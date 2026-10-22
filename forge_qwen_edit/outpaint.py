"""Signed canvas edges: negative crops, positive adds a model-filled border."""
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image

from . import __version__
from .masking import canonical_image, fibo_masked_instruction
from .workflow import reference_content_box, output_resize_size

EDGES = ("left", "right", "top", "bottom")
GREY = (128, 128, 128, 255)


def canvas_plan(size, edges):
    width, height = size
    shrink = edges.get("shrink_by", 1)
    try:
        if isinstance(shrink, bool) or not 1 <= float(shrink) <= 4:
            raise ValueError()
        shrink = float(shrink)
    except (ValueError, TypeError, OverflowError):
        raise ValueError("Shrink by must be a number from 1 to 4; 1 keeps the original size.") from None
    blend = edges.get("seam_blend", 32)
    try:
        if isinstance(blend, bool) or int(blend) != float(blend) or not 0 <= int(blend) <= 128:
            raise ValueError()
        blend = int(blend)
    except (ValueError, TypeError, OverflowError):
        raise ValueError("Seam blending must be a whole number from 0 to 128 pixels.") from None
    values = {}
    for key in EDGES:
        value = edges.get(key, 0)
        try:
            number = int(value)
            if isinstance(value, bool) or float(value) != number or abs(number) > 16384:
                raise ValueError()
        except (TypeError, ValueError, OverflowError):
            raise ValueError("Canvas edges must be whole pixel values between -16384 and 16384.") from None
        values[key] = number
    left, right, top, bottom = (values[key] for key in EDGES)
    output = (width + left + right, height + top + bottom)
    source_box = (max(0, -left), max(0, -top), min(width, width + right), min(height, height + bottom))
    if source_box[0] >= source_box[2] or source_box[1] >= source_box[3]:
        raise ValueError("Keep some of the original image inside the canvas.")
    if min(output) < 1 or max(output) > 16384 or output[0] * output[1] > 64_000_000:
        raise ValueError("The canvas must be 1–16384 pixels per side and at most 64 megapixels.")
    position = (max(0, left), max(0, top))
    retained_size = (source_box[2] - source_box[0], source_box[3] - source_box[1])
    resize = edges.get("output_resize")
    final_size = output_resize_size(output, resize) if resize is not None else tuple(max(1, round(side / shrink)) for side in output)
    # Scale the placement, not a grey-padded bitmap: grey must never bleed into
    # the retained photo during resampling. Keep even small added edges present.
    final_position, final_retained = [], []
    for axis in range(2):
        before, after = (left, right) if axis == 0 else (top, bottom)
        length = final_size[axis]
        start = max(1, round(position[axis] * length / output[axis])) if before > 0 else 0
        end = min(length - 1, round((position[axis] + retained_size[axis]) * length / output[axis])) if after > 0 else length
        if end <= start:
            raise ValueError("Output size is too small. Keep room for the original and added edges.")
        final_position.append(start)
        final_retained.append(end - start)
    return {"version": 3, "edges": values, "seam_blend": blend, "shrink_by": shrink,
            **({"output_resize": dict(resize)} if resize is not None else {}),
            "source_size": list(size), "canvas_size": list(output), "output_size": list(final_size),
            "source_box": list(source_box), "position": final_position, "retained_size": final_retained,
            "expand": retained_size != output, "changed": any(values.values()) or final_size != output}


def canvas_reference_resolution(size, resolution, shrink_by=1):
    """Keep the user's resolution cap, but never enlarge an explicitly shrunk canvas."""
    box = reference_content_box(*size, resolution)
    if shrink_by > 1 and (box[2] - box[0] > size[0] or box[3] - box[1] > size[1]):
        return 0  # Native pixels; only model-grid padding is added.
    return int(resolution)


def canvas_images(source, plan, painted_mask=None):
    source = canonical_image(source)
    if list(source.size) != plan["source_size"]:
        raise ValueError("The source changed. Set the canvas edges again.")
    retained = source.crop(plan["source_box"])
    target_size = tuple(plan["retained_size"])
    if retained.size != target_size:
        retained = retained.resize(target_size, Image.Resampling.LANCZOS)
    output = Image.new("RGBA", plan["output_size"], GREY)
    output.paste(retained, tuple(plan["position"]))
    output.info = source.info.copy()
    mask = Image.new("L", output.size, 255)
    x, y = plan["position"]
    if painted_mask is not None:
        if painted_mask.size != source.size:
            raise ValueError("The painted area does not match the source image.")
        paint = painted_mask.convert("L").crop(plan["source_box"])
        if paint.size != target_size:
            paint = paint.resize(target_size, Image.Resampling.NEAREST)
        mask.paste(paint, (x, y))
    else:
        mask.paste(0, (x, y, x + retained.width, y + retained.height))
    return output, mask


