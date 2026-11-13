#!/usr/bin/env python3
"""Synthetic public CLI authority and Docker isolation scenario for #208.

This does not contact a provider or run OpenCode. The separate boundary probe
uses an already-local image to check read-only source, bounded workspace,
no network, and exact cleanup readback. See AGENT-LED-SETUP-CHECKS.md.
"""

import argparse
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
from engagement_records import canonical_json_bytes, sha256_bytes  # noqa: E402
from operator_signature import encode_operator_signature_proof  # noqa: E402

CLI = ROOT / 'tools/native_research.py'
RELAY = (ROOT / 'experiments/native-network-preflight/tcp-relay-host-override/'
         'cloud-linux-amd64-20261020a/tcp-relay-linux-amd64')
NAMESPACE = 'llm-redteam-harness-native-setup-v1'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*argv, **kwargs):
    return subprocess.run(argv, capture_output=True, text=True, check=False, timeout=30, **kwargs)


def cli(env, *args):
    result = run(sys.executable, str(CLI), *args, cwd=ROOT, env=env)
    try:
        value = json.loads(result.stdout)
    except ValueError:
        value = {'code': 'invalid_cli_json', 'stderr': result.stderr[:1000]}
    return result.returncode, value


def sign(key, content):
    result = subprocess.run(['ssh-keygen', '-Y', 'sign', '-f', str(key), '-n', NAMESPACE],
                            input=content, capture_output=True, check=True, timeout=10)
    return result.stdout


