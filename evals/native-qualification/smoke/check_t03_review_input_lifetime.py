#!/usr/bin/env python3
"""Owned packet-to-current-input challenge; no Docker, application or model."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[3]
RUNNER = ROOT / 'evals/native-qualification/smoke/opencode_v2_managed_owned.py'
NAMES = ('index.php', 'message.php', 'check.php')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    spec = importlib.util.spec_from_file_location('t03_managed_runner', RUNNER)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    result = {'classification': 'owned synthetic review-input lifetime; no native review',
              'runner_sha256': sha(RUNNER), 'provider_calls': 0, 'target_calls': 0,
              'checks': []}

    def check(name, condition):
        result['checks'].append({'name': name, 'pass': bool(condition)})
        if not condition:
            raise AssertionError(name)

    try:
        with tempfile.TemporaryDirectory(prefix='t03-review-input-') as temporary:
            root = Path(temporary)
            originals, candidate, packet = (root / name for name in ('originals', 'candidate', 'packet'))
            for directory in (originals, candidate, packet):
                directory.mkdir(mode=0o700)
            for name in NAMES:
                data = (ROOT / 'evals/native-qualification/smoke' / name).read_bytes()
                (originals / name).write_bytes(data)
                (candidate / name).write_bytes(data.replace(b"return 'before';", b"return 'after';")
                                                  if name == 'message.php' else data)
            note = candidate / 'research-note.md'
            note.write_text('Provisional local claim from an ordinary file change.\n')
            note_bytes = note.read_bytes()
            source_bytes = (candidate / 'message.php').read_bytes()
            stream = json.dumps({'type': 'tool_use', 'sessionID': 'ses_Synthetic1',
                'part': {'type': 'tool', 'tool': 'read', 'state': {'status': 'completed',
                    'input': {'filePath': '/workspace/project/message.php'},
                    'output': 'local file read', 'error': None}}}) + '\n'
            sources = {}
            for phase, folder in (('baseline', originals), ('candidate', candidate)):
                rows = []
                for name in ('index.php', 'check.php'):
                    run = subprocess.run(['php', str(folder / name)], capture_output=True,
                                         text=True, timeout=10)
                    rows.append({'command': 'php ' + name, 'exit': run.returncode,
                                 'stdout': run.stdout, 'stderr': run.stderr})
                sources[phase] = {'source_sha256': {name: sha(folder / name) for name in NAMES},
                                  'results': rows}
            pin = runner.publish_review_packet(packet, originals, candidate, note, stream,
                                               sources, 'owned-capability')
            try:
                check('unchanged actual claim and source match frozen packet',
                      runner.review_inputs_current(packet, pin, originals, candidate, note))
                raw = json.loads((packet / 'RAW-APP-CHECKS.json').read_text())['checks']
                check('frozen packet retains contrary baseline and candidate effect',
                      raw['baseline']['results'][1]['exit'] == 1
                      and raw['baseline']['results'][1]['stderr'] ==
                          'message() must return after\n'
                      and raw['candidate']['results'][1]['exit'] == 0
                      and raw['candidate']['results'][1]['stdout'] == 'check passed\n')
                observed = subprocess.run(['php', str(packet / 'index.php')], capture_output=True,
                                          text=True, timeout=10)
                check('offline PHP execution observes frozen candidate result',
                      observed.returncode == 0 and observed.stdout == 'after\n'
                      and observed.stderr == '')

                def reviewer_tool(session, command, output, status='completed', error=None):
                    event = {'type': 'tool_use', 'sessionID': session, 'part': {'type': 'tool',
                        'tool': 'shell', 'state': {'status': status,
                            'input': {'command': command}, 'output': output, 'error': error}}}
                    return runner.native_tool_material(json.dumps(event) + '\n')['records']

                session = 'ses_Reviewer1'
                direct = reviewer_tool(session, 'php /handoff/index.php', observed.stdout)
                check('material signal requires reviewer execution and observed result',
                      runner.reviewer_material_php_check(direct, session))
                check('quoted PHP is not execution',
                      not runner.reviewer_material_php_check(
                          reviewer_tool(session, "echo 'php /handoff/index.php'", observed.stdout), session))
                check('other session cannot provide reviewer material check',
                      not runner.reviewer_material_php_check(direct, 'ses_Other1'))
                check('failed or result-free tool is not a material check',
                      not runner.reviewer_material_php_check(
                          reviewer_tool(session, 'php /handoff/index.php', observed.stdout,
                                        status='failed', error='failed'), session)
                      and not runner.reviewer_material_php_check(
                          reviewer_tool(session, 'php /handoff/index.php', ''), session))
                check('unbound PHP path is not the frozen candidate',
                      not runner.reviewer_material_php_check(
                          reviewer_tool(session, 'php /tmp/index.php', observed.stdout), session))
                note.write_text('Changed claim after review.\n')
                check('changed claim is stale despite intact packet',
                      runner.verify_review_packet(packet, pin)
                      and not runner.review_inputs_current(packet, pin, originals, candidate, note))
                note.write_bytes(note_bytes)
                (candidate / 'message.php').write_text("<?php return 'later';\n")
                check('changed current source is stale despite intact packet',
                      runner.verify_review_packet(packet, pin)
                      and not runner.review_inputs_current(packet, pin, originals, candidate, note))
                (candidate / 'message.php').write_bytes(source_bytes)
                extra = candidate / 'extra.php'
                extra.write_text("<?php return 'later';\n")
                check('new current source file is stale despite intact packet',
                      runner.verify_review_packet(packet, pin)
                      and not runner.review_inputs_current(packet, pin, originals, candidate, note))
                extra.unlink()
                check('stop before packet/review cannot become current',
                      not runner.review_inputs_current(root / 'absent-packet', None,
                                                       originals, candidate, note))
                request = packet / 'REQUEST.json'
                request.chmod(0o600)
                request.write_bytes(request.read_bytes() + b' ')
                check('post-freeze packet change is stale',
                      not runner.review_inputs_current(packet, pin, originals, candidate, note))
            finally:
                packet.chmod(0o700)
                for item in packet.iterdir():
                    item.chmod(0o600)
            result['status'] = 'pass'
    except Exception as error:
        result['status'] = 'fail'
        result['error_type'] = type(error).__name__
        raise
    finally:
        (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print('PASS: frozen review inputs reject changed claim, source, packet and absent review')


if __name__ == '__main__':
    main()
