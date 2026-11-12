#!/usr/bin/env python3
"""Host-owned, offline build of a frozen native setup proposal.

The #208 setup turn has already stopped. This tool neither contacts a provider
nor starts research. It consumes its exact frozen proposal, a separately signed
offline-build scope amendment and approval, and a host-selected image/catalog.
"""

from __future__ import annotations

import argparse
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import select
import shlex
import shutil
import sqlite3
import stat
import subprocess
import time
import uuid

from engagement_records import RecordError, canonical_json_bytes
from operator_signature import verify_embedded_operator_signature
import native_research as nr


NAMESPACE = nr.SETUP_SIGNATURE_NAMESPACE
EFFECT_CLASS = 'owned-disposable-offline-target-build'
NETWORK_CLASS = 'none'
CATALOG_KIND = 'native-setup-dependency-catalog-v1'
MAX_OUTPUT_BYTES = 64 * 1024 * 1024
MAX_CATALOG_BYTES = 128 * 1024 * 1024


class BuildError(RuntimeError):
    pass


def fail(code: str) -> None:
    raise BuildError(code)


def sha(path: Path) -> str:
    return nr._sha(path)


def digest(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def source_modes(root: Path, inventory: dict[str, str]) -> dict[str, int]:
    modes = {}
    for name in inventory:
        entry = (root / name).stat(follow_symlinks=False)
        mode = stat.S_IMODE(entry.st_mode)
        if not stat.S_ISREG(entry.st_mode) or mode > 0o777 or mode & 0o022:
            fail('build_source_mode_unsafe')
        modes[name] = mode
    return modes


def read_json(path: Path) -> dict:
    return nr._read_json(path)


def write_json(path: Path, value: dict, *, once: bool = False) -> None:
    nr._write_json(path, value, once=once)


def safe_path(value: object) -> str:
    if not isinstance(value, str) or not value or len(value.encode()) > 512:
        fail('build_path_invalid')
    path = PurePosixPath(value)
    if (path.is_absolute() or any(part in ('.', '..') for part in value.split('/'))
            or value.startswith('/') or value.endswith('/') or '//' in value
            or '\\' in value
            or any(ord(character) < 32 for character in value)):
        fail('build_path_invalid')
    return value


def utc(value: object) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(
            r'20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z', value):
        fail('build_time_invalid')
    try:
        return datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
    except ValueError:
        fail('build_time_invalid')


def private_directory(path: Path) -> Path:
    if not path.is_absolute() or path.is_symlink() or not path.is_dir():
        fail('build_directory_invalid')
    entry = path.stat(follow_symlinks=False)
    if entry.st_uid != os.getuid() or entry.st_mode & 0o077:
        fail('build_directory_permissions')
    return path


def catalog_snapshot(path: Path, recipe: dict) -> dict:
    root = private_directory(path)
    spec = read_json(root / 'catalog.json')
    entries = spec.get('entries')
    if (set(spec) != {'kind', 'entries'} or spec['kind'] != CATALOG_KIND
            or not isinstance(entries, list) or len(entries) > 256):
        fail('build_catalog_invalid')
    names = {}
    for row in entries:
        if not isinstance(row, dict) or set(row) != {'id', 'path', 'sha256', 'mode'}:
            fail('build_catalog_invalid')
        name, relative = safe_path(row['id']), safe_path(row['path'])
        if not relative.startswith('payload/'):
            fail('build_catalog_invalid')
        if name in names or not nr.HEX_RE.fullmatch(str(row['sha256'])):
            fail('build_catalog_invalid')
        file = root / relative
        if sha(nr._file(file)) != row['sha256']:
            fail('build_catalog_file_changed')
        mode = stat.S_IMODE(file.stat(follow_symlinks=False).st_mode)
        if (type(row['mode']) is not int or mode != row['mode'] or mode > 0o777
                or not mode & 0o400 or mode & 0o022):
            fail('build_catalog_mode_changed_or_unsafe')
        names[name] = {'path': relative, 'sha256': row['sha256'], 'mode': mode}
    observed = nr._inventory(root, max_files=10000, max_bytes=MAX_CATALOG_BYTES)
    aggregate = hashlib.sha256()
    for relative, file_sha in sorted(observed.items()):
        aggregate.update(json.dumps([relative, file_sha], separators=(',', ':'),
                                    ensure_ascii=False).encode() + b'\n')
    inventory = {'files': len(observed), 'bytes': sum((root / name).stat().st_size
                                                     for name in observed),
                 'tree_sha256': aggregate.hexdigest()}
    if set(observed) != {'catalog.json'} | {row['path'] for row in names.values()}:
        fail('build_catalog_unlisted_file')
    requested = recipe['offline_dependencies']
    if len(set(requested)) != len(requested) or set(requested) != set(names):
        fail('build_dependency_missing_or_unselected')
    for name in requested:
        safe_path(name)
        if names[name]['path'] != 'payload/' + name:
            fail('build_dependency_path_mismatch')
    return {'root': root, 'tree': inventory, 'selected': {
        name: {'sha256': names[name]['sha256'], 'mode': names[name]['mode']}
        for name in sorted(names)}}


def frozen_setup(run_root: Path) -> dict:
    root = nr._private_root(run_root)
    plan = nr._verified_plan(root, allow_expired_setup=True)
    controls = root / 'controls'
    if 'setup_only' not in plan:
        fail('build_requires_setup_run')
    if nr._unresolved_dispatches(root):
        fail('setup_dispatch_unknown_effect')
    snapshot = nr._filesystem_snapshot(root, plan)
    frozen = controls / 'setup-output'
    receipt = read_json(frozen / 'receipt.json')
    if (snapshot.get('status') != 'complete'
            or snapshot.get('setup_output_receipt_sha256') != sha(frozen / 'receipt.json')
            or receipt.get('assessment') != 'proposal_needs_host_review'
            or receipt.get('target_build_executed') is not False
            or receipt.get('security_result') is not None):
        fail('build_setup_proposal_invalid')
    final = read_json(controls / 'final.json')
    host_snapshot = read_json(controls / 'host-snapshot.json')
    cleanup = read_json(controls / 'cleanup.json')
    native_stop = host_snapshot.get('native_stop')
    byte_snapshot = dict(host_snapshot)
    byte_snapshot.pop('native_stop', None)
    if (final.get('status') != 'stopped_complete'
            or final.get('native_stop', {}).get('status') != 'stopped'
            or final.get('host_snapshot', {}).get('status') != 'complete'
            or final['host_snapshot'].get('receipt_sha256') != sha(controls / 'host-snapshot.json')
            or byte_snapshot != snapshot
            or final.get('cleanup') != cleanup
            or cleanup.get('status') != 'complete'
            or any(row.get('absent') is not True for row in cleanup.get('resources', []))):
        fail('build_setup_stop_or_cleanup_incomplete')
    if not isinstance(native_stop, dict):
        fail('build_setup_native_stop_proof_missing')
    chain = None
    if read_json(controls / 'approval.json').get('kind') == 'native-setup-approval-v2':
        if not hasattr(nr, 'setup_chain_snapshot'):
            fail('build_setup_chain_verifier_unavailable')
        chain = nr.setup_chain_snapshot(root)
        if (chain.get('current_run_root') != str(root)
                or chain.get('current_plan_sha256') != sha(root / 'plan.json')
                or chain.get('approval_sha256') != sha(controls / 'approval.json')
                or chain.get('current_terminal_sha256') != sha(controls / 'final.json')):
            fail('build_setup_chain_mismatch')
        checkpoint_path = (controls / 'setup-checkpoints' / receipt['dispatch_id'] / 'receipt.json')
        checkpoint = read_json(checkpoint_path)
        if (chain.get('current_checkpoint_sha256') != sha(checkpoint_path)
                or checkpoint.get('files') != receipt.get('files')):
            fail('build_setup_checkpoint_output_mismatch')
    else:
        if not (controls / 'setup-approval-receipt.json').exists():
            fail('build_setup_approval_receipt_missing')
        nr._setup_approval(root, plan, controls / 'approval.json', allow_expired=True)
        verify_v1_stop_provenance(root, plan, host_snapshot, cleanup, receipt)
    recipe = read_json(frozen / 'recipe.json')
    if (set(recipe) != {'kind', 'runtime', 'build_command', 'offline_dependencies'}
            or recipe['kind'] != 'native-setup-recipe-v1'
            or not isinstance(recipe['offline_dependencies'], list)
            or len(recipe['offline_dependencies']) > 256
            or any(not isinstance(item, str) or not 1 <= len(item) <= 256
                   for item in recipe['offline_dependencies'])):
        fail('build_recipe_invalid')
    nr._validate_source_runtime(recipe['runtime'])
    nr._validate_argv(recipe['build_command'])
    threat = nr._file(frozen / 'THREAT_MODEL.md', private=True)
    if not threat.read_text().strip():
        fail('build_threat_model_empty')
    allowance = receipt.get('pool_after')
    limits = allowance.get('hard_limits') if isinstance(allowance, dict) else None
    if (not isinstance(limits, dict)
            or limits.get('max_connections') != plan['limits']['max_connections']
            or limits.get('max_bytes') != plan['limits']['max_bytes']
            or type(allowance.get('used_tunnels')) is not int
            or type(allowance.get('charged_tunnel_bytes')) is not int
            or not 0 <= allowance['used_tunnels'] <= limits['max_connections']
            or not 0 <= allowance['charged_tunnel_bytes'] <= limits['max_bytes']):
        fail('build_setup_allowance_invalid')
    dispatch = read_json(controls / 'dispatch' / (receipt['dispatch_id'] + '.json'))
    if dispatch.get('pool_after') != allowance:
        fail('build_setup_allowance_dispatch_mismatch')
    if chain is not None:
        pool = nr._provider_snapshot(root)
        if (allowance['used_tunnels'] != pool['used_tunnels']
                or allowance['charged_tunnel_bytes'] != pool['charged_tunnel_bytes']
                or chain['cumulative_used']['connections'] < pool['used_tunnels']
                or chain['cumulative_used']['bytes'] < pool['charged_tunnel_bytes']):
            fail('build_setup_provider_accounting_mismatch')
    if chain is None:
        limits = plan['limits']
        used = {'connections': allowance['used_tunnels'],
                'bytes': allowance['charged_tunnel_bytes']}
        chain = {'initial_run_root': str(root), 'initial_plan_sha256': sha(root / 'plan.json'),
                 'current_run_root': str(root), 'current_plan_sha256': sha(root / 'plan.json'),
                 'approval_sha256': sha(controls / 'approval.json'), 'epoch_index': 0,
                 'cumulative_used': used, 'original_limits': limits,
                 'absolute_deadline': allowance['provider_deadline_unix'],
                 'current_terminal_sha256': sha(controls / 'final.json'),
                 'current_checkpoint_sha256': None,
                 'chain_sha256': digest({'single_epoch': sha(controls / 'final.json'),
                                         'approval': sha(controls / 'approval.json')})}
    return {'root': root, 'controls': controls, 'plan': plan, 'recipe': recipe,
            'receipt': receipt, 'allowance': allowance, 'chain': chain}


def verify_v1_stop_provenance(root: Path, plan: dict, snapshot: dict,
                              cleanup: dict, receipt: dict) -> None:
    controls = root / 'controls'
    manifest_path = controls / 'producer-manifest.json'
    manifest = read_json(manifest_path)
    run = read_json(controls / 'native-state/RUN.json')
    revoked_path = controls / 'native-state/REVOKED'
    revoked = read_json(revoked_path)
    resources = read_json(controls / 'resources.json')
    ids = [row.get('id') for row in resources.get('resources', [])
           if row.get('kind') == 'container']
    expected_ids = [row.get('id') for row in manifest.get('producers', [])]
    manifest_sha = sha(manifest_path)
    if (len(ids) != 2 or any(not isinstance(item, str) or
                             not re.fullmatch(r'[0-9a-f]{64}', item) for item in ids)
            or ids != expected_ids or run.get('ids') != ids or revoked.get('ids') != ids
            or revoked.get('producers_verified_stopped') is not True
            or run.get('manifest_sha256') != manifest_sha
            or revoked.get('manifest_sha256') != manifest_sha
            or snapshot['native_stop'].get('manifest_sha256') != manifest_sha
            or snapshot['native_stop'].get('revoked_sha256') != sha(revoked_path)
            or snapshot['native_stop'].get('producer_ids_sha256') != hashlib.sha256(
                json.dumps(ids, separators=(',', ':')).encode()).hexdigest()):
        fail('build_setup_native_stop_proof_invalid')
    recorded = {(row.get('kind'), row.get('name')) for row in resources.get('resources', [])}
    cleaned = {(row.get('kind'), row.get('name')) for row in cleanup.get('resources', [])}
    if (not recorded or recorded != cleaned
            or len(recorded) != len(resources['resources'])
            or len(cleaned) != len(cleanup['resources'])):
        fail('build_setup_resource_cleanup_mismatch')
    for row in resources['resources']:
        kind, identifier = row.get('kind'), row.get('id')
        if kind not in ('container', 'network') or not isinstance(identifier, str):
            fail('build_setup_resource_invalid')
        result = nr._docker(kind, 'ls', '-a', '--no-trunc', '--filter', 'id=' + identifier,
                            '--format', '{{.ID}}', timeout=15) if kind == 'container' else nr._docker(
                                'network', 'ls', '--no-trunc', '--filter', 'id=' + identifier,
                                '--format', '{{.ID}}', timeout=15)
        if result.stdout.strip():
            fail('build_setup_resource_still_present')
    ledger_before = nr._setup_provider_pins(root)
    pool = nr._provider_snapshot(root)
    try:
        with closing(sqlite3.connect('file:' + str(controls / 'provider/tunnel.sqlite3') + '?mode=ro',
                                     uri=True, timeout=1)) as db:
            tunnel_count, tunnel_bytes = db.execute(
                'SELECT COUNT(*),COALESCE(SUM(uploaded+downloaded),0) FROM tunnels').fetchone()
    except sqlite3.Error:
        fail('build_setup_provider_ledger_unavailable')
    if nr._setup_provider_pins(root) != ledger_before:
        fail('build_setup_provider_ledger_changed')
    config = pool['config']
    after = receipt.get('pool_after')
    if (not isinstance(after, dict)
            or config.get('producer_manifest_sha256') != manifest_sha
            or config.get('max_connections') != plan['limits']['max_connections']
            or config.get('max_bytes') != plan['limits']['max_bytes']
            or config.get('native_run_duration') != plan['limits']['duration_seconds']
            or config.get('authority') != nr.AUTHORITY
            or after.get('used_tunnels') != pool['used_tunnels']
            or after.get('charged_tunnel_bytes') != pool['charged_tunnel_bytes']
            or after.get('provider_deadline_unix') != pool['created'] + config['duration']
            or after.get('run_identity', {}).get('manifest_sha256') != manifest_sha
            or after.get('run_identity', {}).get('ids') != ids
            or set(pool.get('tunnel_phases', {})) - {'closed'}
            or sum(pool.get('tunnel_phases', {}).values()) != pool['used_tunnels']
            or tunnel_count != pool['used_tunnels']
            or tunnel_bytes != pool['charged_tunnel_bytes']):
        fail('build_setup_provider_accounting_mismatch')


def check_setup_fresh(setup: dict) -> None:
    approval = read_json(setup['controls'] / 'approval.json')
    scope = read_json_from_scope(setup['controls'] / 'scope.md')
    if (datetime.now(timezone.utc) >= utc(approval['expires_at'])
            or datetime.now(timezone.utc) >= utc(scope['expires_at'])):
        fail('checked_setup_grant_expired')


def template(run_root: Path, image_id: str, catalog_path: Path,
             max_workspace_bytes: int, memory_bytes: int, duration_seconds: int,
             output_paths: list[str], approved_at: str, expires_at: str,
             *, require_fresh: bool = True) -> dict:
    setup = frozen_setup(run_root)
    if require_fresh:
        check_setup_fresh(setup)
    root, controls, plan, recipe = (setup[key] for key in ('root', 'controls', 'plan', 'recipe'))
    if (not nr.IMAGE_RE.fullmatch(image_id)
            or type(max_workspace_bytes) is not int
            or not 8 * 1024 * 1024 <= max_workspace_bytes <= 128 * 1024 * 1024
            or type(memory_bytes) is not int
            or not 64 * 1024 * 1024 <= memory_bytes <= 1024 * 1024 * 1024
            or type(duration_seconds) is not int or not 5 <= duration_seconds <= 600
            or not 1 <= len(output_paths) <= 64):
        fail('build_limits_invalid')
    outputs = [safe_path(path) for path in output_paths]
    if len(set(outputs)) != len(outputs):
        fail('build_output_duplicate')
    catalog = catalog_snapshot(catalog_path, recipe)
    approved, expires = utc(approved_at), utc(expires_at)
    if (approved >= expires or expires > approved + timedelta(hours=24)
            or (require_fresh and not approved <= datetime.now(timezone.utc) < expires)):
        fail('build_approval_time_invalid')
    scope = read_json_from_scope(controls / 'scope.md')
    if expires > utc(scope['expires_at']):
        fail('build_exceeds_setup_scope_expiry')
    amendment = {'kind': 'native-setup-build-scope-v1',
                 'engagement_id': plan['setup_only']['engagement_id'],
                 'operator_id': plan['setup_only']['operator_id'],
                 'source_manifest_sha256': plan['source_manifest_sha256'],
                 'setup_scope_sha256': plan['scope_sha256'],
                 'goal_sha256': plan['brief_sha256'],
                 'setup_output_receipt_sha256': sha(controls / 'setup-output/receipt.json'),
                 'setup_chain_sha256': setup['chain']['chain_sha256'],
                 'cumulative_setup_used': setup['chain']['cumulative_used'],
                 'recipe_sha256': sha(controls / 'setup-output/recipe.json'),
                 'threat_model_sha256': sha(controls / 'setup-output/THREAT_MODEL.md'),
                 'effect_class': EFFECT_CLASS, 'network_class': NETWORK_CLASS,
                 'image_id': image_id, 'platform': plan['platform'],
                 'dependency_catalog_tree_sha256': catalog['tree']['tree_sha256'],
                 'dependencies': catalog['selected'], 'outputs': outputs,
                 'max_workspace_bytes': max_workspace_bytes,
                 'memory_bytes': memory_bytes, 'duration_seconds': duration_seconds,
                 'expires_at': expires_at}
    approval = {'kind': 'native-setup-build-approval-v1',
                'scope_amendment_sha256': digest(amendment),
                'setup_plan_sha256': sha(root / 'plan.json'),
                'setup_approval_sha256': sha(controls / 'approval.json'),
                'setup_chain_sha256': setup['chain']['chain_sha256'],
                'cumulative_setup_used': setup['chain']['cumulative_used'],
                'effect_class': EFFECT_CLASS, 'network_class': NETWORK_CLASS,
                'image_id': image_id,
                'dependency_catalog_tree_sha256': catalog['tree']['tree_sha256'],
                'max_workspace_bytes': max_workspace_bytes,
                'memory_bytes': memory_bytes, 'duration_seconds': duration_seconds,
                'outputs': outputs, 'approved_by': plan['setup_only']['operator_id'],
                'approved_at': approved_at, 'expires_at': expires_at}
    return {'kind': 'native-setup-build-template-v1',
            'scope_amendment': amendment, 'approval': approval}


def read_json_from_scope(path: Path) -> dict:
    text = nr._file(path, private=True).read_text()
    sections = re.findall(r'^```native-setup-scope-v1\s*\n(.*?)^```\s*$',
                          text, re.MULTILINE | re.DOTALL)
    if len(sections) != 1:
        fail('build_setup_scope_invalid')
    try:
        return json.loads(sections[0])
    except ValueError:
        fail('build_setup_scope_invalid')


def verify_authority(setup: dict, path: Path, catalog: dict,
                     *, historical: bool = False) -> dict:
    controls, plan = setup['controls'], setup['plan']
    authority = read_json(nr._file(path, private=True))
    if (set(authority) != {'kind', 'scope_amendment', 'approval'}
            or authority['kind'] != 'native-setup-build-authority-v1'):
        fail('build_authority_invalid')
    amendment, approval = authority['scope_amendment'], authority['approval']
    if not isinstance(amendment, dict) or not isinstance(approval, dict):
        fail('build_authority_invalid')
    amendment_unsigned = {key: value for key, value in amendment.items()
                          if key != 'operator_signature'}
    approval_unsigned = {key: value for key, value in approval.items()
                         if key != 'operator_signature'}
    try:
        expected = template(setup['root'], amendment.get('image_id'), catalog['root'],
                            amendment.get('max_workspace_bytes'), amendment.get('memory_bytes'),
                            amendment.get('duration_seconds'), amendment.get('outputs'),
                            approval.get('approved_at'), approval.get('expires_at'),
                            require_fresh=not historical)
    except (TypeError, KeyError):
        fail('build_authority_invalid')
    if (amendment_unsigned != expected['scope_amendment']
            or approval_unsigned != expected['approval']
            or set(amendment) != set(amendment_unsigned) | {'operator_signature'}
            or set(approval) != set(approval_unsigned) | {'operator_signature'}):
        fail('build_authority_mismatch')
    if utc(amendment['expires_at']) != utc(approval['expires_at']):
        fail('build_authority_expiry_mismatch')
    scope_bytes = (controls / 'scope.md').read_bytes()
    for value, unsigned in ((amendment, amendment_unsigned), (approval, approval_unsigned)):
        try:
            fingerprint = verify_embedded_operator_signature(
                proof=value['operator_signature'], scope_bytes=scope_bytes,
                operator_id=plan['setup_only']['operator_id'],
                challenge_bytes=canonical_json_bytes(unsigned), namespace=NAMESPACE)
        except (RecordError, OSError, KeyError):
            fail('build_authority_signature_invalid')
        if fingerprint != plan['setup_only']['trusted_fingerprint']:
            fail('build_authority_signer_untrusted')
    return authority


@contextmanager
def build_lock(controls: Path):
    path = controls / 'setup-build.lock'
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def docker_call(setup: dict, arguments: list[str], *, timeout: int,
                max_output: int = 1024 * 1024) -> subprocess.CompletedProcess[bytes]:
    command = [setup['plan']['docker_binary'], *arguments]
    environment = {key: os.environ[key] for key in
                   ('HOME', 'PATH', 'DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_CONFIG')
                   if key in os.environ}
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, env=environment)
    buffers = [bytearray(), bytearray()]
    streams = {process.stdout: 0, process.stderr: 1}
    deadline = time.monotonic() + timeout
    try:
        while streams:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout)
            for stream in select.select(list(streams), [], [], min(.2, remaining))[0]:
                chunk = os.read(stream.fileno(), 65536)
                if not chunk:
                    del streams[stream]
                    continue
                buffer = buffers[streams[stream]]
                if len(buffer) + len(chunk) > (max_output if streams[stream] == 0 else 1024 * 1024):
                    fail('build_docker_output_limit_exceeded')
                buffer.extend(chunk)
        code = process.wait(timeout=max(.1, deadline - time.monotonic()))
        return subprocess.CompletedProcess(command, code, bytes(buffers[0]), bytes(buffers[1]))
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdout.close()
        process.stderr.close()


