#!/usr/bin/env python3
"""Failure-first signed workflows for useful native context across related tasks.

Run with --output FILE. Python 3 and ssh-keygen are required. All native owners,
environment receipts and network observations here are explicitly simulated;
the signed inputs, controller journal, runner and authority checks are real.
Expected: every scenario passes. Temporary keys, records and workspaces are
removed. No provider, target, Docker daemon or SSH host is contacted.

The retained path must keep one specialist, session, owner, dispatch and allowance
after a genuinely completed invocation. It may consume the old outcome and claim
the next eligible task only when the resources and runtime authority are identical.
Reviewers, changed resources, stale grants, nonterminal native/tool work, unknown
effects and changed session/owner readback must use the existing cleanup path.
Long-lived same-owner native_tools/network_proxy pipes remain dispatched, never
fabricated as settled. Replayed history must preserve both task assignments.
"""
from __future__ import annotations

import argparse
import copy
from datetime import timedelta
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'tools'), str(Path(__file__).parent)]
from check_engagement_evidence_e2e import Case, fixture, require
from engagement_contract import canonical, digest, load_inputs
from engagement_controller import Controller, ControllerError, Principal, instant
from engagement_runner import Runner, WorkerContext


class Workflow(Case):
    def __init__(self, path, *, application=False, role='specialist', pending=False,
                 next_resources=None, higher_incompatible=False, no_next=False, startup_pipes=False):
        self.path, self.serial, self.workspaces = path, 0, {}
        self.inputs = fixture.make_fixture(path / 'input')
        scope = fixture.fixture_scope(self.inputs)
        scope['limits']['hard']['invocations'] = 100
        scope['limits']['max_workers'] = 6
        if application:
            scope['access'].append({'id': 'app-main', 'kind': 'application',
                'identity': {'base_url': 'http://127.0.0.1:43199', 'version': None},
                'account_refs': [], 'permissions': ['read']})
            scope['network']['target'] = [{'protocol': 'http', 'host': '127.0.0.1', 'port': 43199,
                'address_policy': {'public_only': False, 'cidrs': ['127.0.0.1/32']}}]
            scope['effects'][0]['access_ids'].append('app-main')
        fixture.resign_fixture(self.inputs, scope)
        self.contract = load_inputs(self.inputs)
        self.c = Controller.initialize(path / 'engagement', self.contract, evidence_class='engineering_simulation')
        self.lead = Principal('worker', 'lead-1', 1)
        self.start('lead-1')
        self.resources = ['source-main', 'app-main'] if application else ['source-main']
        self.actor = self.worker('specialist-1', role, start=False)
        self.request('task_create', {'task_id': 'task-1', 'question': 'Inspect original harmless bytes.',
            'priority': 10, 'resources': self.resources, 'prerequisites': [], 'evidence_refs': []})
        self.request('task_assign', {'task_id': 'task-1', 'worker_id': self.actor.id})
        if not no_next:
            self.request('task_create', {'task_id': 'task-2', 'question': 'Follow up using the same observations.',
                'priority': 9, 'resources': self.resources if next_resources is None else next_resources,
                'prerequisites': ['task-1'], 'evidence_refs': []})
        if higher_incompatible:
            self.request('task_create', {'task_id': 'task-first', 'question': 'Higher priority independent question.',
                'priority': 20, 'resources': [], 'prerequisites': ['task-1'], 'evidence_refs': []})
        self.g = None
        self.session = 'retained-session'
        if not pending:
            self.g = self.c.prepare_worker_dispatch(self.actor.id, 1, self.workspace(self.actor.id),
                seconds=30, resources=self.resources, adapter_id='native-runner')
            if startup_pipes:
                for service in ('native_tools', 'network_proxy'):
                    self.environment('launch_stdio', 'dispatched', role=service)
            self.c.record_runtime_preparation_owner(self.g, self.owner(self.actor.id, self.session))
            self.c.record_worker_started(self.actor.id, 1, self.session, self.workspace(self.actor.id),
                owner_receipt=self.owner(self.actor.id, self.session))

    def outcome(self, *, settled=True, disposition='completed', status='completed'):
        invocation = self.c.begin_invocation(self.g)
        self.request('task_result', {'task_id': 'task-1', 'generation': 1,
            'disposition': disposition, 'result': 'The first bounded question is answered.',
            'evidence_refs': []}, self.actor)
        if settled:
            self.c.record_invocation_observed(self.g, invocation, {'status': status,
                'usage': {'tokens': {'input': 2, 'output': 3, 'total': 5}, 'cost': None}})
        return invocation

    def environment(self, operation='execute', status='settled', *, role=None, nonce=None, grant=None):
        grant = grant or self.g
        nonce = nonce or ('2' * 32)
        profile = self.contract.environment_profiles['lab-main']
        identity = {'kind': 'research-environment-receipt-v2', 'nonce': nonce,
            'container_id': 'a' * 64, 'container_name': 'oslit-' + nonce,
            'stage_container_id': None, 'stage_container_name': 'oslit-' + nonce + '-stage',
            'prepared_image_id': None, 'prepared_image_name': 'oslit-input-' + nonce + ':latest',
            'unsettled': [], 'daemon_id': 'fixture-daemon', 'image_id': profile['image_id'],
            'profile_sha256': digest(json.dumps(profile, sort_keys=True, separators=(',', ':')).encode()),
            'support_inputs': [],
            'access': [{k: row[k] for k in ('id', 'kind', 'identity')}
                       for row in self.contract.scope['access'] if row['id'] in grant['resources']]}
        common = {'kind': 'environment-observation-v2', 'operation': operation,
            'operation_id': 'operation-' + uuid.uuid4().hex, 'identity': identity}
        extra = {'role': role} if role is not None else {}
        self.c.record_environment_observation(grant, 'lab-main', dict(common,
            phase='intent', request_sha256=digest(b'harmless command'), **extra), effect_id='read-source')
        if status is not None:
            self.c.record_environment_observation(grant, 'lab-main', dict(common,
                phase='result', status=status, **extra), effect_id='read-source')
        return common

    def network(self, status=None):
        identity = self.environment()['identity']
        common = {'kind': 'target-network-observation-v1', 'operation_id': 'target-request',
            'access_id': 'app-main', 'effect_id': 'read-source', 'account_ref': None,
            'origin': 'http://127.0.0.1:43199', 'method': 'GET', 'path_sha256': digest(b'/harmless')}
        self.c.record_network_observation(self.g, 'lab-main', identity['nonce'], dict(common, phase='intent'))
        if status is not None:
            self.c.record_network_observation(self.g, 'lab-main', identity['nonce'], dict(common,
                phase='result', status=status, http_status=200, request_bytes=0, response_bytes=1))


