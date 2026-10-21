"""Dedicated editing tab. Import the GPU backend only when a job is requested."""

import html
import json
from pathlib import Path
from types import SimpleNamespace
from PIL import Image

import gradio as gr
import torch

from modules import script_callbacks, sd_schedulers, shared
from modules.ui_components import ToolButton
from modules_forge import main_entry, main_thread

from .workflow import PROFILES, SCHEDULES, cyberzit_quality_values, reference_content_box
from .masking import AREA_MODES, WHOLE_MODES, canonical_image, has_painted_area, edit_modes, extract_mask
from .canvas import EditCanvas, MetadataImage, ReferenceImage
from . import model_bar
from .adapters import DEFAULT_FAMILY, EDIT_MODELS, get_adapter
from .batching import run_batch, validate_count
from .outpaint import EDGES, canvas_plan, canvas_images, canvas_reference_resolution, save_crop
from .prompt_metadata import original_prompts


_active = False
PAINT_KEYS = "**Scroll** to zoom · **right-drag** to pan · **Shift + paint** to erase · **F** to enlarge · **R** to fit · **Ctrl+Z** to undo · **W + scroll** for brush size."
EDIT_MODE_INFO = "Standard uses your instruction directly. Camera angle adds viewpoint guidance. Expression transfer adds expression-only guidance for the first additional reference."


def model_controls(family, area_only=False, mode=AREA_MODES[0], canvas_enabled=False):
    fibo = family in EDIT_MODELS and get_adapter(family).key == "fibo2"
    dev = family in EDIT_MODELS and get_adapter(family).guidance > 1
    reference_help = ("Optional. Refer to the source as `<image_1>`, then `<image_2>` and `<image_3>`. "
                      if fibo else "Optional. Refer to the source as **image 1**, then **image 2** and **image 3**.")
    if canvas_enabled or area_only:
        reference_help += " Use references for architecture, materials or appearance in the added / painted areas. The base image stays protected outside the edit selection."
        if fibo:
            reference_help += " Fibo masked + multi-reference guidance is experimental."
    reference_help += " References are numbered in filled-slot order; more references use more memory."
    help_text = ("Paint the entire object and a small border. Fibo receives an **opaque neutral-grey region**, not the green brush overlay. "
                 "Describe what should replace it. Pixels outside the painted area are preserved by compositing."
                 if fibo else "Paint the whole object and a small border, then describe what should replace it. "
                 "**Green-replacement instructions are added automatically.** Unpainted pixels stay unchanged. For expressions, choose Refine / expression.")
    modes = edit_modes(family, area_only)
    selected = modes[0] if mode not in modes else mode
    if selected == "Expression transfer":
        if not canvas_enabled:
            reference_help = "Use the first additional reference for the expression. The source supplies identity, appearance and scene. References are numbered in filled-slot order."
        help_text = "Paint the face to limit the final change. The model receives the clean source face and expression reference; unpainted pixels are preserved by compositing."
    description_help = ("For outpaint, describe the scene itself and what continues into the added space: objects, setting, colors and surfaces. Get prompt from metadata can supply a starting description."
                        if canvas_enabled else "Describe the result you want, not the original. Fibo receives this as a structured result caption alongside your instruction. Leave blank for a plain edit. No cloud service is used.")
    return (gr.update(visible=fibo, info=description_help), reference_help,
            gr.update(interactive=True), gr.update(interactive=True),
            gr.update(choices=modes, value=selected, interactive=len(modes) > 1,
                      label="Painted-area mode" if area_only else "Edit mode",
                      info=("Expression transfer keeps the source face visible and uses the mask for final compositing." if selected == "Expression transfer" else "Neutral-grey masked replacement; the original is kept for the final composite." if fibo else "Replace hides painted content. Refine also sends the clean original.") if area_only else EDIT_MODE_INFO),
            gr.update(value=PAINT_KEYS + "\n\n" + help_text, visible=area_only),
            gr.update(info="Dev: 50 steps is the official starting point; 30 is a faster preview." if dev else "Turbo is trained for 4 steps. Other counts are experimental, not higher-quality presets." if fibo else "Number of sampling steps."),
            gr.update(info="Limits model working size; Shrink by sets the saved canvas size. Shrunk canvases are never upscaled for generation. 0 uses the resulting canvas size." if canvas_enabled else "1024 is closest to Fibo's roughly 1 MP training size. Smaller values are faster. Painted edits preserve the original canvas size; 0 uses native size." if fibo else "Independent of quality. In painted mode this controls crop detail. 0 uses native size."),
            gr.update(interactive=area_only and not canvas_enabled),
            gr.update(interactive=dev, label="Negative prompt" if dev else "Negative prompt (inactive at CFG 1)",
                      info="Dev uses a trained null caption when empty. Negative conditioning is text-only." if dev else "Not used at CFG 1. Express exclusions in the edit instruction."),
            gr.update(interactive=dev, info="Dev default: 5." if dev else "Fixed at 1 for this editing model."))


