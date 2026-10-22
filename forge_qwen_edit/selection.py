"""Model-bar validation without loading weights or depending on local paths."""
from pathlib import Path

from .adapters import EDIT_MODELS


def basename(value):
    return str(value).replace("\\", "/").rsplit("/", 1)[-1]


def adapter_for_checkpoint(checkpoint):
    name = getattr(checkpoint, "name", checkpoint) or ""
    return next((adapter for adapter in EDIT_MODELS.values() if adapter.accepts(str(name))), None)


def required_components(adapter):
    if adapter.key == "fibo2":
        return f"{adapter.label} checkpoint + Qwen3-VL 4B encoder + FLUX.2 VAE"
    return "Qwen Image 2.1 base/Turbo checkpoint + Qwen3-VL 8B encoder + Qwen Image 2.1 VAE"


def validate_components(adapter, selected, available, allow_custom=False, custom_vae=None):
    """Validate known filenames, or an explicitly assigned custom encoder/VAE pair."""
    names = [basename(value) for value in selected or []]
    missing_files = [name for name in names if name not in available or not Path(available[name]).is_file()]
    if missing_files:
        raise ValueError(f"Selected file not found: {', '.join(missing_files)}. Install it and refresh the top model list.")
    if allow_custom:
        if len(names) != 2 or len(set(names)) != 2:
            raise ValueError("Custom setup needs two selected files: one text encoder and one VAE in the top VAE / Text Encoder field.")
        vae = basename(custom_vae) if custom_vae else None
        if vae not in names:
            raise ValueError("In Extras, choose which selected file is the VAE. The other file is used as the text encoder.")
        return next(name for name in names if name != vae), vae
    encoders = [name for name in names if adapter.accepts(name, "encoder")]
    vaes = [name for name in names if adapter.accepts(name, "vae")]
    if len(names) != 2 or len(encoders) != 1 or len(vaes) != 1 or len(set(names)) != 2:
        problems = []
        if not encoders:
            problems.append(f"Missing text encoder: {adapter.defaults[1]}.")
        if not vaes:
            problems.append(f"Missing VAE: {adapter.defaults[2]}.")
        if len(encoders) > 1 or len(vaes) > 1 or len(set(names)) != len(names):
            problems.append("Select just one compatible text encoder and one VAE.")
        extras = [name for name in names if name not in encoders + vaes]
        if extras:
            problems.append(f"Unrecognized for this model: {', '.join(extras)}. For custom files, enable Allow custom encoder / VAE filenames in Extras.")
        raise ValueError(' '.join(problems) + " Set these in the top VAE / Text Encoder field.")
    return encoders[0], vaes[0]


def suggested_components(adapter, selected, available):
    """Return a complete installed pair or fail; never apply half a selection."""
    names = [basename(value) for value in selected or []]
    chosen = []
    for kind, preferred in zip(("encoder", "vae"), adapter.defaults[1:]):
        candidates = sorted(name for name, path in available.items() if adapter.accepts(name, kind) and Path(path).is_file())
        current = [name for name in names if name in candidates]
        choice = current[0] if len(current) == 1 else preferred if preferred in candidates else next(iter(candidates), None)
        if choice is None:
            raise ValueError(f"Missing {kind}: {preferred}. Install it and refresh the top model list. Required: {required_components(adapter)}.")
        chosen.append(choice)
    return chosen


def profiles_for(adapter, checkpoint):
    if adapter.key == "fibo2":
        return list(adapter.profiles)
    turbo = "turbo" in str(checkpoint).lower()
    return [name for name in adapter.profiles if (name == "Turbo (8 steps)") == turbo]