def unchanged_after_refusal(x):
    before = x.c.state()
    try:
        result = x.c.continue_specialist(x.g)
    except ControllerError:
        result = None
    require(result is None, 'unsafe specialist continuation admitted')
    require(x.c.state() == before, 'refused continuation changed tasks, authority or usage')


def continuity(x):
    x.outcome()
    prior = copy.deepcopy(x.g)
    before = x.c.state()
    continued = x.c.continue_specialist(x.g)
    require(continued is not None and continued['assignment']['task_id'] == 'task-2', 'related next task not assigned')
    state = Controller(x.c.root).state()
    worker = state['workers'][x.actor.id]
    require(state['tasks']['task-1']['status'] == 'completed' and state['tasks']['task-2']['status'] == 'assigned',
        'journal did not atomically finish and claim')
    require(worker['status'] == 'active' and worker['generation'] == 1 and worker['session_id'] == x.session,
        'native worker identity was recreated')
    require(state['usage'] == before['usage'] and len(state['dispatches']) == 1 and state['cleanup'] == 'pending',
        'continuation created allowance or asserted cleanup')
    dispatch = state['dispatches'][prior['dispatch_id']]
    require(dispatch['status'] == 'pending' and prior in dispatch['prior_grants'], 'prior grant history was lost')
    require({k: v for k, v in continued.items() if k != 'assignment'} ==
            {k: v for k, v in prior.items() if k != 'assignment'}, 'continuation widened authority or lease')
    x.c.authorize_dispatch(continued)
    try:
        x.c.authorize_dispatch(prior)
    except ControllerError:
        pass
    else:
        raise AssertionError('old task grant admitted a new effect')
    x.c.bind_grant(state, prior)
    second = x.c.begin_invocation(continued)
    require(second != before['dispatches'][prior['dispatch_id']]['invocations'][0] and
        x.c.state()['usage']['invocations'] == 2, 'second native invocation was free or reused')


