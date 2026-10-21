"""Persistent, opt-in RGB correction for unpainted Fibo results."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile

from .adjustments import apply_luts, parse_adjustment, result_context, result_recipe


def identity():
    return [list(range(256)) for _ in range(3)]


def compose(first, second):
    return [[second[c][value] for value in first[c]] for c in range(3)]


def config_path():
    from modules import shared
    return Path(shared.data_path) / "image-edit-curves.json"


def validate_preset(preset):
    return parse_adjustment(json.dumps(dict(version=1, base_sha256="0" * 64,
        settings=preset["settings"], luts=preset["luts"])))


def read_config(path=None):
    path = Path(path) if path is not None else config_path()
    if not path.exists():
        return {"version": 1, "enabled": False, "preset": None}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != 1 or type(data.get("enabled")) is not bool:
        raise ValueError("The saved Fibo curves preset could not be read.")
    if data.get("preset") is not None:
        validate_preset(data["preset"])
    return data


def write_config(data, path=None):
    path = Path(path) if path is not None else config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
            name = stream.name
            json.dump(data, stream, ensure_ascii=False)
        os.replace(name, path)
    finally:
        if name and Path(name).exists():
            Path(name).unlink()


def eligible(recipe):
    return recipe.get("model_family") in ("Fibo 2.0 Edit Turbo", "Fibo 2.0 Dev") and not recipe.get("area_only", False)


def baseline(recipe):
    tables = identity()
    previous = recipe.get("fibo_global_curves")
    if previous:
        tables = validate_preset(previous)["luts"]
    for adjustment in recipe.get("postprocessing", []):
        if adjustment.get("type") == "curves" and adjustment.get("scope") == "whole image":
            tables = compose(tables, validate_preset(adjustment)["luts"])
    return tables


def describe_default(recipe):
    config = read_config()
    return {"eligible": eligible(recipe), "enabled": config["enabled"],
            "available": config.get("preset") is not None,
            "can_capture": eligible(recipe) and baseline(recipe) != identity()}


def prepare_default(saved_path, payload):
    data = parse_adjustment(payload)
    source, mask, _ = result_context(saved_path, data["base_sha256"])
    recipe = result_recipe(source, data["base_sha256"])
    if mask is not None or not eligible(recipe):
        raise ValueError("Default curves are for unpainted Fibo results only.")
    config = read_config()
    enabled = data.get("enabled", True)
    if type(enabled) is not bool:
        raise ValueError("Invalid default curves selection.")
    if enabled:
        previous = baseline(recipe)
        # An already-corrected result starts with identity controls. Re-enabling
        # must not erase its preset or apply that correction a second time.
        if data["luts"] != identity() or config.get("preset") is None:
            tables = compose(previous, data["luts"])
            if tables == identity():
                raise ValueError("Adjust the curve or levels before saving a default.")
            config["preset"] = {"version": 1, "scope": "whole image", "luts": tables,
                                "settings": deepcopy(data["settings"])}
    config["enabled"] = enabled
    return config


def apply_default(image, family_key, area_only, recipe, path=None):
    if family_key != "fibo2" or area_only:
        return image
    config = read_config(path)
    if not config["enabled"] or not config.get("preset"):
        return image
    recipe["fibo_global_curves"] = deepcopy(config["preset"])
    return apply_luts(image, config["preset"]["luts"])
