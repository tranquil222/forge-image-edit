"""Exercise the production job/save path with a CPU stand-in for model inference."""
import ast
from contextlib import closing, nullcontext
from datetime import datetime
import json
from pathlib import Path
import secrets
import sys
import tempfile
from types import SimpleNamespace
import unittest

import numpy as np
from PIL import Image, ImageDraw
from PIL.PngImagePlugin import PngInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from forge_qwen_edit.masking import canonical_image, composite_patch, context_box, editor_value, extract_mask, location_guide, scoped_instruction, fibo_masked_reference, fibo_masked_instruction
from forge_qwen_edit.workflow import QUALITY_PRESETS, fibo_result_prompt, image_digest, parse_seed, prepare_reference
from forge_qwen_edit.adapters import get_adapter
from forge_qwen_edit.metadata import build_metadata, preserve_binary_metadata
from forge_qwen_edit.selection import validate_components


class NativeMaskedTests(unittest.TestCase):
    def test_replace_hides_original_content_and_records_crop_recipe(self):
        self.check_masked_job("Replace / remove")

    def test_refine_keeps_clean_reference_and_records_crop_recipe(self):
        self.check_masked_job("Refine / expression")

    def test_fibo_uses_own_components_shift_and_recipe(self):
        self.check_masked_job("Replace / remove", "Fibo 2.0 Edit Turbo")

    def test_masked_output_drops_original_metadata_when_disabled(self):
        self.check_masked_job("Replace / remove", "Fibo 2.0 Edit Turbo", False)

    def check_masked_job(self, mode, family="Qwen Image 2.1", keep_metadata=True):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            adapter = get_adapter(family)
            encoder_name, vae_name = adapter.defaults[1:]
            for name in (encoder_name, vae_name):
                (root / name).touch()
            calls = []

            class FakeProcessing:
                def __init__(self, **kwargs):
                    self.__dict__.update(kwargs)
                    calls.append(self)
                def close(self):
                    self.closed = True

            def inference(p):
                return SimpleNamespace(images=[Image.new("RGBA", (p.width, p.height), (180, 20, 50, 255))], infotexts=["test sampler"])

            fibo = family.startswith("Fibo")
            model_name = "fibo2_edit_turbo_int8_convrot.safetensors" if fibo else "qwen_image_2.1.safetensors"
            schedule = "Simple" if fibo else "CyberZit Quality"
            def native_save(image, path, basename, **kwargs):
                self.assertNotIn("Author", image.info)
                self.assertEqual(Path(path), root / "user-img2img")
                self.assertEqual(kwargs["extension"], "png")
                target = Path(path) / "native-name.png"
                target.parent.mkdir(parents=True, exist_ok=True)
                info = PngInfo()
                for key, value in kwargs["existing_info"].items():
                    info.add_text(key, value)
                image.save(target, pnginfo=info)
                return str(target), None

            namespace = dict(globals(), __version__="test", EditProcessing=FakeProcessing, EditCancelled=RuntimeError,
                isolated_options=lambda *args: nullcontext(),
                sd_samplers=SimpleNamespace(find_sampler_config=lambda name: True),
                sd_schedulers=SimpleNamespace(schedulers_map={schedule: True}),
                sd_models=SimpleNamespace(checkpoints_list={"model": SimpleNamespace(name=model_name)}),
                main_entry=SimpleNamespace(module_list={name: root / name for name in (encoder_name, vae_name)}),
                images=SimpleNamespace(save_image=native_save),
                shared=SimpleNamespace(opts=SimpleNamespace(outdir_samples="", outdir_img2img_samples=str(root / "user-img2img"), enable_pnginfo=True), data_path=root, state=SimpleNamespace(interrupted=False, skipped=False)),
                processing=SimpleNamespace(process_images=inference))
            tree = ast.parse((Path(__file__).resolve().parents[1] / "forge_qwen_edit/native.py").read_text())
            function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "generate")
            exec(compile(ast.Module(body=[function], type_ignores=[]), "production_generate", "exec"), namespace)
            source = Image.new("RGBA", (640, 420), (20, 40, 80, 200))
            source.info["Author"] = "original-author"
            editor = editor_value(source)
            layer = Image.new("RGBA", source.size)
            ImageDraw.Draw(layer).rectangle((200, 100, 290, 220), fill=(0, 255, 0, 255))
            editor["layers"] = [layer]
            output, filename, seed, message = namespace["generate"](
                source, None, None, "Remove the stray object.", "", 512, 4 if fibo else 8, "-1", "Euler" if fibo else "Res Multistep", schedule, model_name, encoder_name, vae_name, True, True, editor, 8, mode, family, "", keep_metadata)
            self.assertEqual(output.size, source.size)
            outside = np.array(layer)[..., 3] == 0
            np.testing.assert_array_equal(np.array(output)[outside], np.array(source)[outside])
            self.assertTrue(calls[0].closed)
            replace = mode == "Replace / remove"
            self.assertEqual(len(calls[0].edit_references), 1 if replace else 2)
            self.assertIn("<image_1>" if fibo else "<image1>" if replace else "<image2>", calls[0].prompt)
            self.assertEqual(calls[0].edit_family, family)
            self.assertEqual(calls[0].distilled_cfg_scale, 1.15 if fibo else .69)
            self.assertEqual(calls[0].edit_prefix_cache, not fibo)
            mask = extract_mask(source, editor)
            expected_first = fibo_masked_reference(source, mask) if fibo else location_guide(source, mask, opaque=True) if replace else source
            expected_first = prepare_reference(expected_first.crop(context_box(mask)), 512)
            self.assertEqual(image_digest(calls[0].edit_references[0]), image_digest(expected_first))
            self.assertGreaterEqual(int(seed), 0)
            with Image.open(filename) as saved:
                self.assertEqual("Author" in saved.info, keep_metadata)
                recipe = json.loads(saved.info["image_edit"])
                self.assertEqual(recipe["model_family"], family)
                self.assertEqual("qwen_edit" in saved.info, not fibo)
                self.assertTrue(recipe["area_only"])
                self.assertEqual(recipe["prompt"], "Remove the stray object.")
                self.assertEqual(recipe["output_size"], [640, 420])
                self.assertEqual(recipe["masked_edit"]["guide_reference"], 1 if replace else 2)
                self.assertEqual(recipe["masked_edit"]["clean_reference_sent"], not replace)
                self.assertEqual(recipe["masked_edit"]["mode"], "Fibo masked edit" if fibo else mode)
                if fibo:
                    self.assertEqual(recipe["masked_edit"]["mask_fill"], [128, 128, 128])
                self.assertEqual(recipe["source_sha256"], image_digest(source))


if __name__ == "__main__":
    unittest.main()
