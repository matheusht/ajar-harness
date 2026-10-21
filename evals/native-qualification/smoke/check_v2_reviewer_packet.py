#!/usr/bin/env python3
"""Owned synthetic packet, read-only mount and drift E2E; no model or provider."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[3]
RUNNER = ROOT / 'evals/native-qualification/smoke/opencode_v2_managed_owned.py'
FIXTURE = ROOT / 'evals/native-qualification/smoke'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--image', required=True, help='locally available image with sh')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    spec = importlib.util.spec_from_file_location('t02_review_packet', RUNNER)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    receipt = {'classification': 'owned synthetic packet and Docker mount E2E; no native model, provider or target',
               'source_sha256': sha(RUNNER), 'checks': []}

    def check(name, passed):
        receipt['checks'].append({'name': name, 'pass': bool(passed)})
        if not passed:
            raise AssertionError(name)

    try:
        with tempfile.TemporaryDirectory(prefix='t02-review-packet-') as temporary:
            work = Path(temporary)
            originals, candidate, packet = work / 'originals', work / 'candidate', work / 'packet'
            originals.mkdir()
            candidate.mkdir()
            packet.mkdir(mode=0o700)
            for name in ('index.php', 'message.php', 'check.php'):
                data = (FIXTURE / name).read_bytes()
                (originals / name).write_bytes(data)
                (candidate / name).write_bytes(data)
            source = (candidate / 'message.php').read_text()
            (candidate / 'message.php').write_text(source.replace("return 'before';", "return 'after';"))
            note = candidate / 'research-note.md'
            note.write_text('Harmless local change: message() returns after; php check.php passed.\n')
            stream = json.dumps({'type': 'tool_use', 'part': {'type': 'tool', 'tool': 'shell',
                'state': {'status': 'completed', 'input': {'command': 'php check.php'},
                          'output': 'check passed\n'}}}) + '\n'
            baseline = [runner.summarize_php(('php', 'index.php'), 0, 'before\n', ''),
                        runner.summarize_php(('php', 'check.php'), 1, '', 'message() must return after\n')]
            after = [runner.summarize_php(('php', 'index.php'), 0, 'after\n', ''),
                     runner.summarize_php(('php', 'check.php'), 0, 'check passed\n', '')]
            app_checks = {
                'baseline': {'source_sha256': {name: sha(originals / name) for name in runner.PACKET_SOURCE_NAMES},
                             'network': 'none', 'image_id': 'synthetic fixture', 'results': baseline},
                'candidate': {'source_sha256': {name: sha(candidate / name) for name in runner.PACKET_SOURCE_NAMES},
                              'network': 'none', 'image_id': 'synthetic fixture', 'results': after}}
            pin = runner.publish_review_packet(packet, originals, candidate, note, stream,
                                               app_checks,
                                               'local_' + 'a' * 32, forbidden_paths=(str(work),))
            check('packet fixed inventory and hashes', runner.verify_review_packet(packet, pin))
            request = json.loads((packet / 'REQUEST.json').read_text())
            check('original and candidate mapped separately',
                  request['files']['ORIGINAL-message.php'] == sha(originals / 'message.php')
                  and request['files']['message.php'] == sha(candidate / 'message.php')
                  and request['files']['ORIGINAL-message.php'] != request['files']['message.php'])
            check('protected original observation unavailable',
                  request['original_observation']['status'] == 'unavailable')
            image = subprocess.run(['docker', 'image', 'inspect', args.image, '--format', '{{.Id}}'],
                                   capture_output=True, text=True, timeout=20)
            check('local test image present', image.returncode == 0 and image.stdout.strip().startswith('sha256:'))
            receipt['test_image_id'] = image.stdout.strip()
            mounted = subprocess.run(['docker', 'run', '--rm', '--network', 'none', '--read-only',
                '--user', f'{os.getuid()}:{os.getgid()}',
                '--mount', f'type=bind,src={packet},dst=/handoff,readonly',
                '--entrypoint', 'sh', args.image, '-c',
                'test -r /handoff/REQUEST.json && test -r /handoff/ORIGINAL-message.php && '
                'test -r /handoff/message.php && ! touch /handoff/denied'],
                capture_output=True, text=True, timeout=30)
            check('reviewer sees packet but cannot write mount', mounted.returncode == 0)
            changed = packet / 'message.php'
            original_packet_bytes = changed.read_bytes()
            changed.chmod(0o600)
            changed.write_bytes(original_packet_bytes + b' ')
            check('post-freeze byte drift rejected', not runner.verify_review_packet(packet, pin))
            changed.write_bytes(original_packet_bytes)
            changed.chmod(0o444)
            check('restored bytes match independent pin', runner.verify_review_packet(packet, pin))
            packet.rename(work / 'old-packet-root')
            packet.mkdir(mode=0o555)
            check('replaced bind root rejected', not runner.verify_review_packet(packet, pin))
            other = work / 'other'
            other.mkdir()
            bad_stream = stream.replace('check passed', 'local_' + 'a' * 32)
            try:
                runner.publish_review_packet(other, originals, candidate, note, bad_stream,
                                             app_checks,
                                             'local_' + 'a' * 32, forbidden_paths=(str(work),))
            except RuntimeError:
                rejected = not list(other.iterdir())
            else:
                rejected = False
            check('capability in raw tool evidence refused before publication', rejected)
            receipt['packet_files'] = sorted(request['files'])
            receipt['packet_request_sha256'] = pin['files']['REQUEST.json']
            receipt['status'] = 'pass'
    except Exception as error:
        receipt['status'] = 'fail'
        receipt['error_type'] = type(error).__name__
        raise
    finally:
        (output / 'result.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('PASS: owned synthetic reviewer packet, Docker read-only mount and drift rejection')


if __name__ == '__main__':
    main()
