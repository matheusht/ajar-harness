"""Codex app-server control adapter. Native wire frames stay private to this module."""
from __future__ import annotations

from pathlib import Path
from collections import deque

from native_runtime_transport import PendingTool, RuntimeError, Session, Transport, identifier, text_content, write_pipe


class Runtime(Session):
    kind = 'codex'
    version = '0.166.0'

    def __init__(self, profile, state_dir, workspace, *, command_prefix=(), host_tools=(),
                 host_call=None, dispatch_guard=None, native_executor=None, credential_resolver=None,
                 protected_model=False, profile_sha256=None, provider_environment=None,
                 owner_observer=None, model_owner=None):
        if model_owner is not None and command_prefix:
            raise RuntimeError('native_model_boundary_override_refused')
        env = self._prepare(profile, state_dir, workspace, host_tools, host_call, dispatch_guard, model_owner)
        if owner_observer is not None and (not protected_model or not callable(owner_observer)):
            raise RuntimeError('native_owner_observer_invalid')
        self.owner_observer = owner_observer
        if profile['protocol']['mode'] != 'stdio-jsonrpc':
            raise RuntimeError('native_protocol_mismatch')
        self.native_executor = native_executor
        if profile.get('credential_ref') is not None and native_executor is None:
            raise RuntimeError('native_credential_tool_boundary_unavailable')
        env['CODEX_HOME'] = str(self.process_state)
        self.authentication = 'not_requested'
        self.helpers = {}
        self.totals = {}
        self.before = {}
        config = self.state_dir / 'config.toml'
        content = Path(profile['config_file']).read_bytes()
        if native_executor is not None:
            import tomllib
            validate_native_config(tomllib.loads(content.decode()))
        if config.exists() and (config.is_symlink() or config.read_bytes() != content):
            raise RuntimeError('runtime_state_config_changed')
        config.write_bytes(content)
        config.chmod(0o400)
        command = [*command_prefix, model_owner.paths.executable if model_owner else profile['executable']['path'],
                   '--strict-config', 'app-server', '--stdio']
        command = self._model_command(command, env, protected_model=protected_model,
            profile_sha256=profile_sha256, credential_resolver=credential_resolver,
            provider_environment=provider_environment)
        try:
            launcher = (lambda command: model_owner.launch_model(command, env, self.credential_binding)) if model_owner else None
            self.transport = Transport(command, env, str(self.workspace), self._event, launcher=launcher)
            self._capture_owner()
            self.transport.request('initialize', {'clientInfo': {'name': 'oslit-runtime', 'version': '2'},
                                                  'capabilities': {'experimentalApi': True}})
            self.transport.send({'jsonrpc': '2.0', 'method': 'initialized'})
            if native_executor is not None:
                validate_native_config(self.transport.request('config/read', {'includeLayers': False})['config'])
                self.transport.request('environment/add', native_executor.registration())
                self.transport.request('environment/info', {'environmentId': native_executor.environment_id})
                native_executor.check_ready()
            if self.credential_binding and self.credential_binding.login():
                reply = self.transport.request('account/login/start', self.credential_binding.login())
                if reply != {'type': 'chatgptAuthTokens'}:
                    raise RuntimeError('native_external_auth_not_accepted')
                self.authentication = 'external_tokens_accepted'
        except Exception as error:
            self._startup_failed(error)
            raise

    def _identity(self, result):
        session = identifier(result.get('thread', {}).get('id'))
        if result.get('model') != self.profile['model'] or result.get('modelProvider') != self.profile['provider']:
            raise RuntimeError('native_model_mismatch')
        if self.native_executor:
            if result.get('activePermissionProfile', {}).get('id') != 'oslit-worker':
                raise RuntimeError('native_permission_profile_mismatch')
            if result.get('thread', {}).get('environments') != [self.native_executor.selection()]:
                raise RuntimeError('native_environment_selection_mismatch')
        self.session_id = session
        self.sessions.add(session)
        self._publish_owner()
        return {'session_id': session, 'runtime': self.kind, 'model': self.profile['model'],
                'provider': self.profile['provider'], 'history': 'ephemeral'}

    def create_helper(self, helper_id):
        with self.transport.io_lock:
            result = self.transport.request('thread/start', {
                'ephemeral': True, 'cwd': str(self.process_workspace), 'model': self.profile['model'],
                'modelProvider': self.profile['provider'], 'approvalPolicy': 'never',
                'permissions': 'oslit-worker', 'environments': [self.native_executor.selection()],
                'allowProviderModelFallback': False,
                'dynamicTools': [{'type': 'function', 'name': t['name'], 'description': t['description'],
                                  'inputSchema': t['inputSchema']} for t in self.host_tools.values()]}, defer_events=True, dispatch_guard=self._admission)
            thread = result.get('thread', {})
            session = identifier(thread.get('id'))
            if (session == self.session_id or session in self.helpers or result.get('model') != self.profile['model'] or
                    result.get('modelProvider') != self.profile['provider'] or
                    result.get('activePermissionProfile', {}).get('id') != 'oslit-worker' or
                    thread.get('environments') != [self.native_executor.selection()]):
                raise RuntimeError('native_helper_identity_invalid')
            child = Helper(self, helper_id, session)
            self.helpers[session] = child
            return child

    def fresh(self):
        self._idle()
        result = self.transport.request('thread/start', {
            'ephemeral': True, 'cwd': str(self.process_workspace), 'model': self.profile['model'],
            'modelProvider': self.profile['provider'], 'approvalPolicy': 'never',
            **({'permissions': 'oslit-worker', 'environments': [self.native_executor.selection()],
                'allowProviderModelFallback': False} if self.native_executor else {'sandbox': 'read-only'}),
            'dynamicTools': [{'type': 'function', 'name': t['name'], 'description': t['description'],
                              'inputSchema': t['inputSchema']} for t in self.host_tools.values()]})
        return self._identity(result)

    def resume(self, session_id):
        identifier(session_id)
        self._idle()
        if session_id not in self.sessions:
            raise RuntimeError('native_session_unavailable_reconstruct_required')
        result = self.transport.request('thread/read', {'threadId': session_id, 'includeTurns': False})
        if result.get('thread', {}).get('id') != session_id:
            raise RuntimeError('native_session_changed')
        return self._identity(dict(result, model=self.profile['model'], modelProvider=self.profile['provider'],
            **({'activePermissionProfile': {'id': 'oslit-worker'}} if self.native_executor else {})))

    def invoke(self, prompt, invocation_id):
        with self.transport.io_lock, self._admission():
            self._begin(invocation_id, prompt)
            self.before = dict(self.totals.get(self.session_id, {}))
        try:
            # Bind the turn before another helper dispatches its deferred events.
            with self.transport.io_lock:
                result = self.transport.request('turn/start', {'threadId': self.session_id,
                    'model': self.profile['model'], 'input': [{'type': 'text', 'text': prompt}]},
                    defer_events=True, dispatch_guard=self._admission)
                turn = identifier(result.get('turn', {}).get('id'))
                if self.native_turn not in (None, turn):
                    raise RuntimeError('native_turn_mismatch')
                self.native_turn = turn
                self._emit('started')
        except Exception:
            self._emit('unknown', reason='native_dispatch_not_settled')
            raise
        return {'invocation_id': invocation_id, 'session_id': self.session_id, 'native_turn': self.native_turn}

    def steer(self, message):
        if not self.active or not self.native_turn:
            raise RuntimeError('native_invocation_not_active')
        message = text_content(message)
        self.transport.request('turn/steer', {'threadId': self.session_id, 'expectedTurnId': self.native_turn,
                                            'input': [{'type': 'text', 'text': message}]},
                               defer_events=True, dispatch_guard=self._admission)
        return {'delivered': True, 'invocation_id': self.invocation_id}

    def interrupt(self):
        self._cancel_tools()
        if not self.active:
            return {'requested': False, 'native_idle': True, 'lab_cleanup': 'not_observed'}
        self.transport.request('turn/interrupt', {'threadId': self.session_id, 'turnId': self.native_turn})
        return {'requested': True, 'lab_cleanup': 'not_observed'}

    def _event(self, frame):
        method, params = frame.get('method'), frame.get('params', {})
        if not isinstance(params, dict):
            raise RuntimeError('native_event_invalid')
        child = self.helpers.get(params.get('threadId'))
        if child is not None:
            child.event(frame)
            return
        if method == 'item/tool/call' and 'id' in frame:
            if (params.get('threadId') != self.session_id or not self.active or
                    params.get('turnId') != self.native_turn):
                pending = PendingTool(response={'content': [{'type': 'text', 'text': 'Stale native assignment.'}], 'isError': True})
            else:
                pending = self._tool(params.get('callId'), params.get('tool'), params.get('arguments'))
            self._queue_tool_reply(frame['id'], pending, lambda result: self._tool_reply(frame['id'], result))
            return
        if 'id' in frame and method == 'account/chatgptAuthTokens/refresh' and self.credential_binding:
            try:
                result = self.credential_binding.refresh(params.get('previousAccountId'))
                self.transport.send({'jsonrpc': '2.0', 'id': frame['id'], 'result': result})
                return
            except RuntimeError:
                pass
        if 'id' in frame and method:
            # Never approve an unconfigured permission, credential, or tool route.
            self.transport.send({'jsonrpc': '2.0', 'id': frame['id'], 'error': {
                'code': -32601, 'message': 'Host operation unavailable'}})
            return
        if not self.active or params.get('threadId') != self.session_id:
            return
        turn = params.get('turnId') or params.get('turn', {}).get('id')
        if turn != self.native_turn:
            return
        if method == 'thread/tokenUsage/updated':
            total = params.get('tokenUsage', {}).get('total', {})
            previous = self.totals.get(self.session_id, {})
            if (not isinstance(total, dict) or not set(previous).issubset(total)
                    or any(type(v) is not int or v < previous.get(k, 0) for k, v in total.items())):
                raise RuntimeError('native_usage_invalid')
            self.totals[self.session_id] = total
            self._usage({key: value - self.before.get(key, 0) for key, value in total.items()}, {
                'input_tokens': 'inputTokens', 'output_tokens': 'outputTokens',
                'cached_input_tokens': 'cachedInputTokens', 'cache_write_input_tokens': 'cacheWriteInputTokens',
                'reasoning_output_tokens': 'reasoningOutputTokens', 'total_tokens': 'totalTokens'})
        elif method == 'item/completed' and params.get('item', {}).get('type') == 'agentMessage':
            self._emit('text', text=text_content(params['item'].get('text')))
        elif method == 'turn/completed':
            status = params.get('turn', {}).get('status')
            if status not in {'completed', 'interrupted', 'failed'}:
                raise RuntimeError('native_completion_invalid')
            self._emit('completed', status=status, usage_available=self.usage is not None,
                       resource_settlement='environment_readback_required')
            self.active = False

    def _tool_reply(self, request_id, result):
        content = []
        for item in result.get('content', []):
            if item.get('type') == 'text':
                content.append({'type': 'inputText', 'text': item['text']})
            elif item.get('type') == 'image':
                content.append({'type': 'inputImage', 'imageUrl':
                                'data:' + item['mimeType'] + ';base64,' + item['data']})
            else:
                raise RuntimeError('native_host_tool_content_unsupported')
        self.transport.send({'jsonrpc': '2.0', 'id': request_id, 'result': {
            'contentItems': content, 'success': not result.get('isError', False)}})


