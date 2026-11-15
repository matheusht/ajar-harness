#!/usr/bin/env python3
"""Failure-first checks for bounded, non-published AppArmor inventory readback."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'tools'), str(Path(__file__).resolve().parent)]

import check_codex_sandbox_policy_candidate as candidate  # noqa: E402

MAX_OUTPUT_BYTES = candidate.diagnostic.MAX_COMMAND_OUTPUT
INVENTORY_SENTINEL = 'SYNTHETIC_INVENTORY_MUST_NOT_BE_PUBLISHED'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = {'kind': 'codex-profile-inventory-readback-check-v1',
        'classification': 'offline_mocked_diagnostic_command', 'checks': [], 'failures': []}

    def check(name, passed, detail=None):
        row = {'name': name, 'passed': bool(passed)}
        if detail is not None:
            row['detail'] = detail
        result['checks'].append(row)
        if not passed:
            result['failures'].append(name)

    expected_path = '/sys/kernel/security/apparmor/profiles'
    check('profile inventory path is fixed',
        str(candidate.APPARMOR_PROFILE_PATH) == expected_path)

    sudo_path = '/usr/bin/sudo'
    sudo_available = True
    saved_command = candidate.diagnostic._command
    saved_which = candidate.shutil.which
    saved_read_text = Path.read_text
    calls = []
    responses = []

    def fake_command(docker, endpoint, *command_args, **kwargs):
        calls.append({'docker': docker, 'endpoint': endpoint,
                      'args': list(command_args), 'kwargs': kwargs})
        response = responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response

    def fake_which(name):
        return sudo_path if name == 'sudo' and sudo_available else None

    def block_direct_inventory_read(path, *positional, **kwargs):
        if path == candidate.APPARMOR_PROFILE_PATH:
            raise OSError('direct inventory read must not happen in the offline check')
        return saved_read_text(path, *positional, **kwargs)

    def invoke(response):
        if response is not None:
            responses.append(response)
        try:
            inventory = candidate._read_loaded_profiles()
        except candidate.CandidateFailure as error:
            return {'status': 'rejected', 'code': error.code}
        except Exception as error:
            return {'status': 'unexpected_error', 'error_type': type(error).__name__}
        return {'status': 'returned', 'enforcing': candidate._loaded_profile(
            inventory, candidate.APPARMOR_PROFILE)}

    try:
        candidate.diagnostic._command = fake_command
        candidate.shutil.which = fake_which
        Path.read_text = block_direct_inventory_read

        profile = (candidate.APPARMOR_PROFILE + ' (enforce)\n'
                   + INVENTORY_SENTINEL + ' (complain)\n')
        success = invoke(SimpleNamespace(returncode=0, stdout=profile.encode(), stderr=b''))
        check('successful sudo read returns the loaded-profile state',
              success == {'status': 'returned', 'enforcing': True},
              {'status': success.get('status'), 'enforcing': success.get('enforcing')})

        cases = [
            ('sudo noninteractive refusal is handled with a fixed error',
             SimpleNamespace(returncode=1, stdout=b'', stderr=b'sudo: a password is required')),
            ('other nonzero cat result is handled with a fixed error',
             SimpleNamespace(returncode=2, stdout=b'', stderr=b'private readback error')),
            ('oversized profile inventory is rejected',
             SimpleNamespace(returncode=0,
                stdout=b'x' * MAX_OUTPUT_BYTES, stderr=b'')),
            ('invalid UTF-8 inventory is rejected',
             SimpleNamespace(returncode=0, stdout=b'\xff', stderr=b'')),
            ('sudo command timeout is handled with a fixed error',
             candidate.diagnostic.DiagnosticFailure('docker_timeout')),
        ]
        for name, response in cases:
            before = len(calls)
            observed = invoke(response)
            passed = (observed.get('status') == 'rejected'
                      and observed.get('code') == 'apparmor_profile_readback_unavailable'
                      and len(calls) == before + 1)
            check(name, passed, {'status': observed.get('status'), 'code': observed.get('code'),
                                 'command_called': len(calls) == before + 1})
            if name.startswith('sudo noninteractive'):
                result['sudo_refusal_code'] = observed.get('code')

        expected_args = ['-n', '/usr/bin/cat', expected_path]
        call_checks = []
        for call in calls:
            options = call['kwargs']
            call_checks.append(call['docker'] == sudo_path and call['endpoint'] is None
                and call['args'] == expected_args and options.get('direct') is True
                and type(options.get('timeout')) in (int, float)
                and 0 < options['timeout'] <= candidate.TIMEOUT)
        check('each read uses fixed sudo cat argv and bounded diagnostic command',
              len(calls) == 6 and all(call_checks),
              {'calls': len(calls), 'all_match': bool(call_checks) and all(call_checks)})

        sudo_available = False
        before = len(calls)
        missing_sudo = invoke(None)
        check('missing sudo is handled without launching a command',
              missing_sudo == {'status': 'rejected', 'code': 'apparmor_profile_readback_unavailable'}
              and len(calls) == before,
              {'status': missing_sudo.get('status'), 'code': missing_sudo.get('code'),
               'command_called': len(calls) != before})

        check('check output does not retain synthetic inventory or stderr content',
              INVENTORY_SENTINEL not in json.dumps(result)
              and 'password is required' not in json.dumps(result)
              and 'private readback error' not in json.dumps(result))
    finally:
        candidate.diagnostic._command = saved_command
        candidate.shutil.which = saved_which
        Path.read_text = saved_read_text

    result['status'] = 'passed' if not result['failures'] else 'failed'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'checks': len(result['checks']),
                      'output': str(args.output)}))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
