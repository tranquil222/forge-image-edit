"""Image preparation and data-only workflow import. No Forge imports."""

import hashlib
import json
import math
from contextlib import nullcontext

import numpy as np
from PIL import Image, ImageOps


QUALITY_PRESETS = {
    "Turbo (8 steps)": {"steps": 8, "sampler": "Euler", "schedule": "Qwen 2.1 Turbo (official)", "prefix_cache": True},
    "Quick": {"steps": 8, "sampler": "Res Multistep", "schedule": "CyberZit Quality", "prefix_cache": True},
    "Normal": {"steps": 12, "sampler": "Res Multistep", "schedule": "CyberZit Quality", "prefix_cache": True},
    "High quality": {"steps": 16, "sampler": "Res Multistep", "schedule": "CyberZit Quality", "prefix_cache": True},
    "Extra high quality": {"steps": 40, "sampler": "Euler", "schedule": "Simple", "prefix_cache": True},
}
PROFILES = (*QUALITY_PRESETS, "Custom")
DEFAULT_MODEL = "qwen_image_2.1_int8_convrot.safetensors"
DEFAULT_TURBO_MODEL = "qwen_image_2.1_turbo_int8_convrot.safetensors"
DEFAULT_ENCODER = "qwen3vl_8b_int8_convrot.safetensors"
DEFAULT_VAE = "qwen_image_2.1_vae_bf16.safetensors"
SCHEDULES = ("CyberZit Quality", "Simple", "Qwen 2.1 Turbo (official)")
SAMPLERS = {"res_multistep": "Res Multistep", "euler": "Euler"}


def fibo_result_prompt(instruction, description=""):
    """Optional native Fibo result caption; no network or prompt enhancement service."""
    if not description or not description.strip():
        return instruction
    try:
        existing = json.loads(instruction)
    except json.JSONDecodeError:
        existing = None
    if isinstance(existing, dict):
        raise ValueError("Use either a JSON edit instruction or the finished-image description field, not both.")
    return json.dumps({"edit_instruction": instruction,
                       "structured_caption": {"short_description": description.strip()}}, ensure_ascii=False)


def reference_size(width, height, resolution):
    if width < 1 or height < 1:
        raise ValueError("The reference image has no pixels.")
    resolution = int(resolution)
    if not 0 <= resolution <= 4096:
        raise ValueError("Reference resolution must be between 0 and 4096.")
    if resolution:
        ratio = width / height
        width = math.sqrt(resolution * resolution * ratio)
        height = math.sqrt(resolution * resolution / ratio)
    rounding = round if resolution else math.ceil
    return max(32, rounding(width / 32) * 32), max(32, rounding(height / 32) * 32)


def reference_content_box(width, height, resolution):
    """Fit without stretching; the model grid is padding, never scene content."""
    grid_w, grid_h = reference_size(width, height, resolution)
    factor = min(grid_w / width, grid_h / height) if int(resolution) else 1
    content_w = max(1, min(grid_w, round(width * factor)))
    content_h = max(1, min(grid_h, round(height * factor)))
    left, top = (grid_w - content_w) // 2, (grid_h - content_h) // 2
    return left, top, left + content_w, top + content_h


def prepare_reference(image, resolution):
    image = ImageOps.exif_transpose(image)
    image = image.convert("RGBA" if "A" in image.getbands() or "transparency" in image.info else "RGB")
    size = reference_size(*image.size, resolution)
    left, top, right, bottom = reference_content_box(*image.size, resolution)
    content_size = (right - left, bottom - top)
    content = image if image.size == content_size else image.resize(content_size, Image.Resampling.LANCZOS)
    if content.size == size:
        return content
    pixels = np.pad(np.asarray(content), ((top, size[1] - bottom), (left, size[0] - right), (0, 0)), mode="edge")
    result = Image.fromarray(pixels)
    result.info = image.info.copy()
    return result


def output_resize_size(source_size, settings):
    """Whole-image output size, with proportions locked (use canvas tools to reframe)."""
    if not isinstance(settings, dict):
        raise ValueError("Output size settings must be an object.")
    if not isinstance(source_size, (tuple, list)) or len(source_size) != 2 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in source_size):
        raise ValueError("Valid source dimensions are required for output resizing.")
    source_w, source_h = source_size
    mode = settings.get("mode", "Resize to")
    if mode == "Resize by":
        scale = settings.get("scale", 1)
        if isinstance(scale, bool) or not isinstance(scale, (int, float)) or not math.isfinite(scale) or not .25 <= scale <= 4:
            raise ValueError("Resize by must be between 0.25 and 4.")
        width, height = round(source_w * scale), round(source_h * scale)
    elif mode == "Resize to":
        width, height = settings.get("width"), settings.get("height")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or int(v) != v for v in (width, height)):
            raise ValueError("Output width and height must be whole numbers.")
        # Either edge may drive the linked controls; allow only pixel rounding.
        if abs(width - height * source_w / source_h) > .51 and abs(height - width * source_h / source_w) > .51:
            raise ValueError("Output dimensions must preserve source proportions. Use Crop / outpaint to change the canvas shape.")
    else:
        raise ValueError("Choose Resize to or Resize by.")
    if not 32 <= width <= 4096 or not 32 <= height <= 4096:
        raise ValueError("Output width and height must be between 32 and 4096 pixels.")
    return int(width), int(height)


def prepare_sized_reference(image, size):
    # Native-sized preparation edge-pads to the model grid; the caller unpads
    # the generated result. No post-generation upscale is substituted for inference.
    return prepare_reference(image.resize(size, Image.Resampling.LANCZOS), 0)


