#!/usr/bin/env python3
"""Inventory native #160/#162 evidence without running a provider or target."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat


SHA = re.compile(r'[0-9a-f]{64}\Z')
T06 = {'F01', 'F02', 'F03', 'F04', 'F05', 'F06', 'F07',
       'F08a', 'F08b', 'F08c', 'F08d', 'L01', 'L02', 'L03'}
ARTIFACTS = {
    'T04': {'case_preflight', 'host_trace', 'pause_resume', 'clean_replay_and_controls',
            'native_review', 'workspace_diff', 'cost_and_help', 'final_output', 'cleanup'},
    'T06': {'challenge_input', 'host_trace', 'contrary_and_controls', 'native_review',
            'updated_claim_and_output', 'cost_and_cleanup'},
}


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def private_dir(path):
    try:
        mode = path.stat(follow_symlinks=False)
        return (path.is_absolute() and not path.is_symlink()
                and stat.S_ISDIR(mode.st_mode) and mode.st_uid == os.getuid()
                and not mode.st_mode & 0o077)
    except OSError:
        return False


def regular(path, *, private=True):
    try:
        mode = path.stat(follow_symlinks=False)
        return (not path.is_symlink() and stat.S_ISREG(mode.st_mode)
                and (not private or mode.st_uid == os.getuid() and not mode.st_mode & 0o077))
    except OSError:
        return False


def read_json(path):
    try:
        if not regular(path) or path.stat().st_size > 4 * 1024 * 1024:
            return None
        value = json.loads(path.read_bytes(), object_pairs_hook=unique_pairs)
    except (OSError, UnicodeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def unique_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('duplicate JSON key')
        value[key] = item
    return value


def relative_file(root, name, *, private=True):
    if (not isinstance(name, str) or not name or name.startswith('/')
            or '\\' in name or any(part in ('', '.', '..') for part in name.split('/'))):
        return None
    path = root
    for part in name.split('/'):
        path = path / part
        if path.is_symlink():
            return None
    return path if regular(path, private=private) else None


def source_matches(root, plan):
    expected = plan.get('source_sha256')
    if (not isinstance(expected, dict) or not expected
            or (root / 'original').is_symlink() or not (root / 'original').is_dir()):
        return False
    if (not all(isinstance(name, str) and isinstance(digest, str) and SHA.fullmatch(digest)
                and relative_file(root / 'original', name, private=False) is not None
                for name, digest in expected.items())):
        return False
    if any(sha(root / 'original' / name) != digest for name, digest in expected.items()):
        return False
    observed = set()
    for path in (root / 'original').rglob('*'):
        if path.is_symlink():
            return False
        if not path.is_dir() and not path.is_file():
            return False
        if path.is_file():
            observed.add(path.relative_to(root / 'original').as_posix())
    return observed == set(expected)


def dispatches(root, plan):
    folder = root / 'controls/dispatch'
    if not folder.is_dir() or folder.is_symlink():
        return [], False, False
    paths = sorted(path for path in folder.glob('*.json') if not path.name.endswith('.trace.json'))
    records = []
    traces_ok = bool(paths)
    allowance_ok = bool(paths)
    identity = None
    last = (0, 0)
    for path in paths:
        record = read_json(path)
        if record is None:
            traces_ok = allowance_ok = False
            continue
        records.append(record)
        trace = path.with_name(path.stem + '.trace.json')
        native = read_json(trace)
        traces_ok &= (record.get('kind') == 'native-dispatch-v1'
                      and record.get('dispatch_id') == path.stem
                      and record.get('status') == 'acknowledged'
                      and isinstance(record.get('session_id'), str)
                      and native is not None
                      and native.get('kind') == 'protected-native-event-trace-v1'
                      and native.get('session_id') == record.get('session_id')
                      and SHA.fullmatch(str(record.get('native_trace_sha256', ''))) is not None
                      and sha(trace) == record.get('native_trace_sha256'))
    records.sort(key=lambda row: str(row.get('created_at', '')))
    for record in records:
        before, after = record.get('pool_before'), record.get('pool_after')
        if not isinstance(before, dict) or not isinstance(after, dict):
            allowance_ok = False
            continue
        if identity is None:
            identity = before.get('run_identity')
        values = []
        for pool in (before, after):
            pair = (pool.get('used_tunnels'), pool.get('charged_tunnel_bytes'))
            if (pool.get('run_identity') != identity or not isinstance(identity, dict)
                    or pool.get('hard_limits') != plan.get('limits')
                    or not all(type(value) is int and value >= 0 for value in pair)):
                allowance_ok = False
            values.append(pair)
        if all(type(value) is int for pair in values for value in pair):
            allowance_ok &= all(a <= b <= c for a, b, c in zip(last, values[0], values[1]))
            last = values[1]
    return records, bool(traces_ok), bool(allowance_ok)


def review_matches(root, records, researcher_sessions):
    for role in ('reviewer-1', 'reviewer-2'):
        receipt = read_json(root / 'controls' / ('review-' + role + '.json'))
        if receipt is None:
            continue
        native = receipt.get('native')
        assessment = receipt.get('assessment')
        if not isinstance(native, dict) or not isinstance(assessment, dict):
            continue
        reviewer = next((record for record in records
                         if record.get('dispatch_id') == native.get('dispatch_id')
                         and record.get('role') == role
                         and record.get('session_id') == receipt.get('session_id')), None)
        checked = assessment.get('independent_check')
        if (reviewer and receipt.get('status') == 'native_turn_observed_unassessed'
                and receipt.get('same_original_allowance') is True
                and native.get('role') == role
                and native.get('session_id') == receipt.get('session_id')
                and receipt.get('session_id') not in researcher_sessions
                and assessment.get('status') == 'candidate_for_operator_review'
                and assessment.get('input_id') == receipt.get('input_id')
                and assessment.get('session_id') == receipt.get('session_id')
                and isinstance(checked, dict)
                and checked.get('status') == 'observed'
                and checked.get('observer_origin') == 'host_protected'
                and SHA.fullmatch(str(assessment.get('effect_sha256', '')))
                and SHA.fullmatch(str(assessment.get('control_sha256', '')))):
            return True
    return False


def artifact_matches(observer, manifest):
    scenario = manifest.get('scenario')
    needed = (ARTIFACTS['T04'] if scenario == 'T04' else
              ARTIFACTS['T06'] if isinstance(scenario, str) and scenario in T06 else None)
    artifacts = manifest.get('artifacts')
    if needed is None or not isinstance(artifacts, dict) or set(artifacts) != needed:
        return False
    names = []
    for row in artifacts.values():
        if not isinstance(row, dict) or set(row) != {'path', 'sha256'}:
            return False
        path = relative_file(observer, row['path'])
        if path is None or not SHA.fullmatch(str(row['sha256'])) or sha(path) != row['sha256']:
            return False
        names.append(row['path'])
    return len(set(names)) == len(names)


def audit(run, observer, manifest_path):
    checks = {}

    def check(name, condition):
        checks[name] = bool(condition)

    check('separate_private_roots', private_dir(run) and private_dir(observer)
          and not run.resolve().is_relative_to(observer.resolve())
          and not observer.resolve().is_relative_to(run.resolve()))
    check('protected_controls', private_dir(run / 'controls'))
    try:
        manifest_file = relative_file(observer, manifest_path.relative_to(observer).as_posix())
    except ValueError:
        manifest_file = None
    manifest = read_json(manifest_file) if manifest_file else None
    check('observer_manifest', manifest is not None and manifest.get('schema_version') == 1
          and isinstance(manifest.get('scenario'), str)
          and manifest.get('scenario') in {'T04', *T06})
    plan = read_json(run / 'plan.json')
    plan_hash = sha(run / 'plan.json') if plan is not None else None
    check('native_plan', plan is not None and plan.get('kind') == 'native-research-plan-v1'
          and manifest is not None and SHA.fullmatch(str(manifest.get('plan_sha256', '')))
          and plan_hash == manifest.get('plan_sha256'))
    if plan is None:
        plan = {}
    activation = read_json(run / 'controls/activation.json')
    surface_path = run / 'controls/loaded-surface.json'
    surface = read_json(surface_path)
    check('loaded_surface_pinned', activation is not None and surface is not None
          and activation.get('kind') == 'native-research-activation-v1'
          and activation.get('plan_sha256') == plan_hash
          and SHA.fullmatch(str(activation.get('loaded_surface_sha256', '')))
          and sha(surface_path) == activation.get('loaded_surface_sha256'))
    source = plan.get('source_sha256')
    source_sha = (hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()
                  if isinstance(source, dict) and all(isinstance(k, str) and isinstance(v, str)
                                                      for k, v in source.items()) else None)
    check('original_source_pinned', bool(source_sha and source_sha == plan.get('source_manifest_sha256')
          and manifest and manifest.get('source_manifest_sha256') == source_sha
          and source_matches(run, plan)))
    brief = run / 'controls/BRIEF.md'
    visible_brief = run / 'researcher/brief/BRIEF.md'
    check('visible_brief_pinned', regular(brief) and regular(visible_brief)
          and sha(brief) == plan.get('brief_sha256')
          and sha(visible_brief) == plan.get('brief_sha256'))
    records, traces_ok, allowance_ok = dispatches(run, plan)
    check('native_dispatch_traces', traces_ok)
    check('single_monotonic_allowance', allowance_ok)
    research = [row for row in records if row.get('role') == 'researcher']
    resumed = [row for row in records if row.get('role') == 'resume']
    sessions = {row.get('session_id') for row in research + resumed}
    check('research_resume_same_session', manifest is not None and (
          bool(research and resumed and len(sessions) == 1 and
               research[0].get('created_at', '') < resumed[0].get('created_at', ''))
          if manifest.get('scenario') == 'T04' else True))
    check('fresh_review_candidate', review_matches(run, records, sessions))
    final = read_json(run / 'controls/final.json')
    check('verified_stop_and_cleanup', final is not None and final.get('status') == 'stopped_complete'
          and isinstance(final.get('cleanup'), dict) and final['cleanup'].get('status') == 'complete')
    check('observer_artifacts_pinned', manifest is not None and artifact_matches(observer, manifest))
    failed = [name for name, passed in checks.items() if not passed]
    return {'status': 'inventory_complete_for_operator_review' if not failed else 'incomplete',
            'scenario': manifest.get('scenario') if manifest else None,
            'checks': checks, 'failed_checks': failed,
            'native_qualification': 'not_assessed',
            'limits': ['file hashes and CLI receipts do not prove original effect, pause state, '
                       'reviewer judgment, provider charges, redaction, or independent cleanup readback']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root', required=True, type=Path)
    parser.add_argument('--observer-root', required=True, type=Path)
    parser.add_argument('--manifest', required=True, type=Path)
    args = parser.parse_args()
    try:
        report = audit(args.run_root, args.observer_root, args.manifest)
    except (OSError, TypeError, ValueError):
        report = {'status': 'incomplete', 'checks': {},
                  'failed_checks': ['input_changed_or_invalid_during_read'],
                  'native_qualification': 'not_assessed'}
    print(json.dumps(report, sort_keys=True))
    return 0 if report['status'] == 'inventory_complete_for_operator_review' else 2


if __name__ == '__main__':
    raise SystemExit(main())
