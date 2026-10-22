#!/usr/bin/env python3
"""Direct, bounded OpenCode research run over one owned local application service.

`prepare` is provider-free. `start` is a foreground owner; a human-supplied,
run-bound approval is required before it can create a live route. `resume` and
`stop` are separate CLI calls while that owner is alive. This is a launch
adapter, not a finding oracle or a provider billing authority.
"""

from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import select
import shutil
import socket
import sqlite3
import ssl
import stat
import subprocess
import sys
import threading
import time
import uuid


ROOT = Path(__file__).resolve().parents[1]
CONTROL_SHA = {
    'experiments/native-network-preflight/v2_connect.py': '7f031921c0cd363fec9f7bd45cd4794bd0751df3c54008acde167cf1535698c3',
    'experiments/native-network-preflight/v2-effect-windows/native_run.py': '759fb38b0df5557b290989bc9b42eb603d5e7631511d4ded2f0646f5decf492f',
    'experiments/native-network-preflight/v2-effect-windows/_native_stop_owner.py': 'dca06e8f2472dda294f6551dc16a31791338552a318ee26a1d05146ef148f175',
    'experiments/native-network-preflight/v2-effect-windows/producer_stop.py': '94d7d3db11c1215ac6c4adbcf2a7fa6758e078faa5681ed442230835198a6cdd',
    'tools/docker_session_runtime.py': '9e8d36eed18387d4106d02a62b3ef7489845cb6da9ccbf57256c3a4432f47651',
}
MODEL = 'opencode/deepseek-v4.1-flash-free'
PROVIDER_ROUTE = 'opencode-keyless-free'
AUTHORITY = 'opencode.ai:443'
VERSION = 'opencode v2.0.32'
OFFICIAL_IMAGE_ENV = {'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
                      'BUN_RUNTIME_TRANSPILER_CACHE_PATH': '0'}
DEFAULT_LIMITS = {'max_connections': 16, 'max_bytes': 8 * 1024 * 1024, 'duration_seconds': 300}
LABEL = 'io.lrh.native-research'
OWNER_LABEL = 'io.llm-redteam-harness.runtime'
NONCE_LABEL = 'io.llm-redteam-harness.session-nonce'
SESSION_RE = re.compile(r'ses_[A-Za-z0-9]{1,64}\Z')
HEX_RE = re.compile(r'[0-9a-f]{64}\Z')
IMAGE_RE = re.compile(r'sha256:[0-9a-f]{64}\Z')
SENSITIVE_ENV = re.compile(r'(?:TOKEN|SECRET|PASSWORD|API_KEY|ACCESS_KEY|PRIVATE_KEY|AUTHORIZATION|CREDENTIAL)', re.I)
CREDENTIAL_TEXT = re.compile(
    r'(?i)(?:\b(?:authorization|proxy-authorization|cookie|set-cookie|x-api-key)\s*[:=]|'
    r'\b(?:bearer|basic)\s+[A-Za-z0-9+/._=-]{8,}|'
    r'\b(?:password|passwd|api[_-]?key|access[_-]?token|secret)\s*[:=]\s*\S+|'
    r'\blocal_[0-9a-f]{32}\b|-----BEGIN [A-Z ]*PRIVATE KEY-----|'
    r'\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b|'
    r'\b(?:X-Amz-Signature|X-Goog-Signature)=)')
DOCKER_BINARY: Path | None = None
CONFIG = {
    '$schema': 'https://opencode.ai/config.json', 'model': MODEL,
    'update': 'disable', 'share': 'disabled', 'plugins': [],
    'mcp': {'servers': {}}, 'websearch': False,
    'permissions': [
        {'action': '*', 'resource': '*', 'effect': 'deny'},
        *({'action': action, 'resource': '*', 'effect': 'allow'}
          for action in ('read', 'glob', 'grep', 'edit', 'write', 'shell')),
    ],
    'policies': [
        {'action': 'provider.use', 'resource': '*', 'effect': 'deny'},
        {'action': 'provider.use', 'resource': 'opencode', 'effect': 'allow'},
    ],
}


class NativeResearchError(RuntimeError):
    pass


def _fail(code: str) -> None:
    raise NativeResearchError(code)


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _file(path: Path, *, private: bool = False) -> Path:
    path = Path(path)
    if not path.is_absolute() or path.is_symlink():
        _fail('absolute_regular_file_required')
    try:
        resolved = path.resolve(strict=True)
        entry = path.stat(follow_symlinks=False)
    except OSError:
        _fail('regular_file_unavailable')
    if (resolved != path or not stat.S_ISREG(entry.st_mode)
            or (private and (entry.st_uid != os.getuid() or entry.st_mode & 0o077))):
        _fail('regular_file_invalid')
    return path


def _private_root(path: Path, *, create: bool = False) -> Path:
    path = Path(path)
    if not path.is_absolute() or path.is_symlink():
        _fail('absolute_private_run_root_required')
    if create:
        if path.exists():
            _fail('run_root_already_exists')
        path.mkdir(mode=0o700, parents=False)
    try:
        entry = path.stat(follow_symlinks=False)
    except OSError:
        _fail('run_root_unavailable')
    if not stat.S_ISDIR(entry.st_mode) or entry.st_uid != os.getuid() or entry.st_mode & 0o077:
        _fail('run_root_permissions')
    return path


def _write_json(path: Path, value: object, *, once: bool = False) -> None:
    data = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    if once:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    else:
        temporary = path.with_name('.' + path.name + '-' + uuid.uuid4().hex)
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_json(path: Path) -> dict:
    path = _file(path, private=True)
    if path.stat().st_size > 1024 * 1024:
        _fail('control_file_oversize')
    try:
        value = json.loads(path.read_bytes())
    except (UnicodeError, ValueError):
        _fail('control_file_invalid')
    if not isinstance(value, dict):
        _fail('control_file_invalid')
    return value


def _inventory(directory: Path) -> dict[str, str]:
    if not directory.is_dir() or directory.is_symlink():
        _fail('source_directory_invalid')
    result = {}
    for path in sorted(directory.rglob('*')):
        relative = path.relative_to(directory)
        if '.git' in relative.parts or path.is_symlink():
            _fail('source_history_or_symlink_forbidden')
        if '.opencode' in relative.parts or relative.as_posix() in ('opencode.json', 'target.json'):
            _fail('source_reserved_runtime_path_forbidden')
        entry = path.stat(follow_symlinks=False)
        if stat.S_ISDIR(entry.st_mode):
            continue
        if not stat.S_ISREG(entry.st_mode):
            _fail('source_special_file_forbidden')
        result[relative.as_posix()] = _sha(path)
    if not result:
        _fail('source_empty')
    return result


def _verify_inventory(directory: Path, expected: dict[str, str]) -> None:
    if _inventory(directory) != expected:
        _fail('source_pin_mismatch')


def _valid_relative_path(value: str) -> bool:
    return (isinstance(value, str) and bool(value) and not value.startswith('/')
            and not '\\' in value and all(part not in ('', '.', '..') for part in value.split('/')))


def _mutable(relative: str, paths: list[str]) -> bool:
    return any(relative == item or relative.startswith(item + '/') for item in paths)


def _verify_target_state(directory: Path, source: dict[str, str], mutable_paths: list[str]) -> None:
    observed = {}
    for path in sorted(directory.rglob('*')):
        relative = path.relative_to(directory).as_posix()
        if _mutable(relative, mutable_paths):
            continue
        if path.is_symlink():
            _fail('target_source_symlink')
        entry = path.stat(follow_symlinks=False)
        if stat.S_ISDIR(entry.st_mode):
            continue
        if not stat.S_ISREG(entry.st_mode):
            _fail('target_source_special_file')
        observed[relative] = _sha(path)
    expected = {name: digest for name, digest in source.items()
                if not _mutable(name, mutable_paths)}
    if observed != expected:
        _fail('target_source_or_state_changed')


def _controls(root: Path) -> Path:
    return root / 'controls'


def _plan(root: Path) -> dict:
    root = _private_root(root)
    plan = _read_json(root / 'plan.json')
    if plan.get('kind') != 'native-research-plan-v1' or not _valid_limits(plan.get('limits')):
        _fail('run_plan_invalid')
    return plan


def _valid_limits(value: object) -> bool:
    return (isinstance(value, dict) and set(value) == set(DEFAULT_LIMITS)
            and type(value['max_connections']) is int and 1 <= value['max_connections'] <= 128
            and type(value['max_bytes']) is int and 1024 <= value['max_bytes'] <= 128 * 1024 * 1024
            and type(value['duration_seconds']) is int and 30 <= value['duration_seconds'] <= 86400)


