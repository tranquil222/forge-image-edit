"""Job-scoped native Forge processing; no core file or class monkey patches."""

import json
import secrets
from contextlib import closing, contextmanager
from pathlib import Path

import numpy as np
import torch

from backend import memory_management
from backend.args import dynamic_args
from backend.text_processing.qwen21_engine import QwenImage21TextProcessingEngine, T2I_TEMPLATE, VISION_BLOCK
from modules import images, processing, prompt_parser, sd_models, sd_samplers, sd_schedulers, shared
from modules_forge import main_entry

from . import __version__
from .adapters import get_adapter
from .workflow import QUALITY_PRESETS, fibo_result_prompt, image_digest, parse_seed, prepare_reference
from .masking import canonical_image, composite_patch, context_box, extract_mask, fibo_masked_instruction, fibo_masked_reference, location_guide, scoped_instruction
from .metadata import build_metadata, preserve_binary_metadata
from .selection import validate_components
from .tone import match_source_tone
from .adjustments import MASK_KEY, encode_selection, remember_selection


class EditCancelled(Exception):
    """Expected cancellation, not a failed generation."""


def check_cancelled():
    if shared.state.interrupted or shared.state.skipped:
        raise EditCancelled()


def release_edit_encoder(patcher):
    """GGUF dequantization needs workspace, not an idle resident text encoder."""
    if patcher.load_device.type == "cpu":
        return
    keep = [loaded for loaded in memory_management.current_loaded_models if loaded.model is not patcher]
    # Use Forge's unload bookkeeping; never move parameters behind its back.
    memory_management.free_memory(1e30, patcher.load_device, keep_loaded=keep)


class EditTextEncoder(QwenImage21TextProcessingEngine):
    def tokenize(self, texts, image_count=0):
        refs = " ".join(f"<image{i + 1}>{VISION_BLOCK}" for i in range(image_count))
        return self.tokenizer([T2I_TEMPLATE.format(refs + text.strip()) for text in texts])["input_ids"]


class EditProcessing(processing.StableDiffusionProcessingTxt2Img):
    """Empty target latent with image-conditioned text + reference VAE latents."""

    def init(self, all_prompts, all_seeds, all_subseeds):
        check_cancelled()
        adapter = get_adapter(self.edit_family)
        if not getattr(dynamic_args, adapter.flag, False):
            raise ValueError(f"Selected weights are not a {adapter.label} model.")
        super().init(all_prompts, all_seeds, all_subseeds)
        self.sd_model.clear_references()
        self.edit_previous_lora = (self.sd_model.forge_objects_after_applying_lora, self.sd_model.current_lora_hash)
        self.sd_model.forge_objects = self.sd_model.forge_objects_original.shallow_copy()
        self.sd_model.forge_objects_after_applying_lora = self.sd_model.forge_objects_original.shallow_copy()
        self.sd_model.current_lora_hash = "[]"
        dynamic_args.ref_latents = []
        dynamic_args.image_slots = []
        if adapter.prefix_cache:
            dynamic_args.qwen21_auto_shift = False
            dynamic_args.qwen21_prefix_cache = self.edit_prefix_cache
            self.sd_model.forge_objects.unet.model.diffusion_model.reset_prefix_cache(self.edit_prefix_cache)
        self.edit_conditioning = None
        self.edit_unconditional = None

    @torch.inference_mode()
    def setup_conds(self):
        check_cancelled()
        self.firstpass_steps = self.steps
        self.step_multiplier = 1
        self.uc = None
        if self.edit_conditioning is None:
            vision, latents = [], []
            vae = self.sd_model.forge_objects.vae
            adapter = get_adapter(self.edit_family)
            for image in self.edit_references:
                check_cancelled()
                tensor = torch.from_numpy(np.array(image).astype(np.float32) / 255.0).unsqueeze(0)
                rgb = tensor[..., :3]
                if tensor.shape[-1] == 4:
                    rgb = rgb * tensor[..., 3:] + (1.0 - tensor[..., 3:])
                latent = vae.first_stage_model.process_in(vae.encode(rgb if adapter.key == "fibo2" else tensor))
                check_cancelled()
                latents.append(latent)
                vision.append(rgb)
            check_cancelled()
            memory_management.load_model_gpu(self.sd_model.forge_objects.clip.patcher)
            check_cancelled()
            if adapter.key == "fibo2":
                encoder = self.sd_model.text_processing_engine_fibo
            else:
                original = self.sd_model.text_processing_engine_qwen
                encoder = EditTextEncoder(original.text_encoder, original.tokenizer)
            self.edit_conditioning = encoder([self.prompt], images=vision)[0]
            check_cancelled()
            if self.cfg_scale > 1:
                # Dev's negative branch is text-only; both branches share VAE refs.
                self.edit_unconditional = encoder([self.negative_prompt], images=[])[0]
            check_cancelled()
            dynamic_args.ref_latents = latents
            if adapter.key == "qwen21":
                dynamic_args.image_slots = list(encoder.image_slots)
                self.extra_generation_params["Qwen reference slots"] = str(encoder.image_slots)
            if self.edit_release_encoder:
                release_edit_encoder(self.sd_model.forge_objects.clip.patcher)
        schedule = [prompt_parser.ScheduledPromptConditioning(self.steps, self.edit_conditioning)]
        self.c = prompt_parser.MulticondLearnedConditioning(
            shape=(1,), batch=[[prompt_parser.ComposableScheduledPromptConditioning(schedule)]]
        )
        if self.edit_unconditional is not None:
            self.uc = [[prompt_parser.ScheduledPromptConditioning(self.steps, self.edit_unconditional)]]

    def sample(self, *args, **kwargs):
        check_cancelled()
        samples = super().sample(*args, **kwargs)
        # Forge can return None when interrupted before its first denoising step.
        # Stop before the core tries to iterate/decode a missing or partial latent.
        check_cancelled()
        if samples is None:
            raise RuntimeError("The sampler returned no image latents.")
        return samples

    def parse_extra_network_prompts(self):
        # Instructions are literal: AND, brackets and colons must not split edits.
        self.extra_network_data = {}

    def close(self):
        self.edit_conditioning = None
        self.edit_unconditional = None
        dynamic_args.ref_latents = []
        dynamic_args.image_slots = []
        if self.sd_model is not None and (dynamic_args.qwen21 or dynamic_args.fibo2):
            self.sd_model.clear_references()
        if hasattr(self, "edit_previous_lora"):
            objects, lora_hash = self.edit_previous_lora
            self.sd_model.forge_objects_after_applying_lora = objects
            self.sd_model.forge_objects = objects.shallow_copy()
            self.sd_model.current_lora_hash = lora_hash
        super().close()


