#!/usr/bin/env python3
"""Offline command/output contract checks; not a native loader qualification."""
from check_omp_loader_preflight import observe_loader
import check_omp_loader_preflight as driver
from types import SimpleNamespace
from unittest.mock import patch

COMMAND = ['/usr/bin/env', '-i', 'HOME=/work', 'PATH=/usr/bin:/bin',
           '/input/native-runtime/bin/bun', '/input/native-runtime/native_runtime_omp_tools.mjs',
           '/input/native-runtime/node_modules/@oh-my-pi/pi-coding-agent', '/work']


class Environment:
    def __init__(self, observation):
        self.observation = observation
        self.calls = []

    def execute(self, argv, *, timeout_seconds):
        self.calls.append(('execute', argv, timeout_seconds))
        if isinstance(self.observation, list):
            return self.observation.pop(0)
        if isinstance(self.observation, Exception):
            raise self.observation
        return self.observation

    def launch_stdio(self, argv, *, role='native_tools'):
        self.calls.append(('launch', argv, role))
        return 'original-process'


def main():
    original = Environment.launch_stdio
    for output, status, code, matches in [('1.4.4\n', 'settled', 0, True),
        ('unpublished diagnostic text', 'settled', 127, False), ('[output withheld]', 'unknown', -9, False)]:
        environment = Environment({'output': output, 'status': status, 'returncode': code})
        result = {}
        with observe_loader(Environment, result):
            assert environment.launch_stdio(COMMAND) == 'original-process'
        expected = [('execute', COMMAND[:-3] + ['--version'], 5)]
        if matches:
            expected.extend(('execute', COMMAND[:-3] + ['--eval', script], 5) for _, script in driver.PROBES)
        expected.append(('launch', COMMAND, 'native_tools'))
        assert environment.calls == expected
        assert result['omp_loader_preflight'] == {'status': status, 'returncode': code,
                                                 'pinned_version_matches': matches}
        assert ('omp_import_preflight' in result) == matches
        assert output not in str(result)
        assert Environment.launch_stdio is original
    for argv, role in [(COMMAND, 'model'), (COMMAND[:-1], 'native_tools'),
                       (['unexpected', *COMMAND[1:]], 'native_tools')]:
        environment, result = Environment({}), {}
        with observe_loader(Environment, result):
            environment.launch_stdio(argv, role=role)
        assert result == {} and environment.calls == [('launch', argv, role)]
    environment, result = Environment(RuntimeError('denied')), {}
    try:
        with observe_loader(Environment, result):
            environment.launch_stdio(COMMAND)
    except RuntimeError:
        pass
    else:
        raise AssertionError('Denied execution continued')
    assert len(environment.calls) == 1 and Environment.launch_stdio is original
    assert result == {'omp_loader_preflight': {'status': 'attempted'}}
    for failed_phase in range(len(driver.PROBES)):
        passed = {'output': '1.4.4', 'status': 'settled', 'returncode': 0}
        failed = {'output': 'unpublished failure detail', 'status': 'settled', 'returncode': 133}
        environment = Environment([passed] * (failed_phase + 1) + [failed])
        result = {}
        with observe_loader(Environment, result):
            environment.launch_stdio(COMMAND)
        rows = result['omp_import_preflight']
        assert len(rows) == failed_phase + 1 and rows[-1]['phase'] == driver.PROBES[failed_phase][0]
        assert rows[-1]['returncode'] == 133 and 'unpublished' not in str(result)
        assert environment.calls[-1] == ('launch', COMMAND, 'native_tools')
        assert Environment.launch_stdio is original
    for runtime in ('omp', 'codex'):
        result = {}
        environment = Environment({'output': '1.4.4\n', 'status': 'settled', 'returncode': 0})
        def run_native(root, fixture, result):
            return environment.launch_stdio(COMMAND)
        fixture = SimpleNamespace(run_native=run_native)
        fixture.main = lambda: fixture.run_native(None, SimpleNamespace(runtime=runtime), result)
        with patch.dict('sys.modules', {'check_linux_model_native_e2e': fixture,
                                      'research_environment': SimpleNamespace(Environment=Environment)}):
            assert driver.main() == 'original-process'
        assert fixture.run_native is run_native and Environment.launch_stdio is original
        assert ('omp_loader_preflight' in result) == (runtime == 'omp')
    print('passed: 13 offline loader-preflight cases; no native or provider calls')


if __name__ == '__main__':
    main()
