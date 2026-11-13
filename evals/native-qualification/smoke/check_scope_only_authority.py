#!/usr/bin/env python3
"""Provider-free signed-scope authority path for setup and research."""

import argparse
import base64
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
from types import SimpleNamespace
from unittest.mock import patch

from check_native_setup_e2e import RELAY, ROOT, cli, run, sha

sys.path.insert(0, str(ROOT / 'tools'))
from engagement_records import canonical_json_bytes  # noqa: E402
import native_research as runner  # noqa: E402
import native_setup_builder as builder  # noqa: E402

NAMESPACE = 'llm-redteam-harness-native-engagement-v1'
CHALLENGE = 'native-engagement-scope-challenge-v1'


def signed_scope(path, boundary, key, signers):
    path.write_text('# Synthetic full engagement scope\n\n'
                    '- Operator allowed signers SHA256: sha256:' + sha(signers) + '\n'
                    '- Signed: [x] synthetic operator\n\n'
                    '```native-engagement-scope-v1\n'
                    + json.dumps(boundary, sort_keys=True) + '\n```\n')
    signature = path.with_suffix('.sig')
    challenge = canonical_json_bytes({'kind': CHALLENGE,
                                      'engagement_id': boundary['engagement_id'],
                                      'scope_sha256': sha(path)})
    signature.write_bytes(subprocess.run(
        ['ssh-keygen', '-Y', 'sign', '-f', str(key), '-n', NAMESPACE],
        input=challenge, capture_output=True, check=True, timeout=10).stdout)
    return signature


