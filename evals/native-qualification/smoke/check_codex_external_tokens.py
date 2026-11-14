#!/usr/bin/env python3
"""Actual native external-token login, fake access token, no provider inference/network.

The source marker remains only in its intentional fake native store. Isolated
app state and tool workspace must never contain a persisted copy. This checks the
experimental 0.166 host-managed auth path, not live token validity or OAuth refresh.
"""
import argparse
import base64
from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'tools'))

def sha(path):return 'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()

def run(root):
    from native_runtime_codex import Runtime, NativeExecutor, _DISABLED_FEATURES
    from native_credentials import HostCredentialResolver
    binary=Path(shutil.which('codex')).resolve()
    work=root/'workspace';work.mkdir();state=root/'app-state';execstate=root/'exec-state';execstate.mkdir(mode=0o700)
    payload={'exp':int(time.time())+3600,'email':'fixture@example.invalid',
        'https://api.openai.com/auth':{'chatgpt_account_id':'fixture-account','chatgpt_plan_type':'plus'}}
    token='eyJhbGciOiJub25lIn0.'+base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')+'.FAKE_SIGNATURE'
    auth=root/'native-source-auth.json';auth.write_text(json.dumps({'tokens':{'access_token':token,'account_id':'fixture-account'}}));auth.chmod(0o600)
    config=root/'config.toml';config.write_text('''model="gpt-6.1-sol"
model_provider="openai"
web_search="disabled"
default_permissions="oslit-worker"
[features]
'''+''.join(x+'=false\n' for x in _DISABLED_FEATURES)+'''
[shell_environment_policy]
inherit="none"
[shell_environment_policy.set]
PATH="/usr/bin:/bin"
[permissions.oslit-worker.filesystem]
":root"="deny"
":minimal"="read"
'''+json.dumps(str(binary.parent))+'''="read"
[permissions.oslit-worker.filesystem.":workspace_roots"]
"."="write"
[permissions.oslit-worker.network]
enabled=false
''')
    schema=root/'schema.json';schema.write_text('{"fixture":"native0.166"}')
    profile={'kind':'codex','version':'0.166.0','executable':{'path':str(binary),'sha256':sha(binary)},
        'protocol':{'mode':'stdio-jsonrpc','schema_file':str(schema),'schema_sha256':sha(schema)},
        'config_file':str(config),'config_sha256':sha(config),'provider':'openai','model':'gpt-6.1-sol',
        'credential_ref':'codex_default','required_capabilities':[]}
    raw=root/'profile.json';raw.write_text(json.dumps(profile)+'\n')
    def launcher(command):
        return subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            cwd=work,env={'PATH':'/usr/bin:/bin','HOME':str(execstate),'CODEX_HOME':str(execstate)},start_new_session=True)
    owner=NativeExecutor(launcher=launcher,command=[str(binary),'exec-server','--listen','stdio'],
        environment_id='native-auth-check',cwd=str(work),dispatch_guard=nullcontext,expected_platform='macos')
    runtime=None
    try:
        port=owner.url.split(':')[-1].rstrip('/')
        runtime=Runtime(profile,state,work,native_executor=owner,dispatch_guard=nullcontext,
            protected_model=True,profile_sha256=sha(raw),credential_resolver=HostCredentialResolver(codex_auth_path=auth),
            command_prefix=['/usr/bin/sandbox-exec','-p',f'(version 1)(allow default)(deny network*)(allow network-outbound (remote ip "localhost:{port}"))'])
        assert runtime.authentication=='external_tokens_accepted', 'native external-token login not accepted'
        close=runtime.close();runtime=None
        leaked=[str(p.relative_to(root)) for tree in (state,work,execstate) for p in tree.rglob('*') if p.is_file() and token.encode() in p.read_bytes()]
        assert not leaked, 'external access token persisted'
        assert not (state/'auth.json').exists(), 'external-token login created native auth copy'
        return {'status':'passed','evidence':'actual_codex_external_token_fake_no_network',
            'login_type':'chatgptAuthTokens','account_routing':'unverified_requires_live_provider','token_persisted':False,'auth_copy_created':False,'close':close,
            'provider_calls':0,'live_token_validity':'unverified','auth_route':'experimental0.166_host_managed'}
    finally:
        if runtime:runtime.close()
        owner.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    with tempfile.TemporaryDirectory(prefix='codex-native-auth-') as d:result=run(Path(d).resolve())
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status']}))
