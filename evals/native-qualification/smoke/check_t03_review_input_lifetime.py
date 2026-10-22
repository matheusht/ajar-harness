#!/usr/bin/env python3
"""Owned packet-to-current-input challenge; no Docker, application or model."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
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
                (originals / name).write_text("<?php return 'before';\n")
                (candidate / name).write_text("<?php return 'after';\n" if name == 'message.php'
                                              else "<?php return 'before';\n")
            note = candidate / 'research-note.md'
            note.write_text('Provisional local claim from an ordinary file change.\n')
            note_bytes = note.read_bytes()
            source_bytes = (candidate / 'message.php').read_bytes()
            stream = json.dumps({'type': 'tool_use', 'sessionID': 'ses_Synthetic1',
                'part': {'type': 'tool', 'tool': 'read', 'state': {'status': 'completed',
                    'input': {'filePath': '/workspace/project/message.php'},
                    'output': 'local file read', 'error': None}}}) + '\n'
            sources = {phase: {'source_sha256': {name: sha(folder / name) for name in NAMES},
                               'results': []}
                       for phase, folder in (('baseline', originals), ('candidate', candidate))}
            pin = runner.publish_review_packet(packet, originals, candidate, note, stream,
                                               sources, 'owned-capability')
            try:
                check('unchanged actual claim and source match frozen packet',
                      runner.review_inputs_current(packet, pin, originals, candidate, note))
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
