import contextlib
import ast
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class InstallerTests(unittest.TestCase):
    def test_shipped_patch_checksums_survive_checkout_line_endings(self):
        for path in (ROOT/'backend-support').glob('manifest*.json'):
            data = json.loads(path.read_text())
            patch = (path.parent/data['patch']).read_bytes().replace(b'\r\n', b'\n')
            self.assertEqual(hashlib.sha256(patch).hexdigest(), data['patch_sha256'])
            self.assertTrue(data['files'])

    def test_customized_file_never_reaches_git_apply(self):
        helper = load('image_edit_backend_test', ROOT/'tools/backend_support.py')
        manifest = json.loads((ROOT/'backend-support/manifest.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'launch.py').write_text('# fixture')
            (root/'backend').mkdir()
            sentinel = root/'backend/args.py'
            sentinel.write_text('# personal changes')
            with mock.patch.object(helper.subprocess, 'check_output', return_value=manifest['base_commit']), mock.patch.object(helper.subprocess, 'run') as run, mock.patch('sys.argv', ['backend_support.py','--forge-root',directory,'--apply']):
                with self.assertRaisesRegex(SystemExit, 'Customized or unsupported file'):
                    helper.main()
            run.assert_not_called()
            self.assertEqual(sentinel.read_text(), '# personal changes')
            self.assertFalse((root/'image-edit-backups').exists())

    def test_unknown_build_leaves_backend_untouched(self):
        helper = load('image_edit_backend_unknown', ROOT/'tools/backend_support.py')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'launch.py').write_text('# fixture')
            with mock.patch.object(helper.subprocess,'check_output',return_value='0'*40), mock.patch.object(helper.subprocess,'run') as run, mock.patch('sys.argv',['backend_support.py','--forge-root',directory,'--apply']):
                with self.assertRaisesRegex(SystemExit,'Backend setup required'):
                    helper.main()
            run.assert_not_called()
            self.assertEqual([p.name for p in root.iterdir()], ['launch.py'])

    def test_url_installer_skips_unsupported_build_without_failing_forge(self):
        installer = load('image_edit_install_test', ROOT/'install.py')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'launch.py').write_text('# fixture')
            (root/'modules').mkdir()
            checked = subprocess.CompletedProcess([],1,'','Backend setup required.')
            with mock.patch.object(Path,'cwd',return_value=root), mock.patch.object(installer.subprocess,'run',return_value=checked) as run, mock.patch.dict(installer.os.environ,{'FORGE_IMAGE_EDIT_SKIP_BACKEND':'0'}), contextlib.redirect_stdout(io.StringIO()) as output:
                installer.main()
            self.assertEqual(run.call_count,1)
            self.assertNotIn('--apply',run.call_args.args[0])
            self.assertIn('No backend files changed',output.getvalue())

    def test_setup_message_distinguishes_missing_files_from_pending_restart(self):
        tree = ast.parse((ROOT/'forge_qwen_edit/model_bar.py').read_text(encoding='utf-8'))
        function = next(n for n in tree.body if getattr(n, 'name', '') == 'ensure_backend')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = SimpleNamespace(dynamic_args=SimpleNamespace())
            presets = SimpleNamespace(PresetArch=SimpleNamespace(__members__={}))
            ns = dict(Path=Path, shared=SimpleNamespace(script_path=directory))
            exec(compile(ast.Module(body=[function], type_ignores=[]), 'backend-check', 'exec'), ns)
            with mock.patch.dict('sys.modules', {'backend.args': args, 'modules_forge.presets': presets}):
                adapter = SimpleNamespace(key='fibo2', flag='fibo2')
                with self.assertRaisesRegex(ValueError, 'Native model support is missing'):
                    ns['ensure_backend'](adapter)
                for name in ('backend/diffusion_engine/fibo2.py', 'backend/nn/fibo2.py', 'backend/text_processing/fibo2_engine.py'):
                    path=root/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text('# fixture')
                with self.assertRaisesRegex(ValueError, 'only partly installed'):
                    ns['ensure_backend'](adapter)
                (root/'backend/args.py').write_text('class dynamic_args:\n    fibo2: bool = False\n    qwen21_auto_shift = True\n    qwen21_prefix_cache = True\n')
                (root/'modules_forge').mkdir(exist_ok=True)
                (root/'modules_forge/presets.py').write_text('class PresetArch:\n    fibo2 = 15\n')
                with self.assertRaisesRegex(ValueError, 'registration is not loaded'):
                    ns['ensure_backend'](adapter)
                args.dynamic_args.fibo2=False; args.dynamic_args.qwen21_prefix_cache=True; args.dynamic_args.qwen21_auto_shift=True
                presets.PresetArch.__members__['fibo2']=15
                ns['ensure_backend'](adapter)

    def test_known_original_and_patched_files_can_mix_but_custom_files_cannot(self):
        helper = load('image_edit_partial_signatures', ROOT/'tools/backend_support.py')
        sha = lambda data: hashlib.sha256(data.encode()).hexdigest()
        manifest = {'files': [dict(path='args.py', before_sha256=sha('old'), after_sha256=sha('patched')),
                              dict(path='new.py', before_sha256=None, after_sha256=sha('added'))]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'args.py').write_text('old'); (root/'new.py').write_text('added')
            self.assertEqual(helper.unknown_files(root, manifest), [])
            (root/'args.py').write_text('patched')
            self.assertEqual(helper.unknown_files(root, manifest), [])
            (root/'args.py').write_text('personal modification')
            self.assertEqual(helper.unknown_files(root, manifest), ['args.py'])
            manifest['files'][0]['path'] = '../outside.py'
            self.assertEqual(helper.unknown_files(root, manifest), ['../outside.py'])

    def test_unknown_build_report_includes_revision_and_mismatched_paths(self):
        helper = load('image_edit_backend_report', ROOT/'tools/backend_support.py')
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory)/'launch.py').write_text('# fixture')
            with mock.patch.object(helper.subprocess,'check_output',return_value='1'*40), mock.patch('sys.argv',['backend_support.py','--forge-root',directory]), contextlib.redirect_stdout(io.StringIO()) as output:
                with self.assertRaisesRegex(SystemExit,'repeated restarts will not fix'):
                    helper.main()
            self.assertIn('Forge revision: ' + '1'*40, output.getvalue())
            self.assertIn('backend/args.py', output.getvalue())


if __name__ == '__main__':
    unittest.main()
