#!/usr/bin/env python3
"""Contained #206 public closeout workflow; synthetic owner, no provider or target."""
from __future__ import annotations

import contextlib
from io import StringIO
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
import native_closeout as closeout
import native_continuation as continuation
import native_research as runner
import check_agent_requested_review as source_check


ALLOWANCE = {'active': True, 'run_identity': {'nonce': 'synthetic'},
             'hard_limits': runner.DEFAULT_LIMITS,
             'used_tunnels': 1, 'charged_tunnel_bytes': 100}


def result_text(outcome: str) -> str:
    return ('# Internal result\n\n'
            '## Supported effects\nHost replays produced a harmless note; security effect unproven.\n\n'
            '## Controls\nOriginal actor rights and causal control remain unchecked.\n\n'
            '## Contrary evidence\nThe before batch failed.\n\n'
            '## Tested paths\nOne offline source script and three replays.\n\n'
            '## Untested paths\nOriginal attacker entry and protected state.\n\n'
            '## Assistance\nSynthetic host receipts; no live provider.\n\n'
            '## Unfinished leads\nActor permission and original effect.\n\n'
            '## Limits\nThis is a bounded ' + outcome + ' internal candidate.\n')


def setup(base: Path, *, outcome: str, review: bool = True,
          review_decision: str = 'raise', lead_disposition: bool = True) -> Path:
    root = source_check.fixture(base)
    source_check.source_action(root, '1' * 32, 'before\n', 1)
    source_check.source_action(root, '2' * 32, 'after\n', 0)
    source_check.requested_review(root)
    (root / 'controls/owner.lock').write_text('')
    (root / 'controls/owner.lock').chmod(0o600)
    result = root / 'researcher/project/RESULT.md'
    result.write_text(result_text(outcome))
    if review:
        def fake_review(run_root, packet, pin, role, module):
            evidence = run_root / 'controls/source-evidence' / role / 'RESULTS.json'
            evidence.parent.mkdir(parents=True, mode=0o700)
            runner._write_json(evidence, {'kind': 'synthetic-source-review-evidence-v1',
                                          'input_id': pin['input_id']}, once=True)
            evidence.chmod(0o444)
            assessment = {'status': 'candidate_for_operator_review',
                          'decision': review_decision,
                          'outcome': {'decision': review_decision,
                                      'next_check': 'Compare original actor rights with a denied control',
                                      'lead_dispositions': ([{'decision': 'retain',
                                                             'basis_examined': 'before and after host batches',
                                                             'uncertain_condition': 'original actor permission',
                                                             'next_check': 'check original actor rights'}]
                                                            if lead_disposition else [])}}
            receipt = {'kind': 'native-source-review-v1', 'status': 'reviewed',
                       'assessment': assessment, 'plan_sha256': runner._sha(run_root / 'plan.json'),
                       'input_id': pin['input_id'], 'packet_pin': pin,
                       'material': {'status': 'captured', 'input_id': pin['input_id'],
                                    'outcome': assessment['outcome']},
                       'evidence_path': str(evidence), 'evidence_sha256': runner._sha(evidence),
                       'reviewer_role': role, 'same_original_allowance': True,
                       'allowance_after': ALLOWANCE,
                       'filing_or_escalation_authorized': False}
            runner._write_json(run_root / 'controls/review-reviewer-1.json', receipt, once=True)
            return receipt

        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(runner, '_verified_plan',
                side_effect=lambda run_root, **kw: runner._read_json(run_root / 'plan.json')))
            stack.enter_context(patch.object(runner, '_approval_active'))
            stack.enter_context(patch.object(runner, 'run_active', return_value=True))
            stack.enter_context(patch.object(runner, 'allowance_snapshot', return_value=ALLOWANCE))
            stack.enter_context(patch.object(runner, '_unresolved_dispatches', return_value=[]))
            stack.enter_context(patch.object(runner, '_source_executor_envelope'))
            stack.enter_context(patch.object(runner, '_freeze_source_input',
                side_effect=lambda run_root, destination, role: (
                    shutil.copytree(run_root / 'researcher/project', destination)
                    and runner._inventory(destination))))
            stack.enter_context(patch.object(runner, 'native_api',
                side_effect=lambda *args: {'items': []}))
            stack.enter_context(patch.object(runner, '_source_review', side_effect=fake_review))
            state = continuation._state(root)
            assert continuation._agent_review(root, state, continuation._next(root))['status'] == 'captured'
    state = continuation._state(root)
    state['last_strong_lead'] = True
    continuation._save_state(root, state)
    runner._write_json(root / 'researcher/NEXT.json', {
        'kind': continuation.NEXT_KIND,
        'last_result': {'state': 'supported' if outcome == 'supported' else
                        'blocked' if outcome == 'blocked' else 'refuted',
                        'rules_out': 'only the tested source branch',
                        'unresolved': 'original actor and protected effect'},
        'capabilities': [],
        'coverage': [{'surface': 'offline source branch', 'status': 'tested'},
                     {'surface': 'original attacker entry', 'status': 'untested',
                      'limit': 'actor rights unavailable'}],
        'next': None, 'host_action': None, 'proposed_stop': True,
        'strong_lead': outcome == 'supported'})
    return root


