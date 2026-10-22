"""Bridge the editing workspace to Forge's existing model controls."""
import html
from pathlib import Path

import gradio as gr
from gradio.context import Context

from modules import sd_models, shared
from modules_forge import main_entry

from .adapters import EDIT_MODELS
from .selection import adapter_for_checkpoint, basename, profiles_for, required_components, suggested_components, validate_components
from .workflow import read_recipe

workspace = None
bar = {}
bound = False


def sampling_choices():
    """Use Forge's live registry, including samplers added by other extensions."""
    from modules import sd_samplers, sd_schedulers
    return (list(dict.fromkeys(item.name for item in sd_samplers.all_samplers)),
            list(dict.fromkeys(item.label for item in sd_schedulers.schedulers_map.values())))


def resolve_checkpoint(value):
    matches = [checkpoint for checkpoint in sd_models.checkpoints_list.values()
               if value in (*checkpoint.ids, checkpoint.short_title, checkpoint.filename)]
    if len(matches) != 1:
        raise ValueError("Select an installed checkpoint in Forge's top Checkpoint field.")
    return matches[0]


def resolve_selection(value, modules, allow_custom=False, custom_vae=None):
    checkpoint = resolve_checkpoint(value)
    adapter = adapter_for_checkpoint(checkpoint)
    if adapter is None:
        raise ValueError("Unsupported checkpoint for Image Edit. Choose Qwen Image 2.1 (base/Turbo) or Fibo 2.0 (Edit Turbo/Dev) in the top Checkpoint field.")
    encoder, vae = validate_components(adapter, modules, main_entry.module_list, allow_custom, custom_vae)
    ensure_backend(adapter)
    return checkpoint, adapter, encoder, vae


def ensure_backend(adapter):
    from backend.args import dynamic_args
    from modules_forge.presets import PresetArch
    root = Path(shared.script_path)
    required = (f"backend/diffusion_engine/{adapter.key}.py", f"backend/nn/{adapter.key}.py", f"backend/text_processing/{adapter.key}_engine.py")
    if not all((root / name).is_file() for name in required):
        raise ValueError("Backend setup required. Native model support is missing; this is not a checkpoint-folder problem. "
                         "Update Image Edit, fully close the Forge console and relaunch your normal launcher. "
                         "If this remains, run the setup check in the guide; your Forge build may need a newer backend patch.")
    if not hasattr(dynamic_args, adapter.flag) or not hasattr(dynamic_args, "qwen21_prefix_cache") or adapter.key not in PresetArch.__members__:
        raise ValueError("Backend setup required. Native files exist, but model registration is not loaded. "
                         "Fully close the Forge console and relaunch your normal launcher, not just Reload UI. "
                         "If this remains, run the setup check in the guide.")


def component_summary(checkpoint, encoder, vae):
    files = zip(("Checkpoint", "Encoder", "VAE"), (checkpoint, encoder, vae))
    return '<div class="qe-model-files">' + "".join(
        f"<span><strong>{kind}:</strong> <code>{html.escape(basename(name))}</code></span>"
        for kind, name in files) + '</div>'


def selection_status(value, modules, allow_custom=False, custom_vae=None):
    try:
        checkpoint = resolve_checkpoint(value)
        adapter = adapter_for_checkpoint(checkpoint)
    except ValueError:
        adapter = None
    if adapter is None:
        return ("Choose a **Qwen Image 2.1** or **Fibo 2.0** checkpoint in the top model bar. "
                "[Exact model files](https://github.com/tranquil222/forge-image-edit/blob/main/MODELS.md)."), False
    try:
        checkpoint, adapter, encoder, vae = resolve_selection(value, modules, allow_custom, custom_vae)
        message = component_summary(checkpoint.filename, encoder, vae)
        if allow_custom:
            message += "\n\nCustom filenames allowed. Actual compatibility is checked when the model loads."
        elif adapter.key == "qwen21" and basename(vae).lower() != "texture_fix_vae_for_qwen_image_2.1_bf16.safetensors":
            message += "\n\nFine checkerboard? [Optional Qwen texture-fix VAE](https://github.com/tranquil222/forge-image-edit/blob/main/MODELS.md#qwen-21-texture-fix-vae)."
        return message, True
    except ValueError as error:
        if str(error).startswith("Backend setup required"):
            detail = html.escape(str(error).removeprefix("Backend setup required. "))
            return ("**Backend setup required.** " + detail + " "
                    "[Step-by-step setup guide](https://github.com/tranquil222/forge-image-edit/blob/main/COMPATIBILITY.md#fibo2-is-missing-from-ui-preset-or-backend-setup-required)."), False
        requirements = component_summary(checkpoint.filename, *adapter.defaults[1:])
        return ("**Model setup needs attention.** " + html.escape(str(error)) + "\n\n" + requirements + "\n\n"
                "[Downloads](https://github.com/tranquil222/forge-image-edit/blob/main/MODELS.md)."), False


