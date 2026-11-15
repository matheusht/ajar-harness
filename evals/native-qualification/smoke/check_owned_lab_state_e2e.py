#!/usr/bin/env python3
"""Failure-first signed lab-state workflow, with explicitly simulated Docker peers.

No Docker, provider, research target or image download is used by this scenario.
The actual journal, controller, boundary startup/capture/recovery and local staging
filesystem are exercised. Physical Linux mount qualification is separate.
"""
from __future__ import annotations
import argparse
import copy
from contextlib import ExitStack
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
from engagement_contract import canonical, digest
from engagement_controller import Controller
from engagement_runner import WorkerContext, frozen_inputs
from research_environment import Environment
spec = importlib.util.spec_from_file_location('lab_boundary_fixture', Path(__file__).with_name('check_engagement_native_boundary_e2e.py'))
b = importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
require = b.require

def reject(call, contains=None):
    try:
        call()
    except Exception as error:
        code = getattr(error, 'code', str(error))
        require(not contains or contains in code, f'{code!r} does not contain {contains!r}')
        return code
    raise AssertionError('forbidden operation accepted')

def module():
    import engagement_lab_artifacts
    return engagement_lab_artifacts

def scope_with_artifact(scope):
    scope['access'][0]['permissions'] = ['read', 'write', 'execute']
    effect = copy.deepcopy(scope['effects'][0])
    effect.update(id='create-lab', kind='artifact_create', artifact_classes=['owned-lab-state-v1'], cleanup_required=True)
    execute = copy.deepcopy(effect); execute.update(id='execute-lab', kind='execute', artifact_classes=[])
    scope['effects'].extend([effect, execute])
    return scope

def case(path, *, start=True, mutate=None):
    source = b.fixture.fixture.fixture_scope
    def adjusted(inputs):
        result = scope_with_artifact(source(inputs))
        if mutate:
            mutate(result)
        return result
    with patch.object(b.fixture.fixture, 'fixture_scope', adjusted):
        return b.fixture.Case(path, start=start)

def initial(x, grant):
    env = Environment(x.contract.environment_profiles['lab-main'], x.contract.scope['environments'][0]['limits'],
        lambda: grant, lambda value: None, grant=grant, dispatch_guard=x.c.lock)
    env.identity['daemon_id'] = 'fixture-daemon'
    return env.receipt()

def allocation(x, grant, identity):
    identity = copy.deepcopy(identity)
    identity.update(container_id='a'*64, stage_container_id='b'*64, prepared_image_id='sha256:'+'c'*64,
        access=[{key: x.contract.scope['access'][0][key] for key in ('id', 'kind', 'identity')}])
    for phase in ('intent', 'result'):
        event = {'kind': 'environment-observation-v2', 'operation': 'start', 'operation_id': 'start-'+identity['nonce'],
            'phase': phase, 'identity': identity}
        if phase == 'result': event['status'] = 'settled'
        x.c.record_environment_observation(grant, 'lab-main', event, effect_id='read-source')
    return identity

def inventory(limits, uid=1000, gid=1000):
    cap = min(limits['workspace_bytes'], 64*1024*1024)
    def row(path, fs, *, writable=False, ro=False, size=0, mode=0o755, owner=0):
        return {'path': path, 'filesystem': fs, 'readonly': ro, 'writable': writable,
            'size_bytes': size, 'mode': mode, 'uid': owner, 'gid': owner,
            'kind': 'file' if path.startswith('/etc/') else 'directory', 'device': None}
    return {'uid': uid, 'gid': gid, 'mounts': [
        row('/', 'overlay', ro=True), row('/proc', 'proc'), row('/dev', 'tmpfs', size=64*1024*1024),
        row('/dev/pts','devpts'), row('/dev/mqueue','mqueue', writable=True, mode=0o1777),
        row('/dev/shm','tmpfs', writable=True, size=cap, mode=0o1777),
        row('/sys','sysfs',ro=True), row('/sys/fs/cgroup','cgroup2',ro=True),
        *[row('/etc/'+name,'ext4') for name in ('hosts','hostname','resolv.conf')],
        row('/work','tmpfs',writable=True,size=limits['workspace_bytes'],mode=0o700,owner=uid),
        row('/tmp','tmpfs',writable=True,size=cap,mode=0o700,owner=uid)],
        'namespaces': {name: f'{name}:[12345]' for name in ('ipc','pid','mnt','net','cgroup')}}


