#!/usr/bin/env python3
"""Run the existing native fixture with a bounded OMP loader observation."""
from contextlib import contextmanager
import json

PROBES = (
    ('javascript', 'void 0'),
    ('sdk_import', 'await import("file:///input/native-runtime/node_modules/@oh-my-pi/pi-coding-agent/src/sdk.ts")'),
    ('schema_import', 'await import("file:///input/native-runtime/node_modules/@oh-my-pi/pi-ai/src/utils/schema/wire.ts")'),
    ('validation_import', 'await import("file:///input/native-runtime/node_modules/@oh-my-pi/pi-ai/src/utils/validation.ts")'),
)


def sidecar_outcome(observation):
    result = {'status': observation['status'], 'returncode': observation['returncode'],
              'ready_matches': False, 'startup_failure_phase': None}
    for line in observation['output'].splitlines():
        try:
            frame = json.loads(line)
        except ValueError:
            continue
        if not isinstance(frame, dict):
            continue
        if frame.get('type') == 'ready' and all(frame.get(key) == value for key, value in
                {'sdkVersion': '18.20.0', 'bunVersion': '1.4.4', 'platform': 'linux', 'arch': 'x64'}.items()):
            result['ready_matches'] = True
        if frame.get('type') == 'startup_failed' and frame.get('phase') in (
                'paths', 'manifest', 'sdk_import', 'schema_import', 'validation_import', 'settings', 'tools', 'catalog'):
            result['startup_failure_phase'] = frame['phase']
    return result


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
            if observation['status'] == 'settled' and observation['returncode'] == 0 and result['omp_loader_preflight']['pinned_version_matches']:
                result['omp_import_preflight'] = []
                for phase, script in PROBES:
                    row = {'phase': phase, 'status': 'attempted'}
                    result['omp_import_preflight'].append(row)
                    observation = environment.execute(argv[:-3] + ['--eval', script], timeout_seconds=5)
                    row.update(status=observation['status'], returncode=observation['returncode'])
                    if observation['status'] != 'settled' or observation['returncode'] != 0:
                        break
                else:
                    result['omp_sidecar_eof_preflight'] = {'status': 'attempted'}
                    result['omp_sidecar_eof_preflight'] = sidecar_outcome(
                        environment.execute(argv, timeout_seconds=30))
        return original(environment, argv, role=role)

    environment_class.launch_stdio = launch
    try:
        yield
    finally:
        environment_class.launch_stdio = original


@contextmanager
def observe_catalog(runtime_module, result):
    original = runtime_module.Transport

    class ObservedTransport(original):
        def request(self, operation, *args, **kwargs):
            try:
                response = super().request(operation, *args, **kwargs)
            except Exception as error:
                if operation == 'catalog':
                    code = getattr(error, 'code', None)
                    result['omp_catalog_request'] = {'status': 'failed',
                        'failure': code if code in ('native_transport_closed', 'native_response_timeout',
                            'native_protocol_invalid_or_overflow', 'native_request_rejected') else 'other',
                        'returncode_before_cleanup': self.process.poll()}
                raise
            if operation == 'catalog':
                result['omp_catalog_request'] = {'status': 'returned'}
            return response

    runtime_module.Transport = ObservedTransport
    try:
        yield
    finally:
        runtime_module.Transport = original


def main():
    import check_linux_model_native_e2e as fixture_module
    import research_environment
    import native_runtime_omp
    original = fixture_module.run_native

    def run_native(root, fixture, result):
        if fixture.runtime != 'omp':
            return original(root, fixture, result)
        with observe_loader(research_environment.Environment, result), observe_catalog(native_runtime_omp, result):
            return original(root, fixture, result)

    fixture_module.run_native = run_native
    try:
        return fixture_module.main()
    finally:
        fixture_module.run_native = original


if __name__ == '__main__':
    raise SystemExit(main())
