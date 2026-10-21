"""Exercise pinned mixed-publisher sets without downloading model weights."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


class ModelDownloadTests(unittest.TestCase):
    def test_mixed_publisher_pins_and_standard_directories(self):
        spec = importlib.util.spec_from_file_location('image_edit_models_test', ROOT/'tools/models.py')
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'launch.py').touch()
            (root/'tools').mkdir()
            cached = root/'cached-weights'
            cached.write_bytes(b'test weights')
            common = dict(bytes=cached.stat().st_size, sha256=hashlib.sha256(cached.read_bytes()).hexdigest())
            catalog = {'small': dict(repository='publisher/checkpoint', revision='checkpoint-pin', model_card='https://huggingface.co/publisher/checkpoint', files=[
                dict(common, source='model.gguf', kind='checkpoint'),
                dict(common, source='text_encoders/encoder.safetensors', kind='encoder', repository='publisher/components', revision='component-pin'),
                dict(common, source='vae/vae.safetensors', kind='vae', repository='publisher/components', revision='component-pin'),
            ])}
            (root/'models.json').write_text(json.dumps(catalog))
            hub = types.ModuleType('huggingface_hub')
            hub.hf_hub_download = mock.Mock(return_value=str(cached))
            with mock.patch.object(helper, '__file__', str(root/'tools/models.py')), mock.patch.dict(sys.modules, huggingface_hub=hub), mock.patch.object(sys, 'argv', ['models.py', '--forge-root', str(root), '--model', 'small', '--download']), mock.patch('builtins.print'):
                helper.main()
                self.assertEqual(hub.hf_hub_download.call_args_list, [
                    mock.call(repo_id='publisher/checkpoint', filename='model.gguf', revision='checkpoint-pin'),
                    mock.call(repo_id='publisher/components', filename='text_encoders/encoder.safetensors', revision='component-pin'),
                    mock.call(repo_id='publisher/components', filename='vae/vae.safetensors', revision='component-pin'),
                ])
                for name in ('Stable-diffusion/model.gguf', 'text_encoder/encoder.safetensors', 'VAE/vae.safetensors'):
                    self.assertEqual((root/'models'/name).read_bytes(), cached.read_bytes())
                hub.hf_hub_download.reset_mock()
                helper.main()
                hub.hf_hub_download.assert_not_called()
                installed = root/'models/Stable-diffusion/model.gguf'
                installed.write_bytes(b'other weights')
                with self.assertRaisesRegex(SystemExit, 'refusing to overwrite'):
                    helper.main()
                self.assertEqual(installed.read_bytes(), b'other weights')


if __name__ == '__main__':
    unittest.main()
