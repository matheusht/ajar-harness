#!/usr/bin/env python3
"""Join a checked research root to synthetic action, review, and closeout."""

import argparse
import contextlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
import native_continuation as continuation
import native_research as runner
import check_agent_closeout as closeout_check
import check_native_source_action as source_check

TRANSITION = Path(__file__).with_name('check_native_setup_to_research.py')


def main() -> int:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    variants = parser.add_mutually_exclusive_group()
    variants.add_argument('--missing-disposition', action='store_true')
    variants.add_argument('--missing-disposition-continue', action='store_true')
    args = parser.parse_args()
    missing_disposition = args.missing_disposition or args.missing_disposition_continue
    with tempfile.TemporaryDirectory(prefix='native-engagement-joined-') as temporary:
        base = Path(temporary).resolve()
        transition_output = base / 'transition.json'
        transition = subprocess.run(
            [sys.executable, str(TRANSITION), '--output', str(transition_output),
             '--keep-root', str(base / 'transition')], cwd=ROOT,
            env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
            capture_output=True, text=True, timeout=180, check=False)
        if transition.returncode:
            raise AssertionError(('checked transition failed', transition.stderr[-1500:]))
        first = json.loads(transition_output.read_text())
        assert first['passed'] and first['fixture_roots'], first
        root = Path(first['fixture_roots']['research'])
        plan = runner._verified_plan(root)
        assert plan['checked_setup']['kind'] == 'native-checked-setup-transition-v1'
        controls = root / 'controls'
        approval = controls / 'approval.json'
        if not approval.exists():
            shutil.copy2(base / 'transition/research-approval-valid.json', approval)
            approval.chmod(0o600)
        project = root / 'researcher/project'
        (project / 'check.sh').write_text('printf benign-check\\n\n')
        final_fields = {
            'last_result': {'state': 'refuted', 'rules_out': 'only the synthetic source branch',
                            'unresolved': 'original actor entry and protected state'},
            'capabilities': [],
            'coverage': [{'surface': 'synthetic source branch', 'status': 'tested'},
                         {'surface': 'original attacker entry', 'status': 'untested',
                          'limit': 'not supplied in this fixture'}],
            'strong_lead': False}
        action_calls, turns, review_calls, stop_calls = [], [], [], []

        def allowance(_root):
            return {'active': True, 'hard_limits': plan['limits'],
                    'run_identity': {'nonce': 'synthetic-joined'},
                    'used_tunnels': 1 if turns else 0,
                    'charged_tunnel_bytes': 10 * len(turns)}

        def invoke(command, session, prompt):
            turns.append(command)
            if len(turns) == 1:
                assert command == 'research' and prompt is None
                runner._write_json(root / 'researcher/NEXT.json', {
                    **source_check.checkpoint(action=source_check.ACTION), 'strong_lead': True})
            elif len(turns) == 2:
                assert command == 'resume' and prompt is not None
                action_paths = list((controls / 'research/source-actions').glob('*/RESULTS.json'))
                assert len(action_paths) == 1 and action_paths[0].parent.name in prompt.read_text()
                (project / 'RESULT.md').write_text(closeout_check.result_text('bounded_negative'))
                runner._write_json(root / 'researcher/NEXT.json', {
                    'kind': continuation.NEXT_KIND, **final_fields,
                    'next': None, 'proposed_stop': False,
                    'host_action': {'kind': continuation.SOURCE_REVIEW_ACTION_KIND,
                                    'claim': 'The synthetic source branch has no proven security effect.'}})
            elif len(turns) == 3:
                assert command == 'resume' and prompt is not None
                review_paths = list((controls / 'research/reviews').glob('*/RESULTS.json'))
                assert len(review_paths) == 1 and review_paths[0].parent.name in prompt.read_text()
                runner._write_json(root / 'researcher/NEXT.json', {
                    'kind': continuation.NEXT_KIND, **final_fields,
                    'next': (None if args.missing_disposition else {
                        'question': 'Does the denied control remain denied?',
                        'test': 'repeat the local denied-control check',
                        'prediction': 'the control remains denied',
                        'disconfirming': 'the control becomes reachable',
                        'authority': 'same checked approval'}),
                    'proposed_stop': args.missing_disposition, 'host_action': None})
            else:
                assert len(turns) == 4 and command == 'resume' and prompt is not None
                assert continuation._next(root)['next']['test'] == 'repeat the local denied-control check'
                runner._write_json(root / 'researcher/NEXT.json', {
                    'kind': continuation.NEXT_KIND, **final_fields,
                    'next': None, 'proposed_stop': True, 'host_action': None})
            return 0, {'status': 'acknowledged', 'session_id': 'ses_joined_fixture',
                       'dispatch_id': f'{len(turns):032x}',
                       'pool_after': {'used_tunnels': 1,
                                      'charged_tunnel_bytes': 10 * len(turns),
                                      'active': True}}

        def fake_review(run_root, packet, pin, role, module):
            assert module.verify_packet(packet, pin)
            unfinished = json.loads((packet / 'UNFINISHED.json').read_text())
            assert unfinished['checkpoint']['strong_lead'] is False
            review_calls.append(role)
            evidence = controls / 'source-evidence' / role / 'RESULTS.json'
            evidence.parent.mkdir(parents=True, exist_ok=True)
            runner._write_json(evidence, {'kind': 'synthetic-source-review-evidence-v1',
                                          'input_id': pin['input_id']}, once=True)
            evidence.chmod(0o444)
            outcome = {'decision': 'retain', 'next_check': 'Check the original actor entry',
                       'lead_dispositions': ([] if missing_disposition else [{
                           'decision': 'narrow',
                           'basis_examined': 'the captured source check and contrary output',
                           'uncertain_condition': 'original actor entry is still untested',
                           'next_check': 'check original actor rights'}])}
            receipt = {'kind': 'native-source-review-v1', 'status': 'reviewed',
                       'assessment': {'status': 'candidate_for_operator_review',
                                      'decision': 'retain', 'outcome': outcome},
                       'plan_sha256': runner._sha(root / 'plan.json'),
                       'input_id': pin['input_id'], 'packet_pin': pin,
                       'material': {'status': 'captured', 'input_id': pin['input_id'],
                                    'outcome': outcome},
                       'evidence_path': str(evidence), 'evidence_sha256': runner._sha(evidence),
                       'reviewer_role': role, 'same_original_allowance': True,
                       'allowance_after': allowance(root),
                       'filing_or_escalation_authorized': False}
            runner._write_json(controls / ('review-' + role + '.json'), receipt, once=True)
            return receipt

        def fake_stop(run_root):
            stop_calls.append('stop')
            closeout_check.write_final(run_root)
            return {'status': 'stop_requested', 'run_root': str(run_root)}

        def fake_docker(*argv, **kwargs):
            return subprocess.CompletedProcess(
                argv, 0, stdout=(b'synthetic-daemon-A\n' if argv[0] == 'info' else b''),
                stderr=b'')

        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(runner, '_approval_active'))
            stack.enter_context(patch.object(runner, 'run_active', return_value=True))
            stack.enter_context(patch.object(runner, 'allowance_snapshot', side_effect=allowance))
            stack.enter_context(patch.object(runner, '_unresolved_dispatches', return_value=[]))
            stack.enter_context(patch.object(runner, '_freeze_source_input',
                                             side_effect=source_check.fake_freeze))
            stack.enter_context(patch.object(runner, '_source_executor_envelope'))
            stack.enter_context(patch.object(runner, 'source_execute',
                                             side_effect=source_check.fake_execute(action_calls)))
            stack.enter_context(patch.object(runner, 'native_api',
                                             side_effect=lambda *argv: {'items': []}))
            stack.enter_context(patch.object(runner, '_source_review', side_effect=fake_review))
            stack.enter_context(patch.object(runner, 'stop', side_effect=fake_stop))
            stack.enter_context(patch.object(runner, '_docker', side_effect=fake_docker))
            outcome = continuation.continue_run(
                root, max_invocations=3 if missing_disposition else 5,
                closeout_wait_seconds=0, invoke=invoke,
                status_fn=lambda _root: {'status': 'active', 'allowance': {'active': True}})
            if args.missing_disposition_continue:
                assert outcome['status'] == 'closure_review_required', outcome
                request = controls / 'continuation/closure-request.json'
                runner._write_json(controls / 'continuation/closure-review.json', {
                    'kind': continuation.REVIEW_KIND,
                    'request_sha256': runner._sha(request),
                    'decision': 'accept',
                    'reason': 'Bounded stop accepted; original entry remains untested.'}, once=True)
                outcome = continuation.continue_run(
                    root, max_invocations=3, closeout_wait_seconds=0, invoke=invoke,
                    status_fn=lambda _root: {'status': 'active', 'allowance': {'active': True}})
        expected = ('stopped_incomplete' if missing_disposition else
                    'complete_internal_candidate')
        assert outcome['status'] == expected, outcome
        expected_turns = ['research', 'resume', 'resume'] + ([] if missing_disposition else ['resume'])
        assert turns == expected_turns and len(action_calls) == 1, (turns, action_calls)
        assert review_calls == ['reviewer-1']
        assert stop_calls == ['stop'], stop_calls
        assert (controls / 'closeout/stop-request.json').exists()
        assert runner._read_json(controls / 'closeout/result.json')['cleanup']['resource_absence'] is True
        state = continuation._state(root)
        assert state['source_action']['phase'] == 'captured'
        assert state['review_action']['phase'] == 'captured'
        assert (controls / 'closeout/request.json').exists() is not missing_disposition
        assert bool(list((controls / 'closeout').glob('feedback-*.json'))) is args.missing_disposition
        if args.missing_disposition_continue:
            assert runner._read_json(controls / 'continuation/closure-request.json')[
                'reason'] == 'strong_lead_abandoned'
        events = [json.loads(line) for line in
                  (controls / 'continuation/events.jsonl').read_text().splitlines()]
        assert any(row.get('event') == 'source_review_captured' for row in events)
        assert any(row.get('event') == 'closure_request' for row in events) is args.missing_disposition_continue
        assert allowance(root)['charged_tunnel_bytes'] == 10 * len(turns)
        result = {'kind': 'native-engagement-joined-synthetic-e2e-v1', 'status': 'passed',
                  'expected_closeout': expected,
                  'lead_disposition': 'missing' if missing_disposition else 'narrow',
                  'transition_checks': len(first['checks']),
                  'plan_sha256': runner._sha(root / 'plan.json'),
                  'transition_evidence_sha256': runner._sha(transition_output),
                  'source_terminal_sha256': state['source_action']['terminal_sha256'],
                  'review_projection_sha256': state['review_action']['projection_sha256'],
                  'closeout_result_sha256': outcome.get('record_sha256'),
                  'turns': turns, 'source_actions': len(action_calls),
                  'fresh_reviews': len(review_calls), 'owner_stops': len(stop_calls),
                  'allowance_run_identity': allowance(root)['run_identity'],
                  'allowance_used_tunnels': allowance(root)['used_tunnels'],
                  'allowance_charged_tunnel_bytes': allowance(root)['charged_tunnel_bytes'],
                  'event_trace': [{'event': row['event'], 'invocation': row.get('invocation'),
                                   'status': row.get('status')} for row in events],
                  'provider_calls': 0, 'target_service_calls': 0,
                  'environment': {'platform': platform.system().lower(),
                                  'python': platform.python_version()},
                  'scenario_sha256': runner._sha(Path(__file__)),
                  'limits': 'Synthetic native turns, source receipts, reviewer, owner, and cleanup; '
                            'no live provider, target service, or real owner teardown.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'status': result['status'], 'result': str(args.output)}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
