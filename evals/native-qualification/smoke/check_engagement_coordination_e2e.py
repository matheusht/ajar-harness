#!/usr/bin/env python3
"""Complete team coordination with real journal/CLI and named simulated native peers.

Requires Python 3 and ssh-keygen. No provider, Docker daemon or target is used.
Run --output FILE; expected reviewed closure, two assigned tasks, replacement after
exactly two opportunities, and reconstruction without allowance reset.
"""
from __future__ import annotations

import argparse
from datetime import timedelta
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'tools'), str(Path(__file__).parent)]
from check_engagement_evidence_e2e import Case, require, fixture
from engagement_contract import canonical, digest, load_inputs
from engagement_controller import Controller, ControllerError, instant
from engagement_runner import Runner, RunnerError, WorkerContext


def check(path, scenario):
    x = Case(path, start=False)
    c = x.c
    if scenario in ('prompt-budget', 'prompt-wire'):
        goal = Path(json.loads(x.inputs.read_bytes())['goal_file'])
        goal.write_text('G' * 196608)
        scope = fixture.fixture_scope(x.inputs)
        scope['goal_sha256'] = digest(goal.read_bytes())
        fixture.resign_fixture(x.inputs, scope)
        x.contract = load_inputs(x.inputs)
        c = x.c = Controller.initialize(path / 'large-goal-engagement', x.contract, evidence_class='engineering_simulation')
        x.start('lead-1')
        for index in range(3 if scenario == 'prompt-wire' else 2):
            x.request('publish', {'publication_id': 'large-' + str(index), 'kind': 'observation',
                'subject': 'Multilingual fixture', 'body': ('é' if scenario == 'prompt-wire' else '漢') * 65536,
                'refs': [], 'supersedes': [], 'artifacts': []})
        runner = Runner(c, boundary_factory=lambda context: None)
        grant = x.grant()
        invocation = c.begin_invocation(grant)
        context = WorkerContext(runner, c.state()['workers']['lead-1'], grant, x.workspace('lead-1'))
        prompt = runner._prompt(context, True, invocation)
        from native_runtime_transport import Session, Transport, MAX_FRAME
        session = Session()
        session.active, session.calls, session.tool_replies = False, {}, []
        session.session_id, session.invocations = 'fixture-prompt', set()
        session._begin(invocation, prompt)
        require(len(prompt.encode()) <= MAX_FRAME // 2, 'total native prompt exceeded adapter limit')
        require(c.state()['workers']['lead-1']['cursor'] is None, 'prompt truncation acknowledged unread updates')
        require('/input/bootstrap/goal.md' in prompt, 'large goal lacks complete frozen file pointer')
        peer = ('import sys,json\nfor line in sys.stdin:\n request=json.loads(line); '
            'print(json.dumps({"jsonrpc":"2.0","id":request["id"],"result":'
            '{"received_bytes":len(request["params"]["input"][0]["text"].encode())}}),flush=True)')
        transport = Transport([sys.executable, '-c', peer], {}, str(path), lambda event: None)
        try:
            reply = transport.request('turn/start', {'threadId': 'fixture-prompt', 'model': 'fixture',
                'input': [{'type': 'text', 'text': prompt}]})
            require(reply['received_bytes'] == len(prompt.encode()), 'native wire changed or lost prompt bytes')
        finally:
            transport.close()
        return {'scenario': scenario, 'status': 'pass', 'prompt_bytes': len(prompt.encode())}
    if scenario == 'capture-parent-lease':
        grant = c.prepare_worker_dispatch('lead-1', 1, x.workspace('lead-1'), seconds=30,
            resources=['source-main'], adapter_id='fixture')
        owner = x.owner('lead-1')
        c.record_worker_started('lead-1', 1, owner['session_id'], x.workspace('lead-1'), owner_receipt=owner)
        auxiliary = c.prepare_capture_dispatch(grant, seconds=5, resources=['source-main'])
        c.clock = lambda: instant(auxiliary['lease_expires_at']) - timedelta(seconds=1)
        renewed = c.renew_dispatch(auxiliary, seconds=30)
        require(instant(renewed['lease_expires_at']) <= instant(grant['lease_expires_at']), 'capture lease outlived parent authority')
        return {'scenario': scenario, 'status': 'pass'}
    peers, starts, endings = [], [], []
    entered, finish_entered, finish_release = threading.Event(), threading.Event(), threading.Event()
    request_serial = 0

    def submit(context, kind, payload):
        nonlocal request_serial
        request_serial += 1
        for _ in range(50):
            try:
                return context.submit({'request_id': f'coord-{context.worker["id"]}-{request_serial}',
                    'expected_revision': c.state()['revision'], 'type': kind, 'payload': payload})
            except ControllerError as error:
                if error.code != 'revision_conflict':
                    raise
        raise AssertionError('revision conflict did not settle')

    def worker(context, name, role):
        return submit(context, 'worker_request', {'worker_id': name, 'role': role,
            'profile_id': 'runtime-main', 'question': 'Inspect the harmless fixture.'})

    class Peer:
        def __init__(self, context):
            self.context = context
            self.runtime = self
            self.session_id = 'native-' + uuid.uuid4().hex
            self.active, self.usage, self.events = False, None, []
            self.count = 0
            self.prompts = []
            peers.append(self)

        def owner(self):
            return dict(x.owner(self.context.worker['id']), session_id=self.session_id)

        def start(self):
            if c.state()['cleanup'] == 'verified':
                raise RunnerError('new_work_inherited_verified_cleanup')
            starts.append((self.context.worker['id'], self.context.worker['generation']))
            return {'session_id': self.session_id, 'owner_receipt': self.owner()}

        def invoke(self, prompt, invocation):
            self.context.authorize()
            self.count += 1
            self.prompts.append(prompt)
            self.active = True
            self.usage = {'input_tokens': 2, 'output_tokens': 3, 'total_tokens': 5}
            self.events = [{'event': 'completed', 'status': 'completed'}]
            role = self.context.worker['role']
            generation = self.context.worker['generation']
            if scenario in ('reviewed-closure', 'stale-closure'):
                if role == 'lead' and self.count == 1:
                    submit(self.context, 'closure_request', {'closure_id': 'dry', 'outcome': 'covered_dry',
                        'claim_ids': [], 'remaining': [], 'reason': 'Only the harmless fixture was inspected.'})
                    worker(self.context, 'reviewer-1', 'reviewer')
                    submit(self.context, 'review_request', {'review_id': 'review-dry', 'kind': 'closure',
                        'subject_id': 'dry', 'reviewer_id': 'reviewer-1'})
                elif role == 'reviewer':
                    with c.lock():
                        review = c.state()['reviews']['review-dry']
                        submit(self.context, 'review_result', {'review_id': 'review-dry',
                            'packet_sha256': review['packet_sha256'], 'disposition': 'accept',
                            'checks': dict.fromkeys(('measurement', 'permissions', 'causal_control', 'clean_replay', 'completeness'), True),
                            'evidence_refs': [], 'contrary_refs': [], 'reason': 'The bounded negative and limits match the fixture.'})
                        if scenario == 'stale-closure':
                            submit(self.context, 'task_create', {'task_id': 'late-followup', 'question': 'Inspect the new lead.',
                                'priority': 0, 'resources': [], 'prerequisites': [], 'evidence_refs': []})
                elif scenario == 'stale-closure' and 'late-followup' in c.state()['tasks']:
                    time.sleep(.4)
                    require(c.state()['status'] == 'active', 'new research work did not keep engagement active')
                    c.stop('fixture_complete')
            elif scenario == 'specialist-next-task':
                if role == 'lead' and self.count == 1:
                    worker(self.context, 'specialist-1', 'specialist')
                    for index in range(2):
                        submit(self.context, 'task_create', {'task_id': f'task-{index}', 'question': 'Inspect fixture.',
                            'priority': 2-index, 'resources': ['source-main'], 'prerequisites': [], 'evidence_refs': []})
                elif role == 'specialist':
                    assignment = c.state()['workers'][self.context.worker['id']]['assignment']
                    submit(self.context, 'task_result', {'task_id': assignment['task_id'],
                        'generation': assignment['generation'], 'disposition': 'completed',
                        'result': 'Inspected the assigned fixture.', 'evidence_refs': []})
                if role == 'lead' and c.state()['tasks'] and all(row['status'] == 'completed' for row in c.state()['tasks'].values()):
                    c.stop('fixture_complete')
            elif scenario == 'review-replacement':
                if generation == 1 and self.count == 1:
                    submit(self.context, 'publish', {'publication_id': 'contrary', 'kind': 'observation',
                        'subject': 'Contrary observation', 'body': 'The fixture contradicts the prior explanation.',
                        'refs': [], 'supersedes': [], 'artifacts': []})
                    submit(self.context, 'strategy_challenge', {'obligation_id': 'challenge', 'kind': 'contradiction',
                        'refs': ['contrary'], 'resources': ['source-main'], 'reason': 'Respond to the contrary observation.'})
                elif generation >= 3:
                    submit(self.context, 'review_response', {'obligation_id': 'challenge', 'action': 'rebuttal',
                        'refs': ['contrary'], 'reason': 'A different reset condition may explain the observation.'})
                    c.stop('fixture_complete')
            elif scenario == 'resume-clean-stop':
                c.stop('fixture_complete')
            elif scenario == 'lead-task-handoff':
                if generation == 1:
                    submit(self.context, 'task_create', {'task_id': 'lead-task', 'question': 'Inspect fixture.',
                        'priority': 1, 'resources': ['source-main'], 'prerequisites': [], 'evidence_refs': []})
                    submit(self.context, 'task_assign', {'task_id': 'lead-task', 'worker_id': 'lead-1'})
                elif generation == 2:
                    assignment = c.state()['workers']['lead-1']['assignment']
                    submit(self.context, 'task_result', {'task_id': 'lead-task', 'generation': assignment['generation'],
                        'disposition': 'completed', 'result': 'Inspected the assigned fixture.', 'evidence_refs': []})
                else:
                    c.stop('fixture_complete')
            elif scenario == 'coordinator-exit':
                self.events = []
                entered.set()
            if role == 'lead':
                time.sleep(.06)

        def observe(self, timeout_seconds=0):
            time.sleep(min(.02, timeout_seconds))
            events, self.events = self.events, []
            if events:
                self.active = False
            return events

        def interrupt(self):
            self.active = False

        def renew(self, seconds=None):
            self.context.authorize()

        def steer(self, message):
            return {'delivered': True}

        def finish(self):
            if scenario == 'coordinator-exit':
                finish_entered.set()
                require(finish_release.wait(8), 'fixture cleanup barrier not released')
            self.active = False
            endings.append((self.context.worker['id'], self.context.worker['generation']))
            return {'runtime': {'session_id': self.session_id, 'owner_receipt_sha256': digest(canonical(self.owner())),
                'process_exited': True, 'child_absence': 'verified', 'capabilities_revoked': True},
                'environment': None, 'cleanup': 'verified',
                'resources': {name: 'reset' for name in self.context.grant['resources']}}

    if scenario == 'resume-clean-stop':
        grant = c.prepare_worker_dispatch('lead-1', 1, x.workspace('lead-1'), seconds=30,
            resources=[], adapter_id='fixture')
        owner = x.owner('lead-1')
        c.record_worker_started('lead-1', 1, owner['session_id'], x.workspace('lead-1'), owner_receipt=owner)
        c.revoke_worker('lead-1', 1, reason='fixture_restart')
        c.record_runtime_stopped(grant, {'session_id': owner['session_id'],
            'owner_receipt_sha256': digest(canonical(owner)), 'process_exited': True,
            'child_absence': 'verified', 'capabilities_revoked': True})
        receipt = c.store_receipt(grant, {'status': 'settled', 'worker_seconds': 7, 'resources': {},
            'usage': {'tokens': {'total': 11}, 'cost': None}, 'cleanup': 'verified'}, adapter_id='fixture')
        c.adopt_receipt(grant['dispatch_id'], receipt, adapter_id='fixture')
    runner = Runner(c, boundary_factory=Peer)
    if scenario == 'coordinator-exit':
        original_state = c.state
        crashed = threading.Event()
        results = []
        def state_with_failure():
            state = original_state()
            if threading.current_thread().name == 'fixture-coordinator' and entered.is_set() and not crashed.is_set():
                crashed.set()
                raise ControllerError('fixture_coordinator_crash')
            return state
        c.state = state_with_failure
        def coordinate():
            try:
                results.append(runner.run())
            except Exception as error:
                results.append({'code': getattr(error, 'code', type(error).__name__)})
        thread = threading.Thread(target=coordinate, name='fixture-coordinator')
        thread.start()
        try:
            require(crashed.wait(4), 'coordinator failure was not injected')
            time.sleep(.05)
            try:
                with Runner(c, boundary_factory=Peer).ownership():
                    raise AssertionError('ownership released while worker was still alive')
            except RunnerError as error:
                require(error.code == 'engagement_already_running', error.code)
            require(finish_entered.wait(4) and thread.is_alive(), 'coordinator did not wait for owned cleanup')
            finish_release.set()
            thread.join(5)
            require(not thread.is_alive() and all(not job.is_alive() for job in runner.jobs.values()), 'owned jobs survived coordinator exit')
            with Runner(c, boundary_factory=Peer).ownership():
                pass
        finally:
            finish_release.set()
            c.state = original_state
            c.stop('fixture_cleanup')
            thread.join(5)
            for job in runner.jobs.values():
                job.join(3)
        return {'scenario': scenario, 'status': 'pass', 'result': results}
    try:
        result = runner.run()
    finally:
        if any(job.is_alive() for job in runner.jobs.values()):
            c.stop('fixture_cleanup')
            for job in runner.jobs.values():
                job.join(3)
    state = c.state()
    if scenario == 'reviewed-closure':
        require(result['status'] == 'closed', repr(result.get('failures')))
        require(state['result'] == {'closure_id': 'dry', 'outcome': 'covered_dry'}, 'reviewed ending lost')
        require(all(row['status'] == 'stopped' for row in state['workers'].values()), 'worker survived closure')
        require(state['cleanup'] == 'verified', 'closure lacks cleanup')
        process = subprocess.run([sys.executable, str(ROOT / 'tools/native_engagement.py'), 'export',
            '--engagement-root', str(c.root), '--output', str(path / 'export')], capture_output=True, text=True, timeout=10)
        require(process.returncode == 0, process.stdout)
    elif scenario == 'specialist-next-task':
        require(all(row['status'] == 'completed' for row in state['tasks'].values()), 'ready work stranded')
        require(len([entry for entry in starts if entry[0] == 'specialist-1']) == 2, 'specialist not reconstructed for next assignment')
        require([entry for entry in endings if entry[0] == 'specialist-1'] ==
                [entry for entry in starts if entry[0] == 'specialist-1'], 'prior worker not stopped before new generation')
    elif scenario == 'review-replacement':
        lead = state['workers']['lead-1']
        require(lead['generation'] >= 3, 'held lead or nonresponsive lead was stranded')
        require(state['obligations']['challenge']['prior_opportunities'][-1] == 2, 'replacement did not bind exactly two completed opportunities')
        require(state['obligations']['challenge']['state'] == 'disputed', 'replacement lost the open obligation')
        second = next(peer for peer in peers if peer.context.worker['generation'] == 2)
        require(all('Respond to the contrary observation.' in prompt for prompt in second.prompts), 'opportunity counted without delivery')
    elif scenario == 'resume-clean-stop':
        require(starts == [('lead-1', 2)], 'clean worker did not resume in a fresh generation: ' + repr(result.get('failures')))
        require(state['usage']['worker_seconds'] >= 7 and state['usage']['tokens']['total'] == 16, 'restart reset allowance or observed usage')
    elif scenario == 'lead-task-handoff':
        require(starts == [('lead-1', 1), ('lead-1', 2), ('lead-1', 3)], 'lead assignment or completion stranded its continuation: ' + repr(result.get('failures')))
        require(state['tasks']['lead-task']['status'] == 'completed', 'lead outcome lost')
    elif scenario == 'stale-closure':
        require(result['status'] == 'stopped' and state['tasks']['late-followup']['status'] == 'ready', 'stale approval stranded valid follow-up')
        require('result' not in state, 'stale closure finalized')
        require(state['closures']['dry']['state'] == 'reopened' and state['reviews']['review-dry']['status'] == 'stale',
                'prior approval could revive without a new review')
    require(not state['usage']['reserved_worker_seconds'], 'clean terminal work retained a reservation')
    return {'scenario': scenario, 'status': 'pass', 'starts': starts, 'endings': endings,
        'ending': result['status'], 'invocations': state['usage']['invocations']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scenario', default='all')
    args = parser.parse_args()
    report = {'classification': 'engineering_simulation', 'provider_calls': 0,
        'research_acceptance': 'not_run', 'scenarios': []}
    for scenario in ('reviewed-closure', 'specialist-next-task', 'review-replacement', 'resume-clean-stop',
                     'lead-task-handoff', 'capture-parent-lease', 'stale-closure', 'coordinator-exit', 'prompt-budget', 'prompt-wire'):
        if args.scenario not in ('all', scenario):
            continue
        try:
            with tempfile.TemporaryDirectory(prefix='oslit-coordination-') as directory:
                report['scenarios'].append(check(Path(directory).resolve(), scenario))
        except Exception as error:
            report['scenarios'].append({'scenario': scenario, 'status': 'fail',
                'error': type(error).__name__ + ': ' + str(error)})
    report['status'] = 'pass' if report['scenarios'] and all(row['status'] == 'pass' for row in report['scenarios']) else 'fail'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    return report['status'] != 'pass'


if __name__ == '__main__':
    raise SystemExit(main())
