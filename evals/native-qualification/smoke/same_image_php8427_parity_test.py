#!/usr/bin/env python3
"""Offline tests for the fresh-image Kanboard parity wrapper."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).with_name('same_image_php8427_parity.py')
SPEC = importlib.util.spec_from_file_location('same_image_php8427_parity', MODULE_PATH)
parity = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(parity)


IMAGE_ID = 'sha256:' + '1' * 64
IMAGE_TAG = 'owned:test'
QUALIFICATION_BASE = '2' * 40
ARCHIVES = {'vulnerable': b'vulnerable archive', 'fixed': b'fixed archive'}
TEST_PINS = {
    'vulnerable': ('3' * 40, hashlib.sha256(ARCHIVES['vulnerable']).hexdigest()),
    'fixed': ('4' * 40, hashlib.sha256(ARCHIVES['fixed']).hexdigest()),
}


class FakeRunner:
    def __init__(self, events, *, wrong_runtime=False, exit_code=0):
        self.events = events
        self.wrong_runtime = wrong_runtime
        self.exit_code = exit_code
        self.observer_case = SimpleNamespace(
            PINS=TEST_PINS, urlopen=object(), subprocess=object(),
            PHP_IMAGE='old-image', PHP_IMAGE_DIGEST='old-digest')
        self.subprocess = object()
        self.QUALIFICATION_BASE = 'old-base'
        self.IMAGE = 'old-tag'
        self.IMAGE_ID = 'sha256:' + '0' * 64
        self.IMAGE_RUNTIME_LABEL = 'old-runtime'
        self.DOCKERFILE = Path('/old/Dockerfile')
        self.DOCKERFILE_SHA256 = '0' * 64
        self.CHECKS = Path('/old/CHECKS')
        self.RUNTIME_BUILD = Path('/old/receipt.json')
        self.RUNTIME_BUILD_SHA256 = '0' * 64
        self.admit_and_probe_image = lambda *_args: None
        self.observer_check_results = lambda *_args: {}
        self.artifact_check_results = lambda *_args: {}
        self.public_observer_result = lambda value: value

    def main(self):
        self.events.append('first-arm')
        if self.events[:3] != ['fetch-vulnerable', 'fetch-fixed', 'first-arm']:
            raise AssertionError('an arm started before both archives were verified')
        receipt = self.RUNTIME_BUILD.read_bytes()
        if hashlib.sha256(receipt).hexdigest() != self.RUNTIME_BUILD_SHA256:
            raise AssertionError('compatibility receipt was not hash-bound')
        value = json.loads(receipt)
        if (value['image_id'] != IMAGE_ID or value['tag'] != IMAGE_TAG
                or value['scope'] != 'immutable-image registration gate only'):
            raise AssertionError('fresh candidate was not explicitly bound')
        archive_receipt = self.RUNTIME_BUILD.with_name('archives.json')
        archive_value = json.loads(archive_receipt.read_text())
        if (archive_value['status'] != 'pass'
                or archive_value['image_id'] != IMAGE_ID
                or not all(item['verified_before_first_arm'] is True
                           for item in archive_value['archives'].values())):
            raise AssertionError('both archives were not admitted before the first arm')
        output = Path(parity.sys.argv[parity.sys.argv.index('--output') + 1])
        output.mkdir(mode=0o700)
        evidence = output / 'evidence'
        evidence.mkdir(mode=0o700)
        runtime = 'sha256:' + '9' * 64 if self.wrong_runtime else IMAGE_ID
        arms = [
            {
                'release': label,
                'runtime': runtime,
                'php': 'PHP 8.4.27 (cli)',
                'commit': commit,
                'archive_sha256': digest,
            }
            for label, (commit, digest) in TEST_PINS.items()
        ]
        public = {'case': 'owned', 'status': 'pass', 'arms': arms}
        (evidence / 'observer-results.public.json').write_text(
            json.dumps(public) + '\n')
        archive_inputs = {
            label: {
                'url': f'https://codeload.github.com/kanboard/kanboard/tar.gz/{commit}',
                'commit': commit,
                'sha256': digest,
            }
            for label, (commit, digest) in TEST_PINS.items()
        }
        docker = {'containers': [], 'images': [IMAGE_ID],
                  'volumes': [], 'networks': ['bridge']}
        result = {
            'status': 'pass',
            'classification': 'owned offline observer parity; zero provider/model calls',
            'qualification_base': QUALIFICATION_BASE,
            'checks': [
                {'name': name, 'pass': True}
                for name in sorted(parity.EXPECTED_CHECKS)
            ],
            'provider_calls': 0,
            'model_calls': 0,
            'researcher_bundle_created': False,
            'docker_before': docker,
            'docker_after': docker,
            'source_sha256': {
                'smoke/check_v2_php_parity_amd64.py': parity.RUNNER_SHA256,
                '.same-image-parity-private/registration.json':
                self.RUNTIME_BUILD_SHA256,
            },
            'image': {
                'tag': IMAGE_TAG,
                'expected_id': IMAGE_ID,
                'actual_id': IMAGE_ID,
                'expected_platform': parity.PLATFORM,
                'actual_platform': parity.PLATFORM,
                'php_version': 'PHP 8.4.27 (cli)',
            },
            'archive_inputs': archive_inputs,
        }
        (output / 'parity-result.json').write_text(json.dumps(result) + '\n')
        return self.exit_code


class FakeAdapter:
    RUNNER_SHA256 = parity.RUNNER_SHA256
    RUNNER = Path('/fixed/preserved-runner.py')

    def __init__(self, runner, events):
        self.runner = runner
        self.events = events
        self.EXPECTED_PINS = TEST_PINS
        self.Candidate = lambda tag, image_id, digest: SimpleNamespace(
            tag=tag, image_id=image_id, dockerfile_sha256=digest)

    def main(self):
        raise AssertionError('sealed adapter main must not be called')

    def load_fixed_policy(self):
        raise AssertionError('sealed fixed policy must not be called')

    def fetch_verified_archives(self, pins, _opener, byte_limit):
        if pins != TEST_PINS or byte_limit != parity.ARCHIVE_BYTE_LIMIT:
            raise AssertionError('archive fetch policy changed')
        self.events.extend(['fetch-vulnerable', 'fetch-fixed'])
        return dict(ARCHIVES)

    def load_preserved_runner(self):
        return self.runner

    @staticmethod
    def admit_and_probe_image(*_args):
        return 'PHP 8.4.27 (cli)', ['gd', 'pdo_sqlite']

    @staticmethod
    def php8427_observer_check_results(_current, _original, preserved, _image):
        return preserved(_current, _original)

    @staticmethod
    def _strict_artifact_checker(preserved):
        return preserved

    @staticmethod
    def _public_result_sanitizer(preserved):
        return preserved

    class GuardedUrlopen:
        def __init__(self, archives, delegate):
            self.archives = archives
            self.delegate = delegate

    class ObserverSubprocess:
        def __init__(self, delegate, image_id):
            self.delegate = delegate
            self.image_id = image_id


class SameImageParityTests(unittest.TestCase):
    def fixture(self, root: Path):
        source = root / 'source/evals/native-qualification'
        source.mkdir(parents=True)
        dockerfile = source / 'Dockerfile.opencode-kanboard-runtime-php8427'
        checks = source / 'CHECKS.md'
        dockerfile.write_text('FROM pinned@example\nRUN true\n')
        checks.write_text('failure predicates\n')
        digest = hashlib.sha256(dockerfile.read_bytes()).hexdigest()
        candidate = root / 'candidate.json'
        candidate.write_text(json.dumps({
            'schema_version': 1,
            'kind': 't02-managed-owned-amd64-php8427-candidate',
            'status': 'registered_before_execution',
            'platform': parity.PLATFORM,
            'tag': IMAGE_TAG,
            'image_id': IMAGE_ID,
            'dockerfile_sha256': digest,
            'image_execution_attempted': False,
        }) + '\n')
        return source, dockerfile, checks, candidate

    def run_fixture(self, root: Path, *, wrong_runtime=False):
        source, dockerfile, checks, candidate = self.fixture(root)
        events = []
        runner = FakeRunner(events, wrong_runtime=wrong_runtime)
        adapter = FakeAdapter(runner, events)
        output = root / 'parity.private'
        with mock.patch.object(parity, 'EXPECTED_PINS', TEST_PINS):
            summary = parity.run_same_image_parity(
                source, output, IMAGE_TAG, IMAGE_ID, dockerfile, checks,
                QUALIFICATION_BASE, candidate,
                opener=lambda *_args, **_kwargs: None,
                adapter_loader=lambda _root: adapter)
        return summary, output, source, candidate, runner, events

    def test_same_fresh_image_passes_both_arms_before_summary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            summary, output, source, candidate, runner, events = self.run_fixture(root)
            self.assertEqual(events, ['fetch-vulnerable', 'fetch-fixed', 'first-arm'])
            self.assertEqual(summary['status'], 'pass')
            self.assertEqual(summary['image_id'], IMAGE_ID)
            self.assertEqual(summary['checks_passed'], 32)
            self.assertTrue(summary['both_arms_same_image'])
            self.assertEqual(
                summary['receipt_sha256']['outer_candidate'],
                hashlib.sha256(candidate.read_bytes()).hexdigest())
            compatibility = output / 'registration-compatibility.json'
            self.assertEqual(
                hashlib.sha256(compatibility.read_bytes()).hexdigest(),
                summary['receipt_sha256']['registration_compatibility'])
            archive_receipt = output / 'archive-admission.json'
            self.assertEqual(
                hashlib.sha256(archive_receipt.read_bytes()).hexdigest(),
                summary['receipt_sha256']['archive_admission'])
            self.assertTrue((output / 'same-image-summary.json').is_file())
            self.assertFalse((source / '.same-image-parity-private').exists())
            self.assertEqual(runner.IMAGE, 'old-tag')
            self.assertEqual(runner.RUNTIME_BUILD, Path('/old/receipt.json'))

    def test_wrong_arm_runtime_fails_after_runner_and_cleans_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, dockerfile, checks, candidate = self.fixture(root)
            events = []
            adapter = FakeAdapter(FakeRunner(events, wrong_runtime=True), events)
            with mock.patch.object(parity, 'EXPECTED_PINS', TEST_PINS):
                with self.assertRaisesRegex(
                        parity.SameImageParityError,
                        'public_observer_runtime_mismatch'):
                    parity.run_same_image_parity(
                        source, root / 'parity.private', IMAGE_TAG, IMAGE_ID,
                        dockerfile, checks, QUALIFICATION_BASE, candidate,
                        adapter_loader=lambda _root: adapter)
            self.assertEqual(events, ['fetch-vulnerable', 'fetch-fixed', 'first-arm'])
            self.assertFalse((source / '.same-image-parity-private').exists())

    def test_candidate_mismatch_blocks_before_adapter_or_archives(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, dockerfile, checks, candidate = self.fixture(root)
            value = json.loads(candidate.read_text())
            value['image_id'] = 'sha256:' + '8' * 64
            candidate.write_text(json.dumps(value) + '\n')
            called = []
            with self.assertRaisesRegex(
                    parity.SameImageParityError,
                    'outer_candidate_receipt_mismatch'):
                parity.run_same_image_parity(
                    source, root / 'parity.private', IMAGE_TAG, IMAGE_ID,
                    dockerfile, checks, QUALIFICATION_BASE, candidate,
                    adapter_loader=lambda _root: called.append(True))
            self.assertEqual(called, [])

    def test_changed_adapter_bytes_fail_pin_before_import(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'evals/native-qualification'
            adapter = source / parity.ADAPTER_RELATIVE
            adapter.parent.mkdir(parents=True)
            adapter.write_text('raise RuntimeError("must not import")\n')
            with self.assertRaisesRegex(
                    parity.SameImageParityError, 'adapter_source_pin_mismatch'):
                parity.load_pinned_adapter(source)

    def test_verified_adapter_bytes_execute_even_if_path_is_replaced(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'evals/native-qualification'
            adapter = source / parity.ADAPTER_RELATIVE
            adapter.parent.mkdir(parents=True)
            trusted = (
                f'RUNNER_SHA256 = {parity.RUNNER_SHA256!r}\n'
                f'EXPECTED_PINS = {parity.EXPECTED_PINS!r}\n'
                'MARKER = "verified-bytes"\n'
            ).encode()
            adapter.write_bytes(trusted)
            original_read = parity._read_regular

            def replace_after_read(path, code, **kwargs):
                raw = original_read(path, code, **kwargs)
                if path == adapter.resolve():
                    adapter.write_text('raise RuntimeError("replacement executed")\n')
                return raw

            module_name = '_t02_same_image_php8427_adapter'
            try:
                with (mock.patch.object(
                        parity, 'ADAPTER_SHA256', hashlib.sha256(trusted).hexdigest()),
                      mock.patch.object(
                          parity, '_read_regular', side_effect=replace_after_read)):
                    loaded = parity.load_pinned_adapter(source)
                self.assertEqual(loaded.MARKER, 'verified-bytes')
            finally:
                parity.sys.modules.pop(module_name, None)

    def test_adapter_runtime_failure_is_normalized_and_private_receipt_removed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, dockerfile, checks, candidate = self.fixture(root)
            events = []
            adapter = FakeAdapter(FakeRunner(events), events)
            adapter.load_preserved_runner = lambda: (_ for _ in ()).throw(
                RuntimeError('expected adapter failure'))
            with mock.patch.object(parity, 'EXPECTED_PINS', TEST_PINS):
                with self.assertRaisesRegex(
                        parity.SameImageParityError,
                        'same_image_dependency_failure'):
                    parity.run_same_image_parity(
                        source, root / 'parity.private', IMAGE_TAG, IMAGE_ID,
                        dockerfile, checks, QUALIFICATION_BASE, candidate,
                        adapter_loader=lambda _root: adapter)
            self.assertEqual(events, [])
            self.assertFalse((source / '.same-image-parity-private').exists())


if __name__ == '__main__':
    unittest.main()