def observe_checkpoint(value, modules, previous, allow_custom=False, custom_vae=None):
    try:
        checkpoint = resolve_checkpoint(value)
        adapter = adapter_for_checkpoint(checkpoint)
    except ValueError:
        checkpoint, adapter = None, None
    status, enabled = selection_status(value, modules, allow_custom, custom_vae)
    if adapter is None:
        return ("", *[gr.update() for _ in range(6)], status, enabled, "", gr.update())
    profiles = profiles_for(adapter, checkpoint.name)
    default = adapter.default_profile if adapter.default_profile in profiles else profiles[0]
    preset = adapter.profiles[default]
    # PNG import sets the signature with its own controls: don't overwrite them.
    changed = previous != checkpoint.name
    summary = ("**Fibo Turbo · 4 steps · Euler / Simple.** Other step counts are experimental; they are not a guaranteed quality improvement."
               if adapter.key == "fibo2" else f"**{default} · {preset['steps']} steps.** Resolution is independent.")
    if adapter.guidance > 1:
        summary = "**Fibo Dev · 50 steps · CFG 5 · Euler / Simple.** Preview uses 30 steps. Resolution is independent."
    samplers, schedules = sampling_choices()
    return (adapter.label, gr.update(choices=[*profiles, "Custom"], **({"value": default} if changed else {})),
            preset["steps"] if changed else gr.update(),
            gr.update(choices=samplers, interactive=True, **({"value": preset["sampler"]} if changed else {})),
            gr.update(choices=schedules, interactive=True, **({"value": preset["schedule"]} if changed else {})),
            gr.update(interactive=adapter.prefix_cache, **({"value": preset["prefix_cache"]} if changed else {})),
            summary if changed else gr.update(), status, enabled, checkpoint.name, adapter.guidance if changed else gr.update())


def check_model_setup(checkpoint_value, selected, allow_custom=False, custom_vae=None):
    """Refresh installed-file detection and validate, never change a selector."""
    main_entry.refresh_models()
    status, ready = selection_status(checkpoint_value, selected, allow_custom, custom_vae)
    if ready:
        gr.Info("Custom file selection is complete. Compatibility is checked when the model loads. No selections changed." if allow_custom else "Model setup is ready. No selections changed.")
    else:
        try:
            resolve_selection(checkpoint_value, selected, allow_custom, custom_vae)
        except ValueError as error:
            gr.Warning(str(error))
    return status, ready


def custom_vae_choices(enabled, selected, current):
    names = [basename(value) for value in selected or []]
    vaes = [name for name in names if 'vae' in name.lower()]
    value = current if current in names else vaes[0] if len(vaes) == 1 else None
    return gr.update(choices=names, value=value, visible=bool(enabled))


def sync_checkpoint_preset(value):
    """A manual checkpoint selection updates the layout, not the other model fields."""
    try:
        adapter = adapter_for_checkpoint(resolve_checkpoint(value))
    except ValueError:
        adapter = None
    if adapter is None:
        return gr.update()
    try:
        ensure_backend(adapter)
    except ValueError:
        return gr.update()
    shared.opts.set("forge_preset", adapter.key)
    shared.opts.save(shared.config_filename)
    return adapter.key


def apply_profile(profile, checkpoint_value):
    checkpoint = resolve_checkpoint(checkpoint_value)
    adapter = adapter_for_checkpoint(checkpoint)
    if adapter is None or profile not in [*profiles_for(adapter, checkpoint.name), "Custom"]:
        raise gr.Error("This quality preset does not match the checkpoint. Select the correct base or Turbo weights in the top model bar.")
    if profile == "Custom":
        return (*[gr.update() for _ in range(4)], "Custom sampling settings. Resolution is independent.", gr.update())
    preset = adapter.profiles[profile]
    return (preset["steps"], preset["sampler"], preset["schedule"], preset["prefix_cache"],
            "**Turbo: 4 steps recommended.** More steps are experimental." if adapter.key == "fibo2" and adapter.guidance == 1 else f"**{profile} · {preset['steps']} steps.** Resolution is unchanged.", adapter.guidance)