class Helper:
    """A host-created native thread, bound to the parent's executor and tool identity."""
    def __init__(self, parent, helper_id, session_id):
        self.parent, self.helper_id, self.session_id = parent, helper_id, session_id
        self.events, self.usage = deque(), None
        self.active, self.native_turn = False, None
        self.accepting_tools = True
        self.invocation_id = helper_id

    _usage = Session._usage

    def _emit(self, event, **fields):
        if len(self.events) >= 128:
            raise RuntimeError('native_helper_backlog_overflow')
        self.events.append({'event': event, **fields})

    def invoke(self, prompt, invocation_id):
        if self.active:
            raise RuntimeError('native_invocation_in_progress')
        self.active = True
        self.invocation_id = identifier(invocation_id)
        with self.parent.transport.io_lock:
            result = self.parent.transport.request('turn/start', {'threadId': self.session_id,
                'model': self.parent.profile['model'], 'input': [{'type': 'text', 'text': prompt}]},
                defer_events=True, dispatch_guard=self.parent._admission)
            self.native_turn = identifier(result.get('turn', {}).get('id'))

    def event(self, frame):
        method, params = frame.get('method'), frame.get('params', {})
        turn = params.get('turnId') or params.get('turn', {}).get('id')
        if method == 'item/tool/call' and 'id' in frame:
            pending = self.parent._tool(params.get('callId'), params.get('tool'), params.get('arguments'),
                session_id=self.session_id, invocation_id=self.invocation_id,
                active=self.accepting_tools and self.active and turn == self.native_turn)
            self.parent._queue_tool_reply(frame['id'], pending, lambda result: self.parent._tool_reply(frame['id'], result))
            return
        if 'id' in frame:
            self.parent.transport.send({'jsonrpc': '2.0', 'id': frame['id'], 'error': {'code': -32601, 'message': 'Host operation unavailable'}})
            return
        if not self.active or turn != self.native_turn:
            return
        if method == 'thread/tokenUsage/updated':
            self._usage(params.get('tokenUsage', {}).get('total', {}), {
                'input_tokens': 'inputTokens', 'output_tokens': 'outputTokens',
                'cached_input_tokens': 'cachedInputTokens', 'cache_write_input_tokens': 'cacheWriteInputTokens',
                'reasoning_output_tokens': 'reasoningOutputTokens', 'total_tokens': 'totalTokens'})
        elif method == 'item/completed' and params.get('item', {}).get('type') == 'agentMessage':
            self._emit('text', text=text_content(params['item'].get('text')))
        elif method == 'turn/completed':
            if params.get('turn', {}).get('status') not in {'completed', 'interrupted', 'failed'}:
                raise RuntimeError('native_completion_invalid')
            self.active = False
            self._emit('completed', status=params.get('turn', {}).get('status'))

    def observe(self, timeout_seconds=0):
        import time
        if not self.events and timeout_seconds:
            time.sleep(min(timeout_seconds, .05))
        events = []
        while self.events:
            events.append(self.events.popleft())
        return events

    def steer(self, message):
        return self.parent.transport.request('turn/steer', {'threadId': self.session_id,
            'expectedTurnId': self.native_turn, 'input': [{'type': 'text', 'text': text_content(message)}]},
            defer_events=True, dispatch_guard=self.parent._admission)

    def interrupt(self):
        with self.parent.transport.io_lock:
            self.accepting_tools = False
            if self.active:
                self.parent.transport.request('turn/interrupt', {'threadId': self.session_id, 'turnId': self.native_turn}, defer_events=True)

    def close(self):
        import time
        self.interrupt()
        deadline = time.monotonic() + 5
        while True:
            with self.parent.transport.io_lock:
                self.parent._flush_tool_replies_locked()
                pending = {item for key, (_, item) in self.parent.calls.items() if key[0] == self.session_id}
                unsettled = any(not item.ready.is_set() for item in pending)
                replies = any(item in pending for _, item, _ in self.parent.tool_replies)
                if not self.active and not unsettled and not replies:
                    break
            if time.monotonic() >= deadline:
                self.parent._emit('unknown', reason='native_helper_stop_unverified')
                raise RuntimeError('native_helper_stop_unverified')
            self.parent.transport.receive(.05)
        self.parent.transport.request('thread/unsubscribe', {'threadId': self.session_id}, defer_events=True)
        self.parent.helpers.pop(self.session_id, None)
        return {'turn_settled': True, 'child_absence': 'parent_process_cleanup_required'}


