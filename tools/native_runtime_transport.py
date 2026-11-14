"""Bounded private native-runtime pipes; no transcript or credential persistence.

Only the host constructs these handles. The environment owner must isolate tools,
credentials and network, revoke capabilities, and establish laboratory cleanup.
A dispatch guard or successful interrupt is not evidence that those controls work.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import re
import signal
import stat
import subprocess
import threading
import time

from engagement_contract import ContractError, safe_publication


class RuntimeError(Exception):
    """Stable failure code; never contains a native error body or prompt."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class HostOperation:
    """Accepted work. wait() completes outside the lock; cancel() requests abort."""
    wait: object
    cancel: object


class PendingTool:
    def __init__(self, operation=None, response=None):
        self.operation = operation
        self.response = response
        self.ready = threading.Event()
        self.cancelled = False
        self.unknown = False
        self.reported = False
        if operation is None:
            self.ready.set()
        else:
            threading.Thread(target=self._wait, daemon=True).start()

    def _wait(self):
        try:
            response = public(self.operation.wait())
            if not isinstance(response, dict) or len(json.dumps(response, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()) > MAX_MESSAGE:
                raise RuntimeError('native_host_tool_result_invalid')
            self.response = response
        except Exception:
            self.unknown = True
            self.response = {'content': [{'type': 'text', 'text':
                             'Host tool outcome unknown; reconcile before retry.'}], 'isError': True}
        finally:
            self.ready.set()

    def cancel(self):
        if not self.ready.is_set() and not self.cancelled:
            self.cancelled = True
            try:
                self.operation.cancel()
            except Exception:
                self.unknown = True


MAX_FRAME = 1024 * 1024
MAX_MESSAGE = 8 * MAX_FRAME
ID = re.compile(r'[A-Za-z0-9_.:-]{1,160}\Z')


def identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise RuntimeError('native_identifier_invalid')
    return value


def public(value):
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()
        safe_publication(encoded)
    except (ContractError, ValueError, TypeError, UnicodeError):
        raise RuntimeError('native_publication_rejected') from None
    return value


def text_content(value):
    if not isinstance(value, str) or len(value.encode()) > 65536:
        return '[runtime text omitted: invalid or oversized]'
    try:
        public(value)
    except RuntimeError:
        return '[runtime text omitted: secret-like content]'
    return value


def _pairs(rows):
    result = {}
    for key, value in rows:
        if key in result:
            raise ValueError('duplicate_key')
        result[key] = value
    return result


def _decode(data):
    value = json.loads(data, object_pairs_hook=_pairs,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))
    if not isinstance(value, dict):
        raise ValueError('frame_not_object')
    return value