def configuration(identity, profile, limits):
    from engagement_lease_owner import guardian_command
    command=guardian_command(identity['nonce'],limits['lease_seconds'])
    host={'Init':False,'NetworkMode':'none','ReadonlyRootfs':True,'Privileged':False,'CapDrop':['ALL'],
        'SecurityOpt':['no-new-privileges=true'],'LogConfig':{'Type':'none'},'RestartPolicy':{'Name':'no'},
        'Memory':limits['memory_bytes'],'MemorySwap':limits['memory_bytes'],'NanoCpus':int(limits['cpu_count']*1e9),
        'PidsLimit':limits['pids'],'Binds':None,'PortBindings':{},
        'Tmpfs':{p:f"rw,nosuid,nodev,size={size},uid={profile['uid']},gid={profile['gid']},mode=0700"
            for p,size in (('/work',limits['workspace_bytes']),('/tmp',min(limits['workspace_bytes'],64*1024*1024)))},
        'IpcMode':'private','PidMode':'','UTSMode':'','CgroupnsMode':'private',
        'ShmSize':min(limits['workspace_bytes'],64*1024*1024),'Devices':[],'DeviceRequests':[],
        'DeviceCgroupRules':[],'CapAdd':[],'VolumesFrom':[],'Links':[],'ExtraHosts':[],
        'Sysctls':{},'MaskedPaths':['/proc/kcore','/proc/keys','/proc/timer_list'],
        'ReadonlyPaths':['/proc/sys','/proc/sysrq-trigger','/proc/irq','/proc/bus']}
    return {'HostConfig':host,'Config':{'Labels':{'io.oslit.guardian':'container-lease-v1',
        'io.oslit.engagement':identity['nonce'],'io.oslit.profile':identity['profile_sha256']},
        'User':'0:0','WorkingDir':'/','OpenStdin':True,'Entrypoint':[command[0]],'Cmd':command[1:]},
        'Image':identity['prepared_image_id'],'Path':command[0],'Args':command[1:],'Mounts':[]}

def ready_value(x, identity):
    profile = x.contract.environment_profiles['lab-main']
    return {'kind':'owned-lab-state-readback-v1', 'identity': identity,
        'inventory':inventory(x.contract.scope['environments'][0]['limits'],profile['uid'],profile['gid']),
        'configuration':configuration(identity,profile,x.contract.scope['environments'][0]['limits'])}

def clean(identity):
    return {'status':'clean','identity':copy.deepcopy(identity),'owned_workspace':'container_removed'}

def intended(x, grant):
    ident = initial(x, grant)
    x.c.record_lab_artifact_intent(grant, 'lab-main', 'create-lab', ident)
    return ident

def selection(path):
    m = module(); x = case(path); g=x.grant(resources=['source-main'])
    require(m.select_effect(x.contract.scope,g,'lab-main') == 'create-lab','signed class unavailable')
    scope=copy.deepcopy(x.contract.scope); scope['effects']=[r for r in scope['effects'] if r['kind']!='artifact_create']
    require(m.select_effect(scope,g,'lab-main') is None,'ordinary scope silently classified')
    unknown=copy.deepcopy(x.contract.scope);unknown['effects'][-2]['artifact_classes']=['unknown-v1']
    require(m.select_effect(unknown,g,'lab-main') is None,'unsupported class changed ordinary scope behavior')
    reject(lambda:m.select_effect(unknown,g,'lab-main','create-lab'),'lab_artifact')
    for mutate in (
        lambda s:s['effects'][-2].update(cleanup_required=False),
        lambda s:s['effects'][-2].update(account_refs=['account']),
        lambda s:s['effects'][-2].update(rung='stored'),
        lambda s:s['access'][0].update(kind='application'),
        lambda s:s['effects'].append(dict(s['effects'][-2],id='create-other'))):
        changed=copy.deepcopy(x.contract.scope); mutate(changed)
        reject(lambda:m.select_effect(changed,g,'lab-main'),'lab_artifact')
    reject(lambda:m.select_effect(x.contract.scope,g,'lab-main','execute-lab'),'lab_artifact')

