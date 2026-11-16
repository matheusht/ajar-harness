#!/usr/bin/env python3
"""Actual Linux native tools and retention against an owned TLS model fixture.

Run only on an explicit disposable Linux Docker host. Failure cases precede this
implementation in LINUX-MODEL-NATIVE-E2E.md. Only the output JSON is publishable;
the caller asset directory retains the pinned model executable and tool bundle.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shlex
import shutil
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


HELPER_BOOTSTRAP_PROBE = '''import json,os,runpy
ns=runpy.run_path('/runtime/native_runtime_bootstrap.py',run_name='oslit_diagnostic')
try: ns['_launch']()
except BaseException as error:
 allowed={'truncated','duplicate','file','pin','environment','credential_environment','size','frame','command','catalog_runtime','helper','state','workspace'}
 kinds={'ValueError','PermissionError','FileNotFoundError','FileExistsError','OSError','MemoryError'}
 category=str(error) if type(error) is ValueError and str(error) in allowed else 'other'
 kind=type(error).__name__ if type(error).__name__ in kinds else 'other'
 trace=[];tb=error.__traceback__
 while tb is not None:
  code=tb.tb_frame.f_code
  if code.co_filename=='/runtime/native_runtime_bootstrap.py': trace.append({'function':code.co_name,'line':tb.tb_lineno})
  tb=tb.tb_next
 errno=error.errno if isinstance(error,OSError) and type(error.errno) is int else None
 os.write(2,('OSLIT_BOOTSTRAP_DIAGNOSTIC '+json.dumps({'kind':kind,'category':category,'errno':errno,'frames':trace[-5:]})+'\\n').encode())
 raise SystemExit(2) from None
'''


def helper_stderr_diagnostic(content, known_secrets):
    try:
        safe_publication(content, known_secrets=known_secrets)
    except ContractError:
        return {'withheld': True}
    allowed = {'truncated', 'duplicate', 'file', 'pin', 'environment', 'credential_environment',
               'size', 'frame', 'command', 'catalog_runtime', 'helper', 'state', 'workspace', 'other'}
    kinds = {'ValueError', 'PermissionError', 'FileNotFoundError', 'FileExistsError', 'OSError', 'MemoryError', 'other'}
    functions = {'_launch', '_read', '_pairs', '_file', '_environment'}
    result = {'withheld': False}
    for line in content.splitlines():
        if not line.startswith(b'OSLIT_BOOTSTRAP_DIAGNOSTIC '):
            continue
        try:
            row = json.loads(line.split(b' ', 1)[1])
            if (set(row) != {'kind', 'category', 'errno', 'frames'} or row['kind'] not in kinds or row['category'] not in allowed
                    or row['errno'] is not None and (type(row['errno']) is not int or not 0 <= row['errno'] <= 4096)
                    or not isinstance(row['frames'], list) or len(row['frames']) > 5
                    or any(not isinstance(frame, dict) or set(frame) != {'function', 'line'}
                           or frame['function'] not in functions or type(frame['line']) is not int
                           or not 0 < frame['line'] < 10000 for frame in row['frames'])):
                raise ValueError()
            result['bootstrap'] = row
        except (ValueError, TypeError, KeyError):
            result['bootstrap'] = 'invalid'
        break
    lower = content.lower()
    result['docker_categories'] = [name for name in ('oci', 'permission denied', 'no such file',
        'not running', 'resource temporarily unavailable', 'out of memory') if name.encode() in lower]
    return result


def helper_diagnostic_self_check():
    sample = b'OSLIT_BOOTSTRAP_DIAGNOSTIC {"kind":"ValueError","category":"state","errno":null,"frames":[{"function":"_launch","line":1}]}\n'
    assert helper_stderr_diagnostic(sample, ())['bootstrap']['category'] == 'state'
    disk = b'OSLIT_BOOTSTRAP_DIAGNOSTIC {"kind":"OSError","category":"other","errno":28,"frames":[]}\n'
    assert helper_stderr_diagnostic(disk, ())['bootstrap']['errno'] == 28
    assert helper_stderr_diagnostic(b'fake-sensitive-sentinel', (b'fake-sensitive-sentinel',)) == {'withheld': True}


def diagnostic_transport(observations, known_secrets):
    from native_runtime_transport import Transport

    class ObservedTransport(Transport):
        def request(self, operation, *args, **kwargs):
            self.observed_operation = operation
            try:
                return super().request(operation, *args, **kwargs)
            except Exception as error:
                if (getattr(error, 'code', None) == 'native_response_timeout'
                        and len(observations) < 8):
                    allowed_methods = {'turn/started', 'turn/completed', 'turn/failed',
                        'thread/tokenUsage/updated', 'item/started', 'item/completed',
                        'item/tool/call', 'item/tool/callCompleted'}
                    counts = {}
                    for frame in self.deferred[:128]:
                        method = frame.get('method') if isinstance(frame, dict) else None
                        if method in allowed_methods:
                            counts[method] = counts.get(method, 0) + 1
                    observations.append({'operation_timeout': operation,
                        'error': 'native_response_timeout',
                        'deferred_event_count': len(self.deferred),
                        'deferred_method_counts': counts,
                        'queued_frame_count': self.frames.qsize(),
                        'unmatched_response_count': len(self.responses)})
                raise
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


def diagnostic_omp_frame(frame, known_secrets):
    """Keep only bounded OMP terminal/error fields; discard assistant content and tool data."""
    if not isinstance(frame, dict):
        return None
    if frame.get('type') == 'prompt_result':
        status = frame.get('status')
        if status not in ('completed', 'aborted', 'error'):
            return {'event': 'prompt_result', 'status': 'invalid'}
        row = {'event': 'prompt_result', 'status': status}
        if type(frame.get('sessionSettled')) is bool:
            row['session_settled'] = frame['sessionSettled']
        error = frame.get('error')
        if status == 'error' and isinstance(error, dict) and isinstance(error.get('message'), str) and error['message']:
            row.update(_diagnostic_omp_error(error['message'], known_secrets))
        return row
    if frame.get('type') != 'message_end':
        return None
    message = frame.get('message')
    if not isinstance(message, dict) or message.get('role') != 'assistant':
        return None
    error = message.get('errorMessage')
    if not isinstance(error, str) or not error:
        return None
    return {'event': 'message_end', 'role': 'assistant',
            **_diagnostic_omp_error(error, known_secrets)}


def _diagnostic_omp_error(error, known_secrets):
    try:
        safe_publication(canonical({'errorMessage': error}), known_secrets=known_secrets)
    except ContractError:
        return {'error_message': '[diagnostic redacted]', 'redacted': True}
    safe_error = ''.join(character if character in '\n\t' or ord(character) >= 32 else ' '
                          for character in error)
    safe_error = re.sub(r'(?i)(?:/home|/users|/private|/var/folders)/[^\s:]+', '[path]', safe_error)
    encoded = safe_error.encode('utf-8', 'replace')
    truncated = len(encoded) > 1024
    if truncated:
        safe_error = encoded[:1024].decode('utf-8', 'ignore')
    return {'error_message': safe_error, 'truncated': truncated}


def observe_omp_native_events(runtime, result, known_secrets):
    """Record selected OMP events before the runtime's unchanged normal handler."""
    transport = runtime.transport
    original = transport.on_event
    diagnostic = result.setdefault('omp_native_events', {'events': [], 'truncated': False})

    def observe(frame):
        row = diagnostic_omp_frame(frame, known_secrets)
        if row is not None:
            if len(diagnostic['events']) < 12:
                diagnostic['events'].append(row)
            else:
                diagnostic['truncated'] = True
        original(frame)

    transport.on_event = observe


