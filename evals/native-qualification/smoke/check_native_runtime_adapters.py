#!/usr/bin/env python3
"""Failure-first runtime workflow specification and repeatable control checks.

Written before the adapters. Real control checks require pinned Codex 0.166.0,
OMP 18.20.0 and macOS sandbox-exec. They deny networking, submit no prompt and
assert fresh contexts, model readback, idle interruption and process exit.
Controlled protocol subprocesses exercise malformed/oversized frames, changed
pins, duplicate callbacks, stale dispatch, secret/meaningless usage rejection,
yield-before-settlement and late completion. These are simulated agent events,
not provider, native-tool containment, research or multi-day qualification.

Expected outputs are saved JSON receipts, with no raw runtime transcript.
Run: python3 <this-file> --output /private/checks/runtime-adapters.json
Use --live to add actual installed native control checks.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, nullcontext
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib
import json
import os
from pathlib import Path
import platform
import shutil
import shlex
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def sha(path):
    with path.open('rb') as stream:
        return 'sha256:' + hashlib.file_digest(stream, 'sha256').hexdigest()


def profile(root, kind, executable):
    config = root / (kind + '.config')
    config.write_text('' if kind == 'codex' else json.dumps({
        'plan': {'enabled': False}, 'tools': {'xdev': False}, 'autolearn': {'enabled': False}}) + '\n')
    schema = root / (kind + '.schema.json')
    schema.write_text(json.dumps({'runtime': kind, 'probe': 'controlled-wire-contract'}))
    return {'kind': kind, 'version': '0.166.0' if kind == 'codex' else '18.20.0',
            'executable': {'path': str(executable.resolve()), 'sha256': sha(executable)},
            'protocol': {'mode': 'stdio-jsonrpc' if kind == 'codex' else 'stdio-jsonl',
                         'schema_file': str(schema), 'schema_sha256': sha(schema)},
            'config_file': str(config), 'config_sha256': sha(config),
            'provider': 'openai' if kind == 'codex' else 'opencode-go',
            'model': 'gpt-6.1-sol' if kind == 'codex' else 'deepseek-v4.1-flash',
            'credential_ref': None, 'required_capabilities': ['startup', 'fresh_session']}


PEER = '''#!/usr/bin/env python3
import json,sys
kind=KIND
if '--version' in sys.argv:
 print('codex-cli 0.166.0' if kind=='codex' else 'omp/18.20.0');sys.exit()
seq=0
prompts=0
session='session-0'
prompt_id=None
host_tools=[]
def emit(x):print(json.dumps(x),flush=True)
if kind=='omp':emit({'type':'ready','protocolVersion':1,'supportedProtocolVersions':[1,2],'maxFrameBytes':1048576,'maxReassembledFrameBytes':67108864})
for line in sys.stdin:
 x=json.loads(line);op=x.get('method',x.get('type'));ident=x.get('id');a=x.get('params',x)
 if kind=='codex' and op is None and 'result' in x:
  assert x['result']['contentItems'] and all(c['type']=='inputText' and isinstance(c['text'],str) for c in x['result']['contentItems'])
 if op is None or op in ['host_tool_result','host_tool_update']:continue
 if 'id' not in x:continue
 if kind=='codex':
  result={}
  if op=='initialize':result={'userAgent':'codex-test'}
  elif op=='thread/start':
   seq+=1;session='session-'+str(seq);result={'thread':{'id':session,'turns':[]},'model':a['model'],'modelProvider':a['modelProvider']}
  elif op in ['thread/resume','thread/read']:result={'thread':{'id':a['threadId'],'turns':[]},'model':'gpt-6.1-sol','modelProvider':'openai'}
  elif op=='turn/start':result={'turn':{'id':'turn-1','status':'inProgress'}}
  prompt=a['input'][0]['text'] if op=='turn/start' else ''
  if op=='turn/start' and prompt=='ordinary':
   emit({'method':'turn/started','params':{'threadId':session,'turn':{'id':'turn-1'}}})
   emit({'id':'call-early','method':'item/tool/call','params':{'threadId':session,'turnId':'turn-1','callId':'tool-1','tool':'engagement_status','arguments':{}}})
  if op=='turn/start' and prompt.startswith('admission|'):
   _,marker,requests=prompt.split('|',2)
   try:
    with open(requests) as f:count=int(f.read())
   except FileNotFoundError:count=0
   with open(requests,'w') as f:f.write(str(count+1))
   import time
   deadline=time.monotonic()+10
   while not __import__('os').path.exists(marker) and time.monotonic()<deadline:time.sleep(.005)
   if not __import__('os').path.exists(marker):sys.exit(17)
  emit({'id':ident,'result':result})
  if op=='turn/start' and prompt.startswith('admission|'):
   emit({'method':'turn/completed','params':{'threadId':session,'turn':{'id':'turn-1','status':'completed'}}})
  if op=='turn/start':
   prompt=a['input'][0]['text']
   if prompt=='malformed':print('{bad',flush=True)
   elif prompt=='oversize':print('x'*1048577,flush=True)
   elif prompt=='canceltool':
    emit({'id':'call-cancel','method':'item/tool/call','params':{'threadId':session,'turnId':'turn-1','callId':'tool-cancel','tool':'engagement_status','arguments':{'long':True}}})
   else:
    emit({'method':'item/reasoning/textDelta','params':{'threadId':session,'turnId':'turn-1','delta':'NEVER_PUBLISH_REASONING'}})
    emit({'method':'item/agentMessage/delta','params':{'threadId':session,'turnId':'turn-1','delta':'Authorization: '+'Bearer '+'fake-secret-value'}})
    call={'id':'call-1','method':'item/tool/call','params':{'threadId':session,'turnId':'turn-1','callId':'tool-1','tool':'engagement_status','arguments':{}}}
    emit(call);emit(call)
    emit({'method':'thread/tokenUsage/updated','params':{'threadId':session,'turnId':'turn-1','tokenUsage':{'last':{'inputTokens':2,'outputTokens':1,'cachedInputTokens':0,'cacheWriteInputTokens':0,'reasoningOutputTokens':0,'totalTokens':3},'total':{'inputTokens':2,'outputTokens':1,'cachedInputTokens':0,'totalTokens':3}}}})
    emit({'method':'turn/completed','params':{'threadId':session,'turn':{'id':'turn-1','status':'completed'}}})
  elif op=='turn/interrupt':emit({'method':'turn/completed','params':{'threadId':session,'turn':{'id':'turn-1','status':'interrupted'}}})
 else:
  data={}
  if op=='new_session':seq+=1;session='session-'+str(seq);data={'cancelled':False}
  elif op=='set_host_tools':host_tools=a['tools']
  elif op in ['get_state','set_model']:data={'sessionId':session,'isSettled':True,'isStreaming':False,'model':{'provider':'opencode-go','id':'deepseek-v4.1-flash'},'dumpTools':host_tools} if op=='get_state' else {'provider':'opencode-go','id':'deepseek-v4.1-flash'}
  elif op=='get_subagents':data={'subagents':[]}
  elif op=='get_session_stats':data={'tokens':{'input':2*prompts,'output':prompts,'reasoning':0,'cacheRead':0,'cacheWrite':0,'total':3*prompts},'cost':0.01*prompts,'premiumRequests':prompts}
  if op=='prompt' and a['message'].endswith('ordinary'):
   emit({'type':'host_tool_call','id':'tool-early','toolCallId':'tool-1','toolName':'engagement_status','arguments':{}})
  emit({'id':ident,'type':'response','command':op,'success':True,'data':data})
  if op=='prompt':
   prompt_id=ident
   prompts+=1
   if a['message'].endswith('malformed'):print('{bad',flush=True)
   elif a['message'].endswith('oversize'):print('x'*1048577,flush=True)
   elif a['message'].endswith('canceltool'):
    emit({'type':'host_tool_call','id':'tool-cancel','toolCallId':'tool-cancel','toolName':'engagement_status','arguments':{'long':True}})
   else:
    emit({'type':'message_update','message':{'role':'assistant'},'assistantMessageEvent':{'type':'thinking_delta','delta':'NEVER_PUBLISH_REASONING'}})
    emit({'type':'message_update','message':{'role':'assistant'},'assistantMessageEvent':{'type':'text_delta','delta':'Cookie: session=fake-secret-value'}})
    call={'type':'host_tool_call','id':'tool-1','toolCallId':'tool-1','toolName':'engagement_status','arguments':{}}
    emit(call);emit(call)
    emit({'type':'prompt_result','id':ident,'agentInvoked':True,'status':'completed','sessionSettled':False})
    emit({'type':'session_settled'})
  elif op=='abort_and_restore_queue':emit({'type':'prompt_result','id':prompt_id,'agentInvoked':True,'status':'aborted','sessionSettled':True})
'''


def controlled(root, kind):
    module = importlib.import_module('native_runtime_' + kind)
    from native_runtime_transport import RuntimeError
    peer = root / (kind + '-peer')
    peer.write_text(PEER.replace('KIND', repr(kind)))
    peer.chmod(0o700)
    config = profile(root, kind, peer)
    calls = []
    allowed = [True]
    guarded = [False]
    cancelled = threading.Event()

    @contextmanager
    def guard():
        if not allowed[0]:
            raise RuntimeError('assignment_revoked')
        require(not guarded[0], 'nested dispatch lock')
        guarded[0] = True
        try:
            yield
        finally:
            guarded[0] = False

    def host(name, arguments):
        require(guarded[0], 'host acceptance outside dispatch lock')
        calls.append((name, arguments))
        def wait_result():
            require(not guarded[0], 'long operation holds dispatch lock')
            if arguments.get('long'):
                require(cancelled.wait(3), 'host cancellation never delivered')
            return {'content': [{'type': 'text', 'text': 'ready'}]}
        return HostOperation(wait_result, cancelled.set)

    tools = [{'name': 'engagement_status', 'description': 'Read own assignment',
              'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}}]
    runtime = module.Runtime(config, root / (kind + '-state'), root,
                             host_tools=tools, host_call=host, dispatch_guard=guard)
    try:
        first = runtime.fresh()
        second = runtime.fresh()
        require(first['session_id'] != second['session_id'], 'fresh session reused history')
        require(runtime.resume(second['session_id'])['session_id'] == second['session_id'], 'live resume lost identity')
        runtime.invoke('ordinary', 'invocation-1')
        events = []
        for _ in range(20):
            events.extend(runtime.observe(1))
            if any(x['event'] == 'completed' for x in events):
                break
        require(any(x['event'] == 'completed' and x['invocation_id'] == 'invocation-1' for x in events), 'missing invocation completion')
        require(len(calls) == 1, 'duplicate host call repeated effect')
        encoded = json.dumps(events)
        require('fake-secret-value' not in encoded and 'NEVER_PUBLISH_REASONING' not in encoded, 'unsafe runtime text published')
        usage = [x for x in events if x['event'] == 'usage']
        require(usage and usage[-1]['usage']['total_tokens'] == 3, 'usage not normalized')
        runtime.invoke('canceltool', 'invocation-2')
        began = time.monotonic()
        runtime.observe(.1)
        require(time.monotonic() - began < 1 and len(calls) == 2, 'host wait blocks control loop')
        runtime.interrupt()
        require(cancelled.is_set(), 'native interrupt did not cancel host operation')
        for _ in range(5):
            runtime.observe(.1)
            if not runtime.active:
                break
        require(not runtime.active, 'native interrupted turn remained active')
        runtime.invoke('ordinary', 'invocation-3')
        for _ in range(10):
            runtime.observe(.1)
            if not runtime.active:
                break
        require(len(calls) == 3, 'native call ID reused another invocation outcome')
        allowed[0] = False
        try:
            runtime.invoke('ordinary', 'invocation-4')
            raise AssertionError('revoked worker dispatched')
        except RuntimeError as error:
            require(str(error) == 'assignment_revoked', 'wrong guard refusal')
    finally:
        closed = runtime.close()
    require(closed['process_exited'] and closed['exit_code'] == 0 and closed['lab_cleanup'] == 'not_observed',
            'peer protocol failure or process exit confused with lab cleanup')
    for bad in ['malformed', 'oversize']:
        rt = module.Runtime(config, root / (kind + '-' + bad), root, dispatch_guard=nullcontext)
        try:
            rt.fresh()
            try:
                rt.invoke(bad, bad)
                for _ in range(4):rt.observe(1)
                raise AssertionError('bad frame accepted')
            except RuntimeError:
                pass
        finally:rt.close()
    changed = {**config, 'executable': {**config['executable'], 'sha256': 'sha256:' + '0' * 64}}
    try:
        module.Runtime(changed, root / (kind + '-badpin'), root)
        raise AssertionError('changed executable admitted')
    except RuntimeError:
        pass
    return {'runtime': kind, 'status': 'passed', 'evidence': 'controlled_protocol_subprocesses',
            'checks': ['fresh', 'live_resume', 'usage', 'duplicate_callback', 'revoked_dispatch',
                       'guarded_acceptance', 'unlocked_completion', 'responsive_tool_wait', 'host_cancellation',
                       'redaction', 'reasoning_omission',
                       'malformed_frame', 'oversized_frame', 'pin_mismatch', 'process_exit'],
            'events': events}


def codex_executor_admission(root, capture_red=False):
    """A turn response waits for a background executor send through the dispatch guard."""
    module = importlib.import_module('native_runtime_codex')
    from native_runtime_transport import HostOperation, RuntimeError
    peer = root / 'codex-admission-peer'
    peer.write_text(PEER.replace('KIND', repr('codex')))
    peer.chmod(0o700)
    config = profile(root, 'codex', peer)
    lock = threading.RLock()
    allowed = [True]
    request_sent = threading.Event()
    sent = threading.Event()
    send_times = []
    guard_state = threading.local()
    turn_start_sends = [0]
    wait_finished_at = []

    @contextmanager
    def guard():
        if not allowed[0]:
            raise RuntimeError('assignment_revoked')
        with lock:
            if not allowed[0]:
                raise RuntimeError('assignment_revoked')
            guard_state.depth = getattr(guard_state, 'depth', 0) + 1
            try:
                yield
            finally:
                guard_state.depth -= 1

    def executor_send():
        request_sent.wait(2)
        try:
            with guard():
                send_times.append(time.monotonic())
                marker.write_text('guarded')
                sent.set()
        except RuntimeError:
            return

    tools = [{'name': 'engagement_status', 'description': 'Read own assignment',
              'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}}]
    runtime = module.Runtime(config, root / 'codex-admission-state', root,
                             host_tools=tools, host_call=lambda *_: None, dispatch_guard=guard)
    marker, request_count = root / 'executor-admitted', root / 'peer-turn-start-count'
    old_request = runtime.transport.request
    old_send = runtime.transport.send

    def send(value):
        if value.get('method') == 'turn/start':
            require(getattr(guard_state, 'depth', 0) > 0, 'turn/start send was not guarded')
            turn_start_sends[0] += 1
        old_send(value)
        if value.get('method') == 'turn/start':
            request_sent.set()

    def bounded_request(operation, params=None, **kwargs):
        if operation == 'turn/start':
            kwargs['timeout'] = .5
        try:
            return old_request(operation, params, **kwargs)
        finally:
            if operation == 'turn/start':
                wait_finished_at.append(time.monotonic())

    runtime.transport.request = bounded_request
    runtime.transport.send = send
    outcome = 'passed'
    try:
        runtime.fresh()
        worker = threading.Thread(target=executor_send, daemon=True)
        worker.start()
        prompt = f'admission|{marker}|{request_count}'
        try:
            runtime.invoke(prompt, 'executor-admission')
        except RuntimeError as error:
            outcome = str(error)
        # The old implementation times out while its outer admission still owns the lock;
        # its executor sender can enter only after the timeout unwinds.
        if outcome != 'passed':
            sent.wait(1)
        else:
            require(sent.wait(1), 'executor send did not pass the guard')
        require(marker.exists() == sent.is_set(), 'executor send marker was not guarded')
        worker.join(1)
        require(not worker.is_alive(), 'background executor sender did not settle')
        if outcome == 'passed':
            require(send_times and send_times[0] < wait_finished_at[0],
                    'executor admission did not release the native response wait')
            runtime.observe(.1)
            require(not runtime.active, 'controlled turn did not settle before revoked-send check')
            allowed[0] = False
            try:
                runtime.invoke(prompt, 'revoked-executor-admission')
                raise AssertionError('revoked request was dispatched')
            except RuntimeError as error:
                require(str(error) == 'assignment_revoked', 'revoked send had wrong refusal')
            require(turn_start_sends[0] == 1, 'revoked turn/start reached the transport send')
            require(request_count.read_text() == '1', 'revoked invocation reached native peer')
        elif capture_red:
            require(outcome == 'native_response_timeout', 'unexpected pre-fix failure: ' + outcome)
            require(marker.exists() and sent.is_set(), 'executor send never proceeded after request wait released')
            require(send_times[0] >= wait_finished_at[0],
                    'executor send was not delayed until the response wait ended')
        else:
            raise AssertionError('executor admission blocked turn response: ' + outcome)
    finally:
        runtime.close()
    if outcome != 'passed':
        return {'runtime': 'codex', 'status': 'red_observed', 'error': outcome,
                'checks': ['peer_waited_for_executor_send', 'turn_start_guarded', 'executor_send_guarded',
                           'executor_send_after_response_wait_ended'],
                'revoked_send': 'not_reached'}
    return {'runtime': 'codex', 'status': 'passed', 'evidence': 'controlled_native_peer_and_guard',
            'checks': ['peer_waited_for_executor_send', 'turn_start_guarded', 'executor_send_guarded',
                       'turn_response_after_guard_release',
                       'revoked_send_refused_before_peer']}


def live(root, kind):
    module = importlib.import_module('native_runtime_' + kind)
    executable = shutil.which(kind)
    if platform.system() != 'Darwin' or not shutil.which('sandbox-exec') or not executable:
        return {'runtime': kind, 'status': 'unavailable', 'reason': 'native_binary_or_macos_network_sandbox_missing'}
    config = profile(root, kind, Path(executable))
    rt = module.Runtime(config, root / (kind + '-live'), root,
                        command_prefix=['/usr/bin/sandbox-exec', '-p', '(version 1)(allow default)(deny network*)'])
    try:
        first = rt.fresh();second = rt.fresh()
        require(first['session_id'] != second['session_id'], 'native fresh context reused')
        require(rt.resume(second['session_id'])['session_id'] == second['session_id'], 'native live resume changed session')
        rt.interrupt()
        caps = rt.capabilities()
        require(caps['execution_boundary'] == 'external_owner_required', 'control probe claims containment')
    finally:closed = rt.close()
    require(closed['process_exited'], 'native process survived close')
    return {'runtime': kind, 'status': 'passed', 'evidence': 'actual_native_provider_free_control',
            'first': first, 'second': second, 'close': closed, 'capabilities': caps,
            'executable': config['executable'], 'model': config['model'], 'provider': config['provider']}


def native_tools(root, sdk):
    """Actual SDK tools, no model/credential access; outer OS sandbox is test-only."""
    from native_runtime_omp import ToolOwner, sdk_tree_digest
    from native_runtime_transport import RuntimeError
    workspace = root / 'tool-workspace'
    workspace.mkdir()
    state = root / 'tool-state'
    sdk_pin = {'root': str(sdk.resolve().parents[2]), 'sha256': sdk_tree_digest(sdk.resolve().parents[2])}
    try:
        ToolOwner(sdk, workspace, root / 'tool-bad-pin', sdk_pin={**sdk_pin, 'sha256': 'sha256:' + '0' * 64},
                  command_prefix=['/usr/bin/sandbox-exec', '-p', '(version 1)(allow default)(deny network*)'],
                  dispatch_guard=nullcontext)
        raise AssertionError('changed SDK dependencies admitted')
    except RuntimeError as error:
        require(str(error) == 'native_sdk_pin_mismatch', 'wrong SDK pin refusal')
    owner = ToolOwner(sdk, workspace, state,
                      sdk_pin=sdk_pin,
                      command_prefix=['/usr/bin/sandbox-exec', '-p', '(version 1)(allow default)(deny network*)'],
                      dispatch_guard=nullcontext)
    results = []
    try:
        require('read' in [t['name'] for t in owner.catalog], 'native read missing')
        require('task' not in [t['name'] for t in owner.catalog], 'native spawn exposed')
        for name, arguments, call_id in [
            ('write', {'path': str(workspace / 'proof.txt'), 'content': 'native-sdk-proof'}, 'write-1'),
            ('read', {'path': str(workspace / 'proof.txt')}, 'read-1'),
            ('bash', {'command': 'printf native-shell-proof', 'timeout': 5}, 'bash-1')]:
            owner.invoke(name, arguments, call_id)
            for _ in range(20):
                rows = owner.observe(1)
                results.extend(rows)
                if any(x['call_id'] == call_id for x in rows):break
            else:raise AssertionError('native tool did not finish')
        require((workspace / 'proof.txt').read_text() == 'native-sdk-proof', 'native write lost bytes')
        require('native-sdk-proof' in json.dumps(results), 'native read did not observe write')
        require('native-shell-proof' in json.dumps(results), 'native shell did not run')
        try:
            owner.invoke('task', {}, 'denied-1')
            raise AssertionError('native unregistered task dispatched')
        except RuntimeError:pass
        owner.invoke('bash', {'command': 'sleep 10', 'timeout': 20}, 'cancel-1')
        owner.interrupt('cancel-1')
        for _ in range(10):
            rows = owner.observe(1);results.extend(rows)
            if any(x['call_id'] == 'cancel-1' for x in rows):break
        require(any(x['call_id'] == 'cancel-1' for x in results), 'native tool cancellation missing outcome')
    finally:closed = owner.close()
    require(closed['process_exited'], 'native tool owner stayed alive')
    return {'status': 'passed', 'evidence': 'actual_native_sdk_tools_no_provider',
            'runtime': 'omp', 'sdk_version': '18.20.0', 'sdk_pin': sdk_pin['sha256'], 'results': results,
            'boundary': 'host-network-denial-only; not lab qualification', 'close': closed}


def native_bridge(root, sdk):
    """Actual OMP and SDK, deterministic loopback model responses, no credentials."""
    from native_runtime_omp import Runtime, ToolOwner, sdk_tree_digest
    workspace = root / 'bridge-workspace'; workspace.mkdir()
    state = root / 'bridge-runtime'; state.mkdir(mode=0o700)
    pid_file = workspace / 'child.pid'
    requests = []
    class Model(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            length = int(self.headers['Content-Length'])
            require(length <= 1024 * 1024, 'fixture request oversized')
            request = json.loads(self.rfile.read(length))
            names = [tool['function']['name'] for tool in request.get('tools', [])]
            require('bash' in names and 'task' not in names, 'unexpected native model tools')
            requests.append({'number': len(requests) + 1, 'tool_names': names})
            count = len(requests)
            if count in (1, 3):
                command = ('printf native-bridge-proof' if count == 1 else
                           shlex.join([sys.executable, '-c',
                            'import os,time,pathlib; pathlib.Path(' + repr(str(pid_file)) +
                            ').write_text(str(os.getpid())); time.sleep(20)']))
                delta = {'role': 'assistant', 'tool_calls': [{'index': 0, 'id': 'fixture-call-' + str(count),
                    'type': 'function', 'function': {'name': 'bash',
                    'arguments': json.dumps({'command': command, 'timeout': 5})}}]}
                finish = 'tool_calls'
            else:
                delta, finish = {'role': 'assistant', 'content': 'Local fixture completed.'}, 'stop'
            self.send_response(200); self.send_header('Content-Type', 'text/event-stream'); self.end_headers()
            for item in ({'delta': delta, 'finish_reason': None}, {'delta': {}, 'finish_reason': finish}):
                chunk = {'id': 'fixture-' + str(count), 'object': 'chat.completion.chunk', 'created': 0,
                         'model': 'fixture-model', 'choices': [{'index': 0, **item}]}
                self.wfile.write(('data: ' + json.dumps(chunk) + '\n\n').encode())
            self.wfile.write(b'data: [DONE]\n\n'); self.wfile.flush()

    server = ThreadingHTTPServer(('127.0.0.1', 0), Model)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    port = server.server_address[1]
    (state / 'models.yml').write_text(json.dumps({'providers': {'oslit-fixture': {
        'baseUrl': f'http://127.0.0.1:{port}/v1', 'api': 'openai-completions', 'auth': 'none',
        'models': [{'id': 'fixture-model', 'name': 'Local fixture', 'reasoning': False,
                    'input': ['text'], 'supportsTools': True, 'contextWindow': 32768, 'maxTokens': 1024,
                    'cost': {'input': 0, 'output': 0, 'cacheRead': 0, 'cacheWrite': 0}}]}}}))
    sdk_root = sdk.resolve().parents[2]
    owner = ToolOwner(sdk, workspace, root / 'bridge-tools',
        sdk_pin={'root': str(sdk_root), 'sha256': sdk_tree_digest(sdk_root)}, dispatch_guard=nullcontext,
        command_prefix=['/usr/bin/sandbox-exec', '-p', '(version 1)(allow default)(deny network*)'])
    config = profile(root, 'omp', Path(shutil.which('omp')))
    config.update(provider='oslit-fixture', model='fixture-model')
    runtime = None
    events = []
    try:
        runtime = Runtime(config, state, workspace, host_tools=owner.catalog, host_call=owner.host_call,
            dispatch_guard=nullcontext, command_prefix=['/usr/bin/sandbox-exec', '-p',
            f'(version 1)(allow default)(deny network*)(allow network-outbound (remote ip "localhost:{port}"))'])
        runtime.fresh()
        runtime.invoke('Run the harmless fixture tool.', 'bridge-normal')
        for _ in range(100):
            events.extend(runtime.observe(.1))
            if not runtime.active:
                break
        require(not runtime.active and len(requests) == 2, 'native tool loop did not settle')
        require('native-bridge-proof' in json.dumps(list(owner.results.values())), 'actual SDK result missing')
        runtime.invoke('Run the cancellation fixture.', 'bridge-cancel')
        for _ in range(100):
            events.extend(runtime.observe(.05))
            if pid_file.exists():
                break
        require(pid_file.exists(), 'actual native shell process never started')
        pid = int(pid_file.read_text())
        runtime.interrupt()
        for _ in range(40):
            events.extend(runtime.observe(.05))
            if not runtime.active and not owner.active:
                break
        require(not runtime.active and not owner.active, 'native cancellation did not settle host operation')
        require(any(event['event'] == 'host_tool_cancel' for event in events), 'native cancellation frame missing')
        readback = subprocess.run(['ps', '-p', str(pid), '-o', 'args='], capture_output=True, text=True)
        require(readback.returncode != 0, 'owned shell child survived native cancellation')
        return {'runtime': 'omp', 'status': 'passed', 'evidence': 'actual_native_sdk_with_simulated_model',
                'checks': ['native_tool_roundtrip', 'native_interrupt', 'host_tool_cancel', 'owned_child_absent'],
                'requests': requests, 'events': events, 'external_provider_calls': 0,
                'sdk_pin': sdk_tree_digest(sdk_root), 'lab_isolation': 'not_qualified'}
    finally:
        if runtime:runtime.close()
        owner.close();server.shutdown();server.server_close();thread.join(timeout=2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--capture-admission-red', action='store_true',
                        help='expect and record the current Codex executor-admission timeout')
    parser.add_argument('--admission-only', action='store_true',
                        help='run only the controlled Codex executor-admission regression')
    parser.add_argument('--omp-sdk', type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='native-runtime-e2e-') as temporary:
        root = Path(temporary).resolve()
        if args.admission_only:
            rows = [codex_executor_admission(root, capture_red=args.capture_admission_red)]
        else:
            rows = [controlled(root, kind) for kind in ['codex', 'omp']]
            rows.append(codex_executor_admission(root, capture_red=args.capture_admission_red))
            if args.live:
                rows.extend(live(root, kind) for kind in ['codex', 'omp'])
            if args.omp_sdk:
                rows.append(native_tools(root, args.omp_sdk))
                rows.append(native_bridge(root, args.omp_sdk))
    result = {'kind': 'native-runtime-adapter-checks-v1', 'results': rows,
              'unverified': ['provider_inference', 'complete_worker_revocation', 'lab_isolation',
                             'durable_native_transcript_resume', 'multi_day_operation']}
    result['source_hashes'] = {str(path.relative_to(ROOT)): sha(path) for path in
        [Path(__file__), *sorted((ROOT / 'tools').glob('native_runtime_*'))] if path.is_file()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': 'passed', 'output': str(args.output), 'checks': len(rows)}))


if __name__ == '__main__':
    main()
