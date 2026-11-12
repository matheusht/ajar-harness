#!/usr/bin/env python3
"""Contained #207 request, pair and denial scenario; no provider or target."""
from __future__ import annotations

import contextlib
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
import native_continuation as continuation
import native_closeout as closeout
import native_patch_check as paired
import native_research as runner
import check_agent_requested_review as source_check
import check_agent_closeout as closeout_check

ALLOWANCE = {'active': True, 'run_identity': {'nonce': 'synthetic'},
             'hard_limits': runner.DEFAULT_LIMITS,
             'used_tunnels': 0, 'charged_tunnel_bytes': 0}
DIFF = ("diff --git a/app.py b/app.py\n"
        "--- a/app.py\n+++ b/app.py\n"
        "@@ -1,2 +1,2 @@\n import sys\n"
        "-print('before' if sys.argv[1] == 'effect' else sys.argv[1])\n"
        "+print('after' if sys.argv[1] == 'effect' else sys.argv[1])\n")
APP = "import sys\nprint('before' if sys.argv[1] == 'effect' else sys.argv[1])\n"
CHECKS = {'effect': 'python3 app.py effect\n',
          'control': 'python3 app.py control\n',
          'normal': 'python3 app.py normal\n',
          'connected': 'python3 app.py connected\n'}


def fixture(base: Path, *, patch_goal: bool = True,
            last_state: str = 'inconclusive') -> Path:
    root = source_check.fixture(base)
    for name in ('original', 'researcher/project', 'reviewer-1/project', 'reviewer-2/project'):
        (root / name / 'app.py').write_text(APP)
    plan = runner._read_json(root / 'plan.json')
    source = runner._inventory(root / 'original')
    plan['source_sha256'] = source
    plan['source_manifest_sha256'] = hashlib.sha256(
        json.dumps(source, sort_keys=True).encode()).hexdigest()
    plan['checked_setup'] = {'synthetic': True}
    plan['source_effect_envelope'] = runner.CHECKED_SOURCE_EFFECT_ENVELOPE
    brief = root / 'controls/research/BRIEF.md'
    brief.write_text('Check the harmless source behavior.\n' +
                     ('Patch goal: required\n' if patch_goal else 'No patch requested.\n'))
    brief.chmod(0o600)
    plan['brief_sha256'] = runner._sha(brief)
    runner._write_json(root / 'plan.json', plan)
    (root / 'researcher/PATCH.diff').write_text(DIFF)
    (root / 'researcher/PATCH.diff').chmod(0o600)
    (root / 'researcher/project/RESULT.md').write_text(
        closeout_check.result_text('paired patch check') +
        '\nProposed fix: the effect path changes from before to after; '
        'normal and connected paths need independent checks.\n')
    runner._write_json(root / 'researcher/NEXT.json', {
        'kind': continuation.NEXT_KIND,
        'last_result': {'state': last_state, 'rules_out': 'none',
                        'unresolved': 'paired effect and normal behavior'},
        'capabilities': [], 'coverage': [], 'strong_lead': True,
        'proposed_stop': False, 'next': None,
        'host_action': {'kind': 'native-patch-check-v1',
                        'claim': 'The diff removes the before branch without changing normal paths.'}})
    return root


