#!/usr/bin/env python3
"""Signed workflow for unstarted cancellation and owned application captures.

Python 3 and ssh-keygen; protected boundary facts simulated explicitly. Run
--output FILE. All scenarios pass; no provider, Docker or external target.
"""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'tools'), str(Path(__file__).parent)]
from check_engagement_evidence_e2e import Case, require, refused
from check_engagement_network_journal_e2e import case as app_case, record, observation, result
from engagement_controller import Controller
from engagement_runner import Runner, WorkerContext
from engagement_network import NetworkGate


def preparation(path):
    x = Case(path, start=False)
    x.g = x.c.prepare_worker_dispatch('lead-1', 1, x.workspace('lead-1'), seconds=30,
                                     resources=['source-main'], adapter_id='fixture-adapter')
    return x


def cancel(x):
    return x.c.cancel_preparation(x.g, {'execution_admitted': False, 'cleanup': 'verified'})


def no_admission(path):
    x = preparation(path)
    x.c.revoke_worker('lead-1', 1, reason='fixture-startup-failure')
    cancel(x)
    cancel(x)
    state = Controller(x.c.root).state()
    require(state['workers']['lead-1']['status'] == 'stopped', 'unstarted worker held')
    require(state['dispatches'][x.g['dispatch_id']]['status'] == 'settled', 'unused reservation not settled')
    require(state['usage']['reserved_worker_seconds'] == state['usage']['invocations'] == 0, 'unused allowance not released')
    require(not state['resource_holds'], 'unadmitted effect held')
    require(state['workers']['lead-1']['session_id'] is None, 'fabricated native session')
    x.c.resume_worker('lead-1', 1, reason='controller_resume')
    require(x.c.state()['workers']['lead-1']['generation'] == 2, 'preflight fix cannot resume')


def cancellation_fences(path):
    x = preparation(path)
    for readback in ({'execution_admitted': True, 'cleanup': 'verified'},
                     {'execution_admitted': False, 'cleanup': 'unresolved'}, {}):
        refused('preparation_cancellation_invalid', lambda: x.c.cancel_preparation(x.g, readback))
    owner = x.owner('lead-1')
    x.c.record_runtime_preparation_owner(x.g, owner)
    refused('preparation_already_admitted', lambda: cancel(x))
    require(x.c.state()['dispatches'][x.g['dispatch_id']]['status'] == 'pending', 'live owner allowance freed')


def environment_fence(path):
    x = preparation(path)
    x.observe(x.g, 'started-environment', '5' * 32)
    refused('preparation_already_admitted', lambda: cancel(x))


def runner_cancel(path):
    x = preparation(path)
    class Boundary:
        runtime = None
        def finish(self):
            return {'execution_admitted': False, 'cleanup': 'verified'}
    runner = Runner(x.c, boundary_factory=lambda ctx: Boundary())
    context = WorkerContext(runner, x.c.state()['workers']['lead-1'], x.g, x.workspace('lead-1'))
    require(runner._settle(context, Boundary(), time.monotonic()), 'runner did not cancel unstarted reservation')
    require(x.c.state()['workers']['lead-1']['status'] == 'stopped', 'runner fabricated runtime stop')


def settle_aux(x, grant, resources):
    receipt = x.c.store_receipt(grant, {'status': 'settled', 'worker_seconds': 1,
        'resources': resources, 'usage': {'tokens': None, 'cost': None}, 'cleanup': 'verified'}, adapter_id=grant['adapter_id'])
    return x.c.adopt_receipt(grant['dispatch_id'], receipt, adapter_id=grant['adapter_id'])


def application_capture(path):
    x = app_case(path)
    child = x.c.prepare_capture_dispatch(x.g, seconds=10, resources=['app-main'])
    refused('capture_in_progress', lambda: x.c.prepare_capture_dispatch(x.g, seconds=10, resources=['app-main']))
    settle_aux(x, child, {'app-main': 'retained'})
    require(x.c.authorize_dispatch(x.g), 'successful auxiliary capture revoked parent')
    require(not x.c.state()['resource_holds'], 'retained ownership incorrectly marked reset/unknown')
    x.settle(x.g, unknown=True)
    require(x.c.state()['resource_holds'].get('app-main'), 'parent uncertainty lost retained app')


def retention_fences(path):
    x = app_case(path)
    refused('receipt_retention_invalid', lambda: settle_aux(x, x.g, {'app-main': 'retained', 'app-other': 'retained'}))
    child = x.c.prepare_capture_dispatch(x.g, seconds=10, resources=['app-main'])
    x.c.revoke_worker('lead-1', 1, reason='fixture')
    refused('receipt_retention_invalid', lambda: settle_aux(x, child, {'app-main': 'retained'}))
    settle_aux(x, child, {'app-main': 'unknown'})
    require(x.c.state()['resource_holds'].get('app-main'), 'revoked capture lost target hold')


