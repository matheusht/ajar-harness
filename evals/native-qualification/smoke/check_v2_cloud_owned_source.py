#!/usr/bin/env python3
"""No-Docker cloud owned pin/origin and failure-teardown checks."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[3]
RUNNER = ROOT / 'evals/native-qualification/smoke/opencode_v2_managed_owned.py'
STOP_OWNER = ROOT / 'experiments/native-network-preflight/v2-effect-windows/_native_stop_owner.py'
RELAY = 'experiments/native-network-preflight/tcp-relay-host-override/cloud-linux-amd64-20261020a/tcp-relay-linux-amd64'
RELAY_SHA = '33ef7484c2a2415915af399689e91e9efee8000b2c685a6b2b72eb4eddedf895'
CURRENT_MANIFEST = Path('evals/native-qualification/t02-source/SOURCE-MANIFEST.json')


def select_manifest(root, current=False):
    extracted = root / 'SOURCE-MANIFEST.json'
    if extracted.exists() or extracted.is_symlink():
        historical = extracted
    else:
        historical = root / 'evals/native-qualification/t02-cloud-transfer-20261020/SOURCE-MANIFEST.json'
    return root / CURRENT_MANIFEST if current else historical


def stage_sources(root, staged, manifest):
    if manifest.is_symlink() or staged.exists():
        raise ValueError('manifest_invalid')
    try:
        document = json.loads(manifest.read_text())
        files = document['files']
        if document['schema_version'] != 1 or document['kind'] != 't02-cloud-source' \
                or not isinstance(files, list) or not files:
            raise ValueError
    except (OSError, ValueError, KeyError, TypeError):
        raise ValueError('manifest_invalid') from None
    checked = []
    names = set()
    for item in files:
        try:
            name, size, expected = item['path'], item['bytes'], item['sha256']
            relative = Path(name)
            if (not isinstance(name, str) or not name or relative.as_posix() != name
                    or relative.is_absolute()
                    or '..' in relative.parts or name in names or type(size) is not int
                    or size < 0 or not isinstance(expected, str)):
                raise ValueError
            source = root / relative
            if (source.is_symlink() or not source.is_file()
                    or not source.resolve().is_relative_to(root.resolve())):
                raise ValueError
            data = source.read_bytes()
            if len(data) != size or hashlib.sha256(data).hexdigest() != expected:
                raise ValueError
            checked.append((relative, data, source.stat().st_mode & 0o777))
            names.add(name)
        except (OSError, ValueError, KeyError, TypeError):
            raise ValueError('manifest_source_mismatch') from None
    for relative, data, mode in checked:
        destination = staged / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        destination.chmod(mode)
    return len(checked)


def load(path):
    spec = importlib.util.spec_from_file_location('cloud_owned_runner_check', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(staged, output, marker, corrupt_copy=False, corrupt_stop_owner_copy=False,
        live_free=False, runtime_ca=None):
    runner = staged / RUNNER.relative_to(ROOT)
    args = ['--output', str(output), '--cloud-platform', 'linux/amd64',
            '--cloud-image-id', 'sha256:' + 'a' * 64,
            '--cloud-relay', str(staged / RELAY), '--cloud-relay-sha256', RELAY_SHA,
            '--cloud-internal-subnet', '172.28.225.0/24',
            '--cloud-external-subnet', '172.28.224.0/24',
            '--cloud-listen-address', '172.28.224.1',
            '--cloud-relay-peer', '172.28.224.10',
            '--cloud-upstream-route', 'HTTPS_PROXY']
    if live_free:
        args.append('--live-free')
    if runtime_ca is not None:
        args += ['--live-runtime-ca', str(runtime_ca),
                 '--live-runtime-ca-sha256', hashlib.sha256(runtime_ca.read_bytes()).hexdigest()]
    env = os.environ.copy()
    env['HTTPS_PROXY'] = 'http://127.0.0.1:3128'
    env['T02_DOCKER_MARKER'] = str(marker)
    env['PATH'] = str(staged / 'fake-bin') + os.pathsep + env.get('PATH', '')
    if corrupt_copy or corrupt_stop_owner_copy:
        source_name = 'STOP_OWNER' if corrupt_stop_owner_copy else 'CONFIG'
        code = f'''
import importlib.util, pathlib, sys
path = pathlib.Path(sys.argv[1]); spec = importlib.util.spec_from_file_location('candidate', path)
candidate = importlib.util.module_from_spec(spec); spec.loader.exec_module(candidate)
original = candidate.shutil.copy2
def corrupt(source, destination, *args, **kwargs):
    result = original(source, destination, *args, **kwargs)
    if pathlib.Path(source) == candidate.{source_name} and 'source' in pathlib.Path(destination).parts:
        pathlib.Path(destination).write_bytes(pathlib.Path(destination).read_bytes() + b' ')
    return result
candidate.shutil.copy2 = corrupt
sys.argv = [str(path), *sys.argv[2:]]
raise SystemExit(candidate.main())
'''
        command = [sys.executable, '-c', code, str(runner), *args]
    else:
        command = [sys.executable, str(runner), *args]
    return subprocess.run(command, env=env, capture_output=True, text=True, timeout=15)


def check_teardown(module, root):
    original = module.cleanup_owned
    try:
        for mode in ('pass', 'closed_before_activation', 'not_started',
                     'close_error', 'unsafe', 'uncertain', 'prior_unsafe',
                     'no_native', 'no_native_prior_unsafe'):
            work = root / ('temporary-' + mode)
            work.mkdir(mode=0o700)
            (work / 'capability').write_text('test-only')
            calls = []

            class Native:
                def close(self):
                    assert work.exists()
                    calls.append('close')
                    if mode == 'close_error':
                        raise RuntimeError('synthetic_stop_failure')
                    return {'status': mode if mode in ('unsafe', 'closed_before_activation',
                                                       'not_started') else 'stopped'}

            def cleanup(resources, nonce, docker):
                assert work.exists()
                calls.append('cleanup')
                return [{'kind': 'container', 'id': 'owned', 'absent': mode != 'uncertain'}]

            module.cleanup_owned = cleanup
            native = None if mode.startswith('no_native') else Native()
            prior_stop = {'status': 'unsafe'} if mode in ('prior_unsafe', 'no_native_prior_unsafe') else None
            result = module.finish_owned(native, [('container', 'owned')], 'nonce', None,
                                         work, prior_stop)
            assert calls == (['close'] if native and prior_stop is None else []) + ['cleanup'], (mode, calls)
            assert result['cleanup_complete'] is (mode != 'uncertain')
            removed = mode in ('pass', 'closed_before_activation', 'not_started', 'no_native')
            assert result['temporary_secret_files_removed'] is removed, mode
            assert work.exists() is (not removed)
            if mode == 'close_error':
                assert result['native_stop_error']['code'] == 'synthetic_stop_failure'
            if not removed:
                assert result['temporary_workspace_unresolved'] == str(work)
                shutil.rmtree(work)
    finally:
        module.cleanup_owned = original


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--current-manifest', action='store_true',
                        help='explicitly check the post-transfer source manifest')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='t02-cloud-owned-source-') as directory:
        temp = Path(directory)
        staged = (temp / 'repo').resolve()
        stage_sources(ROOT, staged, select_manifest(ROOT, current=args.current_manifest))
        fake = staged / 'fake-bin/docker'
        fake.parent.mkdir()
        fake.write_text('#!/bin/sh\nprintf called >> "$T02_DOCKER_MARKER"\nexit 99\n')
        fake.chmod(0o700)
        staged_module = load(staged / RUNNER.relative_to(ROOT))
        module = staged_module
        helper = staged / STOP_OWNER.relative_to(ROOT)
        assert staged_module.STOP_OWNER in staged_module.CONTROL_SHA and helper.is_file()
        assert len(staged_module.CLOUD_OWNED_INPUT_SHA) == 7
        ca_pem = None
        if args.current_manifest:
            ca_key, ca_pem = temp / 'ca.key', temp / 'ca.pem'
            generated = subprocess.run([
                'openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-noenc', '-days', '1',
                '-sha256', '-subj', '/CN=T02 benign source-check CA',
                '-addext', 'basicConstraints=critical,CA:TRUE',
                '-keyout', str(ca_key), '-out', str(ca_pem)],
                capture_output=True, text=True, timeout=15)
            assert generated.returncode == 0
            ca_key.chmod(0o600)
            ca_pem.chmod(0o600)
        marker = temp / 'docker-called'
        output = temp / 'live-denied'
        result = run(staged, output, marker, live_free=True, runtime_ca=ca_pem)
        assert result.returncode != 0 and 'cloud_live_route_not_qualified' in result.stderr
        assert not output.exists() and not marker.exists()
        original_helper = helper.read_bytes()
        for name, changed in (('missing-stop-owner', None),
                              ('mutated-stop-owner', original_helper + b' ')):
            if changed is None:
                helper.unlink()
            else:
                helper.write_bytes(changed)
            output = temp / name
            result = run(staged, output, marker)
            assert result.returncode != 0 and 'control_pin_mismatch' in result.stderr
            assert not output.exists() and not marker.exists()
            helper.write_bytes(original_helper)
        for index, path in enumerate(staged_module.CLOUD_OWNED_INPUT_SHA):
            source = staged / path.relative_to(staged_module.ROOT)
            original = source.read_bytes()
            source.write_bytes(original + b' ')
            output = temp / ('mutated-' + str(index))
            result = run(staged, output, marker)
            assert result.returncode != 0 and 'cloud_owned_input_pin_mismatch' in result.stderr
            assert not output.exists() and not marker.exists(), path
            source.write_bytes(original)
        output = temp / 'archive-mutated'
        result = run(staged, output, marker, corrupt_copy=True)
        assert result.returncode != 0 and not marker.exists()
        report = json.loads((output / 'result.json').read_text())
        assert {'name': 'archived cloud owned inputs match fixed reviewed pins', 'pass': False} in report['checks']
        assert report['status'] == 'fail'
        output = temp / 'archive-stop-owner-mutated'
        result = run(staged, output, marker, corrupt_stop_owner_copy=True)
        assert result.returncode != 0 and not marker.exists()
        report = json.loads((output / 'result.json').read_text())
        assert report['status'] == 'fail' and 'active_control_origins' not in report
        assert report['error']['code'] == 'archived_control_pin_mismatch'
        output = temp / 'archive-unchanged'
        result = run(staged, output, marker)
        assert result.returncode != 0 and marker.exists()
        report = json.loads((output / 'result.json').read_text())
        assert {'name': 'archived cloud owned inputs match fixed reviewed pins', 'pass': True} in report['checks']
        assert {'name': 'cloud owned mounts and fixture sources select archive', 'pass': True} in report['checks']
        assert report['active_control_origins']['stop_owner'] == str((output / 'source' / STOP_OWNER.relative_to(ROOT)).resolve())
        check_teardown(module, temp)
    print('PASS: live-free pre-output denial, 7 input mutations, stop-owner pins/origin, 9 teardown cases; no real Docker/provider/CI')


if __name__ == '__main__':
    main()
