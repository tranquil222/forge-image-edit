import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from PIL.PngImagePlugin import PngInfo

from forge_qwen_edit import adjustments as A, fibo_defaults as F


def settings():
    return {c: {"points": [[0, 0], [255, 255]], "levels": [0, 1, 255, 0, 255]}
            for c in ("rgb", "red", "green", "blue")}


class FiboDefaultTests(unittest.TestCase):
    def test_default_gating_alpha_and_record(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "curves.json"
            preset = {"settings": settings(), "luts": [[min(n + 20, 255) for n in range(256)]] * 3}
            F.write_config({"version": 1, "enabled": True, "preset": preset}, path)
            image = Image.new("RGBA", (10, 12), (60, 90, 120, 87))
            for key, masked in (("qwen21", False), ("fibo2", True)):
                recipe = {}
                self.assertIs(F.apply_default(image, key, masked, recipe, path), image)
                self.assertEqual(recipe, {})
            recipe = {}
            output = F.apply_default(image, "fibo2", False, recipe, path)
            self.assertEqual(output.getpixel((0, 0)), (80, 110, 140, 87))
            self.assertEqual(recipe["fibo_global_curves"], preset)
            self.assertTrue(F.eligible({"model_family": "Fibo 2.0 Dev"}))
            self.assertTrue(F.eligible({"model_family": "Fibo 2.0 Edit Turbo"}))
            self.assertFalse(F.eligible({"model_family": "Qwen Image 2.1"}))
            F.write_config({"version": 1, "enabled": False, "preset": preset}, path)
            self.assertIs(F.apply_default(image, "fibo2", False, {}, path), image)

    def test_refinement_composes_existing_default_and_manual_curves_once(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); config = root / "curves.json"; image_path = root / "result.png"
            a = [[min(n + 20, 255) for n in range(256)]] * 3
            b = [[max(n - 5, 0) for n in range(256)]] * 3
            c = [[round(n * .9) for n in range(256)]] * 3
            recipe = {"model_family": "Fibo 2.0 Edit Turbo", "area_only": False,
                "fibo_global_curves": {"settings": settings(), "luts": a},
                "postprocessing": [{"type": "curves", "scope": "whole image", "settings": settings(), "luts": b}]}
            info = PngInfo(); info.add_text("image_edit", json.dumps(recipe))
            Image.new("RGB", (8, 9)).save(image_path, pnginfo=info)
            digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
            payload = {"version": 1, "id": "test", "base_sha256": digest, "settings": settings(), "luts": c, "enabled": True}
            with patch.object(F, "config_path", return_value=config):
                saved = F.prepare_default(image_path, json.dumps(payload)); F.write_config(saved)
                expected = F.compose(F.compose(a, b), c)
                self.assertEqual(saved["preset"]["luts"], expected)
                self.assertEqual(expected[0][60], 68)
                # Disabling and re-enabling identity controls preserves the saved LUT.
                payload.update(enabled=False, luts=F.identity())
                F.write_config(F.prepare_default(image_path, json.dumps(payload)))
                self.assertFalse(F.read_config()["enabled"])
                payload["enabled"] = True
                saved = F.prepare_default(image_path, json.dumps(payload)); F.write_config(saved)
                self.assertEqual(saved["preset"]["luts"], expected)
                self.assertTrue(F.read_config()["enabled"])
                state = A.describe_result(image_path, json.dumps(payload))["fibo_default"]
                self.assertTrue(state["eligible"] and state["available"] and state["enabled"])
                # Identity/current preview must not get the old correction again.
                self.assertEqual(F.baseline(recipe), F.compose(a, b))

    def test_metadata_disabled_stays_eligible_in_session_and_bad_presets_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); image_path = root / "result.png"; config = root / "curves.json"
            Image.new("RGB", (8, 9)).save(image_path)
            A.remember_selection(image_path, None, {"model_family": "Fibo 2.0 Dev", "area_only": False})
            digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
            payload = {"version": 1, "id": "test", "base_sha256": digest, "settings": settings(),
                       "luts": [[255 - n for n in range(256)]] * 3}
            with patch.object(F, "config_path", return_value=config):
                F.write_config(F.prepare_default(image_path, json.dumps(payload)))
                self.assertTrue(F.read_config()["enabled"])
                source, _, _ = A.result_context(image_path, digest)
                _, _, recipe = A.adjustment_metadata(source, payload, False)
                self.assertEqual(recipe["model_family"], "Fibo 2.0 Dev")
                self.assertEqual(recipe["postprocessing"][0]["luts"], payload["luts"])
                payload["luts"][0][0] = 256
                with self.assertRaises(ValueError): F.prepare_default(image_path, json.dumps(payload))
                A.remember_selection(image_path, None, {"model_family": "Qwen Image 2.1"})
                payload["luts"][0][0] = 255
                with self.assertRaisesRegex(ValueError, "unpainted Fibo"):
                    F.prepare_default(image_path, json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
