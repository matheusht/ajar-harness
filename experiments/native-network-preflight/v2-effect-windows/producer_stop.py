"""Exact frozen producer set for the owned dummy-only parent-loss experiment."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'tools'))
from docker_session_runtime import _inspect_one, _owned, _run_docker, _validate_id


def binding(info):
    value = {key: info[key] for key in ('Id', 'Image', 'Config', 'Mounts')}
    value['Mounts'] = sorted(info['Mounts'], key=lambda mount: mount['Destination'])
    value['networks'] = sorted(info['NetworkSettings']['Networks'])
    value['host'] = {key: info['HostConfig'][key] for key in
                     ('ReadonlyRootfs', 'Privileged', 'RestartPolicy', 'CapDrop', 'SecurityOpt')}
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class Producers:
    def __init__(self, path, fault_id=None, kill_fault_id=None):
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            entry = os.fstat(stream.fileno())
            if not stat.S_ISREG(entry.st_mode) or entry.st_uid != os.getuid() or entry.st_mode & 0o077 or entry.st_size > 16384:
                raise ValueError('producer_manifest_permissions')
            raw = stream.read(16385)
        self.manifest = json.loads(raw)
        self.digest = hashlib.sha256(raw).hexdigest()
        self.docker = Path(shutil.which('docker')).resolve(strict=True)
        self.items = self.manifest['producers']
        if self.manifest['version'] != 1 or not 1 <= len(self.items) <= 8 or len({p['id'] for p in self.items}) != len(self.items):
            raise ValueError('producer_manifest_invalid')
        self.fault_id = fault_id
        self.kill_fault_id = kill_fault_id
        if any(identifier and identifier not in {p['id'] for p in self.items} for identifier in (fault_id, kill_fault_id)):
            raise ValueError('producer_fault_id_unbound')
        for item in self.items:
            info = self.inspect(item)
            if info['State']['Status'] != 'created':
                raise ValueError('producer_must_be_created_stopped')

    def inspect(self, item):
        identifier = _validate_id(item['id'], code='producer_id_invalid')
        info = _inspect_one(self.docker, 'container', identifier)
        if not _owned(info, identifier=identifier, nonce=self.manifest['nonce']) or binding(info) != item['binding']:
            raise ValueError('producer_identity_mismatch')
        return info

    def start(self, fail_after=None, stop_check=None, hold_dir=None, lock_fd=None, start_record=None):
        for number,item in enumerate(self.items,1):
            if stop_check and stop_check():raise RuntimeError('native_stop_during_start')
            self.inspect(item)
            if start_record:start_record(item,'begin')
            _run_docker(self.docker, ['container', 'start', item['id']],pass_fds=(lock_fd,) if lock_fd is not None else ())
            if start_record:start_record(item,'done')
            if fail_after==number:raise RuntimeError('injected_partial_start_failure')
            if number==1 and hold_dir:
                (hold_dir/'STARTED').touch()
                deadline=time.monotonic()+30
                while not (hold_dir/'RELEASE').exists():
                    if stop_check and stop_check():raise RuntimeError('native_stop_during_start')
                    if time.monotonic()>=deadline:raise RuntimeError('injected_start_hold_timeout')
                    time.sleep(.01)
            if stop_check and stop_check():raise RuntimeError('native_stop_during_start')

    def freeze(self, event):
        errors = []
        for item in self.items:
            try:
                info = self.inspect(item)
                if info['State']['Running'] and not info['State']['Paused']:
                    try:
                        if item['id'] == self.fault_id:
                            raise RuntimeError('injected_pause_command_failure')
                        _run_docker(self.docker, ['container', 'pause', item['id']])
                    except Exception as error:
                        event('producer_pause_failed', {'id': item['id'], 'error': str(error), 'injected': item['id'] == self.fault_id})
                        if self.inspect(item)['State']['Running']:
                            if item['id'] == self.kill_fault_id:
                                raise RuntimeError('injected_kill_command_failure')
                            _run_docker(self.docker, ['container', 'kill', item['id']])
                state = self.inspect(item)['State']
                if state['Running'] and not state['Paused']:
                    raise RuntimeError('producer_not_stopped')
                event('producer_frozen', {'id': item['id'], 'state': state, 'monotonic': time.monotonic()})
            except Exception as error:
                errors.append({'id': item['id'], 'error': str(error)})
        # Recheck the entire sealed set immediately before the caller publishes REVOKED.
        for item in self.items:
            try:
                state = self.inspect(item)['State']
                if state['Running'] and not state['Paused']:
                    errors.append({'id': item['id'], 'error': 'producer_not_stopped'})
            except Exception as error:
                errors.append({'id': item['id'], 'error': str(error)})
        if errors:
            event('producer_stop_failed', {'errors': errors})
            raise RuntimeError('producer_stop_failed')
        proof={'ids':[p['id'] for p in self.items], 'manifest_sha256':self.digest,
               'monotonic':time.monotonic()}
        event('producer_set_frozen', proof)
        return proof
