#!/usr/bin/env python3
"""Run the preserved Kanboard observer with the pinned PHP 8.4.27 image."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.request import urlopen


HERE = Path(__file__).resolve().parent.parent
QUALIFICATION_BASE = '8e7b730edce6480eec3c92fc10a21a7cb74147a9'
IMAGE = 't02-kanboard-runtime:amd64-php8427-20261021c'
IMAGE_ID = 'sha256:241dd8f788c62d5c9ef87bdab07ce1f05aca7db0199d532a68b5910c7397f7de'
BASE_IMAGE = ('ghcr.io/anomalyco/opencode@sha256:'
              '85986f556e985e377bd24cd68a5ccfbc647bb49e591194edda8a0e4542303319')
CA_SHA256 = '43e169bf3454bc74c12d3df8c1403f0b4e7da135bf5959f8ab31eb634896bf73'
CA_SIZE = 230249
DOCKERFILE_SHA256 = 'be4948ac34c02f1cf84560f86874f07dc4d6c4b4efc8b1141956d2bf16f7497e'
SOURCE_MANIFEST_SHA256 = 'f5cd14b2cf57039dc75ffb02b31b3acce78afb46877bb58a9108d2120f994d5e'
CHECKS_SHA256 = 'eac607c837d9d356f79662cc0050958d0cf67384565a298be108fedc2636bc94'
CANDIDATE_RECEIPT_SHA256 = 'b988d104545f4ace568a268f79cdf1d2bfb2f686d948ce34f144a01db394df73'
RUNTIME_RECEIPT_SHA256 = '0481663a5d4e62b8ec84054288af98523300128fda04512b02c4e89a77ed1e4c'
OUTER_BASELINE_SHA256 = 'd9de6c807003c1bc84d7d5575fab1bf19281e4c5d964085d13119db274ed2df1'
BUILD_METADATA_SHA256 = '12d9c6ea2780aab8fc7a9b00a288705682a9602ca859b44adad7c95ff83b9a8b'
EVIDENCE = HERE / 't02-evidence/opencode-v2-php-parity-amd64-php8427-20261021c'
CANDIDATE_RECEIPT = EVIDENCE / 'candidate.json'
RUNTIME_RECEIPT = EVIDENCE / 'runtime-admission.json'
DOCKERFILE = HERE / 'Dockerfile.opencode-kanboard-runtime-php8427'
CHECKS = HERE / 'T01-AMD64-KANBOARD-PHP8427-CHECKS-20261021.md'
SOURCE_MANIFEST = HERE / 'T01-AMD64-KANBOARD-PHP8427-SOURCE-MANIFEST.json'
RUNNER = HERE / 'smoke/check_v2_php_parity_amd64.py'
RUNNER_TEST = HERE / 'smoke/check_v2_php_parity_amd64_test.py'
OBSERVER = HERE / 'observer_case.py'
T01_RESULT = HERE / 'observer-evidence-final/observer-results.json'
BRIEF = HERE / 'RESEARCHER-BRIEF.md'
RUNNER_SHA256 = 'bf983ccc93fac42033c7785fab35aa10e263c9035ee8680a3896c183df281927'
RUNNER_TEST_SHA256 = '3bd6542d300de103a8f142655c576de74c6f4665b97a5ee8c57a161b30235c18'
OBSERVER_SHA256 = '72273bfd4e1c1aa9f7f53279e525ec1c74c2669324fa62f1b6b22abf65d596bf'
T01_RESULT_SHA256 = '9db3bc220484a7a786729847f3c8fa8cc1d364a74b1e4a81d2bb78f80dc924fa'
BRIEF_SHA256 = '8f2b5604870cf86719ae94ac180cb6cbe0c5c12cdd2356bc90f4104bb7179a5a'
REQUIRED_PHP_PACKAGES = frozenset({
    'php84', 'php84-ctype', 'php84-dom', 'php84-gd', 'php84-iconv',
    'php84-mbstring', 'php84-openssl', 'php84-pdo_sqlite', 'php84-session',
    'php84-simplexml', 'php84-xml',
})

_CANDIDATE_KEYS = {
    'schema_version', 'kind', 'recorded_at', 'status', 'scope',
    'parity_status', 'qualification_base', 'platform', 'tag', 'image_id',
    'image_execution_attempted', 'build_inputs', 'image_inspection',
    'outer_baseline', 'archives', 'execution', 'claim_limits',
}
_BUILD_INPUT_KEYS = {
    'source_manifest_sha256', 'dockerfile_path', 'dockerfile_sha256', 'base',
    'base_override_used', 'context', 'platform', 'load',
    'build_metadata_private_sha256', 'managed_ca',
}
_CA_KEYS = {
    'source_class', 'sha256', 'size_bytes', 'buildkit_secret_id',
    'buildkit_target', 'persisted_in_image', 'system_trust_changed',
    'bytes_recorded', 'proxy_values_recorded',
}
_INSPECTION_KEYS = {
    'metadata_only', 'id', 'repo_tags', 'repo_digests', 'os', 'architecture',
    'size_bytes', 'created',
}
_BASELINE_KEYS = {
    'private_receipt_sha256', 'candidate_tag_absent_before_build',
    'candidate_image_absent_before_build', 'containers_before',
    'images_before', 'volumes_before', 'build_cache_records_before',
    'cleanup_pending',
}
_EXECUTION_KEYS = {
    'docker_run_calls', 'package_probes', 'php_probes', 'archives_retrieved',
    'archives_verified', 'archives_extracted', 'application_containers_started',
    'application_arms_started', 'provider_calls', 'model_calls',
    'live_targets_contacted', 'external_credentials_used',
    'researcher_bundle_created',
}
_CLAIM_KEYS = {
    'php_package_revision_qualified', 'application_semantics_qualified',
    'historical_semantic_comparison_complete', 'byte_identical_php8426_parity',
}
EXPECTED_PINS = {
    'vulnerable': (
        'f0f7d27007f5a788f14416c548421efd740b7bce',
        '3f24269475bf00137d4b0d957d97a2567a5249101dad89067a49d609f4df2edf'),
    'fixed': (
        'a98bc5f855d4e7e47eb3425a6c7da6c6cc6748a3',
        '44db3df81a25bbd56c768c8b3180a1f05879e2c7fbaa6ac73707e7f3e9098f56'),
}


@dataclass(frozen=True)
class Candidate:
    tag: str
    image_id: str
    dockerfile_sha256: str


@dataclass(frozen=True)
class RuntimeAdmission:
    image_id: str
    php_version: str
    php_modules: tuple[str, ...]
    packages: tuple[str, ...]


def _strict_json(raw: bytes) -> dict:
    def pairs(values: list[tuple[str, object]]) -> dict:
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError(f'duplicate JSON key: {key}')
            result[key] = value
        return result

    value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs)
    if not isinstance(value, dict):
        raise ValueError('receipt must be a JSON object')
    return value


def parse_candidate_receipt(raw: bytes, expected_sha256: str) -> Candidate:
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('candidate receipt hash mismatch')
    value = _strict_json(raw)
    if set(value) != _CANDIDATE_KEYS:
        raise ValueError('candidate receipt keys differ from the fixed schema')
    build = value.get('build_inputs')
    if not isinstance(build, dict) or set(build) != _BUILD_INPUT_KEYS:
        raise ValueError('candidate build input keys differ from the fixed schema')
    ca = build.get('managed_ca')
    inspection = value.get('image_inspection')
    baseline = value.get('outer_baseline')
    archives = value.get('archives')
    execution = value.get('execution')
    claims = value.get('claim_limits')
    if not isinstance(ca, dict) or set(ca) != _CA_KEYS:
        raise ValueError('managed CA keys differ from the fixed schema')
    if not isinstance(inspection, dict) or set(inspection) != _INSPECTION_KEYS:
        raise ValueError('image inspection keys differ from the fixed schema')
    if not isinstance(baseline, dict) or set(baseline) != _BASELINE_KEYS:
        raise ValueError('outer baseline keys differ from the fixed schema')
    if not isinstance(execution, dict) or set(execution) != _EXECUTION_KEYS:
        raise ValueError('execution keys differ from the fixed schema')
    if not isinstance(claims, dict) or set(claims) != _CLAIM_KEYS:
        raise ValueError('claim-limit keys differ from the fixed schema')
    if not isinstance(archives, dict) or set(archives) != set(EXPECTED_PINS):
        raise ValueError('archive keys differ from the fixed schema')
    for label, (commit, digest) in EXPECTED_PINS.items():
        archive = archives.get(label)
        if (not isinstance(archive, dict)
                or set(archive) != {'commit', 'sha256', 'retrieved'}
                or archive != {
                    'commit': commit, 'sha256': digest, 'retrieved': False}):
            raise ValueError(f'{label} archive registration is not pristine')
    image_id = value.get('image_id')
    dockerfile_sha256 = build.get('dockerfile_sha256')
    checks = (
        value.get('schema_version') == 1,
        value.get('kind') == 't01-cloud-amd64-kanboard-php8427-candidate',
        isinstance(value.get('recorded_at'), str)
        and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ', value['recorded_at']),
        value.get('status') == 'pass',
        value.get('scope') == 'build-and-registration-only',
        value.get('parity_status') == 'not_run',
        value.get('qualification_base') == QUALIFICATION_BASE,
        value.get('platform') == 'linux/amd64',
        value.get('tag') == IMAGE,
        image_id == IMAGE_ID,
        value.get('image_execution_attempted') is False,
        build.get('source_manifest_sha256') == SOURCE_MANIFEST_SHA256,
        build.get('dockerfile_path')
        == 'evals/native-qualification/Dockerfile.opencode-kanboard-runtime-php8427',
        dockerfile_sha256 == DOCKERFILE_SHA256,
        build.get('base') == BASE_IMAGE,
        build.get('base_override_used') is False,
        build.get('context') == 'evals/native-qualification',
        build.get('platform') == 'linux/amd64',
        build.get('load') is True,
        build.get('build_metadata_private_sha256') == BUILD_METADATA_SHA256,
        ca == {
            'source_class': 'existing managed combined CA bundle',
            'sha256': CA_SHA256,
            'size_bytes': CA_SIZE,
            'buildkit_secret_id': 'proxy_ca',
            'buildkit_target': '/etc/apk/ca.pem',
            'persisted_in_image': False,
            'system_trust_changed': False,
            'bytes_recorded': False,
            'proxy_values_recorded': False,
        },
        inspection.get('metadata_only') is True,
        inspection.get('id') == IMAGE_ID,
        inspection.get('repo_tags') == [IMAGE],
        inspection.get('repo_digests') == [],
        inspection.get('os') == 'linux',
        inspection.get('architecture') == 'amd64',
        type(inspection.get('size_bytes')) is int and inspection['size_bytes'] > 0,
        isinstance(inspection.get('created'), str) and bool(inspection['created']),
        baseline == {
            'private_receipt_sha256': OUTER_BASELINE_SHA256,
            'candidate_tag_absent_before_build': True,
            'candidate_image_absent_before_build': True,
            'containers_before': 0,
            'images_before': 0,
            'volumes_before': 0,
            'build_cache_records_before': 0,
            'cleanup_pending': True,
        },
        all(value == 0 for key, value in execution.items()
            if key != 'researcher_bundle_created'),
        execution.get('researcher_bundle_created') is False,
        all(value is False for value in claims.values()),
    )
    if not all(checks):
        raise ValueError('candidate receipt violates the fixed policy')
    return Candidate(IMAGE, image_id, dockerfile_sha256)


def runtime_check_results(image_info: dict, php_version: str,
                          php_modules: list[str], packages: list[str],
                          candidate: Candidate,
                          dockerfile_sha256: str) -> dict[str, bool]:
    modules = {value.lower() for value in php_modules}
    required = {f'{name}-8.4.27-r0' for name in REQUIRED_PHP_PACKAGES}
    php_packages = [value for value in packages if value.startswith('php84')]
    return {
        'exact_image_id': image_info.get('Id') == candidate.image_id,
        'expected_tag': candidate.tag in (image_info.get('RepoTags') or []),
        'linux_amd64': (
            image_info.get('Os') == 'linux'
            and image_info.get('Architecture') == 'amd64'),
        'dockerfile_pin': dockerfile_sha256 == candidate.dockerfile_sha256,
        'php_8_4_27': php_version.startswith('PHP 8.4.27 '),
        'required_php_modules': {'gd', 'pdo_sqlite'} <= modules,
        'required_php_packages': required <= set(packages),
        'all_php84_packages_8_4_27_r0': (
            bool(php_packages)
            and all(value.endswith('-8.4.27-r0') for value in php_packages)),
    }


def admit_and_probe_image(image_info: dict, dockerfile_sha256: str, check,
                          candidate: Candidate, command_runner):
    identity = runtime_check_results(
        image_info, '', [], [], candidate, dockerfile_sha256)
    for name in ('exact_image_id', 'expected_tag', 'linux_amd64',
                 'dockerfile_pin'):
        check(name.replace('_', ' '), identity[name])

    commands = (
        ['docker', 'run', '--rm', '--pull=never', '--network', 'none',
         '--entrypoint', 'apk', candidate.image_id, 'info', '-v'],
        ['docker', 'run', '--rm', '--pull=never', '--network', 'none',
         '--entrypoint', 'php', candidate.image_id, '-v'],
        ['docker', 'run', '--rm', '--pull=never', '--network', 'none',
         '--entrypoint', 'php', candidate.image_id, '-m'],
    )
    results = [command_runner.run(
        command, capture_output=True, text=True) for command in commands]
    packages = results[0].stdout.splitlines() if results[0].returncode == 0 else []
    php_version = (
        results[1].stdout.splitlines()[0]
        if results[1].returncode == 0 and results[1].stdout.splitlines() else '')
    php_modules = (
        sorted(set(results[2].stdout.splitlines()))
        if results[2].returncode == 0 else [])
    runtime = runtime_check_results(
        image_info, php_version, php_modules, packages, candidate,
        dockerfile_sha256)
    for name in ('php_8_4_27', 'required_php_modules',
                 'required_php_packages', 'all_php84_packages_8_4_27_r0'):
        check(name.replace('_', ' '), runtime[name])
    return php_version, php_modules


def php8427_observer_check_results(current: dict, original: dict,
                                   preserved_checker, image_id: str):
    checks = dict(preserved_checker(current, original))
    arms = current.get('arms')
    by_release = {}
    if isinstance(arms, list) and len(arms) == 2 and all(
            isinstance(arm, dict) for arm in arms):
        by_release = {arm.get('release'): arm for arm in arms}
    checks['current_runtime_both_arms'] = (
        set(by_release) == {'vulnerable', 'fixed'}
        and all(
            arm.get('runtime') == image_id
            and str(arm.get('php', '')).startswith('PHP 8.4.27 ')
            for arm in by_release.values()))
    return checks


def parse_runtime_receipt(raw: bytes, expected_sha256: str) -> RuntimeAdmission:
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('runtime receipt hash mismatch')
    value = _strict_json(raw)
    expected_top = {
        'schema_version', 'kind', 'recorded_at', 'status', 'scope',
        'candidate_receipt_sha256', 'image_id', 'platform', 'execution_policy',
        'packages', 'php', 'application_qualification', 'external_activity',
        'claim_limits',
    }
    if set(value) != expected_top:
        raise ValueError('runtime receipt keys differ from the fixed schema')
    policy = value.get('execution_policy')
    packages = value.get('packages')
    php = value.get('php')
    application = value.get('application_qualification')
    external = value.get('external_activity')
    claims = value.get('claim_limits')
    schemas = (
        (policy, {'immutable_image_id_only', 'pull', 'network', 'commands',
                  'exit_codes', 'container_ids_retained'}),
        (packages, {'required_revision', 'required_packages',
                    'installed_php84_packages', 'required_packages_present',
                    'all_installed_php84_packages_match_revision',
                    'mixed_php84_revision_detected', 'apk_index_warnings_observed',
                    'apk_index_warning_context'}),
        (php, {'version_line', 'version_matches', 'modules', 'required_modules',
               'required_modules_present'}),
        (application, {'archives_retrieved', 'application_arms_started', 'status'}),
        (external, {'provider_calls', 'model_calls', 'live_targets_contacted',
                    'external_credentials_used', 'researcher_bundle_created'}),
        (claims, {'application_semantics_qualified',
                  'historical_semantic_comparison_complete',
                  'byte_identical_php8426_parity'}),
    )
    if any(not isinstance(item, dict) or set(item) != keys
           for item, keys in schemas):
        raise ValueError('runtime receipt nested keys differ from the fixed schema')
    command_prefix = [
        'docker', 'run', '--rm', '--pull=never', '--network', 'none',
        '--entrypoint']
    expected_commands = [
        command_prefix + ['apk', IMAGE_ID, 'info', '-v'],
        command_prefix + ['php', IMAGE_ID, '-v'],
        command_prefix + ['php', IMAGE_ID, '-m'],
    ]
    installed = packages.get('installed_php84_packages')
    modules = php.get('modules')
    required_package_strings = {
        f'{name}-8.4.27-r0' for name in REQUIRED_PHP_PACKAGES}
    checks = (
        value.get('schema_version') == 1,
        value.get('kind') == 't01-cloud-amd64-kanboard-php8427-runtime-admission',
        isinstance(value.get('recorded_at'), str)
        and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ', value['recorded_at']),
        value.get('status') == 'pass',
        value.get('scope') == 'immutable-image package-and-php admission only',
        value.get('candidate_receipt_sha256') == CANDIDATE_RECEIPT_SHA256,
        value.get('image_id') == IMAGE_ID,
        value.get('platform') == 'linux/amd64',
        policy.get('immutable_image_id_only') is True,
        policy.get('pull') == 'never',
        policy.get('network') == 'none',
        policy.get('commands') == expected_commands,
        policy.get('exit_codes') == [0, 0, 0],
        policy.get('container_ids_retained') is False,
        packages.get('required_revision') == '8.4.27-r0',
        set(packages.get('required_packages') or []) == REQUIRED_PHP_PACKAGES,
        isinstance(installed, list) and required_package_strings <= set(installed),
        isinstance(installed, list) and bool(installed)
        and all(isinstance(item, str) and item.startswith('php84')
                and item.endswith('-8.4.27-r0') for item in installed),
        packages.get('required_packages_present') is True,
        packages.get('all_installed_php84_packages_match_revision') is True,
        packages.get('mixed_php84_revision_detected') is False,
        packages.get('apk_index_warnings_observed') is True,
        isinstance(packages.get('apk_index_warning_context'), str)
        and '--network none' in packages['apk_index_warning_context'],
        isinstance(php.get('version_line'), str)
        and php['version_line'].startswith('PHP 8.4.27 '),
        php.get('version_matches') is True,
        isinstance(modules, list) and {'gd', 'pdo_sqlite'} <= {
            str(item).lower() for item in modules},
        php.get('required_modules') == ['gd', 'pdo_sqlite'],
        php.get('required_modules_present') is True,
        application == {
            'archives_retrieved': 0,
            'application_arms_started': 0,
            'status': 'not_run',
        },
        external == {
            'provider_calls': 0,
            'model_calls': 0,
            'live_targets_contacted': 0,
            'external_credentials_used': 0,
            'researcher_bundle_created': False,
        },
        claims == {
            'application_semantics_qualified': False,
            'historical_semantic_comparison_complete': False,
            'byte_identical_php8426_parity': False,
        },
    )
    if not all(checks):
        raise ValueError('runtime receipt violates the fixed policy')
    return RuntimeAdmission(IMAGE_ID, php['version_line'], tuple(modules),
                            tuple(installed))


def fetch_verified_archives(pins: dict[str, tuple[str, str]], opener,
                            byte_limit: int) -> dict[str, bytes]:
    archives = {}
    for label in ('vulnerable', 'fixed'):
        commit, digest = pins[label]
        url = f'https://codeload.github.com/kanboard/kanboard/tar.gz/{commit}'
        chunks = []
        size = 0
        with opener(url, timeout=60) as response:
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > byte_limit:
                    raise RuntimeError(f'{label} archive exceeds byte limit')
                chunks.append(chunk)
        raw = b''.join(chunks)
        if hashlib.sha256(raw).hexdigest() != digest:
            raise RuntimeError(f'{label} archive hash mismatch')
        archives[label] = raw
    return archives


class GuardedUrlopen:
    """Serve verified archive bytes and allow only loopback readiness calls."""

    def __init__(self, archives: dict[str, bytes], readiness_opener):
        if set(archives) != set(EXPECTED_PINS):
            raise ValueError('both verified archives are required')
        self._archive_urls = {
            f'https://codeload.github.com/kanboard/kanboard/tar.gz/{commit}':
            archives[label]
            for label, (commit, _digest) in EXPECTED_PINS.items()
        }
        self._readiness_opener = readiness_opener
        self._served: set[str] = set()

    def __call__(self, url, *args, **kwargs):
        if not isinstance(url, str):
            raise RuntimeError('URL rejected by qualification guard')
        if url in self._archive_urls:
            if url in self._served:
                raise RuntimeError('URL rejected after archive was already served')
            self._served.add(url)
            return io.BytesIO(self._archive_urls[url])
        match = re.fullmatch(
            r'http://127\.0\.0\.1:([1-9][0-9]{0,4})/robots\.txt', url)
        if match and int(match.group(1)) <= 65535:
            return self._readiness_opener(url, *args, **kwargs)
        raise RuntimeError('URL rejected by qualification guard')


class ObserverSubprocess:
    """Permit only the observer's fixed Docker command shapes."""

    def __init__(self, delegate, image_id: str):
        self._delegate = delegate
        self._image_id = image_id
        self._containers: set[str] = set()

    def __getattr__(self, name):
        return getattr(self._delegate, name)

    @staticmethod
    def _argv(argv, kwargs) -> list[str]:
        if kwargs.get('shell') is True or not isinstance(argv, (list, tuple)):
            raise RuntimeError('subprocess command rejected')
        if not all(isinstance(item, str) for item in argv):
            raise RuntimeError('subprocess command rejected')
        return list(argv)

    def _server_run(self, command: list[str]) -> bool:
        if len(command) != 31:
            return False
        fixed = {
            0: 'docker', 1: 'run', 2: '-d', 3: '--rm', 4: '--pull=never',
            5: '--read-only', 6: '--user', 8: '--network', 9: 'bridge',
            10: '--memory', 11: '512m', 12: '--cpus', 13: '2',
            14: '--pids-limit', 15: '128', 16: '--tmpfs',
            17: '/tmp:rw,nosuid,size=64m', 18: '-p', 20: '--mount',
            22: '--workdir', 23: '/app', 24: '--entrypoint', 25: 'php',
            26: self._image_id, 27: '-S', 29: '-t', 30: '/app',
        }
        if any(command[index] != value for index, value in fixed.items()):
            return False
        if not re.fullmatch(r'[0-9]+', command[7]):
            return False
        port = re.fullmatch(r'127\.0\.0\.1:([1-9][0-9]{0,4}):\1', command[19])
        if not port or int(port.group(1)) > 65535:
            return False
        if command[28] != f'0.0.0.0:{port.group(1)}':
            return False
        mount = re.fullmatch(r'type=bind,source=([^,\n]+),target=/app', command[21])
        return bool(mount and Path(mount.group(1)).is_absolute())

    def check_output(self, argv, *args, **kwargs):
        command = self._argv(argv, kwargs)
        if command[:2] != ['docker', 'run']:
            if (command[:2] == ['docker', 'logs'] and len(command) == 3
                    and command[2] in self._containers):
                return self._delegate.check_output(command, *args, **kwargs)
            if command and command[0] == 'docker':
                raise RuntimeError('Docker command rejected by observer guard')
            return self._delegate.check_output(command, *args, **kwargs)
        if self._server_run(command):
            output = self._delegate.check_output(command, *args, **kwargs)
            container_id = output.strip() if isinstance(output, str) else output.strip().decode()
            if not re.fullmatch(r'[0-9a-f]{64}', container_id):
                raise RuntimeError('observer returned an invalid container ID')
            self._containers.add(container_id)
            return output
        version = [
            'docker', 'run', '--rm', '--network', 'none', '--entrypoint',
            'php', self._image_id, '--version',
        ]
        if command == version:
            admitted = command[:3] + ['--pull=never'] + command[3:]
            return self._delegate.check_output(admitted, *args, **kwargs)
        raise RuntimeError('Docker run rejected by observer guard')

    def run(self, argv, *args, **kwargs):
        command = self._argv(argv, kwargs)
        allowed = (
            len(command) == 5
            and command[:4] == ['docker', 'stop', '--time', '5']
            and command[4] in self._containers
        ) or (
            len(command) == 3
            and command[:2] == ['docker', 'inspect']
            and command[2] in self._containers
        )
        if command and command[0] == 'docker' and not allowed:
            raise RuntimeError('Docker command rejected by observer guard')
        return self._delegate.run(command, *args, **kwargs)


