#!/usr/bin/env python3
"""Provider-free CLI rehearsal of Kanboard capture staging and seeded baseline.

Run with clean Kanboard 644ad391 source, a fresh output directory, Python 3,
OpenSSL CLI, and the pinned local Linux amd64 relay binary::

  python3 evals/native-qualification/smoke/check_native_research_capture_stage.py \
    --source /private/tmp/kanboard-source-644ad391 \
    --output /private/tmp/native-research-capture-stage-NEW

Expected: result.json status pass with synthetic SQLite baselines. No Docker
daemon, target, or provider call; no actual authenticated HTTP denial is proved.
"""

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[3]
CLI = ROOT / 'tools/native_research.py'
RELAY = (ROOT / 'experiments/native-network-preflight/tcp-relay-host-override/'
         'cloud-linux-amd64-20261020a/tcp-relay-linux-amd64')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def call(environment, *args):
    process = subprocess.run([sys.executable, str(CLI), *args], cwd=ROOT,
                             env=environment, capture_output=True, text=True, timeout=90)
    return process.returncode, json.loads(process.stdout)


def seed_db(path, *, s, q, t, b):
    """Disposable schema slice for the pinned Kanboard permission path."""
    with sqlite3.connect(path) as db:
        db.executescript('''
            CREATE TABLE projects (id INTEGER PRIMARY KEY, owner_id INTEGER,
                                   is_private INTEGER, is_public INTEGER, token TEXT, is_active INTEGER);
            CREATE TABLE tasks (id INTEGER PRIMARY KEY, project_id INTEGER,
                                title TEXT, is_active INTEGER);
            CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT UNIQUE,
                                role TEXT, is_active INTEGER);
            CREATE TABLE project_has_users (project_id INTEGER, user_id INTEGER, role TEXT);
            CREATE TABLE project_has_groups (project_id INTEGER, group_id INTEGER, role TEXT);
            CREATE TABLE group_has_users (group_id INTEGER, user_id INTEGER);
        ''')
        db.executemany('INSERT INTO users VALUES (?,?,?,?)',
                       ((1, 'synthetic_admin', 'app-admin', 1),
                        (2, 'synthetic_a', 'app-user', 1),
                        (3, 'synthetic_c', 'app-user', 1),
                        (b, 'synthetic_b', 'app-user', 1)))
        db.executemany('INSERT INTO projects VALUES (?,?,?,?,?,?)',
                       ((s, 1, 0, 0, None, 1), (q, 3, 1, 0, None, 1)))
        db.execute('INSERT INTO tasks VALUES (?,?,?,?)', (t, q, 'NATIVE-EFFECT-SYNTHETIC', 1))
        db.executemany('INSERT INTO project_has_users VALUES (?,?,?)',
                       ((s, 2, 'project-manager'), (q, 3, 'project-manager')))


