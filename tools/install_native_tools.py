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

from engagement_contract import ContractError, canonical, digest, read_bytes, source_manifest
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


def download(row, output, *, expected_size=None):
    limit = MAX_ARCHIVE if expected_size is None else expected_size
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
            if expected_length is not None and expected_length > limit:
                raise InstallError('archive_too_large' if expected_size is None else 'archive_size_mismatch')
            while chunk := response.read(1024 * 1024):
                count += len(chunk)
                if count > limit:raise InstallError('archive_too_large' if expected_size is None else 'archive_size_mismatch')
                checksum.update(chunk)
                stream.write(chunk)
            if expected_length is not None and count != expected_length:
                raise InstallError('archive_download_failed')
    except InstallError:
        raise
    except Exception:
        raise InstallError('archive_download_failed') from None
    if expected_size is not None and count != expected_size:
        raise InstallError('archive_size_mismatch')
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


def unpack_codex_package_support(archive, destination, budget, platform, version):
    path = destination / 'codex-package.json'
    unpack(archive, path, budget, member='codex-package.json')
    try:
        metadata = json.loads(path.read_bytes())
        target = {'linux/arm64': 'aarch64', 'linux/amd64': 'x86_64'}[platform] + '-unknown-linux-musl'
        if metadata.get('version') != version or metadata.get('target') != target:
            raise InstallError('native_package_identity_mismatch')
    except (ValueError, AttributeError, UnicodeError):
        raise InstallError('native_package_identity_mismatch') from None
    path.chmod(0o444)
    helper = destination / 'codex-resources/bwrap'
    unpack(archive, helper, budget, member='codex-resources/bwrap')
    with helper.open('rb') as stream:header = stream.read(20)
    machine = {'linux/arm64': 183, 'linux/amd64': 62}[platform]
    if (len(header) != 20 or header[:6] != bytes([127, 69, 76, 70, 2, 1]) or
            int.from_bytes(header[18:20], 'little') != machine):
        raise InstallError('native_package_helper_platform_mismatch')
    if not helper.stat().st_mode & 0o111:
        raise InstallError('native_package_helper_not_executable')
    helper.chmod(0o555)
    helper.parent.chmod(0o755)


def inspector(kind, bundle):
    module = importlib.import_module('native_runtime_' + kind)
    return module.inspect_tool_bundle({'kind': kind, 'version': module.Runtime.version, 'tool_bundle': bundle})


def installation_inputs(args):
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
    return lock_bytes, lock, destination


def write_receipt(path, result):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        stream.write(json.dumps(result, indent=2) + '\n')


def install(args):
    lock_bytes, lock, destination = installation_inputs(args)
    budget, archives = [0, 0], []
    try:
        with tempfile.TemporaryDirectory(prefix='.oslit-download-', dir=destination.parent) as temporary:
            archive = Path(temporary) / 'archive'
            def acquire(row, output, *, package=False, codex=False):
                archives.append(download(row, archive))
                unpack(archive, output, budget, member=None if package else row['member'], package=package)
                if codex:
                    unpack_codex_package_support(archive, destination, budget, args.platform, lock['codex_version'])
                archive.unlink()
            platform = lock['platforms'][args.platform]
            if args.runtime == 'codex':
                acquire(platform['codex'], destination / 'bin/codex', codex=True)
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
        write_receipt(args.receipt, result)
        return result
    except BaseException:
        shutil.rmtree(destination)
        raise


