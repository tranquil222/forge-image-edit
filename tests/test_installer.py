import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

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


if __name__ == '__main__':
    unittest.main()
