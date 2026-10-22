#!/usr/bin/env python3
"""Provider-free CLI acceptance smoke; all evidence here is synthetic."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile


CHECKER = Path(__file__).with_name('check_native_acceptance_inventory.py')
REQUIRED = ('case_preflight', 'host_trace', 'pause_resume', 'clean_replay_and_controls',
            'native_review', 'workspace_diff', 'cost_and_help', 'final_output', 'cleanup')


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + '\n' if isinstance(value, dict) else value)
    path.chmod(0o600)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def invoke(run, observer):
    proc = subprocess.run([sys.executable, str(CHECKER), '--run-root', str(run),
                           '--observer-root', str(observer), '--manifest', str(observer / 'manifest.json')],
                          capture_output=True, text=True, check=False)
    return proc.returncode, json.loads(proc.stdout)


def main():
    with tempfile.TemporaryDirectory(prefix='native-acceptance-synthetic-') as tmp:
        parent = Path(tmp)
        run, observer = parent / 'run', parent / 'observer'
        run.mkdir(mode=0o700)
        observer.mkdir(mode=0o700)
        (run / 'controls').mkdir(mode=0o700)
        source = {'app.txt': put(run / 'original/app.txt', 'ordinary source\n')}
        brief_sha = put(run / 'controls/BRIEF.md', 'ordinary unhinted brief\n')
        put(run / 'researcher/brief/BRIEF.md', 'ordinary unhinted brief\n')
        source_sha = hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()
        plan = {'kind': 'native-research-plan-v1', 'source_sha256': source,
                'source_manifest_sha256': source_sha, 'brief_sha256': brief_sha,
                'limits': {'max_connections': 8, 'max_bytes': 8192, 'duration_seconds': 120}}
        plan_sha = put(run / 'plan.json', plan)
        loaded_sha = put(run / 'controls/loaded-surface.json', {'model': 'synthetic', 'tools': []})
        put(run / 'controls/activation.json', {'kind': 'native-research-activation-v1',
                                               'plan_sha256': plan_sha,
                                               'loaded_surface_sha256': loaded_sha})
        identity = {'manifest_sha256': 'a' * 64, 'nonce': 'synthetic'}
        counters = ((0, 0), (1, 20), (1, 20), (2, 40))
        for index, (role, session) in enumerate((('researcher', 'ses_Research1'),
                                                  ('resume', 'ses_Research1'),
                                                  ('reviewer-1', 'ses_Review1'))):
            ident = f'dispatch{index}'
            trace = {'kind': 'protected-native-event-trace-v1', 'session_id': session,
                     'events': [{'type': 'tool'}]}
            trace_sha = put(run / f'controls/dispatch/{ident}.trace.json', trace)
            before, after = counters[index], counters[index + 1]
            pool = lambda pair: {'run_identity': identity, 'hard_limits': plan['limits'],
                                 'used_tunnels': pair[0], 'charged_tunnel_bytes': pair[1]}
            put(run / f'controls/dispatch/{ident}.json', {
                'kind': 'native-dispatch-v1', 'dispatch_id': ident, 'role': role,
                'status': 'acknowledged', 'session_id': session, 'native_trace_sha256': trace_sha,
                'pool_before': pool(before), 'pool_after': pool(after),
                'created_at': f'2026-10-22T00:00:0{index}Z'})
        put(run / 'controls/review-reviewer-1.json', {
            'status': 'native_turn_observed_unassessed', 'input_id': 'i' * 64,
            'session_id': 'ses_Review1', 'reviewer_role': 'reviewer-1',
            'same_original_allowance': True,
            'native': {'dispatch_id': 'dispatch2', 'role': 'reviewer-1', 'session_id': 'ses_Review1'},
            'assessment': {'status': 'candidate_for_operator_review', 'input_id': 'i' * 64,
                           'session_id': 'ses_Review1', 'effect_sha256': 'e' * 64,
                           'control_sha256': 'c' * 64,
                           'independent_check': {'status': 'observed',
                                                 'observer_origin': 'host_protected'}}})
        put(run / 'controls/final.json', {'status': 'stopped_complete',
                                          'cleanup': {'status': 'complete'}})
        artifacts = {name: {'path': name + '.json',
                            'sha256': put(observer / (name + '.json'), {'synthetic': name})}
                     for name in REQUIRED}
        manifest = {'schema_version': 1, 'scenario': 'T04', 'plan_sha256': plan_sha,
                    'source_manifest_sha256': source_sha, 'artifacts': artifacts}
        put(observer / 'manifest.json', manifest)

        code, report = invoke(run, observer)
        assert code == 0 and report['status'] == 'inventory_complete_for_operator_review', report
        assert report['native_qualification'] == 'not_assessed', report

        (run / 'researcher/brief/BRIEF.md').write_text('changed visible brief\n')
        code, report = invoke(run, observer)
        assert code == 2 and 'visible_brief_pinned' in report['failed_checks'], report
        put(run / 'researcher/brief/BRIEF.md', 'ordinary unhinted brief\n')

        (run / 'controls/loaded-surface.json').write_text('{"changed":true}\n')
        code, report = invoke(run, observer)
        assert code == 2 and 'loaded_surface_pinned' in report['failed_checks'], report
        put(run / 'controls/loaded-surface.json', {'model': 'synthetic', 'tools': []})

        (observer / 'host_trace.json').write_text('{"changed":true}\n')
        code, report = invoke(run, observer)
        assert code == 2 and 'observer_artifacts_pinned' in report['failed_checks'], report
        put(observer / 'host_trace.json', {'synthetic': 'host_trace'})

        (observer / 'clean_replay_and_controls.json').unlink()
        code, report = invoke(run, observer)
        assert code == 2 and 'observer_artifacts_pinned' in report['failed_checks'], report
        put(observer / 'clean_replay_and_controls.json', {'synthetic': 'clean_replay_and_controls'})

        resume = run / 'controls/dispatch/dispatch1.json'
        value = json.loads(resume.read_text())
        value['session_id'] = 'ses_Different1'
        put(resume, value)
        code, report = invoke(run, observer)
        assert code == 2 and 'research_resume_same_session' in report['failed_checks'], report
        value['session_id'] = 'ses_Research1'
        put(resume, value)

        review = run / 'controls/review-reviewer-1.json'
        value = json.loads(review.read_text())
        value['assessment']['status'] = 'unfinished'
        put(review, value)
        code, report = invoke(run, observer)
        assert code == 2 and 'fresh_review_candidate' in report['failed_checks'], report

        value['assessment']['status'] = 'candidate_for_operator_review'
        put(review, value)
        challenge_names = ('challenge_input', 'host_trace', 'contrary_and_controls',
                           'native_review', 'updated_claim_and_output', 'cost_and_cleanup')
        challenge_artifacts = {name: {'path': name + '-f01.json',
                                      'sha256': put(observer / (name + '-f01.json'),
                                                    {'synthetic': name})}
                               for name in challenge_names}
        manifest['scenario'] = 'F01'
        manifest['artifacts'] = challenge_artifacts
        put(observer / 'manifest.json', manifest)
        code, report = invoke(run, observer)
        assert code == 0 and report['status'] == 'inventory_complete_for_operator_review', report
        manifest['scenario'] = 'F99'
        put(observer / 'manifest.json', manifest)
        code, report = invoke(run, observer)
        assert code == 2 and 'observer_manifest' in report['failed_checks'], report

    print('PASS: synthetic T04/F01 inventory rejects stale or missing artifacts, changed surface/brief/session, unassessed review and unknown challenge; provider_calls=0 target_calls=0')


if __name__ == '__main__':
    main()