def import_recipe(file, current_checkpoint, modules):
    if file is None:
        raise gr.Error("Choose a generated PNG first.")
    try:
        recipe = read_recipe(file)
        if recipe.get("operation") == "canvas_crop":
            values = [gr.update() for _ in range(35)]
            values[11] = "This PNG is a canvas crop with no model settings. The crop is already in its pixels."
            return tuple(values)
        family = recipe.get("model_family", "Qwen Image 2.1")
        adapter = EDIT_MODELS[family]
        ensure_backend(adapter)
        samplers, schedules = sampling_choices()
        if recipe["sampler"] not in samplers:
            raise ValueError(f"Recipe sampler is not installed in Forge: {recipe['sampler']}.")
        if recipe["schedule"] not in schedules:
            raise ValueError(f"Recipe schedule is not installed in Forge: {recipe['schedule']}.")
        candidates = [checkpoint for checkpoint in sd_models.checkpoints_list.values() if adapter.accepts(checkpoint.name)]
        requested = recipe.get("model")
        if requested:
            matches = [checkpoint for checkpoint in candidates if checkpoint.name == requested]
            if not matches:
                matches = [checkpoint for checkpoint in candidates if basename(checkpoint.name) == basename(requested)]
            if len(matches) > 1:
                raise ValueError(f"Several installed checkpoints match {requested}; use unique filenames before importing this recipe.")
            checkpoint = next(iter(matches), None)
        else:
            checkpoint = resolve_checkpoint(current_checkpoint)
        if checkpoint is None or not adapter.accepts(checkpoint.name):
            raise ValueError(f"Recipe checkpoint is not installed: {requested}. Required: {required_components(adapter)}.")
        components = [recipe.get("encoder"), recipe.get("vae")]
        if not all(components):
            components = suggested_components(adapter, modules, main_entry.module_list)
        encoder, vae = validate_components(adapter, components, main_entry.module_list, recipe.get("custom_components", False), recipe.get("vae"))
    except (KeyError, TypeError, ValueError, OSError) as error:
        raise gr.Error(str(error)) from error
    note = "Edit recipe loaded. The displayed source is used for the next edit."
    if recipe.get("area_only"):
        note += " Canvas changes are already in this image; set new crop/outpaint edges if needed." if recipe.get("canvas") else " Repaint the selection for a new model edit."
    if recipe.get("postprocessing"):
        note += " Manual curves are already in the pixels; they are not applied again."
    from .masking import edit_modes
    modes = edit_modes(family, bool(recipe.get("area_only")))
    mode = recipe.get("edit_mode", recipe.get("masked_edit", {}).get("mode", modes[0]))
    if mode not in modes:
        mode = modes[0]
    choice = checkpoint.short_title if shared.opts.sd_checkpoint_dropdown_use_short else checkpoint.name
    # Deliberate import changes the visible main model selection too.
    dtype = recipe.get("storage_dtype", "Automatic")
    if dtype not in main_entry.forge_unet_storage_dtype_options:
        dtype = "Automatic"
    shared.opts.set("forge_preset", adapter.key)
    main_entry._load_presets(choice, [encoder, vae], dtype, adapter.key)
    resize = recipe.get("output_resize") or {}
    return (recipe["prompt"], recipe.get("negative_prompt", ""), recipe["resolution"], recipe["steps"], recipe["seed"],
            gr.update(choices=samplers, value=recipe["sampler"], interactive=True),
            gr.update(choices=schedules, value=recipe["schedule"], interactive=True), choice, [encoder, vae], adapter.key, dtype,
            note, gr.update(choices=[*profiles_for(adapter, checkpoint.name), "Custom"], value="Custom"), "Imported edit recipe.", family,
            gr.update(value=bool(recipe.get("prefix_cache", adapter.prefix_cache)) and adapter.prefix_cache, interactive=adapter.prefix_cache),
            recipe.get("result_description", ""), bool(recipe.get("keep_original_metadata", True)), checkpoint.name, recipe["cfg"], False, gr.update(choices=modes, value=mode),
            recipe.get("fibo_shift_mode", "Manual") if adapter.key == "fibo2" else gr.update(),
            gr.update(value=recipe.get("fibo_shift", 1.15), interactive=recipe.get("fibo_shift_mode", "Manual") == "Manual") if adapter.key == "fibo2" else gr.update(),
            recipe.get("fibo_rope", False) if adapter.key == "fibo2" else gr.update(),
            bool(resize), resize.get("mode", "Resize to"), resize.get("width", gr.update()), resize.get("height", gr.update()), resize.get("scale", 1),
            recipe.get("qwen_shift_mode", "Manual") if adapter.key == "qwen21" else gr.update(),
            gr.update(value=recipe.get("qwen_shift", .69), interactive=recipe.get("qwen_shift_mode", "Manual") == "Manual") if adapter.key == "qwen21" else gr.update(),
            recipe.get("qwen_rope", False) if adapter.key == "qwen21" else gr.update(),
            bool(recipe.get("custom_components", False)),
            gr.update(choices=[encoder, vae], value=vae, visible=bool(recipe.get("custom_components", False))))


def import_handoff(image, checkpoint, modules):
    if image is None or not any(key in image.info for key in ("image_edit", "qwen_edit")):
        return tuple(gr.update() for _ in range(35))
    # read_recipe accepts PIL images as well as uploaded paths; no stored paths opened.
    return import_recipe(image, checkpoint, modules)


