#!/usr/bin/env python3
"""Qualify exact OpenCode control and candidate images with owned TLS chains.

This checker is dormant unless an operator supplies the exact confirmation token.
It never builds or pulls an image. The control is an exact unpatched OpenCode
v2.0.32 image. The candidate is a separate reviewed build whose native HTTP
request executor requires a fixed ``OPENCODE_EXCLUSIVE_CA_FILE`` plus its exact
``OPENCODE_EXCLUSIVE_CA_SHA256``. It passes the bounded, verified bytes as Bun
``fetch(..., {tls: {ca}})`` input. The three core arms prove the result.
Environment variable names alone do not.

The stable ``provider.list`` and ``model.list`` CLI/API reads must expose the
selected native package. The provider's effective settings must expose the owned
base URL and HTTP transport; the model's effective settings must expose the same
owned base URL without a transport override before every core dispatch.
``config.get`` must independently prove the exact
mounted source document. A candidate that omits those facts is blocked. The
checker does not infer effective settings from a config file or a successful
request. Each readback and run uses a separate CLI process in the same
container, but both clients use one loopback-only OpenCode server process. That
server owns the authoritative provider, model, and transport resolution. Normal
execution requires separate authorization before creating its per-container,
ephemeral control password. That value exists only in the bounded server/client
process environments; core dumps are disabled and successful exact container
removal destroys the process state.
"""

import argparse
import copy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import stat
import subprocess
import sys
import tempfile
import threading
import time
import uuid


CONFIRMATION = 'I_CONFIRM_OWNED_TLS_FIXTURE_ONLY'
CONTROL_CREDENTIAL_CONFIRMATION = 'I_CONFIRM_EPHEMERAL_LOOPBACK_CONTROL_CREDENTIAL'
LABEL = 'io.lrh.t02-exclusive-trust'
MODEL = 'opencode/deepseek-v4.1-flash-free'
MODEL_ID = 'deepseek-v4.1-flash-free'
NATIVE_PACKAGE = '@opencode/ai/providers/openai-compatible'
EXPECTED_VERSION = 'opencode v2.0.32'
EXPECTED_PATH = '/inference/openai/v1/chat/completions'
DOCKER_HOST = 'unix:///var/run/docker.sock'
RUNTIME_CA_PATH = '/fixture/runtime-ca.pem'
AMBIENT_CA_PATH = '/fixture/ambient-ca.pem'
EXCLUSIVE_CA_ENV = 'OPENCODE_EXCLUSIVE_CA_FILE'
EXCLUSIVE_CA_HASH_ENV = 'OPENCODE_EXCLUSIVE_CA_SHA256'
OPENCODE_SERVER_PORT = 4096
OPENCODE_SERVER_URL = 'http://127.0.0.1:' + str(OPENCODE_SERVER_PORT)
CONTROL_PASSWORD_HEX_LENGTH = 128
TMPFS_OPTIONS = 'rw,nosuid,nodev,size=64m'
VERSION_RECORD = 'opencode-version.txt'
MAX_EXCLUSIVE_CA_BYTES = 4 * 1024 * 1024
MAX_REQUEST_BYTES = 1024 * 1024
AMBIENT_ROOT_SERIAL = 40001
REPLACEMENT_ROOT_SERIAL = 40002
AMBIENT_LEAF_SERIAL = 41001
REPLACEMENT_LEAF_SERIAL = 42001
MALFORMED_EXCLUSIVE_CA_HASH = 'NOT-A-SHA256'

PROXY_ENV = (
    'HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY', 'ALL_PROXY', 'FTP_PROXY',
    'http_proxy', 'https_proxy', 'no_proxy', 'all_proxy', 'ftp_proxy',
)
TRUST_ENV = (
    'SSL_CERT_FILE', 'SSL_CERT_DIR', 'CURL_CA_BUNDLE', 'REQUESTS_CA_BUNDLE',
    'NODE_EXTRA_CA_CERTS', 'GIT_SSL_CAINFO', EXCLUSIVE_CA_ENV,
    EXCLUSIVE_CA_HASH_ENV,
)
MUST_BE_ABSENT_ENV = (
    'SSLKEYLOGFILE', 'NODE_TLS_REJECT_UNAUTHORIZED', 'GIT_SSL_NO_VERIFY',
    'OPENCODE_API_KEY',
)
SENSITIVE_ENV_PARTS = (
    'TOKEN', 'SECRET', 'PASSWORD', 'API_KEY', 'ACCESS_KEY', 'PRIVATE_KEY',
    'AUTHORIZATION', 'CREDENTIAL',
)
BOUNDARY_ENV = {
    'OPENCODE_DISABLE_MODELS_FETCH': '1',
    'OPENCODE_CONFIG_PROJECT_DISABLE': '1',
    'OPENCODE_DISABLE_CLAUDE_CODE': '1',
    'OPENCODE_FILEWATCHER_DISABLE': '1',
    'OPENCODE_DISABLE_FFF': '1',
}
SERVER_CONTROL_ENV = ('OPENCODE_SERVER_USERNAME', 'OPENCODE_SERVER_PASSWORD')
CORE_ARMS = (
    ('ambient-control', 'control', 'ambient', 'ambient'),
    ('replacement-positive', 'candidate', 'replacement', 'replacement'),
    ('ambient-rejected', 'candidate', 'replacement', 'ambient'),
)
PRESOCKET_CASES = (
    ('missing-replacement-pair', 'missing-both'),
    ('missing-replacement-path-env', 'missing-path-env'),
    ('missing-replacement-hash-env', 'missing-hash-env'),
    ('malformed-replacement-hash', 'malformed-hash'),
    ('wrong-replacement-path', 'wrong-path'),
    ('fixed-path-missing-file', 'missing-file'),
    ('unreadable-replacement-ca', 'unreadable'),
    ('empty-replacement-ca', 'empty'),
    ('oversized-replacement-ca', 'oversized'),
    ('replacement-hash-mismatch', 'hash-mismatch'),
)
PAIR_STATE = {
    'absent': 'absent',
    'valid': 'complete',
    'missing-both': 'absent',
    'missing-path-env': 'hash-only',
    'missing-hash-env': 'path-only',
    'malformed-hash': 'malformed-hash',
    'wrong-path': 'complete',
    'missing-file': 'complete',
    'unreadable': 'complete',
    'empty': 'complete',
    'oversized': 'complete',
    'hash-mismatch': 'complete',
}


class CheckError(RuntimeError):
    """A fixed, receipt-safe failure code."""


def _count(value):
    return type(value) is int and value >= 0


def _native_facts_verified(row):
    return (row.get('native_http_verified') is True
            and row.get('provider_package') == NATIVE_PACKAGE
            and row.get('effective_model_package') == NATIVE_PACKAGE
            and row.get('provider_transport') == 'http'
            and row.get('model_transport_override_absent') is True
            and row.get('transport_authority') == 'provider.settings'
            and row.get('provider_base_url_verified') is True
            and row.get('model_base_url_verified') is True
            and row.get('base_url_verified') is True
            and row.get('source_document_verified') is True
            and row.get('readback_scope') == 'persistent-server-authority')


def evaluate_arms(rows, fixture):
    """Evaluate sanitized core-arm and candidate pre-socket observations.

    Positive arms must complete an owned HTTP request.  The negative arm must
    reach the owned TCP listener, fail its TLS handshake, and deliver no HTTP.
    Every core arm must prove the native package and HTTP transport before
    dispatch. Invalid candidate inputs must fail before the owned TCP listener.
    """
    checks = []

    def add(name, passed):
        checks.append({'name': name, 'pass': bool(passed)})

    valid_rows = isinstance(rows, list) and all(isinstance(row, dict) for row in rows)
    fixture_valid = (isinstance(fixture, dict)
                     and re.fullmatch(r'[0-9a-f]{64}',
                                      fixture.get('ambient_ca_sha256', '')) is not None
                     and re.fullmatch(r'[0-9a-f]{64}',
                                      fixture.get('replacement_ca_sha256', '')) is not None
                     and fixture.get('ambient_ca_sha256')
                     != fixture.get('replacement_ca_sha256'))
    add('initial CA fixture hashes are distinct and valid', fixture_valid)
    names = [row.get('arm') for row in rows] if valid_rows else []
    expected_names = ([name for name, _, _, _ in CORE_ARMS]
                      + [name for name, _ in PRESOCKET_CASES])
    add('exact arm identities', valid_rows and sorted(names) == sorted(expected_names)
        and len(set(names)) == len(expected_names))
    by_name = {row.get('arm'): row for row in rows} if valid_rows else {}

    for name, image_role, trust_mode, served_chain in CORE_ARMS:
        row = by_name.get(name, {})
        counts_valid = all(_count(row.get(key)) for key in (
            'preflight_tcp_connections', 'preflight_http_requests', 'tcp_connections',
            'tls_handshakes', 'tls_failures', 'http_requests', 'expected_path_requests',
            'unexpected_http_requests',
        ))
        add(name + ' observation schema', counts_valid
            and row.get('case_kind') == 'core'
            and row.get('image_role') == image_role
            and row.get('trust_mode') == trust_mode
            and row.get('served_chain') == served_chain
            and row.get('version_verified') is True
            and row.get('server_started') is True
            and row.get('mounted_ca_hashes_stable') is True
            and fixture_valid
            and row.get('ambient_ca_sha256') == fixture.get('ambient_ca_sha256')
            and row.get('replacement_ca_sha256') == (
                fixture.get('replacement_ca_sha256')
                if image_role == 'candidate' else None)
            and row.get('replacement_pair_state') == (
                'complete' if image_role == 'candidate' else 'absent'))
        add(name + ' native HTTP package preflight', _native_facts_verified(row))
        add(name + ' readback made no selected-endpoint request', counts_valid
            and row.get('preflight_tcp_connections') == 0
            and row.get('preflight_http_requests') == 0)
        add(name + ' dispatched only after preflight', row.get('dispatched') is True)

    for name in ('ambient-control', 'replacement-positive'):
        row = by_name.get(name, {})
        add(name + ' owned TLS and HTTP succeeded', row.get('exit_kind') == 'zero'
            and _count(row.get('tcp_connections')) and row.get('tcp_connections') >= 1
            and _count(row.get('tls_handshakes')) and row.get('tls_handshakes') >= 1
            and row.get('tls_failures') == 0
            and _count(row.get('http_requests')) and row.get('http_requests') >= 1
            and row.get('expected_path_requests') == row.get('http_requests')
            and row.get('unexpected_http_requests') == 0)

    denied = by_name.get('ambient-rejected', {})
    add('ambient-only chain rejected by replacement store', denied.get('exit_kind') == 'nonzero'
        and _count(denied.get('tcp_connections')) and denied.get('tcp_connections') >= 1
        and denied.get('tls_handshakes') == 0
        and _count(denied.get('tls_failures')) and denied.get('tls_failures') >= 1
        and denied.get('http_requests') == 0
        and denied.get('expected_path_requests') == 0
        and denied.get('unexpected_http_requests') == 0)

    positive = by_name.get('replacement-positive', {})
    add('candidate arms used identical ambient and replacement CA inputs',
        fixture_valid
        and positive.get('ambient_ca_sha256') == denied.get('ambient_ca_sha256')
        == fixture.get('ambient_ca_sha256')
        and positive.get('replacement_ca_sha256')
        == denied.get('replacement_ca_sha256')
        == fixture.get('replacement_ca_sha256'))

    for name, input_mode in PRESOCKET_CASES:
        row = by_name.get(name, {})
        counts_valid = all(_count(row.get(key)) for key in (
            'preflight_tcp_connections', 'preflight_http_requests', 'tcp_connections',
            'tls_handshakes', 'tls_failures', 'http_requests',
            'expected_path_requests', 'unexpected_http_requests',
        ))
        server_started = row.get('server_started') is True
        authority_valid = (
            server_started
            and _native_facts_verified(row)
            and row.get('preflight_tcp_connections') == 0
            and row.get('preflight_http_requests') == 0
            and row.get('dispatched') is True
            and row.get('failure_stage') == 'same-server-dispatch'
        ) or (
            row.get('server_started') is False
            and row.get('native_http_verified') is False
            and row.get('preflight_tcp_connections') == 0
            and row.get('preflight_http_requests') == 0
            and row.get('dispatched') is False
            and row.get('failure_stage') == 'server-startup'
        )
        add(name + ' candidate input rejected before socket',
            row.get('case_kind') == 'pre-socket'
            and row.get('image_role') == 'candidate'
            and row.get('input_mode') == input_mode
            and row.get('version_verified') is True
            and row.get('replacement_pair_state') == PAIR_STATE[input_mode]
            and authority_valid
            and row.get('termination_verified') is True
            and row.get('exit_kind') == 'nonzero'
            and counts_valid
            and all(row.get(key) == 0 for key in (
                'tcp_connections', 'tls_handshakes', 'tls_failures', 'http_requests',
                'expected_path_requests', 'unexpected_http_requests',
            )))
    return {'pass': bool(checks) and all(check['pass'] for check in checks), 'checks': checks}


