#!/usr/bin/env python3
"""Failure-first public-CLI checks for the hosted image driver, with owned peers.

Docker and the installer are synthetic subprocesses in a temporary copied tree.
This checks orchestration/readback/failure cleanup only, never actual image build.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
BASE = 'python@sha256:' + 'a' * 64

INSTALLER = r'''#!/usr/bin/env python3
import argparse,hashlib,json,os
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('command')
for name in ('runtime','platform','base-image','destination','receipt'):p.add_argument('--'+name,required=True)
a=p.parse_args();root=Path(a.destination);root.mkdir(mode=0o700)
if os.environ['FIXTURE_CASE']=='install-failure':raise SystemExit(1)
files={'bin/model':b'ELF model fixture','engagement_network_bridge.py':b'relay','native_runtime_bootstrap.py':b'bootstrap'}
if a.runtime=='codex':files.update({'bin/bun':b'ELF bun fixture','native_runtime_codex_exec.mjs':b'bridge'})
manifest={}
for name,data in files.items():
    path=root/'runtime'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    mode=0o555 if name.startswith('bin/') else 0o444;path.chmod(mode)
    manifest[name]={'sha256':'sha256:'+hashlib.sha256(data).hexdigest(),'size':len(data),'mode':mode}
for name in ('runtime','runtime/bin'):(root/name).chmod(0o755)
(root/'Dockerfile').write_text('FROM '+a.base_image+'\nCOPY --chown=0:0 runtime/ /runtime/\n')
receipt={'kind':'native-model-image-context-receipt-v1','status':'prepared','runtime':a.runtime,'platform':a.platform,
    'runtime_manifest':manifest,'execution_verified':False,'base_image':a.base_image,
    'profile_fields':{'executable':{'path':str(root/'runtime/bin/model'),'sha256':manifest['bin/model']['sha256']}}}
Path(a.receipt).write_text(json.dumps(receipt));print(json.dumps(receipt))
'''

DOCKER = r'''#!/usr/bin/env python3
import base64,io,json,os,sys,tarfile,time
from pathlib import Path
state_path=Path(os.environ['FIXTURE_STATE']);s=json.loads(state_path.read_text());a=sys.argv[3:];case=os.environ['FIXTURE_CASE']
s['calls'].append(a)
def save():state_path.write_text(json.dumps(s))
def end(value='',code=0):
    save()
    if value:print(value)
    raise SystemExit(code)
def option(name):return a[a.index(name)+1]
def image_config():return {'Entrypoint':[],'Cmd':['/bin/true'],'User':'1000:1000','WorkingDir':'/work','Volumes':None,'Healthcheck':None,'OnBuild':None,'ExposedPorts':None,'Labels':{}}
if a[0]=='info':end('daemon-changed' if case=='daemon-change' and s.get('probe') else 'owned-daemon')
if a[0]=='version':end(json.dumps({'Client':{'Version':'synthetic'},'Server':{'Version':'synthetic'}}))
if a[:2]==['image','inspect']:
    key=a[2]
    if key==s['base_ref'] or key==s['base_id']:
        config=image_config()
        if case=='base-onbuild':config['OnBuild']=['RUN touch /forbidden-build-effect']
        if case=='base-volume':config['Volumes']={'/foreign':{}}
        if case=='base-healthcheck':config['Healthcheck']={'Test':['CMD','/bin/true']}
        if case=='base-port':config['ExposedPorts']={'80/tcp':{}}
        end(json.dumps([{'Id':s['base_id'],'Os':'linux','Architecture':'arm64' if case=='base-platform' else 'amd64',
            'RepoDigests':[s['base_ref']],'Config':config}]))
    if s.get('image') and key in (s['image']['Id'],s['tag']):end(json.dumps([s['image']]))
    end('not found',1)
if a[:2]==['image','ls']:
    ids=[s['base_id'],s['unrelated_image']]+([s['image']['Id']] if s.get('image') else [])
    if '--filter' in a:
        f=option('--filter')
        ids=([s['image']['Id']] if s.get('image') and (f.startswith('label=') or f.split('=',1)[-1] in s['image']['Id']) else [])
    end('\n'.join(ids))
if a[:2]==['container','ls']:
    ids=[s['unrelated_container']]+([s['probe']['Id']] if s.get('probe') else [])
    if '--filter' in a:ids=[x for x in ids if option('--filter').split('=',1)[-1] in x]
    end('\n'.join(ids))
if a[0]=='build':
    if case=='build-failure':end('owned build failure',1)
    s['tag']=option('--tag');label=option('--label');key,value=label.split('=',1)
    config=image_config();config['Labels']={key:('wrong' if case=='image-label' else value)}
    if case=='inherited-volume':config['Volumes']={'/foreign':{}}
    s['image']={'Id':'sha256:'+'b'*64,'Os':'linux','Architecture':'arm64' if case=='image-platform' else 'amd64',
        'Config':config,'RepoTags':[s['tag']]}
    s['context']=a[-1];Path(option('--iidfile')).write_text('sha256:'+'f'*64 if case=='iid-mismatch' else s['image']['Id']);save()
    if case=='build-response-lost-untagged':s['tag']='';end('',1)
    if case=='build-timeout':time.sleep(2)
    end('',1 if case=='build-response-lost' else 0)
if a[:2]==['container','create']:
    label=option('--label');key,value=label.split('=',1)
    s['probe']={'Id':'c'*64,'Name':'/'+option('--name'),'Image':s['image']['Id'],
        'Config':image_config(),'State':{'Running':False,'Status':'created','Pid':0},
        'HostConfig':{'NetworkMode':'none','ReadonlyRootfs':True,'Memory':268435456,'MemorySwap':268435456,
            'NanoCpus':1000000000,'PidsLimit':32,'Privileged':False,'Binds':None,'PortBindings':None,
            'CapDrop':['ALL'],'SecurityOpt':['no-new-privileges']},'Mounts':[]}
    s['probe']['Config']['Labels']={key:('wrong' if case=='probe-label' else value)}
    end(s['probe']['Id'],1 if case=='create-response-lost' else 0)
if a[:2]==['container','inspect']:
    if s.get('probe') and a[2] in (s['probe']['Id'],s['probe']['Name'].lstrip('/')):end(json.dumps([s['probe']]))
    end('not found',1)
if a[0]=='cp':
    root=Path(s['context'])/'runtime';out=io.BytesIO()
    with tarfile.open(fileobj=out,mode='w') as archive:
        for name in ('runtime','runtime/bin'):
            row=tarfile.TarInfo(name);row.type=tarfile.DIRTYPE;row.mode=0o755;archive.addfile(row)
        for file in sorted(root.rglob('*')):
            if not file.is_file():continue
            name='runtime/'+str(file.relative_to(root))
            if case=='missing-file' and name.endswith('bin/model'):continue
            data=file.read_bytes();row=tarfile.TarInfo(name);row.mode=file.stat().st_mode&0o777
            if name.endswith('bin/model'):
                if case=='changed-file':data+=b'x'
                if case=='mode':row.mode=0o777
                if case=='owner':row.uid=1000
                if case=='link':row.type=tarfile.SYMTYPE;row.linkname='/outside';archive.addfile(row);continue
            row.size=len(data);archive.addfile(row,io.BytesIO(data))
        if case=='extra-file':
            row=tarfile.TarInfo('runtime/extra');row.size=1;archive.addfile(row,io.BytesIO(b'x'))
    save();sys.stdout.buffer.write(out.getvalue());raise SystemExit(0)
if a[:2]==['container','rm']:
    if not s.get('probe') or a[-1]!=s['probe']['Id']:end('foreign removal',2)
    s['deleted'].append(s['probe']['Id']);s['probe']=None;end()
if a[:2]==['image','rm']:
    if not s.get('image') or a[-1]!=s['image']['Id'] or s.get('probe'):end('foreign removal',2)
    s['deleted'].append(s['image']['Id']);s['image']=None;end()
end('unsupported synthetic docker command: '+repr(a),2)
'''


def run(base):
    driver = ROOT / 'evals/native-qualification/smoke/check_model_image_docker_e2e.py'
    if not driver.exists():
        return {'status':'failed','classification':'synthetic_hosted_driver','checks':[
            {'name':'driver exists','passed':False,'error':'check_model_image_docker_e2e.py is not implemented'}]}
    repository = base / 'repository'; smoke=repository/'evals/native-qualification/smoke';smoke.mkdir(parents=True)
    shutil.copyfile(driver,smoke/driver.name)
    helpers=repository/'tools';helpers.mkdir()
    for name in ('engagement_contract.py','engagement_records.py','operator_signature.py'):
        shutil.copyfile(ROOT/'tools'/name,helpers/name)
    (helpers/'install_native_tools.py').write_text(INSTALLER)
    binaries=base/'bin';binaries.mkdir();(binaries/'docker').write_text(DOCKER);(binaries/'docker').chmod(0o700)
    wrapper=smoke/'invoke.py';wrapper.write_text('import os\nimport check_model_image_docker_e2e as driver\n'
        'driver.host_platform.system=lambda: "Darwin" if os.environ["FIXTURE_CASE"]=="non-linux" else "Linux"\n'
        'driver.host_platform.machine=lambda: "aarch64" if os.environ["FIXTURE_CASE"]=="host-platform" else "x86_64"\n'
        'driver.BUILD_TIMEOUT=0.1 if os.environ["FIXTURE_CASE"]=="build-timeout" else 10\n'
        'raise SystemExit(driver.main())\n')
    checks=[]
    cases=('codex','omp','non-linux','host-platform','base-tag','base-platform','base-onbuild','base-volume','base-healthcheck','base-port','existing-directory',
        'install-failure','build-failure','build-response-lost','build-response-lost-untagged','iid-mismatch','build-timeout','image-label','image-platform',
        'inherited-volume','create-response-lost','probe-label','daemon-change','changed-file','missing-file',
        'extra-file','mode','owner','link')
    for name in cases:
        folder=base/name;folder.mkdir();state=folder/'state.json';out=folder/'result.json';directory=folder/'artifacts'
        initial={'calls':[],'deleted':[],'base_ref':BASE,'base_id':'sha256:'+'a'*64,
            'unrelated_image':'sha256:'+'d'*64,'unrelated_container':'e'*64}
        state.write_text(json.dumps(initial))
        if name=='existing-directory':directory.mkdir();(directory/'keep').write_text('untouched')
        env={**os.environ,'PATH':str(binaries)+os.pathsep+os.environ['PATH'],'FIXTURE_STATE':str(state),'FIXTURE_CASE':name}
        args=[sys.executable,str(wrapper),'--runtime','omp' if name=='omp' else 'codex','--platform','linux/amd64',
              '--base-image','python:latest' if name=='base-tag' else BASE,'--endpoint','unix:///fixture.sock',
              '--directory',str(directory),'--output',str(out)]
        try:
            completed=subprocess.run(args,env=env,capture_output=True,text=True,timeout=15)
            result=json.loads(out.read_bytes()) if out.exists() else {}
            final=json.loads(state.read_bytes())
            detail={key:result.get(key) for key in ('status','error','cleanup')}
            assert completed.returncode==(0 if name in ('codex','omp') else 1),completed.stdout+completed.stderr
            assert result['status']==('passed' if name in ('codex','omp') else 'failed'),detail
            assert not any(a[0] in ('start','run','exec') or a[:2] in (['container','start'],['container','exec']) for a in final['calls'])
            assert initial['base_id'] not in final['deleted'] and initial['unrelated_image'] not in final['deleted']
            assert initial['unrelated_container'] not in final['deleted']
            if name in ('codex','omp'):
                assert result['cleanup']['status']=='clean',detail
                assert not final.get('image') and not final.get('probe')
                assert (directory/'context/runtime/bin/model').is_file(),'host executable not retained'
                assert (directory/'context-receipt.json').is_file()
            if name in ('non-linux','host-platform','base-tag','base-platform','base-onbuild','base-volume','base-healthcheck','base-port','existing-directory'):
                assert not (directory/'context').exists(),'acquisition before admission'
            if name=='existing-directory':assert (directory/'keep').read_text()=='untouched'
            if name in ('changed-file','missing-file','extra-file','mode','owner','link','image-platform','inherited-volume'):
                assert not final.get('image') and not final.get('probe'),detail
                assert result['cleanup']['status']=='clean',detail
            if name in ('image-label','probe-label','daemon-change','build-timeout','iid-mismatch','build-failure','build-response-lost','build-response-lost-untagged','create-response-lost'):
                assert result['cleanup']['status']=='unresolved',detail
            if name in ('build-response-lost','build-response-lost-untagged','create-response-lost'):
                assert not final.get('image') and not final.get('probe'),detail
            if name in ('base-onbuild','base-volume','base-healthcheck','base-port'):
                assert not any(a[0]=='build' for a in final['calls']),detail
            if name in ('image-label','probe-label','daemon-change','iid-mismatch'):assert not final['deleted'],detail
            checks.append({'name':name,'passed':True})
        except Exception as error:
            checks.append({'name':name,'passed':False,'error':str(error)})
    return {'status':'passed' if all(row['passed'] for row in checks) else 'failed',
        'classification':'synthetic_hosted_driver','checks':checks,'actual_docker_calls':0,
        'binary_downloads':0,'native_execution':'not_run',
        'source_sha256':'sha256:'+hashlib.sha256(driver.read_bytes()).hexdigest()}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    with tempfile.TemporaryDirectory(prefix='model-image-driver-fixture-') as root:result=run(Path(root).resolve())
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result));raise SystemExit(result['status']!='passed')