def lifecycle(path):
    x=case(path); g=x.grant(resources=['source-main']); ident=intended(x,g); initial_identity=copy.deepcopy(ident)
    require(x.c.state()['lab_artifacts'][ident['nonce']]['state']=='intended','intent missing')
    reject(lambda:x.settle(g),'lab_artifact_cleanup')
    ident=allocation(x,g,ident); readback=ready_value(x,ident)
    x.c.record_lab_artifact_ready(g,'lab-main',readback)
    x.c.record_lab_artifact_ready(g,'lab-main',readback)
    x.c.record_lab_artifact_intent(g,'lab-main','create-lab',initial_identity)
    reopened=Controller(x.c.root)
    require(len(reopened.state()['lab_artifacts'])==1,'reopen duplicated artifact')
    require(reopened.state()['lab_artifacts'][ident['nonce']]['state']=='ready','ready not durable')
    x.settle(g,unknown=True)
    reject(lambda:x.c.reconcile(g['dispatch_id'], {'source-main':'reset'}, adapter_id=g['adapter_id']), 'lab_artifact_cleanup')
    x.c.record_environment_cleanup(g,'lab-main',clean(ident))
    x.c.record_lab_artifact_cleanup(g,'lab-main',clean(ident))
    x.c.record_lab_artifact_cleanup(g,'lab-main',clean(ident))
    x.settle(g)
    summary=x.c.status()['lab_state_artifacts']
    require(summary['count']==1 and summary['pending_cleanup']==0 and summary['retained_evidence_objects']>0,'honest status absent')
    require('files_created' not in summary,'per-file accounting invented')

def execution_separation(path):
    x=case(path);g=x.grant(resources=['source-main']);ident=intended(x,g);ident=allocation(x,g,ident)
    event={'kind':'environment-observation-v2','phase':'intent','operation':'execute',
        'operation_id':'execute-before-ready','identity':ident}
    reject(lambda:x.c.record_environment_observation(g,'lab-main',event,effect_id='execute-lab'),'lab_artifact')
    x.c.record_lab_artifact_ready(g,'lab-main',ready_value(x,ident))
    reject(lambda:x.c.record_environment_observation(g,'lab-main',event,effect_id='create-lab'),'artifact')
    reject(lambda:x.c.record_environment_observation(g,'lab-main',event,effect_id='read-source'),'lab_artifact')
    x.c.record_environment_observation(g,'lab-main',event,effect_id='execute-lab')
    x.c.revoke_worker('lead-1',1,reason='fixture-revoke')
    reject(lambda:x.c.record_environment_observation(g,'lab-main',dict(event,operation_id='after-revoke'),effect_id='execute-lab'))
    x.c.record_environment_cleanup(g,'lab-main',clean(ident));x.c.record_lab_artifact_cleanup(g,'lab-main',clean(ident))

def writable_inventory(path):
    m=module();x=case(path);profile=x.contract.environment_profiles['lab-main'];limits=x.contract.scope['environments'][0]['limits']
    good=inventory(limits,profile['uid'],profile['gid']);m.validate_inventory(good,profile,limits)
    mutations=[lambda v:v['mounts'].append(dict(v['mounts'][-1],path='/foreign')),
        lambda v:next(r for r in v['mounts'] if r['path']=='/dev/shm').update(size_bytes=2**60),
        lambda v:next(r for r in v['mounts'] if r['path']=='/etc/hosts').update(writable=True),
        lambda v:next(r for r in v['mounts'] if r['path']=='/').update(readonly=False),
        lambda v:next(r for r in v['mounts'] if r['path']=='/sys/fs/cgroup').update(readonly=False),
        lambda v:v['mounts'].remove(next(r for r in v['mounts'] if r['path']=='/dev/mqueue')),
        lambda v:next(r for r in v['mounts'] if r['path']=='/work').update(mode=0o777),
        lambda v:v.update(uid=0),lambda v:v['namespaces'].pop('ipc')]
    for change in mutations:
        bad=copy.deepcopy(good);change(bad);reject(lambda:m.validate_inventory(bad,profile,limits),'lab_artifact')

