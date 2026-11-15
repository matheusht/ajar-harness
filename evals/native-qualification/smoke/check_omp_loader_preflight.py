#!/usr/bin/env python3
"""Run the existing native fixture with a bounded OMP loader observation."""
from contextlib import contextmanager
import json
import re

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




MODEL_STORAGE_PROBE = """import json, os, stat
from contextlib import ExitStack

def probe(work):
    def fail(error):
        raise error
    with ExitStack() as stack:
        fd = os.open(work, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        stack.callback(os.close, fd)
        v = os.fstatvfs(fd)
        for name in ('.model', '.omp', 'natives'):
            fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            stack.callback(os.close, fd)
        count = size = entries = 0
        for directory, directories, files, current in os.fwalk('.', dir_fd=fd, follow_symlinks=False, onerror=fail):
            entries += len(directories) + len(files)
            if entries > 1000:
                raise ValueError('bounded')
            for name in files:
                if name.endswith('.node'):
                    info = os.stat(name, dir_fd=current, follow_symlinks=False)
                    if stat.S_ISREG(info.st_mode):
                        count += 1
                        size += info.st_size
        return {'work_available_bytes': v.f_bavail * v.f_frsize,
                'native_files': count, 'native_bytes': size}

if __name__ == '__main__':
    print(json.dumps(probe('/work')))
"""

def model_storage_outcome(observation):
    row = {'status': observation['status'], 'returncode': observation['returncode']}
    try:
        data = json.loads(observation['output'])
    except (ValueError, TypeError):
        data = None
    keys = {'work_available_bytes', 'native_files', 'native_bytes'}
    if (observation['status'] == 'settled' and observation['returncode'] == 0 and
            isinstance(data, dict) and set(data) == keys and
            all(type(value) is int and 0 <= value <= 2**53 for value in data.values())):
        row.update(data)
    else:
        row['observation'] = 'unavailable'
    return row


@contextmanager
def observe_model_startup(runtime_module, result):
    original = runtime_module.Runtime

    class ObservedRuntime(original):
        def _startup_failed(self, error):
            row = {'phase': 'post_ready' if self.ready else 'awaiting_ready',
                   'returncode_before_cleanup': None}
            result['omp_model_startup_failure'] = row
            try:
                if self.transport is not None:
                    row['returncode_before_cleanup'] = self.transport.process.poll()
            except Exception:
                row['process_observation'] = 'unavailable'
            try:
                owner = getattr(self, 'model_owner', None)
                if owner is not None and row['returncode_before_cleanup'] is not None:
                    result['omp_model_storage_failure'] = model_storage_outcome(owner.environment.execute([
                        '/usr/bin/env', '-i', 'PATH=/usr/local/bin:/usr/bin:/bin',
                        'python3', '-I', '-S', '-c', MODEL_STORAGE_PROBE], timeout_seconds=5))
            except Exception:
                result['omp_model_storage_failure'] = {'observation': 'unavailable'}
            return super()._startup_failed(error)

    runtime_module.Runtime = ObservedRuntime
    try:
        yield
    finally:
        runtime_module.Runtime = original




def version_output_category(output):
    if not output.strip():
        return 'empty'
    # Classify complete version lines only; never return captured native text.
    plain = re.sub(r'\x1b\[[0-9;]*m', '', output)
    versions = []
    for line in plain.splitlines():
        match = re.fullmatch(r'(?:omp/|omp(?: version)?[ \t]+)?v?([0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3})', line.strip())
        if match:
            versions.append(match.group(1))
    if len(versions) != 1:
        return 'unrecognized'
    return 'expected_version' if versions[0] == '18.20.0' else 'other_numeric_version'


@contextmanager
def observe_model_version(owner_class, result):
    original = owner_class.launch_model

    def launch(owner, command, public_environment, binding):
        if owner.profile['kind'] == 'omp':
            owner.check_authority()
            result['omp_model_version_preflight'] = {'status': 'attempted'}
            observation = owner.environment.execute([
                '/usr/bin/env', '-i', 'HOME=/tmp', 'TMPDIR=/tmp', 'PI_CODING_AGENT_DIR=/tmp',
                'PATH=/usr/local/bin:/usr/bin:/bin', '/runtime/bin/model', '--version'], timeout_seconds=10)
            result['omp_model_version_preflight'] = {
                'status': observation['status'], 'returncode': observation['returncode'],
                'pinned_version_matches': observation['output'].strip() == 'omp/18.20.0',
                'pinned_version_line_present': 'omp/18.20.0' in observation['output'].splitlines(),
                'output_category': version_output_category(observation['output'])}
        return original(owner, command, public_environment, binding)

    owner_class.launch_model = launch
    try:
        yield
    finally:
        owner_class.launch_model = original


def main():
    import check_linux_model_native_e2e as fixture_module
    import research_environment
    import native_runtime_omp
    import native_runtime_linux
    original = fixture_module.run_native

    def run_native(root, fixture, result):
        if fixture.runtime != 'omp':
            return original(root, fixture, result)
        with observe_loader(research_environment.Environment, result), observe_catalog(native_runtime_omp, result), observe_model_startup(native_runtime_omp, result), observe_model_version(native_runtime_linux.LinuxModelOwner, result):
            return original(root, fixture, result)

    fixture_module.run_native = run_native
    try:
        return fixture_module.main()
    finally:
        fixture_module.run_native = original


if __name__ == '__main__':
    raise SystemExit(main())
