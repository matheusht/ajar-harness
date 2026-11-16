#!/usr/bin/env python3
"""Exercise signed v2 external inputs without a provider or target connection."""
from __future__ import annotations

import argparse
import base64
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
NAMESPACE = 'llm-redteam-harness-native-engagement-v2'


def encoded(value) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=False) + '\n').encode()


def sha(data: bytes) -> str:
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def write(path: Path, data: bytes) -> None:
    path.write_bytes(data)
    path.chmod(0o600)


def resign_fixture(inputs_path: Path, scope: dict) -> None:
    """Sign mutated engineering input with its ephemeral fixture-only key."""
    inputs = json.loads(inputs_path.read_bytes())
    scope_path = Path(inputs['scope_file'])
    signers = Path(inputs['allowed_signers'])
    text = ('# Harmless engineering fixture\n\n'
            '- Operator allowed signers SHA256: ' + sha(signers.read_bytes()) + '\n'
            '- Signed: [x] fixture operator\n\n```native-engagement-scope-v2\n')
    write(scope_path, text.encode() + encoded(scope) + b'```\n')
    challenge = encoded({'kind': 'native-engagement-scope-challenge-v2',
                         'engagement_id': scope['engagement_id'],
                         'scope_sha256': sha(scope_path.read_bytes())})
    signed = subprocess.run(['ssh-keygen', '-Y', 'sign', '-f',
                             str(inputs_path.parent / 'operator_key'), '-n', NAMESPACE],
                            input=challenge, capture_output=True, timeout=10, check=True)
    write(Path(inputs['scope_signature']), signed.stdout)


def fixture_scope(inputs_path: Path) -> dict:
    inputs = json.loads(inputs_path.read_bytes())
    text = Path(inputs['scope_file']).read_text()
    return json.loads(re.search(r'```native-engagement-scope-v2\n(.*?)\n```',
                                text, re.S).group(1))


