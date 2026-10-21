import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from forge_qwen_edit.masking import composite_patch, context_box, editor_value, extract_mask, location_guide, scoped_instruction


class MaskingTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(7)
        self.pixels = rng.integers(0, 256, (380, 620, 4), dtype=np.uint8)
        self.source = Image.fromarray(self.pixels, "RGBA")
        self.layer = Image.new("RGBA", self.source.size)
        ImageDraw.Draw(self.layer).ellipse((263, 142, 327, 211), fill=(0, 255, 0, 255))
        self.editor = editor_value(self.source)
        self.editor["layers"] = [self.layer]

    def test_unpainted_pixels_and_alpha_are_exactly_preserved(self):
        mask = extract_mask(self.source, self.editor)
        crop = context_box(mask)
        edited = Image.new("RGBA", (768, 768), (220, 30, 10, 255))
        for feather in (0, 8, 32):
            output = np.array(composite_patch(self.source, edited, mask, crop, feather))
            outside = np.array(mask) == 0
            self.assertEqual(output.shape, self.pixels.shape)
            np.testing.assert_array_equal(output[outside], self.pixels[outside])
            np.testing.assert_array_equal(output[..., 3], self.pixels[..., 3])
            self.assertFalse(np.array_equal(output[~outside], self.pixels[~outside]))

    def test_original_green_pixels_do_not_become_a_mask(self):
        green = Image.new("RGBA", (100, 100), (0, 255, 0, 255))
        with self.assertRaisesRegex(ValueError, "No area is painted"):
            extract_mask(green, editor_value(green))

    def test_stale_mask_is_rejected_even_when_dimensions_match(self):
        changed = self.source.copy()
        changed.putpixel((0, 0), (1, 2, 3, 255))
        with self.assertRaisesRegex(ValueError, "different source"):
            extract_mask(changed, self.editor)

    def test_context_contains_selection_at_edges_and_inside_small_images(self):
        for size, selection in [((620, 380), (0, 0, 11, 20)), ((620, 380), (610, 370, 619, 379)), ((45, 30), (12, 6, 21, 14))]:
            mask = Image.new("L", size)
            ImageDraw.Draw(mask).rectangle(selection, fill=255)
            x1, y1, x2, y2 = context_box(mask)
            a, b, c, d = mask.getbbox()
            self.assertTrue(0 <= x1 <= a < c <= x2 <= size[0])
            self.assertTrue(0 <= y1 <= b < d <= y2 <= size[1])

    def test_guide_is_separate_and_only_marks_the_selected_area(self):
        before = self.source.tobytes()
        mask = extract_mask(self.source, self.editor)
        guide = np.array(location_guide(self.source, mask))
        outside = np.array(mask) == 0
        np.testing.assert_array_equal(guide[outside], np.array(self.source.convert("RGB"))[outside])
        self.assertEqual(self.source.tobytes(), before)
        self.assertIn("<image4>", scoped_instruction("Give image 1 a subtle smile.", 4))

    def test_multiple_strokes_and_erased_transparency(self):
        second = Image.new("RGBA", self.source.size)
        ImageDraw.Draw(second).rectangle((2, 2, 12, 12), fill=(0, 255, 0, 255))
        self.editor["layers"].append(second)
        mask = extract_mask(self.source, self.editor)
        self.assertEqual(mask.getpixel((6, 6)), 255)
        self.assertEqual(mask.getpixel((300, 180)), 255)
        self.assertEqual(mask.getpixel((100, 100)), 0)

    def test_replacement_guide_cannot_reveal_any_covered_original_pixels(self):
        mask = extract_mask(self.source, self.editor)
        mask.putpixel((100, 100), 1)  # even an anti-aliased boundary is opaque
        changed = self.source.copy()
        changed.paste((255, 10, 20, 255), mask=mask.point(lambda a: 255 if a else 0))
        first = location_guide(self.source, mask, opaque=True)
        second = location_guide(changed, mask, opaque=True)
        self.assertEqual(first.tobytes(), second.tobytes())
        pixels = np.array(first)
        self.assertTrue(np.all(pixels[np.array(mask) > 0] == [0, 255, 0]))

    def test_replacement_instructions_are_automatically_appended(self):
        prompt = "a plain black jacket"
        effective = scoped_instruction(prompt, 1, replace=True)
        self.assertTrue(effective.startswith(prompt + "\n\n"))
        self.assertIn("Replace the entire green-marked region", effective)
        self.assertIn("content specified by the user's instruction above", effective)
        self.assertIn("outside the marked area unchanged", effective)


if __name__ == "__main__":
    unittest.main()
