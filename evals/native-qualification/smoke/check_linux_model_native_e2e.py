#!/usr/bin/env python3
"""Actual Linux native tools and retention against an owned TLS model fixture.

Run only on an explicit disposable Linux Docker host. Failure cases precede this
implementation in LINUX-MODEL-NATIVE-E2E.md. Only the output JSON is publishable;
the caller asset directory retains the pinned model executable and tool bundle.
"""
from __future__ import annotations

import argparse
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shlex
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
from engagement_contract import ContractError, canonical, digest, load_inputs, safe_publication, source_manifest
from check_engagement_contract_e2e import make_fixture, fixture_scope, resign_fixture, write
from check_model_image_docker_e2e import prepare_image, verify_image, cleanup_image

FIRST_PROMPT = 'Run the harmless Linux native boundary fixture and preserve its artifact.'
SECOND_PROMPT = 'Continue the same fixture using the earlier context and artifact.'
LEASE = 240
PROVIDER_HOST = '127.0.0.2'


def check(result, name, condition):
    result['checks'].append({'name': name, 'passed': bool(condition)})
    if not condition:
        raise AssertionError(name)


def error_code(error):
    value = getattr(error, 'code', None)
    return value if isinstance(value, str) and re.fullmatch('[a-z_]{1,100}', value) else type(error).__name__


def diagnostic_transport(observations, known_secrets):
    from native_runtime_transport import Transport

    class ObservedTransport(Transport):
        def request(self, operation, *args, **kwargs):
            self.observed_operation = operation
            try:
                return super().request(operation, *args, **kwargs)
            finally:
                self.observed_operation = None

        def receive(self, *args, **kwargs):
            received = super().receive(*args, **kwargs)
            for response in self.responses.values():
                if 'error' in response and len(observations) < 8:
                    try:
                        message = safe_publication(canonical(response['error']), known_secrets=known_secrets).decode()[:2048]
                    except ContractError:
                        message = '[diagnostic redacted]'
                    observations.append({'operation': self.observed_operation, 'error': message})
            return received

    return ObservedTransport


def environment_diagnostics(controller, known_secrets):
    with controller.lock():
        events = [event for event in controller._events() if event['type'] == 'evidence_recorded'
                  and event['payload'].get('action') == 'environment_observation']
    selected = events[:128]
    for event in selected:
        safe_publication(canonical(event), known_secrets=known_secrets)
    return {'events': selected, 'truncated': len(events) > len(selected)}


class ExecutorDiagnostics:
    """Fixture-local stderr observer for the fixed uncredentialed exec-server only."""
    def __init__(self, module):
        self.module = module
        self.captures = []

    def __getattr__(self, name):
        return getattr(self.module, name)

    def Popen(self, command, *args, **kwargs):
        selected = (isinstance(command, list) and command[-6:] == [
            '/input/native-runtime/bin/codex', 'exec-server', '--listen', 'stdio',
            '--linux-sandbox-pid-namespace', 'isolate'] and kwargs.get('stderr') == self.module.DEVNULL)
        if not selected:
            return self.module.Popen(command, *args, **kwargs)
        process = self.module.Popen(command, *args, **dict(kwargs, stderr=self.module.PIPE))
        capture = {'process': process, 'content': bytearray(), 'bytes': 0, 'complete': False}
        def drain():
            try:
                while chunk := process.stderr.read(4096):
                    capture['bytes'] += len(chunk)
                    available = max(0, 8192 - len(capture['content']))
                    capture['content'].extend(chunk[:available])
                capture['complete'] = True
            except (OSError, ValueError):
                pass
            finally:
                process.stderr.close()
        thread = threading.Thread(target=drain, daemon=True)
        capture['thread'] = thread
        self.captures.append(capture)
        thread.start()
        return process

    def finish(self, known_secrets):
        observations = []
        for capture in self.captures:
            capture['thread'].join(timeout=1)
            complete = not capture['thread'].is_alive() and capture['complete']
            oversized = capture['bytes'] > 8192
            if not complete:
                message = '[incomplete diagnostic withheld]'
            elif oversized:
                message = '[oversized diagnostic withheld]'
            else:
                try:
                    message = safe_publication(bytes(capture['content']), known_secrets=known_secrets).decode(
                        'utf-8', errors='replace')[:2048]
                except ContractError:
                    message = '[diagnostic redacted]'
            observations.append({'role': 'codex_exec_server', 'returncode': capture['process'].poll(),
                'bytes': capture['bytes'], 'complete': complete, 'truncated': oversized,
                'stderr': message})
        return observations


