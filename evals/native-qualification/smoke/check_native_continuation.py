#!/usr/bin/env python3
"""Offline continuation CLI smoke check; no provider, Docker, model or target."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch
import contextlib

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
import native_research as runner
import native_continuation as continuation
import check_agent_closeout as closeout_check

FAKE_RUNNER = r'''
import json
from pathlib import Path
import sys

argv = sys.argv[1:]
command = argv[0]
root = Path(argv[argv.index('--run-root') + 1])
runner = Path(__file__).resolve().parent
calls = runner / 'calls.jsonl'
with calls.open('a') as stream:
    stream.write(json.dumps({'command': command}) + '\n')

def write_next(value):
    (root / 'researcher/NEXT.json').write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')

def result(session, dispatch):
    print(json.dumps({'status': 'acknowledged', 'session_id': session,
                      'dispatch_id': dispatch,
                      'pool_before': {'used_tunnels': 0, 'charged_tunnel_bytes': 0,
                                      'active': True},
                      'pool_after': {'used_tunnels': 1, 'charged_tunnel_bytes': 10,
                                     'active': True}}))

if command == 'status':
    print(json.dumps({'status': 'active', 'allowance': {'active': True}}))
elif command == 'research':
    write_next({'kind': 'native-continuation-next-v1',
                'last_result': {'state': 'supported', 'rules_out': 'the first input',
                                'unresolved': 'the second condition'},
                'capabilities': [{'capability': 'observed effect',
                                  'enables': 'the second entry'}],
                'coverage': [{'surface': 'first entry', 'status': 'tested'}],
                'next': {'question': 'does the second entry accept the result?',
                         'test': 'run the second local check',
                         'prediction': 'the second entry accepts it',
                         'disconfirming': 'the second entry rejects it',
                         'authority': 'existing local scope'},
                'proposed_stop': False, 'strong_lead': True})
    result('ses_fake1', 'a' * 32)
elif command == 'resume':
    print(json.dumps({'status': 'rejected',
                      'code': 'resume_session_not_in_researcher_store'}))
    raise SystemExit(2)
elif command == 'reconstruct':
    write_next({'kind': 'native-continuation-next-v1',
                'last_result': {'state': 'blocked', 'rules_out': 'the second entry',
                                'unresolved': 'the remaining trust condition'},
                'capabilities': [{'capability': 'observed effect',
                                  'enables': 'the second entry'}],
                'coverage': [{'surface': 'second entry', 'status': 'blocked',
                              'limit': 'local fixture only'}],
                'next': None, 'proposed_stop': True, 'strong_lead': True})
    result('ses_fake2', 'c' * 32)
else:
    print(json.dumps({'status': 'rejected', 'code': 'unexpected_command'}))
'''


def run_controller(root: Path, fake: Path):
    return continuation.continue_run(root, runner_path=fake,
                                     max_invocations=4, invocation_timeout=60)


def main():
    with tempfile.TemporaryDirectory(prefix='continuation-smoke-') as temp:
        base = Path(temp).resolve()
        root = base / 'run'
        root.mkdir(mode=0o700)
        controls = root / 'controls'
        controls.mkdir(mode=0o700)
        (root / 'researcher').mkdir(mode=0o700)
        runner._write_json(root / 'plan.json', {'kind': 'continuation-smoke'}, once=True)
        fake = base / 'fake_runner.py'
        fake.write_text(FAKE_RUNNER)
        fake.chmod(0o700)

        first = run_controller(root, fake)
        checks = []
        def check(name, condition):
            checks.append({'name': name, 'pass': bool(condition)})
            if not condition:
                raise AssertionError(name)

        calls = [json.loads(line)['command'] for line in
                 (base / 'calls.jsonl').read_text().splitlines()]
        check('first run stopped for closure review',
              first.get('status') == 'closure_review_required')
        check('research, failed resume, reconstruction order',
              calls == ['status', 'research', 'resume', 'reconstruct'])
        check('checkpoint records the reconstruction session',
              json.loads((controls / 'continuation/state.json').read_text())['session_id'] == 'ses_fake2')
        events = [json.loads(line) for line in
                  (controls / 'continuation/events.jsonl').read_text().splitlines()]
        check('failed resume was not counted as a dispatch',
              any(row.get('event') == 'dispatch_not_sent' and row.get('code') ==
                  'resume_session_not_in_researcher_store' for row in events))
        check('closure request was produced',
              (controls / 'continuation/closure-request.json').is_file())

        request = controls / 'continuation/closure-request.json'
        review = controls / 'continuation/closure-review.json'
        runner._write_json(review, {
            'kind': 'native-continuation-closure-review-v1',
            'request_sha256': runner._sha(request),
            'decision': 'accept', 'reason': 'bounded local coverage accepted'})
        next_path = root / 'researcher/NEXT.json'
        original_next = next_path.read_bytes()
        changed = json.loads(original_next)
        changed['last_result']['unresolved'] = 'a newly observed condition'
        runner._write_json(next_path, changed)
        try:
            run_controller(root, fake)
            stale_rejected = False
        except continuation.ContinuationError as error:
            stale_rejected = str(error) == 'continuation_closure_request_stale'
        check('review cannot accept a changed stop proposal', stale_rejected)
        next_path.write_bytes(original_next)
        second = run_controller(root, fake)
        check('accepted closure returns without another invocation',
              second.get('status') == 'closed'
              and [json.loads(line)['command'] for line in
                   (base / 'calls.jsonl').read_text().splitlines()] == calls)
        reopened = base / 'reopened-closure'
        (reopened / 'controls').mkdir(parents=True, mode=0o700)
        reopened.chmod(0o700)
        (reopened / 'researcher').mkdir(mode=0o700)
        runner._write_json(reopened / 'plan.json', {'kind': 'continuation-smoke'}, once=True)
        reopen_state = continuation._state(reopened)
        reopen_state['invocations'] = 1
        continuation._save_state(reopened, reopen_state)
        old_next = {'kind': continuation.NEXT_KIND,
                    'last_result': {'state': 'inconclusive', 'unresolved': 'old condition'},
                    'capabilities': [], 'coverage': [], 'next': None,
                    'proposed_stop': True, 'strong_lead': False}
        runner._write_json(reopened / 'researcher/NEXT.json', old_next)
        continuation._closure_request(reopened, reopen_state, old_next)
        reopen_request = reopened / 'controls/continuation/closure-request.json'
        reopen_review = reopened / 'controls/continuation/closure-review.json'
        runner._write_json(reopen_review, {
            'kind': continuation.REVIEW_KIND,
            'request_sha256': runner._sha(reopen_request),
            'decision': 'reopen', 'reason': 'test another path',
            'test': 'check the new condition'}, once=True)
        reopen_state['applied_closure_review_sha256'] = runner._sha(reopen_review)
        reopen_state['stop_reason'] = None
        continuation._save_state(reopened, reopen_state)
        runner._write_json(reopened / 'researcher/NEXT.json', {
            **old_next, 'proposed_stop': False,
            'next': {'question': 'is the new path reachable?', 'test': 'check the new condition',
                     'prediction': 'reachable', 'disconfirming': 'denied',
                     'authority': 'same approval'}})
        try:
            reopened_outcome = continuation.continue_run(
                reopened, runner_path=fake, max_invocations=1)
        except continuation.ContinuationError:
            reopened_outcome = None
        check('applied reopen permits a new next brief',
              reopened_outcome is not None
              and reopened_outcome['status'] == 'max_invocations')
        manual = base / 'manual-dismissal'
        (manual / 'controls').mkdir(parents=True, mode=0o700)
        manual.chmod(0o700)
        (manual / 'researcher').mkdir(mode=0o700)
        runner._write_json(manual / 'plan.json', {'kind': 'continuation-smoke'}, once=True)
        manual_state = continuation._state(manual)
        manual_state.update(invocations=1, last_strong_lead=True)
        continuation._save_state(manual, manual_state)
        runner._write_json(manual / 'researcher/NEXT.json', {
            'kind': continuation.NEXT_KIND,
            'last_result': {'state': 'refuted', 'unresolved': 'the prior lead'},
            'capabilities': [], 'coverage': [], 'next': None,
            'host_action': {'kind': continuation.SOURCE_REVIEW_ACTION_KIND,
                            'claim': 'Review the dismissed lead'},
            'proposed_stop': False, 'strong_lead': False})
        manual_outcome = run_controller(manual, fake)
        check('manual dismissal still requires legacy closure review',
              manual_outcome['status'] == 'closure_review_required'
              and runner._read_json(manual / 'controls/continuation/closure-request.json')
                  ['reason'] == 'strong_lead_abandoned')
        legacy = base / 'legacy-source-closure'
        (legacy / 'controls').mkdir(parents=True, mode=0o700)
        legacy.chmod(0o700)
        (legacy / 'researcher').mkdir(mode=0o700)
        runner._write_json(legacy / 'plan.json', {
            'kind': 'continuation-smoke', 'source_only': {'build_command': ['true']}}, once=True)
        legacy_state = continuation._state(legacy)
        legacy_state['invocations'] = 1
        continuation._save_state(legacy, legacy_state)
        legacy_next = {'kind': continuation.NEXT_KIND,
                       'last_result': {'state': 'refuted', 'unresolved': 'bounded negative'},
                       'capabilities': [], 'coverage': [], 'next': None,
                       'proposed_stop': True, 'strong_lead': False}
        runner._write_json(legacy / 'researcher/NEXT.json', legacy_next)
        continuation._closure_request(legacy, legacy_state, legacy_next)
        legacy_request = legacy / 'controls/continuation/closure-request.json'
        runner._write_json(legacy / 'controls/continuation/closure-review.json', {
            'kind': continuation.REVIEW_KIND, 'request_sha256': runner._sha(legacy_request),
            'decision': 'accept', 'reason': 'legacy bounded closeout accepted'})
        legacy_outcome = run_controller(legacy, fake)
        check('legacy source-only closure uses accepted manual review',
              legacy_outcome['status'] == 'closed'
              and [json.loads(line)['command'] for line in
                   (base / 'calls.jsonl').read_text().splitlines()] == calls)
        patch_root = base / 'patch-dismissal'
        (patch_root / 'controls').mkdir(parents=True, mode=0o700)
        patch_root.chmod(0o700)
        (patch_root / 'researcher').mkdir(mode=0o700)
        runner._write_json(patch_root / 'plan.json', {
            'kind': 'continuation-smoke', 'checked_setup': {'synthetic': True}}, once=True)
        patch_state = continuation._state(patch_root)
        patch_state.update(invocations=1, last_strong_lead=True)
        continuation._save_state(patch_root, patch_state)
        runner._write_json(patch_root / 'researcher/NEXT.json', {
            'kind': continuation.NEXT_KIND,
            'last_result': {'state': 'supported', 'unresolved': 'the prior lead'},
            'capabilities': [], 'coverage': [], 'next': None,
            'host_action': {'kind': continuation.SOURCE_PATCH_ACTION_KIND,
                            'claim': 'Check the proposed fix and lead disposition'},
            'proposed_stop': False, 'strong_lead': False})
        with patch.object(continuation, '_agent_review', return_value={
                'status': 'review_incomplete', 'review_id': 'synthetic'}) as reviewed:
            patch_outcome = run_controller(patch_root, fake)
        check('checked patch dismissal reaches independent review',
              patch_outcome['status'] == 'review_incomplete'
              and reviewed.call_count == 1
              and not (patch_root / 'controls/continuation/closure-request.json').exists())
        checked = base / 'checked-closure'
        (checked / 'controls').mkdir(parents=True, mode=0o700)
        checked.chmod(0o700)
        (checked / 'researcher').mkdir(mode=0o700)
        runner._write_json(checked / 'plan.json', {
            'kind': 'continuation-smoke', 'source_only': {'synthetic': True},
            'checked_setup': {'synthetic': True}}, once=True)
        checked_state = continuation._state(checked)
        checked_state.update(invocations=1, last_strong_lead=True)
        continuation._save_state(checked, checked_state)
        checked_next = {
            'kind': continuation.NEXT_KIND,
            'last_result': {'state': 'refuted', 'unresolved': 'original entry'},
            'capabilities': [], 'coverage': [], 'next': None,
            'host_action': {'kind': continuation.SOURCE_REVIEW_ACTION_KIND,
                            'claim': 'Review the bounded stop'},
            'proposed_stop': False, 'strong_lead': False}
        runner._write_json(checked / 'researcher/NEXT.json', checked_next)
        continuation._closure_request(checked, checked_state, checked_next,
                                      reason='strong_lead_abandoned')
        checked_request = checked / 'controls/continuation/closure-request.json'
        runner._write_json(checked / 'controls/continuation/closure-review.json', {
            'kind': continuation.REVIEW_KIND,
            'request_sha256': runner._sha(checked_request),
            'decision': 'accept', 'reason': 'bounded stop accepted'}, once=True)
        (checked / 'controls/owner.lock').write_text('')
        (checked / 'controls/owner.lock').chmod(0o600)
        stops = []
        def fake_stop(run_root):
            stops.append('stop')
            closeout_check.write_final(run_root)
            return {'status': 'stop_requested'}
        def fake_docker(*argv, **_kwargs):
            return subprocess.CompletedProcess(
                argv, 0, stdout=(b'synthetic-daemon-A\n' if argv[0] == 'info' else b''),
                stderr=b'')
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(runner, '_verified_plan',
                side_effect=lambda run_root, **_kw: runner._read_json(run_root / 'plan.json')))
            stack.enter_context(patch.object(runner, '_unresolved_dispatches', return_value=[]))
            stack.enter_context(patch.object(runner, 'stop', side_effect=fake_stop))
            stack.enter_context(patch.object(runner, '_docker', side_effect=fake_docker))
            checked_outcome = run_controller(checked, fake)
        check('accepted checked closure uses owner stop and cleanup path',
              checked_outcome['status'] == 'stopped_incomplete'
              and checked_outcome['cleanup']['resource_absence'] is True
              and stops == ['stop']
              and runner._read_json(checked / 'controls/closeout/result.json')['reason']
                  == 'manual_closure_accepted')
        legacy_stop = base / 'legacy-forced-stop'
        (legacy_stop / 'controls/continuation').mkdir(parents=True, mode=0o700)
        legacy_stop.chmod(0o700)
        (legacy_stop / 'researcher').mkdir(mode=0o700)
        runner._write_json(legacy_stop / 'plan.json', {
            'kind': 'continuation-smoke', 'source_only': {'synthetic': True}}, once=True)
        runner._write_json(legacy_stop / 'controls/continuation/STOP', {
            'kind': continuation.STOP_KIND, 'reason': 'operator_stop'}, once=True)
        (legacy_stop / 'controls/owner.lock').write_text('')
        (legacy_stop / 'controls/owner.lock').chmod(0o600)
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(runner, '_verified_plan',
                side_effect=lambda run_root, **_kw: runner._read_json(run_root / 'plan.json')))
            stack.enter_context(patch.object(runner, '_unresolved_dispatches', return_value=[]))
            stack.enter_context(patch.object(runner, 'stop', side_effect=fake_stop))
            stack.enter_context(patch.object(runner, '_docker', side_effect=fake_docker))
            legacy_stop_outcome = run_controller(legacy_stop, fake)
        check('legacy forced stop still checks owner cleanup',
              legacy_stop_outcome['status'] == 'stopped_incomplete'
              and legacy_stop_outcome['cleanup']['resource_absence'] is True
              and stops == ['stop', 'stop'])
        print(json.dumps({'checks': checks, 'status': 'passed',
                          'limits': 'Synthetic subprocess, owner stop, and Docker readback; '
                                    'no native model, provider, Docker daemon, or target.'},
                         indent=2))
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
