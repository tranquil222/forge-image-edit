"""Model-specific sampling controls, independent of Forge imports."""

import math
from contextlib import contextmanager

FIBO_SHIFT_MODES = ("Manual", "Image-size adjusted")
DEFAULT_FIBO_SHIFT = 1.15
DEFAULT_QWEN_SHIFT = 0.69
FIBO_ROPE_X = 0.85
FIBO_ROPE_Y = 0.80
QWEN_ROPE_X = 0.85
QWEN_ROPE_Y = 0.80


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


def validate_qwen_sampling(mode, shift, rope=False):
    try:
        return validate_fibo_sampling(mode, shift, rope)
    except ValueError as error:
        raise ValueError(str(error).replace("Fibo", "Qwen")) from None


def resolve_qwen_shift(mode, shift, width, height):
    mode, shift, _ = validate_qwen_sampling(mode, shift)
    if mode == "Manual":
        return shift
    if width <= 0 or height <= 0:
        raise ValueError("Qwen working dimensions must be positive.")
    # Match Forge QwenImage21.calculate_shift (16px VAE grid, capped at .9).
    tokens = math.ceil(width / 16) * math.ceil(height / 16)
    return max(.5, min(.9, .5 + (tokens - 256) * (.9 - .5) / (8192 - 256)))


def shift_qwen_sigmas(sigmas, shift):
    """Adjust fixed quality/Turbo grids relative to the unchanged .69 default.

    Simple uses the model predictor's shift directly. Fixed grids bypass that
    predictor, so apply a log-SNR delta here, not a second absolute shift.
    """
    if shift == DEFAULT_QWEN_SHIFT:
        return sigmas
    factor = math.exp(shift - DEFAULT_QWEN_SHIFT)
    return factor * sigmas / (1 + (factor - 1) * sigmas)


def qwen_schedule_override(function, shift):
    def schedule(steps):
        values = function(n=steps, sigma_min=0.0, sigma_max=1.0, device="cpu")
        return shift_qwen_sigmas(values, shift)
    return schedule


def qwen_image_spans(text_length, image_slots, reference_sizes, target_size):
    """Exact image ranges in Qwen's interleaved text/reference/target sequence."""
    slots = (list(image_slots) + [text_length] * len(reference_sizes))[:len(reference_sizes)]
    bounds = [0, *slots, text_length]
    if any(not isinstance(v, int) or not 0 <= v <= text_length for v in bounds) or bounds != sorted(bounds):
        raise ValueError("Qwen RoPE received invalid reference text positions.")
    spans, length = [], 0
    for (start, end), (height, width) in zip(zip(bounds, bounds[1:]), [*reference_sizes, target_size]):
        if min(height, width) <= 0:
            raise ValueError("Qwen RoPE received an empty image grid.")
        length += end - start
        spans.append((length, length + height * width))
        length += height * width
    return spans, length


@contextmanager
def qwen_rope_context(sd_model, enabled=False, ref_latents=(), image_slots=()):
    """Scale only Qwen image XY coordinates, never text or image-plane IDs.

    Hooks are scoped to one queued sample and removed even on cancellation.
    Clear cached reference keys on both boundaries so they cannot cross settings.
    """
    if not enabled:
        yield
        return
    model = sd_model.forge_objects.unet.model.diffusion_model
    embedder = getattr(model, "pe_embedder", None)
    reset = getattr(model, "reset_prefix_cache", None)
    if embedder is None or not hasattr(embedder, "register_forward_pre_hook") or not callable(reset):
        raise ValueError("This Qwen backend does not expose compatible RoPE coordinates. Update the backend before enabling RoPE adjustment.")
    spans, length = [], 0
    cache_enabled = bool(model.prefix_cache_enabled)

    def capture_layout(module, args, kwargs):
        nonlocal spans, length
        def argument(name, index, fallback=None):
            value = kwargs.get(name, args[index] if len(args) > index else None)
            return fallback if value is None else value
        x, context = argument("x", 0), argument("context", 2)
        refs = argument("ref_latents", 3, ref_latents)
        slots = argument("image_slots", 4, image_slots)
        spans, length = qwen_image_spans(context.shape[1], slots, [r.shape[-2:] for r in refs], x.shape[-2:])

    def scale_positions(module, inputs):
        ids = inputs[0]
        if not spans or ids.shape[-2:] != (length, 3):
            raise ValueError("Qwen RoPE sequence does not match this backend's image layout.")
        ids = ids.clone()
        for start, end in spans:
            ids[..., start:end, 1] *= QWEN_ROPE_Y
            ids[..., start:end, 2] *= QWEN_ROPE_X
        return (ids, *inputs[1:])

    handles = []
    try:
        reset(cache_enabled)
        handles.append(model.register_forward_pre_hook(capture_layout, with_kwargs=True))
        handles.append(embedder.register_forward_pre_hook(scale_positions))
        yield
    finally:
        for handle in reversed(handles):
            handle.remove()
        reset(cache_enabled)


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