def image_digest(image):
    return hashlib.sha256(image.mode.encode() + str(image.size).encode() + image.tobytes()).hexdigest()


def cyberzit_quality_values(steps):
    """CyberZiT quality, detail=0: rational flow shift 3, including terminal 0.

    Formula from Cyberdelia/ComfyUI-CyberZiT (MIT; see licenses/CyberZiT.txt).
    These are final sigmas, independent of the model's own timestep shift.
    """
    if isinstance(steps, bool) or int(steps) != steps or steps < 1:
        raise ValueError("Steps must be a positive integer.")
    values = []
    for i in range(int(steps) + 1):
        sigma = 1.0 - i / steps
        values.append(3.0 * sigma / (1.0 + 2.0 * sigma))
    return values


def read_recipe(path):
    """Read settings, never execute a graph or resolve its embedded file paths."""
    with (nullcontext(path) if isinstance(path, Image.Image) else Image.open(path)) as image:
        if "image_edit" in image.info or "qwen_edit" in image.info:
            recipe = json.loads(image.info.get("image_edit", image.info.get("qwen_edit")))
            if recipe.get("version") != 1:
                raise ValueError("Unsupported Image Edit recipe version.")
            return validate_recipe(recipe)
        graph = json.loads(image.info.get("prompt", "{}"))
    if not isinstance(graph, dict):
        raise ValueError("The PNG does not contain a ComfyUI prompt graph.")
    nodes = [n for n in graph.values() if isinstance(n, dict)]
    encoders = [n["inputs"] for n in nodes if n.get("class_type") == "TextEncodeQwenImage21"]
    samplers = [n["inputs"] for n in nodes if n.get("class_type") == "KSampler"]
    if len(encoders) != 1 or len(samplers) != 1:
        raise ValueError("Import requires one Qwen Image 2.1 encoder and one KSampler. Complex graphs are not guessed.")
    encoder, sampler = encoders[0], samplers[0]
    if sampler.get("denoise") != 1.0:
        raise ValueError("This tab uses full-denoise reference editing. That PNG uses a different denoise value.")
    schedule_map = {"cyberzit_quality": SCHEDULES[0], "simple": SCHEDULES[1]}
    if sampler.get("sampler_name") not in SAMPLERS or sampler.get("scheduler") not in schedule_map:
        raise ValueError("That sampler/scheduler is not supported by the basic PNG importer.")
    recipe = {
        "version": 1, "prompt": encoder.get("prompt", ""),
        "negative_prompt": encoder.get("negative_prompt", ""),
        "resolution": encoder.get("resolution", 1024), "steps": sampler.get("steps"),
        "cfg": sampler.get("cfg"), "seed": str(sampler.get("seed")),
        "sampler": SAMPLERS[sampler["sampler_name"]], "schedule": schedule_map[sampler["scheduler"]],
    }
    for kind, field, key in (("UNETLoader", "unet_name", "model"), ("CLIPLoader", "clip_name", "encoder"), ("VAELoader", "vae_name", "vae")):
        matches = [n["inputs"].get(field) for n in nodes if n.get("class_type") == kind]
        if len(matches) == 1 and isinstance(matches[0], str):
            recipe[key] = matches[0].replace("\\", "/").rsplit("/", 1)[-1]
    return validate_recipe(recipe)


def validate_recipe(recipe):
    if recipe.get("operation") == "canvas_crop":
        return recipe
    for key in ("prompt", "negative_prompt"):
        if not isinstance(recipe.get(key, ""), str):
            raise ValueError(f"The {key} is linked to another node; a literal value is required.")
    if recipe.get("sampler") not in SAMPLERS.values() or recipe.get("schedule") not in SCHEDULES:
        raise ValueError("Unsupported sampler or schedule in this recipe.")
    cfg = float(recipe.get("cfg", 1))
    if not 1 <= cfg <= 15 or (recipe.get("model_family") != "Fibo 2.0 Dev" and cfg != 1):
        raise ValueError("CFG must be 1 for Turbo/Qwen, or between 1 and 15 for Fibo Dev.")
    steps = int(recipe["steps"])
    resolution = int(recipe["resolution"])
    if not 1 <= steps <= 150 or not 0 <= resolution <= 4096:
        raise ValueError("The recipe's steps or resolution is out of range.")
    seed = parse_seed(recipe["seed"])
    if recipe.get("output_resize") is not None:
        output_resize_size(recipe.get("source_size", recipe.get("output_size", (0, 0))), recipe["output_resize"])
    if recipe.get("model_family", "").startswith("Fibo 2.0"):
        from .sampling import validate_fibo_sampling
        mode, shift, rope = validate_fibo_sampling(recipe.get("fibo_shift_mode", "Manual"), recipe.get("fibo_shift", 1.15), recipe.get("fibo_rope", False))
        recipe = {**recipe, "fibo_shift_mode": mode, "fibo_shift": shift, "fibo_rope": rope}
    elif recipe.get("model_family", "Qwen Image 2.1") == "Qwen Image 2.1":
        from .sampling import validate_qwen_sampling
        mode, shift, rope = validate_qwen_sampling(recipe.get("qwen_shift_mode", "Manual"), recipe.get("qwen_shift", .69), recipe.get("qwen_rope", False))
        recipe = {**recipe, "qwen_shift_mode": mode, "qwen_shift": shift, "qwen_rope": rope}
    return {**recipe, "steps": steps, "resolution": resolution, "seed": str(seed), "cfg": cfg}


def parse_seed(value):
    try:
        seed = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError("Seed must be a whole number, or -1 for random.") from None
    if not -1 <= seed <= 2**64 - 1:
        raise ValueError("Seed must be -1 or an unsigned 64-bit integer.")
    return seed