def event_call(setup: dict, journal_path: Path, journal: dict, action: str,
               arguments: list[str], *, timeout: int,
               max_output: int = 1024 * 1024) -> subprocess.CompletedProcess[bytes]:
    event = {'action': action, 'status': 'pending', 'argv_sha256': digest(arguments)}
    journal['events'].append(event)
    journal['status'] = 'pending'
    journal['pending_action'] = action
    write_json(journal_path, journal)
    try:
        result = docker_call(setup, arguments, timeout=timeout, max_output=max_output)
    except (subprocess.TimeoutExpired, OSError, BuildError):
        event['status'] = 'unknown_effect'
        journal['status'] = 'unknown_effect'
        write_json(journal_path, journal)
        fail('build_action_unknown_effect')
    event.update({'status': 'acknowledged', 'exit_code': result.returncode,
                  'stdout_sha256': hashlib.sha256(result.stdout).hexdigest(),
                  'stderr_sha256': hashlib.sha256(result.stderr).hexdigest(),
                  'output_redacted': bool(nr.CREDENTIAL_TEXT.search(
                      (result.stdout + result.stderr).decode(errors='replace')))})
    journal['pending_action'] = None
    write_json(journal_path, journal)
    if event['output_redacted']:
        fail('build_output_credential_like')
    return result


