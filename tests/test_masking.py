import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from forge_qwen_edit.masking import composite_patch, context_box, editor_value, extract_mask, location_guide, scoped_instruction, has_painted_area, edit_modes, camera_angle_instruction, expression_transfer_instruction


class MaskingTests(unittest.TestCase):
    def test_camera_is_a_whole_scene_choice_for_both_models(self):
        for family in ('Qwen Image 2.1', 'Fibo 2.0 Edit Turbo', 'Fibo 2.0 Dev'):
            self.assertEqual(edit_modes(family), ['Standard', 'Camera angle', 'Expression transfer'])
            self.assertNotIn('Camera angle', edit_modes(family, True))
            self.assertIn('Expression transfer', edit_modes(family, True))

    def test_expression_guidance_preserves_fibo_caption_and_reference_roles(self):
        import json
        value = {'edit_instruction': 'Use the sneer.', 'structured_caption': {'short_description': 'a portrait'}}
        result = json.loads(expression_transfer_instruction(json.dumps(value), fibo=True))
        self.assertEqual(result['structured_caption'], value['structured_caption'])
        self.assertTrue(result['edit_instruction'].startswith(value['edit_instruction']))
        self.assertIn('Edit the person in <image_1>', result['edit_instruction'])
        self.assertIn('Use <image_2> only as a facial-expression reference', result['edit_instruction'])
        self.assertIn('not a face swap', result['edit_instruction'])

    def test_camera_guidance_preserves_fibo_structured_caption_and_user_move(self):
        import json
        value = {'edit_instruction': 'Aerial view from above the cat.', 'structured_caption': {'short_description': 'same cat and room'}}
        result = json.loads(camera_angle_instruction(json.dumps(value), fibo=True))
        self.assertEqual(result['structured_caption'], value['structured_caption'])
        self.assertTrue(result['edit_instruction'].startswith(value['edit_instruction']))
        self.assertIn('<image_1>', result['edit_instruction'])
        self.assertNotEqual(result['edit_instruction'], value['edit_instruction'])

    def test_automatic_scope_uses_only_painted_alpha(self):
        self.assertFalse(has_painted_area(None))
        empty = Image.new('RGBA', (16, 16), (128, 128, 128, 0))
        self.assertFalse(has_painted_area(empty))
        empty.putpixel((5, 5), (128, 128, 128, 255))
        self.assertTrue(has_painted_area(empty))
        empty.putpixel((5, 5), (128, 128, 128, 0))
        self.assertFalse(has_painted_area(empty))
        with self.assertRaisesRegex(ValueError, 'transparency'):
            has_painted_area(empty.convert('RGB'))

    def test_submitted_strokes_override_stale_scope_flag(self):
        import ast
        from types import SimpleNamespace
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'forge_qwen_edit/ui.py').read_text(encoding='utf-8'))
        method = next(n for n in tree.body if getattr(n, 'name', '') == 'run_canvas_edit')
        ns = dict(has_painted_area=has_painted_area, run_edit=lambda *args, **kwargs: args, validate_count=lambda x: x,
            model_bar=SimpleNamespace(resolve_selection=lambda *a: (SimpleNamespace(name='checkpoint'), SimpleNamespace(label='Fibo'), 'encoder', 'vae')))
        exec(compile(ast.Module(body=[method], type_ignores=[]), 'scope_dispatch', 'exec'), ns)
        for old_flag, alpha, expected in ((False, 255, True), (True, 0, False)):
            foreground = Image.new('RGBA', (16, 16), (128, 128, 128, alpha))
            result = ns['run_canvas_edit']('task', *([None] * 10), 'checkpoint', [], 'Automatic', False,
                old_flag, foreground, 8, 'Replace / remove', '', True, 1, False, False, 0, 0, 0, 0, 32, 1, 1, '', '')
            self.assertEqual(result[15], expected)
            submitted = ns['run_canvas_edit']('task', *([None] * 10), 'checkpoint', [], 'Automatic', False,
                old_flag, foreground, 8, 'Replace / remove', '', True, 1, False, False, 0, 0, 0, 0, 32, 1, 1, '', '',
                'Manual', .85, True, True, 'Resize by', 1024, 1024, 2)
            self.assertEqual(submitted[-4:-1], ('Manual', .85, True))
            self.assertEqual(submitted[-1], None if expected else dict(mode='Resize by', width=1024, height=1024, scale=2))
            current = ns['run_canvas_edit']('task', *([None] * 10), 'checkpoint', [], 'Automatic', False,
                old_flag, foreground, 8, 'Replace / remove', '', True, 1, False, False, 0, 0, 0, 0, 32, 1, 1, '', '',
                'Manual', .85, True, True, 'Resize by', 1024, 1024, 2, 'Image-size adjusted', .69, True)
            self.assertEqual(current[:-3], submitted)
            self.assertEqual(current[-3:], ('Image-size adjusted', .69, True))
            from unittest.mock import Mock
            runner = Mock(return_value='custom job')
            resolver = Mock(return_value=(SimpleNamespace(name='checkpoint'), SimpleNamespace(label='Fibo'), 'encoder', 'vae'))
            ns.update(run_edit=runner, model_bar=SimpleNamespace(resolve_selection=resolver))
            self.assertEqual(ns['run_canvas_edit']('task', *([None] * 10), 'checkpoint', ['vae', 'encoder'], 'Automatic', False,
                old_flag, foreground, 8, 'Replace / remove', '', True, 1, False, False, 0, 0, 0, 0, 32, 1, 1, '', '',
                'Manual', .85, True, True, 'Resize by', 1024, 1024, 2, 'Image-size adjusted', .69, True, True, 'vae'), 'custom job')
            resolver.assert_called_once_with('checkpoint', ['vae', 'encoder'], True, 'vae')
            self.assertEqual(runner.call_args.args, current)
            self.assertEqual(runner.call_args.kwargs, dict(batch_count=1, custom_components=True))
            ns.update(run_edit=lambda *args, **kwargs: args)

    def setUp(self):
        rng = np.random.default_rng(7)
        self.pixels = rng.integers(0, 256, (380, 620, 4), dtype=np.uint8)
        self.source = Image.fromarray(self.pixels, "RGBA")
        self.layer = Image.new("RGBA", self.source.size)
        ImageDraw.Draw(self.layer).ellipse((263, 142, 327, 211), fill=(0, 255, 0, 255))
        self.editor = editor_value(self.source)
        self.editor["layers"] = [self.layer]

    def test_shared_size_dispatches_to_canvas_or_model_without_losing_paint(self):
        import ast
        from types import SimpleNamespace
        from forge_qwen_edit.outpaint import EDGES, canvas_plan
        from forge_qwen_edit.masking import canonical_image
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'forge_qwen_edit/ui.py').read_text(encoding='utf-8'))
        method = next(n for n in tree.body if getattr(n, 'name', '') == 'run_canvas_edit')
        ns = dict(has_painted_area=has_painted_area, extract_mask=extract_mask, canonical_image=canonical_image,
            EDGES=EDGES, canvas_plan=canvas_plan, validate_count=lambda n: n, gr=SimpleNamespace(Error=ValueError),
            run_edit=lambda *args, **kw: ('model', args), run_canvas_crop=lambda *args, **kw: ('crop', args, kw),
            model_bar=SimpleNamespace(resolve_selection=lambda *a: (SimpleNamespace(name='checkpoint'), SimpleNamespace(label='Fibo'), 'encoder', 'vae')))
        exec(compile(ast.Module(body=[method], type_ignores=[]), 'canvas_dispatch', 'exec'), ns)
        for left, paint in ((0, None), (80, None), (0, self.layer), (80, self.layer)):
            result = ns['run_canvas_edit']('task', self.source, *([None] * 9), 'checkpoint', [], 'Automatic', False,
                False, paint, 8, 'Standard', '', True, 1, False, True, left, 0, 0, 0, 32, 1, 1, '', '',
                'Manual', .85, True, True, 'Resize by', 1024, 1024, .5)
            if left or paint is not None:
                self.assertEqual(result[0], 'model')
                self.assertEqual(result[1][-6]['output_resize']['scale'], .5)
                self.assertIsNone(result[1][-1])
                self.assertEqual(result[1][15], paint is not None)
            else:
                self.assertEqual(result[0], 'crop')
                self.assertTrue(result[1][9])
                self.assertEqual(result[2]['output_scale'], .5)

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