def provider_request_diagnostic(method, target, headers):
    method = method if method in ('GET', 'POST') else 'other'
    path, separator, _query = target.partition('?') if isinstance(target, str) else ('', '', '')
    routes = {('GET', '/v1/models'): 'openai_models_v1',
              ('POST', '/v1/chat/completions'): 'openai_chat_completions_v1',
              ('POST', '/v1/responses'): 'openai_responses_v1'}
    return {'method': method, 'route': routes.get((method, path), 'other'),
            'query_present': bool(separator),
            'authorization_present': any(name.lower() == 'authorization' for name in headers)}


def diagnostic_omp_model_state(model, expected_base_url, expected_provider, expected_model):
    api = model.get('api')
    return {'api': api if api in ('openai-completions', 'openai-responses') else 'other',
            'base_url_matches': model.get('baseUrl') == expected_base_url,
            'provider_matches': model.get('provider') == expected_provider,
            'model_matches': model.get('id') == expected_model}


class NetworkDenialObserver:
    """Test-only replacement subclass that records bounded NetworkDenied codes."""
    def __init__(self, module):
        self.module = module
        self.maximum = 16
        self.codes = []
        self.total = 0
        self.original_type = module.NetworkDenied
        self.installed_type = None
        self.lock = threading.Lock()

    def install(self):
        observer = self
        original = self.original_type

        class ObservedNetworkDenied(original):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                value = args[0] if args else None
                code = value if isinstance(value, str) and re.fullmatch(r'[a-z_]{1,100}', value) else 'unclassified'
                with observer.lock:
                    observer.total += 1
                    if len(observer.codes) < observer.maximum:
                        observer.codes.append(code)

        self.installed_type = ObservedNetworkDenied
        self.module.NetworkDenied = ObservedNetworkDenied

    def restore(self):
        if self.installed_type is not None and self.module.NetworkDenied is self.installed_type:
            self.module.NetworkDenied = self.original_type

    def snapshot(self):
        with self.lock:
            return {'codes': list(self.codes), 'total': self.total,
                    'truncated': self.total > len(self.codes)}


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
        self.requests, self.errors, self.escapes, self.request_observations = [], [], 0, []
        self.error_frames = []
        self.public_error_codes = []
        self.json_parse_diagnostics = []
        self.discovery_requests = 0
        self.request_observation_total = 0
        self.request_observation_lock = threading.Lock()
        self.command = None
        self.autonomy = None
        self.public_frames = None
        self.autonomy_lock = threading.Lock()
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                fixture.observe_request('GET', self.path, self.headers)
                if (fixture.runtime == 'omp' and self.path == '/v1/models'
                        and self.headers.get('Authorization') == 'Bearer ' + fixture.secret):
                    fixture.discovery_requests += 1
                    body = canonical({'object': 'list', 'data': [{'id': 'fixture-model', 'object': 'model',
                        'created': 0, 'owned_by': 'fixture'}]})
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                fixture.escapes += 1
                self.send_response(403); self.end_headers()

            def do_POST(self):
                incomplete_authenticated = False
                try:
                    fixture.observe_request('POST', self.path, self.headers)
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 < size <= 2 * 1024 * 1024:
                        raise ValueError('provider_request_size')
                    read_started = datetime.now(timezone.utc)
                    raw = self.rfile.read(size)
                    read_finished = datetime.now(timezone.utc)
                    try:
                        body = json.loads(raw)
                    except json.JSONDecodeError as error:
                        if len(fixture.json_parse_diagnostics) < 8:
                            encoding = self.headers.get('Content-Encoding', 'identity').lower()
                            transfer = self.headers.get('Transfer-Encoding', 'none').lower()
                            content_type = self.headers.get('Content-Type', '').split(';', 1)[0].lower()
                            fixture.json_parse_diagnostics.append({'expected_bytes': size, 'received_bytes': len(raw),
                                'error_position': error.pos,
                                'content_encoding': encoding if encoding in ('identity', 'gzip', 'deflate', 'br') else 'other',
                                'transfer_encoding': transfer if transfer in ('none', 'chunked') else 'other',
                                'content_type': content_type if content_type in ('application/json', '') else 'other'})
                            if len(raw) < size and fixture.public_frames is not None:
                                incomplete_authenticated = (self.headers.get('Authorization') == 'Bearer ' + fixture.secret
                                    and content_type == 'application/json' and encoding == 'identity' and transfer == 'none')
                                fixture.json_parse_diagnostics[-1]['authenticated'] = incomplete_authenticated
                                fixture.json_parse_diagnostics[-1]['controller_snapshot'] = fixture.public_frames.status_snapshot(read_started, read_finished)
                        raise
                    if self.headers.get('Authorization') != 'Bearer ' + fixture.secret:
                        raise ValueError('provider_credential_missing')
                    if fixture.secret in json.dumps(body) or not fixture.command:
                        raise ValueError('provider_body_invalid')
                    fixture.requests.append(body)
                    seq = len(fixture.requests)
                    if self.path == '/v1/responses/compact' and fixture.public_frames is not None:
                        response = canonical(fixture.public_frames.compact_response(body))
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/json')
                        self.send_header('Content-Length', str(len(response)))
                        self.end_headers(); self.wfile.write(response); self.wfile.flush()
                        return
                    if seq > 4 and fixture.autonomy is None and fixture.public_frames is None:
                        raise ValueError('provider_unexpected_request')
                    command = fixture.command if seq == 1 else 'cat /work/first-turn.txt'
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/event-stream')
                    self.end_headers()
                    frames = (fixture.public_frames(body, seq, self.path) if fixture.public_frames is not None else
                              fixture.autonomy_frames(body) if seq > 4 else fixture.frames(seq, command))
                    for frame in frames:
                        self.wfile.write(frame)
                    self.wfile.flush()
                except Exception as error:
                    fixture.errors.append('incomplete_authenticated_request' if incomplete_authenticated else error_code(error))
                    public_codes = {'public_lane_unavailable', 'source_output_not_observed',
                        'helper_not_completed', 'helper_output_not_observed', 'helper_authority_not_observed',
                        'review_packet_not_observed', 'review_packet_invalid', 'public_compaction_unqualified'}
                    if str(error) in public_codes and len(fixture.public_error_codes) < 8:
                        fixture.public_error_codes.append(str(error))
                    import traceback
                    if len(fixture.error_frames) < 8:
                        fixture.error_frames.append([{'file': Path(frame.filename).name, 'line': frame.lineno,
                            'function': frame.name} for frame in traceback.extract_tb(error.__traceback__)[-6:]])
                    self.close_connection = True

        self.server = ThreadingHTTPServer((PROVIDER_HOST, 0), Handler)
        self.server.daemon_threads = True
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certificate, key)
        self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def observe_request(self, method, target, headers):
        row = provider_request_diagnostic(method, target, headers)
        with self.request_observation_lock:
            self.request_observation_total += 1
            if len(self.request_observations) < 16:
                self.request_observations.append(row)

    def request_snapshot(self):
        with self.request_observation_lock:
            return {'total': self.request_observation_total, 'events': list(self.request_observations),
                    'truncated': self.request_observation_total > len(self.request_observations)}

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

    def autonomy_frames(self, body):
        """Route independent native sessions without making provider output a model claim."""
        raw = json.dumps(body)
        previous = body.get('previous_response_id', '')
        child = 'internal helper acting under the parent' in raw or previous.startswith('autonomy-child-')
        hold = False
        with self.autonomy_lock:
            if child and self.autonomy.get('hold_next_child'):
                self.autonomy['hold_next_child'] = False
                hold = True
        if hold:
            self.autonomy['child_held'].set()
            if not self.autonomy['child_release'].wait(15):
                raise ValueError('fixture_child_release_timeout')
        with self.autonomy_lock:
            state = self.autonomy
            lane = 'child' if child else 'parent'
            count = state[lane]
            state[lane] += 1
            identity = 'autonomy-' + lane + '-' + str(count)
            if child and count == 0:
                name, arguments = 'engagement_knowledge', {'action': 'read', 'version': state['version'], 'materialize': True}
            elif not child and count == 0:
                name, arguments = 'engagement_helper', {'action': 'spawn', 'prompt': 'Read the owned fixture reference.'}
            elif not child and count == 2:
                name, arguments = 'engagement_helper', {'action': 'read', 'helper_id': state['helper_id']}
            elif not child and state.get('next_parent_action'):
                name, arguments = state.pop('next_parent_action')
            else:
                name, arguments = None, None
            if self.runtime == 'codex':
                item = ({'id': 'fc_' + identity, 'type': 'function_call', 'call_id': 'call-' + identity,
                         'name': name, 'arguments': json.dumps(arguments)} if name else
                        {'id': 'msg_' + identity, 'type': 'message', 'role': 'assistant',
                         'content': [{'type': 'output_text', 'text': 'Owned fixture complete.'}]})
                response = {'id': identity, 'object': 'response', 'status': 'completed', 'output': [item],
                            'usage': {'input_tokens': 10, 'output_tokens': 10, 'total_tokens': 20}}
                frames = [{'type': 'response.created', 'response': {**response, 'status': 'in_progress', 'output': []}},
                          {'type': 'response.output_item.added', 'output_index': 0, 'item': item},
                          {'type': 'response.output_item.done', 'output_index': 0, 'item': item},
                          {'type': 'response.completed', 'response': response}]
                return [('event: ' + frame['type'] + '\ndata: ' + json.dumps(dict(frame, sequence_number=i)) + '\n\n').encode()
                        for i, frame in enumerate(frames)]
            delta = ({'role': 'assistant', 'tool_calls': [{'index': 0, 'id': 'call-' + identity, 'type': 'function',
                      'function': {'name': name, 'arguments': json.dumps(arguments)}}]} if name else
                     {'role': 'assistant', 'content': 'Owned fixture complete.'})
            frames = [{'delta': delta, 'finish_reason': None},
                      {'delta': {}, 'finish_reason': 'tool_calls' if name else 'stop'}]
            return [('data: ' + json.dumps({'id': identity, 'object': 'chat.completion.chunk', 'created': 0,
                    'model': 'fixture-model', 'choices': [{'index': 0, **frame}]}) + '\n\n').encode()
                    for frame in frames] + [b'data: [DONE]\n\n']

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)


