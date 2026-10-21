import json
from pathlib import Path
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from forge_qwen_edit.outpaint import canvas_plan, canvas_images, canvas_blend_mask, outpaint_instruction, save_crop
from forge_qwen_edit.workflow import read_recipe


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
        self.assertIn('bright green', outpaint_instruction('', False))
        result = json.loads(outpaint_instruction(json.dumps(original), True, painted=True))
        self.assertEqual(result['structured_caption'], original['structured_caption'])
        self.assertIn('painted areas', result['edit_instruction'])

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


if __name__ == '__main__': unittest.main()
