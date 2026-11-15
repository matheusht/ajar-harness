#!/usr/bin/env python3
"""Prove a fresh Docker host refuses Codex tool setup before its profile is loaded."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint', required=True)
    parser.add_argument('--image-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = {'kind': 'codex-tool-policy-missing-profile-e2e-v1',
              'classification': 'actual_docker_without_host_profile',
              'status': 'failed', 'checks': []}

    def check(name, value):
        result['checks'].append({'name': name, 'passed': bool(value)})
        if not value:
            raise AssertionError(name)

    environment = recovered = None
    profile = limits = authorize = None
    docker = None
    try:
        sys.path.insert(0, str(ROOT / 'tools'))
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from research_environment import Environment, EnvironmentUnavailable
        import check_codex_sandbox_policy_candidate as candidate

        docker = shutil.which('docker')
        if not docker or not args.endpoint.startswith('unix:///') or not Path(args.endpoint[7:]).exists():
            raise RuntimeError('explicit_local_docker_unavailable')
        info = subprocess.run([docker, '--host', args.endpoint, 'info', '--format', '{{.ID}}'],
            check=True, capture_output=True, text=True, timeout=10)
        daemon_id = info.stdout.strip()
        if not daemon_id:
            raise RuntimeError('docker_daemon_identity_unavailable')
        inventory = candidate._read_loaded_profiles()
        absent = not candidate._profile_present(inventory, candidate.APPARMOR_PROFILE)
        check('exact named profile is absent before the refusal check', absent)
        profile = {'kind': 'research-environment-profile-v2', 'transport': 'docker',
            'docker_binary': docker, 'docker_endpoint': args.endpoint, 'daemon_id': daemon_id,
            'image_id': args.image_id, 'platform': 'linux/amd64', 'uid': 1000, 'gid': 1000,
            'ssh': None, 'codex_tool_policy': 'docker-confined-v1'}
        limits = {'memory_bytes': 256 * 1024 * 1024, 'workspace_bytes': 16 * 1024 * 1024,
            'cpu_count': 1, 'pids': 32, 'lease_seconds': 60, 'output_bytes': 4096}
        authorize = lambda: {'seconds_remaining': 60}
        events = []
        with tempfile.TemporaryDirectory(prefix='codex-policy-unloaded-') as temporary:
            source = Path(temporary) / 'source.bin'
            source.write_bytes(b'fixed benign policy preflight input\n')
            access = {'id': 'source-main', 'kind': 'binary', 'identity': {
                'sha256': 'sha256:' + hashlib.sha256(source.read_bytes()).hexdigest(),
                'platform': 'linux/amd64'}, 'account_refs': [], 'permissions': ['read', 'execute']}
            environment = Environment(profile, limits, authorize, events.append,
                dispatch_guard=lambda: __import__('contextlib').nullcontext(), codex_tool_policy=True)
            original_run = environment._run
            create_refusal_evidence = {'apparmor': False, 'profile': False}

            def observed_run(argv, *positional, **keywords):
                observation = original_run(argv, *positional, **keywords)
                if (len(argv) >= 2 and argv[:2] == ['container', 'create']
                        and observation['returncode'] != 0):
                    text = observation['output'].decode('utf-8', 'replace').lower()
                    create_refusal_evidence.update(apparmor='apparmor' in text,
                        profile=candidate.APPARMOR_PROFILE.lower() in text)
                return observation

            environment._run = observed_run
            refusal = None
            try:
                environment.prepare([access], {'source-main': str(source)})
            except Exception as error:
                refusal = error
            receipt = environment.receipt()
            unsettled_before_recovery = list(receipt['unsettled'])
            result['refusal_phase'] = ('start' if any(row.get('operation') == 'start'
                and row.get('phase') == 'intent' for row in events) else 'create_or_setup')
            if refusal is not None:
                known_codes = {'environment_start_unobserved', 'environment_configuration_mismatch',
                    'environment_worker_inactive', 'environment_create_unknown',
                    'environment_stage_unknown', 'environment_snapshot_unknown'}
                observed_code = getattr(refusal, 'code', None)
                start_message = str(refusal).lower()
                result['startup_failure'] = {'exception_type': type(refusal).__name__,
                    'environment_code': observed_code if observed_code in known_codes else None,
                    'message_mentions_apparmor': 'apparmor' in start_message,
                    'message_mentions_profile': candidate.APPARMOR_PROFILE.lower() in start_message}
            start_intended = result['refusal_phase'] == 'start'
            create_intents = [row for row in events if row.get('phase') == 'intent'
                              and row.get('operation') == 'create']
            start_intents = [row for row in events if row.get('phase') == 'intent'
                             and row.get('operation') == 'start']
            check('one Codex tool container create was attempted', len(create_intents) == 1)
            if start_intended:
                check('policy refusal occurred at the observed start phase',
                      isinstance(refusal, Exception) and len(start_intents) == 1
                      and receipt['container_id'] is not None)
                inspect = subprocess.run([docker, '--host', args.endpoint, 'container', 'inspect',
                    receipt['container_id']],
                    capture_output=True, text=True, timeout=10)
                rows = json.loads(inspect.stdout) if inspect.returncode == 0 else []
                info = rows[0] if isinstance(rows, list) and len(rows) == 1 else {}
                state = info.get('State', {}) if isinstance(info, dict) else {}
                state_error = state.get('Error', '') if isinstance(state, dict) else ''
                state_error_apparmor = isinstance(state_error, str) and 'apparmor' in state_error.lower()
                host = info.get('HostConfig', {}) if isinstance(info, dict) else {}
                security = host.get('SecurityOpt') or []
                host_apparmor_options = [value[len('apparmor='):] for value in security
                    if isinstance(value, str) and value.startswith('apparmor=')]
                configured_profile_exact = (host_apparmor_options == [candidate.APPARMOR_PROFILE]
                    and info.get('AppArmorProfile') == candidate.APPARMOR_PROFILE)
                nonready_state = (state.get('Running') is False
                    and state.get('Status') in ('created', 'exited', 'dead'))
                profile_refusal = (absent and state_error_apparmor
                    and configured_profile_exact and nonready_state)
                result['start_readback'] = {'inspect_succeeded': inspect.returncode == 0,
                    'state_status': state.get('Status') if state.get('Status') in (
                        'created', 'running', 'paused', 'restarting', 'removing', 'exited', 'dead') else None,
                    'state_running': state.get('Running') if type(state.get('Running')) is bool else None,
                    'state_error_present': bool(state_error),
                    'state_error_mentions_apparmor': state_error_apparmor,
                    'host_profile_absent_before_start': absent,
                    'configured_profile_exact': configured_profile_exact,
                    'nonready_state': nonready_state,
                    'apparmor_profile': info.get('AppArmorProfile'),
                    'host_apparmor_options': host_apparmor_options,
                    'host_security_option_names': sorted('no-new-privileges' if value in (
                        'no-new-privileges', 'no-new-privileges=true', 'no-new-privileges:true')
                        else 'apparmor' if value.startswith('apparmor=')
                        else 'seccomp' if value.startswith('seccomp=') else 'other'
                        for value in security if isinstance(value, str)),
                    'cap_add': sorted(host.get('CapAdd') or []),
                    'cap_drop': sorted(host.get('CapDrop') or [])}
                check('Docker AppArmor start refusal matches the exact configured profile and stayed nonready',
                      profile_refusal)
                result['refusal_evidence'] = {'state_error_mentions_apparmor': state_error_apparmor,
                    'configured_profile_exact': configured_profile_exact,
                    'host_profile_absent_before_start': absent, 'nonready_state': nonready_state,
                    'ready_environment_returned': False}
            else:
                check('setup refusal is the production environment creation refusal',
                      isinstance(refusal, EnvironmentUnavailable)
                      and refusal.code == 'environment_create_unknown')
                check('create refusal retains its unsettled ownership receipt',
                      'create' in receipt['unsettled'])
                check('create error names the absent AppArmor profile',
                      create_refusal_evidence['apparmor'] and create_refusal_evidence['profile'])
                # The daemon owns the exact failure text; only fixed predicates are published.
                log = subprocess.run([docker, '--host', args.endpoint, 'container', 'ls', '--all',
                    '--no-trunc', '--quiet', '--filter', 'label=io.oslit.engagement=' + receipt['nonce']],
                    capture_output=True, text=True, timeout=10)
                check('create refusal left no owned container', log.returncode == 0 and not log.stdout.strip())
                result['refusal_evidence'] = {'phase': 'create', 'docker_error_mentions_apparmor':
                    create_refusal_evidence['apparmor'], 'docker_error_mentions_profile':
                    create_refusal_evidence['profile'], 'ready_environment_returned': False}
                # An exact daemon refusal plus an empty container inventory settles the
                # unknown create outcome before cleanup-only receipt recovery.
                receipt['unsettled'].remove('create')
            result['events'] = [{'phase': row.get('phase'), 'operation': row.get('operation'),
                'status': row.get('status')} for row in events]
            recovered = Environment(profile, limits, authorize, events.append,
                dispatch_guard=lambda: __import__('contextlib').nullcontext(), receipt=receipt)
            cleanup = recovered.cleanup()
            result['cleanup'] = {'status': cleanup['status'],
                'owned_workspace': cleanup.get('owned_workspace')}
            check('cleanup-only recovery removed all owned resources', cleanup['status'] == 'clean')
            check('recovery did not retry container creation', len([row for row in events
                if row.get('phase') == 'intent' and row.get('operation') == 'create']) == 1)
            leftovers = subprocess.run([docker, '--host', args.endpoint, 'container', 'ls', '--all',
                '--quiet', '--filter', 'label=io.oslit.engagement=' + receipt['nonce']],
                capture_output=True, text=True, timeout=10)
            check('refused attempt left no owned stage or active container',
                  leftovers.returncode == 0 and not leftovers.stdout.strip())
            if receipt['prepared_image_id']:
                image = subprocess.run([docker, '--host', args.endpoint, 'image', 'inspect',
                    receipt['prepared_image_id']], capture_output=True, text=True, timeout=10)
                check('recovery removed the partial prepared image', image.returncode != 0)
            result['identity'] = {'daemon_id': daemon_id, 'image_id': args.image_id,
                                  'container_id_observed': receipt['container_id'] is not None,
                                  'unsettled_before_recovery': unsettled_before_recovery}
        result['status'] = 'passed'
    except Exception as error:
        result['error'] = (getattr(error, 'code', None) or type(error).__name__)
        # Once any resource identity exists, attempt retired-receipt cleanup even when the
        # operation ledger appears settled. This path never calls prepare/start.
        if environment is not None and profile is not None:
            try:
                receipt = environment.receipt()
                recovered = Environment(profile, limits, authorize, lambda _: None,
                    dispatch_guard=lambda: __import__('contextlib').nullcontext(), receipt=receipt)
                cleanup = recovered.cleanup()
                result['fallback_cleanup'] = {'status': cleanup.get('status'),
                    'owned_workspace': cleanup.get('owned_workspace')}
            except Exception as cleanup_error:
                result['fallback_cleanup'] = {'status': 'unresolved',
                    'error': getattr(cleanup_error, 'code', type(cleanup_error).__name__)}
    cleanup_result = result.get('fallback_cleanup') or result.get('cleanup') or {}
    result['cleanup_status'] = (cleanup_result.get('status')
        if cleanup_result.get('status') in ('clean', 'unresolved') else 'unresolved')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'output': str(args.output)}))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
