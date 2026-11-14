#!/usr/bin/env python3
"""Failure-first real journal/inert-process diagnostic workflows; no Docker/native."""
import argparse
from datetime import timedelta
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

p = argparse.ArgumentParser()
p.add_argument('--source', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
sys.path.insert(0, str(a.source.resolve().parent))
spec = importlib.util.spec_from_file_location('linux_fixture', a.source)
m = importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
from check_engagement_evidence_e2e import Case
from engagement_contract import canonical, digest
from engagement_controller import Controller, instant

TAIL = ['/input/native-runtime/bin/codex', 'exec-server', '--listen', 'stdio',
        '--linux-sandbox-pid-namespace', 'isolate']
SECRETS = (b'fixture-provider-private-canary', b'fixture-bridge-private-canary')
result = {'classification': 'real_journal_with_simulated_observations_and_actual_inert_processes',
          'docker': 'not_run', 'native_execution': 'not_run', 'provider_calls': 0, 'checks': []}
def check(name, call):
    try:
        call()
        result['checks'].append({'name': name, 'passed': True})
    except Exception as error:
        result['checks'].append({'name': name, 'passed': False, 'error': type(error).__name__})

with tempfile.TemporaryDirectory(prefix='linux-diagnostic-check-') as directory:
    root = Path(directory).resolve()
    case = Case(root / 'journal')
    grant = case.grant(resources=['source-main'])
    identity = case.observe(grant, 'settled-operation', '1' * 32)
    start = case.c.clock()
    case.c.clock = lambda: start
    common = {'kind': 'environment-observation-v2', 'operation': 'execute',
              'operation_id': 'fixture-private-marker', 'identity': identity}
    case.c.record_environment_observation(grant, 'lab-main', dict(common, phase='intent',
        request_sha256=digest(b'inert request')), effect_id='read-source')
    case.c.clock = lambda: start + timedelta(seconds=5.2)
    case.c.record_environment_observation(grant, 'lab-main', dict(common, phase='result',
        status='unknown', returncode=-9, output_sha256=digest(b'')), effect_id='read-source')
    originals = {path: path.read_bytes() for path in (case.c.root / 'events').iterdir()}
    def journal_exact():
        observed = m.environment_diagnostics(Controller(case.c.root), ())
        expected = [json.loads(data) for path, data in sorted(originals.items())
                    if json.loads(data)['payload'].get('action') == 'environment_observation']
        assert observed['events'] == expected and not observed['truncated']
        for event in observed['events']:
            assert event['sha256'] == digest(canonical({k: v for k, v in event.items() if k != 'sha256'}))
        last = observed['events'][-2:]
        assert (instant(last[1]['at']) - instant(last[0]['at'])).total_seconds() == 5.2
        assert last[1]['payload']['data']['observation']['returncode'] == -9
        assert instant(last[1]['payload']['data']['grant']['lease_expires_at']) > instant(last[1]['at'])
        assert all(path.read_bytes() == data for path, data in originals.items())
    check('exact_journal_timestamps_and_outcomes', journal_exact)
    def journal_secret():
        try:m.environment_diagnostics(case.c, (b'fixture-private-marker',))
        except m.ContractError:return
        raise AssertionError('known secret admitted')
    check('known_secret_event_refused', journal_secret)
    def journal_corrupt():
        path = sorted(originals)[-1]
        changed = json.loads(originals[path]);changed['at'] = '2020-01-01T00:00:00+00:00'
        path.write_bytes(canonical(changed))
        try:
            try:m.environment_diagnostics(case.c, ())
            except Exception as error:
                assert getattr(error, 'code', '') == 'journal_corrupt'
                return
            raise AssertionError('corrupt journal admitted')
        finally:path.write_bytes(originals[path])
    check('corrupt_journal_refused', journal_corrupt)

    cases = [('safe', b'fixture exec startup rejected\n', True),
             ('sensitive', b'Authorization: Bearer fixture-private-canary\n', True),
             ('provider_secret', SECRETS[0], True), ('bridge_secret', SECRETS[1], True),
             ('large', b'x' * 70000, True), ('unselected', b'uncaptured error\n', False)]
    for name, stderr, selected in cases:
        def scenario(stderr=stderr, selected=selected, name=name):
            observer = m.ExecutorDiagnostics(subprocess)
            script = ('import sys,json\n'
                      'assert sys.stdin.buffer.readline()==b"private request marker\\n"\n'
                      'sys.stderr.buffer.write(' + repr(stderr) + ');sys.stderr.buffer.flush()\n'
                      'print(json.dumps(sys.argv[1:]),flush=True)\n'
                      'raise SystemExit(23)\n')
            tail = TAIL if selected else ['unrelated']
            command = [sys.executable, '-I', '-S', '-c', script, *tail]
            process = observer.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, env={}, start_new_session=True)
            process.stdin.write(b'private request marker\n');process.stdin.close()
            stdout = process.stdout.read();process.stdout.close();process.wait(timeout=5)
            assert process.args == command and process.returncode == 23
            assert json.loads(stdout) == tail
            observations = observer.finish(SECRETS)
            assert observer.DEVNULL == subprocess.DEVNULL
            if not selected:
                assert observations == []
                return
            assert len(observations) == 1 and observations[0]['returncode'] == 23
            row = observations[0]
            assert row['complete'] is True and row['bytes'] == len(stderr)
            assert len(row['stderr']) <= 2048
            text = json.dumps(observations)
            assert 'private-canary' not in text and 'private request marker' not in text
            if name == 'safe':assert row['stderr'] == stderr.decode()
            if name in ('sensitive', 'provider_secret', 'bridge_secret'):assert row['stderr'] == '[diagnostic redacted]'
            if name == 'large':assert row['stderr'] == '[oversized diagnostic withheld]' and row['truncated']
        check('stderr_' + name, scenario)
result['status'] = 'passed' if all(row['passed'] for row in result['checks']) else 'failed'
a.output.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result));raise SystemExit(result['status'] != 'passed')