def canvas_model_controls(family, area_only, mode, enabled):
    # Toggling the canvas must not refresh the retained mode/tip components:
    # Gradio's pending state can change their heights even with progress hidden.
    updates = model_controls(family, area_only, mode, enabled)
    return tuple(updates[i] for i in (0, 1, 7, 8))


def cyberzit_quality(n, sigma_min, sigma_max, device, **kwargs):
    return torch.tensor(cyberzit_quality_values(n), dtype=torch.float32, device=device)


def official_turbo(n, sigma_min, sigma_max, device, **kwargs):
    grid = [1.0, .978453, .95418, .926626, .89508, .845148, .704534, .414568, 0.0]
    positions = torch.linspace(0, 8, n + 1, dtype=torch.float64)
    lower = positions.floor().long().clamp(max=7)
    weights = positions - lower
    values = torch.tensor(grid, dtype=torch.float64)
    return (values[lower] * (1 - weights) + values[lower + 1] * weights).to(device=device, dtype=torch.float32)


def register_schedule():
    for name, label, function in (("qwen_edit_cyberzit_quality", SCHEDULES[0], cyberzit_quality), ("qwen21_turbo", SCHEDULES[2], official_turbo)):
        if label not in sd_schedulers.schedulers_map:
            scheduler = sd_schedulers.Scheduler(name, label, function)
            sd_schedulers.schedulers.append(scheduler)
            sd_schedulers.schedulers_map[scheduler.name] = scheduler
            sd_schedulers.schedulers_map[scheduler.label] = scheduler


def dimensions(image, resolution, area_only=False, mode="Standard"):
    if image is None:
        return "Output follows the first image’s aspect ratio."
    if area_only:
        image = canonical_image(image)
        detail = f"Crop resolution: {resolution if resolution else 'native'}."
        return f"**Painted-area edit** · Output stays **{image.width} × {image.height}**. {detail} Unpainted pixels are preserved."
    left, top, right, bottom = reference_content_box(*image.size, resolution)
    width, height = right - left, bottom - top
    scope = "Camera-angle edit · whole image" if mode == "Camera angle" else "Expression transfer · whole image" if mode == "Expression transfer" else "Whole-image edit"
    return f"**{scope}** · Output: **{width} × {height}** · source: {image.width} × {image.height} · source proportions preserved"


def camera_help(mode, family="", area_only=False):
    if mode == "Expression transfer":
        fallback = "Standard" if not area_only else "Fibo masked edit" if family.startswith("Fibo 2.0") else "Refine / expression"
        return gr.update(visible=True, value=(
            "**If the reference takes over:** Describe only the expression in words, or ask an image-capable LLM to describe it. "
            f"Remove the additional references, switch to **{fallback}**, and paint the face to keep the rest unchanged.\n\n"
            "**Example:** Pucker her lips into a small rounded kiss and narrow one eye slightly."))
    return gr.update(visible=mode == "Camera angle", value="**Tip:** Describe what the new view reveals, including foreground objects, not just the camera move. **Do NOT say ‘keep things the same’ or ‘keep everything unchanged’**—this can work against the new perspective. For example: **Low-angle view, looking up at the underside of the face and held object.** For a scene-specific prompt, give ChatGPT or another image-capable LLM your source image and short request, and ask it to describe how the reframed image should look. Uses the whole image; leave the canvas unpainted.")


def reset_canvas_controls(source, enabled=False):
    width, height = canonical_image(source).size if source is not None else (512, 512)
    return (gr.update(value=bool(enabled), interactive=source is not None),
            *[gr.update(value=0, minimum=-4096, maximum=4096) for _ in range(4)],
            [width, height] if source is not None else [0, 0],
            gr.update(interactive=source is not None), gr.update(choices=[], value=None, visible=False), [],
            gr.update(value="", visible=False))


def get_metadata_prompt(source, family):
    choices = original_prompts(source)
    if not choices:
        return (gr.update(), gr.update(), gr.update(choices=[], value=None, visible=False), [],
                gr.update(value="No readable original prompt found in this image. Your instruction was left unchanged.", visible=True))
    multiple = len(choices) > 1
    fibo = family.startswith("Fibo")
    text = gr.update() if multiple else choices[0][1]
    return (gr.update() if fibo else text, text if fibo else gr.update(),
            gr.update(choices=[(label, str(i)) for i, (label, _) in enumerate(choices)], value=None, visible=multiple), choices,
            gr.update(value="Multiple positive prompts found. Choose one below." if multiple else
                "Original prompt loaded into Describe the finished image. Adjust it for the result you want." if fibo else
                "Original positive prompt loaded into Edit instruction. Adjust it to describe the edit you want.", visible=True))


