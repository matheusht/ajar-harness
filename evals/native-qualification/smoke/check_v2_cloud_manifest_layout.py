#!/usr/bin/env python3
"""Source-only T02 manifest selection and staging checks."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile


CHECKER = Path(__file__).resolve().with_name('check_v2_cloud_owned_source.py')
spec = importlib.util.spec_from_file_location('t02_source_checker', CHECKER)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
RELATIVE = 'evals/native-qualification/smoke/fixture.bin'
SIDECAR = 'evals/native-qualification/t02-cloud-transfer-20261020/SOURCE-MANIFEST.json'


def manifest(data):
    return {'schema_version': 1, 'kind': 't02-cloud-source', 'files': [
        {'path': RELATIVE, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}]}


def write(root, data, placement):
    source = root / RELATIVE
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(data)
    source.chmod(0o755)
    path = root / placement
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest(data)) + '\n')
    return source, path


with tempfile.TemporaryDirectory(prefix='t02-manifest-layout-') as directory:
    temp = Path(directory).resolve()
    local = temp / 'local'
    source, sidecar = write(local, b'local fixture', SIDECAR)
    assert checker.select_manifest(local) == sidecar
    staged = temp / 'staged-local'
    assert checker.stage_sources(local, staged, sidecar) == 1
    assert (staged / RELATIVE).read_bytes() == source.read_bytes()
    assert (staged / RELATIVE).stat().st_mode & 0o111

    extracted = temp / 'extracted'
    source, root_manifest = write(extracted, b'extracted fixture', 'SOURCE-MANIFEST.json')
    _, sidecar = write(extracted, b'extracted fixture', SIDECAR)
    sidecar.write_text(json.dumps(manifest(b'wrong sidecar')) + '\n')
    assert checker.select_manifest(extracted) == root_manifest
    staged = temp / 'staged-extracted'
    assert checker.stage_sources(extracted, staged, root_manifest) == 1
    assert (staged / RELATIVE).read_bytes() == source.read_bytes()

    source.write_bytes(source.read_bytes() + b'!')
    rejected = temp / 'staged-mutated'
    try:
        checker.stage_sources(extracted, rejected, root_manifest)
    except ValueError as error:
        assert str(error) == 'manifest_source_mismatch'
    else:
        raise AssertionError('changed extracted source accepted')
    assert not rejected.exists()

    root_manifest.write_text('{broken')
    try:
        checker.stage_sources(extracted, temp / 'staged-bad-root', checker.select_manifest(extracted))
    except ValueError as error:
        assert str(error) == 'manifest_invalid'
    else:
        raise AssertionError('invalid root manifest fell back to sidecar')
    assert not (temp / 'staged-bad-root').exists()

print('PASS: local sidecar, ZIP-root precedence, executable staged bytes, mutated/invalid source rejection; no Docker/provider/CI')