def tool_bundle(fixture, result):
    destination = fixture.directory / 'tool-bundle'
    if fixture.runtime == 'codex':
        (destination / 'bin').mkdir(parents=True, mode=0o700)
        executable = Path(fixture.context_receipt['profile_fields']['executable']['path'])
        os.link(executable, destination / 'bin/codex')
        shutil.copyfile(executable.parent.parent / 'codex-package.json', destination / 'codex-package.json')
        (destination / 'codex-resources').mkdir()
        shutil.copy2(executable.parent.parent / 'codex-resources/bwrap', destination / 'codex-resources/bwrap')
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


def omp_fixture_catalog(provider_url, context_window=32768, api='openai-completions'):
    return canonical({'providers': {'openai': {'baseUrl': provider_url + '/v1',
        'api': api, 'apiKey': 'OPENAI_API_KEY', 'models': [{'id': 'fixture-model', 'name': 'Owned fixture',
            'reasoning': False, 'input': ['text'], 'supportsTools': True,
            'contextWindow': context_window, 'maxTokens': 1024,
            'cost': {'input': 0, 'output': 0, 'cacheRead': 0, 'cacheWrite': 0}}]}}})


def validate_omp_fixture_catalog(content, provider_url, secret, api='openai-completions'):
    catalog = json.loads(content)
    provider = catalog['providers']['openai']
    if (provider.get('baseUrl') != provider_url + '/v1' or provider.get('api') != api
            or provider.get('apiKey') != 'OPENAI_API_KEY'
            or [model.get('id') for model in provider.get('models', [])] != ['fixture-model']
            or secret.encode() in content):
        raise ValueError('omp_fixture_model_catalog_invalid')


def signed_inputs(root, fixture, provider, bundle, codex_tool_policy=None):
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
            'limits': {'memory_bytes': 1610612736 if fixture.runtime == 'omp' else 1073741824, 'cpu_count': 2, 'pids': 128,
                       'workspace_bytes': 1073741824 if fixture.runtime == 'omp' else 134217728}}}
    if fixture.runtime == 'omp':
        catalog = root / 'models.yml'
        public = getattr(fixture, 'public_run', False)
        api = 'openai-responses' if public else 'openai-completions'
        catalog_content = omp_fixture_catalog(provider.origin, 131072 if public else 32768, api)
        validate_omp_fixture_catalog(catalog_content, provider.origin, provider.secret, api)
        write(catalog, catalog_content)
        profile['model_catalog'] = {'path': str(catalog), 'sha256': digest(catalog.read_bytes())}
    write(Path(inputs['runtime_profiles']['runtime-main']), canonical(profile))
    environment = {'kind': 'research-environment-profile-v2', 'transport': 'docker',
        'docker_binary': fixture.docker, 'docker_endpoint': fixture.endpoint, 'daemon_id': fixture.daemon_id,
        'image_id': fixture.base_id, 'platform': fixture.platform, 'uid': 1000, 'gid': 1000, 'ssh': None}
    if codex_tool_policy is not None:
        environment['codex_tool_policy'] = codex_tool_policy
    write(Path(inputs['environment_profiles']['lab-main']), canonical(environment))
    scope = fixture_scope(inputs_path)
    if getattr(fixture, 'autonomy', False):
        from check_owned_lab_state_e2e import scope_with_artifact
        scope = scope_with_artifact(scope)
        scope['authority_policy'] = 'research-autonomy-v1'
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


