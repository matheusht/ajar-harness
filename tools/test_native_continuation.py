"""Offline contract checks for the durable continuation controller.

Run with PYTHONPATH=tools python3 -m unittest tools/test_native_continuation.py.
No provider, Docker, model, or target is used.
"""
from __future__ import annotations

import fcntl
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import native_continuation as continuation
import native_research as runner


def next_value(*, state='supported', with_next=True, stop=False, strong=True):
    return {
        'kind': continuation.NEXT_KIND,
        'last_result': {'state': state, 'rules_out': 'the tested input',
                        'unresolved': 'the next condition'},
        'capabilities': [{'capability': 'observed effect', 'enables': 'next reachable state'}],
        'coverage': [{'surface': 'entry', 'status': 'tested', 'limit': 'synthetic'}],
        'next': ({'question': 'what next?', 'test': 'run one check',
                  'prediction': 'the control remains', 'disconfirming': 'the control fails',
                  'authority': 'existing local scope'} if with_next else None),
        'proposed_stop': stop,
        'strong_lead': strong,
    }


def result(session='ses_1', dispatch='a' * 32):
    return {'status': 'acknowledged', 'session_id': session, 'dispatch_id': dispatch,
            'pool_before': {'used_tunnels': 0, 'charged_tunnel_bytes': 0, 'active': True},
            'pool_after': {'used_tunnels': 1, 'charged_tunnel_bytes': 10, 'active': True}}


class Fixture:
    def __init__(self, temp):
        self.root = Path(temp).resolve() / 'run'
        self.root.mkdir(mode=0o700)
        self.controls = self.root / 'controls'
        self.controls.mkdir(mode=0o700)
        (self.root / 'researcher').mkdir(mode=0o700)
        runner._write_json(self.root / 'plan.json', {'kind': 'continuation-test'}, once=True)
        self.calls = []
        self.write_next(None)

    def write_next(self, value):
        path = self.root / 'researcher/NEXT.json'
        if value is None:
            value = {'kind': continuation.NEXT_KIND, 'last_result': None,
                     'capabilities': [], 'coverage': [], 'next': None,
                     'proposed_stop': False, 'strong_lead': False}
        runner._write_json(path, value)

    def status(self, _root):
        return {'status': 'active', 'allowance': {'active': True}}

    def run(self, invoke, *, maximum=8, status=None, resume_after_stop=False):
        return continuation.continue_run(
            self.root, max_invocations=maximum, invoke=invoke,
            status_fn=status or self.status, resume_after_stop=resume_after_stop)