def fixture(base: Path) -> dict:
    """One initial signed scope and a public provider-free prepared setup root."""
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    source = base / 'source'
    source.mkdir(mode=0o700)
    (source / 'main.py').write_text('print("fixture ready")\n')
    brief = base / 'goal.md'
    brief.write_text('Inspect the harmless source and form a testable threat model.\n')
    key = base / 'operator_key'
    subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)],
                   check=True, timeout=10)
    signers = base / 'allowed_signers'
    signers.write_text('synthetic-operator ' + key.with_suffix('.pub').read_text())
    encoded = run('ssh-keygen', '-lf', str(key.with_suffix('.pub')),
                  '-E', 'sha256').stdout.split('SHA256:')[1].split()[0]
    fingerprint = 'sha256:' + base64.b64decode(encoded + '=' * (-len(encoded) % 4)).hex()
    relay = base / 'relay'
    shutil.copy2(RELAY, relay)
    relay.chmod(0o700)
    ca, ca_key = base / 'ca.pem', base / 'ca.key'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-noenc',
                    '-days', '1', '-subj', '/CN=scope only fixture',
                    '-keyout', str(ca_key), '-out', str(ca)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    ca_key.unlink()
    catalog = base / 'catalog'
    (catalog / 'payload').mkdir(parents=True, mode=0o700)
    dependency = catalog / 'payload/data.txt'
    dependency.write_text('offline fixture data\n')
    dependency.chmod(0o600)
    (catalog / 'catalog.json').write_text(json.dumps({
        'kind': builder.CATALOG_KIND, 'entries': [{
            'id': 'data.txt', 'path': 'payload/data.txt',
            'sha256': sha(dependency), 'mode': 0o600}]}, sort_keys=True) + '\n')
    catalog_tree = builder.catalog_snapshot(catalog, {
        'offline_dependencies': ['data.txt']})['tree']['tree_sha256']
    source_manifest = hashlib.sha256(json.dumps(
        {'main.py': sha(source / 'main.py')}, sort_keys=True).encode()).hexdigest()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    scope = base / 'scope.md'
    boundary = {
        'kind': 'native-engagement-scope-v1', 'engagement_id': 'scope-only-fixture',
        'operator_id': 'synthetic-operator',
        'source_manifest_sha256': source_manifest, 'goal_sha256': sha(brief),
        'surfaces': ['owned original source tree'],
        'benign_objectives': ['source-only analysis and bounded offline checks'],
        'escalation_ceiling': 'source_only_research',
        'impact_demo_authorized': False, 'accounts': [],
        'cleanup': 'Stop and remove every owned container and network.',
        'model': runner.MODEL, 'provider_route': runner.PROVIDER_ROUTE,
        'image_id': 'sha256:' + '1' * 64, 'platform': 'linux/amd64',
        'relay_sha256': sha(relay), 'runtime_ca_sha256': sha(ca),
        'limits': {'max_connections': 5, 'max_bytes': 2097152,
                   'duration_seconds': 3600},
        'setup': {
            'effect_class': runner.SETUP_EFFECT_CLASS,
            'network_class': runner.SETUP_NETWORK_CLASS,
            'limits': {'max_connections': 2, 'max_bytes': 1048576,
                       'duration_seconds': 120},
            'max_workspace_bytes': 67108864},
        'build': {
            'effect_class': builder.EFFECT_CLASS,
            'network_class': builder.NETWORK_CLASS,
            'image_id': 'sha256:' + '2' * 64,
            'dependency_catalog_tree_sha256': catalog_tree,
            'max_workspace_bytes': 67108864,
            'memory_bytes': 268435456, 'duration_seconds': 120,
            'max_output_paths': 64, 'max_attempts': 1},
        'research': {'effect_class': 'checked-offline-source-research',
                     'network_class': 'metered-model-relay-only'},
        'issued_at': now.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'expires_at': (now + timedelta(minutes=30)).strftime('%Y-%m-%dT%H:%M:%SZ')}
    signature = signed_scope(scope, boundary, key, signers)
    marker = base / 'docker-called'
    shim = base / 'bin/docker'
    shim.parent.mkdir()
    shim.write_text('#!/bin/sh\nprintf called > "' + str(marker) + '"\nexit 90\n')
    shim.chmod(0o700)
    env = dict(os.environ, PATH=str(shim.parent) + os.pathsep + os.environ.get('PATH', ''),
               PYTHONDONTWRITEBYTECODE='1')
    root = base / 'run'
    prepare = ('prepare', '--setup-only', '--run-root', str(root), '--source', str(source),
               '--brief', str(brief), '--scope-file', str(scope), '--scope-sha256', sha(scope),
               '--setup-scope-signature', str(signature), '--setup-allowed-signers', str(signers),
               '--setup-trusted-fingerprint', fingerprint,
               '--setup-operator-id', boundary['operator_id'],
               '--setup-engagement-id', boundary['engagement_id'],
               '--relay', str(relay), '--relay-sha256', sha(relay),
               '--runtime-ca', str(ca), '--runtime-ca-sha256', sha(ca),
               '--image-id', boundary['image_id'], '--platform', boundary['platform'],
               '--max-connections', '2', '--max-bytes', '1048576',
               '--duration-seconds', '120', '--setup-max-workspace-bytes', '67108864')
    code, result = cli(env, *prepare)
    return {'base': base, 'source': source, 'brief': brief, 'key': key,
            'signers': signers, 'fingerprint': fingerprint, 'relay': relay,
            'ca': ca, 'catalog': catalog, 'catalog_tree_sha256': catalog_tree,
            'scope': scope, 'signature': signature, 'boundary': boundary,
            'root': root, 'prepare_args': prepare, 'prepare_code': code,
            'prepare_result': result, 'env': env, 'docker_marker': marker}


