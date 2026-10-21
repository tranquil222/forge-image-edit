"""Optional global tone matching; no compositing, sharpening or detail restoration."""
import numpy as np
from PIL import Image, ImageFilter


def match_source_tone(source, edited, exclude=None):
    """Fit one neutral RGB gain/offset to aligned, mostly unchanged content.

    Robust fitting reduces the influence of a newly edited object. Work at low
    resolution for the estimate only; apply the curve to the untouched full-size
    result. Alpha is preserved. A painted region is excluded from the fit.
    """
    size = edited.size
    reference = source.convert("RGBA").resize(size, Image.Resampling.LANCZOS)
    result = edited.convert("RGBA")
    small = (max(1, round(size[0] * min(1, 256 / max(size)))),
             max(1, round(size[1] * min(1, 256 / max(size)))))
    arrays = [np.asarray(im.resize(small, Image.Resampling.BOX).filter(ImageFilter.GaussianBlur(1)), dtype=np.float64) / 255
              for im in (reference, result)]
    ref, out = arrays
    valid = (ref[..., 3] > .99) & (out[..., 3] > .99)
    if exclude is not None:
        # Include a small border so the edited edge cannot steer the fit.
        selection = exclude.convert("L").resize(small, Image.Resampling.BOX).filter(ImageFilter.MaxFilter(5))
        valid &= np.asarray(selection) == 0
    info = {"algorithm": "robust_affine_rgb_v1", "applied": False, "reason": "too_little_unchanged_context"}
    if np.count_nonzero(valid) < 64:
        return edited, info
    weights = np.array([.2126, .7152, .0722])
    x, y = (im[..., :3] @ weights for im in (out, ref))
    x, y = x[valid], y[valid]
    # Avoid fitting through clipped shadows/highlights: lost detail is not recoverable.
    valid = (x > .02) & (x < .98) & (y > .02) & (y < .98)
    x, y = x[valid], y[valid]
    if len(x) < 64 or np.std(x) < .01 or np.std(y) < .01:
        info["reason"] = "too_little_tonal_range"
        return edited, info
    spread_x = np.diff(np.percentile(x, [10, 90]))[0]
    spread_y = np.diff(np.percentile(y, [10, 90]))[0]
    gain = spread_y / max(spread_x, .01)
    offset = np.median(y - gain * x)
    for _ in range(8):
        residual = y - (gain * x + offset)
        center = np.median(residual)
        scale = max(1 / 255, 1.4826 * np.median(np.abs(residual - center)))
        u = (residual - center) / (4.685 * scale)
        weight = np.square(np.maximum(0, 1 - u * u))
        total = weight.sum()
        if total < 64:
            return edited, info
        mx, my = (np.sum(weight * values) / total for values in (x, y))
        variance = np.sum(weight * (x - mx) ** 2)
        if variance < 1e-5:
            info["reason"] = "too_little_tonal_range"
            return edited, info
        gain = np.sum(weight * (x - mx) * (y - my)) / variance
        offset = my - gain * mx
    # This is a modest drift correction, not relighting or a new color grade.
    gain = float(np.clip(gain, .67, 1.5))
    offset = float(np.clip(offset, -.2, .2))
    pixels = np.array(result)
    pixels[..., :3] = np.clip(np.rint(pixels[..., :3].astype(np.float32) * gain + offset * 255), 0, 255).astype(np.uint8)
    matched = Image.fromarray(pixels).convert(edited.mode if edited.mode in ("RGB", "RGBA") else "RGBA")
    matched.info = edited.info.copy()
    info.update(applied=True, gain=round(gain, 8), offset=round(offset, 8))
    info.pop("reason", None)
    return matched, info


def tone_summary(info):
    """Concise per-result feedback, including when the estimate does nothing."""
    if not info.get("applied"):
        reason = "too little tonal range" if info.get("reason") == "too_little_tonal_range" else "too little unchanged context"
        return f"auto tone skipped ({reason})"
    gain, offset = info["gain"], info["offset"]
    # One output level or less is effectively negligible for this 8-bit export.
    largest_shift = max(abs(offset * 255), abs((gain - 1 + offset) * 255))
    if largest_shift <= 1.5:
        return "auto tone: negligible global drift detected"
    return f"auto tone: contrast {(gain - 1) * 100:+.1f}%, brightness {offset * 255:+.1f}/255"
