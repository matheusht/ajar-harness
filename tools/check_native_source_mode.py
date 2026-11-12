"""Failure-first source-mode checks. No provider or target engagement.

Default: offline contracts. --docker: synthetic executor lifecycle on a local image.
The Docker scenario replaces host authority checks with a local test owner; it is
not qualification of approval, stop ownership, native review, or paid transport.
"""
import argparse
import contextlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from unittest.mock import patch

import native_research as runner


def contracts():
    profile = {'version_command': ['python3', '--version'],
               'version_stdout': 'Python 3.13.0', 'dependency_command': ['true']}
    assert runner._validate_source_runtime(profile) == profile
    for bad in (dict(profile, extra=True), dict(profile, version_command=[]),
                dict(profile, dependency_command=['env', 'API_KEY=x']),
                dict(profile, version_stdout=''), dict(profile, version_command='python3')):
        try:
            runner._validate_source_runtime(bad)
        except runner.NativeResearchError:
            pass
        else:
            raise AssertionError('invalid runtime accepted')
    check = {'kind': 'native-source-check-v1', 'input_id': 'a' * 64,
             'effect': ['sh', 'effect.sh'], 'control': ['sh', 'control.sh'],
             'rationale': 'Control removes the triggering input.'}
    runner._validate_source_check(check, 'a' * 64)
    for bad in (dict(check, input_id='b' * 64), dict(check, control=check['effect']),
                dict(check, control=[]), dict(check, rationale='')):
        try:
            runner._validate_source_check(bad, 'a' * 64)
        except runner.NativeResearchError:
            pass
        else:
            raise AssertionError('invalid independent check accepted')
    runner._verify_source_original({'main.py': 'a'}, {'main.py': 'a', 'check.py': 'b'})
    for changed in ({'main.py': 'b'}, {'check.py': 'b'}):
        try:
            runner._verify_source_original({'main.py': 'a'}, changed)
        except runner.NativeResearchError:
            pass
        else:
            raise AssertionError('changed original accepted')
    with tempfile.TemporaryDirectory(prefix='native-source-approval-') as temp:
        root = Path(temp).resolve()
        controls = root / 'controls'
        controls.mkdir(mode=0o700)
        plan = {'source_only': {}, 'scope_sha256': 'a' * 64,
                'provider_route': 'fixture', 'model': 'fixture', 'limits': {}}
        runner._write_json(root / 'plan.json', plan, once=True)
        plan_sha = runner._sha(root / 'plan.json')
        approval = {'kind': 'native-research-live-approval-v1',
                    'plan_sha256': plan_sha, 'scope_sha256': plan['scope_sha256'],
                    'provider_route': plan['provider_route'], 'model': plan['model'],
                    'limits': plan['limits'],
                    'expires_at': '2000-01-01T00:00:00Z'}
        runner._write_json(controls / 'approval.json', approval, once=True)
        runner._write_json(controls / 'activation.json', {
            'kind': 'native-research-activation-v1', 'plan_sha256': plan_sha,
            'approval_sha256': runner._sha(controls / 'approval.json')}, once=True)
        with patch.object(runner, '_verified_plan', return_value=plan), \
             patch.object(runner, '_plan', return_value=plan), \
             patch.object(runner, 'run_active', return_value=True), \
             patch.object(runner, '_unresolved_dispatches', return_value=False):
            try:
                runner.source_execute(root)
            except runner.NativeResearchError as error:
                assert str(error) == 'research_approval_expired'
            else:
                raise AssertionError('expired approval allowed source dispatch')
        assert not (controls / 'source-executions').exists()
    return ['runtime_schema', 'check_and_control_binding', 'original_source_preserved',
            'expired_approval_blocks_source_dispatch']


