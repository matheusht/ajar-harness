#!/usr/bin/env python3
"""Contained #205 request-to-packet-to-readback check; no provider or target."""
from __future__ import annotations

import contextlib
import hashlib
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


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def fixture(base: Path) -> Path:
    root = base / 'run'
    for name in ('controls/continuation/source-actions', 'controls/source-executions',
                 'controls/research', 'controls/experiments/native-review-qualification',
                 'researcher/project', 'handoff/reviewer-1', 'handoff/reviewer-2',
                 'reviewer-1/project', 'reviewer-2/project'):
        (root / name).mkdir(parents=True, mode=0o700)
    root.chmod(0o700)
    (root / 'researcher/project/check.sh').write_text('printf after\\n')
    shutil.copytree(root / 'researcher/project', root / 'original')
    for role in ('reviewer-1', 'reviewer-2'):
        shutil.copy2(root / 'original/check.sh', root / role / 'project/check.sh')
    shutil.copy2(ROOT / 'experiments/native-review-qualification/fresh_review.py',
                 root / 'controls/experiments/native-review-qualification/fresh_review.py')
    source = runner._inventory(root / 'original')
    runner._write_json(root / 'plan.json', {
        'kind': 'native-research-plan-v1', 'source_only': {'module_cache_sha256': digest(b'{}')},
        'source_effect_envelope': runner.SOURCE_EFFECT_ENVELOPE,
        'scope_sha256': 'a' * 64, 'limits': runner.DEFAULT_LIMITS,
        'source_sha256': source,
        'source_manifest_sha256': digest(json.dumps(source, sort_keys=True).encode()),
        'target_image_id': 'synthetic', 'platform': 'linux/arm64'})
    runner._write_json(root / 'controls/approval.json', {'kind': 'synthetic-approval'})
    (root / 'researcher/RESEARCH.md').write_text('One failed before check; after branch remains unfinished.\n')
    (root / 'researcher/RESEARCH.md').chmod(0o600)
    for directory in (root, *(path for path in root.rglob('*') if path.is_dir())):
        directory.chmod(0o700)
    return root


def source_action(root: Path, identity: str, output: str, exit_code: int) -> None:
    controls = root / 'controls'
    action = controls / 'continuation/source-actions' / identity
    execution = controls / 'source-executions' / identity
    action.mkdir(mode=0o700)
    execution.mkdir(mode=0o700)
    shutil.copytree(root / 'original', action / 'input')
    shutil.copytree(action / 'input', execution / 'input')
    inventory = runner._inventory(action / 'input')
    runner._write_json(action / 'command.json', ['sh', 'check.sh'])
    runner._write_json(action / 'input-manifest.json', inventory)
    runner._write_json(execution / 'input-manifest.json', inventory)
    request = {'kind': continuation.SOURCE_REQUEST_KIND, 'action_id': identity,
               'next_sha256': 'b' * 64, 'plan_sha256': runner._sha(root / 'plan.json'),
               'scope_sha256': runner._plan(root)['scope_sha256'],
               'approval_sha256': runner._sha(controls / 'approval.json'),
               'command_sha256': runner._sha(action / 'command.json'),
               'input_manifest_sha256': runner._sha(action / 'input-manifest.json'),
               'allowance_before': {'active': True, 'run_identity': {'nonce': 'synthetic'},
                                    'used_tunnels': 0, 'charged_tunnel_bytes': 0}}
    runner._write_json(action / 'request.json', request)
    receipt = {'kind': 'native-source-execution-v1', 'status': 'captured',
               'execution_id': identity, 'owner_role': 'researcher',
               'plan_sha256': request['plan_sha256'],
               'original_source_manifest_sha256': runner._plan(root)['source_manifest_sha256'],
               'module_cache_sha256': runner._plan(root)['source_only']['module_cache_sha256'],
               'image_id': 'synthetic', 'platform': 'linux/arm64', 'network': 'none',
               'command': ['sh', 'check.sh'],
               'input_manifest_sha256': request['input_manifest_sha256'],
               'assessment': 'needs_review', 'replay_output_equal': True,
               'all_commands_succeeded': exit_code == 0, 'runs': []}
    for role in runner.CAPTURE_TARGETS:
        folder = execution / role
        folder.mkdir()
        shutil.copytree(action / 'input', folder / 'files')
        runner._write_json(folder / 'files.json', inventory)
        (folder / 'stdout.txt').write_text(output)
        (folder / 'stderr.txt').write_text('')
        (folder / 'stdout.txt').chmod(0o600)
        (folder / 'stderr.txt').chmod(0o600)
        receipt['runs'].append({'role': role, 'exit_code': exit_code,
                                'stdout_sha256': runner._sha(folder / 'stdout.txt'),
                                'stderr_sha256': runner._sha(folder / 'stderr.txt'),
                                'output_manifest_sha256': runner._sha(folder / 'files.json')})
    runner._write_json(execution / 'receipt.json', receipt)
    projection = continuation._source_projection(root, request, execution / 'receipt.json', receipt)
    projected = controls / 'research/source-actions' / identity
    projected.mkdir(parents=True)
    runner._write_json(projected / 'RESULTS.json', projection)
    runner._write_json(action / 'terminal.json', {
        'kind': continuation.SOURCE_TERMINAL_KIND, 'status': 'captured',
        'action_id': identity, 'request_sha256': runner._sha(action / 'request.json'),
        'source_receipt_sha256': runner._sha(execution / 'receipt.json'),
        'projection_sha256': runner._sha(projected / 'RESULTS.json'),
        'allowance_before': request['allowance_before'],
        'assessment': 'needs_review', 'security_effect': 'unproven'})
    continuation._event(root, {'at': continuation._now(), 'event': 'source_action_captured',
                               'action_id': identity,
                               'terminal_sha256': runner._sha(action / 'terminal.json')})


