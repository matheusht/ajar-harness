#!/usr/bin/env python3
"""Install pinned native tool bundles privately, without executing package code."""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tarfile
import tempfile
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import zipfile

from engagement_contract import ContractError, canonical, digest, source_manifest
from native_runtime_transport import RuntimeError

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / 'config/native-tool-lock.json'
MAX_ARCHIVE = 256 * 1024 ** 2
MAX_EXPANDED = 1024 ** 3


class InstallError(ValueError):
    pass


def safe_relative(name):
    value = PurePosixPath(name)
    if (not name or value.is_absolute() or any(part in ('', '.', '..') for part in name.split('/'))
            or '\\' in name or any(ord(c) < 32 for c in name)):
        raise InstallError('archive_path_invalid')
    return value


def download(row, output):
    parsed = urlsplit(row['url'])
    if (parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname == '127.0.0.1')
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise InstallError('archive_url_invalid')
    integrity = row['integrity']
    if re.fullmatch(r'sha256:[0-9a-f]{64}', integrity):
        algorithm, expected = 'sha256', bytes.fromhex(integrity[7:])
    elif integrity.startswith('sha512-'):
        algorithm, expected = 'sha512', base64.b64decode(integrity[7:], validate=True)
        if len(expected) != 64:raise InstallError('archive_integrity_invalid')
    else:
        raise InstallError('archive_integrity_invalid')
    checksum, count = hashlib.new(algorithm), 0
    try:
        with urlopen(Request(row['url'], headers={'User-Agent': 'oslit-native-install/1'}), timeout=30) as response, output.open('xb') as stream:
            os.chmod(output, 0o600)
            length = response.headers.get('Content-Length')
            expected_length = int(length) if length else None
            if expected_length is not None and expected_length > MAX_ARCHIVE:
                raise InstallError('archive_too_large')
            while chunk := response.read(1024 * 1024):
                count += len(chunk)
                if count > MAX_ARCHIVE:raise InstallError('archive_too_large')
                checksum.update(chunk)
                stream.write(chunk)
            if expected_length is not None and count != expected_length:
                raise InstallError('archive_download_failed')
    except InstallError:
        raise
    except Exception:
        raise InstallError('archive_download_failed') from None
    if checksum.digest() != expected:
        raise InstallError('archive_digest_mismatch')
    return {'url': row['url'], 'integrity': integrity, 'compressed_bytes': count}


def write_member(stream, path, size, executable, budget):
    budget[0] += size
    budget[1] += 1
    if size < 0 or budget[0] > MAX_EXPANDED or budget[1] > 100000:
        raise InstallError('archive_expanded_limit')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    count = 0
    with path.open('xb') as output:
        os.chmod(path, 0o700 if executable else 0o600)
        while chunk := stream.read(min(1024 * 1024, size - count + 1)):
            count += len(chunk)
            if count > size:raise InstallError('archive_member_invalid')
            output.write(chunk)
    if count != size:raise InstallError('archive_member_invalid')


def unpack(archive, destination, budget, *, member=None, package=False):
    found = False
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as entries:
            for info in entries.infolist():
                name = info.filename.rstrip('/')
                safe_relative(name)
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode):raise InstallError('archive_entry_invalid')
                if info.is_dir():continue
                if member is not None and name != member:continue
                with entries.open(info) as stream:
                    write_member(stream, destination, info.file_size, True, budget)
                found = True
    else:
        with tarfile.open(archive, 'r:*') as entries:
            for info in entries:
                name = info.name.rstrip('/')
                safe_relative(name)
                if info.isdir():continue
                if not info.isfile():raise InstallError('archive_entry_invalid')
                if member is not None and name != member:continue
                if package:
                    if not name.startswith('package/'):
                        raise InstallError('archive_path_invalid')
                    path = destination / safe_relative(name[len('package/'):])
                else:
                    path = destination
                with entries.extractfile(info) as stream:
                    write_member(stream, path, info.size, bool(info.mode & 0o111), budget)
                found = True
    if not found:raise InstallError('archive_member_missing')


def inspector(kind, bundle):
    module = importlib.import_module('native_runtime_' + kind)
    return module.inspect_tool_bundle({'kind': kind, 'version': module.Runtime.version, 'tool_bundle': bundle})


