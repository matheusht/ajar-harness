#!/usr/bin/env python3
"""Build, admit, run and exactly clean one offline amd64 managed T02 rehearsal."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
from typing import Callable
from urllib.parse import urlsplit


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
INTEGRATION_HEAD = 'b8f0453575740cb1482dc716fa1807c195459f58'
IMAGE_SOURCE_HEAD = 'adf6692474c81771e7e6fa2bc19e2a8dd067eb30'
IMAGE_TAG = 't02-managed-runtime:amd64-php8427-20261021a'
PLATFORM = 'linux/amd64'
BASE_IMAGE = ('ghcr.io/anomalyco/opencode@sha256:'
              '85986f556e985e377bd24cd68a5ccfbc647bb49e591194edda8a0e4542303319')
DOCKERFILE = ROOT / 'evals/native-qualification/Dockerfile.opencode-kanboard-runtime-php8427'
DOCKERFILE_SHA256 = 'be4948ac34c02f1cf84560f86874f07dc4d6c4b4efc8b1141956d2bf16f7497e'
CHECKS = ROOT / 'evals/native-qualification/T02-AMD64-MANAGED-OWNED-PHP8427-CHECKS-20261021.md'
CHECKS_SHA256 = 'a41d16baa20cbb5971df05b4f0621c147b6a4a592c76bec82fe3091cec826d99'
SOURCE_MANIFEST = ROOT / 'evals/native-qualification/t02-source/SOURCE-MANIFEST.json'
MANAGED_RUNNER = HERE / 'opencode_v2_managed_owned.py'
MANAGED_RUNNER_SHA256 = 'e5f442ddcda8515cb0fb29b9a601cdea068e6c66da795c4b8c8da0e351569475'
RELAY = ROOT / ('experiments/native-network-preflight/tcp-relay-host-override/'
                'cloud-linux-amd64-20261020a/tcp-relay-linux-amd64')
RELAY_SHA256 = '33ef7484c2a2415915af399689e91e9efee8000b2c685a6b2b72eb4eddedf895'
CA_SHA256 = '43e169bf3454bc74c12d3df8c1403f0b4e7da135bf5959f8ab31eb634896bf73'
CA_SIZE = 230249
INTERNAL_SUBNET = '172.28.225.0/24'
EXTERNAL_SUBNET = '172.28.224.0/24'
LISTEN_ADDRESS = '172.28.224.1'
RELAY_PEER = '172.28.224.10'
UPSTREAM_ROUTE = 'HTTPS_PROXY'
REQUIRED_PHP_PACKAGES = frozenset({
    'php84', 'php84-ctype', 'php84-dom', 'php84-gd', 'php84-iconv',
    'php84-mbstring', 'php84-openssl', 'php84-pdo_sqlite', 'php84-session',
    'php84-simplexml', 'php84-xml',
})
EXPECTED_IMAGE_ENV = {
    'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
    'BUN_RUNTIME_TRANSPILER_CACHE_PATH': '0',
}
REQUIRED_MANAGED_CHECKS = frozenset({
    'host-check created immutable image and exact mounts/env',
    'relay created immutable image and exact mounts/env',
    'first created immutable image and exact mounts/env',
    'reviewer created immutable image and exact mounts/env',
    'resume created immutable image and exact mounts/env',
    'external-receiver created immutable image and exact mounts/env',
    'host-owned network-none checker started',
    'host checker removed by exact ID',
    'archived T05 controls and relay active',
    'archived cloud owned inputs match fixed reviewed pins',
    'cloud owned mounts and fixture sources select archive',
    'inherited Docker commands use intended local daemon',
    'exact derived V2/PHP image',
    'ephemeral local TLS CA and leaf generated',
    'leaf verifies for fixed authority',
    'original snapshot matches seeded researcher project',
    'original PHP fails local check and prints before',
    'internal network created',
    'Docker internal subnet permits reserved relay address',
    'reserved relay address differs from internal gateway',
    'relay network created',
    'owned external bridge matches selected subnet and gateway',
    'relay joined only owned internal and external networks',
    'reserved relay address recorded before activation',
    'four bound producers created stopped',
    'only relay dual homed',
    'one managed fixed-authority CONNECT pool ready',
    'one original NativeRun and CONNECT allowance recorded',
    'frozen private peer and upstream mode match launch selection',
    'relay started at reserved internal address',
    'researcher effective proxy, trust and isolated DNS readback',
    'researcher reaches fixed CONNECT through owned relay',
    'alternate authority and wrong capability denied before tunnel',
    'owned external receiver started',
    'relay positive and researcher literal-IP direct egress denied',
    'native V2 image and config active',
    'reviewer and resume OpenCode processes idle before first turn',
    'cloud relay positive before wrong peer with settled tunnel',
    'cloud external wrong peer closes before HTTP and admission',
    'cloud internal researcher cannot reach listener directly',
    'cloud relay positive after wrong peer with settled tunnel',
    'first native model route reached',
    'native tools edited and checked harmless PHP',
    'first producer process subtree stopped before candidate snapshot',
    'model outputs are regular project files without symlinks',
    'only intended fixture source changed',
    'actual harmless research note exists and is bounded',
    'host-owned candidate snapshot matches stopped researcher output',
    'independent host PHP check passes and prints after',
    'researcher stopped and reviewer idle before packet publication',
    'fixed packet root and exact bytes frozen before reviewer session',
    'fresh reviewer has only read-only packet and separate empty project',
    'review retains original active run, pool and remaining allowance',
    'fresh reviewer native store has no prior sessions',
    'new reviewer session has no old messages',
    'fresh reviewer uses same model route and native store',
    'review did not replace pool, reset counters or change frozen packet',
    'candidate source and independent effect stable after reviewer',
    'first producer stopped before exact-session resume',
    'first process exited and stopped native store intact',
    'resume OpenCode process idle before same-session read',
    'session survives in presealed replacement',
    'exact native session resumed through same route',
    'host effect and source bytes retained after resume',
    'one host pool retains all role tunnels',
    'declared tunnel cap has room for bounded exhaustion probe',
    'same cap denies reviewer and resume with retained charges',
    'provider admission closed',
    'verified run stop and exact producers frozen',
    'queued and fresh host sends denied after verified stop',
    'source pins unchanged through managed run',
})
REQUIRED_MANAGED_CHECK_COUNTS = {
    name: (4 if name in {
        'host-check created immutable image and exact mounts/env',
        'host-owned network-none checker started',
        'host checker removed by exact ID',
    } else 1)
    for name in REQUIRED_MANAGED_CHECKS
}


class GateError(RuntimeError):
    """A stable public failure code for a fail-closed qualification gate."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _read_regular_stable(path: Path, code: str, *,
                         expected_sha256: str | None = None,
                         expected_size: int | None = None,
                         reject_group_world_write: bool = False) -> tuple[bytes, os.stat_result]:
    """Read one original path without following a symlink or accepting a race."""
    try:
        before_path = os.lstat(path)
    except OSError as error:
        raise GateError(code) from error
    if (stat.S_ISLNK(before_path.st_mode) or not stat.S_ISREG(before_path.st_mode)
            or (reject_group_world_write and before_path.st_mode & 0o022)):
        raise GateError(code)
    flags = os.O_RDONLY | getattr(os, 'O_CLOEXEC', 0) | getattr(os, 'O_NOFOLLOW', 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise GateError(code) from error
    try:
        before_fd = os.fstat(descriptor)
        identity = ('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns')
        if any(getattr(before_path, key) != getattr(before_fd, key) for key in identity):
            raise GateError(code)
        chunks = []
        while chunk := os.read(descriptor, 65536):
            chunks.append(chunk)
        data = b''.join(chunks)
        after_fd = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if any(getattr(before_fd, key) != getattr(after_fd, key) for key in identity):
        raise GateError(code + '_changed_during_read')
    if ((expected_size is not None and len(data) != expected_size)
            or (expected_sha256 is not None
                and sha256_bytes(data) != expected_sha256)):
        raise GateError(code)
    return data, before_fd


def strict_json(raw: bytes):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise GateError('duplicate_json_key')
            result[key] = value
        return result

    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GateError('invalid_json') from error


def _private_write(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                         | getattr(os, 'O_CLOEXEC', 0), 0o600)
    try:
        view = memoryview(data)
        while view:
            count = os.write(descriptor, view)
            if count <= 0:
                raise OSError('short write')
            view = view[count:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_json(path: Path, value: object) -> None:
    raw = (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()
    if path.exists():
        temporary = path.with_name(path.name + '.new')
        _private_write(temporary, raw)
        os.replace(temporary, path)
    else:
        _private_write(path, raw)


def _run(commands, argv: list[str], timeout: int = 60, env=None):
    result = commands.run(argv, capture_output=True, text=True,
                          timeout=timeout, env=env)
    if not isinstance(result, subprocess.CompletedProcess):
        raise GateError('invalid_command_result')
    return result


def _required(commands, argv: list[str], code: str, timeout: int = 60, env=None):
    result = _run(commands, argv, timeout=timeout, env=env)
    if result.returncode != 0:
        raise GateError(code)
    return result


def validate_sources() -> dict[str, object]:
    head = subprocess.run(
        ['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True,
        text=True, timeout=15)
    ancestor = subprocess.run(
        ['git', 'merge-base', '--is-ancestor', INTEGRATION_HEAD, 'HEAD'],
        cwd=ROOT, capture_output=True, text=True, timeout=15)
    status = subprocess.run(
        ['git', 'status', '--porcelain'], cwd=ROOT, capture_output=True,
        text=True, timeout=15)
    if (head.returncode or ancestor.returncode or status.returncode
            or not re.fullmatch(r'[0-9a-f]{40}\n?', head.stdout)
            or status.stdout):
        raise GateError('source_lineage_or_cleanliness_mismatch')
    critical = {
        DOCKERFILE: DOCKERFILE_SHA256,
        CHECKS: CHECKS_SHA256,
        MANAGED_RUNNER: MANAGED_RUNNER_SHA256,
        RELAY: RELAY_SHA256,
    }
    critical_reads = {}
    for path, digest in critical.items():
        critical_reads[path], _mode = _read_regular_stable(
            path, 'critical_source_pin_mismatch', expected_sha256=digest)
    manifest_bytes, _manifest_mode = _read_regular_stable(
        SOURCE_MANIFEST, 'source_manifest_pin_mismatch')
    manifest = strict_json(manifest_bytes)
    if (not isinstance(manifest, dict) or set(manifest) != {'schema_version', 'kind', 'files'}
            or manifest.get('schema_version') != 1 or manifest.get('kind') != 't02-cloud-source'
            or not isinstance(manifest.get('files'), list)):
        raise GateError('source_manifest_schema_mismatch')
    paths = set()
    declared = {}
    entries = []
    for item in manifest['files']:
        if (not isinstance(item, dict) or set(item) != {'path', 'bytes', 'sha256'}
                or not isinstance(item['path'], str)
                or type(item['bytes']) is not int or item['bytes'] < 0
                or not isinstance(item['sha256'], str)
                or not re.fullmatch(r'[0-9a-f]{64}', item['sha256'])
                or item['path'] in paths):
            raise GateError('source_manifest_entry_invalid')
        paths.add(item['path'])
        relative = Path(item['path'])
        if (relative.is_absolute() or not relative.parts
                or any(part in ('', '.', '..') for part in relative.parts)
                or relative.as_posix() != item['path']):
            raise GateError('source_manifest_path_escape')
        path = ROOT / relative
        _data, mode = _read_regular_stable(
            path, 'source_manifest_pin_mismatch',
            expected_sha256=item['sha256'], expected_size=item['bytes'])
        declared[path.absolute()] = item['sha256']
        entries.append({**item, 'executable': bool(mode.st_mode & 0o111)})
    if any(declared.get(path.absolute()) != digest for path, digest in critical.items()):
        raise GateError('critical_source_not_manifest_pinned')
    try:
        dockerfile = critical_reads[DOCKERFILE].decode('utf-8')
    except UnicodeDecodeError as error:
        raise GateError('dockerfile_policy_mismatch') from error
    if (dockerfile.splitlines()[0] != 'FROM ' + BASE_IMAGE
            or re.search(r'(?m)^ARG\s+', dockerfile)
            or any(f'{name}=8.4.27-r0' not in dockerfile
                   for name in REQUIRED_PHP_PACKAGES)):
        raise GateError('dockerfile_policy_mismatch')
    relay_bytes = critical_reads[RELAY]
    if (len(relay_bytes) < 20 or relay_bytes[:6] != b'\x7fELF\x02\x01'
            or relay_bytes[18:20] != b'>\x00'
            or not os.access(RELAY, os.X_OK)):
        raise GateError('relay_binary_policy_mismatch')
    final_status = subprocess.run(
        ['git', 'status', '--porcelain'], cwd=ROOT, capture_output=True,
        text=True, timeout=15)
    if final_status.returncode or final_status.stdout:
        raise GateError('source_changed_during_validation')
    return {
        'integration_head': INTEGRATION_HEAD,
        'image_source_head': IMAGE_SOURCE_HEAD,
        'source_commit': head.stdout.strip(),
        'source_manifest_sha256': sha256_bytes(manifest_bytes),
        'dockerfile_sha256': DOCKERFILE_SHA256,
        'checks_sha256': CHECKS_SHA256,
        'managed_runner_sha256': MANAGED_RUNNER_SHA256,
        'relay_sha256': RELAY_SHA256,
        'private': {'manifest_entries': entries,
                    'manifest_bytes': manifest_bytes},
    }


def stage_sources(source: dict[str, object], output: Path) -> dict[str, Path]:
    """Take a digest-checked private snapshot and use only it after validation."""
    private = source.get('private')
    if not isinstance(private, dict):
        raise GateError('source_snapshot_contract_failed')
    entries = private.get('manifest_entries')
    manifest_bytes = private.get('manifest_bytes')
    if not isinstance(entries, list) or not isinstance(manifest_bytes, bytes):
        raise GateError('source_snapshot_contract_failed')
    stage_root = output / 'source.private'
    try:
        stage_root.mkdir(mode=0o700)
        for entry in entries:
            if (not isinstance(entry, dict)
                    or set(entry) != {'path', 'bytes', 'sha256', 'executable'}):
                raise GateError('source_snapshot_contract_failed')
            relative = Path(entry['path'])
            source_path = ROOT / relative
            data, _mode = _read_regular_stable(
                source_path, 'source_changed_before_snapshot',
                expected_sha256=entry['sha256'], expected_size=entry['bytes'])
            destination = stage_root / relative
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            _private_write(destination, data)
            if entry['executable']:
                destination.chmod(0o700)
        staged_manifest = stage_root / SOURCE_MANIFEST.relative_to(ROOT)
        staged_manifest.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        _private_write(staged_manifest, manifest_bytes)
    except (OSError, GateError):
        shutil.rmtree(stage_root, ignore_errors=True)
        raise
    staged = {
        'root': stage_root,
        'cleanup_root': stage_root,
        'dockerfile': stage_root / DOCKERFILE.relative_to(ROOT),
        'managed_runner': stage_root / MANAGED_RUNNER.relative_to(ROOT),
        'relay': stage_root / RELAY.relative_to(ROOT),
    }
    if any(not path.is_file() for key, path in staged.items()
           if key not in {'root', 'cleanup_root'}):
        shutil.rmtree(stage_root, ignore_errors=True)
        raise GateError('source_snapshot_incomplete')
    return staged


def validate_ca(path: Path) -> dict[str, object]:
    if not path.is_absolute():
        raise GateError('managed_ca_file_mismatch')
    data, _mode = _read_regular_stable(
        path, 'managed_ca_file_mismatch', expected_size=CA_SIZE,
        reject_group_world_write=True)
    if sha256_bytes(data) != CA_SHA256:
        raise GateError('managed_ca_hash_mismatch')
    return {'sha256': CA_SHA256, 'size_bytes': CA_SIZE, 'bytes': data}


def _json_lines(raw: str, code: str) -> list[dict]:
    rows = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise GateError(code) from error
        if not isinstance(row, dict):
            raise GateError(code)
        rows.append(row)
    return rows


def _stable_builder(value):
    if isinstance(value, dict):
        return {key: _stable_builder(item) for key, item in sorted(value.items())
                if 'activity' not in key.lower()}
    if isinstance(value, list):
        return [_stable_builder(item) for item in value]
    return value


def _list_ids(commands, argv: list[str], code: str) -> list[str]:
    result = _required(commands, argv, code)
    values = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(values) != len(set(values)):
        raise GateError(code)
    return sorted(values)


def _inspect_each(commands, kind: str, identifiers: list[str], code: str) -> list[dict]:
    rows = []
    for identifier in identifiers:
        result = _required(commands, ['docker', kind, 'inspect', identifier], code)
        value = strict_json(result.stdout.encode())
        if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
            raise GateError(code)
        rows.append(value[0])
    return rows


def _cache_size_bytes(value: object) -> int:
    if type(value) is int and value >= 0:
        return value
    if not isinstance(value, str):
        raise GateError('docker_cache_row_invalid')
    match = re.fullmatch(r'(0|[1-9][0-9]*)(?:\.([0-9]+))?(B|kB|MB|GB|TB)', value)
    if not match:
        raise GateError('docker_cache_row_invalid')
    whole, fraction, unit = match.groups()
    fraction = fraction or ''
    numerator = int(whole + fraction)
    denominator = 10 ** len(fraction)
    multiplier = {
        'B': 1,
        'kB': 1000,
        'MB': 1000 ** 2,
        'GB': 1000 ** 3,
        'TB': 1000 ** 4,
    }[unit]
    scaled = numerator * multiplier
    if scaled % denominator:
        raise GateError('docker_cache_row_invalid')
    return scaled // denominator


def _cache_rows(commands) -> list[dict]:
    result = _required(commands, ['docker', 'buildx', 'du', '--format', 'json'],
                       'docker_cache_read_failed')
    rows = _json_lines(result.stdout, 'docker_cache_json_invalid')
    normalized = []
    for row in rows:
        identifier = row.get('ID', row.get('Id', row.get('id')))
        size = _cache_size_bytes(row.get('Size', row.get('size')))
        parent_keys = [key for key in ('Parents', 'parents') if key in row]
        if len(parent_keys) != 1:
            raise GateError('docker_cache_row_invalid')
        parents = row[parent_keys[0]]
        if parents is None:
            parents = []
        if (not isinstance(identifier, str) or not identifier
                or not isinstance(parents, list)
                or not all(isinstance(item, str) for item in parents)):
            raise GateError('docker_cache_row_invalid')
        normalized.append({'id': identifier, 'size_bytes': size,
                           'parents': sorted(set(parents))})
    if len({row['id'] for row in normalized}) != len(normalized):
        raise GateError('docker_cache_duplicate_id')
    return sorted(normalized, key=lambda row: row['id'])


def docker_snapshot(commands) -> dict[str, object]:
    context_name = _required(
        commands, ['docker', 'context', 'show'],
        'docker_context_read_failed').stdout.strip()
    if not context_name or '\n' in context_name:
        raise GateError('docker_context_invalid')
    context_value = strict_json(_required(
        commands, ['docker', 'context', 'inspect', context_name],
        'docker_context_inspect_failed').stdout.encode())
    if (not isinstance(context_value, list) or len(context_value) != 1
            or not isinstance(context_value[0], dict)):
        raise GateError('docker_context_inspect_failed')
    docker_endpoint = (context_value[0].get('Endpoints') or {}).get('docker')
    if not isinstance(docker_endpoint, dict):
        raise GateError('docker_context_inspect_failed')
    engine_value = strict_json(_required(
        commands, ['docker', 'info', '--format', '{{json .}}'],
        'docker_engine_read_failed').stdout.encode())
    if not isinstance(engine_value, dict):
        raise GateError('docker_engine_read_failed')
    containers = _list_ids(
        commands, ['docker', 'container', 'ls', '-aq', '--no-trunc'],
        'docker_container_list_failed')
    image_ids = _list_ids(
        commands, ['docker', 'image', 'ls', '-aq', '--no-trunc'],
        'docker_image_list_failed')
    images = _inspect_each(commands, 'image', image_ids, 'docker_image_inspect_failed')
    image_projection = sorted(({
        'id': item.get('Id'),
        'repo_tags': sorted(item.get('RepoTags') or []),
        'repo_digests': sorted(item.get('RepoDigests') or []),
        'os': item.get('Os'),
        'architecture': item.get('Architecture'),
        'layers': list((item.get('RootFS') or {}).get('Layers') or []),
    } for item in images), key=lambda item: str(item['id']))
    volumes = _list_ids(commands, ['docker', 'volume', 'ls', '-q'],
                        'docker_volume_list_failed')
    network_ids = _list_ids(
        commands, ['docker', 'network', 'ls', '-q', '--no-trunc'],
        'docker_network_list_failed')
    networks = _inspect_each(commands, 'network', network_ids,
                             'docker_network_inspect_failed')
    network_projection = sorted(({
        'id': item.get('Id'), 'name': item.get('Name'),
        'driver': item.get('Driver'), 'internal': item.get('Internal'),
        'ipam': item.get('IPAM'), 'labels': item.get('Labels') or {},
        'options': item.get('Options') or {},
        'containers': sorted((item.get('Containers') or {}).keys()),
    } for item in networks), key=lambda item: str(item['id']))
    builders = _required(
        commands, ['docker', 'buildx', 'ls', '--format', 'json'],
        'docker_builder_read_failed')
    builder_rows = sorted(
        (_stable_builder(row) for row in _json_lines(
            builders.stdout, 'docker_builder_json_invalid')),
        key=lambda item: json.dumps(item, sort_keys=True))
    current_builders = [row for row in builder_rows
                        if row.get('Current') is True]
    if len(current_builders) != 1:
        raise GateError('docker_selected_builder_invalid')
    selected_builder = current_builders[0]
    cache = _cache_rows(commands)
    return {
        'context': {
            'name': context_name,
            'docker_host': docker_endpoint.get('Host'),
            'skip_tls_verify': docker_endpoint.get('SkipTLSVerify'),
        },
        'engine': {
            'id': engine_value.get('ID'),
            'name': engine_value.get('Name'),
            'os_type': engine_value.get('OSType'),
            'architecture': engine_value.get('Architecture'),
            'storage_driver': engine_value.get('Driver'),
            'server_version': engine_value.get('ServerVersion'),
            'docker_root_dir': engine_value.get('DockerRootDir'),
        },
        'containers': containers,
        'images': image_projection,
        'volumes': volumes,
        'networks': network_projection,
        'builders': builder_rows,
        'selected_builder': _stable_builder(selected_builder),
        'cache': cache,
        'cache_bytes': sum(row['size_bytes'] for row in cache),
    }


def _assert_fresh_topology(baseline: dict[str, object], commands,
                           environ: dict[str, str]) -> None:
    context = baseline.get('context')
    engine = baseline.get('engine')
    selected_builder = baseline.get('selected_builder')
    builder_nodes = (selected_builder.get('Nodes')
                     if isinstance(selected_builder, dict) else None)
    node = (builder_nodes[0]
            if isinstance(builder_nodes, list) and len(builder_nodes) == 1
            else None)
    endpoint = node.get('Endpoint') if isinstance(node, dict) else None
    platforms = node.get('Platforms') if isinstance(node, dict) else None
    has_amd64 = ('linux/amd64' in platforms if isinstance(platforms, str)
                 else isinstance(platforms, list) and 'linux/amd64' in platforms)
    if (environ.get('DOCKER_HOST') not in (None, '', 'unix:///var/run/docker.sock')
            or environ.get('DOCKER_CONTEXT') not in (None, '', 'default')
            or environ.get('BUILDX_BUILDER') not in (None, '')
            or environ.get('BUILDKIT_HOST') not in (None, '')
            or not isinstance(context, dict)
            or context != {
                'name': 'default',
                'docker_host': 'unix:///var/run/docker.sock',
                'skip_tls_verify': False,
            }
            or not isinstance(engine, dict)
            or not isinstance(engine.get('id'), str) or not engine['id']
            or engine.get('os_type') != 'linux'
            or engine.get('architecture') not in {'x86_64', 'amd64'}
            or not isinstance(selected_builder, dict)
            or selected_builder.get('Current') is not True
            or selected_builder.get('Name') != 'default'
            or selected_builder.get('Driver') != 'docker'
            or not isinstance(node, dict)
            or node.get('Name') != 'default'
            or endpoint not in {context.get('name'), context.get('docker_host')}
            or node.get('Status') != 'running'
            or not has_amd64):
        raise GateError('local_linux_amd64_engine_mismatch')
    existing = _run(commands, ['docker', 'image', 'inspect', IMAGE_TAG])
    if existing.returncode == 0:
        raise GateError('candidate_tag_preexisting')
    if existing.returncode not in (1,):
        raise GateError('candidate_tag_inspect_uncertain')
    requested = [ipaddress.ip_network(INTERNAL_SUBNET),
                 ipaddress.ip_network(EXTERNAL_SUBNET)]
    if requested[0].overlaps(requested[1]):
        raise GateError('requested_subnets_overlap')
    for network in baseline['networks']:
        for config in (network.get('ipam') or {}).get('Config') or []:
            subnet = config.get('Subnet') if isinstance(config, dict) else None
            if not subnet:
                continue
            try:
                current = ipaddress.ip_network(subnet)
            except ValueError as error:
                raise GateError('existing_subnet_invalid') from error
            if any(current.overlaps(item) for item in requested):
                raise GateError('requested_subnet_conflict')


def _image_info(commands, reference: str, code: str) -> dict:
    result = _required(commands, ['docker', 'image', 'inspect', reference], code)
    value = strict_json(result.stdout.encode())
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        raise GateError(code)
    return value[0]


def admit_build_provenance(path: Path, image_info: dict, image_id: str) -> dict:
    raw, _mode = _read_regular_stable(path, 'build_provenance_unreadable')
    if not raw or len(raw) > 1024 * 1024:
        raise GateError('build_provenance_size_invalid')
    value = strict_json(raw)
    if not isinstance(value, dict):
        raise GateError('build_provenance_invalid')
    provenance = value.get('buildx.build.provenance')
    invocation = provenance.get('invocation') if isinstance(provenance, dict) else None
    parameters = invocation.get('parameters') if isinstance(invocation, dict) else None
    environment = invocation.get('environment') if isinstance(invocation, dict) else None
    config_source = invocation.get('configSource') if isinstance(invocation, dict) else None
    materials = provenance.get('materials') if isinstance(provenance, dict) else None
    secrets = parameters.get('secrets') if isinstance(parameters, dict) else None
    locals_ = parameters.get('locals') if isinstance(parameters, dict) else None
    layers = (image_info.get('RootFS') or {}).get('Layers')
    manifest_digest = value.get('containerimage.digest')
    base_digest = BASE_IMAGE.rsplit('@sha256:', 1)[1]
    material_ok = (
        isinstance(materials, list) and len(materials) == 1
        and isinstance(materials[0], dict)
        and materials[0].get('digest') == {'sha256': base_digest}
        and isinstance(materials[0].get('uri'), str)
        and 'digest=sha256:' + base_digest in materials[0]['uri']
        and 'platform=linux%2Famd64' in materials[0]['uri'])
    if (value.get('containerimage.config.digest') != image_id
            or not isinstance(manifest_digest, str)
            or not re.fullmatch(r'sha256:[0-9a-f]{64}', manifest_digest)
            or not isinstance(provenance, dict)
            or provenance.get('buildType') != 'https://mobyproject.org/buildkit@v1'
            or not material_ok
            or not isinstance(invocation, dict)
            or not isinstance(config_source, dict)
            or config_source.get('entryPoint') != DOCKERFILE.name
            or not isinstance(parameters, dict)
            or parameters.get('frontend') != 'dockerfile.v0'
            or secrets != [{'id': 'proxy_ca', 'optional': True}]
            or not isinstance(locals_, list)
            or {item.get('name') for item in locals_ if isinstance(item, dict)}
            != {'context', 'dockerfile'}
            or not isinstance(environment, dict)
            or environment.get('platform') != PLATFORM
            or not isinstance(layers, list) or not layers
            or any(not isinstance(layer, str)
                   or not re.fullmatch(r'sha256:[0-9a-f]{64}', layer)
                   for layer in layers)):
        raise GateError('build_provenance_mismatch')
    return {
        'private_metadata_sha256': sha256_bytes(raw),
        'build_type': provenance['buildType'],
        'base_material': BASE_IMAGE,
        'platform': PLATFORM,
        'secret_ids': ['proxy_ca'],
        'image_config_digest': image_id,
        'image_manifest_digest': manifest_digest,
        'rootfs_layer_count': len(layers),
    }


def _image_env_is_allowlisted(info: dict) -> bool:
    env = (info.get('Config') or {}).get('Env') or []
    if not isinstance(env, list) or any(not isinstance(item, str) or '=' not in item for item in env):
        return False
    pairs = [item.split('=', 1) for item in env]
    names = [name for name, _value in pairs]
    return len(names) == len(set(names)) and dict(pairs) == EXPECTED_IMAGE_ENV


def _probe(commands, image_id: str, entrypoint: str, *args: str):
    argv = ['docker', 'run', '--rm', '--pull=never', '--platform', PLATFORM,
            '--network', 'none', '--entrypoint', entrypoint, image_id, *args]
    return _required(commands, argv, 'runtime_probe_failed', timeout=90)


def admit_runtime(commands, image_info: dict, image_id: str,
                  recorded_at: Callable[[], str], output: Path) -> dict:
    if (image_info.get('Id') != image_id or image_info.get('Os') != 'linux'
            or image_info.get('Architecture') != 'amd64'
            or IMAGE_TAG not in (image_info.get('RepoTags') or [])
            or not _image_env_is_allowlisted(image_info)):
        raise GateError('candidate_metadata_admission_failed')
    packages_result = _probe(commands, image_id, 'apk', 'info', '-v')
    php_result = _probe(commands, image_id, 'php', '-v')
    modules_result = _probe(commands, image_id, 'php', '-m')
    opencode_result = _probe(commands, image_id, 'opencode', '--version')
    tools_result = _probe(
        commands, image_id, 'sh', '-c',
        'for n in sh php wget opencode; do command -v "$n" >/dev/null || exit 7; echo "$n"; done')
    packages = sorted(line.strip() for line in packages_result.stdout.splitlines()
                      if line.strip().startswith('php84'))
    required = {f'{name}-8.4.27-r0' for name in REQUIRED_PHP_PACKAGES}
    version_lines = php_result.stdout.splitlines()
    modules = sorted({line.strip().lower() for line in modules_result.stdout.splitlines()
                      if line.strip()})
    tools = tools_result.stdout.splitlines()
    if (not packages or not required <= set(packages)
            or any(not item.endswith('-8.4.27-r0') for item in packages)
            or not version_lines or not version_lines[0].startswith('PHP 8.4.27 ')
            or not {'gd', 'pdo_sqlite'} <= set(modules)
            or opencode_result.stdout.strip() != 'opencode v2.0.32'
            or tools != ['sh', 'php', 'wget', 'opencode']):
        raise GateError('runtime_content_admission_failed')
    receipt = {
        'schema_version': 1,
        'kind': 't02-managed-owned-amd64-php8427-runtime-admission',
        'recorded_at': recorded_at(),
        'status': 'pass',
        'image_id': image_id,
        'platform': PLATFORM,
        'execution_policy': {'pull': 'never', 'network': 'none'},
        'php_version': version_lines[0],
        'opencode_version': 'opencode v2.0.32',
        'installed_php84_packages': packages,
        'required_modules': ['gd', 'pdo_sqlite'],
        'required_tools': ['sh', 'php', 'wget', 'opencode'],
        'image_environment_names': sorted(EXPECTED_IMAGE_ENV),
        'external_activity': {'provider_calls': 0, 'model_calls': 0,
                              'live_targets_contacted': 0},
    }
    _write_json(output / 'runtime-admission.json', receipt)
    return receipt


def _managed_summary(value: dict) -> dict:
    checks = value.get('checks')
    runs = value.get('native_runs')
    if (value.get('status') != 'pass'
            or value.get('classification') !=
            'owned TLS/native managed CONNECT offline E2E; zero provider calls'
            or value.get('review_status') != 'unqualified_owned_synthetic_response'
            or not isinstance(checks, list) or not checks
            or any(not isinstance(item, dict) or item.get('pass') is not True
                   for item in checks)
            or not isinstance(runs, list)
            or [(item.get('stage'), item.get('exit_code')) for item in runs]
            != [('first', 0), ('reviewer', 0), ('resume', 0)]
            or value.get('cleanup_complete') is not True
            or value.get('temporary_secret_files_removed') is not True
            or value.get('source_pins_stable') is not True
            or value.get('source_copies_match') is not True):
        raise GateError('managed_result_admission_failed')
    names = [item.get('name') for item in checks]
    if Counter(names) != Counter(REQUIRED_MANAGED_CHECK_COUNTS):
        raise GateError('managed_required_checks_missing')
    return {
        'status': 'pass',
        'classification': value['classification'],
        'review_status': value['review_status'],
        'checks_passed': len(checks),
        'checks_total': len(checks),
        'required_check_counts': dict(sorted(REQUIRED_MANAGED_CHECK_COUNTS.items())),
        'native_stages': ['first', 'reviewer', 'resume'],
        'cleanup_complete': True,
        'temporary_secret_files_removed': True,
        'source_pins_stable': True,
        'source_copies_match': True,
    }


def _cache_cleanup_order(rows: list[dict], new_ids: set[str]) -> list[str]:
    by_id = {row['id']: row for row in rows if row['id'] in new_ids}
    depth_cache = {}

    def depth(identifier: str, active: set[str]) -> int:
        if identifier in depth_cache:
            return depth_cache[identifier]
        if identifier in active:
            raise GateError('cache_parent_cycle')
        active = active | {identifier}
        parents = [item for item in by_id[identifier]['parents'] if item in by_id]
        value = 0 if not parents else 1 + max(depth(parent, active) for parent in parents)
        depth_cache[identifier] = value
        return value

    return sorted(new_ids, key=lambda identifier: (depth(identifier, set()), identifier),
                  reverse=True)


def cleanup_outer(commands, baseline: dict | None, image_id: str | None) -> dict:
    result = {'image_removed': False, 'cache_ids_removed': [],
              'unresolved_cache_ids': [], 'errors': []}
    if baseline is None:
        return result
    baseline_images = {item['id'] for item in baseline['images']}
    tag_info = _run(commands, ['docker', 'image', 'inspect', IMAGE_TAG])
    removable_id = image_id
    if tag_info.returncode == 0:
        try:
            values = strict_json(tag_info.stdout.encode())
            actual = values[0].get('Id') if isinstance(values, list) and len(values) == 1 else None
        except GateError:
            actual = None
        if not isinstance(actual, str) or actual in baseline_images:
            result['errors'].append('candidate_image_identity_uncertain')
        elif image_id is not None and actual != image_id:
            result['errors'].append('candidate_image_identity_changed')
        else:
            removable_id = actual
            removed = _run(commands, ['docker', 'image', 'rm', IMAGE_TAG])
            if removed.returncode:
                result['errors'].append('candidate_tag_remove_failed')
    if removable_id and removable_id not in baseline_images:
        present = _run(commands, ['docker', 'image', 'inspect', removable_id])
        if present.returncode == 0:
            removed = _run(commands, ['docker', 'image', 'rm', removable_id])
            if removed.returncode:
                result['errors'].append('candidate_image_remove_failed')
    tag_after = _run(commands, ['docker', 'image', 'inspect', IMAGE_TAG])
    id_after = (_run(commands, ['docker', 'image', 'inspect', removable_id])
                if removable_id else None)
    result['image_removed'] = (tag_after.returncode != 0
                               and (id_after is None or id_after.returncode != 0))
    try:
        current_cache = _cache_rows(commands)
        baseline_ids = {row['id'] for row in baseline['cache']}
        new_ids = {row['id'] for row in current_cache} - baseline_ids
        for identifier in _cache_cleanup_order(current_cache, new_ids):
            pruned = _run(commands, [
                'docker', 'buildx', 'prune', '--force', '--filter', 'id=' + identifier])
            if pruned.returncode == 0:
                result['cache_ids_removed'].append(identifier)
            else:
                result['errors'].append('cache_remove_failed')
        after_ids = {row['id'] for row in _cache_rows(commands)}
        result['unresolved_cache_ids'] = sorted(after_ids - baseline_ids)
    except GateError as error:
        result['errors'].append(str(error))
    return result


def run_attempt(output: Path, ca_path: Path, commands, environ: dict[str, str],
                *, source_validator=validate_sources, ca_validator=validate_ca,
                source_snapshotter=stage_sources,
                expected_source_commit: str,
                recorded_at: Callable[[], str]) -> int:
    output = output.resolve()
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    baseline = None
    image_id = None
    managed = None
    runtime = None
    source = None
    staged = None
    failure = None
    attempted = False
    private_ca = output / 'managed-ca.private.pem'
    cleanup = {'image_removed': False, 'cache_ids_removed': [],
               'unresolved_cache_ids': [], 'errors': []}
    baseline_restored = False
    try:
        source = source_validator()
        if (not isinstance(source, dict)
                or not re.fullmatch(r'[0-9a-f]{40}', expected_source_commit)
                or source.get('source_commit') != expected_source_commit):
            raise GateError('exact_source_commit_mismatch')
        ca = ca_validator(ca_path)
        if (ca.get('sha256') != CA_SHA256 or ca.get('size_bytes') != CA_SIZE
                or not isinstance(ca.get('bytes'), bytes)):
            raise GateError('managed_ca_validation_contract_failed')
        proxy = environ.get(UPSTREAM_ROUTE)
        try:
            parsed = urlsplit(proxy) if isinstance(proxy, str) else None
            proxy_port = parsed.port if parsed else None
        except ValueError as error:
            raise GateError('managed_proxy_environment_unavailable') from error
        if (not parsed or parsed.scheme not in ('http', 'https')
                or not parsed.hostname or proxy_port is None):
            raise GateError('managed_proxy_environment_unavailable')
        staged = source_snapshotter(source, output)
        if (not isinstance(staged, dict)
                or not all(isinstance(staged.get(key), Path)
                           for key in ('root', 'dockerfile', 'managed_runner', 'relay'))):
            raise GateError('source_snapshot_contract_failed')
        baseline = docker_snapshot(commands)
        _write_json(output / 'baseline.private.json', baseline)
        _assert_fresh_topology(baseline, commands, environ)
        _private_write(private_ca, ca['bytes'])
        build_metadata = output / 'build-metadata.private.json'
        build = [
            'docker', 'buildx', 'build', '--builder', 'default',
            '--platform', PLATFORM, '--load',
            '--secret', 'id=proxy_ca,src=' + str(private_ca),
            '--metadata-file', str(build_metadata),
            '--file', str(staged['dockerfile']), '--tag', IMAGE_TAG,
            str(staged['dockerfile'].parent),
        ]
        attempted = True
        built = _run(commands, build, timeout=600, env=environ)
        build_output_hash = sha256_bytes((built.stdout + '\0' + built.stderr).encode())
        if built.returncode:
            raise GateError('candidate_build_failed')
        private_ca.unlink()
        info = _image_info(commands, IMAGE_TAG, 'candidate_image_registration_failed')
        image_id = info.get('Id')
        baseline_ids = {item['id'] for item in baseline['images']}
        if (not isinstance(image_id, str)
                or not re.fullmatch(r'sha256:[0-9a-f]{64}', image_id)
                or image_id in baseline_ids):
            raise GateError('candidate_image_not_new_and_immutable')
        provenance = admit_build_provenance(build_metadata, info, image_id)
        candidate = {
            'schema_version': 1,
            'kind': 't02-managed-owned-amd64-php8427-candidate',
            'recorded_at': recorded_at(),
            'status': 'registered_before_execution',
            'integration_head': INTEGRATION_HEAD,
            'image_source_head': IMAGE_SOURCE_HEAD,
            'source_commit': source['source_commit'],
            'source_manifest_sha256': source['source_manifest_sha256'],
            'dockerfile_sha256': DOCKERFILE_SHA256,
            'base_image': BASE_IMAGE,
            'managed_ca': {'sha256': CA_SHA256, 'size_bytes': CA_SIZE,
                           'buildkit_secret_only': True,
                           'system_trust_changed': False},
            'platform': PLATFORM,
            'tag': IMAGE_TAG,
            'image_id': image_id,
            'build_provenance': provenance,
            'build_output_private_sha256': build_output_hash,
            'image_execution_attempted': False,
            'baseline_private_sha256': sha256_file(output / 'baseline.private.json'),
        }
        _write_json(output / 'candidate.json', candidate)
        runtime = admit_runtime(commands, info, image_id, recorded_at, output)
        managed_output = output / 'managed-run.private'
        argv = [
            sys.executable, str(staged['managed_runner']), '--output', str(managed_output),
            '--cloud-platform', PLATFORM, '--cloud-image-id', image_id,
            '--cloud-relay', str(staged['relay']), '--cloud-relay-sha256', RELAY_SHA256,
            '--cloud-internal-subnet', INTERNAL_SUBNET,
            '--cloud-external-subnet', EXTERNAL_SUBNET,
            '--cloud-listen-address', LISTEN_ADDRESS,
            '--cloud-relay-peer', RELAY_PEER,
            '--cloud-upstream-route', UPSTREAM_ROUTE,
        ]
        run = _run(commands, argv, timeout=900, env=environ)
        if run.returncode:
            raise GateError('managed_runner_failed')
        managed_value = strict_json((managed_output / 'result.json').read_bytes())
        if not isinstance(managed_value, dict):
            raise GateError('managed_result_invalid')
        managed = _managed_summary(managed_value)
    except (GateError, OSError, subprocess.SubprocessError, ValueError) as error:
        failure = str(error) if isinstance(error, GateError) else 'controller_internal_failure'
    finally:
        if private_ca.exists():
            try:
                private_ca.unlink()
            except OSError:
                failure = failure or 'private_ca_cleanup_failed'
        cleanup_root = staged.get('cleanup_root') if isinstance(staged, dict) else None
        if isinstance(cleanup_root, Path):
            try:
                if cleanup_root.parent != output or cleanup_root.name != 'source.private':
                    raise OSError('unexpected source snapshot cleanup path')
                shutil.rmtree(cleanup_root)
            except OSError:
                failure = failure or 'source_snapshot_cleanup_failed'
        cleanup = cleanup_outer(commands, baseline, image_id)
        if baseline is not None:
            try:
                final = docker_snapshot(commands)
                _write_json(output / 'final-baseline.private.json', final)
                baseline_restored = final == baseline
            except (GateError, OSError):
                baseline_restored = False
                cleanup['errors'].append('final_baseline_unverifiable')
    success = (failure is None and managed is not None and runtime is not None
               and cleanup['image_removed']
               and not cleanup['unresolved_cache_ids']
               and not cleanup['errors'] and baseline_restored)
    status = 'pass' if success else ('blocked' if not attempted else 'fail')
    receipt = {
        'schema_version': 1,
        'kind': 't02-managed-owned-amd64-php8427-result',
        'recorded_at': recorded_at(),
        'status': status,
        'failure': failure,
        'source': ({key: value for key, value in source.items()
                    if key != 'private'} if isinstance(source, dict) else None),
        'candidate_image_id': image_id,
        'runtime_admitted': runtime is not None,
        'managed': managed,
        'external_activity': {
            'provider_calls': 0, 'model_calls': 0, 'live_targets_contacted': 0,
            'engagements_started': 0, 'external_credentials_used': 0,
            'researcher_bundle_created': False,
        },
        'live_admission_enabled': False,
        'cleanup': cleanup,
        'baseline_restored': baseline_restored,
        'claim_limits': {
            'owned_synthetic_response_only': True,
            'provider_or_model_route_qualified': False,
            'live_tls_qualified': False,
            'default_adoption': False,
        },
    }
    _write_json(output / 'result.json', receipt)
    return 0 if success else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--managed-ca', required=True, type=Path)
    parser.add_argument('--source-commit', required=True)
    args = parser.parse_args()

    def recorded_at():
        import datetime
        return datetime.datetime.now(datetime.timezone.utc).replace(
            microsecond=0).isoformat().replace('+00:00', 'Z')

    return run_attempt(args.output, args.managed_ca, subprocess, dict(os.environ),
                       expected_source_commit=args.source_commit,
                       recorded_at=recorded_at)


if __name__ == '__main__':
    raise SystemExit(main())