def inspect_container(setup: dict, name: str) -> dict | None:
    result = docker_call(setup, ['container', 'inspect', name], timeout=15)
    if result.returncode:
        if b'No such' in result.stderr:
            return None
        fail('build_container_inspection_unavailable')
    try:
        values = json.loads(result.stdout)
    except ValueError:
        fail('build_container_inspection_invalid')
    if not isinstance(values, list) or len(values) != 1:
        fail('build_container_inspection_invalid')
    return values[0]


def inspect_image(setup: dict, image_id: str) -> None:
    result = docker_call(setup, ['image', 'inspect', image_id], timeout=15,
                         max_output=2 * 1024 * 1024)
    if result.returncode:
        fail('build_image_unavailable')
    try:
        values = json.loads(result.stdout)
    except ValueError:
        fail('build_image_inspection_invalid')
    if not isinstance(values, list) or len(values) != 1:
        fail('build_image_inspection_invalid')
    image = values[0]
    if (image.get('Id') != image_id or image.get('Os') != 'linux'
            or image.get('Architecture') != setup['plan']['platform'].split('/')[1]):
        fail('build_image_pin_mismatch')
    config = image.get('Config') or {}
    environment = config.get('Env') or []
    if not isinstance(environment, list) or any(not isinstance(item, str) for item in environment):
        fail('build_image_environment_invalid')
    if (config.get('Volumes') or any(
            '=' not in item or
            (nr.SENSITIVE_ENV.search(item.split('=', 1)[0]) and item.split('=', 1)[1]) or
            (item.split('=', 1)[0].startswith(('LD_', 'BUN_', 'OPENCODE_')) and
             item != 'BUN_RUNTIME_TRANSPILER_CACHE_PATH=0')
            for item in environment)):
        fail('build_image_ambient_effect_or_credential')