def denial(fn, reason: str) -> None:
    try:
        fn()
    except (paired.PatchCheckError, closeout.CloseoutError,
            continuation.ContinuationError,
            runner.NativeResearchError, ValueError) as error:
        assert reason in str(error), (reason, str(error))
    else:
        raise AssertionError('accepted_' + reason)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix='paired-patch-e2e-') as temporary:
        base = Path(temporary).resolve()
        root = fixture(base / 'valid')
        plan = runner._read_json(root / 'plan.json')
        nxt = continuation._next(root)
        next_sha = continuation._next_hash(root)
        module = runner._load_review_module(root)
        request = paired.freeze_patch(root, nxt, next_sha, plan, ALLOWANCE, module)
        pair = paired.verify_patch(root, request, plan, module)
        assert pair['original_manifest'] == plan['source_sha256']
        assert pair['patched_manifest']['app.py'] != plan['source_sha256']['app.py']
        assert runner._inventory(root / 'original') == plan['source_sha256']
        reviewer = root / 'reviewer-1/project'
        for name, content in CHECKS.items():
            (reviewer / (name + '.sh')).write_text(content)
        review_input = root / 'controls/paired-review-input'
        shutil.copytree(reviewer, review_input)
        original_input = runner._inventory(review_input)
        patched_input, patched_inventory, scripts = paired.review_input(
            root, request, review_input, original_input)
        assert original_input['effect.sh'] == patched_inventory['effect.sh']
        assert scripts == {'effect.sh': original_input['effect.sh'],
                           'control.sh': original_input['control.sh'],
                           'normal.sh': original_input['normal.sh'],
                           'connected.sh': original_input['connected.sh']}
        assert runner._inventory(patched_input) == patched_inventory
        check = {'kind': 'native-paired-source-check-v1', 'input_id': 'fixture',
                 'effect': ['sh', 'effect.sh'], 'control': ['sh', 'control.sh'],
                 'normal': ['sh', 'normal.sh'], 'connected': ['sh', 'connected.sh'],
                 'rationale': 'Same effect and ordinary paths on clean paired copies.'}
        assert runner._validate_source_check(check, 'fixture', paired=True) == check
        denied = []
        for missing in ('effect', 'control', 'normal', 'connected'):
            broken = dict(check)
            del broken[missing]
            denial(lambda: runner._validate_source_check(broken, 'fixture', paired=True),
                   'source_review_check_invalid')
            denied.append('missing_' + missing)
        for case in ('goal_missing', 'older_route', 'diff_missing', 'unsafe_path',
                     'symlink_patch', 'diff_changed', 'original_changed',
                     'patched_changed', 'script_collision'):
            trial = fixture(base / case, patch_goal=case != 'goal_missing')
            trial_plan = runner._read_json(trial / 'plan.json')
            trial_next = continuation._next(trial)
            trial_sha = continuation._next_hash(trial)
            trial_module = runner._load_review_module(trial)
            if case == 'diff_missing':
                (trial / 'researcher/PATCH.diff').unlink()
            if case == 'older_route':
                trial_plan.pop('checked_setup')
                trial_plan['source_effect_envelope'] = runner.SOURCE_EFFECT_ENVELOPE
                runner._write_json(trial / 'plan.json', trial_plan)
            if case == 'unsafe_path':
                (trial / 'researcher/PATCH.diff').write_text(
                    'diff --git a/../escaped b/../escaped\n'
                    '--- a/../escaped\n+++ b/../escaped\n'
                    '@@ -0,0 +1 @@\n+escape\n')
            if case == 'symlink_patch':
                (trial / 'researcher/PATCH.diff').write_text(
                    'diff --git a/link b/link\nnew file mode 120000\n'
                    '--- /dev/null\n+++ b/link\n@@ -0,0 +1 @@\n+/tmp\n')
            if case == 'original_changed':
                (trial / 'original/app.py').write_text("print('tampered')\n")
            if case == 'script_collision':
                (trial / 'researcher/PATCH.diff').write_text(
                    'diff --git a/collision.py b/collision.py\nnew file mode 100644\n'
                    '--- /dev/null\n+++ b/collision.py\n@@ -0,0 +1 @@\n+collision\n')
            if case in ('goal_missing', 'older_route', 'diff_missing', 'original_changed',
                        'unsafe_path', 'symlink_patch'):
                denial(lambda: paired.freeze_patch(trial, trial_next, trial_sha,
                       trial_plan, ALLOWANCE, trial_module), 'patch_')
            else:
                frozen = paired.freeze_patch(trial, trial_next, trial_sha,
                                             trial_plan, ALLOWANCE, trial_module)
                if case == 'diff_changed':
                    (trial / 'researcher/PATCH.diff').write_text(DIFF + '\n')
                    denial(lambda: paired.verify_patch(trial, frozen, trial_plan,
                                                       trial_module), 'patch_')
                elif case == 'patched_changed':
                    (trial / 'controls/continuation/patches' / trial_sha /
                     'patched/app.py').write_text("print('forged')\n")
                    denial(lambda: paired.verify_patch(trial, frozen, trial_plan,
                                                       trial_module), 'patch_')
                else:
                    (trial / 'reviewer-1/project/collision.py').write_text('test\n')
                    original = trial / 'controls/review-input'
                    shutil.copytree(trial / 'reviewer-1/project', original)
                    denial(lambda: paired.review_input(trial, frozen, original,
                                                       runner._inventory(original)), 'patch_')
            denied.append(case)
        # Exercise the public host-review action with a synthetic local source
        # executor. It runs the same frozen reviewer commands on both trees.
        paired_run = fixture(base / 'paired-execution', last_state='supported')
        paired_plan = runner._read_json(paired_run / 'plan.json')
        (paired_run / 'controls/source-evidence/reviewer-1').mkdir(parents=True, mode=0o700)
        paired_next = continuation._next(paired_run)
        paired_state = continuation._state(paired_run)
        paired_module = runner._load_review_module(paired_run)
        review_calls = []

        def freeze_input(run_root, destination, role):
            shutil.copytree(run_root / role / 'project', destination)
            if role.startswith('reviewer-'):
                shutil.copy2(run_root / role / 'source-check.json', destination.parent / 'source-check.json')
                (destination.parent / 'source-check.json').chmod(0o600)
            return runner._inventory(destination)

        def initial_review(run_root, packet, pin, role, **kwargs):
            review_calls.append(role)
            reviewer = run_root / role
            for name, content in CHECKS.items():
                (reviewer / 'project' / (name + '.sh')).write_text(content)
            runner._write_json(reviewer / 'source-check.json', {
                'kind': 'native-paired-source-check-v1', 'input_id': pin['input_id'],
                'effect': ['sh', 'effect.sh'], 'control': ['sh', 'control.sh'],
                'normal': ['sh', 'normal.sh'], 'connected': ['sh', 'connected.sh'],
                'rationale': 'Check the same harmless branch and adjacent paths on both copies.'})
            return {'status': 'native_turn_observed_unassessed', 'session_id': 'ses_synthetic',
                    'native': {'dispatch_id': 'a' * 32},
                    'allowance_before': ALLOWANCE, 'allowance_after': ALLOWANCE}

        executions = []

        def local_execute(run_root, command_file, *, source_snapshot, owner_role,
                          paired_request, source_variant):
            command = json.loads(command_file.read_bytes())
            identity = f'{len(executions) + 1:032x}'
            directory = run_root / 'controls/source-executions' / identity
            directory.mkdir(mode=0o700)
            inventory = runner._inventory(source_snapshot)
            shutil.copytree(source_snapshot, directory / 'input')
            runner._write_json(directory / 'input-manifest.json', inventory, once=True)
            receipt = {'kind': 'native-source-execution-v1', 'status': 'captured',
                       'execution_id': identity, 'owner_role': owner_role,
                       'plan_sha256': runner._sha(run_root / 'plan.json'),
                       'command': command, 'source_variant': source_variant,
                       'paired_patch_request_sha256': runner._sha(paired_request),
                       'input_manifest_sha256': runner._sha(directory / 'input-manifest.json'),
                       'replay_output_equal': True, 'runs': []}
            for role in runner.CAPTURE_TARGETS:
                folder = directory / role
                folder.mkdir(mode=0o700)
                work = folder / 'files'
                shutil.copytree(source_snapshot, work)
                run = subprocess.run(command, cwd=work, stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=5)
                output_inventory = runner._inventory(work)
                runner._write_json(folder / 'files.json', output_inventory, once=True)
                (folder / 'stdout.txt').write_bytes(run.stdout)
                (folder / 'stderr.txt').write_bytes(run.stderr)
                receipt['runs'].append({'role': role, 'exit_code': run.returncode,
                    'stdout_sha256': runner._sha(folder / 'stdout.txt'),
                    'stderr_sha256': runner._sha(folder / 'stderr.txt'),
                    'output_manifest_sha256': runner._sha(folder / 'files.json')})
            runner._write_json(directory / 'receipt.json', receipt, once=True)
            executions.append((source_variant, tuple(command)))
            return {'status': 'captured', 'receipt_path': str(directory / 'receipt.json'),
                    'receipt_sha256': runner._sha(directory / 'receipt.json')}

        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(runner, '_verified_plan',
                side_effect=lambda run_root, **kw: runner._read_json(run_root / 'plan.json')))
            stack.enter_context(patch.object(runner, '_approval_active'))
            stack.enter_context(patch.object(runner, '_unresolved_dispatches', return_value=[]))
            stack.enter_context(patch.object(runner, '_source_executor_envelope'))
            stack.enter_context(patch.object(runner, 'native_api',
                side_effect=lambda *args: {'items': []}))
            stack.enter_context(patch.object(runner, '_load_review_module', return_value=paired_module))
            stack.enter_context(patch.object(runner, '_freeze_source_input', side_effect=freeze_input))
            stack.enter_context(patch.object(runner, 'allowance_snapshot', return_value=ALLOWANCE))
            stack.enter_context(patch.object(runner, 'run_active', return_value=True))
            stack.enter_context(patch.object(runner, 'source_execute', side_effect=local_execute))
            stack.enter_context(patch.object(runner, 'invoke_native',
                side_effect=lambda *args, **kw: {'status': 'acknowledged', '_raw_stdout': ''}))
            stack.enter_context(patch.object(runner, '_source_evidence_read', return_value=True))
            stack.enter_context(patch.object(paired_module, 'invoke_fresh_review', side_effect=initial_review))
            stack.enter_context(patch.object(paired_module, 'project_review_material',
                side_effect=lambda run_root, packet, pin, invocation, raw, **kw: {
                    'status': 'captured', 'input_id': pin['input_id'],
                    'outcome': {'decision': 'raise',
                    'checked_link': ('The app effect path prints before on original and after '
                        'on patched because the diff changes that branch; normal and connected '
                        'paths remain stable. source-evidence-sha256:' + runner._sha(
                        run_root / 'controls/source-evidence/reviewer-1/RESULTS.json') +
                        ' patch-diff-sha256:' + runner._read_json(
                        run_root / 'controls/continuation/patches' /
                        continuation._next_hash(run_root) / 'request.json')['diff_sha256'])}}))
            stack.enter_context(patch.object(paired_module, '_same_allowance', return_value=True))
            result = continuation._agent_review(paired_run, paired_state, paired_next)
            assert result['status'] == 'captured' and review_calls == ['reviewer-1']
            packet = paired_run / 'handoff/reviewer-1'
            assert 'PATCH.json' in json.loads((packet / 'REQUEST.json').read_text())['roles']['conditions']
            assert (packet / 'PATCH.diff').read_text() == DIFF
            receipt = runner._read_json(paired_run / 'controls/review-reviewer-1.json')
            assert continuation._agent_review(paired_run, paired_state, paired_next)['status'] == 'captured'
            assert review_calls == ['reviewer-1']
        evidence = json.loads((paired_run / 'controls/source-evidence/reviewer-1/RESULTS.json').read_bytes())
        assert receipt['status'] == 'reviewed' and receipt['patch_assessment'] == 'checked_fix_candidate'
        assert paired.verify_review_evidence(paired_run, 'reviewer-1', receipt) == evidence
        assert evidence['paired_observation']['status'] == 'differential_with_normal_paths_preserved'
        expected = {variant: {'effect': effect, 'control': 'control\n',
                              'normal': 'normal\n', 'connected': 'connected\n'}
                    for variant, effect in (('original', 'before\n'), ('patched', 'after\n'))}
        observed = {variant: {name: evidence['cases'][variant][name]['outputs']['target']['stdout']
                              for name in CHECKS}
                    for variant in ('original', 'patched')}
        assert observed == expected, observed
        no_fix_link = copy.deepcopy(receipt)
        no_fix_link['material']['outcome']['checked_link'] = (
            'source-evidence-sha256:' + receipt['evidence_sha256'])
        no_fix_link['assessment']['outcome'] = no_fix_link['material']['outcome']
        denial(lambda: paired.verify_review_evidence(paired_run, 'reviewer-1', no_fix_link),
               'patch_review_assessment_changed')
        denied.append('missing_material_fix_link')
        assert len(executions) == 8 and len({command for _, command in executions}) == 4
        assert {variant for variant, _ in executions} == {'original', 'patched'}
        stop_next = dict(paired_next, host_action=None, proposed_stop=True)
        runner._write_json(paired_run / 'researcher/NEXT.json', stop_next)
        (paired_run / 'controls/owner.lock').write_text('')
        (paired_run / 'controls/owner.lock').chmod(0o600)
        stop_calls = []

        def local_stop(run_root):
            stop_calls.append('stop')
            closeout_check.write_final(run_root, complete=False)
            return {'status': 'stop_requested', 'run_root': str(run_root)}

        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(runner, '_verified_plan',
                side_effect=lambda run_root, **kw: runner._read_json(run_root / 'plan.json')))
            stack.enter_context(patch.object(runner, '_approval_active'))
            stack.enter_context(patch.object(runner, '_unresolved_dispatches', return_value=[]))
            stack.enter_context(patch.object(runner, 'allowance_snapshot', return_value=ALLOWANCE))
            stack.enter_context(patch.object(runner, 'run_active', return_value=True))
            stack.enter_context(patch.object(runner, '_docker',
                side_effect=lambda *argv, **kw: subprocess.CompletedProcess(
                    argv, 0, stdout=(b'synthetic-daemon-A\n' if argv[0] == 'info' else b''),
                    stderr=b'')))
            pending = closeout.closeout(paired_run, wait_seconds=0, stop_fn=local_stop)
            assert pending['status'] == 'cleanup_unverified' and stop_calls == ['stop']
            closeout_check.write_final(paired_run)
            close = closeout.closeout(paired_run, wait_seconds=0, stop_fn=local_stop)
        assert close['status'] == 'complete_internal_candidate', close
        close_record = runner._read_json(Path(close['record_path']))
        assert close_record['request']['review']['patch_check']['assessment'] == 'checked_fix_candidate'
        assert close_record['cleanup']['status'] == 'verified' and stop_calls == ['stop']
        assert close_record['cleanup']['resource_absence'] is True
        denied.append('uncertain_cleanup_before_readback')
        original_cleanup = runner._read_json(paired_run / 'controls/cleanup.json')
        cleanup = dict(original_cleanup)
        cleanup['status'] = 'unresolved'
        runner._write_json(paired_run / 'controls/cleanup.json', cleanup)
        denial(lambda: closeout._final_readback(paired_run), 'closeout_owner_cleanup_unverified')
        denied.append('failed_cleanup_readback')
        runner._write_json(paired_run / 'controls/cleanup.json', original_cleanup)
        script = paired_run / 'controls/source-review-reviewer-1/input/effect.sh'
        original_script = script.read_bytes()
        script.write_text('python3 app.py control\n')
        denial(lambda: paired.verify_review_evidence(paired_run, 'reviewer-1', receipt),
               'patch_review_input_changed')
        denied.append('changed_reviewer_script')
        script.write_bytes(original_script)
        tampered = paired_run / 'controls/source-executions' / evidence['cases']['patched']['effect']['receipt']['execution_id'] / runner.CAPTURE_TARGETS[0] / 'stdout.txt'
        tampered.write_text('forged\n')
        denial(lambda: paired.verify_review_evidence(paired_run, 'reviewer-1', receipt), 'patch_review_output_changed')
        denied.append('changed_protected_output')
        patch_area = paired_run / 'controls/continuation/patches' / evidence['patch']['request']['action_id']
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(runner, '_verified_plan',
                side_effect=lambda run_root, **kw: runner._read_json(run_root / 'plan.json')))
            stack.enter_context(patch.object(runner, '_approval_active'))
            stack.enter_context(patch.object(runner, '_unresolved_dispatches', return_value=[]))
            stack.enter_context(patch.object(runner, '_source_executor_envelope'))
            stack.enter_context(patch.object(runner, 'run_active', return_value=True))
            denial(lambda: runner.source_execute(paired_run,
                paired_run / 'controls/source-review-reviewer-1/effect.json',
                source_snapshot=patch_area / 'review-input-patched', owner_role='reviewer-1',
                paired_request=patch_area / 'request.json', source_variant='original'),
                'source_review_original_changed')
        denied.append('patched_copy_as_original')
        no_patch = closeout_check.setup(base / 'no-patch', outcome='supported')
        assert paired.goal_required(no_patch, runner._read_json(no_patch / 'plan.json')) is False
        no_patch_stops = []

        def stop_without_patch(run_root):
            no_patch_stops.append('stop')
            closeout_check.write_final(run_root)
            return {'status': 'stop_requested', 'run_root': str(run_root)}

        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(runner, '_verified_plan',
                side_effect=lambda run_root, **kw: runner._read_json(run_root / 'plan.json')))
            stack.enter_context(patch.object(runner, '_approval_active'))
            stack.enter_context(patch.object(runner, '_unresolved_dispatches', return_value=[]))
            stack.enter_context(patch.object(runner, 'allowance_snapshot',
                return_value=closeout_check.ALLOWANCE))
            stack.enter_context(patch.object(runner, 'run_active', return_value=True))
            stack.enter_context(patch.object(runner, '_docker',
                side_effect=lambda *argv, **kw: subprocess.CompletedProcess(
                    argv, 0, stdout=(b'synthetic-daemon-A\n' if argv[0] == 'info' else b''),
                    stderr=b'')))
            ordinary_close = closeout.closeout(no_patch, wait_seconds=0,
                                               stop_fn=stop_without_patch)
        assert ordinary_close['status'] == 'complete_internal_candidate', ordinary_close
        assert no_patch_stops == ['stop']
        ordinary_record = runner._read_json(Path(ordinary_close['record_path']))
        assert ordinary_record['request']['review']['patch_check'] is None
        execution_receipts = {variant: {name: {
            'receipt_sha256': evidence['cases'][variant][name]['receipt_sha256'],
            'input_manifest_sha256': evidence['cases'][variant][name]['receipt']['input_manifest_sha256'],
            'runs': [{key: row[key] for key in ('role', 'exit_code', 'stdout_sha256',
                                                'stderr_sha256', 'output_manifest_sha256')}
                     for row in evidence['cases'][variant][name]['receipt']['runs']]}
            for name in CHECKS} for variant in ('original', 'patched')}
        print(json.dumps({'status': 'passed', 'provider_calls': 0, 'target_calls': 0,
                          'original_manifest_sha256': plan['source_manifest_sha256'],
                          'patch_request_sha256': runner._sha(root / 'controls/continuation/patches'
                                                              / next_sha / 'request.json'),
                          'patched_manifest_sha256': request['patched_manifest_sha256'],
                          'denied': denied, 'review_calls': review_calls,
                          'commands': {name: ['sh', name + '.sh'] for name in CHECKS},
                          'observed_stdout': observed,
                          'patch_request': request,
                          'execution_receipts': execution_receipts,
                          'paired_executions': len(executions),
                          'synthetic_source_replays': len(executions) * len(runner.CAPTURE_TARGETS),
                          'cost': {'provider_calls': 0, 'target_calls': 0,
                                   'monetary_spend': 'not metered; synthetic local fixture'},
                          'checked_closeout_sha256': close['record_sha256'],
                          'checked_cleanup': close_record['cleanup']['status'],
                          'checked_cleanup_receipt': close_record['cleanup'],
                          'no_patch_closeout_sha256': ordinary_close['record_sha256'],
                          'no_patch_cleanup': ordinary_record['cleanup']['status'],
                          'no_patch_cleanup_receipt': ordinary_record['cleanup'],
                          'paired_evidence_sha256': runner._sha(
                              paired_run / 'controls/source-evidence/reviewer-1/RESULTS.json')},
                         sort_keys=True))


if __name__ == '__main__':
    main()