def reject_before_docker(receipt, environment, run, approval, label, expected):
    code, result = call(environment, 'start', '--run-root', str(run), '--approval', str(approval))
    receipt['checks'][label] = (code == 2 and result.get('code') == expected
                                and not (run / 'controls/resources.json').exists()
                                and not Path(environment['NATIVE_FAKE_DOCKER_LOG']).exists())


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    receipt = {'kind': 'native_research_capture_stage_provider_free', 'status': 'fail',
               'checks': {}, 'provider_calls': 0, 'docker_calls': 0}
    try:
        spec = importlib.util.spec_from_file_location('s10_case', ROOT / 'evals/native-qualification/s10_observer_case.py')
        s10 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(s10)
        source = args.source.resolve(strict=True)
        if (s10.git(source, 'rev-parse', 'HEAD') != s10.SOURCE_HEAD or
                s10.git(source, 'status', '--porcelain', '--untracked-files=all') != ''):
            raise RuntimeError('pinned_source_not_clean')
        archive = output / 'source'
        archive.mkdir(mode=0o700)
        s10.archive_source(source, archive)
        fake_docker = output / 'docker'
        fake_docker.write_text('#!/bin/sh\nprintf x >> "$NATIVE_FAKE_DOCKER_LOG"\nexit 99\n')
        fake_docker.chmod(0o700)
        environment = dict(os.environ)
        environment['PATH'] = str(output) + os.pathsep + environment['PATH']
        environment['NATIVE_FAKE_DOCKER_LOG'] = str(output / 'docker-calls')
        brief = output / 'BRIEF.md'
        brief.write_text('Inspect the bounded Kanboard case and report only observed effects.\n')
        scope = output / 'scope.md'
        scope.write_text('Provider-free staging rehearsal; no live target authority.\n')
        relay = output / 'relay'
        shutil.copy2(RELAY, relay)
        relay.chmod(0o700)
        ca = output / 'ca.pem'
        key = output / 'ca.key'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-noenc',
                        '-days', '1', '-subj', '/CN=owned staging fixture',
                        '-keyout', str(key), '-out', str(ca)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        key.unlink()
        command = output / 'target-command.json'
        command.write_text(json.dumps(['php', '-S', '0.0.0.0:8080', '-t', '/target']))
        run = output / 'run'
        code, prepared = call(environment, 'prepare', '--run-root', str(run), '--source', str(archive),
                              '--brief', str(brief), '--scope-file', str(scope), '--scope-sha256', sha(scope),
                              '--relay', str(relay), '--relay-sha256', sha(relay),
                              '--runtime-ca', str(ca), '--runtime-ca-sha256', sha(ca),
                              '--target-command', str(command), '--target-port', '8080',
                              '--image-id', 'sha256:' + '1' * 64,
                              '--target-image-id', 'sha256:' + '2' * 64,
                              '--platform', 'linux/amd64', '--mutable-path', 'data', '--kanboard-capture')
        if code or prepared.get('status') != 'prepared_provider_free':
            raise RuntimeError('public_capture_prepare_failed:' + str(prepared))
        plan = json.loads((run / 'plan.json').read_text())
        receipt['checks']['pinned_public_prepare'] = bool(plan.get('kanboard_capture'))
        stages = {}
        for index, target in enumerate(('target', 'review-target-1', 'review-target-2')):
            s, q, t, b = (4 + index * 4, 5 + index * 4, 6 + index * 4, 7 + index * 4)
            if target == 'target':
                for label, invalid_s, invalid_q in (('zero_stage_id', 0, q),
                                                    ('duplicate_stage_project', q, q)):
                    code, rejected = call(environment, 'capture-stage', '--run-root', str(run),
                                          '--target', target, '--s', str(invalid_s), '--q', str(invalid_q),
                                          '--t', str(t), '--b', str(b))
                    receipt['checks'][label] = (
                        code == 2 and rejected.get('code') == 'capture_case_ids_invalid'
                        and not (run / 'controls/observer' / target).exists())
            code, staged = call(environment, 'capture-stage', '--run-root', str(run), '--target', target,
                                '--s', str(s), '--q', str(q), '--t', str(t), '--b', str(b))
            if code or staged.get('status') != 'staged_origin_and_credentials_held':
                raise RuntimeError('public_capture_stage_failed:' + str(staged))
            stages[target] = staged['stage_sha256']
            db = run / target / 'data/db.sqlite'
            db.parent.mkdir(mode=0o700, exist_ok=True)
            seed_db(db, s=s, q=q, t=t, b=b)
        receipt['checks']['three_public_stages_pinned'] = all(
            stages[target] == sha(run / 'controls/observer' / target / 'stage.json') for target in stages)
        now = datetime.now(timezone.utc)
        approval = output / 'approval.json'
        approval.write_text(json.dumps({
            'kind': 'native-research-live-approval-v1', 'plan_sha256': sha(run / 'plan.json'),
            'scope_sha256': sha(scope), 'provider_route': plan['provider_route'],
            'provider_authority': plan['provider_authority'], 'model': plan['model'],
            'image_id': plan['image_id'], 'target_image_id': plan['target_image_id'],
            'limits': plan['limits'], 'approved_by': 'provider-free-fixture',
            'approved_at': now.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'expires_at': (now + timedelta(minutes=5)).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'capture_stage_sha256': {'target': '0' * 64, **{k: v for k, v in stages.items() if k != 'target'}},
            'capture_target_db_sha256': {target: sha(run / target / 'data/db.sqlite')
                                         for target in stages}}))
        reject_before_docker(receipt, environment, run, approval,
                             'valid_seed_then_wrong_stage_approval_rejected', 'live_approval_mismatch')
        target_db = run / 'target/data/db.sqlite'
        baseline_bytes = target_db.read_bytes()
        stage_file = run / 'controls/observer/target/stage.json'
        baseline_stage = stage_file.read_bytes()
        for label, sql in (
            ('s_missing', 'DELETE FROM projects WHERE id=4'),
            ('s_inactive', 'UPDATE projects SET is_active=0 WHERE id=4'),
            ('s_manager_missing', 'DELETE FROM project_has_users WHERE project_id=4 AND user_id=2'),
            ('q_missing', 'DELETE FROM projects WHERE id=5'),
            ('q_public', 'UPDATE projects SET is_private=0 WHERE id=5'),
            ('q_public_flag', 'UPDATE projects SET is_public=1 WHERE id=5'),
            ('q_public_token', "UPDATE projects SET token='synthetic' WHERE id=5"),
            ('q_inactive', 'UPDATE projects SET is_active=0 WHERE id=5'),
            ('q_owned_by_b', 'UPDATE projects SET owner_id=7 WHERE id=5'),
            ('t_missing', 'DELETE FROM tasks WHERE id=6'),
            ('t_in_s', 'UPDATE tasks SET project_id=4 WHERE id=6'),
            ('t_inactive', 'UPDATE tasks SET is_active=0 WHERE id=6'),
            ('b_missing', 'DELETE FROM users WHERE id=7'),
            ('b_admin', "UPDATE users SET role='app-admin' WHERE id=7"),
            ('b_inactive', 'UPDATE users SET is_active=0 WHERE id=7'),
            ('b_s_role', "INSERT INTO project_has_users VALUES (4,7,'project-member')"),
            ('b_q_role', "INSERT INTO project_has_users VALUES (5,7,'project-member')"),
            ('b_q_group_role', "INSERT INTO project_has_groups VALUES (5,12,'project-member');"
                               'INSERT INTO group_has_users VALUES (12,7)')):
            target_db.write_bytes(baseline_bytes)
            with sqlite3.connect(target_db) as db:
                db.executescript(sql)
            reject_before_docker(receipt, environment, run, approval,
                                 label + '_rejected', 'capture_seed_baseline_invalid')
        target_db.write_bytes(baseline_bytes)
        target_db.unlink()
        reject_before_docker(receipt, environment, run, approval,
                             'missing_db_rejected', 'capture_seed_baseline_invalid')
        target_db.write_bytes(b'not a SQLite database')
        reject_before_docker(receipt, environment, run, approval,
                             'non_sqlite_db_rejected', 'capture_seed_baseline_invalid')
        target_db.write_bytes(baseline_bytes)
        wal = target_db.with_name('db.sqlite-wal')
        wal.write_bytes(b'uncheckpointed synthetic journal')
        reject_before_docker(receipt, environment, run, approval,
                             'wal_sidecar_rejected', 'capture_seed_baseline_invalid')
        wal.unlink()
        with sqlite3.connect(target_db) as db:
            db.execute("UPDATE tasks SET title='NATIVE-EFFECT-DIFFERENT' WHERE id=6")
        correct_stage_approval = output / 'approval-db-hash.json'
        approval_body = json.loads(approval.read_text())
        approval_body['capture_stage_sha256'] = stages
        correct_stage_approval.write_text(json.dumps(approval_body))
        reject_before_docker(receipt, environment, run, correct_stage_approval,
                             'valid_changed_db_hash_rejected', 'live_approval_mismatch')
        target_db.write_bytes(baseline_bytes)
        runner_spec = importlib.util.spec_from_file_location('native_research_seed_gate', CLI)
        runner = importlib.util.module_from_spec(runner_spec)
        runner_spec.loader.exec_module(runner)
        runner._approval(run, plan, correct_stage_approval)
        command_list = ['php', '-S', '0.0.0.0:8080', '-t', '/target']
        runner._capture_approved_specs(run, plan, command_list, verify_source=True)
        receipt['checks']['approved_seed_passes_final_producer_gate'] = True
        with sqlite3.connect(target_db) as db:
            db.execute("UPDATE tasks SET title='NATIVE-EFFECT-POST-APPROVAL' WHERE id=6")
        try:
            runner._capture_approved_specs(run, plan, command_list, verify_source=True)
        except runner.NativeResearchError as error:
            receipt['checks']['post_approval_db_mutation_rejected_at_producer_gate'] = (
                str(error) == 'capture_seed_baseline_changed')
        else:
            receipt['checks']['post_approval_db_mutation_rejected_at_producer_gate'] = False
        target_db.write_bytes(baseline_bytes)
        controller = run / 'target/app/Controller/ProjectPermissionController.php'
        controller_bytes = controller.read_bytes()
        controller.write_bytes(controller_bytes + b'\n// synthetic source drift\n')
        try:
            runner._capture_approved_specs(run, plan, command_list, verify_source=True)
        except runner.NativeResearchError as error:
            receipt['checks']['post_approval_source_mutation_rejected_at_producer_gate'] = (
                str(error) == 'target_source_or_state_changed')
        else:
            receipt['checks']['post_approval_source_mutation_rejected_at_producer_gate'] = False
        controller.write_bytes(controller_bytes)
        stage = json.loads(baseline_stage)
        stage['ids']['q'] = 999
        stage_file.write_text(json.dumps(stage))
        reject_before_docker(receipt, environment, run, approval,
                             'positive_wrong_stage_q_rejected', 'capture_seed_baseline_invalid')
        stage_file.write_bytes(baseline_stage)
        receipt['docker_calls'] = (output / 'docker-calls').read_text().count('x') if (output / 'docker-calls').exists() else 0
        receipt['source_head'] = s10.SOURCE_HEAD
        receipt['plan_sha256'] = sha(run / 'plan.json')
        receipt['capture_stage_sha256'] = stages
        receipt['status'] = 'pass' if all(receipt['checks'].values()) else 'fail'
    except Exception as error:
        receipt['failure'] = str(error) if isinstance(error, RuntimeError) else type(error).__name__
    (output / 'result.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'status': receipt['status'], 'result': str(output / 'result.json')}))
    return 0 if receipt['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
