#!/usr/bin/env python3
"""Provider-free Kanboard recovery check against disposable SQLite state."""

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
import uuid

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
from native_effect_recovery import RecoveryError, arm_kanboard_role_grant, reconcile_kanboard_role_grant


def make_case(base: Path):
    root = base / 'run'
    (root / 'controls/dispatch').mkdir(parents=True, mode=0o700)
    (root / 'controls/observer').mkdir(mode=0o700)
    (root / 'target/data').mkdir(parents=True, mode=0o700)
    controller = root / 'target/app/Controller/ProjectPermissionController.php'
    controller.parent.mkdir(parents=True, mode=0o700)
    controller.write_text('<?php // synthetic controller source for offline recovery check\n')
    root.chmod(0o700)
    db_path = root / 'target/data/db.sqlite'
    with closing(sqlite3.connect(db_path)) as db, db:
        db.executescript('''
            CREATE TABLE projects (id INTEGER PRIMARY KEY, owner_id INTEGER, is_private INTEGER, is_public INTEGER, token TEXT);
            CREATE TABLE tasks (id INTEGER PRIMARY KEY, project_id INTEGER, title TEXT, is_active INTEGER);
            CREATE TABLE users (id INTEGER PRIMARY KEY, role TEXT);
            CREATE TABLE project_has_users (project_id INTEGER, user_id INTEGER, role TEXT, UNIQUE(project_id,user_id));
            CREATE TABLE project_has_groups (project_id INTEGER, group_id INTEGER, role TEXT);
            CREATE TABLE group_has_users (group_id INTEGER, user_id INTEGER);
            INSERT INTO projects VALUES (1,1,0,0,NULL),(2,4,1,0,NULL);
            INSERT INTO tasks VALUES (1,2,'synthetic marker',1);
            INSERT INTO users VALUES (2,'app-user'),(3,'app-user');
            INSERT INTO project_has_users VALUES (1,2,'project-manager');
        ''')
    collector = root / 'controls/observer/receipts.sqlite'
    with closing(sqlite3.connect(collector)) as db, db:
        db.execute('CREATE TABLE receipts (id INTEGER PRIMARY KEY AUTOINCREMENT, peer TEXT NOT NULL, payload TEXT NOT NULL)')
    dispatch_id = str(uuid.uuid4())
    dispatch = root / 'controls/dispatch' / (dispatch_id + '.json')
    dispatch.write_text(json.dumps({'kind': 'native-dispatch-v1', 'dispatch_id': dispatch_id,
                                    'status': 'unknown_effect', 'role': 'researcher',
                                    'session_id': 'ses_test', 'prompt_sha256': 'a' * 64,
                                    'created_at': datetime.now(timezone.utc).isoformat()}))
    dispatch.chmod(0o600)
    return root, dispatch_id, db_path, collector, dispatch


def arm(root, dispatch_id, collector):
    return arm_kanboard_role_grant(root, dispatch_id, s=1, q=2, t=1,
                                   actor_a=2, subject_b=3, researcher_ip='172.30.0.8',
                                   app_ip='172.30.0.7', collector_db=collector)


def projection(role=None):
    return {'s_owner_id': 1, 's_is_private': 0, 'q_owner_id': 4, 'q_is_private': 1,
            'q_is_public': 0, 'q_has_public_token': False, 't_project_id': 2,
            't_title_sha256': hashlib.sha256(b'synthetic marker').hexdigest(),
            't_is_active': 1, 'b_s_role': None, 'b_q_role': role,
            'b_q_group_role_count': 0}


def effect(db_path, collector, *, actor=2, source='127.0.0.1', request_id='b' * 24,
           before=None, after=None, duplicate=False, **changes):
    with closing(sqlite3.connect(db_path)) as db, db:
        db.execute("INSERT INTO project_has_users VALUES (2,3,'project-manager')")
    row = {'kind': 'web_add', 'request_id': request_id, 'method': 'POST',
           'remote_addr': source, 'broker_peer_ip': '172.30.0.8',
           'broker_handle': 'A', 'broker_request_id': 'f' * 32,
           'php_pid': 123, 'controller_sha256': 'c' * 64,
           'actor_id': actor, 'app_role': 'app-user', 'effective_project_role': 'project-manager',
           'route_project_id': 1, 'body_project_id': 2, 'body_user_id': 3,
           'task_id': 0, 'status': 302, 'marker_present': False,
           'response_sha256': 'd' * 64, 'before': before or projection(),
           'after': after or projection('project-manager'), 'probe_error': None}
    row.update(changes)
    row['controller_sha256'] = hashlib.sha256((db_path.parents[1] / 'app/Controller/ProjectPermissionController.php').read_bytes()).hexdigest()
    with closing(sqlite3.connect(collector)) as db, db:
        db.execute('INSERT INTO receipts(peer,payload) VALUES (?,?)', ('172.30.0.7', json.dumps(row)))
        if duplicate:
            row['request_id'] = 'e' * 24
            db.execute('INSERT INTO receipts(peer,payload) VALUES (?,?)', ('172.30.0.7', json.dumps(row)))


