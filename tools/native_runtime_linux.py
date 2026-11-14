"""Private Linux model container; the lab remains the only target/tool environment."""
from __future__ import annotations

import copy
from contextlib import nullcontext
import json
import os
from pathlib import Path, PurePosixPath
import re
import select
import struct
import sys
from types import SimpleNamespace

from engagement_contract import canonical, digest, read_bytes, safe_publication, source_manifest, validate_model_host
from native_runtime_bootstrap import CONFIGS, MAX_BOOTSTRAP, MODEL, STATE, WORKSPACE
from native_runtime_transport import RuntimeError, write_pipe
from research_environment import Environment

BOUNDARY = 'linux-docker-model-v1'
OWNER_KIND = 'native-runtime-owner-v2'
CONTROL_BYTES = 4 * 1024 * 1024
ENVIRONMENT_KEYS = {'kind', 'nonce', 'container_id', 'container_name', 'stage_container_id',
    'stage_container_name', 'prepared_image_id', 'prepared_image_name', 'unsettled',
    'daemon_id', 'image_id', 'profile_sha256', 'access', 'support_inputs'}


def environment_profile(profile):
    host = validate_model_host(profile['model_host'])
    return {'kind': 'research-environment-profile-v2', 'transport': 'docker',
        **{key: host[key] for key in ('docker_binary', 'docker_endpoint', 'daemon_id', 'image_id',
                                     'platform', 'uid', 'gid')}, 'ssh': None}


def environment_digest(profile):
    return digest(json.dumps(profile, sort_keys=True, separators=(',', ':')).encode())


def configuration_digest(profile, maximum_lease_seconds):
    return digest(canonical({'boundary': BOUNDARY, 'runtime': profile['kind'],
        'model_host': profile['model_host'], 'model_sha256': profile['executable']['sha256'],
        'config_sha256': profile['config_sha256'],
        'model_catalog_sha256': profile.get('model_catalog', {}).get('sha256'),
        'maximum_lease_seconds': maximum_lease_seconds}))


def _integer(value, minimum=1):
    return type(value) is int and value >= minimum


def _sha(value):
    return isinstance(value, str) and re.fullmatch(r'sha256:[0-9a-f]{64}', value) is not None