def write_final(root: Path, *, complete: bool = True) -> None:
    controls = root / 'controls'
    resource = {'nonce': 'a' * 32,
                'resources': [{'kind': 'container', 'name': 'synthetic-owner', 'id': 'b' * 64,
                               'role': 'researcher'},
                              {'kind': 'network', 'name': 'synthetic-network', 'id': 'c' * 64,
                               'role': 'transport'}]}
    runner._write_json(controls / 'resources.json', resource)
    cleanup = {'status': 'complete' if complete else 'unresolved',
               'resources': [{'kind': row['kind'], 'name': row['name'], 'absent': complete}
                             for row in reversed(resource['resources'])]}
    runner._write_json(controls / 'cleanup.json', cleanup)
    revoked = controls / 'native-state/REVOKED'
    revoked.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    runner._write_json(revoked, {'kind': 'synthetic-native-revoked-v1',
                                 'ids': [resource['resources'][0]['id']],
                                 'producers_verified_stopped': True})
    snapshot = controls / 'host-snapshot.json'
    runner._write_json(snapshot, {'kind': 'native-research-host-byte-receipt-v1',
                                   'status': 'complete',
                                   'plan_sha256': runner._sha(root / 'plan.json'),
                                   'native_stop': {'revoked_sha256': runner._sha(revoked)}})
    final = {'status': 'stopped_complete' if complete else 'unsafe_or_unresolved',
             'native_stop': {'status': 'stopped'},
             'host_snapshot': {'status': 'complete', 'receipt_path': str(snapshot),
                               'receipt_sha256': runner._sha(snapshot)},
             'origin_stop': {'status': 'not_configured'},
             'origin_cleanup': {'status': 'not_configured'},
             'capture_stop': {'status': 'not_configured'},
             'capture_cleanup': {'status': 'not_configured'},
             'cleanup': cleanup, 'stop_reason': 'operator_stop'}
    runner._write_json(controls / 'final.json', final)


