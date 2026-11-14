#!/usr/bin/env python3
"""Actual local sockets through the worker stdio relay; no container isolation claim."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
import hashlib
import http.client
import http.server
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time

REPO=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(REPO/'tools'))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result={'kind':'environment-proxy-bridge-e2e-v2','classification':'actual_local_socket_and_stdio_controls',
            'checks':[],'unverified':['Docker network-none containment','SSH transport','native client CA configuration','provider behavior']}
    def check(name,condition):
        result['checks'].append({'name':name,'passed':bool(condition)});assert condition,name
    try:
        from engagement_network import NetworkGate
        from engagement_network_bridge import ProxyBridge, BridgeUnavailable, MAX_FRAME
        relay=REPO/'tools/engagement_network_bridge.py'
        def launch(command):
            return subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True,
                                    env={k:os.environ[k] for k in ('PATH','LANG') if k in os.environ})
        with tempfile.TemporaryDirectory(prefix='proxy-bridge-e2e-') as name:
            root=Path(name);hits=[];waiting=threading.Event();release=threading.Event()
            class Receiver(http.server.BaseHTTPRequestHandler):
                def do_GET(self):
                    hits.append(self.path)
                    if self.path=='/wait':waiting.set();release.wait(3)
                    self.send_response(200);self.end_headers()
                    try:self.wfile.write(b'controlled-response')
                    except OSError:pass
                def log_message(self,*_):pass
            receiver=http.server.ThreadingHTTPServer(('127.0.0.1',0),Receiver)
            reader=threading.Thread(target=receiver.serve_forever,daemon=True);reader.start()
            route={'protocol':'http','host':'127.0.0.1','port':receiver.server_port,
                   'address_policy':{'public_only':False,'cidrs':['127.0.0.1/32']}}
            active=[True];gate=NetworkGate([route],lambda:active[0],dispatch_guard=nullcontext)
            endpoint=root/'gateway.sock';gate.serve(endpoint)
            bridge=None
            try:
                bridge=ProxyBridge(lambda command:launch(command),[sys.executable,str(relay),'relay'],gate,lambda:active[0],dispatch_guard=nullcontext)
                def fetch(path='/ok',url=None):
                    client=http.client.HTTPConnection('127.0.0.1',bridge.port,timeout=5)
                    client.request('GET',url or f'http://127.0.0.1:{receiver.server_port}'+path)
                    response=client.getresponse();body=response.read();status=response.status;client.close();return status,body
                check('ordinary proxy client crosses relay and fixed worker gate',fetch()==(200,b'controlled-response') and hits==['/ok'])
                with ThreadPoolExecutor(max_workers=2) as pool:
                    replies=list(pool.map(fetch,['/one','/two']))
                check('simultaneous streams remain distinct',all(value==(200,b'controlled-response') for value in replies) and '/one' in hits and '/two' in hits)
                before=len(hits);denied=fetch(url='http://denied.invalid/no')
                check('relay cannot change the fixed gateway policy',denied[0]==403 and len(hits)==before)
                peer=socket.create_connection(('127.0.0.1',bridge.port),timeout=5)
                peer.sendall(f'GET http://127.0.0.1:{receiver.server_port}/wait HTTP/1.1\r\nHost: target\r\n\r\n'.encode())
                assert waiting.wait(2)
                closed=bridge.close()
                try:ended=peer.recv(1024)==b''
                except OSError:ended=True
                peer.close();release.set()
                check('bridge cancellation closes active client stream',ended and closed['host_process_exited'])
                bridge=ProxyBridge(launch,[sys.executable,str(relay),'relay'],gate,lambda:active[0],dispatch_guard=nullcontext)
                port=bridge.port;active[0]=False
                deadline=time.monotonic()+2
                while (not bridge.closed.is_set() or bridge.process.poll() is None) and time.monotonic()<deadline:time.sleep(.02)
                try:peer=socket.create_connection(('127.0.0.1',port),timeout=.2);peer.close();live=True
                except OSError:live=False
                check('revoked grant retires relay listener',bridge.closed.is_set() and not live)
                bridge.close();bridge=None
            finally:
                release.set()
                if bridge:bridge.close()
                gate.close();receiver.shutdown();receiver.server_close();reader.join()

            active[0]=True
            gate=NetworkGate([route],lambda:True,dispatch_guard=nullcontext);gate.serve(endpoint)
            try:
                for label,frame in [('malformed',json.dumps({'type':'open','id':1,'destination':'forbidden'})),
                                    ('oversized','x'*(MAX_FRAME+1))]:
                    command=[sys.executable,'-c','import time;print(\'{"type":"ready","port":12345}\',flush=True);print('+repr(frame)+',flush=True);time.sleep(5)']
                    malformed=None
                    try:
                        malformed=ProxyBridge(launch,command,gate,lambda:True,dispatch_guard=nullcontext)
                        deadline=time.monotonic()+2
                        while not malformed.closed.is_set() and time.monotonic()<deadline:time.sleep(.02)
                        rejected=malformed.closed.is_set()
                    except BridgeUnavailable:rejected=True
                    finally:
                        if malformed:malformed.close()
                    check(label+' worker frames fail closed',rejected)
            finally:gate.close()

            process=launch([sys.executable,str(relay),'relay'])
            ready=json.loads(process.stdout.readline());process.stdin.write(b'x'*(MAX_FRAME+1)+b'\n');process.stdin.flush();process.wait(timeout=3)
            check('relay rejects oversized host frames',process.returncode!=0 and ready['type']=='ready')
            process.stdin.close();process.stdout.close()

            certificate=root/'certificate.pem';key=root/'private.pem'
            subprocess.run([shutil.which('openssl') or '/usr/bin/openssl','req','-x509','-newkey','rsa:2048','-nodes',
                            '-keyout',str(key),'-out',str(certificate),'-days','1','-subj','/CN=localhost',
                            '-addext','subjectAltName=DNS:localhost,IP:127.0.0.1'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True,timeout=15)
            key.chmod(0o600);client_context=ssl.create_default_context(cafile=str(certificate))
            receiver=http.server.ThreadingHTTPServer(('127.0.0.1',0),Receiver)
            server_context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);server_context.load_cert_chain(certificate,key)
            receiver.socket=server_context.wrap_socket(receiver.socket,server_side=True)
            reader=threading.Thread(target=receiver.serve_forever,daemon=True);reader.start()
            route={**route,'protocol':'https','port':receiver.server_port}
            gate=NetworkGate([route],lambda:True,dispatch_guard=nullcontext,upstream_context=client_context)
            gate.serve(endpoint,certificate=certificate,private_key=key)
            bridge=ProxyBridge(launch,[sys.executable,str(relay),'relay'],gate,lambda:True,dispatch_guard=nullcontext)
            def encrypted_request(host):
                peer=socket.create_connection(('127.0.0.1',bridge.port),timeout=5)
                authority=f'127.0.0.1:{receiver.server_port}'
                peer.sendall(f'CONNECT {authority} HTTP/1.1\r\nHost: {authority}\r\n\r\n'.encode());header=b''
                while not header.endswith(b'\r\n\r\n'):header+=peer.recv(1)
                assert header.startswith(b'HTTP/1.1 200')
                peer=client_context.wrap_socket(peer,server_hostname='127.0.0.1')
                peer.sendall(f'GET /encrypted HTTP/1.1\r\nHost: {host}\r\n\r\n'.encode())
                response=http.client.HTTPResponse(peer);response.begin();status=response.status;response.read();response.close();peer.close();return status
            try:
                before=len(hits)
                check('HTTPS crosses bounded relay with verified upstream TLS',encrypted_request(f'127.0.0.1:{receiver.server_port}')==200 and len(hits)==before+1)
                before=len(hits)
                check('inner HTTPS host escape remains denied through relay',encrypted_request('denied.invalid')==403 and len(hits)==before)
            finally:
                bridge.close();gate.close();receiver.shutdown();receiver.server_close();reader.join()
        result['status']='passed'
    except Exception as error:
        result['status']='failed';result['error']=type(error).__name__+': '+str(error)
    result['source_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'checks':len(result['checks']),'output':str(args.output)}))
    return 0 if result['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
