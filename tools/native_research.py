#!/usr/bin/env python3
"""Direct, bounded OpenCode research over owned source or an application service.

`prepare` is provider-free. `start` is a foreground owner; a human-supplied,
run-bound approval is required before it can create a live route. `resume` and
`stop` are separate CLI calls while that owner is alive. This is a launch
adapter, not a finding oracle or a provider billing authority.
"""

from __future__ import annotations

import argparse
import base64
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import importlib.util
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import select
import shutil
import socket
import sqlite3
import ssl
import stat
import subprocess
import sys
import tempfile
import threading
import time
import uuid

from engagement_records import RecordError, canonical_json_bytes
from operator_signature import verify_operator_signature_bytes, verify_embedded_operator_signature


ROOT = Path(__file__).resolve().parents[1]
RESEARCH_WORKFLOW = ROOT / 'engine/native-research-workflow.md'
SETUP_WORKFLOW = ROOT / 'engine/native-setup-workflow.md'
CONTROL_SHA = {
    'experiments/native-network-preflight/v2_connect.py': '7f031921c0cd363fec9f7bd45cd4794bd0751df3c54008acde167cf1535698c3',
    'experiments/native-network-preflight/v2-effect-windows/native_run.py': '759fb38b0df5557b290989bc9b42eb603d5e7631511d4ded2f0646f5decf492f',
    'experiments/native-network-preflight/v2-effect-windows/_native_stop_owner.py': 'dca06e8f2472dda294f6551dc16a31791338552a318ee26a1d05146ef148f175',
    'experiments/native-network-preflight/v2-effect-windows/producer_stop.py': '94d7d3db11c1215ac6c4adbcf2a7fa6758e078faa5681ed442230835198a6cdd',
    'experiments/native-review-qualification/fresh_review.py': 'c026cc99430d7108df48bf0e8803d1f7aac8687031a13b8e785c90a1ba6cb00c',
    'tools/docker_session_runtime.py': '9e8d36eed18387d4106d02a62b3ef7489845cb6da9ccbf57256c3a4432f47651',
    'tools/native_kanboard_origin_gate.py': 'bb59962e022e59cd6994149c2a2eaf1d26d0bf7b3963c41289520df13ff0658e',
    'tools/native_effect_recovery.py': 'a9a000be18229660f779912ec625ae753233f0ed78107265db9eeb8bf021db7c',
}
CAPTURE_FILES = {
    'evals/native-qualification/kanboard_native_capture.py': 'fdd256cf0a7a289d1fd446af51018ac379607601d701e97045f9c7364dfe0f79',
    'evals/native-qualification/smoke/kanboard_effect_probe.php': '5484f9ac40a710ea5eb5492bc13b712211e5f1cbcde934e2548e946c8fa0379d',
    'evals/native-qualification/smoke/kanboard_effect_collector.php': '991d727e36b0c1fedc9898f4a773282ce7f062f8f00de4ae5dd05d2256b9e3b5',
    'evals/native-qualification/smoke/kanboard_role_broker.php': '2ee3d3806825f210071b73f53ade076e471f97237b81a0a66cc00632e6e97c8d',
}
CAPTURE_SOURCE_SHA = '056280086b353347075f0352b5826bd20ef7328854e7283e4c5cd71d7e57f839'
CAPTURE_CONTROLLER_SHA = '6df47c20fe6b1963bd14a86bc3cbd554fbcea9f622a23f67af115a854811aad6'
T01_CAPTURE_FILES = {
    'evals/native-qualification/kanboard_native_capture.py': 'fdd256cf0a7a289d1fd446af51018ac379607601d701e97045f9c7364dfe0f79',
    'evals/native-qualification/smoke/t01_jsonrpc_broker.php': '11d343c985b06fb49f76a47e99166d40e22d3d8046188faf920ef3bb8be82458',
    'evals/native-qualification/smoke/t01_receipt_collector.php': 'fdc0f2fbd16e205fe76d6706d5c5e1861d67b368093de4723ec8e4894a80eaa7',
    'tools/t01_semantic_reconcile.py': 'efbfa97dbc9d9f1e6acdd74f40c66e5cd98e343baf8bf713760198c8f84a613a',
}
T01_SOURCE_SHA = '5d49c3f485f555f3118b0afb983997e29a5ddaad4b0ed6f9cf19d855c2e4f884'
T01_MIDDLEWARE_SHA = 'b58767b343bcbfaa1d9ae461cf39dc72e7f489ba3899dea2246541153bdd3c4f'
T01_BRIEF_SHA = 'cfa72ecb1279d292cd915c4c8b7c9405095405e422d1bf96e211db809b139c95'
T01_WORKSPACE_BRIEF_SHA = '64b2b256fdc3285237bdf5c69f478ad680121e4a30284e1090819cff05b9cf09'
CAPTURE_TARGETS = ('target', 'review-target-1', 'review-target-2')
SOURCE_EFFECT_ENVELOPE = {
    'kind': 'native-offline-source-effect-v1', 'network': 'none',
    'writable_host_mount': '/target:owned_disposable_copy',
    'readonly_host_mount': '/modules:offline_dependencies',
    'replays': 2, 'assessment': 'reproducibility_only',
}
CHECKED_SOURCE_EFFECT_ENVELOPE = dict(
    SOURCE_EFFECT_ENVELOPE, readonly_host_mount='/deps:offline_dependencies')


def _source_dependency_destination(plan: dict) -> str:
    return '/deps' if 'checked_setup' in plan else '/modules'
ORIGIN_ROLES = {'researcher': 'target', 'resume': 'target',
                'reviewer-1': 'review-target-1', 'reviewer-2': 'review-target-2'}
ORIGIN_SOURCE_FILES = {
    'tools/native_origin/protocol.go': '17b99d8fb6e243470f6a58f1ba0cb931a8f5fff5d8301eaaf4544284061ccf19',
    'tools/native_origin/main_linux.go': '048126cae823ac48fe0684fe569d51c814a5ea82fc7c673692c6acbc96a02be5',
}
ORIGIN_GO_VERSION = 'go1.26.4'
MODEL = 'opencode/deepseek-v4.1-flash-free'
PROVIDER_ROUTE = 'opencode-keyless-free'
PAID_MODEL = 'opencode-go/deepseek-v4.1-flash'
PAID_ROUTE = 'opencode-go'
AUTHORITY = 'opencode.ai:443'
VERSION = 'opencode v2.0.32'
OFFICIAL_IMAGE_ENV = {'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
                      'BUN_RUNTIME_TRANSPILER_CACHE_PATH': '0'}
DEFAULT_LIMITS = {'max_connections': 16, 'max_bytes': 8 * 1024 * 1024, 'duration_seconds': 300}
SETUP_SIGNATURE_NAMESPACE = 'llm-redteam-harness-native-setup-v1'
SETUP_EFFECT_CLASS = 'read-only-original-and-disposable-offline-proposal'
SETUP_NETWORK_CLASS = 'metered-model-relay-only'
SETUP_OUTPUT_FILES = ('recipe.json', 'THREAT_MODEL.md')
SETUP_SOURCE_MAX_BYTES = 128 * 1024 * 1024
SETUP_SOURCE_MAX_FILES = 10000
LABEL = 'io.lrh.native-research'
OWNER_LABEL = 'io.llm-redteam-harness.runtime'
NONCE_LABEL = 'io.llm-redteam-harness.session-nonce'
SESSION_RE = re.compile(r'ses_[A-Za-z0-9]{1,64}\Z')
HEX_RE = re.compile(r'[0-9a-f]{64}\Z')
IMAGE_RE = re.compile(r'sha256:[0-9a-f]{64}\Z')
SENSITIVE_ENV = re.compile(r'(?:TOKEN|SECRET|PASSWORD|API_KEY|ACCESS_KEY|PRIVATE_KEY|AUTHORIZATION|CREDENTIAL)', re.I)
CREDENTIAL_TEXT = re.compile(
    r'(?i)(?:\b(?:authorization|proxy-authorization|cookie|set-cookie|x-api-key)\s*[:=]|'
    r'\b(?:bearer|basic)\s+[A-Za-z0-9+/._=-]{8,}|'
    r'\b(?:password|passwd|api[_-]?key|access[_-]?token|secret)\s*[:=]\s*\S+|'
    r'\blocal_[0-9a-f]{32}\b|-----BEGIN [A-Z ]*PRIVATE KEY-----|'
    r'\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b|'
    r'\b(?:X-Amz-Signature|X-Goog-Signature)=)')
DOCKER_BINARY: Path | None = None
CONFIG = {
    '$schema': 'https://opencode.ai/config.json', 'model': MODEL,
    'update': 'disable', 'share': 'disabled', 'plugins': [],
    'mcp': {'servers': {}}, 'websearch': False,
    'permissions': [
        {'action': '*', 'resource': '*', 'effect': 'deny'},
        *({'action': action, 'resource': '*', 'effect': 'allow'}
          for action in ('read', 'glob', 'grep', 'edit', 'write', 'shell')),
    ],
    'policies': [
        {'action': 'provider.use', 'resource': '*', 'effect': 'deny'},
        {'action': 'provider.use', 'resource': 'opencode', 'effect': 'allow'},
    ],
}


class NativeResearchError(RuntimeError):
    pass


def _model_config(plan: dict) -> dict:
    if (plan.get('provider_authority') != AUTHORITY or
            (plan.get('model'), plan.get('provider_route')) not in
            ((MODEL, PROVIDER_ROUTE), (PAID_MODEL, PAID_ROUTE))):
        _fail('provider_or_model_unqualified')
    config = json.loads(json.dumps(CONFIG))
    if plan.get('setup_only'):
        config['permissions'] = [row for row in config['permissions']
                                 if row.get('action') != 'shell']
    if plan['model'] == PAID_MODEL:
        config['model'] = PAID_MODEL
        config['policies'][-1]['resource'] = PAID_ROUTE
        config['providers'] = {PAID_ROUTE: {'settings': {
            'apiKey': 'native-host-injection',
            'baseURL': 'https://opencode.ai/inference/go/openai/v1'}}}
    return config


def _fail(code: str) -> None:
    raise NativeResearchError(code)


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _file(path: Path, *, private: bool = False) -> Path:
    path = Path(path)
    if not path.is_absolute() or path.is_symlink():
        _fail('absolute_regular_file_required')
    try:
        resolved = path.resolve(strict=True)
        entry = path.stat(follow_symlinks=False)
    except OSError:
        _fail('regular_file_unavailable')
    if (resolved != path or not stat.S_ISREG(entry.st_mode)
            or (private and (entry.st_uid != os.getuid() or entry.st_mode & 0o077))):
        _fail('regular_file_invalid')
    return path


def _private_root(path: Path, *, create: bool = False) -> Path:
    path = Path(path)
    if not path.is_absolute() or path.is_symlink():
        _fail('absolute_private_run_root_required')
    if create:
        if path.exists():
            _fail('run_root_already_exists')
        path.mkdir(mode=0o700, parents=False)
    try:
        entry = path.stat(follow_symlinks=False)
    except OSError:
        _fail('run_root_unavailable')
    if not stat.S_ISDIR(entry.st_mode) or entry.st_uid != os.getuid() or entry.st_mode & 0o077:
        _fail('run_root_permissions')
    return path


def _write_json(path: Path, value: object, *, once: bool = False) -> None:
    data = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    if once:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    else:
        temporary = path.with_name('.' + path.name + '-' + uuid.uuid4().hex)
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_json(path: Path) -> dict:
    path = _file(path, private=True)
    if path.stat().st_size > 1024 * 1024:
        _fail('control_file_oversize')
    def unique_pairs(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError('duplicate key')
            value[key] = item
        return value
    try:
        value = json.loads(path.read_bytes(), object_pairs_hook=unique_pairs)
    except (UnicodeError, ValueError):
        _fail('control_file_invalid')
    if not isinstance(value, dict):
        _fail('control_file_invalid')
    return value


def _setup_scope_challenge(scope_hash: str, engagement_id: str) -> bytes:
    return canonical_json_bytes({'kind': 'native-setup-scope-challenge-v1',
                                 'engagement_id': engagement_id, 'scope_sha256': scope_hash})


def _verify_setup_scope(scope: Path, signature: Path, signers: Path,
                        engagement_id: str, operator_id: str, trusted_fingerprint: str,
                        source_manifest_sha256: str | None, goal_sha256: str,
                        *, allow_expired: bool = False) -> str:
    if (not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', engagement_id)
            or not re.fullmatch(r'[A-Za-z0-9_.@+-]{1,128}', operator_id)
            or not re.fullmatch(r'sha256:[0-9a-f]{64}', trusted_fingerprint)):
        _fail('setup_signer_input_invalid')
    scope = _file(scope, private=True)
    signature = _file(signature, private=True)
    signers = _file(signers, private=True)
    scope_bytes = scope.read_bytes()
    try:
        scope_text = scope_bytes.decode('utf-8')
    except UnicodeError:
        _fail('setup_scope_incomplete')
    if len(scope_bytes) > 256 * 1024:
        _fail('setup_scope_incomplete')
    sections = re.findall(r'^```native-setup-scope-v1\s*\n(.*?)^```\s*$',
                          scope_text, re.MULTILINE | re.DOTALL)
    if len(sections) != 1:
        _fail('setup_scope_incomplete')
    def unique_pairs(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError('duplicate key')
            value[key] = item
        return value
    try:
        boundary = json.loads(sections[0], object_pairs_hook=unique_pairs)
    except ValueError:
        _fail('setup_scope_incomplete')
    required = {'kind', 'engagement_id', 'operator_id', 'source_manifest_sha256',
                'goal_sha256', 'surfaces', 'benign_objectives', 'escalation_ceiling',
                'impact_demo_authorized', 'accounts', 'cleanup', 'effect_class',
                'network_class', 'expires_at'}
    def concrete(value):
        return (isinstance(value, str) and 8 <= len(value.strip()) <= 1000
                and not re.search(r'\b(?:TBD|TODO|unknown|placeholder|n/a)\b|<|>|___', value, re.I)
                and not CREDENTIAL_TEXT.search(value))
    if (not isinstance(boundary, dict) or set(boundary) != required
            or boundary['kind'] != 'native-setup-scope-v1'
            or boundary['engagement_id'] != engagement_id
            or boundary['operator_id'] != operator_id
            or not isinstance(boundary['source_manifest_sha256'], str)
            or not HEX_RE.fullmatch(boundary['source_manifest_sha256'])
            or (source_manifest_sha256 is not None
                and boundary['source_manifest_sha256'] != source_manifest_sha256)
            or boundary['goal_sha256'] != goal_sha256
            or not isinstance(boundary['surfaces'], list)
            or not boundary['surfaces'] or len(boundary['surfaces']) > 16
            or not all(concrete(item) for item in boundary['surfaces'])
            or not isinstance(boundary['benign_objectives'], list)
            or not boundary['benign_objectives'] or len(boundary['benign_objectives']) > 16
            or not all(concrete(item) for item in boundary['benign_objectives'])
            or boundary['escalation_ceiling'] != 'setup_only'
            or boundary['impact_demo_authorized'] is not False
            or not isinstance(boundary['accounts'], list) or len(boundary['accounts']) > 16
            or not all(concrete(item) for item in boundary['accounts'])
            or not concrete(boundary['cleanup'])
            or boundary['effect_class'] != SETUP_EFFECT_CLASS
            or boundary['network_class'] != SETUP_NETWORK_CLASS
            or not isinstance(boundary['expires_at'], str)
            or not re.fullmatch(r'20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z',
                                boundary['expires_at'])):
        _fail('setup_scope_incomplete')
    try:
        expiry = datetime.strptime(boundary['expires_at'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
    except ValueError:
        _fail('setup_scope_incomplete')
    if not allow_expired and datetime.now(timezone.utc) >= expiry:
        _fail('setup_scope_expired')
    try:
        fingerprint = verify_operator_signature_bytes(
            scope_bytes=scope_bytes, operator_id=operator_id,
            challenge_bytes=_setup_scope_challenge(_sha(scope), engagement_id),
            signature_bytes=signature.read_bytes(), allowed_signers_bytes=signers.read_bytes(),
            namespace=SETUP_SIGNATURE_NAMESPACE)
    except (RecordError, OSError):
        _fail('setup_scope_signature_invalid')
    if fingerprint != trusted_fingerprint:
        _fail('setup_scope_signer_untrusted')
    return boundary['source_manifest_sha256']


def _setup_approval(root: Path, plan: dict, approval_path: Path, *,
                    allow_expired: bool = False) -> None:
    approval = _read_json(approval_path)
    if approval.get('monetary_cap_usd') is not None:
        _fail('setup_monetary_cap_unenforceable')
    linked = approval.get('kind') == 'native-setup-approval-v2'
    epoch_path = _controls(root) / 'setup-epoch.json'
    if epoch_path.exists() and not linked:
        _fail('setup_epoch_requires_linked_grant')
    expected = {'kind': 'native-setup-approval-v1',
                'engagement_id': plan['setup_only']['engagement_id'],
                'plan_sha256': (approval.get('plan_sha256') if linked else _sha(root / 'plan.json')),
                'source_manifest_sha256': plan['source_manifest_sha256'],
                'scope_sha256': plan['scope_sha256'], 'brief_sha256': plan['brief_sha256'],
                'image_id': plan['image_id'], 'platform': plan['platform'],
                'model': plan['model'], 'provider_route': plan['provider_route'],
                'provider_authority': plan['provider_authority'],
                'relay_sha256': plan['relay_sha256'],
                'runtime_ca_sha256': plan['runtime_ca_sha256'],
                'effect_class': SETUP_EFFECT_CLASS, 'network_class': SETUP_NETWORK_CLASS,
                'limits': (approval.get('limits') if linked else plan['limits']),
                'max_workspace_bytes': plan['setup_only']['max_workspace_bytes'],
                'monetary_cap_usd': None}
    if linked:
        expected.update(kind='native-setup-approval-v2',
                        initial_run_root=str(approval.get('initial_run_root')),
                        absolute_deadline=approval.get('absolute_deadline'))
    if (any(approval.get(key) != value for key, value in expected.items())
            or set(approval) != set(expected) | {'approved_by', 'approved_at', 'expires_at', 'operator_signature'}):
        _fail('setup_approval_mismatch')
    if (approval.get('approved_by') != plan['setup_only']['operator_id']
            or not all(isinstance(approval.get(key), str) and re.fullmatch(
                r'20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z', approval[key])
                for key in ('approved_at', 'expires_at'))):
        _fail('setup_approval_invalid')
    try:
        approved = datetime.strptime(approval['approved_at'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
        expires = datetime.strptime(approval['expires_at'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
    except ValueError:
        _fail('setup_approval_invalid')
    age = (datetime.now(timezone.utc) - approved).total_seconds()
    if (age < 0 or (not allow_expired and age > 24 * 3600)
            or not approved < expires <= approved + timedelta(hours=24)
            or (not allow_expired and datetime.now(timezone.utc) >= expires)):
        _fail('setup_approval_stale_or_future')
    if linked:
        try:
            deadline = datetime.strptime(approval['absolute_deadline'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
        except (KeyError, TypeError, ValueError):
            _fail('setup_epoch_deadline_invalid')
        if (not _valid_limits(approval['limits']) or not approved < deadline <= expires
                or deadline > approved + timedelta(seconds=approval['limits']['duration_seconds'])
                or (not allow_expired and datetime.now(timezone.utc) >= deadline)):
            _fail('setup_epoch_deadline_expired_or_invalid')
        if not epoch_path.exists() and (approval['initial_run_root'] != str(root)
              or approval['plan_sha256'] != _sha(root / 'plan.json')
              or approval['limits'] != plan['limits']):
            _fail('setup_initial_grant_mismatch')
    unsigned = {key: value for key, value in approval.items() if key != 'operator_signature'}
    controls = _controls(root)
    try:
        fingerprint = verify_embedded_operator_signature(
            proof=approval['operator_signature'],
            scope_bytes=(controls / 'scope.md').read_bytes(),
            operator_id=approval['approved_by'],
            challenge_bytes=canonical_json_bytes(unsigned),
            namespace=SETUP_SIGNATURE_NAMESPACE)
    except (RecordError, OSError):
        _fail('setup_approval_signature_invalid')
    if fingerprint != plan['setup_only']['trusted_fingerprint']:
        _fail('setup_approval_signer_untrusted')
    if linked and epoch_path.exists():
        _verify_setup_epoch_link(root, plan, approval, allow_expired=allow_expired)
    archived = controls / 'approval.json'
    if archived.exists():
        if archived.read_bytes() != approval_path.read_bytes():
            _fail('setup_approval_archive_changed')
    else:
        shutil.copy2(approval_path, archived)
        archived.chmod(0o600)
    receipt = {'kind': 'native-setup-approval-receipt-v1',
               'approval_sha256': _sha(archived), 'signer_fingerprint': fingerprint}
    receipt_path = controls / 'setup-approval-receipt.json'
    if receipt_path.exists():
        if _read_json(receipt_path) != receipt:
            _fail('setup_approval_receipt_changed')
    else:
        _write_json(receipt_path, receipt, once=True)


def setup_approval_template(run_root: Path, approved_at: str, expires_at: str, *,
                            linked_epochs: bool = False, absolute_deadline: str | None = None) -> dict:
    root = _private_root(run_root)
    plan = _verified_plan(root, pristine=True)
    if ('setup_only' not in plan or (_controls(root) / 'resources.json').exists()
            or (_controls(root) / 'setup-epoch.json').exists()):
        _fail('setup_template_unavailable')
    if bool(linked_epochs) != bool(absolute_deadline):
        _fail('setup_epoch_template_deadline_required')
    result = {'kind': 'native-setup-approval-v1',
            'engagement_id': plan['setup_only']['engagement_id'],
            'plan_sha256': _sha(root / 'plan.json'),
            'source_manifest_sha256': plan['source_manifest_sha256'],
            'scope_sha256': plan['scope_sha256'], 'brief_sha256': plan['brief_sha256'],
            'image_id': plan['image_id'], 'platform': plan['platform'],
            'model': plan['model'], 'provider_route': plan['provider_route'],
            'provider_authority': plan['provider_authority'],
            'relay_sha256': plan['relay_sha256'],
            'runtime_ca_sha256': plan['runtime_ca_sha256'],
            'effect_class': SETUP_EFFECT_CLASS, 'network_class': SETUP_NETWORK_CLASS,
            'limits': plan['limits'],
            'max_workspace_bytes': plan['setup_only']['max_workspace_bytes'],
            'monetary_cap_usd': None,
            'approved_by': plan['setup_only']['operator_id'],
            'approved_at': approved_at, 'expires_at': expires_at}
    if linked_epochs:
        result.update(kind='native-setup-approval-v2', initial_run_root=str(root),
                      absolute_deadline=absolute_deadline)
    return result


def setup_source_manifest(source: Path) -> dict:
    source = Path(source)
    if not source.is_absolute() or source.is_symlink() or not source.is_dir():
        _fail('source_directory_invalid')
    inventory = _inventory(source, max_files=SETUP_SOURCE_MAX_FILES,
                           max_bytes=SETUP_SOURCE_MAX_BYTES)
    return {'kind': 'native-setup-source-manifest-v1',
            'source_manifest_sha256': hashlib.sha256(
                json.dumps(inventory, sort_keys=True).encode()).hexdigest(),
            'source_files': len(inventory), 'source_sha256': inventory}


def _inventory(directory: Path, *, max_files: int | None = None,
               max_bytes: int | None = None) -> dict[str, str]:
    if not directory.is_dir() or directory.is_symlink():
        _fail('source_directory_invalid')
    result = {}
    total_bytes = 0
    for path in directory.rglob('*'):
        relative = path.relative_to(directory)
        if '.git' in relative.parts or path.is_symlink():
            _fail('source_history_or_symlink_forbidden')
        if '.opencode' in relative.parts or relative.as_posix() in ('opencode.json', 'target.json'):
            _fail('source_reserved_runtime_path_forbidden')
        entry = path.stat(follow_symlinks=False)
        if stat.S_ISDIR(entry.st_mode):
            continue
        if not stat.S_ISREG(entry.st_mode):
            _fail('source_special_file_forbidden')
        total_bytes += entry.st_size
        if ((max_files is not None and len(result) >= max_files)
                or (max_bytes is not None and total_bytes > max_bytes)):
            _fail('setup_source_limit_exceeded')
        result[relative.as_posix()] = _sha(path)
    if not result:
        _fail('source_empty')
    return result


def _verify_inventory(directory: Path, expected: dict[str, str], *,
                      setup_limit: bool = False) -> None:
    observed = (_inventory(directory, max_files=SETUP_SOURCE_MAX_FILES,
                           max_bytes=SETUP_SOURCE_MAX_BYTES) if setup_limit else _inventory(directory))
    if observed != expected:
        _fail('source_pin_mismatch')


def _checked_archive_manifest(directory: Path) -> dict:
    inventory = _inventory(directory, max_files=11000, max_bytes=320 * 1024 * 1024)
    entries = {}
    total = 0
    for relative, digest in inventory.items():
        path = directory / relative
        entry = path.stat(follow_symlinks=False)
        total += entry.st_size
        entries[relative] = {'sha256': digest, 'mode': stat.S_IMODE(entry.st_mode)}
    return {'files': len(entries), 'bytes': total,
            'sha256': hashlib.sha256(canonical_json_bytes(entries)).hexdigest()}


def _copy_checked_setup(root: Path, checked: dict, setup_root: Path) -> dict:
    """Archive the verified package before the first research plan is sealed."""
    controls = _controls(root)
    archive = controls / 'checked-setup'
    archive.mkdir(mode=0o700)
    shutil.copytree(Path(checked['checked_root']), archive / 'package')
    source_controls = setup_root / 'controls'
    frozen = source_controls / 'setup-output'
    proposal = _read_json(frozen / 'receipt.json')
    trace = source_controls / 'dispatch' / (proposal['dispatch_id'] + '.trace.json')
    for source, name in ((setup_root / 'plan.json', 'setup-plan.json'),
                         (source_controls / 'scope.md', 'setup-scope.md'),
                         (source_controls / 'approval.json', 'setup-approval.json'),
                         (source_controls / 'setup-build/authority.json', 'build-authority.json'),
                         (frozen / 'receipt.json', 'setup-output-receipt.json'),
                         (frozen / 'recipe.json', 'recipe.json'),
                         (frozen / 'THREAT_MODEL.md', 'THREAT_MODEL.md'),
                         (trace, 'setup-trace.json')):
        shutil.copy2(_file(source, private=True), archive / name)
        (archive / name).chmod(0o600)
    research = controls / 'research/checked-setup'
    research.mkdir(mode=0o700)
    for source, name in ((archive / 'THREAT_MODEL.md', 'INITIAL_THREAT_MODEL.md'),
                         (archive / 'setup-trace.json', 'SETUP_TRACE.json')):
        shutil.copy2(source, research / name)
        (research / name).chmod(0o600)
    receipt = checked['receipt']
    recipe = checked['recipe']
    if (_read_json(archive / 'package/receipt.json') != receipt
            or _read_json(archive / 'recipe.json') != recipe
            or receipt.get('source_manifest_sha256') != _plan_source_manifest(root)
            or receipt.get('source_mode_sha256') != _source_mode_digest(root / 'original')
            or receipt.get('goal_sha256') != _sha(controls / 'BRIEF.md')):
        _fail('checked_setup_source_or_goal_mismatch')
    return {'kind': 'native-checked-setup-transition-v1',
            'archive': _checked_archive_manifest(archive),
            'checked_receipt_sha256': _sha(archive / 'package/receipt.json'),
            'setup_output_receipt_sha256': _sha(archive / 'setup-output-receipt.json'),
            'recipe_sha256': _sha(archive / 'recipe.json'),
            'initial_threat_model_sha256': _sha(archive / 'THREAT_MODEL.md'),
            'setup_trace_sha256': _sha(archive / 'setup-trace.json'),
            'build_authority_sha256': _sha(archive / 'build-authority.json'),
            'setup_chain_sha256': receipt['setup_chain_sha256'],
            'cumulative_setup_used': receipt['cumulative_setup_used'],
            'source_manifest_sha256': receipt['source_manifest_sha256'],
            'source_mode_sha256': receipt['source_mode_sha256'],
            'goal_sha256': receipt['goal_sha256'],
            'target_image_id': receipt['image_id'],
            'platform': receipt['platform'],
            'runtime_sha256': hashlib.sha256(canonical_json_bytes(recipe['runtime'])).hexdigest(),
            'build_command_sha256': hashlib.sha256(canonical_json_bytes(recipe['build_command'])).hexdigest()}


def _plan_source_manifest(root: Path) -> str:
    inventory = _inventory(root / 'original')
    return hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest()


def _file_modes(directory: Path, inventory: dict[str, str]) -> dict[str, int]:
    return {name: stat.S_IMODE((directory / name).stat(follow_symlinks=False).st_mode)
            for name in inventory}


def _checked_files(directory: Path) -> dict[str, dict[str, int | str]]:
    if not directory.exists():
        return {}
    if directory.is_symlink() or not directory.is_dir():
        _fail('checked_setup_directory_invalid')
    if not any(directory.iterdir()):
        return {}
    inventory = _inventory(directory)
    modes = _file_modes(directory, inventory)
    return {name: {'sha256': digest, 'mode': modes[name]}
            for name, digest in inventory.items()}


def _source_mode_digest(directory: Path) -> str:
    inventory = _inventory(directory)
    return hashlib.sha256(canonical_json_bytes(_file_modes(directory, inventory))).hexdigest()


def _verify_checked_setup(root: Path, plan: dict) -> None:
    pin = plan['checked_setup']
    controls = _controls(root)
    archive = controls / 'checked-setup'
    required = {'kind', 'archive', 'checked_receipt_sha256', 'setup_output_receipt_sha256',
                'recipe_sha256', 'initial_threat_model_sha256', 'setup_trace_sha256',
                'build_authority_sha256', 'setup_chain_sha256', 'cumulative_setup_used',
                'source_manifest_sha256', 'source_mode_sha256', 'goal_sha256',
                'target_image_id', 'platform',
                'runtime_sha256', 'build_command_sha256'}
    if (not isinstance(pin, dict) or set(pin) != required
            or pin['kind'] != 'native-checked-setup-transition-v1'
            or 'source_only' not in plan or 'setup_only' in plan
            or plan['scope_sha256'] == _sha(archive / 'setup-scope.md')
            or pin['archive'] != _checked_archive_manifest(archive)):
        _fail('checked_setup_pin_mismatch')
    checked = _read_json(archive / 'package/receipt.json')
    proposal = _read_json(archive / 'setup-output-receipt.json')
    recipe = _read_json(archive / 'recipe.json')
    setup_plan = _read_json(archive / 'setup-plan.json')
    import native_setup_builder as builder
    catalog = builder.catalog_snapshot(archive / 'package/dependencies', recipe)
    dependency_root = archive / 'package/dependencies/payload'
    archived_dependencies = _checked_files(dependency_root)
    active_dependencies = _checked_files(controls / 'source-modules')
    archived_outputs = _checked_files(archive / 'package/output')
    if (pin['checked_receipt_sha256'] != _sha(archive / 'package/receipt.json')
            or pin['setup_output_receipt_sha256'] != _sha(archive / 'setup-output-receipt.json')
            or pin['recipe_sha256'] != _sha(archive / 'recipe.json')
            or pin['initial_threat_model_sha256'] != _sha(archive / 'THREAT_MODEL.md')
            or pin['setup_trace_sha256'] != _sha(archive / 'setup-trace.json')
            or pin['build_authority_sha256'] != _sha(archive / 'build-authority.json')
            or pin['setup_chain_sha256'] != checked.get('setup_chain_sha256')
            or pin['cumulative_setup_used'] != checked.get('cumulative_setup_used')
            or pin['source_manifest_sha256'] != checked.get('source_manifest_sha256')
            or pin['source_mode_sha256'] != checked.get('source_mode_sha256')
            or pin['goal_sha256'] != checked.get('goal_sha256')
            or pin['target_image_id'] != checked.get('image_id')
            or pin['platform'] != checked.get('platform')
            or pin['runtime_sha256'] != hashlib.sha256(
                canonical_json_bytes(recipe.get('runtime'))).hexdigest()
            or pin['build_command_sha256'] != hashlib.sha256(
                canonical_json_bytes(recipe.get('build_command'))).hexdigest()
            or checked.get('kind') != 'native-setup-checked-v1'
            or checked.get('status') != 'ready'
            or checked.get('setup_output_receipt_sha256') != pin['setup_output_receipt_sha256']
            or checked.get('recipe_sha256') != pin['recipe_sha256']
            or checked.get('threat_model_sha256') != pin['initial_threat_model_sha256']
            or checked.get('build_authority_sha256') != pin['build_authority_sha256']
            or checked.get('dependency_catalog_tree_sha256') != catalog['tree']['tree_sha256']
            or checked.get('dependencies') != catalog['selected']
            or proposal.get('files') != {'recipe.json': pin['recipe_sha256'],
                                         'THREAT_MODEL.md': pin['initial_threat_model_sha256']}
            or proposal.get('native_trace_sha256') != pin['setup_trace_sha256']
            or setup_plan.get('source_manifest_sha256') != pin['source_manifest_sha256']
            or setup_plan.get('brief_sha256') != pin['goal_sha256']
            or _sha(archive / 'setup-plan.json') != checked.get('setup_plan_sha256')
            or _sha(archive / 'setup-scope.md') != checked.get('setup_scope_sha256')
            or _sha(archive / 'setup-approval.json') != checked.get('setup_approval_sha256')
            or _sha(controls / 'research/checked-setup/INITIAL_THREAT_MODEL.md')
            != pin['initial_threat_model_sha256']
            or _sha(controls / 'research/checked-setup/SETUP_TRACE.json')
            != pin['setup_trace_sha256']
            or plan['source_manifest_sha256'] != pin['source_manifest_sha256']
            or _source_mode_digest(root / 'original') != pin['source_mode_sha256']
            or plan['brief_sha256'] != pin['goal_sha256']
            or plan['target_image_id'] != pin['target_image_id']
            or plan['platform'] != pin['platform']
            or plan['source_only'].get('runtime') != recipe.get('runtime')
            or plan['source_only'].get('build_command') != recipe.get('build_command')
            or archived_dependencies != checked.get('dependencies')
            or archived_outputs != checked.get('outputs')
            or archived_dependencies != active_dependencies):
        _fail('checked_setup_pin_mismatch')


def prepare_checked(args: argparse.Namespace) -> dict:
    """Seal a source-only research plan from a checked, stopped setup package."""
    scope = _file(Path(args.scope_file), private=True)
    if _sha(scope) != args.scope_sha256:
        _fail('research_scope_pin_mismatch')
    setup_root = _private_root(Path(args.checked_setup_root))
    research_root = Path(args.run_root)
    if not research_root.is_absolute():
        _fail('checked_setup_run_root_overlap')
    resolved_setup = setup_root.resolve(strict=True)
    resolved_research = research_root.resolve(strict=False)
    if (resolved_research.is_relative_to(resolved_setup)
            or resolved_setup.is_relative_to(resolved_research)):
        _fail('checked_setup_run_root_overlap')
    import native_setup_builder as builder
    checked = builder.verify_checked(setup_root, require_fresh=True)
    receipt = checked['receipt']
    recipe = checked['recipe']
    if (args.scope_sha256 == receipt['setup_scope_sha256']
            or b'native-setup-scope-v1' in scope.read_bytes()):
        _fail('separate_research_scope_required')
    setup_plan = _read_json(setup_root / 'plan.json')
    setup_controls = _controls(setup_root)
    if (receipt['setup_plan_sha256'] != _sha(setup_root / 'plan.json')
            or receipt['goal_sha256'] != _sha(setup_controls / 'BRIEF.md')):
        _fail('checked_setup_goal_or_plan_changed')
    limits = {'max_connections': args.max_connections, 'max_bytes': args.max_bytes,
              'duration_seconds': args.duration_seconds}
    if not _valid_limits(limits):
        _fail('research_allowance_invalid')
    with tempfile.TemporaryDirectory(prefix='native-checked-prepare-') as temporary:
        temporary_root = Path(temporary).resolve(strict=True)
        runtime = temporary_root / 'runtime.json'
        command = temporary_root / 'command.json'
        _write_json(runtime, recipe['runtime'], once=True)
        _write_json(command, recipe['build_command'], once=True)
        words = ['prepare', '--source-only', '--run-root', str(args.run_root),
                 '--source', checked['source_dir'],
                 '--brief', str(setup_controls / 'BRIEF.md'),
                 '--scope-file', str(scope), '--scope-sha256', args.scope_sha256,
                 '--relay', str(setup_controls / 'relay'),
                 '--relay-sha256', setup_plan['relay_sha256'],
                 '--runtime-ca', str(setup_controls / 'runtime-ca.pem'),
                 '--runtime-ca-sha256', setup_plan['runtime_ca_sha256'],
                 '--image-id', setup_plan['image_id'],
                 '--target-image-id', receipt['image_id'],
                 '--platform', receipt['platform'],
                 '--source-runtime', str(runtime), '--build-command', str(command),
                 '--model', setup_plan['model'], '--provider-route', setup_plan['provider_route'],
                 '--max-connections', str(args.max_connections),
                 '--max-bytes', str(args.max_bytes),
                 '--duration-seconds', str(args.duration_seconds)]
        if receipt.get('dependencies'):
            words.extend(('--module-cache', checked['dependency_dir']))
        prepared_args = _parser().parse_args(words)
        prepared_args.checked_setup = {'checked': checked, 'setup_root': setup_root}
        result = prepare(prepared_args)
    result['checked_setup_receipt_sha256'] = _sha(
        Path(args.run_root) / 'controls/checked-setup/package/receipt.json')
    return result


def _copy_setup_source(source: Path, destination: Path, inventory: dict[str, str]) -> None:
    if len(inventory) > SETUP_SOURCE_MAX_FILES:
        _fail('setup_source_limit_exceeded')
    destination.mkdir(mode=0o700)
    copied_bytes = 0
    source_fd = os.open(source, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for relative in inventory:
            parts = Path(relative).parts
            parent_fd = os.dup(source_fd)
            target_parent = destination
            try:
                for part in parts[:-1]:
                    next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                      dir_fd=parent_fd)
                    os.close(parent_fd)
                    parent_fd = next_fd
                    target_parent /= part
                    target_parent.mkdir(mode=0o700, exist_ok=True)
                descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
                with os.fdopen(descriptor, 'rb') as src, (target_parent / parts[-1]).open('xb') as dst:
                    if not stat.S_ISREG(os.fstat(src.fileno()).st_mode):
                        _fail('setup_source_changed')
                    while True:
                        chunk = src.read(min(1024 * 1024, SETUP_SOURCE_MAX_BYTES - copied_bytes + 1))
                        if not chunk:
                            break
                        copied_bytes += len(chunk)
                        if copied_bytes > SETUP_SOURCE_MAX_BYTES:
                            _fail('setup_source_limit_exceeded')
                        dst.write(chunk)
            finally:
                os.close(parent_fd)
    finally:
        os.close(source_fd)
    _verify_inventory(source, inventory, setup_limit=True)
    _verify_inventory(destination, inventory, setup_limit=True)


def _valid_relative_path(value: str) -> bool:
    return (isinstance(value, str) and bool(value) and not value.startswith('/')
            and not '\\' in value and all(part not in ('', '.', '..') for part in value.split('/')))


def _mutable(relative: str, paths: list[str]) -> bool:
    return any(relative == item or relative.startswith(item + '/') for item in paths)


def _verify_target_state(directory: Path, source: dict[str, str], mutable_paths: list[str]) -> None:
    observed = {}
    for path in sorted(directory.rglob('*')):
        relative = path.relative_to(directory).as_posix()
        if _mutable(relative, mutable_paths):
            continue
        if path.is_symlink():
            _fail('target_source_symlink')
        entry = path.stat(follow_symlinks=False)
        if stat.S_ISDIR(entry.st_mode):
            continue
        if not stat.S_ISREG(entry.st_mode):
            _fail('target_source_special_file')
        observed[relative] = _sha(path)
    expected = {name: digest for name, digest in source.items()
                if not _mutable(name, mutable_paths)}
    if observed != expected:
        _fail('target_source_or_state_changed')


def _snapshot_tree(directory: Path) -> tuple[dict, dict[str, str], dict[str, int]]:
    """Hash a bounded tree; discovered names remain in memory only."""
    if not directory.is_dir() or directory.is_symlink():
        _fail('snapshot_directory_invalid')
    rows: list[tuple[str, str]] = []
    observed: dict[str, str] = {}
    sizes: dict[str, int] = {}
    byte_count = 0
    entry_count = 0
    for path in directory.rglob('*'):
        entry_count += 1
        if entry_count > 100_000:
            _fail('snapshot_entry_limit')
        relative = path.relative_to(directory).as_posix()
        if len(relative.encode('utf-8')) > 4096 or len(path.parts) - len(directory.parts) > 64:
            _fail('snapshot_path_limit')
        if path.is_symlink():
            _fail('snapshot_symlink_forbidden')
        entry = path.stat(follow_symlinks=False)
        if stat.S_ISDIR(entry.st_mode):
            continue
        if not stat.S_ISREG(entry.st_mode):
            _fail('snapshot_special_file_forbidden')
        byte_count += entry.st_size
        if byte_count > 2 * 1024 * 1024 * 1024:
            _fail('snapshot_byte_limit')
        digest = _sha(path)
        after = path.stat(follow_symlinks=False)
        if ((entry.st_dev, entry.st_ino, entry.st_size, entry.st_mtime_ns) !=
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
            _fail('snapshot_file_changed_during_hash')
        rows.append((relative, digest))
        observed[relative] = digest
        sizes[relative] = entry.st_size
    aggregate = hashlib.sha256()
    for relative, digest in sorted(rows):
        aggregate.update(json.dumps([relative, digest], separators=(',', ':'),
                                    ensure_ascii=False).encode('utf-8') + b'\n')
    return ({'files': len(rows), 'bytes': byte_count,
             'tree_sha256': aggregate.hexdigest()}, observed, sizes)


def _snapshot_delta(observed: dict[str, str], baseline: dict[str, str]) -> dict[str, int]:
    return {'added': len(observed.keys() - baseline.keys()),
            'modified': sum(observed[name] != baseline[name]
                            for name in observed.keys() & baseline.keys()),
            'removed': len(baseline.keys() - observed.keys())}


def _snapshot_store(root: Path) -> dict:
    directory = root / 'researcher/data/opencode'
    if not directory.exists():
        return {'status': 'missing', 'present': False}
    summary, _, _ = _snapshot_tree(directory)
    main = directory / 'opencode.db'
    if not main.exists():
        return {'status': 'missing', 'present': False, 'tree': summary}
    if main.is_symlink() or not main.is_file():
        _fail('snapshot_store_file_invalid')
    identity = {}
    for label, path in (('main', main), ('wal', directory / 'opencode.db-wal'),
                        ('shm', directory / 'opencode.db-shm')):
        if not path.exists():
            identity[label] = {'present': False}
            continue
        if path.is_symlink() or not path.is_file():
            _fail('snapshot_store_file_invalid')
        entry = path.stat(follow_symlinks=False)
        identity[label] = {'present': True, 'sha256': _sha(path), 'bytes': entry.st_size,
                           'device': entry.st_dev, 'inode': entry.st_ino}
    with main.open('rb') as stream:
        header = stream.read(16)
    return {'status': 'present' if header == b'SQLite format 3\x00' else 'invalid_header',
            'present': True, 'tree': summary, **identity}


def _filesystem_snapshot(root: Path, plan: dict) -> dict:
    """Provider-free byte collection; caller is responsible for stop proof."""
    _verify_inventory(root / 'original', plan['source_sha256'], setup_limit='setup_only' in plan)
    if 'setup_only' in plan:
        receipt_path = _controls(root) / 'setup-output/receipt.json'
        package = _read_json(receipt_path) if receipt_path.exists() else None
        if package is not None:
            expected = package.get('files')
            dispatch_id = package.get('dispatch_id')
            setup_dispatches = _setup_dispatches(root)
            if (not isinstance(dispatch_id, str) or not re.fullmatch(r'[0-9a-f]{32}', dispatch_id)
                    or not setup_dispatches
                    or setup_dispatches[-1]['dispatch_id'] != dispatch_id
                    or package.get('kind') != 'native-setup-output-v1'
                    or package.get('status') != 'frozen_proposal'
                    or package.get('plan_sha256') != _sha(root / 'plan.json')
                    or package.get('approval_sha256') != _sha(_controls(root) / 'approval.json')
                    or package.get('original_source_manifest_sha256') != plan['source_manifest_sha256']
                    or package.get('setup_sequence') != _read_json(_controls(root) / 'dispatch' /
                                                                   (dispatch_id + '.json')).get('setup_sequence')
                    or package.get('dispatch_sha256') != _sha(_controls(root) / 'dispatch' /
                                                              (dispatch_id + '.json'))
                    or package.get('native_trace_sha256') != _sha(_controls(root) / 'dispatch' /
                                                                   (dispatch_id + '.trace.json'))
                    or not isinstance(expected, dict) or set(expected) != set(SETUP_OUTPUT_FILES)
                    or any(_sha(_file(_controls(root) / 'setup-output' / name, private=True)) != digest
                           for name, digest in expected.items())):
                _fail('setup_output_pin_mismatch')
        store = _snapshot_store(root)
        return {'kind': 'native-setup-host-byte-receipt-v1',
                'status': 'complete' if package is not None else 'incomplete',
                'plan_sha256': _sha(root / 'plan.json'),
                'original_source_manifest_sha256': plan['source_manifest_sha256'],
                'setup_output_receipt_sha256': _sha(receipt_path) if package else None,
                'native_store': store}
    project, project_files, _ = _snapshot_tree(root / 'researcher/project')
    project['delta'] = _snapshot_delta(project_files, plan['source_sha256'])
    targets = {}
    mutable_paths = plan['mutable_paths']
    for role in ('target', 'review-target-1', 'review-target-2'):
        summary, observed, sizes = _snapshot_tree(root / role)
        immutable = {name: digest for name, digest in observed.items()
                     if not _mutable(name, mutable_paths)}
        baseline = {name: digest for name, digest in plan['source_sha256'].items()
                    if not _mutable(name, mutable_paths)}
        summary['immutable_delta'] = _snapshot_delta(immutable, baseline)
        summary['mutable_files'] = sum(_mutable(name, mutable_paths) for name in observed)
        summary['mutable_bytes'] = sum(size for name, size in sizes.items()
                                       if _mutable(name, mutable_paths))
        targets[role] = summary
    store = _snapshot_store(root)
    notebook = None
    if 'research_workflow_sha256' in plan:
        path = root / 'researcher/RESEARCH.md'
        notebook = {'present': False}
        if path.exists() or path.is_symlink():
            path = _file(path, private=True)
            if path.stat().st_size > 8 * 1024 * 1024:
                _fail('research_notebook_oversize')
            notebook = {'present': True, 'sha256': _sha(path), 'bytes': path.stat().st_size}
    return {'kind': 'native-research-host-byte-receipt-v1',
            'status': 'complete' if store['status'] == 'present' else 'incomplete',
            'researcher_project': project, 'native_store': store,
            **({'research_notebook': notebook} if notebook is not None else {}),
            'targets': targets, 'target_image_id': plan['target_image_id'],
            'plan_sha256': _sha(root / 'plan.json')}


def _stopped_snapshot(root: Path, plan: dict) -> dict:
    """Bind byte collection to the exact NativeRun terminal producer set."""
    controls = _controls(root)
    manifest_path = controls / 'producer-manifest.json'
    manifest = _read_json(manifest_path)
    state = _read_json(controls / 'native-state/RUN.json')
    revoked = _read_json(controls / 'native-state/REVOKED')
    resources = _read_json(controls / 'resources.json')
    ids = [row.get('id') for row in resources.get('resources', [])
           if row.get('kind') == 'container']
    manifest_ids = [item.get('id') for item in manifest.get('producers', [])]
    manifest_digest = _sha(manifest_path)
    expected_count = 2 if 'setup_only' in plan else 8
    if (len(ids) != expected_count or ids != manifest_ids or state.get('ids') != ids
            or revoked.get('ids') != ids or revoked.get('producers_verified_stopped') is not True
            or state.get('manifest_sha256') != manifest_digest
            or revoked.get('manifest_sha256') != manifest_digest):
        _fail('snapshot_native_stop_proof_invalid')
    _, producer = _activate_controls(root)
    by_id = {row['id']: row.get('role') for row in resources['resources']
             if row.get('kind') == 'container'}
    target_builds = set()
    for item in manifest['producers']:
        info = _inspect('container', item['id'])
        run_state = info.get('State', {})
        if (info.get('Id') != item['id'] or producer.binding(info) != item.get('binding')
                or (run_state.get('Running') is True and run_state.get('Paused') is not True)):
            _fail('snapshot_producer_not_frozen')
        if by_id.get(item['id']) in ('target', 'review-target-1', 'review-target-2'):
            if info.get('Image') != plan['target_image_id']:
                _fail('snapshot_target_build_changed')
            target_builds.add(by_id[item['id']])
    if 'setup_only' not in plan and target_builds != {'target', 'review-target-1', 'review-target-2'}:
        _fail('snapshot_target_build_missing')
    receipt = _filesystem_snapshot(root, plan)
    if 'setup_only' not in plan:
        receipt['target_build'] = {'image_id': plan['target_image_id'],
                                   'matching_frozen_containers': len(target_builds)}
    receipt['native_stop'] = {'manifest_sha256': manifest_digest,
                              'producer_ids_sha256': hashlib.sha256(
                                  json.dumps(ids, separators=(',', ':')).encode()).hexdigest(),
                              'revoked_sha256': _sha(controls / 'native-state/REVOKED')}
    path = controls / 'host-snapshot.json'
    _write_json(path, receipt, once=True)
    return {'status': receipt['status'], 'receipt_path': str(path),
            'receipt_sha256': _sha(path)}


def _controls(root: Path) -> Path:
    return root / 'controls'


def _plan(root: Path) -> dict:
    root = _private_root(root)
    plan = _read_json(root / 'plan.json')
    if plan.get('kind') != 'native-research-plan-v1' or not _valid_limits(plan.get('limits')):
        _fail('run_plan_invalid')
    return plan


def _valid_limits(value: object) -> bool:
    return (isinstance(value, dict) and set(value) == set(DEFAULT_LIMITS)
            and type(value['max_connections']) is int and 1 <= value['max_connections'] <= 128
            and type(value['max_bytes']) is int and 1024 <= value['max_bytes'] <= 128 * 1024 * 1024
            and type(value['duration_seconds']) is int and 30 <= value['duration_seconds'] <= 86400)


def _validate_target_command(path: Path) -> list[str]:
    path = _file(path)
    if path.stat().st_size > 8192:
        _fail('target_command_oversize')
    try:
        command = json.loads(path.read_text())
    except (UnicodeError, ValueError):
        _fail('target_command_invalid')
    return _validate_argv(command)


def _validate_argv(command: object) -> list[str]:
    if (not isinstance(command, list) or not 1 <= len(command) <= 64
            or any(not isinstance(item, str) or not item or '\x00' in item or len(item) > 4096
                   for item in command)):
        _fail('target_command_invalid')
    if any(re.search(r'(?:password|passwd|token|secret|api[-_]?key|authorization|cookie|bearer|basic)', item, re.I)
           for item in command):
        _fail('target_command_may_contain_credential')
    return command


def _capture_mode(plan: dict) -> str | None:
    if 'kanboard_capture' in plan and 't01_capture' in plan:
        _fail('capture_modes_conflict')
    return 't01' if 't01_capture' in plan else ('s10' if 'kanboard_capture' in plan else None)


def _origin_enabled(plan: dict) -> bool:
    return isinstance(plan.get('native_origin'), dict) and _capture_mode(plan) is not None


def _origin_binary(root: Path, plan: dict) -> Path:
    if not _origin_enabled(plan):
        _fail('native_origin_not_configured')
    pin = plan['native_origin']
    binary = _file(_controls(root) / 'origin/bin/native-origin', private=True)
    header = binary.read_bytes()[:20]
    machine = {'linux/amd64': 62, 'linux/arm64': 183}[plan['platform']]
    if (pin.get('kind') != 'native-origin-build-v1'
            or pin.get('go_version') != ORIGIN_GO_VERSION
            or pin.get('source_sha256') != ORIGIN_SOURCE_FILES
            or pin.get('binary_sha256') != _sha(binary)
            or len(header) != 20 or header[:6] != b'\x7fELF\x02\x01'
            or int.from_bytes(header[18:20], 'little') != machine
            or binary.stat().st_mode & 0o022 or not binary.stat().st_mode & 0o111):
        _fail('native_origin_binary_pin_mismatch')
    for relative, digest in ORIGIN_SOURCE_FILES.items():
        if _sha(_file(_controls(root) / relative, private=True)) != digest:
            _fail('native_origin_source_pin_mismatch')
    return binary


def _capture_pins(case: str = 's10') -> dict[str, str]:
    if case == 't01':
        return {'adapter_sha256': T01_CAPTURE_FILES['evals/native-qualification/kanboard_native_capture.py'],
                'broker_sha256': T01_CAPTURE_FILES['evals/native-qualification/smoke/t01_jsonrpc_broker.php'],
                'collector_sha256': T01_CAPTURE_FILES['evals/native-qualification/smoke/t01_receipt_collector.php'],
                'source_manifest_sha256': T01_SOURCE_SHA, 'middleware_sha256': T01_MIDDLEWARE_SHA}
    return {'adapter_sha256': CAPTURE_FILES['evals/native-qualification/kanboard_native_capture.py'],
            'probe_sha256': CAPTURE_FILES['evals/native-qualification/smoke/kanboard_effect_probe.php'],
            'collector_sha256': CAPTURE_FILES['evals/native-qualification/smoke/kanboard_effect_collector.php'],
            'broker_sha256': CAPTURE_FILES['evals/native-qualification/smoke/kanboard_role_broker.php'],
            'source_manifest_sha256': CAPTURE_SOURCE_SHA,
            'controller_sha256': CAPTURE_CONTROLLER_SHA}


def _load_capture_module(root: Path):
    path = _controls(root) / 'evals/native-qualification/kanboard_native_capture.py'
    if _sha(_file(path, private=True)) != CAPTURE_FILES['evals/native-qualification/kanboard_native_capture.py']:
        _fail('capture_adapter_pin_mismatch')
    spec = importlib.util.spec_from_file_location('native_kanboard_capture', path)
    if spec is None or spec.loader is None:
        _fail('capture_adapter_unavailable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_origin_gate(root: Path):
    path = _controls(root) / 'tools/native_kanboard_origin_gate.py'
    if _sha(_file(path)) != CONTROL_SHA['tools/native_kanboard_origin_gate.py']:
        _fail('origin_gate_pin_mismatch')
    spec = importlib.util.spec_from_file_location('native_kanboard_origin_gate', path)
    if spec is None or spec.loader is None:
        _fail('origin_gate_unavailable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_recovery_module(root: Path):
    path = _controls(root) / 'tools/native_effect_recovery.py'
    if _sha(_file(path)) != CONTROL_SHA['tools/native_effect_recovery.py']:
        _fail('recovery_helper_pin_mismatch')
    spec = importlib.util.spec_from_file_location('native_effect_recovery', path)
    if spec is None or spec.loader is None:
        _fail('recovery_helper_unavailable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_t01_semantic_module(root: Path):
    relative = 'tools/t01_semantic_reconcile.py'
    path = _controls(root) / relative
    if _sha(_file(path, private=True)) != T01_CAPTURE_FILES[relative]:
        _fail('t01_semantic_pin_mismatch')
    spec = importlib.util.spec_from_file_location('t01_semantic_reconcile', path)
    if spec is None or spec.loader is None:
        _fail('t01_semantic_unavailable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _kanboard_recovery_window(root: Path, dispatch_id: str, role: str) -> tuple[dict, dict, dict]:
    if role != 'resume' or 'kanboard_capture' not in _plan(root):
        _fail('kanboard_recovery_turn_unqualified')
    slot = _controls(root) / 'observer/target'
    stage = _read_json(slot / 'stage.json')
    dispatch = _read_json(_controls(root) / 'dispatch' / (dispatch_id + '.json'))
    window = _read_json(slot / ('window-' + dispatch_id + '.json'))
    ids = stage.get('ids')
    topology = window.get('topology')
    if (stage.get('kind') != 'kanboard-native-capture-stage-v1'
            or stage.get('target') != 'target'
            or stage.get('plan_sha256') != _sha(root / 'plan.json')
            or stage.get('source_manifest_sha256') != CAPTURE_SOURCE_SHA
            or stage.get('controller_sha256') != _sha(_file(
                root / 'target/app/Controller/ProjectPermissionController.php'))
            or not isinstance(ids, dict) or set(ids) != {'s', 'q', 't', 'b'}
            or any(type(value) is not int or value < 1 for value in ids.values())
            or ids['s'] == ids['q']
            or window.get('kind') != 'kanboard-native-window-v1'
            or window.get('dispatch_id') != dispatch_id or window.get('target') != 'target'
            or window.get('role') != role or window.get('session_id') != dispatch.get('session_id')
            or window.get('dispatch_sha256') != _sha(_controls(root) / 'dispatch' / (dispatch_id + '.json'))
            or dispatch.get('status') != 'unknown_effect' or dispatch.get('role') != role
            or not isinstance(topology, dict)
            or topology.get('status') != 'topology_attested_origin_and_credentials_held'
            or topology.get('target') != 'target'
            or topology.get('collector_db') != str(slot / 'receipts/receipts.sqlite')
            or not isinstance(topology.get('native_client_ip'), str)
            or not isinstance(topology.get('app_observer_ip'), str)):
        _fail('kanboard_recovery_window_changed')
    return stage, window, topology


def _arm_kanboard_role_grant(root: Path, dispatch_id: str, role: str) -> dict:
    stage, window, topology = _kanboard_recovery_window(root, dispatch_id, role)
    ids = stage['ids']
    db_path = _file(root / 'target/data/db.sqlite', private=True)
    try:
        with closing(sqlite3.connect(db_path.as_uri() + '?mode=ro', uri=True)) as db:
            managers = db.execute(
                'SELECT pu.user_id FROM project_has_users pu JOIN users u ON u.id=pu.user_id '
                "WHERE pu.project_id=? AND pu.role='project-manager' "
                "AND u.role='app-user' AND u.is_active=1", (ids['s'],)).fetchmany(2)
    except sqlite3.DatabaseError:
        _fail('kanboard_recovery_actor_unavailable')
    if len(managers) != 1 or type(managers[0][0]) is not int:
        _fail('kanboard_recovery_actor_ambiguous')
    module = _load_recovery_module(root)
    result = module.arm_kanboard_role_grant(
        root, dispatch_id, s=ids['s'], q=ids['q'], t=ids['t'], actor_a=managers[0][0],
        subject_b=ids['b'], researcher_ip=topology['native_client_ip'],
        app_ip=topology['app_observer_ip'], collector_db=Path(topology['collector_db']),
        origin_ingress=_origin_enabled(_plan(root)))
    sidecar = _read_json(_controls(root) / 'recovery' / (dispatch_id + '.json'))
    if (sidecar.get('collector_max_id') != window.get('collector_max_id_before')
            or sidecar.get('collector_prefix_count') != window.get('collector_count_before')
            or sidecar.get('collector_prefix_sha256') != window.get('collector_prefix_sha256')):
        _fail('kanboard_recovery_window_advanced')
    return result


def prepare(args: argparse.Namespace) -> dict:
    for name in ('build_command', 'go_toolchain', 'module_cache', 'source_runtime'):
        if not hasattr(args, name):
            setattr(args, name, None)
    source = Path(args.source)
    brief = _file(Path(args.brief))
    scope = _file(Path(args.scope_file), private=True)
    relay = _file(Path(args.relay), private=True)
    ca = _file(Path(args.runtime_ca), private=True)
    source_only = bool(getattr(args, 'source_only', False))
    setup_only = bool(getattr(args, 'setup_only', False))
    checked_context = getattr(args, 'checked_setup', None)
    if checked_context is not None and (not source_only or setup_only):
        _fail('checked_setup_source_profile_required')
    source_modules = None
    module_inventory = {}
    source_profile = {}
    if setup_only:
        if (source_only or args.target_command or args.target_port is not None or args.build_command
                or args.module_cache or args.go_toolchain or args.source_runtime
                or args.kanboard_capture or args.t01_capture or args.origin_ingress
                or args.mutable_path or args.expected_skill_id):
            _fail('setup_profile_invalid')
        command_path = None
    elif source_only:
        if (args.target_command or args.target_port is not None or not args.build_command
                or args.kanboard_capture or args.t01_capture or args.origin_ingress
                or bool(args.go_toolchain) == bool(args.source_runtime)):
            _fail('source_profile_invalid')
        command_path = Path(args.build_command)
        if args.module_cache:
            source_modules = Path(args.module_cache)
            if not source_modules.is_absolute() or source_modules.resolve() != source_modules:
                _fail('source_module_cache_invalid')
            module_inventory = _inventory(source_modules)
        if args.source_runtime:
            source_profile['runtime'] = _validate_source_runtime(_read_json(_file(Path(args.source_runtime))))
        else:
            if not source_modules or not re.fullmatch(r'go1\.[0-9]+\.[0-9]+', args.go_toolchain):
                _fail('source_profile_invalid')
            found = shutil.which('go')
            if not found:
                _fail('source_metadata_go_unavailable')
            metadata_go = Path(found).resolve(strict=True)
            if metadata_go.stat().st_mode & 0o022:
                _fail('source_metadata_go_writable')
            version = subprocess.run([str(metadata_go), 'version'], stdin=subprocess.DEVNULL,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10,
                                     env={'PATH': '/usr/bin:/bin', 'GOTOOLCHAIN': 'local'}, check=False)
            if version.returncode or not version.stdout.decode(errors='replace').startswith(
                    'go version ' + args.go_toolchain + ' '):
                _fail('source_metadata_go_version_mismatch')
            source_profile.update({'go_toolchain': args.go_toolchain,
                                   'metadata_go': str(metadata_go), 'metadata_go_sha256': _sha(metadata_go)})
    else:
        if (not args.target_command or args.target_port is None or args.build_command
                or args.module_cache or args.go_toolchain or args.source_runtime):
            _fail('service_profile_invalid')
        command_path = Path(args.target_command)
    target_command = None if setup_only else _validate_target_command(command_path)
    run_root = Path(args.run_root)
    if not source.is_absolute() or source.is_symlink() or not source.is_dir():
        _fail('source_directory_invalid')
    source = source.resolve(strict=True)
    if not run_root.is_absolute() or run_root.is_relative_to(source) or source.is_relative_to(run_root):
        _fail('source_run_root_overlap')
    model_config = _model_config(vars(args))
    limits = {'max_connections': args.max_connections, 'max_bytes': args.max_bytes,
              'duration_seconds': args.duration_seconds}
    if not _valid_limits(limits):
        _fail('allowance_invalid')
    target_image_id = args.image_id if setup_only else args.target_image_id
    if (not IMAGE_RE.fullmatch(args.image_id) or not isinstance(target_image_id, str)
            or not IMAGE_RE.fullmatch(target_image_id)
            or args.platform not in ('linux/arm64', 'linux/amd64')
            or (not source_only and not setup_only and not 1 <= args.target_port <= 65535)):
        _fail('runtime_or_target_pin_invalid')
    if setup_only:
        if (not all((args.setup_operator_id, args.setup_engagement_id,
                     args.setup_scope_signature, args.setup_allowed_signers,
                     args.setup_trusted_fingerprint))
                or type(args.setup_max_workspace_bytes) is not int
                or not 8 * 1024 * 1024 <= args.setup_max_workspace_bytes <= 512 * 1024 * 1024):
            _fail('setup_authority_input_missing')
        signed_source_manifest = _verify_setup_scope(
            scope, Path(args.setup_scope_signature), Path(args.setup_allowed_signers),
            args.setup_engagement_id, args.setup_operator_id,
            args.setup_trusted_fingerprint, None, _sha(brief))
    elif any((args.setup_operator_id, args.setup_engagement_id, args.setup_scope_signature,
              args.setup_allowed_signers, args.setup_trusted_fingerprint)):
        _fail('setup_authority_unexpected')
    source_inventory = (_inventory(source, max_files=SETUP_SOURCE_MAX_FILES,
                                   max_bytes=SETUP_SOURCE_MAX_BYTES) if setup_only else _inventory(source))
    source_manifest = hashlib.sha256(json.dumps(source_inventory, sort_keys=True).encode()).hexdigest()
    if setup_only and source_manifest != signed_source_manifest:
        _fail('setup_signed_source_mismatch')
    for path, expected in ((scope, args.scope_sha256), (relay, args.relay_sha256),
                           (ca, args.runtime_ca_sha256)):
        if not HEX_RE.fullmatch(expected) or _sha(path) != expected:
            _fail('input_digest_mismatch')
    if b'PRIVATE KEY' in ca.read_bytes() or ca.stat().st_size > 4 * 1024 * 1024:
        _fail('runtime_ca_invalid')
    try:
        trust = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        trust.load_verify_locations(cafile=str(ca))
    except ssl.SSLError:
        _fail('runtime_ca_invalid')
    header = relay.open('rb').read(20)
    machine = {'linux/amd64': 62, 'linux/arm64': 183}[args.platform]
    if (len(header) != 20 or header[:6] != b'\x7fELF\x02\x01'
            or int.from_bytes(header[18:20], 'little') != machine
            or not relay.stat().st_mode & 0o111):
        _fail('relay_platform_invalid')
    for relative, digest in CONTROL_SHA.items():
        if _sha(ROOT / relative) != digest:
            _fail('control_pin_mismatch')
    docker_found = shutil.which('docker')
    if not docker_found:
        _fail('docker_unavailable')
    docker_binary = Path(docker_found).resolve(strict=True)
    docker_entry = docker_binary.stat(follow_symlinks=False)
    if (not stat.S_ISREG(docker_entry.st_mode) or not os.access(docker_binary, os.X_OK)
            or docker_entry.st_mode & 0o022):
        _fail('docker_executable_invalid')
    if source_only and any(name == '.native-source' or name.startswith('.native-source/')
                           for name in source_inventory):
        _fail('source_reserved_execution_path')
    capture = bool(getattr(args, 'kanboard_capture', False))
    t01_capture = bool(getattr(args, 't01_capture', False))
    origin_ingress = bool(getattr(args, 'origin_ingress', False))
    if capture and t01_capture:
        _fail('capture_modes_conflict')
    if origin_ingress and not (capture or t01_capture):
        _fail('native_origin_requires_capture')
    go_binary = None
    if origin_ingress:
        for relative, digest in ORIGIN_SOURCE_FILES.items():
            if _sha(ROOT / relative) != digest:
                _fail('native_origin_source_pin_mismatch')
        found = shutil.which('go')
        if not found:
            _fail('native_origin_go_unavailable')
        go_binary = Path(found).resolve(strict=True)
        if go_binary.stat().st_mode & 0o022:
            _fail('native_origin_go_writable')
        version = subprocess.run([str(go_binary), 'version'], stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 timeout=10, check=False)
        if version.returncode or not version.stdout.decode(errors='replace').startswith(
                'go version ' + ORIGIN_GO_VERSION + ' '):
            _fail('native_origin_go_version_mismatch')
    if capture:
        manifest = hashlib.sha256(json.dumps(source_inventory, sort_keys=True).encode()).hexdigest()
        if (manifest != CAPTURE_SOURCE_SHA or
                target_command != ['php', '-S', f'0.0.0.0:{args.target_port}', '-t', '/target']):
            _fail('kanboard_capture_source_or_command_unqualified')
        for relative, digest in CAPTURE_FILES.items():
            if _sha(ROOT / relative) != digest:
                _fail('capture_code_pin_mismatch')
    if t01_capture:
        manifest = hashlib.sha256(json.dumps(source_inventory, sort_keys=True).encode()).hexdigest()
        if (manifest != T01_SOURCE_SHA or
                target_command != ['php', '-S', f'0.0.0.0:{args.target_port}', '-t', '/target'] or
                args.target_port == 8764):
            _fail('t01_capture_source_or_command_unqualified')
        for relative, digest in T01_CAPTURE_FILES.items():
            if _sha(ROOT / relative) != digest:
                _fail('t01_capture_code_pin_mismatch')
    try:
        brief_text = brief.read_text()
    except UnicodeError:
        _fail('brief_encoding_invalid')
    if not brief_text.strip() or CREDENTIAL_TEXT.search(brief_text):
        _fail('brief_empty_or_credential_like')
    if t01_capture and _sha(brief) not in (T01_BRIEF_SHA, T01_WORKSPACE_BRIEF_SHA):
        _fail('t01_capture_brief_pin_mismatch')
    mutable_paths = list(args.mutable_path or [])
    if (len(mutable_paths) != len(set(mutable_paths))
            or any(not _valid_relative_path(item) or item == '.git' or item.startswith('.git/')
                   for item in mutable_paths)):
        _fail('mutable_path_invalid')
    expected_skill_ids = list(args.expected_skill_id or [])
    if (len(expected_skill_ids) != len(set(expected_skill_ids))
            or any(not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', item) for item in expected_skill_ids)):
        _fail('expected_skill_id_invalid')
    root = _private_root(run_root, create=True)
    try:
        copy_names = ('original',) if setup_only else (
            'original', 'target', 'review-target-1', 'review-target-2', 'researcher/project')
        for name in copy_names:
            if setup_only:
                _copy_setup_source(source, root / name, source_inventory)
            else:
                shutil.copytree(source, root / name, dirs_exist_ok=False)
                _verify_inventory(root / name, source_inventory)
        for name in (('researcher',) if setup_only else ('researcher', 'reviewer-1', 'reviewer-2')):
            base = root / name
            for sub in ('home', 'config/opencode', 'data', 'cache', 'state', 'tmp', 'brief'):
                (base / sub).mkdir(parents=True, mode=0o700, exist_ok=True)
        if not setup_only:
            for name in ('reviewer-1', 'reviewer-2'):
                if source_only:
                    shutil.copytree(source, root / name / 'project')
                else:
                    (root / name / 'project').mkdir(mode=0o700)
        (root / 'handoff').mkdir(mode=0o700)
        for name in ('reviewer-1', 'reviewer-2'):
            (root / 'handoff' / name).mkdir(mode=0o700)
        controls = _controls(root)
        controls.mkdir(mode=0o700)
        if args.model == PAID_MODEL:
            shutil.copy2(ROOT / 'tools/native_provider_gateway.py', controls / 'provider-gateway.py')
            (controls / 'provider-gateway.py').chmod(0o600)
        if source_only:
            if source_modules:
                shutil.copytree(source_modules, controls / 'source-modules')
                _verify_inventory(controls / 'source-modules', module_inventory)
            else:
                (controls / 'source-modules').mkdir(mode=0o700)
            for role in ('reviewer-1', 'reviewer-2'):
                (controls / 'source-evidence' / role).mkdir(parents=True, mode=0o700)
            (controls / 'source-executions').mkdir(mode=0o700)
        (controls / 'dispatch').mkdir(mode=0o700)
        capture_files = CAPTURE_FILES if capture else (T01_CAPTURE_FILES if t01_capture else {})
        for relative in (*CONTROL_SHA, *capture_files, *(ORIGIN_SOURCE_FILES if origin_ingress else {})):
            destination = controls / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, destination)
            if relative in capture_files or relative in ORIGIN_SOURCE_FILES:
                destination.chmod(0o600)
            if _sha(destination) != (CONTROL_SHA | capture_files |
                                     (ORIGIN_SOURCE_FILES if origin_ingress else {}))[relative]:
                _fail('archived_control_pin_mismatch')
        origin_build = None
        if origin_ingress:
            for role in ORIGIN_ROLES:
                (controls / 'origin/socket' / role).mkdir(parents=True, mode=0o700)
                (controls / 'origin/ledger' / role).mkdir(parents=True, mode=0o700)
            (controls / 'origin/arms').mkdir(parents=True, mode=0o700)
            (controls / 'origin/registrations').mkdir(parents=True, mode=0o700)
            (controls / 'origin/proofs').mkdir(parents=True, mode=0o700)
            (controls / 'origin/window-close').mkdir(parents=True, mode=0o700)
            binary = controls / 'origin/bin/native-origin'
            binary.parent.mkdir(parents=True, mode=0o700)
            build_env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
                         'HOME': os.environ.get('HOME', str(root)),
                         'GO111MODULE': 'off', 'GOTOOLCHAIN': 'local',
                         'CGO_ENABLED': '0', 'GOOS': 'linux',
                         'GOARCH': args.platform.split('/')[1], 'GOPROXY': 'off',
                         'GOSUMDB': 'off', 'GOFLAGS': '', 'GOWORK': 'off'}
            built = subprocess.run([str(go_binary), 'build', '-trimpath', '-buildvcs=false',
                                    '-ldflags=-buildid=', '-o', str(binary),
                                    *(str(controls / name) for name in ORIGIN_SOURCE_FILES)],
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, env=build_env, timeout=120, check=False)
            if built.returncode or not binary.exists():
                _fail('native_origin_build_failed')
            binary.chmod(0o700)
            header = binary.open('rb').read(20)
            machine = {'linux/amd64': 62, 'linux/arm64': 183}[args.platform]
            if (len(header) != 20 or header[:6] != b'\x7fELF\x02\x01'
                    or int.from_bytes(header[18:20], 'little') != machine):
                _fail('native_origin_build_platform_mismatch')
            origin_build = {'kind': 'native-origin-build-v1',
                            'go_version': ORIGIN_GO_VERSION,
                            'go_binary_sha256': _sha(go_binary),
                            'source_sha256': ORIGIN_SOURCE_FILES,
                            'binary_sha256': _sha(binary)}
        inputs = [(relay, 'relay'), (ca, 'runtime-ca.pem'),
                  (scope, 'scope.md'), (brief, 'BRIEF.md')]
        if command_path is not None:
            inputs.append((command_path, 'target-command.json'))
        if setup_only:
            inputs.extend(((Path(args.setup_scope_signature), 'setup-scope.sig'),
                           (Path(args.setup_allowed_signers), 'setup-allowed-signers')))
        for source_path, name in inputs:
            destination = controls / name
            shutil.copy2(source_path, destination)
            destination.chmod(0o700 if name == 'relay' else 0o600)
        shutil.copy2(controls / 'BRIEF.md', root / 'researcher/brief/BRIEF.md')
        (root / 'researcher/brief/BRIEF.md').chmod(0o600)
        (controls / 'research').mkdir(mode=0o700)
        (controls / 'research-snapshots').mkdir(mode=0o700)
        (controls / 'continuation').mkdir(mode=0o700)
        workflow = SETUP_WORKFLOW if setup_only else RESEARCH_WORKFLOW
        for input_path, name in ((workflow, 'WORKFLOW.md'), (brief, 'BRIEF.md')):
            shutil.copy2(input_path, controls / 'research' / name)
            (controls / 'research' / name).chmod(0o600)
        checked_pin = None
        if checked_context is not None:
            checked_pin = _copy_checked_setup(root, checked_context['checked'],
                                              checked_context['setup_root'])
        notebook = root / 'researcher/RESEARCH.md'
        notebook.write_text(
            '# Research notebook\n\n'
            'Read /research/BRIEF.md, /research/WORKFLOW.md, and the current /research/RUN.json.\n'
            'This editable notebook records research, not authority or independent proof.\n\n'
            '## Hypotheses, experiments, and observations\n\nNot started. Link scripts and results.\n\n'
            '## Unfinished conditions and possible effects\n\nNo tests dispatched yet.\n\n'
            '## Continuation\n\n'
            'After each experiment, update NEXT.json with the result state (supported, refuted, '
            'blocked, or inconclusive), what it rules out, useful capabilities and coverage, and '
            'the next brief. If you propose to stop, set proposed_stop true and omit next.\n\n'
            '## Review and internal result\n\nUnreviewed; no supported conclusion yet.\n\n'
            '## Cleanup\n\nOperator verification pending.\n')
        notebook.chmod(0o600)
        next_template = root / 'researcher/NEXT.json'
        next_template.write_text(json.dumps({
            'kind': 'native-continuation-next-v1', 'last_result': None,
            'capabilities': [], 'coverage': [], 'next': None,
            'proposed_stop': False, 'strong_lead': False}, indent=2, sort_keys=True) + '\n')
        next_template.chmod(0o600)
        _write_json(controls / 'opencode.json', model_config, once=True)
        for name in (('researcher',) if setup_only else ('researcher', 'reviewer-1', 'reviewer-2')):
            (root / name / 'config/opencode/opencode.json').touch(mode=0o600)
        plan = {
            'kind': 'native-research-plan-v1', 'provider_route': args.provider_route,
            'provider_authority': AUTHORITY, 'model': args.model,
            'image_id': args.image_id, 'target_image_id': target_image_id,
            'platform': args.platform, 'target_port': args.target_port,
            'opencode_version': VERSION,
            'limits': limits, 'source_sha256': source_inventory,
            'mutable_paths': mutable_paths,
            'expected_skill_ids': sorted(expected_skill_ids),
            'source_manifest_sha256': hashlib.sha256(json.dumps(source_inventory, sort_keys=True).encode()).hexdigest(),
            'brief_sha256': _sha(controls / 'BRIEF.md'),
            'research_workflow_sha256': _sha(controls / 'research/WORKFLOW.md'),
            'scope_sha256': _sha(controls / 'scope.md'),
            'relay_sha256': _sha(controls / 'relay'),
            'runtime_ca_sha256': _sha(controls / 'runtime-ca.pem'),
            'target_command_sha256': None if setup_only else _sha(controls / 'target-command.json'),
            'config_sha256': _sha(controls / 'opencode.json'),
            'docker_binary': str(docker_binary), 'docker_sha256': _sha(docker_binary),
            'control_sha256': CONTROL_SHA,
        }
        if source_only:
            plan['source_only'] = dict(source_profile,
                module_cache_sha256=hashlib.sha256(json.dumps(module_inventory, sort_keys=True).encode()).hexdigest(),
                build_command=target_command)
            plan['source_effect_envelope'] = (CHECKED_SOURCE_EFFECT_ENVELOPE
                                              if checked_pin is not None else SOURCE_EFFECT_ENVELOPE)
        if checked_pin is not None:
            plan['checked_setup'] = checked_pin
            _verify_checked_setup(root, plan)
        if setup_only:
            plan['setup_only'] = {
                'engagement_id': args.setup_engagement_id,
                'operator_id': args.setup_operator_id,
                'trusted_fingerprint': args.setup_trusted_fingerprint,
                'scope_signature_sha256': _sha(controls / 'setup-scope.sig'),
                'allowed_signers_sha256': _sha(controls / 'setup-allowed-signers'),
                'max_workspace_bytes': args.setup_max_workspace_bytes,
                'effect_class': SETUP_EFFECT_CLASS, 'network_class': SETUP_NETWORK_CLASS}
        if args.model == PAID_MODEL:
            plan['provider_gateway_sha256'] = _sha(controls / 'provider-gateway.py')
        if capture:
            plan['kanboard_capture'] = _capture_pins()
        if t01_capture:
            plan['t01_capture'] = _capture_pins('t01')
            if plan['brief_sha256'] == T01_WORKSPACE_BRIEF_SHA:
                plan['t01_research_mode'] = 'workspace_research'
        if origin_build is not None:
            plan['native_origin'] = origin_build
        _write_json(root / 'plan.json', plan, once=True)
        return {'status': 'prepared_provider_free', 'run_root': str(root),
                'plan_sha256': _sha(root / 'plan.json'), 'source_files': len(source_inventory),
                'live_approval_required': True}
    except Exception:
        shutil.rmtree(root)
        raise


def _docker(*arguments: str, timeout: float = 30, allow_failure: bool = False) -> subprocess.CompletedProcess[bytes]:
    if DOCKER_BINARY is None:
        _fail('docker_unavailable')
    environment = {key: value for key, value in os.environ.items()
                   if key in ('HOME', 'PATH', 'DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_CONFIG')}
    try:
        result = subprocess.run([str(DOCKER_BINARY), *arguments], stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                env=environment, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        _fail('docker_command_unavailable')
    if len(result.stdout) > 2 * 1024 * 1024 or len(result.stderr) > 2 * 1024 * 1024:
        _fail('docker_command_output_oversize')
    if result.returncode and not allow_failure:
        _fail('docker_command_failed')
    return result


def _inspect(kind: str, identifier: str) -> dict:
    try:
        value = json.loads(_docker(kind, 'inspect', identifier).stdout)
    except (UnicodeError, ValueError):
        _fail('docker_inspect_invalid')
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        _fail('docker_inspect_invalid')
    return value[0]


def _image(image_id: str, platform: str, *, official: bool = False) -> None:
    info = _inspect('image', image_id)
    if (info.get('Id') != image_id or info.get('Os') != 'linux'
            or info.get('Architecture') != platform.split('/')[1]):
        _fail('image_pin_mismatch')
    config = info.get('Config') or {}
    env = config.get('Env') or []
    if official and (len(env) != len(OFFICIAL_IMAGE_ENV)
                     or dict(item.split('=', 1) for item in env if '=' in item) != OFFICIAL_IMAGE_ENV):
        _fail('opencode_image_environment_mismatch')
    if any('=' not in item or (SENSITIVE_ENV.search(item.split('=', 1)[0])
                               and item.split('=', 1)[1])
           or (item.split('=', 1)[0].startswith(('LD_', 'BUN_', 'OPENCODE_'))
               and item not in ('BUN_RUNTIME_TRANSPILER_CACHE_PATH=0',)) for item in env):
        _fail('image_ambient_credential')


def _verified_plan(root: Path, *, pristine: bool = False,
                   allow_expired_setup: bool = False) -> dict:
    global DOCKER_BINARY
    plan = _plan(root)
    controls = _controls(root)
    if ('t01_research_mode' in plan and
            (plan['t01_research_mode'] != 'workspace_research' or 't01_capture' not in plan)):
        _fail('t01_capture_research_mode_invalid')
    config = _model_config(plan)
    if plan.get('model') == PAID_MODEL:
        digest = plan.get('provider_gateway_sha256')
        if (not isinstance(digest, str) or not HEX_RE.fullmatch(digest)
                or _sha(_file(controls / 'provider-gateway.py', private=True)) != digest
                or _sha(ROOT / 'tools/native_provider_gateway.py') != digest):
            _fail('provider_gateway_pin_mismatch')
    if (plan.get('opencode_version') != VERSION
            or plan.get('control_sha256') != CONTROL_SHA
            or not IMAGE_RE.fullmatch(str(plan.get('image_id')))
            or not IMAGE_RE.fullmatch(str(plan.get('target_image_id')))):
        _fail('run_plan_pin_mismatch')
    docker_found = shutil.which('docker')
    if not docker_found:
        _fail('docker_unavailable')
    docker_binary = Path(docker_found).resolve(strict=True)
    if (str(docker_binary) != plan.get('docker_binary') or _sha(docker_binary) != plan.get('docker_sha256')
            or docker_binary.stat().st_mode & 0o022):
        _fail('docker_binary_pin_mismatch')
    DOCKER_BINARY = docker_binary
    for relative, digest in CONTROL_SHA.items():
        if _sha(controls / relative) != digest:
            _fail('archived_control_pin_mismatch')
    if 'native_origin' in plan:
        if _capture_mode(plan) is None:
            _fail('native_origin_capture_missing')
        _origin_binary(root, plan)
    if 'kanboard_capture' in plan:
        if plan['kanboard_capture'] != _capture_pins():
            _fail('capture_plan_pin_mismatch')
        for relative, digest in CAPTURE_FILES.items():
            if _sha(_file(controls / relative, private=True)) != digest:
                _fail('archived_capture_pin_mismatch')
        if plan.get('source_manifest_sha256') != CAPTURE_SOURCE_SHA:
            _fail('capture_source_pin_mismatch')
    if 't01_capture' in plan:
        if _capture_mode(plan) != 't01' or plan['t01_capture'] != _capture_pins('t01'):
            _fail('t01_capture_plan_pin_mismatch')
        expected_brief = T01_WORKSPACE_BRIEF_SHA if 't01_research_mode' in plan else T01_BRIEF_SHA
        if plan.get('brief_sha256') != expected_brief:
            _fail('t01_capture_brief_pin_mismatch')
        for relative, digest in T01_CAPTURE_FILES.items():
            if _sha(_file(controls / relative, private=True)) != digest:
                _fail('archived_t01_capture_pin_mismatch')
        if plan.get('source_manifest_sha256') != T01_SOURCE_SHA:
            _fail('t01_capture_source_pin_mismatch')
    pinned_inputs = [('relay', 'relay_sha256'), ('runtime-ca.pem', 'runtime_ca_sha256'),
                     ('scope.md', 'scope_sha256'), ('BRIEF.md', 'brief_sha256'),
                     ('opencode.json', 'config_sha256')]
    if 'setup_only' not in plan:
        pinned_inputs.append(('target-command.json', 'target_command_sha256'))
    for name, key in pinned_inputs:
        if _sha(controls / name) != plan.get(key):
            _fail('run_input_pin_mismatch')
    if 'setup_only' in plan:
        setup = plan['setup_only']
        if (not isinstance(setup, dict) or set(setup) != {
                'engagement_id', 'operator_id', 'trusted_fingerprint',
                'scope_signature_sha256', 'allowed_signers_sha256',
                'max_workspace_bytes', 'effect_class', 'network_class'}
                or setup['effect_class'] != SETUP_EFFECT_CLASS
                or setup['network_class'] != SETUP_NETWORK_CLASS
                or type(setup['max_workspace_bytes']) is not int
                or not 8 * 1024 * 1024 <= setup['max_workspace_bytes'] <= 512 * 1024 * 1024
                or setup['scope_signature_sha256'] != _sha(controls / 'setup-scope.sig')
                or setup['allowed_signers_sha256'] != _sha(controls / 'setup-allowed-signers')
                or plan['target_command_sha256'] is not None
                or plan['target_image_id'] != plan['image_id']
                or 'source_only' in plan or _capture_mode(plan)):
            _fail('setup_plan_invalid')
        _verify_setup_scope(controls / 'scope.md', controls / 'setup-scope.sig',
                            controls / 'setup-allowed-signers', setup['engagement_id'],
                            setup['operator_id'], setup['trusted_fingerprint'],
                            plan['source_manifest_sha256'], plan['brief_sha256'],
                            allow_expired=allow_expired_setup)
    if _read_json(controls / 'opencode.json') != config:
        _fail('run_config_mismatch')
    if 'source_only' in plan:
        source = plan['source_only']
        common = {'module_cache_sha256', 'build_command'}
        if (not isinstance(source, dict) or plan.get('target_port') is not None or _capture_mode(plan)
                or source.get('build_command') != _validate_target_command(controls / 'target-command.json')):
            _fail('source_profile_invalid')
        if 'runtime' in source:
            if set(source) != common | {'runtime'}:
                _fail('source_profile_invalid')
            _validate_source_runtime(source['runtime'])
        else:
            if (set(source) != common | {'go_toolchain', 'metadata_go', 'metadata_go_sha256'}
                    or not re.fullmatch(r'go1\.[0-9]+\.[0-9]+', str(source.get('go_toolchain')))):
                _fail('source_profile_invalid')
            if _sha(_file(Path(source['metadata_go']))) != source['metadata_go_sha256']:
                _fail('source_metadata_go_changed')
        modules = controls / 'source-modules'
        inventory = _inventory(modules) if any(modules.iterdir()) else {}
        module_digest = hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest()
        if module_digest != source['module_cache_sha256']:
            _fail('source_module_cache_changed')
        expected_envelope = (CHECKED_SOURCE_EFFECT_ENVELOPE if 'checked_setup' in plan
                             else SOURCE_EFFECT_ENVELOPE)
        if ('checked_setup' in plan or 'source_effect_envelope' in plan) and plan.get(
                'source_effect_envelope') != expected_envelope:
            _fail('source_effect_envelope_changed')
    if (controls / 'checked-setup').exists() != ('checked_setup' in plan):
        _fail('checked_setup_plan_membership_changed')
    if 'checked_setup' in plan:
        _verify_checked_setup(root, plan)
    if _sha(root / 'researcher/brief/BRIEF.md') != plan.get('brief_sha256'):
        _fail('run_brief_changed')
    if 'research_workflow_sha256' in plan:
        for name, key in (('WORKFLOW.md', 'research_workflow_sha256'), ('BRIEF.md', 'brief_sha256')):
            path = _file(controls / 'research' / name, private=True)
            if not HEX_RE.fullmatch(str(plan.get(key))) or _sha(path) != plan[key]:
                _fail('research_workflow_changed')
    _verify_inventory(root / 'original', plan['source_sha256'], setup_limit='setup_only' in plan)
    if pristine:
        if 'setup_only' not in plan:
            _verify_inventory(root / 'researcher/project', plan['source_sha256'])
            for name in ('target', 'review-target-1', 'review-target-2'):
                _verify_target_state(root / name, plan['source_sha256'], plan['mutable_paths'])
            if 'checked_setup' in plan:
                for name in ('researcher/project', 'target', 'review-target-1', 'review-target-2'):
                    if _source_mode_digest(root / name) != plan['checked_setup']['source_mode_sha256']:
                        _fail('checked_setup_pristine_source_mode_changed')
    return plan


def capture_stage(run_root: Path, target: str, *, s: int | None = None, q: int | None = None,
                  t: int | None = None, b: int | None = None) -> dict:
    root = _private_root(Path(run_root))
    plan = _verified_plan(root, pristine=True)
    if _capture_mode(plan) is None or (_controls(root) / 'resources.json').exists():
        _fail('capture_stage_not_prestart')
    result = _load_capture_module(root).stage(root, target, s=s, q=q, t=t, b=b)
    result['stage_sha256'] = _sha(_controls(root) / 'observer' / target / 'stage.json')
    return result


def _approval(root: Path, plan: dict, path: Path) -> None:
    if 'setup_only' in plan:
        _setup_approval(root, plan, path)
        return
    capture_db_pins = {}
    if _capture_mode(plan):
        _, capture_db_pins = _capture_specs(
            root, plan, _validate_target_command(_controls(root) / 'target-command.json'))
    approval = _read_json(path)
    expected = {
        'kind': 'native-research-live-approval-v1',
        'plan_sha256': _sha(root / 'plan.json'),
        'scope_sha256': plan['scope_sha256'],
        'provider_route': plan['provider_route'],
        'provider_authority': AUTHORITY,
        'model': plan['model'],
        'image_id': plan['image_id'],
        'target_image_id': plan['target_image_id'],
        'limits': plan['limits'],
    }
    if _capture_mode(plan):
        expected['capture_stage_sha256'] = {
            target: _sha(_controls(root) / 'observer' / target / 'stage.json')
            for target in CAPTURE_TARGETS}
    if 'kanboard_capture' in plan:
        expected['capture_target_db_sha256'] = capture_db_pins
    if any(approval.get(key) != value for key, value in expected.items()):
        _fail('live_approval_mismatch')
    if set(approval) != set(expected) | {'approved_by', 'approved_at', 'expires_at'}:
        _fail('live_approval_unknown_field')
    if (not isinstance(approval.get('approved_by'), str) or not approval['approved_by'].strip()
            or not isinstance(approval.get('approved_at'), str)
            or not isinstance(approval.get('expires_at'), str)
            or not all(re.fullmatch(r'20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z',
                                    approval[key]) for key in ('approved_at', 'expires_at'))):
        _fail('live_approval_invalid')
    try:
        approved = datetime.strptime(approval['approved_at'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
        expires = datetime.strptime(approval['expires_at'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
    except ValueError:
        _fail('live_approval_invalid')
    age = (datetime.now(timezone.utc) - approved).total_seconds()
    if not 0 <= age <= 24 * 3600 or not approved < expires <= approved + timedelta(hours=24) or datetime.now(timezone.utc) >= expires:
        _fail('live_approval_stale_or_future')
    archived = _controls(root) / 'approval.json'
    if archived.exists():
        if _read_json(archived) != approval:
            _fail('live_approval_archive_changed')
    else:
        _write_json(archived, approval, once=True)


def _approval_active(root: Path) -> None:
    plan = _plan(root)
    plan_sha = _sha(root / 'plan.json')
    approval_path = _controls(root) / 'approval.json'
    approval = _read_json(approval_path)
    activation = _read_json(_controls(root) / 'activation.json')
    if 'setup_only' in plan:
        if (activation.get('kind') != 'native-research-activation-v1'
                or activation.get('plan_sha256') != plan_sha
                or activation.get('approval_sha256') != _sha(approval_path)):
            _fail('setup_approval_changed')
        _setup_approval(root, plan, approval_path)
        return
    if (activation.get('kind') != 'native-research-activation-v1'
            or activation.get('plan_sha256') != plan_sha
            or activation.get('approval_sha256') != _sha(approval_path)
            or approval.get('kind') != 'native-research-live-approval-v1'
            or approval.get('plan_sha256') != plan_sha
            or approval.get('scope_sha256') != plan['scope_sha256']
            or approval.get('provider_route') != plan['provider_route']
            or approval.get('model') != plan['model']
            or approval.get('limits') != plan['limits']):
        _fail('research_approval_changed')
    try:
        expires = datetime.strptime(approval['expires_at'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
    except (KeyError, TypeError, ValueError):
        _fail('research_approval_changed')
    if datetime.now(timezone.utc) >= expires:
        _fail('research_approval_expired')


def _activate_controls(root: Path):
    controls = _controls(root)
    paths = {
        'docker_session_runtime': controls / 'tools/docker_session_runtime.py',
        'producer_stop': controls / 'experiments/native-network-preflight/v2-effect-windows/producer_stop.py',
        'native_run': controls / 'experiments/native-network-preflight/v2-effect-windows/native_run.py',
    }
    for name, path in paths.items():
        if name in sys.modules:
            if Path(sys.modules[name].__file__).resolve() != path.resolve():
                _fail('control_import_origin_mismatch')
            continue
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            _fail('control_import_unavailable')
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    native = sys.modules['native_run']
    expected = controls / 'experiments/native-network-preflight/v2_connect.py'
    if Path(native.NativeRun('unused', 'unused', 1, []).argv[1]).resolve() != expected.resolve():
        _fail('connect_origin_mismatch')
    return native, sys.modules['producer_stop']


def _save_resources(root: Path, nonce: str, rows: list[dict]) -> None:
    path = _controls(root) / 'resources.json'
    if path.exists():
        prior = _read_json(path)
        daemon_id = prior.get('docker_daemon_id')
        if prior.get('nonce') != nonce or not isinstance(daemon_id, str):
            _fail('docker_daemon_pin_missing_or_changed')
    else:
        daemon_id = _docker_daemon_id()
    if _docker_daemon_id() != daemon_id:
        _fail('docker_daemon_changed')
    _write_json(path, {'nonce': nonce, 'docker_daemon_id': daemon_id, 'resources': rows})


def _docker_daemon_id() -> str:
    value = _docker('info', '--format', '{{.ID}}').stdout.decode(errors='replace').strip()
    if not 1 <= len(value) <= 128 or not value.isascii():
        _fail('docker_daemon_identity_unavailable')
    return value


def _declare_resource(root: Path, nonce: str, rows: list[dict], kind: str, name: str, role: str) -> None:
    rows.append({'kind': kind, 'name': name, 'id': None, 'role': role})
    _save_resources(root, nonce, rows)


def _seal_resource(root: Path, nonce: str, rows: list[dict], identifier: str) -> None:
    if not HEX_RE.fullmatch(identifier):
        _fail('docker_resource_id_invalid')
    if not rows or rows[-1].get('id') is not None:
        _fail('resource_declaration_missing')
    rows[-1]['id'] = identifier
    _save_resources(root, nonce, rows)


def _network(root: Path, nonce: str, rows: list[dict], role: str, *, internal: bool) -> tuple[str, str, str]:
    name = 'lrh-native-' + nonce[:12] + '-' + role
    arguments = ['network', 'create'] + (['--internal'] if internal else [])
    arguments += ['--label', LABEL + '=' + nonce, name]
    _declare_resource(root, nonce, rows, 'network', name, role)
    identifier = _docker(*arguments).stdout.decode().strip()
    _seal_resource(root, nonce, rows, identifier)
    info = _inspect('network', identifier)
    configs = (info.get('IPAM') or {}).get('Config') or []
    if (info.get('Id') != identifier or info.get('Name') != name or info.get('Driver') != 'bridge'
            or info.get('Labels', {}).get(LABEL) != nonce
            or info.get('Internal') is not internal or len(configs) != 1):
        _fail('network_boundary_invalid')
    try:
        network = ipaddress.ip_network(configs[0]['Subnet'], strict=True)
    except (KeyError, ValueError):
        _fail('network_subnet_invalid')
    if not isinstance(network, ipaddress.IPv4Network) or network.num_addresses < 32:
        _fail('network_subnet_invalid')
    relay_ip = str(network.network_address + 10)
    target_ip = str(network.network_address + 11)
    if configs[0].get('Gateway') in (relay_ip, target_ip):
        _fail('network_reserved_ip_conflict')
    return identifier, relay_ip, target_ip


def _mount(source: Path, destination: str, *, readonly: bool = False) -> str:
    source = source.resolve(strict=True)
    if any(char in str(source) for char in (',', '\n', '\r')) or not destination.startswith('/'):
        _fail('docker_mount_invalid')
    return 'type=bind,src=' + str(source) + ',dst=' + destination + (',readonly' if readonly else '')


def _create(root: Path, nonce: str, rows: list[dict], role: str, image: str, platform: str,
            network: str, ip: str | None, mounts: list[str], environment: list[str],
            command: list[str], *, workdir: str = '/workspace/project', dns_isolated: bool = True,
            workspace_tmpfs_bytes: int | None = None) -> str:
    if len({item.split('=', 1)[0] for item in environment}) != len(environment):
        _fail('container_environment_duplicate')
    name = 'lrh-native-' + nonce[:12] + '-' + role
    arguments = ['container', 'create', '--name', name, '--pull', 'never', '--platform', platform,
                 '--network', network, '--read-only', '--restart', 'no', '--log-driver', 'none',
                 '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges=true',
                 '--user', f'{os.getuid()}:{os.getgid()}', '--memory', '1g', '--cpus', '1',
                 '--pids-limit', '64', '--tmpfs', '/tmp:rw,nosuid,nodev,size=128m',
                 '--label', LABEL + '=' + nonce,
                 '--label', OWNER_LABEL + '=docker-session-v1',
                 '--label', NONCE_LABEL + '=' + nonce, '--workdir', workdir]
    if ip is not None:
        arguments += ['--ip', ip]
    if workspace_tmpfs_bytes is not None:
        arguments += ['--tmpfs', '/workspace:rw,nosuid,nodev,size=' + str(workspace_tmpfs_bytes)]
    if dns_isolated:
        arguments += ['--dns', '127.0.0.1']
    for mount in mounts:
        arguments += ['--mount', mount]
    for item in environment:
        arguments += ['--env', item]
    arguments += ['--entrypoint', command[0], image, *command[1:]]
    _declare_resource(root, nonce, rows, 'container', name, role)
    identifier = _docker(*arguments).stdout.decode().strip()
    _seal_resource(root, nonce, rows, identifier)
    info = _inspect('container', identifier)
    if (info.get('Id') != identifier or info.get('Image') != image
            or info.get('State', {}).get('Status') != 'created'
            or info.get('Name') != '/' + name
            or info.get('Config', {}).get('Image') != image
            or info.get('Config', {}).get('Labels', {}).get(LABEL) != nonce
            or info.get('Config', {}).get('User') != f'{os.getuid()}:{os.getgid()}'
            or info.get('Config', {}).get('WorkingDir') != workdir
            or info.get('Config', {}).get('Entrypoint') != [command[0]]
            or info.get('Config', {}).get('Cmd') not in ([*command[1:]], None if len(command) == 1 else [*command[1:]])
            or info.get('HostConfig', {}).get('ReadonlyRootfs') is not True
            or info.get('HostConfig', {}).get('Privileged') is not False
            or info.get('HostConfig', {}).get('CapDrop') != ['ALL']
            or 'no-new-privileges=true' not in info.get('HostConfig', {}).get('SecurityOpt', [])
            or info.get('HostConfig', {}).get('PidsLimit') != 64
            or info.get('HostConfig', {}).get('Memory') != 1024 * 1024 * 1024
            or info.get('HostConfig', {}).get('NanoCpus') != 1000000000
            or info.get('HostConfig', {}).get('LogConfig', {}).get('Type') != 'none'
            or info.get('HostConfig', {}).get('RestartPolicy', {}).get('Name') != 'no'
            or info.get('HostConfig', {}).get('Dns') != (['127.0.0.1'] if dns_isolated else [])
            or (workspace_tmpfs_bytes is not None and
                info.get('HostConfig', {}).get('Tmpfs', {}).get('/workspace') !=
                'rw,nosuid,nodev,size=' + str(workspace_tmpfs_bytes))
            or set(info.get('NetworkSettings', {}).get('Networks', {})) !=
                {str(_inspect('network', network).get('Name'))}):
        _fail('container_create_mismatch')
    network_state = next(iter(info['NetworkSettings']['Networks'].values()))
    if ip is not None and (network_state.get('IPAddress') != ip
                           and (network_state.get('IPAMConfig') or {}).get('IPv4Address') != ip):
        _fail('container_network_ip_mismatch')
    actual_mounts = {(item.get('Source'), item.get('Destination'), item.get('RW'))
                     for item in info.get('Mounts', []) if item.get('Type') == 'bind'}
    expected_mounts = set()
    for mount in mounts:
        fields = dict(part.split('=', 1) for part in mount.split(',') if '=' in part)
        expected_mounts.add((fields['src'], fields['dst'], 'readonly' not in mount.split(',')))
    if actual_mounts != expected_mounts:
        _fail('container_mount_mismatch')
    actual_env = dict(item.split('=', 1) for item in info.get('Config', {}).get('Env', []) if '=' in item)
    expected_env = dict(item.split('=', 1) for item in environment)
    inherited_rows = (_inspect('image', image).get('Config') or {}).get('Env') or []
    allowed_inherited = dict(item.split('=', 1) for item in inherited_rows if '=' in item)
    if (any(actual_env.get(key) != value for key, value in expected_env.items())
            or any(actual_env.get(key) != value for key, value in allowed_inherited.items())
            or set(actual_env) != set(expected_env) | set(allowed_inherited)
            or any(SENSITIVE_ENV.search(key) and value for key, value in actual_env.items())
            or any('PROXY' in key.upper() and key not in expected_env and value
                   for key, value in actual_env.items())
            or any(key.startswith(('LD_', 'BUN_', 'OPENCODE_'))
                   and key not in expected_env and key not in allowed_inherited and value
                   for key, value in actual_env.items())):
        _fail('container_environment_mismatch')
    return identifier


def _created_manifest(root: Path, nonce: str, rows: list[dict], producer) -> Path:
    containers = [row for row in rows if row['kind'] == 'container']
    expected_roles = ({'relay', 'researcher'} if 'setup_only' in _plan(root) else
                      {'relay', 'researcher', 'resume', 'reviewer-1', 'reviewer-2',
                       'target', 'review-target-1', 'review-target-2'})
    if ({row['role'] for row in containers} != expected_roles
            or any(row.get('id') is None for row in containers)):
        _fail('producer_set_incomplete')
    items = []
    for row in containers:
        info = _inspect('container', row['id'])
        if (info['State']['Status'] != 'created' or info['Config']['Labels'].get(LABEL) != nonce):
            _fail('producer_not_created_stopped')
        items.append({'id': row['id'], 'binding': producer.binding(info)})
    path = _controls(root) / 'producer-manifest.json'
    _write_json(path, {'version': 1, 'nonce': nonce, 'producers': items}, once=True)
    return path


def _research_environment(root: Path, base: str, relay_ip: str, target_ip: str,
                          capability: str) -> list[str]:
    proxy = 'http://run:' + capability + '@' + relay_ip + ':8080'
    no_proxy = 'localhost,127.0.0.1,::1,' + target_ip
    return [
        'HOME=/workspace/home', 'XDG_CONFIG_HOME=/workspace/config',
        'XDG_DATA_HOME=/workspace/data', 'XDG_CACHE_HOME=/workspace/cache',
        'XDG_STATE_HOME=/workspace/state', 'TMPDIR=/workspace/tmp',
        'HTTP_PROXY=' + proxy, 'HTTPS_PROXY=' + proxy,
        'http_proxy=' + proxy, 'https_proxy=' + proxy,
        'ALL_PROXY=', 'all_proxy=', 'FTP_PROXY=', 'ftp_proxy=',
        'NO_PROXY=' + no_proxy, 'no_proxy=' + no_proxy,
        'SSL_CERT_FILE=/runtime-ca.pem', 'SSL_CERT_DIR=', 'CURL_CA_BUNDLE=',
        'REQUESTS_CA_BUNDLE=', 'NODE_EXTRA_CA_CERTS=',
        'GIT_SSL_CAINFO=', 'GIT_SSL_NO_VERIFY=', 'NO_COLOR=1',
    ]


def _write_target_info(root: Path, role: str, target_ip: str, plan: dict) -> None:
    info = {
        'url': ('unix:///origin/socket/ingress.sock' if _origin_enabled(plan) else
                f'http://{target_ip}:{plan["target_port"]}'),
        'source_manifest_sha256': plan['source_manifest_sha256'],
        'role': role,
    }
    if 'source_only' in plan:
        info.pop('url')
        info.update({'kind': 'source_only', 'source': '/workspace/project',
                     'runtime': _source_runtime(plan),
                     'build_command': plan['source_only']['build_command'],
                     'execution_evidence': 'Host source-execute receipts required; tool output is unreviewed.'})
    if _origin_enabled(plan):
        info['native_origin_route'] = {
            'binary': '/origin/bin/native-origin',
            'actor_handles': ['A', 'B'] if 't01_capture' in plan else ['A', 'B', 'C'],
            'tcp_port_is_target_loopback_only': True,
        }
        if 'kanboard_capture' in plan:
            info['native_origin_route']['get'] = '/origin/bin/native-origin request A GET /'
            info['native_origin_route']['post'] = (
                'printf FORM | /origin/bin/native-origin request A POST PATH '
                'application/x-www-form-urlencoded')
        else:
            info['native_origin_route']['post'] = (
                'printf BODY | /origin/bin/native-origin request A POST '
                '/jsonrpc.php application/json')
    if 'kanboard_capture' in plan:
        info['synthetic_actor_route'] = {
            'header': 'X-Native-Actor', 'handles': ['A', 'B', 'C'],
            'form_csrf_placeholder': 'broker-managed',
            'backend_identity_and_session': 'target-owned',
        }
    if 't01_capture' in plan:
        info['synthetic_actor_route'] = {
            'header': 'X-Native-Actor', 'handles': ['A', 'B'],
            'entrypoint': 'POST /jsonrpc.php',
            'response_request_id_header': 'X-LRH-Request-ID',
            'backend_identity_and_session': 'target-owned; original same-operation origin held',
        }
        if plan.get('t01_research_mode') == 'workspace_research':
            info['url_role'] = 'protected_original_api_copy'
            info['protected_api_limits'] = [
                'JSON-RPC only', 'ordinary actors A and B only',
                'response strings and dynamic keys redacted',
                'no protected web or administrator access; effect coverage is case-specific',
            ]
            if role == 'researcher':
                info['workspace_research'] = {
                    'source': '/workspace/project', 'service_bind': '127.0.0.1',
                    'entry_paths': ['web', 'JSON-RPC'],
                    'setup': 'researcher-controlled; separate from the supplied protected API copy',
                }
    destination = 'SOURCE.json' if 'source_only' in plan else 'project/target.json'
    _write_json(root / role / destination, info, once=True)


def _capture_seed_baseline(root: Path, target: str, ids: dict[str, int]) -> str:
    """Check the staged private Kanboard state, then bind the checked DB bytes."""
    path = root / target / 'data/db.sqlite'
    try:
        path = _file(path, private=True)
        if any(sidecar.exists() or sidecar.is_symlink()
               for sidecar in (path.with_name('db.sqlite-wal'), path.with_name('db.sqlite-shm'),
                               path.with_name('db.sqlite-journal'))):
            _fail('capture_seed_baseline_invalid')
        before = _sha(path)
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)) as db:
            db.execute('PRAGMA query_only=ON')
            if db.execute('PRAGMA quick_check').fetchone() != ('ok',):
                _fail('capture_seed_baseline_invalid')
            s = db.execute('SELECT is_private,is_active FROM projects WHERE id=?',
                           (ids['s'],)).fetchone()
            q = db.execute('SELECT owner_id,is_private,is_public,token,is_active '
                           'FROM projects WHERE id=?', (ids['q'],)).fetchone()
            task = db.execute('SELECT project_id,title,is_active FROM tasks WHERE id=?',
                              (ids['t'],)).fetchone()
            b = db.execute('SELECT role,is_active FROM users WHERE id=?', (ids['b'],)).fetchone()

            def no_project_role(project_id: int, user_id: int) -> bool:
                direct = db.execute('SELECT 1 FROM project_has_users WHERE project_id=? AND user_id=?',
                                    (project_id, user_id)).fetchone()
                group = db.execute(
                    'SELECT 1 FROM project_has_groups pg JOIN group_has_users gu '
                    'ON gu.group_id=pg.group_id WHERE pg.project_id=? AND gu.user_id=?',
                    (project_id, user_id)).fetchone()
                return direct is None and group is None

            managers = [row[0] for row in db.execute(
                'SELECT u.id FROM project_has_users pu JOIN users u ON u.id=pu.user_id '
                "WHERE pu.project_id=? AND pu.role='project-manager' "
                "AND u.role='app-user' AND u.is_active=1", (ids['s'],))]
            q_owner = None if q is None else q[0]
            owner = None if q_owner is None else db.execute(
                'SELECT role,is_active FROM users WHERE id=?', (q_owner,)).fetchone()
            owner_role = None if q_owner is None else db.execute(
                'SELECT role FROM project_has_users WHERE project_id=? AND user_id=?',
                (ids['q'], q_owner)).fetchone()
            valid = (
                s == (0, 1)
                and q is not None and q[1] == 1 and q[2] == 0 and q[3] in (None, '')
                and q[4] == 1 and q_owner != ids['b']
                and owner == ('app-user', 1) and owner_role == ('project-manager',)
                and task is not None and task[0] == ids['q'] and isinstance(task[1], str)
                and bool(task[1]) and task[2] == 1
                and b == ('app-user', 1)
                and len(managers) == 1 and q_owner not in managers
                and all(no_project_role(ids['q'], manager) for manager in managers)
                and no_project_role(ids['s'], ids['b']) and no_project_role(ids['q'], ids['b'])
            )
            if not valid:
                _fail('capture_seed_baseline_invalid')
        if _sha(path) != before:
            _fail('capture_seed_baseline_invalid')
        return before
    except (OSError, sqlite3.Error, NativeResearchError, TypeError, ValueError):
        _fail('capture_seed_baseline_invalid')


def _capture_specs(root: Path, plan: dict, command: list[str], *, materialize: bool = False) -> tuple[
        dict[str, tuple[list[str], list[str], list[str]]], dict[str, str]]:
    case = _capture_mode(plan)
    if case is None:
        return {}, {}
    if command != ['php', '-S', f'0.0.0.0:{plan["target_port"]}', '-t', '/target']:
        _fail('capture_target_command_changed')
    if case == 't01':
        if plan['target_port'] == 8764:
            _fail('t01_backend_port_conflict')
        specs = {}
        for target in CAPTURE_TARGETS:
            slot = _controls(root) / 'observer' / target
            stage = _read_json(slot / 'stage.json')
            if (set(stage) != {'kind', 'target', 'research_role', 'source_manifest_sha256',
                               'image_id', 'plan_sha256', 'collector_sha256', 'broker_sha256'}
                    or stage['kind'] != 'kanboard-t01-capture-stage-v1'
                    or stage['target'] != target
                    or stage['research_role'] != {'target': 'researcher',
                                                  'review-target-1': 'reviewer-1',
                                                  'review-target-2': 'reviewer-2'}[target]
                    or stage['source_manifest_sha256'] != T01_SOURCE_SHA
                    or stage['image_id'] != plan['target_image_id']
                    or stage['plan_sha256'] != _sha(root / 'plan.json')
                    or stage['collector_sha256'] != _sha(_file(slot / 'receipt.php', private=True))
                    or stage['broker_sha256'] != _sha(_file(slot / 'broker.php', private=True))
                    or stage['collector_sha256'] != _capture_pins('t01')['collector_sha256']
                    or stage['broker_sha256'] != _capture_pins('t01')['broker_sha256']):
                _fail('t01_capture_stage_changed')
            specs[target] = ([_mount(slot / 'broker.php', '/observer/broker.php', readonly=True)],
                             ['DB_FILENAME=/target/data/db.sqlite',
                              *(['LRH_ORIGIN_INGRESS=1'] if _origin_enabled(plan) else [])],
                             ['php', '/observer/broker.php', str(plan['target_port']), '/target',
                              'http://kanboard-effect-collector:8765/receipt.php'])
        return specs, {}
    specs = {}
    db_pins = {}
    for target in CAPTURE_TARGETS:
        slot = _controls(root) / 'observer' / target
        stage = _read_json(slot / 'stage.json')
        ids = stage.get('ids')
        if (stage.get('kind') != 'kanboard-native-capture-stage-v1'
                or stage.get('target') != target
                or stage.get('plan_sha256') != _sha(root / 'plan.json')
                or stage.get('source_manifest_sha256') != CAPTURE_SOURCE_SHA
                or stage.get('controller_sha256') != CAPTURE_CONTROLLER_SHA
                or not isinstance(ids, dict) or set(ids) != {'s', 'q', 't', 'b'}
                or any(type(value) is not int or value <= 0 for value in ids.values())
                or ids['s'] == ids['q']
                or stage.get('probe_sha256') != _sha(_file(slot / 'effect.php', private=True))
                or stage.get('collector_sha256') != _sha(_file(slot / 'receipt.php', private=True))
                or stage.get('broker_sha256') != _sha(_file(slot / 'broker.php', private=True))
                or stage['probe_sha256'] != _capture_pins()['probe_sha256']
                or stage['collector_sha256'] != _capture_pins()['collector_sha256']
                or stage['broker_sha256'] != _capture_pins()['broker_sha256']):
            _fail('capture_stage_changed')
        db_pins[target] = _capture_seed_baseline(root, target, ids)
        with closing(sqlite3.connect((root / target / 'data/db.sqlite').as_uri() + '?mode=ro&immutable=1',
                                     uri=True)) as db:
            a = db.execute('SELECT u.username FROM project_has_users pu JOIN users u ON u.id=pu.user_id '
                           "WHERE pu.project_id=? AND pu.role='project-manager' "
                           "AND u.role='app-user' AND u.is_active=1", (ids['s'],)).fetchall()
            c = db.execute('SELECT u.username FROM projects p JOIN users u ON u.id=p.owner_id '
                           "WHERE p.id=? AND u.role='app-user' AND u.is_active=1", (ids['q'],)).fetchall()
            b = db.execute('SELECT username FROM users WHERE id=? AND role=? AND is_active=1',
                           (ids['b'], 'app-user')).fetchall()
        if not len(a) == len(b) == len(c) == 1:
            _fail('capture_actor_map_ambiguous')
        expected_actors = {'A': a[0][0], 'B': b[0][0], 'C': c[0][0]}
        if (len(set(expected_actors.values())) != 3
                or any(not isinstance(user, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', user)
                       for user in expected_actors.values())):
            _fail('capture_actor_map_changed')
        if not materialize:
            continue
        actor_map_path = slot / 'actors.json'
        if actor_map_path.exists():
            if _read_json(actor_map_path) != expected_actors:
                _fail('capture_actor_map_changed')
        else:
            _write_json(actor_map_path, expected_actors, once=True)
        route_path = slot / 'actor-route.json'
        route = {'kind': 'kanboard-native-actor-route-v1', 'target': target,
                 'map_sha256': _sha(actor_map_path), 'baseline_db_sha256': db_pins[target]}
        if route_path.exists():
            if _read_json(route_path) != route:
                _fail('capture_actor_map_changed')
        else:
            _write_json(route_path, route, once=True)
        mounts = [_mount(slot / 'effect.php', '/observer/effect.php', readonly=True),
                  _mount(slot / 'broker.php', '/observer/broker.php', readonly=True),
                  _mount(slot / 'actors.json', '/observer/actors.json', readonly=True)]
        environment = ['NATIVE_EFFECT_COLLECTOR=http://kanboard-effect-collector:8765/receipt.php',
                       'NATIVE_EFFECT_SOURCE_DIR=/target', 'DB_FILENAME=/target/data/db.sqlite',
                       'REVERSE_PROXY_AUTH=true', 'REVERSE_PROXY_USER_HEADER=HTTP_X_LRH_ACTOR']
        environment += ['NATIVE_EFFECT_' + key.upper() + '=' + str(ids[key])
                        for key in ('s', 'q', 't', 'b')]
        listen_port = plan['target_port']
        if listen_port == 18081:
            _fail('capture_target_port_conflict')
        listen_host = '127.0.0.1' if _origin_enabled(plan) else '0.0.0.0'
        app_command = ('php -d auto_prepend_file=/observer/effect.php -S 127.0.0.1:18081 '
                       '-t /target >/dev/null 2>&1 & '
                       'exec php /observer/broker.php ' + listen_host + ':' + str(listen_port) +
                       ' /observer/actors.json 127.0.0.1:18081')
        specs[target] = (mounts, environment, ['sh', '-c', app_command])
    return specs, db_pins


def _capture_approved_specs(root: Path, plan: dict, command: list[str], *,
                            verify_source: bool = False) -> dict[str, tuple[list[str], list[str], list[str]]]:
    if _capture_mode(plan) == 't01':
        specs, _ = _capture_specs(root, plan, command)
        approval = _read_json(_controls(root) / 'approval.json')
        if approval.get('capture_stage_sha256') != {
                target: _sha(_controls(root) / 'observer' / target / 'stage.json')
                for target in CAPTURE_TARGETS}:
            _fail('t01_capture_stage_approval_changed')
        if verify_source:
            for target in CAPTURE_TARGETS:
                _verify_target_state(root / target, plan['source_sha256'], plan['mutable_paths'])
        return specs
    _, db_pins = _capture_specs(root, plan, command)
    if db_pins:
        approval = _read_json(_controls(root) / 'approval.json')
        if (approval.get('capture_target_db_sha256') != db_pins
                or approval.get('capture_stage_sha256') != {
                    target: _sha(_controls(root) / 'observer' / target / 'stage.json')
                    for target in CAPTURE_TARGETS}):
            _fail('capture_seed_baseline_changed')
        specs, materialized_pins = _capture_specs(root, plan, command, materialize=True)
        if materialized_pins != db_pins:
            _fail('capture_seed_baseline_changed')
        if verify_source:
            for target in CAPTURE_TARGETS:
                _verify_target_state(root / target, plan['source_sha256'], plan['mutable_paths'])
        return specs
    return {}


def _preseal_setup(root: Path, plan: dict, nonce: str, rows: list[dict], port: int,
                   capability: str) -> dict:
    external, _, _ = _network(root, nonce, rows, 'external', internal=False)
    research, relay_ip, _ = _network(root, nonce, rows, 'research', internal=True)
    controls = _controls(root)
    relay = _create(root, nonce, rows, 'relay', plan['image_id'], plan['platform'],
                    external, None, [_mount(controls / 'relay', '/relay', readonly=True)],
                    ['HOST_GATEWAY_PORT=' + str(port)], ['/relay'], workdir='/', dns_isolated=False)
    _docker('network', 'connect', '--ip', relay_ip, research, relay)
    network_name = _inspect('network', research)['Name']
    actual = _inspect('container', relay)['NetworkSettings']['Networks'][network_name]
    if actual.get('IPAddress') != relay_ip and (actual.get('IPAMConfig') or {}).get('IPv4Address') != relay_ip:
        _fail('setup_relay_network_mismatch')
    environment = _research_environment(root, 'researcher', relay_ip, '127.0.0.1', capability)
    command = ['sh', '-c',
               'mkdir -p /workspace/home /workspace/config/opencode /workspace/data '
               '/workspace/cache /workspace/state /workspace/tmp /workspace/project && '
               'while :; do sleep 3600; done']
    researcher = _create(
        root, nonce, rows, 'researcher', plan['image_id'], plan['platform'], research, None,
        [_mount(root / 'original', '/source', readonly=True),
         _mount(controls / 'opencode.json', '/workspace/config/opencode/opencode.json', readonly=True),
         _mount(controls / 'runtime-ca.pem', '/runtime-ca.pem', readonly=True),
         _mount(controls / 'research', '/research', readonly=True)],
        environment, command, workdir='/',
        workspace_tmpfs_bytes=plan['setup_only']['max_workspace_bytes'])
    if set(_inspect('container', relay)['NetworkSettings']['Networks']) != {
            _inspect('network', external)['Name'], network_name}:
        _fail('setup_relay_membership_mismatch')
    return {'relay': relay, 'researcher': researcher,
            'network_names': {'research': network_name}}


def _preseal(root: Path, plan: dict, nonce: str, rows: list[dict], port: int,
             capability: str) -> dict:
    if 'setup_only' in plan:
        return _preseal_setup(root, plan, nonce, rows, port, capability)
    target_command = _validate_target_command(_controls(root) / 'target-command.json')
    capture_specs = _capture_approved_specs(root, plan, target_command)
    capture = _load_capture_module(root) if capture_specs else None
    external, _, _ = _network(root, nonce, rows, 'external', internal=False)
    research, research_relay_ip, research_target_ip = _network(
        root, nonce, rows, 'research', internal=True)
    reviews = {}
    for slot in ('reviewer-1', 'reviewer-2'):
        reviews[slot] = _network(root, nonce, rows, slot, internal=True)
    controls = _controls(root)
    platform = plan['platform']
    relay = _create(root, nonce, rows, 'relay', plan['image_id'], platform, external, None,
                    [_mount(controls / 'relay', '/relay', readonly=True)],
                    ['HOST_GATEWAY_PORT=' + str(port)], ['/relay'],
                    workdir='/', dns_isolated=False)
    network_names = {}
    for role, item in (('research', (research, research_relay_ip, research_target_ip)),
                       *((slot, reviews[slot]) for slot in ('reviewer-1', 'reviewer-2'))):
        network, relay_ip, _ = item
        _docker('network', 'connect', '--ip', relay_ip, network, relay)
        network_names[role] = _inspect('network', network)['Name']
        actual = _inspect('container', relay)['NetworkSettings']['Networks'][network_names[role]]
        if (actual.get('IPAddress') != relay_ip
                and (actual.get('IPAMConfig') or {}).get('IPv4Address') != relay_ip):
            _fail('relay_internal_ip_mismatch')
    targets = {}
    for role, item in (('target', (research, research_target_ip)),
                       ('review-target-1', (reviews['reviewer-1'][0], reviews['reviewer-1'][2])),
                       ('review-target-2', (reviews['reviewer-2'][0], reviews['reviewer-2'][2]))):
        network, ip = item
        extra_mounts, extra_env, command = capture_specs.get(role, ([], [], target_command))
        if 'source_only' in plan:
            network, ip = 'none', None
            command = ['sh', '-c', 'while :; do sleep 3600; done']
            extra_mounts = [_mount(controls / 'source-modules',
                                   _source_dependency_destination(plan), readonly=True)]
            for sub in ('tmp', 'go-build-cache'):
                (root / role / '.native-source' / sub).mkdir(parents=True, mode=0o700)
            extra_env = _source_environment('/target/.native-source', plan)
        targets[role] = _create(root, nonce, rows, role, plan['target_image_id'], platform,
                                network, ip, [_mount(root / role, '/target'), *extra_mounts],
                                ['HOME=/target', 'HTTP_PROXY=', 'HTTPS_PROXY=', 'ALL_PROXY=',
                                 'http_proxy=', 'https_proxy=', 'all_proxy=', 'NO_PROXY=*', 'no_proxy=*',
                                 *extra_env], command, workdir='/target',
                                dns_isolated=not bool(capture_specs) and 'source_only' not in plan)
        if capture is not None:
            capture.activate(root, role)
    _write_target_info(root, 'researcher', research_target_ip, plan)
    for slot in ('reviewer-1', 'reviewer-2'):
        _write_target_info(root, slot, reviews[slot][2], plan)

    def create_research(role: str, network: str, relay_ip: str, target_ip: str) -> str:
        base = root / ('researcher' if role == 'resume' else role)
        mounts = [_mount(base, '/workspace'),
                  _mount(controls / 'opencode.json', '/workspace/config/opencode/opencode.json', readonly=True),
                  _mount(controls / 'runtime-ca.pem', '/runtime-ca.pem', readonly=True)]
        if role in ('researcher', 'resume') and 'research_workflow_sha256' in plan:
            mounts.append(_mount(controls / 'research', '/research', readonly=True))
        if _origin_enabled(plan):
            mounts.extend([_mount(_origin_binary(root, plan), '/origin/bin/native-origin', readonly=True),
                           _mount(controls / 'origin/socket' / role, '/origin/socket', readonly=True)])
        if role in ('reviewer-1', 'reviewer-2'):
            mounts.append(_mount(root / 'handoff' / role, '/handoff', readonly=True))
            mounts.append(_mount(root / 'original', '/workspace/original', readonly=True))
        environment = _research_environment(root, role, relay_ip, target_ip, capability)
        if 'source_only' in plan:
            mounts.append(_mount(controls / 'source-modules',
                                 _source_dependency_destination(plan), readonly=True))
            environment.extend(_source_environment('/workspace', plan))
            if role in ('reviewer-1', 'reviewer-2'):
                mounts.append(_mount(controls / 'source-evidence' / role, '/source-evidence', readonly=True))
        return _create(root, nonce, rows, role, plan['image_id'], platform, network,
                       None, mounts, environment,
                       ['sh', '-c', 'while :; do sleep 3600; done'])

    researcher = create_research('researcher', research, research_relay_ip, research_target_ip)
    reviewers = {slot: create_research(slot, reviews[slot][0], reviews[slot][1], reviews[slot][2])
                 for slot in ('reviewer-1', 'reviewer-2')}
    resume = create_research('resume', research, research_relay_ip, research_target_ip)
    if set(_inspect('container', relay)['NetworkSettings']['Networks']) != {
            _inspect('network', external)['Name'], *network_names.values()}:
        _fail('relay_network_membership_mismatch')
    return {
        'relay': relay, 'researcher': researcher, 'resume': resume, **reviewers, **targets,
        'research_target_ip': research_target_ip,
        'review_target_ips': {slot: reviews[slot][2] for slot in reviewers},
        'network_names': network_names,
    }


def _capture_stop(root: Path, plan: dict, native_status: str) -> dict:
    if _capture_mode(plan) is None:
        return {'status': 'not_configured'}
    module = _load_capture_module(root)
    results = []
    for target in CAPTURE_TARGETS:
        ledger_path = _controls(root) / 'observer' / target / 'resources.json'
        if not ledger_path.exists():
            if native_status in ('stopped', 'closed_before_activation'):
                _fail('capture_ledger_missing_after_native_start')
            continue
        ledger = _read_json(ledger_path)
        if ledger.get('status') in ('aborted', 'removed'):
            results.append({'target': target, 'status': ledger['status']})
        elif native_status == 'stopped':
            results.append(module.freeze(root, target))
        elif native_status == 'closed_before_activation':
            results.append(module.close_startup(root, target))
        elif native_status == 'not_started':
            results.append(module.abort_activation(root, target))
        else:
            _fail('capture_native_stop_unverified')
    return {'status': 'complete', 'targets': results}


def _origin_resources_path(root: Path) -> Path:
    return _controls(root) / 'origin/resources.json'


def _origin_resolve_row(root: Path, record: dict, row: dict, *, allow_absent: bool = False) -> str | None:
    """Resolve a create interrupted before its exact ID was sealed."""
    identifier = row.get('id')
    if identifier is None:
        name = row.get('name')
        listing = _docker('container', 'ls', '-a', '--no-trunc',
                          '--filter', 'name=^/' + name + '$', '--format', '{{.ID}}')
        matches = listing.stdout.decode().splitlines()
        if not matches:
            return None
        if len(matches) != 1 or not HEX_RE.fullmatch(matches[0]):
            _fail('native_origin_resource_ambiguous')
        identifier = matches[0]
        row['id'] = identifier
        _write_json(_origin_resources_path(root), record)
    if not isinstance(identifier, str) or not HEX_RE.fullmatch(identifier):
        _fail('native_origin_resource_invalid')
    if allow_absent:
        listed = _docker('container', 'ls', '-a', '--no-trunc',
                         '--filter', 'id=' + identifier, '--format', '{{.ID}}')
        if listed.stdout.strip() == b'':
            return None
        if listed.stdout.decode().strip() != identifier:
            _fail('native_origin_resource_ambiguous')
    info = _inspect('container', identifier)
    if (info.get('Id') != identifier or info.get('Name') != '/' + row['name']
            or info.get('Config', {}).get('Labels', {}).get(LABEL) != record['nonce']
            or info.get('Config', {}).get('Labels', {}).get('io.lrh.native-origin') != row['role']):
        _fail('native_origin_resource_owner_changed')
    return identifier


def _origin_start(root: Path, plan: dict, nonce: str, bindings: dict) -> dict:
    if not _origin_enabled(plan):
        return {'status': 'not_configured'}
    binary = _origin_binary(root, plan)
    controls = _controls(root)
    rows = [{'role': role, 'target': target,
             'name': 'lrh-origin-' + nonce[:12] + '-' + role, 'id': None}
            for role, target in ORIGIN_ROLES.items()]
    ledger = {'kind': 'native-origin-resources-v1', 'nonce': nonce,
              'status': 'creating', 'resources': rows,
              'producer_manifest_sha256': _sha(controls / 'producer-manifest.json')}
    _write_json(_origin_resources_path(root), ledger, once=True)
    for row in rows:
        role, target = row['role'], row['target']
        agent_id, target_id = bindings[role], bindings[target]
        for identifier, image in ((agent_id, plan['image_id']), (target_id, plan['target_image_id'])):
            inspected = _inspect('container', identifier)
            if (inspected.get('Id') != identifier or inspected.get('Image') != image
                    or inspected.get('State', {}).get('Running') is not True
                    or inspected.get('Config', {}).get('Labels', {}).get(LABEL) != nonce):
                _fail('native_origin_namespace_owner_invalid')
        mounts = [_mount(binary, '/origin/bin/native-origin', readonly=True),
                  _mount(controls / 'origin/socket' / role, '/origin/socket'),
                  _mount(controls / 'origin/ledger' / role, '/origin/ledger'),
                  _mount(controls / 'origin/arms', '/origin/arms', readonly=True)]
        command = ['/origin/bin/native-origin', 'ingress', role, target,
                   str(plan['target_port']), '/origin/socket', '/origin/ledger',
                   '/origin/arms', str(os.getuid())]
        arguments = ['container', 'create', '--name', row['name'], '--pull', 'never',
                     '--platform', plan['platform'], '--network', 'container:' + target_id,
                     '--pid', 'container:' + agent_id, '--read-only', '--restart', 'no',
                     '--log-driver', 'none', '--cap-drop', 'ALL',
                     '--security-opt', 'no-new-privileges=true',
                     '--user', f'{os.getuid()}:{os.getgid()}',
                     '--memory', '256m', '--cpus', '0.5', '--pids-limit', '32',
                     '--label', LABEL + '=' + nonce,
                     '--label', 'io.lrh.native-origin=' + role,
                     '--env', 'LRH_RUN_NONCE=' + nonce]
        for mount in mounts:
            arguments += ['--mount', mount]
        arguments += ['--entrypoint', command[0], plan['image_id'], *command[1:]]
        identifier = _docker(*arguments).stdout.decode().strip()
        if not HEX_RE.fullmatch(identifier):
            _fail('native_origin_create_id_invalid')
        row['id'] = identifier
        _write_json(_origin_resources_path(root), ledger)
        info = _inspect('container', identifier)
        host = info.get('HostConfig', {})
        actual_mounts = {(item.get('Source'), item.get('Destination'), item.get('RW'))
                         for item in info.get('Mounts', [])}
        expected_mounts = {(str(binary), '/origin/bin/native-origin', False),
                           (str(controls / 'origin/socket' / role), '/origin/socket', True),
                           (str(controls / 'origin/ledger' / role), '/origin/ledger', True),
                           (str(controls / 'origin/arms'), '/origin/arms', False)}
        if (info.get('Id') != identifier or info.get('Image') != plan['image_id']
                or info.get('State', {}).get('Status') != 'created'
                or info.get('Name') != '/' + row['name']
                or host.get('NetworkMode') != 'container:' + target_id
                or host.get('PidMode') != 'container:' + agent_id
                or host.get('ReadonlyRootfs') is not True
                or host.get('Privileged') is not False
                or host.get('CapDrop') != ['ALL']
                or 'no-new-privileges=true' not in host.get('SecurityOpt', [])
                or actual_mounts != expected_mounts
                or info.get('Config', {}).get('Labels', {}).get(LABEL) != nonce):
            _fail('native_origin_container_topology_invalid')
        _docker('container', 'start', identifier)
        running = _inspect('container', identifier)
        socket_path = controls / 'origin/socket' / role / 'ingress.sock'
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not socket_path.exists():
            time.sleep(.05)
        if (running.get('State', {}).get('Running') is not True
                or not socket_path.exists() or not stat.S_ISSOCK(socket_path.stat().st_mode)
                or socket_path.stat().st_uid != os.getuid()
                or socket_path.stat().st_mode & 0o077):
            _fail('native_origin_socket_unavailable')
    ledger['status'] = 'active'
    _write_json(_origin_resources_path(root), ledger)
    return {'status': 'active', 'roles': list(ORIGIN_ROLES),
            'resource_ledger_sha256': _sha(_origin_resources_path(root))}


def _origin_stop(root: Path, plan: dict, native_status: str) -> dict:
    if not _origin_enabled(plan):
        return {'status': 'not_configured'}
    path = _origin_resources_path(root)
    if not path.exists():
        return {'status': 'not_started'}
    if native_status not in ('stopped', 'closed_before_activation', 'not_started'):
        _fail('native_origin_native_stop_unverified')
    record = _read_json(path)
    if (record.get('kind') != 'native-origin-resources-v1'
            or record.get('producer_manifest_sha256') != _sha(_controls(root) / 'producer-manifest.json')
            or [row.get('role') for row in record.get('resources', [])] != list(ORIGIN_ROLES)):
        _fail('native_origin_resource_ledger_invalid')
    stopped = []
    for row in record['resources']:
        identifier = _origin_resolve_row(root, record, row)
        if identifier is None:
            stopped.append({'role': row['role'], 'id': None, 'status': 'absent'})
            continue
        info = _inspect('container', identifier)
        if info.get('State', {}).get('Running') is True:
            _docker('container', 'stop', '--time', '10', identifier)
        info = _inspect('container', identifier)
        if info.get('State', {}).get('Status') not in ('exited', 'dead', 'created'):
            _fail('native_origin_container_stop_unknown')
        stopped.append({'role': row['role'], 'id': identifier,
                        'status': info['State']['Status']})
    ledger_hashes = {}
    for role in ORIGIN_ROLES:
        file = _controls(root) / 'origin/ledger' / role / 'requests.jsonl'
        ledger_hashes[role] = _sha(file) if file.exists() else None
    stop_kind = {'stopped': 'REVOKED', 'closed_before_activation': 'STARTUP_CLOSED',
                 'not_started': 'NOT_STARTED'}[native_status]
    stop_path = _controls(root) / 'native-state' / stop_kind
    if stop_kind != 'NOT_STARTED' and not stop_path.exists():
        _fail('native_origin_native_stop_unverified')
    receipt = {'kind': 'native-origin-stopped-v1', 'nonce': record['nonce'],
               'native_stop_kind': stop_kind,
               'native_stop_sha256': _sha(stop_path) if stop_kind != 'NOT_STARTED' else None,
               'producer_manifest_sha256': record['producer_manifest_sha256'],
               'containers': stopped, 'ledger_sha256': ledger_hashes}
    output = _controls(root) / 'origin/stopped.json'
    if output.exists():
        if _read_json(output) != receipt:
            _fail('native_origin_stop_receipt_changed')
    else:
        _write_json(output, receipt, once=True)
    record['status'] = 'stopped'
    _write_json(path, record)
    return {'status': 'complete' if stop_kind != 'NOT_STARTED' and
            all(row['id'] for row in stopped) else 'partial',
            'receipt_sha256': _sha(output)}


def _origin_cleanup(root: Path, plan: dict) -> dict:
    if not _origin_enabled(plan):
        return {'status': 'not_configured'}
    path = _origin_resources_path(root)
    if not path.exists():
        return {'status': 'not_started'}
    record = _read_json(path)
    if record.get('status') not in ('stopped', 'cleanup_unknown', 'removed'):
        _fail('native_origin_not_stopped')
    for row in reversed(record['resources']):
        identifier = _origin_resolve_row(root, record, row, allow_absent=True)
        if identifier is None:
            continue
        info = _inspect('container', identifier)
        if info.get('State', {}).get('Running') is True:
            _fail('native_origin_still_running')
        _docker('container', 'rm', identifier)
        listed = _docker('container', 'ls', '-a', '--no-trunc',
                         '--filter', 'id=' + identifier, '--format', '{{.ID}}')
        if listed.stdout.strip():
            record['status'] = 'cleanup_unknown'
            _write_json(path, record)
            _fail('native_origin_cleanup_unknown')
    for role in ORIGIN_ROLES:
        (_controls(root) / 'origin/socket' / role / 'ingress.sock').unlink(missing_ok=True)
    record['status'] = 'removed'
    _write_json(path, record)
    receipt = {'kind': 'native-origin-cleanup-v1', 'nonce': record['nonce'],
               'stopped_sha256': _sha(_controls(root) / 'origin/stopped.json'),
               'resource_ids': [row['id'] for row in record['resources']],
               'all_absent': True}
    output = _controls(root) / 'origin/cleanup.json'
    if output.exists():
        if _read_json(output) != receipt:
            _fail('native_origin_cleanup_receipt_changed')
    else:
        _write_json(output, receipt, once=True)
    return {'status': 'complete', 'receipt_sha256': _sha(output)}


def _capture_cleanup(root: Path, plan: dict) -> dict:
    if _capture_mode(plan) is None:
        return {'status': 'not_configured'}
    module = _load_capture_module(root)
    results = []
    for target in CAPTURE_TARGETS:
        ledger_path = _controls(root) / 'observer' / target / 'resources.json'
        if not ledger_path.exists():
            continue
        ledger = _read_json(ledger_path)
        if ledger.get('status') == 'aborted':
            results.append({'target': target, 'status': 'aborted'})
        elif ledger.get('status') == 'removed':
            results.append({'target': target, 'status': 'removed'})
        else:
            results.append(module.cleanup(root, target))
    return {'status': 'complete', 'targets': results}


def _cleanup_resources(root: Path, *, require_created: bool = False) -> dict:
    record = _read_json(_controls(root) / 'resources.json')
    if record.get('docker_daemon_id') is not None and _docker_daemon_id() != record['docker_daemon_id']:
        _fail('docker_daemon_changed')
    nonce = record.get('nonce')
    if not isinstance(nonce, str) or not re.fullmatch(r'[0-9a-f]{32}', nonce):
        _fail('resource_record_invalid')
    results = []
    def absent(kind: str, value: str) -> bool:
        if kind == 'container':
            result = _docker('container', 'ls', '-a', '--no-trunc', '--filter', 'id=' + value,
                             '--format', '{{.ID}}')
        else:
            result = _docker('network', 'ls', '--no-trunc', '--filter', 'id=' + value,
                             '--format', '{{.ID}}')
        return not result.stdout.strip()

    for row in reversed(record.get('resources', [])):
        kind, name, identifier = row.get('kind'), row.get('name'), row.get('id')
        if kind not in ('container', 'network') or not isinstance(name, str):
            _fail('resource_record_invalid')
        if identifier is None:
            # The create call may have succeeded before its id was durably sealed.
            try:
                info = _inspect(kind, name)
            except NativeResearchError:
                # An unsealed create may be absent, but do not infer that from inspect failure alone.
                listing = (_docker('container', 'ls', '-a', '--no-trunc', '--filter', 'name=^/' + name + '$',
                                   '--format', '{{.ID}}') if kind == 'container' else
                           _docker('network', 'ls', '--no-trunc', '--filter', 'name=^' + name + '$',
                                   '--format', '{{.ID}}'))
                if listing.stdout.strip():
                    _fail('resource_cleanup_unsealed_ambiguous')
                results.append({'kind': kind, 'name': name, 'absent': True})
                continue
            identifier = info.get('Id')
        try:
            info = _inspect(kind, identifier)
        except NativeResearchError:
            if not absent(kind, identifier):
                _fail('resource_cleanup_inspection_ambiguous')
            results.append({'kind': kind, 'name': name, 'absent': True})
            continue
        labels = (info.get('Config', {}).get('Labels') if kind == 'container' else info.get('Labels')) or {}
        actual_name = info.get('Name', '').lstrip('/')
        if (info.get('Id') != identifier or actual_name != name
                or labels.get(LABEL) != nonce):
            _fail('resource_cleanup_identity_mismatch')
        if require_created and kind == 'container' and info.get('State', {}).get('Status') != 'created':
            _fail('prestart_resource_not_created_stopped')
        if (kind == 'container' and not require_created
                and info.get('State', {}).get('Running') is True
                and info.get('State', {}).get('Paused') is not True):
            _fail('resource_restarted_after_stop')
        command = ('container', 'rm', '-f', identifier) if kind == 'container' else ('network', 'rm', identifier)
        _docker(*command)
        if not absent(kind, identifier):
            _fail('resource_cleanup_not_absent')
        results.append({'kind': kind, 'name': name, 'absent': True})
    result = {'status': 'complete', 'resources': results}
    _write_json(_controls(root) / 'cleanup.json', result)
    return result


def _provider_snapshot(root: Path) -> dict:
    path = _controls(root) / 'provider/tunnel.sqlite3'
    if not path.exists() or path.is_symlink():
        _fail('provider_ledger_unavailable')
    connection = sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True, timeout=1)
    try:
        row = connection.execute('SELECT config,created,bytes FROM pool').fetchone()
        if row is None:
            _fail('provider_pool_unavailable')
        config = json.loads(row[0])
        used = connection.execute('SELECT count(*) FROM tunnels').fetchone()[0]
        phases = connection.execute('SELECT phase,count(*) FROM tunnels GROUP BY phase').fetchall()
        return {'config': config, 'created': row[1], 'used_tunnels': used,
                'charged_tunnel_bytes': row[2], 'tunnel_phases': dict(phases)}
    finally:
        connection.close()


def run_active(run_root: Path) -> bool:
    root = _private_root(Path(run_root))
    native, _ = _activate_controls(root)
    return native.active(_controls(root) / 'native-state')


def allowance_snapshot(run_root: Path) -> dict:
    root = _private_root(Path(run_root))
    native, _ = _activate_controls(root)
    run = native.snapshot(_controls(root) / 'native-state')
    pool = _provider_snapshot(root)
    config = pool['config']
    planned_limits = _plan(root)['limits']
    planned = planned_limits['duration_seconds']
    linked = (_controls(root) / 'approval.json').exists() and _read_json(
        _controls(root) / 'approval.json').get('kind') == 'native-setup-approval-v2'
    if (config.get('authority') != AUTHORITY or config.get('producer_manifest_sha256') != run['manifest_sha256']
            or config.get('max_connections') != planned_limits['max_connections']
            or config.get('max_bytes') != planned_limits['max_bytes']
            or type(config.get('native_run_duration')) is not int
            or config.get('duration') != config['native_run_duration']
            or (not 1 <= config['native_run_duration'] <= planned if linked else
                config['native_run_duration'] != planned)):
        _fail('shared_allowance_identity_mismatch')
    return {'run_identity': {key: run[key] for key in
                            ('manifest_sha256', 'nonce', 'ids', 'deadline_monotonic', 'created_monotonic')},
            'hard_limits': {'max_connections': config['max_connections'],
                            'max_bytes': config['max_bytes'], 'duration_seconds': config['duration']},
            'used_tunnels': pool['used_tunnels'],
            'charged_tunnel_bytes': pool['charged_tunnel_bytes'],
            'provider_deadline_unix': pool['created'] + config['duration'],
            'active': native.active(_controls(root) / 'native-state'),
            'provider_request_count': None, 'monetary_spend': None}


def _resources(root: Path) -> dict:
    record = _read_json(_controls(root) / 'resources.json')
    if any(row.get('id') is None for row in record.get('resources', [])):
        _fail('unsealed_resource_record')
    result = {row['role']: row['id'] for row in record['resources'] if row['kind'] == 'container'}
    if 'setup_only' in _plan(root) and 'researcher' in result:
        result['resume'] = result['researcher']
    return result


@contextmanager
def _turn_lock(root: Path):
    path = _controls(root) / 'turn.lock'
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


@contextmanager
def _owner_lock(root: Path):
    descriptor = os.open(_controls(root) / 'owner.lock',
                         os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            _fail('live_owner_present')
        yield
    finally:
        os.close(descriptor)


def _origin_arm(root: Path, plan: dict, role: str, dispatch_id: str,
                gate_nonce: str, root_pid: int, root_start: int) -> dict:
    if (role not in ORIGIN_ROLES or not re.fullmatch(r'[0-9a-f]{32}', dispatch_id)
            or not re.fullmatch(r'[0-9a-f]{32}', gate_nonce)
            or root_pid <= 1 or root_start <= 0):
        _fail('native_origin_gate_marker_invalid')
    controls = _controls(root)
    dispatch = _read_json(controls / 'dispatch' / (dispatch_id + '.pre.json'))
    resources = _read_json(_origin_resources_path(root))
    if (dispatch.get('status') != 'unknown_effect' or dispatch.get('role') != role
            or resources.get('status') != 'active'
            or [row.get('role') for row in resources.get('resources', [])] != list(ORIGIN_ROLES)):
        _fail('native_origin_dispatch_not_armed')
    registration = {'kind': 'native-origin-registration-v1',
                    'dispatch_id': dispatch_id, 'role': role,
                    'target': ORIGIN_ROLES[role], 'gate_nonce': gate_nonce,
                    'root_pid': root_pid, 'root_starttime': root_start,
                    'run_nonce': resources['nonce'],
                    'agent_container_id': _resources(root)[role],
                    'target_container_id': _resources(root)[ORIGIN_ROLES[role]],
                    'sidecar_container_id': next(row['id'] for row in resources['resources']
                                                 if row['role'] == role),
                    'dispatch_pre_sha256': _sha(controls / 'dispatch' / (dispatch_id + '.pre.json')),
                    'producer_manifest_sha256': _sha(controls / 'producer-manifest.json'),
                    'source_manifest_sha256': plan['source_manifest_sha256'],
                    'target_image_id': plan['target_image_id'],
                    'binary_sha256': plan['native_origin']['binary_sha256']}
    path = controls / 'origin/registrations' / (dispatch_id + '.json')
    _write_json(path, registration, once=True)
    arm = {'kind': 'native-origin-arm-v1', 'status': 'armed',
           'role': role, 'target': ORIGIN_ROLES[role],
           'run_nonce': resources['nonce'], 'dispatch_id': dispatch_id,
           'gate_nonce': gate_nonce, 'root_pid': root_pid,
           'root_starttime': root_start, 'heartbeat_unix_ms': int(time.time() * 1000)}
    _write_json(controls / 'origin/arms' / (role + '.json'), arm)
    return arm


def _origin_disarm(root: Path, role: str, arm: dict) -> None:
    closed = dict(arm)
    closed['status'] = 'closed'
    closed['heartbeat_unix_ms'] = int(time.time() * 1000)
    _write_json(_controls(root) / 'origin/arms' / (role + '.json'), closed)


def _origin_close_window(root: Path, target: str, dispatch_id: str) -> Path:
    """Seal the app collector end boundary before a later native turn starts."""
    controls = _controls(root)
    window_path = controls / 'observer' / target / ('window-' + dispatch_id + '.json')
    window = _read_json(window_path)
    topology = window.get('topology')
    if (window.get('dispatch_id') != dispatch_id or not isinstance(topology, dict)
            or not isinstance(topology.get('collector_db'), str)):
        _fail('native_origin_window_invalid')
    collector = _file(Path(topology['collector_db']), private=True)
    with closing(sqlite3.connect(collector.as_uri() + '?mode=ro', uri=True)) as db:
        rows = db.execute('SELECT id,peer,payload FROM receipts ORDER BY id').fetchall()
    before = window.get('collector_max_id_before')
    prefix = [row for row in rows if type(before) is int and row[0] <= before]
    if (type(before) is not int or before < 0
            or len(prefix) != window.get('collector_count_before')
            or hashlib.sha256(json.dumps(prefix, separators=(',', ':'),
                                         ensure_ascii=True).encode()).hexdigest() !=
               window.get('collector_prefix_sha256')
            or len(rows) > 5000):
        _fail('native_origin_window_prefix_changed')
    receipt = {'kind': 'native-origin-window-close-v1', 'target': target,
               'dispatch_id': dispatch_id, 'window_sha256': _sha(window_path),
               'collector_count_after': len(rows),
               'collector_max_id_after': rows[-1][0] if rows else 0,
               'collector_prefix_sha256_after': hashlib.sha256(
                   json.dumps(rows, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()}
    path = controls / 'origin/window-close' / (dispatch_id + '.json')
    _write_json(path, receipt, once=True)
    return path


@contextmanager
def _poststop_read_lock(root: Path):
    """Exclude an owner without creating or changing a stopped run artifact."""
    path = _file(_controls(root) / 'owner.lock', private=True)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            _fail('live_owner_present')
        yield
    finally:
        os.close(descriptor)


def _native_exec(root: Path, role: str, argv: list[str], timeout_seconds: int,
                 *, origin_dispatch: str | None = None) -> subprocess.CompletedProcess[bytes]:
    if role not in ('researcher', 'resume', 'reviewer-1', 'reviewer-2'):
        _fail('native_role_invalid')
    plan = _verified_plan(root)
    identifier = _resources(root)[role]
    info = _inspect('container', identifier)
    if (info.get('Image') != plan['image_id'] or info.get('State', {}).get('Running') is not True
            or info.get('Config', {}).get('Labels', {}).get(LABEL) !=
            _read_json(_controls(root) / 'resources.json')['nonce']):
        _fail('native_container_identity_invalid')
    native, _ = _activate_controls(root)
    state = _controls(root) / 'native-state'
    origin = _origin_enabled(plan) and argv[0] == 'run'
    if origin and origin_dispatch is None:
        _fail('native_origin_dispatch_missing')
    if origin_dispatch is not None and not origin:
        _fail('native_origin_dispatch_unexpected')
    gate_nonce = uuid.uuid4().hex if origin else None
    command = [str(DOCKER_BINARY), 'container', 'exec',
               *(['-i'] if origin else []), '-w', '/workspace/project', identifier,
               *(['/origin/bin/native-origin', 'gate', gate_nonce] if origin else
                 ['/usr/local/bin/opencode']), *argv]
    with native.dispatch_guard(state):
        try:
            child = subprocess.Popen(command, stdin=subprocess.PIPE if origin else subprocess.DEVNULL,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     env={key: value for key, value in os.environ.items()
                                          if key in ('HOME', 'PATH', 'DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_CONFIG')})
        except OSError:
            _fail('native_dispatch_unknown_effect')
    arm = None
    heartbeat_stop = threading.Event()
    heartbeat_errors = []
    heartbeat_thread = None
    try:
        if origin:
            if not select.select([child.stdout], [], [], 10)[0]:
                _fail('native_origin_gate_marker_missing')
            marker = child.stdout.readline(128).decode('ascii', errors='strict').strip().split('\t')
            if (len(marker) != 4 or marker[0] != 'LRH_GATE' or marker[1] != gate_nonce
                    or not marker[2].isdigit() or not marker[3].isdigit()):
                _fail('native_origin_gate_marker_invalid')
            arm = _origin_arm(root, plan, role, origin_dispatch, gate_nonce,
                              int(marker[2]), int(marker[3]))

            def refresh() -> None:
                while not heartbeat_stop.wait(1):
                    try:
                        arm['heartbeat_unix_ms'] = int(time.time() * 1000)
                        _write_json(_controls(root) / 'origin/arms' / (role + '.json'), arm)
                    except Exception as error:
                        heartbeat_errors.append(str(error))
                        return

            heartbeat_thread = threading.Thread(target=refresh, daemon=True)
            heartbeat_thread.start()
            child.stdin.write(b'G')
            child.stdin.flush()
            child.stdin.close()
            child.stdin = None
        stdout, stderr = child.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        heartbeat_stop.set()
        child.terminate()
        try:
            child.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.communicate()
        _fail('native_dispatch_timeout_unknown_effect')
    except Exception:
        heartbeat_stop.set()
        child.terminate()
        try:
            child.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.communicate()
        raise
    finally:
        heartbeat_stop.set()
        if heartbeat_thread is not None:
            heartbeat_thread.join()
        if arm is not None:
            _origin_disarm(root, role, arm)
    if heartbeat_errors:
        _fail('native_origin_heartbeat_failed_unknown_effect')
    if len(stdout) > 16 * 1024 * 1024 or len(stderr) > 1024 * 1024:
        _fail('native_dispatch_output_oversize_unknown_effect')
    return subprocess.CompletedProcess(command, child.returncode, stdout, stderr)


def native_api(run_root: Path, role: str, *parts: str) -> dict:
    root = _private_root(Path(run_root))
    if (not parts or parts[0] not in ('session.create', 'session.list', 'session.get', 'session.message.list')
            or len(parts) > 12 or any(not isinstance(part, str) or len(part) > 4096 for part in parts)):
        _fail('native_api_call_not_allowed')
    with _turn_lock(root):
        if 'setup_only' in _plan(root):
            _setup_output_open(root)
        _approval_active(root)
        if not run_active(root):
            _fail('native_run_closed_before_dispatch')
        if _unresolved_dispatches(root):
            _fail('prior_dispatch_unknown_effect')
        result = _native_exec(root, role, ['api', '--standalone', *parts], 90)
    if result.returncode:
        _fail('native_api_effect_unknown')
    try:
        value = json.loads(result.stdout)
    except (UnicodeError, ValueError):
        _fail('native_api_response_invalid')
    if not isinstance(value, dict):
        _fail('native_api_response_invalid')
    return value


def _summarize_native(stdout: str, session_id: str) -> dict:
    events = []
    for line in stdout.splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            _fail('native_jsonl_invalid')
        if not isinstance(item, dict):
            _fail('native_jsonl_invalid')
        events.append(item)
    if not events or session_id not in {item.get('sessionID') for item in events}:
        _fail('native_session_evidence_missing')
    parts = [item['part'] for item in events if isinstance(item.get('part'), dict)]
    if any(item.get('type') == 'error' or item.get('error') for item in events) or any(
            item.get('error') or (item.get('type') == 'tool' and
            isinstance(item.get('state'), dict) and item['state'].get('status') in ('error', 'failed'))
            for item in parts):
        _fail('native_event_error_unknown_effect')
    event_names = {'step_finish', 'step_start', 'text', 'tool_use', 'error'}
    tool_names = {'read', 'glob', 'grep', 'edit', 'write', 'shell', 'patch', 'question',
                  'skill', 'subagent', 'webfetch', 'websearch'}
    return {'event_types': sorted({item.get('type') if item.get('type') in event_names else 'other'
                                   for item in events}),
            'tool_names': sorted({item.get('tool') if item.get('tool') in tool_names else 'other'
                                  for item in parts if item.get('type') == 'tool'}),
            'tool_count': sum(item.get('type') == 'tool' for item in parts)}


def _protected_trace(stdout: str, session_id: str) -> dict:
    """Preserve native event order and hashes without storing model or tool text."""
    rows = []
    for number, line in enumerate(stdout.splitlines(), 1):
        event = json.loads(line)
        part = event.get('part') if isinstance(event.get('part'), dict) else {}
        state = part.get('state') if isinstance(part.get('state'), dict) else {}
        row = {'line': number,
               'event_type': event.get('type') if event.get('type') in
               ('step_finish', 'step_start', 'text', 'tool_use', 'error') else 'other',
               'session_matches': event.get('sessionID') == session_id,
               'part_type': part.get('type') if part.get('type') in
               ('step-finish', 'step-start', 'text', 'tool', 'error', 'usage') else 'other'}
        if part.get('type') == 'tool':
            row.update({'tool': part.get('tool') if part.get('tool') in
                        ('read', 'glob', 'grep', 'edit', 'write', 'shell', 'patch', 'question',
                         'skill', 'subagent', 'webfetch', 'websearch') else 'other',
                        'status': state.get('status') if state.get('status') in
                        ('completed', 'running', 'pending', 'error', 'failed') else 'other',
                        'input_sha256': hashlib.sha256(json.dumps(state.get('input'), sort_keys=True,
                                                          default=str).encode()).hexdigest(),
                        'output_sha256': hashlib.sha256(json.dumps(state.get('output'), sort_keys=True,
                                                           default=str).encode()).hexdigest()})
        elif part.get('type') == 'text':
            row['text_sha256'] = hashlib.sha256(str(part.get('text', '')).encode()).hexdigest()
        rows.append(row)
    return {'kind': 'protected-native-event-trace-v1', 'session_id': session_id,
            'source': 'actual opencode run --format json stdout',
            'stdout_sha256': hashlib.sha256(stdout.encode()).hexdigest(), 'events': rows}


def _native_response_ids(stdout: str) -> list[str]:
    """Read only completed native tool output, never model text, for T01 joins."""
    found = set()
    for line in stdout.splitlines():
        event = json.loads(line)
        part = event.get('part') if isinstance(event, dict) else None
        state = part.get('state') if isinstance(part, dict) else None
        if (not isinstance(part, dict) or part.get('type') != 'tool' or
                not isinstance(state, dict) or state.get('status') != 'completed'):
            continue
        output = state.get('output')
        if output is None:
            continue
        rendered = output if isinstance(output, str) else json.dumps(output, sort_keys=True)
        found.update(re.findall(r'(?i)X-LRH-Request-ID:\s*([0-9a-f]{32})', rendered))
    return sorted(item.lower() for item in found)


def _native_response_claims(stdout: str) -> list[dict]:
    """Retain only broker IDs and hashes from completed native tool events."""
    claims = []
    for number, line in enumerate(stdout.splitlines(), 1):
        event = json.loads(line)
        part = event.get('part') if isinstance(event, dict) else None
        state = part.get('state') if isinstance(part, dict) else None
        if (not isinstance(part, dict) or part.get('type') != 'tool' or
                not isinstance(state, dict) or state.get('status') != 'completed'):
            continue
        output = state.get('output')
        rendered = output if isinstance(output, str) else json.dumps(output, sort_keys=True)
        ids = sorted(set(item.lower() for item in re.findall(
            r'(?i)X-LRH-Request-ID:\s*([0-9a-f]{32})', rendered)))
        if ids:
            claims.append({'line': number, 'tool': part.get('tool') if part.get('tool') in
                           ('shell', 'read', 'webfetch') else 'other',
                           'input_sha256': hashlib.sha256(json.dumps(state.get('input'), sort_keys=True,
                                                         default=str).encode()).hexdigest(),
                           'output_sha256': hashlib.sha256(json.dumps(output, sort_keys=True,
                                                          default=str).encode()).hexdigest(),
                           'request_ids': ids})
    return claims


def _unresolved_dispatches(root: Path) -> list[str]:
    unresolved = []
    for path in (_controls(root) / 'dispatch').glob('*.json'):
        if path.name.endswith(('.trace.json', '.pre.json', '.origin.json')):
            continue
        record = _read_json(path)
        if record.get('status') == 'unknown_effect':
            unresolved.append(record.get('dispatch_id', path.stem))
    for path in (_controls(root) / 'source-executions').glob('*/receipt.json'):
        if _read_json(path).get('status') == 'unknown_effect':
            unresolved.append(path.parent.name)
    return sorted(unresolved)


def _setup_dispatches(root: Path) -> list[dict]:
    rows = []
    for path in (_controls(root) / 'dispatch').glob('*.json'):
        if path.name.endswith(('.trace.json', '.pre.json', '.origin.json')):
            continue
        row = _read_json(path)
        if row.get('role') in ('researcher', 'resume'):
            if (row.get('kind') != 'native-dispatch-v1'
                    or row.get('dispatch_id') != path.stem
                    or type(row.get('setup_sequence')) is not int
                    or row['setup_sequence'] < 1):
                _fail('setup_dispatch_order_invalid')
            rows.append(row)
    rows.sort(key=lambda row: row['setup_sequence'])
    if [row['setup_sequence'] for row in rows] != list(range(1, len(rows) + 1)):
        _fail('setup_dispatch_order_invalid')
    return rows


def _setup_checkpoint(root: Path, record: dict) -> str:
    """Freeze the bounded proposal state before acknowledging a setup turn."""
    controls = _controls(root)
    final = controls / 'setup-checkpoints' / record['dispatch_id']
    staging_root = controls / 'setup-checkpoint-staging'
    staging_root.mkdir(mode=0o700, exist_ok=True)
    final.parent.mkdir(mode=0o700, exist_ok=True)
    staging = staging_root / uuid.uuid4().hex
    staging.mkdir(mode=0o700)
    identifier = _resources(root)['researcher']
    files = {}
    script = ('if [ -L "$1" ]; then exit 3; elif [ -f "$1" ]; then '
              'head -c 1048577 "$1"; elif [ -e "$1" ]; then exit 3; else exit 4; fi')
    for name in SETUP_OUTPUT_FILES:
        argv = ('container', 'exec', identifier, 'sh', '-c', script,
                'setup-checkpoint', '/workspace/project/' + name)
        first = _docker(*argv, timeout=20, allow_failure=True)
        second = _docker(*argv, timeout=20, allow_failure=True)
        if (first.returncode != second.returncode or first.stdout != second.stdout
                or first.returncode not in (0, 4) or len(first.stdout) > 1024 * 1024):
            _fail('setup_checkpoint_unstable')
        if first.returncode == 4:
            files[name] = None
            continue
        try:
            content = first.stdout.decode('utf-8')
        except UnicodeError:
            _fail('setup_checkpoint_encoding_invalid')
        if CREDENTIAL_TEXT.search(content):
            _fail('setup_checkpoint_credential_like')
        target = staging / name
        target.write_bytes(first.stdout)
        target.chmod(0o600)
        files[name] = _sha(target)
    receipt = {'kind': 'native-setup-checkpoint-v1',
               'plan_sha256': _sha(root / 'plan.json'),
               'approval_sha256': _sha(controls / 'approval.json'),
               'dispatch_id': record['dispatch_id'],
               'native_trace_sha256': record['native_trace_sha256'],
               'pool_after': record['pool_after'], 'files': files}
    _write_json(staging / 'receipt.json', receipt, once=True)
    os.rename(staging, final)
    descriptor = os.open(final.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return _sha(final / 'receipt.json')


def _verified_setup_checkpoint(root: Path, dispatch: dict) -> tuple[Path, dict]:
    controls = _controls(root)
    path = controls / 'setup-checkpoints' / dispatch['dispatch_id']
    receipt_path = path / 'receipt.json'
    receipt = _read_json(receipt_path)
    trace = controls / 'dispatch' / (dispatch['dispatch_id'] + '.trace.json')
    if (receipt.get('kind') != 'native-setup-checkpoint-v1'
            or receipt.get('plan_sha256') != _sha(root / 'plan.json')
            or receipt.get('approval_sha256') != _sha(controls / 'approval.json')
            or receipt.get('dispatch_id') != dispatch['dispatch_id']
            or receipt.get('native_trace_sha256') != dispatch.get('native_trace_sha256')
            or receipt.get('native_trace_sha256') != _sha(trace)
            or receipt.get('pool_after') != dispatch.get('pool_after')
            or dispatch.get('checkpoint_sha256') != _sha(receipt_path)
            or not isinstance(receipt.get('files'), dict)
            or set(receipt['files']) != set(SETUP_OUTPUT_FILES)):
        _fail('setup_checkpoint_changed')
    for name, digest in receipt['files'].items():
        target = path / name
        if digest is None:
            if target.exists() or target.is_symlink():
                _fail('setup_checkpoint_changed')
        elif (not isinstance(digest, str) or not HEX_RE.fullmatch(digest)
              or target.stat().st_size > 1024 * 1024 or _sha(_file(target, private=True)) != digest):
            _fail('setup_checkpoint_changed')
    return path, receipt


def _setup_output_open(root: Path) -> None:
    if (_controls(root) / 'setup-output').exists():
        _fail('setup_output_already_frozen')


def _research_context(root: Path, continuity: str, *, pool: dict | None = None) -> dict | None:
    """Project current authority into advice; never treat notes as authority."""
    plan = _plan(root)
    if 'research_workflow_sha256' not in plan:
        if continuity == 'fresh_context_from_workspace':
            _fail('portable_research_requires_new_prepare')
        return None
    plan = _verified_plan(root)
    _approval_active(root)
    if _unresolved_dispatches(root):
        _fail('prior_dispatch_unknown_effect')
    try:
        if not run_active(root):
            _fail('research_allowance_inactive')
        pool = allowance_snapshot(root) if pool is None else pool
        if pool.get('active') is not True:
            _fail('research_allowance_inactive')
        identity, limits = pool['run_identity'], pool['hard_limits']
        used_connections, used_bytes = pool['used_tunnels'], pool['charged_tunnel_bytes']
        now = time.monotonic()
        provider_now, provider_deadline = time.time(), pool['provider_deadline_unix']
        numbers = (identity['created_monotonic'], identity['deadline_monotonic'], now,
                   limits['duration_seconds'], limits['max_connections'], limits['max_bytes'],
                   used_connections, used_bytes, provider_now, provider_deadline)
        if any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in numbers):
            _fail('research_allowance_unavailable')
        remaining = {'remaining_connections': max(0, limits['max_connections'] - used_connections),
                     'remaining_bytes': max(0, limits['max_bytes'] - used_bytes),
                     'remaining_seconds': max(0, min(identity['deadline_monotonic'] - now,
                                                     provider_deadline - provider_now))}
        if any(value <= 0 for value in remaining.values()):
            _fail('research_allowance_exhausted')
    except (KeyError, TypeError, ValueError, OverflowError, OSError, sqlite3.Error):
        _fail('research_allowance_unavailable')
    except NativeResearchError as error:
        if str(error) not in ('research_allowance_inactive', 'research_allowance_exhausted'):
            _fail('research_allowance_unavailable')
        raise
    dispatches = sorted((_controls(root) / 'dispatch').glob('*.json'))
    if len(dispatches) > 4096:
        _fail('research_dispatch_inventory_limit')
    prior = []
    for path in dispatches:
        if not re.fullmatch(r'[0-9a-f]{32}\.json', path.name):
            continue
        row = _read_json(path)
        if (row.get('dispatch_id') != path.stem or row.get('status') != 'acknowledged'
                or row.get('role') not in ('researcher', 'resume', 'reviewer-1', 'reviewer-2')):
            _fail('research_dispatch_inventory_invalid')
        prior.append({key: row[key] for key in ('dispatch_id', 'role', 'status')})
    return {'kind': 'portable-research-run-snapshot-v1', 'continuity': continuity,
            'authority': 'Advisory snapshot at dispatch time only; host controls remain authoritative.',
            'captured_monotonic': now, 'captured_unix': provider_now,
            'plan_sha256': _sha(root / 'plan.json'),
            'source_manifest_sha256': plan['source_manifest_sha256'],
            'scope_sha256': plan['scope_sha256'], 'brief_sha256': plan['brief_sha256'],
            'workflow_sha256': plan['research_workflow_sha256'],
            'workspace': 'researcher', 'notebook': '/workspace/RESEARCH.md',
            'run_identity': identity,
            'allowance': {**limits, 'used_connections': used_connections, 'used_bytes': used_bytes,
                          'spent_seconds': max(0, now - identity['created_monotonic']), **remaining,
                          'provider_deadline_unix': provider_deadline,
                          'provider_request_count': None, 'monetary_spend': None},
            'prior_dispatches': prior, 'review': None, 'cleanup': None,
            'review_and_cleanup_status': 'unassessed; consult the operator, not this snapshot'}


def invoke_native(run_root: Path, role: str, session_id: str, prompt: str,
                  include_raw: bool = False, before_dispatch=None,
                  kanboard_role_grant: bool = False, continuity: str | None = None) -> dict:
    root = _private_root(Path(run_root))
    if (role not in ('researcher', 'resume', 'reviewer-1', 'reviewer-2')
            or not SESSION_RE.fullmatch(session_id) or not isinstance(prompt, str)
            or not 1 <= len(prompt.encode()) <= 128 * 1024):
        _fail('native_turn_input_invalid')
    if CREDENTIAL_TEXT.search(prompt):
        _fail('native_prompt_credential_like')
    if before_dispatch is not None and not callable(before_dispatch):
        _fail('native_observer_hook_invalid')
    setup_only = 'setup_only' in _plan(root)
    if kanboard_role_grant and role != 'resume':
        _fail('kanboard_recovery_turn_unqualified')
    if setup_only and continuity is not None and continuity not in ('fresh_setup', 'setup_resume'):
        _fail('setup_continuity_invalid')
    if not setup_only and continuity is not None and continuity not in (
            ('fresh_research',) if role == 'researcher' else
            ('native_history', 'fresh_context_from_workspace') if role == 'resume' else ()):
        _fail('research_continuity_invalid')
    if role.startswith('reviewer-'):
        target = 'review-target-' + role[-1]
        plan = _plan(root)
        if 'source_only' in plan:
            _verify_inventory(root / 'original', plan['source_sha256'])
        else:
            _verify_target_state(root / target, plan['source_sha256'], plan['mutable_paths'])
        target_id = _resources(root)[target]
        source_digest = plan['source_manifest_sha256']
    else:
        target_id = None
        source_digest = None
    dispatch_id = uuid.uuid4().hex
    record_path = _controls(root) / 'dispatch' / (dispatch_id + '.json')
    record = {'kind': 'native-dispatch-v1', 'status': 'unknown_effect',
              'dispatch_id': dispatch_id, 'role': role, 'session_id': session_id,
              'protected_capture': 'unavailable',
              'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
              'created_at': datetime.now(timezone.utc).isoformat(),
              'review_target_id': target_id,
              'review_target_source_sha256': source_digest}
    with _turn_lock(root):
        if setup_only:
            _setup_output_open(root)
        _approval_active(root)
        if _unresolved_dispatches(root):
            _fail('prior_dispatch_unknown_effect')
        if not run_active(root):
            _fail('native_run_closed_before_dispatch')
        pool_before = allowance_snapshot(root)
        if setup_only and role in ('researcher', 'resume'):
            _verify_inventory(root / 'original', _plan(root)['source_sha256'], setup_limit=True)
            checkpoint_note = ('This is a fresh physical setup epoch and a fresh native session. '
                               'Read /research/setup-checkpoint/receipt.json and its proposal files; '
                               'reconstruct the unfinished proposal from those host-frozen bytes. '
                               'Do not assume native history survived.\n'
                               if (_controls(root) / 'setup-epoch.json').exists() else '')
            prompt = (
                'Read /research/WORKFLOW.md and /research/BRIEF.md first. '
                'The original source is read-only at /source. Write only in '
                '/workspace/project. Prepare a runtime recipe and THREAT_MODEL.md; '
                'do not run target code or fetch dependencies.\n' + checkpoint_note + '\n' + prompt)
            record.update({'continuity': continuity or 'fresh_setup',
                           'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest()})
        elif role in ('researcher', 'resume'):
            continuity = continuity or ('fresh_research' if role == 'researcher' else 'native_history')
            context = _research_context(root, continuity, pool=pool_before)
            if context is not None:
                context['dispatch_id'] = dispatch_id
                snapshot_path = _controls(root) / 'research-snapshots' / (dispatch_id + '.json')
                _write_json(snapshot_path, context, once=True)
                _write_json(_controls(root) / 'research/RUN.json', context)
                prompt = (
                    'Read /research/WORKFLOW.md, /research/BRIEF.md and /research/RUN.json '
                    'with your tools before another experiment. Consult /workspace/RESEARCH.md '
                    'if present, along with saved scripts and results. '
                    'The run snapshot is advice at this dispatch time, not new authority. '
                    'Keep material hypotheses, observations, scripts/results, unfinished effects, '
                    'review limits and your final internal note in ordinary workspace files. '
                    'After the experiment, update /workspace/NEXT.json with last_result.state '
                    '(supported, refuted, blocked, or inconclusive), what it rules out, useful '
                    'capabilities and coverage, and the next brief or an explicit stop proposal. '
                    'Do not invent a branch after a refutation. '
                    'Native history is optional; do not reset allowance or repeat an uncertain effect.\n'
                    f'Continuation mode: {continuity}.\n\n{prompt}')
                if len(prompt.encode()) > 128 * 1024:
                    _fail('native_turn_input_invalid')
                record.update({'continuity': continuity, 'research_snapshot_sha256': _sha(snapshot_path),
                               'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest()})
        if setup_only:
            record['setup_sequence'] = len(_setup_dispatches(root)) + 1
        record['pool_before'] = pool_before
        _write_json(record_path, record, once=True)
        _write_json(record_path.with_name(dispatch_id + '.pre.json'), record, once=True)
        try:
            if _capture_mode(_plan(root)):
                target = 'target' if role in ('researcher', 'resume') else 'review-target-' + role[-1]
                _load_capture_module(root).bind_dispatch(root, target, dispatch_id)
            if kanboard_role_grant:
                _arm_kanboard_role_grant(root, dispatch_id, role)
            if before_dispatch is not None:
                before_dispatch(root, dispatch_id)
            result = _native_exec(root, role,
                                  ['run', '--standalone', '--agent', 'build', '--model', _plan(root)['model'],
                                   '--format', 'json', '--session', session_id, prompt],
                                  min(3600, max(30, _plan(root)['limits']['duration_seconds'])),
                                  origin_dispatch=dispatch_id if _origin_enabled(_plan(root)) else None)
            stdout = result.stdout.decode('utf-8')
            stderr = result.stderr.decode('utf-8')
            if result.returncode:
                _fail('native_turn_exit_unknown_effect')
            summary = _summarize_native(stdout, session_id)
            trace_path = _controls(root) / 'dispatch' / (dispatch_id + '.trace.json')
            _write_json(trace_path, _protected_trace(stdout, session_id), once=True)
            usage = {'status': 'unavailable'}
            if run_active(root):
                try:
                    observed = _native_exec(root, role, ['api', '--standalone', 'session.get',
                                                        '--param', 'sessionID=' + session_id], 90)
                    detail = json.loads(observed.stdout).get('data') if observed.returncode == 0 else None
                    if isinstance(detail, dict) and detail.get('id') == session_id:
                        usage = {'status': 'observed', 'id': session_id,
                                 'cost': detail.get('cost'), 'tokens': detail.get('tokens')}
                except (NativeResearchError, UnicodeError, ValueError):
                    pass
            pool_after = allowance_snapshot(root)
            record.update({'status': 'acknowledged', 'stdout_sha256': hashlib.sha256(result.stdout).hexdigest(),
                           'stderr_sha256': hashlib.sha256(result.stderr).hexdigest(),
                           **summary, 'pool_before': pool_before, 'pool_after': pool_after,
                           'native_trace_sha256': _sha(trace_path), 'native_usage': usage})
            if _origin_enabled(_plan(root)):
                registration = _controls(root) / 'origin/registrations' / (dispatch_id + '.json')
                record['origin_registration_sha256'] = _sha(registration)
                record['native_response_claims'] = _native_response_claims(stdout)
            if 'kanboard_capture' in _plan(root):
                target = 'target' if role in ('researcher', 'resume') else 'review-target-' + role[-1]
                window = _read_json(_controls(root) / 'observer' / target /
                                    ('window-' + dispatch_id + '.json'))
                before = _file(record_path.with_name(dispatch_id + '.pre.json'), private=True).read_bytes()
                origin = _load_origin_gate(root).assess(window, before, record, trace_path.read_bytes())
                _write_json(record_path.with_name(dispatch_id + '.origin.json'), origin, once=True)
                record['origin_hold'] = origin
            elif 't01_capture' in _plan(root):
                target = 'target' if role in ('researcher', 'resume') else 'review-target-' + role[-1]
                closed = _load_capture_module(root).close_dispatch(
                    root, target, dispatch_id, _native_response_ids(stdout))
                origin = {'status': 'held', 'reason': closed['reason'],
                          'dispatch_id': dispatch_id, 'native_request_attributable': False,
                          'closed_window_sha256': _sha(_controls(root) / 'observer' / target /
                                                       ('closed-' + dispatch_id + '.json')),
                          'joined_request_ids': closed['joined_request_ids']}
                _write_json(record_path.with_name(dispatch_id + '.origin.json'), origin, once=True)
                record['origin_hold'] = origin
            if _origin_enabled(_plan(root)):
                target = ORIGIN_ROLES[role]
                record['origin_window_close_sha256'] = _sha(_origin_close_window(root, target, dispatch_id))
            if setup_only and _read_json(_controls(root) / 'approval.json').get('kind') == 'native-setup-approval-v2':
                record['checkpoint_sha256'] = _setup_checkpoint(root, record)
            _write_json(record_path, record)
            returned = dict(record)
            if include_raw:
                returned['_raw_stdout'] = stdout
            return returned
        except Exception:
            # The durable pre-dispatch record remains uncertain; no automatic retry.
            record['status'] = 'unknown_effect'
            return dict(record)


def _probe_target(root: Path, container_id: str, target_ip: str, port: int) -> None:
    code = ('$s=@stream_socket_client("tcp://".$argv[1].":".$argv[2],$e,$m,2);'
            'if(!$s)exit(2);fclose($s);echo "connected";')
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and run_active(root):
        result = _docker('container', 'exec', container_id, 'php', '-r', code,
                         target_ip, str(port), timeout=5, allow_failure=True)
        if result.returncode == 0 and result.stdout == b'connected':
            return
        time.sleep(.25)
    _fail('owned_target_route_unavailable')


def _probe_origin_route(root: Path, plan: dict, bindings: dict) -> None:
    """Show each broker answers only in its target namespace, not on agent TCP."""
    code = ('$s=@stream_socket_client("tcp://".$argv[1].":".$argv[2],$e,$m,2);'
            'if(!$s)exit(2);fclose($s);echo "connected";')
    for role, target in ORIGIN_ROLES.items():
        target_id = bindings[target]
        target_ip = (bindings['research_target_ip'] if target == 'target' else
                     bindings['review_target_ips'][role])
        deadline = time.monotonic() + 30
        connected = False
        while time.monotonic() < deadline and run_active(root):
            result = _docker('container', 'exec', target_id, 'php', '-r', code,
                             '127.0.0.1', str(plan['target_port']), timeout=5,
                             allow_failure=True)
            if result.returncode == 0 and result.stdout == b'connected':
                connected = True
                break
            time.sleep(.25)
        if not connected:
            _fail('native_origin_target_loopback_unavailable')
        direct = _docker('container', 'exec', bindings[role],
                         '/origin/bin/native-origin', 'probe-tcp', target_ip,
                         str(plan['target_port']), timeout=5, allow_failure=True)
        if direct.returncode != 0 or direct.stdout not in (b'unreachable', b'connected'):
            _fail('native_origin_direct_tcp_probe_unavailable')
        if direct.stdout == b'connected':
            _fail('native_origin_direct_tcp_bypass')


def _validate_source_runtime(value: object) -> dict:
    if (not isinstance(value, dict) or set(value) !=
            {'version_command', 'version_stdout', 'dependency_command'}
            or not isinstance(value['version_stdout'], str)
            or not 1 <= len(value['version_stdout'].encode()) <= 4096
            or CREDENTIAL_TEXT.search(value['version_stdout'])):
        _fail('source_runtime_invalid')
    _validate_argv(value['version_command'])
    _validate_argv(value['dependency_command'])
    return value


def _source_runtime(plan: dict) -> dict:
    source = plan['source_only']
    return source.get('runtime') or {
        'version_command': ['go', 'version'],
        'version_stdout': 'go version ' + source['go_toolchain'] + ' ' + plan['platform'],
        'dependency_command': ['go', 'list', '-m', '-f', '{{if not .Dir}}{{.Path}}{{end}}', 'all']}


def _source_environment(base: str, plan: dict) -> list[str]:
    if 'runtime' in plan['source_only']:
        return []
    return ['GOTOOLCHAIN=local', 'GOPROXY=off', 'GOSUMDB=off', 'GOWORK=off',
            'GOENV=off', 'GOFLAGS=-mod=readonly',
            'GOMODCACHE=' + _source_dependency_destination(plan),
            'GOCACHE=' + base + '/go-build-cache', 'GOTMPDIR=' + base + '/tmp', 'CGO_ENABLED=0']


def _source_probe(root: Path, container_id: str) -> dict:
    plan = _plan(root)
    profile = _source_runtime(plan)
    info = _inspect('container', container_id)
    executor = info['Config']['WorkingDir'] == '/target'
    base = '/target/.native-source' if executor else '/workspace'
    workdir = '/target' if executor else '/workspace/project'
    environment = ['PATH=' + OFFICIAL_IMAGE_ENV['PATH'], 'HOME=/tmp', *_source_environment(base, plan)]
    result = _docker('container', 'exec', '-w', workdir, container_id, 'env', '-i',
                     *environment, *profile['version_command'], timeout=10, allow_failure=True)
    if result.returncode or result.stdout.decode(errors='replace').strip() != profile['version_stdout']:
        _fail('source_runtime_version_unavailable')
    closure = _docker('container', 'exec', '-w', workdir, container_id, 'env', '-i',
                      *environment, *profile['dependency_command'], timeout=60, allow_failure=True)
    if closure.returncode or closure.stdout.strip():
        _fail('source_offline_dependency_closure_unavailable')
    return {'runtime_version': profile['version_stdout'], 'image_id': info['Image']}


def _source_command(root: Path, identifier: str, workdir: str, argv: list[str],
                    destination: Path, timeout: float) -> dict:
    """Bound output while reading it; loss of acknowledgement stops every producer."""
    native, _ = _activate_controls(root)
    plan = _plan(root)
    environment = ['PATH=' + OFFICIAL_IMAGE_ENV['PATH'], 'HOME=/tmp',
                   'TMPDIR=/target/.native-source/tmp', *_source_environment('/target/.native-source', plan)]
    command = [str(DOCKER_BINARY), 'container', 'exec', '-w', workdir, identifier,
               'env', '-i', *environment, *argv]
    child = None
    buffers = [bytearray(), bytearray()]
    try:
        with native.dispatch_guard(_controls(root) / 'native-state'):
            if 'source_effect_envelope' in plan:
                _source_executor_envelope(root, plan)
            child = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     env={key: value for key, value in os.environ.items()
                                          if key in ('HOME', 'PATH', 'DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_CONFIG')})
        streams = {child.stdout: 0, child.stderr: 1}
        deadline = time.monotonic() + timeout
        while streams:
            if time.monotonic() >= deadline or not run_active(root):
                _fail('source_execution_timeout_or_stopped')
            for stream in select.select(list(streams), [], [], .2)[0]:
                chunk = os.read(stream.fileno(), 65536)
                if not chunk:
                    del streams[stream]
                    continue
                buffer = buffers[streams[stream]]
                if len(buffer) + len(chunk) > 1024 * 1024:
                    _fail('source_execution_output_oversize')
                buffer.extend(chunk)
        code = child.wait(timeout=max(.1, deadline - time.monotonic()))
        outputs = {}
        for name, value in zip(('stdout', 'stderr'), buffers):
            raw = bytes(value)
            outputs[name + '_sha256'] = hashlib.sha256(raw).hexdigest()
            if CREDENTIAL_TEXT.search(raw.decode(errors='replace')):
                outputs[name + '_redacted'] = True
            else:
                path = destination / (name + '.txt')
                path.write_bytes(raw)
                path.chmod(0o600)
        return {'exit_code': code, 'environment': environment, **outputs}
    except Exception:
        stop(root)
        raise
    finally:
        if child is not None:
            if child.poll() is None:
                child.kill()
            child.wait()
            child.stdout.close()
            child.stderr.close()


def _verify_source_original(original: dict, current: dict) -> None:
    # shortcut: endpoint hashes miss temporary edits; inspect scripts before accepting causal claims.
    if any(current.get(name) != digest for name, digest in original.items()):
        _fail('source_review_original_changed')


def _freeze_source_input(root: Path, destination: Path, role: str) -> dict:
    if role not in ('researcher', 'reviewer-1', 'reviewer-2'):
        _fail('source_owner_invalid')
    source = root / role / 'project'
    native, _ = _activate_controls(root)
    writers = [_resources(root)[name] for name in (('researcher', 'resume') if role == 'researcher' else (role,))]
    try:
        with native.dispatch_guard(_controls(root) / 'native-state'):
            if not run_active(root):
                _fail('source_execution_unavailable')
            for identifier in writers:
                _docker('container', 'pause', identifier)
                if _inspect('container', identifier).get('State', {}).get('Paused') is not True:
                    _fail('source_writer_freeze_unavailable')
        inventory = _inventory(source)
        shutil.copytree(source, destination, symlinks=True)
        _verify_inventory(destination, inventory)
        _verify_inventory(source, inventory)
        # A review definition is outside the project and must freeze with its scripts.
        if role.startswith('reviewer-'):
            check = root / role / 'source-check.json'
            if check.exists():
                shutil.copy2(_file(check), destination.parent / 'source-check.json')
                (destination.parent / 'source-check.json').chmod(0o600)
        with native.dispatch_guard(_controls(root) / 'native-state'):
            if not run_active(root):
                _fail('source_execution_unavailable')
            for identifier in writers:
                _docker('container', 'unpause', identifier)
        return inventory
    except Exception:
        stop(root)
        raise


def _source_executor_envelope(root: Path, plan: dict) -> None:
    """Read back the approved offline effect boundary immediately before a batch."""
    expected_envelope = (CHECKED_SOURCE_EFFECT_ENVELOPE if 'checked_setup' in plan
                         else SOURCE_EFFECT_ENVELOPE)
    if plan.get('source_effect_envelope') != expected_envelope:
        _fail('source_action_authority_required')
    resources = _read_json(_controls(root) / 'resources.json')
    nonce = resources.get('nonce')
    for role in CAPTURE_TARGETS:
        identifier = _resources(root)[role]
        info = _inspect('container', identifier)
        host = info.get('HostConfig') or {}
        config = info.get('Config') or {}
        mounts = {(row.get('Source'), row.get('Destination'), row.get('RW'))
                  for row in info.get('Mounts', [])}
        expected = {(str(root / role), '/target', True),
                    (str(_controls(root) / 'source-modules'),
                     _source_dependency_destination(plan), False)}
        if (info.get('Id') != identifier or info.get('Image') != plan['target_image_id']
                or config.get('Labels', {}).get(LABEL) != nonce
                or config.get('User') != f'{os.getuid()}:{os.getgid()}'
                or host.get('NetworkMode') != 'none' or host.get('ReadonlyRootfs') is not True
                or set(info.get('NetworkSettings', {}).get('Networks', {})) != {'none'}
                or host.get('Privileged') is not False or host.get('CapDrop') != ['ALL']
                or 'no-new-privileges=true' not in (host.get('SecurityOpt') or [])
                or host.get('PidsLimit') != 64 or host.get('Memory') != 1024 * 1024 * 1024
                or host.get('NanoCpus') != 1000000000
                or host.get('RestartPolicy', {}).get('Name') != 'no'
                or mounts != expected):
            _fail('source_effect_envelope_not_enforced')


def _reset_source_executor(root: Path, role: str, identifier: str, plan: dict) -> None:
    native, _ = _activate_controls(root)
    with native.dispatch_guard(_controls(root) / 'native-state'):
        if not run_active(root):
            _fail('source_execution_unavailable')
        info = _inspect('container', identifier)
        if (info.get('Image') != plan['target_image_id'] or
                info.get('HostConfig', {}).get('NetworkMode') != 'none' or
                info.get('State', {}).get('Running') is not True or
                info.get('Config', {}).get('Labels', {}).get(LABEL) !=
                _read_json(_controls(root) / 'resources.json')['nonce'] or
                not any(m.get('Destination') == '/target' and m.get('Source') == str(root / role)
                        for m in info.get('Mounts', []))):
            _fail('source_executor_identity_mismatch')
        if info['State'].get('Paused'):
            _docker('container', 'unpause', identifier)
        _docker('container', 'kill', identifier)
        if _inspect('container', identifier)['State'].get('Running') is not False:
            _fail('source_executor_stop_unavailable')
        base = root / role
        for child in base.iterdir():
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
        shutil.copytree(root / 'original', base, dirs_exist_ok=True)
        _verify_inventory(base, plan['source_sha256'])
        for name in ('tmp', 'go-build-cache'):
            (base / '.native-source' / name).mkdir(parents=True, mode=0o700)
        if not run_active(root):
            _fail('source_execution_unavailable')
        _docker('container', 'start', identifier)
        if _inspect('container', identifier)['State'].get('Running') is not True:
            _fail('source_executor_restart_unavailable')


def source_execute(run_root: Path, command_file: Path | None = None, *,
                   source_snapshot: Path | None = None, owner_role: str = 'researcher',
                   execution_id: str | None = None, expected_command: list[str] | None = None,
                   expected_input: dict[str, str] | None = None) -> dict:
    root = _private_root(run_root)
    with _turn_lock(root):
        plan = _verified_plan(root)
        if 'source_only' not in plan or not run_active(root) or _unresolved_dispatches(root):
            _fail('source_execution_unavailable')
        _approval_active(root)
        if 'source_effect_envelope' in plan:
            _source_executor_envelope(root, plan)
        if owner_role not in ('researcher', 'reviewer-1', 'reviewer-2'):
            _fail('source_owner_invalid')
        command = _validate_target_command(command_file or _controls(root) / 'target-command.json')
        if expected_command is not None and command != expected_command:
            _fail('source_execution_command_changed')
        if source_snapshot is not None:
            inventory = _inventory(source_snapshot)
            if expected_input is not None and inventory != expected_input:
                _fail('source_execution_input_changed')
            if owner_role.startswith('reviewer-'):
                _verify_source_original(plan['source_sha256'], inventory)
        identity = execution_id or uuid.uuid4().hex
        if not re.fullmatch(r'[0-9a-f]{32}', identity):
            _fail('source_execution_id_invalid')
        directory = _controls(root) / 'source-executions' / identity
        directory.mkdir(mode=0o700)
        path = directory / 'receipt.json'
        receipt = {'kind': 'native-source-execution-v1', 'status': 'unknown_effect',
                   'execution_id': identity, 'owner_role': owner_role,
                   'plan_sha256': _sha(root / 'plan.json'),
                   'original_source_manifest_sha256': plan['source_manifest_sha256'],
                   'module_cache_sha256': plan['source_only']['module_cache_sha256'],
                   'command': command, 'image_id': plan['target_image_id'],
                   'platform': plan['platform'], 'runtime': _source_runtime(plan),
                   'network': 'none', 'runs': [], 'assessment': 'needs_review'}
        _write_json(path, receipt, once=True)
        try:
            if source_snapshot is None:
                inventory = _freeze_source_input(root, directory / 'input', owner_role)
            else:
                shutil.copytree(source_snapshot, directory / 'input', symlinks=True)
                _verify_inventory(directory / 'input', inventory)
                if expected_input is not None:
                    _verify_inventory(directory / 'input', expected_input)
            if owner_role.startswith('reviewer-'):
                _verify_source_original(plan['source_sha256'], inventory)
            _write_json(directory / 'input-manifest.json', inventory, once=True)
            receipt['input_manifest_sha256'] = _sha(directory / 'input-manifest.json')
            _write_json(path, receipt)
            for role in CAPTURE_TARGETS:
                if 'source_effect_envelope' in plan:
                    _source_executor_envelope(root, plan)
                identifier = _resources(root)[role]
                _reset_source_executor(root, role, identifier, plan)
                output = directory / role
                output.mkdir(mode=0o700)
                relative = '.native-source/run'
                work = root / role / relative
                shutil.copytree(directory / 'input', work)
                _verify_inventory(work, inventory)
                execution = _source_command(root, identifier, '/target/' + relative, command, output,
                                            plan['limits']['duration_seconds'])
                _docker('container', 'pause', identifier)
                if _inspect('container', identifier).get('State', {}).get('Paused') is not True:
                    _fail('source_executor_freeze_unavailable')
                output_inventory = _inventory(work)
                if owner_role.startswith('reviewer-'):
                    _verify_source_original(plan['source_sha256'], output_inventory)
                shutil.copytree(work, output / 'files', symlinks=True)
                _verify_inventory(output / 'files', output_inventory)
                _write_json(output / 'files.json', output_inventory, once=True)
                execution.update({'role': role, 'container_id': identifier, 'producer_paused': True,
                                  'output_manifest_sha256': _sha(output / 'files.json')})
                binaries = {}
                if 'metadata_go' in plan['source_only']:
                    for name in output_inventory:
                        binary = output / 'files' / name
                        with binary.open('rb') as stream:
                            is_elf = stream.read(4) == b'\x7fELF'
                        if not is_elf:
                            continue
                        metadata = subprocess.run([plan['source_only']['metadata_go'], 'version', '-m', str(binary)],
                                                  stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                                  stderr=subprocess.PIPE, timeout=10, check=False,
                                                  env={'PATH': '/usr/bin:/bin', 'GOTOOLCHAIN': 'local'})
                        if len(metadata.stdout) > 1024 * 1024:
                            _fail('source_binary_metadata_oversize')
                        text = metadata.stdout.decode(errors='replace')
                        metadata_path = output / ('binary-' + str(len(binaries)) + '.json')
                        _write_json(metadata_path, {'go_version_m_exit': metadata.returncode,
                                    'go_version_m': '[redacted]' if CREDENTIAL_TEXT.search(text) else text}, once=True)
                        binaries[name] = {'sha256': _sha(binary), 'metadata_sha256': _sha(metadata_path)}
                execution['binaries'] = binaries
                receipt['runs'].append(execution)
                _write_json(path, receipt)
            if not run_active(root):
                _fail('source_execution_unavailable')
            signatures = {(row['exit_code'], row['stdout_sha256'], row['stderr_sha256']) for row in receipt['runs']}
            receipt.update({'status': 'captured', 'replay_output_equal': len(signatures) == 1,
                            'all_commands_succeeded': all(row['exit_code'] == 0 for row in receipt['runs'])})
            _write_json(path, receipt)
            return {'status': 'captured', 'assessment': 'needs_review', 'receipt_path': str(path),
                    'receipt_sha256': _sha(path), 'replay_output_equal': receipt['replay_output_equal'],
                    'all_commands_succeeded': receipt['all_commands_succeeded']}
        except Exception:
            stop(root)
            raise


def setup_freeze(run_root: Path) -> dict:
    """Copy only the two proposed files from a bounded setup workspace."""
    root = _private_root(run_root)
    with _turn_lock(root):
        plan = _verified_plan(root)
        if 'setup_only' not in plan or not run_active(root):
            _fail('setup_freeze_unavailable')
        _approval_active(root)
        if _unresolved_dispatches(root):
            _fail('prior_dispatch_unknown_effect')
        records = _setup_dispatches(root)
        if not records or records[-1].get('status') != 'acknowledged':
            _fail('setup_turn_not_acknowledged')
        latest = records[-1]
        output = _controls(root) / 'setup-output'
        if output.exists():
            _fail('setup_output_already_frozen')
        staging_root = _controls(root) / 'setup-staging'
        staging_root.mkdir(mode=0o700, exist_ok=True)
        staging = staging_root / (latest['dispatch_id'] + '-' + uuid.uuid4().hex)
        staging.mkdir(mode=0o700)
        identifier = _resources(root)['researcher']
        files = {}
        for name in SETUP_OUTPUT_FILES:
            command = ('test -f "$1" && test ! -L "$1" && '
                       'head -c 1048577 "$1"')
            argv = ('container', 'exec', identifier, 'sh', '-c', command,
                    'setup-read', '/workspace/project/' + name)
            first = _docker(*argv, timeout=20, allow_failure=True)
            second = _docker(*argv, timeout=20, allow_failure=True)
            if (first.returncode or second.returncode or first.stdout != second.stdout
                    or not first.stdout or len(first.stdout) > 1024 * 1024):
                _fail('setup_output_missing_changed_or_oversize')
            try:
                text = first.stdout.decode('utf-8')
            except UnicodeError:
                _fail('setup_output_encoding_invalid')
            if CREDENTIAL_TEXT.search(text):
                _fail('setup_output_credential_like')
            path = staging / name
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(first.stdout)
                stream.flush()
                os.fsync(stream.fileno())
            files[name] = _sha(path)
        recipe = _read_json(staging / 'recipe.json')
        if (set(recipe) != {'kind', 'runtime', 'build_command', 'offline_dependencies'}
                or recipe['kind'] != 'native-setup-recipe-v1'
                or not isinstance(recipe['offline_dependencies'], list)
                or len(recipe['offline_dependencies']) > 256
                or any(not isinstance(item, str) or not 1 <= len(item) <= 256
                       for item in recipe['offline_dependencies'])):
            _fail('setup_recipe_invalid')
        _validate_source_runtime(recipe['runtime'])
        _validate_argv(recipe['build_command'])
        if not (staging / 'THREAT_MODEL.md').read_text().strip():
            _fail('setup_threat_model_empty')
        trace = _controls(root) / 'dispatch' / (latest['dispatch_id'] + '.trace.json')
        if not trace.exists():
            _fail('setup_trace_missing')
        receipt = {'kind': 'native-setup-output-v1', 'status': 'frozen_proposal',
                   'plan_sha256': _sha(root / 'plan.json'),
                   'approval_sha256': _sha(_controls(root) / 'approval.json'),
                   'original_source_manifest_sha256': plan['source_manifest_sha256'],
                   'dispatch_id': latest['dispatch_id'],
                   'setup_sequence': latest['setup_sequence'],
                   'dispatch_sha256': _sha(_controls(root) / 'dispatch' /
                                           (latest['dispatch_id'] + '.json')),
                   'native_trace_sha256': _sha(trace),
                   'pool_before': latest.get('pool_before'),
                   'pool_after': latest.get('pool_after'),
                   'native_usage': latest.get('native_usage'),
                   'files': files, 'assessment': 'proposal_needs_host_review',
                   'target_build_executed': False, 'security_result': None}
        _write_json(staging / 'receipt.json', receipt, once=True)
        os.rename(staging, output)
        descriptor = os.open(_controls(root), os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return {'status': 'frozen_proposal', 'receipt_path': str(output / 'receipt.json'),
                'receipt_sha256': _sha(output / 'receipt.json')}


def _workspace_runtime_probe(root: Path, container_id: str) -> dict | None:
    if 'source_only' in _plan(root):
        return _source_probe(root, container_id)
    if _plan(root).get('t01_research_mode') != 'workspace_research':
        return None
    extensions = ['pdo_sqlite', 'gd', 'mbstring', 'hash', 'openssl', 'json',
                  'ctype', 'filter', 'session', 'dom', 'SimpleXML', 'xml']
    code = ('$extensions=' + json.dumps(extensions) + ';'
            'echo json_encode(["php_version"=>PHP_VERSION,"extensions"=>array_combine('
            '$extensions,array_map("extension_loaded",$extensions)),'
            '"data_writable"=>is_writable("/workspace/project/data"),'
            '"vendor_autoload_present"=>is_file("/workspace/project/vendor/autoload.php")]);')
    try:
        result = _docker('container', 'exec', container_id, 'php', '-r', code,
                         timeout=10, allow_failure=True)
    except NativeResearchError:
        _fail('workspace_php_runtime_unavailable')
    if result.returncode or len(result.stdout) > 4096:
        _fail('workspace_php_runtime_unavailable')
    try:
        value = json.loads(result.stdout)
    except (UnicodeError, ValueError, RecursionError):
        _fail('workspace_php_runtime_unavailable')
    if (not isinstance(value, dict) or
            set(value) != {'php_version', 'extensions', 'data_writable', 'vendor_autoload_present'} or
            not isinstance(value['php_version'], str) or
            not isinstance(value['extensions'], dict) or set(value['extensions']) != set(extensions) or
            any(loaded is not True for loaded in value['extensions'].values()) or
            value['data_writable'] is not True or value['vendor_autoload_present'] is not True):
        _fail('workspace_php_runtime_unavailable')
    version = re.fullmatch(r'([0-9]{1,2})\.([0-9]{1,2})\.([0-9]{1,3})', value['php_version'])
    if version is None or tuple(map(int, version.groups())) < (8, 1, 0):
        _fail('workspace_php_runtime_unavailable')
    return {**value, 'extensions': extensions}


def _surface_probe(root: Path, container_id: str) -> dict:
    plan = _plan(root)
    config = _model_config(plan)
    workspace_runtime = _workspace_runtime_probe(root, container_id)
    version = _docker('container', 'exec', container_id, '/usr/local/bin/opencode', '--version')
    if version.stdout.decode(errors='replace').strip() != VERSION:
        _fail('opencode_version_mismatch')
    db = _docker('container', 'exec', container_id, '/usr/local/bin/opencode', 'debug', 'paths', 'db')
    if db.stdout.decode(errors='replace').strip() != '/workspace/data/opencode/opencode.db':
        _fail('opencode_store_path_mismatch')
    command = [str(DOCKER_BINARY), 'container', 'exec', '-w', '/workspace/project', container_id,
               '/bin/sh', '-c', 'echo $$; exec /usr/local/bin/opencode serve --hostname 127.0.0.1 --port 4096']
    server = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, bufsize=1)
    pid = None
    try:
        if not select.select([server.stdout], [], [], 10)[0]:
            _fail('surface_server_unavailable')
        pid = int(server.stdout.readline().strip())
        password = None
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and not password:
            if select.select([server.stdout], [], [], 1)[0]:
                match = re.search(r'server password ([^\s]+)', server.stdout.readline())
                if match:
                    password = match.group(1)
            if server.poll() is not None:
                break
        if not password:
            _fail('surface_server_password_unavailable')
        header = 'Authorization: Basic ' + base64.b64encode(('opencode:' + password).encode()).decode()

        def get(endpoint: str):
            result = _docker('container', 'exec', container_id, 'wget', '-qO-', '--header', header,
                             'http://127.0.0.1:4096/api/' + endpoint, timeout=15)
            try:
                value = json.loads(result.stdout)
            except (UnicodeError, ValueError):
                _fail('surface_api_invalid')
            return value.get('data', value) if isinstance(value, dict) else value

        for _ in range(50):
            agents, plugins = get('agent'), get('plugin')
            required_permissions = 1 if 'setup_only' in plan else 12
            if agents and plugins and len(agents[0].get('permissions', [])) >= required_permissions:
                break
            time.sleep(.1)
        configs = get('config')
        document = next((row.get('info') for row in configs if row.get('type') == 'document'), None)
        skills, mcp, references, commands = (get(endpoint) for endpoint in
                                              ('skill', 'mcp', 'reference', 'command'))
        if (not isinstance(document, dict) or not isinstance(agents, list)
                or not isinstance(plugins, list) or not isinstance(skills, list)
                or not isinstance(mcp, list) or not isinstance(references, list)
                or not isinstance(commands, list)):
            _fail('surface_inventory_invalid')
        plugin_ids = sorted(item.get('id') for item in plugins)
        tools = sorted(item.removeprefix('opencode.tool.') for item in plugin_ids
                       if isinstance(item, str) and item.startswith('opencode.tool.'))
        inventory = {
            'config_sources': [{'type': row.get('type'), 'path': row.get('path')} for row in configs],
            'effective_config': {key: document.get(key) for key in
                                 ('model', 'fallback', 'permissions', 'policies', 'plugins', 'mcp', 'websearch')},
            'agents': [{'id': row.get('id'), 'mode': row.get('mode'),
                        'permissions': row.get('permissions')} for row in agents],
            'plugin_ids': plugin_ids, 'registered_tool_names': tools,
            'skill_ids': sorted(item.get('id') for item in skills),
            'mcp_count': len(mcp), 'reference_count': len(references),
            'command_count': len(commands), 'native_db_path': '/workspace/data/opencode/opencode.db',
        }
        if workspace_runtime is not None:
            inventory['workspace_runtime'] = workspace_runtime
        if plan['model'] == PAID_MODEL:
            loaded = document.get('providers', {}).get(PAID_ROUTE, {}).get('settings', {})
            expected = config['providers'][PAID_ROUTE]['settings']
            if any(loaded.get(key) != value for key, value in expected.items()):
                _fail('paid_provider_surface_mismatch')
            inventory['paid_provider'] = {'id': PAID_ROUTE, 'base_url': expected['baseURL'],
                                           'credential_location': 'host_gateway_only'}
        effective = inventory['effective_config']
        provider, model = plan['model'].split('/', 1)
        if (effective['model'] != {'providerID': provider, 'model': model}
                or effective['fallback'] is not None
                or effective['permissions'] != config['permissions']
                or effective['policies'] != config['policies']
                or effective['plugins'] != [] or effective['websearch'] is not False
                or effective['mcp'] != config['mcp']
                or inventory['mcp_count'] != 0
                or inventory['skill_ids'] != _plan(root)['expected_skill_ids']
                or not {'edit', 'write', 'shell'} <= set(tools)
                or not any(agent['id'] == 'build' and agent['mode'] == 'primary'
                           for agent in inventory['agents'])
                or not any(row['path'] == '/workspace/config/opencode/opencode.json'
                           for row in inventory['config_sources'])):
            _fail('loaded_surface_mismatch')
        return inventory
    finally:
        if pid is not None:
            _docker('container', 'exec', container_id, 'kill', '-TERM', str(pid),
                    allow_failure=True)
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
        server.stdout.close()


def start(run_root: Path, approval_path: Path, *, provider_key_file: Path | None = None,
          provider_tls_key: Path | None = None) -> dict:
    root = _private_root(Path(run_root))
    with _owner_lock(root):
        return _start_owned(root, Path(approval_path), provider_key_file=provider_key_file,
                            provider_tls_key=provider_tls_key)


def _start_owned(run_root: Path, approval_path: Path, *, provider_key_file: Path | None = None,
                 provider_tls_key: Path | None = None) -> dict:
    root = _private_root(Path(run_root))
    plan = _verified_plan(root, pristine=True)
    controls = _controls(root)
    paid = plan['model'] == PAID_MODEL
    if paid:
        if provider_key_file is None or provider_tls_key is None:
            _fail('host_provider_credentials_required')
        for path in (provider_key_file, provider_tls_key):
            path = _file(path, private=True)
            if path.is_relative_to(root) or path.is_relative_to(ROOT) or path.stat().st_size > 16384:
                _fail('host_credential_location_invalid')
    elif provider_key_file is not None or provider_tls_key is not None:
        _fail('unexpected_provider_credentials')
    if (controls / 'resources.json').exists() or (controls / 'native-state/RUN.json').exists():
        _fail('run_already_started_or_ambiguous')
    _approval(root, plan, Path(approval_path))
    runtime_duration = plan['limits']['duration_seconds']
    setup_grant = (_read_json(controls / 'approval.json') if 'setup_only' in plan else None)
    if setup_grant and setup_grant.get('kind') == 'native-setup-approval-v2':
        deadline = datetime.strptime(setup_grant['absolute_deadline'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
        runtime_duration = min(runtime_duration, int(deadline.timestamp() - time.time()) - 5)
        if runtime_duration < 30:
            _fail('setup_epoch_allowance_exhausted')
    _image(plan['image_id'], plan['platform'], official=True)
    if 'setup_only' not in plan:
        _image(plan['target_image_id'], plan['platform'])
    nonce = uuid.uuid4().hex
    capability = 'local_' + uuid.uuid4().hex
    capability_path = controls / 'capability'
    descriptor = os.open(capability_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        stream.write(capability)
        stream.flush()
        os.fsync(stream.fileno())
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    rows: list[dict] = []
    _save_resources(root, nonce, rows)
    native = None
    gateway = None
    result = {'status': 'start_incomplete', 'run_root': str(root)}
    try:
        bindings = _preseal(root, plan, nonce, rows, port, capability)
        _, producer = _activate_controls(root)
        manifest = _created_manifest(root, nonce, rows, producer)
        native_module, _ = _activate_controls(root)
        if setup_grant and setup_grant.get('kind') == 'native-setup-approval-v2':
            runtime_duration = min(runtime_duration, int(deadline.timestamp() - time.time()) - 5)
            if runtime_duration < 30:
                _fail('setup_epoch_allowance_exhausted')
        proxy_args = ['--state-dir', str(controls / 'provider'),
                      '--capability-file', str(capability_path),
                      '--max-connections', str(plan['limits']['max_connections']),
                      '--max-bytes', str(plan['limits']['max_bytes']),
                      '--duration', str(runtime_duration), '--port', str(port)]
        if paid:
            spec = importlib.util.spec_from_file_location('native_paid_gateway', controls / 'provider-gateway.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            gateway_capability = uuid.uuid4().hex
            gateway = module.Gateway(provider_key_file.read_text().strip(),
                                     controls / 'runtime-ca.pem', provider_tls_key,
                                     gateway_capability, lambda: native_module.active(controls / 'native-state'),
                                     lambda: native_module.dispatch_guard(controls / 'native-state'))
            proxy_args += ['--upstream-proxy-env', 'HTTPS_PROXY']
        native = native_module.NativeRun(manifest, controls / 'native-state',
                                         runtime_duration, proxy_args)
        if _capture_mode(plan):
            _capture_approved_specs(root, plan,
                                    _validate_target_command(controls / 'target-command.json'),
                                    verify_source=True)
        if (controls / 'native-state/STOP_REQUEST').exists():
            _fail('native_stop_before_start')
        old_proxy = os.environ.get('HTTPS_PROXY')
        try:
            if gateway is not None:
                os.environ['HTTPS_PROXY'] = 'http://host:' + gateway_capability + '@127.0.0.1:' + str(gateway.port)
            ready = native.start()
        finally:
            if old_proxy is None:
                os.environ.pop('HTTPS_PROXY', None)
            else:
                os.environ['HTTPS_PROXY'] = old_proxy
        if (ready['proxy_info'].get('authority') != AUTHORITY
                or ready['proxy_info'].get('port') != port
                or ready['proxy_info'].get('host') != '127.0.0.1'
                or ready['ids'] != [row['id'] for row in rows if row['kind'] == 'container']):
            _fail('native_authority_readback_mismatch')
        result['origin_start'] = _origin_start(root, plan, nonce, bindings)
        if _origin_enabled(plan) and result['origin_start']['status'] != 'active':
            _fail('native_origin_start_incomplete')
        capture_topology_sha = None
        if _capture_mode(plan):
            capture_module = _load_capture_module(root)
            topology = {target: capture_module.attest(root, target) for target in CAPTURE_TARGETS}
            topology_path = controls / 'capture-topology.json'
            _write_json(topology_path, topology, once=True)
            capture_topology_sha = _sha(topology_path)
        if 'setup_only' in plan:
            info = _inspect('container', bindings['researcher'])
            networks = set(info.get('NetworkSettings', {}).get('Networks', {}))
            if networks != {bindings['network_names']['research']}:
                _fail('setup_research_network_mismatch')
        elif 'source_only' in plan:
            for role in CAPTURE_TARGETS:
                info = _inspect('container', bindings[role])
                if info['HostConfig']['NetworkMode'] != 'none':
                    _fail('source_executor_network_not_none')
                _source_probe(root, bindings[role])
        elif _origin_enabled(plan):
            _probe_origin_route(root, plan, bindings)
        else:
            _probe_target(root, bindings['researcher'], bindings['research_target_ip'], plan['target_port'])
            for role in ('reviewer-1', 'reviewer-2'):
                _probe_target(root, bindings[role], bindings['review_target_ips'][role], plan['target_port'])
        surface = _surface_probe(root, bindings['researcher'])
        _write_json(controls / 'loaded-surface.json', surface, once=True)
        _write_json(controls / 'activation.json', {
            'kind': 'native-research-activation-v1', 'nonce': nonce,
            'plan_sha256': _sha(root / 'plan.json'), 'manifest_sha256': _sha(manifest),
            'approval_sha256': _sha(controls / 'approval.json'),
            'watcher_pid': ready['watcher_pid'], 'started_at': datetime.now(timezone.utc).isoformat(),
            'provider_route': plan['provider_route'], 'provider_authority': AUTHORITY,
            'model': plan['model'], 'limits': plan['limits'],
            'protected_capture': 'unavailable',
            'capture_topology_sha256': capture_topology_sha,
            'loaded_surface_sha256': _sha(controls / 'loaded-surface.json'),
        }, once=True)
        result = {'status': 'active', 'run_root': str(root),
                  'origin_start': result['origin_start'],
                  'run_identity': allowance_snapshot(root)['run_identity'],
                  'target_url': (None if 'source_only' in plan or 'setup_only' in plan else
                                 'unix:///origin/socket/ingress.sock' if _origin_enabled(plan) else
                                 f'http://{bindings["research_target_ip"]}:{plan["target_port"]}'),
                  'protected_capture': 'unavailable',
                  'capture_topology': (('attested_original_session_origin_held' if 't01_capture' in plan
                                        else 'attested_origin_and_credentials_held') if capture_topology_sha
                                       else 'not_configured'),
                  'provider_request_count': None, 'monetary_spend': None}
        print(json.dumps(result, sort_keys=True), flush=True)
        while native_module.active(controls / 'native-state') and native.process.poll() is None:
            if setup_grant and setup_grant.get('kind') == 'native-setup-approval-v2' and time.time() >= deadline.timestamp():
                native_module.request_stop(controls / 'native-state', 'operator_stop')
                break
            time.sleep(.2)
    finally:
        if gateway is not None:
            gateway.close()
        if native is not None:
            try:
                result['native_stop'] = native.close()
            except Exception:
                result['native_stop'] = {'status': 'unresolved'}
        else:
            result['native_stop'] = {'status': 'not_started'}
        if result['native_stop']['status'] in ('stopped', 'closed_before_activation', 'not_started'):
            try:
                result['origin_stop'] = _origin_stop(root, plan, result['native_stop']['status'])
            except Exception as error:
                result['origin_stop'] = {'status': 'unresolved', 'code': str(error)}
        else:
            result['origin_stop'] = {'status': 'not_taken'}
        if result['native_stop']['status'] == 'stopped':
            try:
                result['host_snapshot'] = _stopped_snapshot(root, plan)
            except NativeResearchError as error:
                result['host_snapshot'] = {'status': 'unavailable', 'code': str(error)}
            except Exception:
                result['host_snapshot'] = {'status': 'unavailable', 'code': 'host_snapshot_unavailable'}
        else:
            result['host_snapshot'] = {'status': 'not_taken'}
        if (result['native_stop']['status'] in ('stopped', 'closed_before_activation', 'not_started')
                and result['origin_stop']['status'] in ('complete', 'not_configured', 'not_started', 'partial')):
            try:
                result['capture_stop'] = _capture_stop(root, plan, result['native_stop']['status'])
            except Exception as error:
                result['capture_stop'] = {'status': 'unresolved', 'code': str(error)}
        else:
            result['capture_stop'] = {'status': 'not_taken'}
        if result['capture_stop']['status'] in ('complete', 'not_configured'):
            try:
                result['origin_cleanup'] = _origin_cleanup(root, plan)
            except Exception as error:
                result['origin_cleanup'] = {'status': 'unresolved', 'code': str(error)}
        if result.get('origin_cleanup', {}).get('status') in ('complete', 'not_configured', 'not_started'):
            try:
                result['cleanup'] = _cleanup_resources(
                    root, require_created=result['native_stop']['status'] == 'not_started')
            except Exception:
                result['cleanup'] = {'status': 'unresolved'}
        if result.get('cleanup', {}).get('status') == 'complete':
            try:
                result['capture_cleanup'] = _capture_cleanup(root, plan)
            except Exception as error:
                result['capture_cleanup'] = {'status': 'unresolved', 'code': str(error)}
        capability_path.unlink(missing_ok=True)
        if (result['native_stop']['status'] in ('unsafe', 'unresolved')
                or (_origin_enabled(plan) and result['native_stop']['status'] == 'stopped'
                    and result.get('origin_start', {}).get('status') != 'active')
                or result['origin_stop']['status'] not in ('complete', 'not_configured', 'not_started')
                or result.get('origin_cleanup', {}).get('status') not in ('complete', 'not_configured', 'not_started')
                or result['capture_stop']['status'] not in ('complete', 'not_configured')
                or result.get('cleanup', {}).get('status') != 'complete'
                or result.get('capture_cleanup', {}).get('status') not in ('complete', 'not_configured')):
            result['status'] = 'unsafe_or_unresolved'
        elif (result['native_stop']['status'] == 'stopped'
              and result['host_snapshot']['status'] != 'complete'):
            result['status'] = 'stopped_evidence_incomplete'
        elif result.get('status') == 'active' and result['native_stop']['status'] == 'stopped':
            result['status'] = 'stopped_complete'
        else:
            result['status'] = 'start_incomplete'
        result['stop_reason'] = _recorded_stop_reason(root)
        _write_json(controls / 'final.json', result)
    return result


def stop(run_root: Path) -> dict:
    root = _private_root(Path(run_root))
    controls = _controls(root)
    if not (controls / 'native-state/RUN.json').exists() and not (controls / 'resources.json').exists():
        return {'status': 'not_active', 'run_root': str(root)}
    cont = controls / 'continuation'
    cont.mkdir(mode=0o700, parents=True, exist_ok=True)
    _write_json(cont / 'STOP', {
        'kind': 'native-continuation-stop-v1', 'reason': 'operator_stop',
        'at': datetime.now(timezone.utc).isoformat()})
    native, _ = _activate_controls(root)
    native.request_stop(controls / 'native-state', 'operator_stop')
    return {'status': 'stop_requested', 'run_root': str(root)}


def recover_start(run_root: Path) -> dict:
    """Remove exact stopped preactivation resources after owner loss, never a live run."""
    root = _private_root(Path(run_root))
    with _owner_lock(root):
        plan = _verified_plan(root)
        controls = _controls(root)
        if not (controls / 'resources.json').exists():
            if (any((controls / 'observer' / target / 'resources.json').exists()
                    for target in CAPTURE_TARGETS)
                    or _origin_resources_path(root).exists()
                    or (controls / 'producer-manifest.json').exists()
                    or (controls / 'native-state/RUN.json').exists()):
                _fail('resource_record_missing_after_creation')
            return {'status': 'no_resources', 'run_root': str(root),
                    'stop_reason': _recorded_stop_reason(root)}
        state = controls / 'native-state'
        if (state / 'UNSAFE').exists():
            _fail('native_run_not_verified_stopped')
        if (state / 'REVOKED').exists():
            native_status, require_created = 'stopped', False
        elif (state / 'STARTUP_CLOSED').exists():
            native_status, require_created = 'closed_before_activation', False
        elif (state / 'RUN.json').exists():
            _fail('native_run_not_verified_stopped')
        else:
            native_status, require_created = 'not_started', True
        origin_stop = _origin_stop(root, plan, native_status)
        if origin_stop['status'] not in ('complete', 'not_configured', 'not_started', 'partial'):
            _fail('native_origin_stop_incomplete')
        capture_stop = _capture_stop(root, plan, native_status)
        host_snapshot = {'status': 'not_taken'}
        if native_status == 'stopped':
            try:
                snapshot_path = controls / 'host-snapshot.json'
                if snapshot_path.exists():
                    receipt = _read_json(snapshot_path)
                    if (receipt.get('plan_sha256') != _sha(root / 'plan.json')
                            or receipt.get('native_stop', {}).get('revoked_sha256') != _sha(state / 'REVOKED')):
                        _fail('recovery_host_snapshot_changed')
                    host_snapshot = {'status': receipt.get('status'), 'receipt_path': str(snapshot_path),
                                     'receipt_sha256': _sha(snapshot_path)}
                else:
                    host_snapshot = _stopped_snapshot(root, plan)
            except NativeResearchError as error:
                host_snapshot = {'status': 'unavailable', 'code': str(error)}
            except Exception:
                host_snapshot = {'status': 'unavailable', 'code': 'host_snapshot_unavailable'}
        origin_cleanup = _origin_cleanup(root, plan)
        if origin_cleanup['status'] not in ('complete', 'not_configured', 'not_started'):
            _fail('native_origin_cleanup_incomplete')
        result = _cleanup_resources(root, require_created=require_created)
        capture_cleanup = _capture_cleanup(root, plan)
        recovery = {'status': ('recovered_exact_resources' if origin_stop['status'] != 'partial'
                               else 'unsafe_or_unresolved'), 'run_root': str(root),
                    'native_state': native_status, 'host_snapshot': host_snapshot,
                    'stop_reason': _recorded_stop_reason(root),
                    'origin_stop': origin_stop, 'origin_cleanup': origin_cleanup,
                    'capture_stop': capture_stop, 'cleanup': result,
                    'capture_cleanup': capture_cleanup}
        _write_json(controls / 'recovery.json', recovery)
        return recovery


def _setup_provider_pins(root: Path) -> dict[str, str]:
    provider = _controls(root) / 'provider'
    result = {}
    for name in ('tunnel.sqlite3', 'tunnel.sqlite3-wal', 'tunnel.sqlite3-shm'):
        path = provider / name
        if path.exists() or path.is_symlink():
            result[name] = _sha(_file(path, private=True))
    if 'tunnel.sqlite3' not in result:
        _fail('setup_provider_ledger_unavailable')
    return result


def _setup_terminal_accounting(root: Path, approval: dict, *, allow_frozen: bool = False,
                               allow_expired: bool = False) -> dict:
    """Read a stopped physical epoch, never infer absence or usage from notes."""
    plan = _verified_plan(root, allow_expired_setup=allow_expired)
    controls = _controls(root)
    if 'setup_only' not in plan or approval.get('kind') != 'native-setup-approval-v2':
        _fail('setup_linked_epoch_required')
    archived = controls / 'approval.json'
    if _read_json(archived) != approval:
        _fail('setup_epoch_grant_changed')
    if not (controls / 'setup-approval-receipt.json').exists():
        _fail('setup_epoch_approval_receipt_missing')
    _setup_approval(root, plan, archived, allow_expired=allow_expired)
    if not allow_frozen:
        _setup_output_open(root)
    if _unresolved_dispatches(root):
        _fail('setup_epoch_unknown_effect')
    dispatches = _setup_dispatches(root)
    if not dispatches or dispatches[-1].get('status') != 'acknowledged':
        _fail('setup_epoch_no_acknowledged_turn')
    checkpoint_path, checkpoint = _verified_setup_checkpoint(root, dispatches[-1])
    state = controls / 'native-state'
    manifest_path, revoked_path = controls / 'producer-manifest.json', state / 'REVOKED'
    manifest, revoked = _read_json(manifest_path), _read_json(revoked_path)
    run = _read_json(state / 'RUN.json')
    resources = _read_json(controls / 'resources.json')
    rows = resources.get('resources')
    if (not isinstance(rows, list) or len(rows) != 4
            or {row.get('role') for row in rows if row.get('kind') == 'container'} != {'relay', 'researcher'}
            or {row.get('role') for row in rows if row.get('kind') == 'network'} != {'external', 'research'}
            or any(not isinstance(row.get('id'), str) or not HEX_RE.fullmatch(row['id'])
                   or not isinstance(row.get('name'), str) or not row['name'] for row in rows)
            or len({row['id'] for row in rows}) != 4):
        _fail('setup_epoch_resource_record_invalid')
    producer_ids = [row['id'] for row in rows if row['kind'] == 'container']
    if (producer_ids != [row.get('id') for row in manifest.get('producers', [])]
            or run.get('ids') != producer_ids or revoked.get('ids') != producer_ids
            or run.get('manifest_sha256') != _sha(manifest_path)
            or revoked.get('manifest_sha256') != _sha(manifest_path)
            or revoked.get('producers_verified_stopped') is not True
            or (state / 'UNSAFE').exists()):
        _fail('setup_epoch_stop_proof_invalid')
    final_path, recovery_path = controls / 'final.json', controls / 'recovery.json'
    if recovery_path.exists() and _read_json(recovery_path).get('status') == 'recovered_exact_resources':
        terminal_path = recovery_path
        terminal = _read_json(recovery_path)
        stopped = terminal.get('native_state') == 'stopped'
    else:
        terminal_path = final_path
        terminal = _read_json(final_path)
        stopped = (terminal.get('status') == 'stopped_complete'
                   and terminal.get('native_stop', {}).get('status') == 'stopped')
    cleanup_path, snapshot_path = controls / 'cleanup.json', controls / 'host-snapshot.json'
    cleanup, snapshot = _read_json(cleanup_path), _read_json(snapshot_path)
    expected_cleanup = [{'kind': row['kind'], 'name': row['name'], 'absent': True}
                        for row in reversed(rows)]
    if (not stopped or terminal.get('cleanup') != cleanup
            or cleanup != {'status': 'complete', 'resources': expected_cleanup}
            or terminal.get('host_snapshot', {}).get('status') != 'complete'
            or terminal['host_snapshot'].get('receipt_sha256') != _sha(snapshot_path)
            or snapshot.get('status') != 'complete'
            or snapshot.get('plan_sha256') != _sha(root / 'plan.json')
            or snapshot.get('native_stop', {}).get('manifest_sha256') != _sha(manifest_path)
            or snapshot.get('native_stop', {}).get('revoked_sha256') != _sha(revoked_path)):
        _fail('setup_epoch_terminal_receipt_invalid')
    for row in rows:
        command = (row['kind'], 'ls', '-a', '--no-trunc', '--filter', 'id=' + row['id'],
                   '--format', '{{.ID}}') if row['kind'] == 'container' else (
                   'network', 'ls', '--no-trunc', '--filter', 'id=' + row['id'], '--format', '{{.ID}}')
        if _docker(*command).stdout.strip():
            _fail('setup_epoch_resource_still_present')
    before = _setup_provider_pins(root)
    try:
        pool = _provider_snapshot(root)
        with closing(sqlite3.connect('file:' + str(controls / 'provider/tunnel.sqlite3') + '?mode=ro',
                                     uri=True, timeout=1)) as db:
            pool_rows = db.execute('SELECT COUNT(*) FROM pool').fetchone()[0]
            tunnel_rows, tunnel_bytes = db.execute(
                'SELECT COUNT(*),COALESCE(SUM(uploaded+downloaded),0) FROM tunnels').fetchone()
    except (sqlite3.Error, ValueError, TypeError, KeyError):
        _fail('setup_provider_ledger_unavailable')
    if _setup_provider_pins(root) != before:
        _fail('setup_provider_ledger_changed')
    config = pool.get('config')
    duration = config.get('duration') if isinstance(config, dict) else None
    if (not isinstance(config, dict) or config.get('authority') != AUTHORITY
            or config.get('producer_manifest_sha256') != _sha(manifest_path)
            or config.get('max_connections') != plan['limits']['max_connections']
            or config.get('max_bytes') != plan['limits']['max_bytes']
            or type(duration) is not int or not 1 <= duration <= plan['limits']['duration_seconds']
            or config.get('native_run_duration') != duration
            or type(pool.get('used_tunnels')) is not int
            or not 0 <= pool['used_tunnels'] <= config['max_connections']
            or type(pool.get('charged_tunnel_bytes')) is not int
            or not 0 <= pool['charged_tunnel_bytes'] <= config['max_bytes']
            or type(pool.get('created')) not in (int, float)
            or not math.isfinite(pool['created'])
            or pool['created'] < datetime.strptime(
                approval['approved_at'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).timestamp()
            or pool['created'] + duration > datetime.strptime(
                approval['absolute_deadline'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).timestamp()
            or set(pool.get('tunnel_phases', {})) - {'closed'}
            or sum(pool['tunnel_phases'].values()) != pool['used_tunnels']
            or pool_rows != 1 or tunnel_rows != pool['used_tunnels']
            or tunnel_bytes != pool['charged_tunnel_bytes']):
        _fail('setup_provider_accounting_invalid')
    return {'plan_sha256': _sha(root / 'plan.json'),
            'terminal_sha256': _sha(terminal_path), 'revoked_sha256': _sha(revoked_path),
            'cleanup_sha256': _sha(cleanup_path), 'provider_pins': before,
            'checkpoint_sha256': _sha(checkpoint_path / 'receipt.json'),
            'checkpoint_path': checkpoint_path, 'checkpoint': checkpoint,
            'used_connections': pool['used_tunnels'],
            'charged_bytes': pool['charged_tunnel_bytes']}


def _verify_setup_epoch_link(root: Path, plan: dict, approval: dict, *,
                             allow_expired: bool = False) -> None:
    controls = _controls(root)
    link = _read_json(controls / 'setup-epoch.json')
    required = {'kind', 'epoch_index', 'previous_run_root', 'previous_plan_sha256',
                'previous_terminal_sha256', 'previous_revoked_sha256',
                'previous_cleanup_sha256', 'previous_provider_pins',
                'previous_checkpoint_sha256', 'used_before', 'grant_sha256',
                'current_plan_sha256', 'absolute_deadline'}
    if (set(link) != required or link['kind'] != 'native-setup-epoch-v1'
            or type(link['epoch_index']) is not int or not 2 <= link['epoch_index'] <= 16
            or link['current_plan_sha256'] != _sha(root / 'plan.json')
            or link['absolute_deadline'] != approval['absolute_deadline']
            or link['grant_sha256'] != _sha(controls / 'approval.json')
            or not isinstance(link['used_before'], dict)
            or set(link['used_before']) != {'connections', 'bytes'}):
        _fail('setup_epoch_link_invalid')
    previous = _private_root(Path(link['previous_run_root']))
    if previous == root or previous == Path(approval['initial_run_root']).resolve() and link['epoch_index'] != 2:
        _fail('setup_epoch_link_invalid')
    previous_approval = _read_json(_controls(previous) / 'approval.json')
    if previous_approval != approval:
        _fail('setup_epoch_grant_changed')
    prior_link_path = _controls(previous) / 'setup-epoch.json'
    prior_index = _read_json(prior_link_path)['epoch_index'] if prior_link_path.exists() else 1
    if prior_index + 1 != link['epoch_index']:
        _fail('setup_epoch_order_invalid')
    prior = _setup_terminal_accounting(previous, approval, allow_expired=allow_expired)
    used_before = ({'connections': 0, 'bytes': 0} if prior_index == 1 else
                   _read_json(prior_link_path)['used_before'])
    cumulative = {'connections': used_before['connections'] + prior['used_connections'],
                  'bytes': used_before['bytes'] + prior['charged_bytes']}
    if (link['previous_plan_sha256'] != prior['plan_sha256']
            or link['previous_terminal_sha256'] != prior['terminal_sha256']
            or link['previous_revoked_sha256'] != prior['revoked_sha256']
            or link['previous_cleanup_sha256'] != prior['cleanup_sha256']
            or link['previous_provider_pins'] != prior['provider_pins']
            or link['previous_checkpoint_sha256'] != prior['checkpoint_sha256']
            or link['used_before'] != cumulative
            or plan['limits']['max_connections'] != approval['limits']['max_connections'] - cumulative['connections']
            or plan['limits']['max_bytes'] != approval['limits']['max_bytes'] - cumulative['bytes']
            or plan['limits']['duration_seconds'] > approval['limits']['duration_seconds']):
        _fail('setup_epoch_residual_mismatch')
    successor = _read_json(_controls(previous) / 'setup-successor.json')
    if successor != {'kind': 'native-setup-successor-v1', 'next_run_root': str(root),
                     'next_plan_sha256': _sha(root / 'plan.json'),
                     'epoch_receipt_sha256': _sha(controls / 'setup-epoch.json')}:
        _fail('setup_epoch_successor_changed')
    copied = controls / 'research/setup-checkpoint'
    for name, digest in prior['checkpoint']['files'].items():
        path = copied / name
        if digest is None:
            if path.exists() or path.is_symlink():
                _fail('setup_epoch_checkpoint_copy_changed')
        elif _sha(_file(path, private=True)) != digest:
            _fail('setup_epoch_checkpoint_copy_changed')
    if _sha(copied / 'receipt.json') != prior['checkpoint_sha256']:
        _fail('setup_epoch_checkpoint_copy_changed')


def setup_next_epoch(run_root: Path, next_run_root: Path) -> dict:
    """Prepare one fresh physical run under a signed residual setup grant."""
    root = _private_root(run_root)
    next_run_root = Path(next_run_root)
    if (not next_run_root.is_absolute() or next_run_root.is_symlink()
            or next_run_root.exists() or next_run_root == root
            or next_run_root.is_relative_to(root) or root.is_relative_to(next_run_root)
            or next_run_root.resolve(strict=False) != next_run_root):
        _fail('setup_next_root_invalid')
    with _owner_lock(root):
        controls = _controls(root)
        if (controls / 'setup-successor.json').exists():
            _fail('setup_epoch_successor_already_exists')
        plan = _verified_plan(root)
        approval = _read_json(controls / 'approval.json')
        if approval.get('kind') != 'native-setup-approval-v2':
            _fail('setup_linked_epoch_required')
        terminal = _setup_terminal_accounting(root, approval)
        ancestor = root
        for _ in range(16):
            link_path = _controls(ancestor) / 'setup-epoch.json'
            if not link_path.exists():
                break
            ancestor = _private_root(Path(_read_json(link_path)['previous_run_root']))
            if (next_run_root.is_relative_to(ancestor)
                    or ancestor.is_relative_to(next_run_root)):
                _fail('setup_next_root_invalid')
        prior_link = controls / 'setup-epoch.json'
        epoch_index = (_read_json(prior_link)['epoch_index'] + 1 if prior_link.exists() else 2)
        if epoch_index > 16:
            _fail('setup_epoch_limit')
        before = (_read_json(prior_link)['used_before'] if prior_link.exists() else
                  {'connections': 0, 'bytes': 0})
        cumulative = {'connections': before['connections'] + terminal['used_connections'],
                      'bytes': before['bytes'] + terminal['charged_bytes']}
        original = approval['limits']
        connections = original['max_connections'] - cumulative['connections']
        bytes_left = original['max_bytes'] - cumulative['bytes']
        deadline = datetime.strptime(approval['absolute_deadline'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
        duration = min(original['duration_seconds'], int(deadline.timestamp() - time.time()) - 5)
        if connections < 1 or bytes_left < 1024 or duration < 30:
            _fail('setup_epoch_allowance_exhausted')
        previous_approval = controls / 'approval.json'
        arguments = argparse.Namespace(
            run_root=str(next_run_root), source=str(root / 'original'),
            brief=str(controls / 'BRIEF.md'), scope_file=str(controls / 'scope.md'),
            scope_sha256=plan['scope_sha256'], relay=str(controls / 'relay'),
            relay_sha256=plan['relay_sha256'], runtime_ca=str(controls / 'runtime-ca.pem'),
            runtime_ca_sha256=plan['runtime_ca_sha256'], image_id=plan['image_id'],
            platform=plan['platform'], target_image_id=None, target_port=None,
            target_command=None, source_only=False, setup_only=True,
            setup_engagement_id=plan['setup_only']['engagement_id'],
            setup_operator_id=plan['setup_only']['operator_id'],
            setup_scope_signature=str(controls / 'setup-scope.sig'),
            setup_allowed_signers=str(controls / 'setup-allowed-signers'),
            setup_trusted_fingerprint=plan['setup_only']['trusted_fingerprint'],
            setup_max_workspace_bytes=plan['setup_only']['max_workspace_bytes'],
            source_runtime=None, build_command=None, go_toolchain=None, module_cache=None,
            kanboard_capture=False, t01_capture=False, origin_ingress=False,
            mutable_path=[], expected_skill_id=[], model=plan['model'],
            provider_route=plan['provider_route'], provider_authority=plan['provider_authority'],
            max_connections=connections, max_bytes=bytes_left, duration_seconds=duration)
        prepared = prepare(arguments)
        next_controls = _controls(next_run_root)
        checkpoint_copy = next_controls / 'research/setup-checkpoint'
        checkpoint_copy.mkdir(mode=0o700)
        for name, digest in terminal['checkpoint']['files'].items():
            if digest is not None:
                shutil.copy2(terminal['checkpoint_path'] / name, checkpoint_copy / name)
                (checkpoint_copy / name).chmod(0o600)
        shutil.copy2(terminal['checkpoint_path'] / 'receipt.json', checkpoint_copy / 'receipt.json')
        (checkpoint_copy / 'receipt.json').chmod(0o600)
        shutil.copy2(previous_approval, next_controls / 'approval.json')
        (next_controls / 'approval.json').chmod(0o600)
        link = {'kind': 'native-setup-epoch-v1', 'epoch_index': epoch_index,
                'previous_run_root': str(root), 'previous_plan_sha256': terminal['plan_sha256'],
                'previous_terminal_sha256': terminal['terminal_sha256'],
                'previous_revoked_sha256': terminal['revoked_sha256'],
                'previous_cleanup_sha256': terminal['cleanup_sha256'],
                'previous_provider_pins': terminal['provider_pins'],
                'previous_checkpoint_sha256': terminal['checkpoint_sha256'],
                'used_before': cumulative, 'grant_sha256': _sha(previous_approval),
                'current_plan_sha256': _sha(next_run_root / 'plan.json'),
                'absolute_deadline': approval['absolute_deadline']}
        _write_json(next_controls / 'setup-epoch.json', link, once=True)
        marker = {'kind': 'native-setup-successor-v1', 'next_run_root': str(next_run_root),
                  'next_plan_sha256': prepared['plan_sha256'],
                  'epoch_receipt_sha256': _sha(next_controls / 'setup-epoch.json')}
        _write_json(controls / 'setup-successor.json', marker, once=True)
        _verify_setup_epoch_link(next_run_root, _verified_plan(next_run_root), approval)
        return {'status': 'prepared_residual_setup_epoch', 'run_root': str(next_run_root),
                'epoch_index': epoch_index, 'plan_sha256': prepared['plan_sha256'],
                'remaining_connections': connections, 'remaining_bytes': bytes_left,
                'duration_seconds': duration, 'absolute_deadline': approval['absolute_deadline'],
                'checkpoint_sha256': terminal['checkpoint_sha256'],
                'provider_request_count': None, 'monetary_spend': None}


def setup_chain_snapshot(run_root: Path) -> dict:
    """Read-only host proof of cumulative v2 setup use after the final stop.

    Consumers must separately validate the frozen setup output; this proves
    only the linked setup authority, physical stops, cleanup and accounting.
    """
    root = _private_root(run_root)
    plan = _verified_plan(root, allow_expired_setup=True)
    controls = _controls(root)
    approval = _read_json(controls / 'approval.json')
    if 'setup_only' not in plan or approval.get('kind') != 'native-setup-approval-v2':
        _fail('setup_linked_epoch_required')
    current = _setup_terminal_accounting(root, approval, allow_frozen=True,
                                         allow_expired=True)
    link_path = controls / 'setup-epoch.json'
    used_before = (_read_json(link_path)['used_before'] if link_path.exists() else
                   {'connections': 0, 'bytes': 0})
    cumulative = {'connections': used_before['connections'] + current['used_connections'],
                  'bytes': used_before['bytes'] + current['charged_bytes']}
    if (cumulative['connections'] > approval['limits']['max_connections']
            or cumulative['bytes'] > approval['limits']['max_bytes']):
        _fail('setup_epoch_residual_mismatch')
    chain = []
    cursor = root
    for _ in range(16):
        epoch_path = _controls(cursor) / 'setup-epoch.json'
        chain.append({'run_root': str(cursor), 'plan_sha256': _sha(cursor / 'plan.json'),
                      'epoch_sha256': _sha(epoch_path) if epoch_path.exists() else None})
        if not epoch_path.exists():
            break
        cursor = _private_root(Path(_read_json(epoch_path)['previous_run_root']))
    else:
        _fail('setup_epoch_limit')
    if (str(cursor) != approval['initial_run_root']
            or _sha(cursor / 'plan.json') != approval['plan_sha256']):
        _fail('setup_initial_grant_mismatch')
    chain.reverse()
    return {'kind': 'native-setup-chain-snapshot-v1',
            'initial_run_root': approval['initial_run_root'],
            'initial_plan_sha256': approval['plan_sha256'],
            'current_run_root': str(root), 'current_plan_sha256': _sha(root / 'plan.json'),
            'approval_sha256': _sha(controls / 'approval.json'),
            'epoch_index': len(chain), 'cumulative_used': cumulative,
            'original_limits': approval['limits'],
            'absolute_deadline': approval['absolute_deadline'],
            'current_terminal_sha256': current['terminal_sha256'],
            'current_checkpoint_sha256': current['checkpoint_sha256'],
            'chain_sha256': hashlib.sha256(canonical_json_bytes(chain)).hexdigest(),
            'provider_request_count': None, 'monetary_spend': None}


def _poststop_role_grant_boundary(root: Path, dispatch_id: str) -> Path:
    plan = _verified_plan(root)
    if 'kanboard_capture' not in plan:
        _fail('kanboard_recovery_not_configured')
    controls = _controls(root)
    dispatch = _read_json(controls / 'dispatch' / (dispatch_id + '.json'))
    if dispatch.get('dispatch_id') != dispatch_id or dispatch.get('status') != 'unknown_effect':
        _fail('kanboard_recovery_dispatch_not_unknown')
    _, _, topology = _kanboard_recovery_window(root, dispatch_id, dispatch.get('role'))
    final_path = controls / 'final.json'
    recovery_path = controls / 'recovery.json'
    if final_path.exists():
        terminal = _read_json(final_path)
        stopped = terminal.get('status') == 'stopped_complete' and terminal.get('native_stop', {}).get('status') == 'stopped'
    elif recovery_path.exists():
        terminal = _read_json(recovery_path)
        stopped = terminal.get('status') == 'recovered_exact_resources' and terminal.get('native_state') == 'stopped'
    else:
        _fail('kanboard_recovery_run_not_stopped')
    if (not stopped or terminal.get('host_snapshot', {}).get('status') != 'complete'
            or terminal.get('capture_stop', {}).get('status') != 'complete'
            or terminal.get('cleanup', {}).get('status') != 'complete'
            or terminal.get('capture_cleanup', {}).get('status') != 'complete'):
        _fail('kanboard_recovery_run_not_stopped')
    if _origin_enabled(plan):
        origin_stopped = controls / 'origin/stopped.json'
        origin_cleaned = controls / 'origin/cleanup.json'
        if (terminal.get('origin_stop', {}).get('status') != 'complete'
                or terminal.get('origin_cleanup', {}).get('status') != 'complete'
                or terminal['origin_stop'].get('receipt_sha256') != _sha(origin_stopped)
                or terminal['origin_cleanup'].get('receipt_sha256') != _sha(origin_cleaned)):
            _fail('kanboard_recovery_ingress_stop_unverified')
    manifest_path = controls / 'producer-manifest.json'
    manifest = _read_json(manifest_path)
    resources = _read_json(controls / 'resources.json')
    run = _read_json(controls / 'native-state/RUN.json')
    revoked_path = controls / 'native-state/REVOKED'
    revoked = _read_json(revoked_path)
    ids = [row.get('id') for row in resources.get('resources', []) if row.get('kind') == 'container']
    manifest_ids = [row.get('id') for row in manifest.get('producers', [])]
    manifest_sha = _sha(manifest_path)
    revoked_sha = _sha(revoked_path)
    if (len(ids) != 8 or len(set(ids)) != 8 or not all(isinstance(value, str) and HEX_RE.fullmatch(value) for value in ids)
            or ids != manifest_ids or run.get('ids') != ids or revoked.get('ids') != ids
            or run.get('manifest_sha256') != manifest_sha
            or revoked.get('manifest_sha256') != manifest_sha
            or revoked.get('producers_verified_stopped') is not True):
        _fail('kanboard_recovery_stop_proof_changed')
    snapshot_path = controls / 'host-snapshot.json'
    snapshot = _read_json(snapshot_path)
    if (terminal['host_snapshot'].get('receipt_path') != str(snapshot_path)
            or terminal['host_snapshot'].get('receipt_sha256') != _sha(snapshot_path)
            or snapshot.get('status') != 'complete'
            or snapshot.get('plan_sha256') != _sha(root / 'plan.json')
            or snapshot.get('native_stop', {}).get('manifest_sha256') != manifest_sha
            or snapshot.get('native_stop', {}).get('revoked_sha256') != revoked_sha):
        _fail('kanboard_recovery_snapshot_changed')
    collector = _file(Path(topology['collector_db']), private=True)
    frozen = _read_json(controls / 'observer/target/frozen.json')
    try:
        with closing(sqlite3.connect(collector.as_uri() + '?mode=ro', uri=True)) as db:
            count, maximum = db.execute('SELECT COUNT(*),COALESCE(MAX(id),0) FROM receipts').fetchone()
    except sqlite3.DatabaseError:
        _fail('kanboard_recovery_collector_unavailable')
    if (frozen.get('kind') != 'kanboard-capture-frozen-v1' or frozen.get('target') != 'target'
            or frozen.get('native_stop_kind') != 'REVOKED'
            or frozen.get('native_stop_sha256') != revoked_sha
            or frozen.get('producer_manifest_sha256') != manifest_sha
            or frozen.get('sqlite_sha256') != _sha(collector)
            or frozen.get('receipt_count') != count or frozen.get('last_receipt_id') != maximum):
        _fail('kanboard_recovery_frozen_collector_changed')
    return collector


def reconcile_role_grant(run_root: Path, dispatch_id: str) -> dict:
    """Observe one declared S10 effect only after exact owned stop and capture freeze."""
    result = {'status': 'hold_unknown', 'dispatch_id': dispatch_id,
              'scope': 'kanboard_b_q_role_grant_v1', 'retry_original': False,
              'run_resume_allowed': False}
    if not isinstance(dispatch_id, str) or not re.fullmatch(r'[0-9a-f]{32}', dispatch_id):
        return dict(result, reason='dispatch_id_invalid')
    try:
        root = _private_root(Path(run_root))
        with _owner_lock(root):
            collector = _poststop_role_grant_boundary(root, dispatch_id)
            before = _sha(collector)
            observed = _load_recovery_module(root).reconcile_kanboard_role_grant(root, dispatch_id)
            if _sha(collector) != before:
                _fail('kanboard_recovery_collector_changed_during_read')
            return observed
    except (NativeResearchError, OSError, sqlite3.DatabaseError, TypeError, KeyError, ValueError) as error:
        return dict(result, reason=str(error) if isinstance(error, NativeResearchError)
                    else 'kanboard_recovery_unavailable')


def _origin_transport_proof(root: Path, dispatch_id: str) -> dict:
    """Bind process, native tool and app IDs from stopped host-owned bytes."""
    plan = _verified_plan(root)
    if not _origin_enabled(plan):
        _fail('native_origin_not_configured')
    controls = _controls(root)
    final_path = controls / 'final.json'
    recovery_path = controls / 'recovery.json'
    if final_path.exists():
        terminal = _read_json(final_path)
        terminal_ok = terminal.get('status') == 'stopped_complete'
    elif recovery_path.exists():
        terminal = _read_json(recovery_path)
        terminal_ok = terminal.get('status') == 'recovered_exact_resources' and terminal.get('native_state') == 'stopped'
    else:
        _fail('native_origin_run_not_stopped')
    if (not terminal_ok or terminal.get('host_snapshot', {}).get('status') != 'complete'
            or terminal.get('origin_stop', {}).get('status') != 'complete'
            or terminal.get('origin_cleanup', {}).get('status') != 'complete'
            or terminal.get('capture_stop', {}).get('status') != 'complete'
            or terminal.get('cleanup', {}).get('status') != 'complete'
            or terminal.get('capture_cleanup', {}).get('status') != 'complete'):
        _fail('native_origin_run_not_stopped')
    stop_path, cleanup_path = controls / 'origin/stopped.json', controls / 'origin/cleanup.json'
    stop, cleanup = _read_json(stop_path), _read_json(cleanup_path)
    manifest_path, revoked_path = controls / 'producer-manifest.json', controls / 'native-state/REVOKED'
    manifest, revoked = _read_json(manifest_path), _read_json(revoked_path)
    run, resources = _read_json(controls / 'native-state/RUN.json'), _read_json(controls / 'resources.json')
    ids = [row.get('id') for row in resources.get('resources', []) if row.get('kind') == 'container']
    if (len(ids) != 8 or ids != [item.get('id') for item in manifest.get('producers', [])]
            or run.get('ids') != ids or revoked.get('ids') != ids
            or revoked.get('producers_verified_stopped') is not True
            or stop.get('kind') != 'native-origin-stopped-v1'
            or stop.get('native_stop_kind') != 'REVOKED'
            or stop.get('native_stop_sha256') != _sha(revoked_path)
            or stop.get('producer_manifest_sha256') != _sha(manifest_path)
            or cleanup.get('kind') != 'native-origin-cleanup-v1'
            or cleanup.get('stopped_sha256') != _sha(stop_path)
            or cleanup.get('all_absent') is not True
            or terminal['origin_stop'].get('receipt_sha256') != _sha(stop_path)
            or terminal['origin_cleanup'].get('receipt_sha256') != _sha(cleanup_path)):
        _fail('native_origin_stop_proof_changed')
    sidecars = _read_json(_origin_resources_path(root))
    rows = sidecars.get('resources', [])
    if (sidecars.get('kind') != 'native-origin-resources-v1'
            or sidecars.get('status') != 'removed'
            or sidecars.get('nonce') != resources.get('nonce')
            or [row.get('role') for row in rows] != list(ORIGIN_ROLES)
            or [row.get('target') for row in rows] != list(ORIGIN_ROLES.values())
            or [row.get('id') for row in rows] != cleanup.get('resource_ids')
            or [row.get('id') for row in rows] != [row.get('id') for row in stop.get('containers', [])]
            or any(not isinstance(row.get('id'), str) or not HEX_RE.fullmatch(row['id']) for row in rows)):
        _fail('native_origin_sidecar_set_changed')
    dispatch_path = controls / 'dispatch' / (dispatch_id + '.json')
    dispatch = _read_json(dispatch_path)
    role = dispatch.get('role')
    if (dispatch.get('kind') != 'native-dispatch-v1' or dispatch.get('status') != 'acknowledged'
            or dispatch.get('dispatch_id') != dispatch_id or role not in ORIGIN_ROLES):
        _fail('native_origin_dispatch_not_acknowledged')
    target = ORIGIN_ROLES[role]
    registration_path = controls / 'origin/registrations' / (dispatch_id + '.json')
    registration = _read_json(registration_path)
    sidecar_id = next(row['id'] for row in rows if row['role'] == role)
    if (dispatch.get('origin_registration_sha256') != _sha(registration_path)
            or registration.get('kind') != 'native-origin-registration-v1'
            or registration.get('dispatch_id') != dispatch_id
            or registration.get('role') != role or registration.get('target') != target
            or registration.get('run_nonce') != resources['nonce']
            or registration.get('agent_container_id') != _resources(root)[role]
            or registration.get('target_container_id') != _resources(root)[target]
            or registration.get('sidecar_container_id') != sidecar_id
            or registration.get('dispatch_pre_sha256') !=
               _sha(controls / 'dispatch' / (dispatch_id + '.pre.json'))
            or registration.get('producer_manifest_sha256') != _sha(manifest_path)
            or registration.get('source_manifest_sha256') != plan['source_manifest_sha256']
            or registration.get('target_image_id') != plan['target_image_id']
            or registration.get('binary_sha256') != plan['native_origin']['binary_sha256']):
        _fail('native_origin_registration_changed')
    trace_path = controls / 'dispatch' / (dispatch_id + '.trace.json')
    trace = _read_json(trace_path)
    if (dispatch.get('native_trace_sha256') != _sha(trace_path)
            or trace.get('kind') != 'protected-native-event-trace-v1'
            or trace.get('session_id') != dispatch.get('session_id')
            or not isinstance(trace.get('events'), list)):
        _fail('native_origin_trace_changed')
    claims = dispatch.get('native_response_claims')
    if not isinstance(claims, list) or not claims:
        _fail('native_origin_native_ids_absent')
    native_ids = []
    events = {item.get('line'): item for item in trace['events'] if isinstance(item, dict)}
    for claim in claims:
        if not isinstance(claim, dict) or not isinstance(claim.get('request_ids'), list):
            _fail('native_origin_native_claim_invalid')
        event = events.get(claim.get('line'))
        if (not isinstance(event, dict) or event.get('part_type') != 'tool'
                or event.get('status') != 'completed' or event.get('tool') != 'shell'
                or claim.get('tool') != 'shell'
                or claim.get('input_sha256') != event.get('input_sha256')
                or claim.get('output_sha256') != event.get('output_sha256')
                or not claim['request_ids']
                or any(not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{32}', value)
                       for value in claim['request_ids'])):
            _fail('native_origin_native_claim_invalid')
        native_ids.extend(claim['request_ids'])
    if len(native_ids) != len(set(native_ids)):
        _fail('native_origin_native_id_duplicate')
    all_rows, seen_ids = [], set()
    for source_role in ORIGIN_ROLES:
        ledger_path = controls / 'origin/ledger' / source_role / 'requests.jsonl'
        if (not ledger_path.exists() or ledger_path.stat().st_size > 16 * 1024 * 1024
                or _sha(ledger_path) != stop.get('ledger_sha256', {}).get(source_role)):
            _fail('native_origin_ledger_changed')
        for line in ledger_path.read_bytes().splitlines():
            try:
                row = json.loads(line)
            except (UnicodeError, ValueError):
                _fail('native_origin_ledger_invalid')
            request_id = row.get('broker_request_id') if isinstance(row, dict) else None
            if (row.get('kind') != 'native-origin-request-v1'
                    or row.get('role') != source_role or row.get('target') != ORIGIN_ROLES[source_role]
                    or row.get('run_nonce') != resources['nonce']
                    or not isinstance(request_id, str) or not re.fullmatch(r'[0-9a-f]{32}', request_id)
                    or request_id in seen_ids):
                _fail('native_origin_ledger_invalid')
            seen_ids.add(request_id)
            if row.get('dispatch_id') != dispatch_id:
                continue
            ancestry = row.get('ancestry')
            if (source_role != role or row.get('gate_nonce') != registration.get('gate_nonce')
                    or row.get('root_pid') != registration.get('root_pid')
                    or row.get('root_starttime') != registration.get('root_starttime')
                    or row.get('sender_uid') != os.getuid()
                    or not isinstance(ancestry, list) or not 1 <= len(ancestry) <= 64
                    or not isinstance(ancestry[0], dict) or not isinstance(ancestry[-1], dict)
                    or ancestry[0].get('pid') != row.get('sender_pid')
                    or ancestry[0].get('starttime') != row.get('sender_starttime')
                    or ancestry[-1].get('pid') != registration.get('root_pid')
                    or ancestry[-1].get('starttime') != registration.get('root_starttime')
                    or row.get('method') not in ('GET', 'POST')
                    or any(not isinstance(row.get(key), str) or not HEX_RE.fullmatch(row[key])
                           for key in ('route_sha256', 'body_sha256', 'request_sha256',
                                       'response_sha256'))):
                _fail('native_origin_ledger_binding_invalid')
            all_rows.append(row)
    ledger_ids = [row['broker_request_id'] for row in all_rows]
    if not ledger_ids or len(ledger_ids) != len(set(ledger_ids)):
        _fail('native_origin_ledger_ids_absent')
    window_path = controls / 'observer' / target / ('window-' + dispatch_id + '.json')
    window = _read_json(window_path)
    topology = window.get('topology')
    if not isinstance(topology, dict) or not isinstance(topology.get('collector_db'), str):
        _fail('native_origin_window_invalid')
    collector = _file(Path(topology['collector_db']), private=True)
    frozen_path = controls / 'observer' / target / 'frozen.json'
    frozen = _read_json(frozen_path)
    if (frozen.get('kind') != 'kanboard-capture-frozen-v1'
            or frozen.get('target') != target or frozen.get('native_stop_kind') != 'REVOKED'
            or frozen.get('native_stop_sha256') != _sha(revoked_path)
            or frozen.get('producer_manifest_sha256') != _sha(manifest_path)
            or frozen.get('sqlite_sha256') != _sha(collector)
            or window.get('dispatch_sha256') !=
               _sha(controls / 'dispatch' / (dispatch_id + '.pre.json'))):
        _fail('native_origin_frozen_capture_changed')
    with closing(sqlite3.connect(collector.as_uri() + '?mode=ro', uri=True)) as db:
        receipts = db.execute('SELECT id,peer,payload FROM receipts ORDER BY id').fetchall()
    before_id = window.get('collector_max_id_before')
    close_path = controls / 'origin/window-close' / (dispatch_id + '.json')
    close = _read_json(close_path)
    after_id = close.get('collector_max_id_after')
    prefix = [row for row in receipts if type(before_id) is int and row[0] <= before_id]
    closed_rows = [row for row in receipts if type(after_id) is int and row[0] <= after_id]
    delta = [row for row in receipts if type(before_id) is int and type(after_id) is int
             and before_id < row[0] <= after_id]
    prefix_digest = hashlib.sha256(json.dumps(prefix, separators=(',', ':'),
                                              ensure_ascii=True).encode()).hexdigest()
    closed_digest = hashlib.sha256(json.dumps(closed_rows, separators=(',', ':'),
                                              ensure_ascii=True).encode()).hexdigest()
    if (type(before_id) is not int or before_id < 0
            or type(after_id) is not int or after_id < before_id
            or dispatch.get('origin_window_close_sha256') != _sha(close_path)
            or close.get('kind') != 'native-origin-window-close-v1'
            or close.get('dispatch_id') != dispatch_id or close.get('target') != target
            or close.get('window_sha256') != _sha(window_path)
            or close.get('collector_count_after') != len(closed_rows)
            or close.get('collector_prefix_sha256_after') != closed_digest
            or prefix_digest != window.get('collector_prefix_sha256')
            or len(prefix) != window.get('collector_count_before')
            or len(receipts) != frozen.get('receipt_count')
            or (receipts[-1][0] if receipts else 0) != frozen.get('last_receipt_id')
            or not 1 <= len(delta) <= 5000):
        _fail('native_origin_capture_window_ambiguous')
    app_ids = []
    for _, peer, payload in delta:
        try:
            item = json.loads(payload)
        except (UnicodeError, ValueError):
            _fail('native_origin_receipt_invalid')
        request_id = (item.get('request_id') if 't01_capture' in plan else
                      item.get('broker_request_id')) if isinstance(item, dict) else None
        broker_peer = (item.get('peer_ip') if 't01_capture' in plan else
                       item.get('broker_peer_ip')) if isinstance(item, dict) else None
        if (peer != topology.get('app_observer_ip') or broker_peer != '127.0.0.1'
                or not isinstance(request_id, str)
                or not re.fullmatch(r'[0-9a-f]{32}', request_id)):
            _fail('native_origin_receipt_binding_invalid')
        app_ids.append(request_id)
    if (len(app_ids) != len(set(app_ids)) or set(app_ids) != set(ledger_ids)
            or set(app_ids) != set(native_ids)):
        _fail('native_origin_request_ids_disagree')
    if 't01_capture' in plan:
        closed = _read_json(controls / 'observer' / target / ('closed-' + dispatch_id + '.json'))
        if (closed.get('window_sha256') != _sha(window_path)
                or set(closed.get('native_response_ids', [])) != set(native_ids)
                or set(closed.get('joined_request_ids', [])) != set(app_ids)):
            _fail('native_origin_t01_window_changed')
    return {'kind': 'native-origin-transport-proof-v1',
            'status': 'process_request_attributed',
            'dispatch_id': dispatch_id, 'role': role, 'target': target,
            'source_manifest_sha256': plan['source_manifest_sha256'],
            'target_image_id': plan['target_image_id'],
            'native_stop_sha256': _sha(revoked_path),
            'producer_manifest_sha256': _sha(manifest_path),
            'sidecar_stop_sha256': _sha(stop_path),
            'sidecar_cleanup_sha256': _sha(cleanup_path),
            'registration_sha256': _sha(registration_path),
            'ingress_ledger_sha256': stop['ledger_sha256'][role],
            'window_close_sha256': _sha(close_path),
            'frozen_capture_sha256': _sha(frozen_path),
            'native_trace_sha256': _sha(trace_path),
            'native_tool_claims': claims,
            'broker_request_ids': sorted(app_ids),
            'request_rows_sha256': hashlib.sha256(json.dumps(all_rows, sort_keys=True).encode()).hexdigest(),
            'semantic_verdict': 'unreviewed',
            'runtime_qualification': 'separate_review_required'}


def reconcile_origin_transport(run_root: Path, dispatch_id: str) -> dict:
    if not isinstance(dispatch_id, str) or not re.fullmatch(r'[0-9a-f]{32}', dispatch_id):
        return {'status': 'held', 'reason': 'dispatch_id_invalid', 'dispatch_id': dispatch_id}
    root = _private_root(Path(run_root))
    with _owner_lock(root):
        try:
            proof = _origin_transport_proof(root, dispatch_id)
            path = _controls(root) / 'origin/proofs' / (dispatch_id + '.json')
            if path.exists():
                if _read_json(path) != proof:
                    _fail('native_origin_existing_proof_changed')
            else:
                _write_json(path, proof, once=True)
            dispatch_path = _controls(root) / 'dispatch' / (dispatch_id + '.json')
            dispatch = _read_json(dispatch_path)
            if dispatch.get('origin_transport_proof_sha256') not in (None, _sha(path)):
                _fail('native_origin_dispatch_proof_changed')
            dispatch['origin_transport_proof_sha256'] = _sha(path)
            _write_json(dispatch_path, dispatch)
            return {'status': proof['status'], 'dispatch_id': dispatch_id,
                    'transport_proof_sha256': _sha(path),
                    'broker_request_count': len(proof['broker_request_ids']),
                    'semantic_verdict': proof['semantic_verdict'],
                    'runtime_qualification': proof['runtime_qualification']}
        except (NativeResearchError, OSError, ValueError, KeyError, TypeError, sqlite3.DatabaseError) as error:
            code = str(error) if isinstance(error, NativeResearchError) else 'native_origin_evidence_unavailable'
            return {'status': 'held', 'reason': code, 'dispatch_id': dispatch_id}

def _t01_poststop_rows(root: Path, dispatch_id: str) -> tuple[list[dict], Path, Path, str]:
    """Validate one frozen target and every closed receipt interval, without a live call."""
    plan = _verified_plan(root)
    if 't01_capture' not in plan:
        _fail('t01_semantic_capture_not_configured')
    controls = _controls(root)
    dispatch = _read_json(controls / 'dispatch' / (dispatch_id + '.json'))
    role = dispatch.get('role')
    if (dispatch.get('dispatch_id') != dispatch_id or dispatch.get('status') != 'acknowledged'
            or role not in ('researcher', 'resume', 'reviewer-1', 'reviewer-2')):
        _fail('t01_semantic_dispatch_unavailable')
    target = 'target' if role in ('researcher', 'resume') else 'review-target-' + role[-1]
    slot = controls / 'observer' / target
    final = _read_json(controls / 'final.json')
    if (final.get('status') != 'stopped_complete' or
            final.get('native_stop', {}).get('status') != 'stopped' or
            final.get('host_snapshot', {}).get('status') != 'complete' or
            final.get('capture_stop', {}).get('status') != 'complete' or
            final.get('cleanup', {}).get('status') != 'complete' or
            final.get('capture_cleanup', {}).get('status') != 'complete'):
        _fail('t01_semantic_run_not_stopped_complete')
    manifest_path = controls / 'producer-manifest.json'
    revoked_path = controls / 'native-state/REVOKED'
    manifest = _read_json(manifest_path)
    run = _read_json(controls / 'native-state/RUN.json')
    revoked = _read_json(revoked_path)
    resources = _read_json(controls / 'resources.json')
    ids = [row.get('id') for row in resources.get('resources', []) if row.get('kind') == 'container']
    if (len(ids) != 8 or len(set(ids)) != 8 or
            ids != [row.get('id') for row in manifest.get('producers', [])] or
            run.get('ids') != ids or revoked.get('ids') != ids or
            revoked.get('producers_verified_stopped') is not True or
            run.get('manifest_sha256') != _sha(manifest_path) or
            revoked.get('manifest_sha256') != _sha(manifest_path)):
        _fail('t01_semantic_stop_proof_changed')
    snapshot_path = controls / 'host-snapshot.json'
    snapshot = _read_json(snapshot_path)
    if (final['host_snapshot'].get('receipt_path') != str(snapshot_path) or
            final['host_snapshot'].get('receipt_sha256') != _sha(snapshot_path) or
            snapshot.get('status') != 'complete' or
            snapshot.get('plan_sha256') != _sha(root / 'plan.json') or
            snapshot.get('native_stop', {}).get('manifest_sha256') != _sha(manifest_path) or
            snapshot.get('native_stop', {}).get('revoked_sha256') != _sha(revoked_path)):
        _fail('t01_semantic_host_snapshot_changed')
    target_summary, _, _ = _snapshot_tree(root / target)
    if target_summary != {key: value for key, value in snapshot.get('targets', {}).get(target, {}).items()
                          if key in ('files', 'bytes', 'tree_sha256')}:
        _fail('t01_semantic_target_bytes_changed')
    topology_path = controls / 'capture-topology.json'
    activation = _read_json(controls / 'activation.json')
    topology = _read_json(topology_path).get(target)
    if (activation.get('capture_topology_sha256') != _sha(topology_path) or
            not isinstance(topology, dict) or topology.get('target') != target or
            topology.get('source_manifest_sha256') != T01_SOURCE_SHA or
            topology.get('status') != 'topology_attested_original_session_origin_held' or
            topology.get('collector_db') != str(slot / 'receipts/receipts.sqlite') or
            (role.startswith('reviewer-') and dispatch.get('review_target_id') != topology.get('target_id'))):
        _fail('t01_semantic_topology_changed')
    collector = _file(slot / 'receipts/receipts.sqlite', private=True)
    if any(collector.with_name(collector.name + suffix).exists()
           for suffix in ('-wal', '-shm', '-journal')):
        _fail('t01_semantic_collector_sidecar_present')
    frozen = _read_json(slot / 'frozen.json')
    if (frozen.get('kind') != 'kanboard-capture-frozen-v1' or
            frozen.get('target') != target or frozen.get('native_stop_kind') != 'REVOKED' or
            frozen.get('native_stop_sha256') != _sha(revoked_path) or
            frozen.get('producer_manifest_sha256') != _sha(manifest_path) or
            frozen.get('sqlite_sha256') != _sha(collector)):
        _fail('t01_semantic_collector_freeze_changed')
    with closing(sqlite3.connect(collector.as_uri() + '?mode=ro&immutable=1', uri=True)) as db:
        if db.execute('PRAGMA quick_check').fetchone() != ('ok',):
            _fail('t01_semantic_collector_invalid')
        raw = db.execute('SELECT id,peer,payload FROM receipts ORDER BY id').fetchall()
    if (len(raw) != frozen.get('receipt_count') or not raw or
            raw[-1][0] != frozen.get('last_receipt_id') or raw[0][0] != 1 or
            raw[0][1] != topology.get('app_observer_ip')):
        _fail('t01_semantic_collector_rows_changed')
    setup = json.loads(raw[0][2])
    readback = _read_json(slot / 'setup-readback.json')
    if (setup.get('kind') != 't01-kanboard-setup-v1' or
            setup.get('source_manifest_sha256') != T01_SOURCE_SHA or
            setup.get('admin_default_revoked') is not True or
            setup.get('project_count') != 0 or setup.get('swimlane_count') != 0 or
            not isinstance(setup.get('actor_ids'), dict) or
            set(setup['actor_ids']) != {'A', 'B'} or
            not all(type(value) is int and value > 0 for value in setup['actor_ids'].values()) or
            setup['actor_ids']['A'] == setup['actor_ids']['B'] or
            readback != {'kind': 't01-setup-readback-v1',
                         'receipt_sha256': hashlib.sha256(raw[0][2].encode()).hexdigest(),
                         'db_sha256': setup.get('db_sha256')}):
        _fail('t01_semantic_setup_changed')
    windows = []
    for path in slot.glob('closed-*.json'):
        ident = path.stem.removeprefix('closed-')
        if not re.fullmatch(r'[0-9a-f]{32}', ident):
            _fail('t01_semantic_closed_window_invalid')
        closed = _read_json(path)
        window_path = slot / ('window-' + ident + '.json')
        window = _read_json(window_path)
        record = _read_json(controls / 'dispatch' / (ident + '.json'))
        pre_path = controls / 'dispatch' / (ident + '.pre.json')
        pre = _read_json(pre_path)
        if (closed.get('kind') != 'kanboard-t01-window-closed-v1' or
                closed.get('dispatch_id') != ident or
                closed.get('window_sha256') != _sha(window_path) or
                window.get('kind') != 'kanboard-t01-window-v1' or
                window.get('dispatch_id') != ident or window.get('target') != target or
                window.get('topology') != topology or
                window.get('dispatch_sha256') != _sha(pre_path) or
                record.get('status') != 'acknowledged' or record.get('dispatch_id') != ident or
                record.get('role') != window.get('role') or
                record.get('session_id') != window.get('session_id') or
                pre.get('status') != 'unknown_effect' or pre.get('dispatch_id') != ident or
                pre.get('role') != record.get('role') or
                (target == 'target' and record['role'] not in ('researcher', 'resume')) or
                (target != 'target' and record['role'] != 'reviewer-' + target[-1])):
            _fail('t01_semantic_window_binding_changed')
        windows.append((window, closed))
    windows.sort(key=lambda pair: pair[0].get('collector_count_before', -1))
    if not windows or not any(row[0]['dispatch_id'] == dispatch_id for row in windows):
        _fail('t01_semantic_selected_window_missing')
    selected = []
    previous = 1
    seen_ids = set()
    for window, closed in windows:
        before = window.get('collector_count_before')
        after = closed.get('collector_count_after')
        if (type(before) is not int or type(after) is not int or before != previous or
                not before <= after <= len(raw) or
                window.get('collector_max_id_before') != raw[before - 1][0] or
                window.get('collector_prefix_sha256') != hashlib.sha256(
                    json.dumps(raw[:before], separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()):
            _fail('t01_semantic_window_interval_changed')
        segment = raw[before:after]
        receipts = []
        for row_id, peer, payload in segment:
            receipt = json.loads(payload)
            if (peer != topology.get('app_observer_ip') or
                    not isinstance(receipt, dict) or
                    receipt.get('kind') != 't01-kanboard-jsonrpc-v1' or
                    receipt.get('peer_ip') != topology.get('native_client_ip') or
                    not isinstance(receipt.get('request_id'), str) or
                    not re.fullmatch(r'[0-9a-f]{32}', receipt['request_id']) or
                    receipt['request_id'] in seen_ids or
                    receipt.get('actor_user_id') != setup['actor_ids'].get(receipt.get('actor'))):
                _fail('t01_semantic_receipt_identity_changed')
            seen_ids.add(receipt['request_id'])
            receipts.append({'row_id': row_id, 'request_id': receipt['request_id'],
                             'actor': receipt.get('actor'), 'method': receipt.get('method'),
                             'result_class': receipt.get('result_class'),
                             'result_matches_db': receipt.get('result_matches_db')})
            selected.append({'row_id': row_id, 'dispatch_id': window['dispatch_id'],
                             'joined': receipt['request_id'] in closed.get('joined_request_ids', []),
                             'receipt': receipt})
        response_ids = closed.get('native_response_ids')
        joined = closed.get('joined_request_ids')
        if (closed.get('receipt_rows') != receipts or not isinstance(response_ids, list) or
                not isinstance(joined, list) or response_ids != sorted(set(response_ids)) or
                joined != sorted(set(response_ids) & {row['request_id'] for row in receipts})):
            _fail('t01_semantic_window_join_changed')
        previous = after
    if previous != len(raw) or _sha(collector) != frozen['sqlite_sha256']:
        _fail('t01_semantic_collector_changed_during_read')
    target_db = _file(root / target / 'data/db.sqlite', private=True)
    if any(target_db.with_name(target_db.name + suffix).exists()
           for suffix in ('-wal', '-shm', '-journal')):
        _fail('t01_semantic_target_sidecar_present')
    return selected, target_db, collector, target


def reconcile_t01_semantic(run_root: Path, dispatch_id: str, effect_request_id: str) -> dict:
    """Assess the original vulnerable arm after stop; origin remains a separate gate."""
    result = {'status': 'hold_unknown', 'scope': 't01_original_vulnerable_arm',
              'dispatch_id': dispatch_id, 'effect_request_id': effect_request_id,
              'retry_original': False, 'native_origin': 'not_assessed',
              'clean_replay': 'not_assessed', 'fixed_control': 'not_assessed'}
    if (not isinstance(dispatch_id, str) or not re.fullmatch(r'[0-9a-f]{32}', dispatch_id) or
            not isinstance(effect_request_id, str) or
            not re.fullmatch(r'[0-9a-f]{32}', effect_request_id)):
        return dict(result, reason='t01_selection_invalid')
    try:
        root = _private_root(Path(run_root))
        with _poststop_read_lock(root):
            rows, target_db, collector, target = _t01_poststop_rows(root, dispatch_id)
            before_target = _sha(target_db)
            before_collector = _sha(collector)
            module = _load_t01_semantic_module(root)
            with closing(sqlite3.connect(target_db.as_uri() + '?mode=ro&immutable=1', uri=True)) as db:
                observed = module.assess_chain(rows, effect_request_id, dispatch_id, db)
            if _sha(target_db) != before_target or _sha(collector) != before_collector:
                _fail('t01_semantic_bytes_changed_during_read')
            return dict(observed, target=target, target_db_sha256=before_target,
                        collector_sha256=before_collector)
    except (NativeResearchError, OSError, sqlite3.DatabaseError, TypeError, KeyError,
            ValueError, IndexError, json.JSONDecodeError) as error:
        return dict(result, reason=str(error) if isinstance(error, NativeResearchError)
                    else 't01_semantic_unavailable')
    except Exception as error:
        return dict(result, reason=str(error) if error.__class__.__name__ == 'SemanticHold'
                    else 't01_semantic_unavailable')

def _recorded_stop_reason(root: Path) -> str | None:
    """Expose the first recorded trigger, without inferring why the run ended."""
    path = _controls(root) / 'native-state/STOP_REQUEST'
    try:
        path.lstat()
    except FileNotFoundError:
        return None
    except OSError:
        return 'stop_reason_unavailable'
    try:
        if _file(path, private=True).stat().st_size > 32768:
            return 'stop_reason_unavailable'
        value = _read_json(path)
        if (set(value) != {'reason', 'monotonic'}
                or not isinstance(value['reason'], str) or not 1 <= len(value['reason']) <= 128
                or type(value['monotonic']) not in (int, float)
                or not math.isfinite(value['monotonic']) or value['monotonic'] < 0):
            return 'stop_reason_unavailable'
        return value['reason'] if value['reason'] in (
            'operator_stop', 'monotonic_timeout', 'owner_close', 'connect_exited',
            'startup_failure', 'owner_lost', 'stop_owner_lost', 'provider_authority_ended',
            'child_exited_without_stop', 'child_exited_before_prepare',
        ) else 'stop_reason_unrecognized'
    except (OSError, NativeResearchError, OverflowError, RecursionError):
        return 'stop_reason_unavailable'


def status(run_root: Path) -> dict:
    root = _private_root(Path(run_root))
    plan = _plan(root)
    controls = _controls(root)
    final = _read_json(controls / 'final.json') if (controls / 'final.json').exists() else None
    recovery = _read_json(controls / 'recovery.json') if (controls / 'recovery.json').exists() else None
    activation = _read_json(controls / 'activation.json') if (controls / 'activation.json').exists() else None
    try:
        allowance = allowance_snapshot(root) if activation else None
    except (NativeResearchError, OSError, sqlite3.Error):
        allowance = None
    dispatches = []
    for path in sorted((controls / 'dispatch').glob('*.json')):
        if path.name.endswith(('.trace.json', '.pre.json', '.origin.json')):
            continue
        row = _read_json(path)
        item = {key: row.get(key) for key in
                ('dispatch_id', 'role', 'session_id', 'status', 'created_at')}
        origin_path = path.with_name(path.stem + '.origin.json')
        if origin_path.exists():
            item['origin_hold'] = _read_json(origin_path)
        dispatches.append(item)
    result = {'status': 'active' if allowance and allowance['active'] else
            'stopped_complete' if final and final.get('status') == 'stopped_complete' else
            'recovered_exact_resources' if recovery and recovery.get('status') == 'recovered_exact_resources' else
            'prepared' if not activation and not final and not (controls / 'resources.json').exists()
            else 'inactive_or_unresolved',
            'run_root': str(root), 'model': plan['model'], 'limits': plan['limits'],
            'allowance': allowance, 'dispatches': dispatches, 'final': final, 'recovery': recovery,
            'stop_reason': _recorded_stop_reason(root),
            'protected_capture': 'unavailable',
            'provider_request_count': None, 'monetary_spend': None}
    if 'setup_only' in plan:
        frozen = controls / 'setup-output/receipt.json'
        setup_dispatches = _setup_dispatches(root)
        result['setup'] = {'original_source_manifest_sha256': plan['source_manifest_sha256'],
                           'max_workspace_bytes': plan['setup_only']['max_workspace_bytes'],
                           'frozen_proposal_receipt_sha256': _sha(frozen) if frozen.exists() else None,
                           'last_dispatch_id': setup_dispatches[-1]['dispatch_id'] if setup_dispatches else None,
                           'pending_dispatches': _unresolved_dispatches(root),
                           'target_build_executed': False}
    return result


def _load_review_module(root: Path):
    path = _controls(root) / 'experiments/native-review-qualification/fresh_review.py'
    if not path.is_file():
        _fail('fresh_review_module_unavailable')
    spec = importlib.util.spec_from_file_location('native_fresh_review', path)
    if spec is None or spec.loader is None:
        _fail('fresh_review_module_unavailable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _validate_source_check(value: object, input_id: str) -> dict:
    if (not isinstance(value, dict) or set(value) !=
            {'kind', 'input_id', 'effect', 'control', 'rationale'}
            or value['kind'] != 'native-source-check-v1' or value['input_id'] != input_id
            or not isinstance(value['rationale'], str) or not value['rationale'].strip()
            or len(value['rationale'].encode()) > 4096 or CREDENTIAL_TEXT.search(value['rationale'])):
        _fail('source_review_check_invalid')
    _validate_argv(value['effect'])
    _validate_argv(value['control'])
    if value['effect'] == value['control']:
        _fail('source_review_control_missing')
    return value


def _source_evidence_read(raw: str, session: str, digest: str) -> bool:
    read, hashed = False, False
    for line in raw.splitlines():
        event = json.loads(line)
        if not isinstance(event, dict) or event.get('sessionID') != session:
            continue
        part = event.get('part') or {}
        state = part.get('state') or {}
        args = state.get('input') or {}
        output = state.get('output')
        if (part.get('type') != 'tool' or state.get('status') != 'completed'
                or state.get('error') or not isinstance(args, dict) or not isinstance(output, str)):
            continue
        if part.get('tool') == 'read' and args.get('filePath', args.get('path')) == '/source-evidence/RESULTS.json' and output:
            read = True
        if (part.get('tool') == 'shell' and args.get('command') == 'sha256sum /source-evidence/RESULTS.json'
                and output.strip() == digest + '  /source-evidence/RESULTS.json'):
            hashed = True
    return read and hashed


def _source_output_summary(before: dict[str, str], after: dict[str, str]) -> dict:
    return {'file_count': len(after),
            'changed_files': {name: digest for name, digest in after.items()
                              if before.get(name) != digest},
            'missing_files': sorted(set(before) - set(after))}


def _publish_source_manifest(path: Path, manifest: dict[str, str], public_bytes) -> str:
    data = (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode()
    if public_bytes(data) != data:
        _fail('source_review_evidence_unsafe_or_oversize')
    _write_json(path, manifest, once=True)
    path.chmod(0o444)
    digest = _sha(path)
    if digest != hashlib.sha256(data).hexdigest():
        _fail('source_review_output_changed')
    return digest


def _source_review(root: Path, packet: Path, pin: dict, role: str, module) -> dict:
    plan = _verified_plan(root)
    _verify_inventory(root / role / 'project', plan['source_sha256'])
    destination = _controls(root) / ('source-review-' + role)
    destination.mkdir(mode=0o700)
    receipt_path = _controls(root) / ('review-' + role + '.json')
    result = {'kind': 'native-source-review-v1', 'status': 'unfinished',
              'assessment': {'status': 'unfinished'}, 'input_id': pin['input_id'],
              'reviewer_role': role, 'plan_sha256': _sha(root / 'plan.json'),
              'packet_pin': pin, 'filing_or_escalation_authorized': False}
    _write_json(receipt_path, result, once=True)
    prompt = (packet / 'PROMPT.txt').read_text()
    begin = prompt.index('Read /workspace/project/target.json')
    end = prompt.index('Examine each proposed', begin)
    prompt = prompt[:begin] + (
        'This is source review. Read /workspace/SOURCE.json. The project is a clean copy of the '
        'original source. Add scripts without changing or deleting any original file. '
        'Write /workspace/source-check.json with exactly kind="native-source-check-v1", '
        'input_id from REQUEST.json, effect (argv array), control (different argv array), '
        'and rationale (why this control tests the causal claim). Both commands must terminate. '
        'The host will freeze your scripts and run each command on three clean offline copies. '
        'Do not modify original files during execution. The host compares original file bytes '
        'before and after each command; this does not rule out temporary changes. ' +
        ('Use /deps' if 'checked_setup' in plan else 'Use /modules') +
        ' for prepared dependencies. Return decision unfinished until you have read '
        'the host results. Do not treat your workspace output as host evidence.\n') + prompt[end:]

    def invoke_initial(run_root, reviewer_role, session, unused_prompt, **kwargs):
        return invoke_native(run_root, reviewer_role, session, prompt, **kwargs)

    first = module.invoke_fresh_review(root, packet, pin, role, native_api=native_api,
        invoke_native=invoke_initial, allowance_snapshot=allowance_snapshot, run_active=run_active,
        public_bytes=module.validate_public_bytes, independent_check=None)
    result['preparation'] = first
    _write_json(receipt_path, result)
    if first['status'] != 'native_turn_observed_unassessed':
        return result
    with _turn_lock(root):
        if not run_active(root) or _unresolved_dispatches(root):
            _fail('source_review_unavailable')
        inventory = _freeze_source_input(root, destination / 'input', role)
        _verify_source_original(plan['source_sha256'], inventory)
        check = _validate_source_check(_read_json(destination / 'source-check.json'), pin['input_id'])
        _write_json(destination / 'input-manifest.json', inventory, once=True)
    evidence = {'kind': 'native-source-review-evidence-v1', 'input_id': pin['input_id'],
                'plan_sha256': result['plan_sha256'], 'check': check,
                'check_sha256': _sha(destination / 'source-check.json'),
                'input_manifest_sha256': _sha(destination / 'input-manifest.json'),
                'preparation_dispatch_id': first['native']['dispatch_id'], 'cases': {}}
    execution_paths = {}
    manifest_paths = {}
    evidence_dir = _controls(root) / 'source-evidence' / role
    for name in ('effect', 'control'):
        command = destination / (name + '.json')
        _write_json(command, check[name], once=True)
        executed = source_execute(root, command, source_snapshot=destination / 'input', owner_role=role)
        path = Path(executed['receipt_path'])
        execution_paths[name] = path
        captured = _read_json(path)
        if (executed['status'] != 'captured' or _sha(path) != executed['receipt_sha256']
                or captured['input_manifest_sha256'] != evidence['input_manifest_sha256']
                or captured['plan_sha256'] != result['plan_sha256'] or captured['owner_role'] != role
                or captured['command'] != check[name]
                or not isinstance(captured['runs'], list) or len(captured['runs']) != 3
                or any(not isinstance(row, dict) for row in captured['runs'])
                or {row.get('role') for row in captured['runs']} != set(CAPTURE_TARGETS)):
            _fail('source_review_execution_binding_changed')
        outputs = {}
        for row in captured['runs']:
            folder = path.parent / row['role']
            output_inventory = _read_json(folder / 'files.json')
            if _sha(folder / 'files.json') != row['output_manifest_sha256']:
                _fail('source_review_output_changed')
            _verify_inventory(folder / 'files', output_inventory)
            manifest_path = evidence_dir / ('manifest-' + name + '-' + row['role'] + '.json')
            manifest_digest = _publish_source_manifest(manifest_path, output_inventory,
                                                       module.validate_public_bytes)
            if manifest_digest != row['output_manifest_sha256']:
                _fail('source_review_output_changed')
            manifest_paths[manifest_path] = manifest_digest
            outputs[row['role']] = {**_source_output_summary(inventory, output_inventory),
                                    'manifest_path': '/source-evidence/' + manifest_path.name,
                                    'manifest_sha256': manifest_digest}
            for stream in ('stdout', 'stderr'):
                output = folder / (stream + '.txt')
                if row.get(stream + '_redacted') or not output.exists():
                    _fail('source_review_output_redacted')
                if _sha(output) != row[stream + '_sha256']:
                    _fail('source_review_output_changed')
                outputs[row['role']][stream] = output.read_text()
        evidence['cases'][name] = {'receipt': captured, 'receipt_sha256': executed['receipt_sha256'],
                                   'outputs': outputs}
    evidence_path = _controls(root) / 'source-evidence' / role / 'RESULTS.json'
    public = (json.dumps(evidence, sort_keys=True, indent=2) + '\n').encode()
    if len(public) > 1024 * 1024 or module.validate_public_bytes(public) != public:
        _fail('source_review_evidence_unsafe_or_oversize')
    _write_json(evidence_path, evidence, once=True)
    evidence_path.chmod(0o444)
    evidence_digest = _sha(evidence_path)
    before = allowance_snapshot(root)
    final = invoke_native(root, role, first['session_id'],
        'Read /handoff/REQUEST.json and every listed file again. Read '
        '/source-evidence/RESULTS.json with the read tool, then run exactly '
        '`sha256sum /source-evidence/RESULTS.json` with the shell tool. '
        'Full output manifests are at the read-only paths listed in RESULTS; inspect them '
        'when assessing a changed or missing file. '
        'Compare the host effect and control results and the three replays. Nonzero exits are '
        'observations, not proof of a security defect. Explain limitations and any weak control. '
        'Return the same review JSON schema required by /handoff/PROMPT.txt. '
        'Include source-evidence-sha256:' + evidence_digest + ' in checked_link. '
        'The executed scripts were yours; execution was by the host. No filing is authorized.', include_raw=True)
    raw = final.pop('_raw_stdout', '')
    after = allowance_snapshot(root)
    stable = (run_active(root) and module._same_allowance(first['allowance_before'], before)
              and module._same_allowance(before, after) and module.verify_packet(packet, pin)
              and _sha(evidence_path) == evidence_digest
              and all(_sha(path) == digest for path, digest in manifest_paths.items())
              and _sha(root / 'plan.json') == result['plan_sha256'])
    _verify_inventory(root / 'original', plan['source_sha256'])
    _verify_inventory(destination / 'input', inventory)
    if (_sha(destination / 'source-check.json') != evidence['check_sha256']
            or any(_sha(path) != evidence['cases'][name]['receipt_sha256']
                   for name, path in execution_paths.items())):
        _fail('source_review_evidence_changed')
    invocation = {'status': 'native_turn_observed_unassessed' if stable and final['status'] == 'acknowledged' else 'unfinished',
                  'session_id': first['session_id'], 'reviewer_role': role, 'native': final}
    material = module.project_review_material(root, packet, pin, invocation, raw,
                                             public_bytes=module.validate_public_bytes)
    result.update({'final': final, 'material': material, 'same_original_allowance': stable,
                   'evidence_sha256': evidence_digest, 'evidence_path': str(evidence_path)})
    if (material.get('status') == 'captured' and _source_evidence_read(raw, first['session_id'], evidence_digest)
            and 'source-evidence-sha256:' + evidence_digest in material['outcome']['checked_link']):
        result['status'] = 'reviewed'
        result['assessment'] = {'status': 'candidate_for_operator_review',
                                'decision': material['outcome']['decision'],
                                'input_id': pin['input_id'], 'outcome': material['outcome'],
                                'evidence_sha256': evidence_digest,
                                'execution_origin': 'host_executed_reviewer_scripts',
                                'filing_or_escalation_authorized': False}
    _write_json(receipt_path, result)
    return result


def review(run_root: Path, observer_root: Path, selection: Path,
           selection_sha256: str, role: str) -> dict:
    root = _private_root(Path(run_root))
    _verified_plan(root)
    if role not in ('reviewer-1', 'reviewer-2') or not HEX_RE.fullmatch(selection_sha256):
        _fail('review_input_invalid')
    if not run_active(root) or _unresolved_dispatches(root):
        _fail('review_run_closed_or_uncertain')
    module = _load_review_module(root)
    packet_dir = root / 'handoff' / role
    pin = module.prepare_packet(observer_root, selection, selection_sha256, packet_dir,
                                public_bytes=module.validate_public_bytes)
    if 'source_only' in _plan(root):
        receipt = _source_review(root, packet_dir, pin, role, module)
        return {'status': receipt['status'], 'assessment': receipt['assessment'],
                'reviewer_role': role, 'receipt_path': str(_controls(root) / ('review-' + role + '.json')),
                'independent_host_check': 'source_effect_and_control' if receipt['status'] == 'reviewed' else 'unfinished'}
    receipt = module.invoke_fresh_review(root, packet_dir, pin, role,
                                         native_api=native_api, invoke_native=invoke_native,
                                         allowance_snapshot=allowance_snapshot,
                                         run_active=run_active,
                                         public_bytes=module.validate_public_bytes,
                                         independent_check=None)
    _write_json(_controls(root) / ('review-' + role + '.json'), receipt, once=True)
    return {'status': receipt['status'], 'assessment': receipt['assessment'],
            'reviewer_role': role, 'receipt_path': str(_controls(root) / ('review-' + role + '.json')),
            'same_original_allowance': receipt['same_original_allowance'],
            'independent_host_check': 'unavailable'}


def _poststop_review_disposition(*, role: str, dispatch_id: str, effect_dispatch_id: str,
                                 effect_request_id: str, review_effect_request_id: str,
                                 review: dict, material: dict,
                                 request: dict, trace: dict, reviewer_origin: dict,
                                 semantic: dict | None, review_semantic: dict | None,
                                 effect_origins: dict) -> dict:
    """Compose semantic controls with exact reviewer and effect process origins."""
    hold = lambda reason: {'status': 'held', 'reason': reason}
    if (role not in ('reviewer-1', 'reviewer-2')
            or not re.fullmatch(r'[0-9a-f]{32}', str(dispatch_id))
            or not re.fullmatch(r'[0-9a-f]{32}', str(effect_dispatch_id))
            or not re.fullmatch(r'[0-9a-f]{32}', str(effect_request_id))
            or not re.fullmatch(r'[0-9a-f]{32}', str(review_effect_request_id))
            or dispatch_id == effect_dispatch_id):
        return hold('poststop_review_identity_invalid')
    if not isinstance(review, dict):
        return hold('poststop_review_receipt_invalid')
    native = review.get('native')
    if (review.get('status') != 'native_turn_observed_unassessed'
            or review.get('reviewer_role') != role
            or not isinstance(native, dict) or native.get('dispatch_id') != dispatch_id
            or native.get('role') != role or native.get('session_id') != review.get('session_id')
            or review.get('same_original_allowance') is not True):
        return hold('poststop_review_receipt_invalid')
    if (not isinstance(request, dict) or not isinstance(material, dict)
            or material.get('kind') != 'native-review-material-v1'
            or material.get('status') != 'captured'
            or material.get('dispatch_id') != dispatch_id
            or material.get('session_id') != review.get('session_id')
            or material.get('input_id') != request.get('input_id')
            or material.get('packet_request_sha256') != review.get('packet_request_sha256')
            or request.get('source_manifest_sha256') != native.get('review_target_source_sha256')
            or not HEX_RE.fullmatch(str(material.get('packet_request_sha256', '')))
            or not HEX_RE.fullmatch(str(request.get('selection_sha256', '')))):
        return hold('poststop_review_material_binding_invalid')
    if (not isinstance(trace, dict) or trace.get('kind') != 'protected-native-event-trace-v1'
            or trace.get('session_id') != review.get('session_id')
            or native.get('native_trace_sha256') != material.get('native_trace_sha256')
            or not isinstance(material.get('shell_actions'), list)
            or not material['shell_actions']):
        return hold('poststop_review_trace_binding_invalid')
    if (not isinstance(reviewer_origin, dict)
            or reviewer_origin.get('kind') != 'native-origin-transport-proof-v1'
            or reviewer_origin.get('status') != 'process_request_attributed'
            or reviewer_origin.get('dispatch_id') != dispatch_id
            or reviewer_origin.get('role') != role
            or reviewer_origin.get('target') != 'review-target-' + role[-1]
            or reviewer_origin.get('native_trace_sha256') != material.get('native_trace_sha256')
            or reviewer_origin.get('source_manifest_sha256') != request.get('source_manifest_sha256')):
        return hold('poststop_reviewer_origin_unavailable')
    events = {row.get('line'): row for row in trace.get('events', []) if isinstance(row, dict)}
    claims = reviewer_origin.get('native_tool_claims')
    if not isinstance(claims, list) or not isinstance(reviewer_origin.get('broker_request_ids'), list):
        return hold('poststop_reviewer_origin_claims_invalid')
    claimed_ids = []
    claimed_action_lines = set()
    claim_lines_by_id = {}
    for claim in claims:
        if not isinstance(claim, dict) or not isinstance(claim.get('request_ids'), list):
            return hold('poststop_reviewer_origin_claims_invalid')
        line = claim.get('line')
        event = events.get(line)
        ids = claim['request_ids']
        if (not isinstance(line, int) or isinstance(line, bool) or not ids
                or not isinstance(event, dict) or claim.get('tool') != 'shell'
                or event.get('part_type') != 'tool' or event.get('tool') != 'shell'
                or event.get('status') != 'completed'
                or event.get('session_matches') is not True
                or claim.get('input_sha256') != event.get('input_sha256')
                or claim.get('output_sha256') != event.get('output_sha256')
                or any(not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{32}', value) for value in ids)):
            return hold('poststop_reviewer_origin_claims_invalid')
        claimed_ids.extend(ids)
        claimed_action_lines.add(line)
        for request_id in ids:
            claim_lines_by_id[request_id] = line
    if (len(claimed_ids) != len(set(claimed_ids))
            or set(claimed_ids) != set(reviewer_origin['broker_request_ids'])):
        return hold('poststop_reviewer_origin_ids_disagree')
    action_lines = set()
    for action in material['shell_actions']:
        if (not isinstance(action, dict) or type(action.get('line')) is not int
                or not all(HEX_RE.fullmatch(str(action.get(key, ''))) for key in
                           ('command_sha256', 'input_sha256', 'output_sha256'))):
            return hold('poststop_review_action_invalid')
        action_lines.add(action['line'])
    if not action_lines.intersection(claimed_action_lines):
        return hold('poststop_reviewer_action_not_attributed')
    if (not isinstance(review_semantic, dict)
            or review_semantic.get('status') != 'effect_and_controls_observed'
            or review_semantic.get('scope') != 't01_original_vulnerable_arm'
            or review_semantic.get('effect_dispatch_id') != dispatch_id
            or review_semantic.get('effect_request_id') != review_effect_request_id
            or review_semantic.get('target') != 'review-target-' + role[-1]):
        reason = review_semantic.get('reason') if isinstance(review_semantic, dict) else None
        if isinstance(reason, str) and re.fullmatch(r'[a-z][a-z0-9_]{0,100}', reason):
            return hold('poststop_reviewer_' + reason)
        return hold('poststop_reviewer_semantic_unavailable_or_mismatched')
    review_creation = review_semantic.get('creation_request_ids')
    review_ordinary = review_semantic.get('ordinary_request_ids')
    review_denial = review_semantic.get('denial_request_id')
    if (not isinstance(review_creation, list) or len(review_creation) != 2
            or not isinstance(review_ordinary, list) or len(review_ordinary) != 2
            or not isinstance(review_denial, str)
            or any(not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{32}', value)
                   for value in [*review_creation, *review_ordinary, review_denial,
                                 review_effect_request_id])):
        return hold('poststop_reviewer_semantic_request_set_invalid')
    reviewer_decisive = [*review_creation, *review_ordinary, review_denial,
                         review_effect_request_id]
    if (len(reviewer_decisive) != len(set(reviewer_decisive))
            or any(reviewer_origin['broker_request_ids'].count(request_id) != 1
                   or claim_lines_by_id.get(request_id) not in action_lines
                   for request_id in reviewer_decisive)):
        return hold('poststop_reviewer_semantic_origin_missing_or_ambiguous')
    if (not isinstance(semantic, dict)
            or semantic.get('status') != 'effect_and_controls_observed'
            or semantic.get('scope') != 't01_original_vulnerable_arm'
            or semantic.get('effect_dispatch_id') != effect_dispatch_id
            or semantic.get('effect_request_id') != effect_request_id):
        reason = semantic.get('reason') if isinstance(semantic, dict) else None
        if isinstance(reason, str) and re.fullmatch(r'[a-z][a-z0-9_]{0,100}', reason):
            return hold('poststop_' + reason)
        return hold('poststop_semantic_verifier_unavailable_or_mismatched')
    creation = semantic.get('creation_request_ids')
    ordinary = semantic.get('ordinary_request_ids')
    denial = semantic.get('denial_request_id')
    if (not isinstance(creation, list) or len(creation) != 2
            or not isinstance(ordinary, list) or len(ordinary) != 2
            or not isinstance(denial, str)
            or any(not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{32}', value)
                   for value in [*creation, *ordinary, denial, effect_request_id])):
        return hold('poststop_semantic_request_set_invalid')
    decisive = [*creation, *ordinary, denial, effect_request_id]
    if len(decisive) != len(set(decisive)):
        return hold('poststop_semantic_request_set_invalid')
    if not isinstance(effect_origins, dict):
        return hold('poststop_effect_origin_unavailable')
    seen = {request_id: 0 for request_id in decisive}
    proof_hashes = {}
    for origin_dispatch, proof in effect_origins.items():
        if (not isinstance(proof, dict) or proof.get('kind') != 'native-origin-transport-proof-v1'
                or proof.get('status') != 'process_request_attributed'
                or proof.get('dispatch_id') != origin_dispatch
                or proof.get('role') not in ('researcher', 'resume')
                or proof.get('target') != 'target'
                or not isinstance(proof.get('broker_request_ids'), list)):
            continue
        ids = proof['broker_request_ids']
        if any(not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{32}', value) for value in ids):
            return hold('poststop_effect_origin_invalid')
        for request_id in decisive:
            if request_id in ids:
                seen[request_id] += 1
                proof_hashes[origin_dispatch] = hashlib.sha256(
                    (json.dumps(proof, sort_keys=True, separators=(',', ':'), allow_nan=False)).encode()
                ).hexdigest()
    if any(count != 1 for count in seen.values()):
        return hold('poststop_decisive_origin_missing_or_ambiguous')
    effect_proof = effect_origins.get(effect_dispatch_id)
    if (not isinstance(effect_proof, dict) or effect_proof.get('dispatch_id') != effect_dispatch_id
            or effect_proof.get('kind') != 'native-origin-transport-proof-v1'
            or effect_proof.get('status') != 'process_request_attributed'
            or effect_proof.get('role') not in ('researcher', 'resume')
            or effect_proof.get('target') != 'target'
            or not isinstance(effect_proof.get('broker_request_ids'), list)
            or effect_request_id not in effect_proof['broker_request_ids']):
        return hold('poststop_effect_origin_dispatch_mismatch')
    return {'status': 'candidate_for_operator_review', 'scope': semantic['scope'],
            'reviewer_role': role, 'review_dispatch_id': dispatch_id,
            'effect_dispatch_id': effect_dispatch_id, 'effect_request_id': effect_request_id,
            'review_effect_request_id': review_effect_request_id,
            'reviewer_material_check': 't01_effect_and_controls_observed',
            'reviewer_decisive_request_ids': sorted(reviewer_decisive),
            'qualification': 'partial', 'clean_replay': 'not_assessed',
            'fixed_control': 'not_assessed', 'lead_dispositions': 'unfinished_unassessed',
            'limits': ['does not establish full #159 qualification',
                       'does not independently assess strong-lead dismissal',
                       'model lead_dispositions remain untrusted review material'],
            'selection_sha256': request['selection_sha256'],
            'decisive_request_ids': sorted(decisive),
            'reviewer_action_lines': sorted(action_lines.intersection(claimed_action_lines)),
            'effect_origin_proof_sha256': proof_hashes}


def assess_poststop_review(run_root: Path, role: str, dispatch_id: str,
                           effect_dispatch_id: str, effect_request_id: str,
                           review_effect_request_id: str) -> dict:
    """Write one immutable assessment after exact native stop and origin reconciliation."""
    held = {'status': 'held', 'reviewer_role': role, 'review_dispatch_id': dispatch_id,
            'effect_dispatch_id': effect_dispatch_id, 'effect_request_id': effect_request_id,
            'review_effect_request_id': review_effect_request_id}
    freeze = None
    if (role not in ('reviewer-1', 'reviewer-2')
            or any(not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{32}', value)
                   for value in (dispatch_id, effect_dispatch_id, effect_request_id,
                                 review_effect_request_id))):
        return dict(held, reason='poststop_review_identity_invalid')
    try:
        root = _private_root(Path(run_root))
        semantic_fn = globals().get('reconcile_t01_semantic')
        semantic = semantic_fn(root, effect_dispatch_id, effect_request_id) if callable(semantic_fn) else None
        review_semantic = (semantic_fn(root, dispatch_id, review_effect_request_id)
                           if callable(semantic_fn) else None)
        with _owner_lock(root):
            plan = _verified_plan(root)
            controls = _controls(root)
            final_path, recovery_path = controls / 'final.json', controls / 'recovery.json'
            if final_path.exists():
                terminal = _read_json(final_path)
                stopped = terminal.get('status') == 'stopped_complete'
            elif recovery_path.exists():
                terminal = _read_json(recovery_path)
                stopped = (terminal.get('status') == 'recovered_exact_resources'
                           and terminal.get('native_state') == 'stopped')
            else:
                stopped = False
                terminal = {}
            if (not stopped or terminal.get('host_snapshot', {}).get('status') != 'complete'
                    or terminal.get('capture_stop', {}).get('status') != 'complete'
                    or terminal.get('capture_cleanup', {}).get('status') != 'complete'
                    or terminal.get('cleanup', {}).get('status') != 'complete'
                    or terminal.get('origin_stop', {}).get('status') != 'complete'
                    or terminal.get('origin_cleanup', {}).get('status') != 'complete'
                    or _unresolved_dispatches(root)):
                return dict(held, reason='poststop_run_not_fully_stopped')
            destination = controls / ('poststop-review-' + role + '.json')

            def freeze(value):
                if destination.exists():
                    existing = _read_json(destination)
                    return existing if existing == value else dict(
                        held, reason='poststop_assessment_already_frozen')
                _write_json(destination, value, once=True)
                return value

            if not _origin_enabled(plan) or 't01_capture' not in plan:
                return freeze(dict(held, reason='poststop_semantic_verifier_unavailable_for_profile'))
            dispatch_path = controls / 'dispatch' / (dispatch_id + '.json')
            dispatch = _read_json(dispatch_path)
            if (dispatch.get('kind') != 'native-dispatch-v1'
                    or dispatch.get('status') != 'acknowledged'
                    or dispatch.get('dispatch_id') != dispatch_id or dispatch.get('role') != role):
                return freeze(dict(held, reason='poststop_reviewer_dispatch_invalid'))
            receipt_path = controls / ('review-' + role + '.json')
            receipt = _read_json(receipt_path)
            material = receipt.get('material')
            receipt_native = receipt.get('native')
            if (receipt.get('reviewer_role') != role or not isinstance(receipt_native, dict)
                    or receipt_native.get('dispatch_id') != dispatch_id
                    or receipt_native.get('native_trace_sha256') != dispatch.get('native_trace_sha256')):
                return freeze(dict(held, reason='poststop_review_receipt_changed'))
            packet_dir = root / 'handoff' / role
            module = _load_review_module(root)
            pin = material.get('packet_pin') if isinstance(material, dict) else None
            if (not isinstance(pin, dict) or not module.verify_packet(packet_dir, pin)
                    or not isinstance(pin.get('files'), dict)
                    or pin['files'].get('REQUEST.json') != material.get('packet_request_sha256')):
                return freeze(dict(held, reason='poststop_review_packet_changed'))
            request_path = packet_dir / 'REQUEST.json'
            request = _read_json(request_path)
            module.validate_public_bytes(request_path.read_bytes())
            module.validate_public_bytes(json.dumps(material, sort_keys=True,
                                                     allow_nan=False).encode())
            selection = {key: request.get(key) for key in
                         ('claim_id', 'claim_version', 'source_manifest_sha256',
                          'source_paths', 'roles', 'files')}
            selected_id = hashlib.sha256((json.dumps(selection, indent=2, sort_keys=True,
                                                       allow_nan=False) + '\n').encode()).hexdigest()
            if (request.get('input_id') != selected_id
                    or request.get('source_manifest_sha256') != plan.get('source_manifest_sha256')
                    or receipt.get('input_id') != selected_id
                    or material.get('input_id') != selected_id
                    or material.get('packet_request_sha256') != _sha(request_path)
                    or request.get('source_revision') != hashlib.sha256((json.dumps({
                        'source': {request['source_paths'][name]: request['files'][name]
                                   for name in request['roles']['source']},
                        'conditions': {name: request['files'][name]
                                       for name in request['roles']['conditions']}
                    }, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()).hexdigest()
                    or request.get('evidence_revision') != hashlib.sha256((json.dumps({
                        name: request['files'][name] for role_name in
                        ('claim', 'raw', 'contrary', 'unfinished')
                        for name in request['roles'][role_name]
                    }, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()).hexdigest()):
                return freeze(dict(held, reason='poststop_review_selection_or_source_changed'))
            _verify_inventory(root / 'original', plan['source_sha256'])
            for name in request['roles']['source']:
                source_path = request['source_paths'][name]
                if (not _valid_relative_path(source_path)
                        or plan['source_sha256'].get(source_path) != request['files'].get(name)
                        or _sha(root / 'original' / source_path) != request['files'][name]):
                    return freeze(dict(held, reason='poststop_review_source_bytes_changed'))
            trace_path = controls / 'dispatch' / (dispatch_id + '.trace.json')
            trace = _read_json(trace_path)
            if (_sha(trace_path) != material.get('native_trace_sha256')
                    or dispatch.get('native_trace_sha256') != _sha(trace_path)):
                return freeze(dict(held, reason='poststop_review_trace_changed'))
            reviewer_origin = _origin_transport_proof(root, dispatch_id)
            effect_origins = {}
            for path in sorted((controls / 'dispatch').glob('*.json')):
                if path.name.endswith(('.trace.json', '.pre.json', '.origin.json')):
                    continue
                try:
                    row = _read_json(path)
                    if row.get('role') in ('researcher', 'resume') and row.get('status') == 'acknowledged':
                        proof = _origin_transport_proof(root, row['dispatch_id'])
                        effect_origins[row['dispatch_id']] = proof
                except (NativeResearchError, OSError, ValueError, KeyError, TypeError,
                        sqlite3.DatabaseError):
                    continue
            result = _poststop_review_disposition(
                role=role, dispatch_id=dispatch_id, effect_dispatch_id=effect_dispatch_id,
                effect_request_id=effect_request_id,
                review_effect_request_id=review_effect_request_id,
                review=receipt, material=material,
                request=request, trace=trace, reviewer_origin=reviewer_origin,
                semantic=semantic, review_semantic=review_semantic,
                effect_origins=effect_origins)
            result.update({'review_receipt_sha256': _sha(receipt_path),
                           'review_packet_request_sha256': _sha(request_path),
                           'review_trace_sha256': _sha(trace_path),
                           'semantic_receipt_sha256': hashlib.sha256(json.dumps(
                               semantic, sort_keys=True, separators=(',', ':'),
                               allow_nan=False).encode()).hexdigest(),
                           'review_semantic_receipt_sha256': hashlib.sha256(json.dumps(
                               review_semantic, sort_keys=True, separators=(',', ':'),
                               allow_nan=False).encode()).hexdigest(),
                           'reviewer_origin_proof_sha256': hashlib.sha256(json.dumps(
                               reviewer_origin, sort_keys=True, separators=(',', ':'),
                               allow_nan=False).encode()).hexdigest()})
            return freeze(result)
    except (NativeResearchError, OSError, ValueError, KeyError, TypeError,
            sqlite3.DatabaseError) as error:
        reason = str(error) if isinstance(error, NativeResearchError) else 'poststop_assessment_unavailable'
        value = dict(held, reason=reason)
        return freeze(value) if callable(freeze) else value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare_cmd = commands.add_parser('prepare', help='provider-free sealed run preparation')
    for name in ('run-root', 'source', 'brief', 'scope-file', 'scope-sha256', 'relay',
                 'relay-sha256', 'runtime-ca', 'runtime-ca-sha256',
                 'image-id', 'platform'):
        prepare_cmd.add_argument('--' + name, required=True)
    prepare_cmd.add_argument('--target-image-id')
    prepare_cmd.add_argument('--target-port', type=int)
    prepare_cmd.add_argument('--target-command')
    prepare_cmd.add_argument('--source-only', action='store_true')
    prepare_cmd.add_argument('--setup-only', action='store_true',
                             help='bounded pre-runtime source setup; no target executor')
    prepare_cmd.add_argument('--setup-engagement-id')
    prepare_cmd.add_argument('--setup-operator-id')
    prepare_cmd.add_argument('--setup-scope-signature')
    prepare_cmd.add_argument('--setup-allowed-signers')
    prepare_cmd.add_argument('--setup-trusted-fingerprint')
    prepare_cmd.add_argument('--setup-max-workspace-bytes', type=int, default=64 * 1024 * 1024)
    prepare_cmd.add_argument('--source-runtime', help='runtime probe JSON; replaces the optional Go preset')
    prepare_cmd.add_argument('--build-command', help='absolute path to a JSON argv array')
    prepare_cmd.add_argument('--go-toolchain', help='exact Go version, for example go1.26.4')
    prepare_cmd.add_argument('--module-cache', help='prepared offline module closure; never fetched here')
    prepare_cmd.add_argument('--kanboard-capture', action='store_true')
    prepare_cmd.add_argument('--t01-capture', action='store_true')
    prepare_cmd.add_argument('--origin-ingress', action='store_true',
                             help='opt-in source-built process-bound Unix ingress for capture')
    prepare_cmd.add_argument('--mutable-path', action='append', default=[])
    prepare_cmd.add_argument('--expected-skill-id', action='append', default=[])
    prepare_cmd.add_argument('--model', default=MODEL)
    prepare_cmd.add_argument('--provider-route', default=PROVIDER_ROUTE)
    prepare_cmd.add_argument('--provider-authority', default=AUTHORITY)
    prepare_cmd.add_argument('--max-connections', type=int, default=DEFAULT_LIMITS['max_connections'])
    prepare_cmd.add_argument('--max-bytes', type=int, default=DEFAULT_LIMITS['max_bytes'])
    prepare_cmd.add_argument('--duration-seconds', type=int, default=DEFAULT_LIMITS['duration_seconds'])
    checked_cmd = commands.add_parser('prepare-checked',
                                      help='seal source-only research from a host-checked setup package')
    for name in ('run-root', 'checked-setup-root', 'scope-file', 'scope-sha256'):
        checked_cmd.add_argument('--' + name, required=True)
    checked_cmd.add_argument('--max-connections', type=int, required=True)
    checked_cmd.add_argument('--max-bytes', type=int, required=True)
    checked_cmd.add_argument('--duration-seconds', type=int, required=True)
    start_cmd = commands.add_parser('start', help='foreground live owner; requires fresh plan-bound approval')
    start_cmd.add_argument('--run-root', required=True)
    start_cmd.add_argument('--approval', required=True)
    start_cmd.add_argument('--provider-key-file', help='private external host file; never copied into the run')
    start_cmd.add_argument('--provider-tls-key', help='private external key for the pinned runtime CA certificate')
    setup_turn_cmd = commands.add_parser('setup-turn', help='one bounded native source setup turn')
    setup_turn_cmd.add_argument('--run-root', required=True)
    setup_resume_cmd = commands.add_parser('setup-resume', help='continue an acknowledged setup session')
    setup_resume_cmd.add_argument('--run-root', required=True)
    setup_resume_cmd.add_argument('--session', required=True)
    setup_resume_cmd.add_argument('--prompt-file', required=True)
    setup_freeze_cmd = commands.add_parser('setup-freeze', help='freeze recipe and threat model for host review')
    setup_freeze_cmd.add_argument('--run-root', required=True)
    setup_template_cmd = commands.add_parser('setup-approval-template',
                                             help='provider-free exact unsigned setup approval')
    setup_template_cmd.add_argument('--run-root', required=True)
    setup_template_cmd.add_argument('--approved-at', required=True)
    setup_template_cmd.add_argument('--expires-at', required=True)
    setup_template_cmd.add_argument('--linked-epochs', action='store_true')
    setup_template_cmd.add_argument('--absolute-deadline')
    setup_next_cmd = commands.add_parser('setup-next-epoch',
                                         help='prepare one residual setup run after verified owner loss')
    setup_next_cmd.add_argument('--run-root', required=True)
    setup_next_cmd.add_argument('--next-run-root', required=True)
    setup_chain_cmd = commands.add_parser('setup-chain',
                                          help='read-only verified cumulative v2 setup authority and usage')
    setup_chain_cmd.add_argument('--run-root', required=True)
    setup_manifest_cmd = commands.add_parser('setup-source-manifest',
                                             help='provider-free regular-file source identity before scope signing')
    setup_manifest_cmd.add_argument('--source', required=True)
    source_cmd = commands.add_parser('source-execute', help='offline source execution and two clean replays')
    source_cmd.add_argument('--run-root', required=True)
    source_cmd.add_argument('--command-file', help='optional experiment argv; default is the pinned build command')
    stage_cmd = commands.add_parser('capture-stage', help='provider-free Kanboard observer staging')
    stage_cmd.add_argument('--run-root', required=True)
    stage_cmd.add_argument('--target', choices=CAPTURE_TARGETS, required=True)
    for name in ('s', 'q', 't', 'b'):
        stage_cmd.add_argument('--' + name, type=int)
    for name in ('status', 'stop', 'recover-start'):
        item = commands.add_parser(name)
        item.add_argument('--run-root', required=True)
    reconcile_cmd = commands.add_parser('reconcile-role-grant', help='post-stop S10 uncertain-effect observation')
    reconcile_cmd.add_argument('--run-root', required=True)
    reconcile_cmd.add_argument('--dispatch-id', required=True)
    origin_cmd = commands.add_parser('reconcile-origin-transport',
                                     help='post-stop native process/request/app transport join')
    origin_cmd.add_argument('--run-root', required=True)
    origin_cmd.add_argument('--dispatch-id', required=True)
    t01_cmd = commands.add_parser('reconcile-t01-semantic',
                                  help='read-only post-stop T01 effect/control assessment')
    t01_cmd.add_argument('--run-root', required=True)
    t01_cmd.add_argument('--dispatch-id', required=True)
    t01_cmd.add_argument('--effect-request-id', required=True)
    poststop_cmd = commands.add_parser('assess-poststop-review',
                                       help='bind a stopped native review to semantic and origin evidence')
    poststop_cmd.add_argument('--run-root', required=True)
    poststop_cmd.add_argument('--role', choices=('reviewer-1', 'reviewer-2'), required=True)
    poststop_cmd.add_argument('--dispatch-id', required=True)
    poststop_cmd.add_argument('--effect-dispatch-id', required=True)
    poststop_cmd.add_argument('--effect-request-id', required=True)
    poststop_cmd.add_argument('--review-effect-request-id', required=True)
    research_cmd = commands.add_parser('research', help='one native turn in the original researcher')
    research_cmd.add_argument('--run-root', required=True)
    resume_cmd = commands.add_parser('resume', help='one native turn in the same persistent researcher store')
    resume_cmd.add_argument('--run-root', required=True)
    resume_cmd.add_argument('--prompt-file', required=True)
    resume_cmd.add_argument('--session', required=True)
    resume_cmd.add_argument('--observe-kanboard-role-grant', action='store_true')
    reconstruct_cmd = commands.add_parser('reconstruct', help='new context from ordinary files in the same active run')
    reconstruct_cmd.add_argument('--run-root', required=True)
    reconstruct_cmd.add_argument('--prompt-file')
    continue_cmd = commands.add_parser('continue', help='durable bounded continuation over one active run')
    continue_cmd.add_argument('--run-root', required=True)
    continue_cmd.add_argument('--max-invocations', type=int, default=24)
    continue_cmd.add_argument('--invocation-timeout', type=int, default=3700)
    continue_cmd.add_argument('--resume-after-stop', action='store_true')
    continue_cmd.add_argument('--reconcile-dispatch-id')
    continue_cmd.add_argument('--reconcile-decision', choices=('no_effect', 'effect_observed'))
    continue_cmd.add_argument('--reconcile-evidence')
    review_cmd = commands.add_parser('review', help='one fresh bounded reviewer on a frozen public packet')
    for name in ('run-root', 'observer-root', 'selection', 'selection-sha256'):
        review_cmd.add_argument('--' + name, required=True)
    review_cmd.add_argument('--role', choices=('reviewer-1', 'reviewer-2'), required=True)
    return parser


def main() -> int:
    os.umask(0o077)
    args = _parser().parse_args()
    try:
        if args.command == 'prepare':
            result = prepare(args)
        elif args.command == 'prepare-checked':
            result = prepare_checked(args)
        elif args.command == 'capture-stage':
            result = capture_stage(Path(args.run_root), args.target, s=args.s, q=args.q, t=args.t, b=args.b)
        elif args.command == 'start':
            result = start(Path(args.run_root), Path(args.approval),
                           provider_key_file=Path(args.provider_key_file) if args.provider_key_file else None,
                           provider_tls_key=Path(args.provider_tls_key) if args.provider_tls_key else None)
        elif args.command == 'source-execute':
            result = source_execute(Path(args.run_root), Path(args.command_file) if args.command_file else None)
        elif args.command in ('setup-turn', 'setup-resume'):
            root = _private_root(Path(args.run_root))
            if 'setup_only' not in _verified_plan(root):
                _fail('setup_mode_required')
            if args.command == 'setup-turn':
                sessions = native_api(root, 'researcher', 'session.list', '--param', 'limit=100',
                                      '--param', 'order=asc')
                if sessions.get('items', sessions.get('data')) != []:
                    _fail('setup_store_not_fresh')
                created = native_api(root, 'researcher', 'session.create', '--data',
                                     '{"title":"bounded source setup"}')
                session = (created.get('data') or {}).get('id')
                prompt = _file(_controls(root) / 'BRIEF.md', private=True).read_text()
                role = 'researcher'
            else:
                session = args.session
                if not SESSION_RE.fullmatch(session):
                    _fail('native_session_id_invalid')
                prompt = _file(Path(args.prompt_file), private=True).read_text()
                role = 'resume'
                existing = native_api(root, role, 'session.get', '--param', 'sessionID=' + session)
                if (existing.get('data') or {}).get('id') != session:
                    _fail('setup_resume_session_invalid')
            if not isinstance(session, str) or not SESSION_RE.fullmatch(session):
                _fail('native_session_id_invalid')
            result = invoke_native(root, role, session, prompt,
                                   continuity='fresh_setup' if role == 'researcher' else 'setup_resume')
        elif args.command == 'setup-freeze':
            result = setup_freeze(Path(args.run_root))
        elif args.command == 'setup-approval-template':
            result = setup_approval_template(Path(args.run_root), args.approved_at, args.expires_at,
                                             linked_epochs=args.linked_epochs,
                                             absolute_deadline=args.absolute_deadline)
        elif args.command == 'setup-next-epoch':
            result = setup_next_epoch(Path(args.run_root), Path(args.next_run_root))
        elif args.command == 'setup-chain':
            result = setup_chain_snapshot(Path(args.run_root))
        elif args.command == 'setup-source-manifest':
            result = setup_source_manifest(Path(args.source))
        elif args.command == 'stop':
            result = stop(Path(args.run_root))
        elif args.command == 'recover-start':
            result = recover_start(Path(args.run_root))
        elif args.command == 'status':
            result = status(Path(args.run_root))
        elif args.command == 'reconcile-role-grant':
            result = reconcile_role_grant(Path(args.run_root), args.dispatch_id)
        elif args.command == 'reconcile-origin-transport':
            result = reconcile_origin_transport(Path(args.run_root), args.dispatch_id)
        elif args.command == 'reconcile-t01-semantic':
            result = reconcile_t01_semantic(Path(args.run_root), args.dispatch_id,
                                            args.effect_request_id)
        elif args.command == 'assess-poststop-review':
            result = assess_poststop_review(Path(args.run_root), args.role, args.dispatch_id,
                                            args.effect_dispatch_id, args.effect_request_id,
                                            args.review_effect_request_id)
        elif args.command in ('research', 'resume', 'reconstruct'):
            root = Path(args.run_root)
            if 'setup_only' in _plan(_private_root(root)):
                _fail('setup_command_required')
            role = 'researcher' if args.command == 'research' else 'resume'
            continuity = {'research': 'fresh_research', 'resume': 'native_history',
                          'reconstruct': 'fresh_context_from_workspace'}[args.command]
            _research_context(_private_root(root), continuity)
            if args.command == 'research':
                prompt = _file(_controls(root) / 'BRIEF.md', private=True).read_text()
                sessions = native_api(root, role, 'session.list', '--param', 'limit=100',
                                      '--param', 'order=asc')
                if sessions.get('items', sessions.get('data')) != []:
                    _fail('researcher_store_not_fresh')
                created = native_api(root, role, 'session.create', '--data',
                                     '{"title":"native bounded research"}')
                session = (created.get('data') or {}).get('id')
            elif args.command == 'resume':
                prompt = _file(Path(args.prompt_file), private=True).read_text()
                session = args.session
            else:
                prompt = (_file(Path(args.prompt_file), private=True).read_text() if args.prompt_file else
                          'Reconstruct the investigation from saved research notes, scripts, results and current '
                          'run snapshot. Identify missing conditions before choosing the next authorized check.')
                prompt = ('Use ordinary workspace files without consulting prior native conversations. '
                          'A fresh session alone does not prove that reconstruction succeeded.\n' + prompt)
                created = native_api(root, role, 'session.create', '--data',
                                     '{"title":"workspace reconstruction"}')
                session = (created.get('data') or {}).get('id')
            if not isinstance(session, str) or not SESSION_RE.fullmatch(session):
                _fail('native_session_id_invalid')
            if args.command == 'resume':
                existing = native_api(root, role, 'session.get', '--param', 'sessionID=' + session)
                if (existing.get('data') or {}).get('id') != session:
                    _fail('resume_session_not_in_researcher_store')
            result = invoke_native(root, role, session, prompt,
                                   kanboard_role_grant=(args.observe_kanboard_role_grant
                                                        if args.command == 'resume' else False),
                                   continuity=continuity)
        elif args.command == 'continue':
            from native_continuation import continue_run, reconcile
            if args.reconcile_dispatch_id:
                if not args.reconcile_decision or not args.reconcile_evidence:
                    _fail('continuation_reconcile_input_missing')
                result = reconcile(Path(args.run_root),
                                   dispatch_id=args.reconcile_dispatch_id,
                                   decision=args.reconcile_decision,
                                   evidence_file=Path(args.reconcile_evidence))
            else:
                result = continue_run(Path(args.run_root), max_invocations=args.max_invocations,
                                      invocation_timeout=args.invocation_timeout,
                                      resume_after_stop=args.resume_after_stop)
        elif args.command == 'review':
            result = review(Path(args.run_root), Path(args.observer_root), Path(args.selection),
                            args.selection_sha256, args.role)
        else:
            _fail('command_invalid')
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0 if (result.get('status') not in ('unknown_effect', 'hold_unknown', 'held', 'unfinished', 'start_incomplete',
                                                'unsafe_or_unresolved', 'stopped_evidence_incomplete',
                                                'rejected', 'continuation_already_running', 'inactive',
                                                'invocation_failed', 'spend_unavailable',
                                                'closure_review_required', 'next_brief_missing',
                                                'reconciliation_required', 'previous_stop',
                                                'spend_reset_detected', 'effect_observed',
                                                'closeout_incomplete', 'result_invalid',
                                                'review_required', 'reopen_required',
                                                'cleanup_pending', 'cleanup_unverified',
                                                'stop_request_unknown', 'stopped_incomplete',
                                                'reopen_no_agent_revision')
                     and result.get('independent_host_check') != 'unavailable') else 2
    except KeyboardInterrupt:
        print(json.dumps({'status': 'interrupted', 'run_root': getattr(args, 'run_root', None)},
                         sort_keys=True))
        return 130
    except Exception as error:
        code = str(error)
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,100}', code):
            code = 'native_research_unavailable'
        terminal = 'rejected'
        if args.command == 'start':
            try:
                final = _read_json(Path(args.run_root) / 'controls/final.json')
                if final.get('status') == 'unsafe_or_unresolved':
                    terminal = 'unsafe_or_unresolved'
            except Exception:
                pass
        print(json.dumps({'status': terminal, 'code': code}, sort_keys=True))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
