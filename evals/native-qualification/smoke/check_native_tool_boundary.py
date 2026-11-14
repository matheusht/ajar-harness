#!/usr/bin/env python3
"""Failure-first boundary checks for the unchanged OMP SDK tools.

Required failures before bridge implementation:
- Missing/mutated SDK or wrong platform refuses before environment launch.
- Supplied launcher owns the only SDK process; no host Popen fallback is allowed.
- Environment launch refusal is not retried through another route.
- Native read/write works inside workspace; sibling credential bytes stay unreadable.
- Shell/Bun subprocesses and symlinks cannot read the sibling credential marker.
- URL tools, direct TCP and Unix sockets cannot reach the simulated provider boundary.
- Ambient secret-like environment variables are not inherited by the SDK owner.
- Cancel/close leave no owned process, without asserting unrelated lab cleanup.

The macOS fixture is engineering evidence, not a signed Linux/Docker environment.
It uses fake marker data, an owned loopback listener and no model/provider calls.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))


def require(value, message):
    if not value:
        raise AssertionError(message)


def check(root, sdk):
    from native_runtime_omp import ToolOwner, sdk_tree_digest
    from native_runtime_transport import RuntimeError
    workspace, state, outside = (root / name for name in ('workspace', 'state', 'outside'))
    workspace.mkdir();outside.mkdir()
    marker = outside / 'credential-marker'
    marker.write_text('OUTSIDE_PROVIDER_MARKER')
    allowed = workspace / 'allowed.txt';allowed.write_text('ALLOWED_WORKSPACE_BYTES')
    (workspace / 'escape').symlink_to(marker)
    sdk_root = sdk.resolve().parents[2]
    bun = Path(shutil.which('bun')).resolve()
    sidecar = (ROOT / 'tools/native_runtime_omp_tools.mjs').resolve()
    q = json.dumps
    policy = f'''(version 1)
(deny default)
(import "system.sb")
(allow process-fork process-exec)
(allow signal (target same-sandbox))
(allow process-info* (target self))
(allow file-read-metadata)
(allow file-read* file-test-existence
  (path-ancestors {q(str(sdk_root))}) (path-ancestors {q(str(bun))}) (path-ancestors {q(str(sidecar))}))
(allow file-read* file-test-existence file-map-executable
  (subpath {q(str(sdk_root))}) (literal {q(str(bun))}) (literal {q(str(sidecar))})
  (subpath "/bin") (subpath "/usr/bin") (subpath "/usr/libexec"))
(allow file-read* file-test-existence file-write* (subpath {q(str(workspace))}) (subpath {q(str(state))}))
(deny network*)
'''
    launches = []
    def launch(command):
        launches.append(command)
        return subprocess.Popen(['/usr/bin/sandbox-exec', '-p', policy, *command],
            cwd=workspace, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env={'PATH': str(bun.parent) + ':/usr/bin:/bin', 'PI_CODING_AGENT_DIR': str(state),
                 'TMPDIR': str(workspace)}, start_new_session=True)
    sdk_pin = {'root': str(sdk_root), 'sha256': sdk_tree_digest(sdk_root)}
    try:
        ToolOwner(sdk, workspace, root / 'wrong-platform', sdk_pin=sdk_pin, dispatch_guard=nullcontext,
                  launcher=launch, command=['unreachable'], target_platform='linux/amd64')
        raise AssertionError('Darwin SDK selected for Linux environment')
    except RuntimeError as error:
        require(str(error) == 'native_sdk_platform_unavailable', 'wrong platform refusal')
    try:
        ToolOwner(sdk, workspace, root / 'invalid-state', sdk_pin=sdk_pin, dispatch_guard=nullcontext,
                  command_prefix=['/usr/bin/false'], command=['invalid-remote-command'])
        raise AssertionError('command without launcher silently selected host execution')
    except RuntimeError as error:
        require(str(error) == 'native_tool_owner_launcher_invalid', 'wrong launcher refusal')
    def refused(command):
        raise RuntimeError('fixture_environment_revoked')
    try:
        ToolOwner(sdk, workspace, root / 'refused-state', sdk_pin=sdk_pin, dispatch_guard=nullcontext,
                  launcher=refused, command=['unreachable'], target_platform='darwin/arm64')
        raise AssertionError('environment launch refusal ignored')
    except RuntimeError as error:
        require(str(error) == 'fixture_environment_revoked', 'environment refusal fell back to host')
    os.environ['OSLIT_FAKE_SECRET'] = 'AMBIENT_SECRET_MARKER'
    owner = ToolOwner(sdk, workspace, state,
        sdk_pin=sdk_pin, dispatch_guard=nullcontext,
        launcher=launch, command=[str(bun), str(sidecar), str(sdk.resolve()), str(workspace)],
        target_platform='darwin/arm64')
    rows = []
    def call(name, arguments, identity):
        owner.invoke(name, arguments, identity)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            for result in owner.observe(.1):
                if result['call_id'] == identity:
                    rows.append({'id': identity, 'status': result['status'], 'result': result['result']})
                    return result
        raise AssertionError('tool outcome missing: ' + identity)
    try:
        positive = call('read', {'path': str(allowed)}, 'inside-read')
        require('ALLOWED_WORKSPACE_BYTES' in json.dumps(positive), 'positive native read failed')
        call('write', {'path': str(workspace / 'written.txt'), 'content': 'NATIVE_WRITE'}, 'inside-write')
        require((workspace / 'written.txt').read_text() == 'NATIVE_WRITE', 'positive native write failed')
        for name in ('outside-read', 'symlink-read'):
            result = call('read', {'path': str(marker if name == 'outside-read' else workspace / 'escape')}, name)
            require('OUTSIDE_PROVIDER_MARKER' not in json.dumps(result) and result['status'] == 'unknown',
                    'native read escaped workspace')
        script = 'const fs=require("fs");try{console.log(fs.readFileSync(' + q(str(marker)) + ',"utf8"))}catch(e){console.log(e.code)}'
        result = call('bash', {'command': shlex.join([str(bun), '-e', script]), 'timeout': 3}, 'subprocess-read')
        require('EPERM' in json.dumps(result) or 'EACCES' in json.dumps(result), 'subprocess denial not observed')
        result = call('bash', {'command': 'printf "${OSLIT_FAKE_SECRET-unset}"', 'timeout': 3}, 'clean-environment')
        require('unset' in json.dumps(result), 'unexpected secret-like environment inheritance')
        listener = socket.socket();listener.bind(('127.0.0.1', 0));listener.listen();listener.settimeout(.1)
        port = listener.getsockname()[1]
        connects = []
        stop = threading.Event()
        def accept():
            while not stop.is_set():
                try:
                    client, _ = listener.accept();connects.append(True);client.close()
                except TimeoutError:
                    pass
        thread = threading.Thread(target=accept, daemon=True);thread.start()
        try:
            with socket.create_connection(('127.0.0.1', port)):
                pass
            deadline = time.monotonic() + 1
            while not connects and time.monotonic() < deadline:time.sleep(.01)
            require(len(connects) == 1, 'positive host network control failed')
            call('read', {'path': f'http://127.0.0.1:{port}/fixture'}, 'native-url-denied')
            script = f'Bun.connect({{hostname:"127.0.0.1",port:{port},socket:{{data(){{}},open(){{console.log("ESCAPED")}}}}}}).catch(e=>console.log(e.code));'
            result = call('bash', {'command': shlex.join([str(bun), '-e', script]), 'timeout': 3}, 'direct-tcp-denied')
            require(len(connects) == 1 and 'ESCAPED' not in json.dumps(result), 'native direct network escaped')
        finally:
            stop.set();thread.join(timeout=1);listener.close()
        socket_directory = tempfile.TemporaryDirectory(prefix='oslit-sock-', dir='/tmp')
        unix_path = Path(socket_directory.name) / 'provider.sock'
        unix = socket.socket(socket.AF_UNIX);unix.bind(str(unix_path));unix.listen();unix.settimeout(.1)
        try:
            script = 'Bun.connect({unix:' + q(str(unix_path)) + ',socket:{data(){},open(){console.log("ESCAPED")}}}).catch(e=>console.log(e.code));'
            result = call('bash', {'command': shlex.join([str(bun), '-e', script]), 'timeout': 3}, 'unix-socket-denied')
            require('ESCAPED' not in json.dumps(result), 'native unix socket escaped')
            try:
                client, _ = unix.accept();client.close()
                raise AssertionError('native unix socket connected')
            except TimeoutError:
                pass
        finally:
            unix.close();socket_directory.cleanup()
    finally:
        os.environ.pop('OSLIT_FAKE_SECRET', None)
        closed = owner.close()
    require(len(launches) == 1 and closed['process_exited'], 'launcher not sole process owner')
    return {'status': 'passed', 'evidence': 'actual_macos_sdk_boundary_fixture',
            'bun_version': subprocess.check_output([str(bun), '--version'], text=True).strip(),
            'sdk_engine_requirement': json.loads((sdk / 'package.json').read_text()).get('engines'),
            'checks': rows, 'launches': len(launches), 'close': closed,
            'unverified': ['Linux/Docker/SSH', 'provider_credentials', 'whole-engagement_qualification']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--omp-sdk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='native-tool-boundary-') as directory:
        result = check(Path(directory).resolve(), args.omp_sdk)
    result['source_hashes'] = {str(path.relative_to(ROOT)): 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()
        for path in [Path(__file__), *sorted((ROOT / 'tools').glob('native_runtime_*'))] if path.is_file()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'output': str(args.output)}))


if __name__ == '__main__':
    main()
