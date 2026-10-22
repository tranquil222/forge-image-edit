"""Qwen schedule effects, positional isolation and cleanup without model weights."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
import numpy as np

from forge_qwen_edit.sampling import (validate_qwen_sampling, resolve_qwen_shift,
    shift_qwen_sigmas, qwen_schedule_override, qwen_image_spans, qwen_rope_context)
from forge_qwen_edit.workflow import validate_recipe, cyberzit_quality_values
from test_sampling import Embedder, Positions


class QwenSamplingTests(unittest.TestCase):
    def test_default_auto_and_invalid_shift(self):
        self.assertEqual(resolve_qwen_shift('Manual', .69, 1024, 1024), .69)
        self.assertAlmostEqual(resolve_qwen_shift('Image-size adjusted', .69, 1024, 1024), .6935483870967742)
        self.assertEqual(resolve_qwen_shift('Image-size adjusted', .69, 2048, 2048), .9)
        self.assertEqual(resolve_qwen_shift('Image-size adjusted', .69, 32, 32), .5)
        for value in (True, None, 'bad', float('nan'), float('inf'), 0, 5.01):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'Qwen'):
                validate_qwen_sampling('Manual', value)

    def test_fixed_quality_and_turbo_grids_respond_without_changing_default(self):
        grids = [np.array(cyberzit_quality_values(12)), np.array([1, .95418, .89508, .704534, 0])]
        for grid in grids:
            self.assertIs(shift_qwen_sigmas(grid, .69), grid)
            for shift in (.1, .85, 1.15, 5):
                changed = shift_qwen_sigmas(grid, shift)
                self.assertEqual(changed[0], 1)
                self.assertEqual(changed[-1], 0)
                self.assertTrue(np.all(np.diff(changed) < 0))
                self.assertFalse(np.array_equal(changed, grid))
        function = lambda **kw: np.array(cyberzit_quality_values(kw['n']))
        actual = qwen_schedule_override(function, 1.15)(12)
        np.testing.assert_array_equal(actual, shift_qwen_sigmas(grids[0], 1.15))

    def test_recipes_use_qwen_defaults_and_ignore_fibo_controls(self):
        recipe = dict(model_family='Qwen Image 2.1', prompt='edit', steps=12, resolution=768, seed='42', cfg=1,
                      sampler='Res Multistep', schedule='CyberZit Quality', fibo_shift=1.15, fibo_rope=True)
        old = validate_recipe(recipe)
        self.assertEqual((old['qwen_shift_mode'], old['qwen_shift'], old['qwen_rope']), ('Manual', .69, False))
        custom = validate_recipe(dict(recipe, qwen_shift_mode='Image-size adjusted', qwen_shift=.85, qwen_rope=True))
        self.assertEqual((custom['qwen_shift_mode'], custom['qwen_shift'], custom['qwen_rope']), ('Image-size adjusted', .85, True))
        with self.assertRaises(ValueError): validate_recipe(dict(recipe, qwen_shift=99))

    def test_rope_scales_exact_image_spans_not_text_or_plane_positions(self):
        spans, length = qwen_image_spans(9, [2, 6], [(2, 3), (1, 1)], (2, 2))
        self.assertEqual(spans, [(2, 8), (12, 13), (16, 20)])
        self.assertEqual(length, 20)
        ids = np.arange(60, dtype=np.float32).reshape(1, 20, 3).view(Positions)
        original = ids.copy(); expected = ids.copy()
        for start, end in spans:
            expected[:, start:end, 1] *= .8; expected[:, start:end, 2] *= .85
        class Model:
            def __init__(self):
                self.pe_embedder = Embedder(); self.hooks = []; self.prefix_cache_enabled = True
                self.cache = {'stale': 1}; self.resets = []
            def register_forward_pre_hook(self, hook, with_kwargs=False):
                self.hooks.append(hook)
                return SimpleNamespace(remove=lambda: self.hooks.remove(hook))
            def reset_prefix_cache(self, enabled):
                self.resets.append(enabled); self.cache.clear()
        model = Model()
        sd = SimpleNamespace(forge_objects=SimpleNamespace(unet=SimpleNamespace(model=SimpleNamespace(diffusion_model=model))))
        x = np.empty((1, 4, 2, 2)); context = np.empty((1, 9, 16)); refs = [np.empty((1, 4, 2, 3)), np.empty((1, 4, 1, 1))]
        for fail in (False, True):
            try:
                with qwen_rope_context(sd, True, refs, [2, 6]):
                    self.assertEqual(model.cache, {})
                    for hook in model.hooks: hook(model, (x, None), dict(context=context))
                    np.testing.assert_array_equal(model.pe_embedder(ids), expected)
                    np.testing.assert_array_equal(ids, original)
                    model.cache['adjusted'] = 1
                    if fail: raise RuntimeError('cancelled')
            except RuntimeError: pass
            self.assertEqual(model.cache, {})
            self.assertEqual(model.hooks, []); self.assertEqual(model.pe_embedder.hooks, [])
            self.assertIs(model.pe_embedder(ids), ids)
        self.assertEqual(model.resets, [True] * 4)
        with qwen_rope_context(None, False): pass
        del model.pe_embedder
        with self.assertRaisesRegex(ValueError, 'compatible RoPE'):
            with qwen_rope_context(sd, True): self.fail('Unsupported backend must fail explicitly')

    def test_ui_families_keep_the_same_sampling_controls_without_fibo_leakage(self):
        from forge_qwen_edit.adapters import EDIT_MODELS, get_adapter
        from forge_qwen_edit.masking import AREA_MODES, edit_modes
        tree = ast.parse((Path(__file__).parents[1] / 'forge_qwen_edit/ui.py').read_text(encoding='utf-8'))
        function = next(n for n in tree.body if getattr(n, 'name', '') == 'model_controls')
        ns = dict(gr=SimpleNamespace(update=lambda **kw: kw), EDIT_MODELS=EDIT_MODELS, get_adapter=get_adapter,
                  AREA_MODES=AREA_MODES, edit_modes=edit_modes, PAINT_KEYS='')
        exec(compile(ast.Module(body=[function], type_ignores=[]), 'controls', 'exec'), ns)
        for family in EDIT_MODELS:
            for canvas in (False, True):
                result = ns['model_controls'](family, False, 'Standard', canvas)
                fibo = family.startswith('Fibo')
                self.assertEqual(result[11]['visible'], fibo)
                self.assertEqual(result[13]['visible'], fibo)
                self.assertEqual(result[15]['visible'], not fibo)


if __name__ == '__main__': unittest.main()