def cleanup_container(setup: dict, journal_path: Path, journal: dict) -> dict:
    name = journal['container_name']
    try:
        info = inspect_container(setup, name)
        if info is not None:
            labels = (info.get('Config') or {}).get('Labels') or {}
            if (info.get('Name', '').lstrip('/') != name
                    or labels.get('io.llm-redteam-harness.setup-build') != journal['nonce']
                    or (journal.get('container_id') is not None
                        and info.get('Id') != journal['container_id'])):
                fail('build_container_identity_mismatch')
            removed = event_call(setup, journal_path, journal, 'container_remove',
                                 ['container', 'rm', '-f', info['Id']], timeout=30)
            if removed.returncode:
                fail('build_container_remove_failed')
        if inspect_container(setup, name) is not None:
            fail('build_container_cleanup_not_absent')
        listing = docker_call(setup, ['container', 'ls', '-a', '--no-trunc',
                                      '--filter', 'name=^/' + name + '$',
                                      '--format', '{{.ID}}'], timeout=15)
        if listing.returncode or listing.stdout.strip():
            fail('build_container_cleanup_not_absent')
        return {'status': 'complete', 'container_name': name,
                'container_id': journal.get('container_id'), 'absent': True}
    except (BuildError, OSError, subprocess.TimeoutExpired) as error:
        return {'status': 'unresolved', 'container_name': name,
                'container_id': journal.get('container_id'), 'code': str(error)}


