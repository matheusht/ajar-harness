#!/usr/bin/env python3
"""Deterministic CONNECT pre-send stop and unsafe reopen, owned loopback only."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import socket
import socketserver
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import uuid

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from native_run import NativeRun,request_stop
from producer_stop import binding


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--unsafe-reopen',action='store_true');args=ap.parse_args()
    out=args.output.resolve();out.mkdir(mode=0o700,parents=True,exist_ok=False)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    sources=[HERE/'connect_send_race.py',HERE/'native_run.py',HERE/'_native_stop_owner.py',HERE/'producer_stop.py',HERE/'DUAL-LOSS-STOP-OWNER-CHECKS.md',HERE.parent/'v2_connect.py']
    report={'classification':'owned CONNECT final-send/unsafe reopen E2E; partial T05','provider_calls':0,'native_calls':0,
            'source_sha256':{p.name:sha(p) for p in sources},'checks':[],'commands':[],'cleanup':[]}
    (out/'source').mkdir()
    for p in sources:shutil.copyfile(p,out/'source'/p.name)
    nonce=uuid.uuid4().hex;capability='local_'+uuid.uuid4().hex
    auth=base64.b64encode(('run:'+capability).encode()).decode();native=None;container=network=connection=None
    server=thread=None;received=[];receiver_done=threading.Event()
    def save():
        text=json.dumps(report,indent=2).replace(capability,'[LOCAL-CAPABILITY]').replace(auth,'[LOCAL-CAPABILITY]').replace(str(Path.home()),'<HOME>')
        (out/'result.json').write_text(text+'\n')
    def check(name,ok):
        report['checks'].append({'check':name,'passed':bool(ok)});save()
        if not ok:raise RuntimeError(name)
    def run(*argv):
        r=subprocess.run(argv,capture_output=True,text=True,timeout=20)
        report['commands'].append({'argv':list(argv),'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr});save()
        if r.returncode:raise RuntimeError(r.stderr[:300])
        return r.stdout.strip()
    def wait(test):
        end=time.monotonic()+30
        while time.monotonic()<end:
            if test():return True
            time.sleep(.01)
        return False
    class Sink(socketserver.BaseRequestHandler):
        def handle(self):
            try:
                while data:=self.request.recv(1024):
                    received.append({'hex':data.hex(),'monotonic':time.monotonic()})
                    with (out/'upstream.jsonl').open('a') as f:f.write(json.dumps(received[-1])+'\n');f.flush();os.fsync(f.fileno())
                    self.request.sendall(b'ACK')
            except OSError:pass
            finally:receiver_done.set()
    try:
        with tempfile.TemporaryDirectory(prefix='owned-send-race-') as temporary:
            root=Path(temporary).resolve();workspace=root/'workspace';workspace.mkdir();(workspace/'research.txt').write_text('INERT retained research\n')
            cap=root/'capability';cap.write_text(capability);cap.chmod(0o600)
            hooks=root/'hooks';hooks.mkdir(mode=0o700)
            server=socketserver.ThreadingTCPServer(('127.0.0.1',0),Sink);server.daemon_threads=True
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            network=run('docker','network','create','--internal','--label','io.lrh.send-race='+nonce,'send-race-'+nonce[:12])
            container=run('docker','container','create','--pull','never','--network',network,'--read-only','--restart','no',
                '--label','io.lrh.send-race='+nonce,'--label','io.llm-redteam-harness.runtime=docker-session-v1',
                '--label','io.llm-redteam-harness.session-nonce='+nonce,'--cap-drop','ALL','--security-opt','no-new-privileges=true',
                '--mount',f'type=bind,src={workspace},dst=/workspace', '--entrypoint','sh',
                'ghcr.io/anomalyco/opencode@sha256:2fc782d346b0670c43378557cf8a2a9926a1f3d28e596180e7b21a0736d8cb7d','-c','exec sleep 120')
            info=json.loads(run('docker','container','inspect',container))[0]
            manifest=root/'manifest.json';manifest.write_text(json.dumps({'version':1,'nonce':nonce,'producers':[{'id':container,'binding':binding(info),'role':'owned-inert-producer'}]}));manifest.chmod(0o600)
            provider=out/'provider';state=out/'native-run';proxy_args=['--state-dir',str(provider),'--capability-file',str(cap),
                '--max-connections','16','--max-bytes','1048576','--duration','120','--dummy-port',str(server.server_address[1])]
            if args.unsafe_reopen:proxy_args+=['--test-pause-failure-id',container,'--test-kill-failure-id',container]
            else:proxy_args+=['--test-send-window',str(hooks)]
            native=NativeRun(manifest,state,120,proxy_args);ready=native.start();report['native_run']=ready
            connection=socket.create_connection(('127.0.0.1',ready['proxy_info']['port']),timeout=3)
            connection.sendall(('CONNECT opencode.ai:443 HTTP/1.1\r\nHost: opencode.ai:443\r\nProxy-Authorization: Basic '+auth+'\r\n\r\n').encode())
            check('actual CONNECT admitted',b' 200 ' in connection.recv(4096))
            connection.sendall(b'before');check('independent upstream positive',connection.recv(3)==b'ACK')
            if not args.unsafe_reopen:
                (hooks/'ARM').touch();connection.sendall(b'charged-but-not-dispatched')
                check('upload held after real quota charge',wait(lambda:(hooks/'CHARGED').exists()))
            request_stop(state,'operator_stop')
            terminal='UNSAFE' if args.unsafe_reopen else 'REVOKED'
            check('actual close API reaches expected outcome',wait(lambda:(state/terminal).exists()))
            report['producer_state_at_stop']=json.loads(run('docker','container','inspect',container))[0]['State']
            if args.unsafe_reopen:
                check('unsafe target never gains ordered marker',not (state/'REVOKED').exists() and report['producer_state_at_stop']['Running'])
            else:
                check('producer paused before verified marker',report['producer_state_at_stop']['Paused'])
                check('socket teardown delayed independently',wait(lambda:(hooks/'STOP_PUBLISHED').exists()) and native.process.poll() is None)
                (hooks/'RELEASE_SEND').touch();check('held sender resumes',wait(lambda:(hooks/'SEND_FINISHED').exists()))
                report['held_send_outcome']=json.loads((hooks/'SEND_FINISHED').read_text())
                (hooks/'RELEASE_CLOSE').touch()
            native.process.wait(timeout=10);connection.close();connection=None
            check('independent upstream fully drained',wait(receiver_done.is_set))
            report['upstream_received']=received
            with sqlite3.connect('file:'+str(provider/'tunnel.sqlite3')+'?mode=ro',uri=True) as db:
                report['provider_ledger']={'pool':db.execute('SELECT config,created,bytes FROM pool').fetchall(),
                    'tunnels':db.execute('SELECT id,phase,uploaded,downloaded,reason FROM tunnels').fetchall(),
                    'events':db.execute('SELECT id,kind,data FROM events').fetchall()}
            if args.unsafe_reopen:
                check('unsafe closure persisted',any(e[1]=='provider_shutdown_unsafe' for e in report['provider_ledger']['events']))
                before=sha(provider/'tunnel.sqlite3');report['provider_before_reopen_sha256']=before
                clone=out/'provider-copy-without-marker';shutil.copytree(provider,clone);(clone/'REVOKED').unlink()
                check('provider-only marker withheld on exact copy',sha(clone/'tunnel.sqlite3')==before)
                for supplied in (False,True):
                    reopen_args=proxy_args[:]
                    for flag in ('--test-pause-failure-id','--test-kill-failure-id'):
                        if flag in reopen_args:
                            at=reopen_args.index(flag);del reopen_args[at:at+2]
                    command=[sys.executable,str(HERE.parent/'v2_connect.py'),*reopen_args]
                    command[command.index('--state-dir')+1]=str(clone)
                    if supplied:command+=['--producer-manifest',str(manifest),'--native-run-state',str(state),'--native-run-duration','120']
                    r=subprocess.run(command,capture_output=True,text=True,timeout=10)
                    report['commands'].append({'argv':command,'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
                    check('same-pool reopen refuses '+('terminal producer/run binding' if supplied else 'omitted run binding'),r.returncode!=0 and ('producer_must_be_created_stopped' if supplied else 'frozen_pool_mismatch') in r.stderr)
                check('unsafe original provider ledger unchanged by copy probes',sha(provider/'tunnel.sqlite3')==before)
            check('no unsent upload forwarded after verified stop',received and b''.join(bytes.fromhex(r['hex']) for r in received)==b'before')
            shutil.copyfile(workspace/'research.txt',out/'research.txt')
            report['status']='unsafe_reopen_denied_partial_T05' if args.unsafe_reopen else 'pre_send_stop_pass_partial_T05'
    except Exception as error:report['status']='failed_or_unavailable';report['error']=type(error).__name__+': '+str(error)
    finally:
        if 'hooks' in locals() and hooks.exists():
            (hooks/'RELEASE_SEND').touch();(hooks/'RELEASE_CLOSE').touch()
        if native:
            try:native.close()
            except Exception as error:report.setdefault('cleanup_errors',[]).append(str(error))
        if connection:connection.close()
        for kind,identifier in (('container',container),('network',network)):
            if identifier:
                try:
                    info=json.loads(run('docker',kind,'inspect',identifier))[0];labels=info['Config']['Labels'] if kind=='container' else info['Labels']
                    if labels.get('io.lrh.send-race')!=nonce:raise RuntimeError('cleanup ownership mismatch')
                    run('docker',kind,'rm',*(['--force','--volumes'] if kind=='container' else []),identifier)
                    r=subprocess.run(['docker',kind,'inspect',identifier],capture_output=True,text=True,timeout=10)
                    report['cleanup'].append({'kind':kind,'id':identifier,'absent':r.returncode!=0 and ('No such' in r.stderr or 'not found' in r.stderr)})
                except Exception as error:report.setdefault('cleanup_errors',[]).append(str(error))
        if server:server.shutdown();server.server_close()
        if thread:thread.join(timeout=2)
        report['cleanup_complete']=not report.get('cleanup_errors') and len(report['cleanup'])==2 and all(x['absent'] for x in report['cleanup']) and (not native or native.process.poll() is not None)
        report['source_pins_stable']=all(sha(p)==report['source_sha256'][p.name] for p in sources);save()
    print(json.dumps({k:report.get(k) for k in ('status','cleanup_complete','source_pins_stable')}))
    return 0 if report['status']!='failed_or_unavailable' and report['cleanup_complete'] and report['source_pins_stable'] else 1


if __name__=='__main__':raise SystemExit(main())
