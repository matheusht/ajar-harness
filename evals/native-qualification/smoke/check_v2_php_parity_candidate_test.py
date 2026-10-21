#!/usr/bin/env python3
"""Behavior tests for fresh-candidate admission around the preserved runner."""

from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import types
import unittest


import check_v2_php_parity_candidate as subject


def _candidate(image_id: str = 'sha256:' + 'a' * 64) -> dict:
    return {
        'schema_version': 1,
        'kind': subject.CANDIDATE_KIND,
        'status': 'pass',
        'phase': 'registered_before_image_execution',
        'recorded_at': '2026-10-21T20:00:00Z',
        'qualification_base': subject.QUALIFICATION_BASE,
        'pre_registration': {
            'build_exit_code': 0,
            'image_executions': 0,
            'archive_retrieval_attempted': False,
            'application_arms_started': 0,
        },
        'build': {
            'dockerfile_path': 'evals/native-qualification/Dockerfile.opencode-kanboard-runtime',
            'dockerfile_sha256': subject.DOCKERFILE_SHA256,
            'dockerfile_default_base': subject.DOCKERFILE_DEFAULT_BASE,
            'effective_base': subject.EFFECTIVE_BASE,
            'context': 'evals/native-qualification',
            'platform': 'linux/amd64',
            'tag': subject.IMAGE_TAG,
            'load': True,
        },
        'ca': {
            'source_class': 'existing managed combined CA bundle',
            'source_path': '/etc/ssl/certs/ca-certificates.crt',
            'sha256_before': subject.CA_SHA256,
            'sha256_after': subject.CA_SHA256,
            'size_bytes': 230249,
            'mode': '0644',
            'secret_id': 'proxy_ca',
            'target': '/etc/apk/ca.pem',
            'bytes_recorded': False,
            'system_trust_changed': False,
        },
        'image': {
            'id': image_id,
            'tag': subject.IMAGE_TAG,
            'os': 'linux',
            'architecture': 'amd64',
            'repo_tags': [subject.IMAGE_TAG],
            'repo_digests': [],
            'created': '2026-10-21T20:00:00Z',
            'size_bytes': 1,
        },
        'archives': {
            label: {
                'url': subject.archive_url(commit),
                'commit': commit,
                'sha256': digest,
            }
            for label, (commit, digest) in subject.EXPECTED_PINS.items()
        },
        'repository_inputs': dict(subject.EXPECTED_REPOSITORY_INPUTS),
        'outer_baseline': {
            'private_receipt_sha256': 'b' * 64,
            'containers': [],
            'images': [],
            'volumes': [],
            'networks': list(subject.EXPECTED_NETWORK_IDS),
            'build_cache_record_ids': [],
            'candidate_tag_absent': True,
        },
        'prior_nonqualifying_image_ids': list(subject.PRIOR_IMAGE_IDS),
        'constraints': {
            'provider_calls': 0,
            'model_calls': 0,
            'live_targets_contacted': 0,
            'external_credentials_used': 0,
            'researcher_bundle_created': False,
        },
    }


