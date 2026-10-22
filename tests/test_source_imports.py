import ast
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image
from PIL.PngImagePlugin import PngInfo
from forge_qwen_edit.source_imports import recent_image, random_image
from forge_qwen_edit import source_imports


class SavedSourceTests(unittest.TestCase):
    def make_image(self, root, name, modified):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        info = PngInfo()
        info.add_text('parameters', 'Original prompt with metadata')
        Image.new('RGB', (16, 16), 'red').save(path, pnginfo=info)
        os.utime(path, ns=(modified, modified))
        return path

    def test_newest_then_older_across_dated_subfolders_with_exact_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            older = self.make_image(root, '2026-10-21/older.PNG', 1000000000)
            newest = self.make_image(root, '2026-10-22/new ü #2.png', 3000000000)
            middle = self.make_image(root, 'middle.png', 2000000000)
            expected = newest.read_bytes()
            cursor = ''
            for wanted in (newest, middle, older):
                path, cursor = recent_image(root, cursor)
                self.assertEqual(path, wanted)
                self.assertIsInstance(json.loads(cursor)['modified'], str)
            self.assertEqual(newest.read_bytes(), expected)
            with Image.open(newest) as image:
                self.assertEqual(image.info['parameters'], 'Original prompt with metadata')
            with self.assertRaisesRegex(ValueError, 'No older saved images'):
                recent_image(root, cursor)

    def test_tied_times_deleted_files_and_new_arrivals_do_not_repeat_or_skip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            a = self.make_image(root, 'a.png', 1000000000)
            b = self.make_image(root, 'b.png', 1000000000)
            c = self.make_image(root, 'c.png', 1000000000)
            path, cursor = recent_image(root)
            self.assertEqual(path, c)
            c.unlink()
            b.unlink()
            self.make_image(root, 'new arrival.png', 5000000000)
            self.assertEqual(recent_image(root, cursor)[0], a)

    def test_skips_empty_corrupt_and_non_image_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            valid = self.make_image(root, 'valid.png', 1000000000)
            (root / 'empty.png').touch()
            (root / 'broken.png').write_text('not an image')
            (root / 'newest.txt').write_text('not an image')
            self.assertEqual(recent_image(root)[0], valid)
            valid.unlink()
            with self.assertRaisesRegex(ValueError, 'No readable saved images'):
                recent_image(root)
            with self.assertRaisesRegex(ValueError, 'No saved images'):
                recent_image(root / 'missing')

    def test_folder_change_restarts_history_and_cursor_is_not_a_file_request(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            first = self.make_image(root / 'first', 'image.png', 1000000000)
            second = self.make_image(root / 'second', 'image.png', 2000000000)
            _, cursor = recent_image(first.parent)
            self.assertEqual(recent_image(second.parent, cursor)[0], second)
            altered = json.loads(cursor)
            altered['name'] = '../../outside.png'
            with self.assertRaisesRegex(ValueError, 'No older saved images'):
                recent_image(first.parent, json.dumps(altered))
            for value in ('invalid', 'null', '[]'):
                with self.assertRaisesRegex(ValueError, 'history could not be read'):
                    recent_image(root, value)

    def test_ui_uses_configured_folder_and_global_override_without_gallery_state(self):
        path = Path(__file__).parents[1] / 'forge_qwen_edit/ui.py'
        functions = [node for node in ast.parse(path.read_text(encoding='utf-8')).body
                     if getattr(node, 'name', '') in ('txt2img_output_folder', 'recent_txt2img_file', 'random_txt2img_file')]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            usual = self.make_image(root / 'txt2img', 'usual.png', 1000000000)
            override = self.make_image(root / 'custom', 'override.png', 2000000000)
            opts = SimpleNamespace(outdir_samples='', outdir_txt2img_samples='txt2img')
            namespace = dict(__package__='forge_qwen_edit', Path=Path,
                shared=SimpleNamespace(opts=opts, script_path=str(root)), gr=SimpleNamespace(Error=ValueError))
            exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), 'exec'), namespace)
            self.assertEqual(namespace['recent_txt2img_file']()[0], str(usual))
            opts.outdir_samples = str(override.parent)
            self.assertEqual(namespace['recent_txt2img_file']()[0], str(override))
            self.assertEqual(namespace['recent_txt2img_file']('', '  "txt2img"  ')[0], str(usual))
            self.assertEqual(namespace['random_txt2img_file']('txt2img'), str(usual))
            self.assertEqual(namespace['random_txt2img_file']('  '), str(override))
            with self.assertRaisesRegex(ValueError, 'No saved images'):
                namespace['random_txt2img_file']('does-not-exist')

    def test_random_uses_readable_saved_files_without_modifying_them(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            one = self.make_image(root, 'one.png', 1000000000)
            two = self.make_image(root, 'dated/two.png', 2000000000)
            (root / 'broken.png').write_text('not an image')
            original = {p: p.read_bytes() for p in (one, two)}
            for wanted in (one, two):
                def order(items):
                    items.sort(key=lambda item: (0 if item[1] == 'broken.png' else 1 if root / item[1] == wanted else 2))
                with patch('forge_qwen_edit.source_imports.random.shuffle', side_effect=order) as shuffle:
                    self.assertEqual(random_image(root), wanted)
                    shuffle.assert_called_once()
            self.assertEqual({p: p.read_bytes() for p in original}, original)

    def test_repeated_imports_reuse_catalog_and_restart_sees_new_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            older = self.make_image(root, 'older.png', 1000000000)
            newer = self.make_image(root, 'newer.png', 2000000000)
            with patch.object(source_imports, '_scan_images', wraps=source_imports._scan_images) as scan:
                self.assertEqual(recent_image(root)[0], newer)
                _, cursor = recent_image(root)
                self.assertEqual(scan.call_count, 2)
                random_image(root)
                self.assertEqual(recent_image(root, cursor)[0], older)
                self.assertEqual(scan.call_count, 2)
                newest = self.make_image(root, 'newest.png', 3000000000)
                self.assertEqual(recent_image(root)[0], newest)
                self.assertEqual(scan.call_count, 3)

    def test_catalog_expiry_and_bounded_folder_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            with patch.object(source_imports, '_catalogs', source_imports.OrderedDict()), \
                 patch.object(source_imports.time, 'monotonic', return_value=100) as clock, \
                 patch.object(source_imports, '_scan_images', wraps=source_imports._scan_images) as scan:
                one = self.make_image(root, 'one.png', 1000000000)
                self.assertEqual(random_image(root), one)
                two = self.make_image(root, 'two.png', 2000000000)
                clock.return_value += source_imports._catalog_seconds
                self.assertIn(random_image(root), (one, two))
                self.assertEqual(scan.call_count, 2)
                self.assertEqual(len(source_imports.image_candidates(root)[1]), 2)
                for i in range(source_imports._catalog_limit + 1):
                    self.make_image(root / str(i), 'image.png', 1000000000)
                    random_image(root / str(i))
                self.assertEqual(len(source_imports._catalogs), source_imports._catalog_limit)


if __name__ == '__main__':
    unittest.main()
