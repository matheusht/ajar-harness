#!/usr/bin/env python3
"""Provider-free composition check for post-stop native review assessment."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.native_research import _poststop_review_disposition


def sha(value):
    return hashlib.sha256(value).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    output = parser.parse_args().output
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    report = {'status': 'fail', 'classification': 'synthetic composition only',
              'provider_calls': 0, 'docker_calls': 0, 'target_calls': 0, 'checks': []}
    request_id = '1' * 32
    creation_ids = ['2' * 32, '3' * 32]
    ordinary_ids = ['4' * 32, '5' * 32]
    denial_id, reviewer_dispatch, effect_dispatch = '6' * 32, '7' * 32, '8' * 32
    role, session = 'reviewer-1', 'ses_Poststop1'
    action_line = 9
    action = {'line': action_line, 'command_sha256': sha(b'run bounded check'),
              'input_sha256': sha(b'input'), 'output_sha256': sha(b'output')}
    request = {'input_id': 'a' * 64, 'selection_sha256': 'b' * 64,
               'source_manifest_sha256': 'c' * 64}
    review = {'status': 'native_turn_observed_unassessed', 'reviewer_role': role,
              'session_id': session, 'packet_request_sha256': 'e' * 64,
              'same_original_allowance': True,
              'native': {'dispatch_id': reviewer_dispatch, 'role': role,
                         'session_id': session, 'native_trace_sha256': 'd' * 64,
                         'review_target_source_sha256': request['source_manifest_sha256']}}
    material = {'kind': 'native-review-material-v1', 'status': 'captured',
                'input_id': request['input_id'], 'dispatch_id': reviewer_dispatch,
                'session_id': session, 'packet_request_sha256': 'e' * 64,
                'native_trace_sha256': 'd' * 64,
                'source_revision': 'f' * 64, 'evidence_revision': '0' * 64,
                'shell_actions': [action]}
    trace = {'kind': 'protected-native-event-trace-v1', 'session_id': session,
             'events': [{'line': action_line, 'part_type': 'tool', 'tool': 'shell',
                         'status': 'completed', 'session_matches': True,
                         'input_sha256': action['input_sha256'],
                         'output_sha256': action['output_sha256']}]}
    reviewer_origin = {'kind': 'native-origin-transport-proof-v1',
                       'status': 'process_request_attributed', 'dispatch_id': reviewer_dispatch,
                       'role': role, 'target': 'review-target-1',
                       'source_manifest_sha256': request['source_manifest_sha256'],
                       'native_trace_sha256': 'd' * 64,
                       'native_tool_claims': [{'line': action_line, 'tool': 'shell',
                           'input_sha256': action['input_sha256'],
                           'output_sha256': action['output_sha256'],
                           'request_ids': ['9' * 32]}],
                       'broker_request_ids': ['9' * 32]}
    semantic = {'status': 'effect_and_controls_observed',
                'scope': 't01_original_vulnerable_arm',
                'creation_request_ids': creation_ids, 'ordinary_request_ids': ordinary_ids,
                'denial_request_id': denial_id, 'effect_request_id': request_id,
                'effect_dispatch_id': effect_dispatch}
    effect_origins = {}
    for dispatch, ids in [(effect_dispatch, [request_id]),
                          ('a1' * 16, creation_ids), ('a2' * 16, ordinary_ids),
                          ('a3' * 16, [denial_id])]:
        effect_origins[dispatch] = {'kind': 'native-origin-transport-proof-v1',
            'status': 'process_request_attributed', 'dispatch_id': dispatch,
            'role': 'researcher', 'target': 'target',
            'broker_request_ids': ids}

    def decide(**overrides):
        inputs = {'role': role, 'dispatch_id': reviewer_dispatch,
                  'effect_dispatch_id': effect_dispatch, 'effect_request_id': request_id,
                  'review': review, 'material': material, 'request': request, 'trace': trace,
                  'reviewer_origin': reviewer_origin, 'semantic': semantic,
                  'effect_origins': effect_origins}
        inputs.update(overrides)
        return _poststop_review_disposition(**inputs)

    def check(value, name):
        report['checks'].append({'name': name, 'pass': bool(value)})

    positive = decide()
    report['positive_result'] = positive
    check(positive.get('status') == 'candidate_for_operator_review',
          'effect, controls, reviewer action and all origin proofs compose')
    check(positive.get('qualification') == 'partial'
          and positive.get('lead_dispositions') == 'unfinished_unassessed'
          and positive.get('clean_replay') == positive.get('fixed_control') == 'not_assessed',
          'candidate preserves unfinished leads and incomplete #159 limits')
    check(decide(semantic=None).get('status') == 'held',
          'missing semantic verifier holds')
    check(decide(effect_origins={effect_dispatch: effect_origins[effect_dispatch]}).get('status') == 'held',
          'missing decisive control origin holds')
    altered = dict(reviewer_origin, role='reviewer-2')
    check(decide(reviewer_origin=altered).get('status') == 'held',
          'reviewer role mismatch holds')
    altered = dict(reviewer_origin, native_tool_claims=[])
    check(decide(reviewer_origin=altered).get('status') == 'held',
          'unattributed reviewer action holds')
    altered = dict(semantic, effect_request_id='f' * 32)
    check(decide(semantic=altered).get('status') == 'held',
          'effect key mismatch holds')
    check(all(item['pass'] for item in report['checks']), 'all synthetic checks pass')
    report['status'] = 'pass' if all(item['pass'] for item in report['checks']) else 'fail'
    (output / 'result.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    (output / 'result.json').chmod(0o600)
    print('PASS' if report['status'] == 'pass' else 'FAIL')
    print(f"checks={sum(item['pass'] for item in report['checks'])}/{len(report['checks'])} "
          'provider_calls=0 docker_calls=0 target_calls=0')
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
