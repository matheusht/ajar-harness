#!/usr/bin/env python3
"""Journal E2E for startup, uncertain effects, continuous reviews and partial cleanup.

Uses signed disposable inputs and named simulated execution receipts, no providers.
Requires Python 3 and ssh-keygen. Run with --output FILE; expected all checks pass.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'tools'), str(Path(__file__).parent)]
from check_engagement_evidence_e2e import Case, require, refused
from engagement_contract import canonical, digest
from engagement_controller import Controller
from engagement_runner import Runner, WorkerContext


def startup(x):
    c = x.c
    grant = c.prepare_worker_dispatch('lead-1', 1, x.workspace('lead-1'),
        seconds=30, resources=[], adapter_id='fixture')
    owner = x.owner('lead-1')
    bridge = copy.deepcopy(owner)
    bridge['session_id'] = None
    bridge['bridge_process'] = bridge.pop('process')
    c.record_runtime_preparation_owner(grant, bridge)
    complete = dict(owner, bridge_process=bridge['bridge_process'])
    c.record_runtime_preparation_owner(grant, complete)
    c.record_runtime_preparation_owner(grant, complete)
    state = Controller(c.root).state()
    require(state['workers']['lead-1']['status'] == 'preparing', 'callback activated worker')
    receipts = state['dispatches'][grant['dispatch_id']]['runtime_owner_receipts']
    require(receipts == [digest(canonical(bridge)), digest(canonical(complete))], 'owner history lost or duplicated')
    require(all(c.read_object(sha) for sha in receipts), 'unfrozen owner')
    malformed = dict(complete, profile_sha256='sha256:' + 'f' * 64)
    refused('runtime_owner_invalid', lambda: c.record_runtime_preparation_owner(grant, malformed))
    c.record_worker_started('lead-1', 1, owner['session_id'], x.workspace('lead-1'), owner_receipt=complete)
    refused('worker_stale', lambda: c.record_runtime_preparation_owner(grant, bridge))


def unknown_effect(x):
    c = x.c
    grant = x.grant(resources=['source-main'])
    identity = x.observe(grant, 'observed-first', '4' * 32)
    common = {'kind': 'environment-observation-v2', 'operation': 'execute',
        'operation_id': 'unknown-second', 'identity': identity}
    c.record_environment_observation(grant, 'lab-main', dict(common, phase='intent',
        request_sha256=digest(b'unknown command')), effect_id='read-source')
    c.record_environment_observation(grant, 'lab-main', dict(common, phase='result',
        status='unknown'), effect_id='read-source')
    x.settle(grant)
    require(c.state()['resource_holds'].get('source-main') == [grant['dispatch_id']], 'terminal receipt erased uncertain effect')
    c.reconcile(grant['dispatch_id'], {'source-main': 'unchanged'}, adapter_id=grant['adapter_id'])
    require(c.state()['resource_holds'].get('source-main'), 'generic resource readback erased unknown operation')
    c.record_environment_observation(grant, 'lab-main', dict(common, phase='result', status='settled',
        returncode=0, output_sha256=digest(b'late readback')), effect_id='read-source')
    require(not c.state()['resource_holds'], 'exact late operation readback did not release hold')
    require(len(c.state()['environment_operations']['unknown-second']['receipts']) == 3, 'unknown history rewritten')


def continuous_review(x):
    c = x.c
    x.publication('contrary')
    x.request('strategy_challenge', {'obligation_id': 'challenge', 'kind': 'contradiction',
        'refs': ['contrary'], 'resources': ['source-main'], 'reason': 'Investigate the contrary evidence.'})
    grant = x.grant()
    for index in range(2):
        invocation = c.begin_invocation(grant)
        c.record_obligation_delivery('challenge', 'lead-1', 1,
            dispatch_id=grant['dispatch_id'], invocation_id=invocation)
        refused('checkpoint_unsettled', lambda: c.record_decision_checkpoint(grant, invocation_id=invocation))
        c.record_invocation_observed(grant, invocation, {'status': 'completed', 'usage': {'tokens': None, 'cost': None}})
        c.record_decision_checkpoint(grant, invocation_id=invocation)
        c.record_decision_checkpoint(grant, invocation_id=invocation)
        require(c.state()['obligations']['challenge']['opportunities'] == index + 1, 'duplicate or lost opportunity')
    require(c.state()['replacement_required'], 'completed turns did not trigger nonresponse')
    require(c.state()['dispatches'][grant['dispatch_id']]['status'] == 'pending', 'turn ended environment reservation')


def partial_cleanup(x):
    c = x.c
    grant = x.grant(resources=['source-main'])
    identity = x.observe(grant, 'before-stop', '7' * 32)
    owner = x.owner('lead-1')
    runtime = {'session_id': owner['session_id'], 'owner_receipt_sha256': digest(canonical(owner)),
        'process_exited': True, 'child_absence': 'verified', 'capabilities_revoked': True}
    class Boundary:
        environment_id = 'lab-main'
        def finish(self):
            return {'runtime': runtime, 'environment': {'status': 'stopped', 'running': False, 'identity': identity},
                'environment_cleanup': None, 'cleanup': 'unresolved', 'resources': {'source-main': 'unknown'}}
    runner = Runner(c, boundary_factory=lambda context: None)
    context = WorkerContext(runner, c.state()['workers']['lead-1'], grant, x.workspace('lead-1'))
    require(runner._settle(context, Boundary(), time.monotonic()) is False, 'cleanup falsely verified')
    state = Controller(c.root).state()
    require(state['workers']['lead-1']['status'] == 'stopped', 'valid stop lost')
    require(state['dispatches'][grant['dispatch_id']]['status'] == 'unknown', 'unknown receipt lost')
    require(state['usage']['reserved_worker_seconds'] == grant['seconds'], 'unknown reservation released')
    require(state['cleanup'] != 'verified', 'cleanup fabricated')


def checkpoint_alias(x):
    c = x.c
    x.publication('contrary')
    x.request('strategy_challenge', {'obligation_id': 'challenge', 'kind': 'contradiction',
        'refs': ['contrary'], 'resources': [], 'reason': 'Review this observation.'})
    grant = x.grant()
    c.record_obligation_delivery('challenge', 'lead-1', 1, dispatch_id=grant['dispatch_id'])
    invocation = c.begin_invocation(grant)
    refused('invocation_checkpoint_required', lambda: c.record_obligation_delivery(
        'challenge', 'lead-1', 1, dispatch_id=grant['dispatch_id']))
    c.record_obligation_delivery('challenge', 'lead-1', 1, dispatch_id=grant['dispatch_id'], invocation_id=invocation)
    c.record_invocation_observed(grant, invocation, {'status': 'completed', 'usage': {'tokens': None, 'cost': None}})
    c.record_decision_checkpoint(grant, invocation_id=invocation)
    receipt = c.store_receipt(grant, {'status': 'settled', 'worker_seconds': 1, 'resources': {},
        'usage': {'tokens': None, 'cost': None}, 'cleanup': 'verified'}, adapter_id=grant['adapter_id'])
    c.adopt_receipt(grant['dispatch_id'], receipt, adapter_id=grant['adapter_id'])
    refused('invocation_checkpoint_required', lambda: c.record_decision_checkpoint(grant))
    require(c.state()['obligations']['challenge']['opportunities'] == 1, 'one native turn counted twice')
    require(not c.state()['replacement_required'], 'one native turn forced replacement')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scenario', default='all')
    args = parser.parse_args()
    report = {'classification': 'engineering_simulation', 'provider_calls': 0,
        'research_acceptance': 'not_run', 'scenarios': []}
    for check in (startup, unknown_effect, continuous_review, partial_cleanup, checkpoint_alias):
        if args.scenario not in ('all', check.__name__):
            continue
        try:
            with tempfile.TemporaryDirectory(prefix='oslit-lifecycle-') as directory:
                check(Case(Path(directory).resolve(), start=check != startup))
            report['scenarios'].append({'scenario': check.__name__, 'status': 'pass'})
        except Exception as error:
            report['scenarios'].append({'scenario': check.__name__, 'status': 'fail',
                'error': type(error).__name__ + ': ' + str(error)})
    report['status'] = 'pass' if report['scenarios'] and all(row['status'] == 'pass' for row in report['scenarios']) else 'fail'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    return report['status'] != 'pass'


if __name__ == '__main__':
    raise SystemExit(main())
