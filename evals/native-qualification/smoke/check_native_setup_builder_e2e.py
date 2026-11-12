#!/usr/bin/env python3
"""Public #202 builder scenario with synthetic #208 authority and stop receipts.

Requires a local Docker daemon and an already-local BusyBox 1.37 image. No
provider or target service is contacted. See SETUP-BUILDER-E2E.md.
"""

import argparse
import atexit
import base64
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
from engagement_records import canonical_json_bytes  # noqa: E402
from operator_signature import encode_operator_signature_proof  # noqa: E402

NAMESPACE = 'llm-redteam-harness-native-setup-v1'
RELAY_SOURCE = ROOT / 'experiments/native-network-preflight/tcp_relay.go'
SETUP = ROOT / 'tools/native_research.py'
BUILDER = ROOT / 'tools/native_setup_builder.py'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def call(*argv, timeout=60, env=None):
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False,
                          env=env)


def cli(path, *args, timeout=60, env=None):
    result = call(sys.executable, str(path), *args, timeout=timeout, env=env)
    try:
        payload = json.loads(result.stdout)
    except ValueError:
        payload = {'code': 'non_json_cli_output', 'stderr': result.stderr[:1000]}
    return result.returncode, payload


def crash_after_checked_rename(run_root, approval, catalog):
    script = r'''
import os
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[1])
import native_setup_builder as builder
root = Path(sys.argv[2])
original = os.rename
def interrupt(source, destination):
    original(source, destination)
    if (Path(source) == root / 'controls/setup-build/stage'
            and Path(destination) == root / 'controls/setup-checked'):
        raise SystemExit(73)
os.rename = interrupt
sys.argv = [str(builder.__file__), 'setup-build', '--run-root', str(root),
            '--approval', sys.argv[3], '--dependency-catalog', sys.argv[4]]
builder.main()
raise SystemExit(74)
'''
    return call(sys.executable, '-c', script, str(ROOT / 'tools'), str(run_root),
                str(approval), str(catalog), timeout=120)