PROBE = r'''import json, os, pathlib, socket, sys
host_file, provider_port, model_pid, lab_port = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
result = {'input_read': pathlib.Path('/input/source-main/main.py').read_text() == 'HARMLESS_SOURCE\n',
          'model_input_absent': not pathlib.Path('/input/model').exists(),
          'host_file_absent': not pathlib.Path(host_file).exists(),
          'credential_absent': 'OPENAI_API_KEY' not in os.environ,
          'model_pid_absent': not pathlib.Path('/proc/' + str(model_pid)).exists(),
          'pid_namespace_inode': os.stat('/proc/self/ns/pid').st_ino}
try:
    connection = socket.create_connection(('127.0.0.2', provider_port), timeout=1)
    connection.close(); result['direct_provider_denied'] = False
except OSError:
    result['direct_provider_denied'] = True
try:
    connection = socket.create_connection(('127.0.0.1', lab_port), timeout=2)
    connection.sendall(('CONNECT 127.0.0.2:' + str(provider_port) + ' HTTP/1.1\r\nHost: 127.0.0.2\r\n\r\n').encode())
    result['lab_provider_denied'] = connection.recv(128).startswith(b'HTTP/1.1 403 ')
    result['lab_route_observation'] = 'proxy_response'
    connection.close()
except OSError:
    result['lab_provider_denied'] = True
    result['lab_route_observation'] = 'socket_denied'
pathlib.Path('/work/first-turn.txt').write_text('LINUX_NATIVE_FIRST_TURN\n')
print('NATIVE_PROBE=' + json.dumps(result, sort_keys=True))
'''


