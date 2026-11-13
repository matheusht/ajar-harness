#!/usr/bin/env python3
"""Contained end-to-end phase-driver scenario with simulated phase commands.

This executes the public driver state machine from one initial input manifest.
The native model, Docker build, reviewer and owner are simulated; it proves
ordering and crash recovery of the driver, not native or target qualification.
"""

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
import native_engagement as driver  # noqa: E402


def write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + '\n')


class Phases:
    def __init__(self, root: Path, scope: dict, *, stop_at: str | None = None):
        self.root = root
        self.scope = scope
        self.stop_at = stop_at
        self.statuses = {'setup': 'prepared', 'research': 'prepared'}
        self.calls = []
        self.dispatches = []
        self.builds = 0
        self.reconciles = 0
        self.crashed = False
        self.resumes = 0
        self.prepare_checked_durations = []

    def owner(self, _root, _script, run_root, _inputs):
        phase = run_root.name
        self.calls.append(phase + ':start')
        self.statuses[phase] = 'active'
        return 81234

    def __call__(self, script, *args, timeout):
        name = script.name
        action = args[0]
        self.calls.append(name + ':' + action)
        setup = self.root / 'setup'
        research = self.root / 'research'
        if name == 'native_research.py' and action == 'prepare':
            write(setup / 'plan.json', {'kind': 'native-research-plan-v1',
                                       'autonomous_engagement': {'kind': 'scope-only'}})
            return 0, {'status': 'prepared_provider_free'}
        if name == 'native_research.py' and action == 'status':
            phase = Path(args[args.index('--run-root') + 1]).name
            absent = self.stop_at != 'cleanup_missing'
            return 0, {'status': self.statuses[phase],
                       'dispatches': sorted(self.dispatches,
                                            key=lambda row: row['dispatch_id']),
                       'final': ({'status': 'stopped_complete',
                                  'native_stop': {'status': 'stopped'},
                                  'cleanup': {'status': 'complete',
                                              'resources': [{'absent': absent}]}}
                                 if self.statuses[phase] == 'stopped_complete' else None),
                       'setup': {'frozen_proposal_receipt_sha256':
                                 'a' * 64 if (setup / 'controls/setup-output/receipt.json').exists()
                                 else None,
                                 'last_dispatch_id': (self.dispatches[-1]['dispatch_id']
                                                      if self.dispatches else None)}}
        if name == 'native_research.py' and action == 'setup-turn':
            if self.stop_at == 'setup_unknown':
                self.dispatches.append({'dispatch_id': 'f' * 32,
                                        'role': 'researcher', 'status': 'unknown_effect',
                                        'session_id': 'ses_synthetic'})
                return 2, {'status': 'unknown_effect', 'code': 'native_turn_exit_unknown_effect'}
            self.dispatches.append({'dispatch_id': 'f' * 32,
                                    'role': 'researcher', 'status': 'acknowledged',
                                    'session_id': 'ses_synthetic'})
            if self.stop_at in ('scope_drift', 'inputs_drift') and not self.crashed:
                self.crashed = True
                raise KeyboardInterrupt('synthetic driver loss with active owner')
            return 0, {'status': 'acknowledged', 'session_id': 'ses_synthetic'}
        if name == 'native_research.py' and action == 'setup-resume':
            self.resumes += 1
            if self.stop_at == 'resume_unknown':
                self.dispatches.append({'dispatch_id': '0' * 32,
                                        'role': 'resume', 'status': 'unknown_effect',
                                        'session_id': 'ses_synthetic'})
                return 2, {'status': 'unknown_effect', 'code': 'native_turn_exit_unknown_effect'}
            self.dispatches.append({'dispatch_id': '0' * 32,
                                    'role': 'resume', 'status': 'acknowledged',
                                    'session_id': 'ses_synthetic'})
            if self.stop_at == 'resume_crash_uuid_order' and not self.crashed:
                self.crashed = True
                raise KeyboardInterrupt('synthetic crash after acknowledged setup resume')
            return 0, {'status': 'acknowledged', 'session_id': 'ses_synthetic'}
        if name == 'native_research.py' and action == 'setup-freeze':
            if self.stop_at in ('freeze_invalid', 'resume_unknown') or (
                    self.stop_at in ('freeze_revision', 'resume_crash_uuid_order')
                    and self.resumes == 0):
                return 2, {'status': 'rejected', 'code': 'setup_output_missing_changed_or_oversize'}
            write(setup / 'controls/setup-output/receipt.json',
                  {'kind': 'native-setup-output-v1'})
            return 0, {'status': 'frozen_proposal'}
        if name == 'native_research.py' and action == 'stop':
            phase = Path(args[args.index('--run-root') + 1]).name
            self.statuses[phase] = 'stopped_complete'
            return 0, {'status': 'stop_requested'}
        if name == 'native_setup_builder.py' and action == 'setup-build':
            self.builds += 1
            if self.stop_at in ('build_unknown', 'build_cleanup_unresolved'):
                return 2, {'status': 'unknown_effect', 'code': 'build_action_unknown_effect'}
            checked = self.receipt()
            write(setup / 'controls/setup-checked/receipt.json', checked)
            if self.stop_at == 'build_crash' and not self.crashed:
                self.crashed = True
                raise KeyboardInterrupt('synthetic driver loss after committed build')
            return 0, {'status': 'ready'}
        if name == 'native_setup_builder.py' and action == 'setup-build-status':
            if '--verify-checked' in args:
                return 0, {'receipt': self.receipt()}
            if self.stop_at == 'build_cleanup_unresolved':
                return ((2, {'status': 'cleanup_unresolved'}) if self.reconciles < 3
                        else (0, {'status': 'blocked_reconciled'}))
            if self.stop_at == 'build_unknown' and self.reconciles:
                return 0, {'status': 'blocked_reconciled'}
            return (2, {'status': 'unknown_effect'}) if self.stop_at == 'build_unknown' \
                else (0, {'status': 'ready'})
        if name == 'native_setup_builder.py' and action == 'setup-build-reconcile':
            self.reconciles += 1
            if self.stop_at == 'build_cleanup_unresolved' and self.reconciles < 3:
                return 2, {'status': 'cleanup_unresolved',
                           'cleanup': {'status': 'unresolved', 'absent': False}}
            if self.stop_at == 'build_cleanup_unresolved':
                return 0, {'status': 'blocked_reconciled',
                           'cleanup': {'status': 'complete', 'absent': True}}
            return 0, {'status': 'blocked_reconciled',
                       'cleanup': {'status': 'complete', 'absent': True}}
        if name == 'native_research.py' and action == 'prepare-checked':
            duration = int(args[args.index('--duration-seconds') + 1])
            self.prepare_checked_durations.append(duration)
            if self.stop_at == 'prepare_allowance_drift':
                if (len(self.prepare_checked_durations) == 1 or
                        duration > self.prepare_checked_durations[0] - 20):
                    return 2, {'status': 'rejected',
                               'code': 'engagement_research_allowance_mismatch'}
            if self.stop_at == 'prepare_partial_plan':
                write(research / 'plan.json', {'kind': 'partial-research-plan'})
                return 2, {'status': 'rejected',
                           'code': 'engagement_research_allowance_mismatch'}
            write(research / 'plan.json', {'autonomous_engagement': {'kind': 'scope-only'},
                                           'checked_setup': {'kind': 'checked'},
                                           'scope_sha256': driver._sha(Path(self.inputs['scope_file']))})
            return 0, {'status': 'prepared_provider_free'}
        if name == 'native_research.py' and action == 'continue':
            self.statuses['research'] = 'stopped_complete'
            final_status = ('stopped_incomplete' if self.stop_at == 'research_incomplete'
                            else 'complete_internal_candidate')
            write(research / 'controls/closeout/result.json',
                  {'kind': 'native-agent-closeout-v1',
                   'status': final_status,
                   'cleanup': {'resource_absence': True}})
            return (2 if final_status == 'stopped_incomplete' else 0), {
                'status': final_status}
        if name == 'native_closeout.py':
            self.statuses['research'] = 'stopped_complete'
            path = research / 'controls/closeout/result.json'
            if path.exists():
                return 0, {'status': json.loads(path.read_text())['status'],
                           'record_sha256': driver._sha(path)}
            return 0, {'status': 'stopped_incomplete'}
        raise AssertionError((name, args))

    def receipt(self):
        used = {'connections': 1, 'bytes': 100}
        total = self.scope['limits']
        return {'kind': 'native-setup-checked-v1', 'status': 'ready',
                'autonomous_engagement_scope_sha256': driver._sha(Path(self.inputs['scope_file'])),
                'cumulative_setup_used': used,
                'remaining_engagement_allowance': {
                    'connections': total['max_connections'] - used['connections'],
                    'bytes': total['max_bytes'] - used['bytes'],
                    'absolute_deadline': driver._deadline(self.scope).strftime('%Y-%m-%dT%H:%M:%SZ')}}


