"""Fixed read-only Linux mount inventory, executed as the native tool identity."""
import json
import os
from pathlib import Path
import re
import stat


def unescape(value):
    return re.sub(r'\\([0-7]{3})', lambda match: chr(int(match.group(1), 8)), value)


mounts = []
for line in Path('/proc/self/mountinfo').read_text().splitlines():
    fields = line.split()
    separator = fields.index('-')
    path, filesystem = unescape(fields[4]), fields[separator + 1]
    info = os.stat(path)
    kind = 'directory' if stat.S_ISDIR(info.st_mode) else 'file' if stat.S_ISREG(info.st_mode) else 'character' if stat.S_ISCHR(info.st_mode) else 'other'
    size = os.statvfs(path) if path in ('/work', '/tmp', '/dev', '/dev/shm') or path.startswith('/state/') else None
    mounts.append({'path': path, 'filesystem': filesystem,
        'readonly': 'ro' in fields[5].split(',') or 'ro' in fields[separator + 3].split(','),
        'writable': os.access(path, os.W_OK), 'size_bytes': size.f_frsize * size.f_blocks if size else 0,
        'mode': stat.S_IMODE(info.st_mode), 'uid': info.st_uid, 'gid': info.st_gid, 'kind': kind,
        'device': f'{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}' if kind == 'character' else None})
print(json.dumps({'uid': os.getuid(), 'gid': os.getgid(), 'mounts': mounts,
    'namespaces': {name: os.readlink('/proc/self/ns/' + name) for name in ('ipc', 'pid', 'mnt', 'net', 'cgroup')}}, sort_keys=True))
