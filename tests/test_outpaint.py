import json
from pathlib import Path
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from forge_qwen_edit.outpaint import canvas_plan, canvas_images, canvas_blend_mask, canvas_reference_resolution, outpaint_instruction, save_crop
from forge_qwen_edit.workflow import read_recipe, reference_content_box


class OutpaintTests(unittest.TestCase):
    def test_mixed_edges_keep_exact_source_and_only_new_pixels_are_grey(self):
        source = Image.fromarray(np.random.default_rng(6).integers(0, 256, (60, 80, 4), dtype=np.uint8))
        source.info['Author'] = 'test'
        plan = canvas_plan(source.size, dict(left=-10, right=30, top=20, bottom=-15))
        canvas, mask = canvas_images(source, plan)
        self.assertEqual(canvas.size, (100, 65))
        self.assertEqual(plan['source_box'], [10, 0, 80, 45])
        self.assertEqual(plan['position'], [0, 20])
        np.testing.assert_array_equal(np.array(canvas)[20:65, :70], np.array(source)[:45, 10:80])
        outside = np.array(mask) > 0
        np.testing.assert_array_equal(np.array(canvas)[outside], np.tile([128, 128, 128, 255], (outside.sum(), 1)))
        self.assertEqual(canvas.info['Author'], 'test')

    def test_each_positive_edge_and_crop_only_geometry(self):
        for edge in ('left', 'right', 'top', 'bottom'):
            plan = canvas_plan((100, 80), {edge: 12})
            self.assertTrue(plan['expand'])
            self.assertEqual(plan['position'], [12 if edge == 'left' else 0, 12 if edge == 'top' else 0])
        plan = canvas_plan((100, 80), dict(left=-5, right=-15, top=-10, bottom=-20))
        self.assertFalse(plan['expand']); self.assertTrue(plan['changed'])
        self.assertEqual(plan['output_size'], [80, 50])
        self.assertEqual(plan['source_box'], [5, 10, 85, 60])
        # Equal final width can still replace a cropped edge with added space.
        self.assertTrue(canvas_plan((100, 80), dict(left=-10, right=10))['expand'])
        self.assertFalse(canvas_plan((100, 80), {})['changed'])

    def test_invalid_or_empty_canvas_does_not_allocate(self):
        for values in ({'left': -100}, {'left': -60, 'right': -60}, {'left': 1.5},
                       {'left': True}, {'left': float('nan')}, {'left': 17000}):
            with self.assertRaises(ValueError): canvas_plan((100, 80), values)
        with self.assertRaises(ValueError): canvas_plan((8000, 8000), {'left': 1})

    def test_outpaint_prompt_preserves_json_and_model_specific_mask(self):
        original = {'edit_instruction': 'Continue the restaurant.', 'structured_caption': {'short_description': 'a restaurant'}}
        result = json.loads(outpaint_instruction(json.dumps(original), True))
        self.assertEqual(result['structured_caption'], original['structured_caption'])
        self.assertIn('neutral-grey', result['edit_instruction'])
        self.assertNotIn('green', result['edit_instruction'])
        self.assertIn('green areas', outpaint_instruction('', False))
        result = json.loads(outpaint_instruction(json.dumps(original), True, painted=True))
        self.assertEqual(result['structured_caption'], original['structured_caption'])
        self.assertIn('painted areas', result['edit_instruction'])

    def test_qwen_outpaint_leads_with_replacement_and_preserves_user_edit(self):
        instruction = 'Continue the tiled floor using the pattern from <image2>.'
        for painted in (False, True):
            with self.subTest(painted=painted):
                prompt = outpaint_instruction(instruction, False, painted)
                self.assertTrue(prompt.startswith('Replace all the green areas'))
                self.assertTrue(prompt.endswith(instruction))
                self.assertEqual(prompt.count(instruction), 1)
                self.assertNotIn('neutral-grey', prompt)
                self.assertNotIn('framed picture', prompt)
                if painted:
                    self.assertIn('apply the requested edit to green areas inside', prompt)
                    self.assertIn('unmasked content', prompt)
                    self.assertNotIn('Keep the existing scene unchanged', prompt)
        self.assertTrue(outpaint_instruction('  ', False).endswith('Extend the surrounding scene naturally.'))

    def test_paint_is_cropped_and_shifted_with_source_without_touching_source_pixels(self):
        source = Image.new('RGBA', (80, 60), (30, 60, 90, 170))
        paint = Image.new('L', source.size)
        paint.paste(255, (0, 5, 25, 35))
        plan = canvas_plan(source.size, dict(left=-10, right=30, top=20, bottom=-15))
        canvas, mask = canvas_images(source, plan, paint)
        np.testing.assert_array_equal(np.array(mask)[20:65, :70], np.array(paint)[:45, 10:])
        self.assertTrue(np.all(np.array(mask)[:20] == 255))
        self.assertTrue(np.all(np.array(mask)[:, 70:] == 255))
        np.testing.assert_array_equal(np.array(canvas)[20:65, :70], np.array(source)[:45, 10:])
        with self.assertRaises(ValueError): canvas_images(source, plan, Image.new('L', (12, 12)))

    def test_seam_alpha_is_inside_original_only_and_does_not_change_model_mask(self):
        source = Image.new('RGB', (80, 60), (30, 60, 90))
        for edge in ('left', 'right', 'top', 'bottom'):
            with self.subTest(edge=edge):
                plan = canvas_plan(source.size, {edge: 20, 'seam_blend': 8})
                canvas, hard = canvas_images(source, plan)
                before = hard.tobytes()
                alpha = np.array(canvas_blend_mask(hard, plan))
                self.assertEqual(hard.tobytes(), before)
                np.testing.assert_array_equal(alpha[np.array(hard) == 255], 255)
                x, y = plan['position']
                interior = alpha[y:y + 60, x:x + 80]
                np.testing.assert_array_equal(interior[8:-8, 8:-8], 0)
                scan = {'left':interior[30, :8], 'right':interior[30, -8:][::-1],
                        'top':interior[:8, 40], 'bottom':interior[-8:, 40][::-1]}[edge]
                self.assertEqual(scan.tolist(), [255, 223, 191, 159, 128, 96, 64, 32])
                plan['seam_blend'] = 0
                self.assertEqual(canvas_blend_mask(hard, plan).tobytes(), before)

    def test_crop_has_no_seam_and_paint_survives_overlap(self):
        source = Image.new('RGB', (80, 60))
        paint = Image.new('L', source.size); paint.paste(255, (3, 20, 12, 35))
        crop_plan = canvas_plan(source.size, {'left': -5, 'seam_blend': 128})
        _, hard = canvas_images(source, crop_plan, paint)
        self.assertEqual(canvas_blend_mask(hard, crop_plan).tobytes(), hard.tobytes())
        expand_plan = canvas_plan(source.size, {'left': 15, 'seam_blend': 32})
        _, hard = canvas_images(source, expand_plan, paint)
        alpha = np.array(canvas_blend_mask(hard, expand_plan))
        np.testing.assert_array_equal(alpha[np.array(hard) == 255], 255)
        for blend in (-1, 129, 1.2, None, float('nan')):
            with self.assertRaises(ValueError): canvas_plan(source.size, {'seam_blend': blend})

    def test_tall_source_expands_to_landscape_then_shrinks_without_grey_bleed(self):
        source = Image.new('RGBA', (768, 2048), (230, 40, 20, 170))
        source.info['Author'] = 'source'
        paint = Image.new('L', source.size)
        paint.paste(255, (0, 256, 128, 512))
        before = source.tobytes()
        plan = canvas_plan(source.size, dict(left=1152, right=1152, shrink_by=2, seam_blend=16))
        self.assertEqual(plan['canvas_size'], [3072, 2048])
        self.assertEqual(plan['output_size'], [1536, 1024])
        self.assertEqual(plan['position'], [576, 0])
        canvas, hard = canvas_images(source, plan, paint)
        expected = source.resize((384, 1024), Image.Resampling.LANCZOS)
        np.testing.assert_array_equal(np.array(canvas)[:, 576:960], np.array(expected))
        np.testing.assert_array_equal(np.array(hard)[:, 576:960], np.array(paint.resize((384, 1024), Image.Resampling.NEAREST)))
        np.testing.assert_array_equal(np.array(canvas)[:, :576], np.broadcast_to([128, 128, 128, 255], (1024, 576, 4)))
        alpha = np.array(canvas_blend_mask(hard, plan))
        self.assertEqual(alpha[600, 576], 255)
        self.assertEqual(alpha[600, 591], 16)
        self.assertEqual(alpha[600, 592], 0)
        self.assertEqual(canvas.info['Author'], 'source')
        self.assertEqual(source.tobytes(), before)

    def test_shrink_validation_and_fractional_geometry(self):
        for value in (0, .5, 4.01, True, None, float('nan'), float('inf'), 'invalid'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                canvas_plan((100, 80), {'shrink_by': value})
        plan = canvas_plan((101, 83), dict(left=-7, right=19, bottom=-5, shrink_by=1.5))
        self.assertEqual(plan['output_size'], [75, 52])
        self.assertEqual(plan['source_box'], [7, 0, 101, 78])
        self.assertEqual(plan['retained_size'], [62, 52])
        self.assertTrue(canvas_plan((100, 80), {'shrink_by': 2})['changed'])
        tiny = canvas_plan((8, 8), dict(left=1, right=1, shrink_by=2))
        self.assertEqual(tiny['position'], [1, 0])
        self.assertEqual(tiny['retained_size'], [3, 4])
        with self.assertRaises(ValueError): canvas_plan((1, 1), dict(left=1, right=1, shrink_by=4))

    def test_shrink_never_reenlarges_model_input_but_keeps_lower_resolution_cap(self):
        self.assertEqual(canvas_reference_resolution((400, 600), 1024, 2), 0)
        self.assertEqual(canvas_reference_resolution((400, 600), 0, 2), 0)
        self.assertEqual(canvas_reference_resolution((1536, 1024), 768, 2), 768)
        self.assertEqual(canvas_reference_resolution((400, 600), 1024, 1), 1024)
        for size in ((400, 600), (1536, 1024), (301, 773)):
            working = canvas_reference_resolution(size, 768, 2)
            x0, y0, x1, y1 = reference_content_box(*size, working)
            self.assertLessEqual(x1 - x0, size[0]); self.assertLessEqual(y1 - y0, size[1])

    def test_crop_saves_exact_pixels_and_metadata_without_a_model(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = Image.fromarray(np.random.default_rng(4).integers(0, 256, (60, 80, 4), dtype=np.uint8))
            source.info.update(Author='test', parameters='original recipe', image_edit_mask='old selection')
            calls = []
            def save(image, directory, basename, **kwargs):
                self.assertEqual(directory, str(root)); calls.append(kwargs)
                info = PngInfo()
                for key, value in kwargs['existing_info'].items(): info.add_text(key, value)
                path = root / f'{len(calls)}-crop.png'; image.save(path, pnginfo=info); return str(path), None
            modules = ModuleType('modules')
            modules.images = SimpleNamespace(save_image=save)
            modules.shared = SimpleNamespace(opts=SimpleNamespace(outdir_samples='', outdir_img2img_samples=str(root), enable_pnginfo=True))
            with patch.dict('sys.modules', modules=modules):
                for keep in (True, False):
                    output, path, message = save_crop(source, dict(left=-10, bottom=-20), keep)
                    np.testing.assert_array_equal(np.array(output), np.array(source)[:40, 10:])
                    self.assertIn('no model run', message)
                    with Image.open(path) as saved:
                        self.assertEqual('Author' in saved.info, keep)
                        self.assertNotIn('image_edit_mask', saved.info)
                        self.assertEqual(read_recipe(saved)['operation'], 'canvas_crop')
                    self.assertEqual(calls[-1]['p'].steps, 0)
                with self.assertRaises(ValueError): save_crop(source, dict(left=10))
                for edges in ({'shrink_by': 2}, {'left': -10, 'bottom': -20, 'shrink_by': 2}):
                    output, path, message = save_crop(source, edges)
                    cropped = source.crop((10, 0, 80, 40)) if 'left' in edges else source
                    expected = cropped.resize((cropped.width // 2, cropped.height // 2), Image.Resampling.LANCZOS)
                    np.testing.assert_array_equal(np.array(output), np.array(expected))
                    self.assertIn('resize only, no model run', message)
                    self.assertEqual(read_recipe(path)['canvas']['shrink_by'], 2)
                for scale in (.75, 1.5):
                    resize = dict(mode='Resize by', scale=scale)
                    output, path, _ = save_crop(source, dict(output_resize=resize))
                    expected = source.resize((round(source.width * scale), round(source.height * scale)), Image.Resampling.LANCZOS)
                    np.testing.assert_array_equal(np.array(output), np.array(expected))
                    self.assertEqual(read_recipe(path)['canvas']['output_resize'], resize)


if __name__ == '__main__': unittest.main()
