#!/usr/bin/env python3
"""Public, provider-free baseline for #202; see AGENT-LED-SETUP-CHECKS.md.

Run with --output PATH. Expected: baseline_passed true and issue_202_acceptance
blocked_unimplemented. The Docker shim records an unexpected call; no daemon,
container, model, provider, or target is used.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[3]
CLI = ROOT / 'tools/native_research.py'
RELAY = (ROOT / 'experiments/native-network-preflight/tcp-relay-host-override/'
         'cloud-linux-amd64-20261020a/tcp-relay-linux-amd64')
RELAY_SHA = '33ef7484c2a2415915af399689e91e9efee8000b2c685a6b2b72eb4eddedf895'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cli(env, *args):
    result = subprocess.run([sys.executable, str(CLI), *args], cwd=ROOT, env=env,
                            capture_output=True, text=True, timeout=30)
    try:
        output = json.loads(result.stdout)
    except ValueError:
        output = {'code': 'invalid_cli_json'}
    return result.returncode, output


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if sha(RELAY) != RELAY_SHA:
        raise RuntimeError('pinned_relay_changed')
    checks = []

    def check(name, passed, observed):
        checks.append({'name': name, 'passed': bool(passed), 'observed': observed})

    with tempfile.TemporaryDirectory(prefix='agent-led-setup-baseline-') as raw:
        base = Path(raw).resolve()
        source = base / 'source'
        (source / 'pkg').mkdir(parents=True)
        (source / 'main.py').write_text('from pkg.message import message\nprint(message())\n')
        (source / 'pkg/__init__.py').write_text('"""Harmless fixture."""\n')
        (source / 'pkg/message.py').write_text('def message():\n    return "fixture ready"\n')
        source_manifest = {path.relative_to(source).as_posix(): sha(path)
                           for path in sorted(source.rglob('*')) if path.is_file()}
        brief = base / 'goal.md'
        brief.write_text('Inspect the harmless source fixture. No target execution is authorized.\n')
        scope = base / 'scope.md'
        scope.write_text('Unsigned fixture scope; no target or provider authorization.\n')
        runtime = base / 'runtime.json'
        runtime.write_text(json.dumps({'version_command': ['python3', '--version'],
                                       'version_stdout': 'fixture only',
                                       'dependency_command': ['true']}))
        build = base / 'build.json'
        build.write_text(json.dumps(['python3', 'main.py']))
        relay = base / 'relay'
        shutil.copy2(RELAY, relay)
        relay.chmod(0o700)
        ca, key = base / 'ca.pem', base / 'ca.key'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-noenc',
                        '-days', '1', '-subj', '/CN=setup baseline fixture',
                        '-keyout', str(key), '-out', str(ca)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        key.unlink()
        shim = base / 'bin/docker'
        shim.parent.mkdir()
        marker = base / 'docker-called'
        shim.write_text('#!/bin/sh\nprintf called > ' + shlex.quote(str(marker)) + '\nexit 90\n')
        shim.chmod(0o700)
        env = dict(os.environ, PATH=str(shim.parent) + os.pathsep + os.environ.get('PATH', ''),
                   PYTHONDONTWRITEBYTECODE='1')
        run = base / 'run'
        code, prepared = cli(env, 'prepare', '--source-only', '--run-root', str(run),
                             '--source', str(source), '--brief', str(brief),
                             '--scope-file', str(scope), '--scope-sha256', sha(scope),
                             '--relay', str(relay), '--relay-sha256', sha(relay),
                             '--runtime-ca', str(ca), '--runtime-ca-sha256', sha(ca),
                             '--source-runtime', str(runtime), '--build-command', str(build),
                             '--image-id', 'sha256:' + '1' * 64,
                             '--target-image-id', 'sha256:' + '2' * 64,
                             '--platform', 'linux/amd64')
        check('public prepare seals an unsigned fixture without setup approval',
              code == 0 and prepared.get('status') == 'prepared_provider_free',
              {'exit': code, 'status': prepared.get('status'), 'code': prepared.get('code')})
        plan = json.loads((run / 'plan.json').read_text()) if code == 0 else {}
        check('all source files are frozen and pinned',
              plan.get('source_sha256') == source_manifest
              and all(sha(run / 'original' / name) == digest
                      for name, digest in source_manifest.items()),
              {'source_file_count': len(source_manifest),
               'source_manifest_sha256': plan.get('source_manifest_sha256')})
        status_code, status = cli(env, 'status', '--run-root', str(run)) if code == 0 else (2, {})
        check('public status has no active allowance',
              status_code == 0 and status.get('status') == 'prepared'
              and status.get('allowance') is None,
              {'exit': status_code, 'status': status.get('status')})
        start_code, start = cli(env, 'start', '--run-root', str(run),
                                '--approval', str(base / 'missing-approval.json')) if code == 0 else (2, {})
        check('start rejects missing research approval before any effect',
              start_code == 2 and start.get('code') == 'regular_file_unavailable'
              and not (run / 'controls/resources.json').exists() and not marker.exists(),
              {'exit': start_code, 'code': start.get('code'),
               'docker_shim_called': marker.exists()})
        inputs = {'source': source_manifest, 'goal_sha256': sha(brief),
                  'scope_sha256': sha(scope), 'runtime_sha256': sha(runtime),
                  'build_command_sha256': sha(build), 'relay_sha256': sha(relay),
                  'ca_sha256': sha(ca), 'cli_sha256': sha(CLI),
                  'scenario_sha256': sha(Path(__file__)), 'setup_approval': 'absent'}

    result = {'kind': 'agent-led-setup-current-boundary-v1', 'inputs': inputs,
              'checks': checks, 'baseline_passed': all(item['passed'] for item in checks),
              'issue_202_acceptance': 'blocked_unimplemented',
              'model_or_target_executed': False, 'docker_daemon_contacted': False,
              'limits': 'Tests public provider-free prepare/status/start refusal only; '
                        'does not test signed setup authority, agent proposal, host build, '
                        'shared allowance, interruption, or cleanup.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'baseline_passed': result['baseline_passed'],
                      'issue_202_acceptance': result['issue_202_acceptance'],
                      'result': str(args.output)}, sort_keys=True))
    return 0 if result['baseline_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
