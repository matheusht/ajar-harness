#!/usr/bin/env python3
"""Offline export reference checks using simulated evidence and the real exporter.

Requires Python 3 and ssh-keygen. No provider, target, or container is used.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    'evidence_export_fixture', Path(__file__).with_name('check_engagement_evidence_e2e.py'))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def snapshot(root):
    return {
        str(path.relative_to(root)): (
            ('symlink', str(path.readlink())) if path.is_symlink()
            else ('file', hashlib.sha256(path.read_bytes()).hexdigest()) if path.is_file()
            else ('directory', path.stat().st_mode)
        )
        for path in root.rglob('*')
    }


class ExportReferences(unittest.TestCase):
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
        actor, packet = case.packet('claim', 'claim-1')
        case.experiment('replay', actor, purpose='replay',
                        explains={'experiment_id': 'effect', 'variable': None}, nonce='2' * 32)
        case.review('claim-1', actor, packet, evidence=['replay'], contrary=['contrary'])
        cls.original = cls.root / 'export'
        case.c.export(cls.original)

    def setUp(self):
        self.bundle = self.root / self._testMethodName
        shutil.copytree(self.original, self.bundle)

    def manifest(self, update):
        path = self.bundle / 'manifest.json'
        data = json.loads(path.read_text())
        update(data)
        path.write_text(json.dumps(data))

    def contract_files(self, value):
        previous = None
        for index, path in enumerate(sorted((self.bundle / 'events').iterdir())):
            event = json.loads(path.read_text())
            if index == 0:
                event['payload']['contract_files'] = value
            event['previous_sha256'] = previous
            event['sha256'] = fixture.digest(fixture.canonical(
                {key: item for key, item in event.items() if key != 'sha256'}))
            path.write_bytes(fixture.canonical(event))
            previous = event['sha256']

    def check(self, valid=False):
        before = snapshot(self.bundle)
        result = subprocess.run(
            [sys.executable, str(ROOT / 'tools/verify_engagement_export_references.py'), str(self.bundle)],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(snapshot(self.bundle), before)
        self.assertEqual(result.stderr, '')
        self.assertEqual(result.returncode, 0 if valid else 1, result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report['check'], 'journal_reference_closure')
        self.assertEqual(report['status'], 'verified' if valid else 'failed')
        if valid:
            self.assertIs(report['authenticity_verified'], False)
            self.assertIs(report['research_acceptance_verified'], False)

    def test_valid_export(self):
        self.check(valid=True)

    def test_omitted_object_and_manifest_entry(self):
        path = next((self.bundle / 'objects').iterdir())
        self.manifest(lambda data: data['files'].pop(str(path.relative_to(self.bundle))))
        path.unlink()
        self.check()

    def test_corrupt_object(self):
        next((self.bundle / 'objects').iterdir()).write_text('{}')
        self.check()

    def test_omitted_last_event(self):
        sorted((self.bundle / 'events').iterdir())[-1].unlink()
        self.check()

    def test_corrupt_event(self):
        sorted((self.bundle / 'events').iterdir())[-1].write_text('{}')
        self.check()

    def test_changed_contract(self):
        next(path for path in (self.bundle / 'contract').rglob('*') if path.is_file()).write_text('{}')
        self.check()

    def test_wrong_revision(self):
        self.manifest(lambda data: data.update(revision=data['revision'] + 1))
        self.check()

    def test_wrong_identity(self):
        self.manifest(lambda data: data.update(engagement_id='wrong'))
        self.check()

    def test_boolean_revision(self):
        self.manifest(lambda data: data.update(revision=True))
        self.check()

    def test_manifest_list(self):
        (self.bundle / 'manifest.json').write_text('[]')
        self.check()

    def test_manifest_null(self):
        (self.bundle / 'manifest.json').write_text('null')
        self.check()

    def test_contract_list(self):
        self.contract_files([])
        self.check()

    def test_contract_null(self):
        self.contract_files(None)
        self.check()

    def test_objects_directory_symlink(self):
        outside = self.root / 'outside-objects'
        shutil.move(self.bundle / 'objects', outside)
        (self.bundle / 'objects').symlink_to(outside, target_is_directory=True)
        before = snapshot(outside)
        self.check()
        self.assertEqual(snapshot(outside), before)

    def test_absolute_contract_path(self):
        path = self.original / 'contract' / 'methodology.md'
        self.contract_files({str(path): fixture.digest(path.read_bytes())})
        self.check()

    def test_parent_contract_path(self):
        path = self.original / 'contract' / 'methodology.md'
        self.contract_files({'../../export/contract/methodology.md': fixture.digest(path.read_bytes())})
        self.check()

    def test_contract_symlink(self):
        path = self.bundle / 'contract' / 'methodology.md'
        path.unlink()
        path.symlink_to(self.original / 'contract' / 'methodology.md')
        self.check()


if __name__ == '__main__':
    unittest.main()
