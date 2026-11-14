#!/usr/bin/env python3
"""Exercise the production owned environment against an explicitly selected Docker daemon."""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'tools'))

PROBE = r'''import json,os,socket,subprocess
from pathlib import Path
checks={}
checks['unprivileged']=os.getuid()==1000 and os.getgid()==1000
for name,path in [('input','/input/source/probe.py'),('root','/etc/oslit-fixture')]:
    try:
        with open(path,'ab') as stream:stream.write(b'forbidden')
    except OSError:checks[name+'_readonly']=True
    else:checks[name+'_readonly']=False
checks['no_admin_socket']=not Path('/var/run/docker.sock').exists()
checks['no_network_interface']=set(os.listdir('/sys/class/net'))=={'lo'}
with socket.socket() as connection:
    connection.settimeout(.5)
    checks['host_loopback_unreachable']=connection.connect_ex(('127.0.0.1',int(os.environ['OSLIT_FIXTURE_PORT'])))!=0
checks['no_new_privileges']='NoNewPrivs:\t1' in Path('/proc/self/status').read_text()
checks['capabilities_dropped']='CapEff:\t0000000000000000' in Path('/proc/self/status').read_text()
Path('/work/result.json').write_text(json.dumps(checks,sort_keys=True)+'\n')
child=subprocess.Popen(['/usr/local/bin/python3','-c','import time;time.sleep(45)'],
    stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
print(json.dumps({'checks':checks,'background_pid':child.pid},sort_keys=True))
assert all(checks.values()),checks
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint', required=True, help='Explicit unix:// Docker endpoint; never uses the default context')
    parser.add_argument('--image-id', required=True, help='Already installed sha256 image ID with /bin/sh and /usr/local/bin/python3')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = {'kind': 'environment-real-docker-e2e-v2', 'classification': 'actual_docker_environment',
              'checks': [], 'observations': [], 'provider_calls': 0, 'external_target_calls': 0,
              'unverified': ['SSH transport', 'native model host', 'joined controller workflow', 'research acceptance']}
    environments = []

    def check(name, value):
        result['checks'].append({'name': name, 'passed': bool(value)})
        assert value, name

    try:
        from engagement_contract import canonical, source_manifest
        from research_environment import Environment, EnvironmentUnavailable
        docker = shutil.which('docker')
        if not docker or not args.endpoint.startswith('unix://'):
            raise RuntimeError('explicit_local_docker_unavailable')

        def call(*arguments, required=True):
            response = subprocess.run([docker, '--host', args.endpoint, *arguments],
                                      capture_output=True, text=True, timeout=10)
            if required and response.returncode:
                raise RuntimeError('docker_fixture_command_failed:' + arguments[0])
            return response

        daemon = call('info', '--format', '{{.ID}}').stdout.strip()
        image, = json.loads(call('image', 'inspect', args.image_id).stdout)
        check('image is an exact Linux content identity', image['Id'] == args.image_id and image['Os'] == 'linux')
        result['environment'] = {'daemon_id': daemon, 'image_id': image['Id'],
                                 'image_digests': image.get('RepoDigests', []),
                                 'platform': image['Os'] + '/' + image['Architecture'],
                                 'docker_version': json.loads(call('version', '--format', '{{json .}}').stdout)}
        existing = set(call('container', 'ls', '--all', '--quiet', '--no-trunc').stdout.split())
        profile = {'kind': 'research-environment-profile-v2', 'transport': 'docker',
                   'docker_binary': docker, 'docker_endpoint': args.endpoint, 'daemon_id': daemon,
                   'image_id': image['Id'], 'platform': result['environment']['platform'],
                   'uid': 1000, 'gid': 1000, 'ssh': None}
        limits = {'memory_bytes': 256 * 1024 * 1024, 'workspace_bytes': 16 * 1024 * 1024,
                  'cpu_count': 1, 'pids': 32, 'lease_seconds': 60, 'output_bytes': 32768}
        active = [False]
        deadline = [time.monotonic() + 60]
        events = result['observations']

        def authorize():
            if not active[0] or time.monotonic() >= deadline[0]:
                raise RuntimeError('fixture_grant_revoked')
            return {'seconds_remaining': deadline[0] - time.monotonic()}

        def owned(receipt=None):
            value = Environment(profile, limits, authorize, events.append,
                                dispatch_guard=nullcontext, receipt=receipt)
            environments.append(value)
            return value

        with tempfile.TemporaryDirectory(prefix='oslit-real-docker-') as folder, socket.socket() as listener:
            root = Path(folder)
            source = root / 'source'; source.mkdir()
            (source / 'probe.py').write_text(PROBE)
            manifest = source_manifest(source)
            access = {'id': 'source', 'kind': 'source', 'account_refs': [], 'permissions': ['read', 'execute'],
                      'identity': {'manifest_sha256': 'sha256:' + hashlib.sha256(canonical(manifest)).hexdigest()}}
            environment = owned()
            try:
                environment.prepare([access], {'source': str(source)})
            except EnvironmentUnavailable:
                pass
            else:
                raise AssertionError('revoked preparation was dispatched')
            check('no authorization creates no container',
                  not call('container', 'ls', '--all', '--quiet', '--filter',
                           'label=io.oslit.engagement=' + environment.identity['nonce']).stdout.strip())
            active[0] = True
            prepared = environment.prepare([access], {'source': str(source)})
            check('production staging starts the exact owned environment', prepared['status'] == 'ready')
            identity = environment.receipt()
            result['owned_identity'] = identity
            info, = json.loads(call('container', 'inspect', identity['container_id']).stdout)
            config = info['HostConfig']
            check('actual container has bounded immutable configuration',
                  config['NetworkMode'] == 'none' and config['ReadonlyRootfs']
                  and config['Memory'] == limits['memory_bytes'] and config['MemorySwap'] == limits['memory_bytes']
                  and config['PidsLimit'] == limits['pids'] and config['NanoCpus'] == 1000000000
                  and not config['Privileged'] and not config.get('Binds') and not config.get('PortBindings'))
            listener.bind(('127.0.0.1', 0)); listener.listen(1)
            port = listener.getsockname()[1]
            executed = environment.execute(['/usr/bin/env', 'OSLIT_FIXTURE_PORT=' + str(port),
                                             '/usr/local/bin/python3', '/input/source/probe.py'], timeout_seconds=10)
            check('actual probe completes inside the production environment',
                  executed['status'] == 'settled' and executed['returncode'] == 0)
            probe = json.loads(executed['output'])
            for name, passed in probe['checks'].items():
                check(name, passed)
            artifact = environment.read_artifact('result.json', 8192)
            check('published bytes come from the actual worker filesystem',
                  json.loads(artifact['content']) == probe['checks']
                  and artifact['output_sha256'] == 'sha256:' + hashlib.sha256(artifact['content']).hexdigest())
            check('input staging preserves the supplied source', source_manifest(source) == manifest)
            processes = call('container', 'top', identity['container_id'], '-eo', 'args').stdout
            check('detached child exists before revocation', 'time.sleep(45)' in processes)
            active[0] = False
            try:
                environment.execute(['/bin/true'], timeout_seconds=1)
            except EnvironmentUnavailable:
                pass
            else:
                raise AssertionError('revoked execution was dispatched')
            check('revocation stops the container and its detached child',
                  environment.revoke()['status'] == 'stopped'
                  and call('container', 'top', identity['container_id'], required=False).returncode != 0)
            recovered = owned(environment.receipt())
            check('receipt-based recovery observes exact resource cleanup', recovered.cleanup()['status'] == 'clean')
            remaining = set(call('container', 'ls', '--all', '--quiet', '--no-trunc').stdout.split())
            check('owned cleanup preserves all preexisting containers', existing <= remaining)
            check('owned container and staging container are absent',
                  not call('container', 'ls', '--all', '--quiet', '--filter',
                           'label=io.oslit.engagement=' + identity['nonce']).stdout.strip())
            check('owned prepared image is absent and the base image remains',
                  call('image', 'inspect', identity['prepared_image_id'], required=False).returncode != 0
                  and call('image', 'inspect', image['Id'], required=False).returncode == 0)
        result['status'] = 'passed'
    except Exception as error:
        result['status'] = 'failed'
        result['error'] = type(error).__name__ + ': ' + str(error)
    finally:
        cleanup = []
        for environment in reversed(environments):
            try:
                cleanup.append(environment.cleanup())
            except Exception as error:
                cleanup.append({'status': 'unresolved', 'code': type(error).__name__ + ': ' + str(error),
                                'identity': environment.receipt()})
                result['status'] = 'failed'
        result['cleanup'] = cleanup
        result['source_sha256'] = {str(path.relative_to(REPO)): 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (Path(__file__).resolve(), REPO / 'tools/research_environment.py',
                         REPO / 'tools/engagement_lease_owner.py', REPO / 'tools/engagement_workspace.py')}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'checks': len(result['checks']), 'output': str(args.output)}))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