def rebind_output(root: Path, identity: str, *, unsafe: bool = False,
                  withheld: bool = False) -> None:
    action = root / 'controls/continuation/source-actions' / identity
    execution = root / 'controls/source-executions' / identity
    receipt_path = execution / 'receipt.json'
    receipt = runner._read_json(receipt_path)
    first = receipt['runs'][0]
    stream = execution / first['role'] / 'stdout.txt'
    if unsafe:
        stream.write_text('file://synthetic-private-evidence\n')
        first['stdout_sha256'] = runner._sha(stream)
    if withheld:
        stream.unlink()
        first['stdout_redacted'] = True
    receipt['replay_output_equal'] = False
    runner._write_json(receipt_path, receipt)
    request = runner._read_json(action / 'request.json')
    projected = root / 'controls/research/source-actions' / identity / 'RESULTS.json'
    runner._write_json(projected,
                       continuation._source_projection(root, request, receipt_path, receipt))
    terminal_path = action / 'terminal.json'
    terminal = runner._read_json(terminal_path)
    terminal['source_receipt_sha256'] = runner._sha(receipt_path)
    terminal['projection_sha256'] = runner._sha(projected)
    runner._write_json(terminal_path, terminal)
    journal = root / 'controls/continuation/events.jsonl'
    rows = [json.loads(line) for line in journal.read_text().splitlines()]
    for row in rows:
        if row.get('event') == 'source_action_captured' and row.get('action_id') == identity:
            row['terminal_sha256'] = runner._sha(terminal_path)
    journal.write_text(''.join(json.dumps(row, sort_keys=True) + '\n' for row in rows))


