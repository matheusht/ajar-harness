#!/usr/bin/env python3
"""Qualify exact OpenCode control and candidate images with owned TLS chains.

This checker is dormant unless an operator supplies the exact confirmation token.
It never builds or pulls an image. The control is an exact unpatched OpenCode
v2.0.32 image. The candidate is a separate reviewed build whose native HTTP
request executor requires a fixed ``OPENCODE_EXCLUSIVE_CA_FILE`` plus its exact
``OPENCODE_EXCLUSIVE_CA_SHA256``. It passes the bounded, verified bytes as Bun
``fetch(..., {tls: {ca}})`` input. The three core arms define the future proof.
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
import socket
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
ARM_MARKER_HEADER = 'X-LRH-Arm-Marker'
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
REJECTION_PREFIX = 'OPENCODE_EXCLUSIVE_CA_REJECT:'
MAX_STRUCTURED_OUTPUT_BYTES = 64 * 1024
DISPATCH_QUIET_SECONDS = 2.0
DISPATCH_QUIET_TIMEOUT_SECONDS = 8.0
DEFAULT_COMMAND_TIMEOUT_SECONDS = 60
NEGATIVE_COMMAND_TIMEOUT_SECONDS = 240
NEGATIVE_TRANSPORT_ATTEMPTS = 11

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
    'OPENCODE_API_KEY', 'OPENCODE_CONFIG', 'OPENCODE_CONFIG_CONTENT',
    'OPENCODE_CONFIG_DIR', 'OPENCODE_CLI_CONFIG_CONTENT', 'OPENCODE_DB',
    'OPENCODE_MODELS_PATH', 'OPENCODE_MODELS_URL', 'OPENCODE_SIMULATE',
    'OPENCODE_TEST_HOME', 'OPENCODE_DISABLE_PROJECT_CONFIG',
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
FIXED_RUNTIME_ENV = {
    'HOME': '/workspace/home',
    'XDG_CONFIG_HOME': '/workspace/config',
    'XDG_DATA_HOME': '/workspace/data',
    'XDG_CACHE_HOME': '/workspace/cache',
    'XDG_STATE_HOME': '/workspace/state',
    'TMPDIR': '/workspace/tmp',
    'NO_COLOR': '1',
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
REJECTION_CODE = {
    'missing-both': 'path_required',
    'missing-path-env': 'path_required',
    'missing-hash-env': 'digest_required',
    'malformed-hash': 'digest_format',
    'wrong-path': 'path_fixed',
    'missing-file': 'open_failed',
    'unreadable': 'open_failed',
    'empty': 'size_invalid',
    'oversized': 'size_invalid',
    'hash-mismatch': 'digest_mismatch',
}
OBSERVATION_KEYS = (
    'tcp_connections', 'tls_handshakes', 'tls_failures', 'http_requests',
    'expected_path_requests', 'arm_header_requests', 'dispatch_marker_requests',
    'unexpected_http_requests',
)
NATIVE_FACT_KEYS = frozenset({
    'native_http_verified', 'provider_package', 'effective_model_package',
    'provider_transport', 'model_transport_override_absent',
    'transport_authority', 'provider_base_url_verified',
    'model_base_url_verified', 'base_url_verified',
    'provider_request_headers_verified', 'model_request_headers_verified',
    'request_marker_verified', 'request_header_authority',
    'source_boundary_verified', 'preflight_method_scope',
    'source_document_verified', 'readback_scope',
})
OBSERVATION_ROW_KEYS = frozenset(OBSERVATION_KEYS) | frozenset(
    prefix + key
    for prefix in ('preflight_', 'dispatch_baseline_')
    for key in OBSERVATION_KEYS
)
CORE_ROW_KEYS = frozenset({
    'arm', 'case_kind', 'image_role', 'trust_mode', 'served_chain',
    'replacement_pair_state', 'ambient_ca_sha256', 'replacement_ca_sha256',
    'mounted_ca_hashes_stable', 'baseline_zero_verified',
    'dispatch_network_activated', 'preflight_network_mode',
    'responder_quiescence_verified', 'responder_sealed',
    'container_removed_before_responder_seal', 'quiescence_window_ms',
    'command_timeout_seconds', 'expected_transport_attempts',
    'version_verified', 'server_started', 'dispatched', 'exit_code',
    'exit_kind',
}) | NATIVE_FACT_KEYS | OBSERVATION_ROW_KEYS
TRANSPORT_PROOF_KEYS = frozenset({
    'structured_transport_verified', 'transport_error_type',
    'transport_session_id_present', 'transport_step_start_count',
    'transport_terminal_error_count', 'transport_trace_event_count',
})
PRESOCKET_ROW_KEYS = frozenset({
    'arm', 'case_kind', 'image_role', 'input_mode', 'replacement_pair_state',
    'version_verified', 'server_started', 'baseline_zero_verified',
    'dispatch_network_activated', 'preflight_network_mode',
    'responder_quiescence_verified', 'responder_sealed',
    'container_removed_before_responder_seal', 'quiescence_window_ms',
    'command_timeout_seconds', 'expected_transport_attempts', 'dispatched',
    'failure_stage', 'termination_verified', 'server_alive_after_rejection',
    'native_readback_stable', 'structured_rejection_verified',
    'rejection_code', 'session_id_present', 'structured_step_start_count',
    'structured_terminal_error_count', 'structured_event_count', 'exit_code',
    'exit_kind',
}) | NATIVE_FACT_KEYS | OBSERVATION_ROW_KEYS
CERTIFICATE_FIXTURE_KEYS = frozenset({
    'ambient_ca_sha256', 'replacement_ca_sha256',
    'ambient_leaf_sha256', 'replacement_leaf_sha256',
    'ambient_root_serial', 'replacement_root_serial',
    'ambient_leaf_serial', 'replacement_leaf_serial',
    'root_serials_distinct', 'leaf_serials_distinct', 'roots_distinct',
    'matching_chains_verified', 'cross_chains_rejected',
    'private_material_recorded',
})


class CheckError(RuntimeError):
    """A fixed, receipt-safe failure code."""


def _count(value):
    return type(value) is int and value >= 0


def _exact_count(row, key, expected):
    value = row.get(key)
    return _count(value) and value == expected


def _certificate_fixture_valid(fixture):
    if (not isinstance(fixture, dict)
            or set(fixture) != CERTIFICATE_FIXTURE_KEYS):
        return False
    hashes = (
        fixture['ambient_ca_sha256'], fixture['replacement_ca_sha256'],
        fixture['ambient_leaf_sha256'], fixture['replacement_leaf_sha256'],
    )
    return (
        all(isinstance(value, str)
            and re.fullmatch(r'[0-9a-f]{64}', value) is not None
            for value in hashes)
        and len(set(hashes)) == len(hashes)
        and fixture['ambient_root_serial'] == str(AMBIENT_ROOT_SERIAL)
        and fixture['replacement_root_serial'] == str(REPLACEMENT_ROOT_SERIAL)
        and fixture['ambient_leaf_serial'] == str(AMBIENT_LEAF_SERIAL)
        and fixture['replacement_leaf_serial'] == str(REPLACEMENT_LEAF_SERIAL)
        and fixture['root_serials_distinct'] is True
        and fixture['leaf_serials_distinct'] is True
        and fixture['roots_distinct'] is True
        and fixture['matching_chains_verified'] is True
        and fixture['cross_chains_rejected'] is True
        and fixture['private_material_recorded'] is False
    )


def _observation_delta(after, before):
    if (not isinstance(after, dict) or not isinstance(before, dict)
            or set(after) != set(OBSERVATION_KEYS)
            or set(before) != set(OBSERVATION_KEYS)
            or not all(_count(after[key]) and _count(before[key])
                       and after[key] >= before[key]
                       for key in OBSERVATION_KEYS)):
        return None
    return {key: after[key] - before[key] for key in OBSERVATION_KEYS}


def _observation_is_zero(snapshot):
    return (isinstance(snapshot, dict) and set(snapshot) == set(OBSERVATION_KEYS)
            and all(snapshot[key] == 0 for key in OBSERVATION_KEYS))


def _prefixed_observation(prefix, snapshot):
    if (not isinstance(prefix, str) or not prefix
            or not isinstance(snapshot, dict)
            or set(snapshot) != set(OBSERVATION_KEYS)
            or not all(_count(snapshot[key]) for key in OBSERVATION_KEYS)):
        raise CheckError('owned_responder_observation_invalid')
    return {prefix + key: snapshot[key] for key in OBSERVATION_KEYS}


def _prefixed_observation_is_zero(row, prefix):
    return all(_count(row.get(prefix + key)) and row[prefix + key] == 0
               for key in OBSERVATION_KEYS)


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
            and row.get('provider_request_headers_verified') is True
            and row.get('model_request_headers_verified') is True
            and row.get('request_marker_verified') is True
            and row.get('request_header_authority') == 'provider.headers+model.headers'
            and row.get('source_boundary_verified') is True
            and row.get('preflight_method_scope') == (
                'openapi.get+server.info+model.list+provider.list+config.get')
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
    fixture_valid = _certificate_fixture_valid(fixture)
    add('closed CA fixture schema is exact and valid', fixture_valid)
    names = [row.get('arm') for row in rows] if valid_rows else []
    names_valid = valid_rows and all(isinstance(name, str) for name in names)
    expected_names = ([name for name, _, _, _ in CORE_ARMS]
                      + [name for name, _ in PRESOCKET_CASES])
    add('exact arm identities', names_valid and sorted(names) == sorted(expected_names)
        and len(set(names)) == len(expected_names))
    by_name = {row['arm']: row for row in rows} if names_valid else {}

    for name, image_role, trust_mode, served_chain in CORE_ARMS:
        row = by_name.get(name, {})
        counts_valid = (all(_count(row.get(key)) for key in OBSERVATION_KEYS)
                        and all(_count(row.get('preflight_' + key))
                                for key in OBSERVATION_KEYS)
                        and all(_count(row.get('dispatch_baseline_' + key))
                                for key in OBSERVATION_KEYS))
        expected_row_keys = (CORE_ROW_KEYS | TRANSPORT_PROOF_KEYS
                             if name == 'ambient-rejected' else CORE_ROW_KEYS)
        baseline_zero = (_prefixed_observation_is_zero(row, 'preflight_')
                         and _prefixed_observation_is_zero(
                             row, 'dispatch_baseline_'))
        add(name + ' observation schema', counts_valid
            and set(row) == expected_row_keys
            and row.get('case_kind') == 'core'
            and row.get('image_role') == image_role
            and row.get('trust_mode') == trust_mode
            and row.get('served_chain') == served_chain
            and row.get('version_verified') is True
            and row.get('server_started') is True
            and row.get('preflight_network_mode') == 'none'
            and row.get('dispatch_network_activated') is True
            and type(row.get('exit_code')) is int
            and baseline_zero
            and row.get('baseline_zero_verified') is baseline_zero
            and row.get('responder_quiescence_verified') is True
            and row.get('responder_sealed') is True
            and row.get('container_removed_before_responder_seal') is True
            and _exact_count(row, 'quiescence_window_ms', int(
                DISPATCH_QUIET_SECONDS * 1000))
            and _exact_count(row, 'command_timeout_seconds', (
                NEGATIVE_COMMAND_TIMEOUT_SECONDS
                if name == 'ambient-rejected' else DEFAULT_COMMAND_TIMEOUT_SECONDS))
            and _exact_count(row, 'expected_transport_attempts', (
                NEGATIVE_TRANSPORT_ATTEMPTS
                if name == 'ambient-rejected' else 1))
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
            and _prefixed_observation_is_zero(row, 'preflight_'))
        add(name + ' dispatched only after preflight', row.get('dispatched') is True)

    for name in ('ambient-control', 'replacement-positive'):
        row = by_name.get(name, {})
        add(name + ' owned TLS and HTTP succeeded', row.get('exit_code') == 0
            and row.get('exit_kind') == 'zero'
            and row.get('tcp_connections') == 1
            and row.get('tls_handshakes') == 1
            and row.get('tls_failures') == 0
            and row.get('http_requests') == 1
            and row.get('expected_path_requests') == row.get('http_requests')
            and row.get('arm_header_requests') == row.get('http_requests')
            and row.get('dispatch_marker_requests') == row.get('http_requests')
            and row.get('unexpected_http_requests') == 0)

    denied = by_name.get('ambient-rejected', {})
    add('ambient-only chain rejected by replacement store', denied.get('exit_code') == 1
        and denied.get('exit_kind') == 'nonzero'
        and denied.get('structured_transport_verified') is True
        and denied.get('transport_error_type') == 'provider.transport'
        and denied.get('transport_session_id_present') is True
        and _count(denied.get('transport_step_start_count'))
        and denied.get('transport_step_start_count') <= NEGATIVE_TRANSPORT_ATTEMPTS
        and _exact_count(denied, 'transport_terminal_error_count', 1)
        and _count(denied.get('transport_trace_event_count'))
        and denied['transport_trace_event_count'] == (
            denied['transport_step_start_count'] + 1)
        and denied.get('tcp_connections') == NEGATIVE_TRANSPORT_ATTEMPTS
        and denied.get('tls_handshakes') == 0
        and denied.get('tls_failures') == NEGATIVE_TRANSPORT_ATTEMPTS
        and denied.get('http_requests') == 0
        and denied.get('expected_path_requests') == 0
        and denied.get('arm_header_requests') == 0
        and denied.get('dispatch_marker_requests') == 0
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
        counts_valid = (all(_count(row.get(key)) for key in OBSERVATION_KEYS)
                        and all(_count(row.get('preflight_' + key))
                                for key in OBSERVATION_KEYS)
                        and all(_count(row.get('dispatch_baseline_' + key))
                                for key in OBSERVATION_KEYS))
        baseline_zero = (_prefixed_observation_is_zero(row, 'preflight_')
                         and _prefixed_observation_is_zero(
                             row, 'dispatch_baseline_'))
        authority_valid = (
            set(row) == PRESOCKET_ROW_KEYS
            and counts_valid
            and row.get('server_started') is True
            and row.get('preflight_network_mode') == 'none'
            and row.get('dispatch_network_activated') is True
            and type(row.get('exit_code')) is int
            and baseline_zero
            and row.get('baseline_zero_verified') is baseline_zero
            and row.get('responder_quiescence_verified') is True
            and row.get('responder_sealed') is True
            and row.get('container_removed_before_responder_seal') is True
            and _exact_count(row, 'quiescence_window_ms', int(
                DISPATCH_QUIET_SECONDS * 1000))
            and _exact_count(row, 'command_timeout_seconds',
                             DEFAULT_COMMAND_TIMEOUT_SECONDS)
            and _exact_count(row, 'expected_transport_attempts', 0)
            and _native_facts_verified(row)
            and _prefixed_observation_is_zero(row, 'preflight_')
            and row.get('dispatched') is True
            and row.get('failure_stage') == 'same-server-dispatch'
            and row.get('structured_rejection_verified') is True
            and row.get('rejection_code') == REJECTION_CODE[input_mode]
            and row.get('session_id_present') is True
            and _count(row.get('structured_step_start_count'))
            and row.get('structured_step_start_count') <= 1
            and _exact_count(row, 'structured_terminal_error_count', 1)
            and _count(row.get('structured_event_count'))
            and row['structured_event_count'] == (
                row['structured_step_start_count'] + 1)
            and row.get('server_alive_after_rejection') is True
            and row.get('native_readback_stable') is True
        )
        add(name + ' candidate input rejected before socket',
            row.get('case_kind') == 'pre-socket'
            and row.get('image_role') == 'candidate'
            and row.get('input_mode') == input_mode
            and row.get('version_verified') is True
            and row.get('replacement_pair_state') == PAIR_STATE[input_mode]
            and authority_valid
            and row.get('termination_verified') is True
            and row.get('exit_code') == 1
            and row.get('exit_kind') == 'nonzero'
            and counts_valid
            and all(row.get(key) == 0 for key in (
                'tcp_connections', 'tls_handshakes', 'tls_failures', 'http_requests',
                'expected_path_requests', 'arm_header_requests',
                'dispatch_marker_requests',
                'unexpected_http_requests',
            )))
    return {'pass': bool(checks) and all(check['pass'] for check in checks), 'checks': checks}


def self_test():
    """Exercise the pure evaluator without Docker, sockets, or subprocesses."""
    if (not all(_critical_name(name) for name in MUST_BE_ABSENT_ENV)
            or not all(_critical_name(name) for name in FIXED_RUNTIME_ENV)
            or any(_image_forbidden_name(name) for name in FIXED_RUNTIME_ENV)
            or not all(_image_forbidden_name(name) for name in MUST_BE_ABSENT_ENV)
            or _critical_name('LRH_BENIGN_PUBLIC_VALUE')):
        raise RuntimeError('critical_environment_fixture_failed')
    raw_config = _config_document(
        'https://opencode.ai:4443/inference/openai/v1', 'lrh-' + 'a' * 32 + '-fixture',
        normalized=False)
    normalized_config = _config_document(
        'https://opencode.ai:4443/inference/openai/v1', 'lrh-' + 'a' * 32 + '-fixture',
        normalized=True)
    if (set(raw_config) != set(normalized_config)
            or raw_config.get('model') != MODEL
            or normalized_config.get('model') != {
                'providerID': 'opencode', 'model': MODEL_ID}
            or 'mcp' in raw_config or 'mcp' in normalized_config):
        raise RuntimeError('normalized_config_fixture_failed')
    if len({AMBIENT_ROOT_SERIAL, REPLACEMENT_ROOT_SERIAL,
            AMBIENT_LEAF_SERIAL, REPLACEMENT_LEAF_SERIAL}) != 4:
        raise RuntimeError('certificate_serial_fixture_failed')
    exit_cases = ((0, 'zero'), (1, 'nonzero'), (124, 'nonzero'),
                  (-9, 'unknown'), (125, 'unknown'), (126, 'unknown'),
                  (127, 'unknown'), (137, 'unknown'), (255, 'unknown'),
                  (None, 'unknown'), (True, 'unknown'))
    if any(_exit_kind(code) != expected for code, expected in exit_cases):
        raise RuntimeError('exit_classification_fixture_failed')
    if (_json_scalar_count({'messages': [{'content': 'dispatch'}]}, 'dispatch') != 1
            or _json_scalar_count(['dispatch', 'dispatch'], 'dispatch') != 2
            or _json_scalar_count({'dispatch': 'other'}, 'dispatch') != 0):
        raise RuntimeError('dispatch_marker_fixture_failed')
    dispatch_markers = {_new_dispatch_prompt('fixture') for _item in range(2)}
    if (len(dispatch_markers) != 2
            or any(re.fullmatch(r'lrh-dispatch-[0-9a-f]{32}-fixture', marker) is None
                   for marker in dispatch_markers)):
        raise RuntimeError('dispatch_marker_uniqueness_fixture_failed')
    for system_exit in (SystemExit(), SystemExit(0), SystemExit(None),
                        SystemExit('unpublished-payload')):
        try:
            _raise_unhandled(system_exit)
        except CheckError as error:
            if str(error) != 'execution_aborted':
                raise
        else:
            raise RuntimeError('system_exit_zero_fixture_failed')
    zero_observation = {key: 0 for key in OBSERVATION_KEYS}
    final_observation = dict(zero_observation, tcp_connections=1,
                             tls_handshakes=1, http_requests=1,
                             expected_path_requests=1,
                             arm_header_requests=1,
                             dispatch_marker_requests=1)
    if (not _observation_is_zero(zero_observation)
            or _observation_is_zero(final_observation)
            or _observation_delta(final_observation, zero_observation) != final_observation
            or _observation_delta(zero_observation, final_observation) is not None):
        raise RuntimeError('observation_delta_fixture_failed')
    fixture = {
        'ambient_ca_sha256': 'a' * 64,
        'replacement_ca_sha256': 'b' * 64,
        'ambient_leaf_sha256': 'c' * 64,
        'replacement_leaf_sha256': 'd' * 64,
        'ambient_root_serial': str(AMBIENT_ROOT_SERIAL),
        'replacement_root_serial': str(REPLACEMENT_ROOT_SERIAL),
        'ambient_leaf_serial': str(AMBIENT_LEAF_SERIAL),
        'replacement_leaf_serial': str(REPLACEMENT_LEAF_SERIAL),
        'root_serials_distinct': True,
        'leaf_serials_distinct': True,
        'roots_distinct': True,
        'matching_chains_verified': True,
        'cross_chains_rejected': True,
        'private_material_recorded': False,
    }
    base = {
        'version_verified': True,
        'server_started': True,
        'preflight_network_mode': 'none',
        'dispatch_network_activated': True,
        'native_http_verified': True,
        'provider_package': NATIVE_PACKAGE,
        'effective_model_package': NATIVE_PACKAGE,
        'provider_transport': 'http',
        'model_transport_override_absent': True,
        'transport_authority': 'provider.settings',
        'provider_base_url_verified': True,
        'model_base_url_verified': True,
        'base_url_verified': True,
        'provider_request_headers_verified': True,
        'model_request_headers_verified': True,
        'request_marker_verified': True,
        'request_header_authority': 'provider.headers+model.headers',
        'source_boundary_verified': True,
        'preflight_method_scope': (
            'openapi.get+server.info+model.list+provider.list+config.get'),
        'source_document_verified': True,
        'readback_scope': 'persistent-server-authority',
        'mounted_ca_hashes_stable': True,
        'baseline_zero_verified': True,
        'responder_quiescence_verified': True,
        'responder_sealed': True,
        'container_removed_before_responder_seal': True,
        'quiescence_window_ms': int(DISPATCH_QUIET_SECONDS * 1000),
        'command_timeout_seconds': DEFAULT_COMMAND_TIMEOUT_SECONDS,
        'expected_transport_attempts': 1,
        **_prefixed_observation('preflight_', zero_observation),
        **_prefixed_observation('dispatch_baseline_', zero_observation),
        'dispatched': True,
        'tcp_connections': 1,
        'tls_handshakes': 1,
        'tls_failures': 0,
        'http_requests': 1,
        'expected_path_requests': 1,
        'arm_header_requests': 1,
        'dispatch_marker_requests': 1,
        'unexpected_http_requests': 0,
        'exit_code': 0,
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
            row.update(exit_kind='nonzero',
                       exit_code=1,
                       structured_transport_verified=True,
                       transport_error_type='provider.transport',
                       transport_session_id_present=True,
                       transport_step_start_count=NEGATIVE_TRANSPORT_ATTEMPTS,
                       transport_terminal_error_count=1,
                       transport_trace_event_count=NEGATIVE_TRANSPORT_ATTEMPTS + 1,
                       command_timeout_seconds=NEGATIVE_COMMAND_TIMEOUT_SECONDS,
                       expected_transport_attempts=NEGATIVE_TRANSPORT_ATTEMPTS,
                       tcp_connections=NEGATIVE_TRANSPORT_ATTEMPTS,
                       tls_handshakes=0,
                       tls_failures=NEGATIVE_TRANSPORT_ATTEMPTS,
                       http_requests=0, expected_path_requests=0,
                       arm_header_requests=0, dispatch_marker_requests=0)
        rows.append(row)
    for name, input_mode in PRESOCKET_CASES:
        row = {
            'arm': name,
            'case_kind': 'pre-socket',
            'image_role': 'candidate',
            'input_mode': input_mode,
            'version_verified': True,
            'replacement_pair_state': PAIR_STATE[input_mode],
            **base,
            'exit_code': 1,
            'exit_kind': 'nonzero',
            'termination_verified': True,
            'failure_stage': 'same-server-dispatch',
            'structured_rejection_verified': True,
            'rejection_code': REJECTION_CODE[input_mode],
            'session_id_present': True,
            'structured_step_start_count': 1,
            'structured_terminal_error_count': 1,
            'structured_event_count': 2,
            'server_alive_after_rejection': True,
            'native_readback_stable': True,
            'expected_transport_attempts': 0,
            'tcp_connections': 0,
            'tls_handshakes': 0,
            'tls_failures': 0,
            'http_requests': 0,
            'expected_path_requests': 0,
            'arm_header_requests': 0,
            'dispatch_marker_requests': 0,
            'unexpected_http_requests': 0,
        }
        row.pop('mounted_ca_hashes_stable')
        rows.append(row)
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
        (1, 'provider_request_headers_verified', False),
        (1, 'model_request_headers_verified', False),
        (1, 'request_marker_verified', False),
        (1, 'request_header_authority', 'provider.settings.headers'),
        (1, 'source_boundary_verified', False),
        (1, 'preflight_method_scope', 'provider.list+model.list'),
        (2, 'preflight_http_requests', 1),
        (2, 'preflight_tls_failures', 1),
        (2, 'dispatch_baseline_tcp_connections', 1),
        (2, 'dispatch_network_activated', False),
        (2, 'preflight_network_mode', 'owned-bridge'),
        (2, 'responder_quiescence_verified', False),
        (2, 'responder_sealed', False),
        (2, 'container_removed_before_responder_seal', False),
        (2, 'quiescence_window_ms', 0),
        (2, 'command_timeout_seconds', DEFAULT_COMMAND_TIMEOUT_SECONDS),
        (2, 'expected_transport_attempts', 1),
        (2, 'dispatched', False),
        (2, 'tcp_connections', 0),
        (2, 'tls_failures', 0),
        (2, 'http_requests', 1),
        (1, 'dispatch_marker_requests', 0),
        (1, 'arm_header_requests', 0),
        (2, 'dispatch_marker_requests', 1),
        (2, 'exit_kind', 'zero'),
        (2, 'exit_code', 0),
        (2, 'exit_kind', 'unknown'),
        (2, 'structured_transport_verified', False),
        (2, 'transport_error_type', 'unknown'),
        (2, 'transport_session_id_present', False),
        (2, 'transport_step_start_count', NEGATIVE_TRANSPORT_ATTEMPTS + 1),
        (2, 'transport_terminal_error_count', 0),
        (2, 'transport_terminal_error_count', True),
        (2, 'transport_trace_event_count', NEGATIVE_TRANSPORT_ATTEMPTS),
        (2, 'transport_trace_event_count', True),
        (1, 'ambient_ca_sha256', 'c' * 64),
        (2, 'replacement_ca_sha256', 'c' * 64),
        (1, 'mounted_ca_hashes_stable', False),
        (0, 'image_role', 'candidate'),
        (1, 'image_role', 'control'),
        (3, 'image_role', 'control'),
        (3, 'server_started', False),
        (3, 'baseline_zero_verified', False),
        (3, 'dispatched', False),
        (3, 'preflight_tcp_connections', 1),
        (3, 'replacement_pair_state', 'complete'),
        (3, 'structured_rejection_verified', False),
        (3, 'rejection_code', 'digest_required'),
        (3, 'session_id_present', False),
        (3, 'structured_step_start_count', 2),
        (3, 'structured_terminal_error_count', 0),
        (3, 'structured_terminal_error_count', True),
        (3, 'structured_event_count', 1),
        (3, 'structured_event_count', True),
        (3, 'server_alive_after_rejection', False),
        (3, 'native_readback_stable', False),
        (3, 'expected_transport_attempts', 1),
        (3, 'expected_transport_attempts', True),
        (3, 'failure_stage', 'server-startup'),
        (4, 'replacement_pair_state', 'absent'),
        (5, 'replacement_pair_state', 'complete'),
        (6, 'replacement_pair_state', 'complete'),
        (7, 'input_mode', 'missing-both'),
        (5, 'tcp_connections', 1),
        (8, 'exit_kind', 'zero'),
        (8, 'exit_code', 0),
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
    for index, key in ((0, 'expected_transport_attempts'),
                       (0, 'command_timeout_seconds')):
        changed = copy.deepcopy(rows)
        changed[index][key] = True
        if evaluate_arms(changed, fixture)['pass']:
            raise RuntimeError('evaluator_boolean_count_fixture_failed')
    changed = copy.deepcopy(rows)
    changed[0]['raw_provider_log'] = 'must-not-be-retained'
    if evaluate_arms(changed, fixture)['pass']:
        raise RuntimeError('evaluator_unknown_field_fixture_failed')
    for malformed_name in (None, 7, []):
        changed = copy.deepcopy(rows)
        changed[0]['arm'] = malformed_name
        if evaluate_arms(changed, fixture)['pass']:
            raise RuntimeError('evaluator_malformed_arm_fixture_failed')
    for malformed_fixture in (
            None,
            {'ambient_ca_sha256': None,
             'replacement_ca_sha256': fixture['replacement_ca_sha256']},
            {'ambient_ca_sha256': fixture['ambient_ca_sha256'],
             'replacement_ca_sha256': []},
    ):
        if evaluate_arms(rows, malformed_fixture)['pass']:
            raise RuntimeError('evaluator_malformed_hash_fixture_failed')
    if evaluate_arms(rows[:-1], fixture)['pass']:
        raise RuntimeError('evaluator_missing_arm_failed')
    changed_fixture = dict(fixture, replacement_ca_sha256=fixture['ambient_ca_sha256'])
    if evaluate_arms(rows, changed_fixture)['pass']:
        raise RuntimeError('evaluator_fixture_identity_failed')
    invalid_fixture_values = {
        'ambient_ca_sha256': None,
        'replacement_ca_sha256': 'e' * 63,
        'ambient_leaf_sha256': fixture['ambient_ca_sha256'],
        'replacement_leaf_sha256': [],
        'ambient_root_serial': AMBIENT_ROOT_SERIAL,
        'replacement_root_serial': '0',
        'ambient_leaf_serial': None,
        'replacement_leaf_serial': str(REPLACEMENT_LEAF_SERIAL + 1),
        'root_serials_distinct': False,
        'leaf_serials_distinct': False,
        'roots_distinct': False,
        'matching_chains_verified': False,
        'cross_chains_rejected': False,
        'private_material_recorded': True,
    }
    for key, value in invalid_fixture_values.items():
        changed_fixture = dict(fixture, **{key: value})
        if evaluate_arms(rows, changed_fixture)['pass']:
            raise RuntimeError('evaluator_fixture_schema_failed')
    changed_fixture = dict(fixture, raw_provider_log='must-not-be-retained')
    if evaluate_arms(rows, changed_fixture)['pass']:
        raise RuntimeError('evaluator_fixture_unknown_field_failed')
    session_id = 'ses_01TESTFIXTURE'

    def step_start(session=session_id, *, part_session=None, message='msg_01TEST',
                   part_id='prt_01TEST'):
        return {
            'type': 'step_start', 'timestamp': 1, 'sessionID': session,
            'part': {
                'id': part_id,
                'sessionID': session if part_session is None else part_session,
                'messageID': message,
                'type': 'step-start',
            },
        }

    def rejection_result(code, *, returncode=1, stderr='', session=session_id,
                         event_type='error', message_prefix='', steps=1,
                         error_type='unknown', extra_error=None):
        events = [step_start(session, part_id='prt_' + str(index + 1))
                  for index in range(steps)]
        error = {
            'type': error_type,
            'message': message_prefix + REJECTION_PREFIX + code,
        }
        if extra_error:
            error.update(extra_error)
        events.append({
            'type': event_type, 'timestamp': 2, 'sessionID': session,
            'error': error,
        })
        return subprocess.CompletedProcess(
            [], returncode,
            '\n'.join(json.dumps(event, separators=(',', ':')) for event in events) + '\n',
            stderr,
        )

    for input_mode, code in REJECTION_CODE.items():
        proof = _structured_rejection(rejection_result(code), input_mode)
        if proof != {
                'structured_rejection_verified': True,
                'rejection_code': code,
                'session_id_present': True,
                'structured_step_start_count': 1,
                'structured_terminal_error_count': 1,
                'structured_event_count': 2}:
            raise RuntimeError('structured_rejection_fixture_failed')
    projected_rejection = _structured_rejection(
        rejection_result('path_required', steps=0), 'missing-both')
    if projected_rejection != {
            'structured_rejection_verified': True,
            'rejection_code': 'path_required',
            'session_id_present': True,
            'structured_step_start_count': 0,
            'structured_terminal_error_count': 1,
            'structured_event_count': 1}:
        raise RuntimeError('structured_projected_rejection_fixture_failed')
    ambiguous_rejections = (
        rejection_result('path_required', returncode=2),
        rejection_result('path_required', stderr='warning'),
        rejection_result('path_required', session=''),
        rejection_result('path_required', steps=2),
        rejection_result('path_required', extra_error={'status': 500}),
        rejection_result('digest_required'),
        rejection_result('path_required', event_type='text'),
        rejection_result('path_required', message_prefix='request failed: '),
        subprocess.CompletedProcess([], 1, '{"type":"error"}\n', ''),
        subprocess.CompletedProcess([], 1, '', ''),
    )
    if any(_structured_rejection(result, 'missing-both') is not None
           for result in ambiguous_rejections):
        raise RuntimeError('structured_rejection_ambiguity_fixture_failed')
    transport_events = [
        step_start(part_id='prt_' + str(index + 1))
        for index in range(NEGATIVE_TRANSPORT_ATTEMPTS)
    ]
    transport_events.append({
        'type': 'error', 'timestamp': 2, 'sessionID': session_id,
        'error': {'type': 'provider.transport', 'message': 'TLS certificate rejected'},
    })

    def transport_result(events=transport_events, *, returncode=1, stderr=''):
        return subprocess.CompletedProcess(
            [], returncode,
            '\n'.join(json.dumps(event, separators=(',', ':')) for event in events) + '\n',
            stderr,
        )

    transport_proof = _structured_transport_terminal(transport_result())
    if transport_proof != {
            'structured_transport_verified': True,
            'transport_error_type': 'provider.transport',
            'transport_session_id_present': True,
            'transport_step_start_count': NEGATIVE_TRANSPORT_ATTEMPTS,
            'transport_terminal_error_count': 1,
            'transport_trace_event_count': NEGATIVE_TRANSPORT_ATTEMPTS + 1}:
        raise RuntimeError('structured_transport_fixture_failed')
    projected_transport = _structured_transport_terminal(
        transport_result(transport_events[-1:]))
    if projected_transport != {
            'structured_transport_verified': True,
            'transport_error_type': 'provider.transport',
            'transport_session_id_present': True,
            'transport_step_start_count': 0,
            'transport_terminal_error_count': 1,
            'transport_trace_event_count': 1}:
        raise RuntimeError('structured_projected_transport_fixture_failed')
    mixed_session_events = copy.deepcopy(transport_events)
    mixed_session_events[1]['sessionID'] = 'ses_OTHER'
    wrong_error_events = copy.deepcopy(transport_events)
    wrong_error_events[-1]['error']['type'] = 'provider.auth'
    response_error_events = copy.deepcopy(transport_events)
    response_error_events[-1]['error']['status'] = 502
    text_events = copy.deepcopy(transport_events)
    text_events[0]['type'] = 'text'
    reordered_events = copy.deepcopy(transport_events)
    reordered_events[-2], reordered_events[-1] = (
        reordered_events[-1], reordered_events[-2])
    ambiguous_transport = (
        transport_result(returncode=2),
        transport_result(stderr='warning'),
        transport_result([step_start(part_id='prt_EXTRA' + str(index))
                          for index in range(NEGATIVE_TRANSPORT_ATTEMPTS + 1)]
                         + transport_events[-1:]),
        transport_result(mixed_session_events),
        transport_result(wrong_error_events),
        transport_result(response_error_events),
        transport_result(text_events),
        transport_result(reordered_events),
        subprocess.CompletedProcess([], 1, '', ''),
    )
    if any(_structured_transport_terminal(result) is not None
           for result in ambiguous_transport):
        raise RuntimeError('structured_transport_ambiguity_fixture_failed')
    identifier = 'c' * 64
    absence_cases = (
        ('container', '', 'Error response from daemon: No such container: ' + identifier),
        ('container', '[]\n', 'Error: No such object: ' + identifier),
        ('network', '', 'Error response from daemon: No such network: ' + identifier),
        ('network', '[]', 'network ' + identifier + ' not found'),
    )
    if any(not _exact_absence_claim(
            kind, identifier,
            subprocess.CompletedProcess([], 1, stdout, message))
            for kind, stdout, message in absence_cases):
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
        subprocess.CompletedProcess([], 1, '[{}]',
                                    'No such container: ' + identifier),
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
    warning_engine = FakeDocker(subprocess.CompletedProcess(
        [], 0, '"27.0.0"\n', 'daemon warning'))
    if (not _docker_engine_responds(responding)
            or _docker_engine_responds(unavailable)
            or _docker_engine_responds(warning_engine)):
        raise RuntimeError('cleanup_engine_liveness_fixture_failed')
    warning_listing = FakeDocker(subprocess.CompletedProcess(
        [], 0, '', 'daemon reported incomplete listing'))
    if (_labeled_ids(warning_listing, 'container', identifier) is not None
            or _label_absence(warning_listing, identifier) != {
                'containers_absent': False, 'networks_absent': False}):
        raise RuntimeError('cleanup_listing_stderr_fixture_failed')

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
    durability_calls = []
    fake_workspace = Path('/fixture/private-workspace')

    def fake_remove(path):
        durability_calls.append(('remove', path))

    def fake_absent(path):
        durability_calls.append(('absent', path))
        return True

    def fake_sync(path):
        durability_calls.append(('sync', path))

    if (not _remove_workspace_durably(
            fake_workspace, remove=fake_remove, absent=fake_absent, sync=fake_sync)
            or durability_calls != [
                ('remove', fake_workspace), ('absent', fake_workspace),
                ('sync', fake_workspace.parent), ('absent', fake_workspace)]):
        raise RuntimeError('temporary_workspace_durability_fixture_failed')

    def failed_sync(_path):
        raise OSError

    if _remove_workspace_durably(
            fake_workspace, remove=lambda _path: None,
            absent=lambda _path: True, sync=failed_sync):
        raise RuntimeError('temporary_workspace_sync_failure_fixture_failed')
    if (not _run_passes(True, None, None, True, True)
            or _run_passes(False, None, None, True, True)
            or _run_passes(True, None, SystemExit(0), True, True)):
        raise RuntimeError('run_completion_fixture_failed')
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
        self.server.record_http(False, False, False)
        self.send_error(405)

    def do_POST(self):
        length_text = self.headers.get('Content-Length', '')
        try:
            length = int(length_text)
        except ValueError:
            length = -1
        expected_path = self.path.split('?', 1)[0] == EXPECTED_PATH
        expected_header = (
            self.headers.get(ARM_MARKER_HEADER) == self.server.expected_arm_marker)
        if length < 0 or length > MAX_REQUEST_BYTES:
            self.server.record_http(expected_path, expected_header, False)
            self.send_error(413)
            return
        body = self.rfile.read(length) if length else b''
        dispatch_marker = False
        if len(body) == length:
            try:
                document = json.loads(body)
            except (UnicodeError, ValueError):
                document = None
            dispatch_marker = (
                _json_scalar_count(document, self.server.expected_dispatch_prompt) == 1)
        self.server.record_http(expected_path, expected_header, dispatch_marker)
        if not expected_path or not expected_header or not dispatch_marker:
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
    block_on_close = False
    allow_reuse_address = False

    def __init__(self, address, context, expected_arm_marker):
        self.tls_context = context
        self.expected_arm_marker = expected_arm_marker
        self.expected_dispatch_prompt = None
        self.observation_lock = threading.Lock()
        self.responder_seal_started = False
        self.responder_sealed = False
        self.observation_revision = 0
        self.active_connections = 0
        self.active_sockets = set()
        self.active_workers = set()
        self.tcp_connections = 0
        self.tls_handshakes = 0
        self.tls_failures = 0
        self.http_requests = 0
        self.expected_path_requests = 0
        self.arm_header_requests = 0
        self.dispatch_marker_requests = 0
        self.unexpected_http_requests = 0
        super().__init__(address, _OwnedHandler)

    def get_request(self):
        raw, address = self.socket.accept()
        raw.settimeout(5)
        with self.observation_lock:
            self.tcp_connections += 1
            self.active_connections += 1
            self.active_sockets.add(raw)
            self.observation_revision += 1
            reject_after_seal = self.responder_seal_started
            if reject_after_seal:
                self.active_connections -= 1
                self.active_sockets.discard(raw)
                self.observation_revision += 1
        if reject_after_seal:
            raw.close()
            raise OSError('owned_responder_sealed')
        try:
            secure = self.tls_context.wrap_socket(raw, server_side=True)
        except (OSError, ssl.SSLError):
            with self.observation_lock:
                self.tls_failures += 1
                self.active_connections -= 1
                self.active_sockets.discard(raw)
                self.observation_revision += 1
            raw.close()
            raise OSError('owned_tls_handshake_failed') from None
        with self.observation_lock:
            self.tls_handshakes += 1
            self.active_sockets.discard(raw)
            self.active_sockets.add(secure)
            self.observation_revision += 1
        return secure, address

    def shutdown_request(self, request):
        try:
            super().shutdown_request(request)
        finally:
            with self.observation_lock:
                self.active_connections -= 1
                self.active_sockets.discard(request)
                self.observation_revision += 1

    def process_request_thread(self, request, client_address):
        worker = threading.current_thread()
        with self.observation_lock:
            self.active_workers.add(worker)
        try:
            super().process_request_thread(request, client_address)
        finally:
            with self.observation_lock:
                self.active_workers.discard(worker)

    def record_http(self, expected_path, expected_header, dispatch_marker):
        with self.observation_lock:
            self.http_requests += 1
            if expected_path:
                self.expected_path_requests += 1
            if expected_path and expected_header:
                self.arm_header_requests += 1
            if expected_path and expected_header and dispatch_marker:
                self.dispatch_marker_requests += 1
            else:
                self.unexpected_http_requests += 1
            self.observation_revision += 1

    def activate_dispatch_prompt(self, dispatch_prompt):
        if (not isinstance(dispatch_prompt, str)
                or re.fullmatch(r'lrh-dispatch-[0-9a-f]{32}-[a-z0-9-]+',
                                dispatch_prompt) is None):
            raise CheckError('dispatch_marker_invalid')
        with self.observation_lock:
            snapshot = {key: getattr(self, key) for key in OBSERVATION_KEYS}
            if (self.expected_dispatch_prompt is not None
                    or self.active_connections != 0
                    or not _observation_is_zero(snapshot)):
                raise CheckError('dispatch_marker_activation_invalid')
            self.expected_dispatch_prompt = dispatch_prompt

    def snapshot(self):
        with self.observation_lock:
            return {key: getattr(self, key) for key in OBSERVATION_KEYS}

    def quiescence_state(self):
        with self.observation_lock:
            return ({key: getattr(self, key) for key in OBSERVATION_KEYS},
                    self.active_connections, self.observation_revision)

    def shutdown_state(self):
        with self.observation_lock:
            return (self.active_connections, len(self.active_sockets),
                    len(self.active_workers),
                    self.responder_sealed)

    def begin_seal(self):
        with self.observation_lock:
            already_complete = self.responder_sealed
            self.responder_seal_started = True
            return already_complete

    def complete_seal(self):
        with self.observation_lock:
            self.responder_sealed = True

    def force_close_connections(self):
        with self.observation_lock:
            active = tuple(self.active_sockets)
        for connection in active:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                connection.close()
            except OSError:
                pass


def _json_scalar_count(value, expected):
    if isinstance(value, str):
        return int(value == expected)
    if isinstance(value, list):
        return sum(_json_scalar_count(item, expected) for item in value)
    if isinstance(value, dict):
        return sum(_json_scalar_count(item, expected) for item in value.values())
    return 0


def _wait_responder_quiescent(server):
    deadline = time.monotonic() + DISPATCH_QUIET_TIMEOUT_SECONDS
    quiet_since = None
    quiet_revision = None
    while time.monotonic() < deadline:
        snapshot, active, revision = server.quiescence_state()
        now = time.monotonic()
        if active == 0:
            if quiet_since is None or revision != quiet_revision:
                quiet_since = now
                quiet_revision = revision
            elif now - quiet_since >= DISPATCH_QUIET_SECONDS:
                return snapshot
        else:
            quiet_since = None
            quiet_revision = revision
        time.sleep(.05)
    raise CheckError('owned_responder_not_quiescent')


def _seal_owned_responder(server, thread):
    if server.begin_seal():
        snapshot, active, _revision = server.quiescence_state()
        _connections, sockets, workers, sealed = server.shutdown_state()
        if (thread.is_alive() or active != 0 or sockets != 0 or workers != 0
                or sealed is not True):
            raise CheckError('owned_responder_shutdown_failed')
        return snapshot
    server.force_close_connections()
    shutdown_failures = []

    def shutdown():
        try:
            server.shutdown()
        except BaseException:
            shutdown_failures.append(True)

    shutdown_thread = None
    if thread.ident is not None:
        shutdown_thread = threading.Thread(target=shutdown, daemon=True)
        shutdown_thread.start()
        shutdown_thread.join(timeout=6)
        thread.join(timeout=6)
    close_failed = False
    try:
        server.server_close()
    except OSError:
        close_failed = True
    if ((shutdown_thread is not None and shutdown_thread.is_alive())
            or thread.is_alive() or shutdown_failures or close_failed):
        raise CheckError('owned_responder_shutdown_failed')
    deadline = time.monotonic() + 6
    _snapshot, active, _revision = server.quiescence_state()
    _connections, sockets, workers, _sealed = server.shutdown_state()
    while (active or sockets or workers) and time.monotonic() < deadline:
        server.force_close_connections()
        time.sleep(.05)
        _snapshot, active, _revision = server.quiescence_state()
        _connections, sockets, workers, _sealed = server.shutdown_state()
    if active != 0 or sockets != 0 or workers != 0:
        raise CheckError('owned_responder_shutdown_failed')
    snapshot = server.snapshot()
    server.complete_seal()
    return snapshot


class Docker:
    def __init__(self):
        self.prefix = ['docker', '--host=' + DOCKER_HOST]

    def run(self, *args, timeout=30, environment=None):
        return _run([*self.prefix, *args], timeout=timeout, environment=environment)

    def json(self, *args, timeout=30):
        result = self.run(*args, timeout=timeout)
        if (type(result.returncode) is not int or result.returncode != 0
                or not isinstance(result.stdout, str)
                or not isinstance(result.stderr, str) or result.stderr.strip()):
            raise CheckError('docker_read_failed')
        try:
            return json.loads(result.stdout)
        except ValueError:
            raise CheckError('docker_json_invalid') from None


def _critical_name(name):
    upper = name.upper()
    return (name in PROXY_ENV or name in TRUST_ENV or name in MUST_BE_ABSENT_ENV
            or name in BOUNDARY_ENV or name in FIXED_RUNTIME_ENV
            or name in SERVER_CONTROL_ENV
            or any(part in upper for part in SENSITIVE_ENV_PARTS))


def _image_forbidden_name(name):
    return _critical_name(name) and name not in FIXED_RUNTIME_ENV


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
    if any(_image_forbidden_name(name) for name in image_env):
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
    return {'id': identifier, 'name': name, 'gateway': str(gateway),
            'subnet': str(subnet)}


def _arm_marker(nonce, arm):
    marker = 'lrh-' + nonce + '-' + arm
    if re.fullmatch(r'lrh-[0-9a-f]{32}-[a-z0-9-]+', marker) is None:
        raise CheckError('arm_marker_invalid')
    return marker


def _new_dispatch_prompt(arm):
    marker = 'lrh-dispatch-' + uuid.uuid4().hex + '-' + arm
    if re.fullmatch(r'lrh-dispatch-[0-9a-f]{32}-[a-z0-9-]+', marker) is None:
        raise CheckError('dispatch_marker_invalid')
    return marker


def _config_document(base_url, arm_marker, *, normalized):
    document = {
        '$schema': 'https://opencode.ai/config.json',
        'model': ({'providerID': 'opencode', 'model': MODEL_ID}
                  if normalized else MODEL),
        'update': 'disable',
        'share': 'disabled',
        'plugins': [],
        'websearch': False,
        'warming': False,
        'permissions': [{'action': '*', 'resource': '*', 'effect': 'deny'}],
        'policies': [
            {'action': 'provider.use', 'resource': '*', 'effect': 'deny'},
            {'action': 'provider.use', 'resource': 'opencode', 'effect': 'allow'},
        ],
        'providers': {
            'opencode': {
                'settings': {
                    'baseURL': base_url,
                    'transport': 'http',
                },
                'headers': {ARM_MARKER_HEADER: arm_marker},
                'models': {MODEL_ID: {'settings': {'baseURL': base_url}}},
            },
        },
    }
    return document


def _config(path, base_url, arm_marker):
    document = _config_document(base_url, arm_marker, normalized=False)
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
        *(name + '=' + value for name, value in FIXED_RUNTIME_ENV.items()),
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
        '--network', 'none', '--add-host', 'opencode.ai:' + gateway,
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
            or item.get('HostConfig', {}).get('NetworkMode') != 'none'
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
            or not set(item.get('NetworkSettings', {}).get('Networks', {})).issubset(
                {'none'})
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


def _activate_dispatch_network(docker, identifier, network):
    before = docker.json('container', 'inspect', identifier)
    if not isinstance(before, list) or len(before) != 1:
        raise CheckError('dispatch_network_prestate_unavailable')
    before_item = before[0]
    before_networks = before_item.get('NetworkSettings', {}).get('Networks')
    if (before_item.get('Id') != identifier
            or before_item.get('State', {}).get('Running') is not True
            or before_item.get('HostConfig', {}).get('NetworkMode') != 'none'
            or not isinstance(before_networks, dict)
            or not set(before_networks).issubset({'none'})
            or network['name'] in before_networks):
        raise CheckError('dispatch_network_prestate_invalid')
    result = docker.run('network', 'connect', network['id'], identifier)
    if (type(result.returncode) is not int or result.returncode != 0
            or not isinstance(result.stdout, str) or result.stdout.strip()
            or not isinstance(result.stderr, str) or result.stderr.strip()):
        raise CheckError('dispatch_network_connect_failed')
    after = docker.json('container', 'inspect', identifier)
    if not isinstance(after, list) or len(after) != 1:
        raise CheckError('dispatch_network_readback_unavailable')
    after_item = after[0]
    after_networks = after_item.get('NetworkSettings', {}).get('Networks')
    attachment = (after_networks.get(network['name'])
                  if isinstance(after_networks, dict) else None)
    try:
        address = ipaddress.ip_address(attachment['IPAddress'])
        subnet = ipaddress.ip_network(network['subnet'])
    except (KeyError, TypeError, ValueError):
        raise CheckError('dispatch_network_readback_invalid') from None
    if (after_item.get('Id') != identifier
            or after_item.get('State', {}).get('Running') is not True
            or not isinstance(after_networks, dict)
            or not set(after_networks).issubset({'none', network['name']})
            or attachment.get('NetworkID') != network['id']
            or attachment.get('Gateway') != network['gateway']
            or address.version != 4 or address not in subnet
            or str(address) == network['gateway']):
        raise CheckError('dispatch_network_readback_invalid')
    return True


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


def _source_roots_pristine(workspace):
    if not isinstance(workspace, Path):
        return False
    blocked = (
        workspace / 'home/.agents',
        workspace / 'home/.claude',
        workspace / 'config/opencode/plugin',
        workspace / 'config/opencode/plugins',
    )
    return all(not os.path.lexists(path) for path in blocked)


def _native_http_preflight(docker, identifier, base_url, arm_marker, workspace):
    if not _source_roots_pristine(workspace):
        raise CheckError('native_http_readback_unavailable')
    models = _api_protocol_list(docker, identifier, 'model.list')
    providers = _api_protocol_list(docker, identifier, 'provider.list')
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
    expected_entries = [
        {
            'type': 'document',
            'path': '/workspace/config/opencode/opencode.json',
            'info': _config_document(base_url, arm_marker, normalized=True),
        },
        {'type': 'directory', 'path': '/workspace/config/opencode'},
    ]
    if config_entries != expected_entries:
        raise CheckError('native_http_readback_unavailable')
    if not _source_roots_pristine(workspace):
        raise CheckError('native_http_readback_unavailable')
    provider_settings = provider.get('settings')
    model_settings = model.get('settings')
    if not isinstance(provider_settings, dict) or not isinstance(model_settings, dict):
        raise CheckError('native_http_readback_unavailable')
    expected_headers = {ARM_MARKER_HEADER: arm_marker}
    model_transport_override_absent = 'transport' not in model_settings
    provider_base_url_verified = provider_settings.get('baseURL') == base_url
    model_base_url_verified = model_settings.get('baseURL') == base_url
    provider_request_headers_verified = provider.get('headers') == expected_headers
    model_request_headers_verified = model.get('headers') == expected_headers
    request_marker_verified = (provider_request_headers_verified
                               and model_request_headers_verified)
    facts = {
        'provider_package': provider.get('package'),
        'effective_model_package': model.get('package'),
        'provider_transport': provider_settings.get('transport'),
        'model_transport_override_absent': model_transport_override_absent,
        'transport_authority': 'provider.settings',
        'provider_base_url_verified': provider_base_url_verified,
        'model_base_url_verified': model_base_url_verified,
        'base_url_verified': provider_base_url_verified and model_base_url_verified,
        'provider_request_headers_verified': provider_request_headers_verified,
        'model_request_headers_verified': model_request_headers_verified,
        'request_marker_verified': request_marker_verified,
        'request_header_authority': 'provider.headers+model.headers',
        'source_boundary_verified': True,
        'preflight_method_scope': (
            'openapi.get+server.info+model.list+provider.list+config.get'),
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
        and facts['provider_request_headers_verified'] is True
        and facts['model_request_headers_verified'] is True
        and facts['request_marker_verified'] is True
        and facts['request_header_authority'] == 'provider.headers+model.headers'
        and facts['source_boundary_verified'] is True
        and facts['preflight_method_scope'] == (
            'openapi.get+server.info+model.list+provider.list+config.get')
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


def _structured_rejection(result, input_mode):
    """Return a receipt-safe proof of one exact runtime-seam rejection."""
    expected = REJECTION_CODE.get(input_mode)
    trace = _structured_error_trace(result, max_step_starts=1)
    if expected is None or trace is None:
        return None
    if trace['error'] != {
            'type': 'unknown', 'message': REJECTION_PREFIX + expected}:
        return None
    return {
        'structured_rejection_verified': True,
        'rejection_code': expected,
        'session_id_present': True,
        'structured_step_start_count': trace['step_start_count'],
        'structured_terminal_error_count': 1,
        'structured_event_count': trace['event_count'],
    }


def _structured_error_trace(result, max_step_starts):
    """Parse one exact same-session step-start/error trace without retaining payloads."""
    if (type(max_step_starts) is not int or max_step_starts < 0
            or result is None or type(result.returncode) is not int
            or result.returncode != 1 or not isinstance(result.stdout, str)
            or not isinstance(result.stderr, str) or result.stderr.strip()
            or len(result.stdout.encode('utf-8')) > MAX_STRUCTURED_OUTPUT_BYTES):
        return None
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not 1 <= len(lines) <= max_step_starts + 1:
        return None
    events = []
    try:
        for line in lines:
            events.append(json.loads(line))
    except (TypeError, ValueError):
        return None
    terminal = events[-1]
    if (not isinstance(terminal, dict)
            or set(terminal) != {'type', 'timestamp', 'sessionID', 'error'}
            or terminal.get('type') != 'error'
            or type(terminal.get('timestamp')) is not int
            or terminal['timestamp'] < 0
            or re.fullmatch(r'ses_[0-9A-Za-z]+',
                            terminal.get('sessionID', '')) is None
            or not isinstance(terminal.get('error'), dict)):
        return None
    session_id = terminal['sessionID']
    part_ids = []
    message_ids = []
    for event in events[:-1]:
        if (not isinstance(event, dict)
                or set(event) != {'type', 'timestamp', 'sessionID', 'part'}
                or event.get('type') != 'step_start'
                or type(event.get('timestamp')) is not int
                or event['timestamp'] < 0
                or event.get('sessionID') != session_id):
            return None
        part = event.get('part')
        if (not isinstance(part, dict)
                or set(part) not in (
                    {'id', 'sessionID', 'messageID', 'type'},
                    {'id', 'sessionID', 'messageID', 'type', 'snapshot'},
                )
                or part.get('sessionID') != session_id
                or part.get('type') != 'step-start'
                or re.fullmatch(r'prt_[0-9A-Za-z]+', part.get('id', '')) is None
                or re.fullmatch(r'msg_[0-9A-Za-z]+',
                                part.get('messageID', '')) is None
                or ('snapshot' in part
                    and (not isinstance(part['snapshot'], str)
                         or not part['snapshot']))):
            return None
        part_ids.append(part['id'])
        message_ids.append(part['messageID'])
    if (len(part_ids) != len(set(part_ids))
            or (message_ids and len(set(message_ids)) != 1)):
        return None
    return {
        'error': terminal['error'],
        'step_start_count': len(events) - 1,
        'event_count': len(events),
    }


def _structured_transport_terminal(result):
    """Return a receipt-safe proof of the pinned retry trace's terminal TLS error."""
    trace = _structured_error_trace(
        result, max_step_starts=NEGATIVE_TRANSPORT_ATTEMPTS)
    if trace is None:
        return None
    error = trace['error']
    if (set(error) != {'type', 'message'}
            or error.get('type') != 'provider.transport'
            or not isinstance(error.get('message'), str)
            or not error['message'].strip()):
        return None
    return {
        'structured_transport_verified': True,
        'transport_error_type': 'provider.transport',
        'transport_session_id_present': True,
        'transport_step_start_count': trace['step_start_count'],
        'transport_terminal_error_count': 1,
        'transport_trace_event_count': trace['event_count'],
    }


