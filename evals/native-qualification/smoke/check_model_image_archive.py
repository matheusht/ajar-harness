#!/usr/bin/env python3
"""Never-started image readback keeps exact bytes, ownership and directory bounds."""
import hashlib
import io
import tarfile
import unittest
from check_model_image_docker_e2e import read_runtime_archive


class RuntimeArchive(unittest.TestCase):
    def fixture(self, resources=True, mutation=None):
        content = {'bin/model': b'fixture-model'}
        if resources:
            content['codex-resources/bwrap'] = b'fixture-helper'
        expected = {name: {'size':len(data), 'mode':0o555,
                    'sha256':'sha256:'+hashlib.sha256(data).hexdigest()} for name,data in content.items()}
        rows = []
        for name in ['runtime', 'runtime/bin'] + (['runtime/codex-resources'] if resources else []):
            row=tarfile.TarInfo(name);row.type=tarfile.DIRTYPE;row.mode=0o755
            rows.append((row,b''))
        for name,data in content.items():
            row=tarfile.TarInfo('runtime/'+name);row.size=len(data);row.mode=0o555
            rows.append((row,data))
        if mutation:mutation(rows)
        output=io.BytesIO()
        with tarfile.open(fileobj=output,mode='w') as archive:
            for row,data in rows:archive.addfile(row,io.BytesIO(data))
        output.seek(0)
        return output,expected

    def test_original_and_resources(self):
        for resources in (False,True):
            with self.subTest(resources=resources):
                stream,expected=self.fixture(resources)
                observed=read_runtime_archive(stream,expected)
                self.assertEqual(set(observed),set(expected))
                self.assertTrue(all(row['uid']==row['gid']==0 for row in observed.values()))

    def test_resources_require_manifest_entry(self):
        def extra(rows):
            row=tarfile.TarInfo('runtime/codex-resources')
            row.type=tarfile.DIRTYPE;row.mode=0o755
            rows.append((row,b''))
        stream,expected=self.fixture(resources=False,mutation=extra)
        with self.assertRaises(RuntimeError):read_runtime_archive(stream,expected)

    def test_mutations_refused(self):
        def extra(rows):
            row=tarfile.TarInfo('runtime/unlisted');row.type=tarfile.DIRTYPE;row.mode=0o755
            rows.append((row,b''))
        def link(rows):
            rows[-1][0].type=tarfile.SYMTYPE;rows[-1][0].linkname='/outside';rows[-1][0].size=0
        mutations = {
            'missing-directory':lambda r:r.pop(2),
            'duplicate-directory':lambda r:r.append(r[2]),
            'unexpected-directory':extra,
            'directory-mode':lambda r:setattr(r[2][0],'mode',0o700),
            'directory-owner':lambda r:setattr(r[2][0],'uid',1000),
            'file-mode':lambda r:setattr(r[-1][0],'mode',0o777),
            'file-owner':lambda r:setattr(r[-1][0],'gid',1000),
            'file-bytes':lambda r:r.__setitem__(-1,(r[-1][0],b'x'*len(r[-1][1]))),
            'missing-file':lambda r:r.pop(),
            'duplicate-file':lambda r:r.append(r[-1]),
            'traversal':lambda r:setattr(r[-1][0],'name','runtime/../outside'),
            'link':link,
        }
        for name,mutation in mutations.items():
            with self.subTest(name=name):
                stream,expected=self.fixture(mutation=mutation)
                with self.assertRaises(RuntimeError):read_runtime_archive(stream,expected)


if __name__ == '__main__':
    unittest.main()
