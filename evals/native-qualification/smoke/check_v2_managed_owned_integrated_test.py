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
import subprocess
import sys
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
        self.assertEqual(controller.CHECKS, entry.CHECKS)
        self.assertEqual(controller.CHECKS_SHA256, entry.CHECKS_SHA256)
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
                   for path in (ENTRY, Path(__file__), entry.CHECKS)]
        source = {'private': {'manifest_entries': entries}}

        class Controller:
            def validate_sources(self):
                return source

        entry.admit_sources(Controller())
        for bad_entries in (entries[:1], entries[:2],
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

    def test_frozen_pin_failure_writes_sanitized_blocked_receipt(self):
        entry = load_entry()
        with tempfile.TemporaryDirectory() as temporary:
            changed = Path(temporary) / FROZEN.name
            changed.write_bytes(FROZEN.read_bytes() + b'\n')
            output = Path(temporary) / 'attempt'
            with mock.patch.object(entry, 'FROZEN', changed), mock.patch.object(
                    sys, 'argv', [str(ENTRY), '--output', str(output),
                                  '--source-commit', 'f' * 40]):
                self.assertEqual(entry.main(), 1)
            receipt = json.loads((output / 'result.json').read_text())
            self.assertEqual(receipt['status'], 'blocked')
            self.assertEqual(receipt['failure'], 'historical_controller_pin_mismatch')
            self.assertFalse(receipt['controller_started'])
            self.assertFalse(receipt['docker_build_attempted'])
            self.assertNotIn(str(output), (output / 'result.json').read_text())

    def test_manifest_failure_stops_before_preflight_or_controller(self):
        entry = load_entry()

        class Controller:
            def validate_sources(self):
                return {'private': {'manifest_entries': []}}

            def main(self):
                raise AssertionError('controller started before source admission')

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'attempt'
            with mock.patch.object(entry, 'load_controller', return_value=Controller()), \
                    mock.patch.object(sys, 'argv', [str(ENTRY), '--output', str(output)]), \
                    mock.patch.object(entry.subprocess, 'run') as command:
                self.assertEqual(entry.main(), 1)
            command.assert_not_called()
            receipt = json.loads((output / 'result.json').read_text())
            self.assertEqual(receipt['status'], 'blocked')
            self.assertEqual(receipt['failure'], 'integrated_source_manifest_mismatch')

    def test_current_manifest_preflight_failure_stops_before_controller(self):
        entry = load_entry()

        class Controller:
            def main(self):
                raise AssertionError('controller started after failed preflight')

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'attempt'
            failed = subprocess.CompletedProcess([], 1, '', 'private-canary')
            with mock.patch.object(entry, 'load_controller', return_value=Controller()), \
                    mock.patch.object(entry, 'admit_sources'), \
                    mock.patch.object(sys, 'argv', [str(ENTRY), '--output', str(output)]), \
                    mock.patch.object(entry.subprocess, 'run', return_value=failed) as command:
                self.assertEqual(entry.main(), 1)
            command.assert_called_once()
            receipt_text = (output / 'result.json').read_text()
            self.assertNotIn('private-canary', receipt_text)
            receipt = json.loads(receipt_text)
            self.assertEqual(receipt['status'], 'blocked')
            self.assertEqual(receipt['failure'], 'offline_preflight_failed')

    def test_current_manifest_preflight_precedes_frozen_controller(self):
        entry = load_entry()
        events = []

        class Controller:
            def main(self):
                events.append('controller')
                return 0

        def checked(argv, **_kwargs):
            events.append(argv)
            return subprocess.CompletedProcess(argv, 0, '', '')

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'attempt'
            with mock.patch.object(entry, 'load_controller', return_value=Controller()), \
                    mock.patch.object(entry, 'admit_sources'), \
                    mock.patch.object(sys, 'argv', [str(ENTRY), '--output', str(output)]), \
                    mock.patch.object(entry.subprocess, 'run', side_effect=checked):
                self.assertEqual(entry.main(), 0)
        self.assertEqual(events[-1], 'controller')
        self.assertEqual([Path(argv[1]).name for argv in events[:-1]], [
            'check_v2_cloud_manifest_layout.py',
            'check_v2_cloud_owned_source.py'])
        self.assertEqual(events[1][2:], ['--current-manifest'])


if __name__ == '__main__':
    unittest.main()