def self_test():
    """Exercise the pure evaluator without Docker, sockets, or subprocesses."""
    if len({AMBIENT_ROOT_SERIAL, REPLACEMENT_ROOT_SERIAL,
            AMBIENT_LEAF_SERIAL, REPLACEMENT_LEAF_SERIAL}) != 4:
        raise RuntimeError('certificate_serial_fixture_failed')
    exit_cases = ((0, 'zero'), (1, 'nonzero'), (124, 'nonzero'),
                  (-9, 'unknown'), (125, 'unknown'), (126, 'unknown'),
                  (127, 'unknown'), (137, 'unknown'), (255, 'unknown'),
                  (None, 'unknown'), (True, 'unknown'))
    if any(_exit_kind(code) != expected for code, expected in exit_cases):
        raise RuntimeError('exit_classification_fixture_failed')
    fixture = {
        'ambient_ca_sha256': 'a' * 64,
        'replacement_ca_sha256': 'b' * 64,
    }
    base = {
        'version_verified': True,
        'server_started': True,
        'native_http_verified': True,
        'provider_package': NATIVE_PACKAGE,
        'effective_model_package': NATIVE_PACKAGE,
        'provider_transport': 'http',
        'model_transport_override_absent': True,
        'transport_authority': 'provider.settings',
        'provider_base_url_verified': True,
        'model_base_url_verified': True,
        'base_url_verified': True,
        'source_document_verified': True,
        'readback_scope': 'persistent-server-authority',
        'mounted_ca_hashes_stable': True,
        'preflight_tcp_connections': 0,
        'preflight_http_requests': 0,
        'dispatched': True,
        'tcp_connections': 1,
        'tls_handshakes': 1,
        'tls_failures': 0,
        'http_requests': 1,
        'expected_path_requests': 1,
        'unexpected_http_requests': 0,
        'exit_kind': 'zero',
    }
    rows = []
    for name, image_role, trust_mode, served_chain in CORE_ARMS:
        row = dict(base, arm=name, case_kind='core', image_role=image_role,
                   trust_mode=trust_mode, served_chain=served_chain,
                   ambient_ca_sha256=fixture['ambient_ca_sha256'],
                   replacement_ca_sha256=(
                       fixture['replacement_ca_sha256']
                       if image_role == 'candidate' else None),
                   replacement_pair_state=(
                       'complete' if image_role == 'candidate' else 'absent'))
        if name == 'ambient-rejected':
            row.update(exit_kind='nonzero', tls_handshakes=0, tls_failures=1,
                       http_requests=0, expected_path_requests=0)
        rows.append(row)
    for name, input_mode in PRESOCKET_CASES:
        rows.append({
            'arm': name,
            'case_kind': 'pre-socket',
            'image_role': 'candidate',
            'input_mode': input_mode,
            'version_verified': True,
            'replacement_pair_state': PAIR_STATE[input_mode],
            **base,
            'exit_kind': 'nonzero',
            'termination_verified': True,
            'failure_stage': 'same-server-dispatch',
            'preflight_tcp_connections': 0,
            'preflight_http_requests': 0,
            'tcp_connections': 0,
            'tls_handshakes': 0,
            'tls_failures': 0,
            'http_requests': 0,
            'expected_path_requests': 0,
            'unexpected_http_requests': 0,
        })
    rows[3].update(server_started=False, native_http_verified=False,
                   dispatched=False, failure_stage='server-startup')
    if not evaluate_arms(rows, fixture)['pass']:
        raise RuntimeError('evaluator_positive_fixture_failed')
    mutations = (
        (0, 'native_http_verified', False),
        (0, 'provider_base_url_verified', False),
        (1, 'provider_package', 'aisdk:@ai-sdk/openai-compatible'),
        (1, 'provider_transport', 'websocket'),
        (1, 'model_transport_override_absent', False),
        (1, 'transport_authority', 'model.settings'),
        (1, 'model_base_url_verified', False),
        (1, 'base_url_verified', False),
        (2, 'preflight_http_requests', 1),
        (2, 'dispatched', False),
        (2, 'tcp_connections', 0),
        (2, 'tls_failures', 0),
        (2, 'http_requests', 1),
        (2, 'exit_kind', 'zero'),
        (2, 'exit_kind', 'unknown'),
        (1, 'ambient_ca_sha256', 'c' * 64),
        (2, 'replacement_ca_sha256', 'c' * 64),
        (1, 'mounted_ca_hashes_stable', False),
        (0, 'image_role', 'candidate'),
        (1, 'image_role', 'control'),
        (3, 'image_role', 'control'),
        (3, 'dispatched', True),
        (3, 'preflight_tcp_connections', 1),
        (3, 'replacement_pair_state', 'complete'),
        (4, 'replacement_pair_state', 'absent'),
        (5, 'replacement_pair_state', 'complete'),
        (6, 'replacement_pair_state', 'complete'),
        (7, 'input_mode', 'missing-both'),
        (5, 'tcp_connections', 1),
        (8, 'exit_kind', 'zero'),
        (9, 'native_http_verified', False),
        (10, 'preflight_http_requests', 1),
        (11, 'tcp_connections', 1),
        (12, 'exit_kind', 'zero'),
        (12, 'termination_verified', False),
    )
    for index, key, value in mutations:
        changed = copy.deepcopy(rows)
        changed[index][key] = value
        if evaluate_arms(changed, fixture)['pass']:
            raise RuntimeError('evaluator_negative_fixture_failed')
    if evaluate_arms(rows[:-1], fixture)['pass']:
        raise RuntimeError('evaluator_missing_arm_failed')
    changed_fixture = dict(fixture, replacement_ca_sha256=fixture['ambient_ca_sha256'])
    if evaluate_arms(rows, changed_fixture)['pass']:
        raise RuntimeError('evaluator_fixture_identity_failed')
    identifier = 'c' * 64
    absence_cases = (
        ('container', 'Error response from daemon: No such container: ' + identifier),
        ('container', 'Error: No such object: ' + identifier),
        ('network', 'Error response from daemon: No such network: ' + identifier),
        ('network', 'network ' + identifier + ' not found'),
    )
    if any(not _exact_absence_claim(
            kind, identifier,
            subprocess.CompletedProcess([], 1, '', message))
            for kind, message in absence_cases):
        raise RuntimeError('cleanup_absence_fixture_failed')
    ambiguous = (
        subprocess.CompletedProcess([], 1, '', 'Cannot connect to the Docker daemon'),
        subprocess.CompletedProcess([], 1, '', 'No such container: ' + 'd' * 64),
        subprocess.CompletedProcess([], 1, '',
                                    'No such container: ' + identifier + 'suffix'),
        subprocess.CompletedProcess([], 1, '',
                                    'No such container: ' + identifier + '\nwarning'),
        subprocess.CompletedProcess([], None, '',
                                    'No such container: ' + identifier),
        subprocess.CompletedProcess([], 0, '[]', ''),
    )
    if any(_exact_absence_claim('container', identifier, result)
           for result in ambiguous):
        raise RuntimeError('cleanup_ambiguity_fixture_failed')

    class FakeDocker:
        def __init__(self, result):
            self.result = result

        def run(self, *_args):
            return self.result

    responding = FakeDocker(subprocess.CompletedProcess([], 0, '"27.0.0"\n', ''))
    unavailable = FakeDocker(subprocess.CompletedProcess([], 1, '', 'daemon unavailable'))
    if not _docker_engine_responds(responding) or _docker_engine_responds(unavailable):
        raise RuntimeError('cleanup_engine_liveness_fixture_failed')

    class RecoveryDocker:
        def run(self, *args):
            if args[:2] == ('container', 'inspect'):
                return subprocess.CompletedProcess(
                    [], 1, '', 'No such container: ' + identifier)
            if args[:2] == ('info', '--format'):
                return subprocess.CompletedProcess([], 0, '"27.0.0"\n', '')
            raise RuntimeError('unexpected_recovery_docker_command')

    recovered_resource = {
        'kind': 'container', 'id': identifier, 'name': 'owned',
        'active': True, 'nonce': identifier,
    }
    recovered_cleanup = [{
        'kind': 'container', 'id': identifier, 'ownership_verified': True,
        'remove_exit': 0, 'post_inspect_absent': False,
        'post_remove_engine_responding': False, 'pass': False,
    }]
    _remove_resource(RecoveryDocker(), recovered_resource, recovered_cleanup)
    if (recovered_resource['active'] is not False
            or recovered_cleanup[-1].get('pass') is not True
            or recovered_cleanup[-1].get('prior_remove_reverified') is not True):
        raise RuntimeError('cleanup_prior_remove_recovery_fixture_failed')
    unowned_absent_resource = dict(recovered_resource, active=True)
    unowned_absent_cleanup = []
    _remove_resource(
        RecoveryDocker(), unowned_absent_resource, unowned_absent_cleanup)
    if (unowned_absent_resource['active'] is not True
            or unowned_absent_cleanup[-1].get('pass') is not False
            or unowned_absent_cleanup[-1].get('ownership_verified') is not False):
        raise RuntimeError('cleanup_unowned_absence_fixture_failed')
    mounted = FakeDocker(subprocess.CompletedProcess(
        [], 0,
        fixture['ambient_ca_sha256'] + '  ' + AMBIENT_CA_PATH + '\n'
        + fixture['replacement_ca_sha256'] + '  ' + RUNTIME_CA_PATH + '\n',
        '',
    ))
    if _mounted_ca_hashes(mounted, identifier, 'candidate') != {
            'ambient': fixture['ambient_ca_sha256'],
            'replacement': fixture['replacement_ca_sha256']}:
        raise RuntimeError('mounted_ca_readback_fixture_failed')
    malformed_mount = FakeDocker(subprocess.CompletedProcess(
        [], 0, fixture['ambient_ca_sha256'] + '  /wrong/path\n', ''))
    try:
        _mounted_ca_hashes(malformed_mount, identifier, 'control')
    except CheckError as error:
        if str(error) != 'mounted_ca_readback_invalid':
            raise
    else:
        raise RuntimeError('mounted_ca_readback_mutation_failed')
    absence = {'containers_absent': True, 'networks_absent': True}
    reconciliations = [{'pass': True, 'discovered': 0}]
    if not _cleanup_complete(identifier, reconciliations, [], [], absence, []):
        raise RuntimeError('cleanup_success_fixture_failed')
    if _cleanup_complete(identifier, reconciliations, [], [], absence, [
            {'kind': 'container', 'name': 'uncertain',
             'outcome': 'create_result_unconfirmed'}]):
        raise RuntimeError('cleanup_uncertain_create_fixture_failed')

    class FailingDocker:
        def __init__(self, error, journal, snapshots, expected):
            self.error = error
            self.journal = journal
            self.snapshots = snapshots
            self.expected = expected

        def run(self, *_args):
            if self.journal != self.expected or self.snapshots != [self.expected]:
                raise RuntimeError('create_not_persisted_before_docker')
            raise self.error

    pending_network = []
    network_snapshots = []
    expected_network = [{
        'kind': 'network', 'name': _network_name(identifier),
        'outcome': 'create_result_unconfirmed'}]
    try:
        _network(
            FailingDocker(
                KeyboardInterrupt(), pending_network, network_snapshots,
                expected_network),
            identifier, [], pending_network,
            lambda: network_snapshots.append(copy.deepcopy(pending_network)),
        )
    except KeyboardInterrupt:
        pass
    else:
        raise RuntimeError('network_create_interrupt_fixture_failed')
    if pending_network != expected_network:
        raise RuntimeError('network_create_journal_fixture_failed')
    pending_container = []
    container_snapshots = []
    expected_container = [{
        'kind': 'container',
        'name': _container_name(identifier, 'replacement-positive'),
        'outcome': 'create_result_unconfirmed'}]
    try:
        _container(
            FailingDocker(
                RuntimeError('ordinary_non_check_error'), pending_container,
                container_snapshots, expected_container),
            'sha256:' + 'd' * 64,
            {'name': _network_name(identifier)}, '172.18.0.1', identifier,
            'replacement-positive', 'candidate', 'valid',
            Path('/fixture/workspace'), Path('/fixture/opencode.json'),
            Path('/fixture/ambient.pem'), Path('/fixture/replacement.pem'),
            'b' * 64, [], pending_container,
            lambda: container_snapshots.append(copy.deepcopy(pending_container)),
        )
    except RuntimeError as error:
        if str(error) != 'ordinary_non_check_error':
            raise
        pass
    else:
        raise RuntimeError('container_create_interrupt_fixture_failed')
    if pending_container != expected_container:
        raise RuntimeError('container_create_journal_fixture_failed')
    confirmed = []
    confirmation_snapshots = []
    confirmed_name = _container_name(identifier, 'confirmed')
    record = _begin_create(
        confirmed, 'container', confirmed_name,
        lambda: confirmation_snapshots.append(copy.deepcopy(confirmed)),
    )
    confirmed_id = 'e' * 64
    confirmed_resource = {
        'kind': 'container', 'name': confirmed_name, 'id': confirmed_id,
        'active': False, 'nonce': identifier,
    }
    _confirm_create(
        record, confirmed_id,
        lambda: confirmation_snapshots.append(copy.deepcopy(confirmed)),
    )
    if (confirmation_snapshots != [
            [{'kind': 'container', 'name': confirmed_name,
              'outcome': 'create_result_unconfirmed'}],
            [{'kind': 'container', 'name': confirmed_name,
              'outcome': 'exact_id_recorded', 'id': confirmed_id}],
            ]
            or not _create_journal_confirmed(confirmed, [confirmed_resource])):
        raise RuntimeError('create_confirmation_journal_fixture_failed')
    interrupted_confirmation = []
    interrupted_record = _begin_create(
        interrupted_confirmation, 'container', confirmed_name, lambda: None)

    def interrupt_confirmation():
        raise KeyboardInterrupt

    try:
        _confirm_create(
            interrupted_record, confirmed_id, interrupt_confirmation,
        )
    except KeyboardInterrupt:
        pass
    else:
        raise RuntimeError('create_confirmation_interrupt_fixture_failed')
    if (interrupted_confirmation != [{
            'kind': 'container', 'name': confirmed_name,
            'outcome': 'create_result_unconfirmed'}]
            or _create_journal_confirmed(
                interrupted_confirmation, [confirmed_resource])):
        raise RuntimeError('create_confirmation_rollback_fixture_failed')

    class InterruptingRecord(dict):
        def __setitem__(self, key, value):
            super().__setitem__(key, value)
            if key == 'outcome':
                raise KeyboardInterrupt

    assignment_interrupted = InterruptingRecord({
        'kind': 'container', 'name': confirmed_name,
        'outcome': 'create_result_unconfirmed'})
    try:
        _confirm_create(assignment_interrupted, confirmed_id, lambda: None)
    except KeyboardInterrupt:
        pass
    else:
        raise RuntimeError('create_confirmation_assignment_interrupt_fixture_failed')
    if assignment_interrupted != {
            'kind': 'container', 'name': confirmed_name,
            'outcome': 'create_result_unconfirmed'}:
        raise RuntimeError('create_confirmation_assignment_rollback_fixture_failed')

    class FakePathEntry:
        def __init__(self, outcome):
            self.outcome = outcome

        def lstat(self):
            if isinstance(self.outcome, BaseException):
                raise self.outcome
            return self.outcome

    if (not _path_entry_absent(FakePathEntry(FileNotFoundError()))
            or _path_entry_absent(FakePathEntry(OSError()))
            or _path_entry_absent(FakePathEntry(object()))):
        raise RuntimeError('temporary_workspace_absence_fixture_failed')
    return True


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stable_file_identity(path, *, maximum=MAX_EXCLUSIVE_CA_BYTES):
    flags = os.O_RDONLY | getattr(os, 'O_CLOEXEC', 0) | getattr(os, 'O_NOFOLLOW', 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        raise CheckError('fixture_identity_unavailable') from None
    try:
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or before.st_size <= 0
                or before.st_size > maximum or stat.S_IMODE(before.st_mode) != 0o600):
            raise CheckError('fixture_identity_invalid')
        chunks = []
        remaining = before.st_size + 1
        while remaining:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
    except OSError:
        raise CheckError('fixture_identity_unavailable') from None
    finally:
        os.close(descriptor)
    data = b''.join(chunks)
    if (len(data) != before.st_size or before.st_dev != after.st_dev
            or before.st_ino != after.st_ino or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or before.st_ctime_ns != after.st_ctime_ns):
        raise CheckError('fixture_identity_changed')
    return {
        'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
        'device': before.st_dev, 'inode': before.st_ino,
        'mtime_ns': before.st_mtime_ns, 'ctime_ns': before.st_ctime_ns,
    }