def select_metadata_prompt(choices, selected, family):
    try:
        index = int(selected)
        if 0 <= index < len(choices):
            return (gr.update(), choices[index][1]) if family.startswith("Fibo") else (choices[index][1], gr.update())
    except (ValueError, TypeError):
        pass
    return gr.update(), gr.update()


def canvas_feedback(size, enabled, left, right, top, bottom, family, painted=False, shrink_by=1, resolution=768):
    enabled = bool(enabled and size and min(size) > 0)
    crop = False
    expanded = False
    crop_label = "Apply crop"
    message = "Load an image to set the canvas edges."
    if size and min(size) > 0:
        try:
            plan = canvas_plan(size, {**dict(zip(EDGES, (left, right, top, bottom))), "shrink_by": shrink_by})
            shrink_by = plan["shrink_by"]
            expanded = plan["expand"]
            crop = plan["changed"] and not expanded and not painted
            width, height = plan["output_size"]
            message = f"**Canvas: {width} × {height}** · original: {size[0]} × {size[1]}. "
            if plan["shrink_by"] > 1:
                message = f"**Output: {width} × {height}** · {plan['canvas_size'][0]} × {plan['canvas_size'][1]} ÷ {plan['shrink_by']:g}. "
                crop_label = "Apply crop / shrink" if any(plan["edges"].values()) else "Apply shrink"
            message += ("Crop / shrink only · no model needed." if crop and shrink_by > 1 else "Crop only · no model needed." if crop else
                f"{'Fibo' if family.startswith('Fibo') else 'The edit model'} will fill the added area{' and your painted areas' if painted else ''}. Original pixels outside painting and seam blending stay unchanged." if expanded else
                "Painted areas will be edited; unpainted retained pixels stay unchanged." if painted else
                "Positive adds space; negative crops that edge.")
            if shrink_by > 1:
                message = message.replace("Original pixels outside", "Downscaled original pixels outside").replace("unpainted retained pixels", "downscaled unpainted pixels")
            if not crop:
                working = canvas_reference_resolution((width, height), resolution, plan["shrink_by"])
                x0, y0, x1, y1 = reference_content_box(width, height, working)
                message += f" Model image: **{x1 - x0} × {y1 - y0}**."
        except ValueError as error:
            message = str(error)
    return (message,
            gr.update(visible=not (enabled and crop), value="Generate outpaint" if enabled and expanded else "Generate edit"),
            gr.update(visible=enabled and crop, value=crop_label))


def run_canvas_crop(source, enabled, left, right, top, bottom, keep_metadata, foreground=None, shrink_by=1):
    global _active
    if not enabled or source is None:
        raise gr.Error("Load an image and enable Crop / outpaint first.")
    edges = {**dict(zip(EDGES, (left, right, top, bottom))), "shrink_by": shrink_by}
    if has_painted_area(foreground):
        plan = canvas_plan(canonical_image(source).size, edges)
        if foreground.getchannel("A").crop(plan["source_box"]).getbbox():
            raise gr.Error("An area is painted. Use Generate edit to apply the painting, or clear it for a crop-only save.")
    _active = True
    try:
        result = main_thread.run_and_wait_result(save_crop, source, edges, keep_metadata)
        if result is None:
            raise RuntimeError(main_thread.last_exception or "The crop could not be saved.")
        output, path, message = result
        items = [{"path": path, "seed": "", "message": message}]
        return output, path, "", gr.update(value=[], visible=False), items, output, f"<p>{html.escape(message)}</p>"
    finally:
        _active = False


