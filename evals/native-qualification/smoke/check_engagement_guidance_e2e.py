#!/usr/bin/env python3
"""Freeze the method once, resume its exact bytes, and export for a native baseline.

Python 3 and ssh-keygen. Owned signed local fixtures; no model/provider/target.
Run --output FILE; all checks pass. No production repository guidance is mutated.
"""
import argparse
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'tools'), str(Path(__file__).parent)]
from check_engagement_evidence_e2e import Case, require, refused
from engagement_contract import digest
from engagement_controller import Controller
from engagement_runner import frozen_inputs, Runner, RunnerError
import engagement_controller


def guidance(path):
    files = {}
    for name in ('methodology.md', 'protocol.md'):
        file = path / name
        file.write_text('Frozen ' + name + '\n')
        files[name] = file
    return files


def freeze_resume(path):
    files = guidance(path)
    with patch.object(engagement_controller, 'BUNDLED_GUIDANCE', files, create=True):
        x = Case(path / 'case')
    expected = {name: file.read_bytes() for name, file in files.items()}
    for file in files.values():
        file.write_text('Changed repository guidance.\n')
    resumed = frozen_inputs(Controller(x.c.root))
    require(resumed.frozen_files == expected, 'resume did not use frozen guidance')
    x.c.export(path / 'export')
    result = json.loads((path / 'export/result.json').read_text())
    require(result['research_guidance'] == {name: digest(content) for name, content in expected.items()},
            'export missing method/protocol hashes')
    require(all((path / 'export/contract' / name).read_bytes() == content for name, content in expected.items()),
            'native baseline method bytes changed')


def tamper(path):
    files = guidance(path)
    with patch.object(engagement_controller, 'BUNDLED_GUIDANCE', files, create=True):
        x = Case(path / 'case')
    (x.c.root / 'contract/methodology.md').write_bytes(b'Changed frozen method\n')
    refused('contract_changed', lambda: frozen_inputs(Controller(x.c.root)))


def missing(path):
    files = guidance(path)
    files['protocol.md'].unlink()
    with patch.object(engagement_controller, 'BUNDLED_GUIDANCE', files, create=True):
        refused('research_guidance_unavailable', lambda: Case(path / 'case'))
    require(not (path / 'case/engagement').exists(), 'failed guidance left initialized root')


def portability(path):
    method = (ROOT / 'engine/native-engagement-method.md').read_text()
    require(not any(word in method for word in ('OSLit', 'engagement_submit', 'engagement_status', '/input', '/work')),
            'portable research method contains OSLit protocol')
    require('engagement_submit' in (ROOT / 'engine/native-engagement-protocol.md').read_text(),
            'native worker lacks concrete protocol')


def historical_stop(path):
    with patch.object(engagement_controller, 'BUNDLED_GUIDANCE', {}):
        x = Case(path / 'case')
    try:
        Runner(x.c)
    except RunnerError as error:
        require(error.code == 'research_guidance_unavailable', 'historical resume failed for wrong reason')
    else:
        raise AssertionError('historical active record resumed without frozen method')
    x.c.stop('operator_stop')
    require(Runner(x.c).contract.frozen_files == {}, 'historical stop recovery needs new methodology')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = {'classification': 'signed_local_workflow', 'provider_calls': 0, 'scenarios': []}
    for check in (freeze_resume, tamper, missing, portability, historical_stop):
        try:
            with tempfile.TemporaryDirectory(prefix='oslit-guidance-') as folder:
                check(Path(folder).resolve())
            report['scenarios'].append({'scenario': check.__name__, 'status': 'pass'})
        except Exception as error:
            report['scenarios'].append({'scenario': check.__name__, 'status': 'fail', 'error': str(error)})
    report['status'] = 'pass' if all(row['status'] == 'pass' for row in report['scenarios']) else 'fail'
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    return report['status'] != 'pass'


if __name__ == '__main__':
    raise SystemExit(main())
