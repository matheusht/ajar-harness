#!/usr/bin/env python3
"""Provider-free native-boundary workflow checks with explicit adapter simulations.

Runs real signed-input/controller/object workflows and local certificate/network
checks. No model provider, Docker daemon, SSH host or research target is contacted.
The fake native/environment peers establish orchestration only, never containment.
"""
from __future__ import annotations

import argparse
import base64
import copy
import importlib.util
import json
import os
import subprocess
import socket
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
from unittest.mock import patch
from contextlib import ExitStack

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
from engagement_contract import canonical, digest
from engagement_controller import ControllerError
from engagement_runner import WorkerContext, frozen_inputs
from native_runtime_codex import Runtime as CodexRuntime
from native_runtime_omp import Runtime as OMPRuntime

spec = importlib.util.spec_from_file_location('boundary_fixture', Path(__file__).with_name('check_engagement_evidence_e2e.py'))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def require(value, text):
    if not value:
        raise AssertionError(text)


def refused(code, call):
    try:
        call()
    except Exception as error:
        require(getattr(error, 'code', str(error)) == code, f'{getattr(error, "code", str(error))} != {code}')
    else:
        raise AssertionError('accepted forbidden operation: ' + code)


def patch_readonly(path):
    x = fixture.Case(path, patch=True)
    x.publication('contrary'); x.instrument(); x.experiment('effect')
    x.experiment('control', purpose='control', explains={'experiment_id': 'effect', 'variable': 'fixture-switch'})
    x.claim()
    diff = x.c.store_object(b'--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-print("harmless fixture ready")\n+print("harmless patched fixture ready")\n')
    x.request('patch_propose', {'patch_id': 'patch-1', 'claim_id': 'claim-1',
        'source_access': 'source-main', 'diff_sha256': diff, 'supersedes': []})
    patch = x.c.state()['patches']['patch-1']
    logical = json.loads(x.c.read_object(patch['patched_manifest_sha256']))
    readonly = {name: dict(row, mode=0o555 if row['mode'] & 0o111 else 0o444) for name, row in logical.items()}
    grant = x.grant(resources=['source-main'])
    x.observe(grant, 'patch-executed', 'a' * 32)
    x.settle(grant)
    x.c.record_patch_execution(grant, 'lab-main', 'patch-executed', 'patch-1', 'patched', readonly)
    require(x.c.state()['environment_operations']['patch-executed']['patch_copy']['patch_id'] == 'patch-1',
        'normalized immutable copy was not bound')
    bad = copy.deepcopy(readonly)
    bad[next(iter(bad))]['sha256'] = 'sha256:' + '0' * 64
    refused('patch_copy_mismatch', lambda: x.c.record_patch_execution(grant, 'lab-main',
        'patch-executed', 'patch-1', 'patched', bad))


class SimulatedEnvironment:
    instances = []
    cleanup_fails = False
    native_files = {}
    reads = 0

    def __init__(self, profile, limits, authorize, observe, **options):
        self.profile, self.limits, self.authorize, self.observe = profile, limits, authorize, observe
        self.options = options
        self.grant = options.get('grant')
        self.identity = copy.deepcopy(options.get('receipt'))
        self.running = False
        self.renewals = []
        self.staged = None
        self.__class__.instances.append(self)

    def prepare(self, accesses, access_files, *, support_inputs):
        self.staged = copy.deepcopy(support_inputs)
        self.access_files = access_files
        nonce = f'{len(self.__class__.instances):032x}'
        self.identity = {'kind': 'research-environment-receipt-v2', 'nonce': nonce,
            'container_id': 'a' * 64, 'container_name': 'oslit-' + nonce,
            'stage_container_id': None, 'stage_container_name': 'oslit-' + nonce + '-stage',
            'prepared_image_id': None, 'prepared_image_name': 'oslit-input-' + nonce + ':latest',
            'unsettled': [], 'daemon_id': 'fixture-daemon', 'image_id': self.profile['image_id'],
            'profile_sha256': digest(json.dumps(self.profile, sort_keys=True, separators=(',', ':')).encode()),
            'access': [{k: row[k] for k in ('id', 'kind', 'identity')} for row in accesses],
            'support_inputs': [{'id': name, 'manifest_sha256': item['manifest_sha256']} for name, item in support_inputs.items()]}
        common = {'kind': 'environment-observation-v2', 'operation': 'start',
            'operation_id': 'fixture-start-' + nonce, 'identity': copy.deepcopy(self.identity)}
        self.observe(dict(common, phase='intent'))
        self.running = True
        self.observe(dict(common, phase='result', status='settled'))
        return {'status': 'prepared', 'identity': self.identity,
            'inputs': {row['id']: '/input/' + row['id'] for row in accesses},
            'support_inputs': {name: '/input/' + name for name in support_inputs}}

    def receipt(self):
        return copy.deepcopy(self.identity)

    def launch_stdio(self, argv, *, role='native_tools'):
        raise AssertionError('simulated native owner must not launch Docker')

    def read_artifact(self, relative, max_bytes):
        if relative.startswith('/') or '..' in Path(relative).parts:
            raise ValueError('workspace_path_invalid')
        content = self.__class__.native_files[relative]
        require(len(content) <= max_bytes, 'artifact over bound')
        self.__class__.reads += 1
        operation = 'artifact-read-' + str(self.__class__.reads)
        self.observe({'kind': 'environment-observation-v2', 'phase': 'result', 'operation': 'read_artifact',
            'operation_id': operation, 'identity': self.receipt(), 'status': 'settled',
            'path': '/work/' + relative, 'output_sha256': digest(content), 'bytes': len(content)})
        return {'operation_id': operation, 'path': '/work/' + relative, 'output_sha256': digest(content),
            'bytes': len(content), 'content': content}

    def execute(self, argv, *, timeout_seconds):
        operation = 'capture-execute-' + self.identity['nonce']
        self.observe({'kind': 'environment-observation-v2', 'phase': 'intent', 'operation': 'execute',
            'operation_id': operation, 'identity': self.receipt(), 'request_sha256': digest(canonical(argv))})
        def mapped(value):
            if value.startswith('/input/'):
                parts = value.split('/')
                root = self.staged[parts[2]]['path'] if parts[2] in self.staged else self.access_files[parts[2]]
                return str(Path(root).joinpath(*parts[3:]))
            return value
        completed = subprocess.run([mapped(value) for value in argv], capture_output=True,
            timeout=timeout_seconds, check=False)
        output = completed.stdout + completed.stderr
        self.observe({'kind': 'environment-observation-v2', 'phase': 'result', 'operation': 'execute',
            'operation_id': operation, 'identity': self.receipt(), 'status': 'settled',
            'returncode': completed.returncode, 'output_sha256': digest(output)})
        return {'status': 'settled', 'returncode': completed.returncode,
            'output': output.decode('utf-8'), 'identity': self.receipt()}

    def renew(self, seconds):
        self.renewals.append(seconds)
        return {'status': 'renewal_sent', 'seconds': seconds, 'identity': self.identity}

    def revoke(self):
        self.running = False
        return {'status': 'stopped', 'running': False, 'identity': self.identity}

    def readback(self):
        return {'status': 'running' if self.running else 'stopped', 'running': self.running, 'identity': self.identity}

    def cleanup(self):
        if self.__class__.cleanup_fails:
            raise ValueError('fixture-cleanup-unobserved')
        self.running = False
        return {'status': 'clean', 'identity': self.identity, 'owned_workspace': 'container_removed'}


