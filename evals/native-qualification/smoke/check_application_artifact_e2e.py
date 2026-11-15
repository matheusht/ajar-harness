#!/usr/bin/env python3
"""Exercise signed app-owned artifact lifecycle through simulated application capture.

Run with --output FILE. Uses the real controller, boundary, journal and application
owner with a fake Docker volume peer. No Docker daemon, provider, or external target.
"""
from __future__ import annotations

import argparse
import copy
from contextlib import contextmanager
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'tools'), str(Path(__file__).parent)]

import check_application_reset_e2e as reset
import check_application_state_volumes_e2e as volume_fixture
import check_owned_lab_state_e2e as lab_fixture
import engagement_lab_artifacts as artifacts
from engagement_contract import canonical, digest, load_inputs
from engagement_controller import Controller
from research_environment import Environment

VOLUMES = [{'path': '/state/db', 'bytes': 4096}]
BASE_CONFIGURED = reset.configured


def require(value, message):
    if not value:
        raise AssertionError(message)


def rejected(call):
    try:
        call()
    except Exception as error:
        return getattr(error, 'code', type(error).__name__)
    raise AssertionError('invalid app artifact authority was accepted')


def configured_with_artifact(path, **options):
    state_volumes = options.pop('state_volumes', VOLUMES)
    inputs, scope, profile, filename = BASE_CONFIGURED(path, state_volumes=state_volumes, **options)
    document = json.loads(inputs.read_bytes())
    access = next(row for row in scope['access'] if row['id'] == 'app-main')
    access['permissions'].append('write')
    effect = {'id': 'app-artifact', 'kind': 'artifact_create', 'access_ids': ['app-main'],
        'environment_ids': ['target-main'], 'account_refs': [], 'rung': 'source_only',
        'artifact_classes': [artifacts.APPLICATION_CLASS], 'cleanup_required': True}
    scope['effects'].append(effect)
    scope['application_states'][0]['artifact_effect_id'] = effect['id']
    reset.fixture.write(inputs, canonical(document))
    reset.fixture.resign_fixture(inputs, scope)
    return inputs, scope, profile, filename


class ArtifactVolumeTarget(volume_fixture.FakeDockerTargetEnvironment):
    """Reuse the volume peer while preserving the intent nonce and app readiness order."""
    instances = []
    trace = []
    controller = None
    application_launches = 0
    allocated = False

    def __init__(self, profile, limits, authorize, observe, **options):
        super().__init__(profile, limits, authorize, observe, **options)
        if self.identity is None:
            environment = Environment(profile, limits, authorize, observe, grant=self.grant,
                dispatch_guard=options['dispatch_guard'], lab_artifact=True,
                state_volumes=options.get('state_volumes'))
            self.identity = environment.receipt()
            self.identity['daemon_id'] = 'fixture-daemon'

    def allocation_identity(self):
        self.authorize()
        return copy.deepcopy(self.identity)

    def prepare(self, accesses, access_files, *, support_inputs):
        nonce = self.identity['nonce']
        row = self.controller.state()['lab_artifacts'].get(nonce)
        self.trace.append({'event': 'prepare_attempt', 'state': row['state'] if row else None})
        if row is None:
            common = {'kind': 'environment-observation-v2', 'operation': 'start',
                'operation_id': 'app-start-' + nonce, 'identity': self.receipt()}
            self.observe(dict(common, phase='intent'))
            raise AssertionError('controller accepted application allocation without artifact intent')
        require(row['state'] == 'intended', 'application allocation did not follow intent')
        self.staged = copy.deepcopy(support_inputs or {})
        self.access_files = access_files
        self.identity.update(container_id=digest(nonce.encode())[7:], stage_container_id='b' * 64,
            prepared_image_id='sha256:' + 'c' * 64,
            access=[{key: item[key] for key in ('id', 'kind', 'identity')} for item in accesses],
            support_inputs=[{'id': name, 'manifest_sha256': item['manifest_sha256']}
                for name, item in self.staged.items()])
        application_volumes = volume_fixture.application_volumes
        application_volumes.create(self)
        self.mount_info = {'Mounts': [{'Destination': item['path'], 'Type': 'volume', 'Name': item['name'],
                'Driver': 'local', 'RW': True} for item in self.identity['state_volumes']],
            'HostConfig': {'Mounts': [{'Type': 'volume', 'Source': item['name'], 'Target': item['path'],
                'ReadOnly': False, 'BindOptions': None, 'TmpfsOptions': None,
                'VolumeOptions': {'NoCopy': True}} for item in self.identity['state_volumes']]}}
        application_volumes.verify_mounts(self, self.mount_info)
        common = {'kind': 'environment-observation-v2', 'operation': 'start',
            'operation_id': 'app-start-' + nonce, 'identity': self.receipt()}
        self.observe(dict(common, phase='intent'))
        self.running = self.allocated = True
        self.observe(dict(common, phase='result', status='settled'))
        self.trace.append({'event': 'environment_allocated', 'state': row['state']})
        return {'status': 'prepared', 'identity': self.receipt(),
            'inputs': {item['id']: '/input/' + item['id'] for item in accesses},
            'support_inputs': {name: '/input/' + name for name in self.staged}}

    def artifact_state_readback(self):
        nonce = self.identity['nonce']
        row = self.controller.state()['lab_artifacts'].get(nonce)
        require(row is not None and row['state'] == 'intended', 'readiness was not read before callback')
        inventory = lab_fixture.inventory(self.limits, self.profile['uid'], self.profile['gid'])
        work = next(item for item in inventory['mounts'] if item['path'] == '/work')
        work['size_bytes'] -= sum(item['bytes'] for item in self.state_specs)
        for item in self.state_specs:
            inventory['mounts'].append({'path': item['path'], 'filesystem': 'tmpfs', 'readonly': False,
                'writable': True, 'size_bytes': item['bytes'], 'mode': 0o700,
                'uid': self.profile['uid'], 'gid': self.profile['gid'], 'kind': 'directory', 'device': None})
        configuration = lab_fixture.configuration(self.receipt(), self.profile, self.limits)
        work_bytes = self.limits['workspace_bytes'] - sum(item['bytes'] for item in self.state_specs)
        configuration['HostConfig']['Tmpfs']['/work'] = (
            f"rw,nosuid,nodev,size={work_bytes},uid={self.profile['uid']},"
            f"gid={self.profile['gid']},mode=0700")
        configuration['Mounts'] = self.mount_info['Mounts']
        configuration['HostConfig']['Mounts'] = self.mount_info['HostConfig']['Mounts']
        return {'kind': 'owned-lab-state-readback-v1', 'identity': self.receipt(),
            'configuration': configuration, 'inventory': inventory}

    def launch_stdio(self, argv, *, role='native_tools'):
        if role == 'application':
            nonce = self.identity['nonce']
            state = self.controller.state()['lab_artifacts'][nonce]['state']
            require(state == 'ready', 'application process launched before artifact readiness')
            self.trace.append({'event': 'application_launch', 'state': state})
            self.__class__.application_launches += 1
        return super().launch_stdio(argv, role=role)


