#!/usr/bin/env python3
"""Failure-first public adapter workflow for a renewable long experiment.

Cases specified before implementation: renewed authority and owner outlive the
initial lease; expired authority or revocation stops before the requested command
deadline; the explicit command deadline still wins over renewal; an unrenewed
independent owner stops its container even while the controller grant stays valid.
The Docker CLI is an explicitly named simulation, with real local processes,
clocks, files, and the actual independent lease owner. No Docker/SSH proof follows.
"""
from __future__ import annotations

import argparse
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


def run_case(name):
    from research_environment import Environment
    with tempfile.TemporaryDirectory(prefix='renewed-execute-') as directory:
        root = Path(directory).resolve()
        docker = root / 'docker'
        command = '''
 if args[-1]=='long-experiment':
  (root/'execution-started').write_text(str(os.getpid()))
  until=time.monotonic()+2.6
  while time.monotonic()<until:
   if not read()['State']['Running']:
    print('OWNER_STOPPED');sys.exit(137)
   time.sleep(.02)
  (root/'execution-finished').touch();print('LONG_EXPERIMENT_FINISHED');sys.exit(0)
'''
        docker.write_text(FAKE_DOCKER.replace('PYTHON', sys.executable).replace(
            "elif args[:2]==['container','exec']:\n", "elif args[:2]==['container','exec']:\n" + command))
        docker.chmod(0o700)
        profile = {'kind': 'research-environment-profile-v2', 'transport': 'docker',
            'docker_binary': str(docker), 'docker_endpoint': 'unix:///fixture/docker.sock',
            'daemon_id': 'daemon-fixture', 'image_id': 'sha256:' + '1' * 64,
            'platform': 'linux/arm64', 'uid': 1000, 'gid': 1000, 'ssh': None}
        limits = {'memory_bytes': 64 * 1024 * 1024, 'workspace_bytes': 1024 * 1024,
            'cpu_count': 1, 'pids': 32, 'lease_seconds': 2, 'output_bytes': 4096}
        deadline, active, done = [time.monotonic() + 30], [True], threading.Event()
        events, renewed, errors = [], [], []

        def authorize():
            if not active[0]:
                raise RuntimeError('revoked')
            return {'seconds_remaining': deadline[0] - time.monotonic()}

        environment = Environment(profile, limits, authorize, events.append, dispatch_guard=nullcontext)
        application = {'id': 'app', 'kind': 'application',
            'identity': {'base_url': 'https://target.invalid/', 'version': None},
            'account_refs': [], 'permissions': ['read']}
        thread = None
        try:
            environment.prepare([application], {})
            initial = 1.2 if name == 'renewed' else (.5 if name == 'expired' else 30)
            deadline[0] = time.monotonic() + initial

            def renew():
                while not done.wait(.15):
                    try:
                        deadline[0] = time.monotonic() + 1.5
                        environment.renew(1.1)
                        renewed.append(time.monotonic())
                    except Exception as error:
                        if not done.is_set():
                            errors.append(type(error).__name__ + ': ' + str(error))
                        return

            def revoke():
                while not (root / 'execution-started').exists() and not done.wait(.01):
                    pass
                if not done.wait(.15):
                    active[0] = False

            if name in ('renewed', 'timeout'):
                thread = threading.Thread(target=renew, daemon=True)
            elif name == 'revoked':
                thread = threading.Thread(target=revoke, daemon=True)
            if thread:
                thread.start()
            started = time.monotonic()
            result = environment.execute(['long-experiment'], timeout_seconds=.45 if name == 'timeout' else 4)
            elapsed = time.monotonic() - started
            done.set()
            if thread:
                thread.join(timeout=2)
            finished = (root / 'execution-finished').exists()
            row = {'scenario': name, 'operation_status': result['status'], 'returncode': result['returncode'],
                'elapsed_seconds': round(elapsed, 3), 'owner_renewals': len(renewed),
                'command_finished': finished, 'environment_held': environment.held}
            if name == 'renewed':
                passed = (result['status'] == 'settled' and result['returncode'] == 0 and finished
                    and 'LONG_EXPERIMENT_FINISHED' in result['output'] and elapsed > initial
                    and len(renewed) >= 2 and not errors and environment.owner.readback()['running'])
            elif name == 'owner-expired':
                until = time.monotonic() + 1
                while environment.owner.readback()['running'] and time.monotonic() < until:
                    time.sleep(.02)
                passed = not finished and result['returncode'] != 0 and not environment.owner.readback()['running']
            else:
                passed = (result['status'] == 'unknown' and not finished and environment.held
                    and elapsed < 1.2 and not environment.commands)
            executions = [event for event in events if event['operation'] == 'execute']
            passed = passed and len(executions) == 2 and executions[0]['phase'] == 'intent' and executions[1]['phase'] == 'result'
            row['status'] = 'passed' if passed else 'failed'
            row['renewal_errors'] = errors
            return row
        finally:
            done.set()
            if thread:
                thread.join(timeout=2)
            environment.cleanup()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = {'classification': 'simulated_docker_cli_with_actual_process_lease_owner',
        'scenarios': [], 'unverified': ['Docker execution', 'SSH execution', 'research qualification']}
    for name in ('renewed', 'expired', 'revoked', 'timeout', 'owner-expired'):
        try:
            report['scenarios'].append(run_case(name))
        except Exception as error:
            report['scenarios'].append({'scenario': name, 'status': 'failed',
                'error': type(error).__name__ + ': ' + str(error)})
    report['status'] = 'passed' if all(row['status'] == 'passed' for row in report['scenarios']) else 'failed'
    report['source_sha256'] = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (Path(__file__), ROOT / 'tools/research_environment.py', ROOT / 'tools/engagement_lease_owner.py')}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'scenarios': len(report['scenarios']), 'output': str(args.output)}))
    return report['status'] != 'passed'


if __name__ == '__main__':
    raise SystemExit(main())
