#!/usr/bin/env python3
"""Cumulative cost validation through an inert OMP protocol subprocess."""
from contextlib import nullcontext
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'tools'), str(Path(__file__).resolve().parent)]
from check_native_runtime_adapters import profile, require
from native_runtime_omp import Runtime
from native_runtime_transport import RuntimeError

PEER = '''#!/usr/bin/env python3
import json,sys
if '--version' in sys.argv:print('omp/18.20.0');sys.exit()
count=0
costs=COSTS
def emit(value):print(json.dumps(value),flush=True)
emit({'type':'ready','protocolVersion':1,'supportedProtocolVersions':[1,2]})
for line in sys.stdin:
 request=json.loads(line);op=request.get('type');ident=request.get('id')
 if ident is None:continue
 data={}
 if op=='get_state':data={'sessionId':'cost-session','isSettled':True,'isStreaming':False,'model':{'provider':'opencode-go','id':'deepseek-v4.1-flash'},'dumpTools':[]}
 elif op=='get_session_stats':data={'tokens':{'input':count,'output':count,'cacheRead':0,'cacheWrite':0,'reasoning':0,'total':2*count},'cost':costs[count]}
 emit({'id':ident,'type':'response','command':op,'success':True,'data':data})
 if op=='prompt':
  count=1
  emit({'type':'prompt_result','id':ident,'agentInvoked':True,'status':'completed','sessionSettled':True})
'''


def scenario(root, before, after, expected):
    peer = root / 'omp-peer'
    peer.write_text(PEER.replace('COSTS', repr([before, after])))
    peer.chmod(0o700)
    runtime = Runtime(profile(root, 'omp', peer), root / 'state', root, dispatch_guard=nullcontext)
    events, error = [], None
    try:
        runtime.fresh()
        runtime.invoke('Harmless accounting fixture.', 'cost-check')
        deadline = time.monotonic() + 5
        try:
            while runtime.active and time.monotonic() < deadline:
                events.extend(runtime.observe(.1))
        except RuntimeError as caught:
            error = str(caught)
        if expected == 'refused':
            require(error == 'native_usage_invalid', 'invalid cumulative cost accepted')
            require(runtime.usage is None, 'invalid cost published')
            require(not any(e['event'] == 'completed' for e in events), 'invalid cost completed invocation')
        else:
            require(error is None and not runtime.active, 'valid or unavailable cost rejected')
            require(runtime.usage['estimated_cost'] == expected, 'wrong cost delta')
            require(runtime.usage['monetary_spend'] is None, 'estimate treated as billed cost')
        return {'error': error, 'estimated_cost': None if runtime.usage is None else runtime.usage['estimated_cost']}
    finally:
        runtime.close()


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    cases = [('negative_before', -1, 0, 'refused'), ('both_negative', -2, -1, 'refused'),
             ('negative_after', 0, -1, 'refused'), ('rollback', 2, 1, 'refused'),
             ('valid', .25, .5, .25), ('zero', 0, 0, 0), ('unavailable', None, None, None)]
    results = []
    with tempfile.TemporaryDirectory(prefix='omp-cost-baseline-') as tmp:
        for name, before, after, expected in cases:
            root = Path(tmp).resolve() / name; root.mkdir()
            try:
                result = scenario(root, before, after, expected)
                results.append({'case': name, 'status': 'passed', **result})
            except Exception as error:
                results.append({'case': name, 'status': 'failed', 'error': str(error)})
    report = {'status': 'passed' if all(r['status'] == 'passed' for r in results) else 'failed',
              'classification': 'controlled_omp_protocol_subprocess', 'provider_calls': 0,
              'native_runtime_executed': False, 'checks': results,
              'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in [Path(__file__).resolve(), ROOT / 'tools/native_runtime_omp.py']}}
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return report['status'] != 'passed'


if __name__ == '__main__':
    raise SystemExit(main())
