#!/usr/bin/env python3
"""Run the frozen same-image controller against the current integrated T02 source."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import ModuleType


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ENTRY = HERE / 'check_v2_managed_owned_integrated.py'
FROZEN = HERE / 'check_v2_managed_owned_amd64_php8427.py'
FROZEN_SHA256 = '3c91fca0a6fe7af4570248de5d6f18ebe6b4f709118fc3c75a31b6b68d726164'
INTEGRATION_HEAD = 'c74d6086e262206a28aa97a8bb94d351a8c98619'
MANAGED_RUNNER_SHA256 = 'bced7e13c11af9649fc9646f3a5994ded5c03367d47f6d02d1ff1af49e7836f2'
IMAGE_TAG = 't02-managed-runtime:amd64-php8427-integrated-20261022a'
TEST = HERE / 'check_v2_managed_owned_integrated_test.py'
CHECKS = ROOT / 'evals/native-qualification/T02-INTEGRATED-SOURCE-ADMISSION-CHECKS-20261022.md'
CHECKS_SHA256 = '9d242acfc191b2834b03ac10fa3f6e52838f22ea0d8f11bd4be70e77abd0cd0a'


def load_controller():
    data = FROZEN.read_bytes()
    if hashlib.sha256(data).hexdigest() != FROZEN_SHA256:
        raise RuntimeError('historical_controller_pin_mismatch')
    controller = ModuleType('frozen_t02_same_image_controller')
    controller.__file__ = str(FROZEN)
    exec(compile(data, str(FROZEN), 'exec'), controller.__dict__)
    if (controller.INTEGRATION_HEAD != 'b8f0453575740cb1482dc716fa1807c195459f58'
            or controller.MANAGED_RUNNER_SHA256 !=
                'e5f442ddcda8515cb0fb29b9a601cdea068e6c66da795c4b8c8da0e351569475'
            or controller.IMAGE_TAG != 't02-managed-runtime:amd64-php8427-20261021d'
            or controller.CHECKS.name != 'T02-AMD64-MANAGED-OWNED-PHP8427-CHECKS-20261021.md'
            or controller.CHECKS_SHA256 !=
                '9eca021870ac7b52b974c58f65de511e950481c246ecf3d34552ed6bad71290d'):
        raise RuntimeError('historical_controller_contract_mismatch')
    controller.INTEGRATION_HEAD = INTEGRATION_HEAD
    controller.MANAGED_RUNNER_SHA256 = MANAGED_RUNNER_SHA256
    controller.IMAGE_TAG = IMAGE_TAG
    controller.CHECKS = CHECKS
    controller.CHECKS_SHA256 = CHECKS_SHA256
    return controller


def admit_sources(controller):
    source = controller.validate_sources()
    entries = source.get('private', {}).get('manifest_entries') if isinstance(source, dict) else None
    if not isinstance(entries, list):
        raise RuntimeError('integrated_source_manifest_mismatch')
    declared = {item.get('path'): item.get('sha256') for item in entries if isinstance(item, dict)}
    for path in (ENTRY, TEST, CHECKS):
        if declared.get(str(path.relative_to(ROOT))) != hashlib.sha256(path.read_bytes()).hexdigest():
            raise RuntimeError('integrated_source_manifest_mismatch')
    return source


def preflight():
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    for script, args in (('check_v2_cloud_manifest_layout.py', []),
                         ('check_v2_cloud_owned_source.py', ['--current-manifest'])):
        try:
            result = subprocess.run([sys.executable, str(HERE / script), *args],
                                    cwd=ROOT, env=env, capture_output=True,
                                    text=True, timeout=120)
        except (OSError, subprocess.SubprocessError) as error:
            raise RuntimeError('offline_preflight_failed') from error
        if result.returncode:
            raise RuntimeError('offline_preflight_failed')


def blocked(output, failure):
    if output is None:
        print('blocked: ' + failure, file=sys.stderr)
        return 1
    receipt = {'schema_version': 1, 'kind': 't02-managed-owned-integrated-admission',
               'status': 'blocked', 'failure': failure,
               'controller_started': False, 'docker_build_attempted': False}
    try:
        output = output.expanduser().resolve()
        output.mkdir(parents=True, mode=0o700, exist_ok=False)
        descriptor = os.open(output / 'result.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w') as stream:
            json.dump(receipt, stream, indent=2, sort_keys=True)
            stream.write('\n')
    except OSError:
        print('blocked: admission_receipt_unavailable', file=sys.stderr)
        return 1
    print('blocked: ' + failure, file=sys.stderr)
    return 1


def main():
    if any(arg in ('-h', '--help') for arg in sys.argv[1:]):
        return load_controller().main()
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--output', type=Path)
    output = parser.parse_known_args()[0].output
    try:
        controller = load_controller()
        admit_sources(controller)
        preflight()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        failure = str(error)
        if failure not in ('historical_controller_pin_mismatch',
                           'historical_controller_contract_mismatch',
                           'integrated_source_manifest_mismatch',
                           'offline_preflight_failed'):
            failure = 'integrated_admission_failed'
        return blocked(output, failure)
    print('Integrated same-image task tag: ' + IMAGE_TAG, flush=True)
    return controller.main()


if __name__ == '__main__':
    raise SystemExit(main())
