"""Regression: idle encoders must not crowd out GGUF dequantization workspace."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest import mock


class MemoryStagingTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((Path(__file__).resolve().parents[1]/'forge_qwen_edit/native.py').read_text())
        helper = next(n for n in tree.body if getattr(n, 'name', '') == 'release_edit_encoder')
        original = next(n for n in tree.body if getattr(n, 'name', '') == 'EditProcessing')
        method = next(n for n in original.body if getattr(n, 'name', '') == 'setup_conds')
        method.decorator_list = []
        wrapper = ast.ClassDef(name='EditProcessing', bases=[], keywords=[], body=[method], decorator_list=[])
        self.events = []
        self.patcher = NS(load_device=NS(type='cuda'))
        self.other_models = [NS(model=object()), NS(model=object())]
        self.memory = NS(current_loaded_models=[self.other_models[0], NS(model=self.patcher), self.other_models[1]],
            free_memory=mock.Mock(side_effect=lambda *a, **k: self.events.append('offload')),
            load_model_gpu=lambda patcher: self.events.append('load'))
        parser = NS(ScheduledPromptConditioning=lambda *args: args,
                    MulticondLearnedConditioning=lambda **kwargs: kwargs,
                    ComposableScheduledPromptConditioning=lambda args: args)
        namespace = dict(memory_management=self.memory, check_cancelled=lambda: None,
                         get_adapter=lambda _: NS(key='fibo2'), prompt_parser=parser, dynamic_args=NS())
        exec(compile(ast.fix_missing_locations(ast.Module(body=[helper, wrapper], type_ignores=[])), 'memory_staging', 'exec'), namespace)
        self.release = namespace['release_edit_encoder']
        self.processor = namespace['EditProcessing']()
        def encode(prompts, images):
            self.events.append(prompts[0])
            return [prompts[0]+' conditioning']
        self.processor.__dict__.update(steps=4, edit_conditioning=None, edit_unconditional=None,
            edit_references=[], edit_family='Fibo', prompt='positive', negative_prompt='negative',
            cfg_scale=5, edit_release_encoder=True,
            sd_model=NS(forge_objects=NS(vae=None, clip=NS(patcher=self.patcher)), text_processing_engine_fibo=encode))

    def test_release_after_both_branches_preserves_conditioning_and_other_models(self):
        self.processor.setup_conds()
        self.assertEqual(self.events, ['load', 'positive', 'negative', 'offload'])
        self.assertEqual(self.memory.free_memory.call_args.kwargs['keep_loaded'], self.other_models)
        self.assertEqual(self.processor.edit_conditioning, 'positive conditioning')
        self.assertEqual(self.processor.edit_unconditional, 'negative conditioning')
        self.processor.setup_conds()
        self.assertEqual(self.events, ['load', 'positive', 'negative', 'offload'])

    def test_regular_models_keep_normal_forge_residency(self):
        self.processor.edit_release_encoder = False
        self.processor.setup_conds()
        self.memory.free_memory.assert_not_called()

    def test_cpu_encoder_is_left_alone(self):
        self.patcher.load_device.type = 'cpu'
        self.release(self.patcher)
        self.memory.free_memory.assert_not_called()


if __name__ == '__main__':unittest.main()