def signed(value, key, signers, fingerprint):
    challenge = canonical_json_bytes(value)
    signature = subprocess.run(['ssh-keygen', '-Y', 'sign', '-f', str(key), '-n', NAMESPACE],
                               input=challenge, capture_output=True, check=True, timeout=10).stdout
    return {**value, 'operator_signature': encode_operator_signature_proof(
        challenge_bytes=challenge, signature_bytes=signature,
        allowed_signers_bytes=signers.read_bytes(), signer_fingerprint=fingerprint)}


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--keep-root', type=Path,
                        help='retain the private synthetic fixture without its signing key')
    parser.add_argument('--emit-research-scope-fixtures', action='store_true',
                        help='sign downstream synthetic research scopes before removing the test key')
    args = parser.parse_args()
    if args.emit_research_scope_fixtures and not args.keep_root:
        parser.error('--emit-research-scope-fixtures requires --keep-root')
    if args.keep_root:
        if not args.keep_root.is_absolute() or args.keep_root.exists():
            parser.error('--keep-root must be a new absolute directory')
        args.keep_root.mkdir(mode=0o700)
    checks = []

    def check(name, passed, observed):
        checks.append({'name': name, 'passed': bool(passed), 'observed': observed})

    context = (nullcontext(str(args.keep_root)) if args.keep_root else
               tempfile.TemporaryDirectory(prefix='native-setup-builder-e2e-'))
    with context as raw:
        base = Path(raw).resolve()
        source = base / 'source'
        (source / 'pkg').mkdir(parents=True)
        (source / 'main.txt').write_text('hello from source\n')
        (source / 'pkg/message.txt').write_text('second source file\n')
        (source / 'build.sh').write_text(
            'mkdir -p out\ncat main.txt > out/result.txt\n'
            '/deps/data.txt >> out/result.txt\nchmod 700 out/result.txt\n')
        source_files = {path.relative_to(source).as_posix(): sha(path)
                        for path in sorted(source.rglob('*')) if path.is_file()}
        manifest_hash = hashlib.sha256(json.dumps(source_files, sort_keys=True).encode()).hexdigest()
        goal = base / 'goal.md'
        goal.write_text('Assess this harmless local source for a concrete unsafe effect, '
                        'with a control and clear limits.\n')
        key = base / 'operator_key'
        subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)],
                       check=True, timeout=10)
        atexit.register(key.unlink, missing_ok=True)
        signers = base / 'allowed_signers'
        signers.write_text('synthetic-operator ' + (base / 'operator_key.pub').read_text())
        fingerprint_b64 = call('ssh-keygen', '-lf', str(base / 'operator_key.pub'),
                               '-E', 'sha256').stdout.split('SHA256:')[1].split()[0]
        fingerprint = 'sha256:' + base64.b64decode(
            fingerprint_b64 + '=' * (-len(fingerprint_b64) % 4)).hex()
        now = datetime.now(timezone.utc).replace(microsecond=0)
        stamp = lambda time: time.strftime('%Y-%m-%dT%H:%M:%SZ')
        scope = base / 'scope.md'
        scope_body = {'kind': 'native-setup-scope-v1', 'engagement_id': 'fixture-202',
                      'operator_id': 'synthetic-operator', 'source_manifest_sha256': manifest_hash,
                      'goal_sha256': sha(goal), 'surfaces': ['owned original source tree'],
                      'benign_objectives': ['prepare an offline runtime recipe and threat model'],
                      'escalation_ceiling': 'setup_only', 'impact_demo_authorized': False,
                      'accounts': [], 'cleanup': 'Stop and remove every owned setup container and network.',
                      'effect_class': 'read-only-original-and-disposable-offline-proposal',
                      'network_class': 'metered-model-relay-only',
                      'expires_at': stamp(now + timedelta(hours=2))}
        scope.write_text('# Synthetic scope\n\n- Operator allowed signers SHA256: sha256:' +
                         sha(signers) + '\n\n```native-setup-scope-v1\n' +
                         json.dumps(scope_body, sort_keys=True) + '\n```\n')
        scope_signature = base / 'scope.sig'
        challenge = canonical_json_bytes({'kind': 'native-setup-scope-challenge-v1',
                                          'engagement_id': 'fixture-202', 'scope_sha256': sha(scope)})
        scope_signature.write_bytes(subprocess.run(
            ['ssh-keygen', '-Y', 'sign', '-f', str(key), '-n', NAMESPACE], input=challenge,
            capture_output=True, check=True, timeout=10).stdout)
        relay = base / 'relay'
        ca = base / 'ca.pem'
        ca_key = base / 'ca.key'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-noenc',
                        '-days', '1', '-subj', '/CN=setup builder fixture', '-keyout',
                        str(ca_key), '-out', str(ca)], capture_output=True, check=True, timeout=30)
        ca_key.unlink()
        image = call('docker', 'image', 'ls', 'busybox:1.37', '--no-trunc',
                     '--format', '{{.ID}}')
        if image.returncode or not image.stdout.strip():
            raise RuntimeError('busybox:1.37 must already be local')
        image_id = image.stdout.splitlines()[0].strip()
        platform = call('docker', 'image', 'inspect', image_id,
                        '--format', '{{.Os}}/{{.Architecture}}').stdout.strip()
        architecture = platform.split('/')[1]
        subprocess.run(['go', 'build', '-o', str(relay), str(RELAY_SOURCE)],
                       env={**os.environ, 'GOOS': 'linux', 'GOARCH': architecture,
                            'CGO_ENABLED': '0'}, capture_output=True, check=True, timeout=60)
        relay.chmod(0o700)
        run_root = base / 'run'
        prepared_code, prepared = cli(SETUP, 'prepare', '--setup-only', '--run-root', str(run_root),
                                     '--source', str(source), '--brief', str(goal),
                                     '--scope-file', str(scope), '--scope-sha256', sha(scope),
                                     '--setup-scope-signature', str(scope_signature),
                                     '--setup-allowed-signers', str(signers),
                                     '--setup-trusted-fingerprint', fingerprint,
                                     '--setup-operator-id', 'synthetic-operator',
                                     '--setup-engagement-id', 'fixture-202',
                                     '--relay', str(relay), '--relay-sha256', sha(relay),
                                     '--runtime-ca', str(ca), '--runtime-ca-sha256', sha(ca),
                                     '--image-id', image_id, '--platform', platform,
                                     '--max-connections', '2', '--max-bytes', '1048576',
                                     '--duration-seconds', '120')
        if prepared_code:
            raise RuntimeError('setup prepare failed: ' + str(prepared))
        setup_template_code, setup_template = cli(SETUP, 'setup-approval-template',
                                                 '--run-root', str(run_root),
                                                 '--approved-at', stamp(now),
                                                 '--expires-at', stamp(now + timedelta(hours=1)))
        if setup_template_code:
            raise RuntimeError('setup approval template failed: ' + str(setup_template))
        controls = run_root / 'controls'
        setup_approval = signed(setup_template, key, signers, fingerprint)
        (controls / 'approval.json').write_text(json.dumps(setup_approval, sort_keys=True) + '\n')
        (controls / 'setup-approval-receipt.json').write_text(json.dumps({
            'kind': 'native-setup-approval-receipt-v1',
            'approval_sha256': sha(controls / 'approval.json'),
            'signer_fingerprint': fingerprint}, sort_keys=True) + '\n')
        dispatch_id = 'a' * 32
        producer_ids = ['b' * 64, 'c' * 64]
        manifest = {'producers': [{'id': value} for value in producer_ids]}
        (controls / 'producer-manifest.json').write_text(json.dumps(manifest, sort_keys=True) + '\n')
        manifest_sha = sha(controls / 'producer-manifest.json')
        state = controls / 'native-state'
        state.mkdir(exist_ok=True)
        (state / 'RUN.json').write_text(json.dumps({
            'ids': producer_ids, 'manifest_sha256': manifest_sha}, sort_keys=True) + '\n')
        (state / 'REVOKED').write_text(json.dumps({
            'ids': producer_ids, 'manifest_sha256': manifest_sha,
            'producers_verified_stopped': True}, sort_keys=True) + '\n')
        resources = {'resources': [
            {'kind': 'container', 'name': 'synthetic-researcher', 'id': producer_ids[0]},
            {'kind': 'container', 'name': 'synthetic-relay', 'id': producer_ids[1]},
            {'kind': 'network', 'name': 'synthetic-network', 'id': 'd' * 64}]}
        (controls / 'resources.json').write_text(json.dumps(resources, sort_keys=True) + '\n')
        provider = controls / 'provider'
        provider.mkdir(exist_ok=True)
        created = now.timestamp()
        provider_config = {'producer_manifest_sha256': manifest_sha,
                           'max_connections': 2, 'max_bytes': 1048576,
                           'native_run_duration': 120, 'duration': 120,
                           'authority': 'opencode.ai:443'}
        connection = sqlite3.connect(provider / 'tunnel.sqlite3')
        connection.execute('CREATE TABLE pool (config TEXT, created REAL, bytes INTEGER)')
        connection.execute('INSERT INTO pool VALUES (?,?,?)',
                           (json.dumps(provider_config), created, 0))
        connection.execute('CREATE TABLE tunnels (phase TEXT, uploaded INTEGER DEFAULT 0, '
                           'downloaded INTEGER DEFAULT 0)')
        connection.commit()
        connection.close()
        pool_after = {'hard_limits': {'max_connections': 2, 'max_bytes': 1048576,
                                      'duration_seconds': 120},
                      'used_tunnels': 0, 'charged_tunnel_bytes': 0,
                      'provider_deadline_unix': created + 120,
                      'run_identity': {'manifest_sha256': manifest_sha, 'ids': producer_ids}}
        dispatch = {'kind': 'native-dispatch-v1', 'role': 'researcher',
                    'dispatch_id': dispatch_id, 'setup_sequence': 1,
                    'status': 'acknowledged', 'pool_after': pool_after}
        dispatch_dir = controls / 'dispatch'
        (dispatch_dir / (dispatch_id + '.json')).write_text(json.dumps(dispatch, sort_keys=True) + '\n')
        (dispatch_dir / (dispatch_id + '.trace.json')).write_text('{}\n')
        frozen = controls / 'setup-output'
        frozen.mkdir()
        recipe = {'kind': 'native-setup-recipe-v1',
                  'runtime': {'version_command': ['sh', '-c', 'printf busybox-fixture-v1'],
                              'version_stdout': 'busybox-fixture-v1',
                              'dependency_command': ['test', '-f', '/deps/data.txt']},
                  'build_command': ['sh', 'build.sh'], 'offline_dependencies': ['data.txt']}
        (frozen / 'recipe.json').write_text(json.dumps(recipe, sort_keys=True) + '\n')
        (frozen / 'THREAT_MODEL.md').write_text(
            '# Fixture threat model\n\nAsset: harmless output. Boundary: read-only source.\n')
        plan = json.loads((run_root / 'plan.json').read_text())
        frozen_receipt = {'kind': 'native-setup-output-v1', 'status': 'frozen_proposal',
                          'plan_sha256': sha(run_root / 'plan.json'),
                          'approval_sha256': sha(controls / 'approval.json'),
                          'original_source_manifest_sha256': manifest_hash,
                          'dispatch_id': dispatch_id, 'setup_sequence': 1,
                          'dispatch_sha256': sha(dispatch_dir / (dispatch_id + '.json')),
                          'native_trace_sha256': sha(dispatch_dir / (dispatch_id + '.trace.json')),
                          'pool_before': None, 'pool_after': pool_after, 'native_usage': None,
                          'files': {'recipe.json': sha(frozen / 'recipe.json'),
                                    'THREAT_MODEL.md': sha(frozen / 'THREAT_MODEL.md')},
                          'assessment': 'proposal_needs_host_review',
                          'target_build_executed': False, 'security_result': None}
        (frozen / 'receipt.json').write_text(json.dumps(frozen_receipt, sort_keys=True) + '\n')
        snapshot = {'kind': 'native-setup-host-byte-receipt-v1', 'status': 'complete',
                    'plan_sha256': sha(run_root / 'plan.json'),
                    'original_source_manifest_sha256': manifest_hash,
                    'setup_output_receipt_sha256': sha(frozen / 'receipt.json'),
                    'native_store': {'status': 'missing', 'present': False},
                    'native_stop': {
                        'manifest_sha256': manifest_sha,
                        'producer_ids_sha256': hashlib.sha256(json.dumps(
                            producer_ids, separators=(',', ':')).encode()).hexdigest(),
                        'revoked_sha256': sha(state / 'REVOKED')}}
        (controls / 'host-snapshot.json').write_text(json.dumps(snapshot, sort_keys=True) + '\n')
        cleanup = {'status': 'complete', 'resources': [
            {'kind': row['kind'], 'name': row['name'], 'absent': True}
            for row in reversed(resources['resources'])]}
        (controls / 'cleanup.json').write_text(json.dumps(cleanup, sort_keys=True) + '\n')
        final = {'status': 'stopped_complete', 'native_stop': {'status': 'stopped'},
                 'host_snapshot': {'status': 'complete', 'receipt_sha256': sha(controls / 'host-snapshot.json')},
                 'cleanup': cleanup}
        (controls / 'final.json').write_text(json.dumps(final, sort_keys=True) + '\n')
        linked_root = base / 'linked-run'
        shutil.copytree(run_root, linked_root)
        linked_controls = linked_root / 'controls'
        linked_grant = dict(setup_template, kind='native-setup-approval-v2',
                            initial_run_root=str(linked_root),
                            absolute_deadline=stamp(now + timedelta(seconds=120)))
        (linked_controls / 'approval.json').write_text(json.dumps(
            signed(linked_grant, key, signers, fingerprint), sort_keys=True) + '\n')
        (linked_controls / 'setup-approval-receipt.json').write_text(json.dumps({
            'kind': 'native-setup-approval-receipt-v1',
            'approval_sha256': sha(linked_controls / 'approval.json'),
            'signer_fingerprint': fingerprint}, sort_keys=True) + '\n')
        linked_resources = {'resources': [
            {'kind': 'container', 'role': 'relay', 'name': 'synthetic-relay', 'id': producer_ids[0]},
            {'kind': 'container', 'role': 'researcher', 'name': 'synthetic-researcher', 'id': producer_ids[1]},
            {'kind': 'network', 'role': 'external', 'name': 'synthetic-external', 'id': 'd' * 64},
            {'kind': 'network', 'role': 'research', 'name': 'synthetic-research', 'id': 'e' * 64}]}
        (linked_controls / 'resources.json').write_text(json.dumps(linked_resources, sort_keys=True) + '\n')
        linked_cleanup = {'status': 'complete', 'resources': [
            {'kind': row['kind'], 'name': row['name'], 'absent': True}
            for row in reversed(linked_resources['resources'])]}
        (linked_controls / 'cleanup.json').write_text(json.dumps(linked_cleanup, sort_keys=True) + '\n')
        linked_checkpoint = linked_controls / 'setup-checkpoints' / dispatch_id
        linked_checkpoint.mkdir(parents=True)
        for filename in ('recipe.json', 'THREAT_MODEL.md'):
            shutil.copyfile(linked_controls / 'setup-output' / filename, linked_checkpoint / filename)
        linked_trace = linked_controls / 'dispatch' / (dispatch_id + '.trace.json')
        linked_checkpoint_receipt = {
            'kind': 'native-setup-checkpoint-v1', 'plan_sha256': sha(linked_root / 'plan.json'),
            'approval_sha256': sha(linked_controls / 'approval.json'),
            'dispatch_id': dispatch_id, 'native_trace_sha256': sha(linked_trace),
            'pool_after': pool_after, 'files': frozen_receipt['files']}
        (linked_checkpoint / 'receipt.json').write_text(json.dumps(
            linked_checkpoint_receipt, sort_keys=True) + '\n')
        linked_dispatch = dict(dispatch, session_id='ses_fixture',
                               native_trace_sha256=sha(linked_trace),
                               checkpoint_sha256=sha(linked_checkpoint / 'receipt.json'))
        linked_dispatch_path = linked_controls / 'dispatch' / (dispatch_id + '.json')
        linked_dispatch_path.write_text(json.dumps(linked_dispatch, sort_keys=True) + '\n')
        linked_frozen = linked_controls / 'setup-output'
        linked_frozen_receipt = dict(frozen_receipt,
                                     approval_sha256=sha(linked_controls / 'approval.json'),
                                     dispatch_sha256=sha(linked_dispatch_path))
        (linked_frozen / 'receipt.json').write_text(json.dumps(linked_frozen_receipt, sort_keys=True) + '\n')
        linked_snapshot = dict(snapshot, setup_output_receipt_sha256=sha(linked_frozen / 'receipt.json'))
        (linked_controls / 'host-snapshot.json').write_text(json.dumps(linked_snapshot, sort_keys=True) + '\n')
        linked_final = dict(final, cleanup=linked_cleanup,
                            host_snapshot={'status': 'complete',
                                           'receipt_sha256': sha(linked_controls / 'host-snapshot.json')})
        (linked_controls / 'final.json').write_text(json.dumps(linked_final, sort_keys=True) + '\n')
        with sqlite3.connect(linked_controls / 'provider/tunnel.sqlite3') as db:
            db.execute('DROP TABLE tunnels')
            db.execute('CREATE TABLE tunnels(id INTEGER PRIMARY KEY,phase TEXT, '
                       'uploaded INTEGER DEFAULT 0, downloaded INTEGER DEFAULT 0)')
        catalog = base / 'catalog'
        (catalog / 'payload').mkdir(parents=True)
        (catalog / 'payload/data.txt').write_text('#!/bin/sh\nprintf "hello from dependency\\n"\n')
        (catalog / 'payload/data.txt').chmod(0o700)
        (catalog / 'catalog.json').write_text(json.dumps({
            'kind': 'native-setup-dependency-catalog-v1',
            'entries': [{'id': 'data.txt', 'path': 'payload/data.txt',
                         'sha256': sha(catalog / 'payload/data.txt'), 'mode': 0o700}]},
            sort_keys=True) + '\n')
        template_args = ('setup-build-approval-template', '--run-root', str(run_root),
                         '--image-id', image_id, '--dependency-catalog', str(catalog),
                         '--max-workspace-bytes', '8388608', '--memory-bytes', '67108864',
                         '--duration-seconds', '30', '--output-path', 'out/result.txt',
                         '--approved-at', stamp(now),
                         '--expires-at', stamp(now + timedelta(hours=1)))
        state_files = [dispatch_dir / (dispatch_id + '.json'), frozen / 'receipt.json',
                       controls / 'host-snapshot.json', controls / 'final.json']
        original_state = {path: path.read_bytes() for path in state_files}
        with sqlite3.connect(provider / 'tunnel.sqlite3') as db:
            db.execute("INSERT INTO tunnels(phase,uploaded) VALUES('active',4096)")
            db.execute('UPDATE pool SET bytes=4096')
        pool_after['used_tunnels'], pool_after['charged_tunnel_bytes'] = 1, 4096
        dispatch['pool_after'] = pool_after
        (dispatch_dir / (dispatch_id + '.json')).write_text(json.dumps(dispatch, sort_keys=True) + '\n')
        frozen_receipt['pool_after'] = pool_after
        frozen_receipt['dispatch_sha256'] = sha(dispatch_dir / (dispatch_id + '.json'))
        (frozen / 'receipt.json').write_text(json.dumps(frozen_receipt, sort_keys=True) + '\n')
        snapshot['setup_output_receipt_sha256'] = sha(frozen / 'receipt.json')
        (controls / 'host-snapshot.json').write_text(json.dumps(snapshot, sort_keys=True) + '\n')
        final['host_snapshot']['receipt_sha256'] = sha(controls / 'host-snapshot.json')
        (controls / 'final.json').write_text(json.dumps(final, sort_keys=True) + '\n')
        active_code, active_result = cli(BUILDER, *template_args)
        check('active provider tunnel refuses offline build approval',
              active_code == 2, {'exit': active_code, 'code': active_result.get('code')})
        with sqlite3.connect(provider / 'tunnel.sqlite3') as db:
            db.execute("UPDATE tunnels SET phase='closed',uploaded=2048")
        mismatch_code, mismatch_result = cli(BUILDER, *template_args)
        check('provider byte sum mismatch refuses offline build approval',
              mismatch_code == 2, {'exit': mismatch_code, 'code': mismatch_result.get('code')})
        with sqlite3.connect(provider / 'tunnel.sqlite3') as db:
            db.execute('DELETE FROM tunnels')
            db.execute('UPDATE pool SET bytes=0')
        for path, data in original_state.items():
            path.write_bytes(data)
        (state / 'REVOKED').rename(state / 'REVOKED-held')
        stopped_code, incomplete_stop = cli(BUILDER, *template_args)
        check('missing native stop proof rejects before template or build',
              stopped_code == 2 and incomplete_stop.get('code') == 'regular_file_unavailable',
              {'exit': stopped_code, 'code': incomplete_stop.get('code')})
        (state / 'REVOKED-held').rename(state / 'REVOKED')
        (catalog / 'payload/data.txt').rename(catalog / 'payload/data-held.txt')
        missing_code, missing_dependency = cli(BUILDER, *template_args)
        check('missing catalog dependency rejects before build',
              missing_code == 2 and missing_dependency.get('code') == 'regular_file_unavailable',
              {'exit': missing_code, 'code': missing_dependency.get('code')})
        (catalog / 'payload/data-held.txt').rename(catalog / 'payload/data.txt')
        template_code, template = cli(BUILDER, *template_args)
        if template_code:
            raise RuntimeError('build template failed: ' + str(template))
        authority = {'kind': 'native-setup-build-authority-v1',
                     'scope_amendment': signed(template['scope_amendment'], key, signers, fingerprint),
                     'approval': signed(template['approval'], key, signers, fingerprint)}
        approval_path = base / 'build-authority.json'
        approval_path.write_text(json.dumps(authority, sort_keys=True) + '\n')
        marker = controls / 'setup-build/journal.json'
        invalid = json.loads(approval_path.read_text())
        invalid['approval']['network_class'] = 'target-network'
        invalid_path = base / 'invalid-build-authority.json'
        invalid_path.write_text(json.dumps(invalid, sort_keys=True) + '\n')
        reject_code, rejected = cli(BUILDER, 'setup-build', '--run-root', str(run_root),
                                    '--approval', str(invalid_path), '--dependency-catalog', str(catalog))
        check('changed build authority rejects before dispatch', reject_code == 2 and not marker.exists(),
              {'exit': reject_code, 'code': rejected.get('code')})
        original = run_root / 'original/main.txt'
        original.write_text('tampered\n')
        change_code, changed = cli(BUILDER, 'setup-build', '--run-root', str(run_root),
                                   '--approval', str(approval_path), '--dependency-catalog', str(catalog))
        check('changed source rejects before dispatch', change_code == 2 and not marker.exists(),
              {'exit': change_code, 'code': changed.get('code')})
        original.write_text('hello from source\n')
        original_build = run_root / 'original/build.sh'
        original_build.chmod(0o700)
        changed_mode_code, changed_mode = cli(BUILDER, 'setup-build', '--run-root', str(run_root),
                                              '--approval', str(approval_path),
                                              '--dependency-catalog', str(catalog))
        check('source mode changed after signing rejects before dispatch',
              changed_mode_code == 2 and not marker.exists(),
              {'exit': changed_mode_code, 'code': changed_mode.get('code')})
        original_build.chmod(0o600)
        build_code, built = cli(BUILDER, 'setup-build', '--run-root', str(run_root),
                                '--approval', str(approval_path), '--dependency-catalog', str(catalog),
                                timeout=120)
        receipt_path = controls / 'setup-checked/receipt.json'
        receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
        check('public offline build reaches checked ready receipt',
              build_code == 0 and receipt.get('kind') == 'native-setup-checked-v1'
              and receipt.get('status') == 'ready'
              and receipt.get('cumulative_build_duration_charged_upper_bound_seconds') == 30,
              {'exit': build_code, 'result': built})
        output_file = controls / 'setup-checked/output/out/result.txt'
        check('output and dependency bytes are saved and pinned',
              output_file.is_file() and sha(output_file) ==
              receipt.get('outputs', {}).get('out/result.txt', {}).get('sha256')
              and output_file.read_text() == 'hello from source\nhello from dependency\n'
              and (controls / 'setup-checked/dependencies/payload/data.txt').is_file(),
              {'output_sha256': sha(output_file) if output_file.exists() else None})
        checked_dependency = controls / 'setup-checked/dependencies/payload/data.txt'
        check('executable dependency and output retain usable modes',
              checked_dependency.is_file() and output_file.is_file()
              and stat.S_IMODE(checked_dependency.stat().st_mode) == 0o700
              and stat.S_IMODE(output_file.stat().st_mode) == 0o700,
              {'dependency_mode': (oct(stat.S_IMODE(checked_dependency.stat().st_mode))
                                   if checked_dependency.exists() else None),
               'output_mode': (oct(stat.S_IMODE(output_file.stat().st_mode))
                               if output_file.exists() else None)})
        journal = json.loads(marker.read_text())
        actions = [row['action'] for row in journal['events']]
        daemon_id = call('docker', 'info', '--format', '{{.ID}}').stdout.strip()
        check('builder pins Docker daemon and inspects boundary before start',
              journal.get('docker_daemon_id') == daemon_id
              and 'container_inspect_prestart' in actions
              and actions.index('container_create') < actions.index('container_inspect_prestart')
              < actions.index('container_start'),
              {'daemon_pinned': journal.get('docker_daemon_id') == daemon_id,
               'actions': actions[:4]})
        check('mounted source and dependencies are read back before build',
              'target_build' in actions and all(
                  name in actions and actions.index(name) < actions.index('target_build')
                  for name in ('source_readback', 'dependency_readback')),
              {'actions': actions})
        status_code, status = cli(BUILDER, 'setup-build-status', '--run-root', str(run_root))
        check('status reports completed cleanup', status_code == 0 and
              status.get('status') == 'ready' and status.get('cleanup', {}).get('status') == 'complete',
              {'exit': status_code, 'status': status.get('status')})
        verified_code, verified = cli(BUILDER, 'setup-build-status', '--run-root',
                                      str(run_root), '--verify-checked')
        check('public readback verifies archived checked package',
              verified_code == 0 and verified.get('receipt', {}).get('status') == 'ready'
              and verified.get('output_dir') == str(controls / 'setup-checked/output'),
              {'exit': verified_code, 'code': verified.get('code')})
        for label, path in (('dependency', checked_dependency), ('output', output_file)):
            if not path.exists():
                check(label + ' mode drift invalidates checked package', False, {'file': 'missing'})
                continue
            previous_mode = stat.S_IMODE(path.stat().st_mode)
            path.chmod(0o600 if previous_mode & 0o100 else 0o700)
            drift_code, drift = cli(BUILDER, 'setup-build-status', '--run-root', str(run_root),
                                    '--verify-checked')
            check(label + ' mode drift invalidates checked package', drift_code == 2,
                  {'exit': drift_code, 'code': drift.get('code')})
            path.chmod(previous_mode)
        original_build = run_root / 'original/build.sh'
        original_mode = stat.S_IMODE(original_build.stat().st_mode)
        original_build.chmod(0o700 if original_mode != 0o700 else 0o600)
        source_mode_code, source_mode_result = cli(BUILDER, 'setup-build-status',
            '--run-root', str(run_root), '--verify-checked')
        check('original source mode drift invalidates checked package', source_mode_code == 2,
              {'exit': source_mode_code, 'code': source_mode_result.get('code')})
        original_build.chmod(original_mode)
        retry_code, retry = cli(BUILDER, 'setup-build', '--run-root', str(run_root),
                                '--approval', str(approval_path), '--dependency-catalog', str(catalog))
        check('a dispatched build is never automatically retried', retry_code == 2,
              {'exit': retry_code, 'code': retry.get('code')})
        adopt_root = base / 'checked-adoption-run'
        shutil.copytree(run_root, adopt_root)
        shutil.rmtree(adopt_root / 'controls/setup-build')
        shutil.rmtree(adopt_root / 'controls/setup-checked')
        interrupted = crash_after_checked_rename(adopt_root, approval_path, catalog)
        adopt_controls = adopt_root / 'controls'
        adopt_journal_path = adopt_controls / 'setup-build/journal.json'
        adopt_receipt_path = adopt_controls / 'setup-checked/receipt.json'
        interrupted_journal = json.loads(adopt_journal_path.read_text()) if adopt_journal_path.exists() else {}
        interrupted_receipt = json.loads(adopt_receipt_path.read_text()) if adopt_receipt_path.exists() else {}
        receipt_before = sha(adopt_receipt_path) if adopt_receipt_path.exists() else None
        events_before = interrupted_journal.get('events')
        check('injected exit lands after checked rename before ready journal',
              interrupted.returncode == 73 and receipt_before is not None
              and interrupted_journal.get('status') == 'pending'
              and interrupted_journal.get('pending_action') is None
              and interrupted_journal.get('cleanup') is None
              and interrupted_receipt.get('cleanup', {}).get('status') == 'complete'
              and isinstance(events_before, list) and events_before
              and all(row.get('status') == 'acknowledged' for row in events_before),
              {'exit': interrupted.returncode, 'journal_status': interrupted_journal.get('status'),
               'checked_receipt_sha256': receipt_before,
               'stderr': interrupted.stderr[:500], 'stdout': interrupted.stdout[:500]})
        pre_code, pre_result = cli(BUILDER, 'setup-build-status', '--run-root',
                                   str(adopt_root), '--verify-checked')
        check('uncommitted checked package is not verified ready', pre_code == 2,
              {'exit': pre_code, 'code': pre_result.get('code')})
        no_repeat_code, no_repeat = cli(BUILDER, 'setup-build', '--run-root', str(adopt_root),
                                        '--approval', str(approval_path),
                                        '--dependency-catalog', str(catalog))
        check('visible checked package blocks a repeated build', no_repeat_code == 2
              and no_repeat.get('code') == 'build_already_dispatched',
              {'exit': no_repeat_code, 'code': no_repeat.get('code')})
        symlink_root = base / 'checked-adoption-dangling-symlink'
        shutil.copytree(adopt_root, symlink_root)
        symlink_checked = symlink_root / 'controls/setup-checked'
        shutil.rmtree(symlink_checked)
        symlink_checked.symlink_to(base / 'missing-checked-package')
        symlink_code, symlink_result = cli(BUILDER, 'setup-build', '--run-root',
            str(symlink_root), '--approval', str(approval_path),
            '--dependency-catalog', str(catalog))
        check('dangling checked path blocks a repeated build', symlink_code == 2
              and symlink_result.get('code') == 'build_already_dispatched'
              and symlink_checked.is_symlink(),
              {'exit': symlink_code, 'code': symlink_result.get('code')})
        for failure in ('changed_receipt', 'uncertain_journal', 'failed_acknowledgement',
                        'wrong_daemon', 'daemon_unavailable', 'missing_native_stop',
                        'resource_present'):
            rejected_root = base / ('checked-adoption-' + failure)
            shutil.copytree(adopt_root, rejected_root)
            rejected_controls = rejected_root / 'controls'
            rejected_journal_path = rejected_controls / 'setup-build/journal.json'
            if failure == 'changed_receipt':
                changed = json.loads((rejected_controls / 'setup-checked/receipt.json').read_text())
                changed['security_result'] = 'forged'
                (rejected_controls / 'setup-checked/receipt.json').write_text(
                    json.dumps(changed, sort_keys=True) + '\n')
            elif failure == 'uncertain_journal':
                changed = json.loads(rejected_journal_path.read_text())
                changed['events'][-1]['status'] = 'unknown_effect'
                changed['status'] = 'unknown_effect'
                rejected_journal_path.write_text(json.dumps(changed, sort_keys=True) + '\n')
            elif failure == 'failed_acknowledgement':
                changed = json.loads(rejected_journal_path.read_text())
                changed['events'][-1]['exit_code'] = 1
                rejected_journal_path.write_text(json.dumps(changed, sort_keys=True) + '\n')
            elif failure == 'wrong_daemon':
                changed = json.loads(rejected_journal_path.read_text())
                changed['docker_daemon_id'] = 'different-daemon'
                rejected_journal_path.write_text(json.dumps(changed, sort_keys=True) + '\n')
            elif failure == 'missing_native_stop':
                (rejected_controls / 'native-state/REVOKED').rename(
                    rejected_controls / 'native-state/REVOKED-held')
            elif failure == 'resource_present':
                candidate = json.loads(rejected_journal_path.read_text())
                created = call('docker', 'container', 'create', '--name', candidate['container_name'],
                               '--label', 'io.llm-redteam-harness.setup-build=' + candidate['nonce'],
                               '--network', 'none', '--pull', 'never', image_id,
                               'sh', '-c', 'true')
                if created.returncode:
                    raise RuntimeError('adoption resource fixture creation failed: ' + created.stderr)
                atexit.register(call, 'docker', 'container', 'rm', '-f', candidate['container_name'])
            try:
                environment = None
                if failure == 'daemon_unavailable':
                    environment = dict(os.environ)
                    environment.pop('DOCKER_CONTEXT', None)
                    environment['DOCKER_HOST'] = 'unix://' + str(base / 'missing-docker.sock')
                rejected_code, rejected = cli(BUILDER, 'setup-build-reconcile',
                                              '--run-root', str(rejected_root), env=environment)
                resource_survived = (failure != 'resource_present' or
                    call('docker', 'container', 'inspect', candidate['container_name']).returncode == 0)
            finally:
                if failure == 'resource_present':
                    removed = call('docker', 'container', 'rm', '-f', candidate['container_name'])
                    if removed.returncode:
                        raise RuntimeError('adoption resource fixture cleanup failed: ' + removed.stderr)
            after = json.loads(rejected_journal_path.read_text())
            held = rejected_code == 2 and after.get('status') != 'ready' and resource_survived
            check('checked adoption holds ' + failure, held,
                  {'exit': rejected_code, 'status': rejected.get('status'),
                   'code': rejected.get('code'), 'journal_status': after.get('status')})
        adopted_code, adopted = cli(BUILDER, 'setup-build-reconcile',
                                    '--run-root', str(adopt_root))
        adopted_journal = json.loads(adopt_journal_path.read_text())
        check('reconcile adopts exact checked package without a second build',
              adopted_code == 0 and adopted.get('status') == 'ready'
              and adopted_journal.get('status') == 'ready'
              and adopted_journal.get('events') == events_before
              and sha(adopt_receipt_path) == receipt_before,
              {'exit': adopted_code, 'status': adopted.get('status'),
               'journal_status': adopted_journal.get('status')})
        adopted_verify_code, adopted_verify = cli(BUILDER, 'setup-build-status',
            '--run-root', str(adopt_root), '--verify-checked')
        check('adopted package passes public readback', adopted_verify_code == 0
              and adopted_verify.get('receipt', {}).get('status') == 'ready',
              {'exit': adopted_verify_code, 'code': adopted_verify.get('code')})
        crash_root = base / 'crash-run'
        shutil.copytree(run_root, crash_root)
        shutil.rmtree(crash_root / 'controls/setup-build')
        shutil.rmtree(crash_root / 'controls/setup-checked')
        crash_controls = crash_root / 'controls'
        crash_journal = crash_controls / 'setup-build'
        crash_journal.mkdir(mode=0o700)
        shutil.copy2(approval_path, crash_journal / 'authority.json')
        pending_action = {'action': 'container_create', 'status': 'pending',
                          'argv_sha256': '0' * 64}
        crash_nonce = uuid.uuid4().hex
        crash_name = 'lrh-setup-build-' + crash_nonce[:20]
        (crash_journal / 'journal.json').write_text(json.dumps({
            'kind': 'native-setup-build-journal-v1', 'status': 'pending',
            'nonce': crash_nonce, 'container_name': crash_name,
            'container_id': None, 'authority_sha256': sha(crash_journal / 'authority.json'),
            'docker_daemon_id': daemon_id[:-1] + ('a' if daemon_id[-1] != 'a' else 'b'),
            'catalog_tree_sha256': template['scope_amendment']['dependency_catalog_tree_sha256'],
            'events': [pending_action], 'pending_action': 'container_create',
            'cleanup': None}, sort_keys=True) + '\n')
        created_crash = call('docker', 'container', 'create', '--name', crash_name,
                             '--label', 'io.llm-redteam-harness.setup-build=' + crash_nonce,
                             '--network', 'none', '--pull', 'never', image_id, 'sh', '-c', 'true')
        if created_crash.returncode:
            raise RuntimeError('crash fixture container creation failed: ' + created_crash.stderr)
        atexit.register(call, 'docker', 'container', 'rm', '-f', crash_name)
        crash_state = json.loads((crash_journal / 'journal.json').read_text())
        crash_state['container_id'] = created_crash.stdout.strip()
        (crash_journal / 'journal.json').write_text(json.dumps(crash_state, sort_keys=True) + '\n')
        stopped_code, stopped = cli(BUILDER, 'setup-build', '--run-root', str(crash_root),
                                    '--approval', str(approval_path),
                                    '--dependency-catalog', str(catalog))
        check('crashed pending build cannot be automatically repeated', stopped_code == 2,
              {'exit': stopped_code, 'code': stopped.get('code')})
        wrong_daemon_code, wrong_daemon = cli(BUILDER, 'setup-build-reconcile',
                                              '--run-root', str(crash_root))
        check('wrong Docker daemon cannot settle cleanup',
              wrong_daemon_code == 2 and wrong_daemon.get('status') == 'cleanup_unresolved'
              and call('docker', 'container', 'inspect', crash_name).returncode == 0
              and not (crash_journal / 'reconciliation.json').exists(),
              {'exit': wrong_daemon_code, 'result': wrong_daemon})
        crash_state = json.loads((crash_journal / 'journal.json').read_text())
        crash_state['docker_daemon_id'] = daemon_id
        (crash_journal / 'journal.json').write_text(json.dumps(crash_state, sort_keys=True) + '\n')
        reconciled_code, reconciled = cli(BUILDER, 'setup-build-reconcile',
                                          '--run-root', str(crash_root))
        check('crashed pending action gets exact blocked cleanup readback',
              reconciled_code == 0 and reconciled.get('status') == 'blocked_reconciled'
              and reconciled.get('pending_action') == 'container_create'
              and reconciled.get('cleanup', {}).get('status') == 'complete'
              and call('docker', 'container', 'inspect', crash_name).returncode != 0
              and reconciled.get('retry_requires_new_approval') is True,
              {'exit': reconciled_code, 'result': reconciled})
        old_retry_code, old_retry = cli(BUILDER, 'setup-build', '--run-root', str(crash_root),
                                        '--approval', str(approval_path),
                                        '--dependency-catalog', str(catalog))
        check('old build approval cannot retry reconciled effect', old_retry_code == 2,
              {'exit': old_retry_code, 'code': old_retry.get('code')})
        retry_template_args = list(template_args)
        retry_template_args[retry_template_args.index('--run-root') + 1] = str(crash_root)
        retry_template_code, retry_template = cli(BUILDER, *retry_template_args)
        check('fresh approval template binds prior uncertain spend',
              retry_template_code == 0
              and retry_template.get('scope_amendment', {}).get(
                  'cumulative_build_duration_charged_upper_bound_seconds') == 30
              and retry_template.get('scope_amendment', {}).get('prior_build_attempts') ==
                  [sha(crash_journal / 'reconciliation.json')],
              {'exit': retry_template_code, 'result': retry_template})
        if retry_template_code == 0:
            retry_authority = {'kind': 'native-setup-build-authority-v1',
                'scope_amendment': signed(retry_template['scope_amendment'], key, signers, fingerprint),
                'approval': signed(retry_template['approval'], key, signers, fingerprint)}
            retry_approval = base / 'retry-build-authority.json'
            retry_approval.write_text(json.dumps(retry_authority, sort_keys=True) + '\n')
            retry_code, retry_result = cli(BUILDER, 'setup-build', '--run-root', str(crash_root),
                                           '--approval', str(retry_approval),
                                           '--dependency-catalog', str(catalog), timeout=120)
            retry_receipt_path = crash_controls / 'setup-checked/receipt.json'
            retry_receipt = json.loads(retry_receipt_path.read_text()) if retry_receipt_path.exists() else {}
            archived = list((crash_controls / 'setup-build-attempts').glob('*/reconciliation.json'))
            check('fresh signed retry reaches checked package with prior attempt archived',
                  retry_code == 0 and retry_receipt.get('status') == 'ready'
                  and retry_receipt.get('cumulative_build_duration_charged_upper_bound_seconds') == 60
                  and len(archived) == 1 and sha(archived[0]) ==
                  retry_template['scope_amendment']['prior_build_attempts'][0],
                  {'exit': retry_code, 'result': retry_result, 'archived': len(archived)})
            retry_verify_code, retry_verified = cli(BUILDER, 'setup-build-status',
                '--run-root', str(crash_root), '--verify-checked')
            check('retried checked package passes public readback',
                  retry_verify_code == 0 and retry_verified.get('receipt', {}).get('status') == 'ready',
                  {'exit': retry_verify_code, 'code': retry_verified.get('code')})
        linked_template_args = list(template_args)
        linked_template_args[linked_template_args.index('--run-root') + 1] = str(linked_root)
        linked_template_code, linked_template = cli(BUILDER, *linked_template_args)
        check('linked setup chain permits a separately signed build template',
              linked_template_code == 0, {'exit': linked_template_code,
                                          'code': linked_template.get('code')})
        if linked_template_code == 0:
            linked_authority = {'kind': 'native-setup-build-authority-v1',
                'scope_amendment': signed(linked_template['scope_amendment'], key, signers, fingerprint),
                'approval': signed(linked_template['approval'], key, signers, fingerprint)}
            linked_authority_path = base / 'linked-build-authority.json'
            linked_authority_path.write_text(json.dumps(linked_authority, sort_keys=True) + '\n')
            linked_code, linked_build = cli(BUILDER, 'setup-build', '--run-root', str(linked_root),
                                          '--approval', str(linked_authority_path),
                                          '--dependency-catalog', str(catalog), timeout=120)
            linked_receipt_path = linked_controls / 'setup-checked/receipt.json'
            linked_receipt = json.loads(linked_receipt_path.read_text()) if linked_receipt_path.exists() else {}
            check('linked setup chain produces checked offline build',
                  linked_code == 0 and linked_receipt.get('status') == 'ready'
                  and linked_receipt.get('setup_chain_sha256') ==
                  linked_template['scope_amendment']['setup_chain_sha256'],
                  {'exit': linked_code, 'result': linked_build})
            linked_verified_code, linked_verified = cli(BUILDER, 'setup-build-status',
                                                        '--run-root', str(linked_root),
                                                        '--verify-checked')
            check('linked checked package passes public readback',
                  linked_verified_code == 0 and linked_verified.get('receipt', {}).get('status') == 'ready',
                  {'exit': linked_verified_code, 'code': linked_verified.get('code')})
        if args.emit_research_scope_fixtures:
            research_scopes = base / 'research-scopes'
            research_scopes.mkdir(mode=0o700)
            boundary = {
                'kind': 'native-research-scope-v1', 'engagement_id': 'fixture-202',
                'operator_id': 'synthetic-operator', 'source_manifest_sha256': manifest_hash,
                'goal_sha256': sha(goal), 'surfaces': ['owned harmless source copy'],
                'benign_objectives': ['assess a concrete unsafe effect with a control'],
                'escalation_ceiling': 'source_only_research',
                'impact_demo_authorized': False, 'accounts': [],
                'cleanup': 'Stop and remove all owned research resources.',
                'effect_class': 'checked-offline-source-research',
                'network_class': 'metered-model-relay-only',
                'limits': {'max_connections': 2, 'max_bytes': 1048576,
                           'duration_seconds': 120},
                'expires_at': stamp(now + timedelta(hours=1))}
            variants = {
                'valid': boundary,
                'expired': dict(boundary, expires_at=stamp(now - timedelta(hours=1))),
                'wrong-engagement': dict(boundary, engagement_id='other-fixture'),
                'broad-effect': dict(boundary, effect_class='networked-target-research'),
                'wrong-source': dict(boundary, source_manifest_sha256='0' * 64),
                'wrong-goal': dict(boundary, goal_sha256='0' * 64),
                'wrong-limits': dict(boundary, limits={**boundary['limits'], 'max_bytes': 1048577}),
            }
            for name, value in variants.items():
                scope_path = research_scopes / (name + '.md')
                scope_path.write_text('# Synthetic checked research scope\n\n'
                    '- Operator allowed signers SHA256: sha256:' + sha(signers) + '\n\n'
                    '```native-research-scope-v1\n' + json.dumps(value, sort_keys=True) + '\n```\n')
                challenge = canonical_json_bytes({
                    'kind': 'native-research-scope-challenge-v1',
                    'engagement_id': 'fixture-202', 'scope_sha256': sha(scope_path)})
                (research_scopes / (name + '.sig')).write_bytes(subprocess.run(
                    ['ssh-keygen', '-Y', 'sign', '-f', str(key), '-n',
                     'llm-redteam-harness-native-research-v1'], input=challenge,
                    capture_output=True, check=True, timeout=10).stdout)
        key.unlink()
        inputs = {'source_manifest_sha256': manifest_hash,
                  'scope_sha256': sha(scope), 'setup_approval_sha256': sha(controls / 'approval.json'),
                  'frozen_setup_receipt_sha256': sha(frozen / 'receipt.json'),
                  'build_authority_sha256': sha(approval_path),
                  'catalog_manifest_sha256': sha(catalog / 'catalog.json'), 'image_id': image_id,
                  'builder_sha256': sha(BUILDER), 'scenario_sha256': sha(Path(__file__))}
        artifacts = {'journal_sha256': sha(marker) if marker.exists() else None,
                     'checked_receipt_sha256': sha(receipt_path) if receipt_path.exists() else None,
                     'adopted_journal_sha256': sha(adopt_journal_path),
                     'adopted_receipt_sha256': sha(adopt_receipt_path)}
    result = {'kind': 'native-setup-builder-synthetic-e2e-v1', 'inputs': inputs,
              'artifacts': artifacts, 'checks': checks,
              'passed': all(row['passed'] for row in checks),
              'fixture_roots': ({'v1': str(args.keep_root / 'run'),
                                 'v2': str(args.keep_root / 'linked-run')}
                                if args.keep_root else None),
              'provider_executed': False, 'target_service_executed': False,
              'classification': 'synthetic setup turn, stop, and pending host crash; real local offline Docker build',
              'limits': 'No real host kill, native model turn, provider qualification, engagement, or research run.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + '\n')
    print(json.dumps({'passed': result['passed'], 'result': str(args.output)}, sort_keys=True))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
