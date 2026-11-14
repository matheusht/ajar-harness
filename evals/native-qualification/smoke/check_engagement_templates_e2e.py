#!/usr/bin/env python3
"""Materialize each unsigned template with disposable pins, sign, and load it.

The four access modes must retain complete v2 fields and produce valid signed
inputs after operator placeholders are filled. Original templates must contain
no usable signature or private credential. This is packaging, not runtime proof.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))


def run(base, fixture_file):
    spec = importlib.util.spec_from_file_location('contract_fixture', fixture_file)
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    from engagement_contract import canonical, digest, load_inputs, source_manifest
    rows = []
    for mode, expected in [('source', {'source'}), ('binary', {'binary'}), ('application', {'application'}),
                           ('combined', {'source', 'binary', 'application'})]:
        try:
            template = ROOT / 'examples/native-engagement-v2' / mode
            original_scope = (template / 'scope.md').read_text()
            assert 'UNSIGNED TEMPLATE' in original_scope and 'REPLACE_' in original_scope
            assert not list(template.glob('*.sig')) and not (template / 'allowed_signers').exists()
            root = base / mode
            inputs = fixture.make_fixture(root)
            initial = json.loads(inputs.read_bytes())
            initial_scope = fixture.fixture_scope(inputs)
            for source in template.iterdir():
                if source.is_file():
                    destination = root / source.name
                    fixture.write(destination, source.read_bytes())
            source_root = Path(initial['access_files']['source-main'])
            runtime_binary = root / 'native-fixture'
            replacements = {
                '/REPLACE_PRIVATE_ROOT/' + mode: str(root), '/REPLACE_SOURCE_TREE': str(source_root),
                '/REPLACE_BINARY_FILE': str(runtime_binary), '/REPLACE_CODEX_EXECUTABLE': str(runtime_binary),
                '/REPLACE_DOCKER_EXECUTABLE': str(runtime_binary), '/REPLACE_DOCKER_SOCKET': str(root / 'docker.sock'),
                '/REPLACE_NATIVE_SCHEMA': str(root / 'runtime-schema.json'),
                '/REPLACE_CODEX_TOOL_BUNDLE': str(root / 'native-bundle'),
                'REPLACE_OPERATOR_ID': 'fixture-operator', 'REPLACE_ISSUED_AT_UTC': initial_scope['issued_at'],
                'REPLACE_GOAL_TEXT': 'Inspect the harmless template fixture and retain its exact limits.',
                'REPLACE_PERMITTED_MODEL': 'fixture-model',
                'REPLACE_POSITIVE_INVOCATION_BUDGET': 10, 'REPLACE_POSITIVE_TOTAL_WORKER_SECONDS': 3600,
            }
            def fill(value):
                if isinstance(value, dict):return {key: fill(item) for key, item in value.items()}
                if isinstance(value, list):return [fill(item) for item in value]
                if not isinstance(value, str):return value
                if value in replacements:return replacements[value]
                for before, after in replacements.items():
                    if isinstance(after, str):value = value.replace(before, after)
                if value.startswith('sha256:REPLACE_'):return 'sha256:' + '1' * 64
                return value
            definitions = fill(json.loads((template / 'inputs.json').read_text()))
            definitions.update(scope_signature=initial['scope_signature'], allowed_signers=initial['allowed_signers'],
                               trusted_fingerprint=initial['trusted_fingerprint'])
            scope = fill(json.loads(re.search(r'```native-engagement-scope-v2\n(.*?)\n```', original_scope, re.S).group(1)))
            goal = Path(definitions['goal_file'])
            fixture.write(goal, fill(goal.read_text()).encode())
            scope['goal_sha256'] = digest(goal.read_bytes())
            for access in scope['access']:
                if access['kind'] == 'source':access['identity']['manifest_sha256'] = digest(canonical(source_manifest(source_root)))
                if access['kind'] == 'binary':access['identity']['sha256'] = digest(runtime_binary.read_bytes())
            for assignment in scope['runtime_assignments']:
                path = Path(definitions['runtime_profiles'][assignment['profile_id']])
                profile = fill(json.loads(path.read_text()))
                profile['executable']['sha256'] = digest(runtime_binary.read_bytes())
                profile['protocol']['schema_sha256'] = digest(Path(profile['protocol']['schema_file']).read_bytes())
                config = Path(profile['config_file'])
                fixture.write(config, fill(config.read_text()).encode())
                profile['config_sha256'] = digest(Path(profile['config_file']).read_bytes())
                profile['tool_bundle']['manifest_sha256'] = digest(canonical(source_manifest(root / 'native-bundle')))
                fixture.write(path, canonical(profile))
                assignment['profile_sha256'] = digest(path.read_bytes())
            for reference in scope['environments']:
                path = Path(definitions['environment_profiles'][reference['profile_id']])
                fixture.write(path, canonical(fill(json.loads(path.read_text()))))
                reference['profile_sha256'] = digest(path.read_bytes())
            fixture.write(inputs, canonical(definitions))
            fixture.resign_fixture(inputs, scope)
            verified = load_inputs(inputs)
            assert {row['kind'] for row in verified.scope['access']} == expected
            assert not verified.scope['patch_required']
            rows.append({'check': mode, 'status': 'passed'})
        except Exception as error:
            rows.append({'check': mode, 'status': 'failed', 'error': str(error)})
    return {'status': 'passed' if all(row['status'] == 'passed' for row in rows) else 'failed',
            'classification': 'materialized_unsigned_templates_with_fixture_signatures',
            'provider_calls': 0, 'target_calls': 0, 'checks': rows}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--contract-fixture', type=Path, default=Path(__file__).with_name('check_engagement_contract_e2e.py'))
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='engagement-templates-') as temporary:
        result = run(Path(temporary).resolve(), args.contract_fixture)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
    raise SystemExit(result['status'] != 'passed')
