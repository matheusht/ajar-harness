#!/usr/bin/env python3
"""Failure-first event-ordering checks through a native-protocol subprocess.

A duplicated usage/completion event must not add a charge; an old turn's start,
usage, and completion cannot complete a new invocation; a cumulative counter that
rolls back inside a turn must fail without replacing the last observed usage.
These are controlled wire peers, not live provider qualification.
"""
from contextlib import nullcontext
import argparse
import json
from pathlib import Path
import sys
import tempfile
import time
ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'tools'), str(Path(__file__).resolve().parent)]
from check_native_runtime_adapters import profile, require
from native_runtime_codex import Runtime
from native_runtime_transport import RuntimeError

PEER = r'''#!/usr/bin/env python3
import json,sys
if '--version' in sys.argv:print('codex-cli 0.166.0');sys.exit()
session='usage-events-session';turns=0
def emit(x):print(json.dumps(x),flush=True)
def usage(turn,total):emit({'method':'thread/tokenUsage/updated','params':{'threadId':session,'turnId':turn,'tokenUsage':{'total':{'inputTokens':total-1,'outputTokens':1,'totalTokens':total}}}})
def done(turn):emit({'method':'turn/completed','params':{'threadId':session,'turn':{'id':turn,'status':'completed'}}})
for line in sys.stdin:
 x=json.loads(line);op=x.get('method');a=x.get('params',{});ident=x.get('id')
 if ident is None:continue
 result={}
 if op=='thread/start':result={'thread':{'id':session},'model':a['model'],'modelProvider':a['modelProvider']}
 elif op=='turn/start':turns+=1;turn='turn-'+str(turns);result={'turn':{'id':turn}}
 emit({'id':ident,'result':result})
 if op=='turn/start':
  prompt=a['input'][0]['text']
  if prompt=='late':
   emit({'method':'turn/started','params':{'threadId':session,'turn':{'id':'turn-1'}}})
   usage('turn-1',800);done('turn-1')
   usage(turn,17);done(turn)
  else:
   usage(turn,8)
   if prompt=='rollback':usage(turn,4)
   elif prompt=='missing':emit({'method':'thread/tokenUsage/updated','params':{'threadId':session,'turnId':turn,'tokenUsage':{'total':{}}}})
   else:usage(turn,8)
   done(turn);done(turn)
'''


def scenario(root, name):
    peer = root / 'codex-peer'; peer.write_text(PEER); peer.chmod(0o700)
    runtime = Runtime(profile(root, 'codex', peer), root / 'state', root, dispatch_guard=nullcontext)
    try:
        runtime.fresh(); runtime.invoke('duplicates' if name == 'late' else name, 'first')
        events = []; error = None; deadline = time.monotonic() + 5
        try:
            while runtime.active and time.monotonic() < deadline: events.extend(runtime.observe(.1))
        except RuntimeError as caught: error = str(caught)
        if name in ('rollback', 'missing'):
            require(error == 'native_usage_invalid', 'invalid cumulative update accepted')
            require(runtime.usage['total_tokens'] == 8, 'last observed usage was erased')
            return {'refusal': error, 'last_total': runtime.usage['total_tokens']}
        require(not runtime.active, 'first invocation did not complete')
        require(len([row for row in events if row['event'] == 'usage']) == 1, 'duplicate usage emitted')
        require(len([row for row in events if row['event'] == 'completed']) == 1, 'duplicate completion emitted')
        if name == 'late':
            runtime.invoke('late', 'second'); events = []; deadline = time.monotonic() + 5
            while runtime.active and time.monotonic() < deadline: events.extend(runtime.observe(.1))
            require(not runtime.active and runtime.native_turn == 'turn-2', 'stale turn replaced current turn')
            require(runtime.usage['total_tokens'] == 9, 'prior turn usage charged to new invocation')
            require(len([row for row in events if row['event'] == 'completed']) == 1, 'late completion duplicated')
        return {'total': runtime.usage['total_tokens'], 'native_turn': runtime.native_turn}
    finally: runtime.close()


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path); args = parser.parse_args(); checks = []
    with tempfile.TemporaryDirectory(prefix='native-usage-events-') as directory:
        for name in ['duplicates', 'late', 'rollback', 'missing']:
            root = Path(directory).resolve() / name; root.mkdir()
            try: checks.append({'check': name, 'status': 'passed', 'result': scenario(root, name)})
            except Exception as error: checks.append({'check': name, 'status': 'failed', 'error': str(error)})
    result = {'status': 'passed' if all(row['status'] == 'passed' for row in checks) else 'failed',
              'evidence': 'controlled_protocol_subprocesses', 'provider_calls': 0, 'checks': checks}
    encoded = json.dumps(result, indent=2) + '\n'
    if args.output: args.output.write_text(encoded)
    print(encoded, end=''); return 0 if result['status'] == 'passed' else 1

if __name__ == '__main__': raise SystemExit(main())
