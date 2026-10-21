"""Signed canvas edges: negative crops, positive adds a model-filled border."""
import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from . import __version__
from .masking import canonical_image

EDGES = ("left", "right", "top", "bottom")
GREY = (128, 128, 128, 255)


def canvas_plan(size, edges):
    width, height = size
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
    return {"version": 1, "edges": values, "source_size": list(size), "output_size": list(output),
            "source_box": list(source_box), "position": list(position),
            "expand": retained_size != output, "changed": any(values.values())}


def canvas_images(source, plan):
    source = canonical_image(source)
    if list(source.size) != plan["source_size"]:
        raise ValueError("The source changed. Set the canvas edges again.")
    retained = source.crop(plan["source_box"])
    output = Image.new("RGBA", plan["output_size"], GREY)
    output.paste(retained, tuple(plan["position"]))
    output.info = source.info.copy()
    mask = Image.new("L", output.size, 255)
    x, y = plan["position"]
    mask.paste(0, (x, y, x + retained.width, y + retained.height))
    return output, mask


def outpaint_instruction(instruction, fibo):
    marker = "neutral-grey" if fibo else "bright green"
    ref = "<image_1>" if fibo else "<image1>"
    rules = (f"Extend the photograph in {ref} into the {marker} border outside its existing content. "
             "The border is missing canvas, not an object. Continue the scene naturally across the image edges, "
             "matching perspective, lighting, textures and scale. Fill every part of the border; leave no mask visible. "
             "Do not add a frame, duplicate the photograph, or shrink the original content. "
             "Preserve the retained photograph.")
    instruction = (instruction or "").strip() or "Extend the surrounding scene naturally."
    if fibo:
        try:
            structured = json.loads(instruction)
        except ValueError:
            structured = None
        if isinstance(structured, dict):
            structured["edit_instruction"] = str(structured.get("edit_instruction", "")).strip() + "\n\n" + rules
            return json.dumps(structured, ensure_ascii=False)
    return instruction + "\n\n" + rules


def save_crop(source, edges, keep_metadata=True):
    from modules import images, shared
    from .adjustments import MASK_KEY, remember_selection
    from .metadata import build_metadata, preserve_binary_metadata

    source = canonical_image(source)
    plan = canvas_plan(source.size, edges)
    if plan["expand"] or not plan["changed"]:
        raise ValueError("Move an edge inward to crop, or use Generate outpaint to fill added space.")
    output = source.crop(plan["source_box"])
    recipe = {"version": 1, "extension_version": __version__, "operation": "canvas_crop",
              "model_family": "Canvas crop", "canvas": plan, "source_size": list(source.size),
              "output_size": list(output.size), "prompt": "Canvas crop", "area_only": False}
    fields, binary = build_metadata(source, recipe, "Canvas crop (no model generation)", keep_metadata)
    fields.pop(MASK_KEY, None)
    output.info.clear()
    directory = shared.opts.outdir_samples or shared.opts.outdir_img2img_samples
    p = SimpleNamespace(prompt="Canvas crop", negative_prompt="", steps=0, cfg_scale=1,
        distilled_cfg_scale=1, sampler_name="", scheduler="", batch_size=1, batch_index=0,
        n_iter=1, iteration=0, all_seeds=[-1], styles=[], denoising_strength=None, user="", extra_generation_params={})
    filename, _ = images.save_image(output, directory, "", seed=-1, prompt="Canvas crop",
        extension="png", info=fields["parameters"], p=p, existing_info=fields, suffix="-crop")
    if shared.opts.enable_pnginfo:
        preserve_binary_metadata(filename, binary)
        output.info.update(fields)
        output.info.update(binary)
    remember_selection(filename, None, recipe)
    return output, str(filename), f"Saved {Path(filename).name} · {output.width} × {output.height} · crop only, no model run"
