#!/usr/bin/env python3
"""Drive one scope-only native engagement through the existing phase commands.

The signed scope and each phase command decide authority. This file only orders
the commands and records enough state to refuse an uncertain repeat after loss
of the driver. ``resume`` re-reads durable phase receipts; it never clears an
unknown model or Docker effect.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid


ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'tools/native_research.py'
BUILDER = ROOT / 'tools/native_setup_builder.py'
CLOSEOUT = ROOT / 'tools/native_closeout.py'
KIND = 'native-engagement-driver-v1'
INPUT_KIND = 'native-engagement-inputs-v1'
SCOPE_KIND = 'native-engagement-scope-v1'
HEX = re.compile(r'[0-9a-f]{64}\Z')
PHASES = ('initialized', 'setup_prepared', 'setup_active', 'setup_turn_done',
          'setup_frozen', 'setup_stopped', 'built', 'research_prepared',
          'research_active', 'complete', 'incomplete')
REVISABLE_FREEZE_ERRORS = {'setup_output_missing_changed_or_oversize',
                           'setup_output_encoding_invalid',
                           'setup_output_credential_like', 'setup_recipe_invalid',
                           'setup_threat_model_empty', 'control_file_invalid'}
INPUT_KEYS = {'kind', 'source', 'brief', 'scope_file', 'scope_signature',
              'allowed_signers', 'trusted_fingerprint', 'relay', 'runtime_ca',
              'dependency_catalog'}
OPTIONAL_INPUT_KEYS = {'provider_key_file', 'provider_tls_key'}


class DriverError(RuntimeError):
    pass


def fail(code: str) -> None:
    raise DriverError(code)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pairs(rows):
    value = {}
    for key, item in rows:
        if key in value:
            fail('duplicate_json_key')
        value[key] = item
    return value


def _read_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 256 * 1024:
        fail('input_file_invalid')
    try:
        value = json.loads(path.read_bytes(), object_pairs_hook=_pairs)
    except (UnicodeError, ValueError):
        fail('input_json_invalid')
    if not isinstance(value, dict):
        fail('input_json_invalid')
    return value


def _write(path: Path, value: dict) -> None:
    data = (json.dumps(value, sort_keys=True, separators=(',', ':'),
                       allow_nan=False) + '\n').encode()
    temporary = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def _write_prompt(path: Path, reason: str) -> None:
    content = ('The host could not freeze your setup proposal: ' + reason + '.\n'
               'Revise only recipe.json and THREAT_MODEL.md in your current workspace. '
               'The signed scope and remaining allowance are unchanged. '
               'Keep the recipe within the offline build envelope.\n')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def _private_root(root: Path) -> Path:
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        fail('engagement_root_invalid')
    if root.stat().st_mode & 0o077:
        fail('engagement_root_not_private')
    return root.resolve(strict=True)


def _scope(inputs: dict) -> dict:
    path = Path(inputs['scope_file'])
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 256 * 1024:
        fail('scope_file_invalid')
    text = path.read_text()
    sections = re.findall(r'^```native-engagement-scope-v1\s*\n(.*?)^```\s*$',
                          text, re.MULTILINE | re.DOTALL)
    if len(sections) != 1:
        fail('engagement_scope_section_invalid')
    try:
        value = json.loads(sections[0], object_pairs_hook=_pairs)
    except (UnicodeError, ValueError):
        fail('engagement_scope_json_invalid')
    if not isinstance(value, dict) or value.get('kind') != SCOPE_KIND:
        fail('engagement_scope_kind_invalid')
    return value


def _inputs(path: Path) -> dict:
    value = _read_json(path)
    if (not INPUT_KEYS <= set(value) or set(value) - INPUT_KEYS - OPTIONAL_INPUT_KEYS
            or value.get('kind') != INPUT_KIND):
        fail('engagement_inputs_invalid')
    for key in INPUT_KEYS - {'kind', 'trusted_fingerprint'}:
        item = value.get(key)
        if not isinstance(item, str) or not Path(item).is_absolute():
            fail('engagement_input_path_invalid')
    for key in OPTIONAL_INPUT_KEYS:
        item = value.get(key)
        if item is not None and (not isinstance(item, str) or not Path(item).is_absolute()):
            fail('engagement_input_path_invalid')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', str(value['trusted_fingerprint'])):
        fail('engagement_fingerprint_invalid')
    return value


def _initialize(root: Path, inputs_file: Path) -> None:
    if not root.is_absolute() or root.exists() or root.is_symlink():
        fail('engagement_root_exists_or_invalid')
    inputs = _inputs(inputs_file)
    if root.is_relative_to(Path(inputs['source'])) or Path(inputs['source']).is_relative_to(root):
        fail('engagement_root_source_overlap')
    scope = _scope(inputs)
    stage = root.with_name(root.name + '.stage-' + uuid.uuid4().hex)
    stage.mkdir(mode=0o700)
    try:
        shutil.copyfile(inputs_file, stage / 'inputs.json')
        (stage / 'inputs.json').chmod(0o600)
        _write(stage / 'state.json', {
            'kind': KIND, 'phase': 'initialized', 'pending': None,
            'inputs_sha256': _sha(stage / 'inputs.json'),
            'scope_sha256': _sha(Path(inputs['scope_file'])),
            'scope_kind': scope['kind'], 'error': None, 'cleanup': None})
        os.rename(stage, root)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


@contextmanager
def _lease(root: Path):
    fd = os.open(root / 'driver.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    except BlockingIOError:
        fail('engagement_driver_already_running')
    finally:
        os.close(fd)


def _state(root: Path) -> dict:
    state = _read_json(root / 'state.json')
    if (state.get('kind') != KIND or state.get('phase') not in PHASES
            or state.get('inputs_sha256') != _sha(root / 'inputs.json')
            or not HEX.fullmatch(str(state.get('scope_sha256')))):
        fail('engagement_state_changed')
    return state


def _command(script: Path, *args: str, timeout: int = 120) -> tuple[int, dict]:
    try:
        completed = subprocess.run([sys.executable, str(script), *args],
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, timeout=timeout,
                                   cwd=ROOT, check=False,
                                   env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
    except subprocess.TimeoutExpired:
        return 124, {'status': 'unknown_effect', 'code': 'phase_command_timeout'}
    try:
        result = json.loads(completed.stdout)
    except (UnicodeError, ValueError):
        return completed.returncode, {'status': 'unknown_effect',
                                      'code': 'phase_command_result_unknown'}
    if not isinstance(result, dict):
        return completed.returncode, {'status': 'unknown_effect',
                                      'code': 'phase_command_result_unknown'}
    return completed.returncode, result


def _spawn_owner(root: Path, script: Path, run_root: Path, inputs: dict) -> int:
    argv = [sys.executable, str(script), 'start', '--run-root', str(run_root)]
    for name, flag in (('provider_key_file', '--provider-key-file'),
                       ('provider_tls_key', '--provider-tls-key')):
        if inputs.get(name):
            argv += [flag, inputs[name]]
    process = subprocess.Popen(argv, stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               cwd=ROOT, start_new_session=True,
                               env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
    return process.pid


def _call(command, script: Path, args: list[str], *, timeout: int,
          statuses: tuple[str, ...]) -> dict:
    code, result = command(script, *args, timeout=timeout)
    if code != 0 or result.get('status') not in statuses:
        fail(result.get('code') if isinstance(result.get('code'), str)
             and re.fullmatch(r'[a-z][a-z0-9_]{0,100}', result['code'])
             else 'phase_' + args[0].replace('-', '_') + '_failed')
    return result


def _status(command, run_root: Path) -> dict:
    return _call(command, NATIVE, ['status', '--run-root', str(run_root)],
                 timeout=30, statuses=('prepared', 'active', 'stopped_complete',
                                       'recovered_exact_resources', 'inactive_or_unresolved'))


def _pending(root: Path, state: dict, action: str, **evidence) -> None:
    if state['pending'] is not None:
        fail('engagement_action_already_pending')
    state['pending'] = {'action': action, **evidence}
    _write(root / 'state.json', state)


def _advance(root: Path, state: dict, phase: str, **evidence) -> None:
    state.update(phase=phase, pending=None, **evidence)
    _write(root / 'state.json', state)


def _active(command, run_root: Path, seconds: int = 90) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            result = _status(command, run_root)
        except DriverError:
            result = {}
        if result.get('status') == 'active':
            return
        if result.get('status') in ('stopped_complete', 'inactive_or_unresolved'):
            fail('owner_not_active')
        time.sleep(.2)
    fail('owner_activation_unknown')


def _stopped(command, run_root: Path, seconds: int = 150) -> dict:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            result = _status(command, run_root)
        except DriverError:
            result = {}
        if result.get('status') == 'stopped_complete':
            final = result.get('final') or {}
            cleanup = final.get('cleanup') or {}
            rows = cleanup.get('resources')
            if (final.get('status') != 'stopped_complete'
                    or (final.get('native_stop') or {}).get('status') != 'stopped'
                    or cleanup.get('status') != 'complete'
                    or not isinstance(rows, list)
                    or not rows
                    or any(row.get('absent') is not True for row in rows)):
                fail('owner_cleanup_unverified')
            return result
        if result.get('status') == 'inactive_or_unresolved':
            fail('owner_cleanup_unresolved')
        time.sleep(.2)
    fail('owner_stop_readback_pending')


def _deadline(scope: dict) -> datetime:
    try:
        issued = datetime.strptime(scope['issued_at'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
        expiry = datetime.strptime(scope['expires_at'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
        duration = scope['limits']['duration_seconds']
    except (KeyError, TypeError, ValueError):
        fail('engagement_deadline_invalid')
    if type(duration) is not int or duration <= 0:
        fail('engagement_deadline_invalid')
    return min(expiry, issued + timedelta(seconds=duration))


def _research_limits(scope: dict, checked: dict) -> dict:
    try:
        used = checked['cumulative_setup_used']
        total = scope['limits']
        connections = total['max_connections'] - used['connections']
        bytes_left = total['max_bytes'] - used['bytes']
        remaining = checked['remaining_engagement_allowance']
        receipt_deadline = datetime.strptime(remaining['absolute_deadline'],
                                             '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
        duration = int((receipt_deadline - datetime.now(timezone.utc)).total_seconds()) - 15
    except (KeyError, TypeError, ValueError):
        fail('engagement_residual_unavailable')
    if (receipt_deadline != _deadline(scope)
            or remaining['connections'] != connections
            or remaining['bytes'] != bytes_left
            or type(connections) is not int or type(bytes_left) is not int
            or not 1 <= connections <= 128 or not 1024 <= bytes_left <= 128 * 1024 * 1024
            or duration < 30):
        fail('engagement_residual_exhausted')
    return {'max_connections': connections, 'max_bytes': bytes_left,
            'duration_seconds': min(duration, 86400)}


def _checked_receipt(setup_root: Path, scope_sha: str) -> dict:
    receipt = _read_json(setup_root / 'controls/setup-checked/receipt.json')
    if (receipt.get('kind') != 'native-setup-checked-v1'
            or receipt.get('status') != 'ready'
            or receipt.get('autonomous_engagement_scope_sha256') != scope_sha):
        fail('checked_setup_not_ready')
    return receipt


def _verify_checked(command, setup: Path, *, historical: bool = False) -> None:
    args = ['setup-build-status', '--run-root', str(setup), '--verify-checked']
    if historical:
        args.append('--historical')
    code, result = command(BUILDER, *args, timeout=60)
    if (code != 0 or result.get('receipt', {}).get('status') != 'ready'
            or result['receipt'].get('kind') != 'native-setup-checked-v1'):
        fail('checked_setup_verification_failed')


def _continuation_busy(root: Path) -> bool:
    lock = root / 'controls/continuation/lease.lock'
    fd = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        return False
    finally:
        os.close(fd)


def _closeout_record(research_root: Path) -> dict | None:
    path = research_root / 'controls/closeout/result.json'
    if not path.exists():
        return None
    record = _read_json(path)
    if record.get('kind') != 'native-agent-closeout-v1':
        fail('engagement_closeout_changed')
    return record


def _terminal(root: Path, state: dict, command) -> dict:
    research = root / 'research'
    record = _closeout_record(research)
    if record is None:
        fail('engagement_closeout_missing')
    record_sha = _sha(research / 'controls/closeout/result.json')
    code, confirmed = command(CLOSEOUT, '--run-root', str(research),
                              '--wait-seconds', '0', timeout=90)
    if (code != 0 or confirmed.get('status') != record.get('status')
            or confirmed.get('record_sha256') != record_sha):
        fail('engagement_closeout_readback_failed')
    status = _status(command, research)
    if (status['status'] != 'stopped_complete'
            or record.get('status') not in ('complete_internal_candidate', 'stopped_incomplete')
            or record.get('cleanup', {}).get('resource_absence') is not True):
        fail('engagement_cleanup_not_verified')
    phase = 'complete' if record['status'] == 'complete_internal_candidate' else 'incomplete'
    _advance(root, state, phase, closeout_sha256=record_sha)
    return {'status': record['status'], 'engagement_root': str(root),
            'setup_root': str(root / 'setup'), 'research_root': str(research),
            'closeout_sha256': state['closeout_sha256']}


def _latest_setup_dispatch(current: dict) -> dict:
    identity = (current.get('setup') or {}).get('last_dispatch_id')
    rows = [row for row in current.get('dispatches', [])
            if row.get('dispatch_id') == identity]
    if not isinstance(identity, str) or len(rows) != 1:
        fail('setup_dispatch_readback_unavailable')
    return rows[0]


def _recover_pending(root: Path, state: dict, command) -> None:
    pending = state['pending']
    if pending is None:
        return
    action = pending['action']
    setup, research = root / 'setup', root / 'research'
    if action == 'setup_prepare':
        if (setup / 'plan.json').exists() and _status(command, setup)['status'] == 'prepared':
            _advance(root, state, 'setup_prepared')
            return
    elif action == 'setup_start':
        if _status(command, setup)['status'] == 'active':
            _advance(root, state, 'setup_active')
            return
    elif action == 'setup_turn':
        current = _status(command, setup)
        rows = current.get('dispatches', [])
        if (len(rows) == pending['before_dispatches'] + 1
                and (latest := _latest_setup_dispatch(current)).get('role') == 'researcher'
                and latest.get('status') == 'acknowledged'):
            _advance(root, state, 'setup_turn_done',
                     setup_session_id=latest.get('session_id'))
            return
    elif action == 'setup_resume':
        current = _status(command, setup)
        rows = current.get('dispatches', [])
        if (len(rows) == pending['before_dispatches'] + 1
                and (latest := _latest_setup_dispatch(current)).get('role') == 'resume'
                and latest.get('status') == 'acknowledged'
                and latest.get('session_id') == state.get('setup_session_id')):
            _advance(root, state, 'setup_turn_done')
            return
    elif action == 'setup_freeze':
        current = _status(command, setup)
        if current.get('setup', {}).get('frozen_proposal_receipt_sha256'):
            _advance(root, state, 'setup_frozen')
            return
    elif action == 'setup_stop':
        _call(command, NATIVE, ['stop', '--run-root', str(setup)], timeout=30,
              statuses=('stop_requested', 'not_active'))
        _stopped(command, setup)
        _advance(root, state, 'setup_stopped')
        return
    elif action == 'setup_build':
        code, value = command(BUILDER, 'setup-build-status', '--run-root', str(setup),
                              timeout=30)
        if code == 0 and value.get('status') == 'ready':
            _verify_checked(command, setup)
            _advance(root, state, 'built')
            return
        if value.get('status') in ('unknown_effect', 'cleanup_unresolved'):
            if pending.get('reconcile_attempted'):
                fail('build_reconciliation_outcome_unknown')
            state['pending']['reconcile_attempted'] = True
            _write(root / 'state.json', state)
            recovered_code, recovered = command(BUILDER, 'setup-build-reconcile',
                                                '--run-root', str(setup), timeout=90)
            if recovered_code == 0 and recovered.get('status') == 'ready':
                _verify_checked(command, setup)
                _advance(root, state, 'built')
                return
    elif action == 'research_prepare':
        plan_path = research / 'plan.json'
        if plan_path.exists():
            plan = _read_json(plan_path)
            if (plan.get('autonomous_engagement') and plan.get('checked_setup')
                    and plan.get('scope_sha256') == state['scope_sha256']):
                _advance(root, state, 'research_prepared')
                return
    elif action == 'research_start':
        if _status(command, research)['status'] == 'active':
            _advance(root, state, 'research_active')
            return
    elif action == 'research_continue':
        if _closeout_record(research) is not None:
            _terminal(root, state, command)
            return
        if _continuation_busy(research):
            return
        # The continuation controller owns its dispatch journal and lease. It
        # may be re-entered; a pending turn is closed incomplete, not replayed.
        state['pending'] = None
        _write(root / 'state.json', state)
        return
    fail('engagement_pending_effect_unresolved')


def _build_cleanup(setup: Path, command) -> dict:
    code, current = command(BUILDER, 'setup-build-status', '--run-root', str(setup),
                            timeout=30)
    status = current.get('status')
    if code == 0 and status == 'not_dispatched':
        return {'status': 'not_dispatched', 'absent': True}
    if code == 0 and status == 'ready':
        _verify_checked(command, setup, historical=True)
        return {'status': 'ready', 'absent': True}
    if status in ('blocked', 'blocked_reconciled', 'unknown_effect', 'cleanup_unresolved'):
        code, current = command(BUILDER, 'setup-build-reconcile', '--run-root',
                                str(setup), timeout=90)
        if code == 0 and current.get('status') == 'ready':
            _verify_checked(command, setup, historical=True)
            return {'status': 'ready', 'absent': True}
        cleanup = current.get('cleanup') or {}
        if (code == 0 and current.get('status') == 'blocked_reconciled'
                and cleanup.get('status') == 'complete'
                and cleanup.get('absent') is True):
            return {'status': 'blocked_reconciled', 'absent': True}
    fail('build_cleanup_unresolved')


def _halt(root: Path, state: dict, command, reason: str) -> dict:
    cleanup = None
    build_cleanup = None
    setup, research = root / 'setup', root / 'research'
    target = (research if state['phase'] in ('research_active', 'complete') or
              (state['pending'] or {}).get('action') in ('research_start', 'research_continue')
              else setup)
    try:
        if (target / 'plan.json').exists():
            current = _status(command, target)
            first_status = current['status']
            if current['status'] != 'stopped_complete':
                command(NATIVE, 'stop', '--run-root', str(target), timeout=30)
            if current['status'] == 'prepared' and (state['pending'] or {}).get(
                    'action') in ('setup_start', 'research_start'):
                pid = (state['pending'] or {}).get('pid')
                owner_alive = pid is None
                for _ in range(450):
                    if pid is not None:
                        try:
                            os.kill(pid, 0)
                            owner_alive = True
                        except ProcessLookupError:
                            owner_alive = False
                            break
                    time.sleep(.2)
                    current = _status(command, target)
                    if current['status'] != 'prepared':
                        break
                if current['status'] == 'prepared' and owner_alive:
                    fail('owner_start_outcome_unknown')
                if current['status'] == 'prepared':
                    cleanup = {'status': 'not_started'}
            if first_status == 'prepared' and current['status'] == 'active':
                command(NATIVE, 'stop', '--run-root', str(target), timeout=30)
            if target == research:
                if current['status'] != 'prepared':
                    _, cleanup = command(CLOSEOUT, '--run-root', str(research),
                                         '--wait-seconds', '120', timeout=150)
            elif (current['status'] == 'prepared' and cleanup is None
                  and state['phase'] == 'setup_prepared' and state['pending'] is None):
                cleanup = {'status': 'not_started'}
            elif current['status'] != 'prepared':
                cleanup = _stopped(command, setup, seconds=150)
    except (DriverError, OSError, ValueError):
        cleanup = {'status': 'unverified'}
    if (state['pending'] or {}).get('action') == 'setup_build':
        try:
            build_cleanup = _build_cleanup(setup, command)
        except (DriverError, OSError, ValueError, KeyError, TypeError):
            build_cleanup = {'status': 'unverified', 'absent': False}
    cleanup_status = cleanup.get('status') if isinstance(cleanup, dict) else 'unverified'
    if build_cleanup is not None and build_cleanup.get('absent') is not True:
        cleanup_status = 'unverified'
    state.update(phase='incomplete', error=reason,
                 cleanup={'status': cleanup_status,
                          **({'build': build_cleanup} if build_cleanup is not None else {})})
    _write(root / 'state.json', state)
    return {'status': 'stopped_incomplete' if state['cleanup']['status'] in
            ('stopped_complete', 'stopped_incomplete', 'not_started') else 'cleanup_unverified',
            'reason': reason, 'engagement_root': str(root),
            'cleanup': state['cleanup']}


def drive(root: Path, *, command=_command, spawn_owner=_spawn_owner) -> dict:
    root = _private_root(root)
    with _lease(root):
        try:
            state = _state(root)
            inputs = _inputs(root / 'inputs.json')
        except (DriverError, OSError, ValueError, KeyError, TypeError):
            stops = {}
            for name in ('setup', 'research'):
                run_root = root / name
                if (run_root / 'plan.json').exists():
                    try:
                        _, stops[name] = command(NATIVE, 'stop', '--run-root', str(run_root),
                                                 timeout=30)
                    except (OSError, ValueError):
                        stops[name] = {'status': 'stop_request_unknown'}
            _write(root / 'emergency-hold.json', {
                'kind': 'native-engagement-emergency-hold-v1',
                'reason': 'driver_state_or_inputs_changed', 'stop_requests': stops})
            fail('engagement_state_or_inputs_changed')
        if (state['phase'] == 'incomplete'
                and (state.get('cleanup') or {}).get('status') == 'unverified'):
            return _halt(root, state, command, state.get('error') or 'engagement_cleanup_unverified')
        if state['phase'] in ('complete', 'incomplete'):
            return {'status': state['phase'], 'engagement_root': str(root),
                    'reason': state.get('error')}
        try:
            if _sha(Path(inputs['scope_file'])) != state['scope_sha256']:
                fail('engagement_scope_changed')
            scope = _scope(inputs)
            _recover_pending(root, state, command)
            if (state['pending'] or {}).get('action') == 'research_continue':
                return {'status': 'in_progress', 'engagement_root': str(root),
                        'phase': state['phase']}
            while state['phase'] not in ('complete', 'incomplete'):
                phase = state['phase']
                setup, research = root / 'setup', root / 'research'
                if phase == 'initialized':
                    _pending(root, state, 'setup_prepare')
                    words = ['prepare', '--setup-only', '--run-root', str(setup),
                             '--source', inputs['source'], '--brief', inputs['brief'],
                             '--scope-file', inputs['scope_file'],
                             '--scope-sha256', state['scope_sha256'],
                             '--setup-engagement-id', scope['engagement_id'],
                             '--setup-operator-id', scope['operator_id'],
                             '--setup-scope-signature', inputs['scope_signature'],
                             '--setup-allowed-signers', inputs['allowed_signers'],
                             '--setup-trusted-fingerprint', inputs['trusted_fingerprint'],
                             '--relay', inputs['relay'], '--relay-sha256', _sha(Path(inputs['relay'])),
                             '--runtime-ca', inputs['runtime_ca'],
                             '--runtime-ca-sha256', _sha(Path(inputs['runtime_ca'])),
                             '--image-id', scope['image_id'], '--platform', scope['platform'],
                             '--model', scope['model'], '--provider-route', scope['provider_route'],
                             '--max-connections', str(scope['setup']['limits']['max_connections']),
                             '--max-bytes', str(scope['setup']['limits']['max_bytes']),
                             '--duration-seconds', str(scope['setup']['limits']['duration_seconds']),
                             '--setup-max-workspace-bytes', str(scope['setup']['max_workspace_bytes'])]
                    _call(command, NATIVE, words, timeout=180,
                          statuses=('prepared_provider_free',))
                    _advance(root, state, 'setup_prepared')
                elif phase == 'setup_prepared':
                    _pending(root, state, 'setup_start')
                    state['pending']['pid'] = spawn_owner(root, NATIVE, setup, inputs)
                    _write(root / 'state.json', state)
                    _active(command, setup)
                    _advance(root, state, 'setup_active')
                elif phase == 'setup_active':
                    current = _status(command, setup)
                    _pending(root, state, 'setup_turn', before_dispatches=len(current['dispatches']))
                    result = _call(command, NATIVE, ['setup-turn', '--run-root', str(setup)],
                                   timeout=scope['setup']['limits']['duration_seconds'] + 90,
                                   statuses=('acknowledged',))
                    _advance(root, state, 'setup_turn_done',
                             setup_session_id=result.get('session_id'))
                elif phase == 'setup_turn_done':
                    _pending(root, state, 'setup_freeze')
                    try:
                        _call(command, NATIVE, ['setup-freeze', '--run-root', str(setup)],
                              timeout=90, statuses=('frozen_proposal',))
                    except DriverError as error:
                        reason = str(error)
                        if (setup / 'controls/setup-output/receipt.json').exists():
                            _advance(root, state, 'setup_frozen')
                            continue
                        attempts = state.get('setup_revision_attempts', 0)
                        session = state.get('setup_session_id')
                        if (reason not in REVISABLE_FREEZE_ERRORS or attempts >= 2
                                or not isinstance(session, str)
                                or not re.fullmatch(r'ses_[A-Za-z0-9]{1,64}', session)):
                            raise
                        prompt = root / f'setup-feedback-{attempts + 1}.md'
                        _write_prompt(prompt, reason)
                        state['pending'] = None
                        state['setup_revision_attempts'] = attempts + 1
                        _write(root / 'state.json', state)
                        current = _status(command, setup)
                        _pending(root, state, 'setup_resume',
                                 before_dispatches=len(current['dispatches']),
                                 prompt_sha256=_sha(prompt))
                        _call(command, NATIVE,
                              ['setup-resume', '--run-root', str(setup),
                               '--session', session, '--prompt-file', str(prompt)],
                              timeout=scope['setup']['limits']['duration_seconds'] + 90,
                              statuses=('acknowledged',))
                        _advance(root, state, 'setup_turn_done')
                        continue
                    _advance(root, state, 'setup_frozen')
                elif phase == 'setup_frozen':
                    _pending(root, state, 'setup_stop')
                    _call(command, NATIVE, ['stop', '--run-root', str(setup)],
                          timeout=30, statuses=('stop_requested', 'not_active'))
                    _stopped(command, setup)
                    _advance(root, state, 'setup_stopped')
                elif phase == 'setup_stopped':
                    _pending(root, state, 'setup_build')
                    try:
                        _call(command, BUILDER,
                              ['setup-build', '--run-root', str(setup),
                               '--dependency-catalog', inputs['dependency_catalog']],
                              timeout=900, statuses=('ready',))
                    except DriverError:
                        _recover_pending(root, state, command)
                        if state['phase'] == 'built':
                            continue
                        raise
                    _verify_checked(command, setup)
                    _advance(root, state, 'built')
                elif phase == 'built':
                    checked = _checked_receipt(setup, state['scope_sha256'])
                    _pending(root, state, 'research_prepare')
                    cushion = 0
                    for attempt in range(3):
                        limits = _research_limits(scope, checked)
                        duration = limits['duration_seconds'] - cushion
                        if duration < 30:
                            fail('engagement_residual_exhausted')
                        started = time.monotonic()
                        try:
                            _call(command, NATIVE, ['prepare-checked', '--run-root', str(research),
                                                   '--checked-setup-root', str(setup),
                                                   '--scope-file', str(setup / 'controls/scope.md'),
                                                   '--scope-sha256', state['scope_sha256'],
                                                   '--research-scope-signature',
                                                   str(setup / 'controls/setup-scope.sig'),
                                                   '--research-allowed-signers',
                                                   str(setup / 'controls/setup-allowed-signers'),
                                                   '--max-connections', str(limits['max_connections']),
                                                   '--max-bytes', str(limits['max_bytes']),
                                                   '--duration-seconds', str(duration)],
                                  timeout=180, statuses=('prepared_provider_free',))
                        except DriverError as error:
                            if (str(error) != 'engagement_research_allowance_mismatch'
                                    or attempt == 2 or research.exists() or research.is_symlink()):
                                raise
                            cushion += max(20, int(time.monotonic() - started) + 10)
                            continue
                        break
                    _advance(root, state, 'research_prepared')
                elif phase == 'research_prepared':
                    _pending(root, state, 'research_start')
                    state['pending']['pid'] = spawn_owner(root, NATIVE, research, inputs)
                    _write(root / 'state.json', state)
                    _active(command, research)
                    _advance(root, state, 'research_active')
                elif phase == 'research_active':
                    _pending(root, state, 'research_continue')
                    _, result = command(NATIVE, 'continue', '--run-root', str(research),
                                        '--max-invocations', '512',
                                        timeout=max(120, int((_deadline(scope) -
                                            datetime.now(timezone.utc)).total_seconds()) + 180))
                    if result.get('status') not in ('complete_internal_candidate',
                                                    'stopped_incomplete'):
                        fail(result.get('code', 'engagement_continuation_failed'))
                    if result['status'] == 'complete_internal_candidate' or _closeout_record(research):
                        return _terminal(root, state, command)
                    fail('engagement_closeout_missing')
            return {'status': state['phase'], 'engagement_root': str(root)}
        except (DriverError, OSError, ValueError, KeyError, TypeError) as error:
            reason = str(error) if isinstance(error, DriverError) else 'engagement_input_unavailable'
            return _halt(root, state, command, reason)


def main(argv: list[str] | None = None) -> int:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    run = commands.add_parser('run', help='begin one scope-only engagement')
    run.add_argument('--engagement-root', type=Path, required=True)
    run.add_argument('--inputs', type=Path, required=True)
    resume = commands.add_parser('resume', help='continue one durable engagement')
    resume.add_argument('--engagement-root', type=Path, required=True)
    status = commands.add_parser('status', help='read the driver phase without dispatch')
    status.add_argument('--engagement-root', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'run':
            _initialize(args.engagement_root, args.inputs)
        if args.command == 'status':
            root = _private_root(args.engagement_root)
            state = _state(root)
            result = {'status': state['phase'], 'pending': state['pending'],
                      'engagement_root': str(root), 'error': state.get('error'),
                      'cleanup': state.get('cleanup')}
        else:
            result = drive(args.engagement_root)
    except (DriverError, OSError, ValueError, KeyError, TypeError) as error:
        code = str(error)
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,100}', code):
            code = 'engagement_driver_unavailable'
        result = {'status': 'rejected', 'code': code}
    print(json.dumps(result, sort_keys=True))
    return 0 if (args.command == 'status' and result['status'] != 'rejected') or result['status'] in (
        'complete_internal_candidate', 'complete') else 2


if __name__ == '__main__':
    raise SystemExit(main())
