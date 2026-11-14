#!/usr/bin/env python3
"""Actual OMP/SDK split with a fake credential and a TLS proxy model fixture.

Extends the failure-first native tool boundary scenarios through the real model
loop: private model environment, separate SDK tools, native proxy/private trust,
no direct egress, native command/read success, credential/process/file denial,
revocation, no persisted key, and kernel-bound owner cleanup. No real provider.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shlex
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import time
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'tools'))
def sha(path):return 'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()


def run(root,sdk):
    from native_runtime_omp import Runtime, ToolOwner, sdk_tree_digest
    from native_runtime_transport import RuntimeError
    from native_credentials import HostCredentialResolver
    from engagement_network import NetworkGate
    work=root/'workspace';work.mkdir();state=root/'model-state';state.mkdir(mode=0o700);tools_state=root/'tool-state'
    outside=root/'outside.txt';outside.write_text('OUTSIDE_PRIVATE_MARKER')
    (work/'inside.txt').write_text('NATIVE_OMP_INSIDE')
    cert=root/'proxy-cert.pem';key=root/'proxy-private.pem'
    subprocess.run([shutil.which('openssl'),'req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),
        '-out',str(cert),'-days','1','-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost,IP:127.0.0.1',
        '-addext','basicConstraints=critical,CA:FALSE'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
    key.chmod(0o600)
    fake='fake-omp-provider-private-marker';active=[True];runtime=[None];requests=[]
    @contextmanager
    def guard():
        if not active[0]:raise RuntimeError('fixture_revoked')
        yield
    class Model(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            assert self.headers.get('Authorization')=='Bearer '+fake, 'OMP model credential absent'
            assert fake not in json.dumps(body), 'OMP tools exposed model credential'
            requests.append(body);seq=len(requests)
            if seq==1:
                pid=runtime[0].transport.process.pid
                command='; '.join(['cat inside.txt','printf NATIVE_OMP_WRITE > written.txt',
                    'cat '+shlex.quote(str(outside)),'/usr/bin/env',"printf '\\nBEGIN_PS\\n'",'/bin/ps eww -p '+str(pid),
                    "printf '\\nEND_PS\\n'",'printf NATIVE_OMP_DONE'])
                delta={'role':'assistant','tool_calls':[{'index':0,'id':'fixture-native-call','type':'function',
                    'function':{'name':'bash','arguments':json.dumps({'command':command,'timeout':5})}}]};finish='tool_calls'
            else:delta={'role':'assistant','content':'Fixture complete.'};finish='stop'
            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
            for item in ({'delta':delta,'finish_reason':None},{'delta':{},'finish_reason':finish}):
                frame={'id':'fixture-'+str(seq),'object':'chat.completion.chunk','created':0,'model':'fixture-model','choices':[{'index':0,**item}]}
                self.wfile.write(('data: '+json.dumps(frame)+'\n\n').encode())
            self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()
    server=ThreadingHTTPServer(('127.0.0.1',0),Model)
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cert,key);server.socket=context.wrap_socket(server.socket,server_side=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    gate=NetworkGate([{'protocol':'https','host':'127.0.0.1','port':server.server_port,
        'address_policy':{'public_only':False,'cidrs':['127.0.0.1/32']}}],lambda:active[0],dispatch_guard=guard,
        upstream_context=ssl.create_default_context(cafile=str(cert)))
    port=gate.serve_tcp(certificate=cert,private_key=key)
    provider_environment={'HTTP_PROXY':f'http://127.0.0.1:{port}','HTTPS_PROXY':f'http://127.0.0.1:{port}',
        'NO_PROXY':'','SSL_CERT_FILE':str(cert),'NODE_EXTRA_CA_CERTS':str(cert)}
    (state/'models.yml').write_text(json.dumps({'providers':{'opencode-go':{
        'baseUrl':f'https://127.0.0.1:{server.server_port}/v1','api':'openai-completions','auth':'apiKey','apiKey':'OPENCODE_API_KEY',
        'models':[{'id':'fixture-model','name':'Local fixture','reasoning':False,'input':['text'],'supportsTools':True,
            'contextWindow':32768,'maxTokens':1024,'cost':{'input':0,'output':0,'cacheRead':0,'cacheWrite':0}}]}}}))
    config=root/'settings.json';config.write_text(json.dumps({'plan':{'enabled':False},'tools':{'xdev':False},'autolearn':{'enabled':False}}))
    schema=root/'schema.json';schema.write_text('{"fixture":"actual-native-omp18.20"}')
    executable=Path(shutil.which('omp')).resolve()
    profile={'kind':'omp','version':'18.20.0','executable':{'path':str(executable),'sha256':sha(executable)},
        'protocol':{'mode':'stdio-jsonl','schema_file':str(schema),'schema_sha256':sha(schema)},
        'config_file':str(config),'config_sha256':sha(config),'provider':'opencode-go','model':'fixture-model',
        'credential_ref':'env_OPENCODE_API_KEY','required_capabilities':['native_tools']}
    raw=root/'profile.json';raw.write_text(json.dumps(profile)+'\n')
    sdk_root=sdk.resolve().parents[2];bun=Path(shutil.which('bun')).resolve();sidecar=(ROOT/'tools/native_runtime_omp_tools.mjs').resolve();q=json.dumps
    policy=f'''(version 1)(deny default)(import "system.sb")
(allow process-fork process-exec)(allow signal (target same-sandbox))(allow process-info* (target self))
(allow file-read-metadata)
(allow file-read* file-test-existence (path-ancestors {q(str(sdk_root))}) (path-ancestors {q(str(bun))}) (path-ancestors {q(str(sidecar))}))
(allow file-read* file-test-existence file-map-executable (subpath {q(str(sdk_root))}) (literal {q(str(bun))}) (literal {q(str(sidecar))}) (subpath "/bin") (subpath "/usr/bin") (subpath "/usr/libexec"))
(allow file-read* file-test-existence file-write* (subpath {q(str(work))}) (subpath {q(str(tools_state))}))
(deny network*)'''
    owner=ToolOwner(sdk,work,tools_state,sdk_pin={'root':str(sdk_root),'sha256':sdk_tree_digest(sdk_root)},
        command_prefix=['/usr/bin/sandbox-exec','-p',policy],dispatch_guard=guard)
    try:
        runtime[0]=Runtime(profile,state,work,host_tools=owner.catalog,host_call=owner.host_call,dispatch_guard=guard,
            credential_resolver=HostCredentialResolver(environment={'OPENCODE_API_KEY':fake}),
            protected_model=True,profile_sha256=sha(raw),provider_environment=provider_environment,
            command_prefix=['/usr/bin/sandbox-exec','-p',f'(version 1)(allow default)(deny network*)(allow network-outbound (remote ip "localhost:{port}"))'])
        identity=runtime[0].fresh();receipt=runtime[0].owner_receipt()
        runtime[0].invoke('Run the native boundary fixture.','native-boundary')
        deadline=time.monotonic()+30
        while runtime[0].active and time.monotonic()<deadline:runtime[0].observe(.1)
        assert not runtime[0].active and len(requests)==2, ('OMP loop not settled',len(requests))
        result=json.dumps(list(owner.results.values()))
        assert 'NATIVE_OMP_INSIDE' in result and 'NATIVE_OMP_DONE' in result and (work/'written.txt').read_text()=='NATIVE_OMP_WRITE'
        assert 'OUTSIDE_PRIVATE_MARKER' not in result and fake not in result
        ps=result.split('BEGIN_PS',1)[1].split('END_PS',1)[0]
        assert str(runtime[0].transport.process.pid) not in ps, 'native SDK could inspect model process'
        active[0]=False
        try:runtime[0].invoke('must refuse','revoked');raise AssertionError('revoked OMP dispatch')
        except RuntimeError as error:assert str(error)=='fixture_revoked'
        closed=runtime[0].close();runtime[0]=None
        assert closed['child_absence']=='verified' and closed['capabilities_revoked']
        assert not any(fake.encode() in p.read_bytes() for p in state.rglob('*') if p.is_file()), 'OMP key persisted'
        return {'status':'passed','evidence':'actual_omp_sdk_tls_proxy_simulated_model',
            'checks':['native_read_write','separate_tool_environment','provider_key_absent_from_tools','outside_file_denied',
                'model_process_inspection_denied','TLS_proxy_private_trust','revoked_dispatch','no_key_persistence','owned_model_stop'],
            'provider_requests':len(requests),'external_provider_calls':0,'identity':identity,'owner_receipt':receipt,'close':closed,
            'bun_version':subprocess.check_output([str(bun),'--version'],text=True).strip(),
            'unverified':['Linux/Docker/SSH','SDK_engine_Bun1.4.4_compatibility','live_provider','research_qualification']}
    finally:
        if runtime[0]:runtime[0].close()
        owner.close();gate.close();server.shutdown();server.server_close();thread.join(timeout=2)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--omp-sdk',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    with tempfile.TemporaryDirectory(prefix='omp-provider-boundary-') as d:result=run(Path(d).resolve(),args.omp_sdk)
    result['source_hashes']={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),*(ROOT/'tools').glob('native_runtime_*'),ROOT/'tools/native_credentials.py'] if p.is_file()}
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'checks':len(result['checks'])}))
