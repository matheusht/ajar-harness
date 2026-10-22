#!/usr/bin/env python3
"""Provider-free end-to-end rehearsal of the public native_research CLI.

Run: python3 evals/native-qualification/smoke/check_native_research_prepare.py
Requires: Python 3, OpenSSL CLI, Docker CLI (daemon is never contacted), and the
pinned local Linux amd64 relay binary. Expected: all checks pass; no target,
container, network, provider, or model is started. Result JSON is saved under
evals/native-qualification/t02-evidence/native-research-prepare-20261022a/.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[3]
CLI = ROOT / 'tools/native_research.py'
RELAY = (ROOT / 'experiments/native-network-preflight/tcp-relay-host-override/'
         'cloud-linux-amd64-20261020a/tcp-relay-linux-amd64')
RELAY_SHA = '33ef7484c2a2415915af399689e91e9efee8000b2c685a6b2b72eb4eddedf895'
OUTPUT = ROOT / 'evals/native-qualification/t02-evidence/native-research-prepare-20261022a/result.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def call(*parts):
    process = subprocess.run(['python3', str(CLI), *parts], cwd=ROOT,
                             capture_output=True, text=True, timeout=30)
    try:
        result = json.loads(process.stdout)
    except ValueError:
        result = {'status': 'invalid_cli_json'}
    return process.returncode, result


def main():
    os.umask(0o077)
    if sha(RELAY) != RELAY_SHA:
        raise RuntimeError('pinned_relay_changed')
    checks = []

    def check(name, good, observed):
        checks.append({'name': name, 'pass': bool(good), 'observed': observed})

    with tempfile.TemporaryDirectory(prefix='native-research-prepare-') as raw:
        root = Path(raw).resolve()
        source = root / 'source'
        source.mkdir()
        (source / 'hello.php').write_text('<?php echo "hello";\n')
        brief = root / 'brief.md'
        brief.write_text('Inspect the owned hello fixture and report observed behavior.\n')
        scope = root / 'scope.md'
        scope.write_text('Disposable preparation fixture. No live authorization.\n')
        relay = root / 'relay'
        shutil.copy2(RELAY, relay)
        relay.chmod(0o700)
        ca = root / 'ca.pem'
        key = root / 'ca.key'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-noenc',
                        '-days', '1', '-subj', '/CN=owned preparation fixture',
                        '-keyout', str(key), '-out', str(ca)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=30)
        key.unlink()
        command = root / 'target-command.json'
        command.write_text(json.dumps(['php', '-S', '0.0.0.0:8080']))
        run_root = root / 'run'
        argv = ('prepare', '--run-root', str(run_root), '--source', str(source),
                '--brief', str(brief), '--scope-file', str(scope), '--scope-sha256', sha(scope),
                '--relay', str(relay), '--relay-sha256', sha(relay),
                '--runtime-ca', str(ca), '--runtime-ca-sha256', sha(ca),
                '--target-command', str(command), '--target-port', '8080',
                '--image-id', 'sha256:' + '1' * 64,
                '--target-image-id', 'sha256:' + '2' * 64,
                '--platform', 'linux/amd64', '--duration-seconds', '7200',
                '--mutable-path', 'data')
        code, prepared = call(*argv)
        check('public prepare creates a private sealed run',
              code == 0 and prepared.get('status') == 'prepared_provider_free'
              and run_root.is_dir() and not run_root.stat().st_mode & 0o077,
              {'exit': code, 'status': prepared.get('status')})
        plan = json.loads((run_root / 'plan.json').read_text()) if code == 0 else {}
        check('source, allowance and mutable state are pinned',
              plan.get('source_sha256') == {'hello.php': sha(source / 'hello.php')}
              and plan.get('limits', {}).get('duration_seconds') == 7200
              and plan.get('mutable_paths') == ['data'],
              {'source_count': len(plan.get('source_sha256', {})),
               'duration_seconds': plan.get('limits', {}).get('duration_seconds'),
               'mutable_paths': plan.get('mutable_paths')})
        status_code, status = call('status', '--run-root', str(run_root))
        check('public status reports prepared and no authority',
              status_code == 0 and status.get('status') == 'prepared'
              and status.get('allowance') is None,
              {'exit': status_code, 'status': status.get('status')})
        for target in ('target', 'review-target-1', 'review-target-2'):
            data = run_root / target / 'data'
            data.mkdir()
            (data / 'db.sqlite').write_bytes(b'host-seeded disposable state')
        missing_code, missing = call('start', '--run-root', str(run_root),
                                     '--approval', str(root / 'missing-approval.json'))
        check('declared mutable target state survives preflight; missing approval still rejects',
              missing_code == 2 and missing.get('code') == 'regular_file_unavailable'
              and not (run_root / 'controls/resources.json').exists()
              and not (run_root / 'controls/provider/tunnel.sqlite3').exists(),
              {'exit': missing_code, 'code': missing.get('code')})
        (run_root / 'target/hello.php').write_text('changed source\n')
        immutable_code, immutable = call('start', '--run-root', str(run_root),
                                          '--approval', str(root / 'missing-approval.json'))
        check('immutable target source drift rejects before approval or Docker',
              immutable_code == 2 and immutable.get('code') == 'target_source_or_state_changed'
              and not (run_root / 'controls/resources.json').exists(),
              {'exit': immutable_code, 'code': immutable.get('code')})
        shutil.copy2(source / 'hello.php', run_root / 'target/hello.php')
        recovery_code, recovery = call('recover-start', '--run-root', str(run_root))
        check('preactivation recovery is a no-op without resources',
              recovery_code == 0 and recovery.get('status') == 'no_resources',
              {'exit': recovery_code, 'status': recovery.get('status')})
        (run_root / 'original/hello.php').write_text('tampered\n')
        changed_code, changed = call('start', '--run-root', str(run_root),
                                     '--approval', str(root / 'missing-approval.json'))
        check('source pin fails before approval or Docker',
              changed_code == 2 and changed.get('code') == 'source_pin_mismatch'
              and not (run_root / 'controls/resources.json').exists(),
              {'exit': changed_code, 'code': changed.get('code')})
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    result = {'kind': 'native-research-provider-free-prepare-e2e-v1',
              'provider_or_target_executed': False,
              'relay_sha256': RELAY_SHA, 'checks': checks,
              'passed': all(item['pass'] for item in checks)}
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'passed': result['passed'], 'checks': len(checks),
                      'result': str(OUTPUT)}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
