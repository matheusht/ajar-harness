#!/usr/bin/env python3
"""Native V2 + managed CONNECT on harmless PHP; owned TLS or one live free run."""
import argparse
import base64
import contextlib
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import runpy
import select
import shutil
import socket
import sqlite3
import ssl
import stat
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from urllib.parse import urlsplit


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CONTROLS = ROOT / 'experiments/native-network-preflight'

IMAGE = 't02-kanboard-runtime:20261020a'
IMAGE_ID = 'sha256:31b7fa2b80f17bbddfeffd0577634257df40490f1b8d4c57f8507b40956cdf15'
MODEL = 'opencode/deepseek-v4.1-flash-free'
OWNED_PATH = '/inference/openai/v1/chat/completions'
CONFIG = HERE / 'opencode_v2_observed_config.json'
LIVE_CONFIG = HERE / 'opencode_v2_live_config.json'
OBSERVER = HERE / 'opencode_v2_request_observer'
RELAY = CONTROLS / 'evidence/v2-connect-official-20261019b/tcp-relay-linux-arm64'
CONNECT = CONTROLS / 'v2_connect.py'
NATIVE = CONTROLS / 'v2-effect-windows/native_run.py'
PRODUCER = CONTROLS / 'v2-effect-windows/producer_stop.py'
DOCKER_RUNTIME = ROOT / 'tools/docker_session_runtime.py'
CHECKS = ROOT / 'evals/native-qualification/T02-V2-MANAGED-OFFLINE-CHECKS-20261020.md'
LIVE_CHECKS = ROOT / 'evals/native-qualification/T02-V2-MANAGED-LIVE-CHECKS-20261020.md'
LIVE_PREPARATION_CHECKS = ROOT / 'evals/native-qualification/T02-LIVE-PREPARATION-CHECKS-20261021.md'
REVIEW_CHECKS = ROOT / 'evals/native-qualification/T02-REVIEWER-PACKET-CHECKS-20261021.md'
MOCK_PHP = HERE / 'opencode_v2_mock_provider.php'
FIXTURE = (HERE / 'index.php', HERE / 'message.php', HERE / 'check.php')
LABEL = 'io.lrh.t02-managed-owned'
DOCKER_PROXY_ENV = ('HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY', 'ALL_PROXY', 'FTP_PROXY',
                    'http_proxy', 'https_proxy', 'no_proxy', 'all_proxy', 'ftp_proxy')
TRUST_ENV = ('SSL_CERT_FILE', 'SSL_CERT_DIR', 'CURL_CA_BUNDLE', 'REQUESTS_CA_BUNDLE',
             'NODE_EXTRA_CA_CERTS', 'NODE_TLS_REJECT_UNAUTHORIZED', 'GIT_SSL_CAINFO',
             'GIT_SSL_NO_VERIFY', 'SSLKEYLOGFILE')
ABSENT_TRUST_ENV = ('NODE_TLS_REJECT_UNAUTHORIZED', 'GIT_SSL_NO_VERIFY', 'SSLKEYLOGFILE')
CLEARABLE_TRUST_ENV = tuple(name for name in TRUST_ENV if name not in ABSENT_TRUST_ENV)
RUNTIME_CA_DEST = '/fixture/runtime-ca.pem'
MAX_RUNTIME_CA_BYTES = 4 * 1024 * 1024
CONNECT_SHA = 'f3bca478555f72a5411987a51e59d630b69dd8b86dd3c8ecc5d7d9971e4f24ea'
NATIVE_SHA = 'c567147c9006766bd6aa5445fcda94093a0812ef1cd0f4c3d41be42d56974c4d'
PRODUCER_SHA = '7e939e8d245996b12f3f509e272acd3a538f222b4c537a8dee6fa0b55dac1db2'
RELAY_SHA = 'f2b4a65487fecbace54ea4954d26f80566b9ccd8a7c476d826b40fe5bf65bbb8'
DOCKER_RUNTIME_SHA = '9beff3af097a711010a5234f2ab72f549f617fdcf8c3833b6d5a29c7fa582b28'
CONTROL_SHA = {CONNECT: CONNECT_SHA, NATIVE: NATIVE_SHA, PRODUCER: PRODUCER_SHA,
               DOCKER_RUNTIME: DOCKER_RUNTIME_SHA}
COMMON_INPUT_SHA = {
    HERE / 'index.php': 'f070f8308bda12bb56df51717675d86558a53891666d419052013e811ce3b7b7',
    HERE / 'message.php': 'ac12d930241f36a93d5e83b7b37737219a8d04fe0d3d5a417a8c3b7edbf8c9d9',
    HERE / 'check.php': '48198c955323cd63bd31e7bdf6a758a5785de513123f00786a6a12aca14e3ba5',
    OBSERVER / 'server.js': 'f3116d1f9555e600aa774f15a80fef0620a5e9d073854bb7ef2c62f985f010bd',
    OBSERVER / 'package.json': '1239d4d885dcad42201a27ed9324f8f0f760b78700d8db9ced39a511cffe7eae',
    MOCK_PHP: '3eccc5c7bd8a9e60c743b6199f60ae669ed9f2d9df4f3e11d69b2038f1215880',
}
LIVE_INPUT_SHA = {LIVE_CONFIG: '9e208956245a68324aebb8b02ff3adda289a8efa3bfa1f132b0d33c7b530c3e8',
                  **COMMON_INPUT_SHA}
CLOUD_OWNED_INPUT_SHA = {CONFIG: '8c63991951ecf580549be2e5cb08ad6746e10adae91f404e11c3a5138bc4215b',
                         **COMMON_INPUT_SHA}
SHELL = ('cat index.php message.php check.php && '
         'sed -i "s/return \'before\';/return \'after\';/" message.php && '
         'php -l index.php && php -l message.php && php -l check.php && '
         'php check.php && php index.php && '
         "printf 'Harmless local change: message() returns after; php check.php passed.\\n' > research-note.md")
PHP_CHECKS = ('php -l index.php', 'php -l message.php', 'php -l check.php',
              'php check.php', 'php index.php')
PACKET_SOURCE_NAMES = ('index.php', 'message.php', 'check.php')
PACKET_PROMPT = (
    'Read /handoff/REQUEST.json and verify every listed file and SHA256 before relying on it. '
    'Inspect CLAIMS.md, RESEARCH.md, all ORIGINAL-* and candidate PHP, RAW-NATIVE-TOOLS.json, '
    'RAW-APP-CHECKS.json and UNFINISHED.json. The original files use ORIGINAL-* names only in '
    '/handoff; copy them to a separate scratch directory with their normal PHP names if you replay '
    'a baseline. Choose and run a material causal or control check using your own tools. State the '
    'exact check and output, which bases remain valid, contrary evidence, any unsupported dismissal, '
    'unfinished conditions, assistance, and limits. This is a harmless local PHP exercise; do not '
    'infer a security finding or an original protected observation from host replay.\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def packet_public_bytes(value, capability, forbidden_paths=()):
    data = value if isinstance(value, bytes) else value.encode()
    if not 0 < len(data) <= 128 * 1024:
        raise RuntimeError('review_packet_material_size')
    try:
        content = data.decode('utf-8')
    except UnicodeDecodeError:
        raise RuntimeError('review_packet_material_encoding') from None
    encoded_capability = base64.b64encode(('run:' + capability).encode()).decode()
    if (capability in content or encoded_capability in content
            or any(path and path in content for path in forbidden_paths)
            or re.search(r'(?i)(?:/Users/|/private/tmp/|/tmp/|/home/|'
                         r'/workspace/(?!project(?:/|\b))|/observer/|file://|https?://|'
                         r'authorization|bearer|cookie|password|secret|credential|'
                         r'api[_-]?key|local_[0-9a-f]{32}|BEGIN [A-Z ]*PRIVATE KEY)', content)):
        raise RuntimeError('review_packet_sensitive_material')
    return data


def native_tool_material(stdout):
    records = []
    for line_number, line in enumerate(stdout.splitlines(), 1):
        try:
            event = json.loads(line)
        except ValueError:
            raise RuntimeError('native_tool_stream_invalid') from None
        if not isinstance(event, dict):
            raise RuntimeError('native_tool_stream_invalid')
        part = event.get('part')
        if not isinstance(part, dict) or part.get('type') != 'tool':
            continue
        state = part.get('state')
        if not isinstance(state, dict) or not isinstance(part.get('tool'), str):
            raise RuntimeError('native_tool_part_invalid')
        records.append({'line': line_number, 'session_id': event.get('sessionID'),
                        'tool': part['tool'], 'status': state.get('status'),
                        'input': state.get('input'), 'output': state.get('output'),
                        'error': state.get('error')})
    if not records:
        raise RuntimeError('native_tool_evidence_missing')
    return {'source': 'native JSONL tool parts in observed order', 'records': records,
            'stream_line_count': len(stdout.splitlines()),
            'intermediate_source_versions': 'unavailable; baseline and final candidate are separately pinned'}


def publish_review_packet(directory, originals, candidate, note, native_stdout, app_checks,
                          capability, forbidden_paths=(), protected_observation=None):
    if protected_observation is not None:
        raise RuntimeError('protected_observation_source_unreviewed')
    if (directory.is_symlink() or not directory.is_dir() or list(directory.iterdir())
            or any(not (base / name).is_file() or (base / name).is_symlink()
                   for base in (originals, candidate) for name in PACKET_SOURCE_NAMES)
            or note.is_symlink() or not note.is_file()):
        raise RuntimeError('review_packet_input_invalid')
    files = {'ORIGINAL-' + name: (originals / name).read_bytes() for name in PACKET_SOURCE_NAMES}
    files.update({name: (candidate / name).read_bytes() for name in PACKET_SOURCE_NAMES})
    files['RESEARCH.md'] = note.read_bytes()
    note_hash = hashlib.sha256(files['RESEARCH.md']).hexdigest()
    files['CLAIMS.md'] = (
        '# Harmless local result\n\nThe actual researcher note is RESEARCH.md (SHA256 '
        + note_hash + '). This operator restatement records the intended local before/after PHP '
        'exercise only. It is not a security finding or protected original observation.\n').encode()
    tool_material = native_tool_material(native_stdout)
    tool_material['source_before_sha256'] = {name: hashlib.sha256(files['ORIGINAL-' + name]).hexdigest()
                                             for name in PACKET_SOURCE_NAMES}
    tool_material['source_after_sha256'] = {name: hashlib.sha256(files[name]).hexdigest()
                                            for name in PACKET_SOURCE_NAMES}
    files['RAW-NATIVE-TOOLS.json'] = (json.dumps(tool_material, indent=2, sort_keys=True) + '\n').encode()
    files['RAW-APP-CHECKS.json'] = (json.dumps({
        'provenance': 'independent host PHP replay; not researcher original observation',
        'checks': app_checks}, indent=2, sort_keys=True) + '\n').encode()
    files['UNFINISHED.json'] = (json.dumps({'operator_authored': True, 'items': [{
        'basis': 'harmless local PHP note and candidate',
        'uncertain_condition': 'fresh reviewer causal/control check and protected original capture unavailable',
        'next_check': 'review packet and independently inspect the PHP behavior',
        'status': 'unreviewed'}]}, indent=2, sort_keys=True) + '\n').encode()
    files['PROMPT.txt'] = PACKET_PROMPT.encode()
    files = {name: packet_public_bytes(data, capability, forbidden_paths)
             for name, data in files.items()}
    request = {'version': 1, 'kind': 't02-harmless-php-review', 'claim_version': note_hash,
               'original_observation': {'status': 'unavailable',
                                        'reason': 'protected_capture_source_unreviewed'},
               'source_map': {'ORIGINAL-' + name: name for name in PACKET_SOURCE_NAMES},
               'previous_actual_review': None,
               'files': {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}}
    files['REQUEST.json'] = packet_public_bytes(json.dumps(request, indent=2, sort_keys=True) + '\n',
                                                 capability, forbidden_paths)
    identity = (directory.stat().st_dev, directory.stat().st_ino)
    for name, data in files.items():
        private_snapshot(directory / name, data)
        (directory / name).chmod(0o444)
    directory.chmod(0o555)
    return {'dev': identity[0], 'ino': identity[1],
            'files': {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}


def verify_review_packet(directory, pin):
    try:
        info = directory.stat()
        return (not directory.is_symlink() and (info.st_dev, info.st_ino) ==
                (pin['dev'], pin['ino']) and info.st_mode & 0o222 == 0
                and set(path.name for path in directory.iterdir()) == set(pin['files'])
                and all((directory / name).is_file() and not (directory / name).is_symlink()
                        and (directory / name).stat().st_mode & 0o222 == 0
                        and sha(directory / name) == digest
                        for name, digest in pin['files'].items()))
    except (OSError, KeyError, TypeError):
        return False


def archive_review_packet(directory, archive, pin):
    if not verify_review_packet(directory, pin):
        raise RuntimeError('review_packet_changed_before_archive')
    archive.mkdir(mode=0o700, exist_ok=False)
    for name, digest in pin['files'].items():
        private_snapshot(archive / name, (directory / name).read_bytes())
        if sha(archive / name) != digest:
            raise RuntimeError('review_packet_archive_mismatch')


def validated_runtime_ca(args, parser):
    name = args.live_runtime_ca
    expected = args.live_runtime_ca_sha256
    if not args.live_free:
        if name is not None or expected is not None:
            parser.error('runtime_ca_live_only')
        return None
    if name is None or expected is None:
        parser.error('live_runtime_ca_required')
    if not re.fullmatch(r'[0-9a-f]{64}', expected):
        parser.error('live_runtime_ca_sha256_invalid')
    path = Path(name)
    text = str(path)
    if (not path.is_absolute() or ',' in text
            or any(ord(character) < 32 or ord(character) == 127 for character in text)):
        parser.error('live_runtime_ca_invalid')
    flags = os.O_RDONLY | getattr(os, 'O_CLOEXEC', 0) | getattr(os, 'O_NOFOLLOW', 0) \
        | getattr(os, 'O_NONBLOCK', 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        parser.error('live_runtime_ca_invalid')
    try:
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or before.st_mode & 0o022
                or not 0 < before.st_size <= MAX_RUNTIME_CA_BYTES):
            parser.error('live_runtime_ca_invalid')
        chunks = []
        remaining = MAX_RUNTIME_CA_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b''.join(chunks)
        after = os.fstat(descriptor)
        if (len(data) != before.st_size or before.st_dev != after.st_dev
                or before.st_ino != after.st_ino or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns):
            parser.error('live_runtime_ca_invalid')
    except OSError:
        parser.error('live_runtime_ca_invalid')
    finally:
        os.close(descriptor)
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        parser.error('live_runtime_ca_hash_mismatch')
    try:
        pem = data.decode('ascii')
        private_markers = ('-----BEGIN PRIVATE KEY-----', '-----BEGIN RSA PRIVATE KEY-----',
                           '-----BEGIN EC PRIVATE KEY-----', '-----BEGIN OPENSSH PRIVATE KEY-----',
                           '-----BEGIN ENCRYPTED PRIVATE KEY-----')
        certificate_pattern = re.compile(
            r'-----BEGIN CERTIFICATE-----\r?\n'
            r'(?P<body>(?:[A-Za-z0-9+/=]{1,64}\r?\n)+)'
            r'-----END CERTIFICATE-----')
        certificate_matches = list(certificate_pattern.finditer(pem))
        cursor = 0
        for match in certificate_matches:
            if pem[cursor:match.start()].strip():
                raise ValueError
            base64.b64decode(''.join(match.group('body').splitlines()), validate=True)
            cursor = match.end()
        if (any(marker in pem for marker in private_markers) or not certificate_matches
                or pem[cursor:].strip()):
            raise ValueError
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cadata=pem)
    except (UnicodeDecodeError, ValueError, ssl.SSLError):
        parser.error('live_runtime_ca_invalid')
    return {'bytes': data, 'sha256': actual, 'size': len(data),
            'certificate_count': len(certificate_matches)}


def private_snapshot(path, data):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                         | getattr(os, 'O_CLOEXEC', 0), 0o600)
    try:
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError('runtime_ca_snapshot_write_failed')
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return path