def runner_bindings(candidate: Candidate) -> dict[str, object]:
    return {
        'QUALIFICATION_BASE': QUALIFICATION_BASE,
        'IMAGE': candidate.tag,
        'IMAGE_ID': candidate.image_id,
        'IMAGE_RUNTIME_LABEL': candidate.image_id,
        'DOCKERFILE': DOCKERFILE,
        'DOCKERFILE_SHA256': candidate.dockerfile_sha256,
        'CHECKS': CHECKS,
        'RUNTIME_BUILD': CANDIDATE_RECEIPT,
        'RUNTIME_BUILD_SHA256': CANDIDATE_RECEIPT_SHA256,
    }


def _strict_artifact_checker(preserved_checker):
    def check(traces, texts, forbidden_roots):
        checks = dict(preserved_checker(traces, texts, forbidden_roots))
        serialized = json.dumps(traces, sort_keys=True) + '\n' + '\n'.join(
            texts.values())
        sensitive = re.compile(
            r'(?i)(?:authorization\s*[:=]|basic\s+[a-z0-9+/=]{8,}|'
            r'"(?:authorization|api[_-]?key|cookie|token|access_token|password)"'
            r'\s*:\s*"(?!\[REDACTED\])[^\"]+")')
        checks['authorization_cookie_token_values_absent'] = (
            sensitive.search(serialized) is None)
        return checks
    return check