def staging(path):
    m=module();x=case(path);g=x.grant(resources=['source-main']);ident=intended(x,g);ident=allocation(x,g,ident)
    x.c.record_lab_artifact_ready(g,'lab-main',ready_value(x,ident))
    directory=x.c.root/'workers'/'fixture'/'capture-1';directory.mkdir(parents=True,mode=0o700)
    x.c.record_artifact_staging(g,ident['nonce'],directory,['capture/probe'])
    (directory/'capture').mkdir();(directory/'capture'/'probe').write_bytes(b'inert')
    x.c.record_environment_cleanup(g,'lab-main',clean(ident))
    reject(lambda:x.c.record_lab_artifact_cleanup(g,'lab-main',clean(ident)),'lab_artifact')
    (directory/'foreign').write_bytes(b'preserve')
    reject(lambda:m.cleanup_staging(x.c,g,ident['nonce']),'lab_artifact')
    require((directory/'foreign').read_bytes()==b'preserve','foreign contents deleted')
    (directory/'foreign').unlink()
    moved=directory.with_name('original');directory.rename(moved);directory.mkdir()
    reject(lambda:m.cleanup_staging(x.c,g,ident['nonce']),'lab_artifact')
    directory.rmdir();moved.rename(directory)
    m.cleanup_staging(x.c,g,ident['nonce']);require(not directory.exists(),'owned staging survived')
    x.c.record_lab_artifact_cleanup(g,'lab-main',clean(ident));x.settle(g)

def intent_recovery(path):
    x=case(path,start=False);workspace=x.workspace('lead-1')
    g=x.c.prepare_worker_dispatch('lead-1',1,workspace,seconds=30,resources=['source-main'],adapter_id='fixture-adapter')
    x.c.record_preparation_setup(g);ident=intended(x,g);x.c=Controller(x.c.root)
    x.c.revoke_worker('lead-1',1,reason='fixture-crash')
    stopped={'status':'absent','identity':ident}
    reject(lambda:x.c.settle_preparation(g,[],worker_seconds=1),'preparation_cleanup')
    reject(lambda:x.c.settle_preparation(g,[{'profile_id':'lab-main','environment':stopped,'cleanup':clean(ident)}],worker_seconds=1),'lab_artifact')
    x.c.record_environment_cleanup(g,'lab-main',clean(ident));x.c.record_lab_artifact_cleanup(g,'lab-main',clean(ident))
    x.c.settle_preparation(g,[{'profile_id':'lab-main','environment':stopped,'cleanup':clean(ident)}],worker_seconds=1)
    require(x.c.state()['dispatches'][g['dispatch_id']]['status']=='settled','intent-only crash not recovered')

def journal_trust(path):
    x=case(path);g=x.grant(resources=['source-main']);ident=intended(x,g)
    altered=copy.deepcopy(ident);altered['daemon_id']='foreign-daemon'
    reject(lambda:x.c.record_lab_artifact_intent(g,'lab-main','create-lab',altered),'environment_identity')
    wrong=dict(g,generation=2)
    reject(lambda:x.c.record_lab_artifact_intent(wrong,'lab-main','create-lab',ident))
    for name in ('lab_artifact_intent','lab_artifact_ready','lab_artifact_cleanup'):
        reject(lambda:x.request(name,{'nonce':ident['nonce']}))
    ident=allocation(x,g,ident);ready=ready_value(x,ident);ready['identity']=dict(ident,container_id='d'*64)
    reject(lambda:x.c.record_lab_artifact_ready(g,'lab-main',ready),'environment_identity')
    unresolved=copy.deepcopy(ident);unresolved['unsettled']=['snapshot_input']
    reject(lambda:x.c.record_lab_artifact_cleanup(g,'lab-main',clean(unresolved)))

def renewal(path):
    x=case(path);g=x.grant(resources=['source-main']);ident=intended(x,g);ident=allocation(x,g,ident)
    x.c.record_lab_artifact_ready(g,'lab-main',ready_value(x,ident))
    renewed=x.c.renew_dispatch(g,seconds=30)
    x.c.record_lab_artifact_ready(renewed,'lab-main',ready_value(x,ident))
    require(len(x.c.state()['lab_artifacts'])==1,'renewal created new allowance')
    x.c.record_environment_cleanup(renewed,'lab-main',clean(ident))
    x.c.record_lab_artifact_cleanup(renewed,'lab-main',clean(ident))

