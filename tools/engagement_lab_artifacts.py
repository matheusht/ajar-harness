"""Host-observed lifecycle of explicitly signed disposable lab state artifacts.

One artifact is the complete owned lab instance, not each file created inside it.
This module neither classifies content nor grants execution or external authority.
"""
from __future__ import annotations
import os
from pathlib import Path
import re
import shutil
import stat

from engagement_contract import canonical, read_json
from engagement_controller import fail

CLASS = 'owned-lab-state-v1'
CONFIG_FIELDS = ('Init', 'NetworkMode', 'ReadonlyRootfs', 'Privileged', 'CapDrop', 'SecurityOpt',
    'LogConfig', 'RestartPolicy', 'Memory', 'MemorySwap', 'NanoCpus', 'PidsLimit', 'Binds', 'PortBindings',
    'Tmpfs', 'IpcMode', 'PidMode', 'UTSMode', 'CgroupnsMode', 'ShmSize', 'Devices', 'DeviceRequests',
    'DeviceCgroupRules', 'CapAdd', 'VolumesFrom', 'Links', 'ExtraHosts', 'Sysctls', 'MaskedPaths', 'ReadonlyPaths')


def configuration_snapshot(info):
    return {'HostConfig': {key: info['HostConfig'].get(key) for key in CONFIG_FIELDS},
        'Config': {**{key: info['Config'][key] for key in ('User', 'WorkingDir', 'OpenStdin', 'Entrypoint', 'Cmd')},
            'Labels': {key: info['Config']['Labels'][key] for key in
                ('io.oslit.engagement', 'io.oslit.profile', 'io.oslit.guardian') if key in info['Config']['Labels']}},
        **{key: info[key] for key in ('Image', 'Path', 'Args', 'Mounts')}}

def select_effect(scope, grant, profile_id, selector=None):
    effects = [row for row in scope['effects'] if row['kind'] == 'artifact_create'
        and profile_id in row['environment_ids'] and set(grant['resources']) <= set(row['access_ids'])]
    if selector is None:
        effects = [row for row in effects if CLASS in row['artifact_classes']]
        if not effects:
            return None
    else:
        effects = [row for row in effects if row['id'] == selector]
    resources = [row for row in scope['access'] if row['id'] in grant['resources']]
    if (len(effects) != 1 or not resources or any(row['kind'] not in ('source', 'binary') or row['account_refs'] for row in resources)):
        fail('lab_artifact_effect_unavailable')
    effect = effects[0]
    if (effect['artifact_classes'] != [CLASS] or effect['account_refs'] or not effect['cleanup_required']
            or effect['rung'] not in ('source_only', 'self')):
        fail('lab_artifact_class_unsupported')
    return effect['id']


def execute_effect(scope, grant, profile_id):
    effects = [row for row in scope['effects'] if row['kind'] == 'execute'
        and profile_id in row['environment_ids'] and set(grant['resources']) <= set(row['access_ids'])
        and not row['account_refs'] and row['rung'] in ('source_only', 'self')]
    if len(effects) != 1:
        fail('lab_artifact_execute_effect_unavailable')
    return effects[0]['id']


def storage_policy(limits):
    if limits['workspace_bytes'] < 4096 or limits['workspace_bytes'] % 4096:
        fail('lab_artifact_storage_limit_unsupported')
    return {'work_bytes': limits['workspace_bytes'], 'tmp_bytes': min(limits['workspace_bytes'], 64*1024*1024),
        'shm_bytes': min(limits['workspace_bytes'], 64*1024*1024), 'dev_bytes': 64*1024*1024,
        'memory_bytes': limits['memory_bytes'], 'pids': limits['pids']}


def validate_configuration(info, limits):
    host = info.get('HostConfig', {})
    if (host.get('IpcMode') != 'private' or host.get('PidMode') != '' or host.get('UTSMode') != ''
            or host.get('CgroupnsMode') != 'private' or host.get('ShmSize') != storage_policy(limits)['shm_bytes']
            or any(host.get(name) for name in ('Devices', 'DeviceRequests', 'DeviceCgroupRules', 'CapAdd',
                'VolumesFrom', 'Links', 'ExtraHosts', 'Sysctls'))
            or not {'/proc/kcore', '/proc/keys', '/proc/timer_list'} <= set(host.get('MaskedPaths') or [])
            or not {'/proc/sys', '/proc/sysrq-trigger', '/proc/irq', '/proc/bus'} <= set(host.get('ReadonlyPaths') or [])):
        fail('lab_artifact_namespace_unverified')


