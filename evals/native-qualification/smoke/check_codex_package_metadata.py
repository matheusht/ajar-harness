#!/usr/bin/env python3
"""Original package metadata survives validated extraction; invalid identities refuse."""
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'tools'))
import install_native_tools as installer


class PackageMetadata(unittest.TestCase):
    def extract(self, payload, platform='linux/amd64', member='codex-package.json', link=False, helper_machine=None, helper_mode=0o755, helper_missing=False, helper_link=False):
        with tempfile.TemporaryDirectory(prefix='codex-metadata-test-') as name:
            root = Path(name)
            archive = root / 'package.tgz'
            with tarfile.open(archive, 'w:gz') as tar:
                info = tarfile.TarInfo(member)
                info.size = len(payload)
                if link:
                    info.type, info.linkname = tarfile.SYMTYPE, '/outside'
                tar.addfile(info, io.BytesIO(payload))
                if not helper_missing:
                    machine = helper_machine or (183 if platform == 'linux/arm64' else 62)
                    data = bytes([127,69,76,70,2,1]) + bytes(12) + machine.to_bytes(2, 'little')
                    helper = tarfile.TarInfo('codex-resources/bwrap')
                    helper.size, helper.mode = len(data), helper_mode
                    if helper_link:helper.type, helper.linkname = tarfile.SYMTYPE, '/outside'
                    tar.addfile(helper, io.BytesIO(data))
            destination = root / 'output'; destination.mkdir()
            installer.unpack_codex_package_support(archive, destination, [0, 0], platform, '0.166.0')
            self.assertEqual((destination / 'codex-package.json').read_bytes(), payload)

    def test_exact_bytes_both_architectures(self):
        for platform, target in [('linux/amd64', 'x86_64'), ('linux/arm64', 'aarch64')]:
            with self.subTest(platform=platform):
                self.extract(json.dumps({'version':'0.166.0', 'target':target+'-unknown-linux-musl',
                    'extra':'retained upstream field'}, indent=3).encode()+b'\n', platform)

    def test_invalid_helpers(self):
        payload = b'{"version":"0.166.0","target":"x86_64-unknown-linux-musl"}'
        for options in ({'helper_machine':183}, {'helper_mode':0o644},
                        {'helper_missing':True}, {'helper_link':True}):
            with self.subTest(options=options), self.assertRaises(installer.InstallError):
                self.extract(payload, **options)

    def test_wrong_version(self):
        with self.assertRaises(installer.InstallError):
            self.extract(b'{"version":"0.0.0","target":"x86_64-unknown-linux-musl"}')

    def test_wrong_target(self):
        with self.assertRaises(installer.InstallError):
            self.extract(b'{"version":"0.166.0","target":"aarch64-unknown-linux-musl"}')

    def test_missing_metadata(self):
        with self.assertRaises(installer.InstallError):
            self.extract(b'{}', member='unrelated')

    def test_malformed_metadata(self):
        for payload in (b'not-json', b'null', b'[]', b'\xff'):
            with self.subTest(payload=payload), self.assertRaises(installer.InstallError):
                self.extract(payload)

    def test_links_refused(self):
        with self.assertRaises(installer.InstallError):
            self.extract(b'', link=True)

    def test_traversal_refused(self):
        with self.assertRaises(installer.InstallError):
            self.extract(b'{}', member='../codex-package.json')


if __name__ == '__main__':
    unittest.main()
