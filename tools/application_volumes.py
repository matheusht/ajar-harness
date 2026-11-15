"""Exact, bounded Docker state copies owned by one application generation."""
from __future__ import annotations

import json
import re

from research_environment import EnvironmentUnavailable


def validate(specs, limits=None):
    if not isinstance(specs, list) or not 1 <= len(specs) <= 8:
        raise EnvironmentUnavailable('application_state_volumes_invalid')
    paths = []
    for row in specs:
        if (not isinstance(row, dict) or set(row) != {'path', 'bytes'} or
                not isinstance(row['path'], str) or not re.fullmatch(r'/state/[A-Za-z0-9][A-Za-z0-9_-]{0,63}', row['path']) or
                type(row['bytes']) is not int or not 4096 <= row['bytes'] <= 10**12 or row['bytes'] % 4096):
            raise EnvironmentUnavailable('application_state_volumes_invalid')
        paths.append(row['path'])
    if len(paths) != len(set(paths)) or (limits is not None and sum(row['bytes'] for row in specs) >= limits['workspace_bytes']):
        raise EnvironmentUnavailable('application_state_volumes_invalid')


def identities(nonce, specs):
    return [dict(row, name=f'oslit-{nonce}-state-{index}', created_at=None) for index, row in enumerate(specs)]


def validate_identity(value, specs, limits):
    validate(specs, limits)
    actual = value.get('state_volumes')
    expected = identities(value['nonce'], specs)
    if not isinstance(actual, list) or len(actual) != len(expected):
        raise EnvironmentUnavailable('application_volume_identity_mismatch')
    for row, wanted in zip(actual, expected):
        if (not isinstance(row, dict) or set(row) != set(wanted) or
                any(row[key] != wanted[key] for key in ('name', 'path', 'bytes')) or
                row['created_at'] is not None and (not isinstance(row['created_at'], str) or not 1 <= len(row['created_at']) <= 64)):
            raise EnvironmentUnavailable('application_volume_identity_mismatch')


def unsettled_valid(value):
    allowed = {'create_stage', 'snapshot_input', 'create'} | {
        f'create_state_volume.{index}' for index in range(len(value.get('state_volumes', [])))}
    return isinstance(value['unsettled'], list) and all(isinstance(key, str) and key in allowed for key in value['unsettled'])


def options(env, row):
    return {'type': 'tmpfs', 'device': 'tmpfs',
            'o': f"size={row['bytes']},uid={env.profile['uid']},gid={env.profile['gid']},mode=0700,nosuid,nodev,noexec"}


def labels(env, row):
    return {'io.oslit.engagement': env.identity['nonce'], 'io.oslit.profile': env.identity['profile_sha256'],
            'io.oslit.state.path': row['path'], 'io.oslit.state.bytes': str(row['bytes'])}


def inspect(env, index, *, absent_ok=False):
    row = env.identity['state_volumes'][index]
    pending = f'create_state_volume.{index}'
    env._daemon()
    result = env._run(['volume', 'inspect', row['name']])
    if result['status'] != 'settled':
        raise EnvironmentUnavailable('application_volume_readback_unavailable')
    if result['returncode']:
        listed = env._run(['volume', 'ls', '--format', '{{.Name}}', '--filter', 'name=^' + row['name'] + '$'])
        if absent_ok and listed['status'] == 'settled' and listed['returncode'] == 0 and not listed['output'].strip():
            if pending in env.identity['unsettled']:
                raise EnvironmentUnavailable('application_volume_creation_unsettled')
            return None
        raise EnvironmentUnavailable('application_volume_readback_unavailable')
    try:
        info, = json.loads(result['output'])
        if (info['Name'] != row['name'] or info['Driver'] != 'local' or info['Scope'] != 'local' or
                info.get('Options') != options(env, row) or info.get('Labels') != labels(env, row) or
                not isinstance(info.get('CreatedAt'), str) or not 1 <= len(info['CreatedAt']) <= 64 or
                row['created_at'] is not None and row['created_at'] != info['CreatedAt']):
            raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise EnvironmentUnavailable('application_volume_identity_mismatch') from None
    if pending in env.identity['unsettled']:
        env.identity['unsettled'].remove(pending)
    row['created_at'] = info['CreatedAt']
    return info


def create(env):
    for index, row in enumerate(env.identity.get('state_volumes', [])):
        if inspect(env, index, absent_ok=True) is not None:
            raise EnvironmentUnavailable('application_volume_already_exists')
        args = ['volume', 'create', '--driver', 'local']
        for key, value in labels(env, row).items():
            args.extend(['--label', key + '=' + value])
        for key, value in options(env, row).items():
            args.extend(['--opt', key + '=' + value])
        args.append(row['name'])
        result = env._effect('create_state_volume', args, uncertain_key=f'create_state_volume.{index}')
        if result['status'] != 'settled' or result['returncode']:
            raise EnvironmentUnavailable('application_volume_create_unknown')
        inspect(env, index)


def cleanup(env):
    for index, row in enumerate(env.identity.get('state_volumes', [])):
        if inspect(env, index, absent_ok=True) is not None:
            result = env._effect('remove_state_volume', ['volume', 'rm', row['name']], cleanup=True)
            if result['status'] != 'settled' or result['returncode']:
                raise EnvironmentUnavailable('application_volume_cleanup_unobserved')
        if inspect(env, index, absent_ok=True) is not None:
            raise EnvironmentUnavailable('application_volume_cleanup_unobserved')


def verify_mounts(env, info, *, stage=False):
    expected = [] if stage else env.identity.get('state_volumes', [])
    actual = info.get('Mounts') or []
    configured = info['HostConfig'].get('Mounts') or []
    if len(actual) != len(expected) or len(configured) != len(expected):
        raise ValueError('state_mount_count')
    for row in expected:
        mount = next((item for item in actual if item.get('Destination') == row['path']), {})
        config = next((item for item in configured if item.get('Target') == row['path']), {})
        if (mount.get('Type') != 'volume' or mount.get('Name') != row['name'] or
                mount.get('Driver') != 'local' or mount.get('RW') is not True or
                config.get('Type') != 'volume' or config.get('Source') != row['name'] or
                config.get('ReadOnly', False) is not False or config.get('BindOptions') or
                config.get('TmpfsOptions') or config.get('VolumeOptions', {}).get('Subpath') or
                config.get('VolumeOptions', {}).get('NoCopy') is not True):
            raise ValueError('state_mount_identity')
