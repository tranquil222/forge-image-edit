"""Append edit history without discarding source PNG text, EXIF or ICC data."""
import base64
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import tempfile

from PIL import Image
from PIL.PngImagePlugin import PngInfo

HISTORY_KEY = "Image Edit history"


def text_fields(info):
    return {key: value for key, value in info.items() if isinstance(key, str) and isinstance(value, str)}


def binary_fields(info):
    """Preserve EXIF/ICC bytes, with JSON- and PNG-safe resolution values."""
    fields = {key: info[key] for key in ("exif", "icc_profile") if key in info}
    dpi = info.get("dpi")
    if isinstance(dpi, (tuple, list)) and len(dpi) == 2:
        try:
            # JPEG/TIFF EXIF resolutions can be Pillow IFDRational objects.
            # PNG stores unsigned 32-bit pixels/metre, not arbitrary DPI.
            values = tuple(float(value) for value in dpi)
            if all(not isinstance(value, (bool, str, bytes)) for value in dpi) and all(
                    math.isfinite(value) and 0 < value <= (2**32 - 1) * .0254 for value in values):
                fields["dpi"] = values
        except (TypeError, ValueError, OverflowError, ZeroDivisionError):
            pass  # Invalid optional resolution must not discard an edit.
    return fields


def build_metadata(source, recipe, parameters, keep_original=True):
    original = deepcopy(source.info) if keep_original else {}
    binary = binary_fields(original)
    history = None
    if keep_original:
        try:
            history = json.loads(original.get(HISTORY_KEY, "null"))
        except (ValueError, TypeError):
            pass
    if not isinstance(history, dict) or history.get("version") != 1 or not isinstance(history.get("edits"), list) or not isinstance(history.get("original_metadata"), dict):
        snapshot = text_fields(original)
        for key in ("exif", "icc_profile"):
            if isinstance(original.get(key), bytes):
                snapshot[key] = {"encoding": "base64", "data": base64.b64encode(original[key]).decode("ascii")}
        if "dpi" in binary:
            snapshot["dpi"] = binary["dpi"]
        history = {"version": 1, "original_metadata": snapshot, "edits": []}
    history["edits"].append({"parameters": parameters, "recipe": recipe})
    original_parameters = history["original_metadata"].get("parameters", "")
    combined = parameters
    if isinstance(original_parameters, str) and original_parameters:
        sections = [original_parameters]
        sections.extend(f"--- Image Edit {index + 1} ---\n{edit['parameters']}" for index, edit in enumerate(history["edits"]) if isinstance(edit, dict) and isinstance(edit.get("parameters"), str))
        combined = "\n\n".join(sections)
    fields = text_fields(original)
    fields.update({"parameters": combined, "image_edit": json.dumps(recipe, ensure_ascii=False),
                   HISTORY_KEY: json.dumps(history, ensure_ascii=False)})
    # The original recipe remains in history; these top-level keys mean latest edit.
    fields.pop("qwen_edit", None)
    if recipe["model_family"] == "Qwen Image 2.1":
        fields["qwen_edit"] = fields["image_edit"]
    return fields, binary


def preserve_binary_metadata(path, binary):
    """Forge's saver owns naming/callbacks; retain extra PNG metadata afterwards.

    Works with unmodified Forge savers that do not forward EXIF/ICC options.
    The replacement is atomic and confined to the file returned by save_image.
    """
    binary = binary_fields(binary)
    if not binary:
        return
    path = Path(path)
    with Image.open(path) as saved:
        image = saved.copy()
        metadata = PngInfo()
        for key, value in text_fields(saved.info).items():
            metadata.add_text(key, value)
    descriptor, temporary = tempfile.mkstemp(prefix=".image-edit-", suffix=".png", dir=path.parent)
    os.close(descriptor)
    try:
        image.save(temporary, format="PNG", pnginfo=metadata, **binary)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
