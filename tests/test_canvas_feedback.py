"""No-op/invalid canvases must not offer generation or bypass model readiness."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

from forge_qwen_edit.outpaint import EDGES, canvas_plan, canvas_reference_resolution
from forge_qwen_edit.workflow import reference_content_box


class CanvasFeedbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse((Path(__file__).parents[1] / 'forge_qwen_edit/ui.py').read_text(encoding='utf-8'))
        function = next(node for node in tree.body if getattr(node, 'name', '') == 'canvas_feedback')
        namespace = dict(gr=SimpleNamespace(update=lambda **values: values), EDGES=EDGES, canvas_plan=canvas_plan,
                         canvas_reference_resolution=canvas_reference_resolution, reference_content_box=reference_content_box)
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<feedback>', 'exec'), namespace)
        cls.feedback = staticmethod(namespace['canvas_feedback'])

    def test_zero_edges_require_an_edit_but_painting_enables_generation(self):
        for painted in (False, True):
            _, generate, crop, hint = self.feedback([512, 512], True, 0, 0, 0, 0, 'Fibo 2.0 Edit Turbo', painted)
            self.assertEqual(generate['interactive'], painted)
            self.assertFalse(crop['visible'])
            self.assertTrue(hint['visible'])
            if not painted:
                self.assertIn('Nothing to change yet', hint['value'])

    def test_expansion_crop_and_shrink_choose_the_right_action(self):
        for left, shrink, crop_expected in ((32, 1, False), (-32, 1, True), (0, 2, True)):
            _, generate, crop, _ = self.feedback([512, 512], True, left, 0, 0, 0, 'Fibo 2.0 Edit Turbo', shrink_by=shrink)
            self.assertEqual(crop['visible'], crop_expected)
            self.assertEqual(generate['visible'], not crop_expected)

    def test_invalid_source_geometry_or_model_never_enables_generation(self):
        for size, left, ready in (([0, 0], 20, True), ([512, 512], -600, True), ([512, 512], 20, False)):
            _, generate, _, _ = self.feedback(size, True, left, 0, 0, 0, 'Fibo 2.0 Edit Turbo', model_ready=ready)
            self.assertFalse(generate['interactive'])


if __name__ == '__main__':
    unittest.main()