def docker_scenario(image):
    # All containers and paths are owned by this check and removed in finally.
    runner.DOCKER_BINARY = Path(shutil.which('docker')).resolve()
    with tempfile.TemporaryDirectory(prefix='native-source-mode-') as temp:
        root = Path(temp).resolve()
        controls = root / 'controls'
        controls.mkdir(mode=0o700)
        (controls / 'source-executions').mkdir()
        (controls / 'dispatch').mkdir()
        (controls / 'source-modules').mkdir()
        original = root / 'original'
        original.mkdir()
        (original / 'experiment.sh').write_text(
            '#!/bin/sh\nset -eu\n[ ! -e previous ]\nprintf result > previous\nprintf first\\n\n')
        source = root / 'researcher/project'
        shutil.copytree(original, source)
        plan = {'source_only': {'runtime': {'version_command': ['sh', '-c', 'printf synthetic'],
                    'version_stdout': 'synthetic', 'dependency_command': ['true']},
                    'module_cache_sha256': 'a' * 64, 'build_command': ['sh', 'experiment.sh']},
                'source_sha256': runner._inventory(original), 'source_manifest_sha256': 'b' * 64,
                'target_image_id': image, 'platform': 'linux/arm64',
                'limits': {'duration_seconds': 30},
                'source_effect_envelope': runner.SOURCE_EFFECT_ENVELOPE}
        runner._write_json(root / 'plan.json', plan)
        runner._write_json(controls / 'target-command.json', ['sh', 'experiment.sh'])
        runner._write_json(controls / 'resources.json', {'nonce': root.name})
        bindings, created = {}, []
        native = type('Owner', (), {'dispatch_guard': staticmethod(lambda _: contextlib.nullcontext())})()
        try:
            for role in (*runner.CAPTURE_TARGETS, 'researcher', 'resume', 'reviewer-1'):
                target = root / role
                target.mkdir(exist_ok=True)
                if role in runner.CAPTURE_TARGETS:
                    shutil.copytree(original, target, dirs_exist_ok=True)
                result = runner._docker('container', 'run', '-d', '--pull', 'never', '--network', 'none',
                    '--read-only', '--restart', 'no', '--log-driver', 'none', '--cap-drop', 'ALL',
                    '--security-opt', 'no-new-privileges=true',
                    '--user', f'{os.getuid()}:{os.getgid()}', '--memory', '1g', '--cpus', '1',
                    '--pids-limit', '64', '--tmpfs', '/tmp:rw,nosuid,nodev,size=128m',
                    '--label', runner.LABEL + '=' + root.name,
                    '--mount', 'type=bind,src=' + str(target) + ',dst=/target',
                    '--mount', 'type=bind,src=' + str(controls / 'source-modules') + ',dst=/modules,readonly',
                    '-w', '/target', '--entrypoint', 'sh', image,
                    '-c', 'while :; do sleep 3600; done')
                bindings[role] = result.stdout.decode().strip()
                created.append(bindings[role])
            with contextlib.ExitStack() as stack:
                for name, value in (('_verified_plan', lambda *a, **k: plan),
                                    ('_plan', lambda _: plan),
                                    ('_resources', lambda _: bindings), ('run_active', lambda _: True),
                                    ('_approval_active', lambda _: None),
                                    ('_activate_controls', lambda _: (native, None)),
                                    ('stop', lambda _: None)):
                    stack.enter_context(patch.object(runner, name, value))
                assert runner._source_probe(root, bindings['target'])['runtime_version'] == 'synthetic'
                first = runner.source_execute(root)
                first_bytes = Path(first['receipt_path']).read_bytes()
                old_output = Path(first['receipt_path']).parent / 'target/files/previous'
                assert old_output.read_text() == 'result'
                (source / 'experiment.sh').write_text('printf second\\n\nprintf new > previous\n')
                second = runner.source_execute(root)
                assert Path(first['receipt_path']).read_bytes() == first_bytes
                assert old_output.read_text() == 'result'
                assert first['all_commands_succeeded'] and second['all_commands_succeeded']
                assert first['receipt_sha256'] != second['receipt_sha256']
                assert first['replay_output_equal'] and second['replay_output_equal']
                reviewer = root / 'reviewer-1/project'
                shutil.copytree(original, reviewer)
                (reviewer / 'check.sh').write_text('printf effect\\n')
                snapshot = controls / 'review-input'
                runner._freeze_source_input(root, snapshot, 'reviewer-1')
                runner._verify_source_original(plan['source_sha256'], runner._inventory(snapshot))
                command = controls / 'review-command.json'
                runner._write_json(command, ['sh', 'check.sh'])
                review = runner.source_execute(root, command, source_snapshot=snapshot, owner_role='reviewer-1')
                assert review['all_commands_succeeded']
                receipt = json.loads(Path(review['receipt_path']).read_text())
                assert receipt['owner_role'] == 'reviewer-1'
                # A changed original is refused before executing reviewer code.
                (snapshot / 'experiment.sh').write_text('printf changed')
                try:
                    runner.source_execute(root, command, source_snapshot=snapshot, owner_role='reviewer-1')
                except runner.NativeResearchError:
                    pass
                else:
                    raise AssertionError('review accepted modified original')
                # Uncertain prior effects prohibit a later batch.
                pending = controls / 'source-executions/pending'
                pending.mkdir()
                runner._write_json(pending / 'receipt.json', {'status': 'unknown_effect'})
                try:
                    runner.source_execute(root)
                except runner.NativeResearchError:
                    pass
                else:
                    raise AssertionError('unknown effect allowed another batch')
                return ['two_batches_three_clean_replays_each', 'old_outputs_preserved',
                        'reviewer_frozen_source_execution', 'modified_original_refused',
                        'unknown_effect_blocks_next_batch']
        finally:
            for identifier in created:
                runner._docker('container', 'rm', '-f', identifier, allow_failure=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--docker', help='existing local image ID with sh; never pulls')
    args = parser.parse_args()
    checks = contracts()
    if args.docker:
        assert args.docker.startswith('sha256:')
        checks += docker_scenario(args.docker)
    print(json.dumps({'checks': checks, 'status': 'passed',
                      'limits': 'Synthetic executor checks; no native model or provider qualification.'}, indent=2))
