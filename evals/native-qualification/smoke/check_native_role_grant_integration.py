#!/usr/bin/env python3
"""Provider-free selected-turn and stopped-run recovery wiring check."""

from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(Path(__file__).parent))
import native_research as runner
from check_kanboard_recovery import effect, make_case


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True))
    path.chmod(0o600)


def fixture(base):
    root, unused_dispatch, db, collector, _ = make_case(base)
    (root / 'controls/dispatch' / (unused_dispatch + '.json')).unlink()
    db.chmod(0o600)
    with closing(sqlite3.connect(db)) as connection, connection:
        connection.execute('ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1')
    slot = root / 'controls/observer/target'
    (slot / 'receipts').mkdir(parents=True, mode=0o700)
    collector.rename(slot / 'receipts/receipts.sqlite')
    collector = slot / 'receipts/receipts.sqlite'
    collector.chmod(0o600)
    archive = root / 'controls/tools/native_effect_recovery.py'
    archive.parent.mkdir(mode=0o700)
    shutil.copy2(ROOT / 'tools/native_effect_recovery.py', archive)
    put(root / 'plan.json', {'kind': 'native-research-plan-v1'})
    plan = {'kanboard_capture': {}, 'limits': {'duration_seconds': 300},
            'source_manifest_sha256': runner.CAPTURE_SOURCE_SHA}
    put(slot / 'stage.json', {'kind': 'kanboard-native-capture-stage-v1', 'target': 'target',
                            'ids': {'s': 1, 'q': 2, 't': 1, 'b': 3},
                            'plan_sha256': sha(root / 'plan.json'),
                            'source_manifest_sha256': runner.CAPTURE_SOURCE_SHA,
                            'controller_sha256': sha(root / 'target/app/Controller/ProjectPermissionController.php')})
    return root, db, collector, plan


def fake_bind(root, target, dispatch_id):
    assert target == 'target'
    slot = root / 'controls/observer/target'
    dispatch = root / 'controls/dispatch' / (dispatch_id + '.json')
    window = {'kind': 'kanboard-native-window-v1', 'dispatch_id': dispatch_id,
              'dispatch_sha256': sha(dispatch), 'target': target, 'role': 'resume',
              'session_id': 'ses_test', 'collector_count_before': 0,
              'collector_max_id_before': 0,
              'collector_prefix_sha256': hashlib.sha256(b'[]').hexdigest(),
              'topology': {'status': 'topology_attested_origin_and_credentials_held',
                           'target': target, 'native_client_ip': '172.30.0.8',
                           'app_observer_ip': '172.30.0.7',
                           'collector_db': str(slot / 'receipts/receipts.sqlite')}}
    put(slot / ('window-' + dispatch_id + '.json'), window)


def invoke(root, plan, selected):
    called = []

    def fake_native(*args):
        called.append(args)
        raise runner.NativeResearchError('synthetic_interruption')

    with patch.object(runner, '_plan', return_value=plan), \
         patch.object(runner, 'run_active', return_value=True), \
         patch.object(runner, 'allowance_snapshot', return_value={'active': True}), \
         patch.object(runner, '_native_exec', side_effect=fake_native), \
         patch.object(runner, '_load_capture_module', return_value=SimpleNamespace(bind_dispatch=fake_bind)):
        result = runner.invoke_native(root, 'resume', 'ses_test', 'synthetic prompt',
                                      kanboard_role_grant=selected)
    assert result['status'] == 'unknown_effect'
    return result['dispatch_id'], len(called)


