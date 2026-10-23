#!/usr/bin/env python3
"""Offline source-review evidence check; no model, target, or provider calls."""

import json
import hashlib
import importlib.util
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
import native_research as runner
spec = importlib.util.spec_from_file_location(
    'fresh_review', ROOT / 'experiments/native-review-qualification/fresh_review.py')
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def main():
    # A large unchanged source tree must not consume the public review limit six times.
    before = {f'package/{i:05d}/source.go': f'{i:064x}' for i in range(2000)}
    after = dict(before)
    summary = runner._source_output_summary(before, after)
    assert summary == {'file_count': 2000, 'changed_files': {}, 'missing_files': []}
    evidence = {'cases': {case: {'outputs': {role: summary for role in
                ('target', 'review-target-1', 'review-target-2')}}
                for case in ('effect', 'control')}}
    assert len(json.dumps(evidence, sort_keys=True, indent=2).encode()) < 1024 * 1024

    after['package/00001/source.go'] = 'f' * 64
    after.pop('package/00002/source.go')
    after['result.txt'] = 'e' * 64
    summary = runner._source_output_summary(before, after)
    assert summary['file_count'] == 2000
    assert summary['changed_files'] == {'package/00001/source.go': 'f' * 64,
                                        'result.txt': 'e' * 64}
    assert summary['missing_files'] == ['package/00002/source.go']
    assert before['package/00001/source.go'] != summary['changed_files']['package/00001/source.go']
    with TemporaryDirectory(prefix='source-review-evidence-') as raw:
        directory = Path(raw)
        path = directory / 'manifest-effect-target.json'
        original = directory / 'files.json'
        runner._write_json(original, after, once=True)
        digest = runner._publish_source_manifest(path, after, review.validate_public_bytes)
        assert path.is_file() and path.stat().st_mode & 0o222 == 0
        assert digest == hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == hashlib.sha256(original.read_bytes()).hexdigest()
        assert json.loads(path.read_bytes()) == after
        unsafe = directory / 'manifest-unsafe.json'
        try:
            runner._publish_source_manifest(unsafe, {'password=secret': '0' * 64},
                                            review.validate_public_bytes)
        except ValueError:
            assert not unsafe.exists()
        else:
            raise AssertionError('sensitive manifest was published')
    print('PASS: unchanged tree compacted; changed, added, and missing files retained; provider_calls=0 target_calls=0')


if __name__ == '__main__':
    main()
