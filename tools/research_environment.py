"""Owned lab execution for the v2 controller; this module grants no authority."""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import select
import shlex
import shutil
import signal
import subprocess
import tarfile
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from contextlib import nullcontext

from engagement_lease_owner import OwnedProcess, command_environment


class EnvironmentUnavailable(RuntimeError):
    pass


def _workspace_path(path, *, directory=False):
    from engagement_workspace import relative_path
    try:
        return relative_path(path, directory=directory)
    except ValueError:
        raise EnvironmentUnavailable('workspace_path_invalid') from None


def inspect_profile(profile):
    """Inspect local prerequisites only. The contract owns strict schema validation."""
    missing = []
    binary = Path(profile['docker_binary'])
    if profile['transport'] == 'docker':
        if not binary.is_file() or not os.access(binary, os.X_OK):
            missing.append('docker_binary_unavailable')
        endpoint = profile['docker_endpoint']
        if not endpoint.startswith('unix://') or not Path(endpoint[7:]).exists():
            missing.append('docker_endpoint_unavailable')
    else:
        if not shutil.which('ssh'):
            missing.append('ssh_binary_unavailable')
        ssh = profile['ssh']
        known = Path(ssh['known_hosts_file'])
        if not known.is_file() or known.is_symlink():
            missing.append('ssh_known_hosts_unavailable')
        elif 'sha256:' + hashlib.sha256(known.read_bytes()).hexdigest() != ssh['known_hosts_sha256']:
            missing.append('ssh_host_pin_changed')
        identity = Path(ssh['identity_file'])
        if not identity.is_file() or identity.is_symlink():
            missing.append('ssh_identity_reference_unavailable')
    return {'kind': 'environment-inspection-v2',
            'status': 'unavailable' if missing else 'prerequisites_present',
            'contacted_environment': False, 'missing': missing,
            'qualified': False, 'unverified': ['daemon', 'worker_isolation', 'cleanup', 'network_routes']}