@contextmanager
def isolated_options(checkpoint, modules, storage_dtype="Automatic"):
    """Restore in-memory selection/options; never save the user's config file."""
    overrides = {
        "sd_model_checkpoint": checkpoint.name, "forge_additional_modules": modules,
        "forge_unet_storage_dtype": storage_dtype, "sd_vae_decode_method": "Full",
        "sd_noise_schedule": "Default", "always_discard_next_to_last_sigma": False,
        "token_merging_ratio": 0.0, "token_merging_ratio_hr": 0.0,
        "sgm_noise_multiplier": False, "randn_source": "CPU",
    }
    missing = object()
    original = {key: shared.opts.data.get(key, missing) for key in overrides}
    old_hash = shared.opts.data.get("sd_checkpoint_hash", missing)
    old_parameters = sd_models.model_data.forge_loading_parameters.copy()
    old_flags = {key: getattr(dynamic_args, key) for key in ("qwen21_auto_shift", "qwen21_prefix_cache", "online_lora")}
    try:
        shared.opts.data.update(overrides)
        dtype, online_lora = main_entry.forge_unet_storage_dtype_options.get(storage_dtype, (None, False))
        dynamic_args.online_lora = online_lora or checkpoint.filename.lower().endswith(".gguf")
        sd_models.model_data.forge_loading_parameters = dict(
            checkpoint_info=checkpoint, additional_modules=modules, unet_storage_dtype=dtype
        )
        yield
    finally:
        selection_keys = ("sd_model_checkpoint", "forge_additional_modules", "forge_unet_storage_dtype")
        selection_changed = any(shared.opts.data.get(key) != overrides[key] for key in selection_keys)
        for key, value in {**original, "sd_checkpoint_hash": old_hash}.items():
            if selection_changed and key in (*selection_keys, "sd_checkpoint_hash"):
                continue
            if value is missing:
                shared.opts.data.pop(key, None)
            else:
                shared.opts.data[key] = value
        if selection_changed:
            # A user can change the main bar while sampling. Preserve that next
            # selection rather than restoring this job's older UI snapshot.
            main_entry.refresh_model_loading_parameters()
        else:
            sd_models.model_data.forge_loading_parameters = old_parameters
        for key, value in old_flags.items():
            if selection_changed and key == "online_lora":
                continue
            setattr(dynamic_args, key, value)


