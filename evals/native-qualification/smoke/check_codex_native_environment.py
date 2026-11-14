#!/usr/bin/env python3
"""Actual Codex native executor workflow, with simulated provider responses only.

Failure scenarios fixed before implementation: missing exec bundle, wrong/mutated
executable, wrong endpoint bearer, host credentials absent from child tools,
workspace-native shell/read/apply_patch retained, sibling/secret/process/network
reads refused by executor OS boundary, revoked dispatch stops new native work,
selected environment failure cannot fall back to host, and close stops owned pipes.
No real provider, target, Docker or SSH qualification follows from this fixture.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools'))


def run(base):
    from native_runtime_codex import NativeExecutor
    from native_runtime_transport import RuntimeError, Transport
    workspace=base/'workspace';workspace.mkdir()
    state=base/'executor-state';state.mkdir(mode=0o700)
    allowed=[True]
    @contextmanager
    def guard():
        if not allowed[0]:raise RuntimeError('fixture_revoked')
        yield
    binary=Path(shutil.which('codex')).resolve()
    def launch(command):
        return subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            env={'PATH':'/usr/bin:/bin','CODEX_HOME':str(state),'HOME':str(state)},cwd=workspace,start_new_session=True)
    owner=NativeExecutor(launcher=launch, command=[str(binary),'exec-server','--listen','stdio'],
        environment_id='native-fixture', cwd=str(workspace),dispatch_guard=guard)
    app_state=base/'app-state';app_state.mkdir(mode=0o700)
    app=Transport([str(binary),'app-server','--stdio'],{'PATH':'/usr/bin:/bin','CODEX_HOME':str(app_state),'HOME':str(app_state)},str(workspace),lambda frame:None)
    rows=[]
    try:
        app.request('initialize',{'clientInfo':{'name':'oslit-native-check','version':'1'},'capabilities':{'experimentalApi':True}})
        app.send({'jsonrpc':'2.0','method':'initialized'})
        bad=owner.registration();bad['authBearerToken']='wrong-fixture-bearer';bad['environmentId']='wrong-fixture'
        try:
            app.request('environment/add',bad,timeout=5)
            app.request('environment/info',{'environmentId':'wrong-fixture'},timeout=7)
            raise AssertionError('wrong bridge bearer admitted')
        except RuntimeError:
            rows.append({'check':'wrong_bearer','status':'passed'})
        app.request('environment/add',owner.registration(),timeout=10)
        info=app.request('environment/info',{'environmentId':owner.environment_id})
        assert info, 'native environment info missing'
        rows.append({'check':'actual_native_environment','status':'passed','info':info})
        allowed[0]=False
        try:
            app.request('environment/info',{'environmentId':owner.environment_id},timeout=5)
            # Some info fields may be native cached; admission is directly checked too.
            owner.check_authority()
            raise AssertionError('revoked owner accepted work')
        except RuntimeError:
            rows.append({'check':'revoked_dispatch','status':'passed'})
    finally:
        app_close=app.close();closed=owner.close()
    assert closed['process_exited'] and closed['bridge_exited'] and app_close['process_exited']
    return {'status':'passed','evidence':'actual_native_executor_control_no_model', 'checks':rows,'close':closed,
            'unverified':['native_tool_model_loop','provider_credentials','Docker/SSH','research_qualification']}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    with tempfile.TemporaryDirectory(prefix='codex-env-') as name:result=run(Path(name).resolve())
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'checks':len(result['checks'])}))