class SimulatedProxy:
    def __init__(self, launcher, command, gate, authorize, *, dispatch_guard):
        self.command, self.gate = command, gate
        self.port = 45671

    def environment(self, ca_path):
        return {'HTTP_PROXY': 'http://127.0.0.1:45671', 'HTTPS_PROXY': 'http://127.0.0.1:45671',
            'NO_PROXY': 'localhost,127.0.0.1,::1', 'SSL_CERT_FILE': ca_path,
            'CURL_CA_BUNDLE': ca_path, 'NODE_EXTRA_CA_CERTS': ca_path}

    def close(self):
        return {'host_process_exited': True, 'native_exit': 'environment_readback_required'}


class SimulatedExecutor:
    def __init__(self, **options):
        self.options = options
        self.environment_id = options['environment_id']
        self.url = 'ws://127.0.0.1:45672/'

    def check_ready(self):
        return {'version': 'engineering-fixture', 'platform': 'linux'}

    def close(self):
        return {'host_process_exited': True}


class SimulatedRuntime:
    instances = []
    def __init__(self, profile, state_dir, workspace, **options):
        self.profile, self.options = profile, options
        self.session_id = None
        self.usage = None
        self.__class__.instances.append(self)

    def fresh(self):
        self.session_id = 'boundary-fixture-session'
        return {'session_id': self.session_id}

    def owner_receipt(self):
        return {'kind': 'native-runtime-owner-v1', 'runtime': 'codex', 'session_id': self.session_id,
            'profile_sha256': self.options['profile_sha256'], 'boundary': 'darwin-no-fork-v1',
            'process': {'pid': 34567, 'pgid': 34567, 'uid': os.getuid(),
                        'started_seconds': 1, 'started_microseconds': 2}}

    def interrupt(self):
        return {'requested': False}

    def close(self):
        return {'session_id': self.session_id, 'process_exited': True,
            'child_absence': 'verified', 'capabilities_revoked': True}


def simulated_boundary(path, lease_seconds=30):
    import engagement_native_boundary as boundary
    x = fixture.Case(path, start=False)
    workspace = x.workspace('lead-1')
    grant = x.c.prepare_worker_dispatch('lead-1', 1, workspace, seconds=lease_seconds,
        resources=['source-main'], adapter_id='fixture-adapter')
    runner = SimpleNamespace(controller=x.c, contract=frozen_inputs(x.c), changed=threading.Event())
    context = WorkerContext(runner, x.c.state()['workers']['lead-1'], grant, workspace)
    def bundle(profile, identity):
        return {'support_input': {'path': profile['tool_bundle']['path'],
                    'manifest_sha256': profile['tool_bundle']['manifest_sha256']},
            'command': ['/input/' + identity + '/bin/codex', 'exec-server', '--listen', 'stdio'],
            'expected_version': 'engineering-fixture', 'expected_platform': 'linux'}
    stack = ExitStack()
    stack.enter_context(patch.object(boundary, 'Environment', SimulatedEnvironment))
    stack.enter_context(patch.object(boundary, 'ProxyBridge', SimulatedProxy))
    stack.enter_context(patch.object(boundary, '_inspect_bundle', bundle))
    stack.enter_context(patch.object(boundary, '_credential_resolver', lambda: lambda profile: SimpleNamespace(check=lambda: None, revoke=lambda: None)))
    stack.enter_context(patch.object(boundary.codex, 'Runtime', SimulatedRuntime))
    stack.enter_context(patch.object(boundary.codex, 'NativeExecutor', SimulatedExecutor, create=True))
    SimulatedEnvironment.instances = []
    SimulatedEnvironment.cleanup_fails = False
    SimulatedRuntime.instances = []
    SimulatedEnvironment.native_files = {}
    SimulatedEnvironment.reads = 0
    return boundary, x, context, stack


