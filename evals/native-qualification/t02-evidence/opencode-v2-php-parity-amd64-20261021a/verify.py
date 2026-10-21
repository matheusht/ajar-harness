#!/usr/bin/env python3
"""Verify the sanitized, blocked amd64 parity receipt without Docker/network."""

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
EXPECTED_BASE = '513b662eda0345d943eb0582f7bc39a8a6512617'
EXPECTED_IMAGE = 'sha256:9ef722322521322a1288a18427ba5bf6ce1479085c97e0ac821982eec4f01769'
ACTUAL_IMAGE = 'sha256:d0b96c08541486079634fd70a0ffb221c32b07a2a04a1a2ab7d041912a7c9a91'
EXPECTED_NETWORKS = {
    ('bridge', '1050252286e8631bf8ee038d52cc1cffb8307746317da75e16c8c33afbde07ba'),
    ('host', 'dc064e5cfa5c545dfe98b45b11f9bd068174af23daf4b5e8155a9ada938b68bb'),
    ('none', '8065fb4aff55641f71f0708775e982d2e8bda062d0ac7ffd91c29ce55e43b216'),
}
EXPECTED_REPOSITORY_INPUTS = {
    'Dockerfile.opencode-kanboard-runtime':
        '7a1ab9b257fb36a216fc1baafabc757436d0a15ffcb9498b6fbe697da3a9bf4b',
    'observer_case.py':
        '72273bfd4e1c1aa9f7f53279e525ec1c74c2669324fa62f1b6b22abf65d596bf',
    'observer-evidence-final/observer-results.json':
        '9db3bc220484a7a786729847f3c8fa8cc1d364a74b1e4a81d2bb78f80dc924fa',
    'CHECKS.md':
        'aad8009c7d1870cf278c192fb97d36d01829428c02ffedf377072af8a527cd19',
    'RESEARCHER-BRIEF.md':
        '8f2b5604870cf86719ae94ac180cb6cbe0c5c12cdd2356bc90f4104bb7179a5a',
    'T02-PHP-PARITY-CHECKS-20261020.md':
        '850a68458864f8e0cb4850e36c71c7589c4b570cefbb9205071b4aaa26cabe37',
    'T02-RESEARCHER-BRIEF-PHP-8.4.26.md':
        '40044703ca38909e80b1db6f79694ed98e27e5892aedf9e269b4256188ad837e',
    'T02-AMD64-PHP-PARITY-CHECKS-20261021.md':
        '5b1adcd37762ae68f302ede6aca2c51437e3031220ce6c2999c0a47627ffafb5',
    'smoke/check_v2_php_parity.py':
        'e30a0f8237b5dcfb546611c8952a0699c013b7786d14d144bc08caa148935616',
    'smoke/check_v2_php_parity_amd64.py':
        'bf983ccc93fac42033c7785fab35aa10e263c9035ee8680a3896c183df281927',
    'smoke/check_v2_php_parity_amd64_test.py':
        '3bd6542d300de103a8f142655c576de74c6f4665b97a5ee8c57a161b30235c18',
    't02-evidence/live-preparation-owned-20261021a/runtime-build.json':
        'e21c872cbefc53022d6dd6f23b88795e873de93c1a183d7adcdb3883fbfc2c8c',
}
EXPECTED_ARCHIVES = {
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


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def receipt_checks(result: dict, inputs: dict, command: str, readme: str) -> dict[str, bool]:
    admission = result.get('admission', {})
    execution = result.get('execution', {})
    cleanup = result.get('cleanup', {})
    runtime = inputs.get('expected_runtime', {})
    archives = inputs.get('archives', {})
    final_networks = {
        (item.get('name'), item.get('id'))
        for item in cleanup.get('final_networks', []) if isinstance(item, dict)}
    serialized = (json.dumps({'result': result, 'inputs': inputs}, sort_keys=True)
                  + command + readme)
    secret_pattern = re.compile(
        r'(?i)(authorization\s*[:=]|basic\s+[a-z0-9+/=]{8,}|'
        r'"(?:cookie|token|access_token|password)"\s*:\s*"[^"]+"|'
        r'https?_proxy\s*=|-----begin [^-]+private key-----)')

    return {
        'qualification base pinned': (
            result.get('qualification_base') == EXPECTED_BASE
            and inputs.get('qualification_base') == EXPECTED_BASE),
        'expected image pinned': (
            admission.get('expected_image_id') == EXPECTED_IMAGE
            and runtime.get('image_id') == EXPECTED_IMAGE
            and runtime.get('tag') == 't02-kanboard-runtime:amd64-live-prep'
            and runtime.get('base')
            == 'ghcr.io/anomalyco/opencode@sha256:'
               '85986f556e985e377bd24cd68a5ccfbc647bb49e591194edda8a0e4542303319'),
        'mismatch retained': (
            result.get('status') == 'blocked_exact_image_unavailable'
            and admission.get('build_exit_code') == 0
            and admission.get('actual_image_id') == ACTUAL_IMAGE
            and admission.get('actual_image_platform') == 'linux/amd64'
            and admission.get('actual_image_inspect', {}).get('repo_tags')
            == ['t02-kanboard-runtime:amd64-live-prep']
            and admission.get('actual_image_inspect', {}).get('repo_digests') == []
            and admission.get('actual_image_id') != admission.get('expected_image_id')
            and admission.get('exact_image_id_match') is False
            and admission.get('decision')
            == 'stop_before_archive_retrieval_or_application_execution'),
        'no parity claim': (
            execution.get('parity_runner_executed') is False
            and execution.get('parity_established') is False
            and execution.get('ordinary_behavior_run') is False
            and execution.get('vulnerable_arm_run') is False
            and execution.get('fixed_arm_run') is False),
        'archives not retrieved': (
            execution.get('archive_retrieval_attempted') is False
            and execution.get('archives_verified') == 0
            and archives == EXPECTED_ARCHIVES),
        'zero external execution': (
            execution.get('application_containers_started') == 0
            and execution.get('researcher_bundle_created') is False
            and execution.get('provider_calls') == 0
            and execution.get('model_calls') == 0
            and execution.get('live_targets_contacted') == 0
            and execution.get('credentials_used') == 0),
        'cleanup exact': (
            cleanup.get('mismatched_image_removed') is True
            and cleanup.get('removed_image_id') == ACTUAL_IMAGE
            and len(cleanup.get('build_cache_records_removed', [])) == 7
            and len(set(cleanup.get('build_cache_records_removed', []))) == 7
            and cleanup.get('global_prune_used') is False
            and cleanup.get('final_task_tag_absent') is True
            and cleanup.get('final_containers') == []
            and cleanup.get('final_images') == []
            and cleanup.get('final_volumes') == []
            and cleanup.get('final_build_cache_bytes') == 0
            and cleanup.get('network_ids_match_baseline') is True
            and final_networks == EXPECTED_NETWORKS
            and cleanup.get('baseline_restored') is True),
        'command marks blocked boundary': (
            EXPECTED_IMAGE in command and ACTUAL_IMAGE in command
            and ': "${PARITY_CA_BUNDLE:?' in command
            and ': "${PARITY_OUTPUT:?' in command
            and 'if [ "${ACTUAL_IMAGE_ID}" != "${EXPECTED_IMAGE_ID}" ]; then' in command
            and '  exit 1\n' in command
            and 'python3 evals/native-qualification/smoke/' in command
            and command.index('  exit 1\n')
            < command.index('python3 evals/native-qualification/smoke/')),
        'readme states blocked scope': (
            'blocked before parity execution' in readme
            and 'does not establish current-image Kanboard parity' in readme
            and re.search(r'different rebuild must\s+not be substituted', readme) is not None),
        'no raw secret material': (
            secret_pattern.search(serialized) is None
            and '/workspace/' not in serialized
            and '/private/tmp/' not in serialized),
    }


def source_checks(inputs: dict) -> dict[str, bool]:
    pins = inputs.get('repository_inputs', {})
    checks = {'source pin manifest exact': pins == EXPECTED_REPOSITORY_INPUTS}
    checks.update({
        f'source pin {relative}': (NATIVE / relative).is_file()
        and sha256(NATIVE / relative) == digest
        for relative, digest in EXPECTED_REPOSITORY_INPUTS.items()})
    return checks


def verify(result: dict, inputs: dict, command: str, readme: str) -> dict[str, bool]:
    return receipt_checks(result, inputs, command, readme) | source_checks(inputs)


def self_test(result: dict, inputs: dict, command: str, readme: str) -> dict[str, bool]:
    tests = {}
    forged = copy.deepcopy(result)
    forged['status'] = 'pass'
    forged['execution']['parity_runner_executed'] = True
    forged['execution']['parity_established'] = True
    forged_checks = receipt_checks(forged, inputs, command, readme)
    tests['reject false parity upgrade'] = (
        not forged_checks['mismatch retained'] and not forged_checks['no parity claim'])

    substituted = copy.deepcopy(result)
    substituted['admission']['actual_image_id'] = EXPECTED_IMAGE
    substitution_checks = receipt_checks(substituted, inputs, command, readme)
    tests['reject inconsistent exact-image substitution'] = not substitution_checks['mismatch retained']

    dirty = copy.deepcopy(result)
    dirty['cleanup']['final_images'] = [ACTUAL_IMAGE]
    tests['reject incomplete cleanup'] = not receipt_checks(
        dirty, inputs, command, readme)['cleanup exact']

    missing_sources = copy.deepcopy(inputs)
    missing_sources.pop('repository_inputs')
    tests['reject missing source pin manifest'] = not source_checks(
        missing_sources)['source pin manifest exact']

    substituted_archive = copy.deepcopy(inputs)
    substituted_archive['archives']['fixed']['sha256'] = '0' * 64
    tests['reject substituted archive pin'] = not receipt_checks(
        result, substituted_archive, command, readme)['archives not retrieved']

    unguarded_command = command.replace('  exit 1\n', '  :\n', 1)
    tests['reject missing command exit gate'] = not receipt_checks(
        result, inputs, unguarded_command, readme)['command marks blocked boundary']
    return tests


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--json-output', type=Path)
    args = parser.parse_args()

    result = json.loads((HERE / 'result.json').read_text())
    inputs = json.loads((HERE / 'inputs.json').read_text())
    command = (HERE / 'run-command.txt').read_text()
    readme = (HERE / 'README.md').read_text()
    checks = verify(result, inputs, command, readme)
    if args.self_test:
        checks |= {f'self-test {name}': passed for name, passed in self_test(
            result, inputs, command, readme).items()}

    receipt = {
        'schema_version': 1,
        'kind': 't02-cloud-amd64-kanboard-parity-public-verification',
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
