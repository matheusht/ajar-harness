#!/usr/bin/env python3
"""Provider-free CLI acceptance smoke; all evidence here is synthetic."""

import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile


CHECKER = Path(__file__).with_name('check_native_acceptance_inventory.py')
REQUIRED = ('case_preflight', 'host_trace', 'pause_resume', 'clean_replay_and_controls',
            'native_review', 'workspace_diff', 'cost_and_help', 'final_output', 'cleanup')
TARGETS = ('target', 'review-target-1', 'review-target-2')
BASE_RECEIPTS = ('controls/final.json', 'controls/host-snapshot.json',
                 'controls/native-state/REVOKED', 'controls/producer-manifest.json')


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + '\n' if isinstance(value, dict) else value)
    path.chmod(0o600)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def invoke(run, observer):
    proc = subprocess.run([sys.executable, str(CHECKER), '--run-root', str(run),
                           '--observer-root', str(observer), '--manifest', str(observer / 'manifest.json')],
                          capture_output=True, text=True, check=False)
    return proc.returncode, json.loads(proc.stdout)


def run_receipts(run, paths):
    return {name: hashlib.sha256((run / name).read_bytes()).hexdigest() for name in paths}


def reject(run, observer, name):
    code, report = invoke(run, observer)
    assert code == 2 and name in report['failed_checks'], report


def repin(run, observer, manifest, name):
    manifest['run_receipts'][name] = hashlib.sha256((run / name).read_bytes()).hexdigest()
    put(observer / 'manifest.json', manifest)


def seed_capture(run, observer, plan, manifest, dispatch_ids, final):
    adapter = 'controls/evals/native-qualification/kanboard_native_capture.py'
    adapter_sha = put(run / adapter, 'synthetic capture adapter\n')
    probe = 'synthetic app probe\n'
    collector = 'synthetic collector\n'
    probe_sha = hashlib.sha256(probe.encode()).hexdigest()
    collector_sha = hashlib.sha256(collector.encode()).hexdigest()
    pins = {'adapter_sha256': adapter_sha, 'probe_sha256': probe_sha,
            'collector_sha256': collector_sha,
            'source_manifest_sha256': plan['source_manifest_sha256'],
            'controller_sha256': plan['source_sha256'][
                'app/Controller/ProjectPermissionController.php']}
    plan['kanboard_capture'] = pins
    plan_sha = put(run / 'plan.json', plan)
    manifest['plan_sha256'] = plan_sha
    revoked_sha = hashlib.sha256((run / 'controls/native-state/REVOKED').read_bytes()).hexdigest()
    producer_sha = hashlib.sha256((run / 'controls/producer-manifest.json').read_bytes()).hexdigest()
    activation_path = run / 'controls/activation.json'
    activation = json.loads(activation_path.read_text())
    activation['plan_sha256'] = plan_sha
    snapshot_path = run / 'controls/host-snapshot.json'
    snapshot = json.loads(snapshot_path.read_text())
    snapshot['plan_sha256'] = plan_sha
    final['host_snapshot']['receipt_sha256'] = put(snapshot_path, snapshot)
    paths = set(BASE_RECEIPTS) | {adapter, 'controls/capture-topology.json'}
    topology = {}
    for index, target in enumerate(TARGETS):
        slot = run / 'controls/observer' / target
        slot.mkdir(mode=0o700, parents=True)
        slot.chmod(0o700)
        (run / 'controls/observer').chmod(0o700)
        (slot / 'receipts').mkdir(mode=0o700)
        put(slot / 'effect.php', probe)
        put(slot / 'receipt.php', collector)
        ids = {'s': 1, 'q': 2, 't': 3, 'b': 4}
        put(slot / 'stage.json', {
            'kind': 'kanboard-native-capture-stage-v1', 'target': target,
            'plan_sha256': plan_sha, 'source_manifest_sha256': pins['source_manifest_sha256'],
            'controller_sha256': pins['controller_sha256'], 'probe_sha256': probe_sha,
            'collector_sha256': collector_sha, 'image_id': plan['target_image_id'], 'ids': ids})
        collector_id = f'{index + 4:064x}'
        network_id = f'{index + 7:064x}'
        app_id = f'{index + 10:064x}'
        topology[target] = {
            'status': 'topology_attested_origin_and_credentials_held', 'target': target,
            'target_id': app_id, 'collector_id': collector_id,
            'observer_network_id': network_id,
            'source_manifest_sha256': pins['source_manifest_sha256']}
        db_path = slot / 'receipts/receipts.sqlite'
        with sqlite3.connect(db_path) as db:
            db.execute('CREATE TABLE receipts (id INTEGER PRIMARY KEY, peer TEXT, payload TEXT)')
            db.execute('INSERT INTO receipts VALUES (1, ?, ?)', ('synthetic', '{}'))
        db_path.chmod(0o600)
        db_sha = hashlib.sha256(db_path.read_bytes()).hexdigest()
        put(slot / 'frozen.json', {
            'kind': 'kanboard-capture-frozen-v1', 'target': target,
            'collector_id': collector_id, 'network_id': network_id,
            'sqlite_sha256': db_sha, 'receipt_count': 1, 'last_receipt_id': 1,
            'native_stop_kind': 'REVOKED', 'native_stop_sha256': revoked_sha,
            'producer_manifest_sha256': producer_sha, 'native_origin': 'unproven',
            'credential_route': 'unavailable'})
        put(slot / 'resources.json', {
            'kind': 'kanboard-capture-resources-v1', 'status': 'removed',
            'target': target, 'nonce': 'a' * 32, 'app_id': app_id,
            'collector_id': collector_id, 'network_id': network_id})
        paths.update(f'controls/observer/{target}/{name}' for name in
                     ('effect.php', 'receipt.php', 'stage.json', 'frozen.json',
                      'resources.json', 'receipts/receipts.sqlite'))
    topology_sha = put(run / 'controls/capture-topology.json', topology)
    activation['capture_topology_sha256'] = topology_sha
    put(activation_path, activation)

    for index, dispatch_id in enumerate(dispatch_ids):
        target = 'target' if index < 2 else 'review-target-1'
        dispatch_path = run / f'controls/dispatch/{dispatch_id}.json'
        record = json.loads(dispatch_path.read_text())
        pre = dict(record)
        pre['status'] = 'unknown_effect'
        pre.pop('native_trace_sha256')
        pre.pop('pool_after')
        pre_name = f'controls/dispatch/{dispatch_id}.pre.json'
        pre_sha = put(run / pre_name, pre)
        window_name = f'controls/observer/{target}/window-{dispatch_id}.json'
        put(run / window_name, {
            'kind': 'kanboard-native-window-v1', 'dispatch_id': dispatch_id,
            'dispatch_sha256': pre_sha, 'role': record['role'],
            'session_id': record['session_id'], 'target': target,
            'topology': topology[target], 'collector_count_before': 0,
            'collector_max_id_before': 0, 'collector_prefix_sha256': '0' * 64,
            'native_origin': 'unproven', 'credential_route': 'unavailable'})
        origin_name = f'controls/dispatch/{dispatch_id}.origin.json'
        origin = {'status': 'held', 'reason': 'native_credential_route_unavailable',
                  'dispatch_id': dispatch_id, 'native_request_attributable': False}
        put(run / origin_name, origin)
        record['origin_hold'] = origin
        put(dispatch_path, record)
        paths.update((pre_name, origin_name, window_name))

    final['capture_stop'] = {'status': 'complete', 'targets': [
        {'status': 'frozen_origin_and_credentials_held', 'target': target,
         'receipt_count': 1,
         'sqlite_sha256': json.loads((run / f'controls/observer/{target}/frozen.json').read_text())[
             'sqlite_sha256']} for target in TARGETS]}
    final['capture_cleanup'] = {'status': 'complete', 'targets': [
        {'status': 'removed', 'target': target, 'collector_absent': True,
         'network_absent': True} for target in TARGETS]}
    put(run / 'controls/final.json', final)
    manifest['run_receipts'] = run_receipts(run, paths)
    put(observer / 'manifest.json', manifest)
    return paths


