#!/usr/bin/env python3
"""Inspect signed v2 inputs and local prerequisites without runtime/target contact."""
from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
import shutil
import sys
import tomllib

from engagement_contract import ContractError, digest, load_inputs, read_bytes, safe_publication
from engagement_controller import overlap
from native_credentials import HostCredentialResolver
from native_runtime_transport import RuntimeError
from research_environment import inspect_profile

METHODOLOGY = Path(__file__).resolve().parents[1] / 'engine/native-engagement-method.md'
PROTOCOL = Path(__file__).resolve().parents[1] / 'engine/native-engagement-protocol.md'
SOCKET_PARENT = Path('/tmp')


def inspect_engagement(inputs: Path) -> dict:
    verified = load_inputs(Path(inputs))
    blocked = set()
    host_missing = []
    if sys.platform != 'darwin':
        host_missing.append('native_model_boundary_unsupported')
    elif not os.access('/usr/bin/sandbox-exec', os.X_OK):
        host_missing.append('native_model_sandbox_unavailable')
    if not shutil.which('openssl'):
        host_missing.append('native_proxy_certificate_tool_unavailable')
    if not SOCKET_PARENT.is_dir() or not os.access(SOCKET_PARENT, os.W_OK | os.X_OK):
        host_missing.append('native_private_socket_directory_unavailable')
    guidance = {}
    for name, path, code in (('methodology', METHODOLOGY, 'native_methodology_unavailable'),
                             ('protocol', PROTOCOL, 'native_protocol_guidance_unavailable')):
        try:
            guidance[name] = digest(safe_publication(read_bytes(path, max_bytes=1024 * 1024)))
        except (ContractError, OSError):
            guidance[name] = None
            host_missing.append(code)
    if any(profile['kind'] == 'codex' for profile in verified.runtime_profiles.values()) and not shutil.which('bun'):
        host_missing.append('native_executor_bridge_unavailable')
    blocked.update(host_missing)
    environments = {}
    for identity, profile in verified.environment_profiles.items():
        observation = inspect_profile(profile)
        blocked.update(observation['missing'])
        environments[identity] = {'transport': profile['transport'], 'platform': profile['platform'], **observation}
    if not verified.scope['network']['provider']:
        blocked.add('provider_route_unavailable')
    account_access = [row['id'] for row in verified.scope['access']
                      if row['kind'] == 'application' and row['account_refs']]
    accounts = {'status': 'not_requested', 'access_ids': account_access, 'target_identity_verified': False}
    if account_access:
        from target_accounts import TargetAccountError, TargetAccountResolver
        target_resolver = None
        try:
            reference = os.environ.get('OSLIT_ACCOUNT_BINDINGS') or None
            if reference is not None:
                reference = Path(reference)
                try:
                    if not reference.is_absolute():raise ValueError()
                    resolved = reference.resolve(strict=True)
                except (OSError, ValueError):
                    raise TargetAccountError('target_account_references_unavailable') from None
                protected = [Path(value) for value in verified.inputs['access_files'].values()]
                protected.extend(Path(profile['tool_bundle']['path']) for profile in verified.runtime_profiles.values())
                if any(overlap(resolved, path.resolve()) for path in protected):
                    raise TargetAccountError('target_account_references_exposed')
            target_resolver = TargetAccountResolver(reference,
                verified.scope, lambda: {'resources': account_access}, lambda observation: None,
                environment_profile_id=next(iter(verified.environment_profiles)))
            accounts['status'] = 'references_available'
        except TargetAccountError as error:
            accounts.update(status='blocked', code=str(error))
            blocked.add(str(error))
        finally:
            if target_resolver is not None:target_resolver.close()
    initial_kinds = {row['kind'] for row in verified.scope['access'] if row['kind'] != 'application'}
    initial_resources = {row['id'] for row in verified.scope['access'] if row['kind'] != 'application'}
    resolver = HostCredentialResolver()
    runtimes = {}
    for identity, profile in verified.runtime_profiles.items():
        missing = []
        adapter = importlib.import_module('native_runtime_' + profile['kind'])
        if profile['version'] != adapter.Runtime.version:
            missing.append('native_runtime_version_unsupported')
        if not os.access(profile['executable']['path'], os.X_OK):
            missing.append('native_runtime_not_executable')
        if profile['kind'] == 'codex' and 'usage_cost_estimate' in profile['required_capabilities']:
            missing.append('native_required_capability_unavailable')
        if profile['kind'] == 'codex':
            try:
                adapter.validate_native_config(tomllib.loads(
                    verified.frozen_files['runtimes/' + identity + '.config'].decode('utf-8')))
            except RuntimeError as error:
                missing.append(str(error))
            except (ValueError, UnicodeError):
                missing.append('native_configuration_invalid')
        bundle = {'status': 'unavailable', 'execution_verified': False}
        try:
            inspection = adapter.inspect_tool_bundle(profile, identity)
            bundle = {'status': 'packaging_verified', 'execution_verified': False,
                      'platform': profile['tool_bundle']['platform'],
                      'manifest_sha256': profile['tool_bundle']['manifest_sha256'],
                      'environment_command': inspection['command']}
        except RuntimeError as error:
            missing.append(str(error))
        candidates = [row['profile_id'] for row in verified.scope['environments']
            if verified.environment_profiles[row['profile_id']]['platform'] == profile['tool_bundle']['platform']
            and initial_kinds <= set(row['capabilities'])
            and sum(row['profile_id'] in effect['environment_ids'] and not effect['account_refs']
                    and effect['kind'] == 'read' and initial_resources <= set(effect['access_ids'])
                    for effect in verified.scope['effects']) == 1]
        if not candidates:
            missing.append('native_environment_assignment_unavailable')
        binding = None
        credential = {'reference': profile['credential_ref'], 'status': 'unavailable', 'provider_validity': 'unverified'}
        try:
            binding = resolver(profile)
            binding.check()
            credential['status'] = 'reference_available' if profile['credential_ref'] is not None else 'not_requested'
        except RuntimeError as error:
            missing.append(str(error))
            credential['code'] = str(error)
        finally:
            if binding is not None:binding.revoke()
        blocked.update(missing)
        runtimes[identity] = {'kind': profile['kind'], 'declared_version': profile['version'],
            'native_version_observed': False, 'provider': profile['provider'], 'model': profile['model'],
            'status': 'blocked' if missing else 'prerequisites_present', 'missing': sorted(set(missing)),
            'credential': credential, 'tool_bundle': bundle, 'initial_environment_candidates': candidates,
            'required_capabilities': profile['required_capabilities'], 'capabilities_verified': False}
    return {'kind': 'native-engagement-preflight-v2',
        'status': 'blocked' if blocked else 'ready_for_runtime_check',
        'verified_inputs': True, 'engagement_id': verified.scope['engagement_id'],
        'scope_sha256': digest(verified.frozen_files['scope.md']), 'goal_sha256': verified.scope['goal_sha256'],
        'signer_fingerprint': verified.signer_fingerprint,
        'access_modes': sorted({row['kind'] for row in verified.scope['access']}),
        'host': {'platform': sys.platform, 'status': 'blocked' if host_missing else 'prerequisites_present',
                 'model_boundary': 'darwin-no-fork-v1' if sys.platform == 'darwin' else 'unsupported',
                 'missing': host_missing, 'methodology_sha256': guidance['methodology'],
                 'protocol_sha256': guidance['protocol'], 'execution_verified': False},
        'runtimes': runtimes, 'environments': environments, 'blocked_codes': sorted(blocked),
        'target_accounts': accounts,
        'unbound_account_access': account_access if accounts['status'] == 'blocked' else [],
        'hard_limits': verified.scope['limits']['hard'],
        'expires_at': verified.scope['expires_at'], 'runtime_and_target_contact': False,
        'capabilities_verified': False,
        'unverified': ['native_runtime_startup', 'provider_authentication_and_inference',
                       'environment_daemon_and_image', 'tool_containment_and_network_routes',
                       'cleanup', 'research_qualification']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = inspect_engagement(args.inputs)
    except ContractError as error:
        result = {'status': 'rejected', 'code': error.code}
    except (OSError, ValueError, KeyError, TypeError):
        result = {'status': 'rejected', 'code': 'engagement_preflight_input_unavailable'}
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0 if result['status'] == 'ready_for_runtime_check' else 2


if __name__ == '__main__':
    raise SystemExit(main())