def inspect_tool_bundle(profile, profile_id='runtime-main'):
    """Verify the fixed Linux exec-server support tree before isolated staging."""
    from engagement_contract import ContractError, canonical, digest, source_manifest
    identifier(profile_id)
    bundle = profile.get('tool_bundle')
    if profile.get('kind') != 'codex' or not isinstance(bundle, dict):
        raise RuntimeError('native_bundle_required')
    root = Path(bundle['path'])
    try:
        manifest = source_manifest(root)
        if digest(canonical(manifest)) != bundle['manifest_sha256']:
            raise RuntimeError('native_bundle_manifest_mismatch')
        binary = root / 'bin/codex'
        with binary.open('rb') as stream:header = stream.read(20)
        arch = {'linux/arm64': 183, 'linux/amd64': 62}.get(bundle['platform'])
        if (arch is None or len(header) != 20 or header[:6] != b'\x7fELF\x02\x01' or
                int.from_bytes(header[18:20], 'little') != arch):
            raise RuntimeError('native_bundle_platform_mismatch')
        if not binary.stat().st_mode & 0o111:
            raise RuntimeError('native_bundle_not_executable')
        if profile['version'] != Runtime.version:
            raise RuntimeError('native_bundle_version_unsupported')
    except ContractError:
        raise RuntimeError('native_bundle_manifest_invalid') from None
    except OSError:
        raise RuntimeError('native_bundle_incomplete') from None
    return {'support_input': {'path': str(root), 'manifest_sha256': bundle['manifest_sha256']},
            'command': ['/input/' + profile_id + '/bin/codex', 'exec-server', '--listen', 'stdio',
                        '--linux-sandbox-pid-namespace', 'isolate'],
            'expected_version': Runtime.version, 'expected_platform': 'linux', 'execution_verified': False}


