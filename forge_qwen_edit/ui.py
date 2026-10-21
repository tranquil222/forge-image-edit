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

from .workflow import PROFILES, SCHEDULES, cyberzit_quality_values, reference_size
from .masking import AREA_MODES, WHOLE_MODES, canonical_image, has_painted_area, edit_modes
from .canvas import EditCanvas, MetadataImage
from . import model_bar
from .adapters import DEFAULT_FAMILY, EDIT_MODELS, get_adapter
from .batching import run_batch, validate_count


_active = False
PAINT_KEYS = "**Scroll** to zoom · **right-drag** to pan · **Shift + paint** to erase · **F** to enlarge · **R** to fit · **Ctrl+Z** to undo · **W + scroll** for brush size."


def model_controls(family, area_only=False, mode=AREA_MODES[0]):
    fibo = family in EDIT_MODELS and get_adapter(family).key == "fibo2"
    dev = family in EDIT_MODELS and get_adapter(family).guidance > 1
    reference_help = ("Optional. Refer to the source as `<image_1>`, then `<image_2>` and `<image_3>`. "
                      "Fibo masked editing uses only the source; additional references are not used when an area is painted."
                      if fibo else "Optional. Refer to the source as **image 1**, then **image 2** and **image 3**. More references use more memory.")
    help_text = ("Paint the entire object and a small border. Fibo receives an **opaque neutral-grey region**, not the green brush overlay. "
                 "Describe what should replace it. Pixels outside the painted area are preserved by compositing."
                 if fibo else "Paint the whole object and a small border, then describe what should replace it. "
                 "**Green-replacement instructions are added automatically.** Unpainted pixels stay unchanged. For expressions, choose Refine / expression.")
    modes = edit_modes(family, area_only)
    selected = modes[0] if mode not in modes else mode
    return (gr.update(visible=fibo), reference_help,
            gr.update(interactive=not (fibo and area_only)), gr.update(interactive=not (fibo and area_only)),
            gr.update(choices=modes, value=selected, interactive=len(modes) > 1, visible=True,
                      label="Painted-area mode" if area_only else "Edit mode",
                      info=("Neutral-grey masked replacement; the original is kept for the final composite." if fibo else "Replace hides painted content. Refine also sends the clean original.") if area_only else "Standard uses your instruction directly. Camera angle adds guidance to redraw the scene from the requested viewpoint."),
            gr.update(value=PAINT_KEYS + "\n\n" + help_text, visible=area_only),
            gr.update(info="Dev: 50 steps is the official starting point; 30 is a faster preview." if dev else "Turbo is trained for 4 steps. Other counts are experimental, not higher-quality presets." if fibo else "Number of sampling steps."),
            gr.update(info="1024 is closest to Fibo's roughly 1 MP training size. Smaller values are faster. Painted edits preserve the original canvas size; 0 uses native size." if fibo else "Independent of quality. In painted mode this controls crop detail. 0 uses native size."),
            gr.update(interactive=area_only),
            gr.update(interactive=dev, label="Negative prompt" if dev else "Negative prompt (inactive at CFG 1)",
                      info="Dev uses a trained null caption when empty. Negative conditioning is text-only." if dev else "Not used at CFG 1. Express exclusions in the edit instruction."),
            gr.update(interactive=dev, info="Dev default: 5." if dev else "Fixed at 1 for this editing model."))


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
    width, height = reference_size(*image.size, resolution)
    scope = "Camera-angle edit · whole image" if mode == "Camera angle" else "Whole-image edit"
    return f"**{scope}** · Output: **{width} × {height}** · source: {image.width} × {image.height} · no crop"


def camera_help(mode):
    return gr.update(visible=mode == "Camera angle", value="**Tip:** Describe what the new view reveals, including foreground objects, not just the camera move. **Do NOT say ‘keep things the same’ or ‘keep everything unchanged’**—this can work against the new perspective. For example: **Low-angle view, looking up at the underside of the face and held object.** For a scene-specific prompt, give ChatGPT or another image-capable LLM your source image and short request, and ask it to describe how the reframed image should look. Uses the whole image; leave the canvas unpainted.")


