#!/usr/bin/env python3
"""Exercise initial-scope artifact policy with a simulated owned lab.

Run with --output FILE. Uses the signed contract, controller, journal, native
boundary, and existing fake owned-lab peer; no provider, Docker, or target.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'tools'), str(Path(__file__).parent)]

import check_owned_lab_state_e2e as lab
from engagement_contract import canonical, load_inputs
from engagement_controller import Controller

POLICY = 'initial-scope-v1'
CLASS = 'owned-lab-state-v2'


def require(value, message):
    if not value:
        raise AssertionError(message)


def signed_case(path, *, policy=POLICY, effect_class=CLASS, mutate=None, start=False):
    def change(scope):
        scope['effects'][-2]['artifact_classes'] = [effect_class]
        if policy is not None:
            scope['authority_policy'] = policy
        if mutate:
            mutate(scope)
    return lab.case(path, start=start, mutate=change)


def expect_rejected(call, label):
    try:
        call()
    except Exception as error:
        return {'name': label, 'status': 'refused', 'code': getattr(error, 'code', type(error).__name__)}
    raise AssertionError(label + ' was accepted')


def admission(path):
    """Real boundary startup exercises implicit artifact admission and readback."""
    source_scope = lab.b.fixture.fixture.fixture_scope
    scope_with_policy = lambda inputs: signed_scope(source_scope(inputs))
    with patch.object(lab.b.fixture.fixture, 'fixture_scope', scope_with_policy):
        _, x, context, stack = lab.b.simulated_boundary(path)
    with stack:
        import engagement_native_boundary as boundary
        stack.enter_context(patch.object(boundary, 'Environment', lab.LabEnvironment))
        stack.enter_context(patch.object(boundary.codex, 'Runtime', lab.LabRuntime))
        lab.LabEnvironment.controller = x.c
        lab.LabEnvironment.instances = []
        owner = boundary.NativeBoundary(context)
        started = owner.start()
        x.c.record_worker_started('lead-1', 1, started['session_id'], context.workspace,
            owner_receipt=started['owner_receipt'])
        artifacts = list(x.c.state()['lab_artifacts'].values())
        require(len(artifacts) == 1 and artifacts[0]['artifact_class'] == CLASS
            and artifacts[0]['state'] == 'ready', 'initial policy did not admit one ready v2 artifact')
        x.c.revoke_worker('lead-1', 1, reason='autonomy-fixture-finish')
        finished = owner.finish()
        require(finished['cleanup'] == 'verified', 'v2 artifact cleanup not read back')
        state = Controller(x.c.root).state()
        require(all(row['state'] == 'clean' for row in state['lab_artifacts'].values()),
            'v2 artifact did not reach clean state')
        event_types = [row['type'] for row in x.c._events()]
        require(not any('confirm' in name or 'approval' in name for name in event_types),
            'per-artifact confirmation event was inserted')
        status = x.c.status()
        require(status.get('authority_policy') == POLICY, 'status omitted effective authority policy')
        board = x.c.board()
        require(board.get('authority_policy') == POLICY, 'board omitted effective authority policy')
        export = path / 'export'; x.c.export(export)
        result = json.loads((export / 'result.json').read_bytes())
        require(result.get('authority_policy') == POLICY, 'export omitted effective authority policy')
        legacy_path = path / 'legacy'; legacy_path.mkdir(mode=0o700)
        legacy = lab.case(legacy_path, start=False)
        legacy_status = legacy.c.status()
        legacy_board = legacy.c.board()
        legacy_export = legacy_path / 'export'; legacy.c.export(legacy_export)
        legacy_result = json.loads((legacy_export / 'result.json').read_bytes())
        require(all(value.get('authority_policy') == 'legacy-confirmation' for value in
            (legacy_status, legacy_board, legacy_result)), 'legacy scope policy default changed')
        return {'artifact_count': len(artifacts), 'artifact_state': 'clean',
            'status_policy': status['authority_policy'], 'export_policy': result['authority_policy'],
            'board_policy': board['authority_policy'], 'legacy_policy': 'legacy-confirmation',
            'confirmation_events': 0}


def signed_scope(source):
    scope = lab.scope_with_artifact(source)
    scope['effects'][-2]['artifact_classes'] = [CLASS]
    scope['authority_policy'] = POLICY
    return scope


def select_signed_case(path, *, effect_class):
    """Load the signed scope, then exercise the artifact selector's resource binding."""
    x = signed_case(path, effect_class=effect_class, start=True)
    return lab.module().select_effect(x.contract.scope, x.grant(resources=['source-main']), 'lab-main')


