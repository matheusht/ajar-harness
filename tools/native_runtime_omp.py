"""OMP JSONL RPC control with host-owned tools and ephemeral native sessions."""
from __future__ import annotations

import time
import hashlib
import json
import os
from pathlib import Path
import stat
import threading
import uuid

from native_runtime_transport import HostOperation, RuntimeError, Session, Transport, identifier, text_content


class Runtime(Session):
    kind = 'omp'
    version = '18.20.0'

    def __init__(self, profile, state_dir, workspace, *, command_prefix=(), host_tools=(),
                 host_call=None, dispatch_guard=None):
        env = self._prepare(profile, state_dir, workspace, host_tools, host_call, dispatch_guard)
        if profile['protocol']['mode'] != 'stdio-jsonl':
            raise RuntimeError('native_protocol_mismatch')
        env['PI_CODING_AGENT_DIR'] = str(self.state_dir)
        self.ready = False
        self.pending_completion = None
        self.stats_before = None
        command = [*command_prefix, profile['executable']['path'], '--mode', 'rpc', '--no-ui',
                   '--no-tools', '--no-extensions', '--no-skills', '--no-rules', '--no-context-files',
                   '--no-title', '--no-lsp', '--no-pty', '--no-session', '--cwd', str(self.workspace),
                   '--config', profile['config_file'], '--model', profile['provider'] + '/' + profile['model']]
        try:
            self.transport = Transport(command, env, str(self.workspace), self._event, omp=True)
            deadline = time.monotonic() + 15
            while not self.ready:
                if time.monotonic() >= deadline:
                    raise RuntimeError('native_startup_timeout')
                self.transport.receive(max(0, deadline - time.monotonic()))
            self.transport.request('negotiate_protocol', {'protocolVersion': 2})
            if self.host_tools:
                self.transport.request('set_host_tools', {'tools': [
                    {'name': t['name'], 'description': t['description'], 'parameters': t['inputSchema']}
                    for t in self.host_tools.values()]})
        except Exception:
            self.close()
            raise

    def _read_state(self):
        state = self.transport.request('get_state')
        model = state.get('model') or {}
        if model.get('id') != self.profile['model'] or model.get('provider') != self.profile['provider']:
            raise RuntimeError('native_model_mismatch')
        tools = state.get('dumpTools')
        if not isinstance(tools, list) or {tool.get('name') for tool in tools} != set(self.host_tools):
            raise RuntimeError('native_unowned_tools')
        return state

    def _identity(self):
        state = self._read_state()
        self.session_id = identifier(state.get('sessionId'))
        self.sessions.add(self.session_id)
        return {'session_id': self.session_id, 'runtime': self.kind, 'model': self.profile['model'],
                'provider': self.profile['provider'], 'history': 'ephemeral'}

    def fresh(self):
        self._idle()
        self.transport.request('new_session')
        return self._identity()

    def resume(self, session_id):
        identifier(session_id)
        self._idle()
        if session_id != self.session_id:
            raise RuntimeError('native_session_unavailable_reconstruct_required')
        # no-session retains the active context; a lost context reconstructs from publications.
        result = self._identity()
        if result['session_id'] != session_id:
            raise RuntimeError('native_session_changed')
        return result

    def invoke(self, prompt, invocation_id):
        with self._admission():
            if self._read_state().get('sessionId') != self.session_id:
                raise RuntimeError('native_session_changed')
            self._begin(invocation_id, prompt)
            self.pending_completion = None
            try:
                self.stats_before = self.transport.request('get_session_stats')
                self.native_turn = self.transport.next_id()
                result = self.transport.request('prompt', {'message': 'Engagement assignment (host):\n' + prompt},
                                                request_id=self.native_turn, defer_events=True)
            except Exception:
                self._emit('unknown', reason='native_dispatch_not_settled')
                raise
        try:
            self._emit('started')
            if result.get('agentInvoked') is False:
                self._finish('local_only')
        except Exception:
            self._emit('unknown', reason='native_dispatch_not_settled')
            raise
        return {'invocation_id': invocation_id, 'session_id': self.session_id, 'native_turn': self.native_turn}

    def steer(self, message):
        if not self.active:
            raise RuntimeError('native_invocation_not_active')
        with self._admission():
            self.transport.request('steer', {'message': text_content(message)}, defer_events=True)
        return {'delivered': True, 'invocation_id': self.invocation_id}

    def interrupt(self):
        self._cancel_tools()
        self.transport.request('abort_and_restore_queue')
        return {'requested': True, 'lab_cleanup': 'not_observed'}

    def _finish(self, status):
        after = self.transport.request('get_session_stats')
        before_tokens = (self.stats_before or {}).get('tokens', {})
        tokens = after.get('tokens', {})
        values = {}
        for key in ('input', 'output', 'cacheRead', 'cacheWrite', 'reasoning', 'total'):
            a, b = tokens.get(key), before_tokens.get(key)
            if type(a) is int and type(b) is int and a >= b >= 0:
                values[key] = a - b
            elif a is not None or b is not None:
                raise RuntimeError('native_usage_invalid')
        cost_after, cost_before = after.get('cost'), (self.stats_before or {}).get('cost')
        cost = None
        if type(cost_after) in (int, float) and type(cost_before) in (int, float):
            cost = cost_after - cost_before
        self._usage(values, {'input_tokens': 'input', 'output_tokens': 'output',
                             'cached_input_tokens': 'cacheRead', 'cache_write_input_tokens': 'cacheWrite',
                             'reasoning_output_tokens': 'reasoning', 'total_tokens': 'total'}, cost=cost)
        self._emit('completed', status=status, usage_available=self.usage is not None,
                   resource_settlement='environment_readback_required')
        self.active = False
        self.pending_completion = None

    def _event(self, frame):
        kind = frame.get('type')
        if kind == 'ready':
            if frame.get('protocolVersion') != 1 or 2 not in frame.get('supportedProtocolVersions', []):
                raise RuntimeError('native_protocol_unsupported')
            self.ready = True
            return
        if kind == 'host_tool_call':
            pending = self._tool(frame.get('toolCallId'), frame.get('toolName'), frame.get('arguments'))
            self._queue_tool_reply(frame['id'], pending, lambda result: self.transport.send({
                'type': 'host_tool_result', 'id': frame['id'], 'result': result,
                'isError': result.get('isError', False)}))
            return
        if kind == 'host_tool_cancel':
            pending = self.tool_requests.get(frame.get('targetId'))
            self._emit('host_tool_cancel', pending=pending is not None)
            if pending:
                pending.cancel()
            return
        if not self.active:
            return
        if kind == 'message_end':
            message = frame.get('message', {})
            if message.get('role') == 'assistant':
                parts = [part.get('text', '') for part in message.get('content', [])
                         if isinstance(part, dict) and part.get('type') == 'text']
                if parts:
                    self._emit('text', text=text_content('\n'.join(parts)))
        elif kind == 'prompt_result' and frame.get('id') == self.native_turn:
            status = frame.get('status')
            if status not in {'completed', 'aborted', 'error'}:
                raise RuntimeError('native_completion_invalid')
            self.pending_completion = status
            if frame.get('sessionSettled') is True:
                self._finish(status)
            else:
                self._emit('yielded', status=status, session_settled=False)
        elif kind == 'session_settled' and self.pending_completion:
            self._finish(self.pending_completion)


