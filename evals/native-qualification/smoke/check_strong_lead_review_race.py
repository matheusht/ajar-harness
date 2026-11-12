#!/usr/bin/env python3
"""Contained checked-setup disposition readback race; no Docker or provider."""
import argparse
import contextlib
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
import native_continuation as continuation
import native_research as runner
import check_agent_closeout as fixture


def main() -> int:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='strong-lead-review-race-') as temporary:
        root = fixture.setup(Path(temporary).resolve(), outcome='bounded_negative')
        state = continuation._state(root)
        assert state['last_strong_lead'] is True
        review = state['review_action']
        assert review['phase'] == 'captured'
        checkpoint = json.loads((root / 'controls/continuation/reviews' /
                                 review['review_id'] / 'observer/UNFINISHED.json').read_text())[
                                     'checkpoint']
        assert checkpoint['strong_lead'] is False
        runner._write_json(root / 'researcher/NEXT.json', checkpoint)
        assert continuation._next_hash(root) == review['next_sha256']
        receipt_path = root / 'controls/review-reviewer-1.json'
        original_read = continuation._read_private
        original_review = continuation._agent_review

        def checked_plan(path):
            value = original_read(path)
            return {**value, 'checked_setup': {'kind': 'synthetic'}} if path == root / 'plan.json' else value

        def review_then_change(*review_args):
            response = original_review(*review_args)
            assert response['status'] == 'captured'
            receipt = runner._read_json(receipt_path)
            receipt['same_original_allowance'] = False
            runner._write_json(receipt_path, receipt)
            return response

        def no_turn(*_args):
            raise AssertionError('model turn dispatched after review evidence changed')

        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(continuation, '_read_private', side_effect=checked_plan))
            stack.enter_context(patch.object(continuation, '_agent_review',
                                             side_effect=review_then_change))
            stack.enter_context(patch.object(runner, '_verified_plan',
                                             side_effect=lambda path, **kw: runner._read_json(
                                                 path / 'plan.json')))
            first = continuation.continue_run(root, max_invocations=2, invoke=no_turn,
                status_fn=lambda _: {'status': 'active', 'allowance': {'active': True}})
            second = continuation.continue_run(root, max_invocations=2, invoke=no_turn,
                status_fn=lambda _: {'status': 'active', 'allowance': {'active': True}})
        state = continuation._state(root)
        assert first['status'] == second['status'] == 'review_incomplete'
        assert first['review_action']['reason'] == 'source_review_cached_evidence_changed'
        assert state['invocations'] == 1 and state['review_action']['phase'] == 'incomplete'
        assert state['last_strong_lead'] is True and state['dismissed_strong_lead'] is False
        assert not (root / 'controls/closeout/request.json').exists()
        events = [json.loads(line)['event'] for line in
                  (root / 'controls/continuation/events.jsonl').read_text().splitlines()]
        assert events.count('source_review_cached_evidence_changed') == 1
        missing = fixture.setup(Path(temporary).resolve() / 'missing',
                                outcome='bounded_negative', lead_disposition=False)
        missing_state = continuation._state(missing)
        missing_id = missing_state['review_action']['review_id']
        missing_checkpoint = json.loads((missing / 'controls/continuation/reviews' /
            missing_id / 'observer/UNFINISHED.json').read_text())['checkpoint']
        runner._write_json(missing / 'researcher/NEXT.json', missing_checkpoint)
        missing_turns = []

        def missing_turn(*_args):
            missing_turns.append('resume')
            runner._write_json(missing / 'researcher/NEXT.json', {
                **missing_checkpoint, 'host_action': None,
                'next': {'question': 'What remains?', 'test': 'one local check',
                         'prediction': 'control holds', 'disconfirming': 'control fails',
                         'authority': 'same approval'}})
            return 0, {'status': 'acknowledged', 'session_id': 'ses_fixture',
                       'dispatch_id': 'a' * 32,
                       'pool_after': {'active': True, 'used_tunnels': 1,
                                      'charged_tunnel_bytes': 1}}

        def missing_checked_plan(path):
            value = original_read(path)
            return {**value, 'checked_setup': {'kind': 'synthetic'}} if path == missing / 'plan.json' else value

        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(continuation, '_read_private',
                                             side_effect=missing_checked_plan))
            stack.enter_context(patch.object(runner, '_verified_plan',
                                             side_effect=lambda path, **kw: runner._read_json(
                                                 path / 'plan.json')))
            missing_result = continuation.continue_run(missing, max_invocations=2,
                invoke=missing_turn,
                status_fn=lambda _: {'status': 'active', 'allowance': {'active': True}})
        assert missing_result['status'] == 'closure_review_required'
        assert missing_turns == ['resume']
        assert continuation._state(missing)['review_action']['phase'] == 'captured'
        assert runner._read_json(missing / 'controls/continuation/closure-request.json')[
            'reason'] == 'strong_lead_abandoned'
        result = {'kind': 'native-strong-lead-review-race-synthetic-e2e-v1',
                  'status': 'passed', 'first_status': first['status'],
                  'retry_status': second['status'], 'invocations': state['invocations'],
                  'valid_missing_disposition_status': missing_result['status'],
                  'valid_missing_disposition_turns': len(missing_turns),
                  'review_phase': state['review_action']['phase'],
                  'review_projection_sha256': review['projection_sha256'],
                  'changed_receipt_sha256': runner._sha(receipt_path),
                  'events': events, 'scenario_sha256': runner._sha(Path(__file__)),
                  'environment': {'platform': platform.system().lower(),
                                  'python': platform.python_version()},
                  'provider_calls': 0, 'target_service_calls': 0,
                  'limits': 'Synthetic cached review and in-memory checked-setup marker; '
                            'no Docker, provider, target, or real owner teardown.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'result': str(args.output)}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
