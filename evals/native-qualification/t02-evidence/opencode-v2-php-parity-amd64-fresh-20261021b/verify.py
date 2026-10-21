#!/usr/bin/env python3
"""Verify the fresh-candidate blocked receipt without Docker or network."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import sys


HERE = Path(__file__).resolve().parent
NATIVE = HERE.parents[1]
BASE = '9c0c0e3f0f7d25fece945a564c8c991a5368d8b9'
TAG = 't02-kanboard-runtime:amd64-parity-20261021b'
DOCKERFILE_SHA256 = '7a1ab9b257fb36a216fc1baafabc757436d0a15ffcb9498b6fbe697da3a9bf4b'
CA_SHA256 = '43e169bf3454bc74c12d3df8c1403f0b4e7da135bf5959f8ab31eb634896bf73'
README_SHA256 = '32bf91b3f7c4d17a11b52987c99d6c0ed1f43c43a182f9b4596ee0dd9e501f45'
INPUTS_SHA256 = '8306c081fcf7d11d137d6c3a773b8d225b4ca0027ddc9a70b1a686d20fcb18a3'
RESULT_SHA256 = 'b7f0875cdb80f2dd567a5be22ce4624858df664b7c96add28a19b3a508b32046'
COMMAND_SHA256 = '2414b40a2b7674a0553e215eeea5a5c06e0c48433c600bc0ca7e0b27ba459997'
OBSERVATIONS_SHA256 = 'd8720995a146140339a2eab86d2967d1d32a74ed86ead96f7795bbe326cd91da'
NETWORKS = [
    {'name': 'bridge', 'id': '1050252286e8631bf8ee038d52cc1cffb8307746317da75e16c8c33afbde07ba'},
    {'name': 'host', 'id': 'dc064e5cfa5c545dfe98b45b11f9bd068174af23daf4b5e8155a9ada938b68bb'},
    {'name': 'none', 'id': '8065fb4aff55641f71f0708775e982d2e8bda062d0ac7ffd91c29ce55e43b216'},
]
CACHE_IDS = {
    '47ehtoqw71c1f0ovp2sfysmh9', 'uae38gxj80a02n8gzi2f73pdz',
    'urofb9wv6yehq8rk8l81or3vz', 'x92kc87fqeg51fzy5c41la612',
    'ydik7lbwq2hcxwqyttv2gls84', '9u2iccw8sozn5ehtlzjldleql',
}
ARCHIVES = {
    'vulnerable': {
        'release': 'v1.2.49',
        'commit': 'f0f7d27007f5a788f14416c548421efd740b7bce',
        'url': ('https://codeload.github.com/kanboard/kanboard/tar.gz/'
                'f0f7d27007f5a788f14416c548421efd740b7bce'),
        'sha256': '3f24269475bf00137d4b0d957d97a2567a5249101dad89067a49d609f4df2edf',
        'retrieved': False,
    },
    'fixed': {
        'release': 'v1.2.50',
        'commit': 'a98bc5f855d4e7e47eb3425a6c7da6c6cc6748a3',
        'url': ('https://codeload.github.com/kanboard/kanboard/tar.gz/'
                'a98bc5f855d4e7e47eb3425a6c7da6c6cc6748a3'),
        'sha256': '44db3df81a25bbd56c768c8b3180a1f05879e2c7fbaa6ac73707e7f3e9098f56',
        'retrieved': False,
    },
}
REPOSITORY_INPUTS = {
    'Dockerfile.opencode-kanboard-runtime': DOCKERFILE_SHA256,
    'observer_case.py': '72273bfd4e1c1aa9f7f53279e525ec1c74c2669324fa62f1b6b22abf65d596bf',
    'observer-evidence-final/observer-results.json':
        '9db3bc220484a7a786729847f3c8fa8cc1d364a74b1e4a81d2bb78f80dc924fa',
    'RESEARCHER-BRIEF.md':
        '8f2b5604870cf86719ae94ac180cb6cbe0c5c12cdd2356bc90f4104bb7179a5a',
    'T01-AMD64-KANBOARD-FRESH-CANDIDATE-CHECKS-20261021.md':
        'ea3a4eff066a6f405d6ddbcf72d912e0405c38da655f878f08b6cfe296ae96e5',
    'smoke/check_v2_php_parity_amd64.py':
        'bf983ccc93fac42033c7785fab35aa10e263c9035ee8680a3896c183df281927',
    'smoke/check_v2_php_parity_amd64_test.py':
        '3bd6542d300de103a8f142655c576de74c6f4665b97a5ee8c57a161b30235c18',
    't02-evidence/opencode-v2-php-parity-amd64-20261021a/README.md':
        'f4509b28f247a138a9af74bfd5325a10718fd568d9d107b268cf472733a0f769',
    't02-evidence/opencode-v2-php-parity-amd64-20261021a/inputs.json':
        '197747bf99a70a8f9df7ebe900e323f82c8c5198c0ca59edf8321a30c3b7e82d',
    't02-evidence/opencode-v2-php-parity-amd64-20261021a/result.json':
        '7709c9e0cfbca3dd00f8d552e0665ce7bc44d3fcacf2704296cec72a5a8343d1',
    't02-evidence/opencode-v2-php-parity-amd64-20261021a/run-command.txt':
        'f25094ae20c429e5a4c6c249de71eb5e36fb4a6aedd1664cd5979dbc7a0366b7',
    't02-evidence/opencode-v2-php-parity-amd64-20261021a/verification.json':
        'e8e3385dbdb9a65d1fc775d7c0d224cc8b68664901bb90bc41b8ad72f70c6fd5',
    't02-evidence/opencode-v2-php-parity-amd64-20261021a/verify.py':
        '273c77591c42e8bc304cf41679b0c17003b6c1ff151f093eb849014e5ecb84ce',
}

INPUT_KEYS = {
    'schema_version', 'kind', 'recorded_at', 'status', 'qualification_base',
    'platform', 'derivation', 'docker', 'dockerfile', 'base_images', 'managed_ca',
    'candidate', 'pre_build_baseline', 'archives', 'repository_inputs',
    'constraints',
}
RESULT_KEYS = {
    'schema_version', 'kind', 'recorded_at', 'status', 'classification',
    'qualification_base', 'provenance', 'failure', 'candidate', 'execution', 'cleanup',
    'follow_up_defects', 'limits', 'remaining_input',
}
NESTED_KEYS = {
    'derivation': {
        'provenance_observed_at', 'docker_baseline_observed_at',
        'failure_contract_frozen_at', 'sanitized_receipt_assembled_at',
        'pre_build_baseline_private_sha256',
    },
    'result_provenance': {
        'cleanup_observed_at', 'independent_final_readback_observed_at',
        'sanitized_result_assembled_at',
    },
    'docker': {
        'context', 'client_version', 'server_version', 'server_os', 'server_arch',
        'api_version', 'buildx_version', 'buildx_revision', 'buildkit_version',
    },
    'dockerfile': {'path', 'sha256'},
    'base_images': {'dockerfile_default', 'effective_build_argument'},
    'managed_ca': {
        'source_class', 'source_path', 'sha256_before', 'size_bytes', 'mode',
        'uid', 'gid', 'mtime', 'buildkit_secret_id', 'buildkit_target',
        'bytes_recorded', 'proxy_values_recorded', 'system_trust_changed',
    },
    'candidate_input': {
        'tag', 'tag_present_before_build', 'required_new_image',
        'prior_nonqualifying_image_ids',
    },
    'pre_build_baseline': {
        'private_receipt_sha256', 'containers', 'images', 'volumes', 'networks',
        'build_cache_record_ids', 'build_cache_bytes',
    },
    'constraints': {
        'provider_calls', 'model_calls', 'live_targets_contacted',
        'external_credentials_used', 'researcher_bundle_created',
        'global_prune_permitted',
    },
    'failure': {
        'phase', 'build_started_at', 'build_failed_at', 'build_exit_code',
        'failed_process', 'apk_exit_code', 'required_php_package_version',
        'available_php_package_version', 'diagnostic',
        'private_build_log_sha256', 'private_build_log_size_bytes',
        'raw_build_log_published', 'build_metadata_file_created',
    },
    'candidate_result': {
        'tag', 'tag_present_after_failure', 'image_loaded', 'image_id',
        'registered', 'registration_receipt_created', 'decision',
    },
    'execution': {
        'build_attempted', 'candidate_tag_absence_checks_performed',
        'registered_candidate_metadata_inspection_succeeded', 'docker_run_calls',
        'archive_retrieval_attempted', 'archives_verified',
        'archives_extracted', 'application_containers_started',
        'ordinary_behavior_run', 'vulnerable_arm_run', 'fixed_arm_run',
        'parity_runner_executed', 'parity_established',
        'researcher_bundle_created', 'provider_calls', 'model_calls',
        'live_targets_contacted', 'external_credentials_used',
    },
    'cleanup': {
        'task_images_removed', 'task_cache_record_ids_created',
        'task_cache_record_ids_removed', 'parent_cache_retries',
        'global_prune_used', 'final_candidate_tag_absent', 'final_containers',
        'final_images', 'final_volumes', 'final_networks',
        'final_build_cache_record_ids', 'final_build_cache_bytes',
        'dockerfile_sha256_after', 'managed_ca_sha256_after',
        'docker_observations_sha256', 'independent_final_readback_private_sha256',
        'baseline_restored',
    },
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reject_duplicates(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f'duplicate JSON key: {key}')
        value[key] = item
    return value


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(), object_pairs_hook=reject_duplicates)
    if not isinstance(value, dict) or not value:
        raise ValueError(f'{path.name}: expected non-empty JSON object')
    return value


def schema_checks(inputs: dict, result: dict) -> dict[str, bool]:
    checks = {
        'inputs top-level schema exact': set(inputs) == INPUT_KEYS,
        'result top-level schema exact': set(result) == RESULT_KEYS,
    }
    mappings = [
        ('derivation', inputs.get('derivation'), 'derivation'),
        ('result provenance', result.get('provenance'), 'result_provenance'),
        ('docker', inputs.get('docker'), 'docker'),
        ('dockerfile', inputs.get('dockerfile'), 'dockerfile'),
        ('base images', inputs.get('base_images'), 'base_images'),
        ('managed ca', inputs.get('managed_ca'), 'managed_ca'),
        ('input candidate', inputs.get('candidate'), 'candidate_input'),
        ('pre-build baseline', inputs.get('pre_build_baseline'), 'pre_build_baseline'),
        ('constraints', inputs.get('constraints'), 'constraints'),
        ('failure', result.get('failure'), 'failure'),
        ('result candidate', result.get('candidate'), 'candidate_result'),
        ('execution', result.get('execution'), 'execution'),
        ('cleanup', result.get('cleanup'), 'cleanup'),
    ]
    for label, value, expected in mappings:
        checks[f'{label} schema exact'] = (
            isinstance(value, dict) and set(value) == NESTED_KEYS[expected])
    checks['archive labels exact'] = (
        set(inputs.get('archives', {})) == set(ARCHIVES)
        and all(set(value) == {'release', 'commit', 'url', 'sha256', 'retrieved'}
                for value in inputs.get('archives', {}).values()
                if isinstance(value, dict)))
    checks['network entry schemas exact'] = all(
        isinstance(item, dict) and set(item) == {'name', 'id'}
        for item in inputs.get('pre_build_baseline', {}).get('networks', [])
        + result.get('cleanup', {}).get('final_networks', []))
    return checks


def receipt_checks(inputs: dict, result: dict, command: str, readme: str,
                   observations: str, command_bytes: bytes,
                   observations_bytes: bytes) -> dict[str, bool]:
    dockerfile = inputs.get('dockerfile', {})
    bases = inputs.get('base_images', {})
    ca = inputs.get('managed_ca', {})
    candidate_input = inputs.get('candidate', {})
    before = inputs.get('pre_build_baseline', {})
    failure = result.get('failure', {})
    candidate = result.get('candidate', {})
    execution = result.get('execution', {})
    cleanup = result.get('cleanup', {})

    serialized = json.dumps({'inputs': inputs, 'result': result}, sort_keys=True)
    serialized += '\n' + command + '\n' + readme + '\n' + observations
    json_secret = re.compile(
        r'(?i)"(?:authorization|api[_-]?key|apikey|cookie|token|access_token|password)"'
        r'\s*:\s*"(?!\[REDACTED\])[^"\n]+"')
    other_secret = re.compile(
        r'(?i)(authorization\s*[:=]\s*(?!\[REDACTED\])\S+|'
        r'basic\s+[a-z0-9+/=]{8,}|https?_proxy\s*=|'
        r'-----begin [^-]+private key-----)')

    expected_constraints = {
        'provider_calls': 0, 'model_calls': 0, 'live_targets_contacted': 0,
        'external_credentials_used': 0, 'researcher_bundle_created': False,
        'global_prune_permitted': False,
    }
    zero_execution = {
        'build_attempted': True,
        'candidate_tag_absence_checks_performed': True,
        'registered_candidate_metadata_inspection_succeeded': False,
        'docker_run_calls': 0,
        'archive_retrieval_attempted': False,
        'archives_verified': 0,
        'archives_extracted': 0,
        'application_containers_started': 0,
        'ordinary_behavior_run': False,
        'vulnerable_arm_run': False,
        'fixed_arm_run': False,
        'parity_runner_executed': False,
        'parity_established': False,
        'researcher_bundle_created': False,
        'provider_calls': 0,
        'model_calls': 0,
        'live_targets_contacted': 0,
        'external_credentials_used': 0,
    }
    return {
        'qualification base and platform exact': (
            inputs.get('qualification_base') == result.get('qualification_base') == BASE
            and inputs.get('platform') == 'linux/amd64'),
        'derived input provenance exact': (
            inputs.get('recorded_at') == '2026-10-21T20:04:03Z'
            and inputs.get('status') == 'derived_from_frozen_pre_build_inputs'
            and inputs.get('kind') == 't02-cloud-amd64-kanboard-fresh-candidate-inputs'
            and inputs.get('derivation') == {
                'provenance_observed_at': '2026-10-21T19:55:09Z',
                'docker_baseline_observed_at': '2026-10-21T19:55:40Z',
                'failure_contract_frozen_at': '2026-10-21T20:00:27Z',
                'sanitized_receipt_assembled_at': '2026-10-21T20:04:03Z',
                'pre_build_baseline_private_sha256':
                    'c3ecbd07c9d784f3782a4f161dccc1141a0d60d24869658d1d9ac2e0f152ecca',
            }),
        'result provenance exact': (
            result.get('recorded_at') == '2026-10-21T20:13:06Z'
            and result.get('provenance') == {
                'cleanup_observed_at': '2026-10-21T20:02:20Z',
                'independent_final_readback_observed_at': '2026-10-21T20:07:51Z',
                'sanitized_result_assembled_at': '2026-10-21T20:13:06Z',
            }),
        'dockerfile and bases exact': (
            dockerfile == {
                'path': 'evals/native-qualification/Dockerfile.opencode-kanboard-runtime',
                'sha256': DOCKERFILE_SHA256,
            }
            and bases.get('dockerfile_default', '').endswith(
                '@sha256:2fc782d346b0670c43378557cf8a2a9926a1f3d28e596180e7b21a0736d8cb7d')
            and bases.get('effective_build_argument', '').endswith(
                '@sha256:85986f556e985e377bd24cd68a5ccfbc647bb49e591194edda8a0e4542303319')),
        'managed ca provenance exact': (
            ca.get('source_path') == '/etc/ssl/certs/ca-certificates.crt'
            and ca.get('sha256_before') == CA_SHA256
            and ca.get('size_bytes') == 230249
            and ca.get('mode') == '0644'
            and ca.get('uid') == 65534
            and ca.get('gid') == 65534
            and ca.get('mtime') == '2026-10-21T03:49:54.214645667Z'
            and ca.get('buildkit_secret_id') == 'proxy_ca'
            and ca.get('buildkit_target') == '/etc/apk/ca.pem'
            and ca.get('bytes_recorded') is False
            and ca.get('proxy_values_recorded') is False
            and ca.get('system_trust_changed') is False),
        'candidate intent exact': (
            candidate_input.get('tag') == TAG
            and candidate_input.get('tag_present_before_build') is False
            and candidate_input.get('required_new_image') is True
            and candidate_input.get('prior_nonqualifying_image_ids') == [
                'sha256:9ef722322521322a1288a18427ba5bf6ce1479085c97e0ac821982eec4f01769',
                'sha256:d0b96c08541486079634fd70a0ffb221c32b07a2a04a1a2ab7d041912a7c9a91',
            ]),
        'outer baseline exact': (
            before.get('containers') == before.get('images') == before.get('volumes') == []
            and before.get('networks') == NETWORKS
            and before.get('build_cache_record_ids') == []
            and before.get('build_cache_bytes') == 0),
        'archives remained unretrieved': inputs.get('archives') == ARCHIVES,
        'constraints remained zero': inputs.get('constraints') == expected_constraints,
        'build blocker exact': (
            result.get('status') == 'blocked_build_dependency_unavailable'
            and failure.get('phase') == 'candidate_image_build'
            and failure.get('build_exit_code') == 1
            and failure.get('apk_exit_code') == 11
            and failure.get('required_php_package_version') == '8.4.26-r0'
            and failure.get('available_php_package_version') == '8.4.27-r0'
            and failure.get('private_build_log_sha256')
            == '92aa9ae5d7a2a67af50877f76ecc1476efcf39f72d29fa7a007d8ec53d801bd9'
            and failure.get('raw_build_log_published') is False
            and failure.get('build_metadata_file_created') is False),
        'candidate never registered': (
            candidate.get('tag') == TAG
            and candidate.get('tag_present_after_failure') is False
            and candidate.get('image_loaded') is False
            and candidate.get('image_id') is None
            and candidate.get('registered') is False
            and candidate.get('registration_receipt_created') is False
            and candidate.get('decision')
            == 'stop_before_candidate_registration_archive_retrieval_or_image_execution'),
        'zero dependent execution': execution == zero_execution,
        'cleanup exact': (
            cleanup.get('task_images_removed') == []
            and set(cleanup.get('task_cache_record_ids_created', [])) == CACHE_IDS
            and len(cleanup.get('task_cache_record_ids_created', [])) == len(CACHE_IDS)
            and set(cleanup.get('task_cache_record_ids_removed', [])) == CACHE_IDS
            and len(cleanup.get('task_cache_record_ids_removed', [])) == len(CACHE_IDS)
            and set(cleanup.get('parent_cache_retries', []))
            == {'47ehtoqw71c1f0ovp2sfysmh9', 'urofb9wv6yehq8rk8l81or3vz'}
            and cleanup.get('global_prune_used') is False
            and cleanup.get('final_candidate_tag_absent') is True
            and cleanup.get('final_containers') == []
            and cleanup.get('final_images') == []
            and cleanup.get('final_volumes') == []
            and cleanup.get('final_networks') == NETWORKS
            and cleanup.get('final_build_cache_record_ids') == []
            and cleanup.get('final_build_cache_bytes') == 0
            and cleanup.get('dockerfile_sha256_after') == DOCKERFILE_SHA256
            and cleanup.get('managed_ca_sha256_after') == CA_SHA256
            and cleanup.get('docker_observations_sha256') == OBSERVATIONS_SHA256
            and cleanup.get('independent_final_readback_private_sha256')
            == 'ecc94f6b186ecf4f237adb5b05bb603e4fd23ad6376d3418ec65fa1ff05e7a64'
            and cleanup.get('baseline_restored') is True),
        'follow-up defects retained': (
            len(result.get('follow_up_defects', [])) == 4
            and all(isinstance(item, str) and item for item in result['follow_up_defects'])),
        'full failed command bytes pinned': (
            hashlib.sha256(command_bytes).hexdigest() == COMMAND_SHA256
            and 'refusing to overwrite existing candidate tag' in command
            and 'set -euC' in command and 'umask 077' in command
            and 'Dockerfile or managed CA SHA-256 mismatch' in command
            and 'PARITY_PRIVATE_ROOT must be a new non-root path' in command
            and 'docker buildx build --platform linux/amd64 --load' in command
            and 'python3 ' not in command),
        'readme states honest blocked scope': (
            'blocked during image build' in readme
            and 'does not establish fresh cloud amd64 application parity' in readme
            and 'No global prune was used' in readme),
        'cleanup observations pinned': (
            hashlib.sha256(observations_bytes).hexdigest() == OBSERVATIONS_SHA256
            and 'After failed build' in observations
            and 'First exact-ID removal pass' in observations
            and 'Independent retained final readback' in observations),
        'no raw secret or private task material': (
            json_secret.search(serialized) is None
            and other_secret.search(serialized) is None
            and '/workspace/' not in serialized
            and '/private/tmp/' not in serialized
            and '-----BEGIN CERTIFICATE-----' not in serialized),
    }


def artifact_byte_checks(inputs_bytes: bytes, result_bytes: bytes,
                         command_bytes: bytes, readme_bytes: bytes,
                         observations_bytes: bytes) -> dict[str, bool]:
    return {
        'complete inputs bytes pinned':
            hashlib.sha256(inputs_bytes).hexdigest() == INPUTS_SHA256,
        'complete result bytes pinned':
            hashlib.sha256(result_bytes).hexdigest() == RESULT_SHA256,
        'complete readme bytes pinned':
            hashlib.sha256(readme_bytes).hexdigest() == README_SHA256,
        'complete command bytes pinned':
            hashlib.sha256(command_bytes).hexdigest() == COMMAND_SHA256,
        'complete cleanup observations bytes pinned':
            hashlib.sha256(observations_bytes).hexdigest() == OBSERVATIONS_SHA256,
    }


def source_checks(inputs: dict) -> dict[str, bool]:
    pins = inputs.get('repository_inputs', {})
    checks = {'source pin manifest exact': pins == REPOSITORY_INPUTS}
    checks.update({
        f'source pin {relative}': (NATIVE / relative).is_file()
        and sha256(NATIVE / relative) == digest
        for relative, digest in REPOSITORY_INPUTS.items()
    })
    return checks


def verify(inputs: dict, result: dict, command: str, readme: str,
           observations: str, inputs_bytes: bytes, result_bytes: bytes,
           command_bytes: bytes, readme_bytes: bytes,
           observations_bytes: bytes) -> dict[str, bool]:
    return (schema_checks(inputs, result)
            | receipt_checks(inputs, result, command, readme, observations,
                             command_bytes, observations_bytes)
            | artifact_byte_checks(inputs_bytes, result_bytes, command_bytes,
                                   readme_bytes, observations_bytes)
            | source_checks(inputs))


def self_test(inputs: dict, result: dict, command: str, readme: str,
              observations: str, inputs_bytes: bytes, result_bytes: bytes,
              command_bytes: bytes, readme_bytes: bytes,
              observations_bytes: bytes) -> dict[str, bool]:
    tests = {}

    forged = copy.deepcopy(result)
    forged['status'] = 'pass'
    tests['reject false pass status'] = not receipt_checks(
        inputs, forged, command, readme, observations,
        command_bytes, observations_bytes)['build blocker exact']

    executed = copy.deepcopy(result)
    executed['execution']['vulnerable_arm_run'] = True
    tests['reject hidden arm execution'] = not receipt_checks(
        inputs, executed, command, readme, observations,
        command_bytes, observations_bytes)['zero dependent execution']

    dirty = copy.deepcopy(result)
    dirty['cleanup']['task_cache_record_ids_removed'].pop()
    tests['reject incomplete cache cleanup'] = not receipt_checks(
        inputs, dirty, command, readme, observations,
        command_bytes, observations_bytes)['cleanup exact']

    retrieved = copy.deepcopy(inputs)
    retrieved['archives']['fixed']['retrieved'] = True
    tests['reject false archive state'] = not receipt_checks(
        retrieved, result, command, readme, observations,
        command_bytes, observations_bytes)['archives remained unretrieved']

    extra = copy.deepcopy(result)
    extra['unreviewed'] = True
    tests['reject extra receipt key'] = not schema_checks(
        inputs, extra)['result top-level schema exact']

    hidden_gate = command.replace(
        'if docker image inspect', 'if false; then :; fi\nif docker image inspect', 1)
    tests['reject false-branch command mutation'] = not receipt_checks(
        inputs, result, hidden_gate, readme, observations,
        hidden_gate.encode(), observations_bytes)['full failed command bytes pinned']

    tests['reject quoted Authorization value'] = not receipt_checks(
        inputs, result, command, readme + '\n{"Authorization":"Bearer secret"}',
        observations, command_bytes, observations_bytes)[
            'no raw secret or private task material']
    tests['reject quoted api_key value'] = not receipt_checks(
        inputs, result, command, readme + '\n{"api_key":"secret"}',
        observations, command_bytes, observations_bytes)[
            'no raw secret or private task material']
    tests['reject any complete inputs mutation'] = not artifact_byte_checks(
        inputs_bytes + b' ', result_bytes, command_bytes, readme_bytes,
        observations_bytes)[
            'complete inputs bytes pinned']
    tests['reject any complete result mutation'] = not artifact_byte_checks(
        inputs_bytes, result_bytes + b' ', command_bytes, readme_bytes,
        observations_bytes)[
            'complete result bytes pinned']
    tests['reject newline-normalized inputs bytes'] = not artifact_byte_checks(
        inputs_bytes.replace(b'\n', b'\r\n'), result_bytes, command_bytes,
        readme_bytes, observations_bytes)['complete inputs bytes pinned']
    return tests


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--json-output', type=Path)
    args = parser.parse_args()

    try:
        inputs_bytes = (HERE / 'inputs.json').read_bytes()
        result_bytes = (HERE / 'result.json').read_bytes()
        inputs_text = inputs_bytes.decode('utf-8')
        result_text = result_bytes.decode('utf-8')
        inputs = json.loads(inputs_text, object_pairs_hook=reject_duplicates)
        result = json.loads(result_text, object_pairs_hook=reject_duplicates)
        if not isinstance(inputs, dict) or not inputs:
            raise ValueError('inputs.json: expected non-empty JSON object')
        if not isinstance(result, dict) or not result:
            raise ValueError('result.json: expected non-empty JSON object')
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({'status': 'fail', 'error': str(error)}, indent=2))
        return 1
    command_bytes = (HERE / 'failed-build-command.txt').read_bytes()
    readme_bytes = (HERE / 'README.md').read_bytes()
    observations_bytes = (HERE / 'docker-observations.txt').read_bytes()
    command = command_bytes.decode('utf-8')
    readme = readme_bytes.decode('utf-8')
    observations = observations_bytes.decode('utf-8')
    checks = verify(
        inputs, result, command, readme, observations, inputs_bytes, result_bytes,
        command_bytes, readme_bytes, observations_bytes)
    if args.self_test:
        checks |= {f'self-test {name}': passed for name, passed in self_test(
            inputs, result, command, readme, observations,
            inputs_bytes, result_bytes, command_bytes, readme_bytes,
            observations_bytes).items()}

    receipt = {
        'schema_version': 1,
        'kind': 't02-cloud-amd64-kanboard-fresh-candidate-public-verification',
        'status': 'pass' if checks and all(checks.values()) else 'fail',
        'checks_passed': sum(checks.values()),
        'checks_total': len(checks),
        'network_required': False,
        'docker_required': False,
        'checks': [{'name': name, 'pass': passed} for name, passed in checks.items()],
    }
    rendered = json.dumps(receipt, indent=2) + '\n'
    if args.json_output:
        args.json_output.write_text(rendered)
    print(rendered, end='')
    return 0 if receipt['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