def pipes(x):
    continuity(x)
    operations = x.c.state()['environment_operations'].values()
    require(all(row['result']['status'] == 'dispatched' and row['session_id'] is None for row in operations),
        'startup pipes fabricated as settled or falsely required a preexisting native session')


def blocked_operation(x, operation, status, role=None):
    x.outcome()
    x.environment(operation, status, role=role)
    unchanged_after_refusal(x)


def auxiliary(x):
    x.c.prepare_capture_dispatch(x.g, seconds=5, resources=x.resources)
    x.outcome()
    unchanged_after_refusal(x)


def network(x, status):
    x.outcome()
    x.network(status)
    unchanged_after_refusal(x)


def settled_network(x):
    x.network('settled')
    continuity(x)


def changed_profile(x):
    x.outcome()
    x.g = dict(x.g, profile_id='other-runtime')
    unchanged_after_refusal(x)


def invocation(x, status):
    x.outcome(settled=status is not None, status=status)
    unchanged_after_refusal(x)


def different_task(x):
    x.outcome()
    unchanged_after_refusal(x)


def authority(x, kind):
    x.outcome()
    if kind == 'stop':
        x.c.stop('operator stop')
    elif kind == 'expiry':
        x.c.clock = lambda: instant(x.g['lease_expires_at']) + timedelta(seconds=1)
    else:
        x.c.revoke_worker(x.actor.id, 1, reason='retire specialist')
    unchanged_after_refusal(x)


def owner_repeat(x):
    receipt = x.owner(x.actor.id, x.session)
    before = x.c.state()
    result = x.c.record_runtime_preparation_owner(x.g, receipt)
    require(result['status'] == 'recorded' and x.c.state() == before, 'same native owner readback is not idempotent')
    for key, value in (('session_id', 'changed-session'), ('profile_sha256', 'sha256:' + '0' * 64),
                       ('process', dict(receipt['process'], started_microseconds=3))):
        try:
            x.c.record_runtime_preparation_owner(x.g, dict(receipt, **{key: value}))
        except ControllerError:
            pass
        else:
            raise AssertionError('active owner replacement accepted: ' + key)
        require(x.c.state() == before, 'changed owner readback mutated journal')
    clock = x.c.clock
    x.c.clock = lambda: instant(x.g['lease_expires_at']) + timedelta(seconds=1)
    try:
        x.c.record_runtime_preparation_owner(x.g, receipt)
    except ControllerError:
        pass
    else:
        raise AssertionError('expired owner repeat bypassed authority')
    x.c.clock = clock
    x.c.revoke_worker(x.actor.id, 1, reason='fixture revoke')
    try:
        x.c.record_runtime_preparation_owner(x.g, receipt)
    except ControllerError:
        pass
    else:
        raise AssertionError('retired owner reused receipt to regain authority')


