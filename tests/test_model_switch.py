import ast
from pathlib import Path
from types import SimpleNamespace as NS
import tempfile
import unittest
from unittest.mock import Mock

from forge_qwen_edit import model_switch as M
from forge_qwen_edit.selection import validate_components


QWEN = 'qwen_image_2.1_Q8_0.gguf'
FIBO = 'fibo2_edit_turbo_int8_convrot.safetensors'
DEV = 'fibo2_dev_int8_convrot.safetensors'


def checkpoint(name):
    return NS(name=name, filename='/models/' + name, short_title=name + ' short', ids=[name, name + ' [hash]'])


class ModelSwitchTests(unittest.TestCase):
    def setUp(self):
        self.items = [checkpoint(n) for n in (QWEN, FIBO, DEV, 'sdxl.safetensors')]
        self.opts = NS(sd_model_checkpoint=QWEN, sd_checkpoint_dropdown_use_short=False,
                       forge_preset='qwen21', forge_checkpoint_qwen21=FIBO,
                       forge_checkpoint_fibo2=QWEN, forge_additional_modules=[], save=Mock())
        self.opts.set = lambda key, value: setattr(self.opts, key, value)
        self.shared = NS(opts=self.opts, config_filename='config.json')
        self.models = NS(checkpoints_list={item.name: item for item in self.items})
        self.calls = []

        def original_checkpoint(value, preset, save=True, refresh=True):
            self.calls.append(('checkpoint', value, preset))
            if self.opts.sd_model_checkpoint == value:
                return False
            self.opts.sd_model_checkpoint = value
            if preset:
                self.opts.set('forge_checkpoint_' + preset, value)
            return True

        def original_preset(preset, **kwargs):
            self.calls.append(('preset', preset, kwargs))
            if kwargs.get('layout_only'):
                return [{'__type__': 'update'}] * 22
            return [dict(value=getattr(self.opts, 'forge_checkpoint_' + preset, 'other')),
                    dict(value=['old modules'])] + [dict(value='keep setting')] * 20

        self.original_checkpoint = original_checkpoint
        self.original_preset = original_preset
        self.entry = NS(checkpoint_change=original_checkpoint, on_preset_change=original_preset, module_list={}, _load_presets=Mock())
        self.gr = NS(update=lambda **k: k, Error=ValueError)
        M.install(self.entry, self.shared, self.models, self.gr)

    def test_crossed_saved_presets_keep_current_model_and_recover_matching_family(self):
        self.assertEqual(M.choose_checkpoint('qwen21', QWEN, FIBO, self.items).name, QWEN)
        self.assertEqual(M.choose_checkpoint('fibo2', QWEN, QWEN, self.items).name, FIBO)
        self.assertEqual(M.choose_checkpoint('fibo2', DEV, FIBO, self.items).name, DEV)
        self.assertEqual(M.choose_checkpoint('fibo2', QWEN, DEV, self.items).name, DEV)

    def test_checkpoint_input_does_not_save_into_other_family_or_change_components(self):
        self.opts.forge_checkpoint_qwen21 = QWEN
        self.entry.checkpoint_change(FIBO, 'qwen21')
        self.assertEqual(self.opts.forge_checkpoint_fibo2, FIBO)
        self.assertEqual(self.opts.forge_checkpoint_qwen21, QWEN)
        self.assertEqual(self.opts.forge_additional_modules, [])
        self.assertEqual(self.calls[-1], ('checkpoint', FIBO, 'fibo2'))
        self.entry.checkpoint_change('sdxl.safetensors', 'fibo2')
        self.assertEqual(self.opts.forge_checkpoint_fibo2, FIBO)
        self.assertEqual(self.calls[-1][-1], None)

    def test_same_checkpoint_repairs_saved_slot_and_persists(self):
        self.entry.checkpoint_change(QWEN, 'fibo2')
        self.assertEqual(self.opts.forge_checkpoint_qwen21, QWEN)
        self.opts.save.assert_called_once()

    def test_manual_preset_cannot_restore_wrong_family_and_preserves_other_settings(self):
        result = self.entry.on_preset_change('fibo2')
        self.assertEqual(result[0]['value'], FIBO)
        self.assertEqual(result[1]['value'], [])  # No half pair when files are missing.
        self.assertEqual(result[2:], [dict(value='keep setting')] * 20)
        self.entry._load_presets.assert_called_once_with(FIBO, [], 'keep setting', 'fibo2')

    def test_valid_custom_vae_preserved_and_complete_installed_pair_used(self):
        with tempfile.TemporaryDirectory() as directory:
            names = ['qwen3vl_8b_int8_convrot.safetensors', 'qwen_image_2.1_vae_bf16.safetensors',
                     'texture_fix_vae_for_qwen_image_2.1_bf16.safetensors',
                     'qwen3vl_4b_int8_convrot.safetensors', 'flux2-vae.safetensors']
            for name in names:
                path = Path(directory) / name
                path.touch()
                self.entry.module_list[name] = path
            self.opts.forge_additional_modules = [names[0], names[2]]
            self.assertEqual(self.entry.on_preset_change('qwen21')[1]['value'], [names[0], names[2]])
            result = self.entry.on_preset_change('fibo2', autofill_components=True)
            self.assertEqual(result[1]['value'], names[3:])
            self.assertFalse(self.calls[-1][2]['autofill_components'])

    def test_layout_only_and_other_presets_untouched_reload_does_not_stack(self):
        result = self.entry.on_preset_change('qwen21', layout_only=True)
        self.assertTrue(all('value' not in item for item in result))
        self.assertEqual(self.opts.forge_checkpoint_qwen21, FIBO)
        self.assertEqual(self.entry.on_preset_change('sdxl')[0]['value'], 'other')
        self.entry._load_presets.assert_not_called()
        M.install(self.entry, self.shared, self.models, self.gr)
        self.assertIs(self.entry.checkpoint_change._image_edit_original, self.original_checkpoint)
        self.assertIs(self.entry.on_preset_change._image_edit_original, self.original_preset)

    def test_missing_or_ambiguous_checkpoints_do_not_change_selection(self):
        self.models.checkpoints_list = {QWEN: self.items[0]}
        with self.assertRaisesRegex(ValueError, 'Select an installed fibo2 checkpoint'):
            self.entry.on_preset_change('fibo2')
        self.assertEqual(self.opts.sd_model_checkpoint, QWEN)
        variants = [checkpoint('fibo2_edit_turbo_a.gguf'), checkpoint('fibo2_edit_turbo_b.gguf')]
        self.assertIsNone(M.choose_checkpoint('fibo2', QWEN, 'missing', variants))
        self.assertIs(M.choose_checkpoint('qwen21', self.items[0].filename, None, self.items), self.items[0])

    def test_check_model_setup_is_read_only(self):
        path = Path(__file__).parents[1] / 'forge_qwen_edit/model_bar.py'
        fn = next(n for n in ast.parse(path.read_text(encoding='utf-8')).body if getattr(n, 'name', '') == 'check_model_setup')
        entry = NS(refresh_models=Mock())
        status = Mock(return_value=('ready', True))
        namespace = dict(main_entry=entry, selection_status=status, gr=NS(Info=Mock()))
        exec(compile(ast.Module(body=[fn], type_ignores=[]), str(path), 'exec'), namespace)
        selected = ['my encoder', 'my vae']
        self.assertEqual(namespace['check_model_setup'](QWEN, selected), ('ready', True))
        self.assertEqual(selected, ['my encoder', 'my vae'])
        status.assert_called_once_with(QWEN, selected, False, None)

    def test_missing_vae_and_encoder_messages_name_the_files(self):
        adapter = M.adapter_for_checkpoint(FIBO)
        with tempfile.TemporaryDirectory() as directory:
            names = adapter.defaults[1:]
            available = {}
            for name in names:
                path = Path(directory) / name
                path.touch()
                available[name] = path
            with self.assertRaisesRegex(ValueError, 'Missing VAE: flux2-vae.safetensors'):
                validate_components(adapter, [names[0]], available)
            with self.assertRaisesRegex(ValueError, 'Missing text encoder: qwen3vl_4b_int8_convrot.safetensors'):
                validate_components(adapter, [names[1]], available)
            with self.assertRaisesRegex(ValueError, 'Selected file not found: flux2-vae.safetensors'):
                validate_components(adapter, list(names), {names[0]: available[names[0]]})

    def test_custom_names_require_opt_in_existing_pair_and_explicit_roles(self):
        adapter = M.adapter_for_checkpoint(FIBO)
        with tempfile.TemporaryDirectory() as directory:
            encoder, vae = 'my-finetuned-encoder.safetensors', 'my-fixed-decoder.safetensors'
            available = {}
            for name in (encoder, vae):
                path = Path(directory) / name
                path.touch()
                available[name] = path
            with self.assertRaisesRegex(ValueError, 'Missing'):
                validate_components(adapter, [vae, encoder], available)
            self.assertEqual(validate_components(adapter, [vae, encoder], available, True, vae), (encoder, vae))
            with self.assertRaisesRegex(ValueError, 'choose which selected file is the VAE'):
                validate_components(adapter, [vae, encoder], available, True, None)
            with self.assertRaisesRegex(ValueError, 'two selected files'):
                validate_components(adapter, [encoder], available, True, vae)
            available.pop(vae)
            with self.assertRaisesRegex(ValueError, 'Selected file not found'):
                validate_components(adapter, [vae, encoder], available, True, vae)

    def test_same_checkpoint_preset_never_replaces_custom_components(self):
        self.opts.forge_additional_modules = ['my-encoder.safetensors', 'fixed-decoder.safetensors']
        result = self.entry.on_preset_change('qwen21')
        self.assertEqual(result[1]['value'], self.opts.forge_additional_modules)

    def test_custom_recipe_restores_roles_and_legacy_recipe_turns_override_off(self):
        from forge_qwen_edit.adapters import EDIT_MODELS
        from forge_qwen_edit.selection import profiles_for
        path = Path(__file__).parents[1] / 'forge_qwen_edit/model_bar.py'
        functions = [n for n in ast.parse(path.read_text(encoding='utf-8')).body
                     if getattr(n, 'name', '') in ('import_recipe', 'import_handoff')]
        with tempfile.TemporaryDirectory() as directory:
            encoder, vae = 'custom-encoder.safetensors', 'custom-decoder.safetensors'
            available = {}
            for name in (encoder, vae):
                file = Path(directory) / name
                file.touch()
                available[name] = file
            entry = NS(module_list=available, forge_unet_storage_dtype_options=['Automatic'], _load_presets=Mock())
            recipe = dict(model_family='Fibo 2.0 Edit Turbo', model=FIBO, encoder=encoder, vae=vae,
                          custom_components=True, sampler='Euler', schedule='Simple', prompt='edit',
                          resolution=768, steps=4, seed=42, cfg=1)
            namespace = dict(__package__='forge_qwen_edit', gr=self.gr, read_recipe=lambda _: recipe,
                             EDIT_MODELS=EDIT_MODELS, ensure_backend=Mock(), sd_models=self.models,
                             main_entry=entry, shared=self.shared, profiles_for=profiles_for,
                             validate_components=validate_components)
            exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), 'exec'), namespace)
            restored = namespace['import_recipe']('recipe.png', QWEN, [])
            self.assertEqual(len(restored), 35)
            self.assertEqual(restored[8], [encoder, vae])
            self.assertEqual(restored[-2:], (True, dict(choices=[encoder, vae], value=vae, visible=True)))
            entry._load_presets.assert_called_once_with(FIBO, [encoder, vae], 'Automatic', 'fibo2')
            recipe.pop('custom_components')
            with self.assertRaisesRegex(ValueError, 'Missing'):
                namespace['import_recipe']('recipe.png', QWEN, [])
            recipe.update(encoder=EDIT_MODELS['Fibo 2.0 Edit Turbo'].defaults[1], vae=EDIT_MODELS['Fibo 2.0 Edit Turbo'].defaults[2])
            for name in (recipe['encoder'], recipe['vae']):
                file = Path(directory) / name
                file.touch()
                available[name] = file
            restored = namespace['import_recipe']('old-recipe.png', QWEN, [])
            self.assertFalse(restored[-2])
            self.assertFalse(restored[-1]['visible'])
            self.assertEqual(len(namespace['import_handoff'](None, QWEN, [])), 35)
            recipe.update(operation='canvas_crop')
            self.assertEqual(len(namespace['import_recipe']('crop.png', QWEN, [])), 35)


if __name__ == '__main__':
    unittest.main()
