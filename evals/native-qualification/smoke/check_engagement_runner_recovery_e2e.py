#!/usr/bin/env python3
"""Failure-first runner transitions using the real journal/CLI and a fake boundary.

Run with --repository CHECKOUT --output FILE. Python 3 and the repository's signed
fixture prerequisites are required. No provider, Docker daemon or target is used.
The recovery interruption preserves the exact post-receipt journal prefix; it is
an injected local exception, not evidence of a live native-process crash.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import uuid

DEFAULT_REPOSITORY = Path(__file__).resolve().parents[3]
USAGE = {'input_tokens': 11, 'output_tokens': 7, 'total_tokens': 18, 'estimated_cost': .5}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def until(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(.02)
    return None


def run_case(repository, fixture, scenario, subcase=None):
    from engagement_contract import canonical, digest, load_inputs
    from engagement_controller import Controller, ControllerError, GRANT_KEYS, Principal
    from engagement_runner import Runner
    row = {'name': subcase or scenario, 'status': 'fail'}
    with tempfile.TemporaryDirectory(prefix='runner-recovery-e2e-') as name:
        root = Path(name).resolve()
        inputs = fixture.make_fixture(root / 'inputs')
        controller = Controller.initialize(root / 'engagement', load_inputs(inputs),
                                           evidence_class='engineering_simulation')
        peers, invocations = {}, []
        serial = 0
        thread = None
        runner_results = []
        interrupted_finalization = threading.Event()

        def cli(operation):
            process = subprocess.run([sys.executable, str(repository / 'tools/native_engagement.py'),
                                      operation, '--engagement-root', str(controller.root)],
                                     capture_output=True, text=True, timeout=10)
            document = json.loads(process.stdout)
            require(document.get('status') != 'rejected', 'CLI rejected ' + operation)
            return document

        def submit(principal, kind, payload):
            nonlocal serial
            serial += 1
            request_id = 'recovery-check-' + str(serial)
            for _ in range(20):
                try:
                    result = controller.submit(principal, {'request_id': request_id,
                        'expected_revision': controller.state()['revision'], 'type': kind, 'payload': payload})
                    if runner is not None:
                        runner.changed.set()
                    return result
                except ControllerError as error:
                    if error.code != 'revision_conflict':
                        raise
            raise AssertionError('concurrent revision never settled')

        class Boundary:
            def __init__(self, context):
                self.context = context
                self.runtime = self
                self.session_id = 'recovery-' + uuid.uuid4().hex
                self.active = False
                self.usage = None
                self.closed = False
                self.invocation_id = None
                self.events = []
                self.entered = threading.Event()
                self.lock = threading.Lock()
                self.terminal_emitted = False
                previous = peers.get(context.worker['id'])
                if previous is not None:
                    require(scenario == 'late-assignment' and previous.closed,
                            'worker reexecuted or acquired a second live boundary')
                peers[context.worker['id']] = self

            def owner_receipt(self):
                return {'kind': 'native-runtime-owner-v1', 'runtime': 'codex',
                    'session_id': self.session_id, 'profile_sha256': self.context.assignment['profile_sha256'],
                    'boundary': 'darwin-no-fork-v1',
                    'process': {'pid': 34567, 'pgid': 34567, 'uid': 501,
                                'started_seconds': 1, 'started_microseconds': 2}}

            def start(self):
                return {'session_id': self.session_id, 'owner_receipt': self.owner_receipt()}

            def invoke(self, prompt, invocation_id):
                self.context.authorize()
                require(not self.closed, 'invocation after boundary closed')
                self.invocation_id = invocation_id
                self.active = True
                invocations.append((self.context.worker['id'], invocation_id))
                self.entered.set()
                if self.context.worker['id'] == 'worker-2' and scenario != 'late-assignment':
                    if scenario == 'outcome-recovery':
                        self.terminal('completed')
                    if subcase != 'operator-stop':
                        assignment = self.context.controller.state()['workers']['worker-2']['assignment']
                        submit(self.context.principal, 'task_result', {'task_id': assignment['task_id'],
                            'generation': assignment['generation'], 'disposition': 'completed',
                            'result': 'Inspected the harmless fixture.', 'evidence_refs': []})
                return {'session_id': self.session_id, 'invocation_id': invocation_id}

            def terminal(self, status='interrupted'):
                with self.lock:
                    if self.invocation_id is not None and not self.terminal_emitted:
                        self.terminal_emitted = True
                        self.active = False
                        self.usage = dict(USAGE)
                        self.events.append({'event': 'completed', 'status': status,
                            'session_id': self.session_id, 'invocation_id': self.invocation_id})

            def observe(self, timeout_seconds=0):
                time.sleep(min(timeout_seconds, .02))
                with self.lock:
                    events, self.events = self.events, []
                    return events

            def steer(self, _message):
                return {'delivered': True}

            def renew(self, _seconds):
                self.context.authorize()

            def interrupt(self):
                self.terminal()
                return {'status': 'interrupted'}

            def finish(self):
                self.terminal()
                self.closed = True
                return {'runtime': {'session_id': self.session_id,
                    'owner_receipt_sha256': digest(canonical(self.owner_receipt())),
                    'process_exited': True, 'child_absence': 'verified', 'capabilities_revoked': True},
                    'environment': None, 'cleanup': 'verified',
                    'resources': {resource: 'reset' for resource in self.context.grant['resources']}}

        def start_runner(value):
            def run():
                try:
                    runner_results.append(value.run())
                except BaseException as error:
                    runner_results.append({'exception': type(error).__name__})
            worker = threading.Thread(target=run, daemon=True)
            worker.start()
            return worker

        def snapshot():
            state = controller.state()
            return {'worker_status': state['workers'].get('worker-2', {}).get('status'),
                'task_status': state['tasks'].get('task-1', {}).get('status'),
                'outcome_pending': bool(state['workers'].get('worker-2', {}).get('outcome_pending')),
                'dispatch_statuses': [entry['status'] for entry in state['dispatches'].values()],
                'invocation_statuses': [entry['status'] for entry in state['invocations'].values()],
                'usage': state['usage']}

        runner = None
        try:
            lead = Principal('worker', 'lead-1', 1)
            if scenario == 'late-assignment':
                runner = Runner(controller, boundary_factory=Boundary)
                thread = start_runner(runner)
                require(until(lambda: peers.get('lead-1') and peers['lead-1'].entered.is_set()),
                        'lead invocation never started')
            else:
                workspace = root / 'lead-setup'; workspace.mkdir(mode=0o700)
                controller.record_worker_started('lead-1', 1, 'lead-setup-session', workspace)

            submit(lead, 'worker_request', {'worker_id': 'worker-2', 'role': 'specialist',
                'profile_id': 'runtime-main', 'question': 'Inspect the assigned private copy.'})
            submit(lead, 'task_create', {'task_id': 'task-1', 'question': 'Inspect fixture.',
                'priority': 1, 'resources': ['source-main'], 'prerequisites': [], 'evidence_refs': []})

            if scenario == 'late-assignment':
                # Let the coordinator observe creation while assignment is still absent.
                time.sleep(.4)
                require(until(lambda: controller.state()['workers']['worker-2']['status'] in ('pending', 'active')),
                        'unassigned worker never became assignable')
                row['started_before_assignment'] = 'worker-2' in peers
            submit(lead, 'task_assign', {'task_id': 'task-1', 'worker_id': 'worker-2'})

            if scenario == 'outcome-recovery':
                def lose_after_receipt(*_args):
                    state = controller.state()
                    require(all(entry['status'] == 'settled' for entry in state['dispatches'].values()),
                            'loss injection ran before receipt adoption')
                    interrupted_finalization.set()
                    raise RuntimeError('simulated interruption before outcome commit')
                controller.finalize_worker_outcome = lose_after_receipt

            if thread is None:
                runner = Runner(controller, boundary_factory=Boundary)
                thread = start_runner(runner)

            require(until(lambda: peers.get('worker-2') and peers['worker-2'].entered.is_set()),
                    'assigned specialist never started')
            if scenario == 'late-assignment':
                def correctly_bound():
                    state = controller.state(); worker = state['workers']['worker-2']
                    peer = peers['worker-2']
                    if worker['status'] != 'active' or peer.closed:
                        return False
                    try: peer.context.authorize()
                    except Exception: return False
                    return (peer.context.grant['assignment'] == worker['assignment'] and
                            set(peer.context.grant['resources']) == {'source-main'})
                safe = until(correctly_bound, timeout=2)
                row['observed'] = snapshot()
                require(safe, 'late assignment stranded the worker or left the live grant stale')
                require(controller.state()['tasks']['task-1']['status'] == 'assigned', 'task was lost')
            else:
                if subcase == 'operator-stop':
                    require(cli('stop')['status'] == 'stopped', 'operator stop did not persist')
                thread.join(5)
                require(not thread.is_alive(), 'runner did not quiesce the finished or stopped worker')
                row['observed'] = snapshot()
                state = controller.state()
                if scenario == 'terminal-accounting':
                    records = list(state['invocations'].values())
                    require(len(records) == 1 and len(invocations) == 1, 'fixture invocation was retried')
                    invocation = records[0]
                    dispatch = state['dispatches'][invocation['dispatch_id']]
                    usage = state['usage']
                    recorded = (invocation['status'] not in ('pending', 'unknown') and
                        usage['tokens'] == {'input': 11, 'output': 7, 'total': 18} and
                        usage['known_estimated_cost'] == .5 and usage['native_invocations_observed'] == 1)
                    unknown = (invocation['status'] in ('pending', 'unknown') and dispatch['status'] != 'settled'
                        and usage['reserved_worker_seconds'] > 0)
                    require(recorded or unknown, 'terminal usage was discarded behind a settled dispatch')
                    if recorded:
                        grant = {key: dispatch[key] for key in GRANT_KEYS}
                        before = controller.state()['usage']
                        controller.record_invocation_observed(grant, invocation['invocation_id'],
                            {'status': invocation['status'], 'usage': invocation['usage']})
                        require(controller.state()['usage'] == before, 'duplicate terminal usage charged twice')
                        row['accounting'] = 'recorded_exactly_once'
                    else:
                        require(subcase == 'operator-stop' or state['tasks']['task-1']['status'] != 'completed',
                                'unsettled accounting finalized task completion')
                        row['accounting'] = 'explicit_unknown_with_reservation'
                else:
                    require(interrupted_finalization.is_set(), 'post-receipt interruption point was not exercised')
                    require(state['workers']['worker-2'].get('outcome_pending'), 'pending outcome fixture was lost')
                    before_usage = state['usage']; before_invocations = len(invocations)
                    controller = Controller(controller.root)
                    recovered = Runner(controller, boundary_factory=Boundary)
                    recovered.run()
                    state = controller.state(); row['after_restart'] = snapshot()
                    require(state['tasks']['task-1']['status'] == 'completed' and
                            not state['workers']['worker-2'].get('outcome_pending'),
                            'restart left the accepted outcome behind a settled receipt')
                    require(len(invocations) == before_invocations and state['usage'] == before_usage,
                            'recovery reexecuted or charged work')
                    Runner(Controller(controller.root), boundary_factory=Boundary).run()
                    require(controller.state()['usage'] == before_usage and len(invocations) == before_invocations,
                            'second recovery was not idempotent')
                row['cli_status'] = cli('status')['status']
            row['status'] = 'pass'
        except Exception as error:
            row['error'] = type(error).__name__ + ': ' + str(error)[:300]
            row.setdefault('observed', snapshot())
        finally:
            if thread is not None and thread.is_alive():
                try: cli('stop')
                except Exception: controller.stop('fixture_cleanup')
                thread.join(3)
            if thread is not None and thread.is_alive():
                row['status'] = 'fail'; row['cleanup_error'] = 'fixture runner thread did not stop'
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path, default=DEFAULT_REPOSITORY)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scenario', choices=('all', 'late-assignment', 'terminal-accounting', 'outcome-recovery'), default='all')
    args = parser.parse_args()
    repository = args.repository.resolve()
    sys.path.insert(0, str(repository / 'tools'))
    source_paths = ['tools/engagement_runner.py', 'tools/engagement_controller.py', 'tools/engagement_evidence.py',
                    'tools/engagement_contract.py', 'tools/native_engagement.py',
                    'evals/native-qualification/smoke/check_engagement_contract_e2e.py']
    report = {'kind': 'engagement-runner-recovery-check-v2', 'classification': 'engineering_simulation',
        'provider_calls': 0, 'research_acceptance': 'not_run', 'scenarios': [],
        'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    try:
        sources = {path: hashlib.sha256((repository / path).read_bytes()).hexdigest() for path in source_paths}
        report['source_sha256'] = sources
        spec = importlib.util.spec_from_file_location('runner_recovery_fixture', repository / source_paths[-1])
        fixture = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture)
        for scenario in ('late-assignment', 'terminal-accounting', 'outcome-recovery'):
            if args.scenario not in ('all', scenario):
                continue
            if scenario == 'terminal-accounting':
                cases = [run_case(repository, fixture, scenario, name) for name in ('task-result', 'operator-stop')]
                report['scenarios'].append({'name': scenario, 'status': 'pass' if all(row['status'] == 'pass' for row in cases) else 'fail', 'subcases': cases})
            else:
                report['scenarios'].append(run_case(repository, fixture, scenario))
        require(all(hashlib.sha256((repository / path).read_bytes()).hexdigest() == sha for path, sha in sources.items()),
                'repository source changed during checks')
        report['status'] = 'pass' if report['scenarios'] and all(row['status'] == 'pass' for row in report['scenarios']) else 'fail'
    except Exception as error:
        report['status'] = 'fail'; report['error'] = type(error).__name__ + ': ' + str(error)[:300]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'scenarios': len(report['scenarios']), 'output': str(args.output)}))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
