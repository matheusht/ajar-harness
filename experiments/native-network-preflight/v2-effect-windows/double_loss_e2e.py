#!/usr/bin/env python3
"""Owned exact-producer dual/single SIGKILL stop E2E; no provider/native inference."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import select
import shutil
import signal
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
from producer_stop import binding

IMAGE='ghcr.io/anomalyco/opencode@sha256:2fc782d346b0670c43378557cf8a2a9926a1f3d28e596180e7b21a0736d8cb7d'
PHP='php@sha256:0d6ec82fde85307fd9c672527017fccf9bac55f254756f035e542f8c566b63c9'


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--fault',choices=('both','parent','child'),default='both');ap.add_argument('--stop-failure',action='store_true');ap.add_argument('--log-failure',action='store_true');ap.add_argument('--effect-before-ack',action='store_true');args=ap.parse_args()
    if (args.stop_failure or args.log_failure) and args.fault!='both':ap.error('failure arms require dual loss')
    if args.stop_failure and args.log_failure:ap.error('one failure arm at a time')
    if args.effect_before_ack and (args.fault!='both' or args.stop_failure or args.log_failure):ap.error('effect-before-ack requires plain dual loss')
    out=args.output.resolve();out.mkdir(mode=0o700,parents=True,exist_ok=False)
    managed=HERE.parents[2]/'evals/native-qualification/smoke/opencode_v2_managed_owned.py'
    files=[Path(__file__).resolve(),HERE/'DUAL-LOSS-STOP-OWNER-CHECKS.md',HERE/'POST-EFFECT-NO-ACK-CHECKS.md',HERE/'native_run.py',HERE/'_native_stop_owner.py',HERE/'producer_stop.py',HERE/'receiver.php',HERE.parent/'v2_connect.py',managed]
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    d={'classification':'owned effect-before-ack E2E; partial #161' if args.effect_before_ack else 'owned launcher/CONNECT loss E2E; partial T05',
       'fault':args.fault,'stop_failure':args.stop_failure,'log_failure':args.log_failure,'effect_before_ack':args.effect_before_ack,'provider_calls':0,'native_calls':0,'model_inference_requested':False,'checks':[],'resources':[],'cleanup':[],
       'source_sha256':{p.name:sha(p) for p in files},'target_boundary_acceptance':False}
    (out/'source').mkdir()
    for p in files:shutil.copyfile(p,out/'source'/p.name)
    nonce=uuid.uuid4().hex;owner=server=child=stop_owner=None;stderr_file=None
    def save():
        (out/'result.json').write_text(json.dumps(d,indent=2).replace(str(Path.home()),'<HOME>')+'\n')
    def check(name,ok):
        d['checks'].append({'check':name,'passed':bool(ok)});save()
        if not ok:raise RuntimeError(name)
    def run(*argv):
        r=subprocess.run(argv,capture_output=True,text=True,timeout=15)
        if r.returncode:raise RuntimeError(r.stderr[:300])
        return r.stdout.strip()
    def inspect(kind,identifier):return json.loads(run('docker',kind,'inspect',identifier))[0]
    def wait(predicate,seconds=5):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            if predicate():return True
            time.sleep(.02)
        return False
    def absent(pid):
        try:os.kill(pid,0);return False
        except ProcessLookupError:return True
    class Sink(socketserver.BaseRequestHandler):
        def handle(self):pass
    try:
        with tempfile.TemporaryDirectory(prefix='native-dual-loss-') as temporary:
            root=Path(temporary);workspace=root/'workspace';workspace.mkdir();receiver_state=root/'receiver';receiver_state.mkdir()
            research=workspace/'research.txt';research.write_text('INERT retained research\n');research_hash=sha(research)
            cap=root/'cap';cap.write_text('local_'+uuid.uuid4().hex);cap.chmod(0o600)
            network=run('docker','network','create','--internal','--label','io.lrh.dual-loss='+nonce,'dual-loss-'+nonce[:12])
            d['resources'].append({'kind':'network','id':network})
            common=['--pull','never','--network',network,'--read-only','--restart','no','--cap-drop','ALL',
                    '--security-opt','no-new-privileges=true','--tmpfs','/tmp:rw,nosuid,nodev,size=16m','--label','io.lrh.dual-loss='+nonce]
            receiver=run('docker','container','create',*common,'--user',f'{os.getuid()}:{os.getgid()}',
                '--mount',f'type=bind,src={receiver_state},dst=/state',
                '--mount',f'type=bind,src={HERE/"receiver.php"},dst=/fixture/receiver.php,readonly',
                '--entrypoint','php',PHP,'-S','0.0.0.0:8080','/fixture/receiver.php')
            d['resources'].append({'kind':'container','id':receiver});run('docker','container','start',receiver)
            d['receiver_start_state']=inspect('container',receiver)
            logs=subprocess.run(['docker','container','logs',receiver],capture_output=True,text=True,timeout=10)
            d['receiver_start_logs']={'stdout':logs.stdout,'stderr':logs.stderr};save()
            check('receiver stays running',d['receiver_start_state']['State']['Running'])
            def receiver_ip():return next(iter(inspect('container',receiver)['NetworkSettings']['Networks'].values()))['IPAddress']
            check('receiver address assigned',wait(lambda:bool(receiver_ip())))
            ip=receiver_ip()
            effect=f'http://{ip}:8080/effect/'
            effect_case='post-effect' if args.effect_before_ack else 'pre-dispatch'
            request='/bin/busybox wget -Y off -qO- --post-data= '+effect+effect_case
            acknowledgement=' > /workspace/ACK.tmp && mv /workspace/ACK.tmp /workspace/ACK' if args.effect_before_ack else ' > /workspace/ACK'
            command='touch /workspace/PENDING; while test ! -e /workspace/RELEASE; do sleep .02; done; '+request+acknowledgement+'; exec sleep 120'
            producer=run('docker','container','create',*common,
                '--label','io.llm-redteam-harness.runtime=docker-session-v1','--label','io.llm-redteam-harness.session-nonce='+nonce,
                '--mount',f'type=bind,src={workspace},dst=/workspace','--entrypoint','sh',IMAGE,'-c',command)
            d['resources'].append({'kind':'container','id':producer})
            second=run('docker','container','create',*common,
                '--label','io.llm-redteam-harness.runtime=docker-session-v1','--label','io.llm-redteam-harness.session-nonce='+nonce,
                '--mount',f'type=bind,src={workspace},dst=/workspace','--entrypoint','sh',IMAGE,'-c','exec sleep 120')
            d['resources'].append({'kind':'container','id':second})
            producers=[{'id':identifier,'binding':binding(inspect('container',identifier))} for identifier in (producer,second)]
            manifest=root/'manifest';manifest.write_text(json.dumps({'version':1,'nonce':nonce,'producers':producers}));manifest.chmod(0o600)
            server=socketserver.ThreadingTCPServer(('127.0.0.1',0),Sink);server.daemon_threads=True
            threading.Thread(target=server.serve_forever,daemon=True).start()
            state=out/'run';stderr_file=(out/'owner.stderr').open('w')
            argv=[sys.executable,str(HERE/'native_run.py'),'--manifest',str(manifest),'--state-dir',str(state),'--timeout','120','--',
                  '--state-dir',str(out/'provider'),'--capability-file',str(cap),'--max-connections','4','--max-bytes','1048576',
                  '--duration','120','--dummy-port',str(server.server_address[1])]
            if args.stop_failure:argv+=['--test-pause-failure-id',second,'--test-kill-failure-id',second]
            owner=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=stderr_file,text=True,start_new_session=True)
            d['owner_pid']=owner.pid
            check('actual launcher readiness bounded',bool(select.select([owner.stdout],[],[],20)[0]))
            ready=json.loads(owner.stdout.readline());child=ready['watcher_pid'];d['watcher_pid']=child
            stop_owner=ready['proxy_info']['stop_owner_pid'];d['stop_owner_pid']=stop_owner
            check('independent stop owner armed before readiness',stop_owner not in (owner.pid,child) and not absent(stop_owner))
            check('exact child parent binding',int(run('ps','-p',str(child),'-o','ppid='))==owner.pid)
            check('pending direct effect staged',wait(lambda:(workspace/'PENDING').exists()) and not (workspace/'RELEASE').exists())
            def rows():
                p=receiver_state/'effects.jsonl';return [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []
            positive=run('docker','exec',producer,'/bin/busybox','wget','-Y','off','-qO-','--post-data=',effect+'positive')
            check('independent receiver positive before loss',positive=='ACK:positive' and rows()==[{'case':'positive','effect':'inert_append'}])
            if args.effect_before_ack:
                (workspace/'RELEASE').touch()
                check('independent effect committed before host loss',wait(lambda:rows()==[
                    {'case':'positive','effect':'inert_append'}, {'case':'post-effect','effect':'inert_append'}]))
                check('effect reached before acknowledgement',not (workspace/'ACK').exists() and not (receiver_state/'response-attempted').exists())
                d['effect_before_fault']={'receiver_rows':rows(),'client_ack_present':(workspace/'ACK').exists(),
                                          'receiver_response_attempted':(receiver_state/'response-attempted').exists()}
            if args.log_failure:(state/'stop-owner.jsonl').chmod(0o000)
            d['fault_monotonic']=time.monotonic()
            if args.fault=='both':
                # Stop both first so neither can handle the other's loss.
                os.kill(owner.pid,signal.SIGSTOP);os.kill(child,signal.SIGSTOP)
                os.kill(owner.pid,signal.SIGKILL);os.kill(child,signal.SIGKILL)
            elif args.fault=='parent':os.kill(owner.pid,signal.SIGKILL)
            else:os.kill(child,signal.SIGKILL)
            owner.wait(timeout=15)
            check('both exact host processes absent',owner.poll() is not None and wait(lambda:absent(child)))
            check('terminal stop result bounded',wait(lambda:any((state/n).exists() for n in ('REVOKED','UNSAFE')),seconds=10))
            d['before_gate_release']={'monotonic':time.monotonic(),'producer_states':{identifier:inspect('container',identifier)['State'] for identifier in (producer,second)},
                'markers':{n:(state/n).exists() for n in ('STOP_REQUEST','STOPPING','REVOKED','UNSAFE')},'receiver_rows':rows()}
            spec=importlib.util.spec_from_file_location('managed_stop_proof_e2e',managed)
            managed_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(managed_module)
            def stop_proof(run_path=state,provider_path=out/'provider',inspect_item=None):
                return managed_module.managed_stop_readback(
                    run_path,provider_path,manifest,ready['manifest_sha256'],ready['ids'],
                    inspect_item or (lambda identifier:inspect('container',identifier)))
            proof=stop_proof();d['managed_stop_proof']=proof
            if args.stop_failure or args.log_failure:
                check('managed readback rejects unsafe owner outcome',not proof['run_verified'])
            else:
                check('managed readback accepts exact run freeze without provider event ordering',
                      proof['run_verified'] and proof['exact_producers_stopped'])
                with sqlite3.connect(out/'provider/tunnel.sqlite3') as db:
                    provider_frozen=db.execute("SELECT count(*) FROM events WHERE kind='producer_set_frozen'").fetchone()[0]
                d['provider_frozen_event_count']=provider_frozen
                if args.fault=='both':
                    check('dual-loss owner proof survives missing provider freeze event',provider_frozen==0)
                copied=root/'proof-tampered';shutil.copytree(state,copied)
                revoked_path=copied/'REVOKED';original=json.loads(revoked_path.read_text())
                (copied/'stop-owner.jsonl').unlink(missing_ok=True)
                check('run proof does not require owner event log',stop_proof(run_path=copied)['run_verified'])
                for name,mutation in (
                    ('false_verified',lambda record:record.update(producers_verified_stopped=False)),
                    ('wrong_digest',lambda record:record.update(manifest_sha256='0'*64)),
                    ('wrong_ids',lambda record:record.update(ids=list(reversed(ready['ids'])))),
                    ('wrong_order',lambda record:record.update(frozen_monotonic=record['monotonic']+1)),
                ):
                    altered=original.copy();mutation(altered)
                    revoked_path.write_text(json.dumps(altered)+'\n')
                    check('managed readback rejects '+name,not stop_proof(run_path=copied)['run_verified'])
                revoked_path.write_text(json.dumps(original)+'\n')
                (copied/'UNSAFE').write_text('{}\n')
                check('managed readback rejects conflicting unsafe marker',not stop_proof(run_path=copied)['run_verified'])
                (copied/'UNSAFE').unlink();revoked_path.unlink()
                check('managed readback rejects missing run revocation',not stop_proof(run_path=copied)['run_verified'])
                def runnable(identifier):
                    info=inspect('container',identifier)
                    if identifier==producer:info['State']={**info['State'],'Running':True,'Paused':False}
                    return info
                check('managed readback rejects runnable exact producer',
                      not stop_proof(inspect_item=runnable)['run_verified'])
                # The provider marker closes admission but is never the run freeze proof.
                provider_copy=root/'provider-proof';provider_copy.mkdir()
                check('managed readback keeps provider closure separate',
                      stop_proof(provider_path=provider_copy)['run_verified'] and
                      not stop_proof(provider_path=provider_copy)['provider_admission_closed'])
            if args.effect_before_ack:
                (receiver_state/'release-post-effect').touch();d['response_release_monotonic']=time.monotonic()
                response_marker=receiver_state/'response-attempted'
                check('receiver attempted held response after freeze',wait(lambda:response_marker.exists() and response_marker.read_text()=='after-release'))
                check('client still has no acknowledgement after freeze',not (workspace/'ACK').exists())
                d['after_response_release']={'receiver_marker':response_marker.read_text(),
                                             'client_ack_present':(workspace/'ACK').exists(),'receiver_rows':rows()}
            else:
                (workspace/'RELEASE').touch();d['gate_release_monotonic']=time.monotonic()
                wait(lambda:any(r['case']=='pre-dispatch' for r in rows()),seconds=2)
            fresh=subprocess.run(['docker','exec',second if args.stop_failure else producer,'/bin/busybox','wget','-Y','off','-qO-','--post-data=',effect+'pre-ack'],capture_output=True,text=True,timeout=5)
            d['fresh_attempt']={'returncode':fresh.returncode,'stdout':fresh.stdout,'stderr':fresh.stderr}
            d['receiver_rows']=rows();check('receiver survives dual loss',inspect('container',receiver)['State']['Running'])
            before=d['before_gate_release'];safe=all(not s['Running'] or s['Paused'] for s in before['producer_states'].values())
            revoked=json.loads((state/'REVOKED').read_text()) if before['markers']['REVOKED'] else {}
            stopping=json.loads((state/'STOPPING').read_text()) if before['markers']['STOPPING'] else {}
            expected_rows=[{'case':'positive','effect':'inert_append'}]
            if args.effect_before_ack:expected_rows.append({'case':'post-effect','effect':'inert_append'})
            d['target_boundary_acceptance']=safe and before['markers']['STOP_REQUEST'] and before['markers']['STOPPING'] and before['markers']['REVOKED'] and not before['markers']['UNSAFE'] and revoked.get('producers_verified_stopped') is True and stopping.get('monotonic',float('inf'))<=revoked.get('monotonic',float('-inf')) and rows()==expected_rows and fresh.returncode!=0
            if args.stop_failure:
                check('stop failure remains unsafe without false revocation',before['markers']['STOPPING'] and before['markers']['UNSAFE'] and not before['markers']['REVOKED'] and not safe and fresh.returncode==0 and any(r['case']=='pre-ack' for r in rows()))
            elif args.log_failure:
                check('log failure still freezes but keeps unsafe',safe and before['markers']['STOPPING'] and before['markers']['UNSAFE'] and
                      not before['markers']['REVOKED'] and all(r['case']=='positive' for r in rows()) and fresh.returncode!=0)
            elif args.effect_before_ack:
                check('verified stop preserves observed effect without ACK or duplicate',d['target_boundary_acceptance'] and not (workspace/'ACK').exists())
            else:check('verified exact stop blocks pending and fresh effects',d['target_boundary_acceptance'])
            check('stop owner exits after CONNECT loss',wait(lambda:absent(stop_owner),seconds=5))
            check('research retained unchanged',sha(research)==research_hash);shutil.copyfile(research,out/'research.txt')
            if (receiver_state/'effects.jsonl').exists():shutil.copyfile(receiver_state/'effects.jsonl',out/'effects.jsonl')
            if args.effect_before_ack:shutil.copyfile(receiver_state/'response-attempted',out/'response-attempted')
            d['status']='dual_loss_stop_failure_unsafe_partial_T05' if args.stop_failure else ('dual_loss_log_failure_unsafe_partial_T05' if args.log_failure else ('effect_before_ack_boundary_pass_partial_issue_161' if args.effect_before_ack else args.fault+'_loss_boundary_pass_partial_T05'))
    except Exception as error:d['status']='failed_or_unavailable';d['error']=type(error).__name__+': '+str(error)
    finally:
        if 'state' in locals() and (state/'stop-owner.jsonl').exists():(state/'stop-owner.jsonl').chmod(0o600)
        if owner and owner.poll() is None:owner.kill();owner.wait(timeout=5)
        if child and not absent(child):
            os.kill(child,signal.SIGKILL);wait(lambda:absent(child))
        if stop_owner and not absent(stop_owner):
            os.kill(stop_owner,signal.SIGKILL);wait(lambda:absent(stop_owner))
        if stderr_file:stderr_file.close()
        for r in reversed(d['resources']):
            try:
                info=inspect(r['kind'],r['id']);labels=info['Config']['Labels'] if r['kind']=='container' else info['Labels']
                if labels.get('io.lrh.dual-loss')!=nonce:raise RuntimeError('cleanup ownership mismatch')
                run('docker',r['kind'],'rm',*(['--force','--volumes'] if r['kind']=='container' else []),r['id'])
                q=subprocess.run(['docker',r['kind'],'inspect',r['id']],capture_output=True,text=True,timeout=10)
                d['cleanup'].append({**r,'absent':q.returncode!=0 and ('No such' in q.stderr or 'not found' in q.stderr)})
            except Exception as error:d.setdefault('cleanup_errors',[]).append(str(error))
        if server:server.shutdown();server.server_close()
        d['cleanup_complete']=not d.get('cleanup_errors') and len(d['cleanup'])==len(d['resources']) and all(r['absent'] for r in d['cleanup']) and (not owner or owner.poll() is not None) and (not child or absent(child)) and (not stop_owner or absent(stop_owner))
        d['source_pins_stable']=all(sha(p)==d['source_sha256'][p.name] for p in files);save()
    print(json.dumps({k:d.get(k) for k in ('status','target_boundary_acceptance','cleanup_complete','source_pins_stable')}))
    return 0 if d.get('status')!='failed_or_unavailable' and d['cleanup_complete'] and d['source_pins_stable'] else 1


if __name__=='__main__':raise SystemExit(main())
