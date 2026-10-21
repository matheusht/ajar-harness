#!/usr/bin/env python3
"""Owned startup-timeout/partial-start safety E2E, no native/model call."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socketserver
import sqlite3
import subprocess
import sys
import tempfile
import threading
import uuid

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from native_run import NativeRun
from producer_stop import binding


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--partial-failure',action='store_true');args=p.parse_args()
    out=args.output.resolve();out.mkdir(mode=0o700,parents=True,exist_ok=False);nonce=uuid.uuid4().hex;resources=[];native=server=None
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    files=[Path(__file__).resolve(),HERE/'native_run.py',HERE/'_native_stop_owner.py',HERE/'producer_stop.py',HERE/'DUAL-LOSS-STOP-OWNER-CHECKS.md',HERE.parent/'v2_connect.py']
    d={'classification':'owned startup safety E2E; partial T05','provider_calls':0,'native_calls':0,'checks':[],'cleanup':[], 'source_sha256':{f.name:sha(f) for f in files}}
    (out/'source').mkdir()
    for f in files:shutil.copyfile(f,out/'source'/f.name)
    def check(name,ok):
        d['checks'].append({'check':name,'passed':bool(ok)})
        if not ok:raise RuntimeError(name)
    def run(*cmd):
        r=subprocess.run(cmd,capture_output=True,text=True,timeout=20)
        if r.returncode:raise RuntimeError(r.stderr[:200])
        return r.stdout.strip()
    class Sink(socketserver.BaseRequestHandler):
        def handle(self):pass
    try:
        with tempfile.TemporaryDirectory(prefix='native-startup-') as temp:
            root=Path(temp);workspace=root/'workspace';workspace.mkdir();cap=root/'cap';cap.write_text('local_'+uuid.uuid4().hex);cap.chmod(0o600)
            network=run('docker','network','create','--internal','--label','io.lrh.startup='+nonce,'startup-'+nonce[:12]);resources.append(('network',network))
            producers=[]
            for i in range(2):
                cid=run('docker','container','create','--pull','never','--network',network,'--read-only','--restart','no',
                    '--label','io.lrh.startup='+nonce,'--label','io.llm-redteam-harness.runtime=docker-session-v1',
                    '--label','io.llm-redteam-harness.session-nonce='+nonce,'--cap-drop','ALL',
                    '--entrypoint','sh','ghcr.io/anomalyco/opencode@sha256:2fc782d346b0670c43378557cf8a2a9926a1f3d28e596180e7b21a0736d8cb7d','-c','exec sleep 120')
                resources.append(('container',cid));producers.append({'id':cid,'binding':binding(json.loads(run('docker','container','inspect',cid))[0])})
            manifest=root/'manifest';manifest.write_text(json.dumps({'version':1,'nonce':nonce,'producers':producers}));manifest.chmod(0o600)
            server=socketserver.ThreadingTCPServer(('127.0.0.1',0),Sink);server.daemon_threads=True
            threading.Thread(target=server.serve_forever,daemon=True).start()
            proxy_args=['--state-dir',str(out/'provider'),'--capability-file',str(cap),'--max-connections','4',
                '--max-bytes','1048576','--duration','120','--dummy-port',str(server.server_address[1])]
            if args.partial_failure:proxy_args+=['--test-start-failure-after','1','--test-pause-failure-id',producers[0]['id'],'--test-kill-failure-id',producers[0]['id']]
            else:proxy_args+=['--test-startup-delay','1']
            native=NativeRun(manifest,out/'run',120,proxy_args)
            try:native.start(timeout_seconds=20 if args.partial_failure else .05);failed=False
            except RuntimeError as error:failed=True;d['startup_error']=str(error)
            check('startup fails explicitly',failed)
            d['close_result']=native.close();d['child_pid']=native.process.pid
            states=[json.loads(run('docker','container','inspect',q['id']))[0]['State'] for q in producers];d['producer_states']=states
            check('exact child exited',native.process.poll() is not None)
            check('never publishes ordered stop on startup failure',not (out/'run/REVOKED').exists())
            if args.partial_failure:
                check('partial-start unsafe state retained',(out/'run/UNSAFE').exists() and states[0]['Running'] and not states[1]['Running'] and d['close_result']['status']=='unsafe')
                with sqlite3.connect(out/'provider/tunnel.sqlite3') as db:events=db.execute('SELECT kind FROM events').fetchall()
                check('unsafe startup closes provider admission and records outcome',(out/'provider/REVOKED').exists() and ('provider_shutdown_unsafe',) in events)
            else:
                check('pre-ready timeout cannot activate producers',all(not s['Running'] for s in states) and (out/'run/STOP_REQUEST').exists() and not (out/'run/READY').exists())
            d['status']='startup_failure_closed_partial_T05'
    except Exception as error:d['status']='failed_or_unavailable';d['error']=type(error).__name__+': '+str(error)
    finally:
        if native:
            try:native.close()
            except Exception as error:d.setdefault('cleanup_errors',[]).append(str(error))
        for kind,identifier in reversed(resources):
            try:
                info=json.loads(run('docker',kind,'inspect',identifier))[0];labels=info['Config']['Labels'] if kind=='container' else info['Labels']
                if labels.get('io.lrh.startup')!=nonce:raise RuntimeError('ownership mismatch')
                run('docker',kind,'rm',*(['--force','--volumes'] if kind=='container' else []),identifier)
                r=subprocess.run(['docker',kind,'inspect',identifier],capture_output=True,text=True,timeout=10)
                d['cleanup'].append({'kind':kind,'id':identifier,'absent':r.returncode!=0 and ('No such' in r.stderr or 'not found' in r.stderr)})
            except Exception as error:d.setdefault('cleanup_errors',[]).append(str(error))
        if server:server.shutdown();server.server_close()
        d['cleanup_complete']=not d.get('cleanup_errors') and len(d['cleanup'])==len(resources) and all(x['absent'] for x in d['cleanup'])
        d['source_pins_stable']=all(sha(f)==d['source_sha256'][f.name] for f in files)
        (out/'result.json').write_text(json.dumps(d,indent=2).replace(str(Path.home()),'<HOME>')+'\n')
    print(json.dumps({k:d.get(k) for k in ('status','cleanup_complete','source_pins_stable')}))
    return 0 if d['status']!='failed_or_unavailable' and d['cleanup_complete'] and d['source_pins_stable'] else 1


if __name__=='__main__':raise SystemExit(main())
