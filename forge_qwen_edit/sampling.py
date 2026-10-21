"""Fibo sampling controls, independent of Forge imports."""

import math
from contextlib import contextmanager

FIBO_SHIFT_MODES = ("Manual", "Image-size adjusted")
DEFAULT_FIBO_SHIFT = 1.15
FIBO_ROPE_X = 0.85
FIBO_ROPE_Y = 0.80


def validate_fibo_sampling(mode, shift, rope=False):
    if mode not in FIBO_SHIFT_MODES:
        raise ValueError("Choose Manual or Image-size adjusted Fibo Shift.")
    if isinstance(shift, bool):
        raise ValueError("Fibo Shift must be between 0.1 and 5.")
    try:
        shift = float(shift)
    except (TypeError, ValueError):
        raise ValueError("Fibo Shift must be between 0.1 and 5.") from None
    if not math.isfinite(shift) or not 0.1 <= shift <= 5:
        raise ValueError("Fibo Shift must be between 0.1 and 5.")
    if not isinstance(rope, bool):
        raise ValueError("RoPE adjustment must be on or off.")
    return mode, shift, rope


def resolve_fibo_shift(mode, shift, width, height):
    mode, shift, _ = validate_fibo_sampling(mode, shift)
    if mode == "Manual":
        return shift
    if width < 16 or height < 16 or width % 16 or height % 16:
        raise ValueError("Fibo working dimensions must be positive multiples of 16.")
    # Diffusers FlowMatch dynamic shifting: 256 tokens -> .5; 4096 -> 1.15.
    tokens = (width // 16) * (height // 16)
    return 0.5 + (tokens - 256) * (1.15 - 0.5) / (4096 - 256)


@contextmanager
def fibo_rope_context(sd_model, enabled=False):
    """Scale this queued job's coordinates; remove the hook even on cancellation.

    Matches ComfyUI pos_ids_x with ScaleROPE X=.85, Y=.80, zero shifts.
    Gist tokens have zero spatial coordinates; their plane IDs stay unchanged.
    No model weights, core files, output dimensions or global classes are changed.
    """
    if not enabled:
        yield
        return
    model = sd_model.forge_objects.unet.model.diffusion_model
    embedder = getattr(model, "rope_embedder", None)
    if embedder is None or not hasattr(embedder, "register_forward_pre_hook"):
        raise ValueError("This Fibo backend does not expose RoPE coordinates. Update the backend before enabling RoPE adjustment.")

    def scale_positions(module, inputs):
        ids = inputs[0].clone()
        ids[..., 1] *= FIBO_ROPE_Y
        ids[..., 2] *= FIBO_ROPE_X
        return (ids, *inputs[1:])

    handle = embedder.register_forward_pre_hook(scale_positions)
    try:
        yield
    finally:
        handle.remove()
