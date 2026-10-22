import ast
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from forge_qwen_edit.adapters import EDIT_MODELS
from forge_qwen_edit.selection import profiles_for
from forge_qwen_edit.workflow import validate_recipe


class SamplingChoicesTests(unittest.TestCase):
    def test_model_changes_use_live_forge_lists_without_family_filters(self):
        path = Path(__file__).parents[1] / 'forge_qwen_edit/model_bar.py'
        functions = [n for n in ast.parse(path.read_text(encoding='utf-8')).body
                     if getattr(n,'name','') in ('sampling_choices','observe_checkpoint')]
        sampler_list = [NS(name=s) for s in ('Euler','Res Multistep','Heun','Third party sampler')]
        schedulers = {s:NS(label=s) for s in ('Simple','CyberZit Quality','Automatic','Beta','Third party schedule')}
        schedulers['alias'] = schedulers['Beta']
        modules = NS(sd_samplers=NS(all_samplers=sampler_list), sd_schedulers=NS(schedulers_map=schedulers))
        namespace = dict(gr=NS(update=lambda **kw:kw), profiles_for=profiles_for,
            selection_status=lambda *a: ('ready',True), resolve_checkpoint=lambda v: NS(name=v))
        exec(compile(ast.Module(body=functions,type_ignores=[]),str(path),'exec'),namespace)
        with patch.dict(sys.modules,{'modules':modules}):
            for adapter in EDIT_MODELS.values():
                namespace['adapter_for_checkpoint'] = lambda _, adapter=adapter: adapter
                for previous in ('',adapter.defaults[0]):
                    result = namespace['observe_checkpoint'](adapter.defaults[0],[],previous)
                    self.assertEqual(result[3]['choices'],[s.name for s in sampler_list])
                    self.assertEqual(result[4]['choices'],list(schedulers)[:-1])
                    self.assertTrue(result[3]['interactive']); self.assertTrue(result[4]['interactive'])
                    if previous: self.assertNotIn('value',result[3]); self.assertNotIn('value',result[4])
            sampler_list.append(NS(name='New registration'))
            self.assertIn('New registration',namespace['sampling_choices']()[0])

    def test_recipe_accepts_installed_custom_names_but_rejects_invalid_types(self):
        recipe = dict(prompt='edit',steps=4,seed='42',cfg=1,resolution=768,
                      sampler='Third party sampler',schedule='Third party schedule')
        self.assertEqual(validate_recipe(recipe)['sampler'],recipe['sampler'])
        for key in ('sampler','schedule'):
            for value in ('',None,[],{}):
                with self.assertRaisesRegex(ValueError,'name'):
                    validate_recipe({**recipe,key:value})


if __name__ == '__main__': unittest.main()
