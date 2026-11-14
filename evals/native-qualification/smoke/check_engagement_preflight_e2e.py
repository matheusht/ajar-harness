#!/usr/bin/env python3
"""Failure-first signed-input preflight, with no model or environment dispatch.

Real SSH signatures bind disposable fixtures. Executables are sentinels, the local
Docker socket is owned and uncontacted, and all secret controls are fake. Scenarios
cover missing/mismatched credentials, scope/input mutation, bad native config,
unsupported versions/host, bundle/environment mismatch, provider routes, target
account binding and absent local/remote prerequisites. Templates remain unsigned.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))


def run(base, fixture_file):
    spec = importlib.util.spec_from_file_location('contract_fixture', fixture_file)
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    from native_runtime_codex import _DISABLED_FEATURES
    fake = 'fixture-private-preflight-marker'
    rows = []
    scenarios = ('local', 'credential-missing', 'credential-mismatch', 'scope-tampered',
        'source-mutated', 'version', 'not-executable', 'capability', 'config', 'bundle-platform', 'environment-platform',
        'docker-missing', 'ssh-prerequisites', 'ssh-missing', 'host-linux', 'provider-missing', 'target-account', 'environment-effect',
        'openssl-missing', 'methodology-missing', 'socket-parent-missing')
    for scenario in scenarios:
        root = base / scenario
        inputs = fixture.make_fixture(root)
        definitions = json.loads(inputs.read_bytes())
        scope = fixture.fixture_scope(inputs)
        profile_path = Path(definitions['runtime_profiles']['runtime-main'])
        profile = json.loads(profile_path.read_bytes())
        marker = root / 'EXECUTED'
        binary = Path(profile['executable']['path'])
        fixture.write(binary, ('#!/bin/sh\ntouch ' + str(marker) + '\nexit 91\n').encode())
        binary.chmod(0o700)
        profile['executable']['sha256'] = fixture.sha(binary.read_bytes())
        profile.update(version='0.166.0', provider='openai', model='gpt-6.1-sol', credential_ref='env_OPENAI_API_KEY')
        config = Path(profile['config_file'])
        fixture.write(config, ('model="gpt-6.1-sol"\nmodel_provider="openai"\nweb_search="disabled"\n'
            'default_permissions="oslit-worker"\n[features]\n' + ''.join(name+'=false\n' for name in _DISABLED_FEATURES) +
            '[shell_environment_policy]\ninherit="none"\n[shell_environment_policy.set]\nPATH="/usr/bin:/bin"\n'
            '[permissions.oslit-worker.filesystem]\n":root"="deny"\n":minimal"="read"\n'
            '[permissions.oslit-worker.filesystem.":workspace_roots"]\n"."="write"\n'
            '[permissions.oslit-worker.network]\nenabled=false\n').encode())
        bundle = Path(profile['tool_bundle']['path'])
        fixture.write(bundle / 'bin/codex', b'\x7fELF\x02\x01' + b'\0' * 12 + (183).to_bytes(2, 'little'))
        (bundle / 'bin/codex').chmod(0o700)
        from engagement_contract import source_manifest, canonical, digest
        profile['tool_bundle']['manifest_sha256'] = digest(canonical(source_manifest(bundle)))
        environment_path = Path(definitions['environment_profiles']['lab-main'])
        environment = json.loads(environment_path.read_bytes())
        # Keep Unix paths short on macOS.
        sock_dir = tempfile.TemporaryDirectory(prefix='oslit-pf-', dir='/tmp')
        endpoint = Path(sock_dir.name).resolve() / 'docker.sock'
        listener = socket.socket(socket.AF_UNIX)
        listener.bind(str(endpoint))
        listener.listen(1)
        listener.settimeout(.02)
        environment['docker_endpoint'] = 'unix://' + str(endpoint)
        scope['network']['provider'] = [{'protocol': 'https', 'host': 'provider.example.invalid', 'port': 443,
            'address_policy': {'public_only': True, 'cidrs': []}}]
        expected = []
        if scenario == 'credential-missing':expected = ['native_credential_unavailable']
        if scenario == 'credential-mismatch':
            profile['credential_ref'] = 'env_WRONG_KEY'
            expected = ['native_credential_provider_mismatch']
        if scenario == 'version':
            profile['version'] = '0.1.0'
            expected = ['native_runtime_version_unsupported']
        if scenario == 'not-executable':
            binary.chmod(0o600)
            expected = ['native_runtime_not_executable']
        if scenario == 'capability':
            profile['required_capabilities'].append('usage_cost_estimate')
            expected = ['native_required_capability_unavailable']
        if scenario == 'config':
            fixture.write(config, config.read_bytes().replace(b'multi_agent=false', b'multi_agent=true'))
            expected = ['native_alternate_tools_enabled']
        if scenario == 'bundle-platform':
            profile['tool_bundle']['platform'] = 'linux/amd64'
            expected = ['native_bundle_platform_mismatch']
        if scenario == 'environment-platform':
            environment['platform'] = 'linux/amd64'
            expected = ['native_environment_assignment_unavailable']
        if scenario == 'docker-missing':
            endpoint.unlink()
            expected = ['docker_endpoint_unavailable']
        if scenario in ('ssh-prerequisites', 'ssh-missing'):
            known, identity = root / 'known_hosts', root / 'identity'
            fixture.write(known, b'fixture.example.invalid ssh-ed25519 fixture-only-not-a-host-key\n')
            fixture.write(identity, b'fixture-only-not-a-private-key\n')
            environment.update(transport='ssh-docker', ssh={'host': 'fixture.example.invalid', 'port': 22,
                'user': 'fixture', 'known_hosts_file': str(known), 'known_hosts_sha256': fixture.sha(known.read_bytes()),
                'identity_file': str(identity), 'python_binary': '/usr/bin/python3'})
            if scenario == 'ssh-missing':
                identity.unlink()
                expected = ['ssh_identity_reference_unavailable']
        if scenario == 'host-linux':expected = ['native_model_boundary_unsupported']
        if scenario == 'openssl-missing':expected = ['native_proxy_certificate_tool_unavailable']
        if scenario == 'methodology-missing':expected = ['native_methodology_unavailable']
        if scenario == 'socket-parent-missing':expected = ['native_private_socket_directory_unavailable']
        if scenario == 'provider-missing':
            scope['network']['provider'] = []
            expected = ['provider_route_unavailable']
        if scenario == 'target-account':
            scope['access'].append({'id': 'app-main', 'kind': 'application',
                'identity': {'base_url': 'https://target.example.invalid', 'version': None},
                'account_refs': ['operator-account'], 'permissions': ['read']})
            scope['network']['target'] = [{'protocol': 'https', 'host': 'target.example.invalid', 'port': 443,
                'address_policy': {'public_only': True, 'cidrs': []}}]
            expected = ['target_account_binding_unavailable']
        profile['config_sha256'] = fixture.sha(config.read_bytes())
        fixture.write(profile_path, fixture.encoded(profile))
        fixture.write(environment_path, fixture.encoded(environment))
        scope['runtime_assignments'][0]['profile_sha256'] = fixture.sha(profile_path.read_bytes())
        scope['environments'][0]['profile_sha256'] = fixture.sha(environment_path.read_bytes())
        if scenario == 'environment-effect':
            definitions['environment_profiles']['lab-other'] = str(environment_path)
            scope['environments'].append({**scope['environments'][0], 'profile_id': 'lab-other'})
            scope['effects'][0]['environment_ids'] = ['lab-other']
            fixture.write(inputs, fixture.encoded(definitions))
        fixture.resign_fixture(inputs, scope)
        if scenario == 'scope-tampered':
            Path(definitions['scope_file']).write_bytes(Path(definitions['scope_file']).read_bytes() + b'changed\n')
            expected = ['scope_signature_invalid']
        if scenario == 'source-mutated':
            (Path(definitions['access_files']['source-main']) / 'main.py').write_text('changed')
            expected = ['digest_mismatch']
        method = root / 'methodology.md'
        if scenario != 'methodology-missing':fixture.write(method, b'Inspect the harmless fixture only.\n')
        code = '''
import shutil,socket,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
def denied(*a,**k):raise AssertionError('preflight contacted a network endpoint')
socket.socket.connect=denied
if sys.argv[3]=='host-linux':sys.platform='linux'
if sys.argv[3]=='openssl-missing':
 original=shutil.which
 shutil.which=lambda name:None if name=='openssl' else original(name)
import engagement_preflight as preflight
preflight.METHODOLOGY=Path(sys.argv[4])
if sys.argv[3]=='socket-parent-missing':preflight.SOCKET_PARENT=Path(sys.argv[4]).parent/'missing-directory'
script=Path(sys.argv[1])/'engagement_preflight.py'
sys.argv=[str(script),'--inputs',sys.argv[2]]
raise SystemExit(preflight.main())
'''
        env = dict(os.environ)
        env['OPENAI_API_KEY'] = '' if scenario == 'credential-missing' else fake
        try:
            result = subprocess.run([sys.executable, '-c', code, str(ROOT / 'tools'), str(inputs), scenario, str(method)],
                capture_output=True, text=True, timeout=15, env=env)
            report = json.loads(result.stdout) if result.stdout else {}
            assert fake not in result.stdout + result.stderr, 'credential value emitted'
            assert not marker.exists(), 'preflight executed supplied binary'
            try:
                connection, _ = listener.accept()
                connection.close()
                raise AssertionError('preflight contacted Docker')
            except socket.timeout:pass
            if expected:
                codes = report.get('blocked_codes', []) + ([report['code']] if report.get('code') else [])
                assert all(code in codes for code in expected), result.stdout + result.stderr
                assert result.returncode != 0
            else:
                assert result.returncode == 0 and report.get('status') == 'ready_for_runtime_check', result.stdout + result.stderr
                assert report['runtime_and_target_contact'] is False and report['capabilities_verified'] is False
                assert report['runtimes']['runtime-main']['credential']['status'] == 'reference_available'
                if scenario == 'environment-effect':
                    assert report['runtimes']['runtime-main']['initial_environment_candidates'] == ['lab-other']
            rows.append({'check': scenario, 'status': 'passed'})
        except Exception as error:
            rows.append({'check': scenario, 'status': 'failed', 'error': str(error)})
        finally:
            listener.close()
            sock_dir.cleanup()
    return {'status': 'passed' if all(row['status'] == 'passed' for row in rows) else 'failed',
        'classification': 'signed_fixture_preflight_no_runtime_or_target', 'real_credentials_used': False,
        'host_linux': 'simulated_platform_branch', 'checks': rows}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--contract-fixture', type=Path, default=Path(__file__).with_name('check_engagement_contract_e2e.py'))
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='preflight-e2e-') as root:
        result = run(Path(root).resolve(), args.contract_fixture)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'failed': [row['check'] for row in result['checks'] if row['status'] != 'passed']}))
    raise SystemExit(result['status'] != 'passed')
