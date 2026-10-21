#!/usr/bin/env python3
"""Prewritten E2E checks on existing frozen bytes; no model or application run."""
import copy
import json
from pathlib import Path
import tempfile

from handoff import prepare_packet, stopped_request, verify_packet

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MANIFEST = ROOT / 'experiments/native-review-qualification/T03-NATIVE-HANDOFF-PREFLIGHT-20261020/HANDOFF.json'


def rejected(action):
    try:
        action()
    except (ValueError, FileNotFoundError):
        return
    raise AssertionError('invalid packet was accepted')


def main():
    checks = []
    with tempfile.TemporaryDirectory(prefix='fresh-handoff-check-') as name:
        work = Path(name)
        first = prepare_packet(ROOT, MANIFEST, 'T03-v1', work / 'v1')
        second = prepare_packet(ROOT, MANIFEST, 'T03-v2', work / 'v2', first)
        assert first['review_status'] == second['review_status'] == 'not_run'
        assert second['previous_request']['review_status'] == 'not_run'
        assert second['requires_actual_prior_review'] and not second['carry_forward_review']
        assert first['input_id'] != second['input_id']
        assert second['files']['app.py'] == first['files']['app.py']
        assert {'CLAIMS.md', 'RAW-SETUP.json', 'policy-v2.json'} <= set(second['changed_files'])
        checks.append('source/claim/raw binding; changed condition requires actual review')
        forged = copy.deepcopy(first)
        forged['review_status'] = 'confirmed'
        rejected(lambda: prepare_packet(ROOT, MANIFEST, 'T03-v2', work / 'forged-review', forged))
        stale = copy.deepcopy(first)
        stale['input_id'] = '0' * 64
        rejected(lambda: prepare_packet(ROOT, MANIFEST, 'T03-v2', work / 'stale-review', stale))
        checks.append('prior preparation cannot author a reviewer outcome or stale input ID')
        for group, request in [('v1', first), ('v2', second)]:
            verify_packet(work / group, request)
            assert request['allowance']['status'] == 'unaccepted'
            assert request['allowance']['remaining'] is None
            assert not any('EXPECTED' in p or 'PREP-RECEIPT' in p for p in request['files'])
        checks.append('exact allowlist, raw material and no invented allowance')
        bad_manifest = work / 'HANDOFF.json'
        manifest = json.loads(MANIFEST.read_text())
        manifest['input_groups']['T03-v1']['reviewer_visible_sha256']['EXPECTED-CHECKS.md'] = '0' * 64
        bad_manifest.write_text(json.dumps(manifest))
        rejected(lambda: prepare_packet(ROOT, bad_manifest, 'T03-v1', work / 'bad'))
        assert not (work / 'bad').exists()
        checks.append('edited manifest and injected answer rejected before staging')
        app = work / 'v1/app.py'
        original = app.read_bytes()
        app.write_bytes(original + b'\n# disposable corruption\n')
        rejected(lambda: verify_packet(work / 'v1', first))
        app.unlink()
        rejected(lambda: verify_packet(work / 'v1', first))
        app.write_bytes(original)
        answer = work / 'v1/EXPECTED-CHECKS.md'
        answer.write_text('observer-only marker, no expected verdict')
        rejected(lambda: verify_packet(work / 'v1', first))
        answer.unlink()
        app.unlink()
        app.symlink_to(work / 'v2/app.py')
        rejected(lambda: verify_packet(work / 'v1', first))
        app.unlink()
        app.write_bytes(original)
        verify_packet(work / 'v1', first)
        checks.append('tampered, missing, extra and symlink staged files rejected')
        lead = prepare_packet(ROOT, MANIFEST, 'T06-strong-lead', work / 'lead')
        before = copy.deepcopy(lead)
        stopped = stopped_request(lead, 'shared_allowance_unaccepted')
        assert lead == before and stopped['unfinished'] == lead['unfinished']
        text = '\n'.join(x['text'] for x in stopped['unfinished']['claim_documents'])
        assert all(x in text for x in ('B:', 'delegate', 'next check', 'C-EXT'))
        assert stopped['review_status'] == 'not_run' and stopped['unfinished']['status'] == 'unreviewed'
        assert stopped['dispositions'] == []
        checks.append('stop preserves complete strong-lead basis, condition and next check')
    print(json.dumps({'status': 'handoff_checks_passed', 'checks': checks,
                      'provider_calls': 0, 'native_review': 'not_run'}, indent=2))


if __name__ == '__main__':
    main()