def make_fixture(root: Path) -> Path:
    """Return signed input path; fixture credentials stay outside engagement roots."""
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    root = root.resolve()
    source = root / 'source'
    source.mkdir(mode=0o700)
    content = b'print("harmless fixture ready")\n'
    write(source / 'main.py', content)
    manifest = {'main.py': {'sha256': sha(content), 'mode': 0o600, 'size': len(content)}}
    goal = root / 'goal.md'
    write(goal, b'Inspect the harmless fixture and retain an honest internal result.\n')
    binary = root / 'native-fixture'
    write(binary, b'#!/bin/sh\nexit 91\n')
    binary.chmod(0o700)
    bundle = root / 'native-bundle'
    (bundle / 'bin').mkdir(mode=0o700, parents=True)
    write(bundle / 'bin/codex', binary.read_bytes())
    bundle_manifest = {'bin/codex': {'sha256': sha(binary.read_bytes()),
                                   'mode': 0o600, 'size': binary.stat().st_size}}
    config = root / 'runtime-config.json'
    schema = root / 'runtime-schema.json'
    write(config, encoded({'fixture': True}))
    write(schema, encoded({'type': 'object'}))
    runtime = {'kind': 'codex', 'version': 'engineering-fixture',
               'executable': {'path': str(binary), 'sha256': sha(binary.read_bytes())},
               'protocol': {'mode': 'stdio-jsonrpc', 'schema_file': str(schema),
                            'schema_sha256': sha(schema.read_bytes())},
               'config_file': str(config), 'config_sha256': sha(config.read_bytes()),
               'provider': 'fixture', 'model': 'fixture-model', 'credential_ref': None,
               'required_capabilities': ['startup', 'fresh_session', 'native_tools'],
               'tool_bundle': {'path': str(bundle), 'manifest_sha256': sha(encoded(bundle_manifest)),
                               'platform': 'linux/arm64'}}
    runtime_file = root / 'runtime.json'
    write(runtime_file, encoded(runtime))
    environment = {'kind': 'research-environment-profile-v2', 'transport': 'docker',
                   'docker_binary': str(binary), 'docker_endpoint': 'unix:///fixture/docker.sock',
                   'daemon_id': None, 'image_id': 'sha256:' + '1' * 64,
                   'platform': 'linux/arm64',
                   'uid': 1000, 'gid': 1000, 'ssh': None}
    environment_file = root / 'environment.json'
    write(environment_file, encoded(environment))
    key = root / 'operator_key'
    subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)],
                   check=True, capture_output=True, timeout=10)
    signers = root / 'allowed_signers'
    write(signers, b'fixture-operator ' + key.with_suffix('.pub').read_bytes())
    fingerprint_text = subprocess.run(['ssh-keygen', '-lf', str(key.with_suffix('.pub')),
                                      '-E', 'sha256'], check=True, capture_output=True,
                                     timeout=10).stdout.decode().split('SHA256:')[1].split()[0]
    fingerprint = 'sha256:' + base64.b64decode(
        fingerprint_text + '=' * (-len(fingerprint_text) % 4)).hex()
    inputs = {'kind': 'native-engagement-inputs-v2', 'scope_file': str(root / 'scope.md'),
              'scope_signature': str(root / 'scope.sig'), 'allowed_signers': str(signers),
              'trusted_fingerprint': fingerprint, 'goal_file': str(goal),
              'access_files': {'source-main': str(source)},
              'runtime_profiles': {'runtime-main': str(runtime_file)},
              'environment_profiles': {'lab-main': str(environment_file)}}
    inputs_path = root / 'inputs.json'
    write(inputs_path, encoded(inputs))
    now = datetime.now(timezone.utc).replace(microsecond=0)
    scope = {'kind': 'native-engagement-scope-v2', 'engagement_id': 'contract-fixture',
             'operator_id': 'fixture-operator',
             'issued_at': (now - timedelta(days=3)).strftime('%Y-%m-%dT%H:%M:%SZ'),
             'expires_at': None, 'goal_sha256': sha(goal.read_bytes()),
             'goal_mode': 'bounded', 'patch_required': False,
             'access': [{'id': 'source-main', 'kind': 'source',
                         'identity': {'manifest_sha256': sha(encoded(manifest))},
                         'account_refs': [], 'permissions': ['read', 'execute']}],
             'environments': [{'profile_id': 'lab-main',
                               'profile_sha256': sha(environment_file.read_bytes()),
                               'capabilities': ['source', 'binary', 'application', 'renewable_lease'],
                               'limits': {'memory_bytes': 268435456, 'cpu_count': 1,
                                          'pids': 64, 'workspace_bytes': 67108864,
                                          'lease_seconds': 60, 'output_bytes': 1048576},
                               'cleanup': {'owned_resources': True, 'owned_workspace': True}}],
             'network': {'provider': [], 'acquisition': [], 'target': []},
             'effects': [{'id': 'read-source', 'kind': 'read', 'access_ids': ['source-main'],
                          'environment_ids': ['lab-main'], 'account_refs': [], 'rung': 'source_only',
                          'artifact_classes': [], 'cleanup_required': False}],
             'escalation_ceiling': 'source_only',
             'benign_objectives': ['Inspect harmless local fixture bytes.'],
             'runtime_assignments': [{'profile_id': 'runtime-main',
                                      'profile_sha256': sha(runtime_file.read_bytes()),
                                      'roles': ['lead', 'specialist', 'reviewer']}],
             'limits': {'hard': {'invocations': 10, 'worker_seconds': 3600},
                        'max_workers': 3, 'max_worker_lease_seconds': 60, 'informational': {}},
             'revocation': {'operator_stop': True, 'disconnected_worker': 'lease_expiry'}}
    resign_fixture(inputs_path, scope)
    return inputs_path


