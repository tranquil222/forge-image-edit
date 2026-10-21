import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from PIL.PngImagePlugin import PngInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from forge_qwen_edit.workflow import cyberzit_quality_values, parse_seed, prepare_reference, read_recipe, reference_size, reference_content_box
from forge_qwen_edit.workflow import output_resize_size, prepare_sized_reference


class WorkflowTests(unittest.TestCase):
    def test_custom_output_size_keeps_portrait_ratio_and_unpads_to_exact_dimensions(self):
        source = Image.new('RGBA', (1024, 1280), (100, 20, 30, 50))
        for settings, expected in ((dict(mode='Resize to', width=1025, height=1281), (1025, 1281)),
                                   (dict(mode='Resize by', scale=1.5), (1536, 1920))):
            size = output_resize_size(source.size, settings)
            self.assertEqual(size, expected)
            reference = prepare_sized_reference(source, size)
            box = reference_content_box(*size, 0)
            self.assertEqual(reference.crop(box).size, expected)
            self.assertEqual(reference.size[0] % 32, 0)
            self.assertEqual(reference.size[1] % 32, 0)
            self.assertEqual(reference.getpixel((30, 30))[3], 50)
        self.assertEqual(source.size, (1024, 1280))

    def test_invalid_output_sizes_never_stretch_or_allocate_excessive_images(self):
        for settings in (dict(width=1024, height=1024), dict(width=float('nan'), height=1280),
                         dict(width=True, height=1280), dict(width=4096, height=5120),
                         dict(mode='Resize by', scale=8), dict(mode='Resize by', scale=False),
                         dict(mode='bad'), dict(width=32.5, height=40.625)):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                output_resize_size((1024, 1280), settings)
        with self.assertRaises(ValueError):
            output_resize_size((0, 0), dict(width=1024, height=1024))

    def test_reference_matches_comfy_sizing(self):
        self.assertEqual(reference_size(768, 768, 768), (768, 768))
        self.assertEqual(reference_size(1024, 768, 768), (896, 672))
        self.assertEqual(reference_size(1200, 800, 0), (1216, 800))
        self.assertEqual(reference_size(1, 99999, 0)[0], 32)

    def test_alpha_survives_reference_preparation(self):
        image = Image.new("RGBA", (90, 90), (100, 20, 30, 50))
        prepared = prepare_reference(image, 0)
        self.assertEqual(prepared.mode, "RGBA")
        self.assertEqual(prepared.size, (96, 96))
        self.assertEqual(prepared.getpixel((40, 40))[3], 50)

    def test_portrait_is_padded_not_stretched_to_model_grid(self):
        self.assertEqual(reference_size(1024, 1280, 768), (672, 864))
        self.assertEqual(reference_content_box(1024, 1280, 768), (0, 12, 672, 852))
        image = Image.effect_noise((1024, 1280), 30).convert('RGBA')
        prepared = prepare_reference(image, 768)
        content = prepared.crop(reference_content_box(*image.size, 768))
        self.assertEqual(content.size, (672, 840))
        self.assertEqual(content.tobytes(), image.resize((672, 840), Image.Resampling.LANCZOS).tobytes())

    def test_native_resolution_roundtrip_preserves_every_pixel(self):
        for size in ((91, 73), (1201, 803), (1, 35), (1024, 1280)):
            image = Image.effect_noise(size, 30).convert('RGBA')
            prepared = prepare_reference(image, 0)
            restored = prepared.crop(reference_content_box(*size, 0))
            self.assertEqual(restored.size, size)
            self.assertEqual(restored.tobytes(), image.tobytes())

    def test_quality_grid_matches_expected_eight_steps(self):
        expected = [1, 21/22, .9, 5/6, .75, 9/14, .5, .3, 0]
        for a, b in zip(cyberzit_quality_values(8), expected):
            self.assertAlmostEqual(a, b, places=14)
        for n in (1, 3, 25, 150):
            values = cyberzit_quality_values(n)
            self.assertEqual(len(values), n + 1)
            self.assertTrue(all(a > b for a, b in zip(values, values[1:])))

    def test_seed_keeps_all_64_bits(self):
        self.assertEqual(parse_seed("18446744073709551615"), 2**64 - 1)
        for value in ("1.5", "NaN", str(2**64), "-2"):
            with self.assertRaises(ValueError): parse_seed(value)

    def write_png(self, folder, graph):
        path = Path(folder) / "recipe.png"
        info = PngInfo()
        info.add_text("prompt", json.dumps(graph))
        Image.new("RGB", (32, 32)).save(path, pnginfo=info)
        return path

    def graph(self):
        return {
            "a": {"class_type": "TextEncodeQwenImage21", "inputs": {"prompt": "change [sign] to A AND B", "negative_prompt": "", "resolution": 768}},
            "b": {"class_type": "KSampler", "inputs": {"steps": 8, "cfg": 1, "seed": 2**63+5, "denoise": 1, "sampler_name": "res_multistep", "scheduler": "cyberzit_quality"}},
            "c": {"class_type": "LoadImage", "inputs": {"image": "../../private.png"}},
        }

    def test_import_preserves_literal_prompt_and_seed_without_opening_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            recipe = read_recipe(self.write_png(folder, self.graph()))
        self.assertEqual(recipe["prompt"], "change [sign] to A AND B")
        self.assertEqual(recipe["seed"], str(2**63+5))
        self.assertEqual(recipe["schedule"], "CyberZit Quality")

    def test_import_does_not_guess_unsupported_or_multi_sampler_graphs(self):
        with tempfile.TemporaryDirectory() as folder:
            graph = self.graph()
            graph["d"] = graph["b"].copy()
            with self.assertRaises(ValueError): read_recipe(self.write_png(folder, graph))
            graph = self.graph()
            graph["b"]["inputs"]["denoise"] = .5
            with self.assertRaises(ValueError): read_recipe(self.write_png(folder, graph))


if __name__ == "__main__":
    unittest.main()