def canvas_blend_mask(mask, plan):
    """Crossfade inside the retained photo only; never fade toward grey padding.

    This alpha mask is for the final composite, not Fibo's hard grey reference.
    No spatial blur/filter is applied to either image.
    """
    blend = plan.get("seam_blend", 0)
    if not blend or not plan["expand"]:
        return mask
    alpha = np.array(mask.convert("L"))
    x, y = plan["position"]
    width, height = plan["retained_size"]
    retained = alpha[y:y + height, x:x + width]
    horizontal = np.rint(255 * (1 - np.arange(min(blend, width)) / blend)).astype(np.uint8)[None, :]
    vertical = np.rint(255 * (1 - np.arange(min(blend, height)) / blend)).astype(np.uint8)[:, None]
    for edge, region, ramp in (
        ("left", retained[:, :horizontal.size], horizontal),
        ("right", retained[:, -horizontal.size:], horizontal[:, ::-1]),
        ("top", retained[:vertical.size, :], vertical),
        ("bottom", retained[-vertical.size:, :], vertical[::-1, :]),
    ):
        if plan["edges"][edge] > 0:
            np.maximum(region, ramp, out=region)
    return Image.fromarray(alpha)


def outpaint_instruction(instruction, fibo, painted=False):
    instruction = (instruction or "").strip() or "Extend the surrounding scene naturally."
    if not fibo:
        # Qwen can copy the coloured border with the longer Fibo-oriented rules.
        # Lead with a direct replacement request; the green guide itself is valid.
        rules = ("Replace all the green areas with a seamless continuation of the surrounding scene. "
                 "Continue the visible content naturally to fill the entire image, matching its style, lighting and perspective. ")
        if painted:
            rules += ("Also apply the requested edit to green areas inside the original image. "
                      "Keep the unmasked content unchanged.")
        else:
            rules += "Keep the existing scene unchanged."
        return rules + "\n\n" + instruction
    # Calling the source a photograph can encourage a picture-on-background
    # interpretation, especially with artwork/collages and a sparse caption.
    rules = ("Extend the existing scene in <image_1> outward into every neutral-grey masked area. "
             "The grey pixels are missing scene content, not a background around a separate picture. "
             "Create one continuous edge-to-edge scene covering the entire canvas. Continue the actual objects, surfaces, colors, patterns and depth from the adjacent visible content into the missing area. "
             "Match its visual style, scale, lighting and perspective. Do not turn the original content into a print, poster, framed picture or object on a wall or floor. "
             "Do not add a rectangular outline, drop shadow, blank surround or new vignette at the old image boundary. Preserve the unmasked content.")
    if painted:
        rules += (" Also replace the painted areas inside the original content with the requested content. "
                  "For object removal, reconstruct the surrounding background instead of continuing the covered object into the new border. "
                  "Preserve only the unpainted parts of the retained content.")
    try:
        structured = json.loads(instruction)
    except ValueError:
        structured = None
    if isinstance(structured, dict):
        structured["edit_instruction"] = str(structured.get("edit_instruction", "")).strip() + "\n\n" + rules
        return fibo_masked_instruction(json.dumps(structured, ensure_ascii=False))
    result = instruction + "\n\n" + rules
    return fibo_masked_instruction(result)


def save_crop(source, edges, keep_metadata=True):
    from modules import images, shared
    from .adjustments import MASK_KEY, remember_selection
    from .metadata import build_metadata, preserve_binary_metadata

    source = canonical_image(source)
    plan = canvas_plan(source.size, edges)
    if plan["expand"] or not plan["changed"]:
        raise ValueError("Crop an edge or change Output size, or use Generate outpaint to fill added space.")
    output, _ = canvas_images(source, plan)
    action = "Canvas crop / resize" if plan["output_size"] != plan["canvas_size"] else "Canvas crop"
    recipe = {"version": 1, "extension_version": __version__, "operation": "canvas_crop",
              "model_family": action, "canvas": plan, "source_size": list(source.size),
              "output_size": list(output.size), "prompt": action, "area_only": False}
    fields, binary = build_metadata(source, recipe, action + " (no model generation)", keep_metadata)
    fields.pop(MASK_KEY, None)
    output.info.clear()
    directory = shared.opts.outdir_samples or shared.opts.outdir_img2img_samples
    p = SimpleNamespace(prompt=action, negative_prompt="", steps=0, cfg_scale=1,
        distilled_cfg_scale=1, sampler_name="", scheduler="", batch_size=1, batch_index=0,
        n_iter=1, iteration=0, all_seeds=[-1], styles=[], denoising_strength=None, user="", extra_generation_params={})
    filename, _ = images.save_image(output, directory, "", seed=-1, prompt=action,
        extension="png", info=fields["parameters"], p=p, existing_info=fields, suffix="-crop")
    if shared.opts.enable_pnginfo:
        preserve_binary_metadata(filename, binary)
        output.info.update(fields)
        output.info.update(binary)
    remember_selection(filename, None, recipe)
    return output, str(filename), f"Saved {Path(filename).name} · {output.width} × {output.height} · crop / resize only, no model run"