def publication_race(x):
    x.outcome()
    runner = Runner(x.c, boundary_factory=lambda context: None)
    context = WorkerContext(runner, x.c.state()['workers'][x.actor.id], x.g, x.workspace(x.actor.id))
    committed, release, checked = threading.Event(), threading.Event(), threading.Event()
    failures = []
    original = x.c.continue_specialist
    def pause(grant):
        result = original(grant)
        committed.set()
        require(release.wait(3), 'fixture did not release grant publication')
        return result
    x.c.continue_specialist = pause
    def advance():
        try:
            context.continue_specialist()
        except Exception as error:
            failures.append(str(error))
    def watch():
        try:
            context.authorize()
        except Exception as error:
            failures.append(str(error))
        finally:
            checked.set()
    worker = threading.Thread(target=advance)
    worker.start()
    require(committed.wait(3), 'continuation did not reach journal publication')
    watcher = threading.Thread(target=watch)
    watcher.start()
    try:
        require(not checked.wait(.05), 'watcher observed new assignment with stale context grant')
    finally:
        release.set()
        worker.join(3); watcher.join(3)
    require(not worker.is_alive() and not watcher.is_alive() and not failures, repr(failures))
    require(context.grant['assignment']['task_id'] == 'task-2', 'context did not publish continued grant')


