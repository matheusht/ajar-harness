#!/usr/bin/env python3
"""Public CLI scenario for a synthetic stopped setup epoch and residual successor.

No model, provider, target, or real NativeRun is started. The terminal receipts,
provider ledger and Docker absence readback are synthetic substitutes.
"""

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
import tempfile

from check_native_setup_e2e import (CLI, NAMESPACE, RELAY, ROOT, canonical_json_bytes,
                                    cli, encode_operator_signature_proof, run, sha, sign)


def write(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + '\n')


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    checks = []

    def check(name, ok, observed):
        checks.append({'name': name, 'passed': bool(ok), 'observed': observed})

    with tempfile.TemporaryDirectory(prefix='setup-epoch-e2e-') as raw:
        base = Path(raw).resolve()
        source = base / 'source'
        (source / 'pkg').mkdir(parents=True)
        (source / 'main.py').write_text('from pkg.message import message\nprint(message())\n')
        (source / 'pkg/__init__.py').write_text('"""Fixture."""\n')
        (source / 'pkg/message.py').write_text('def message():\n    return "fixture ready"\n')
        brief = base / 'goal.md'
        brief.write_text('Inspect this harmless source and propose an offline runtime recipe.\n')
        key = base / 'operator_key'
        subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)],
                       check=True, timeout=10)
        signers = base / 'allowed_signers'
        signers.write_text('synthetic-operator ' + (base / 'operator_key.pub').read_text())
        encoded = run('ssh-keygen', '-lf', str(base / 'operator_key.pub'), '-E', 'sha256').stdout
        encoded = encoded.split('SHA256:')[1].split()[0]
        fingerprint = 'sha256:' + base64.b64decode(encoded + '=' * (-len(encoded) % 4)).hex()
        relay = base / 'relay'
        shutil.copy2(RELAY, relay)
        relay.chmod(0o700)
        ca, ca_key = base / 'ca.pem', base / 'ca.key'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-noenc',
                        '-days', '1', '-subj', '/CN=setup epoch fixture',
                        '-keyout', str(ca_key), '-out', str(ca)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        ca_key.unlink()
        log = base / 'docker-calls'
        present_marker = base / 'resource-present'
        shim = base / 'bin/docker'
        shim.parent.mkdir()
        shim.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "' + str(log) + '"\n'
                        'case "$1 $2" in "container ls"|"network ls") '
                        'if [ -f "' + str(present_marker) + '" ]; then echo present; fi; '
                        'exit 0;; esac\nexit 90\n')
        shim.chmod(0o700)
        env = dict(os.environ, PATH=str(shim.parent) + os.pathsep + os.environ.get('PATH', ''),
                   PYTHONDONTWRITEBYTECODE='1')
        code, manifest = cli(env, 'setup-source-manifest', '--source', str(source))
        if code:
            raise RuntimeError('source manifest failed: ' + str(manifest))
        now = datetime.now(timezone.utc).replace(microsecond=0)
        scope = base / 'scope.md'
        boundary = {'kind': 'native-setup-scope-v1', 'engagement_id': 'fixture-epoch',
                    'operator_id': 'synthetic-operator',
                    'source_manifest_sha256': manifest['source_manifest_sha256'],
                    'goal_sha256': sha(brief), 'surfaces': ['owned original source tree'],
                    'benign_objectives': ['propose offline runtime and threat model'],
                    'escalation_ceiling': 'setup_only', 'impact_demo_authorized': False,
                    'accounts': [], 'cleanup': 'Stop and remove owned setup resources.',
                    'effect_class': 'read-only-original-and-disposable-offline-proposal',
                    'network_class': 'metered-model-relay-only',
                    'expires_at': (now + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%SZ')}
        scope.write_text('# Synthetic setup scope\n\n- Operator allowed signers SHA256: sha256:'
                         + sha(signers) + '\n\n```native-setup-scope-v1\n'
                         + json.dumps(boundary, sort_keys=True) + '\n```\n')
        scope_sig = base / 'scope.sig'
        scope_sig.write_bytes(sign(key, canonical_json_bytes({
            'kind': 'native-setup-scope-challenge-v1',
            'engagement_id': 'fixture-epoch', 'scope_sha256': sha(scope)})))
        first = base / 'run-1'
        prepare = ('prepare', '--setup-only', '--run-root', str(first), '--source', str(source),
                   '--brief', str(brief), '--scope-file', str(scope), '--scope-sha256', sha(scope),
                   '--setup-scope-signature', str(scope_sig), '--setup-allowed-signers', str(signers),
                   '--setup-trusted-fingerprint', fingerprint, '--setup-operator-id', 'synthetic-operator',
                   '--setup-engagement-id', 'fixture-epoch', '--relay', str(relay),
                   '--relay-sha256', sha(relay), '--runtime-ca', str(ca), '--runtime-ca-sha256', sha(ca),
                   '--image-id', 'sha256:' + '1' * 64, '--platform', 'linux/amd64',
                   '--max-connections', '3', '--max-bytes', '1048576', '--duration-seconds', '180')
        code, prepared = cli(env, *prepare)
        if code:
            raise RuntimeError('synthetic prepare failed: ' + str(prepared))
        deadline = (now + timedelta(seconds=180)).strftime('%Y-%m-%dT%H:%M:%SZ')
        code, grant = cli(env, 'setup-approval-template', '--run-root', str(first),
                          '--approved-at', now.strftime('%Y-%m-%dT%H:%M:%SZ'),
                          '--expires-at', (now + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%SZ'),
                          '--linked-epochs', '--absolute-deadline', deadline)
        if code:
            raise RuntimeError('v2 grant template failed: ' + str(grant))
        unsigned = dict(grant)
        proof = encode_operator_signature_proof(
            challenge_bytes=canonical_json_bytes(unsigned),
            signature_bytes=sign(key, canonical_json_bytes(unsigned)),
            allowed_signers_bytes=signers.read_bytes(), signer_fingerprint=fingerprint)
        grant['operator_signature'] = proof
        grant_file = base / 'grant.json'
        write(grant_file, grant)
        expired = dict(unsigned)
        expired['approved_at'] = (now - timedelta(seconds=180)).strftime('%Y-%m-%dT%H:%M:%SZ')
        expired['absolute_deadline'] = (now - timedelta(seconds=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
        expired['operator_signature'] = encode_operator_signature_proof(
            challenge_bytes=canonical_json_bytes(expired),
            signature_bytes=sign(key, canonical_json_bytes(expired)),
            allowed_signers_bytes=signers.read_bytes(), signer_fingerprint=fingerprint)
        expired_file = base / 'expired-grant.json'
        write(expired_file, expired)
        code, expired_result = cli(env, 'start', '--run-root', str(first), '--approval', str(expired_file))
        check('signed expired absolute deadline rejects before Docker',
              code == 2 and expired_result.get('code') == 'setup_epoch_deadline_expired_or_invalid'
              and not log.exists(), {'exit': code, 'code': expired_result.get('code')})
        tampered = dict(grant, expires_at=(now + timedelta(minutes=59)).strftime('%Y-%m-%dT%H:%M:%SZ'))
        tampered_file = base / 'tampered-grant.json'
        write(tampered_file, tampered)
        code, tampered_result = cli(env, 'start', '--run-root', str(first), '--approval', str(tampered_file))
        check('changed v2 grant rejects before Docker',
              code == 2 and tampered_result.get('code') == 'setup_approval_signature_invalid'
              and not log.exists(), {'exit': code, 'code': tampered_result.get('code')})
        code, first_start = cli(env, 'start', '--run-root', str(first), '--approval', str(grant_file))
        check('signed v2 initial grant reaches resource boundary',
              code == 2 and first_start.get('code') == 'docker_command_failed',
              {'exit': code, 'code': first_start.get('code')})

        controls = first / 'controls'
        ids = ['a' * 64, 'b' * 64]
        network_ids = ['c' * 64, 'd' * 64]
        manifest_path = controls / 'producer-manifest.json'
        write(manifest_path, {'producers': [{'id': value} for value in ids]})
        native_state = controls / 'native-state'
        write(native_state / 'RUN.json', {'ids': ids, 'manifest_sha256': sha(manifest_path)})
        revoked = native_state / 'REVOKED'
        write(revoked, {'ids': ids, 'manifest_sha256': sha(manifest_path),
                        'producers_verified_stopped': True})
        resources = ([{'kind': 'container', 'role': role, 'name': role, 'id': identifier}
                      for role, identifier in zip(('relay', 'researcher'), ids)]
                     + [{'kind': 'network', 'role': role, 'name': role, 'id': identifier}
                        for role, identifier in zip(('external', 'research'), network_ids)])
        write(controls / 'resources.json', {'nonce': 'fixture', 'resources': resources})
        cleanup = {'status': 'complete', 'resources': [
            {'kind': item['kind'], 'name': item['name'], 'absent': True} for item in reversed(resources)]}
        write(controls / 'cleanup.json', cleanup)
        write(controls / 'host-snapshot.json', {'status': 'complete',
              'plan_sha256': sha(first / 'plan.json'),
              'native_stop': {'manifest_sha256': sha(manifest_path), 'revoked_sha256': sha(revoked)}})
        write(controls / 'final.json', {'status': 'stopped_complete',
              'native_stop': {'status': 'stopped'},
              'host_snapshot': {'status': 'complete', 'receipt_sha256': sha(controls / 'host-snapshot.json')},
              'cleanup': cleanup})
        provider = controls / 'provider/tunnel.sqlite3'
        provider.parent.mkdir(exist_ok=True)
        with sqlite3.connect(provider) as db:
            db.execute('CREATE TABLE pool(config TEXT,created REAL,bytes INTEGER)')
            db.execute('CREATE TABLE tunnels(id INTEGER PRIMARY KEY,phase TEXT, '
                       'uploaded INTEGER DEFAULT 0, downloaded INTEGER DEFAULT 0)')
            db.execute('INSERT INTO pool VALUES(?,?,?)', (json.dumps({
                'authority': 'opencode.ai:443', 'producer_manifest_sha256': sha(manifest_path),
                'native_run_duration': 170, 'max_connections': 3,
                'max_bytes': 1048576, 'duration': 170}), now.timestamp(), 4096))
            db.execute('INSERT INTO tunnels(phase,uploaded) VALUES(?,?)', ('closed', 4096))
        dispatch_id = 'e' * 32
        trace = controls / 'dispatch' / (dispatch_id + '.trace.json')
        write(trace, {'kind': 'protected-native-event-trace-v1', 'session_id': 'ses_fixture', 'events': []})
        checkpoint = controls / 'setup-checkpoints' / dispatch_id
        checkpoint.mkdir(parents=True)
        (checkpoint / 'THREAT_MODEL.md').write_text('# Harmless source\nInitial boundaries observed.\n')
        write(checkpoint / 'receipt.json', {'kind': 'native-setup-checkpoint-v1',
              'plan_sha256': sha(first / 'plan.json'), 'dispatch_id': dispatch_id,
              'approval_sha256': sha(controls / 'approval.json'), 'pool_after': {'status': 'synthetic'},
              'native_trace_sha256': sha(trace),
              'files': {'recipe.json': None, 'THREAT_MODEL.md': sha(checkpoint / 'THREAT_MODEL.md')}})
        write(controls / 'dispatch' / (dispatch_id + '.json'), {
            'kind': 'native-dispatch-v1', 'role': 'researcher', 'status': 'acknowledged',
            'dispatch_id': dispatch_id, 'setup_sequence': 1, 'session_id': 'ses_fixture',
            'pool_after': {'status': 'synthetic'},
            'native_trace_sha256': sha(trace), 'checkpoint_sha256': sha(checkpoint / 'receipt.json')})

        successor = base / 'run-2'
        next_cmd = ('setup-next-epoch', '--run-root', str(first), '--next-run-root', str(successor))
        code, nested = cli(env, 'setup-next-epoch', '--run-root', str(first),
                           '--next-run-root', str(first / 'nested'))
        check('nested successor root refuses before resource readback',
              code == 2 and nested.get('code') == 'setup_next_root_invalid'
              and not (first / 'nested').exists(),
              {'exit': code, 'code': nested.get('code')})
        revoked.rename(base / 'held-revoked')
        code, missing = cli(env, *next_cmd)
        check('missing verified stop refuses successor', code == 2 and not successor.exists(),
              {'exit': code, 'code': missing.get('code')})
        (base / 'held-revoked').rename(revoked)
        present_marker.write_text('synthetic present\n')
        code, present = cli(env, *next_cmd)
        check('resource still present refuses successor', code == 2 and not successor.exists(),
              {'exit': code, 'code': present.get('code')})
        present_marker.unlink()
        dispatch_file = controls / 'dispatch' / (dispatch_id + '.json')
        dispatch_value = json.loads(dispatch_file.read_text())
        write(dispatch_file, dict(dispatch_value, status='unknown_effect'))
        code, unknown = cli(env, *next_cmd)
        check('unknown setup turn refuses automatic retry', code == 2 and not successor.exists(),
              {'exit': code, 'code': unknown.get('code')})
        write(dispatch_file, dispatch_value)
        threat = checkpoint / 'THREAT_MODEL.md'
        threat_original = threat.read_bytes()
        threat.write_bytes(threat_original + b'changed\n')
        code, changed_checkpoint = cli(env, *next_cmd)
        check('changed host checkpoint refuses successor', code == 2 and not successor.exists(),
              {'exit': code, 'code': changed_checkpoint.get('code')})
        threat.write_bytes(threat_original)
        cleanup_file = controls / 'cleanup.json'
        write(cleanup_file, {'status': 'unresolved', 'resources': []})
        code, failed_cleanup = cli(env, *next_cmd)
        check('failed cleanup refuses successor', code == 2 and not successor.exists(),
              {'exit': code, 'code': failed_cleanup.get('code')})
        write(cleanup_file, cleanup)
        with sqlite3.connect(provider) as db:
            db.execute("UPDATE tunnels SET phase='active'")
        code, active = cli(env, *next_cmd)
        check('active provider tunnel refuses successor', code == 2 and not successor.exists(),
              {'exit': code, 'code': active.get('code')})
        with sqlite3.connect(provider) as db:
            db.execute("UPDATE tunnels SET phase='closed'")
            db.execute('UPDATE pool SET bytes=1048577')
        code, over_cap = cli(env, *next_cmd)
        check('over-cap provider ledger refuses successor', code == 2 and not successor.exists(),
              {'exit': code, 'code': over_cap.get('code')})
        with sqlite3.connect(provider) as db:
            db.execute('UPDATE pool SET bytes=4096')
            db.execute('UPDATE pool SET bytes=2048')
        code, inconsistent = cli(env, *next_cmd)
        check('inconsistent provider byte ledger refuses successor',
              code == 2 and not successor.exists(),
              {'exit': code, 'code': inconsistent.get('code')})
        with sqlite3.connect(provider) as db:
            db.execute('UPDATE pool SET bytes=4096')
        code, chain = cli(env, 'setup-chain', '--run-root', str(first))
        check('public read-only chain reports original total use',
              code == 0 and chain.get('cumulative_used') == {'connections': 1, 'bytes': 4096}
              and chain.get('epoch_index') == 1 and chain.get('initial_plan_sha256') == sha(first / 'plan.json')
              and isinstance(chain.get('chain_sha256'), str),
              {'exit': code, 'used': chain.get('cumulative_used'), 'chain_sha256': chain.get('chain_sha256')})
        code, continued = cli(env, *next_cmd)
        check('stopped owner prepares residual successor', code == 0 and successor.is_dir(),
              {'exit': code, 'status': continued.get('status'), 'code': continued.get('code')})
        if successor.is_dir():
            next_plan = json.loads((successor / 'plan.json').read_text())
            check('residual limits and original pins persist',
                  next_plan['limits']['max_connections'] == 2
                  and next_plan['limits']['max_bytes'] == 1048576 - 4096
                  and 30 <= next_plan['limits']['duration_seconds'] < 180
                  and next_plan['source_manifest_sha256'] == manifest['source_manifest_sha256']
                  and next_plan['brief_sha256'] == sha(brief), next_plan['limits'])
            link = json.loads((successor / 'controls/setup-epoch.json').read_text())
            check('successor keeps signed original absolute deadline',
                  link.get('absolute_deadline') == deadline
                  and link.get('used_before') == {'connections': 1, 'bytes': 4096},
                  {'deadline': link.get('absolute_deadline'), 'used_before': link.get('used_before')})
            check('host checkpoint mounted for fresh context',
                  (successor / 'controls/research/setup-checkpoint/THREAT_MODEL.md').read_bytes()
                  == (checkpoint / 'THREAT_MODEL.md').read_bytes()
                  and not any((successor / 'researcher/data').iterdir()),
                  {'checkpoint_sha256': sha(successor / 'controls/research/setup-checkpoint/THREAT_MODEL.md')})
            code, reset_template = cli(env, 'setup-approval-template', '--run-root', str(successor),
                                       '--approved-at', now.strftime('%Y-%m-%dT%H:%M:%SZ'),
                                       '--expires-at', (now + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%SZ'),
                                       '--linked-epochs', '--absolute-deadline', deadline)
            check('successor cannot mint a fresh grant template',
                  code == 2 and reset_template.get('code') == 'setup_template_unavailable',
                  {'exit': code, 'code': reset_template.get('code')})
            code, successor_start = cli(env, 'start', '--run-root', str(successor),
                                        '--approval', str(grant_file))
            check('linked grant reaches resource boundary for successor',
                  code == 2 and successor_start.get('code') == 'docker_command_failed',
                  {'exit': code, 'code': successor_start.get('code')})
        code, duplicate = cli(env, *next_cmd[:-1], str(base / 'run-3'))
        check('same stopped epoch cannot branch twice', code == 2 and not (base / 'run-3').exists(),
              {'exit': code, 'code': duplicate.get('code')})
        pins = {'source_manifest_sha256': manifest['source_manifest_sha256'],
                'first_plan_sha256': sha(first / 'plan.json'), 'grant_sha256': sha(grant_file),
                'provider_ledger_sha256': sha(provider), 'revoked_sha256': sha(revoked),
                'scenario_sha256': sha(Path(__file__)), 'cli_sha256': sha(CLI)}
    result = {'kind': 'native-setup-linked-epoch-synthetic-e2e-v1', 'checks': checks,
              'passed': all(row['passed'] for row in checks), 'inputs': pins,
              'model_or_provider_executed': False, 'target_executed': False,
              'classification': 'synthetic signed grant, fabricated stop and provider ledger, Docker absence shim',
              'limits': 'Does not prove live owner loss, provider billing, native reconstruction, or real cleanup.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'passed': result['passed'], 'result': str(args.output)}, sort_keys=True))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
