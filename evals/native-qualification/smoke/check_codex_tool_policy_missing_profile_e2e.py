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
                    '--format', '{{json .State}}', receipt['container_id']],
                    capture_output=True, text=True, timeout=10)
                state = json.loads(inspect.stdout) if inspect.returncode == 0 else {}
                state_error = state.get('Error', '') if isinstance(state, dict) else ''
                profile_refusal = (isinstance(state_error, str) and
                    'apparmor' in state_error.lower() and candidate.APPARMOR_PROFILE in state_error)
                check('Docker recorded missing named AppArmor profile as the start refusal',
                      profile_refusal)
                result['refusal_evidence'] = {'docker_state_error_mentions_apparmor':
                    'apparmor' in state_error.lower(), 'docker_state_error_mentions_profile':
                    candidate.APPARMOR_PROFILE in state_error, 'ready_environment_returned': False}
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
            result['cleanup'] = cleanup
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
                result['fallback_cleanup'] = recovered.cleanup()
            except Exception as cleanup_error:
                result['fallback_cleanup'] = {'status': 'unresolved',
                    'error': getattr(cleanup_error, 'code', type(cleanup_error).__name__)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'output': str(args.output)}))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