def _stdout_proves_no_objects(stdout):
    if not isinstance(stdout, str):
        return False
    if not stdout.strip():
        return True
    try:
        parsed = json.loads(stdout)
    except ValueError:
        return False
    return type(parsed) is list and not parsed


def _exact_absence_claim(kind, identifier, result):
    if (kind not in {'container', 'network'} or result is None
            or re.fullmatch(r'[0-9a-f]{64}', identifier) is None
            or type(result.returncode) is not int or result.returncode == 0
            or not _stdout_proves_no_objects(result.stdout)
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
    if (type(result.returncode) is not int or result.returncode != 0
            or not isinstance(result.stdout, str)
            or not isinstance(result.stderr, str) or result.stderr.strip()):
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
    if (type(inspected_before.returncode) is int and inspected_before.returncode == 0
            and isinstance(inspected_before.stdout, str)
            and isinstance(inspected_before.stderr, str)
            and not inspected_before.stderr.strip()):
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
    if (type(result.returncode) is not int or result.returncode != 0
            or not isinstance(result.stdout, str)
            or not isinstance(result.stderr, str) or result.stderr.strip()):
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


def _remove_workspace_durably(path, *, remove=shutil.rmtree,
                              absent=_path_entry_absent, sync=_fsync_directory):
    try:
        remove(path)
    except FileNotFoundError:
        pass
    except OSError:
        return False
    if not absent(path):
        return False
    try:
        sync(path.parent)
    except OSError:
        return False
    return absent(path)


def _run_passes(verdict_complete, failure, unhandled, cleanup_ok,
                temporary_removed):
    return (verdict_complete is True and failure is None and unhandled is None
            and cleanup_ok is True and temporary_removed is True)


def _raise_unhandled(unhandled):
    if isinstance(unhandled, SystemExit):
        raise CheckError('execution_aborted') from None
    raise unhandled


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
    arm_marker = _arm_marker(nonce, name)
    server = _OwnedTLSServer((network['gateway'], 0), context, arm_marker)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    identifier = None
    try:
        thread.start()
        initial_snapshot = server.snapshot()
        if not _observation_is_zero(initial_snapshot):
            raise CheckError('owned_responder_initial_state_invalid')
        base_url = 'https://opencode.ai:' + str(server.server_address[1]) + '/inference/openai/v1'
        arm_root = work / ('arm-' + name)
        workspace = arm_root / 'workspace'
        for relative in ('home', 'config/opencode', 'data', 'cache', 'state', 'tmp', 'project'):
            (workspace / relative).mkdir(parents=True, exist_ok=True)
        (workspace / 'project/README.md').write_text('Owned TLS trust fixture.\n', encoding='utf-8')
        config = arm_root / 'opencode.json'
        _config(config, base_url, arm_marker)
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
        if preflight_before != initial_snapshot:
            raise CheckError('owned_responder_prebaseline_activity')
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
        facts = _native_http_preflight(
            docker, identifier, base_url, arm_marker, workspace)
        preflight_after = server.snapshot()
        preflight_delta = _observation_delta(preflight_after, preflight_before)
        if preflight_delta is None or any(preflight_delta.values()):
            raise CheckError('native_http_preflight_dispatched')
        dispatch_network_activated = _activate_dispatch_network(
            docker, identifier, network)
        activation_snapshot = server.snapshot()
        activation_delta = _observation_delta(activation_snapshot, preflight_after)
        if activation_delta is None or any(activation_delta.values()):
            raise CheckError('dispatch_network_activation_observed_traffic')
        dispatch_prompt = _new_dispatch_prompt(name)
        server.activate_dispatch_prompt(dispatch_prompt)
        dispatch_baseline = server.snapshot()
        if dispatch_baseline != activation_snapshot:
            raise CheckError('dispatch_marker_activation_observed_traffic')
        command_timeout = (NEGATIVE_COMMAND_TIMEOUT_SECONDS
                           if name == 'ambient-rejected'
                           else DEFAULT_COMMAND_TIMEOUT_SECONDS)
        run = _authenticated_exec(
            docker, identifier,
            'opencode', 'run', '--server', OPENCODE_SERVER_URL,
            '--agent', 'build', '--model', MODEL,
            '--format', 'json', dispatch_prompt, timeout=command_timeout,
        )
        if not _source_roots_pristine(workspace):
            raise CheckError('native_http_readback_unavailable')
        transport_terminal = {}
        if name == 'ambient-rejected':
            transport_terminal = _structured_transport_terminal(run)
            if transport_terminal is None:
                raise CheckError('candidate_transport_terminal_unverified')
        mounted_after = _mounted_ca_hashes(docker, identifier, image_role)
        if mounted_after != mounted_before:
            raise CheckError('mounted_ca_identity_changed')
        _require_fixture_identities(certificates, fixture_identities)
        resource = next(item for item in resources
                        if item['kind'] == 'container' and item['id'] == identifier)
        _remove_resource(docker, resource, cleanup)
        if resource['active']:
            raise CheckError('container_remove_before_responder_seal_failed')
        quiet_snapshot = _wait_responder_quiescent(server)
        final_snapshot = _seal_owned_responder(server, thread)
        if final_snapshot != quiet_snapshot:
            raise CheckError('owned_responder_activity_after_quiescence')
        dispatch = _observation_delta(final_snapshot, dispatch_baseline)
        if dispatch is None:
            raise CheckError('owned_responder_observation_invalid')
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
            'baseline_zero_verified': (
                _observation_is_zero(preflight_delta)
                and _observation_is_zero(dispatch_baseline)),
            'dispatch_network_activated': dispatch_network_activated,
            'preflight_network_mode': 'none',
            'responder_quiescence_verified': True,
            'responder_sealed': True,
            'container_removed_before_responder_seal': True,
            'quiescence_window_ms': int(DISPATCH_QUIET_SECONDS * 1000),
            'command_timeout_seconds': command_timeout,
            'expected_transport_attempts': (
                NEGATIVE_TRANSPORT_ATTEMPTS
                if name == 'ambient-rejected' else 1),
            'version_verified': version_verified, 'server_started': True, **facts,
            **_prefixed_observation('preflight_', preflight_delta),
            **_prefixed_observation('dispatch_baseline_', dispatch_baseline),
            'dispatched': True,
            'exit_code': run.returncode,
            'exit_kind': _exit_kind(run.returncode),
            **transport_terminal,
            **dispatch,
        }
        return row
    finally:
        if identifier is not None:
            resource = next(item for item in resources
                            if item['kind'] == 'container' and item['id'] == identifier)
            _remove_resource(docker, resource, cleanup)
        _seal_owned_responder(server, thread)


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
    arm_marker = _arm_marker(nonce, name)
    server = _OwnedTLSServer((network['gateway'], 0), context, arm_marker)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    identifier = None
    try:
        thread.start()
        initial_snapshot = server.snapshot()
        if not _observation_is_zero(initial_snapshot):
            raise CheckError('owned_responder_initial_state_invalid')
        base_url = 'https://opencode.ai:' + str(server.server_address[1]) + '/inference/openai/v1'
        arm_root = work / ('arm-' + name)
        workspace = arm_root / 'workspace'
        for relative in ('home', 'config/opencode', 'data', 'cache', 'state', 'tmp', 'project'):
            (workspace / relative).mkdir(parents=True, exist_ok=True)
        (workspace / 'project/README.md').write_text(
            'Owned invalid replacement-CA fixture.\n', encoding='utf-8')
        config = arm_root / 'opencode.json'
        _config(config, base_url, arm_marker)
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
        if preflight_before != initial_snapshot:
            raise CheckError('owned_responder_prebaseline_activity')
        _start_server_container(docker, identifier)
        version_verified = _version_verified(workspace)
        if not version_verified:
            raise CheckError('opencode_version_mismatch')
        server_started = _wait_server(docker, identifier)
        if not server_started:
            raise CheckError('candidate_server_start_failed')
        facts = _native_http_preflight(
            docker, identifier, base_url, arm_marker, workspace)
        preflight_after = server.snapshot()
        preflight_delta = _observation_delta(preflight_after, preflight_before)
        if preflight_delta is None or any(preflight_delta.values()):
            raise CheckError('native_http_preflight_dispatched')
        dispatch_network_activated = _activate_dispatch_network(
            docker, identifier, network)
        activation_snapshot = server.snapshot()
        activation_delta = _observation_delta(activation_snapshot, preflight_after)
        if activation_delta is None or any(activation_delta.values()):
            raise CheckError('dispatch_network_activation_observed_traffic')
        dispatch_prompt = _new_dispatch_prompt(name)
        server.activate_dispatch_prompt(dispatch_prompt)
        dispatch_baseline = server.snapshot()
        if dispatch_baseline != activation_snapshot:
            raise CheckError('dispatch_marker_activation_observed_traffic')
        run = _authenticated_exec(
            docker, identifier,
            'opencode', 'run', '--server', OPENCODE_SERVER_URL,
            '--agent', 'build', '--model', MODEL,
            '--format', 'json', dispatch_prompt,
            timeout=DEFAULT_COMMAND_TIMEOUT_SECONDS,
        )
        rejection = _structured_rejection(run, input_mode)
        if rejection is None:
            raise CheckError('candidate_rejection_unverified')
        state = _container_state(docker, identifier)
        if state.get('Running') is not True:
            raise CheckError('candidate_server_stopped_after_rejection')
        if not _wait_server(docker, identifier):
            raise CheckError('candidate_server_stopped_after_rejection')
        facts_after = _native_http_preflight(
            docker, identifier, base_url, arm_marker, workspace)
        if facts_after != facts:
            raise CheckError('native_http_readback_changed_after_rejection')
        resource = next(item for item in resources
                        if item['kind'] == 'container' and item['id'] == identifier)
        _remove_resource(docker, resource, cleanup)
        if resource['active']:
            raise CheckError('container_remove_before_responder_seal_failed')
        quiet_snapshot = _wait_responder_quiescent(server)
        final_snapshot = _seal_owned_responder(server, thread)
        if final_snapshot != quiet_snapshot:
            raise CheckError('owned_responder_activity_after_quiescence')
        dispatch = _observation_delta(final_snapshot, dispatch_baseline)
        if dispatch is None:
            raise CheckError('owned_responder_observation_invalid')
        _require_fixture_identities(certificates, fixture_identities)
        return {
            'arm': name,
            'case_kind': 'pre-socket',
            'image_role': 'candidate',
            'input_mode': input_mode,
            'replacement_pair_state': PAIR_STATE[input_mode],
            'version_verified': version_verified,
            'server_started': True,
            'baseline_zero_verified': (
                _observation_is_zero(preflight_delta)
                and _observation_is_zero(dispatch_baseline)),
            'dispatch_network_activated': dispatch_network_activated,
            'preflight_network_mode': 'none',
            'responder_quiescence_verified': True,
            'responder_sealed': True,
            'container_removed_before_responder_seal': True,
            'quiescence_window_ms': int(DISPATCH_QUIET_SECONDS * 1000),
            'command_timeout_seconds': DEFAULT_COMMAND_TIMEOUT_SECONDS,
            'expected_transport_attempts': 0,
            **facts,
            **_prefixed_observation('preflight_', preflight_delta),
            **_prefixed_observation('dispatch_baseline_', dispatch_baseline),
            'dispatched': True,
            'failure_stage': 'same-server-dispatch',
            'termination_verified': True,
            'server_alive_after_rejection': True,
            'native_readback_stable': True,
            **rejection,
            'exit_code': run.returncode,
            'exit_kind': _exit_kind(run.returncode),
            **dispatch,
        }
    finally:
        if identifier is not None:
            resource = next(item for item in resources
                            if item['kind'] == 'container' and item['id'] == identifier)
            _remove_resource(docker, resource, cleanup)
        _seal_owned_responder(server, thread)


