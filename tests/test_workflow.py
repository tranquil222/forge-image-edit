import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from PIL.PngImagePlugin import PngInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from forge_qwen_edit.workflow import cyberzit_quality_values, parse_seed, prepare_reference, read_recipe, reference_size


class WorkflowTests(unittest.TestCase):
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