def seed_t01(run, observer, plan, manifest, dispatch_ids, final, old_paths):
    """Turn the S10 fixture into a T01 fixture."""
    middleware = 'app/Api/Middleware/AuthenticationMiddleware.php'
    plan['source_sha256'][middleware] = put(run / 'original' / middleware, 'synthetic middleware\n')
    source_sha = hashlib.sha256(json.dumps(plan['source_sha256'], sort_keys=True).encode()).hexdigest()
    plan['source_manifest_sha256'] = manifest['source_manifest_sha256'] = source_sha
    adapter = 'controls/evals/native-qualification/kanboard_native_capture.py'
    broker_sha = hashlib.sha256(b'synthetic T01 broker\n').hexdigest()
    pins = {'adapter_sha256': hashlib.sha256((run / adapter).read_bytes()).hexdigest(),
            'broker_sha256': broker_sha, 'collector_sha256': hashlib.sha256(
                b'synthetic collector\n').hexdigest(), 'source_manifest_sha256': source_sha,
            'middleware_sha256': plan['source_sha256'][middleware]}
    plan.pop('kanboard_capture')
    plan['t01_capture'] = pins
    origin_sources = ('tools/native_origin/protocol.go', 'tools/native_origin/main_linux.go')
    plan['native_origin'] = {
        'kind': 'native-origin-build-v1', 'binary_sha256': 'b' * 64,
        'source_sha256': {name: put(run / 'controls' / name, 'synthetic origin source\n')
                          for name in origin_sources}}
    plan_sha = put(run / 'plan.json', plan)
    manifest['plan_sha256'] = plan_sha
    activation_path = run / 'controls/activation.json'
    activation = json.loads(activation_path.read_text())
    activation['plan_sha256'] = plan_sha
    snapshot_path = run / 'controls/host-snapshot.json'
    snapshot = json.loads(snapshot_path.read_text())
    snapshot['plan_sha256'] = plan_sha
    final['host_snapshot']['receipt_sha256'] = put(snapshot_path, snapshot)
    paths = set(old_paths) - {f'controls/observer/{target}/effect.php' for target in TARGETS}
    topology = json.loads((run / 'controls/capture-topology.json').read_text())
    for target in TARGETS:
        slot = run / 'controls/observer' / target
        put(slot / 'broker.php', 'synthetic T01 broker\n')
        paths.add(f'controls/observer/{target}/broker.php')
        stage = json.loads((slot / 'stage.json').read_text())
        for name in ('controller_sha256', 'probe_sha256', 'ids'):
            stage.pop(name)
        stage.update(kind='kanboard-t01-capture-stage-v1', plan_sha256=plan_sha,
                     source_manifest_sha256=source_sha, broker_sha256=broker_sha)
        put(slot / 'stage.json', stage)
        topology[target].update(status='topology_attested_original_session_origin_held',
                                source_manifest_sha256=source_sha,
                                app_observer_ip='172.28.0.10',
                                native_client_ip='172.29.0.10')
        setup = {'kind': 't01-kanboard-setup-v1', 'request_id': 'a' * 32,
                 'source_manifest_sha256': source_sha, 'actor_ids': {'A': 2, 'B': 3},
                 'admin_default_revoked': True, 'project_count': 0,
                 'swimlane_count': 0, 'db_sha256': 'd' * 64}
        payload = json.dumps(setup, separators=(',', ':'))
        db_path = slot / 'receipts/receipts.sqlite'
        with sqlite3.connect(db_path) as db:
            db.execute('UPDATE receipts SET peer=?,payload=? WHERE id=1',
                       ('172.28.0.10', payload))
        db_sha = hashlib.sha256(db_path.read_bytes()).hexdigest()
        put(slot / 'setup-readback.json', {'kind': 't01-setup-readback-v1',
             'receipt_sha256': hashlib.sha256(payload.encode()).hexdigest(),
             'db_sha256': setup['db_sha256']})
        paths.add(f'controls/observer/{target}/setup-readback.json')
        frozen = json.loads((slot / 'frozen.json').read_text())
        frozen.update(sqlite_sha256=db_sha, credential_route='brokered_identity_control')
        put(slot / 'frozen.json', frozen)
    topology_sha = put(run / 'controls/capture-topology.json', topology)
    activation['capture_topology_sha256'] = topology_sha
    put(activation_path, activation)
    for index, dispatch_id in enumerate(dispatch_ids):
        target = 'target' if index < 2 else 'review-target-1'
        slot = run / 'controls/observer' / target
        record_path = run / f'controls/dispatch/{dispatch_id}.json'
        record = json.loads(record_path.read_text())
        window_path = slot / f'window-{dispatch_id}.json'
        window = json.loads(window_path.read_text())
        with sqlite3.connect(slot / 'receipts/receipts.sqlite') as db:
            rows = db.execute('SELECT id,peer,payload FROM receipts ORDER BY id').fetchall()
        window.update(kind='kanboard-t01-window-v1', topology=topology[target],
                      collector_count_before=1, collector_max_id_before=1,
                      collector_prefix_sha256=hashlib.sha256(json.dumps(
                          rows, separators=(',', ':')).encode()).hexdigest(),
                      credential_route='brokered_identity_control')
        put(window_path, window)
        closed = {'kind': 'kanboard-t01-window-closed-v1', 'dispatch_id': dispatch_id,
                  'window_sha256': hashlib.sha256(window_path.read_bytes()).hexdigest(),
                  'collector_count_after': 1, 'receipt_rows': [],
                  'native_response_ids': [], 'joined_request_ids': [],
                  'native_origin': 'unproven', 'status': 'held',
                  'reason': 'native_response_receipt_join_unavailable'}
        closed_path = slot / f'closed-{dispatch_id}.json'
        closed_sha = put(closed_path, closed)
        paths.add(f'controls/observer/{target}/closed-{dispatch_id}.json')
        origin = {'status': 'held', 'reason': closed['reason'],
                  'dispatch_id': dispatch_id, 'native_request_attributable': False,
                  'closed_window_sha256': closed_sha, 'joined_request_ids': []}
        put(run / f'controls/dispatch/{dispatch_id}.origin.json', origin)
        record['origin_hold'] = origin
        put(record_path, record)
    for row in final['capture_stop']['targets']:
        row['status'] = 'frozen_original_session_origin_held'
        row['sqlite_sha256'] = json.loads((run / f'controls/observer/{row["target"]}/frozen.json').read_text())['sqlite_sha256']
    put(run / 'controls/final.json', final)
    manifest['run_receipts'] = run_receipts(run, paths)
    put(observer / 'manifest.json', manifest)
    return paths


