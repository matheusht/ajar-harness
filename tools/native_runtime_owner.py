"""A host model process that cannot fork, with kernel-bound recovery identity.

This owner currently supports macOS. Linux must supply a separately qualified
namespace/cgroup owner; a process-group-only assertion is not a substitute.
"""
from __future__ import annotations
import ctypes
import os
import re
import signal
import sys
import time
from native_runtime_transport import RuntimeError

BOUNDARY = 'darwin-no-fork-v1'


def model_command(command):
    if sys.platform != 'darwin':
        raise RuntimeError('native_model_boundary_unsupported')
    policy = '(version 1)(allow default)'
    if command[:2] == ['/usr/bin/sandbox-exec', '-p']:
        policy, command = command[2], command[3:]
        if 'process-fork' in policy:
            raise RuntimeError('native_model_boundary_override_refused')
    return ['/usr/bin/sandbox-exec', '-p', policy + '(deny process-fork)', *command]


class _ProcessInfo(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint32) for name in
        ('flags', 'status', 'xstatus', 'pid', 'ppid', 'uid', 'gid', 'ruid', 'rgid', 'svuid', 'svgid', 'reserved')] + [
        ('comm', ctypes.c_char * 16), ('name', ctypes.c_char * 32)] + [
        (name, ctypes.c_uint32) for name in ('nfiles', 'pgid', 'pjobc', 'tdev', 'tpgid')] + [
        ('nice', ctypes.c_int32), ('started_seconds', ctypes.c_uint64), ('started_microseconds', ctypes.c_uint64)]


def process_identity(pid):
    if sys.platform != 'darwin' or type(pid) is not int or pid <= 1:
        raise RuntimeError('native_owner_identity_invalid')
    library = ctypes.CDLL('/usr/lib/libproc.dylib', use_errno=True)
    info = _ProcessInfo()
    library.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
    size = library.proc_pidinfo(pid, 3, 0, ctypes.byref(info), ctypes.sizeof(info))
    if size != ctypes.sizeof(info):
        try:os.kill(pid, 0)
        except ProcessLookupError:return None
        raise RuntimeError('native_owner_identity_unavailable')
    return {key: int(getattr(info, key)) for key in
            ('pid', 'pgid', 'uid', 'started_seconds', 'started_microseconds')}


def _validate_identity(value):
    keys = {'pid', 'pgid', 'uid', 'started_seconds', 'started_microseconds'}
    if (not isinstance(value, dict) or set(value) != keys or
            any(type(v) is not int or v < 0 for v in value.values()) or
            value['pid'] <= 1 or value['pid'] != value['pgid'] or value['uid'] != os.getuid() or
            value['started_seconds'] <= 0 or value['started_microseconds'] >= 1000000):
        raise RuntimeError('native_owner_identity_invalid')


def _group_absent(pgid):
    try:os.killpg(pgid, 0)
    except ProcessLookupError:return True
    return False


def recover_runtime_owner(receipt, *, profile=None, maximum_lease_seconds=None):
    """Revoke only the exact recorded owner. No credential store is changed."""
    if isinstance(receipt, dict) and receipt.get('kind') == 'native-runtime-owner-v2':
        from native_runtime_linux import recover_runtime_owner as recover_linux
        if profile is None or maximum_lease_seconds is None:
            raise RuntimeError('native_owner_profile_required')
        return recover_linux(receipt, profile, maximum_lease_seconds=maximum_lease_seconds)
    if (not isinstance(receipt, dict) or receipt.get('kind') != 'native-runtime-owner-v1' or
            receipt.get('boundary') != BOUNDARY or receipt.get('runtime') not in ('codex', 'omp') or
            receipt.get('session_id') is not None and not isinstance(receipt.get('session_id'), str) or
            not re.fullmatch(r'sha256:[0-9a-f]{64}', str(receipt.get('profile_sha256')))):
        raise RuntimeError('native_owner_receipt_invalid')
    identities = [receipt[key] for key in ('process', 'bridge_process') if receipt.get(key) is not None]
    if not identities:
        raise RuntimeError('native_owner_identity_invalid')
    for identity in identities:
        _validate_identity(identity)
        current = process_identity(identity['pid'])
        if current is not None and current != identity:
            raise RuntimeError('native_owner_identity_changed')
        if current is None and not _group_absent(identity['pgid']):
            raise RuntimeError('native_owner_descendants_unknown')
    # Validate every owner before signalling any of them.
    for identity in reversed(identities):
        if process_identity(identity['pid']) is not None:
            if process_identity(identity['pid']) != identity:
                raise RuntimeError('native_owner_identity_changed')
            try:os.killpg(identity['pgid'], signal.SIGKILL)
            except ProcessLookupError:pass
    deadline = time.monotonic() + 2
    while True:
        absent = True
        for identity in identities:
            try:os.waitpid(identity['pid'], os.WNOHANG)
            except ChildProcessError:pass
            try:
                current = process_identity(identity['pid'])
            except RuntimeError as error:
                if str(error) != 'native_owner_identity_unavailable':raise
                absent = False
                continue
            if current is not None and current != identity:
                raise RuntimeError('native_owner_identity_changed')
            absent = absent and current is None and _group_absent(identity['pgid'])
        if absent:break
        if time.monotonic() >= deadline:
            raise RuntimeError('native_owner_stop_unverified')
        time.sleep(.02)
    return {'session_id': receipt['session_id'], 'process_exited': True,
            'child_absence': 'verified', 'capabilities_revoked': True,
            'boundary': BOUNDARY}
