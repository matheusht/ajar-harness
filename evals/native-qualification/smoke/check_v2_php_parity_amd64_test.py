#!/usr/bin/env python3
"""Behavior tests for the cloud amd64 Kanboard parity admission checks."""

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / 'smoke'))
import check_v2_php_parity_amd64 as subject  # noqa: E402

COMMAND = (HERE / 't02-evidence/opencode-v2-php-parity-amd64-20261021a/'
           'run-command.txt')


class ParityAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = json.loads(
            (HERE / 'observer-evidence-final/observer-results.json').read_text())

    def current_result(self):
        value = copy.deepcopy(self.original)
        for arm in value['arms']:
            arm['runtime'] = subject.IMAGE_RUNTIME_LABEL
            arm['php'] = 'PHP 8.4.26 (cli) (built: test) (NTS)'
        return value

    def test_exact_image_admission(self):
        image = {
            'Id': subject.IMAGE_ID,
            'Architecture': 'amd64',
            'Os': 'linux',
            'RepoTags': [subject.IMAGE],
        }
        checks = subject.image_check_results(
            image, 'PHP 8.4.26 (cli)', ['Core', 'gd', 'PDO', 'pdo_sqlite'],
            subject.DOCKERFILE_SHA256)
        self.assertTrue(all(checks.values()), checks)

        wrong_id = dict(image, Id='sha256:' + '0' * 64)
        self.assertFalse(subject.image_check_results(
            wrong_id, 'PHP 8.4.26 (cli)', ['gd', 'pdo_sqlite'],
            subject.DOCKERFILE_SHA256)['exact_image_id'])
        wrong_arch = dict(image, Architecture='arm64')
        self.assertFalse(subject.image_check_results(
            wrong_arch, 'PHP 8.4.26 (cli)', ['gd', 'pdo_sqlite'],
            subject.DOCKERFILE_SHA256)['linux_amd64'])
        self.assertFalse(subject.image_check_results(
            image, 'PHP 8.4.26 (cli)', ['pdo_sqlite'],
            subject.DOCKERFILE_SHA256)['required_php_modules'])

    def test_wrong_image_id_executes_no_container(self):
        image = {
            'Id': 'sha256:' + '0' * 64,
            'Architecture': 'amd64',
            'Os': 'linux',
            'RepoTags': [subject.IMAGE],
        }

        def fail_closed(name, passed):
            if not passed:
                raise AssertionError(name)

        with mock.patch.object(subject.subprocess, 'run') as run:
            with self.assertRaisesRegex(AssertionError, 'exact image id'):
                subject.admit_and_probe_image(
                    image, subject.DOCKERFILE_SHA256, fail_closed)
            run.assert_not_called()

    def test_ordinary_and_differentiating_behavior(self):
        current = self.current_result()
        checks = subject.observer_check_results(current, self.original)
        self.assertTrue(all(checks.values()), checks)

        bad_ordinary = self.current_result()
        bad_ordinary['arms'][0]['private_project_control']['code'] = 500
        self.assertFalse(subject.observer_check_results(
            bad_ordinary, self.original)['ordinary_controls_both_arms'])

        bad_vulnerable = self.current_result()
        bad_vulnerable['arms'][0]['cross_role_read']['result']['project_id'] = 999
        self.assertFalse(subject.observer_check_results(
            bad_vulnerable, self.original)['vulnerable_exact_metadata'])

        bad_fixed = self.current_result()
        bad_fixed['arms'][1]['cross_role_read'] = {'result': {'id': 2}}
        self.assertFalse(subject.observer_check_results(
            bad_fixed, self.original)['fixed_cross_role_denial'])

        bad_cleanup = self.current_result()
        bad_cleanup['arms'][1]['cleanup']['container_absent'] = False
        self.assertFalse(subject.observer_check_results(
            bad_cleanup, self.original)['cleanup_complete'])

        duplicate = self.current_result()
        duplicate['arms'].append(copy.deepcopy(duplicate['arms'][0]))
        self.assertFalse(subject.observer_check_results(
            duplicate, self.original)['two_release_arms'])

    def test_public_artifact_admission(self):
        traces = {
            'vulnerable': [
                {'actor': 'admin', 'method': 'createUser',
                 'params': ['alice', '[REDACTED]'], 'raw_response': '{"result": 2}'},
                {'actor': 'admin', 'method': 'createUser',
                 'params': ['bob', '[REDACTED]'], 'raw_response': '{"result": 3}'},
            ],
            'fixed': [
                {'actor': 'admin', 'method': 'createUser',
                 'params': ['alice', '[REDACTED]'], 'raw_response': '{"result": 2}'},
                {'actor': 'admin', 'method': 'createUser',
                 'params': ['bob', '[REDACTED]'], 'raw_response': '{"result": 3}'},
            ],
        }
        checks = subject.artifact_check_results(
            traces, {'vulnerable': '127.0.0.1 request', 'fixed': '127.0.0.1 request'},
            ['/tmp/private-parity-root'])
        self.assertTrue(all(checks.values()), checks)

        leaked = copy.deepcopy(traces)
        leaked['vulnerable'][0]['params'][1] = 'synthetic-secret'
        self.assertFalse(subject.artifact_check_results(
            leaked, {}, [])['create_user_passwords_redacted'])
        self.assertFalse(subject.artifact_check_results(
            traces, {'fixed': '/tmp/private-parity-root/fixed-run'},
            ['/tmp/private-parity-root'])['private_paths_absent'])
        missing = subject.artifact_check_results(
            {'vulnerable': [], 'fixed': []}, {}, [])
        self.assertFalse(missing['expected_traces_present'])
        self.assertFalse(missing['expected_create_user_entries'])

    def test_docker_baseline_requires_exact_identity(self):
        before = {
            'containers': [], 'images': [subject.IMAGE_ID], 'volumes': [],
            'networks': ['bridge-id', 'host-id', 'none-id']}
        self.assertTrue(all(subject.docker_baseline_check_results(
            before, copy.deepcopy(before)).values()))
        after = copy.deepcopy(before)
        after['containers'].append('leftover-container')
        self.assertFalse(subject.docker_baseline_check_results(
            before, after)['containers_restored'])

    def test_repeatable_command_is_shell_valid_and_mismatch_stops(self):
        syntax = subprocess.run(
            ['bash', '-n', str(COMMAND)], capture_output=True, text=True)
        self.assertEqual(syntax.returncode, 0, syntax.stderr)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            marker = root / 'python-called'
            fake_docker = root / 'docker'
            fake_docker.write_text(
                '#!/bin/sh\n'
                'if [ "$1 $2" = "image inspect" ]; then\n'
                '  printf "%s\\n" '
                "'sha256:d0b96c08541486079634fd70a0ffb221c32b07a2a04a1a2ab7d041912a7c9a91'\n"
                'fi\n')
            fake_docker.chmod(0o700)
            fake_python = root / 'python3'
            fake_python.write_text(
                '#!/bin/sh\nprintf called > "$PYTHON_MARKER"\n')
            fake_python.chmod(0o700)
            env = os.environ.copy()
            env.update({
                'PATH': f'{root}:/usr/bin:/bin',
                'PARITY_CA_BUNDLE': str(root / 'ca.pem'),
                'PARITY_OUTPUT': str(root / 'output'),
                'PYTHON_MARKER': str(marker),
            })
            run = subprocess.run(
                ['bash', str(COMMAND)], cwd=HERE.parent.parent,
                env=env, capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertFalse(marker.exists(), run.stdout + run.stderr)


if __name__ == '__main__':
    unittest.main()