def policy_readback(fixture, tool_container_id, model_container_id, selected_policy, expected_seccomp):
    """Publish policy names and hashes only, never Docker's serialized policy blob."""
    import hashlib
    import json
    from codex_tool_policy import APPARMOR_PROFILE

    def inspect(container_id):
        observed = subprocess.run([fixture.docker, '--host', fixture.endpoint, 'container',
            'inspect', container_id], check=True, capture_output=True, text=True, timeout=10)
        rows = json.loads(observed.stdout)
        if len(rows) != 1:
            raise ValueError('container_policy_readback_invalid')
        info = rows[0]
        host = info['HostConfig']
        security = host.get('SecurityOpt') or []
        seccomp = [value[len('seccomp='):] for value in security
                   if isinstance(value, str) and value.startswith('seccomp=')]
        parsed, seccomp_kind, seccomp_digest = None, 'missing', None
        if len(seccomp) == 1:
            if seccomp[0] == 'unconfined':
                seccomp_kind = 'unconfined'
            else:
                try:
                    parsed = json.loads(seccomp[0])
                    seccomp_kind = 'json'
                    seccomp_digest = 'sha256:' + hashlib.sha256(
                        json.dumps(parsed, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
                except (ValueError, TypeError):
                    seccomp_kind = 'invalid'
        return {'apparmor_profile': info.get('AppArmorProfile'),
            'cap_add': sorted(host.get('CapAdd') or []), 'cap_drop': sorted(host.get('CapDrop') or []),
            'security_opt_names': sorted('no-new-privileges' if value in (
                'no-new-privileges', 'no-new-privileges=true', 'no-new-privileges:true')
                else 'apparmor' if value.startswith('apparmor=')
                else 'seccomp' if value.startswith('seccomp=') else 'other'
                for value in security if isinstance(value, str)),
            'seccomp_kind': seccomp_kind, 'seccomp_sha256': seccomp_digest,
            'seccomp_matches_codex_policy': parsed == expected_seccomp,
            'codex_tool_policy_applied': info.get('AppArmorProfile') == APPARMOR_PROFILE
                and host.get('CapAdd') in (None, [])
                and sorted(host.get('CapDrop') or []) == ['ALL']
                and parsed == expected_seccomp}

    tool, model = inspect(tool_container_id), inspect(model_container_id)
    model_policy_is_default = (model['apparmor_profile'] != APPARMOR_PROFILE
        and model['cap_add'] == [] and model['cap_drop'] == ['ALL']
        and model['security_opt_names'] == ['no-new-privileges']
        and model['seccomp_matches_codex_policy'] is False)
    return {'signed_policy': selected_policy, 'tool_container': tool, 'model_container': model,
        'tool_policy_verified': tool['codex_tool_policy_applied'] is True,
        'tool_apparmor_enforcement_verified_by_prepare': True,
        'model_container_separate': tool_container_id != model_container_id,
        'model_policy_is_default': model_policy_is_default}


def invoke(context, boundary, prompt, result):
    from engagement_runner import Runner
    invocation = context.controller.begin_invocation(context.grant)
    boundary.runtime.invoke(prompt, invocation)
    started = time.monotonic()
    deadline, completed = started + 70, None
    observed = []
    observed_truncated = False
    while time.monotonic() < deadline:
        events = boundary.runtime.observe(timeout_seconds=.1)
        for event in events:
            kind = event.get('event')
            if kind in ('started', 'completed', 'yielded', 'unknown', 'host_tool_cancel'):
                row = {'event': kind}
                for key in ('status', 'reason', 'resource_settlement'):
                    value = event.get(key)
                    if isinstance(value, str) and len(value) <= 128:
                        row[key] = value
                if type(event.get('session_settled')) is bool:
                    row['session_settled'] = event['session_settled']
                if type(event.get('usage_available')) is bool:
                    row['usage_available'] = event['usage_available']
                if len(observed) < 32:
                    observed.append(row)
                else:
                    observed_truncated = True
            if kind == 'completed':
                completed = event
        if not boundary.runtime.active:
            break
    result.setdefault('native_invocation_diagnostics', []).append({
        'runtime': boundary.runtime.kind,
        'phase': 'completed' if completed is not None else 'no_completion_before_deadline',
        'status': completed.get('status') if completed is not None else None,
        'active_after_wait': bool(boundary.runtime.active),
        'wait_seconds': round(time.monotonic() - started, 3),
        'events': observed, 'events_truncated': observed_truncated,
    })
    check(result, 'native invocation completed', completed is not None and completed['status'] == 'completed')
    context.controller.record_invocation_observed(context.grant, invocation,
        {'status': completed['status'], 'usage': Runner._usage(boundary.runtime)})


def verify_engagement_export(controller, root, result):
    """Export this run privately, then verify bytes, journal references and result projection."""
    import subprocess

    bundle = root / 'export'
    stage = 'export'
    try:
        exported = controller.export(bundle)
        commands = {
            'integrity': [sys.executable, str(ROOT / 'tools/check_engagement_export.py'), str(bundle)],
            'references': [sys.executable, str(ROOT / 'tools/verify_engagement_export_references.py'), str(bundle)],
            'result': [sys.executable, str(ROOT / 'tools/verify_engagement_export_references.py'),
                       str(bundle), '--check-result'],
        }
        reports = {}
        for name, command in commands.items():
            stage = name
            completed = subprocess.run(command, capture_output=True, text=True, timeout=30)
            if completed.returncode != 0:
                raise ValueError('export_' + name + '_verification_failed')
            reports[name] = json.loads(completed.stdout)
        manifest = json.loads((bundle / 'manifest.json').read_text())
        result['export_verification'] = {
            'status': 'passed' if exported['status'] == 'exported'
                and reports['integrity'].get('integrity') == 'verified'
                and reports['references'].get('status') == 'verified'
                and reports['result'].get('result_consistency_verified') is True
                else 'failed',
            'revision': exported['revision'],
            'file_count': len(manifest['files']),
            'manifest_sha256': digest((bundle / 'manifest.json').read_bytes()),
            'integrity': reports['integrity'],
            'references': reports['references'],
            'result': reports['result'],
        }
        result['checks'].append({'name': 'same engagement export integrity, references and result verified',
                                 'passed': result['export_verification']['status'] == 'passed'})
        if result['export_verification']['status'] != 'passed':
            result['status'] = 'failed'
    except Exception as error:
        result['export_verification'] = {'status': 'failed', 'error': error_code(error), 'stage': stage}


def run_native(root, fixture, result):
    from engagement_controller import Controller
    from engagement_runner import Runner, WorkerContext
    from engagement_native_boundary import NativeBoundary, recover_boundary
    from check_native_userns_probe import compare_environment
    import native_runtime_codex
    import research_environment
    bundle = tool_bundle(fixture, result)
    if fixture.runtime == 'codex':
        from check_codex_sandbox_policy_diagnostic import run_diagnostic, verified_bwrap_asset
        try:
            bwrap = Path(bundle['path']) / 'codex-resources/bwrap'
            expected = fixture.context_receipt.get('runtime_manifest', {}).get(
                'codex-resources/bwrap', {}).get('sha256')
            installed = verified_bwrap_asset(bwrap, expected)
        except Exception:
            expected, installed = None, None
        if not expected or installed != expected:
            result['codex_sandbox_policy_diagnostic'] = {
                'kind': 'codex-sandbox-policy-diagnostic-v1',
                'classification': 'diagnostic_only', 'qualification': False,
                'status': 'failed', 'error': 'bwrap_asset_identity_invalid',
                'cleanup': 'not_started'}
        else:
            try:
                result['codex_sandbox_policy_diagnostic'] = run_diagnostic(
                    fixture.docker, fixture.endpoint, fixture.image_id, expected)
            except Exception:
                result['codex_sandbox_policy_diagnostic'] = {
                    'kind': 'codex-sandbox-policy-diagnostic-v1',
                    'classification': 'diagnostic_only', 'qualification': False,
                    'status': 'failed', 'error': 'diagnostic_integration_error',
                    'cleanup': 'unresolved'}
            if (os.environ.get('OSLIT_CODEX_POLICY_REPLAY') == '1'
                    and getattr(fixture, 'codex_tool_policy', None) is None):
                from check_codex_sandbox_policy_candidate import run_candidate
                try:
                    result['codex_policy_candidate'] = run_candidate(
                        fixture.docker, fixture.endpoint, fixture.image_id, expected,
                        allow_host_policy_load=True, parser='/usr/sbin/apparmor_parser')
                except Exception:
                    result['codex_policy_candidate'] = {
                        'classification': 'diagnostic_only', 'qualification': False,
                        'status': 'failed', 'error': 'candidate_integration_error',
                        'cleanup': 'unresolved'}
    secret = 'fake-oslit-linux-provider-' + uuid.uuid4().hex
    provider = Provider(root / 'provider-tls', fixture.runtime, secret)
    original = {name: os.environ.get(name) for name in ('OPENAI_API_KEY', 'SSL_CERT_FILE')}
    os.environ['OPENAI_API_KEY'], os.environ['SSL_CERT_FILE'] = secret, str(provider.ca)
    boundary = context = runner = controller = None
    denial_observer = None
    original_transport = native_runtime_codex.Transport
    original_subprocess = research_environment.subprocess
    executor_diagnostics = ExecutorDiagnostics(original_subprocess)
    research_environment.subprocess = executor_diagnostics
    result['native_request_errors'] = []
    native_runtime_codex.Transport = diagnostic_transport(result['native_request_errors'], (secret.encode(),))
    started = time.monotonic()
    try:
        codex_tool_policy = getattr(fixture, 'codex_tool_policy', None)
        inputs = signed_inputs(root, fixture, provider, bundle, codex_tool_policy)
        controller = Controller.initialize(root / 'engagement', load_inputs(inputs))
        if fixture.runtime == 'omp':
            frozen_catalog = controller.root / 'contract/runtimes/runtime-main.models.yml'
            validate_omp_fixture_catalog(frozen_catalog.read_bytes(), provider.origin, secret)
        runner = Runner(controller)
        worker = next(row for row in controller.state()['workers'].values() if row['role'] == 'lead')
        workspace = root / 'workspace'; workspace.mkdir(mode=0o700)
        grant = controller.prepare_worker_dispatch(worker['id'], worker['generation'], workspace,
            seconds=LEASE, resources=['source-main'], adapter_id='native-runner')
        context = WorkerContext(runner, worker, grant, workspace)
        if fixture.runtime == 'omp':
            import engagement_network
            denial_observer = NetworkDenialObserver(engagement_network)
            denial_observer.install()
        boundary = NativeBoundary(context)
        try:
            identity = boundary.start()
        finally:
            result['userns_diagnostic'] = (compare_environment(boundary.environment)
                if boundary.environment is not None else {'classification': 'environment_unavailable'})
        if fixture.runtime == 'omp':
            observe_omp_native_events(boundary.runtime, result, (secret.encode(),))
            state = boundary.runtime._read_state()
            model_state = state.get('model') or {}
            result['omp_native_model_state'] = diagnostic_omp_model_state(model_state,
                provider.origin + '/v1', 'openai', 'fixture-model')
            result['omp_provider_requests_before_prompt'] = provider.request_snapshot()
            result['omp_network_denials_before_prompt'] = denial_observer.snapshot()
        result['native_execution'] = 'initialized'
        controller.record_worker_started(worker['id'], worker['generation'], identity['session_id'], workspace,
                                         owner_receipt=identity['owner_receipt'])
        result['native_identity'] = identity
        model = boundary.model_owner
        model_receipt = model.receipt(identity['session_id'])
        lab_identity = boundary.environment.receipt()
        if fixture.runtime == 'codex' and codex_tool_policy is not None:
            from codex_tool_policy import load_policy
            policy = load_policy()
            result['codex_tool_policy_readback'] = policy_readback(
                fixture, lab_identity['container_id'],
                model_receipt['owner']['environment']['container_id'],
                codex_tool_policy, policy['seccomp_document'])
            check(result, 'signed Codex policy observed on tool container and separate model container',
                result['codex_tool_policy_readback']['tool_policy_verified']
                and result['codex_tool_policy_readback']['model_container_separate']
                and result['codex_tool_policy_readback']['model_policy_is_default'])
        check(result, 'actual separate model and tool containers',
              model_receipt['boundary'] == 'linux-docker-model-v1'
              and model_receipt['owner']['environment']['container_id'] != lab_identity['container_id'])
        outside = root / 'outside.txt'; write(outside, b'HOST_ONLY_MARKER\n')
        provider.command = '/usr/local/bin/python3 /input/source-main/probe.py ' + shlex.quote(str(outside)) + ' ' + str(
            provider.server.server_port) + ' ' + str(model_receipt['owner']['init']['host_pid']) + ' ' + str(boundary.proxy.port)
        if fixture.runtime == 'omp':
            try:
                invoke(context, boundary, FIRST_PROMPT, result)
            finally:
                result['omp_prompt_request_diagnostic'] = {
                    'provider_requests_before': result['omp_provider_requests_before_prompt'],
                    'provider_requests_after': provider.request_snapshot(),
                    'network_denials_before': result['omp_network_denials_before_prompt'],
                    'network_denials_after': denial_observer.snapshot(),
                }
        else:
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
        if getattr(fixture, 'autonomy', False):
            from engagement_knowledge import KnowledgeLibrary
            boundary._knowledge_shared = KnowledgeLibrary(root / 'shared-library', corpus_root=None)
            boundary._knowledge_local = KnowledgeLibrary(controller.root / 'knowledge', corpus_root=None)
            reference = b'Owned benign native helper reference.\n'
            selected = boundary._knowledge_shared.retain(reference, origin='fixture:owned', title='Owned fixture')
            provider.autonomy = {'version': selected['version'], 'parent': 0, 'child': 0}
            if fixture.runtime == 'omp':
                create_helper = boundary.runtime.create_helper
                def sample_omp_workspace(stage):
                    owner = boundary.model_owner
                    sample = '''import json,os,pathlib
s=os.statvfs('/work');p=pathlib.Path('/sys/fs/cgroup')
print(json.dumps({'total_bytes':s.f_blocks*s.f_frsize,'available_bytes':s.f_bavail*s.f_frsize,
 'memory_current':int((p/'memory.current').read_text()),'pids_current':int((p/'pids.current').read_text())}))'''
                    try:
                        observed = owner.environment._run(['container', 'exec', '--user', '0:0',
                            owner.environment.identity['container_id'], 'python3', '-I', '-S', '-c', sample],
                            timeout=5, output_limit=1024)
                        values = json.loads(observed['output'])
                        if (observed['returncode'] != 0 or set(values) != {'total_bytes', 'available_bytes',
                                'memory_current', 'pids_current'} or
                                any(type(value) is not int or value < 0 for value in values.values())):
                            raise ValueError('fixture_workspace_sample_invalid')
                        result.setdefault('omp_workspace_samples', []).append({'stage': stage, **values})
                    except Exception:
                        result.setdefault('omp_workspace_samples', []).append({'stage': stage, 'status': 'unavailable'})
                def observe_helper(helper_id):
                    sample_omp_workspace('before_helper_launch')
                    owner = boundary.model_owner
                    original_model_launch = owner.launch_model
                    diagnostic = result['omp_helper_bootstrap'] = {'launched': False, 'acknowledgment': 'not_observed'}
                    def observe_model_launch(command, public_environment, binding, *, helper_id=None):
                        from contextlib import contextmanager
                        import native_runtime_linux
                        expected = str(owner.paths.state) + '-helper-' + str(helper_id)
                        diagnostic.update(helper_id_valid=bool(re.fullmatch(r'[0-9a-f]{32}', str(helper_id))),
                            home_matches=public_environment.get('HOME') == expected,
                            state_matches=public_environment.get('PI_CODING_AGENT_DIR') == expected,
                            guard_entered=False, guard_body_finished=False, frame_write_completed=False)
                        try:
                            binding.check()
                            diagnostic['binding_available'] = True
                        except Exception:
                            diagnostic['binding_available'] = False
                        launch_stdio = owner.environment.launch_stdio
                        guard, write_pipe = owner.guard, native_runtime_linux.write_pipe
                        launch_thread = threading.get_ident()
                        process_ref = []
                        stderr_capture = {'content': bytearray(), 'thread': None}
                        @contextmanager
                        def observed_guard():
                            with guard():
                                if threading.get_ident() == launch_thread:
                                    diagnostic['guard_entered'] = True
                                try:
                                    yield
                                finally:
                                    if threading.get_ident() == launch_thread:
                                        diagnostic['guard_body_finished'] = True
                        def observed_write(pipe, data):
                            written = write_pipe(pipe, data)
                            if (threading.get_ident() == launch_thread and process_ref
                                    and pipe is process_ref[0].stdin):
                                diagnostic['frame_write_completed'] = True
                            return written
                        class ObservedOutput:
                            def __init__(self, stream): self.stream = stream
                            def __getattr__(self, name): return getattr(self.stream, name)
                            def readline(self, *args):
                                value = self.stream.readline(*args)
                                diagnostic['acknowledgment'] = ('ready' if value == b'{"native_model_bootstrap":"ready"}\n'
                                    else 'empty' if not value else 'unexpected')
                                return value
                        def observed_stdio(*args, **kwargs):
                            if not str(kwargs.get('role', '')).startswith('model_helper_'):
                                return launch_stdio(*args, **kwargs)
                            if not getattr(fixture, 'diagnostic_bootstrap', False):
                                process = launch_stdio(*args, **kwargs)
                                diagnostic.update(instrumented_bootstrap=False, launched=True)
                                process.stdout = ObservedOutput(process.stdout)
                                process_ref.append(process)
                                return process
                            argv = list(args[0])
                            if not argv or argv[-1] != '/runtime/native_runtime_bootstrap.py':
                                raise ValueError('fixture_bootstrap_command_invalid')
                            argv[-1:] = ['-c', HELPER_BOOTSTRAP_PROBE]
                            real_popen = research_environment.subprocess.Popen
                            def diagnostic_popen(command, *inner_args, **inner_kwargs):
                                selected = (threading.get_ident() == launch_thread and isinstance(command, list)
                                            and HELPER_BOOTSTRAP_PROBE in command
                                            and inner_kwargs.get('stderr') == research_environment.subprocess.DEVNULL)
                                if selected:
                                    inner_kwargs['stderr'] = research_environment.subprocess.PIPE
                                process = real_popen(command, *inner_args, **inner_kwargs)
                                if selected:
                                    def drain():
                                        try:
                                            while chunk := process.stderr.read(4096):
                                                available = max(0, 4096 - len(stderr_capture['content']))
                                                stderr_capture['content'].extend(chunk[:available])
                                        finally:
                                            process.stderr.close()
                                    stderr_capture['thread'] = threading.Thread(target=drain, daemon=True)
                                    stderr_capture['thread'].start()
                                return process
                            research_environment.subprocess.Popen = diagnostic_popen
                            try:
                                process = launch_stdio(argv, *args[1:], **kwargs)
                            finally:
                                research_environment.subprocess.Popen = real_popen
                            diagnostic['instrumented_bootstrap'] = True
                            diagnostic['launched'] = True
                            process.stdout = ObservedOutput(process.stdout)
                            process_ref.append(process)
                            return process
                        owner.environment.launch_stdio = observed_stdio
                        owner.guard = observed_guard
                        native_runtime_linux.write_pipe = observed_write
                        try:
                            return original_model_launch(command, public_environment, binding, helper_id=helper_id)
                        except Exception as error:
                            diagnostic['error'] = error_code(error)
                            diagnostic['process_exited'] = bool(process_ref and process_ref[0].poll() is not None)
                            if stderr_capture['thread'] is not None:
                                stderr_capture['thread'].join(timeout=1)
                                diagnostic['stderr'] = helper_stderr_diagnostic(bytes(stderr_capture['content']), (secret.encode(),))
                            counters = '''import json,os,pathlib
p=pathlib.Path('/sys/fs/cgroup');out={}
for name in ('memory.current','pids.current'):
 try: out[name]=int((p/name).read_text().strip())
 except (OSError,ValueError): pass
for name in ('memory.events','pids.events'):
 try: out[name]={k:int(v) for k,v in (line.split() for line in (p/name).read_text().splitlines())}
 except (OSError,ValueError): pass
for name,path in (('work','/work'),('tmp','/tmp')):
 try:
  s=os.statvfs(path);out[name]={'available_bytes':s.f_bavail*s.f_frsize,'total_bytes':s.f_blocks*s.f_frsize,'available_inodes':s.f_favail,'total_inodes':s.f_files}
 except OSError: pass
print(json.dumps(out))'''
                            try:
                                observed = owner.environment._run(['container', 'exec', '--user', '0:0',
                                    owner.environment.identity['container_id'], 'python3', '-I', '-S', '-c', counters],
                                    timeout=5, output_limit=4096)
                                values = json.loads(observed['output'])
                                if (not isinstance(values, dict) or set(values) - {'memory.current', 'pids.current', 'memory.events', 'pids.events', 'work', 'tmp'}
                                        or any(not (type(value) is int and value >= 0 or isinstance(value, dict)
                                            and all(isinstance(key, str) and re.fullmatch(r'[a-z_]{1,32}', key)
                                                    and type(number) is int and number >= 0 for key, number in value.items()))
                                               for value in values.values())):
                                    raise ValueError('fixture_cgroup_invalid')
                                diagnostic['cgroup'] = {'status': observed['status'], 'returncode': observed['returncode'],
                                    'values': values}
                            except Exception:
                                diagnostic['cgroup'] = {'status': 'unavailable'}
                            raise
                        finally:
                            owner.environment.launch_stdio = launch_stdio
                            owner.guard = guard
                            native_runtime_linux.write_pipe = write_pipe
                    owner.launch_model = observe_model_launch
                    try:
                        child = create_helper(helper_id)
                    finally:
                        owner.launch_model = original_model_launch
                    diagnostic = {}
                    observe_omp_native_events(child, diagnostic, (secret.encode(),))
                    result['omp_helper_native_events'] = diagnostic['omp_native_events']
                    return child
                boundary.runtime.create_helper = observe_helper
            invoke(context, boundary, 'Use a helper for the owned fixture reference.', result)
            deadline = time.monotonic() + 45
            unknown_event = False
            while time.monotonic() < deadline:
                helpers = list(controller.state()['helpers'].values())
                if helpers and helpers[0].get('status') in ('completed', 'failed', 'stopped'):
                    break
                events = boundary.runtime.observe(timeout_seconds=.1)
                unknown_event |= any(event.get('event') == 'unknown' for event in events)
            if fixture.runtime == 'omp':
                sample_omp_workspace('after_first_helper')
            check(result, 'helper wait retains a known parent transport', not unknown_event)
            state = controller.state()
            helpers = list(state['helpers'].values())
            deliveries = state.get('knowledge_deliveries', [])
            result['autonomy_diagnostic'] = {'provider_lanes': {key: provider.autonomy[key] for key in ('parent', 'child')},
                'helpers': [{key: row.get(key) for key in ('status', 'reason', 'parent_session_id', 'session_id', 'owner_receipt_sha256')}
                            for row in helpers],
                'delivery_count': len(deliveries), 'provider_errors': provider.errors[:8],
                'tool_error_codes': sorted(set(re.findall(r'\b(?:native|helper|worker|knowledge)_[a-z_]{3,80}\b',
                                                          json.dumps(provider.requests))))[:20]}
            check(result, 'native helper completes under parent authority', len(helpers) == 1
                  and helpers[0].get('status') == 'completed' and helpers[0].get('worker_id') == worker['id']
                  and helpers[0].get('parent_session_id') == identity['session_id'])
            helper_usage = helpers[0].get('usage', {})
            check(result, 'native helper reports usage totals',
                  type((helper_usage.get('tokens') or {}).get('total')) is int)
            def helper_usage_count():
                return sum(event['type'] == 'helper_observed' and event['payload']['helper_id'] == helpers[0]['helper_id']
                           and event['payload']['action'] == 'usage' for event in controller._events())
            before_count = helper_usage_count()
            before_tokens = controller.state()['usage']['tokens']
            controller.record_helper(context.grant, helpers[0]['helper_id'], 'usage', {'usage': helper_usage})
            check(result, 'replayed helper cumulative usage is counted once', before_count > 0
                  and helper_usage_count() == before_count and controller.state()['usage']['tokens'] == before_tokens)
            provider.autonomy['helper_id'] = helpers[0]['helper_id']
            invoke(context, boundary, 'Read the completed owned helper result.', result)
            check(result, 'parent reads helper through native tool', provider.autonomy['parent'] == 4
                  and helpers[0]['helper_id'] in json.dumps(provider.requests))
            check(result, 'native helper materializes exact retained reference', any(
                item.get('version') == selected['version'] and item.get('action') == 'delivery'
                and item.get('materialization', {}).get('status') == 'materialized' for item in deliveries))
            readback = boundary.environment.execute(['cat', '/work/knowledge/' + selected['version'][7:] + '/reference.bin'], timeout_seconds=10)
            check(result, 'materialized reference bytes verified', readback['status'] == 'settled'
                  and readback.get('output', '').encode() == reference)
            revised = b'Owned revised native helper reference.\n'
            updated = boundary._knowledge_shared.retain(revised, origin='fixture:owned', title='Owned fixture')
            check(result, 'same-name source update selects a new immutable version', updated['version'] != selected['version'])
            for version in (selected['version'], updated['version']):
                before_deliveries = len(controller.state().get('knowledge_deliveries', []))
                provider.autonomy['next_parent_action'] = ('engagement_knowledge',
                    {'action': 'read', 'version': version, 'materialize': True})
                invoke(context, boundary, 'Read the selected owned reference version.', result)
                check(result, 'native read selected version delivered', any(
                    item.get('version') == version and item.get('action') == 'delivery'
                    and item.get('materialization', {}).get('status') == 'materialized'
                    for item in controller.state().get('knowledge_deliveries', [])[before_deliveries:]))
            for record, expected in ((selected, reference), (updated, revised)):
                readback = boundary.environment.execute(['cat', '/work/knowledge/' + record['version'][7:] + '/reference.bin'],
                    timeout_seconds=10)
                check(result, 'selected immutable version retains exact bytes', readback['status'] == 'settled'
                      and readback.get('output', '').encode() == expected)
            provider.autonomy.update(hold_next_child=True, child_held=threading.Event(), child_release=threading.Event())
            provider.autonomy['next_parent_action'] = ('engagement_helper',
                {'action': 'spawn', 'prompt': 'Wait with the owned test provider until stopped.'})
            try:
                invoke(context, boundary, 'Start a second helper for the owned stop fixture.', result)
                rows = list(controller.state()['helpers'].values())
                check(result, 'second helper created for active stop', len(rows) == 2)
                second = next(row for row in rows if row['helper_id'] != helpers[0]['helper_id'])
                deadline = time.monotonic() + 30
                while not provider.autonomy['child_held'].is_set() and time.monotonic() < deadline:
                    boundary.runtime.observe(timeout_seconds=.1)
                check(result, 'second helper reaches the held native provider request', provider.autonomy['child_held'].is_set())
                def release_on_stop():
                    job = boundary.helpers.jobs.get(second['helper_id'])
                    if job is not None:
                        job['stop'].wait(12)
                    provider.autonomy['child_release'].set()
                releaser = threading.Thread(target=release_on_stop, daemon=True); releaser.start()
                provider.autonomy['next_parent_action'] = ('engagement_helper',
                    {'action': 'stop', 'helper_id': second['helper_id']})
                invoke(context, boundary, 'Stop the active owned test helper.', result)
                releaser.join(timeout=15)
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    stopped = controller.state()['helpers'][second['helper_id']]
                    if stopped.get('status') in ('stopped', 'failed', 'completed'):
                        break
                    boundary.runtime.observe(timeout_seconds=.1)
                check(result, 'active native helper stops and releases its session',
                      stopped.get('status') == 'stopped' and second['helper_id'] not in boundary.helpers.jobs)
            finally:
                provider.autonomy['child_release'].set()
            result['autonomy_coverage'] = {'helper_and_reference': 'passed', 'provider': 'scripted',
                'duplicate_helper_usage': 'passed',
                'reference_version_update': 'passed',
                'active_helper_stop': 'passed',
                'not_covered': ['live_model_direction', 'fetch_retention_failure',
                                'independent_technique_review', 'reviewed_closure']}
        result['native_execution'] = 'two_invocations_completed'
        result['controlled_provider_requests'] = len(provider.requests)
        result['controlled_provider_discovery_requests'] = provider.discovery_requests
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
        requests_before_refusal = len(provider.requests)
        refused = False
        try:
            boundary.runtime.invoke('Must refuse after revocation.', 'after-revocation')
        except Exception as error:
            refused = getattr(error, 'code', None) == 'worker_stale'
        check(result, 'revoked native invocation refused', refused and len(provider.requests) == requests_before_refusal)
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
        if denial_observer is not None:
            denial_observer.restore()
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
            if fixture.runtime == 'omp':
                try:
                    transport = boundary.runtime.transport
                    laboratory_channel = getattr(getattr(boundary, 'proxy', None), 'channel', None)
                    provider_channel = getattr(getattr(boundary, 'model_proxy', None), 'channel', None)
                    result['omp_runtime_diagnostic'] = {
                        'runtime_ready': bool(boundary.runtime.ready),
                        'runtime_active': bool(boundary.runtime.active),
                        'pending_completion': boundary.runtime.pending_completion
                            if boundary.runtime.pending_completion in ('completed', 'aborted', 'error') else None,
                        'transport_failure': transport.failure
                            if isinstance(transport.failure, str) and re.fullmatch(r'[a-z_]{1,100}', transport.failure)
                            else None,
                        'process_returncode': transport.process.poll(),
                        'provider_requests': len(provider.requests),
                        'provider_errors': provider.errors[:8],
                        'provider_errors_truncated': len(provider.errors) > 8,
                        'provider_escapes': provider.escapes,
                        'proxy_channel_failures': {
                            'laboratory': laboratory_channel.failure
                                if laboratory_channel is not None and isinstance(laboratory_channel.failure, str)
                                and re.fullmatch(r'[a-z_]{1,100}', laboratory_channel.failure) else None,
                            'model_provider': provider_channel.failure
                                if provider_channel is not None and isinstance(provider_channel.failure, str)
                                and re.fullmatch(r'[a-z_]{1,100}', provider_channel.failure) else None,
                        },
                    }
                except Exception:
                    result['omp_runtime_diagnostic'] = {'status': 'unavailable'}
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
        if controller is not None:
            verify_engagement_export(controller, root, result)
        result['native_executor_stderr'] = executor_diagnostics.finish(tuple(known_secrets))
        provider.close()
        for name, value in original.items():
            if value is None:os.environ.pop(name, None)
            else:os.environ[name] = value
        result['controlled_provider_requests'] = len(provider.requests)
        result['controlled_provider_discovery_requests'] = provider.discovery_requests
        result['controlled_provider_errors'] = provider.errors
        safe_publication(canonical(result), known_secrets=tuple(known_secrets))


def main(*, classify_result=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', choices=('codex', 'omp'), required=True)
    parser.add_argument('--platform', choices=('linux/amd64', 'linux/arm64'), required=True)
    parser.add_argument('--base-image', required=True)
    parser.add_argument('--endpoint', required=True)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--codex-tool-policy', choices=('docker-confined-v1',))
    parser.add_argument('--autonomy', action='store_true', help='Exercise a native helper and retained reference with scripted provider replies')
    parser.add_argument('--public-run-only', action='store_true', help='Exercise the signed public CLI and Runner with scripted native responses')
    parser.add_argument('--diagnostic-bootstrap', action='store_true', help='Instrument the OMP helper bootstrap for a failed-start diagnosis')
    args = parser.parse_args()
    result = {'kind': 'linux-model-native-e2e-v1', 'classification': 'actual_native_with_owned_simulated_provider',
              'runtime': args.runtime, 'status': 'failed', 'checks': [], 'external_provider_calls': 0,
              'native_execution': 'not_started',
              'research_acceptance': 'not_run', 'image': {'status': 'failed', 'checks': []}}
    fixture = None
    try:
        fixture = prepare_image(runtime=args.runtime, platform=args.platform, base_image=args.base_image,
                                endpoint=args.endpoint, directory=args.directory, result=result['image'])
        fixture.codex_tool_policy = args.codex_tool_policy
        fixture.autonomy = args.autonomy or args.public_run_only
        fixture.diagnostic_bootstrap = args.diagnostic_bootstrap
        result['model_workspace_bytes'] = 1073741824 if args.runtime == 'omp' else 134217728
        result['model_memory_bytes'] = 1610612736 if args.runtime == 'omp' else 1073741824
        verify_image(fixture, result['image'])
        result['image']['status'] = 'passed'
        with tempfile.TemporaryDirectory(prefix='oslit-linux-native-') as temporary:
            if args.public_run_only:
                from check_research_autonomy_public_e2e import run_public
                run_public(Path(temporary).resolve() / 'public', fixture, result)
            else:
                run_native(Path(temporary).resolve(), fixture, result)
                check(result, 'same engagement export verified', result.get('export_verification', {}).get('status') == 'passed')
                check(result, 'native boundary cleanup verified', result.get('boundary_cleanup', {}).get('cleanup') == 'verified')
        result['status'] = 'passed'
    except Exception as error:
        result['error'] = error_code(error)
        import traceback
        result['error_frames'] = [{'file': Path(frame.filename).name, 'line': frame.lineno, 'function': frame.name}
                                  for frame in traceback.extract_tb(error.__traceback__)[-8:]]
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
            [Path(__file__), Path(__file__).with_name('check_native_userns_probe.py'),
             Path(__file__).with_name('check_research_autonomy_public_e2e.py'),
             Path(__file__).with_name('check_codex_sandbox_policy_diagnostic.py'),
             Path(__file__).with_name('check_codex_sandbox_policy_candidate.py'),
             Path(__file__).with_name('check_codex_tool_policy_missing_profile_e2e.py'),
             Path(__file__).with_name('manage_codex_tool_policy_host.py'),
             *sorted((ROOT / 'engine/codex-tool-policy-v1').glob('*')),
             Path(__file__).with_name('check_omp_loader_preflight.py'),
             Path(__file__).with_name('check_model_image_docker_e2e.py'),
             *sorted((ROOT / 'tools').glob('*.py')), ROOT / 'tools/native_runtime_codex_exec.mjs',
             ROOT / 'tools/native_runtime_omp_tools.mjs', ROOT / 'config/native-tool-lock.json']}
        if classify_result is not None and classify_result(result):
            result['status'] = 'passed'
            result['expected_stop'] = result.pop('error')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(safe_publication(canonical(result)))
    print(json.dumps({'status': result['status'], 'output': str(args.output)}))
    return result['status'] != 'passed'


if __name__ == '__main__':
    raise SystemExit(main())
