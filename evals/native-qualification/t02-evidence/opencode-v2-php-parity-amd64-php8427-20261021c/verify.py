#!/usr/bin/env python3
"""Verify the public PHP 8.4.27 Kanboard qualification offline."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


HERE = Path(__file__).resolve().parent
NATIVE = HERE.parents[1]
ROOT = NATIVE.parents[1]

QUALIFICATION_ID = 't01-kanboard-php8427-amd64-20261021c'
IMAGE_TAG = 't02-kanboard-runtime:amd64-php8427-20261021c'
IMAGE_ID = 'sha256:241dd8f788c62d5c9ef87bdab07ce1f05aca7db0199d532a68b5910c7397f7de'
BASE_IMAGE = ('ghcr.io/anomalyco/opencode@sha256:'
              '85986f556e985e377bd24cd68a5ccfbc647bb49e591194edda8a0e4542303319')
PLATFORM = 'linux/amd64'
PHP_VERSION_LINE = 'PHP 8.4.27 (cli) (built: Oct 21 2026 16:38:20) (NTS)'
PHP_REVISION = '8.4.27-r0'
PARENT_COMMIT = '8e7b730edce6480eec3c92fc10a21a7cb74147a9'
CANDIDATE_SHA256 = 'b988d104545f4ace568a268f79cdf1d2bfb2f686d948ce34f144a01db394df73'
RUNTIME_SHA256 = '0481663a5d4e62b8ec84054288af98523300128fda04512b02c4e89a77ed1e4c'
DOCKERFILE_SHA256 = 'be4948ac34c02f1cf84560f86874f07dc4d6c4b4efc8b1141956d2bf16f7497e'
MANIFEST_SHA256 = 'f5cd14b2cf57039dc75ffb02b31b3acce78afb46877bb58a9108d2120f994d5e'
CHECKS_SHA256 = 'eac607c837d9d356f79662cc0050958d0cf67384565a298be108fedc2636bc94'
CA_SHA256 = '43e169bf3454bc74c12d3df8c1403f0b4e7da135bf5959f8ab31eb634896bf73'
BASELINE_SHA256 = 'd9de6c807003c1bc84d7d5575fab1bf19281e4c5d964085d13119db274ed2df1'
BUILD_METADATA_SHA256 = '12d9c6ea2780aab8fc7a9b00a288705682a9602ca859b44adad7c95ff83b9a8b'
FINAL_READBACK_SHA256 = '68b705d23b677242e0a8a229ccfac73e02c7a8aaca34683bb1e89feea5f4fc41'

RUNTIME_COMMANDS = [
    ['docker', 'run', '--rm', '--pull=never', '--network', 'none',
     '--entrypoint', 'apk', IMAGE_ID, 'info', '-v'],
    ['docker', 'run', '--rm', '--pull=never', '--network', 'none',
     '--entrypoint', 'php', IMAGE_ID, '-v'],
    ['docker', 'run', '--rm', '--pull=never', '--network', 'none',
     '--entrypoint', 'php', IMAGE_ID, '-m'],
]

RESULT_CLASSIFICATION = (
    'owned offline two-arm observer; zero provider/model/target calls')
RESULT_LIMITS = [
    ('This qualifies only the immutable image ID recorded above against the owned '
     'ordinary observer.'),
    ('The live Alpine repository is not a durable package snapshot and may stop '
     'serving 8.4.27-r0.'),
    ('The result is semantic application comparison, not byte-identical PHP 8.4.26 '
     'parity.'),
    ('No provider, model, hosted CI, live target, engagement, or researcher workflow '
     'was exercised.'),
]

ARTIFACT_SHA256 = {
    'README.md': '65b77519db23ff9a6f352603a16c24da324634ae27a333c9fea91fbf47dba600',
    'build-command.txt': '26c36644ee686c7538b6da2f266fbc445f37ff5710ecd8081017381e151ee2be',
    'candidate.json': CANDIDATE_SHA256,
    'docker-observations.txt': 'aa4b36938b3117f0b794200a78bff7f062a5a8e7522d6f661932dc19449d0344',
    'evidence/fixed-requests.json':
        '037fef5ac1842e4413c281f3868a474d0ef1bdf7e049de3220cd55b6f4c9ad4b',
    'evidence/observer-results.public.json':
        'cf7b83e7c79dcb2ade0f833e158ed3535e94350d7effcbc9e34075aca7f92b9d',
    'evidence/vulnerable-requests.json':
        '088257b93fffbe83284c25ffec0b2a938cbffcc41c31ddf86b5623c1c64aad00',
    'inputs.json': '915656a1ef7798d5b1bcec0bc33a06f689a5274d8bd11ef7280310b0b1ff6c33',
    'result.json': 'eaef887fe2aa1c527b1db4d260001e2ecf0475b4dcfae85a43de2d40ff58aef7',
    'run-command.txt': '32d88a17c9aca8728b9722e86cc22cf50ae7734d5967dc834f6b7c82e81a85e2',
    'runtime-admission.json': RUNTIME_SHA256,
}

ARCHIVES = {
    'vulnerable': {
        'commit': 'f0f7d27007f5a788f14416c548421efd740b7bce',
        'url': ('https://codeload.github.com/kanboard/kanboard/tar.gz/'
                'f0f7d27007f5a788f14416c548421efd740b7bce'),
        'sha256': '3f24269475bf00137d4b0d957d97a2567a5249101dad89067a49d609f4df2edf',
        'size_bytes': 3530544,
    },
    'fixed': {
        'commit': 'a98bc5f855d4e7e47eb3425a6c7da6c6cc6748a3',
        'url': ('https://codeload.github.com/kanboard/kanboard/tar.gz/'
                'a98bc5f855d4e7e47eb3425a6c7da6c6cc6748a3'),
        'sha256': '44db3df81a25bbd56c768c8b3180a1f05879e2c7fbaa6ac73707e7f3e9098f56',
        'size_bytes': 3530789,
    },
}

NETWORKS = [
    {'name': 'bridge', 'id': '1050252286e8631bf8ee038d52cc1cffb8307746317da75e16c8c33afbde07ba',
     'driver': 'bridge'},
    {'name': 'host', 'id': 'dc064e5cfa5c545dfe98b45b11f9bd068174af23daf4b5e8155a9ada938b68bb',
     'driver': 'host'},
    {'name': 'none', 'id': '8065fb4aff55641f71f0708775e982d2e8bda062d0ac7ffd91c29ce55e43b216',
     'driver': 'null'},
]
BUILDER = {
    'name': 'default', 'driver': 'docker', 'node': 'default',
    'node_id': '3d9ccea9-b6e8-44d3-bacb-cc5a846b48ca',
    'buildkit_version': 'v0.24.0',
}
CACHE_IDS = {
    'kihzfbgjzuzb8z8c7bks0nd9o', 'llghvf4decuvuo09l50r7thy8',
    'p4z6l2l0cokwl26ffbbueegll', 'q95p7txgmon8hz04xnyg7u623',
    'sccib46cldao8b3cq9sz4ymnk', '1vnhgkxgfxhj38ofd0ltl7htv',
    '75ti2wpmyib4oeqrzm1bns0hk',
}
REQUIRED_PACKAGES = [
    'php84', 'php84-ctype', 'php84-dom', 'php84-gd', 'php84-iconv',
    'php84-mbstring', 'php84-openssl', 'php84-pdo_sqlite', 'php84-session',
    'php84-simplexml', 'php84-xml',
]
INSTALLED_PACKAGES = [
    'php84-8.4.27-r0', 'php84-common-8.4.27-r0', 'php84-ctype-8.4.27-r0',
    'php84-dom-8.4.27-r0', 'php84-gd-8.4.27-r0', 'php84-iconv-8.4.27-r0',
    'php84-mbstring-8.4.27-r0', 'php84-openssl-8.4.27-r0',
    'php84-pdo-8.4.27-r0', 'php84-pdo_sqlite-8.4.27-r0',
    'php84-session-8.4.27-r0', 'php84-simplexml-8.4.27-r0',
    'php84-xml-8.4.27-r0',
]

DECLARED_REPOSITORY_INPUT_PINS = {
    'evals/native-qualification/smoke/check_v2_php_parity_amd64_php8427.py':
        '100cebaaf715e42fa9c10e4c396a5075c931f6f780baac64f590844308d0973d',
    'evals/native-qualification/smoke/check_v2_php_parity_amd64_php8427_test.py':
        '5f2fd1a889df96b21bb7aad73f7fd3a3ced7ad99d79d971e4d262edb480cd0fd',
    'evals/native-qualification/smoke/check_v2_php_parity_amd64.py':
        'bf983ccc93fac42033c7785fab35aa10e263c9035ee8680a3896c183df281927',
    'evals/native-qualification/smoke/check_v2_php_parity_amd64_test.py':
        '3bd6542d300de103a8f142655c576de74c6f4665b97a5ee8c57a161b30235c18',
    'evals/native-qualification/observer_case.py':
        '72273bfd4e1c1aa9f7f53279e525ec1c74c2669324fa62f1b6b22abf65d596bf',
    'evals/native-qualification/observer-evidence-final/observer-results.json':
        '9db3bc220484a7a786729847f3c8fa8cc1d364a74b1e4a81d2bb78f80dc924fa',
    'evals/native-qualification/RESEARCHER-BRIEF.md':
        '8f2b5604870cf86719ae94ac180cb6cbe0c5c12cdd2356bc90f4104bb7179a5a',
}
HISTORICAL_PHP8426_PINS = {
    'evals/native-qualification/Dockerfile.opencode-kanboard-runtime':
        '7a1ab9b257fb36a216fc1baafabc757436d0a15ffcb9498b6fbe697da3a9bf4b',
    ('evals/native-qualification/t02-evidence/'
     'opencode-v2-php-parity-amd64-fresh-20261021b/README.md'):
        '32bf91b3f7c4d17a11b52987c99d6c0ed1f43c43a182f9b4596ee0dd9e501f45',
    ('evals/native-qualification/t02-evidence/'
     'opencode-v2-php-parity-amd64-fresh-20261021b/docker-observations.txt'):
        'd8720995a146140339a2eab86d2967d1d32a74ed86ead96f7795bbe326cd91da',
    ('evals/native-qualification/t02-evidence/'
     'opencode-v2-php-parity-amd64-fresh-20261021b/failed-build-command.txt'):
        '2414b40a2b7674a0553e215eeea5a5c06e0c48433c600bc0ca7e0b27ba459997',
    ('evals/native-qualification/t02-evidence/'
     'opencode-v2-php-parity-amd64-fresh-20261021b/inputs.json'):
        '8306c081fcf7d11d137d6c3a773b8d225b4ca0027ddc9a70b1a686d20fcb18a3',
    ('evals/native-qualification/t02-evidence/'
     'opencode-v2-php-parity-amd64-fresh-20261021b/result.json'):
        'b7f0875cdb80f2dd567a5be22ce4624858df664b7c96add28a19b3a508b32046',
    ('evals/native-qualification/t02-evidence/'
     'opencode-v2-php-parity-amd64-fresh-20261021b/verification.json'):
        'd9a6d0c8c064192a6a6e0bf93c29c0588565a0b14a3b4f5ed3903b5133737fa3',
    ('evals/native-qualification/t02-evidence/'
     'opencode-v2-php-parity-amd64-fresh-20261021b/verify.py'):
        'acaa5c1859c1c029880a4e921c44bcbda2b19bed76f6f5a30a6d85e7bbd6899b',
}
SOURCE_PINS = {
    **DECLARED_REPOSITORY_INPUT_PINS,
    **HISTORICAL_PHP8426_PINS,
}
IMAGE_SOURCE_PINS = {
    'evals/native-qualification/Dockerfile.opencode-kanboard-runtime-php8427':
        DOCKERFILE_SHA256,
    'evals/native-qualification/T01-AMD64-KANBOARD-PHP8427-SOURCE-MANIFEST.json':
        MANIFEST_SHA256,
    'evals/native-qualification/T01-AMD64-KANBOARD-PHP8427-CHECKS-20261021.md':
        CHECKS_SHA256,
}

INPUT_KEYS = {
    'schema_version', 'kind', 'qualification_id', 'evidence_stage', 'recorded_at',
    'requested_scope', 'repository', 'path_bases', 'docker', 'pre_build_baseline',
    'image_source', 'managed_ca', 'receipts', 'archives', 'repository_inputs',
    'public_arm_artifacts', 'constraints',
}
CANDIDATE_KEYS = {
    'schema_version', 'kind', 'recorded_at', 'status', 'scope', 'parity_status',
    'qualification_base', 'platform', 'tag', 'image_id',
    'image_execution_attempted', 'build_inputs', 'image_inspection',
    'outer_baseline', 'archives', 'execution', 'claim_limits',
}
RUNTIME_KEYS = {
    'schema_version', 'kind', 'recorded_at', 'status', 'scope',
    'candidate_receipt_sha256', 'image_id', 'platform', 'execution_policy',
    'packages', 'php', 'application_qualification', 'external_activity',
    'claim_limits',
}
RESULT_KEYS = {
    'schema_version', 'kind', 'qualification_id', 'evidence_stage', 'recorded_at',
    'review_status', 'observed_outcome', 'classification', 'image',
    'runtime_admission', 'archive_admission', 'observer', 'execution',
    'outer_cleanup', 'claims', 'limits',
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def load_json(raw: bytes, name: str):
    value = json.loads(raw.decode('utf-8'), object_pairs_hook=reject_duplicates)
    if not isinstance(value, (dict, list)):
        raise ValueError(f'{name}: expected a JSON object or array')
    return value


def exact_keys(value, keys: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == keys


def strict_equal(actual, expected) -> bool:
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return (set(actual) == set(expected)
                and all(strict_equal(actual[key], value)
                        for key, value in expected.items()))
    if isinstance(expected, (list, tuple)):
        return (len(actual) == len(expected)
                and all(strict_equal(left, right)
                        for left, right in zip(actual, expected)))
    return actual == expected


def artifact_byte_checks(raw: dict[str, bytes]) -> dict[str, bool]:
    return {f'complete bytes pinned: {name}': (
        name in raw and sha256_bytes(raw[name]) == digest)
        for name, digest in ARTIFACT_SHA256.items()}


def schema_checks(inputs: dict, candidate: dict, runtime: dict, result: dict,
                  observer: dict, traces: dict[str, list]) -> dict[str, bool]:
    checks = {
        'inputs top-level schema exact': exact_keys(inputs, INPUT_KEYS),
        'candidate top-level schema exact': exact_keys(candidate, CANDIDATE_KEYS),
        'runtime top-level schema exact': exact_keys(runtime, RUNTIME_KEYS),
        'result top-level schema exact': exact_keys(result, RESULT_KEYS),
        'observer top-level schema exact': exact_keys(observer, {'case', 'status', 'arms'}),
        'trace labels exact': set(traces) == {'vulnerable', 'fixed'},
    }
    mappings = [
        ('input requested scope', inputs.get('requested_scope'), {
            'current_runtime', 'historical_application_semantic_comparison',
            'byte_identical_php8426_parity', 'repairs_sealed_php8426_build'}),
        ('input repository', inputs.get('repository'), {
            'name', 'sealed_parent_pull_request', 'sealed_parent_commit',
            'frozen_source_commit', 'candidate_receipt_commit',
            'runtime_receipt_commit', 'adapter_commit'}),
        ('input path bases', inputs.get('path_bases'), {
            'repository_paths', 'dockerfile_manifest_path', 'public_evidence_paths'}),
        ('input docker', inputs.get('docker'), {
            'context', 'client_version', 'server_version', 'api_version', 'server_os',
            'server_architecture', 'storage_driver', 'engine_id', 'buildx_version',
            'buildx_revision', 'builder'}),
        ('input builder', inputs.get('docker', {}).get('builder'), set(BUILDER)),
        ('input baseline', inputs.get('pre_build_baseline'), {
            'private_receipt_sha256', 'containers', 'images', 'image_tag_mappings',
            'volumes', 'networks', 'build_cache_record_ids', 'build_cache_bytes',
            'candidate_tag_present'}),
        ('input image source', inputs.get('image_source'), {
            'tag', 'image_id', 'platform', 'base', 'base_override_used', 'dockerfile',
            'dockerfile_sha256', 'source_manifest', 'source_manifest_sha256',
            'checks', 'checks_sha256', 'build_attempts', 'build_exit_code',
            'build_metadata_private_sha256', 'raw_build_log_published'}),
        ('input managed ca', inputs.get('managed_ca'), {
            'source_class', 'sha256_before_and_after', 'size_bytes',
            'buildkit_secret_id', 'buildkit_target', 'persisted_in_image',
            'system_trust_changed', 'bytes_recorded', 'proxy_values_recorded'}),
        ('input receipts', inputs.get('receipts'), {'candidate.json', 'runtime-admission.json'}),
        ('input public artifacts', inputs.get('public_arm_artifacts'), {
            'evidence/observer-results.public.json',
            'evidence/vulnerable-requests.json', 'evidence/fixed-requests.json'}),
        ('input constraints', inputs.get('constraints'), {
            'provider_calls', 'model_calls', 'live_targets_contacted',
            'engagements_started', 'external_credentials_used',
            'researcher_bundle_created', 'global_prune_permitted'}),
        ('candidate build inputs', candidate.get('build_inputs'), {
            'source_manifest_sha256', 'dockerfile_path', 'dockerfile_sha256', 'base',
            'base_override_used', 'context', 'platform', 'load',
            'build_metadata_private_sha256', 'managed_ca'}),
        ('candidate managed ca', candidate.get('build_inputs', {}).get('managed_ca'), {
            'source_class', 'sha256', 'size_bytes', 'buildkit_secret_id',
            'buildkit_target', 'persisted_in_image', 'system_trust_changed',
            'bytes_recorded', 'proxy_values_recorded'}),
        ('candidate inspection', candidate.get('image_inspection'), {
            'metadata_only', 'id', 'repo_tags', 'repo_digests', 'os',
            'architecture', 'size_bytes', 'created'}),
        ('candidate outer baseline', candidate.get('outer_baseline'), {
            'private_receipt_sha256', 'candidate_tag_absent_before_build',
            'candidate_image_absent_before_build', 'containers_before',
            'images_before', 'volumes_before', 'build_cache_records_before',
            'cleanup_pending'}),
        ('candidate execution', candidate.get('execution'), {
            'docker_run_calls', 'package_probes', 'php_probes', 'archives_retrieved',
            'archives_verified', 'archives_extracted', 'application_containers_started',
            'application_arms_started', 'provider_calls', 'model_calls',
            'live_targets_contacted', 'external_credentials_used',
            'researcher_bundle_created'}),
        ('candidate claim limits', candidate.get('claim_limits'), {
            'php_package_revision_qualified', 'application_semantics_qualified',
            'historical_semantic_comparison_complete',
            'byte_identical_php8426_parity'}),
        ('runtime execution policy', runtime.get('execution_policy'), {
            'immutable_image_id_only', 'pull', 'network', 'commands', 'exit_codes',
            'container_ids_retained'}),
        ('runtime packages', runtime.get('packages'), {
            'required_revision', 'required_packages', 'installed_php84_packages',
            'required_packages_present', 'all_installed_php84_packages_match_revision',
            'mixed_php84_revision_detected', 'apk_index_warnings_observed',
            'apk_index_warning_context'}),
        ('runtime php', runtime.get('php'), {
            'version_line', 'version_matches', 'modules', 'required_modules',
            'required_modules_present'}),
        ('runtime application', runtime.get('application_qualification'), {
            'archives_retrieved', 'application_arms_started', 'status'}),
        ('runtime external activity', runtime.get('external_activity'), {
            'provider_calls', 'model_calls', 'live_targets_contacted',
            'external_credentials_used', 'researcher_bundle_created'}),
        ('runtime claim limits', runtime.get('claim_limits'), {
            'application_semantics_qualified',
            'historical_semantic_comparison_complete',
            'byte_identical_php8426_parity'}),
        ('result image', result.get('image'), {
            'tag', 'id', 'platform', 'new_relative_to_baseline',
            'registered_before_first_execution', 'candidate_receipt_sha256'}),
        ('result runtime', result.get('runtime_admission'), {
            'receipt_sha256', 'php_version', 'required_packages_present',
            'all_installed_php84_packages_match_8_4_27_r0',
            'required_modules_present',
            'every_probe_used_exact_id_pull_never_network_none'}),
        ('result archive', result.get('archive_admission'), {
            'vulnerable_sha256', 'fixed_sha256', 'archives_verified',
            'both_verified_before_runner_invocation',
            'arms_started_before_both_verified'}),
        ('result observer', result.get('observer'), {
            'private_runner_result_sha256', 'runner_status', 'runner_checks_passed',
            'runner_checks_total', 'failed_checks', 'two_unique_arms',
            'ordinary_controls_both_arms', 'vulnerable_exact_metadata',
            'fixed_cross_role_denial', 'semantic_match_historical_t01',
            'current_runtime_both_arms', 'source_pins_both_arms',
            'arm_cleanup_complete', 'public_result_sha256',
            'vulnerable_trace_sha256', 'fixed_trace_sha256'}),
        ('result execution', result.get('execution'), {
            'application_arms_started', 'application_containers_started',
            'provider_calls', 'model_calls', 'live_targets_contacted',
            'external_credentials_used', 'researcher_bundle_created'}),
        ('result cleanup', result.get('outer_cleanup'), {
            'task_image_removed', 'task_cache_record_ids_created',
            'task_cache_record_ids_removed', 'global_prune_used', 'final_containers',
            'final_images', 'final_image_tag_mappings', 'final_volumes',
            'final_networks', 'final_builder_identity', 'final_build_cache_record_ids',
            'final_build_cache_bytes', 'candidate_tag_absent',
            'candidate_image_absent', 'final_readback_private_sha256',
            'baseline_restored'}),
        ('result claims', result.get('claims'), {
            'current_php8427_application_semantics_qualified',
            'historical_application_semantics_matched',
            'byte_identical_php8426_parity',
            'sealed_php8426_build_remains_blocked',
            'provider_or_model_route_qualified'}),
    ]
    for name, value, keys in mappings:
        checks[f'{name} schema exact'] = exact_keys(value, keys)
    checks['input archive schema exact'] = (
        exact_keys(inputs.get('archives'), {
            'vulnerable', 'fixed', 'both_verified_before_runner_invocation'})
        and all(exact_keys(inputs['archives'].get(label), {
            'commit', 'url', 'sha256', 'size_bytes'})
            for label in ('vulnerable', 'fixed')))
    checks['candidate archive schema exact'] = (
        exact_keys(candidate.get('archives'), {'vulnerable', 'fixed'})
        and all(exact_keys(candidate['archives'].get(label), {
            'commit', 'sha256', 'retrieved'})
            for label in ('vulnerable', 'fixed')))
    checks['observer arms use exact schema'] = (
        isinstance(observer.get('arms'), list)
        and all(exact_keys(arm, {
            'release', 'loopback', 'php', 'runtime', 'project_id', 'swimlane_id',
            'authorized_project', 'authorized_swimlane', 'private_project_control',
            'cross_role_read', 'cleanup', 'commit', 'archive_sha256'})
            for arm in observer.get('arms', [])))
    checks['trace entry schemas exact'] = all(
        isinstance(trace, list) and all(exact_keys(entry, {
            'actor', 'method', 'params', 'http_status', 'raw_response'})
            for entry in trace)
        for trace in traces.values())
    return checks


def input_checks(inputs: dict) -> dict[str, bool]:
    image = inputs.get('image_source', {})
    baseline = inputs.get('pre_build_baseline', {})
    return {
        'input identity and stage exact': (
            strict_equal(inputs.get('schema_version'), 1)
            and inputs.get('kind') == 'kanboard-current-runtime-qualification-inputs'
            and inputs.get('qualification_id') == QUALIFICATION_ID
            and inputs.get('evidence_stage') == 'final-public-inputs'),
        'requested scope is current-runtime semantic comparison only': strict_equal(
            inputs.get('requested_scope'), {
                'current_runtime': 'PHP 8.4.27-r0 on linux/amd64',
                'historical_application_semantic_comparison': True,
                'byte_identical_php8426_parity': False,
                'repairs_sealed_php8426_build': False,
            }),
        'repository chain exact': strict_equal(inputs.get('repository'), {
            'name': 'matheusht/redteam-harness',
            'sealed_parent_pull_request': 179,
            'sealed_parent_commit': PARENT_COMMIT,
            'frozen_source_commit': 'a9ee2c1864134ff406e34aed6216ce73aabe9bc7',
            'candidate_receipt_commit': '6db061431e2bfbc786e4d7e8a1df85bdf2ae540e',
            'runtime_receipt_commit': '8c09d46034adf9d20ce911721628ba96889378ea',
            'adapter_commit': 'bea822b9df62e9e4527cbed2fe97199811b52095',
        }),
        'path bases disambiguated': strict_equal(inputs.get('path_bases'), {
            'repository_paths': 'repository root',
            'dockerfile_manifest_path': 'evals/native-qualification build context',
            'public_evidence_paths': 'this evidence directory',
        }),
        'docker and builder identity exact': (
            inputs.get('docker', {}).get('context') == 'default'
            and inputs.get('docker', {}).get('client_version') == '28.4.0'
            and inputs.get('docker', {}).get('server_version') == '28.4.0'
            and inputs.get('docker', {}).get('api_version') == '1.51'
            and inputs.get('docker', {}).get('server_os') == 'linux'
            and inputs.get('docker', {}).get('server_architecture') == 'amd64'
            and inputs.get('docker', {}).get('storage_driver') == 'vfs'
            and inputs.get('docker', {}).get('engine_id') == BUILDER['node_id']
            and strict_equal(inputs.get('docker', {}).get('builder'), BUILDER)),
        'complete empty pre-build baseline exact': strict_equal(baseline, {
            'private_receipt_sha256': BASELINE_SHA256,
            'containers': [],
            'images': [],
            'image_tag_mappings': [],
            'volumes': [],
            'networks': NETWORKS,
            'build_cache_record_ids': [],
            'build_cache_bytes': 0,
            'candidate_tag_present': False,
        }),
        'image source exact': (
            image.get('tag') == IMAGE_TAG
            and image.get('image_id') == IMAGE_ID
            and image.get('platform') == PLATFORM
            and image.get('base') == BASE_IMAGE
            and image.get('base_override_used') is False
            and image.get('dockerfile_sha256') == DOCKERFILE_SHA256
            and image.get('source_manifest_sha256') == MANIFEST_SHA256
            and image.get('checks_sha256') == CHECKS_SHA256
            and strict_equal(image.get('build_attempts'), 1)
            and strict_equal(image.get('build_exit_code'), 0)
            and image.get('build_metadata_private_sha256') == BUILD_METADATA_SHA256
            and image.get('raw_build_log_published') is False),
        'managed ca provenance exact': strict_equal(inputs.get('managed_ca'), {
            'source_class': 'existing managed combined CA bundle',
            'sha256_before_and_after': CA_SHA256,
            'size_bytes': 230249,
            'buildkit_secret_id': 'proxy_ca',
            'buildkit_target': '/etc/apk/ca.pem',
            'persisted_in_image': False,
            'system_trust_changed': False,
            'bytes_recorded': False,
            'proxy_values_recorded': False,
        }),
        'receipt hashes exact': strict_equal(inputs.get('receipts'), {
            'candidate.json': CANDIDATE_SHA256,
            'runtime-admission.json': RUNTIME_SHA256,
        }),
        'archives exact and both pre-admitted': (
            strict_equal(inputs.get('archives', {}).get('vulnerable'),
                         ARCHIVES['vulnerable'])
            and strict_equal(inputs.get('archives', {}).get('fixed'),
                             ARCHIVES['fixed'])
            and inputs.get('archives', {}).get(
                'both_verified_before_runner_invocation') is True),
        'source pin manifest exact': strict_equal(
            inputs.get('repository_inputs'), DECLARED_REPOSITORY_INPUT_PINS),
        'public arm artifact hashes exact': strict_equal(
            inputs.get('public_arm_artifacts'), {
            'evidence/observer-results.public.json':
                ARTIFACT_SHA256['evidence/observer-results.public.json'],
            'evidence/vulnerable-requests.json':
                ARTIFACT_SHA256['evidence/vulnerable-requests.json'],
            'evidence/fixed-requests.json':
                ARTIFACT_SHA256['evidence/fixed-requests.json'],
        }),
        'input constraints exact': strict_equal(inputs.get('constraints'), {
            'provider_calls': 0,
            'model_calls': 0,
            'live_targets_contacted': 0,
            'engagements_started': 0,
            'external_credentials_used': 0,
            'researcher_bundle_created': False,
            'global_prune_permitted': False,
        }),
    }


def candidate_checks(candidate: dict) -> dict[str, bool]:
    build = candidate.get('build_inputs', {})
    inspection = candidate.get('image_inspection', {})
    execution = candidate.get('execution', {})
    expected_zero = {key: False if key == 'researcher_bundle_created' else 0
                     for key in execution}
    return {
        'candidate is scoped pre-execution registration': (
            strict_equal(candidate.get('schema_version'), 1)
            and candidate.get('kind') == 't01-cloud-amd64-kanboard-php8427-candidate'
            and candidate.get('status') == 'pass'
            and candidate.get('scope') == 'build-and-registration-only'
            and candidate.get('parity_status') == 'not_run'
            and candidate.get('qualification_base') == PARENT_COMMIT
            and candidate.get('image_execution_attempted') is False),
        'candidate image binding exact': (
            candidate.get('platform') == PLATFORM
            and candidate.get('tag') == IMAGE_TAG
            and candidate.get('image_id') == IMAGE_ID
            and inspection.get('metadata_only') is True
            and inspection.get('id') == IMAGE_ID
            and strict_equal(inspection.get('repo_tags'), [IMAGE_TAG])
            and strict_equal(inspection.get('repo_digests'), [])
            and inspection.get('os') == 'linux'
            and inspection.get('architecture') == 'amd64'
            and type(inspection.get('size_bytes')) is int
            and inspection['size_bytes'] > 0),
        'candidate build source exact': (
            build.get('source_manifest_sha256') == MANIFEST_SHA256
            and build.get('dockerfile_path')
            == 'evals/native-qualification/Dockerfile.opencode-kanboard-runtime-php8427'
            and build.get('dockerfile_sha256') == DOCKERFILE_SHA256
            and build.get('base') == BASE_IMAGE
            and build.get('base_override_used') is False
            and build.get('context') == 'evals/native-qualification'
            and build.get('platform') == PLATFORM
            and build.get('load') is True
            and build.get('build_metadata_private_sha256') == BUILD_METADATA_SHA256),
        'candidate managed ca exact': strict_equal(build.get('managed_ca'), {
            'source_class': 'existing managed combined CA bundle',
            'sha256': CA_SHA256,
            'size_bytes': 230249,
            'buildkit_secret_id': 'proxy_ca',
            'buildkit_target': '/etc/apk/ca.pem',
            'persisted_in_image': False,
            'system_trust_changed': False,
            'bytes_recorded': False,
            'proxy_values_recorded': False,
        }),
        'candidate baseline is pre-build and cleanup pending': (
            strict_equal(candidate.get('outer_baseline'), {
                'private_receipt_sha256': BASELINE_SHA256,
                'candidate_tag_absent_before_build': True,
                'candidate_image_absent_before_build': True,
                'containers_before': 0,
                'images_before': 0,
                'volumes_before': 0,
                'build_cache_records_before': 0,
                'cleanup_pending': True,
            })),
        'candidate archives remained unretrieved': all(
            strict_equal(candidate.get('archives', {}).get(label), {
                'commit': expected['commit'], 'sha256': expected['sha256'],
                'retrieved': False})
            for label, expected in ARCHIVES.items()),
        'candidate dependent execution remained zero': strict_equal(
            execution, expected_zero),
        'candidate claims remained false': strict_equal(
            candidate.get('claim_limits'), {
            'php_package_revision_qualified': False,
            'application_semantics_qualified': False,
            'historical_semantic_comparison_complete': False,
            'byte_identical_php8426_parity': False,
        }),
    }


def runtime_checks(runtime: dict) -> dict[str, bool]:
    policy = runtime.get('execution_policy', {})
    packages = runtime.get('packages', {})
    php = runtime.get('php', {})
    php_packages = packages.get('installed_php84_packages', [])
    required_installed = {f'{name}-{PHP_REVISION}' for name in REQUIRED_PACKAGES}
    return {
        'runtime receipt identity exact': (
            strict_equal(runtime.get('schema_version'), 1)
            and runtime.get('kind')
            == 't01-cloud-amd64-kanboard-php8427-runtime-admission'
            and runtime.get('status') == 'pass'
            and runtime.get('scope') == 'immutable-image package-and-php admission only'
            and runtime.get('candidate_receipt_sha256') == CANDIDATE_SHA256
            and runtime.get('image_id') == IMAGE_ID
            and runtime.get('platform') == PLATFORM),
        'runtime command policy exact': (
            policy.get('immutable_image_id_only') is True
            and policy.get('pull') == 'never'
            and policy.get('network') == 'none'
            and strict_equal(policy.get('exit_codes'), [0, 0, 0])
            and policy.get('container_ids_retained') is False
            and strict_equal(policy.get('commands'), RUNTIME_COMMANDS)),
        'runtime required packages exact': (
            packages.get('required_revision') == PHP_REVISION
            and strict_equal(packages.get('required_packages'), REQUIRED_PACKAGES)
            and strict_equal(packages.get('installed_php84_packages'),
                             INSTALLED_PACKAGES)
            and required_installed <= set(php_packages)
            and packages.get('required_packages_present') is True),
        'runtime all php84 packages use one revision': (
            bool(php_packages)
            and all(isinstance(name, str) and name.startswith('php84')
                    and name.endswith(f'-{PHP_REVISION}') for name in php_packages)
            and packages.get('all_installed_php84_packages_match_revision') is True
            and packages.get('mixed_php84_revision_detected') is False),
        'runtime php and modules exact': (
            php.get('version_line') == PHP_VERSION_LINE
            and php.get('version_matches') is True
            and strict_equal(php.get('required_modules'), ['gd', 'pdo_sqlite'])
            and {'gd', 'pdo_sqlite'} <= {
                str(module).lower() for module in php.get('modules', [])}
            and php.get('required_modules_present') is True),
        'runtime application remained not run': strict_equal(
            runtime.get('application_qualification'), {
            'archives_retrieved': 0, 'application_arms_started': 0,
            'status': 'not_run'}),
        'runtime external activity remained zero': strict_equal(
            runtime.get('external_activity'), {
            'provider_calls': 0, 'model_calls': 0, 'live_targets_contacted': 0,
            'external_credentials_used': 0, 'researcher_bundle_created': False}),
        'runtime pre-application claims remained false': strict_equal(
            runtime.get('claim_limits'), {
            'application_semantics_qualified': False,
            'historical_semantic_comparison_complete': False,
            'byte_identical_php8426_parity': False}),
    }


def arms_by_release(observer: dict) -> dict[str, dict]:
    arms = observer.get('arms')
    if not isinstance(arms, list) or len(arms) != 2 or not all(
            isinstance(arm, dict) for arm in arms):
        return {}
    by_release = {arm.get('release'): arm for arm in arms}
    return by_release if len(by_release) == 2 else {}


def denied(value) -> bool:
    return strict_equal(value, {'code': 403, 'message': 'Forbidden'})


def observer_checks(observer: dict, historical: dict) -> dict[str, bool]:
    current = arms_by_release(observer)
    original = arms_by_release(historical)
    two_arms = set(current) == set(original) == {'vulnerable', 'fixed'}
    ordinary = two_arms and all(
        arm.get('loopback') is True
        and type(arm.get('project_id')) is int and arm['project_id'] > 0
        and type(arm.get('swimlane_id')) is int and arm['swimlane_id'] > 0
        and strict_equal(arm.get('authorized_project'), arm.get('project_id'))
        and strict_equal(arm.get('authorized_swimlane'), arm.get('swimlane_id'))
        and denied(arm.get('private_project_control'))
        for arm in current.values())
    vulnerable = current.get('vulnerable', {})
    vulnerable_result = vulnerable.get('cross_role_read', {}).get('result', {})
    vulnerable_exact = (
        strict_equal(vulnerable_result.get('id'), vulnerable.get('swimlane_id'))
        and strict_equal(vulnerable_result.get('project_id'),
                         vulnerable.get('project_id'))
        and vulnerable_result.get('name') == 'Observer Swimlane')
    fixed_denied = denied(
        current.get('fixed', {}).get('cross_role_read', {}).get('denial'))
    comparable = (
        'release', 'loopback', 'project_id', 'swimlane_id', 'authorized_project',
        'authorized_swimlane', 'private_project_control', 'cross_role_read',
        'commit', 'archive_sha256')
    semantic_match = two_arms and all(
        strict_equal(
            {key: current[label].get(key) for key in comparable},
            {key: original[label].get(key) for key in comparable})
        for label in ('vulnerable', 'fixed'))
    cleanup = two_arms and all(
        strict_equal(arm.get('cleanup'), {
            'container_id': '[REDACTED]', 'host_pid': None,
            'loopback_port': '[REDACTED]', 'stop_returncode': 0,
            'container_absent': True, 'port_closed': True,
            'run_dir': f'<private-output>/{label}-run', 'run_dir_absent': True,
            'db_path': f'<private-output>/{label}-run/app/data/db.sqlite',
            'db_absent': True})
        for label, arm in current.items())
    runtime = two_arms and all(
        arm.get('runtime') == IMAGE_ID
        and arm.get('php') == PHP_VERSION_LINE
        for arm in current.values())
    pins = two_arms and all(
        arm.get('commit') == ARCHIVES[label]['commit']
        and arm.get('archive_sha256') == ARCHIVES[label]['sha256']
        for label, arm in current.items())
    return {
        'observer receipt identity exact': (
            observer.get('case') == 'Kanboard local observer preflight'
            and observer.get('status') == 'pass'),
        'observer has exactly two unique release arms': two_arms,
        'ordinary controls pass on both arms': ordinary,
        'vulnerable arm returns exact metadata': vulnerable_exact,
        'fixed arm returns exact denial': fixed_denied,
        'application semantics match historical t01': semantic_match,
        'arm cleanup complete and redacted': cleanup,
        'current runtime exact on both arms': runtime,
        'archive source pins exact on both arms': pins,
    }


def trace_checks(traces: dict[str, list], observer: dict) -> dict[str, bool]:
    current = arms_by_release(observer)
    requests = {}
    raw_objects = {}
    for label, trace in traces.items():
        if not isinstance(trace, list):
            continue
        requests[label] = [
            (entry.get('actor'), entry.get('method'), entry.get('params'),
             entry.get('http_status'))
            for entry in trace if isinstance(entry, dict)]
        values = []
        try:
            values = [json.loads(entry.get('raw_response', ''),
                                 object_pairs_hook=reject_duplicates)
                      for entry in trace]
        except (TypeError, ValueError, json.JSONDecodeError):
            values = []
        raw_objects[label] = values

    expected_requests = {}
    for label in ('vulnerable', 'fixed'):
        arm = current.get(label, {})
        project_id = arm.get('project_id')
        swimlane_id = arm.get('swimlane_id')
        expected_requests[label] = [
            ('admin', 'createUser', ['alice', '[REDACTED]'], 200),
            ('admin', 'createUser', ['bob', '[REDACTED]'], 200),
            ('admin', 'createProject', ['Observer Private Project'], 200),
            ('admin', 'addProjectUser', [project_id, 2, 'project-manager'], 200),
            ('alice', 'getProjectById', [project_id], 200),
            ('bob', 'getProjectById', [project_id], 403),
            ('alice', 'addSwimlane', [
                project_id, 'Observer Swimlane', 'Synthetic description'], 200),
            ('alice', 'getSwimlane', [swimlane_id], 200),
            ('bob', 'getSwimlane', [swimlane_id],
             200 if label == 'vulnerable' else 403),
        ]

    def rpc_result(value, expected) -> bool:
        return (exact_keys(value, {'jsonrpc', 'result', 'id'})
                and value.get('jsonrpc') == '2.0'
                and strict_equal(value.get('id'), 1)
                and strict_equal(value.get('result'), expected))

    def rpc_denial(value) -> bool:
        return strict_equal(value, {
            'jsonrpc': '2.0', 'error': {'code': 403, 'message': 'Forbidden'},
            'id': None})

    def project_effect(value, project_id) -> bool:
        if not (exact_keys(value, {'jsonrpc', 'result', 'id'})
                and value.get('jsonrpc') == '2.0'
                and strict_equal(value.get('id'), 1)):
            return False
        project = value.get('result')
        if not isinstance(project, dict):
            return False
        timestamp = project.get('last_modified')
        without_timestamp = dict(project)
        without_timestamp.pop('last_modified', None)
        return (type(timestamp) is int and timestamp > 0
                and strict_equal(without_timestamp, {
                    'id': project_id,
                    'name': 'Observer Private Project',
                    'is_active': 1,
                    'token': '[REDACTED]',
                    'is_public': 0,
                    'is_private': 0,
                    'is_everybody_allowed': 0,
                    'default_swimlane': 'Default swimlane',
                    'show_default_swimlane': 1,
                    'description': None,
                    'identifier': '',
                    'start_date': '',
                    'end_date': '',
                    'owner_id': 1,
                    'priority_default': 0,
                    'priority_start': 0,
                    'priority_end': 3,
                    'email': None,
                    'predefined_email_subjects': None,
                    'per_swimlane_task_limits': 0,
                    'task_limit': 0,
                    'enable_global_tags': 1,
                    'url': {
                        'board': ('http://localhost/?controller=BoardViewController'
                                  f'&action=show&project_id={project_id}'),
                        'list': ('http://localhost/?controller=TaskListController'
                                 f'&action=show&project_id={project_id}'),
                    },
                }))

    def swimlane_effect(value, project_id, swimlane_id) -> bool:
        return rpc_result(value, {
            'id': swimlane_id,
            'name': 'Observer Swimlane',
            'position': 2,
            'is_active': 1,
            'project_id': project_id,
            'description': 'Synthetic description',
            'task_limit': 0,
        })

    semantic_effects = {}
    for label in ('vulnerable', 'fixed'):
        arm = current.get(label, {})
        project_id = arm.get('project_id')
        swimlane_id = arm.get('swimlane_id')
        values = raw_objects.get(label, [])
        semantic_effects[label] = (
            len(values) == 9
            and rpc_result(values[0], 2)
            and rpc_result(values[1], 3)
            and rpc_result(values[2], project_id)
            and rpc_result(values[3], True)
            and project_effect(values[4], project_id)
            and rpc_denial(values[5])
            and rpc_result(values[6], swimlane_id)
            and swimlane_effect(values[7], project_id, swimlane_id)
            and (swimlane_effect(values[8], project_id, swimlane_id)
                 if label == 'vulnerable' else rpc_denial(values[8])))

    return {
        'trace requests and parameters exact for both arms': (
            strict_equal(requests, expected_requests)),
        'trace synthetic user passwords redacted': all(
            len(traces.get(label, [])) == 9
            and strict_equal(traces[label][0].get('params'),
                             ['alice', '[REDACTED]'])
            and strict_equal(traces[label][1].get('params'),
                             ['bob', '[REDACTED]'])
            for label in ('vulnerable', 'fixed')),
        'trace raw responses are unique-key json': all(
            len(raw_objects.get(label, [])) == 9 for label in ('vulnerable', 'fixed')),
        'trace semantic response effects exact for all calls': (
            strict_equal(semantic_effects, {'vulnerable': True, 'fixed': True})),
    }


def result_checks(inputs: dict, result: dict,
                  observer_results: dict[str, bool]) -> dict[str, bool]:
    image = result.get('image', {})
    runtime = result.get('runtime_admission', {})
    archive = result.get('archive_admission', {})
    observer = result.get('observer', {})
    execution = result.get('execution', {})
    cleanup = result.get('outer_cleanup', {})
    baseline = inputs.get('pre_build_baseline', {})
    semantic_names = {
        'observer has exactly two unique release arms',
        'ordinary controls pass on both arms',
        'vulnerable arm returns exact metadata',
        'fixed arm returns exact denial',
        'application semantics match historical t01',
        'arm cleanup complete and redacted',
        'current runtime exact on both arms',
        'archive source pins exact on both arms',
    }
    return {
        'result remains pre-oracle needs-review evidence': (
            strict_equal(result.get('schema_version'), 1)
            and result.get('kind') == 'kanboard-current-runtime-qualification-result'
            and result.get('qualification_id') == QUALIFICATION_ID
            and result.get('evidence_stage') == 'pre-oracle-result'
            and result.get('review_status') == 'needs_review'
            and result.get('observed_outcome')
            == 'pass_current_runtime_application_semantics'
            and result.get('classification') == RESULT_CLASSIFICATION),
        'result image cross-binding exact': strict_equal(image, {
            'tag': IMAGE_TAG, 'id': IMAGE_ID, 'platform': PLATFORM,
            'new_relative_to_baseline': True,
            'registered_before_first_execution': True,
            'candidate_receipt_sha256': CANDIDATE_SHA256}),
        'result runtime cross-binding exact': (
            runtime.get('receipt_sha256') == RUNTIME_SHA256
            and runtime.get('php_version') == PHP_VERSION_LINE
            and runtime.get('required_packages_present') is True
            and runtime.get('all_installed_php84_packages_match_8_4_27_r0') is True
            and runtime.get('required_modules_present') is True
            and runtime.get(
                'every_probe_used_exact_id_pull_never_network_none') is True),
        'result archive gate exact': strict_equal(archive, {
            'vulnerable_sha256': ARCHIVES['vulnerable']['sha256'],
            'fixed_sha256': ARCHIVES['fixed']['sha256'],
            'archives_verified': 2,
            'both_verified_before_runner_invocation': True,
            'arms_started_before_both_verified': 0}),
        'result observer hashes exact': (
            observer.get('public_result_sha256')
            == ARTIFACT_SHA256['evidence/observer-results.public.json']
            and observer.get('vulnerable_trace_sha256')
            == ARTIFACT_SHA256['evidence/vulnerable-requests.json']
            and observer.get('fixed_trace_sha256')
            == ARTIFACT_SHA256['evidence/fixed-requests.json']),
        'result runner summary exact': (
            observer.get('runner_status') == 'pass'
            and strict_equal(observer.get('runner_checks_passed'), 32)
            and strict_equal(observer.get('runner_checks_total'), 32)
            and strict_equal(observer.get('failed_checks'), [])),
        'result observer claims independently supported': (
            all(observer_results.get(name) is True for name in semantic_names)
            and observer.get('two_unique_arms') is True
            and observer.get('ordinary_controls_both_arms') is True
            and observer.get('vulnerable_exact_metadata') is True
            and observer.get('fixed_cross_role_denial') is True
            and observer.get('semantic_match_historical_t01') is True
            and observer.get('current_runtime_both_arms') is True
            and observer.get('source_pins_both_arms') is True
            and observer.get('arm_cleanup_complete') is True),
        'result execution is two owned arms and zero external activity': (
            strict_equal(execution, {
                'application_arms_started': 2,
                'application_containers_started': 2,
                'provider_calls': 0,
                'model_calls': 0,
                'live_targets_contacted': 0,
                'external_credentials_used': 0,
                'researcher_bundle_created': False})),
        'outer cleanup removed the exact task resources': (
            cleanup.get('task_image_removed') == IMAGE_ID
            and set(cleanup.get('task_cache_record_ids_created', [])) == CACHE_IDS
            and len(cleanup.get('task_cache_record_ids_created', [])) == len(CACHE_IDS)
            and set(cleanup.get('task_cache_record_ids_removed', [])) == CACHE_IDS
            and len(cleanup.get('task_cache_record_ids_removed', [])) == len(CACHE_IDS)
            and cleanup.get('global_prune_used') is False
            and cleanup.get('candidate_tag_absent') is True
            and cleanup.get('candidate_image_absent') is True),
        'outer cleanup exactly restored complete baseline': (
            strict_equal(cleanup.get('final_containers'), [])
            and strict_equal(baseline.get('containers'), [])
            and strict_equal(cleanup.get('final_images'), [])
            and strict_equal(baseline.get('images'), [])
            and strict_equal(cleanup.get('final_image_tag_mappings'), [])
            and strict_equal(baseline.get('image_tag_mappings'), [])
            and strict_equal(cleanup.get('final_volumes'), [])
            and strict_equal(baseline.get('volumes'), [])
            and strict_equal(cleanup.get('final_networks'), NETWORKS)
            and strict_equal(baseline.get('networks'), NETWORKS)
            and strict_equal(cleanup.get('final_builder_identity'), BUILDER)
            and strict_equal(inputs.get('docker', {}).get('builder'), BUILDER)
            and strict_equal(cleanup.get('final_build_cache_record_ids'), [])
            and strict_equal(baseline.get('build_cache_record_ids'), [])
            and strict_equal(cleanup.get('final_build_cache_bytes'), 0)
            and strict_equal(baseline.get('build_cache_bytes'), 0)
            and cleanup.get('final_readback_private_sha256')
            == FINAL_READBACK_SHA256
            and cleanup.get('baseline_restored') is True),
        'claim limits are explicit and exact': strict_equal(result.get('claims'), {
            'current_php8427_application_semantics_qualified': True,
            'historical_application_semantics_matched': True,
            'byte_identical_php8426_parity': False,
            'sealed_php8426_build_remains_blocked': True,
            'provider_or_model_route_qualified': False}),
        'limits retain exact current-runtime scope': strict_equal(
            result.get('limits'), RESULT_LIMITS),
    }


def source_checks(inputs: dict,
                  source_overrides: dict[str, bytes] | None = None) -> dict[str, bool]:
    source_overrides = source_overrides or {}
    checks = {
        'source manifest in inputs exact': strict_equal(
            inputs.get('repository_inputs'), DECLARED_REPOSITORY_INPUT_PINS)}
    for relative, digest in SOURCE_PINS.items():
        path = ROOT / relative
        value = source_overrides.get(relative)
        if value is None and path.is_file():
            value = path.read_bytes()
        checks[f'source file pinned: {relative}'] = (
            path.is_file() and value is not None and sha256_bytes(value) == digest)
    image = inputs.get('image_source', {})
    path_bindings = {
        image.get('dockerfile'): image.get('dockerfile_sha256'),
        image.get('source_manifest'): image.get('source_manifest_sha256'),
        image.get('checks'): image.get('checks_sha256'),
    }
    checks['image source paths and hashes exact'] = strict_equal(
        path_bindings, IMAGE_SOURCE_PINS)
    for relative, digest in IMAGE_SOURCE_PINS.items():
        path = ROOT / relative
        value = source_overrides.get(relative)
        if value is None and path.is_file():
            value = path.read_bytes()
        checks[f'image source pinned: {relative}'] = (
            path.is_file() and value is not None and sha256_bytes(value) == digest)
    return checks


SENSITIVE_KEYS = {
    'authorization', 'proxyauthorization', 'apikey', 'cookie', 'setcookie',
    'token', 'accesstoken', 'password', 'secret', 'signature', 'sig',
    'xamzsignature', 'xgoogsignature',
}
JSON_SECRET = re.compile(
    r'(?i)"(?:authorization|proxy[-_]?authorization|api[-_]?key|apikey|'
    r'cookie|set-cookie|token|access[-_]?token|password|secret|signature|sig|'
    r'x-amz-signature|x-goog-signature)"\s*:\s*'
    r'"(?!\[REDACTED\]")[^"\r\n]+"')
HEADER_FIELD = re.compile(
    r'(?im)\b(?:authorization|proxy-authorization|cookie|set-cookie)\s*'
    r'[:=]\s*([^\r\n]+)')
PLAINTEXT_SECRET_FIELD = re.compile(
    r'(?im)\b(?:password|api[-_]?key|access[-_]?token|token|secret)\s*'
    r'[:=]\s*([^\r\n]+)')
SIGNED_URL_SECRET = re.compile(
    r'(?i)[?&](?:x-amz-(?:signature|credential|security-token)|'
    r'x-goog-(?:signature|credential)|googleaccessid|sig|signature|'
    r'access[-_]?token|token|api[-_]?key)='
    r'(?!\[REDACTED\](?:[&#\s]|$)|%5bredacted%5d(?:[&#\s]|$))'
    r'[^&#\s"<>]+')
JWT_SECRET = re.compile(
    r'(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{8,}'
    r'\.[A-Za-z0-9_-]{8,}(?![A-Za-z0-9_-])')
OTHER_SECRET = re.compile(
    r'(?i)(?:https?_proxy\s*=|-----begin [^-]+private key-----|'
    r'-----begin certificate-----)')


def has_unredacted_field(pattern: re.Pattern, value: str) -> bool:
    redacted = {'[REDACTED]', '"[REDACTED]"', "'[REDACTED]'"}
    return any(match.group(1).strip() not in redacted
               for match in pattern.finditer(value))


def semantic_secret_free(value) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = re.sub(r'[-_]', '', str(key).lower())
            if (normalized in SENSITIVE_KEYS
                    and item not in (None, False, 0, '', '[REDACTED]')):
                return False
            if not semantic_secret_free(item):
                return False
            if key == 'raw_response' and isinstance(item, str):
                try:
                    nested = json.loads(item, object_pairs_hook=reject_duplicates)
                except (ValueError, json.JSONDecodeError):
                    return False
                if not semantic_secret_free(nested):
                    return False
        return True
    if isinstance(value, list):
        return all(semantic_secret_free(item) for item in value)
    if isinstance(value, str):
        return not (JSON_SECRET.search(value)
                    or has_unredacted_field(HEADER_FIELD, value)
                    or has_unredacted_field(PLAINTEXT_SECRET_FIELD, value)
                    or SIGNED_URL_SECRET.search(value) or JWT_SECRET.search(value)
                    or OTHER_SECRET.search(value))
    return True


def public_material_checks(raw: dict[str, bytes],
                           parsed: dict[str, object]) -> dict[str, bool]:
    texts = []
    decoded = True
    for value in raw.values():
        try:
            texts.append(value.decode('utf-8'))
        except UnicodeDecodeError:
            decoded = False
    serialized = '\n'.join(texts)
    return {
        'all public artifacts are utf-8': decoded,
        'json header and plaintext secret values absent': (
            JSON_SECRET.search(serialized) is None
            and not has_unredacted_field(HEADER_FIELD, serialized)
            and not has_unredacted_field(PLAINTEXT_SECRET_FIELD, serialized)),
        'signed url credential values absent': SIGNED_URL_SECRET.search(serialized) is None,
        'raw jwt values absent': JWT_SECRET.search(serialized) is None,
        'proxy ca and private-key material absent': OTHER_SECRET.search(serialized) is None,
        'private workspace paths absent': (
            '/workspace/' not in serialized and '/private/tmp/' not in serialized),
        'parsed public json contains no secret values': all(
            semantic_secret_free(value) for value in parsed.values()),
    }


def command_checks(raw: dict[str, bytes]) -> dict[str, bool]:
    build = raw['build-command.txt'].decode('utf-8')
    run = raw['run-command.txt'].decode('utf-8')
    readme = raw['README.md'].decode('utf-8')
    observations = raw['docker-observations.txt'].decode('utf-8')
    build_syntax = subprocess.run(
        ['bash', '-n', str(HERE / 'build-command.txt')],
        capture_output=True).returncode
    run_syntax = subprocess.run(
        ['bash', '-n', str(HERE / 'run-command.txt')],
        capture_output=True).returncode
    forbidden_run = re.search(
        r'(?m)^[^#\n]*\bdocker\s+(?:build|buildx|tag|pull)\b', run)
    try:
        inspect_index = run.index('ACTUAL="$(docker image inspect')
        mismatch_index = run.index('if [ "${ACTUAL}" != "${EXPECTED}" ]; then')
        exit_index = run.index('  exit 1\n', mismatch_index)
        python_index = run.index('exec python3 ')
        gate_order = inspect_index < mismatch_index < exit_index < python_index
    except ValueError:
        gate_order = False
    return {
        'build and replay commands are shell-valid': build_syntax == run_syntax == 0,
        'historical build command exact and bounded': (
            'set -euo pipefail' in build
            and "EXPECTED_HEAD='a9ee2c1864134ff406e34aed6216ce73aabe9bc7'" in build
            and 'refusing pre-existing task tag' in build
            and 'docker buildx build' in build
            and '--platform linux/amd64' in build and '--load' in build
            and '--secret id=proxy_ca,type=file,src=/etc/ssl/certs/ca-certificates.crt'
            in build and '--build-arg' not in build),
        'replay command never builds tags or pulls': forbidden_run is None,
        'replay mismatch gate precedes python': gate_order,
        'replay binds exact receipts image and platform': (
            CANDIDATE_SHA256 in run and RUNTIME_SHA256 in run
            and f"EXPECTED='{IMAGE_ID} {PLATFORM}'" in run
            and 'docker image inspect "${TAG}"' in run),
        'readme states current-runtime limits and oracle boundary': (
            'This is **not** byte-identical PHP 8.4.26 parity' in readme
            and re.search(r'`result\.json`\s+remains `needs_review`', readme)
            is not None
            and 'only `verification.json` is the public offline oracle' in readme),
        'docker observations state exact restored lifecycle': (
            re.search(r'No global prune was\s+used', observations) is not None
            and 'baseline_restored=true' in observations
            and IMAGE_ID in observations and BASELINE_SHA256 in observations
            and FINAL_READBACK_SHA256 in observations),
    }


def executable_wrong_id_negative() -> bool:
    with tempfile.TemporaryDirectory(prefix='php8427-command-negative-') as temp:
        root = Path(temp)
        marker = root / 'python-called'
        fake_docker = root / 'docker'
        fake_python = root / 'python3'
        fake_docker.write_text(
            '#!/bin/sh\n'
            'if [ "$1 $2" = "image inspect" ]; then\n'
            "  printf '%s\\n' 'sha256:0000000000000000000000000000000000000000000000000000000000000000 linux/amd64'\n"
            '  exit 0\n'
            'fi\n'
            'exit 97\n')
        fake_python.write_text(
            '#!/bin/sh\nprintf called > "$PYTHON_MARKER"\n')
        fake_docker.chmod(0o700)
        fake_python.chmod(0o700)
        env = os.environ.copy()
        env.update({
            'PATH': f'{root}:/usr/bin:/bin',
            'PHP8427_OUTPUT': str(root / 'output'),
            'PYTHON_MARKER': str(marker),
        })
        run = subprocess.run(
            ['bash', str(HERE / 'run-command.txt')], cwd=ROOT, env=env,
            capture_output=True, text=True)
        return run.returncode != 0 and not marker.exists()


def self_tests(raw: dict[str, bytes], inputs: dict, candidate: dict,
               runtime: dict, result: dict, observer: dict, historical: dict,
               traces: dict[str, list], parsed: dict[str, object]) -> dict[str, bool]:
    tests = {}
    binding_probe = json.loads(render_receipt({'binding probe': True}))
    tests['verification receipt binds exact verifier bytes'] = (
        binding_probe.get('verifier_sha256')
        == sha256_bytes((HERE / 'verify.py').read_bytes()))
    tests['verification receipt binds exact public artifact map'] = strict_equal(
        binding_probe.get('artifact_sha256'), {
            name: sha256_bytes(raw[name]) for name in sorted(raw)})

    historical_php8426 = {
        'evals/native-qualification/Dockerfile.opencode-kanboard-runtime':
            '7a1ab9b257fb36a216fc1baafabc757436d0a15ffcb9498b6fbe697da3a9bf4b',
        ('evals/native-qualification/t02-evidence/'
         'opencode-v2-php-parity-amd64-fresh-20261021b/README.md'):
            '32bf91b3f7c4d17a11b52987c99d6c0ed1f43c43a182f9b4596ee0dd9e501f45',
        ('evals/native-qualification/t02-evidence/'
         'opencode-v2-php-parity-amd64-fresh-20261021b/docker-observations.txt'):
            'd8720995a146140339a2eab86d2967d1d32a74ed86ead96f7795bbe326cd91da',
        ('evals/native-qualification/t02-evidence/'
         'opencode-v2-php-parity-amd64-fresh-20261021b/failed-build-command.txt'):
            '2414b40a2b7674a0553e215eeea5a5c06e0c48433c600bc0ca7e0b27ba459997',
        ('evals/native-qualification/t02-evidence/'
         'opencode-v2-php-parity-amd64-fresh-20261021b/inputs.json'):
            '8306c081fcf7d11d137d6c3a773b8d225b4ca0027ddc9a70b1a686d20fcb18a3',
        ('evals/native-qualification/t02-evidence/'
         'opencode-v2-php-parity-amd64-fresh-20261021b/result.json'):
            'b7f0875cdb80f2dd567a5be22ce4624858df664b7c96add28a19b3a508b32046',
        ('evals/native-qualification/t02-evidence/'
         'opencode-v2-php-parity-amd64-fresh-20261021b/verification.json'):
            'd9a6d0c8c064192a6a6e0bf93c29c0588565a0b14a3b4f5ed3903b5133737fa3',
        ('evals/native-qualification/t02-evidence/'
         'opencode-v2-php-parity-amd64-fresh-20261021b/verify.py'):
            'acaa5c1859c1c029880a4e921c44bcbda2b19bed76f6f5a30a6d85e7bbd6899b',
    }
    for relative, digest in historical_php8426.items():
        try:
            mutated_checks = source_checks(
                inputs, {relative: (ROOT / relative).read_bytes() + b'\nmutation'})
        except TypeError:
            mutated_checks = {}
        tests[f'reject immutable historical mutation: {relative}'] = (
            SOURCE_PINS.get(relative) == digest
            and mutated_checks.get(f'source file pinned: {relative}') is False)

    for name in ARTIFACT_SHA256:
        mutated = raw[name].replace(b'\n', b'\r\n')
        mutated_raw = dict(raw)
        mutated_raw[name] = mutated
        tests[f'reject CRLF byte substitution: {name}'] = (
            mutated != raw[name]
            and not artifact_byte_checks(mutated_raw)[
                f'complete bytes pinned: {name}'])

    try:
        load_json(b'{"value": 1, "value": 2}', 'duplicate-test')
        tests['reject duplicate json key'] = False
    except ValueError:
        tests['reject duplicate json key'] = True

    extra = copy.deepcopy(inputs)
    extra['unreviewed'] = True
    tests['reject extra input key'] = not schema_checks(
        extra, candidate, runtime, result, observer, traces)[
            'inputs top-level schema exact']

    typed_input = copy.deepcopy(inputs)
    typed_input['constraints']['provider_calls'] = False
    typed_input['constraints']['researcher_bundle_created'] = 0
    tests['reject bool-int input constraint substitutions'] = not input_checks(
        typed_input)['input constraints exact']

    wrong_image = copy.deepcopy(result)
    wrong_image['image']['id'] = 'sha256:' + '0' * 64
    tests['reject wrong result image id'] = not result_checks(
        inputs, wrong_image, observer_checks(observer, historical))[
            'result image cross-binding exact']

    wrong_runtime = copy.deepcopy(runtime)
    wrong_runtime['php']['version_line'] = 'PHP 8.4.26 (cli)'
    tests['reject wrong php runtime'] = not runtime_checks(wrong_runtime)[
        'runtime php and modules exact']

    altered_version = copy.deepcopy(runtime)
    altered_version['php']['version_line'] = (
        'PHP 8.4.27 (cli) (built: Oct 21 2026 16:38:21) (NTS)')
    tests['reject altered exact php version line'] = not runtime_checks(
        altered_version)['runtime php and modules exact']

    altered_command = copy.deepcopy(runtime)
    altered_command['execution_policy']['commands'][0].insert(-2, '--unexpected')
    tests['reject non-exact runtime command'] = not runtime_checks(
        altered_command)['runtime command policy exact']

    typed_exit_code = copy.deepcopy(runtime)
    typed_exit_code['execution_policy']['exit_codes'][0] = False
    tests['reject bool-for-int runtime exit code'] = not runtime_checks(
        typed_exit_code)['runtime command policy exact']

    typed_application_count = copy.deepcopy(runtime)
    typed_application_count['application_qualification']['archives_retrieved'] = False
    tests['reject bool-for-int runtime application count'] = not runtime_checks(
        typed_application_count)['runtime application remained not run']

    typed_external_count = copy.deepcopy(runtime)
    typed_external_count['external_activity']['provider_calls'] = False
    tests['reject bool-for-int runtime external count'] = not runtime_checks(
        typed_external_count)['runtime external activity remained zero']

    altered_result_version = copy.deepcopy(result)
    altered_result_version['runtime_admission']['php_version'] = (
        'PHP 8.4.27 (cli) (built: substituted) (NTS)')
    tests['reject result runtime version substitution'] = not result_checks(
        inputs, altered_result_version, observer_checks(observer, historical))[
            'result runtime cross-binding exact']

    altered_arm_version = copy.deepcopy(observer)
    altered_arm_version['arms'][0]['php'] = (
        'PHP 8.4.27 (cli) (built: substituted) (NTS)')
    tests['reject arm runtime version substitution'] = not observer_checks(
        altered_arm_version, historical)['current runtime exact on both arms']

    mixed = copy.deepcopy(runtime)
    mixed['packages']['installed_php84_packages'][-1] = 'php84-xml-8.4.26-r0'
    tests['reject mixed php84 package revision'] = not runtime_checks(mixed)[
        'runtime all php84 packages use one revision']

    changed_archive = copy.deepcopy(inputs)
    changed_archive['archives']['fixed']['sha256'] = '0' * 64
    tests['reject changed archive pin'] = not input_checks(changed_archive)[
        'archives exact and both pre-admitted']

    missing_arm = copy.deepcopy(observer)
    missing_arm['arms'].pop()
    tests['reject missing arm'] = not observer_checks(missing_arm, historical)[
        'observer has exactly two unique release arms']

    duplicate_arm = copy.deepcopy(observer)
    duplicate_arm['arms'][1] = copy.deepcopy(duplicate_arm['arms'][0])
    tests['reject duplicate arm'] = not observer_checks(duplicate_arm, historical)[
        'observer has exactly two unique release arms']

    semantic_mismatch = copy.deepcopy(observer)
    semantic_mismatch['arms'][0]['cross_role_read']['result']['project_id'] = 999
    mismatch_checks = observer_checks(semantic_mismatch, historical)
    tests['reject vulnerable semantic mismatch'] = (
        not mismatch_checks['vulnerable arm returns exact metadata']
        and not mismatch_checks['application semantics match historical t01'])

    typed_observer_effect = copy.deepcopy(observer)
    typed_observer_effect['arms'][0]['cross_role_read']['result']['project_id'] = True
    tests['reject bool-for-int observer effect'] = not observer_checks(
        typed_observer_effect, historical)[
            'vulnerable arm returns exact metadata']

    typed_observer_cleanup = copy.deepcopy(observer)
    typed_observer_cleanup['arms'][0]['cleanup']['stop_returncode'] = False
    tests['reject bool-for-int observer cleanup'] = not observer_checks(
        typed_observer_cleanup, historical)['arm cleanup complete and redacted']

    wrong_trace_params = copy.deepcopy(traces)
    wrong_trace_params['vulnerable'][3]['params'][2] = 'viewer'
    tests['reject altered intermediate trace parameters'] = not trace_checks(
        wrong_trace_params, observer)['trace requests and parameters exact for both arms']

    wrong_param_type = copy.deepcopy(traces)
    wrong_param_type['vulnerable'][3]['params'][0] = True
    tests['reject bool-for-int trace parameter substitution'] = not trace_checks(
        wrong_param_type, observer)[
            'trace requests and parameters exact for both arms']

    wrong_trace_effect = copy.deepcopy(traces)
    wrong_trace_effect['fixed'][3]['raw_response'] = (
        '{"jsonrpc":"2.0","result":false,"id":1}')
    tests['reject altered intermediate trace effect'] = not trace_checks(
        wrong_trace_effect, observer)[
            'trace semantic response effects exact for all calls']

    wrong_nested_type = copy.deepcopy(traces)
    nested_response = json.loads(
        wrong_nested_type['fixed'][7]['raw_response'],
        object_pairs_hook=reject_duplicates)
    nested_response['result']['project_id'] = True
    wrong_nested_type['fixed'][7]['raw_response'] = json.dumps(
        nested_response, separators=(',', ':'))
    tests['reject nested bool-for-int trace substitution'] = not trace_checks(
        wrong_nested_type, observer)[
            'trace semantic response effects exact for all calls']

    dirty = copy.deepcopy(result)
    dirty['outer_cleanup']['final_images'] = [IMAGE_ID]
    tests['reject incomplete outer cleanup'] = not result_checks(
        inputs, dirty, observer_checks(observer, historical))[
            'outer cleanup exactly restored complete baseline']

    typed_execution = copy.deepcopy(result)
    typed_execution['execution']['provider_calls'] = False
    tests['reject bool-for-int result execution count'] = not result_checks(
        inputs, typed_execution, observer_checks(observer, historical))[
            'result execution is two owned arms and zero external activity']

    typed_cleanup = copy.deepcopy(result)
    typed_cleanup['outer_cleanup']['final_build_cache_bytes'] = False
    tests['reject bool-for-int final cleanup bytes'] = not result_checks(
        inputs, typed_cleanup, observer_checks(observer, historical))[
            'outer cleanup exactly restored complete baseline']

    wrong_readback = copy.deepcopy(result)
    wrong_readback['outer_cleanup']['final_readback_private_sha256'] = '0' * 64
    tests['reject wrong final cleanup readback hash'] = not result_checks(
        inputs, wrong_readback, observer_checks(observer, historical))[
            'outer cleanup exactly restored complete baseline']

    wrong_classification = copy.deepcopy(result)
    wrong_classification['classification'] = 'qualification broadened'
    tests['reject substituted result classification'] = not result_checks(
        inputs, wrong_classification, observer_checks(observer, historical))[
            'result remains pre-oracle needs-review evidence']

    wrong_limits = copy.deepcopy(result)
    wrong_limits['limits'][0] = 'This qualifies every runtime.'
    tests['reject substituted result limits'] = not result_checks(
        inputs, wrong_limits, observer_checks(observer, historical))[
            'limits retain exact current-runtime scope']

    forged_claim = copy.deepcopy(result)
    forged_claim['claims']['byte_identical_php8426_parity'] = True
    tests['reject forged php8426 parity claim'] = not result_checks(
        inputs, forged_claim, observer_checks(observer, historical))[
            'claim limits are explicit and exact']

    typed_claim = copy.deepcopy(result)
    typed_claim['claims']['current_php8427_application_semantics_qualified'] = 1
    tests['reject int-for-bool result claim'] = not result_checks(
        inputs, typed_claim, observer_checks(observer, historical))[
            'claim limits are explicit and exact']

    auth_raw = dict(raw)
    auth_raw['README.md'] += b'\n{"Authorization":"Bearer secret"}\n'
    tests['reject quoted Authorization value'] = not public_material_checks(
        auth_raw, parsed)['json header and plaintext secret values absent']

    api_raw = dict(raw)
    api_raw['README.md'] += b'\n{"api_key":"secret"}\n'
    tests['reject quoted api_key value'] = not public_material_checks(
        api_raw, parsed)['json header and plaintext secret values absent']

    jwt_raw = dict(raw)
    jwt_raw['README.md'] += (
        b'\neyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJvd25lZCJ9.c2lnbmF0dXJlMQ\n')
    tests['reject raw JWT value'] = not public_material_checks(
        jwt_raw, parsed)['raw jwt values absent']

    header_cases = {
        'Digest Authorization header':
            b'\nAuthorization: Digest username="owned", response="secret"\n',
        'Proxy-Authorization header':
            b'\nProxy-Authorization: Negotiate secret\n',
        'Cookie header': b'\nCookie: session=secret\n',
        'Set-Cookie header': b'\nSet-Cookie: session=secret; HttpOnly\n',
    }
    for label, payload in header_cases.items():
        mutated = dict(raw)
        mutated['README.md'] += payload
        tests[f'reject {label}'] = not public_material_checks(
            mutated, parsed)['json header and plaintext secret values absent']

    plaintext_cases = {
        'unquoted password assignment': b'\npassword=secret\n',
        'unquoted Password field': b'\nPassword: secret\n',
        'unquoted api_key assignment': b'\napi_key=secret\n',
        'unquoted API-Key field': b'\nAPI-Key: secret\n',
    }
    for label, payload in plaintext_cases.items():
        mutated = dict(raw)
        mutated['README.md'] += payload
        tests[f'reject {label}'] = not public_material_checks(
            mutated, parsed)['json header and plaintext secret values absent']

    safe_redactions = dict(raw)
    safe_redactions['README.md'] += (
        b'\nAuthorization: [REDACTED]\nCookie: [REDACTED]\n'
        b'password=[REDACTED]\nAPI-Key: [REDACTED]\n')
    tests['accept exact plaintext redactions'] = public_material_checks(
        safe_redactions, parsed)['json header and plaintext secret values absent']

    signed_url_cases = {
        'AWS signed URL marker':
            b'\nhttps://owned.invalid/object?X-Amz-Signature=secret\n',
        'Google signed URL marker':
            b'\nhttps://owned.invalid/object?X-Goog-Signature=secret\n',
        'generic signed URL marker':
            b'\nhttps://owned.invalid/object?expires=1&sig=secret\n',
    }
    for label, payload in signed_url_cases.items():
        mutated = dict(raw)
        mutated['README.md'] += payload
        tests[f'reject {label}'] = not public_material_checks(
            mutated, parsed)['signed url credential values absent']

    hidden_gate = raw['run-command.txt'].replace(
        b'if [ "${ACTUAL}" != "${EXPECTED}" ]; then',
        b'if false; then :; fi\nif [ "${ACTUAL}" != "${EXPECTED}" ]; then', 1)
    tests['reject false-branch run-command mutation'] = (
        sha256_bytes(hidden_gate) != ARTIFACT_SHA256['run-command.txt'])

    tests['wrong-id replay executes no python'] = executable_wrong_id_negative()

    wrong_source = copy.deepcopy(inputs)
    key = next(iter(DECLARED_REPOSITORY_INPUT_PINS))
    wrong_source['repository_inputs'][key] = '0' * 64
    tests['reject source pin substitution'] = not source_checks(wrong_source)[
        'source manifest in inputs exact']
    return tests


def public_artifact_sha256(raw: dict[str, bytes] | None = None) -> dict[str, str]:
    if raw is None:
        raw = {name: (HERE / name).read_bytes() for name in ARTIFACT_SHA256}
    return {name: sha256_bytes(raw[name]) for name in sorted(raw)}


def render_receipt(checks: dict[str, bool], error: str | None = None,
                   verifier_sha256: str | None = None,
                   artifact_sha256: dict[str, str] | None = None) -> str:
    if verifier_sha256 is None:
        verifier_sha256 = sha256_bytes((HERE / 'verify.py').read_bytes())
    if artifact_sha256 is None:
        artifact_sha256 = public_artifact_sha256()
    receipt = {
        'schema_version': 1,
        'kind': 'kanboard-current-runtime-public-verification',
        'qualification_id': QUALIFICATION_ID,
        'verifier_sha256': verifier_sha256,
        'artifact_sha256': artifact_sha256,
        'status': 'pass' if checks and all(checks.values()) and error is None else 'fail',
        'checks_passed': sum(bool(value) for value in checks.values()),
        'checks_total': len(checks),
        'network_required': False,
        'docker_required': False,
        'checks': [
            {'name': name, 'pass': bool(passed)} for name, passed in checks.items()],
    }
    if error is not None:
        receipt['error'] = error
    return json.dumps(receipt, indent=2) + '\n'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--json-output', type=Path)
    args = parser.parse_args()

    checks: dict[str, bool] = {}
    error = None
    raw: dict[str, bytes] = {}
    verifier_digest = sha256_bytes((HERE / 'verify.py').read_bytes())
    artifact_digests: dict[str, str] = {}
    try:
        raw = {name: (HERE / name).read_bytes() for name in ARTIFACT_SHA256}
        artifact_digests = public_artifact_sha256(raw)
        checks |= artifact_byte_checks(raw)
        if not all(checks.values()):
            raise ValueError('public artifact byte hash mismatch')

        inputs = load_json(raw['inputs.json'], 'inputs.json')
        candidate = load_json(raw['candidate.json'], 'candidate.json')
        runtime = load_json(raw['runtime-admission.json'], 'runtime-admission.json')
        result = load_json(raw['result.json'], 'result.json')
        observer = load_json(
            raw['evidence/observer-results.public.json'],
            'evidence/observer-results.public.json')
        traces = {
            'vulnerable': load_json(
                raw['evidence/vulnerable-requests.json'],
                'evidence/vulnerable-requests.json'),
            'fixed': load_json(
                raw['evidence/fixed-requests.json'],
                'evidence/fixed-requests.json'),
        }
        historical_raw = (
            NATIVE / 'observer-evidence-final/observer-results.json').read_bytes()
        if sha256_bytes(historical_raw) != SOURCE_PINS[
                'evals/native-qualification/observer-evidence-final/observer-results.json']:
            raise ValueError('historical observer result hash mismatch')
        historical = load_json(historical_raw, 'historical observer result')
        parsed = {
            'inputs.json': inputs,
            'candidate.json': candidate,
            'runtime-admission.json': runtime,
            'result.json': result,
            'evidence/observer-results.public.json': observer,
            'evidence/vulnerable-requests.json': traces['vulnerable'],
            'evidence/fixed-requests.json': traces['fixed'],
        }
        observer_results = observer_checks(observer, historical)
        checks |= schema_checks(inputs, candidate, runtime, result, observer, traces)
        checks |= input_checks(inputs)
        checks |= candidate_checks(candidate)
        checks |= runtime_checks(runtime)
        checks |= observer_results
        checks |= trace_checks(traces, observer)
        checks |= result_checks(inputs, result, observer_results)
        checks |= source_checks(inputs)
        checks |= public_material_checks(raw, parsed)
        checks |= command_checks(raw)
        if args.self_test:
            checks |= {f'self-test {name}': passed for name, passed in self_tests(
                raw, inputs, candidate, runtime, result, observer,
                historical, traces, parsed).items()}
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as failure:
        error = f'{type(failure).__name__}: {failure}'

    rendered = render_receipt(
        checks, error, verifier_digest, artifact_digests)
    if args.json_output:
        args.json_output.write_text(rendered)
    print(rendered, end='')
    return 0 if error is None and checks and all(checks.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
