#!/usr/bin/env python3
"""Run the coordinator against real journal/CLI and explicit simulated boundaries.

This proves orchestration and recovery, not model behavior or lab containment.
Run with --output FILE; no provider, Docker daemon, or research target is used.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))


def require(value, message):
    if not value:
        raise AssertionError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', default='all')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = {'kind': 'engagement-runner-check-v2', 'classification': 'engineering_simulation',
              'provider_calls': 0, 'research_acceptance': 'not_run', 'scenarios': []}
    scenarios = ('single-owner', 'native-continuation', 'direction-stop', 'recovery',
                 'frozen-contract', 'unavailable-boundary', 'private-source-parallel',
                 'renewal', 'invocation-accounting', 'task-finish', 'receipt-double-count',
                 'renewal-boundary', 'capture-admission', 'native-prerequisite-code',
                 'environment-prerequisite-code', 'unexpected-private-error',
                 'review-finish-accept', 'review-finish-reopen', 'review-unexpected-failure')
    for scenario in scenarios:
        if args.scenario not in ('all', scenario):
            continue
        try:
            from engagement_runner import Runner, RunnerError, frozen_inputs
            from engagement_controller import Controller, ControllerError, Principal
            from engagement_contract import canonical, digest, load_inputs
            spec = importlib.util.spec_from_file_location('runner_fixture',
                Path(__file__).with_name('check_engagement_contract_e2e.py'))
            fixture = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(fixture)
            with tempfile.TemporaryDirectory(prefix='oslit-runner-') as temporary:
                directory = Path(temporary).resolve()
                inputs = fixture.make_fixture(directory / 'input')
                c = Controller.initialize(directory / 'engagement', load_inputs(inputs),
                                          evidence_class='engineering_simulation')
                calls, peers = [], []
                now = datetime.now(timezone.utc)

                class Peer:
                    def __init__(self, context):
                        self.context = context
                        self.session_id = 'session-' + uuid.uuid4().hex
                        self.active, self.usage, self.events = False, None, []
                        self.prompts, self.directions = [], []
                        self.closed = False
                        self.count = 0
                        self.runtime = self
                        self.identity = None
                        peers.append(self)

                    def start(self):
                        if scenario == 'native-prerequisite-code':
                            from native_runtime_transport import RuntimeError as NativeFailure
                            raise NativeFailure('native_bundle_platform_mismatch')
                        if scenario == 'environment-prerequisite-code':
                            from research_environment import EnvironmentUnavailable
                            raise EnvironmentUnavailable('environment_grant_inactive')
                        if scenario == 'unexpected-private-error':
                            raise ValueError('private-exception-content')
                        calls.append(('start', self.context.worker['id']))
                        return {'session_id': self.session_id, 'owner_receipt': self.owner_receipt()}

                    def owner_receipt(self):
                        return {'kind': 'native-runtime-owner-v1', 'runtime': 'codex',
                            'session_id': self.session_id,
                            'profile_sha256': self.context.assignment['profile_sha256'],
                            'boundary': 'darwin-no-fork-v1',
                            'process': {'pid': 34567, 'pgid': 34567, 'uid': 501,
                                        'started_seconds': 1, 'started_microseconds': 2}}

                    def invoke(self, prompt, invocation_id):
                        require(not self.closed, 'dispatch after close')
                        self.context.authorize()
                        self.prompts.append(prompt)
                        self.count += 1
                        self.active = True
                        self.usage = {'input_tokens': 2, 'output_tokens': 3,
                                      'total_tokens': 5, 'estimated_cost': None,
                                      'monetary_spend': None, 'provider_requests': None}
                        calls.append(('invoke', invocation_id))
                        self.events = [{'event': 'completed', 'status': 'completed'}]
                        if scenario == 'task-finish' and self.count == 1:
                            request = {'request_id': 'finish-1', 'expected_revision': c.state()['revision'],
                                'type': 'task_result', 'payload': {'task_id': 'task-1', 'generation': 1,
                                    'disposition': 'completed', 'result': 'Inspected fixture.', 'evidence_refs': []}}
                            result = self.context.submit(request)
                            require(result['status'] == 'accepted', 'finish intent not accepted')
                        return {'invocation_id': invocation_id, 'session_id': self.session_id}

                    def observe(self, timeout_seconds=0):
                        if scenario.startswith('review-') and self.active:
                            if scenario == 'review-unexpected-failure':
                                raise ControllerError('assignment_required')
                            from engagement_evidence import CHECKS
                            review = c.state()['reviews']['review-dry']
                            if review['status'] == 'pending':
                                result = self.context.submit({'request_id': 'review-result',
                                    'expected_revision': c.state()['revision'], 'type': 'review_result',
                                    'payload': {'review_id': 'review-dry', 'packet_sha256': review['packet_sha256'],
                                        'disposition': scenario.removeprefix('review-finish-'),
                                        'checks': dict.fromkeys(CHECKS, True), 'evidence_refs': [],
                                        'contrary_refs': [], 'reason': 'Bounded harmless fixture review.'}})
                                require(result['status'] == 'accepted', 'review result rejected')
                                try:
                                    self.context.authorize()
                                    raise AssertionError('completed reviewer retained tool authority')
                                except ControllerError as error:
                                    require(error.code == 'assignment_required', error.code)
                                return []  # The decision precedes the native turn's final event.
                        if scenario == 'direction-stop' and not self.directions:
                            time.sleep(min(timeout_seconds, .02))
                            return []
                        events, self.events = self.events, []
                        if events:
                            self.active = False
                        if scenario in ('native-continuation', 'frozen-contract') and self.count == 2:
                            c.stop('fixture_done')
                        elif scenario == 'direction-stop' and self.directions:
                            c.stop('fixture_done')
                        return events

                    def steer(self, message):
                        self.context.authorize()
                        self.directions.append(message)
                        return {'delivered': True}

                    def renew(self, seconds=None):
                        self.context.authorize()
                        calls.append(('renew', seconds))

                    def finish(self):
                        self.closed = True
                        self.active = False
                        calls.append(('close', self.session_id))
                        if scenario in ('native-prerequisite-code', 'environment-prerequisite-code', 'unexpected-private-error'):
                            return {'execution_admitted': False, 'cleanup': 'verified'}
                        return {'runtime': {'session_id': self.session_id,
                            'owner_receipt_sha256': digest(canonical(self.owner_receipt())),
                            'process_exited': True, 'child_absence': 'verified', 'capabilities_revoked': True},
                            'environment': None, 'cleanup': 'verified',
                            'resources': {name: 'reset' for name in self.context.grant['resources']}}

                def run_thread(runner):
                    result = []
                    def work():
                        try:
                            result.append(runner.run())
                        except BaseException as error:
                            result.append(error)
                    thread = threading.Thread(target=work, daemon=True)
                    thread.start()
                    return thread, result

                def join(thread, result):
                    thread.join(8)
                    if thread.is_alive():
                        c.stop('fixture_timeout')
                        thread.join(3)
                    require(not thread.is_alive(), 'coordinator did not stop')
                    require(bool(result) and isinstance(result[0], dict), repr(result))
                    return result[0]

                runner = Runner(c, boundary_factory=Peer)
                if scenario in ('native-prerequisite-code', 'environment-prerequisite-code', 'unexpected-private-error'):
                    result = runner.run()
                    expected = {'native-prerequisite-code': 'native_bundle_platform_mismatch',
                        'environment-prerequisite-code': 'environment_grant_inactive',
                        'unexpected-private-error': 'native_worker_unavailable'}[scenario]
                    require(result['failures'] == {'lead-1': expected}, 'specific safe blocker lost or private error exposed')
                    require(result['cleanup'] == 'verified' and c.state()['usage']['invocations'] == 0,
                            'prerequisite refusal fabricated an invocation or cleanup')
                    require('private-exception-content' not in json.dumps(result), 'private exception leaked')
                elif scenario == 'single-owner':
                    with runner.ownership():
                        try:
                            with Runner(c, boundary_factory=Peer).ownership():
                                raise AssertionError('two owners admitted')
                        except RunnerError as error:
                            require(error.code == 'engagement_already_running', error.code)
                    with Runner(c, boundary_factory=Peer).ownership():
                        pass
                elif scenario in ('native-continuation', 'frozen-contract'):
                    if scenario == 'frozen-contract':
                        Path(json.loads(inputs.read_text())['goal_file']).write_text('MUTATED ORIGINAL GOAL')
                    result = runner.run()
                    require(len(peers) == 1 and peers[0].count == 2, 'native context recreated between turns')
                    require(len({row[1] for row in calls if row[0] == 'invoke'}) == 2, 'invocation ID repeated')
                    require('harmless fixture' in peers[0].prompts[0], 'frozen goal missing')
                    require('MUTATED ORIGINAL GOAL' not in peers[0].prompts[0], 'unfrozen goal used')
                    require(result['status'] == 'stopped' and peers[0].closed, 'stop/cleanup missing')
                    require(c.state()['usage']['invocations'] == 2, 'actual invocation count lost')
                    require(c.state()['usage']['tokens']['total'] == 10, 'native usage double-counted or lost')
                    output = directory / 'export'
                    process = subprocess.run([sys.executable, str(ROOT / 'tools/native_engagement.py'),
                        'export', '--engagement-root', str(c.root), '--output', str(output)],
                        capture_output=True, text=True, timeout=10)
                    require(process.returncode == 0, process.stdout)
                elif scenario == 'direction-stop':
                    thread, result = run_thread(runner)
                    until = time.monotonic() + 4
                    while not peers and time.monotonic() < until:
                        time.sleep(.01)
                    c.direction('Use the published contrary observation before the next experiment.')
                    join(thread, result)
                    require(peers[0].directions and peers[0].closed, 'direction or stop lost')
                    require(peers[0].count == 1, 'new invocation after stop')
                elif scenario == 'unavailable-boundary':
                    def unavailable(context):
                        raise RunnerError('fixture_environment_unavailable')
                    result = Runner(c, boundary_factory=unavailable).run()
                    require(result['status'] == 'blocked', 'unavailable environment passed')
                    require(not peers and not calls, 'fallback runtime dispatched')
                elif scenario == 'recovery':
                    workspace = directory / 'old-workspace'
                    workspace.mkdir(mode=0o700)
                    grant = c.prepare_worker_dispatch('lead-1', 1, workspace,
                        seconds=30, resources=[], adapter_id='native-runner')
                    recovery_calls = []
                    def recovery(context, dispatch):
                        recovery_calls.append(dispatch['dispatch_id'])
                        return {'status': 'unknown', 'cleanup': 'unresolved'}
                    result = Runner(c, boundary_factory=Peer, recovery=recovery).run()
                    require(recovery_calls == [grant['dispatch_id']], 'pending dispatch not reconciled first')
                    require(result['status'] == 'blocked' and not peers, 'unknown effect replayed')
                    require(c.state()['usage']['reserved_worker_seconds'] == 30, 'unknown allowance reset')
                else:
                    workspace = directory / 'workspace'
                    workspace.mkdir(mode=0o700)
                    grant = c.prepare_worker_dispatch('lead-1', 1, workspace, seconds=30,
                        resources=['source-main'], adapter_id='native-runner')
                    c.record_worker_started('lead-1', 1, 'session-one', workspace)
                    lead = Principal('worker', 'lead-1', 1)
                    serial = 0
                    def submit(kind, payload):
                        nonlocal serial
                        serial += 1
                        return c.submit(lead, {'request_id': str(serial), 'expected_revision': c.state()['revision'],
                                             'type': kind, 'payload': payload})
                    if scenario.startswith('review-'):
                        submit('closure_request', {'closure_id': 'dry', 'outcome': 'covered_dry',
                            'claim_ids': [], 'remaining': [], 'reason': 'Bounded harmless fixture.'})
                        submit('worker_request', {'worker_id': 'reviewer-1', 'role': 'reviewer',
                            'profile_id': 'runtime-main', 'question': 'Review the bounded fixture.'})
                        submit('review_request', {'review_id': 'review-dry', 'kind': 'closure',
                            'subject_id': 'dry', 'reviewer_id': 'reviewer-1'})
                        runner._work(c.state()['workers']['reviewer-1'])
                        expected = {'reviewer-1': 'assignment_required'} if scenario == 'review-unexpected-failure' else {}
                        require(runner.failures == expected, 'review completion misclassified: ' + repr(runner.failures))
                        require(peers[-1].closed and peers[-1].count == 1, 'reviewer continued or escaped cleanup')
                        dispatch = next(row for row in c.state()['dispatches'].values() if row['worker_id'] == 'reviewer-1')
                        require(dispatch['status'] == 'settled', 'review dispatch not settled')
                        require(all(c.state()['invocations'][name]['status'] != 'pending'
                                    for name in dispatch['invocations']), 'review invocation left pending')
                    elif scenario == 'renewal':
                        c.clock = lambda: now + timedelta(seconds=15)
                        renewed = c.renew_dispatch(grant, seconds=30)
                        require(renewed['seconds'] > grant['seconds'], 'renewal reset reservation')
                        require(c.state()['usage']['reserved_worker_seconds'] == renewed['seconds'], 'renewal not reserved')
                        try:
                            c.authorize_dispatch(grant)
                            raise AssertionError('stale grant authorized new work')
                        except ControllerError:
                            pass
                        require(c.authorize_dispatch(renewed), 'latest grant rejected')
                    elif scenario == 'invocation-accounting':
                        first = c.begin_invocation(grant)
                        c.record_invocation_observed(grant, first, {'status': 'completed',
                            'usage': {'tokens': {'input': 2, 'output': 3, 'total': 5}, 'cost': None}})
                        c.record_invocation_observed(grant, first, {'status': 'completed',
                            'usage': {'tokens': {'input': 2, 'output': 3, 'total': 5}, 'cost': None}})
                        second = c.begin_invocation(grant)
                        require(first != second and c.state()['usage']['invocations'] == 2, 'invocation allowance bypass')
                        require(c.state()['usage']['tokens']['total'] == 5, 'duplicate usage charged')
                    elif scenario == 'receipt-double-count':
                        invocation = c.begin_invocation(grant)
                        c.record_invocation_observed(grant, invocation, {'status': 'completed',
                            'usage': {'tokens': {'total': 5}, 'cost': .25}})
                        document = {'status': 'settled', 'worker_seconds': 1,
                            'resources': {'source-main': 'reset'},
                            'usage': {'tokens': {'total': 5}, 'cost': .25}, 'cleanup': 'verified'}
                        receipt = c.store_receipt(grant, document, adapter_id=grant['adapter_id'])
                        try:
                            c.adopt_receipt(grant['dispatch_id'], receipt, adapter_id=grant['adapter_id'])
                            raise AssertionError('managed receipt duplicated native usage')
                        except ControllerError as error:
                            require(error.code == 'receipt_usage_already_recorded', error.code)
                        require(c.state()['usage']['tokens']['total'] == 5, 'usage changed on refused receipt')
                        require(c.state()['usage']['known_estimated_cost'] == .25, 'estimated cost lost')
                    elif scenario == 'renewal-boundary':
                        c.clock = lambda: now + timedelta(seconds=15)
                        renewed = c.renew_dispatch(grant, seconds=30)
                        revision = c.state()['revision']
                        for invalid in (True, 0, 61):
                            try:
                                c.renew_dispatch(renewed, seconds=invalid)
                                raise AssertionError('invalid renewal admitted')
                            except ControllerError:
                                pass
                        require(c.state()['revision'] == revision, 'invalid renewal mutated journal')
                        c.clock = lambda: now + timedelta(days=2)
                        try:
                            c.renew_dispatch(renewed, seconds=30)
                            raise AssertionError('expired lease resurrected')
                        except ControllerError as error:
                            require(error.code == 'lease_expired', error.code)
                    elif scenario == 'capture-admission':
                        auxiliary = c.prepare_capture_dispatch(grant, seconds=10, resources=['source-main'])
                        require(auxiliary['dispatch_id'] != grant['dispatch_id'], 'capture reused parent reservation')
                        require(c.state()['usage']['reserved_worker_seconds'] == 40, 'capture capacity not reserved')
                        require(c.state()['usage']['invocations'] == 1, 'capture fabricated a native invocation')
                        try:
                            c.prepare_capture_dispatch(grant, seconds=10, resources=['source-main'])
                            raise AssertionError('second simultaneous capture admitted')
                        except ControllerError as error:
                            require(error.code == 'capture_in_progress', error.code)
                        c.stop('fixture_stop')
                        for active_grant in (grant, auxiliary):
                            try:
                                c.authorize_dispatch(active_grant)
                                raise AssertionError('capture retained authority after stop')
                            except ControllerError:
                                pass
                    elif scenario == 'private-source-parallel':
                        submit('worker_request', {'worker_id': 'worker-2', 'role': 'specialist',
                            'profile_id': 'runtime-main', 'question': 'Inspect another private copy.'})
                        submit('task_create', {'task_id': 'task-2', 'question': 'Inspect copy.', 'priority': 1,
                            'resources': ['source-main'], 'prerequisites': [], 'evidence_refs': []})
                        submit('task_assign', {'task_id': 'task-2', 'worker_id': 'worker-2'})
                        other = directory / 'other-workspace'; other.mkdir(mode=0o700)
                        second = c.prepare_worker_dispatch('worker-2', 1, other, seconds=30,
                            resources=['source-main'], adapter_id='native-runner')
                        require(c.authorize_dispatch(grant) and c.authorize_dispatch(second), 'private copies serialized')
                    elif scenario == 'task-finish':
                        # Use a pending worker and a real assignment for the coordinator.
                        c.stop('end_unused_fixture')
                        inputs2 = fixture.make_fixture(directory / 'input-2')
                        c = Controller.initialize(directory / 'engagement-2', load_inputs(inputs2),
                                                  evidence_class='engineering_simulation')
                        w = directory / 'setup-workspace'; w.mkdir(mode=0o700)
                        c.record_worker_started('lead-1', 1, 'setup-session', w)
                        submit('worker_request', {'worker_id': 'worker-2', 'role': 'specialist',
                            'profile_id': 'runtime-main', 'question': 'Inspect assigned copy.'})
                        submit('task_create', {'task_id': 'task-1', 'question': 'Inspect copy.', 'priority': 1,
                            'resources': [], 'prerequisites': [], 'evidence_refs': []})
                        submit('task_assign', {'task_id': 'task-1', 'worker_id': 'worker-2'})
                        c.revoke_worker('lead-1', 1, reason='fixture_has_no_lead_runtime')
                        result = Runner(c, boundary_factory=Peer).run()
                        require(c.state()['tasks']['task-1']['status'] == 'completed', 'outcome lost during quiesce')
                        require(peers[-1].closed, 'task completed before worker stopped')
                report['scenarios'].append({'name': scenario, 'status': 'pass'})
        except Exception as error:
            report['scenarios'].append({'name': scenario, 'status': 'fail',
                                       'error': type(error).__name__ + ': ' + str(error)[:300]})
    report['status'] = 'pass' if report['scenarios'] and all(row['status'] == 'pass' for row in report['scenarios']) else 'fail'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    print(json.dumps(report, sort_keys=True))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