def _label_absence(docker, nonce):
    try:
        containers = docker.run('container', 'ls', '-aq', '--no-trunc',
                                '--filter', 'label=' + LABEL + '=' + nonce)
        networks = docker.run('network', 'ls', '-q', '--no-trunc',
                              '--filter', 'label=' + LABEL + '=' + nonce)
    except CheckError:
        return {'containers_absent': False, 'networks_absent': False}
    def exact_empty_success(result):
        return (type(result.returncode) is int and result.returncode == 0
                and isinstance(result.stdout, str) and not result.stdout.strip()
                and isinstance(result.stderr, str) and not result.stderr.strip())

    return {'containers_absent': exact_empty_success(containers),
            'networks_absent': exact_empty_success(networks)}


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
    temporary_root = Path(tempfile.gettempdir()).resolve()
    work = temporary_root / ('t02-exclusive-trust-' + nonce)
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
        'temporary_workspace_state': 'planned_not_created',
        'pass_valid_only_with_checker_exit_code': 0,
        'external_provider_service_calls': 0, 'external_model_service_calls': 0,
    }

    def persist():
        _write_json(output, receipt)

    persist()
    docker = Docker()
    resources = []
    cleanup = receipt['cleanup']
    failure = None
    unhandled = None
    verdict_complete = False
    cleanup_ok = False
    workspace_created = False
    try:
        try:
            os.mkdir(work, 0o700)
            workspace_created = True
            work_mode = work.lstat().st_mode
            if (not stat.S_ISDIR(work_mode)
                    or stat.S_IMODE(work_mode) != 0o700):
                raise OSError
            _fsync_directory(temporary_root)
        except OSError:
            raise CheckError('temporary_workspace_create_failed') from None
        receipt['temporary_workspace_state'] = 'created_private'
        persist()
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
        verdict_complete = True
    except CheckError as error:
        failure = str(error)
    except KeyboardInterrupt:
        failure = 'interrupted'
    except Exception:
        failure = 'unexpected_failure'
    except BaseException as error:
        failure = 'execution_aborted'
        unhandled = error
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
        if cleanup_ok and unhandled is None and workspace_created:
            receipt['temporary_removed'] = _remove_workspace_durably(work)
        if receipt['temporary_removed']:
            receipt.pop('retained_temporary_workspace', None)
            receipt['temporary_workspace_state'] = 'removed_durable'
        elif workspace_created:
            receipt['retained_temporary_workspace'] = str(work)
            receipt['temporary_workspace_state'] = 'retained_for_recovery'
        else:
            receipt.pop('retained_temporary_workspace', None)
            receipt['temporary_workspace_state'] = 'not_created'
        if failure is None and not verdict_complete:
            failure = 'execution_incomplete'
        if failure is None and (not cleanup_ok or not receipt['temporary_removed']):
            failure = 'cleanup_failed'
        receipt['status'] = ('pass' if _run_passes(
            verdict_complete, failure, unhandled, cleanup_ok,
            receipt['temporary_removed']) else 'failed')
        if receipt['status'] != 'pass' and failure is None:
            failure = 'execution_incomplete'
        if failure is not None:
            receipt['error_code'] = failure if re.fullmatch(r'[a-z][a-z0-9_]{0,79}', failure) else 'failure'
        _write_json(output, receipt)
    if unhandled is not None:
        _raise_unhandled(unhandled)
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