def _fixture_identities(certificates):
    return {
        chain + '.' + field: _stable_file_identity(certificates[chain][field])
        for chain in ('ambient', 'replacement')
        for field in ('ca', 'leaf', 'leaf_key')
    }


def _require_fixture_identities(certificates, expected):
    if _fixture_identities(certificates) != expected:
        raise CheckError('certificate_fixture_changed')


def _safe_output(raw):
    path = raw if raw.is_absolute() else Path.cwd() / raw
    if path.exists() or path.is_symlink():
        raise CheckError('output_exists_or_symlink')
    if not path.name or path.name in ('.', '..') or ',' in path.name \
            or any(ord(character) < 32 or ord(character) == 127 for character in str(path)):
        raise CheckError('output_path_invalid')
    parent = path.parent
    if not parent.exists() or not parent.is_dir():
        raise CheckError('output_parent_invalid')
    current = Path(path.anchor)
    for part in path.parent.parts[1:]:
        current /= part
        try:
            mode = current.lstat().st_mode
        except OSError:
            raise CheckError('output_parent_invalid') from None
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise CheckError('output_parent_invalid')
    try:
        os.mkdir(path, 0o700)
    except OSError:
        raise CheckError('output_create_failed') from None
    try:
        _fsync_directory(parent)
    except OSError:
        raise CheckError('output_parent_sync_failed') from None
    return path.resolve(strict=True)


def _fsync_directory(path):
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0)
        | getattr(os, 'O_CLOEXEC', 0) | getattr(os, 'O_NOFOLLOW', 0))
    try:
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_json(output, receipt):
    target = output / 'result.json'
    temporary = output / '.result.json.tmp'
    data = (json.dumps(receipt, indent=2, sort_keys=True) + '\n').encode()
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC
                         | getattr(os, 'O_CLOEXEC', 0), 0o600)
    try:
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, target)
    _fsync_directory(output)


def _run(argv, timeout=30, input_text=None, environment=None):
    process_environment = {'PATH': os.environ.get('PATH', '')}
    if environment:
        process_environment.update(environment)
    try:
        return subprocess.run(argv, input=input_text, capture_output=True, text=True,
                              timeout=timeout, env=process_environment)
    except subprocess.TimeoutExpired:
        raise CheckError('command_timeout') from None
    except OSError:
        raise CheckError('command_unavailable') from None


def _openssl(*args, expected=0):
    result = _run(['openssl', *args], timeout=20)
    if (result.returncode == 0) is (expected == 0):
        return result
    raise CheckError('certificate_fixture_failed')


def _generate_chain(folder, label, root_serial, leaf_serial):
    key = folder / (label + '-ca.key')
    root = folder / (label + '-ca.pem')
    leaf_key = folder / (label + '-leaf.key')
    request = folder / (label + '-leaf.csr')
    leaf = folder / (label + '-leaf.pem')
    extension = folder / (label + '-leaf.ext')
    extension.write_text('subjectAltName=DNS:opencode.ai\n'
                         'basicConstraints=critical,CA:FALSE\n'
                         'keyUsage=critical,digitalSignature,keyEncipherment\n'
                         'extendedKeyUsage=serverAuth\n', encoding='ascii')
    _openssl('req', '-x509', '-newkey', 'rsa:2048', '-noenc', '-days', '1', '-sha256',
             '-subj', '/CN=T02 owned ' + label + ' root',
             '-set_serial', str(root_serial),
             '-addext', 'basicConstraints=critical,CA:TRUE',
             '-addext', 'keyUsage=critical,keyCertSign,cRLSign',
             '-keyout', str(key), '-out', str(root))
    _openssl('req', '-newkey', 'rsa:2048', '-noenc', '-sha256', '-subj', '/CN=opencode.ai',
             '-keyout', str(leaf_key), '-out', str(request))
    _openssl('x509', '-req', '-in', str(request), '-CA', str(root), '-CAkey', str(key),
             '-set_serial', str(leaf_serial), '-days', '1', '-sha256', '-extfile', str(extension),
             '-out', str(leaf))
    key.chmod(0o600)
    leaf_key.chmod(0o600)
    root.chmod(0o600)
    leaf.chmod(0o600)
    _openssl('verify', '-CAfile', str(root), '-verify_hostname', 'opencode.ai', str(leaf))
    return {'ca_key': key, 'ca': root, 'leaf_key': leaf_key, 'leaf': leaf}