class Provider:
    """Deterministic wire fixture; request bodies and credentials never published."""
    def __init__(self, directory, runtime, secret):
        from engagement_native_boundary import _certificates
        directory.mkdir(mode=0o700)
        self.ca, certificate, key = _certificates(directory, [PROVIDER_HOST], lifetime_seconds=3600)
        self.runtime, self.secret = runtime, secret
        self.requests, self.errors, self.escapes = [], [], 0
        self.command = None
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                fixture.escapes += 1
                self.send_response(403); self.end_headers()

            def do_POST(self):
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 < size <= 2 * 1024 * 1024:
                        raise ValueError('provider_request_size')
                    body = json.loads(self.rfile.read(size))
                    if self.headers.get('Authorization') != 'Bearer ' + fixture.secret:
                        raise ValueError('provider_credential_missing')
                    if fixture.secret in json.dumps(body) or not fixture.command:
                        raise ValueError('provider_body_invalid')
                    fixture.requests.append(body)
                    seq = len(fixture.requests)
                    if seq > 4:
                        raise ValueError('provider_unexpected_request')
                    command = fixture.command if seq == 1 else 'cat /work/first-turn.txt'
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/event-stream')
                    self.end_headers()
                    frames = fixture.frames(seq, command)
                    for frame in frames:
                        self.wfile.write(frame)
                    self.wfile.flush()
                except Exception as error:
                    fixture.errors.append(error_code(error))
                    self.close_connection = True

        self.server = ThreadingHTTPServer((PROVIDER_HOST, 0), Handler)
        self.server.daemon_threads = True
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certificate, key)
        self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def origin(self):
        return 'https://' + PROVIDER_HOST + ':' + str(self.server.server_port)

    def frames(self, seq, command):
        tool = seq in (1, 3)
        if self.runtime == 'codex':
            item = ({'id': 'fc_' + str(seq), 'type': 'function_call', 'call_id': 'call-' + str(seq),
                     'name': 'exec_command', 'arguments': json.dumps({'cmd': command, 'max_output_tokens': 2000})}
                    if tool else {'id': 'msg_' + str(seq), 'type': 'message', 'role': 'assistant',
                                  'content': [{'type': 'output_text', 'text': 'Fixture complete.'}]})
            response = {'id': 'fixture-' + str(seq), 'object': 'response', 'status': 'completed',
                        'output': [item], 'usage': {'input_tokens': 10, 'output_tokens': 10, 'total_tokens': 20}}
            frames = [{'type': 'response.created', 'response': {**response, 'status': 'in_progress', 'output': []}},
                      {'type': 'response.output_item.added', 'output_index': 0, 'item': item},
                      {'type': 'response.output_item.done', 'output_index': 0, 'item': item},
                      {'type': 'response.completed', 'response': response}]
            return [('event: ' + frame['type'] + '\ndata: ' + json.dumps(dict(frame, sequence_number=i)) + '\n\n').encode()
                    for i, frame in enumerate(frames)]
        delta = ({'role': 'assistant', 'tool_calls': [{'index': 0, 'id': 'call-' + str(seq), 'type': 'function',
                  'function': {'name': 'bash', 'arguments': json.dumps({'command': command, 'timeout': 10})}}]}
                 if tool else {'role': 'assistant', 'content': 'Fixture complete.'})
        frames = [{'delta': delta, 'finish_reason': None},
                  {'delta': {}, 'finish_reason': 'tool_calls' if tool else 'stop'}]
        return [('data: ' + json.dumps({'id': 'fixture-' + str(seq), 'object': 'chat.completion.chunk',
                    'created': 0, 'model': 'fixture-model', 'choices': [{'index': 0, **frame}]}) + '\n\n').encode()
                for frame in frames] + [b'data: [DONE]\n\n']

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)


def tool_bundle(fixture, result):
    destination = fixture.directory / 'tool-bundle'
    if fixture.runtime == 'codex':
        (destination / 'bin').mkdir(parents=True, mode=0o700)
        os.link(fixture.context_receipt['profile_fields']['executable']['path'], destination / 'bin/codex')
        bundle = {'path': str(destination), 'manifest_sha256': digest(canonical(source_manifest(destination))),
                  'platform': fixture.platform}
        result['tool_installation'] = {'reused_verified_model_bytes': True, 'tool_bundle': bundle}
        return bundle
    receipt = fixture.directory / 'tool-receipt.json'
    installed = subprocess.run([sys.executable, str(ROOT / 'tools/install_native_tools.py'), 'install',
        '--runtime', fixture.runtime, '--platform', fixture.platform, '--destination', str(destination),
        '--receipt', str(receipt)], capture_output=True, timeout=600)
    result['tool_installer'] = {'returncode': installed.returncode}
    for name in ('stdout', 'stderr'):
        content = getattr(installed, name)
        try:
            text = safe_publication(content[:2048]).decode('utf-8', 'replace')
        except ContractError:
            text = '[diagnostic redacted]'
        result['tool_installer'].update({name: text, name + '_truncated': len(content) > 2048})
    check(result, 'pinned OMP SDK tool bundle installed', installed.returncode == 0)
    result['tool_installation'] = json.loads(receipt.read_bytes())
    return result['tool_installation']['profile_fields']['tool_bundle']