def seed_poststop_origin(run, observer, manifest, paths, dispatch_ids):
    """Add synthetic origin lifecycle and once-only partial review receipts."""
    roles = ('researcher', 'resume', 'reviewer-1', 'reviewer-2')
    origin_paths = {f'controls/{name}' for name in plan_source_names(run)}
    ledger_hashes = {}
    for role in roles:
        name = f'controls/origin/ledger/{role}/requests.jsonl'
        ledger_hashes[role] = put(run / name, '')
        origin_paths.add(name)
    revoked_sha = hashlib.sha256((run / 'controls/native-state/REVOKED').read_bytes()).hexdigest()
    manifest_sha = hashlib.sha256((run / 'controls/producer-manifest.json').read_bytes()).hexdigest()
    nonce = 'a' * 32
    resource_rows = [{'role': role, 'target': target, 'id': f'{index + 10:064x}'}
                     for index, (role, target) in enumerate((
                         ('researcher', 'target'), ('resume', 'target'),
                         ('reviewer-1', 'review-target-1'), ('reviewer-2', 'review-target-2')))]
    put(run / 'controls/origin/resources.json', {
        'kind': 'native-origin-resources-v1', 'status': 'removed', 'nonce': nonce,
        'resources': resource_rows})
    stop_sha = put(run / 'controls/origin/stopped.json', {
        'kind': 'native-origin-stopped-v1', 'nonce': nonce, 'native_stop_kind': 'REVOKED',
        'native_stop_sha256': revoked_sha, 'producer_manifest_sha256': manifest_sha,
        'ledger_sha256': ledger_hashes,
        'containers': [{'role': row['role'], 'id': row['id'], 'status': 'exited'}
                       for row in resource_rows]})
    cleanup_sha = put(run / 'controls/origin/cleanup.json', {
        'kind': 'native-origin-cleanup-v1', 'nonce': nonce, 'stopped_sha256': stop_sha,
        'resource_ids': [row['id'] for row in resource_rows], 'all_absent': True})
    origin_paths.update(('controls/origin/resources.json', 'controls/origin/stopped.json',
                         'controls/origin/cleanup.json'))
    records = []
    for dispatch_id in dispatch_ids:
        record_path = run / f'controls/dispatch/{dispatch_id}.json'
        record = json.loads(record_path.read_text())
        records.append(record)
        registration = f'controls/origin/registrations/{dispatch_id}.json'
        close = f'controls/origin/window-close/{dispatch_id}.json'
        target = 'target' if record['role'] in ('researcher', 'resume') else 'review-target-' + record['role'][-1]
        pre_path = run / 'controls/dispatch' / f'{dispatch_id}.pre.json'
        put(run / registration, {'kind': 'native-origin-registration-v1',
             'dispatch_id': dispatch_id, 'role': record['role'],
             'target': target,
             'dispatch_pre_sha256': hashlib.sha256(pre_path.read_bytes()).hexdigest(),
             'source_manifest_sha256': json.loads((run / 'plan.json').read_text())['source_manifest_sha256'],
             'target_image_id': json.loads((run / 'plan.json').read_text())['target_image_id'],
             'binary_sha256': json.loads((run / 'plan.json').read_text())['native_origin']['binary_sha256']})
        window_path = run / 'controls/observer' / target / f'window-{dispatch_id}.json'
        put(run / close, {'kind': 'native-origin-window-close-v1',
             'dispatch_id': dispatch_id,
             'target': 'target' if record['role'] in ('researcher', 'resume')
             else 'review-target-' + record['role'][-1],
             'window_sha256': hashlib.sha256(window_path.read_bytes()).hexdigest()})
        record['origin_registration_sha256'] = hashlib.sha256((run / registration).read_bytes()).hexdigest()
        record['origin_window_close_sha256'] = hashlib.sha256((run / close).read_bytes()).hexdigest()
        if dispatch_id == dispatch_ids[0]:
            proof = f'controls/origin/proofs/{dispatch_id}.json'
            put(run / proof, {'kind': 'native-origin-transport-proof-v1',
                 'status': 'process_request_attributed', 'dispatch_id': dispatch_id,
                 'role': record['role']})
            record['origin_transport_proof_sha256'] = hashlib.sha256((run / proof).read_bytes()).hexdigest()
            origin_paths.add(proof)
        put(record_path, record)
        origin_paths.update((registration, close))

    review_path = run / 'controls/review-reviewer-1.json'
    review = json.loads(review_path.read_text())
    review['input_id'] = 'a' * 64
    review['assessment']['status'] = 'unfinished'
    request_path = run / 'handoff/reviewer-1/REQUEST.json'
    request_sha = put(request_path, {'synthetic': 'review packet'})
    reviewer_id = dispatch_ids[2]
    trace_path = run / f'controls/dispatch/{reviewer_id}.trace.json'
    trace_sha = hashlib.sha256(trace_path.read_bytes()).hexdigest()
    review['native']['native_trace_sha256'] = trace_sha
    review['material'] = {
        'input_id': review['input_id'], 'packet_request_sha256': request_sha,
        'native_trace_sha256': trace_sha,
        'packet_pin': {'files': {'REQUEST.json': request_sha}},
        'shell_actions': [],
    }
    review_sha = put(review_path, review)
    put(run / f'controls/poststop-review-reviewer-1.json', {
        'status': 'candidate_for_operator_review', 'scope': 't01_original_vulnerable_arm',
        'reviewer_role': 'reviewer-1', 'review_dispatch_id': reviewer_id,
        'effect_dispatch_id': dispatch_ids[1], 'effect_request_id': 'e' * 32,
        'review_effect_request_id': 'f' * 32,
        'reviewer_material_check': 't01_effect_and_controls_observed',
        'qualification': 'partial', 'clean_replay': 'not_assessed',
        'fixed_control': 'not_assessed', 'lead_dispositions': 'unfinished_unassessed',
        'limits': ['does not establish full #159 qualification',
                   'does not independently assess strong-lead dismissal',
                   'model lead_dispositions remain untrusted review material'],
        'review_receipt_sha256': review_sha,
        'review_packet_request_sha256': request_sha,
        'review_trace_sha256': trace_sha,
        'semantic_receipt_sha256': '1' * 64,
        'review_semantic_receipt_sha256': '2' * 64,
        'reviewer_origin_proof_sha256': '3' * 64,
        'effect_origin_proof_sha256': {dispatch_ids[1]: '4' * 64},
    })
    poststop = 'controls/poststop-review-reviewer-1.json'
    paths.update(origin_paths)
    paths.add(poststop)
    final_path = run / 'controls/final.json'
    final = json.loads(final_path.read_text())
    final['origin_stop'] = {'status': 'complete', 'receipt_sha256': stop_sha}
    final['origin_cleanup'] = {'status': 'complete', 'receipt_sha256': cleanup_sha}
    put(final_path, final)
    paths.add('controls/final.json')
    manifest['run_receipts'] = run_receipts(run, paths)
    put(observer / 'manifest.json', manifest)
    return poststop, origin_paths


