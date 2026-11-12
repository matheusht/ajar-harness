#!/usr/bin/env python3
"""Contained public continuation crash/restart check; no provider or real target."""
from __future__ import annotations

import contextlib
import json
from pathlib import Path
import platform
import shutil
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
import native_continuation as continuation
import native_research as runner
from check_agent_requested_review import fixture, requested_review, source_action


def run_case(base: Path, case: str) -> dict:
    root = fixture(base / case)
    source_action(root, '1' * 32, 'before\n', 1)
    source_action(root, '2' * 32, 'after\n', 0)
    requested_review(root)
    allowance = {'active': True, 'run_identity': {'nonce': 'synthetic'},
                 'hard_limits': runner.DEFAULT_LIMITS,
                 'used_tunnels': 0, 'charged_tunnel_bytes': 0}
    review_calls, agent_calls = [], []

    def terminal_review(run_root, packet, pin, role, module):
        assert role == 'reviewer-1' and module.verify_packet(packet, pin)
        assert 'before' in (packet / 'CONTRARY.json').read_text()
        review_calls.append(pin['input_id'])
        evidence = run_root / 'controls/source-evidence' / role / 'RESULTS.json'
        evidence.parent.mkdir(parents=True, mode=0o700)
        runner._write_json(evidence, {'kind': 'synthetic-source-review-evidence-v1',
                                      'input_id': pin['input_id']}, once=True)
        evidence.chmod(0o444)
        receipt = {'kind': 'native-source-review-v1', 'status': 'reviewed',
                   'assessment': {'status': 'candidate_for_operator_review'},
                   'plan_sha256': runner._sha(run_root / 'plan.json'),
                   'input_id': pin['input_id'], 'packet_pin': pin,
                   'evidence_path': str(evidence), 'evidence_sha256': runner._sha(evidence),
                   'reviewer_role': role, 'filing_or_escalation_authorized': False}
        runner._write_json(run_root / 'controls/review-reviewer-1.json', receipt, once=True)
        return receipt

    def agent_turn(command, session, prompt):
        assert case in ('adopt', 'no_projection') and command == 'resume' and session == 'ses_fixture'
        projection = next((root / 'controls/research/reviews').glob('*/RESULTS.json'))
        assert projection.parent.name in prompt.read_text()
        assert runner._read_json(projection)['security_effect'] == 'unproven'
        agent_calls.append(command)
        runner._write_json(root / 'researcher/NEXT.json', {
            'kind': continuation.NEXT_KIND,
            'last_result': {'state': 'inconclusive', 'rules_out': 'none',
                            'unresolved': 'Original actor rights remain unchecked'},
            'capabilities': [], 'coverage': [], 'next': None,
            'host_action': None, 'proposed_stop': True, 'strong_lead': True})
        return 0, {'status': 'acknowledged', 'session_id': 'ses_fixture',
                   'dispatch_id': 'a' * 32,
                   'pool_after': {'active': True, 'used_tunnels': 1,
                                  'charged_tunnel_bytes': 1}}

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(runner, '_verified_plan',
            side_effect=lambda run_root, **kw: runner._read_json(run_root / 'plan.json')))
        stack.enter_context(patch.object(runner, '_approval_active'))
        stack.enter_context(patch.object(runner, 'run_active', return_value=True))
        stack.enter_context(patch.object(runner, 'allowance_snapshot', return_value=allowance))
        stack.enter_context(patch.object(runner, '_unresolved_dispatches', return_value=[]))
        stack.enter_context(patch.object(runner, '_source_executor_envelope'))
        stack.enter_context(patch.object(runner, '_freeze_source_input',
            side_effect=lambda run_root, destination, role: (
                shutil.copytree(run_root / 'researcher/project', destination)
                and runner._inventory(destination))))
        stack.enter_context(patch.object(runner, 'native_api',
            side_effect=lambda *args: {'items': []}))
        stack.enter_context(patch.object(runner, '_source_review',
            side_effect=terminal_review))
        if case.startswith('no_projection'):
            original_review = runner.review

            def interrupted_review(*args):
                result = original_review(*args)
                raise RuntimeError('interrupted_after_receipt')

            interruption = patch.object(runner, 'review', side_effect=interrupted_review)
        else:
            original_save = continuation._save_state

            def interrupted_save(run_root, state):
                if (state.get('review_action') or {}).get('phase') == 'captured':
                    raise RuntimeError('interrupted_after_projection')
                original_save(run_root, state)

            interruption = patch.object(continuation, '_save_state',
                                        side_effect=interrupted_save)
        with interruption:
            try:
                continuation.continue_run(root, max_invocations=2,
                    invoke=lambda *args: (_ for _ in ()).throw(AssertionError('agent_called_before_restart')),
                    status_fn=lambda _: {'status': 'active', 'allowance': {'active': True}})
                raise AssertionError('interruption_not_reached')
            except RuntimeError as error:
                assert str(error).startswith('interrupted_after_')
        state = continuation._state(root)
        assert state['review_action']['phase'] == 'dispatched'
        identity = state['review_action']['review_id']
        projection = root / 'controls/research/reviews' / identity / 'RESULTS.json'
        receipt = root / 'controls/review-reviewer-1.json'
        packet = root / 'handoff/reviewer-1'
        mutation = case.removeprefix('no_projection_')
        if mutation == 'changed_projection':
            value = runner._read_json(projection)
            value['unsupported_claim'] = 'confirmed'
            runner._write_json(projection, value)
        elif mutation == 'missing_receipt':
            receipt.unlink()
        elif mutation == 'changed_receipt':
            value = runner._read_json(receipt)
            value['assessment']['status'] = 'unfinished'
            runner._write_json(receipt, value)
        elif mutation == 'missing_packet':
            packet.chmod(0o700)
            (packet / 'RAW.json').unlink()
        elif mutation == 'changed_packet':
            packet.chmod(0o700)
            raw = packet / 'RAW.json'
            raw.chmod(0o600)
            raw.write_bytes(raw.read_bytes() + b' ')
        elif mutation == 'missing_selection':
            (root / 'controls/continuation/reviews' / identity / 'selection.json').unlink()
        elif mutation == 'changed_selection':
            selected = root / 'controls/continuation/reviews' / identity / 'selection.json'
            value = runner._read_json(selected)
            value['claim_version'] = '0' * 64
            runner._write_json(selected, value)
        elif mutation == 'changed_claim':
            value = runner._read_json(root / 'researcher/NEXT.json')
            value['host_action']['claim'] = 'Changed after reviewer dispatch'
            runner._write_json(root / 'researcher/NEXT.json', value)
        elif mutation == 'changed_source':
            (root / 'researcher/project/check.sh').write_text('printf changed\n')
        elif mutation == 'missing_source':
            (root / 'researcher/project/check.sh').unlink()
        elif mutation == 'unfinished_receipt':
            value = runner._read_json(receipt)
            value['status'] = 'unfinished'
            value['assessment']['status'] = 'unfinished'
            runner._write_json(receipt, value)
            if projection.exists():
                projected = runner._read_json(projection)
                projected['status'] = 'unfinished'
                projected['assessment'] = value['assessment']
                projected['receipt_sha256'] = runner._sha(receipt)
                runner._write_json(projection, projected)
        try:
            result = continuation.continue_run(root, max_invocations=2,
                closeout_wait_seconds=0, invoke=agent_turn,
                status_fn=lambda _: {'status': 'active', 'allowance': {'active': True}})
            outcome = result['status']
        except (continuation.ContinuationError, runner.NativeResearchError) as error:
            outcome = 'held:' + str(error)
        assert len(review_calls) == 1
        if case in ('adopt', 'no_projection'):
            assert outcome == 'cleanup_pending' and agent_calls == ['resume'], (outcome, agent_calls)
            assert continuation._state(root)['review_action']['phase'] == 'captured'
            assert len([line for line in (root / 'controls/continuation/events.jsonl').read_text().splitlines()
                        if json.loads(line).get('event') == 'source_review_captured']) == 1
            return {'outcome': outcome, 'review_calls': 1, 'agent_calls': 1,
                    'receipt_sha256': runner._sha(receipt),
                    'projection_sha256': runner._sha(projection)}
        assert outcome == 'review_incomplete' or outcome.startswith('held:')
        assert not agent_calls
        if case.startswith('no_projection'):
            assert not projection.exists()
        return {'outcome': outcome, 'review_calls': 1, 'agent_calls': 0}


def main() -> None:
    with tempfile.TemporaryDirectory(prefix='native-review-crash-adoption-') as temp:
        base = Path(temp).resolve()
        cases = ('adopt', 'no_projection', 'changed_projection', 'missing_receipt',
                 'changed_receipt', 'changed_packet', 'changed_claim', 'changed_source',
                 'unfinished_receipt', 'no_projection_missing_receipt',
                 'no_projection_changed_receipt', 'no_projection_missing_packet',
                 'no_projection_changed_packet', 'no_projection_missing_selection',
                 'no_projection_changed_selection', 'no_projection_changed_claim',
                 'no_projection_missing_source', 'no_projection_changed_source',
                 'no_projection_unfinished_receipt')
        results = {case: run_case(base, case) for case in cases}
    assert not base.exists()
    print(json.dumps({'status': 'passed', 'cases': results,
                      'source_sha256': runner._sha(ROOT / 'tools/native_continuation.py'),
                      'check_sha256': runner._sha(Path(__file__)),
                      'environment': {'python': platform.python_version(),
                                      'platform': platform.system().lower()},
                      'provider_calls': 0, 'target_calls': 0,
                      'cleanup': 'temporary_files_removed'}, sort_keys=True))


if __name__ == '__main__':
    main()