def signed_inputs(root, fixture, provider, bundle):
    from native_runtime_codex import _DISABLED_FEATURES
    inputs_path = make_fixture(root / 'input')
    inputs = json.loads(inputs_path.read_bytes())
    source = Path(inputs['access_files']['source-main'])
    write(source / 'main.py', b'HARMLESS_SOURCE\n')
    write(source / 'probe.py', PROBE.encode())
    schema = root / 'wire-schema.json'
    write(schema, canonical({'fixture': 'actual-pinned-native-wire'}))
    config = root / ('config.toml' if fixture.runtime == 'codex' else 'config.json')
    if fixture.runtime == 'codex':
        features = '\n'.join(name + ' = false' for name in _DISABLED_FEATURES)
        content = f'''model = "gpt-6.1-sol"
model_provider = "oslit-fixture"
web_search = "disabled"
default_permissions = "oslit-worker"
[features]
{features}
[shell_environment_policy]
inherit = "none"
[shell_environment_policy.set]
PATH = "/usr/local/bin:/usr/bin:/bin"
[permissions.oslit-worker.filesystem]
":root" = "deny"
":minimal" = "read"
"/input" = "read"
"/proc" = "read"
"/usr/local" = "read"
[permissions.oslit-worker.filesystem.":workspace_roots"]
"." = "write"
[permissions.oslit-worker.network]
enabled = false
[model_providers.oslit-fixture]
name = "Owned deterministic fixture"
base_url = "{provider.origin}/v1"
wire_api = "responses"
requires_openai_auth = false
env_key = "OPENAI_API_KEY"
'''.encode()
    else:
        content = canonical({'plan': {'enabled': False}, 'tools': {'xdev': False}, 'autolearn': {'enabled': False}})
    write(config, content)
    profile = {'kind': fixture.runtime, 'version': '0.166.0' if fixture.runtime == 'codex' else '18.20.0',
        'executable': fixture.context_receipt['profile_fields']['executable'],
        'protocol': {'mode': 'stdio-jsonrpc' if fixture.runtime == 'codex' else 'stdio-jsonl',
                     'schema_file': str(schema), 'schema_sha256': digest(schema.read_bytes())},
        'config_file': str(config), 'config_sha256': digest(content),
        'provider': 'oslit-fixture' if fixture.runtime == 'codex' else 'openai',
        'model': 'gpt-6.1-sol' if fixture.runtime == 'codex' else 'fixture-model',
        'credential_ref': 'env_OPENAI_API_KEY', 'required_capabilities': ['startup', 'fresh_session', 'native_tools'],
        'tool_bundle': bundle,
        'model_host': {'kind': 'linux-docker-model-v1', 'docker_binary': fixture.docker,
            'docker_endpoint': fixture.endpoint, 'daemon_id': fixture.daemon_id, 'image_id': fixture.image_id,
            'platform': fixture.platform, 'uid': 1000, 'gid': 1000,
            'limits': {'memory_bytes': 1073741824, 'cpu_count': 2, 'pids': 128, 'workspace_bytes': 134217728}}}
    if fixture.runtime == 'omp':
        catalog = root / 'models.yml'
        write(catalog, canonical({'providers': {'openai': {'baseUrl': provider.origin + '/v1',
            'api': 'openai-completions', 'models': [{'id': 'fixture-model', 'name': 'Owned fixture',
                'reasoning': False, 'input': ['text'], 'supportsTools': True,
                'contextWindow': 32768, 'maxTokens': 1024,
                'cost': {'input': 0, 'output': 0, 'cacheRead': 0, 'cacheWrite': 0}}]}}}))
        profile['model_catalog'] = {'path': str(catalog), 'sha256': digest(catalog.read_bytes())}
    write(Path(inputs['runtime_profiles']['runtime-main']), canonical(profile))
    environment = {'kind': 'research-environment-profile-v2', 'transport': 'docker',
        'docker_binary': fixture.docker, 'docker_endpoint': fixture.endpoint, 'daemon_id': fixture.daemon_id,
        'image_id': fixture.base_id, 'platform': fixture.platform, 'uid': 1000, 'gid': 1000, 'ssh': None}
    write(Path(inputs['environment_profiles']['lab-main']), canonical(environment))
    scope = fixture_scope(inputs_path)
    scope['access'][0]['identity']['manifest_sha256'] = digest(canonical(source_manifest(source)))
    scope['runtime_assignments'][0]['profile_sha256'] = digest(canonical(profile))
    scope['environments'][0]['profile_sha256'] = digest(canonical(environment))
    scope['environments'][0]['limits'].update(memory_bytes=1073741824, cpu_count=2, pids=128,
                                            workspace_bytes=1073741824, lease_seconds=LEASE)
    scope['limits']['max_worker_lease_seconds'] = LEASE
    scope['network']['provider'] = [{'protocol': 'https', 'host': PROVIDER_HOST,
        'port': provider.server.server_port, 'address_policy': {'public_only': False, 'cidrs': [PROVIDER_HOST + '/32']}}]
    resign_fixture(inputs_path, scope)
    return inputs_path