_DISABLED_FEATURES = ('apps', 'plugins', 'multi_agent', 'multi_agent_v2', 'browser_use',
    'browser_use_external', 'browser_use_full_cdp_access', 'computer_use', 'in_app_browser',
    'remote_plugin', 'plugin_discovery_prefetch', 'recommended_plugins', 'shell_snapshot',
    'api_key_model_discovery')


def validate_native_config(config):
    """The signed native profile keeps model-owned execution inside its selected executor."""
    if (config.get('default_permissions') != 'oslit-worker' or config.get('web_search') != 'disabled'
            or any(config.get(key) is not None for key in ('sandbox_mode', 'sandbox_workspace_write'))
            or config.get('mcp_servers') or config.get('hooks')):
        raise RuntimeError('native_configuration_boundary_invalid')
    features = config.get('features', {})
    if any(features.get(key) is not False for key in _DISABLED_FEATURES):
        raise RuntimeError('native_alternate_tools_enabled')
    permissions = config.get('permissions', {}).get('oslit-worker', {})
    fs = permissions.get('filesystem', {})
    if (permissions.get('extends') is not None or permissions.get('workspace_roots') or
            fs.get(':root') != 'deny' or fs.get(':minimal') != 'read' or
            fs.get(':workspace_roots') != {'.': 'write'} or
            any(value not in (None, 'read', 'deny') for key, value in fs.items()
                if key not in (':workspace_roots', 'glob_scan_max_depth'))):
        raise RuntimeError('native_filesystem_profile_invalid')
    network = permissions.get('network', {})
    if network.get('dangerously_allow_all_unix_sockets') or network.get('dangerously_allow_non_loopback_proxy'):
        raise RuntimeError('native_network_profile_invalid')
    if network.get('enabled') is not False and features.get('network_proxy') is not True:
        raise RuntimeError('native_network_profile_invalid')
    shell = config.get('shell_environment_policy', {})
    if (shell.get('inherit') != 'none' or shell.get('ignore_default_excludes') is True or
            shell.get('experimental_use_profile') is True or shell.get('include_only') or
            any(key not in {'PATH', 'HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY', 'SSL_CERT_FILE',
                           'CURL_CA_BUNDLE', 'NODE_EXTRA_CA_CERTS'} for key in (shell.get('set') or {}))):
        raise RuntimeError('native_shell_environment_invalid')
    return config