def run_canvas_edit(task_id, *args):
    *args, reference2_curves, reference3_curves = args
    *args, batch_count = args
    batch_count = validate_count(batch_count)
    *args, canvas_enabled, left, right, top, bottom, seam_blend, shrink_by = args
    *base, checkpoint_value, modules, dtype, cache, enabled, foreground, feather, mode, result_description, keep_metadata, guidance, preserve_tone = args
    # Read the submitted strokes directly; the UI's paint flag is asynchronous.
    enabled = has_painted_area(foreground)
    editor = {"background": base[0], "layers": [foreground] if foreground is not None else []}
    canvas_edges = {**dict(zip(EDGES, (left, right, top, bottom))), "seam_blend": seam_blend, "shrink_by": shrink_by} if canvas_enabled else None
    if canvas_enabled:
        if base[0] is None:
            raise ValueError("Add a source image first.")
        plan = canvas_plan(canonical_image(base[0]).size, canvas_edges)
        paint = extract_mask(base[0], editor) if enabled else None
        retained_paint = paint is not None and paint.crop(plan["source_box"]).getbbox() is not None
        if not plan["expand"] and not retained_paint:
            return run_canvas_crop(base[0], True, left, right, top, bottom, keep_metadata, foreground, shrink_by)
    checkpoint, adapter, encoder, vae = model_bar.resolve_selection(checkpoint_value, modules)
    return run_edit(task_id, *base, checkpoint.name, encoder, vae, cache, enabled, editor, feather, mode,
                    adapter.label, result_description, keep_metadata, dtype, guidance, preserve_tone, canvas_edges,
                    (reference2_curves, reference3_curves), batch_count=batch_count)


def custom_settings(family=DEFAULT_FAMILY):
    if family == "Fibo 2.0 Dev":
        return "Custom", "**Fibo Dev custom settings.** The official starting point is 50 steps and CFG 5."
    return "Custom", ("**Fibo custom settings.** Four steps are recommended for Turbo; more steps are not a guaranteed quality improvement."
                      if family in EDIT_MODELS and get_adapter(family).key == "fibo2" else "Custom sampling settings. Quality presets leave resolution unchanged.")


def run_edit(task_id, *args, batch_count=1):
    global _active
    from .native import generate
    _active = True
    try:
        result = main_thread.run_and_wait_result(run_batch, generate, args, batch_count, shared.state)
        if result is None:
            raise RuntimeError(main_thread.last_exception or "The edit did not complete. See the Forge console.")
        output, items, message = result
        if not items:
            # A validation failure or early cancel must not erase the previous result.
            return (*[gr.update() for _ in range(6)], f"<p>{html.escape(message)}</p>")
        gallery = [(item["path"], f"{i + 1} · seed {item['seed']}") for i, item in enumerate(items)]
        comparison = args[0]
        if len(args) > 24 and args[24] is not None:
            plan = canvas_plan(canonical_image(comparison).size, args[24])
            comparison, _ = canvas_images(comparison, plan)
        return (output, items[-1]["path"], items[-1]["seed"],
                gr.update(value=gallery, visible=batch_count > 1, selected_index=len(items) - 1),
                items, comparison, f"<p>{html.escape(message)}</p>")
    finally:
        _active = False


def select_batch_result(items, selection):
    if _active:
        return tuple(gr.update() for _ in range(4))
    try:
        index = json.loads(selection)["index"]
    except (ValueError, TypeError, KeyError):
        return tuple(gr.update() for _ in range(4))
    if not isinstance(index, int) or not 0 <= index < len(items):
        return tuple(gr.update() for _ in range(4))
    item = items[index]
    if not Path(item["path"]).is_file():
        raise gr.Error("This saved image is no longer available.")
    return item["path"], item["path"], item["seed"], f"<p>{html.escape(item['message'])}</p>"


def cancel_edit():
    if _active:
        shared.state.interrupt()
        return "<p>Cancelling… waiting for the current operation to finish.</p>"
    return gr.update()


def reuse_result(image, saved_path=None):
    if image is None:
        raise gr.Error("Generate an edit before using its result as the source.")
    if saved_path and Path(saved_path).is_file():
        with Image.open(saved_path) as saved:
            return saved.copy()
    return image


def curves_request(payload, saved_path, keep_metadata):
    from .adjustments import describe_result, save_adjustment
    from .fibo_defaults import prepare_default, write_config
    request_id = ""
    try:
        if not isinstance(payload, str) or len(payload) > 24000:
            raise ValueError("Invalid curves request.")
        request = json.loads(payload)
        if not isinstance(request, dict) or request.get("version") != 1:
            raise ValueError("Invalid curves request.")
        request_id = request.get("id", "")
        if request.get("op") == "context":
            return gr.update(), gr.update(), gr.update(), json.dumps(describe_result(saved_path, payload))
        if _active:
            raise ValueError("Wait for the current edit to finish before applying curves.")
        config = None
        if request.get("op") == "fibo_default" or request.get("use_fibo_default") is True:
            config = prepare_default(saved_path, payload)
        if request.get("op") == "fibo_default":
            write_config(config)
            return gr.update(), gr.update(), gr.update(), json.dumps({"id": request_id, "ok": True,
                "op": "fibo_default", "enabled": config["enabled"], "available": config.get("preset") is not None})
        output, path, request_id = save_adjustment(saved_path, payload, keep_metadata)
        if config is not None:
            write_config(config)
        return output, path, f"<p>Saved {html.escape(Path(path).name)} · curves applied · previous file kept</p>", json.dumps({"id": request_id, "ok": True})
    except (ValueError, TypeError, KeyError, OSError) as error:
        return gr.update(), gr.update(), gr.update(), json.dumps({"id": request_id, "ok": False, "error": str(error)})


