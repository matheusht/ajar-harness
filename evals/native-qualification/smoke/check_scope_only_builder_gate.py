#!/usr/bin/env python3
"""Failure-first scope-only builder authority check; no Docker or provider.

Checks the signed catalog/image/output/budget envelope before a build effect,
then checks that changed frozen inputs cannot reuse a derived authority. The
joined Docker scenario remains the separate end-to-end qualification gate.
"""

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
import native_research as runner
import native_setup_builder as builder
import check_scope_only_authority as scope_fixture


def fixture(base: Path) -> dict:
    """Synthesize a stopped setup with exact host receipts; no model or Docker effect."""
    item = scope_fixture.fixture(base)
    if item['prepare_code']:
        raise RuntimeError('full-engagement prepare failed: ' + str(item['prepare_result']))
    root = item['root']
    controls = root / 'controls'
    plan = runner._read_json(root / 'plan.json')
    runner._derived_approval(root, plan, phase='setup', create=True)
    dispatch_id = 'a' * 32
    producer_ids = ['b' * 64, 'c' * 64]
    manifest = {'producers': [{'id': value} for value in producer_ids]}
    runner._write_json(controls / 'producer-manifest.json', manifest, once=True)
    manifest_sha = runner._sha(controls / 'producer-manifest.json')
    state = controls / 'native-state'
    state.mkdir(mode=0o700, exist_ok=True)
    runner._write_json(state / 'RUN.json',
                       {'ids': producer_ids, 'manifest_sha256': manifest_sha}, once=True)
    runner._write_json(state / 'REVOKED',
                       {'ids': producer_ids, 'manifest_sha256': manifest_sha,
                        'producers_verified_stopped': True}, once=True)
    resources = {'resources': [
        {'kind': 'container', 'name': 'synthetic-researcher', 'id': producer_ids[0]},
        {'kind': 'container', 'name': 'synthetic-relay', 'id': producer_ids[1]},
        {'kind': 'network', 'name': 'synthetic-network', 'id': 'd' * 64}]}
    runner._write_json(controls / 'resources.json', resources, once=True)
    provider = controls / 'provider'
    provider.mkdir(mode=0o700, exist_ok=True)
    created = datetime.now(timezone.utc).timestamp()
    provider_config = {'producer_manifest_sha256': manifest_sha,
                       'max_connections': plan['limits']['max_connections'],
                       'max_bytes': plan['limits']['max_bytes'],
                       'native_run_duration': plan['limits']['duration_seconds'],
                       'duration': plan['limits']['duration_seconds'],
                       'authority': runner.AUTHORITY}
    with sqlite3.connect(provider / 'tunnel.sqlite3') as db:
        db.execute('CREATE TABLE pool (config TEXT, created REAL, bytes INTEGER)')
        db.execute('INSERT INTO pool VALUES (?,?,?)',
                   (json.dumps(provider_config), created, 0))
        db.execute('CREATE TABLE tunnels (phase TEXT, uploaded INTEGER DEFAULT 0, '
                   'downloaded INTEGER DEFAULT 0)')
    pool_after = {'hard_limits': plan['limits'], 'used_tunnels': 0,
                  'charged_tunnel_bytes': 0,
                  'provider_deadline_unix': created + plan['limits']['duration_seconds'],
                  'run_identity': {'manifest_sha256': manifest_sha, 'ids': producer_ids}}
    dispatch_dir = controls / 'dispatch'
    dispatch_dir.mkdir(mode=0o700, exist_ok=True)
    trace = dispatch_dir / (dispatch_id + '.trace.json')
    runner._write_json(trace, {}, once=True)
    dispatch_path = dispatch_dir / (dispatch_id + '.json')
    runner._write_json(dispatch_path, {
        'kind': 'native-dispatch-v1', 'role': 'researcher', 'dispatch_id': dispatch_id,
        'setup_sequence': 1, 'status': 'acknowledged', 'pool_after': pool_after}, once=True)
    catalog_spec = runner._read_json(item['catalog'] / 'catalog.json')
    frozen = controls / 'setup-output'
    frozen.mkdir(mode=0o700)
    recipe = {
        'kind': 'native-setup-recipe-v2',
        'runtime': {'version_command': ['sh', '-c', 'printf fixture'],
                    'version_stdout': 'fixture',
                    'dependency_command': ['sh', '-c', 'true']},
        'build_command': ['sh', '-c', 'mkdir -p out; printf fixture > out/result.txt'],
        'offline_dependencies': [entry['id'] for entry in catalog_spec['entries']],
        'outputs': ['out/result.txt']}
    runner._write_json(frozen / 'recipe.json', recipe, once=True)
    (frozen / 'THREAT_MODEL.md').write_text(
        '# Initial threat model\n\nEntry path: main.py. Asset: fixture output. '
        'Assumption: offline build. Disconfirm with a blocked network check.\n')
    runner._write_json(frozen / 'receipt.json', {
        'kind': 'native-setup-output-v1', 'status': 'frozen_proposal',
        'plan_sha256': runner._sha(root / 'plan.json'),
        'approval_sha256': runner._sha(controls / 'approval.json'),
        'original_source_manifest_sha256': plan['source_manifest_sha256'],
        'dispatch_id': dispatch_id, 'setup_sequence': 1,
        'dispatch_sha256': runner._sha(dispatch_path),
        'native_trace_sha256': runner._sha(trace),
        'pool_before': None, 'pool_after': pool_after, 'native_usage': None,
        'files': {'recipe.json': runner._sha(frozen / 'recipe.json'),
                  'THREAT_MODEL.md': runner._sha(frozen / 'THREAT_MODEL.md')},
        'assessment': 'proposal_needs_host_review',
        'target_build_executed': False, 'security_result': None}, once=True)
    snapshot = runner._filesystem_snapshot(root, plan)
    snapshot['native_stop'] = {
        'manifest_sha256': manifest_sha,
        'producer_ids_sha256': hashlib.sha256(json.dumps(
            producer_ids, separators=(',', ':')).encode()).hexdigest(),
        'revoked_sha256': runner._sha(state / 'REVOKED')}
    runner._write_json(controls / 'host-snapshot.json', snapshot, once=True)
    cleanup = {'status': 'complete', 'resources': [
        {'kind': row['kind'], 'name': row['name'], 'absent': True}
        for row in reversed(resources['resources'])]}
    runner._write_json(controls / 'cleanup.json', cleanup, once=True)
    runner._write_json(controls / 'final.json', {
        'status': 'stopped_complete', 'native_stop': {'status': 'stopped'},
        'host_snapshot': {'status': 'complete',
                          'receipt_sha256': runner._sha(controls / 'host-snapshot.json')},
        'cleanup': cleanup}, once=True)
    item['key'].unlink()
    item.update(plan=plan, recipe=recipe, pool_after=pool_after)
    return item