class LabEnvironment(b.SimulatedEnvironment):
    controller=None
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        if self.identity is None:
            original=Environment(*args,**{k:v for k,v in kwargs.items() if k!='lab_artifact'})
            self.identity=original.receipt();self.identity['daemon_id']='fixture-daemon'
    def allocation_identity(self):return self.receipt()
    def prepare(self,accesses,access_files,*,support_inputs):
        nonce=self.identity['nonce']
        require(self.controller.state()['lab_artifacts'][nonce]['state']=='intended','allocation before artifact intent')
        self.staged=copy.deepcopy(support_inputs);self.access_files=access_files
        self.identity.update(container_id='a'*64,stage_container_id='b'*64,prepared_image_id='sha256:'+'c'*64,
            access=[{k:r[k] for k in ('id','kind','identity')} for r in accesses],
            support_inputs=[{'id':n,'manifest_sha256':v['manifest_sha256']} for n,v in support_inputs.items()])
        common={'kind':'environment-observation-v2','operation':'start','operation_id':'start-'+nonce,'identity':self.receipt()}
        self.observe(dict(common,phase='intent'));self.running=True;self.observe(dict(common,phase='result',status='settled'))
        return {'status':'prepared','identity':self.receipt(),'inputs':{},'support_inputs':{}}
    def artifact_state_readback(self):
        return {'kind':'owned-lab-state-readback-v1','identity':self.receipt(),
            'inventory':inventory(self.limits,self.profile['uid'],self.profile['gid']),
            'configuration':configuration(self.receipt(),self.profile,self.limits)}

class LabRuntime(b.SimulatedRuntime):
    def __init__(self,*args,**kwargs):
        require(any(r['state']=='ready' for r in LabEnvironment.controller.state()['lab_artifacts'].values()),'native started before class ready')
        super().__init__(*args,**kwargs)

def boundary_flow(path):
    import engagement_native_boundary as boundary
    source=b.fixture.fixture.fixture_scope
    with patch.object(b.fixture.fixture,'fixture_scope',lambda inputs:scope_with_artifact(source(inputs))):
        _,x,context,stack=b.simulated_boundary(path)
    with stack:
        stack.enter_context(patch.object(boundary,'Environment',LabEnvironment))
        stack.enter_context(patch.object(boundary.codex,'Runtime',LabRuntime))
        LabEnvironment.controller=x.c;LabEnvironment.instances=[]
        owner=boundary.NativeBoundary(context);owner.start()
        require(len(x.c.state()['lab_artifacts'])==1,'main lab missing')
        x.c.record_worker_started('lead-1',1,owner.runtime.session_id,context.workspace,owner_receipt=owner.owner_receipt)
        x.c.revoke_worker('lead-1',1,reason='fixture-finish')
        result=owner.finish();require(result['cleanup']=='verified','boundary artifact cleanup failed')
        require(all(r['state']=='clean' for r in x.c.state()['lab_artifacts'].values()),'boundary did not settle artifact')

def existing(path):
    b.lifecycle(path)


def retained_specialist(path):
    spec=importlib.util.spec_from_file_location('retained_lab_fixture',Path(__file__).with_name('check_engagement_retained_specialist_e2e.py'))
    retained=importlib.util.module_from_spec(spec);spec.loader.exec_module(retained)
    source=retained.fixture.fixture_scope
    with patch.object(retained.fixture,'fixture_scope',lambda inputs:scope_with_artifact(source(inputs))):
        x=retained.Workflow(path)
    ident=intended(x,x.g);ident=allocation(x,x.g,ident)
    x.c.record_lab_artifact_ready(x.g,'lab-main',ready_value(x,ident))
    x.outcome();continued=x.c.continue_specialist(x.g)
    require(continued is not None,'class prevented valid retention')
    x.c.record_lab_artifact_ready(continued,'lab-main',ready_value(x,ident))
    require(len(x.c.state()['lab_artifacts'])==1 and x.c.state()['lab_artifacts'][ident['nonce']]['state']=='ready',
        'retention re-created or cleaned the live artifact')

