import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from forge_qwen_edit.masking import composite_patch
from forge_qwen_edit.tone import match_source_tone, tone_summary
from forge_qwen_edit.workflow import read_recipe


class ToneTests(unittest.TestCase):
    def scene(self):
        x, y = np.meshgrid(np.linspace(0, 1, 192), np.linspace(0, 1, 128))
        texture = 7 * np.sin(x * 150) * np.cos(y * 100)
        return Image.fromarray(np.stack([40 + x * 140 + texture, 55 + y * 130 + texture,
                                        65 + (x + y) * 55 + texture], axis=-1).round().astype(np.uint8))

    def shifted(self, source):
        return Image.fromarray(np.clip(np.array(source).astype(float) * 1.15 - 12, 0, 255).round().astype(np.uint8))

    def test_recovers_tone_without_replacing_edited_object(self):
        source = self.scene()
        result = self.shifted(source)
        result.paste((30, 50, 210), (60, 40, 100, 80))
        matched, info = match_source_tone(source, result)
        original, corrected = np.array(source), np.array(matched)
        outside = np.ones(original.shape[:2], dtype=bool)
        outside[35:85, 55:105] = False
        self.assertTrue(info['applied'])
        self.assertAlmostEqual(info['gain'], 1 / 1.15, delta=.025)
        self.assertLess(np.abs(corrected.astype(float) - original)[outside].mean(), 1.3)
        # The new blue object remains; this is not original-pixel compositing.
        self.assertGreater(int(corrected[60, 80, 2]) - int(corrected[60, 80, 0]), 120)

    def test_repeated_correction_does_not_accumulate_contrast(self):
        original = self.scene()
        source = original
        for _ in range(5):
            source, info = match_source_tone(source, self.shifted(source))
        self.assertLess(np.abs(np.array(source).astype(float) - np.array(original)).mean(), 2)

    def test_identity_alpha_and_flat_images(self):
        original = self.scene().convert('RGBA')
        pixels = np.array(original)
        pixels[:10, :, 3] = 0
        original = Image.fromarray(pixels)
        matched, info = match_source_tone(original, original)
        np.testing.assert_array_equal(np.array(original), np.array(matched))
        for image in [Image.new('RGB', (32, 32), 'gray'), Image.new('RGBA', (32, 32), (10, 20, 30, 0))]:
            result, info = match_source_tone(image, image)
            self.assertIs(result, image)
            self.assertFalse(info['applied'])

    def test_painted_exclusion_and_exact_outside_pixels(self):
        source = self.scene().convert('RGBA')
        result = self.shifted(source.convert('RGB'))
        result.paste((0, 0, 240), (40, 30, 140, 100))
        mask = Image.new('L', source.size)
        mask.paste(255, (40, 30, 140, 100))
        corrected, info = match_source_tone(source, result, mask)
        self.assertAlmostEqual(info['gain'], 1 / 1.15, delta=.03)
        output = composite_patch(source, corrected, mask, (0, 0, *source.size), 8)
        outside = np.array(mask) == 0
        np.testing.assert_array_equal(np.array(source)[outside], np.array(output)[outside])

    def test_recipe_roundtrip_and_old_recipe_default(self):
        recipe = dict(version=1, prompt='Replace the apple', steps=4, resolution=768, seed='42',
                      sampler='Euler', schedule='Simple', cfg=1, model_family='Fibo 2.0 Edit Turbo')
        for enabled in (None, False, True):
            data = dict(recipe)
            if enabled is not None:
                data['preserve_tone'] = enabled
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder)/'recipe.png'
                info = PngInfo()
                info.add_text('image_edit', json.dumps(data))
                Image.new('RGB', (32, 32)).save(path, pnginfo=info)
                self.assertEqual(bool(read_recipe(path).get('preserve_tone', False)), bool(enabled))

    def test_result_feedback_distinguishes_small_applied_and_skipped_corrections(self):
        self.assertIn('negligible', tone_summary(dict(applied=True, gain=1.00130333, offset=-.00394541)))
        self.assertIn('contrast -10.0%', tone_summary(dict(applied=True, gain=.9, offset=.03)))
        self.assertIn('brightness +7.6/255', tone_summary(dict(applied=True, gain=.9, offset=.03)))
        self.assertIn('skipped', tone_summary(dict(applied=False)))
        _, info = match_source_tone(Image.new('RGB', (32, 32), 'gray'), Image.new('RGB', (32, 32), 'gray'))
        self.assertIn('too little tonal range', tone_summary(info))


if __name__ == '__main__':
    unittest.main()
