#!/usr/bin/env python3
"""Signed source capture selection and reviewed escalation, with fake native peers.

Python 3, ssh-keygen and OpenSSL are required. The pinned harmless probe executes
as an owned local subprocess; container/model ownership and reviewer judgments
are engineering simulations. No provider, Docker, SSH or research target calls.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import copy
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'tools'), str(Path(__file__).parent)]
from engagement_contract import canonical, digest
from engagement_runner import WorkerContext
import check_engagement_native_boundary_e2e as native
import check_native_application_capture_e2e as application
from check_native_target_accounts_e2e import require, receiver


class UniqueRuntime(native.SimulatedRuntime):
    def fresh(self):
        self.session_id = 'capture-effect-session-' + str(len(self.instances))
        return {'session_id': self.session_id}


@contextmanager
def composed(path, *, elevated=True, invalid=False, no_initial=False, ambiguous=False):
    original = native.fixture.fixture.resign_fixture
    def sign(inputs, scope):
        scope['escalation_ceiling'] = 'cross_user'
        scope['limits']['hard']['invocations'] = 30
        initial = dict(scope['effects'][0], rung='self')
        scope['effects'] = [initial]
        if elevated:
            scope['effects'] += [dict(initial, id=rung + '-source', rung=rung) for rung in ('stored', 'cross_user')]
        if no_initial:
            scope['effects'] = [dict(initial, id='stored-source', rung='stored')]
        if ambiguous:
            scope['effects'].append(dict(initial, id='other-initial-read'))
        if invalid:
            scope['access'] = [row for row in scope['access'] if row['id'] == 'source-main']
            scope['environments'] = [row for row in scope['environments'] if row['profile_id'] == 'lab-main']
            scope['access'][0]['account_refs'] = ['named-source-account']
            scope['access'][0]['permissions'] = ['read', 'execute', 'write']
            source = copy.deepcopy(scope['access'][0]); source['id'] = 'source-other'
            scope['access'].append(source)
            environment = copy.deepcopy(scope['environments'][0]); environment['profile_id'] = 'lab-other'
            scope['environments'].append(environment)
            document = json.loads(inputs.read_bytes())
            document['access_files']['source-other'] = document['access_files']['source-main']
            document['environment_profiles']['lab-other'] = document['environment_profiles']['lab-main']
            native.fixture.fixture.write(inputs, canonical(document))
            scope['effects'] += [dict(initial, id='wrong-access', access_ids=['source-other']),
                dict(initial, id='wrong-environment', environment_ids=['lab-other']),
                dict(initial, id='account-effect', account_refs=['named-source-account']),
                dict(initial, id='artifact-effect', kind='artifact_create', artifact_classes=['harmless-fixture'], cleanup_required=True),
                dict(initial, id='execute-source', kind='execute')]
        original(inputs, scope)
    with patch.object(native.fixture.fixture, 'resign_fixture', sign):
        boundary, case, context, stack = native.simulated_boundary(path, lease_seconds=60)
    with stack:
        stack.enter_context(patch.object(boundary.codex, 'Runtime', UniqueRuntime))
        instance = boundary.NativeBoundary(context)
        info = instance.start()
        case.c.record_worker_started('lead-1', 1, info['session_id'], context.workspace, owner_receipt=info['owner_receipt'])
        native.SimulatedEnvironment.native_files = {'candidate.txt': b'harmless candidate',
            'probe.py': b'print("owned harmless probe completed")\n'}
        case.instrument()
        case.boundaries = [(instance, context)]
        try:
            yield case, instance, context
        finally:
            for item, _ in reversed(case.boundaries):
                item.finish()


def arguments(effect=None):
    value = {'instrument_id': 'instrument-1', 'candidate_path': 'candidate.txt', 'probe_path': 'probe.py',
        'interpreter': 'python3', 'arguments': [], 'conditions': {'fixture': 'one'}, 'seconds': 10,
        'patch_id': None, 'patch_arm': None}
    if effect is not None:
        value['effect_id'] = effect
    return value


def invoke(instance, context, args):
    context.renew(60)
    with context.guard():
        operation = instance.host_call('engagement_capture', args)
    result = operation.wait()
    return result, json.loads(result['content'][0]['text'])


def capture(case, instance, context, name, *, effect=None, purpose='effect', explains=None):
    result, value = invoke(instance, context, arguments(effect))
    require(not result.get('isError'), 'protected capture failed: ' + str(value))
    operation = case.c.state()['environment_operations'][value['operation_id']]
    require(operation['effect_id'] == (effect or 'read-source'), 'captured effect was not bound to selected permission')
    case.request('experiment_record', {'experiment_id': name, 'instrument_id': 'instrument-1',
        'candidate_sha256': value['candidate_sha256'], 'probe_sha256': value['probe_sha256'],
        'operation_id': value['operation_id'], 'purpose': purpose, 'conditions': {'fixture': 'one'},
        'score': None, 'resources': ['source-main'], 'explains': explains, 'supersedes': []}, context.principal)
    return value


def review_claim(case, lead, lead_context, name, *, effect=None):
    effect_name, control_name = name + '-effect', name + '-control'
    capture(case, lead, lead_context, effect_name, effect=effect)
    capture(case, lead, lead_context, control_name, effect=effect, purpose='control',
        explains={'experiment_id': effect_name, 'variable': 'fixture-switch'})
    case.request('claim_propose', {'claim_id': name, 'text': 'Harmless composed fixture effect.',
        'effect': effect_name, 'control': control_name, 'replay': None, 'contrary': ['contrary'],
        'resources': ['source-main'], 'supersedes': []})
    actor = case.worker(name + '-reviewer', 'reviewer', start=False)
    packet = case.request('review_request', {'review_id': 'review-' + name, 'kind': 'claim',
        'subject_id': name, 'reviewer_id': actor.id})['result']['payload']['packet_sha256']
    grant = case.c.prepare_worker_dispatch(actor.id, 1, case.workspace(actor.id), seconds=60,
        resources=['source-main'], adapter_id='fixture-adapter')
    context = WorkerContext(lead_context.runner, case.c.state()['workers'][actor.id], grant, case.workspace(actor.id))
    instance = type(lead)(context)
    info = instance.start()
    case.c.record_worker_started(actor.id, 1, info['session_id'], context.workspace, owner_receipt=info['owner_receipt'])
    case.boundaries.append((instance, context))
    replay = name + '-replay'
    capture(case, instance, context, replay, effect=effect, purpose='replay',
        explains={'experiment_id': effect_name, 'variable': None})
    case.review(name, actor, packet, evidence=[replay], contrary=['contrary'])
    require(case.c.state()['claims'][name]['state'] == 'independently_confirmed', 'composed capture review did not confirm fixture')


def transition(case, claim_id, effect, name):
    actor = case.worker(name + '-reviewer', 'reviewer', start=False)
    case.request('review_request', {'review_id': name, 'kind': 'escalation', 'subject_id': claim_id,
        'reviewer_id': actor.id, 'next_effect_id': effect})
    case.start(actor.id)
    state = case.c.state(); claim = state['claims'][claim_id]; review = state['reviews'][name]
    prior = state['reviews'][claim['review_id']]
    evidence = sorted({claim['effect'], claim['control'], *prior['result']['evidence_refs']})
    case.request('review_result', {'review_id': name, 'packet_sha256': review['packet_sha256'],
        'disposition': 'accept', 'checks': {key: True for key in
            ('measurement', 'permissions', 'causal_control', 'clean_replay', 'completeness')},
        'evidence_refs': evidence, 'contrary_refs': ['contrary'], 'reason': 'Bounded engineering fixture transition.'}, actor)


def initial_setup(path):
    with composed(path) as (case, instance, context):
        require({row['effect_id'] for row in case.c.state()['environment_operations'].values()} == {'read-source'},
            'setup selected a later rung')
        capture(case, instance, context, 'initial-capture')


def invalid_selectors(path):
    with composed(path, elevated=False, invalid=True) as (case, instance, context):
        for effect in ('missing', 'wrong-access', 'wrong-environment', 'account-effect', 'artifact-effect', '', 7, None):
            args = arguments(); args['effect_id'] = effect
            before = len(case.c.state()['dispatches'])
            response, value = invoke(instance, context, args)
            require(response.get('isError') and value['code'] == 'native_capture_effect_invalid', 'invalid effect selector was accepted')
            require(len(case.c.state()['dispatches']) == before, 'invalid effect reserved auxiliary work')
        capture(case, instance, context, 'explicit-execute', effect='execute-source')


def setup_refusal(path):
    for name, flags in [('elevated-only', {'no_initial': True}), ('ambiguous-initial', {'ambiguous': True})]:
        try:
            with composed(path / name, **flags):
                raise AssertionError('unsupported initial setup admitted')
        except Exception as error:
            require(getattr(error, 'code', None) == 'native_environment_capability_unavailable', 'unexpected setup refusal')


def without_review(path):
    with composed(path) as (case, instance, context):
        for effect in ('stored-source', 'cross_user-source'):
            before = len([row for row in case.c.state()['environment_operations'].values() if row['operation'] == 'execute'])
            result, value = invoke(instance, context, arguments(effect))
            require(result.get('isError') and value['code'] == 'effect_escalation_review_required', 'higher capture bypassed review')
            state = case.c.state()
            require(len([row for row in state['environment_operations'].values() if row['operation'] == 'execute']) == before,
                'rejected higher execution intent was recorded')
            require(state['dispatches'][value['dispatch_id']]['status'] == 'settled', 'refused higher capture left a reservation pending')


def full_chain(path):
    with composed(path) as (case, instance, context):
        case.publication('contrary')
        review_claim(case, instance, context, 'self-claim')
        transition(case, 'self-claim', 'stored-source', 'stored-transition')
        review_claim(case, instance, context, 'stored-claim', effect='stored-source')
        transition(case, 'stored-claim', 'cross_user-source', 'cross-transition')
        capture(case, instance, context, 'cross-capture', effect='cross_user-source')
        state = case.c.state()
        require(state['experiments']['stored-claim-effect']['effect_id'] == 'stored-source', 'stored predecessor was relabeled')
        require(state['experiments']['cross-capture']['effect_id'] == 'cross_user-source', 'final capture lost exact effect')


def application_selector(path):
    with receiver() as target, application.case(path, target) as case:
        args = arguments('read-anonymous'); args['conditions'] = {}; args['arguments'] = ['owner-a']
        before = len(case.controller.state()['dispatches'])
        with case.context.guard():
            operation = case.boundary.host_call('engagement_capture', args)
        response = operation.wait()
        require(response.get('isError') and application.value(response)['code'] == 'native_capture_effect_invalid',
            'application capture accepted a local effect selector')
        require(len(case.controller.state()['dispatches']) == before and not target.seen, 'invalid application selector reached target/admission')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scenario', default='all')
    args = parser.parse_args()
    checks = {'initial-setup': initial_setup, 'invalid-selectors': invalid_selectors, 'setup-refusal': setup_refusal,
        'without-review': without_review, 'full-chain': full_chain, 'application-selector': application_selector}
    report = {'classification': 'composed_source_capture_engineering_simulation', 'provider_calls': 0,
        'docker_calls': 0, 'ssh_calls': 0, 'external_target_calls': 0, 'scenarios': []}
    for name, check in checks.items():
        if args.scenario not in ('all', name):
            continue
        try:
            with tempfile.TemporaryDirectory(prefix='capture-effect-') as folder:
                check(Path(folder).resolve())
            report['scenarios'].append({'scenario': name, 'status': 'pass'})
        except Exception as error:
            report['scenarios'].append({'scenario': name, 'status': 'fail', 'error': getattr(error, 'code', str(error))})
    report['status'] = 'pass' if report['scenarios'] and all(row['status'] == 'pass' for row in report['scenarios']) else 'fail'
    names = ['tools/engagement_native_boundary.py', 'tools/engagement_controller.py', 'tools/engagement_evidence.py',
        'tools/engagement_runner.py', str(Path(__file__).relative_to(ROOT))]
    report['source_sha256'] = {name: digest((ROOT / name).read_bytes()) for name in names}
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    return report['status'] != 'pass'


if __name__ == '__main__':
    raise SystemExit(main())