def lifecycle(path):
    boundary, x, context, stack = simulated_boundary(path)
    with stack:
        before = x.c.state()['revision']
        instance = boundary.NativeBoundary(context)
        require(x.c.state()['revision'] == before, 'constructor created journal effects')
        identity = instance.start()
        x.c.record_worker_started('lead-1', 1, identity['session_id'], context.workspace,
            owner_receipt=identity['owner_receipt'])
        runtime = SimulatedRuntime.instances[-1]
        require(runtime.options['protected_model'] is True, 'host model lacks process containment')
        require(runtime.options['profile_sha256'] == context.assignment['profile_sha256'], 'raw profile pin changed')
        require('deny network' in runtime.options['command_prefix'][2], 'host model network default is open')
        require('45672' in runtime.options['command_prefix'][2], 'native executor endpoint not admitted')
        environment = SimulatedEnvironment.instances[0]
        bootstrap = Path(environment.staged['bootstrap']['path'])
        require((bootstrap / 'goal.md').read_bytes() == x.contract.goal_bytes, 'goal not staged')
        require((bootstrap / 'methodology.md').is_file(), 'methodology not staged')
        require(not any('PRIVATE KEY' in p.read_text(errors='ignore') for p in bootstrap.rglob('*') if p.is_file()),
            'private TLS material entered worker support')
        instance.renew(10)
        require(environment.renewals == [10], 'worker lease was not renewed')
        page = instance.host_call('engagement_status', {'since': None, 'limit': 10}).wait()
        require('content' in page and not page.get('isError'), 'authenticated worker status unavailable')
        result = instance.finish()
        require(result['cleanup'] == 'verified', 'exact complete cleanup not recognized')
        require(result['resources']['source-main'] == 'reset', 'private copy cleanup not reported as reset')
        require(result['runtime']['owner_receipt_sha256'] == digest(canonical(identity['owner_receipt'])), 'stop receipt lost owner binding')
        require(instance.finish() == result, 'finish retry changed terminal readback')
        require(x.c.state()['workers']['lead-1']['status'] == 'revoked', 'finish did not revoke new authority')


def cleanup_failure(path):
    boundary, x, context, stack = simulated_boundary(path)
    with stack:
        instance = boundary.NativeBoundary(context)
        identity = instance.start()
        x.c.record_worker_started('lead-1', 1, identity['session_id'], context.workspace,
            owner_receipt=identity['owner_receipt'])
        SimulatedEnvironment.cleanup_fails = True
        result = instance.finish()
        require(result['cleanup'] == 'unresolved', 'failed cleanup became verified')
        require(result['resources']['source-main'] == 'unknown', 'unknown copy lifetime released resource')


def admission_and_late_result(path):
    boundary, x, context, stack = simulated_boundary(path)
    with stack:
        instance = boundary.NativeBoundary(context)
        identity = instance.start()
        x.c.record_worker_started('lead-1', 1, identity['session_id'], context.workspace,
            owner_receipt=identity['owner_receipt'])
        environment = SimulatedEnvironment.instances[0]
        calls = []
        original = copy.deepcopy(context.grant)
        def recorder(grant, profile, observation, **options):
            calls.append((copy.deepcopy(grant), observation['phase']))
        with patch.object(x.c, 'record_environment_observation', recorder):
            event = {'kind': 'environment-observation-v2', 'operation': 'execute',
                'operation_id': 'late-result', 'identity': environment.receipt()}
            environment.observe(dict(event, phase='intent', request_sha256=digest(b'harmless command')))
            context.grant = dict(original, lease_expires_at='2099-01-01T00:00:00+00:00')
            environment.observe(dict(event, phase='result', status='settled', returncode=0,
                output_sha256=digest(b'harmless output')))
        require(calls == [(original, 'intent'), (original, 'result')], 'late result adopted a newer grant version')
        context.grant = original
        instance.finish()


def recovery_missing_owner(path):
    boundary, x, context, stack = simulated_boundary(path)
    with stack:
        result = boundary.recover_boundary(context, x.c.state()['dispatches'][context.grant['dispatch_id']])
        require(result['status'] == 'unknown', 'missing owner receipt invented stopped process')


def route_separation(path):
    import engagement_native_boundary as boundary
    x = fixture.Case(path)
    scope = copy.deepcopy(x.contract.scope)
    def route(host):
        return {'protocol': 'https', 'host': host, 'port': 443,
            'address_policy': {'public_only': True, 'cidrs': []}}
    scope['network'] = {'provider': [route('provider.example')],
        'acquisition': [route('packages.example'), route('app.example'), route('provider.example')],
        'target': [route('app.example')]}
    scope['access'].append({'id': 'application-main', 'kind': 'application',
        'identity': {'base_url': 'https://app.example/', 'version': None},
        'account_refs': [], 'permissions': ['read']})
    selected = boundary._routes(scope, ['source-main'])
    require([row['host'] for row in selected['provider']] == ['provider.example'], 'provider routes lost')
    require([row['host'] for row in selected['lab']] == ['packages.example'], 'source worker obtained app/provider route')
    selected = boundary._routes(scope, ['application-main'])
    require({row['host'] for row in selected['lab']} == {'app.example', 'packages.example'}, 'app grant lost its target')


def recovery_exact_owner(path):
    boundary, x, context, stack = simulated_boundary(path)
    with stack:
        instance = boundary.NativeBoundary(context)
        identity = instance.start()
        x.c.record_worker_started('lead-1', 1, identity['session_id'], context.workspace,
            owner_receipt=identity['owner_receipt'])
        instance.finish()
        def stopped(owner):
            require(owner == identity['owner_receipt'], 'recovery used an unbound process owner')
            return {'session_id': owner['session_id'], 'process_exited': True,
                'child_absence': 'verified', 'capabilities_revoked': True}
        with patch.object(boundary, '_recover_owner', stopped):
            result = boundary.recover_boundary(context, x.c.state()['dispatches'][context.grant['dispatch_id']])
        require(result['status'] == 'settled', 'exact recovery did not settle')
        require(x.c.state()['dispatches'][context.grant['dispatch_id']]['status'] == 'settled', 'recovery did not persist settlement')


