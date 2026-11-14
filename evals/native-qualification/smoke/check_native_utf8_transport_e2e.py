#!/usr/bin/env python3
"""Failure-first UTF-8 wire checks through real subprocess pipes.

Before the encoder change: admitted multilingual prompts below 512 KiB fail on
ASCII-escaped wire size; native Codex/OMP control peers must receive exact text;
public payload and asynchronous result limits must count the same UTF-8 bytes.
The 1 MiB wire cap and secret/invalid-text rejection must remain effective.
No model or external provider is used; peers simulate native protocols.
"""
from contextlib import nullcontext
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'tools'), str(Path(__file__).resolve().parent)]
from check_native_runtime_adapters import profile, require
from native_runtime_transport import HostOperation, MAX_FRAME, PendingTool, RuntimeError, Transport, public

PEER = r'''#!/usr/bin/env python3
import hashlib,json,sys
kind=KIND
if '--version' in sys.argv:
 print('codex-cli 0.166.0' if kind=='codex' else 'omp/18.20.0');sys.exit()
prompts=0
session='utf8-session'
def emit(x):print(json.dumps(x,ensure_ascii=False),flush=True)
if kind=='omp':emit({'type':'ready','protocolVersion':1,'supportedProtocolVersions':[1,2]})
for line in sys.stdin:
 x=json.loads(line);op=x.get('method',x.get('type'));ident=x.get('id');a=x.get('params',x)
 if ident is None:continue
 if kind=='codex':
  result={}
  if op=='thread/start':result={'thread':{'id':session},'model':a['model'],'modelProvider':a['modelProvider']}
  elif op=='turn/start':result={'turn':{'id':'utf8-turn'}}
  emit({'id':ident,'result':result})
  if op=='turn/start':
   text=a['input'][0]['text']
   emit({'method':'item/completed','params':{'threadId':session,'turnId':'utf8-turn','item':{'type':'agentMessage','text':hashlib.sha256(text.encode()).hexdigest()}}})
   emit({'method':'turn/completed','params':{'threadId':session,'turn':{'id':'utf8-turn','status':'completed'}}})
 else:
  data={}
  if op=='get_state':data={'sessionId':session,'model':{'provider':'opencode-go','id':'deepseek-v4.1-flash'},'dumpTools':[]}
  elif op=='get_session_stats':data={'tokens':{'input':prompts,'output':prompts,'cacheRead':0,'cacheWrite':0,'reasoning':0,'total':2*prompts},'cost':0}
  emit({'type':'response','id':ident,'command':op,'success':True,'data':data})
  if op=='prompt':
   prompts+=1
   text=a['message'].removeprefix('Engagement assignment (host):\n')
   emit({'type':'message_end','message':{'role':'assistant','content':[{'type':'text','text':hashlib.sha256(text.encode()).hexdigest()}]}})
   emit({'type':'prompt_result','id':ident,'status':'completed','sessionSettled':True})
'''


def controlled(root, kind, prompt):
    peer = root / (kind + '-peer'); peer.write_text(PEER.replace('KIND', repr(kind))); peer.chmod(0o700)
    runtime = importlib.import_module('native_runtime_' + kind).Runtime(
        profile(root, kind, peer), root / (kind + '-state'), root, dispatch_guard=nullcontext)
    try:
        runtime.fresh(); runtime.invoke(prompt, 'unicode-roundtrip')
        events = []; deadline = time.monotonic() + 5
        while runtime.active and time.monotonic() < deadline: events.extend(runtime.observe(.1))
        require(not runtime.active, 'controlled runtime did not finish')
        require(any(row.get('text') == hashlib.sha256(prompt.encode()).hexdigest() for row in events), 'native prompt text changed')
    finally: runtime.close()
    return {'runtime': kind, 'prompt_bytes': len(prompt.encode()), 'text_sha256': hashlib.sha256(prompt.encode()).hexdigest()}


def pipe(root, prompt):
    script = 'import sys,json,hashlib\nfor line in sys.stdin:\n x=json.loads(line);print(json.dumps({"id":x["id"],"result":{"bytes":len(line.encode()),"sha256":hashlib.sha256(x["params"]["text"].encode()).hexdigest()}}),flush=True)'
    transport = Transport([sys.executable, '-c', script], dict(os.environ), str(root), lambda event: None)
    try:
        result = transport.request('echo', {'text': prompt})
        require(result['sha256'] == hashlib.sha256(prompt.encode()).hexdigest(), 'wire text changed')
        require(result['bytes'] < MAX_FRAME, 'wire cap exceeded')
        try: transport.send({'text': '界' * MAX_FRAME}); raise AssertionError('oversized UTF-8 wire accepted')
        except RuntimeError as error: require(str(error) == 'native_request_oversized', 'wrong size rejection')
    finally: transport.close()
    return result


def payloads():
    text = 'é' * (3 * 1024 * 1024)
    require(public({'text': text})['text'] == text, 'public payload changed')
    response = {'text': 'é' * (2 * 1024 * 1024)}
    pending = PendingTool(operation=HostOperation(lambda: response, lambda: None))
    require(pending.ready.wait(5), 'asynchronous result stalled')
    require(not pending.unknown and pending.response == response, 'valid UTF-8 result rejected')
    try: public({'text': 'Authorization: ' + 'Bearer ' + 'fake-secret-value'}); raise AssertionError('secret accepted')
    except RuntimeError: pass
    return {'public_text_bytes': len(text.encode()), 'pending_text_bytes': len(response['text'].encode())}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path); args = parser.parse_args()
    prompt = ('é🧪日本語' * 30000) + ('"\n\\' * 1000)
    require(len(prompt.encode()) < MAX_FRAME // 2, 'fixture prompt violates admission limit')
    checks = []
    with tempfile.TemporaryDirectory(prefix='native-utf8-wire-') as directory:
        root = Path(directory).resolve()
        for name, run in [('wire_roundtrip_and_cap', lambda: pipe(root, prompt)),
                          ('codex_roundtrip', lambda: controlled(root, 'codex', prompt)),
                          ('omp_roundtrip', lambda: controlled(root, 'omp', prompt)),
                          ('public_and_pending_utf8_bytes', payloads)]:
            try: checks.append({'check': name, 'status': 'passed', 'result': run()})
            except Exception as error: checks.append({'check': name, 'status': 'failed', 'error': str(error)})
    result = {'status': 'passed' if all(row['status'] == 'passed' for row in checks) else 'failed',
              'evidence': 'controlled_protocol_subprocesses', 'provider_calls': 0, 'checks': checks}
    encoded = json.dumps(result, indent=2) + '\n'
    if args.output: args.output.write_text(encoded)
    print(encoded, end=''); return 0 if result['status'] == 'passed' else 1

if __name__ == '__main__': raise SystemExit(main())