def capture_order(path):
    import engagement_native_boundary as boundary
    source=b.fixture.fixture.fixture_scope
    with patch.object(b.fixture.fixture,'fixture_scope',lambda inputs:scope_with_artifact(source(inputs))):
        _,x,context,stack=b.simulated_boundary(path)
    with stack:
        stack.enter_context(patch.object(boundary,'Environment',LabEnvironment))
        stack.enter_context(patch.object(boundary.codex,'Runtime',LabRuntime))
        LabEnvironment.controller=x.c;LabEnvironment.instances=[]
        owner=boundary.NativeBoundary(context);started=owner.start()
        x.c.record_worker_started('lead-1',1,started['session_id'],context.workspace,owner_receipt=started['owner_receipt'])
        x.instrument();LabEnvironment.native_files={'candidate.txt':b'inert','probe.py':b'print("inert output")\n'}
        args={'instrument_id':'instrument-1','candidate_path':'candidate.txt','probe_path':'probe.py',
            'interpreter':'python3','arguments':[],'conditions':{},'seconds':10,'patch_id':None,'patch_arm':None,
            'effect_id':'execute-lab','artifact_effect_id':'create-lab'}
        original=x.c.adopt_receipt
        def adopt(dispatch_id,*a,**kw):
            for row in x.c.state()['lab_artifacts'].values():
                if row['dispatch_id']==dispatch_id:
                    require(row['state']=='clean','settlement before artifact cleanup')
                    require(all(not Path(v['path']).exists() for v in row['staging']),'settlement before host staging absence')
            return original(dispatch_id,*a,**kw)
        with patch.object(x.c,'adopt_receipt',adopt):
            response=owner.host_call('engagement_capture',args).wait()
        require(not response.get('isError'),'capture failed: '+str(response))
        value=json.loads(response['content'][0]['text']);require(value['status']=='captured','capture unavailable')
        require(len(x.c.state()['lab_artifacts'])==2,'capture reused main artifact')
        owner.finish()


def namespace_configuration(path):
    m=module();x=case(path);limits=x.contract.scope['environments'][0]['limits']
    good={'HostConfig':{'IpcMode':'private','PidMode':'','UTSMode':'','CgroupnsMode':'private',
        'ShmSize':min(limits['workspace_bytes'],64*1024*1024),'Devices':[],'DeviceRequests':[],
        'DeviceCgroupRules':[],'CapAdd':[],'VolumesFrom':[],'Links':[],'ExtraHosts':[],
        'Sysctls':{},'MaskedPaths':['/proc/kcore','/proc/keys','/proc/timer_list'],
        'ReadonlyPaths':['/proc/sys','/proc/sysrq-trigger','/proc/irq','/proc/bus']}}
    m.validate_configuration(good,limits)
    for key,value in [('IpcMode','host'),('IpcMode','container:foreign'),('PidMode','host'),
        ('CgroupnsMode','host'),('UTSMode','host'),('ShmSize',2**60),('CapAdd',['SYS_ADMIN']),
        ('Devices',[{'PathOnHost':'/dev/sda'}]),('DeviceRequests',[{}]),('Sysctls',{'kernel.foo':'1'}),
        ('MaskedPaths',[]),('ReadonlyPaths',[])]:
        changed=copy.deepcopy(good);changed['HostConfig'][key]=value
        reject(lambda:m.validate_configuration(changed,limits),'lab_artifact')


