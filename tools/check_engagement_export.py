"""Check exported bytes only, not signer identity or research acceptance."""
import argparse
import hashlib
import json
import re
from pathlib import Path


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate key')
        result[key] = value
    return result


def verify(root):
    if root.absolute() != root.resolve():
        return ['symlink_root']
    if (root / 'manifest.json').is_symlink():
        return ['symlink:manifest.json']
    if not (root / 'manifest.json').is_file():
        return ['invalid_manifest']
    try:
        manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'), object_pairs_hook=unique_object)
    except (ValueError, OSError):
        return ['invalid_manifest']
    if (not isinstance(manifest, dict)
            or set(manifest) != {'kind', 'engagement_id', 'revision', 'files'}
            or manifest['kind'] != 'engagement-result-bundle-v2'
            or not isinstance(manifest['engagement_id'], str) or not manifest['engagement_id']
            or type(manifest['revision']) is not int or manifest['revision'] < 0
            or not isinstance(manifest['files'], dict) or 'result.json' not in manifest['files']
            or any(not isinstance(value, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', value)
                   for value in manifest['files'].values())):
        return ['invalid_manifest']
    errors = []
    for name, expected in manifest['files'].items():
        if (not name or '\x00' in name or name.startswith('/') or '\\' in name
                or any(part in ('', '.', '..') for part in name.split('/'))
                or name == 'manifest.json'):
            errors.append('unsafe_path:' + name)
            continue
        path = root / name
        if any(part.is_symlink() for part in [path, *path.parents]):
            errors.append('symlink:' + name)
            continue
        if not path.is_file():
            errors.append('missing_file:' + name)
            continue
        with path.open('rb') as stream:
            actual = 'sha256:' + hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != expected:
            errors.append('digest_mismatch:' + name)
    for path in root.rglob('*'):
        name = path.relative_to(root).as_posix()
        if path.is_symlink():
            errors.append('symlink:' + name)
        elif path.is_file() and name != 'manifest.json' and name not in manifest['files']:
            errors.append('unlisted_file:' + name)
        elif not path.is_dir() and not path.is_file():
            errors.append('special_file:' + name)
    return sorted(set(errors))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    args = parser.parse_args()
    try:
        errors = verify(args.bundle)
    except (OSError, ValueError, RuntimeError):
        errors = ['unreadable_bundle']
    print(json.dumps({'integrity': 'failed' if errors else 'verified',
                      'authenticity': 'not_assessed', 'acceptance': 'not_assessed', 'errors': errors}))
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
