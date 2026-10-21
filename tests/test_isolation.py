"""Exercise the production job scope without initializing Forge or the GPU."""

import ast
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import unittest


class IsolationTests(unittest.TestCase):
    def test_original_model_options_and_flags_restore_on_error(self):
        self.check_restoration(False)

    def test_new_main_bar_selection_during_job_is_not_overwritten(self):
        self.check_restoration(True)

    def check_restoration(self, user_changed_selection):
        tree = ast.parse((Path(__file__).resolve().parents[1] / "forge_qwen_edit/native.py").read_text())
        scope = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "isolated_options")
        saved = {"sd_model_checkpoint": "custom-model", "forge_additional_modules": ["custom-vae"], "randn_source": "GPU", "sd_checkpoint_hash": "original-hash"}
        shared = SimpleNamespace(opts=SimpleNamespace(data=saved.copy()))
        params = {"checkpoint_info": "original", "additional_modules": ["custom-vae"]}
        sd_models = SimpleNamespace(model_data=SimpleNamespace(forge_loading_parameters=params.copy()))
        flags = SimpleNamespace(qwen21_auto_shift=True, qwen21_prefix_cache=False, online_lora=True)
        refreshed = []
        def refresh():
            refreshed.append(True)
            sd_models.model_data.forge_loading_parameters = {"checkpoint_info": shared.opts.data["sd_model_checkpoint"]}
        namespace = dict(contextmanager=contextmanager, shared=shared, sd_models=sd_models, dynamic_args=flags, main_entry=SimpleNamespace(forge_unet_storage_dtype_options={"Automatic": (None, False)}, refresh_model_loading_parameters=refresh))
        exec(compile(ast.Module(body=[scope], type_ignores=[]), "isolated_options", "exec"), namespace)
        checkpoint = SimpleNamespace(name="qwen", filename="qwen.safetensors")
        with self.assertRaisesRegex(RuntimeError, "test failure"):
            with namespace["isolated_options"](checkpoint, ["new-encoder", "new-vae"]):
                self.assertEqual(shared.opts.data["sd_model_checkpoint"], "qwen")
                self.assertEqual(shared.opts.data["randn_source"], "CPU")
                shared.opts.data["sd_checkpoint_hash"] = "changed"
                flags.qwen21_auto_shift = False
                if user_changed_selection:
                    shared.opts.data["sd_model_checkpoint"] = "next-model"
                    shared.opts.data["forge_additional_modules"] = ["next-vae"]
                raise RuntimeError("test failure")
        if user_changed_selection:
            self.assertEqual(shared.opts.data["sd_model_checkpoint"], "next-model")
            self.assertEqual(shared.opts.data["forge_additional_modules"], ["next-vae"])
            self.assertEqual(shared.opts.data["randn_source"], "GPU")
            self.assertEqual(refreshed, [True])
            return
        self.assertEqual(shared.opts.data, saved)
        self.assertEqual(sd_models.model_data.forge_loading_parameters, params)
        self.assertTrue(flags.qwen21_auto_shift)
        self.assertFalse(flags.qwen21_prefix_cache)
        self.assertTrue(flags.online_lora)


if __name__ == "__main__":
    unittest.main()