@contextmanager
def fixture_case(path):
    ArtifactVolumeTarget.reset_peer()
    ArtifactVolumeTarget.trace = []
    ArtifactVolumeTarget.application_launches = 0
    ArtifactVolumeTarget.allocated = False
    with patch.object(reset, 'configured', configured_with_artifact), \
            patch.object(reset, 'TargetEnvironment', ArtifactVolumeTarget):
        with reset.composed(path, state_volumes=VOLUMES) as case:
            ArtifactVolumeTarget.controller = case.controller
            yield case
    ArtifactVolumeTarget.reset_peer()


def compatibility():
    for kind in ('source', 'binary'):
        identity = {'id': kind + '-main', 'kind': kind, 'account_refs': []}
        scope = {'access': [identity], 'application_states': [], 'effects': [{
            'id': 'create-' + kind, 'kind': 'artifact_create', 'access_ids': [identity['id']],
            'environment_ids': ['lab'], 'account_refs': [], 'rung': 'self',
            'artifact_classes': [artifacts.CLASS], 'cleanup_required': True}]}
        grant = {'resources': [identity['id']]}
        require(artifacts.select_effect(scope, grant, 'lab') == 'create-' + kind,
            f'owned source artifact selection changed for {kind}')


def contract_gates(path):
    inputs, scope, _, _ = configured_with_artifact(path)
    load_inputs(inputs)
    bad_cases = []
    for name, mutate in (
        ('wrong_effect', lambda value: value['application_states'][0].update(artifact_effect_id='reset-app')),
        ('wrong_class', lambda value: value['effects'][-1].update(artifact_classes=[artifacts.CLASS])),
        ('account_or_cleanup', lambda value: value['effects'][-1].update(account_refs=['acct'], cleanup_required=False)),
    ):
        changed = copy.deepcopy(scope); mutate(changed); reset.fixture.resign_fixture(inputs, changed)
        rejected(lambda: load_inputs(inputs))
        bad_cases.append(name)
    reset.fixture.resign_fixture(inputs, scope)
    return {'valid_app_class': artifacts.APPLICATION_CLASS, 'rejected': bad_cases}


def successful_capture(path):
    with fixture_case(path) as case:
        before = set(ArtifactVolumeTarget.volumes)
        response = reset.capture(case, starting_state={'app-main': 'counter-zero'})
        require(not response.get('isError'), 'signed application artifact capture failed: ' + str(reset.value(response)))
        captured = reset.value(response)
        state = case.controller.state()
        entries = [row for row in state['lab_artifacts'].values()
            if row['artifact_class'] == artifacts.APPLICATION_CLASS]
        require(len(entries) == 1 and entries[0]['state'] == 'clean',
            'application artifact did not reach clean state')
        require(captured['clean_start'] and case.controller.read_object(captured['output_sha256']) == b'0\n1\n1\n',
            'application reset did not preserve the signed baseline')
        events = [row['event'] for row in ArtifactVolumeTarget.trace]
        require(events.index('prepare_attempt') < events.index('environment_allocated') < events.index('application_launch'),
            'intent/readiness/application start order changed')
        require(ArtifactVolumeTarget.volumes.keys() == before,
            'application artifact cleanup changed unrelated volume state')
        return {'capture_status': 'passed', 'artifact_state': entries[0]['state'],
            'order': events, 'application_generation': entries[0]['nonce'],
            'volume_nocopy': True, 'unrelated_volumes_preserved': True}