def _prepare_certificates(folder):
    ambient = _generate_chain(
        folder, 'ambient', AMBIENT_ROOT_SERIAL, AMBIENT_LEAF_SERIAL)
    replacement = _generate_chain(
        folder, 'replacement', REPLACEMENT_ROOT_SERIAL, REPLACEMENT_LEAF_SERIAL)
    if sha256(ambient['ca']) == sha256(replacement['ca']):
        raise CheckError('certificate_roots_not_distinct')
    _openssl('verify', '-CAfile', str(ambient['ca']), '-verify_hostname', 'opencode.ai',
             str(replacement['leaf']), expected=1)
    _openssl('verify', '-CAfile', str(replacement['ca']), '-verify_hostname', 'opencode.ai',
             str(ambient['leaf']), expected=1)
    return ambient, replacement


class _OwnedHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, _format, *_args):
        return

    def do_GET(self):
        with self.server.observation_lock:
            self.server.http_requests += 1
            self.server.unexpected_http_requests += 1
        self.send_error(405)

    def do_POST(self):
        length_text = self.headers.get('Content-Length', '')
        try:
            length = int(length_text)
        except ValueError:
            length = -1
        expected = self.path.split('?', 1)[0] == EXPECTED_PATH
        with self.server.observation_lock:
            self.server.http_requests += 1
            if expected:
                self.server.expected_path_requests += 1
            else:
                self.server.unexpected_http_requests += 1
        if length < 0 or length > MAX_REQUEST_BYTES:
            self.send_error(413)
            return
        if length:
            self.rfile.read(length)
        if not expected:
            self.send_error(404)
            return
        item = {'id': 'owned-exclusive-trust', 'object': 'chat.completion.chunk',
                'created': 1, 'model': MODEL_ID}
        chunks = [
            item | {'choices': [{'index': 0,
                                 'delta': {'role': 'assistant', 'content': 'OK'},
                                 'finish_reason': None}]},
            item | {'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}],
                    'usage': {'prompt_tokens': 2, 'completion_tokens': 1, 'total_tokens': 3}},
        ]
        payload = (''.join('data: ' + json.dumps(chunk, separators=(',', ':')) + '\n\n'
                           for chunk in chunks) + 'data: [DONE]\n\n').encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(payload)


class _OwnedTLSServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, address, context):
        self.tls_context = context
        self.observation_lock = threading.Lock()
        self.tcp_connections = 0
        self.tls_handshakes = 0
        self.tls_failures = 0
        self.http_requests = 0
        self.expected_path_requests = 0
        self.unexpected_http_requests = 0
        super().__init__(address, _OwnedHandler)

    def get_request(self):
        raw, address = self.socket.accept()
        raw.settimeout(5)
        with self.observation_lock:
            self.tcp_connections += 1
        try:
            secure = self.tls_context.wrap_socket(raw, server_side=True)
        except (OSError, ssl.SSLError):
            with self.observation_lock:
                self.tls_failures += 1
            raw.close()
            raise OSError('owned_tls_handshake_failed') from None
        with self.observation_lock:
            self.tls_handshakes += 1
        return secure, address

    def snapshot(self):
        with self.observation_lock:
            return {key: getattr(self, key) for key in (
                'tcp_connections', 'tls_handshakes', 'tls_failures', 'http_requests',
                'expected_path_requests', 'unexpected_http_requests',
            )}


class Docker:
    def __init__(self):
        self.prefix = ['docker', '--host=' + DOCKER_HOST]

    def run(self, *args, timeout=30, environment=None):
        return _run([*self.prefix, *args], timeout=timeout, environment=environment)

    def json(self, *args, timeout=30):
        result = self.run(*args, timeout=timeout)
        if result.returncode:
            raise CheckError('docker_read_failed')
        try:
            return json.loads(result.stdout)
        except ValueError:
            raise CheckError('docker_json_invalid') from None


def _critical_name(name):
    upper = name.upper()
    return (name in PROXY_ENV or name in TRUST_ENV or name in MUST_BE_ABSENT_ENV
            or name in BOUNDARY_ENV or name in SERVER_CONTROL_ENV
            or any(part in upper for part in SENSITIVE_ENV_PARTS))


def _env_map(items):
    if not isinstance(items, list) or any(not isinstance(item, str) or '=' not in item for item in items):
        raise CheckError('container_env_invalid')
    pairs = [item.split('=', 1) for item in items]
    if len({name for name, _ in pairs}) != len(pairs):
        raise CheckError('container_env_duplicate')
    return dict(pairs)


def _inspect_image(docker, image_id):
    data = docker.json('image', 'inspect', image_id)
    if (not isinstance(data, list) or len(data) != 1 or data[0].get('Id') != image_id
            or data[0].get('Os') != 'linux' or data[0].get('Architecture') != 'amd64'):
        raise CheckError('exact_linux_amd64_image_required')
    image_env = _env_map(data[0].get('Config', {}).get('Env') or [])
    if any(_critical_name(name) for name in image_env):
        raise CheckError('image_contains_critical_environment')
    return {'id': image_id, 'os': 'linux', 'architecture': 'amd64'}


def _network_name(nonce):
    return 'nq-exclusive-' + nonce[:12]


def _container_name(nonce, arm):
    return _network_name(nonce) + '-' + arm


def _begin_create(create_journal, kind, name, persist):
    record = {'kind': kind, 'name': name,
              'outcome': 'create_result_unconfirmed'}
    create_journal.append(record)
    persist()
    return record


def _confirm_create(record, identifier, persist):
    pending = dict(record)
    try:
        record['id'] = identifier
        record['outcome'] = 'exact_id_recorded'
        persist()
    except BaseException:
        record.clear()
        record.update(pending)
        raise


def _network(docker, nonce, resources, create_journal, persist):
    name = _network_name(nonce)
    record = _begin_create(create_journal, 'network', name, persist)
    result = docker.run('network', 'create', '--internal', '--driver', 'bridge',
                        '--label', LABEL + '=' + nonce, name)
    if result.returncode or not re.fullmatch(r'[0-9a-f]{64}', result.stdout.strip()):
        raise CheckError('internal_network_create_failed')
    identifier = result.stdout.strip()
    resources.append({'kind': 'network', 'id': identifier, 'name': name,
                      'active': True, 'nonce': nonce})
    _confirm_create(record, identifier, persist)
    data = docker.json('network', 'inspect', identifier)
    if not isinstance(data, list) or len(data) != 1:
        raise CheckError('internal_network_inspect_failed')
    item = data[0]
    configs = item.get('IPAM', {}).get('Config')
    if (item.get('Id') != identifier or item.get('Name') != name or item.get('Internal') is not True
            or item.get('Driver') != 'bridge' or not isinstance(configs, list) or len(configs) != 1):
        raise CheckError('internal_network_invalid')
    try:
        subnet = ipaddress.ip_network(configs[0]['Subnet'])
        gateway = ipaddress.ip_address(configs[0]['Gateway'])
    except (KeyError, ValueError):
        raise CheckError('internal_network_ipam_invalid') from None
    if gateway not in subnet or gateway.version != 4:
        raise CheckError('internal_network_gateway_invalid')
    return {'id': identifier, 'name': name, 'gateway': str(gateway)}


def _config(path, base_url):
    document = {
        '$schema': 'https://opencode.ai/config.json',
        'model': MODEL,
        'update': 'disable',
        'share': 'disabled',
        'plugins': [],
        'mcp': {'servers': {}},
        'websearch': False,
        'warming': False,
        'permissions': [{'action': '*', 'resource': '*', 'effect': 'deny'}],
        'policies': [
            {'action': 'provider.use', 'resource': '*', 'effect': 'deny'},
            {'action': 'provider.use', 'resource': 'opencode', 'effect': 'allow'},
        ],
        'providers': {
            'opencode': {
                'settings': {'baseURL': base_url, 'transport': 'http'},
                'models': {MODEL_ID: {'settings': {'baseURL': base_url}}},
            },
        },
    }
    path.write_text(json.dumps(document, separators=(',', ':')) + '\n', encoding='utf-8')
    path.chmod(0o600)


