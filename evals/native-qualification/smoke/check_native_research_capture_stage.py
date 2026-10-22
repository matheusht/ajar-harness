#!/usr/bin/env python3
"""Provider-free public CLI rehearsal of pinned Kanboard capture staging.

Run with clean Kanboard 644ad391 source, a fresh output directory, Python 3,
OpenSSL CLI, and the pinned local Linux amd64 relay binary::

  python3 evals/native-qualification/smoke/check_native_research_capture_stage.py \
    --source /private/tmp/kanboard-source-644ad391 \
    --output /private/tmp/native-research-capture-stage-NEW

Expected: result.json status pass. No Docker daemon, target, or provider call.
"""

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[3]
CLI = ROOT / 'tools/native_research.py'
RELAY = (ROOT / 'experiments/native-network-preflight/tcp-relay-host-override/'
         'cloud-linux-amd64-20261020a/tcp-relay-linux-amd64')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def call(environment, *args):
    process = subprocess.run([sys.executable, str(CLI), *args], cwd=ROOT,
                             env=environment, capture_output=True, text=True, timeout=90)
    return process.returncode, json.loads(process.stdout)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    receipt = {'kind': 'native_research_capture_stage_provider_free', 'status': 'fail',
               'checks': {}, 'provider_calls': 0, 'docker_calls': 0}
    try:
        spec = importlib.util.spec_from_file_location('s10_case', ROOT / 'evals/native-qualification/s10_observer_case.py')
        s10 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(s10)
        source = args.source.resolve(strict=True)
        if (s10.git(source, 'rev-parse', 'HEAD') != s10.SOURCE_HEAD or
                s10.git(source, 'status', '--porcelain', '--untracked-files=all') != ''):
            raise RuntimeError('pinned_source_not_clean')
        archive = output / 'source'
        archive.mkdir(mode=0o700)
        s10.archive_source(source, archive)
        fake_docker = output / 'docker'
        fake_docker.write_text('#!/bin/sh\nexit 99\n')
        fake_docker.chmod(0o700)
        environment = dict(os.environ)
        environment['PATH'] = str(output) + os.pathsep + environment['PATH']
        brief = output / 'BRIEF.md'
        brief.write_text('Inspect the bounded Kanboard case and report only observed effects.\n')
        scope = output / 'scope.md'
        scope.write_text('Provider-free staging rehearsal; no live target authority.\n')
        relay = output / 'relay'
        shutil.copy2(RELAY, relay)
        relay.chmod(0o700)
        ca = output / 'ca.pem'
        key = output / 'ca.key'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-noenc',
                        '-days', '1', '-subj', '/CN=owned staging fixture',
                        '-keyout', str(key), '-out', str(ca)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        key.unlink()
        command = output / 'target-command.json'
        command.write_text(json.dumps(['php', '-S', '0.0.0.0:8080', '-t', '/target']))
        run = output / 'run'
        code, prepared = call(environment, 'prepare', '--run-root', str(run), '--source', str(archive),
                              '--brief', str(brief), '--scope-file', str(scope), '--scope-sha256', sha(scope),
                              '--relay', str(relay), '--relay-sha256', sha(relay),
                              '--runtime-ca', str(ca), '--runtime-ca-sha256', sha(ca),
                              '--target-command', str(command), '--target-port', '8080',
                              '--image-id', 'sha256:' + '1' * 64,
                              '--target-image-id', 'sha256:' + '2' * 64,
                              '--platform', 'linux/amd64', '--mutable-path', 'data', '--kanboard-capture')
        if code or prepared.get('status') != 'prepared_provider_free':
            raise RuntimeError('public_capture_prepare_failed:' + str(prepared))
        plan = json.loads((run / 'plan.json').read_text())
        receipt['checks']['pinned_public_prepare'] = bool(plan.get('kanboard_capture'))
        stages = {}
        for index, target in enumerate(('target', 'review-target-1', 'review-target-2')):
            code, staged = call(environment, 'capture-stage', '--run-root', str(run), '--target', target,
                                '--s', str(4 + index * 4), '--q', str(5 + index * 4),
                                '--t', str(6 + index * 4), '--b', str(7 + index * 4))
            if code or staged.get('status') != 'staged_origin_and_credentials_held':
                raise RuntimeError('public_capture_stage_failed:' + str(staged))
            stages[target] = staged['stage_sha256']
        receipt['checks']['three_public_stages_pinned'] = all(
            stages[target] == sha(run / 'controls/observer' / target / 'stage.json') for target in stages)
        now = datetime.now(timezone.utc)
        approval = output / 'approval.json'
        approval.write_text(json.dumps({
            'kind': 'native-research-live-approval-v1', 'plan_sha256': sha(run / 'plan.json'),
            'scope_sha256': sha(scope), 'provider_route': plan['provider_route'],
            'provider_authority': plan['provider_authority'], 'model': plan['model'],
            'image_id': plan['image_id'], 'target_image_id': plan['target_image_id'],
            'limits': plan['limits'], 'approved_by': 'provider-free-fixture',
            'approved_at': now.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'expires_at': (now + timedelta(minutes=5)).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'capture_stage_sha256': {'target': '0' * 64, **{k: v for k, v in stages.items() if k != 'target'}}}))
        code, rejected = call(environment, 'start', '--run-root', str(run), '--approval', str(approval))
        receipt['checks']['wrong_stage_approval_rejected_before_docker'] = (
            code == 2 and rejected.get('code') == 'live_approval_mismatch'
            and not (run / 'controls/resources.json').exists())
        receipt['source_head'] = s10.SOURCE_HEAD
        receipt['plan_sha256'] = sha(run / 'plan.json')
        receipt['capture_stage_sha256'] = stages
        receipt['status'] = 'pass' if all(receipt['checks'].values()) else 'fail'
    except Exception as error:
        receipt['failure'] = str(error) if isinstance(error, RuntimeError) else type(error).__name__
    (output / 'result.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'status': receipt['status'], 'result': str(output / 'result.json')}))
    return 0 if receipt['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