class NativeExecutor:
    """Private authenticated transport to one environment-owned native executor.

    The WebSocket bridge handles framing only. Every executor request crosses the
    same host admission lock. No provider credential enters this tool process.
    """
    def __init__(self, *, launcher, command, environment_id, cwd, dispatch_guard, bun='bun',
                 expected_platform=None, expected_version='0.166.0', owner_observer=None,
                 profile_sha256=None, model_owner=None):
        import json
        import secrets
        import select
        import shutil
        import subprocess
        import threading
        self.environment_id = identifier(environment_id)
        self.cwd = str(cwd)
        self.guard = dispatch_guard
        self.expected_platform, self.expected_version = expected_platform, expected_version
        self.initialize_id = None
        self.ready = None
        self.bridge_identity = None
        self.profile_sha256 = profile_sha256
        self.model_owner = model_owner
        self.token = secrets.token_urlsafe(32)
        self.closed = False
        self.failure = None
        self.transport_diagnostic = None
        self.diagnostic_lock = threading.Lock()
        self.executor = self.bridge = None
        self.threads = []
        if not callable(launcher) or not callable(dispatch_guard) or not Path(cwd).is_absolute():
            raise RuntimeError('native_executor_boundary_unavailable')
        if owner_observer is not None:
            import re
            if not callable(owner_observer) or not re.fullmatch(r'sha256:[0-9a-f]{64}', str(profile_sha256)):
                raise RuntimeError('native_owner_observer_invalid')
        binary = shutil.which(bun) if model_owner is None else None
        if model_owner is None and not binary:
            raise RuntimeError('native_executor_bridge_unavailable')
        try:
            with self.guard():
                self.executor = launcher(command)
            from native_runtime_owner import model_command, process_identity
            if model_owner is not None:
                self.bridge = model_owner.launch_support('codex_bridge')
            else:
                self.bridge = subprocess.Popen(model_command([binary, str(Path(__file__).with_name('native_runtime_codex_exec.mjs'))]),
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    env={'PATH': '/usr/bin:/bin'}, start_new_session=True)
                self.bridge_identity = process_identity(self.bridge.pid)
                if self.bridge_identity is None:raise RuntimeError('native_executor_bridge_startup_failed')
            if owner_observer is not None:owner_observer(self.owner_receipt())
            self.bridge.stdin.write(json.dumps({'token': self.token}).encode() + b'\n')
            self.bridge.stdin.flush()
            if not select.select([self.bridge.stdout], [], [], 5)[0]:
                raise RuntimeError('native_executor_bridge_startup_timeout')
            ready = json.loads(self.bridge.stdout.readline(4096))
            self.url = ready['ready']
            from urllib.parse import urlsplit
            parsed = urlsplit(self.url)
            if parsed.scheme != 'ws' or parsed.hostname != '127.0.0.1' or parsed.path != '/' or not parsed.port:
                raise RuntimeError('native_executor_bridge_endpoint_invalid')
            for source, destination, admit in ((self.bridge, self.executor, True), (self.executor, self.bridge, False)):
                thread = threading.Thread(target=self._copy, args=(source, destination, admit), daemon=True)
                self.threads.append(thread);thread.start()
        except Exception as error:
            error.owner_receipt = self.owner_receipt() if (self.bridge_identity or model_owner) and self.profile_sha256 else None
            try:
                error.cleanup_result = self.close()
                if model_owner is not None:
                    error.cleanup_result.update(model_owner.revoke_and_verify())
                elif error.owner_receipt:
                    from native_runtime_owner import recover_runtime_owner
                    error.cleanup_result.update(recover_runtime_owner(error.owner_receipt))
            except Exception:
                error.cleanup_result = {'process_exited': None, 'child_absence': 'unverified',
                                        'capabilities_revoked': False}
            raise

    def owner_receipt(self):
        if self.model_owner is not None:
            return self.model_owner.receipt()
        from native_runtime_owner import BOUNDARY
        if not self.bridge_identity or not self.profile_sha256:
            raise RuntimeError('native_owner_receipt_unavailable')
        return {'kind': 'native-runtime-owner-v1', 'runtime': 'codex', 'session_id': None,
                'profile_sha256': self.profile_sha256, 'boundary': BOUNDARY,
                'bridge_process': dict(self.bridge_identity)}

    def _copy(self, source, destination, admit):
        import json
        from contextlib import nullcontext
        phase = 'read'
        try:
            while not self.closed:
                phase = 'read'
                line = source.stdout.readline(2 * 1048576 + 1)
                if not line:
                    break
                phase = 'frame'
                if len(line) > 2 * 1048576 or not line.endswith(b'\n'):
                    raise RuntimeError('native_executor_frame_oversized')
                if admit:
                    value = json.loads(line)
                    frame = value['frame'].encode()
                    if len(frame) > 1048576:
                        raise RuntimeError('native_executor_frame_oversized')
                    payload = json.loads(frame)
                    if payload.get('method') == 'initialize':self.initialize_id = payload.get('id')
                    output = frame + b'\n'
                else:
                    payload = json.loads(line)
                    if payload.get('id') == self.initialize_id and 'result' in payload:
                        phase = 'identity'
                        info = payload['result'].get('environmentInfo', {})
                        phase = 'identity_version'
                        if info.get('executorVersion') != self.expected_version:
                            raise RuntimeError('native_executor_identity_mismatch')
                        phase = 'identity_platform'
                        if self.expected_platform is not None and info.get('platformOs') != self.expected_platform:
                            raise RuntimeError('native_executor_identity_mismatch')
                        self.ready = {'version': info['executorVersion'], 'platform': info.get('platformOs')}
                    output = json.dumps({'frame': line.decode().rstrip('\n')}).encode() + b'\n'
                phase = 'admission'
                with self.guard() if admit else nullcontext():
                    if self.closed:
                        break
                    phase = 'write'
                    write_pipe(destination.stdin, output)
        except Exception:
            with self.diagnostic_lock:
                if self.transport_diagnostic is None:
                    self.transport_diagnostic = {'direction': 'to_executor' if admit else 'from_executor',
                                                 'phase': phase, 'outcome': 'exception'}
            self.failure = 'native_executor_transport_failed'
        finally:
            if not self.closed:
                with self.diagnostic_lock:
                    if self.transport_diagnostic is None:
                        self.transport_diagnostic = {'direction': 'to_executor' if admit else 'from_executor',
                                                     'phase': 'read', 'outcome': 'eof'}
                self.failure = self.failure or 'native_executor_transport_closed'
                # Losing either pipe revokes the host endpoint immediately.
                try:self.bridge.stdin.close()
                except (OSError, ValueError):pass

    def check_authority(self):
        if self.closed or self.failure:
            raise RuntimeError(self.failure or 'native_executor_closed')
        with self.guard():
            pass

    def check_ready(self):
        self.check_authority()
        if self.ready is None:raise RuntimeError('native_executor_not_ready')
        return dict(self.ready)

    def registration(self):
        """Private app-server input. Never journal, log or publish this mapping."""
        self.check_authority()
        return {'environmentId': self.environment_id, 'execServerUrl': self.url,
                'authBearerToken': self.token, 'connectTimeoutMs': 5000}

    def selection(self):
        self.check_authority()
        return {'environmentId': self.environment_id, 'cwd': self.cwd, 'runtimeWorkspaceRoots': [self.cwd]}

    def close(self):
        import os
        import signal
        import subprocess
        self.closed = True
        self.token = None
        for process in (self.bridge, self.executor):
            if process is None:continue
            try:process.stdin.close()
            except (OSError, ValueError):pass
            if process.poll() is None:
                try:process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGTERM);process.wait(timeout=2)
                    except ProcessLookupError:pass
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL);process.wait(timeout=2)
        for thread in self.threads:
            thread.join(timeout=1)
        return {'process_exited': self.executor is None or self.executor.poll() is not None,
                'bridge_exited': self.bridge is None or self.bridge.poll() is not None,
                'capabilities_revoked': True, 'child_absence': 'environment_readback_required'}