def signed_resource_case(path, *, artifact_class=CLASS, artifact_access_ids=None):
    """Sign source, binary, and application access in one fixture for selector coverage."""
    fixture = lab.b.fixture.fixture
    original_make = fixture.make_fixture
    original_scope = fixture.fixture_scope

    def make_with_binary(root):
        inputs_path = original_make(root)
        inputs = json.loads(inputs_path.read_bytes())
        binary = Path(inputs['goal_file']).parent / 'binary-resource'
        fixture.write(binary, b'harmless selector fixture\n')
        inputs['access_files']['binary-main'] = str(binary)
        fixture.write(inputs_path, fixture.encoded(inputs))
        return inputs_path

    def adjusted(inputs_path):
        scope = original_scope(inputs_path)
        scope['access'][0]['permissions'] = ['read', 'write', 'execute']
        inputs = json.loads(inputs_path.read_bytes())
        binary_path = Path(inputs['access_files']['binary-main'])
        scope['access'].append({'id': 'binary-main', 'kind': 'binary',
            'identity': {'sha256': 'sha256:' + hashlib.sha256(binary_path.read_bytes()).hexdigest(),
                'platform': 'linux/arm64'}, 'account_refs': [],
            'permissions': ['read', 'write', 'execute']})
        scope['access'].append({'id': 'application-main', 'kind': 'application',
            'identity': {'base_url': 'https://app.example/', 'version': None},
            'account_refs': [], 'permissions': ['read', 'write', 'execute']})
        scope['network']['target'].append({'protocol': 'https', 'host': 'app.example', 'port': 443,
            'address_policy': {'public_only': True, 'cidrs': []}})
        scope = lab.scope_with_artifact(scope)
        artifact = scope['effects'][-2]
        artifact['artifact_classes'] = [artifact_class]
        artifact['access_ids'] = artifact_access_ids or ['source-main', 'binary-main', 'application-main']
        scope['authority_policy'] = POLICY
        return scope

    with patch.object(fixture, 'make_fixture', make_with_binary), patch.object(fixture, 'fixture_scope', adjusted):
        return lab.b.fixture.Case(path, start=False)


def resource_selection(root):
    observations = []
    x = signed_resource_case(root / 'all-modes')
    selector = lab.module().select_effect
    modes = {
        'source': ['source-main'],
        'binary': ['binary-main'],
        'application': ['application-main'],
        'combined': ['source-main', 'binary-main', 'application-main'],
    }
    for name, resources in modes.items():
        selected = selector(x.contract.scope, {'resources': resources}, 'lab-main')
        require(selected == 'create-lab', name + ' resource selection failed')
        observations.append({'mode': name, 'resources': resources, 'effect_id': selected})

    no_grant = signed_resource_case(root / 'no-matching-grant', artifact_access_ids=['binary-main'])
    observations.append(expect_rejected(lambda: selector(no_grant.contract.scope,
        {'resources': ['source-main']}, 'lab-main'), 'missing-matching-creation-grant'))

    legacy_application = signed_resource_case(root / 'legacy-v1-application',
        artifact_class='owned-lab-state-v1', artifact_access_ids=['application-main'])
    observations.append(expect_rejected(lambda: selector(legacy_application.contract.scope,
        {'resources': ['application-main']}, 'lab-main'),
        'legacy-v1-application-resource'))
    return observations


def policy_gates(root):
    observations = []
    missing = expect_rejected(lambda: signed_case(root / 'missing', policy=None), 'missing-policy-v2-effect')
    observations.append(missing)
    unknown = expect_rejected(lambda: signed_case(root / 'unknown', policy='future-policy-v9'), 'unknown-policy')
    observations.append(unknown)
    wrong = expect_rejected(lambda: select_signed_case(root / 'wrong-class', effect_class='owned-application-state-v1'),
        'misbound-application-class')
    observations.append(wrong)
    cleanup = expect_rejected(lambda: signed_case(root / 'cleanup', mutate=lambda scope:
        scope['effects'][-2].update(cleanup_required=False)), 'missing-cleanup-obligation')
    observations.append(cleanup)
    return observations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = {'kind': 'initial-scope-autonomy-e2e-v1',
        'classification': 'engineering_simulation_fake_owned_lab',
        'resource_mode_coverage': 'signed scope load plus selector evaluation for source, binary, application, and combined resource sets; selector-only resource fixtures are not dispatch-issued work grants; fake-lab startup/readback remains source-only',
        'provider_calls': 0, 'docker_daemon_calls': 0, 'external_target_calls': 0,
        'research_acceptance': 'not_run', 'checks': []}
    try:
        with tempfile.TemporaryDirectory(prefix='autonomy-policy-') as folder:
            root = Path(folder).resolve()
            gates = root / 'gates'; gates.mkdir(mode=0o700)
            report['checks'].append({'name': 'fail_closed_policy_gates', 'status': 'passed',
                'observed': policy_gates(gates)})
            flow = root / 'initial-policy-flow'; flow.mkdir(mode=0o700)
            report['checks'].append({'name': 'single_initial_scope_artifact_flow', 'status': 'passed',
                'observed': admission(flow)})
            report['checks'].append({'name': 'signed_resource_mode_selection', 'status': 'passed',
                'observed': resource_selection(root / 'resource-modes')})
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
