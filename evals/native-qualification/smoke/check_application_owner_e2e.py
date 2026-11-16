#!/usr/bin/env python3
"""Owned counter and actual stdio connector; Docker lifecycle is simulated.

Run with Python 3 and --output FILE. No provider, Docker daemon, external target
or download is used. Expected: fresh owners read 0, mutation reads 1, wrong
origins/changed profiles/revocation fail, and every owned process exits.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import hashlib
import http.client
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))

COUNTER = '''import http.server,sys
class Counter(http.server.BaseHTTPRequestHandler):
    value=0
    def do_GET(self):
        if self.path=="/increment":Counter.value+=1
        value=str(Counter.value).encode()
        self.send_response(200);self.send_header("Content-Length",str(len(value)));self.end_headers();self.wfile.write(value)
    def log_message(self,*args):pass
print("reset complete (untrusted stdout)",flush=True)
http.server.HTTPServer(("127.0.0.1",int(sys.argv[1])),Counter).serve_forever()
'''


class OwnedHttpEnvironment:
    """Explicit test peer; only application and fixed connector run for real."""
    instances = []

    def __init__(self, profile, limits, authorize, observe, *, grant=None, dispatch_guard=None,
                 receipt=None, **options):
        from engagement_contract import digest, canonical
        self.profile, self.limits, self.authorize, self.observe = profile, limits, authorize, observe
        self.guard = dispatch_guard
        self.identity = receipt or {'kind': 'research-environment-receipt-v2', 'nonce': uuid.uuid4().hex,
            'container_id': uuid.uuid4().hex * 2, 'profile_sha256': digest(canonical(profile)),
            'daemon_id': profile['daemon_id'], 'image_id': profile['image_id']}
        self.processes, self.staged = [], {}
        self.status = 'absent' if receipt else 'unprepared'
        self.__class__.instances.append(self)

    def receipt(self): return dict(self.identity)

    def prepare(self, accesses, access_files, *, support_inputs=None):
        assert len(accesses) == 1 and accesses[0]['kind'] == 'application' and not access_files, 'target must not inherit client files'
        self.authorize(); self.staged = support_inputs; self.status = 'running'
        return {'status': 'ready', 'identity': self.receipt()}

    def launch_stdio(self, argv, *, role='native_tools'):
        assert role in ('application', 'application_connector')
        self.authorize()
        mapped = []
        for value in argv:
            if value.startswith('/input/'):
                _, _, name, *relative = value.split('/')
                value = str(Path(self.staged[name]['path']).joinpath(*relative))
            mapped.append(value)
        process = subprocess.Popen(mapped, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, start_new_session=True)
        self.processes.append(process)
        return process

    def readback(self): return {'status': self.status, 'identity': self.receipt()}
    def renew(self, seconds=None): self.authorize(); return {'status': 'renewal_sent'}

    def cleanup(self):
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=2)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=2)
            for stream in (process.stdin, process.stdout):
                if stream is not None and not stream.closed: stream.close()
        self.status = 'absent'
        return {'status': 'clean', 'identity': self.receipt(), 'owned_workspace': 'container_removed'}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scenario', choices=('all', 'timeout', 'cleanup'), default='all')
    args = parser.parse_args()
    result = {'kind': 'owned-application-counter-e2e-v1',
        'classification': 'actual_http_and_stdio_with_simulated_container_owner', 'checks': [],
        'unverified': ['Docker isolation', 'SSH transport', 'joined native model workflow', 'research outcome']}
    def check(name, condition):
        result['checks'].append({'name': name, 'passed': bool(condition)})
        assert condition, name
    try:
        import application_state as module
        from engagement_contract import canonical, digest, source_manifest
        from engagement_network import NetworkGate
        original = module.Environment; module.Environment = OwnedHttpEnvironment
        with tempfile.TemporaryDirectory(prefix='application-owner-') as folder:
            path = Path(folder).resolve(); bootstrap = path / 'bootstrap'; bootstrap.mkdir()
            (bootstrap / 'bridge.py').write_bytes((ROOT / 'tools/engagement_network_bridge.py').read_bytes())
            counter = path / 'counter.py'; counter.write_text(COUNTER)
            bound = socket.socket(); bound.bind(('127.0.0.1', 0)); port = bound.getsockname()[1]; bound.close()
            origin = f'http://owned-counter.invalid:{port}'
            access = {'id': 'app-main', 'kind': 'application', 'permissions': ['read', 'reset'],
                'account_refs': [], 'identity': {'base_url': origin + '/', 'version': 'counter-v1'}}
            profile = {'kind': 'owned-application-state-v1', 'method': 'owned-container-recreate-v1',
                'baseline_id': 'counter-zero', 'command': [sys.executable, str(counter), str(port)], 'service_port': port}
            environment = {'kind': 'research-environment-profile-v2', 'transport': 'docker',
                'docker_binary': '/fixture/docker', 'docker_endpoint': 'unix:///fixture/docker.sock',
                'daemon_id': 'fixture-daemon', 'image_id': 'sha256:' + '1' * 64,
                'platform': 'linux/arm64', 'uid': 1000, 'gid': 1000, 'ssh': None}
            limits = {'memory_bytes': 64 * 1024 ** 2, 'workspace_bytes': 1024 ** 2, 'cpu_count': 1,
                'pids': 32, 'lease_seconds': 10, 'output_bytes': 4096}
            support = {'application-connector': {'path': str(bootstrap), 'manifest_sha256': digest(canonical(source_manifest(bootstrap)))}}
            active = [True]; events = []
            def authorize():
                if not active[0]: raise RuntimeError('revoked')
                return {'dispatch_id': 'capture-1', 'seconds_remaining': 10, 'resources': ['app-main']}
            def owner(p=profile, a=access):
                return module.ApplicationOwner(p, a, environment, limits, authorize, events.append,
                    grant=authorize(), dispatch_guard=nullcontext, bootstrap=support)
            for changed in ({**profile, 'service_port': port + 1}, {**profile, 'command': ['relative']},
                            {**profile, 'method': 'script-success-marker'}):
                try: owner(changed)
                except Exception: pass
                else: raise AssertionError('invalid profile accepted')
            bad = {**access, 'identity': {**access['identity'], 'base_url': f'http://production.example:{port}/'}}
            try: owner(a=bad)
            except Exception: pass
            else: raise AssertionError('remote masquerade accepted')
            check('invalid profiles and public origins have no target effects', not OwnedHttpEnvironment.instances)
            first = owner()
            try: first.reset('changed-baseline')
            except Exception: pass
            else: raise AssertionError('changed baseline accepted')
            check('changed baseline has no preparation effect', first.environment.status == 'unprepared')
            receipt = first.reset('counter-zero')
            check('start receipt binds exact owner and signed baseline', receipt['baseline_id'] == 'counter-zero'
                and receipt['target_nonce'] == first.environment.receipt()['nonce']
                and receipt['container_id'] == first.environment.receipt()['container_id'])
            routes = [{'protocol': 'http', 'host': 'owned-counter.invalid', 'port': port,
                'address_policy': {'public_only': False, 'cidrs': ['127.0.0.1/32']}}]
            gate = NetworkGate(routes, lambda: active[0], dispatch_guard=nullcontext,
                target_connectors={origin: first.connect})
            check('actual private connector reads fresh baseline', gate.fetch(origin + '/')['body'] == b'0')
            check('actual request mutates only owned target', gate.fetch(origin + '/increment')['body'] == b'1')
            for wrong in (f'http://elsewhere.invalid:{port}', f'https://owned-counter.invalid:{port}',
                          f'http://owned-counter.invalid:{port+1}'):
                try: first.connect(wrong)
                except Exception: pass
                else: raise AssertionError('wrong origin connected')
            check('fixed connector rejects host scheme and port substitution', True)
            try: first.reset('counter-zero')
            except Exception: pass
            else: raise AssertionError('owner reset reused a generation')
            check('one owner cannot mint a second reset epoch', True)
            active[0] = False
            try: first.connect(origin)
            except Exception: pass
            else: raise AssertionError('revoked connection admitted')
            check('revocation prevents new connections', True)
            gate.close(); cleaned = first.cleanup()
            check('cleanup remains possible after revocation', cleaned['status'] == 'clean')
            active[0] = True
            second = owner(); replay = second.reset('counter-zero')
            gate = NetworkGate(routes, lambda: active[0], dispatch_guard=nullcontext,
                target_connectors={origin: second.connect})
            check('independent generation returns same baseline', replay['target_nonce'] != receipt['target_nonce']
                and replay['container_id'] != receipt['container_id'] and gate.fetch(origin + '/')['body'] == b'0')
            gate.close(); second.cleanup()
            check('all owned processes exited', all(p.poll() is not None for env in OwnedHttpEnvironment.instances for p in env.processes))
            if args.scenario in ('all', 'timeout'):
                silent = COUNTER.replace('import http.server,sys', 'import http.server,sys,time').replace(
                    '    def do_GET(self):', '    def do_GET(self):\n        time.sleep(30)')
                waiting = owner({**profile, 'command': [sys.executable, '-c', silent, str(port)]})
                waiting.reset('counter-zero')
                gate = NetworkGate(routes, lambda: active[0], dispatch_guard=nullcontext,
                    target_connectors={origin: waiting.connect})
                done = threading.Event(); failures = []
                def fetch_silent():
                    try: gate.fetch(origin + '/')
                    except Exception as error: failures.append(type(error).__name__)
                    finally: done.set()
                worker = threading.Thread(target=fetch_silent, daemon=True)
                started = time.monotonic(); worker.start()
                bounded = done.wait(6)
                elapsed = time.monotonic() - started
                gate.close(); worker.join(2); waiting.cleanup()
                result['silent_response'] = {'elapsed_seconds': elapsed, 'finished_before_gate_close': bounded, 'errors': failures}
                check('silent owned target has the same finite response deadline', bounded and elapsed < 6 and failures == ['TimeoutError'])
            if args.scenario in ('all', 'cleanup'):
                damaged = owner(); damaged.reset('counter-zero')
                close = damaged.bridge.close
                def failed_close(): raise OSError('injected connector close failure')
                damaged.bridge.close = failed_close
                failure = None
                try: damaged.cleanup()
                except Exception as error: failure = type(error).__name__
                finally:
                    damaged.bridge.close = close; close()
                result['connector_close_failure'] = {'error': failure, 'target_status': damaged.environment.status}
                check('connector failure still cleans exact target and remains an error',
                    failure is not None and damaged.environment.status == 'absent'
                    and all(process.poll() is not None for process in damaged.environment.processes))
        module.Environment = original
        result['status'] = 'passed'
    except Exception as error:
        result['status'] = 'failed'; result['error'] = type(error).__name__ + ': ' + str(error)
    finally:
        for environment in OwnedHttpEnvironment.instances:
            environment.cleanup()
    result['source_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'checks': len(result['checks']), 'output': str(args.output)}))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__': raise SystemExit(main())