def bridge_cases(base: Path) -> dict:
    """Exercise the public continuation path, including stop priority."""
    observed = {}
    for case, expected in (
        ('accepted', 'complete_internal_candidate'),
        ('agent_turn', 'complete_internal_candidate'),
        ('delayed_cleanup', 'cleanup_pending'),
        ('stale_result', 'review_required'),
        ('user_stop_during_review', 'stopped_incomplete'),
        ('review_reopen', 'complete_internal_candidate'),
        ('reopen_no_revision', 'stopped_incomplete'),
        ('budget_stop', 'stopped_incomplete'),
        ('budget_without_proposal', 'stopped_incomplete'),
        ('user_stop', 'stopped_incomplete'),
        ('unknown_pending', 'stopped_incomplete')):
        root = setup(base / ('bridge_' + case), outcome='supported',
                     review=case not in ('budget_stop', 'user_stop', 'unknown_pending'),
                     review_decision='reopen' if case in ('review_reopen', 'reopen_no_revision')
                     else 'raise')
        proposal = continuation._next(root)
        if case == 'stale_result':
            (root / 'researcher/project/RESULT.md').write_text(
                result_text('supported') + '\nChanged after review.\n')
        if case in ('agent_turn', 'budget_without_proposal', 'user_stop', 'unknown_pending'):
            nxt = dict(proposal)
            nxt['proposed_stop'] = False
            nxt['next'] = {'question': 'What remains?', 'test': 'one local check',
                           'prediction': 'the control holds',
                           'disconfirming': 'the control fails',
                           'authority': 'same signed scope'}
            runner._write_json(root / 'researcher/NEXT.json', nxt)
        if case == 'user_stop':
            runner._write_json(root / 'controls/continuation/STOP',
                               {'kind': continuation.STOP_KIND, 'reason': 'operator_stop'})
        if case == 'unknown_pending':
            state = continuation._state(root)
            state['pending'] = {'role': 'resume', 'session': 'ses_fixture',
                                'started_at': 'synthetic'}
            continuation._save_state(root, state)
        calls = []

        def fake_stop(run_root):
            calls.append('stop')
            if case != 'delayed_cleanup':
                write_final(run_root)
            return {'status': 'stop_requested', 'run_root': str(run_root)}

        def fail_invoke(*_args):
            calls.append('invoke')
            if case == 'agent_turn':
                runner._write_json(root / 'researcher/NEXT.json', proposal)
                return 0, {'status': 'acknowledged', 'session_id': 'ses_fixture',
                    'dispatch_id': 'f' * 32,
                    'pool_before': {'used_tunnels': 0, 'charged_tunnel_bytes': 0,
                                    'active': True},
                    'pool_after': {'used_tunnels': 1, 'charged_tunnel_bytes': 10,
                                   'active': True}}
            if case == 'review_reopen':
                prompt = _args[2]
                if len([item for item in calls if item == 'invoke']) == 1:
                    assert 'Compare original actor rights' in prompt.read_text()
                    (root / 'researcher/project/RESULT.md').write_text(
                        result_text('supported') + '\nThe requested actor check remains inconclusive.\n')
                    (root / 'researcher/RESEARCH.md').write_text(
                        'The requested actor check remains inconclusive; re-review required.\n')
                    nxt = dict(proposal)
                    nxt['proposed_stop'] = False
                    nxt['next'] = None
                    nxt['host_action'] = {'kind': continuation.SOURCE_REVIEW_ACTION_KIND,
                                          'claim': 'Recheck the changed internal result.'}
                    runner._write_json(root / 'researcher/NEXT.json', nxt)
                else:
                    assert 'fresh source review' in prompt.read_text().lower()
                    runner._write_json(root / 'researcher/NEXT.json', proposal)
                return 0, {'status': 'acknowledged', 'session_id': 'ses_fixture',
                    'dispatch_id': ('e' if calls.count('invoke') == 1 else 'd') * 32,
                    'pool_before': {'used_tunnels': 0, 'charged_tunnel_bytes': 0,
                                    'active': True},
                    'pool_after': {'used_tunnels': 1, 'charged_tunnel_bytes': 10,
                                   'active': True}}
            if case == 'reopen_no_revision':
                assert 'Compare original actor rights' in _args[2].read_text()
                return 0, {'status': 'acknowledged', 'session_id': 'ses_fixture',
                    'dispatch_id': 'c' * 32,
                    'pool_before': {'used_tunnels': 0, 'charged_tunnel_bytes': 0,
                                    'active': True},
                    'pool_after': {'used_tunnels': 1, 'charged_tunnel_bytes': 10,
                                   'active': True}}
            raise AssertionError('agent turn after stop proposal')

        def fresh_review(run_root, packet, pin, role, module):
            assert role == 'reviewer-2' and module.verify_packet(packet, pin)
            evidence = run_root / 'controls/source-evidence' / role / 'RESULTS.json'
            evidence.parent.mkdir(parents=True, mode=0o700)
            runner._write_json(evidence, {'kind': 'synthetic-source-review-evidence-v1',
                                          'input_id': pin['input_id']}, once=True)
            evidence.chmod(0o444)
            outcome = {'decision': 'raise', 'next_check': 'No further source check'}
            receipt = {'kind': 'native-source-review-v1', 'status': 'reviewed',
                       'assessment': {'status': 'candidate_for_operator_review',
                                      'decision': 'raise', 'outcome': outcome},
                       'plan_sha256': runner._sha(run_root / 'plan.json'),
                       'input_id': pin['input_id'], 'packet_pin': pin,
                       'material': {'status': 'captured', 'input_id': pin['input_id'],
                                    'outcome': outcome},
                       'evidence_path': str(evidence), 'evidence_sha256': runner._sha(evidence),
                       'reviewer_role': role, 'same_original_allowance': True,
                       'allowance_after': ALLOWANCE,
                       'filing_or_escalation_authorized': False}
            runner._write_json(run_root / 'controls/review-reviewer-2.json', receipt, once=True)
            return receipt

        allowance = dict(ALLOWANCE)
        if case in ('budget_stop', 'budget_without_proposal'):
            allowance['active'] = False
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(runner, '_verified_plan',
                side_effect=lambda run_root, **kw: runner._read_json(run_root / 'plan.json')))
            stack.enter_context(patch.object(runner, '_approval_active'))
            stack.enter_context(patch.object(runner, 'run_active', return_value=True))
            stack.enter_context(patch.object(runner, 'allowance_snapshot', return_value=allowance))
            stack.enter_context(patch.object(runner, '_unresolved_dispatches', return_value=[]))
            stack.enter_context(patch.object(runner, '_docker',
                side_effect=lambda *argv, **kw: subprocess.CompletedProcess(
                    argv, 0, stdout=b'', stderr=b'')))
            stack.enter_context(patch.object(runner, 'stop', side_effect=fake_stop))
            if case == 'user_stop_during_review':
                original_review = closeout._review

                def review_then_stop(*args):
                    outcome = original_review(*args)
                    runner._write_json(root / 'controls/continuation/STOP',
                        {'kind': continuation.STOP_KIND, 'reason': 'operator_stop'})
                    return outcome

                stack.enter_context(patch.object(closeout, '_review',
                    side_effect=review_then_stop))
            if case == 'review_reopen':
                stack.enter_context(patch.object(runner, '_source_executor_envelope'))
                stack.enter_context(patch.object(runner, '_freeze_source_input',
                    side_effect=lambda run_root, destination, role: (
                        shutil.copytree(run_root / 'researcher/project', destination)
                        and runner._inventory(destination))))
                stack.enter_context(patch.object(runner, 'native_api',
                    side_effect=lambda *args: {'items': []}))
                stack.enter_context(patch.object(runner, '_source_review', side_effect=fresh_review))
            response = continuation.continue_run(root, max_invocations=3,
                closeout_wait_seconds=0,
                invoke=fail_invoke, status_fn=lambda _root: {'status': 'active',
                    'allowance': {'active': case != 'budget_without_proposal'}})
        assert response['status'] == expected, (case, response)
        expected_calls = (['invoke', 'stop'] if case == 'agent_turn' else
            ['invoke', 'invoke', 'stop'] if case == 'review_reopen' else
            ['invoke', 'stop'] if case == 'reopen_no_revision' else
            ['stop'] if case in ('accepted', 'delayed_cleanup', 'budget_stop',
            'budget_without_proposal', 'user_stop', 'user_stop_during_review',
            'unknown_pending') else [])
        assert calls == expected_calls, (case, calls)
        if case == 'delayed_cleanup':
            write_final(root)
            with contextlib.ExitStack() as stack:
                stack.enter_context(patch.object(runner, '_verified_plan',
                    side_effect=lambda run_root, **kw: runner._read_json(run_root / 'plan.json')))
                stack.enter_context(patch.object(runner, '_approval_active'))
                stack.enter_context(patch.object(runner, 'run_active', return_value=True))
                stack.enter_context(patch.object(runner, 'allowance_snapshot',
                    return_value=allowance))
                stack.enter_context(patch.object(runner, '_unresolved_dispatches', return_value=[]))
                stack.enter_context(patch.object(runner, '_docker',
                    side_effect=lambda *argv, **kw: subprocess.CompletedProcess(
                        argv, 0, stdout=b'', stderr=b'')))
                stack.enter_context(patch.object(runner, 'stop', side_effect=fake_stop))
                response = continuation.continue_run(root, max_invocations=3,
                    closeout_wait_seconds=0, invoke=fail_invoke,
                    status_fn=lambda _root: {'status': 'active', 'allowance': {'active': True}})
            assert response['status'] == 'complete_internal_candidate', response
            assert calls == ['stop'], calls
        if case in ('accepted', 'review_reopen'):
            record = runner._read_json(Path(response['record_path']))
            assert record['cleanup']['resource_absence'] is True
            assert record['security_effect'] == 'unproven'
            assert record['filing_or_deployment_authorized'] is False
        if case == 'review_reopen':
            records = list((root / 'controls/closeout').glob('reopen-*.json'))
            assert len(records) == 1
            reopened = runner._read_json(records[0])
            assert reopened['proposal'] == proposal
            assert reopened['next_check'].startswith('Compare original actor rights')
            assert (root / 'controls/closeout' /
                    ('RESULT-' + reopened['result_sha256'] + '.md')).is_file()
            assert reopened['review_projection_sha256'] != runner._read_json(
                root / 'controls/continuation/state.json')['review_action']['projection_sha256']
        observed[case] = {'status': response['status'], 'stop_calls': calls.count('stop'),
                          'invocations': response['invocations']}
    return observed


