#!/usr/bin/env python3
"""Provider-free prepared-run rehearsal of the post-stop byte receipt.

Run: python3 evals/native-qualification/smoke/check_native_research_snapshot.py
Requires: Python 3, OpenSSL CLI, Docker CLI (daemon is never contacted), and
the pinned local Linux amd64 relay binary. Expected: all checks pass and
result JSON saved under t02-evidence/native-research-snapshot-20261022a/.
This exercises byte collection only; it does not simulate NativeRun stop proof.
"""

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
import native_research  # noqa: E402

CLI = ROOT / 'tools/native_research.py'
RELAY = (ROOT / 'experiments/native-network-preflight/tcp-relay-host-override/'
         'cloud-linux-amd64-20261020a/tcp-relay-linux-amd64')
RELAY_SHA = '33ef7484c2a2415915af399689e91e9efee8000b2c685a6b2b72eb4eddedf895'
OUTPUT = ROOT / 'evals/native-qualification/t02-evidence/native-research-snapshot-20261022a/result.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    os.umask(0o077)
    if sha(RELAY) != RELAY_SHA:
        raise RuntimeError('pinned_relay_changed')
    checks = []

    def check(name, passed, observed):
        checks.append({'name': name, 'pass': bool(passed), 'observed': observed})

    with tempfile.TemporaryDirectory(prefix='native-snapshot-check-') as raw:
        base = Path(raw).resolve()
        source = base / 'source'
        source.mkdir()
        (source / 'hello.php').write_text('<?php echo "hello";\n')
        brief = base / 'brief.md'
        brief.write_text('Inspect this harmless disposable fixture.\n')
        scope = base / 'scope.md'
        scope.write_text('Provider-free fixture; no live authorization.\n')
        relay = base / 'relay'
        shutil.copy2(RELAY, relay)
        relay.chmod(0o700)
        ca = base / 'ca.pem'
        key = base / 'ca.key'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-noenc',
                        '-days', '1', '-subj', '/CN=disposable snapshot fixture',
                        '-keyout', str(key), '-out', str(ca)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        key.unlink()
        command = base / 'target-command.json'
        command.write_text(json.dumps(['php', '-S', '0.0.0.0:8080']))
        run_root = base / 'run'
        process = subprocess.run([
            sys.executable, str(CLI), 'prepare', '--run-root', str(run_root),
            '--source', str(source), '--brief', str(brief),
            '--scope-file', str(scope), '--scope-sha256', sha(scope),
            '--relay', str(relay), '--relay-sha256', sha(relay),
            '--runtime-ca', str(ca), '--runtime-ca-sha256', sha(ca),
            '--target-command', str(command), '--target-port', '8080',
            '--image-id', 'sha256:' + '1' * 64,
            '--target-image-id', 'sha256:' + '2' * 64,
            '--platform', 'linux/amd64', '--duration-seconds', '7200',
            '--mutable-path', 'data'], cwd=ROOT, capture_output=True, text=True, timeout=30)
        if process.returncode:
            raise RuntimeError('provider_free_prepare_failed')
        plan = json.loads((run_root / 'plan.json').read_text())
        project = run_root / 'researcher/project'
        (project / 'hello.php').write_text('<?php echo "changed";\n')
        secret_name = 'private-password-cookie.txt'
        (project / secret_name).write_text('synthetic value only\n')
        (run_root / 'target/hello.php').write_text('<?php echo "target changed";\n')
        (run_root / 'review-target-2/data').mkdir()
        (run_root / 'review-target-2/data/state.txt').write_text('synthetic state\n')
        store = run_root / 'researcher/data/opencode/opencode.db'
        store.parent.mkdir(mode=0o700)
        with sqlite3.connect(store) as db:
            db.execute('CREATE TABLE example (value TEXT)')
            db.execute('INSERT INTO example (value) VALUES (?)', ('synthetic only',))

        receipt = native_research._filesystem_snapshot(run_root, plan)
        encoded = json.dumps(receipt, sort_keys=True)
        check('snapshot records changed persistent project without filenames',
              receipt.get('status') == 'complete' and
              receipt.get('researcher_project', {}).get('delta') ==
              {'added': 1, 'modified': 1, 'removed': 0} and
              not any(name in encoded for name in ('hello.php', secret_name, 'state.txt', 'db.sqlite')),
              {'status': receipt.get('status'),
               'delta': receipt.get('researcher_project', {}).get('delta')})
        check('snapshot records native SQLite byte identity',
              receipt.get('native_store', {}).get('status') == 'present' and
              receipt.get('native_store', {}).get('main', {}).get('sha256') == sha(store),
              {'store_status': receipt.get('native_store', {}).get('status')})
        targets = receipt.get('targets', {})
        check('snapshot distinguishes target source drift and mutable state',
              targets.get('target', {}).get('immutable_delta') ==
              {'added': 0, 'modified': 1, 'removed': 0} and
              targets.get('review-target-1', {}).get('immutable_delta') ==
              {'added': 0, 'modified': 0, 'removed': 0} and
              targets.get('review-target-2', {}).get('mutable_files') == 1,
              {'target_delta': targets.get('target', {}).get('immutable_delta'),
               'review_2_mutable_files': targets.get('review-target-2', {}).get('mutable_files')})
        store.unlink()
        missing = native_research._filesystem_snapshot(run_root, plan)
        check('missing native SQLite is explicit and incomplete',
              missing.get('status') == 'incomplete' and
              missing.get('native_store', {}).get('status') == 'missing',
              {'status': missing.get('status'),
               'store_status': missing.get('native_store', {}).get('status')})
        (project / 'unsafe-link').symlink_to(source / 'hello.php')
        try:
            native_research._filesystem_snapshot(run_root, plan)
        except native_research.NativeResearchError as error:
            symlink_rejected = str(error) == 'snapshot_symlink_forbidden'
        else:
            symlink_rejected = False
        check('symlink cannot escape a stopped byte snapshot', symlink_rejected,
              {'rejected': symlink_rejected})

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    result = {'kind': 'native-research-provider-free-byte-snapshot-check-v1',
              'provider_or_target_executed': False, 'native_stop_proof_exercised': False,
              'relay_sha256': RELAY_SHA, 'checks': checks,
              'passed': all(item['pass'] for item in checks)}
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'passed': result['passed'], 'checks': len(checks),
                      'result': str(OUTPUT)}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
