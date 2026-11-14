"""Fixed read-only helper executed inside the worker with Python -I -S.

Descriptor binding, file stamps and manifest shape match engagement_contract.
This standalone module imports no target code or optional worker packages.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
import stat
import sys

WORKSPACE_ROOT = '/work'


class WorkspaceReadError(ValueError):
    pass


def _require(condition, code):
    if not condition:
        raise WorkspaceReadError(code)


def relative_path(path, *, directory=False):
    _require(isinstance(path, str) and len(path.encode('utf-8')) <= 4096 and
             not any(ord(char) < 32 or ord(char) == 127 for char in path), 'workspace_path_invalid')
    if directory:
        _require(path == '/work' or (path.startswith('/work/') and len(path) > 6), 'workspace_path_invalid')
        path = path[6:] if path != '/work' else ''
    else:
        _require(bool(path), 'workspace_path_invalid')
    _require(not path.startswith('/') and (not path or all(part not in ('', '.', '..') for part in path.split('/'))),
             'workspace_path_invalid')
    return path


def _stamp(entry):
    return (entry.st_dev, entry.st_ino, entry.st_mode, entry.st_uid, entry.st_gid,
            entry.st_size, entry.st_mtime_ns, entry.st_ctime_ns, entry.st_nlink)


@contextmanager
def _open(relative, *, directory=False):
    descriptors = []
    links = []
    try:
        current = os.open(WORKSPACE_ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
        root = current
        descriptors.append(current)
        parts = relative.split('/') if relative else []
        for index, name in enumerate(parts):
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
            if index != len(parts) - 1 or directory:
                flags |= os.O_DIRECTORY
            child = os.open(name, flags, dir_fd=current)
            links.append((current, name, child)); descriptors.append(child)
            current = child
        entry = os.fstat(current)
        _require(stat.S_ISDIR(entry.st_mode) if directory else stat.S_ISREG(entry.st_mode),
                 'workspace_file_not_regular')
        yield current, entry
        live = os.stat(WORKSPACE_ROOT, follow_symlinks=False)
        opened = os.fstat(root)
        _require((live.st_dev, live.st_ino, live.st_mode) == (opened.st_dev, opened.st_ino, opened.st_mode),
                 'workspace_file_changed')
        for parent, name, child in links:
            live = os.stat(name, dir_fd=parent, follow_symlinks=False)
            opened = os.fstat(child)
            _require((live.st_dev, live.st_ino, live.st_mode) == (opened.st_dev, opened.st_ino, opened.st_mode),
                     'workspace_file_changed')
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _read(fd, entry, limit, *, hash_only):
    _require(stat.S_ISREG(entry.st_mode), 'workspace_file_not_regular')
    _require(entry.st_size <= limit, 'workspace_file_oversize')
    digest = hashlib.sha256(); parts = []; size = 0
    while chunk := os.read(fd, min(65536, limit - size + 1)):
        size += len(chunk)
        _require(size <= limit, 'workspace_file_oversize')
        if hash_only:
            digest.update(chunk)
        else:
            parts.append(chunk)
    _require(size == entry.st_size and _stamp(entry) == _stamp(os.fstat(fd)), 'workspace_file_changed')
    return 'sha256:' + digest.hexdigest() if hash_only else b''.join(parts)


def read_artifact(path, limit):
    relative = relative_path(path)
    with _open(relative) as (fd, entry):
        data = _read(fd, entry, limit, hash_only=False)
    return data


def read_manifest(path, byte_limit, output_limit):
    relative = relative_path(path, directory=True)
    manifest = {}; observed = {}; total = 0

    def walk(fd, prefix, *, verify=False):
        nonlocal total
        before = os.fstat(fd); name = '/'.join(prefix)
        if verify:
            _require(observed.get(name) == _stamp(before), 'workspace_file_changed')
        else:
            observed[name] = _stamp(before)
        names = sorted(os.listdir(fd))
        for name in names:
            _require(name not in ('.', '..') and not any(ord(char) < 32 or ord(char) == 127 for char in name),
                     'workspace_path_invalid')
            child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=fd)
            try:
                entry = os.fstat(child); relative_name = '/'.join((*prefix, name))
                if stat.S_ISDIR(entry.st_mode):
                    walk(child, (*prefix, name), verify=verify)
                else:
                    _require(stat.S_ISREG(entry.st_mode), 'workspace_file_not_regular')
                    if verify:
                        _require(observed.get(relative_name) == _stamp(entry), 'workspace_file_changed')
                    else:
                        _require(len(manifest) < min(200000, max(1, output_limit // 96)), 'workspace_manifest_limit')
                        total += entry.st_size
                        _require(total <= byte_limit, 'workspace_file_oversize')
                        manifest[relative_name] = {'sha256': _read(child, entry, byte_limit, hash_only=True),
                                                   'mode': stat.S_IMODE(entry.st_mode), 'size': entry.st_size}
                        observed[relative_name] = _stamp(entry)
                live = os.stat(name, dir_fd=fd, follow_symlinks=False)
                _require(_stamp(live) == _stamp(os.fstat(child)), 'workspace_file_changed')
            finally:
                os.close(child)
        _require(names == sorted(os.listdir(fd)) and _stamp(before) == _stamp(os.fstat(fd)), 'workspace_file_changed')

    with _open(relative, directory=True) as (fd, _):
        walk(fd, ())
        walk(fd, (), verify=True)
    _require(bool(manifest), 'workspace_empty')
    data = (json.dumps(manifest, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')
    _require(len(data) <= output_limit, 'workspace_manifest_limit')
    return data


def main():
    try:
        operation, path, byte_limit, output_limit = sys.argv[1:]
        byte_limit, output_limit = int(byte_limit), int(output_limit)
        _require(0 <= byte_limit <= 8 * 1024 ** 3 and 0 <= output_limit <= 16 * 1024 ** 2,
                 'workspace_read_limit_invalid')
        if operation == 'artifact':
            data = read_artifact(path, min(byte_limit, output_limit))
        elif operation == 'manifest':
            data = read_manifest(path, byte_limit, output_limit)
        else:
            raise WorkspaceReadError('workspace_operation_invalid')
        sys.stdout.buffer.write(data)
        return 0
    except WorkspaceReadError as error:
        sys.stdout.write(str(error) + '\n')
    except (OSError, ValueError, RecursionError):
        sys.stdout.write('workspace_read_unavailable\n')
    return 74


if __name__ == '__main__':
    raise SystemExit(main())
