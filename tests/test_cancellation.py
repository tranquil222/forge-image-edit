"""Exercise the cancellation boundary without loading Forge or using the GPU."""

import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from forge_qwen_edit.sampling import fibo_rope_context, qwen_rope_context
from forge_qwen_edit.adapters import get_adapter


class CancellationTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] / "forge_qwen_edit/native.py").read_text())
        nodes = [n for n in tree.body if getattr(n, "name", "") in ("EditCancelled", "check_cancelled")]
        original = next(n for n in tree.body if getattr(n, "name", "") == "EditProcessing")
        sample = next(n for n in original.body if getattr(n, "name", "") == "sample")
        wrapper = ast.ClassDef(name="EditProcessing", bases=[ast.Name(id="Base", ctx=ast.Load())], keywords=[], body=[sample], decorator_list=[])
        self.state = SimpleNamespace(interrupted=False, skipped=False)
        self.calls = []
        self.result = object()
        self.interrupt_during_sample = False
        owner = self

        class Base:
            def sample(self, *args, **kwargs):
                owner.calls.append((args, kwargs))
                if owner.interrupt_during_sample:
                    owner.state.interrupted = True
                return owner.result

        ns = dict(shared=SimpleNamespace(state=self.state), Base=Base, fibo_rope_context=fibo_rope_context,
                  qwen_rope_context=qwen_rope_context, get_adapter=get_adapter,
                  dynamic_args=SimpleNamespace(ref_latents=[], image_slots=[]))
        module = ast.fix_missing_locations(ast.Module(body=[*nodes, wrapper], type_ignores=[]))
        exec(compile(module, "cancellation_boundary", "exec"), ns)
        self.processor = ns["EditProcessing"]()
        self.processor.sd_model = None
        self.processor.edit_family = 'Qwen Image 2.1'
        self.cancelled = ns["EditCancelled"]

    def test_cancel_before_sample_never_calls_sampler(self):
        self.state.interrupted = True
        with self.assertRaises(self.cancelled):
            self.processor.sample()
        self.assertEqual(self.calls, [])

    def test_cancel_at_first_step_handles_none_latent(self):
        self.result = None
        self.interrupt_during_sample = True
        with self.assertRaises(self.cancelled):
            self.processor.sample()

    def test_cancel_discards_partial_latent(self):
        self.interrupt_during_sample = True
        with self.assertRaises(self.cancelled):
            self.processor.sample()

    def test_missing_latent_without_cancel_is_still_an_error(self):
        self.result = None
        with self.assertRaisesRegex(RuntimeError, "no image latents"):
            self.processor.sample()

    def test_success_preserves_sample_and_arguments(self):
        self.assertIs(self.processor.sample("conditioning", seed=17), self.result)
        self.assertEqual(self.calls, [(("conditioning",), {"seed": 17})])


if __name__ == "__main__":
    unittest.main()
