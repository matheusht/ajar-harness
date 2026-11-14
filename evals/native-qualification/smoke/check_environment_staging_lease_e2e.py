#!/usr/bin/env python3
"""Failure-first preparation workflow: simulated Docker CLI, actual timed processes."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
from check_environment_transport_e2e import FAKE_DOCKER
from research_environment import Environment, EnvironmentUnavailable

DELAY = r'''
operation = None
if args[:2] == ['container', 'create']:
 operation = 'create_stage' if get('--name').endswith('-stage') else 'create'
elif args[:3] == ['container', 'cp', '-']: operation = 'stage_input'
elif args[:2] == ['container', 'commit']: operation = 'snapshot_input'
elif args[:2] == ['image', 'inspect']: operation = 'metadata'
elif args[:2] == ['container', 'rm'] and args[-1] == 'a' * 64: operation = 'cleanup'
configuration = json.loads((root/'delay.json').read_text()) if (root/'delay.json').exists() else {}
if operation is not None and operation == configuration.get('operation'):
 (root/'started').write_text(str(os.getpid()))
 if configuration.get('overflow'):
  sys.stdout.buffer.write(b'x' * (4 * 1024 * 1024 + 1));sys.stdout.buffer.flush()
 time.sleep(5.25)
 (root/'completed').touch()
'''


def run_case(name):
    with tempfile.TemporaryDirectory(prefix='staging-lease-') as directory:
        root = Path(directory).resolve()
        docker = root / 'docker'
        docker.write_text(FAKE_DOCKER.replace('PYTHON', sys.executable).replace(
            "if args[:1]==['info']:", DELAY + "\nif args[:1]==['info']:"))
        docker.chmod(0o700)
        profile = {'kind': 'research-environment-profile-v2', 'transport': 'docker',
            'docker_binary': str(docker), 'docker_endpoint': 'unix:///fixture/docker.sock',
            'daemon_id': 'daemon-fixture', 'image_id': 'sha256:' + '1' * 64,
            'platform': 'linux/arm64', 'uid': 1000, 'gid': 1000, 'ssh': None}
        limits = {'memory_bytes': 64 * 1024 * 1024, 'workspace_bytes': 1024 * 1024,
            'cpu_count': 1, 'pids': 32, 'lease_seconds': 20, 'output_bytes': 4096}
        active, deadline, done, events = [True], [time.monotonic() + 20], threading.Event(), []
        def authorize():
            if not active[0]:raise RuntimeError('revoked')
            return {'seconds_remaining': deadline[0] - time.monotonic()}
        environment = Environment(profile, limits, authorize, events.append, dispatch_guard=nullcontext)
        binary = root / 'source';binary.write_bytes(b'unchanged harmless input')
        access = {'id': 'input', 'kind': 'binary', 'identity': {
            'sha256': 'sha256:' + hashlib.sha256(binary.read_bytes()).hexdigest(), 'platform': 'linux/arm64'},
            'account_refs': [], 'permissions': ['read', 'execute']}
        operation = name if name in ('create_stage', 'stage_input', 'snapshot_input', 'create', 'metadata', 'cleanup') else 'snapshot_input'
        config = root / 'delay.json'
        thread = None
        row = {'scenario': name, 'delayed_operation': operation, 'events': []}
        def stop():
            while not (root / 'started').exists() and not done.wait(.01):pass
            if done.wait(.15):return
            if name == 'revoked':active[0] = False
            else:deadline[0] = time.monotonic() + .15
        try:
            if name == 'cleanup':environment.prepare([access], {'input': str(binary)})
            config.write_text(json.dumps({'operation': operation, 'overflow': name == 'output-cap'}))
            if name in ('revoked', 'expired'):
                thread = threading.Thread(target=stop, daemon=True);thread.start()
            started = time.monotonic()
            error = None
            try:
                if name == 'metadata':
                    value = environment._run(['image', 'inspect', profile['image_id']])
                elif name == 'cleanup':value = environment.cleanup()
                else:value = environment.prepare([access], {'input': str(binary)})
            except EnvironmentUnavailable as failure:
                error = failure.code;value = None
            elapsed = time.monotonic() - started
            done.set()
            if thread:thread.join(timeout=2)
            observed = [event for event in events if event['operation'] == ('remove' if name == 'cleanup' else operation)]
            outcome = next((event for event in reversed(observed) if event['phase'] == 'result'), None)
            row.update(elapsed_seconds=round(elapsed, 3), error=error, events=observed,
                       client_completed=(root / 'completed').exists(), grant_remaining=round(deadline[0] - time.monotonic(), 3))
            if name in ('create_stage', 'stage_input', 'snapshot_input', 'create'):
                assert error is None and value['status'] == 'ready' and row['client_completed']
                assert outcome['status'] == 'settled' and outcome['returncode'] == 0 and elapsed > 5
                assert row['grant_remaining'] > 0
            elif name == 'metadata':
                assert error is None and value['status'] == 'unknown' and value['returncode'] == -9
                assert 4.9 < elapsed < 7 and not row['client_completed']
            else:
                assert error is not None and outcome['status'] == 'unknown' and outcome['returncode'] == -9
                assert not row['client_completed'] and not environment.commands
                if name == 'cleanup':assert 4.9 < elapsed < 8
                else:assert environment.held and elapsed < 4
            assert binary.read_bytes() == b'unchanged harmless input'
            row['status'] = 'passed'
        except Exception as failure:
            row.update(status='failed', assertion=type(failure).__name__)
        finally:
            done.set()
            if thread:thread.join(timeout=2)
            config.unlink(missing_ok=True)
            try:row['cleanup'] = environment.cleanup()['status']
            except Exception as failure:row['cleanup'] = getattr(failure, 'code', type(failure).__name__)
        return row


def main():
    p = argparse.ArgumentParser(description=__doc__);p.add_argument('--output', type=Path, required=True);args = p.parse_args()
    cases = ('create_stage', 'stage_input', 'snapshot_input', 'create', 'revoked', 'expired', 'output-cap', 'metadata', 'cleanup')
    with ThreadPoolExecutor(max_workers=4) as pool:rows = list(pool.map(run_case, cases))
    result = {'classification': 'simulated_docker_cli_with_actual_inert_delays_and_local_lease_owner',
        'status': 'passed' if all(row['status'] == 'passed' for row in rows) else 'failed', 'cases': rows,
        'docker': 'not_run', 'native_runtime': 'not_run', 'provider_calls': 0,
        'source_sha256': {str(path.relative_to(ROOT)): 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (Path(__file__), ROOT / 'tools/research_environment.py')}}
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'cases': [{k: row.get(k) for k in ('scenario', 'status', 'error', 'elapsed_seconds')} for row in rows]}))
    return result['status'] != 'passed'


if __name__ == '__main__':raise SystemExit(main())
