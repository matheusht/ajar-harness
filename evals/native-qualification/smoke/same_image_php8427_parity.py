#!/usr/bin/env python3
"""Qualify one already-admitted PHP 8.4.27 image with the preserved T01 observer."""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import types
from urllib.request import urlopen


ADAPTER_RELATIVE = Path('smoke/check_v2_php_parity_amd64_php8427.py')
ADAPTER_SHA256 = '100cebaaf715e42fa9c10e4c396a5075c931f6f780baac64f590844308d0973d'
RUNNER_SHA256 = 'bf983ccc93fac42033c7785fab35aa10e263c9035ee8680a3896c183df281927'
PLATFORM = 'linux/amd64'
ARCHIVE_BYTE_LIMIT = 128 * 1024 * 1024
EXPECTED_PINS = {
    'vulnerable': (
        'f0f7d27007f5a788f14416c548421efd740b7bce',
        '3f24269475bf00137d4b0d957d97a2567a5249101dad89067a49d609f4df2edf'),
    'fixed': (
        'a98bc5f855d4e7e47eb3425a6c7da6c6cc6748a3',
        '44db3df81a25bbd56c768c8b3180a1f05879e2c7fbaa6ac73707e7f3e9098f56'),
}
EXPECTED_CHECKS = frozenset({
    'pinned repository inputs unchanged',
    'published amd64 build receipt matches current pins',
    'pinned local image is available without pull',
    'exact image id',
    'expected tag',
    'linux amd64',
    'dockerfile pin',
    'php 8 4 27',
    'required php modules',
    'required php packages',
    'all php84 packages 8 4 27 r0',
    'pinned T01 comparator copies are exact',
    'two release arms',
    'ordinary controls both arms',
    'vulnerable exact metadata',
    'fixed cross role denial',
    'semantic match t01',
    'cleanup complete',
    'current runtime both arms',
    'source pins both arms',
    'expected traces present',
    'expected create user entries',
    'create user passwords redacted',
    'authorization cookie token values absent',
    'private paths absent',
    'observer material was not mounted into a researcher',
    'archives and extracted sources remain pinned after run',
    'repository inputs remain unchanged after run',
    'containers restored',
    'images restored',
    'volumes restored',
    'networks restored',
})