def output_command(identifier: str, path: str) -> list[str]:
    prefixes = []
    current = PurePosixPath('/workspace/project')
    for part in PurePosixPath(path).parts:
        current = current / part
        prefixes.append('test ! -L ' + shlex.quote(str(current)))
    target = shlex.quote(str(current))
    script = ' && '.join([*prefixes, 'test -f ' + target,
                          'if test -x ' + target + '; then printf "1\\n"; '
                          'else printf "0\\n"; fi',
                          'head -c ' + str(MAX_OUTPUT_BYTES + 1) + ' ' + target])
    return ['container', 'exec', identifier, 'sh', '-c', script]


def setup_build(run_root: Path, approval_path: Path, catalog_path: Path) -> dict:
    setup = frozen_setup(run_root)
    controls, recipe, plan = (setup[key] for key in ('controls', 'recipe', 'plan'))
    catalog = catalog_snapshot(catalog_path, recipe)
    authority = verify_authority(setup, approval_path, catalog)
    amendment = authority['scope_amendment']
    with build_lock(controls):
        journal_dir = controls / 'setup-build'
        if journal_dir.exists() or (controls / 'setup-checked').exists():
            fail('build_already_dispatched')
        inspect_image(setup, amendment['image_id'])
        journal_dir.mkdir(mode=0o700)
        shutil.copy2(approval_path, journal_dir / 'authority.json')
        (journal_dir / 'authority.json').chmod(0o600)
        nonce = uuid.uuid4().hex
        name = 'lrh-setup-build-' + nonce[:20]
        journal = {'kind': 'native-setup-build-journal-v1', 'status': 'pending',
                   'nonce': nonce, 'container_name': name, 'container_id': None,
                   'authority_sha256': sha(journal_dir / 'authority.json'),
                   'catalog_tree_sha256': catalog['tree']['tree_sha256'],
                   'events': [], 'pending_action': 'container_create', 'cleanup': None}
        journal_path = journal_dir / 'journal.json'
        write_json(journal_path, journal, once=True)
        stage = journal_dir / 'stage'
        stage.mkdir(mode=0o700)
        problem = None
        deadline = time.monotonic() + amendment['duration_seconds']
        def remaining(maximum: int) -> int:
            seconds = int(deadline - time.monotonic())
            if seconds < 1:
                fail('build_duration_exhausted')
            return min(maximum, seconds)
        try:
            create = ['container', 'create', '--name', name, '--pull', 'never',
                      '--label', 'io.llm-redteam-harness.setup-build=' + nonce,
                      '--network', 'none', '--read-only', '--cap-drop', 'ALL',
                      '--security-opt', 'no-new-privileges=true',
                      '--pids-limit', '64', '--memory', str(amendment['memory_bytes']),
                      '--cpus', '1', '--entrypoint', 'sh',
                      '--user', f'{os.getuid()}:{os.getgid()}',
                      '--tmpfs', '/workspace:rw,nosuid,nodev,size=' + str(amendment['max_workspace_bytes']),
                      '--tmpfs', '/tmp:rw,nosuid,nodev,size=8388608',
                      '--mount', 'type=bind,src=' + str(setup['root'] / 'original') + ',dst=/source,readonly',
                      '--mount', 'type=bind,src=' + str(catalog['root'] / 'payload') + ',dst=/deps,readonly',
                      amendment['image_id'], '-c', 'while :; do sleep 3600; done']
            created = event_call(setup, journal_path, journal, 'container_create', create,
                                 timeout=remaining(30))
            if created.returncode or not re.fullmatch(rb'[0-9a-f]{64}\s*', created.stdout):
                fail('build_container_create_failed')
            journal['container_id'] = created.stdout.decode().strip()
            write_json(journal_path, journal)
            started = event_call(setup, journal_path, journal, 'container_start',
                                 ['container', 'start', journal['container_id']],
                                 timeout=remaining(30))
            if started.returncode:
                fail('build_container_start_failed')
            info = inspect_container(setup, journal['container_id'])
            mounts = info.get('Mounts') or []
            mounted = {row.get('Destination'): row for row in mounts}
            host = info.get('HostConfig') or {}
            if (info.get('Id') != journal['container_id']
                    or host.get('NetworkMode') != 'none'
                    or host.get('ReadonlyRootfs') is not True
                    or host.get('Tmpfs', {}).get('/workspace') !=
                    'rw,nosuid,nodev,size=' + str(amendment['max_workspace_bytes'])
                    or set(mounted) != {'/source', '/deps'}
                    or any(row.get('Type') != 'bind' or row.get('RW') is not False
                           or row.get('Source') != str(expected)
                           for destination, expected in (('/source', setup['root'] / 'original'),
                                                         ('/deps', catalog['root'] / 'payload'))
                           for row in (mounted[destination],))):
                fail('build_container_boundary_mismatch')
            identifier = journal['container_id']
            copied = event_call(setup, journal_path, journal, 'source_copy',
                                ['container', 'exec', identifier, 'sh', '-c',
                                 'mkdir -p /workspace/project && cp -R /source/. /workspace/project/'],
                                timeout=remaining(30))
            if copied.returncode:
                fail('build_source_copy_failed')
            source_readback = stage / 'source-readback'
            source_readback.mkdir(mode=0o700)
            read = event_call(setup, journal_path, journal, 'source_readback',
                              ['cp', identifier + ':/source/.', str(source_readback)],
                              timeout=remaining(30))
            original_modes = source_modes(setup['root'] / 'original', plan['source_sha256'])
            if (read.returncode or nr._inventory(source_readback, max_files=nr.SETUP_SOURCE_MAX_FILES,
                                                 max_bytes=nr.SETUP_SOURCE_MAX_BYTES) != plan['source_sha256']
                    or source_modes(source_readback, plan['source_sha256']) != original_modes):
                fail('build_mounted_source_mismatch')
            dependency_readback = stage / 'dependency-readback'
            dependency_readback.mkdir(mode=0o700)
            read = event_call(setup, journal_path, journal, 'dependency_readback',
                              ['cp', identifier + ':/deps/.', str(dependency_readback)],
                              timeout=remaining(30))
            dependency_hashes = nr._inventory(dependency_readback, max_files=10000,
                                               max_bytes=MAX_CATALOG_BYTES)
            if (read.returncode or set(dependency_hashes) != set(catalog['selected'])
                    or any(dependency_hashes[name] != value['sha256'] or
                           stat.S_IMODE((dependency_readback / name).stat().st_mode) != value['mode']
                           for name, value in catalog['selected'].items())):
                fail('build_mounted_dependency_mismatch')
            shutil.rmtree(source_readback)
            shutil.rmtree(dependency_readback)
            base = ['container', 'exec', '-w', '/workspace/project', identifier,
                    'env', '-i', 'PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
                    'HOME=/tmp', 'TMPDIR=/tmp']
            version = event_call(setup, journal_path, journal, 'runtime_version',
                                 base + recipe['runtime']['version_command'],
                                 timeout=remaining(15))
            if (version.returncode or version.stdout.decode(errors='replace').strip()
                    != recipe['runtime']['version_stdout']):
                fail('build_runtime_version_mismatch')
            dependency = event_call(setup, journal_path, journal, 'dependency_probe',
                                    base + recipe['runtime']['dependency_command'],
                                    timeout=remaining(30))
            if dependency.returncode or dependency.stdout.strip():
                fail('build_offline_dependency_closure_unavailable')
            built = event_call(setup, journal_path, journal, 'target_build',
                               base + recipe['build_command'],
                               timeout=remaining(amendment['duration_seconds']))
            if built.returncode:
                fail('build_command_failed')
            outputs = {}
            for path in amendment['outputs']:
                command = output_command(identifier, path)
                first = event_call(setup, journal_path, journal, 'output_read_1:' + path,
                                   command, timeout=remaining(30), max_output=MAX_OUTPUT_BYTES + 3)
                second = event_call(setup, journal_path, journal, 'output_read_2:' + path,
                                    command, timeout=remaining(30), max_output=MAX_OUTPUT_BYTES + 3)
                mode_flag, content = first.stdout[:2], first.stdout[2:]
                if (first.returncode or second.returncode or first.stdout != second.stdout
                        or mode_flag not in (b'0\n', b'1\n') or len(content) > MAX_OUTPUT_BYTES):
                    fail('build_output_missing')
                destination = stage / 'output' / path
                destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(descriptor, 'wb') as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                destination.chmod(0o700 if mode_flag == b'1\n' else 0o600)
                outputs[path] = {'sha256': sha(destination),
                                 'mode': stat.S_IMODE(destination.stat().st_mode)}
            nr._verify_inventory(setup['root'] / 'original', plan['source_sha256'], setup_limit=True)
            current_catalog = catalog_snapshot(catalog_path, recipe)
            if current_catalog['tree'] != catalog['tree']:
                fail('build_catalog_changed_during_execution')
            dependencies = {}
            (stage / 'dependencies').mkdir(mode=0o700)
            shutil.copyfile(catalog['root'] / 'catalog.json', stage / 'dependencies/catalog.json')
            (stage / 'dependencies/catalog.json').chmod(0o600)
            for name, expected in catalog['selected'].items():
                destination = stage / 'dependencies/payload' / name
                destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                shutil.copyfile(catalog['root'] / 'payload' / name, destination)
                destination.chmod(expected['mode'])
                if sha(destination) != expected['sha256']:
                    fail('build_dependency_copy_changed')
                dependencies[name] = expected
            checked_catalog = catalog_snapshot(stage / 'dependencies', recipe)
            if checked_catalog['tree'] != catalog['tree']:
                fail('build_dependency_archive_changed')
        except (BuildError, nr.NativeResearchError, OSError, subprocess.TimeoutExpired) as error:
            problem = str(error)
        cleanup = cleanup_container(setup, journal_path, journal)
        journal['cleanup'] = cleanup
        if problem or cleanup['status'] != 'complete':
            journal['status'] = 'unknown_effect' if any(
                row['status'] in ('pending', 'unknown_effect') for row in journal['events']) else 'blocked'
            journal['code'] = problem or 'build_cleanup_incomplete'
            write_json(journal_path, journal)
            shutil.rmtree(stage, ignore_errors=True)
            result = {'kind': 'native-setup-build-blocked-v1', 'status': journal['status'],
                      'code': journal['code'], 'journal_sha256': sha(journal_path),
                      'cleanup': cleanup, 'security_result': None}
            write_json(journal_dir / 'blocked.json', result, once=True)
            return result
        checked = controls / 'setup-checked'
        receipt = {'kind': 'native-setup-checked-v1', 'status': 'ready',
                   'source_manifest_sha256': plan['source_manifest_sha256'],
                   'source_mode_sha256': digest(original_modes),
                   'setup_plan_sha256': sha(setup['root'] / 'plan.json'),
                   'setup_scope_sha256': plan['scope_sha256'],
                   'goal_sha256': plan['brief_sha256'],
                   'setup_approval_sha256': sha(controls / 'approval.json'),
                   'setup_output_receipt_sha256': sha(controls / 'setup-output/receipt.json'),
                   'setup_chain_sha256': setup['chain']['chain_sha256'],
                   'cumulative_setup_used': setup['chain']['cumulative_used'],
                   'original_setup_limits': setup['chain']['original_limits'],
                   'build_authority_sha256': sha(journal_dir / 'authority.json'),
                   'build_scope_amendment_sha256': digest({key: value for key, value in
                       authority['scope_amendment'].items() if key != 'operator_signature'}),
                   'build_approval_sha256': digest({key: value for key, value in
                       authority['approval'].items() if key != 'operator_signature'}),
                   'recipe_sha256': sha(controls / 'setup-output/recipe.json'),
                   'threat_model_sha256': sha(controls / 'setup-output/THREAT_MODEL.md'),
                   'image_id': amendment['image_id'], 'platform': plan['platform'],
                   'dependency_catalog_tree_sha256': catalog['tree']['tree_sha256'],
                   'dependencies': dependencies, 'outputs': outputs,
                   'effect_class': EFFECT_CLASS, 'network_class': NETWORK_CLASS,
                   'setup_allowance_sha256': digest(setup['allowance']),
                   'remaining_setup_allowance': {
                       'connections': (setup['chain']['original_limits']['max_connections']
                                       - setup['chain']['cumulative_used']['connections']),
                       'bytes': (setup['chain']['original_limits']['max_bytes']
                                 - setup['chain']['cumulative_used']['bytes']),
                       'absolute_deadline': setup['chain']['absolute_deadline']},
                   'cleanup': cleanup, 'security_result': None,
                   'target_service_executed': False}
        write_json(stage / 'receipt.json', receipt, once=True)
        os.rename(stage, checked)
        journal['status'] = 'ready'
        write_json(journal_path, journal)
        return {'kind': receipt['kind'], 'status': 'ready',
                'receipt_path': str(checked / 'receipt.json'),
                'receipt_sha256': sha(checked / 'receipt.json'), 'cleanup': cleanup}