def install(args):
    lock_bytes = args.lock.read_bytes()
    lock = json.loads(lock_bytes)
    if (lock.get('kind') != 'native-tool-installation-lock-v1' or
            (lock.get('codex_version'), lock.get('omp_version'), lock.get('bun_version')) != ('0.166.0', '18.20.0', '1.4.4')):
        raise InstallError('installation_version_unsupported')
    if args.platform not in ('linux/arm64', 'linux/amd64') or args.platform not in lock['platforms']:
        raise InstallError('installation_platform_unsupported')
    destination = args.destination.absolute()
    if destination.parent.resolve() != destination.parent or not destination.parent.is_dir():
        raise InstallError('installation_parent_invalid')
    if args.receipt.resolve().is_relative_to(destination):
        raise InstallError('installation_receipt_inside_bundle')
    if args.receipt.exists() or args.receipt.is_symlink():
        raise InstallError('installation_receipt_exists')
    try:destination.mkdir(mode=0o700)
    except FileExistsError:raise InstallError('installation_destination_exists') from None
    budget, archives = [0, 0], []
    try:
        with tempfile.TemporaryDirectory(prefix='.oslit-download-', dir=destination.parent) as temporary:
            archive = Path(temporary) / 'archive'
            def acquire(row, output, *, package=False):
                archives.append(download(row, archive))
                unpack(archive, output, budget, member=None if package else row['member'], package=package)
                archive.unlink()
            platform = lock['platforms'][args.platform]
            if args.runtime == 'codex':
                acquire(platform['codex'], destination / 'bin/codex')
            else:
                acquire(platform['bun'], destination / 'bin/bun')
                cpu = 'arm64' if args.platform == 'linux/arm64' else 'x64'
                for row in lock['packages']:
                    if row.get('os') and row['os'] != 'linux' or row.get('cpu') and row['cpu'] != cpu:
                        continue
                    location = safe_relative(row['destination'])
                    if not str(location).startswith('node_modules/'):
                        raise InstallError('archive_path_invalid')
                    acquire(row, destination / location, package=True)
                    metadata = json.loads((destination / location / 'package.json').read_bytes())
                    if (metadata['name'], metadata['version']) != (row['name'], row['version']):
                        raise InstallError('installation_package_identity_mismatch')
                sidecar = destination / 'native_runtime_omp_tools.mjs'
                sidecar.write_bytes((ROOT / 'tools/native_runtime_omp_tools.mjs').read_bytes())
                sidecar.chmod(0o600)
        manifest = source_manifest(destination)
        bundle = {'path': str(destination), 'manifest_sha256': digest(canonical(manifest)), 'platform': args.platform}
        if args.runtime == 'omp':bundle['bun_version'] = lock['bun_version']
        inspector(args.runtime, bundle)
        result = {'kind': 'native-tool-installation-receipt-v1', 'status': 'installed',
            'runtime': args.runtime, 'version': lock[args.runtime + '_version'],
            'lock_sha256': digest(lock_bytes), 'profile_fields': {'tool_bundle': bundle},
            'archives': archives, 'files': len(manifest), 'expanded_bytes': sum(row['size'] for row in manifest.values()),
            'execution_verified': False, 'next_check': 'isolated_native_handshake'}
        descriptor = os.open(args.receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'w') as stream:
            stream.write(json.dumps(result, indent=2) + '\n')
        return result
    except BaseException:
        shutil.rmtree(destination)
        raise


def preflight(args):
    receipt = json.loads(args.receipt.read_bytes())
    if receipt.get('kind') != 'native-tool-installation-receipt-v1' or receipt.get('runtime') not in ('codex', 'omp'):
        raise InstallError('installation_receipt_invalid')
    result = inspector(receipt['runtime'], receipt['profile_fields']['tool_bundle'])
    return {'status': 'ready_for_environment_check', 'runtime': receipt['runtime'],
            'profile_fields': receipt['profile_fields'], 'execution_verified': False,
            'environment_command': result['command'], 'next_check': 'isolated_native_handshake'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    command = commands.add_parser('install')
    command.add_argument('--runtime', choices=('codex', 'omp'), required=True)
    command.add_argument('--platform', choices=('linux/arm64', 'linux/amd64'), required=True)
    command.add_argument('--destination', type=Path, required=True)
    command.add_argument('--receipt', type=Path, required=True)
    command.add_argument('--lock', type=Path, default=LOCK)
    command = commands.add_parser('preflight')
    command.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = install(args) if args.command == 'install' else preflight(args)
    except (InstallError, RuntimeError, ContractError) as error:
        print(json.dumps({'status': 'failed', 'error': str(error)}))
        return 1
    except (OSError, KeyError, TypeError, ValueError, tarfile.TarError, zipfile.BadZipFile):
        print(json.dumps({'status': 'failed', 'error': 'installation_input_or_io_invalid'}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
