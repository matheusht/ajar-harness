#!/usr/bin/env python3
"""Failure-first public CLI wiring with signed local fixtures and the real runner.

Inspect must call comprehensive preflight without dispatch. Run/resume must use the
real NativeBoundary and report unavailable prerequisites instead of a placeholder.
Stop must persist revocation, then recover under the sole runner lock; a live owner
must receive pending stop status without a second cleanup owner. Unknown effects
remain unknown. V1 status routing and the absence of a CLI simulation switch remain.
Configured native/environment binaries are unused sentinels; no model, Docker
daemon, or target is called. SSH signing uses an ephemeral local fixture key.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'tools'), str(Path(__file__).resolve().parent)]
from check_engagement_contract_e2e import make_fixture, fixture_scope, resign_fixture, write, encoded, sha
from engagement_contract import load_inputs
from engagement_controller import Controller


def require(value, message):
    if not value: raise AssertionError(message)


def inputs_fixture(root):
    inputs = make_fixture(root)
    document = json.loads(inputs.read_bytes()); scope = fixture_scope(inputs)
    runtime_file = Path(document['runtime_profiles']['runtime-main'])
    runtime = json.loads(runtime_file.read_bytes()); binary = Path(runtime['executable']['path'])
    marker = root / 'EXECUTED'
    write(binary, ('#!/bin/sh\nprintf executed > ' + shlex.quote(str(marker)) + '\nexit 91\n').encode()); binary.chmod(0o700)
    runtime['executable']['sha256'] = sha(binary.read_bytes()); write(runtime_file, encoded(runtime))
    scope['runtime_assignments'][0]['profile_sha256'] = sha(runtime_file.read_bytes()); resign_fixture(inputs, scope)
    return inputs, marker


def cli(*arguments):
    process = subprocess.run([sys.executable, str(ROOT / 'tools/native_engagement.py'), *map(str, arguments)],
        capture_output=True, text=True, timeout=15)
    require(process.stdout.strip(), 'CLI did not return JSON: ' + process.stderr[-500:])
    return process.returncode, json.loads(process.stdout)


def owner(root):
    code = 'import fcntl,os,sys\nfd=os.open(sys.argv[1],os.O_CREAT|os.O_RDWR,0o600);fcntl.flock(fd,fcntl.LOCK_EX);print("locked",flush=True);sys.stdin.read()'
    process = subprocess.Popen([sys.executable, '-c', code, str(root / 'runner.lock')],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    require(process.stdout.readline().strip() == 'locked', 'fixture owner did not acquire lock')
    return process


def scenario(root, name):
    inputs, marker = inputs_fixture(root / 'inputs')
    engagement = root / 'engagement'
    if name == 'inspect':
        code, result = cli('inspect', '--inputs', inputs)
        require(result.get('kind') == 'native-engagement-preflight-v2', 'inspect skipped composed preflight')
        require(code == 2 and result['status'] == 'blocked' and 'native_bundle_platform_mismatch' in result['blocked_codes'],
                'inspect hid unavailable native prerequisite')
        require(not engagement.exists() and not marker.exists() and result['runtime_and_target_contact'] is False,
                'inspect dispatched or initialized')
        return {'status': result['status'], 'blocked_codes': result['blocked_codes']}
    if name == 'run-resume':
        code, first = cli('run', '--inputs', inputs, '--engagement-root', engagement)
        require(code == 2 and first['status'] == 'blocked' and first.get('code') == 'worker_progress_unavailable',
                'run did not enter real runner/boundary')
        controller = Controller(engagement); before = controller.state()
        require(before['evidence_class'] == 'native' and len(before['dispatches']) == 1, 'run bypassed native dispatch journal')
        require(not marker.exists() and first['cleanup'] == 'verified'
                and before['workers']['lead-1']['status'] == 'stopped'
                and all(row.get('cancelled_receipt') for row in before['dispatches'].values()),
                'unadmitted preparation was executed or lacked cancellation proof')
        code, resumed = cli('resume', '--engagement-root', engagement)
        after = controller.state()
        require(code == 2 and resumed.get('code') == 'worker_progress_unavailable', 'resume skipped runner recovery')
        require(after['usage'] == before['usage'] and len(after['dispatches']) == 2
                and all(row.get('cancelled_receipt') for row in after['dispatches'].values()),
                'resume charged unused work or lost cancelled preparation history')
        require(resumed['failures'] == first['failures'] and after['workers']['lead-1']['generation'] == 2,
                'resume hid the unchanged prerequisite or reused stale authority')
        code, repeat = cli('run', '--inputs', inputs, '--engagement-root', engagement)
        require(code == 2 and repeat.get('code') == 'engagement_root_exists_or_invalid', 'run replaced existing journal')
        return {'run_status': first['status'], 'resume_status': resumed['status'], 'cleanup': resumed['cleanup'],
                'dispatches': len(after['dispatches']), 'usage_unchanged': True}
    controller = Controller.initialize(engagement, load_inputs(inputs))
    if name == 'stop-recovery':
        workspace = root / 'workspace'; workspace.mkdir(mode=0o700)
        grant = controller.prepare_worker_dispatch('lead-1', 1, workspace, seconds=30,
            resources=['source-main'], adapter_id='native-runner')
        code, result = cli('stop', '--engagement-root', engagement)
        state = controller.state()
        require(code == 0 and state['status'] == 'stopped', 'stop authority not persisted')
        require(result.get('failures', {}).get('lead-1') == 'recovery_effect_unresolved', 'stop did not attempt owned recovery')
        require(result['cleanup'] != 'verified' and state['dispatches'][grant['dispatch_id']]['status'] != 'settled'
                and result['resource_holds'], 'stop invented cleanup for unobserved effects')
        return {'status': result['status'], 'cleanup': result['cleanup'], 'failures': result['failures']}
    if name in ('stop-owned', 'resume-owned'):
        process = owner(engagement)
        try:
            code, result = cli('stop' if name == 'stop-owned' else 'resume', '--engagement-root', engagement)
            require(process.poll() is None, 'CLI terminated the active owner')
            if name == 'stop-owned':
                require(code == 0 and result['status'] == 'stopping' and controller.state()['status'] == 'stopped',
                        'active owner stop was not persisted and reported pending')
            else:
                require(code == 2 and result.get('code') == 'engagement_already_running', 'resume acquired a second owner')
            require(not controller.state()['dispatches'] and not marker.exists(), 'busy CLI dispatched a worker')
            return {'status': result['status'], 'code': result.get('code'), 'owner_untouched': True}
        finally:
            process.communicate('', timeout=3)
    if name == 'no-simulation-switch':
        process = subprocess.run([sys.executable, str(ROOT / 'tools/native_engagement.py'), 'resume',
            '--engagement-root', str(engagement), '--simulate'], capture_output=True, text=True, timeout=5)
        require(process.returncode == 2 and 'unrecognized arguments' in process.stderr, 'simulation escape exposed')
        return {'rejected': True}
    raise AssertionError('unknown scenario')


def legacy(root):
    directory = root / 'legacy'; directory.mkdir(mode=0o700)
    data = encoded({'kind': 'native-engagement-inputs-v1'})
    write(directory / 'inputs.json', data)
    write(directory / 'state.json', encoded({'kind': 'native-engagement-driver-v1', 'phase': 'initialized',
        'pending': None, 'inputs_sha256': hashlib.sha256(data).hexdigest(), 'scope_sha256': '0' * 64,
        'scope_kind': 'native-engagement-scope-v1', 'error': None, 'cleanup': None}))
    code, result = cli('status', '--engagement-root', directory)
    require(code == 0 and result['status'] == 'initialized' and 'revision' not in result, 'v1 status routed to v2')
    return {'status': result['status'], 'route': 'v1'}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True); args = parser.parse_args()
    checks = []
    with tempfile.TemporaryDirectory(prefix='engagement-public-cli-') as directory:
        for name in ['inspect', 'run-resume', 'stop-recovery', 'stop-owned', 'resume-owned', 'no-simulation-switch', 'v1-status']:
            root = Path(directory).resolve() / name; root.mkdir(mode=0o700)
            try: checks.append({'scenario': name, 'status': 'passed', 'result': legacy(root) if name == 'v1-status' else scenario(root, name)})
            except Exception as error: checks.append({'scenario': name, 'status': 'failed', 'error': str(error)})
    result = {'status': 'passed' if all(row['status'] == 'passed' for row in checks) else 'failed',
        'classification': 'public_cli_signed_fixture_real_runner_unavailable_native_boundary',
        'external_provider_calls': 0, 'target_calls': 0, 'docker_calls': 0, 'checks': checks,
        'unverified': ['complete native run with Docker', 'live provider behavior', 'research qualification']}
    args.output.write_text(json.dumps(result, indent=2) + '\n'); print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'passed' else 1

if __name__ == '__main__': raise SystemExit(main())