def validate_inventory(value, profile, limits):
    policy = storage_policy(limits)
    required = {'/', '/work', '/tmp', '/dev', '/dev/shm', '/dev/pts', '/dev/mqueue', '/proc',
        '/sys', '/sys/fs/cgroup', '/etc/hosts', '/etc/hostname', '/etc/resolv.conf'}
    try:
        if (set(value) != {'uid', 'gid', 'mounts', 'namespaces'}
                or type(value['uid']) is not int or type(value['gid']) is not int
                or value['uid'] != profile['uid']
                or value['gid'] != profile['gid'] or value['uid'] == 0 or not isinstance(value['mounts'], list)
                or not 13 <= len(value['mounts']) <= 128 or type(value['namespaces']) is not dict
                or set(value['namespaces']) != {'ipc', 'pid', 'mnt', 'net', 'cgroup'}
                or any(not re.fullmatch(name + r':\[[0-9]+\]', item) for name, item in value['namespaces'].items())):
            raise ValueError()
        observed = set()
        for row in value['mounts']:
            if set(row) != {'path','filesystem','readonly','writable','size_bytes','mode','uid','gid','kind','device'}:
                raise ValueError()
            path = row['path']
            if (not isinstance(path, str) or path in observed or not path.startswith('/')
                    or type(row['readonly']) is not bool or type(row['writable']) is not bool
                    or any(type(row[k]) is not int or row[k] < 0 for k in ('size_bytes','mode','uid','gid'))):
                raise ValueError()
            observed.add(path)
            if path in required and (row['kind'] != ('file' if path.startswith('/etc/') else 'directory') or row['device'] is not None):
                raise ValueError()
            if path in ('/work', '/tmp', '/dev/shm', '/dev'):
                size = policy[{'/work':'work_bytes','/tmp':'tmp_bytes','/dev/shm':'shm_bytes','/dev':'dev_bytes'}[path]]
                if row['filesystem'] != 'tmpfs' or row['size_bytes'] != size or row['readonly']:
                    raise ValueError()
                if path in ('/work','/tmp') and (not row['writable'] or row['uid'] != profile['uid']
                        or row['gid'] != profile['gid'] or row['mode'] != 0o700):
                    raise ValueError()
                if path == '/dev' and (row['writable'] or row['uid'] != 0):
                    raise ValueError()
                if path == '/dev/shm' and (not row['writable'] or row['mode'] != 0o1777):
                    raise ValueError()
            elif path == '/dev/mqueue':
                if row['filesystem'] != 'mqueue' or row['readonly'] or not row['writable'] or row['mode'] != 0o1777:
                    raise ValueError()
            elif path == '/dev/pts':
                if row['filesystem'] != 'devpts' or row['writable']:
                    raise ValueError()
            elif path in ('/', '/sys', '/sys/fs/cgroup'):
                if not row['readonly'] or row['writable']:
                    raise ValueError()
                if path == '/sys' and row['filesystem'] != 'sysfs':
                    raise ValueError()
                if path == '/sys/fs/cgroup' and row['filesystem'] not in ('cgroup','cgroup2'):
                    raise ValueError()
            elif path == '/proc':
                if row['filesystem'] != 'proc' or row['writable']:
                    raise ValueError()
            elif path in ('/etc/hosts','/etc/hostname','/etc/resolv.conf'):
                if row['writable'] or row['uid'] != 0 or row['mode'] & 0o022:
                    raise ValueError()
            elif path.startswith('/proc/') or path.startswith('/sys/'):
                # Docker's read-only kernel submounts and masked /dev/null bindings.
                masked = (path in ('/proc/interrupts','/proc/kcore','/proc/keys','/proc/latency_stats','/proc/timer_list')
                    and row['filesystem']=='tmpfs' and row['kind']=='character' and row['device']=='1:3')
                if not masked and (row['writable'] or not row['readonly']):
                    raise ValueError()
            else:
                raise ValueError()
        if not required <= observed:
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        fail('lab_artifact_storage_unverified')