class CandidateAdmissionTests(unittest.TestCase):
    def test_exact_receipt_bytes_and_schema_are_required(self):
        candidate = _candidate()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'candidate.json'
            path.write_text(json.dumps(candidate, sort_keys=True) + '\n')
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(subject.load_candidate_receipt(path, digest), candidate)
            with self.assertRaisesRegex(subject.AdmissionError, 'receipt SHA-256'):
                subject.load_candidate_receipt(path, '0' * 64)

            extra = copy.deepcopy(candidate)
            extra['unreviewed'] = True
            path.write_text(json.dumps(extra, sort_keys=True) + '\n')
            with self.assertRaisesRegex(subject.AdmissionError, 'schema'):
                subject.load_candidate_receipt(
                    path, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_candidate_and_current_metadata_must_match_exactly(self):
        candidate = _candidate()
        info = {
            'Id': candidate['image']['id'],
            'Os': 'linux',
            'Architecture': 'amd64',
            'RepoTags': [subject.IMAGE_TAG],
        }
        checks = subject.admission_checks(
            candidate, info, subject.DOCKERFILE_SHA256, subject.CA_SHA256,
            dict(subject.EXPECTED_REPOSITORY_INPUTS))
        self.assertTrue(all(checks.values()), checks)

        wrong_id = dict(info, Id='sha256:' + 'c' * 64)
        self.assertFalse(subject.admission_checks(
            candidate, wrong_id, subject.DOCKERFILE_SHA256, subject.CA_SHA256,
            dict(subject.EXPECTED_REPOSITORY_INPUTS))['exact image id'])
        wrong_arch = dict(info, Architecture='arm64')
        self.assertFalse(subject.admission_checks(
            candidate, wrong_arch, subject.DOCKERFILE_SHA256, subject.CA_SHA256,
            dict(subject.EXPECTED_REPOSITORY_INPUTS))['linux amd64'])
        self.assertFalse(subject.admission_checks(
            candidate, info, '0' * 64, subject.CA_SHA256,
            dict(subject.EXPECTED_REPOSITORY_INPUTS))['dockerfile unchanged'])
        self.assertFalse(subject.admission_checks(
            candidate, info, subject.DOCKERFILE_SHA256, '0' * 64,
            dict(subject.EXPECTED_REPOSITORY_INPUTS))['managed ca unchanged'])

    def test_both_archives_are_verified_before_return(self):
        payloads = {'vulnerable': b'vulnerable archive', 'fixed': b'fixed archive'}
        pins = {
            label: ('f' * 40 if label == 'fixed' else 'e' * 40,
                    hashlib.sha256(payload).hexdigest())
            for label, payload in payloads.items()
        }
        urls = {subject.archive_url(commit): payloads[label]
                for label, (commit, _digest) in pins.items()}
        opened = []

        def opener(url, timeout):
            opened.append((url, timeout))
            return io.BytesIO(urls[url])

        archives = subject.prefetch_archives(pins, opener=opener, max_bytes=1024)
        self.assertEqual(archives, payloads)
        self.assertEqual({item[0] for item in opened}, set(urls))

        bad_urls = dict(urls)
        bad_urls[subject.archive_url(pins['fixed'][0])] = b'wrong'
        with self.assertRaisesRegex(subject.AdmissionError, 'fixed archive SHA-256'):
            subject.prefetch_archives(
                pins, opener=lambda url, timeout: io.BytesIO(bad_urls[url]),
                max_bytes=1024)

    def test_url_dispatcher_is_closed_except_verified_archives_and_loopback_readiness(self):
        commit = 'e' * 40
        archive = b'pinned bytes'
        delegated = []

        def loopback(url, timeout):
            delegated.append((url, timeout))
            return io.BytesIO(b'ready')

        dispatcher = subject.QualifiedUrlopen(
            {subject.archive_url(commit): archive}, loopback)
        with dispatcher(subject.archive_url(commit), timeout=60) as response:
            self.assertEqual(response.read(), archive)
        with dispatcher('http://127.0.0.1:49152/robots.txt', timeout=0.2) as response:
            self.assertEqual(response.read(), b'ready')
        with self.assertRaisesRegex(subject.AdmissionError, 'URL denied'):
            dispatcher('https://example.invalid/', timeout=1)
        with self.assertRaisesRegex(subject.AdmissionError, 'URL denied'):
            dispatcher('http://localhost:49152/robots.txt', timeout=1)
        self.assertEqual(len(delegated), 1)

    def test_subprocess_proxy_enforces_exact_image_and_pull_never(self):
        calls = []

        class Delegate:
            DEVNULL = object()
            STDOUT = object()
            TimeoutExpired = TimeoutError

            def check_output(self, command, *args, **kwargs):
                calls.append(list(command))
                return 'ok'

        image_id = _candidate()['image']['id']
        proxy = subject.QualifiedSubprocess(Delegate(), image_id)
        version = [
            'docker', 'run', '--rm', '--network', 'none', '--entrypoint',
            'php', image_id, '--version']
        self.assertEqual(proxy.check_output(version, text=True), 'ok')
        self.assertIn('--pull=never', calls[-1])
        self.assertEqual(version, [
            'docker', 'run', '--rm', '--network', 'none', '--entrypoint',
            'php', image_id, '--version'])

        with self.assertRaisesRegex(subject.AdmissionError, 'candidate image'):
            proxy.check_output([
                'docker', 'run', '--rm', '--pull=never', '--entrypoint',
                'php', 'sha256:' + '0' * 64, '--version'])
        with self.assertRaisesRegex(subject.AdmissionError, 'unsupported docker run'):
            proxy.check_output([
                'docker', 'run', '--rm', '--pull=never', image_id, 'sh'])

    def test_runner_bindings_are_restored_after_failure(self):
        candidate = _candidate()
        original = {
            'urlopen': subject.observer_case.urlopen,
            'subprocess': subject.observer_case.subprocess,
            'image': subject.runner.IMAGE,
            'checks': subject.runner.CHECKS,
        }
        archive_bytes = {
            subject.archive_url(commit): label.encode()
            for label, (commit, _digest) in subject.EXPECTED_PINS.items()
        }
        with self.assertRaisesRegex(RuntimeError, 'delegate failed'):
            with subject.qualified_runner_bindings(candidate, archive_bytes):
                self.assertEqual(subject.runner.IMAGE, subject.IMAGE_TAG)
                self.assertEqual(subject.runner.IMAGE_ID, candidate['image']['id'])
                self.assertEqual(subject.runner.CHECKS, subject.CHECKS)
                raise RuntimeError('delegate failed')
        self.assertIs(subject.observer_case.urlopen, original['urlopen'])
        self.assertIs(subject.observer_case.subprocess, original['subprocess'])
        self.assertEqual(subject.runner.IMAGE, original['image'])
        self.assertEqual(subject.runner.CHECKS, original['checks'])


if __name__ == '__main__':
    unittest.main()