def missing_intent(path):
    with fixture_case(path) as case:
        with patch.object(case.controller, 'record_lab_artifact_intent', lambda *_args: {'status': 'skipped'}):
            response = reset.capture(case, starting_state={'app-main': 'counter-zero'})
        require(response.get('isError'), 'application allocation without artifact intent succeeded')
        require(ArtifactVolumeTarget.application_launches == 0 and not ArtifactVolumeTarget.allocated,
            'missing intent allocated target state or launched application')
        require(not case.controller.state()['lab_artifacts'],
            'missing-intent setup unexpectedly created an artifact journal row')
        return {'capture_refused': True, 'application_launches': 0, 'target_allocated': False}


def cleanup_hold(path):
    with fixture_case(path) as case:
        ArtifactVolumeTarget.cleanup_fails = True
        response = reset.capture(case, starting_state={'app-main': 'counter-zero'})
        require(response.get('isError'), 'unobserved application cleanup reported success')
        state = case.controller.state()
        entries = [row for row in state['lab_artifacts'].values()
            if row['artifact_class'] == artifacts.APPLICATION_CLASS]
        require(entries and any(row['state'] != 'clean' for row in entries),
            'cleanup uncertainty was not retained in shared artifact journal')
        require('app-main' in state['resource_holds'] and any(row['status'] == 'unknown'
            for row in state['dispatches'].values()), 'uncertain application cleanup released its hold')
        return {'capture_refused': True, 'artifact_states': [row['state'] for row in entries],
            'application_held': True}


def recovery(path):
    with fixture_case(path) as case:
        ArtifactVolumeTarget.cleanup_fails = True
        response = reset.capture(case, starting_state={'app-main': 'counter-zero'})
        require(response.get('isError'), 'failure setup unexpectedly completed')
        dispatch = next(row for row in case.controller.state()['dispatches'].values()
            if row.get('parent_dispatch_id') and row['status'] == 'unknown')
        from engagement_runner import WorkerContext
        import engagement_native_boundary as boundary
        state = case.controller.state()
        grant = {key: dispatch[key] for key in __import__('engagement_controller').GRANT_KEYS}
        context = WorkerContext(case.context.runner, state['workers']['lead-1'], grant, case.context.workspace)
        ArtifactVolumeTarget.cleanup_fails = False
        original = boundary.Environment
        def recovered(profile, *args, **kwargs):
            environment = ArtifactVolumeTarget if profile['image_id'] == 'sha256:' + '3' * 64 else original
            return environment(profile, *args, **kwargs)
        with patch.object(boundary, 'Environment', recovered):
            result = boundary.recover_boundary(context, dispatch)
        require(result['status'] == 'settled', 'artifact cleanup recovery did not settle: ' + str(result))
        after = Controller(case.controller.root).state()
        require(all(row['state'] == 'clean' for row in after['lab_artifacts'].values()),
            'recovery left owned application artifact pending')
        require(ArtifactVolumeTarget.volumes.keys() == {ArtifactVolumeTarget.preserve},
            'recovery removed unrelated volume or retained owned application volume')
        return {'recovery_status': result['status'], 'artifacts_clean': True,
            'unrelated_volume_preserved': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = {'kind': 'application-owned-artifact-e2e-v1',
        'classification': 'engineering_simulation_fake_docker_volume_peer',
        'provider_calls': 0, 'docker_daemon_calls': 0, 'external_target_calls': 0,
        'research_acceptance': 'not_run', 'checks': []}
    try:
        compatibility()
        report['checks'].append({'name': 'source_binary_artifact_selector_compatibility', 'status': 'passed'})
        with tempfile.TemporaryDirectory(prefix='app-artifact-') as folder:
            root = Path(folder).resolve()
            for name, function in (('signed_effect_contract_gates', contract_gates),
                ('missing_intent_before_allocation', missing_intent),
                ('normal_ready_to_clean', successful_capture),
                ('cleanup_hold', cleanup_hold), ('cleanup_recovery', recovery)):
                directory = root / name; directory.mkdir(mode=0o700)
                report['checks'].append({'name': name, 'status': 'passed', 'observed': function(directory)})
        report['status'] = 'passed'
    except Exception as error:
        report['status'] = 'failed'
        report['error'] = getattr(error, 'code', type(error).__name__ + ': ' + str(error))
    report['command'] = [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'checks': len(report['checks']), 'output': str(args.output)}))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