def _public_result_sanitizer(preserved_sanitizer):
    def sanitize(value):
        public = preserved_sanitizer(value)
        for arm in public.get('arms', []):
            cleanup = arm.get('cleanup', {})
            for name in ('container_id', 'host_pid', 'loopback_port'):
                if cleanup.get(name) is not None:
                    cleanup[name] = '[REDACTED]'
        return public
    return sanitize


@contextmanager
def installed_runner_adapter(runner, candidate: Candidate,
                             archives: dict[str, bytes]):
    if runner.observer_case.PINS != EXPECTED_PINS:
        raise RuntimeError('preserved observer archive pins changed')
    bindings = runner_bindings(candidate)
    old_bindings = {name: getattr(runner, name) for name in bindings}
    function_names = (
        'admit_and_probe_image', 'observer_check_results',
        'artifact_check_results', 'public_observer_result')
    old_functions = {name: getattr(runner, name) for name in function_names}
    observer = runner.observer_case
    old_observer = {
        name: getattr(observer, name)
        for name in ('urlopen', 'subprocess', 'PHP_IMAGE', 'PHP_IMAGE_DIGEST')}
    try:
        for name, value in bindings.items():
            setattr(runner, name, value)
        runner.admit_and_probe_image = lambda info, digest, check: (
            admit_and_probe_image(
                info, digest, check, candidate, runner.subprocess))
        runner.observer_check_results = lambda current, original: (
            php8427_observer_check_results(
                current, original, old_functions['observer_check_results'],
                candidate.image_id))
        runner.artifact_check_results = _strict_artifact_checker(
            old_functions['artifact_check_results'])
        runner.public_observer_result = _public_result_sanitizer(
            old_functions['public_observer_result'])
        observer.urlopen = GuardedUrlopen(archives, old_observer['urlopen'])
        observer.subprocess = ObserverSubprocess(
            old_observer['subprocess'], candidate.image_id)
        yield runner
    finally:
        for name, value in old_bindings.items():
            setattr(runner, name, value)
        for name, value in old_functions.items():
            setattr(runner, name, value)
        for name, value in old_observer.items():
            setattr(observer, name, value)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_fixed_policy() -> tuple[Candidate, RuntimeAdmission]:
    pins = {
        RUNNER: RUNNER_SHA256,
        RUNNER_TEST: RUNNER_TEST_SHA256,
        OBSERVER: OBSERVER_SHA256,
        T01_RESULT: T01_RESULT_SHA256,
        BRIEF: BRIEF_SHA256,
        DOCKERFILE: DOCKERFILE_SHA256,
        CHECKS: CHECKS_SHA256,
        SOURCE_MANIFEST: SOURCE_MANIFEST_SHA256,
        CANDIDATE_RECEIPT: CANDIDATE_RECEIPT_SHA256,
        RUNTIME_RECEIPT: RUNTIME_RECEIPT_SHA256,
    }
    changed = [str(path.relative_to(HERE)) for path, digest in pins.items()
               if not path.is_file() or _sha256(path) != digest]
    if changed:
        raise RuntimeError('pinned source changed: ' + ', '.join(changed))
    candidate = parse_candidate_receipt(
        CANDIDATE_RECEIPT.read_bytes(), CANDIDATE_RECEIPT_SHA256)
    runtime = parse_runtime_receipt(
        RUNTIME_RECEIPT.read_bytes(), RUNTIME_RECEIPT_SHA256)
    if runtime.image_id != candidate.image_id:
        raise RuntimeError('runtime receipt image differs from candidate')
    return candidate, runtime