def main() -> None:
    with tempfile.TemporaryDirectory(prefix='agent-closeout-') as temp:
        base = Path(temp).resolve()
        observed = {}
        for case, outcome, review, decision, expected in (
            ('supported', 'supported', True, 'raise', 'complete_internal_candidate'),
            ('bounded_negative', 'bounded_negative', True, 'retain', 'complete_internal_candidate'),
            ('review_reopen', 'supported', True, 'reopen', 'reopen_required'),
            ('stale_result', 'supported', True, 'raise', 'review_required'),
            ('changed_source', 'supported', True, 'raise', 'review_required'),
            ('changed_effect_receipt', 'supported', True, 'raise', 'review_required'),
            ('missing_review', 'supported', False, 'raise', 'review_required'),
            ('dismissed_lead', 'bounded_negative', False, 'raise', 'review_required'),
            ('weak_dismissal', 'bounded_negative', True, 'retain', 'review_required'),
            ('blocked', 'blocked', False, 'raise', 'stopped_incomplete'),
            ('blocked_missing_result', 'blocked', False, 'raise', 'stopped_incomplete'),
            ('unknown_effect', 'supported', True, 'raise', 'stopped_incomplete'),
            ('budget_stop', 'supported', False, 'raise', 'stopped_incomplete'),
            ('user_stop', 'supported', False, 'raise', 'stopped_incomplete'),
            ('failed_cleanup', 'supported', True, 'raise', 'cleanup_unverified'),
            ('remaining_resource', 'supported', True, 'raise', 'cleanup_unverified'),
            ('owner_missing', 'supported', True, 'raise', 'cleanup_pending'),
            ('controller_closed_alone', 'supported', True, 'raise', 'cleanup_pending'),
            ('stop_request_unknown', 'supported', True, 'raise', 'stop_request_unknown'),
            ('missing_result', 'supported', True, 'raise', 'result_invalid'),
            ('malformed_result', 'supported', True, 'raise', 'result_invalid'),
            ('unsafe_result', 'supported', True, 'raise', 'result_invalid'),
            ('target_safety_claim', 'supported', True, 'raise', 'result_invalid')):
            root = setup(base / case, outcome=outcome, review=review,
                         review_decision=decision,
                         lead_disposition=case != 'weak_dismissal')
            if case == 'stale_result':
                (root / 'researcher/project/RESULT.md').write_text(result_text(outcome) +
                    '\nAdditional changed claim.\n')
            if case == 'target_safety_claim':
                (root / 'researcher/project/RESULT.md').write_text(result_text(outcome) +
                    '\nThe target is safe.\n')
            if case == 'missing_result':
                (root / 'researcher/project/RESULT.md').unlink()
            if case == 'malformed_result':
                (root / 'researcher/project/RESULT.md').write_text('# Incomplete result\n')
            if case == 'unsafe_result':
                (root / 'researcher/project/RESULT.md').write_text(result_text(outcome) +
                    '\nfile://synthetic-private-evidence\n')
            if case == 'changed_source':
                (root / 'researcher/project/check.sh').write_text('printf changed\n')
            if case == 'changed_effect_receipt':
                receipt = root / ('controls/source-executions/' + '1' * 32 + '/receipt.json')
                value = runner._read_json(receipt)
                value['runs'][0]['exit_code'] = 0
                runner._write_json(receipt, value)
            if case == 'blocked_missing_result':
                (root / 'researcher/project/RESULT.md').unlink()
            if case == 'controller_closed_alone':
                state = continuation._state(root)
                state['stop_reason'] = 'closed'
                continuation._save_state(root, state)
            if case == 'user_stop':
                runner._write_json(root / 'controls/continuation/STOP',
                                   {'kind': continuation.STOP_KIND, 'reason': 'operator_stop'})
            stop_calls = []

            def fake_stop(run_root):
                stop_calls.append(case)
                if case == 'stop_request_unknown':
                    raise RuntimeError('synthetic_stop_uncertain')
                if case not in ('owner_missing', 'controller_closed_alone'):
                    write_final(run_root, complete=case != 'failed_cleanup')
                return {'status': 'stop_requested', 'run_root': str(run_root)}

            def fake_docker(*argv, **kwargs):
                return subprocess.CompletedProcess(argv, 0,
                    stdout=b'present' if case == 'remaining_resource' else b'', stderr=b'')

            current_allowance = dict(ALLOWANCE)
            if case == 'budget_stop':
                current_allowance['active'] = False
            with contextlib.ExitStack() as stack:
                stack.enter_context(patch.object(runner, '_verified_plan',
                    side_effect=lambda run_root, **kw: runner._read_json(run_root / 'plan.json')))
                stack.enter_context(patch.object(runner, '_approval_active'))
                stack.enter_context(patch.object(runner, 'run_active', return_value=True))
                stack.enter_context(patch.object(runner, 'allowance_snapshot',
                    return_value=current_allowance))
                stack.enter_context(patch.object(runner, '_unresolved_dispatches',
                    return_value=['synthetic unknown'] if case == 'unknown_effect' else []))
                stack.enter_context(patch.object(runner, '_docker', side_effect=fake_docker))
                output = StringIO()
                with contextlib.redirect_stdout(output):
                    code = closeout.main(['--run-root', str(root), '--wait-seconds', '0'],
                                         stop_fn=fake_stop)
            response = json.loads(output.getvalue())
            assert code == 0 and response['status'] == expected, (case, response)
            if case in ('supported', 'bounded_negative'):
                record = runner._read_json(Path(response['record_path']))
                assert record['status'] == 'complete_internal_candidate'
                assert record['cleanup']['resource_absence'] is True
                assert record['security_effect'] == 'unproven'
                assert record['filing_or_deployment_authorized'] is False
                assert len(stop_calls) == 1
            if expected in ('review_required', 'reopen_required', 'result_invalid'):
                assert not stop_calls
            if case == 'review_reopen':
                assert 'original actor rights' in response['next_check']
            if case in ('unknown_effect', 'budget_stop', 'user_stop', 'blocked',
                        'blocked_missing_result'):
                assert len(stop_calls) == 1
            if case in ('failed_cleanup', 'remaining_resource', 'owner_missing',
                        'controller_closed_alone', 'stop_request_unknown'):
                assert len(stop_calls) == 1 and response['status'] != 'complete_internal_candidate'
            observed[case] = {'status': response['status'], 'stop_calls': len(stop_calls),
                              'record_sha256': response.get('record_sha256')}
        observed['continuation_bridge'] = bridge_cases(base)
        print(json.dumps({'status': 'passed', 'cases': observed,
                          'source_sha256': runner._sha(ROOT / 'tools/native_closeout.py'),
                          'continuation_sha256': runner._sha(ROOT / 'tools/native_continuation.py'),
                          'check_sha256': runner._sha(Path(__file__)),
                          'environment': {'platform': platform.system().lower(),
                                          'python': platform.python_version()},
                          'provider_calls': 0, 'target_calls': 0,
                          'native_review': 'synthetic',
                          'native_trace': None,
                          'limits': 'Synthetic owner and Docker readback; no live provider, target, or effect proof.'},
                         sort_keys=True))


if __name__ == '__main__':
    main()
