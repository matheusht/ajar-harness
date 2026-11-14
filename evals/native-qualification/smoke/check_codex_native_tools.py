#!/usr/bin/env python3
"""Actual Codex native tools through an isolated executor and a simulated Responses server.

The boundary scenarios are specified in check_codex_native_environment.py before
bridge implementation. This complete workflow exercises those same scenarios
with the actual model/tool loop. Fake markers only; never uses real credentials.
Optional retained-session scenario: read back the same native thread with its
selected executor, then run another tool turn using earlier context and files.
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
import subprocess
import ssl
import sys
import tempfile
import threading
import time
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'tools'))


def sha(path):return 'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()


def run(root, *, tls_proxy=False, retain_session=False):
    from native_runtime_codex import Runtime, NativeExecutor, _DISABLED_FEATURES
    from native_credentials import HostCredentialResolver
    from native_runtime_transport import RuntimeError
    work=root/'workspace';work.mkdir()
    (work/'inside.txt').write_text('NATIVE_INSIDE_PROOF')
    outside=root/'outside-marker';outside.write_text('OUTSIDE_PRIVATE_MARKER')
    (work/'symlink').symlink_to(outside)
    exec_state=root/'exec-state';exec_state.mkdir(mode=0o700)
    app_state=root/'app-state'
    binary=Path(shutil.which('codex')).resolve()
    allowed=[True];requests=[];events=[];runtime=[None];escapes=[]
    fake='fake-native-provider-private-marker'
    @contextmanager
    def guard():
        if not allowed[0]:raise RuntimeError('fixture_revoked')
        yield
    class Model(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            assert self.headers.get('Authorization')=='Bearer '+fake, 'model credential not bound'
            assert fake not in json.dumps(body), 'tool path exposed provider credential'
            requests.append(body);seq=len(requests)
            if seq==1:
                item={'id':'fc_positive','type':'function_call','call_id':'positive','name':'exec_command',
                    'arguments':json.dumps({'cmd':'cat inside.txt; printf SHELL_WRITE_PROOF > shell-written.txt', 'max_output_tokens':1000})}
            elif seq==2:
                item={'id':'fc_patch','type':'custom_tool_call','call_id':'native-patch','name':'apply_patch',
                    'input':'*** Begin Patch\n*** Add File: native-patch.txt\n+NATIVE_PATCH_PROOF\n*** End Patch'}
            elif seq==3:
                pid=runtime[0].transport.process.pid
                command='; '.join(['cat '+shlex.quote(str(outside)), 'cat symlink', '/usr/bin/env',
                    "printf '\\nBEGIN_PS\\n'", '/bin/ps eww -p '+str(pid), "printf '\\nEND_PS\\n'",
                    '/usr/bin/curl --max-time 1 -s '+shlex.quote(f'http://127.0.0.1:{server.server_port}/forbidden'),
                    'printf NATIVE_NEGATIVES_DONE'])
                item={'id':'fc_negative','type':'function_call','call_id':'negative','name':'exec_command',
                    'arguments':json.dumps({'cmd':command,'max_output_tokens':2000})}
            elif seq in (4,5,6):
                name={4:'spawn_agent',5:'mcp__fixture__escape',6:'web.run'}[seq]
                item={'id':'fc_alternate_'+str(seq),'type':'function_call','call_id':'alternate-'+str(seq),
                    'name':name,'arguments':json.dumps({'prompt':'harmless denial probe','search_query':[{'q':'fixture'}]})}
            elif retain_session and seq == 8:
                item={'id':'fc_retained','type':'function_call','call_id':'retained','name':'exec_command',
                    'arguments':json.dumps({'cmd':'cat shell-written.txt native-patch.txt', 'max_output_tokens':1000})}
            else:
                item={'id':'msg_done','type':'message','role':'assistant','content':[{'type':'output_text','text':'Fixture complete.'}]}
            response={'id':'fixture-'+str(seq),'object':'response','status':'completed','output':[item],
                'usage':{'input_tokens':10,'output_tokens':10,'total_tokens':20}}
            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
            frames=[{'type':'response.created','response':{**response,'status':'in_progress','output':[]}},
                {'type':'response.output_item.added','output_index':0,'item':item},
                {'type':'response.output_item.done','output_index':0,'item':item},
                {'type':'response.completed','response':response}]
            for index,frame in enumerate(frames):
                frame['sequence_number']=index
                self.wfile.write(('event: '+frame['type']+'\ndata: '+json.dumps(frame)+'\n\n').encode())
            self.wfile.flush()
        def do_GET(self):
            escapes.append(True);self.send_response(403);self.end_headers()
    server=ThreadingHTTPServer(('127.0.0.1',0),Model)
    gate=None;provider_environment=None;proxy_port=server.server_port
    if tls_proxy:
        from engagement_network import NetworkGate
        cert=root/'proxy-ca.pem';key=root/'proxy-private.pem'
        subprocess.run([shutil.which('openssl'),'req','-x509','-newkey','rsa:2048','-nodes',
            '-keyout',str(key),'-out',str(cert),'-days','1','-subj','/CN=localhost',
            '-addext','subjectAltName=DNS:localhost,IP:127.0.0.1','-addext','basicConstraints=critical,CA:FALSE'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
        key.chmod(0o600)
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cert,key)
        server.socket=context.wrap_socket(server.socket,server_side=True)
        gate=NetworkGate([{'protocol':'https','host':'127.0.0.1','port':server.server_port,
            'address_policy':{'public_only':False,'cidrs':['127.0.0.1/32']}}],lambda:allowed[0],
            dispatch_guard=guard,upstream_context=ssl.create_default_context(cafile=str(cert)))
        proxy_port=gate.serve_tcp(certificate=cert,private_key=key)
        provider_environment={'HTTP_PROXY':f'http://127.0.0.1:{proxy_port}',
            'HTTPS_PROXY':f'http://127.0.0.1:{proxy_port}','NO_PROXY':'',
            'SSL_CERT_FILE':str(cert),'NODE_EXTRA_CA_CERTS':str(cert)}
    scheme='https' if tls_proxy else 'http'
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    config=root/'config.toml'
    feature_lines='\n'.join(name+' = false' for name in _DISABLED_FEATURES)
    config.write_text(f'''model = "gpt-6.1-sol"
model_provider = "oslit-fixture"
web_search = "disabled"
default_permissions = "oslit-worker"
[features]
{feature_lines}
[shell_environment_policy]
inherit = "none"
[shell_environment_policy.set]
PATH = "/usr/bin:/bin"
[permissions.oslit-worker.filesystem]
":root" = "deny"
":minimal" = "read"
{json.dumps(str(binary.parent))} = "read"
[permissions.oslit-worker.filesystem.":workspace_roots"]
"." = "write"
[permissions.oslit-worker.network]
enabled = false
[model_providers.oslit-fixture]
name = "Local fake provider"
base_url = "{scheme}://127.0.0.1:{server.server_port}/v1"
wire_api = "responses"
requires_openai_auth = false
env_key = "OPENAI_API_KEY"
''')
    schema=root/'schema.json';schema.write_text('{"fixture":"actual-native-wire-schema"}')
    profile={'kind':'codex','version':'0.166.0','executable':{'path':str(binary),'sha256':sha(binary)},
        'protocol':{'mode':'stdio-jsonrpc','schema_file':str(schema),'schema_sha256':sha(schema)},
        'config_file':str(config),'config_sha256':sha(config),'provider':'oslit-fixture','model':'gpt-6.1-sol',
        'credential_ref':'env_OPENAI_API_KEY','required_capabilities':['native_tools']}
    raw=root/'profile.json';raw.write_text(json.dumps(profile,sort_keys=True)+'\n')
    def launch(command):
        return subprocess.Popen(command,cwd=work,
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            env={'PATH':'/usr/bin:/bin','HOME':str(exec_state),'CODEX_HOME':str(exec_state)},start_new_session=True)
    owner=NativeExecutor(launcher=launch,command=[str(binary),'exec-server','--listen','stdio'],
        environment_id='native-work',cwd=str(work),dispatch_guard=guard,expected_platform='macos')
    try:
        runtime[0]=Runtime(profile,app_state,work,native_executor=owner,dispatch_guard=guard,
            protected_model=True,profile_sha256=sha(raw),provider_environment=provider_environment,credential_resolver=HostCredentialResolver(environment={'OPENAI_API_KEY':fake}),
            command_prefix=['/usr/bin/sandbox-exec','-p',f'(version 1)(allow default)(deny network*)(allow network-outbound (remote ip "localhost:{proxy_port}"))(allow network-outbound (remote ip "localhost:{owner.url.split(":")[-1].rstrip("/")}"))'])
        identity=runtime[0].fresh();receipt=runtime[0].owner_receipt()
        runtime[0].invoke('Run the native boundary fixture.','fixture-run')
        deadline=time.monotonic()+30
        while runtime[0].active and time.monotonic()<deadline:events.extend(runtime[0].observe(.1))
        assert not runtime[0].active, 'native loop did not settle'
        assert len(requests)==7, ('unexpected native loop request count',len(requests))
        assert (work/'shell-written.txt').read_text()=='SHELL_WRITE_PROOF'
        assert (work/'native-patch.txt').read_text()=='NATIVE_PATCH_PROOF\n'
        text=json.dumps(requests)
        assert 'NATIVE_INSIDE_PROOF' in text and 'NATIVE_NEGATIVES_DONE' in text
        assert 'OUTSIDE_PRIVATE_MARKER' not in text and fake not in text
        assert 'Operation not permitted' in text or 'Permission denied' in text
        # At least one native unavailable-tool result must exist for each forced alternate route.
        outputs=[x for r in requests for x in r.get('input',[]) if x.get('type') in ('function_call_output','custom_tool_call_output')]
        negative=next(str(x['output']) for x in outputs if x.get('call_id')=='negative')
        ps_output=negative.split('BEGIN_PS',1)[1].split('END_PS',1)[0]
        assert str(runtime[0].transport.process.pid) not in ps_output, 'native process inspection reached model process'
        assert not escapes, 'native tool reached provider endpoint'
        for call_id in ('alternate-4','alternate-5','alternate-6'):
            assert any(x.get('call_id')==call_id and str(x.get('output','')).startswith('unsupported call:') for x in outputs), call_id
        retained = None
        if retain_session:
            resumed = runtime[0].resume(identity['session_id'])
            assert resumed['session_id'] == identity['session_id'] and runtime[0].owner_receipt() == receipt
            runtime[0].invoke('Continue the related task using the earlier context and files.','retained-task')
            deadline=time.monotonic()+30
            while runtime[0].active and time.monotonic()<deadline:events.extend(runtime[0].observe(.1))
            assert not runtime[0].active and len(requests)==9, 'retained native tool turn did not settle'
            assert ('Run the native boundary fixture.' in json.dumps(requests[7]) or
                    requests[7].get('previous_response_id') == 'fixture-7'), 'retained native conversation missing'
            second_outputs=[x for r in requests[7:] for x in r.get('input',[]) if x.get('call_id')=='retained']
            assert any('SHELL_WRITE_PROOF' in str(x.get('output','')) and 'NATIVE_PATCH_PROOF' in str(x.get('output',''))
                for x in second_outputs), 'retained native executor could not read earlier artifacts'
            retained={'session_id':resumed['session_id'],'same_owner':True,'prior_context_observed':True,
                'native_tool_readback':'first_turn_files_read_in_second_turn'}
        allowed[0]=False
        try:runtime[0].invoke('must refuse','after-revoke');raise AssertionError('revoked runtime dispatched')
        except RuntimeError as error:assert str(error)=='fixture_revoked'
        assert len(requests)==(9 if retain_session else 7)
        close=runtime[0].close();runtime[0]=None
        assert close['child_absence']=='verified' and close['capabilities_revoked']
        assert not any(fake.encode() in p.read_bytes() for p in app_state.rglob('*') if p.is_file()),'provider key persisted'
        return {'status':'passed','evidence':'actual_codex_native_tools_with_simulated_model',
            'checks':['native_shell_read_write','native_apply_patch','outside_and_symlink_denied',
                'provider_key_absent_from_tools','cross_process_inspection_denied','provider_endpoint_denied',
                'spawn_mcp_web_routes_refused','revoked_dispatch','no_key_persistence','owned_runtime_stop'],
            'tls_proxy_verified':tls_proxy,'provider_requests':len(requests),'external_provider_calls':0,'identity':identity,'owner_receipt':receipt,'close':close,
            'retained_session':retained,
            'unverified':['Linux/Docker/SSH','live_provider_credentials','research_qualification']}
    finally:
        if runtime[0]:runtime[0].close()
        owner.close()
        if gate:gate.close()
        server.shutdown();server.server_close();thread.join(timeout=2)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--tls-proxy',action='store_true');parser.add_argument('--retain-session',action='store_true');args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='codex-native-tools-') as name:result=run(Path(name).resolve(),tls_proxy=args.tls_proxy,retain_session=args.retain_session)
    result['source_hashes']={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),*(ROOT/'tools').glob('native_runtime_*'),ROOT/'tools/native_credentials.py'] if p.is_file()}
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'checks':len(result['checks'])}))