def model_image_context(args):
    if not re.fullmatch(r'[a-z0-9][a-z0-9./:_-]*@sha256:[0-9a-f]{64}', args.base_image):
        raise InstallError('model_base_image_invalid')
    lock_bytes, lock, destination = installation_inputs(args)
    budget, archives = [0, 0], []
    runtime = destination / 'runtime'
    try:
        with tempfile.TemporaryDirectory(prefix='.oslit-download-', dir=destination.parent) as temporary:
            archive = Path(temporary) / 'archive'
            platform = lock['platforms'][args.platform]
            binaries = [('model', platform['codex'] if args.runtime == 'codex' else platform['model_omp'])]
            if args.runtime == 'codex':binaries.append(('bun', platform['bun']))
            for name, row in binaries:
                output = runtime / 'bin' / name
                raw = args.runtime == 'omp'
                if raw and (row.get('format') != 'raw' or type(row.get('size')) is not int
                            or not 0 < row['size'] <= MAX_EXPANDED):
                    raise InstallError('model_asset_invalid')
                archives.append(download(row, archive, expected_size=row['size'] if raw else None))
                if raw:
                    with archive.open('rb') as stream:
                        write_member(stream, output, row['size'], True, budget)
                else:
                    unpack(archive, output, budget, member=row['member'])
                    if args.runtime == 'codex' and name == 'model':
                        unpack_codex_package_support(archive, runtime, budget, args.platform, lock['codex_version'])
                archive.unlink()
                with output.open('rb') as stream:header = stream.read(20)
                if (len(header) != 20 or header[:6] != b'\x7fELF\x02\x01' or
                        int.from_bytes(header[18:20], 'little') != {'linux/arm64': 183, 'linux/amd64': 62}[args.platform]):
                    raise InstallError('native_bundle_platform_mismatch')
                output.chmod(0o555)
            if args.runtime == 'omp':
                from native_model_addon import prepare_omp_addon_assets
                assets = Path(temporary) / 'addon-assets'
                addon = prepare_omp_addon_assets(lock, args.platform, assets, budget=budget)
                shutil.copytree(assets, runtime, dirs_exist_ok=True)
                archives.append(addon['archive'])
            helpers = ['engagement_network_bridge.py', 'native_runtime_bootstrap.py']
            if args.runtime == 'codex':helpers.append('native_runtime_codex_exec.mjs')
            for name in helpers:
                try:data = read_bytes(ROOT / 'tools' / name)
                except (OSError, ContractError):raise InstallError('model_helper_invalid') from None
                (runtime / name).write_bytes(data)
                (runtime / name).chmod(0o444)
        runtime.chmod(0o755)
        (runtime / 'bin').chmod(0o755)
        (destination / 'Dockerfile').write_text(
            'FROM ' + args.base_image + '\nCOPY --chown=0:0 runtime/ /runtime/\n'
            'ENV PATH=/runtime/bin:/usr/local/bin:/usr/bin:/bin\n'
            'USER 1000:1000\nWORKDIR /work\nENTRYPOINT []\nCMD ["/bin/true"]\n')
        (destination / '.dockerignore').write_text('*\n!Dockerfile\n!runtime/\n!runtime/**\n')
        for name in ('Dockerfile', '.dockerignore'):(destination / name).chmod(0o600)
        manifest = source_manifest(runtime)
        result = {'kind': 'native-model-image-context-receipt-v1', 'status': 'prepared',
            'runtime': args.runtime, 'version': lock[args.runtime + '_version'], 'platform': args.platform,
            'base_image': args.base_image, 'lock_sha256': digest(lock_bytes),
            'profile_fields': {'executable': {'path': str(runtime / 'bin/model'),
                                            'sha256': manifest['bin/model']['sha256']}},
            'runtime_manifest': manifest, 'context_manifest_sha256': digest(canonical(source_manifest(destination))),
            'archives': archives, 'execution_verified': False, 'next_check': 'build_and_verify_model_image'}
        write_receipt(args.receipt, result)
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
    for name in ('install', 'model-image-context'):
        command = commands.add_parser(name)
        command.add_argument('--runtime', choices=('codex', 'omp'), required=True)
        command.add_argument('--platform', choices=('linux/arm64', 'linux/amd64'), required=True)
        command.add_argument('--destination', type=Path, required=True)
        command.add_argument('--receipt', type=Path, required=True)
        command.add_argument('--lock', type=Path, default=LOCK)
        if name == 'model-image-context':command.add_argument('--base-image', required=True)
    command = commands.add_parser('preflight')
    command.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = {'install': install, 'model-image-context': model_image_context, 'preflight': preflight}[args.command](args)
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
