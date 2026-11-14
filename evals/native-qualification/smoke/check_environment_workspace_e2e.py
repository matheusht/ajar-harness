#!/usr/bin/env python3
"""Actual bounded filesystem helper through an explicitly simulated Docker CLI."""
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
    result = {'kind': 'environment-workspace-readback-e2e-v2',
              'classification': 'simulated_docker_transport_with_actual_filesystem_helper', 'checks': [],
              'unverified': ['real Docker workspace', 'SSH workspace', 'earlier experiment byte identity']}
    def check(name, condition):
        result['checks'].append({'name': name, 'passed': bool(condition)}); assert condition, name
    try:
        from research_environment import Environment, EnvironmentUnavailable
        from engagement_contract import canonical, source_manifest, ContractError
        with tempfile.TemporaryDirectory(prefix='workspace-readback-e2e-') as name:
            root = Path(name).resolve(); work = root / 'workspace'; work.mkdir()
            tree = work / 'tree'; tree.mkdir(); (tree / 'probe.py').write_text('print("local-probe")\n')
            (tree / 'probe.py').chmod(0o751); (tree / 'nested').mkdir(); (tree / 'nested' / 'result.txt').write_text('controlled-result\n')
            (work / 'empty').write_bytes(b'')
            docker = root / 'docker'
            shim = r'''
 if '-c' in args:
  import subprocess
  (root/'helper-called').touch()
  index=args.index('-c');program=args[index+1]
  program=program.replace("WORKSPACE_ROOT = '/work'",'WORKSPACE_ROOT = '+repr(str(root/'workspace')))
  if (root/'race-kind').exists():
   race=(root/'race-kind').read_text();(root/'race-kind').unlink()
   injection=''' + 'r"""' + r'''
_original_read = os.read
_race_done = False
def _race_read(fd, count):
    global _race_done
    data = _original_read(fd, count)
    if data and not _race_done:
        _race_done = True
        if RACE_KIND == 'file':
            with open(WORKSPACE_ROOT + '/tree/probe.py', 'wb') as target:
                target.write(b'changed during read\n')
        elif RACE_KIND == 'directory':
            os.rename(WORKSPACE_ROOT + '/tree', WORKSPACE_ROOT + '/old-tree')
            os.mkdir(WORKSPACE_ROOT + '/tree')
        elif RACE_KIND == 'addition':
            with open(WORKSPACE_ROOT + '/tree/late.txt', 'wb') as target:
                target.write(b'new file\n')
    return data
os.read = _race_read
''' + '"""' + r'''
   program=program.replace("if __name__ == '__main__':",'RACE_KIND = '+repr(race)+'\n'+injection+"\nif __name__ == '__main__':")
  process=subprocess.run([sys.executable,'-I','-S','-c',program,*args[index+2:]])
  sys.exit(process.returncode)
'''
            docker.write_text(FAKE_DOCKER.replace('PYTHON', sys.executable).replace("elif args[:2]==['container','exec']:\n", "elif args[:2]==['container','exec']:\n" + shim))
            docker.chmod(0o700)
            profile = {'kind': 'research-environment-profile-v2', 'transport': 'docker', 'docker_binary': str(docker),
                       'docker_endpoint': 'unix:///fixture/docker.sock', 'daemon_id': 'daemon-fixture',
                       'image_id': 'sha256:' + '1' * 64, 'platform': 'linux/arm64', 'uid': 1000, 'gid': 1000, 'ssh': None}
            limits = {'memory_bytes': 64 * 1024 * 1024, 'workspace_bytes': 1024 * 1024, 'cpu_count': 1,
                      'pids': 32, 'lease_seconds': 5, 'output_bytes': 4096}
            active = [True]; events = []
            def authorize():
                if not active[0]: raise RuntimeError('revoked')
                return {'seconds_remaining': 5}
            environment = Environment(profile, limits, authorize, events.append, dispatch_guard=nullcontext)
            application = {'id': 'app', 'kind': 'application', 'identity': {'base_url': 'https://target.invalid/', 'version': None},
                           'account_refs': [], 'permissions': ['read']}
            environment.prepare([application], {})
            def denied(call):
                try: call()
                except (EnvironmentUnavailable, ContractError): return True
                return False
            try:
                expected = source_manifest(tree)
                read = environment.read_workspace_manifest('/work/tree')
                check('worker tree matches canonical source manifest with exact modes', read['manifest'] == expected and read['manifest_sha256'] == 'sha256:' + hashlib.sha256(canonical(expected)).hexdigest())
                callback = next(e for e in events if e['operation_id'] == read['operation_id'])
                check('manifest callback binds exact path count and digest', callback['operation'] == 'read_workspace_manifest' and callback['phase'] == 'result' and callback['files'] == len(expected) and callback['path'] == '/work/tree' and callback['manifest_sha256'] == read['manifest_sha256'])
                artifact = environment.read_artifact('tree/probe.py', 4096)
                check('artifact returns actual bytes and explicit operation identity', artifact['content'] == (tree / 'probe.py').read_bytes() and artifact['bytes'] == len(artifact['content']) and artifact['output_sha256'] == expected['probe.py']['sha256'] and bool(artifact['operation_id']))
                callback = next(e for e in events if e['operation_id'] == artifact['operation_id'])
                check('artifact callback retains digest and size without raw bytes', callback['operation'] == 'read_artifact' and callback['bytes'] == artifact['bytes'] and callback['output_sha256'] == artifact['output_sha256'] and 'content' not in callback)
                check('empty regular artifact obeys zero byte limit', environment.read_artifact('empty', 0)['content'] == b'')

                for path in ('/etc/passwd', '../outside', 'tree/../probe.py', 'tree//probe.py', './tree/probe.py', 'tree/\x00bad'):
                    (root / 'helper-called').unlink(missing_ok=True)
                    check('artifact rejects invalid path ' + repr(path), denied(lambda: environment.read_artifact(path, 4096)) and not (root / 'helper-called').exists())
                for path in ('/input', '/work/', '/work/../input', '/work//tree', '/work/tree/'):
                    (root / 'helper-called').unlink(missing_ok=True)
                    check('manifest rejects invalid workspace path ' + path, denied(lambda: environment.read_workspace_manifest(path)) and not (root / 'helper-called').exists())

                outside = root / 'outside'; outside.write_text('outside fixture\n')
                (tree / 'link').symlink_to(outside)
                check('artifact refuses final symlink escape', denied(lambda: environment.read_artifact('tree/link', 4096)))
                check('manifest refuses symlink entries', denied(lambda: environment.read_workspace_manifest('/work/tree')))
                (tree / 'link').unlink(); (work / 'linked').symlink_to(tree, target_is_directory=True)
                check('artifact refuses parent directory symlink', denied(lambda: environment.read_artifact('linked/probe.py', 4096)))
                check('manifest refuses root directory symlink', denied(lambda: environment.read_workspace_manifest('/work/linked')))
                (work / 'linked').unlink(); os.mkfifo(work / 'pipe')
                check('nonregular artifact fails without blocking', denied(lambda: environment.read_artifact('pipe', 4096)))
                (work / 'pipe').unlink()
                check('artifact size bound rejects oversized file', denied(lambda: environment.read_artifact('tree/probe.py', 1)))
                check('caller cannot expand admitted output bound', denied(lambda: environment.read_artifact('tree/probe.py', limits['output_bytes'] + 1)))
                (tree / 'sensitive.txt').write_bytes(b'Authorization: fixture-transient\n')
                previous = len(events)
                check('sensitive artifact is withheld before callback persistence', denied(lambda: environment.read_artifact('tree/sensitive.txt', 4096)) and len(events) == previous)
                (tree / 'sensitive.txt').unlink()

                original = (tree / 'probe.py').read_bytes()
                (root / 'race-kind').write_text('file')
                check('file mutation during read is refused', denied(lambda: environment.read_artifact('tree/probe.py', 4096)) and (tree / 'probe.py').read_bytes() != original)
                (tree / 'probe.py').write_bytes(original)
                (root / 'race-kind').write_text('addition')
                check('tree addition during manifest scan is refused', denied(lambda: environment.read_workspace_manifest('/work/tree')) and (tree / 'late.txt').exists())
                (tree / 'late.txt').unlink()
                (root / 'race-kind').write_text('directory')
                check('parent replacement during read is refused', denied(lambda: environment.read_artifact('tree/probe.py', 4096)) and (work / 'old-tree').exists())
                tree.rmdir(); (work / 'old-tree').rename(tree)
                active[0] = False; previous = len(events); (root / 'helper-called').unlink(missing_ok=True)
                check('revoked grant prevents helper dispatch and publication', denied(lambda: environment.read_artifact('tree/probe.py', 4096)) and len(events) == previous and not (root / 'helper-called').exists())
            finally:
                environment.cleanup()
        result['status'] = 'passed'
    except Exception as error:
        result['status'] = 'failed'; result['error'] = type(error).__name__ + ': ' + str(error)
    result['source_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'checks': len(result['checks']), 'output': str(args.output)}))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__': raise SystemExit(main())
