#!/usr/bin/env python3
"""Agent-owned internal closeout for one approved native source run.

The agent writes RESULT.md and a NEXT.json stop proposal. This host routine
binds those bytes to an existing fresh review, requests the existing owner stop,
and checks teardown before returning an internal candidate. It never files,
deploys, or confirms a security effect.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time

import native_continuation as continuation
import native_research as runner

KIND = 'native-agent-closeout-v1'
HEADINGS = ('Supported effects', 'Controls', 'Contrary evidence', 'Tested paths',
            'Untested paths', 'Assistance', 'Unfinished leads', 'Limits')
SAFETY_CLAIM = re.compile(
    r'(?i)\b(?:the\s+)?(?:target|application|system)\s+(?:is|was)\s+'
    r'(?:safe|secure|vulnerability[- ]free)\b|\bno\s+vulnerabilities\b|'
    r'\bfull(?:y)?\s+cover(?:ed|age)\b')
HEX32 = re.compile(r'[0-9a-f]{32}\Z')
HEX64 = re.compile(r'[0-9a-f]{64}\Z')
RESOURCE_NAME = re.compile(r'[A-Za-z0-9_.-]{1,128}\Z')


class CloseoutError(RuntimeError):
    pass


def _fail(reason: str) -> None:
    raise CloseoutError(reason)


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def _area(root: Path) -> Path:
    path = root / 'controls/closeout'
    path.mkdir(mode=0o700, exist_ok=True)
    entry = path.stat(follow_symlinks=False)
    if (not stat.S_ISDIR(entry.st_mode) or entry.st_uid != os.getuid()
            or entry.st_mode & 0o077):
        _fail('closeout_directory_invalid')
    return path


def _write_once(path: Path, value: object) -> str:
    if path.exists() or path.is_symlink():
        if runner._read_json(path) != value:
            _fail('closeout_record_changed')
    else:
        runner._write_json(path, value, once=True)
    return runner._sha(path)


def _draft(root: Path, module=None) -> tuple[str | None, str | None]:
    """Preserve safe ordinary result bytes; never synthesize a missing draft."""
    if module is None:
        return None, None
    path = root / 'researcher/project/RESULT.md'
    try:
        file = runner._file(path)
        data = file.read_bytes()
    except (runner.NativeResearchError, OSError):
        return None, None
    if not 0 < len(data) <= 128 * 1024:
        return None, None
    try:
        text = data.decode('utf-8')
        module.validate_public_bytes(data)
    except (UnicodeError, ValueError):
        return None, None
    digest = _hash(data)
    frozen = _area(root) / ('RESULT-' + digest + '.md')
    if frozen.exists() or frozen.is_symlink():
        if runner._sha(runner._file(frozen, private=True)) != digest:
            _fail('closeout_draft_changed')
    else:
        descriptor = os.open(frozen, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    if runner._sha(file) != digest:
        _fail('closeout_result_changed')
    return digest, text


def _result(root: Path, module) -> tuple[str, str]:
    digest, text = _draft(root, module)
    if digest is None or text is None:
        _fail('closeout_result_missing_or_unsafe')
    if SAFETY_CLAIM.search(text):
        _fail('closeout_target_safety_claim')
    for heading in HEADINGS:
        match = re.search(r'(?ims)^##\s+' + re.escape(heading) +
                          r'\s*\n(.*?)(?=^##\s+|\Z)', text)
        if not match or not match.group(1).strip():
            _fail('closeout_result_incomplete')
    return digest, text


def _allowance(root: Path, plan: dict) -> dict:
    runner._approval_active(root)
    snapshot = runner.allowance_snapshot(root)
    limits = snapshot.get('hard_limits')
    if (snapshot.get('active') is not True or limits != plan['limits']
            or not isinstance(snapshot.get('run_identity'), dict)
            or type(snapshot.get('used_tunnels')) is not int
            or type(snapshot.get('charged_tunnel_bytes')) is not int
            or snapshot['used_tunnels'] < 0 or snapshot['charged_tunnel_bytes'] < 0
            or snapshot['used_tunnels'] >= limits['max_connections']
            or snapshot['charged_tunnel_bytes'] >= limits['max_bytes']
            or not runner.run_active(root)):
        _fail('closeout_allowance_or_run_inactive')
    return snapshot


def _unresolved(root: Path, state: dict) -> list[str]:
    reasons = []
    if state.get('pending') is not None:
        reasons.append('native_continuation_pending')
    source = state.get('source_action')
    if source and source.get('phase') != 'captured':
        reasons.append('source_action_' + str(source.get('phase')))
    review = state.get('review_action')
    if review and review.get('phase') in ('dispatched', 'incomplete'):
        reasons.append('review_' + str(review['phase']))
    reasons.extend('native_dispatch_' + str(item) for item in runner._unresolved_dispatches(root))
    return reasons


def _review(root: Path, state: dict, nxt: dict, result_sha: str,
            allowance: dict, plan: dict) -> dict:
    prior = state.get('review_action')
    if not isinstance(prior, dict) or prior.get('phase') != 'captured':
        _fail('closeout_fresh_review_required')
    identity, role = prior.get('review_id'), prior.get('role')
    if (not isinstance(identity, str) or not HEX32.fullmatch(identity)
            or role not in ('reviewer-1', 'reviewer-2')):
        _fail('closeout_review_binding_invalid')
    module = runner._load_review_module(root)
    projection_path = root / 'controls/research/reviews' / identity / 'RESULTS.json'
    if runner._sha(runner._file(projection_path, private=True)) != prior.get('projection_sha256'):
        _fail('closeout_review_projection_changed')
    projection = runner._read_json(projection_path)
    receipt_path = root / 'controls' / ('review-' + role + '.json')
    receipt = runner._read_json(receipt_path)
    assessment, material, pin = (receipt.get('assessment'), receipt.get('material'),
                                 receipt.get('packet_pin'))
    if (projection.get('kind') != 'native-source-review-results-v1'
            or projection.get('review_id') != identity
            or projection.get('plan_sha256') != runner._sha(root / 'plan.json')
            or projection.get('status') != 'reviewed'
            or projection.get('receipt_sha256') != runner._sha(receipt_path)
            or projection.get('security_effect') != 'unproven'
            or projection.get('filing_or_escalation_authorized') is not False
            or receipt.get('kind') != 'native-source-review-v1'
            or receipt.get('status') != 'reviewed'
            or receipt.get('plan_sha256') != runner._sha(root / 'plan.json')
            or receipt.get('reviewer_role') != role
            or receipt.get('filing_or_escalation_authorized') is not False
            or receipt.get('same_original_allowance') is not True
            or not isinstance(assessment, dict)
            or assessment.get('status') != 'candidate_for_operator_review'
            or assessment != projection.get('assessment')
            or not isinstance(material, dict) or material.get('status') != 'captured'
            or not isinstance(material.get('outcome'), dict)
            or material.get('input_id') != receipt.get('input_id')
            or assessment.get('outcome') != material['outcome']
            or not isinstance(pin, dict) or not isinstance(pin.get('files'), dict)
            or pin.get('input_id') != receipt.get('input_id')
            or projection.get('input_id') != receipt.get('input_id')
            or projection.get('packet_request_sha256') != pin['files'].get('REQUEST.json')):
        _fail('closeout_review_binding_invalid')
    packet = root / 'handoff' / role
    if not module.verify_packet(packet, pin):
        _fail('closeout_review_packet_changed')
    evidence = root / 'controls/source-evidence' / role / 'RESULTS.json'
    if (receipt.get('evidence_path') != str(evidence)
            or receipt.get('evidence_sha256') != runner._sha(runner._file(evidence))):
        _fail('closeout_review_evidence_changed')
    directory = root / 'controls/continuation/reviews' / identity
    selected_sha = projection.get('selection_sha256')
    selected, _ = module._selection(directory / 'observer', directory / 'selection.json',
                                   selected_sha, module.validate_public_bytes)
    request = json.loads((packet / 'REQUEST.json').read_bytes())
    if (request.get('input_id') != receipt['input_id']
            or request.get('selection_sha256') != selected_sha
            or request.get('source_manifest_sha256') != plan['source_manifest_sha256']
            or request.get('roles') != selected['roles']
            or request.get('files') != selected['files']
            or request.get('source_paths') != selected['source_paths']):
        _fail('closeout_review_selection_changed')
    unfinished = json.loads((directory / 'observer/UNFINISHED.json').read_bytes())
    note = unfinished.get('result_note') if isinstance(unfinished, dict) else None
    reviewed_checkpoint = unfinished.get('checkpoint') if isinstance(unfinished, dict) else None
    if (not isinstance(note, dict) or not isinstance(note.get('text'), str)
            or note.get('sha256') != result_sha
            or note.get('provenance') != 'agent_statement_frozen_source'
            or _hash(note['text'].encode()) != result_sha
            or not isinstance(reviewed_checkpoint, dict)
            or unfinished.get('research_note') !=
                runner._file(root / 'researcher/RESEARCH.md').read_text()):
        _fail('closeout_review_result_changed')
    conditions = json.loads((directory / 'observer/CONDITIONS.json').read_bytes())
    current = conditions.get('current_source') if isinstance(conditions, dict) else None
    if (not isinstance(current, dict) or current.get('RESULT.md') != result_sha
            or runner._inventory(root / 'researcher/project') != current
            or runner._inventory(directory / 'current-source') != current
            or conditions.get('current_files') != continuation._review_tree(
                directory / 'current-source', current, module)):
        _fail('closeout_review_source_changed')
    raw = json.loads((directory / 'observer/RAW.json').read_bytes())
    actions = continuation._review_source_actions(root, state, module)
    if not isinstance(raw, dict) or raw.get('source_actions') != actions:
        _fail('closeout_review_source_actions_changed')
    after = receipt.get('allowance_after')
    if after is None and isinstance(receipt.get('preparation'), dict):
        after = receipt['preparation'].get('allowance_after')
    if (not isinstance(after, dict)
            or after.get('run_identity') != allowance['run_identity']
            or type(after.get('used_tunnels')) is not int
            or type(after.get('charged_tunnel_bytes')) is not int
            or after['used_tunnels'] > allowance['used_tunnels']
            or after['charged_tunnel_bytes'] > allowance['charged_tunnel_bytes']):
        _fail('closeout_review_allowance_changed')
    outcome = material['outcome']
    decision = outcome.get('decision')
    if decision == 'reopen':
        next_check = outcome.get('next_check')
        if not isinstance(next_check, str) or not next_check.strip():
            _fail('closeout_reopen_test_missing')
        module.validate_public_bytes(next_check.encode())
        return {'decision': 'reopen', 'next_check': next_check.strip()}
    if decision not in ('raise', 'retain'):
        _fail('closeout_review_did_not_accept_result')
    if ((state.get('last_strong_lead') is True
         or reviewed_checkpoint.get('strong_lead') is True)
            and nxt.get('strong_lead') is False):
        leads = outcome.get('lead_dispositions')
        if (not isinstance(leads, list) or not leads
                or any(not isinstance(item, dict)
                       or item.get('decision') not in ('retain', 'narrow', 'reject')
                       or not all(isinstance(item.get(key), str) and item[key].strip()
                                  for key in ('basis_examined', 'uncertain_condition', 'next_check'))
                       for item in leads)):
            _fail('closeout_strong_lead_review_missing')
    return {'decision': decision, 'review_id': identity,
            'input_id': receipt['input_id'], 'receipt_sha256': runner._sha(receipt_path),
            'packet_request_sha256': pin['files']['REQUEST.json'],
            'source_action_corpus_sha256': _hash(_json(actions))}


def _resources_absent(root: Path) -> dict:
    resources = runner._read_json(root / 'controls/resources.json')
    rows = resources.get('resources')
    daemon_id = resources.get('docker_daemon_id')
    if (not isinstance(resources.get('nonce'), str) or not HEX32.fullmatch(resources['nonce'])
            or not isinstance(rows, list) or not rows
            or not isinstance(daemon_id, str) or not 1 <= len(daemon_id) <= 128):
        _fail('closeout_resource_record_invalid')
    if runner._docker_daemon_id() != daemon_id:
        _fail('closeout_docker_daemon_changed')
    readback = []
    for row in rows:
        if (not isinstance(row, dict) or row.get('kind') not in ('container', 'network')
                or not isinstance(row.get('name'), str)
                or not RESOURCE_NAME.fullmatch(row['name'])
                or not isinstance(row.get('id'), str) or not HEX64.fullmatch(row['id'])):
            _fail('closeout_resource_record_invalid')
        kind, identity, name = row['kind'], row['id'], row['name']
        by_id = runner._docker(kind, 'ls', '-a' if kind == 'container' else '--no-trunc',
                               *(['--no-trunc'] if kind == 'container' else []),
                               '--filter', 'id=' + identity, '--format', '{{.ID}}')
        by_name = runner._docker(kind, 'ls', '-a' if kind == 'container' else '--no-trunc',
                                 *(['--no-trunc'] if kind == 'container' else []),
                                 '--filter', 'name=^' + ('/' if kind == 'container' else '')
                                 + name + '$', '--format', '{{.ID}}')
        absent = not by_id.stdout.strip() and not by_name.stdout.strip()
        readback.append({'kind': kind, 'name': name, 'id': identity, 'absent': absent})
    if runner._docker_daemon_id() != daemon_id:
        _fail('closeout_docker_daemon_changed')
    return {'resource_absence': all(row['absent'] for row in readback), 'resources': readback,
            'resources_sha256': runner._sha(root / 'controls/resources.json')}


def _final_readback(root: Path) -> dict:
    controls = root / 'controls'
    final_path = controls / 'final.json'
    final = runner._read_json(final_path)
    cleanup_path = controls / 'cleanup.json'
    cleanup = runner._read_json(cleanup_path)
    snapshot_path = controls / 'host-snapshot.json'
    snapshot = runner._read_json(snapshot_path)
    revoked_path = controls / 'native-state/REVOKED'
    revoked = runner._read_json(revoked_path)
    resources = runner._read_json(controls / 'resources.json')
    ids = [row.get('id') for row in resources.get('resources', [])
           if isinstance(row, dict) and row.get('kind') == 'container']
    if (final.get('status') != 'stopped_complete'
            or not isinstance(final.get('native_stop'), dict)
            or final['native_stop'].get('status') != 'stopped'
            or final.get('host_snapshot', {}).get('status') != 'complete'
            or final['host_snapshot'].get('receipt_path') != str(snapshot_path)
            or final['host_snapshot'].get('receipt_sha256') != runner._sha(snapshot_path)
            or snapshot.get('kind') != 'native-research-host-byte-receipt-v1'
            or snapshot.get('status') != 'complete'
            or snapshot.get('plan_sha256') != runner._sha(root / 'plan.json')
            or snapshot.get('native_stop', {}).get('revoked_sha256') != runner._sha(revoked_path)
            or revoked.get('producers_verified_stopped') is not True
            or revoked.get('ids') != ids
            or final.get('origin_stop', {}).get('status') not in ('complete', 'not_configured')
            or final.get('origin_cleanup', {}).get('status') not in ('complete', 'not_configured')
            or final.get('capture_stop', {}).get('status') not in ('complete', 'not_configured')
            or final.get('capture_cleanup', {}).get('status') not in ('complete', 'not_configured')
            or final.get('cleanup') != cleanup
            or cleanup.get('status') != 'complete'):
        _fail('closeout_owner_cleanup_unverified')
    readback = _resources_absent(root)
    expected = [{'kind': row['kind'], 'name': row['name'], 'absent': True}
                for row in reversed(resources['resources'])]
    if not readback['resource_absence'] or cleanup.get('resources') != expected:
        _fail('closeout_remaining_effect_or_resource')
    unresolved = _unresolved(root, continuation._state(root))
    return {'status': 'verified', 'final_sha256': runner._sha(final_path),
            'cleanup_sha256': runner._sha(cleanup_path),
            'host_snapshot_sha256': runner._sha(snapshot_path),
            'native_revoked_sha256': runner._sha(revoked_path),
            **readback, 'unresolved_effects': unresolved, 'target_state': 'not_assessed'}


def _wait_final(root: Path, seconds: int, sleep_fn) -> bool:
    deadline = time.monotonic() + seconds
    while True:
        if (root / 'controls/final.json').exists():
            try:
                with runner._poststop_read_lock(root):
                    return True
            except runner.NativeResearchError as error:
                if str(error) != 'live_owner_present':
                    raise
        if time.monotonic() >= deadline:
            return False
        sleep_fn(min(.2, max(0.0, deadline - time.monotonic())))


def _hold(root: Path, status: str, reason: str, marker_sha: str,
          result_sha: str | None) -> dict:
    controls = root / 'controls'
    final_path, resources_path = controls / 'final.json', controls / 'resources.json'
    final_sha = runner._sha(final_path) if final_path.exists() else None
    resources_sha = runner._sha(resources_path) if resources_path.exists() else None
    try:
        resources = runner._read_json(resources_path).get('resources', [])
    except (runner.NativeResearchError, OSError, ValueError, TypeError):
        resources = None
    try:
        unresolved = _unresolved(root, continuation._state(root))
    except (runner.NativeResearchError, OSError, ValueError, TypeError):
        unresolved = ['effect_readback_unavailable']
    record = {'kind': 'native-closeout-hold-v1', 'status': status, 'reason': reason,
              'result_sha256': result_sha, 'stop_request_sha256': marker_sha,
              'final_sha256': final_sha, 'resources_sha256': resources_sha,
              'owned_resources': resources, 'unresolved_effects': unresolved,
              'target_safety': 'not_established',
              'filing_or_deployment_authorized': False}
    suffix = _hash(_json(record))
    path = _area(root) / ('hold-' + status + '-' + suffix + '.json')
    digest = _write_once(path, record)
    return {'status': status, 'record_path': str(path), 'record_sha256': digest,
            'result_sha256': result_sha, 'unresolved_effects': unresolved,
            'filing_or_deployment_authorized': False}


def _stop_and_readback(root: Path, *, reason: str, accepted: bool, result_sha: str | None,
                       request: dict | None, wait_seconds: int, stop_fn, sleep_fn) -> dict:
    area = _area(root)
    marker = {'kind': 'native-closeout-stop-request-v1', 'reason': reason,
              'plan_sha256': runner._sha(root / 'plan.json'),
              'result_sha256': result_sha,
              'request_sha256': runner._sha(area / 'request.json') if request else None}
    marker_path = area / 'stop-request.json'
    first = not marker_path.exists()
    marker_sha = _write_once(marker_path, marker)
    if first or not (root / 'controls/final.json').exists():
        try:
            stop_fn(root)
        except Exception:
            return _hold(root, 'stop_request_unknown', reason, marker_sha, result_sha)
    try:
        final_ready = _wait_final(root, wait_seconds, sleep_fn)
    except (runner.NativeResearchError, OSError, ValueError, TypeError):
        return _hold(root, 'cleanup_unverified', reason, marker_sha, result_sha)
    if not final_ready:
        return _hold(root, 'cleanup_pending', reason, marker_sha, result_sha)
    try:
        cleanup = _final_readback(root)
    except (CloseoutError, runner.NativeResearchError, OSError, ValueError,
            TypeError, KeyError, AttributeError):
        return _hold(root, 'cleanup_unverified', reason, marker_sha, result_sha)
    if result_sha is not None:
        try:
            if runner._sha(runner._file(root / 'researcher/project/RESULT.md')) != result_sha:
                _fail('closeout_result_changed_after_stop')
        except (CloseoutError, runner.NativeResearchError, OSError):
            return _hold(root, 'cleanup_unverified', reason, marker_sha, result_sha)
    record = {'kind': KIND, 'status': ('complete_internal_candidate' if accepted
                                     and not cleanup['unresolved_effects']
                                     else 'stopped_incomplete'),
              'reason': reason, 'plan_sha256': runner._sha(root / 'plan.json'),
              'result_sha256': result_sha, 'request': request,
              'stop_request_sha256': marker_sha, 'cleanup': cleanup,
              'security_effect': 'unproven', 'target_safety': 'not_established',
              'filing_or_deployment_authorized': False}
    path = area / 'result.json'
    digest = _write_once(path, record)
    return {'status': record['status'], 'record_path': str(path),
            'record_sha256': digest, 'cleanup': {'resource_absence': True},
            'security_effect': 'unproven', 'filing_or_deployment_authorized': False}


def _resume_stop(root: Path, area: Path, wait_seconds: int, stop_fn, sleep_fn) -> dict | None:
    path = area / 'stop-request.json'
    if not path.exists():
        return None
    marker = runner._read_json(path)
    request_sha = marker.get('request_sha256')
    result_sha = marker.get('result_sha256')
    if (marker.get('kind') != 'native-closeout-stop-request-v1'
            or marker.get('plan_sha256') != runner._sha(root / 'plan.json')
            or not isinstance(marker.get('reason'), str)
            or (result_sha is not None and (not isinstance(result_sha, str)
                                            or not HEX64.fullmatch(result_sha)))):
        _fail('closeout_stop_request_changed')
    request = None
    if request_sha is not None:
        request_path = area / 'request.json'
        if (not isinstance(request_sha, str) or not HEX64.fullmatch(request_sha)
                or runner._sha(runner._file(request_path, private=True)) != request_sha):
            _fail('closeout_request_changed')
        request = runner._read_json(request_path)
        if (request.get('kind') != 'native-closeout-request-v1'
                or request.get('result_sha256') != result_sha):
            _fail('closeout_request_changed')
    return _stop_and_readback(root, reason=marker['reason'], accepted=request is not None,
                              result_sha=result_sha, request=request,
                              wait_seconds=wait_seconds, stop_fn=stop_fn, sleep_fn=sleep_fn)


def closeout(run_root: Path, *, wait_seconds: int = 120, stop_fn=None,
             sleep_fn=time.sleep, forced_stop_reason: str | None = None) -> dict:
    root = runner._private_root(Path(run_root))
    area = _area(root)
    plan = runner._verified_plan(root)
    if 'source_only' not in plan:
        return {'status': 'closeout_incomplete', 'reason': 'source_profile_required'}
    stop_fn = stop_fn or runner.stop
    prior = _resume_stop(root, area, wait_seconds, stop_fn, sleep_fn)
    if prior is not None:
        return prior
    state = continuation._state(root)
    if forced_stop_reason is not None:
        if not isinstance(forced_stop_reason, str) or not forced_stop_reason.strip():
            _fail('closeout_stop_reason_invalid')
        try:
            module = runner._load_review_module(root)
        except (runner.NativeResearchError, OSError, ValueError, TypeError):
            module = None
        draft_sha, _ = _draft(root, module)
        return _stop_and_readback(root, reason=forced_stop_reason, accepted=False,
                                  result_sha=draft_sha, request=None,
                                  wait_seconds=wait_seconds, stop_fn=stop_fn,
                                  sleep_fn=sleep_fn)
    stop_reason = continuation._stop(root)
    try:
        unresolved = _unresolved(root, state)
    except (runner.NativeResearchError, OSError, ValueError, TypeError):
        unresolved = ['unresolved_effect_readback_unavailable']
    try:
        allowance = _allowance(root, plan)
        authority_reason = None
    except (runner.NativeResearchError, CloseoutError, OSError, ValueError, TypeError) as error:
        allowance, authority_reason = None, (str(error) if isinstance(
            error, (runner.NativeResearchError, CloseoutError)) else 'authority_unavailable')
    if stop_reason or unresolved or authority_reason:
        try:
            module = runner._load_review_module(root)
        except (runner.NativeResearchError, OSError, ValueError, TypeError):
            module = None
        draft_sha, _ = _draft(root, module)
        return _stop_and_readback(root, reason=(stop_reason or
            ('unknown_effect' if unresolved else authority_reason)), accepted=False,
            result_sha=draft_sha, request=None, wait_seconds=wait_seconds,
            stop_fn=stop_fn, sleep_fn=sleep_fn)
    module = runner._load_review_module(root)
    try:
        nxt = continuation._next(root)
        if (nxt is None or nxt.get('proposed_stop') is not True
                or nxt.get('next') is not None or nxt.get('host_action') is not None):
            _fail('closeout_stop_proposal_missing')
    except (CloseoutError, continuation.ContinuationError, runner.NativeResearchError,
            OSError, ValueError, TypeError, AttributeError) as error:
        reason = str(error) if isinstance(error, (CloseoutError, continuation.ContinuationError,
                                                 runner.NativeResearchError)) else 'closeout_result_invalid'
        return {'status': 'result_invalid', 'reason': reason}
    try:
        result_sha, _ = _result(root, module)
    except (CloseoutError, runner.NativeResearchError, OSError, ValueError,
            TypeError, AttributeError) as error:
        if nxt['last_result']['state'] in ('blocked', 'inconclusive'):
            draft_sha, _ = _draft(root, module)
            return _stop_and_readback(root, reason='blocked_or_inconclusive_draft',
                                      accepted=False, result_sha=draft_sha, request=None,
                                      wait_seconds=wait_seconds, stop_fn=stop_fn,
                                      sleep_fn=sleep_fn)
        reason = str(error) if isinstance(error, (CloseoutError, runner.NativeResearchError)) \
            else 'closeout_result_invalid'
        return {'status': 'result_invalid', 'reason': reason}
    if nxt['last_result']['state'] in ('blocked', 'inconclusive'):
        return _stop_and_readback(root, reason=nxt['last_result']['state'], accepted=False,
                                  result_sha=result_sha, request=None, wait_seconds=wait_seconds,
                                  stop_fn=stop_fn, sleep_fn=sleep_fn)
    try:
        review = _review(root, state, nxt, result_sha, allowance, plan)
    except (CloseoutError, continuation.ContinuationError, runner.NativeResearchError,
            OSError, ValueError, TypeError, KeyError, AttributeError):
        return {'status': 'review_required', 'reason': 'fresh_review_binding_unavailable',
                'result_sha256': result_sha}
    stop_now = continuation._stop(root)
    if stop_now:
        return _stop_and_readback(root, reason=stop_now, accepted=False,
                                  result_sha=result_sha, request=None,
                                  wait_seconds=wait_seconds, stop_fn=stop_fn,
                                  sleep_fn=sleep_fn)
    try:
        fresh_allowance = _allowance(root, plan)
    except (CloseoutError, runner.NativeResearchError, OSError, ValueError, TypeError):
        fresh_allowance = None
    if (fresh_allowance is None
            or fresh_allowance['run_identity'] != allowance['run_identity']
            or fresh_allowance['used_tunnels'] != allowance['used_tunnels']
            or fresh_allowance['charged_tunnel_bytes'] != allowance['charged_tunnel_bytes']):
        return _stop_and_readback(root, reason='allowance_changed_during_closeout',
                                  accepted=False, result_sha=result_sha, request=None,
                                  wait_seconds=wait_seconds, stop_fn=stop_fn,
                                  sleep_fn=sleep_fn)
    if review['decision'] == 'reopen':
        record = {'kind': 'native-closeout-reopen-v1',
                  'plan_sha256': runner._sha(root / 'plan.json'),
                  'result_sha256': result_sha,
                  'next_sha256': continuation._next_hash(root),
                  'proposal': nxt, 'review_id': state['review_action']['review_id'],
                  'review_projection_sha256': state['review_action']['projection_sha256'],
                  'next_check': review['next_check'],
                  'same_approval_and_allowance': True}
        path = area / ('reopen-' + _hash(_json(record)) + '.json')
        digest = _write_once(path, record)
        return {'status': 'reopen_required', 'next_check': review['next_check'],
                'result_sha256': result_sha, 'same_approval_and_allowance': True,
                'next_sha256': record['next_sha256'],
                'review_projection_sha256': state['review_action']['projection_sha256'],
                'reopen_record_path': str(path), 'reopen_record_sha256': digest}
    next_sha = continuation._next_hash(root)
    if (runner._sha(root / 'researcher/project/RESULT.md') != result_sha
            or continuation._next_hash(root) != next_sha):
        return {'status': 'review_required', 'reason': 'closeout_claim_changed'}
    request = {'kind': 'native-closeout-request-v1',
               'plan_sha256': runner._sha(root / 'plan.json'),
               'scope_sha256': plan['scope_sha256'],
               'approval_sha256': runner._sha(root / 'controls/approval.json'),
               'result_sha256': result_sha, 'next_sha256': next_sha,
               'result_class': ('supported' if nxt['last_result']['state'] == 'supported'
                                else 'bounded_negative'),
               'review': review, 'allowance_before': allowance,
               'coverage': nxt.get('coverage', []),
               'unfinished': nxt['last_result'].get('unresolved')}
    _write_once(area / 'request.json', request)
    return _stop_and_readback(root, reason='agent_proposed_closeout', accepted=True,
                              result_sha=result_sha, request=request, wait_seconds=wait_seconds,
                              stop_fn=stop_fn, sleep_fn=sleep_fn)


def main(argv=None, *, stop_fn=None, sleep_fn=time.sleep) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root', type=Path, required=True)
    parser.add_argument('--wait-seconds', type=int, default=120)
    args = parser.parse_args(argv)
    if not 0 <= args.wait_seconds <= 3600:
        parser.error('--wait-seconds must be between 0 and 3600')
    try:
        result = closeout(args.run_root, wait_seconds=args.wait_seconds,
                          stop_fn=stop_fn, sleep_fn=sleep_fn)
    except (CloseoutError, continuation.ContinuationError, runner.NativeResearchError,
            OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        result = {'status': 'closeout_error', 'reason': str(error) if isinstance(
            error, (CloseoutError, continuation.ContinuationError,
                    runner.NativeResearchError)) else 'closeout_unavailable'}
        print(json.dumps(result, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
