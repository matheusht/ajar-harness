"""Fixed container entry: one private frame, then the pinned native executable."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import resource
import stat
import struct

MODEL = '/runtime/bin/model'
STATE = '/work/.model'
WORKSPACE = '/work'
CONFIGS = {'codex': '/input/model/config.toml', 'omp': '/input/model/config.json'}
MODEL_CATALOG = '/input/model/models.yml'
MAX_BOOTSTRAP = 2 * 1024 * 1024
PUBLIC_ENV = {'PATH', 'HOME', 'TMPDIR', 'LANG', 'LC_ALL', 'NO_COLOR', 'CODEX_HOME',
    'PI_CODING_AGENT_DIR', 'HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY', 'SSL_CERT_FILE',
    'CURL_CA_BUNDLE', 'NODE_EXTRA_CA_CERTS'}


def _read(size):
    result = bytearray()
    while len(result) < size:
        chunk = os.read(0, size - len(result))
        if not chunk:
            raise ValueError('truncated')
        result.extend(chunk)
    return bytes(result)


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('duplicate')
        result[key] = value
    return result


def _file(path, expected):
    path = Path(path)
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or path.resolve() != path or
            not isinstance(expected, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', expected)):
        raise ValueError('file')
    with path.open('rb') as stream:
        observed = 'sha256:' + hashlib.file_digest(stream, 'sha256').hexdigest()
    if observed != expected:
        raise ValueError('pin')
    return path


def _environment(public, private, runtime, state=STATE):
    if not isinstance(public, dict) or not isinstance(private, dict) or len(public) + len(private) > 64:
        raise ValueError('environment')
    if set(public) - PUBLIC_ENV or public.get('HOME') != state or public.get('TMPDIR') != '/tmp':
        raise ValueError('environment')
    state_key = 'CODEX_HOME' if runtime == 'codex' else 'PI_CODING_AGENT_DIR'
    if public.get(state_key) != state:
        raise ValueError('environment')
    for key, value in {**public, **private}.items():
        if (not isinstance(key, str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', key)
                or not isinstance(value, str) or not value or len(value.encode()) > 32768
                or any(c in value for c in '\r\n\0')):
            raise ValueError('environment')
    if any(key in PUBLIC_ENV or key.startswith(('LD_', 'DYLD_', 'PYTHON', 'BUN_', 'NODE_',
                                               'GCONV_', 'RUBY', 'PERL')) for key in private):
        raise ValueError('credential_environment')
    return {**public, **private}


def _launch():
    size, = struct.unpack('!I', _read(4))
    if not 0 < size <= MAX_BOOTSTRAP:
        raise ValueError('size')
    frame = json.loads(_read(size), object_pairs_hook=_pairs)
    optional = set(frame) & {'model_catalog_sha256', 'helper_id'} if isinstance(frame, dict) else set()
    if (not isinstance(frame, dict) or set(frame) != {'kind', 'runtime', 'argv', 'environment',
            'credentials', 'executable_sha256', 'config_sha256'} | optional
            or frame['kind'] != 'native-model-bootstrap-v1' or frame['runtime'] not in CONFIGS):
        raise ValueError('frame')
    argv = frame['argv']
    if (not isinstance(argv, list) or not 1 <= len(argv) <= 256 or argv[0] != MODEL or
            any(not isinstance(value, str) or not value or '\0' in value or len(value.encode()) > 32768 for value in argv)):
        raise ValueError('command')
    _file(MODEL, frame['executable_sha256'])
    config = _file(CONFIGS[frame['runtime']], frame['config_sha256'])
    copies = [('config.toml', config, frame['config_sha256'])] if frame['runtime'] == 'codex' else []
    if 'model_catalog_sha256' in optional:
        if frame['runtime'] != 'omp':
            raise ValueError('catalog_runtime')
        copies.append(('models.yml', _file(MODEL_CATALOG, frame['model_catalog_sha256']), frame['model_catalog_sha256']))
    helper = frame.get('helper_id')
    if helper is not None and (frame['runtime'] != 'omp' or not isinstance(helper, str) or not re.fullmatch(r'[0-9a-f]{32}', helper)):
        raise ValueError('helper')
    selected_state = STATE + '-helper-' + helper if helper is not None else STATE
    environment = _environment(frame['environment'], frame['credentials'], frame['runtime'], selected_state)
    os.umask(0o077)
    state = Path(selected_state)
    if state.is_symlink() or state.resolve() != state:
        raise ValueError('state')
    state.mkdir(mode=0o700, exist_ok=True)
    info = state.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError('state')
    for name, source, expected in copies:
        destination = state / name
        if destination.exists() or destination.is_symlink():
            _file(destination, expected)
        else:
            descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(source.read_bytes())
    workspace = Path(WORKSPACE)
    if workspace.resolve() != workspace or not workspace.is_dir():
        raise ValueError('workspace')
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.chdir(workspace)
    os.write(1, b'{"native_model_bootstrap":"ready"}\n')
    os.execve(MODEL, argv, environment)


def main():
    try:
        _launch()
    except Exception:
        os.write(2, b'native_model_bootstrap_refused\n')
        raise SystemExit(2) from None


if __name__ == '__main__':
    main()