def _validate_target_command(path: Path) -> list[str]:
    path = _file(path)
    if path.stat().st_size > 8192:
        _fail('target_command_oversize')
    try:
        command = json.loads(path.read_text())
    except (UnicodeError, ValueError):
        _fail('target_command_invalid')
    if (not isinstance(command, list) or not 1 <= len(command) <= 64
            or any(not isinstance(item, str) or not item or '\x00' in item or len(item) > 4096
                   for item in command)):
        _fail('target_command_invalid')
    if any(re.search(r'(?:password|passwd|token|secret|api[-_]?key|authorization|cookie|bearer|basic)', item, re.I)
           for item in command):
        _fail('target_command_may_contain_credential')
    return command


def prepare(args: argparse.Namespace) -> dict:
    source = Path(args.source)
    brief = _file(Path(args.brief))
    scope = _file(Path(args.scope_file), private=True)
    relay = _file(Path(args.relay), private=True)
    ca = _file(Path(args.runtime_ca), private=True)
    _validate_target_command(Path(args.target_command))
    run_root = Path(args.run_root)
    if not source.is_absolute() or source.is_symlink() or not source.is_dir():
        _fail('source_directory_invalid')
    source = source.resolve(strict=True)
    if not run_root.is_absolute() or run_root.is_relative_to(source) or source.is_relative_to(run_root):
        _fail('source_run_root_overlap')
    if args.model != MODEL or args.provider_route != PROVIDER_ROUTE or args.provider_authority != AUTHORITY:
        _fail('provider_or_model_unqualified')
    limits = {'max_connections': args.max_connections, 'max_bytes': args.max_bytes,
              'duration_seconds': args.duration_seconds}
    if not _valid_limits(limits):
        _fail('allowance_invalid')
    if (not IMAGE_RE.fullmatch(args.image_id) or not IMAGE_RE.fullmatch(args.target_image_id)
            or args.platform not in ('linux/arm64', 'linux/amd64')
            or not 1 <= args.target_port <= 65535):
        _fail('runtime_or_target_pin_invalid')
    for path, expected in ((scope, args.scope_sha256), (relay, args.relay_sha256),
                           (ca, args.runtime_ca_sha256)):
        if not HEX_RE.fullmatch(expected) or _sha(path) != expected:
            _fail('input_digest_mismatch')
    if b'PRIVATE KEY' in ca.read_bytes() or ca.stat().st_size > 4 * 1024 * 1024:
        _fail('runtime_ca_invalid')
    try:
        trust = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        trust.load_verify_locations(cafile=str(ca))
    except ssl.SSLError:
        _fail('runtime_ca_invalid')
    header = relay.open('rb').read(20)
    machine = {'linux/amd64': 62, 'linux/arm64': 183}[args.platform]
    if (len(header) != 20 or header[:6] != b'\x7fELF\x02\x01'
            or int.from_bytes(header[18:20], 'little') != machine
            or not relay.stat().st_mode & 0o111):
        _fail('relay_platform_invalid')
    for relative, digest in CONTROL_SHA.items():
        if _sha(ROOT / relative) != digest:
            _fail('control_pin_mismatch')
    docker_found = shutil.which('docker')
    if not docker_found:
        _fail('docker_unavailable')
    docker_binary = Path(docker_found).resolve(strict=True)
    docker_entry = docker_binary.stat(follow_symlinks=False)
    if (not stat.S_ISREG(docker_entry.st_mode) or not os.access(docker_binary, os.X_OK)
            or docker_entry.st_mode & 0o022):
        _fail('docker_executable_invalid')
    source_inventory = _inventory(source)
    try:
        brief_text = brief.read_text()
    except UnicodeError:
        _fail('brief_encoding_invalid')
    if not brief_text.strip() or CREDENTIAL_TEXT.search(brief_text):
        _fail('brief_empty_or_credential_like')
    mutable_paths = list(args.mutable_path or [])
    if (len(mutable_paths) != len(set(mutable_paths))
            or any(not _valid_relative_path(item) or item == '.git' or item.startswith('.git/')
                   for item in mutable_paths)):
        _fail('mutable_path_invalid')
    expected_skill_ids = list(args.expected_skill_id or [])
    if (len(expected_skill_ids) != len(set(expected_skill_ids))
            or any(not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', item) for item in expected_skill_ids)):
        _fail('expected_skill_id_invalid')
    root = _private_root(run_root, create=True)
    try:
        for name in ('original', 'target', 'review-target-1', 'review-target-2', 'researcher/project'):
            shutil.copytree(source, root / name, dirs_exist_ok=False)
            _verify_inventory(root / name, source_inventory)
        for name in ('researcher', 'reviewer-1', 'reviewer-2'):
            base = root / name
            for sub in ('home', 'config/opencode', 'data', 'cache', 'state', 'tmp', 'brief'):
                (base / sub).mkdir(parents=True, mode=0o700, exist_ok=True)
        for name in ('reviewer-1', 'reviewer-2'):
            (root / name / 'project').mkdir(mode=0o700)
        (root / 'handoff').mkdir(mode=0o700)
        for name in ('reviewer-1', 'reviewer-2'):
            (root / 'handoff' / name).mkdir(mode=0o700)
        controls = _controls(root)
        controls.mkdir(mode=0o700)
        (controls / 'dispatch').mkdir(mode=0o700)
        for relative in CONTROL_SHA:
            destination = controls / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, destination)
            if _sha(destination) != CONTROL_SHA[relative]:
                _fail('archived_control_pin_mismatch')
        for source_path, name in ((relay, 'relay'), (ca, 'runtime-ca.pem'),
                                  (scope, 'scope.md'), (brief, 'BRIEF.md'),
                                  (Path(args.target_command), 'target-command.json')):
            destination = controls / name
            shutil.copy2(source_path, destination)
            destination.chmod(0o700 if name == 'relay' else 0o600)
        shutil.copy2(controls / 'BRIEF.md', root / 'researcher/brief/BRIEF.md')
        (root / 'researcher/brief/BRIEF.md').chmod(0o600)
        _write_json(controls / 'opencode.json', CONFIG, once=True)
        for name in ('researcher', 'reviewer-1', 'reviewer-2'):
            (root / name / 'config/opencode/opencode.json').touch(mode=0o600)
        plan = {
            'kind': 'native-research-plan-v1', 'provider_route': PROVIDER_ROUTE,
            'provider_authority': AUTHORITY, 'model': args.model,
            'image_id': args.image_id, 'target_image_id': args.target_image_id,
            'platform': args.platform, 'target_port': args.target_port,
            'opencode_version': VERSION,
            'limits': limits, 'source_sha256': source_inventory,
            'mutable_paths': mutable_paths,
            'expected_skill_ids': sorted(expected_skill_ids),
            'source_manifest_sha256': hashlib.sha256(json.dumps(source_inventory, sort_keys=True).encode()).hexdigest(),
            'brief_sha256': _sha(controls / 'BRIEF.md'),
            'scope_sha256': _sha(controls / 'scope.md'),
            'relay_sha256': _sha(controls / 'relay'),
            'runtime_ca_sha256': _sha(controls / 'runtime-ca.pem'),
            'target_command_sha256': _sha(controls / 'target-command.json'),
            'config_sha256': _sha(controls / 'opencode.json'),
            'docker_binary': str(docker_binary), 'docker_sha256': _sha(docker_binary),
            'control_sha256': CONTROL_SHA,
        }
        _write_json(root / 'plan.json', plan, once=True)
        return {'status': 'prepared_provider_free', 'run_root': str(root),
                'plan_sha256': _sha(root / 'plan.json'), 'source_files': len(source_inventory),
                'live_approval_required': True}
    except Exception:
        shutil.rmtree(root)
        raise


def _docker(*arguments: str, timeout: float = 30, allow_failure: bool = False) -> subprocess.CompletedProcess[bytes]:
    if DOCKER_BINARY is None:
        _fail('docker_unavailable')
    environment = {key: value for key, value in os.environ.items()
                   if key in ('HOME', 'PATH', 'DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_CONFIG')}
    try:
        result = subprocess.run([str(DOCKER_BINARY), *arguments], stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                env=environment, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        _fail('docker_command_unavailable')
    if len(result.stdout) > 2 * 1024 * 1024 or len(result.stderr) > 2 * 1024 * 1024:
        _fail('docker_command_output_oversize')
    if result.returncode and not allow_failure:
        _fail('docker_command_failed')
    return result


def _inspect(kind: str, identifier: str) -> dict:
    try:
        value = json.loads(_docker(kind, 'inspect', identifier).stdout)
    except (UnicodeError, ValueError):
        _fail('docker_inspect_invalid')
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        _fail('docker_inspect_invalid')
    return value[0]


def _image(image_id: str, platform: str, *, official: bool = False) -> None:
    info = _inspect('image', image_id)
    if (info.get('Id') != image_id or info.get('Os') != 'linux'
            or info.get('Architecture') != platform.split('/')[1]):
        _fail('image_pin_mismatch')
    config = info.get('Config') or {}
    env = config.get('Env') or []
    if official and (len(env) != len(OFFICIAL_IMAGE_ENV)
                     or dict(item.split('=', 1) for item in env if '=' in item) != OFFICIAL_IMAGE_ENV):
        _fail('opencode_image_environment_mismatch')
    if any('=' not in item or (SENSITIVE_ENV.search(item.split('=', 1)[0])
                               and item.split('=', 1)[1])
           or (item.split('=', 1)[0].startswith(('LD_', 'BUN_', 'OPENCODE_'))
               and item not in ('BUN_RUNTIME_TRANSPILER_CACHE_PATH=0',)) for item in env):
        _fail('image_ambient_credential')


def _verified_plan(root: Path, *, pristine: bool = False) -> dict:
    global DOCKER_BINARY
    plan = _plan(root)
    controls = _controls(root)
    if (plan.get('provider_route') != PROVIDER_ROUTE or plan.get('provider_authority') != AUTHORITY
            or plan.get('model') != MODEL or plan.get('opencode_version') != VERSION
            or plan.get('control_sha256') != CONTROL_SHA
            or not IMAGE_RE.fullmatch(str(plan.get('image_id')))
            or not IMAGE_RE.fullmatch(str(plan.get('target_image_id')))):
        _fail('run_plan_pin_mismatch')
    docker_found = shutil.which('docker')
    if not docker_found:
        _fail('docker_unavailable')
    docker_binary = Path(docker_found).resolve(strict=True)
    if (str(docker_binary) != plan.get('docker_binary') or _sha(docker_binary) != plan.get('docker_sha256')
            or docker_binary.stat().st_mode & 0o022):
        _fail('docker_binary_pin_mismatch')
    DOCKER_BINARY = docker_binary
    for relative, digest in CONTROL_SHA.items():
        if _sha(controls / relative) != digest:
            _fail('archived_control_pin_mismatch')
    for name, key in (('relay', 'relay_sha256'), ('runtime-ca.pem', 'runtime_ca_sha256'),
                      ('scope.md', 'scope_sha256'), ('BRIEF.md', 'brief_sha256'),
                      ('target-command.json', 'target_command_sha256'),
                      ('opencode.json', 'config_sha256')):
        if _sha(controls / name) != plan.get(key):
            _fail('run_input_pin_mismatch')
    if _read_json(controls / 'opencode.json') != CONFIG:
        _fail('run_config_mismatch')
    if _sha(root / 'researcher/brief/BRIEF.md') != plan.get('brief_sha256'):
        _fail('run_brief_changed')
    _verify_inventory(root / 'original', plan['source_sha256'])
    if pristine:
        for name in ('target', 'review-target-1', 'review-target-2', 'researcher/project'):
            _verify_inventory(root / name, plan['source_sha256'])
    return plan


def _approval(root: Path, plan: dict, path: Path) -> None:
    approval = _read_json(path)
    expected = {
        'kind': 'native-research-live-approval-v1',
        'plan_sha256': _sha(root / 'plan.json'),
        'scope_sha256': plan['scope_sha256'],
        'provider_route': PROVIDER_ROUTE,
        'provider_authority': AUTHORITY,
        'model': MODEL,
        'image_id': plan['image_id'],
        'target_image_id': plan['target_image_id'],
        'limits': plan['limits'],
    }
    if any(approval.get(key) != value for key, value in expected.items()):
        _fail('live_approval_mismatch')
    if (not isinstance(approval.get('approved_by'), str) or not approval['approved_by'].strip()
            or not isinstance(approval.get('approved_at'), str)
            or not isinstance(approval.get('expires_at'), str)
            or not all(re.fullmatch(r'20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z',
                                    approval[key]) for key in ('approved_at', 'expires_at'))):
        _fail('live_approval_invalid')
    try:
        approved = datetime.strptime(approval['approved_at'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
        expires = datetime.strptime(approval['expires_at'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
    except ValueError:
        _fail('live_approval_invalid')
    age = (datetime.now(timezone.utc) - approved).total_seconds()
    if not 0 <= age <= 24 * 3600 or not approved < expires <= approved + timedelta(hours=24) or datetime.now(timezone.utc) >= expires:
        _fail('live_approval_stale_or_future')


def _activate_controls(root: Path):
    controls = _controls(root)
    paths = {
        'docker_session_runtime': controls / 'tools/docker_session_runtime.py',
        'producer_stop': controls / 'experiments/native-network-preflight/v2-effect-windows/producer_stop.py',
        'native_run': controls / 'experiments/native-network-preflight/v2-effect-windows/native_run.py',
    }
    for name, path in paths.items():
        if name in sys.modules:
            if Path(sys.modules[name].__file__).resolve() != path.resolve():
                _fail('control_import_origin_mismatch')
            continue
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            _fail('control_import_unavailable')
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    native = sys.modules['native_run']
    expected = controls / 'experiments/native-network-preflight/v2_connect.py'
    if Path(native.NativeRun('unused', 'unused', 1, []).argv[1]).resolve() != expected.resolve():
        _fail('connect_origin_mismatch')
    return native, sys.modules['producer_stop']


def _save_resources(root: Path, nonce: str, rows: list[dict]) -> None:
    _write_json(_controls(root) / 'resources.json', {'nonce': nonce, 'resources': rows})


def _declare_resource(root: Path, nonce: str, rows: list[dict], kind: str, name: str, role: str) -> None:
    rows.append({'kind': kind, 'name': name, 'id': None, 'role': role})
    _save_resources(root, nonce, rows)


def _seal_resource(root: Path, nonce: str, rows: list[dict], identifier: str) -> None:
    if not HEX_RE.fullmatch(identifier):
        _fail('docker_resource_id_invalid')
    if not rows or rows[-1].get('id') is not None:
        _fail('resource_declaration_missing')
    rows[-1]['id'] = identifier
    _save_resources(root, nonce, rows)


def _network(root: Path, nonce: str, rows: list[dict], role: str, *, internal: bool) -> tuple[str, str, str]:
    name = 'lrh-native-' + nonce[:12] + '-' + role
    arguments = ['network', 'create'] + (['--internal'] if internal else [])
    arguments += ['--label', LABEL + '=' + nonce, name]
    _declare_resource(root, nonce, rows, 'network', name, role)
    identifier = _docker(*arguments).stdout.decode().strip()
    _seal_resource(root, nonce, rows, identifier)
    info = _inspect('network', identifier)
    configs = (info.get('IPAM') or {}).get('Config') or []
    if (info.get('Id') != identifier or info.get('Name') != name or info.get('Driver') != 'bridge'
            or info.get('Labels', {}).get(LABEL) != nonce
            or info.get('Internal') is not internal or len(configs) != 1):
        _fail('network_boundary_invalid')
    try:
        network = ipaddress.ip_network(configs[0]['Subnet'], strict=True)
    except (KeyError, ValueError):
        _fail('network_subnet_invalid')
    if not isinstance(network, ipaddress.IPv4Network) or network.num_addresses < 32:
        _fail('network_subnet_invalid')
    relay_ip = str(network.network_address + 10)
    target_ip = str(network.network_address + 11)
    if configs[0].get('Gateway') in (relay_ip, target_ip):
        _fail('network_reserved_ip_conflict')
    return identifier, relay_ip, target_ip


def _mount(source: Path, destination: str, *, readonly: bool = False) -> str:
    source = source.resolve(strict=True)
    if any(char in str(source) for char in (',', '\n', '\r')) or not destination.startswith('/'):
        _fail('docker_mount_invalid')
    return 'type=bind,src=' + str(source) + ',dst=' + destination + (',readonly' if readonly else '')


def _create(root: Path, nonce: str, rows: list[dict], role: str, image: str, platform: str,
            network: str, ip: str | None, mounts: list[str], environment: list[str],
            command: list[str], *, workdir: str = '/workspace/project', dns_isolated: bool = True) -> str:
    if len({item.split('=', 1)[0] for item in environment}) != len(environment):
        _fail('container_environment_duplicate')
    name = 'lrh-native-' + nonce[:12] + '-' + role
    arguments = ['container', 'create', '--name', name, '--pull', 'never', '--platform', platform,
                 '--network', network, '--read-only', '--restart', 'no', '--log-driver', 'none',
                 '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges=true',
                 '--user', f'{os.getuid()}:{os.getgid()}', '--memory', '1g', '--cpus', '1',
                 '--pids-limit', '64', '--tmpfs', '/tmp:rw,nosuid,nodev,size=128m',
                 '--label', LABEL + '=' + nonce,
                 '--label', OWNER_LABEL + '=docker-session-v1',
                 '--label', NONCE_LABEL + '=' + nonce, '--workdir', workdir]
    if ip is not None:
        arguments += ['--ip', ip]
    if dns_isolated:
        arguments += ['--dns', '127.0.0.1']
    for mount in mounts:
        arguments += ['--mount', mount]
    for item in environment:
        arguments += ['--env', item]
    arguments += ['--entrypoint', command[0], image, *command[1:]]
    _declare_resource(root, nonce, rows, 'container', name, role)
    identifier = _docker(*arguments).stdout.decode().strip()
    _seal_resource(root, nonce, rows, identifier)
    info = _inspect('container', identifier)
    if (info.get('Id') != identifier or info.get('Image') != image
            or info.get('State', {}).get('Status') != 'created'
            or info.get('Name') != '/' + name
            or info.get('Config', {}).get('Image') != image
            or info.get('Config', {}).get('Labels', {}).get(LABEL) != nonce
            or info.get('Config', {}).get('User') != f'{os.getuid()}:{os.getgid()}'
            or info.get('Config', {}).get('WorkingDir') != workdir
            or info.get('Config', {}).get('Entrypoint') != [command[0]]
            or info.get('Config', {}).get('Cmd') not in ([*command[1:]], None if len(command) == 1 else [*command[1:]])
            or info.get('HostConfig', {}).get('ReadonlyRootfs') is not True
            or info.get('HostConfig', {}).get('Privileged') is not False
            or info.get('HostConfig', {}).get('CapDrop') != ['ALL']
            or 'no-new-privileges=true' not in info.get('HostConfig', {}).get('SecurityOpt', [])
            or info.get('HostConfig', {}).get('PidsLimit') != 64
            or info.get('HostConfig', {}).get('Memory') != 1024 * 1024 * 1024
            or info.get('HostConfig', {}).get('NanoCpus') != 1000000000
            or info.get('HostConfig', {}).get('LogConfig', {}).get('Type') != 'none'
            or info.get('HostConfig', {}).get('RestartPolicy', {}).get('Name') != 'no'
            or info.get('HostConfig', {}).get('Dns') != (['127.0.0.1'] if dns_isolated else [])
            or set(info.get('NetworkSettings', {}).get('Networks', {})) !=
                {str(_inspect('network', network).get('Name'))}):
        _fail('container_create_mismatch')
    network_state = next(iter(info['NetworkSettings']['Networks'].values()))
    if ip is not None and network_state.get('IPAddress') != ip:
        _fail('container_network_ip_mismatch')
    actual_mounts = {(item.get('Source'), item.get('Destination'), item.get('RW'))
                     for item in info.get('Mounts', [])}
    expected_mounts = set()
    for mount in mounts:
        fields = dict(part.split('=', 1) for part in mount.split(',') if '=' in part)
        expected_mounts.add((fields['src'], fields['dst'], 'readonly' not in mount.split(',')))
    if actual_mounts != expected_mounts:
        _fail('container_mount_mismatch')
    actual_env = dict(item.split('=', 1) for item in info.get('Config', {}).get('Env', []) if '=' in item)
    expected_env = dict(item.split('=', 1) for item in environment)
    inherited_rows = (_inspect('image', image).get('Config') or {}).get('Env') or []
    allowed_inherited = dict(item.split('=', 1) for item in inherited_rows if '=' in item)
    if (any(actual_env.get(key) != value for key, value in expected_env.items())
            or any(actual_env.get(key) != value for key, value in allowed_inherited.items())
            or set(actual_env) != set(expected_env) | set(allowed_inherited)
            or any(SENSITIVE_ENV.search(key) and value for key, value in actual_env.items())
            or any('PROXY' in key.upper() and key not in expected_env and value
                   for key, value in actual_env.items())
            or any(key.startswith(('LD_', 'BUN_', 'OPENCODE_'))
                   and key not in expected_env and key not in allowed_inherited and value
                   for key, value in actual_env.items())):
        _fail('container_environment_mismatch')
    return identifier


def _created_manifest(root: Path, nonce: str, rows: list[dict], producer) -> Path:
    containers = [row for row in rows if row['kind'] == 'container']
    if len(containers) != 8 or any(row.get('id') is None for row in containers):
        _fail('producer_set_incomplete')
    items = []
    for row in containers:
        info = _inspect('container', row['id'])
        if (info['State']['Status'] != 'created' or info['Config']['Labels'].get(LABEL) != nonce):
            _fail('producer_not_created_stopped')
        items.append({'id': row['id'], 'binding': producer.binding(info)})
    path = _controls(root) / 'producer-manifest.json'
    _write_json(path, {'version': 1, 'nonce': nonce, 'producers': items}, once=True)
    return path


def _research_environment(root: Path, base: str, relay_ip: str, target_ip: str,
                          capability: str) -> list[str]:
    proxy = 'http://run:' + capability + '@' + relay_ip + ':8080'
    no_proxy = 'localhost,127.0.0.1,::1,' + target_ip
    return [
        'HOME=/workspace/home', 'XDG_CONFIG_HOME=/workspace/config',
        'XDG_DATA_HOME=/workspace/data', 'XDG_CACHE_HOME=/workspace/cache',
        'XDG_STATE_HOME=/workspace/state', 'TMPDIR=/workspace/tmp',
        'HTTP_PROXY=' + proxy, 'HTTPS_PROXY=' + proxy,
        'http_proxy=' + proxy, 'https_proxy=' + proxy,
        'ALL_PROXY=', 'all_proxy=', 'FTP_PROXY=', 'ftp_proxy=',
        'NO_PROXY=' + no_proxy, 'no_proxy=' + no_proxy,
        'SSL_CERT_FILE=/runtime-ca.pem', 'SSL_CERT_DIR=', 'CURL_CA_BUNDLE=',
        'REQUESTS_CA_BUNDLE=', 'NODE_EXTRA_CA_CERTS=',
        'GIT_SSL_CAINFO=', 'GIT_SSL_NO_VERIFY=', 'NO_COLOR=1',
    ]


def _write_target_info(root: Path, role: str, target_ip: str, plan: dict) -> None:
    _write_json(root / role / 'project/target.json', {
        'url': f'http://{target_ip}:{plan["target_port"]}',
        'source_manifest_sha256': plan['source_manifest_sha256'],
        'role': role,
    }, once=True)


def _preseal(root: Path, plan: dict, nonce: str, rows: list[dict], port: int,
             capability: str) -> dict:
    external, _, _ = _network(root, nonce, rows, 'external', internal=False)
    research, research_relay_ip, research_target_ip = _network(
        root, nonce, rows, 'research', internal=True)
    reviews = {}
    for slot in ('reviewer-1', 'reviewer-2'):
        reviews[slot] = _network(root, nonce, rows, slot, internal=True)
    controls = _controls(root)
    platform = plan['platform']
    relay = _create(root, nonce, rows, 'relay', plan['image_id'], platform, external, None,
                    [_mount(controls / 'relay', '/relay', readonly=True)],
                    ['HOST_GATEWAY_PORT=' + str(port)], ['/relay'],
                    workdir='/', dns_isolated=False)
    network_names = {}
    for role, item in (('research', (research, research_relay_ip, research_target_ip)),
                       *((slot, reviews[slot]) for slot in ('reviewer-1', 'reviewer-2'))):
        network, relay_ip, _ = item
        _docker('network', 'connect', '--ip', relay_ip, network, relay)
        network_names[role] = _inspect('network', network)['Name']
        actual = _inspect('container', relay)['NetworkSettings']['Networks'][network_names[role]]
        if actual.get('IPAddress') != relay_ip:
            _fail('relay_internal_ip_mismatch')
    target_command = _validate_target_command(controls / 'target-command.json')
    targets = {}
    for role, item in (('target', (research, research_target_ip)),
                       ('review-target-1', (reviews['reviewer-1'][0], reviews['reviewer-1'][2])),
                       ('review-target-2', (reviews['reviewer-2'][0], reviews['reviewer-2'][2]))):
        network, ip = item
        targets[role] = _create(root, nonce, rows, role, plan['target_image_id'], platform,
                                network, ip, [_mount(root / role, '/target')],
                                ['HOME=/target', 'HTTP_PROXY=', 'HTTPS_PROXY=', 'ALL_PROXY=',
                                 'http_proxy=', 'https_proxy=', 'all_proxy=', 'NO_PROXY=*', 'no_proxy=*'],
                                target_command, workdir='/target')
    _write_target_info(root, 'researcher', research_target_ip, plan)
    for slot in ('reviewer-1', 'reviewer-2'):
        _write_target_info(root, slot, reviews[slot][2], plan)

    def create_research(role: str, network: str, relay_ip: str, target_ip: str) -> str:
        base = root / ('researcher' if role == 'resume' else role)
        mounts = [_mount(base, '/workspace'),
                  _mount(controls / 'opencode.json', '/workspace/config/opencode/opencode.json', readonly=True),
                  _mount(controls / 'runtime-ca.pem', '/runtime-ca.pem', readonly=True)]
        if role in ('reviewer-1', 'reviewer-2'):
            mounts.append(_mount(root / 'handoff' / role, '/handoff', readonly=True))
            mounts.append(_mount(root / 'original', '/workspace/original', readonly=True))
        return _create(root, nonce, rows, role, plan['image_id'], platform, network,
                       None, mounts, _research_environment(root, role, relay_ip, target_ip, capability),
                       ['sh', '-c', 'while :; do sleep 3600; done'])

    researcher = create_research('researcher', research, research_relay_ip, research_target_ip)
    reviewers = {slot: create_research(slot, reviews[slot][0], reviews[slot][1], reviews[slot][2])
                 for slot in ('reviewer-1', 'reviewer-2')}
    resume = create_research('resume', research, research_relay_ip, research_target_ip)
    if set(_inspect('container', relay)['NetworkSettings']['Networks']) != {
            _inspect('network', external)['Name'], *network_names.values()}:
        _fail('relay_network_membership_mismatch')
    return {
        'relay': relay, 'researcher': researcher, 'resume': resume, **reviewers, **targets,
        'research_target_ip': research_target_ip,
        'review_target_ips': {slot: reviews[slot][2] for slot in reviewers},
        'network_names': network_names,
    }


def _cleanup_resources(root: Path, *, require_created: bool = False) -> dict:
    record = _read_json(_controls(root) / 'resources.json')
    nonce = record.get('nonce')
    if not isinstance(nonce, str) or not re.fullmatch(r'[0-9a-f]{32}', nonce):
        _fail('resource_record_invalid')
    results = []
    def absent(kind: str, value: str) -> bool:
        if kind == 'container':
            result = _docker('container', 'ls', '-a', '--no-trunc', '--filter', 'id=' + value,
                             '--format', '{{.ID}}')
        else:
            result = _docker('network', 'ls', '--no-trunc', '--filter', 'id=' + value,
                             '--format', '{{.ID}}')
        return not result.stdout.strip()

    for row in reversed(record.get('resources', [])):
        kind, name, identifier = row.get('kind'), row.get('name'), row.get('id')
        if kind not in ('container', 'network') or not isinstance(name, str):
            _fail('resource_record_invalid')
        if identifier is None:
            # The create call may have succeeded before its id was durably sealed.
            try:
                info = _inspect(kind, name)
            except NativeResearchError:
                # An unsealed create may be absent, but do not infer that from inspect failure alone.
                listing = (_docker('container', 'ls', '-a', '--no-trunc', '--filter', 'name=^/' + name + '$',
                                   '--format', '{{.ID}}') if kind == 'container' else
                           _docker('network', 'ls', '--no-trunc', '--filter', 'name=^' + name + '$',
                                   '--format', '{{.ID}}'))
                if listing.stdout.strip():
                    _fail('resource_cleanup_unsealed_ambiguous')
                results.append({'kind': kind, 'name': name, 'absent': True})
                continue
            identifier = info.get('Id')
        try:
            info = _inspect(kind, identifier)
        except NativeResearchError:
            if not absent(kind, identifier):
                _fail('resource_cleanup_inspection_ambiguous')
            results.append({'kind': kind, 'name': name, 'absent': True})
            continue
        labels = (info.get('Config', {}).get('Labels') if kind == 'container' else info.get('Labels')) or {}
        actual_name = info.get('Name', '').lstrip('/')
        if (info.get('Id') != identifier or actual_name != name
                or labels.get(LABEL) != nonce):
            _fail('resource_cleanup_identity_mismatch')
        if require_created and kind == 'container' and info.get('State', {}).get('Status') != 'created':
            _fail('prestart_resource_not_created_stopped')
        command = ('container', 'rm', '-f', identifier) if kind == 'container' else ('network', 'rm', identifier)
        _docker(*command)
        if not absent(kind, identifier):
            _fail('resource_cleanup_not_absent')
        results.append({'kind': kind, 'name': name, 'absent': True})
    result = {'status': 'complete', 'resources': results}
    _write_json(_controls(root) / 'cleanup.json', result)
    return result


def _provider_snapshot(root: Path) -> dict:
    path = _controls(root) / 'provider/tunnel.sqlite3'
    if not path.exists() or path.is_symlink():
        _fail('provider_ledger_unavailable')
    connection = sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True, timeout=1)
    try:
        row = connection.execute('SELECT config,created,bytes FROM pool').fetchone()
        if row is None:
            _fail('provider_pool_unavailable')
        config = json.loads(row[0])
        used = connection.execute('SELECT count(*) FROM tunnels').fetchone()[0]
        phases = connection.execute('SELECT phase,count(*) FROM tunnels GROUP BY phase').fetchall()
        return {'config': config, 'created': row[1], 'used_tunnels': used,
                'charged_tunnel_bytes': row[2], 'tunnel_phases': dict(phases)}
    finally:
        connection.close()


def run_active(run_root: Path) -> bool:
    root = _private_root(Path(run_root))
    native, _ = _activate_controls(root)
    return native.active(_controls(root) / 'native-state')


def allowance_snapshot(run_root: Path) -> dict:
    root = _private_root(Path(run_root))
    native, _ = _activate_controls(root)
    run = native.snapshot(_controls(root) / 'native-state')
    pool = _provider_snapshot(root)
    config = pool['config']
    if (config.get('authority') != AUTHORITY or config.get('producer_manifest_sha256') != run['manifest_sha256']
            or config.get('native_run_duration') != _plan(root)['limits']['duration_seconds']):
        _fail('shared_allowance_identity_mismatch')
    return {'run_identity': {key: run[key] for key in
                            ('manifest_sha256', 'nonce', 'ids', 'deadline_monotonic', 'created_monotonic')},
            'hard_limits': {'max_connections': config['max_connections'],
                            'max_bytes': config['max_bytes'], 'duration_seconds': config['duration']},
            'used_tunnels': pool['used_tunnels'],
            'charged_tunnel_bytes': pool['charged_tunnel_bytes'],
            'active': native.active(_controls(root) / 'native-state'),
            'provider_request_count': None, 'monetary_spend': None}


def _resources(root: Path) -> dict:
    record = _read_json(_controls(root) / 'resources.json')
    if any(row.get('id') is None for row in record.get('resources', [])):
        _fail('unsealed_resource_record')
    return {row['role']: row['id'] for row in record['resources'] if row['kind'] == 'container'}


@contextmanager
def _turn_lock(root: Path):
    path = _controls(root) / 'turn.lock'
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


@contextmanager
def _owner_lock(root: Path):
    descriptor = os.open(_controls(root) / 'owner.lock',
                         os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            _fail('live_owner_present')
        yield
    finally:
        os.close(descriptor)


def _native_exec(root: Path, role: str, argv: list[str], timeout_seconds: int) -> subprocess.CompletedProcess[bytes]:
    if role not in ('researcher', 'resume', 'reviewer-1', 'reviewer-2'):
        _fail('native_role_invalid')
    plan = _verified_plan(root)
    identifier = _resources(root)[role]
    info = _inspect('container', identifier)
    if (info.get('Image') != plan['image_id'] or info.get('State', {}).get('Running') is not True
            or info.get('Config', {}).get('Labels', {}).get(LABEL) !=
            _read_json(_controls(root) / 'resources.json')['nonce']):
        _fail('native_container_identity_invalid')
    native, _ = _activate_controls(root)
    state = _controls(root) / 'native-state'
    command = [str(DOCKER_BINARY), 'container', 'exec', '-w', '/workspace/project', identifier,
               '/usr/local/bin/opencode', *argv]
    with native.dispatch_guard(state):
        try:
            child = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     env={key: value for key, value in os.environ.items()
                                          if key in ('HOME', 'PATH', 'DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_CONFIG')})
        except OSError:
            _fail('native_dispatch_unknown_effect')
    try:
        stdout, stderr = child.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        child.terminate()
        try:
            child.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.communicate()
        _fail('native_dispatch_timeout_unknown_effect')
    if len(stdout) > 16 * 1024 * 1024 or len(stderr) > 1024 * 1024:
        _fail('native_dispatch_output_oversize_unknown_effect')
    return subprocess.CompletedProcess(command, child.returncode, stdout, stderr)


def native_api(run_root: Path, role: str, *parts: str) -> dict:
    root = _private_root(Path(run_root))
    if (not parts or parts[0] not in ('session.create', 'session.list', 'session.get', 'session.message.list')
            or len(parts) > 12 or any(not isinstance(part, str) or len(part) > 4096 for part in parts)):
        _fail('native_api_call_not_allowed')
    with _turn_lock(root):
        if _unresolved_dispatches(root):
            _fail('prior_dispatch_unknown_effect')
        result = _native_exec(root, role, ['api', '--standalone', *parts], 90)
    if result.returncode:
        _fail('native_api_effect_unknown')
    try:
        value = json.loads(result.stdout)
    except (UnicodeError, ValueError):
        _fail('native_api_response_invalid')
    if not isinstance(value, dict):
        _fail('native_api_response_invalid')
    return value


def _summarize_native(stdout: str, session_id: str) -> dict:
    events = []
    for line in stdout.splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            _fail('native_jsonl_invalid')
        if not isinstance(item, dict):
            _fail('native_jsonl_invalid')
        events.append(item)
    if not events or session_id not in {item.get('sessionID') for item in events}:
        _fail('native_session_evidence_missing')
    parts = [item['part'] for item in events if isinstance(item.get('part'), dict)]
    if any(item.get('type') == 'error' or item.get('error') for item in events) or any(
            item.get('error') or (item.get('type') == 'tool' and
            isinstance(item.get('state'), dict) and item['state'].get('status') in ('error', 'failed'))
            for item in parts):
        _fail('native_event_error_unknown_effect')
    event_names = {'step_finish', 'step_start', 'text', 'tool_use', 'error'}
    tool_names = {'read', 'glob', 'grep', 'edit', 'write', 'shell', 'patch', 'question',
                  'skill', 'subagent', 'webfetch', 'websearch'}
    return {'event_types': sorted({item.get('type') if item.get('type') in event_names else 'other'
                                   for item in events}),
            'tool_names': sorted({item.get('tool') if item.get('tool') in tool_names else 'other'
                                  for item in parts if item.get('type') == 'tool'}),
            'tool_count': sum(item.get('type') == 'tool' for item in parts)}


def _protected_trace(stdout: str, session_id: str) -> dict:
    """Preserve native event order and hashes without storing model or tool text."""
    rows = []
    for number, line in enumerate(stdout.splitlines(), 1):
        event = json.loads(line)
        part = event.get('part') if isinstance(event.get('part'), dict) else {}
        state = part.get('state') if isinstance(part.get('state'), dict) else {}
        row = {'line': number,
               'event_type': event.get('type') if event.get('type') in
               ('step_finish', 'step_start', 'text', 'tool_use', 'error') else 'other',
               'session_matches': event.get('sessionID') == session_id,
               'part_type': part.get('type') if part.get('type') in
               ('step-finish', 'step-start', 'text', 'tool', 'error', 'usage') else 'other'}
        if part.get('type') == 'tool':
            row.update({'tool': part.get('tool') if part.get('tool') in
                        ('read', 'glob', 'grep', 'edit', 'write', 'shell', 'patch', 'question',
                         'skill', 'subagent', 'webfetch', 'websearch') else 'other',
                        'status': state.get('status') if state.get('status') in
                        ('completed', 'running', 'pending', 'error', 'failed') else 'other',
                        'input_sha256': hashlib.sha256(json.dumps(state.get('input'), sort_keys=True,
                                                          default=str).encode()).hexdigest(),
                        'output_sha256': hashlib.sha256(json.dumps(state.get('output'), sort_keys=True,
                                                           default=str).encode()).hexdigest()})
        elif part.get('type') == 'text':
            row['text_sha256'] = hashlib.sha256(str(part.get('text', '')).encode()).hexdigest()
        rows.append(row)
    return {'kind': 'protected-native-event-trace-v1', 'session_id': session_id,
            'source': 'actual opencode run --format json stdout',
            'stdout_sha256': hashlib.sha256(stdout.encode()).hexdigest(), 'events': rows}


def _unresolved_dispatches(root: Path) -> list[str]:
    unresolved = []
    for path in (_controls(root) / 'dispatch').glob('*.json'):
        record = _read_json(path)
        if record.get('status') == 'unknown_effect':
            unresolved.append(record.get('dispatch_id', path.stem))
    return sorted(unresolved)


def invoke_native(run_root: Path, role: str, session_id: str, prompt: str,
                  include_raw: bool = False, before_dispatch=None) -> dict:
    root = _private_root(Path(run_root))
    if (role not in ('researcher', 'resume', 'reviewer-1', 'reviewer-2')
            or not SESSION_RE.fullmatch(session_id) or not isinstance(prompt, str)
            or not 1 <= len(prompt.encode()) <= 128 * 1024):
        _fail('native_turn_input_invalid')
    if CREDENTIAL_TEXT.search(prompt):
        _fail('native_prompt_credential_like')
    if before_dispatch is not None and not callable(before_dispatch):
        _fail('native_observer_hook_invalid')
    if role.startswith('reviewer-'):
        target = 'review-target-' + role[-1]
        plan = _plan(root)
        _verify_target_state(root / target, plan['source_sha256'], plan['mutable_paths'])
        target_id = _resources(root)[target]
        source_digest = plan['source_manifest_sha256']
    else:
        target_id = None
        source_digest = None
    dispatch_id = uuid.uuid4().hex
    record_path = _controls(root) / 'dispatch' / (dispatch_id + '.json')
    record = {'kind': 'native-dispatch-v1', 'status': 'unknown_effect',
              'dispatch_id': dispatch_id, 'role': role, 'session_id': session_id,
              'protected_capture': 'unavailable',
              'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
              'created_at': datetime.now(timezone.utc).isoformat(),
              'review_target_id': target_id,
              'review_target_source_sha256': source_digest}
    with _turn_lock(root):
        if _unresolved_dispatches(root):
            _fail('prior_dispatch_unknown_effect')
        if not run_active(root):
            _fail('native_run_closed_before_dispatch')
        pool_before = allowance_snapshot(root)
        record['pool_before'] = pool_before
        _write_json(record_path, record, once=True)
        try:
            if before_dispatch is not None:
                before_dispatch(root, dispatch_id)
                record['observer_arm_status'] = 'armed_before_native_exec'
                _write_json(record_path, record)
            result = _native_exec(root, role,
                                  ['run', '--standalone', '--agent', 'build', '--model', MODEL,
                                   '--format', 'json', '--session', session_id, prompt],
                                  min(3600, max(30, _plan(root)['limits']['duration_seconds'])))
            stdout = result.stdout.decode('utf-8')
            stderr = result.stderr.decode('utf-8')
            if result.returncode:
                _fail('native_turn_exit_unknown_effect')
            summary = _summarize_native(stdout, session_id)
            trace_path = _controls(root) / 'dispatch' / (dispatch_id + '.trace.json')
            _write_json(trace_path, _protected_trace(stdout, session_id), once=True)
            usage = {'status': 'unavailable'}
            if run_active(root):
                try:
                    observed = _native_exec(root, role, ['api', '--standalone', 'session.get',
                                                        '--param', 'sessionID=' + session_id], 90)
                    detail = json.loads(observed.stdout).get('data') if observed.returncode == 0 else None
                    if isinstance(detail, dict) and detail.get('id') == session_id:
                        usage = {'status': 'observed', 'id': session_id,
                                 'cost': detail.get('cost'), 'tokens': detail.get('tokens')}
                except (NativeResearchError, UnicodeError, ValueError):
                    pass
            pool_after = allowance_snapshot(root)
            record.update({'status': 'acknowledged', 'stdout_sha256': hashlib.sha256(result.stdout).hexdigest(),
                           'stderr_sha256': hashlib.sha256(result.stderr).hexdigest(),
                           **summary, 'pool_before': pool_before, 'pool_after': pool_after,
                           'native_trace_sha256': _sha(trace_path), 'native_usage': usage})
            _write_json(record_path, record)
            returned = dict(record)
            if include_raw:
                returned['_raw_stdout'] = stdout
            return returned
        except Exception:
            # The durable pre-dispatch record remains uncertain; no automatic retry.
            return dict(record)


def _probe_target(root: Path, container_id: str, target_ip: str, port: int) -> None:
    code = ('$s=@stream_socket_client("tcp://".$argv[1].":".$argv[2],$e,$m,2);'
            'if(!$s)exit(2);fclose($s);echo "connected";')
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and run_active(root):
        result = _docker('container', 'exec', container_id, 'php', '-r', code,
                         target_ip, str(port), timeout=5, allow_failure=True)
        if result.returncode == 0 and result.stdout == b'connected':
            return
        time.sleep(.25)
    _fail('owned_target_route_unavailable')


def _surface_probe(root: Path, container_id: str) -> dict:
    version = _docker('container', 'exec', container_id, '/usr/local/bin/opencode', '--version')
    if version.stdout.decode(errors='replace').strip() != VERSION:
        _fail('opencode_version_mismatch')
    db = _docker('container', 'exec', container_id, '/usr/local/bin/opencode', 'debug', 'paths', 'db')
    if db.stdout.decode(errors='replace').strip() != '/workspace/data/opencode/opencode.db':
        _fail('opencode_store_path_mismatch')
    command = [str(DOCKER_BINARY), 'container', 'exec', '-w', '/workspace/project', container_id,
               '/bin/sh', '-c', 'echo $$; exec /usr/local/bin/opencode serve --hostname 127.0.0.1 --port 4096']
    server = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, bufsize=1)
    pid = None
    try:
        if not select.select([server.stdout], [], [], 10)[0]:
            _fail('surface_server_unavailable')
        pid = int(server.stdout.readline().strip())
        password = None
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and not password:
            if select.select([server.stdout], [], [], 1)[0]:
                match = re.search(r'server password ([^\s]+)', server.stdout.readline())
                if match:
                    password = match.group(1)
            if server.poll() is not None:
                break
        if not password:
            _fail('surface_server_password_unavailable')
        header = 'Authorization: Basic ' + base64.b64encode(('opencode:' + password).encode()).decode()

        def get(endpoint: str):
            result = _docker('container', 'exec', container_id, 'wget', '-qO-', '--header', header,
                             'http://127.0.0.1:4096/api/' + endpoint, timeout=15)
            try:
                value = json.loads(result.stdout)
            except (UnicodeError, ValueError):
                _fail('surface_api_invalid')
            return value.get('data', value) if isinstance(value, dict) else value

        for _ in range(50):
            agents, plugins = get('agent'), get('plugin')
            if agents and plugins and len(agents[0].get('permissions', [])) >= 12:
                break
            time.sleep(.1)
        configs = get('config')
        document = next((row.get('info') for row in configs if row.get('type') == 'document'), None)
        skills, mcp, references, commands = (get(endpoint) for endpoint in
                                              ('skill', 'mcp', 'reference', 'command'))
        if (not isinstance(document, dict) or not isinstance(agents, list)
                or not isinstance(plugins, list) or not isinstance(skills, list)
                or not isinstance(mcp, list) or not isinstance(references, list)
                or not isinstance(commands, list)):
            _fail('surface_inventory_invalid')
        plugin_ids = sorted(item.get('id') for item in plugins)
        tools = sorted(item.removeprefix('opencode.tool.') for item in plugin_ids
                       if isinstance(item, str) and item.startswith('opencode.tool.'))
        inventory = {
            'config_sources': [{'type': row.get('type'), 'path': row.get('path')} for row in configs],
            'effective_config': {key: document.get(key) for key in
                                 ('model', 'fallback', 'permissions', 'policies', 'plugins', 'mcp', 'websearch')},
            'agents': [{'id': row.get('id'), 'mode': row.get('mode'),
                        'permissions': row.get('permissions')} for row in agents],
            'plugin_ids': plugin_ids, 'registered_tool_names': tools,
            'skill_ids': sorted(item.get('id') for item in skills),
            'mcp_count': len(mcp), 'reference_count': len(references),
            'command_count': len(commands), 'native_db_path': '/workspace/data/opencode/opencode.db',
        }
        effective = inventory['effective_config']
        if (effective['model'] != {'providerID': 'opencode', 'model': 'deepseek-v4.1-flash-free'}
                or effective['fallback'] is not None
                or effective['permissions'] != CONFIG['permissions']
                or effective['policies'] != CONFIG['policies']
                or effective['plugins'] != [] or effective['websearch'] is not False
                or effective['mcp'] != CONFIG['mcp']
                or inventory['mcp_count'] != 0
                or inventory['skill_ids'] != _plan(root)['expected_skill_ids']
                or not {'edit', 'write', 'shell'} <= set(tools)
                or not any(agent['id'] == 'build' and agent['mode'] == 'primary'
                           for agent in inventory['agents'])
                or not any(row['path'] == '/workspace/config/opencode/opencode.json'
                           for row in inventory['config_sources'])):
            _fail('loaded_surface_mismatch')
        return inventory
    finally:
        if pid is not None:
            _docker('container', 'exec', container_id, 'kill', '-TERM', str(pid),
                    allow_failure=True)
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
        server.stdout.close()


def start(run_root: Path, approval_path: Path) -> dict:
    root = _private_root(Path(run_root))
    with _owner_lock(root):
        return _start_owned(root, Path(approval_path))


def _start_owned(run_root: Path, approval_path: Path) -> dict:
    root = _private_root(Path(run_root))
    plan = _verified_plan(root, pristine=True)
    _approval(root, plan, Path(approval_path))
    controls = _controls(root)
    if (controls / 'resources.json').exists() or (controls / 'native-state/RUN.json').exists():
        _fail('run_already_started_or_ambiguous')
    _image(plan['image_id'], plan['platform'], official=True)
    _image(plan['target_image_id'], plan['platform'])
    nonce = uuid.uuid4().hex
    capability = 'local_' + uuid.uuid4().hex
    capability_path = controls / 'capability'
    descriptor = os.open(capability_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        stream.write(capability)
        stream.flush()
        os.fsync(stream.fileno())
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    rows: list[dict] = []
    _save_resources(root, nonce, rows)
    native = None
    result = {'status': 'start_incomplete', 'run_root': str(root)}
    try:
        bindings = _preseal(root, plan, nonce, rows, port, capability)
        _, producer = _activate_controls(root)
        manifest = _created_manifest(root, nonce, rows, producer)
        native_module, _ = _activate_controls(root)
        proxy_args = ['--state-dir', str(controls / 'provider'),
                      '--capability-file', str(capability_path),
                      '--max-connections', str(plan['limits']['max_connections']),
                      '--max-bytes', str(plan['limits']['max_bytes']),
                      '--duration', str(plan['limits']['duration_seconds']), '--port', str(port)]
        native = native_module.NativeRun(manifest, controls / 'native-state',
                                         plan['limits']['duration_seconds'], proxy_args)
        ready = native.start()
        if (ready['proxy_info'].get('authority') != AUTHORITY
                or ready['proxy_info'].get('port') != port
                or ready['proxy_info'].get('host') != '127.0.0.1'
                or ready['ids'] != [row['id'] for row in rows if row['kind'] == 'container']):
            _fail('native_authority_readback_mismatch')
        _probe_target(root, bindings['researcher'], bindings['research_target_ip'], plan['target_port'])
        for role in ('reviewer-1', 'reviewer-2'):
            _probe_target(root, bindings[role], bindings['review_target_ips'][role], plan['target_port'])
        surface = _surface_probe(root, bindings['researcher'])
        _write_json(controls / 'loaded-surface.json', surface, once=True)
        _write_json(controls / 'activation.json', {
            'kind': 'native-research-activation-v1', 'nonce': nonce,
            'plan_sha256': _sha(root / 'plan.json'), 'manifest_sha256': _sha(manifest),
            'watcher_pid': ready['watcher_pid'], 'started_at': datetime.now(timezone.utc).isoformat(),
            'provider_route': PROVIDER_ROUTE, 'provider_authority': AUTHORITY,
            'model': MODEL, 'limits': plan['limits'],
            'protected_capture': 'unavailable',
            'loaded_surface_sha256': _sha(controls / 'loaded-surface.json'),
        }, once=True)
        result = {'status': 'active', 'run_root': str(root), 'run_identity': allowance_snapshot(root)['run_identity'],
                  'target_url': f'http://{bindings["research_target_ip"]}:{plan["target_port"]}',
                  'protected_capture': 'unavailable',
                  'provider_request_count': None, 'monetary_spend': None}
        print(json.dumps(result, sort_keys=True), flush=True)
        while native_module.active(controls / 'native-state') and native.process.poll() is None:
            time.sleep(.2)
    finally:
        if native is not None:
            try:
                result['native_stop'] = native.close()
            except Exception:
                result['native_stop'] = {'status': 'unresolved'}
        else:
            result['native_stop'] = {'status': 'not_started'}
        if result['native_stop']['status'] in ('stopped', 'closed_before_activation', 'not_started'):
            try:
                result['cleanup'] = _cleanup_resources(root)
            except Exception:
                result['cleanup'] = {'status': 'unresolved'}
        capability_path.unlink(missing_ok=True)
        result['status'] = ('stopped_complete' if result.get('status') == 'active'
                            and result['native_stop']['status'] == 'stopped'
                            and result.get('cleanup', {}).get('status') == 'complete' else
                            'start_incomplete' if result.get('status') == 'start_incomplete' else
                            'unsafe_or_unresolved')
        _write_json(controls / 'final.json', result)
    return result


def stop(run_root: Path) -> dict:
    root = _private_root(Path(run_root))
    if not (_controls(root) / 'native-state/RUN.json').exists():
        return {'status': 'not_active', 'run_root': str(root)}
    native, _ = _activate_controls(root)
    native.request_stop(_controls(root) / 'native-state', 'operator_stop')
    return {'status': 'stop_requested', 'run_root': str(root)}


def recover_start(run_root: Path) -> dict:
    """Remove exact stopped preactivation resources after owner loss, never a live run."""
    root = _private_root(Path(run_root))
    with _owner_lock(root):
        _verified_plan(root)
        controls = _controls(root)
        if not (controls / 'resources.json').exists():
            return {'status': 'no_resources', 'run_root': str(root)}
        state = controls / 'native-state'
        if (state / 'RUN.json').exists():
            if (state / 'UNSAFE').exists() or not any((state / name).exists()
                                                      for name in ('REVOKED', 'STARTUP_CLOSED')):
                _fail('native_run_not_verified_stopped')
            require_created = False
        else:
            require_created = True
        result = _cleanup_resources(root, require_created=require_created)
        recovery = {'status': 'recovered_exact_resources', 'run_root': str(root),
                    'native_state': 'not_activated' if require_created else 'verified_stopped',
                    'cleanup': result}
        _write_json(controls / 'recovery.json', recovery)
        return recovery


def status(run_root: Path) -> dict:
    root = _private_root(Path(run_root))
    plan = _plan(root)
    controls = _controls(root)
    final = _read_json(controls / 'final.json') if (controls / 'final.json').exists() else None
    recovery = _read_json(controls / 'recovery.json') if (controls / 'recovery.json').exists() else None
    activation = _read_json(controls / 'activation.json') if (controls / 'activation.json').exists() else None
    try:
        allowance = allowance_snapshot(root) if activation else None
    except (NativeResearchError, OSError, sqlite3.Error):
        allowance = None
    dispatches = []
    for path in sorted((controls / 'dispatch').glob('*.json')):
        if path.name.endswith('.trace.json'):
            continue
        row = _read_json(path)
        dispatches.append({key: row.get(key) for key in
                           ('dispatch_id', 'role', 'session_id', 'status', 'created_at')})
    return {'status': 'active' if allowance and allowance['active'] else
            'stopped_complete' if final and final.get('status') == 'stopped_complete' else
            'recovered_exact_resources' if recovery and recovery.get('status') == 'recovered_exact_resources' else
            'prepared' if not activation and not final and not (controls / 'resources.json').exists()
            else 'inactive_or_unresolved',
            'run_root': str(root), 'model': plan['model'], 'limits': plan['limits'],
            'allowance': allowance, 'dispatches': dispatches, 'final': final, 'recovery': recovery,
            'protected_capture': 'unavailable',
            'provider_request_count': None, 'monetary_spend': None}


def _load_review_module():
    path = ROOT / 'experiments/native-review-qualification/fresh_review.py'
    if not path.is_file():
        _fail('fresh_review_module_unavailable')
    spec = importlib.util.spec_from_file_location('native_fresh_review', path)
    if spec is None or spec.loader is None:
        _fail('fresh_review_module_unavailable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def review(run_root: Path, observer_root: Path, selection: Path,
           selection_sha256: str, role: str) -> dict:
    root = _private_root(Path(run_root))
    _verified_plan(root)
    if role not in ('reviewer-1', 'reviewer-2') or not HEX_RE.fullmatch(selection_sha256):
        _fail('review_input_invalid')
    if not run_active(root) or _unresolved_dispatches(root):
        _fail('review_run_closed_or_uncertain')
    module = _load_review_module()
    packet_dir = root / 'handoff' / role
    pin = module.prepare_packet(observer_root, selection, selection_sha256, packet_dir,
                                public_bytes=module.validate_public_bytes)
    receipt = module.invoke_fresh_review(root, packet_dir, pin, role,
                                         native_api=native_api, invoke_native=invoke_native,
                                         allowance_snapshot=allowance_snapshot,
                                         run_active=run_active,
                                         public_bytes=module.validate_public_bytes,
                                         independent_check=None)
    _write_json(_controls(root) / ('review-' + role + '.json'), receipt, once=True)
    return {'status': receipt['status'], 'assessment': receipt['assessment'],
            'reviewer_role': role, 'receipt_path': str(_controls(root) / ('review-' + role + '.json')),
            'same_original_allowance': receipt['same_original_allowance'],
            'independent_host_check': 'unavailable'}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare_cmd = commands.add_parser('prepare', help='provider-free sealed run preparation')
    for name in ('run-root', 'source', 'brief', 'scope-file', 'scope-sha256', 'relay',
                 'relay-sha256', 'runtime-ca', 'runtime-ca-sha256', 'target-command',
                 'image-id', 'target-image-id', 'platform'):
        prepare_cmd.add_argument('--' + name, required=True)
    prepare_cmd.add_argument('--target-port', type=int, required=True)
    prepare_cmd.add_argument('--mutable-path', action='append', default=[])
    prepare_cmd.add_argument('--expected-skill-id', action='append', default=[])
    prepare_cmd.add_argument('--model', default=MODEL)
    prepare_cmd.add_argument('--provider-route', default=PROVIDER_ROUTE)
    prepare_cmd.add_argument('--provider-authority', default=AUTHORITY)
    prepare_cmd.add_argument('--max-connections', type=int, default=DEFAULT_LIMITS['max_connections'])
    prepare_cmd.add_argument('--max-bytes', type=int, default=DEFAULT_LIMITS['max_bytes'])
    prepare_cmd.add_argument('--duration-seconds', type=int, default=DEFAULT_LIMITS['duration_seconds'])
    start_cmd = commands.add_parser('start', help='foreground live owner; requires fresh plan-bound approval')
    start_cmd.add_argument('--run-root', required=True)
    start_cmd.add_argument('--approval', required=True)
    for name in ('status', 'stop', 'recover-start'):
        item = commands.add_parser(name)
        item.add_argument('--run-root', required=True)
    research_cmd = commands.add_parser('research', help='one native turn in the original researcher')
    research_cmd.add_argument('--run-root', required=True)
    resume_cmd = commands.add_parser('resume', help='one native turn in the same persistent researcher store')
    resume_cmd.add_argument('--run-root', required=True)
    resume_cmd.add_argument('--prompt-file', required=True)
    resume_cmd.add_argument('--session', required=True)
    review_cmd = commands.add_parser('review', help='one fresh bounded reviewer on a frozen public packet')
    for name in ('run-root', 'observer-root', 'selection', 'selection-sha256'):
        review_cmd.add_argument('--' + name, required=True)
    review_cmd.add_argument('--role', choices=('reviewer-1', 'reviewer-2'), required=True)
    return parser


def main() -> int:
    os.umask(0o077)
    args = _parser().parse_args()
    try:
        if args.command == 'prepare':
            result = prepare(args)
        elif args.command == 'start':
            result = start(Path(args.run_root), Path(args.approval))
        elif args.command == 'stop':
            result = stop(Path(args.run_root))
        elif args.command == 'recover-start':
            result = recover_start(Path(args.run_root))
        elif args.command == 'status':
            result = status(Path(args.run_root))
        elif args.command in ('research', 'resume'):
            root = Path(args.run_root)
            role = 'researcher' if args.command == 'research' else 'resume'
            if args.command == 'research':
                prompt = _file(_controls(root) / 'BRIEF.md', private=True).read_text()
                sessions = native_api(root, role, 'session.list', '--param', 'limit=100',
                                      '--param', 'order=asc')
                if sessions.get('items', sessions.get('data')) != []:
                    _fail('researcher_store_not_fresh')
                created = native_api(root, role, 'session.create', '--data',
                                     '{"title":"native bounded research"}')
                session = (created.get('data') or {}).get('id')
            else:
                prompt = _file(Path(args.prompt_file), private=True).read_text()
                session = args.session
            if not isinstance(session, str) or not SESSION_RE.fullmatch(session):
                _fail('native_session_id_invalid')
            if role == 'resume':
                existing = native_api(root, role, 'session.get', '--param', 'sessionID=' + session)
                if (existing.get('data') or {}).get('id') != session:
                    _fail('resume_session_not_in_researcher_store')
            result = invoke_native(root, role, session, prompt)
        elif args.command == 'review':
            result = review(Path(args.run_root), Path(args.observer_root), Path(args.selection),
                            args.selection_sha256, args.role)
        else:
            _fail('command_invalid')
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0 if (result.get('status') not in ('unknown_effect', 'unfinished', 'start_incomplete',
                                                'unsafe_or_unresolved')
                     and result.get('independent_host_check') != 'unavailable') else 2
    except (NativeResearchError, OSError, ValueError, KeyError, sqlite3.Error) as error:
        code = str(error)
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,100}', code):
            code = 'native_research_unavailable'
        print(json.dumps({'status': 'rejected', 'code': code}, sort_keys=True))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
