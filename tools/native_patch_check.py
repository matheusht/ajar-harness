#!/usr/bin/env python3
"""Freeze one goal-authorized diff against the sealed original source."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

import native_research as runner

ACTION_KIND = 'native-patch-check-v1'
REQUEST_KIND = 'native-patch-request-v1'
GOAL_LINE = re.compile(r'(?m)^Patch goal: required\s*$')
MAX_DIFF_BYTES = 1024 * 1024


class PatchCheckError(RuntimeError):
    pass


def _fail(reason: str) -> None:
    raise PatchCheckError(reason)


def _manifest_sha(manifest: dict) -> str:
    return hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()


def _area(root: Path, next_sha: str) -> Path:
    if not isinstance(next_sha, str) or not re.fullmatch(r'[0-9a-f]{64}', next_sha):
        _fail('patch_request_invalid')
    base = root / 'controls/continuation/patches'
    base.mkdir(mode=0o700, exist_ok=True)
    return base / next_sha


def goal_required(root: Path, plan: dict) -> bool:
    if 'brief_sha256' not in plan:
        return False
    path = runner._file(root / 'controls/research/BRIEF.md', private=True)
    if runner._sha(path) != plan.get('brief_sha256'):
        _fail('patch_goal_changed')
    return bool(GOAL_LINE.search(path.read_text()))


def _goal(root: Path, plan: dict) -> None:
    if 'checked_setup' not in plan:
        _fail('patch_signed_goal_required')
    if not goal_required(root, plan):
        _fail('patch_goal_not_authorized')


def _diff(root: Path, module) -> bytes:
    try:
        path = runner._file(root / 'researcher/PATCH.diff')
    except runner.NativeResearchError:
        _fail('patch_diff_unavailable')
    data = path.read_bytes()
    if not 0 < len(data) <= MAX_DIFF_BYTES:
        _fail('patch_diff_missing_or_oversize')
    try:
        if module.validate_public_bytes(data) != data:
            _fail('patch_diff_unsafe')
        data.decode('utf-8')
    except (UnicodeError, ValueError):
        _fail('patch_diff_unsafe')
    if (b'GIT binary patch' in data or b'\x00' in data
            or re.search(rb'(?m)^(?:new |old )?file mode 120000\s*$', data)
            or re.search(rb'(?m)^new mode 120000\s*$', data)):
        _fail('patch_diff_unsafe')
    return data


def _apply(directory: Path, data: bytes) -> None:
    for check in (True, False):
        command = ['git', 'apply', '--no-unsafe-paths', '--check' if check else '--apply', '-']
        try:
            result = subprocess.run(command, cwd=directory, input=data,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    timeout=30, check=False)
        except (OSError, subprocess.TimeoutExpired):
            _fail('patch_apply_unavailable')
        if result.returncode != 0:
            _fail('patch_diff_not_applicable')


def freeze_patch(root: Path, nxt: dict, next_sha: str, plan: dict,
                 allowance: dict, module) -> dict:
    action = nxt.get('host_action') if isinstance(nxt, dict) else None
    if not isinstance(action, dict) or action.get('kind') != ACTION_KIND:
        _fail('patch_request_invalid')
    _goal(root, plan)
    try:
        runner._verify_inventory(root / 'original', plan['source_sha256'])
    except runner.NativeResearchError:
        _fail('patch_original_changed')
    data = _diff(root, module)
    area = _area(root, next_sha)
    if area.exists() or area.is_symlink():
        if not (area / 'request.json').exists():
            _fail('patch_freeze_incomplete')
        request = runner._read_json(area / 'request.json')
        verify_patch(root, request, plan, module)
        return request
    area.mkdir(mode=0o700)
    diff_path = area / 'PATCH.diff'
    descriptor = os.open(diff_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    patched = area / 'patched'
    shutil.copytree(root / 'original', patched)
    _apply(patched, data)
    original_manifest = runner._inventory(root / 'original')
    patched_manifest = runner._inventory(patched)
    original_modes = runner._file_modes(root / 'original', original_manifest)
    patched_modes = runner._file_modes(patched, patched_manifest)
    if original_manifest == patched_manifest and original_modes == patched_modes:
        _fail('patch_diff_empty')
    runner._write_json(area / 'original-manifest.json', original_manifest, once=True)
    runner._write_json(area / 'patched-manifest.json', patched_manifest, once=True)
    runner._write_json(area / 'original-modes.json', original_modes, once=True)
    runner._write_json(area / 'patched-modes.json', patched_modes, once=True)
    request = {'kind': REQUEST_KIND, 'action_id': next_sha, 'next_sha256': next_sha,
               'claim': nxt['host_action']['claim'],
               'plan_sha256': runner._sha(root / 'plan.json'),
               'scope_sha256': plan['scope_sha256'],
               'goal_sha256': plan['brief_sha256'],
               'approval_sha256': runner._sha(root / 'controls/approval.json'),
               'diff_sha256': runner._sha(diff_path),
               'original_manifest_sha256': _manifest_sha(original_manifest),
               'patched_manifest_sha256': _manifest_sha(patched_manifest),
               'original_mode_sha256': _manifest_sha(original_modes),
               'patched_mode_sha256': _manifest_sha(patched_modes),
               'copies': ['original', 'patched'], 'actor': 'researcher',
               'initial_state': 'sealed_original_source',
               'approved_effect_envelope': plan['source_effect_envelope'],
               'allowance_before': allowance}
    runner._write_json(area / 'request.json', request, once=True)
    return request


def verify_patch(root: Path, request: dict, plan: dict, module) -> dict:
    if not isinstance(request, dict):
        _fail('patch_request_invalid')
    next_sha = request.get('action_id')
    area = _area(root, next_sha)
    _goal(root, plan)
    if (request.get('kind') != REQUEST_KIND
            or request.get('next_sha256') != next_sha
            or request.get('plan_sha256') != runner._sha(root / 'plan.json')
            or request.get('scope_sha256') != plan['scope_sha256']
            or request.get('goal_sha256') != plan['brief_sha256']
            or request.get('approval_sha256') != runner._sha(root / 'controls/approval.json')
            or request.get('copies') != ['original', 'patched']
            or request.get('actor') != 'researcher'
            or request.get('initial_state') != 'sealed_original_source'
            or request.get('approved_effect_envelope') != plan['source_effect_envelope']
            or runner._read_json(area / 'request.json') != request):
        _fail('patch_request_changed')
    data = _diff(root, module)
    if hashlib.sha256(data).hexdigest() != request.get('diff_sha256'):
        _fail('patch_diff_changed')
    if runner._sha(runner._file(area / 'PATCH.diff', private=True)) != request['diff_sha256']:
        _fail('patch_diff_changed')
    original = runner._read_json(area / 'original-manifest.json')
    patched = runner._read_json(area / 'patched-manifest.json')
    original_modes = runner._read_json(area / 'original-modes.json')
    patched_modes = runner._read_json(area / 'patched-modes.json')
    if (original != plan['source_sha256']
            or _manifest_sha(original) != request['original_manifest_sha256']
            or _manifest_sha(patched) != request['patched_manifest_sha256']
            or _manifest_sha(original_modes) != request['original_mode_sha256']
            or _manifest_sha(patched_modes) != request['patched_mode_sha256']):
        _fail('patch_manifest_changed')
    try:
        runner._verify_inventory(root / 'original', original)
        runner._verify_inventory(area / 'patched', patched)
    except runner.NativeResearchError:
        _fail('patch_manifest_changed')
    if (runner._file_modes(root / 'original', original) != original_modes
            or runner._file_modes(area / 'patched', patched) != patched_modes):
        _fail('patch_manifest_changed')
    with tempfile.TemporaryDirectory(prefix='patch-recheck-') as temporary:
        replay = Path(temporary) / 'patched'
        shutil.copytree(root / 'original', replay)
        _apply(replay, data)
        if (runner._inventory(replay) != patched
                or runner._file_modes(replay, patched) != patched_modes):
            _fail('patch_diff_does_not_explain_bytes')
    return {'request': request, 'original_manifest': original,
            'patched_manifest': patched, 'original_modes': original_modes,
            'patched_modes': patched_modes, 'area': area}


def review_input(root: Path, request: dict, original_input: Path,
                 input_manifest: dict) -> tuple[Path, dict, dict]:
    plan = runner._plan(root)
    module = runner._load_review_module(root)
    pair = verify_patch(root, request, plan, module)
    if runner._inventory(original_input) != input_manifest:
        _fail('patch_review_input_changed')
    runner._verify_source_original(pair['original_manifest'], input_manifest)
    if runner._file_modes(original_input, pair['original_manifest']) != pair['original_modes']:
        _fail('patch_review_input_mode_changed')
    scripts = {name: digest for name, digest in input_manifest.items()
               if name not in pair['original_manifest']}
    if not scripts or set(scripts) & set(pair['patched_manifest']):
        _fail('patch_review_script_collision')
    destination = pair['area'] / 'review-input-patched'
    if destination.exists() or destination.is_symlink():
        _fail('patch_review_input_already_exists')
    shutil.copytree(pair['area'] / 'patched', destination)
    for name in scripts:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original_input / name, target)
    inventory = runner._inventory(destination)
    if (any(inventory.get(name) != digest for name, digest in scripts.items())
            or any(inventory.get(name) != digest
                   for name, digest in pair['patched_manifest'].items())):
        _fail('patch_review_input_changed')
    return destination, inventory, scripts


def verify_review_evidence(root: Path, role: str, receipt: dict) -> dict:
    """Read back every protected paired execution without running one again."""
    if role not in ('reviewer-1', 'reviewer-2') or not isinstance(receipt, dict):
        _fail('patch_review_role_invalid')
    plan = runner._plan(root)
    module = runner._load_review_module(root)
    path = root / 'controls/source-evidence' / role / 'RESULTS.json'
    if (receipt.get('evidence_path') != str(path)
            or receipt.get('evidence_sha256') != runner._sha(runner._file(path))):
        _fail('patch_review_evidence_changed')
    evidence = json.loads(path.read_bytes())
    if not isinstance(evidence, dict):
        _fail('patch_review_evidence_invalid')
    patch = evidence.get('patch')
    if not isinstance(patch, dict) or not isinstance(evidence.get('cases'), dict):
        _fail('patch_review_evidence_invalid')
    request = patch.get('request')
    if not isinstance(request, dict):
        _fail('patch_review_evidence_invalid')
    pair = verify_patch(root, request, plan, module)
    request_sha = runner._sha(pair['area'] / 'request.json')
    scripts = patch.get('reviewer_scripts')
    if (receipt.get('paired_patch_request_sha256') != request_sha
            or patch.get('request_sha256') != request_sha
            or not isinstance(scripts, dict) or not scripts):
        _fail('patch_review_evidence_invalid')
    if request.get('approval_sha256') != runner._sha(root / 'controls/approval.json'):
        _fail('patch_approval_changed')
    originals = runner._inventory(root / 'controls' / ('source-review-' + role) / 'input')
    patched = runner._inventory(pair['area'] / 'review-input-patched')
    input_modes = patch.get('input_modes')
    if (not isinstance(input_modes, dict) or set(input_modes) != {'original', 'patched'}
            or input_modes['original'] != runner._file_modes(
                root / 'controls' / ('source-review-' + role) / 'input', originals)
            or input_modes['patched'] != runner._file_modes(
                pair['area'] / 'review-input-patched', patched)
            or any(input_modes['original'].get(name) != mode
                   for name, mode in pair['original_modes'].items())
            or any(input_modes['patched'].get(name) != mode
                   for name, mode in pair['patched_modes'].items())
            or any(input_modes['original'].get(name) != input_modes['patched'].get(name)
                   for name in scripts)):
        _fail('patch_review_input_mode_changed')
    if (any(originals.get(name) != digest or patched.get(name) != digest
            for name, digest in scripts.items())
            or any(originals.get(name) != digest for name, digest in pair['original_manifest'].items())
            or any(patched.get(name) != digest for name, digest in pair['patched_manifest'].items())
            or patch.get('patched_input_manifest') != patched):
        _fail('patch_review_input_changed')
    check = evidence.get('check')
    runner._validate_source_check(check, receipt['input_id'], paired=True)
    review_area = root / 'controls' / ('source-review-' + role)
    if (evidence.get('check_sha256') != runner._sha(review_area / 'source-check.json')
            or runner._read_json(review_area / 'source-check.json') != check
            or evidence.get('input_manifest_sha256') != runner._sha(review_area / 'input-manifest.json')
            or runner._read_json(review_area / 'input-manifest.json') != originals
            or set(evidence.get('cases', {})) != {'original', 'patched'}):
        _fail('patch_review_check_changed')
    ids = set()
    for variant, source in (('original', originals), ('patched', patched)):
        if set(evidence['cases'][variant]) != {'effect', 'control', 'normal', 'connected'}:
            _fail('patch_review_case_missing')
        for name, case in evidence['cases'][variant].items():
            saved = case.get('receipt')
            identity = saved.get('execution_id') if isinstance(saved, dict) else None
            if (not isinstance(identity, str) or not re.fullmatch(r'[0-9a-f]{32}', identity)
                    or identity in ids):
                _fail('patch_review_execution_invalid')
            ids.add(identity)
            execution = root / 'controls/source-executions' / identity
            receipt_path = execution / 'receipt.json'
            observed = runner._read_json(receipt_path)
            if (runner._sha(receipt_path) != case.get('receipt_sha256')
                    or observed != saved or observed.get('status') != 'captured'
                    or observed.get('owner_role') != role
                    or observed.get('source_variant') != variant
                    or observed.get('paired_patch_request_sha256') != request_sha
                    or observed.get('command') != check[name]
                    or observed.get('plan_sha256') != runner._sha(root / 'plan.json')
                    or observed.get('input_manifest_sha256') != runner._sha(execution / 'input-manifest.json')
                    or runner._read_json(execution / 'input-manifest.json') != source
                    or runner._inventory(execution / 'input') != source
                    or runner._file_modes(execution / 'input', source) != input_modes[variant]
                    or [row.get('role') for row in observed.get('runs', [])] != list(runner.CAPTURE_TARGETS)):
                _fail('patch_review_execution_changed')
            for row in observed['runs']:
                folder = execution / row['role']
                output = runner._read_json(folder / 'files.json')
                summarized = case.get('outputs', {}).get(row['role'])
                output_modes = runner._file_modes(folder / 'files', output)
                actual_summary = runner._source_output_summary(
                    source, output, input_modes[variant], output_modes)
                checked_modes = pair['original_modes'] if variant == 'original' else pair['patched_modes']
                if (not isinstance(summarized, dict)
                        or row.get('output_manifest_sha256') != runner._sha(folder / 'files.json')
                        or runner._inventory(folder / 'files') != output
                        or any(output.get(file) != digest for file, digest in scripts.items())
                        or any(output.get(file) != digest for file, digest in
                               (pair['original_manifest'] if variant == 'original' else
                                pair['patched_manifest']).items())
                        or any(output_modes.get(file) != mode
                               for file, mode in checked_modes.items())
                        or any(summarized.get(key) != value
                               for key, value in actual_summary.items())
                        or summarized.get('manifest_sha256') != row['output_manifest_sha256']):
                    _fail('patch_review_output_changed')
                manifest_name = summarized.get('manifest_path', '').removeprefix('/source-evidence/')
                published = root / 'controls/source-evidence' / role / manifest_name
                if (not manifest_name.startswith('manifest-')
                        or '/' in manifest_name
                        or runner._sha(runner._file(published)) != row['output_manifest_sha256']):
                    _fail('patch_review_output_changed')
                for stream in ('stdout', 'stderr'):
                    file = folder / (stream + '.txt')
                    if (row.get(stream + '_redacted') or runner._sha(file) != row.get(stream + '_sha256')
                            or file.read_text() != summarized.get(stream)):
                        _fail('patch_review_output_changed')
    def signature(variant: str, name: str):
        return [(row['exit_code'], row['stdout_sha256'], row['stderr_sha256'])
                for row in evidence['cases'][variant][name]['receipt']['runs']]
    def deltas(variant: str, name: str):
        outputs = evidence['cases'][variant][name]['outputs']
        return [{key: outputs[role][key] for key in
                 ('changed_files', 'missing_files', 'changed_modes')}
                for role in runner.CAPTURE_TARGETS]
    stable = all(evidence['cases'][variant][name]['receipt'].get('replay_output_equal') is True
                 and len(set(signature(variant, name))) == 1
                 and all(item == deltas(variant, name)[0]
                         for item in deltas(variant, name)[1:])
                 for variant in ('original', 'patched')
                 for name in ('effect', 'control', 'normal', 'connected'))
    preserved = all(signature('original', name) == signature('patched', name)
                    and all(row[0] == 0 for row in signature('original', name))
                    and deltas('original', name) == deltas('patched', name)
                    for name in ('normal', 'connected'))
    control_held = (signature('original', 'control') == signature('patched', 'control')
                    and deltas('original', 'control') == deltas('patched', 'control'))
    effect_changed = (signature('original', 'effect') != signature('patched', 'effect')
                      or deltas('original', 'effect') != deltas('patched', 'effect'))
    if evidence.get('paired_observation') != {
            'status': 'differential_with_normal_paths_preserved' if
                stable and preserved and control_held and effect_changed else 'unproven',
            'replays_stable': stable, 'normal_and_connected_preserved': preserved,
            'control_held': control_held, 'effect_changed': effect_changed}:
        _fail('patch_review_observation_changed')
    material = receipt.get('material')
    outcome = material.get('outcome') if isinstance(material, dict) else None
    link = outcome.get('checked_link') if isinstance(outcome, dict) else None
    assessment = receipt.get('assessment')
    if (not isinstance(link, str)
            or 'source-evidence-sha256:' + receipt['evidence_sha256'] not in link
            or not isinstance(assessment, dict) or assessment.get('outcome') != outcome):
        _fail('patch_review_fix_link_changed')
    candidate = (stable and preserved and control_held and effect_changed
                 and outcome.get('decision') in ('raise', 'retain')
                 and 'patch-diff-sha256:' + request['diff_sha256'] in link)
    if receipt.get('patch_assessment') != ('checked_fix_candidate' if candidate else 'unproven'):
        _fail('patch_review_assessment_changed')
    return evidence
