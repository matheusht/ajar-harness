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
from contextlib import closing, contextmanager
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
    'experiments/native-review-qualification/fresh_review.py': 'ee5875bb5585aa80bf4a30291a1c7b5a4cfe0d317bebb774e4aee1e9e4763e42',
    'tools/docker_session_runtime.py': '9e8d36eed18387d4106d02a62b3ef7489845cb6da9ccbf57256c3a4432f47651',
    'tools/native_kanboard_origin_gate.py': 'bb59962e022e59cd6994149c2a2eaf1d26d0bf7b3963c41289520df13ff0658e',
    'tools/native_effect_recovery.py': 'a9a000be18229660f779912ec625ae753233f0ed78107265db9eeb8bf021db7c',
}
CAPTURE_FILES = {
    'evals/native-qualification/kanboard_native_capture.py': 'a14d3f02a9c2b24a69d344bfdd426026a9a67db1415cb1e3da4f271081e492c2',
    'evals/native-qualification/smoke/kanboard_effect_probe.php': '5484f9ac40a710ea5eb5492bc13b712211e5f1cbcde934e2548e946c8fa0379d',
    'evals/native-qualification/smoke/kanboard_effect_collector.php': '991d727e36b0c1fedc9898f4a773282ce7f062f8f00de4ae5dd05d2256b9e3b5',
    'evals/native-qualification/smoke/kanboard_role_broker.php': '2ee3d3806825f210071b73f53ade076e471f97237b81a0a66cc00632e6e97c8d',
}
CAPTURE_SOURCE_SHA = '056280086b353347075f0352b5826bd20ef7328854e7283e4c5cd71d7e57f839'
CAPTURE_CONTROLLER_SHA = '6df47c20fe6b1963bd14a86bc3cbd554fbcea9f622a23f67af115a854811aad6'
T01_CAPTURE_FILES = {
    'evals/native-qualification/kanboard_native_capture.py': 'a14d3f02a9c2b24a69d344bfdd426026a9a67db1415cb1e3da4f271081e492c2',
    'evals/native-qualification/smoke/t01_jsonrpc_broker.php': '84854db4eac14538200852a58d22e1cd0eaffc3f6fdd47603864ea3fa5f893e6',
    'evals/native-qualification/smoke/t01_receipt_collector.php': '21b96ab11307045001c50c1cc5a5043467fdb4ee381e782ee45d2b6989e42e2c',
}
T01_SOURCE_SHA = '5d49c3f485f555f3118b0afb983997e29a5ddaad4b0ed6f9cf19d855c2e4f884'
T01_MIDDLEWARE_SHA = 'b58767b343bcbfaa1d9ae461cf39dc72e7f489ba3899dea2246541153bdd3c4f'
T01_BRIEF_SHA = 'cfa72ecb1279d292cd915c4c8b7c9405095405e422d1bf96e211db809b139c95'
CAPTURE_TARGETS = ('target', 'review-target-1', 'review-target-2')
ORIGIN_ROLES = {'researcher': 'target', 'resume': 'target',
                'reviewer-1': 'review-target-1', 'reviewer-2': 'review-target-2'}
