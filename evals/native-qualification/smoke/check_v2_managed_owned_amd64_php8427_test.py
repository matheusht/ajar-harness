#!/usr/bin/env python3
"""Offline behavioral tests for the bounded amd64 managed-owned controller."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


MODULE_PATH = Path(__file__).with_name('check_v2_managed_owned_amd64_php8427.py')
SPEC = importlib.util.spec_from_file_location('managed_php8427_controller', MODULE_PATH)
controller = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(controller)


IMAGE_ID = 'sha256:' + '1' * 64
BASE_CACHE_ID = 'cache-existing'
CACHE_ROOT_ID = 'cache-root'
CACHE_MIDDLE_ID = 'cache-middle'
CACHE_CHILD_ID = 'cache-child'
NETWORK = {
    'Id': 'network-default',
    'Name': 'bridge',
    'Driver': 'bridge',
    'Internal': False,
    'IPAM': {'Config': [{'Subnet': '172.17.0.0/16', 'Gateway': '172.17.0.1'}]},
    'Containers': {},
    'Labels': {},
    'Options': {},
}
IMAGE = {
    'Id': IMAGE_ID,
    'RepoTags': [controller.IMAGE_TAG],
    'RepoDigests': [],
    'Os': 'linux',
    'Architecture': 'amd64',
    'Config': {'Env': ['PATH=/usr/local/bin:/usr/bin:/bin']},
    'RootFS': {'Layers': ['sha256:' + '2' * 64]},
}


def completed(argv, returncode=0, stdout='', stderr=''):
    return subprocess.CompletedProcess(argv, returncode, stdout, stderr)


class FakeCommands:
    """Stateful Docker/runner seam; no real command is executed."""

    def __init__(self, *, preexisting_tag=False, bad_php=False,
                 bad_provenance=False, bad_env=False, truncated_managed=False,
                 leave_cache=False, remote_builder=False):
        self.preexisting_tag = preexisting_tag
        self.bad_php = bad_php
        self.bad_provenance = bad_provenance
        self.bad_env = bad_env
        self.truncated_managed = truncated_managed
        self.leave_cache = leave_cache
        self.remote_builder = remote_builder
        self.built = False
        self.image_present = preexisting_tag
        self.cache_rows = {
            BASE_CACHE_ID: {'ID': BASE_CACHE_ID, 'Size': 1024, 'Parents': []},
        }
        self.pruned_cache_ids = []
        self.calls = []
        self.output_root = None

    @property
    def cache_present(self):
        return any(identifier != BASE_CACHE_ID for identifier in self.cache_rows)

    def image(self):
        value = json.loads(json.dumps(IMAGE))
        if self.bad_env:
            value['Config']['Env'].append('OPENAI_APIKEY=owned-test-sentinel')
        return value

    def run(self, argv, **_kwargs):
        argv = list(argv)
        self.calls.append(argv)
        if argv[:3] == ['docker', 'context', 'show']:
            return completed(argv, stdout='default\n')
        if argv[:3] == ['docker', 'context', 'inspect']:
            value = [{
                'Name': 'default',
                'Endpoints': {'docker': {
                    'Host': 'unix:///var/run/docker.sock',
                    'SkipTLSVerify': False,
                }},
            }]
            return completed(argv, stdout=json.dumps(value))
        if argv[:4] == ['docker', 'info', '--format', '{{json .}}']:
            value = {
                'ID': 'owned-test-engine', 'Name': 'owned-test-engine',
                'OSType': 'linux', 'Architecture': 'x86_64', 'Driver': 'vfs',
                'ServerVersion': '28.4.0', 'DockerRootDir': '/var/lib/docker',
            }
            return completed(argv, stdout=json.dumps(value))
        if argv[:5] == ['docker', 'container', 'ls', '-aq', '--no-trunc']:
            return completed(argv)
        if argv[:5] == ['docker', 'image', 'ls', '-aq', '--no-trunc']:
            return completed(argv, stdout=(IMAGE_ID + '\n') if self.image_present else '')
        if argv[:3] == ['docker', 'image', 'inspect']:
            target = argv[3]
            if self.image_present and target in (IMAGE_ID, controller.IMAGE_TAG):
                return completed(argv, stdout=json.dumps([self.image()]))
            return completed(argv, returncode=1, stderr='not found')
        if argv[:4] == ['docker', 'volume', 'ls', '-q']:
            return completed(argv)
        if argv[:5] == ['docker', 'network', 'ls', '-q', '--no-trunc']:
            return completed(argv, stdout=NETWORK['Id'] + '\n')
        if argv[:3] == ['docker', 'network', 'inspect']:
            return completed(argv, stdout=json.dumps([NETWORK]))
        if argv[:5] == ['docker', 'buildx', 'ls', '--format', 'json']:
            row = {'Name': 'default', 'Driver': 'docker', 'Status': 'running',
                   'Buildkit': 'v0.24.0', 'Platforms': 'linux/amd64',
                   'LastActivity': 'ignored'}
            return completed(argv, stdout=json.dumps(row) + '\n')
        if argv[:4] == ['docker', 'buildx', 'inspect', 'default']:
            value = {
                'Name': 'default',
                'Driver': 'docker-container' if self.remote_builder else 'docker',
                'Nodes': [{
                    'Name': 'default',
                    'Endpoint': ('tcp://remote.invalid:1234'
                                 if self.remote_builder else 'default'),
                    'Status': 'running',
                    'Buildkit': 'v0.24.0',
                    'Platforms': 'linux/amd64,linux/amd64/v2',
                }],
            }
            return completed(argv, stdout=json.dumps(value))
        if argv[:5] == ['docker', 'buildx', 'du', '--format', 'json']:
            return completed(argv, stdout=''.join(
                json.dumps(self.cache_rows[key]) + '\n'
                for key in sorted(self.cache_rows)))
        if argv[:3] == ['docker', 'buildx', 'build']:
            self.built = self.image_present = True
            self.cache_rows.update({
                CACHE_ROOT_ID: {
                    'ID': CACHE_ROOT_ID, 'Size': 2048,
                    'Parents': [BASE_CACHE_ID],
                },
                CACHE_MIDDLE_ID: {
                    'ID': CACHE_MIDDLE_ID, 'Size': 3072,
                    'Parents': [CACHE_ROOT_ID],
                },
                CACHE_CHILD_ID: {
                    'ID': CACHE_CHILD_ID, 'Size': 4096,
                    'Parents': [CACHE_MIDDLE_ID],
                },
            })
            metadata = {
                'buildx.build.provenance': {
                    'buildType': 'https://mobyproject.org/buildkit@v1',
                    'materials': [{
                        'uri': ('pkg:docker/ghcr.io/anomalyco/opencode?digest='
                                'sha256:' + ('0' if self.bad_provenance else '85986f556e985e377bd24cd68a5ccfbc647bb49e591194edda8a0e4542303319')
                                + '&platform=linux%2Famd64'),
                        'digest': {'sha256': (
                            '0' if self.bad_provenance else
                            '85986f556e985e377bd24cd68a5ccfbc647bb49e591194edda8a0e4542303319')},
                    }],
                    'invocation': {
                        'configSource': {'entryPoint': controller.DOCKERFILE.name},
                        'parameters': {
                            'frontend': 'dockerfile.v0',
                            'secrets': [{'id': 'proxy_ca', 'optional': True}],
                            'locals': [{'name': 'context'}, {'name': 'dockerfile'}],
                        },
                        'environment': {'platform': controller.PLATFORM},
                    },
                },
                'containerimage.config.digest': IMAGE_ID,
                'containerimage.digest': 'sha256:' + '3' * 64,
            }
            metadata_path = Path(argv[argv.index('--metadata-file') + 1])
            metadata_path.write_text(json.dumps(metadata))
            return completed(argv, stdout='private build output')
        if argv[:2] == ['docker', 'run']:
            candidate = self.output_root / 'candidate.json'
            if not candidate.is_file():
                return completed(argv, returncode=97,
                                 stderr='candidate receipt missing before execution')
            entry = argv[argv.index('--entrypoint') + 1]
            if entry == 'apk':
                packages = sorted(
                    f'{name}-8.4.27-r0' for name in controller.REQUIRED_PHP_PACKAGES)
                packages += ['php84-common-8.4.27-r0', 'php84-pdo-8.4.27-r0']
                return completed(argv, stdout='\n'.join(packages) + '\n')
            if entry == 'php' and argv[-1] == '-v':
                version = 'PHP 8.4.26 (cli)' if self.bad_php else 'PHP 8.4.27 (cli)'
                return completed(argv, stdout=version + '\n')
            if entry == 'php' and argv[-1] == '-m':
                return completed(argv, stdout='Core\ngd\npdo_sqlite\n')
            if entry == 'opencode':
                return completed(argv, stdout='opencode v2.0.32\n')
            if entry == 'sh':
                return completed(argv, stdout='sh\nphp\nwget\nopencode\n')
            return completed(argv, returncode=98, stderr='unexpected probe')
        if argv and argv[0].endswith('python3') and str(controller.MANAGED_RUNNER) in argv:
            if '--live-free' in argv or '--live-runtime-ca' in argv:
                return completed(argv, returncode=96, stderr='live flag forbidden')
            managed = Path(argv[argv.index('--output') + 1])
            managed.mkdir(mode=0o700)
            names = [name for name, count in
                     sorted(controller.REQUIRED_MANAGED_CHECK_COUNTS.items())
                     for _ in range(count)]
            if self.truncated_managed:
                names.pop()
            checks = [{'name': name, 'pass': True} for name in names]
            result = {
                'status': 'pass',
                'classification': 'owned TLS/native managed CONNECT offline E2E; zero provider calls',
                'review_status': 'unqualified_owned_synthetic_response',
                'checks': checks,
                'native_runs': [
                    {'stage': 'first', 'exit_code': 0},
                    {'stage': 'reviewer', 'exit_code': 0},
                    {'stage': 'resume', 'exit_code': 0},
                ],
                'cleanup_complete': True,
                'temporary_secret_files_removed': True,
                'source_pins_stable': True,
                'source_copies_match': True,
            }
            (managed / 'result.json').write_text(json.dumps(result))
            return completed(argv, stdout=json.dumps({'status': 'pass'}))
        if argv[:3] == ['docker', 'image', 'rm']:
            self.image_present = False
            return completed(argv, stdout=argv[-1] + '\n')
        if argv[:4] == ['docker', 'buildx', 'prune', '--force']:
            identifier = argv[-1].removeprefix('id=')
            self.pruned_cache_ids.append(identifier)
            if not self.leave_cache:
                self.cache_rows.pop(identifier, None)
            return completed(argv)
        return completed(argv, returncode=99, stderr='unexpected: ' + repr(argv))


class ControllerTests(unittest.TestCase):
    def attempt(self, commands, source_validator=None, source_snapshotter=None,
                env_updates=None):
        temp = tempfile.TemporaryDirectory(prefix='managed-controller-test-')
        self.addCleanup(temp.cleanup)
        output = Path(temp.name) / 'attempt'
        commands.output_root = output
        source = source_validator or (lambda: {
            'integration_head': controller.INTEGRATION_HEAD,
            'source_commit': 'f' * 40,
            'source_manifest_sha256': 'a' * 64,
        })
        snapshotter = source_snapshotter or (lambda _source, _output: {
            'root': controller.ROOT,
            'dockerfile': controller.DOCKERFILE,
            'managed_runner': controller.MANAGED_RUNNER,
            'relay': controller.RELAY,
        })
        environment = {'HTTPS_PROXY': 'http://managed.invalid:3128'}
        environment.update(env_updates or {})
        result = controller.run_attempt(
            output, Path('/managed/ca.pem'), commands, environment,
            source_validator=source,
            ca_validator=lambda _path: {
                'sha256': controller.CA_SHA256,
                'size_bytes': controller.CA_SIZE,
                'bytes': b'owned synthetic CA bytes',
            },
            source_snapshotter=snapshotter,
            expected_source_commit='f' * 40,
            recorded_at=lambda: '2026-10-21T22:00:00Z')
        return output, result

    def test_source_failure_prevents_every_docker_command(self):
        commands = FakeCommands()

        def fail_source():
            raise controller.GateError('source_pin_mismatch')

        output, result = self.attempt(commands, fail_source)
        self.assertEqual(1, result)
        self.assertEqual([], commands.calls)
        receipt = json.loads((output / 'result.json').read_text())
        self.assertEqual('blocked', receipt['status'])
        self.assertEqual('source_pin_mismatch', receipt['failure'])

    def test_source_change_before_snapshot_prevents_every_docker_command(self):
        commands = FakeCommands()

        def changed(_source, _output):
            raise controller.GateError('source_changed_before_snapshot')

        output, result = self.attempt(commands, source_snapshotter=changed)
        self.assertEqual(1, result)
        self.assertEqual([], commands.calls)
        receipt = json.loads((output / 'result.json').read_text())
        self.assertEqual('source_changed_before_snapshot', receipt['failure'])

    def test_validate_ca_rejects_symlink_without_following_it(self):
        with tempfile.TemporaryDirectory(prefix='managed-ca-test-') as folder:
            target = Path(folder) / 'target.pem'
            target.write_bytes(b'not the managed CA')
            link = Path(folder) / 'managed.pem'
            link.symlink_to(target)
            with self.assertRaisesRegex(controller.GateError,
                                        '^managed_ca_file_mismatch$'):
                controller.validate_ca(link)

    def test_preexisting_tag_refuses_build_and_image_execution(self):
        commands = FakeCommands(preexisting_tag=True)
        _output, result = self.attempt(commands)
        self.assertEqual(1, result)
        self.assertFalse(any(call[:3] == ['docker', 'buildx', 'build']
                             for call in commands.calls))
        self.assertFalse(any(call[:2] == ['docker', 'run'] for call in commands.calls))

    def test_remote_buildx_selector_refuses_build_and_image_execution(self):
        commands = FakeCommands()
        _output, result = self.attempt(
            commands, env_updates={'BUILDX_BUILDER': 'remote-builder'})
        self.assertEqual(1, result)
        self.assertFalse(any(call[:3] == ['docker', 'buildx', 'build']
                             for call in commands.calls))
        self.assertFalse(any(call[:2] == ['docker', 'run'] for call in commands.calls))

    def test_remote_selected_builder_refuses_build_and_image_execution(self):
        commands = FakeCommands(remote_builder=True)
        _output, result = self.attempt(commands)
        self.assertEqual(1, result)
        self.assertFalse(any(call[:3] == ['docker', 'buildx', 'build']
                             for call in commands.calls))
        self.assertFalse(any(call[:2] == ['docker', 'run'] for call in commands.calls))

    def test_candidate_is_registered_before_probes_and_offline_managed_run(self):
        commands = FakeCommands()
        output, result = self.attempt(commands)
        self.assertEqual(0, result)
        candidate = json.loads((output / 'candidate.json').read_text())
        self.assertEqual(IMAGE_ID, candidate['image_id'])
        self.assertEqual('sha256:' + '3' * 64,
                         candidate['build_provenance']['image_manifest_digest'])
        managed = next(call for call in commands.calls
                       if call and call[0].endswith('python3'))
        self.assertNotIn('--live-free', managed)
        self.assertNotIn('--live-runtime-ca', managed)
        self.assertEqual(IMAGE_ID, managed[managed.index('--cloud-image-id') + 1])
        self.assertTrue(all('--pull=never' in call for call in commands.calls
                            if call[:2] == ['docker', 'run']))
        receipt = json.loads((output / 'result.json').read_text())
        self.assertEqual('pass', receipt['status'])
        self.assertTrue(receipt['baseline_restored'])
        self.assertEqual(0, receipt['external_activity']['provider_calls'])
        self.assertFalse(commands.image_present)
        self.assertFalse(commands.cache_present)
        self.assertEqual(
            [CACHE_CHILD_ID, CACHE_MIDDLE_ID, CACHE_ROOT_ID],
            commands.pruned_cache_ids)
        self.assertEqual({BASE_CACHE_ID}, set(commands.cache_rows))

    def test_failed_runtime_admission_skips_managed_run_and_still_cleans(self):
        commands = FakeCommands(bad_php=True)
        _output, result = self.attempt(commands)
        self.assertEqual(1, result)
        self.assertFalse(any(call and call[0].endswith('python3') for call in commands.calls))
        self.assertFalse(commands.image_present)
        self.assertFalse(commands.cache_present)

    def test_bad_build_provenance_skips_image_execution_and_still_cleans(self):
        commands = FakeCommands(bad_provenance=True)
        _output, result = self.attempt(commands)
        self.assertEqual(1, result)
        self.assertFalse(any(call[:2] == ['docker', 'run'] for call in commands.calls))
        self.assertFalse(any(call and call[0].endswith('python3') for call in commands.calls))
        self.assertFalse(commands.image_present)
        self.assertFalse(commands.cache_present)

    def test_unexpected_image_environment_skips_probes_and_managed_run(self):
        commands = FakeCommands(bad_env=True)
        _output, result = self.attempt(commands)
        self.assertEqual(1, result)
        self.assertFalse(any(call[:2] == ['docker', 'run'] for call in commands.calls))
        self.assertFalse(any(call and call[0].endswith('python3') for call in commands.calls))
        self.assertFalse(commands.image_present)
        self.assertFalse(commands.cache_present)

    def test_truncated_managed_result_fails_and_still_cleans(self):
        commands = FakeCommands(truncated_managed=True)
        output, result = self.attempt(commands)
        self.assertEqual(1, result)
        receipt = json.loads((output / 'result.json').read_text())
        self.assertEqual('managed_required_checks_missing', receipt['failure'])
        self.assertFalse(commands.image_present)
        self.assertFalse(commands.cache_present)

    def test_unremoved_exact_cache_fails_outer_cleanup(self):
        commands = FakeCommands(leave_cache=True)
        output, result = self.attempt(commands)
        self.assertEqual(1, result)
        receipt = json.loads((output / 'result.json').read_text())
        self.assertEqual('fail', receipt['status'])
        self.assertFalse(receipt['baseline_restored'])
        self.assertEqual(
            [CACHE_CHILD_ID, CACHE_MIDDLE_ID, CACHE_ROOT_ID],
            receipt['cleanup']['unresolved_cache_ids'])


if __name__ == '__main__':
    unittest.main()