def main() -> int:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    checks = []
    with tempfile.TemporaryDirectory(prefix='scope-only-authority-') as raw:
        item = fixture(Path(raw).resolve())
        def check(name, passed, observed):
            checks.append({'name': name, 'passed': bool(passed), 'observed': observed})
        check('initial signed scope prepares without a later approval',
              item['prepare_code'] == 0 and item['root'].joinpath('plan.json').is_file(),
              {'exit': item['prepare_code'], 'result': item['prepare_result']})
        if item['prepare_code'] == 0:
            root, env = item['root'], item['env']
            plan = json.loads((root / 'plan.json').read_text())
            check('host plan marks full-engagement scope',
                  plan.get('autonomous_engagement', {}).get('kind') == 'native-engagement-scope-v1',
                  {'marker': plan.get('autonomous_engagement')})
            held = root / 'controls/scope-held.md'
            (root / 'controls/scope.md').rename(held)
            code, result = cli(env, 'start', '--run-root', str(root))
            check('missing archived scope refuses before Docker',
                  code == 2 and not item['docker_marker'].exists(),
                  {'exit': code, 'code': result.get('code')})
            held.rename(root / 'controls/scope.md')
            item['key'].unlink()
            code, result = cli(env, 'start', '--run-root', str(root))
            approval = root / 'controls/approval.json'
            derived = json.loads(approval.read_text()) if approval.exists() else {}
            check('setup start derives bounded host authority without operator key',
                  code == 2 and item['docker_marker'].exists()
                  and derived.get('kind') == 'native-scope-derived-approval-v1'
                  and derived.get('phase') == 'setup'
                  and derived.get('plan_sha256') == sha(root / 'plan.json')
                  and derived.get('limits') == item['boundary']['setup']['limits'],
                  {'exit': code, 'code': result.get('code'), 'authority': derived.get('kind')})
            provider = root / 'controls/provider/tunnel.sqlite3'
            provider.parent.mkdir(exist_ok=True)
            ids = ['a' * 64, 'b' * 64]
            manifest = root / 'controls/producer-manifest.json'
            manifest.write_text(json.dumps({'producers': [{'id': value} for value in ids]}) + '\n')
            manifest_sha = sha(manifest)
            duration = plan['limits']['duration_seconds'] - 10
            config = {'authority': runner.AUTHORITY, 'producer_manifest_sha256': manifest_sha,
                      'max_connections': plan['limits']['max_connections'],
                      'max_bytes': plan['limits']['max_bytes'],
                      'native_run_duration': duration, 'duration': duration}
            with sqlite3.connect(provider) as db:
                db.execute('CREATE TABLE pool(config TEXT, created REAL, bytes INTEGER)')
                db.execute('CREATE TABLE tunnels(phase TEXT, uploaded INTEGER, downloaded INTEGER)')
                db.execute('INSERT INTO pool VALUES(?,?,?)',
                           (json.dumps(config), datetime.now(timezone.utc).timestamp(), 0))
            identity = {'manifest_sha256': manifest_sha, 'nonce': 'synthetic', 'ids': ids,
                        'deadline_monotonic': 100, 'created_monotonic': 0}
            native = SimpleNamespace(snapshot=lambda _state: identity,
                                     active=lambda _state: True)
            with patch.object(runner, '_activate_controls', return_value=(native, None)):
                try:
                    snapshot = runner.allowance_snapshot(root)
                    shortened = snapshot['hard_limits']['duration_seconds'] == duration
                except runner.NativeResearchError:
                    shortened = False
            check('scope-derived activation accepts a bounded shortened duration', shortened,
                  {'planned': plan['limits']['duration_seconds'], 'actual': duration})
            state = root / 'controls/native-state'
            state.mkdir(exist_ok=True)
            (state / 'RUN.json').write_text(json.dumps({'ids': ids,
                                                       'manifest_sha256': manifest_sha}) + '\n')
            revoked = state / 'REVOKED'
            revoked.write_text(json.dumps({'ids': ids, 'manifest_sha256': manifest_sha,
                                           'producers_verified_stopped': True}) + '\n')
            resources = [{'kind': 'container', 'name': 'synthetic-' + str(i), 'id': value}
                         for i, value in enumerate(ids)]
            resources.append({'kind': 'network', 'name': 'synthetic-network', 'id': 'c' * 64})
            (root / 'controls/resources.json').write_text(json.dumps({'resources': resources}) + '\n')
            cleanup = {'resources': [{'kind': row['kind'], 'name': row['name']}
                                     for row in resources]}
            snapshot = {'native_stop': {'manifest_sha256': manifest_sha,
                                        'revoked_sha256': sha(revoked),
                                        'producer_ids_sha256': hashlib.sha256(json.dumps(
                                            ids, separators=(',', ':')).encode()).hexdigest()}}
            receipt = {'pool_after': {'used_tunnels': 0, 'charged_tunnel_bytes': 0,
                                      'provider_deadline_unix':
                                      datetime.now(timezone.utc).timestamp() + duration,
                                      'run_identity': {'manifest_sha256': manifest_sha, 'ids': ids}}}
            with sqlite3.connect(provider) as db:
                created = db.execute('SELECT created FROM pool').fetchone()[0]
            receipt['pool_after']['provider_deadline_unix'] = created + duration
            with patch.object(runner, '_docker', return_value=subprocess.CompletedProcess([], 0, b'', b'')):
                try:
                    builder.verify_v1_stop_provenance(root, plan, snapshot, cleanup, receipt)
                    builder_accepted = True
                except (runner.NativeResearchError, builder.BuildError) as error:
                    builder_accepted = False
                    builder_error = str(error)
            check('scope-derived stopped setup accepts the shortened provider record',
                  builder_accepted, {'actual': duration,
                                     'code': None if builder_accepted else builder_error})
            config['duration'] = config['native_run_duration'] = plan['limits']['duration_seconds'] + 1
            with sqlite3.connect(provider) as db:
                db.execute('UPDATE pool SET config=?', (json.dumps(config),))
            with patch.object(runner, '_activate_controls', return_value=(native, None)):
                try:
                    runner.allowance_snapshot(root)
                    overlong_rejected = False
                except runner.NativeResearchError as error:
                    overlong_rejected = str(error) == 'shared_allowance_identity_mismatch'
            check('scope-derived activation rejects a duration above the plan',
                  overlong_rejected, {'actual': config['duration']})
        delayed = fixture(Path(raw).resolve() / 'delayed')
        if delayed['prepare_code'] == 0:
            deadline = datetime.strptime(delayed['boundary']['expires_at'],
                                         '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
            clock = [datetime.now(timezone.utc).timestamp()]
            reached_native = []
            def delayed_preseal(*_args):
                clock[0] = deadline.timestamp() - 20
                return {}
            def native_constructor(*_args):
                reached_native.append(True)
                raise RuntimeError('native constructor reached after deadline window closed')
            fake_native = SimpleNamespace(NativeRun=native_constructor)
            fake_manifest = delayed['root'] / 'controls/producer-manifest.json'
            fake_manifest.write_text('{}\n')
            with (patch.object(runner.shutil, 'which', return_value=str(delayed['base'] / 'bin/docker')),
                  patch.object(runner.time, 'time', side_effect=lambda: clock[0]),
                  patch.object(runner, '_image'), patch.object(runner, '_save_resources'),
                  patch.object(runner, '_preseal', side_effect=delayed_preseal),
                  patch.object(runner, '_created_manifest', return_value=fake_manifest),
                  patch.object(runner, '_activate_controls', return_value=(fake_native, None)),
                  patch.object(runner, '_origin_stop', return_value={'status': 'not_configured'}),
                  patch.object(runner, '_capture_stop', return_value={'status': 'not_configured'}),
                  patch.object(runner, '_origin_cleanup', return_value={'status': 'not_configured'}),
                  patch.object(runner, '_cleanup_resources', return_value={'status': 'complete'}),
                  patch.object(runner, '_capture_cleanup', return_value={'status': 'not_configured'})):
                try:
                    runner._start_owned(delayed['root'], None)
                    code = 'unexpected_start'
                except (runner.NativeResearchError, RuntimeError) as error:
                    code = str(error)
            check('preseal delay exhausts authority before native activation',
                  code == 'engagement_allowance_exhausted' and not reached_native,
                  {'code': code, 'native_constructor_reached': bool(reached_native)})
        prestop = fixture(Path(raw).resolve() / 'prestop')
        if prestop['prepare_code'] == 0:
            code, result = cli(prestop['env'], 'stop', '--run-root', str(prestop['root']))
            stop_path = prestop['root'] / 'controls/native-state/STOP_REQUEST'
            check('scope-only stop persists before activation',
                  code == 0 and result.get('status') == 'stop_requested'
                  and stop_path.is_file(),
                  {'exit': code, 'status': result.get('status'), 'stop_file': stop_path.is_file()})
            code, result = cli(prestop['env'], 'start', '--run-root', str(prestop['root']))
            check('preactivation stop prevents resource creation',
                  code == 2 and not prestop['docker_marker'].exists()
                  and not (prestop['root'] / 'controls/resources.json').exists(),
                  {'exit': code, 'code': result.get('code')})
        result = {'status': 'passed' if checks and all(row['passed'] for row in checks) else 'failed',
                  'checks': checks, 'provider_calls': 0, 'target_service_calls': 0}
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
        print(json.dumps({'status': result['status'], 'checks': len(checks),
                          'result': str(args.output)}, sort_keys=True))
        return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
