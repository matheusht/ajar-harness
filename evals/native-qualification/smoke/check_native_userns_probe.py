#!/usr/bin/env python3
"""Bounded user-namespace probe for the disposable native Linux fixture."""
from __future__ import annotations

import json
import subprocess
import sys


PROBE = r'''import ctypes, errno, json, pathlib
result = {}
for key, path in {
    'unprivileged_userns_clone': '/proc/sys/kernel/unprivileged_userns_clone',
    'apparmor_restrict_unprivileged_userns': '/proc/sys/kernel/apparmor_restrict_unprivileged_userns',
    'apparmor_profile': '/proc/self/attr/current',
    'uid_map': '/proc/self/uid_map', 'gid_map': '/proc/self/gid_map',
}.items():
    try:
        result[key] = pathlib.Path(path).read_text().strip()[:256]
    except OSError:
        result[key] = 'unavailable'
try:
    status = pathlib.Path('/proc/self/status').read_text()
    result['seccomp'] = next(line.split(':', 1)[1].strip() for line in status.splitlines() if line.startswith('Seccomp:'))
    result['cap_eff'] = next(line.split(':', 1)[1].strip() for line in status.splitlines() if line.startswith('CapEff:'))
except (OSError, StopIteration):
    result['process_status'] = 'unavailable'
libc = ctypes.CDLL(None, use_errno=True)
if libc.unshare(0x10000000) == 0:
    result['unshare_userns'] = 'allowed'
else:
    code = ctypes.get_errno()
    result['unshare_userns'] = 'denied'
    result['errno'] = code
    result['errno_name'] = errno.errorcode.get(code, 'UNKNOWN')
print('OSLIT_USERNS=' + json.dumps(result, sort_keys=True, separators=(',', ':')))
'''


def _parse(output):
    prefix = 'OSLIT_USERNS='
    lines = [line[len(prefix):] for line in output.splitlines() if line.startswith(prefix)]
    if len(lines) != 1:
        return {'status': 'invalid_output'}
    try:
        result = json.loads(lines[0])
    except (ValueError, TypeError):
        return {'status': 'invalid_output'}
    if (not isinstance(result, dict) or result.get('unshare_userns') not in ('allowed', 'denied')
            or any(key not in result for key in ('uid_map', 'gid_map', 'seccomp', 'cap_eff'))):
        return {'status': 'invalid_output'}
    result['status'] = 'observed'
    return result


def host_probe():
    if not sys.platform.startswith('linux'):
        return {'status': 'unsupported_platform', 'platform': sys.platform}
    try:
        completed = subprocess.run([sys.executable, '-I', '-S', '-c', PROBE], capture_output=True,
                                   text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {'status': 'execution_failed'}
    if completed.returncode != 0 or len(completed.stdout) > 2048:
        return {'status': 'execution_failed', 'returncode': completed.returncode,
                'stdout_bytes': len(completed.stdout.encode())}
    return _parse(completed.stdout)


def compare_environment(environment):
    host = host_probe()
    try:
        observed = environment.execute(['/usr/local/bin/python3', '-I', '-S', '-c', PROBE], timeout_seconds=5)
    except Exception:
        tool = {'status': 'execution_failed'}
    else:
        if observed.get('status') != 'settled' or observed.get('returncode') != 0 or len(observed.get('output', '')) > 2048:
            tool = {'status': 'execution_failed', 'phase': observed.get('status'),
                    'returncode': observed.get('returncode')}
        else:
            tool = _parse(observed['output'])
    host_result, tool_result = host.get('unshare_userns'), tool.get('unshare_userns')
    if host_result == 'allowed' and tool_result == 'denied':
        classification = 'tool_container_policy'
    elif host_result == 'denied' and tool_result == 'denied':
        classification = 'runner_or_upstream_policy'
    elif host_result == 'allowed' and tool_result == 'allowed':
        classification = 'user_namespace_available'
    else:
        classification = 'inconclusive'
    return {'classification': classification, 'host': host, 'tool_container': tool}