def validate_receipt(receipt, profile, *, profile_sha256, maximum_lease_seconds, grant=None, preparing=False):
    """Validate public ownership bytes against the signed runtime and dispatch."""
    try:
        if (not isinstance(receipt, dict) or set(receipt) != {'kind', 'runtime', 'session_id',
                'profile_sha256', 'boundary', 'owner'} or receipt['kind'] != OWNER_KIND
                or receipt['runtime'] != profile['kind'] or receipt['profile_sha256'] != profile_sha256
                or receipt['boundary'] != BOUNDARY or not _sha(profile_sha256)
                or receipt['session_id'] is not None and (not isinstance(receipt['session_id'], str)
                    or not 1 <= len(receipt['session_id']) <= 256)):
            raise ValueError()
        owner = receipt['owner']
        if (not isinstance(owner, dict) or set(owner) != {'phase', 'dispatch_id', 'worker_id', 'generation',
                'scope_sha256', 'environment', 'configuration_sha256', 'host', 'init', 'cgroup'}
                or owner['phase'] not in ('intended', 'created', 'running')
                or not preparing and owner['phase'] != 'running'
                or not _integer(owner['generation']) or not _sha(owner['scope_sha256'])
                or owner['configuration_sha256'] != configuration_digest(profile, maximum_lease_seconds)):
            raise ValueError()
        for key in ('dispatch_id', 'worker_id'):
            if not isinstance(owner[key], str) or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}', owner[key]):
                raise ValueError()
        if grant is not None and any(owner[key] != grant[key] for key in
                                      ('dispatch_id', 'worker_id', 'generation', 'scope_sha256')):
            raise ValueError()
        host = owner['host']
        if (not isinstance(host, dict) or set(host) != {'id_sha256', 'boot_id'} or not _sha(host['id_sha256'])
                or not isinstance(host['boot_id'], str)
                or not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', host['boot_id'])):
            raise ValueError()
        env = owner['environment']; expected = environment_profile(profile)
        if (not isinstance(env, dict) or set(env) != ENVIRONMENT_KEYS
                or env['kind'] != 'research-environment-receipt-v2' or env['access'] != []
                or not isinstance(env['nonce'], str) or not re.fullmatch('[0-9a-f]{32}', env['nonce'])
                or env['container_name'] != 'oslit-' + env['nonce']
                or env['stage_container_name'] != 'oslit-' + env['nonce'] + '-stage'
                or env['prepared_image_name'] != 'oslit-input-' + env['nonce'] + ':latest'
                or env['daemon_id'] != expected['daemon_id'] or env['image_id'] != expected['image_id']
                or env['profile_sha256'] != environment_digest(expected)
                or not isinstance(env['unsettled'], list) or len(env['unsettled']) != len(set(env['unsettled']))
                or set(env['unsettled']) - {'create_stage', 'snapshot_input', 'create'}):
            raise ValueError()
        for key in ('container_id', 'stage_container_id', 'prepared_image_id'):
            pattern = r'sha256:[0-9a-f]{64}' if key == 'prepared_image_id' else r'[0-9a-f]{64}'
            if env[key] is not None and (not isinstance(env[key], str) or not re.fullmatch(pattern, env[key])):
                raise ValueError()
        if env['prepared_image_id'] == env['image_id']:
            raise ValueError()
        support = env['support_inputs']
        if (not isinstance(support, list) or len(support) > 1 or support and
                (set(support[0]) != {'id', 'manifest_sha256'} or support[0]['id'] != 'model'
                 or not _sha(support[0]['manifest_sha256']))):
            raise ValueError()
        if owner['phase'] != 'intended' and not env['container_id']:
            raise ValueError()
        if owner['phase'] == 'running' and (env['unsettled'] or not env['prepared_image_id'] or not support
                                           or owner['init'] is None or owner['cgroup'] is None):
            raise ValueError()
        init, cgroup = owner['init'], owner['cgroup']
        if (init is None) != (cgroup is None):
            raise ValueError()
        if init is not None:
            if (not isinstance(init, dict) or set(init) != {'host_pid', 'start_ticks', 'pid_namespace_inode'}
                    or any(not _integer(value) for value in init.values()) or init['host_pid'] <= 1
                    or not isinstance(cgroup, dict) or set(cgroup) != {'relative_path', 'device', 'inode'}
                    or not _integer(cgroup['device'], 0) or not _integer(cgroup['inode'])):
                raise ValueError()
            path = cgroup['relative_path']
            if (not isinstance(path, str) or not path.startswith('/') or path.startswith('//')
                    or str(PurePosixPath(path)) != path or '..' in PurePosixPath(path).parts
                    or not env['container_id'] or not any(part in (env['container_id'], 'docker-' + env['container_id'] + '.scope')
                                                         for part in PurePosixPath(path).parts)):
                raise ValueError()
        safe_publication(canonical(receipt))
    except (ValueError, KeyError, TypeError, AttributeError):
        raise RuntimeError('native_owner_receipt_invalid') from None
    return receipt


def require_monotonic_owner(prior, current):
    """Ownership facts only advance; cleanup lives in a separate stop observation."""
    if any(current.get(key) != prior.get(key) for key in ('kind', 'runtime', 'profile_sha256', 'boundary')):
        raise RuntimeError('native_owner_identity_changed')
    if prior['session_id'] is not None and current['session_id'] != prior['session_id']:
        raise RuntimeError('native_owner_identity_changed')
    old, new = prior['owner'], current['owner']
    phases = ('intended', 'created', 'running')
    if phases.index(new['phase']) < phases.index(old['phase']):
        raise RuntimeError('native_owner_identity_changed')
    for key in old.keys() - {'phase', 'environment'}:
        if old[key] is not None and old[key] != new[key]:
            raise RuntimeError('native_owner_identity_changed')
    for key in ENVIRONMENT_KEYS - {'unsettled'}:
        value = old['environment'][key]
        if key == 'support_inputs' and not value and old['phase'] == 'intended':
            continue
        if value is not None and value != new['environment'][key]:
            raise RuntimeError('native_owner_identity_changed')
    if old['phase'] == 'running' and old['environment']['unsettled'] != new['environment']['unsettled']:
        raise RuntimeError('native_owner_identity_changed')


def host_identity():
    if sys.platform != 'linux' or not Path('/sys/fs/cgroup/cgroup.controllers').is_file():
        raise RuntimeError('native_model_host_prerequisites_unavailable')
    try:
        machine = Path('/etc/machine-id').read_bytes().strip()
        boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        if not re.fullmatch(rb'[0-9a-f]{32}', machine) or not re.fullmatch(r'[0-9a-f-]{36}', boot):
            raise ValueError()
        return {'id_sha256': digest(machine), 'boot_id': boot}
    except (OSError, ValueError):
        raise RuntimeError('native_model_host_identity_unavailable') from None


def process_start_ticks(pid):
    try:
        text = Path(f'/proc/{pid}/stat').read_text()
        fields = text[text.rindex(')') + 2:].split()
        value = int(fields[19])
        if value <= 0:
            raise ValueError()
        return value
    except FileNotFoundError:
        return None
    except (OSError, ValueError, IndexError):
        raise RuntimeError('native_model_process_identity_unavailable') from None


def _cgroup_path(relative):
    path = Path('/sys/fs/cgroup') / relative.lstrip('/')
    if path.resolve() != path or path == Path('/sys/fs/cgroup'):
        raise RuntimeError('native_model_cgroup_identity_invalid')
    return path


def running_identity(info, *, namespace_inode):
    try:
        pid = info['State']['Pid']
        if not info['State']['Running'] or not _integer(pid, 2):
            raise ValueError()
        started = process_start_ticks(pid)
        if started is None or not _integer(namespace_inode) or namespace_inode == Path('/proc/self/ns/pid').stat().st_ino:
            raise ValueError()
        init = {'host_pid': pid, 'start_ticks': started, 'pid_namespace_inode': namespace_inode}
        rows = Path(f'/proc/{pid}/cgroup').read_text().splitlines()
        paths = [row[3:] for row in rows if row.startswith('0::')]
        if len(paths) != 1 or not any(part in (info['Id'], 'docker-' + info['Id'] + '.scope')
                                     for part in PurePosixPath(paths[0]).parts):
            raise ValueError()
        path = _cgroup_path(paths[0]); status = path.stat()
        if str(pid) not in (path / 'cgroup.procs').read_text().split():
            raise ValueError()
        return {'init': init, 'cgroup': {'relative_path': paths[0], 'device': status.st_dev, 'inode': status.st_ino}}
    except (OSError, ValueError, KeyError, TypeError):
        raise RuntimeError('native_model_namespace_unverified') from None


def verify_absence(receipt):
    owner = receipt['owner']; current = host_identity()
    if current['id_sha256'] != owner['host']['id_sha256']:
        raise RuntimeError('native_model_host_changed')
    if current['boot_id'] != owner['host']['boot_id']:
        return True
    if owner['init'] is None:
        return True
    if process_start_ticks(owner['init']['host_pid']) == owner['init']['start_ticks']:
        raise RuntimeError('native_model_descendants_unknown')
    path = _cgroup_path(owner['cgroup']['relative_path'])
    try:
        status = path.stat()
    except FileNotFoundError:
        return True
    if (status.st_dev, status.st_ino) != (owner['cgroup']['device'], owner['cgroup']['inode']):
        raise RuntimeError('native_model_cgroup_identity_changed')
    try:
        fields = dict(line.split() for line in (path / 'cgroup.events').read_text().splitlines())
        if fields.get('populated') != '0':
            raise ValueError()
    except (OSError, ValueError):
        raise RuntimeError('native_model_descendants_unknown') from None
    return True


def inspect_model_host(profile):
    from research_environment import inspect_profile
    missing = list(inspect_profile(environment_profile(profile))['missing'])
    if sys.platform != 'linux':
        missing.append('native_model_host_platform_mismatch')
    else:
        try:
            host_identity()
        except RuntimeError as error:
            missing.append(str(error))
    return {'boundary': BOUNDARY, 'missing': sorted(set(missing)),
            'status': 'blocked' if missing else 'prerequisites_present', 'execution_verified': False}


class LinuxModelOwner:
    boundary = BOUNDARY

    def __init__(self, profile, profile_sha256, grant, *, authorize, dispatch_guard, observe_owner,
                 maximum_lease_seconds, support_directory=None, receipt=None):
        self.profile = copy.deepcopy(profile)
        self.profile_sha256, self.grant = profile_sha256, copy.deepcopy(grant)
        self.authorize, self.guard, self.observe_owner = authorize, dispatch_guard, observe_owner
        if not _integer(maximum_lease_seconds) or not _sha(profile_sha256):
            raise RuntimeError('native_model_owner_configuration_invalid')
        self.maximum_lease_seconds = maximum_lease_seconds
        self.support_directory = Path(support_directory) if support_directory is not None else None
        self.paths = SimpleNamespace(executable=MODEL, state=STATE, workspace=WORKSPACE,
                                     config=CONFIGS[profile['kind']], ca='/input/model/ca.pem')
        self.ready, self.closed, self.final = False, receipt is not None, None
        self.binding, self.session_id, self.observed = None, None, None
        limits = {**profile['model_host']['limits'], 'lease_seconds': maximum_lease_seconds, 'output_bytes': CONTROL_BYTES}
        if receipt is not None:
            validate_receipt(receipt, profile, profile_sha256=profile_sha256,
                             maximum_lease_seconds=maximum_lease_seconds, preparing=True)
            self.identity = copy.deepcopy(receipt['owner'])
            self.session_id = receipt['session_id']
        else:
            self.identity = {'phase': 'intended', **{name: grant[name] for name in
                ('dispatch_id', 'worker_id', 'generation', 'scope_sha256')}, 'environment': None,
                'configuration_sha256': configuration_digest(profile, maximum_lease_seconds),
                'host': host_identity(), 'init': None, 'cgroup': None}
        self.environment = Environment(environment_profile(profile), limits, authorize, self._observe,
            grant=grant, dispatch_guard=dispatch_guard,
            receipt=self.identity['environment'] if receipt is not None else None)
        if receipt is None:
            self.identity['environment'] = self.environment.receipt()
        else:
            self.observed = copy.deepcopy(receipt)

    def receipt(self, session_id=None):
        if session_id is not None:
            if self.session_id not in (None, session_id):
                raise RuntimeError('native_owner_identity_changed')
            self.session_id = session_id
        return {'kind': OWNER_KIND, 'runtime': self.profile['kind'], 'session_id': self.session_id,
                'profile_sha256': self.profile_sha256, 'boundary': BOUNDARY, 'owner': copy.deepcopy(self.identity)}

    def _publish(self):
        value = self.receipt()
        validate_receipt(value, self.profile, profile_sha256=self.profile_sha256,
            maximum_lease_seconds=self.maximum_lease_seconds, grant=self.grant, preparing=True)
        if self.observed is not None:
            require_monotonic_owner(self.observed, value)
        if value != self.observed:
            self.observe_owner(value)
            self.observed = copy.deepcopy(value)

    def _observe(self, observation):
        if self.closed:
            return
        self.identity['environment'] = copy.deepcopy(observation['identity'])
        if self.identity['environment']['container_id'] and self.identity['phase'] == 'intended':
            self.identity['phase'] = 'created'
        self._publish()

    def _daemon(self):
        result = self.environment._run(['info', '--format', '{{json .}}'])
        try:
            info = json.loads(result['output'])
            if (result['status'] != 'settled' or result['returncode'] or
                    info['ID'] != self.profile['model_host']['daemon_id'] or str(info['CgroupVersion']) != '2'
                    or any('rootless' in option for option in info['SecurityOptions'])):
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise RuntimeError('native_model_daemon_prerequisites_unavailable') from None

    def _configuration(self, info):
        self.environment._verify_configuration(info)
        try:
            host, config = info['HostConfig'], info['Config']
            if (host['PidMode'] not in ('', 'private') or host['IpcMode'] != 'private'
                    or host['CgroupnsMode'] != 'private' or host.get('CgroupParent') or host.get('UsernsMode')
                    or any(host.get(name) for name in ('Devices', 'DeviceRequests', 'DeviceCgroupRules', 'CapAdd',
                                                      'ExtraHosts', 'Links', 'VolumesFrom', 'Binds', 'PortBindings'))
                    or host.get('Privileged') or info.get('Mounts') or config.get('Volumes')
                    or any('unconfined' in value for value in host['SecurityOpt'])
                    or config.get('Healthcheck', {}).get('Test', ['NONE']) != ['NONE']):
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            raise RuntimeError('native_model_configuration_mismatch') from None

    def _running_identity(self, info):
        # Linux ptrace rules hide the root guardian namespace from a nonroot host.
        # This fixed read-only command stays inside the exact owned container.
        command = ('import json,os;from pathlib import Path;'
            's=Path("/proc/1/stat").read_text();'
            'print(json.dumps({"uid":os.getuid(),"pid1_start_ticks":int(s[s.rindex(")")+2:].split()[19]),'
            '"pid_namespace_inode":Path("/proc/1/ns/pid").stat().st_ino,'
            '"self_pid_namespace_inode":Path("/proc/self/ns/pid").stat().st_ino}))')
        result = self.environment._run(['container', 'exec', '--user', '0:0', '--workdir', '/', info['Id'],
            'python3', '-I', '-S', '-c', command], output_limit=4096)
        try:
            value = json.loads(result['output'])
            if (result['status'] != 'settled' or result['returncode'] or
                    set(value) != {'uid', 'pid1_start_ticks', 'pid_namespace_inode', 'self_pid_namespace_inode'}
                    or value['uid'] != 0 or not _integer(value['pid_namespace_inode'])
                    or value['self_pid_namespace_inode'] != value['pid_namespace_inode']
                    or value['pid1_start_ticks'] != process_start_ticks(info['State']['Pid'])):
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            raise RuntimeError('native_model_namespace_unverified') from None
        return running_identity(info, namespace_inode=value['pid_namespace_inode'])

    def _files(self):
        expected = {MODEL: self.profile['executable']['sha256']}
        names = ['native_runtime_bootstrap.py', 'engagement_network_bridge.py']
        if self.profile['kind'] == 'codex':
            names.append('native_runtime_codex_exec.mjs')
        for name in names:
            expected['/runtime/' + name] = digest(read_bytes(Path(__file__).with_name(name)))
        paths = list(expected) + (['/runtime/bin/bun'] if self.profile['kind'] == 'codex' else [])
        command = ('import hashlib,json,os,stat,sys;from pathlib import Path;result={}\n'
            'for name in sys.argv[1:]:\n p=Path(name);s=p.lstat()\n'
            ' if not stat.S_ISREG(s.st_mode) or p.resolve()!=p:raise ValueError()\n'
            ' with p.open("rb") as f:h="sha256:"+hashlib.file_digest(f,"sha256").hexdigest()\n'
            ' result[name]={"sha256":h,"mode":stat.S_IMODE(s.st_mode),"uid":s.st_uid,"gid":s.st_gid}\n'
            'print(json.dumps(result,sort_keys=True))')
        result = self.environment.execute(['python3', '-I', '-S', '-c', command, *paths],
                                          timeout_seconds=min(30, self.maximum_lease_seconds))
        try:
            observed = json.loads(result['output'])
            if result['status'] != 'settled' or result['returncode'] or set(observed) != set(paths):
                raise ValueError()
            for path, entry in observed.items():
                if (not isinstance(entry, dict) or set(entry) != {'sha256', 'mode', 'uid', 'gid'}
                        or entry['uid'] != 0 or entry['gid'] != 0
                        or entry['mode'] != (0o555 if path.startswith('/runtime/bin/') else 0o444)
                        or not _sha(entry['sha256']) or path in expected and entry['sha256'] != expected[path]):
                    raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise RuntimeError('native_model_image_files_changed') from None

    def prepare(self, *, config_bytes, ca_bytes):
        if self.closed or self.ready or self.support_directory is None:
            raise RuntimeError('native_model_owner_not_preparable')
        self.authorize()
        if digest(safe_publication(config_bytes)) != self.profile['config_sha256']:
            raise RuntimeError('native_model_config_changed')
        safe_publication(ca_bytes)
        if not 0 < len(ca_bytes) <= 1024 * 1024:
            raise RuntimeError('native_model_ca_invalid')
        files = [(Path(self.paths.config).name, config_bytes), ('ca.pem', ca_bytes)]
        if 'model_catalog' in self.profile:
            catalog = self.profile['model_catalog']
            content = safe_publication(read_bytes(Path(catalog['path']), private=True, max_bytes=MAX_BOOTSTRAP))
            if digest(content) != catalog['sha256']:
                raise RuntimeError('native_model_catalog_changed')
            files.append(('models.yml', content))
        self.support_directory.mkdir(mode=0o700)
        for name, content in files:
            descriptor = os.open(self.support_directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(content)
        support = {'model': {'path': str(self.support_directory),
                            'manifest_sha256': digest(canonical(source_manifest(self.support_directory)))}}
        self._publish()
        self._daemon()
        self.environment.prepare([], {}, support_inputs=support)
        info = self.environment._inspect(); self._configuration(info)
        self._files()
        self.identity['environment'] = self.environment.receipt()
        self.identity.update(self._running_identity(info), phase='running')
        self._publish()
        self.ready = True
        return self.paths

    def check_authority(self):
        if self.closed or not self.ready:
            raise RuntimeError('native_model_owner_inactive')
        self.authorize()
        info = self.environment._inspect(); self._configuration(info)
        if (host_identity() != self.identity['host'] or
                self._running_identity(info) != {name: self.identity[name] for name in ('init', 'cgroup')}):
            raise RuntimeError('native_owner_identity_changed')

    def launch_support(self, role):
        self.check_authority()
        if role == 'provider_relay':
            command = ['python3', '-I', '-S', '/runtime/engagement_network_bridge.py', 'relay']
            slot = 'model_provider_proxy'
        elif role == 'codex_bridge' and self.profile['kind'] == 'codex':
            command = ['/runtime/bin/bun', '/runtime/native_runtime_codex_exec.mjs']
            slot = 'model_codex_bridge'
        else:
            raise RuntimeError('native_model_support_role_invalid')
        return self.environment.launch_stdio(['/usr/bin/env', '-i', 'PATH=/usr/local/bin:/usr/bin:/bin',
            'HOME=/work', 'TMPDIR=/tmp', *command], role=slot)

    def launch_model(self, command, public_environment, binding):
        self.check_authority()
        if not isinstance(command, list) or not command or command[0] != MODEL:
            raise RuntimeError('native_model_command_invalid')
        safe_publication(canonical(public_environment))
        process = self.environment.launch_stdio(['/usr/bin/env', '-i', 'PATH=/usr/local/bin:/usr/bin:/bin',
            'python3', '-I', '-S', '/runtime/native_runtime_bootstrap.py'], role='model')
        try:
            with self.guard():
                self.check_authority()
                self.binding = binding
                private = binding.environment() if binding is not None else {}
                frame = json.dumps({'kind': 'native-model-bootstrap-v1', 'runtime': self.profile['kind'],
                    'argv': command, 'environment': public_environment, 'credentials': private,
                    'executable_sha256': self.profile['executable']['sha256'],
                    'config_sha256': self.profile['config_sha256'],
                    **({'model_catalog_sha256': self.profile['model_catalog']['sha256']}
                       if 'model_catalog' in self.profile else {})}, separators=(',', ':')).encode()
                if len(frame) > MAX_BOOTSTRAP:
                    raise RuntimeError('native_model_bootstrap_oversized')
                write_pipe(process.stdin, struct.pack('!I', len(frame)) + frame)
                if not select.select([process.stdout], [], [], 5)[0]:
                    raise RuntimeError('native_model_bootstrap_unavailable')
                if json.loads(process.stdout.readline(256)) != {'native_model_bootstrap': 'ready'}:
                    raise RuntimeError('native_model_bootstrap_unavailable')
        except Exception:
            try:
                self.revoke_and_verify()
            except Exception:
                pass
            raise RuntimeError('native_model_bootstrap_unavailable') from None
        return process

    def renew(self, grant, seconds):
        self.check_authority()
        if any(grant[key] != self.grant[key] for key in ('dispatch_id', 'worker_id', 'generation', 'scope_sha256')):
            raise RuntimeError('native_owner_identity_changed')
        self.grant = copy.deepcopy(grant)
        self.environment.grant = copy.deepcopy(grant)
        return self.environment.renew(seconds)

    def revoke_and_verify(self, session_id=None):
        if self.final is not None:
            return dict(self.final, session_id=session_id or self.session_id)
        self.closed = True
        if self.binding is not None:
            self.binding.revoke()
        current_host = host_identity()
        if current_host['id_sha256'] != self.identity['host']['id_sha256']:
            raise RuntimeError('native_model_host_changed')
        self._daemon()
        info = self.environment._inspect(absent_ok=True)
        if info is not None:
            self._configuration(info)
            if (info['State']['Running'] and current_host == self.identity['host'] and self.identity['init'] is not None
                    and self._running_identity(info) != {name: self.identity[name] for name in ('init', 'cgroup')}):
                raise RuntimeError('native_owner_identity_changed')
        stopped = self.environment.revoke()
        cleanup = self.environment.cleanup()
        if (stopped.get('status') not in ('stopped', 'absent') or cleanup.get('status') != 'clean'
                or cleanup['identity']['unsettled'] or not verify_absence(self.receipt())):
            raise RuntimeError('native_model_cleanup_unverified')
        self.final = {'session_id': session_id or self.session_id, 'process_exited': True,
            'child_absence': 'verified', 'capabilities_revoked': True, 'boundary': BOUNDARY,
            'model_environment_cleanup': cleanup}
        return copy.deepcopy(self.final)


def recover_runtime_owner(receipt, profile, *, maximum_lease_seconds):
    owner = LinuxModelOwner(profile, receipt['profile_sha256'], None, authorize=lambda: False,
        dispatch_guard=nullcontext, observe_owner=lambda value: None,
        maximum_lease_seconds=maximum_lease_seconds, receipt=receipt)
    return owner.revoke_and_verify(receipt['session_id'])
