#!/usr/bin/env python3
"""Run the existing native fixture with a bounded OMP loader observation."""
from contextlib import contextmanager


@contextmanager
def observe_loader(environment_class, result):
    original = environment_class.launch_stdio
    suffix = ['/input/native-runtime/bin/bun', '/input/native-runtime/native_runtime_omp_tools.mjs',
              '/input/native-runtime/node_modules/@oh-my-pi/pi-coding-agent', '/work']

    def launch(environment, argv, *, role='native_tools'):
        if role == 'native_tools' and argv[-4:] == suffix and argv[:2] == ['/usr/bin/env', '-i']:
            result['omp_loader_preflight'] = {'status': 'attempted'}
            observation = environment.execute(argv[:-3] + ['--version'], timeout_seconds=5)
            result['omp_loader_preflight'] = {
                'status': observation['status'], 'returncode': observation['returncode'],
                'pinned_version_matches': observation['output'].strip() == '1.4.4'}
        return original(environment, argv, role=role)

    environment_class.launch_stdio = launch
    try:
        yield
    finally:
        environment_class.launch_stdio = original


def main():
    import check_linux_model_native_e2e as fixture_module
    import research_environment
    original = fixture_module.run_native

    def run_native(root, fixture, result):
        if fixture.runtime != 'omp':
            return original(root, fixture, result)
        with observe_loader(research_environment.Environment, result):
            return original(root, fixture, result)

    fixture_module.run_native = run_native
    try:
        return fixture_module.main()
    finally:
        fixture_module.run_native = original


if __name__ == '__main__':
    raise SystemExit(main())