def requested_review(root: Path) -> None:
    (root / 'researcher/project/RESULT.md').write_text(
        'Agent candidate: after branch; original actor rights remain unknown.\n')
    runner._write_json(root / 'researcher/NEXT.json', {
        'kind': continuation.NEXT_KIND,
        'last_result': {'state': 'inconclusive', 'rules_out': 'none',
                        'unresolved': 'Original attacker rights and causal control remain unchecked'},
        'capabilities': [], 'coverage': [], 'next': None,
        'host_action': {'kind': 'native-source-review-v1',
                        'claim': 'The after branch may preserve the harmless note.'},
        'proposed_stop': False, 'strong_lead': True})
    state = continuation._state(root)
    state.update(invocations=1, session_id='ses_fixture',
                 source_action={'action_id': '2' * 32, 'phase': 'captured',
                                'terminal_sha256': runner._sha(root / ('controls/continuation/source-actions/'
                                    + '2' * 32 + '/terminal.json')),
                                'after_invocations': 0})
    continuation._save_state(root, state)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix='agent-requested-review-') as temp:
        base = Path(temp).resolve()
        root = fixture(base / 'happy')
        source_action(root, '1' * 32, 'before\n', 1)
        source_action(root, '2' * 32, 'after\n', 0)
        requested_review(root)
        calls = []

        def fake_source_review(run_root, packet, pin, role, module):
            assert role == 'reviewer-1' and module.verify_packet(packet, pin)
            raw = (packet / 'RAW.json').read_text()
            contrary = (packet / 'CONTRARY.json').read_text()
            unfinished = (packet / 'UNFINISHED.json').read_text()
            assert '1' * 32 in raw and '2' * 32 in raw and 'before' in raw and 'after' in raw
            assert 'before' in contrary and 'causal control' in unfinished
            result_note = json.loads((packet / 'UNFINISHED.json').read_text())['result_note']
            assert result_note['provenance'] == 'agent_statement_frozen_source'
            assert result_note['sha256'] == runner._sha(root / 'researcher/project/RESULT.md')
            calls.append(pin['input_id'])
            receipt = {'kind': 'native-source-review-v1', 'status': 'reviewed',
                       'assessment': {'status': 'candidate_for_operator_review'},
                       'plan_sha256': runner._sha(run_root / 'plan.json'),
                       'input_id': pin['input_id'], 'packet_pin': pin,
                       'reviewer_role': role, 'filing_or_escalation_authorized': False}
            runner._write_json(run_root / 'controls/review-reviewer-1.json', receipt, once=True)
            return receipt

        def invoke(command, session, prompt):
            assert command == 'resume' and session == 'ses_fixture'
            projected = list((root / 'controls/research/reviews').glob('*/RESULTS.json'))
            assert len(projected) == 1 and str(projected[0].parent.name) in prompt.read_text()
            assert runner._read_json(projected[0])['security_effect'] == 'unproven'
            runner._write_json(root / 'researcher/NEXT.json', {
                'kind': continuation.NEXT_KIND,
                'last_result': {'state': 'inconclusive', 'rules_out': 'none',
                                'unresolved': 'Original attacker rights remain unchecked'},
                'capabilities': [], 'coverage': [], 'next': None,
                'host_action': None, 'proposed_stop': True, 'strong_lead': True})
            return 0, {'status': 'acknowledged', 'session_id': 'ses_fixture',
                       'dispatch_id': 'a' * 32,
                       'pool_after': {'active': True, 'used_tunnels': 1,
                                      'charged_tunnel_bytes': 1}}

        allowance = {'active': True, 'run_identity': {'nonce': 'synthetic'},
                     'hard_limits': runner.DEFAULT_LIMITS,
                     'used_tunnels': 0, 'charged_tunnel_bytes': 0}
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
                side_effect=fake_source_review))
            result = continuation.continue_run(root, max_invocations=2, invoke=invoke,
                status_fn=lambda _: {'status': 'active', 'allowance': {'active': True}})
        assert result['status'] == 'closure_review_required' and len(calls) == 1
        denied = []
        for case in ('malformed_claim', 'expired_approval', 'exhausted_allowance',
                     'uncertain_prior_action', 'reused_slot', 'reused_store',
                     'changed_source', 'changed_adverse_receipt', 'unsafe_output',
                     'withheld_output', 'unfinished_source_action', 'missing_notes',
                     'symlink_notes'):
            blocked = fixture(base / case)
            source_action(blocked, '1' * 32, 'before\n', 1)
            source_action(blocked, '2' * 32, 'after\n', 0)
            requested_review(blocked)
            if case == 'malformed_claim':
                next_value = runner._read_json(blocked / 'researcher/NEXT.json')
                next_value['host_action']['claim'] = 'A' * 5000
                runner._write_json(blocked / 'researcher/NEXT.json', next_value)
            elif case == 'reused_slot':
                (blocked / 'handoff/reviewer-1/OLD.txt').write_text('used')
                (blocked / 'handoff/reviewer-2/OLD.txt').write_text('used')
            elif case == 'changed_source':
                (blocked / 'original/check.sh').write_text('printf changed\\n')
            elif case == 'changed_adverse_receipt':
                path = blocked / ('controls/source-executions/' + '1' * 32 + '/receipt.json')
                receipt = runner._read_json(path)
                receipt['runs'][0]['exit_code'] = 0
                runner._write_json(path, receipt)
            elif case == 'unsafe_output':
                rebind_output(blocked, '1' * 32, unsafe=True)
            elif case == 'withheld_output':
                rebind_output(blocked, '1' * 32, withheld=True)
            elif case == 'unfinished_source_action':
                (blocked / ('controls/continuation/source-actions/' + '3' * 32)).mkdir(mode=0o700)
            elif case == 'missing_notes':
                (blocked / 'researcher/RESEARCH.md').unlink()
            elif case == 'symlink_notes':
                note = blocked / 'researcher/RESEARCH.md'
                note.unlink()
                note.symlink_to(blocked / 'original/check.sh')
            blocked_allowance = dict(allowance)
            if case == 'exhausted_allowance':
                blocked_allowance['used_tunnels'] = runner.DEFAULT_LIMITS['max_connections']
            blocked_calls = []
            with contextlib.ExitStack() as stack:
                stack.enter_context(patch.object(runner, '_verified_plan',
                    side_effect=lambda run_root, **kw: runner._read_json(run_root / 'plan.json')))
                stack.enter_context(patch.object(runner, '_approval_active',
                    side_effect=(runner.NativeResearchError('research_approval_expired')
                                 if case == 'expired_approval' else None)))
                stack.enter_context(patch.object(runner, 'run_active', return_value=True))
                stack.enter_context(patch.object(runner, 'allowance_snapshot',
                    return_value=blocked_allowance))
                stack.enter_context(patch.object(runner, '_unresolved_dispatches',
                    return_value=['unknown'] if case == 'uncertain_prior_action' else []))
                stack.enter_context(patch.object(runner, '_source_executor_envelope'))
                stack.enter_context(patch.object(runner, '_freeze_source_input',
                    side_effect=lambda run_root, destination, role: (
                        shutil.copytree(run_root / 'researcher/project', destination)
                        and runner._inventory(destination))))
                stack.enter_context(patch.object(runner, 'native_api',
                    side_effect=lambda *args: ({'items': [{'id': 'ses_existing'}]}
                        if case == 'reused_store' else {'items': []})))
                stack.enter_context(patch.object(runner, '_source_review',
                    side_effect=lambda *args: blocked_calls.append('review')))
                try:
                    outcome = continuation.continue_run(blocked, max_invocations=2,
                        invoke=lambda *args: blocked_calls.append('research'),
                        status_fn=lambda _: {'status': 'active', 'allowance': {'active': True}})
                    assert outcome['status'] in ('review_incomplete', 'review_unavailable')
                except (runner.NativeResearchError, continuation.ContinuationError,
                        ValueError, RuntimeError):
                    pass
            assert blocked_calls == [] and not list((blocked / 'handoff/reviewer-1').glob('REQUEST.json'))
            assert not list((blocked / 'handoff/reviewer-2').glob('REQUEST.json'))
            if case != 'malformed_claim':
                incomplete = list((blocked / 'controls/continuation').glob('review-incomplete-*.json'))
                assert len(incomplete) == 1 and runner._read_json(incomplete[0])['reason']
            denied.append(case)
        post_dispatch = []
        for case in ('reviewer_unknown', 'reviewer_unfinished', 'packet_changed'):
            blocked = fixture(base / case)
            source_action(blocked, '1' * 32, 'before\n', 1)
            source_action(blocked, '2' * 32, 'after\n', 0)
            requested_review(blocked)
            review_calls = []

            def disrupted_review(run_root, packet, pin, role, module):
                review_calls.append(case)
                if case == 'reviewer_unknown':
                    raise RuntimeError('synthetic_dispatch_unknown')
                receipt = {'kind': 'native-source-review-v1', 'status': 'unfinished'
                           if case == 'reviewer_unfinished' else 'reviewed',
                           'assessment': {'status': 'unfinished'
                                          if case == 'reviewer_unfinished'
                                          else 'candidate_for_operator_review'},
                           'plan_sha256': runner._sha(run_root / 'plan.json'),
                           'input_id': pin['input_id'], 'packet_pin': pin,
                           'reviewer_role': role, 'filing_or_escalation_authorized': False}
                runner._write_json(run_root / 'controls/review-reviewer-1.json', receipt, once=True)
                if case == 'packet_changed':
                    raw = packet / 'RAW.json'
                    raw.chmod(0o644)
                    raw.write_bytes(raw.read_bytes() + b' ')
                return receipt

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
                    side_effect=disrupted_review))
                try:
                    outcome = continuation.continue_run(blocked, max_invocations=2,
                        invoke=lambda *args: (_ for _ in ()).throw(AssertionError('readback_sent')),
                        status_fn=lambda _: {'status': 'active', 'allowance': {'active': True}})
                    assert outcome['status'] == 'review_incomplete' and case == 'reviewer_unfinished'
                except (RuntimeError, continuation.ContinuationError):
                    assert case != 'reviewer_unfinished'
                repeated = continuation.continue_run(blocked, max_invocations=2,
                    invoke=lambda *args: (_ for _ in ()).throw(AssertionError('duplicate_sent')),
                    status_fn=lambda _: {'status': 'active', 'allowance': {'active': True}})
            assert repeated['status'] == 'review_incomplete' and len(review_calls) == 1
            post_dispatch.append(case)
        cached_readback_denied = []
        for case in ('missing_receipt', 'changed_receipt', 'missing_packet',
                     'changed_packet', 'changed_selection', 'changed_source_action',
                     'missing_reviewer_evidence', 'changed_reviewer_evidence'):
            blocked = fixture(base / ('cached-' + case))
            source_action(blocked, '1' * 32, 'before\n', 1)
            source_action(blocked, '2' * 32, 'after\n', 0)
            requested_review(blocked)
            review_calls = []

            def cached_review(run_root, packet, pin, role, module):
                review_calls.append(case)
                evidence = run_root / 'controls/source-evidence' / role / 'RESULTS.json'
                evidence.parent.mkdir(parents=True, mode=0o700)
                runner._write_json(evidence, {'kind': 'synthetic-source-review-evidence-v1',
                                              'input_id': pin['input_id']}, once=True)
                evidence.chmod(0o444)
                receipt = {'kind': 'native-source-review-v1', 'status': 'reviewed',
                           'assessment': {'status': 'candidate_for_operator_review'},
                           'plan_sha256': runner._sha(run_root / 'plan.json'),
                           'input_id': pin['input_id'], 'packet_pin': pin,
                           'evidence_path': str(evidence),
                           'evidence_sha256': runner._sha(evidence),
                           'reviewer_role': role, 'filing_or_escalation_authorized': False}
                runner._write_json(run_root / 'controls/review-reviewer-1.json', receipt, once=True)
                return receipt

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
                    side_effect=cached_review))
                state = continuation._state(blocked)
                first = continuation._agent_review(blocked, state, continuation._next(blocked))
                assert first['status'] == 'captured' and len(review_calls) == 1
                cached = continuation._agent_review(blocked, state, continuation._next(blocked))
                assert cached['status'] == 'captured' and len(review_calls) == 1
                review_id = first['review_id']
                receipt_path = blocked / 'controls/review-reviewer-1.json'
                packet = blocked / 'handoff/reviewer-1'
                if case == 'missing_receipt':
                    receipt_path.unlink()
                elif case == 'changed_receipt':
                    receipt = runner._read_json(receipt_path)
                    receipt['assessment']['status'] = 'unfinished'
                    runner._write_json(receipt_path, receipt)
                elif case == 'missing_packet':
                    packet.chmod(0o755)
                    (packet / 'RAW.json').unlink()
                elif case == 'changed_packet':
                    raw = packet / 'RAW.json'
                    raw.chmod(0o644)
                    raw.write_bytes(raw.read_bytes() + b' ')
                elif case == 'changed_selection':
                    selection = blocked / 'controls/continuation/reviews' / review_id / 'selection.json'
                    value = runner._read_json(selection)
                    value['claim_version'] = '0' * 64
                    runner._write_json(selection, value)
                elif case == 'changed_source_action':
                    stream = blocked / ('controls/source-executions/' + '1' * 32
                                        + '/target/stdout.txt')
                    stream.write_text('changed after packet\n')
                elif case in ('missing_reviewer_evidence', 'changed_reviewer_evidence'):
                    evidence = blocked / 'controls/source-evidence/reviewer-1/RESULTS.json'
                    if case == 'missing_reviewer_evidence':
                        evidence.unlink()
                    else:
                        evidence.chmod(0o644)
                        evidence.write_bytes(evidence.read_bytes() + b' ')
                repeated = continuation.continue_run(blocked, max_invocations=2,
                    invoke=lambda *args: (_ for _ in ()).throw(AssertionError('cached_readback_sent')),
                    status_fn=lambda _: {'status': 'active', 'allowance': {'active': True}})
            assert repeated['status'] == 'review_incomplete' and len(review_calls) == 1
            cached_readback_denied.append(case)
        packet = root / 'handoff/reviewer-1'
        reviewer = root / 'controls/review-reviewer-1.json'
        projection = next((root / 'controls/research/reviews').glob('*/RESULTS.json'))
        action_rows = []
        for identity in ('1' * 32, '2' * 32):
            action = root / 'controls/continuation/source-actions' / identity
            execution = root / 'controls/source-executions' / identity
            source_receipt = runner._read_json(execution / 'receipt.json')
            action_rows.append({'action_id': identity,
                                'input_manifest_sha256': runner._sha(action / 'input-manifest.json'),
                                'receipt_sha256': runner._sha(execution / 'receipt.json'),
                                'terminal_sha256': runner._sha(action / 'terminal.json'),
                                'output_sha256': [row['stdout_sha256'] for row in source_receipt['runs']],
                                'all_commands_succeeded': source_receipt['all_commands_succeeded']})
        report = {'status': 'passed', 'review_calls': len(calls),
                  'reviewer_action': 'synthetic_candidate_receipt',
                  'reviewer_role': 'reviewer-1', 'packet_input_id': calls[0],
                  'packet_file_sha256': {path.name: runner._sha(path)
                                         for path in sorted(packet.iterdir())},
                  'review_receipt_sha256': runner._sha(reviewer),
                  'readback_projection_sha256': runner._sha(projection),
                  'same_run_readback': True, 'security_effect': 'unproven',
                  'allowance_before': allowance, 'allowance_after': allowance,
                  'original_source_manifest_sha256': runner._plan(root)['source_manifest_sha256'],
                  'source_actions': action_rows,
                  'provider_calls': 0, 'target_calls': 0, 'native_review': 'synthetic',
                  'denied': denied, 'post_dispatch_no_retry': post_dispatch,
                  'cached_readback_denied': cached_readback_denied,
                  'environment': {'python': platform.python_version(),
                                  'platform': platform.system().lower()},
                  'source_sha256': runner._sha(ROOT / 'tools/native_continuation.py'),
                  'check_sha256': runner._sha(Path(__file__))}
    report['cleanup'] = 'temporary_files_removed' if not base.exists() else 'incomplete'
    assert report['cleanup'] == 'temporary_files_removed'
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
