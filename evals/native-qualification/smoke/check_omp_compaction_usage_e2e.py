#!/usr/bin/env python3
"""Replay pinned OMP active-window statistics through invocation completion.

Define failures before changing the adapter: normal monotonic totals stay exact;
committed native compaction makes the affected delta unavailable even when its
final counters grew; repeated/manual compactions and the next invocation retain
completion. Missing, skipped or aborted compaction evidence cannot excuse a
counter reset. Malformed counters/cost remain refused in either path.
"""
import argparse
from collections import deque
from contextlib import nullcontext
import copy
import hashlib
import json
import math
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
from native_runtime_omp import Runtime


def run(snapshots):
    checks = []
    class Transport:
        io_lock = threading.RLock()
        sequence = 0
        stats = None
        def next_id(self):
            self.sequence += 1
            return 'request-' + str(self.sequence)
        def request(self, method, *args, **kwargs):
            if method == 'get_state':
                return {'model': {'id': 'owned-model', 'provider': 'owned-provider'},
                        'dumpTools': [], 'sessionId': 'owned-session'}
            if method == 'get_session_stats':
                return copy.deepcopy(self.stats)
            if method == 'prompt':
                return {'agentInvoked': True}
            raise AssertionError('unexpected transport request')
    def runtime():
        peer = Runtime.__new__(Runtime)
        peer.transport = Transport()
        peer.profile = {'model': 'owned-model', 'provider': 'owned-provider'}
        peer.session_id = 'owned-session'
        peer.active = False
        peer.calls, peer.tool_replies, peer.invocations = {}, [], set()
        peer.host_tools, peer.events, peer.usage = {}, deque(), None
        peer._admission = nullcontext
        return peer
    committed = {'type': 'auto_compaction_end', 'result': {'summary': 'Owned compacted context.'},
                 'aborted': False, 'willRetry': False, 'action': 'compact'}
    def complete(peer, after, events=(), invocation='owned-turn'):
        peer.transport.stats = snapshots['before']
        peer.invoke('Owned harmless accounting fixture.', invocation)
        for event in events:
            peer._event(copy.deepcopy(event))
        peer.transport.stats = after
        peer._event({'type': 'prompt_result', 'id': peer.native_turn,
                     'status': 'completed', 'sessionSettled': True})
        completed = [event for event in peer.events if event['event'] == 'completed'][-1]
        assert completed['status'] == 'completed' and not peer.active
        return completed
    def unavailable(after, events):
        peer = runtime()
        completed = complete(peer, after, events)
        dimensions = ('input_tokens', 'output_tokens', 'cached_input_tokens',
                      'cache_write_input_tokens', 'reasoning_output_tokens', 'total_tokens')
        assert all(peer.usage[key] is None for key in dimensions)
        assert peer.usage['estimated_cost'] is None
        assert set(dimensions) <= set(peer.usage['missing_dimensions'])
        assert completed['usage_available'] is False
        return peer
    def exact(peer):
        assert peer.usage['input_tokens'] == 20 and peer.usage['total_tokens'] == 30
        assert math.isclose(peer.usage['estimated_cost'], .1)
    def normal():
        peer = runtime()
        assert complete(peer, snapshots['normal'])['usage_available'] is True
        exact(peer)
    def repeat():
        peer = unavailable(snapshots['compacted'], [committed, committed])
        complete(peer, snapshots['normal'], invocation='next-turn')
        exact(peer)
    def refused(after, events=()):
        try:
            complete(runtime(), after, events)
        except Exception as error:
            assert getattr(error, 'code', None) == 'native_usage_invalid'
            return
        raise AssertionError('invalid accounting accepted')
    def unsupported_events():
        for event in ({**committed, 'aborted': True}, {**committed, 'skipped': True},
                      {**committed, 'result': None}, {'type': 'other', 'result': {}},
                      {**committed, 'result': 'not-a-result'}):
            refused(snapshots['compacted'], [event])
    def malformed():
        for events in ([], [committed]):
            for value in (-1, 1.5, True, '3', float('nan'), float('inf')):
                for side in ('after', 'before'):
                    bad = copy.deepcopy(snapshots['normal'])
                    before = copy.deepcopy(snapshots['before'])
                    (bad if side == 'after' else before)['tokens']['total'] = value
                    original = snapshots['before']
                    snapshots['before'] = before
                    try:
                        refused(bad, events)
                    finally:
                        snapshots['before'] = original
    def malformed_cost():
        for events in ([], [committed]):
            for value in (-1, True, '3', float('nan'), float('inf')):
                bad = copy.deepcopy(snapshots['normal'])
                bad['cost'] = value
                refused(bad, events)
    cases = [
        ('normal invocation retains exact delta', normal),
        ('committed compaction with falling totals completes with unavailable usage',
         lambda: unavailable(snapshots['compacted'], [committed])),
        ('committed compaction with growing totals does not fabricate a delta',
         lambda: unavailable(snapshots['compactedPositive'], [committed])),
        ('repeated compactions stay unavailable and next invocation resets accounting', repeat),
        ('committed manual compaction uses the same accounting boundary',
         lambda: unavailable(snapshots['compacted'], [{**committed, 'type': 'manual_compaction_end'}])),
        ('counter reset without native compaction evidence remains refused',
         lambda: refused(snapshots['compacted'])),
        ('skipped aborted malformed and unrelated events do not excuse reset', unsupported_events),
        ('malformed counters remain refused before and after compaction', malformed),
        ('malformed cost remains refused before and after compaction', malformed_cost),
    ]
    for name, action in cases:
        try:
            action()
            checks.append({'name': name, 'passed': True})
        except Exception as error:
            checks.append({'name': name, 'passed': False,
                           'error': getattr(error, 'code', type(error).__name__)})
    return checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stats', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    stats = json.loads(args.stats.read_bytes())
    checks = run(stats)
    result = {'kind': 'omp-compaction-usage-e2e-v1',
              'classification': 'actual_adapter_with_pinned_stats_and_simulated_native_events',
              'status': 'passed' if all(row['passed'] for row in checks) else 'failed',
              'checks': checks, 'stats_sha256': hashlib.sha256(args.stats.read_bytes()).hexdigest(),
              'source_sha256': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in (Path(__file__), ROOT / 'tools/native_runtime_omp.py', ROOT / 'tools/native_runtime_transport.py')}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
