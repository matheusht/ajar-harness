#!/usr/bin/env python3
"""Offline behavioral tests for the bounded amd64 managed-owned controller."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
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
    'Config': {'Env': [
        'PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
        'BUN_RUNTIME_TRANSPILER_CACHE_PATH=0',
    ]},
    'RootFS': {'Layers': ['sha256:' + '2' * 64]},
}


def completed(argv, returncode=0, stdout='', stderr=''):
    return subprocess.CompletedProcess(argv, returncode, stdout, stderr)


class FakeCommands:
    """Stateful Docker/runner seam; no real command is executed."""

    def __init__(self, *, preexisting_tag=False, bad_php=False,
                 bad_provenance=False, bad_env=False, truncated_managed=False,
                 bad_env_value=False, bad_cache_size=False,
                 missing_cache_parents=False, leave_cache=False,
                 remote_builder=False, bad_managed_image=False,
                 bad_parity=False, bad_parity_image=False,
                 late_unknown_cache=False):
        self.preexisting_tag = preexisting_tag
        self.bad_php = bad_php
        self.bad_provenance = bad_provenance
        self.bad_env = bad_env
        self.bad_env_value = bad_env_value
        self.bad_cache_size = bad_cache_size
        self.missing_cache_parents = missing_cache_parents
        self.truncated_managed = truncated_managed
        self.leave_cache = leave_cache
        self.remote_builder = remote_builder
        self.bad_managed_image = bad_managed_image
        self.bad_parity = bad_parity
        self.bad_parity_image = bad_parity_image
        self.late_unknown_cache = late_unknown_cache
        self.built = False
        self.image_present = preexisting_tag
        self.cache_rows = {
            BASE_CACHE_ID: {
                'ID': BASE_CACHE_ID,
                'Size': '36.8MiB' if bad_cache_size else '549B',
            },
        }
        if not missing_cache_parents:
            self.cache_rows[BASE_CACHE_ID]['Parents'] = None
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
        if self.bad_env_value:
            value['Config']['Env'][1] = 'BUN_RUNTIME_TRANSPILER_CACHE_PATH=1'
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
            row = {'Name': 'default',
                   'Driver': 'docker-container' if self.remote_builder else 'docker',
                   'Current': True,
                   'Nodes': [{
                       'Name': 'default',
                       'Endpoint': ('tcp://remote.invalid:1234'
                                    if self.remote_builder else 'default'),
                       'Status': 'running', 'Buildkit': 'v0.24.0',
                       'Platforms': 'linux/amd64',
                   }],
                   'LastActivity': 'ignored'}
            return completed(argv, stdout=json.dumps(row) + '\n')
        if argv[:4] == ['docker', 'buildx', 'inspect', 'default']:
            return completed(argv, returncode=1,
                             stderr='unknown flag: --format')
        if argv[:5] == ['docker', 'buildx', 'du', '--format', 'json']:
            return completed(argv, stdout=''.join(
                json.dumps(self.cache_rows[key]) + '\n'
                for key in sorted(self.cache_rows)))
        if argv[:3] == ['docker', 'buildx', 'build']:
            self.built = self.image_present = True
            self.cache_rows.update({
                CACHE_ROOT_ID: {
                    'ID': CACHE_ROOT_ID, 'Size': '36.8MB',
                    'Parents': None,
                },
                CACHE_MIDDLE_ID: {
                    'ID': CACHE_MIDDLE_ID, 'Size': '0B',
                    'Parents': [CACHE_ROOT_ID],
                },
                CACHE_CHILD_ID: {
                    'ID': CACHE_CHILD_ID, 'Size': '1.5kB',
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
        if (argv and argv[0] == sys.executable and len(argv) > 1
                and Path(argv[1]).name == controller.PARITY_WRAPPER.name):
            candidate_path = self.output_root / 'candidate.json'
            runtime_path = self.output_root / 'runtime-admission.json'
            if not candidate_path.is_file() or not runtime_path.is_file():
                return completed(argv, returncode=95,
                                 stderr='parity started before registration/runtime')
            if self.bad_parity:
                return completed(argv, returncode=1, stderr='bounded parity failure')
            parity_output = Path(argv[argv.index('--output') + 1])
            parity_output.mkdir(mode=0o700)
            candidate_sha = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
            summary = {
                'schema_version': 1,
                'kind': 't02-same-image-php8427-application-parity',
                'status': 'pass',
                'platform': controller.PLATFORM,
                'image_tag': controller.IMAGE_TAG,
                'image_id': ('sha256:' + '8' * 64
                             if self.bad_parity_image else IMAGE_ID),
                'checks_passed': 32,
                'both_arms_same_image': True,
                'docker_baseline_restored': True,
                'archive_inputs': {
                    'vulnerable': {
                        'commit': 'f0f7d27007f5a788f14416c548421efd740b7bce',
                        'sha256': ('3f24269475bf00137d4b0d957d97a2567a5249101'
                                   'dad89067a49d609f4df2edf'),
                    },
                    'fixed': {
                        'commit': 'a98bc5f855d4e7e47eb3425a6c7da6c6cc6748a3',
                        'sha256': ('44db3df81a25bbd56c768c8b3180a1f05879e2c7'
                                   'fbaa6ac73707e7f3e9098f56'),
                    },
                },
                'source_pins': {
                    'adapter_sha256': controller.PARITY_SOURCE_FILES[
                        controller.PARITY_ADAPTER_RELATIVE],
                    'runner_sha256': controller.PARITY_SOURCE_FILES[Path(
                        'evals/native-qualification/smoke/check_v2_php_parity_amd64.py')],
                    'dockerfile_sha256': controller.DOCKERFILE_SHA256,
                },
                'receipt_sha256': {
                    'outer_candidate': candidate_sha,
                    'registration_compatibility': '4' * 64,
                    'archive_admission': '7' * 64,
                    'parity_result': '5' * 64,
                    'public_observer_result': '6' * 64,
                },
                'external_activity': {
                    'public_source_archives_retrieved': 2,
                    'provider_calls': 0,
                    'model_calls': 0,
                    'live_targets_contacted': 0,
                    'researcher_bundle_created': False,
                },
                'claim_limits': {
                    'owned_offline_application_semantics_only': True,
                    'provider_or_model_route_qualified': False,
                    'default_adoption': False,
                },
            }
            (parity_output / 'same-image-summary.json').write_text(
                json.dumps(summary))
            if self.late_unknown_cache:
                self.cache_rows['cache-unregistered'] = {
                    'ID': 'cache-unregistered', 'Size': '1kB', 'Parents': None}
            return completed(argv, stdout=json.dumps({'status': 'pass'}))
        if argv and argv[0] == sys.executable and str(controller.MANAGED_RUNNER) in argv:
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
                'selected_boundary': {
                    'cloud': True,
                    'platform': controller.PLATFORM,
                    'image_id': ('sha256:' + '9' * 64
                                 if self.bad_managed_image else IMAGE_ID),
                    'relay_sha': controller.RELAY_SHA256,
                    'internal_subnet': controller.INTERNAL_SUBNET,
                    'external_subnet': controller.EXTERNAL_SUBNET,
                    'listen': controller.LISTEN_ADDRESS,
                    'peer': controller.RELAY_PEER,
                    'upstream_route': controller.UPSTREAM_ROUTE,
                },
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
                parity_source_validator=None, parity_source_snapshotter=None,
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
            'checks': controller.CHECKS,
            'managed_runner': controller.MANAGED_RUNNER,
            'parity_wrapper': controller.PARITY_WRAPPER,
            'relay': controller.RELAY,
        })
        parity_validator = parity_source_validator or (lambda _root: {
            'source_head': controller.PARITY_SOURCE_HEAD,
            'adapter_sha256': controller.PARITY_SOURCE_FILES[
                controller.PARITY_ADAPTER_RELATIVE],
            'files': [],
        })
        parity_snapshotter = parity_source_snapshotter or (
            lambda _source, _staged_root: {
                'root': controller.ROOT,
                'native_root': controller.ROOT / 'evals/native-qualification',
                'adapter': controller.ROOT / controller.PARITY_ADAPTER_RELATIVE,
                'dockerfile': controller.DOCKERFILE,
                'checks': controller.CHECKS,
            })
        environment = {'HTTPS_PROXY': 'http://managed.invalid:3128'}
        environment.update(env_updates or {})
        result = controller.run_attempt(
            output, Path('/managed/ca.pem'), commands, environment,
            parity_source_root=Path('/published/pr182'),
            source_validator=source,
            parity_source_validator=parity_validator,
            ca_validator=lambda _path: {
                'sha256': controller.CA_SHA256,
                'size_bytes': controller.CA_SIZE,
                'bytes': b'owned synthetic CA bytes',
            },
            source_snapshotter=snapshotter,
            parity_source_snapshotter=parity_snapshotter,
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

    def test_parity_source_failure_prevents_every_docker_command(self):
        commands = FakeCommands()

        def fail_parity(_root):
            raise controller.GateError('parity_source_pin_mismatch')

        output, result = self.attempt(
            commands, parity_source_validator=fail_parity)
        self.assertEqual(1, result)
        self.assertEqual([], commands.calls)
        receipt = json.loads((output / 'result.json').read_text())
        self.assertEqual('blocked', receipt['status'])
        self.assertEqual('parity_source_pin_mismatch', receipt['failure'])

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
        self.assertFalse(any(call[:4] ==
                             ['docker', 'buildx', 'inspect', 'default']
                             for call in commands.calls))
        parity = next(call for call in commands.calls
                      if call and call[0] == sys.executable
                      and Path(call[1]).name == controller.PARITY_WRAPPER.name)
        managed = next(call for call in commands.calls
                       if call and call[0] == sys.executable
                       and '--cloud-image-id' in call)
        self.assertLess(commands.calls.index(parity), commands.calls.index(managed))
        self.assertNotIn('--live-free', managed)
        self.assertNotIn('--live-runtime-ca', managed)
        self.assertEqual(IMAGE_ID, managed[managed.index('--cloud-image-id') + 1])
        self.assertTrue(all('--pull=never' in call for call in commands.calls
                            if call[:2] == ['docker', 'run']))
        receipt = json.loads((output / 'result.json').read_text())
        baseline = json.loads((output / 'baseline.private.json').read_text())
        self.assertEqual('pass', receipt['status'])
        self.assertTrue(receipt['baseline_restored'])
        self.assertEqual(
            [{'id': BASE_CACHE_ID, 'parents': [], 'size_bytes': 549}],
            baseline['cache'])
        self.assertEqual(549, baseline['cache_bytes'])
        self.assertEqual(0, receipt['external_activity']['provider_calls'])
        self.assertEqual(IMAGE_ID, receipt['same_image_parity']['image_id'])
        self.assertEqual(
            IMAGE_ID, receipt['managed']['selected_boundary']['image_id'])
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
        self.assertFalse(any(call and call[0] == sys.executable for call in commands.calls))
        self.assertFalse(commands.image_present)
        self.assertFalse(commands.cache_present)

    def test_bad_build_provenance_skips_image_execution_and_still_cleans(self):
        commands = FakeCommands(bad_provenance=True)
        _output, result = self.attempt(commands)
        self.assertEqual(1, result)
        self.assertFalse(any(call[:2] == ['docker', 'run'] for call in commands.calls))
        self.assertFalse(any(call and call[0] == sys.executable for call in commands.calls))
        self.assertFalse(commands.image_present)
        self.assertFalse(commands.cache_present)

    def test_unexpected_image_environment_skips_probes_and_managed_run(self):
        commands = FakeCommands(bad_env=True)
        _output, result = self.attempt(commands)
        self.assertEqual(1, result)
        self.assertFalse(any(call[:2] == ['docker', 'run'] for call in commands.calls))
        self.assertFalse(any(call and call[0] == sys.executable for call in commands.calls))
        self.assertFalse(commands.image_present)
        self.assertFalse(commands.cache_present)

    def test_changed_safe_image_environment_value_skips_runtime_execution(self):
        commands = FakeCommands(bad_env_value=True)
        _output, result = self.attempt(commands)
        self.assertEqual(1, result)
        self.assertFalse(any(call[:2] == ['docker', 'run'] for call in commands.calls))
        self.assertFalse(any(call and call[0] == sys.executable
                             for call in commands.calls))
        self.assertFalse(commands.image_present)
        self.assertFalse(commands.cache_present)

    def test_unsupported_cache_size_unit_blocks_before_build(self):
        commands = FakeCommands(bad_cache_size=True)
        output, result = self.attempt(commands)
        self.assertEqual(1, result)
        receipt = json.loads((output / 'result.json').read_text())
        self.assertEqual('docker_cache_row_invalid', receipt['failure'])
        self.assertFalse(any(call[:3] == ['docker', 'buildx', 'build']
                             for call in commands.calls))
        self.assertFalse(any(call[:2] == ['docker', 'run']
                             for call in commands.calls))

    def test_missing_cache_parents_blocks_before_build(self):
        commands = FakeCommands(missing_cache_parents=True)
        output, result = self.attempt(commands)
        self.assertEqual(1, result)
        receipt = json.loads((output / 'result.json').read_text())
        self.assertEqual('docker_cache_row_invalid', receipt['failure'])
        self.assertFalse(any(call[:3] == ['docker', 'buildx', 'build']
                             for call in commands.calls))

    def test_truncated_managed_result_fails_and_still_cleans(self):
        commands = FakeCommands(truncated_managed=True)
        output, result = self.attempt(commands)
        self.assertEqual(1, result)
        receipt = json.loads((output / 'result.json').read_text())
        self.assertEqual('managed_required_checks_missing', receipt['failure'])
        self.assertFalse(commands.image_present)
        self.assertFalse(commands.cache_present)

    def test_failed_parity_skips_managed_run_and_still_cleans(self):
        commands = FakeCommands(bad_parity=True)
        output, result = self.attempt(commands)
        self.assertEqual(1, result)
        receipt = json.loads((output / 'result.json').read_text())
        self.assertEqual('same_image_parity_runner_failed', receipt['failure'])
        self.assertFalse(any('--cloud-image-id' in call for call in commands.calls))
        self.assertFalse(commands.image_present)
        self.assertFalse(commands.cache_present)

    def test_parity_image_mismatch_skips_managed_run_and_still_cleans(self):
        commands = FakeCommands(bad_parity_image=True)
        output, result = self.attempt(commands)
        self.assertEqual(1, result)
        receipt = json.loads((output / 'result.json').read_text())
        self.assertEqual(
            'same_image_parity_result_admission_failed', receipt['failure'])
        self.assertFalse(any('--cloud-image-id' in call for call in commands.calls))
        self.assertFalse(commands.image_present)
        self.assertFalse(commands.cache_present)

    def test_managed_boundary_image_mismatch_fails_and_still_cleans(self):
        commands = FakeCommands(bad_managed_image=True)
        output, result = self.attempt(commands)
        self.assertEqual(1, result)
        receipt = json.loads((output / 'result.json').read_text())
        self.assertEqual('managed_result_admission_failed', receipt['failure'])
        self.assertFalse(commands.image_present)
        self.assertFalse(commands.cache_present)

    def test_unregistered_late_cache_is_not_removed(self):
        commands = FakeCommands(late_unknown_cache=True)
        output, result = self.attempt(commands)
        self.assertEqual(1, result)
        receipt = json.loads((output / 'result.json').read_text())
        self.assertIn('unregistered_cache_records_present',
                      receipt['cleanup']['errors'])
        self.assertIn('cache-unregistered', receipt['cleanup']['unresolved_cache_ids'])
        self.assertEqual([], commands.pruned_cache_ids)

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
