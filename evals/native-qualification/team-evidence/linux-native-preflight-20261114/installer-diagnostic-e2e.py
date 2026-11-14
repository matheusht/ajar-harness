#!/usr/bin/env python3
"""Failure-first public installer-call checks; only owned inert CLI peers execute."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    source = args.source.resolve()
    sys.path.insert(0, str(source.parent))
    spec = importlib.util.spec_from_file_location('native_fixture_under_check', source)
    subject = importlib.util.module_from_spec(spec); spec.loader.exec_module(subject)
    report = {'classification': 'actual_owned_installer_cli_with_inert_fixture_outputs',
              'native_execution': False, 'docker_calls': 0, 'downloads': 0, 'provider_calls': 0,
              'source_sha256': 'sha256:' + hashlib.sha256(source.read_bytes()).hexdigest(), 'checks': []}
    cases = [('failed_plain', 17, b'{"status":"failed","error":"fixture_archive_digest_mismatch"}\n', b'fixture diagnostic\n'),
             ('failed_sensitive', 19, b'fixture safe stdout\n', b'Authorization: Bearer fixture-private-marker\n'),
             ('failed_oversized', 23, b'x' * 6000, b'y' * 6000),
             ('successful', 0, b'fixture installed\n', b'')]
    with tempfile.TemporaryDirectory(prefix='oslit-installer-diagnostics-') as temporary:
        for name, code, stdout, stderr in cases:
            root = Path(temporary) / name; (root / 'tools').mkdir(parents=True)
            assets = root / 'assets'; assets.mkdir()
            script = ('import json, pathlib, sys\n'
                      'receipt=pathlib.Path(sys.argv[sys.argv.index("--receipt")+1])\n'
                      'receipt.write_text(json.dumps({"profile_fields":{"tool_bundle":{"fixture":True}}}))\n'
                      'sys.stdout.buffer.write(bytes.fromhex(' + repr(stdout.hex()) + '))\n'
                      'sys.stderr.buffer.write(bytes.fromhex(' + repr(stderr.hex()) + '))\n'
                      'raise SystemExit(' + str(code) + ')\n')
            (root / 'tools/install_native_tools.py').write_text(script)
            subject.ROOT = root
            result = {'checks': []}
            failed = False
            try: subject.tool_bundle(SimpleNamespace(runtime='omp', platform='linux/amd64', directory=assets), result)
            except AssertionError: failed = True
            try:
                observed = result['tool_installer']
                assert failed == bool(code) and observed['returncode'] == code
                assert observed['stdout_truncated'] == (len(stdout) > 2048)
                assert observed['stderr_truncated'] == (len(stderr) > 2048)
                assert len(observed['stdout'].encode()) <= 2048 and len(observed['stderr'].encode()) <= 2048
                assert 'fixture-private-marker' not in json.dumps(observed)
                if name == 'failed_sensitive':assert observed['stderr'] == '[diagnostic redacted]'
                else:assert observed['stdout'] == stdout[:2048].decode() and observed['stderr'] == stderr[:2048].decode()
                report['checks'].append({'name': name, 'passed': True})
            except Exception as error:
                report['checks'].append({'name': name, 'passed': False, 'error': type(error).__name__})
    report['status'] = 'passed' if all(row['passed'] for row in report['checks']) else 'failed'
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'checks': report['checks']}))
    return report['status'] != 'passed'


if __name__ == '__main__':raise SystemExit(main())
