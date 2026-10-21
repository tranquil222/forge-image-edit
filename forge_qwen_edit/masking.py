"""Painted-area editing: data-only mask extraction, contextual crop and compositing."""

import json

from PIL import Image, ImageChops, ImageFilter, ImageOps

from .workflow import image_digest

AREA_MODES = ("Replace / remove", "Refine / expression")


def canonical_image(image):
    return ImageOps.exif_transpose(image).convert("RGBA")


def editor_value(source):
    if source is None:
        return None
    source = canonical_image(source)
    return {"background": source, "layers": [], "composite": source}


def has_painted_area(foreground):
    """Only stroke alpha selects an edit area; an empty canvas edits globally."""
    if foreground is None:
        return False
    if "A" not in foreground.getbands():
        raise ValueError("The painted layer has no transparency. Clear the painted area and paint again.")
    return foreground.getchannel("A").getbbox() is not None


def extract_mask(source, editor):
    """Read stroke alpha, never select naturally green pixels in the photo."""
    source = canonical_image(source)
    if not isinstance(editor, dict) or editor.get("background") is None:
        raise ValueError("Paint the area you want to change first.")
    background = canonical_image(editor["background"])
    if background.size != source.size or image_digest(background) != image_digest(source):
        raise ValueError("The painted area belongs to a different source. Clear the painted area and paint again.")
    mask = Image.new("L", source.size, 0)
    for layer in editor.get("layers") or []:
        if layer is None:
            continue
        if layer.size != source.size:
            raise ValueError("The painting canvas changed size. Clear the painted area and paint again.")
        if "A" not in layer.getbands():
            raise ValueError("The painted layer has no transparency. Clear the painted area and paint again.")
        mask = ImageChops.lighter(mask, layer.getchannel("A"))
    if mask.getbbox() is None:
        raise ValueError("No area is painted. Paint over the object or expression you want to change.")
    return mask


def context_box(mask):
    """Include surrounding context without processing an entire large photo."""
    box = mask.getbbox()
    if box is None:
        raise ValueError("The edit mask is empty.")
    left, top, right, bottom = box
    width, height = mask.size
    margin = max(64, round(max(right - left, bottom - top) * 0.5))
    crop_width = min(width, max(256, right - left + margin * 2))
    crop_height = min(height, max(256, bottom - top + margin * 2))
    x = min(max(0, (left + right - crop_width) // 2), width - crop_width)
    y = min(max(0, (top + bottom - crop_height) // 2), height - crop_height)
    return x, y, x + crop_width, y + crop_height


def location_guide(source, mask, opaque=False):
    """A separate green-marked reference; the clean reference stays intact."""
    rgb = canonical_image(source).convert("RGB")
    # Replacement must not leak the old content through a translucent overlay.
    overlay = mask.point(lambda value: 255 if value else 0) if opaque else mask.point(lambda value: round(value * 0.65))
    return Image.composite(Image.new("RGB", rgb.size, (0, 255, 0)), rgb, overlay)


def fibo_masked_reference(source, mask):
    """Fibo reference preprocessing: RGB 128 grey, binary mask threshold 128.

    Matches BriaFibo2ImageProcessor.grey_out from the reference pipeline.
    Qwen's coloured location guide is deliberately not used for this model.
    """
    rgb = canonical_image(source).convert("RGB")
    binary = mask.convert("L").point(lambda value: 255 if value >= 128 else 0)
    if binary.getbbox() is None:
        raise ValueError("Paint an opaque edit area; Fibo requires mask opacity of at least 50%.")
    return Image.composite(Image.new("RGB", rgb.size, (128, 128, 128)), rgb, binary)


def fibo_masked_instruction(instruction):
    rules = ("The neutral-grey area in <image_1> marks the region to edit. "
            "Replace that entire masked area with the requested content. For removal, reconstruct the "
            "background that belongs there. Match the surrounding scene and leave no grey mask visible.")
    try:
        structured = json.loads(instruction)
    except ValueError:
        structured = None
    if isinstance(structured, dict):
        structured["edit_instruction"] = str(structured.get("edit_instruction", "")).strip() + "\n\n" + rules
        return json.dumps(structured, ensure_ascii=False)
    return instruction.strip() + "\n\n" + rules


def scoped_instruction(instruction, guide_index, replace=False):
    if replace:
        return (
            f"{instruction.strip()}\n\n"
            "Editing rules for <image1>: The solid bright green region is a "
            "selection marker covering the area to replace, not an object or a "
            "color to keep. Replace the entire green-marked region with the "
            "content specified by the user's instruction above. That instruction "
            "defines the desired replacement. If it requests object removal, "
            "reconstruct the surrounding background in that region. Remove all "
            "green marker; do not merely recolor the marker or leave it in place. "
            "Match the surrounding rendering style and lighting. Keep everything "
            "outside the marked area unchanged."
        )
    return (
        f"Edit <image1>. <image{guide_index}> is a location guide of the same crop: "
        "the bright green overlay marks the only area to change. Use the clean "
        "original in <image1> for appearance and identity, not the green overlay. "
        f"Requested edit: {instruction.strip()}\n"
        "Apply that change inside the marked area. Keep the original rendering "
        "style, lighting and all other details. Return a clean image with no green marker."
    )


def composite_patch(source, edited, mask, box, feather=8):
    """Feather inward only. Pixels outside painted support are byte-for-byte kept."""
    source = canonical_image(source)
    if mask.size != source.size:
        raise ValueError("Mask dimensions do not match the original image.")
    feather = float(feather)
    if not 0 <= feather <= 64:
        raise ValueError("Edge blending must be between 0 and 64 pixels.")
    x1, y1, x2, y2 = box
    patch_size = (x2 - x1, y2 - y1)
    if min(patch_size) < 1 or x1 < 0 or y1 < 0 or x2 > source.width or y2 > source.height:
        raise ValueError("Invalid edit crop.")
    patch = edited.convert("RGBA").resize(patch_size, Image.Resampling.LANCZOS)
    original = source.crop(box)
    # Cleanup must not accidentally change the source's transparency.
    patch.putalpha(original.getchannel("A"))
    alpha = mask
    if feather:
        alpha = ImageChops.multiply(mask, mask.filter(ImageFilter.GaussianBlur(feather)))
    merged = Image.composite(patch, original, alpha.crop(box))
    output = source.copy()
    output.paste(merged, (x1, y1))
    return output
