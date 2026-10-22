"""Camera JPEG/TIFF metadata must survive the edit-to-PNG save path."""
import base64
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image
from PIL.PngImagePlugin import PngInfo
from PIL.TiffImagePlugin import IFDRational

from forge_qwen_edit.metadata import HISTORY_KEY, build_metadata, preserve_binary_metadata


class CameraMetadataTests(unittest.TestCase):
    def camera_image(self, format):
        exif = Image.Exif()
        exif[282], exif[283], exif[296] = IFDRational(300, 1), IFDRational(150, 1), 2
        exif[271] = "Test camera"
        stream = BytesIO()
        Image.new("RGB", (24, 16), (22, 44, 66)).save(stream, format=format, exif=exif)
        stream.seek(0)
        with Image.open(stream) as image:
            result = image.copy()
        # Real Pillow decoders, not a manually fabricated info dictionary.
        self.assertIsInstance(result.info["dpi"][0], IFDRational)
        return result

    def test_camera_resolution_history_and_png_roundtrip(self):
        for format in ("JPEG", "TIFF"):
            for family in ("Qwen Image 2.1", "Fibo 2.0 Edit Turbo", "Fibo 2.0 Dev"):
                with self.subTest(format=format, family=family), tempfile.TemporaryDirectory() as directory:
                    source = self.camera_image(format)
                    source.info.update(Author="camera owner", icc_profile=b"test-profile")
                    original_dpi = source.info["dpi"]
                    # Pillow's JPEG EXIF fallback uses XResolution for both axes.
                    expected_dpi = [300.0, 300.0 if format == "JPEG" else 150.0]
                    original_exif = source.info.get("exif")
                    recipe = dict(model_family=family, prompt="remove object", seed="42")
                    fields, binary = build_metadata(source, recipe, "edit parameters")
                    history = json.loads(fields[HISTORY_KEY])
                    self.assertEqual(history["original_metadata"]["dpi"], expected_dpi)
                    self.assertTrue(all(type(value) is float for value in binary["dpi"]))
                    self.assertIs(source.info["dpi"], original_dpi)
                    if original_exif:
                        self.assertEqual(binary["exif"], original_exif)
                        self.assertEqual(base64.b64decode(history["original_metadata"]["exif"]["data"]), original_exif)
                    path = Path(directory) / "edit.png"
                    pnginfo = PngInfo()
                    for key, value in fields.items():
                        pnginfo.add_text(key, value)
                    output = Image.new("RGB", source.size, (100, 80, 60))
                    output.save(path, pnginfo=pnginfo)
                    preserve_binary_metadata(path, binary)
                    with Image.open(path) as saved:
                        self.assertEqual(saved.tobytes(), output.tobytes())
                        self.assertEqual(saved.info["Author"], "camera owner")
                        self.assertEqual(saved.info["icc_profile"], b"test-profile")
                        self.assertAlmostEqual(saved.info["dpi"][0], 300, delta=.02)
                        self.assertAlmostEqual(saved.info["dpi"][1], expected_dpi[1], delta=.02)
                        if original_exif:
                            self.assertEqual(saved.info["exif"], original_exif)
                        appended, _ = build_metadata(saved, recipe, "second edit")
                        self.assertEqual(len(json.loads(appended[HISTORY_KEY])["edits"]), 2)
                    fresh, fresh_binary = build_metadata(source, recipe, "fresh edit", False)
                    self.assertEqual(fresh_binary, {})
                    self.assertEqual(json.loads(fresh[HISTORY_KEY])["original_metadata"], {})

    def test_invalid_optional_resolution_does_not_break_saving(self):
        for dpi in ((IFDRational(0, 0), 72), (float("inf"), 72), (-1, 72), (1e300, 72),
                    (True, 72), ("300", "72"), (object(), 72), (72,), None):
            with self.subTest(dpi=dpi), tempfile.TemporaryDirectory() as directory:
                source = Image.new("RGB", (8, 8))
                source.info.update(dpi=dpi, Author="kept")
                fields, binary = build_metadata(source, {"model_family": "Qwen Image 2.1"}, "edit")
                self.assertNotIn("dpi", binary)
                self.assertNotIn("dpi", json.loads(fields[HISTORY_KEY])["original_metadata"])
                self.assertEqual(fields["Author"], "kept")
                path = Path(directory) / "saved.png"
                source.save(path)
                before = path.read_bytes()
                preserve_binary_metadata(path, {"dpi": dpi})
                self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