def request_provenance(path, *, unknown=False):
    x = app_case(path)
    x.instrument()
    child = x.c.prepare_capture_dispatch(x.g, seconds=10, resources=['app-main'])
    nonce = '6' * 32
    x.observe(child, 'captured-execution', nonce)
    row = observation('captured-request')
    record(x, row, child, nonce)
    record(x, result(row, status='unknown' if unknown else 'settled'), child, nonce)
    candidate, probe = x.c.store_object(b'candidate'), x.c.store_object(b'probe')
    instrument = x.c.state()['instruments']['instrument-1']
    measurement = {
        'instrument_id': 'instrument-1', 'instrument_sha256': instrument['artifact_sha256'],
        'candidate_sha256': candidate, 'probe_sha256': probe, 'conditions': {},
        'reset': instrument['reset'], 'clean_start': False}
    if not unknown:
        refused('experiment_reset_unverified', lambda: x.c.record_experiment_execution(
            child, 'lab-main', 'captured-execution', dict(measurement, clean_start=True)))
    x.c.record_experiment_execution(child, 'lab-main', 'captured-execution', measurement)
    settle_aux(x, child, {'app-main': 'unknown' if unknown else 'retained'})
    payload = {'experiment_id': 'app-experiment', 'instrument_id': 'instrument-1',
        'candidate_sha256': candidate, 'probe_sha256': probe, 'operation_id': 'captured-execution',
        'purpose': 'exploration', 'conditions': {}, 'score': None, 'resources': ['app-main'],
        'explains': None, 'supersedes': []}
    if unknown:
        refused('experiment_network_unsettled', lambda: x.request('experiment_record', payload))
        return
    x.request('experiment_record', payload)
    experiment = x.c.state()['experiments']['app-experiment']
    require(experiment.get('network_operations') == ['captured-request'], 'protected request provenance omitted')
    require(experiment.get('target_bindings') == [{key: row[key] for key in
            ('access_id', 'effect_id', 'account_ref', 'origin', 'method')}], 'actual principal binding omitted')
    require(experiment['clean_start'] is False, 'local clean lab invented remote reset')


def unknown_request(path):
    request_provenance(path, unknown=True)


def renewal_publication(path):
    x = Case(path)
    grant = x.grant()
    runner = Runner(x.c, boundary_factory=lambda ctx: None)
    context = WorkerContext(runner, x.c.state()['workers']['lead-1'], grant, x.workspace('lead-1'))
    advanced, release, watched = threading.Event(), threading.Event(), threading.Event()
    original = x.c.renew_dispatch
    def delayed(grant, *, seconds):
        renewed = original(grant, seconds=seconds)
        advanced.set()
        require(release.wait(5), 'renewal barrier timed out')
        return renewed
    x.c.renew_dispatch = delayed
    def active():
        if advanced.is_set():
            watched.set()
        try:
            context.authorize()
            return True
        except Exception:
            return False
    gate = NetworkGate([], active, dispatch_guard=context.guard)
    prepared_guard = context.guard()
    results = []
    def guarded():
        try:
            with prepared_guard:
                results.append('guarded')
        except Exception as error:
            results.append(getattr(error, 'code', str(error)))
    def renew():
        if hasattr(context, 'renew'):
            context.renew(30)
        else:
            context.grant = x.c.renew_dispatch(context.grant, seconds=30)
    renewal = threading.Thread(target=renew)
    guard_thread = threading.Thread(target=guarded)
    try:
        renewal.start()
        require(advanced.wait(2), 'journal did not renew')
        guard_thread.start()
        require(watched.wait(2), 'actual gateway watcher did not inspect renewal')
        time.sleep(.1)
    finally:
        release.set()
        renewal.join(3)
        if guard_thread.ident is not None:
            guard_thread.join(3)
        still_open = not gate.closed.is_set()
        gate.close()
    require(still_open and results == ['guarded'], 'gateway or prepared guard observed stale grant: ' + str(results))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = {'classification': 'engineering_simulation', 'provider_calls': 0, 'scenarios': []}
    for check in (no_admission, cancellation_fences, environment_fence, runner_cancel, application_capture,
                  retention_fences, request_provenance, unknown_request, renewal_publication):
        try:
            with tempfile.TemporaryDirectory(prefix='oslit-admission-') as folder:
                check(Path(folder).resolve())
            report['scenarios'].append({'scenario': check.__name__, 'status': 'pass'})
        except Exception as error:
            report['scenarios'].append({'scenario': check.__name__, 'status': 'fail', 'error': str(error)})
    report['status'] = 'pass' if all(row['status'] == 'pass' for row in report['scenarios']) else 'fail'
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    return report['status'] != 'pass'


if __name__ == '__main__':
    raise SystemExit(main())
