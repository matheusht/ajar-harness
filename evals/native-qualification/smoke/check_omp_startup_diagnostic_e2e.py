#!/usr/bin/env python3
"""Offline sidecar startup failures through the actual JSONL transport."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
from native_runtime_omp import ToolOwner
from native_runtime_transport import RuntimeError, Transport


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True, help='Absolute Bun or Node executable')
    args = parser.parse_args()
    runtime = args.runtime.resolve(strict=True)
    cases = []
    with tempfile.TemporaryDirectory(prefix='omp-startup-diagnostic-') as directory:
        sdk = Path(directory) / 'sdk'
        sdk.mkdir()
        for phase in ('paths', 'manifest', 'sdk_import'):
            if phase == 'sdk_import':
                (sdk / 'package.json').write_text(json.dumps({
                    'name': '@oh-my-pi/pi-coding-agent', 'version': '18.20.0'}))
            for delay in (0, .1):
                owner = ToolOwner.__new__(ToolOwner)
                owner.ready = False
                transport = Transport([str(runtime), str(ROOT / 'tools/native_runtime_omp_tools.mjs'),
                    str(Path(directory) / 'missing' if phase == 'paths' else sdk), directory],
                    {}, directory, owner._event, omp=True)
                try:
                    time.sleep(delay)
                    transport.request('catalog', timeout=3)
                except RuntimeError as error:
                    assert str(error) == 'native_tool_startup_' + phase, str(error)
                else:
                    raise AssertionError('Expected failed startup')
                finally:
                    transport.close()
                assert transport.process.poll() is not None
                cases.append({'phase': phase, 'delay': delay, 'cleanup': 'reaped'})
    owner = ToolOwner.__new__(ToolOwner)
    owner.ready = False
    for phase in ('paths', 'manifest', 'sdk_import', 'schema_import', 'validation_import',
                  'settings', 'tools', 'catalog'):
        try:
            owner._event({'type': 'startup_failed', 'phase': phase})
        except RuntimeError as error:
            assert str(error) == 'native_tool_startup_' + phase
        else:
            raise AssertionError('Expected phase failure')
    for ready, phase in ((False, 'untrusted-value'), (False, None), (False, []), (True, 'paths')):
        owner.ready = ready
        try:
            owner._event({'type': 'startup_failed', 'phase': phase})
        except RuntimeError as error:
            assert str(error) == 'native_tool_startup_diagnostic_invalid'
        else:
            raise AssertionError('Expected invalid diagnostic rejection')
    print(json.dumps({'status': 'passed', 'classification': 'offline_sidecar_transport',
                      'subprocess_cases': cases, 'frame_cases': 12, 'provider_calls': 0}))


if __name__ == '__main__':
    main()
