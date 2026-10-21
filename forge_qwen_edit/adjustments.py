"""CPU-only, full-resolution curves export using the browser's exact RGB LUTs."""
from copy import deepcopy
from collections import OrderedDict
import base64
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageChops, ImageFilter

from . import __version__
from .metadata import build_metadata, preserve_binary_metadata, text_fields

MASK_KEY = "image_edit_mask"
_selections = OrderedDict()


def encode_selection(mask, feather=0):
    """Store the exact inward-feathered support, not the green/grey guide."""
    if mask is None:
        return None
    alpha = mask.convert("L")
    if feather:
        alpha = ImageChops.multiply(alpha, alpha.filter(ImageFilter.GaussianBlur(float(feather))))
    buffer = io.BytesIO()
    alpha.save(buffer, format="PNG")
    return {"version": 1, "size": list(alpha.size), "png": base64.b64encode(buffer.getvalue()).decode("ascii")}


def remember_selection(path, selection):
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    _selections[digest] = selection
    _selections.move_to_end(digest)
    while len(_selections) > 12:
        _selections.popitem(last=False)


def result_context(saved_path, digest):
    if not saved_path:
        raise ValueError("Generate an edit before adjusting the result.")
    path = Path(saved_path)
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError("The result changed. Reopen its viewer before applying curves.")
    with Image.open(path) as opened:
        source = opened.copy()
    selection = _selections.get(digest)
    if digest not in _selections:
        try:
            selection = json.loads(source.info.get(MASK_KEY, "null"))
            recipe = json.loads(source.info.get("image_edit", "null"))
        except (ValueError, TypeError):
            raise ValueError("The saved edit selection could not be read.") from None
        if selection is None and isinstance(recipe, dict) and recipe.get("area_only"):
            raise ValueError("This older painted result has no saved mask. Generate a new painted edit to adjust only that area.")
    mask = None
    if selection is not None:
        if (not isinstance(selection, dict) or selection.get("version") != 1 or selection.get("size") != list(source.size)
                or not isinstance(selection.get("png"), str) or len(selection["png"]) > 24_000_000):
            raise ValueError("The saved mask does not match this result.")
        with Image.open(io.BytesIO(base64.b64decode(selection["png"], validate=True))) as opened:
            if opened.size != source.size:
                raise ValueError("The saved mask dimensions do not match this result.")
            mask = opened.convert("L")
    return source, mask, selection


def describe_result(saved_path, payload):
    data = json.loads(payload)
    _, mask, selection = result_context(saved_path, data.get("base_sha256"))
    return {"id": data.get("id"), "ok": True, "op": "context", "scope": "Painted area" if mask else "Whole image",
            "mask": "data:image/png;base64," + selection["png"] if mask else None}


def parse_adjustment(payload):
    if not isinstance(payload, str) or len(payload) > 24000:
        raise ValueError("Invalid curves settings.")
    data = json.loads(payload)
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("Unsupported curves settings.")
    tables = data.get("luts")
    if not isinstance(tables, list) or len(tables) != 3 or any(
        not isinstance(lut, list) or len(lut) != 256 or any(type(n) is not int or not 0 <= n <= 255 for n in lut)
        for lut in tables
    ):
        raise ValueError("Curves require three 256-value RGB tables.")
    settings = data.get("settings")
    if not isinstance(settings, dict) or set(settings) != {"rgb", "red", "green", "blue"}:
        raise ValueError("Curves require RGB, red, green and blue settings.")
    for channel in settings.values():
        if not isinstance(channel, dict):
            raise ValueError("Invalid channel settings.")
        points, levels = channel.get("points"), channel.get("levels")
        if (not isinstance(points, list) or not 2 <= len(points) <= 16 or
                any(not isinstance(p, list) or len(p) != 2 or any(type(n) is not int or not 0 <= n <= 255 for n in p) for p in points) or
                points[0][0] != 0 or points[-1][0] != 255 or any(a[0] >= b[0] for a, b in zip(points, points[1:]))):
            raise ValueError("Invalid curve points.")
        if (not isinstance(levels, list) or len(levels) != 5 or
                any(type(n) not in (int, float) or not np.isfinite(n) for n in levels) or
                not (0 <= levels[0] < levels[2] <= 255 and .1 <= levels[1] <= 10 and 0 <= levels[3] <= levels[4] <= 255)):
            raise ValueError("Invalid level controls.")
    if not isinstance(data.get("base_sha256"), str) or len(data["base_sha256"]) != 64:
        raise ValueError("Reopen the result before applying curves.")
    return data