def _container(docker, image_id, network, gateway, nonce, arm, image_role, input_mode,
               workspace, config, ambient_ca, exclusive_input, exclusive_sha256,
               resources, create_journal, persist):
    allowed = {
        'control': {'absent'},
        'candidate': {'valid', 'missing-both', 'missing-path-env',
                      'missing-hash-env', 'malformed-hash', 'wrong-path',
                      'missing-file', 'unreadable', 'empty', 'oversized',
                      'hash-mismatch'},
    }
    if image_role not in allowed or input_mode not in allowed[image_role]:
        raise CheckError('container_image_role_invalid')
    hash_is_valid = re.fullmatch(r'[0-9a-f]{64}', exclusive_sha256) is not None
    if ((input_mode == 'malformed-hash'
         and exclusive_sha256 != MALFORMED_EXCLUSIVE_CA_HASH)
            or (input_mode != 'malformed-hash' and not hash_is_valid)):
        raise CheckError('exclusive_ca_hash_invalid')
    mounts = [
        'type=bind,src=' + str(workspace) + ',dst=/workspace',
        'type=bind,src=' + str(config) + ',dst=/workspace/config/opencode/opencode.json,readonly',
        'type=bind,src=' + str(ambient_ca) + ',dst=' + AMBIENT_CA_PATH + ',readonly',
    ]
    mounted_modes = {'valid', 'missing-path-env', 'missing-hash-env',
                     'malformed-hash', 'wrong-path', 'unreadable', 'empty',
                     'oversized', 'hash-mismatch'}
    if input_mode in mounted_modes:
        mounts.append('type=bind,src=' + str(exclusive_input)
                      + ',dst=' + RUNTIME_CA_PATH + ',readonly')
    env = [name + '=' for name in PROXY_ENV]
    env += [
        'HOME=/workspace/home',
        'XDG_CONFIG_HOME=/workspace/config',
        'XDG_DATA_HOME=/workspace/data',
        'XDG_CACHE_HOME=/workspace/cache',
        'XDG_STATE_HOME=/workspace/state',
        'TMPDIR=/workspace/tmp',
        'NO_COLOR=1',
        'SSL_CERT_FILE=' + AMBIENT_CA_PATH,
        *(name + '=' + value for name, value in BOUNDARY_ENV.items()),
    ]
    path_modes = allowed['candidate'] - {'missing-both', 'missing-path-env'}
    hash_modes = allowed['candidate'] - {'missing-both', 'missing-hash-env'}
    if input_mode in path_modes - {'wrong-path'}:
        env.append(EXCLUSIVE_CA_ENV + '=' + RUNTIME_CA_PATH)
    elif input_mode == 'wrong-path':
        env.append(EXCLUSIVE_CA_ENV + '=/fixture/not-runtime-ca.pem')
    if input_mode in hash_modes:
        env.append(EXCLUSIVE_CA_HASH_ENV + '=' + exclusive_sha256)
    name = _container_name(nonce, arm)
    argv = [
        'container', 'create', '--pull', 'never', '--platform', 'linux/amd64',
        '--name', name,
        '--network', network['name'], '--add-host', 'opencode.ai:' + gateway,
        '--read-only', '--restart', 'no', '--log-driver', 'none',
        '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges=true',
        '--user', str(os.getuid()) + ':' + str(os.getgid()),
        '--memory', '1g', '--memory-swap', '1g', '--cpus', '1',
        '--pids-limit', '64', '--ulimit', 'core=0:0',
        '--tmpfs', '/tmp:' + TMPFS_OPTIONS,
        '--workdir', '/workspace/project', '--dns', '127.0.0.1',
        '--label', LABEL + '=' + nonce, '--label', LABEL + '.arm=' + arm,
    ]
    for mount in mounts:
        argv += ['--mount', mount]
    for item in env:
        argv += ['--env', item]
    server_command = (
        'set -eu; umask 077; '
        'control_words="$(/bin/busybox od -A n -N 64 -t x1 -v /dev/urandom)"; '
        'OPENCODE_SERVER_PASSWORD=; '
        'for control_word in $control_words; do '
        'OPENCODE_SERVER_PASSWORD="${OPENCODE_SERVER_PASSWORD}${control_word}"; done; '
        'unset control_word control_words; '
        '[ "${#OPENCODE_SERVER_PASSWORD}" -eq '
        + str(CONTROL_PASSWORD_HEX_LENGTH) + ' ]; '
        'opencode --version > /workspace/' + VERSION_RECORD + '; '
        'OPENCODE_SERVER_USERNAME=opencode; '
        'export OPENCODE_SERVER_USERNAME OPENCODE_SERVER_PASSWORD; '
        'exec opencode serve --hostname 127.0.0.1 --port '
        + str(OPENCODE_SERVER_PORT))
    record = _begin_create(create_journal, 'container', name, persist)
    result = docker.run(*argv, '--entrypoint', 'sh', image_id, '-c', server_command)
    identifier = result.stdout.strip()
    if result.returncode or not re.fullmatch(r'[0-9a-f]{64}', identifier):
        raise CheckError('container_create_failed')
    resources.append({'kind': 'container', 'id': identifier, 'name': name,
                      'active': True, 'nonce': nonce})
    _confirm_create(record, identifier, persist)
    data = docker.json('container', 'inspect', identifier)
    if not isinstance(data, list) or len(data) != 1:
        raise CheckError('container_inspect_failed')
    item = data[0]
    effective = _env_map(item.get('Config', {}).get('Env') or [])
    requested = dict(value.split('=', 1) for value in env)
    critical = {name: value for name, value in effective.items() if _critical_name(name)}
    expected_bind_mounts = {
        '/workspace': (str(workspace), True),
        '/workspace/config/opencode/opencode.json': (str(config), False),
        AMBIENT_CA_PATH: (str(ambient_ca), False),
    }
    if input_mode in mounted_modes:
        expected_bind_mounts[RUNTIME_CA_PATH] = (str(exclusive_input), False)
    bind_mounts = {}
    for mount in item.get('Mounts', []):
        if isinstance(mount, dict) and mount.get('Type') == 'bind':
            destination = mount.get('Destination')
            if destination in bind_mounts:
                raise CheckError('container_mount_readback_failed')
            bind_mounts[destination] = (mount.get('Source'), mount.get('RW'))
    if (item.get('Id') != identifier or item.get('Image') != image_id
            or item.get('Name') != '/' + name
            or item.get('State', {}).get('Status') != 'created'
            or item.get('Config', {}).get('User') != str(os.getuid()) + ':' + str(os.getgid())
            or item.get('Config', {}).get('WorkingDir') != '/workspace/project'
            or item.get('Config', {}).get('Entrypoint') != ['sh']
            or item.get('Config', {}).get('Cmd') != ['-c', server_command]
            or item.get('Config', {}).get('Labels', {}).get(LABEL) != nonce
            or item.get('Config', {}).get('Labels', {}).get(LABEL + '.arm') != arm
            or item.get('HostConfig', {}).get('ReadonlyRootfs') is not True
            or item.get('HostConfig', {}).get('NetworkMode') != network['name']
            or item.get('HostConfig', {}).get('CapDrop') != ['ALL']
            or item.get('HostConfig', {}).get('Memory') != 1024 * 1024 * 1024
            or item.get('HostConfig', {}).get('MemorySwap') != 1024 * 1024 * 1024
            or item.get('HostConfig', {}).get('NanoCpus') != 1_000_000_000
            or item.get('HostConfig', {}).get('PidsLimit') != 64
            or item.get('HostConfig', {}).get('RestartPolicy') != {
                'Name': 'no', 'MaximumRetryCount': 0}
            or item.get('HostConfig', {}).get('LogConfig') != {
                'Type': 'none', 'Config': {}}
            or item.get('HostConfig', {}).get('Tmpfs') != {'/tmp': TMPFS_OPTIONS}
            or item.get('HostConfig', {}).get('Ulimits') != [
                {'Name': 'core', 'Hard': 0, 'Soft': 0}]
            or not any(value in {'no-new-privileges', 'no-new-privileges=true',
                                 'no-new-privileges:true'}
                       for value in item.get('HostConfig', {}).get('SecurityOpt', []))
            or item.get('HostConfig', {}).get('Dns') != ['127.0.0.1']
            or item.get('HostConfig', {}).get('ExtraHosts') != ['opencode.ai:' + gateway]
            or set(item.get('NetworkSettings', {}).get('Networks', {})) != {network['name']}
            or bind_mounts != expected_bind_mounts
            or critical != {name: value for name, value in requested.items() if _critical_name(name)}
            or any(name in effective for name in MUST_BE_ABSENT_ENV)
            or any(effective.get(name) != '' for name in PROXY_ENV)):
        raise CheckError('container_boundary_readback_failed')
    expected_exclusive = {
        'absent': None,
        'missing-both': None,
        'missing-path-env': None,
        'missing-hash-env': RUNTIME_CA_PATH,
        'malformed-hash': RUNTIME_CA_PATH,
        'valid': RUNTIME_CA_PATH,
        'empty': RUNTIME_CA_PATH,
        'oversized': RUNTIME_CA_PATH,
        'missing-file': RUNTIME_CA_PATH,
        'unreadable': RUNTIME_CA_PATH,
        'hash-mismatch': RUNTIME_CA_PATH,
        'wrong-path': '/fixture/not-runtime-ca.pem',
    }[input_mode]
    expected_hash = None if input_mode in {'absent', 'missing-both',
                                           'missing-hash-env'} else exclusive_sha256
    if effective.get('SSL_CERT_FILE') != AMBIENT_CA_PATH:
        raise CheckError('container_ambient_trust_readback_failed')
    if ((expected_exclusive is None and EXCLUSIVE_CA_ENV in effective)
            or (expected_exclusive is not None
                and effective.get(EXCLUSIVE_CA_ENV) != expected_exclusive)
            or (expected_hash is None and EXCLUSIVE_CA_HASH_ENV in effective)
            or (expected_hash is not None
                and effective.get(EXCLUSIVE_CA_HASH_ENV) != expected_hash)):
        raise CheckError('container_exclusive_trust_readback_failed')
    for name in TRUST_ENV:
        if name not in {'SSL_CERT_FILE', EXCLUSIVE_CA_ENV, EXCLUSIVE_CA_HASH_ENV} \
                and name in effective:
            raise CheckError('container_unexpected_trust_environment')
    return identifier


def _authenticated_exec(docker, identifier, *command, timeout=45):
    # In v2.0.32, `serve` uses server-process mode=default, which retains the
    # control environment in PID 1. Env.session filters both control names from
    # tool child environments. Read exactly one value without host materialization.
    client_command = (
        'set -eu; OPENCODE_SERVER_PASSWORD=; control_matches=0; '
        'while IFS= read -r -d "" control_entry; do '
        'case "$control_entry" in OPENCODE_SERVER_PASSWORD=*) '
        'OPENCODE_SERVER_PASSWORD="${control_entry#OPENCODE_SERVER_PASSWORD=}"; '
        'control_matches=$((control_matches + 1));; esac; '
        'done < /proc/1/environ; '
        '[ "$control_matches" -eq 1 ]; '
        '[ "${#OPENCODE_SERVER_PASSWORD}" -eq '
        + str(CONTROL_PASSWORD_HEX_LENGTH) + ' ]; '
        'unset control_entry control_matches; '
        'OPENCODE_SERVER_USERNAME=opencode; '
        'export OPENCODE_SERVER_USERNAME OPENCODE_SERVER_PASSWORD; exec "$@"')
    return docker.run(
        'container', 'exec', '-w', '/workspace/project', identifier,
        'sh', '-c', client_command, 'opencode-control-client', *command,
        timeout=timeout,
    )


def _start_server_container(docker, identifier):
    started = docker.run('container', 'start', identifier)
    if started.returncode:
        raise CheckError('container_start_failed')


def _api_json(docker, identifier, method):
    result = _authenticated_exec(
        docker, identifier,
        'opencode', 'api', '--server', OPENCODE_SERVER_URL, method,
    )
    if result.returncode:
        raise CheckError('native_http_readback_unavailable')
    try:
        parsed = json.loads(result.stdout)
    except ValueError:
        raise CheckError('native_http_readback_unavailable') from None
    return parsed


def _container_state(docker, identifier):
    data = docker.json('container', 'inspect', identifier)
    if not isinstance(data, list) or len(data) != 1 or data[0].get('Id') != identifier:
        raise CheckError('container_state_unavailable')
    state = data[0].get('State')
    if not isinstance(state, dict):
        raise CheckError('container_state_unavailable')
    return state


def _wait_server(docker, identifier):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        result = _authenticated_exec(
            docker, identifier,
            'opencode', 'api', '--server', OPENCODE_SERVER_URL, 'server.info', timeout=5,
        )
        if result.returncode == 0:
            try:
                parsed = json.loads(result.stdout)
            except ValueError:
                raise CheckError('persistent_server_readiness_invalid') from None
            if not isinstance(parsed, dict):
                raise CheckError('persistent_server_readiness_invalid')
            return True
        state = _container_state(docker, identifier)
        if state.get('Running') is not True:
            return False
        time.sleep(.1)
    raise CheckError('persistent_server_readiness_timeout')