def protected_capture(path):
    boundary, x, context, stack = simulated_boundary(path)
    with stack:
        instance = boundary.NativeBoundary(context)
        identity = instance.start()
        x.c.record_worker_started('lead-1', 1, identity['session_id'], context.workspace,
            owner_receipt=identity['owner_receipt'])
        x.instrument()
        SimulatedEnvironment.native_files = {'candidate.txt': b'candidate signal',
            'probe.py': b'import hashlib,pathlib,sys\nprint(hashlib.sha256(pathlib.Path(sys.argv[2]).read_bytes()).hexdigest())\n'}
        operation = instance.host_call('engagement_capture', {'instrument_id': 'instrument-1',
            'candidate_path': 'candidate.txt', 'probe_path': 'probe.py', 'interpreter': 'python3',
            'arguments': [], 'conditions': {'fixture': 'one'}, 'seconds': 10,
            'patch_id': None, 'patch_arm': None})
        require(hasattr(operation, 'wait'), 'capture did not reserve asynchronous owned work')
        result = operation.wait()
        require(not result.get('isError'), 'protected capture failed: ' + str(result))
        value = json.loads(result['content'][0]['text'])
        state = x.c.state()
        captured = state['dispatches'][value['dispatch_id']]
        require(captured['status'] == 'settled' and captured['parent_dispatch_id'] == context.grant['dispatch_id'], 'capture reservation not settled separately')
        observed = state['environment_operations'][value['operation_id']]
        require(observed['measurement']['clean_start'] is True, 'fresh instance not recorded')
        require(observed['measurement']['candidate_sha256'] == digest(b'candidate signal'), 'candidate bytes lost')
        require(observed['measurement']['probe_sha256'] == digest(SimulatedEnvironment.native_files['probe.py']), 'executed probe bytes lost')
        require(state['workers']['lead-1']['status'] == 'active', 'capture cleanup revoked its parent')
        require(len(SimulatedEnvironment.instances) == 2, 'capture reused mutable worker environment')
        instance.finish()


def renewable_capture(path):
    boundary, x, context, stack = simulated_boundary(path, lease_seconds=3)
    with stack:
        instance = boundary.NativeBoundary(context)
        identity = instance.start()
        x.c.record_worker_started('lead-1', 1, identity['session_id'], context.workspace,
            owner_receipt=identity['owner_receipt'])
        x.instrument()
        SimulatedEnvironment.native_files = {'candidate.txt': b'candidate signal',
            'probe.py': b'import time\ntime.sleep(4)\nprint("renewed capture complete")\n'}
        stopped = threading.Event()
        failures = []
        def renew_parent():
            while not stopped.wait(.3):
                try:
                    context.renew(3)
                    instance.renew(2)
                except Exception as error:
                    failures.append(type(error).__name__ + ': ' + str(error))
                    break
        renewal = threading.Thread(target=renew_parent)
        renewal.start()
        try:
            operation = instance.host_call('engagement_capture', {'instrument_id': 'instrument-1',
                'candidate_path': 'candidate.txt', 'probe_path': 'probe.py', 'interpreter': 'python3',
                'arguments': [], 'conditions': {'fixture': 'one'}, 'seconds': 7,
                'patch_id': None, 'patch_arm': None})
            result = operation.wait()
            require(not result.get('isError'), 'capture did not survive its initial short lease: ' + str(result))
            value = json.loads(result['content'][0]['text'])
            state = x.c.state()
            captured = state['dispatches'][value['dispatch_id']]
            require(captured['status'] == 'settled' and len(captured.get('prior_grants', [])) > 0,
                'long capture did not reserve continued work')
            require(SimulatedEnvironment.instances[1].renewals, 'capture environment lifetime was not renewed')
            observed = state['environment_operations'][value['operation_id']]
            require(observed['grant'] in captured['prior_grants'], 'late execution result lost its original admission')
            require(state['workers']['lead-1']['status'] == 'active', 'long capture stopped its parent')
            require(not failures, 'parent reservation renewal failed: ' + str(failures))
        finally:
            stopped.set(); renewal.join(timeout=2)
            instance.finish()


def cancelled_capture(path):
    boundary, x, context, stack = simulated_boundary(path)
    with stack:
        instance = boundary.NativeBoundary(context)
        identity = instance.start()
        x.c.record_worker_started('lead-1', 1, identity['session_id'], context.workspace,
            owner_receipt=identity['owner_receipt'])
        x.instrument()
        operation = instance.host_call('engagement_capture', {'instrument_id': 'instrument-1',
            'candidate_path': 'not-read.txt', 'probe_path': 'not-read.py', 'interpreter': 'python3',
            'arguments': [], 'conditions': {'fixture': 'one'}, 'seconds': 10,
            'patch_id': None, 'patch_arm': None})
        operation.cancel()
        result = operation.wait()
        require(result.get('isError'), 'cancelled capture executed')
        value = json.loads(result['content'][0]['text'])
        state = x.c.state()
        require(state['dispatches'][value['dispatch_id']]['status'] == 'settled', 'known unstarted work remained reserved')
        require(state['workers']['lead-1']['status'] == 'active', 'auxiliary cancellation stopped its parent')
        require(len(SimulatedEnvironment.instances) == 1, 'cancelled capture created another environment')
        instance.finish()