def pinned(path, expected, *, max_bytes=None):
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path or path.is_symlink():
        raise RuntimeError('runtime_pin_path_invalid')
    try:
        with path.open('rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or (max_bytes and info.st_size > max_bytes):
                raise RuntimeError('runtime_pin_path_invalid')
            digest = 'sha256:' + hashlib.file_digest(stream, 'sha256').hexdigest()
    except OSError:
        raise RuntimeError('runtime_pin_unavailable') from None
    if digest != expected:
        raise RuntimeError('runtime_pin_mismatch')
    return path


def write_pipe(stream, data, *, timeout=5):
    """Bound backpressure as well as response time; never wait indefinitely under admission."""
    import select
    descriptor = stream.fileno()
    os.set_blocking(descriptor, False)
    deadline = time.monotonic() + timeout
    position = 0
    while position < len(data):
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not select.select([], [descriptor], [], remaining)[1]:
            raise RuntimeError('native_write_timeout')
        try:
            position += os.write(descriptor, data[position:])
        except BlockingIOError:
            continue


class Transport:
    """One owned process and a bounded JSONL pipe. stderr is deliberately discarded."""

    def __init__(self, command, environment, cwd, on_event, *, omp=False, launcher=None):
        self.omp = omp
        self.on_event = on_event
        self.frames = queue.Queue(maxsize=128)
        self.responses = {}
        self.deferred = []
        self.sequence = 0
        self.write_lock = threading.Lock()
        self.failure = None
        self.closed = False
        self.process = (launcher(command) if launcher is not None else
                        subprocess.Popen(command, cwd=cwd, env=environment, stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                         start_new_session=True))
        if self.process.stdin is None or self.process.stdout is None:
            raise RuntimeError('native_launcher_pipes_missing')
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        chunks = None
        try:
            while True:
                line = self.process.stdout.readline(MAX_FRAME + 1)
                if not line:
                    break
                if len(line) > MAX_FRAME or not line.endswith(b'\n'):
                    raise ValueError('frame_too_large')
                value = _decode(line)
                if value.get('type') == 'rpc_chunk':
                    index, count, size = (value.get(k) for k in ('index', 'count', 'byteLength'))
                    if (any(type(v) is not int for v in (index, count, size)) or
                            not 1 <= count <= 128 or not 0 < size <= MAX_MESSAGE or
                            not isinstance(value.get('chunkId'), str)):
                        raise ValueError('invalid_chunk')
                    if chunks is None:
                        chunks = {'id': value['chunkId'], 'count': count, 'size': size, 'parts': [], 'bytes': 0}
                    if (value['chunkId'] != chunks['id'] or count != chunks['count'] or size != chunks['size']
                            or index != len(chunks['parts'])):
                        raise ValueError('chunk_sequence')
                    part = base64.b64decode(value['data'], validate=True)
                    chunks['parts'].append(part)
                    chunks['bytes'] += len(part)
                    if chunks['bytes'] > size:
                        raise ValueError('chunk_size')
                    if len(chunks['parts']) < count:
                        continue
                    if chunks['bytes'] != size:
                        raise ValueError('chunk_size')
                    value = _decode(b''.join(chunks['parts']))
                    chunks = None
                elif chunks is not None:
                    raise ValueError('interleaved_chunk')
                self.frames.put_nowait(value)
            if chunks:
                raise ValueError('incomplete_chunk')
        except (ValueError, KeyError, TypeError, queue.Full, OSError):
            self.failure = 'native_protocol_invalid_or_overflow'
            if self.process.poll() is None:
                self.process.kill()
        finally:
            if not self.closed and self.failure is None:
                self.failure = 'native_transport_closed'
            try:
                self.frames.put_nowait(None)
            except queue.Full:
                pass

    def next_id(self):
        self.sequence += 1
        return 'request-' + str(self.sequence)

    def send(self, value):
        data = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode() + b'\n'
        if len(data) > MAX_FRAME:
            raise RuntimeError('native_request_oversized')
        if self.closed or self.process.poll() is not None:
            raise RuntimeError('native_transport_closed')
        try:
            with self.write_lock:
                write_pipe(self.process.stdin, data)
        except OSError:
            raise RuntimeError('native_transport_closed') from None

    def receive(self, timeout, *, defer_events=False):
        if self.failure:
            raise RuntimeError(self.failure)
        if self.deferred and not defer_events:
            frame = self.deferred.pop(0)
        else:
            try:
                frame = self.frames.get(timeout=max(0, timeout))
            except queue.Empty:
                if self.failure:
                    raise RuntimeError(self.failure)
                return False
        if frame is None:
            raise RuntimeError(self.failure or 'native_transport_closed')
        is_response = frame.get('type') == 'response' if self.omp else (
            'id' in frame and ('result' in frame or 'error' in frame))
        if is_response:
            if len(self.responses) >= 128:
                raise RuntimeError('native_response_overflow')
            self.responses[frame['id']] = frame
        else:
            if defer_events:
                if len(self.deferred) >= 128:
                    raise RuntimeError('native_event_backlog_overflow')
                self.deferred.append(frame)
            else:
                self.on_event(frame)
        return True

    def request(self, operation, params=None, *, request_id=None, timeout=15, defer_events=False):
        request_id = request_id or self.next_id()
        value = {'id': request_id, 'type': operation, **(params or {})} if self.omp else {
            'jsonrpc': '2.0', 'id': request_id, 'method': operation, 'params': params or {}}
        self.send(value)
        deadline = time.monotonic() + timeout
        while request_id not in self.responses:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError('native_response_timeout')
            self.receive(remaining, defer_events=defer_events)
        response = self.responses.pop(request_id)
        if ('error' in response and not self.omp) or (self.omp and response.get('success') is not True):
            raise RuntimeError('native_request_rejected')
        return response.get('data', {}) if self.omp else response.get('result', {})

    def close(self):
        if not self.closed:
            self.closed = True
            try:
                self.process.stdin.close()
            except OSError:
                pass
            try:
                self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                # The leader is still ours and live; signal its owned process group.
                try:
                    os.killpg(self.process.pid, signal.SIGTERM)
                    self.process.wait(timeout=2)
                except ProcessLookupError:
                    pass
                except subprocess.TimeoutExpired:
                    os.killpg(self.process.pid, signal.SIGKILL)
                    self.process.wait(timeout=2)
            self.reader.join(timeout=1)
            self.process.stdout.close()
        return {'process_exited': self.process.poll() is not None,
                'exit_code': self.process.returncode, 'lab_cleanup': 'not_observed',
                'child_absence': 'not_observed'}


class Session:
    """Shared adapter bookkeeping, not engagement authority or conversation state.

    dispatch_guard() returns a context manager that serializes admission with stop.
    host_call(name, arguments) accepts work while that guard is held, then returns
    HostOperation(wait, cancel). Waiting runs asynchronously after guard release.
    The host must not wait on another controller process during acceptance.
    """

    kind = ''
    version = ''

    def _prepare(self, profile, state_dir, workspace, host_tools, host_call, dispatch_guard):
        self.profile = profile
        if profile['kind'] != self.kind or profile['version'] != self.version:
            raise RuntimeError('native_runtime_version_unsupported')
        self._check_pins()
        self.state_dir, self.workspace = Path(state_dir), Path(workspace)
        for path in (self.state_dir, self.workspace):
            if not path.is_absolute() or path.resolve() != path:
                raise RuntimeError('runtime_directory_invalid')
        self.state_dir.mkdir(mode=0o700, exist_ok=True)
        info = self.state_dir.stat()
        if info.st_uid != os.getuid() or info.st_mode & 0o077 or not self.workspace.is_dir():
            raise RuntimeError('runtime_directory_not_private')
        self.host_tools = {identifier(x['name']): public(x) for x in host_tools}
        if len(self.host_tools) != len(host_tools):
            raise RuntimeError('duplicate_host_tool')
        self.host_call = host_call
        self.guard = dispatch_guard
        self.session_id = None
        self.native_turn = None
        self.invocation_id = None
        self.invocations = set()
        self.events = []
        self.calls = {}
        self.tool_replies = []
        self.tool_requests = {}
        self.active = False
        self.transport = None
        self.sessions = set()
        self.usage = None
        self.closed = False
        self.credential_binding = None
        self.model_boundary = None
        self.model_identity = None
        self.profile_sha256 = None
        self.native_executor = None
        self.owner_observer = None
        env = {k: os.environ[k] for k in ('PATH', 'LANG', 'LC_ALL', 'TMPDIR', 'SYSTEMROOT') if k in os.environ}
        env['NO_COLOR'] = '1'
        env['HOME'] = str(self.state_dir)
        return env

    def _check_pins(self):
        p = self.profile
        pinned(p['executable']['path'], p['executable']['sha256'])
        pinned(p['protocol']['schema_file'], p['protocol']['schema_sha256'], max_bytes=16 * MAX_FRAME)
        config = pinned(p['config_file'], p['config_sha256'], max_bytes=MAX_FRAME)
        try:
            safe_publication(config.read_bytes())
        except ContractError:
            raise RuntimeError('runtime_config_contains_secret') from None

    def _model_command(self, command, env, *, protected_model, profile_sha256, credential_resolver, provider_environment=None):
        if self.profile.get('credential_ref') is not None and (not protected_model or credential_resolver is None):
            raise RuntimeError('native_credential_boundary_unavailable')
        if provider_environment is not None:
            from urllib.parse import urlsplit
            allowed = {'HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY', 'SSL_CERT_FILE', 'CURL_CA_BUNDLE', 'NODE_EXTRA_CA_CERTS'}
            if (not isinstance(provider_environment, dict) or set(provider_environment) - allowed or
                    any(not isinstance(value, str) for value in provider_environment.values())):
                raise RuntimeError('native_provider_environment_invalid')
            public(provider_environment)
            for key, value in provider_environment.items():
                if key.endswith('_PROXY') and key != 'NO_PROXY':
                    parsed = urlsplit(value)
                    if (parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or not parsed.port
                            or parsed.username or parsed.password or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
                        raise RuntimeError('native_provider_environment_invalid')
                elif key == 'NO_PROXY':
                    if any(part not in ('', 'localhost', '127.0.0.1', '::1', '[::1]') for part in value.split(',')):
                        raise RuntimeError('native_provider_environment_invalid')
                elif not Path(value).is_absolute() or not Path(value).is_file() or Path(value).resolve() != Path(value):
                    raise RuntimeError('native_provider_environment_invalid')
            env.update(provider_environment)
        if protected_model:
            from native_runtime_owner import BOUNDARY, model_command
            if not isinstance(profile_sha256, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', profile_sha256):
                raise RuntimeError('native_owner_profile_pin_required')
            command = model_command(command)
            self.model_boundary = BOUNDARY
            self.profile_sha256 = profile_sha256
        if credential_resolver is not None:
            from native_credentials import CredentialBinding
            binding = credential_resolver(self.profile)
            if not isinstance(binding, CredentialBinding):
                raise RuntimeError('native_credential_binding_invalid')
            if self.profile.get('credential_ref') is None and (binding.environment() or binding.login()):
                raise RuntimeError('native_credential_binding_invalid')
            self.credential_binding = binding
            env.update(binding.environment())
        return command

    def _capture_owner(self):
        if self.model_boundary:
            from native_runtime_owner import process_identity
            self.model_identity = process_identity(self.transport.process.pid)
            if self.model_identity is None:
                raise RuntimeError('native_owner_process_missing')
            self._publish_owner()

    def _publish_owner(self):
        if self.owner_observer is not None:
            self.owner_observer(self.owner_receipt())

    def _startup_failed(self, error):
        error.owner_receipt = self.owner_receipt() if self.model_identity else None
        try:
            error.cleanup_result = self.close()
        except Exception:
            error.cleanup_result = {'process_exited': None, 'child_absence': 'unverified',
                                    'capabilities_revoked': False}

    def owner_receipt(self):
        if not self.model_boundary or self.model_identity is None:
            raise RuntimeError('native_owner_receipt_unavailable')
        return {'kind': 'native-runtime-owner-v1', 'runtime': self.kind, 'session_id': self.session_id,
                'profile_sha256': self.profile_sha256, 'boundary': self.model_boundary,
                'process': dict(self.model_identity),
                **({'bridge_process': dict(self.native_executor.bridge_identity)} if self.native_executor else {})}

    def capabilities(self):
        native = self.native_executor is not None and self.native_executor.ready is not None
        return {'runtime': self.kind, 'version': self.version,
                'available': ['startup', 'fresh_session', 'steer', 'interrupt', 'usage_tokens'] +
                             (['native_tools'] if native else []),
                'resume': 'live_session_only', 'durable_resume': 'reconstruct_from_published_work',
                'native_tools': 'environment_owned_native_executor' if native else 'withheld_until_isolated_tool_owner',
                'execution_boundary': self.model_boundary or 'external_owner_required',
                'child_inventory': 'children_prohibited' if self.model_boundary else 'unverified',
                'usage_cost_estimate': 'reported' if self.kind == 'omp' else 'unavailable',
                'provider_inference': 'unverified'}

    def _emit(self, event, **fields):
        if len(self.events) >= 512:
            raise RuntimeError('native_event_backlog_overflow')
        self.events.append(public({'kind': 'native-runtime-event-v1', 'runtime': self.kind,
                                   'session_id': self.session_id, 'invocation_id': self.invocation_id,
                                   'event': event, **fields}))

    @contextmanager
    def _admission(self):
        if self.closed:
            raise RuntimeError('native_transport_closed')
        if self.guard is None:
            raise RuntimeError('native_execution_boundary_unavailable')
        with self.guard():
            self._check_pins()
            if self.credential_binding:self.credential_binding.check()
            if self.native_executor:self.native_executor.check_authority()
            yield

    def _idle(self):
        if self.active:
            raise RuntimeError('native_invocation_in_progress')
        if self.tool_replies or any(not pending.ready.is_set() for _, pending in self.calls.values()):
            raise RuntimeError('native_tool_outcome_unsettled')

    def _begin(self, invocation_id, prompt):
        self._idle()
        if not self.session_id:
            raise RuntimeError('native_session_missing')
        identifier(invocation_id)
        public(prompt)
        if not isinstance(prompt, str) or not prompt or len(prompt.encode()) > MAX_FRAME // 2:
            raise RuntimeError('native_prompt_invalid')
        if invocation_id in self.invocations:
            raise RuntimeError('native_invocation_already_dispatched')
        if len(self.invocations) >= 4096:
            raise RuntimeError('native_session_dispatch_limit_reconstruct_required')
        self.invocations.add(invocation_id)
        self.invocation_id = invocation_id
        self.native_turn = None
        self.usage = None
        self.active = True

    def _tool(self, call_id, name, arguments):
        identifier(call_id)
        call_key = (self.session_id, self.invocation_id, call_id)
        fingerprint = json.dumps([name, arguments], sort_keys=True, separators=(',', ':'), allow_nan=False)
        if call_key in self.calls:
            previous, response = self.calls[call_key]
            if previous != fingerprint:
                raise RuntimeError('native_tool_call_changed')
            return response
        if len(self.calls) >= 4096:
            raise RuntimeError('native_tool_call_limit')
        if sum(not pending.ready.is_set() for _, pending in self.calls.values()) >= 8:
            raise RuntimeError('native_tool_concurrency_limit')
        try:
            if not self.active or name not in self.host_tools or self.host_call is None:
                raise RuntimeError('native_host_tool_denied')
            public(arguments)
        except Exception:
            response = {'content': [{'type': 'text', 'text': 'Host tool request refused.'}], 'isError': True}
            pending = PendingTool(response=response)
        else:
            try:
                with self._admission():
                    operation = self.host_call(name, arguments)
                if (not isinstance(operation, HostOperation) or not callable(operation.wait)
                        or not callable(operation.cancel)):
                    raise RuntimeError('native_host_tool_acceptance_invalid')
                pending = PendingTool(operation=operation)
            except Exception:
                self._emit('unknown', reason='host_tool_outcome_unavailable', call_id=call_id)
                response = {'content': [{'type': 'text', 'text': 'Host tool outcome unknown; reconcile before retry.'}],
                            'isError': True}
                pending = PendingTool(response=response)
        self.calls[call_key] = (fingerprint, pending)
        return pending

    def _queue_tool_reply(self, request_id, pending, reply):
        if len(self.tool_replies) >= 128:
            raise RuntimeError('native_tool_reply_overflow')
        self.tool_requests[request_id] = pending
        self.tool_replies.append((request_id, pending, reply))

    def _flush_tool_replies(self):
        waiting = []
        for request_id, pending, reply in self.tool_replies:
            if not pending.ready.is_set():
                waiting.append((request_id, pending, reply))
                continue
            if pending.unknown and not pending.reported:
                self._emit('unknown', reason='host_tool_outcome_unavailable')
                pending.reported = True
            reply(pending.response)
            self.tool_requests.pop(request_id, None)
        self.tool_replies = waiting

    def _cancel_tools(self):
        for _, pending in self.calls.values():
            pending.cancel()

    def _usage(self, value, names, *, cost=None):
        """Per-invocation totals; input/output include their cache/reasoning subsets."""
        usage = {output: value.get(source) for output, source in names.items()}
        if any(v is not None and (type(v) is not int or v < 0) for v in usage.values()):
            raise RuntimeError('native_usage_invalid')
        if cost is not None and (type(cost) not in (int, float) or not math.isfinite(cost) or cost < 0):
            raise RuntimeError('native_usage_invalid')
        usage.update({'monetary_spend': None, 'estimated_cost': cost, 'provider_requests': None,
                      'missing_dimensions': ['monetary_spend', 'provider_requests'] +
                      [key for key, v in usage.items() if v is None], 'source': 'native_runtime'})
        if usage != self.usage:
            self.usage = usage
            self._emit('usage', usage=usage)

    def observe(self, timeout_seconds=0):
        if not 0 <= timeout_seconds <= 60:
            raise RuntimeError('native_observe_timeout_invalid')
        deadline = time.monotonic() + timeout_seconds
        while True:
            self._flush_tool_replies()
            wait = max(0, deadline - time.monotonic()) if not self.events else 0
            if not self.transport.receive(min(wait, .05) if self.tool_replies else wait):
                if self.events or time.monotonic() >= deadline or not self.tool_replies:
                    break
            if time.monotonic() >= deadline and self.transport.frames.empty():
                break
        self._flush_tool_replies()
        events, self.events = self.events, []
        return events

    def close(self):
        receipt = self.owner_receipt() if self.model_identity else None
        self.closed = True
        self.active = False
        self._cancel_tools()
        if self.native_executor:self.native_executor.close()
        if self.credential_binding:self.credential_binding.revoke()
        result = self.transport.close() if self.transport else {
            'process_exited': True, 'exit_code': None, 'lab_cleanup': 'not_observed', 'child_absence': 'not_observed'}
        if receipt:
            from native_runtime_owner import recover_runtime_owner
            result.update(recover_runtime_owner(receipt))
        return result