def researcher_trust(live, runtime_ca, offline_ca):
    source = runtime_ca if live else offline_ca
    if source is None:
        raise RuntimeError('live_runtime_ca_unavailable' if live else 'offline_runtime_ca_unavailable')
    destination = RUNTIME_CA_DEST if live else '/fixture/test-ca.pem'
    return {'mounts': ['type=bind,src=' + str(source) + ',dst=' + destination + ',readonly'],
            'env': ['SSL_CERT_FILE=' + destination],
            'container_path': destination}


def reviewed_inputs_match(expected):
    try:
        return all(sha(path) == digest for path, digest in expected.items())
    except OSError:
        return False


def control_pins_match(relay=RELAY, relay_sha=RELAY_SHA):
    try:
        return all(sha(path) == expected for path, expected in
                   (*CONTROL_SHA.items(), (relay, relay_sha)))
    except OSError:
        return False


def cloud_inputs(args, parser):
    names = ('cloud_platform', 'cloud_image_id', 'cloud_relay', 'cloud_relay_sha256',
             'cloud_internal_subnet', 'cloud_external_subnet', 'cloud_listen_address', 'cloud_relay_peer',
             'cloud_upstream_route')
    values = [getattr(args, name) for name in names]
    if not any(value is not None for value in values):
        if args.live_free:
            parser.error('live_requires_observed_cloud_inputs')
        return {'platform': 'linux/arm64', 'image_id': IMAGE_ID, 'relay': RELAY,
                'relay_sha': RELAY_SHA, 'listen': '127.0.0.1', 'peer': None,
                'internal_subnet': None, 'external_subnet': None,
                'upstream_route': 'direct', 'cloud': False}
    if any(value is None for value in values):
        parser.error('incomplete_cloud_inputs')
    platform, image_id, relay_name, relay_sha, internal_subnet, subnet, listen, peer, route = values
    if not re.fullmatch(r'linux/(amd64|arm64)', platform):
        parser.error('invalid_cloud_platform')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', image_id):
        parser.error('invalid_cloud_image_id')
    if not re.fullmatch(r'[0-9a-f]{64}', relay_sha) or relay_sha == RELAY_SHA:
        parser.error('invalid_or_historical_cloud_relay_sha256')
    relay = Path(relay_name)
    relay = relay if relay.is_absolute() else ROOT / relay
    if relay.is_symlink():
        parser.error('cloud_relay_symlink')
    try:
        relay = relay.resolve(strict=True)
        relay.relative_to(CONTROLS.resolve())
        mode = relay.stat().st_mode
        if not stat.S_ISREG(mode) or not mode & 0o111 or ',' in str(relay) or sha(relay) != relay_sha:
            parser.error('invalid_cloud_relay')
        with relay.open('rb') as stream:
            header = stream.read(20)
    except (OSError, ValueError):
        parser.error('invalid_cloud_relay')
    if len(header) != 20 or header[:6] != b'\x7fELF\x02\x01' or int.from_bytes(header[18:20], 'little') != {
            'linux/amd64': 62, 'linux/arm64': 183}[platform]:
        parser.error('cloud_relay_platform_mismatch')
    if not control_pins_match(relay, relay_sha):
        parser.error('control_pin_mismatch')
    controls = runpy.run_path(str(CONNECT))
    try:
        listen = controls['private_ipv4'](listen)
        peer = controls['private_ipv4'](peer)
        network = ipaddress.IPv4Network(subnet, strict=True)
        internal_network = ipaddress.IPv4Network(internal_subnet, strict=True)
        if (not any(network.subnet_of(private) for private in controls['PRIVATE_IPV4'])
                or network.num_addresses < 32 or listen == peer
                or ipaddress.IPv4Address(listen) not in network
                or ipaddress.IPv4Address(peer) not in network
                or any(ipaddress.IPv4Address(value) in
                       (network.network_address, network.broadcast_address)
                       for value in (listen, peer))):
            raise ValueError('cloud_external_subnet_invalid')
        if (not any(internal_network.subnet_of(private) for private in controls['PRIVATE_IPV4'])
                or internal_network.num_addresses < 32 or internal_network.overlaps(network)):
            raise ValueError('cloud_internal_subnet_invalid')
        if route in ('HTTP_PROXY', 'HTTPS_PROXY'):
            controls['proxy_from_environment'](route)
    except (ValueError, UnicodeError):
        parser.error('invalid_cloud_route_or_proxy')
    if route not in ('HTTP_PROXY', 'HTTPS_PROXY'):
        parser.error('invalid_cloud_upstream_route')
    if not control_pins_match(relay, relay_sha):
        parser.error('control_pin_changed_before_output')
    return {'platform': platform, 'image_id': image_id, 'relay': relay,
            'relay_sha': relay_sha, 'listen': listen, 'peer': peer,
            'internal_subnet': str(internal_network), 'external_subnet': str(network),
            'upstream_route': route, 'cloud': True}


def created_matches(info, identifier, mounts, env, image_id=IMAGE_ID):
    if not isinstance(info, dict) or info.get('Id') != identifier or info.get('Image') != image_id:
        return False
    if info.get('Config', {}).get('Image') != image_id:
        return False
    if info.get('State', {}).get('Status') != 'created':
        return False
    expected_mounts = set()
    for item in mounts:
        parts = item.split(',')
        fields = dict(part.split('=', 1) for part in parts if '=' in part)
        if fields.get('type') != 'bind' or not fields.get('src') or not fields.get('dst'):
            return False
        if any(part not in ('readonly', 'type=bind') and not part.startswith(('src=', 'dst='))
               for part in parts):
            return False
        expected_mounts.add((fields['src'], fields['dst'], 'readonly' not in parts))
    actual_mounts = info.get('Mounts')
    if not isinstance(actual_mounts, list) or any(not isinstance(item, dict) for item in actual_mounts):
        return False
    if len(actual_mounts) != len(expected_mounts) or {
            (item.get('Source'), item.get('Destination'), item.get('RW')) for item in actual_mounts
            } != expected_mounts:
        return False
    requested_pairs = [item.split('=', 1) for item in env]
    if any(len(item) != 2 for item in requested_pairs) or len({name for name, _ in requested_pairs}) != len(env):
        return False
    requested = dict(requested_pairs)
    actual = info.get('Config', {}).get('Env')
    if not isinstance(actual, list) or any(not isinstance(item, str) or '=' not in item for item in actual):
        return False
    actual_pairs = [item.split('=', 1) for item in actual]
    if len({name for name, _ in actual_pairs}) != len(actual_pairs):
        return False
    effective = dict(actual_pairs)
    if any(effective.get(name) != value for name, value in requested.items()):
        return False
    critical = lambda name: (name in TRUST_ENV or 'PROXY' in name.upper() or any(word in name.upper() for word in
        ('TOKEN', 'SECRET', 'PASSWORD', 'API_KEY', 'ACCESS_KEY', 'PRIVATE_KEY',
         'AUTHORIZATION', 'CREDENTIAL')))
    return all(name in requested for name in effective if critical(name))


def idle_top(result):
    return result.returncode == 0 and 'opencode' not in result.stdout.lower()


def activate_controls(source_root, relay=RELAY, relay_sha=RELAY_SHA):
    if any(name in sys.modules for name in ('docker_session_runtime', 'producer_stop', 'native_run')):
        raise RuntimeError('control_module_preloaded')
    if any(sha(source_root / path.relative_to(ROOT)) != expected
           for path, expected in (*CONTROL_SHA.items(), (relay, relay_sha))):
        raise RuntimeError('archived_control_pin_mismatch')
    paths = {'docker_session_runtime': source_root / DOCKER_RUNTIME.relative_to(ROOT),
             'producer_stop': source_root / PRODUCER.relative_to(ROOT),
             'native_run': source_root / NATIVE.relative_to(ROOT)}
    loaded = {}
    for name, path in paths.items():
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise RuntimeError('archived_control_import_unavailable')
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        if Path(module.__file__).resolve() != path.resolve():
            raise RuntimeError('archived_control_origin_mismatch')
        loaded[name] = module
    runtime, producer, native = (loaded[name] for name in
                                 ('docker_session_runtime', 'producer_stop', 'native_run'))
    connect_path = source_root / CONNECT.relative_to(ROOT)
    if Path(native.NativeRun('unused', 'unused', 1, []).argv[1]).resolve() != connect_path.resolve():
        raise RuntimeError('archived_connect_origin_mismatch')
    globals().update(DockerRuntimeError=runtime.DockerRuntimeError,
                     _inspect_one=runtime._inspect_one, _is_absent=runtime._is_absent,
                     NativeRun=native.NativeRun, RunStopped=native.RunStopped,
                     snapshot_native_run=native.snapshot, active_native_run=native.active,
                     dispatch_guard=native.dispatch_guard, request_stop=native.request_stop,
                     binding=producer.binding)
    return {name: str(path.resolve()) for name, path in paths.items()} | {'v2_connect': str(connect_path.resolve())}


