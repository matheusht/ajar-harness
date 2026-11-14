#!/usr/bin/env python3
"""Actual owned-counter reset, fixed private routing and exact Docker cleanup.

Opt-in only: --endpoint unix://... --image-id sha256:... --output FILE. The image
must already exist and contain /usr/local/bin/python3. No pull, model provider,
external application, existing container reset or Docker configuration change.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'tools'), str(Path(__file__).parent)]
from check_application_owner_e2e import COUNTER


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint', required=True)
    parser.add_argument('--image-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = {'kind': 'application-owner-docker-e2e-v1', 'classification': 'actual_docker_owned_counter',
        'checks': [], 'observations': [], 'provider_calls': 0, 'external_target_calls': 0,
        'unverified': ['SSH transport', 'joined native model and journal workflow', 'research acceptance']}
    owners, gates = [], []
    def check(name, passed):
        result['checks'].append({'name': name, 'passed': bool(passed)})
        assert passed, name
    try:
        from application_state import ApplicationOwner
        from engagement_contract import canonical, digest, source_manifest
        from engagement_network import NetworkGate
        from research_environment import Environment
        docker = shutil.which('docker')
        if docker is None or not args.endpoint.startswith('unix:///'):
            raise ValueError('explicit_docker_endpoint_required')
        def call(*arguments, required=True):
            observed = subprocess.run([docker, '--host', args.endpoint, *arguments], capture_output=True, timeout=10)
            if required and observed.returncode:
                raise ValueError('owned_fixture_docker_command_failed')
            return observed
        daemon = call('info', '--format', '{{.ID}}').stdout.decode().strip()
        image, = json.loads(call('image', 'inspect', args.image_id).stdout)
        check('supplied baseline is an exact installed Linux image', image['Id'] == args.image_id and image['Os'] == 'linux')
        existing = set(call('container', 'ls', '--all', '--quiet', '--no-trunc').stdout.split())
        environment = {'kind': 'research-environment-profile-v2', 'transport': 'docker',
            'docker_binary': docker, 'docker_endpoint': args.endpoint, 'daemon_id': daemon,
            'image_id': args.image_id, 'platform': image['Os'] + '/' + image['Architecture'],
            'uid': 1000, 'gid': 1000, 'ssh': None}
        limits = {'memory_bytes': 128 * 1024 ** 2, 'workspace_bytes': 8 * 1024 ** 2,
            'cpu_count': 1, 'pids': 32, 'lease_seconds': 60, 'output_bytes': 8192}
        profile = {'kind': 'owned-application-state-v1', 'method': 'owned-container-recreate-v1',
            'baseline_id': 'counter-zero', 'command': ['/usr/local/bin/python3', '-I', '-S', '-c', COUNTER, '8123'],
            'service_port': 8123}
        origin = 'http://owned-counter.invalid:8123'
        access = {'id': 'app-main', 'kind': 'application', 'identity': {'base_url': origin + '/', 'version': 'counter-v1'},
            'account_refs': [], 'permissions': ['read', 'reset']}
        routes = [{'protocol': 'http', 'host': 'owned-counter.invalid', 'port': 8123,
            'address_policy': {'public_only': False, 'cidrs': ['127.0.0.1/32']}}]
        active = [True]; deadline = time.monotonic() + 120
        def authorize():
            if not active[0] or time.monotonic() >= deadline: raise ValueError('fixture_grant_inactive')
            return {'seconds_remaining': min(60, deadline - time.monotonic())}
        with tempfile.TemporaryDirectory(prefix='owned-application-docker-') as name:
            folder = Path(name).resolve(); helper = folder / 'helper'; helper.mkdir()
            (helper / 'bridge.py').write_bytes((ROOT / 'tools/engagement_network_bridge.py').read_bytes())
            support = {'application-connector': {'path': str(helper), 'manifest_sha256': digest(canonical(source_manifest(helper)))}}
            def create():
                owner = ApplicationOwner(profile, access, environment, limits, authorize, result['observations'].append,
                    grant=authorize(), dispatch_guard=nullcontext, bootstrap=support)
                owners.append(owner)
                receipt = owner.reset('counter-zero')
                gate = NetworkGate(routes, lambda: active[0], dispatch_guard=nullcontext,
                    target_connectors={origin: owner.connect}); gates.append(gate)
                return owner, receipt, gate
            first, start, gate = create()
            info, = json.loads(call('container', 'inspect', start['container_id']).stdout)
            check('actual target is isolated with no persistent state or published port',
                info['HostConfig']['NetworkMode'] == 'none' and info['HostConfig']['ReadonlyRootfs']
                and not info['HostConfig'].get('Binds') and not info['Mounts'] and not info['HostConfig'].get('PortBindings'))
            observed = [gate.fetch(origin + suffix)['body'].decode() for suffix in ('/', '/increment', '/')]
            check('private connector observes baseline and actual mutation', observed == ['0', '1', '1'])
            result['first'] = {'receipt': start, 'counter_observations': observed}
            before = first.environment.receipt()
            try: first.connect('http://different.invalid:8123')
            except Exception: pass
            else: raise AssertionError('wrong target origin accepted')
            check('wrong-origin attempt preserved exact target identity', first.environment.receipt() == before)
            gate.close(); first.cleanup()
            check('first exact target and derived image are absent',
                call('container', 'inspect', start['container_id'], required=False).returncode != 0
                and call('image', 'inspect', before['prepared_image_id'], required=False).returncode != 0)
            second, replay, gate = create()
            check('recreation reaches baseline in a distinct actual container',
                replay['container_id'] != start['container_id'] and replay['target_nonce'] != start['target_nonce']
                and gate.fetch(origin + '/')['body'] == b'0')
            result['replay'] = replay
            active[0] = False
            try: second.connect(origin)
            except Exception: pass
            else: raise AssertionError('revoked target connection accepted')
            gate.close()
            receipt = second.environment.receipt()
            recovered = Environment(environment, limits, authorize, result['observations'].append,
                dispatch_guard=nullcontext, receipt=receipt)
            readback = recovered.cleanup()
            check('recovery cleans exact target after authority ends', readback['status'] == 'clean')
            result['recovery'] = readback
            second.cleanup()
            remaining = set(call('container', 'ls', '--all', '--quiet', '--no-trunc').stdout.split())
            check('all preexisting containers and supplied base image remain', existing <= remaining
                and call('image', 'inspect', args.image_id, required=False).returncode == 0)
            check('all owned containers are absent', all(not call('container', 'ls', '--all', '--quiet',
                '--filter', 'label=io.oslit.engagement=' + owner.environment.receipt()['nonce']).stdout.strip() for owner in owners))
        result['status'] = 'passed'
    except Exception as error:
        result['status'] = 'failed'; result['error'] = type(error).__name__ + ': ' + str(error)
    finally:
        for gate in gates:
            gate.close()
        result['cleanup'] = []
        for owner in owners:
            try: result['cleanup'].append(owner.cleanup())
            except Exception as error:
                result['status'] = 'failed'
                result['cleanup'].append({'status': 'unresolved', 'code': getattr(error, 'code', type(error).__name__)})
        result['source_sha256'] = {name: 'sha256:' + hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in (
            'tools/application_state.py', 'tools/engagement_network_bridge.py', 'tools/engagement_network.py',
            'tools/research_environment.py', 'tools/engagement_lease_owner.py',
            'evals/native-qualification/smoke/check_application_owner_e2e.py',
            'evals/native-qualification/smoke/check_application_owner_docker_e2e.py')}
        args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'checks': len(result['checks']), 'output': str(args.output)}))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__': raise SystemExit(main())
