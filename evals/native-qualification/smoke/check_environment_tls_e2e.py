#!/usr/bin/env python3
"""Real local TLS proxy checks; no provider, public destination or trust-store edit."""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import hashlib
import http.client
import http.server
import json
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'tools'))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result={'kind':'environment-local-tls-e2e-v2','classification':'actual_local_harmless_tls',
            'checks':[],'unverified':['Docker or SSH network integration','provider behavior','research']}
    def check(name,condition):
        result['checks'].append({'name':name,'passed':bool(condition)});assert condition,name
    try:
        from engagement_network import NetworkGate
        with tempfile.TemporaryDirectory(prefix='oslit-tls-e2e-') as name:
            root=Path(name);certificate=root/'test-cert.pem';key=root/'test-key.pem'
            subprocess.run([shutil.which('openssl') or '/usr/bin/openssl','req','-x509','-newkey','rsa:2048',
                            '-nodes','-keyout',str(key),'-out',str(certificate),'-days','1',
                            '-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost,IP:127.0.0.1'],
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True,timeout=15)
            key.chmod(0o600)
            context=ssl.create_default_context(cafile=str(certificate))
            hits=[]
            class Receiver(http.server.BaseHTTPRequestHandler):
                def do_GET(self):
                    hits.append(self.path);self.send_response(200);self.end_headers();self.wfile.write(b'tls-ok')
                def log_message(self,*_):pass
            server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Receiver)
            tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.load_cert_chain(certificate,key)
            server.socket=tls.wrap_socket(server.socket,server_side=True)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            route={'protocol':'https','host':'127.0.0.1','port':server.server_port,
                   'address_policy':{'public_only':False,'cidrs':['127.0.0.1/32']}}
            gate=None
            try:
                gate=NetworkGate([route],lambda:True,dispatch_guard=nullcontext,upstream_context=context)
                endpoint=root/'proxy.sock';gate.serve(endpoint,certificate=certificate,private_key=key)
                def request(inner_host,path='/ok'):
                    peer=socket.socket(socket.AF_UNIX);peer.settimeout(5);peer.connect(str(endpoint))
                    authority=f'127.0.0.1:{server.server_port}'
                    peer.sendall(f'CONNECT {authority} HTTP/1.1\r\nHost: {authority}\r\n\r\n'.encode())
                    response=b''
                    while not response.endswith(b'\r\n\r\n'):response+=peer.recv(1)
                    assert response.startswith(b'HTTP/1.1 200'),response
                    encrypted=context.wrap_socket(peer,server_hostname='127.0.0.1')
                    encrypted.sendall(f'GET {path} HTTP/1.1\r\nHost: {inner_host}\r\n\r\n'.encode())
                    response=http.client.HTTPResponse(encrypted);response.begin()
                    result=f'HTTP/1.1 {response.status} '.encode()+response.read()
                    response.close();encrypted.close();return result
                good=request(f'127.0.0.1:{server.server_port}')
                check('CONNECT terminates TLS and forwards admitted inner request',good.endswith(b'tls-ok') and hits==['/ok'])
                bad=request('denied.invalid')
                check('inner Host cannot bypass CONNECT authority',bad.startswith(b'HTTP/1.1 403') and hits==['/ok'])
                bad=request(f'127.0.0.1:{server.server_port}','https://denied.invalid/no')
                check('inner absolute URI cannot change destination',bad.startswith(b'HTTP/1.1 403') and hits==['/ok'])
                direct=NetworkGate([route],lambda:True,dispatch_guard=nullcontext)
                try:
                    try:direct.fetch(f'https://127.0.0.1:{server.server_port}/untrusted')
                    except ssl.SSLError:pass
                    else:raise AssertionError('untrusted upstream certificate accepted')
                    check('upstream certificate validation remains enabled',hits==['/ok'])
                finally:direct.close()
            finally:
                if gate:gate.close()
                server.shutdown();server.server_close();thread.join()
            check('private test material stays in disposable directory',key.stat().st_mode & 0o077==0)
        result['status']='passed'
    except Exception as error:
        result['status']='failed';result['error']=type(error).__name__+': '+str(error)
    result['source_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'checks':len(result['checks']),'output':str(args.output)}))
    return 0 if result['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