class Environment:
    """Exact container observations; authority and the only journal stay with the caller.

    Inputs enter an owned stopped staging container, then an immutable image layer.
    This avoids host mounts, remote staging directories, and a second build service.
    The writable workspace is a bounded tmpfs. Network access uses a separate host
    capability; this container has no direct network or administrative socket.
    """

    def __init__(self, profile, limits, authorize, observe, *, grant=None, dispatch_guard=None, receipt=None,
                 known_hosts_file=None):
        from engagement_contract import validate_environment_profile
        validate_environment_profile(profile)
        self.profile = json.loads(json.dumps(profile))
        if known_hosts_file is not None and profile['transport'] != 'ssh-docker':
            raise EnvironmentUnavailable('ssh_host_override_invalid')
        self.known_hosts_file = known_hosts_file
        self.limits = dict(limits)
        if set(limits) != {'memory_bytes', 'cpu_count', 'pids', 'workspace_bytes', 'lease_seconds', 'output_bytes'}:
            raise EnvironmentUnavailable('environment_limits_invalid')
        for key, value in limits.items():
            valid = type(value) in (int, float) and math.isfinite(value) and value > 0
            if not valid or (key != 'cpu_count' and type(value) is not int):
                raise EnvironmentUnavailable('environment_limits_invalid')
        self.authorize, self.observe = authorize, observe
        self.grant = json.loads(json.dumps(grant)) if grant is not None else None
        self.dispatch_guard = dispatch_guard
        self.lock = threading.RLock()
        self.commands = set()
        self.owner = None
        self.stdio_processes = {}
        self.held = False
        self.retired = False
        self.identity = {'kind': 'research-environment-receipt-v2', 'nonce': uuid.uuid4().hex,
                         'container_id': None, 'container_name': None,
                         'stage_container_id': None, 'stage_container_name': None,
                         'prepared_image_id': None, 'prepared_image_name': None, 'unsettled': [],
                         'daemon_id': profile['daemon_id'], 'image_id': profile['image_id'],
                         'profile_sha256': self._digest(profile), 'access': [], 'support_inputs': []}
        self.identity['container_name'] = 'oslit-' + self.identity['nonce']
        self.identity['stage_container_name'] = self.identity['container_name'] + '-stage'
        self.identity['prepared_image_name'] = 'oslit-input-' + self.identity['nonce'] + ':latest'
        if receipt is not None:
            required = set(self.identity)
            if (not isinstance(receipt, dict) or set(receipt) != required or
                    receipt['kind'] != self.identity['kind'] or
                    receipt['profile_sha256'] != self._digest(profile) or
                    receipt['image_id'] != profile['image_id'] or
                    not re.fullmatch('[0-9a-f]{32}', receipt.get('nonce', '')) or
                    receipt['container_name'] != 'oslit-' + receipt['nonce'] or
                    receipt['stage_container_name'] != 'oslit-' + receipt['nonce'] + '-stage' or
                    receipt['prepared_image_name'] != 'oslit-input-' + receipt['nonce'] + ':latest' or
                    (receipt['container_id'] is not None and
                     not re.fullmatch('[0-9a-f]{64}', receipt['container_id'])) or
                    (receipt['stage_container_id'] is not None and
                     not re.fullmatch('[0-9a-f]{64}', receipt['stage_container_id'])) or
                    (receipt['prepared_image_id'] is not None and
                     not re.fullmatch('sha256:[0-9a-f]{64}', receipt['prepared_image_id'])) or
                    not isinstance(receipt['unsettled'], list) or
                    not set(receipt['unsettled']) <= {'create_stage', 'snapshot_input', 'create'} or
                    not receipt['daemon_id']):
                raise EnvironmentUnavailable('environment_receipt_invalid')
            self.identity = json.loads(json.dumps(receipt))
            # Recovery can inspect/revoke/clean an exact resource; it cannot revive it.
            self.retired = True

    @staticmethod
    def _digest(value):
        return 'sha256:' + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

    def receipt(self):
        return json.loads(json.dumps(self.identity))

    def _admit(self):
        if self.retired or self.held:
            raise EnvironmentUnavailable('environment_retired_or_held')
        if self.dispatch_guard is None:
            raise EnvironmentUnavailable('environment_dispatch_guard_required')
        try:
            authorized = self.authorize()
            grant = self.grant if authorized is True else authorized
            if not isinstance(grant, dict):
                raise ValueError('grant_required')
            if 'lease_expires_at' in grant:
                deadline = datetime.fromisoformat(grant['lease_expires_at'].replace('Z', '+00:00'))
                remaining = (deadline - datetime.now(timezone.utc)).total_seconds()
            else:
                remaining = grant['seconds_remaining']
            if type(remaining) not in (int, float) or not math.isfinite(remaining) or remaining <= 0:
                raise ValueError('expired')
            return min(remaining, self.limits['lease_seconds'])
        except Exception:
            raise EnvironmentUnavailable('environment_grant_inactive') from None

    def _event(self, phase, operation, operation_id, **fields):
        from engagement_contract import canonical, safe_publication
        event = {'kind': 'environment-observation-v2', 'phase': phase, 'operation': operation,
                 'operation_id': operation_id, 'identity': self.receipt(), **fields}
        safe_publication(canonical(event))
        self.observe(event)

    def _ssh(self, command):
        from engagement_contract import read_bytes, ContractError
        ssh = self.profile['ssh']
        known = Path(self.known_hosts_file if self.known_hosts_file is not None else ssh['known_hosts_file'])
        try:
            content = read_bytes(known, max_bytes=1024 * 1024)
        except (ContractError, OSError):
            raise EnvironmentUnavailable('ssh_host_pin_changed') from None
        if 'sha256:' + hashlib.sha256(content).hexdigest() != ssh['known_hosts_sha256']:
            raise EnvironmentUnavailable('ssh_host_pin_changed')
        return [shutil.which('ssh') or '/usr/bin/ssh', '-F', '/dev/null', '-T',
                '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                '-o', 'UserKnownHostsFile=' + str(known), '-o', 'GlobalKnownHostsFile=/dev/null',
                '-o', 'IdentitiesOnly=yes', '-o', 'IdentityAgent=none', '-o', 'ForwardAgent=no',
                '-o', 'ClearAllForwardings=yes', '-o', 'ConnectTimeout=5',
                '-o', 'ServerAliveInterval=2', '-o', 'ServerAliveCountMax=2',
                '-i', ssh['identity_file'], '-p', str(ssh['port']),
                ssh['user'] + '@' + ssh['host'], shlex.join(command)]

    def _docker(self, args):
        command = [self.profile['docker_binary'], '--host', self.profile['docker_endpoint'], *args]
        return self._ssh(command) if self.profile['transport'] == 'ssh-docker' else command

    def _run(self, args, *, timeout=5, input_file=None, output_file=None,
             output_limit=4 * 1024 * 1024, dispatch=False, include_stderr=False):
        """Bound command time and output; discarded bytes never become observations."""
        try:
            guard = self.dispatch_guard() if dispatch and self.dispatch_guard else nullcontext()
            with guard:
                with self.lock:
                    if dispatch:
                        self._admit()
                    process = subprocess.Popen(self._docker(args), stdin=input_file or subprocess.DEVNULL,
                                               stdout=subprocess.PIPE,
                                               stderr=subprocess.STDOUT if include_stderr else subprocess.DEVNULL,
                                               env=command_environment(), start_new_session=True)
                    self.commands.add(process)
        except OSError:
            return {'returncode': None, 'output': b'', 'status': 'unavailable'}
        output, eof = bytearray(), False
        output_size = 0
        status = 'settled'
        deadline = time.monotonic() + max(.01, timeout)
        while not eof or process.poll() is None:
            if dispatch:
                try:
                    self._admit()
                except EnvironmentUnavailable:
                    status = 'unknown'
                    break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                status = 'unknown'
                break
            ready = select.select([] if eof else [process.stdout], [], [], min(.05, remaining))[0]
            if ready:
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    eof = True
                elif output_size + len(chunk) > output_limit:
                    status = 'unknown'
                    break
                else:
                    output_size += len(chunk)
                    if output_file is None:
                        output.extend(chunk)
                    else:
                        output_file.write(chunk)
        if status == 'unknown':
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
        process.wait(timeout=2); process.stdout.close()
        with self.lock:
            self.commands.discard(process)
        return {'returncode': process.returncode, 'output': bytes(output), 'status': status}

    def _daemon(self):
        result = self._run(['info', '--format', '{{.ID}}'])
        value = result['output'].decode('utf-8', errors='replace').strip()
        if result['status'] != 'settled' or result['returncode'] or not value:
            raise EnvironmentUnavailable('docker_daemon_unavailable')
        if self.identity['daemon_id'] is not None and value != self.identity['daemon_id']:
            raise EnvironmentUnavailable('docker_daemon_changed')
        self.identity['daemon_id'] = value

    def _effect(self, operation, args, *, cleanup=False, timeout=5, input_file=None, output_limit=None):
        remaining = timeout if cleanup else min(timeout, self._admit())
        self._daemon()
        operation_id = uuid.uuid4().hex
        if operation in ('create_stage', 'snapshot_input', 'create'):
            self.identity['unsettled'].append(operation)
        self._event('intent', operation, operation_id, request_sha256=self._digest(args))
        # The journal write may have taken time or the grant may have been revoked.
        if not cleanup:
            remaining = min(remaining, self._admit())
        if operation == 'execute':
            remaining = timeout
        result = self._run(args, timeout=remaining, input_file=input_file,
                           output_limit=output_limit or 4 * 1024 * 1024, dispatch=not cleanup,
                           include_stderr=operation == 'execute')
        if result['status'] == 'settled' and result['returncode'] == 0 and operation in self.identity['unsettled']:
            self.identity['unsettled'].remove(operation)
        try:
            self._event('result', operation, operation_id, status=result['status'],
                        returncode=result['returncode'], output_sha256='sha256:' + hashlib.sha256(result['output']).hexdigest())
        except Exception:
            self.held = True
            raise
        return result

    def _inspect(self, *, absent_ok=False, stage=False):
        self._daemon()
        id_key, name_key = ('stage_container_id', 'stage_container_name') if stage else ('container_id', 'container_name')
        identity = self.identity[id_key] or self.identity[name_key]
        result = self._run(['container', 'inspect', identity])
        if result['status'] != 'settled':
            raise EnvironmentUnavailable('environment_readback_unavailable')
        if result['returncode']:
            listed = self._run(['container', 'ls', '--all', '--no-trunc', '--format', '{{.ID}}',
                                '--filter', 'name=^/' + self.identity[name_key] + '$'])
            if absent_ok and listed['status'] == 'settled' and listed['returncode'] == 0 and not listed['output'].strip():
                if ('create_stage' if stage else 'create') in self.identity['unsettled']:
                    raise EnvironmentUnavailable('environment_creation_unsettled')
                return None
            raise EnvironmentUnavailable('environment_readback_unavailable')
        try:
            rows = json.loads(result['output'])
            if len(rows) != 1:
                raise ValueError('count')
            info = rows[0]
            if (not re.fullmatch('[0-9a-f]{64}', info['Id']) or
                    (self.identity[id_key] and info['Id'] != self.identity[id_key]) or
                    info['Name'] != '/' + self.identity[name_key] or
                    info['Config']['Labels']['io.oslit.engagement'] != self.identity['nonce']):
                raise ValueError('identity')
            self.identity[id_key] = info['Id']
            operation = 'create_stage' if stage else 'create'
            if operation in self.identity['unsettled']:
                self.identity['unsettled'].remove(operation)
            return info
        except (ValueError, TypeError, KeyError):
            raise EnvironmentUnavailable('environment_identity_mismatch') from None

    def _verify_configuration(self, info, *, stage=False):
        try:
            host = info['HostConfig']
            expected_tmpfs = self._tmpfs()
            expected_image = self.profile['image_id'] if stage else self.identity['prepared_image_id']
            expected_readonly = not stage
            if (info['Image'] != expected_image or
                    info['Config']['User'] != f"{self.profile['uid']}:{self.profile['gid']}" or
                    host['NetworkMode'] != 'none' or host['ReadonlyRootfs'] is not expected_readonly or
                    host['Privileged'] or set(host['CapDrop'] or []) != {'ALL'} or
                    not any(x in ('no-new-privileges', 'no-new-privileges=true') for x in host['SecurityOpt']) or
                    host['LogConfig']['Type'] != 'none' or host['RestartPolicy']['Name'] != 'no' or
                    host['Memory'] != self.limits['memory_bytes'] or
                    host['MemorySwap'] != self.limits['memory_bytes'] or
                    host['NanoCpus'] != int(self.limits['cpu_count'] * 1e9) or
                    host['PidsLimit'] != self.limits['pids'] or
                    host.get('Binds') or info.get('Mounts') or host.get('PortBindings') or
                    host['Tmpfs'] != expected_tmpfs):
                raise ValueError('configuration')
        except (KeyError, TypeError, ValueError):
            raise EnvironmentUnavailable('environment_configuration_mismatch') from None

    def _input_image(self, *, absent_ok=False):
        self._daemon()
        result = self._run(['image', 'inspect', self.identity['prepared_image_id'] or self.identity['prepared_image_name']])
        if result['status'] != 'settled':
            raise EnvironmentUnavailable('input_image_readback_unavailable')
        if result['returncode']:
            if absent_ok and 'snapshot_input' not in self.identity['unsettled']:
                listed = self._run(['image', 'ls', '--all', '--quiet', '--no-trunc'])
                if (listed['status'] == 'settled' and listed['returncode'] == 0 and
                        self.identity['prepared_image_id'] not in listed['output'].decode('ascii').splitlines()):
                    return None
            raise EnvironmentUnavailable('input_image_readback_unavailable')
        try:
            info, = json.loads(result['output'])
            if (not re.fullmatch('sha256:[0-9a-f]{64}', info['Id']) or
                    info['Id'] == self.profile['image_id'] or
                    (self.identity['prepared_image_id'] is not None and info['Id'] != self.identity['prepared_image_id']) or
                    info['Config']['Labels']['io.oslit.engagement'] != self.identity['nonce'] or
                    info['Os'] + '/' + info['Architecture'] != self.profile['platform'] or
                    info['Config'].get('Volumes')):
                raise ValueError('image')
            self.identity['prepared_image_id'] = info['Id']
            if 'snapshot_input' in self.identity['unsettled']:
                self.identity['unsettled'].remove('snapshot_input')
            return info
        except (ValueError, KeyError, TypeError):
            raise EnvironmentUnavailable('input_image_identity_mismatch') from None

    def _tmpfs(self):
        return {path: f"rw,nosuid,nodev,size={size},uid={self.profile['uid']},gid={self.profile['gid']},mode=0700"
                for path, size in (('/work', self.limits['workspace_bytes']),
                                   ('/tmp', min(self.limits['workspace_bytes'], 64 * 1024 * 1024)))}

    def _archive(self, accesses, access_files, support_inputs):
        from engagement_contract import canonical, read_bytes, source_manifest
        archive = tempfile.TemporaryFile()
        total = 0
        identities = []
        support_identities = []
        self.expected_input = {}
        try:
            if not isinstance(support_inputs, dict) or len(support_inputs) > 32:
                raise EnvironmentUnavailable('support_inputs_invalid')
            entries = [(access, False) for access in accesses]
            files_by_id = dict(access_files)
            access_ids = {access['id'] for access in accesses}
            for identity, support in support_inputs.items():
                if (identity in access_ids or not isinstance(support, dict) or
                        set(support) != {'path', 'manifest_sha256'}):
                    raise EnvironmentUnavailable('support_inputs_invalid')
                entries.append(({'id': identity, 'kind': 'source',
                                 'identity': {'manifest_sha256': support['manifest_sha256']}}, True))
                files_by_id[identity] = support['path']
            with tarfile.open(fileobj=archive, mode='w|') as output:
                for access, is_support in entries:
                    name = access['id']
                    if not re.fullmatch('[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}', name):
                        raise EnvironmentUnavailable('access_identity_invalid')
                    if is_support:
                        support_identities.append({'id': name, **access['identity']})
                    else:
                        identities.append({'id': name, 'kind': access['kind'], 'identity': access['identity']})
                    if access['kind'] == 'application':
                        continue
                    source = Path(files_by_id[name])
                    if access['kind'] == 'source':
                        manifest = source_manifest(source)
                        digest = 'sha256:' + hashlib.sha256(canonical(manifest)).hexdigest()
                        if digest != access['identity']['manifest_sha256']:
                            raise EnvironmentUnavailable('source_identity_changed')
                        files = [(relative, source / relative, entry) for relative, entry in manifest.items()]
                    elif access['kind'] == 'binary':
                        if access['identity']['platform'] != self.profile['platform']:
                            raise EnvironmentUnavailable('binary_platform_unavailable')
                        files = [('', source, {'sha256': access['identity']['sha256'], 'mode': 0o555,
                                              'size': source.stat().st_size})]
                    else:
                        raise EnvironmentUnavailable('access_kind_invalid')
                    for relative, path, entry in files:
                        total += entry['size']
                        if total > self.limits['workspace_bytes']:
                            raise EnvironmentUnavailable('input_workspace_limit')
                        data = read_bytes(path, max_bytes=entry['size'])
                        if 'sha256:' + hashlib.sha256(data).hexdigest() != entry['sha256']:
                            raise EnvironmentUnavailable('input_identity_changed')
                        item = tarfile.TarInfo('input/' + name + ('/' + relative if relative else ''))
                        item.size = len(data); item.mode = 0o555 if entry['mode'] & 0o111 else 0o444
                        item.uid = 0; item.gid = 0; item.mtime = 0
                        output.addfile(item, io.BytesIO(data))
                        self.expected_input[item.name] = {'sha256': entry['sha256'], 'mode': item.mode,
                                                          'size': item.size}
            archive.seek(0)
            self.identity['access'] = identities
            self.identity['support_inputs'] = support_identities
            return archive
        except Exception:
            archive.close()
            raise

    def _verify_inputs(self):
        if not self.expected_input:
            return
        try:
            with tempfile.TemporaryFile() as archive:
                result = self._run(['container', 'cp', self.identity['container_id'] + ':/input', '-'],
                                   timeout=min(30, self._admit()), output_file=archive,
                                   output_limit=self.limits['workspace_bytes'] + 8192 * (len(self.expected_input) + 1))
                if result['status'] != 'settled' or result['returncode']:
                    raise EnvironmentUnavailable('input_readback_unavailable')
                archive.seek(0)
                observed = {}
                with tarfile.open(fileobj=archive, mode='r|*') as stream:
                    for item in stream:
                        name = PurePosixPath(item.name).as_posix()
                        if item.isdir():
                            if name == 'input' or any(path.startswith(name + '/') for path in self.expected_input):
                                continue
                            raise EnvironmentUnavailable('input_readback_changed')
                        if not item.isreg() or name not in self.expected_input or name in observed:
                            raise EnvironmentUnavailable('input_readback_changed')
                        expected = self.expected_input[name]
                        if item.size != expected['size'] or item.mode != expected['mode']:
                            raise EnvironmentUnavailable('input_readback_changed')
                        content = stream.extractfile(item)
                        digest = hashlib.sha256()
                        while chunk := content.read(65536):
                            digest.update(chunk)
                        observed[name] = {**expected, 'sha256': 'sha256:' + digest.hexdigest()}
                if observed != self.expected_input:
                    raise EnvironmentUnavailable('input_readback_changed')
            self._event('result', 'readback_input', uuid.uuid4().hex, status='settled',
                        manifest_sha256=self._digest(observed), files=len(observed))
        except Exception:
            self.held = True
            raise

    def prepare(self, accesses, access_files, *, support_inputs=None):
        self._admit()
        if self.identity['container_id']:
            raise EnvironmentUnavailable('environment_already_prepared')
        self._daemon()
        image = self._run(['image', 'inspect', self.profile['image_id']])
        try:
            info, = json.loads(image['output'])
            if (image['status'] != 'settled' or image['returncode'] or
                    info['Id'] != self.profile['image_id'] or
                    info['Os'] + '/' + info['Architecture'] != self.profile['platform'] or
                    info['Config'].get('Volumes')):
                raise ValueError('image')
        except (ValueError, KeyError, TypeError):
            raise EnvironmentUnavailable('pinned_image_unavailable') from None
        with self._archive(accesses, access_files, {} if support_inputs is None else support_inputs) as archive:
            args = ['container', 'create', '--name', self.identity['stage_container_name'],
                    '--label', 'io.oslit.engagement=' + self.identity['nonce'],
                    '--label', 'io.oslit.profile=' + self.identity['profile_sha256'],
                    '--network', 'none', '--cap-drop', 'ALL',
                    '--security-opt', 'no-new-privileges=true', '--pids-limit', str(self.limits['pids']),
                    '--log-driver', 'none', '--restart', 'no', '--no-healthcheck',
                    '--memory', str(self.limits['memory_bytes']), '--memory-swap', str(self.limits['memory_bytes']),
                    '--cpus', str(self.limits['cpu_count']), '--user', f"{self.profile['uid']}:{self.profile['gid']}",
                    '--workdir', '/work', '--entrypoint', '/bin/sh', '--init']
            for path, options in self._tmpfs().items():
                args.extend(['--tmpfs', path + ':' + options])
            args.extend([self.profile['image_id'], '-c', 'while :; do sleep 3600; done'])
            created = self._effect('create_stage', args)
            if created['status'] != 'settled' or created['returncode']:
                self.held = True
                raise EnvironmentUnavailable('environment_create_unknown')
            self._verify_configuration(self._inspect(stage=True), stage=True)
            copied = self._effect('stage_input', ['container', 'cp', '-', self.identity['stage_container_id'] + ':/'], input_file=archive)
            if copied['status'] != 'settled' or copied['returncode']:
                self.held = True
                raise EnvironmentUnavailable('environment_stage_unknown')
            committed = self._effect('snapshot_input', ['container', 'commit', self.identity['stage_container_id'],
                                                       self.identity['prepared_image_name']])
            if committed['status'] != 'settled' or committed['returncode']:
                self.held = True
                raise EnvironmentUnavailable('environment_snapshot_unknown')
            self._input_image()
            removed = self._effect('remove_stage', ['container', 'rm', self.identity['stage_container_id']], cleanup=True)
            if removed['status'] != 'settled' or removed['returncode'] or self._inspect(stage=True, absent_ok=True) is not None:
                self.held = True
                raise EnvironmentUnavailable('environment_stage_cleanup_unobserved')
            args[args.index('--name') + 1] = self.identity['container_name']
            args[-3] = self.identity['prepared_image_id']
            args.insert(2, '--read-only')
            created = self._effect('create', args)
            if created['status'] != 'settled' or created['returncode']:
                self.held = True
                raise EnvironmentUnavailable('environment_create_unknown')
            self._verify_configuration(self._inspect())
            self._verify_inputs()
        duration = self._admit()
        identity = {'binary': self.profile['docker_binary'], 'endpoint': self.profile['docker_endpoint'],
                    'daemon_id': self.identity['daemon_id'], 'id': self.identity['container_id'],
                    'nonce': self.identity['nonce']}
        command = [self.profile['docker_binary'], '--host', self.profile['docker_endpoint'],
                   'container', 'start', '--attach', self.identity['container_id']]
        owner_command = None
        if self.profile['transport'] == 'ssh-docker':
            source = Path(__file__).with_name('engagement_lease_owner.py').read_text()
            owner_command = self._ssh([self.profile['ssh']['python_binary'], '-c', source, 'watch'])
        operation_id = uuid.uuid4().hex
        self._event('intent', 'start', operation_id)
        duration = min(duration, self._admit())
        self.owner = OwnedProcess(command, lease_seconds=duration, maximum_lease_seconds=self.limits['lease_seconds'],
                                  docker_identity=identity, owner_command=owner_command)
        try:
            with self.dispatch_guard():
                with self.lock:
                    self._admit()
                    self.owner.start()
            until = time.monotonic() + min(duration, 5)
            while True:
                info = self._inspect()
                self._verify_configuration(info)
                if info['State']['Running']:
                    break
                if time.monotonic() >= until:
                    raise EnvironmentUnavailable('environment_start_unobserved')
                time.sleep(.05)
        except Exception:
            self.held = True
            self._event('result', 'start', operation_id, status='unknown')
            raise
        self._event('result', 'start', operation_id, status='settled')
        return {'status': 'ready', 'identity': self.receipt(), 'workspace': '/work',
                'inputs': {row['id']: '/input/' + row['id'] for row in accesses if row['kind'] != 'application'},
                'support_inputs': {row['id']: '/input/' + row['id'] for row in self.identity['support_inputs']},
                'direct_network': 'none', 'qualification': 'unverified'}

    def execute(self, argv, *, timeout_seconds):
        from engagement_contract import canonical, safe_publication
        self._admit()
        if not self.owner or not self.owner.readback()['running']:
            raise EnvironmentUnavailable('environment_worker_inactive')
        if (not isinstance(argv, list) or not argv or len(argv) > 256 or
                any(not isinstance(x, str) or not x or '\0' in x for x in argv) or
                type(timeout_seconds) not in (float, int) or not math.isfinite(timeout_seconds) or timeout_seconds <= 0):
            raise EnvironmentUnavailable('environment_command_invalid')
        safe_publication(canonical(argv))
        self._verify_configuration(self._inspect())
        result = self._effect('execute', ['container', 'exec', '--user',
                              f"{self.profile['uid']}:{self.profile['gid']}", '--workdir', '/work',
                              self.identity['container_id'], *argv], timeout=timeout_seconds,
                              output_limit=self.limits['output_bytes'])
        output = result.pop('output')
        if result['status'] != 'settled':
            self.held = True
        try:
            safe_publication(output)
            result['output'] = output.decode('utf-8')
        except (ValueError, UnicodeError):
            self.held = True
            result['status'] = 'unknown'
            result['output'] = '[output withheld]'
        result['identity'] = self.receipt()
        return result

    def _workspace_read(self, operation, path, byte_limit, output_limit):
        from engagement_contract import read_bytes
        self._admit()
        if not self.owner or not self.owner.readback()['running']:
            raise EnvironmentUnavailable('environment_worker_inactive')
        self._verify_configuration(self._inspect())
        program = read_bytes(Path(__file__).with_name('engagement_workspace.py'), max_bytes=65536).decode('utf-8')
        result = self._run(['container', 'exec', '--user', f"{self.profile['uid']}:{self.profile['gid']}",
                            '--env', 'PATH=/usr/local/bin:/usr/bin:/bin', '--workdir', '/',
                            self.identity['container_id'], 'python3', '-I', '-S', '-c', program,
                            operation, path, str(byte_limit), str(output_limit)],
                           timeout=self._admit(), output_limit=max(output_limit, 128), dispatch=True)
        self._admit()
        if result['status'] != 'settled' or result['returncode']:
            code = result['output'].decode('ascii', errors='replace').strip()
            if not re.fullmatch('workspace_[a-z_]{1,64}', code):
                code = 'workspace_read_unavailable'
            raise EnvironmentUnavailable(code)
        if len(result['output']) > output_limit:
            raise EnvironmentUnavailable('workspace_read_limit')
        return result['output']

    def read_workspace_manifest(self, path='/work'):
        from engagement_contract import canonical, safe_publication, MAX_PUBLICATION_BYTES
        _workspace_path(path, directory=True)
        safe_publication(path.encode('utf-8'))
        output_limit = min(self.limits['output_bytes'], MAX_PUBLICATION_BYTES)
        output = self._workspace_read('manifest', path, self.limits['workspace_bytes'], output_limit)
        safe_publication(output)
        manifest = json.loads(output)
        if not isinstance(manifest, dict) or not manifest or len(manifest) > 200000:
            raise EnvironmentUnavailable('workspace_manifest_invalid')
        total = 0
        for relative, entry in manifest.items():
            _workspace_path(relative)
            if (not isinstance(entry, dict) or set(entry) != {'sha256', 'mode', 'size'} or
                    not isinstance(entry['sha256'], str) or not re.fullmatch('sha256:[0-9a-f]{64}', entry['sha256']) or
                    type(entry['mode']) is not int or not 0 <= entry['mode'] <= 0o7777 or
                    type(entry['size']) is not int or entry['size'] < 0):
                raise EnvironmentUnavailable('workspace_manifest_invalid')
            total += entry['size']
        if total > self.limits['workspace_bytes'] or output != canonical(manifest):
            raise EnvironmentUnavailable('workspace_manifest_invalid')
        digest = 'sha256:' + hashlib.sha256(output).hexdigest()
        operation_id = uuid.uuid4().hex
        with self.dispatch_guard():
            self._admit()
            self._event('result', 'read_workspace_manifest', operation_id, status='settled',
                        path=path, manifest_sha256=digest, files=len(manifest))
        return {'operation_id': operation_id, 'path': path, 'manifest_sha256': digest, 'manifest': manifest}

    def read_artifact(self, relative_path, max_bytes):
        from engagement_contract import safe_publication, MAX_PUBLICATION_BYTES
        _workspace_path(relative_path)
        path = '/work/' + relative_path
        safe_publication(path.encode('utf-8'))
        if type(max_bytes) is not int or not 0 <= max_bytes <= min(self.limits['workspace_bytes'], self.limits['output_bytes'], MAX_PUBLICATION_BYTES):
            raise EnvironmentUnavailable('workspace_read_limit_invalid')
        output = self._workspace_read('artifact', relative_path, max_bytes, max_bytes)
        safe_publication(output)
        digest = 'sha256:' + hashlib.sha256(output).hexdigest()
        operation_id = uuid.uuid4().hex
        with self.dispatch_guard():
            self._admit()
            self._event('result', 'read_artifact', operation_id, status='settled',
                        path=path, output_sha256=digest, bytes=len(output))
        return {'operation_id': operation_id, 'path': path, 'output_sha256': digest,
                'bytes': len(output), 'content': output}

    def launch_stdio(self, argv, *, role='native_tools'):
        """Launch a fixed host service role; model requests never select this role."""
        from engagement_contract import canonical, safe_publication
        self._admit()
        if role not in ('native_tools', 'network_proxy'):
            raise EnvironmentUnavailable('host_pipe_role_invalid')
        if role in self.stdio_processes:
            raise EnvironmentUnavailable('host_pipe_already_started')
        if not self.owner or not self.owner.readback()['running']:
            raise EnvironmentUnavailable('environment_worker_inactive')
        if (not isinstance(argv, list) or not argv or len(argv) > 256 or
                any(not isinstance(item, str) or not item or '\0' in item for item in argv)):
            raise EnvironmentUnavailable('environment_command_invalid')
        safe_publication(canonical(argv))
        self._verify_configuration(self._inspect())
        operation_id = uuid.uuid4().hex
        self._event('intent', 'launch_stdio', operation_id, request_sha256=self._digest(argv), role=role)
        with self.dispatch_guard():
            with self.lock:
                self._admit()
                if role in self.stdio_processes:
                    raise EnvironmentUnavailable('host_pipe_already_started')
                try:
                    process = subprocess.Popen(self._docker(['container', 'exec', '--interactive', '--user',
                        f"{self.profile['uid']}:{self.profile['gid']}", '--workdir', '/work',
                        self.identity['container_id'], *argv]), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL, env=command_environment(), start_new_session=True)
                except OSError:
                    raise EnvironmentUnavailable('native_tool_process_unavailable') from None
                self.stdio_processes[role] = process
                self.commands.add(process)
        try:
            self._event('result', 'launch_stdio', operation_id, status='dispatched',
                        role=role, native_acknowledgment='caller_required')
        except Exception:
            self.held = True
            self.revoke()
            raise
        return process

    def readback(self):
        info = self._inspect(absent_ok=True)
        if info is None:
            return {'status': 'absent', 'identity': self.receipt()}
        self._verify_configuration(info)
        return {'status': 'held' if self.held else ('running' if info['State']['Running'] else 'stopped'),
                'running': info['State']['Running'], 'identity': self.receipt()}

    def renew(self, seconds):
        remaining = self._admit()
        if type(seconds) not in (float, int) or not math.isfinite(seconds) or not 0 < seconds <= remaining:
            raise EnvironmentUnavailable('environment_lease_exceeds_grant')
        if not self.owner:
            raise EnvironmentUnavailable('environment_worker_inactive')
        self._verify_configuration(self._inspect())
        operation_id = uuid.uuid4().hex
        self._event('intent', 'renew', operation_id, seconds=seconds)
        with self.dispatch_guard():
            with self.lock:
                self.owner.renew(min(seconds, self._admit()))
        self._event('result', 'renew', operation_id, status='settled')
        return {'status': 'renewal_sent', 'seconds': seconds, 'identity': self.receipt()}

    def revoke(self):
        with self.lock:
            self.retired = True
            for process in list(self.commands):
                if process.poll() is None:
                    try: os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                    process.wait(timeout=2)
        info = self._inspect(absent_ok=True)
        if info is None:
            return {'status': 'absent', 'identity': self.receipt()}
        if self.owner:
            self.owner.revoke()
        info = self._inspect()
        if info['State']['Running']:
            result = self._effect('revoke', ['container', 'kill', self.identity['container_id']], cleanup=True)
            if result['status'] != 'settled' or result['returncode']:
                raise EnvironmentUnavailable('environment_revocation_unobserved')
        if self._inspect()['State']['Running']:
            raise EnvironmentUnavailable('environment_revocation_unobserved')
        return {'status': 'stopped', 'identity': self.receipt()}

    def cleanup(self):
        self.revoke()
        info = self._inspect(absent_ok=True)
        if info is not None:
            removed = self._effect('remove', ['container', 'rm', self.identity['container_id']], cleanup=True)
            if removed['status'] != 'settled' or removed['returncode']:
                raise EnvironmentUnavailable('environment_cleanup_unobserved')
        if self._inspect(absent_ok=True) is not None:
            raise EnvironmentUnavailable('environment_cleanup_unobserved')
        stage = self._inspect(stage=True, absent_ok=True)
        if stage is not None:
            if stage['State']['Running']:
                killed = self._effect('stop_stage', ['container', 'kill', self.identity['stage_container_id']], cleanup=True)
                if killed['status'] != 'settled' or killed['returncode']:
                    raise EnvironmentUnavailable('environment_stage_cleanup_unobserved')
            removed = self._effect('remove_stage', ['container', 'rm', self.identity['stage_container_id']], cleanup=True)
            if removed['status'] != 'settled' or removed['returncode'] or self._inspect(stage=True, absent_ok=True) is not None:
                raise EnvironmentUnavailable('environment_stage_cleanup_unobserved')
        image = self._input_image(absent_ok=True)
        if image is not None:
            removed = self._effect('remove_input_image', ['image', 'rm', self.identity['prepared_image_id']], cleanup=True)
            if removed['status'] != 'settled' or removed['returncode'] or self._input_image(absent_ok=True) is not None:
                raise EnvironmentUnavailable('environment_image_cleanup_unobserved')
        return {'status': 'clean', 'identity': self.receipt(), 'owned_workspace': 'container_removed'}