def command(*argv, timeout=30):
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)


def safe_label(value):
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{0,63}', value) else 'unclassified'


def public_error(error):
    detail = str(error)
    return {'type': type(error).__name__,
            'code': detail if re.fullmatch(r'[a-z][a-z0-9_]{0,79}', detail) else 'details_omitted'}


def native_clean(row):
    return not row['error_types'] and not row['top_level_error_types'] and 'error' not in row['event_types']


def safe_number(value):
    return value if type(value) in (int, float) and abs(value) <= 10**15 and math.isfinite(value) else None


def safe_tokens(value):
    if not isinstance(value, dict):
        return None
    cache = value.get('cache') if isinstance(value.get('cache'), dict) else {}
    return {**{key: safe_number(value.get(key)) for key in ('input', 'output', 'reasoning')},
            'cache': {key: safe_number(cache.get(key)) for key in ('read', 'write')}}


def token_field_sums_or_unknown(rows):
    totals = {}
    for key in ('input', 'output', 'reasoning', 'cache_read', 'cache_write'):
        values = []
        for row in rows:
            tokens = row.get('tokens')
            if not isinstance(tokens, dict):
                values.append(None)
            elif key.startswith('cache_'):
                cache = tokens.get('cache')
                values.append(cache.get(key.removeprefix('cache_')) if isinstance(cache, dict) else None)
            else:
                values.append(tokens.get(key))
        totals[key] = sum(values) if values and all(safe_number(v) is not None for v in values) else None
    return totals


def owned_health_count(responder):
    return responder.health_rows if responder is not None else None


def provider_state(database, responder):
    with sqlite3.connect(database) as db:
        charged = db.execute('SELECT bytes FROM pool').fetchone()[0]
        tunnels = db.execute('SELECT id,phase,uploaded,downloaded FROM tunnels ORDER BY id').fetchall()
        events = db.execute('SELECT count(*) FROM events').fetchone()[0]
        closed_events = db.execute("SELECT count(*) FROM events WHERE kind='closed'").fetchone()[0]
    return {'events': events, 'closed_events': closed_events,
            'tunnels': tunnels, 'charged_bytes': charged,
            'uploaded_bytes': sum(row[2] for row in tunnels),
            'downloaded_bytes': sum(row[3] for row in tunnels),
            'owned_responses': len(responder.rows) if responder is not None else None,
            'owned_health': owned_health_count(responder)}


def inspect(kind, identifier):
    binary = shutil.which('docker')
    if not binary:
        raise RuntimeError('docker_inspect_unavailable')
    binary = Path(binary).resolve(strict=True)
    try:
        info = _inspect_one(binary, kind, identifier)
    except DockerRuntimeError as error:
        if error.code == 'docker_command_failed' and _is_absent(binary, kind, identifier):
            return None
        raise
    if info.get('Id') != identifier:
        raise RuntimeError('docker_inspect_identity_mismatch')
    return info


def cleanup_owned(resources, nonce, docker):
    rows = []
    for kind, identifier in reversed(resources):
        try:
            state = inspect(kind, identifier)
            labels = (state['Config']['Labels'] if kind == 'container' else state['Labels']) if state else None
        except Exception as error:
            rows.append({'kind': kind, 'id': identifier, 'absent': False,
                         'error': 'inspect_unverifiable', 'error_type': type(error).__name__})
            continue
        if state is None:
            rows.append({'kind': kind, 'id': identifier, 'absent': True})
            continue
        if not isinstance(labels, dict):
            rows.append({'kind': kind, 'id': identifier, 'absent': False,
                         'error': 'inspect_unverifiable'})
            continue
        if labels.get(LABEL) != nonce:
            rows.append({'kind': kind, 'id': identifier, 'absent': False,
                         'error': 'ownership_mismatch'})
            continue
        try:
            removed = docker(kind, 'rm', '--force', '--volumes', identifier) if kind == 'container' \
                else docker(kind, 'rm', identifier)
            if removed.returncode:
                rows.append({'kind': kind, 'id': identifier, 'absent': False,
                             'error': 'remove_failed'})
                continue
            rows.append({'kind': kind, 'id': identifier,
                         'absent': inspect(kind, identifier) is None})
        except Exception as error:
            rows.append({'kind': kind, 'id': identifier, 'absent': False,
                         'error': 'remove_or_post_inspect_unverifiable',
                         'error_type': type(error).__name__})
    return rows


def finish_owned(native, resources, nonce, docker, work, prior_stop=None, responder=None):
    result = {}
    if prior_stop is not None:
        result['native_stop'] = prior_stop
    elif native:
        try:
            result['native_stop'] = native.close()
        except Exception as error:
            result['native_stop_error'] = public_error(error)
    if responder:
        try:
            responder.shutdown()
            responder.server_close()
        except Exception as error:
            result['responder_stop_error'] = public_error(error)
    try:
        result['cleanup'] = cleanup_owned(resources, nonce, docker)
        result['cleanup_complete'] = len(result['cleanup']) == len(resources) and all(
            item.get('absent') for item in result['cleanup'])
    except Exception as error:
        result['cleanup'], result['cleanup_complete'] = [], False
        result['cleanup_error'] = public_error(error)
    if (work is not None and result['cleanup_complete']
            and ((native is None and prior_stop is None)
                 or (result.get('native_stop') or {}).get('status')
                 in ('stopped', 'closed_before_activation', 'not_started'))):
        try:
            shutil.rmtree(work)
        except OSError as error:
            result['temporary_cleanup_error'] = public_error(error)
    result['temporary_secret_files_removed'] = work is not None and not work.exists()
    if work is not None and not result['temporary_secret_files_removed']:
        result['temporary_workspace_unresolved'] = str(work)
    return result


def summarize_native(stage, returncode, stdout, stderr):
    events = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    parts = [event['part'] for event in events if isinstance(event.get('part'), dict)]
    tools, checks_seen = [], set()
    names = {'read', 'glob', 'grep', 'edit', 'write', 'shell', 'patch', 'question',
             'skill', 'subagent', 'webfetch', 'websearch'}
    statuses = {'completed', 'running', 'pending', 'error', 'failed'}
    for part in parts:
        if part.get('type') != 'tool':
            continue
        name = part.get('tool') if part.get('tool') in names else 'other'
        state = part.get('state') if isinstance(part.get('state'), dict) else {}
        status = state.get('status') if state.get('status') in statuses else 'other'
        tools.append({'name': name, 'status': status})
        if name == 'shell' and status == 'completed':
            command_text = (state.get('input') or {}).get('command') if isinstance(state.get('input'), dict) else None
            if isinstance(command_text, str):
                exact = command_text.strip()
                if exact in PHP_CHECKS:
                    checks_seen.add(exact)
                elif exact in (' && '.join(PHP_CHECKS), SHELL):
                    checks_seen.update(PHP_CHECKS)
    event_names = {'step_finish', 'step_start', 'text', 'tool_use', 'error'}
    part_names = {'step-finish', 'step-start', 'text', 'tool', 'error', 'usage'}
    return {'stage': stage, 'exit_code': returncode,
            'session_ids': sorted({event['sessionID'] for event in events
                                   if isinstance(event.get('sessionID'), str) and
                                   re.fullmatch(r'ses_[A-Za-z0-9]{1,64}', event['sessionID'])}),
            'event_types': sorted({event.get('type') if event.get('type') in event_names else 'other'
                                   for event in events}),
            'part_types': sorted({part.get('type') if part.get('type') in part_names else 'other'
                                  for part in parts}),
            'error_types': ['native_part_error'] if any(part.get('error') for part in parts) else [],
            'top_level_error_types': ['native_event_error'] if any(
                event.get('type') == 'error' or event.get('error') for event in events) else [],
            'text_event_count': sum(part.get('type') == 'text' for part in parts),
            'tools': tools, 'shell_checks_observed': sorted(checks_seen),
            'stdout_sha256': hashlib.sha256(stdout.encode()).hexdigest(),
            'stderr_sha256': hashlib.sha256(stderr.encode()).hexdigest()}


def summarize_php(argv, returncode, stdout, stderr):
    if stdout not in ('', 'before\n', 'after\n', 'check passed\n') or \
            stderr not in ('', 'message() must return after\n'):
        raise RuntimeError('unexpected_php_output')
    return {'argv': argv, 'exit': returncode,
            'stdout': stdout, 'stderr': stderr,
            'stdout_class': ('before' if stdout == 'before\n' else
                             'after' if stdout == 'after\n' else
                             'check_passed' if stdout == 'check passed\n' else 'other'),
            'stderr_class': ('empty' if stderr == '' else
                             'expected_baseline_failure' if stderr == 'message() must return after\n'
                             else 'other'),
            'stdout_sha256': hashlib.sha256(stdout.encode()).hexdigest(),
            'stderr_sha256': hashlib.sha256(stderr.encode()).hexdigest()}