def _owner(c, state, grant, nonce):
    c.bind_grant(state, grant)
    row = state['lab_artifacts'].get(nonce)
    if row is None or any(row[key] != grant[key] for key in ('dispatch_id', 'worker_id', 'generation', 'profile_id', 'resources', 'scope_sha256', 'adapter_id')):
        fail('lab_artifact_owner_mismatch')
    return row


def _record(c, action, data):
    sha = c.store_object(canonical(data))
    return c._host('evidence_recorded', {'action': action, 'data': data, '_objects': [sha]})


def record_intent(c, grant, profile_id, effect_id, value):
    from engagement_evidence import identity
    with c.lock():
        state = c.state()
        c.bind_grant(state, grant)
        if select_effect(state['scope'], grant, profile_id, effect_id) != effect_id:
            fail('lab_artifact_effect_unavailable')
        reference = next(row for row in state['scope']['environments'] if row['profile_id'] == profile_id)
        if not isinstance(value, dict) or not isinstance(value.get('nonce'), str):
            fail('environment_identity_invalid')
        nonce = value['nonce']
        prior = state['lab_artifacts'].get(nonce)
        data = {key: grant[key] for key in ('dispatch_id', 'worker_id', 'generation', 'profile_id', 'resources', 'scope_sha256', 'adapter_id')}
        data.update(nonce=nonce, environment_profile_id=profile_id, artifact_class=CLASS, effect_id=effect_id,
            identity=value, policy=storage_policy(reference['limits']))
        if prior:
            _owner(c, state, grant, nonce)
            if prior['identity'] != value:
                fail('environment_identity_changed')
            if any(prior[key] != item for key, item in data.items()):
                fail('lab_artifact_intent_changed')
            return {'status': 'recorded'}
        c._authorize(state, grant)
        identity(c, state, grant, profile_id, value)
        if (nonce in state['environments'] or value['unsettled'] or
                any(value[key] is not None for key in ('container_id', 'stage_container_id', 'prepared_image_id'))):
            fail('lab_artifact_intent_too_late')
        return _record(c, 'lab_artifact_intended', data)


def record_ready(c, grant, profile_id, readback):
    from engagement_evidence import identity
    from research_environment import Environment
    with c.lock():
        state = c.state()
        if (not isinstance(readback, dict) or set(readback) != {'kind', 'identity', 'inventory', 'configuration'}
                or readback['kind'] != 'owned-lab-state-readback-v1'):
            fail('lab_artifact_readback_invalid')
        value = readback['identity']
        reference = identity(c, state, grant, profile_id, value)
        row = _owner(c, state, grant, value['nonce'])
        if row.get('ready') == readback:
            return {'status': 'recorded'}
        c._authorize(state, grant)
        if (row['environment_profile_id'] != profile_id or row['state'] == 'clean' or value['unsettled']
                or any(value[key] is None for key in ('container_id', 'stage_container_id', 'prepared_image_id'))
                or state['environments'].get(value['nonce'], {}).get('allocation_pending', True)):
            fail('lab_artifact_readback_invalid')
        if row.get('ready') is not None:
            fail('lab_artifact_readback_changed')
        profile = read_json(c.root / 'contract/environments' / (profile_id + '.json'), private=True)
        verifier = Environment(profile, reference['limits'], lambda: False, lambda value: None,
            receipt=value, lab_artifact=True)
        verifier._verify_configuration(readback['configuration'])
        validate_inventory(readback['inventory'], profile, reference['limits'])
        return _record(c, 'lab_artifact_ready', {'nonce': value['nonce'], 'readback': readback})


