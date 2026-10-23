#!/usr/bin/env python3
"""Behavior tests for the additive PHP 8.4.27 qualification adapter."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock


HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / 'smoke'))
import check_v2_php_parity_amd64_php8427 as subject  # noqa: E402


def encoded(value: dict) -> tuple[bytes, str]:
    raw = (json.dumps(value, sort_keys=True) + '\n').encode()
    return raw, hashlib.sha256(raw).hexdigest()


class CandidateReceiptTests(unittest.TestCase):
    def test_accepts_exact_pre_execution_registration(self):
        raw = subject.CANDIDATE_RECEIPT.read_bytes()

        candidate = subject.parse_candidate_receipt(
            raw, subject.CANDIDATE_RECEIPT_SHA256)

        self.assertEqual(candidate.image_id, subject.IMAGE_ID)
        self.assertEqual(candidate.dockerfile_sha256, subject.DOCKERFILE_SHA256)


class RuntimeAdmissionTests(unittest.TestCase):
    def test_accepts_exact_runtime_admission_receipt(self):
        raw = subject.RUNTIME_RECEIPT.read_bytes()

        runtime = subject.parse_runtime_receipt(
            raw, subject.RUNTIME_RECEIPT_SHA256)

        self.assertEqual(runtime.image_id, subject.IMAGE_ID)
        self.assertTrue(runtime.php_version.startswith('PHP 8.4.27 '))

    def test_accepts_only_php8427_package_revision_and_required_modules(self):
        candidate = subject.Candidate(subject.IMAGE, 'sha256:' + 'a' * 64, 'b' * 64)
        image = {
            'Id': candidate.image_id,
            'Architecture': 'amd64',
            'Os': 'linux',
            'RepoTags': [candidate.tag],
        }
        packages = [f'{name}-8.4.27-r0' for name in subject.REQUIRED_PHP_PACKAGES]
        packages.append('php84-extra-8.4.27-r0')

        checks = subject.runtime_check_results(
            image, 'PHP 8.4.27 (cli)', ['Core', 'gd', 'PDO', 'pdo_sqlite'],
            packages, candidate, 'b' * 64)

        self.assertTrue(all(checks.values()), checks)
        packages[-1] = 'php84-extra-8.4.26-r0'
        self.assertFalse(subject.runtime_check_results(
            image, 'PHP 8.4.27 (cli)', ['gd', 'pdo_sqlite'], packages,
            candidate, 'b' * 64)['all_php84_packages_8_4_27_r0'])

    def test_wrong_image_stops_before_probe_and_exact_image_uses_three_offline_runs(self):
        candidate = subject.Candidate(subject.IMAGE, subject.IMAGE_ID,
                                      subject.DOCKERFILE_SHA256)
        image = {'Id': 'sha256:' + '0' * 64, 'Architecture': 'amd64',
                 'Os': 'linux', 'RepoTags': [subject.IMAGE]}
        process = mock.Mock()

        def check(name, passed):
            if not passed:
                raise AssertionError(name)

        with self.assertRaisesRegex(AssertionError, 'exact image id'):
            subject.admit_and_probe_image(
                image, subject.DOCKERFILE_SHA256, check, candidate, process)
        process.run.assert_not_called()

        image['Id'] = subject.IMAGE_ID
        package_lines = '\n'.join(
            f'{name}-8.4.27-r0' for name in subject.REQUIRED_PHP_PACKAGES)
        process.run.side_effect = [
            SimpleNamespace(returncode=0, stdout=package_lines, stderr=''),
            SimpleNamespace(returncode=0, stdout='PHP 8.4.27 (cli)\n', stderr=''),
            SimpleNamespace(returncode=0, stdout='Core\ngd\npdo_sqlite\n', stderr=''),
        ]

        version, modules = subject.admit_and_probe_image(
            image, subject.DOCKERFILE_SHA256, check, candidate, process)

        self.assertTrue(version.startswith('PHP 8.4.27 '))
        self.assertIn('pdo_sqlite', modules)
        for call in process.run.call_args_list:
            command = call.args[0]
            self.assertIn('--pull=never', command)
            self.assertIn('--network', command)
            self.assertIn(subject.IMAGE_ID, command)

    def test_semantic_comparator_changes_only_current_runtime_rule(self):
        current = {
            'arms': [
                {'release': label, 'runtime': subject.IMAGE_ID,
                 'php': 'PHP 8.4.27 (cli)'}
                for label in ('vulnerable', 'fixed')
            ]
        }

        def preserved(_current, _original):
            return {'semantic_match_t01': True,
                    'current_runtime_both_arms': False,
                    'cleanup_complete': True}

        checks = subject.php8427_observer_check_results(
            current, {'arms': []}, preserved, subject.IMAGE_ID)

        self.assertEqual(checks, {
            'semantic_match_t01': True,
            'current_runtime_both_arms': True,
            'cleanup_complete': True,
        })
        current['arms'][1]['php'] = 'PHP 8.4.26 (cli)'
        self.assertFalse(subject.php8427_observer_check_results(
            current, {}, preserved, subject.IMAGE_ID)['current_runtime_both_arms'])


class ArchiveAdmissionTests(unittest.TestCase):
    def test_both_archive_hashes_are_checked_before_use(self):
        payloads = {'vulnerable': b'vulnerable archive', 'fixed': b'fixed archive'}
        pins = {
            label: ('commit-' + label, hashlib.sha256(payload).hexdigest())
            for label, payload in payloads.items()
        }

        def opener(url, timeout):
            label = 'vulnerable' if 'commit-vulnerable' in url else 'fixed'
            return io.BytesIO(payloads[label])

        archives = subject.fetch_verified_archives(pins, opener, 1024)

        self.assertEqual(archives['vulnerable'], payloads['vulnerable'])
        bad = dict(pins)
        bad['fixed'] = (bad['fixed'][0], '0' * 64)
        with self.assertRaisesRegex(RuntimeError, 'fixed archive hash mismatch'):
            subject.fetch_verified_archives(bad, opener, 1024)

    def test_guard_serves_only_pinned_archives_and_loopback_readiness(self):
        delegated = []

        def original(url, timeout):
            delegated.append((url, timeout))
            return io.BytesIO(b'ready')

        archives = {'vulnerable': b'v', 'fixed': b'f'}
        guarded = subject.GuardedUrlopen(archives, original)
        vulnerable_commit = subject.EXPECTED_PINS['vulnerable'][0]
        archive_url = (
            'https://codeload.github.com/kanboard/kanboard/tar.gz/'
            + vulnerable_commit)

        with guarded(archive_url, timeout=60) as response:
            self.assertEqual(response.read(), b'v')
        with guarded('http://127.0.0.1:12345/robots.txt', timeout=0.2) as response:
            self.assertEqual(response.read(), b'ready')
        self.assertEqual(delegated, [('http://127.0.0.1:12345/robots.txt', 0.2)])
        for rejected in (
                archive_url + '?changed=1',
                'http://localhost:12345/robots.txt',
                'https://example.test/',
                'http://user@127.0.0.1:12345/robots.txt'):
            with self.subTest(url=rejected):
                with self.assertRaisesRegex(RuntimeError, 'URL rejected'):
                    guarded(rejected, timeout=1)


class ObserverSubprocessTests(unittest.TestCase):
    def test_every_observer_docker_run_uses_exact_id_and_pull_never(self):
        calls = []

        class Delegate:
            def check_output(self, argv, **kwargs):
                calls.append(list(argv))
                if argv[:3] == ['docker', 'run', '-d']:
                    return 'c' * 64 + ('\n' if kwargs.get('text') else '')
                return 'PHP 8.4.27 (cli)\n'

            def run(self, argv, **kwargs):
                calls.append(list(argv))
                return SimpleNamespace(returncode=0, stdout='', stderr='')

        proxy = subject.ObserverSubprocess(Delegate(), subject.IMAGE_ID)
        server = [
            'docker', 'run', '-d', '--rm', '--pull=never', '--read-only',
            '--user', '1000', '--network', 'bridge', '--memory', '512m',
            '--cpus', '2', '--pids-limit', '128', '--tmpfs',
            '/tmp:rw,nosuid,size=64m', '-p', '127.0.0.1:12345:12345',
            '--mount', 'type=bind,source=/private/app,target=/app',
            '--workdir', '/app', '--entrypoint', 'php', subject.IMAGE_ID,
            '-S', '0.0.0.0:12345', '-t', '/app',
        ]
        self.assertEqual(proxy.check_output(server, text=True).strip(), 'c' * 64)
        old_version = [
            'docker', 'run', '--rm', '--network', 'none', '--entrypoint',
            'php', subject.IMAGE_ID, '--version',
        ]
        proxy.check_output(old_version, text=True)

        self.assertIn('--pull=never', calls[-1])
        self.assertIn(subject.IMAGE_ID, calls[-1])
        wrong = list(server)
        wrong[wrong.index(subject.IMAGE_ID)] = 'sha256:' + '0' * 64
        with self.assertRaisesRegex(RuntimeError, 'Docker run rejected'):
            proxy.check_output(wrong, text=True)


class RunnerBindingTests(unittest.TestCase):
    def test_bindings_point_only_to_the_new_fixed_candidate_inputs(self):
        candidate = subject.Candidate(
            subject.IMAGE, subject.IMAGE_ID, subject.DOCKERFILE_SHA256)

        bindings = subject.runner_bindings(candidate)

        self.assertEqual(set(bindings), {
            'QUALIFICATION_BASE', 'IMAGE', 'IMAGE_ID', 'IMAGE_RUNTIME_LABEL',
            'DOCKERFILE', 'DOCKERFILE_SHA256', 'CHECKS', 'RUNTIME_BUILD',
            'RUNTIME_BUILD_SHA256',
        })
        self.assertEqual(bindings['DOCKERFILE'], subject.DOCKERFILE)
        self.assertEqual(bindings['RUNTIME_BUILD'], subject.CANDIDATE_RECEIPT)
        self.assertNotIn('8.4.26', str(bindings))

    def test_adapter_restores_runner_and_observer_after_exception(self):
        original_checker = lambda current, original: {
            'current_runtime_both_arms': False}
        observer = SimpleNamespace(
            PINS=subject.EXPECTED_PINS, urlopen=object(), subprocess=object(),
            PHP_IMAGE='old-image', PHP_IMAGE_DIGEST='old-digest')
        runner = SimpleNamespace(
            observer_case=observer, subprocess=mock.Mock(),
            admit_and_probe_image=object(),
            observer_check_results=original_checker,
            artifact_check_results=lambda traces, texts, roots: {},
            public_observer_result=lambda value: value,
            **{name: 'old-' + name for name in subject.runner_bindings(
                subject.Candidate(subject.IMAGE, subject.IMAGE_ID,
                                  subject.DOCKERFILE_SHA256))},
        )
        original = {name: getattr(runner, name) for name in subject.runner_bindings(
            subject.Candidate(subject.IMAGE, subject.IMAGE_ID,
                              subject.DOCKERFILE_SHA256))}
        old_urlopen = observer.urlopen
        old_subprocess = observer.subprocess

        with self.assertRaisesRegex(RuntimeError, 'stop'):
            with subject.installed_runner_adapter(
                    runner,
                    subject.Candidate(subject.IMAGE, subject.IMAGE_ID,
                                      subject.DOCKERFILE_SHA256),
                    {'vulnerable': b'v', 'fixed': b'f'}):
                self.assertEqual(runner.IMAGE_ID, subject.IMAGE_ID)
                self.assertIsNot(observer.urlopen, old_urlopen)
                raise RuntimeError('stop')

        self.assertEqual(
            {name: getattr(runner, name) for name in original}, original)
        self.assertIs(observer.urlopen, old_urlopen)
        self.assertIs(observer.subprocess, old_subprocess)


if __name__ == '__main__':
    unittest.main()