class OwnedTLS(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.path != '/health':
            self.send_error(404)
            return
        self.server.health_rows += 1
        self.send_response(200)
        self.send_header('Content-Length', '6')
        self.end_headers()
        self.wfile.write(b'ready\n')

    def do_POST(self):
        if self.path.split('?')[0] != OWNED_PATH:
            self.send_error(404)
            return
        length = int(self.headers.get('Content-Length', '0'))
        if not 0 < length <= 2 * 1024 * 1024:
            self.send_error(413)
            return
        try:
            body = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeDecodeError):
            self.send_error(400)
            return
        tools = body.get('tools') if isinstance(body, dict) else None
        names = [item.get('function', {}).get('name') for item in tools or [] if isinstance(item, dict)]
        self.server.rows.append({'role': self.server.current_role,
            'path': self.path.split('?')[0], 'model': body.get('model'),
            'stream': body.get('stream'), 'tool_names': names,
            'authorization_present': self.headers.get('Authorization') is not None})
        item = {'id': 'owned-managed', 'object': 'chat.completion.chunk', 'created': 1,
                'model': 'deepseek-v4.1-flash-free'}
        if 'shell' in names and not self.server.issued:
            tool = next(x for x in tools if x.get('function', {}).get('name') == 'shell')
            required = tool.get('function', {}).get('parameters', {}).get('required', [])
            arguments = {'command': SHELL, 'description': 'Inspect and check harmless PHP files',
                         'workdir': '/workspace/project', 'timeout': 120000}
            self.server.required = required
            if not set(required) <= set(arguments):
                self.send_error(422)
                return
            self.server.issued = True
            delta = {'role': 'assistant', 'tool_calls': [{'index': 0, 'id': 'call_owned_php',
                'type': 'function', 'function': {'name': 'shell',
                'arguments': json.dumps({key: value for key, value in arguments.items()
                                         if key in set(required) | {'command', 'description'}})}}]}
            finish = 'tool_calls'
        else:
            delta, finish = {'role': 'assistant', 'content': 'Owned offline response complete.'}, 'stop'
        chunks = [item | {'choices': [{'index': 0, 'delta': delta, 'finish_reason': None}]},
                  item | {'choices': [{'index': 0, 'delta': {}, 'finish_reason': finish}],
                          'usage': {'prompt_tokens': 5, 'completion_tokens': 1, 'total_tokens': 6}}]
        raw = (''.join('data: ' + json.dumps(chunk) + '\n\n' for chunk in chunks)
               + 'data: [DONE]\n\n').encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--live-free', action='store_true', help='use official keyless free-model route once')
    parser.add_argument('--cloud-platform')
    parser.add_argument('--cloud-image-id')
    parser.add_argument('--cloud-relay')
    parser.add_argument('--cloud-relay-sha256')
    parser.add_argument('--cloud-internal-subnet')
    parser.add_argument('--cloud-external-subnet')
    parser.add_argument('--cloud-listen-address')
    parser.add_argument('--cloud-relay-peer')
    parser.add_argument('--cloud-upstream-route')
    parser.add_argument('--live-runtime-ca')
    parser.add_argument('--live-runtime-ca-sha256')
    args = parser.parse_args()
    live = args.live_free
    config = LIVE_CONFIG if live else CONFIG
    selected = cloud_inputs(args, parser)
    runtime_ca = validated_runtime_ca(args, parser)
    if live:
        parser.error('cloud_live_route_not_qualified')
    if live and not reviewed_inputs_match(LIVE_INPUT_SHA):
        parser.error('live_input_pin_mismatch')
    if selected['cloud'] and not reviewed_inputs_match(CLOUD_OWNED_INPUT_SHA):
        parser.error('cloud_owned_input_pin_mismatch')
    if not control_pins_match(selected['relay'], selected['relay_sha']):
        parser.error('control_pin_mismatch')
    output = args.output.resolve()
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    nonce = uuid.uuid4().hex
    qualification_docs = ((LIVE_CHECKS, LIVE_PREPARATION_CHECKS, REVIEW_CHECKS) if live
                          else (CHECKS, REVIEW_CHECKS))
    pin_files = (Path(__file__), CONNECT, NATIVE, PRODUCER, DOCKER_RUNTIME, selected['relay'], config,
                 *qualification_docs,
                 MOCK_PHP, OBSERVER / 'server.js', OBSERVER / 'package.json', *FIXTURE)
    source_root = output / 'source'
    for path in pin_files:
        target = source_root / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    archived_inputs = live or selected['cloud']

    def input_source(path):
        return source_root / path.relative_to(ROOT) if archived_inputs else path

    config_mount = input_source(config)
    observer_mount = input_source(OBSERVER)
    mock_mount = input_source(MOCK_PHP)
    relay_mount = source_root / selected['relay'].relative_to(ROOT)
    report = {'classification': ('official V2 keyless free-model managed CONNECT; harmless PHP'
               if live else 'owned TLS/native managed CONNECT offline E2E; zero provider calls'),
              'status': 'running', 'checks': [], 'resources': [], 'cleanup': [], 'native_runs': [],
              'usage_provenance': ('native delayed researcher-writable; provider billing unavailable'
                                   if live else 'synthetic owned response'),
              'selected_boundary': {key: selected[key] for key in
                                    ('cloud', 'platform', 'image_id', 'relay_sha', 'internal_subnet', 'external_subnet',
                                     'listen', 'peer', 'upstream_route')},
              'source_sha256': {str(p.relative_to(ROOT)): sha(p) for p in pin_files}}
    if runtime_ca is not None:
        report['runtime_trust'] = {'sha256': runtime_ca['sha256'], 'bytes': runtime_ca['size'],
                                   'certificate_count': runtime_ca['certificate_count'],
                                   'container_path': RUNTIME_CA_DEST, 'mount_read_only': True}
    resources = []
    native = None
    responder = None
    work = None
    first_native_stdout = None
    reviewer_native_stdout = None

    def save():
        (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')

    def check(name, passed):
        report['checks'].append({'name': name, 'pass': bool(passed)})
        save()
        if not passed:
            raise AssertionError(name)

    def docker(*argv, timeout=30):
        return command('docker', *argv, timeout=timeout)

    def connect_probe(identifier, mode='valid'):
        if mode not in ('valid', 'alternate', 'wrong'):
            raise ValueError('invalid probe mode')
        code = ('$u=parse_url(getenv("HTTPS_PROXY"));'
            '$s=stream_socket_client("tcp://".$u["host"].":".$u["port"],$e,$m,5);'
            'if(!$s)exit(2);stream_set_timeout($s,5);'
            '$target=$argv[1]==="alternate"?"example.com:443":"opencode.ai:443";'
            '$a=base64_encode("run:".($argv[1]==="wrong"?"invalid-local-capability":$u["pass"]));'
            'fwrite($s,"CONNECT ".$target." HTTP/1.1\\r\\nHost: ".$target."\\r\\nProxy-Authorization: Basic ".$a."\\r\\n\\r\\n");'
            'echo fgets($s);fclose($s);')
        result = docker('container', 'exec', identifier, 'php', '-r', code, mode)
        return {'exit_code': result.returncode, 'status_line': result.stdout.strip()}

    def own(kind, identifier, role):
        resources.append((kind, identifier))
        report['resources'].append({'kind': kind, 'id': identifier, 'role': role})
        save()

    def created(role, network, mounts=(), env=(), entry='sh', args=('-c', 'exec sleep 600'), ip=None):
        argv = ['container', 'create', '--pull', 'never', '--platform', selected['platform'],
                '--network', network, '--read-only', '--restart', 'no', '--log-driver', 'none',
                '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges=true',
                '--user', f'{os.getuid()}:{os.getgid()}', '--memory', '1g', '--cpus', '1',
                '--pids-limit', '64', '--tmpfs', '/tmp:rw,nosuid,nodev,size=128m',
                '--label', LABEL + '=' + nonce,
                '--label', 'io.llm-redteam-harness.runtime=docker-session-v1',
                '--label', 'io.llm-redteam-harness.session-nonce=' + nonce]
        for item in mounts:
            argv += ['--mount', item]
        pairs = [item.split('=', 1) for item in env]
        if (any(len(pair) != 2 or not pair[0] for pair in pairs)
                or len({pair[0] for pair in pairs}) != len(pairs)):
            raise RuntimeError('invalid_requested_container_env')
        names = {pair[0] for pair in pairs}
        requested_env = [name + '=' for name in DOCKER_PROXY_ENV + CLEARABLE_TRUST_ENV
                         if name not in names] + list(env)
        for item in requested_env:
            argv += ['--env', item]
        if ip is not None:
            argv += ['--ip', ip]
        if role not in ('relay', 'external-receiver'):
            argv += ['--workdir', '/workspace/project', '--dns', '127.0.0.1']
        result = docker(*argv, '--entrypoint', entry, selected['image_id'], *args)
        if result.returncode:
            raise RuntimeError(role + ' create: ' + result.stderr[:160])
        identifier = result.stdout.strip()
        own('container', identifier, role)
        check(role + ' created immutable image and exact mounts/env',
              created_matches(inspect('container', identifier), identifier, mounts, requested_env,
                              selected['image_id']))
        return identifier

    def api(identifier, *parts):
        result = docker('container', 'exec', '-w', '/workspace/project', identifier,
                        'opencode', 'api', '--standalone', *parts, timeout=60)
        if result.returncode:
            raise RuntimeError('native_api_' + safe_label(parts[0]).replace('.', '_') + '_failed')
        return json.loads(result.stdout)

    def native_call(identifier, stage, session, prompt):
        nonlocal first_native_stdout, reviewer_native_stdout
        if responder:
            responder.current_role = stage
        before = ledger_totals() if live else None
        result = docker('container', 'exec', '-w', '/workspace/project', identifier,
                        'opencode', 'run', '--standalone', '--agent', 'build', '--model', MODEL,
                        '--format', 'json', '--session', session, prompt, timeout=180)
        if responder:
            responder.current_role = None
        if stage == 'first':
            first_native_stdout = result.stdout
        elif stage == 'reviewer':
            reviewer_native_stdout = result.stdout
        row = summarize_native(stage, result.returncode, result.stdout, result.stderr)
        if live:
            row['pool_before'] = before
            row['pool_after'] = ledger_totals()
        (output / (stage + '.trace.json')).write_text(json.dumps(row, indent=2) + '\n')
        report['native_runs'].append(row)
        save()
        return row

    def usage(identifier, session):
        item = api(identifier, 'session.get', '--param', 'sessionID=' + session).get('data', {})
        return {'id': item.get('id'), 'parentID': item.get('parentID'),
                'cost': safe_number(item.get('cost')), 'tokens': safe_tokens(item.get('tokens'))}

    def all_native_usage(identifier, stage):
        sessions, cursor, seen = [], None, set()
        for session_page in range(20):
            params = ['session.list', '--param', 'limit=100']
            params += ['--param', 'cursor=' + cursor] if cursor else ['--param', 'order=asc']
            response = api(identifier, *params)
            items = response.get('items', response.get('data'))
            if not isinstance(items, list):
                raise RuntimeError('native session page missing items')
            sessions += items
            next_cursor = (response.get('cursor') or {}).get('next')
            if not next_cursor:
                break
            if next_cursor in seen:
                raise RuntimeError('native session cursor repeated')
            seen.add(next_cursor)
            cursor = next_cursor
        else:
            raise RuntimeError('native session pagination exceeded 20 pages')
        ids = [item['id'] for item in sessions]
        if len(ids) != len(set(ids)) or any(not isinstance(sid, str) or
            not re.fullmatch(r'ses_[A-Za-z0-9]{1,64}', sid) for sid in ids):
            raise RuntimeError('native_session_ids_invalid')
        rows = []
        for sid in ids:
            info = api(identifier, 'session.get', '--param', 'sessionID=' + sid)['data']
            messages, cursor, seen = [], None, set()
            for message_page in range(20):
                params = ['session.message.list', '--param', 'sessionID=' + sid,
                          '--param', 'limit=100']
                params += ['--param', 'cursor=' + cursor] if cursor else ['--param', 'order=asc']
                response = api(identifier, *params)
                if not isinstance(response.get('data'), list):
                    raise RuntimeError('native message page missing data list')
                for message in response['data']:
                    item = message.get('info', message)
                    if item.get('type') == 'assistant':
                        mid = item.get('id')
                        if not isinstance(mid, str) or not re.fullmatch(r'msg_[A-Za-z0-9]{1,64}', mid):
                            raise RuntimeError('native_message_id_invalid')
                        finish = item.get('finish')
                        retry = item.get('retry') if isinstance(item.get('retry'), dict) else {}
                        messages.append({'id': mid, 'cost': safe_number(item.get('cost')),
                                         'tokens': safe_tokens(item.get('tokens')),
                                         'finish': finish if isinstance(finish, str) and finish in
                                             {'stop', 'tool_calls', 'length', 'content_filter'} else 'other',
                                         'retry_attempt': safe_number(retry.get('attempt')),
                                         'had_error': bool(item.get('error'))})
                next_cursor = (response.get('cursor') or {}).get('next')
                if not next_cursor:
                    break
                if next_cursor in seen:
                    raise RuntimeError('native message cursor repeated')
                seen.add(next_cursor)
                cursor = next_cursor
            else:
                raise RuntimeError('native message pagination exceeded 20 pages')
            parent = info.get('parentID')
            if parent is not None and (not isinstance(parent, str) or not re.fullmatch(r'ses_[A-Za-z0-9]{1,64}', parent)):
                raise RuntimeError('native_parent_id_invalid')
            rows.append({'id': sid, 'parentID': parent, 'cost': safe_number(info.get('cost')),
                         'tokens': safe_tokens(info.get('tokens')), 'message_pages': message_page + 1,
                         'assistant_usage': messages})
        snapshot = {'stage': stage, 'session_pages': session_page + 1, 'sessions': rows}
        report.setdefault('all_native_usage', []).append(snapshot)
        save()
        return snapshot

    def ledger_totals():
        with sqlite3.connect(output / 'provider/tunnel.sqlite3') as db:
            return {'charged_bytes': db.execute('SELECT bytes FROM pool').fetchone()[0],
                    'tunnels': db.execute('SELECT count(*) FROM tunnels').fetchone()[0]}

    def authority_snapshot():
        run = snapshot_native_run(output / 'run')
        with sqlite3.connect(output / 'provider/tunnel.sqlite3') as db:
            config_text, created, charged = db.execute('SELECT config,created,bytes FROM pool').fetchone()
            tunnels = db.execute('SELECT count(*) FROM tunnels').fetchone()[0]
        config_data = json.loads(config_text)
        return {'run_identity': {key: run[key] for key in
                                 ('manifest_sha256', 'nonce', 'ids', 'deadline_monotonic', 'created_monotonic')},
                'pool_config': config_text, 'pool_created': created,
                'pool_deadline': created + config_data['duration'],
                'max_connections': config_data['max_connections'],
                'max_bytes': config_data['max_bytes'],
                'charged_bytes': charged, 'tunnels': tunnels,
                'active': active_native_run(output / 'run')}

    def settled_surface(identifier):
        server = subprocess.Popen(['docker', 'container', 'exec', '-w', '/workspace/project',
            identifier, 'sh', '-c', 'echo $$; exec opencode serve --hostname 127.0.0.1 --port 4096'],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        pid = None
        try:
            ready, _, _ = select.select([server.stdout], [], [], 10)
            if not ready:
                raise RuntimeError('settled surface process did not start')
            pid = int(server.stdout.readline().strip())
            password = None
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline and not password:
                ready, _, _ = select.select([server.stdout], [], [], 1)
                if ready:
                    line = server.stdout.readline()
                    found = re.search(r'server password ([^\s]+)', line)
                    if found:
                        password = found.group(1)
                if server.poll() is not None:
                    break
            if not password:
                raise RuntimeError('settled surface server unavailable')
            header = 'Authorization: Basic ' + base64.b64encode(
                ('opencode:' + password).encode()).decode()

            def get(path):
                reply = docker('container', 'exec', identifier, 'wget', '-qO-', '--header', header,
                    'http://127.0.0.1:4096/api/' + path)
                if reply.returncode:
                    raise RuntimeError('settled API route: ' + path)
                parsed = json.loads(reply.stdout)
                return parsed.get('data', parsed) if isinstance(parsed, dict) else parsed

            for _ in range(50):
                agents, plugins = get('agent'), get('plugin')
                if agents and plugins and len(agents[0].get('permissions', [])) >= 12:
                    break
                time.sleep(.1)
            config_rows = get('config')
            document = next(x['info'] for x in config_rows if x.get('type') == 'document')
            skills, mcp, references, commands = (get(path) for path in ('skill', 'mcp', 'reference', 'command'))
            plugin_ids = sorted(p.get('id') for p in plugins)
            result = {'config_sources': [{'type': row.get('type'), 'path': row.get('path')}
                                       for row in config_rows],
                'effective_config': {key: document.get(key) for key in
                    ('model', 'fallback', 'permissions', 'policies', 'plugins', 'mcp', 'websearch')},
                'agents': [{'id': a.get('id'), 'mode': a.get('mode'),
                            'permissions': a.get('permissions')} for a in agents],
                'plugin_ids': plugin_ids,
                'registered_tool_names': sorted(x.removeprefix('opencode.tool.') for x in plugin_ids
                                                if x.startswith('opencode.tool.')),
                'skill_ids': sorted(x.get('id') for x in skills), 'mcp_count': len(mcp),
                'reference_count': len(references), 'command_count': len(commands)}
            return result
        finally:
            if pid is not None:
                docker('container', 'exec', identifier, 'kill', '-TERM', str(pid))
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
            server.stdout.close()

    def host_php(folder):
        made = created('host-check', 'none',
                       ['type=bind,src=' + str(folder) + ',dst=/workspace/project,readonly'])
        check('host-owned network-none checker started', docker('container', 'start', made).returncode == 0)
        rows = []
        for args in (('php', 'index.php'), ('php', 'check.php')):
            result = docker('container', 'exec', '-w', '/workspace/project', made, *args)
            rows.append(summarize_php(args, result.returncode, result.stdout, result.stderr))
        removed = docker('container', 'rm', '--force', '--volumes', made)
        check('host checker removed by exact ID', removed.returncode == 0 and inspect('container', made) is None)
        return rows

    save()
    try:
        report['active_control_origins'] = activate_controls(source_root, selected['relay'],
                                                              selected['relay_sha'])
        check('archived T05 controls and relay active',
              all(Path(path).is_relative_to(source_root.resolve())
                  for path in report['active_control_origins'].values())
              and sha(relay_mount) == selected['relay_sha'])
        if live:
            check('archived live inputs match fixed reviewed pins',
                  all(sha(source_root / path.relative_to(ROOT)) == expected
                      for path, expected in LIVE_INPUT_SHA.items()))
        if selected['cloud']:
            check('archived cloud owned inputs match fixed reviewed pins',
                  all(sha(input_source(path)) == expected
                      for path, expected in CLOUD_OWNED_INPUT_SHA.items()))
            check('cloud owned mounts and fixture sources select archive',
                  all(input_source(path).is_relative_to(source_root)
                      for path in (config, OBSERVER, MOCK_PHP, *FIXTURE)))
        if selected['cloud']:
            local_daemon = command('docker', '--host=unix:///var/run/docker.sock',
                                   'info', '--format', '{{.ID}}')
            inherited_daemon = docker('info', '--format', '{{.ID}}')
            check('inherited Docker commands use intended local daemon',
                  local_daemon.returncode == 0 and inherited_daemon.returncode == 0
                  and bool(local_daemon.stdout.strip())
                  and local_daemon.stdout.strip() == inherited_daemon.stdout.strip())
        image = docker('image', 'inspect', selected['image_id'] if selected['cloud'] else IMAGE)
        check('exact derived V2/PHP image', image.returncode == 0 and
              json.loads(image.stdout)[0]['Id'] == selected['image_id'] and
              json.loads(image.stdout)[0]['Os'] == 'linux' and
              json.loads(image.stdout)[0]['Architecture'] == selected['platform'].split('/')[1])
        # Keep mounts and stop controls until NativeRun closes and owned IDs are absent.
        with contextlib.nullcontext(tempfile.mkdtemp(prefix='nq-v2-managed-owned-')) as temporary:
            work = Path(temporary).resolve()
            certs = work / 'certs'
            certs.mkdir(mode=0o700)
            ca_pem = None
            runtime_ca_snapshot = None
            if live:
                runtime_ca_snapshot = private_snapshot(certs / 'runtime-ca.pem', runtime_ca['bytes'])
                check('runtime CA private snapshot matches validated bytes',
                      sha(runtime_ca_snapshot) == runtime_ca['sha256']
                      and runtime_ca_snapshot.stat().st_mode & 0o077 == 0)
            else:
                ca_key, ca_pem = certs / 'ca.key', certs / 'ca.pem'
                server_key, server_csr, server_pem = certs / 'server.key', certs / 'server.csr', certs / 'server.pem'
                extension = certs / 'server.ext'
                extension.write_text('subjectAltName=DNS:opencode.ai\nextendedKeyUsage=serverAuth\n')
                commands = [
                    ('req', '-x509', '-newkey', 'rsa:2048', '-noenc', '-days', '1', '-sha256',
                     '-subj', '/CN=T02 offline CA', '-addext', 'basicConstraints=critical,CA:TRUE',
                     '-keyout', str(ca_key), '-out', str(ca_pem)),
                    ('req', '-newkey', 'rsa:2048', '-noenc', '-sha256', '-subj', '/CN=opencode.ai',
                     '-keyout', str(server_key), '-out', str(server_csr)),
                    ('x509', '-req', '-in', str(server_csr), '-CA', str(ca_pem), '-CAkey', str(ca_key),
                     '-CAcreateserial', '-days', '1', '-sha256', '-extfile', str(extension), '-out', str(server_pem))]
                check('ephemeral local TLS CA and leaf generated', all(
                      command('openssl', *cert).returncode == 0 for cert in commands))
                ca_key.chmod(0o600)
                server_key.chmod(0o600)
                check('leaf verifies for fixed authority',
                      command('openssl', 'verify', '-CAfile', str(ca_pem), '-verify_hostname',
                              'opencode.ai', str(server_pem)).returncode == 0)
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                context.load_cert_chain(str(server_pem), str(server_key))
                responder = ThreadingHTTPServer(('127.0.0.1', 0), OwnedTLS)
                responder.socket = context.wrap_socket(responder.socket, server_side=True)
                responder.rows, responder.issued, responder.required, responder.current_role = [], False, [], None
                responder.health_rows = 0
                threading.Thread(target=responder.serve_forever, daemon=True).start()
            with socket.socket() as reservation:
                reservation.bind(('127.0.0.1', 0))
                port = reservation.getsockname()[1]
            if not live:
                report['tls'] = {'ca_sha256': sha(ca_pem), 'authority': 'opencode.ai:443',
                                 'responder_loopback': True}
            workspace, review = work / 'workspace', work / 'reviewer'
            baseline_source, handoff = work / 'baseline-source', work / 'handoff'
            baseline_source.mkdir(mode=0o700)
            handoff.mkdir(mode=0o700)
            handoff_identity = (handoff.stat().st_dev, handoff.stat().st_ino)
            for base in (workspace, review):
                for name in ('home', 'config/opencode', 'data', 'cache', 'state', 'tmp', 'project', 'telemetry'):
                    (base / name).mkdir(parents=True, exist_ok=True)
                (base / 'config/opencode/opencode.json').touch()
            for fixture in FIXTURE:
                fixture_source = input_source(fixture)
                shutil.copy2(fixture_source, workspace / 'project' / fixture.name)
                shutil.copy2(fixture_source, baseline_source / fixture.name)
            original_hashes = {p.name: sha(workspace / 'project' / p.name) for p in FIXTURE}
            report['baseline'] = host_php(baseline_source)
            check('original PHP fails local check and prints before',
                  report['baseline'][0]['exit'] == 0 and report['baseline'][0]['stdout_class'] == 'before'
                  and report['baseline'][0]['stderr_class'] == 'empty'
                  and report['baseline'][1]['exit'] != 0
                  and report['baseline'][1]['stderr_class'] == 'expected_baseline_failure')
            capfile = work / 'capability'
            capability = 'local_' + uuid.uuid4().hex
            capfile.write_text(capability)
            capfile.chmod(0o600)
            internal_args = ['network', 'create', '--internal']
            if selected['cloud']:
                internal_args += ['--subnet', selected['internal_subnet']]
            network = docker(*internal_args, '--label', LABEL + '=' + nonce,
                             'nq-v2-managed-' + nonce[:12] + '-internal')
            check('internal network created', network.returncode == 0)
            internal = network.stdout.strip()
            own('network', internal, 'internal')
            internal_name = 'nq-v2-managed-' + nonce[:12] + '-internal'
            internal_state = inspect('network', internal)
            internal_ipam = internal_state['IPAM']['Config'][0]
            subnet = internal_ipam['Subnet']
            network_range = ipaddress.ip_network(subnet)
            check('Docker internal subnet permits reserved relay address',
                  internal_state.get('Internal') is True and internal_state.get('Driver') == 'bridge'
                  and network_range.num_addresses >= 32
                  and (not selected['cloud'] or
                       (subnet == selected['internal_subnet'] and not internal_ipam.get('Gateway'))))
            relay_ip = str(network_range.network_address + 10)
            check('reserved relay address differs from internal gateway',
                  relay_ip != internal_ipam.get('Gateway'))
            external_args = ['network', 'create']
            if selected['cloud']:
                external_args += ['--subnet', selected['external_subnet'], '--gateway', selected['listen']]
            external_result = docker(*external_args, '--label', LABEL + '=' + nonce,
                                     'nq-v2-managed-' + nonce[:12] + '-external')
            check('relay network created', external_result.returncode == 0)
            external = external_result.stdout.strip()
            own('network', external, 'external')
            if selected['cloud']:
                external_ipam = inspect('network', external)['IPAM']['Config'][0]
                check('owned external bridge matches selected subnet and gateway',
                      external_ipam['Subnet'] == selected['external_subnet']
                      and external_ipam['Gateway'] == selected['listen'])
            relay_env = ['HOST_GATEWAY_PORT=' + str(port)]
            if selected['cloud']:
                relay_env.append('HOST_GATEWAY_HOST=' + selected['listen'])
            relay = created('relay', external,
                            ['type=bind,src=' + str(relay_mount) + ',dst=/relay,readonly'],
                            relay_env, '/relay', (), ip=selected['peer'])
            check('relay joined only owned internal and external networks',
                  docker('network', 'connect', '--ip', relay_ip, internal, relay).returncode == 0)
            relay_state = inspect('container', relay)
            check('reserved relay address recorded before activation',
                  internal_name in relay_state['NetworkSettings']['Networks']
                  and relay_state['NetworkSettings']['Networks'][internal_name]['IPAMConfig']['IPv4Address'] == relay_ip
                  and (not selected['cloud'] or relay_state['NetworkSettings']['Networks'][
                       'nq-v2-managed-' + nonce[:12] + '-external']['IPAMConfig']['IPv4Address'] ==
                       selected['peer']))
            proxy = 'http://run:' + capability + '@' + relay_ip + ':8080'

            def research(role, base):
                mounts = ['type=bind,src=' + str(base) + ',dst=/workspace',
                          'type=bind,src=' + str(config_mount) + ',dst=/workspace/config/opencode/opencode.json,readonly',
                          'type=bind,src=' + str(observer_mount) + ',dst=/observer/opencode_v2_request_observer,readonly']
                if role == 'reviewer':
                    mounts.append('type=bind,src=' + str(handoff) + ',dst=/handoff,readonly')
                trust = researcher_trust(live, runtime_ca_snapshot, ca_pem)
                mounts += trust['mounts']
                env = [name + '=' + proxy for name in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy')]
                env += ['HOME=/workspace/home', 'XDG_CONFIG_HOME=/workspace/config',
                        'XDG_DATA_HOME=/workspace/data', 'XDG_CACHE_HOME=/workspace/cache',
                        'XDG_STATE_HOME=/workspace/state', 'TMPDIR=/workspace/tmp',
                        'T02_OBSERVER_PATH=/workspace/telemetry/request-names.jsonl',
                        'NO_COLOR=1',
                        'NO_PROXY=127.0.0.1,localhost,::1', 'no_proxy=127.0.0.1,localhost,::1']
                env += trust['env']
                return created(role, internal, mounts, env)

            first = research('first', workspace)
            reviewer = research('reviewer', review)
            resume = research('resume', workspace)
            ids = (relay, first, reviewer, resume)
            states = [inspect('container', identifier) for identifier in ids]
            check('four bound producers created stopped', all(
                  state['State']['Status'] == 'created' and
                  state['Config']['Labels'].get('io.llm-redteam-harness.session-nonce') == nonce
                  for state in states))
            check('only relay dual homed',
                  set(states[0]['NetworkSettings']['Networks']) ==
                  {'nq-v2-managed-' + nonce[:12] + '-internal', 'nq-v2-managed-' + nonce[:12] + '-external'}
                  and all(len(state['NetworkSettings']['Networks']) == 1 for state in states[1:]))
            manifest = work / 'producer-manifest.json'
            manifest.write_text(json.dumps({'version': 1, 'nonce': nonce,
                'producers': [{'id': identifier, 'binding': binding(state)}
                              for identifier, state in zip(ids, states)]}))
            manifest.chmod(0o600)
            proxy_args = ['--state-dir', str(output / 'provider'), '--capability-file', str(capfile),
                          '--max-connections', '16', '--max-bytes', str(8 * 1024 * 1024),
                          '--duration', '300', '--port', str(port)]
            if selected['cloud']:
                proxy_args += ['--listen-address', selected['listen'], '--relay-peer', selected['peer']]
            if live and selected['upstream_route'] != 'direct':
                proxy_args += ['--upstream-proxy-env', selected['upstream_route']]
            if not live:
                proxy_args += ['--dummy-port', str(responder.server_address[1])]
            native = NativeRun(manifest, output / 'run', 300, proxy_args)
            ready = native.start()
            report['native_start'] = ready
            check('one managed fixed-authority CONNECT pool ready',
                  ready['proxy_info']['authority'] == 'opencode.ai:443'
                  and ready['proxy_info']['dummy'] is (not live) and ready['proxy_info']['port'] == port
                  and ready['proxy_info']['host'] == selected['listen']
                  and (ready['proxy_info'].get('upstream_transport') == 'http_connect') ==
                      (live and selected['upstream_route'] != 'direct')
                  and ready['ids'] == list(ids))
            first_authority = authority_snapshot()
            check('one original NativeRun and CONNECT allowance recorded',
                  first_authority['run_identity']['nonce'] == nonce
                  and first_authority['run_identity']['manifest_sha256'] == sha(manifest)
                  and first_authority['run_identity']['ids'] == list(ids)
                  and first_authority['active']
                  and first_authority['tunnels'] == 0 and first_authority['charged_bytes'] == 0)
            with sqlite3.connect(output / 'provider/tunnel.sqlite3') as db:
                frozen = json.loads(db.execute('SELECT config FROM pool').fetchone()[0])
            check('frozen private peer and upstream mode match launch selection',
                  frozen.get('private_listener') == ({'listen_address': selected['listen'],
                      'relay_peer': selected['peer']} if selected['cloud'] else None)
                  and (frozen.get('upstream_proxy') or {}).get('env') ==
                      (selected['upstream_route'] if live and selected['upstream_route'] != 'direct' else None))
            check('relay started at reserved internal address',
                  inspect('container', relay)['NetworkSettings']['Networks'][internal_name]['IPAddress'] == relay_ip
                  and (not selected['cloud'] or inspect('container', relay)['NetworkSettings']['Networks'][
                       'nq-v2-managed-' + nonce[:12] + '-external']['IPAddress'] == selected['peer']))
            first_state = inspect('container', first)
            effective_env = dict(item.split('=', 1) for item in first_state['Config']['Env'] if '=' in item)
            expected_proxy = urlsplit(effective_env.get('HTTPS_PROXY', ''))
            expected_trust = researcher_trust(live, runtime_ca_snapshot, ca_pem)
            check('researcher effective proxy, trust and isolated DNS readback',
                  expected_proxy.hostname == relay_ip and expected_proxy.port == 8080
                  and effective_env.get('https_proxy') == effective_env.get('HTTPS_PROXY')
                  and effective_env.get('SSL_CERT_FILE') == expected_trust['container_path']
                  and all(effective_env.get(name) == '' for name in CLEARABLE_TRUST_ENV
                          if name != 'SSL_CERT_FILE')
                  and all(name not in effective_env for name in ABSENT_TRUST_ENV)
                  and first_state['HostConfig']['Dns'] == ['127.0.0.1']
                  and set(first_state['NetworkSettings']['Networks']) ==
                      {'nq-v2-managed-' + nonce[:12] + '-internal'})
            probe = connect_probe(first)
            with sqlite3.connect(output / 'provider/tunnel.sqlite3') as db:
                probe_tunnels = db.execute('SELECT count(*) FROM tunnels').fetchone()[0]
            report['relay_probe'] = {**probe, 'host_tunnels': probe_tunnels}
            check('researcher reaches fixed CONNECT through owned relay',
                  probe['exit_code'] == 0 and probe['status_line'].startswith('HTTP/1.1 200')
                  and probe_tunnels == 1)
            alternate = connect_probe(first, 'alternate')
            wrong = connect_probe(first, 'wrong')
            with sqlite3.connect(output / 'provider/tunnel.sqlite3') as db:
                rejected_tunnels = db.execute('SELECT count(*) FROM tunnels').fetchone()[0]
                rejection_rows = db.execute("SELECT data FROM events WHERE kind='rejected'").fetchall()
            reasons = {json.loads(row[0]).get('reason') for row in rejection_rows}
            report['proxy_denials'] = {'alternate': alternate, 'wrong_capability': wrong,
                                       'tunnels_after': rejected_tunnels, 'reasons': sorted(reasons)}
            check('alternate authority and wrong capability denied before tunnel',
                  alternate['status_line'].startswith('HTTP/1.1 403')
                  and wrong['status_line'].startswith('HTTP/1.1 403')
                  and rejected_tunnels == probe_tunnels
                  and {'authority_or_method', 'proxy_authorization_or_host'} <= reasons)
            external_receiver = created('external-receiver', external,
                ['type=bind,src=' + str(mock_mount) + ',dst=/fixture/router.php,readonly'],
                entry='php', args=('-S', '0.0.0.0:8082', '/fixture/router.php'))
            check('owned external receiver started',
                  docker('container', 'start', external_receiver).returncode == 0)
            receiver_state = inspect('container', external_receiver)
            receiver_ip = receiver_state['NetworkSettings']['Networks'][
                'nq-v2-managed-' + nonce[:12] + '-external']['IPAddress']
            receiver_url = 'http://' + receiver_ip + ':8082/health'
            for _ in range(20):
                positive = docker('container', 'exec', relay, 'php', '-r',
                                  'echo file_get_contents($argv[1]);', receiver_url)
                if positive.returncode == 0 and positive.stdout == 'ready\n':
                    break
                time.sleep(.1)
            negative = docker('container', 'exec', first, 'wget', '-Y', 'off', '-qO-', '-T', '3',
                              receiver_url)
            report['external_route'] = {'receiver_ip': receiver_ip,
                'relay_positive': positive.returncode == 0 and positive.stdout == 'ready\n',
                'researcher_direct_denied': negative.returncode != 0}
            check('relay positive and researcher literal-IP direct egress denied',
                  report['external_route']['relay_positive'] and
                  report['external_route']['researcher_direct_denied'] and
                  set(receiver_state['NetworkSettings']['Networks']) ==
                  {'nq-v2-managed-' + nonce[:12] + '-external'})
            loaded = api(first, 'config.get')
            document = next(x['info'] for x in loaded if x.get('type') == 'document')
            check('native V2 image and config active',
                  docker('container', 'exec', first, 'opencode', '--version').stdout.strip() == 'opencode v2.0.32'
                  and document.get('model') ==
                  {'providerID': 'opencode', 'model': 'deepseek-v4.1-flash-free'})
            if live:
                report['loaded_surface'] = settled_surface(first)
                effective = report['loaded_surface']['effective_config']
                db_path = docker('container', 'exec', first, 'opencode', 'debug', 'paths', 'db')
                report['loaded_surface']['native_db_path'] = db_path.stdout.strip()
                expected = json.loads(config_mount.read_text())
                check('live effective agents, policy, plugins, skills, tools and store read back',
                      effective['model'] == document['model']
                      and effective['permissions'] == expected['permissions']
                      and effective['policies'] == expected['policies']
                      and effective['plugins'] == expected['plugins']
                      and effective['fallback'] is None
                      and effective['websearch'] is False
                      and report['loaded_surface']['mcp_count'] == 0
                      and any(a['id'] == 'build' and a['mode'] == 'primary'
                              and expected['permissions'][0] in a['permissions']
                              and {'action': 'write', 'resource': '*', 'effect': 'allow'}
                                  in a['permissions']
                              for a in report['loaded_surface']['agents'])
                      and {'edit', 'write', 'shell'} <=
                          set(report['loaded_surface']['registered_tool_names'])
                      and 't02.request-names' in report['loaded_surface']['plugin_ids']
                      and db_path.returncode == 0
                      and report['loaded_surface']['native_db_path'] ==
                          '/workspace/data/opencode/opencode.db')
                check('surface server exited before native model run',
                      idle_top(docker('container', 'top', first)))
            check('reviewer and resume OpenCode processes idle before first turn',
                  all(idle_top(docker('container', 'top', identifier))
                      for identifier in (reviewer, resume)))
            if selected['cloud']:
                def peer_state():
                    return provider_state(output / 'provider/tunnel.sqlite3', responder)

                def settled_relay():
                    before = peer_state()
                    probe = connect_probe(first)
                    deadline = time.monotonic() + 5
                    after = before
                    while time.monotonic() < deadline:
                        after = peer_state()
                        if (len(after['tunnels']) == len(before['tunnels']) + 1
                                and all(row[1] == 'closed' for row in after['tunnels'])
                                and after['closed_events'] == len(after['tunnels'])):
                            break
                        time.sleep(.05)
                    return {'probe': probe, 'tunnels_before': len(before['tunnels']),
                            'tunnels_after': len(after['tunnels']),
                            'settled': (probe['exit_code'] == 0
                                and probe['status_line'].startswith('HTTP/1.1 200')
                                and len(after['tunnels']) == len(before['tunnels']) + 1
                                and all(row[1] == 'closed' for row in after['tunnels'])
                                and after['closed_events'] == len(after['tunnels']))}

                report['cloud_relay_before_peer'] = settled_relay()
                check('cloud relay positive before wrong peer with settled tunnel',
                      report['cloud_relay_before_peer']['settled'])
                before_peer = peer_state()
                peer_code = (
                    '$cap=stream_get_contents(STDIN);'
                    'if(!preg_match("/^local_[0-9a-f]{32}$/D",$cap))exit(3);'
                    '$s=@stream_socket_client("tcp://".$argv[1].":".$argv[2],$e,$m,3);'
                    'if(!$s){echo "{\\"connected\\":false}";exit;}'
                    'stream_set_timeout($s,3);'
                    '$auth=base64_encode("run:".$cap);unset($cap);'
                    '$request="CONNECT opencode.ai:443 HTTP/1.1\\r\\nHost: opencode.ai:443\\r\\n".'
                    '"Proxy-Authorization: Basic ".$auth."\\r\\nX-Forwarded-For: ".$argv[3].'
                    '"\\r\\nForwarded: for=".$argv[3]."\\r\\n\\r\\n";'
                    '@fwrite($s,$request);$reply=@fgets($s);$meta=stream_get_meta_data($s);fclose($s);'
                    'echo json_encode(["connected"=>true,"closed_before_status"=>'
                    '($reply===false && $meta["eof"] && !$meta["timed_out"])]);')
                peer = subprocess.run(['docker', 'container', 'exec', '-i', external_receiver,
                    'php', '-r', peer_code, selected['listen'], str(port), selected['peer']],
                    input=capability, capture_output=True, text=True, timeout=10)
                try:
                    peer_reply = json.loads(peer.stdout) if peer.returncode == 0 else {}
                except ValueError:
                    peer_reply = {}
                if not isinstance(peer_reply, dict):
                    peer_reply = {}
                time.sleep(.1)
                after_peer = peer_state()
                report['cloud_peer_probe'] = {'receiver_ip': receiver_ip,
                    'exit_code': peer.returncode,
                    'tcp_connected': peer_reply.get('connected') is True,
                    'closed_before_status': peer_reply.get('closed_before_status') is True,
                    'ledger_before': before_peer, 'ledger_after': after_peer}
                check('cloud external wrong peer closes before HTTP and admission',
                      receiver_ip != selected['peer'] and peer.returncode == 0
                      and peer_reply.get('connected') is True
                      and peer_reply.get('closed_before_status') is True
                      and after_peer == before_peer)
                direct_code = ('$s=@stream_socket_client("tcp://".$argv[1].":".$argv[2],$e,$m,3);'
                               'if($s){fclose($s);echo "connected";}else echo "denied";')
                direct = docker('container', 'exec', first, 'php', '-r', direct_code,
                                selected['listen'], str(port))
                time.sleep(.1)
                after_direct = peer_state()
                report['cloud_researcher_direct_probe'] = {'denied': direct.stdout == 'denied',
                    'ledger_before': after_peer, 'ledger_after': after_direct}
                check('cloud internal researcher cannot reach listener directly',
                      direct.returncode == 0 and direct.stdout == 'denied'
                      and after_direct == after_peer)
                report['cloud_relay_after_peer'] = settled_relay()
                check('cloud relay positive after wrong peer with settled tunnel',
                      report['cloud_relay_after_peer']['settled'])
            first_session = api(first, 'session.create', '--data', '{"title":"managed harmless PHP"}')['data']['id']
            report['first_session'] = first_session
            first_prompt = ('Inspect index.php, message.php and check.php. Edit only message.php so '
                'message() returns after instead of before. Use shell to run php -l index.php, '
                'php -l message.php, php -l check.php, php check.php and php index.php. '
                'Use the write tool to create research-note.md with only the local observed result. '
                'Then briefly report what actually passed.') if live else (
                'Inspect the harmless three-file PHP fixture, change message.php from before to after, '
                'run PHP lint and the local check, then report the result. Use your tools.')
            first_run = native_call(first, 'first', first_session, first_prompt)
            check('first native model route reached',
                  first_run['exit_code'] == 0 and native_clean(first_run)
                  and first_session in first_run['session_ids']
                  and (first_run['pool_after']['charged_bytes'] > first_run['pool_before']['charged_bytes']
                       if live else any(row['role'] == 'first' and row['path'] == OWNED_PATH
                           and row['model'] == 'deepseek-v4.1-flash-free' and row['stream'] is True
                           for row in responder.rows)))
            check('native tools edited and checked harmless PHP',
                  (all(any(tool['name'] == name and tool['status'] == 'completed'
                           for tool in first_run['tools']) for name in ('edit', 'shell', 'write'))
                   and set(PHP_CHECKS) <= set(first_run['shell_checks_observed'])
                   if live else any(tool['name'] == 'shell' and tool['status'] == 'completed' and
                                    'php check.php' in first_run['shell_checks_observed']
                                    for tool in first_run['tools'])
                   and responder.issued))
            project_files = list((workspace / 'project').iterdir())
            check('model outputs are regular project files without symlinks',
                  all(p.is_file() and not p.is_symlink() for p in project_files)
                  and all((workspace / 'project' / p.name).is_file() for p in FIXTURE))
            changed = {p.name: sha(workspace / 'project' / p.name) for p in FIXTURE}
            check('only intended fixture source changed',
                  changed['message.php'] != original_hashes['message.php']
                  and all(changed[n] == original_hashes[n] for n in ('index.php', 'check.php'))
                  and set(p.name for p in project_files) ==
                      {'index.php', 'message.php', 'check.php', 'research-note.md'})
            note = workspace / 'project/research-note.md'
            check('actual harmless research note exists and is bounded',
                  note.is_file() and not note.is_symlink() and 0 < note.stat().st_size <= 2048)
            note_text = note.read_text()
            if live:
                check('ordinary research note records local result only',
                      'after' in note_text.lower() and 'check' in note_text.lower() and
                      capability not in note_text and
                      base64.b64encode(('run:' + capability).encode()).decode() not in note_text and
                      not re.search(r'(?i)authorization|bearer|cookie|password|token|api[_-]?key|https?://|local_[0-9a-f]{32}',
                                    note_text))
                report['research_note'] = {'sha256': sha(note), 'bytes': note.stat().st_size,
                                           'mentions_after': 'after' in note_text.lower(),
                                           'mentions_check': 'check' in note_text.lower()}
            report['host_after_first'] = host_php(workspace / 'project')
            check('independent host PHP check passes and prints after',
                  report['host_after_first'][0]['stdout_class'] == 'after'
                  and report['host_after_first'][1]['stdout_class'] == 'check_passed'
                  and all(x['stderr_class'] == 'empty' for x in report['host_after_first'])
                  and all(x['exit'] == 0 for x in report['host_after_first']))
            report['usage_after_first'] = usage(first, first_session)
            first_usage = all_native_usage(first, 'first')
            if live:
                check('first native usage pages include primary session',
                      any(x['id'] == first_session for x in first_usage['sessions'])
                      and not any(a['had_error'] for x in first_usage['sessions']
                                  for a in x['assistant_usage']))
            check('researcher quiescent and reviewer idle before packet publication',
                  idle_top(docker('container', 'top', first))
                  and idle_top(docker('container', 'top', reviewer)))
            packet_pin = publish_review_packet(
                handoff, baseline_source, workspace / 'project', note, first_native_stdout,
                {'baseline': {'source_sha256': original_hashes, 'network': 'none',
                              'image_id': selected['image_id'], 'results': report['baseline']},
                 'candidate': {'source_sha256': changed, 'network': 'none',
                               'image_id': selected['image_id'], 'results': report['host_after_first']}},
                capability, forbidden_paths=(str(ROOT), str(output), str(work)))
            report['review_packet'] = {'files': packet_pin['files'],
                'archive': 'review-packet/',
                'classification': 'fixed observer-selected harmless packet; original protected capture unavailable'}
            check('fixed packet root and exact bytes frozen before reviewer session',
                  (packet_pin['dev'], packet_pin['ino']) == handoff_identity
                  and verify_review_packet(handoff, packet_pin))
            archive_review_packet(handoff, output / 'review-packet', packet_pin)
            reviewer_state = inspect('container', reviewer)
            check('fresh reviewer has only read-only packet and separate empty project',
                  any(item.get('Source') == str(handoff) and item.get('Destination') == '/handoff'
                          and item.get('RW') is False for item in reviewer_state['Mounts'])
                  and not any((review / 'project').iterdir())
                  and all(item.get('Source') != str(workspace) for item in reviewer_state['Mounts']))
            review_authority = authority_snapshot()
            authority_keys = ('run_identity', 'pool_config', 'pool_created', 'pool_deadline',
                              'max_connections', 'max_bytes')
            report['review_allowance_before'] = {
                'pool_config_sha256': hashlib.sha256(review_authority['pool_config'].encode()).hexdigest(),
                'tunnels': review_authority['tunnels'],
                'charged_bytes': review_authority['charged_bytes'],
                'same_original_authority': all(review_authority[k] == first_authority[k]
                                               for k in authority_keys),
                'active': review_authority['active']}
            report['review_status'] = 'unfinished_until_actual_material_review'
            check('review retains original active run, pool and remaining allowance',
                  report['review_allowance_before']['same_original_authority']
                  and review_authority['active'] and time.time() < review_authority['pool_deadline']
                  and first_authority['tunnels'] <= review_authority['tunnels'] < review_authority['max_connections']
                  and first_authority['charged_bytes'] <= review_authority['charged_bytes'] < review_authority['max_bytes']
                  and verify_review_packet(handoff, packet_pin))
            empty_reviewer = all_native_usage(reviewer, 'pre-review')
            check('fresh reviewer native store has no prior sessions', not empty_reviewer['sessions'])
            reviewer_session = api(reviewer, 'session.create', '--data', '{"title":"managed reviewer"}')['data']['id']
            report['reviewer_session'] = reviewer_session
            check('new reviewer session has no old messages',
                  api(reviewer, 'session.message.list', '--param', 'sessionID=' + reviewer_session,
                      '--param', 'limit=100').get('data') == []
                  and verify_review_packet(handoff, packet_pin))
            review_run = native_call(reviewer, 'reviewer', reviewer_session,
                                     (handoff / 'PROMPT.txt').read_text())
            report['usage_after_review'] = usage(reviewer, reviewer_session)
            review_usage = all_native_usage(reviewer, 'reviewer')
            if live:
                check('reviewer native usage pages include reviewer session',
                      any(x['id'] == reviewer_session for x in review_usage['sessions'])
                      and not any(a['had_error'] for x in review_usage['sessions']
                                  for a in x['assistant_usage']))
            check('fresh reviewer uses same model route and native store',
                  review_run['exit_code'] == 0 and native_clean(review_run)
                  and reviewer_session in review_run['session_ids']
                  and report['usage_after_review']['id'] == reviewer_session
                  and (review_run['pool_after']['charged_bytes'] > review_run['pool_before']['charged_bytes']
                       if live else any(row['role'] == 'reviewer' and row['path'] == OWNED_PATH
                                        for row in responder.rows)))
            after_review_authority = authority_snapshot()
            check('review did not replace pool, reset counters or change frozen packet',
                  all(after_review_authority[k] == first_authority[k] for k in authority_keys)
                  and after_review_authority['tunnels'] >= review_authority['tunnels']
                  and after_review_authority['charged_bytes'] >= review_authority['charged_bytes']
                  and verify_review_packet(handoff, packet_pin)
                  and set(p.name for p in (output / 'review-packet').iterdir()) == set(packet_pin['files'])
                  and all(sha(output / 'review-packet' / name) == digest
                          for name, digest in packet_pin['files'].items()))
            try:
                review_tools = native_tool_material(reviewer_native_stdout)
            except RuntimeError as error:
                if str(error) != 'native_tool_evidence_missing':
                    raise
                review_tools = {'source': 'native reviewer JSONL', 'records': [],
                                'status': 'no_reviewer_tool_action'}
            tool_bytes = packet_public_bytes(json.dumps(review_tools, indent=2) + '\n', capability,
                                             (str(ROOT), str(output), str(work)))
            private_snapshot(output / 'reviewer-tools.json', tool_bytes)
            completed = [item for item in review_tools['records'] if item['status'] == 'completed']
            material_read = any('/handoff/' in json.dumps(item['input'])
                                and item['tool'] in ('read', 'shell', 'glob', 'grep') for item in completed)
            material_check = any(item['tool'] == 'shell' and 'php ' in json.dumps(item['input'])
                                 for item in completed)
            report['host_after_review'] = host_php(workspace / 'project')
            report['reviewer_material_work'] = {
                'packet_read_observed': material_read,
                'reviewer_selected_php_check_observed': material_check,
                'independent_candidate_effect_replayed': report['host_after_review'] == report['host_after_first'],
                'native_tool_evidence_sha256': hashlib.sha256(tool_bytes).hexdigest(),
                'qualification': ('candidate_for_operator_review' if live and material_read and material_check
                                  and report['host_after_review'] == report['host_after_first']
                                  else 'unqualified_owned_synthetic_response' if not live
                                  else 'unfinished_material_review')}
            report['review_status'] = report['reviewer_material_work']['qualification']
            check('candidate source and independent effect stable after reviewer',
                  report['host_after_review'] == report['host_after_first']
                  and {p.name: sha(workspace / 'project' / p.name) for p in FIXTURE} == changed)
            check('first producer stopped before exact-session resume',
                  docker('container', 'stop', first).returncode == 0)
            dbpath = workspace / 'data/opencode/opencode.db'
            report['stopped_store_files'] = {name: {'exists': (dbpath.parent / name).exists(),
                'bytes': (dbpath.parent / name).stat().st_size if (dbpath.parent / name).exists() else None}
                for name in ('opencode.db', 'opencode.db-wal', 'opencode.db-shm')}
            statement = 'PRAGMA quick_check'
            try:
                with sqlite3.connect('file:' + str(dbpath) + '?mode=ro', uri=True) as db:
                    quick = db.execute('PRAGMA quick_check').fetchone()[0]
                    statement = 'SELECT id,cost'
                    retained = db.execute('SELECT id,cost FROM session_v2 ORDER BY id').fetchall()
                    if any(not isinstance(sid, str) or not re.fullmatch(r'ses_[A-Za-z0-9]{1,64}', sid)
                           for sid, _ in retained):
                        raise RuntimeError('stopped_store_session_id_invalid')
                    retained = [(sid, safe_number(cost)) for sid, cost in retained]
            except sqlite3.DatabaseError as error:
                report['stopped_store_sql_failure'] = {'statement': statement,
                                                       'error_type': type(error).__name__}
                saved = output / 'stopped-store-private'
                saved.mkdir(mode=0o700)
                saved.chmod(0o700)
                excluded = []
                for name in report['stopped_store_files']:
                    item = dbpath.parent / name
                    if item.exists():
                        if capability.encode() in item.read_bytes():
                            excluded.append(name)
                            continue
                        shutil.copy2(item, saved / name)
                        (saved / name).chmod(0o600)
                report['stopped_store_quarantine'] = {
                    'classification': 'unredacted private forensic evidence; do not share',
                    'directory_mode': '0700', 'file_mode': '0600',
                    'file_sha256': {p.name: sha(p) for p in saved.iterdir()},
                    'excluded_for_local_capability': excluded}
                raise RuntimeError('stopped_store_sql_failed') from error
            report['stopped_store'] = {'quick_check': 'ok' if quick == 'ok' else 'not_ok',
                                       'sessions': retained}
            check('first process exited and stopped native store intact',
                  not inspect('container', first)['State']['Running'] and quick == 'ok'
                  and any(row[0] == first_session for row in retained))
            check('resume OpenCode process idle before same-session read',
                  idle_top(docker('container', 'top', resume)))
            check('session survives in presealed replacement',
                  usage(resume, first_session)['id'] == first_session)
            resume_run = native_call(resume, 'resume', first_session,
                                     'Read the existing harmless PHP result and confirm the local check. Do not edit files.')
            report['usage_after_resume'] = usage(resume, first_session)
            if live:
                resume_usage = all_native_usage(resume, 'resume')
                check('resumed native usage pages include exact primary session',
                      any(x['id'] == first_session for x in resume_usage['sessions'])
                      and not any(a['had_error'] for x in resume_usage['sessions']
                                  for a in x['assistant_usage']))
            check('exact native session resumed through same route',
                  resume_run['exit_code'] == 0 and native_clean(resume_run)
                  and first_session in resume_run['session_ids']
                  and (resume_run['pool_after']['charged_bytes'] > resume_run['pool_before']['charged_bytes']
                       if live else any(row['role'] == 'resume' and row['path'] == OWNED_PATH
                                        for row in responder.rows)))
            report['host_after_resume'] = host_php(workspace / 'project')
            check('host effect and source bytes retained after resume',
                  report['host_after_resume'] == report['host_after_first']
                  and {p.name: sha(workspace / 'project' / p.name) for p in FIXTURE} == changed)
            if live:
                final_primary = all_native_usage(resume, 'final-primary')
                final_reviewer = all_native_usage(reviewer, 'final-reviewer')
                unique = final_primary['sessions'] + final_reviewer['sessions']
                costs = [item['cost'] for item in unique]
                assistant_rows = [a for session in unique for a in session['assistant_usage']]
                message_ids = [a['id'] for a in assistant_rows]
                distinct_messages = len(message_ids) == len(set(message_ids))
                assistant_totals = token_field_sums_or_unknown(assistant_rows if distinct_messages else [])
                session_totals = token_field_sums_or_unknown(unique)
                report['native_usage_reconciliation'] = {
                    'unique_session_ids': [item['id'] for item in unique],
                    'sum_unique_session_cost_fields_or_unknown': (sum(costs) if all(isinstance(v, (int, float))
                        for v in costs) else None),
                    'session_cost_aggregation_semantics': 'unknown; not provider bill',
                    'assistant_message_count': len(assistant_rows),
                    'assistant_message_ids_distinct': distinct_messages,
                    'assistant_message_token_field_sums_or_unknown': assistant_totals,
                    'unique_session_token_field_sums_or_unknown': session_totals,
                    'session_minus_assistant_field_sums_or_unknown': {
                        key: (session_totals[key] - assistant_totals[key]
                              if session_totals[key] is not None and assistant_totals[key] is not None else None)
                        for key in assistant_totals},
                    'token_aggregation_semantics': 'unknown; neither subtotal is whole-run provider usage',
                    'provider_billed_usage': None,
                    'inner_http_request_total': None,
                    'provenance': 'native delayed researcher-writable; provider unavailable'}
                check('all final native session pages reconciled or marked unknown',
                      len({item['id'] for item in unique}) == len(unique)
                      and first_session in report['native_usage_reconciliation']['unique_session_ids']
                      and reviewer_session in report['native_usage_reconciliation']['unique_session_ids'])
            with sqlite3.connect(output / 'provider/tunnel.sqlite3') as db:
                report['ledger_before_stop'] = {'pool': db.execute('SELECT bytes,created FROM pool').fetchone(),
                    'tunnels': db.execute('SELECT id,phase,uploaded,downloaded,reason FROM tunnels ORDER BY id').fetchall()}
            check('one host pool retains all role tunnels',
                  len(report['ledger_before_stop']['tunnels']) >= 1 and
                  report['ledger_before_stop']['pool'][0] > 0)
            if live:
                charged = sum(row[2] + row[3] for row in report['ledger_before_stop']['tunnels'])
                check('live one-pool charge reconciles within frozen hard caps',
                      charged == report['ledger_before_stop']['pool'][0]
                      and len(report['ledger_before_stop']['tunnels']) <= 16
                      and charged <= 8 * 1024 * 1024)
            else:
                accepted_rows = len(responder.rows)
                remaining = 16 - len(report['ledger_before_stop']['tunnels'])
                check('declared tunnel cap has room for bounded exhaustion probe', remaining > 0)
                fill = [connect_probe(reviewer) for _ in range(remaining)]
                reviewer_capped = connect_probe(reviewer)
                resume_capped = connect_probe(resume)
                with sqlite3.connect(output / 'provider/tunnel.sqlite3') as db:
                    pool_bytes = db.execute('SELECT bytes FROM pool').fetchone()[0]
                    charged = db.execute('SELECT sum(uploaded+downloaded) FROM tunnels').fetchone()[0]
                    tunnels = db.execute('SELECT count(*) FROM tunnels').fetchone()[0]
                    cap_denials = [json.loads(row[0]).get('reason') for row in db.execute(
                        "SELECT data FROM events WHERE kind='rejected'")]
                report['cap_reconciliation'] = {'fill_count': len(fill), 'tunnels': tunnels,
                    'pool_bytes': pool_bytes, 'sum_tunnel_bytes': charged,
                    'reviewer_status': reviewer_capped['status_line'],
                    'resume_status': resume_capped['status_line'],
                    'admission_limit_denials': cap_denials.count('admission_limit'),
                    'owned_responses_unchanged': len(responder.rows) == accepted_rows}
                check('same cap denies reviewer and resume with retained charges',
                      all(row['status_line'].startswith('HTTP/1.1 200') for row in fill)
                      and reviewer_capped['status_line'].startswith('HTTP/1.1 403')
                      and resume_capped['status_line'].startswith('HTTP/1.1 403')
                      and tunnels == 16 and charged == pool_bytes
                      and cap_denials.count('admission_limit') >= 2
                      and len(responder.rows) == accepted_rows)
            send_release = threading.Event()
            queued = {}
            sent = []
            health_before = owned_health_count(responder)

            def owned_health_send():
                if live:
                    sent.append('local-send')
                    return True
                tls = ssl.create_default_context(cafile=str(ca_pem))
                with socket.create_connection(('127.0.0.1', responder.server_address[1]), timeout=3) as raw:
                    with tls.wrap_socket(raw, server_hostname='opencode.ai') as secure:
                        secure.sendall(b'GET /health HTTP/1.1\r\nHost: opencode.ai\r\nConnection: close\r\n\r\n')
                        return secure.recv(64).startswith(b'HTTP/1.0 200')

            def queued_send():
                send_release.wait(30)
                try:
                    with dispatch_guard(output / 'run'):
                        queued['sent'] = owned_health_send()
                except RunStopped:
                    queued['denied'] = True

            worker = threading.Thread(target=queued_send, daemon=True)
            worker.start()
            request_stop(output / 'run', 'harmless_live_complete' if live else 'owned_offline_complete')
            report['native_stop'] = native.close()
            try:
                stop_request = json.loads((output / 'run/STOP_REQUEST').read_text())['monotonic']
                stopping = json.loads((output / 'run/STOPPING').read_text())['monotonic']
                revoked = json.loads((output / 'run/REVOKED').read_text())
                with sqlite3.connect(output / 'provider/tunnel.sqlite3') as db:
                    detected = json.loads(db.execute("SELECT data FROM events WHERE kind='stop_detected' ORDER BY id DESC LIMIT 1").fetchone()[0])['monotonic']
                    frozen = json.loads(db.execute("SELECT data FROM events WHERE kind='producer_set_frozen' ORDER BY id DESC LIMIT 1").fetchone()[0])['monotonic']
                ordered = (output / 'provider/REVOKED').exists() and revoked['producers_verified_stopped'] is True \
                    and stop_request <= stopping <= detected <= frozen <= revoked['monotonic']
                report['stop_order'] = {'provider_only_marker_present': (output / 'provider/REVOKED').exists(),
                                        'run_revoked_verified': revoked['producers_verified_stopped'],
                                        'ordered_monotonic': ordered}
            except (OSError, ValueError, KeyError, TypeError, IndexError, sqlite3.Error):
                ordered = False
                report['stop_order'] = {'error': 'marker_readback_unavailable'}
            check('provider closure and verified run stop markers ordered', ordered)
            check('verified run stop and exact producers frozen',
                  report['native_stop']['status'] == 'stopped' and
                  all(not (state := inspect('container', identifier)['State'])['Running'] or state['Paused']
                      for identifier in ids))
            send_release.set()
            worker.join(timeout=5)
            fresh = {}
            try:
                with dispatch_guard(output / 'run'):
                    fresh['sent'] = owned_health_send()
            except RunStopped:
                fresh['denied'] = True
            report['post_stop_dispatch'] = {'queued': queued, 'fresh': fresh,
                                            'owned_health_before': health_before,
                                            'owned_health_after': owned_health_count(responder)}
            check('queued and fresh host sends denied after verified stop',
                  not worker.is_alive() and queued == {'denied': True}
                  and fresh == {'denied': True}
                  and not sent
                  and owned_health_count(responder) == health_before)
            if not live:
                report['responder_rows'] = responder.rows
                report['responder_required_shell_fields'] = responder.required
            else:
                with sqlite3.connect(output / 'provider/tunnel.sqlite3') as db:
                    report['ledger_after_stop'] = {'bytes': db.execute('SELECT bytes FROM pool').fetchone()[0],
                        'tunnels': db.execute('SELECT count(*) FROM tunnels').fetchone()[0],
                        'denials': [json.loads(row[0]).get('reason') for row in db.execute(
                            "SELECT data FROM events WHERE kind='rejected'")]}
                report['in_flight_after_stop_charged_bytes'] = max(0,
                    report['ledger_after_stop']['bytes'] - report['ledger_before_stop']['pool'][0])
            check('source pins unchanged through managed run',
                  all(sha(ROOT / name) == digest for name, digest in report['source_sha256'].items()))
    except Exception as error:
        report['error'] = public_error(error)
    finally:
        report.update(finish_owned(native, resources, nonce, docker, work,
                                   report.get('native_stop'), responder))
        report['source_pins_stable'] = all(sha(ROOT / name) == digest
                                            for name, digest in report['source_sha256'].items())
        report['source_copies_match'] = all(sha(source_root / name) == digest
                                            for name, digest in report['source_sha256'].items())
        report['status'] = 'pass' if (report['checks'] and all(x['pass'] for x in report['checks'])
                                     and report['cleanup_complete'] and report['temporary_secret_files_removed']
                                     and report['source_pins_stable'] and report['source_copies_match']
                                     and not any(report.get(key) for key in
                                                 ('error', 'native_stop_error', 'responder_stop_error',
                                                  'cleanup_error', 'temporary_cleanup_error'))) else 'fail'
        save()
    print(json.dumps({'status': report['status'], 'checks': len(report['checks']),
                      'output': str(output)}))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