def host_network_policy(path):
    import engagement_native_boundary as boundary
    from native_runtime_owner import model_command
    listeners = [socket.socket(), socket.socket()]
    try:
        for listener in listeners:
            listener.bind(('127.0.0.1', 0)); listener.listen(1)
        allowed, denied = [listener.getsockname()[1] for listener in listeners]
        prefix = boundary._model_policy(f'http://127.0.0.1:{allowed}')
        program = ('import socket,sys\n'
            'listener=socket.socket();listener.bind(("127.0.0.1",0));listener.listen(1);listener.close()\n'
            f'socket.create_connection(("127.0.0.1",{allowed}),timeout=2).close()\n'
            'try:\n'
            f' socket.create_connection(("127.0.0.1",{denied}),timeout=2).close()\n'
            'except OSError:\n sys.exit(0)\n'
            'sys.exit(3)\n')
        result = subprocess.run(model_command([*prefix, sys.executable, '-c', program]),
            capture_output=True, timeout=10)
        require(result.returncode == 0, 'actual host network sandbox failed its loopback bind or fixed outbound allowlist: ' + str(result.returncode) + ' ' + result.stderr.decode())
    finally:
        for listener in listeners:
            listener.close()


def certificates(path):
    import engagement_native_boundary as boundary
    budget = 5 * 24 * 60 * 60
    ca, certificate, key = boundary._certificates(path, ['localhost', '127.0.0.1'], lifetime_seconds=budget)
    result = subprocess.run(['openssl', 'verify', '-CAfile', str(ca), str(certificate)],
        capture_output=True, timeout=10)
    require(result.returncode == 0, 'generated leaf does not chain to worker CA')
    result = subprocess.run(['openssl', 'x509', '-in', str(certificate), '-text', '-noout'],
        capture_output=True, timeout=10)
    require(b'CA:FALSE' in result.stdout and b'DNS:localhost' in result.stdout,
        'proxy presented a CA certificate or lost its route hostname')
    require(key.stat().st_mode & 0o077 == 0, 'proxy private key is exposed')
    for issued in (ca, certificate):
        validity = subprocess.run(['openssl', 'x509', '-in', str(issued), '-checkend', str(budget), '-noout'],
            capture_output=True, timeout=10)
        require(validity.returncode == 0, 'certificate introduces a deadline shorter than the signed work budget')


def startup_owner(path):
    boundary, x, context, stack = simulated_boundary(path)
    with stack:
        require(hasattr(x.c, 'record_runtime_preparation_owner'), 'protected startup owner API missing')
        class ObservedExecutor(SimulatedExecutor):
            def __init__(self, **options):
                super().__init__(**options)
                require(callable(options.get('owner_observer')), 'bridge owner was not bound before readiness')
                self.bridge_identity = {'pid': 34568, 'pgid': 34568, 'uid': os.getuid(),
                    'started_seconds': 1, 'started_microseconds': 2}
                options['owner_observer']({'kind': 'native-runtime-owner-v1', 'runtime': 'codex',
                    'session_id': None, 'profile_sha256': options['profile_sha256'], 'boundary': 'darwin-no-fork-v1',
                    'bridge_process': self.bridge_identity})
        class ObservedRuntime(SimulatedRuntime):
            def owner_receipt(self):
                return dict(super().owner_receipt(), bridge_process=self.options['native_executor'].bridge_identity)
            def __init__(self, profile, state_dir, workspace, **options):
                super().__init__(profile, state_dir, workspace, **options)
                require(callable(options.get('owner_observer')), 'model owner was not bound before initialization')
                options['owner_observer'](self.owner_receipt())
            def fresh(self):
                identity = super().fresh()
                self.options['owner_observer'](self.owner_receipt())
                return identity
        with patch.object(boundary.codex, 'NativeExecutor', ObservedExecutor), patch.object(boundary.codex, 'Runtime', ObservedRuntime):
            instance = boundary.NativeBoundary(context)
            before = x.c.state()['revision']
            identity = instance.start()
            require(x.c.state()['revision'] >= before + 3, 'startup owners were not durably recorded')
            require(x.c.read_object(digest(canonical(identity['owner_receipt']))) == canonical(identity['owner_receipt']),
                'final preparation owner bytes not frozen')
            require(x.c.state()['workers']['lead-1']['status'] == 'preparing', 'startup receipt activated worker early')
            x.c.record_worker_started('lead-1', 1, identity['session_id'], context.workspace,
                owner_receipt=identity['owner_receipt'])
            instance.finish()


def startup_failure_cleanup(path):
    boundary, x, context, stack = simulated_boundary(path)
    with stack:
        class FailingRuntime(SimulatedRuntime):
            def __init__(self, profile, state_dir, workspace, **options):
                super().__init__(profile, state_dir, workspace, **options)
                options['owner_observer'](self.owner_receipt())
                raise boundary.BoundaryError('fixture-startup-failure')
        recovered = []
        def recover(owner):
            recovered.append(owner)
            return {'session_id': None, 'process_exited': True,
                'child_absence': 'verified', 'capabilities_revoked': True}
        instance = boundary.NativeBoundary(context)
        with patch.object(boundary.codex, 'Runtime', FailingRuntime):
            refused('fixture-startup-failure', instance.start)
        owner = SimulatedRuntime.instances[-1].owner_receipt()
        require(x.c.state()['workers']['lead-1']['status'] == 'preparing', 'failed constructor activated worker')
        with patch.object(boundary, '_recover_owner', recover):
            result = instance.finish()
        require(recovered == [owner], 'failed constructor lost the process owner')
        require(result['cleanup'] == 'verified', 'exact startup cleanup remained unverified')
        x.c.record_worker_stopped(context.grant, instance.environment_id,
            {'runtime': result['runtime'], 'environment': result['environment']})
        require(x.c.state()['workers']['lead-1']['status'] == 'stopped', 'startup stop receipt did not bind')
        with patch.object(boundary, '_recover_owner', recover):
            result = boundary.recover_boundary(context, x.c.state()['dispatches'][context.grant['dispatch_id']])
        require(result['status'] == 'settled', 'pre-session recovery did not settle exact known owners')


