#!/usr/bin/env python3
"""Provider-free public-CLI check of a stop before NativeRun preparation."""

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[3]
CLI = ROOT / 'tools/native_research.py'
NATIVE = 'experiments/native-network-preflight/v2-effect-windows/native_run.py'
CONTROLS = ('tools/docker_session_runtime.py',
            'experiments/native-network-preflight/v2-effect-windows/producer_stop.py',
            NATIVE, 'experiments/native-network-preflight/v2_connect.py')


def stop(root: Path, expected: str) -> None:
    call = subprocess.run([sys.executable, str(CLI), 'stop', '--run-root', str(root)],
                          capture_output=True, text=True, check=False)
    assert call.returncode == 0, call.stderr or call.stdout
    assert json.loads(call.stdout)['status'] == expected, call.stdout


def main() -> None:
    with TemporaryDirectory(prefix='native-preactivation-stop-') as temp:
        root = Path(temp) / 'run'
        controls = root / 'controls'
        root.mkdir(mode=0o700)
        controls.mkdir(mode=0o700)
        stop(root, 'not_active')
        state = controls / 'native-state'
        assert not state.exists(), 'prepared-only stop poisoned later startup'

        for name in CONTROLS:
            destination = controls / name
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, destination)
        resources = controls / 'resources.json'
        resources.write_text(json.dumps({'nonce': 'a' * 32, 'resources': []}) + '\n')
        resources.chmod(0o600)

        stop(root, 'stop_requested')
        marker = state / 'STOP_REQUEST'
        first = marker.read_bytes()
        assert json.loads(first)['reason'] == 'operator_stop'
        stop(root, 'stop_requested')
        assert marker.read_bytes() == first, 'repeat stop changed the durable request'

        spec = importlib.util.spec_from_file_location('preactivation_native_run', controls / NATIVE)
        native = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(native)
        try:
            native.prepare(state, controls / 'producer-manifest.json', None, 30)
        except ValueError as error:
            assert str(error) == 'native_run_cannot_restart', error
        else:
            raise AssertionError('NativeRun accepted producer startup after operator stop')
        assert not (state / 'RUN.json').exists()

        owner = Path(temp) / 'owner'
        (owner / 'controls').mkdir(mode=0o700, parents=True)
        owner.chmod(0o700)
        runner_spec = importlib.util.spec_from_file_location('preactivation_runner', CLI)
        runner = importlib.util.module_from_spec(runner_spec)
        runner_spec.loader.exec_module(runner)

        class FakeRun:
            start_calls = 0

            def __init__(self, *_):
                pass

            def start(self):
                FakeRun.start_calls += 1
                raise AssertionError('producer startup reached after operator stop')

            def close(self):
                return {'status': 'not_started'}

        class FakeNative:
            NativeRun = FakeRun
            request_stop = staticmethod(native.request_stop)

        plan = {'image_id': 'sha256:' + '1' * 64, 'target_image_id': 'sha256:' + '2' * 64,
                'platform': 'linux/amd64', 'limits': {'duration_seconds': 30,
                                                      'max_connections': 1, 'max_bytes': 4096}}
        runner._verified_plan = lambda *_args, **_kwargs: plan
        runner._approval = lambda *_args: None
        runner._image = lambda *_args, **_kwargs: None
        runner._activate_controls = lambda *_args: (FakeNative, None)
        runner._created_manifest = lambda *_args: owner / 'controls/producer-manifest.json'
        runner._capture_stop = lambda *_args: {'status': 'not_configured'}
        cleanup_requires_created = []

        def cleanup(*_args, require_created=False):
            cleanup_requires_created.append(require_created)
            return {'status': 'complete'}

        runner._cleanup_resources = cleanup
        runner._capture_cleanup = lambda *_args: {'status': 'not_configured'}

        def preseal(*_args):
            assert runner.stop(owner)['status'] == 'stop_requested'
            return {}

        runner._preseal = preseal
        try:
            runner._start_owned(owner, owner / 'approval.json')
        except runner.NativeResearchError as error:
            assert str(error) == 'native_stop_before_start', error
        else:
            raise AssertionError('owner ignored the preactivation stop')
        assert FakeRun.start_calls == 0
        assert cleanup_requires_created == [True], 'owner cleanup did not require created-stopped producers'
        final = json.loads((owner / 'controls/final.json').read_text())
        assert final['status'] == 'start_incomplete' and final['cleanup']['status'] == 'complete'
        assert not (owner / 'controls/capability').exists()
    print('PASS: prepared stop is a no-op; preactivation stop is durable and blocks NativeRun; provider_calls=0 docker_calls=0 target_calls=0')


if __name__ == '__main__':
    main()
