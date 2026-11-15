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
        if matches:
            expected.append(('execute', COMMAND, 30))
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
    class Owner:
        def launch_model(self, *args):
            return 'original'
    for runtime in ('omp', 'codex'):
        result = {}
        environment = Environment({'output': '1.4.4\n', 'status': 'settled', 'returncode': 0})
        def run_native(root, fixture, result):
            result.update(controlled_provider_requests=0, external_provider_calls=0)
            return environment.launch_stdio(COMMAND)
        fixture = SimpleNamespace(run_native=run_native, invoke=lambda *args: None)
        fixture.main = lambda: fixture.run_native(None, SimpleNamespace(runtime=runtime), result)
        with patch.dict('sys.modules', {'check_linux_model_native_e2e': fixture,
                                      'research_environment': SimpleNamespace(Environment=Environment, subprocess=__import__('subprocess')),
                                      'native_runtime_omp': SimpleNamespace(Transport=object, Runtime=object, RuntimeError=RuntimeError),
                                      'native_runtime_codex': SimpleNamespace(Runtime=object, RuntimeError=RuntimeError),
                                      'native_runtime_linux': SimpleNamespace(LinuxModelOwner=Owner)}):
            assert driver.main() == 'original-process'
        assert fixture.run_native is run_native and Environment.launch_stdio is original
        assert ('omp_loader_preflight' in result) == (runtime == 'omp')
    for output, ready, phase in [
        ('unpublished error text', False, None),
        ('{"type":"ready","sdkVersion":"18.20.0","bunVersion":"1.4.4","platform":"linux","arch":"x64"}', True, None),
        ('{"type":"ready","sdkVersion":"wrong"}', False, None),
        ('{"type":"startup_failed","phase":"tools","error":"unpublished detail"}', False, 'tools'),
        ('{"type":"startup_failed","phase":"unpublished detail"}', False, None),
        ('null\n[]\n{"type":"startup_failed","phase":[]}', False, None),
    ]:
        summary = driver.sidecar_outcome({'status': 'settled', 'returncode': 1, 'output': output})
        assert summary == {'status': 'settled', 'returncode': 1,
                           'ready_matches': ready, 'startup_failure_phase': phase}
        assert 'unpublished' not in str(summary)
    class Failure(Exception):
        code = 'native_transport_closed'
    for operation, fail in [('catalog', False), ('catalog', True), ('other', True)]:
        class Transport:
            process = SimpleNamespace(poll=lambda: 139)
            def request(self, operation):
                if fail:
                    raise Failure('unpublished native detail')
                return {'unpublished': 'catalog-content'}
        module, result = SimpleNamespace(Transport=Transport), {}
        try:
            with driver.observe_catalog(module, result):
                returned = module.Transport().request(operation)
                assert returned == {'unpublished': 'catalog-content'}
        except Failure:
            assert fail
        assert module.Transport is Transport
        expected = {} if operation != 'catalog' else {'omp_catalog_request': (
            {'status': 'failed', 'failure': 'native_transport_closed', 'returncode_before_cleanup': 139}
            if fail else {'status': 'returned'})}
        assert result == expected and 'unpublished' not in str(result)
    for ready, exit_code, unavailable in [(False, 7, False), (True, None, False), (False, None, True)]:
        cleanup = []
        error = Failure('unpublished model detail')
        def poll():
            if unavailable:
                raise ValueError('unpublished process detail')
            return exit_code
        class Model:
            def _startup_failed(self, failure):
                cleanup.append(failure)
                failure.cleanup_result = 'verified'
        module, result = SimpleNamespace(Runtime=Model), {}
        with driver.observe_model_startup(module, result):
            model = module.Runtime()
            model.ready = ready
            model.transport = SimpleNamespace(process=SimpleNamespace(poll=poll))
            model._startup_failed(error)
        assert module.Runtime is Model and cleanup == [error] and error.cleanup_result == 'verified'
        row = result['omp_model_startup_failure']
        assert row['phase'] == ('post_ready' if ready else 'awaiting_ready')
        assert row['returncode_before_cleanup'] == exit_code
        assert ('process_observation' in row) == unavailable
        assert 'unpublished' not in str(result)
    for kind, denied in [('omp', False), ('codex', False), ('omp', True)]:
        class ModelOwner:
            profile = {'kind': kind}
            def check_authority(self):
                if denied:
                    raise Failure('unpublished denial')
            def launch_model(self, *args):
                calls.append(args)
                return 'original-process'
        calls, result = [], {}
        owner = ModelOwner()
        owner.environment = Environment({'status': 'settled', 'returncode': 0, 'output': 'omp/18.20.0\n'})
        original = ModelOwner.launch_model
        try:
            with driver.observe_model_version(ModelOwner, result):
                assert owner.launch_model(['original-command'], {'private': 'unpublished'}, object()) == 'original-process'
        except Failure:
            assert denied
        assert ModelOwner.launch_model is original
        assert len(calls) == (0 if denied else 1)
        assert len(owner.environment.calls) == (1 if kind == 'omp' and not denied else 0)
        if kind == 'omp' and not denied:
            argv = owner.environment.calls[0][1]
            assert argv == ['/usr/bin/env', '-i', 'HOME=/tmp', 'TMPDIR=/tmp', 'PI_CODING_AGENT_DIR=/tmp',
                'PATH=/usr/local/bin:/usr/bin:/bin', '/runtime/bin/model', '--version']
            assert owner.environment.calls[0][2] == 10
            assert result == {'omp_model_version_preflight': {'status': 'settled', 'returncode': 0,
                'pinned_version_matches': True, 'pinned_version_line_present': True, 'output_category': 'expected_version'}}
        else:
            assert result == {}
        assert 'unpublished' not in str(result)
    for output, expected in [('unpublished warning\nomp/18.20.0\n', True), ('118.20.0\n', False),
                             ('unpublished 18.20.0 detail', False)]:
        owner = ModelOwner()
        owner.profile = {'kind': 'omp'}
        owner.check_authority = lambda: None
        owner.environment = Environment({'status': 'settled', 'returncode': 0, 'output': output})
        result = {}
        with driver.observe_model_version(ModelOwner, result):
            owner.launch_model([], {}, None)
        row = result['omp_model_version_preflight']
        assert row['pinned_version_line_present'] is expected and row['pinned_version_matches'] is False
        assert 'unpublished' not in str(row)
    for output, expected in [('omp/18.20.0\n', 'expected_version'), ('omp/18.19.0\n', 'other_numeric_version'), ('', 'empty'), ('\x1b[32momp v18.20.0\x1b[0m\n', 'expected_version'),
                             ('1.4.4', 'other_numeric_version'), ('unpublished 18.20.0 detail', 'unrecognized'),
                             ('18.20.0\n1.4.4', 'unrecognized')]:
        assert driver.version_output_category(output) == expected
    for output, accepted in [('{"work_noexec":false,"work_available_bytes":0,"native_files":1,"native_bytes":128}', True),
        ('{"work_noexec":false,"work_available_bytes":0,"native_files":true,"native_bytes":128}', False),
        ('{"secret":"unpublished"}', False), ('unpublished', False)]:
        row = driver.model_storage_outcome({'status':'settled','returncode':0,'output':output})
        assert ('native_bytes' in row) == accepted and 'unpublished' not in str(row)
    for denied in (False, True):
        class Storage:
            def execute(self, argv, *, timeout_seconds):
                assert argv[-1] == driver.MODEL_STORAGE_PROBE and timeout_seconds == 5
                if denied:
                    raise Failure('unpublished refusal')
                return {'status':'settled','returncode':0,
                        'output':'{"work_noexec":false,"work_available_bytes":0,"native_files":1,"native_bytes":128}'}
        cleanup = []
        class Model:
            def _startup_failed(self, error):
                cleanup.append(error)
        module, result = SimpleNamespace(Runtime=Model), {}
        error = Failure('unpublished')
        with driver.observe_model_startup(module,result):
            model = module.Runtime(); model.ready = False
            model.transport = SimpleNamespace(process=SimpleNamespace(poll=lambda:1))
            model.model_owner = SimpleNamespace(environment=Storage())
            model._startup_failed(error)
        assert cleanup == [error] and module.Runtime is Model and 'unpublished' not in str(result)
        assert ('native_bytes' in result['omp_model_storage_failure']) != denied
    import tempfile
    from pathlib import Path
    scope = {'__name__': 'probe_test'}
    exec(driver.MODEL_STORAGE_PROBE, scope)
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        work = root / 'work'; work.mkdir()
        outside = root / 'outside'; outside.mkdir(); (outside / 'unrelated.node').write_bytes(b'outside')
        cache = work / '.model' / '.omp' / 'natives'; cache.mkdir(parents=True)
        (cache / 'good.node').write_bytes(b'123')
        (cache / 'linked.node').symlink_to(outside / 'unrelated.node')
        (cache / 'linked-dir').symlink_to(outside, target_is_directory=True)
        row = scope['probe'](str(work))
        assert row['native_files'] == 1 and row['native_bytes'] == 3
        cache.rename(cache.with_name('saved'))
        cache.symlink_to(outside, target_is_directory=True)
        try:
            scope['probe'](str(work))
        except OSError:
            pass
        else:
            raise AssertionError('followed cache root symlink')
        cache.unlink()
        try:
            scope['probe'](str(work))
        except FileNotFoundError:
            pass
        else:
            raise AssertionError('missing cache reported complete')
    for chunks, expected in [([b'unpublished-secret'], set()), ([b'EN', b'OSPC'], {'enospc_marker'}),
                             ([b'EENOENT'], {'enoent_marker'}),
                             ([b'No space left on device'], {'no_space_marker'}),
                             ([b'failed to map segment from shared object'], {'addon_mapping_marker'})]:
        categories = driver.ErrorCategories()
        for chunk in chunks:
            categories.feed(chunk)
        assert categories.found == expected
        assert 'unpublished' not in str(vars(categories))
    import subprocess
    import sys
    class ProcessModule:
        DEVNULL = subprocess.DEVNULL
        PIPE = subprocess.PIPE
        def Popen(self, command, *args, **kwargs):
            return subprocess.Popen([sys.executable, '-c',
                "import sys;sys.stderr.write('ENOSPC' + 'unpublished-secret' * 10000);raise SystemExit(7)"],
                *args, **kwargs)
    original = ProcessModule(); module = SimpleNamespace(subprocess=original); result = {}
    with driver.observe_model_stderr(module, result):
        process = module.subprocess.Popen(['python3','-I','-S','/runtime/native_runtime_bootstrap.py'],
            stderr=original.DEVNULL, stdout=subprocess.DEVNULL)
        assert process.wait(timeout=5) == 7
    assert module.subprocess is original
    assert result['omp_model_stderr_categories'] == [{'markers':['enospc_marker'], 'bytes':180006, 'truncated':True, 'complete':True}]
    assert 'unpublished' not in str(result)
    for direct in (False, True):
        invoked = []
        class Runtime:
            def invoke(self, *args):
                invoked.append(args)
        fixture = SimpleNamespace(invoke=lambda *args: invoked.append(args))
        module = SimpleNamespace(Runtime=Runtime, RuntimeError=Failure)
        original = fixture.invoke
        result = {'controlled_provider_requests': 0, 'external_provider_calls': 0}
        try:
            with driver.startup_only(fixture, module, result):
                if direct:
                    module.Runtime().invoke('prompt')
                else:
                    fixture.invoke('prompt')
        except Failure:
            pass
        else:
            raise AssertionError('invocation was not stopped')
        assert not invoked and fixture.invoke is original and module.Runtime is Runtime
        assert result['native_startup_only'] == 'stopped_before_invocation'
    try:
        with driver.startup_only(fixture, module, {'controlled_provider_requests': 1}):
            pass
    except Failure:
        pass
    else:
        raise AssertionError('nonzero provider count accepted')
    for runtime in ('omp', 'codex'):
        invoked = []
        result = {}
        fixture = SimpleNamespace(invoke=lambda *args: invoked.append(args))
        def run_native(root, current, result):
            result.update(controlled_provider_requests=0, external_provider_calls=0)
            fixture.invoke('must-not-send')
        fixture.run_native = run_native
        fixture.main = lambda: fixture.run_native(None, SimpleNamespace(runtime=runtime), result)
        original = fixture.invoke
        with patch.dict('sys.modules', {'check_linux_model_native_e2e': fixture,
                'research_environment': SimpleNamespace(Environment=Environment, subprocess=subprocess),
                'native_runtime_omp': SimpleNamespace(Transport=object, Runtime=object, RuntimeError=Failure),
                'native_runtime_codex': SimpleNamespace(Runtime=object, RuntimeError=Failure),
                'native_runtime_linux': SimpleNamespace(LinuxModelOwner=Owner)}):
            try:
                driver.main()
            except Failure:
                pass
            else:
                raise AssertionError('matrix runtime invoked provider')
        assert not invoked and fixture.invoke is original and fixture.run_native is run_native
    for counts in ({}, {'controlled_provider_requests':False,'external_provider_calls':0},
                   {'controlled_provider_requests':0,'external_provider_calls':-1}):
        try:
            with driver.startup_only(fixture,module,counts):
                pass
        except Failure:
            pass
        else:
            raise AssertionError('invalid provider counters accepted')
    print('passed: 61 offline diagnostic cases; no native or provider calls')


if __name__ == '__main__':
    main()