def record_staging(c, grant, nonce, path, paths):
    with c.lock():
        state = c.state()
        c._authorize(state, grant)
        row = _owner(c, state, grant, nonce)
        if row['state'] == 'clean':
            fail('lab_artifact_staging_invalid')
        directory = Path(path)
        try:
            info = directory.lstat()
            if (directory.resolve(strict=True) != directory or not directory.is_relative_to(c.root / 'workers')
                    or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700
                    or not isinstance(paths, list) or len(paths) > 10000 or len(paths) != len(set(paths))
                    or any(not isinstance(name, str) or not name or Path(name).is_absolute()
                        or '..' in Path(name).parts for name in paths)):
                raise ValueError()
        except (OSError, ValueError, TypeError):
            fail('lab_artifact_staging_invalid')
        owner = {'path': str(directory), 'device': info.st_dev, 'inode': info.st_ino, 'paths': sorted(paths)}
        prior = next((item for item in row['staging'] if item['path'] == owner['path']), None)
        if prior == owner:
            return {'status': 'recorded'}
        if prior is not None:
            fail('lab_artifact_staging_conflict')
        if any(directory.iterdir()):
            fail('lab_artifact_staging_invalid')
        return _record(c, 'lab_artifact_staging', {'nonce': nonce, 'owner': owner})


def cleanup_staging(c, grant, nonce):
    with c.lock():
        row = _owner(c, c.state(), grant, nonce)
        for owner in row['staging']:
            directory = Path(owner['path'])
            if not directory.exists() and not directory.is_symlink():
                continue
            try:
                info = directory.lstat()
                if (directory.resolve(strict=True) != directory or not stat.S_ISDIR(info.st_mode)
                        or (info.st_dev, info.st_ino) != (owner['device'], owner['inode'])):
                    raise ValueError()
                allowed = set(owner['paths'])
                parents = {str(parent) for name in allowed for parent in Path(name).parents if str(parent) != '.'}
                for path in directory.rglob('*'):
                    item = path.lstat()
                    name = str(path.relative_to(directory))
                    if not ((stat.S_ISREG(item.st_mode) and name in allowed and item.st_nlink == 1)
                            or (stat.S_ISDIR(item.st_mode) and name in parents)):
                        raise ValueError()
                shutil.rmtree(directory)
                if directory.exists() or directory.is_symlink():
                    raise ValueError()
            except (OSError, ValueError):
                fail('lab_artifact_staging_cleanup_unverified')


def record_cleanup(c, grant, profile_id, readback):
    from engagement_evidence import identity
    with c.lock():
        state = c.state()
        if (not isinstance(readback, dict) or set(readback) != {'status', 'identity', 'owned_workspace'}
                or readback['status'] != 'clean' or readback['owned_workspace'] != 'container_removed'):
            fail('lab_artifact_cleanup_unverified')
        value = readback['identity']
        identity(c, state, grant, profile_id, value)
        row = _owner(c, state, grant, value['nonce'])
        if (row['environment_profile_id'] != profile_id or value['unsettled']
                or state['environments'][value['nonce']].get('cleanup') != 'verified'
                or any(Path(owner['path']).exists() or Path(owner['path']).is_symlink() for owner in row['staging'])):
            fail('lab_artifact_cleanup_unverified')
        if row['state'] == 'clean':
            return {'status': 'recorded'}
        return _record(c, 'lab_artifact_cleanup_observed', {'nonce': value['nonce'], 'readback': readback})


def require_clean(state, dispatch_id):
    if any(row['dispatch_id'] == dispatch_id and row['state'] != 'clean' for row in state['lab_artifacts'].values()):
        fail('lab_artifact_cleanup_unverified')


def admit_operation(state, grant, profile_id, observation, effect):
    op, nonce = observation['operation'], observation['identity']['nonce']
    row = state['lab_artifacts'].get(nonce)
    if select_effect(state['scope'], grant, profile_id, row['effect_id'] if row else None) is None:
        return
    if row is None or row['dispatch_id'] != grant['dispatch_id'] or row['state'] == 'clean':
        fail('lab_artifact_intent_missing')
    if op == 'execute' or (op == 'launch_stdio' and observation.get('role') == 'native_tools'):
        if row['state'] != 'ready' or effect['kind'] != 'execute':
            fail('lab_artifact_execute_unavailable')