def status(run_root: Path) -> dict:
    root = nr._private_root(run_root)
    controls = root / 'controls'
    path = controls / 'setup-build/journal.json'
    if not path.exists():
        return {'kind': 'native-setup-build-status-v1', 'status': 'not_dispatched'}
    journal = read_json(path)
    pending = [row['action'] for row in journal.get('events', [])
               if row.get('status') in ('pending', 'unknown_effect')]
    if journal.get('pending_action') and journal['pending_action'] not in pending:
        pending.append(journal['pending_action'])
    checked = controls / 'setup-checked/receipt.json'
    result = {'kind': 'native-setup-build-status-v1',
              'status': ('blocked_reconciled' if journal['status'] == 'blocked_reconciled' else
                         'unknown_effect' if pending else journal['status']),
              'pending_actions': pending, 'container_name': journal.get('container_name'),
              'container_id': journal.get('container_id'),
              'cleanup': journal.get('cleanup'), 'journal_sha256': sha(path)}
    if checked.exists():
        result['checked_receipt_sha256'] = sha(checked)
    reconciled = controls / 'setup-build/reconciliation.json'
    if reconciled.exists():
        result['reconciliation_sha256'] = sha(reconciled)
    return result


def reconcile(run_root: Path) -> dict:
    """Clean an interrupted build's exact container and retain its uncertain action."""
    setup = frozen_setup(run_root)
    controls = setup['controls']
    with build_lock(controls):
        directory = controls / 'setup-build'
        journal_path = directory / 'journal.json'
        journal = read_json(journal_path)
        authority_path = directory / 'authority.json'
        nonce, name = journal.get('nonce'), journal.get('container_name')
        events = journal.get('events')
        pending = [row.get('action') for row in events if row.get('status') in
                   ('pending', 'unknown_effect')] if isinstance(events, list) else []
        if (journal.get('kind') != 'native-setup-build-journal-v1'
                or journal.get('status') not in ('pending', 'unknown_effect', 'blocked',
                                                 'blocked_reconciled', 'cleanup_unresolved')
                or not isinstance(nonce, str) or not re.fullmatch(r'[0-9a-f]{32}', nonce)
                or name != 'lrh-setup-build-' + nonce[:20]
                or journal.get('authority_sha256') != sha(nr._file(authority_path, private=True))
                or not isinstance(events, list)
                or any(not isinstance(row, dict) or not isinstance(row.get('action'), str)
                       for row in events)
                or journal.get('pending_action') not in (None, *pending)
                or (journal.get('container_id') is not None and
                    not re.fullmatch(r'[0-9a-f]{64}', str(journal['container_id'])))):
            fail('build_reconciliation_journal_invalid')
        receipt_path = directory / 'reconciliation.json'
        if receipt_path.exists():
            receipt = read_json(receipt_path)
            if receipt.get('journal_sha256') != sha(journal_path):
                fail('build_reconciliation_changed')
            if inspect_container(setup, name) is not None:
                fail('build_reconciliation_resource_reappeared')
            return receipt
        cleanup = cleanup_container(setup, journal_path, journal)
        journal['cleanup'] = cleanup
        journal['status'] = ('blocked_reconciled' if cleanup['status'] == 'complete'
                             else 'cleanup_unresolved')
        write_json(journal_path, journal)
        authority = read_json(authority_path)
        approval = authority.get('approval') if isinstance(authority, dict) else None
        duration = approval.get('duration_seconds') if isinstance(approval, dict) else None
        if type(duration) is not int or not 5 <= duration <= 600:
            fail('build_reconciliation_authority_invalid')
        receipt = {'kind': 'native-setup-build-reconciliation-v1',
                   'status': journal['status'], 'pending_action': journal.get('pending_action'),
                   'uncertain_actions': pending, 'cleanup': cleanup,
                   'journal_sha256': sha(journal_path),
                   'build_duration_charged_upper_bound_seconds': duration,
                   'setup_cumulative_used': setup['chain']['cumulative_used'],
                   'retry_requires_new_approval': True, 'security_result': None}
        write_json(receipt_path, receipt, once=True)
        return receipt


