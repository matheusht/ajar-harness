#!/usr/bin/env python3
"""Signed app-state volume replay using the real controller and a fake Docker owner.

Run with Python 3, OpenSSL and ssh-keygen; no Docker daemon, provider, public
network, external application, or research target is contacted. The HTTP counter
and private connector are real processes; volume/container ownership is modeled.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import uuid
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'tools'), str(Path(__file__).parent)]
import application_volumes
import application_state
from engagement_contract import canonical, digest, load_inputs
import check_application_reset_e2e as reset


VOLUMES = [{'path': '/state/db', 'bytes': 4096}]
BASELINE_IMAGE = 'sha256:' + '3' * 64


class FakeDockerTargetEnvironment(reset.TargetEnvironment):
    """Exercise the production volume helper and journal with an in-memory Docker peer."""
    instances = []
    volumes = {}
    created_records = []
    preserve = 'preexisting-unrelated-volume'
    create_unknown = False
    hide_created_volume = False
    remove_unknown = False
    serial = 0

    def __init__(self, profile, limits, authorize, observe, **options):
        self.state_specs = copy.deepcopy(options.get('state_volumes') or [])
        self.volume_directories = {}
        self.mount_info = None
        super().__init__(profile, limits, authorize, observe, **options)

    @classmethod
    def reset_peer(cls):
        for row in cls.volumes.values():
            directory = row.get('directory')
            if directory:
                shutil.rmtree(directory, ignore_errors=True)
        cls.volumes = {cls.preserve: {'Name': cls.preserve, 'Driver': 'local', 'Scope': 'local',
            'Options': {'type': 'none'}, 'Labels': {'fixture': 'preserve'}, 'CreatedAt': '2026-01-01T00:00:00Z'}}
        cls.created_records = []
        cls.instances = []
        cls.serial = 0
        cls.create_unknown = cls.hide_created_volume = cls.remove_unknown = False

    def _daemon(self):
        return 'fixture-daemon'

    def _run(self, args, **_kwargs):
        if args[:2] == ['info', '--format']:
            return {'status': 'settled', 'returncode': 0, 'output': b'fixture-daemon\n'}
        if args[:2] == ['volume', 'inspect']:
            row = self.__class__.volumes.get(args[2])
            if row is None or (self.__class__.hide_created_volume and args[2] != self.preserve):
                return {'status': 'settled', 'returncode': 1, 'output': b''}
            return {'status': 'settled', 'returncode': 0, 'output': json.dumps([{
                key: value for key, value in row.items() if key != 'directory'}]).encode()}
        if args[:2] == ['volume', 'ls']:
            name = args[-1].removeprefix('name=^').removesuffix('$')
            present = name in self.__class__.volumes and not (self.__class__.hide_created_volume and name != self.preserve)
            return {'status': 'settled', 'returncode': 0, 'output': (name + '\n').encode() if present else b''}
        if args[:2] == ['volume', 'create']:
            labels, options = {}, {}
            cursor = 2
            while cursor < len(args) - 1:
                if args[cursor] == '--driver':
                    if args[cursor + 1] != 'local': return {'status': 'settled', 'returncode': 1, 'output': b''}
                    cursor += 2
                elif args[cursor] in ('--label', '--opt'):
                    key, value = args[cursor + 1].split('=', 1)
                    (labels if args[cursor] == '--label' else options)[key] = value
                    cursor += 2
                else:
                    return {'status': 'settled', 'returncode': 1, 'output': b''}
            name = args[-1]
            if name in self.__class__.volumes:
                return {'status': 'settled', 'returncode': 1, 'output': b''}
            directory = Path(tempfile.mkdtemp(prefix='state-volume-'))
            descriptor = next(row for row in self.identity['state_volumes'] if row['name'] == name)
            if self.profile['image_id'] != BASELINE_IMAGE:
                return {'status': 'settled', 'returncode': 1, 'output': b''}
            # NoCopy=true leaves initialization to the signed app inside its cgroup.
            self.__class__.serial += 1
            self.__class__.volumes[name] = {'Name': name, 'Driver': 'local', 'Scope': 'local',
                'Options': options, 'Labels': labels,
                'CreatedAt': f'2026-11-15T00:00:{self.__class__.serial:02d}Z', 'directory': str(directory)}
            self.__class__.created_records.append({key: value for key, value in self.__class__.volumes[name].items()
                if key != 'directory'})
            self.volume_directories[descriptor['path']] = directory
            return {'status': 'settled', 'returncode': 0, 'output': (name + '\n').encode()}
        if args[:2] == ['volume', 'rm']:
            if self.__class__.remove_unknown:
                return {'status': 'unknown', 'returncode': None, 'output': b''}
            row = self.__class__.volumes.pop(args[2], None)
            if row is None:
                return {'status': 'settled', 'returncode': 1, 'output': b''}
            if row.get('directory'):
                shutil.rmtree(row['directory'], ignore_errors=True)
            return {'status': 'settled', 'returncode': 0, 'output': b''}
        raise AssertionError('unexpected fake Docker command: ' + repr(args))

    def _event(self, phase, operation, operation_id, **fields):
        self.observe({'kind': 'environment-observation-v2', 'phase': phase, 'operation': operation,
            'operation_id': operation_id, 'identity': self.receipt(), **fields})

    def _effect(self, operation, args, *, cleanup=False, uncertain_key=None, **_kwargs):
        operation_id = uuid.uuid4().hex
        if uncertain_key:
            self.identity['unsettled'].append(uncertain_key)
        self._event('intent', operation, operation_id, request_sha256=digest(canonical(args)))
        result = self._run(args)
        if operation == 'create_state_volume' and self.__class__.create_unknown:
            result = {'status': 'unknown', 'returncode': None, 'output': b''}
        if result['status'] == 'settled' and result['returncode'] == 0 and uncertain_key:
            self.identity['unsettled'].remove(uncertain_key)
        self._event('result', operation, operation_id, status=result['status'],
            returncode=result['returncode'], output_sha256=digest(result['output']))
        return result

    def prepare(self, accesses, access_files, *, support_inputs=None):
        from application_volumes import identities, create, verify_mounts
        self.staged = copy.deepcopy(support_inputs or {})
        self.access_files = access_files
        nonce = uuid.uuid4().hex
        self.identity = {'kind': 'research-environment-receipt-v3', 'nonce': nonce,
            'container_id': None, 'container_name': 'oslit-' + nonce,
            'stage_container_id': None, 'stage_container_name': 'oslit-' + nonce + '-stage',
            'prepared_image_id': None, 'prepared_image_name': 'oslit-input-' + nonce + ':latest',
            'unsettled': [], 'daemon_id': 'fixture-daemon', 'image_id': self.profile['image_id'],
            'profile_sha256': 'sha256:' + hashlib.sha256(json.dumps(self.profile, sort_keys=True,
                separators=(',', ':')).encode()).hexdigest(),
            'access': [{'id': row['id'], 'kind': row['kind'], 'identity': row['identity']} for row in accesses],
            'support_inputs': [{'id': name, 'manifest_sha256': row['manifest_sha256']}
                for name, row in self.staged.items()],
            'state_volumes': identities(nonce, self.state_specs)}
        create(self)
        self.identity['container_id'] = digest(nonce.encode())[7:]
        self.mount_info = {'Mounts': [{'Destination': row['path'], 'Type': 'volume', 'Name': row['name'],
            'Driver': 'local', 'RW': True} for row in self.identity['state_volumes']],
            'HostConfig': {'Mounts': [{'Type': 'volume', 'Source': row['name'], 'Target': row['path'],
                'ReadOnly': False, 'BindOptions': None, 'TmpfsOptions': None, 'VolumeOptions': {'NoCopy': True}}
                for row in self.identity['state_volumes']]}}
        verify_mounts(self, self.mount_info)
        op = 'fixture-start-' + nonce
        self._event('intent', 'start', op)
        self.running = True
        self._event('result', 'start', op, status='settled')
        return {'status': 'prepared', 'identity': self.receipt(),
            'inputs': {row['id']: '/input/' + row['id'] for row in accesses},
            'support_inputs': {name: '/input/' + name for name in self.staged}}

    def launch_stdio(self, argv, *, role='native_tools'):
        mapped = []
        for value in argv:
            mapped.append(str(self.volume_directories[value]) if value in self.volume_directories else value)
        return super().launch_stdio(mapped, role=role)

    def readback(self):
        return {'status': 'running' if self.running else 'stopped', 'identity': self.receipt()}

    def cleanup(self):
        result = super().cleanup()
        application_volumes.cleanup(self)
        return result


def rejected(call, code_fragment):
    try:
        call()
    except Exception as error:
        actual = getattr(error, 'code', str(error))
        require(code_fragment in actual, f'expected {code_fragment!r}, got {actual!r}')
        return actual
    raise AssertionError('invalid volume input accepted')


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def signed_contract(path):
    inputs, scope, profile, filename = reset.configured(path, state_volumes=VOLUMES)
    verified = load_inputs(inputs)
    require(verified.frozen_files['applications/app-main.json'] == filename.read_bytes(),
        'signed v2 application profile was not frozen')
    require(profile['kind'] == 'owned-application-state-v2' and
        scope['application_states'][0]['profile_sha256'] == digest(filename.read_bytes()),
        'signed scope and application profile were not joined')
    row = application_volumes.identities('c' * 32, VOLUMES)[0]
    fake = SimpleNamespace(profile={'uid': 1000, 'gid': 1000}, identity={'state_volumes': [row]})
    def mount_info(no_copy):
        volume_options = {} if no_copy is None else {'NoCopy': no_copy}
        return {'Mounts': [{'Destination': row['path'], 'Type': 'volume', 'Name': row['name'],
            'Driver': 'local', 'RW': True}],
            'HostConfig': {'Mounts': [{'Type': 'volume', 'Source': row['name'], 'Target': row['path'],
                'ReadOnly': False, 'BindOptions': None, 'TmpfsOptions': None, 'VolumeOptions': volume_options}]}}
    for no_copy in (False, None):
        try:
            application_volumes.verify_mounts(fake, mount_info(no_copy))
        except ValueError:
            pass
        else:
            raise AssertionError(f'target verifier accepted NoCopy={no_copy!r}')
    application_volumes.verify_mounts(fake, mount_info(True))
    valid_digest = digest(filename.read_bytes())
    for specs in ([], [{}], [{'path': '/state/a', 'bytes': True}],
            [{'path': '/state/a/nested', 'bytes': 4096}],
            [{'path': '/state/a', 'bytes': 2048}],
            [{'path': '/state/a', 'bytes': 4097}],
            [{'path': '/state/a', 'bytes': 4096}, {'path': '/state/a', 'bytes': 4096}]):
        bad = copy.deepcopy(profile); bad['state_volumes'] = specs
        rejected(lambda: application_state.validate_profile(bad), 'application_state_profile_invalid')
    limits = next(row['limits'] for row in scope['environments'] if row['profile_id'] == 'target-main')
    rejected(lambda: application_volumes.validate([{'path': '/state/a', 'bytes': limits['workspace_bytes']}], limits),
        'application_state_volumes_invalid')
    require(digest(filename.read_bytes()) == valid_digest, 'negative profile cases changed signed bytes')
    original = filename.read_bytes()
    filename.write_bytes(canonical({**profile, 'baseline_id': 'changed'}))
    try:
        load_inputs(inputs)
    except Exception as error:
        require(getattr(error, 'code', None) == 'digest_mismatch', 'profile tamper had wrong refusal')
    else:
        raise AssertionError('changed signed volume profile accepted')
    filename.write_bytes(original)
    return inputs, [
        {'name': 'signed-v2-profile-frozen-and-profile-tamper-rejected', 'passed': True},
        {'name': 'target-mount-requires-volume-nocopy-true', 'passed': True},
        {'name': 'invalid-path-size-duplicate-and-total-byte-descriptors-rejected', 'passed': True}]


def workflow(path):
    import application_state as state_module
    FakeDockerTargetEnvironment.reset_peer()
    checks = []
    with reset.composed(path, state_volumes=VOLUMES) as x:
        original = state_module.Environment
        state_module.Environment = FakeDockerTargetEnvironment
        try:
            before = set(FakeDockerTargetEnvironment.volumes)
            first_response = reset.capture(x, starting_state={'app-main': 'counter-zero'})
            require(not first_response.get('isError'), 'first volume-backed capture refused: ' + str(first_response))
            first = reset.value(first_response)
            require(first['clean_start'] is True, 'signed volume baseline did not produce clean start')
            state = x.controller.state()
            first_start = next(iter(state['application_starts'].values()))
            first_nonce = first_start['receipt']['target_nonce']
            first_volume, = state['environments'][first_nonce]['identity']['state_volumes']
            require(first_volume['path'] == '/state/db' and first_volume['bytes'] == 4096
                and first_volume['name'].startswith('oslit-') and first_volume['created_at'],
                'application start omitted protected volume identity')
            created_info = next(row for row in FakeDockerTargetEnvironment.created_records
                if row['Name'] == first_volume['name'])
            require(created_info['Driver'] == 'local' and created_info['Labels'] == {
                'io.oslit.engagement': first_nonce,
                'io.oslit.profile': state['environments'][first_nonce]['identity']['profile_sha256'],
                'io.oslit.state.path': '/state/db', 'io.oslit.state.bytes': '4096'}
                and created_info['Options'] == application_volumes.options(
                    FakeDockerTargetEnvironment.instances[-1], first_volume),
                'volume labels or bounded local tmpfs options differ from the signed owner')
            require(first['output_sha256'] and FakeDockerTargetEnvironment.volumes.keys() == {FakeDockerTargetEnvironment.preserve},
                'first capture did not clean only its owned volume')
            checks.append({'name': 'v3-receipt-exact-local-tmpfs-labels-options-mount-and-cleanup', 'passed': True})
            operations = [row for row in state['environment_operations'].values()
                if row['identity']['nonce'] == first_nonce]
            created = next(row for row in operations if row['operation'] == 'create_state_volume')
            started = next(row for row in operations if row['operation'] == 'start')
            removed = next(row for row in operations if row['operation'] == 'remove_state_volume')
            require(created['intent'] is not None and created['result']['status'] == 'settled'
                and started['result']['status'] == 'settled' and removed['result']['status'] == 'settled'
                and operations.index(created) < operations.index(started) < operations.index(removed),
                'volume create/mount/cleanup order was not journaled')
            checks.append({'name': 'controller-journal-create-before-start-and-remove-after-stop', 'passed': True})
            second_response = reset.capture(x, starting_state={'app-main': 'counter-zero'})
            require(not second_response.get('isError'), 'second volume-backed capture refused: ' + str(second_response))
            second = reset.value(second_response)
            starts = list(x.controller.state()['application_starts'].values())
            second_start = next(row for row in starts if row['receipt']['target_nonce'] != first_nonce)
            second_volume, = x.controller.state()['environments'][second_start['receipt']['target_nonce']]['identity']['state_volumes']
            require(second_volume['name'] != first_volume['name'] and second_volume['created_at'] != first_volume['created_at'],
                'replay reused the prior volume generation')
            output = x.controller.read_object(second['output_sha256']).decode()
            require('0' in output, 'fresh generation did not begin from the pinned-image baseline')
            require(set(FakeDockerTargetEnvironment.volumes) == before,
                'cleanup removed or changed a preexisting volume')
            checks.append({'name': 'fresh-replay-generation-reaches-pinned-image-baseline-and-preserves-unrelated-volume', 'passed': True})
            FakeDockerTargetEnvironment.remove_unknown = True
            failed_response = reset.capture(x, starting_state={'app-main': 'counter-zero'})
            require(failed_response.get('isError'), 'uncertain volume cleanup reported a successful capture')
            failed_state = x.controller.state()
            failed_dispatches = [row for row in failed_state['dispatches'].values()
                if row.get('parent_dispatch_id') and row['status'] == 'unknown'
                and row['observation']['resources'].get('app-main') == 'unknown']
            require(failed_dispatches, 'cleanup failure did not leave an unknown dispatch: ' + repr([
                (row['status'], row.get('observation')) for row in failed_state['dispatches'].values()
                if row.get('parent_dispatch_id')]))
            failed_dispatch = failed_dispatches[0]
            require('app-main' in failed_state['resource_holds'] and failed_dispatch['observation']['status'] == 'unknown',
                'cleanup uncertainty released the application resource')
            failed_nonce = next(row['receipt']['target_nonce'] for row in failed_state['application_starts'].values()
                if row['grant']['dispatch_id'] == failed_dispatch['dispatch_id'])
            failed_volume, = failed_state['environments'][failed_nonce]['identity']['state_volumes']
            remove = next(row for row in failed_state['environment_operations'].values()
                if row['identity']['nonce'] == failed_nonce and row['operation'] == 'remove_state_volume')
            require(remove['result']['status'] == 'unknown' and failed_volume['name'] in FakeDockerTargetEnvironment.volumes,
                'uncertain removal lost its exact volume identity or result')
            checks.append({'name': 'unknown-volume-cleanup-retains-exact-volume-and-resource-hold', 'passed': True})
        finally:
            FakeDockerTargetEnvironment.remove_unknown = False
            state_module.Environment = original
            FakeDockerTargetEnvironment.reset_peer()
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = {'kind': 'application-state-volumes-e2e-v1',
        'classification': 'real_signed_contract_controller_http_and_private_connector_with_fake_docker_owner',
        'checks': [], 'provider_calls': 0, 'external_target_calls': 0, 'docker_calls': 0,
        'planned_not_exercised': ['v1 compatibility in this workflow', 'all invalid schema/path/size variants in the scenario table',
            'missing reset authority and invalid effect bindings', 'volume label/options/timestamp tampering',
            'uncertain create/readback and recovery', 'revocation during create or cleanup',
            'multiple volumes and limit-count boundary', 'physical Docker volume semantics', 'SSH transport'],
        'unverified': ['physical Docker volume semantics', 'SSH transport', 'provider/runtime integration', 'research acceptance']}
    with tempfile.TemporaryDirectory(prefix='app-state-volumes-') as folder:
        root = Path(folder).resolve()
        try:
            inputs, checks = signed_contract(root / 'contract')
            report['checks'].extend(checks)
            report['checks'].extend(workflow(root / 'workflow'))
            report['frozen_profile_sha256'] = digest(load_inputs(inputs).frozen_files['applications/app-main.json'])
            report['status'] = 'passed'
        except Exception as error:
            report['status'] = 'failed'
            report['error'] = getattr(error, 'code', type(error).__name__ + ': ' + str(error))
    source_names = ['tools/application_state.py', 'tools/application_volumes.py', 'tools/research_environment.py',
        'tools/engagement_contract.py', 'tools/engagement_evidence.py', 'tools/engagement_controller.py',
        'tools/engagement_native_boundary.py', 'evals/native-qualification/smoke/check_application_reset_e2e.py',
        'evals/native-qualification/APPLICATION-STATE-VOLUMES-SCENARIOS.md', str(Path(__file__).relative_to(ROOT))]
    report['source_sha256'] = {name: digest((ROOT / name).read_bytes()) for name in source_names}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'checks': len(report['checks']), 'output': str(args.output)}))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
