"""Codex app-server control adapter. Native wire frames stay private to this module."""
from __future__ import annotations

from pathlib import Path

from native_runtime_transport import PendingTool, RuntimeError, Session, Transport, identifier, text_content


class Runtime(Session):
    kind = 'codex'
    version = '0.166.0'

    def __init__(self, profile, state_dir, workspace, *, command_prefix=(), host_tools=(),
                 host_call=None, dispatch_guard=None):
        env = self._prepare(profile, state_dir, workspace, host_tools, host_call, dispatch_guard)
        if profile['protocol']['mode'] != 'stdio-jsonrpc':
            raise RuntimeError('native_protocol_mismatch')
        env['CODEX_HOME'] = str(self.state_dir)
        self.totals = {}
        self.before = {}
        config = self.state_dir / 'config.toml'
        content = Path(profile['config_file']).read_bytes()
        if config.exists() and (config.is_symlink() or config.read_bytes() != content):
            raise RuntimeError('runtime_state_config_changed')
        config.write_bytes(content)
        config.chmod(0o400)
        command = [*command_prefix, profile['executable']['path'], 'app-server', '--stdio']
        try:
            self.transport = Transport(command, env, str(self.workspace), self._event)
            self.transport.request('initialize', {'clientInfo': {'name': 'oslit-runtime', 'version': '2'},
                                                  'capabilities': {'experimentalApi': True}})
            self.transport.send({'jsonrpc': '2.0', 'method': 'initialized'})
        except Exception:
            self.close()
            raise

    def _identity(self, result):
        session = identifier(result.get('thread', {}).get('id'))
        if result.get('model') != self.profile['model'] or result.get('modelProvider') != self.profile['provider']:
            raise RuntimeError('native_model_mismatch')
        self.session_id = session
        self.sessions.add(session)
        return {'session_id': session, 'runtime': self.kind, 'model': self.profile['model'],
                'provider': self.profile['provider'], 'history': 'ephemeral'}

    def fresh(self):
        self._idle()
        result = self.transport.request('thread/start', {
            'ephemeral': True, 'cwd': str(self.workspace), 'model': self.profile['model'],
            'modelProvider': self.profile['provider'], 'approvalPolicy': 'never', 'sandbox': 'read-only',
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
        return self._identity(dict(result, model=self.profile['model'], modelProvider=self.profile['provider']))

    def invoke(self, prompt, invocation_id):
        with self._admission():
            self._begin(invocation_id, prompt)
            self.before = dict(self.totals.get(self.session_id, {}))
            try:
                result = self.transport.request('turn/start', {'threadId': self.session_id,
                          'model': self.profile['model'], 'input': [{'type': 'text', 'text': prompt}]}, defer_events=True)
            except Exception:
                self._emit('unknown', reason='native_dispatch_not_settled')
                raise
        try:
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
        with self._admission():
            self.transport.request('turn/steer', {'threadId': self.session_id, 'expectedTurnId': self.native_turn,
                                                 'input': [{'type': 'text', 'text': message}]}, defer_events=True)
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
        if method == 'item/tool/call' and 'id' in frame:
            if (params.get('threadId') != self.session_id or not self.active or
                    params.get('turnId') != self.native_turn):
                pending = PendingTool(response={'content': [{'type': 'text', 'text': 'Stale native assignment.'}], 'isError': True})
            else:
                pending = self._tool(params.get('callId'), params.get('tool'), params.get('arguments'))
            self._queue_tool_reply(frame['id'], pending, lambda result: self._tool_reply(frame['id'], result))
            return
        if 'id' in frame and method:
            # Never approve an unconfigured permission, credential, or tool route.
            self.transport.send({'jsonrpc': '2.0', 'id': frame['id'], 'error': {
                'code': -32601, 'message': 'Host operation unavailable'}})
            return
        if not self.active or params.get('threadId') != self.session_id:
            return
        if method == 'turn/started':
            self.native_turn = identifier(params.get('turn', {}).get('id'))
        turn = params.get('turnId') or params.get('turn', {}).get('id')
        if turn != self.native_turn:
            return
        if method == 'thread/tokenUsage/updated':
            total = params.get('tokenUsage', {}).get('total', {})
            if any(type(v) is not int or v < self.before.get(k, 0) for k, v in total.items()):
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