def one_case(label, mutate=None, expected='hold_unknown'):
    with TemporaryDirectory(prefix='kanboard-recovery-') as temp:
        root, dispatch_id, db_path, collector, dispatch = make_case(Path(temp).resolve())
        before = (db_path.read_bytes(), collector.read_bytes(), dispatch.read_bytes())
        arm(root, dispatch_id, collector)
        assert before == (db_path.read_bytes(), collector.read_bytes(), dispatch.read_bytes()), label + ': arm changed source'
        if mutate:
            mutate(root, dispatch_id, db_path, collector, dispatch)
        result = reconcile_kanboard_role_grant(root, dispatch_id)
        assert result['status'] == expected, (label, result)
        assert result['retry_original'] is False, label
        assert result['dispatch_id'] == dispatch_id, label
        if expected == 'effect_observed':
            assert result['effect_id']['project_id'] == 2 and result['effect_id']['user_id'] == 3
            assert type(result['effect_id']['rowid']) is int and result['effect_id']['rowid'] > 0
            assert result['request_id'] == 'b' * 24
            assert result['scope'] == 'kanboard_b_q_role_grant_v1'
        print('PASS', label)


def main():
    one_case('crash before effect')
    one_case('target state plus exact app request',
             lambda r, d, p, c, x: effect(p, c), 'effect_observed')
    def target_only(r, d, p, c, x):
        with closing(sqlite3.connect(p)) as db, db:
            db.execute("INSERT INTO project_has_users VALUES (2,3,'project-manager')")
    one_case('target state without receipt', target_only)
    one_case('duplicate app write', lambda r, d, p, c, x: effect(p, c, duplicate=True))
    one_case('wrong actor', lambda r, d, p, c, x: effect(p, c, actor=3))
    one_case('wrong backend source IP', lambda r, d, p, c, x: effect(p, c, source='172.30.0.9'))
    one_case('wrong broker peer IP', lambda r, d, p, c, x: effect(p, c, broker_peer_ip='172.30.0.9'))
    one_case('wrong broker handle', lambda r, d, p, c, x: effect(p, c, broker_handle='B'))
    one_case('missing broker request ID', lambda r, d, p, c, x: effect(p, c, broker_request_id=''))
    one_case('stale prestate', lambda r, d, p, c, x: effect(p, c, before=projection('project-viewer')))
    one_case('wrong route', lambda r, d, p, c, x: effect(p, c, route_project_id=2))
    one_case('wrong status', lambda r, d, p, c, x: effect(p, c, status=403))
    one_case('probe error', lambda r, d, p, c, x: effect(p, c, probe_error='prestate_unavailable'))
    def corrupt_prefix(r, d, p, c, x):
        effect(p, c)
        with closing(sqlite3.connect(c)) as db, db:
            db.execute("UPDATE receipts SET payload='{}' WHERE id=1")
    one_case('corrupt collector row', corrupt_prefix)
    def wrong_final_role(r, d, p, c, x):
        effect(p, c)
        with closing(sqlite3.connect(p)) as db, db:
            db.execute("UPDATE project_has_users SET role='project-viewer' WHERE project_id=2 AND user_id=3")
    one_case('changed target role', wrong_final_role)
    one_case('replaced target DB', lambda r, d, p, c, x: p.rename(p.with_suffix('.old')))
    one_case('missing collector', lambda r, d, p, c, x: c.unlink())
    one_case('changed dispatch', lambda r, d, p, c, x: x.write_text('{"status":"acknowledged"}'))
    one_case('corrupt sidecar', lambda r, d, p, c, x: (r / 'controls/recovery' / (d + '.json')).write_text('{'))
    with TemporaryDirectory(prefix='kanboard-recovery-') as temp:
        root, dispatch_id, db_path, collector, dispatch = make_case(Path(temp).resolve())
        with closing(sqlite3.connect(db_path)) as db, db:
            db.execute("INSERT INTO project_has_users VALUES (2,3,'project-member')")
        try:
            arm(root, dispatch_id, collector)
        except RecoveryError:
            pass
        else:
            raise AssertionError('preexisting B-Q role accepted')
        assert not (root / 'controls/recovery' / (dispatch_id + '.json')).exists()
        print('PASS preexisting role rejects before dispatch')
    print('PASS 20 offline checks; zero model, provider, Docker or application calls')


if __name__ == '__main__':
    main()