def preparation_without_execution(path):
    boundary, x, context, stack = simulated_boundary(path)
    with stack:
        instance = boundary.NativeBoundary(context)
        with patch.object(boundary, '_inspect_bundle', side_effect=boundary.BoundaryError('fixture-preflight-unavailable')):
            refused('fixture-preflight-unavailable', instance.start)
        result = instance.finish()
        require(result.get('execution_admitted') is False, 'preflight failure lost its no-execution fact')
        require(instance.owner_receipt is None and not SimulatedEnvironment.instances,
            'preflight failure reached native or environment execution')
        require(result['cleanup'] == 'verified', 'unused preparation did not provide explicit cancellation cleanup')
        require(result['runtime']['process_exited'] is False and result['runtime']['child_absence'] == 'not_observed',
            'unused preparation invented process absence')
        require(result['resources'] == {'source-main': 'unchanged'}, 'unused preparation claimed input reset')


def frozen_guidance(path):
    boundary, x, context, stack = simulated_boundary(path)
    with stack, patch.object(boundary, '_methodology', return_value=b'Mutable repository text.\n', create=True):
        instance = boundary.NativeBoundary(context)
        try:
            instance.start()
            for name in ('methodology.md', 'protocol.md'):
                require((instance.bootstrap / name).read_bytes() == context.contract.frozen_files[name],
                    'worker did not receive frozen ' + name)
        finally:
            instance.finish()


def missing_guidance(path):
    boundary, x, context, stack = simulated_boundary(path)
    with stack:
        context.contract.frozen_files.pop('protocol.md')
        instance = boundary.NativeBoundary(context)
        try:
            refused('native_engagement_guidance_unavailable', instance.start)
            require(not instance.execution_admitted and not SimulatedEnvironment.instances, 'missing guidance reached execution')
        finally:
            result = instance.finish()
        require(result['cleanup'] == 'verified', 'missing guidance preparation could not be cancelled')


def unused_preparation_cleanup(path):
    for mode in ('clean', 'directory-failure', 'gate-failure', 'admitted-without-owner'):
        root = path / mode
        root.mkdir(mode=0o700)
        boundary, x, context, stack = simulated_boundary(root)
        with stack:
            instance = boundary.NativeBoundary(context)
            instance.state_dir = root / 'staged'; instance.state_dir.mkdir(mode=0o700)
            instance.socket_dir = root / 'sockets'; instance.socket_dir.mkdir(mode=0o700)
            (instance.state_dir / 'private-material').write_bytes(b'fixture-private-key-placeholder')
            closed = []
            def close_gate():
                closed.append(True)
                if mode == 'gate-failure':
                    raise OSError('fixture close failure')
            instance.lab_gate = SimpleNamespace(close=close_gate)
            instance.credential_binding = SimpleNamespace(revoke=lambda: closed.append('credentials'))
            instance.execution_admitted = mode == 'admitted-without-owner'
            if mode == 'directory-failure':
                with patch.object(boundary.shutil, 'rmtree', side_effect=OSError('fixture remove failure')):
                    result = instance.finish()
            else:
                result = instance.finish()
            require(closed == [True, 'credentials'], 'preparation resources were not closed')
            require(result['cleanup'] == ('verified' if mode == 'clean' else 'unresolved'),
                'unused preparation cleanup overstated its observation')
            require(result['runtime']['process_exited'] is False, 'missing owner became process absence proof')
            if mode == 'clean':
                require(not instance.state_dir.exists() and not instance.socket_dir.exists(), 'preparation directories remained')
                require(instance.finish() == result, 'cancellation cleanup changed on retry')
            elif mode == 'directory-failure':
                require(instance.state_dir.exists(), 'failed cleanup directory disappeared')


def environment_effect_selection(path):
    import engagement_native_boundary as boundary
    from engagement_contract import load_inputs
    from engagement_controller import Controller
    inputs = fixture.fixture.make_fixture(path / 'input')
    scope = fixture.fixture.fixture_scope(inputs)
    ungranted = dict(scope['environments'][0], profile_id='lab-ungranted')
    scope['environments'].insert(0, ungranted)
    document = json.loads(inputs.read_bytes())
    document['environment_profiles']['lab-ungranted'] = document['environment_profiles']['lab-main']
    inputs.write_bytes(canonical(document))
    fixture.fixture.resign_fixture(inputs, scope)
    contract = load_inputs(inputs)
    controller = Controller.initialize(path / 'engagement', contract, evidence_class='engineering_simulation')
    workspace = path / 'workspace'; workspace.mkdir(mode=0o700)
    grant = controller.prepare_worker_dispatch('lead-1', 1, workspace, seconds=30,
        resources=['source-main'], adapter_id='fixture-adapter')
    context = SimpleNamespace(controller=controller, contract=contract,
        worker=controller.state()['workers']['lead-1'], grant=grant, workspace=workspace,
        assignment=contract.scope['runtime_assignments'][0])
    context.authorize = lambda: (controller.authorize_dispatch(grant) and grant)
    instance = boundary.NativeBoundary(context)
    require(instance.environment_id is None, 'constructor selected a fallible environment before lifecycle ownership')
    try:
        instance.start()
    except Exception as error:
        require(getattr(error, 'code', None) == 'native_bundle_platform_mismatch', 'wrong unavailable fixture prerequisite')
    else:
        raise AssertionError('unavailable native fixture was executed')
    require(instance.environment_id == 'lab-main', 'selected an environment without a matching signed effect')
    require(instance.finish()['cleanup'] == 'verified', 'read-only selection failure lacked unused cleanup proof')


