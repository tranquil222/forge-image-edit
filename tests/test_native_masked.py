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
from forge_qwen_edit.workflow import output_resize_size, prepare_sized_reference
from forge_qwen_edit.adapters import get_adapter
from forge_qwen_edit.sampling import validate_fibo_sampling, resolve_fibo_shift, FIBO_ROPE_X, FIBO_ROPE_Y
from forge_qwen_edit.sampling import validate_qwen_sampling, resolve_qwen_shift, qwen_schedule_override, DEFAULT_QWEN_SHIFT, QWEN_ROPE_X, QWEN_ROPE_Y
from forge_qwen_edit.metadata import build_metadata, preserve_binary_metadata
from forge_qwen_edit.selection import validate_components
from forge_qwen_edit.tone import match_source_tone, tone_summary
from forge_qwen_edit.adjustments import MASK_KEY, encode_selection, remember_selection, result_context
from forge_qwen_edit.fibo_defaults import apply_default as apply_fibo_default
from forge_qwen_edit.outpaint import canvas_plan, canvas_images, canvas_blend_mask, canvas_reference_resolution, outpaint_instruction
from forge_qwen_edit.masking import masked_reference_instruction, expression_transfer_instruction
from forge_qwen_edit.reference_adjustments import adjust_reference, reference_adjustment_records, UPLOAD_DIGEST


