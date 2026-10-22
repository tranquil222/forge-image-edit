"""Unchanged canvases allow normal edits; invalid inputs still block generation."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from PIL import Image

from forge_qwen_edit.outpaint import EDGES, canvas_plan, canvas_reference_resolution
from forge_qwen_edit.workflow import reference_content_box
from forge_qwen_edit.masking import canonical_image, extract_mask, has_painted_area


class CanvasFeedbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse((Path(__file__).parents[1] / 'forge_qwen_edit/ui.py').read_text(encoding='utf-8'))
        function = next(node for node in tree.body if getattr(node, 'name', '') == 'canvas_feedback')
        namespace = dict(gr=SimpleNamespace(update=lambda **values: values), EDGES=EDGES, canvas_plan=canvas_plan,
                         canvas_reference_resolution=canvas_reference_resolution, reference_content_box=reference_content_box)
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<feedback>', 'exec'), namespace)
        cls.feedback = staticmethod(namespace['canvas_feedback'])

    def test_zero_edges_allow_normal_or_painted_edits(self):
        for painted in (False, True):
            _, generate, crop, hint = self.feedback([512, 512], True, 0, 0, 0, 0, 'Fibo 2.0 Edit Turbo', painted)
            self.assertTrue(generate['interactive'])
            self.assertEqual(generate['value'], 'Generate edit')
            self.assertFalse(crop['visible'])
            self.assertEqual(hint['visible'], not painted)
            if not painted:
                self.assertIn('apply your prompt to the whole image', hint['value'])

    def test_normal_fallback_reports_actual_edit_size(self):
        message, _, _, _ = self.feedback([896, 1216], True, 0, 0, 0, 0, 'Fibo 2.0 Edit Turbo')
        x0, y0, x1, y1 = reference_content_box(896, 1216, 768)
        self.assertEqual(message, f'Output: **{x1-x0} × {y1-y0}** · source: 896 × 1216')
        for resize in (dict(output_width=896, output_height=1216), dict(resize_mode='Resize by', output_scale=1)):
            message, generate, crop, _ = self.feedback([896, 1216], True, 0, 0, 0, 0, 'Fibo 2.0 Edit Turbo',
                resize_enabled=True, **resize)
            self.assertTrue(generate['interactive'])
            self.assertFalse(crop['visible'])
            self.assertIn('Output: **896 × 1216**', message)

    def test_expansion_crop_and_shrink_choose_the_right_action(self):
        for left, shrink, crop_expected in ((32, 1, False), (-32, 1, True), (0, 2, True)):
            _, generate, crop, _ = self.feedback([512, 512], True, left, 0, 0, 0, 'Fibo 2.0 Edit Turbo', shrink_by=shrink)
            self.assertEqual(crop['visible'], crop_expected)
            self.assertEqual(generate['visible'], not crop_expected)

    def test_invalid_source_geometry_or_model_never_enables_generation(self):
        for size, left, ready in (([0, 0], 20, True), ([0, 0], 0, True), ([512, 512], -600, True),
                                  ([512, 512], 20, False), ([512, 512], 0, False)):
            _, generate, _, _ = self.feedback(size, True, left, 0, 0, 0, 'Fibo 2.0 Edit Turbo', model_ready=ready)
            self.assertFalse(generate['interactive'])

    def test_shared_resize_handles_expanded_and_resize_only_canvases(self):
        message, generate, crop, hint = self.feedback([512, 512], True, 256, 0, 0, 0, 'Fibo 2.0 Edit Turbo',
            resize_enabled=True, output_width=600, output_height=400)
        self.assertTrue(generate['interactive'])
        self.assertFalse(crop['visible'])
        self.assertIn('600 × 400', message)
        self.assertFalse(hint['visible'])
        _, generate, crop, _ = self.feedback([512, 512], True, 0, 0, 0, 0, 'Fibo 2.0 Edit Turbo',
            resize_enabled=True, resize_mode='Resize by', output_scale=.5)
        self.assertTrue(crop['visible'])
        self.assertEqual(crop['value'], 'Apply resize')
        self.assertFalse(generate['visible'])


class CanvasFallbackDispatchTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((Path(__file__).parents[1] / 'forge_qwen_edit/ui.py').read_text(encoding='utf-8'))
        function = next(node for node in tree.body if getattr(node, 'name', '') == 'run_canvas_edit')
        self.run_edit = Mock(return_value='edited')
        self.crop = Mock(return_value='cropped')
        self.resolve = Mock(return_value=(SimpleNamespace(name='checkpoint'), SimpleNamespace(label='Fibo'), 'encoder', 'vae'))
        namespace = dict(gr=SimpleNamespace(Error=ValueError), EDGES=EDGES, canvas_plan=canvas_plan,
            canonical_image=canonical_image, extract_mask=extract_mask, has_painted_area=has_painted_area,
            validate_count=lambda n: n, model_bar=SimpleNamespace(resolve_selection=self.resolve),
            run_edit=self.run_edit, run_canvas_crop=self.crop)
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<canvas dispatch>', 'exec'), namespace)
        self.dispatch = namespace['run_canvas_edit']
        self.source = Image.new('RGBA', (512, 768), (100, 100, 100, 255))
        self.source.info['parameters'] = 'Made with Krea 2 and a Turbo LoRA'

    def args(self, canvas=True, left=0, paint=None, tail=()):
        return (self.source, *([None] * 9), 'checkpoint', ['encoder', 'vae'], 'Automatic', True,
                False, paint, 8, 'Standard', 'requested result', True, 1, False,
                canvas, left, 0, 0, 0, 32, 1, 2, '', '', *tail)

    def test_zero_edge_dispatch_matches_unchecked_for_legacy_and_current_requests(self):
        sampling = ('Manual', .85, True)
        sizing = (True, 'Resize to', 512, 768, 1)
        qwen = ('Image-size adjusted', .69, True)
        for family in ('Fibo 2.0 Edit Turbo', 'Fibo 2.0 Dev', 'Qwen Image 2.1'):
            self.resolve.return_value = (SimpleNamespace(name='checkpoint'), SimpleNamespace(label=family), 'encoder', 'vae')
            for tail in ((), sampling, (*sampling, *sizing), (*sampling, *sizing, *qwen),
                         (*sampling, *sizing, *qwen, True, 'vae')):
                with self.subTest(family=family, fields=len(tail)):
                    self.assertEqual(self.dispatch('task', *self.args(canvas=False, tail=tail)), 'edited')
                    normal = self.run_edit.call_args
                    self.assertEqual(self.dispatch('task', *self.args(tail=tail)), 'edited')
                    self.assertEqual(self.run_edit.call_args, normal)
                    self.assertIsNone(self.run_edit.call_args.args[25])
        self.crop.assert_not_called()

    def test_real_outpaint_and_paint_keep_canvas_payload(self):
        paint = Image.new('RGBA', self.source.size)
        paint.putpixel((50, 50), (0, 255, 0, 255))
        for left, strokes in ((32, None), (0, paint), (32, paint)):
            self.assertEqual(self.dispatch('task', *self.args(left=left, paint=strokes)), 'edited')
            self.assertEqual(self.run_edit.call_args.args[25]['left'], left)
            self.assertEqual(self.run_edit.call_args.args[15], strokes is not None)
        self.crop.assert_not_called()

    def test_cropping_still_avoids_generation(self):
        self.assertEqual(self.dispatch('task', *self.args(left=-32)), 'cropped')
        self.run_edit.assert_not_called()
        self.resolve.assert_not_called()

    def test_fallback_still_validates_model_and_invalid_geometry(self):
        self.resolve.side_effect = ValueError('Missing VAE')
        with self.assertRaisesRegex(ValueError, 'Missing VAE'):
            self.dispatch('task', *self.args())
        with self.assertRaisesRegex(ValueError, 'Keep some of the original'):
            self.dispatch('task', *self.args(left=-600))
        self.run_edit.assert_not_called()
        self.crop.assert_not_called()


if __name__ == '__main__':
    unittest.main()
