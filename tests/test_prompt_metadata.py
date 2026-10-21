import json
from pathlib import Path
import sys
import unittest

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from forge_qwen_edit.metadata import HISTORY_KEY, build_metadata
from forge_qwen_edit.prompt_metadata import original_prompts


def node(kind, **inputs):
    return {"class_type": kind, "inputs": inputs}


class PromptMetadataTests(unittest.TestCase):
    def image(self, **info):
        image = Image.new("RGB", (32, 32))
        image.info.update(info)
        return image

    def prompts(self, graph):
        return [text for _, text in original_prompts(self.image(prompt=json.dumps(graph))) ]

    def test_forge_multiline_positive_excludes_negative_and_settings(self):
        image = self.image(parameters="A kitchen, (blue tiles:1.2)\nAn apple\nNegative prompt: bad hands\nSteps: 20, Sampler: Euler, Seed: 42")
        self.assertEqual(original_prompts(image)[0][1], "A kitchen, (blue tiles:1.2)\nAn apple")
        image.info["parameters"] = "An apple\nSteps: 20, Seed: 42"
        self.assertEqual(original_prompts(image)[0][1], "An apple")

    def test_edited_image_prefers_original_history_not_edit_instruction(self):
        image = self.image(parameters="Original kitchen\nSteps: 20, Seed: 42")
        fields, _ = build_metadata(image, {"version": 1, "model_family": "Fibo 2.0 Edit Turbo"}, "fill gray area\nSteps: 4, Seed: 7")
        image.info = fields
        self.assertEqual(original_prompts(image)[0][1], "Original kitchen")
        fields, _ = build_metadata(image, {"version": 1, "model_family": "Fibo 2.0 Edit Turbo"}, "another edit", False)
        image.info = fields
        self.assertEqual(original_prompts(image), [])

    def test_comfy_output_branch_excludes_negative_and_disconnected_encoders(self):
        graph = {"1": node("CLIPTextEncode", text="positive kitchen"), "2": node("CLIPTextEncode", text="negative hands"),
                 "3": node("KSampler", positive=["1", 0], negative=["2", 0]),
                 "4": node("VAEDecode", samples=["3", 0]), "5": node("SaveImage", images=["4", 0]),
                 "6": node("CLIPTextEncode", text="disconnected"), "7": node("KSampler", positive=["6", 0])}
        self.assertEqual(self.prompts(graph), ["positive kitchen"])

    def test_comfy_linked_string_and_custom_guider(self):
        graph = {"1": node("PrimitiveStringMultiline", value="低角度厨房"),
                 "2": node("CLIPTextEncodeFlux", clip_l="低角度厨房", t5xxl=["1", 0]),
                 "3": node("BasicGuider", conditioning=["2", 0]),
                 "4": node("SamplerCustomAdvanced", guider=["3", 0]),
                 "5": node("SaveImage", images=["4", 0])}
        self.assertEqual(self.prompts(graph), ["低角度厨房"])

    def test_multiple_positive_branches_are_separate_choices(self):
        graph = {"1": node("CLIPTextEncodeSDXL", text_g="global scene", text_l="local detail"),
                 "2": node("KSampler", positive=["1", 0])}
        self.assertEqual(set(self.prompts(graph)), {"global scene", "local detail"})

    def test_qwen_positive_text_not_negative_or_model_paths(self):
        graph = {"1": node("TextEncodeQwenImage21", prompt="change the sky", negative_prompt="bad sky", clip=["3", 0]),
                 "2": node("KSampler", positive=["1", 0], negative=["1", 1]),
                 "3": node("CLIPLoader", clip_name="model.safetensors")}
        self.assertEqual(self.prompts(graph), ["change the sky"])

    def test_comfy_original_survives_plugin_edit_history(self):
        graph = {"1": node("CLIPTextEncode", text="original apple"), "2": node("KSampler", positive=["1", 0])}
        image = self.image(prompt=json.dumps(graph))
        fields, _ = build_metadata(image, {"version": 1, "model_family": "Qwen Image 2.1"}, "remove apple")
        image.info = fields
        self.assertEqual(original_prompts(image)[0][1], "original apple")

    def test_empty_unsupported_and_cyclic_metadata_does_not_guess(self):
        for info in ({}, {"prompt": "{broken"}, {"prompt": "[]"}, {"workflow": '{"nodes": []}'},
                     {HISTORY_KEY: "{}", "image_edit": "{}", "parameters": "edit instruction"}):
            self.assertEqual(original_prompts(self.image(**info)), [])
        self.assertEqual(self.prompts({"1": node("KSampler", positive=["2", 0]),
                                      "2": node("ConditioningCombine", conditioning_1=["2", 0])}), [])

    def test_exif_original_prompt(self):
        exif = Image.Exif()
        exif[34665] = {37510: b"UNICODE\x00" + "苹果厨房\nSteps: 4, Seed: 8".encode("utf-16-be")}
        self.assertEqual(original_prompts(self.image(exif=exif.tobytes()))[0][1], "苹果厨房")


if __name__ == "__main__":
    unittest.main()
