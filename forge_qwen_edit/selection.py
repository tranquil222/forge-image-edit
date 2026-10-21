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


def validate_components(adapter, selected, available):
    """Require exactly one compatible encoder and VAE; reject stale extras."""
    names = [basename(value) for value in selected or []]
    requirement = required_components(adapter)
    if any(name not in available or not Path(available[name]).is_file() for name in names):
        raise ValueError(f"A selected component is missing. Refresh the model list. Required: {requirement}.")
    encoders = [name for name in names if adapter.accepts(name, "encoder")]
    vaes = [name for name in names if adapter.accepts(name, "vae")]
    if len(names) != 2 or len(encoders) != 1 or len(vaes) != 1 or len(set(names)) != 2:
        raise ValueError(f"Incorrect VAE / Text Encoder selection. Required: {requirement}. Select only its encoder and VAE.")
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
