#!/usr/bin/env python3
"""Add and safely remove the reviewed Codex AppArmor profile on a disposable CI host."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_codex_sandbox_policy_candidate as candidate  # noqa: E402


def write_result(path, result):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, sort_keys=True, indent=2) + '\n')


def remove_owned_profile(marker, output):
    result = {'kind': 'codex-tool-policy-host-profile-cleanup-v1', 'status': 'failed'}
    try:
        if not marker.exists():
            result.update(status='clean', ownership='none', unload='not_attempted')
            write_result(output, result)
            return result
        ownership = json.loads(marker.read_text())
        if (ownership.get('kind') != 'codex-tool-policy-host-profile-owner-v1'
                or ownership.get('profile') != candidate.APPARMOR_PROFILE
                or ownership.get('apparmor_sha256') != candidate.APPARMOR_SHA256
                or ownership.get('attempted') is not True
                or ownership.get('absent_before_attempt') is not True):
            raise ValueError('ownership_marker_invalid')
        unresolved = []
        for name in ('startup', 'joined'):
            path = Path(ownership[name + '_result'])
            try:
                observed = json.loads(path.read_text())
            except Exception:
                observed = {}
            if (observed.get('boundary_cleanup', {}).get('cleanup') != 'verified'
                    or observed.get('image', {}).get('cleanup', {}).get('status') != 'clean'):
                unresolved.append(name)
        profiles = candidate._read_loaded_profiles()
        present = candidate._profile_present(profiles, candidate.APPARMOR_PROFILE)
        if unresolved:
            result.update(status='retained_for_unresolved_native_cleanup', unresolved=unresolved,
                          profile_present=present)
        elif not present:
            result.update(status='clean', profile_present=False, unload='not_needed')
        else:
            if not candidate._loaded_profile(profiles, candidate.APPARMOR_PROFILE):
                raise ValueError('owned_profile_not_enforcing')
            if candidate._digest(candidate.APPARMOR_FILE) != candidate.APPARMOR_SHA256:
                raise ValueError('apparmor_policy_digest_mismatch')
            sudo, parser = shutil.which('sudo'), '/usr/sbin/apparmor_parser'
            if not sudo or not Path(parser).is_file():
                raise ValueError('apparmor_unload_tool_unavailable')
            unloaded = candidate._parser_command(sudo, parser, '-R', candidate.APPARMOR_FILE)
            profiles = candidate._read_loaded_profiles()
            absent = not candidate._profile_present(profiles, candidate.APPARMOR_PROFILE)
            result.update(status='clean' if unloaded.returncode == 0 and absent else 'failed',
                          profile_present=not absent, unload='attempted')
    except Exception as error:
        result['error'] = getattr(error, 'code', None) or type(error).__name__
    write_result(output, result)
    return result


def install_profile(marker, startup_result, joined_result, output):
    result = {'kind': 'codex-tool-policy-host-profile-setup-v1', 'status': 'failed'}
    try:
        if not sys.platform.startswith('linux'):
            raise ValueError('candidate_host_not_linux')
        if candidate._digest(candidate.APPARMOR_FILE) != candidate.APPARMOR_SHA256:
            raise ValueError('apparmor_policy_digest_mismatch')
        if candidate._daemon_profile('unix:///var/run/docker.sock') != 'unconfined':
            raise ValueError('docker_daemon_apparmor_mismatch')
        sudo, parser = shutil.which('sudo'), '/usr/sbin/apparmor_parser'
        if not sudo or not Path(parser).is_file():
            raise ValueError('apparmor_loader_unavailable')
        profiles = candidate._read_loaded_profiles()
        if candidate._profile_present(profiles, candidate.APPARMOR_PROFILE):
            raise ValueError('candidate_profile_name_already_loaded')
        if marker.exists():
            raise ValueError('ownership_marker_already_exists')
        ownership = {'kind': 'codex-tool-policy-host-profile-owner-v1',
            'profile': candidate.APPARMOR_PROFILE, 'apparmor_sha256': candidate.APPARMOR_SHA256,
            'absent_before_attempt': True, 'attempted': True,
            'startup_result': str(startup_result), 'joined_result': str(joined_result)}
        marker.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(ownership, stream, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        loaded = candidate._parser_command(sudo, parser, '-Ka', candidate.APPARMOR_FILE)
        profiles = candidate._read_loaded_profiles()
        enforcing = candidate._loaded_profile(profiles, candidate.APPARMOR_PROFILE)
        result.update(status='passed' if loaded.returncode == 0 and enforcing else 'failed',
                      profile=candidate.APPARMOR_PROFILE, enforcing=enforcing,
                      loader_returncode=loaded.returncode, ownership_marker=str(marker))
    except Exception as error:
        result['error'] = getattr(error, 'code', None) or type(error).__name__
    write_result(output, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    install = sub.add_parser('install')
    install.add_argument('--marker', type=Path, required=True)
    install.add_argument('--startup-result', type=Path, required=True)
    install.add_argument('--joined-result', type=Path, required=True)
    install.add_argument('--output', type=Path, required=True)
    cleanup = sub.add_parser('cleanup')
    cleanup.add_argument('--marker', type=Path, required=True)
    cleanup.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = (install_profile(args.marker, args.startup_result, args.joined_result, args.output)
        if args.action == 'install' else remove_owned_profile(args.marker, args.output))
    print(json.dumps({'status': result['status'], 'output': str(args.output)}))
    return 0 if result['status'] == 'passed' or result['status'] == 'clean' else 1


if __name__ == '__main__':
    raise SystemExit(main())