def native_host_tools(path):
    from native_runtime_transport import Session
    boundary, x, context, stack = simulated_boundary(path)
    with stack:
        instance = boundary.NativeBoundary(context)
        identity = instance.start()
        x.c.record_worker_started('lead-1', 1, identity['session_id'], context.workspace,
            owner_receipt=identity['owner_receipt'])
        # Exercise the real shared native tool protocol with simulated model IO.
        runtime = Session()
        runtime.kind, runtime.version = 'codex', 'engineering-fixture'
        runtime.session_id, runtime.invocation_id = identity['session_id'], 'fixture-turn'
        runtime.calls, runtime.events, runtime.active = {}, [], True
        runtime.host_tools = {tool['name']: tool for tool in boundary.TOOLS}
        runtime.host_call, runtime._admission = instance.host_call, context.guard
        private = x.c.store_object(b'fixture not yet published')
        denied = runtime._tool('private-object', 'engagement_read', {'sha256': private})
        require(denied.ready.wait(2) and denied.response.get('isError'), 'unpublished object was readable')
        x.instrument()
        published = x.c.state()['instruments']['instrument-1']['artifact_sha256']
        calls = [('engagement_status', {'since': None, 'limit': 10}),
            ('engagement_read', {'sha256': published}),
            ('engagement_submit', {'request': {'request_id': 'native-submit',
                'expected_revision': x.c.state()['revision'], 'type': 'task_create',
                'payload': {'task_id': 'native-task', 'question': 'Inspect fixture.', 'priority': 1,
                    'resources': [], 'prerequisites': [], 'evidence_refs': []}}})]
        for index, (name, arguments) in enumerate(calls):
            pending = runtime._tool('native-call-' + str(index), name, arguments)
            require(pending.ready.wait(2), name + ' did not finish')
            require(not pending.unknown and not pending.response.get('isError'), name + ' did not cross native host protocol')
        require('native-task' in x.c.state()['tasks'], 'native submit lost its journal effect')
        require(not runtime.events, 'valid host calls were reported as unknown')
        instance.finish()


def native_reply_peer(boundary, context, transport, kind):
    runtime_class = CodexRuntime if kind == 'codex' else OMPRuntime
    peer = runtime_class.__new__(runtime_class)
    peer.transport = transport
    peer.session_id, peer.invocation_id = 'reply-session-' + kind, 'reply-turn'
    peer.calls, peer.events, peer.active = {}, [], True
    peer.tool_replies, peer.tool_requests = [], {}
    peer.host_tools = {tool['name']: tool for tool in boundary.TOOLS}
    peer.host_call, peer._admission = context['instance'].host_call, context['context'].guard
    return peer


def native_reply(peer, identity, name, arguments):
    if peer.kind == 'codex':
        pending = peer._tool(identity, name, arguments)
    else:
        peer._event({'type': 'host_tool_call', 'id': identity, 'toolCallId': identity,
            'toolName': name, 'arguments': arguments})
        pending = peer.tool_requests[identity]
    require(pending.ready.wait(5) and not pending.unknown, 'native host call did not finish')
    if peer.kind == 'codex':
        peer._tool_reply(identity, pending.response)
    else:
        peer._flush_tool_replies()
    return pending.response


def native_response_chunks(path):
    from native_runtime_transport import Transport
    boundary, x, context, stack = simulated_boundary(path)
    with stack:
        instance = boundary.NativeBoundary(context)
        identity = instance.start()
        x.c.record_worker_started('lead-1', 1, identity['session_id'], context.workspace,
            owner_receipt=identity['owner_receipt'])
        transport = Transport([sys.executable, '-c', 'import sys\nfor line in sys.stdin: pass'], {}, str(ROOT), lambda event: None)
        try:
            objects = [b'harmless observation\n' * 60000, b'\x80\x81\x82' * 400000]
            for index, content in enumerate(objects):
                sha = x.c.store_object(content)
                x.request('instrument_register', {'instrument_id': 'large-' + str(index), 'artifact_sha256': sha,
                    'metric': 'harmless', 'reset': 'clean-copy', 'conditions': {}, 'supersedes': []})
                for kind in ('codex', 'omp'):
                    peer = native_reply_peer(boundary, {'instance': instance, 'context': context}, transport, kind)
                    parts, offset, count = [], 0, 0
                    while offset is not None:
                        response = native_reply(peer, f'read-{index}-{count}', 'engagement_read', {'sha256': sha, 'offset': offset})
                        require(not response.get('isError'), 'published range was refused')
                        body = json.loads(response['content'][0]['text'])
                        require(body['offset'] == offset and body['total_bytes'] == len(content), 'range metadata lost')
                        parts.append(base64.b64decode(body['content']) if body['encoding'] == 'base64' else body['content'].encode())
                        next_offset = body['next_offset']
                        require(next_offset is None or next_offset > offset, 'range cursor did not advance')
                        offset, count = next_offset, count + 1
                        require(count < 100, 'range did not terminate')
                    require(count > 1 and b''.join(parts) == content, 'chunked native replies changed evidence bytes')
        finally:
            transport.close(); instance.finish()


