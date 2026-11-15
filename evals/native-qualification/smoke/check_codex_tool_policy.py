#!/usr/bin/env python3
"""Failure-first contract and exact readback checks for Codex tool confinement.

Cases: absent policy preserves historical profile bytes/hash; the exact enum is
accepted and unknown enum rejected; configuration can be explicit only when the
signed profile contains it; policy-file drift fails closed; exact AppArmor and
seccomp readback plus empty CapAdd are required. Real missing-profile creation,
recovery cleanup, Codex startup and joined work run in the hosted Docker workflow.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from contextlib import nullcontext

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))

from engagement_contract import ContractError, validate_environment_profile  # noqa: E402
import codex_tool_policy  # noqa: E402
from research_environment import Environment, EnvironmentUnavailable  # noqa: E402


def require(value, message):
    if not value:
        raise AssertionError(message)


def refused(call, error_type):
    try:
        call()
    except error_type:
        return
    raise AssertionError('forbidden operation was accepted')


def base_profile():
    return {'kind': 'research-environment-profile-v2', 'transport': 'docker',
        'docker_binary': '/fixture/docker', 'docker_endpoint': 'unix:///fixture/docker.sock',
        'daemon_id': 'fixture-daemon', 'image_id': 'sha256:' + '1' * 64,
        'platform': 'linux/amd64', 'uid': 1000, 'gid': 1000, 'ssh': None}


def limits():
    return {'memory_bytes': 64 * 1024 * 1024, 'cpu_count': 1, 'pids': 32,
        'workspace_bytes': 1024 * 1024, 'lease_seconds': 20, 'output_bytes': 4096}


def policy_readback(policy):
    seccomp = policy['seccomp_document']
    seccomp_value = json.dumps(seccomp, separators=(',', ':'))
    info = {'AppArmorProfile': policy['apparmor_profile'], 'HostConfig': {
        'SecurityOpt': ['no-new-privileges=true', 'apparmor=' + policy['apparmor_profile'],
                        'seccomp=' + seccomp_value], 'CapAdd': []}}
    codex_tool_policy.verify_configuration(info, policy)
    variants = []
    for change in (
        lambda value: value['HostConfig']['SecurityOpt'].append('seccomp=unconfined'),
        lambda value: value['HostConfig']['SecurityOpt'].__setitem__(1, 'apparmor=wrong'),
        lambda value: value['HostConfig']['SecurityOpt'].__setitem__(2, 'seccomp={"defaultAction":"SCMP_ACT_ALLOW"}'),
        lambda value: value['HostConfig'].__setitem__('CapAdd', ['SYS_ADMIN']),
        lambda value: value.__setitem__('AppArmorProfile', 'docker-default'),
    ):
        changed = copy.deepcopy(info)
        change(changed)
        variants.append(changed)
    for changed in variants:
        refused(lambda changed=changed: codex_tool_policy.verify_configuration(changed, policy), ValueError)


def main():
    result = {'kind': 'codex-tool-policy-check-v1',
              'classification': 'local_contract_and_policy_readback',
              'status': 'failed', 'checks': []}

    def check(name, call):
        call()
        result['checks'].append({'name': name, 'passed': True})

    try:
        legacy = base_profile()
        check('no-policy profile remains valid', lambda: validate_environment_profile(legacy))
        legacy_digest = Environment._digest(legacy)
        require(legacy_digest == 'sha256:a01e76b3bd06f9e4546537d93628eb3b6df5f45af4897a285099a49220122b50',
                'historical no-policy profile hash changed')
        signed = {**legacy, 'codex_tool_policy': 'docker-confined-v1'}
        check('fixed Codex policy enum is accepted while optional',
              lambda: validate_environment_profile(signed))
        check('unknown policy enum is rejected', lambda: refused(lambda: validate_environment_profile(
            {**legacy, 'codex_tool_policy': 'unconfined'}), ContractError))
        check('policy remains dormant without explicit tool-environment activation',
              lambda: Environment(signed, limits(), lambda: {'seconds_remaining': 20}, lambda _: None,
                                  dispatch_guard=nullcontext, codex_tool_policy=False))
        check('explicit activation requires a signed policy enum', lambda: refused(lambda: Environment(
            legacy, limits(), lambda: {'seconds_remaining': 20}, lambda _: None,
            dispatch_guard=nullcontext, codex_tool_policy=True), EnvironmentUnavailable))

        policy = codex_tool_policy.load_policy()
        require(policy['apparmor_profile'] == 'oslit-codex-tool-v1'
                and isinstance(policy['seccomp'], bytes)
                and json.loads(policy['seccomp']) == policy['seccomp_document'],
                'pinned policy inputs are incomplete')
        check('exact policy readback is enforced', lambda: policy_readback(policy))
        for filename, attribute in (('seccomp.json', 'SECCOMP_FILE'),
                                    ('apparmor', 'APPARMOR_FILE')):
            original = getattr(codex_tool_policy, attribute)
            try:
                with tempfile.TemporaryDirectory(prefix='codex-policy-drift-') as temporary:
                    changed = Path(temporary) / filename
                    changed.write_bytes(original.read_bytes() + b' ')
                    setattr(codex_tool_policy, attribute, changed)
                    check(filename + ' digest drift fails closed',
                          lambda: refused(codex_tool_policy.load_policy, ContractError))
            finally:
                setattr(codex_tool_policy, attribute, original)
        result['status'] = 'passed'
    except Exception as error:
        result['error'] = type(error).__name__ + ': ' + str(error)
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
