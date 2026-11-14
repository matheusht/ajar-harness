#!/usr/bin/env python3
"""Kernel-identity owner recovery: wrong birth never signals, owned no-fork process stops."""
import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'tools'))


def run():
    from native_runtime_owner import model_command, process_identity, recover_runtime_owner
    from native_runtime_transport import RuntimeError
    child=subprocess.run(model_command(['/usr/bin/python3','-c','import subprocess;subprocess.run(["/bin/echo","escaped"],check=True)']),capture_output=True,text=True)
    assert child.returncode!=0 and 'Operation not permitted' in child.stderr and 'escaped\n' not in child.stdout
    process=subprocess.Popen(model_command(['/bin/sleep','30']),stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    try:
        identity=process_identity(process.pid)
        receipt={'kind':'native-runtime-owner-v1','runtime':'codex','session_id':'fixture','profile_sha256':'sha256:'+'1'*64,
            'boundary':'darwin-no-fork-v1','process':identity,'bridge_process':None}
        changed=copy.deepcopy(receipt);changed['process']['started_microseconds']+=1
        try:recover_runtime_owner(changed);raise AssertionError('wrong birth admitted')
        except RuntimeError as error:assert str(error)=='native_owner_identity_changed'
        assert process.poll() is None,'wrong receipt stopped process'
        result=recover_runtime_owner(receipt)
        process.wait(timeout=2)
        assert result['process_exited'] and result['child_absence']=='verified' and result['capabilities_revoked']
        repeated=recover_runtime_owner(receipt)
        assert repeated['process_exited'],'stopped owner recovery not idempotent'
        return {'status':'passed','evidence':'actual_darwin_kernel_identity_and_no_fork','fork_denied':True,'identity_mismatch_refused':True,'readback':result}
    finally:
        if process.poll() is None:process.kill();process.wait()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args();result=run()
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status']}))
