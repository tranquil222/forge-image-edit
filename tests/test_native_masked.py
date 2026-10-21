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
from forge_qwen_edit.masking import canonical_image, composite_patch, context_box, editor_value, extract_mask, location_guide, scoped_instruction, fibo_masked_reference, fibo_masked_instruction, camera_angle_instruction
from forge_qwen_edit.workflow import QUALITY_PRESETS, fibo_result_prompt, image_digest, parse_seed, prepare_reference, reference_content_box
from forge_qwen_edit.adapters import get_adapter
from forge_qwen_edit.metadata import build_metadata, preserve_binary_metadata
from forge_qwen_edit.selection import validate_components
from forge_qwen_edit.tone import match_source_tone, tone_summary
from forge_qwen_edit.adjustments import MASK_KEY, encode_selection, remember_selection, result_context
from forge_qwen_edit.fibo_defaults import apply_default as apply_fibo_default
from forge_qwen_edit.outpaint import canvas_plan, canvas_images, outpaint_instruction


class NativeMaskedTests(unittest.TestCase):
    def test_replace_hides_original_content_and_records_crop_recipe(self):
        self.check_masked_job("Replace / remove")

    def test_refine_keeps_clean_reference_and_records_crop_recipe(self):
        self.check_masked_job("Refine / expression")

    def test_fibo_uses_own_components_shift_and_recipe(self):
        self.check_masked_job("Replace / remove", "Fibo 2.0 Edit Turbo")

    def test_masked_output_drops_original_metadata_when_disabled(self):
        self.check_masked_job("Replace / remove", "Fibo 2.0 Edit Turbo", False)

    def test_tone_option_keeps_mask_boundary_and_records_recipe(self):
        self.check_masked_job("Replace / remove", "Fibo 2.0 Edit Turbo", preserve_tone=True)

    def test_camera_uses_clean_full_scene_and_records_reusable_preset(self):
        for family in ("Qwen Image 2.1", "Fibo 2.0 Edit Turbo"):
            with self.subTest(family=family):
                self.check_masked_job("Camera angle", family)

    def test_outpaint_uses_full_canvas_model_border_and_keeps_retained_pixels(self):
        for family in ("Qwen Image 2.1", "Fibo 2.0 Edit Turbo"):
            with self.subTest(family=family):
                self.check_masked_job("Outpaint", family)

    def check_masked_job(self, mode, family="Qwen Image 2.1", keep_metadata=True, preserve_tone=False):
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
                apply_default=lambda image, key, area, recipe: apply_fibo_default(image, key, area, recipe, root / "curves.json"),
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
            camera = mode == "Camera angle"
            edges = {"left": -32, "right": 80, "top": 24, "bottom": -20} if mode == "Outpaint" else None
            instruction = "Move the camera near the ground looking up at the subject." if camera else "Remove the stray object."
            output, filename, seed, message = namespace["generate"](
                source, None, None, instruction, "", 512, 4 if fibo else 8, "-1", "Euler" if fibo else "Res Multistep", schedule, model_name, encoder_name, vae_name, True, not camera, editor, 8, mode, family, "", keep_metadata, preserve_tone=preserve_tone, canvas_edges=edges)
            if edges is not None:
                plan = canvas_plan(source.size, edges)
                expanded, border = canvas_images(source, plan)
                self.assertEqual(output.size, (688, 424))
                retained = np.array(border) == 0
                np.testing.assert_array_equal(np.array(output)[retained], np.array(expanded)[retained])
                np.testing.assert_array_equal(np.array(output)[~retained], np.tile([180, 20, 50, 255], ((~retained).sum(), 1)))
                reference = fibo_masked_reference(expanded, border) if fibo else location_guide(expanded, border, opaque=True)
                self.assertEqual(len(calls[0].edit_references), 1)
                self.assertEqual(image_digest(calls[0].edit_references[0]), image_digest(prepare_reference(reference, 512)))
                with Image.open(filename) as saved:
                    recipe = json.loads(saved.info['image_edit'])
                    self.assertEqual(recipe['canvas'], plan)
                    self.assertEqual(recipe['edit_mode'], 'Outpaint')
                    self.assertEqual(recipe['masked_edit']['feather'], 0)
                    self.assertEqual(recipe['masked_edit']['crop'], [0, 0, 688, 424])
                    self.assertNotIn('fibo_global_curves', recipe)
                    _, selected, _ = result_context(filename, __import__('hashlib').sha256(Path(filename).read_bytes()).hexdigest())
                    np.testing.assert_array_equal(np.array(selected), np.array(border))
                return
            if camera:
                clean = prepare_reference(source, 512)
                box = reference_content_box(*source.size, 512)
                self.assertEqual(output.size, (box[2] - box[0], box[3] - box[1]))
                self.assertEqual(len(calls[0].edit_references), 1)
                self.assertEqual(image_digest(calls[0].edit_references[0]), image_digest(clean))
                self.assertIn(instruction, calls[0].prompt)
                self.assertEqual(calls[0].prompt, camera_angle_instruction(instruction, fibo))
                from forge_qwen_edit.workflow import read_recipe
                recipe = read_recipe(filename)
                self.assertEqual(recipe["edit_mode"], "Camera angle")
                self.assertEqual(recipe["prompt"], instruction)
                self.assertEqual(recipe["effective_prompt"], calls[0].prompt)
                self.assertFalse(recipe["area_only"])
                self.assertNotIn("masked_edit", recipe)
                with Image.open(filename) as saved:
                    self.assertNotIn(MASK_KEY, saved.info)
                with self.assertRaisesRegex(ValueError, "whole scene"):
                    namespace["generate"](source, None, None, instruction, "", 512, 4 if fibo else 8, "-1", "Euler" if fibo else "Res Multistep", schedule, model_name, encoder_name, vae_name, True, True, editor, 8, mode, family)
                return
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
                self.assertEqual(recipe["preserve_tone"], preserve_tone)
                self.assertEqual("tone_match" in recipe, preserve_tone)
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
                _, saved_mask, _ = result_context(filename, __import__('hashlib').sha256(Path(filename).read_bytes()).hexdigest())
                self.assertIsNotNone(saved_mask)
                self.assertIn(MASK_KEY, saved.info)
                np.testing.assert_array_equal(np.array(saved_mask)[outside], 0)


if __name__ == "__main__":
    unittest.main()