def invoke(context, boundary, prompt, result):
    from engagement_runner import Runner
    invocation = context.controller.begin_invocation(context.grant)
    boundary.runtime.invoke(prompt, invocation)
    deadline, completed = time.monotonic() + 70, None
    while time.monotonic() < deadline:
        events = boundary.runtime.observe(timeout_seconds=.1)
        completed = next((event for event in events if event['event'] == 'completed'), completed)
        if not boundary.runtime.active:
            break
    check(result, 'native invocation completed', completed is not None and completed['status'] == 'completed')
    context.controller.record_invocation_observed(context.grant, invocation,
        {'status': completed['status'], 'usage': Runner._usage(boundary.runtime)})


def run_native(root, fixture, result):
    from engagement_controller import Controller
    from engagement_runner import Runner, WorkerContext
    from engagement_native_boundary import NativeBoundary, recover_boundary
    import native_runtime_codex
    import research_environment
    bundle = tool_bundle(fixture, result)
    secret = 'fake-oslit-linux-provider-' + uuid.uuid4().hex
    provider = Provider(root / 'provider-tls', fixture.runtime, secret)
    original = {name: os.environ.get(name) for name in ('OPENAI_API_KEY', 'SSL_CERT_FILE')}
    os.environ['OPENAI_API_KEY'], os.environ['SSL_CERT_FILE'] = secret, str(provider.ca)
    boundary = context = runner = controller = None
    original_transport = native_runtime_codex.Transport
    original_subprocess = research_environment.subprocess
    executor_diagnostics = ExecutorDiagnostics(original_subprocess)
    research_environment.subprocess = executor_diagnostics
    result['native_request_errors'] = []
    native_runtime_codex.Transport = diagnostic_transport(result['native_request_errors'], (secret.encode(),))
    started = time.monotonic()
    try:
        inputs = signed_inputs(root, fixture, provider, bundle)
        controller = Controller.initialize(root / 'engagement', load_inputs(inputs))
        runner = Runner(controller)
        worker = next(row for row in controller.state()['workers'].values() if row['role'] == 'lead')
        workspace = root / 'workspace'; workspace.mkdir(mode=0o700)
        grant = controller.prepare_worker_dispatch(worker['id'], worker['generation'], workspace,
            seconds=LEASE, resources=['source-main'], adapter_id='native-runner')
        context = WorkerContext(runner, worker, grant, workspace)
        boundary = NativeBoundary(context)
        identity = boundary.start()
        result['native_execution'] = 'initialized'
        controller.record_worker_started(worker['id'], worker['generation'], identity['session_id'], workspace,
                                         owner_receipt=identity['owner_receipt'])
        result['native_identity'] = identity
        model = boundary.model_owner
        model_receipt = model.receipt(identity['session_id'])
        lab_identity = boundary.environment.receipt()
        check(result, 'actual separate model and tool containers',
              model_receipt['boundary'] == 'linux-docker-model-v1'
              and model_receipt['owner']['environment']['container_id'] != lab_identity['container_id'])
        outside = root / 'outside.txt'; write(outside, b'HOST_ONLY_MARKER\n')
        provider.command = '/usr/local/bin/python3 /input/source-main/probe.py ' + shlex.quote(str(outside)) + ' ' + str(
            provider.server.server_port) + ' ' + str(model_receipt['owner']['init']['host_pid']) + ' ' + str(boundary.proxy.port)
        invoke(context, boundary, FIRST_PROMPT, result)
        text = json.dumps(provider.requests)
        check(result, 'owned TLS provider credential and native tool outputs',
              len(provider.requests) == 2 and not provider.errors and secret not in text and 'NATIVE_PROBE=' in text)
        # Parse the JSON object from the actual tool result, not from the requested source text.
        outputs = ([row.get('output', '') for row in provider.requests[-1].get('input', [])
                    if row.get('call_id') == 'call-1'] if fixture.runtime == 'codex' else
                   [row.get('content', '') for row in provider.requests[-1].get('messages', []) if row.get('role') == 'tool'])
        output = '\n'.join(value if isinstance(value, str) else json.dumps(value) for value in outputs)
        match = re.search(r'NATIVE_PROBE=(\{[^\n]*\})', output)
        check(result, 'native tool produced structured probe result', match is not None)
        probe = json.loads(match.group(1))
        result['native_probe'] = probe
        checks = ('input_read', 'model_input_absent', 'host_file_absent', 'credential_absent',
                  'model_pid_absent', 'direct_provider_denied', 'lab_provider_denied')
        check(result, 'tool input, credential, process and provider separation',
              all(probe.get(key) is True for key in checks)
              and probe['pid_namespace_inode'] != model_receipt['owner']['init']['pid_namespace_inode']
              and provider.escapes == 0)
        # The native sandbox may deny even the proxy socket. Separately observe
        # the actual lab gate's response from the same isolated tool container.
        denied = boundary.environment.execute(['/usr/local/bin/python3', '-c',
            "import socket; s=socket.create_connection(('127.0.0.1', " + str(boundary.proxy.port) + "), timeout=2); "
            "s.sendall(b'CONNECT 127.0.0.2:" + str(provider.server.server_port) + " HTTP/1.1\\r\\nHost: 127.0.0.2\\r\\n\\r\\n'); "
            "print(s.recv(128).split(b'\\r\\n')[0].decode()); s.close()"], timeout_seconds=5)
        check(result, 'actual laboratory gate refuses the provider route', denied['status'] == 'settled'
              and denied['output'].strip() == 'HTTP/1.1 403 Unavailable')
        result['lab_provider_gate_observation'] = 'HTTP_403_from_actual_tool_container'
        context.renew(LEASE)
        boundary.renew(LEASE - 5)
        resumed = boundary.runtime.resume(identity['session_id'])
        check(result, 'same native session and model owner retained', resumed['session_id'] == identity['session_id']
              and boundary.runtime.owner_receipt() == model_receipt)
        invoke(context, boundary, SECOND_PROMPT, result)
        check(result, 'earlier conversation and laboratory artifact retained', len(provider.requests) == 4
              and (FIRST_PROMPT in json.dumps(provider.requests[2])
                   or provider.requests[2].get('previous_response_id') == 'fixture-2')
              and 'LINUX_NATIVE_FIRST_TURN' in json.dumps(provider.requests[3]) and not provider.errors)
        result['native_execution'] = 'two_invocations_completed'
        result['controlled_provider_requests'] = len(provider.requests)
        inspect_bytes = canonical(model.environment._inspect())
        public_files = [path for path in controller.root.rglob('*') if path.is_file()]
        check(result, 'synthetic credential absent from container config and host evidence',
              secret.encode() not in inspect_bytes and all(secret.encode() not in path.read_bytes() for path in public_files))
        scan = model.environment.execute(['python3', '-c',
            "import pathlib; p=b'fake-oslit-linux-provider-'; files=[x for x in pathlib.Path('/work').rglob('*') if x.is_file()]; "
            "print('MODEL_STATE_CLEAN' if all(p not in x.read_bytes() for x in files) else 'MODEL_STATE_EXPOSED')"], timeout_seconds=10)
        check(result, 'synthetic credential absent from native state', scan['status'] == 'settled'
              and scan['output'].strip() == 'MODEL_STATE_CLEAN')
        child = model.environment.execute(['python3', '-c',
            "import subprocess; p=subprocess.Popen(['python3','-c','import time; time.sleep(600)'], "
            "start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); print(p.pid)"],
            timeout_seconds=10)
        check(result, 'detached model descendant created', child['status'] == 'settled' and child['output'].strip().isdigit())
        boundary.renew(8)
        watcher = model.environment.owner.process
        watcher.kill(); watcher.wait(timeout=3)
        fault_started = time.monotonic()
        deadline = fault_started + 12
        while time.monotonic() < deadline:
            observed = model.environment._inspect(absent_ok=True)
            if observed is None or not observed['State']['Running']:
                break
            time.sleep(.2)
        check(result, 'model guardian stops namespace after exact watcher loss',
              observed is None or not observed['State']['Running'])
        result['watcher_loss'] = {'guardian_stop_seconds': round(time.monotonic() - fault_started, 3),
                                 'renewed_owner_lease_seconds': 8, 'detached_child_started': True}
        controller.revoke_worker(worker['id'], worker['generation'], reason='fixture-recovery')
        refused = False
        try:
            boundary.runtime.invoke('Must refuse after revocation.', 'after-revocation')
        except Exception as error:
            refused = getattr(error, 'code', None) == 'worker_stale'
        check(result, 'revoked native invocation refused', refused and len(provider.requests) == 4)
        reopened = Controller(controller.root)
        recovery_runner = Runner(reopened)
        current = reopened.state()
        dispatch = current['dispatches'][context.grant['dispatch_id']]
        recovered_context = WorkerContext(recovery_runner, current['workers'][worker['id']],
                                          copy.deepcopy(context.grant), workspace)
        recovery = recover_boundary(recovered_context, dispatch)
        result['recovery'] = recovery
        check(result, 'reopened controller recovers exact owner receipts', recovery.get('status') == 'settled')
        repeated = recover_boundary(recovered_context, reopened.state()['dispatches'][context.grant['dispatch_id']])
        check(result, 'receipt recovery remains idempotent', repeated.get('status') == 'settled')
        current = reopened.state()
        result['accounting'] = {'usage': current['usage'], 'resource_holds': current['resource_holds']}
        check(result, 'verified recovery releases dispatch reservation', current['usage']['reserved_worker_seconds'] == 0
              and not current['resource_holds'])
    finally:
        native_runtime_codex.Transport = original_transport
        research_environment.subprocess = original_subprocess
        known_secrets = [secret.encode()]
        if boundary is not None and boundary.native_owner is not None and fixture.runtime == 'codex':
            native = boundary.native_owner
            if native.token is not None:
                known_secrets.append(native.token.encode())
            result['native_executor_state'] = {'failure': native.failure, 'ready': native.ready,
                'transport_diagnostic': native.transport_diagnostic,
                'executor_returncode': native.executor.poll() if native.executor is not None else None,
                'bridge_returncode': native.bridge.poll() if native.bridge is not None else None}
        if controller is not None:
            try:
                result['environment_operation_diagnostics'] = environment_diagnostics(controller, tuple(known_secrets))
            except Exception as error:
                result['environment_operation_diagnostics'] = {'status': 'unavailable', 'error': error_code(error)}
                result['status'] = 'failed'
        if boundary is not None:
            result['recovery_identities'] = {}
            readers = {
                'model_owner': lambda: boundary.model_owner.receipt() if boundary.model_owner is not None else boundary.owner_receipt,
                'laboratory': lambda: boundary.environment.receipt() if boundary.environment is not None else None,
            }
            for name, readback in readers.items():
                try:
                    receipt = readback()
                    if receipt is None:
                        result['recovery_identities'][name] = {'status': 'not_observed'}
                    else:
                        safe_publication(canonical(receipt), known_secrets=(secret.encode(),))
                        result['recovery_identities'][name] = {'status': 'observed', 'receipt': receipt}
                except Exception as error:
                    result['recovery_identities'][name] = {'status': 'unavailable', 'error': error_code(error)}
            try:
                readback = boundary.finish()
                result['boundary_cleanup'] = readback
                if readback.get('cleanup') != 'verified':
                    result['status'] = 'failed'
                if context is not None and result.get('recovery', {}).get('status') != 'settled':
                    result['partial_settlement'] = runner._settle(context, boundary, started)
            except Exception as error:
                result['boundary_cleanup_error'] = error_code(error)
                result['status'] = 'failed'
        result['native_executor_stderr'] = executor_diagnostics.finish(tuple(known_secrets))
        provider.close()
        for name, value in original.items():
            if value is None:os.environ.pop(name, None)
            else:os.environ[name] = value
        result['controlled_provider_requests'] = len(provider.requests)
        result['controlled_provider_errors'] = provider.errors
        safe_publication(canonical(result), known_secrets=tuple(known_secrets))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', choices=('codex', 'omp'), required=True)
    parser.add_argument('--platform', choices=('linux/amd64', 'linux/arm64'), required=True)
    parser.add_argument('--base-image', required=True)
    parser.add_argument('--endpoint', required=True)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = {'kind': 'linux-model-native-e2e-v1', 'classification': 'actual_native_with_owned_simulated_provider',
              'runtime': args.runtime, 'status': 'failed', 'checks': [], 'external_provider_calls': 0,
              'native_execution': 'not_started',
              'research_acceptance': 'not_run', 'image': {'status': 'failed', 'checks': []}}
    fixture = None
    try:
        fixture = prepare_image(runtime=args.runtime, platform=args.platform, base_image=args.base_image,
                                endpoint=args.endpoint, directory=args.directory, result=result['image'])
        verify_image(fixture, result['image'])
        result['image']['status'] = 'passed'
        with tempfile.TemporaryDirectory(prefix='oslit-linux-native-') as temporary:
            run_native(Path(temporary).resolve(), fixture, result)
        check(result, 'native boundary cleanup verified', result.get('boundary_cleanup', {}).get('cleanup') == 'verified')
        result['status'] = 'passed'
    except Exception as error:
        result['error'] = error_code(error)
    finally:
        if fixture is not None:
            if (result.get('boundary_cleanup_error') or result.get('boundary_cleanup', {}).get('cleanup') == 'unresolved'):
                result['image']['cleanup'] = {'status': 'unresolved', 'reason': 'native_resources_not_settled',
                                              'retained_directory': str(fixture.directory)}
                result['image']['status'] = 'failed'
            else:
                cleanup_image(fixture, result['image'])
            if result['image']['status'] != 'passed':result['status'] = 'failed'
        result['source_hashes'] = {str(path.relative_to(ROOT)): digest(path.read_bytes()) for path in
            [Path(__file__), Path(__file__).with_name('check_model_image_docker_e2e.py'),
             *sorted((ROOT / 'tools').glob('*.py')), ROOT / 'tools/native_runtime_codex_exec.mjs',
             ROOT / 'tools/native_runtime_omp_tools.mjs', ROOT / 'config/native-tool-lock.json']}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(safe_publication(canonical(result)))
    print(json.dumps({'status': result['status'], 'output': str(args.output)}))
    return result['status'] != 'passed'


if __name__ == '__main__':
    raise SystemExit(main())