class ContinuationContract(unittest.TestCase):
    def test_research_resume_and_closure_request(self):
        with tempfile.TemporaryDirectory(prefix='continuation-') as temp:
            f = Fixture(temp)

            def invoke(command, session, prompt):
                f.calls.append((command, session, prompt))
                if command == 'research':
                    f.write_next(next_value())
                    return 0, result()
                f.write_next(next_value(state='refuted', with_next=False, stop=True))
                return 0, result(session='ses_1', dispatch='b' * 32)

            value = f.run(invoke)
            self.assertEqual([row[0] for row in f.calls], ['research', 'resume'])
            self.assertEqual(value['status'], 'closure_review_required')
            self.assertEqual(value['invocations'], 2)
            request = json.loads((f.controls / 'continuation/closure-request.json').read_text())
            self.assertEqual(request['kind'], continuation.REQUEST_KIND)
            self.assertEqual(request['capabilities'], next_value()['capabilities'])
            self.assertEqual(request['coverage'], next_value()['coverage'])
            self.assertEqual(request['reason'], 'proposed_stop')
            state = json.loads((f.controls / 'continuation/state.json').read_text())
            self.assertIsNone(state['pending'])
            self.assertEqual(state['last_result_state'], 'refuted')
            self.assertEqual(state['last_pool']['used_tunnels'], 1)

    def test_accept_closes(self):
        with tempfile.TemporaryDirectory(prefix='continuation-') as temp:
            f = Fixture(temp)

            def stop_invoke(command, session, prompt):
                f.calls.append((command, session, prompt))
                f.write_next(next_value(with_next=False, stop=True))
                return 0, result()

            self.assertEqual(f.run(stop_invoke)['status'], 'closure_review_required')
            request_path = f.controls / 'continuation/closure-request.json'
            runner._write_json(f.controls / 'continuation/closure-review.json', {
                'kind': continuation.REVIEW_KIND,
                'request_sha256': runner._sha(request_path),
                'decision': 'accept', 'reason': 'coverage accepted'})
            value = f.run(stop_invoke)
            self.assertEqual(value['status'], 'closed')
            self.assertEqual(len(f.calls), 1)
            events = [json.loads(line) for line in
                      (f.controls / 'continuation/events.jsonl').read_text().splitlines()]
            self.assertTrue(any(row.get('event') == 'closure_review'
                                and row.get('decision') == 'accept' for row in events))

    def test_reopen_requires_next_and_resumes(self):
        with tempfile.TemporaryDirectory(prefix='continuation-') as temp:
            f = Fixture(temp)

            def first_invoke(command, session, prompt):
                f.calls.append((command, session, prompt))
                f.write_next(next_value(with_next=False, stop=True))
                return 0, result()

            self.assertEqual(f.run(first_invoke)['status'], 'closure_review_required')
            request_path = f.controls / 'continuation/closure-request.json'
            runner._write_json(f.controls / 'continuation/closure-review.json', {
                'kind': continuation.REVIEW_KIND,
                'request_sha256': runner._sha(request_path),
                'decision': 'reopen', 'reason': 'untested sibling path',
                'test': 'run the sibling check'})
            with self.assertRaises(continuation.ContinuationError):
                f.run(first_invoke)
            self.assertEqual(len(f.calls), 1)
            f.write_next(next_value())

            def second_invoke(command, session, prompt):
                f.calls.append((command, session, prompt))
                f.write_next(next_value(state='blocked', with_next=False, stop=True))
                return 0, result(session='ses_2', dispatch='b' * 32)

            value = f.run(second_invoke)
            self.assertEqual(value['status'], 'closure_review_required')
            self.assertEqual([row[0] for row in f.calls], ['research', 'resume'])
            new_request = f.controls / 'continuation/closure-request.json'
            runner._write_json(f.controls / 'continuation/closure-review.json', {
                'kind': continuation.REVIEW_KIND,
                'request_sha256': runner._sha(new_request),
                'decision': 'accept', 'reason': 'bounded coverage accepted'})
            self.assertEqual(f.run(second_invoke)['status'], 'closed')

    def test_operator_stop_blocks_invocation(self):
        with tempfile.TemporaryDirectory(prefix='continuation-') as temp:
            f = Fixture(temp)
            (f.controls / 'continuation').mkdir(mode=0o700)
            runner._write_json(f.controls / 'continuation/STOP', {
                'kind': continuation.STOP_KIND, 'reason': 'operator_stop'})
            called = []
            value = f.run(lambda *args: called.append(args) or (0, result()))
            self.assertEqual(value['status'], 'stopped')
            self.assertEqual(called, [])

    def test_pending_dispatch_is_not_retried(self):
        with tempfile.TemporaryDirectory(prefix='continuation-') as temp:
            f = Fixture(temp)

            def crash(command, session, prompt):
                f.calls.append((command, session, prompt))
                raise RuntimeError('controller crashed after dispatch')

            with self.assertRaises(RuntimeError):
                f.run(crash)
            state = json.loads((f.controls / 'continuation/state.json').read_text())
            self.assertIsNotNone(state['pending'])
            called = []
            value = f.run(lambda *args: called.append(args) or (0, result()))
            self.assertEqual(value['status'], 'reconciliation_required')
            self.assertEqual(called, [])

    def test_context_loss_reconstructs(self):
        with tempfile.TemporaryDirectory(prefix='continuation-') as temp:
            f = Fixture(temp)

            def invoke(command, session, prompt):
                f.calls.append((command, session, prompt))
                if command == 'research':
                    f.write_next(next_value())
                    return 0, result()
                if command == 'resume':
                    return 2, {'status': 'rejected',
                               'code': 'resume_session_not_in_researcher_store'}
                f.write_next(next_value(state='blocked', with_next=False, stop=True))
                return 0, result(session='ses_2', dispatch='c' * 32)

            value = f.run(invoke)
            self.assertEqual([row[0] for row in f.calls], ['research', 'resume', 'reconstruct'])
            self.assertEqual(value['status'], 'closure_review_required')
            state = json.loads((f.controls / 'continuation/state.json').read_text())
            self.assertEqual(state['session_id'], 'ses_2')

    def test_max_invocations_and_journal(self):
        with tempfile.TemporaryDirectory(prefix='continuation-') as temp:
            f = Fixture(temp)

            def invoke(command, session, prompt):
                f.calls.append((command, session, prompt))
                f.write_next(next_value(state='inconclusive'))
                return 0, result(dispatch=f'{len(f.calls):032x}')

            value = f.run(invoke, maximum=2)
            self.assertEqual(value['status'], 'max_invocations')
            self.assertEqual([row[0] for row in f.calls], ['research', 'resume'])
            events = [json.loads(line) for line in
                      (f.controls / 'continuation/events.jsonl').read_text().splitlines()]
            self.assertEqual([row['event'] for row in events].count('dispatch_started'), 2)
            self.assertEqual([row['event'] for row in events].count('invocation'), 2)
            state = json.loads((f.controls / 'continuation/state.json').read_text())
            self.assertEqual(state['invocations'], 2)
            self.assertIsNone(state['pending'])

    def test_lease_blocks_second_loop(self):
        with tempfile.TemporaryDirectory(prefix='continuation-') as temp:
            f = Fixture(temp)
            continuation._cont(f.root)
            with open(f.controls / 'continuation/lease.lock', 'a+') as stream:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaises(continuation.ContinuationError):
                    f.run(lambda *args: (0, result()))

    def test_invalid_next_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix='continuation-') as temp:
            f = Fixture(temp)

            def invoke(command, session, prompt):
                f.calls.append((command, session, prompt))
                bad = next_value()
                bad['last_result']['state'] = 'maybe'
                f.write_next(bad)
                return 0, result()

            with self.assertRaises(continuation.ContinuationError):
                f.run(invoke)
            state = json.loads((f.controls / 'continuation/state.json').read_text())
            self.assertEqual(state['invocations'], 1)
            self.assertIsNone(state['pending'])

    def test_missing_next_brief_stops(self):
        with tempfile.TemporaryDirectory(prefix='continuation-') as temp:
            f = Fixture(temp)

            def invoke(command, session, prompt):
                f.calls.append((command, session, prompt))
                return 0, result()

            value = f.run(invoke)
            self.assertEqual(value['status'], 'next_brief_missing')
            state = json.loads((f.controls / 'continuation/state.json').read_text())
            self.assertEqual(state['invocations'], 1)
            self.assertIsNone(state['pending'])
            self.assertEqual(f.run(invoke)['status'], 'next_brief_missing')
            self.assertEqual(len(f.calls), 1)

    def test_fifo_next_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix='continuation-') as temp:
            f = Fixture(temp)

            def invoke(command, session, prompt):
                f.calls.append((command, session, prompt))
                path = f.root / 'researcher/NEXT.json'
                path.unlink()
                os.mkfifo(path)
                return 0, result()

            with self.assertRaises(continuation.ContinuationError):
                f.run(invoke)
            self.assertEqual(len(f.calls), 1)

    def test_inactive_run_blocks_invocation(self):
        with tempfile.TemporaryDirectory(prefix='continuation-') as temp:
            f = Fixture(temp)
            called = []
            value = f.run(lambda *args: called.append(args) or (0, result()),
                          status=lambda _: {'status': 'stopped_complete',
                                            'stop_reason': 'owner_lost'})
            self.assertEqual(value['status'], 'inactive')
            self.assertEqual(called, [])

    def test_stale_checkpoint_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix='continuation-') as temp:
            f = Fixture(temp)
            continuation._cont(f.root)
            runner._write_json(f.controls / 'continuation/state.json', {
                'kind': continuation.STATE_KIND, 'plan_sha256': '0' * 64,
                'invocations': 0, 'pending': None})
            with self.assertRaises(continuation.ContinuationError):
                f.run(lambda *args: (0, result()))

    def test_unknown_effect_preserves_pending(self):
        with tempfile.TemporaryDirectory(prefix='continuation-') as temp:
            f = Fixture(temp)
            called = []

            def invoke(command, session, prompt):
                called.append((command, session, prompt))
                return 2, {'status': 'unknown_effect',
                           'code': 'native_turn_exit_unknown_effect'}

            value = f.run(invoke)
            self.assertEqual(value['status'], 'unknown_effect')
            state = json.loads((f.controls / 'continuation/state.json').read_text())
            self.assertIsNotNone(state['pending'])
            second = f.run(lambda *args: called.append(args) or (0, result()))
            self.assertEqual(second['status'], 'reconciliation_required')
            self.assertEqual(len(called), 1)

    def test_spend_unavailable_preserves_pending(self):
        with tempfile.TemporaryDirectory(prefix='continuation-') as temp:
            f = Fixture(temp)
            called = []

            def invoke(command, session, prompt):
                called.append((command, session, prompt))
                f.write_next(next_value())
                return 0, {'status': 'acknowledged', 'session_id': 'ses_1',
                           'dispatch_id': 'd' * 32}

            value = f.run(invoke)
            self.assertEqual(value['status'], 'spend_unavailable')
            state = json.loads((f.controls / 'continuation/state.json').read_text())
            self.assertIsNotNone(state['pending'])
            self.assertEqual(f.run(lambda *args: called.append(args) or (0, result()))['status'],
                             'reconciliation_required')
            self.assertEqual(len(called), 1)

    def test_reopen_review_is_consumed_once(self):
        with tempfile.TemporaryDirectory(prefix='continuation-') as temp:
            f = Fixture(temp)

            def first_invoke(command, session, prompt):
                f.calls.append((command, session, prompt))
                f.write_next(next_value(with_next=False, stop=True))
                return 0, result()

            self.assertEqual(f.run(first_invoke)['status'], 'closure_review_required')
            request_path = f.controls / 'continuation/closure-request.json'
            runner._write_json(f.controls / 'continuation/closure-review.json', {
                'kind': continuation.REVIEW_KIND,
                'request_sha256': runner._sha(request_path),
                'decision': 'reopen', 'reason': 'concrete sibling path',
                'test': 'run the sibling check'})
            f.write_next(next_value())

            def expired(command, session, prompt):
                f.calls.append((command, session, prompt))
                return 2, {'status': 'rejected', 'code': 'research_approval_expired'}

            self.assertEqual(f.run(expired)['status'], 'invocation_failed')
            self.assertEqual(f.run(expired)['status'], 'previous_stop')
            self.assertEqual(len(f.calls), 2)

    def test_stale_closure_review_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix='continuation-') as temp:
            f = Fixture(temp)

            def stop_invoke(command, session, prompt):
                f.calls.append((command, session, prompt))
                f.write_next(next_value(with_next=False, stop=True))
                return 0, result()

            self.assertEqual(f.run(stop_invoke)['status'], 'closure_review_required')
            runner._write_json(f.controls / 'continuation/closure-review.json', {
                'kind': continuation.REVIEW_KIND,
                'request_sha256': '0' * 64,
                'decision': 'accept', 'reason': 'stale'})
            with self.assertRaises(continuation.ContinuationError):
                f.run(stop_invoke)
            self.assertEqual(len(f.calls), 1)

    def test_native_research_continue_cli_wires(self):
        with tempfile.TemporaryDirectory(prefix='continuation-') as temp:
            root = Path(temp) / 'run'
            root.mkdir(mode=0o700)
            with patch('native_continuation.continue_run',
                       return_value={'status': 'closed'}) as called, \
                 patch.object(sys, 'argv', ['native_research.py', 'continue',
                                            '--run-root', str(root),
                                            '--max-invocations', '3']), \
                 redirect_stdout(io.StringIO()):
                code = runner.main()
            self.assertEqual(code, 0)
            called.assert_called_once()
            self.assertEqual(called.call_args.kwargs['max_invocations'], 3)
            with patch('native_continuation.continue_run',
                       return_value={'status': 'reconciliation_required'}), \
                 patch.object(sys, 'argv', ['native_research.py', 'continue',
                                            '--run-root', str(root)]), \
                 redirect_stdout(io.StringIO()):
                self.assertEqual(runner.main(), 2)

    def test_strong_lead_abandonment_requires_review(self):
        with tempfile.TemporaryDirectory(prefix='continuation-') as temp:
            f = Fixture(temp)

            def invoke(command, session, prompt):
                f.calls.append((command, session, prompt))
                if command == 'research':
                    f.write_next(next_value(strong=True))
                    return 0, result()
                f.write_next(next_value(strong=False))
                return 0, result(dispatch='e' * 32)

            value = f.run(invoke)
            self.assertEqual([row[0] for row in f.calls], ['research', 'resume'])
            self.assertEqual(value['status'], 'closure_review_required')
            request = json.loads((f.controls / 'continuation/closure-request.json').read_text())
            self.assertEqual(request['reason'], 'strong_lead_abandoned')
            self.assertTrue(request['abandoned_strong_lead'])
            self.assertFalse(request['strong_lead'])

    def test_spend_reset_is_detected(self):
        with tempfile.TemporaryDirectory(prefix='continuation-') as temp:
            f = Fixture(temp)

            def invoke(command, session, prompt):
                f.calls.append((command, session, prompt))
                f.write_next(next_value())
                if command == 'research':
                    return 0, result()
                return 0, {'status': 'acknowledged', 'session_id': 'ses_1',
                           'dispatch_id': 'f' * 32,
                           'pool_after': {'used_tunnels': 0, 'charged_tunnel_bytes': 0,
                                          'active': True}}

            value = f.run(invoke)
            self.assertEqual(value['status'], 'spend_reset_detected')
            state = json.loads((f.controls / 'continuation/state.json').read_text())
            self.assertEqual(state['invocations'], 2)
            self.assertIsNone(state['pending'])
            self.assertEqual(f.run(invoke)['status'], 'previous_stop')
            self.assertEqual(len(f.calls), 2)

    def test_previous_stop_requires_explicit_resume(self):
        with tempfile.TemporaryDirectory(prefix='continuation-') as temp:
            f = Fixture(temp)

            def expired(command, session, prompt):
                f.calls.append((command, session, prompt))
                return 2, {'status': 'rejected', 'code': 'research_approval_expired'}

            self.assertEqual(f.run(expired, maximum=1)['status'], 'invocation_failed')
            self.assertEqual(f.run(expired, maximum=1)['status'], 'previous_stop')
            self.assertEqual(len(f.calls), 1)

            def success(command, session, prompt):
                f.calls.append((command, session, prompt))
                f.write_next(next_value())
                return 0, result()

            self.assertEqual(f.run(success, maximum=1, resume_after_stop=True)['status'],
                             'max_invocations')
            self.assertEqual(len(f.calls), 2)

    def test_reconcile_no_effect_clears_pending(self):
        with tempfile.TemporaryDirectory(prefix='continuation-') as temp:
            f = Fixture(temp)

            def crash(command, session, prompt):
                f.calls.append((command, session, prompt))
                raise RuntimeError('controller crashed after dispatch')

            with self.assertRaises(RuntimeError):
                f.run(crash)
            dispatch_id = 'd' * 32
            (f.controls / 'dispatch').mkdir(mode=0o700)
            runner._write_json(f.controls / 'dispatch' / (dispatch_id + '.json'), {
                'kind': 'native-dispatch-v1', 'dispatch_id': dispatch_id,
                'role': 'researcher', 'status': 'unknown_effect'})
            evidence = (f.root.parent / 'observation.md').resolve()
            evidence.write_text('Observed no target effect after the stopped turn.\n')
            evidence.chmod(0o600)
            value = continuation.reconcile(f.root, dispatch_id=dispatch_id,
                                           decision='no_effect', evidence_file=evidence)
            self.assertEqual(value['status'], 'reconciled')
            state = json.loads((f.controls / 'continuation/state.json').read_text())
            self.assertIsNone(state['pending'])
            calls = []

            def success(command, session, prompt):
                calls.append((command, session, prompt))
                f.write_next(next_value())
                return 0, result()

            self.assertEqual(f.run(success, maximum=1)['status'], 'max_invocations')
            self.assertEqual(len(calls), 1)

    def test_reconcile_effect_observed_stops(self):
        with tempfile.TemporaryDirectory(prefix='continuation-') as temp:
            f = Fixture(temp)

            def crash(command, session, prompt):
                f.calls.append((command, session, prompt))
                raise RuntimeError('controller crashed after dispatch')

            with self.assertRaises(RuntimeError):
                f.run(crash)
            dispatch_id = 'c' * 32
            (f.controls / 'dispatch').mkdir(mode=0o700)
            runner._write_json(f.controls / 'dispatch' / (dispatch_id + '.json'), {
                'kind': 'native-dispatch-v1', 'dispatch_id': dispatch_id,
                'role': 'researcher', 'status': 'unknown_effect'})
            evidence = (f.root.parent / 'observation.md').resolve()
            evidence.write_text('Observed a local effect and stopped.\n')
            evidence.chmod(0o600)
            value = continuation.reconcile(f.root, dispatch_id=dispatch_id,
                                           decision='effect_observed', evidence_file=evidence)
            self.assertEqual(value['status'], 'effect_observed')
            state = json.loads((f.controls / 'continuation/state.json').read_text())
            self.assertIsNone(state['pending'])
            self.assertEqual(state['stop_reason'], 'effect_observed')
            self.assertEqual(f.run(lambda *args: (0, result()))['status'], 'previous_stop')
            with self.assertRaises(continuation.ContinuationError):
                f.run(lambda *args: (0, result()), resume_after_stop=True)

    def test_stop_writes_durable_continuation_stop(self):
        with tempfile.TemporaryDirectory(prefix='continuation-') as temp:
            root = Path(temp) / 'run'
            root.mkdir(mode=0o700)
            controls = root / 'controls'
            controls.mkdir(mode=0o700)
            state = controls / 'native-state'
            state.mkdir(mode=0o700)
            (state / 'RUN.json').write_text('{}')
            class Native:
                def request_stop(self, *_args):
                    return None
            with patch.object(runner, '_activate_controls', return_value=(Native(), None)):
                value = runner.stop(root)
            self.assertEqual(value['status'], 'stop_requested')
            stop = json.loads((controls / 'continuation/STOP').read_text())
            self.assertEqual(stop['kind'], continuation.STOP_KIND)
            self.assertEqual(stop['reason'], 'operator_stop')


if __name__ == '__main__':
    unittest.main()
