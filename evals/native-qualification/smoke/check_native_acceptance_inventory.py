#!/usr/bin/env python3
"""Inventory native #160/#162 evidence without running a provider or target."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat


SHA = re.compile(r'[0-9a-f]{64}\Z')
T06 = {'F01', 'F02', 'F03', 'F04', 'F05', 'F06', 'F07',
       'F08a', 'F08b', 'F08c', 'F08d', 'L01', 'L02', 'L03'}
ORIGIN_ROLES = {'researcher': 'target', 'resume': 'target',
                'reviewer-1': 'review-target-1', 'reviewer-2': 'review-target-2'}
ORIGIN_SOURCES = ('tools/native_origin/protocol.go', 'tools/native_origin/main_linux.go')
ARTIFACTS = {
    'T04': {'case_preflight', 'host_trace', 'pause_resume', 'clean_replay_and_controls',
            'native_review', 'workspace_diff', 'cost_and_help', 'final_output', 'cleanup'},
    'T06': {'challenge_input', 'host_trace', 'contrary_and_controls', 'native_review',
            'updated_claim_and_output', 'cost_and_cleanup'},
}
CAPTURE_TARGETS = ('target', 'review-target-1', 'review-target-2')
BASE_RECEIPTS = {'controls/final.json', 'controls/host-snapshot.json',
                 'controls/native-state/REVOKED', 'controls/producer-manifest.json'}


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def private_dir(path):
    try:
        mode = path.stat(follow_symlinks=False)
        return (path.is_absolute() and not path.is_symlink()
                and stat.S_ISDIR(mode.st_mode) and mode.st_uid == os.getuid()
                and not mode.st_mode & 0o077)
    except OSError:
        return False


def regular(path, *, private=True):
    try:
        mode = path.stat(follow_symlinks=False)
        return (not path.is_symlink() and stat.S_ISREG(mode.st_mode)
                and (not private or mode.st_uid == os.getuid() and not mode.st_mode & 0o077))
    except OSError:
        return False


def read_json(path):
    try:
        if not regular(path) or path.stat().st_size > 4 * 1024 * 1024:
            return None
        value = json.loads(path.read_bytes(), object_pairs_hook=unique_pairs)
    except (OSError, UnicodeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def unique_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('duplicate JSON key')
        value[key] = item
    return value


def relative_file(root, name, *, private=True):
    if (not isinstance(name, str) or not name or name.startswith('/')
            or '\\' in name or any(part in ('', '.', '..') for part in name.split('/'))):
        return None
    path = root
    for part in name.split('/'):
        path = path / part
        if path.is_symlink():
            return None
    return path if regular(path, private=private) else None


def source_matches(root, plan):
    expected = plan.get('source_sha256')
    if (not isinstance(expected, dict) or not expected
            or (root / 'original').is_symlink() or not (root / 'original').is_dir()):
        return False
    if (not all(isinstance(name, str) and isinstance(digest, str) and SHA.fullmatch(digest)
                and relative_file(root / 'original', name, private=False) is not None
                for name, digest in expected.items())):
        return False
    if any(sha(root / 'original' / name) != digest for name, digest in expected.items()):
        return False
    observed = set()
    for path in (root / 'original').rglob('*'):
        if path.is_symlink():
            return False
        if not path.is_dir() and not path.is_file():
            return False
        if path.is_file():
            observed.add(path.relative_to(root / 'original').as_posix())
    return observed == set(expected)


def dispatches(root, plan):
    folder = root / 'controls/dispatch'
    if not folder.is_dir() or folder.is_symlink():
        return [], False, False
    paths = sorted(path for path in folder.glob('*.json')
                   if not path.name.endswith(('.trace.json', '.pre.json', '.origin.json')))
    records = []
    traces_ok = bool(paths)
    allowance_ok = bool(paths)
    identity = None
    last = (0, 0)
    for path in paths:
        record = read_json(path)
        if record is None:
            traces_ok = allowance_ok = False
            continue
        records.append(record)
        trace = path.with_name(path.stem + '.trace.json')
        native = read_json(trace)
        traces_ok &= (record.get('kind') == 'native-dispatch-v1'
                      and record.get('dispatch_id') == path.stem
                      and record.get('status') == 'acknowledged'
                      and isinstance(record.get('session_id'), str)
                      and native is not None
                      and native.get('kind') == 'protected-native-event-trace-v1'
                      and native.get('session_id') == record.get('session_id')
                      and SHA.fullmatch(str(record.get('native_trace_sha256', ''))) is not None
                      and sha(trace) == record.get('native_trace_sha256'))
    records.sort(key=lambda row: str(row.get('created_at', '')))
    for record in records:
        before, after = record.get('pool_before'), record.get('pool_after')
        if not isinstance(before, dict) or not isinstance(after, dict):
            allowance_ok = False
            continue
        if identity is None:
            identity = before.get('run_identity')
        values = []
        for pool in (before, after):
            pair = (pool.get('used_tunnels'), pool.get('charged_tunnel_bytes'))
            if (pool.get('run_identity') != identity or not isinstance(identity, dict)
                    or pool.get('hard_limits') != plan.get('limits')
                    or not all(type(value) is int and value >= 0 for value in pair)):
                allowance_ok = False
            values.append(pair)
        if all(type(value) is int for pair in values for value in pair):
            allowance_ok &= all(a <= b <= c for a, b, c in zip(last, values[0], values[1]))
            last = values[1]
    return records, bool(traces_ok), bool(allowance_ok)


def poststop_review_candidate(root, records, researcher_sessions, plan):
    if 't01_capture' not in plan or not isinstance(plan.get('native_origin'), dict):
        return None
    for role in ('reviewer-1', 'reviewer-2'):
        path = root / 'controls' / ('poststop-review-' + role + '.json')
        receipt = read_json(path)
        if not isinstance(receipt, dict):
            continue
        reviewer_id = receipt.get('review_dispatch_id')
        if not isinstance(reviewer_id, str) or not re.fullmatch(r'[0-9a-f]{32}', reviewer_id):
            continue
        review_path = root / 'controls' / ('review-' + role + '.json')
        review = read_json(review_path)
        native = review.get('native') if isinstance(review, dict) else None
        material = review.get('material') if isinstance(review, dict) else None
        reviewer = next((row for row in records if row.get('dispatch_id') == reviewer_id
                         and row.get('role') == role), None)
        if not reviewer or not isinstance(native, dict) or not isinstance(material, dict):
            continue
        session = review.get('session_id')
        trace_path = root / 'controls/dispatch' / (reviewer_id + '.trace.json')
        request_path = relative_file(root, f'handoff/{role}/REQUEST.json')
        effects = [row for row in records if row.get('role') in ('researcher', 'resume')]
        effect_ids = {row.get('dispatch_id') for row in effects
                      if isinstance(row.get('dispatch_id'), str)}
        effect_proofs = receipt.get('effect_origin_proof_sha256')
        limits = receipt.get('limits')
        required_limits = {'does not establish full #159 qualification',
                           'does not independently assess strong-lead dismissal',
                           'model lead_dispositions remain untrusted review material'}
        input_id = review.get('input_id')
        effect_id = receipt.get('effect_dispatch_id')
        poststop_valid = (
            receipt.get('status') == 'candidate_for_operator_review'
            and receipt.get('scope') == 't01_original_vulnerable_arm'
            and receipt.get('reviewer_role') == role
            and isinstance(effect_id, str) and re.fullmatch(r'[0-9a-f]{32}', effect_id)
            and effect_id in effect_ids
            and all(re.fullmatch(r'[0-9a-f]{32}', str(receipt.get(name, '')))
                    for name in ('review_dispatch_id', 'effect_dispatch_id',
                                 'effect_request_id', 'review_effect_request_id'))
            and receipt.get('reviewer_material_check') == 't01_effect_and_controls_observed'
            and receipt.get('qualification') == 'partial'
            and receipt.get('clean_replay') == 'not_assessed'
            and receipt.get('fixed_control') == 'not_assessed'
            and receipt.get('lead_dispositions') == 'unfinished_unassessed'
            and isinstance(limits, list) and all(isinstance(item, str) for item in limits)
            and required_limits.issubset(limits)
            and isinstance(session, str) and reviewer.get('session_id') == session
            and session not in researcher_sessions
            and review.get('reviewer_role') == role
            and review.get('status') == 'native_turn_observed_unassessed'
            and review.get('same_original_allowance') is True
            and native.get('dispatch_id') == reviewer_id and native.get('role') == role
            and native.get('session_id') == session
            and isinstance(input_id, str) and SHA.fullmatch(input_id)
            and material.get('input_id') == input_id
            and request_path is not None
            and material.get('packet_request_sha256') == sha(request_path)
            and isinstance(material.get('packet_pin'), dict)
            and isinstance(material['packet_pin'].get('files'), dict)
            and material['packet_pin'].get('files', {}).get('REQUEST.json') == sha(request_path)
            and regular(trace_path)
            and reviewer.get('native_trace_sha256') == sha(trace_path)
            and native.get('native_trace_sha256') == sha(trace_path)
            and material.get('native_trace_sha256') == sha(trace_path)
            and receipt.get('review_receipt_sha256') == sha(review_path)
            and receipt.get('review_packet_request_sha256') == sha(request_path)
            and receipt.get('review_trace_sha256') == sha(trace_path)
            and all(SHA.fullmatch(str(receipt.get(name, ''))) for name in
                    ('semantic_receipt_sha256', 'review_semantic_receipt_sha256',
                     'reviewer_origin_proof_sha256'))
            and isinstance(effect_proofs, dict) and receipt.get('effect_dispatch_id') in effect_proofs
            and all(dispatch in effect_ids and SHA.fullmatch(str(digest))
                    for dispatch, digest in effect_proofs.items()))
        if poststop_valid:
            return {key: receipt[key] for key in
                    ('status', 'reviewer_role', 'review_dispatch_id', 'effect_dispatch_id',
                     'effect_request_id', 'review_effect_request_id', 'qualification',
                     'reviewer_material_check', 'clean_replay', 'fixed_control',
                     'lead_dispositions', 'limits')}
    return None


def artifact_matches(observer, manifest):
    scenario = manifest.get('scenario')
    needed = (ARTIFACTS['T04'] if scenario == 'T04' else
              ARTIFACTS['T06'] if isinstance(scenario, str) and scenario in T06 else None)
    artifacts = manifest.get('artifacts')
    if needed is None or not isinstance(artifacts, dict) or set(artifacts) != needed:
        return False
    names = []
    for row in artifacts.values():
        if not isinstance(row, dict) or set(row) != {'path', 'sha256'}:
            return False
        path = relative_file(observer, row['path'])
        if path is None or not SHA.fullmatch(str(row['sha256'])) or sha(path) != row['sha256']:
            return False
        names.append(row['path'])
    return len(set(names)) == len(names)


def capture_target(role):
    return ('target' if role in ('researcher', 'resume') else
            'review-target-' + role[-1] if role in ('reviewer-1', 'reviewer-2') else None)


def required_run_receipts(root, plan, records, manifest):
    names = set(BASE_RECEIPTS)
    if 'kanboard_capture' in plan and 't01_capture' in plan:
        return None
    if 'kanboard_capture' not in plan and 't01_capture' not in plan:
        return names
    t01 = 't01_capture' in plan
    names.update(('controls/evals/native-qualification/kanboard_native_capture.py',
                  'controls/capture-topology.json'))
    for target in CAPTURE_TARGETS:
        names.update(f'controls/observer/{target}/{name}' for name in
                     (('broker.php', 'receipt.php', 'stage.json', 'setup-readback.json',
                       'frozen.json', 'resources.json', 'receipts/receipts.sqlite') if t01 else
                      ('effect.php', 'receipt.php', 'stage.json', 'frozen.json',
                       'resources.json', 'receipts/receipts.sqlite')))
    for record in records:
        dispatch_id, target = record.get('dispatch_id'), capture_target(record.get('role'))
        if not isinstance(dispatch_id, str) or not re.fullmatch(r'[0-9a-f]{32}', dispatch_id) or not target:
            return None
        names.update((f'controls/dispatch/{dispatch_id}.pre.json',
                      f'controls/dispatch/{dispatch_id}.origin.json',
                      f'controls/observer/{target}/window-{dispatch_id}.json'))
        if t01:
            names.add(f'controls/observer/{target}/closed-{dispatch_id}.json')
    if isinstance(plan.get('native_origin'), dict):
        names.update('controls/' + name for name in ORIGIN_SOURCES)
        names.update(('controls/origin/resources.json', 'controls/origin/stopped.json',
                      'controls/origin/cleanup.json'))
        names.update(f'controls/origin/ledger/{role}/requests.jsonl' for role in ORIGIN_ROLES)
        for record in records:
            dispatch_id, role = record.get('dispatch_id'), record.get('role')
            if not isinstance(dispatch_id, str) or role not in ORIGIN_ROLES:
                return None
            names.update((f'controls/origin/registrations/{dispatch_id}.json',
                          f'controls/origin/window-close/{dispatch_id}.json'))
            proof_digest = record.get('origin_transport_proof_sha256')
            if proof_digest is not None:
                if not isinstance(proof_digest, str) or not SHA.fullmatch(proof_digest):
                    return None
                names.add(f'controls/origin/proofs/{dispatch_id}.json')
        if t01:
            recorded = manifest.get('run_receipts', {}) if isinstance(manifest, dict) else {}
            names.update(f'controls/poststop-review-{role}.json' for role in
                         ('reviewer-1', 'reviewer-2')
                         if any(row.get('role') == role for row in records)
                         and (f'controls/poststop-review-{role}.json' in recorded
                              or relative_file(root, f'controls/poststop-review-{role}.json') is not None))
    return names


def run_receipts_match(root, manifest, needed):
    recorded = manifest.get('run_receipts') if isinstance(manifest, dict) else None
    if needed is None or not isinstance(recorded, dict) or set(recorded) != needed:
        return False
    return all(isinstance(digest, str) and SHA.fullmatch(digest) and
               (path := relative_file(root, name)) is not None and sha(path) == digest
               for name, digest in recorded.items())


def host_snapshot_matches(root, plan_hash, final):
    snapshot_path = root / 'controls/host-snapshot.json'
    snapshot = read_json(snapshot_path)
    revoked_path = root / 'controls/native-state/REVOKED'
    revoked = read_json(revoked_path)
    manifest_path = root / 'controls/producer-manifest.json'
    producer_manifest = read_json(manifest_path)
    if not all(isinstance(value, dict) for value in
               (snapshot, revoked, producer_manifest, final)):
        return False
    stop = snapshot.get('native_stop')
    final_snapshot = final.get('host_snapshot')
    return bool(isinstance(stop, dict) and isinstance(final_snapshot, dict)
                and snapshot.get('kind') == 'native-research-host-byte-receipt-v1'
                and snapshot.get('status') == 'complete'
                and snapshot.get('plan_sha256') == plan_hash
                and revoked.get('producers_verified_stopped') is True
                and stop.get('revoked_sha256') == sha(revoked_path)
                and stop.get('manifest_sha256') == sha(manifest_path)
                and revoked.get('manifest_sha256') == sha(manifest_path)
                and final.get('native_stop', {}).get('status') == 'stopped'
                and final_snapshot.get('status') == 'complete'
                and final_snapshot.get('receipt_path') == str(snapshot_path)
                and final_snapshot.get('receipt_sha256') == sha(snapshot_path))


def origin_receipts_match(root, plan, records, final):
    if not isinstance(final, dict):
        return False
    pin = plan.get('native_origin')
    if not isinstance(pin, dict):
        return True
    source_hashes = pin.get('source_sha256')
    controls = root / 'controls'
    if not isinstance(source_hashes, dict) or set(source_hashes) != set(ORIGIN_SOURCES):
        return False
    if any((path := relative_file(root, 'controls/' + name, private=False)) is None
           or sha(path) != source_hashes.get(name) for name in ORIGIN_SOURCES):
        return False
    resource_path = controls / 'origin/resources.json'
    stop_path = controls / 'origin/stopped.json'
    cleanup_path = controls / 'origin/cleanup.json'
    resources, stop, cleanup = map(read_json, (resource_path, stop_path, cleanup_path))
    if not all(isinstance(value, dict) for value in (resources, stop, cleanup)):
        return False
    origin_stop, origin_cleanup = final.get('origin_stop'), final.get('origin_cleanup')
    if (resources.get('kind') != 'native-origin-resources-v1'
            or resources.get('status') != 'removed'
            or stop.get('kind') != 'native-origin-stopped-v1'
            or cleanup.get('kind') != 'native-origin-cleanup-v1'
            or cleanup.get('stopped_sha256') != sha(stop_path)
            or cleanup.get('all_absent') is not True
            or not isinstance(origin_stop, dict) or origin_stop.get('status') != 'complete'
            or origin_stop.get('receipt_sha256') != sha(stop_path)
            or not isinstance(origin_cleanup, dict) or origin_cleanup.get('status') != 'complete'
            or origin_cleanup.get('receipt_sha256') != sha(cleanup_path)):
        return False
    ledger_hashes = stop.get('ledger_sha256')
    if not isinstance(ledger_hashes, dict) or set(ledger_hashes) != set(ORIGIN_ROLES):
        return False
    revoked_path = controls / 'native-state/REVOKED'
    manifest_path = controls / 'producer-manifest.json'
    rows = resources.get('resources')
    if (resources.get('nonce') != stop.get('nonce')
            or cleanup.get('nonce') != resources.get('nonce')
            or stop.get('native_stop_kind') != 'REVOKED'
            or stop.get('native_stop_sha256') != sha(revoked_path)
            or stop.get('producer_manifest_sha256') != sha(manifest_path)
            or not isinstance(rows, list) or len(rows) != len(ORIGIN_ROLES)
            or [row.get('role') for row in rows if isinstance(row, dict)] != list(ORIGIN_ROLES)
            or [row.get('id') for row in rows if isinstance(row, dict)] != cleanup.get('resource_ids')):
        return False
    for role in ORIGIN_ROLES:
        path = relative_file(root, f'controls/origin/ledger/{role}/requests.jsonl')
        if path is None or ledger_hashes.get(role) != sha(path):
            return False
    for record in records:
        dispatch_id, role = record.get('dispatch_id'), record.get('role')
        if role not in ORIGIN_ROLES or not isinstance(dispatch_id, str):
            return False
        registration_path = controls / 'origin/registrations' / (dispatch_id + '.json')
        close_path = controls / 'origin/window-close' / (dispatch_id + '.json')
        pre_path = controls / 'dispatch' / (dispatch_id + '.pre.json')
        target = ORIGIN_ROLES[role]
        window_path = controls / 'observer' / target / ('window-' + dispatch_id + '.json')
        registration, close = read_json(registration_path), read_json(close_path)
        if (not isinstance(registration, dict) or not isinstance(close, dict)
                or record.get('origin_registration_sha256') != sha(registration_path)
                or registration.get('kind') != 'native-origin-registration-v1'
                or registration.get('dispatch_id') != dispatch_id
                or registration.get('role') != role
                or registration.get('target') != target
                or registration.get('dispatch_pre_sha256') != sha(pre_path)
                or registration.get('source_manifest_sha256') != plan.get('source_manifest_sha256')
                or registration.get('target_image_id') != plan.get('target_image_id')
                or registration.get('binary_sha256') != pin.get('binary_sha256')
                or record.get('origin_window_close_sha256') != sha(close_path)
                or close.get('kind') != 'native-origin-window-close-v1'
                or close.get('dispatch_id') != dispatch_id
                or close.get('target') != target
                or close.get('window_sha256') != sha(window_path)):
            return False
        proof_hash = record.get('origin_transport_proof_sha256')
        if proof_hash is not None:
            proof_path = controls / 'origin/proofs' / (dispatch_id + '.json')
            proof = read_json(proof_path)
            if (not isinstance(proof, dict) or proof_hash != sha(proof_path)
                    or proof.get('kind') != 'native-origin-transport-proof-v1'
                    or proof.get('dispatch_id') != dispatch_id
                    or proof.get('role') != role):
                return False
    return True


def capture_matches(root, plan, plan_hash, activation, final, records):
    if 'kanboard_capture' in plan and 't01_capture' in plan:
        return False
    if 'kanboard_capture' not in plan and 't01_capture' not in plan:
        return bool(final and final.get('capture_stop', {}).get('status') == 'not_configured'
                    and final.get('capture_cleanup', {}).get('status') == 'not_configured'
                    and activation and activation.get('capture_topology_sha256') is None)
    t01 = 't01_capture' in plan
    pins = plan.get('t01_capture' if t01 else 'kanboard_capture')
    if not isinstance(pins, dict) or not isinstance(activation, dict) or not isinstance(final, dict):
        return False
    adapter = root / 'controls/evals/native-qualification/kanboard_native_capture.py'
    topology_path = root / 'controls/capture-topology.json'
    topology = read_json(topology_path)
    revoked = relative_file(root, 'controls/native-state/REVOKED')
    producer_manifest = relative_file(root, 'controls/producer-manifest.json')
    if revoked is None or producer_manifest is None:
        return False
    revoked_sha, producer_sha = sha(revoked), sha(producer_manifest)
    if (not regular(adapter) or not isinstance(topology, dict) or set(topology) != set(CAPTURE_TARGETS)
            or sha(adapter) != pins.get('adapter_sha256')
            or activation.get('capture_topology_sha256') != sha(topology_path)
            or pins.get('source_manifest_sha256') != plan.get('source_manifest_sha256')
            or (pins.get('middleware_sha256') != plan.get('source_sha256', {}).get(
                'app/Api/Middleware/AuthenticationMiddleware.php') if t01 else
                pins.get('controller_sha256') != plan.get('source_sha256', {}).get(
                    'app/Controller/ProjectPermissionController.php'))):
        return False
    stopped = final.get('capture_stop')
    cleaned = final.get('capture_cleanup')
    if (not isinstance(stopped, dict) or stopped.get('status') != 'complete'
            or not isinstance(cleaned, dict) or cleaned.get('status') != 'complete'):
        return False
    stop_rows, cleanup_rows = stopped.get('targets'), cleaned.get('targets')
    if (not isinstance(stop_rows, list) or not isinstance(cleanup_rows, list)
            or len(stop_rows) != len(CAPTURE_TARGETS)
            or len(cleanup_rows) != len(CAPTURE_TARGETS)
            or not all(isinstance(row, dict) for row in stop_rows + cleanup_rows)):
        return False
    stops = {row.get('target'): row for row in stop_rows}
    cleanups = {row.get('target'): row for row in cleanup_rows}
    if set(stops) != set(CAPTURE_TARGETS) or set(cleanups) != set(CAPTURE_TARGETS):
        return False
    frozen_by_target = {}
    for target in CAPTURE_TARGETS:
        slot = root / 'controls/observer' / target
        stage, frozen, ledger = (read_json(slot / name) for name in
                                 ('stage.json', 'frozen.json', 'resources.json'))
        topo = topology[target]
        if not all(isinstance(row, dict) for row in (stage, frozen, ledger, topo)):
            return False
        db_path = relative_file(root, f'controls/observer/{target}/receipts/receipts.sqlite')
        hook = relative_file(root, f'controls/observer/{target}/{"broker" if t01 else "effect"}.php')
        collector = relative_file(root, f'controls/observer/{target}/receipt.php')
        if not all((db_path, hook, collector)):
            return False
        try:
            with sqlite3.connect(db_path.as_uri() + '?mode=ro', uri=True) as db:
                if db.execute('PRAGMA quick_check').fetchone() != ('ok',):
                    return False
                count, last_id = db.execute('SELECT COUNT(*), COALESCE(MAX(id), 0) FROM receipts').fetchone()
                setup_row = db.execute('SELECT peer,payload FROM receipts WHERE id=1').fetchone() if t01 else None
        except sqlite3.DatabaseError:
            return False
        if t01:
            try:
                setup = json.loads(setup_row[1]) if setup_row else None
            except (TypeError, ValueError):
                return False
            readback = read_json(slot / 'setup-readback.json')
            if (not isinstance(setup, dict) or not isinstance(readback, dict)
                    or setup_row[0] != topo.get('app_observer_ip')
                    or setup.get('kind') != 't01-kanboard-setup-v1'
                    or setup.get('source_manifest_sha256') != pins['source_manifest_sha256']
                    or setup.get('admin_default_revoked') is not True
                    or setup.get('project_count') != 0 or setup.get('swimlane_count') != 0
                    or readback.get('kind') != 't01-setup-readback-v1'
                    or readback.get('receipt_sha256') != hashlib.sha256(setup_row[1].encode()).hexdigest()
                    or readback.get('db_sha256') != setup.get('db_sha256')):
                return False
        if (stage.get('kind') != ('kanboard-t01-capture-stage-v1' if t01 else
                                  'kanboard-native-capture-stage-v1')
                or stage.get('target') != target or stage.get('plan_sha256') != plan_hash
                or stage.get('source_manifest_sha256') != pins['source_manifest_sha256']
                or stage.get('image_id') != plan.get('target_image_id')
                or stage.get('collector_sha256') != sha(collector)
                or sha(collector) != pins.get('collector_sha256')
                or (stage.get('broker_sha256') != sha(hook) or
                    sha(hook) != pins.get('broker_sha256') if t01 else
                    stage.get('controller_sha256') != pins.get('controller_sha256') or
                    stage.get('probe_sha256') != sha(hook) or
                    sha(hook) != pins.get('probe_sha256'))
                or topo.get('target') != target
                or topo.get('source_manifest_sha256') != pins['source_manifest_sha256']
                or frozen.get('kind') != 'kanboard-capture-frozen-v1'
                or frozen.get('target') != target or frozen.get('native_stop_kind') != 'REVOKED'
                or frozen.get('native_stop_sha256') != revoked_sha
                or frozen.get('producer_manifest_sha256') != producer_sha
                or frozen.get('sqlite_sha256') != sha(db_path)
                or type(count) is not int or type(last_id) is not int
                or frozen.get('receipt_count') != count or frozen.get('last_receipt_id') != last_id
                or frozen.get('collector_id') != topo.get('collector_id')
                or frozen.get('network_id') != topo.get('observer_network_id')
                or ledger.get('kind') != 'kanboard-capture-resources-v1'
                or ledger.get('target') != target or ledger.get('status') != 'removed'
                or ledger.get('nonce') != activation.get('nonce')
                or ledger.get('collector_id') != frozen.get('collector_id')
                or ledger.get('network_id') != frozen.get('network_id')
                or ledger.get('app_id') != topo.get('target_id')
                or stops[target].get('status') != ('frozen_original_session_origin_held' if t01 else
                                                   'frozen_origin_and_credentials_held')
                or stops[target].get('sqlite_sha256') != frozen['sqlite_sha256']
                or stops[target].get('receipt_count') != count
                or cleanups[target].get('status') != 'removed'
                or cleanups[target].get('collector_absent') is not True
                or cleanups[target].get('network_absent') is not True):
            return False
        frozen_by_target[target] = frozen
    for record in records:
        dispatch_id, role = record.get('dispatch_id'), record.get('role')
        target = capture_target(role)
        if not target or not isinstance(dispatch_id, str) or not re.fullmatch(r'[0-9a-f]{32}', dispatch_id):
            return False
        pre_path = root / 'controls/dispatch' / (dispatch_id + '.pre.json')
        origin = read_json(root / 'controls/dispatch' / (dispatch_id + '.origin.json'))
        window = read_json(root / 'controls/observer' / target / ('window-' + dispatch_id + '.json'))
        pre = read_json(pre_path)
        if not all(isinstance(item, dict) for item in (window, pre, origin)):
            return False
        if (window.get('kind') != ('kanboard-t01-window-v1' if t01 else
                                   'kanboard-native-window-v1')
                or window.get('dispatch_id') != dispatch_id
                or window.get('role') != role or window.get('session_id') != record.get('session_id')
                or window.get('target') != target or window.get('topology') != topology[target]
                or window.get('dispatch_sha256') != sha(pre_path)
                or pre.get('kind') != 'native-dispatch-v1' or pre.get('status') != 'unknown_effect'
                or pre.get('dispatch_id') != dispatch_id or pre.get('role') != role
                or pre.get('session_id') != record.get('session_id')
                or pre.get('pool_before') != record.get('pool_before')
                or pre.get('created_at') != record.get('created_at')
                or pre.get('prompt_sha256') != record.get('prompt_sha256')
                or origin.get('dispatch_id') != dispatch_id
                or origin != record.get('origin_hold')
                or type(window.get('collector_count_before')) is not int
                or not 0 <= window['collector_count_before'] <= frozen_by_target[target]['receipt_count']):
            return False
        if t01:
            closed_path = root / 'controls/observer' / target / ('closed-' + dispatch_id + '.json')
            closed = read_json(closed_path)
            if (not isinstance(closed, dict)
                    or closed.get('kind') != 'kanboard-t01-window-closed-v1'
                    or closed.get('dispatch_id') != dispatch_id
                    or closed.get('window_sha256') != sha(root / 'controls/observer' / target /
                                                          ('window-' + dispatch_id + '.json'))
                    or closed.get('native_origin') != 'unproven'
                    or closed.get('status') != 'held'
                    or origin.get('closed_window_sha256') != sha(closed_path)
                    or origin.get('joined_request_ids') != closed.get('joined_request_ids')
                    or origin.get('native_request_attributable') is not False):
                return False
    return True


def audit(run, observer, manifest_path):
    checks = {}

    def check(name, condition):
        checks[name] = bool(condition)

    check('separate_private_roots', private_dir(run) and private_dir(observer)
          and not run.resolve().is_relative_to(observer.resolve())
          and not observer.resolve().is_relative_to(run.resolve()))
    check('protected_controls', private_dir(run / 'controls'))
    try:
        manifest_file = relative_file(observer, manifest_path.relative_to(observer).as_posix())
    except ValueError:
        manifest_file = None
    manifest = read_json(manifest_file) if manifest_file else None
    check('observer_manifest', manifest is not None and manifest.get('schema_version') == 1
          and isinstance(manifest.get('scenario'), str)
          and manifest.get('scenario') in {'T04', *T06})
    plan = read_json(run / 'plan.json')
    plan_hash = sha(run / 'plan.json') if plan is not None else None
    check('native_plan', plan is not None and plan.get('kind') == 'native-research-plan-v1'
          and manifest is not None and SHA.fullmatch(str(manifest.get('plan_sha256', '')))
          and plan_hash == manifest.get('plan_sha256'))
    if plan is None:
        plan = {}
    activation = read_json(run / 'controls/activation.json')
    surface_path = run / 'controls/loaded-surface.json'
    surface = read_json(surface_path)
    check('loaded_surface_pinned', activation is not None and surface is not None
          and activation.get('kind') == 'native-research-activation-v1'
          and activation.get('plan_sha256') == plan_hash
          and SHA.fullmatch(str(activation.get('loaded_surface_sha256', '')))
          and sha(surface_path) == activation.get('loaded_surface_sha256'))
    source = plan.get('source_sha256')
    source_sha = (hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()
                  if isinstance(source, dict) and all(isinstance(k, str) and isinstance(v, str)
                                                      for k, v in source.items()) else None)
    check('original_source_pinned', bool(source_sha and source_sha == plan.get('source_manifest_sha256')
          and manifest and manifest.get('source_manifest_sha256') == source_sha
          and source_matches(run, plan)))
    brief = run / 'controls/BRIEF.md'
    visible_brief = run / 'researcher/brief/BRIEF.md'
    check('visible_brief_pinned', regular(brief) and regular(visible_brief)
          and sha(brief) == plan.get('brief_sha256')
          and sha(visible_brief) == plan.get('brief_sha256'))
    records, traces_ok, allowance_ok = dispatches(run, plan)
    check('native_dispatch_traces', traces_ok)
    check('single_monotonic_allowance', allowance_ok)
    research = [row for row in records if row.get('role') == 'researcher']
    resumed = [row for row in records if row.get('role') == 'resume']
    sessions = {row.get('session_id') for row in research + resumed}
    check('research_resume_same_session', manifest is not None and (
          bool(research and resumed and len(sessions) == 1 and
               research[0].get('created_at', '') < resumed[0].get('created_at', ''))
          if manifest.get('scenario') == 'T04' else True))
    review_candidate = poststop_review_candidate(run, records, sessions, plan)
    check('fresh_review_candidate', review_candidate is not None)
    final = read_json(run / 'controls/final.json')
    check('verified_stop_and_cleanup', final is not None and final.get('status') == 'stopped_complete'
          and isinstance(final.get('cleanup'), dict) and final['cleanup'].get('status') == 'complete')
    check('run_receipts_bound', run_receipts_match(run, manifest,
          required_run_receipts(run, plan, records, manifest)))
    check('host_snapshot_bound', host_snapshot_matches(run, plan_hash, final))
    check('origin_receipts_bound', origin_receipts_match(run, plan, records, final))
    check('capture_receipts_bound' if 'kanboard_capture' in plan or 't01_capture' in plan
          else 'capture_not_configured',
          capture_matches(run, plan, plan_hash, activation, final, records))
    check('observer_artifacts_pinned', manifest is not None and artifact_matches(observer, manifest))
    failed = [name for name, passed in checks.items() if not passed]
    return {'status': 'inventory_complete_for_operator_review' if not failed else 'incomplete',
            'scenario': manifest.get('scenario') if manifest else None,
            'checks': checks, 'failed_checks': failed,
            'review_candidate': review_candidate,
            'native_qualification': 'not_assessed',
            'limits': ['file hashes and CLI receipts do not prove original effect, pause state, '
                       'reviewer judgment, provider charges, redaction, or independent cleanup readback',
                       'the T01 poststop reviewer candidate is partial and does not establish native qualification']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root', required=True, type=Path)
    parser.add_argument('--observer-root', required=True, type=Path)
    parser.add_argument('--manifest', required=True, type=Path)
    args = parser.parse_args()
    try:
        report = audit(args.run_root, args.observer_root, args.manifest)
    except (OSError, TypeError, ValueError):
        report = {'status': 'incomplete', 'checks': {},
                  'failed_checks': ['input_changed_or_invalid_during_read'],
                  'native_qualification': 'not_assessed'}
    print(json.dumps(report, sort_keys=True))
    return 0 if report['status'] == 'inventory_complete_for_operator_review' else 2


if __name__ == '__main__':
    raise SystemExit(main())
