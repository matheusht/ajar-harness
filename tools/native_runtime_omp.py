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
                 host_call=None, dispatch_guard=None, credential_resolver=None, protected_model=False,
                 profile_sha256=None, provider_environment=None, owner_observer=None, model_owner=None):
        if model_owner is not None and command_prefix:
            raise RuntimeError('native_model_boundary_override_refused')
        env = self._prepare(profile, state_dir, workspace, host_tools, host_call, dispatch_guard, model_owner)
        if owner_observer is not None and (not protected_model or not callable(owner_observer)):
            raise RuntimeError('native_owner_observer_invalid')
        self.owner_observer = owner_observer
        if profile['protocol']['mode'] != 'stdio-jsonl':
            raise RuntimeError('native_protocol_mismatch')
        env['PI_CODING_AGENT_DIR'] = str(self.process_state)
        if model_owner is None and 'model_catalog' in profile:
            catalog = self.state_dir / 'models.yml'
            content = Path(profile['model_catalog']['path']).read_bytes()
            if catalog.is_symlink() or catalog.exists() and catalog.read_bytes() != content:
                raise RuntimeError('runtime_state_config_changed')
            if not catalog.exists():
                descriptor = os.open(catalog, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
                with os.fdopen(descriptor, 'wb') as stream:
                    stream.write(content)
        self.ready = False
        self.pending_completion = None
        self.stats_before = None
        command = [*command_prefix, model_owner.paths.executable if model_owner else profile['executable']['path'], '--mode', 'rpc', '--no-ui',
                   '--no-tools', '--no-extensions', '--no-skills', '--no-rules', '--no-context-files',
                   '--no-title', '--no-lsp', '--no-pty', '--no-session', '--cwd', str(self.process_workspace),
                   '--config', self.process_config, '--model', profile['provider'] + '/' + profile['model']]
        command = self._model_command(command, env, protected_model=protected_model,
            profile_sha256=profile_sha256, credential_resolver=credential_resolver,
            provider_environment=provider_environment)
        try:
            launcher = (lambda command: model_owner.launch_model(command, env, self.credential_binding)) if model_owner else None
            self.transport = Transport(command, env, str(self.workspace), self._event, omp=True, launcher=launcher)
            self._capture_owner()
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
        except Exception as error:
            self._startup_failed(error)
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
        self._publish_owner()
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
        after = self.transport.request('get_session_stats', defer_events=True)
        before_tokens = (self.stats_before or {}).get('tokens', {})
        tokens = after.get('tokens', {})
        values = {}
        for key in ('input', 'output', 'cacheRead', 'cacheWrite', 'reasoning', 'total'):
            a, b = tokens.get(key), before_tokens.get(key)
            if type(a) is int and type(b) is int and a >= b >= 0:
                values[key] = a - b
            elif a is not None or b is not None:
                raise RuntimeError('native_usage_invalid')
        # OMP separates uncached input from cache reads/writes; the common total includes all three.
        inputs = ('input', 'cacheRead', 'cacheWrite')
        values['input'] = sum(values[key] for key in inputs) if all(key in values for key in inputs) else None
        cost_after, cost_before = after.get('cost'), (self.stats_before or {}).get('cost')
        cost = None
        if type(cost_after) in (int, float) and type(cost_before) in (int, float):
            if cost_after < 0 or cost_before < 0:
                raise RuntimeError('native_usage_invalid')
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


def inspect_tool_bundle(profile, profile_id='runtime-main'):
    """Verify signed portable inputs without executing supplied code on the host.

    Readiness still requires the isolated process's version/platform handshake.
    The returned command names only the fixed, read-only support-input layout.
    """
    from engagement_contract import ContractError, canonical, digest, source_manifest
    identifier(profile_id)
    bundle = profile.get('tool_bundle')
    if profile.get('kind') != 'omp' or not isinstance(bundle, dict):
        raise RuntimeError('native_bundle_required')
    root = Path(bundle['path'])
    try:
        manifest = source_manifest(root)
    except ContractError:
        raise RuntimeError('native_bundle_manifest_invalid') from None
    if digest(canonical(manifest)) != bundle['manifest_sha256']:
        raise RuntimeError('native_bundle_manifest_mismatch')
    platform = bundle['platform']
    arch = {'linux/arm64': ('arm64', 183), 'linux/amd64': ('x64', 62)}.get(platform)
    if arch is None:
        raise RuntimeError('native_bundle_platform_mismatch')
    bun = root / 'bin/bun'
    try:
        with bun.open('rb') as stream:
            header = stream.read(20)
        if not bun.stat().st_mode & 0o111:
            raise RuntimeError('native_bundle_bun_not_executable')
        if len(header) != 20 or header[:6] != b'\x7fELF\x02\x01' or int.from_bytes(header[18:20], 'little') != arch[1]:
            raise RuntimeError('native_bundle_platform_mismatch')
        sdk = root / 'node_modules/@oh-my-pi/pi-coding-agent'
        metadata = json.loads((sdk / 'package.json').read_bytes())
    except (OSError, ValueError):
        raise RuntimeError('native_bundle_incomplete') from None
    if metadata.get('name') != '@oh-my-pi/pi-coding-agent' or metadata.get('version') != profile['version'] or profile['version'] != Runtime.version:
        raise RuntimeError('native_bundle_sdk_mismatch')
    # Pin the supported SDK's exact engine requirement, rather than interpret npm ranges.
    if metadata.get('engines', {}).get('bun') != '>=1.4.4':
        raise RuntimeError('native_bundle_engine_unsupported')
    try:
        bun_version = tuple(int(x) for x in bundle['bun_version'].split('.'))
    except (AttributeError, ValueError):
        raise RuntimeError('native_bundle_bun_unsupported') from None
    if len(bun_version) != 3 or bun_version < (1, 4, 4):
        raise RuntimeError('native_bundle_bun_unsupported')
    addon = root / ('node_modules/@oh-my-pi/pi-natives-linux-' + arch[0])
    try:
        data = json.loads((addon / 'package.json').read_bytes())
        expected_main = ('./pi_natives.linux-x64-baseline.node' if arch[0] == 'x64'
                         else './pi_natives.linux-arm64.node')
        if (data.get('name') != '@oh-my-pi/pi-natives-linux-' + arch[0] or
                data.get('version') != profile['version'] or data.get('main') != expected_main or
                not (addon / expected_main).is_file() or not (sdk / 'src/sdk.ts').is_file()):
            raise RuntimeError('native_bundle_platform_unavailable')
        sidecar = (root / 'native_runtime_omp_tools.mjs').read_bytes()
    except (OSError, ValueError):
        raise RuntimeError('native_bundle_platform_unavailable') from None
    if sidecar != Path(__file__).with_name('native_runtime_omp_tools.mjs').read_bytes():
        raise RuntimeError('native_bundle_sidecar_mismatch')
    remote = '/input/' + profile_id
    return {'support_input': {'path': str(root), 'manifest_sha256': bundle['manifest_sha256']},
            'sdk_dir': str(sdk), 'sdk_pin': {'root': str(root), 'sha256': sdk_tree_digest(root)},
            'command': [remote + '/bin/bun', remote + '/native_runtime_omp_tools.mjs',
                        remote + '/node_modules/@oh-my-pi/pi-coding-agent', '/work'],
            'expected_ready': {'sdkVersion': profile['version'], 'bunVersion': bundle['bun_version'],
                               'platform': 'linux', 'arch': arch[0]},
            'execution_verified': False}


class ToolOwner:
    """Reuse pinned SDK tools in an uncredentialed process owned by a lab adapter.

    The command prefix and dispatch guard must come from the trusted environment
    owner. They are not themselves evidence of isolation or secret-free storage.
    """

    def __init__(self, sdk_dir, workspace, state_dir, *, sdk_pin, command_prefix=(), dispatch_guard=None,
                 bun='bun', launcher=None, command=None, target_platform=None, expected_ready=None):
        import shutil
        from native_runtime_transport import public
        self.guard = dispatch_guard
        self.expected_ready = expected_ready
        self.catalog = []
        self.events = []
        self.results = {}
        self.lock = threading.RLock()
        self.closed = False
        self.active = set()
        self.seen = set()
        self.ready = False
        self.transport = None
        if dispatch_guard is None or (not command_prefix and launcher is None):
            raise RuntimeError('native_tool_owner_boundary_unavailable')
        if launcher is not None and (command_prefix or not isinstance(command, list) or not command):
            raise RuntimeError('native_tool_owner_launcher_invalid')
        if launcher is None and command is not None:
            raise RuntimeError('native_tool_owner_launcher_invalid')
        sdk_dir, workspace, state_dir = (Path(p).resolve() for p in (sdk_dir, workspace, state_dir))
        sdk_root = Path(sdk_pin['root'])
        if not sdk_dir.is_relative_to(sdk_root) or sdk_tree_digest(sdk_root) != sdk_pin['sha256']:
            raise RuntimeError('native_sdk_pin_mismatch')
        if launcher is not None:
            platform_addon = {'linux/amd64': 'linux-x64', 'linux/arm64': 'linux-arm64',
                              'darwin/arm64': 'darwin-arm64', 'darwin/amd64': 'darwin-x64'}.get(target_platform)
            addon = sdk_root / 'node_modules' / '@oh-my-pi' / ('pi-natives-' + (platform_addon or 'unavailable'))
            try:
                version = json.loads((addon / 'package.json').read_text())['version']
            except (OSError, ValueError, KeyError):
                raise RuntimeError('native_sdk_platform_unavailable') from None
            if version != '18.20.0':
                raise RuntimeError('native_sdk_platform_unavailable')
        state_dir.mkdir(mode=0o700, exist_ok=False)
        env = {key: os.environ[key] for key in ('PATH', 'LANG', 'TMPDIR') if key in os.environ}
        env['PI_CODING_AGENT_DIR'] = str(state_dir)
        if launcher is None:
            executable = shutil.which(bun)
            if not executable:
                raise RuntimeError('native_tool_owner_bun_unavailable')
            command = [*command_prefix, executable, str(Path(__file__).with_name('native_runtime_omp_tools.mjs')),
                       str(sdk_dir), str(workspace)]
        try:
            self.transport = Transport(command, env, str(workspace), self._event, omp=True, launcher=launcher)
            response = self.transport.request('catalog', timeout=30)
            if not self.ready:
                raise RuntimeError('native_tool_owner_not_ready')
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
        if frame.get('type') == 'startup_failed':
            phase = frame.get('phase')
            if self.ready or phase not in ('paths', 'manifest', 'sdk_import', 'schema_import',
                                           'validation_import', 'settings', 'tools', 'catalog'):
                raise RuntimeError('native_tool_startup_diagnostic_invalid')
            raise RuntimeError('native_tool_startup_' + phase)
        elif frame.get('type') == 'ready':
            if frame.get('sdkVersion') != '18.20.0':
                raise RuntimeError('native_sdk_version_unsupported')
            if self.expected_ready is not None and any(frame.get(key) != value for key, value in self.expected_ready.items()):
                raise RuntimeError('native_tool_owner_platform_mismatch')
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
