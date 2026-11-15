#!/usr/bin/env python3
"""Validate v2 engagement authority and safe bytes without starting any work."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import errno
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import stat
from urllib.parse import urlsplit

from engagement_records import RecordError, detect_secret_classes
from operator_signature import verify_operator_signature_bytes

INPUT_KIND = 'native-engagement-inputs-v2'
SCOPE_KIND = 'native-engagement-scope-v2'
SIGNATURE_NAMESPACE = 'llm-redteam-harness-native-engagement-v2'
CODEX_TOOL_POLICY = 'docker-confined-v1'
MAX_PUBLICATION_BYTES = 16 * 1024 * 1024
MAX_SOURCE_BYTES = 8 * 1024 * 1024 * 1024
MAX_SOURCE_FILES = 200000
ID = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}\Z')
DIGEST = re.compile(r'sha256:[0-9a-f]{64}\Z')
RUNTIME_CAPABILITIES = {'startup', 'fresh_session', 'resume', 'steer', 'interrupt',
                        'usage_tokens', 'usage_cost_estimate', 'native_tools', 'child_inventory'}
ENVIRONMENT_CAPABILITIES = {'source', 'binary', 'application', 'acquisition',
                            'network_proxy', 'shared_write', 'renewable_lease'}
RUNGS = ('source_only', 'self', 'stored', 'cross_user')
SENSITIVE_TEXT = re.compile(
    rb'(?i)(?:\b(?:authorization|proxy-authorization|cookie|set-cookie|x-api-key)["\']?\s*[:=]|'
    rb'\b(?:password|passwd|api[_-]?key|access[_-]?token|secret)["\']?\s*[:=]\s*\S+|'
    rb'\b(?:bearer|basic)\s+[A-Za-z0-9+/._=-]{8,}|'
    rb'\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b|'
    rb'[?&](?:x-amz-signature|x-goog-signature|signature|sig)=|'
    rb'-----BEGIN [A-Z ]*PRIVATE KEY-----)')


class ContractError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class VerifiedInputs:
    scope: dict
    inputs: dict
    goal_bytes: bytes
    runtime_profiles: dict[str, dict]
    environment_profiles: dict[str, dict]
    frozen_files: dict[str, bytes]
    signer_fingerprint: str


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ContractError(code)


def _json_value(value, depth: int = 0) -> None:
    _require(depth <= 64, 'json_depth')
    if type(value) is str:
        try:
            value.encode('utf-8')
        except UnicodeError:
            raise ContractError('json_invalid') from None
        return
    if value is None or type(value) is bool:
        return
    if type(value) is int:
        _require(-(2 ** 63) <= value < 2 ** 63, 'json_number_invalid')
    elif type(value) is float:
        _require(math.isfinite(value), 'json_nonfinite')
    elif type(value) is list:
        _require(len(value) <= 200000, 'json_collection_oversize')
        for item in value:
            _json_value(item, depth + 1)
    elif type(value) is dict:
        _require(len(value) <= 200000 and all(type(key) is str for key in value), 'json_invalid')
        for item in value.values():
            _json_value(item, depth + 1)
    else:
        raise ContractError('json_invalid')


def canonical(value) -> bytes:
    _json_value(value)
    try:
        data = (json.dumps(value, sort_keys=True, separators=(',', ':'),
                           ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')
    except (ValueError, UnicodeError):
        raise ContractError('json_invalid') from None
    _require(len(data) <= MAX_PUBLICATION_BYTES, 'json_oversize')
    return data


def digest(data: bytes) -> str:
    _require(type(data) is bytes, 'bytes_required')
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def _pairs(items):
    value = {}
    for key, item in items:
        _require(key not in value, 'duplicate_json_key')
        value[key] = item
    return value


def _nonfinite(_value):
    raise ContractError('json_nonfinite')


def _decode(data: bytes):
    try:
        value = json.loads(data.decode('utf-8'), object_pairs_hook=_pairs, parse_constant=_nonfinite)
    except (ValueError, UnicodeError, RecursionError) as error:
        if isinstance(error, ContractError):
            raise
        raise ContractError('json_invalid') from None
    _json_value(value)
    return value


def _path(value) -> Path:
    _require(isinstance(value, (str, Path)), 'path_invalid')
    text = str(value)
    _require(bool(text) and not text.startswith('//') and '\x00' not in text
             and not any(ord(c) < 32 for c in text), 'path_invalid')
    path = Path(text)
    _require(path.is_absolute() and str(path) == text and '..' not in path.parts,
             'path_invalid')
    return path


def _stamp(entry):
    return (entry.st_dev, entry.st_ino, entry.st_mode, entry.st_uid, entry.st_gid,
            entry.st_size, entry.st_mtime_ns, entry.st_ctime_ns, entry.st_nlink)


@contextmanager
def _bound_open(path: Path, *, directory: bool = False, private: bool = False):
    path = _path(path)
    descriptors = []
    links = []
    try:
        current = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        descriptors.append(current)
        for index, name in enumerate(path.parts[1:]):
            last = index == len(path.parts) - 2
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
            if not last or directory:
                flags |= os.O_DIRECTORY
            child = os.open(name, flags, dir_fd=current)
            entry = os.fstat(child)
            links.append((current, name, child))
            descriptors.append(child)
            current = child
        entry = os.fstat(current)
        _require(stat.S_ISDIR(entry.st_mode) if directory else stat.S_ISREG(entry.st_mode),
                 'source_invalid' if directory else 'file_not_regular')
        if private:
            _require(entry.st_uid == os.getuid() and not entry.st_mode & 0o077
                     and (directory or entry.st_nlink == 1), 'file_not_private')
        yield current, entry
        for parent, name, child in links:
            live = os.stat(name, dir_fd=parent, follow_symlinks=False)
            opened = os.fstat(child)
            _require((live.st_dev, live.st_ino, live.st_mode) ==
                     (opened.st_dev, opened.st_ino, opened.st_mode), 'file_changed')
    except OSError as error:
        code = 'path_invalid' if error.errno in (errno.ELOOP, errno.ENOTDIR) else 'file_unavailable'
        raise ContractError(code) from None
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _read_fd(fd: int, entry, max_bytes: int, *, hash_only: bool = False):
    _require(type(max_bytes) is int and max_bytes >= 0, 'read_limit_invalid')
    _require(stat.S_ISREG(entry.st_mode), 'file_not_regular')
    _require(entry.st_size <= max_bytes, 'file_oversize')
    parts = []
    hasher = hashlib.sha256()
    size = 0
    while chunk := os.read(fd, min(1024 * 1024, max_bytes - size + 1)):
        size += len(chunk)
        _require(size <= max_bytes, 'file_oversize')
        if hash_only:
            hasher.update(chunk)
        else:
            parts.append(chunk)
    _require(size == entry.st_size and _stamp(entry) == _stamp(os.fstat(fd)), 'file_changed')
    return 'sha256:' + hasher.hexdigest() if hash_only else b''.join(parts)


def read_bytes(path: Path, *, private: bool = False, max_bytes: int = 1024 * 1024) -> bytes:
    with _bound_open(path, private=private) as (fd, entry):
        return _read_fd(fd, entry, max_bytes)


def read_json(path: Path, *, private: bool = False, max_bytes: int = 1024 * 1024):
    return _decode(read_bytes(path, private=private, max_bytes=max_bytes))


def safe_publication(data: bytes, *, known_secrets: tuple[bytes, ...] = ()) -> bytes:
    _require(type(data) is bytes and len(data) <= MAX_PUBLICATION_BYTES, 'publication_invalid')
    _require(all(type(value) is bytes and value for value in known_secrets), 'known_secrets_invalid')
    views = [data]
    for marks, encoding in (((b'\xff\xfe\x00\x00', b'\x00\x00\xfe\xff'), 'utf-32'),
                            ((b'\xff\xfe', b'\xfe\xff'), 'utf-16')):
        if data.startswith(marks):
            try:
                views.append(data.decode(encoding).encode('utf-8'))
            except UnicodeError:
                raise ContractError('publication_invalid') from None
            break
    sensitive_views = []
    for view in tuple(views):
        try:
            value = _decode(view)
        except ContractError:
            sensitive_views.append(view)
            continue
        views.append(canonical(value))
        pending = [value]
        while pending:
            item = pending.pop()
            if type(item) is str:
                views.append(item.encode('utf-8'))
                sensitive_views.append(item.encode('utf-8'))
            elif type(item) is list:
                pending.extend(item)
            elif type(item) is dict:
                pending.extend(item.values())
                # OMP's exact public environment reference is not a credential value.
                if item.get('apiKey') == 'OPENAI_API_KEY':
                    del item['apiKey']
        sensitive_views.append(canonical(value))
    for view in views:
        _require(not detect_secret_classes(view)
                 and not any(value in view for value in known_secrets), 'publication_secret')
    _require(not any(SENSITIVE_TEXT.search(view) for view in sensitive_views), 'publication_secret')
    return data


def source_manifest(root: Path) -> dict[str, dict]:
    manifest = {}
    observed = {}
    total = 0

    def walk(fd, prefix, *, verify=False):
        nonlocal total
        before = os.fstat(fd)
        relative_root = '/'.join(prefix)
        if verify:
            _require(observed.get(relative_root) == _stamp(before), 'file_changed')
        else:
            observed[relative_root] = _stamp(before)
        names = sorted(os.listdir(fd))
        for name in names:
            _require(name not in ('.', '..') and not any(ord(c) < 32 for c in name), 'source_invalid')
            child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                            dir_fd=fd)
            try:
                entry = os.fstat(child)
                relative = '/'.join((*prefix, name))
                if stat.S_ISDIR(entry.st_mode):
                    walk(child, (*prefix, name), verify=verify)
                else:
                    _require(stat.S_ISREG(entry.st_mode), 'source_invalid')
                    if verify:
                        _require(observed.get(relative) == _stamp(entry), 'file_changed')
                    else:
                        _require(len(manifest) < MAX_SOURCE_FILES, 'source_limits')
                        total += entry.st_size
                        _require(total <= MAX_SOURCE_BYTES, 'source_limits')
                        manifest[relative] = {'sha256': _read_fd(child, entry, MAX_SOURCE_BYTES,
                                                                hash_only=True),
                                              'mode': stat.S_IMODE(entry.st_mode), 'size': entry.st_size}
                        observed[relative] = _stamp(entry)
                live = os.stat(name, dir_fd=fd, follow_symlinks=False)
                _require(_stamp(live) == _stamp(os.fstat(child)), 'file_changed')
            finally:
                os.close(child)
        _require(names == sorted(os.listdir(fd)) and _stamp(before) == _stamp(os.fstat(fd)),
                 'file_changed')

    with _bound_open(root, directory=True) as (fd, _entry):
        walk(fd, ())
        walk(fd, (), verify=True)
    _require(bool(manifest), 'source_empty')
    safe_publication(canonical(manifest))
    return manifest


def _object(value, keys, code):
    _require(type(value) is dict and set(value) == set(keys), code)
    return value


def _text(value, code, *, limit=2048):
    _require(type(value) is str and 0 < len(value.encode('utf-8')) <= limit
             and not any(ord(c) < 32 and c not in '\n\t' for c in value), code)
    safe_publication(value.encode())
    return value


def _identifier(value, code):
    _require(type(value) is str and ID.fullmatch(value) is not None, code)
    return value


def _digest(value, code):
    _require(type(value) is str and DIGEST.fullmatch(value) is not None, code)
    return value


def _integer(value, code, *, minimum=1, maximum=2 ** 63 - 1):
    _require(type(value) is int and minimum <= value <= maximum, code)
    return value


def _strings(value, code, *, allowed=None, minimum=0, maximum=256):
    _require(type(value) is list and minimum <= len(value) <= maximum
             and all(type(item) is str for item in value)
             and len(value) == len(set(value)), code)
    for item in value:
        _identifier(item, code)
    if allowed is not None:
        _require(set(value) <= set(allowed), code)
    return value


def _host(value, code):
    _text(value, code, limit=253)
    try:
        normalized = str(ipaddress.ip_address(value))
    except ValueError:
        _require(all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', part)
                     for part in value.split('.')), code)
        normalized = value.lower()
    _require(value == normalized, code)
    return value


def _url(value, code):
    _text(value, code)
    try:
        url = urlsplit(value)
        _require(url.scheme in ('http', 'https') and url.hostname is not None
                 and url.username is None and url.password is None
                 and not url.query and not url.fragment, code)
        _host(url.hostname, code)
        port = url.port or (443 if url.scheme == 'https' else 80)
        _integer(port, code, maximum=65535)
        host = '[' + url.hostname + ']' if ':' in url.hostname else url.hostname
        _require(url.netloc in (host, host + ':' + str(port)), code)
        return url.scheme, url.hostname, port
    except ValueError as error:
        if isinstance(error, ContractError):
            raise
        raise ContractError(code) from None


def validate_runtime_profile(profile: dict) -> dict:
    code = 'runtime_profile_invalid'
    _require(type(profile) is dict, code)
    optional = tuple(name for name in ('model_host', 'model_catalog') if name in profile)
    _object(profile, ('kind', 'version', 'executable', 'protocol', 'config_file',
                      'config_sha256', 'provider', 'model', 'credential_ref',
                      'required_capabilities', 'tool_bundle', *optional), code)
    _require(profile['kind'] in ('codex', 'omp'), code)
    for key in ('version', 'provider', 'model'):
        _text(profile[key], code, limit=256)
    executable = _object(profile['executable'], ('path', 'sha256'), code)
    _path(executable['path'])
    _digest(executable['sha256'], code)
    protocol = _object(profile['protocol'], ('mode', 'schema_file', 'schema_sha256'), code)
    _require(protocol['mode'] == ('stdio-jsonrpc' if profile['kind'] == 'codex' else 'stdio-jsonl'), code)
    _path(protocol['schema_file'])
    _digest(protocol['schema_sha256'], code)
    _path(profile['config_file'])
    _digest(profile['config_sha256'], code)
    if profile['credential_ref'] is not None:
        _identifier(profile['credential_ref'], code)
    _strings(profile['required_capabilities'], code, allowed=RUNTIME_CAPABILITIES)
    extra = ('bun_version',) if profile['kind'] == 'omp' else ()
    bundle = _object(profile['tool_bundle'], ('path', 'manifest_sha256', 'platform', *extra), code)
    _path(bundle['path'])
    _digest(bundle['manifest_sha256'], code)
    _require(bundle['platform'] in ('linux/arm64', 'linux/amd64'), code)
    if profile['kind'] == 'omp':
        _require(type(bundle['bun_version']) is str and
                 re.fullmatch(r'(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)',
                              bundle['bun_version']) is not None, code)
    if 'model_host' in profile:
        validate_model_host(profile['model_host'])
    if 'model_catalog' in profile:
        _require(profile['kind'] == 'omp', code)
        catalog = _object(profile['model_catalog'], ('path', 'sha256'), code)
        _path(catalog['path'])
        _digest(catalog['sha256'], code)
    safe_publication(canonical(profile))
    return profile


def validate_model_host(host: dict) -> dict:
    code = 'runtime_model_host_invalid'
    _object(host, ('kind', 'docker_binary', 'docker_endpoint', 'daemon_id', 'image_id',
                   'platform', 'uid', 'gid', 'limits'), code)
    _require(host['kind'] == 'linux-docker-model-v1' and
             host['platform'] in ('linux/amd64', 'linux/arm64'), code)
    _path(host['docker_binary'])
    _require(type(host['docker_endpoint']) is str and host['docker_endpoint'].startswith('unix:///'), code)
    _path(host['docker_endpoint'][7:])
    _text(host['daemon_id'], code, limit=256)
    _digest(host['image_id'], code)
    for name in ('uid', 'gid'):
        _integer(host[name], code, maximum=2 ** 32 - 1)
    limits = _object(host['limits'], ('memory_bytes', 'cpu_count', 'pids', 'workspace_bytes'), code)
    for name in ('memory_bytes', 'pids', 'workspace_bytes'):
        _integer(limits[name], code)
    _require(type(limits['cpu_count']) in (int, float) and math.isfinite(limits['cpu_count'])
             and limits['cpu_count'] > 0, code)
    safe_publication(canonical(host))
    return host


def validate_environment_profile(profile: dict) -> dict:
    code = 'environment_profile_invalid'
    _object(profile, ('kind', 'transport', 'docker_binary', 'docker_endpoint', 'daemon_id',
                      'image_id', 'platform', 'uid', 'gid', 'ssh',
                      *(('codex_tool_policy',) if isinstance(profile, dict) and 'codex_tool_policy' in profile else ())), code)
    if 'codex_tool_policy' in profile:
        _require(profile['codex_tool_policy'] == CODEX_TOOL_POLICY, code)
    _require(profile['kind'] == 'research-environment-profile-v2'
             and profile['transport'] in ('docker', 'ssh-docker')
             and profile['platform'] in ('linux/arm64', 'linux/amd64'), code)
    _path(profile['docker_binary'])
    endpoint = profile['docker_endpoint']
    _require(type(endpoint) is str and endpoint.startswith('unix:///'), code)
    _path(endpoint[7:])
    if profile['daemon_id'] is not None:
        _text(profile['daemon_id'], code, limit=256)
    _digest(profile['image_id'], code)
    _integer(profile['uid'], code, maximum=2 ** 32 - 1)
    _integer(profile['gid'], code, minimum=0, maximum=2 ** 32 - 1)
    ssh = profile['ssh']
    if profile['transport'] == 'docker':
        _require(ssh is None, code)
    else:
        _object(ssh, ('host', 'port', 'user', 'known_hosts_file', 'known_hosts_sha256',
                      'identity_file', 'python_binary'), code)
        _host(ssh['host'], code)
        _integer(ssh['port'], code, maximum=65535)
        _require(type(ssh['user']) is str and
                 re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]{0,63}', ssh['user']) is not None, code)
        for key in ('known_hosts_file', 'identity_file', 'python_binary'):
            _path(ssh[key])
        _digest(ssh['known_hosts_sha256'], code)
    safe_publication(canonical(profile))
    return profile


def _scope(scope: dict, now: datetime, allow_expired: bool) -> None:
    _object(scope, ('kind', 'engagement_id', 'operator_id', 'issued_at', 'expires_at',
                    'goal_sha256', 'goal_mode', 'patch_required', 'access', 'environments',
                    'network', 'effects', 'escalation_ceiling', 'benign_objectives',
                    'runtime_assignments', 'limits', 'revocation',
                    *(('application_states',) if isinstance(scope, dict) and 'application_states' in scope else ()),
                    *(('authority_policy',) if isinstance(scope, dict) and 'authority_policy' in scope else ())), 'scope_invalid')
    _require(scope['kind'] == SCOPE_KIND, 'scope_kind_invalid')
    _require('authority_policy' not in scope or scope['authority_policy'] == 'initial-scope-v1',
             'scope_authority_policy_invalid')
    _identifier(scope['engagement_id'], 'scope_invalid')
    _require(type(scope['operator_id']) is str and re.fullmatch(
        r'[A-Za-z0-9_.@+-]{1,128}', scope['operator_id']) is not None, 'scope_invalid')
    _digest(scope['goal_sha256'], 'scope_invalid')
    _require(scope['goal_mode'] in ('bounded', 'broad') and type(scope['patch_required']) is bool
             and scope['escalation_ceiling'] in RUNGS, 'scope_invalid')
    times = []
    for key in ('issued_at', 'expires_at'):
        value = scope[key]
        if value is None and key == 'expires_at':
            times.append(None)
            continue
        _require(type(value) is str and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ', value),
                 'scope_time_invalid')
        try:
            times.append(datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc))
        except ValueError:
            raise ContractError('scope_time_invalid') from None
    issued, expires = times
    _require(expires is None or issued < expires, 'scope_time_invalid')
    _require(issued <= now, 'scope_not_yet_valid')
    _require(allow_expired or expires is None or now < expires, 'scope_expired')
    _require(type(scope['benign_objectives']) is list and 1 <= len(scope['benign_objectives']) <= 64,
             'scope_invalid')
    for objective in scope['benign_objectives']:
        _text(objective, 'scope_invalid')
    _object(scope['revocation'], ('operator_stop', 'disconnected_worker'), 'scope_invalid')
    _require(scope['revocation'] == {'operator_stop': True, 'disconnected_worker': 'lease_expiry'}
             and type(scope['revocation']['operator_stop']) is bool, 'scope_invalid')
    limits = _object(scope['limits'], ('hard', 'max_workers', 'max_worker_lease_seconds',
                                      'informational'), 'scope_limits_invalid')
    _require(type(limits['hard']) is dict, 'scope_limits_invalid')
    _require(not set(limits['hard']) - {'invocations', 'worker_seconds'}, 'hard_limit_unsupported')
    _require(set(limits['hard']) == {'invocations', 'worker_seconds'}, 'scope_limits_invalid')
    for value in (*limits['hard'].values(), limits['max_workers'], limits['max_worker_lease_seconds']):
        _integer(value, 'scope_limits_invalid')
    _require(type(limits['informational']) is dict and set(limits['informational']) <= {
        'input_tokens', 'output_tokens', 'cached_input_tokens', 'cache_write_tokens',
        'reasoning_tokens', 'provider_requests', 'estimated_cost_usd'}, 'scope_limits_invalid')
    for value in limits['informational'].values():
        _require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
                 'scope_limits_invalid')
    _require(type(scope['access']) is list and 1 <= len(scope['access']) <= 256, 'scope_access_invalid')
    accesses = {}
    for access in scope['access']:
        code = 'scope_access_invalid'
        _object(access, ('id', 'kind', 'identity', 'account_refs', 'permissions'), code)
        identity = _identifier(access['id'], code)
        _require(identity not in accesses, code)
        accesses[identity] = access
        _strings(access['account_refs'], code)
        _strings(access['permissions'], code, allowed=('read', 'execute', 'write', 'reset'), minimum=1)
        if access['kind'] == 'source':
            _object(access['identity'], ('manifest_sha256',), code)
            _digest(access['identity']['manifest_sha256'], code)
        elif access['kind'] == 'binary':
            _object(access['identity'], ('sha256', 'platform'), code)
            _digest(access['identity']['sha256'], code)
            _require(access['identity']['platform'] in ('linux/amd64', 'linux/arm64'), code)
        elif access['kind'] == 'application':
            _object(access['identity'], ('base_url', 'version'), code)
            _url(access['identity']['base_url'], code)
            if access['identity']['version'] is not None:
                _text(access['identity']['version'], code)
        else:
            raise ContractError(code)
    _require(type(scope['environments']) is list and 1 <= len(scope['environments']) <= 64,
             'scope_environment_invalid')
    environments = {}
    for environment in scope['environments']:
        code = 'scope_environment_invalid'
        _object(environment, ('profile_id', 'profile_sha256', 'capabilities', 'limits', 'cleanup'), code)
        identity = _identifier(environment['profile_id'], code)
        _require(identity not in environments, code)
        environments[identity] = environment
        _digest(environment['profile_sha256'], code)
        _strings(environment['capabilities'], code, allowed=ENVIRONMENT_CAPABILITIES, minimum=1)
        limits = _object(environment['limits'], ('memory_bytes', 'cpu_count', 'pids',
                                                'workspace_bytes', 'lease_seconds', 'output_bytes'), code)
        for key, value in limits.items():
            if key == 'cpu_count':
                _require(type(value) in (int, float) and math.isfinite(value) and value > 0, code)
            else:
                _integer(value, code)
        _require(limits['lease_seconds'] <= scope['limits']['max_worker_lease_seconds'], code)
        cleanup = _object(environment['cleanup'], ('owned_resources', 'owned_workspace'), code)
        _require(all(value is True for value in cleanup.values()), code)
    _object(scope['network'], ('provider', 'acquisition', 'target'), 'scope_network_invalid')
    target_routes = set()
    for kind, routes in scope['network'].items():
        code = 'scope_network_invalid'
        _require(type(routes) is list and len(routes) <= 256, code)
        seen = set()
        for route in routes:
            _object(route, ('protocol', 'host', 'port', 'address_policy'), code)
            _require(route['protocol'] in ('http', 'https'), code)
            _host(route['host'], code)
            _integer(route['port'], code, maximum=65535)
            identity = (route['protocol'], route['host'], route['port'])
            _require(identity not in seen, code)
            seen.add(identity)
            policy = _object(route['address_policy'], ('public_only', 'cidrs'), code)
            _require(type(policy['public_only']) is bool and type(policy['cidrs']) is list
                     and len(policy['cidrs']) <= 256 and all(type(cidr) is str for cidr in policy['cidrs'])
                     and len(set(policy['cidrs'])) == len(policy['cidrs']), code)
            _require((policy['public_only'] and not policy['cidrs'])
                     or (not policy['public_only'] and bool(policy['cidrs'])), code)
            for cidr in policy['cidrs']:
                try:
                    _require(str(ipaddress.ip_network(cidr, strict=True)) == cidr, code)
                except ValueError as error:
                    if isinstance(error, ContractError):
                        raise
                    raise ContractError(code) from None
            if kind == 'target':
                target_routes.add(identity)
    for access in accesses.values():
        if access['kind'] == 'application':
            _require(_url(access['identity']['base_url'], 'scope_access_invalid') in target_routes,
                     'scope_network_invalid')
    _require(type(scope['effects']) is list and 1 <= len(scope['effects']) <= 256, 'scope_effect_invalid')
    effect_ids = set()
    for effect in scope['effects']:
        code = 'scope_effect_invalid'
        _object(effect, ('id', 'kind', 'access_ids', 'environment_ids', 'account_refs',
                         'rung', 'artifact_classes', 'cleanup_required'), code)
        identity = _identifier(effect['id'], code)
        _require(identity not in effect_ids, code)
        effect_ids.add(identity)
        _require(effect['kind'] in ('read', 'execute', 'write', 'reset', 'artifact_create')
                 and effect['rung'] in RUNGS and
                 RUNGS.index(effect['rung']) <= RUNGS.index(scope['escalation_ceiling']), code)
        _strings(effect['access_ids'], code, allowed=accesses, minimum=1)
        _strings(effect['environment_ids'], code, allowed=environments, minimum=1)
        _strings(effect['account_refs'], code)
        _strings(effect['artifact_classes'], code)
        _require(type(effect['cleanup_required']) is bool, code)
        if effect['kind'] in ('write', 'reset', 'artifact_create'):
            _require(effect['cleanup_required'], code)
        if effect['kind'] == 'artifact_create':
            _require(bool(effect['artifact_classes']), code)
            if 'owned-lab-state-v2' in effect['artifact_classes']:
                _require(scope.get('authority_policy') == 'initial-scope-v1', 'scope_authority_policy_required')
        permission = 'write' if effect['kind'] == 'artifact_create' else effect['kind']
        for access_id in effect['access_ids']:
            access = accesses[access_id]
            _require(permission in access['permissions'] and
                     set(effect['account_refs']) <= set(access['account_refs']), code)
            for environment_id in effect['environment_ids']:
                _require(access['kind'] in environments[environment_id]['capabilities'], code)
    references = scope.get('application_states', [])
    _require(type(references) is list and len(references) <= len(accesses), 'scope_application_state_invalid')
    state_accesses = set()
    for reference in references:
        code = 'scope_application_state_invalid'
        _object(reference, ('access_id', 'profile_sha256', 'environment_id', 'reset_effect_id',
            *(('artifact_effect_id',) if isinstance(reference, dict) and 'artifact_effect_id' in reference else ())), code)
        _require(scope.get('authority_policy') != 'initial-scope-v1' or 'artifact_effect_id' in reference, code)
        for key in ('access_id', 'environment_id', 'reset_effect_id'):
            _identifier(reference[key], code)
        access = accesses.get(reference['access_id'])
        effect = next((row for row in scope['effects'] if row['id'] == reference['reset_effect_id']), None)
        _require(access is not None and access['kind'] == 'application' and 'reset' in access['permissions']
                 and access['id'] not in state_accesses and reference['environment_id'] in environments, code)
        _digest(reference['profile_sha256'], code)
        _require(effect is not None and effect['kind'] == 'reset' and effect['access_ids'] == [access['id']]
                 and effect['environment_ids'] == [reference['environment_id']] and not effect['account_refs']
                 and not effect['artifact_classes'] and effect['cleanup_required'], code)
        if 'artifact_effect_id' in reference:
            _identifier(reference['artifact_effect_id'], code)
            artifact = next((row for row in scope['effects'] if row['id'] == reference['artifact_effect_id']), None)
            _require(artifact is not None and artifact['kind'] == 'artifact_create' and
                artifact['access_ids'] == [access['id']] and artifact['environment_ids'] == [reference['environment_id']] and
                artifact['artifact_classes'] == ['owned-application-state-v1'] and not artifact['account_refs'] and
                artifact['cleanup_required'] and artifact['rung'] in ('source_only', 'self'), code)
        origin = _url(access['identity']['base_url'], code)
        _require(sum(other['kind'] == 'application' and _url(other['identity']['base_url'], code) == origin
                     for other in accesses.values()) == 1, code)
        state_accesses.add(access['id'])
    _require(all(effect['kind'] != 'reset' or any(row['reset_effect_id'] == effect['id'] for row in references)
                 for effect in scope['effects']), 'scope_application_state_invalid')
    _require(type(scope['runtime_assignments']) is list and 1 <= len(scope['runtime_assignments']) <= 64,
             'scope_runtime_invalid')
    runtime_ids = set()
    for assignment in scope['runtime_assignments']:
        code = 'scope_runtime_invalid'
        _object(assignment, ('profile_id', 'profile_sha256', 'roles'), code)
        identity = _identifier(assignment['profile_id'], code)
        _require(identity not in runtime_ids, code)
        runtime_ids.add(identity)
        _digest(assignment['profile_sha256'], code)
        _strings(assignment['roles'], code, allowed=('lead', 'specialist', 'reviewer'), minimum=1)
    _require(any('lead' in item['roles'] for item in scope['runtime_assignments']), 'scope_runtime_invalid')


def _pinned_file(path, expected, *, private=False, max_bytes=MAX_PUBLICATION_BYTES):
    data = read_bytes(_path(path), private=private, max_bytes=max_bytes)
    _require(digest(data) == expected, 'digest_mismatch')
    return data


def _pinned_digest(path, expected):
    with _bound_open(_path(path)) as (fd, entry):
        _require(_read_fd(fd, entry, MAX_SOURCE_BYTES, hash_only=True) == expected, 'digest_mismatch')


def load_inputs(path: Path, *, now: datetime | None = None,
                allow_expired: bool = False) -> VerifiedInputs:
    now = now or datetime.now(timezone.utc)
    _require(isinstance(now, datetime) and now.tzinfo is not None, 'clock_invalid')
    _require(type(allow_expired) is bool, 'clock_invalid')
    raw_inputs = read_bytes(path, private=True)
    inputs = _decode(raw_inputs)
    _object(inputs, ('kind', 'scope_file', 'scope_signature', 'allowed_signers',
                     'trusted_fingerprint', 'goal_file', 'access_files',
                     'runtime_profiles', 'environment_profiles',
                     *(('application_profiles',) if isinstance(inputs, dict) and 'application_profiles' in inputs else ())), 'inputs_invalid')
    _require(inputs['kind'] == INPUT_KIND, 'inputs_kind_invalid')
    _digest(inputs['trusted_fingerprint'], 'inputs_invalid')
    for key in ('scope_file', 'scope_signature', 'allowed_signers', 'goal_file'):
        _path(inputs[key])
    for key in ('access_files', 'runtime_profiles', 'environment_profiles',
                *(('application_profiles',) if 'application_profiles' in inputs else ())):
        _require(type(inputs[key]) is dict and len(inputs[key]) <= 256, 'inputs_invalid')
        for identity, filename in inputs[key].items():
            _identifier(identity, 'inputs_invalid')
            _path(filename)
    scope_bytes = read_bytes(Path(inputs['scope_file']), private=True, max_bytes=256 * 1024)
    safe_publication(scope_bytes)
    try:
        scope_text = scope_bytes.decode('utf-8')
    except UnicodeError:
        raise ContractError('scope_invalid') from None
    sections = re.findall(r'^```native-engagement-scope-v2\s*\n(.*?)^```\s*$',
                          scope_text, re.M | re.S)
    fences = re.findall(r'^```native-[a-z-]+-v\d+\b', scope_text, re.M)
    _require(len(sections) == 1 and fences == ['```native-engagement-scope-v2'], 'scope_invalid')
    scope = _decode(sections[0].encode())
    _scope(scope, now, allow_expired)
    signature = read_bytes(Path(inputs['scope_signature']), private=True, max_bytes=256 * 1024)
    signers = read_bytes(Path(inputs['allowed_signers']), private=True)
    try:
        fingerprint = verify_operator_signature_bytes(
            scope_bytes=scope_bytes, operator_id=scope['operator_id'],
            challenge_bytes=canonical({'kind': 'native-engagement-scope-challenge-v2',
                                       'engagement_id': scope['engagement_id'],
                                       'scope_sha256': digest(scope_bytes)}),
            signature_bytes=signature, allowed_signers_bytes=signers,
            namespace=SIGNATURE_NAMESPACE)
    except (RecordError, OSError):
        raise ContractError('scope_signature_invalid') from None
    _require(fingerprint == inputs['trusted_fingerprint'], 'scope_signer_untrusted')
    goal = _pinned_file(inputs['goal_file'], scope['goal_sha256'], private=True, max_bytes=1024 * 1024)
    _require(bool(goal.strip()), 'goal_invalid')
    frozen = {'inputs.json': raw_inputs, 'scope.md': scope_bytes, 'scope.sig': signature,
              'allowed_signers': signers, 'goal.md': goal}
    runtime_profiles = {}
    _require(set(inputs['runtime_profiles']) == {row['profile_id'] for row in scope['runtime_assignments']},
             'inputs_profile_mismatch')
    for assignment in scope['runtime_assignments']:
        identity = assignment['profile_id']
        raw = _pinned_file(inputs['runtime_profiles'][identity], assignment['profile_sha256'], private=True)
        profile = validate_runtime_profile(_decode(raw))
        _pinned_digest(profile['executable']['path'], profile['executable']['sha256'])
        config = _pinned_file(profile['config_file'], profile['config_sha256'], private=True)
        schema = _pinned_file(profile['protocol']['schema_file'], profile['protocol']['schema_sha256'])
        frozen.update({f'runtimes/{identity}.json': raw, f'runtimes/{identity}.config': config,
                       f'runtimes/{identity}.schema': schema})
        if 'model_catalog' in profile:
            catalog = profile['model_catalog']
            frozen[f'runtimes/{identity}.models.yml'] = _pinned_file(catalog['path'], catalog['sha256'], private=True)
        bundle = profile['tool_bundle']
        manifest = canonical(source_manifest(Path(bundle['path'])))
        _require(digest(manifest) == bundle['manifest_sha256'], 'digest_mismatch')
        frozen[f'runtimes/{identity}.bundle-manifest.json'] = manifest
        runtime_profiles[identity] = profile
    environment_profiles = {}
    _require(set(inputs['environment_profiles']) == {row['profile_id'] for row in scope['environments']},
             'inputs_profile_mismatch')
    for reference in scope['environments']:
        identity = reference['profile_id']
        raw = _pinned_file(inputs['environment_profiles'][identity], reference['profile_sha256'], private=True)
        profile = validate_environment_profile(_decode(raw))
        frozen[f'environments/{identity}.json'] = raw
        if profile['ssh'] is not None:
            ssh = profile['ssh']
            known_hosts = _pinned_file(ssh['known_hosts_file'], ssh['known_hosts_sha256'])
            frozen[f'environments/{identity}.known_hosts'] = known_hosts
        environment_profiles[identity] = profile
    references = scope.get('application_states', [])
    _require(set(inputs.get('application_profiles', {})) == {row['access_id'] for row in references},
             'inputs_profile_mismatch')
    for reference in references:
        from application_state import validate_profile, owned_origin, ApplicationStateError
        identity = reference['access_id']
        raw = _pinned_file(inputs['application_profiles'][identity], reference['profile_sha256'], private=True)
        try:
            profile = validate_profile(_decode(raw))
            owned_origin(next(row for row in scope['access'] if row['id'] == identity), profile)
            if 'state_volumes' in profile:
                from application_volumes import validate
                from research_environment import EnvironmentUnavailable
                environment = next(row for row in scope['environments'] if row['profile_id'] == reference['environment_id'])
                try:
                    validate(profile['state_volumes'], environment['limits'])
                except EnvironmentUnavailable:
                    raise ApplicationStateError('application_state_volumes_invalid') from None
        except ApplicationStateError as error:
            raise ContractError(error.code) from None
        _require(raw == canonical(profile), 'application_profile_noncanonical')
        route = next(row for row in scope['network']['target'] if
            (row['protocol'], row['host'], row['port']) == _url(
                next(row for row in scope['access'] if row['id'] == identity)['identity']['base_url'], 'scope_application_state_invalid'))
        _require(not route['address_policy']['public_only'] and any(ipaddress.ip_address('127.0.0.1') in ipaddress.ip_network(cidr)
                 for cidr in route['address_policy']['cidrs']), 'scope_application_state_invalid')
        frozen[f'applications/{identity}.json'] = raw
    _require(set(inputs['access_files']) == {row['id'] for row in scope['access']
                                           if row['kind'] in ('source', 'binary')}, 'inputs_access_mismatch')
    for access in scope['access']:
        identity = access['id']
        if access['kind'] == 'source':
            manifest = canonical(source_manifest(Path(inputs['access_files'][identity])))
            _require(digest(manifest) == access['identity']['manifest_sha256'], 'digest_mismatch')
            frozen[f'access/{identity}.manifest.json'] = manifest
        elif access['kind'] == 'binary':
            _pinned_digest(inputs['access_files'][identity], access['identity']['sha256'])
    for data in frozen.values():
        safe_publication(data)
    return VerifiedInputs(scope, inputs, goal, runtime_profiles, environment_profiles, frozen, fingerprint)


def inspect_inputs(path: Path, *, now: datetime | None = None) -> dict:
    verified = load_inputs(path, now=now)
    return {'status': 'verified_inputs', 'kind': INPUT_KIND,
            'engagement_id': verified.scope['engagement_id'],
            'scope_sha256': digest(verified.frozen_files['scope.md']),
            'goal_sha256': verified.scope['goal_sha256'],
            'signer_fingerprint': verified.signer_fingerprint,
            'access_modes': sorted({item['kind'] for item in verified.scope['access']}),
            'runtimes': {identity: {'kind': item['kind'], 'declared_version': item['version'],
                                    'provider': item['provider'], 'model': item['model']}
                         for identity, item in verified.runtime_profiles.items()},
            'environments': {identity: {'transport': item['transport'], 'platform': item['platform']}
                             for identity, item in verified.environment_profiles.items()},
            'hard_limits': verified.scope['limits']['hard'],
            'expires_at': verified.scope['expires_at'], 'capabilities_verified': False,
            'runtime_and_target_contact': False}