class SameImageParityError(RuntimeError):
    """A stable fail-closed error from the same-image parity gate."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_regular(path: Path, code: str, *, byte_limit: int = 4 * 1024 * 1024) -> bytes:
    try:
        before = os.lstat(path)
    except OSError as error:
        raise SameImageParityError(code) from error
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise SameImageParityError(code)
    flags = os.O_RDONLY | getattr(os, 'O_CLOEXEC', 0) | getattr(os, 'O_NOFOLLOW', 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise SameImageParityError(code) from error
    try:
        opened = os.fstat(descriptor)
        if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)):
            raise SameImageParityError(code)
        chunks = []
        size = 0
        while chunk := os.read(descriptor, 65536):
            size += len(chunk)
            if size > byte_limit:
                raise SameImageParityError(code)
            chunks.append(chunk)
        data = b''.join(chunks)
        after = os.fstat(descriptor)
        if ((opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
            raise SameImageParityError(code + '_changed')
        return data
    finally:
        os.close(descriptor)


def _strict_json(raw: bytes, code: str) -> dict:
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise SameImageParityError(code)
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SameImageParityError(code) from error
    if not isinstance(value, dict):
        raise SameImageParityError(code)
    return value


def _write_exclusive(path: Path, raw: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                         | getattr(os, 'O_CLOEXEC', 0), 0o600)
    try:
        view = memoryview(raw)
        while view:
            count = os.write(descriptor, view)
            if count <= 0:
                raise OSError('short write')
            view = view[count:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


def _within(path: Path, root: Path, code: str) -> Path:
    resolved_root = root.resolve(strict=True)
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(resolved_root)
    except ValueError as error:
        raise SameImageParityError(code) from error
    if path.is_symlink() or not resolved.is_file():
        raise SameImageParityError(code)
    return resolved


def load_pinned_adapter(source_root: Path):
    adapter_path = _within(source_root / ADAPTER_RELATIVE, source_root,
                           'adapter_path_invalid')
    adapter_raw = _read_regular(adapter_path, 'adapter_source_unreadable')
    if _sha256(adapter_raw) != ADAPTER_SHA256:
        raise SameImageParityError('adapter_source_pin_mismatch')
    name = '_t02_same_image_php8427_adapter'
    if name in sys.modules:
        raise SameImageParityError('adapter_already_loaded')
    adapter = types.ModuleType(name)
    adapter.__file__ = str(adapter_path)
    adapter.__package__ = ''
    sys.modules[name] = adapter
    try:
        code = compile(adapter_raw, str(adapter_path), 'exec', dont_inherit=True)
        exec(code, adapter.__dict__)
    except Exception as error:
        sys.modules.pop(name, None)
        raise SameImageParityError('adapter_import_failed') from error
    if (getattr(adapter, 'RUNNER_SHA256', None) != RUNNER_SHA256
            or getattr(adapter, 'EXPECTED_PINS', None) != EXPECTED_PINS):
        sys.modules.pop(name, None)
        raise SameImageParityError('adapter_policy_mismatch')
    return adapter


def _outer_candidate(path: Path, image_tag: str, image_id: str,
                     dockerfile_sha256: str) -> tuple[dict, str]:
    raw = _read_regular(path, 'outer_candidate_receipt_unreadable')
    value = _strict_json(raw, 'outer_candidate_receipt_invalid')
    if (value.get('schema_version') != 1
            or value.get('kind') != 't02-managed-owned-amd64-php8427-candidate'
            or value.get('status') != 'registered_before_execution'
            or value.get('platform') != PLATFORM
            or value.get('tag') != image_tag
            or value.get('image_id') != image_id
            or value.get('dockerfile_sha256') != dockerfile_sha256
            or value.get('image_execution_attempted') is not False):
        raise SameImageParityError('outer_candidate_receipt_mismatch')
    return value, _sha256(raw)


@contextmanager
def installed_same_image_adapter(adapter, runner, candidate, archives,
                                 *, qualification_base: str,
                                 dockerfile: Path, checks: Path,
                                 receipt: Path, receipt_sha256: str):
    """Install explicit fresh-candidate bindings on the preserved runner only."""
    if runner.observer_case.PINS != EXPECTED_PINS:
        raise SameImageParityError('preserved_observer_pins_changed')
    bindings = {
        'QUALIFICATION_BASE': qualification_base,
        'IMAGE': candidate.tag,
        'IMAGE_ID': candidate.image_id,
        'IMAGE_RUNTIME_LABEL': candidate.image_id,
        'DOCKERFILE': dockerfile,
        'DOCKERFILE_SHA256': candidate.dockerfile_sha256,
        'CHECKS': checks,
        'RUNTIME_BUILD': receipt,
        'RUNTIME_BUILD_SHA256': receipt_sha256,
    }
    old_bindings = {name: getattr(runner, name) for name in bindings}
    function_names = ('admit_and_probe_image', 'observer_check_results',
                      'artifact_check_results', 'public_observer_result')
    old_functions = {name: getattr(runner, name) for name in function_names}
    observer = runner.observer_case
    old_observer = {
        name: getattr(observer, name)
        for name in ('urlopen', 'subprocess', 'PHP_IMAGE', 'PHP_IMAGE_DIGEST')
    }
    try:
        for name, value in bindings.items():
            setattr(runner, name, value)
        runner.admit_and_probe_image = lambda info, digest, check: (
            adapter.admit_and_probe_image(
                info, digest, check, candidate, runner.subprocess))
        runner.observer_check_results = lambda current, original: (
            adapter.php8427_observer_check_results(
                current, original, old_functions['observer_check_results'],
                candidate.image_id))
        runner.artifact_check_results = adapter._strict_artifact_checker(
            old_functions['artifact_check_results'])
        runner.public_observer_result = adapter._public_result_sanitizer(
            old_functions['public_observer_result'])
        observer.urlopen = adapter.GuardedUrlopen(
            archives, old_observer['urlopen'])
        observer.subprocess = adapter.ObserverSubprocess(
            old_observer['subprocess'], candidate.image_id)
        yield runner
    finally:
        for name, value in old_bindings.items():
            setattr(runner, name, value)
        for name, value in old_functions.items():
            setattr(runner, name, value)
        for name, value in old_observer.items():
            setattr(observer, name, value)


def _validate_result(output: Path, image_tag: str, image_id: str,
                     qualification_base: str,
                     compatibility_sha256: str) -> tuple[dict, bytes, bytes]:
    result_raw = _read_regular(output / 'parity-result.json',
                               'parity_result_unreadable', byte_limit=2 * 1024 * 1024)
    result = _strict_json(result_raw, 'parity_result_invalid')
    checks = result.get('checks')
    names = []
    if isinstance(checks, list):
        for item in checks:
            if (not isinstance(item, dict) or set(item) != {'name', 'pass'}
                    or not isinstance(item.get('name'), str)
                    or item.get('pass') is not True):
                raise SameImageParityError('parity_checks_failed')
            names.append(item['name'])
    if (result.get('status') != 'pass'
            or result.get('classification') !=
            'owned offline observer parity; zero provider/model calls'
            or result.get('qualification_base') != qualification_base
            or Counter(names) != Counter({name: 1 for name in EXPECTED_CHECKS})
            or result.get('provider_calls') != 0
            or result.get('model_calls') != 0
            or result.get('researcher_bundle_created') is not False
            or 'error' in result or 'cleanup_error' in result
            or result.get('docker_before') != result.get('docker_after')):
        raise SameImageParityError('parity_result_failed')
    source_sha256 = result.get('source_sha256')
    if (not isinstance(source_sha256, dict)
            or source_sha256.get('smoke/check_v2_php_parity_amd64.py')
            != RUNNER_SHA256
            or source_sha256.get(
                '.same-image-parity-private/registration.json')
            != compatibility_sha256):
        raise SameImageParityError('parity_source_binding_mismatch')
    image = result.get('image')
    if (not isinstance(image, dict)
            or image.get('tag') != image_tag
            or image.get('expected_id') != image_id
            or image.get('actual_id') != image_id
            or image.get('expected_platform') != PLATFORM
            or image.get('actual_platform') != PLATFORM
            or not str(image.get('php_version', '')).startswith('PHP 8.4.27 ')):
        raise SameImageParityError('parity_image_mismatch')
    expected_archives = {
        label: {
            'url': f'https://codeload.github.com/kanboard/kanboard/tar.gz/{commit}',
            'commit': commit,
            'sha256': digest,
        }
        for label, (commit, digest) in EXPECTED_PINS.items()
    }
    if result.get('archive_inputs') != expected_archives:
        raise SameImageParityError('parity_archive_pins_mismatch')
    public_raw = _read_regular(
        output / 'evidence/observer-results.public.json',
        'public_observer_result_unreadable', byte_limit=2 * 1024 * 1024)
    public = _strict_json(public_raw, 'public_observer_result_invalid')
    arms = public.get('arms')
    if not isinstance(arms, list) or len(arms) != 2:
        raise SameImageParityError('public_observer_arms_mismatch')
    by_release = {
        arm.get('release'): arm for arm in arms if isinstance(arm, dict)
    }
    if set(by_release) != set(EXPECTED_PINS):
        raise SameImageParityError('public_observer_arms_mismatch')
    for label, (commit, digest) in EXPECTED_PINS.items():
        arm = by_release[label]
        if (arm.get('runtime') != image_id
                or not str(arm.get('php', '')).startswith('PHP 8.4.27 ')
                or (arm.get('commit'), arm.get('archive_sha256')) != (commit, digest)):
            raise SameImageParityError('public_observer_runtime_mismatch')
    return result, result_raw, public_raw


def run_same_image_parity(source_root: Path, output: Path, image_tag: str,
                          image_id: str, dockerfile: Path, checks: Path,
                          qualification_base: str, outer_candidate_receipt: Path,
                          *, opener=urlopen, adapter_loader=load_pinned_adapter) -> dict:
    """Run the two arms on the same immutable image, or raise before returning."""
    source_root = source_root.resolve(strict=True)
    output = output.resolve()
    if (output.exists() or not re.fullmatch(r'sha256:[0-9a-f]{64}', image_id)
            or not image_tag or re.search(r'\s', image_tag)
            or not re.fullmatch(r'[0-9a-f]{40}', qualification_base)):
        raise SameImageParityError('same_image_input_invalid')
    dockerfile = _within(dockerfile, source_root, 'dockerfile_path_invalid')
    checks = _within(checks, source_root, 'checks_path_invalid')
    dockerfile_sha256 = _sha256(_read_regular(dockerfile, 'dockerfile_unreadable'))
    _candidate_value, outer_candidate_sha256 = _outer_candidate(
        outer_candidate_receipt, image_tag, image_id, dockerfile_sha256)
    adapter = adapter_loader(source_root)
    if getattr(adapter, 'EXPECTED_PINS', None) != EXPECTED_PINS:
        raise SameImageParityError('adapter_archive_policy_mismatch')
    candidate = adapter.Candidate(image_tag, image_id, dockerfile_sha256)

    compatibility = {
        'schema_version': 1,
        'kind': 't02-same-image-parity-registration-compatibility',
        'status': 'pass',
        'scope': 'immutable-image registration gate only',
        'qualification_base': qualification_base,
        'platform': PLATFORM,
        'tag': image_tag,
        'image_id': image_id,
        'outer_candidate_receipt_sha256': outer_candidate_sha256,
        'build_inputs': {'dockerfile_sha256': dockerfile_sha256},
        'claim_limits': {
            'runtime_admitted_by_this_receipt': False,
            'application_semantics_qualified_by_this_receipt': False,
            'provider_or_model_route_qualified': False,
            'default_adoption': False,
        },
    }
    compatibility_raw = _json_bytes(compatibility)
    compatibility_sha256 = _sha256(compatibility_raw)
    private_dir = source_root / '.same-image-parity-private'
    receipt = private_dir / 'registration.json'
    archive_receipt = private_dir / 'archives.json'
    archive_receipt_raw = None
    archive_receipt_sha256 = None
    private_created = False
    try:
        private_dir.mkdir(mode=0o700)
        private_created = True
        _write_exclusive(receipt, compatibility_raw)
        runner = adapter.load_preserved_runner()
        if (getattr(adapter, 'RUNNER_SHA256', None) != RUNNER_SHA256
                or runner.observer_case.PINS != EXPECTED_PINS):
            raise SameImageParityError('preserved_runner_pin_mismatch')
        archives = adapter.fetch_verified_archives(
            EXPECTED_PINS, opener, ARCHIVE_BYTE_LIMIT)
        if (not isinstance(archives, dict) or set(archives) != set(EXPECTED_PINS)
                or any(not isinstance(archives[label], bytes)
                       or _sha256(archives[label]) != EXPECTED_PINS[label][1]
                       for label in EXPECTED_PINS)):
            raise SameImageParityError('prefetched_archive_mismatch')
        archive_admission = {
            'schema_version': 1,
            'kind': 't02-same-image-kanboard-archive-admission',
            'status': 'pass',
            'scope': 'both public source archives verified before either arm',
            'image_id': image_id,
            'registration_compatibility_sha256': compatibility_sha256,
            'byte_limit_each': ARCHIVE_BYTE_LIMIT,
            'archives': {
                label: {
                    'commit': commit,
                    'sha256': digest,
                    'size_bytes': len(archives[label]),
                    'verified_before_first_arm': True,
                }
                for label, (commit, digest) in EXPECTED_PINS.items()
            },
            'provider_calls': 0,
            'model_calls': 0,
            'live_targets_contacted': 0,
        }
        archive_receipt_raw = _json_bytes(archive_admission)
        archive_receipt_sha256 = _sha256(archive_receipt_raw)
        _write_exclusive(archive_receipt, archive_receipt_raw)
        with installed_same_image_adapter(
                adapter, runner, candidate, archives,
                qualification_base=qualification_base,
                dockerfile=dockerfile, checks=checks,
                receipt=receipt, receipt_sha256=compatibility_sha256):
            prior_argv = sys.argv
            try:
                sys.argv = [str(adapter.RUNNER), '--output', str(output)]
                exit_code = runner.main()
            finally:
                sys.argv = prior_argv
        if output.is_dir():
            _write_exclusive(output / 'registration-compatibility.json',
                             compatibility_raw)
            _write_exclusive(output / 'archive-admission.json',
                             archive_receipt_raw)
        if exit_code != 0:
            raise SameImageParityError('preserved_runner_failed')
        result, result_raw, public_raw = _validate_result(
            output, image_tag, image_id, qualification_base,
            compatibility_sha256)
        summary = {
            'schema_version': 1,
            'kind': 't02-same-image-php8427-application-parity',
            'status': 'pass',
            'platform': PLATFORM,
            'image_tag': image_tag,
            'image_id': image_id,
            'checks_passed': len(EXPECTED_CHECKS),
            'both_arms_same_image': True,
            'docker_baseline_restored': True,
            'archive_inputs': {
                label: {'commit': commit, 'sha256': digest}
                for label, (commit, digest) in EXPECTED_PINS.items()
            },
            'source_pins': {
                'adapter_sha256': ADAPTER_SHA256,
                'runner_sha256': RUNNER_SHA256,
                'dockerfile_sha256': dockerfile_sha256,
            },
            'receipt_sha256': {
                'outer_candidate': outer_candidate_sha256,
                'registration_compatibility': compatibility_sha256,
                'archive_admission': archive_receipt_sha256,
                'parity_result': _sha256(result_raw),
                'public_observer_result': _sha256(public_raw),
            },
            'external_activity': {
                'public_source_archives_retrieved': 2,
                'provider_calls': 0,
                'model_calls': 0,
                'live_targets_contacted': 0,
                'researcher_bundle_created': False,
            },
            'claim_limits': {
                'owned_offline_application_semantics_only': True,
                'provider_or_model_route_qualified': False,
                'default_adoption': False,
            },
        }
        _write_exclusive(output / 'same-image-summary.json', _json_bytes(summary))
        return summary
    except SameImageParityError:
        raise
    except OSError as error:
        raise SameImageParityError('same_image_filesystem_failure') from error
    except (RuntimeError, ValueError) as error:
        raise SameImageParityError('same_image_dependency_failure') from error
    finally:
        if private_created:
            try:
                archive_receipt.unlink(missing_ok=True)
                receipt.unlink(missing_ok=True)
                private_dir.rmdir()
            except OSError as error:
                if sys.exc_info()[0] is None:
                    raise SameImageParityError(
                        'compatibility_receipt_cleanup_failed') from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--image-tag', required=True)
    parser.add_argument('--image-id', required=True)
    parser.add_argument('--dockerfile', required=True, type=Path)
    parser.add_argument('--checks', required=True, type=Path)
    parser.add_argument('--qualification-base', required=True)
    parser.add_argument('--outer-candidate-receipt', required=True, type=Path)
    args = parser.parse_args()
    try:
        summary = run_same_image_parity(
            args.source_root, args.output, args.image_tag, args.image_id,
            args.dockerfile, args.checks, args.qualification_base,
            args.outer_candidate_receipt)
    except SameImageParityError as error:
        print(json.dumps({'status': 'fail', 'error': str(error)}, sort_keys=True))
        return 1
    print(json.dumps({
        'status': summary['status'],
        'checks': summary['checks_passed'],
        'image_id': summary['image_id'],
        'output': str(args.output.resolve()),
    }, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