def load_preserved_runner():
    if _sha256(RUNNER) != RUNNER_SHA256 or _sha256(OBSERVER) != OBSERVER_SHA256:
        raise RuntimeError('preserved runner or observer changed before import')
    existing = sys.modules.get('observer_case')
    if existing is not None:
        existing_path = Path(getattr(existing, '__file__', '')).resolve()
        if existing_path != OBSERVER.resolve():
            raise RuntimeError('conflicting observer_case module is already loaded')
        observer = existing
    else:
        observer_spec = importlib.util.spec_from_file_location(
            'observer_case', OBSERVER)
        if observer_spec is None or observer_spec.loader is None:
            raise RuntimeError('cannot load preserved observer')
        observer = importlib.util.module_from_spec(observer_spec)
        sys.modules['observer_case'] = observer
        observer_spec.loader.exec_module(observer)
    runner_name = '_t01_preserved_amd64_runner_for_php8427'
    if runner_name in sys.modules:
        raise RuntimeError('preserved runner is already loaded')
    runner_spec = importlib.util.spec_from_file_location(runner_name, RUNNER)
    if runner_spec is None or runner_spec.loader is None:
        raise RuntimeError('cannot load preserved runner')
    runner = importlib.util.module_from_spec(runner_spec)
    sys.modules[runner_name] = runner
    try:
        runner_spec.loader.exec_module(runner)
    except Exception:
        sys.modules.pop(runner_name, None)
        raise
    if runner.observer_case is not observer:
        raise RuntimeError('preserved runner imported a different observer')
    if (_sha256(RUNNER) != RUNNER_SHA256
            or _sha256(OBSERVER) != OBSERVER_SHA256):
        raise RuntimeError('preserved source changed during import')
    return runner


def inspect_candidate(candidate: Candidate) -> dict:
    inspected = subprocess.run(
        ['docker', 'image', 'inspect', candidate.tag],
        capture_output=True, text=True)
    if inspected.returncode != 0:
        raise RuntimeError('registered candidate image is unavailable without pull')
    try:
        values = json.loads(inspected.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError('candidate image inspection returned invalid JSON') from error
    if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], dict):
        raise RuntimeError('candidate image inspection returned an unexpected shape')
    info = values[0]
    identity = runtime_check_results(
        info, '', [], [], candidate, _sha256(DOCKERFILE))
    for name in ('exact_image_id', 'expected_tag', 'linux_amd64',
                 'dockerfile_pin'):
        if not identity[name]:
            raise RuntimeError('candidate image failed ' + name.replace('_', ' '))
    return info


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.parse_args()

    candidate, _runtime = load_fixed_policy()
    inspect_candidate(candidate)
    archives = fetch_verified_archives(EXPECTED_PINS, urlopen, 128 * 1024 * 1024)
    runner = load_preserved_runner()
    with installed_runner_adapter(runner, candidate, archives):
        return runner.main()


if __name__ == '__main__':
    raise SystemExit(main())