def interrupted_workflows(path):
    import engagement_native_boundary as boundary
    import shutil
    source=b.fixture.fixture.fixture_scope
    for phase in ('intent','stage-response-loss','image-response-loss','before-ready','after-ready','native-write','cleanup-response-loss'):
        root=path/phase;root.mkdir()
        with patch.object(b.fixture.fixture,'fixture_scope',lambda inputs:scope_with_artifact(source(inputs))):
            _,x,context,stack=b.simulated_boundary(root)
        with stack:
            class InterruptedEnvironment(LabEnvironment):
                failure=phase
                cleanup_failed=False
                def prepare(self,accesses,access_files,*,support_inputs):
                    if phase in ('intent','stage-response-loss','image-response-loss'):
                        if phase=='intent':raise ValueError('fixture-after-artifact-intent')
                        self.identity.update(access=[{k:r[k] for k in ('id','kind','identity')} for r in accesses],
                            support_inputs=[{'id':n,'manifest_sha256':v['manifest_sha256']} for n,v in support_inputs.items()])
                        if phase=='image-response-loss':self.identity['stage_container_id']='b'*64
                        operation='create_stage' if phase=='stage-response-loss' else 'snapshot_input'
                        self.identity['unsettled']=[operation]
                        event={'kind':'environment-observation-v2','operation':operation,'operation_id':operation+'-fault',
                            'identity':self.receipt()}
                        self.observe(dict(event,phase='intent'));self.observe(dict(event,phase='result',status='unknown'))
                        raise ValueError('fixture-allocation-acknowledgment-lost')
                    super().prepare(accesses,access_files,support_inputs=support_inputs)
                    if phase=='before-ready':raise ValueError('fixture-before-ready')
                def cleanup(self):
                    if phase=='cleanup-response-loss' and not self.__class__.cleanup_failed:
                        self.__class__.cleanup_failed=True
                        raise ValueError('fixture-cleanup-response-lost')
                    if self.identity['unsettled']:
                        self.identity['stage_container_id']='b'*64
                        if phase=='image-response-loss':self.identity['prepared_image_id']='sha256:'+'c'*64
                        self.identity['unsettled']=[]
                        event={'kind':'environment-observation-v2','operation':'remove_stage','operation_id':'exact-stage-cleanup',
                            'identity':self.receipt()}
                        self.observe(dict(event,phase='intent'));self.observe(dict(event,phase='result',status='settled'))
                    return super().cleanup()
            stack.enter_context(patch.object(boundary,'Environment',InterruptedEnvironment))
            stack.enter_context(patch.object(boundary.codex,'Runtime',LabRuntime))
            LabEnvironment.controller=x.c;InterruptedEnvironment.instances=[]
            original=x.c.record_lab_artifact_ready
            if phase=='after-ready':
                def after_ready(*a,**kw):original(*a,**kw);raise ValueError('fixture-after-ready')
                stack.enter_context(patch.object(x.c,'record_lab_artifact_ready',after_ready))
            owner=boundary.NativeBoundary(context)
            if phase in ('native-write','cleanup-response-loss'):
                started=owner.start()
                x.c.record_worker_started('lead-1',1,started['session_id'],context.workspace,owner_receipt=started['owner_receipt'])
                if phase=='native-write':
                    value=owner.environment.execute(['python3','-c','print("inert first write observation")'],timeout_seconds=2)
                    require(value['status']=='settled','first native operation absent')
                def recovered(receipt,**options):
                    return {'session_id':receipt['session_id'],'process_exited':True,'child_absence':'verified','capabilities_revoked':True}
                stack.enter_context(patch.object(boundary,'_recover_owner',recovered))
            else:
                reject(owner.start)
                require(not LabRuntime.instances,'native owner ran during failed setup')
            for gate in (owner.provider_gate,owner.lab_gate):
                if gate is not None:gate.close()
            x.c.revoke_worker('lead-1',1,reason='fixture-process-loss')
            reopened=Controller(x.c.root);context.runner.controller=reopened;context.runner.contract=frozen_inputs(reopened)
            dispatch=reopened.state()['dispatches'][context.grant['dispatch_id']]
            result=boundary.recover_boundary(context,dispatch)
            if phase=='cleanup-response-loss':
                require(result['status']=='unknown' and any(row['state']!='clean' for row in reopened.state()['lab_artifacts'].values()),
                    'lost cleanup response settled the artifact')
                result=boundary.recover_boundary(context,dispatch)
            require(result['status']=='settled',phase+': '+str(result))
            state=reopened.state()
            require(all(row['state']=='clean' for row in state['lab_artifacts'].values()) and not state['resource_holds'],
                'exact recovery retained/released the wrong obligation')
            require(state['usage']['invocations']==(1 if phase in ('native-write','cleanup-response-loss') else 0),
                'native invocation refund incorrect')
            for directory in (owner.socket_dir,owner.state_dir):
                if directory and directory.exists():shutil.rmtree(directory)

CASES={'signed_selection':selection,'journal_lifecycle':lifecycle,'separate_execution':execution_separation,
    'namespace_configuration':namespace_configuration,'complete_writable_inventory':writable_inventory,'host_staging_cleanup':staging,
    'intent_only_recovery':intent_recovery,'journal_trust':journal_trust,
    'renewal_preserves_artifact':renewal,'native_boundary_order':boundary_flow,'retained_specialist':retained_specialist,'capture_cleanup_order':capture_order,'interrupted_workflows':interrupted_workflows,'existing_without_class':existing}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    results=[]
    with tempfile.TemporaryDirectory(prefix='oslit-lab-state-e2e-') as directory:
        for name,run in CASES.items():
            path=Path(directory).resolve()/name;path.mkdir()
            try:run(path);results.append({'case':name,'status':'passed'})
            except Exception as error:results.append({'case':name,'status':'failed','error':f'{type(error).__name__}: {error}'})
    report={'kind':'owned-lab-state-contained-e2e-v1','evidence_class':'engineering_simulation',
        'docker_contacted':False,'provider_contacted':False,'physical_mount_qualification':False,
        'passed':all(row['status']=='passed' for row in results),'results':results}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2));return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