def main() -> None:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    checks = {}

    def refused(name, call):
        try:
            call()
        except (builder.BuildError, runner.NativeResearchError):
            checks[name] = True
        else:
            checks[name] = False

    with tempfile.TemporaryDirectory(prefix='scope-only-builder-gate-') as temporary:
        item = fixture(Path(temporary).resolve())
        root = item['root']
        controls = root / 'controls'
        plan = item['plan']
        if plan.get('autonomous_engagement', {}).get('kind') != 'native-engagement-scope-v1':
            raise RuntimeError('scope-only fixture did not prepare a full-engagement plan')
        recipe = item['recipe']
        catalog_root = item['catalog']
        catalog = builder.catalog_snapshot(catalog_root, recipe)
        absent = subprocess.CompletedProcess([], 0, b'', b'')
        with patch.dict(os.environ, {'PATH': item['env']['PATH']}), \
             patch.object(runner, '_docker', return_value=absent):
            setup = builder.frozen_setup(root)
            checks['synthetic_stopped_setup_verified'] = (
                setup['receipt']['assessment'] == 'proposal_needs_host_review'
                and setup['chain']['cumulative_used'] == {'connections': 0, 'bytes': 0})
            authority = builder.derived_build_authority(setup, catalog)
            path = controls / 'scope-only-build-authority.json'
            runner._write_json(path, authority, once=True)
            checks['derived_from_initial_scope'] = (
                authority['kind'] == 'native-setup-build-derived-authority-v1'
                and not item['docker_marker'].exists()
                and not item['key'].exists()
                and all('operator_signature' not in authority[key]
                        for key in ('scope_amendment', 'approval'))
                and builder.verify_authority(setup, path, catalog) == authority)

            try:
                builder.setup_build(root, None, catalog_root)
            except builder.BuildError as error:
                checks['public_build_accepts_scope_only_authority'] = (
                    str(error) == 'build_docker_daemon_unavailable'
                    and item['docker_marker'].exists()
                    and not (controls / 'setup-build').exists())
            else:
                checks['public_build_accepts_scope_only_authority'] = False
            item['docker_marker'].unlink(missing_ok=True)

            changed_catalog = deepcopy(catalog)
            changed_catalog['tree']['tree_sha256'] = '0' * 64
            refused('changed_catalog_refused',
                    lambda: builder.derived_build_authority(setup, changed_catalog))

            refused('later_build_approval_refused',
                    lambda: builder.setup_build(root, path, catalog_root))

            with patch.object(builder, 'prior_build_attempts', return_value={
                    'receipts': ['0' * 64], 'charged_seconds': 120}):
                refused('signed_attempt_limit_refused',
                        lambda: builder.derived_build_authority(setup, catalog))

            refused('deadline_cannot_be_renewed',
                    lambda: builder.derived_build_authority(
                        setup, catalog, approved_at=authority['approval']['expires_at'],
                        historical=True))

            changed_recipe = deepcopy(setup)
            changed_recipe['recipe'] = {**recipe, 'outputs': ['../outside']}
            refused('unsafe_output_refused',
                    lambda: builder.derived_build_authority(changed_recipe, catalog))

            changed_recipe = deepcopy(setup)
            changed_recipe['recipe'] = {**recipe, 'outputs': ['other.txt']}
            refused('changed_output_refuses_prior_authority',
                    lambda: builder.verify_authority(changed_recipe, path, catalog))

            forged = deepcopy(authority)
            forged['scope_amendment']['image_id'] = 'sha256:' + '0' * 64
            runner._write_json(path, forged)
            refused('different_build_image_refused',
                    lambda: builder.verify_authority(setup, path, catalog))

            changed_plan = deepcopy(setup)
            changed_plan['plan']['source_manifest_sha256'] = '0' * 64
            refused('changed_source_pin_refused',
                    lambda: builder.derived_build_authority(changed_plan, catalog))

            threat = controls / 'setup-output/THREAT_MODEL.md'
            original_threat = threat.read_bytes()
            threat.write_bytes(original_threat + b'changed\n')
            refused('changed_initial_threat_model_refused',
                    lambda: builder.frozen_setup(root))
            threat.write_bytes(original_threat)

            scope = controls / 'scope.md'
            original_scope = scope.read_bytes()
            scope.write_bytes(original_scope + b'changed\n')
            refused('changed_signed_scope_refused',
                    lambda: builder.frozen_setup(root))
            scope.write_bytes(original_scope)

    result = {'status': 'passed' if all(checks.values()) else 'failed',
              'checks': checks, 'provider_calls': 0, 'target_service_calls': 0,
              'real_docker_calls': 0, 'docker_shim_calls': 1}
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    if result['status'] != 'passed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
