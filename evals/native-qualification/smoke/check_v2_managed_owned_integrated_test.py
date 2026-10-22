#!/usr/bin/env python3
"""Offline gates for the integrated same-image controller.

Failures to reject before Docker: a changed historical controller; a wrong or
dirty integration HEAD; an old runner or stale current source manifest; a
manifest that omits or mispins this entrypoint or check; and a supplied source
commit different from the validated HEAD. The historical module must stay
byte-identical, and its admission, run, and cleanup functions must be reused.
"""

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


HERE = Path(__file__).resolve().parent
ENTRY = HERE / 'check_v2_managed_owned_integrated.py'
FROZEN = HERE / 'check_v2_managed_owned_amd64_php8427.py'


def load_entry():
    spec = importlib.util.spec_from_file_location('integrated_entry', ENTRY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class IntegratedControllerOfflineTest(unittest.TestCase):
    def test_only_data_pins_change_in_private_historical_module(self):
        entry = load_entry()
        old_bytes = FROZEN.read_bytes()
        controller = entry.load_controller()
        self.assertEqual(hashlib.sha256(FROZEN.read_bytes()).hexdigest(),
                         hashlib.sha256(old_bytes).hexdigest())
        self.assertEqual(controller.INTEGRATION_HEAD, entry.INTEGRATION_HEAD)
        self.assertEqual(controller.MANAGED_RUNNER_SHA256, entry.MANAGED_RUNNER_SHA256)
        self.assertEqual(controller.IMAGE_TAG, entry.IMAGE_TAG)
        self.assertEqual(Path(controller.main.__code__.co_filename), FROZEN)
        self.assertEqual(Path(controller.run_attempt.__code__.co_filename), FROZEN)
        self.assertEqual(Path(controller.validate_sources.__code__.co_filename), FROZEN)

    def test_changed_historical_controller_is_rejected(self):
        entry = load_entry()
        with tempfile.TemporaryDirectory() as temporary:
            changed = Path(temporary) / FROZEN.name
            changed.write_bytes(FROZEN.read_bytes() + b'\n')
            with mock.patch.object(entry, 'FROZEN', changed):
                with self.assertRaisesRegex(RuntimeError, 'historical_controller_pin_mismatch'):
                    entry.load_controller()

    def test_own_manifest_entries_are_required_and_exact(self):
        entry = load_entry()
        entries = [{'path': str(path.relative_to(entry.ROOT)),
                    'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                   for path in (ENTRY, Path(__file__))]
        source = {'private': {'manifest_entries': entries}}

        class Controller:
            def validate_sources(self):
                return source

        entry.admit_sources(Controller())
        for bad_entries in (entries[:1],
                            [{**entries[0], 'sha256': '0' * 64}, entries[1]]):
            source['private']['manifest_entries'] = bad_entries
            with self.assertRaisesRegex(RuntimeError, 'integrated_source_manifest_mismatch'):
                entry.admit_sources(Controller())

    def test_wrong_source_commit_stops_before_commands(self):
        entry = load_entry()
        controller = entry.load_controller()

        class NoCommands:
            def run(self, *_args, **_kwargs):
                raise AssertionError('command executed before exact source admission')

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'attempt'
            result = controller.run_attempt(
                output, Path(temporary) / 'absent-ca', NoCommands(), {},
                parity_source_root=Path(temporary),
                source_validator=lambda: {'source_commit': '0' * 40},
                expected_source_commit='1' * 40,
                recorded_at=lambda: '2026-10-22T00:00:00Z')
            self.assertEqual(result, 1)
            receipt = json.loads((output / 'result.json').read_text())
            self.assertEqual(receipt['status'], 'blocked')
            self.assertEqual(receipt['failure'], 'exact_source_commit_mismatch')


if __name__ == '__main__':
    unittest.main()
