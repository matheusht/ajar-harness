#!/usr/bin/env python3
"""Failure-first startup ownership checks on actual installed native processes.

Before implementation: a rejected owner publication must stop the exact model or
bridge before native initialization; errors retain that receipt and verified
cleanup. Accepted startup/session callbacks must retain both ownership stages.
This submits no model prompt, opens no provider connection and uses no lab target.
"""
import argparse
from contextlib import contextmanager
import importlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(Path(__file__).parent))
from check_native_runtime_adapters import profile


class PublicationRejected(ValueError):
    pass


@contextmanager
def guard():
    yield


def run(base):
    from native_runtime_owner import process_identity, recover_runtime_owner
    rows = []
    for kind in ('codex', 'omp', 'bridge'):
        root = base / kind
        root.mkdir()
        work = root / 'workspace'
        work.mkdir()
        observed = []
        def reject(receipt):
            observed.append(receipt)
            key = 'bridge_process' if kind == 'bridge' else 'process'
            assert receipt['session_id'] is None
            assert process_identity(receipt[key]['pid']) == receipt[key]
            raise PublicationRejected('fixture_journal_unavailable')
        try:
            if kind == 'bridge':
                from native_runtime_codex import NativeExecutor
                def launch(command):
                    return subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL, start_new_session=True)
                NativeExecutor(launcher=launch, command=['/bin/sleep', '30'], environment_id='fixture',
                    cwd=str(work), dispatch_guard=guard, profile_sha256='sha256:' + '1' * 64,
                    owner_observer=reject)
            else:
                native = importlib.import_module('native_runtime_' + kind)
                p = profile(root, kind, Path(shutil.which(kind)).resolve())
                native.Runtime(p, root / 'state', work, protected_model=True,
                    profile_sha256='sha256:' + '1' * 64, owner_observer=reject,
                    dispatch_guard=guard,
                    command_prefix=['/usr/bin/sandbox-exec', '-p', '(version 1)(allow default)(deny network*)'])
            raise AssertionError('owner rejection ignored')
        except PublicationRejected as error:
            assert len(observed) == 1, 'owner absent or published twice'
            assert error.owner_receipt == observed[0], 'exception lost actual owner'
            assert error.cleanup_result['process_exited']
            assert error.cleanup_result['child_absence'] == 'verified'
            assert error.cleanup_result['capabilities_revoked'] is True
            assert recover_runtime_owner(error.owner_receipt)['process_exited']
            rows.append({'check': kind + '_rejected_publication', 'status': 'passed'})
        except Exception as error:
            rows.append({'check': kind + '_rejected_publication', 'status': 'failed',
                         'error': type(error).__name__ + ': ' + str(error)})
    for kind in ('codex', 'omp'):
        root = base / (kind + '-accepted')
        root.mkdir()
        work = root / 'workspace'
        work.mkdir()
        observed = []
        runtime = None
        try:
            native = importlib.import_module('native_runtime_' + kind)
            p = profile(root, kind, Path(shutil.which(kind)).resolve())
            runtime = native.Runtime(p, root / 'state', work, protected_model=True,
                profile_sha256='sha256:' + '2' * 64, owner_observer=observed.append,
                dispatch_guard=guard,
                command_prefix=['/usr/bin/sandbox-exec', '-p', '(version 1)(allow default)(deny network*)'])
            assert len(observed) == 1 and observed[0]['session_id'] is None
            identity = runtime.fresh()
            assert len(observed) == 2 and observed[1]['session_id'] == identity['session_id']
            assert observed[0]['process'] == observed[1]['process']
            closed = runtime.close()
            assert closed['process_exited'] and closed['child_absence'] == 'verified'
            rows.append({'check': kind + '_accepted_stages', 'status': 'passed'})
        except Exception as error:
            rows.append({'check': kind + '_accepted_stages', 'status': 'failed',
                         'error': type(error).__name__ + ': ' + str(error)})
        finally:
            if runtime:runtime.close()
    return {'status': 'passed' if all(row['status'] == 'passed' for row in rows) else 'failed',
            'classification': 'actual_native_startup_no_model', 'provider_requests': 0, 'checks': rows}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    with tempfile.TemporaryDirectory(prefix='native-startup-owner-') as path:
        result = run(Path(path).resolve())
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
    sys.exit(result['status'] != 'passed')
