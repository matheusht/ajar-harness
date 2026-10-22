#!/usr/bin/env python3
"""Run the frozen same-image controller against the current integrated T02 source."""

import hashlib
from pathlib import Path
import sys
from types import ModuleType


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ENTRY = HERE / 'check_v2_managed_owned_integrated.py'
FROZEN = HERE / 'check_v2_managed_owned_amd64_php8427.py'
FROZEN_SHA256 = '3c91fca0a6fe7af4570248de5d6f18ebe6b4f709118fc3c75a31b6b68d726164'
INTEGRATION_HEAD = 'c74d6086e262206a28aa97a8bb94d351a8c98619'
MANAGED_RUNNER_SHA256 = '524abbd26c2bede524b463d0e902fe4f8dd986f8f678f2732ccbc9b842d0ae24'
IMAGE_TAG = 't02-managed-runtime:amd64-php8427-integrated-20261022a'
TEST = HERE / 'check_v2_managed_owned_integrated_test.py'


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
            or controller.IMAGE_TAG != 't02-managed-runtime:amd64-php8427-20261021d'):
        raise RuntimeError('historical_controller_contract_mismatch')
    controller.INTEGRATION_HEAD = INTEGRATION_HEAD
    controller.MANAGED_RUNNER_SHA256 = MANAGED_RUNNER_SHA256
    controller.IMAGE_TAG = IMAGE_TAG
    return controller


def admit_sources(controller):
    source = controller.validate_sources()
    entries = source.get('private', {}).get('manifest_entries') if isinstance(source, dict) else None
    if not isinstance(entries, list):
        raise RuntimeError('integrated_source_manifest_mismatch')
    declared = {item.get('path'): item.get('sha256') for item in entries if isinstance(item, dict)}
    for path in (ENTRY, TEST):
        if declared.get(str(path.relative_to(ROOT))) != hashlib.sha256(path.read_bytes()).hexdigest():
            raise RuntimeError('integrated_source_manifest_mismatch')
    return source


def main():
    controller = load_controller()
    if any(arg in ('-h', '--help') for arg in sys.argv[1:]):
        return controller.main()
    admit_sources(controller)
    print('Integrated same-image task tag: ' + IMAGE_TAG, flush=True)
    return controller.main()


if __name__ == '__main__':
    raise SystemExit(main())