def boundary_probe(source, image):
    name = 'lrh-setup-fixture-' + uuid.uuid4().hex[:12]
    identifier = None
    observed = {}
    try:
        created = run('docker', 'container', 'create', '--name', name, '--pull', 'never',
                      '--network', 'none', '--read-only', '--cap-drop', 'ALL',
                      '--security-opt', 'no-new-privileges=true',
                      '--user', f'{os.getuid()}:{os.getgid()}',
                      '--tmpfs', '/workspace:rw,nosuid,nodev,size=8388608',
                      '--mount', f'type=bind,src={source},dst=/source,readonly',
                      image, 'sh', '-c', 'while :; do sleep 3600; done')
        if created.returncode:
            return {'status': 'unavailable', 'reason': created.stderr.strip()[:1000]}
        identifier = created.stdout.strip()
        started = run('docker', 'container', 'start', identifier)
        if started.returncode:
            return {'status': 'unavailable', 'reason': started.stderr.strip()[:1000]}
        info = json.loads(run('docker', 'container', 'inspect', identifier).stdout)[0]
        readable = run('docker', 'container', 'exec', identifier, 'cat', '/source/main.py')
        write_source = run('docker', 'container', 'exec', identifier, 'sh', '-c',
                           'echo changed > /source/main.py')
        write_workspace = run('docker', 'container', 'exec', identifier, 'sh', '-c',
                              'echo proposal > /workspace/proposal')
        observed = {'status': 'checked', 'container_id': identifier,
                    'network': info['HostConfig']['NetworkMode'],
                    'readonly_root': info['HostConfig']['ReadonlyRootfs'],
                    'workspace_tmpfs': info['HostConfig']['Tmpfs'].get('/workspace'),
                    'source_mount_readonly': any(item.get('Destination') == '/source'
                                                 and item.get('RW') is False
                                                 for item in info['Mounts']),
                    'source_readable': readable.returncode == 0,
                    'source_write_denied': write_source.returncode != 0,
                    'workspace_write_succeeded': write_workspace.returncode == 0}
    finally:
        if identifier:
            removed = run('docker', 'container', 'rm', '-f', identifier)
            listing = run('docker', 'container', 'ls', '-a', '--no-trunc',
                          '--filter', 'id=' + identifier, '--format', '{{.ID}}')
            observed['cleanup_absent'] = removed.returncode == 0 and not listing.stdout.strip()
    observed['passed'] = (observed.get('status') == 'checked'
                          and observed.get('network') == 'none'
                          and observed.get('readonly_root') is True
                          and observed.get('workspace_tmpfs') == 'rw,nosuid,nodev,size=8388608'
                          and observed.get('source_mount_readonly') is True
                          and observed.get('source_readable') is True
                          and observed.get('source_write_denied') is True
                          and observed.get('workspace_write_succeeded') is True
                          and observed.get('cleanup_absent') is True)
    return observed


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--boundary-image', default='busybox:1.37')
    parser.add_argument('--skip-docker-boundary', action='store_true')
    args = parser.parse_args()
    checks = []

    def check(name, passed, observed):
        checks.append({'name': name, 'passed': bool(passed), 'observed': observed})

    with tempfile.TemporaryDirectory(prefix='native-setup-e2e-') as raw:
        base = Path(raw).resolve()
        source = base / 'source'
        (source / 'pkg').mkdir(parents=True)
        (source / 'main.py').write_text('from pkg.message import message\nprint(message())\n')
        (source / 'pkg/__init__.py').write_text('"""Fixture."""\n')
        (source / 'pkg/message.py').write_text('def message():\n    return "fixture ready"\n')
        source_pin = {path.relative_to(source).as_posix(): sha(path)
                      for path in sorted(source.rglob('*')) if path.is_file()}
        brief = base / 'goal.md'
        brief.write_text('Inspect this harmless source. Choose a runtime without a build hint.\n')
        key = base / 'operator_key'
        subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)],
                       check=True, timeout=10)
        signers = base / 'allowed_signers'
        signers.write_text('synthetic-operator ' + (base / 'operator_key.pub').read_text())
        fingerprint_b64 = run('ssh-keygen', '-lf', str(base / 'operator_key.pub'),
                              '-E', 'sha256').stdout.split('SHA256:')[1].split()[0]
        fingerprint = 'sha256:' + base64.b64decode(fingerprint_b64 + '=' * (-len(fingerprint_b64) % 4)).hex()
        scope = base / 'scope.md'
        boundary = {'kind': 'native-setup-scope-v1', 'engagement_id': 'fixture-208',
                    'operator_id': 'synthetic-operator',
                    'source_manifest_sha256': hashlib.sha256(json.dumps(
                        source_pin, sort_keys=True).encode()).hexdigest(),
                    'goal_sha256': sha(brief),
                    'surfaces': ['owned original source tree'],
                    'benign_objectives': ['propose an offline runtime recipe and threat model'],
                    'escalation_ceiling': 'setup_only', 'impact_demo_authorized': False,
                    'accounts': [],
                    'cleanup': 'Stop and remove every owned setup container and network.',
                    'effect_class': 'read-only-original-and-disposable-offline-proposal',
                    'network_class': 'metered-model-relay-only',
                    'expires_at': (datetime.now(timezone.utc) + timedelta(hours=1)).strftime(
                        '%Y-%m-%dT%H:%M:%SZ')}
        scope_prefix = ('# Harmless synthetic setup scope\n\n'
                        '- Operator allowed signers SHA256: sha256:' + sha(signers) + '\n'
                        '- Signed: [x] synthetic operator\n\n')
        def scope_text(value):
            return scope_prefix + '```native-setup-scope-v1\n' + json.dumps(value, sort_keys=True) + '\n```\n'
        scope.write_text(scope_text(boundary))
        scope_signature = base / 'scope.sig'
        scope_signature.write_bytes(sign(key, canonical_json_bytes({
            'kind': 'native-setup-scope-challenge-v1', 'engagement_id': 'fixture-208',
            'scope_sha256': sha(scope)})))
        relay = base / 'relay'
        shutil.copy2(RELAY, relay)
        relay.chmod(0o700)
        ca, ca_key = base / 'ca.pem', base / 'ca.key'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-noenc',
                        '-days', '1', '-subj', '/CN=native setup fixture',
                        '-keyout', str(ca_key), '-out', str(ca)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        ca_key.unlink()
        marker = base / 'docker-called'
        shim = base / 'bin/docker'
        shim.parent.mkdir()
        shim.write_text('#!/bin/sh\nprintf called > "' + str(marker) + '"\nexit 90\n')
        shim.chmod(0o700)
        env = dict(os.environ, PATH=str(shim.parent) + os.pathsep + os.environ.get('PATH', ''),
                   PYTHONDONTWRITEBYTECODE='1')
        run_root = base / 'run'
        prepare_args = ('prepare', '--setup-only', '--run-root', str(run_root),
                        '--source', str(source), '--brief', str(brief),
                        '--scope-file', str(scope), '--scope-sha256', sha(scope),
                        '--setup-scope-signature', str(scope_signature),
                        '--setup-allowed-signers', str(signers),
                        '--setup-trusted-fingerprint', fingerprint,
                        '--setup-operator-id', 'synthetic-operator',
                        '--setup-engagement-id', 'fixture-208',
                        '--relay', str(relay), '--relay-sha256', sha(relay),
                        '--runtime-ca', str(ca), '--runtime-ca-sha256', sha(ca),
                        '--image-id', 'sha256:' + '1' * 64, '--platform', 'linux/amd64',
                        '--max-connections', '2', '--max-bytes', '1048576',
                        '--duration-seconds', '120')
        manifest_code, manifest = cli(env, 'setup-source-manifest', '--source', str(source))
        check('public source identity matches signed manifest',
              manifest_code == 0 and manifest.get('source_sha256') == source_pin
              and manifest.get('source_manifest_sha256') == boundary['source_manifest_sha256'],
              {'exit': manifest_code, 'source_manifest_sha256': manifest.get('source_manifest_sha256')})
        incomplete_scope = base / 'scope-incomplete.md'
        incomplete_boundary = dict(boundary)
        incomplete_boundary.pop('benign_objectives')
        incomplete_scope.write_text(scope_text(incomplete_boundary))
        incomplete_sig = base / 'scope-incomplete.sig'
        incomplete_sig.write_bytes(sign(key, canonical_json_bytes({
            'kind': 'native-setup-scope-challenge-v1', 'engagement_id': 'fixture-208',
            'scope_sha256': sha(incomplete_scope)})))
        incomplete_args = list(prepare_args)
        incomplete_args[incomplete_args.index('--scope-file') + 1] = str(incomplete_scope)
        incomplete_args[incomplete_args.index('--scope-sha256') + 1] = sha(incomplete_scope)
        incomplete_args[incomplete_args.index('--setup-scope-signature') + 1] = str(incomplete_sig)
        incomplete_args[incomplete_args.index('--run-root') + 1] = str(base / 'incomplete-run')
        code, incomplete = cli(env, *incomplete_args)
        check('signed but incomplete scope refuses before run creation',
              code == 2 and incomplete.get('code') == 'setup_scope_incomplete'
              and not (base / 'incomplete-run').exists() and not marker.exists(),
              {'exit': code, 'code': incomplete.get('code')})
        unsigned_args = list(prepare_args)
        unsigned_args[unsigned_args.index('--setup-scope-signature') + 1] = str(base / 'absent.sig')
        unsigned_args[unsigned_args.index('--run-root') + 1] = str(base / 'unsigned-run')
        code, unsigned = cli(env, *unsigned_args)
        check('unsigned scope refuses before run creation',
              code == 2 and unsigned.get('code') == 'regular_file_unavailable'
              and not (base / 'unsigned-run').exists() and not marker.exists(),
              {'exit': code, 'code': unsigned.get('code')})
        large_source = base / 'large-source'
        shutil.copytree(source, large_source)
        with (large_source / 'large.bin').open('wb') as stream:
            stream.truncate(129 * 1024 * 1024)
        large_args = list(prepare_args)
        large_args[large_args.index('--source') + 1] = str(large_source)
        large_args[large_args.index('--run-root') + 1] = str(base / 'large-run')
        code, large = cli(env, *large_args)
        check('source disk cap refuses before copy',
              code == 2 and large.get('code') == 'setup_source_limit_exceeded'
              and not (base / 'large-run').exists() and not marker.exists(),
              {'exit': code, 'code': large.get('code')})
        changed_source = base / 'changed-source'
        shutil.copytree(source, changed_source)
        (changed_source / 'main.py').write_text('print("changed fixture")\n')
        changed_source_args = list(prepare_args)
        changed_source_args[changed_source_args.index('--source') + 1] = str(changed_source)
        changed_source_args[changed_source_args.index('--run-root') + 1] = str(base / 'changed-source-run')
        code, changed_source_result = cli(env, *changed_source_args)
        check('signed source digest rejects changed export before copy',
              code == 2 and changed_source_result.get('code') == 'setup_signed_source_mismatch'
              and not (base / 'changed-source-run').exists() and not marker.exists(),
              {'exit': code, 'code': changed_source_result.get('code')})
        code, prepared = cli(env, *prepare_args)
        check('signed scope and source prepare without Docker contact',
              code == 0 and prepared.get('status') == 'prepared_provider_free'
              and not marker.exists(), {'exit': code, 'result': prepared})
        if code:
            raise RuntimeError('signed setup prepare failed: ' + str(prepared))
        plan = json.loads((run_root / 'plan.json').read_text())
        check('original source matches all frozen pins',
              plan.get('source_sha256') == source_pin
              and all(sha(run_root / 'original' / name) == digest
                      for name, digest in source_pin.items()),
              {'source_file_count': len(source_pin),
               'source_manifest_sha256': plan.get('source_manifest_sha256')})
        dispatch_dir = run_root / 'controls/dispatch'
        older_id, newer_id = 'f' * 32, '0' * 31 + '1'
        (dispatch_dir / (older_id + '.json')).write_text(json.dumps({
            'kind': 'native-dispatch-v1', 'role': 'researcher', 'status': 'acknowledged',
            'dispatch_id': older_id, 'setup_sequence': 1}) + '\n')
        (dispatch_dir / (newer_id + '.json')).write_text(json.dumps({
            'kind': 'native-dispatch-v1', 'role': 'resume', 'status': 'acknowledged',
            'dispatch_id': newer_id, 'setup_sequence': 2}) + '\n')
        status_code, ordering = cli(env, 'status', '--run-root', str(run_root))
        check('latest turn follows durable order, not reversed UUID order',
              status_code == 0 and ordering.get('setup', {}).get('last_dispatch_id') == newer_id,
              {'exit': status_code, 'last_dispatch_id': ordering.get('setup', {}).get('last_dispatch_id')})
        (dispatch_dir / (older_id + '.json')).unlink()
        (dispatch_dir / (newer_id + '.json')).unlink()
        code, missing = cli(env, 'start', '--run-root', str(run_root),
                            '--approval', str(base / 'missing-approval.json'))
        check('missing setup approval rejects before effect',
              code == 2 and missing.get('code') == 'regular_file_unavailable' and not marker.exists(),
              {'exit': code, 'code': missing.get('code'), 'docker_called': marker.exists()})
        now = datetime.now(timezone.utc).replace(microsecond=0)
        approval = {'kind': 'native-setup-approval-v1', 'engagement_id': 'fixture-208',
                    'plan_sha256': sha(run_root / 'plan.json'),
                    'source_manifest_sha256': plan['source_manifest_sha256'],
                    'scope_sha256': sha(scope), 'brief_sha256': sha(brief),
                    'image_id': plan['image_id'], 'platform': plan['platform'],
                    'model': plan['model'], 'provider_route': plan['provider_route'],
                    'provider_authority': plan['provider_authority'],
                    'relay_sha256': sha(relay), 'runtime_ca_sha256': sha(ca),
                    'effect_class': plan['setup_only']['effect_class'],
                    'network_class': plan['setup_only']['network_class'],
                    'limits': plan['limits'],
                    'max_workspace_bytes': plan['setup_only']['max_workspace_bytes'],
                    'monetary_cap_usd': None, 'approved_by': 'synthetic-operator',
                    'approved_at': now.strftime('%Y-%m-%dT%H:%M:%SZ'),
                    'expires_at': (now + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%SZ')}

        def signed_approval(value, path):
            unsigned = dict(value)
            signature = sign(key, canonical_json_bytes(unsigned))
            value = dict(unsigned)
            value['operator_signature'] = encode_operator_signature_proof(
                challenge_bytes=canonical_json_bytes(unsigned), signature_bytes=signature,
                allowed_signers_bytes=signers.read_bytes(), signer_fingerprint=fingerprint)
            path.write_text(json.dumps(value, sort_keys=True) + '\n')
            return path

        expensive = dict(approval, monetary_cap_usd=1)
        expensive_path = signed_approval(expensive, base / 'money-approval.json')
        code, money = cli(env, 'start', '--run-root', str(run_root), '--approval', str(expensive_path))
        check('unmetered requested monetary cap fails closed',
              code == 2 and money.get('code') == 'setup_monetary_cap_unenforceable'
              and not marker.exists(), {'exit': code, 'code': money.get('code')})
        expanded = dict(approval, effect_class='target-build')
        expanded_path = signed_approval(expanded, base / 'expanded-approval.json')
        code, blocked = cli(env, 'start', '--run-root', str(run_root), '--approval', str(expanded_path))
        check('unsupported effect class rejects before effect',
              code == 2 and blocked.get('code') == 'setup_approval_mismatch'
              and not marker.exists(), {'exit': code, 'code': blocked.get('code')})
        approval_path = signed_approval(approval, base / 'approval.json')
        archived_scope = run_root / 'controls/scope.md'
        archived_scope.write_text(archived_scope.read_text() + 'changed\n')
        code, changed_scope = cli(env, 'start', '--run-root', str(run_root),
                                  '--approval', str(approval_path))
        check('changed archived scope rejects before effect',
              code == 2 and changed_scope.get('code') == 'run_input_pin_mismatch'
              and not marker.exists(), {'exit': code, 'code': changed_scope.get('code')})
        shutil.copy2(scope, archived_scope)
        (run_root / 'original/main.py').write_text('changed\n')
        code, changed = cli(env, 'start', '--run-root', str(run_root), '--approval', str(approval_path))
        check('changed frozen source rejects before effect',
              code == 2 and changed.get('code') == 'source_pin_mismatch'
              and not marker.exists(), {'exit': code, 'code': changed.get('code')})
        (run_root / 'original/main.py').write_text((source / 'main.py').read_text())
        code, accepted = cli(env, 'start', '--run-root', str(run_root), '--approval', str(approval_path))
        check('valid setup approval reaches Docker only after signature checks',
              code == 2 and accepted.get('code') == 'docker_command_failed' and marker.exists()
              and (run_root / 'controls/setup-approval-receipt.json').exists(),
              {'exit': code, 'code': accepted.get('code'), 'docker_called': marker.exists()})
        frozen = run_root / 'controls/setup-output'
        frozen.mkdir()
        (frozen / 'receipt.json').write_text('{"kind":"native-setup-output-v1"}\n')
        prompt = base / 'resume.md'
        prompt.write_text('Continue the harmless setup.\n')
        turn_code, frozen_turn = cli(env, 'setup-turn', '--run-root', str(run_root))
        resume_code, frozen_resume = cli(env, 'setup-resume', '--run-root', str(run_root),
                                         '--session', 'ses_fixture', '--prompt-file', str(prompt))
        check('frozen setup refuses another first turn before native dispatch',
              turn_code == 2 and frozen_turn.get('code') == 'setup_output_already_frozen',
              {'exit': turn_code, 'code': frozen_turn.get('code')})
        check('frozen setup refuses resume before native dispatch',
              resume_code == 2 and frozen_resume.get('code') == 'setup_output_already_frozen',
              {'exit': resume_code, 'code': frozen_resume.get('code')})
        boundary = (None if args.skip_docker_boundary else
                    boundary_probe(source, args.boundary_image))
        if boundary is not None:
            check('local Docker source and cleanup boundary', boundary.get('passed'), boundary)
        inputs = {'source': source_pin, 'scope_sha256': sha(scope),
                  'scope_signature_sha256': sha(scope_signature),
                  'setup_approval_sha256': sha(approval_path),
                  'goal_sha256': sha(brief), 'relay_sha256': sha(relay),
                  'runtime_ca_sha256': sha(ca),
                  'cli_sha256': sha(CLI), 'scenario_sha256': sha(Path(__file__))}
    result = {'kind': 'native-setup-synthetic-e2e-v1', 'inputs': inputs, 'checks': checks,
              'passed': all(row['passed'] for row in checks),
              'provider_or_model_executed': False, 'target_executed': False,
              'classification': 'synthetic signed authority, Docker shim, and local boundary probe',
              'limits': 'No native model turn, live relay, interruption recovery, or full start cleanup.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'passed': result['passed'], 'result': str(args.output)}, sort_keys=True))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
