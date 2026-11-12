#!/usr/bin/env python3
"""Public #202 builder scenario with synthetic #208 authority and stop receipts.

Requires a local Docker daemon and an already-local BusyBox 1.37 image. No
provider or target service is contacted. See SETUP-BUILDER-E2E.md.
"""

import argparse
import base64
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile

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


def call(*argv, timeout=60):
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)


def cli(path, *args, timeout=60):
    result = call(sys.executable, str(path), *args, timeout=timeout)
    try:
        payload = json.loads(result.stdout)
    except ValueError:
        payload = {'code': 'non_json_cli_output', 'stderr': result.stderr[:1000]}
    return result.returncode, payload


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
    args = parser.parse_args()
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
        (source / 'build.sh').write_text('mkdir -p out\ncat main.txt /deps/data.txt > out/result.txt\n')
        source_files = {path.relative_to(source).as_posix(): sha(path)
                        for path in sorted(source.rglob('*')) if path.is_file()}
        manifest_hash = hashlib.sha256(json.dumps(source_files, sort_keys=True).encode()).hexdigest()
        goal = base / 'goal.md'
        goal.write_text('Assess this harmless local source for a concrete unsafe effect, '
                        'with a control and clear limits.\n')
        key = base / 'operator_key'
        subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)],
                       check=True, timeout=10)
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
        connection.execute('CREATE TABLE tunnels (phase TEXT)')
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
        (catalog / 'payload/data.txt').write_text('hello from dependency\n')
        (catalog / 'catalog.json').write_text(json.dumps({
            'kind': 'native-setup-dependency-catalog-v1',
            'entries': [{'id': 'data.txt', 'path': 'payload/data.txt',
                         'sha256': sha(catalog / 'payload/data.txt')}]}, sort_keys=True) + '\n')
        template_args = ('setup-build-approval-template', '--run-root', str(run_root),
                         '--image-id', image_id, '--dependency-catalog', str(catalog),
                         '--max-workspace-bytes', '8388608', '--memory-bytes', '67108864',
                         '--duration-seconds', '30', '--output-path', 'out/result.txt',
                         '--approved-at', stamp(now),
                         '--expires-at', stamp(now + timedelta(hours=1)))
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
        build_code, built = cli(BUILDER, 'setup-build', '--run-root', str(run_root),
                                '--approval', str(approval_path), '--dependency-catalog', str(catalog),
                                timeout=120)
        receipt_path = controls / 'setup-checked/receipt.json'
        receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
        check('public offline build reaches checked ready receipt',
              build_code == 0 and receipt.get('kind') == 'native-setup-checked-v1'
              and receipt.get('status') == 'ready',
              {'exit': build_code, 'result': built})
        output_file = controls / 'setup-checked/output/out/result.txt'
        check('output and dependency bytes are saved and pinned',
              output_file.is_file() and sha(output_file) == receipt.get('outputs', {}).get('out/result.txt')
              and output_file.read_text() == 'hello from source\nhello from dependency\n'
              and (controls / 'setup-checked/dependencies/payload/data.txt').is_file(),
              {'output_sha256': sha(output_file) if output_file.exists() else None})
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
        retry_code, retry = cli(BUILDER, 'setup-build', '--run-root', str(run_root),
                                '--approval', str(approval_path), '--dependency-catalog', str(catalog))
        check('a dispatched build is never automatically retried', retry_code == 2,
              {'exit': retry_code, 'code': retry.get('code')})
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
        key.unlink()
        inputs = {'source_manifest_sha256': manifest_hash,
                  'scope_sha256': sha(scope), 'setup_approval_sha256': sha(controls / 'approval.json'),
                  'frozen_setup_receipt_sha256': sha(frozen / 'receipt.json'),
                  'build_authority_sha256': sha(approval_path),
                  'catalog_manifest_sha256': sha(catalog / 'catalog.json'), 'image_id': image_id,
                  'builder_sha256': sha(BUILDER), 'scenario_sha256': sha(Path(__file__))}
        artifacts = {'journal_sha256': sha(marker) if marker.exists() else None,
                     'checked_receipt_sha256': sha(receipt_path) if receipt_path.exists() else None}
    result = {'kind': 'native-setup-builder-synthetic-e2e-v1', 'inputs': inputs,
              'artifacts': artifacts, 'checks': checks,
              'passed': all(row['passed'] for row in checks),
              'fixture_roots': ({'v1': str(args.keep_root / 'run'),
                                 'v2': str(args.keep_root / 'linked-run')}
                                if args.keep_root else None),
              'provider_executed': False, 'target_service_executed': False,
              'classification': 'synthetic setup turn and stop, real local offline Docker build',
              'limits': 'No native model turn, provider qualification, real engagement, or later research run.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + '\n')
    print(json.dumps({'passed': result['passed'], 'result': str(args.output)}, sort_keys=True))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