def create_tab():
    main_entry.refresh_models()
    model_bar.bar.clear()
    model_bar.bound = False
    model_bar.workspace = None
    with gr.Blocks(analytics_enabled=False) as tab:
        with gr.Column(elem_id="qwen_edit_workspace"):
            gr.HTML('<div class="qe-heading"><h2>Image Edit</h2></div>')
            family = gr.Textbox(value="", visible=False, elem_id="image_edit_model")
            selection_signature = gr.State("")
            with gr.Row(elem_id="image_edit_model_row"):
                backend_label = gr.Markdown("Select your edit checkpoint in Forge's top model bar.", elem_id="image_edit_model_status")
                correct_components = gr.Button("Use matching encoder / VAE", size="sm", scale=0, min_width=220, elem_id="image_edit_correct_components")
            with gr.Row(equal_height=True):
                with gr.Column(scale=1, min_width=350, elem_id="image_edit_source_column"):
                    mask_editor = EditCanvas()
                    source = mask_editor.background
                    # Derived, hidden transport value, never a user toggle.
                    # Gradio 4 inserts State placeholders into JS submit inputs.
                    area_only = gr.Checkbox(value=False, visible=False, interactive=False)
                    canvas_enabled = gr.Checkbox(value=False, label="Crop / outpaint", interactive=False, elem_id="image_edit_canvas_enabled")
                    canvas_source_size = gr.State([0, 0])
                    # Both sections stay mounted. CSS switches them from the checkbox
                    # in one frame, without queued visibility updates or moving the toggle.
                    with gr.Column(elem_id="image_edit_canvas_controls"):
                        gr.Markdown("**Added pixels per edge** · positive expands, negative crops. The green outline is the final canvas; it stays visible.")
                        gr.Markdown("**Paint over edge objects to replace them while extending the scene.** Added space and painted areas are filled together.")
                        with gr.Row(elem_id="image_edit_canvas_horizontal"):
                            canvas_left = gr.Slider(-4096, 4096, value=0, step=1, label="Left", min_width=140, elem_id="image_edit_canvas_left")
                            canvas_right = gr.Slider(-4096, 4096, value=0, step=1, label="Right", min_width=140, elem_id="image_edit_canvas_right")
                        with gr.Row(elem_id="image_edit_canvas_vertical"):
                            canvas_top = gr.Slider(-4096, 4096, value=0, step=1, label="Top", min_width=140, elem_id="image_edit_canvas_top")
                            canvas_bottom = gr.Slider(-4096, 4096, value=0, step=1, label="Bottom", min_width=140, elem_id="image_edit_canvas_bottom")
                        canvas_summary = gr.Markdown(elem_id="image_edit_canvas_summary")
                        with gr.Row():
                            canvas_shrink = gr.Dropdown([("1× (off)", 1), ("1.5×", 1.5), ("2×", 2), ("3×", 3), ("4×", 4)], value=1,
                                label="Shrink by", info="2× halves width and height, including added edges. The loaded source stays untouched.",
                                scale=1, min_width=150, elem_id="image_edit_canvas_shrink")
                            seam_blend = gr.Slider(0, 128, value=32, step=1, label="Seam blending (output px)",
                                info="Crossfade after generation inside the original. No image blur; 0 keeps a hard edge.",
                                scale=2, min_width=220, elem_id="image_edit_seam_blend")
                        canvas_reset = gr.Button("Reset edges", size="sm", elem_id="image_edit_canvas_reset")
                    with gr.Column(elem_id="image_edit_standard_controls"):
                        gr.Markdown("**Paint an edit area to confine changes.** Leave unpainted for a whole-image edit.")
                        area_mode = gr.Dropdown(list(WHOLE_MODES), value=WHOLE_MODES[0], label="Edit mode", info=EDIT_MODE_INFO, elem_id="qwen_edit_area_mode")
                        camera_note = gr.Markdown(visible=False, elem_id="image_edit_camera_help")
                        mask_help = gr.Markdown("**Scroll** to zoom · **right-drag** to pan · **Shift + paint** to erase · **F** to enlarge · **R** to fit · **Ctrl+Z** to undo · **W + scroll** for brush size.\n\nPaint the whole object and a small border, then describe what should replace it. **Green-replacement instructions are added automatically**—you do not need to type them. Unpainted pixels stay unchanged. For facial expressions, choose Refine / expression.", visible=False)
                        size_label = gr.Markdown("Output follows the first image’s aspect ratio.")
                with gr.Column(scale=1, min_width=350, elem_id="qwen_edit_result_container"):
                    result = gr.Image(label="Edited result · click to enlarge", type="pil", image_mode="RGBA", format="png", interactive=False, height=420, elem_id="qwen_edit_result")
                    with gr.Row(elem_id="qwen_edit_result_actions"):
                        reuse = gr.Button("Use result as source", size="sm")
                        with gr.Column(min_width=200, elem_id="image_edit_download_column"):
                            download_button = gr.DownloadButton("Download PNG with settings", size="sm", interactive=False, elem_id="qwen_edit_download")
                            gr.Markdown("Also saved automatically to Forge’s img2img output folder (or your custom output folder).", elem_id="image_edit_save_note")
                    # Retain the full native saved-file path for reuse and curves.
                    download = gr.File(label="Edited PNG", interactive=False, elem_id="image_edit_download_data")
                    batch_gallery = gr.Gallery(label="Batch results · select to review", columns=4, rows=1, height=220,
                        object_fit="contain", preview=False, allow_preview=False, visible=False, elem_id="image_edit_batch_gallery")
                    batch_items = gr.State([])
                    batch_selection = gr.Textbox(visible=False, elem_id="image_edit_batch_selection")
                    batch_source = MetadataImage(visible=False, numpy=False, elem_id="image_edit_batch_source")
            with gr.Row(elem_id="image_edit_run_row"):
                with gr.Row(elem_id="image_edit_seed_controls"):
                    seed = gr.Textbox(value="-1", label="Seed", elem_id="qwen_edit_seed", min_width=150, scale=1)
                    random_seed = ToolButton("🎲", elem_id="image_edit_random_seed", tooltip="Random seed (-1) for each edit")
                    reuse_seed = ToolButton("♻️", elem_id="image_edit_reuse_seed", tooltip="Reuse the selected result's seed")
                    batch_count = gr.Number(value=1, minimum=1, maximum=64, precision=0, step=1, label="Batch count", scale=0, min_width=100, elem_id="image_edit_batch_count")
                with gr.Row(elem_id="image_edit_run_buttons"):
                    generate = gr.Button("Generate edit", variant="primary", elem_id="qwen_edit_generate", scale=3, interactive=False)
                    apply_crop = gr.Button("Apply crop", variant="primary", elem_id="image_edit_apply_crop", scale=3, visible=False)
                    cancel = gr.Button("Cancel", elem_id="qwen_edit_cancel", scale=1)
            last_seed = gr.Textbox(value="", visible=False, elem_id="qwen_edit_last_seed")
            status = gr.HTML(elem_id="qwen_edit_status")
            instruction = gr.Textbox(label="Edit instruction", placeholder="Remove the stray object and reconstruct the background. Or: give this person a subtle, natural smile while keeping their identity.", lines=3, elem_id="qwen_edit_instruction")
            result_description = gr.Textbox(label="Describe the finished image (optional, Fibo)",
                placeholder="Example: The woman remains beside an empty bed with an uninterrupted green bedspread and white pillows.",
                info="Describe the result you want, not the original. Fibo receives this as a structured result caption alongside your instruction. Leave blank for a plain edit. No cloud service is used.",
                value="", lines=3, visible=False, elem_id="fibo_edit_result_description")
            with gr.Row(elem_id="image_edit_prompt_heading"):
                get_prompt = gr.Button("Get prompt from metadata", size="sm", scale=0, min_width=210, interactive=False, elem_id="image_edit_get_prompt")
                prompt_note = gr.Markdown(visible=False, elem_id="image_edit_prompt_note")
            prompt_choices = gr.Dropdown([], label="Metadata prompt", visible=False, elem_id="image_edit_prompt_choices")
            prompt_items = gr.State([])
            with gr.Row():
                profile = gr.Dropdown(list(PROFILES), value="Normal", label="Speed / quality", elem_id="qwen_edit_quality", scale=1, min_width=240)
                resolution = gr.Dropdown([0, 512, 768, 1024, 1536, 2048], value=768, allow_custom_value=True, label="Resolution", info="Independent of quality. In painted-area mode this controls crop detail; the final image keeps its original size. 0 uses native size.", elem_id="qwen_edit_resolution", scale=1, min_width=240)
            profile_summary = gr.Markdown("Everyday edits using the efficient Comfy sampler. **12 steps.** Resolution is unchanged.", elem_id="qwen_edit_preset_summary")
            preserve_tone = gr.Checkbox(value=False, label="Auto-correct global brightness / contrast", elem_id="image_edit_preserve_tone",
                info="Next generation only. Estimates overall drift from unchanged areas, not contrast changes confined to the edited object or lost texture. For manual adjustment, open the result → Curves. Leave off for camera moves or relighting.")
            with gr.Accordion("Additional reference images", open=False):
                reference_help = gr.Markdown("Optional. Refer to the source as **image 1**, then **image 2** and **image 3** in your instruction. More references use more memory.")
                with gr.Row(elem_id="image_edit_reference_row"):
                    references = []
                    for slot in (2, 3):
                        with gr.Column(min_width=280):
                            references.append(ReferenceImage(label=f"Image {slot}", type="pil", image_mode="RGBA", format="png", height=240, elem_id=f"image_edit_reference{slot}"))
                            gr.HTML(f'<div class="qe-reference-editor" data-reference-slot="{slot}"><button type="button" data-action="curves" aria-expanded="false" aria-controls="image_edit_reference_panel{slot}" disabled>Edit</button><span class="qe-reference-note">Load a reference to adjust its tones.</span></div>')
                    reference2, reference3 = references
                gr.HTML('<div id="image_edit_reference_workspace" hidden>'
                        '<div class="qe-reference-editor qe-reference-panel-host">'
                        '<div id="image_edit_reference_panel2" class="qe-curves-panel" hidden></div>'
                        '<div id="image_edit_reference_panel3" class="qe-curves-panel" hidden></div></div>'
                        '<figure class="qe-reference-source"><figcaption><strong>&lt;image_1&gt; · Source image</strong>'
                        '<span>Color reference only</span></figcaption>'
                        '<img alt="Image 1 source for color comparison" hidden>'
                        '<p>Load image_1 to compare colors.</p></figure></div>')
                reference2_curves = gr.Textbox(value="", visible=False)
                reference3_curves = gr.Textbox(value="", visible=False)
                for component in (reference2_curves, reference3_curves):
                    component.do_not_save_to_config = True
            with gr.Accordion("Sampling settings", open=False):
                feather = gr.Slider(0, 64, value=8, step=1, label="Painted edge blending", interactive=False, info="Only used with a painted area. Softens its inside edge; pixels outside the painting stay untouched.")
                with gr.Row():
                    steps = gr.Slider(1, 150, value=12, step=1, label="Steps")
                    sampler = gr.Dropdown(["Res Multistep", "Euler"], value="Res Multistep", label="Sampler")
                    schedule = gr.Dropdown(list(SCHEDULES), value=SCHEDULES[0], label="Schedule")
                    guidance = gr.Slider(1, 15, value=1, step=0.1, label="CFG", interactive=False)
                prefix_cache = gr.Checkbox(value=True, label="Cache reference attention between steps", info="Turn off to save VRAM; recommended for 12–16 GB cards.")
                negative = gr.Textbox(value="", label="Negative prompt (inactive at CFG 1)", interactive=False, lines=1, info="Not used by these CFG 1 editing modes. Express exclusions in the edit instruction.")
            keep_metadata = gr.Checkbox(value=True, label="Keep original metadata", elem_id="image_edit_keep_metadata",
                info="Retain the source metadata and append an Image Edit section and recipe. Turn off to save only the new edit metadata. Forge's global metadata setting still applies.")
            with gr.Accordion("Import settings from a generated PNG", open=False):
                gr.Markdown("Reads a PNG made by Image Edit, older Qwen Edit recipes, or a simple Qwen 2.1 Comfy workflow. Upload the original source image separately.")
                recipe_file = gr.File(file_types=[".png"], type="filepath", label="Generated PNG")
                import_button = gr.Button("Import recipe", size="sm")
                import_status = gr.Markdown()
            handoff = MetadataImage(visible=False, numpy=False, elem_id="image_edit_handoff")
            curves_payload = gr.Textbox(visible=False, elem_id="image_edit_curves_request")
            curves_receipt = gr.Textbox(visible=False)
            curves_payload.change(curves_request, [curves_payload, download, keep_metadata],
                [result, download, status, curves_receipt], show_progress="hidden", api_name="image_edit_curves").then(
                    fn=None, inputs=[curves_receipt], outputs=[],
                    js="receipt => { window.imageEditCurvesSaved?.(receipt); }", api_name=False)
            task_id = gr.Textbox(visible=False)
            edge_controls = [canvas_left, canvas_right, canvas_top, canvas_bottom]
            for component in (canvas_enabled, *edge_controls, seam_blend, canvas_shrink, prompt_choices):
                component.do_not_save_to_config = True
            source.change(reset_canvas_controls, [source, canvas_enabled],
                [canvas_enabled, *edge_controls, canvas_source_size, get_prompt, prompt_choices, prompt_items, prompt_note], show_progress="hidden", api_name=False).then(
                canvas_feedback, [canvas_source_size, canvas_enabled, *edge_controls, family, area_only, canvas_shrink, resolution],
                [canvas_summary, generate, apply_crop], queue=False, show_progress="hidden", api_name=False)
            canvas_reset.click(lambda: (0, 0, 0, 0), outputs=edge_controls, show_progress="hidden", api_name=False)
            for component in (canvas_enabled, *edge_controls, family, area_only, canvas_shrink, resolution):
                component.change(canvas_feedback, [canvas_source_size, canvas_enabled, *edge_controls, family, area_only, canvas_shrink, resolution],
                    [canvas_summary, generate, apply_crop], queue=False, show_progress="hidden", api_name=False)
            for component in (canvas_enabled, *edge_controls):
                component.change(None, [canvas_enabled, *edge_controls], [],
                    js="(enabled, left, right, top, bottom) => { window.imageEditSetCanvasEdges?.(enabled, left, right, top, bottom); }", api_name=False)
            from modules.call_queue import wrap_gradio_gpu_call
            apply_crop.click(wrap_gradio_gpu_call(run_canvas_crop, extra_outputs=[gr.update() for _ in range(6)]),
                [source, canvas_enabled, *edge_controls, keep_metadata, mask_editor.foreground, canvas_shrink],
                [result, download, last_seed, batch_gallery, batch_items, batch_source, status], api_name="image_edit_crop")
            for component in (family, result_description, profile, resolution, steps, sampler, schedule, guidance, prefix_cache, keep_metadata, preserve_tone, area_only, area_mode, mask_editor.block, mask_editor.background, mask_editor.foreground, feather, curves_payload, curves_receipt, batch_count, batch_gallery, batch_source, batch_selection, last_seed):
                component.do_not_save_to_config = True
            for component in (steps, sampler, schedule, guidance, prefix_cache):
                component.input(custom_settings, [family], outputs=[profile, profile_summary], show_progress="hidden")
            mask_editor.foreground.change(has_painted_area, [mask_editor.foreground], [area_only], show_progress="hidden", api_name=False)
            for component in (source, resolution, area_only, area_mode):
                component.change(dimensions, [source, resolution, area_only, area_mode], [size_label], queue=False, show_progress="hidden")
            for component in (area_mode, family, area_only):
                component.change(camera_help, [area_mode, family, area_only], [camera_note], queue=False, show_progress="hidden")
            canvas_enabled.change(canvas_model_controls, [family, area_only, area_mode, canvas_enabled],
                [result_description, reference_help, resolution, feather], queue=False, show_progress="hidden", api_name=False)
            for component in (family, area_only, area_mode):
                event = component.input if component is area_mode else component.change
                event(model_controls, [family, area_only, area_mode, canvas_enabled],
                    [result_description, reference_help, reference2, reference3, area_mode, mask_help, steps, resolution, feather, negative, guidance],
                    js="(family, enabled, mode, canvas) => { qwenEditSetModel(family); return [family, enabled, mode, canvas]; }" if component is family else None,
                    queue=False, show_progress="hidden", api_name="image_edit_controls" if component is family else False)
            reuse.click(reuse_result, [result, download], [source])
            get_prompt.click(get_metadata_prompt, [source, family], [instruction, result_description, prompt_choices, prompt_items, prompt_note], show_progress="hidden", api_name=False)
            prompt_choices.input(select_metadata_prompt, [prompt_items, prompt_choices, family], [instruction, result_description], show_progress="hidden", api_name=False)
            download.change(lambda path: gr.update(value=path, interactive=bool(path)), [download], [download_button], show_progress="hidden", api_name=False)
            random_seed.click(lambda: "-1", outputs=[seed], queue=False, show_progress="hidden")
            reuse_seed.click(lambda last: last or gr.update(), [last_seed], [seed], queue=False, show_progress="hidden")
            # Send only a thumbnail index. Gradio 4 SelectData rejects Forge's
            # native output paths because they deliberately bypass upload cache.
            batch_selection.change(select_batch_result, [batch_items, batch_selection], [result, download, last_seed, status], show_progress="hidden", api_name=False)
            cancel.click(cancel_edit, outputs=[status], queue=False)
    model_bar.workspace = SimpleNamespace(**locals())
    # Retain the tab ID for existing canvas and image-browser handoffs.
    return [(tab, "Image Edit", "qwen_edit")]


def register():
    register_schedule()
    script_callbacks.on_ui_tabs(create_tab)
    script_callbacks.on_after_component(model_bar.after_component)
