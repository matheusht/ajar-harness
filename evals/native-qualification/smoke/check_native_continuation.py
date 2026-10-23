#!/usr/bin/env python3
"""Offline continuation CLI smoke check; no provider, Docker, model or target."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
import native_research as runner

FAKE_RUNNER = r'''
import json
from pathlib import Path
import sys

argv = sys.argv[1:]
command = argv[0]
root = Path(argv[argv.index('--run-root') + 1])
runner = Path(__file__).resolve().parent
calls = runner / 'calls.jsonl'
with calls.open('a') as stream:
    stream.write(json.dumps({'command': command}) + '\n')

def write_next(value):
    (root / 'researcher/NEXT.json').write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')

def result(session, dispatch):
    print(json.dumps({'status': 'acknowledged', 'session_id': session,
                      'dispatch_id': dispatch,
                      'pool_before': {'used_tunnels': 0, 'charged_tunnel_bytes': 0,
                                      'active': True},
                      'pool_after': {'used_tunnels': 1, 'charged_tunnel_bytes': 10,
                                     'active': True}}))

if command == 'status':
    print(json.dumps({'status': 'active', 'allowance': {'active': True}}))
elif command == 'research':
    write_next({'kind': 'native-continuation-next-v1',
                'last_result': {'state': 'supported', 'rules_out': 'the first input',
                                'unresolved': 'the second condition'},
                'capabilities': [{'capability': 'observed effect',
                                  'enables': 'the second entry'}],
                'coverage': [{'surface': 'first entry', 'status': 'tested'}],
                'next': {'question': 'does the second entry accept the result?',
                         'test': 'run the second local check',
                         'prediction': 'the second entry accepts it',
                         'disconfirming': 'the second entry rejects it',
                         'authority': 'existing local scope'},
                'proposed_stop': False, 'strong_lead': True})
    result('ses_fake1', 'a' * 32)
elif command == 'resume':
    print(json.dumps({'status': 'rejected',
                      'code': 'resume_session_not_in_researcher_store'}))
    raise SystemExit(2)
elif command == 'reconstruct':
    write_next({'kind': 'native-continuation-next-v1',
                'last_result': {'state': 'blocked', 'rules_out': 'the second entry',
                                'unresolved': 'the remaining trust condition'},
                'capabilities': [{'capability': 'observed effect',
                                  'enables': 'the second entry'}],
                'coverage': [{'surface': 'second entry', 'status': 'blocked',
                              'limit': 'local fixture only'}],
                'next': None, 'proposed_stop': True, 'strong_lead': True})
    result('ses_fake2', 'c' * 32)
else:
    print(json.dumps({'status': 'rejected', 'code': 'unexpected_command'}))
'''


def run_controller(root: Path, fake: Path):
    command = [sys.executable, str(ROOT / 'tools/native_continuation.py'),
               '--run-root', str(root), '--runner', str(fake),
               '--max-invocations', '4', '--invocation-timeout', '60']
    completed = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, timeout=120)
    try:
        value = json.loads(completed.stdout)
    except ValueError:
        raise AssertionError('continuation output was not JSON')
    return completed.returncode, value


def main():
    with tempfile.TemporaryDirectory(prefix='continuation-smoke-') as temp:
        base = Path(temp).resolve()
        root = base / 'run'
        root.mkdir(mode=0o700)
        controls = root / 'controls'
        controls.mkdir(mode=0o700)
        (root / 'researcher').mkdir(mode=0o700)
        runner._write_json(root / 'plan.json', {'kind': 'continuation-smoke'}, once=True)
        fake = base / 'fake_runner.py'
        fake.write_text(FAKE_RUNNER)
        fake.chmod(0o700)

        first_code, first = run_controller(root, fake)
        checks = []
        def check(name, condition):
            checks.append({'name': name, 'pass': bool(condition)})
            if not condition:
                raise AssertionError(name)

        calls = [json.loads(line)['command'] for line in
                 (base / 'calls.jsonl').read_text().splitlines()]
        check('first run stopped for closure review',
              first_code == 2 and first.get('status') == 'closure_review_required')
        check('research, failed resume, reconstruction order',
              calls == ['status', 'research', 'resume', 'reconstruct'])
        check('checkpoint records the reconstruction session',
              json.loads((controls / 'continuation/state.json').read_text())['session_id'] == 'ses_fake2')
        events = [json.loads(line) for line in
                  (controls / 'continuation/events.jsonl').read_text().splitlines()]
        check('failed resume was not counted as a dispatch',
              any(row.get('event') == 'dispatch_not_sent' and row.get('code') ==
                  'resume_session_not_in_researcher_store' for row in events))
        check('closure request was produced',
              (controls / 'continuation/closure-request.json').is_file())

        request = controls / 'continuation/closure-request.json'
        review = controls / 'continuation/closure-review.json'
        runner._write_json(review, {
            'kind': 'native-continuation-closure-review-v1',
            'request_sha256': runner._sha(request),
            'decision': 'accept', 'reason': 'bounded local coverage accepted'})
        second_code, second = run_controller(root, fake)
        check('accepted closure returns without another invocation',
              second_code == 0 and second.get('status') == 'closed'
              and [json.loads(line)['command'] for line in
                   (base / 'calls.jsonl').read_text().splitlines()] == calls)
        print(json.dumps({'checks': checks, 'status': 'passed',
                          'limits': 'Synthetic subprocess only; no native model, provider, or target.'},
                         indent=2))
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
