"""Acquire immutable OMP addon assets; never execute downloaded package code."""
import json
import os
from pathlib import Path
import shutil
import tempfile

from engagement_contract import canonical, digest, source_manifest
from install_native_tools import InstallError, download, unpack


def prepare_omp_addon_assets(lock, platform, destination, *, budget=None):
    cpu = {'linux/amd64': 'x64', 'linux/arm64': 'arm64'}.get(platform)
    if cpu is None or lock.get('omp_version') != '18.20.0':
        raise InstallError('model_addon_platform_or_version_invalid')
    name = '@oh-my-pi/pi-natives-linux-' + cpu
    rows = [row for row in lock['packages'] if row.get('name') == name]
    if len(rows) != 1 or any(rows[0].get(key) != value for key, value in
            {'version': '18.20.0', 'os': 'linux', 'cpu': cpu}.items()):
        raise InstallError('model_addon_lock_invalid')
    destination = Path(destination)
    if (not destination.is_absolute() or destination.exists() or destination.is_symlink()
            or destination.parent.resolve() != destination.parent or not destination.parent.is_dir()):
        raise InstallError('model_addon_destination_invalid')
    filenames = (['pi_natives.linux-x64-baseline.node', 'pi_natives.linux-x64-modern.node']
                 if cpu == 'x64' else ['pi_natives.linux-arm64.node'])
    with tempfile.TemporaryDirectory(prefix='.omp-addon-', dir=destination.parent) as temporary:
        root = Path(temporary)
        archive = root / 'package.tgz'
        receipt = download(rows[0], archive)
        package = root / 'package'
        unpack(archive, package, budget if budget is not None else [0, 0], package=True)
        metadata = json.loads((package / 'package.json').read_bytes())
        if (metadata.get('name') != name or metadata.get('version') != '18.20.0'
                or metadata.get('main') != './' + filenames[0]
                or metadata.get('os') != ['linux'] or metadata.get('cpu') != [cpu]):
            raise InstallError('model_addon_package_identity_invalid')
        for filename in filenames:
            with (package / filename).open('rb') as stream:
                header = stream.read(20)
            if (len(header) != 20 or header[:6] != b'\x7fELF\x02\x01'
                    or int.from_bytes(header[18:20], 'little') != (62 if cpu == 'x64' else 183)):
                raise InstallError('model_addon_binary_platform_invalid')
        documents = ['package.json', 'LICENSE', 'THIRD-PARTY-NOTICES.txt', 'README.md']
        if any(not (package / filename).is_file() for filename in documents):
            raise InstallError('model_addon_notices_missing')
        destination.mkdir(mode=0o700)
        try:
            (destination / 'bin').mkdir(mode=0o755)
            for filename in filenames:
                target = destination / 'bin' / filename
                shutil.copyfile(package / filename, target)
                os.chmod(target, 0o444)
            for filename in documents:
                target = destination / ('omp-native-' + filename)
                shutil.copyfile(package / filename, target)
                os.chmod(target, 0o444)
            manifest = source_manifest(destination)
            return {'kind': 'omp-model-addon-assets-v1', 'runtime': 'omp', 'version': '18.20.0',
                    'platform': platform, 'archive': receipt,
                    'assets': manifest, 'manifest_sha256': digest(canonical(manifest)),
                    'execution_verified': False}
        except Exception:
            shutil.rmtree(destination)
            raise
