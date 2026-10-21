"""Schedule validation and job-scoped RoPE geometry, without a GPU dependency."""
import unittest
from types import SimpleNamespace

import numpy as np

from forge_qwen_edit.sampling import validate_fibo_sampling, resolve_fibo_shift, fibo_rope_context
from forge_qwen_edit.workflow import validate_recipe


class Positions(np.ndarray):
    def clone(self):
        return self.copy()


class Embedder:
    def __init__(self):
        self.hooks = []

    def register_forward_pre_hook(self, hook):
        self.hooks.append(hook)
        return SimpleNamespace(remove=lambda: self.hooks.remove(hook))

    def __call__(self, ids):
        args = (ids,)
        for hook in self.hooks:
            args = hook(self, args)
        return args[0]


class SamplingTests(unittest.TestCase):
    def test_manual_and_image_size_schedules(self):
        self.assertEqual(resolve_fibo_shift("Manual", 1.15, 2048, 2048), 1.15)
        self.assertEqual(resolve_fibo_shift("Manual", 0.8, 768, 768), 0.8)
        for width, height, expected in ((544, 480, .6293229166666667), (800, 736, .8459895833333333), (1088, 992, 1.1703125), (1024, 1024, 1.15)):
            self.assertAlmostEqual(resolve_fibo_shift("Image-size adjusted", 1.15, width, height), expected)
        with self.assertRaises(ValueError):
            resolve_fibo_shift("Image-size adjusted", 1.15, 1018, 1018)

    def test_invalid_controls_fail_before_sampling(self):
        for value in (True, None, "bad", float("nan"), float("inf"), -.5, 5.01):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_fibo_sampling("Manual", value)
        with self.assertRaises(ValueError):
            validate_fibo_sampling("unknown", 1.15)
        with self.assertRaises(ValueError):
            validate_fibo_sampling("Manual", 1.15, "false")

    def test_recipe_old_defaults_and_new_settings(self):
        old = dict(model_family="Fibo 2.0 Edit Turbo", prompt="edit", steps=4, resolution=768, seed="12", cfg=1, sampler="Euler", schedule="Simple")
        restored = validate_recipe(old)
        self.assertEqual((restored['fibo_shift_mode'], restored['fibo_shift'], restored['fibo_rope']), ("Manual", 1.15, False))
        restored = validate_recipe(dict(old, fibo_shift_mode="Image-size adjusted", fibo_shift=.75, fibo_rope=True))
        self.assertEqual((restored['fibo_shift_mode'], restored['fibo_shift'], restored['fibo_rope']), ("Image-size adjusted", .75, True))
        with self.assertRaises(ValueError):
            validate_recipe(dict(old, fibo_shift=99))

    def test_rope_matches_upstream_positions_and_is_removed_after_errors(self):
        embedder = Embedder()
        model = SimpleNamespace(forge_objects=SimpleNamespace(unet=SimpleNamespace(model=SimpleNamespace(diffusion_model=SimpleNamespace(rope_embedder=embedder)))))
        # Gist tokens, target image and differently-sized reference: distinct
        # planes must stay distinct, while both images use the same XY scaling.
        ids = np.array([[[1, 0, 0], [256, 0, 0], [513, 1, 2], [514, 3, 4], [515, 2, 1]]], dtype=np.float32).view(Positions)
        original = ids.copy()
        expected = np.array([[[1, 0, 0], [256, 0, 0], [513, .8, 1.7], [514, 2.4, 3.4], [515, 1.6, .85]]], dtype=np.float32)
        for fail in (False, True):
            try:
                with fibo_rope_context(model, True):
                    np.testing.assert_allclose(embedder(ids), expected)
                    np.testing.assert_array_equal(ids, original)
                    if fail:
                        raise RuntimeError("cancelled")
            except RuntimeError as error:
                self.assertEqual(str(error), "cancelled")
            self.assertEqual(embedder.hooks, [])
            self.assertIs(embedder(ids), ids)
        with fibo_rope_context(None, False):
            pass
        del model.forge_objects.unet.model.diffusion_model.rope_embedder
        with self.assertRaisesRegex(ValueError, "does not expose RoPE"):
            with fibo_rope_context(model, True):
                self.fail("Unsupported backend must not silently ignore the control")


if __name__ == "__main__":
    unittest.main()
