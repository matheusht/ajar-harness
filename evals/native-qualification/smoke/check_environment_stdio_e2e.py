#!/usr/bin/env python3
"""Persistent private tool pipe through simulated Docker; no containment claim."""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'tools'))
from check_environment_transport_e2e import FAKE_DOCKER


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result={'kind':'environment-native-pipe-replay-v2','classification':'simulated_docker_cli_with_actual_stdio',
            'checks':[],'unverified':['real Docker containment','SSH connection','native SDK in Linux image','native network bridge']}
    def check(name,condition):
        result['checks'].append({'name':name,'passed':bool(condition)});assert condition,name
    try:
        from research_environment import Environment, EnvironmentUnavailable
        with tempfile.TemporaryDirectory(prefix='environment-pipe-replay-') as name:
            root=Path(name).resolve();docker=root/'docker'
            code=FAKE_DOCKER.replace("elif args[:2]==['container','exec']:\n",
                "elif args[:2]==['container','exec']:\n if args[-1]=='stdio':\n  print('env-leaked:'+str('OSLIT_TEST_PRIVATE_VALUE' in os.environ),flush=True)\n  for line in sys.stdin:print('reply:'+line.rstrip('\\n'),flush=True)\n  sys.exit(0)\n")
            docker.write_text(code.replace('PYTHON',sys.executable));docker.chmod(0o700)
            profile={'kind':'research-environment-profile-v2','transport':'docker','docker_binary':str(docker),
                     'docker_endpoint':'unix:///fixture/docker.sock','daemon_id':'daemon-fixture',
                     'image_id':'sha256:'+'1'*64,'platform':'linux/arm64','uid':1000,'gid':1000,'ssh':None}
            limits={'memory_bytes':64*1024*1024,'workspace_bytes':1024*1024,'cpu_count':1,'pids':32,'lease_seconds':5,'output_bytes':4096}
            active=[True];events=[]
            def authorize():
                if not active[0]:raise RuntimeError('revoked')
                return {'seconds_remaining':5}
            environment=Environment(profile,limits,authorize,events.append,dispatch_guard=nullcontext)
            application={'id':'app','kind':'application','identity':{'base_url':'https://target.invalid/','version':None},'account_refs':[],'permissions':['read']}
            environment.prepare([application],{})
            try:
                os.environ['OSLIT_TEST_PRIVATE_VALUE']='fixture-value'
                process=environment.launch_stdio(['stdio'])
                check('tool pipe receives only restricted host environment',process.stdout.readline()==b'env-leaked:False\n')
                process.stdin.write(b'one\n');process.stdin.flush()
                first=process.stdout.readline()
                process.stdin.write(b'two\n');process.stdin.flush()
                check('same owned process serves consecutive native messages',first==b'reply:one\n' and process.stdout.readline()==b'reply:two\n')
                check('pipe launch is recorded without claiming command acceptance',any(e['operation']=='launch_stdio' and e.get('status')=='dispatched' for e in events))
                try:environment.launch_stdio(['stdio'])
                except EnvironmentUnavailable:pass
                else:raise AssertionError('second owner accepted under existing environment')
                check('one native tool owner per environment',process.poll() is None)
                active[0]=False
                stopped=environment.revoke()
                check('revocation closes pipe process and observes worker stopped',process.poll() is not None and stopped['status']=='stopped')
                try:environment.launch_stdio(['stdio'])
                except EnvironmentUnavailable:pass
                else:raise AssertionError('retired environment launched native process')
                check('retired generation cannot recreate native pipe',process.poll() is not None)
                process.stdin.close();process.stdout.close()
            finally:
                os.environ.pop('OSLIT_TEST_PRIVATE_VALUE',None)
                environment.cleanup()
        result['status']='passed'
    except Exception as error:
        result['status']='failed';result['error']=type(error).__name__+': '+str(error)
    result['source_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'checks':len(result['checks']),'output':str(args.output)}))
    return 0 if result['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