def plan_source_names(run):
    plan = json.loads((run / 'plan.json').read_text())
    return plan['native_origin']['source_sha256']


def main():
    with tempfile.TemporaryDirectory(prefix='native-acceptance-synthetic-') as tmp:
        parent = Path(tmp)
        run, observer = parent / 'run', parent / 'observer'
        run.mkdir(mode=0o700)
        observer.mkdir(mode=0o700)
        (run / 'controls').mkdir(mode=0o700)
        source = {'app.txt': put(run / 'original/app.txt', 'ordinary source\n'),
                  'app/Controller/ProjectPermissionController.php': put(
                      run / 'original/app/Controller/ProjectPermissionController.php',
                      'synthetic controller\n')}
        brief_sha = put(run / 'controls/BRIEF.md', 'ordinary unhinted brief\n')
        put(run / 'researcher/brief/BRIEF.md', 'ordinary unhinted brief\n')
        source_sha = hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()
        plan = {'kind': 'native-research-plan-v1', 'source_sha256': source,
                'source_manifest_sha256': source_sha, 'brief_sha256': brief_sha,
                'target_image_id': 'sha256:synthetic',
                'limits': {'max_connections': 8, 'max_bytes': 8192, 'duration_seconds': 120}}
        plan_sha = put(run / 'plan.json', plan)
        loaded_sha = put(run / 'controls/loaded-surface.json', {'model': 'synthetic', 'tools': []})
        put(run / 'controls/activation.json', {'kind': 'native-research-activation-v1',
                                               'nonce': 'a' * 32,
                                               'plan_sha256': plan_sha,
                                               'loaded_surface_sha256': loaded_sha})
        identity = {'manifest_sha256': 'a' * 64, 'nonce': 'a' * 32}
        counters = ((0, 0), (1, 20), (1, 20), (2, 40))
        dispatch_ids = []
        for index, (role, session) in enumerate((('researcher', 'ses_Research1'),
                                                  ('resume', 'ses_Research1'),
                                                  ('reviewer-1', 'ses_Review1'))):
            ident = f'{index + 1:032x}'
            dispatch_ids.append(ident)
            trace = {'kind': 'protected-native-event-trace-v1', 'session_id': session,
                     'events': [{'type': 'tool'}]}
            trace_sha = put(run / f'controls/dispatch/{ident}.trace.json', trace)
            before, after = counters[index], counters[index + 1]
            pool = lambda pair: {'run_identity': identity, 'hard_limits': plan['limits'],
                                 'used_tunnels': pair[0], 'charged_tunnel_bytes': pair[1]}
            put(run / f'controls/dispatch/{ident}.json', {
                'kind': 'native-dispatch-v1', 'dispatch_id': ident, 'role': role,
                'status': 'acknowledged', 'session_id': session, 'native_trace_sha256': trace_sha,
                'protected_capture': 'unavailable', 'prompt_sha256': 'p' * 64,
                'review_target_id': 'target-synthetic' if role == 'reviewer-1' else None,
                'review_target_source_sha256': source_sha if role == 'reviewer-1' else None,
                'pool_before': pool(before), 'pool_after': pool(after),
                'created_at': f'2026-10-22T00:00:0{index}Z'})
        put(run / 'controls/review-reviewer-1.json', {
            'status': 'native_turn_observed_unassessed', 'input_id': 'i' * 64,
            'session_id': 'ses_Review1', 'reviewer_role': 'reviewer-1',
            'same_original_allowance': True,
            'native': {'dispatch_id': dispatch_ids[2], 'role': 'reviewer-1', 'session_id': 'ses_Review1'},
            'assessment': {'status': 'candidate_for_operator_review', 'input_id': 'i' * 64,
                           'session_id': 'ses_Review1', 'effect_sha256': 'e' * 64,
                           'control_sha256': 'c' * 64,
                           'independent_check': {'status': 'observed',
                                                 'observer_origin': 'host_protected'}}})
        manifest_sha = put(run / 'controls/producer-manifest.json',
                           {'producers': [{'id': 'producer-synthetic'}]})
        revoked_sha = put(run / 'controls/native-state/REVOKED',
                          {'ids': ['producer-synthetic'], 'producers_verified_stopped': True,
                           'manifest_sha256': manifest_sha})
        snapshot_sha = put(run / 'controls/host-snapshot.json', {
            'kind': 'native-research-host-byte-receipt-v1', 'status': 'complete',
            'plan_sha256': plan_sha, 'native_stop': {'manifest_sha256': manifest_sha,
                                                  'revoked_sha256': revoked_sha}})
        final = {'status': 'stopped_complete', 'native_stop': {'status': 'stopped'},
                 'host_snapshot': {'status': 'complete',
                                   'receipt_path': str(run / 'controls/host-snapshot.json'),
                                   'receipt_sha256': snapshot_sha},
                 'cleanup': {'status': 'complete'},
                 'capture_stop': {'status': 'not_configured'},
                 'capture_cleanup': {'status': 'not_configured'}}
        put(run / 'controls/final.json', final)
        artifacts = {name: {'path': name + '.json',
                            'sha256': put(observer / (name + '.json'), {'synthetic': name})}
                     for name in REQUIRED}
        manifest = {'schema_version': 1, 'scenario': 'T04', 'plan_sha256': plan_sha,
                    'source_manifest_sha256': source_sha, 'run_receipts': run_receipts(run, BASE_RECEIPTS),
                    'artifacts': artifacts}
        put(observer / 'manifest.json', manifest)

        code, report = invoke(run, observer)
        assert code == 2 and 'fresh_review_candidate' in report['failed_checks'], report
        assert report['native_qualification'] == 'not_assessed', report
        assert report['checks']['capture_not_configured'] is True, report

        snapshot_path = run / 'controls/host-snapshot.json'
        snapshot = snapshot_path.read_bytes()
        snapshot_path.unlink()
        reject(run, observer, 'host_snapshot_bound')
        snapshot_path.write_bytes(snapshot)
        snapshot_path.chmod(0o600)
        put(snapshot_path, {'kind': 'native-research-host-byte-receipt-v1', 'status': 'complete',
                            'plan_sha256': '0' * 64})
        reject(run, observer, 'host_snapshot_bound')
        snapshot_path.write_bytes(snapshot)
        snapshot_path.chmod(0o600)

        final_path = run / 'controls/final.json'
        altered = dict(final)
        altered['host_snapshot'] = dict(final['host_snapshot'], receipt_sha256='0' * 64)
        put(final_path, altered)
        manifest['run_receipts']['controls/final.json'] = hashlib.sha256(final_path.read_bytes()).hexdigest()
        put(observer / 'manifest.json', manifest)
        reject(run, observer, 'host_snapshot_bound')
        put(final_path, final)
        manifest['run_receipts'] = run_receipts(run, BASE_RECEIPTS)
        put(observer / 'manifest.json', manifest)

        (run / 'researcher/brief/BRIEF.md').write_text('changed visible brief\n')
        code, report = invoke(run, observer)
        assert code == 2 and 'visible_brief_pinned' in report['failed_checks'], report
        put(run / 'researcher/brief/BRIEF.md', 'ordinary unhinted brief\n')

        (run / 'controls/loaded-surface.json').write_text('{"changed":true}\n')
        code, report = invoke(run, observer)
        assert code == 2 and 'loaded_surface_pinned' in report['failed_checks'], report
        put(run / 'controls/loaded-surface.json', {'model': 'synthetic', 'tools': []})

        (observer / 'host_trace.json').write_text('{"changed":true}\n')
        code, report = invoke(run, observer)
        assert code == 2 and 'observer_artifacts_pinned' in report['failed_checks'], report
        put(observer / 'host_trace.json', {'synthetic': 'host_trace'})

        (observer / 'clean_replay_and_controls.json').unlink()
        code, report = invoke(run, observer)
        assert code == 2 and 'observer_artifacts_pinned' in report['failed_checks'], report
        put(observer / 'clean_replay_and_controls.json', {'synthetic': 'clean_replay_and_controls'})

        resume = run / f'controls/dispatch/{dispatch_ids[1]}.json'
        value = json.loads(resume.read_text())
        value['session_id'] = 'ses_Different1'
        put(resume, value)
        code, report = invoke(run, observer)
        assert code == 2 and 'research_resume_same_session' in report['failed_checks'], report
        value['session_id'] = 'ses_Research1'
        put(resume, value)

        review = run / 'controls/review-reviewer-1.json'
        value = json.loads(review.read_text())
        value['assessment']['status'] = 'unfinished'
        put(review, value)
        code, report = invoke(run, observer)
        assert code == 2 and 'fresh_review_candidate' in report['failed_checks'], report

        value['assessment']['status'] = 'candidate_for_operator_review'
        put(review, value)

        capture_paths = seed_capture(run, observer, plan, manifest, dispatch_ids, final)
        code, report = invoke(run, observer)
        assert code == 2 and 'fresh_review_candidate' in report['failed_checks'], report
        assert report['native_qualification'] == 'not_assessed', report
        assert report['checks']['capture_receipts_bound'] is True, report

        stage_name = 'controls/observer/target/stage.json'
        stage_path = run / stage_name
        stage_bytes = stage_path.read_bytes()
        stage_path.unlink()
        reject(run, observer, 'capture_receipts_bound')
        stage_path.write_bytes(stage_bytes)
        stage_path.chmod(0o600)
        stage = json.loads(stage_path.read_text())
        stage['probe_sha256'] = '0' * 64
        put(stage_path, stage)
        repin(run, observer, manifest, stage_name)
        reject(run, observer, 'capture_receipts_bound')
        stage_path.write_bytes(stage_bytes)
        stage_path.chmod(0o600)
        repin(run, observer, manifest, stage_name)

        window_name = f'controls/observer/target/window-{dispatch_ids[0]}.json'
        window_path = run / window_name
        window_bytes = window_path.read_bytes()
        window_path.unlink()
        reject(run, observer, 'capture_receipts_bound')
        window_path.write_bytes(window_bytes)
        window_path.chmod(0o600)

        pre_name = f'controls/dispatch/{dispatch_ids[0]}.pre.json'
        pre_path = run / pre_name
        pre_bytes = pre_path.read_bytes()
        pre = json.loads(pre_path.read_text())
        pre['session_id'] = 'ses_Unrelated'
        put(pre_path, pre)
        repin(run, observer, manifest, pre_name)
        reject(run, observer, 'capture_receipts_bound')
        pre_path.write_bytes(pre_bytes)
        pre_path.chmod(0o600)
        repin(run, observer, manifest, pre_name)

        origin_name = f'controls/dispatch/{dispatch_ids[0]}.origin.json'
        origin_path = run / origin_name
        origin = json.loads(origin_path.read_text())
        origin['dispatch_id'] = dispatch_ids[1]
        put(origin_path, origin)
        repin(run, observer, manifest, origin_name)
        reject(run, observer, 'capture_receipts_bound')
        origin['dispatch_id'] = dispatch_ids[0]
        put(origin_path, origin)
        repin(run, observer, manifest, origin_name)

        db_name = 'controls/observer/target/receipts/receipts.sqlite'
        db_path = run / db_name
        db_bytes = db_path.read_bytes()
        with sqlite3.connect(db_path) as db:
            db.execute('INSERT INTO receipts VALUES (2, ?, ?)', ('synthetic', '{}'))
        repin(run, observer, manifest, db_name)
        reject(run, observer, 'capture_receipts_bound')
        db_path.write_bytes(db_bytes)
        db_path.chmod(0o600)
        repin(run, observer, manifest, db_name)

        frozen_name = 'controls/observer/target/frozen.json'
        frozen_path = run / frozen_name
        frozen_bytes = frozen_path.read_bytes()
        frozen_path.unlink()
        reject(run, observer, 'capture_receipts_bound')
        frozen_path.write_bytes(frozen_bytes)
        frozen_path.chmod(0o600)
        frozen = json.loads(frozen_bytes)
        for field in ('native_stop_sha256', 'producer_manifest_sha256'):
            put(frozen_path, dict(frozen, **{field: '0' * 64}))
            repin(run, observer, manifest, frozen_name)
            reject(run, observer, 'capture_receipts_bound')
        put(frozen_path, frozen)
        repin(run, observer, manifest, frozen_name)

        ledger_name = 'controls/observer/target/resources.json'
        ledger_path = run / ledger_name
        ledger = json.loads(ledger_path.read_text())
        ledger['status'] = 'frozen'
        put(ledger_path, ledger)
        repin(run, observer, manifest, ledger_name)
        reject(run, observer, 'capture_receipts_bound')
        ledger['status'] = 'removed'
        put(ledger_path, ledger)
        repin(run, observer, manifest, ledger_name)

        final_name = 'controls/final.json'
        final['capture_stop']['status'] = 'unresolved'
        put(run / final_name, final)
        repin(run, observer, manifest, final_name)
        reject(run, observer, 'capture_receipts_bound')
        final['capture_stop']['status'] = 'complete'
        final['capture_cleanup']['status'] = 'unresolved'
        put(run / final_name, final)
        repin(run, observer, manifest, final_name)
        reject(run, observer, 'capture_receipts_bound')
        final['capture_cleanup']['status'] = 'complete'
        put(run / final_name, final)
        repin(run, observer, manifest, final_name)
        assert set(manifest['run_receipts']) == capture_paths
        code, report = invoke(run, observer)
        assert code == 2 and 'fresh_review_candidate' in report['failed_checks'], report

        challenge_names = ('challenge_input', 'host_trace', 'contrary_and_controls',
                           'native_review', 'updated_claim_and_output', 'cost_and_cleanup')
        challenge_artifacts = {name: {'path': name + '-f01.json',
                                      'sha256': put(observer / (name + '-f01.json'),
                                                    {'synthetic': name})}
                               for name in challenge_names}
        manifest['scenario'] = 'F01'
        manifest['artifacts'] = challenge_artifacts
        put(observer / 'manifest.json', manifest)
        code, report = invoke(run, observer)
        assert code == 2 and 'fresh_review_candidate' in report['failed_checks'], report
        manifest['scenario'] = 'F99'
        put(observer / 'manifest.json', manifest)
        code, report = invoke(run, observer)
        assert code == 2 and 'observer_manifest' in report['failed_checks'], report

        manifest['scenario'] = 'F01'
        t01_paths = seed_t01(run, observer, plan, manifest, dispatch_ids, final, capture_paths)
        poststop_name, origin_paths = seed_poststop_origin(
            run, observer, manifest, t01_paths, dispatch_ids)
        code, report = invoke(run, observer)
        assert code == 0 and report['status'] == 'inventory_complete_for_operator_review', report
        assert report['checks']['capture_receipts_bound'] is True, report
        assert report['review_candidate']['reviewer_material_check'] == 't01_effect_and_controls_observed'
        assert report['review_candidate']['qualification'] == 'partial'
        assert set(manifest['run_receipts']) == t01_paths | origin_paths | {poststop_name}
        spec = importlib.util.spec_from_file_location('native_inventory', CHECKER)
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        records = [json.loads((run / f'controls/dispatch/{ident}.json').read_text())
                   for ident in dispatch_ids]
        second_review = dict(records[-1], dispatch_id='4' * 32, role='reviewer-2')
        needed = checker.required_run_receipts(run, json.loads((run / 'plan.json').read_text()),
                                               records + [second_review], manifest)
        assert poststop_name in needed and 'controls/poststop-review-reviewer-2.json' not in needed

        poststop_path = run / poststop_name
        poststop = json.loads(poststop_path.read_text())
        variants = {'status': 'held', 'reviewer_role': 'reviewer-2',
                    'review_dispatch_id': dispatch_ids[0], 'effect_dispatch_id': 'f' * 32,
                    'effect_request_id': 'not-a-request-id',
                    'review_effect_request_id': 'not-a-request-id'}
        for field, invalid in variants.items():
            put(poststop_path, poststop | {field: invalid})
            repin(run, observer, manifest, poststop_name)
            reject(run, observer, 'fresh_review_candidate')
        put(poststop_path, poststop)
        repin(run, observer, manifest, poststop_name)

        review_path = run / 'controls/review-reviewer-1.json'
        review_bytes = review_path.read_bytes()
        request_path = run / 'handoff/reviewer-1/REQUEST.json'
        request_bytes = request_path.read_bytes()
        review = json.loads(review_bytes)
        review['session_id'] = 'ses_Unrelated'
        put(review_path, review)
        reject(run, observer, 'fresh_review_candidate')
        review['session_id'] = 'ses_Review1'
        review['material']['native_trace_sha256'] = '0' * 64
        put(review_path, review)
        reject(run, observer, 'fresh_review_candidate')
        request_sha = put(request_path, {'synthetic': 'changed packet'})
        review['material']['packet_request_sha256'] = request_sha
        review['material']['packet_pin']['files']['REQUEST.json'] = request_sha
        put(review_path, review)
        reject(run, observer, 'fresh_review_candidate')
        review_path.write_bytes(review_bytes)
        review_path.chmod(0o600)
        request_path.write_bytes(request_bytes)
        request_path.chmod(0o600)

        for name in ('controls/tools/native_origin/protocol.go',
                     'controls/origin/stopped.json',
                     'controls/origin/ledger/researcher/requests.jsonl',
                     f'controls/origin/registrations/{dispatch_ids[0]}.json',
                     f'controls/origin/window-close/{dispatch_ids[0]}.json',
                     f'controls/origin/proofs/{dispatch_ids[0]}.json'):
            path = run / name
            original = path.read_bytes()
            path.unlink()
            reject(run, observer, 'run_receipts_bound')
            path.write_bytes(original)
            path.chmod(0o600)
            path.write_bytes(original + b'changed')
            reject(run, observer, 'run_receipts_bound')
            path.write_bytes(original)
            path.chmod(0o600)

        registration_name = f'controls/origin/registrations/{dispatch_ids[0]}.json'
        registration_path = run / registration_name
        registration = json.loads(registration_path.read_text())
        put(registration_path, registration | {'dispatch_id': dispatch_ids[1]})
        repin(run, observer, manifest, registration_name)
        reject(run, observer, 'origin_receipts_bound')
        put(registration_path, registration)
        repin(run, observer, manifest, registration_name)
        ledger_name = 'controls/origin/ledger/researcher/requests.jsonl'
        ledger_path = run / ledger_name
        ledger = ledger_path.read_bytes()
        ledger_path.write_bytes(b'changed ledger\n')
        repin(run, observer, manifest, ledger_name)
        reject(run, observer, 'origin_receipts_bound')
        ledger_path.write_bytes(ledger)
        ledger_path.chmod(0o600)
        repin(run, observer, manifest, ledger_name)

        poststop_path.unlink()
        reject(run, observer, 'run_receipts_bound')
        put(poststop_path, poststop)
        poststop['effect_dispatch_id'] = 'f' * 32
        put(poststop_path, poststop)
        repin(run, observer, manifest, poststop_name)
        reject(run, observer, 'fresh_review_candidate')
        poststop['effect_dispatch_id'] = dispatch_ids[1]
        put(poststop_path, poststop)
        repin(run, observer, manifest, poststop_name)

        review = json.loads(review_path.read_text())
        review['assessment']['status'] = 'candidate_for_operator_review'
        put(review_path, review)
        poststop_path.unlink()
        manifest['run_receipts'].pop(poststop_name)
        put(observer / 'manifest.json', manifest)
        reject(run, observer, 'fresh_review_candidate')
        poststop['effect_dispatch_id'] = dispatch_ids[1]
        put(poststop_path, poststop)
        review['assessment']['status'] = 'unfinished'
        put(review_path, review)
        manifest['run_receipts'] = run_receipts(
            run, t01_paths | origin_paths | {poststop_name})
        put(observer / 'manifest.json', manifest)

        for name in (f'controls/observer/target/{item}' for item in
                     ('broker.php', 'setup-readback.json', f'closed-{dispatch_ids[0]}.json')):
            path = run / name
            original = path.read_bytes()
            path.unlink()
            reject(run, observer, 'capture_receipts_bound')
            path.write_bytes(original)
            path.chmod(0o600)
        closed_name = f'controls/observer/target/closed-{dispatch_ids[0]}.json'
        closed_path = run / closed_name
        closed = json.loads(closed_path.read_text())
        put(closed_path, dict(closed, window_sha256='0' * 64))
        repin(run, observer, manifest, closed_name)
        reject(run, observer, 'capture_receipts_bound')
        put(closed_path, closed)
        repin(run, observer, manifest, closed_name)
        setup_name = 'controls/observer/target/setup-readback.json'
        setup_path = run / setup_name
        setup = json.loads(setup_path.read_text())
        put(setup_path, dict(setup, receipt_sha256='0' * 64))
        repin(run, observer, manifest, setup_name)
        reject(run, observer, 'capture_receipts_bound')
        put(setup_path, setup)
        repin(run, observer, manifest, setup_name)

        code, report = invoke(run, observer)
        assert code == 0 and report['checks']['capture_receipts_bound'] is True, report

    print('PASS: synthetic T04/F01 S10/T01 inventory holds stale legacy review, admits only a bound partial T01 poststop candidate, and rejects missing/changed origin lifecycle evidence; provider_calls=0 target_calls=0')


if __name__ == '__main__':
    main()
