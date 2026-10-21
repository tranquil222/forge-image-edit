import hashlib
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

import numpy as np
from PIL import Image, ImageDraw
from PIL.PngImagePlugin import PngInfo

from forge_qwen_edit import adjustments as A


def payload(digest='a' * 64):
    return dict(version=1, id='test', base_sha256=digest,
        settings={c: dict(points=[[0, 0], [255, 255]], levels=[0, 1, 255, 0, 255]) for c in ('rgb', 'red', 'green', 'blue')},
        luts=[[min(255, n + 35) for n in range(256)] for _ in range(3)])


class AdjustmentTests(unittest.TestCase):
    def test_luts_and_feather_preserve_unpainted_rgba(self):
        source = Image.new('RGBA', (48, 32), (80, 100, 130, 123))
        mask = Image.new('L', source.size)
        ImageDraw.Draw(mask).rectangle((12, 8, 30, 25), fill=255)
        selection = A.encode_selection(mask, 3)
        import base64, io
        alpha = Image.open(io.BytesIO(base64.b64decode(selection['png']))).convert('L')
        output = A.apply_luts(source, payload()['luts'], alpha)
        before, after = np.array(source), np.array(output)
        np.testing.assert_array_equal(after[np.array(mask) == 0], before[np.array(mask) == 0])
        np.testing.assert_array_equal(after[..., 3], before[..., 3])
        self.assertGreater(int(after[16, 20, 0]), 110)
        self.assertGreater(int(after[8, 12, 0]), 80)
        self.assertLess(int(after[8, 12, 0]), 115)

    def test_persisted_selection_stale_file_and_legacy_mask(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'image.png'
            source = Image.new('RGBA', (24, 16), (10, 20, 30, 90))
            info = PngInfo(); selection = A.encode_selection(Image.new('L', source.size, 128))
            info.add_text(A.MASK_KEY, json.dumps(selection)); info.add_text('image_edit', json.dumps({'area_only': True}))
            source.save(path, pnginfo=info); digest = hashlib.sha256(path.read_bytes()).hexdigest()
            A._selections.clear()
            _, mask, saved = A.result_context(path, digest)
            self.assertEqual(mask.getpixel((0, 0)), 128); self.assertEqual(saved, selection)
            with self.assertRaisesRegex(ValueError, 'changed'):
                A.result_context(path, 'b' * 64)
            info = PngInfo(); info.add_text('image_edit', json.dumps({'area_only': True}))
            source.save(path, pnginfo=info)
            with self.assertRaisesRegex(ValueError, 'no saved mask'):
                A.result_context(path, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_invalid_tables_points_and_levels_are_rejected(self):
        valid = payload(); A.parse_adjustment(json.dumps(valid))
        for mutate in (
            lambda d: d['luts'][0].pop(), lambda d: d['luts'][0].__setitem__(0, 256),
            lambda d: d['settings']['red'].__setitem__('points', [[0, 0], [0, 20], [255, 255]]),
            lambda d: d['settings']['rgb']['levels'].__setitem__(1, float('nan')),
        ):
            value = payload(); mutate(value)
            with self.assertRaises(ValueError): A.parse_adjustment(json.dumps(value))

    def test_native_save_metadata_mask_and_original_file_retained(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source_path = root / 'before.png'
            source = Image.new('RGBA', (24, 16), (50, 70, 90, 127))
            recipe = dict(version=1, model_family='Fibo 2.0 Edit Turbo', prompt='change the hat',
                          seed='42', steps=4, cfg=1, sampler='Euler', schedule='Simple', resolution=768, area_only=True)
            selection = A.encode_selection(Image.new('L', source.size, 128))
            info = PngInfo(); info.add_text('image_edit', json.dumps(recipe)); info.add_text('Author', 'original author')
            info.add_text(A.MASK_KEY, json.dumps(selection)); source.save(source_path, pnginfo=info)
            before_bytes = source_path.read_bytes(); digest = hashlib.sha256(before_bytes).hexdigest()
            opts = types.SimpleNamespace(outdir_samples='', outdir_img2img_samples=str(root/'native'), enable_pnginfo=True)
            modules = types.ModuleType('modules'); saved_calls = []
            def save(image, directory, basename, **kwargs):
                saved_calls.append(kwargs); self.assertEqual(directory, str(root/'native'))
                path = root / ('corrected-' + str(len(saved_calls)) + '.png')
                pnginfo = PngInfo()
                if opts.enable_pnginfo:
                    for key, value in kwargs['existing_info'].items(): pnginfo.add_text(key, value)
                image.save(path, pnginfo=pnginfo)
                return str(path), None
            modules.images = types.SimpleNamespace(save_image=save)
            modules.shared = types.SimpleNamespace(opts=opts, data_path=root)
            with mock.patch.dict('sys.modules', modules=modules):
                result, path, _ = A.save_adjustment(source_path, json.dumps(payload(digest)), True)
                with Image.open(path) as saved:
                    self.assertEqual(saved.info['Author'], 'original author')
                    latest = json.loads(saved.info['image_edit'])
                    self.assertEqual(latest['prompt'], recipe['prompt'])
                    self.assertEqual(latest['postprocessing'][-1]['scope'], 'painted area')
                    self.assertIn(A.MASK_KEY, saved.info)
                self.assertEqual(source_path.read_bytes(), before_bytes)
                self.assertEqual(result.size, source.size)
                self.assertEqual(result.getpixel((0, 0)), (68, 88, 108, 127))
                opts.enable_pnginfo = False
                _, path, _ = A.save_adjustment(source_path, json.dumps(payload(digest)), False)
                with Image.open(path) as saved: self.assertEqual(saved.info, {})
                # Selection stays available in-session even when PNG metadata is off.
                _, mask, _ = A.result_context(path, hashlib.sha256(Path(path).read_bytes()).hexdigest())
                self.assertIsNotNone(mask)

    def test_whole_image_metadata_free_input_does_not_invent_generation_recipe(self):
        source = Image.new('RGB', (16, 16), (70, 90, 110))
        source.info['Author'] = 'test'
        fields, binary, recipe = A.adjustment_metadata(source, payload(), False)
        self.assertNotIn('Author', fields); self.assertNotIn('image_edit', fields)
        self.assertEqual(json.loads(fields['image_edit_adjustment'])['scope'], 'whole image')
        self.assertEqual(recipe, {})
        self.assertEqual(A.apply_luts(source, payload()['luts']).getpixel((0, 0)), (105, 125, 145, 255))


if __name__ == '__main__': unittest.main()
