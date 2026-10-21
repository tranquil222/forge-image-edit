"""Edit-model registry shared by the UI, job runner and PNG recipes.

New architectures register their own components/defaults here and conditioning
adapter in native.py; checkpoints are never treated as interchangeable.
"""
from dataclasses import dataclass

from .workflow import DEFAULT_ENCODER, DEFAULT_MODEL, DEFAULT_VAE, QUALITY_PRESETS, SCHEDULES


@dataclass(frozen=True)
class EditModel:
    label: str
    key: str
    flag: str
    defaults: tuple
    profiles: dict
    default_profile: str
    schedules: tuple
    shift: float
    prefix_cache: bool
    guidance: float = 1.0

    @property
    def samplers(self):
        return ("Euler",) if self.key == "fibo2" else ("Res Multistep", "Euler")

    def accepts(self, name, component="model"):
        name = name.replace("\\", "/").rsplit("/", 1)[-1].lower()
        if component == "model" and any(token in name for token in ("vae", "qwen3vl", "qwen3-vl")):
            return False
        if self.key == "fibo2":
            if component == "model":
                variant = "dev" if self.guidance > 1 else "turbo"
                return "fibo" in name and variant in name and (variant == "dev" or "edit" in name)
            if component == "encoder":
                return any(s in name for s in ("qwen3vl", "qwen3-vl")) and "4b" in name
            return "flux2" in name and "vae" in name
        if component == "encoder":
            return any(s in name for s in ("qwen3vl", "qwen3-vl")) and "8b" in name
        return "qwen" in name and any(s in name for s in ("2.1", "21")) and (component != "vae" or "vae" in name)


EDIT_MODELS = {
    "Qwen Image 2.1": EditModel(
        "Qwen Image 2.1", "qwen21", "qwen21", (DEFAULT_MODEL, DEFAULT_ENCODER, DEFAULT_VAE),
        QUALITY_PRESETS, "Normal", SCHEDULES, .69, True),
    "Fibo 2.0 Edit Turbo": EditModel(
        "Fibo 2.0 Edit Turbo", "fibo2", "fibo2",
        ("fibo2_edit_turbo_int8_convrot.safetensors", "qwen3vl_4b_int8_convrot.safetensors", "flux2-vae.safetensors"),
        {"Turbo (4 steps)": {"steps": 4, "sampler": "Euler", "schedule": "Simple", "prefix_cache": False}},
        "Turbo (4 steps)", ("Simple",), 1.15, False),
    "Fibo 2.0 Dev": EditModel(
        "Fibo 2.0 Dev", "fibo2", "fibo2",
        ("fibo2_dev_int8_convrot.safetensors", "qwen3vl_4b_int8_convrot.safetensors", "flux2-vae.safetensors"),
        {"Standard (50 steps)": {"steps": 50, "sampler": "Euler", "schedule": "Simple", "prefix_cache": False},
         "Preview (30 steps)": {"steps": 30, "sampler": "Euler", "schedule": "Simple", "prefix_cache": False}},
        "Standard (50 steps)", ("Simple",), 1.15, False, 5.0),
}
DEFAULT_FAMILY = "Qwen Image 2.1"


def get_adapter(family=DEFAULT_FAMILY):
    try:
        return EDIT_MODELS[family]
    except KeyError:
        raise ValueError(f"Unsupported edit model: {family}. Choose a model from the Image Edit selector.") from None