def _mounted_ca_hashes(docker, identifier, image_role):
    paths = [AMBIENT_CA_PATH]
    if image_role == 'candidate':
        paths.append(RUNTIME_CA_PATH)
    result = docker.run(
        'container', 'exec', identifier,
        '/bin/busybox', 'sha256sum', *paths,
    )
    if result.returncode:
        raise CheckError('mounted_ca_readback_unavailable')
    lines = result.stdout.splitlines()
    if len(lines) != len(paths):
        raise CheckError('mounted_ca_readback_invalid')
    hashes = {}
    for key, path, line in zip(('ambient', 'replacement'), paths, lines):
        match = re.fullmatch(r'([0-9a-f]{64})[ \t]+\*?' + re.escape(path), line)
        if match is None:
            raise CheckError('mounted_ca_readback_invalid')
        hashes[key] = match.group(1)
    return hashes


def _version_verified(workspace):
    path = workspace / VERSION_RECORD
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            path.lstat()
            break
        except OSError:
            pass
        time.sleep(.05)
    flags = os.O_RDONLY | getattr(os, 'O_CLOEXEC', 0) | getattr(os, 'O_NOFOLLOW', 0)
    try:
        descriptor = os.open(path, flags)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > 128:
            return False
        data = os.read(descriptor, 129)
        after = os.fstat(descriptor)
    except OSError:
        return False
    finally:
        if 'descriptor' in locals():
            os.close(descriptor)
    if (len(data) != before.st_size or before.st_dev != after.st_dev
            or before.st_ino != after.st_ino or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns):
        return False
    try:
        value = data.decode('ascii')
    except UnicodeError:
        return False
    return value.strip() == EXPECTED_VERSION


def _api_protocol_list(docker, identifier, method):
    parsed = _api_json(docker, identifier, method)
    if not isinstance(parsed, dict) or not isinstance(parsed.get('data'), list):
        raise CheckError('native_http_readback_unavailable')
    return parsed['data']


def _api_direct_list(docker, identifier, method):
    parsed = _api_json(docker, identifier, method)
    if not isinstance(parsed, list):
        raise CheckError('native_http_readback_unavailable')
    return parsed


def _native_http_preflight(docker, identifier, base_url):
    providers = _api_protocol_list(docker, identifier, 'provider.list')
    models = _api_protocol_list(docker, identifier, 'model.list')
    config_entries = _api_direct_list(docker, identifier, 'config.get')
    provider_matches = [
        row for row in providers
        if isinstance(row, dict) and row.get('id') == 'opencode'
    ]
    model_matches = [
        row for row in models
        if (isinstance(row, dict) and row.get('providerID') == 'opencode'
            and row.get('id') == MODEL_ID)
    ]
    if len(provider_matches) != 1 or len(model_matches) != 1:
        raise CheckError('native_http_readback_unavailable')
    provider = provider_matches[0]
    model = model_matches[0]
    source_matches = 0
    conflicting_source = False
    for entry in config_entries:
        if not isinstance(entry, dict) or entry.get('type') != 'document':
            continue
        document = entry.get('info')
        config_providers = document.get('providers') if isinstance(document, dict) else None
        config_provider = (config_providers.get('opencode')
                           if isinstance(config_providers, dict) else None)
        provider_settings = (config_provider.get('settings')
                             if isinstance(config_provider, dict) else None)
        config_models = (config_provider.get('models')
                         if isinstance(config_provider, dict) else None)
        config_model = (config_models.get(MODEL_ID)
                        if isinstance(config_models, dict) else None)
        model_settings = config_model.get('settings') if isinstance(config_model, dict) else None
        if not isinstance(config_provider, dict):
            continue
        relevant = (isinstance(provider_settings, dict)
                    and any(key in provider_settings for key in ('baseURL', 'transport')))
        relevant = relevant or (isinstance(model_settings, dict)
                                and any(key in model_settings
                                        for key in ('baseURL', 'transport')))
        if not relevant:
            continue
        if (isinstance(provider_settings, dict)
                and entry.get('path') == '/workspace/config/opencode/opencode.json'
                and document.get('model') == MODEL
                and isinstance(config_model, dict)
                and isinstance(model_settings, dict)
                and provider_settings.get('baseURL') == base_url
                and provider_settings.get('transport') == 'http'
                and model_settings.get('baseURL') == base_url
                and 'transport' not in model_settings):
            source_matches += 1
        else:
            conflicting_source = True
    if source_matches != 1 or conflicting_source:
        raise CheckError('native_http_readback_unavailable')
    provider_settings = provider.get('settings')
    model_settings = model.get('settings')
    if not isinstance(provider_settings, dict) or not isinstance(model_settings, dict):
        raise CheckError('native_http_readback_unavailable')
    model_transport_override_absent = 'transport' not in model_settings
    provider_base_url_verified = provider_settings.get('baseURL') == base_url
    model_base_url_verified = model_settings.get('baseURL') == base_url
    facts = {
        'provider_package': provider.get('package'),
        'effective_model_package': model.get('package'),
        'provider_transport': provider_settings.get('transport'),
        'model_transport_override_absent': model_transport_override_absent,
        'transport_authority': 'provider.settings',
        'provider_base_url_verified': provider_base_url_verified,
        'model_base_url_verified': model_base_url_verified,
        'base_url_verified': provider_base_url_verified and model_base_url_verified,
        'source_document_verified': True,
        'readback_scope': 'persistent-server-authority',
    }
    facts['native_http_verified'] = (
        facts['provider_package'] == NATIVE_PACKAGE
        and facts['effective_model_package'] == NATIVE_PACKAGE
        and facts['provider_transport'] == 'http'
        and facts['model_transport_override_absent'] is True
        and facts['transport_authority'] == 'provider.settings'
        and facts['provider_base_url_verified'] is True
        and facts['model_base_url_verified'] is True
        and facts['base_url_verified'] is True
        and facts['source_document_verified'] is True
    )
    if not facts['native_http_verified']:
        raise CheckError('native_http_readback_unavailable')
    return facts


def _exit_kind(returncode):
    if type(returncode) is not int:
        return 'unknown'
    if returncode == 0:
        return 'zero'
    if 0 < returncode < 125:
        return 'nonzero'
    return 'unknown'


def _exact_absence_claim(kind, identifier, result):
    if (kind not in {'container', 'network'} or result is None
            or re.fullmatch(r'[0-9a-f]{64}', identifier) is None
            or type(result.returncode) is not int or result.returncode == 0
            or not isinstance(result.stderr, str)):
        return False
    core = (
        ('no such container: ' + identifier, 'no such object: ' + identifier)
        if kind == 'container'
        else ('no such network: ' + identifier, 'network ' + identifier + ' not found'))
    expected = set(core)
    expected.update('error response from daemon: ' + message for message in core)
    expected.update('error: ' + message for message in core)
    lines = [line.strip().lower() for line in result.stderr.splitlines()
             if line.strip()]
    return len(lines) == 1 and lines[0] in expected


def _docker_engine_responds(docker):
    try:
        result = docker.run('info', '--format', '{{json .ServerVersion}}')
    except CheckError:
        return False
    if result.returncode:
        return False
    try:
        version = json.loads(result.stdout)
    except ValueError:
        return False
    return isinstance(version, str) and bool(version.strip())


def _remove_resource(docker, resource, cleanup):
    if not resource['active']:
        return
    try:
        inspected_before = docker.run(resource['kind'], 'inspect', resource['id'])
    except CheckError:
        cleanup.append({'kind': resource['kind'], 'id': resource['id'],
                        'ownership_verified': False, 'remove_exit': None,
                        'post_inspect_absent': False,
                        'post_remove_engine_responding': False, 'pass': False})
        return
    prior_remove = next((row for row in reversed(cleanup)
                         if row.get('kind') == resource['kind']
                         and row.get('id') == resource['id']
                         and row.get('ownership_verified') is True
                         and row.get('remove_exit') == 0), None)
    if _exact_absence_claim(resource['kind'], resource['id'], inspected_before):
        engine_responding = (
            prior_remove is not None and _docker_engine_responds(docker))
        passed = prior_remove is not None and engine_responding
        cleanup.append({
            'kind': resource['kind'], 'id': resource['id'],
            'ownership_verified': prior_remove is not None,
            'remove_exit': 0 if prior_remove is not None else None,
            'post_inspect_absent': True,
            'post_remove_engine_responding': engine_responding,
            'prior_remove_reverified': prior_remove is not None,
            'pass': passed,
        })
        if passed:
            resource['active'] = False
        return
    ownership_verified = False
    if inspected_before.returncode == 0:
        try:
            rows = json.loads(inspected_before.stdout)
            item = rows[0] if isinstance(rows, list) and len(rows) == 1 else {}
            labels = (item.get('Config', {}).get('Labels', {})
                      if resource['kind'] == 'container' else item.get('Labels', {}))
            ownership_verified = (item.get('Id') == resource['id']
                                  and labels.get(LABEL) == resource['nonce'])
        except (AttributeError, IndexError, ValueError):
            ownership_verified = False
    if not ownership_verified:
        cleanup.append({'kind': resource['kind'], 'id': resource['id'],
                        'ownership_verified': False, 'remove_exit': None,
                        'post_inspect_absent': False,
                        'post_remove_engine_responding': False, 'pass': False})
        return
    command = ('container', 'rm', '--force', '--volumes', resource['id']) \
        if resource['kind'] == 'container' else ('network', 'rm', resource['id'])
    try:
        removed = docker.run(*command)
    except CheckError:
        removed = None
    try:
        inspected = docker.run(resource['kind'], 'inspect', resource['id'])
    except CheckError:
        inspected = None
    remove_exit = removed.returncode if removed is not None else None
    post_inspect_absent = _exact_absence_claim(
        resource['kind'], resource['id'], inspected)
    post_remove_engine_responding = (
        post_inspect_absent and _docker_engine_responds(docker))
    passed = (remove_exit == 0 and post_inspect_absent
              and post_remove_engine_responding)
    cleanup.append({'kind': resource['kind'], 'id': resource['id'],
                    'ownership_verified': True,
                    'remove_exit': remove_exit,
                    'post_inspect_absent': post_inspect_absent,
                    'post_remove_engine_responding': post_remove_engine_responding,
                    'pass': passed})
    if passed:
        resource['active'] = False


def _labeled_ids(docker, kind, nonce):
    command = ('container', 'ls', '-aq', '--no-trunc') if kind == 'container' \
        else ('network', 'ls', '-q', '--no-trunc')
    try:
        result = docker.run(*command, '--filter', 'label=' + LABEL + '=' + nonce)
    except CheckError:
        return None
    if result.returncode:
        return None
    identifiers = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(set(identifiers)) != len(identifiers) \
            or any(re.fullmatch(r'[0-9a-f]{64}', item) is None for item in identifiers):
        return None
    return identifiers


def _reconcile_labeled_resources(docker, nonce, resources, cleanup):
    discovered = 0
    for kind in ('container', 'network'):
        identifiers = _labeled_ids(docker, kind, nonce)
        if identifiers is None:
            return {'pass': False, 'discovered': discovered}
        for identifier in identifiers:
            resource = next((item for item in resources
                             if item['kind'] == kind and item['id'] == identifier), None)
            if resource is None:
                resource = {'kind': kind, 'id': identifier, 'active': True, 'nonce': nonce}
                resources.append(resource)
                discovered += 1
            else:
                resource['active'] = True
            _remove_resource(docker, resource, cleanup)
        for resource in resources:
            if (resource['kind'] == kind and resource['active']
                    and resource['id'] not in identifiers):
                _remove_resource(docker, resource, cleanup)
    return {'pass': True, 'discovered': discovered}