def runner_workflow(x, *, resume='valid', delayed=False):
    x.c.revoke_worker('lead-1', 1, reason='fixture owns only specialist runtime')
    peers = []
    class Peer:
        def __init__(self, context):
            self.context = context
            self.runtime = self
            self.session_id = 'peer-' + uuid.uuid4().hex
            self.active, self.usage, self.closed = False, None, False
            self.count, self.observations, self.resumes = 0, 0, []
            self.prompts, self.grants = [], []
            peers.append(self)

        def owner_receipt(self):
            return x.owner(x.actor.id, self.session_id)

        def start(self):
            self.context.controller.record_runtime_preparation_owner(self.context.grant, self.owner_receipt())
            return {'session_id': self.session_id, 'owner_receipt': self.owner_receipt()}

        def invoke(self, prompt, invocation_id):
            require(not self.closed and not self.active, 'invocation overlapped or restarted closed owner')
            self.context.authorize()
            self.count += 1
            self.active = True
            self.prompts.append(prompt)
            self.grants.append(copy.deepcopy(self.context.grant))
            self.usage = {'input_tokens': 2, 'output_tokens': 3, 'total_tokens': 5}
            assignment = self.context.controller.state()['workers'][x.actor.id]['assignment']
            self.context.submit({'request_id': 'finish-' + invocation_id,
                'expected_revision': self.context.controller.state()['revision'], 'type': 'task_result',
                'payload': dict(assignment, disposition='completed', result='Harmless task completed.', evidence_refs=[])})
            return {'invocation_id': invocation_id, 'session_id': self.session_id}

        def observe(self, timeout_seconds=0):
            self.observations += 1
            if delayed and self.count == 1 and self.observations <= 2:
                state = x.c.state()
                require(state['tasks']['task-1']['status'] == 'assigned' and state['tasks']['task-2']['status'] == 'ready',
                    'task advanced before native completion')
                time.sleep(min(.01, timeout_seconds))
                return []
            self.active = False
            return [{'event': 'completed', 'status': 'completed'}]

        def resume(self, session_id):
            require(not self.active and session_id == self.session_id, 'non-idle/wrong session resume')
            self.resumes.append(session_id)
            if resume == 'unsettled':
                raise ValueError('native_tool_outcome_unsettled')
            if resume == 'changed':
                return {'session_id': 'other-session'}
            self.context.controller.record_runtime_preparation_owner(self.context.grant, self.owner_receipt())
            return {'session_id': self.session_id}

        def steer(self, message):
            self.context.authorize()

        def renew(self, seconds):
            self.context.authorize()

        def finish(self):
            self.closed, self.active = True, False
            return {'runtime': {'session_id': self.session_id,
                'owner_receipt_sha256': digest(canonical(self.owner_receipt())),
                'process_exited': True, 'child_absence': 'verified', 'capabilities_revoked': True},
                'environment': None, 'cleanup': 'verified',
                'resources': {name: 'reset' for name in self.context.grant['resources']}}

    result = Runner(x.c, boundary_factory=Peer).run()
    require(len(peers) == 1 and peers[0].closed, 'fixture owner was recreated or left alive')
    peer, state = peers[0], x.c.state()
    require(state['tasks']['task-1']['status'] == 'completed', 'first outcome was lost')
    if resume == 'valid':
        require(peer.count == 2 and len(set(peer.resumes)) == 1 and peer.resumes,
            'related tasks did not retain actual boundary session')
        require(state['tasks']['task-2']['status'] == 'completed' and 'task-2' in peer.prompts[1],
            'second task or prompt lost assignment')
        require(peer.grants[0]['dispatch_id'] == peer.grants[1]['dispatch_id'] and
            peer.grants[0]['generation'] == peer.grants[1]['generation'], 'continuation created owner/dispatch')
        require(len(state['dispatches']) == 1 and state['usage']['invocations'] == 2 and
            state['usage']['tokens']['total'] == 10, 'retained session miscounted usage')
        require(not result['failures'], 'safe continuation failed: ' + repr(result['failures']))
    else:
        require(peer.count == 1 and state['tasks']['task-2']['status'] == 'ready', 'bad readback admitted next task')
        require(peer.resumes, 'native session readback was not attempted')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scenario', default='all')
    args = parser.parse_args()
    cases = {
        'same-authority': ({}, continuity),
        'retained-pipes': ({'startup_pipes': True}, pipes),
        'no-outcome': ({}, unchanged_after_refusal),
        'no-next-task': ({'no_next': True}, different_task),
        'pending-execution': ({}, lambda x: blocked_operation(x, 'execute', None)),
        'dispatched-execution': ({}, lambda x: blocked_operation(x, 'execute', 'dispatched')),
        'unknown-stdio': ({}, lambda x: blocked_operation(x, 'launch_stdio', 'unknown', 'native_tools')),
        'pending-capture': ({}, auxiliary),
        'pending-network': ({'application': True}, lambda x: network(x, None)),
        'unknown-network': ({'application': True}, lambda x: network(x, 'unknown')),
        'settled-application': ({'application': True}, settled_network),
        'pending-invocation': ({}, lambda x: invocation(x, None)),
        'failed-invocation': ({}, lambda x: invocation(x, 'failed')),
        'changed-resources': ({'next_resources': []}, different_task),
        'changed-profile': ({}, changed_profile),
        'priority-preserved': ({'higher_incompatible': True}, different_task),
        'fresh-reviewer': ({'role': 'reviewer'}, different_task),
        'stop': ({}, lambda x: authority(x, 'stop')),
        'expired-lease': ({}, lambda x: authority(x, 'expiry')),
        'retired-worker': ({}, lambda x: authority(x, 'retire')),
        'same-owner-readback': ({}, owner_repeat),
        'atomic-grant-publication': ({}, publication_race),
        'runner-same-session': ({'pending': True}, runner_workflow),
        'runner-delayed-completion': ({'pending': True}, lambda x: runner_workflow(x, delayed=True)),
        'runner-changed-session': ({'pending': True}, lambda x: runner_workflow(x, resume='changed')),
        'runner-unsettled-tools': ({'pending': True}, lambda x: runner_workflow(x, resume='unsettled')),
    }
    report = {'classification': 'engineering_simulation', 'provider_calls': 0, 'target_calls': 0,
        'native_containment': 'not_exercised', 'scenarios': []}
    for name, (options, check) in cases.items():
        if args.scenario not in ('all', name):
            continue
        try:
            with tempfile.TemporaryDirectory(prefix='retained-specialist-') as folder:
                check(Workflow(Path(folder).resolve(), **options))
            report['scenarios'].append({'scenario': name, 'status': 'pass'})
        except Exception as error:
            report['scenarios'].append({'scenario': name, 'status': 'fail',
                'error': type(error).__name__ + ': ' + str(error)[:300]})
    report['status'] = 'pass' if report['scenarios'] and all(row['status'] == 'pass' for row in report['scenarios']) else 'fail'
    report['source_sha256'] = {name: digest((ROOT / name).read_bytes()) for name in
        ['tools/engagement_controller.py', 'tools/engagement_runner.py', str(Path(__file__).relative_to(ROOT))]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    return report['status'] != 'pass'


if __name__ == '__main__':
    raise SystemExit(main())
