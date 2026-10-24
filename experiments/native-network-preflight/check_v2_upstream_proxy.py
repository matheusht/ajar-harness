#!/usr/bin/env python3
"""Owned HTTP CONNECT proxy + real TLS receiver E2E; no Docker/provider."""
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
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from urllib.parse import quote
from check_v2_connect import TLSHandler
sys.path.insert(0,str(Path(__file__).resolve().parent/'v2-effect-windows'))
from native_run import request_stop

HERE=Path(__file__).resolve().parent


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    out=args.output.resolve();out.mkdir(mode=0o700,parents=True,exist_ok=False)
    files=[HERE/n for n in ('v2_connect.py','check_v2_upstream_proxy.py','check_v2_connect.py','UPSTREAM-PROXY-CHECKS.md','READINESS-STOP-CHECKS.md')]
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    d={'classification':'owned upstream proxy transport E2E; not cloud/native qualification','provider_calls':0,'docker_calls':0,
       'checks':[],'commands':[],'processes':[],'source_sha256':{p.name:sha(p) for p in files}}
    (out/'source').mkdir()
    for p in files:shutil.copyfile(p,out/'source'/p.name)
    capability='local_'+uuid.uuid4().hex;username='proxy_'+uuid.uuid4().hex;password='secret/'+uuid.uuid4().hex
    auth='Basic '+base64.b64encode(('run:'+capability).encode()).decode();proxy_auth='Basic '+base64.b64encode((username+':'+password).encode()).decode()
    secrets=[capability,auth,auth[6:],username,password,quote(password,safe=''),proxy_auth,proxy_auth[6:]]
    processes=[];servers=[];ports=[];connections=[];release=threading.Event();d['raw_runtime_output_secret_free']=True
    def clean(s):
        for value in secrets:s=s.replace(value,'[REDACTED]')
        return s.replace(str(Path.home()),'<HOME>')
    def save(): (out/'result.json').write_text(clean(json.dumps(d,indent=2))+'\n')
    def check(name,ok):
        d['checks'].append({'check':name,'passed':bool(ok)});save()
        if not ok:raise RuntimeError(name)
    def wait(test,seconds=8):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            if test():return True
            time.sleep(.02)
        return False
    def header(s):
        data=bytearray()
        while not data.endswith(b'\r\n\r\n') and len(data)<16384:
            part=s.recv(1)
            if not part:break
            data.extend(part)
        return bytes(data)
    class Proxy(socketserver.BaseRequestHandler):
        def handle(self):
            row={'mode':self.server.mode,'peer_closed':False,'payload_consumed':0};self.server.rows.append(row);remote=None
            try:
                self.request.settimeout(8);request=header(self.request)
                lines=request.split(b'\r\n');fields={}
                for line in lines[1:]:
                    if b':' in line:
                        key,value=line.split(b':',1);fields[key.lower()]=value.strip()
                row['fixed_authority']=lines[0] in (b'CONNECT opencode.ai:443 HTTP/1.1',b'CONNECT opencode.ai:443 HTTP/1.0')
                row['selected_auth']=fields.get(b'proxy-authorization')==self.server.expected_auth
                row['local_capability_leaked']=capability.encode() in request or auth.encode() in request
                row['extra_header_forwarded']=b'x-no-forward' in fields
                row['received_request']=True
                if not row['fixed_authority'] or not row['selected_auth']:
                    self.request.sendall(b'HTTP/1.1 403 Forbidden\r\n\r\n');return
                mode=row['mode']
                if mode=='deny':self.request.sendall(b'HTTP/1.1 403 Forbidden\r\n\r\n');return
                if mode=='bad-status':self.request.sendall(b'NOT-HTTP 200 OK\r\n\r\n');return
                if mode=='no-status-space':self.request.sendall(b'HTTP/1.1 200\r\n\r\n');return
                if mode=='status-control':self.request.sendall(b'HTTP/1.1 200 OK\nInvalid\r\n\r\n');return
                if mode=='bad-header':self.request.sendall(b'HTTP/1.1 200 OK\r\nNoColon\r\n\r\n');return
                if mode=='oversize':self.request.sendall(b'HTTP/1.1 200 OK\r\nX: '+b'x'*17000+b'\r\n\r\n');return
                if mode=='eof':return
                if mode=='slow':
                    for byte in b'HTTP/1.1 200 Connection Established\r\n\r\n':
                        self.request.sendall(bytes([byte]));time.sleep(.2)
                    row['reply_completed']=True;return
                if mode=='hang':
                    until=time.monotonic()+8
                    while time.monotonic()<until and not release.is_set():
                        ready,_,_=select.select([self.request],[],[],.05)
                        if ready and not self.request.recv(1):row['peer_closed']=True;break
                    return
                self.request.sendall(b'HTTP/1.1 200 \r\n\r\n' if mode=='empty-reason' else b'HTTP/1.1 200 Connection Established\r\n\r\n')
                if mode=='stall':
                    release.wait(timeout=35)
                    while data:=self.request.recv(65536):row['payload_consumed']+=len(data)
                    row['peer_closed']=True;return
                remote=socket.create_connection(self.server.target,timeout=5)
                while not release.is_set():
                    ready,_,_=select.select([self.request,remote],[],[],.1)
                    for source in ready:
                        data=source.recv(65536)
                        if not data:return
                        (remote if source is self.request else self.request).sendall(data)
            except OSError as error:row['error']=type(error).__name__
            finally:
                if remote:remote.close()
                row['done']=True
    def serve(handler,small=False):
        server=socketserver.ThreadingTCPServer(('127.0.0.1',0),handler,bind_and_activate=False);server.daemon_threads=True
        if small:server.socket.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,4096)
        server.server_bind();server.server_activate();servers.append(server);ports.append(server.server_address[1])
        threading.Thread(target=server.serve_forever,daemon=True).start();return server
    try:
        with tempfile.TemporaryDirectory(prefix='upstream-proxy-e2e-') as temporary:
            root=Path(temporary);cap=root/'cap';cap.write_text(capability);cap.chmod(0o600)
            cert=root/'cert.pem';key=root/'key.pem'
            r=subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=opencode.ai',
                '-addext','subjectAltName=DNS:opencode.ai','-keyout',str(key),'-out',str(cert)],capture_output=True,timeout=20)
            check('owned TLS certificate created',r.returncode==0)
            tls=serve(TLSHandler);tls.rows=[];tls.sni=[];tls.context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.context.load_cert_chain(cert,key)
            tls.context.set_servername_callback(lambda sock,name,ctx:tls.sni.append(name))
            proxy=serve(Proxy,True);proxy.mode='tunnel';proxy.rows=[];proxy.target=tls.server_address;proxy.expected_auth=proxy_auth.encode()
            alternate=serve(Proxy);alternate.mode='tunnel';alternate.rows=[];alternate.target=tls.server_address;alternate.expected_auth=proxy_auth.encode()
            url=f'http://{quote(username,safe="")}:{quote(password,safe="")}@127.0.0.1:{proxy.server_address[1]}'
            trace=out/'connection-trace.jsonl';wrapper=root/'offline-wrapper.py'
            wrapper.write_text('''import copy,json,os,runpy,socket,sys,time,threading
from pathlib import Path
TRACE=REPLACE_TRACE
PORTS=REPLACE_PORTS
def record(kind,**data):
 fd=os.open(TRACE,os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
 try:os.write(fd,(json.dumps(dict(kind=kind,monotonic=time.monotonic(),**data))+'\\n').encode())
 finally:os.close(fd)
resolve=socket.getaddrinfo
connect=socket.create_connection
def owned_resolve(host,port,*a,**kw):
 if host!='127.0.0.1' or port not in PORTS:
  record('forbidden_resolution');raise OSError('offline_network_guard')
 record('resolution',port=port)
 return resolve(host,port,*a,**kw)
def owned_connect(address,*a,**kw):
 if address[0]!='127.0.0.1' or address[1] not in PORTS:
  record('forbidden_connection');raise OSError('offline_network_guard')
 record('connection',port=address[1])
 s=connect(address,*a,**kw);s.setsockopt(socket.SOL_SOCKET,socket.SO_SNDBUF,4096);return s
socket.getaddrinfo=owned_resolve
socket.create_connection=owned_connect
sys.path.insert(0,str(Path(REPLACE_SOURCE).parent))
sys.path.insert(0,str(Path(REPLACE_SOURCE).parent/'v2-effect-windows'))
import v2_connect,native_run
original_pool=v2_connect.Pool
phase=threading.local()
original_accept=v2_connect.accept_proxy_tunnel
def accepted_proxy(*args):
 original_accept(*args);phase.ready=True
v2_connect.accept_proxy_tunnel=accepted_proxy
original_server=v2_connect.Server
class ObservedClient:
 def __init__(self,s):self.socket=s
 def __getattr__(self,name):return getattr(self.socket,name)
 def sendall(self,data):
  ready=data.startswith(b'HTTP/1.1 200 ')
  if ready:record('client_ready_write_begin')
  self.socket.sendall(data)
  if ready:record('client_ready_write_end')
class ObservedServer(original_server):
 def get_request(self):
  request,address=super().get_request();return ObservedClient(request),address
v2_connect.Server=ObservedServer
class GuardPool(original_pool):
 def __init__(self,args):
  super().__init__(args)
  self.control=Path(os.environ['LRH_GUARD_FIXTURE']) if os.environ.get('LRH_GUARD_FIXTURE') else None
  if self.control:
   self.args=copy.copy(args);self.args.native_run_state=self.control;self.args.native_control=native_run
 def checkpoint(self,name):
  (self.control/(name+'_HELD')).touch();end=time.monotonic()+12
  while not (self.control/(name+'_RELEASE')).exists() and time.monotonic()<end:time.sleep(.01)
 def admit(self):
  number=super().admit()
  if self.control and (self.control/'ARM').exists():self.checkpoint('ADMISSION')
  return number
 def active(self,*args,**kwargs):
  allowed=super().active(*args,**kwargs)
  if allowed and self.control and (self.control/'READINESS_ARM').exists() and getattr(phase,'ready',False):
   phase.ready=False;self.checkpoint('READINESS')
  return allowed
 def event(self,kind,data):
  if self.control and kind=='stop_detected':self.checkpoint('WATCH')
  return super().event(kind,data)
v2_connect.Pool=GuardPool
v2_connect.main()
'''.replace('REPLACE_TRACE',repr(str(trace))).replace('REPLACE_PORTS',repr(ports)).replace('REPLACE_SOURCE',repr(str(HERE/'v2_connect.py'))))
            shutil.copyfile(wrapper,out/'source/offline-wrapper.py');d['wrapper_sha256']=sha(wrapper)
            def start(name,proxy_url=url,selector='HTTPS_PROXY',dummy=False,duration=120,extra=(),guard=None):
                command=[sys.executable,str(wrapper),'--state-dir',str(out/name),'--capability-file',str(cap),
                    '--max-connections','16','--max-bytes','8388608','--duration',str(duration)]
                if selector:command+=['--upstream-proxy-env',selector]
                if dummy:command+=['--dummy-port',str(tls.server_address[1])]
                command+=list(extra);env=os.environ.copy()
                for k in ('HTTP_PROXY','HTTPS_PROXY'):env.pop(k,None)
                if proxy_url is not None:env['HTTPS_PROXY']=proxy_url;env['HTTP_PROXY']=proxy_url
                if guard:env['LRH_GUARD_FIXTURE']=str(guard)
                p=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env);processes.append(p)
                d['commands'].append({'argv':command})
                check(name+' startup returns within bound',bool(select.select([p.stdout],[],[],8)[0]))
                line=p.stdout.readline();info=json.loads(line) if line else None
                if info is None:p.wait(timeout=3)
                d['processes'].append({'pid':p.pid,'state':name,'startup':info})
                return p,info
            def stop(p):
                if p.poll() is None:p.terminate()
                stdout,stderr=p.communicate(timeout=7)
                d['raw_runtime_output_secret_free'] &= not any(value in stdout+stderr for value in secrets)
                (out/('process-'+str(p.pid)+'.stderr')).write_text(clean(stderr))
            def connect(info,authority='opencode.ai:443',credential=auth,method='CONNECT'):
                s=socket.create_connection(('127.0.0.1',info['port']),timeout=8);connections.append(s)
                s.sendall((f'{method} {authority} HTTP/1.1\r\nHost: {authority}\r\nProxy-Authorization: {credential}\r\nX-No-Forward: inert\r\n\r\n').encode())
                return s,header(s)
            def tls_positive(info):
                s,response=connect(info)
                if b' 200 ' not in response:s.close();return False
                context=ssl.create_default_context(cafile=cert)
                with context.wrap_socket(s,server_hostname='opencode.ai') as stream:
                    stream.sendall(b'owned-tls-input');return stream.recv(4096)==b'owned-tls-response'
            def ledger(name):
                # Ordinary test SIGTERM may leave a hot journal; recover this owned working pool.
                with sqlite3.connect(out/name/'tunnel.sqlite3') as db:
                    pool=db.execute('SELECT config,created,bytes FROM pool').fetchone()
                    return {'config':json.loads(pool[0]),'created':pool[1],'bytes':pool[2],
                            'tunnels':db.execute('SELECT phase,uploaded,reason FROM tunnels').fetchall()}
            guard=out/'host-guard-fixture';guard.mkdir(mode=0o700)
            (guard/'RUN.json').write_text(json.dumps({'deadline_monotonic':time.monotonic()+120}));(guard/'RUN.json').chmod(0o600)
            (guard/'READY').touch(mode=0o600);(guard/'ARM').touch()
            p,guard_info=start('queued-connect',guard=guard);result={};accepted_before=len(proxy.rows)
            def queued():
                try:
                    connection,response=connect(guard_info);result['accepted']=b' 200 ' in response;connection.close()
                except OSError:result['accepted']=False
            queued_thread=threading.Thread(target=queued,daemon=True);queued_thread.start()
            check('actual admission held before upstream dispatch',wait(lambda:(guard/'ADMISSION_HELD').exists()))
            request_stop(guard,'queued_upstream_stop')
            check('independent watcher teardown held',wait(lambda:(guard/'WATCH_HELD').exists()))
            trace_before=trace.read_text() if trace.exists() else ''
            (guard/'ADMISSION_RELEASE').touch();queued_thread.join(timeout=4)
            time.sleep(.15)
            trace_after=trace.read_text() if trace.exists() else ''
            d['queued_upstream_observation']={'proxy_connections_before':accepted_before,'proxy_connections_after':len(proxy.rows),'client_result':result,'trace_before':trace_before.splitlines(),'trace_after':trace_after.splitlines(),'stop_request':json.loads((guard/'STOP_REQUEST').read_text())}
            check('closed host guard prevents queued TCP and CONNECT dispatch',not queued_thread.is_alive() and result=={'accepted':False} and len(proxy.rows)==accepted_before and trace_before==trace_after)
            check('host-only fixture never fabricates native verified marker',not (guard/'REVOKED').exists())
            (guard/'WATCH_RELEASE').touch();p.wait(timeout=4);stop(p)
            d['host_guard_fixture']='real dispatch guard and stop API; no Docker inventory/freeze or native verified marker'
            proxy.mode='no-status-space';p,status_info=start('no-status-space');status_socket,status_reply=connect(status_info);status_socket.close()
            d['missing_status_space_accepted']=b' 200 ' in status_reply
            check('status code requires trailing space before CRLF',not d['missing_status_space_accepted']);stop(p);proxy.mode='tunnel'
            ready_guard=out/'readiness-guard-fixture';ready_guard.mkdir(mode=0o700)
            (ready_guard/'RUN.json').write_text(json.dumps({'deadline_monotonic':time.monotonic()+120}));(ready_guard/'RUN.json').chmod(0o600)
            (ready_guard/'READY').touch(mode=0o600);(ready_guard/'READINESS_ARM').touch()
            p,ready_info=start('readiness-stop',guard=ready_guard);ready_result={};stop_result={}
            def pending_readiness():
                try:
                    connection,response=connect(ready_info);ready_result.update(accepted=b' 200 ' in response,observed_monotonic=time.monotonic());connection.close()
                except OSError:ready_result.update(accepted=False,observed_monotonic=time.monotonic())
            ready_thread=threading.Thread(target=pending_readiness,daemon=True);ready_thread.start()
            check('actual post-proxy readiness check held',wait(lambda:(ready_guard/'READINESS_HELD').exists()))
            def stop_readiness():
                stop_result['started']=time.monotonic()
                try:request_stop(ready_guard,'readiness_race');stop_result['returned']=time.monotonic()
                except Exception as error:stop_result['error']=type(error).__name__
            stop_thread=threading.Thread(target=stop_readiness,daemon=True);stop_thread.start()
            wait(lambda:'returned' in stop_result or 'error' in stop_result,seconds=.25)
            if 'returned' in stop_result:check('teardown held after completed early stop',wait(lambda:(ready_guard/'WATCH_HELD').exists()))
            (ready_guard/'READINESS_RELEASE').touch();stop_thread.join(timeout=4);ready_thread.join(timeout=4)
            check('readiness and stop threads settle',not stop_thread.is_alive() and not ready_thread.is_alive() and 'returned' in stop_result and 'error' not in stop_result)
            check('readiness watcher teardown independently held',wait(lambda:(ready_guard/'WATCH_HELD').exists()))
            writes=[json.loads(line) for line in trace.read_text().splitlines() if json.loads(line)['kind'].startswith('client_ready_write')]
            ends=[r['monotonic'] for r in writes if r['kind']=='client_ready_write_end']
            d['readiness_stop_observation']={'stop':stop_result,'client':ready_result,'actual_ready_writes':writes,'native_verified_marker_present':(ready_guard/'REVOKED').exists()}
            check('local readiness write cannot follow completed stop',all(end<=stop_result['returned'] for end in ends) and (not ready_result['accepted'] or bool(ends)))
            check('readiness fixture has no native verified stop claim',not (ready_guard/'REVOKED').exists())
            (ready_guard/'WATCH_RELEASE').touch();p.wait(timeout=4);stop(p)
            proxy.mode='empty-reason';p,empty_info=start('empty-reason');check('valid empty reason with trailing space preserves TLS',tls_positive(empty_info));stop(p);proxy.mode='tunnel'
            tls_before_main=len(tls.rows)
            process,info=start('main');check('explicit proxy branch ready',info is not None)
            check('actual owned TLS through selected proxy',tls_positive(info) and len(tls.rows)==tls_before_main+1)
            check('fixed authority selected auth no local/header leakage',proxy.rows[0]['fixed_authority'] and proxy.rows[0]['selected_auth'] and not proxy.rows[0]['local_capability_leaked'] and not proxy.rows[0]['extra_header_forwarded'])
            before=len(proxy.rows)
            for label,kwargs in [('authority',{'authority':'outside.invalid:443'}),('port',{'authority':'opencode.ai:444'}),('method',{'method':'GET'}),('local-auth',{'credential':'Basic wrong'})]:
                s,response=connect(info,**kwargs);s.close();check('wrong '+label+' rejected before upstream',b' 403 ' in response and len(proxy.rows)==before)
            for mode in ('deny','bad-status','status-control','bad-header','oversize','eof','hang','slow'):
                proxy.mode=mode;s,response=connect(info);s.close();d.setdefault('proxy_failure_results',[]).append({'mode':mode,'client_accepted':b' 200 ' in response});check(mode+' fails closed',b' 200 ' not in response)
            proxy.mode='tunnel';check('failed hops do not reset or disable later bounded positive',tls_positive(info))
            check('all main tunnel phases settle',wait(lambda:all(r[0]=='closed' for r in ledger('main')['tunnels'])))
            snapshot=ledger('main');stop(process)
            for label,new_url,selector in [('endpoint',url.replace(str(proxy.server_address[1]),str(alternate.server_address[1])),'HTTPS_PROXY'),
                ('credentials',url.replace(quote(password,safe=''),quote(password+'x',safe='')),'HTTPS_PROXY'),('selector',url,'HTTP_PROXY'),('direct',url,None)]:
                p,rejected=start('main',new_url,selector);check('frozen '+label+' cannot change',rejected is None and p.returncode!=0 and ledger('main')==snapshot);stop(p)
            process,info=start('main');check('same proxy clean restart retains counters and deadline',info is not None and ledger('main')['created']==snapshot['created'] and ledger('main')['bytes']==snapshot['bytes']);check('retained proxy pool still works',tls_positive(info));stop(process)
            invalid=[('missing',None,()),('empty','',()),('scheme',url.replace('http:','https:',1),()),('path',url+'/other',()),('query',url+'?x=1',()),('fragment',url+'#x',()),('empty-query',url+'?',()),('empty-fragment',url+'#',()),('control',url+'\n',()),('bad-port','http://127.0.0.1:0',()),('dummy-conflict',url,('--dummy-port',str(tls.server_address[1])))]
            for label,bad,extra in invalid:
                p,rejected=start('invalid-'+label,bad,extra=extra);check(label+' invalid configuration refused',rejected is None and p.returncode!=0);stop(p)
            for label,selector,extra in [('variable','OTHER_PROXY',()),('empty-variable',None,('--upstream-proxy-env',''))]:
                p,rejected=start('invalid-'+label,url,selector=selector,extra=extra);check(label+' invalid selection refused',rejected is None and p.returncode!=0);stop(p)
            proxy.expected_auth=None
            p,info=start('no-proxy-auth',f'http://127.0.0.1:{proxy.server_address[1]}');check('configured proxy without credentials works',info is not None and tls_positive(info));stop(p)
            proxy.expected_auth=proxy_auth.encode()
            p,info=start('http-variable',selector='HTTP_PROXY');check('explicit HTTP_PROXY selection works',info is not None and tls_positive(info));stop(p)
            p,info=start('ambient-ignored','not a URL',None,True);check('default dummy ignores ambient proxy selection',info is not None and tls_positive(info));stop(p)
            for name,duration,manual in [('stop-handshake',120,True),('deadline-handshake',1,False)]:
                proxy.mode='hang';p,info=start(name,duration=duration);result={};offset=len(proxy.rows)
                def pending():
                    try:
                        s,response=connect(info);result['accepted']=b' 200 ' in response;s.close()
                    except OSError:result['accepted']=False
                worker=threading.Thread(target=pending,daemon=True);worker.start()
                check(name+' upstream handshake staged',wait(lambda:len(proxy.rows)>offset and proxy.rows[-1].get('received_request')))
                if manual:(out/name/'REVOKED').touch()
                worker.join(timeout=7);check(name+' blocked socket settles',not worker.is_alive() and result=={'accepted':False} and wait(lambda:proxy.rows[-1]['peer_closed']))
                p.wait(timeout=4);stop(p);check(name+' provider admission closed',(out/name/'REVOKED').exists())
            proxy.mode='stall';p,info=start('backpressure');active=[];senders=[];backpressure_started=time.monotonic()
            for _ in range(4):
                s,response=connect(info);check('backpressure tunnel admitted',b' 200 ' in response);s.settimeout(12);active.append(s)
                def send(s=s):
                    try:s.sendall(b'x'*8388608)
                    except OSError:pass
                worker=threading.Thread(target=send,daemon=True);senders.append(worker);worker.start()
            def backpressured():
                stalled=[r for r in proxy.rows if r['mode']=='stall']
                return (len([r for r in ledger('backpressure')['tunnels'] if r[0]=='active' and r[1]>0])==4
                        and all(w.is_alive() for w in senders) and len(stalled)==4
                        and all(r['payload_consumed']==0 for r in stalled))
            check('real four-worker charged backpressure staged',wait(backpressured,seconds=max(0,backpressure_started+4-time.monotonic())))
            d['backpressure_staged']={'ledger':ledger('backpressure'),'senders_alive':[w.is_alive() for w in senders],
                'proxy_payload_consumed':[r['payload_consumed'] for r in proxy.rows if r['mode']=='stall']}
            (out/'backpressure/REVOKED').touch();stop_issued=time.monotonic()
            d['backpressure_stop_window']={'staging_started':backpressure_started,'stop_issued':stop_issued,'socket_timeout_seconds':5}
            check('backpressure stop issued before socket timeout',stop_issued<backpressure_started+5)
            p.wait(timeout=5)
            for s in active:s.close()
            for worker in senders:worker.join(timeout=3)
            check('backpressured senders and worker process settle',all(not w.is_alive() for w in senders) and p.poll() is not None)
            after=ledger('backpressure');time.sleep(.15);check('no post-stop payload charge',ledger('backpressure')['bytes']==after['bytes']);stop(p)
            d['proxy_rows']=proxy.rows;d['alternate_proxy_rows']=alternate.rows;d['tls_rows']=tls.rows;d['main_ledger']=ledger('main');d['backpressure_ledger']=after
            trace_rows=[json.loads(line) for line in trace.read_text().splitlines()];d['connection_trace']=trace_rows
            check('no raw provider fallback or external resolution',not any(r['kind'].startswith('forbidden') for r in trace_rows) and not alternate.rows)
            d['status']='upstream_proxy_owned_e2e_pass_not_cloud_qualified'
    except Exception as error:d['status']='failed_or_unavailable';d['error']=type(error).__name__+': '+str(error)
    finally:
        release.set()
        for s in connections:
            try:s.close()
            except OSError:pass
        for p in processes:
            if p.poll() is None:p.terminate()
            try:stdout,stderr=p.communicate(timeout=7)
            except subprocess.TimeoutExpired:p.kill();stdout,stderr=p.communicate(timeout=3)
            d['raw_runtime_output_secret_free'] &= not any(value in stdout+stderr for value in secrets)
            (out/('process-'+str(p.pid)+'.stderr')).write_text(clean(stderr))
        for server in servers:server.shutdown();server.server_close()
        d['process_cleanup']=all(p.poll() is not None for p in processes)
        d['listener_cleanup']=True
        for port in ports:
            with socket.socket() as probe:d['listener_cleanup'] &= probe.connect_ex(('127.0.0.1',port))!=0
        d['source_pins_stable']=all(sha(p)==d['source_sha256'][p.name] for p in files)
        save()
        leaks=[str(p.relative_to(out)) for p in out.rglob('*') if p.is_file() and p.suffix not in ('.sqlite3','-shm','-wal') and any(value.encode() in p.read_bytes() for value in secrets)]
        # Scan SQLite bytes too; extension filtering above only avoids duplicate work.
        leaks += [str(p.relative_to(out)) for p in out.rglob('tunnel.sqlite3') if any(value.encode() in p.read_bytes() for value in secrets)]
        d['credential_scan_clean']=not leaks
        if leaks:d['credential_leak_paths']=leaks
        save()
    print(json.dumps({k:d.get(k) for k in ('status','process_cleanup','listener_cleanup','source_pins_stable','credential_scan_clean')}))
    return 0 if d.get('status')=='upstream_proxy_owned_e2e_pass_not_cloud_qualified' and all(d[k] for k in ('process_cleanup','listener_cleanup','source_pins_stable','credential_scan_clean','raw_runtime_output_secret_free')) else 1


if __name__=='__main__':raise SystemExit(main())