def _path_entry_absent(path):
    try:
        path.lstat()
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return False


def _latest_cleanup_pass(resources, cleanup):
    latest = {}
    for row in cleanup:
        kind = row.get('kind')
        identifier = row.get('id')
        if kind in {'container', 'network'} and isinstance(identifier, str):
            latest[(kind, identifier)] = row.get('pass') is True
    return all(not resource['active']
               and latest.get((resource['kind'], resource['id'])) is True
               for resource in resources)


def _create_journal_confirmed(create_journal, resources):
    if not isinstance(create_journal, list) or not isinstance(resources, list):
        return False
    journal_keys = []
    for row in create_journal:
        if (not isinstance(row, dict)
                or row.get('kind') not in {'container', 'network'}
                or not isinstance(row.get('name'), str) or not row.get('name')
                or row.get('outcome') != 'exact_id_recorded'
                or re.fullmatch(r'[0-9a-f]{64}', row.get('id', '')) is None):
            return False
        journal_keys.append((row['kind'], row['id'], row['name']))
    resource_keys = []
    for resource in resources:
        if (not isinstance(resource, dict)
                or resource.get('kind') not in {'container', 'network'}
                or not isinstance(resource.get('name'), str) or not resource.get('name')
                or re.fullmatch(r'[0-9a-f]{64}', resource.get('id', '')) is None):
            return False
        resource_keys.append((resource['kind'], resource['id'], resource['name']))
    return (len(journal_keys) == len(set(journal_keys))
            and len(resource_keys) == len(set(resource_keys))
            and set(journal_keys) == set(resource_keys))


def _cleanup_complete(nonce, reconciliations, resources, cleanup, absence,
                      create_journal):
    return (_create_journal_confirmed(create_journal, resources)
            and (not nonce or (reconciliations
                               and reconciliations[-1].get('pass') is True))
            and _latest_cleanup_pass(resources, cleanup)
            and isinstance(absence, dict)
            and absence.get('containers_absent') is True
            and absence.get('networks_absent') is True)


def _arm(docker, image_id, image_role, network, nonce, work, certificates,
         fixture_identities,
         resources, cleanup, create_journal, persist, name, trust_mode, served_chain):
    _require_fixture_identities(certificates, fixture_identities)
    chain = certificates[served_chain]
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(chain['leaf']), str(chain['leaf_key']))
    _require_fixture_identities(certificates, fixture_identities)
    server = _OwnedTLSServer((network['gateway'], 0), context)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    identifier = None
    try:
        base_url = 'https://opencode.ai:' + str(server.server_address[1]) + '/inference/openai/v1'
        arm_root = work / ('arm-' + name)
        workspace = arm_root / 'workspace'
        for relative in ('home', 'config/opencode', 'data', 'cache', 'state', 'tmp', 'project'):
            (workspace / relative).mkdir(parents=True, exist_ok=True)
        (workspace / 'project/README.md').write_text('Owned TLS trust fixture.\n', encoding='utf-8')
        config = arm_root / 'opencode.json'
        _config(config, base_url)
        input_mode = 'absent' if image_role == 'control' else 'valid'
        _require_fixture_identities(certificates, fixture_identities)
        identifier = _container(
            docker, image_id, network, network['gateway'], nonce, name, image_role,
            input_mode,
            workspace, config, certificates['ambient']['ca'], certificates['replacement']['ca'],
            fixture_identities['replacement.ca']['sha256'],
            resources, create_journal, persist,
        )
        _require_fixture_identities(certificates, fixture_identities)
        preflight_before = server.snapshot()
        _start_server_container(docker, identifier)
        version_verified = _version_verified(workspace)
        if not version_verified:
            raise CheckError('opencode_version_mismatch')
        if not _wait_server(docker, identifier):
            raise CheckError('persistent_server_start_failed')
        mounted_before = _mounted_ca_hashes(docker, identifier, image_role)
        expected_mounted = {
            'ambient': fixture_identities['ambient.ca']['sha256'],
        }
        if image_role == 'candidate':
            expected_mounted['replacement'] = (
                fixture_identities['replacement.ca']['sha256'])
        if mounted_before != expected_mounted:
            raise CheckError('mounted_ca_identity_mismatch')
        facts = _native_http_preflight(docker, identifier, base_url)
        preflight_after = server.snapshot()
        preflight_tcp = preflight_after['tcp_connections'] - preflight_before['tcp_connections']
        preflight_http = preflight_after['http_requests'] - preflight_before['http_requests']
        if preflight_tcp != 0 or preflight_http != 0:
            raise CheckError('native_http_preflight_dispatched')
        run = _authenticated_exec(
            docker, identifier,
            'opencode', 'run', '--server', OPENCODE_SERVER_URL,
            '--agent', 'build', '--model', MODEL,
            '--format', 'json', 'Reply with OK only. Do not use tools.', timeout=60,
        )
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            current = server.snapshot()
            if current['http_requests'] or current['tls_failures']:
                break
            time.sleep(.05)
        snapshot = server.snapshot()
        mounted_after = _mounted_ca_hashes(docker, identifier, image_role)
        if mounted_after != mounted_before:
            raise CheckError('mounted_ca_identity_changed')
        _require_fixture_identities(certificates, fixture_identities)
        row = {
            'arm': name, 'case_kind': 'core', 'image_role': image_role,
            'trust_mode': trust_mode, 'served_chain': served_chain,
            'replacement_pair_state': (
                'complete' if image_role == 'candidate' else 'absent'),
            'ambient_ca_sha256': mounted_before['ambient'],
            'replacement_ca_sha256': (
                mounted_before['replacement']
                if image_role == 'candidate' else None),
            'mounted_ca_hashes_stable': True,
            'version_verified': version_verified, 'server_started': True, **facts,
            'preflight_tcp_connections': preflight_tcp,
            'preflight_http_requests': preflight_http,
            'dispatched': True,
            'exit_kind': _exit_kind(run.returncode),
            **snapshot,
        }
        return row
    finally:
        if identifier is not None:
            resource = next(item for item in resources
                            if item['kind'] == 'container' and item['id'] == identifier)
            _remove_resource(docker, resource, cleanup)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _pre_socket_case(docker, candidate_image_id, network, nonce, work, certificates,
                     fixture_identities, exclusive_inputs, resources, cleanup,
                     create_journal, persist,
                     name, input_mode):
    _require_fixture_identities(certificates, fixture_identities)
    chain = certificates['replacement']
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(chain['leaf']), str(chain['leaf_key']))
    _require_fixture_identities(certificates, fixture_identities)
    server = _OwnedTLSServer((network['gateway'], 0), context)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    identifier = None
    try:
        base_url = 'https://opencode.ai:' + str(server.server_address[1]) + '/inference/openai/v1'
        arm_root = work / ('arm-' + name)
        workspace = arm_root / 'workspace'
        for relative in ('home', 'config/opencode', 'data', 'cache', 'state', 'tmp', 'project'):
            (workspace / relative).mkdir(parents=True, exist_ok=True)
        (workspace / 'project/README.md').write_text(
            'Owned invalid replacement-CA fixture.\n', encoding='utf-8')
        config = arm_root / 'opencode.json'
        _config(config, base_url)
        exclusive_input = exclusive_inputs[input_mode]
        _require_fixture_identities(certificates, fixture_identities)
        identifier = _container(
            docker, candidate_image_id, network, network['gateway'], nonce, name,
            'candidate', input_mode, workspace, config, certificates['ambient']['ca'],
            exclusive_input['path'], exclusive_input['sha256'], resources,
            create_journal, persist,
        )
        _require_fixture_identities(certificates, fixture_identities)
        preflight_before = server.snapshot()
        _start_server_container(docker, identifier)
        version_verified = _version_verified(workspace)
        if not version_verified:
            raise CheckError('opencode_version_mismatch')
        server_started = _wait_server(docker, identifier)
        if not server_started:
            state = _container_state(docker, identifier)
            exit_code = state.get('ExitCode')
            exit_kind = _exit_kind(exit_code)
            if state.get('Running') is not False or exit_kind != 'nonzero':
                raise CheckError('candidate_rejection_state_unavailable')
            _require_fixture_identities(certificates, fixture_identities)
            snapshot = server.snapshot()
            return {
                'arm': name,
                'case_kind': 'pre-socket',
                'image_role': 'candidate',
                'input_mode': input_mode,
                'replacement_pair_state': PAIR_STATE[input_mode],
                'version_verified': version_verified,
                'server_started': False,
                'native_http_verified': False,
                'readback_scope': 'persistent-server-authority',
                'preflight_tcp_connections': (
                    snapshot['tcp_connections'] - preflight_before['tcp_connections']),
                'preflight_http_requests': (
                    snapshot['http_requests'] - preflight_before['http_requests']),
                'dispatched': False,
                'failure_stage': 'server-startup',
                'termination_verified': True,
                'exit_kind': exit_kind,
                **snapshot,
            }
        facts = _native_http_preflight(docker, identifier, base_url)
        preflight_after = server.snapshot()
        preflight_tcp = preflight_after['tcp_connections'] - preflight_before['tcp_connections']
        preflight_http = preflight_after['http_requests'] - preflight_before['http_requests']
        if preflight_tcp != 0 or preflight_http != 0:
            raise CheckError('native_http_preflight_dispatched')
        run = _authenticated_exec(
            docker, identifier,
            'opencode', 'run', '--server', OPENCODE_SERVER_URL,
            '--agent', 'build', '--model', MODEL,
            '--format', 'json', 'Reply with OK only. Do not use tools.', timeout=60,
        )
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and not any(server.snapshot().values()):
            time.sleep(.05)
        _require_fixture_identities(certificates, fixture_identities)
        return {
            'arm': name,
            'case_kind': 'pre-socket',
            'image_role': 'candidate',
            'input_mode': input_mode,
            'replacement_pair_state': PAIR_STATE[input_mode],
            'version_verified': version_verified,
            'server_started': True,
            **facts,
            'preflight_tcp_connections': preflight_tcp,
            'preflight_http_requests': preflight_http,
            'dispatched': True,
            'failure_stage': 'same-server-dispatch',
            'termination_verified': _exit_kind(run.returncode) == 'nonzero',
            'exit_kind': _exit_kind(run.returncode),
            **server.snapshot(),
        }
    finally:
        if identifier is not None:
            resource = next(item for item in resources
                            if item['kind'] == 'container' and item['id'] == identifier)
            _remove_resource(docker, resource, cleanup)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _label_absence(docker, nonce):
    try:
        containers = docker.run('container', 'ls', '-aq', '--no-trunc',
                                '--filter', 'label=' + LABEL + '=' + nonce)
        networks = docker.run('network', 'ls', '-q', '--no-trunc',
                              '--filter', 'label=' + LABEL + '=' + nonce)
    except CheckError:
        return {'containers_absent': False, 'networks_absent': False}
    return {'containers_absent': containers.returncode == 0 and not containers.stdout.strip(),
            'networks_absent': networks.returncode == 0 and not networks.stdout.strip()}


