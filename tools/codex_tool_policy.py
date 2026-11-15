"""Pinned policy for an explicitly authorized Codex tool container."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from engagement_contract import ContractError, read_bytes

POLICY_DIR = Path(__file__).resolve().parents[1] / 'engine/codex-tool-policy-v1'
APPARMOR_FILE = POLICY_DIR / 'oslit-codex-tool-v1.apparmor'
SECCOMP_FILE = POLICY_DIR / 'oslit-codex-tool-v1.seccomp.json'
APPARMOR_PROFILE = 'oslit-codex-tool-v1'
APPARMOR_SHA256 = '416fa88e0a55d80ba102e7d7ba4205281dff504e9021e66d21bae9c7feb4960f'
SECCOMP_SHA256 = 'ce43ad043604a1d352bb505633df3087630716dfb9af894841faadef6021275a'


def load_policy():
    content = {}
    for name, path, expected in (('apparmor', APPARMOR_FILE, APPARMOR_SHA256),
                                 ('seccomp', SECCOMP_FILE, SECCOMP_SHA256)):
        value = read_bytes(path, max_bytes=1024 * 1024)
        if hashlib.sha256(value).hexdigest() != expected:
            raise ContractError('codex_tool_policy_changed')
        content[name] = value
    return {'seccomp': content['seccomp'], 'seccomp_document': json.loads(content['seccomp']),
            'apparmor_profile': APPARMOR_PROFILE}


def verify_configuration(info, policy):
    host = info['HostConfig']
    options = host['SecurityOpt']
    if type(options) is not list or any(type(value) is not str for value in options):
        raise ValueError('codex_tool_policy')
    nnp = [value for value in options if value in (
        'no-new-privileges', 'no-new-privileges=true', 'no-new-privileges:true')]
    apparmor = [value for value in options if value.startswith('apparmor=')]
    seccomp = [value for value in options if value.startswith('seccomp=')]
    if (len(options) != 3 or len(nnp) != 1 or len(seccomp) != 1
            or apparmor != ['apparmor=' + policy['apparmor_profile']]
            or host.get('CapAdd') not in (None, [])
            or info.get('AppArmorProfile') != policy['apparmor_profile']
            or json.loads(seccomp[0][len('seccomp='):]) != policy['seccomp_document']):
        raise ValueError('codex_tool_policy')
