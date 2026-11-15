#!/usr/bin/env python3
"""Offline packaging checks; do not execute native assets or claim acceptance."""
import io
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
import sys
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'tools'))
import native_model_addon as addon


def main():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        row = {'name': '@oh-my-pi/pi-natives-linux-x64', 'version': '18.20.0', 'os': 'linux', 'cpu': 'x64'}
        lock = {'omp_version': '18.20.0', 'packages': [row]}
        metadata = {**row, 'os': ['linux'], 'cpu': ['x64'], 'main': './pi_natives.linux-x64-baseline.node'}
        header = b'\x7fELF\x02\x01' + b'\0' * 12 + (62).to_bytes(2, 'little')
        files = {'package.json': json.dumps(metadata).encode(), 'LICENSE': b'MIT',
                 'THIRD-PARTY-NOTICES.txt': b'notices', 'README.md': b'readme',
                 **{'pi_natives.linux-x64-' + variant + '.node': header for variant in ('baseline', 'modern')}}
        for scenario in ('valid', 'wrong-version', 'wrong-platform', 'missing-notice', 'archive-symlink'):
            archive = root / (scenario + '.tgz')
            contents = dict(files)
            if scenario == 'wrong-version':
                contents['package.json'] = json.dumps({**metadata, 'version': '0.0.0'}).encode()
            if scenario == 'wrong-platform':
                contents['pi_natives.linux-x64-modern.node'] = header[:18] + (183).to_bytes(2, 'little')
            if scenario == 'missing-notice':
                del contents['LICENSE']
            with tarfile.open(archive, 'w:gz') as stream:
                for name, value in contents.items():
                    entry = tarfile.TarInfo('package/' + name)
                    entry.size = len(value)
                    if scenario == 'archive-symlink' and name.endswith('modern.node'):
                        entry.type = tarfile.SYMTYPE
                        entry.linkname = '/outside'
                        entry.size = 0
                        stream.addfile(entry)
                    else:
                        stream.addfile(entry, io.BytesIO(value))
            def download(selected, path):
                assert selected == row
                shutil.copyfile(archive, path)
                return {'integrity': 'synthetic-fixture'}
            destination = root / (scenario + '-assets')
            with patch.object(addon, 'download', download):
                try:
                    result = addon.prepare_omp_addon_assets(lock, 'linux/amd64', destination)
                except addon.InstallError:
                    assert scenario != 'valid' and not destination.exists()
                else:
                    assert scenario == 'valid' and result['execution_verified'] is False
                    assert len(result['assets']) == 6
                    assert all(p.stat().st_mode & 0o777 == 0o444 for p in destination.rglob('*') if p.is_file())
        for destination in (root / 'valid-assets', root / 'linked'):
            if destination.name == 'linked':
                destination.symlink_to(root / 'valid-assets', target_is_directory=True)
            try:
                addon.prepare_omp_addon_assets(lock, 'linux/amd64', destination)
            except addon.InstallError:
                pass
            else:
                raise AssertionError('existing destination accepted')
    print('passed: 7 offline addon packaging cases; no native execution')


if __name__ == '__main__':
    main()
