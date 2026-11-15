"""Byte-inventory checks using local files and signed controller fixtures; no provider."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / 'tools/check_engagement_export.py'

class ExportCheck(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.payload = b'{}\n'
        (self.root / 'result.json').write_bytes(self.payload)
        self.manifest = {'kind': 'engagement-result-bundle-v2', 'engagement_id': 'example',
                         'revision': 1, 'files': {'result.json': 'sha256:' + hashlib.sha256(self.payload).hexdigest()}}

    def run_check(self):
        (self.root / 'manifest.json').write_text(json.dumps(self.manifest))
        result = subprocess.run([sys.executable, str(SCRIPT), str(self.root)], capture_output=True, text=True)
        return result.returncode, json.loads(result.stdout)

    def test_unchanged_export_has_integrity_only(self):
        code, report = self.run_check()
        self.assertEqual(code, 0)
        self.assertEqual(report['integrity'], 'verified')
        self.assertEqual(report['acceptance'], 'not_assessed')
        self.assertEqual(report['authenticity'], 'not_assessed')

    def test_missing_file_is_reported(self):
        (self.root / 'result.json').unlink()
        code, report = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn('missing_file:result.json', report['errors'])

    def test_unlisted_file_fails(self):
        (self.root / 'unlisted.txt').write_text('extra')
        code, report = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn('unlisted_file:unlisted.txt', report['errors'])

    def test_unsafe_reference_is_rejected(self):
        self.manifest['files']['../outside'] = 'sha256:' + 'a' * 64
        code, report = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn('unsafe_path:../outside', report['errors'])

    def test_symlink_rejected_even_when_bytes_match(self):
        (self.root / 'target').write_bytes(self.payload)
        (self.root / 'result.json').unlink()
        (self.root / 'result.json').symlink_to('target')
        self.manifest['files']['target'] = self.manifest['files']['result.json']
        code, report = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn('symlink:result.json', report['errors'])

    def test_wrong_manifest_kind_fails(self):
        self.manifest['kind'] = 'promotion-bundle'
        code, report = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn('invalid_manifest', report['errors'])

    def test_duplicate_key_fails(self):
        raw = json.dumps(self.manifest)
        (self.root / 'manifest.json').write_text(raw[:-1] + ', "revision": 2}')
        result = subprocess.run([sys.executable, str(SCRIPT), str(self.root)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('invalid_manifest', json.loads(result.stdout)['errors'])

    def test_changed_file_fails(self):
        (self.root / 'result.json').write_text('changed')
        code, report = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn('digest_mismatch:result.json', report['errors'])

    def test_malformed_fields_fail(self):
        for key, value in [('revision', True), ('files', []), ('kind', None), ('engagement_id', '')]:
            with self.subTest(key=key):
                original = self.manifest[key]
                self.manifest[key] = value
                code, report = self.run_check()
                self.assertEqual(code, 1)
                self.assertIn('invalid_manifest', report['errors'])
                self.manifest[key] = original

    def test_bad_digest_fails(self):
        self.manifest['files']['result.json'] = 'SHA256:bad'
        code, report = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn('invalid_manifest', report['errors'])

    def test_nested_export_files_pass(self):
        (self.root / 'objects').mkdir()
        (self.root / 'objects' / 'receipt').write_bytes(self.payload)
        self.manifest['files']['objects/receipt'] = self.manifest['files']['result.json']
        self.assertEqual(self.run_check()[0], 0)

    def test_noncanonical_paths_fail(self):
        for name in ['/tmp/outside', './result.json', 'objects//file', 'objects/../result.json', 'manifest.json', '']:
            with self.subTest(name=name):
                self.manifest['files'][name] = 'sha256:' + 'a' * 64
                code, report = self.run_check()
                self.assertEqual(code, 1)
                self.assertIn('unsafe_path:' + name, report['errors'])
                del self.manifest['files'][name]

    def test_manifest_symlink_fails(self):
        (self.root / 'raw.json').write_text(json.dumps(self.manifest))
        (self.root / 'manifest.json').symlink_to('raw.json')
        result = subprocess.run([sys.executable, str(SCRIPT), str(self.root)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('symlink:manifest.json', json.loads(result.stdout)['errors'])

    def test_symlink_parent_fails(self):
        (self.root / 'objects').symlink_to(self.root, target_is_directory=True)
        self.manifest['files']['objects/result.json'] = self.manifest['files']['result.json']
        code, report = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn('symlink:objects/result.json', report['errors'])

    def test_special_file_is_rejected_without_opening_it(self):
        os.mkfifo(self.root / 'pipe')
        code, report = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn('special_file:pipe', report['errors'])

    def test_manifest_fifo_is_rejected_without_blocking(self):
        os.mkfifo(self.root / 'manifest.json')
        result = subprocess.run([sys.executable, str(SCRIPT), str(self.root)], capture_output=True, text=True, timeout=2)
        self.assertEqual(result.returncode, 1)
        self.assertIn('invalid_manifest', json.loads(result.stdout)['errors'])

    def test_invalid_json_is_reported(self):
        (self.root / 'manifest.json').write_bytes(b'not json')
        result = subprocess.run([sys.executable, str(SCRIPT), str(self.root)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('invalid_manifest', json.loads(result.stdout)['errors'])

    def test_null_path_is_rejected(self):
        self.manifest['files']['bad' + chr(0)] = 'sha256:' + 'a' * 64
        code, report = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn('unsafe_path:bad' + chr(0), report['errors'])

class ActualExportCheck(unittest.TestCase):
    def test_real_export_and_file_mutations(self):
        sys.path[:0] = [str(ROOT / 'tools'), str(Path(__file__).parent)]
        from check_engagement_evidence_e2e import Case

        with tempfile.TemporaryDirectory(prefix='oslit-export-check-') as directory:
            root = Path(directory).resolve()
            case = Case(root / 'case')
            bundle = root / 'export'
            self.assertEqual(case.c.export(bundle)['status'], 'exported')
            manifest = json.loads((bundle / 'manifest.json').read_text())
            self.assertTrue(any(name.startswith('events/') for name in manifest['files']))
            self.assertTrue(any(name.startswith('contract/') for name in manifest['files']))

            def check(code, error=None):
                run = subprocess.run([sys.executable, str(SCRIPT), str(bundle)],
                                     capture_output=True, text=True, timeout=10)
                report = json.loads(run.stdout)
                self.assertEqual(run.returncode, code, report)
                self.assertEqual(report['authenticity'], 'not_assessed')
                self.assertEqual(report['acceptance'], 'not_assessed')
                if error:
                    self.assertIn(error, report['errors'])

            check(0)
            result = bundle / 'result.json'
            original = result.read_bytes()
            result.write_bytes(original + b' ')
            check(1, 'digest_mismatch:result.json')
            result.unlink()
            check(1, 'missing_file:result.json')
            result.write_bytes(original)
            (bundle / 'unexpected.txt').write_text('unlisted')
            check(1, 'unlisted_file:unexpected.txt')


if __name__ == '__main__':
    unittest.main()
