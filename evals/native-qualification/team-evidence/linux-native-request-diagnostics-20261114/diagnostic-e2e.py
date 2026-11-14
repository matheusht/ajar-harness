#!/usr/bin/env python3
"""Failure-first native diagnostic check through an actual inert JSONL process."""
import argparse, importlib.util, json, pathlib, sys, tempfile
p=argparse.ArgumentParser();p.add_argument('--source',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args()
sys.path.insert(0,str(a.source.resolve().parent));s=importlib.util.spec_from_file_location('fixture',a.source);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
cases=[('safe',{'error':{'code':-32600,'message':'fixture rejected signed configuration'}}),('sensitive',{'error':{'code':-32600,'message':'Authorization: Bearer diagnostic-private-canary'}}),('known_secret',{'error':{'code':-32600,'message':'diagnostic-known-private-canary'}}),('large',{'error':{'code':-32600,'message':'x'*10000}}),('success',{'result':{'ok':True}})]
result={'classification':'actual_inert_jsonl_process_only','checks':[]}
for name,reply in cases:
 observations=[]; transport=None
 try:
  cls=m.diagnostic_transport(observations,(b'diagnostic-known-private-canary',))
  script='import sys,json\nfor line in sys.stdin:\n q=json.loads(line);print(json.dumps(dict('+repr(reply)+',id=q["id"])),flush=True)\n'
  with tempfile.TemporaryDirectory() as directory:
   transport=cls([sys.executable,'-I','-S','-c',script],{},directory,lambda frame:None)
   failed=None
   try:value=transport.request('config/read',{'must_not_publish':'request-private-marker'})
   except Exception as error:failed=getattr(error,'code',type(error).__name__)
   if name=='success':assert value=={'ok':True} and not observations and failed is None
   else:
    assert failed=='native_request_rejected' and len(observations)==1
    assert observations[0]['operation']=='config/read'
    body=json.dumps(observations)
    assert 'request-private-marker' not in body and 'private-canary' not in body
    if name=='safe':assert 'fixture rejected signed configuration' in body
    if name in ('sensitive','known_secret'):assert observations[0]['error']=='[diagnostic redacted]'
    assert len(observations[0]['error'])<=2048
  result['checks'].append({'name':name,'passed':True})
 except Exception as error:result['checks'].append({'name':name,'passed':False,'error':type(error).__name__})
 finally:
  if transport:transport.close()
result['status']='passed' if all(x['passed'] for x in result['checks']) else 'failed'
a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));raise SystemExit(result['status']!='passed')