def execute(args):
    if args.confirm_owned_only != CONFIRMATION:
        raise CheckError('explicit_owned_confirmation_required')
    if args.confirm_ephemeral_loopback_credential != CONTROL_CREDENTIAL_CONFIRMATION:
        raise CheckError('ephemeral_loopback_credential_confirmation_required')
    if (not re.fullmatch(r'sha256:[0-9a-f]{64}', args.control_image_id)
            or not re.fullmatch(r'sha256:[0-9a-f]{64}', args.candidate_image_id)):
        raise CheckError('exact_image_id_required')
    if args.control_image_id == args.candidate_image_id:
        raise CheckError('separate_control_and_candidate_images_required')
    self_test()
    output = _safe_output(args.output)
    nonce = uuid.uuid4().hex
    work = Path(tempfile.mkdtemp(prefix='t02-exclusive-trust-')).resolve()
    resource_arms = ([name for name, _, _, _ in CORE_ARMS]
                     + [name for name, _ in PRESOCKET_CASES])
    create_journal = []
    receipt = {
        'schema_version': 1,
        'kind': 't02-opencode-exclusive-trust-owned-check',
        'status': 'running',
        'classification': ('owned internal TLS/SSE fixture against exact separate control '
                           'and candidate images; zero external or live provider/model '
                           'service calls'),
        'checks': [], 'arms': [], 'resources': [], 'cleanup': [],
        'create_journal': create_journal,
        'cleanup_recovery': {
            'label': LABEL, 'nonce': nonce,
            'network_name': _network_name(nonce),
            'container_names': [_container_name(nonce, arm) for arm in resource_arms],
        },
        'retained_temporary_workspace': str(work),
        'external_provider_service_calls': 0, 'external_model_service_calls': 0,
    }

    def persist():
        _write_json(output, receipt)

    persist()
    docker = Docker()
    resources = []
    cleanup = receipt['cleanup']
    failure = None
    cleanup_ok = False
    try:
        socket_path = Path('/var/run/docker.sock')
        if not socket_path.exists() or not stat.S_ISSOCK(socket_path.stat().st_mode):
            raise CheckError('local_docker_socket_required')
        receipt['images'] = {
            'control': _inspect_image(docker, args.control_image_id),
            'candidate': _inspect_image(docker, args.candidate_image_id),
        }
        cert_dir = work / 'certificates'
        cert_dir.mkdir(mode=0o700)
        ambient, replacement = _prepare_certificates(cert_dir)
        certificates = {'ambient': ambient, 'replacement': replacement}
        fixture_identities = _fixture_identities(certificates)
        receipt['certificate_fixture'] = {
            'ambient_ca_sha256': fixture_identities['ambient.ca']['sha256'],
            'replacement_ca_sha256': fixture_identities['replacement.ca']['sha256'],
            'ambient_leaf_sha256': fixture_identities['ambient.leaf']['sha256'],
            'replacement_leaf_sha256': fixture_identities['replacement.leaf']['sha256'],
            'ambient_root_serial': str(AMBIENT_ROOT_SERIAL),
            'replacement_root_serial': str(REPLACEMENT_ROOT_SERIAL),
            'ambient_leaf_serial': str(AMBIENT_LEAF_SERIAL),
            'replacement_leaf_serial': str(REPLACEMENT_LEAF_SERIAL),
            'root_serials_distinct': AMBIENT_ROOT_SERIAL != REPLACEMENT_ROOT_SERIAL,
            'leaf_serials_distinct': AMBIENT_LEAF_SERIAL != REPLACEMENT_LEAF_SERIAL,
            'roots_distinct': True,
            'matching_chains_verified': True,
            'cross_chains_rejected': True,
            'private_material_recorded': False,
        }
        network = _network(docker, nonce, resources, create_journal, persist)
        receipt['resources'].append({
            'kind': 'network', 'id': network['id'], 'name': network['name'],
            'internal': True, 'driver': 'bridge'})
        invalid_dir = work / 'invalid-replacement-inputs'
        invalid_dir.mkdir(mode=0o700)
        empty_ca = invalid_dir / 'empty.pem'
        empty_ca.write_bytes(b'')
        empty_ca.chmod(0o600)
        oversized_ca = invalid_dir / 'oversized.pem'
        oversized_ca.write_bytes(b'X' * (MAX_EXCLUSIVE_CA_BYTES + 1))
        oversized_ca.chmod(0o600)
        unreadable_ca = invalid_dir / 'unreadable.pem'
        shutil.copyfile(replacement['ca'], unreadable_ca)
        unreadable_hash = sha256(unreadable_ca)
        unreadable_ca.chmod(0o000)
        missing_ca = invalid_dir / 'missing.pem'
        replacement_hash = fixture_identities['replacement.ca']['sha256']
        exclusive_inputs = {
            'missing-both': {'path': replacement['ca'], 'sha256': replacement_hash},
            'missing-path-env': {'path': replacement['ca'], 'sha256': replacement_hash},
            'missing-hash-env': {'path': replacement['ca'], 'sha256': replacement_hash},
            'malformed-hash': {
                'path': replacement['ca'], 'sha256': MALFORMED_EXCLUSIVE_CA_HASH},
            'wrong-path': {'path': replacement['ca'], 'sha256': replacement_hash},
            'missing-file': {'path': missing_ca, 'sha256': replacement_hash},
            'unreadable': {'path': unreadable_ca, 'sha256': unreadable_hash},
            'empty': {'path': empty_ca, 'sha256': sha256(empty_ca)},
            'oversized': {'path': oversized_ca, 'sha256': sha256(oversized_ca)},
            'hash-mismatch': {
                'path': replacement['ca'],
                'sha256': fixture_identities['ambient.ca']['sha256']},
        }
        receipt['invalid_input_fixture'] = {
            'empty_bytes': empty_ca.stat().st_size,
            'oversized_bytes': oversized_ca.stat().st_size,
            'oversized_limit_bytes': MAX_EXCLUSIVE_CA_BYTES,
            'unreadable_mode': '0000',
            'fixed_path_missing': not missing_ca.exists(),
            'hash_mismatch_uses_distinct_root_hash': True,
            'private_material_recorded': False,
        }
        image_ids = {
            'control': args.control_image_id,
            'candidate': args.candidate_image_id,
        }
        for name, image_role, trust_mode, served_chain in CORE_ARMS:
            row = _arm(docker, image_ids[image_role], image_role, network, nonce,
                       work, certificates, fixture_identities, resources, cleanup,
                       create_journal, persist, name, trust_mode, served_chain)
            receipt['arms'].append(row)
            receipt['resources'].extend(
                {'kind': item['kind'], 'id': item['id'], 'name': item['name']}
                for item in resources
                if item['kind'] == 'container'
                and not any(record['id'] == item['id'] for record in receipt['resources'])
            )
            _write_json(output, receipt)
        for name, input_mode in PRESOCKET_CASES:
            row = _pre_socket_case(
                docker, args.candidate_image_id, network, nonce, work, certificates,
                fixture_identities, exclusive_inputs, resources, cleanup,
                create_journal, persist, name, input_mode,
            )
            receipt['arms'].append(row)
            receipt['resources'].extend(
                {'kind': item['kind'], 'id': item['id'], 'name': item['name']}
                for item in resources
                if item['kind'] == 'container'
                and not any(record['id'] == item['id'] for record in receipt['resources'])
            )
            _write_json(output, receipt)
        _require_fixture_identities(certificates, fixture_identities)
        verdict = evaluate_arms(receipt['arms'], receipt['certificate_fixture'])
        receipt['checks'] = verdict['checks']
        if not verdict['pass']:
            raise CheckError('exclusive_trust_arms_failed')
    except CheckError as error:
        failure = str(error)
    except KeyboardInterrupt:
        failure = 'interrupted'
    except Exception:
        failure = 'unexpected_failure'
    finally:
        for resource in reversed(resources):
            if resource['active']:
                _remove_resource(docker, resource, cleanup)
        nonce_value = nonce
        reconciliations = []
        if nonce_value:
            reconciliations.append(
                _reconcile_labeled_resources(docker, nonce_value, resources, cleanup))
            reconciliations.append(
                _reconcile_labeled_resources(docker, nonce_value, resources, cleanup))
        receipt['label_reconciliation'] = reconciliations
        for item in resources:
            if not any(record.get('kind') == item['kind'] and record.get('id') == item['id']
                       for record in receipt['resources']):
                receipt['resources'].append({
                    'kind': item['kind'], 'id': item['id'],
                    'name': item.get('name')})
        absence = _label_absence(docker, nonce_value) if nonce_value else {
            'containers_absent': True, 'networks_absent': True}
        receipt['label_cleanup'] = absence
        cleanup_ok = _cleanup_complete(
            nonce_value, reconciliations, resources, cleanup, absence,
            create_journal)
        receipt['temporary_removed'] = False
        if cleanup_ok:
            try:
                shutil.rmtree(work)
            except OSError:
                pass
            receipt['temporary_removed'] = _path_entry_absent(work)
        if receipt['temporary_removed']:
            receipt.pop('retained_temporary_workspace', None)
        else:
            receipt['retained_temporary_workspace'] = str(work)
        if failure is None and (not cleanup_ok or not receipt['temporary_removed']):
            failure = 'cleanup_failed'
        receipt['status'] = 'pass' if failure is None else 'failed'
        if failure is not None:
            receipt['error_code'] = failure if re.fullmatch(r'[a-z][a-z0-9_]{0,79}', failure) else 'failure'
        _write_json(output, receipt)
    if failure is not None:
        raise CheckError(failure)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true',
                        help='run only the pure receipt evaluator self-test')
    parser.add_argument('--output', type=Path,
                        help='new directory for the sanitized receipt')
    parser.add_argument('--control-image-id',
                        help='exact local unpatched control sha256 image ID')
    parser.add_argument('--candidate-image-id',
                        help='exact local patched candidate sha256 image ID')
    parser.add_argument('--confirm-owned-only',
                        help='exact explicit-confirmation token')
    parser.add_argument('--confirm-ephemeral-loopback-credential',
                        help='exact separate authorization for a one-run loopback password')
    args = parser.parse_args()
    runtime_values = (args.output, args.control_image_id, args.candidate_image_id,
                      args.confirm_owned_only, args.confirm_ephemeral_loopback_credential)
    if args.self_test:
        if any(value is not None for value in runtime_values):
            parser.error('self_test_runtime_arguments_refused')
        self_test()
        print('PASS: pure exclusive trust receipt evaluator self-test')
        return 0
    if args.output is None:
        parser.error('the following arguments are required: --output')
    if args.control_image_id is None:
        parser.error('the following arguments are required: --control-image-id')
    if args.candidate_image_id is None:
        parser.error('the following arguments are required: --candidate-image-id')
    if args.confirm_owned_only is None:
        parser.error('the following arguments are required: --confirm-owned-only')
    if args.confirm_ephemeral_loopback_credential is None:
        parser.error('the following arguments are required: '
                     '--confirm-ephemeral-loopback-credential')
    try:
        output = execute(args)
    except CheckError as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        return 1
    print('PASS: owned OpenCode exclusive trust check; receipt at ' + str(output / 'result.json'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
