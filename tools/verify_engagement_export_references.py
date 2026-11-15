"""Replay an offline v2 export and verify its journal's retained references."""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath

from engagement_contract import ContractError, read_json
from engagement_controller import Controller, ControllerError, private_directory


def verify(root):
    root = Path(root)
    controller = Controller(root)
    manifest = read_json(root / 'manifest.json', private=True)
    if not isinstance(manifest, dict):
        raise ValueError('export_manifest_invalid')
    if manifest.get('kind') != 'engagement-result-bundle-v2':
        raise ValueError('export_kind_invalid')
    objects = root / 'objects'
    if objects.exists() or objects.is_symlink():
        private_directory(objects)
    events = controller._events()
    contract_files = events[0]['payload']['contract_files']
    if not isinstance(contract_files, dict):
        raise ValueError('export_contract_invalid')
    for name in contract_files:
        if (not isinstance(name, str) or not name
                or PurePosixPath(name).is_absolute()
                or any(part in ('', '.', '..') for part in name.split('/'))):
            raise ValueError('export_contract_path_invalid')
        path = root / 'contract' / name
        if path.resolve(strict=True) != path:
            raise ValueError('export_contract_path_invalid')
    state = controller._replay(events)
    if (manifest.get('engagement_id') != state['engagement_id']
            or type(manifest.get('revision')) is not int
            or manifest['revision'] != state['revision']):
        raise ValueError('export_journal_binding_invalid')
    return {'status': 'verified', 'engagement_id': state['engagement_id'],
            'revision': state['revision'], 'check': 'journal_reference_closure',
            'authenticity_verified': False, 'research_acceptance_verified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    args = parser.parse_args()
    try:
        result = verify(args.bundle)
    except (ContractError, ControllerError, OSError, ValueError, KeyError, TypeError):
        print(json.dumps({'status': 'failed', 'check': 'journal_reference_closure'}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