def sdk_tree_digest(root):
    """Pin the complete isolated SDK installation, including transitive packages."""
    root = Path(root)
    if not root.is_absolute() or root.resolve() != root or not root.is_dir():
        raise RuntimeError('native_sdk_root_invalid')
    manifest = hashlib.sha256()
    count = total = 0
    for directory, directories, files in os.walk(root, followlinks=False):
        directories.sort()
        for name in sorted(directories + files):
            path = Path(directory) / name
            info = path.lstat()
            count += 1
            if count > 100000:
                raise RuntimeError('native_sdk_tree_oversized')
            relative = str(path.relative_to(root))
            if stat.S_ISLNK(info.st_mode):
                target = path.resolve(strict=True)
                if not target.is_relative_to(root):
                    raise RuntimeError('native_sdk_external_link')
                content = ['link', os.readlink(path)]
            elif stat.S_ISREG(info.st_mode):
                total += info.st_size
                if total > 2 * 1024 ** 3:
                    raise RuntimeError('native_sdk_tree_oversized')
                with path.open('rb') as stream:
                    content = ['file', hashlib.file_digest(stream, 'sha256').hexdigest()]
            elif stat.S_ISDIR(info.st_mode):
                content = ['directory']
            else:
                raise RuntimeError('native_sdk_entry_invalid')
            manifest.update(json.dumps([relative, info.st_mode & 0o777, content], separators=(',', ':')).encode())
    return 'sha256:' + manifest.hexdigest()


