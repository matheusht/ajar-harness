#!/usr/bin/env python3
"""Owned dual SIGKILL after the first sealed producer starts, before READY."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import signal
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import uuid

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from producer_stop import binding

IMAGE='ghcr.io/anomalyco/opencode@sha256:2fc782d346b0670c43378557cf8a2a9926a1f3d28e596180e7b21a0736d8cb7d'


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--inflight-start',action='store_true');args=ap.parse_args()
    out=args.output.resolve();out.mkdir(mode=0o700,parents=True,exist_ok=False)
    sources=[Path(__file__).resolve(),HERE/'DUAL-LOSS-STOP-OWNER-CHECKS.md',HERE/'native_run.py',HERE/'_native_stop_owner.py',HERE/'producer_stop.py',HERE.parent/'v2_connect.py',HERE.parents[2]/'tools/docker_session_runtime.py']
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    d={'classification':'owned partial-start dual-loss E2E; partial T05','inflight_start':args.inflight_start,'provider_calls':0,'native_calls':0,
       'checks':[],'resources':[],'cleanup':[],'source_sha256':{p.name:sha(p) for p in sources}}
    (out/'source').mkdir()
    for p in sources:shutil.copyfile(p,out/'source'/p.name)
    nonce=uuid.uuid4().hex;launcher=server=None;child=stop_owner=None
    def save():
        (out/'result.json').write_text(json.dumps(d,indent=2).replace(str(Path.home()),'<HOME>')+'\n')
    def check(name,ok):
        d['checks'].append({'check':name,'passed':bool(ok)});save()
        if not ok:raise RuntimeError(name)
    def run(*argv):
        r=subprocess.run(argv,capture_output=True,text=True,timeout=20)
        if r.returncode:raise RuntimeError(r.stderr[:300])
        return r.stdout.strip()
    def inspect(kind,identifier):return json.loads(run('docker',kind,'inspect',identifier))[0]
    def wait(predicate,seconds=10):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            if predicate():return True
            time.sleep(.02)
        return False
    def child_of(pid):
        r=subprocess.run(['pgrep','-P',str(pid)],capture_output=True,text=True,timeout=2)
        return int(r.stdout.splitlines()[0]) if r.returncode==0 and len(r.stdout.splitlines())==1 else None
    def absent(pid):
        try:os.kill(pid,0);return False
        except ProcessLookupError:return True
    class Sink(socketserver.BaseRequestHandler):
        def handle(self):pass
    try:
        with tempfile.TemporaryDirectory(prefix='native-start-loss-') as temporary:
            root=Path(temporary);workspace=root/'workspace';workspace.mkdir();hooks=root/'hooks';hooks.mkdir(mode=0o700)
            research=workspace/'research.txt';research.write_text('INERT retained research\n');research_hash=sha(research)
            cap=root/'cap';cap.write_text('local_'+uuid.uuid4().hex);cap.chmod(0o600)
            network=run('docker','network','create','--internal','--label','io.lrh.start-loss='+nonce,'start-loss-'+nonce[:12])
            d['resources'].append({'kind':'network','id':network})
            producers=[]
            for _ in range(2):
                identifier=run('docker','container','create','--pull','never','--network',network,'--read-only','--restart','no',
                    '--label','io.lrh.start-loss='+nonce,'--label','io.llm-redteam-harness.runtime=docker-session-v1',
                    '--label','io.llm-redteam-harness.session-nonce='+nonce,'--cap-drop','ALL','--security-opt','no-new-privileges=true',
                    '--mount',f'type=bind,src={workspace},dst=/workspace','--entrypoint','sh',IMAGE,'-c','exec sleep 120')
                d['resources'].append({'kind':'container','id':identifier})
                producers.append({'id':identifier,'binding':binding(inspect('container',identifier))})
            manifest=root/'manifest';manifest.write_text(json.dumps({'version':1,'nonce':nonce,'producers':producers}));manifest.chmod(0o600)
            server=socketserver.ThreadingTCPServer(('127.0.0.1',0),Sink);server.daemon_threads=True
            threading.Thread(target=server.serve_forever,daemon=True).start()
            env=os.environ.copy()
            if args.inflight_start:
                wrapper=root/'bin';wrapper.mkdir(mode=0o700)
                real_docker=shutil.which('docker')
                if not real_docker:raise RuntimeError('docker_unavailable')
                script=wrapper/'docker'
                script.write_text('#!/usr/bin/env python3\nimport os,sys,time\nfrom pathlib import Path\n'
                    f'if sys.argv[1:4]==["container","start",{producers[0]["id"]!r}]:\n'
                    f'    Path({str(hooks/"CLI_READY")!r}).touch()\n'
                    f'    while not Path({str(hooks/"RELEASE")!r}).exists():time.sleep(.01)\n'
                    f'os.execv({real_docker!r},[{real_docker!r},*sys.argv[1:]])\n')
                script.chmod(0o700)
                env['PATH']=str(wrapper)+os.pathsep+env.get('PATH','')
            state=out/'run';argv=[sys.executable,str(HERE/'native_run.py'),'--manifest',str(manifest),'--state-dir',str(state),'--timeout','120','--',
                  '--state-dir',str(out/'provider'),'--capability-file',str(cap),'--max-connections','4','--max-bytes','1048576',
                  '--duration','120','--dummy-port',str(server.server_address[1])]
            if not args.inflight_start:argv+=['--test-start-hold-dir',str(hooks)]
            launcher=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True,env=env)
            d['launcher_pid']=launcher.pid
            if args.inflight_start:
                check('Docker start CLI launched before READY',wait(lambda:(hooks/'CLI_READY').exists()) and
                      all(not inspect('container',p['id'])['State']['Running'] for p in producers) and
                      not (state/'READY').exists() and not select.select([launcher.stdout],[],[],0)[0])
            else:
                check('first producer started and held before READY',wait(lambda:(hooks/'STARTED').exists()) and
                      inspect('container',producers[0]['id'])['State']['Running'] and not inspect('container',producers[1]['id'])['State']['Running'] and
                      not (state/'READY').exists() and not select.select([launcher.stdout],[],[],0)[0])
            child=child_of(launcher.pid)
            armed=[json.loads(line) for line in (state/'stop-owner.jsonl').read_text().splitlines() if json.loads(line)['kind']=='stop_owner_armed']
            stop_owner=armed[0]['data']['pid'] if len(armed)==1 else None
            check('independent owner armed during partial start',child is not None and stop_owner is not None and not absent(stop_owner))
            d['connect_pid']=child;d['stop_owner_pid']=stop_owner;d['fault_monotonic']=time.monotonic()
            os.kill(launcher.pid,signal.SIGSTOP);os.kill(child,signal.SIGSTOP)
            os.kill(launcher.pid,signal.SIGKILL);os.kill(child,signal.SIGKILL)
            launcher.wait(timeout=5)
            check('both host processes absent',wait(lambda:absent(child)))
            if args.inflight_start:
                time.sleep(.2)
                check('owner waits for in-flight Docker start before any stop marker',(state/'START_IN_FLIGHT').exists() and
                      not any((state/name).exists() for name in ('STOP_REQUEST','STOPPING','REVOKED','UNSAFE')))
                (hooks/'RELEASE').touch()
            check('terminal result bounded',wait(lambda:(state/'REVOKED').exists() or (state/'UNSAFE').exists()))
            d['producer_states']={p['id']:inspect('container',p['id'])['State'] for p in producers}
            d['markers']={name:(state/name).exists() for name in ('READY','START_IN_FLIGHT','STOP_REQUEST','STOPPING','REVOKED','UNSAFE')}
            stopped=all(not s['Running'] or s['Paused'] for s in d['producer_states'].values())
            if args.inflight_start:
                check('uncertain in-flight start stays UNSAFE despite exact freeze',not d['markers']['READY'] and
                      d['markers']['START_IN_FLIGHT'] and d['markers']['STOPPING'] and d['markers']['UNSAFE'] and
                      not d['markers']['REVOKED'] and stopped)
            else:
                check('partial-start exact set verified before REVOKED',not d['markers']['READY'] and d['markers']['STOPPING'] and
                      d['markers']['REVOKED'] and not d['markers']['UNSAFE'] and stopped and
                      json.loads((state/'REVOKED').read_text())['producers_verified_stopped'] is True)
            check('stop owner exits after takeover',wait(lambda:absent(stop_owner)))
            check('research retained unchanged',sha(research)==research_hash)
            shutil.copyfile(research,out/'research.txt')
            d['status']='inflight_start_dual_loss_unsafe_partial_T05' if args.inflight_start else 'partial_start_dual_loss_pass_partial_T05'
    except Exception as error:d['status']='failed_or_unavailable';d['error']=type(error).__name__+': '+str(error)
    finally:
        if 'hooks' in locals() and hooks.exists():(hooks/'RELEASE').touch()
        if launcher and launcher.poll() is None:launcher.kill();launcher.wait(timeout=5)
        for pid in (child,stop_owner):
            if pid and not absent(pid):os.kill(pid,signal.SIGKILL);wait(lambda:absent(pid))
        for item in reversed(d['resources']):
            try:
                info=inspect(item['kind'],item['id']);labels=info['Config']['Labels'] if item['kind']=='container' else info['Labels']
                if labels.get('io.lrh.start-loss')!=nonce:raise RuntimeError('cleanup ownership mismatch')
                run('docker',item['kind'],'rm',*(['--force','--volumes'] if item['kind']=='container' else []),item['id'])
                r=subprocess.run(['docker',item['kind'],'inspect',item['id']],capture_output=True,text=True,timeout=10)
                d['cleanup'].append({**item,'absent':r.returncode!=0 and ('No such' in r.stderr or 'not found' in r.stderr)})
            except Exception as error:d.setdefault('cleanup_errors',[]).append(str(error))
        if server:server.shutdown();server.server_close()
        d['cleanup_complete']=not d.get('cleanup_errors') and len(d['cleanup'])==len(d['resources']) and all(r['absent'] for r in d['cleanup']) and (not child or absent(child)) and (not stop_owner or absent(stop_owner))
        d['source_pins_stable']=all(sha(p)==d['source_sha256'][p.name] for p in sources);save()
    print(json.dumps({k:d.get(k) for k in ('status','cleanup_complete','source_pins_stable')}))
    return 0 if d['status']!='failed_or_unavailable' and d['cleanup_complete'] and d['source_pins_stable'] else 1


if __name__=='__main__':raise SystemExit(main())