def after_component(component, **kwargs):
    global bound
    if bound or Context.root_block is None:
        return
    identifiers = {"setting_sd_model_checkpoint": "checkpoint", "setting_sd_modules": "modules",
                   "forge_ui_preset": "preset", "forge_ui_dtype": "dtype"}
    key = identifiers.get(kwargs.get("elem_id", getattr(component, "elem_id", None)))
    if workspace is None or key is None:
        return
    bar[key] = component
    if len(bar) != 4:
        return
    bound = True
    bind(workspace, bar)


def bind(ui, controls):
    from modules.call_queue import wrap_gradio_gpu_call
    from .ui import run_canvas_edit
    from . import model_switch
    model_switch.install(main_entry, shared, sd_models, gr)
    checkpoint, modules, preset, dtype = [controls[key] for key in ("checkpoint", "modules", "preset", "dtype")]
    outputs = [ui.family, ui.profile, ui.steps, ui.sampler, ui.schedule, ui.prefix_cache, ui.profile_summary, ui.backend_label, ui.model_ready, ui.selection_signature, ui.guidance]
    custom = [ui.allow_custom_components, ui.custom_vae]
    checkpoint.change(observe_checkpoint, [checkpoint, modules, ui.selection_signature, *custom], outputs, show_progress="hidden", api_name="image_edit_selection")
    checkpoint.input(sync_checkpoint_preset, [checkpoint], [preset], queue=False, show_progress="hidden", api_name=False)
    for component in (modules, *custom):
        component.change(selection_status, [checkpoint, modules, *custom], [ui.backend_label, ui.model_ready], show_progress="hidden", api_name="image_edit_validate" if component is modules else False)
    for component in (modules, ui.allow_custom_components):
        component.change(custom_vae_choices, [ui.allow_custom_components, modules, ui.custom_vae], [ui.custom_vae], show_progress="hidden", api_name=False)
    Context.root_block.load(observe_checkpoint, [checkpoint, modules, ui.selection_signature, *custom], outputs, show_progress="hidden")
    ui.correct_components.click(check_model_setup, [checkpoint, modules, *custom], [ui.backend_label, ui.model_ready], show_progress="hidden", api_name="image_edit_check_model")
    ui.profile.input(apply_profile, [ui.profile, checkpoint], [ui.steps, ui.sampler, ui.schedule, ui.prefix_cache, ui.profile_summary, ui.guidance], show_progress="hidden", api_name="image_edit_preset")
    recipe_outputs = [ui.instruction, ui.negative, ui.resolution, ui.steps, ui.seed, ui.sampler, ui.schedule, checkpoint, modules, preset, dtype,
                      ui.import_status, ui.profile, ui.profile_summary, ui.family, ui.prefix_cache, ui.result_description, ui.keep_metadata, ui.selection_signature, ui.guidance, ui.preserve_tone, ui.area_mode, ui.fibo_shift_mode, ui.fibo_shift, ui.fibo_rope, ui.output_size_enabled, ui.output_size_mode, ui.output_width, ui.output_height, ui.output_scale, ui.qwen_shift_mode, ui.qwen_shift, ui.qwen_rope, *custom]
    ui.import_button.click(import_recipe, [ui.recipe_file, checkpoint, modules], recipe_outputs, show_progress="hidden", api_name="image_edit_import")
    ui.handoff.change(import_handoff, [ui.handoff, checkpoint, modules], recipe_outputs, show_progress="hidden", api_name="image_edit_handoff")
    ui.generate.click(wrap_gradio_gpu_call(run_canvas_edit, extra_outputs=[gr.update() for _ in range(6)]),
        [ui.task_id, ui.source, ui.reference2, ui.reference3, ui.instruction, ui.negative, ui.resolution, ui.steps, ui.seed,
         ui.sampler, ui.schedule, checkpoint, modules, dtype, ui.prefix_cache, ui.area_only, ui.mask_editor.foreground,
         ui.feather, ui.area_mode, ui.result_description, ui.keep_metadata, ui.guidance, ui.preserve_tone,
         ui.canvas_enabled, ui.canvas_left, ui.canvas_right, ui.canvas_top, ui.canvas_bottom, ui.seam_blend, ui.canvas_shrink, ui.batch_count,
         ui.reference2_curves, ui.reference3_curves, ui.fibo_shift_mode, ui.fibo_shift, ui.fibo_rope,
         ui.output_size_enabled, ui.output_size_mode, ui.output_width, ui.output_height, ui.output_scale, ui.qwen_shift_mode, ui.qwen_shift, ui.qwen_rope, *custom],
        [ui.result, ui.download, ui.last_seed, ui.batch_gallery, ui.batch_items, ui.batch_source, ui.status], js="qwenEditSubmit", api_name="image_edit_generate")
