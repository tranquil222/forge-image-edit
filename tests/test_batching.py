import contextlib
import io
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from forge_qwen_edit.batching import run_batch, validate_count


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.state = SimpleNamespace(interrupted=False, skipped=False)
        self.source, self.mask = object(), object()
        self.args = [self.source, None, None, 'edit the object', '', 768, 4,
                     '6255021648265544245', 'Euler', 'Simple', self.mask]
        self.calls = []

    def generate(self, *args):
        self.calls.append(args)
        self.assertEqual(self.state.job_no, len(self.calls) - 1)
        self.assertEqual(self.state.textinfo, f'Image Edit {len(self.calls)} / {self.state.job_count}')
        seed = args[7] if args[7] != '-1' else str(900 + len(self.calls))
        return object(), f'result-{seed}.png', seed, f'Saved seed {seed}'

    def test_fixed_seeds_are_exact_sequential_and_source_is_not_chained(self):
        output, items, message = run_batch(self.generate, self.args, 3, self.state)
        self.assertIsNotNone(output)
        self.assertEqual([item['seed'] for item in items],
                         ['6255021648265544245', '6255021648265544246', '6255021648265544247'])
        for call in self.calls:
            self.assertIs(call[0], self.source)
            self.assertIs(call[-1], self.mask)
            self.assertEqual(call[1:7], tuple(self.args[1:7]))
        self.assertEqual(self.args[7], '6255021648265544245')
        self.assertEqual(self.state.job_no, 3)
        self.assertIn('3 / 3', message)

    def test_random_seed_stays_random_for_each_item(self):
        self.args[7] = '-1'
        _, items, _ = run_batch(self.generate, self.args, 3, self.state)
        self.assertEqual([call[7] for call in self.calls], ['-1'] * 3)
        self.assertEqual([item['seed'] for item in items], ['901', '902', '903'])

    def test_unsigned_seed_boundary_wraps_without_float_rounding(self):
        self.args[7] = str(2**64 - 1)
        _, items, _ = run_batch(self.generate, self.args, 2, self.state)
        self.assertEqual([item['seed'] for item in items], [str(2**64 - 1), '0'])

    def test_cancel_between_items_keeps_completed_and_starts_no_next_item(self):
        def generate(*args):
            result = self.generate(*args)
            self.state.interrupted = True
            return result
        _, items, message = run_batch(generate, self.args, 4, self.state)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(items), 1)
        self.assertIn('Cancelled.', message)
        self.assertIn('1 / 4', message)

    def test_cancel_during_item_never_replaces_last_completed_output(self):
        saved = object()
        def generate(*args):
            if self.calls:
                self.state.interrupted = True
                return None, None, '', 'Edit cancelled.'
            _, path, seed, message = self.generate(*args)
            return saved, path, seed, message
        output, items, _ = run_batch(generate, self.args, 3, self.state)
        self.assertIs(output, saved)
        self.assertEqual(len(items), 1)

    def test_later_failure_keeps_completed_and_stops(self):
        def generate(*args):
            if self.calls:
                raise RuntimeError('test failure')
            return self.generate(*args)
        with contextlib.redirect_stderr(io.StringIO()):
            output, items, message = run_batch(generate, self.args, 4, self.state)
        self.assertIsNotNone(output)
        self.assertEqual(len(items), 1)
        self.assertIn('Stopped at edit 2', message)
        self.assertIn('test failure', message)

    def test_one_item_retains_native_message(self):
        _, items, message = run_batch(self.generate, self.args, 1, self.state)
        self.assertEqual(message, items[0]['message'])

    def test_invalid_seed_or_count_never_starts_inference(self):
        for count in (0, -1, 65, 2.5, True, None, 'abc', float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                run_batch(self.generate, self.args, count, self.state)
        for count in (1, 64, 2.0, '3'):
            self.assertEqual(validate_count(count), int(count))
        self.args[7] = 'broken'
        with self.assertRaises(ValueError):
            run_batch(self.generate, self.args, 1, self.state)
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
