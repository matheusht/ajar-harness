#!/usr/bin/env python3
"""Repeat the T01 Kanboard observer on the pinned cloud amd64 PHP image."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import observer_case  # noqa: E402


QUALIFICATION_BASE = '513b662eda0345d943eb0582f7bc39a8a6512617'
IMAGE = 't02-kanboard-runtime:amd64-live-prep'
IMAGE_ID = 'sha256:9ef722322521322a1288a18427ba5bf6ce1479085c97e0ac821982eec4f01769'
IMAGE_RUNTIME_LABEL = IMAGE_ID
DOCKERFILE_SHA256 = '7a1ab9b257fb36a216fc1baafabc757436d0a15ffcb9498b6fbe697da3a9bf4b'
OBSERVER_SHA256 = '72273bfd4e1c1aa9f7f53279e525ec1c74c2669324fa62f1b6b22abf65d596bf'
T01_RESULT_SHA256 = '9db3bc220484a7a786729847f3c8fa8cc1d364a74b1e4a81d2bb78f80dc924fa'
BRIEF_SHA256 = '8f2b5604870cf86719ae94ac180cb6cbe0c5c12cdd2356bc90f4104bb7179a5a'
RUNTIME_BUILD_SHA256 = 'e21c872cbefc53022d6dd6f23b88795e873de93c1a183d7adcdb3883fbfc2c8c'
EXPECTED_PINS = {
    'vulnerable': (
        'f0f7d27007f5a788f14416c548421efd740b7bce',
        '3f24269475bf00137d4b0d957d97a2567a5249101dad89067a49d609f4df2edf'),
    'fixed': (
        'a98bc5f855d4e7e47eb3425a6c7da6c6cc6748a3',
        '44db3df81a25bbd56c768c8b3180a1f05879e2c7fbaa6ac73707e7f3e9098f56'),
}

T01_RESULT = HERE / 'observer-evidence-final/observer-results.json'
BRIEF = HERE / 'RESEARCHER-BRIEF.md'
DOCKERFILE = HERE / 'Dockerfile.opencode-kanboard-runtime'
CHECKS = HERE / 'T02-AMD64-PHP-PARITY-CHECKS-20261021.md'
OBSERVER = HERE / 'observer_case.py'
RUNTIME_BUILD = HERE / 't02-evidence/live-preparation-owned-20261021a/runtime-build.json'


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def image_check_results(image_info: dict, php_version: str, php_modules: list[str],
                        dockerfile_sha256: str) -> dict[str, bool]:
    modules = {value.lower() for value in php_modules}
    return {
        'exact_image_id': image_info.get('Id') == IMAGE_ID,
        'expected_tag': IMAGE in image_info.get('RepoTags', []),
        'linux_amd64': (
            image_info.get('Os') == 'linux'
            and image_info.get('Architecture') == 'amd64'),
        'dockerfile_pin': dockerfile_sha256 == DOCKERFILE_SHA256,
        'php_8_4_26': php_version.startswith('PHP 8.4.26 '),
        'required_php_modules': {'gd', 'pdo_sqlite'} <= modules,
    }


def admit_and_probe_image(image_info: dict, dockerfile_sha256: str, check) -> tuple[str, list[str]]:
    """Reject an unqualified image before executing even an offline probe."""
    identity = image_check_results(image_info, '', [], dockerfile_sha256)
    for name in ('exact_image_id', 'expected_tag', 'linux_amd64', 'dockerfile_pin'):
        check(name.replace('_', ' '), identity[name])

    version = subprocess.run([
        'docker', 'run', '--rm', '--pull=never', '--network', 'none',
        '--entrypoint', 'php', IMAGE_ID, '-v'], capture_output=True, text=True)
    modules = subprocess.run([
        'docker', 'run', '--rm', '--pull=never', '--network', 'none',
        '--entrypoint', 'php', IMAGE_ID, '-m'], capture_output=True, text=True)
    php_version = version.stdout.splitlines()[0] if version.returncode == 0 else ''
    php_modules = sorted(set(modules.stdout.splitlines())) if modules.returncode == 0 else []
    runtime = image_check_results(image_info, php_version, php_modules, dockerfile_sha256)
    for name in ('php_8_4_26', 'required_php_modules'):
        check(name.replace('_', ' '), runtime[name])
    return php_version, php_modules


def _arms_by_release(result: dict) -> dict[str, dict]:
    arms = result.get('arms')
    if not isinstance(arms, list) or len(arms) != 2:
        return {}
    if not all(isinstance(arm, dict) for arm in arms):
        return {}
    by_release = {arm.get('release'): arm for arm in arms}
    return by_release if len(by_release) == len(arms) else {}


def _denied(value: object) -> bool:
    return (isinstance(value, dict) and value.get('code') == 403
            and 'forbid' in str(value.get('message', '')).lower())


def observer_check_results(current: dict, original: dict) -> dict[str, bool]:
    current_arms = _arms_by_release(current)
    original_arms = _arms_by_release(original)
    two_arms = set(current_arms) == set(original_arms) == {'vulnerable', 'fixed'}

    ordinary = two_arms and all(
        arm.get('loopback') is True
        and arm.get('authorized_project') == arm.get('project_id')
        and arm.get('authorized_swimlane') == arm.get('swimlane_id')
        and _denied(arm.get('private_project_control'))
        for arm in current_arms.values())

    vulnerable = current_arms.get('vulnerable', {})
    vulnerable_result = vulnerable.get('cross_role_read', {}).get('result', {})
    vulnerable_exact = (
        vulnerable_result.get('id') == vulnerable.get('swimlane_id')
        and vulnerable_result.get('project_id') == vulnerable.get('project_id')
        and vulnerable_result.get('name') == 'Observer Swimlane')

    fixed = current_arms.get('fixed', {})
    fixed_denied = _denied(fixed.get('cross_role_read', {}).get('denial'))

    comparable = (
        'release', 'loopback', 'project_id', 'swimlane_id', 'authorized_project',
        'authorized_swimlane', 'private_project_control', 'cross_role_read',
        'commit', 'archive_sha256')
    semantic_match = two_arms and all(
        {key: current_arms[label].get(key) for key in comparable}
        == {key: original_arms[label].get(key) for key in comparable}
        for label in ('vulnerable', 'fixed'))

    cleanup = two_arms and all(
        arm.get('cleanup', {}).get('container_absent') is True
        and arm.get('cleanup', {}).get('port_closed') is True
        and arm.get('cleanup', {}).get('run_dir_absent') is True
        and arm.get('cleanup', {}).get('db_absent') is True
        for arm in current_arms.values())

    runtime = two_arms and all(
        arm.get('runtime') == IMAGE_RUNTIME_LABEL
        and str(arm.get('php', '')).startswith('PHP 8.4.26 ')
        for arm in current_arms.values())

    pins = two_arms and all(
        (current_arms[label].get('commit'), current_arms[label].get('archive_sha256'))
        == EXPECTED_PINS[label]
        for label in ('vulnerable', 'fixed'))

    return {
        'two_release_arms': two_arms,
        'ordinary_controls_both_arms': ordinary,
        'vulnerable_exact_metadata': vulnerable_exact,
        'fixed_cross_role_denial': fixed_denied,
        'semantic_match_t01': semantic_match,
        'cleanup_complete': cleanup,
        'current_runtime_both_arms': runtime,
        'source_pins_both_arms': pins,
    }


def artifact_check_results(traces: dict[str, list], texts: dict[str, str],
                           forbidden_roots: list[str]) -> dict[str, bool]:
    expected_labels = set(EXPECTED_PINS)
    expected_traces = (
        set(traces) == expected_labels
        and all(isinstance(traces[label], list) and traces[label]
                for label in expected_labels))
    entries = [entry for trace in traces.values() for entry in trace]
    create_users = {
        label: [entry for entry in traces.get(label, [])
                if isinstance(entry, dict) and entry.get('method') == 'createUser']
        for label in expected_labels}
    expected_creates = expected_traces and all(
        len(create_users[label]) == 2
        and {entry.get('actor') for entry in create_users[label]} == {'admin'}
        and {tuple(entry.get('params', [])) for entry in create_users[label]}
        == {('alice', '[REDACTED]'), ('bob', '[REDACTED]')}
        for label in expected_labels)
    create_user_redacted = all(
        len(entry.get('params', [])) > 1 and entry['params'][1] == '[REDACTED]'
        for entry in entries if entry.get('method') == 'createUser')
    serialized = json.dumps(traces, sort_keys=True) + '\n' + '\n'.join(texts.values())
    sensitive_value = re.compile(
        r'(?i)(authorization\s*[:=]|basic\s+[a-z0-9+/=]{8,}|'
        r'"(?:cookie|token|access_token|password)"\s*:\s*"(?!\[REDACTED\])[^\"]+")')
    return {
        'expected_traces_present': expected_traces,
        'expected_create_user_entries': expected_creates,
        'create_user_passwords_redacted': expected_creates and create_user_redacted,
        'authorization_cookie_token_values_absent': sensitive_value.search(serialized) is None,
        'private_paths_absent': all(root not in serialized for root in forbidden_roots),
    }


def docker_state() -> dict[str, list[str]]:
    commands = {
        'containers': ['docker', 'container', 'ls', '-aq', '--no-trunc'],
        'images': ['docker', 'image', 'ls', '-q', '--no-trunc'],
        'volumes': ['docker', 'volume', 'ls', '-q'],
        'networks': ['docker', 'network', 'ls', '-q', '--no-trunc'],
    }
    state = {}
    for name, command in commands.items():
        output = subprocess.run(command, check=True, capture_output=True, text=True).stdout
        state[name] = sorted(set(output.splitlines()))
    return state


def docker_baseline_check_results(before: dict[str, list[str]],
                                  after: dict[str, list[str]]) -> dict[str, bool]:
    return {
        'containers_restored': before.get('containers') == after.get('containers'),
        'images_restored': before.get('images') == after.get('images'),
        'volumes_restored': before.get('volumes') == after.get('volumes'),
        'networks_restored': before.get('networks') == after.get('networks'),
    }


def public_observer_result(result: dict) -> dict:
    public = copy.deepcopy(result)
    for arm in public.get('arms', []):
        release = arm['release']
        arm['cleanup']['run_dir'] = f'<private-output>/{release}-run'
        arm['cleanup']['db_path'] = f'<private-output>/{release}-run/app/data/db.sqlite'
    return public


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.chmod(output, 0o700)

    report = {
        'schema_version': 1,
        'kind': 't02-cloud-amd64-kanboard-parity',
        'classification': 'owned offline observer parity; zero provider/model calls',
        'qualification_base': QUALIFICATION_BASE,
        'image': {'tag': IMAGE, 'expected_id': IMAGE_ID, 'expected_platform': 'linux/amd64'},
        'archive_inputs': {
            label: {
                'url': f'https://codeload.github.com/kanboard/kanboard/tar.gz/{commit}',
                'commit': commit,
                'sha256': digest,
            }
            for label, (commit, digest) in EXPECTED_PINS.items()
        },
        'checks': [],
        'provider_calls': 0,
        'model_calls': 0,
        'researcher_bundle_created': False,
    }

    def save() -> None:
        (output / 'parity-result.json').write_text(json.dumps(report, indent=2) + '\n')

    def record(name: str, condition: bool) -> None:
        report['checks'].append({'name': name, 'pass': bool(condition)})
        save()

    def check(name: str, condition: bool) -> None:
        record(name, condition)
        if not condition:
            raise AssertionError(name)

    before = None
    try:
        before = docker_state()
        report['docker_before'] = before
        source_paths = (Path(__file__), OBSERVER, T01_RESULT, BRIEF, DOCKERFILE, CHECKS,
                        RUNTIME_BUILD)
        report['source_sha256'] = {
            str(path.relative_to(HERE)): sha256(path) for path in source_paths}
        check('pinned repository inputs unchanged',
              sha256(OBSERVER) == OBSERVER_SHA256
              and sha256(T01_RESULT) == T01_RESULT_SHA256
              and sha256(BRIEF) == BRIEF_SHA256
              and sha256(DOCKERFILE) == DOCKERFILE_SHA256
              and sha256(RUNTIME_BUILD) == RUNTIME_BUILD_SHA256
              and observer_case.PINS == EXPECTED_PINS)

        runtime_build = json.loads(RUNTIME_BUILD.read_text())
        check('published amd64 build receipt matches current pins',
              runtime_build.get('status') == 'pass'
              and runtime_build.get('platform') == 'linux/amd64'
              and runtime_build.get('image_id') == IMAGE_ID
              and runtime_build.get('tag') == IMAGE
              and runtime_build.get('build_inputs', {}).get('dockerfile_sha256')
              == DOCKERFILE_SHA256)

        inspected = subprocess.run(
            ['docker', 'image', 'inspect', IMAGE], capture_output=True, text=True)
        check('pinned local image is available without pull', inspected.returncode == 0)
        image_info = json.loads(inspected.stdout)[0]
        report['image'].update({
            'actual_id': image_info.get('Id'),
            'actual_platform': f"{image_info.get('Os')}/{image_info.get('Architecture')}",
            'repo_tags': image_info.get('RepoTags') or [],
            'repo_digests': image_info.get('RepoDigests') or [],
        })
        php_version, php_modules = admit_and_probe_image(
            image_info, sha256(DOCKERFILE), check)
        report['image'].update({
            'php_version': php_version,
            'php_modules': php_modules,
        })

        original_brief = output / 'original-RESEARCHER-BRIEF.md'
        original_result = output / 'original-T01-observer-results.json'
        shutil.copy2(BRIEF, original_brief)
        shutil.copy2(T01_RESULT, original_result)
        check('pinned T01 comparator copies are exact',
              sha256(original_brief) == BRIEF_SHA256
              and sha256(original_result) == T01_RESULT_SHA256)

        observer_case.PHP_IMAGE = IMAGE_ID
        observer_case.PHP_IMAGE_DIGEST = IMAGE_RUNTIME_LABEL
        evidence = output / 'evidence'
        evidence.mkdir(mode=0o700)
        summaries = []
        for label, (commit, digest) in EXPECTED_PINS.items():
            source = observer_case.prepare_source(output, label, commit, digest)
            with tempfile.TemporaryDirectory(prefix=f'{label}-run-', dir=output) as temp:
                run_dir = Path(temp)
                summary = observer_case.run_arm(
                    label, source, run_dir, evidence, container_php=True)
                db_path = run_dir / 'app/data/db.sqlite'
            if run_dir.exists() or db_path.exists():
                raise RuntimeError(f'{label}: disposable run directory or DB remained')
            summary['cleanup'].update({
                'run_dir': str(run_dir),
                'run_dir_absent': True,
                'db_path': str(db_path),
                'db_absent': True,
            })
            summary['commit'] = commit
            summary['archive_sha256'] = digest
            summaries.append(summary)

        observer_result = {
            'case': 'Kanboard local observer preflight',
            'status': 'pass',
            'arms': summaries,
        }
        raw_result = evidence / 'observer-results.json'
        raw_result.write_text(json.dumps(observer_result, indent=2) + '\n')
        original = json.loads(original_result.read_text())
        for name, passed in observer_check_results(observer_result, original).items():
            check(name.replace('_', ' '), passed)

        public_result = public_observer_result(observer_result)
        public_path = evidence / 'observer-results.public.json'
        public_path.write_text(json.dumps(public_result, indent=2) + '\n')
        traces = {
            label: json.loads((evidence / f'{label}-requests.json').read_text())
            for label in EXPECTED_PINS}
        texts = {
            f'{label}-server': (evidence / f'{label}-server.log').read_text(errors='replace')
            for label in EXPECTED_PINS}
        texts['observer-result'] = public_path.read_text()
        for name, passed in artifact_check_results(
                traces, texts, [str(output)]).items():
            check(name.replace('_', ' '), passed)

        check('observer material was not mounted into a researcher',
              report['researcher_bundle_created'] is False
              and '--mount", f"type=bind,source={app},target=/app"' in OBSERVER.read_text())
        check('archives and extracted sources remain pinned after run', all(
              sha256(output / f'{label}.tar.gz') == digest
              and observer_case.prepare_source(output, label, commit, digest).is_dir()
              for label, (commit, digest) in EXPECTED_PINS.items()))
        check('repository inputs remain unchanged after run',
              sha256(OBSERVER) == OBSERVER_SHA256
              and sha256(T01_RESULT) == T01_RESULT_SHA256
              and sha256(BRIEF) == BRIEF_SHA256
              and sha256(DOCKERFILE) == DOCKERFILE_SHA256)
        report['result_sha256'] = {
            'raw_observer': sha256(raw_result),
            'public_observer': sha256(public_path),
        }
    except Exception as error:
        report['error'] = {
            'type': type(error).__name__,
            'message': str(error)[:500],
        }
    finally:
        try:
            after = docker_state()
            report['docker_after'] = after
            if before is not None:
                for name, passed in docker_baseline_check_results(before, after).items():
                    record(name.replace('_', ' '), passed)
        except Exception as cleanup_error:
            report['cleanup_error'] = {
                'type': type(cleanup_error).__name__,
                'message': str(cleanup_error)[:500],
            }
        report['status'] = (
            'pass' if report['checks'] and all(item['pass'] for item in report['checks'])
            and 'error' not in report and 'cleanup_error' not in report else 'fail')
        save()

    print(json.dumps({
        'status': report['status'],
        'checks': len(report['checks']),
        'output': str(output),
    }, sort_keys=True))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