def verify_checked(run_root: Path, *, require_fresh: bool = True) -> dict:
    """Read-only recheck for a later research-plan preparer.

    Returns the frozen, host-owned paths and content only after checking the
    signed build authority, stopped setup chain, journal, cleanup, and all
    checked bytes. A caller must still obtain its own research authority.
    """
    setup = frozen_setup(run_root)
    controls, recipe, chain = (setup[key] for key in ('controls', 'recipe', 'chain'))
    checked = controls / 'setup-checked'
    receipt = read_json(checked / 'receipt.json')
    journal_dir = controls / 'setup-build'
    journal = read_json(journal_dir / 'journal.json')
    archived_authority = journal_dir / 'authority.json'
    catalog = catalog_snapshot(checked / 'dependencies', recipe)
    authority = verify_authority(setup, archived_authority, catalog,
                                 historical=not require_fresh)
    amendment = authority['scope_amendment']
    approval = authority['approval']
    if require_fresh:
        check_setup_fresh(setup)
    if (journal.get('kind') != 'native-setup-build-journal-v1'
            or journal.get('status') != 'ready'
            or journal.get('authority_sha256') != sha(archived_authority)
            or journal.get('catalog_tree_sha256') != catalog['tree']['tree_sha256']
            or not isinstance(journal.get('events'), list)
            or not journal['events']
            or any(row.get('status') != 'acknowledged' for row in journal['events'])
            or journal.get('pending_action') is not None
            or journal.get('cleanup', {}).get('status') != 'complete'):
        fail('checked_build_journal_invalid')
    actions = [row['action'] for row in journal['events']]
    if (actions.count('container_create') != 1 or actions.count('container_start') != 1
            or actions.count('source_copy') != 1 or actions.count('source_readback') != 1
            or actions.count('dependency_readback') != 1 or actions.count('runtime_version') != 1
            or actions.count('dependency_probe') != 1 or actions.count('target_build') != 1
            or actions.count('container_remove') != 1
            or any(actions.count('output_read_1:' + path) != 1 or
                   actions.count('output_read_2:' + path) != 1 for path in amendment['outputs'])):
        fail('checked_build_action_sequence_invalid')
    if inspect_container(setup, journal['container_name']) is not None:
        fail('checked_build_container_still_present')
    output_dir = checked / 'output'
    output_hashes = nr._inventory(output_dir, max_files=64, max_bytes=128 * 1024 * 1024)
    output_inventory = {name: {'sha256': digest,
                               'mode': stat.S_IMODE((output_dir / name).stat(follow_symlinks=False).st_mode)}
                        for name, digest in output_hashes.items()}
    if set(output_inventory) != set(amendment['outputs']):
        fail('checked_output_set_changed')
    expected = {
        'kind': 'native-setup-checked-v1', 'status': 'ready',
        'source_manifest_sha256': setup['plan']['source_manifest_sha256'],
        'source_mode_sha256': digest(source_modes(setup['root'] / 'original',
                                                  setup['plan']['source_sha256'])),
        'setup_plan_sha256': sha(setup['root'] / 'plan.json'),
        'setup_scope_sha256': setup['plan']['scope_sha256'],
        'goal_sha256': setup['plan']['brief_sha256'],
        'setup_approval_sha256': sha(controls / 'approval.json'),
        'setup_output_receipt_sha256': sha(controls / 'setup-output/receipt.json'),
        'setup_chain_sha256': chain['chain_sha256'],
        'cumulative_setup_used': chain['cumulative_used'],
        'original_setup_limits': chain['original_limits'],
        'build_authority_sha256': sha(archived_authority),
        'build_scope_amendment_sha256': digest({key: value for key, value in
            amendment.items() if key != 'operator_signature'}),
        'build_approval_sha256': digest({key: value for key, value in
            approval.items() if key != 'operator_signature'}),
        'recipe_sha256': sha(controls / 'setup-output/recipe.json'),
        'threat_model_sha256': sha(controls / 'setup-output/THREAT_MODEL.md'),
        'image_id': amendment['image_id'], 'platform': setup['plan']['platform'],
        'dependency_catalog_tree_sha256': catalog['tree']['tree_sha256'],
        'dependencies': catalog['selected'], 'outputs': output_inventory,
        'effect_class': EFFECT_CLASS, 'network_class': NETWORK_CLASS,
        'setup_allowance_sha256': digest(setup['allowance']),
        'remaining_setup_allowance': {
            'connections': (chain['original_limits']['max_connections']
                            - chain['cumulative_used']['connections']),
            'bytes': (chain['original_limits']['max_bytes']
                      - chain['cumulative_used']['bytes']),
            'absolute_deadline': chain['absolute_deadline']},
        'cleanup': journal['cleanup'], 'security_result': None,
        'target_service_executed': False}
    if receipt != expected:
        fail('checked_receipt_or_bytes_changed')
    return {'receipt': receipt, 'recipe': recipe,
            'source_dir': str(setup['root'] / 'original'),
            'output_dir': str(output_dir),
            'dependency_dir': str(checked / 'dependencies/payload'),
            'checked_root': str(checked)}


