"""Check summary consistency against real exports with simulated evidence."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from check_engagement_export_references_e2e import fixture, snapshot

ROOT = Path(__file__).resolve().parents[3]


class ResultConsistency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name).resolve()
        case = fixture.Case(cls.root)
        case.publication('contrary')
        case.instrument()
        case.experiment('effect')
        case.experiment('control', purpose='control',
                        explains={'experiment_id': 'effect', 'variable': 'fixture_switch'})
        case.claim()
        cls.original = cls.root / 'export'
        case.c.export(cls.original)

    def setUp(self):
        self.bundle = self.root / self._testMethodName
        shutil.copytree(self.original, self.bundle)

    def change(self, mutate):
        path = self.bundle / 'result.json'
        result = json.loads(path.read_text())
        mutate(result)
        path.write_bytes(fixture.canonical(result))
        manifest = self.bundle / 'manifest.json'
        inventory = json.loads(manifest.read_text())
        inventory['files']['result.json'] = fixture.digest(path.read_bytes())
        manifest.write_bytes(fixture.canonical(inventory))

    def check(self, valid=False):
        before = snapshot(self.bundle)
        command = [sys.executable, str(ROOT / 'tools/verify_engagement_export_references.py'),
                   str(self.bundle)]
        reference = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertEqual(reference.returncode, 0, reference.stdout)
        result = subprocess.run(command + ['--check-result'], capture_output=True,
                                text=True, timeout=30)
        self.assertEqual(result.returncode, 0 if valid else 1, result.stdout)
        self.assertEqual(result.stderr, '')
        self.assertEqual(snapshot(self.bundle), before)
        if valid:
            report = json.loads(result.stdout)
            self.assertIs(report['result_consistency_verified'], True)
            self.assertIs(report['authenticity_verified'], False)
            self.assertIs(report['research_acceptance_verified'], False)

    def test_original(self):
        self.check(valid=True)

    def test_false_cleanup(self):
        self.change(lambda data: data.update(cleanup='verified'))
        self.check()

    def test_false_completion(self):
        self.change(lambda data: data.update(status='completed'))
        self.check()

    def test_forged_external_authority(self):
        self.change(lambda data: data.update(external_action_authorized=True))
        self.check()

    def test_boolean_is_not_integer(self):
        self.change(lambda data: data.update(external_action_authorized=0))
        self.check()

    def test_omitted_claim(self):
        self.change(lambda data: data.update(claims={}))
        self.check()

    def test_changed_claim(self):
        self.change(lambda data: data['claims']['claim-1'].update(state='independently_confirmed'))
        self.check()

    def test_omitted_field(self):
        self.change(lambda data: data.pop('usage'))
        self.check()

    def test_unrecognized_field(self):
        self.change(lambda data: data.update(accepted=True))
        self.check()

    def test_changed_usage(self):
        self.change(lambda data: data['usage'].update(invocations=999))
        self.check()

    def test_changed_guidance(self):
        self.change(lambda data: data.update(research_guidance={}))
        self.check()

    def test_large_json_whitespace(self):
        path = self.bundle / 'result.json'
        path.write_bytes(path.read_bytes() + b' ' * (1024 * 1024))
        self.check(valid=True)

    def test_result_exceeds_publication_limit(self):
        path = self.bundle / 'result.json'
        path.write_bytes(path.read_bytes() + b' ' * (16 * 1024 * 1024))
        self.check()

    def test_json_whitespace(self):
        path = self.bundle / 'result.json'
        path.write_text(json.dumps(json.loads(path.read_text()), indent=2))
        self.check(valid=True)


if __name__ == '__main__':
    unittest.main()
