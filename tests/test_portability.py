import json
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image
from PIL.PngImagePlugin import PngInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from forge_qwen_edit.adapters import get_adapter
from forge_qwen_edit.masking import fibo_masked_reference, fibo_masked_instruction
from forge_qwen_edit.metadata import HISTORY_KEY, build_metadata, preserve_binary_metadata
from forge_qwen_edit.selection import adapter_for_checkpoint, suggested_components, validate_components, profiles_for
from forge_qwen_edit.workflow import fibo_result_prompt, read_recipe, validate_recipe


class PortabilityTests(unittest.TestCase):
    def test_gray_threshold_and_untouched_pixels(self):
        source = Image.new("RGB", (3, 1), (12, 34, 56))
        mask = Image.new("L", source.size)
        mask.putdata([0, 127, 128])
        self.assertEqual([fibo_masked_reference(source, mask).getpixel((x, 0)) for x in range(3)], [(12, 34, 56), (12, 34, 56), (128, 128, 128)])
        with self.assertRaisesRegex(ValueError, "50%"):
            fibo_masked_reference(source, Image.new("L", source.size, 127))

    def test_structured_mask_instruction_keeps_caption(self):
        prompt = fibo_result_prompt("remove the toy", "an empty bed")
        parsed = json.loads(fibo_masked_instruction(prompt))
        self.assertEqual(parsed["structured_caption"]["short_description"], "an empty bed")
        self.assertIn("<image_1>", parsed["edit_instruction"])
        with self.assertRaisesRegex(ValueError, "not both"):
            fibo_result_prompt(prompt, "another caption")

    def test_components_in_custom_paths_reject_wrong_extra_and_missing(self):
        adapter = get_adapter("Fibo 2.0 Edit Turbo")
        with tempfile.TemporaryDirectory(prefix="custom model location ") as temporary:
            available = {}
            for name in (*adapter.defaults[1:], "qwen_image_vae.safetensors", "qwen3vl_8b_bf16.safetensors"):
                path = Path(temporary) / name
                path.touch()
                available[name] = str(path)
            pair = suggested_components(adapter, [], available)
            self.assertEqual(validate_components(adapter, pair, available), adapter.defaults[1:])
            for invalid in (pair + ["qwen_image_vae.safetensors"], [pair[0], "qwen_image_vae.safetensors"], ["qwen3vl_8b_bf16.safetensors", pair[1]]):
                with self.assertRaisesRegex(ValueError, "Required"):
                    validate_components(adapter, invalid, available)
            Path(available[pair[1]]).unlink()
            with self.assertRaisesRegex(ValueError, "Missing vae"):
                suggested_components(adapter, [], available)

    def test_turbo_never_offers_base_quality_presets(self):
        adapter = get_adapter("Qwen Image 2.1")
        self.assertEqual(profiles_for(adapter, "qwen_image_2.1_turbo.safetensors"), ["Turbo (8 steps)"])
        self.assertNotIn("Turbo (8 steps)", profiles_for(adapter, "qwen_image_2.1.safetensors"))

    def test_smaller_quants_keep_selected_encoder_and_turbo_schedule(self):
        checkpoint = "qwen_image_2.1_turbo_Q4_K_M.gguf"
        adapter = adapter_for_checkpoint(checkpoint)
        self.assertEqual(adapter.key, "qwen21")
        self.assertEqual(profiles_for(adapter, checkpoint), ["Turbo (8 steps)"])
        with tempfile.TemporaryDirectory() as temporary:
            available = {}
            for name in (*adapter.defaults[1:], "qwen3vl_8b_w4a8.safetensors", "qwen3vl_4b_int8_convrot.safetensors"):
                path = Path(temporary) / name
                path.touch()
                available[name] = str(path)
            selected = ["qwen3vl_8b_w4a8.safetensors", adapter.defaults[2]]
            self.assertEqual(suggested_components(adapter, selected, available), selected)
            self.assertEqual(validate_components(adapter, selected, available), tuple(selected))
            with self.assertRaisesRegex(ValueError, "Required"):
                validate_components(adapter, ["qwen3vl_4b_int8_convrot.safetensors", selected[1]], available)

    def test_dev_uses_separate_guidance_defaults_and_recipe_validation(self):
        adapter = adapter_for_checkpoint("fibo2_dev_int8_convrot.safetensors")
        self.assertEqual(adapter.guidance, 5)
        self.assertEqual(adapter.profiles[adapter.default_profile]["steps"], 50)
        self.assertFalse(adapter.accepts("fibo2_edit_turbo_int8_convrot.safetensors"))
        recipe = dict(prompt="edit", model_family=adapter.label, cfg=5, seed="42", steps=50, resolution=1024, sampler="Euler", schedule="Simple")
        self.assertEqual(validate_recipe(recipe)["cfg"], 5)
        recipe["model_family"] = "Fibo 2.0 Edit Turbo"
        with self.assertRaisesRegex(ValueError, "CFG"):
            validate_recipe(recipe)

    def test_metadata_append_toggle_and_png_roundtrip(self):
        source = Image.new("RGB", (16, 16))
        source.info.update(parameters="original prompt\nSteps: 20, Seed: 123", Author="test author", icc_profile=b"test-profile")
        recipe = dict(version=1, model_family="Fibo 2.0 Edit Turbo", prompt="remove toy", steps=4, resolution=1024, seed="42", cfg=1, sampler="Euler", schedule="Simple")
        fields, binary = build_metadata(source, recipe, "remove toy\nSteps: 4, Seed: 42", True)
        self.assertEqual(fields["Author"], "test author")
        self.assertTrue(fields["parameters"].startswith(source.info["parameters"]))
        self.assertIn("--- Image Edit 1 ---", fields["parameters"])
        source.info.update(fields)
        appended, _ = build_metadata(source, recipe, "second edit", True)
        history = json.loads(appended[HISTORY_KEY])
        self.assertEqual(len(history["edits"]), 2)
        self.assertEqual(history["original_metadata"]["parameters"], "original prompt\nSteps: 20, Seed: 123")
        fresh, fresh_binary = build_metadata(source, recipe, "new parameters", False)
        self.assertNotIn("Author", fresh)
        self.assertEqual(fresh_binary, {})
        self.assertEqual(fresh["parameters"], "new parameters")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "edit.png"
            info = PngInfo()
            for key, value in fields.items():
                info.add_text(key, value)
            source.save(path, pnginfo=info)
            preserve_binary_metadata(path, binary)
            with Image.open(path) as saved:
                self.assertEqual(saved.info["icc_profile"], b"test-profile")
                self.assertEqual(read_recipe(saved)["prompt"], "remove toy")


if __name__ == "__main__":
    unittest.main()
