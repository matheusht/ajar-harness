#!/usr/bin/env python3
"""Repeat the T01 observer under the pinned derived V2/PHP image, without model access."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import observer_case  # noqa: E402

IMAGE = 't02-kanboard-runtime:20261020a'
IMAGE_ID = 'sha256:31b7fa2b80f17bbddfeffd0577634257df40490f1b8d4c57f8507b40956cdf15'
IMAGE_DIGEST = 't02-kanboard-runtime@' + IMAGE_ID
ORIGINAL = Path('/private/tmp/native-qualification-observer-20261019-final')
T01_RESULT = HERE / 'observer-evidence-final/observer-results.json'
BRIEF = HERE / 'RESEARCHER-BRIEF.md'
DOCKERFILE = HERE / 'Dockerfile.opencode-kanboard-runtime'
CHECKS = HERE / 'T02-PHP-PARITY-CHECKS-20261020.md'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    report = {'classification': 'offline derived-runtime observer parity; no model/provider calls',
              'image': IMAGE, 'image_id': IMAGE_ID, 'checks': [],
              'source_sha256': {str(path.relative_to(HERE)): sha(path) for path in
                  (Path(__file__), HERE / 'observer_case.py', BRIEF, DOCKERFILE, CHECKS)}}

    def check(name, condition):
        report['checks'].append({'name': name, 'pass': bool(condition)})
        (output / 'parity-result.json').write_text(json.dumps(report, indent=2) + '\n')
        if not condition:
            raise AssertionError(name)

    try:
        original_brief = output / 'original-RESEARCHER-BRIEF.md'
        original_result = output / 'original-T01-observer-results.json'
        shutil.copy2(BRIEF, original_brief)
        shutil.copy2(T01_RESULT, original_result)
        report['original_sha256'] = {'brief': sha(original_brief), 't01_result': sha(original_result)}
        check('original brief and T01 receipt byte copies', sha(BRIEF) == sha(original_brief)
              and sha(T01_RESULT) == sha(original_result))
        image = subprocess.run(['docker', 'image', 'inspect', IMAGE], capture_output=True, text=True)
        check('exact local derived image ID', image.returncode == 0 and
              json.loads(image.stdout)[0]['Id'] == IMAGE_ID and
              IMAGE_DIGEST in json.loads(image.stdout)[0]['RepoDigests'])
        check('Dockerfile pins V2 base and PHP packages',
              'ghcr.io/anomalyco/opencode@sha256:2fc782d346b0670c43378557cf8a2a9926a1f3d28e596180e7b21a0736d8cb7d' in DOCKERFILE.read_text()
              and 'php84=8.4.26-r0' in DOCKERFILE.read_text())
        version = subprocess.run(['docker', 'run', '--rm', '--pull', 'never', '--network', 'none',
                                  '--entrypoint', 'php', IMAGE, '-v'], capture_output=True, text=True)
        modules = subprocess.run(['docker', 'run', '--rm', '--pull', 'never', '--network', 'none',
                                  '--entrypoint', 'php', IMAGE, '-m'], capture_output=True, text=True)
        report['php_version'] = version.stdout.splitlines()[0] if version.returncode == 0 else None
        report['php_modules'] = sorted(set(modules.stdout.splitlines())) if modules.returncode == 0 else []
        check('actual PHP 8.4.26 with SQLite and GD', version.returncode == modules.returncode == 0
              and report['php_version'].startswith('PHP 8.4.26 ')
              and {'pdo_sqlite', 'gd'} <= {x.lower() for x in report['php_modules']})
        for label, (_, digest) in observer_case.PINS.items():
            source = ORIGINAL / (label + '.tar.gz')
            check(label + ' original archive pinned', source.is_file() and sha(source) == digest)
            shutil.copy2(source, output / source.name)
            check(label + ' copied archive pinned', sha(output / source.name) == digest)

        observer_case.PHP_IMAGE = IMAGE
        observer_case.PHP_IMAGE_DIGEST = IMAGE_DIGEST
        old_argv = sys.argv
        try:
            sys.argv = [str(HERE / 'observer_case.py'), '--observer-root', str(output), '--container-php']
            check('same T01 observer flow completed', observer_case.main() == 0)
        finally:
            sys.argv = old_argv
        new = json.loads((output / 'evidence/observer-results.json').read_text())
        original = json.loads(original_result.read_text())
        comparable = ('release', 'loopback', 'project_id', 'swimlane_id', 'authorized_project',
                      'authorized_swimlane', 'private_project_control', 'cross_role_read',
                      'commit', 'archive_sha256')
        check('both arm semantic outcomes equal T01', len(new['arms']) == len(original['arms']) == 2
              and all({key: arm[key] for key in comparable} ==
                      {key: prior[key] for key in comparable}
                      for arm, prior in zip(new['arms'], original['arms'])))
        check('both arms used exact derived PHP runtime', all(arm['runtime'] == IMAGE_DIGEST
              and arm['php'].startswith('PHP 8.4.26 ') for arm in new['arms']))
        check('all owned app containers, ports and databases gone', all(
              arm['cleanup']['container_absent'] and arm['cleanup']['port_closed']
              and arm['cleanup']['run_dir_absent'] and arm['cleanup']['db_absent']
              for arm in new['arms']))
        report['observer_result_sha256'] = sha(output / 'evidence/observer-results.json')
        report['semantic_comparison'] = {'vulnerable': 'same exact created metadata',
                                         'fixed': 'same cross-role 403',
                                         'ordinary': 'same authorized reads and private-project 403'}
        check('original source, brief and T01 result unchanged',
              sha(BRIEF) == report['original_sha256']['brief'] and
              sha(T01_RESULT) == report['original_sha256']['t01_result'] and
              sha(HERE / 'observer_case.py') == report['source_sha256']['observer_case.py'])
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
    report['status'] = 'pass' if report['checks'] and all(x['pass'] for x in report['checks']) else 'fail'
    (output / 'parity-result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'checks': len(report['checks']), 'output': str(output)}))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