def run_canvas_edit(task_id, *args):
    *args, batch_count = args
    batch_count = validate_count(batch_count)
    *base, checkpoint_value, modules, dtype, cache, enabled, foreground, feather, mode, result_description, keep_metadata, guidance, preserve_tone = args
    checkpoint, adapter, encoder, vae = model_bar.resolve_selection(checkpoint_value, modules)
    # Derive this from the submitted strokes, not an asynchronously updated UI
    # flag. Painting, erasing, undo and the native clear button all work directly.
    enabled = has_painted_area(foreground)
    editor = {"background": base[0], "layers": [foreground] if foreground is not None else []}
    return run_edit(task_id, *base, checkpoint.name, encoder, vae, cache, enabled, editor, feather, mode,
                    adapter.label, result_description, keep_metadata, dtype, guidance, preserve_tone, batch_count=batch_count)


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
        return (output, items[-1]["path"], items[-1]["seed"],
                gr.update(value=gallery, visible=batch_count > 1, selected_index=len(items) - 1),
                items, args[0], f"<p>{html.escape(message)}</p>")
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
        output, path, request_id = save_adjustment(saved_path, payload, keep_metadata)
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
            gr.HTML('<div class="qe-heading"><div class="qe-eyebrow">FORGE NEO / IMAGE EDITING</div><h2>Image Edit</h2><p>Describe a change. Keep the rest.</p></div>')
            family = gr.Textbox(value="", visible=False, elem_id="image_edit_model")
            selection_signature = gr.State("")
            backend_label = gr.Markdown("Select your edit checkpoint in Forge's top model bar.")
            correct_components = gr.Button("Use matching encoder / VAE", size="sm", elem_id="image_edit_correct_components")
            with gr.Row(equal_height=True):
                with gr.Column(scale=1, min_width=350):
                    mask_editor = EditCanvas()
                    source = mask_editor.background
                    # Derived, hidden transport value, never a user toggle.
                    # Gradio 4 inserts State placeholders into JS submit inputs.
                    area_only = gr.Checkbox(value=False, visible=False, interactive=False)
                    gr.Markdown("**Paint an edit area to confine changes.** Leave unpainted for a whole-image edit.")
                    area_mode = gr.Dropdown(list(WHOLE_MODES), value=WHOLE_MODES[0], label="Edit mode", info="Standard uses your instruction directly. Camera angle adds guidance to redraw the scene from the requested viewpoint.", elem_id="qwen_edit_area_mode")
                    camera_note = gr.Markdown(visible=False, elem_id="image_edit_camera_help")
                    mask_help = gr.Markdown("**Scroll** to zoom · **right-drag** to pan · **Shift + paint** to erase · **F** to enlarge · **R** to fit · **Ctrl+Z** to undo · **W + scroll** for brush size.\n\nPaint the whole object and a small border, then describe what should replace it. **Green-replacement instructions are added automatically**—you do not need to type them. Unpainted pixels stay unchanged. For facial expressions, choose Refine / expression.", visible=False)
                    size_label = gr.Markdown("Output follows the first image’s aspect ratio.")
                with gr.Column(scale=1, min_width=350, elem_id="qwen_edit_result_container"):
                    result = gr.Image(label="Edited result · click to enlarge", type="pil", image_mode="RGBA", format="png", interactive=False, height=420, elem_id="qwen_edit_result")
                    with gr.Row(elem_id="qwen_edit_result_actions"):
                        reuse = gr.Button("Use result as source", size="sm")
                        download = gr.File(label="Download PNG with recipe", interactive=False, height=72, elem_id="qwen_edit_download")
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
                    cancel = gr.Button("Cancel", elem_id="qwen_edit_cancel", scale=1)
            last_seed = gr.Textbox(value="", visible=False, elem_id="qwen_edit_last_seed")
            status = gr.HTML(elem_id="qwen_edit_status")
            instruction = gr.Textbox(label="Edit instruction", placeholder="Remove the stray object and reconstruct the background. Or: give this person a subtle, natural smile while keeping their identity.", lines=3, elem_id="qwen_edit_instruction")
            result_description = gr.Textbox(label="Describe the finished image (optional, Fibo)",
                placeholder="Example: The woman remains beside an empty bed with an uninterrupted green bedspread and white pillows.",
                info="Describe the result you want, not the original. Fibo receives this as a structured result caption alongside your instruction. Leave blank for a plain edit. No cloud service is used.",
                value="", lines=3, visible=False, elem_id="fibo_edit_result_description")
            with gr.Row():
                profile = gr.Dropdown(list(PROFILES), value="Normal", label="Speed / quality", elem_id="qwen_edit_quality", scale=1, min_width=240)
                resolution = gr.Dropdown([0, 512, 768, 1024, 1536, 2048], value=768, allow_custom_value=True, label="Resolution", info="Independent of quality. In painted-area mode this controls crop detail; the final image keeps its original size. 0 uses native size.", elem_id="qwen_edit_resolution", scale=1, min_width=240)
            profile_summary = gr.Markdown("Everyday edits using the efficient Comfy sampler. **12 steps.** Resolution is unchanged.", elem_id="qwen_edit_preset_summary")
            preserve_tone = gr.Checkbox(value=False, label="Match source brightness / contrast", elem_id="image_edit_preserve_tone",
                info="Reduce global tone drift after an object edit. Does not prevent texture changes; paint an edit area to keep the rest exact. Leave off for lighting or contrast changes.")
            with gr.Accordion("Additional reference images", open=False):
                reference_help = gr.Markdown("Optional. Refer to the source as **image 1**, then **image 2** and **image 3** in your instruction. More references use more memory.")
                with gr.Row():
                    reference2 = gr.Image(label="Image 2", type="pil", image_mode="RGBA", height=240)
                    reference3 = gr.Image(label="Image 3", type="pil", image_mode="RGBA", height=240)
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
            for component in (family, result_description, profile, resolution, steps, sampler, schedule, guidance, prefix_cache, keep_metadata, preserve_tone, area_only, area_mode, mask_editor.block, mask_editor.background, mask_editor.foreground, feather, curves_payload, curves_receipt, batch_count, batch_gallery, batch_source, batch_selection, last_seed):
                component.do_not_save_to_config = True
            for component in (steps, sampler, schedule, guidance, prefix_cache):
                component.input(custom_settings, [family], outputs=[profile, profile_summary], show_progress="hidden")
            mask_editor.foreground.change(has_painted_area, [mask_editor.foreground], [area_only], show_progress="hidden", api_name=False)
            for component in (source, resolution, area_only, area_mode):
                component.change(dimensions, [source, resolution, area_only, area_mode], [size_label], show_progress="hidden")
            area_mode.change(camera_help, [area_mode], [camera_note], show_progress="hidden")
            for component in (family, area_only):
                component.change(model_controls, [family, area_only, area_mode],
                    [result_description, reference_help, reference2, reference3, area_mode, mask_help, steps, resolution, feather, negative, guidance],
                    js="(family, enabled, mode) => { qwenEditSetModel(family); return [family, enabled, mode]; }" if component is family else None,
                    show_progress="hidden", api_name="image_edit_controls" if component is family else False)
            reuse.click(reuse_result, [result, download], [source])
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
