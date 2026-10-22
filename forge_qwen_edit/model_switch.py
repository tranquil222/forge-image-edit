"""Keep Forge's saved edit-model presets in their own families.

Installed as UI callbacks, without rewriting Forge files. Checkpoint input only
syncs the layout preset; it never changes the user's VAE/encoder selection.
"""
from functools import wraps
from pathlib import Path

from .adapters import EDIT_MODELS
from .selection import adapter_for_checkpoint, basename, suggested_components


EDIT_PRESETS = {adapter.key for adapter in EDIT_MODELS.values()}


def find_checkpoint(value, checkpoints):
    matches = [item for item in checkpoints if value and value in
               (item.name, item.filename, item.short_title, *item.ids)]
    return matches[0] if len(matches) == 1 else None


def choose_checkpoint(preset, current, saved, checkpoints):
    """Prefer the selected model, then a valid saved model, then an installed default."""
    def matches(item):
        adapter = adapter_for_checkpoint(item) if item else None
        return adapter is not None and adapter.key == preset

    for value in (current, saved):
        item = find_checkpoint(value, checkpoints)
        if matches(item):
            return item
    candidates = [item for item in checkpoints if matches(item)]
    for adapter in EDIT_MODELS.values():
        if adapter.key == preset:
            preferred = [item for item in candidates if item.name.replace('\\', '/').rsplit('/', 1)[-1] == adapter.defaults[0]]
            if len(preferred) == 1:
                return preferred[0]
    return candidates[0] if len(candidates) == 1 else None


def install(main_entry, shared, sd_models, gr):
    """Wrap only the two relevant callbacks; repeated Reload UI never stacks wrappers."""
    checkpoint_original = getattr(main_entry.checkpoint_change, '_image_edit_original', main_entry.checkpoint_change)
    preset_original = getattr(main_entry.on_preset_change, '_image_edit_original', main_entry.on_preset_change)

    @wraps(checkpoint_original)
    def checkpoint_change(ckpt_name, preset, save=True, refresh=True):
        item = find_checkpoint(ckpt_name, sd_models.checkpoints_list.values())
        adapter = adapter_for_checkpoint(item) if item else None
        # A checkpoint selected while the other layout is showing used to be
        # saved into that layout's slot. Repair even when the model is unchanged.
        if adapter:
            preset = adapter.key
            shared.opts.set(f'forge_checkpoint_{preset}', ckpt_name)
        elif preset in EDIT_PRESETS:
            preset = None  # Don't poison an edit preset with an unrelated model.
        changed = checkpoint_original(ckpt_name, preset, save=save, refresh=refresh)
        if adapter and save and not changed:
            shared.opts.save(shared.config_filename)
        return changed

    @wraps(preset_original)
    def on_preset_change(preset, **kwargs):
        if preset not in EDIT_PRESETS or kwargs.get('layout_only'):
            return preset_original(preset, **kwargs)
        current = shared.opts.sd_model_checkpoint
        item = choose_checkpoint(preset, current, getattr(shared.opts, f'forge_checkpoint_{preset}', None),
                                 list(sd_models.checkpoints_list.values()))
        if item is None:
            # Keep actual fields intact rather than combine another family's
            # checkpoint with this preset's components.
            raise gr.Error(f'Select an installed {preset} checkpoint in the top Checkpoint field first.')
        choice = item.short_title if shared.opts.sd_checkpoint_dropdown_use_short else item.name
        shared.opts.set(f'forge_checkpoint_{preset}', choice)
        adapter = adapter_for_checkpoint(item)
        same_checkpoint = find_checkpoint(current, sd_models.checkpoints_list.values()) == item
        selected = (shared.opts.forge_additional_modules if same_checkpoint
                    else getattr(shared.opts, f'forge_additional_modules_{preset}', []))
        selected = [basename(name) for name in selected]
        custom_pair = (len(set(selected)) == 2 and len(selected) == 2
                       and all(name in main_entry.module_list and Path(main_entry.module_list[name]).is_file() for name in selected)
                       and any(not any(a.accepts(name, kind) for a in EDIT_MODELS.values() for kind in ('encoder', 'vae')) for name in selected))
        try:
            modules = selected if same_checkpoint or custom_pair else suggested_components(adapter, selected, main_entry.module_list)
        except ValueError:
            # Missing files remain a precise validation error in Image Edit;
            # don't silently apply a partial pair or download anything.
            modules = list(shared.opts.forge_additional_modules)
        if 'autofill_components' in kwargs:
            kwargs['autofill_components'] = False  # Complete pair already resolved above.
        result = preset_original(preset, **kwargs)
        result[0] = gr.update(value=choice)
        result[1] = gr.update(value=modules)
        # This callback also runs on initial page load, where Forge does not
        # chain _load_presets. Persist a repaired selection so the backend and
        # visible bar agree there too. A later manual-input success is harmless.
        main_entry._load_presets(choice, modules, result[2].get('value', 'Automatic'), preset)
        return result

    checkpoint_change._image_edit_original = checkpoint_original
    on_preset_change._image_edit_original = preset_original
    main_entry.checkpoint_change = checkpoint_change
    main_entry.on_preset_change = on_preset_change
