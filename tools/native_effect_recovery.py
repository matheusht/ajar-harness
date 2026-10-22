#!/usr/bin/env python3
"""Host-only, fail-closed recovery of one Kanboard B-Q role grant.

This observes one declared target operation, not an arbitrary OpenCode turn.
The caller must arm it before dispatch and separately prove the producer has
stopped before using an observed result to continue the run.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import uuid


class RecoveryError(RuntimeError):
    """A fixed-code arming or observation failure; no raw target data escapes."""


KIND = 'kanboard_b_q_role_grant_v1'
CONTROLLER = Path('app/Controller/ProjectPermissionController.php')
HEX64 = re.compile(r'[0-9a-f]{64}\Z')
HEX24 = re.compile(r'[0-9a-f]{24}\Z')
HEX32 = re.compile(r'[0-9a-f]{32}\Z')
MAX_RECEIPTS = 5000


def _fail(code: str):
    raise RecoveryError(code)


def _dispatch_id(value: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except (TypeError, ValueError, AttributeError):
        _fail('dispatch_id_invalid')
    if parsed.version != 4 or value not in (parsed.hex, str(parsed)):
        _fail('dispatch_id_invalid')
    return value


def _root(path: Path) -> Path:
    path = Path(path)
    if not path.is_absolute() or path.is_symlink():
        _fail('run_root_invalid')
    try:
        entry = path.stat(follow_symlinks=False)
        if path.resolve(strict=True) != path:
            _fail('run_root_invalid')
    except OSError:
        _fail('run_root_invalid')
    if not stat.S_ISDIR(entry.st_mode) or entry.st_uid != os.getuid() or entry.st_mode & 0o077:
        _fail('run_root_invalid')
    return path


def _regular(path: Path, root: Path) -> Path:
    if not path.is_relative_to(root):
        _fail('host_file_outside_run')
    try:
        if path.resolve(strict=True) != path:
            _fail('host_file_linked')
        entry = path.stat(follow_symlinks=False)
    except OSError:
        _fail('host_file_unavailable')
    if (not stat.S_ISREG(entry.st_mode) or entry.st_uid != os.getuid()
            or entry.st_mode & 0o022):
        _fail('host_file_invalid')
    return path


def _json_file(path: Path, root: Path) -> dict:
    path = _regular(path, root)
    if path.stat().st_size > 32768:
        _fail('control_oversize')
    try:
        value = json.loads(path.read_bytes(), parse_constant=lambda _: _fail('control_invalid'))
    except (UnicodeError, ValueError):
        _fail('control_invalid')
    if not isinstance(value, dict):
        _fail('control_invalid')
    return value


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _identity(path: Path) -> list[int]:
    info = path.stat(follow_symlinks=False)
    return [info.st_dev, info.st_ino]


def _dispatch(root: Path, dispatch_id: str, *, require_fresh: bool = False) -> Path:
    path = root / 'controls/dispatch' / (dispatch_id + '.json')
    value = _json_file(path, root)
    if (value.get('kind') != 'native-dispatch-v1' or value.get('dispatch_id') != dispatch_id
            or value.get('status') != 'unknown_effect' or value.get('role') not in ('researcher', 'resume')
            or not isinstance(value.get('session_id'), str) or not value['session_id'].startswith('ses_')
            or not isinstance(value.get('prompt_sha256'), str)
            or not HEX64.fullmatch(value['prompt_sha256'])
            or not isinstance(value.get('created_at'), str)):
        _fail('dispatch_not_recoverable')
    try:
        created = datetime.fromisoformat(value['created_at'].replace('Z', '+00:00'))
        age = (datetime.now(timezone.utc) - created).total_seconds()
    except ValueError:
        _fail('dispatch_time_invalid')
    if created.tzinfo is None or age < -5 or (require_fresh and age > 300):
        _fail('dispatch_time_stale')
    return path


def _open_db(path: Path):
    db = None
    try:
        db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=2)
        db.execute('PRAGMA query_only=ON')
        healthy = db.execute('PRAGMA quick_check').fetchone() == ('ok',)
        if not healthy:
            db.close()
            _fail('sqlite_integrity_invalid')
        return db
    except sqlite3.DatabaseError:
        if db is not None:
            db.close()
        _fail('sqlite_unavailable')


def _single(db: sqlite3.Connection, query: str, values: tuple) -> tuple:
    rows = db.execute(query, values).fetchmany(2)
    if len(rows) != 1:
        _fail('target_identity_ambiguous')
    return rows[0]


def _role(db: sqlite3.Connection, project: int, user: int) -> tuple[int | None, str | None]:
    rows = db.execute('SELECT rowid,role FROM project_has_users WHERE project_id=? AND user_id=?',
                      (project, user)).fetchmany(2)
    if len(rows) > 1:
        _fail('target_role_ambiguous')
    return rows[0] if rows else (None, None)


def _target(root: Path, ids: dict) -> tuple[dict, int | None]:
    path = _regular(root / 'target/data/db.sqlite', root)
    db = _open_db(path)
    try:
        db.execute('BEGIN')
        s = _single(db, 'SELECT owner_id,is_private FROM projects WHERE id=?', (ids['s'],))
        q = _single(db, 'SELECT owner_id,is_private,is_public,token FROM projects WHERE id=?', (ids['q'],))
        t = _single(db, 'SELECT project_id,title,is_active FROM tasks WHERE id=?', (ids['t'],))
        a = _single(db, 'SELECT role FROM users WHERE id=?', (ids['actor_a'],))
        b = _single(db, 'SELECT role FROM users WHERE id=?', (ids['subject_b'],))
        _, a_s_role = _role(db, ids['s'], ids['actor_a'])
        _, b_s_role = _role(db, ids['s'], ids['subject_b'])
        rowid, b_q_role = _role(db, ids['q'], ids['subject_b'])
        groups = db.execute('SELECT COUNT(*) FROM project_has_groups pg '
                            'JOIN group_has_users gu ON pg.group_id=gu.group_id '
                            'WHERE pg.project_id=? AND gu.user_id=?',
                            (ids['q'], ids['subject_b'])).fetchone()[0]
        if (not isinstance(t[1], str) or not t[1] or a[0] != 'app-user' or b[0] != 'app-user'
                or a_s_role != 'project-manager' or b_s_role is not None
                or s[1] not in (0, 1) or q[1] != 1 or q[2] != 0 or bool(q[3])
                or t[0] != ids['q'] or t[2] != 1 or groups != 0):
            _fail('target_preconditions_changed')
        state = {
            's_owner_id': s[0], 's_is_private': s[1],
            'q_owner_id': q[0], 'q_is_private': q[1], 'q_is_public': q[2],
            'q_has_public_token': bool(q[3]), 't_project_id': t[0],
            't_title_sha256': hashlib.sha256(t[1].encode()).hexdigest(),
            't_is_active': t[2], 'b_s_role': b_s_role, 'b_q_role': b_q_role,
            'b_q_group_role_count': groups,
        }
        return state, rowid
    except sqlite3.DatabaseError:
        _fail('target_sqlite_invalid')
    finally:
        db.close()


def _receipts(path: Path, root: Path) -> list[tuple]:
    _regular(path, root)
    db = _open_db(path)
    try:
        count = db.execute('SELECT COUNT(*) FROM receipts').fetchone()[0]
        if type(count) is not int or count > MAX_RECEIPTS:
            _fail('collector_size_invalid')
        rows = db.execute('SELECT id,peer,payload FROM receipts ORDER BY id').fetchall()
        if (len(rows) != count or any(type(row[0]) is not int or row[0] < 1
                                      or not isinstance(row[1], str) or not isinstance(row[2], str)
                                      for row in rows)):
            _fail('collector_rows_invalid')
        return rows
    except sqlite3.DatabaseError:
        _fail('collector_sqlite_invalid')
    finally:
        db.close()


def _prefix_digest(rows: list[tuple]) -> str:
    return hashlib.sha256(json.dumps(rows, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


def _write_once(path: Path, value: dict):
    data = (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


def arm_kanboard_role_grant(run_root: Path, dispatch_id: str, *, s: int, q: int, t: int,
                             actor_a: int, subject_b: int, researcher_ip: str,
                             app_ip: str, collector_db: Path) -> dict:
    """Durably bind one S10 B-Q role-grant observation before native dispatch."""
    root = _root(run_root)
    dispatch_id = _dispatch_id(dispatch_id)
    dispatch = _dispatch(root, dispatch_id, require_fresh=True)
    ids = {'s': s, 'q': q, 't': t, 'actor_a': actor_a, 'subject_b': subject_b}
    if (any(type(value) is not int or value < 1 for value in ids.values())
            or s == q or actor_a == subject_b):
        _fail('target_ids_invalid')
    try:
        research_ip = str(ipaddress.ip_address(researcher_ip))
        application_ip = str(ipaddress.ip_address(app_ip))
    except ValueError:
        _fail('target_ip_invalid')
    if research_ip == application_ip or research_ip != researcher_ip or application_ip != app_ip:
        _fail('target_ip_invalid')
    controls = root / 'controls'
    collector = Path(collector_db)
    if not collector.is_relative_to(controls / 'observer'):
        _fail('collector_outside_host_controls')
    _regular(collector, root)
    target_db = _regular(root / 'target/data/db.sqlite', root)
    controller = _regular(root / 'target' / CONTROLLER, root)
    baseline, rowid = _target(root, ids)
    if rowid is not None or baseline['b_q_role'] is not None:
        _fail('effect_present_before_dispatch')
    rows = _receipts(collector, root)
    recovery = controls / 'recovery'
    if recovery.exists():
        if recovery.is_symlink() or recovery.resolve() != recovery:
            _fail('recovery_directory_invalid')
        entry = recovery.stat(follow_symlinks=False)
        if not stat.S_ISDIR(entry.st_mode) or entry.st_uid != os.getuid() or entry.st_mode & 0o077:
            _fail('recovery_directory_invalid')
    else:
        recovery.mkdir(mode=0o700)
        directory = os.open(controls, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    record = {
        'kind': KIND, 'dispatch_id': dispatch_id, 'dispatch_sha256': _sha(dispatch),
        'ids': ids, 'researcher_ip': research_ip, 'app_ip': application_ip,
        'target_db_identity': _identity(target_db), 'collector_identity': _identity(collector),
        'collector_relative': str(collector.relative_to(controls)),
        'controller_sha256': _sha(controller), 'baseline': baseline,
        'collector_max_id': rows[-1][0] if rows else 0,
        'collector_prefix_count': len(rows), 'collector_prefix_sha256': _prefix_digest(rows),
    }
    _write_once(recovery / (dispatch_id + '.json'), record)
    return {'status': 'armed', 'dispatch_id': dispatch_id, 'scope': KIND}


def _valid_state(value: object) -> bool:
    numeric = ('s_owner_id', 's_is_private', 'q_owner_id', 'q_is_private', 'q_is_public',
               't_project_id', 't_is_active', 'b_q_group_role_count')
    return (isinstance(value, dict) and set(value) == set(numeric) | {
        'q_has_public_token', 't_title_sha256', 'b_s_role', 'b_q_role'}
        and all(type(value[key]) is int for key in numeric)
        and type(value['q_has_public_token']) is bool
        and isinstance(value['t_title_sha256'], str) and bool(HEX64.fullmatch(value['t_title_sha256']))
        and value['b_s_role'] is None
        and value['b_q_role'] in (None, 'project-manager', 'project-member', 'project-viewer'))


def _reconcile(root: Path, dispatch_id: str) -> dict:
    sidecar = _json_file(root / 'controls/recovery' / (dispatch_id + '.json'), root)
    if (sidecar.get('kind') != KIND or sidecar.get('dispatch_id') != dispatch_id
            or not isinstance(sidecar.get('ids'), dict)
            or set(sidecar['ids']) != {'s', 'q', 't', 'actor_a', 'subject_b'}
            or any(type(value) is not int or value < 1 for value in sidecar['ids'].values())
            or not _valid_state(sidecar.get('baseline'))
            or sidecar['baseline']['b_q_role'] is not None
            or not isinstance(sidecar.get('dispatch_sha256'), str)
            or not HEX64.fullmatch(sidecar['dispatch_sha256'])):
        _fail('recovery_record_invalid')
    dispatch = _dispatch(root, dispatch_id)
    if _sha(dispatch) != sidecar['dispatch_sha256']:
        _fail('dispatch_changed')
    target_db = _regular(root / 'target/data/db.sqlite', root)
    relative = sidecar.get('collector_relative')
    if not isinstance(relative, str) or not relative.startswith('observer/'):
        _fail('collector_path_invalid')
    collector = root / 'controls' / relative
    if not collector.is_relative_to(root / 'controls/observer'):
        _fail('collector_path_invalid')
    collector = _regular(collector, root)
    controller = _regular(root / 'target' / CONTROLLER, root)
    if (_identity(target_db) != sidecar.get('target_db_identity')
            or _sha(controller) != sidecar.get('controller_sha256')
            or _identity(collector) != sidecar.get('collector_identity')):
        _fail('target_or_collector_changed')
    baseline = sidecar['baseline']
    state, rowid = _target(root, sidecar['ids'])
    rows = _receipts(collector, root)
    highwater = sidecar.get('collector_max_id')
    prefix = [row for row in rows if row[0] <= highwater] if type(highwater) is int else []
    new = [row for row in rows if row[0] > highwater] if type(highwater) is int else []
    if (type(highwater) is not int or highwater < 0
            or len(prefix) != sidecar.get('collector_prefix_count')
            or _prefix_digest(prefix) != sidecar.get('collector_prefix_sha256')
            or len(new) != 1 or new[0][0] != highwater + 1):
        _fail('collector_window_ambiguous')
    try:
        receipt = json.loads(new[0][2], parse_constant=lambda _: _fail('receipt_invalid'))
    except (UnicodeError, ValueError):
        _fail('receipt_invalid')
    ids = sidecar['ids']
    expected = dict(baseline, b_q_role='project-manager')
    if (not isinstance(receipt, dict) or not _valid_state(receipt.get('before'))
            or not _valid_state(receipt.get('after'))
            or receipt['before'] != baseline or receipt['after'] != expected
            or state != expected or type(rowid) is not int or rowid < 1
            or new[0][1] != sidecar.get('app_ip')
            or receipt.get('kind') != 'web_add' or receipt.get('method') != 'POST'
            or receipt.get('remote_addr') != '127.0.0.1'
            or receipt.get('broker_peer_ip') != sidecar.get('researcher_ip')
            or receipt.get('broker_handle') != 'A'
            or not isinstance(receipt.get('broker_request_id'), str)
            or not HEX32.fullmatch(receipt['broker_request_id'])
            or receipt.get('actor_id') != ids['actor_a'] or type(receipt.get('actor_id')) is not int
            or receipt.get('app_role') != 'app-user'
            or receipt.get('effective_project_role') != 'project-manager'
            or receipt.get('route_project_id') != ids['s'] or type(receipt.get('route_project_id')) is not int
            or receipt.get('body_project_id') != ids['q'] or type(receipt.get('body_project_id')) is not int
            or receipt.get('body_user_id') != ids['subject_b'] or type(receipt.get('body_user_id')) is not int
            or receipt.get('task_id') != 0 or type(receipt.get('task_id')) is not int
            or receipt.get('status') not in (302, 303) or type(receipt.get('status')) is not int
            or receipt.get('marker_present') is not False or receipt.get('probe_error') is not None
            or receipt.get('controller_sha256') != sidecar.get('controller_sha256')
            or not isinstance(receipt.get('request_id'), str)
            or not HEX24.fullmatch(receipt['request_id'])):
        _fail('effect_observation_ambiguous')
    after, same_rowid = _target(root, ids)
    if after != state or same_rowid != rowid or _receipts(collector, root) != rows:
        _fail('observation_changed_during_read')
    return {'status': 'effect_observed', 'dispatch_id': dispatch_id, 'scope': KIND,
            'effect_id': {'project_id': ids['q'], 'user_id': ids['subject_b'], 'rowid': rowid},
            'request_id': receipt['request_id'],
            'broker_request_id': receipt['broker_request_id'], 'retry_original': False,
            'run_resume_allowed': False}


def reconcile_kanboard_role_grant(run_root: Path, dispatch_id: str) -> dict:
    """Read target state; all unavailable or ambiguous evidence stays on hold."""
    dispatch_id = _dispatch_id(dispatch_id)
    try:
        return _reconcile(_root(run_root), dispatch_id)
    except (RecoveryError, OSError, sqlite3.DatabaseError, TypeError, KeyError, ValueError) as error:
        code = str(error) if isinstance(error, RecoveryError) else 'observation_unavailable'
        return {'status': 'hold_unknown', 'dispatch_id': dispatch_id, 'scope': KIND,
                'reason': code, 'retry_original': False, 'run_resume_allowed': False}
