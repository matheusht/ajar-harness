#!/usr/bin/env python3
"""Command-boundary replay: never represents real Docker/SSH isolation evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from contextlib import nullcontext

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'tools'))

FAKE_DOCKER = r'''#!PYTHON
import json,sys,time,os
from pathlib import Path
root=Path(__file__).parent
state=root/'state.json'
args=sys.argv[3:]
if '--name' in args and args[args.index('--name')+1].endswith('-stage'):state=root/'stage.json'
if args[-1:] and ('-stage' in args[-1] or args[-1]=='b'*64):state=root/'stage.json'
def read(): return json.loads(state.read_text()) if state.exists() else None
def write(value):
 p=root/(str(os.getpid())+'.tmp');p.write_text(json.dumps(value));p.replace(state)
def get(flag,default=None): return args[args.index(flag)+1] if flag in args else default
if args[:1]==['info']: print('daemon-fixture')
elif args[:2]==['image','inspect']:
 if args[-1]=='sha256:'+'1'*64: print(json.dumps([{'Id':'sha256:'+'1'*64,'Os':'linux','Architecture':'arm64','Config':{'Volumes':None}}]))
 elif (root/'image.json').exists():print('['+(root/'image.json').read_text()+']')
 else:sys.exit(1)
elif args[:2]==['container','create']:
 labels=dict(v.split('=',1) for i,v in enumerate(args) if i and args[i-1]=='--label')
 tmpfs=dict(v.split(':',1) for i,v in enumerate(args) if i and args[i-1]=='--tmpfs')
 x={'Id':('b' if get('--name').endswith('-stage') else 'a')*64,'Name':'/'+get('--name'),'Image':args[-3],
 'Config':{'Labels':labels,'User':get('--user'),'Volumes':None},
 'HostConfig':{'NetworkMode':get('--network'),'ReadonlyRootfs':'--read-only' in args,
 'Privileged':False,'CapDrop':['ALL'],'SecurityOpt':['no-new-privileges=true'],
 'LogConfig':{'Type':'none'},'RestartPolicy':{'Name':'no'},
 'Memory':int(get('--memory')),'MemorySwap':int(get('--memory-swap')),
 'NanoCpus':int(float(get('--cpus'))*1e9),'PidsLimit':int(get('--pids-limit')),
 'Binds':None,'Tmpfs':tmpfs,'PortBindings':{}},'Mounts':[],
 'State':{'Running':False,'Status':'created'}}
 write(x);print(x['Id'])
elif args[:2]==['container','inspect']:
 x=read()
 if x is None: sys.exit(1)
 print(json.dumps([x]))
elif args[:2]==['container','ls']:
 x=read();print(x['Id'] if x else '')
elif args[:2]==['container','cp']:
 if args[-1]=='-':sys.stdout.buffer.write((root/'input.tar').read_bytes());sys.exit(0)
 if args[-1].startswith('b'*64+':'):state=root/'stage.json'
 if read()['HostConfig']['ReadonlyRootfs']:sys.exit(1)
 data=sys.stdin.buffer.read()
 (root/'input.tar').write_bytes(data)
elif args[:2]==['container','commit']:
 x=json.loads((root/'stage.json').read_text())
 image={'Id':'sha256:'+'2'*64,'Os':'linux','Architecture':'arm64','Config':{'Volumes':None,'Labels':x['Config']['Labels']}}
 (root/'image.json').write_text(json.dumps(image));print(image['Id'])
 if (root/'commit-failure').exists():sys.exit(1)
elif args[:2]==['image','rm']:(root/'image.json').unlink()
elif args[:2]==['image','ls']:
 if (root/'image.json').exists():print(json.loads((root/'image.json').read_text())['Id'])
elif args[:2]==['container','start']:
 x=read();x['State']={'Running':True,'Status':'running'};write(x)
 while read() and read()['State']['Running']: time.sleep(.02)
elif args[:2]==['container','exec']:
 if args[-1]=='sleep': time.sleep(60)
 elif args[-1]=='fail':print('missing-fixture-dependency',file=sys.stderr);sys.exit(7)
 else: print('benign-output')
elif args[:2]==['container','kill']:
 x=read();x['State']={'Running':False,'Status':'exited'};write(x)
elif args[:2]==['container','rm']:
 state.unlink(missing_ok=True)
else: sys.exit(64)
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = {'kind': 'environment-command-replay-v2', 'classification': 'simulated_docker_cli',
              'checks': [], 'unverified': ['real Docker', 'SSH transport', 'network isolation', 'research']}
    def check(name, condition):
        result['checks'].append({'name': name, 'passed': bool(condition)})
        assert condition, name
    try:
        from research_environment import Environment as OwnedEnvironment, EnvironmentUnavailable
        from engagement_contract import canonical, source_manifest
        def Environment(*args, **kwargs):
            return OwnedEnvironment(*args, dispatch_guard=nullcontext, **kwargs)
        with tempfile.TemporaryDirectory(prefix='environment-command-replay-') as folder:
            root = Path(folder).resolve()
            docker = root / 'docker'
            docker.write_text(FAKE_DOCKER.replace('PYTHON', sys.executable)); docker.chmod(0o700)
            profile = {'kind': 'research-environment-profile-v2', 'transport': 'docker',
                       'docker_binary': str(docker), 'docker_endpoint': 'unix:///fixture/docker.sock',
                       'daemon_id': 'daemon-fixture', 'image_id': 'sha256:'+'1'*64,
                       'platform': 'linux/arm64',
                       'uid': 1000, 'gid': 1000, 'ssh': None}
            limits = {'memory_bytes': 64*1024*1024, 'workspace_bytes': 1024*1024,
                      'cpu_count': 1, 'pids': 32, 'lease_seconds': 5, 'output_bytes': 4096}
            active = [False]; events = []
            def authorize():
                if not active[0]: raise RuntimeError('revoked')
                return {'seconds_remaining': 5}
            env = Environment(profile, limits, authorize, events.append)
            binary = root/'hello';binary.write_bytes(b'benign-binary')
            access = {'id':'echo','kind':'binary','identity':{'sha256':'sha256:'+hashlib.sha256(binary.read_bytes()).hexdigest(),
                     'platform':'linux/arm64'},'account_refs':[],'permissions':['read','execute']}
            try: env.prepare([access], {'echo': str(binary)})
            except EnvironmentUnavailable: pass
            else: raise AssertionError('denied preparation dispatched')
            check('authorization precedes first environment effect', not (root/'state.json').exists())
            active[0] = True
            prepared = env.prepare([access], {'echo':str(binary)})
            check('binary-only preparation binds actual archive bytes', prepared['status']=='ready' and b'benign-binary' in (root/'input.tar').read_bytes())
            check('stopped input staging creates a distinct immutable image',prepared['identity']['prepared_image_id']=='sha256:'+'2'*64 and not (root/'stage.json').exists())
            check('prepared image input bytes are independently read back',any(event['operation']=='readback_input' and event.get('status')=='settled' for event in events))
            state=json.loads((root/'state.json').read_text())
            check('CLI requests network-none and bounded read-only worker', state['HostConfig']['NetworkMode']=='none' and state['HostConfig']['ReadonlyRootfs'] and state['HostConfig']['Memory']==limits['memory_bytes'])
            output=env.execute(['echo','hello'], timeout_seconds=1)
            check('execution is attributed and observed', output['status']=='settled' and output['output']=='benign-output\n' and any(e['phase']=='intent' and e['operation']=='execute' for e in events))
            failure=env.execute(['fail'],timeout_seconds=1)
            check('ordinary command failure retains bounded setup diagnosis',failure['status']=='settled' and failure['returncode']==7 and 'missing-fixture-dependency' in failure['output'])
            receipt=env.receipt()
            check('receipt retains exact identity without second journal', receipt['container_id']=='a'*64 and receipt['nonce'] and receipt['daemon_id']=='daemon-fixture')
            recovered = Environment(profile, limits, authorize, events.append,
                                    receipt={**receipt, 'container_id': None})
            check('crash before ID acknowledgment reconciles name and nonce', recovered.readback()['identity']['container_id'] == receipt['container_id'])
            active[0]=False
            try: env.execute(['echo','stale'],timeout_seconds=1)
            except EnvironmentUnavailable: pass
            else: raise AssertionError('stale execution dispatched')
            stopped=env.revoke()
            check('revocation is permitted after grant ends', stopped['status']=='stopped')
            cleaned=env.cleanup()
            check('cleanup observes exact resource absence', cleaned['status']=='clean' and not (root/'state.json').exists())
            check('cleanup removes only the owned derived image',not (root/'image.json').exists())
            active[0]=True
            changed={**access,'identity':{**access['identity'],'platform':'linux/amd64'}}
            mismatch=Environment(profile,limits,authorize,events.append)
            try: mismatch.prepare([changed],{'echo':str(binary)})
            except EnvironmentUnavailable: pass
            else: raise AssertionError('unsupported binary architecture dispatched')
            check('wrong binary architecture is rejected before creation', not (root/'state.json').exists())
            env=Environment(profile,limits,authorize,events.append)
            env.prepare([access],{'echo':str(binary)})
            output=env.execute(['sleep'],timeout_seconds=.1)
            check('timed out command remains an unknown effect',output['status']=='unknown')
            try: env.execute(['echo'],timeout_seconds=1)
            except EnvironmentUnavailable: pass
            else: raise AssertionError('uncertain worker reused')
            check('unknown execution holds further writes',env.readback()['status']=='held')
            env.cleanup()
            env=Environment(profile,limits,authorize,events.append)
            env.prepare([access],{'echo':str(binary)})
            state=json.loads((root/'state.json').read_text()); state['Config']['Labels']['io.oslit.engagement']='foreign';(root/'state.json').write_text(json.dumps(state))
            try: env.cleanup()
            except EnvironmentUnavailable: pass
            else: raise AssertionError('foreign resource removed')
            check('nonce mismatch cannot remove a resource', (root/'state.json').exists())
            state['Config']['Labels']['io.oslit.engagement']=env.receipt()['nonce'];(root/'state.json').write_text(json.dumps(state));env.cleanup()
            source=root/'source';source.mkdir();(source/'hello.py').write_text('print("source-input")\n')
            snapshot=source_manifest(source)
            source_access={'id':'source','kind':'source','identity':{'manifest_sha256':'sha256:'+hashlib.sha256(canonical(snapshot)).hexdigest()},
                           'account_refs':[],'permissions':['read','execute']}
            app_access={'id':'app','kind':'application','identity':{'base_url':'https://target.invalid/','version':None},
                        'account_refs':[],'permissions':['read']}
            combined=Environment(profile,limits,authorize,events.append)
            prepared=combined.prepare([source_access,access,app_access],{'source':str(source),'echo':str(binary)})
            check('combined preparation preserves each access identity',len(prepared['identity']['access'])==3 and b'source-input' in (root/'input.tar').read_bytes())
            check('source snapshot leaves supplied source unchanged',source_manifest(source)==snapshot)
            combined.cleanup()
            application=Environment(profile,limits,authorize,events.append)
            prepared=application.prepare([app_access],{})
            check('application-only preparation needs no fabricated source',prepared['status']=='ready' and prepared['inputs']=={})
            application.cleanup()
            (source/'hello.py').write_text('changed\n')
            changed=Environment(profile,limits,authorize,events.append)
            try:changed.prepare([source_access],{'source':str(source)})
            except EnvironmentUnavailable:pass
            else:raise AssertionError('changed signed source accepted')
            check('changed signed source is rejected before creation',not (root/'state.json').exists())
            (root/'commit-failure').touch()
            ambiguous=Environment(profile,limits,authorize,events.append)
            try:ambiguous.prepare([access],{'echo':str(binary)})
            except EnvironmentUnavailable:pass
            else:raise AssertionError('failed commit treated as complete')
            receipt=ambiguous.receipt()
            check('failed image acknowledgment retains unresolved creation',receipt['prepared_image_id'] is None and receipt['unsettled']==['snapshot_input'])
            recovered=Environment(profile,limits,authorize,events.append,receipt=receipt)
            recovered.cleanup()
            check('restart reconciles and removes exact partially acknowledged image',not (root/'image.json').exists() and not (root/'stage.json').exists())
            (root/'commit-failure').unlink()
        result['status']='passed'
    except Exception as error:
        result['status']='failed';result['error']=type(error).__name__+': '+str(error)
    result['source_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'checks':len(result['checks']),'output':str(args.output)}))
    return 0 if result['status']=='passed' else 1


if __name__=='__main__': raise SystemExit(main())