ORIGIN_SOURCE_FILES = {
    'tools/native_origin/protocol.go': '17b99d8fb6e243470f6a58f1ba0cb931a8f5fff5d8301eaaf4544284061ccf19',
    'tools/native_origin/main_linux.go': '048126cae823ac48fe0684fe569d51c814a5ea82fc7c673692c6acbc96a02be5',
}
ORIGIN_GO_VERSION = 'go1.26.4'
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
    def unique_pairs(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError('duplicate key')
            value[key] = item
        return value
    try:
        value = json.loads(path.read_bytes(), object_pairs_hook=unique_pairs)
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


def _snapshot_tree(directory: Path) -> tuple[dict, dict[str, str], dict[str, int]]:
    """Hash a bounded tree; discovered names remain in memory only."""
    if not directory.is_dir() or directory.is_symlink():
        _fail('snapshot_directory_invalid')
    rows: list[tuple[str, str]] = []
    observed: dict[str, str] = {}
    sizes: dict[str, int] = {}
    byte_count = 0
    entry_count = 0
    for path in directory.rglob('*'):
        entry_count += 1
        if entry_count > 100_000:
            _fail('snapshot_entry_limit')
        relative = path.relative_to(directory).as_posix()
        if len(relative.encode('utf-8')) > 4096 or len(path.parts) - len(directory.parts) > 64:
            _fail('snapshot_path_limit')
        if path.is_symlink():
            _fail('snapshot_symlink_forbidden')
        entry = path.stat(follow_symlinks=False)
        if stat.S_ISDIR(entry.st_mode):
            continue
        if not stat.S_ISREG(entry.st_mode):
            _fail('snapshot_special_file_forbidden')
        byte_count += entry.st_size
        if byte_count > 2 * 1024 * 1024 * 1024:
            _fail('snapshot_byte_limit')
        digest = _sha(path)
        after = path.stat(follow_symlinks=False)
        if ((entry.st_dev, entry.st_ino, entry.st_size, entry.st_mtime_ns) !=
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
            _fail('snapshot_file_changed_during_hash')
        rows.append((relative, digest))
        observed[relative] = digest
        sizes[relative] = entry.st_size
    aggregate = hashlib.sha256()
    for relative, digest in sorted(rows):
        aggregate.update(json.dumps([relative, digest], separators=(',', ':'),
                                    ensure_ascii=False).encode('utf-8') + b'\n')
    return ({'files': len(rows), 'bytes': byte_count,
             'tree_sha256': aggregate.hexdigest()}, observed, sizes)


def _snapshot_delta(observed: dict[str, str], baseline: dict[str, str]) -> dict[str, int]:
    return {'added': len(observed.keys() - baseline.keys()),
            'modified': sum(observed[name] != baseline[name]
                            for name in observed.keys() & baseline.keys()),
            'removed': len(baseline.keys() - observed.keys())}


def _snapshot_store(root: Path) -> dict:
    directory = root / 'researcher/data/opencode'
    if not directory.exists():
        return {'status': 'missing', 'present': False}
    summary, _, _ = _snapshot_tree(directory)
    main = directory / 'opencode.db'
    if not main.exists():
        return {'status': 'missing', 'present': False, 'tree': summary}
    if main.is_symlink() or not main.is_file():
        _fail('snapshot_store_file_invalid')
    identity = {}
    for label, path in (('main', main), ('wal', directory / 'opencode.db-wal'),
                        ('shm', directory / 'opencode.db-shm')):
        if not path.exists():
            identity[label] = {'present': False}
            continue
        if path.is_symlink() or not path.is_file():
            _fail('snapshot_store_file_invalid')
        entry = path.stat(follow_symlinks=False)
        identity[label] = {'present': True, 'sha256': _sha(path), 'bytes': entry.st_size,
                           'device': entry.st_dev, 'inode': entry.st_ino}
    with main.open('rb') as stream:
        header = stream.read(16)
    return {'status': 'present' if header == b'SQLite format 3\x00' else 'invalid_header',
            'present': True, 'tree': summary, **identity}


def _filesystem_snapshot(root: Path, plan: dict) -> dict:
    """Provider-free byte collection; caller is responsible for stop proof."""
    _verify_inventory(root / 'original', plan['source_sha256'])
    project, project_files, _ = _snapshot_tree(root / 'researcher/project')
    project['delta'] = _snapshot_delta(project_files, plan['source_sha256'])
    targets = {}
    mutable_paths = plan['mutable_paths']
    for role in ('target', 'review-target-1', 'review-target-2'):
        summary, observed, sizes = _snapshot_tree(root / role)
        immutable = {name: digest for name, digest in observed.items()
                     if not _mutable(name, mutable_paths)}
        baseline = {name: digest for name, digest in plan['source_sha256'].items()
                    if not _mutable(name, mutable_paths)}
        summary['immutable_delta'] = _snapshot_delta(immutable, baseline)
        summary['mutable_files'] = sum(_mutable(name, mutable_paths) for name in observed)
        summary['mutable_bytes'] = sum(size for name, size in sizes.items()
                                       if _mutable(name, mutable_paths))
        targets[role] = summary
    store = _snapshot_store(root)
    return {'kind': 'native-research-host-byte-receipt-v1',
            'status': 'complete' if store['status'] == 'present' else 'incomplete',
            'researcher_project': project, 'native_store': store,
            'targets': targets, 'target_image_id': plan['target_image_id'],
            'plan_sha256': _sha(root / 'plan.json')}


def _stopped_snapshot(root: Path, plan: dict) -> dict:
    """Bind byte collection to the exact NativeRun terminal producer set."""
    controls = _controls(root)
    manifest_path = controls / 'producer-manifest.json'
    manifest = _read_json(manifest_path)
    state = _read_json(controls / 'native-state/RUN.json')
    revoked = _read_json(controls / 'native-state/REVOKED')
    resources = _read_json(controls / 'resources.json')
    ids = [row.get('id') for row in resources.get('resources', [])
           if row.get('kind') == 'container']
    manifest_ids = [item.get('id') for item in manifest.get('producers', [])]
    manifest_digest = _sha(manifest_path)
    if (len(ids) != 8 or ids != manifest_ids or state.get('ids') != ids
            or revoked.get('ids') != ids or revoked.get('producers_verified_stopped') is not True
            or state.get('manifest_sha256') != manifest_digest
            or revoked.get('manifest_sha256') != manifest_digest):
        _fail('snapshot_native_stop_proof_invalid')
    _, producer = _activate_controls(root)
    by_id = {row['id']: row.get('role') for row in resources['resources']
             if row.get('kind') == 'container'}
    target_builds = set()
    for item in manifest['producers']:
        info = _inspect('container', item['id'])
        run_state = info.get('State', {})
        if (info.get('Id') != item['id'] or producer.binding(info) != item.get('binding')
                or (run_state.get('Running') is True and run_state.get('Paused') is not True)):
            _fail('snapshot_producer_not_frozen')
        if by_id.get(item['id']) in ('target', 'review-target-1', 'review-target-2'):
            if info.get('Image') != plan['target_image_id']:
                _fail('snapshot_target_build_changed')
            target_builds.add(by_id[item['id']])
    if target_builds != {'target', 'review-target-1', 'review-target-2'}:
        _fail('snapshot_target_build_missing')
    receipt = _filesystem_snapshot(root, plan)
    receipt['target_build'] = {'image_id': plan['target_image_id'],
                               'matching_frozen_containers': len(target_builds)}
    receipt['native_stop'] = {'manifest_sha256': manifest_digest,
                              'producer_ids_sha256': hashlib.sha256(
                                  json.dumps(ids, separators=(',', ':')).encode()).hexdigest(),
                              'revoked_sha256': _sha(controls / 'native-state/REVOKED')}
    path = controls / 'host-snapshot.json'
    _write_json(path, receipt, once=True)
    return {'status': receipt['status'], 'receipt_path': str(path),
            'receipt_sha256': _sha(path)}


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


def _capture_mode(plan: dict) -> str | None:
    if 'kanboard_capture' in plan and 't01_capture' in plan:
        _fail('capture_modes_conflict')
    return 't01' if 't01_capture' in plan else ('s10' if 'kanboard_capture' in plan else None)


def _origin_enabled(plan: dict) -> bool:
    return isinstance(plan.get('native_origin'), dict) and _capture_mode(plan) is not None


def _origin_binary(root: Path, plan: dict) -> Path:
    if not _origin_enabled(plan):
        _fail('native_origin_not_configured')
    pin = plan['native_origin']
    binary = _file(_controls(root) / 'origin/bin/native-origin', private=True)
    header = binary.read_bytes()[:20]
    machine = {'linux/amd64': 62, 'linux/arm64': 183}[plan['platform']]
    if (pin.get('kind') != 'native-origin-build-v1'
            or pin.get('go_version') != ORIGIN_GO_VERSION
            or pin.get('source_sha256') != ORIGIN_SOURCE_FILES
            or pin.get('binary_sha256') != _sha(binary)
            or len(header) != 20 or header[:6] != b'\x7fELF\x02\x01'
            or int.from_bytes(header[18:20], 'little') != machine
            or binary.stat().st_mode & 0o022 or not binary.stat().st_mode & 0o111):
        _fail('native_origin_binary_pin_mismatch')
    for relative, digest in ORIGIN_SOURCE_FILES.items():
        if _sha(_file(_controls(root) / relative, private=True)) != digest:
            _fail('native_origin_source_pin_mismatch')
    return binary


def _capture_pins(case: str = 's10') -> dict[str, str]:
    if case == 't01':
        return {'adapter_sha256': T01_CAPTURE_FILES['evals/native-qualification/kanboard_native_capture.py'],
                'broker_sha256': T01_CAPTURE_FILES['evals/native-qualification/smoke/t01_jsonrpc_broker.php'],
                'collector_sha256': T01_CAPTURE_FILES['evals/native-qualification/smoke/t01_receipt_collector.php'],
                'source_manifest_sha256': T01_SOURCE_SHA, 'middleware_sha256': T01_MIDDLEWARE_SHA}
    return {'adapter_sha256': CAPTURE_FILES['evals/native-qualification/kanboard_native_capture.py'],
            'probe_sha256': CAPTURE_FILES['evals/native-qualification/smoke/kanboard_effect_probe.php'],
            'collector_sha256': CAPTURE_FILES['evals/native-qualification/smoke/kanboard_effect_collector.php'],
            'broker_sha256': CAPTURE_FILES['evals/native-qualification/smoke/kanboard_role_broker.php'],
            'source_manifest_sha256': CAPTURE_SOURCE_SHA,
            'controller_sha256': CAPTURE_CONTROLLER_SHA}


def _load_capture_module(root: Path):
    path = _controls(root) / 'evals/native-qualification/kanboard_native_capture.py'
    if _sha(_file(path, private=True)) != CAPTURE_FILES['evals/native-qualification/kanboard_native_capture.py']:
        _fail('capture_adapter_pin_mismatch')
    spec = importlib.util.spec_from_file_location('native_kanboard_capture', path)
    if spec is None or spec.loader is None:
        _fail('capture_adapter_unavailable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_origin_gate(root: Path):
    path = _controls(root) / 'tools/native_kanboard_origin_gate.py'
    if _sha(_file(path)) != CONTROL_SHA['tools/native_kanboard_origin_gate.py']:
        _fail('origin_gate_pin_mismatch')
    spec = importlib.util.spec_from_file_location('native_kanboard_origin_gate', path)
    if spec is None or spec.loader is None:
        _fail('origin_gate_unavailable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_recovery_module(root: Path):
    path = _controls(root) / 'tools/native_effect_recovery.py'
    if _sha(_file(path)) != CONTROL_SHA['tools/native_effect_recovery.py']:
        _fail('recovery_helper_pin_mismatch')
    spec = importlib.util.spec_from_file_location('native_effect_recovery', path)
    if spec is None or spec.loader is None:
        _fail('recovery_helper_unavailable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _kanboard_recovery_window(root: Path, dispatch_id: str, role: str) -> tuple[dict, dict, dict]:
    if role != 'resume' or 'kanboard_capture' not in _plan(root):
        _fail('kanboard_recovery_turn_unqualified')
    slot = _controls(root) / 'observer/target'
    stage = _read_json(slot / 'stage.json')
    dispatch = _read_json(_controls(root) / 'dispatch' / (dispatch_id + '.json'))
    window = _read_json(slot / ('window-' + dispatch_id + '.json'))
    ids = stage.get('ids')
    topology = window.get('topology')
    if (stage.get('kind') != 'kanboard-native-capture-stage-v1'
            or stage.get('target') != 'target'
            or stage.get('plan_sha256') != _sha(root / 'plan.json')
            or stage.get('source_manifest_sha256') != CAPTURE_SOURCE_SHA
            or stage.get('controller_sha256') != _sha(_file(
                root / 'target/app/Controller/ProjectPermissionController.php'))
            or not isinstance(ids, dict) or set(ids) != {'s', 'q', 't', 'b'}
            or any(type(value) is not int or value < 1 for value in ids.values())
            or ids['s'] == ids['q']
            or window.get('kind') != 'kanboard-native-window-v1'
            or window.get('dispatch_id') != dispatch_id or window.get('target') != 'target'
            or window.get('role') != role or window.get('session_id') != dispatch.get('session_id')
            or window.get('dispatch_sha256') != _sha(_controls(root) / 'dispatch' / (dispatch_id + '.json'))
            or dispatch.get('status') != 'unknown_effect' or dispatch.get('role') != role
            or not isinstance(topology, dict)
            or topology.get('status') != 'topology_attested_origin_and_credentials_held'
            or topology.get('target') != 'target'
            or topology.get('collector_db') != str(slot / 'receipts/receipts.sqlite')
            or not isinstance(topology.get('native_client_ip'), str)
            or not isinstance(topology.get('app_observer_ip'), str)):
        _fail('kanboard_recovery_window_changed')
    return stage, window, topology


def _arm_kanboard_role_grant(root: Path, dispatch_id: str, role: str) -> dict:
    stage, window, topology = _kanboard_recovery_window(root, dispatch_id, role)
    ids = stage['ids']
    db_path = _file(root / 'target/data/db.sqlite', private=True)
    try:
        with closing(sqlite3.connect(db_path.as_uri() + '?mode=ro', uri=True)) as db:
            managers = db.execute(
                'SELECT pu.user_id FROM project_has_users pu JOIN users u ON u.id=pu.user_id '
                "WHERE pu.project_id=? AND pu.role='project-manager' "
                "AND u.role='app-user' AND u.is_active=1", (ids['s'],)).fetchmany(2)
    except sqlite3.DatabaseError:
        _fail('kanboard_recovery_actor_unavailable')
    if len(managers) != 1 or type(managers[0][0]) is not int:
        _fail('kanboard_recovery_actor_ambiguous')
    module = _load_recovery_module(root)
    result = module.arm_kanboard_role_grant(
        root, dispatch_id, s=ids['s'], q=ids['q'], t=ids['t'], actor_a=managers[0][0],
        subject_b=ids['b'], researcher_ip=topology['native_client_ip'],
        app_ip=topology['app_observer_ip'], collector_db=Path(topology['collector_db']),
        origin_ingress=_origin_enabled(_plan(root)))
    sidecar = _read_json(_controls(root) / 'recovery' / (dispatch_id + '.json'))
    if (sidecar.get('collector_max_id') != window.get('collector_max_id_before')
            or sidecar.get('collector_prefix_count') != window.get('collector_count_before')
            or sidecar.get('collector_prefix_sha256') != window.get('collector_prefix_sha256')):
        _fail('kanboard_recovery_window_advanced')
    return result


def prepare(args: argparse.Namespace) -> dict:
    source = Path(args.source)
    brief = _file(Path(args.brief))
    scope = _file(Path(args.scope_file), private=True)
    relay = _file(Path(args.relay), private=True)
    ca = _file(Path(args.runtime_ca), private=True)
    target_command = _validate_target_command(Path(args.target_command))
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
    capture = bool(getattr(args, 'kanboard_capture', False))
    t01_capture = bool(getattr(args, 't01_capture', False))
    origin_ingress = bool(getattr(args, 'origin_ingress', False))
    if capture and t01_capture:
        _fail('capture_modes_conflict')
    if origin_ingress and not (capture or t01_capture):
        _fail('native_origin_requires_capture')
    go_binary = None
    if origin_ingress:
        for relative, digest in ORIGIN_SOURCE_FILES.items():
            if _sha(ROOT / relative) != digest:
                _fail('native_origin_source_pin_mismatch')
        found = shutil.which('go')
        if not found:
            _fail('native_origin_go_unavailable')
        go_binary = Path(found).resolve(strict=True)
        if go_binary.stat().st_mode & 0o022:
            _fail('native_origin_go_writable')
        version = subprocess.run([str(go_binary), 'version'], stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 timeout=10, check=False)
        if version.returncode or not version.stdout.decode(errors='replace').startswith(
                'go version ' + ORIGIN_GO_VERSION + ' '):
            _fail('native_origin_go_version_mismatch')
    if capture:
        manifest = hashlib.sha256(json.dumps(source_inventory, sort_keys=True).encode()).hexdigest()
        if (manifest != CAPTURE_SOURCE_SHA or
                target_command != ['php', '-S', f'0.0.0.0:{args.target_port}', '-t', '/target']):
            _fail('kanboard_capture_source_or_command_unqualified')
        for relative, digest in CAPTURE_FILES.items():
            if _sha(ROOT / relative) != digest:
                _fail('capture_code_pin_mismatch')
    if t01_capture:
        manifest = hashlib.sha256(json.dumps(source_inventory, sort_keys=True).encode()).hexdigest()
        if (manifest != T01_SOURCE_SHA or
                target_command != ['php', '-S', f'0.0.0.0:{args.target_port}', '-t', '/target'] or
                args.target_port == 8764):
            _fail('t01_capture_source_or_command_unqualified')
        for relative, digest in T01_CAPTURE_FILES.items():
            if _sha(ROOT / relative) != digest:
                _fail('t01_capture_code_pin_mismatch')
    try:
        brief_text = brief.read_text()
    except UnicodeError:
        _fail('brief_encoding_invalid')
    if not brief_text.strip() or CREDENTIAL_TEXT.search(brief_text):
        _fail('brief_empty_or_credential_like')
    if t01_capture and _sha(brief) != T01_BRIEF_SHA:
        _fail('t01_capture_brief_pin_mismatch')
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
        capture_files = CAPTURE_FILES if capture else (T01_CAPTURE_FILES if t01_capture else {})
        for relative in (*CONTROL_SHA, *capture_files, *(ORIGIN_SOURCE_FILES if origin_ingress else {})):
            destination = controls / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, destination)
            if relative in capture_files or relative in ORIGIN_SOURCE_FILES:
                destination.chmod(0o600)
            if _sha(destination) != (CONTROL_SHA | capture_files |
                                     (ORIGIN_SOURCE_FILES if origin_ingress else {}))[relative]:
                _fail('archived_control_pin_mismatch')
        origin_build = None
        if origin_ingress:
            for role in ORIGIN_ROLES:
                (controls / 'origin/socket' / role).mkdir(parents=True, mode=0o700)
                (controls / 'origin/ledger' / role).mkdir(parents=True, mode=0o700)
            (controls / 'origin/arms').mkdir(parents=True, mode=0o700)
            (controls / 'origin/registrations').mkdir(parents=True, mode=0o700)
            (controls / 'origin/proofs').mkdir(parents=True, mode=0o700)
            (controls / 'origin/window-close').mkdir(parents=True, mode=0o700)
            binary = controls / 'origin/bin/native-origin'
            binary.parent.mkdir(parents=True, mode=0o700)
            build_env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
                         'HOME': os.environ.get('HOME', str(root)),
                         'GO111MODULE': 'off', 'GOTOOLCHAIN': 'local',
                         'CGO_ENABLED': '0', 'GOOS': 'linux',
                         'GOARCH': args.platform.split('/')[1], 'GOPROXY': 'off',
                         'GOSUMDB': 'off', 'GOFLAGS': '', 'GOWORK': 'off'}
            built = subprocess.run([str(go_binary), 'build', '-trimpath', '-buildvcs=false',
                                    '-ldflags=-buildid=', '-o', str(binary),
                                    *(str(controls / name) for name in ORIGIN_SOURCE_FILES)],
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, env=build_env, timeout=120, check=False)
            if built.returncode or not binary.exists():
                _fail('native_origin_build_failed')
            binary.chmod(0o700)
            header = binary.open('rb').read(20)
            machine = {'linux/amd64': 62, 'linux/arm64': 183}[args.platform]
            if (len(header) != 20 or header[:6] != b'\x7fELF\x02\x01'
                    or int.from_bytes(header[18:20], 'little') != machine):
                _fail('native_origin_build_platform_mismatch')
            origin_build = {'kind': 'native-origin-build-v1',
                            'go_version': ORIGIN_GO_VERSION,
                            'go_binary_sha256': _sha(go_binary),
                            'source_sha256': ORIGIN_SOURCE_FILES,
                            'binary_sha256': _sha(binary)}
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
        if capture:
            plan['kanboard_capture'] = _capture_pins()
        if t01_capture:
            plan['t01_capture'] = _capture_pins('t01')
        if origin_build is not None:
            plan['native_origin'] = origin_build
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
    if 'native_origin' in plan:
        if _capture_mode(plan) is None:
            _fail('native_origin_capture_missing')
        _origin_binary(root, plan)
    if 'kanboard_capture' in plan:
        if plan['kanboard_capture'] != _capture_pins():
            _fail('capture_plan_pin_mismatch')
        for relative, digest in CAPTURE_FILES.items():
            if _sha(_file(controls / relative, private=True)) != digest:
                _fail('archived_capture_pin_mismatch')
        if plan.get('source_manifest_sha256') != CAPTURE_SOURCE_SHA:
            _fail('capture_source_pin_mismatch')
    if 't01_capture' in plan:
        if _capture_mode(plan) != 't01' or plan['t01_capture'] != _capture_pins('t01'):
            _fail('t01_capture_plan_pin_mismatch')
        if plan.get('brief_sha256') != T01_BRIEF_SHA:
            _fail('t01_capture_brief_pin_mismatch')
        for relative, digest in T01_CAPTURE_FILES.items():
            if _sha(_file(controls / relative, private=True)) != digest:
                _fail('archived_t01_capture_pin_mismatch')
        if plan.get('source_manifest_sha256') != T01_SOURCE_SHA:
            _fail('t01_capture_source_pin_mismatch')
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
        _verify_inventory(root / 'researcher/project', plan['source_sha256'])
        for name in ('target', 'review-target-1', 'review-target-2'):
            _verify_target_state(root / name, plan['source_sha256'], plan['mutable_paths'])
    return plan


def capture_stage(run_root: Path, target: str, *, s: int | None = None, q: int | None = None,
                  t: int | None = None, b: int | None = None) -> dict:
    root = _private_root(Path(run_root))
    plan = _verified_plan(root, pristine=True)
    if _capture_mode(plan) is None or (_controls(root) / 'resources.json').exists():
        _fail('capture_stage_not_prestart')
    result = _load_capture_module(root).stage(root, target, s=s, q=q, t=t, b=b)
    result['stage_sha256'] = _sha(_controls(root) / 'observer' / target / 'stage.json')
    return result


def _approval(root: Path, plan: dict, path: Path) -> None:
    capture_db_pins = {}
    if _capture_mode(plan):
        _, capture_db_pins = _capture_specs(
            root, plan, _validate_target_command(_controls(root) / 'target-command.json'))
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
    if _capture_mode(plan):
        expected['capture_stage_sha256'] = {
            target: _sha(_controls(root) / 'observer' / target / 'stage.json')
            for target in CAPTURE_TARGETS}
    if 'kanboard_capture' in plan:
        expected['capture_target_db_sha256'] = capture_db_pins
    if any(approval.get(key) != value for key, value in expected.items()):
        _fail('live_approval_mismatch')
    if set(approval) != set(expected) | {'approved_by', 'approved_at', 'expires_at'}:
        _fail('live_approval_unknown_field')
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
    archived = _controls(root) / 'approval.json'
    if archived.exists():
        if _read_json(archived) != approval:
            _fail('live_approval_archive_changed')
    else:
        _write_json(archived, approval, once=True)


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
    if ip is not None and (network_state.get('IPAddress') != ip
                           and (network_state.get('IPAMConfig') or {}).get('IPv4Address') != ip):
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
    info = {
        'url': ('unix:///origin/socket/ingress.sock' if _origin_enabled(plan) else
                f'http://{target_ip}:{plan["target_port"]}'),
        'source_manifest_sha256': plan['source_manifest_sha256'],
        'role': role,
    }
    if _origin_enabled(plan):
        info['native_origin_route'] = {
            'binary': '/origin/bin/native-origin',
            'actor_handles': ['A', 'B'] if 't01_capture' in plan else ['A', 'B', 'C'],
            'tcp_port_is_target_loopback_only': True,
        }
        if 'kanboard_capture' in plan:
            info['native_origin_route']['get'] = '/origin/bin/native-origin request A GET /'
            info['native_origin_route']['post'] = (
                'printf FORM | /origin/bin/native-origin request A POST PATH '
                'application/x-www-form-urlencoded')
        else:
            info['native_origin_route']['post'] = (
                'printf BODY | /origin/bin/native-origin request A POST '
                '/jsonrpc.php application/json')
    if 'kanboard_capture' in plan:
        info['synthetic_actor_route'] = {
            'header': 'X-Native-Actor', 'handles': ['A', 'B', 'C'],
            'form_csrf_placeholder': 'broker-managed',
            'backend_identity_and_session': 'target-owned',
        }
    if 't01_capture' in plan:
        info['synthetic_actor_route'] = {
            'header': 'X-Native-Actor', 'handles': ['A', 'B'],
            'entrypoint': 'POST /jsonrpc.php',
            'response_request_id_header': 'X-LRH-Request-ID',
            'backend_identity_and_session': 'target-owned; original same-operation origin held',
        }
    _write_json(root / role / 'project/target.json', info, once=True)


def _capture_seed_baseline(root: Path, target: str, ids: dict[str, int]) -> str:
    """Check the staged private Kanboard state, then bind the checked DB bytes."""
    path = root / target / 'data/db.sqlite'
    try:
        path = _file(path, private=True)
        if any(sidecar.exists() or sidecar.is_symlink()
               for sidecar in (path.with_name('db.sqlite-wal'), path.with_name('db.sqlite-shm'),
                               path.with_name('db.sqlite-journal'))):
            _fail('capture_seed_baseline_invalid')
        before = _sha(path)
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)) as db:
            db.execute('PRAGMA query_only=ON')
            if db.execute('PRAGMA quick_check').fetchone() != ('ok',):
                _fail('capture_seed_baseline_invalid')
            s = db.execute('SELECT is_private,is_active FROM projects WHERE id=?',
                           (ids['s'],)).fetchone()
            q = db.execute('SELECT owner_id,is_private,is_public,token,is_active '
                           'FROM projects WHERE id=?', (ids['q'],)).fetchone()
            task = db.execute('SELECT project_id,title,is_active FROM tasks WHERE id=?',
                              (ids['t'],)).fetchone()
            b = db.execute('SELECT role,is_active FROM users WHERE id=?', (ids['b'],)).fetchone()

            def no_project_role(project_id: int, user_id: int) -> bool:
                direct = db.execute('SELECT 1 FROM project_has_users WHERE project_id=? AND user_id=?',
                                    (project_id, user_id)).fetchone()
                group = db.execute(
                    'SELECT 1 FROM project_has_groups pg JOIN group_has_users gu '
                    'ON gu.group_id=pg.group_id WHERE pg.project_id=? AND gu.user_id=?',
                    (project_id, user_id)).fetchone()
                return direct is None and group is None

            managers = [row[0] for row in db.execute(
                'SELECT u.id FROM project_has_users pu JOIN users u ON u.id=pu.user_id '
                "WHERE pu.project_id=? AND pu.role='project-manager' "
                "AND u.role='app-user' AND u.is_active=1", (ids['s'],))]
            q_owner = None if q is None else q[0]
            owner = None if q_owner is None else db.execute(
                'SELECT role,is_active FROM users WHERE id=?', (q_owner,)).fetchone()
            owner_role = None if q_owner is None else db.execute(
                'SELECT role FROM project_has_users WHERE project_id=? AND user_id=?',
                (ids['q'], q_owner)).fetchone()
            valid = (
                s == (0, 1)
                and q is not None and q[1] == 1 and q[2] == 0 and q[3] in (None, '')
                and q[4] == 1 and q_owner != ids['b']
                and owner == ('app-user', 1) and owner_role == ('project-manager',)
                and task is not None and task[0] == ids['q'] and isinstance(task[1], str)
                and bool(task[1]) and task[2] == 1
                and b == ('app-user', 1)
                and len(managers) == 1 and q_owner not in managers
                and all(no_project_role(ids['q'], manager) for manager in managers)
                and no_project_role(ids['s'], ids['b']) and no_project_role(ids['q'], ids['b'])
            )
            if not valid:
                _fail('capture_seed_baseline_invalid')
        if _sha(path) != before:
            _fail('capture_seed_baseline_invalid')
        return before
    except (OSError, sqlite3.Error, NativeResearchError, TypeError, ValueError):
        _fail('capture_seed_baseline_invalid')


def _capture_specs(root: Path, plan: dict, command: list[str], *, materialize: bool = False) -> tuple[
        dict[str, tuple[list[str], list[str], list[str]]], dict[str, str]]:
    case = _capture_mode(plan)
    if case is None:
        return {}, {}
    if command != ['php', '-S', f'0.0.0.0:{plan["target_port"]}', '-t', '/target']:
        _fail('capture_target_command_changed')
    if case == 't01':
        if plan['target_port'] == 8764:
            _fail('t01_backend_port_conflict')
        specs = {}
        for target in CAPTURE_TARGETS:
            slot = _controls(root) / 'observer' / target
            stage = _read_json(slot / 'stage.json')
            if (set(stage) != {'kind', 'target', 'research_role', 'source_manifest_sha256',
                               'image_id', 'plan_sha256', 'collector_sha256', 'broker_sha256'}
                    or stage['kind'] != 'kanboard-t01-capture-stage-v1'
                    or stage['target'] != target
                    or stage['research_role'] != {'target': 'researcher',
                                                  'review-target-1': 'reviewer-1',
                                                  'review-target-2': 'reviewer-2'}[target]
                    or stage['source_manifest_sha256'] != T01_SOURCE_SHA
                    or stage['image_id'] != plan['target_image_id']
                    or stage['plan_sha256'] != _sha(root / 'plan.json')
                    or stage['collector_sha256'] != _sha(_file(slot / 'receipt.php', private=True))
                    or stage['broker_sha256'] != _sha(_file(slot / 'broker.php', private=True))
                    or stage['collector_sha256'] != _capture_pins('t01')['collector_sha256']
                    or stage['broker_sha256'] != _capture_pins('t01')['broker_sha256']):
                _fail('t01_capture_stage_changed')
            specs[target] = ([_mount(slot / 'broker.php', '/observer/broker.php', readonly=True)],
                             ['DB_FILENAME=/target/data/db.sqlite',
                              *(['LRH_ORIGIN_INGRESS=1'] if _origin_enabled(plan) else [])],
                             ['php', '/observer/broker.php', str(plan['target_port']), '/target',
                              'http://kanboard-effect-collector:8765/receipt.php'])
        return specs, {}
    specs = {}
    db_pins = {}
    for target in CAPTURE_TARGETS:
        slot = _controls(root) / 'observer' / target
        stage = _read_json(slot / 'stage.json')
        ids = stage.get('ids')
        if (stage.get('kind') != 'kanboard-native-capture-stage-v1'
                or stage.get('target') != target
                or stage.get('plan_sha256') != _sha(root / 'plan.json')
                or stage.get('source_manifest_sha256') != CAPTURE_SOURCE_SHA
                or stage.get('controller_sha256') != CAPTURE_CONTROLLER_SHA
                or not isinstance(ids, dict) or set(ids) != {'s', 'q', 't', 'b'}
                or any(type(value) is not int or value <= 0 for value in ids.values())
                or ids['s'] == ids['q']
                or stage.get('probe_sha256') != _sha(_file(slot / 'effect.php', private=True))
                or stage.get('collector_sha256') != _sha(_file(slot / 'receipt.php', private=True))
                or stage.get('broker_sha256') != _sha(_file(slot / 'broker.php', private=True))
                or stage['probe_sha256'] != _capture_pins()['probe_sha256']
                or stage['collector_sha256'] != _capture_pins()['collector_sha256']
                or stage['broker_sha256'] != _capture_pins()['broker_sha256']):
            _fail('capture_stage_changed')
        db_pins[target] = _capture_seed_baseline(root, target, ids)
        with closing(sqlite3.connect((root / target / 'data/db.sqlite').as_uri() + '?mode=ro&immutable=1',
                                     uri=True)) as db:
            a = db.execute('SELECT u.username FROM project_has_users pu JOIN users u ON u.id=pu.user_id '
                           "WHERE pu.project_id=? AND pu.role='project-manager' "
                           "AND u.role='app-user' AND u.is_active=1", (ids['s'],)).fetchall()
            c = db.execute('SELECT u.username FROM projects p JOIN users u ON u.id=p.owner_id '
                           "WHERE p.id=? AND u.role='app-user' AND u.is_active=1", (ids['q'],)).fetchall()
            b = db.execute('SELECT username FROM users WHERE id=? AND role=? AND is_active=1',
                           (ids['b'], 'app-user')).fetchall()
        if not len(a) == len(b) == len(c) == 1:
            _fail('capture_actor_map_ambiguous')
        expected_actors = {'A': a[0][0], 'B': b[0][0], 'C': c[0][0]}
        if (len(set(expected_actors.values())) != 3
                or any(not isinstance(user, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', user)
                       for user in expected_actors.values())):
            _fail('capture_actor_map_changed')
        if not materialize:
            continue
        actor_map_path = slot / 'actors.json'
        if actor_map_path.exists():
            if _read_json(actor_map_path) != expected_actors:
                _fail('capture_actor_map_changed')
        else:
            _write_json(actor_map_path, expected_actors, once=True)
        route_path = slot / 'actor-route.json'
        route = {'kind': 'kanboard-native-actor-route-v1', 'target': target,
                 'map_sha256': _sha(actor_map_path), 'baseline_db_sha256': db_pins[target]}
        if route_path.exists():
            if _read_json(route_path) != route:
                _fail('capture_actor_map_changed')
        else:
            _write_json(route_path, route, once=True)
        mounts = [_mount(slot / 'effect.php', '/observer/effect.php', readonly=True),
                  _mount(slot / 'broker.php', '/observer/broker.php', readonly=True),
                  _mount(slot / 'actors.json', '/observer/actors.json', readonly=True)]
        environment = ['NATIVE_EFFECT_COLLECTOR=http://kanboard-effect-collector:8765/receipt.php',
                       'NATIVE_EFFECT_SOURCE_DIR=/target', 'DB_FILENAME=/target/data/db.sqlite',
                       'REVERSE_PROXY_AUTH=true', 'REVERSE_PROXY_USER_HEADER=HTTP_X_LRH_ACTOR']
        environment += ['NATIVE_EFFECT_' + key.upper() + '=' + str(ids[key])
                        for key in ('s', 'q', 't', 'b')]
        listen_port = plan['target_port']
        if listen_port == 18081:
            _fail('capture_target_port_conflict')
        listen_host = '127.0.0.1' if _origin_enabled(plan) else '0.0.0.0'
        app_command = ('php -d auto_prepend_file=/observer/effect.php -S 127.0.0.1:18081 '
                       '-t /target >/dev/null 2>&1 & '
                       'exec php /observer/broker.php ' + listen_host + ':' + str(listen_port) +
                       ' /observer/actors.json 127.0.0.1:18081')
        specs[target] = (mounts, environment, ['sh', '-c', app_command])
    return specs, db_pins


def _capture_approved_specs(root: Path, plan: dict, command: list[str], *,
                            verify_source: bool = False) -> dict[str, tuple[list[str], list[str], list[str]]]:
    if _capture_mode(plan) == 't01':
        specs, _ = _capture_specs(root, plan, command)
        approval = _read_json(_controls(root) / 'approval.json')
        if approval.get('capture_stage_sha256') != {
                target: _sha(_controls(root) / 'observer' / target / 'stage.json')
                for target in CAPTURE_TARGETS}:
            _fail('t01_capture_stage_approval_changed')
        if verify_source:
            for target in CAPTURE_TARGETS:
                _verify_target_state(root / target, plan['source_sha256'], plan['mutable_paths'])
        return specs
    _, db_pins = _capture_specs(root, plan, command)
    if db_pins:
        approval = _read_json(_controls(root) / 'approval.json')
        if (approval.get('capture_target_db_sha256') != db_pins
                or approval.get('capture_stage_sha256') != {
                    target: _sha(_controls(root) / 'observer' / target / 'stage.json')
                    for target in CAPTURE_TARGETS}):
            _fail('capture_seed_baseline_changed')
        specs, materialized_pins = _capture_specs(root, plan, command, materialize=True)
        if materialized_pins != db_pins:
            _fail('capture_seed_baseline_changed')
        if verify_source:
            for target in CAPTURE_TARGETS:
                _verify_target_state(root / target, plan['source_sha256'], plan['mutable_paths'])
        return specs
    return {}


def _preseal(root: Path, plan: dict, nonce: str, rows: list[dict], port: int,
             capability: str) -> dict:
    target_command = _validate_target_command(_controls(root) / 'target-command.json')
    capture_specs = _capture_approved_specs(root, plan, target_command)
    capture = _load_capture_module(root) if capture_specs else None
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
        if (actual.get('IPAddress') != relay_ip
                and (actual.get('IPAMConfig') or {}).get('IPv4Address') != relay_ip):
            _fail('relay_internal_ip_mismatch')
    targets = {}
    for role, item in (('target', (research, research_target_ip)),
                       ('review-target-1', (reviews['reviewer-1'][0], reviews['reviewer-1'][2])),
                       ('review-target-2', (reviews['reviewer-2'][0], reviews['reviewer-2'][2]))):
        network, ip = item
        extra_mounts, extra_env, command = capture_specs.get(role, ([], [], target_command))
        targets[role] = _create(root, nonce, rows, role, plan['target_image_id'], platform,
                                network, ip, [_mount(root / role, '/target'), *extra_mounts],
                                ['HOME=/target', 'HTTP_PROXY=', 'HTTPS_PROXY=', 'ALL_PROXY=',
                                 'http_proxy=', 'https_proxy=', 'all_proxy=', 'NO_PROXY=*', 'no_proxy=*',
                                 *extra_env], command, workdir='/target',
                                dns_isolated=not bool(capture_specs))
        if capture is not None:
            capture.activate(root, role)
    _write_target_info(root, 'researcher', research_target_ip, plan)
    for slot in ('reviewer-1', 'reviewer-2'):
        _write_target_info(root, slot, reviews[slot][2], plan)

    def create_research(role: str, network: str, relay_ip: str, target_ip: str) -> str:
        base = root / ('researcher' if role == 'resume' else role)
        mounts = [_mount(base, '/workspace'),
                  _mount(controls / 'opencode.json', '/workspace/config/opencode/opencode.json', readonly=True),
                  _mount(controls / 'runtime-ca.pem', '/runtime-ca.pem', readonly=True)]
        if _origin_enabled(plan):
            mounts.extend([_mount(_origin_binary(root, plan), '/origin/bin/native-origin', readonly=True),
                           _mount(controls / 'origin/socket' / role, '/origin/socket', readonly=True)])
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


def _capture_stop(root: Path, plan: dict, native_status: str) -> dict:
    if _capture_mode(plan) is None:
        return {'status': 'not_configured'}
    module = _load_capture_module(root)
    results = []
    for target in CAPTURE_TARGETS:
        ledger_path = _controls(root) / 'observer' / target / 'resources.json'
        if not ledger_path.exists():
            if native_status in ('stopped', 'closed_before_activation'):
                _fail('capture_ledger_missing_after_native_start')
            continue
        ledger = _read_json(ledger_path)
        if ledger.get('status') in ('aborted', 'removed'):
            results.append({'target': target, 'status': ledger['status']})
        elif native_status == 'stopped':
            results.append(module.freeze(root, target))
        elif native_status == 'closed_before_activation':
            results.append(module.close_startup(root, target))
        elif native_status == 'not_started':
            results.append(module.abort_activation(root, target))
        else:
            _fail('capture_native_stop_unverified')
    return {'status': 'complete', 'targets': results}


def _origin_resources_path(root: Path) -> Path:
    return _controls(root) / 'origin/resources.json'


def _origin_resolve_row(root: Path, record: dict, row: dict, *, allow_absent: bool = False) -> str | None:
    """Resolve a create interrupted before its exact ID was sealed."""
    identifier = row.get('id')
    if identifier is None:
        name = row.get('name')
        listing = _docker('container', 'ls', '-a', '--no-trunc',
                          '--filter', 'name=^/' + name + '$', '--format', '{{.ID}}')
        matches = listing.stdout.decode().splitlines()
        if not matches:
            return None
        if len(matches) != 1 or not HEX_RE.fullmatch(matches[0]):
            _fail('native_origin_resource_ambiguous')
        identifier = matches[0]
        row['id'] = identifier
        _write_json(_origin_resources_path(root), record)
    if not isinstance(identifier, str) or not HEX_RE.fullmatch(identifier):
        _fail('native_origin_resource_invalid')
    if allow_absent:
        listed = _docker('container', 'ls', '-a', '--no-trunc',
                         '--filter', 'id=' + identifier, '--format', '{{.ID}}')
        if listed.stdout.strip() == b'':
            return None
        if listed.stdout.decode().strip() != identifier:
            _fail('native_origin_resource_ambiguous')
    info = _inspect('container', identifier)
    if (info.get('Id') != identifier or info.get('Name') != '/' + row['name']
            or info.get('Config', {}).get('Labels', {}).get(LABEL) != record['nonce']
            or info.get('Config', {}).get('Labels', {}).get('io.lrh.native-origin') != row['role']):
        _fail('native_origin_resource_owner_changed')
    return identifier


def _origin_start(root: Path, plan: dict, nonce: str, bindings: dict) -> dict:
    if not _origin_enabled(plan):
        return {'status': 'not_configured'}
    binary = _origin_binary(root, plan)
    controls = _controls(root)
    rows = [{'role': role, 'target': target,
             'name': 'lrh-origin-' + nonce[:12] + '-' + role, 'id': None}
            for role, target in ORIGIN_ROLES.items()]
    ledger = {'kind': 'native-origin-resources-v1', 'nonce': nonce,
              'status': 'creating', 'resources': rows,
              'producer_manifest_sha256': _sha(controls / 'producer-manifest.json')}
    _write_json(_origin_resources_path(root), ledger, once=True)
    for row in rows:
        role, target = row['role'], row['target']
        agent_id, target_id = bindings[role], bindings[target]
        for identifier, image in ((agent_id, plan['image_id']), (target_id, plan['target_image_id'])):
            inspected = _inspect('container', identifier)
            if (inspected.get('Id') != identifier or inspected.get('Image') != image
                    or inspected.get('State', {}).get('Running') is not True
                    or inspected.get('Config', {}).get('Labels', {}).get(LABEL) != nonce):
                _fail('native_origin_namespace_owner_invalid')
        mounts = [_mount(binary, '/origin/bin/native-origin', readonly=True),
                  _mount(controls / 'origin/socket' / role, '/origin/socket'),
                  _mount(controls / 'origin/ledger' / role, '/origin/ledger'),
                  _mount(controls / 'origin/arms', '/origin/arms', readonly=True)]
        command = ['/origin/bin/native-origin', 'ingress', role, target,
                   str(plan['target_port']), '/origin/socket', '/origin/ledger',
                   '/origin/arms', str(os.getuid())]
        arguments = ['container', 'create', '--name', row['name'], '--pull', 'never',
                     '--platform', plan['platform'], '--network', 'container:' + target_id,
                     '--pid', 'container:' + agent_id, '--read-only', '--restart', 'no',
                     '--log-driver', 'none', '--cap-drop', 'ALL',
                     '--security-opt', 'no-new-privileges=true',
                     '--user', f'{os.getuid()}:{os.getgid()}',
                     '--memory', '256m', '--cpus', '0.5', '--pids-limit', '32',
                     '--label', LABEL + '=' + nonce,
                     '--label', 'io.lrh.native-origin=' + role,
                     '--env', 'LRH_RUN_NONCE=' + nonce]
        for mount in mounts:
            arguments += ['--mount', mount]
        arguments += ['--entrypoint', command[0], plan['image_id'], *command[1:]]
        identifier = _docker(*arguments).stdout.decode().strip()
        if not HEX_RE.fullmatch(identifier):
            _fail('native_origin_create_id_invalid')
        row['id'] = identifier
        _write_json(_origin_resources_path(root), ledger)
        info = _inspect('container', identifier)
        host = info.get('HostConfig', {})
        actual_mounts = {(item.get('Source'), item.get('Destination'), item.get('RW'))
                         for item in info.get('Mounts', [])}
        expected_mounts = {(str(binary), '/origin/bin/native-origin', False),
                           (str(controls / 'origin/socket' / role), '/origin/socket', True),
                           (str(controls / 'origin/ledger' / role), '/origin/ledger', True),
                           (str(controls / 'origin/arms'), '/origin/arms', False)}
        if (info.get('Id') != identifier or info.get('Image') != plan['image_id']
                or info.get('State', {}).get('Status') != 'created'
                or info.get('Name') != '/' + row['name']
                or host.get('NetworkMode') != 'container:' + target_id
                or host.get('PidMode') != 'container:' + agent_id
                or host.get('ReadonlyRootfs') is not True
                or host.get('Privileged') is not False
                or host.get('CapDrop') != ['ALL']
                or 'no-new-privileges=true' not in host.get('SecurityOpt', [])
                or actual_mounts != expected_mounts
                or info.get('Config', {}).get('Labels', {}).get(LABEL) != nonce):
            _fail('native_origin_container_topology_invalid')
        _docker('container', 'start', identifier)
        running = _inspect('container', identifier)
        socket_path = controls / 'origin/socket' / role / 'ingress.sock'
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not socket_path.exists():
            time.sleep(.05)
        if (running.get('State', {}).get('Running') is not True
                or not socket_path.exists() or not stat.S_ISSOCK(socket_path.stat().st_mode)
                or socket_path.stat().st_uid != os.getuid()
                or socket_path.stat().st_mode & 0o077):
            _fail('native_origin_socket_unavailable')
    ledger['status'] = 'active'
    _write_json(_origin_resources_path(root), ledger)
    return {'status': 'active', 'roles': list(ORIGIN_ROLES),
            'resource_ledger_sha256': _sha(_origin_resources_path(root))}


def _origin_stop(root: Path, plan: dict, native_status: str) -> dict:
    if not _origin_enabled(plan):
        return {'status': 'not_configured'}
    path = _origin_resources_path(root)
    if not path.exists():
        return {'status': 'not_started'}
    if native_status not in ('stopped', 'closed_before_activation', 'not_started'):
        _fail('native_origin_native_stop_unverified')
    record = _read_json(path)
    if (record.get('kind') != 'native-origin-resources-v1'
            or record.get('producer_manifest_sha256') != _sha(_controls(root) / 'producer-manifest.json')
            or [row.get('role') for row in record.get('resources', [])] != list(ORIGIN_ROLES)):
        _fail('native_origin_resource_ledger_invalid')
    stopped = []
    for row in record['resources']:
        identifier = _origin_resolve_row(root, record, row)
        if identifier is None:
            stopped.append({'role': row['role'], 'id': None, 'status': 'absent'})
            continue
        info = _inspect('container', identifier)
        if info.get('State', {}).get('Running') is True:
            _docker('container', 'stop', '--time', '10', identifier)
        info = _inspect('container', identifier)
        if info.get('State', {}).get('Status') not in ('exited', 'dead', 'created'):
            _fail('native_origin_container_stop_unknown')
        stopped.append({'role': row['role'], 'id': identifier,
                        'status': info['State']['Status']})
    ledger_hashes = {}
    for role in ORIGIN_ROLES:
        file = _controls(root) / 'origin/ledger' / role / 'requests.jsonl'
        ledger_hashes[role] = _sha(file) if file.exists() else None
    stop_kind = {'stopped': 'REVOKED', 'closed_before_activation': 'STARTUP_CLOSED',
                 'not_started': 'NOT_STARTED'}[native_status]
    stop_path = _controls(root) / 'native-state' / stop_kind
    if stop_kind != 'NOT_STARTED' and not stop_path.exists():
        _fail('native_origin_native_stop_unverified')
    receipt = {'kind': 'native-origin-stopped-v1', 'nonce': record['nonce'],
               'native_stop_kind': stop_kind,
               'native_stop_sha256': _sha(stop_path) if stop_kind != 'NOT_STARTED' else None,
               'producer_manifest_sha256': record['producer_manifest_sha256'],
               'containers': stopped, 'ledger_sha256': ledger_hashes}
    output = _controls(root) / 'origin/stopped.json'
    if output.exists():
        if _read_json(output) != receipt:
            _fail('native_origin_stop_receipt_changed')
    else:
        _write_json(output, receipt, once=True)
    record['status'] = 'stopped'
    _write_json(path, record)
    return {'status': 'complete' if stop_kind != 'NOT_STARTED' and
            all(row['id'] for row in stopped) else 'partial',
            'receipt_sha256': _sha(output)}


def _origin_cleanup(root: Path, plan: dict) -> dict:
    if not _origin_enabled(plan):
        return {'status': 'not_configured'}
    path = _origin_resources_path(root)
    if not path.exists():
        return {'status': 'not_started'}
    record = _read_json(path)
    if record.get('status') not in ('stopped', 'cleanup_unknown', 'removed'):
        _fail('native_origin_not_stopped')
    for row in reversed(record['resources']):
        identifier = _origin_resolve_row(root, record, row, allow_absent=True)
        if identifier is None:
            continue
        info = _inspect('container', identifier)
        if info.get('State', {}).get('Running') is True:
            _fail('native_origin_still_running')
        _docker('container', 'rm', identifier)
        listed = _docker('container', 'ls', '-a', '--no-trunc',
                         '--filter', 'id=' + identifier, '--format', '{{.ID}}')
        if listed.stdout.strip():
            record['status'] = 'cleanup_unknown'
            _write_json(path, record)
            _fail('native_origin_cleanup_unknown')
    for role in ORIGIN_ROLES:
        (_controls(root) / 'origin/socket' / role / 'ingress.sock').unlink(missing_ok=True)
    record['status'] = 'removed'
    _write_json(path, record)
    receipt = {'kind': 'native-origin-cleanup-v1', 'nonce': record['nonce'],
               'stopped_sha256': _sha(_controls(root) / 'origin/stopped.json'),
               'resource_ids': [row['id'] for row in record['resources']],
               'all_absent': True}
    output = _controls(root) / 'origin/cleanup.json'
    if output.exists():
        if _read_json(output) != receipt:
            _fail('native_origin_cleanup_receipt_changed')
    else:
        _write_json(output, receipt, once=True)
    return {'status': 'complete', 'receipt_sha256': _sha(output)}


def _capture_cleanup(root: Path, plan: dict) -> dict:
    if _capture_mode(plan) is None:
        return {'status': 'not_configured'}
    module = _load_capture_module(root)
    results = []
    for target in CAPTURE_TARGETS:
        ledger_path = _controls(root) / 'observer' / target / 'resources.json'
        if not ledger_path.exists():
            continue
        ledger = _read_json(ledger_path)
        if ledger.get('status') == 'aborted':
            results.append({'target': target, 'status': 'aborted'})
        elif ledger.get('status') == 'removed':
            results.append({'target': target, 'status': 'removed'})
        else:
            results.append(module.cleanup(root, target))
    return {'status': 'complete', 'targets': results}


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
        if (kind == 'container' and not require_created
                and info.get('State', {}).get('Running') is True
                and info.get('State', {}).get('Paused') is not True):
            _fail('resource_restarted_after_stop')
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


def _origin_arm(root: Path, plan: dict, role: str, dispatch_id: str,
                gate_nonce: str, root_pid: int, root_start: int) -> dict:
    if (role not in ORIGIN_ROLES or not re.fullmatch(r'[0-9a-f]{32}', dispatch_id)
            or not re.fullmatch(r'[0-9a-f]{32}', gate_nonce)
            or root_pid <= 1 or root_start <= 0):
        _fail('native_origin_gate_marker_invalid')
    controls = _controls(root)
    dispatch = _read_json(controls / 'dispatch' / (dispatch_id + '.pre.json'))
    resources = _read_json(_origin_resources_path(root))
    if (dispatch.get('status') != 'unknown_effect' or dispatch.get('role') != role
            or resources.get('status') != 'active'
            or [row.get('role') for row in resources.get('resources', [])] != list(ORIGIN_ROLES)):
        _fail('native_origin_dispatch_not_armed')
    registration = {'kind': 'native-origin-registration-v1',
                    'dispatch_id': dispatch_id, 'role': role,
                    'target': ORIGIN_ROLES[role], 'gate_nonce': gate_nonce,
                    'root_pid': root_pid, 'root_starttime': root_start,
                    'run_nonce': resources['nonce'],
                    'agent_container_id': _resources(root)[role],
                    'target_container_id': _resources(root)[ORIGIN_ROLES[role]],
                    'sidecar_container_id': next(row['id'] for row in resources['resources']
                                                 if row['role'] == role),
                    'dispatch_pre_sha256': _sha(controls / 'dispatch' / (dispatch_id + '.pre.json')),
                    'producer_manifest_sha256': _sha(controls / 'producer-manifest.json'),
                    'source_manifest_sha256': plan['source_manifest_sha256'],
                    'target_image_id': plan['target_image_id'],
                    'binary_sha256': plan['native_origin']['binary_sha256']}
    path = controls / 'origin/registrations' / (dispatch_id + '.json')
    _write_json(path, registration, once=True)
    arm = {'kind': 'native-origin-arm-v1', 'status': 'armed',
           'role': role, 'target': ORIGIN_ROLES[role],
           'run_nonce': resources['nonce'], 'dispatch_id': dispatch_id,
           'gate_nonce': gate_nonce, 'root_pid': root_pid,
           'root_starttime': root_start, 'heartbeat_unix_ms': int(time.time() * 1000)}
    _write_json(controls / 'origin/arms' / (role + '.json'), arm)
    return arm


def _origin_disarm(root: Path, role: str, arm: dict) -> None:
    closed = dict(arm)
    closed['status'] = 'closed'
    closed['heartbeat_unix_ms'] = int(time.time() * 1000)
    _write_json(_controls(root) / 'origin/arms' / (role + '.json'), closed)


def _origin_close_window(root: Path, target: str, dispatch_id: str) -> Path:
    """Seal the app collector end boundary before a later native turn starts."""
    controls = _controls(root)
    window_path = controls / 'observer' / target / ('window-' + dispatch_id + '.json')
    window = _read_json(window_path)
    topology = window.get('topology')
    if (window.get('dispatch_id') != dispatch_id or not isinstance(topology, dict)
            or not isinstance(topology.get('collector_db'), str)):
        _fail('native_origin_window_invalid')
    collector = _file(Path(topology['collector_db']), private=True)
    with closing(sqlite3.connect(collector.as_uri() + '?mode=ro', uri=True)) as db:
        rows = db.execute('SELECT id,peer,payload FROM receipts ORDER BY id').fetchall()
    before = window.get('collector_max_id_before')
    prefix = [row for row in rows if type(before) is int and row[0] <= before]
    if (type(before) is not int or before < 0
            or len(prefix) != window.get('collector_count_before')
            or hashlib.sha256(json.dumps(prefix, separators=(',', ':'),
                                         ensure_ascii=True).encode()).hexdigest() !=
               window.get('collector_prefix_sha256')
            or len(rows) > 5000):
        _fail('native_origin_window_prefix_changed')
    receipt = {'kind': 'native-origin-window-close-v1', 'target': target,
               'dispatch_id': dispatch_id, 'window_sha256': _sha(window_path),
               'collector_count_after': len(rows),
               'collector_max_id_after': rows[-1][0] if rows else 0,
               'collector_prefix_sha256_after': hashlib.sha256(
                   json.dumps(rows, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()}
    path = controls / 'origin/window-close' / (dispatch_id + '.json')
    _write_json(path, receipt, once=True)
    return path


def _native_exec(root: Path, role: str, argv: list[str], timeout_seconds: int,
                 *, origin_dispatch: str | None = None) -> subprocess.CompletedProcess[bytes]:
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
    origin = _origin_enabled(plan) and argv[0] == 'run'
    if origin and origin_dispatch is None:
        _fail('native_origin_dispatch_missing')
    if origin_dispatch is not None and not origin:
        _fail('native_origin_dispatch_unexpected')
    gate_nonce = uuid.uuid4().hex if origin else None
    command = [str(DOCKER_BINARY), 'container', 'exec',
               *(['-i'] if origin else []), '-w', '/workspace/project', identifier,
               *(['/origin/bin/native-origin', 'gate', gate_nonce] if origin else
                 ['/usr/local/bin/opencode']), *argv]
    with native.dispatch_guard(state):
        try:
            child = subprocess.Popen(command, stdin=subprocess.PIPE if origin else subprocess.DEVNULL,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     env={key: value for key, value in os.environ.items()
                                          if key in ('HOME', 'PATH', 'DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_CONFIG')})
        except OSError:
            _fail('native_dispatch_unknown_effect')
    arm = None
    heartbeat_stop = threading.Event()
    heartbeat_errors = []
    heartbeat_thread = None
    try:
        if origin:
            if not select.select([child.stdout], [], [], 10)[0]:
                _fail('native_origin_gate_marker_missing')
            marker = child.stdout.readline(128).decode('ascii', errors='strict').strip().split('\t')
            if (len(marker) != 4 or marker[0] != 'LRH_GATE' or marker[1] != gate_nonce
                    or not marker[2].isdigit() or not marker[3].isdigit()):
                _fail('native_origin_gate_marker_invalid')
            arm = _origin_arm(root, plan, role, origin_dispatch, gate_nonce,
                              int(marker[2]), int(marker[3]))

            def refresh() -> None:
                while not heartbeat_stop.wait(1):
                    try:
                        arm['heartbeat_unix_ms'] = int(time.time() * 1000)
                        _write_json(_controls(root) / 'origin/arms' / (role + '.json'), arm)
                    except Exception as error:
                        heartbeat_errors.append(str(error))
                        return

            heartbeat_thread = threading.Thread(target=refresh, daemon=True)
            heartbeat_thread.start()
            child.stdin.write(b'G')
            child.stdin.flush()
            child.stdin.close()
            child.stdin = None
        stdout, stderr = child.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        heartbeat_stop.set()
        child.terminate()
        try:
            child.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.communicate()
        _fail('native_dispatch_timeout_unknown_effect')
    except Exception:
        heartbeat_stop.set()
        child.terminate()
        try:
            child.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.communicate()
        raise
    finally:
        heartbeat_stop.set()
        if heartbeat_thread is not None:
            heartbeat_thread.join()
        if arm is not None:
            _origin_disarm(root, role, arm)
    if heartbeat_errors:
        _fail('native_origin_heartbeat_failed_unknown_effect')
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


def _native_response_ids(stdout: str) -> list[str]:
    """Read only completed native tool output, never model text, for T01 joins."""
    found = set()
    for line in stdout.splitlines():
        event = json.loads(line)
        part = event.get('part') if isinstance(event, dict) else None
        state = part.get('state') if isinstance(part, dict) else None
        if (not isinstance(part, dict) or part.get('type') != 'tool' or
                not isinstance(state, dict) or state.get('status') != 'completed'):
            continue
        output = state.get('output')
        if output is None:
            continue
        rendered = output if isinstance(output, str) else json.dumps(output, sort_keys=True)
        found.update(re.findall(r'(?i)X-LRH-Request-ID:\s*([0-9a-f]{32})', rendered))
    return sorted(item.lower() for item in found)


def _native_response_claims(stdout: str) -> list[dict]:
    """Retain only broker IDs and hashes from completed native tool events."""
    claims = []
    for number, line in enumerate(stdout.splitlines(), 1):
        event = json.loads(line)
        part = event.get('part') if isinstance(event, dict) else None
        state = part.get('state') if isinstance(part, dict) else None
        if (not isinstance(part, dict) or part.get('type') != 'tool' or
                not isinstance(state, dict) or state.get('status') != 'completed'):
            continue
        output = state.get('output')
        rendered = output if isinstance(output, str) else json.dumps(output, sort_keys=True)
        ids = sorted(set(item.lower() for item in re.findall(
            r'(?i)X-LRH-Request-ID:\s*([0-9a-f]{32})', rendered)))
        if ids:
            claims.append({'line': number, 'tool': part.get('tool') if part.get('tool') in
                           ('shell', 'read', 'webfetch') else 'other',
                           'input_sha256': hashlib.sha256(json.dumps(state.get('input'), sort_keys=True,
                                                         default=str).encode()).hexdigest(),
                           'output_sha256': hashlib.sha256(json.dumps(output, sort_keys=True,
                                                          default=str).encode()).hexdigest(),
                           'request_ids': ids})
    return claims


def _unresolved_dispatches(root: Path) -> list[str]:
    unresolved = []
    for path in (_controls(root) / 'dispatch').glob('*.json'):
        if path.name.endswith(('.trace.json', '.pre.json', '.origin.json')):
            continue
        record = _read_json(path)
        if record.get('status') == 'unknown_effect':
            unresolved.append(record.get('dispatch_id', path.stem))
    return sorted(unresolved)


def invoke_native(run_root: Path, role: str, session_id: str, prompt: str,
                  include_raw: bool = False, before_dispatch=None,
                  kanboard_role_grant: bool = False) -> dict:
    root = _private_root(Path(run_root))
    if (role not in ('researcher', 'resume', 'reviewer-1', 'reviewer-2')
            or not SESSION_RE.fullmatch(session_id) or not isinstance(prompt, str)
            or not 1 <= len(prompt.encode()) <= 128 * 1024):
        _fail('native_turn_input_invalid')
    if CREDENTIAL_TEXT.search(prompt):
        _fail('native_prompt_credential_like')
    if before_dispatch is not None and not callable(before_dispatch):
        _fail('native_observer_hook_invalid')
    if kanboard_role_grant and role != 'resume':
        _fail('kanboard_recovery_turn_unqualified')
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
        _write_json(record_path.with_name(dispatch_id + '.pre.json'), record, once=True)
        try:
            if _capture_mode(_plan(root)):
                target = 'target' if role in ('researcher', 'resume') else 'review-target-' + role[-1]
                _load_capture_module(root).bind_dispatch(root, target, dispatch_id)
            if kanboard_role_grant:
                _arm_kanboard_role_grant(root, dispatch_id, role)
            if before_dispatch is not None:
                before_dispatch(root, dispatch_id)
            result = _native_exec(root, role,
                                  ['run', '--standalone', '--agent', 'build', '--model', MODEL,
                                   '--format', 'json', '--session', session_id, prompt],
                                  min(3600, max(30, _plan(root)['limits']['duration_seconds'])),
                                  origin_dispatch=dispatch_id if _origin_enabled(_plan(root)) else None)
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
            if _origin_enabled(_plan(root)):
                registration = _controls(root) / 'origin/registrations' / (dispatch_id + '.json')
                record['origin_registration_sha256'] = _sha(registration)
                record['native_response_claims'] = _native_response_claims(stdout)
            if 'kanboard_capture' in _plan(root):
                target = 'target' if role in ('researcher', 'resume') else 'review-target-' + role[-1]
                window = _read_json(_controls(root) / 'observer' / target /
                                    ('window-' + dispatch_id + '.json'))
                before = _file(record_path.with_name(dispatch_id + '.pre.json'), private=True).read_bytes()
                origin = _load_origin_gate(root).assess(window, before, record, trace_path.read_bytes())
                _write_json(record_path.with_name(dispatch_id + '.origin.json'), origin, once=True)
                record['origin_hold'] = origin
            elif 't01_capture' in _plan(root):
                target = 'target' if role in ('researcher', 'resume') else 'review-target-' + role[-1]
                closed = _load_capture_module(root).close_dispatch(
                    root, target, dispatch_id, _native_response_ids(stdout))
                origin = {'status': 'held', 'reason': closed['reason'],
                          'dispatch_id': dispatch_id, 'native_request_attributable': False,
                          'closed_window_sha256': _sha(_controls(root) / 'observer' / target /
                                                       ('closed-' + dispatch_id + '.json')),
                          'joined_request_ids': closed['joined_request_ids']}
                _write_json(record_path.with_name(dispatch_id + '.origin.json'), origin, once=True)
                record['origin_hold'] = origin
            if _origin_enabled(_plan(root)):
                target = ORIGIN_ROLES[role]
                record['origin_window_close_sha256'] = _sha(_origin_close_window(root, target, dispatch_id))
            _write_json(record_path, record)
            returned = dict(record)
            if include_raw:
                returned['_raw_stdout'] = stdout
            return returned
        except Exception:
            # The durable pre-dispatch record remains uncertain; no automatic retry.
            record['status'] = 'unknown_effect'
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


def _probe_origin_route(root: Path, plan: dict, bindings: dict) -> None:
    """Show each broker answers only in its target namespace, not on agent TCP."""
    code = ('$s=@stream_socket_client("tcp://".$argv[1].":".$argv[2],$e,$m,2);'
            'if(!$s)exit(2);fclose($s);echo "connected";')
    for role, target in ORIGIN_ROLES.items():
        target_id = bindings[target]
        target_ip = (bindings['research_target_ip'] if target == 'target' else
                     bindings['review_target_ips'][role])
        deadline = time.monotonic() + 30
        connected = False
        while time.monotonic() < deadline and run_active(root):
            result = _docker('container', 'exec', target_id, 'php', '-r', code,
                             '127.0.0.1', str(plan['target_port']), timeout=5,
                             allow_failure=True)
            if result.returncode == 0 and result.stdout == b'connected':
                connected = True
                break
            time.sleep(.25)
        if not connected:
            _fail('native_origin_target_loopback_unavailable')
        direct = _docker('container', 'exec', bindings[role],
                         '/origin/bin/native-origin', 'probe-tcp', target_ip,
                         str(plan['target_port']), timeout=5, allow_failure=True)
        if direct.returncode != 0 or direct.stdout not in (b'unreachable', b'connected'):
            _fail('native_origin_direct_tcp_probe_unavailable')
        if direct.stdout == b'connected':
            _fail('native_origin_direct_tcp_bypass')


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
    controls = _controls(root)
    if (controls / 'resources.json').exists() or (controls / 'native-state/RUN.json').exists():
        _fail('run_already_started_or_ambiguous')
    _approval(root, plan, Path(approval_path))
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
        if _capture_mode(plan):
            _capture_approved_specs(root, plan,
                                    _validate_target_command(controls / 'target-command.json'),
                                    verify_source=True)
        if (controls / 'native-state/STOP_REQUEST').exists():
            _fail('native_stop_before_start')
        ready = native.start()
        if (ready['proxy_info'].get('authority') != AUTHORITY
                or ready['proxy_info'].get('port') != port
                or ready['proxy_info'].get('host') != '127.0.0.1'
                or ready['ids'] != [row['id'] for row in rows if row['kind'] == 'container']):
            _fail('native_authority_readback_mismatch')
        result['origin_start'] = _origin_start(root, plan, nonce, bindings)
        if _origin_enabled(plan) and result['origin_start']['status'] != 'active':
            _fail('native_origin_start_incomplete')
        capture_topology_sha = None
        if _capture_mode(plan):
            capture_module = _load_capture_module(root)
            topology = {target: capture_module.attest(root, target) for target in CAPTURE_TARGETS}
            topology_path = controls / 'capture-topology.json'
            _write_json(topology_path, topology, once=True)
            capture_topology_sha = _sha(topology_path)
        if _origin_enabled(plan):
            _probe_origin_route(root, plan, bindings)
        else:
            _probe_target(root, bindings['researcher'], bindings['research_target_ip'], plan['target_port'])
            for role in ('reviewer-1', 'reviewer-2'):
                _probe_target(root, bindings[role], bindings['review_target_ips'][role], plan['target_port'])
        surface = _surface_probe(root, bindings['researcher'])
        _write_json(controls / 'loaded-surface.json', surface, once=True)
        _write_json(controls / 'activation.json', {
            'kind': 'native-research-activation-v1', 'nonce': nonce,
            'plan_sha256': _sha(root / 'plan.json'), 'manifest_sha256': _sha(manifest),
            'approval_sha256': _sha(controls / 'approval.json'),
            'watcher_pid': ready['watcher_pid'], 'started_at': datetime.now(timezone.utc).isoformat(),
            'provider_route': PROVIDER_ROUTE, 'provider_authority': AUTHORITY,
            'model': MODEL, 'limits': plan['limits'],
            'protected_capture': 'unavailable',
            'capture_topology_sha256': capture_topology_sha,
            'loaded_surface_sha256': _sha(controls / 'loaded-surface.json'),
        }, once=True)
        result = {'status': 'active', 'run_root': str(root),
                  'origin_start': result['origin_start'],
                  'run_identity': allowance_snapshot(root)['run_identity'],
                  'target_url': ('unix:///origin/socket/ingress.sock' if _origin_enabled(plan) else
                                 f'http://{bindings["research_target_ip"]}:{plan["target_port"]}'),
                  'protected_capture': 'unavailable',
                  'capture_topology': (('attested_original_session_origin_held' if 't01_capture' in plan
                                        else 'attested_origin_and_credentials_held') if capture_topology_sha
                                       else 'not_configured'),
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
                result['origin_stop'] = _origin_stop(root, plan, result['native_stop']['status'])
            except Exception as error:
                result['origin_stop'] = {'status': 'unresolved', 'code': str(error)}
        else:
            result['origin_stop'] = {'status': 'not_taken'}
        if result['native_stop']['status'] == 'stopped':
            try:
                result['host_snapshot'] = _stopped_snapshot(root, plan)
            except NativeResearchError as error:
                result['host_snapshot'] = {'status': 'unavailable', 'code': str(error)}
            except Exception:
                result['host_snapshot'] = {'status': 'unavailable', 'code': 'host_snapshot_unavailable'}
        else:
            result['host_snapshot'] = {'status': 'not_taken'}
        if (result['native_stop']['status'] in ('stopped', 'closed_before_activation', 'not_started')
                and result['origin_stop']['status'] in ('complete', 'not_configured', 'not_started', 'partial')):
            try:
                result['capture_stop'] = _capture_stop(root, plan, result['native_stop']['status'])
            except Exception as error:
                result['capture_stop'] = {'status': 'unresolved', 'code': str(error)}
        else:
            result['capture_stop'] = {'status': 'not_taken'}
        if result['capture_stop']['status'] in ('complete', 'not_configured'):
            try:
                result['origin_cleanup'] = _origin_cleanup(root, plan)
            except Exception as error:
                result['origin_cleanup'] = {'status': 'unresolved', 'code': str(error)}
        if result.get('origin_cleanup', {}).get('status') in ('complete', 'not_configured', 'not_started'):
            try:
                result['cleanup'] = _cleanup_resources(
                    root, require_created=result['native_stop']['status'] == 'not_started')
            except Exception:
                result['cleanup'] = {'status': 'unresolved'}
        if result.get('cleanup', {}).get('status') == 'complete':
            try:
                result['capture_cleanup'] = _capture_cleanup(root, plan)
            except Exception as error:
                result['capture_cleanup'] = {'status': 'unresolved', 'code': str(error)}
        capability_path.unlink(missing_ok=True)
        if (result['native_stop']['status'] in ('unsafe', 'unresolved')
                or (_origin_enabled(plan) and result['native_stop']['status'] == 'stopped'
                    and result.get('origin_start', {}).get('status') != 'active')
                or result['origin_stop']['status'] not in ('complete', 'not_configured', 'not_started')
                or result.get('origin_cleanup', {}).get('status') not in ('complete', 'not_configured', 'not_started')
                or result['capture_stop']['status'] not in ('complete', 'not_configured')
                or result.get('cleanup', {}).get('status') != 'complete'
                or result.get('capture_cleanup', {}).get('status') not in ('complete', 'not_configured')):
            result['status'] = 'unsafe_or_unresolved'
        elif (result['native_stop']['status'] == 'stopped'
              and result['host_snapshot']['status'] != 'complete'):
            result['status'] = 'stopped_evidence_incomplete'
        elif result.get('status') == 'active' and result['native_stop']['status'] == 'stopped':
            result['status'] = 'stopped_complete'
        else:
            result['status'] = 'start_incomplete'
        _write_json(controls / 'final.json', result)
    return result


def stop(run_root: Path) -> dict:
    root = _private_root(Path(run_root))
    controls = _controls(root)
    if not (controls / 'native-state/RUN.json').exists() and not (controls / 'resources.json').exists():
        return {'status': 'not_active', 'run_root': str(root)}
    native, _ = _activate_controls(root)
    native.request_stop(controls / 'native-state', 'operator_stop')
    return {'status': 'stop_requested', 'run_root': str(root)}


def recover_start(run_root: Path) -> dict:
    """Remove exact stopped preactivation resources after owner loss, never a live run."""
    root = _private_root(Path(run_root))
    with _owner_lock(root):
        plan = _verified_plan(root)
        controls = _controls(root)
        if not (controls / 'resources.json').exists():
            if (any((controls / 'observer' / target / 'resources.json').exists()
                    for target in CAPTURE_TARGETS)
                    or _origin_resources_path(root).exists()
                    or (controls / 'producer-manifest.json').exists()
                    or (controls / 'native-state/RUN.json').exists()):
                _fail('resource_record_missing_after_creation')
            return {'status': 'no_resources', 'run_root': str(root)}
        state = controls / 'native-state'
        if (state / 'UNSAFE').exists():
            _fail('native_run_not_verified_stopped')
        if (state / 'REVOKED').exists():
            native_status, require_created = 'stopped', False
        elif (state / 'STARTUP_CLOSED').exists():
            native_status, require_created = 'closed_before_activation', False
        elif (state / 'RUN.json').exists():
            _fail('native_run_not_verified_stopped')
        else:
            native_status, require_created = 'not_started', True
        origin_stop = _origin_stop(root, plan, native_status)
        if origin_stop['status'] not in ('complete', 'not_configured', 'not_started', 'partial'):
            _fail('native_origin_stop_incomplete')
        capture_stop = _capture_stop(root, plan, native_status)
        host_snapshot = {'status': 'not_taken'}
        if native_status == 'stopped':
            try:
                snapshot_path = controls / 'host-snapshot.json'
                if snapshot_path.exists():
                    receipt = _read_json(snapshot_path)
                    if (receipt.get('plan_sha256') != _sha(root / 'plan.json')
                            or receipt.get('native_stop', {}).get('revoked_sha256') != _sha(state / 'REVOKED')):
                        _fail('recovery_host_snapshot_changed')
                    host_snapshot = {'status': receipt.get('status'), 'receipt_path': str(snapshot_path),
                                     'receipt_sha256': _sha(snapshot_path)}
                else:
                    host_snapshot = _stopped_snapshot(root, plan)
            except NativeResearchError as error:
                host_snapshot = {'status': 'unavailable', 'code': str(error)}
            except Exception:
                host_snapshot = {'status': 'unavailable', 'code': 'host_snapshot_unavailable'}
        origin_cleanup = _origin_cleanup(root, plan)
        if origin_cleanup['status'] not in ('complete', 'not_configured', 'not_started'):
            _fail('native_origin_cleanup_incomplete')
        result = _cleanup_resources(root, require_created=require_created)
        capture_cleanup = _capture_cleanup(root, plan)
        recovery = {'status': ('recovered_exact_resources' if origin_stop['status'] != 'partial'
                               else 'unsafe_or_unresolved'), 'run_root': str(root),
                    'native_state': native_status, 'host_snapshot': host_snapshot,
                    'origin_stop': origin_stop, 'origin_cleanup': origin_cleanup,
                    'capture_stop': capture_stop, 'cleanup': result,
                    'capture_cleanup': capture_cleanup}
        _write_json(controls / 'recovery.json', recovery)
        return recovery


def _poststop_role_grant_boundary(root: Path, dispatch_id: str) -> Path:
    plan = _verified_plan(root)
    if 'kanboard_capture' not in plan:
        _fail('kanboard_recovery_not_configured')
    controls = _controls(root)
    dispatch = _read_json(controls / 'dispatch' / (dispatch_id + '.json'))
    if dispatch.get('dispatch_id') != dispatch_id or dispatch.get('status') != 'unknown_effect':
        _fail('kanboard_recovery_dispatch_not_unknown')
    _, _, topology = _kanboard_recovery_window(root, dispatch_id, dispatch.get('role'))
    final_path = controls / 'final.json'
    recovery_path = controls / 'recovery.json'
    if final_path.exists():
        terminal = _read_json(final_path)
        stopped = terminal.get('status') == 'stopped_complete' and terminal.get('native_stop', {}).get('status') == 'stopped'
    elif recovery_path.exists():
        terminal = _read_json(recovery_path)
        stopped = terminal.get('status') == 'recovered_exact_resources' and terminal.get('native_state') == 'stopped'
    else:
        _fail('kanboard_recovery_run_not_stopped')
    if (not stopped or terminal.get('host_snapshot', {}).get('status') != 'complete'
            or terminal.get('capture_stop', {}).get('status') != 'complete'
            or terminal.get('cleanup', {}).get('status') != 'complete'
            or terminal.get('capture_cleanup', {}).get('status') != 'complete'):
        _fail('kanboard_recovery_run_not_stopped')
    if _origin_enabled(plan):
        origin_stopped = controls / 'origin/stopped.json'
        origin_cleaned = controls / 'origin/cleanup.json'
        if (terminal.get('origin_stop', {}).get('status') != 'complete'
                or terminal.get('origin_cleanup', {}).get('status') != 'complete'
                or terminal['origin_stop'].get('receipt_sha256') != _sha(origin_stopped)
                or terminal['origin_cleanup'].get('receipt_sha256') != _sha(origin_cleaned)):
            _fail('kanboard_recovery_ingress_stop_unverified')
    manifest_path = controls / 'producer-manifest.json'
    manifest = _read_json(manifest_path)
    resources = _read_json(controls / 'resources.json')
    run = _read_json(controls / 'native-state/RUN.json')
    revoked_path = controls / 'native-state/REVOKED'
    revoked = _read_json(revoked_path)
    ids = [row.get('id') for row in resources.get('resources', []) if row.get('kind') == 'container']
    manifest_ids = [row.get('id') for row in manifest.get('producers', [])]
    manifest_sha = _sha(manifest_path)
    revoked_sha = _sha(revoked_path)
    if (len(ids) != 8 or len(set(ids)) != 8 or not all(isinstance(value, str) and HEX_RE.fullmatch(value) for value in ids)
            or ids != manifest_ids or run.get('ids') != ids or revoked.get('ids') != ids
            or run.get('manifest_sha256') != manifest_sha
            or revoked.get('manifest_sha256') != manifest_sha
            or revoked.get('producers_verified_stopped') is not True):
        _fail('kanboard_recovery_stop_proof_changed')
    snapshot_path = controls / 'host-snapshot.json'
    snapshot = _read_json(snapshot_path)
    if (terminal['host_snapshot'].get('receipt_path') != str(snapshot_path)
            or terminal['host_snapshot'].get('receipt_sha256') != _sha(snapshot_path)
            or snapshot.get('status') != 'complete'
            or snapshot.get('plan_sha256') != _sha(root / 'plan.json')
            or snapshot.get('native_stop', {}).get('manifest_sha256') != manifest_sha
            or snapshot.get('native_stop', {}).get('revoked_sha256') != revoked_sha):
        _fail('kanboard_recovery_snapshot_changed')
    collector = _file(Path(topology['collector_db']), private=True)
    frozen = _read_json(controls / 'observer/target/frozen.json')
    try:
        with closing(sqlite3.connect(collector.as_uri() + '?mode=ro', uri=True)) as db:
            count, maximum = db.execute('SELECT COUNT(*),COALESCE(MAX(id),0) FROM receipts').fetchone()
    except sqlite3.DatabaseError:
        _fail('kanboard_recovery_collector_unavailable')
    if (frozen.get('kind') != 'kanboard-capture-frozen-v1' or frozen.get('target') != 'target'
            or frozen.get('native_stop_kind') != 'REVOKED'
            or frozen.get('native_stop_sha256') != revoked_sha
            or frozen.get('producer_manifest_sha256') != manifest_sha
            or frozen.get('sqlite_sha256') != _sha(collector)
            or frozen.get('receipt_count') != count or frozen.get('last_receipt_id') != maximum):
        _fail('kanboard_recovery_frozen_collector_changed')
    return collector


def reconcile_role_grant(run_root: Path, dispatch_id: str) -> dict:
    """Observe one declared S10 effect only after exact owned stop and capture freeze."""
    result = {'status': 'hold_unknown', 'dispatch_id': dispatch_id,
              'scope': 'kanboard_b_q_role_grant_v1', 'retry_original': False,
              'run_resume_allowed': False}
    if not isinstance(dispatch_id, str) or not re.fullmatch(r'[0-9a-f]{32}', dispatch_id):
        return dict(result, reason='dispatch_id_invalid')
    try:
        root = _private_root(Path(run_root))
        with _owner_lock(root):
            collector = _poststop_role_grant_boundary(root, dispatch_id)
            before = _sha(collector)
            observed = _load_recovery_module(root).reconcile_kanboard_role_grant(root, dispatch_id)
            if _sha(collector) != before:
                _fail('kanboard_recovery_collector_changed_during_read')
            return observed
    except (NativeResearchError, OSError, sqlite3.DatabaseError, TypeError, KeyError, ValueError) as error:
        return dict(result, reason=str(error) if isinstance(error, NativeResearchError)
                    else 'kanboard_recovery_unavailable')


def _origin_transport_proof(root: Path, dispatch_id: str) -> dict:
    """Bind process, native tool and app IDs from stopped host-owned bytes."""
    plan = _verified_plan(root)
    if not _origin_enabled(plan):
        _fail('native_origin_not_configured')
    controls = _controls(root)
    final_path = controls / 'final.json'
    recovery_path = controls / 'recovery.json'
    if final_path.exists():
        terminal = _read_json(final_path)
        terminal_ok = terminal.get('status') == 'stopped_complete'
    elif recovery_path.exists():
        terminal = _read_json(recovery_path)
        terminal_ok = terminal.get('status') == 'recovered_exact_resources' and terminal.get('native_state') == 'stopped'
    else:
        _fail('native_origin_run_not_stopped')
    if (not terminal_ok or terminal.get('host_snapshot', {}).get('status') != 'complete'
            or terminal.get('origin_stop', {}).get('status') != 'complete'
            or terminal.get('origin_cleanup', {}).get('status') != 'complete'
            or terminal.get('capture_stop', {}).get('status') != 'complete'
            or terminal.get('cleanup', {}).get('status') != 'complete'
            or terminal.get('capture_cleanup', {}).get('status') != 'complete'):
        _fail('native_origin_run_not_stopped')
    stop_path, cleanup_path = controls / 'origin/stopped.json', controls / 'origin/cleanup.json'
    stop, cleanup = _read_json(stop_path), _read_json(cleanup_path)
    manifest_path, revoked_path = controls / 'producer-manifest.json', controls / 'native-state/REVOKED'
    manifest, revoked = _read_json(manifest_path), _read_json(revoked_path)
    run, resources = _read_json(controls / 'native-state/RUN.json'), _read_json(controls / 'resources.json')
    ids = [row.get('id') for row in resources.get('resources', []) if row.get('kind') == 'container']
    if (len(ids) != 8 or ids != [item.get('id') for item in manifest.get('producers', [])]
            or run.get('ids') != ids or revoked.get('ids') != ids
            or revoked.get('producers_verified_stopped') is not True
            or stop.get('kind') != 'native-origin-stopped-v1'
            or stop.get('native_stop_kind') != 'REVOKED'
            or stop.get('native_stop_sha256') != _sha(revoked_path)
            or stop.get('producer_manifest_sha256') != _sha(manifest_path)
            or cleanup.get('kind') != 'native-origin-cleanup-v1'
            or cleanup.get('stopped_sha256') != _sha(stop_path)
            or cleanup.get('all_absent') is not True
            or terminal['origin_stop'].get('receipt_sha256') != _sha(stop_path)
            or terminal['origin_cleanup'].get('receipt_sha256') != _sha(cleanup_path)):
        _fail('native_origin_stop_proof_changed')
    sidecars = _read_json(_origin_resources_path(root))
    rows = sidecars.get('resources', [])
    if (sidecars.get('kind') != 'native-origin-resources-v1'
            or sidecars.get('status') != 'removed'
            or sidecars.get('nonce') != resources.get('nonce')
            or [row.get('role') for row in rows] != list(ORIGIN_ROLES)
            or [row.get('target') for row in rows] != list(ORIGIN_ROLES.values())
            or [row.get('id') for row in rows] != cleanup.get('resource_ids')
            or [row.get('id') for row in rows] != [row.get('id') for row in stop.get('containers', [])]
            or any(not isinstance(row.get('id'), str) or not HEX_RE.fullmatch(row['id']) for row in rows)):
        _fail('native_origin_sidecar_set_changed')
    dispatch_path = controls / 'dispatch' / (dispatch_id + '.json')
    dispatch = _read_json(dispatch_path)
    role = dispatch.get('role')
    if (dispatch.get('kind') != 'native-dispatch-v1' or dispatch.get('status') != 'acknowledged'
            or dispatch.get('dispatch_id') != dispatch_id or role not in ORIGIN_ROLES):
        _fail('native_origin_dispatch_not_acknowledged')
    target = ORIGIN_ROLES[role]
    registration_path = controls / 'origin/registrations' / (dispatch_id + '.json')
    registration = _read_json(registration_path)
    sidecar_id = next(row['id'] for row in rows if row['role'] == role)
    if (dispatch.get('origin_registration_sha256') != _sha(registration_path)
            or registration.get('kind') != 'native-origin-registration-v1'
            or registration.get('dispatch_id') != dispatch_id
            or registration.get('role') != role or registration.get('target') != target
            or registration.get('run_nonce') != resources['nonce']
            or registration.get('agent_container_id') != _resources(root)[role]
            or registration.get('target_container_id') != _resources(root)[target]
            or registration.get('sidecar_container_id') != sidecar_id
            or registration.get('dispatch_pre_sha256') !=
               _sha(controls / 'dispatch' / (dispatch_id + '.pre.json'))
            or registration.get('producer_manifest_sha256') != _sha(manifest_path)
            or registration.get('source_manifest_sha256') != plan['source_manifest_sha256']
            or registration.get('target_image_id') != plan['target_image_id']
            or registration.get('binary_sha256') != plan['native_origin']['binary_sha256']):
        _fail('native_origin_registration_changed')
    trace_path = controls / 'dispatch' / (dispatch_id + '.trace.json')
    trace = _read_json(trace_path)
    if (dispatch.get('native_trace_sha256') != _sha(trace_path)
            or trace.get('kind') != 'protected-native-event-trace-v1'
            or trace.get('session_id') != dispatch.get('session_id')
            or not isinstance(trace.get('events'), list)):
        _fail('native_origin_trace_changed')
    claims = dispatch.get('native_response_claims')
    if not isinstance(claims, list) or not claims:
        _fail('native_origin_native_ids_absent')
    native_ids = []
    events = {item.get('line'): item for item in trace['events'] if isinstance(item, dict)}
    for claim in claims:
        if not isinstance(claim, dict) or not isinstance(claim.get('request_ids'), list):
            _fail('native_origin_native_claim_invalid')
        event = events.get(claim.get('line'))
        if (not isinstance(event, dict) or event.get('part_type') != 'tool'
                or event.get('status') != 'completed' or event.get('tool') != 'shell'
                or claim.get('tool') != 'shell'
                or claim.get('input_sha256') != event.get('input_sha256')
                or claim.get('output_sha256') != event.get('output_sha256')
                or not claim['request_ids']
                or any(not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{32}', value)
                       for value in claim['request_ids'])):
            _fail('native_origin_native_claim_invalid')
        native_ids.extend(claim['request_ids'])
    if len(native_ids) != len(set(native_ids)):
        _fail('native_origin_native_id_duplicate')
    all_rows, seen_ids = [], set()
    for source_role in ORIGIN_ROLES:
        ledger_path = controls / 'origin/ledger' / source_role / 'requests.jsonl'
        if (not ledger_path.exists() or ledger_path.stat().st_size > 16 * 1024 * 1024
                or _sha(ledger_path) != stop.get('ledger_sha256', {}).get(source_role)):
            _fail('native_origin_ledger_changed')
        for line in ledger_path.read_bytes().splitlines():
            try:
                row = json.loads(line)
            except (UnicodeError, ValueError):
                _fail('native_origin_ledger_invalid')
            request_id = row.get('broker_request_id') if isinstance(row, dict) else None
            if (row.get('kind') != 'native-origin-request-v1'
                    or row.get('role') != source_role or row.get('target') != ORIGIN_ROLES[source_role]
                    or row.get('run_nonce') != resources['nonce']
                    or not isinstance(request_id, str) or not re.fullmatch(r'[0-9a-f]{32}', request_id)
                    or request_id in seen_ids):
                _fail('native_origin_ledger_invalid')
            seen_ids.add(request_id)
            if row.get('dispatch_id') != dispatch_id:
                continue
            ancestry = row.get('ancestry')
            if (source_role != role or row.get('gate_nonce') != registration.get('gate_nonce')
                    or row.get('root_pid') != registration.get('root_pid')
                    or row.get('root_starttime') != registration.get('root_starttime')
                    or row.get('sender_uid') != os.getuid()
                    or not isinstance(ancestry, list) or not 1 <= len(ancestry) <= 64
                    or not isinstance(ancestry[0], dict) or not isinstance(ancestry[-1], dict)
                    or ancestry[0].get('pid') != row.get('sender_pid')
                    or ancestry[0].get('starttime') != row.get('sender_starttime')
                    or ancestry[-1].get('pid') != registration.get('root_pid')
                    or ancestry[-1].get('starttime') != registration.get('root_starttime')
                    or row.get('method') not in ('GET', 'POST')
                    or any(not isinstance(row.get(key), str) or not HEX_RE.fullmatch(row[key])
                           for key in ('route_sha256', 'body_sha256', 'request_sha256',
                                       'response_sha256'))):
                _fail('native_origin_ledger_binding_invalid')
            all_rows.append(row)
    ledger_ids = [row['broker_request_id'] for row in all_rows]
    if not ledger_ids or len(ledger_ids) != len(set(ledger_ids)):
        _fail('native_origin_ledger_ids_absent')
    window_path = controls / 'observer' / target / ('window-' + dispatch_id + '.json')
    window = _read_json(window_path)
    topology = window.get('topology')
    if not isinstance(topology, dict) or not isinstance(topology.get('collector_db'), str):
        _fail('native_origin_window_invalid')
    collector = _file(Path(topology['collector_db']), private=True)
    frozen_path = controls / 'observer' / target / 'frozen.json'
    frozen = _read_json(frozen_path)
    if (frozen.get('kind') != 'kanboard-capture-frozen-v1'
            or frozen.get('target') != target or frozen.get('native_stop_kind') != 'REVOKED'
            or frozen.get('native_stop_sha256') != _sha(revoked_path)
            or frozen.get('producer_manifest_sha256') != _sha(manifest_path)
            or frozen.get('sqlite_sha256') != _sha(collector)
            or window.get('dispatch_sha256') !=
               _sha(controls / 'dispatch' / (dispatch_id + '.pre.json'))):
        _fail('native_origin_frozen_capture_changed')
    with closing(sqlite3.connect(collector.as_uri() + '?mode=ro', uri=True)) as db:
        receipts = db.execute('SELECT id,peer,payload FROM receipts ORDER BY id').fetchall()
    before_id = window.get('collector_max_id_before')
    close_path = controls / 'origin/window-close' / (dispatch_id + '.json')
    close = _read_json(close_path)
    after_id = close.get('collector_max_id_after')
    prefix = [row for row in receipts if type(before_id) is int and row[0] <= before_id]
    closed_rows = [row for row in receipts if type(after_id) is int and row[0] <= after_id]
    delta = [row for row in receipts if type(before_id) is int and type(after_id) is int
             and before_id < row[0] <= after_id]
    prefix_digest = hashlib.sha256(json.dumps(prefix, separators=(',', ':'),
                                              ensure_ascii=True).encode()).hexdigest()
    closed_digest = hashlib.sha256(json.dumps(closed_rows, separators=(',', ':'),
                                              ensure_ascii=True).encode()).hexdigest()
    if (type(before_id) is not int or before_id < 0
            or type(after_id) is not int or after_id < before_id
            or dispatch.get('origin_window_close_sha256') != _sha(close_path)
            or close.get('kind') != 'native-origin-window-close-v1'
            or close.get('dispatch_id') != dispatch_id or close.get('target') != target
            or close.get('window_sha256') != _sha(window_path)
            or close.get('collector_count_after') != len(closed_rows)
            or close.get('collector_prefix_sha256_after') != closed_digest
            or prefix_digest != window.get('collector_prefix_sha256')
            or len(prefix) != window.get('collector_count_before')
            or len(receipts) != frozen.get('receipt_count')
            or (receipts[-1][0] if receipts else 0) != frozen.get('last_receipt_id')
            or not 1 <= len(delta) <= 5000):
        _fail('native_origin_capture_window_ambiguous')
    app_ids = []
    for _, peer, payload in delta:
        try:
            item = json.loads(payload)
        except (UnicodeError, ValueError):
            _fail('native_origin_receipt_invalid')
        request_id = (item.get('request_id') if 't01_capture' in plan else
                      item.get('broker_request_id')) if isinstance(item, dict) else None
        broker_peer = (item.get('peer_ip') if 't01_capture' in plan else
                       item.get('broker_peer_ip')) if isinstance(item, dict) else None
        if (peer != topology.get('app_observer_ip') or broker_peer != '127.0.0.1'
                or not isinstance(request_id, str)
                or not re.fullmatch(r'[0-9a-f]{32}', request_id)):
            _fail('native_origin_receipt_binding_invalid')
        app_ids.append(request_id)
    if (len(app_ids) != len(set(app_ids)) or set(app_ids) != set(ledger_ids)
            or set(app_ids) != set(native_ids)):
        _fail('native_origin_request_ids_disagree')
    if 't01_capture' in plan:
        closed = _read_json(controls / 'observer' / target / ('closed-' + dispatch_id + '.json'))
        if (closed.get('window_sha256') != _sha(window_path)
                or set(closed.get('native_response_ids', [])) != set(native_ids)
                or set(closed.get('joined_request_ids', [])) != set(app_ids)):
            _fail('native_origin_t01_window_changed')
    return {'kind': 'native-origin-transport-proof-v1',
            'status': 'process_request_attributed',
            'dispatch_id': dispatch_id, 'role': role, 'target': target,
            'source_manifest_sha256': plan['source_manifest_sha256'],
            'target_image_id': plan['target_image_id'],
            'native_stop_sha256': _sha(revoked_path),
            'producer_manifest_sha256': _sha(manifest_path),
            'sidecar_stop_sha256': _sha(stop_path),
            'sidecar_cleanup_sha256': _sha(cleanup_path),
            'registration_sha256': _sha(registration_path),
            'ingress_ledger_sha256': stop['ledger_sha256'][role],
            'window_close_sha256': _sha(close_path),
            'frozen_capture_sha256': _sha(frozen_path),
            'native_trace_sha256': _sha(trace_path),
            'native_tool_claims': claims,
            'broker_request_ids': sorted(app_ids),
            'request_rows_sha256': hashlib.sha256(json.dumps(all_rows, sort_keys=True).encode()).hexdigest(),
            'semantic_verdict': 'unreviewed',
            'runtime_qualification': 'separate_review_required'}


def reconcile_origin_transport(run_root: Path, dispatch_id: str) -> dict:
    if not isinstance(dispatch_id, str) or not re.fullmatch(r'[0-9a-f]{32}', dispatch_id):
        return {'status': 'held', 'reason': 'dispatch_id_invalid', 'dispatch_id': dispatch_id}
    root = _private_root(Path(run_root))
    with _owner_lock(root):
        try:
            proof = _origin_transport_proof(root, dispatch_id)
            path = _controls(root) / 'origin/proofs' / (dispatch_id + '.json')
            if path.exists():
                if _read_json(path) != proof:
                    _fail('native_origin_existing_proof_changed')
            else:
                _write_json(path, proof, once=True)
            dispatch_path = _controls(root) / 'dispatch' / (dispatch_id + '.json')
            dispatch = _read_json(dispatch_path)
            if dispatch.get('origin_transport_proof_sha256') not in (None, _sha(path)):
                _fail('native_origin_dispatch_proof_changed')
            dispatch['origin_transport_proof_sha256'] = _sha(path)
            _write_json(dispatch_path, dispatch)
            return {'status': proof['status'], 'dispatch_id': dispatch_id,
                    'transport_proof_sha256': _sha(path),
                    'broker_request_count': len(proof['broker_request_ids']),
                    'semantic_verdict': proof['semantic_verdict'],
                    'runtime_qualification': proof['runtime_qualification']}
        except (NativeResearchError, OSError, ValueError, KeyError, TypeError, sqlite3.DatabaseError) as error:
            code = str(error) if isinstance(error, NativeResearchError) else 'native_origin_evidence_unavailable'
            return {'status': 'held', 'reason': code, 'dispatch_id': dispatch_id}


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
        if path.name.endswith(('.trace.json', '.pre.json', '.origin.json')):
            continue
        row = _read_json(path)
        item = {key: row.get(key) for key in
                ('dispatch_id', 'role', 'session_id', 'status', 'created_at')}
        origin_path = path.with_name(path.stem + '.origin.json')
        if origin_path.exists():
            item['origin_hold'] = _read_json(origin_path)
        dispatches.append(item)
    return {'status': 'active' if allowance and allowance['active'] else
            'stopped_complete' if final and final.get('status') == 'stopped_complete' else
            'recovered_exact_resources' if recovery and recovery.get('status') == 'recovered_exact_resources' else
            'prepared' if not activation and not final and not (controls / 'resources.json').exists()
            else 'inactive_or_unresolved',
            'run_root': str(root), 'model': plan['model'], 'limits': plan['limits'],
            'allowance': allowance, 'dispatches': dispatches, 'final': final, 'recovery': recovery,
            'protected_capture': 'unavailable',
            'provider_request_count': None, 'monetary_spend': None}


def _load_review_module(root: Path):
    path = _controls(root) / 'experiments/native-review-qualification/fresh_review.py'
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
    module = _load_review_module(root)
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
    prepare_cmd.add_argument('--kanboard-capture', action='store_true')
    prepare_cmd.add_argument('--t01-capture', action='store_true')
    prepare_cmd.add_argument('--origin-ingress', action='store_true',
                             help='opt-in source-built process-bound Unix ingress for capture')
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
    stage_cmd = commands.add_parser('capture-stage', help='provider-free Kanboard observer staging')
    stage_cmd.add_argument('--run-root', required=True)
    stage_cmd.add_argument('--target', choices=CAPTURE_TARGETS, required=True)
    for name in ('s', 'q', 't', 'b'):
        stage_cmd.add_argument('--' + name, type=int)
    for name in ('status', 'stop', 'recover-start'):
        item = commands.add_parser(name)
        item.add_argument('--run-root', required=True)
    reconcile_cmd = commands.add_parser('reconcile-role-grant', help='post-stop S10 uncertain-effect observation')
    reconcile_cmd.add_argument('--run-root', required=True)
    reconcile_cmd.add_argument('--dispatch-id', required=True)
    origin_cmd = commands.add_parser('reconcile-origin-transport',
                                     help='post-stop native process/request/app transport join')
    origin_cmd.add_argument('--run-root', required=True)
    origin_cmd.add_argument('--dispatch-id', required=True)
    research_cmd = commands.add_parser('research', help='one native turn in the original researcher')
    research_cmd.add_argument('--run-root', required=True)
    resume_cmd = commands.add_parser('resume', help='one native turn in the same persistent researcher store')
    resume_cmd.add_argument('--run-root', required=True)
    resume_cmd.add_argument('--prompt-file', required=True)
    resume_cmd.add_argument('--session', required=True)
    resume_cmd.add_argument('--observe-kanboard-role-grant', action='store_true')
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
        elif args.command == 'capture-stage':
            result = capture_stage(Path(args.run_root), args.target, s=args.s, q=args.q, t=args.t, b=args.b)
        elif args.command == 'start':
            result = start(Path(args.run_root), Path(args.approval))
        elif args.command == 'stop':
            result = stop(Path(args.run_root))
        elif args.command == 'recover-start':
            result = recover_start(Path(args.run_root))
        elif args.command == 'status':
            result = status(Path(args.run_root))
        elif args.command == 'reconcile-role-grant':
            result = reconcile_role_grant(Path(args.run_root), args.dispatch_id)
        elif args.command == 'reconcile-origin-transport':
            result = reconcile_origin_transport(Path(args.run_root), args.dispatch_id)
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
            result = invoke_native(root, role, session, prompt,
                                   kanboard_role_grant=(args.observe_kanboard_role_grant
                                                        if role == 'resume' else False))
        elif args.command == 'review':
            result = review(Path(args.run_root), Path(args.observer_root), Path(args.selection),
                            args.selection_sha256, args.role)
        else:
            _fail('command_invalid')
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0 if (result.get('status') not in ('unknown_effect', 'hold_unknown', 'unfinished', 'start_incomplete',
                                                'unsafe_or_unresolved', 'stopped_evidence_incomplete')
                     and result.get('independent_host_check') != 'unavailable') else 2
    except KeyboardInterrupt:
        print(json.dumps({'status': 'interrupted', 'run_root': getattr(args, 'run_root', None)},
                         sort_keys=True))
        return 130
    except Exception as error:
        code = str(error)
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,100}', code):
            code = 'native_research_unavailable'
        terminal = 'rejected'
        if args.command == 'start':
            try:
                final = _read_json(Path(args.run_root) / 'controls/final.json')
                if final.get('status') == 'unsafe_or_unresolved':
                    terminal = 'unsafe_or_unresolved'
            except Exception:
                pass
        print(json.dumps({'status': terminal, 'code': code}, sort_keys=True))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