def apply_luts(image, tables, mask=None):
    pixels = np.array(image.convert("RGBA"))
    lookup = np.asarray(tables, dtype=np.uint8)
    for channel in range(3):
        pixels[..., channel] = lookup[channel, pixels[..., channel]]
    output = Image.fromarray(pixels)
    if mask is not None:
        if mask.size != image.size:
            raise ValueError("Mask dimensions do not match the result.")
        output = Image.composite(output, image.convert("RGBA"), mask)
    return output


def adjustment_metadata(source, data, keep_original, selection=None):
    scope = "painted area" if selection is not None else "whole image"
    adjustment = {"type": "curves", "version": 1, "extension_version": __version__,
                  "scope": scope, "space": "8-bit RGB", "order": "master levels/curve, then channel levels/curve",
                  "settings": data["settings"], "luts": data["luts"], "input_sha256": data["base_sha256"]}
    parameters = f"Manual RGB curves / levels adjustment ({scope}; no generation)"
    try:
        recipe = json.loads(source.info.get("image_edit", source.info.get("qwen_edit", "null")))
    except (ValueError, TypeError):
        recipe = None
    if isinstance(recipe, dict) and recipe.get("model_family"):
        recipe = deepcopy(recipe)
        previous = recipe.get("postprocessing", [])
        recipe["postprocessing"] = (previous if isinstance(previous, list) else []) + [adjustment]
        fields, binary = build_metadata(source, recipe, parameters, keep_original)
    else:
        # Ordinary or metadata-free PNGs get an adjustment record, not invented
        # model settings that would break the generation-recipe importer.
        fields = text_fields(source.info) if keep_original else {}
        previous = fields.get("parameters", "")
        fields["parameters"] = (previous + "\n\n--- Image Edit adjustment ---\n" if previous else "") + parameters
        binary = {key: source.info[key] for key in ("exif", "icc_profile", "dpi") if keep_original and key in source.info}
        recipe = {}
    fields["image_edit_adjustment"] = json.dumps(adjustment, ensure_ascii=False)
    fields.pop(MASK_KEY, None)
    if selection is not None and len(selection["png"]) < 500_000:
        fields[MASK_KEY] = json.dumps(selection)
    return fields, binary, recipe


def save_adjustment(saved_path, payload, keep_original=True):
    from modules import images, shared

    data = parse_adjustment(payload)
    source, mask, selection = result_context(saved_path, data["base_sha256"])
    output = apply_luts(source, data["luts"], mask)
    fields, binary, recipe = adjustment_metadata(source, data, bool(keep_original), selection)
    directory = shared.opts.outdir_samples or shared.opts.outdir_img2img_samples or str(Path(shared.data_path) / "outputs/img2img-images")
    seed, prompt = recipe.get("seed", ""), recipe.get("prompt", "curves adjustment")
    p = SimpleNamespace(prompt=prompt, negative_prompt=recipe.get("negative_prompt", ""),
        steps=recipe.get("steps", 0), cfg_scale=recipe.get("cfg", 1), distilled_cfg_scale=1,
        sampler_name=recipe.get("sampler", ""), scheduler=recipe.get("schedule", ""),
        batch_size=1, batch_index=0, n_iter=1, iteration=0, all_seeds=[seed], styles=[],
        denoising_strength=None, user="", extra_generation_params={"Image Edit adjustment": "Curves"})
    filename, _ = images.save_image(output, directory, "", seed=seed, prompt=prompt,
        extension="png", info=fields["parameters"], p=p, existing_info=fields, suffix="-curves")
    if shared.opts.enable_pnginfo:
        preserve_binary_metadata(filename, binary)
        output.info.update(fields)
        output.info.update(binary)
    remember_selection(filename, selection)
    return output, str(filename), data.get("id", "")
