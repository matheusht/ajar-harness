#!/usr/bin/env python3
"""Compare Docker seccomp and AppArmor effects on fixed, harmless Codex sandbox probes.

This is diagnostic evidence only. It never qualifies native execution or changes production policy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shlex
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))

from engagement_contract import ContractError, canonical, safe_publication  # noqa: E402

LABEL = 'io.oslit.codex-sandbox-diagnostic'
IMAGE_ID_RE = re.compile(r'sha256:[0-9a-f]{64}\Z')
SHA_RE = re.compile(r'(?:sha256:)?[0-9a-f]{64}\Z')
MAX_OUTPUT = 2048
MAX_COMMAND_OUTPUT = 65536
TIMEOUT = 25

SCENARIOS = (
    ('default', ()),
    ('seccomp_unconfined', ('seccomp=unconfined',)),
    ('apparmor_unconfined', ('apparmor=unconfined',)),
    ('both_unconfined', ('seccomp=unconfined', 'apparmor=unconfined')),
)

UNSHARE_PROBE = r'''import ctypes, errno, json, pathlib
libc=ctypes.CDLL(None,use_errno=True)
if libc.unshare(0x10000000)==0:
 r={'status':'allowed'}
else:
 code=ctypes.get_errno(); r={'status':'denied','errno':code,'errno_name':errno.errorcode.get(code,'UNKNOWN')}
try:
 status=pathlib.Path('/proc/self/status').read_text()
 r['seccomp']=next(x.split(':',1)[1].strip() for x in status.splitlines() if x.startswith('Seccomp:'))
except Exception: r['seccomp']='unavailable'
try: r['apparmor_profile']=pathlib.Path('/proc/self/attr/current').read_text().strip()[:96]
except Exception: r['apparmor_profile']='unavailable'
print('OSLIT_USERNS='+json.dumps(r,sort_keys=True,separators=(',',':')))
'''

BWRAP_COMMAND = (
    '/runtime/codex-resources/bwrap', '--die-with-parent', '--unshare-user',
    '--unshare-pid', '--unshare-net', '--uid', '1000', '--gid', '1000',
    '--ro-bind', '/', '/', '--proc', '/proc', '--dev', '/dev', '--', '/bin/true',
)


class DiagnosticFailure(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _text(raw: bytes) -> str:
    value = raw[:MAX_OUTPUT].decode('utf-8', 'replace')
    value = ''.join(c if c in '\n\t' or 32 <= ord(c) < 127 or ord(c) >= 160 else ' ' for c in value)
    value = re.sub(r'(?i)(?:/home|/users|/private|/var/folders)/[^\s:]+', '[path]', value)
    value = re.sub(r'\b[0-9a-f]{32,64}\b', '[id]', value)
    return value.strip()


def _command(docker, endpoint, *args, timeout=TIMEOUT):
    command = [docker, '--host', endpoint, *args]
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   bufsize=0)
    except OSError:
        raise DiagnosticFailure('docker_unavailable') from None
    selector = selectors.DefaultSelector()
    buffers = {}
    for stream in (process.stdout, process.stderr):
        os.set_blocking(stream.fileno(), False)
        selector.register(stream, selectors.EVENT_READ)
        buffers[stream] = bytearray()
    deadline = time.monotonic() + timeout
    timed_out = False
    while selector.get_map():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            if timed_out:
                break
            timed_out = True
            process.kill()
            deadline = time.monotonic() + 2
        ready = selector.select(max(0, min(remaining, .2)))
        if not ready and timed_out and time.monotonic() >= deadline:
            break
        for key, _ in ready:
            stream = key.fileobj
            try:
                chunk = os.read(stream.fileno(), 8192)
            except BlockingIOError:
                continue
            if not chunk:
                selector.unregister(stream)
                stream.close()
                continue
            buffer = buffers[stream]
            if len(buffer) < MAX_COMMAND_OUTPUT:
                buffer.extend(chunk[:MAX_COMMAND_OUTPUT - len(buffer)])
    if timed_out:
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        selector.close()
        for stream in (process.stdout, process.stderr):
            if not stream.closed:
                stream.close()
        raise DiagnosticFailure('docker_timeout')
    selector.close()
    return subprocess.CompletedProcess(command, process.wait(),
        bytes(buffers.get(process.stdout, b'')), bytes(buffers.get(process.stderr, b'')))


def _inspect(docker, endpoint, kind, identity):
    response = _command(docker, endpoint, 'inspect', '--type', kind, identity)
    if response.returncode != 0:
        message = _text(response.stderr + response.stdout).lower()
        if re.search(r'\bno such (?:object|container|image):', message):
            return None
        raise DiagnosticFailure('docker_inspect_failed')
    try:
        value = json.loads(response.stdout)
        if type(value) is not list or len(value) != 1 or type(value[0]) is not dict:
            raise ValueError
        return value[0]
    except (ValueError, TypeError):
        raise DiagnosticFailure('docker_inspect_invalid') from None


def _userns_result(output: bytes):
    rows = [line[len(b'OSLIT_USERNS='):] for line in output.splitlines()
            if line.startswith(b'OSLIT_USERNS=')]
    if len(rows) != 1:
        return {'status': 'invalid_output'}
    try:
        value = json.loads(rows[0])
    except (ValueError, TypeError):
        return {'status': 'invalid_output'}
    if type(value) is not dict or value.get('status') not in ('allowed', 'denied'):
        return {'status': 'invalid_output'}
    return {key: value[key] for key in ('status', 'errno', 'errno_name', 'seccomp', 'apparmor_profile')
            if key in value and type(value[key]) in (str, int)}


def verified_bwrap_asset(path, expected_sha256):
    """Return the expected digest only when the staged helper file matches it exactly."""
    if not isinstance(expected_sha256, str) or not SHA_RE.fullmatch(expected_sha256):
        return None
    target = Path(path)
    try:
        if target.is_symlink() or not target.is_file() or not target.stat().st_mode & 0o111:
            return None
        observed = 'sha256:' + hashlib.sha256(target.read_bytes()).hexdigest()
    except OSError:
        return None
    expected = expected_sha256 if expected_sha256.startswith('sha256:') else 'sha256:' + expected_sha256
    return expected if observed == expected else None


def _image_check(docker, endpoint, image_id):
    if not IMAGE_ID_RE.fullmatch(image_id):
        raise DiagnosticFailure('image_id_invalid')
    image = _inspect(docker, endpoint, 'image', image_id)
    if image is None or image.get('Id') != image_id or image.get('Os') != 'linux':
        raise DiagnosticFailure('image_identity_invalid')
    config = image.get('Config') or {}
    if any(config.get(key) for key in ('Entrypoint', 'Volumes', 'Healthcheck', 'OnBuild', 'ExposedPorts')):
        raise DiagnosticFailure('image_defaults_invalid')
    return image


def _scenario_command(docker, endpoint, image_id, run_id, name, security_options):
    container_name = 'oslit-codex-policy-' + run_id[:12] + '-' + name
    shell_script = (
        'python3 -c ' + shlex.quote(UNSHARE_PROBE) + '\n'
        + shlex.join(BWRAP_COMMAND) + '\n'
        + 'rc=$?; printf "OSLIT_BWRAP_STATUS=exit:%s\\n" "$rc"; exit 0'
    )
    args = ['container', 'create', '--name', container_name,
            '--label', LABEL + '.run=' + run_id, '--label', LABEL + '.scenario=' + name,
            '--network', 'none', '--read-only', '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges=true',
            '--user', '1000:1000',
            '--memory', '268435456', '--memory-swap', '268435456', '--cpus', '1',
            '--pids-limit', '32', '--tmpfs', '/tmp:rw,noexec,nosuid,nodev,size=16777216']
    for option in security_options:
        args.extend(['--security-opt', option])
    args.extend(['--entrypoint', '/bin/sh', image_id, '-c', shell_script])
    return container_name, args


def _owned_container(container, run_id, name, image_id):
    labels = (container.get('Config') or {}).get('Labels') or {}
    return (container.get('Image') == image_id
            and container.get('Name') == '/oslit-codex-policy-' + run_id[:12] + '-' + name
            and labels.get(LABEL + '.run') == run_id
            and labels.get(LABEL + '.scenario') == name)


def _verify_container(container, run_id, name, image_id, security_options):
    if not _owned_container(container, run_id, name, image_id):
        raise DiagnosticFailure('container_identity_invalid')
    config = container.get('HostConfig') or {}
    expected = {'no-new-privileges=true', *security_options}
    observed = set()
    for value in config.get('SecurityOpt') or ():
        observed.add('no-new-privileges=true' if value in (
            'no-new-privileges', 'no-new-privileges=true', 'no-new-privileges:true') else value)
    mounts = container.get('Mounts') or []
    if (config.get('NetworkMode') != 'none' or config.get('ReadonlyRootfs') is not True
            or config.get('CapDrop') != ['ALL'] or config.get('CapAdd')
            or config.get('Privileged') is not False
            or (container.get('Config') or {}).get('User') != '1000:1000'
            or config.get('Memory') != 268435456
            or config.get('MemorySwap') != 268435456 or config.get('NanoCpus') != 1000000000
            or config.get('PidsLimit') != 32 or observed != expected
            or config.get('Binds') or config.get('PortBindings')
            or any(row.get('Type') == 'bind' for row in mounts)
            or any(row.get('Type') != 'tmpfs' or row.get('Destination') != '/tmp' for row in mounts)):
        raise DiagnosticFailure('container_policy_invalid')
    if container.get('AppArmorProfile') is not None and type(container.get('AppArmorProfile')) is not str:
        raise DiagnosticFailure('apparmor_observation_invalid')


def _run_one(docker, endpoint, image_id, run_id, name, security_options, bwrap_sha256):
    row = {'scenario': name, 'security_options': list(security_options),
           'classification': 'diagnostic_only', 'qualification': False,
           'bwrap_sha256': bwrap_sha256, 'container_cleanup': 'pending'}
    container_name, create_args = _scenario_command(
        docker, endpoint, image_id, run_id, name, security_options)
    container_id = None
    created = False
    try:
        created_result = _command(docker, endpoint, *create_args)
        if created_result.returncode != 0:
            row.update(status='create_failed', error='container_create_failed',
                       stderr=_text(created_result.stderr))
            return row
        container_id = created_result.stdout.decode('ascii', 'ignore').strip()
        if not re.fullmatch(r'[0-9a-f]{12,64}', container_id):
            row.update(status='create_failed', error='container_id_invalid')
            return row
        created = True
        container = _inspect(docker, endpoint, 'container', container_id)
        if container is None:
            row.update(status='setup_failed', error='created_container_missing')
            return row
        _verify_container(container, run_id, name, image_id, security_options)
        row['apparmor_profile'] = _text(str(container.get('AppArmorProfile', 'unavailable')).encode())
        started = _command(docker, endpoint, 'container', 'start', '--attach', container_id)
        output = started.stdout
        unshare = _userns_result(output)
        status_rows = [line.decode('ascii', 'replace') for line in output.splitlines()
                       if line.startswith(b'OSLIT_BWRAP_STATUS=')]
        bwrap_code = status_rows[0].partition('=')[2] if len(status_rows) == 1 else 'missing'
        row.update(status='observed' if started.returncode == 0 and unshare['status'] != 'invalid_output'
                   and re.fullmatch(r'exit:[0-9]{1,3}', bwrap_code) else 'probe_failed',
                   unshare=unshare,
                   bwrap={'status': bwrap_code, 'container_exit': started.returncode,
                          'stdout': _text(output), 'stderr': _text(started.stderr)})
        final = _inspect(docker, endpoint, 'container', container_id)
        if final is not None and _owned_container(final, run_id, name, image_id):
            state = final.get('State') or {}
            row['container_exit'] = state.get('ExitCode') if type(state.get('ExitCode')) is int else None
        return row
    except DiagnosticFailure as error:
        row.update(status='setup_failed', error=error.code)
        return row
    finally:
        if not created:
            # A failed create must not leave a partially created same-name object behind.
            try:
                found = _inspect(docker, endpoint, 'container', container_name)
                if found is None:
                    row['container_cleanup'] = 'verified'
                elif _owned_container(found, run_id, name, image_id):
                    container_id = found.get('Id')
                    created = True
                else:
                    row['container_cleanup'] = 'unresolved'
                    row['cleanup_error'] = 'name_taken_by_unowned_container'
            except DiagnosticFailure as error:
                row['container_cleanup'] = 'unresolved'
                row['cleanup_error'] = error.code
        if created and container_id:
            try:
                current = _inspect(docker, endpoint, 'container', container_id)
                if current is not None:
                    if not _owned_container(current, run_id, name, image_id):
                        raise DiagnosticFailure('cleanup_ownership_mismatch')
                    removed = _command(docker, endpoint, 'container', 'rm', '--force', container_id)
                    if removed.returncode != 0:
                        raise DiagnosticFailure('container_remove_failed')
                if _inspect(docker, endpoint, 'container', container_id) is not None:
                    raise DiagnosticFailure('container_still_present')
                row['container_cleanup'] = 'verified'
            except DiagnosticFailure as error:
                row['container_cleanup'] = 'unresolved'
                row['cleanup_error'] = error.code


def run_diagnostic(docker: str, endpoint: str, image_id: str, bwrap_sha256: str) -> dict:
    """Run four fixed probes on the verified image and clean up only labeled containers."""
    run_id = uuid.uuid4().hex
    helper_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result = {'kind': 'codex-sandbox-policy-diagnostic-v1',
              'classification': 'diagnostic_only', 'qualification': False,
              'status': 'failed', 'run_id': run_id,
              'helper_sha256': 'sha256:' + helper_sha256,
              'image_id': image_id, 'bwrap_sha256': bwrap_sha256,
              'common_policy': {'cap_drop': ['ALL'], 'no_new_privileges': True,
                  'network': 'none', 'host_bind_mounts': 0, 'readonly_root': True,
                  'memory_bytes': 268435456, 'memory_swap_bytes': 268435456,
                  'cpu_count': 1, 'pids_limit': 32,
                  'tmpfs': ['/tmp:rw,noexec,nosuid,nodev,size=16777216']},
              'scenarios': []}
    if not SHA_RE.fullmatch(bwrap_sha256):
        result.update(error='bwrap_digest_invalid', cleanup='not_started')
        return result
    if not isinstance(docker, str) or not Path(docker).is_absolute() or Path(docker).name != 'docker':
        result.update(error='docker_path_invalid', cleanup='not_started')
        return result
    if not isinstance(endpoint, str) or not endpoint.startswith('unix:///') or any(
            character in endpoint for character in ('\x00', '\n', '\r')):
        result.update(error='docker_endpoint_invalid', cleanup='not_started')
        return result
    if not sys.platform.startswith('linux'):
        result.update(error='diagnostic_host_not_linux', cleanup='not_started')
        return result
    normalized_sha = bwrap_sha256 if bwrap_sha256.startswith('sha256:') else 'sha256:' + bwrap_sha256
    result['bwrap_sha256'] = normalized_sha
    try:
        _image_check(docker, endpoint, image_id)
    except DiagnosticFailure as error:
        result.update(error=error.code, cleanup='not_started')
        return result
    for name, options in SCENARIOS:
        try:
            row = _run_one(docker, endpoint, image_id, run_id, name, options, normalized_sha)
        except Exception:
            row = {'scenario': name, 'status': 'failed', 'error': 'diagnostic_internal_error',
                   'classification': 'diagnostic_only', 'qualification': False,
                   'container_cleanup': 'unresolved'}
        result['scenarios'].append(row)
    clean = all(row.get('container_cleanup') == 'verified' for row in result['scenarios'])
    result['cleanup'] = 'verified' if clean else 'unresolved'
    matrix = len(result['scenarios']) == len(SCENARIOS) and all(
        row.get('status') == 'observed' for row in result['scenarios'])
    result['matrix'] = 'complete' if matrix else 'partial'
    result['status'] = 'observed' if matrix and clean else 'failed'
    return result


def _self_check():
    assert len(SCENARIOS) == 4 and len({name for name, _ in SCENARIOS}) == 4
    assert [options for _, options in SCENARIOS] == [(), ('seccomp=unconfined',),
        ('apparmor=unconfined',), ('seccomp=unconfined', 'apparmor=unconfined')]
    for name, options in SCENARIOS:
        args = _scenario_command('docker', 'unix:///fixture', 'sha256:' + 'a' * 64,
                                 'b' * 32, name, options)[1]
        assert args[args.index('--cap-drop') + 1] == 'ALL'
        assert args[args.index('--network') + 1] == 'none'
        assert args[args.index('--read-only') + 0] == '--read-only'
        assert args[args.index('--user') + 1] == '1000:1000'
        assert args[args.index('--pids-limit') + 1] == '32'
        assert '--mount' not in args and '-v' not in args and '--privileged' not in args
        assert '/runtime/codex-resources/bwrap' in args[-1]
        assert '/bin/true' in args[-1]
        inspection = {'Image': 'sha256:' + 'a' * 64,
            'Name': '/oslit-codex-policy-' + 'b' * 12 + '-' + name,
            'Config': {'User': '1000:1000', 'Labels': {
                LABEL + '.run': 'b' * 32, LABEL + '.scenario': name}},
            'HostConfig': {'NetworkMode': 'none', 'ReadonlyRootfs': True,
                'CapDrop': ['ALL'], 'CapAdd': [], 'Privileged': False,
                'Memory': 268435456, 'MemorySwap': 268435456, 'NanoCpus': 1000000000,
                'PidsLimit': 32, 'SecurityOpt': ['no-new-privileges:true', *options],
                'Binds': [], 'PortBindings': {}},
            'Mounts': [{'Type': 'tmpfs', 'Destination': '/tmp'}],
            'AppArmorProfile': 'docker-default'}
        _verify_container(inspection, 'b' * 32, name, 'sha256:' + 'a' * 64, options)
        with_extra_capability = {**inspection, 'HostConfig': {
            **inspection['HostConfig'], 'CapAdd': ['SYS_ADMIN']}}
        try:
            _verify_container(with_extra_capability, 'b' * 32, name,
                              'sha256:' + 'a' * 64, options)
        except DiagnosticFailure as error:
            assert error.code == 'container_policy_invalid'
        else:
            raise AssertionError('additional capability accepted')
        with_extra_security = {**inspection, 'HostConfig': {
            **inspection['HostConfig'], 'SecurityOpt': ['no-new-privileges=true', *options,
                                                        'apparmor=unconfined']}}
        if 'apparmor=unconfined' not in options:
            try:
                _verify_container(with_extra_security, 'b' * 32, name,
                                  'sha256:' + 'a' * 64, options)
            except DiagnosticFailure as error:
                assert error.code == 'container_policy_invalid'
            else:
                raise AssertionError('unexpected security option accepted')
    assert _userns_result(b'OSLIT_USERNS={"status":"denied","errno":1,"errno_name":"EPERM"}\n') == {
        'status': 'denied', 'errno': 1, 'errno_name': 'EPERM'}
    assert run_diagnostic('unused', 'unused', 'sha256:' + 'a' * 64, 'wrong')['error'] == 'bwrap_digest_invalid'
    assert run_diagnostic('docker', 'tcp://example.invalid:2375',
                          'sha256:' + 'a' * 64, 'a' * 64)['error'] == 'docker_path_invalid'
    assert run_diagnostic('/usr/bin/docker', 'tcp://example.invalid:2375',
                          'sha256:' + 'a' * 64, 'a' * 64)['error'] == 'docker_endpoint_invalid'
    with tempfile.TemporaryDirectory(prefix='codex-bwrap-selfcheck-') as temporary:
        helper = Path(temporary) / 'bwrap'
        helper.write_bytes(b'pinned harmless fixture helper')
        helper.chmod(0o555)
        digest_value = 'sha256:' + hashlib.sha256(helper.read_bytes()).hexdigest()
        assert verified_bwrap_asset(helper, digest_value) == digest_value
        assert verified_bwrap_asset(helper, 'sha256:' + '0' * 64) is None
        assert verified_bwrap_asset(helper, 'invalid') is None
    return {'status': 'passed', 'scenarios': 4, 'docker_contact': False,
            'asset_hash_path': 'passed', 'qualification': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-check', action='store_true')
    parser.add_argument('--docker')
    parser.add_argument('--endpoint')
    parser.add_argument('--image-id')
    parser.add_argument('--bwrap-sha256')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.self_check:
        print(json.dumps(_self_check(), sort_keys=True))
        return 0
    if not all((args.docker, args.endpoint, args.image_id, args.bwrap_sha256, args.output)):
        parser.error('diagnostic requires --docker, --endpoint, --image-id, --bwrap-sha256, and --output')
    report = run_diagnostic(args.docker, args.endpoint, args.image_id, args.bwrap_sha256)
    data = canonical(report)
    try:
        safe_publication(data)
    except ContractError:
        data = canonical({'kind': report['kind'], 'classification': 'diagnostic_only',
                          'qualification': False, 'status': 'failed',
                          'error': 'diagnostic_output_redacted'})
    destination = args.output
    if (not destination.is_absolute() or destination.exists() or destination.is_symlink()
            or destination.parent.resolve() != destination.parent):
        parser.error('--output must be a new absolute path in a canonical directory')
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(data + b'\n')
    print(json.dumps({'status': report['status'], 'cleanup': report.get('cleanup', 'not_started'),
                      'output_written': True}, sort_keys=True))
    return 0 if report['status'] == 'observed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