def native_status_bounds(path):
    from native_runtime_transport import Transport
    boundary, x, context, stack = simulated_boundary(path)
    with stack:
        instance = boundary.NativeBoundary(context)
        identity = instance.start()
        x.c.record_worker_started('lead-1', 1, identity['session_id'], context.workspace,
            owner_receipt=identity['owner_receipt'])
        transport = Transport([sys.executable, '-c', 'import sys\nfor line in sys.stdin: pass'], {}, str(ROOT), lambda event: None)
        try:
            for _ in range(3):
                x.c.direction('é' * 65536)
            for kind in ('codex', 'omp'):
                peer = native_reply_peer(boundary, {'instance': instance, 'context': context}, transport, kind)
                response = native_reply(peer, 'status-large', 'engagement_status', {'since': None, 'limit': 100})
                require(not response.get('isError'), 'bounded status failed')
                body = json.loads(response['content'][0]['text'])
                require(body['next_cursor'], 'status lost its cursor')
            since = x.c.status(limit=1000)['next_cursor']
            for _ in range(3):
                x.c.direction('\\' * 65536)
            peer = native_reply_peer(boundary, {'instance': instance, 'context': context}, transport, 'codex')
            response = native_reply(peer, 'status-escaped', 'engagement_status', {'since': since, 'limit': 100})
            body = json.loads(response['content'][0]['text'])
            require(body['has_more'] and body['next_cursor'], 'shrinking an escaped status page lost its cursor')
            # A host status fixture covers a single payload larger than the reply
            # budget; the valid journal/direction path above uses the real reader.
            page = x.c.status(since=since, limit=1)
            view_text = '🧪' * 262144
            page['updates'][0]['payload']['text'] = view_text
            before = x.c.state()['revision']
            files = sorted(str(p) for p in (x.c.root / 'objects').rglob('*'))
            with patch.object(x.c, 'status', return_value=page):
                response = native_reply(peer, 'status-view', 'engagement_status', {'since': since, 'limit': 1})
            body = json.loads(response['content'][0]['text'])
            view = body['ephemeral_read_view']
            require(x.c.state()['revision'] == before and files == sorted(str(p) for p in (x.c.root / 'objects').rglob('*')),
                'status wrote a journal event or evidence file')
            chunks, offset, index = [], 0, 0
            while offset is not None:
                response = native_reply(peer, 'view-' + str(index), 'engagement_read', {'sha256': view['sha256'], 'offset': offset})
                chunk = json.loads(response['content'][0]['text'])
                chunks.append(base64.b64decode(chunk['content']) if chunk['encoding'] == 'base64' else chunk['content'].encode())
                offset, index = chunk['next_offset'], index + 1
                require(index < 100, 'status view did not terminate')
            decoded = b''.join(chunks)
            require(digest(decoded) == view['sha256'] and len(decoded) == view['bytes'], 'status view identity changed')
            require(json.loads(decoded)['updates'][0]['payload']['text'] == view_text, 'oversized status payload was discarded')
            native_reply(peer, 'new-status', 'engagement_status', {'since': None, 'limit': 1})
            response = native_reply(peer, 'expired-view', 'engagement_read', {'sha256': view['sha256']})
            require(response.get('isError'), 'replaced status view retained unintended read authority')
            require(x.c.state()['workers']['lead-1']['cursor'] is None, 'read-only status acknowledged unread updates')
        finally:
            transport.close(); instance.finish()


def module_present(path):
    import engagement_native_boundary as boundary
    require(callable(boundary.NativeBoundary) and callable(boundary.recover_boundary), 'boundary API missing')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', default='all')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    scenarios = {'patch-readonly': patch_readonly, 'module': module_present, 'lifecycle': lifecycle,
        'cleanup-failure': cleanup_failure, 'late-result': admission_and_late_result,
        'missing-owner': recovery_missing_owner, 'route-separation': route_separation,
        'recovery': recovery_exact_owner, 'capture': protected_capture,
        'host-network': host_network_policy, 'certificates': certificates, 'startup-owner': startup_owner,
        'native-host-tools': native_host_tools, 'startup-failure-cleanup': startup_failure_cleanup,
        'renewable-capture': renewable_capture, 'cancelled-capture': cancelled_capture,
        'environment-effect-selection': environment_effect_selection,
        'preparation-without-execution': preparation_without_execution,
        'unused-preparation-cleanup': unused_preparation_cleanup,
        'frozen-guidance': frozen_guidance, 'missing-guidance': missing_guidance,
        'native-response-chunks': native_response_chunks, 'native-status-bounds': native_status_bounds}
    report = {'kind': 'engagement-native-boundary-e2e-v2', 'classification': 'engineering_simulation',
        'provider_calls': 0, 'docker_calls': 0, 'ssh_calls': 0, 'research_acceptance': 'not_run', 'scenarios': [],
        'source_sha256': {name: digest((ROOT / name).read_bytes()) for name in (
            'tools/engagement_controller.py', 'tools/engagement_evidence.py', 'tools/engagement_native_boundary.py',
            'tools/research_environment.py', 'tools/engagement_network.py', 'tools/engagement_runner.py',
            'evals/native-qualification/smoke/check_engagement_native_boundary_e2e.py')}}
    for name, operation in scenarios.items():
        if args.scenario not in ('all', name):
            continue
        with tempfile.TemporaryDirectory(prefix='oslit-boundary-') as temporary:
            try:
                operation(Path(temporary).resolve())
                report['scenarios'].append({'id': name, 'status': 'passed',
                    'observation': 'actual_local_host' if name in ('host-network', 'certificates') else 'engineering_simulation'})
            except Exception as error:
                report['scenarios'].append({'id': name, 'status': 'failed', 'error': type(error).__name__ + ': ' + str(error)})
    report['passed'] = bool(report['scenarios']) and all(row['status'] == 'passed' for row in report['scenarios'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical(report))
    print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
