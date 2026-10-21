"""Non-destructive, per-upload reference tone adjustments."""
from copy import deepcopy

from .adjustments import apply_luts, parse_adjustment

UPLOAD_DIGEST = "_image_edit_upload_sha256"
CURVES_RECORD = "_image_edit_reference_curves"


def adjust_reference(image, payload):
    if not payload:
        return image
    if image is None:
        raise ValueError("The adjusted reference was removed. Load a reference image first.")
    data = parse_adjustment(payload)
    if data["base_sha256"] != image.info.get(UPLOAD_DIGEST):
        raise ValueError("The reference image changed. Reopen its Edit controls before generating.")
    result = apply_luts(image, data["luts"])
    result.info = image.info.copy()
    result.info[CURVES_RECORD] = deepcopy({key: data[key] for key in ("version", "base_sha256", "settings", "luts")})
    return result


def reference_adjustment_records(references):
    return [{"slot": index, **deepcopy(image.info[CURVES_RECORD])}
            for index, image in enumerate(references, 2)
            if image is not None and CURVES_RECORD in image.info]
