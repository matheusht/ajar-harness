#!/usr/bin/env python3
"""Owned RFC1918 listener/real TCP source E2E; no Docker/provider/cloud."""
import argparse
import base64
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
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
from check_v2_connect import TLSHandler,HeldCollector

HERE=Path(__file__).resolve().parent
RANGES=tuple(ipaddress.ip_network(n) for n in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16'))


def local_private_address():
    if shutil.which('ip'):
        r=subprocess.run(['ip','-j','-4','address','show'],capture_output=True,text=True,check=True,timeout=5)
        values=[a['local'] for i in json.loads(r.stdout) for a in i.get('addr_info',[]) if a.get('family')=='inet']
    else:
        r=subprocess.run([shutil.which('ifconfig') or '/sbin/ifconfig','-a'],capture_output=True,text=True,check=True,timeout=5)
        values=re.findall(r'\binet (\d+\.\d+\.\d+\.\d+)',r.stdout)
    return next((v for v in values if any(ipaddress.ip_address(v) in n for n in RANGES)),None)


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--local-ip');args=ap.parse_args()
    out=args.output.resolve();out.mkdir(mode=0o700,parents=True,exist_ok=False)
    files=[HERE/n for n in ('v2_connect.py','check_v2_private_listener.py','check_v2_connect.py','PRIVATE-LISTENER-CHECKS.md')]
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();capability='local_'+uuid.uuid4().hex
    auth='Basic '+base64.b64encode(('run:'+capability).encode()).decode()
    d={'classification':'owned private listener/source tuple E2E; not cloud/native qualification','provider_calls':0,'docker_calls':0,'cloud_calls':0,
       'checks':[],'commands':[],'processes':[],'source_sha256':{p.name:sha(p) for p in files}}
    (out/'source').mkdir()
    for p in files:shutil.copyfile(p,out/'source'/p.name)
    servers=[];processes=[];connections=[];ports=[]
    def clean(s):
        for value in (capability,auth,auth[6:]):s=s.replace(value,'[LOCAL-CAPABILITY]')
        return s.replace(str(Path.home()),'<HOME>')
    def save():(out/'result.json').write_text(clean(json.dumps(d,indent=2))+'\n')
    def check(name,ok):
        d['checks'].append({'check':name,'passed':bool(ok)});save()
        if not ok:raise RuntimeError(name)
    def wait(predicate,seconds=5):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            if predicate():return True
            time.sleep(.02)
        return False
    def serve(handler):
        server=socketserver.ThreadingTCPServer(('127.0.0.1',0),handler);server.daemon_threads=True;servers.append(server);ports.append(server.server_address)
        threading.Thread(target=server.serve_forever,daemon=True).start();return server
    def header(s):
        b=bytearray()
        while not b.endswith(b'\r\n\r\n') and len(b)<16384:
            part=s.recv(1)
            if not part:break
            b.extend(part)
        return bytes(b)
    class Proxy(socketserver.BaseRequestHandler):
        def handle(self):
            remote=None
            try:
                self.request.settimeout(3);request=header(self.request)
                self.server.rows.append({'fixed_authority':request.startswith(b'CONNECT opencode.ai:443 HTTP/1.1\r\n'),'local_capability_leaked':capability.encode() in request})
                if not self.server.rows[-1]['fixed_authority']:return
                remote=socket.create_connection(self.server.target,timeout=3);self.request.sendall(b'HTTP/1.1 200 OK\r\n\r\n')
                while True:
                    ready,_,_=select.select([self.request,remote],[],[],.2)
                    for source in ready:
                        data=source.recv(65536)
                        if not data:return
                        (remote if source is self.request else self.request).sendall(data)
            except OSError:pass
            finally:
                if remote:remote.close()
    try:
        private=args.local_ip or local_private_address();check('assigned local RFC1918 address available',private is not None and any(ipaddress.IPv4Address(private) in n for n in RANGES))
        # Kernel-observed peer proof on a temporary owned listener, without aliases/routes.
        with socket.socket() as listener:
            listener.bind((private,0));listener.listen();listener.settimeout(2)
            observed=[]
            for source in (private,'127.0.0.1'):
                with socket.create_connection(listener.getsockname(),timeout=2,source_address=(source,0)) as client:
                    peer,addr=listener.accept()
                    with peer:client.sendall(b'owned');assert peer.recv(5)==b'owned'
                    observed.append({'requested_source':source,'kernel_peer':addr[0]})
            d['local_source_probe']=observed
            check('two distinct actual TCP peers verified safely',observed[0]['kernel_peer']==private and observed[1]['kernel_peer']=='127.0.0.1')
        with tempfile.TemporaryDirectory(prefix='private-listener-e2e-') as temporary:
            root=Path(temporary);cap=root/'cap';cap.write_text(capability);cap.chmod(0o600);cert=root/'cert.pem';key=root/'key.pem'
            r=subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=owned.fixture','-addext','subjectAltName=DNS:owned.fixture','-keyout',str(key),'-out',str(cert)],capture_output=True,timeout=20)
            check('owned TLS fixture created',r.returncode==0)
            tls=serve(TLSHandler);tls.rows=[];tls.sni=[];tls.context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.context.load_cert_chain(cert,key)
            held=serve(HeldCollector);held.rows=[]
            proxy=serve(Proxy);proxy.rows=[];proxy.target=tls.server_address
            def start(name,extra=(),duration=120,target=None,chain=False):
                cmd=[sys.executable,str(HERE/'v2_connect.py'),'--state-dir',str(out/name),'--capability-file',str(cap),
                    '--max-connections','16','--max-bytes','8388608','--duration',str(duration),*extra]
                env=os.environ.copy()
                if chain:
                    env['HTTPS_PROXY']='http://127.0.0.1:'+str(proxy.server_address[1]);cmd+=['--upstream-proxy-env','HTTPS_PROXY']
                else:cmd+=['--dummy-port',str(target or tls.server_address[1])]
                p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env);processes.append(p);d['commands'].append({'argv':cmd})
                check(name+' startup bounded',bool(select.select([p.stdout],[],[],6)[0]))
                line=p.stdout.readline();info=json.loads(line) if line else None
                if info is None:p.wait(timeout=3)
                d['processes'].append({'pid':p.pid,'state':name,'startup':info})
                if info:ports.append((info['host'],info['port']))
                return p,info
            def stop(p):
                if p.poll() is None:p.terminate()
                stdout,stderr=p.communicate(timeout=5);(out/('process-'+str(p.pid)+'.stderr')).write_text(clean(stderr))
                return stderr
            def ledger(name):
                # Recovery is permitted on this test's owned working pool after SIGTERM.
                with sqlite3.connect(out/name/'tunnel.sqlite3') as db:
                    config,created,charged=db.execute('SELECT config,created,bytes FROM pool').fetchone()
                    return {'config':json.loads(config),'created':created,'bytes':charged,
                            'tunnels':db.execute('SELECT phase,uploaded,reason FROM tunnels').fetchall(),
                            'events':db.execute('SELECT kind,data FROM events').fetchall()}
            def connect(info,source=private,credential=auth,authority='opencode.ai:443',prefix=None,record=True):
                s=socket.create_connection((info['host'],info['port']),timeout=3,source_address=(source,0));connections.append(s)
                data=prefix or (f'CONNECT {authority} HTTP/1.1\r\nHost: {authority}\r\nProxy-Authorization: {credential}\r\nX-Forwarded-For: {private}\r\nForwarded: for={private}\r\n\r\n').encode()
                try:s.sendall(data);reply=header(s)
                except (ConnectionResetError,BrokenPipeError):reply=b''
                if record:d.setdefault('client_source_readback',[]).append({'requested_source':source,'actual_source':s.getsockname()[0]})
                return s,reply
            def positive(info):
                s,reply=connect(info)
                if b' 200 ' not in reply:s.close();return False
                context=ssl.create_default_context(cafile=cert)
                with context.wrap_socket(s,server_hostname='owned.fixture') as stream:
                    stream.sendall(b'owned-tls-input');return stream.recv(4096)==b'owned-tls-response'
            flags=('--listen-address',private,'--relay-peer',private)
            p,info=start('main',flags);check('explicit private listener ready',info is not None and info['host']==private)
            baseline=ledger('main');burst={'completed':0,'accepted':0}
            for _ in range(4096):
                try:
                    s,reply=connect(info,'127.0.0.1',prefix=b'C',record=False);s.close();burst['completed']+=1;burst['accepted']+=b' 200 ' in reply
                except OSError as error:burst['error']=type(error).__name__;break
            after_burst=ledger('main');d['wrong_peer_burst']={**burst,'events_before':len(baseline['events']),'events_after':len(after_burst['events']),'provider_revoked':(out/'main/REVOKED').exists()}
            check('untrusted peer burst cannot spend audit or transport authority',burst['completed']==4096 and burst['accepted']==0 and after_burst==baseline and not tls.rows and p.poll() is None and not (out/'main/REVOKED').exists())
            for label,prefix in [('known-capability',None),('proxy-protocol',b'PROXY TCP4 '+private.encode()+b' '+private.encode()+b' 1234 443\r\n'),('incomplete-header',b'C')]:
                before=ledger('main');s,reply=connect(info,'127.0.0.1',prefix=prefix);s.close();after=ledger('main')
                check('wrong peer '+label+' closes before admission',b' 200 ' not in reply and not after['tunnels'] and after['bytes']==before['bytes']==0 and not tls.rows and after==before)
            stalled=[]
            for _ in range(4):
                s=socket.create_connection((private,info['port']),timeout=2,source_address=(private,0));s.sendall(b'C');stalled.append(s);connections.append(s)
            time.sleep(.1);before_rejections=ledger('main')['events']
            s,reply=connect(info,'127.0.0.1');s.close()
            check('wrong peer filtered before full worker slots',ledger('main')['events']==before_rejections and not ledger('main')['tunnels'])
            for s in stalled:s.close()
            check('authorized incomplete headers settle',wait(lambda:sum(k=='rejected' and json.loads(v).get('reason')=='short_header' for k,v in ledger('main')['events'])>=4))
            for label,kwargs in [('capability',{'credential':'Basic wrong'}),('authority',{'authority':'outside.invalid:443'})]:
                s,reply=connect(info,**kwargs);s.close();check('authorized peer wrong '+label+' rejected',b' 403 ' in reply and not ledger('main')['tunnels'] and not tls.rows)
            check('authorized kernel peer and capability reach real TLS',positive(info) and len(tls.rows)==1)
            check('private pool frozen identity recorded',ledger('main')['config'].get('private_listener')=={'listen_address':private,'relay_peer':private})
            check('positive tunnel settles',wait(lambda:all(r[0]=='closed' for r in ledger('main')['tunnels'])))
            stop(p);snapshot=ledger('main')
            other_peer='10.254.254.254' if private!='10.254.254.254' else '10.254.254.253'
            for label,changed in [('peer',('--listen-address',private,'--relay-peer',other_peer)),('bind',('--listen-address',other_peer,'--relay-peer',private)),('default',())]:
                child,rejected=start('main',changed);stderr=stop(child)
                check('retained pool refuses '+label+' change',rejected is None and child.returncode!=0 and 'frozen_pool_mismatch' in stderr and ledger('main')==snapshot)
            p,info=start('main',flags);check('same private mode retains budget/deadline',info is not None and ledger('main')['created']==snapshot['created'] and ledger('main')['bytes']==snapshot['bytes']);check('same mode remains usable',positive(info));stop(p)
            child,different=start('different-peer',('--listen-address',private,'--relay-peer',other_peer))
            tls_before=len(tls.rows);s,reply=connect(different);s.close()
            check('listen address cannot substitute for configured relay peer',b' 200 ' not in reply and not ledger('different-peer')['tunnels'] and ledger('different-peer')['bytes']==0 and len(tls.rows)==tls_before and not ledger('different-peer')['events']);stop(child)
            invalid=['0.0.0.0','8.8.8.8','127.0.0.1','169.254.1.1','224.0.0.1','192.0.2.1','100.64.0.1','198.18.0.1','localhost','192.168.0.1/32','::1','fc00::1','::ffff:192.168.0.1','10.01.2.3','not-an-ip']
            for n,value in enumerate(invalid):
                for field in ('listen-address','relay-peer'):
                    extra=list(flags);extra[1 if field=='listen-address' else 3]=value
                    child,rejected=start('invalid-'+str(n)+'-'+field,extra);check('invalid '+field+' '+value+' refused',rejected is None and child.returncode!=0);stop(child)
            for field in ('listen-address','relay-peer'):
                child,rejected=start('missing-'+field,('--'+field,private));check('missing matching flag refused',rejected is None and child.returncode!=0);stop(child)
            child,default=start('default');check('neither flag preserves exact loopback default',default is not None and default['host']=='127.0.0.1' and 'private_listener' not in ledger('default')['config']);stop(child)
            child,composed=start('composed',flags,chain=True);count=len(proxy.rows)
            s,reply=connect(composed,'127.0.0.1');s.close();check('wrong source cannot reach configured upstream proxy',len(proxy.rows)==count and not ledger('composed')['tunnels'])
            check('private ingress composes with explicit HTTP CONNECT hop',positive(composed) and len(proxy.rows)==count+1 and proxy.rows[-1]=={'fixed_authority':True,'local_capability_leaked':False});stop(child)
            for name,duration,manual in [('revoke',120,True),('deadline',2,False)]:
                child,current=start(name,flags,duration=duration,target=held.server_address[1]);s,reply=connect(current);check(name+' held transport admitted',b' 200 ' in reply)
                payload=('before-'+name).encode();s.sendall(payload);check(name+' independent held route positive',s.recv(3)==b'ACK')
                if manual:(out/name/'REVOKED').touch()
                child.wait(timeout=6)
                try:s.sendall(b'after-stop');closed=s.recv(64)==b''
                except OSError:closed=True
                s.close();snapshot=ledger(name);time.sleep(.1)
                check(name+' held and fresh dispatch stop',closed and ledger(name)['bytes']==snapshot['bytes'] and [r['payload'] for r in held.rows]==(['before-revoke'] if manual else ['before-revoke','before-deadline']))
                with socket.socket() as fresh:
                    fresh.settimeout(1);check(name+' listener gone',fresh.connect_ex((private,current['port']))!=0)
                stop(child)
            d['local_listen_address']=private;d['authorized_local_peer']=private;d['tls_rows']=tls.rows;d['held_rows']=held.rows;d['proxy_rows']=proxy.rows;d['main_ledger']=ledger('main')
            d['status']='private_listener_owned_e2e_pass_not_cloud_qualified'
    except Exception as error:d['status']='failed_or_unavailable';d['error']=type(error).__name__+': '+str(error)
    finally:
        for s in connections:
            try:s.close()
            except OSError:pass
        for p in processes:
            if p.poll() is None:p.terminate()
            try:stdout,stderr=p.communicate(timeout=5)
            except subprocess.TimeoutExpired:p.kill();stdout,stderr=p.communicate(timeout=3)
            (out/('process-'+str(p.pid)+'.stderr')).write_text(clean(stderr))
        for server in servers:server.shutdown();server.server_close()
        d['process_cleanup']=all(p.poll() is not None for p in processes);d['listener_cleanup']=True
        for host,port in ports:
            with socket.socket() as probe:probe.settimeout(.3);d['listener_cleanup'] &= probe.connect_ex((host,port))!=0
        d['owned_listeners']=[{'host':h,'port':p} for h,p in ports]
        d['source_pins_stable']=all(sha(p)==d['source_sha256'][p.name] for p in files);save()
        d['credential_scan_clean']=all(not any(value.encode() in p.read_bytes() for value in (capability,auth,auth[6:])) for p in out.rglob('*') if p.is_file());save()
    print(json.dumps({k:d.get(k) for k in ('status','process_cleanup','listener_cleanup','source_pins_stable','credential_scan_clean')}))
    return 0 if d.get('status')=='private_listener_owned_e2e_pass_not_cloud_qualified' and all(d[k] for k in ('process_cleanup','listener_cleanup','source_pins_stable','credential_scan_clean')) else 1


if __name__=='__main__':raise SystemExit(main())
