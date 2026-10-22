#!/usr/bin/env python3
"""Synthetic public-status checks; no Docker, native runtime, provider, or target."""
import argparse
from contextlib import ExitStack
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
CLI = ROOT / 'tools/native_research.py'
CODES = ('operator_stop', 'monotonic_timeout', 'owner_close', 'connect_exited',
         'startup_failure', 'owner_lost', 'stop_owner_lost', 'provider_authority_ended',
         'child_exited_without_stop', 'child_exited_before_prepare')
SENTINEL = 'private-sentinel-value-not-for-output'


def write(path, value):
    path.write_bytes(value if isinstance(value, bytes) else json.dumps(value).encode())
    path.chmod(0o600)


def snapshot(root):
    result = {}
    for path in sorted(root.rglob('*')):
        item = path.lstat()
        kind = stat.S_IFMT(item.st_mode)
        content = path.read_bytes() if stat.S_ISREG(item.st_mode) else (
            os.readlink(path) if stat.S_ISLNK(item.st_mode) else None)
        result[str(path.relative_to(root))] = (kind, item.st_mode, item.st_mtime_ns, content)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    checks = []

    def check(name, passed):
        checks.append({'name': name, 'passed': bool(passed)})
        assert passed, name

    with TemporaryDirectory(prefix='native-stop-reason-') as temp:
        root = Path(temp).resolve() / 'run'
        controls = root / 'controls'
        state = controls / 'native-state'
        state.mkdir(mode=0o700, parents=True)
        root.chmod(0o700)
        controls.chmod(0o700)
        plan = {'kind': 'native-research-plan-v1', 'model': 'synthetic',
                'limits': {'duration_seconds': 30, 'max_connections': 1, 'max_bytes': 1024}}
        write(root / 'plan.json', plan)
        marker = state / 'STOP_REQUEST'

        def status(expected, name, terminal='prepared'):
            before = snapshot(root)
            call = subprocess.run([sys.executable, '-B', str(CLI), 'status', '--run-root', str(root)],
                                  capture_output=True, text=True, timeout=10)
            check(name + ': CLI succeeds', call.returncode == 0)
            value = json.loads(call.stdout)
            check(name + ': stop reason', 'stop_reason' in value and value['stop_reason'] == expected)
            check(name + ': status unchanged', value['status'] == terminal)
            check(name + ': inspection is read-only', snapshot(root) == before)
            check(name + ': no private reason output', SENTINEL not in call.stdout + call.stderr)
            return value

        status(None, 'missing request')
        for reason in CODES:
            write(marker, {'reason': reason, 'monotonic': 1.25})
            status(reason, reason)
        write(marker, {'reason': 'operator_stop', 'monotonic': 1.25})
        write(state / 'STOPPING', {'reason': 'monotonic_timeout', 'monotonic': 2})
        write(controls / 'final.json', {'status': 'stopped_complete', 'stop_reason': 'owner_lost'})
        status('operator_stop', 'first trigger wins', 'stopped_complete')
        write(controls / 'final.json', {'status': 'stopped_complete'})
        status('operator_stop', 'old final receipt', 'stopped_complete')
        marker.unlink()
        status(None, 'terminal receipt does not invent reason', 'stopped_complete')
        (controls / 'final.json').unlink()

        invalid = [b'{', b'[]', b'{"reason":"operator_stop","reason":"owner_close","monotonic":1}',
                   {'reason': 'operator_stop'}, {'reason': 'operator_stop', 'monotonic': 1, 'extra': True},
                   {'reason': 'operator_stop', 'monotonic': True},
                   {'reason': 'operator_stop', 'monotonic': -1},
                   {'reason': 'operator_stop', 'monotonic': float('nan')},
                   {'reason': 'operator_stop', 'monotonic': float('inf')},
                   {'reason': 'operator_stop', 'monotonic': 10 ** 1000},
                   {'reason': 'operator_stop', 'monotonic': '1'},
                   {'reason': 1, 'monotonic': 1}, {'reason': '', 'monotonic': 1},
                   {'reason': 'x' * 129, 'monotonic': 1},
                   b'{"reason":"operator_stop","monotonic":1}' + b' ' * 32768]
        for number, value in enumerate(invalid):
            write(marker, value)
            status('stop_reason_unavailable', f'invalid request {number}')
        write(marker, {'reason': SENTINEL, 'monotonic': 1})
        status('stop_reason_unrecognized', 'custom reason is not echoed')
        marker.chmod(0o644)
        status('stop_reason_unavailable', 'nonprivate request')
        marker.unlink()
        marker.symlink_to(state / 'missing')
        status('stop_reason_unavailable', 'dangling symlink')
        marker.unlink()
        marker.symlink_to(state / 'STOPPING')
        status('stop_reason_unavailable', 'symlink request')
        marker.unlink()
        marker.mkdir()
        status('stop_reason_unavailable', 'directory request')
        marker.rmdir()
        os.mkfifo(marker, 0o600)
        status('stop_reason_unavailable', 'FIFO request')
        marker.unlink()

        spec = importlib.util.spec_from_file_location('stop_reason_runner', CLI)
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        write(controls / 'activation.json', {'kind': 'synthetic-activation'})
        before = snapshot(root)
        with patch.object(runner, 'allowance_snapshot', return_value={'active': True}):
            active = runner.status(root)
        check('active without request stays active and reasonless',
              active['status'] == 'active' and active.get('stop_reason') is None)
        check('active status is read-only', snapshot(root) == before)
        (controls / 'activation.json').unlink()
        write(marker, {'reason': 'operator_stop', 'monotonic': 1})
        first = marker.read_bytes()
        runtime_calls = []

        def forbidden(*_args, **_kwargs):
            runtime_calls.append(True)
            raise AssertionError('runtime boundary called')

        class NoSocket:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def bind(self, *_): pass
            def getsockname(self): return ('127.0.0.1', 1)

        with ExitStack() as stack:
            for name in ('_docker', '_native_exec', '_activate_controls'):
                stack.enter_context(patch.object(runner, name, side_effect=forbidden))
            for name, value in (('_verified_plan', dict(plan, image_id='fixture',
                                                        target_image_id='fixture', platform='fixture')),
                                ('_approval', None), ('_image', None),
                                ('_capture_stop', {'status': 'not_configured'}),
                                ('_cleanup_resources', {'status': 'complete'}),
                                ('_capture_cleanup', {'status': 'not_configured'})):
                stack.enter_context(patch.object(runner, name, return_value=value))
            stack.enter_context(patch.object(runner.socket, 'socket', return_value=NoSocket()))
            stack.enter_context(patch.object(runner, '_preseal',
                                            side_effect=runner.NativeResearchError('synthetic_start_failure')))
            try:
                runner._start_owned(root, root / 'approval.json')
            except runner.NativeResearchError as error:
                check('startup failure preserved', str(error) == 'synthetic_start_failure')
            else:
                raise AssertionError('synthetic startup failure disappeared')
            final = json.loads((controls / 'final.json').read_bytes())
            check('final receipt reason', final.get('stop_reason') == 'operator_stop')
            check('reason does not upgrade startup failure', final['status'] == 'start_incomplete')
            recovery = runner.recover_start(root)
            check('recovery reason', recovery.get('stop_reason') == 'operator_stop')
            check('recovery state unchanged', recovery['status'] == 'recovered_exact_resources'
                  and recovery['native_state'] == 'not_started')
            check('recovery receipt includes reason', json.loads(
                (controls / 'recovery.json').read_bytes())['stop_reason'] == 'operator_stop')
        check('final and recovery preserve first request', marker.read_bytes() == first)
        check('no runtime calls', runtime_calls == [])

    result = {'passed': True, 'checks': checks, 'provider_calls': 0,
              'target_calls': 0, 'docker_calls': 0, 'native_runtime_calls': 0}
    if args.output:
        with args.output.open('x') as stream:
            json.dump(result, stream, indent=2, sort_keys=True)
            stream.write('\n')
        args.output.chmod(0o600)
    print(f'PASS: {len(checks)} stop-reason checks; provider_calls=0 target_calls=0 docker_calls=0 native_runtime_calls=0')


if __name__ == '__main__':
    main()
