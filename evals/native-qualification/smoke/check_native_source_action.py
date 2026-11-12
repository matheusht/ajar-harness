#!/usr/bin/env python3
"""Synthetic native-turn bridge; --docker runs the real offline source executor."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
import native_continuation as continuation
import native_research as runner


ACTION = {'kind': 'native-source-execute-v1', 'command': ['sh', 'check.sh']}


def checkpoint(*, action: dict | None, stop: bool = False) -> dict:
    action = {'kind': action['kind'], 'command': list(action['command'])} if action else None
    return {'kind': continuation.NEXT_KIND,
            'last_result': {'state': 'inconclusive', 'rules_out': 'none',
                            'unresolved': 'original entry and permission'},
            'capabilities': [], 'coverage': [], 'next': None,
            'host_action': action, 'proposed_stop': stop, 'strong_lead': False}


def fixture(base: Path, image: str | None = None) -> Path:
    root = base / 'run'
    (root / 'controls/continuation').mkdir(parents=True, mode=0o700)
    root.chmod(0o700)
    (root / 'controls/research').mkdir(mode=0o700)
    (root / 'controls/source-executions').mkdir(mode=0o700)
    (root / 'controls/source-modules').mkdir(mode=0o700)
    (root / 'researcher/project').mkdir(parents=True, mode=0o700)
    (root / 'researcher/project/check.sh').write_text('printf benign-check\\n\n')
    source = runner._inventory(root / 'researcher/project')
    if image:
        shutil.copytree(root / 'researcher/project', root / 'original')
        for role in runner.CAPTURE_TARGETS:
            shutil.copytree(root / 'original', root / role)
    runner._write_json(root / 'plan.json', {'kind': 'native-research-plan-v1',
        'source_only': {
            'runtime': {'version_command': ['sh', '-c', 'printf synthetic'],
                        'version_stdout': 'synthetic', 'dependency_command': ['true']},
            'module_cache_sha256': hashlib.sha256(b'{}').hexdigest(),
            'build_command': ACTION['command']},
        'source_effect_envelope': runner.SOURCE_EFFECT_ENVELOPE,
        'scope_sha256': 'a' * 64, 'limits': runner.DEFAULT_LIMITS,
        'source_sha256': source,
        'source_manifest_sha256': hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest(),
        'target_image_id': image or 'fixture', 'platform': 'linux/arm64'})
    if image:
        runner._write_json(root / 'controls/resources.json', {'nonce': root.name})
    runner._write_json(root / 'controls/approval.json', {'kind': 'fixture-approval'})
    return root


def fake_freeze(root: Path, destination: Path, role: str) -> dict:
    assert role == 'researcher'
    shutil.copytree(root / 'researcher/project', destination)
    return runner._inventory(destination)


def captured_receipt(root: Path, command_file: Path, source_snapshot: Path,
                     execution_id: str) -> dict:
    directory = root / 'controls/source-executions' / execution_id
    directory.mkdir()
    shutil.copytree(source_snapshot, directory / 'input')
    inventory = runner._inventory(directory / 'input')
    runner._write_json(directory / 'input-manifest.json', inventory, once=True)
    receipt = {'kind': 'native-source-execution-v1', 'status': 'captured',
               'execution_id': execution_id, 'owner_role': 'researcher',
               'plan_sha256': runner._sha(root / 'plan.json'),
               'original_source_manifest_sha256': runner._plan(root)['source_manifest_sha256'],
               'module_cache_sha256': runner._plan(root)['source_only']['module_cache_sha256'],
               'image_id': runner._plan(root)['target_image_id'],
               'platform': runner._plan(root)['platform'], 'network': 'none',
               'command': json.loads(command_file.read_text()),
               'input_manifest_sha256': runner._sha(directory / 'input-manifest.json'),
               'assessment': 'needs_review', 'replay_output_equal': True,
               'all_commands_succeeded': True, 'runs': []}
    for role in runner.CAPTURE_TARGETS:
        output = directory / role
        output.mkdir()
        shutil.copytree(source_snapshot, output / 'files')
        runner._write_json(output / 'files.json', inventory, once=True)
        (output / 'stdout.txt').write_text('benign-check\n')
        (output / 'stderr.txt').write_text('')
        (output / 'stdout.txt').chmod(0o600)
        (output / 'stderr.txt').chmod(0o600)
        receipt['runs'].append({'role': role, 'exit_code': 0,
                                'stdout_sha256': runner._sha(output / 'stdout.txt'),
                                'stderr_sha256': runner._sha(output / 'stderr.txt'),
                                'output_manifest_sha256': runner._sha(output / 'files.json')})
    path = directory / 'receipt.json'
    runner._write_json(path, receipt, once=True)
    return {'status': 'captured', 'assessment': 'needs_review',
            'receipt_path': str(path), 'receipt_sha256': runner._sha(path),
            'replay_output_equal': True, 'all_commands_succeeded': True}


def fake_execute(calls: list, *, crash: bool = False, crash_after_capture: bool = False):
    def execute(root: Path, command_file: Path | None = None, *,
                source_snapshot: Path | None = None, owner_role: str = 'researcher',
                execution_id: str | None = None, expected_command=None,
                expected_input=None) -> dict:
        assert owner_role == 'researcher' and execution_id and source_snapshot
        assert json.loads(command_file.read_text()) == ACTION['command']
        assert expected_command == ACTION['command']
        assert runner._inventory(source_snapshot) == expected_input
        calls.append(execution_id)
        if crash:
            raise RuntimeError('synthetic_crash_after_dispatch')
        result = captured_receipt(root, command_file, source_snapshot, execution_id)
        if crash_after_capture:
            raise RuntimeError('synthetic_crash_after_capture')
        return result
    return execute


def run_case(base: Path, *, crash: bool = False, crash_before_dispatch: bool = False,
             crash_before_state: bool = False, late_capture: bool = False,
             crash_after_capture: bool = False, tamper_receipt: bool = False,
             image: str | None = None, authority_record: bool = False):
    root = fixture(base, image)
    if authority_record:
        directory = root / 'controls/continuation/source-actions'
        directory.mkdir(mode=0o700)
        runner._write_json(directory / ('authority-' + 'b' * 64 + '.json'),
                           {'kind': 'native-source-authority-request-v1'})
    calls, turns = [], []
    created, bindings = [], {}
    if image:
        runner.DOCKER_BINARY = Path(shutil.which('docker')).resolve()
        for role in runner.CAPTURE_TARGETS:
            target = root / role
            result = runner._docker('container', 'run', '-d', '--pull', 'never',
                '--network', 'none', '--read-only', '--restart', 'no', '--log-driver', 'none',
                '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges=true',
                '--user', f'{os.getuid()}:{os.getgid()}', '--memory', '1g', '--cpus', '1',
                '--pids-limit', '64', '--tmpfs', '/tmp:rw,nosuid,nodev,size=128m',
                '--label', runner.LABEL + '=' + root.name,
                '--mount', 'type=bind,src=' + str(target) + ',dst=/target',
                '--mount', 'type=bind,src=' + str(root / 'controls/source-modules')
                           + ',dst=/modules,readonly',
                '-w', '/target', '--entrypoint', 'sh', image,
                '-c', 'while :; do sleep 3600; done')
            bindings[role] = result.stdout.decode().strip()
            created.append(bindings[role])

    def invoke(command, session, prompt):
        turns.append(command)
        if command == 'research':
            runner._write_json(root / 'researcher/NEXT.json', checkpoint(action=ACTION))
        else:
            projections = list((root / 'controls/research/source-actions').glob('*/RESULTS.json'))
            assert len(projections) == 1
            assert prompt and ('/research/source-actions/' + projections[0].parent.name
                               + '/RESULTS.json') in prompt.read_text()
            projection = runner._read_json(projections[0])
            assert projection['assessment'] == 'needs_review'
            assert projection['security_effect'] == 'unproven'
            runner._write_json(root / 'researcher/NEXT.json', checkpoint(action=None, stop=True))
        return 0, {'status': 'acknowledged', 'session_id': 'ses_fixture',
                   'dispatch_id': 'a' * 32,
                   'pool_after': {'used_tunnels': len(turns), 'charged_tunnel_bytes': len(turns),
                                  'active': True}}

    owner = type('Owner', (), {'dispatch_guard': staticmethod(lambda _: contextlib.nullcontext())})()
    with contextlib.ExitStack() as stack:
        for name, value in (('_verified_plan', lambda root, **kw: runner._read_json(root / 'plan.json')),
                            ('_approval_active', lambda _: None),
                            ('run_active', lambda _: True),
                            ('allowance_snapshot', lambda _: {'active': True,
                                'run_identity': {'nonce': 'fixture'}, 'used_tunnels': 0,
                                'charged_tunnel_bytes': 0}),
                            ('_unresolved_dispatches', lambda _: []),
                            ('_freeze_source_input', fake_freeze)):
            stack.enter_context(patch.object(runner, name, value))
        if image:
            stack.enter_context(patch.object(runner, '_resources', return_value=bindings))
            stack.enter_context(patch.object(runner, '_activate_controls', return_value=(owner, None)))
            stack.enter_context(patch.object(runner, 'stop', return_value=None))
            original_execute = runner.source_execute
            def real_execute(*args, **kwargs):
                calls.append(kwargs['execution_id'])
                return original_execute(*args, **kwargs)
            stack.enter_context(patch.object(runner, 'source_execute', side_effect=real_execute))
        else:
            stack.enter_context(patch.object(runner, '_source_executor_envelope'))
            stack.enter_context(patch.object(runner, 'source_execute',
                side_effect=fake_execute(calls, crash=crash or late_capture,
                                         crash_after_capture=crash_after_capture)))
        if crash_before_state:
            original_save = continuation._save_state
            def interrupt_state(run_root, value):
                if (value.get('source_action') or {}).get('phase') == 'prepared':
                    raise RuntimeError('synthetic_crash_before_prepared_state')
                original_save(run_root, value)
            stack.enter_context(patch.object(continuation, '_save_state',
                                             side_effect=interrupt_state))
        if crash_before_dispatch:
            original_event = continuation._event
            def interrupt_prepared(run_root, event):
                original_event(run_root, event)
                if event.get('event') == 'source_action_prepared':
                    raise RuntimeError('synthetic_crash_before_dispatch')
            event_patch = patch.object(continuation, '_event', side_effect=interrupt_prepared)
            stack.enter_context(event_patch)
        try:
            first = continuation.continue_run(root, max_invocations=3, closeout_wait_seconds=0, invoke=invoke,
                status_fn=lambda _: {'status': 'active', 'allowance': {'active': True}})
        except RuntimeError as error:
            assert (crash and str(error) == 'synthetic_crash_after_dispatch'
                    or late_capture and str(error) == 'synthetic_crash_after_dispatch'
                    or crash_before_state and str(error) == 'synthetic_crash_before_prepared_state'
                    or crash_before_dispatch and str(error) == 'synthetic_crash_before_dispatch'
                    or crash_after_capture and str(error) == 'synthetic_crash_after_capture')
            first = None
        if crash_before_dispatch or crash_before_state:
            stack.pop_all().close()
            return run_prepared_resume(root, calls, turns, invoke,
                'synthetic_crash_before_prepared_state' if crash_before_state
                else 'synthetic_crash_before_dispatch')
        if tamper_receipt:
            action = runner._read_json(root / 'controls/continuation/state.json')['source_action']
            receipt_path = root / 'controls/source-executions' / action['action_id'] / 'receipt.json'
            original_receipt = runner._read_json(receipt_path)
            receipt = dict(original_receipt)
            receipt['command'] = ['sh', 'swapped.sh']
            runner._write_json(receipt_path, receipt)
            bad_receipt_sha = runner._sha(receipt_path)
        if crash or crash_after_capture or late_capture:
            second = continuation.continue_run(root, max_invocations=3, closeout_wait_seconds=0, invoke=invoke,
                status_fn=lambda _: {'status': 'active', 'allowance': {'active': True}})
            if crash or tamper_receipt or late_capture:
                assert second['status'] == 'cleanup_pending'
                assert (root / 'controls/closeout/stop-request.json').exists(), second
                assert len(calls) == 1 and turns == ['research']
                if tamper_receipt:
                    held = runner._read_json(root / 'controls/continuation/state.json')['source_action']
                    assert held['phase'] == 'evidence_changed'
                    assert held['observed_receipt_sha256'] == bad_receipt_sha
                    assert held['evidence_change_reason'] == 'source_action_receipt_mismatch'
                    runner._write_json(receipt_path, original_receipt)
                    third = continuation.continue_run(root, max_invocations=3, closeout_wait_seconds=0, invoke=invoke,
                        status_fn=lambda _: {'status': 'active', 'allowance': {'active': True}})
                    assert third['status'] == 'cleanup_pending', third
                    assert len(calls) == 1 and turns == ['research']
                if late_capture:
                    action = runner._read_json(root / 'controls/continuation/state.json')['source_action']
                    directory = root / 'controls/continuation/source-actions' / action['action_id']
                    captured_receipt(root, directory / 'command.json', directory / 'input',
                                     action['action_id'])
                    third = continuation.continue_run(root, max_invocations=3, closeout_wait_seconds=0, invoke=invoke,
                        status_fn=lambda _: {'status': 'active', 'allowance': {'active': True}})
                    assert third['status'] == 'cleanup_pending', third
                    assert len(calls) == 1 and turns == ['research']
            else:
                assert second['status'] == 'cleanup_pending'
                assert len(calls) == 1 and turns == ['research', 'resume']
        else:
            assert first['status'] == 'cleanup_pending'
            assert turns == ['research', 'resume'] and len(calls) == 1
            second = continuation.continue_run(root, max_invocations=3, closeout_wait_seconds=0, invoke=invoke,
                status_fn=lambda _: {'status': 'active', 'allowance': {'active': True}})
            assert second['status'] == 'cleanup_pending' and len(calls) == 1
    try:
        action = runner._read_json(root / 'controls/continuation/state.json')['source_action']
        directory = root / 'controls/continuation/source-actions' / action['action_id']
        evidence = {'action_id': action['action_id'],
                    'request_sha256': action['request_sha256'],
                    'terminal_sha256': action['terminal_sha256'],
                    'source_receipt_sha256': (runner._sha(root / 'controls/source-executions'
                        / action['action_id'] / 'receipt.json') if action['terminal_sha256'] else None)}
        if tamper_receipt:
            evidence['observed_bad_receipt_sha256'] = action['observed_receipt_sha256']
            evidence['evidence_change_reason'] = action['evidence_change_reason']
        if action['terminal_sha256']:
            receipt = runner._read_json(root / 'controls/source-executions' / action['action_id'] / 'receipt.json')
            request = runner._read_json(directory / 'request.json')
            terminal = runner._read_json(directory / 'terminal.json')
            assert len(receipt['runs']) == 3
            assert runner._sha(directory / 'terminal.json') == action['terminal_sha256']
            assert terminal['allowance_before'] == request['allowance_before']
            assert terminal['allowance_observed_at_adoption']['run_identity'] == request['allowance_before']['run_identity']
        return {'first_status': first['status'] if first else (
                    'synthetic_crash_after_capture' if crash_after_capture else
                    'synthetic_crash_after_dispatch'),
                'second_status': second['status'], 'source_batches': len(calls),
                'late_receipt_status': third['status'] if late_capture else None,
                'replacement_status': third['status'] if tamper_receipt else None,
                'turns': turns, 'evidence': evidence,
                'cleanup': 'all_fixture_containers_absent' if image else 'temporary_files_removed'}
    finally:
        for identifier in created:
            runner._docker('container', 'rm', '-f', identifier, allow_failure=True)
            remaining = runner._docker('container', 'ls', '-a', '--no-trunc',
                '--filter', 'id=' + identifier, '--format', '{{.ID}}')
            assert remaining.stdout.strip() == b''


def run_prepared_resume(root: Path, calls: list, turns: list, invoke,
                        first_status: str) -> dict:
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(runner, '_verified_plan',
            side_effect=lambda run_root, **kw: runner._read_json(run_root / 'plan.json')))
        stack.enter_context(patch.object(runner, '_approval_active'))
        stack.enter_context(patch.object(runner, 'run_active', return_value=True))
        stack.enter_context(patch.object(runner, 'allowance_snapshot', return_value={
            'active': True, 'run_identity': {'nonce': 'fixture'},
            'used_tunnels': 0, 'charged_tunnel_bytes': 0}))
        stack.enter_context(patch.object(runner, '_unresolved_dispatches', return_value=[]))
        stack.enter_context(patch.object(runner, '_source_executor_envelope'))
        stack.enter_context(patch.object(runner, 'source_execute',
            side_effect=fake_execute(calls)))
        result = continuation.continue_run(root, max_invocations=3, closeout_wait_seconds=0, invoke=invoke,
            status_fn=lambda _: {'status': 'active', 'allowance': {'active': True}})
    assert result['status'] == 'cleanup_pending'
    assert len(calls) == 1 and turns == ['research', 'resume']
    return {'first_status': first_status,
            'second_status': result['status'], 'source_batches': len(calls),
            'turns': turns}


def incomplete_orphan_case(base: Path, *, disputed: str | None = None) -> dict:
    root = fixture(base)
    calls = []
    freeze_calls = []
    turns = []
    def invoke(command, session, prompt):
        turns.append(command)
        if command == 'research':
            runner._write_json(root / 'researcher/NEXT.json', checkpoint(action=ACTION))
        else:
            assert command == 'resume'
            runner._write_json(root / 'researcher/NEXT.json', checkpoint(action=None, stop=True))
        return 0, {'status': 'acknowledged', 'session_id': 'ses_fixture',
                   'dispatch_id': 'a' * 32,
                   'pool_after': {'used_tunnels': len(turns),
                                  'charged_tunnel_bytes': len(turns), 'active': True}}
    def interrupted_freeze(run_root, destination, role):
        freeze_calls.append(1)
        inventory = fake_freeze(run_root, destination, role)
        if len(freeze_calls) == 1:
            raise RuntimeError('synthetic_crash_during_freeze')
        return inventory
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(runner, '_verified_plan',
            side_effect=lambda run_root, **kw: runner._read_json(run_root / 'plan.json')))
        stack.enter_context(patch.object(runner, '_approval_active'))
        stack.enter_context(patch.object(runner, 'run_active', return_value=True))
        stack.enter_context(patch.object(runner, 'allowance_snapshot', return_value={
            'active': True, 'run_identity': {'nonce': 'fixture'},
            'used_tunnels': 0, 'charged_tunnel_bytes': 0}))
        stack.enter_context(patch.object(runner, '_unresolved_dispatches', return_value=[]))
        stack.enter_context(patch.object(runner, '_freeze_source_input',
            side_effect=interrupted_freeze))
        stack.enter_context(patch.object(runner, '_source_executor_envelope'))
        stack.enter_context(patch.object(runner, 'source_execute',
            side_effect=fake_execute(calls)))
        try:
            continuation.continue_run(root, max_invocations=3, closeout_wait_seconds=0, invoke=invoke,
                status_fn=lambda _: {'status': 'active', 'allowance': {'active': True}})
        except RuntimeError as error:
            assert str(error) == 'synthetic_crash_during_freeze'
        else:
            raise AssertionError('freeze interruption was not observed')
        orphan = next((root / 'controls/continuation/source-actions').iterdir())
        if disputed == 'execution':
            (root / 'controls/source-executions' / orphan.name).mkdir()
        elif disputed == 'dispatch_event':
            continuation._event(root, {'event': 'source_action_dispatched',
                                       'action_id': orphan.name})
        elif disputed == 'malformed_journal':
            with (root / 'controls/continuation/events.jsonl').open('ab') as stream:
                stream.write(b'{"event":"source_action_dispatched"')
        if disputed:
            try:
                continuation.continue_run(root, max_invocations=3, closeout_wait_seconds=0, invoke=invoke,
                    status_fn=lambda _: {'status': 'active', 'allowance': {'active': True}})
            except continuation.ContinuationError as error:
                assert str(error) == 'source_action_orphan_requires_reconciliation'
            else:
                raise AssertionError('disputed orphan unexpectedly recovered')
            assert not calls
            assert orphan.exists()
            return {'status': 'reconciliation_required', 'reason': disputed,
                    'source_batches': 0}
        result = continuation.continue_run(root, max_invocations=3, closeout_wait_seconds=0, invoke=invoke,
            status_fn=lambda _: {'status': 'active', 'allowance': {'active': True}})
        assert result['status'] == 'cleanup_pending'
    assert len(calls) == 1 and calls[0] != orphan.name and turns == ['research', 'resume']
    abort = root / 'controls/continuation/aborted-source-actions' / orphan.name / 'abort.json'
    assert runner._read_json(abort)['status'] == 'aborted_before_dispatch'
    assert not (root / 'controls/source-executions' / orphan.name).exists()
    return {'status': 'recovered_pre_dispatch', 'source_batches': len(calls),
            'aborted_orphan': orphan.name, 'new_action_id': calls[0]}


def second_action_orphan_case(base: Path, *, incomplete: bool) -> dict:
    root = fixture(base)
    calls, turns, freezes = [], [], []
    interrupted = False
    def invoke(command, session, prompt):
        turns.append(command)
        runner._write_json(root / 'researcher/NEXT.json',
                           checkpoint(action=ACTION if len(turns) < 3 else None,
                                      stop=len(turns) == 3))
        return 0, {'status': 'acknowledged', 'session_id': 'ses_fixture',
                   'dispatch_id': 'a' * 32,
                   'pool_after': {'used_tunnels': len(turns),
                                  'charged_tunnel_bytes': len(turns), 'active': True}}
    def freeze(run_root, destination, role):
        nonlocal interrupted
        freezes.append(1)
        inventory = fake_freeze(run_root, destination, role)
        if incomplete and len(freezes) == 2 and not interrupted:
            interrupted = True
            raise RuntimeError('synthetic_second_freeze_crash')
        return inventory
    original_save = continuation._save_state
    def save(run_root, value):
        nonlocal interrupted
        if (not incomplete and not interrupted
                and (value.get('source_action') or {}).get('phase') == 'prepared'
                and (value.get('source_action') or {}).get('after_invocations') == 2):
            interrupted = True
            raise RuntimeError('synthetic_second_prepared_crash')
        original_save(run_root, value)
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(runner, '_verified_plan',
            side_effect=lambda run_root, **kw: runner._read_json(run_root / 'plan.json')))
        stack.enter_context(patch.object(runner, '_approval_active'))
        stack.enter_context(patch.object(runner, 'run_active', return_value=True))
        stack.enter_context(patch.object(runner, 'allowance_snapshot', return_value={
            'active': True, 'run_identity': {'nonce': 'fixture'},
            'used_tunnels': 0, 'charged_tunnel_bytes': 0}))
        stack.enter_context(patch.object(runner, '_unresolved_dispatches', return_value=[]))
        stack.enter_context(patch.object(runner, '_freeze_source_input', side_effect=freeze))
        stack.enter_context(patch.object(runner, '_source_executor_envelope'))
        stack.enter_context(patch.object(runner, 'source_execute',
            side_effect=fake_execute(calls)))
        stack.enter_context(patch.object(continuation, '_save_state', side_effect=save))
        try:
            continuation.continue_run(root, max_invocations=4, closeout_wait_seconds=0, invoke=invoke,
                status_fn=lambda _: {'status': 'active', 'allowance': {'active': True}})
        except RuntimeError as error:
            assert str(error) == ('synthetic_second_freeze_crash' if incomplete
                                  else 'synthetic_second_prepared_crash')
        else:
            raise AssertionError('second action interruption was not observed')
        state = runner._read_json(root / 'controls/continuation/state.json')
        first_id = state['source_action']['action_id']
        assert state['source_action']['phase'] == 'captured' and len(calls) == 1
        action_dirs = list((root / 'controls/continuation/source-actions').iterdir())
        orphan = next(path for path in action_dirs if path.name != first_id)
        result = continuation.continue_run(root, max_invocations=4, closeout_wait_seconds=0, invoke=invoke,
            status_fn=lambda _: {'status': 'active', 'allowance': {'active': True}})
    assert result['status'] == 'cleanup_pending'
    assert len(calls) == 2 and turns == ['research', 'resume', 'resume']
    assert (calls[1] != orphan.name) == incomplete
    if incomplete:
        abort = root / 'controls/continuation/aborted-source-actions' / orphan.name / 'abort.json'
        assert runner._read_json(abort)['status'] == 'aborted_before_dispatch'
    return {'status': 'recovered_second_action', 'source_batches': len(calls),
            'first_action_id': first_id, 'orphan_action_id': orphan.name,
            'second_action_id': calls[1], 'orphan_quarantined': incomplete}


def captured_event_gap_case(base: Path) -> dict:
    root = fixture(base)
    calls, turns = [], []
    interrupted = False
    def invoke(command, session, prompt):
        turns.append(command)
        runner._write_json(root / 'researcher/NEXT.json',
                           checkpoint(action=ACTION if len(turns) < 4 else None,
                                      stop=len(turns) == 4))
        return 0, {'status': 'acknowledged', 'session_id': 'ses_fixture',
                   'dispatch_id': 'a' * 32,
                   'pool_after': {'used_tunnels': len(turns),
                                  'charged_tunnel_bytes': len(turns), 'active': True}}
    original_event = continuation._event
    def event(run_root, value):
        nonlocal interrupted
        if not interrupted and value.get('event') == 'source_action_captured':
            interrupted = True
            raise RuntimeError('synthetic_crash_before_captured_event')
        original_event(run_root, value)
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(runner, '_verified_plan',
            side_effect=lambda run_root, **kw: runner._read_json(run_root / 'plan.json')))
        stack.enter_context(patch.object(runner, '_approval_active'))
        stack.enter_context(patch.object(runner, 'run_active', return_value=True))
        stack.enter_context(patch.object(runner, 'allowance_snapshot', return_value={
            'active': True, 'run_identity': {'nonce': 'fixture'},
            'used_tunnels': 0, 'charged_tunnel_bytes': 0}))
        stack.enter_context(patch.object(runner, '_unresolved_dispatches', return_value=[]))
        stack.enter_context(patch.object(runner, '_freeze_source_input', side_effect=fake_freeze))
        stack.enter_context(patch.object(runner, '_source_executor_envelope'))
        stack.enter_context(patch.object(runner, 'source_execute',
            side_effect=fake_execute(calls)))
        stack.enter_context(patch.object(continuation, '_event', side_effect=event))
        try:
            continuation.continue_run(root, max_invocations=5, closeout_wait_seconds=0, invoke=invoke,
                status_fn=lambda _: {'status': 'active', 'allowance': {'active': True}})
        except RuntimeError as error:
            assert str(error) == 'synthetic_crash_before_captured_event'
        else:
            raise AssertionError('captured event interruption was not observed')
        state = runner._read_json(root / 'controls/continuation/state.json')
        first_id = state['source_action']['action_id']
        assert state['source_action']['phase'] == 'captured' and calls == [first_id]
        result = continuation.continue_run(root, max_invocations=5, closeout_wait_seconds=0, invoke=invoke,
            status_fn=lambda _: {'status': 'active', 'allowance': {'active': True}})
    assert result['status'] == 'cleanup_pending'
    assert len(calls) == 3 and len(set(calls)) == 3
    assert turns == ['research', 'resume', 'resume', 'resume']
    events = continuation._source_action_events(root)
    captured = [row for row in events if row.get('event') == 'source_action_captured'
                and row.get('action_id') == first_id]
    assert len(captured) == 1 and captured[0].get('recovered_from_state') is True
    return {'status': 'recovered_captured_event', 'source_batches': len(calls),
            'first_action_id': first_id, 'first_captured_events': len(captured)}


def rejection_cases(base: Path) -> list[str]:
    cases = ('malformed', 'duplicate_key', 'oversized', 'symlink', 'invalid_argv',
             'stale_next', 'swapped_command', 'swapped_source', 'swapped_request',
             'missing_envelope', 'expired_approval', 'exhausted', 'stopped')
    for case in cases:
        root = fixture(base / case)
        calls = []
        next_path = root / 'researcher/NEXT.json'

        def invoke(command, session, prompt):
            assert command == 'research'
            value = checkpoint(action=ACTION)
            if case == 'malformed':
                next_path.write_text('{')
            elif case == 'duplicate_key':
                next_path.write_text(json.dumps(value)[:-1] + ',"kind":"duplicate"}')
            elif case == 'oversized':
                next_path.write_text(json.dumps(value) + ' ' * 65536)
            elif case == 'symlink':
                other = root / 'researcher/NEXT-real.json'
                runner._write_json(other, value)
                next_path.symlink_to(other)
            else:
                if case == 'invalid_argv':
                    value['host_action']['command'] = ['env', 'API_KEY=value']
                runner._write_json(next_path, value)
            if case == 'stopped':
                runner._write_json(root / 'controls/continuation/STOP',
                    {'kind': continuation.STOP_KIND, 'reason': 'operator_stop'})
            return 0, {'status': 'acknowledged', 'session_id': 'ses_fixture',
                       'dispatch_id': 'a' * 32,
                       'pool_after': {'used_tunnels': 1, 'charged_tunnel_bytes': 1,
                                      'active': True}}

        def freeze(run_root, destination, role):
            inventory = fake_freeze(run_root, destination, role)
            if case == 'stale_next':
                value = checkpoint(action=ACTION)
                value['last_result']['unresolved'] = 'changed after validation'
                runner._write_json(next_path, value)
            return inventory

        original_event = continuation._event
        def event(run_root, row):
            original_event(run_root, row)
            if row.get('event') != 'source_action_prepared':
                return
            directory = root / 'controls/continuation/source-actions' / row['action_id']
            if case == 'swapped_command':
                runner._write_json(directory / 'command.json', ['sh', 'other.sh'])
            elif case == 'swapped_source':
                (directory / 'input/check.sh').write_text('printf changed\n')
            elif case == 'swapped_request':
                request = runner._read_json(directory / 'request.json')
                request['scope_sha256'] = 'b' * 64
                runner._write_json(directory / 'request.json', request)

        if case == 'missing_envelope':
            plan = runner._read_json(root / 'plan.json')
            del plan['source_effect_envelope']
            runner._write_json(root / 'plan.json', plan)
        allowance = {'active': True, 'run_identity': {'nonce': 'fixture'},
                     'used_tunnels': runner.DEFAULT_LIMITS['max_connections'] if case == 'exhausted' else 0,
                     'charged_tunnel_bytes': 0}
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(runner, '_verified_plan',
                side_effect=lambda run_root, **kw: runner._read_json(run_root / 'plan.json')))
            stack.enter_context(patch.object(runner, '_approval_active',
                side_effect=(runner.NativeResearchError('research_approval_expired')
                             if case == 'expired_approval' else None)))
            stack.enter_context(patch.object(runner, 'run_active', return_value=True))
            stack.enter_context(patch.object(runner, 'allowance_snapshot', return_value=allowance))
            stack.enter_context(patch.object(runner, '_unresolved_dispatches', return_value=[]))
            stack.enter_context(patch.object(runner, '_freeze_source_input', side_effect=freeze))
            stack.enter_context(patch.object(runner, '_source_executor_envelope'))
            stack.enter_context(patch.object(runner, 'source_execute',
                side_effect=fake_execute(calls)))
            stack.enter_context(patch.object(continuation, '_event', side_effect=event))
            try:
                result = continuation.continue_run(root, max_invocations=2, closeout_wait_seconds=0, invoke=invoke,
                    status_fn=lambda _: {'status': 'active', 'allowance': {'active': True}})
                assert case in ('missing_envelope', 'stopped')
                assert result['status'] == ('authority_required' if case == 'missing_envelope'
                                            else 'cleanup_pending')
                if case == 'missing_envelope':
                    authority = runner._read_json(Path(result['source_action']['authority_request']))
                    assert authority['human_decision_required'] is True
                    assert authority['research_help'] is False
            except (runner.NativeResearchError, continuation.ContinuationError):
                assert case not in ('missing_envelope', 'stopped')
        assert calls == [], case
        assert list((root / 'controls/source-executions').iterdir()) == [], case
    locked = fixture(base / 'concurrent')
    with continuation._lease(locked):
        try:
            continuation.continue_run(locked, max_invocations=1)
        except continuation.ContinuationError as error:
            assert str(error) == 'continuation_already_running'
        else:
            raise AssertionError('concurrent controller accepted')
    return [*cases, 'concurrent']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--docker', help='existing pinned linux/arm64 image with sh; never pulls')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='native-source-action-') as temp:
        base = Path(temp).resolve()
        happy = run_case(base / 'happy')
        prior_authority_record = run_case(base / 'authority-record', authority_record=True)
        uncertain = run_case(base / 'uncertain', crash=True)
        prepared = run_case(base / 'prepared', crash_before_dispatch=True)
        orphan_prepared = run_case(base / 'orphan-prepared', crash_before_state=True)
        orphan_incomplete = incomplete_orphan_case(base / 'orphan-incomplete')
        orphan_execution = incomplete_orphan_case(base / 'orphan-execution',
                                                   disputed='execution')
        orphan_dispatch_event = incomplete_orphan_case(base / 'orphan-dispatch-event',
                                                        disputed='dispatch_event')
        orphan_malformed_journal = incomplete_orphan_case(base / 'orphan-malformed-journal',
                                                          disputed='malformed_journal')
        second_orphan_prepared = second_action_orphan_case(base / 'second-orphan-prepared',
                                                           incomplete=False)
        second_orphan_incomplete = second_action_orphan_case(base / 'second-orphan-incomplete',
                                                             incomplete=True)
        captured_event_gap = captured_event_gap_case(base / 'captured-event-gap')
        late_capture = run_case(base / 'late-capture', late_capture=True)
        adopted = run_case(base / 'adopted', crash_after_capture=True)
        tampered_receipt = run_case(base / 'tampered-receipt',
                                    crash_after_capture=True, tamper_receipt=True)
        rejected = rejection_cases(base / 'rejected')
        docker = run_case(base / 'docker', image=args.docker) if args.docker else None
    print(json.dumps({'status': 'passed', 'happy': happy, 'uncertain': uncertain,
                      'adopted': adopted,
                      'tampered_receipt': tampered_receipt,
                      'prior_authority_record': prior_authority_record,
                      'prepared': prepared,
                      'orphan_prepared': orphan_prepared,
                      'orphan_incomplete': orphan_incomplete,
                      'orphan_execution': orphan_execution,
                      'orphan_dispatch_event': orphan_dispatch_event,
                      'orphan_malformed_journal': orphan_malformed_journal,
                      'second_orphan_prepared': second_orphan_prepared,
                      'second_orphan_incomplete': second_orphan_incomplete,
                      'captured_event_gap': captured_event_gap,
                      'late_capture': late_capture,
                      'rejected': rejected,
                      'docker': docker,
                      'image_id': args.docker,
                      'environment': {'platform': sys.platform, 'python': sys.version.split()[0],
                                      'docker': (runner._docker('version', '--format', '{{.Server.Version}}')
                                                 .stdout.decode().strip() if args.docker else None)},
                      'expected': {'source_batches_per_request': 1,
                                   'clean_executor_runs': 3,
                                   'unknown_effect_auto_retries': 0,
                                   'changed_receipt_auto_adoptions': 0},
                      'native_tool_trace': None,
                      'provider_cost': None,
                      'source_sha256': runner._sha(ROOT / 'tools/native_research.py'),
                      'continuation_sha256': runner._sha(ROOT / 'tools/native_continuation.py'),
                      'check_sha256': runner._sha(Path(__file__)),
                      'command': ACTION['command'],
                      'limits': 'Synthetic native turns and authority; Docker source executor only when requested. No provider or target qualification.'},
                     indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