class NativeMaskedTests(unittest.TestCase):
    def test_reference_guidance_keeps_structured_fibo_caption(self):
        original = {'edit_instruction': 'Use the architecture from <image_2>.', 'structured_caption': {'short_description': 'a stone courtyard'}}
        result = json.loads(masked_reference_instruction(json.dumps(original), True, 2))
        self.assertEqual(result['structured_caption'], original['structured_caption'])
        self.assertTrue(result['edit_instruction'].startswith(original['edit_instruction']))
        self.assertIn('<image_2>, <image_3>', result['edit_instruction'])

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

    def test_expression_uses_clean_base_and_preserves_masked_pixels(self):
        for family in ("Qwen Image 2.1", "Fibo 2.0 Edit Turbo"):
            for painted in (False, True):
                for gap in (False, True):
                    with self.subTest(family=family, painted=painted, gap=gap):
                        self.check_masked_job("Expression transfer", family, extra_refs=True,
                            expression_painted=painted, reference_gap=gap)

    def test_expression_requires_a_reference_before_inference(self):
        self.check_masked_job("Expression transfer", "Fibo 2.0 Edit Turbo")

    def test_outpaint_uses_full_canvas_model_border_and_keeps_retained_pixels(self):
        for family in ("Qwen Image 2.1", "Fibo 2.0 Edit Turbo"):
            with self.subTest(family=family):
                self.check_masked_job("Outpaint", family, canvas_paint=False)

    def test_outpaint_paint_and_seam_composite_share_exact_selection(self):
        for family in ("Qwen Image 2.1", "Fibo 2.0 Edit Turbo"):
            with self.subTest(family=family):
                self.check_masked_job("Outpaint", family, canvas_paint=True)

    def test_painted_canvas_can_crop_or_keep_size_without_expansion(self):
        for edges in ({}, {'left': -32, 'bottom': -20}):
            for family in ("Qwen Image 2.1", "Fibo 2.0 Edit Turbo"):
                with self.subTest(edges=edges, family=family):
                    self.check_masked_job("Outpaint", family, canvas_paint=True, canvas_edges=edges)

    def test_shrunk_canvas_is_sent_small_and_saved_small_for_both_models(self):
        for family in ("Qwen Image 2.1", "Fibo 2.0 Edit Turbo"):
            for edges in ({"left": -32, "right": 80, "top": 24, "shrink_by": 2}, {"shrink_by": 1.5}):
                with self.subTest(family=family, edges=edges):
                    self.check_masked_job("Outpaint", family, canvas_paint=True, canvas_edges=edges)

    def test_extra_references_reach_both_models_for_paint_and_outpaint(self):
        for family in ("Qwen Image 2.1", "Fibo 2.0 Edit Turbo"):
            for mode in ("Replace / remove", "Outpaint"):
                with self.subTest(family=family, mode=mode):
                    self.check_masked_job(mode, family, canvas_paint=True, extra_refs=True)

    def test_adjusted_references_reach_inference_for_global_paint_and_outpaint(self):
        for family in ("Qwen Image 2.1", "Fibo 2.0 Edit Turbo"):
            for mode in ("Camera angle", "Replace / remove", "Outpaint"):
                with self.subTest(family=family, mode=mode):
                    self.check_masked_job(mode, family, canvas_paint=True, extra_refs=True, adjust_refs=True)

    def test_sampling_controls_reach_jobs_and_pngs_without_affecting_qwen(self):
        for family in ("Fibo 2.0 Edit Turbo", "Qwen Image 2.1"):
            for mode in ("Camera angle", "Replace / remove", "Outpaint"):
                for shift_mode in ("Manual", "Image-size adjusted"):
                    with self.subTest(family=family, mode=mode, shift_mode=shift_mode):
                        self.check_masked_job(mode, family, fibo_shift_mode=shift_mode, fibo_shift=.75, fibo_rope=True)

    def test_exact_output_size_drives_inference_and_saved_png_for_both_models(self):
        for family in ("Qwen Image 2.1", "Fibo 2.0 Edit Turbo"):
            for resize in (dict(mode='Resize to', width=801, height=526), dict(mode='Resize by', scale=1.5)):
                with self.subTest(family=family, resize=resize):
                    self.check_masked_job('Camera angle', family, output_resize=resize, extra_refs=True, fibo_shift_mode='Image-size adjusted')

    def test_shared_canvas_resize_drives_model_and_saved_size_with_paint_and_references(self):
        for family in ("Qwen Image 2.1", "Fibo 2.0 Edit Turbo"):
            for resize in (dict(mode='Resize to', width=901, height=526), dict(mode='Resize by', scale=.5), dict(mode='Resize by', scale=1.5)):
                with self.subTest(family=family, resize=resize):
                    self.check_masked_job('Outpaint', family, canvas_paint=True, extra_refs=True, fibo_rope=True,
                        canvas_edges=dict(right=80, output_resize=resize))

    def test_qwen_shift_and_rope_reach_global_painted_and_outpaint_jobs(self):
        for mode in ('Camera angle', 'Replace / remove', 'Outpaint'):
            for shift_mode in ('Manual', 'Image-size adjusted'):
                with self.subTest(mode=mode, shift_mode=shift_mode):
                    self.check_masked_job(mode, qwen_shift_mode=shift_mode, qwen_shift=.85, qwen_rope=True)

    def test_custom_component_roles_reach_job_and_png_for_both_models(self):
        for family in ("Qwen Image 2.1", "Fibo 2.0 Edit Turbo"):
            with self.subTest(family=family):
                self.check_masked_job("Camera angle", family, custom_components=True)

    def check_masked_job(self, mode, family="Qwen Image 2.1", keep_metadata=True, preserve_tone=False, canvas_paint=False, canvas_edges=None, extra_refs=False, adjust_refs=False, expression_painted=False, reference_gap=False, fibo_shift_mode="Manual", fibo_shift=1.15, fibo_rope=False, output_resize=None, qwen_shift_mode="Manual", qwen_shift=.69, qwen_rope=False, custom_components=False):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            adapter = get_adapter(family)
            encoder_name, vae_name = adapter.defaults[1:]
            if custom_components:
                encoder_name, vae_name = 'custom-encoder.safetensors', 'custom-decoder.safetensors'
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
                sd_schedulers=SimpleNamespace(schedulers_map={schedule: SimpleNamespace(function=lambda **kw: np.linspace(1, 0, kw['n']+1))}),
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
            expression = mode == "Expression transfer"
            edges = (canvas_edges if canvas_edges is not None else {"left": -32, "right": 80, "top": 24, "bottom": -20}) if mode == "Outpaint" else None
            instruction = "Move the camera near the ground looking up at the subject." if camera else "Remove the stray object."
            extras = [Image.new('RGB', (320, 240), (155, 90, 40)), Image.new('RGB', (240, 320), (20, 180, 60))] if extra_refs else [None, None]
            if expression:
                instruction = "Transfer the sneer." if expression_painted else ""
                if reference_gap:
                    extras[0] = None
                if not extra_refs:
                    with self.assertRaisesRegex(ValueError, "additional reference image"):
                        namespace["generate"](source, None, None, "", "", 512, 4, "-1", "Euler", schedule, model_name, encoder_name, vae_name, True, area_mode=mode, model_family=family)
                    self.assertEqual(calls, [])
                    return
            curves = None
            if adjust_refs:
                from test_adjustments import payload
                extras[0].info[UPLOAD_DIGEST] = 'a' * 64
                extras[1].info[UPLOAD_DIGEST] = 'b' * 64
                curves = [json.dumps(payload('a' * 64)), json.dumps(payload('b' * 64))]
            output, filename, seed, message = namespace["generate"](
                source, *extras, instruction, "", 512, 4 if fibo else 8, "-1", "Euler" if fibo else "Res Multistep", schedule, model_name, encoder_name, vae_name, True, expression_painted if expression else (not camera and (edges is None or canvas_paint)), editor, 8, mode, family, "", keep_metadata, preserve_tone=preserve_tone, canvas_edges=edges, reference_curves=curves, fibo_shift_mode=fibo_shift_mode, fibo_shift=fibo_shift, fibo_rope=fibo_rope, output_resize=output_resize, qwen_shift_mode=qwen_shift_mode, qwen_shift=qwen_shift, qwen_rope=qwen_rope, custom_components=custom_components)
            expected_shift = resolve_fibo_shift(fibo_shift_mode, fibo_shift, calls[0].width, calls[0].height) if fibo else resolve_qwen_shift(qwen_shift_mode, qwen_shift, calls[0].width, calls[0].height)
            self.assertEqual(calls[0].distilled_cfg_scale, expected_shift)
            self.assertEqual(calls[0].edit_fibo_rope, fibo and fibo_rope)
            self.assertEqual(calls[0].edit_qwen_rope, not fibo and qwen_rope)
            with Image.open(filename) as saved:
                sampling_recipe = json.loads(saved.info['image_edit'])
            self.assertEqual(sampling_recipe['custom_components'], custom_components)
            self.assertEqual(sampling_recipe['encoder'], encoder_name)
            self.assertEqual(sampling_recipe['vae'], vae_name)
            if fibo:
                self.assertEqual(sampling_recipe['fibo_shift_effective'], expected_shift)
                self.assertEqual(sampling_recipe['fibo_shift_mode'], fibo_shift_mode)
                self.assertEqual(sampling_recipe['fibo_shift'], fibo_shift)
                self.assertEqual(sampling_recipe['fibo_rope'], fibo_rope)
                if fibo_rope:
                    self.assertEqual(sampling_recipe['fibo_rope_scale'], {'x': .85, 'y': .8})
            else:
                self.assertNotIn('fibo_rope', sampling_recipe)
                self.assertEqual(sampling_recipe['qwen_shift_effective'], expected_shift)
                self.assertEqual(sampling_recipe['qwen_rope'], qwen_rope)
                if expected_shift != .69:
                    self.assertTrue(callable(calls[0].sampler_noise_scheduler_override))
                    self.assertNotEqual(calls[0].sampler_noise_scheduler_override(8)[4], .5)
                else:
                    self.assertFalse(hasattr(calls[0], 'sampler_noise_scheduler_override'))
            if expression:
                from forge_qwen_edit.workflow import read_recipe
                recipe = read_recipe(filename)
                self.assertEqual(recipe['edit_mode'], mode)
                self.assertEqual(recipe['area_only'], expression_painted)
                self.assertEqual(recipe['effective_prompt'], expression_transfer_instruction(recipe['prompt'], fibo))
                expected_source = source.crop(context_box(extract_mask(source, editor))) if expression_painted else source
                self.assertEqual(image_digest(calls[0].edit_references[0]), image_digest(prepare_reference(expected_source, 512)))
                filled = [im for im in extras if im is not None]
                self.assertEqual(len(calls[0].edit_references), 1 + len(filled))
                for actual, extra in zip(calls[0].edit_references[1:], filled):
                    self.assertEqual(image_digest(actual), image_digest(prepare_reference(extra, 512)))
                self.assertNotIn('neutral-grey', calls[0].prompt)
                if expression_painted:
                    self.assertEqual(output.size, source.size)
                    outside = np.array(layer)[..., 3] == 0
                    np.testing.assert_array_equal(np.array(output)[outside], np.array(source)[outside])
                    self.assertTrue(recipe['masked_edit']['clean_reference_sent'])
                    self.assertIsNone(recipe['masked_edit']['guide_reference'])
                    self.assertNotIn('mask_fill', recipe['masked_edit'])
                    _, saved_mask, _ = result_context(filename, __import__('hashlib').sha256(Path(filename).read_bytes()).hexdigest())
                    self.assertIsNotNone(saved_mask)
                else:
                    box = reference_content_box(*source.size, 512)
                    self.assertEqual(output.size, (box[2] - box[0], box[3] - box[1]))
                    self.assertNotIn('masked_edit', recipe)
                return
            if extra_refs:
                self.assertEqual(len(calls[0].edit_references), 3)
                expected_extras = [adjust_reference(im, data) for im, data in zip(extras, curves)] if curves else extras
                for actual, extra in zip(calls[0].edit_references[1:], expected_extras):
                    self.assertEqual(image_digest(actual), image_digest(prepare_reference(extra, 512)))
                if not camera:
                    self.assertIn('<image_2>' if fibo else 'image 2', calls[0].prompt)
                    self.assertIn('not a collage', calls[0].prompt)
                if adjust_refs:
                    self.assertEqual(extras[0].getpixel((0, 0)), (155, 90, 40))
                    self.assertEqual(extras[1].getpixel((0, 0)), (20, 180, 60))
                    with Image.open(filename) as saved:
                        self.assertEqual(json.loads(saved.info['image_edit'])['reference_adjustments'], reference_adjustment_records(expected_extras))
            if edges is not None:
                plan = canvas_plan(source.size, edges)
                expanded, hard = canvas_images(source, plan, extract_mask(source, editor) if canvas_paint else None)
                border = canvas_blend_mask(hard, plan)
                self.assertEqual(output.size, tuple(plan['output_size']))
                retained = np.array(border) == 0
                np.testing.assert_array_equal(np.array(output)[retained], np.array(expanded)[retained])
                generated = Image.new('RGBA', expanded.size, (180, 20, 50, 255))
                generated.putalpha(expanded.getchannel('A'))
                expected = Image.composite(generated, expanded, border)
                np.testing.assert_array_equal(np.array(output), np.array(expected))
                reference = fibo_masked_reference(expanded, hard) if fibo else location_guide(expanded, hard, opaque=True)
                self.assertEqual(len(calls[0].edit_references), 3 if extra_refs else 1)
                working = 0 if plan.get('output_resize') else canvas_reference_resolution(expanded.size, 512, plan['shrink_by'])
                self.assertEqual(image_digest(calls[0].edit_references[0]), image_digest(prepare_reference(reference, working)))
                if plan['shrink_by'] > 1:
                    self.assertLessEqual(calls[0].width, expanded.width + 31)
                    self.assertLessEqual(calls[0].height, expanded.height + 31)
                with Image.open(filename) as saved:
                    recipe = json.loads(saved.info['image_edit'])
                    self.assertEqual(recipe['canvas'], plan)
                    self.assertEqual(recipe['masked_reference_guidance'], extra_refs)
                    self.assertEqual(recipe['working_resolution'], working)
                    self.assertEqual(recipe['edit_mode'], 'Outpaint' if plan['expand'] else 'Painted canvas edit')
                    self.assertEqual(recipe['canvas_painted_area'], canvas_paint)
                    self.assertEqual(recipe['masked_edit']['feather'], 0)
                    self.assertEqual(recipe['masked_edit']['crop'], [0, 0, *plan['output_size']])
                    if plan['expand']:
                        expected_prompt = outpaint_instruction(instruction, fibo, canvas_paint)
                        if extra_refs:
                            expected_prompt = masked_reference_instruction(expected_prompt, fibo, 2)
                        self.assertEqual(calls[0].prompt, expected_prompt)
                        self.assertEqual(recipe['effective_prompt'], expected_prompt)
                    self.assertNotIn('fibo_global_curves', recipe)
                    _, selected, _ = result_context(filename, __import__('hashlib').sha256(Path(filename).read_bytes()).hexdigest())
                    np.testing.assert_array_equal(np.array(selected), np.array(border))
                return
            if camera:
                size = output_resize_size(source.size, output_resize) if output_resize else None
                clean = prepare_sized_reference(source, size) if size else prepare_reference(source, 512)
                box = reference_content_box(*size, 0) if size else reference_content_box(*source.size, 512)
                self.assertEqual(output.size, (box[2] - box[0], box[3] - box[1]))
                self.assertEqual(len(calls[0].edit_references), 3 if extra_refs else 1)
                self.assertEqual(image_digest(calls[0].edit_references[0]), image_digest(clean))
                self.assertIn(instruction, calls[0].prompt)
                self.assertEqual(calls[0].prompt, camera_angle_instruction(instruction, fibo))
                from forge_qwen_edit.workflow import read_recipe
                recipe = read_recipe(filename)
                self.assertEqual(recipe.get('output_resize'), output_resize)
                self.assertEqual(recipe["edit_mode"], "Camera angle")
                self.assertEqual(recipe["prompt"], instruction)
                self.assertEqual(recipe["effective_prompt"], calls[0].prompt)
                self.assertFalse(recipe["area_only"])
                self.assertNotIn("masked_edit", recipe)
                with Image.open(filename) as saved:
                    self.assertNotIn(MASK_KEY, saved.info)
                with self.assertRaisesRegex(ValueError, "whole scene"):
                    namespace["generate"](source, None, None, instruction, "", 512, 4 if fibo else 8, "-1", "Euler" if fibo else "Res Multistep", schedule, model_name, encoder_name, vae_name, True, True, editor, 8, mode, family, custom_components=custom_components)
                return
            self.assertEqual(output.size, source.size)
            outside = np.array(layer)[..., 3] == 0
            np.testing.assert_array_equal(np.array(output)[outside], np.array(source)[outside])
            self.assertTrue(calls[0].closed)
            replace = mode == "Replace / remove"
            self.assertEqual(len(calls[0].edit_references), (1 if replace else 2) + (2 if extra_refs else 0))
            self.assertIn("<image_1>" if fibo else "<image1>" if replace else "<image2>", calls[0].prompt)
            self.assertEqual(calls[0].edit_family, family)
            self.assertEqual(calls[0].distilled_cfg_scale, expected_shift)
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
