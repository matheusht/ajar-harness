"""Replay an offline v2 export and verify its journal's retained references."""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath

from engagement_contract import ContractError, MAX_PUBLICATION_BYTES, canonical, read_json
from engagement_controller import Controller, ControllerError, private_directory


def verify(root, *, check_result=False):
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
    if check_result:
        fields = ('engagement_id', 'scope_sha256', 'evidence_class', 'status', 'tasks',
                  'claims', 'closures', 'reviews', 'obligations', 'experiments', 'patches',
                  'network_operations', 'directions', 'usage', 'cleanup', 'resource_holds')
        expected = {name: state[name] for name in fields}
        expected.update(claim_acceptance='per_claim', external_action_authorized=False,
                        lab_artifacts=state['lab_artifacts'],
                        retained_evidence_objects=len(state['evidence_objects']),
                        research_guidance={name: contract_files[name]
                            for name in ('methodology.md', 'protocol.md') if name in contract_files})
        if canonical(read_json(root / 'result.json', private=True, max_bytes=MAX_PUBLICATION_BYTES)) != canonical(expected):
            raise ValueError('export_result_mismatch')
    return {'status': 'verified', 'engagement_id': state['engagement_id'],
            'revision': state['revision'], 'check': 'journal_reference_closure',
            'authenticity_verified': False, 'research_acceptance_verified': False,
            'result_consistency_verified': check_result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--check-result', action='store_true',
                        help='also compare result.json with the replayed journal projection')
    args = parser.parse_args()
    try:
        result = verify(args.bundle, check_result=args.check_result)
    except (ContractError, ControllerError, OSError, ValueError, KeyError, TypeError):
        print(json.dumps({'status': 'failed', 'check': 'journal_reference_closure'}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
