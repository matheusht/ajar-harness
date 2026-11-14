#!/usr/bin/env python3
"""Frozen host-key bytes with unchanged signed identity, through simulated SSH."""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'tools'))
from check_environment_transport_e2e import FAKE_DOCKER


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = {'kind': 'environment-frozen-known-hosts-e2e-v2', 'classification': 'simulated_ssh_and_docker_cli',
              'checks': [], 'unverified': ['SSH connection', 'remote host identity', 'remote lease owner']}
    def check(name, condition):
        result['checks'].append({'name': name, 'passed': bool(condition)}); assert condition, name
    try:
        from research_environment import Environment, EnvironmentUnavailable
        with tempfile.TemporaryDirectory(prefix='known-hosts-e2e-') as name:
            root = Path(name).resolve(); docker = root / 'docker'; ssh = root / 'ssh'
            docker.write_text(FAKE_DOCKER.replace('PYTHON', sys.executable)); docker.chmod(0o700)
            ssh.write_text('#!' + sys.executable + '''
import json,shlex,subprocess,sys
from pathlib import Path
root=Path(__file__).parent
known=[value for value in sys.argv if value.startswith('UserKnownHostsFile=')]
with (root/'ssh-observed.jsonl').open('a') as target:
 target.write(json.dumps({'known_hosts':known})+'\\n')
raise SystemExit(subprocess.run(shlex.split(sys.argv[-1])).returncode)
'''); ssh.chmod(0o700)
            original = root / 'original-known-hosts'; frozen = root / 'frozen-known-hosts'
            content = b'local-fixture ssh-ed25519 AAAlocalfixture\n'
            frozen.write_bytes(content); frozen.chmod(0o400)
            key = root / 'identity-reference'; key.write_text('noncredential fixture reference\n'); key.chmod(0o600)
            profile = {'kind': 'research-environment-profile-v2', 'transport': 'ssh-docker', 'docker_binary': str(docker),
                       'docker_endpoint': 'unix:///fixture/docker.sock', 'daemon_id': 'daemon-fixture',
                       'image_id': 'sha256:' + '1' * 64, 'platform': 'linux/arm64', 'uid': 1000, 'gid': 1000,
                       'ssh': {'host': 'fixture.invalid', 'port': 22, 'user': 'fixture', 'known_hosts_file': str(original),
                               'known_hosts_sha256': 'sha256:' + hashlib.sha256(content).hexdigest(),
                               'identity_file': str(key), 'python_binary': sys.executable}}
            limits = {'memory_bytes': 64 * 1024 * 1024, 'workspace_bytes': 1024 * 1024, 'cpu_count': 1,
                      'pids': 32, 'lease_seconds': 5, 'output_bytes': 4096}
            previous_path = os.environ.get('PATH', ''); os.environ['PATH'] = str(root) + os.pathsep + previous_path
            environment = None
            try:
                environment = Environment(profile, limits, lambda: {'seconds_remaining': 5}, lambda _: None,
                                          dispatch_guard=nullcontext, known_hosts_file=frozen)
                application = {'id': 'app', 'kind': 'application', 'identity': {'base_url': 'https://target.invalid/', 'version': None},
                               'account_refs': [], 'permissions': ['read']}
                environment.prepare([application], {})
                check('frozen transport reference leaves signed profile identity intact', environment.profile == profile and environment.receipt()['profile_sha256'] == environment._digest(profile))
                check('missing original path does not replace pinned frozen bytes', not original.exists() and environment.execute(['echo'], timeout_seconds=1)['returncode'] == 0)
                rows = [json.loads(line) for line in (root / 'ssh-observed.jsonl').read_text().splitlines()]
                check('all simulated SSH launches receive the frozen host-key file', rows and all(row['known_hosts'] == ['UserKnownHostsFile=' + str(frozen)] for row in rows))
                before = len(rows); frozen.chmod(0o600); frozen.write_bytes(b'changed\n')
                try: environment.execute(['echo'], timeout_seconds=1)
                except EnvironmentUnavailable: refused = True
                else: refused = False
                check('changed frozen bytes refuse before transport dispatch', refused and len((root / 'ssh-observed.jsonl').read_text().splitlines()) == before)
                frozen.write_bytes(content); saved = root / 'saved-known-hosts'; frozen.rename(saved); frozen.symlink_to(saved)
                try: environment.execute(['echo'], timeout_seconds=1)
                except EnvironmentUnavailable: refused = True
                else: refused = False
                check('symlinked frozen reference refuses before transport dispatch', refused and len((root / 'ssh-observed.jsonl').read_text().splitlines()) == before)
                frozen.unlink(); saved.rename(frozen)
                check('cleanup retains exact signed resource identity', environment.cleanup()['status'] == 'clean')
                environment = None
            finally:
                if environment:
                    if frozen.is_symlink(): frozen.unlink()
                    frozen.write_bytes(content); environment.cleanup()
                os.environ['PATH'] = previous_path
        result['status'] = 'passed'
    except Exception as error:
        result['status'] = 'failed'; result['error'] = type(error).__name__ + ': ' + str(error)
    result['source_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'checks': len(result['checks']), 'output': str(args.output)}))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__': raise SystemExit(main())
