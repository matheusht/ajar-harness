#!/usr/bin/env python3
"""Failure-first native accounting workflow, with no external provider calls.

Scenarios specified before changes: three provider rounds in one invocation;
second invocation retries one transient error and counts only its two reported
rounds; abort after one completed
round retains that usage; a subsequent invocation excludes the aborted turn;
duplicate/stale notifications cannot replace a turn or lower cumulative usage;
completion is emitted once. Native request and billed-cost counts stay explicitly
unknown. Run on macOS with pinned Codex 0.166.0 and OMP 18.20.0 on PATH.
Input/output totals include their cached/reasoning subsets on both runtimes.
The HTTP fixture supplies usage; this checks native normalization, not billing.
"""
from __future__ import annotations
import argparse
from contextlib import nullcontext
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib
import json
from pathlib import Path
import platform
import shutil
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_native_runtime_adapters import profile, require, sha
from native_runtime_transport import HostOperation

TOOL = {'name': 'fixture_usage_probe', 'description': 'Return a harmless accounting fixture marker.',
        'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}}
ROUNDS = [(11, 7, 2, 1), (17, 5, 3, 2), (23, 3, 5, 1),
          (31, 13, 7, 3), (37, 17, 11, 4), (41, 19, 13, 5), (43, 23, 17, 7)]


def native(root, kind):
    require(platform.system() == 'Darwin' and shutil.which('sandbox-exec'), 'macOS sandbox required')
    executable = shutil.which(kind)
    require(executable, kind + ' binary unavailable')
    workspace = root / 'workspace'; workspace.mkdir()
    state = root / 'state'; state.mkdir(mode=0o700)
    mode = ['first']; counts = {}; requests = []; calls = []; events = []
    blocked = threading.Event(); release = threading.Event()
    class Model(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            length = int(self.headers['Content-Length'])
            require(length < 1024 * 1024, 'request oversized')
            body = json.loads(self.rfile.read(length))
            current = mode[0]; counts[current] = counts.get(current, 0) + 1
            step = counts[current]
            requests.append({'invocation': current, 'round': step})
            if current == 'second' and step == 1:
                self.send_response(500); self.send_header('Content-Type', 'application/json'); self.end_headers()
                self.wfile.write(b'{"error":{"message":"Temporary fixture failure","type":"server_error"}}'); self.wfile.flush()
                return
            if current == 'second': step -= 1
            if current == 'abort' and step == 2:
                blocked.set(); release.wait(10)
                return
            index = {'first': 0, 'second': 3, 'abort': 5, 'after_abort': 6}[current] + step - 1
            i, o, cache, reasoning = ROUNDS[index]
            more = step < {'first': 3, 'second': 2, 'abort': 2, 'after_abort': 1}[current]
            self.send_response(200); self.send_header('Content-Type', 'text/event-stream'); self.end_headers()
            if kind == 'codex':
                names = [tool.get('name') for tool in body.get('tools', []) if tool.get('name')]
                name = next((name for name in names if name.endswith('fixture_usage_probe')), None)
                require(name is not None, 'dynamic fixture tool absent')
                item = ({'id': f'fc_{index}', 'type': 'function_call', 'call_id': f'call-{index}',
                         'name': name, 'arguments': '{}'} if more else
                        {'id': f'msg_{index}', 'type': 'message', 'role': 'assistant',
                         'content': [{'type': 'output_text', 'text': 'Fixture complete.'}]})
                response = {'id': f'fixture-{index}', 'object': 'response', 'status': 'completed', 'output': [item],
                    'usage': {'input_tokens': i, 'output_tokens': o, 'total_tokens': i + o,
                              'input_tokens_details': {'cached_tokens': cache},
                              'output_tokens_details': {'reasoning_tokens': reasoning}}}
                frames = [{'type': 'response.created', 'response': dict(response, status='in_progress', output=[])},
                          {'type': 'response.output_item.added', 'output_index': 0, 'item': item},
                          {'type': 'response.output_item.done', 'output_index': 0, 'item': item},
                          {'type': 'response.completed', 'response': response}]
                for sequence, frame in enumerate(frames):
                    frame['sequence_number'] = sequence
                    self.wfile.write(('event: ' + frame['type'] + '\ndata: ' + json.dumps(frame) + '\n\n').encode())
            else:
                names = [tool['function']['name'] for tool in body.get('tools', [])]
                require('fixture_usage_probe' in names, 'host fixture tool absent')
                delta = ({'role': 'assistant', 'tool_calls': [{'index': 0, 'id': f'call-{index}', 'type': 'function',
                          'function': {'name': 'fixture_usage_probe', 'arguments': '{}'}}]} if more else
                         {'role': 'assistant', 'content': 'Fixture complete.'})
                for item in ({'delta': delta, 'finish_reason': None},
                             {'delta': {}, 'finish_reason': 'tool_calls' if more else 'stop'}):
                    frame = {'id': f'fixture-{index}', 'object': 'chat.completion.chunk', 'created': 0,
                             'model': 'fixture-model', 'choices': [{'index': 0, **item}]}
                    self.wfile.write(('data: ' + json.dumps(frame) + '\n\n').encode())
                self.wfile.write(('data: ' + json.dumps({'id': f'fixture-{index}', 'object': 'chat.completion.chunk',
                    'created': 0, 'model': 'fixture-model', 'choices': [], 'usage': {
                    'prompt_tokens': i, 'completion_tokens': o, 'total_tokens': i + o,
                    'prompt_tokens_details': {'cached_tokens': cache},
                    'completion_tokens_details': {'reasoning_tokens': reasoning}}}) + '\n\n').encode())
                self.wfile.write(b'data: [DONE]\n\n')
            self.wfile.flush()
    server = ThreadingHTTPServer(('127.0.0.1', 0), Model)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    config = profile(root, kind, Path(executable))
    config.update(provider='oslit-fixture', model='fixture-model')
    if kind == 'codex':
        Path(config['config_file']).write_text(f'''model = "fixture-model"
model_provider = "oslit-fixture"
web_search = "disabled"
[model_providers.oslit-fixture]
name = "Local simulated provider"
base_url = "http://127.0.0.1:{server.server_port}/v1"
wire_api = "responses"
requires_openai_auth = false
''')
        config['config_sha256'] = sha(Path(config['config_file']))
    else:
        (state / 'models.yml').write_text(json.dumps({'providers': {'oslit-fixture': {
            'baseUrl': f'http://127.0.0.1:{server.server_port}/v1', 'api': 'openai-completions', 'auth': 'none',
            'models': [{'id': 'fixture-model', 'name': 'Local fixture', 'reasoning': False,
                        'input': ['text'], 'supportsTools': True, 'contextWindow': 32768, 'maxTokens': 1024,
                        'cost': {'input': 1, 'output': 2, 'cacheRead': 0.5, 'cacheWrite': 1}}]}}}))
    def host_call(name, arguments):
        require(name == TOOL['name'] and arguments == {}, 'unexpected host action')
        calls.append({'invocation': mode[0], 'tool': name})
        return HostOperation(lambda: {'content': [{'type': 'text', 'text': 'harmless fixture marker'}]}, lambda: None)
    module = importlib.import_module('native_runtime_' + kind)
    runtime = None; outcomes = []
    try:
        runtime = module.Runtime(config, state, workspace, host_tools=[TOOL], host_call=host_call,
            dispatch_guard=nullcontext, command_prefix=['/usr/bin/sandbox-exec', '-p',
            f'(version 1)(allow default)(deny network*)(allow network-outbound (remote ip "localhost:{server.server_port}"))'])
        identity = runtime.fresh()
        for name, indices in [('first', [0, 1, 2]), ('second', [3, 4]), ('abort', [5]), ('after_abort', [6])]:
            mode[0] = name; start = len(events)
            runtime.invoke('Run the accounting fixture ' + name + '.', name)
            deadline = time.monotonic() + 35; interrupted = False
            while runtime.active and time.monotonic() < deadline:
                events.extend(runtime.observe(.05))
                if name == 'abort' and blocked.is_set() and not interrupted:
                    runtime.interrupt(); interrupted = True; release.set()
            events.extend(runtime.observe(.05))
            require(not runtime.active, kind + ' invocation did not finish: ' + name)
            completed = [row for row in events[start:] if row['event'] == 'completed']
            require(len(completed) == 1, json.dumps({'invocation': name, 'completion_count': len(completed), 'completed': completed, 'usage': runtime.usage, 'events': [row['event'] for row in events[start:]]}))
            expected = {'input_tokens': sum(ROUNDS[n][0] for n in indices),
                        'output_tokens': sum(ROUNDS[n][1] for n in indices),
                        'cached_input_tokens': sum(ROUNDS[n][2] for n in indices),
                        'reasoning_output_tokens': sum(ROUNDS[n][3] for n in indices),
                        'total_tokens': sum(ROUNDS[n][0] + ROUNDS[n][1] for n in indices)}
            actual = runtime.usage
            require(actual and all(actual.get(key) == value for key, value in expected.items()),
                    json.dumps({'runtime': kind, 'invocation': name, 'expected': expected, 'actual': actual}))
            require(actual['monetary_spend'] is None and actual['provider_requests'] is None,
                    'unavailable provider dimensions inferred')
            if kind == 'omp':
                expected_cost = sum((ROUNDS[n][0] - ROUNDS[n][2] + 2 * ROUNDS[n][1] + .5 * ROUNDS[n][2]) / 1000000 for n in indices)
                require(abs(actual['estimated_cost'] - expected_cost) < 1e-12, 'cost delta wrong')
            require(completed[0]['status'] in ({'interrupted', 'aborted'} if name == 'abort' else {'completed'}),
                    'wrong completion status')
            outcomes.append({'invocation': name, 'expected': expected, 'usage': actual, 'completion': completed[0]['status']})
        require(counts == {'first': 3, 'second': 3, 'abort': 2, 'after_abort': 1}, 'unexpected provider retries')
        require(len(calls) == 4, 'unexpected host tool count')
        return {'runtime': kind, 'status': 'passed', 'evidence': 'actual_native_loopback_simulated_provider',
                'identity': identity, 'runtime_version': config['version'], 'executable': config['executable'],
                'outcomes': outcomes, 'requests': requests,
                'host_calls': calls, 'external_provider_calls': 0,
                'unverified': ['live_provider_billing', 'research_qualification', 'Linux_native_execution']}
    finally:
        release.set()
        if runtime: runtime.close()
        server.shutdown(); server.server_close(); thread.join(timeout=2)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--runtime', choices=['codex', 'omp', 'all'], default='all')
    parser.add_argument('--output', type=Path); args = parser.parse_args()
    results = []
    with tempfile.TemporaryDirectory(prefix='native-usage-accounting-') as temp:
        for kind in (['codex', 'omp'] if args.runtime == 'all' else [args.runtime]):
            root = Path(temp).resolve() / kind; root.mkdir()
            try: results.append(native(root, kind))
            except Exception as error: results.append({'runtime': kind, 'status': 'failed', 'error': str(error), 'error_type': type(error).__name__})
    result = {'status': 'passed' if all(row['status'] == 'passed' for row in results) else 'failed', 'results': results}
    encoded = json.dumps(result, indent=2) + '\n'
    if args.output: args.output.write_text(encoded)
    print(encoded, end=''); return 0 if result['status'] == 'passed' else 1

if __name__ == '__main__': raise SystemExit(main())
