#!/usr/bin/env python3
"""Run a fixed harmless bwrap probe under two digest-pinned Docker policies.

This test-only route loads a unique AppArmor policy on the local disposable Linux
CI host. It does not qualify the native runtime or change production settings.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import struct
import sys

ROOT = Path(__file__).resolve().parents[3]
POLICY_DIR = ROOT / 'evals/native-qualification/fixtures/codex-tool-policy-v1'
APPARMOR_FILE = POLICY_DIR / 'oslit-codex-tool-v1.apparmor'
SECCOMP_FILE = POLICY_DIR / 'oslit-codex-tool-v1.seccomp.json'
APPARMOR_PROFILE = 'oslit-codex-tool-v1'
APPARMOR_SHA256 = '416fa88e0a55d80ba102e7d7ba4205281dff504e9021e66d21bae9c7feb4960f'
SECCOMP_SHA256 = 'ce43ad043604a1d352bb505633df3087630716dfb9af894841faadef6021275a'
BWRAP_SHA256 = 'sha256:77360cb751ccedc5971391444ac86a8a33c15b04d6b4a6fe45f5d25496e62c4c'
APPARMOR_PROFILE_PATH = Path('/sys/kernel/security/apparmor/profiles')
TIMEOUT = 30

import check_codex_sandbox_policy_diagnostic as diagnostic  # noqa: E402
from engagement_contract import ContractError, canonical, safe_publication  # noqa: E402

BASE_VERIFY_CONTAINER = diagnostic._verify_container


class CandidateFailure(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


# This check runs before bwrap. It attempts a valid tmpfs mount in the outer
# container's /tmp, then removes the directory. In the candidate it must fail
# with EPERM while CapEff is zero. The following stock probe separately checks
# that the single intended NEWUSER syscall is admitted.
OUTER_MOUNT_PROBE = r'''import ctypes,errno,json,os,tempfile
libc=ctypes.CDLL(None,use_errno=True)
path=tempfile.mkdtemp(prefix='oslit-outer-mount-',dir='/tmp')
rc=libc.mount(b'tmpfs',os.fsencode(path),b'tmpfs',2|4,None)
if rc==0:
 cleanup=libc.umount2(os.fsencode(path),2)==0
 status='allowed'
 code=0
else:
 code=ctypes.get_errno(); cleanup=True
 status='denied'
os.rmdir(path)
try:
 capeff=next(x.split(':',1)[1].strip() for x in open('/proc/self/status') if x.startswith('CapEff:'))
except Exception: capeff='unavailable'
print('OSLIT_OUTER_MOUNT='+json.dumps({'status':status,'errno':code,'errno_name':errno.errorcode.get(code,'NONE'),'cleanup':cleanup,'cap_eff':capeff},sort_keys=True,separators=(',',':')))
'''


def _digest(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise CandidateFailure('policy_file_unavailable')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _profile_mode(contents: str, name: str) -> str | None:
    for line in contents.splitlines():
        if line.startswith(name + ' (') and line.endswith(')'):
            return line[len(name) + 2:-1]
    return None


def _profile_present(contents: str, name: str) -> bool:
    return _profile_mode(contents, name) is not None


def _loaded_profile(contents: str, name: str) -> bool:
    return _profile_mode(contents, name) == 'enforce'


def _read_loaded_profiles() -> str:
    sudo = shutil.which('sudo')
    if sudo is None:
        raise CandidateFailure('apparmor_profile_readback_unavailable')
    try:
        result = diagnostic._command(sudo, None, '-n', '/usr/bin/cat',
                                     str(APPARMOR_PROFILE_PATH), direct=True, timeout=TIMEOUT)
        if result.returncode != 0 or len(result.stdout) >= diagnostic.MAX_COMMAND_OUTPUT:
            raise CandidateFailure('apparmor_profile_readback_unavailable')
        return result.stdout.decode('utf-8', 'strict')
    except (OSError, UnicodeDecodeError, diagnostic.DiagnosticFailure):
        raise CandidateFailure('apparmor_profile_readback_unavailable') from None


def _daemon_profile(endpoint: str) -> str:
    if not endpoint.startswith('unix:///'):
        raise CandidateFailure('docker_endpoint_not_local_unix')
    path = endpoint[len('unix://'):]
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.settimeout(2)
        client.connect(path)
        credentials = client.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i'))
        pid, _, _ = struct.unpack('3i', credentials)
    except OSError:
        raise CandidateFailure('docker_daemon_identity_unavailable') from None
    finally:
        client.close()
    try:
        return Path(f'/proc/{pid}/attr/current').read_text().strip()
    except OSError:
        raise CandidateFailure('docker_daemon_apparmor_unavailable') from None


def _parse_mount_result(output: str) -> dict:
    rows = [line.removeprefix('OSLIT_OUTER_MOUNT=') for line in output.splitlines()
            if line.startswith('OSLIT_OUTER_MOUNT=')]
    if len(rows) != 1:
        raise CandidateFailure('outer_mount_result_invalid')
    try:
        row = json.loads(rows[0])
    except (ValueError, TypeError):
        raise CandidateFailure('outer_mount_result_invalid') from None
    if (type(row) is not dict or row.get('status') not in ('allowed', 'denied')
            or type(row.get('errno')) is not int or type(row.get('cleanup')) is not bool
            or not isinstance(row.get('cap_eff'), str)):
        raise CandidateFailure('outer_mount_result_invalid')
    return {key: row[key] for key in ('status', 'errno', 'errno_name', 'cleanup', 'cap_eff')}


def _self_check() -> dict:
    assert _digest(APPARMOR_FILE) == APPARMOR_SHA256
    assert _digest(SECCOMP_FILE) == SECCOMP_SHA256
    profile = json.loads(SECCOMP_FILE.read_text())
    candidate = [row for row in profile['syscalls']
                 if row.get('comment', '').startswith('Codex bwrap v1:')]
    assert len(candidate) == 3
    clone, unshare, mounts = candidate
    assert clone['names'] == ['clone']
    assert clone['args'] == [{'index': 0, 'value': 0x7e020000,
                              'valueTwo': 0x78020000, 'op': 'SCMP_CMP_MASKED_EQ'}]
    assert unshare['names'] == ['unshare']
    assert unshare['args'] == [{'index': 0, 'value': 0x10000000, 'op': 'SCMP_CMP_EQ'}]
    assert mounts['names'] == ['mount', 'umount2', 'pivot_root']
    assert not _profile_present('docker-default (enforce)\n', APPARMOR_PROFILE)
    assert _profile_present(APPARMOR_PROFILE + ' (complain)\n', APPARMOR_PROFILE)
    assert not _loaded_profile(APPARMOR_PROFILE + ' (complain)\n', APPARMOR_PROFILE)
    assert _loaded_profile(APPARMOR_PROFILE + ' (enforce)\n', APPARMOR_PROFILE)
    assert _parse_mount_result('OSLIT_OUTER_MOUNT={"status":"denied","errno":1,"errno_name":"EPERM","cleanup":true,"cap_eff":"0000000000000000"}') == {
        'status': 'denied', 'errno': 1, 'errno_name': 'EPERM',
        'cleanup': True, 'cap_eff': '0000000000000000'}
    image_id = 'sha256:' + 'a' * 64
    run_id = 'b' * 32
    options = ('seccomp=' + str(SECCOMP_FILE), 'apparmor=' + APPARMOR_PROFILE)
    inspection = {'Image': image_id,
        'Name': '/oslit-codex-policy-' + run_id[:12] + '-candidate',
        'AppArmorProfile': APPARMOR_PROFILE,
        'Config': {'User': '1000:1000', 'Labels': {
            diagnostic.LABEL + '.run': run_id,
            diagnostic.LABEL + '.scenario': 'candidate'}},
        'HostConfig': {'NetworkMode': 'none', 'ReadonlyRootfs': True,
            'CapDrop': ['ALL'], 'CapAdd': [], 'Privileged': False,
            'Memory': 268435456, 'MemorySwap': 268435456,
            'NanoCpus': 1000000000, 'PidsLimit': 32,
            'SecurityOpt': ['no-new-privileges:true',
                'apparmor=' + APPARMOR_PROFILE,
                'seccomp=' + json.dumps(profile, separators=(',', ':'))],
            'Binds': [], 'PortBindings': {}},
        'Mounts': [{'Type': 'tmpfs', 'Destination': '/tmp'}]}
    original_verify = diagnostic._verify_container
    try:
        diagnostic._verify_container = _candidate_verify_container
        diagnostic._verify_container(inspection, run_id, 'candidate', image_id, options)
        mismatched = {**inspection, 'HostConfig': {**inspection['HostConfig'],
            'SecurityOpt': [*inspection['HostConfig']['SecurityOpt'][:-1],
                            'seccomp=' + json.dumps({'defaultAction': 'SCMP_ACT_ALLOW'})]}}
        try:
            diagnostic._verify_container(mismatched, run_id, 'candidate', image_id, options)
        except diagnostic.DiagnosticFailure as error:
            assert error.code == 'seccomp_readback_mismatch'
        else:
            raise AssertionError('different serialized seccomp policy accepted')
    finally:
        diagnostic._verify_container = original_verify
    assert _profile_cleanup_action(False, False, 'not_attempted', False, None) == 'not_loaded'
    assert _profile_cleanup_action(True, False, 'absent', False, None) == 'verified'
    assert _profile_cleanup_action(True, False, 'unavailable', False, None) == 'unresolved'
    assert _profile_cleanup_action(True, True, 'unavailable', False, None) == 'remove_owned_profile'
    assert _profile_cleanup_action(True, True, 'enforce', True, None) == 'retained_for_unresolved_container_cleanup'
    assert _profile_cleanup_action(True, True, 'enforce', True,
                                   {'container_cleanup': 'verified'}) == 'remove_owned_profile'
    return {'status': 'passed', 'docker_contact': False, 'profile_load': False,
            'candidate_profile_rules': 3, 'seccomp_readback': 'structural_match',
            'load_recovery': 'passed', 'qualification': False}


def _parser_command(sudo: str, parser: str, action: str, path: Path):
    return diagnostic._command(sudo, None, '-n', parser, action, str(path), direct=True,
                               timeout=TIMEOUT)


def _candidate_verify_container(container, run_id, name, image_id, security_options):
    config = container.get('HostConfig') or {}
    observed = config.get('SecurityOpt') or []
    if type(observed) is not list or any(type(value) is not str for value in observed):
        raise diagnostic.DiagnosticFailure('container_policy_invalid')
    no_new_privileges = [value for value in observed if value in (
        'no-new-privileges', 'no-new-privileges=true', 'no-new-privileges:true')]
    apparmor = [value for value in observed if value.startswith('apparmor=')]
    seccomp = [value for value in observed if value.startswith('seccomp=')]
    if (len(no_new_privileges) != 1 or len(apparmor) != 1 or len(seccomp) != 1
            or len(observed) != 3 or apparmor[0] != 'apparmor=' + APPARMOR_PROFILE):
        raise diagnostic.DiagnosticFailure('container_policy_invalid')
    seccomp_value = seccomp[0][len('seccomp='):]
    expected_path = str(SECCOMP_FILE)
    if seccomp_value != expected_path:
        try:
            serialized = json.loads(seccomp_value)
        except (ValueError, TypeError):
            raise diagnostic.DiagnosticFailure('seccomp_readback_mismatch') from None
        if serialized != json.loads(SECCOMP_FILE.read_text()):
            raise diagnostic.DiagnosticFailure('seccomp_readback_mismatch')
    normalized = {'no-new-privileges=true', *security_options}
    adjusted = {**container, 'HostConfig': {**config,
        'SecurityOpt': list(normalized)}}
    BASE_VERIFY_CONTAINER(adjusted, run_id, name, image_id,
                          ('seccomp=' + expected_path, 'apparmor=' + APPARMOR_PROFILE))
    if container.get('AppArmorProfile') != APPARMOR_PROFILE:
        raise diagnostic.DiagnosticFailure('apparmor_runtime_profile_mismatch')


def _profile_cleanup_action(load_attempted: bool, load_succeeded: bool,
                            load_readback: str, scenario_started: bool,
                            row: dict | None) -> str:
    if not load_attempted:
        return 'not_loaded'
    if not load_succeeded:
        return 'verified' if load_readback == 'absent' else 'unresolved'
    if scenario_started and (row is None or row.get('container_cleanup') != 'verified'):
        return 'retained_for_unresolved_container_cleanup'
    return 'remove_owned_profile'


def _write_output(path: Path, report: dict) -> None:
    data = canonical(report)
    try:
        safe_publication(data)
    except ContractError:
        data = canonical({'kind': report['kind'], 'classification': 'diagnostic_only',
                          'qualification': False, 'status': 'failed',
                          'error': 'candidate_output_redacted'})
    if (not path.is_absolute() or path.exists() or path.is_symlink()
            or path.parent.resolve() != path.parent):
        raise CandidateFailure('output_path_invalid')
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(data + b'\n')


def run_candidate(docker: str, endpoint: str, image_id: str, bwrap_sha256: str,
                  allow_host_policy_load: bool, parser: str) -> dict:
    run_id = diagnostic.uuid.uuid4().hex
    report = {'kind': 'codex-sandbox-policy-candidate-v1',
              'classification': 'diagnostic_only', 'qualification': False,
              'status': 'failed', 'run_id': run_id, 'cleanup': 'not_started',
              'candidate_profiles': {'apparmor_name': APPARMOR_PROFILE,
                  'apparmor_sha256': 'sha256:' + APPARMOR_SHA256,
                  'seccomp_sha256': 'sha256:' + SECCOMP_SHA256},
              'bwrap_sha256': BWRAP_SHA256,
              'common_policy': {'cap_drop': ['ALL'], 'no_new_privileges': True,
                  'network': 'none', 'host_bind_mounts': 0, 'readonly_root': True,
                  'memory_bytes': 268435456, 'memory_swap_bytes': 268435456,
                  'cpu_count': 1, 'pids_limit': 32,
                  'tmpfs': ['/tmp:rw,noexec,nosuid,nodev,size=16777216']}}
    if not allow_host_policy_load:
        report['error'] = 'explicit_host_policy_load_flag_required'
        return report
    if not sys.platform.startswith('linux'):
        report['error'] = 'candidate_host_not_linux'
        return report
    if (not Path(docker).is_absolute() or Path(docker).name != 'docker'
            or not re.fullmatch(r'sha256:[0-9a-f]{64}', image_id)
            or bwrap_sha256 != BWRAP_SHA256):
        report['error'] = 'candidate_input_invalid'
        return report
    if _digest(APPARMOR_FILE) != APPARMOR_SHA256 or _digest(SECCOMP_FILE) != SECCOMP_SHA256:
        report['error'] = 'candidate_policy_digest_mismatch'
        return report
    try:
        json.loads(SECCOMP_FILE.read_text())
        if _daemon_profile(endpoint) != 'unconfined':
            report['error'] = 'docker_daemon_apparmor_mismatch'
            return report
        diagnostic._image_check(docker, endpoint, image_id)
        profiles = _read_loaded_profiles()
        if _profile_present(profiles, APPARMOR_PROFILE):
            report['error'] = 'candidate_profile_name_already_loaded'
            return report
    except (CandidateFailure, diagnostic.DiagnosticFailure) as error:
        report['error'] = getattr(error, 'code', 'candidate_preflight_failed')
        return report
    sudo = shutil.which('sudo')
    if sudo is None or not Path(parser).is_absolute() or Path(parser).name != 'apparmor_parser':
        report['error'] = 'apparmor_loader_unavailable'
        return report

    load_attempted = False
    load_succeeded = False
    load_readback = 'not_attempted'
    profile_cleanup = 'not_started'
    scenario_started = False
    row = None
    try:
        load_attempted = True
        try:
            loaded = _parser_command(sudo, parser, '-Ka', APPARMOR_FILE)
        except diagnostic.DiagnosticFailure:
            load_readback = 'unavailable'
            report['error'] = 'apparmor_load_result_uncertain'
            return report
        load_succeeded = loaded.returncode == 0
        if not load_succeeded:
            report['error'] = 'apparmor_load_failed'
            report['loader_output'] = diagnostic._text(loaded.stderr + loaded.stdout)
            try:
                profiles = _read_loaded_profiles()
                load_readback = ('absent' if not _profile_present(profiles, APPARMOR_PROFILE)
                    else 'present_' + str(_profile_mode(profiles, APPARMOR_PROFILE)))
            except CandidateFailure:
                load_readback = 'unavailable'
            return report
        load_readback = 'enforce' if _loaded_profile(
            _read_loaded_profiles(), APPARMOR_PROFILE) else 'not_enforcing'
        if load_readback != 'enforce':
            report['error'] = 'apparmor_load_readback_missing'
            return report

        options = ('seccomp=' + str(SECCOMP_FILE), 'apparmor=' + APPARMOR_PROFILE)
        prior_probe = diagnostic.UNSHARE_PROBE
        prior_verify = diagnostic._verify_container
        diagnostic.UNSHARE_PROBE = OUTER_MOUNT_PROBE + '\n' + prior_probe
        diagnostic._verify_container = _candidate_verify_container
        audit_window_started = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        scenario_started = True
        try:
            row = diagnostic._run_one(docker, endpoint, image_id, run_id, 'candidate',
                                      options, BWRAP_SHA256)
        finally:
            diagnostic.UNSHARE_PROBE = prior_probe
            diagnostic._verify_container = prior_verify
        report['scenario'] = row
        outer_mount = _parse_mount_result(row.get('bwrap', {}).get('stdout', ''))
        report['outside_namespace_mount'] = outer_mount
        report['outside_namespace_mount_denied'] = (
            outer_mount.get('status') == 'denied' and outer_mount.get('errno') == 1
            and outer_mount.get('cap_eff') == '0000000000000000' and outer_mount.get('cleanup'))
        report['apparmor_runtime_name_matches'] = row.get('apparmor_profile') == APPARMOR_PROFILE
        bwrap_ok = (row.get('status') == 'observed'
                    and row.get('bwrap', {}).get('status') == 'exit:0'
                    and row.get('unshare', {}).get('status') == 'allowed')
        success = (bwrap_ok and report['outside_namespace_mount_denied']
                   and report['apparmor_runtime_name_matches']
                   and row.get('container_cleanup') == 'verified')
        report['status'] = 'observed' if success else 'failed'
        report['candidate_replay'] = 'passed' if success else 'failed'
        report['host_kernel_denials'] = diagnostic._kernel_denial_snapshot(
            audit_window_started)
        # The path is needed for Docker's create/readback comparison but is not
        # part of the published receipt; the fixed policy digest is recorded above.
        row['security_options'] = ['seccomp=sha256:' + SECCOMP_SHA256,
                                   'apparmor=' + APPARMOR_PROFILE]
        return report
    except (CandidateFailure, diagnostic.DiagnosticFailure) as error:
        report['error'] = getattr(error, 'code', 'candidate_run_failed')
        return report
    finally:
        action = _profile_cleanup_action(load_attempted, load_succeeded, load_readback,
                                         scenario_started, row)
        if action == 'remove_owned_profile':
            try:
                removed = _parser_command(sudo, parser, '-R', APPARMOR_FILE)
                if removed.returncode != 0:
                    profile_cleanup = 'unresolved'
                else:
                    profile_cleanup = 'verified' if not _profile_present(
                        _read_loaded_profiles(), APPARMOR_PROFILE) else 'unresolved'
            except (CandidateFailure, diagnostic.DiagnosticFailure):
                profile_cleanup = 'unresolved'
        elif action == 'retained_for_unresolved_container_cleanup':
            profile_cleanup = action
        elif action == 'unresolved':
            profile_cleanup = action
        else:
            profile_cleanup = action
        report['profile_load_attempted'] = load_attempted
        report['profile_load_succeeded'] = load_succeeded
        report['profile_load_readback'] = load_readback
        report['profile_cleanup'] = profile_cleanup
        report['cleanup'] = ('verified' if (profile_cleanup == 'verified'
                             or (not load_attempted and profile_cleanup == 'not_loaded'))
                             and (row is None or row.get('container_cleanup') == 'verified')
                             else 'unresolved')
        if report['cleanup'] != 'verified':
            report['status'] = 'failed'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-check', action='store_true')
    parser.add_argument('--allow-host-policy-load', action='store_true')
    parser.add_argument('--docker')
    parser.add_argument('--endpoint')
    parser.add_argument('--image-id')
    parser.add_argument('--bwrap-sha256', default=BWRAP_SHA256)
    parser.add_argument('--apparmor-parser', default='/usr/sbin/apparmor_parser')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.self_check:
        print(json.dumps(_self_check(), sort_keys=True))
        return 0
    if not all((args.docker, args.endpoint, args.image_id, args.output)):
        parser.error('candidate replay requires --allow-host-policy-load, --docker, --endpoint, --image-id, and --output')
    report = run_candidate(args.docker, args.endpoint, args.image_id, args.bwrap_sha256,
                           args.allow_host_policy_load, args.apparmor_parser)
    try:
        _write_output(args.output, report)
    except CandidateFailure as error:
        print(json.dumps({'status': 'failed', 'error': error.code, 'output_written': False}))
        return 1
    print(json.dumps({'status': report['status'], 'cleanup': report.get('cleanup'),
                      'output_written': True}, sort_keys=True))
    return 0 if report['status'] == 'observed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