def generate(source, reference2, reference3, instruction, negative, resolution, steps, seed, sampler, schedule, model_name, encoder_name, vae_name, prefix_cache, area_only=False, editor=None, feather=8, area_mode="Replace / remove", model_family="Qwen Image 2.1", result_description="", keep_original_metadata=True, storage_dtype="Automatic", guidance=None, preserve_tone=False):
    adapter = get_adapter(model_family)
    guidance = adapter.guidance if guidance is None else float(guidance)
    if not 1 <= guidance <= 15 or (adapter.guidance == 1 and guidance != 1):
        raise ValueError("CFG must be 1 for Turbo/Qwen, or between 1 and 15 for Fibo Dev.")
    if source is None:
        raise ValueError("Add a source image first.")
    if not instruction or not instruction.strip():
        raise ValueError("Enter an edit instruction.")
    if sampler not in adapter.samplers or sd_samplers.find_sampler_config(sampler) is None:
        raise ValueError("Required sampler is unavailable in this Forge build.")
    if schedule not in sd_schedulers.schedulers_map:
        raise ValueError("The selected schedule is unavailable. Reload Forge after installing the extension.")
    if schedule not in adapter.schedules:
        raise ValueError(f"That schedule is not compatible with {adapter.label}. Select its speed / quality preset.")
    if not 1 <= int(steps) <= 150:
        raise ValueError("Steps must be between 1 and 150.")
    checkpoint = next((c for c in sd_models.checkpoints_list.values() if c.name == model_name), None)
    if checkpoint is None:
        raise ValueError(f"Choose an installed {adapter.label} checkpoint in Forge's top model bar.")
    if not adapter.accepts(checkpoint.name):
        raise ValueError(f"The selected checkpoint is not supported by {adapter.label}.")
    validate_components(adapter, [encoder_name, vae_name], main_entry.module_list)
    prefix_cache = bool(prefix_cache) and adapter.prefix_cache
    if schedule == "Qwen 2.1 Turbo (official)" and "turbo" not in checkpoint.name.lower():
        raise ValueError("The Official Turbo schedule requires Turbo weights. Choose your Turbo checkpoint.")
    if schedule == "Qwen 2.1 Turbo (official)" and (int(steps) != 8 or sampler != "Euler"):
        raise ValueError("Official Turbo uses exactly 8 steps and Euler. Select the Turbo preset to set these together.")
    modules = []
    for name in (encoder_name, vae_name):
        path = main_entry.module_list.get(name)
        if path is None or not Path(path).is_file():
            raise ValueError(f"Missing component: {name}. Install it in models/VAE or models/text_encoder, then Refresh models.")
        modules.append(str(path))
    original = canonical_image(source)
    mask, crop = None, None
    effective_instruction = instruction
    input_references = [original, *[im for im in (reference2, reference3) if im is not None]]
    if area_only:
        if adapter.key != "fibo2" and area_mode not in ("Replace / remove", "Refine / expression"):
            raise ValueError("Choose a painted-area mode.")
        if not 0 <= float(feather) <= 64:
            raise ValueError("Edge blending must be between 0 and 64 pixels.")
        mask = extract_mask(original, editor)
        crop = context_box(mask)
        replace = adapter.key == "fibo2" or area_mode == "Replace / remove"
        if adapter.key == "fibo2":
            # Fibo's trained mask input is neutral grey, not Qwen's green guide.
            # Native masked editing uses exactly one source image.
            input_references = [fibo_masked_reference(original, mask).crop(crop)]
            guide_reference = 1
            area_mode = "Fibo masked edit"
            effective_instruction = fibo_masked_instruction(instruction)
        elif replace:
            # Do not send the clean crop: it would reveal the covered content.
            input_references[0] = location_guide(original, mask, opaque=True).crop(crop)
            guide_reference = 1
        else:
            input_references[0] = original.crop(crop)
            input_references.append(location_guide(original, mask).crop(crop))
            guide_reference = len(input_references)
        if adapter.key != "fibo2":
            effective_instruction = scoped_instruction(instruction, guide_reference, replace=replace)
    if adapter.key == "fibo2":
        effective_instruction = fibo_result_prompt(effective_instruction, result_description)
    else:
        result_description = ""
    references = [prepare_reference(im, resolution) for im in input_references]
    seed = parse_seed(seed)
    if seed == -1:
        seed = secrets.randbits(63)
    recipe = {
        "version": 1, "extension_version": __version__, "model_family": model_family, "prompt": instruction,
        "negative_prompt": negative, "resolution": int(resolution), "steps": int(steps),
        "cfg": guidance, "seed": str(seed), "sampler": sampler, "schedule": schedule,
        "model": checkpoint.name, "encoder": encoder_name, "vae": vae_name,
        "prefix_cache": bool(prefix_cache),
        "result_description": result_description,
        "keep_original_metadata": bool(keep_original_metadata), "storage_dtype": storage_dtype,
        "preserve_tone": bool(preserve_tone),
        "reference_sha256": [image_digest(im) for im in references],
        "reference_sizes": [list(im.size) for im in references],
        "area_only": bool(area_only), "source_sha256": image_digest(original),
        "source_size": list(original.size),
    }
    if area_only:
        recipe["masked_edit"] = {"crop": list(crop), "mask_sha256": image_digest(mask), "feather": float(feather), "guide_reference": guide_reference, "mode": area_mode, "clean_reference_sent": not replace}
        if adapter.key == "fibo2":
            recipe["masked_edit"].update(mask_fill=[128, 128, 128], mask_threshold=128)
    if effective_instruction != instruction:
        recipe["effective_prompt"] = effective_instruction
    recipe["quality_preset"] = next((name for name, values in adapter.profiles.items() if all(recipe[key] == value for key, value in values.items())), "Custom")
    if guidance != adapter.guidance:
        recipe["quality_preset"] = "Custom"
    output_dir = Path(shared.opts.outdir_samples or shared.opts.outdir_img2img_samples)
    with isolated_options(checkpoint, modules, storage_dtype):
        p = EditProcessing(
            prompt=effective_instruction, negative_prompt=negative, steps=int(steps), seed=seed,
            sampler_name=sampler, scheduler=schedule, cfg_scale=guidance, distilled_cfg_scale=adapter.shift,
            width=references[0].width, height=references[0].height, batch_size=1, n_iter=1,
            outpath_samples=str(output_dir), outpath_grids=str(output_dir),
            do_not_save_samples=True, do_not_save_grid=True, restore_faces=False, tiling=False,
            disable_extra_networks=True, s_churn=0.0, s_noise=1.0,
            extra_generation_params={
                "Image Edit": __version__, "Edit model": model_family, "Reference resolution": int(resolution),
                "Edit references": len(references), "Prefix cache": bool(prefix_cache),
                "Edit mode": "Reference / empty latent", "Edit quality preset": recipe["quality_preset"],
                "Painted area": bool(area_only),
                "Preserve source tone": bool(preserve_tone),
            },
        )
        p.edit_references = references
        p.edit_family = model_family
        p.edit_prefix_cache = bool(prefix_cache)
        p.edit_release_encoder = checkpoint.name.lower().endswith(".gguf")
        try:
            with closing(p):
                result = processing.process_images(p)
        except EditCancelled:
            return None, None, "", "Edit cancelled. No completed image was saved."
        if shared.state.interrupted or shared.state.skipped or not result.images:
            return None, None, "", "Edit cancelled. No completed image was saved."
        output = result.images[0]
        if preserve_tone:
            tone_source = original.crop(crop) if area_only else original
            tone_exclude = mask.crop(crop) if area_only else None
            output, recipe["tone_match"] = match_source_tone(tone_source, output, tone_exclude)
        if area_only:
            output = composite_patch(original, output, mask, crop, feather)
        recipe["output_size"] = list(output.size)
        metadata, binary = build_metadata(original, recipe, result.infotexts[0], keep_original_metadata)
        selection = encode_selection(mask, feather) if area_only else None
        metadata.pop(MASK_KEY, None)
        if selection is not None and len(selection["png"]) < 500_000:
            metadata[MASK_KEY] = json.dumps(selection)
        # A composite inherits source.info; do not let Pillow or save hooks leak
        # those fields when preservation (or all metadata) is disabled.
        output.info.clear()
        # Native naming, configured img2img path, dated subfolders and save hooks.
        path, _ = images.save_image(output, str(output_dir), "", seed=seed, prompt=instruction,
                                    extension="png", info=metadata["parameters"], p=p, existing_info=metadata)
        if shared.opts.enable_pnginfo:
            preserve_binary_metadata(path, binary)
            output.info.update(metadata)
            output.info.update(binary)
        path = Path(path)
        remember_selection(path, selection)
        note = " · outside painted area preserved" if area_only else ""
        return output, str(path), str(seed), f"Saved {path.name} · {output.width} × {output.height} · seed {seed}{note}"
