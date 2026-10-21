#!/usr/bin/env python3
"""Behavior tests for the cloud amd64 Kanboard parity admission checks."""

import copy
import json
from pathlib import Path
import sys
import unittest


HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / 'smoke'))
import check_v2_php_parity_amd64 as subject  # noqa: E402


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
        image = {'Id': subject.IMAGE_ID, 'Architecture': 'amd64', 'Os': 'linux'}
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

    def test_public_artifact_admission(self):
        traces = {
            'vulnerable': [
                {'actor': 'admin', 'method': 'createUser',
                 'params': ['alice', '[REDACTED]'], 'raw_response': '{"result": 2}'},
            ],
            'fixed': [
                {'actor': 'bob', 'method': 'getSwimlane', 'params': [2],
                 'raw_response': '{"error":{"code":403}}'},
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


if __name__ == '__main__':
    unittest.main()
