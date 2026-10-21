import json
import unittest

from PIL import Image

from forge_qwen_edit.reference_adjustments import adjust_reference, reference_adjustment_records, UPLOAD_DIGEST, CURVES_RECORD
from test_adjustments import payload


class ReferenceAdjustmentTests(unittest.TestCase):
    def setUp(self):
        self.original = Image.new('RGBA', (24, 16), (80, 100, 130, 123))
        self.original.info[UPLOAD_DIGEST] = 'a' * 64
        self.original.info['Author'] = 'source'

    def test_repeated_adjustment_starts_from_original_and_keeps_alpha(self):
        data = json.dumps(payload())
        first = adjust_reference(self.original, data)
        second = adjust_reference(self.original, data)
        self.assertEqual(first.getpixel((3, 3)), (115, 135, 165, 123))
        self.assertEqual(first.tobytes(), second.tobytes())
        self.assertEqual(self.original.getpixel((3, 3)), (80, 100, 130, 123))
        self.assertNotIn(CURVES_RECORD, self.original.info)
        self.assertEqual(first.info['Author'], 'source')

    def test_reset_and_unfilled_slots_use_original(self):
        self.assertIs(adjust_reference(self.original, ''), self.original)
        self.assertIsNone(adjust_reference(None, ''))
        self.assertEqual(reference_adjustment_records((self.original, None)), [])

    def test_stale_or_removed_reference_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'changed'):
            adjust_reference(self.original, json.dumps(payload('b' * 64)))
        with self.assertRaisesRegex(ValueError, 'removed'):
            adjust_reference(None, json.dumps(payload()))

    def test_record_preserves_slot_and_does_not_alias_settings(self):
        adjusted = adjust_reference(self.original, json.dumps(payload()))
        records = reference_adjustment_records((None, adjusted))
        self.assertEqual(records[0]['slot'], 3)
        self.assertEqual(records[0]['base_sha256'], 'a' * 64)
        records[0]['settings']['rgb']['points'][0][0] = 10
        self.assertEqual(adjusted.info[CURVES_RECORD]['settings']['rgb']['points'][0][0], 0)

    def test_invalid_luts_never_modify_source(self):
        data = payload(); data['luts'][0][0] = 300
        with self.assertRaises(ValueError):
            adjust_reference(self.original, json.dumps(data))
        self.assertEqual(self.original.getpixel((0, 0)), (80, 100, 130, 123))