def probe(operation: str, path: Path, **options) -> tuple[int, dict]:
    code = '''
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
try:
    import engagement_contract as c
except ImportError:
    print(json.dumps({'status':'unavailable','code':'contract_module_missing'}))
    raise SystemExit(3)
op, path, options = sys.argv[2], Path(sys.argv[3]), json.loads(sys.argv[4])
try:
    if op == 'inspect':
        result = c.inspect_inputs(path)
    elif op == 'load':
        v = c.load_inputs(path, allow_expired=options.get('allow_expired', False))
        result = {'status':'verified', 'scope':v.scope, 'frozen':sorted(v.frozen_files),
                  'frozen_digests':{k:c.digest(b) for k,b in v.frozen_files.items()}}
    elif op == 'publication':
        result = {'status':'safe','digest':c.digest(c.safe_publication(path.read_bytes(),
                  known_secrets=tuple(s.encode() for s in options.get('known_secrets', []))))}
    elif op == 'read':
        result = {'status':'read','digest':c.digest(c.read_bytes(path, **options))}
    elif op == 'manifest':
        result = {'status':'manifest','manifest':c.source_manifest(path)}
    elif op == 'json':
        result = {'status':'read','value':c.read_json(path, **options)}
    elif op == 'canonical':
        result = {'status':'canonical','value':c.canonical(json.loads(path.read_bytes())).decode()}
    elif op == 'environment':
        result = {'status':'verified', 'profile':c.validate_environment_profile(c.read_json(path))}
    elif op == 'runtime':
        result = {'status':'verified', 'profile':c.validate_runtime_profile(c.read_json(path))}
    print(json.dumps(result, allow_nan=False))
except c.ContractError as error:
    print(json.dumps({'status':'refused','code':error.code}))
    raise SystemExit(2)
'''
    completed = subprocess.run([sys.executable, '-c', code, str(ROOT / 'tools'), operation,
                                str(path), json.dumps(options)], capture_output=True,
                               text=True, timeout=30,
                               env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
    try:
        result = json.loads(completed.stdout)
    except ValueError:
        result = {'status': 'invalid_response', 'stdout': completed.stdout[-2000:],
                  'stderr': completed.stderr[-2000:]}
    return completed.returncode, result


def main() -> int:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    checks = []

    def check(name, operation, path, expected=None, **options):
        code, result = probe(operation, path, **options)
        success = code == 0 if expected is None else code == 2 and result.get('code') in expected
        checks.append({'name': name, 'passed': success, 'exit_code': code, 'observed': result})
        assert success, (name, code, result)
        return result

    try:
        with tempfile.TemporaryDirectory(prefix='engagement-contract-e2e-') as temporary:
            base = Path(temporary).resolve()
            inputs_path = make_fixture(base / 'fixture')
            fixture = inputs_path.parent
            original_inputs = json.loads(inputs_path.read_bytes())
            original_scope = fixture_scope(inputs_path)
            original_files = {p: p.read_bytes() for p in fixture.rglob('*') if p.is_file()}

            def reset():
                for path, data in original_files.items():
                    if path.is_symlink():
                        path.unlink()
                    write(path, data)
                (fixture / 'native-fixture').chmod(0o700)

            def change_scope(name, change, expected):
                reset()
                scope = copy.deepcopy(original_scope)
                change(scope)
                resign_fixture(inputs_path, scope)
                check(name, 'inspect', inputs_path, expected)

            environment_probe = base / 'environment-probe.json'
            environment = json.loads((fixture / 'environment.json').read_bytes())
            write(environment_probe, encoded(dict(environment, workspace_root=str(base / 'unused-workspace'))))
            check('obsolete_workspace_root_refused', 'environment', environment_probe,
                  {'environment_profile_invalid'})
            write(environment_probe, encoded(environment))
            check('environment_requires_no_unused_host_workspace', 'environment', environment_probe)
            runtime_probe = base / 'runtime-probe.json'
            codex_profile = json.loads((fixture / 'runtime.json').read_bytes())
            missing_bundle = {key: value for key, value in codex_profile.items() if key != 'tool_bundle'}
            write(runtime_probe, encoded(missing_bundle))
            check('codex_missing_tool_bundle', 'runtime', runtime_probe, {'runtime_profile_invalid'})
            write(runtime_probe, encoded(codex_profile))
            check('codex_native_bundle_shape', 'runtime', runtime_probe)
            report = check('signed_source_no_deadline_after_three_days', 'inspect', inputs_path)
            assert report['status'] == 'verified_inputs' and report['capabilities_verified'] is False
            frozen = check('freeze_safe_contract_only', 'load', inputs_path)
            assert not any('operator_key' in name for name in frozen['frozen'])
            assert 'access/source-main.manifest.json' in frozen['frozen']

            bundle = base / 'tool-bundle'
            bundle.mkdir(mode=0o700)
            bundle_files = {'bin/bun': b'harmless non-executable bundle fixture\n',
                            'native_runtime_omp_tools.mjs': b'// fixture only\n',
                            'node_modules/@oh-my-pi/pi-coding-agent/package.json':
                                encoded({'name': '@oh-my-pi/pi-coding-agent', 'version': '18.20.0'})}
            for name, data in bundle_files.items():
                path = bundle / name
                path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                write(path, data)
            bundle_manifest = {name: {'sha256': sha(data), 'mode': 0o600, 'size': len(data)}
                               for name, data in sorted(bundle_files.items())}
            omp = json.loads((fixture / 'runtime.json').read_bytes())
            omp.update(kind='omp', version='18.20.0')
            omp['protocol']['mode'] = 'stdio-jsonl'
            omp.pop('tool_bundle')

            def check_runtime(name, profile, expected=None, operation='inspect'):
                reset()
                write(fixture / 'runtime.json', encoded(profile))
                scope = copy.deepcopy(original_scope)
                scope['runtime_assignments'][0]['profile_sha256'] = sha((fixture / 'runtime.json').read_bytes())
                resign_fixture(inputs_path, scope)
                return check(name, operation, inputs_path, expected)

            check_runtime('omp_missing_tool_bundle', omp, {'runtime_profile_invalid'})
            omp['tool_bundle'] = {'path': str(bundle), 'manifest_sha256': sha(encoded(bundle_manifest)),
                                  'platform': 'linux/arm64', 'bun_version': '1.4.4'}
            bundle_report = check_runtime('omp_pinned_tool_bundle', omp, operation='load')
            assert bundle_report['frozen_digests']['runtimes/runtime-main.bundle-manifest.json'] == sha(encoded(bundle_manifest))
            assert set(original_inputs['access_files']) == {'source-main'}
            for name, update in (
                    ('omp_bundle_unknown_field', {'entrypoint': 'arbitrary.js'}),
                    ('omp_bundle_platform_invalid', {'platform': 'darwin/arm64'}),
                    ('omp_bundle_version_invalid', {'bun_version': 'latest'}),
                    ('omp_bundle_path_relative', {'path': 'relative/tools'}),
                    ('omp_bundle_digest_invalid', {'manifest_sha256': 'not-a-digest'})):
                changed = copy.deepcopy(omp)
                changed['tool_bundle'].update(update)
                check_runtime(name, changed, {'runtime_profile_invalid', 'path_invalid'})
            changed = copy.deepcopy(omp)
            changed['tool_bundle'] = None
            check_runtime('omp_bundle_null', changed, {'runtime_profile_invalid'})
            codex = json.loads(original_files[fixture / 'runtime.json'])
            codex['tool_bundle'] = omp['tool_bundle']
            check_runtime('codex_cannot_claim_omp_tool_bundle', codex, {'runtime_profile_invalid'})
            bun = bundle / 'bin/bun'
            write(bun, b'changed bundle bytes\n')
            check_runtime('omp_bundle_tamper', omp, {'digest_mismatch'})
            write(bun, bundle_files['bin/bun'])
            bun.chmod(0o700)
            check_runtime('omp_bundle_mode_tamper', omp, {'digest_mismatch'})
            bun.chmod(0o600)
            bun.unlink()
            bun.symlink_to(fixture / 'native-fixture')
            check_runtime('omp_bundle_symlink', omp, {'path_invalid', 'file_unavailable', 'source_invalid'})
            bun.unlink()
            write(bun, bundle_files['bin/bun'])
            reset()

            environment = json.loads((fixture / 'environment.json').read_bytes())
            known_hosts = fixture / 'known_hosts'
            write(known_hosts, b'lab.example.test ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFixture\n')
            credential = fixture / 'ssh-credential-reference'
            os.mkfifo(credential)
            environment.update(transport='ssh-docker', ssh={
                'host': 'lab.example.test', 'port': 22, 'user': 'researcher',
                'known_hosts_file': str(known_hosts), 'known_hosts_sha256': sha(known_hosts.read_bytes()),
                'identity_file': str(credential), 'python_binary': '/usr/bin/python3'})
            write(fixture / 'environment.json', encoded(environment))
            scope = copy.deepcopy(original_scope)
            scope['environments'][0]['profile_sha256'] = sha((fixture / 'environment.json').read_bytes())
            resign_fixture(inputs_path, scope)
            remote = check('ssh_credential_reference_is_never_read', 'load', inputs_path)
            assert not any('credential' in name for name in remote['frozen'])
            write(known_hosts, b'changed host key\n')
            check('ssh_host_key_pin_changed', 'inspect', inputs_path, {'digest_mismatch'})
            credential.unlink()
            known_hosts.unlink()

            for mode in ('binary', 'application', 'combined'):
                reset()
                scope = copy.deepcopy(original_scope)
                inputs = copy.deepcopy(original_inputs)
                access = [] if mode != 'combined' else scope['access']
                files = {} if mode != 'combined' else inputs['access_files']
                if mode in ('binary', 'combined'):
                    access.append({'id': 'binary-main', 'kind': 'binary',
                                   'identity': {'sha256': sha((fixture / 'native-fixture').read_bytes()),
                                                'platform': 'linux/arm64'},
                                   'account_refs': [], 'permissions': ['read', 'execute']})
                    files['binary-main'] = str(fixture / 'native-fixture')
                if mode in ('application', 'combined'):
                    access.append({'id': 'app-main', 'kind': 'application',
                                   'identity': {'base_url': 'http://127.0.0.1:43199', 'version': None},
                                   'account_refs': ['low-privilege'], 'permissions': ['read']})
                    scope['network']['target'] = [{'protocol': 'http', 'host': '127.0.0.1',
                                                  'port': 43199, 'address_policy': {
                                                      'public_only': False, 'cidrs': ['127.0.0.1/32']}}]
                scope['access'] = access
                scope['effects'][0]['access_ids'] = [row['id'] for row in access]
                inputs['access_files'] = files
                write(inputs_path, encoded(inputs))
                resign_fixture(inputs_path, scope)
                check('signed_' + mode + '_without_source_prerequisite', 'inspect', inputs_path)

            reset()
            changed = copy.deepcopy(original_inputs)
            changed['kind'] = 'native-engagement-inputs-v1'
            write(inputs_path, encoded(changed))
            check('v1_is_not_reinterpreted', 'inspect', inputs_path, {'inputs_kind_invalid'})
            reset()
            changed = copy.deepcopy(original_inputs)
            changed['trusted_fingerprint'] = 'sha256:' + '0' * 64
            write(inputs_path, encoded(changed))
            check('wrong_trusted_signer', 'inspect', inputs_path, {'scope_signer_untrusted'})
            reset()
            write(fixture / 'scope.md', (fixture / 'scope.md').read_bytes() + b'changed\n')
            check('scope_tamper', 'inspect', inputs_path, {'scope_signature_invalid'})
            reset()
            write(fixture / 'scope.sig', b'not a signature\n')
            check('wrong_signature', 'inspect', inputs_path, {'scope_signature_invalid'})
            for name in ('goal.md', 'runtime.json', 'runtime-config.json', 'runtime-schema.json',
                         'environment.json', 'native-fixture', 'source/main.py'):
                reset()
                target = fixture / name
                write(target, target.read_bytes() + b'changed\n')
                check('tamper_' + name, 'inspect', inputs_path,
                      {'digest_mismatch', 'json_invalid', 'runtime_profile_invalid',
                       'environment_profile_invalid'})

            change_scope('expiry', lambda s: s.update(expires_at=s['issued_at']), {'scope_time_invalid'})
            change_scope('expired', lambda s: s.update(expires_at=(datetime.now(timezone.utc) -
                         timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ')), {'scope_expired'})
            check('expired_cleanup_read', 'load', inputs_path, allow_expired=True)
            change_scope('future_issue', lambda s: s.update(issued_at=(datetime.now(timezone.utc) +
                         timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ')), {'scope_not_yet_valid'})
            change_scope('unsupported_hard_cost', lambda s: s['limits']['hard'].update(cost=1),
                         {'hard_limit_unsupported'})
            change_scope('boolean_limit', lambda s: s['limits']['hard'].update(invocations=True),
                         {'scope_limits_invalid'})
            change_scope('nan_limit', lambda s: s['limits']['hard'].update(worker_seconds=float('nan')),
                         {'json_nonfinite'})
            change_scope('unknown_scope_field', lambda s: s.update(free_access=True), {'scope_invalid'})
            change_scope('unknown_role', lambda s: s['runtime_assignments'][0]['roles'].append('operator'),
                         {'scope_runtime_invalid'})
            change_scope('unknown_effect_resource', lambda s: s['effects'][0]['access_ids'].append('outside'),
                         {'scope_effect_invalid'})
            change_scope('duplicate_access_id', lambda s: s['access'].append(copy.deepcopy(s['access'][0])),
                         {'scope_access_invalid'})
            change_scope('network_wildcard', lambda s: s['network']['acquisition'].append({
                'protocol': 'https', 'host': '*.example.test', 'port': 443,
                'address_policy': {'public_only': True, 'cidrs': []}}), {'scope_network_invalid'})
            change_scope('effect_above_ceiling', lambda s: s['effects'][0].update(rung='cross_user'),
                         {'scope_effect_invalid'})

            reset()
            write(inputs_path, b'{"kind":"one","kind":"two"}\n')
            check('duplicate_json_key', 'inspect', inputs_path, {'duplicate_json_key'})
            write(inputs_path, b'x' * (1024 * 1024 + 1))
            check('oversize_input', 'inspect', inputs_path, {'file_oversize'})
            reset()
            (fixture / 'goal.md').chmod(0o644)
            check('private_input_mode', 'inspect', inputs_path, {'file_not_private'})
            reset()
            alias = base / 'alias'
            alias.symlink_to(fixture, target_is_directory=True)
            check('ancestor_symlink', 'inspect', alias / 'inputs.json', {'path_invalid'})
            alias.unlink()
            check('double_slash_alias', 'inspect', Path('/' + str(inputs_path)), {'path_invalid'})
            alias.symlink_to(inputs_path)
            check('leaf_symlink', 'inspect', alias, {'path_invalid'})
            alias.unlink()
            os.link(inputs_path, alias)
            check('private_hardlink_alias', 'inspect', alias, {'file_not_private'})
            alias.unlink()
            outside = base / 'outside'
            write(outside, b'outside\n')
            (fixture / 'source/link').symlink_to(outside)
            check('source_symlink_escape', 'inspect', inputs_path, {'path_invalid', 'source_invalid'})
            (fixture / 'source/link').unlink()
            os.mkfifo(fixture / 'source/fifo')
            check('source_special_file', 'inspect', inputs_path, {'source_invalid', 'file_not_regular'})
            (fixture / 'source/fifo').unlink()
            (fixture / 'fifo').unlink(missing_ok=True)
            os.mkfifo(fixture / 'fifo')
            check('fifo_read_does_not_block', 'read', fixture / 'fifo', {'file_not_regular'})
            (fixture / 'fifo').unlink()

            race = base / 'source-race'
            race.mkdir()
            write(race / 'a.txt', b'before\n')
            with (race / 'b.bin').open('wb') as stream:
                stream.truncate(256 * 1024 * 1024)
            race_code = '''
import json,sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import engagement_contract as c
print('ready',flush=True)
try:
    m=c.source_manifest(Path(sys.argv[2]))
    result={'status':'read','sha256':m['a.txt']['sha256']}
except c.ContractError as error:
    result={'status':'refused','code':error.code}
result['finished_ns']=time.monotonic_ns()
print(json.dumps(result),flush=True)
'''
            process = subprocess.Popen([sys.executable, '-c', race_code, str(ROOT / 'tools'), str(race)],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            assert process.stdout.readline().strip() == 'ready'
            time.sleep(0.01)
            mutation_ns = time.monotonic_ns()
            write(race / 'a.txt', b'after\n')
            stdout, stderr = process.communicate(timeout=30)
            observed = json.loads(stdout)
            overlapping = observed['finished_ns'] > mutation_ns
            success = overlapping and (observed.get('code') == 'file_changed' or
                                       observed.get('sha256') == sha(b'after\n'))
            checks.append({'name': 'source_changed_during_inventory', 'passed': success,
                           'exit_code': process.returncode, 'observed': observed,
                           'mutation_overlapped_scan': overlapping})
            assert success, ('source_changed_during_inventory', observed, stderr)

            publication = base / 'publication'
            schema = {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                      '$defs': {'InputUiRequest': {'properties': {'secret': {'type': 'boolean'}}}}}
            write(publication, encoded(schema))
            check('public_schema_secret_boolean_declaration', 'publication', publication)
            check('schema_known_secret_still_refused', 'publication', publication, {'publication_secret'},
                  known_secrets=['InputUiRequest'])
            unsafe_schema = copy.deepcopy(schema)
            unsafe_schema['$defs']['InputUiRequest']['properties']['secret']['default'] = 'harmless12345678'
            write(publication, encoded(unsafe_schema))
            check('schema_secret_default_refused', 'publication', publication, {'publication_secret'})
            write(publication, encoded({'properties': {'secret': {'type': 'boolean'}}}))
            check('non_schema_secret_declaration_refused', 'publication', publication, {'publication_secret'})
            write(publication, encoded({'secret': 'harmless12345678'}))
            check('json_secret_value_refused', 'publication', publication, {'publication_secret'})
            sentinels = [b'Authorization: ' + b' '.join((b'Bearer', b'harmless12345678')), b'Cookie: auth=harmless12345678',
                         b'Set-Cookie: session=harmless12345678', b'password=harmless12345678',
                         b'https://example.test/a?X-Amz-Signature=' + b'a' * 64,
                         b'.'.join(b'eyJ' + part * 10 for part in (b'a', b'b')) + b'.' + b'c' * 10,
                         b'-----BEGIN OPENSSH PRIVATE KEY-----', b'sk-' + b'A' * 30,
                         b'{"\\u0070assword":"harmless12345678"}',
                         'password=harmless12345678'.encode('utf-16')]
            for index, data in enumerate(sentinels):
                write(publication, data)
                check('publication_secret_' + str(index), 'publication', publication, {'publication_secret'})
            write(publication, b'ordinary opaque sentinel value')
            check('publication_known_secret', 'publication', publication, {'publication_secret'},
                  known_secrets=['opaque sentinel'])
            write(publication, b'An observed harmless result with no credentials.\n')
            check('safe_publication_unchanged', 'publication', publication)
            write(publication, b'{"value": Infinity}')
            check('strict_json_infinity', 'json', publication, {'json_nonfinite'})
            check('strict_canonical_infinity', 'canonical', publication, {'json_nonfinite'})
            write(publication, b'{"a":1,"a":2}')
            check('strict_json_duplicate', 'json', publication, {'duplicate_json_key'})
            write(publication, b'{"value":"\\ud800"}')
            check('strict_json_invalid_unicode', 'json', publication, {'json_invalid'})
            reset()
            final = check('restored_inputs_still_valid', 'inspect', inputs_path)
            assert final == report
    except (AssertionError, OSError, subprocess.SubprocessError) as error:
        failure = str(error)
    else:
        failure = None
    result = {'kind': 'engagement-contract-e2e-v2', 'status': 'failed' if failure else 'passed',
              'classification': 'provider-free external-input workflow',
              'command': [sys.executable, str(Path(__file__).resolve()), '--output', str(args.output)],
              'environment': {'python': platform.python_version(), 'platform': platform.platform(),
                              'required': ['ssh-keygen'], 'provider_calls': 0, 'target_calls': 0},
              'checks': checks, 'failure': failure,
              'cleanup': 'temporary fixture and ephemeral signing key removed',
              'unverified': ['native runtime isolation', 'provider behavior', 'target effects',
                             'remote enforcement', 'research acceptance']}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write(args.output, encoded(result))
    print(json.dumps({'status': result['status'], 'checks': len(checks),
                      'failed': [row['name'] for row in checks if not row['passed']],
                      'output': str(args.output)}))
    return int(failure is not None)


if __name__ == '__main__':
    raise SystemExit(main())