def main() -> int:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    template_command = commands.add_parser('setup-build-approval-template')
    template_command.add_argument('--run-root', type=Path, required=True)
    template_command.add_argument('--image-id', required=True)
    template_command.add_argument('--dependency-catalog', type=Path, required=True)
    template_command.add_argument('--max-workspace-bytes', type=int, required=True)
    template_command.add_argument('--memory-bytes', type=int, required=True)
    template_command.add_argument('--duration-seconds', type=int, required=True)
    template_command.add_argument('--output-path', action='append', required=True)
    template_command.add_argument('--approved-at', required=True)
    template_command.add_argument('--expires-at', required=True)
    build_command = commands.add_parser('setup-build')
    build_command.add_argument('--run-root', type=Path, required=True)
    build_command.add_argument('--approval', type=Path, required=True)
    build_command.add_argument('--dependency-catalog', type=Path, required=True)
    status_command = commands.add_parser('setup-build-status')
    status_command.add_argument('--run-root', type=Path, required=True)
    status_command.add_argument('--verify-checked', action='store_true')
    status_command.add_argument('--historical', action='store_true')
    reconcile_command = commands.add_parser('setup-build-reconcile')
    reconcile_command.add_argument('--run-root', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'setup-build-approval-template':
            result = template(args.run_root, args.image_id, args.dependency_catalog,
                              args.max_workspace_bytes, args.memory_bytes,
                              args.duration_seconds, args.output_path,
                              args.approved_at, args.expires_at)
        elif args.command == 'setup-build':
            result = setup_build(args.run_root, args.approval, args.dependency_catalog)
        elif args.command == 'setup-build-reconcile':
            result = reconcile(args.run_root)
        else:
            result = (verify_checked(args.run_root, require_fresh=not args.historical)
                      if args.verify_checked
                      else status(args.run_root))
    except (BuildError, nr.NativeResearchError, RecordError, OSError, ValueError) as error:
        print(json.dumps({'status': 'refused', 'code': str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get('status') not in ('blocked', 'unknown_effect', 'cleanup_unresolved') else 2


if __name__ == '__main__':
    raise SystemExit(main())