def stopped(root, collector):
    controls = root / 'controls'
    ids = [format(index, '064x') for index in range(1, 9)]
    put(controls / 'resources.json', {'resources': [{'kind': 'container', 'id': value} for value in ids]})
    manifest = controls / 'producer-manifest.json'
    put(manifest, {'producers': [{'id': value} for value in ids]})
    state = controls / 'native-state'
    put(state / 'RUN.json', {'ids': ids, 'manifest_sha256': sha(manifest)})
    put(state / 'REVOKED', {'ids': ids, 'manifest_sha256': sha(manifest),
                            'producers_verified_stopped': True})
    snapshot = controls / 'host-snapshot.json'
    put(snapshot, {'status': 'complete', 'plan_sha256': sha(root / 'plan.json'),
                   'native_stop': {'manifest_sha256': sha(manifest),
                                   'revoked_sha256': sha(state / 'REVOKED')}})
    with closing(sqlite3.connect(collector)) as db:
        count, maximum = db.execute('SELECT COUNT(*), COALESCE(MAX(id),0) FROM receipts').fetchone()
    put(controls / 'observer/target/frozen.json', {
        'kind': 'kanboard-capture-frozen-v1', 'target': 'target',
        'sqlite_sha256': sha(collector), 'receipt_count': count,
        'last_receipt_id': maximum, 'native_stop_kind': 'REVOKED',
        'native_stop_sha256': sha(state / 'REVOKED'),
        'producer_manifest_sha256': sha(manifest)})
    put(controls / 'final.json', {'status': 'stopped_complete',
                                 'native_stop': {'status': 'stopped'},
                                 'host_snapshot': {'status': 'complete', 'receipt_path': str(snapshot),
                                                   'receipt_sha256': sha(snapshot)},
                                 'capture_stop': {'status': 'complete'},
                                 'cleanup': {'status': 'complete'},
                                 'capture_cleanup': {'status': 'complete'}})


def main():
    selected_args = runner._parser().parse_args(['resume', '--run-root', '/tmp/synthetic',
                                                 '--prompt-file', '/tmp/prompt', '--session', 'ses_test',
                                                 '--observe-kanboard-role-grant'])
    assert selected_args.observe_kanboard_role_grant is True
    with TemporaryDirectory(prefix='native-role-recovery-') as temp:
        root, db, collector, plan = fixture(Path(temp).resolve())
        with patch.object(runner, '_plan', return_value=plan), \
             patch.object(runner, '_verified_plan', return_value=plan):
            unselected, called = invoke(root, plan, False)
            assert called == 1
            assert not (root / 'controls/recovery' / (unselected + '.json')).exists()
        print('PASS unselected turn retains native behavior without recovery sidecar')

    with TemporaryDirectory(prefix='native-role-recovery-') as temp:
        root, db, collector, plan = fixture(Path(temp).resolve())
        with patch.object(runner, '_plan', return_value=plan), \
             patch.object(runner, '_verified_plan', return_value=plan):
            dispatch_id, called = invoke(root, plan, True)
            assert called == 1
            assert (root / 'controls/recovery' / (dispatch_id + '.json')).exists()
            assert runner.reconcile_role_grant(root, dispatch_id)['status'] == 'hold_unknown'
            effect(db, collector)
            stopped(root, collector)
            assert runner.reconcile_role_grant(root, dispatch_id)['status'] == 'effect_observed'
            frozen = root / 'controls/observer/target/frozen.json'
            saved = frozen.read_bytes()
            frozen.write_text('{}')
            assert runner.reconcile_role_grant(root, dispatch_id)['status'] == 'hold_unknown'
            frozen.write_bytes(saved)
            final = root / 'controls/final.json'
            saved_final = final.read_bytes()
            final.write_text('{}')
            assert runner.reconcile_role_grant(root, dispatch_id)['status'] == 'hold_unknown'
            final.write_bytes(saved_final)
            revoked = root / 'controls/native-state/REVOKED'
            saved_revoked = revoked.read_bytes()
            revoked.write_text('{}')
            assert runner.reconcile_role_grant(root, dispatch_id)['status'] == 'hold_unknown'
            revoked.write_bytes(saved_revoked)
            dispatch = root / 'controls/dispatch' / (dispatch_id + '.json')
            saved_dispatch = dispatch.read_bytes()
            put(dispatch, {'dispatch_id': dispatch_id, 'status': 'acknowledged'})
            assert runner.reconcile_role_grant(root, dispatch_id)['status'] == 'hold_unknown'
            dispatch.write_bytes(saved_dispatch)
            print('PASS selected pre-dispatch arming and exact post-stop observation')
    with TemporaryDirectory(prefix='native-role-recovery-') as temp:
        root, db, collector, plan = fixture(Path(temp).resolve())
        (root / 'controls/observer/target/stage.json').write_text('{}')
        with patch.object(runner, '_plan', return_value=plan), \
             patch.object(runner, '_verified_plan', return_value=plan):
            dispatch_id, called = invoke(root, plan, True)
            assert called == 0
            assert not (root / 'controls/recovery' / (dispatch_id + '.json')).exists()
        print('PASS invalid stage holds before native execution')
    print('PASS provider-free runner wiring; no Docker, model, or application calls')


if __name__ == '__main__':
    main()