def scenario(base: Path, name: str) -> dict:
    base.mkdir(mode=0o700)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    scope = {'kind': 'native-engagement-scope-v1',
             'engagement_id': 'synthetic', 'operator_id': 'synthetic',
             'issued_at': now.strftime('%Y-%m-%dT%H:%M:%SZ'),
             'expires_at': (now + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%SZ'),
             'limits': {'max_connections': 10, 'max_bytes': 1048576,
                        'duration_seconds': 3600},
             'setup': {'limits': {'max_connections': 2, 'max_bytes': 65536,
                                 'duration_seconds': 120},
                       'max_workspace_bytes': 8388608},
             'image_id': 'sha256:' + '1' * 64, 'platform': 'linux/amd64',
             'model': 'opencode/deepseek-v4.1-flash-free',
             'provider_route': 'opencode-keyless-free'}
    scope_path = base / 'scope.md'
    scope_path.write_text('```native-engagement-scope-v1\n' +
                          json.dumps(scope, sort_keys=True) + '\n```\n')
    files = {}
    for key in ('source', 'brief', 'scope_signature', 'allowed_signers',
                'relay', 'runtime_ca', 'dependency_catalog'):
        path = base / key
        if key == 'source' or key == 'dependency_catalog':
            path.mkdir()
        else:
            path.write_text('synthetic')
        files[key] = str(path)
    inputs = {'kind': 'native-engagement-inputs-v1', **files,
              'scope_file': str(scope_path),
              'trusted_fingerprint': 'sha256:' + '2' * 64}
    inputs_path = base / 'inputs.json'
    write(inputs_path, inputs)
    root = base / 'run'
    driver._initialize(root, inputs_path)
    fake = Phases(root, scope, stop_at=name if name != 'success' else None)
    fake.inputs = inputs
    if name in ('build_crash', 'resume_crash_uuid_order'):
        try:
            driver.drive(root, command=fake, spawn_owner=fake.owner)
        except KeyboardInterrupt:
            pass
        else:
            raise AssertionError('synthetic crash not reached')
        assert driver._state(root)['pending']['action'] == (
            'setup_build' if name == 'build_crash' else 'setup_resume')
        result = driver.drive(root, command=fake, spawn_owner=fake.owner)
        assert fake.builds == 1, fake.calls
        assert result['status'] == 'complete_internal_candidate', result
    elif name == 'build_cleanup_unresolved':
        first = driver.drive(root, command=fake, spawn_owner=fake.owner)
        assert first['status'] == 'cleanup_unverified', first
        assert fake.builds == 1 and fake.reconciles == 2, fake.calls
        result = driver.drive(root, command=fake, spawn_owner=fake.owner)
        assert result['status'] == 'stopped_incomplete', result
        assert fake.builds == 1 and fake.reconciles == 3, fake.calls
    elif name in ('scope_drift', 'inputs_drift'):
        try:
            driver.drive(root, command=fake, spawn_owner=fake.owner)
        except KeyboardInterrupt:
            pass
        else:
            raise AssertionError('synthetic crash not reached')
        if name == 'scope_drift':
            scope_path.write_text(scope_path.read_text() + '\nchanged\n')
            result = driver.drive(root, command=fake, spawn_owner=fake.owner)
            assert result['reason'] == 'engagement_scope_changed', result
        else:
            (root / 'inputs.json').write_text((root / 'inputs.json').read_text() + ' ')
            try:
                driver.drive(root, command=fake, spawn_owner=fake.owner)
            except driver.DriverError as error:
                assert str(error) == 'engagement_state_or_inputs_changed'
            else:
                raise AssertionError('changed inputs were accepted')
            result = {'status': 'rejected'}
        assert fake.statuses['setup'] == 'stopped_complete'
    else:
        result = driver.drive(root, command=fake, spawn_owner=fake.owner)
    if name == 'success':
        assert result['status'] == 'complete_internal_candidate', result
        assert fake.builds == 1
        assert fake.calls.index('native_research.py:setup-freeze') < \
            fake.calls.index('native_setup_builder.py:setup-build') < \
            fake.calls.index('native_research.py:prepare-checked')
    elif name == 'build_unknown':
        assert result['status'] == 'stopped_incomplete', result
        assert fake.builds == 1 and fake.reconciles == 2
        assert 'native_research.py:prepare-checked' not in fake.calls
    elif name == 'build_cleanup_unresolved':
        assert result['status'] == 'stopped_incomplete'
        assert 'native_research.py:prepare-checked' not in fake.calls
    elif name in ('setup_unknown', 'freeze_invalid'):
        assert result['status'] == 'stopped_incomplete', result
        assert fake.builds == 0
        assert 'native_research.py:prepare-checked' not in fake.calls
    elif name == 'resume_unknown':
        assert result['status'] == 'stopped_incomplete', result
        assert fake.resumes == 1 and fake.builds == 0
    elif name == 'freeze_revision':
        assert result['status'] == 'complete_internal_candidate', result
        assert fake.resumes == 1 and fake.builds == 1
    elif name == 'resume_crash_uuid_order':
        assert result['status'] == 'complete_internal_candidate', result
        assert fake.resumes == 1 and fake.builds == 1
    elif name == 'prepare_allowance_drift':
        assert result['status'] == 'complete_internal_candidate', result
        assert len(fake.prepare_checked_durations) == 2
        assert fake.prepare_checked_durations[1] <= fake.prepare_checked_durations[0] - 20
    elif name == 'prepare_partial_plan':
        assert result['status'] == 'stopped_incomplete', result
        assert len(fake.prepare_checked_durations) == 1
        assert fake.statuses['research'] == 'prepared'
    elif name == 'research_incomplete':
        assert result['status'] == 'stopped_incomplete', result
        assert driver._state(root)['phase'] == 'incomplete'
    elif name == 'scope_drift':
        assert result['status'] == 'stopped_incomplete', result
        assert fake.builds == 0
    elif name == 'inputs_drift':
        assert result['status'] == 'rejected', result
        assert fake.builds == 0
    elif name == 'cleanup_missing':
        assert result['status'] == 'cleanup_unverified', result
        assert fake.builds == 0
    return {'status': result['status'], 'phase': (driver._state(root)['phase']
            if name != 'inputs_drift' else 'emergency_hold'),
            'build_dispatches': fake.builds, 'build_reconciles': fake.reconciles,
            'calls': fake.calls}


def main() -> int:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.output.is_absolute():
        parser.error('--output must be absolute')
    with tempfile.TemporaryDirectory(prefix='native-phase-driver-e2e-') as temporary:
        base = Path(temporary)
        checks = {name: scenario(base / name, name) for name in
                  ('success', 'setup_unknown', 'freeze_invalid', 'build_unknown',
                   'build_crash', 'build_cleanup_unresolved', 'scope_drift',
                   'inputs_drift', 'cleanup_missing', 'freeze_revision',
                   'resume_crash_uuid_order', 'resume_unknown', 'research_incomplete',
                   'prepare_allowance_drift', 'prepare_partial_plan')}
    report = {'status': 'passed', 'kind': 'native-scope-only-phase-driver-e2e-v1',
              'command': ('PYTHONDONTWRITEBYTECODE=1 python3 '
                          'evals/native-qualification/smoke/check_scope_only_phase_driver_e2e.py '
                          '--output "$PWD/evals/native-qualification/setup-evidence/'
                          'scope-only-phase-driver-synthetic-e2e.json"'),
              'requirements': 'Python 3; no Docker, provider, or target service required',
              'inputs': 'generated disposable source, scope, manifest, and simulated phase receipts',
              'expected': 'status passed; no unknown effect retried; stopped outcomes retain cleanup state',
              'provider_calls': 0, 'docker_calls': 0, 'target_calls': 0,
              'human_phase_signatures': 0, 'checks': checks,
              'limitation': 'phase commands and owner are simulated; no authority or live effect qualified'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'status': 'passed', 'output': str(args.output),
                      'cases': list(checks)}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