class ToolOwner:
    """Reuse pinned SDK tools in an uncredentialed process owned by a lab adapter.

    The command prefix and dispatch guard must come from the trusted environment
    owner. They are not themselves evidence of isolation or secret-free storage.
    """

    def __init__(self, sdk_dir, workspace, state_dir, *, sdk_pin, command_prefix=(), dispatch_guard=None, bun='bun'):
        import shutil
        from native_runtime_transport import public
        self.guard = dispatch_guard
        self.catalog = []
        self.events = []
        self.results = {}
        self.lock = threading.RLock()
        self.closed = False
        self.active = set()
        self.seen = set()
        self.ready = False
        self.transport = None
        if not command_prefix or dispatch_guard is None:
            raise RuntimeError('native_tool_owner_boundary_unavailable')
        sdk_dir, workspace, state_dir = (Path(p).resolve() for p in (sdk_dir, workspace, state_dir))
        sdk_root = Path(sdk_pin['root'])
        if not sdk_dir.is_relative_to(sdk_root) or sdk_tree_digest(sdk_root) != sdk_pin['sha256']:
            raise RuntimeError('native_sdk_pin_mismatch')
        state_dir.mkdir(mode=0o700, exist_ok=False)
        env = {key: os.environ[key] for key in ('PATH', 'LANG', 'TMPDIR') if key in os.environ}
        env['PI_CODING_AGENT_DIR'] = str(state_dir)
        executable = shutil.which(bun)
        if not executable:
            raise RuntimeError('native_tool_owner_bun_unavailable')
        command = [*command_prefix, executable, str(Path(__file__).with_name('native_runtime_omp_tools.mjs')),
                   str(sdk_dir), str(workspace)]
        try:
            self.transport = Transport(command, env, str(workspace), self._event, omp=True)
            response = self.transport.request('catalog', timeout=30)
            self.catalog = public(response['tools'])
        except Exception:
            self.close()
            raise

    def invoke(self, tool, arguments, call_id):
        with self.guard():
            return self._accept(tool, arguments, call_id)

    def _accept(self, tool, arguments, call_id):
        """Only for a host_call closure already inside the same dispatch guard."""
        with self.lock:
            return self._accept_locked(tool, arguments, call_id)

    def _accept_locked(self, tool, arguments, call_id):
        from native_runtime_transport import public
        identifier(call_id)
        if call_id in self.seen or tool not in {t['name'] for t in self.catalog}:
            raise RuntimeError('native_tool_request_refused')
        public(arguments)
        self.seen.add(call_id)
        self.active.add(call_id)
        try:
            return self.transport.request('call', {'tool': tool, 'arguments': arguments,
                                                 'call_id': call_id}, defer_events=True)
        except Exception:
            self.events.append({'call_id': call_id, 'status': 'unknown', 'result': None})
            raise

    def interrupt(self, call_id):
        identifier(call_id)
        with self.lock:
            return self.transport.request('cancel', {'call_id': call_id})

    def host_call(self, tool, arguments):
        """HostOperation factory, called with the runtime's admission guard held."""
        call_id = uuid.uuid4().hex
        self._accept(tool, arguments, call_id)
        def wait():
            while not self.closed:
                with self.lock:
                    if call_id in self.results:
                        row = self.results[call_id]
                        if row['status'] != 'returned':
                            raise RuntimeError('native_tool_outcome_unknown')
                        return row['result']
                    self.transport.receive(.05)
            raise RuntimeError('native_tool_owner_closed')
        return HostOperation(wait, lambda: self.interrupt(call_id))

    def _event(self, frame):
        from native_runtime_transport import public
        if frame.get('type') == 'ready':
            if frame.get('sdkVersion') != '18.20.0':
                raise RuntimeError('native_sdk_version_unsupported')
            self.ready = True
        elif frame.get('type') == 'tool_result':
            call_id = frame.get('call_id')
            if call_id not in self.active:
                raise RuntimeError('native_tool_result_identity_invalid')
            self.active.remove(call_id)
            try:
                result = public(frame.get('result'))
                status = frame.get('status')
                if status not in {'returned', 'unknown'}:
                    raise RuntimeError('native_tool_result_invalid')
            except RuntimeError:
                result, status = None, 'unknown'
            row = {'call_id': call_id, 'status': status, 'result': result}
            self.results[call_id] = row
            self.events.append(row)

    def observe(self, timeout_seconds=0):
        if not 0 <= timeout_seconds <= 60:
            raise RuntimeError('native_observe_timeout_invalid')
        with self.lock:
            self.transport.receive(timeout_seconds if not self.events else 0)
            while self.transport.receive(0):
                pass
            events, self.events = self.events, []
            return events

    def close(self):
        self.closed = True
        with self.lock:
            if self.transport:
                return self.transport.close()
        return {'process_exited': True, 'lab_cleanup': 'not_observed', 'child_absence': 'not_observed'}
