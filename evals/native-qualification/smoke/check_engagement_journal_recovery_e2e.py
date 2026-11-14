#!/usr/bin/env python3
"""Failure-first v2 journal recovery checks; no provider or target is contacted.

Run with --repository PATH to exercise another checkout without copying its code.
The signing fixture, assertions and crash hook belong to this test, never the product.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]


def fingerprint(root):
    return hashlib.sha256(b''.join(path.name.encode() + b'\0' + path.read_bytes()
        for path in sorted((root / 'events').iterdir()) if path.is_file())).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    sys.path.insert(0, str(repository / 'tools'))
    result = {'kind': 'engagement-journal-recovery-e2e-v2',
              'classification': 'engineering_simulation', 'scenarios': [],
              'provider_calls': 0, 'target_calls': 0,
              'requirements': 'Python 3 and ssh-keygen; no provider, Docker or SSH host',
              'expected': 'Eight passed scenarios; refused operations leave journal and capacity unchanged',
              'python': sys.version.split()[0], 'platform': platform.platform(),
              'command': [sys.executable, str(Path(__file__).resolve()),
                          '--repository', str(repository), '--output', str(args.output)],
              'unverified': ['native isolation', 'live provider usage', 'Docker and SSH',
                             'multi-day operation', 'research acceptance']}
    try:
        from engagement_contract import ContractError, canonical, digest, load_inputs, source_manifest
        from engagement_controller import Controller, ControllerError, Principal, WorkerServer
        spec = importlib.util.spec_from_file_location('authority_fixture',
            Path(__file__).with_name('check_engagement_contract_e2e.py'))
        fixture = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fixture)

        class Case:
            def __init__(self, directory, row, initialize=True):
                self.path, self.row = directory, row
                self.inputs = fixture.make_fixture(directory / 'input')
                self.contract = load_inputs(self.inputs)
                self.root = directory / 'engagement'
                self.serial, self.servers = 0, []
                row['checks'], row['commands'] = [], []
                row['inputs'] = {'scope_sha256': digest(self.contract.frozen_files['scope.md']),
                                 'signer_fingerprint': self.contract.signer_fingerprint,
                                 'source': self.contract.scope['access'][0]['identity']}
                if initialize:
                    self.c = Controller.initialize(self.root, self.contract,
                        evidence_class='engineering_simulation')
                    parent = directory / 'workspaces'
                    parent.mkdir(mode=0o700)
                    self.workspace = parent / 'lead'
                    self.workspace.mkdir(mode=0o700)
                    self.c.record_worker_started('lead-1', 1, 'fixture-lead', self.workspace)

            def check(self, name, passed, **observed):
                self.row['checks'].append({'name': name, 'status': 'passed' if passed else 'failed',
                                           'observed': observed})

            def attempt(self, operation):
                try:
                    return {'status': 'accepted', 'value': operation()}
                except (ControllerError, ContractError) as error:
                    return {'status': 'rejected', 'code': error.code}

            def request(self, kind, payload):
                self.serial += 1
                return {'request_id': f'fixture-{self.serial}',
                        'expected_revision': self.c.state()['revision'], 'type': kind, 'payload': payload}

            def submit(self, kind, payload, worker='lead-1'):
                return self.c.submit(Principal('worker', worker, 1), self.request(kind, payload))

            def cli(self, *arguments):
                command = [sys.executable, str(repository / 'tools/native_engagement.py'),
                           *map(str, arguments)]
                proc = subprocess.run(command, capture_output=True, text=True, timeout=30)
                evidence = {'argv': command, 'returncode': proc.returncode,
                            'stdout_bytes': len(proc.stdout.encode())}
                self.row['commands'].append(evidence)
                document = json.loads(proc.stdout)
                evidence.update(status=document.get('status'), code=document.get('code'))
                return document

            def socket(self, worker='lead-1'):
                path = self.path / (worker + '.sock')
                server = WorkerServer(self.root, Principal('worker', worker, 1), path)
                server.start()
                self.servers.append(server)
                return path

            def cli_submit(self, endpoint, request):
                path = self.path / 'request.json'
                path.write_bytes(canonical(request))
                path.chmod(0o600)
                return self.cli('submit', '--socket', endpoint, '--file', path)

            def worker(self, name, workspace=None):
                self.submit('worker_request', {'worker_id': name, 'role': 'specialist',
                    'profile_id': 'runtime-main', 'question': 'Inspect harmless fixture.'})
                workspace = workspace or self.path / 'workspaces' / name
                workspace.mkdir(mode=0o700, exist_ok=True)
                return self.attempt(lambda: self.c.record_worker_started(name, 1,
                    'fixture-session-' + name, workspace))

            def task(self, name, resources, worker):
                self.submit('task_create', {'task_id': name, 'question': 'Inspect fixture.',
                    'priority': 1, 'resources': resources, 'prerequisites': [], 'evidence_refs': []})
                self.submit('task_assign', {'task_id': name, 'worker_id': worker})

            def close(self):
                for server in self.servers:
                    server.close()

        def publication(identity, body='Harmless observation.', artifacts=None):
            return {'publication_id': identity, 'kind': 'observation', 'subject': 'fixture',
                    'body': body, 'refs': [], 'supersedes': [], 'artifacts': artifacts or []}

        def observation(status='settled', resources=None, seconds=2):
            return {'status': status, 'worker_seconds': seconds, 'resources': resources or {},
                    'usage': {'tokens': None, 'cost': None}, 'cleanup': 'pending'}

        def ownership(x):
            x.worker('owner')
            x.worker('other')
            x.task('task-a', ['source-main'], 'owner')
            x.task('task-b', [], 'other')
            before = fingerprint(x.root)
            outcome = x.attempt(lambda: x.c.prepare_dispatch('other', 1, seconds=1,
                resources=['source-main'], adapter_id='fixture-owner'))
            x.check('cross-task resource refused before reservation', outcome['status'] == 'rejected'
                    and fingerprint(x.root) == before, outcome=outcome)
            own = x.attempt(lambda: x.c.prepare_dispatch('owner', 1, seconds=1,
                resources=['source-main'], adapter_id='fixture-owner'))
            x.check('actual owner remains eligible', own['status'] == 'accepted', outcome=own)

        def workspaces(x):
            nested = x.workspace / 'nested'
            outcome = x.worker('nested-worker', nested)
            x.check('nested workspace refused', outcome['status'] == 'rejected', outcome=outcome)
            sentinel = b'fixture-private-other-worker-history'
            if outcome['status'] == 'accepted':
                (nested / 'private-note.txt').write_bytes(sentinel)
            endpoint = x.socket()
            response = x.cli_submit(endpoint, x.request('publish', publication('cross-workspace',
                artifacts=[{'path': 'nested/private-note.txt'}])))
            leaked = any(sentinel in p.read_bytes() for p in (x.root / 'objects').iterdir() if p.is_file())
            x.check('host publication cannot expose nested worker history',
                    response['status'] == 'rejected' and not leaked, response=response, leaked=leaked)
            # The request creates a pending worker; only its start must be refused.
            x.submit('worker_request', {'worker_id': 'parent-worker', 'role': 'specialist',
                'profile_id': 'runtime-main', 'question': 'Inspect harmless fixture.'})
            before = fingerprint(x.root)
            parent = x.attempt(lambda: x.c.record_worker_started('parent-worker', 1,
                'fixture-parent', x.workspace.parent))
            x.check('ancestor workspace refused without mutation', parent['status'] == 'rejected'
                    and fingerprint(x.root) == before, outcome=parent)

        def crash(x):
            before = x.c.state()['revision']
            helper = '''
import os, stat, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from engagement_controller import Controller
root = Path(sys.argv[2]); events = (root / 'events').stat(); sync = os.fsync
def crash_after_commit(fd):
    sync(fd)
    info = os.fstat(fd)
    if stat.S_ISDIR(info.st_mode) and (info.st_dev, info.st_ino) == (events.st_dev, events.st_ino):
        os._exit(86)
os.fsync = crash_after_commit
Controller(root).direction('Committed immediately before fixture process death.')
'''
            proc = subprocess.run([sys.executable, '-c', helper, str(repository / 'tools'),
                                   str(x.root)], capture_output=True, text=True, timeout=15)
            x.check('owned process dies after actual directory commit', proc.returncode == 86,
                    returncode=proc.returncode)
            response = x.cli('status', '--engagement-root', x.root)
            x.check('committed journal replays after process death', response.get('status') == 'active'
                    and response.get('revision') == before + 1,
                    status=response.get('status'), code=response.get('code'), revision=response.get('revision'))
            if response.get('status') == 'active':
                recovered = Controller(x.root)
                outcome = recovered.direction('Continue after clean replay.')
                x.check('recovered journal appends without losing the committed event',
                    outcome['revision'] == before + 2 and len(recovered.state()['directions']) == 2)
            else:
                x.row['not_run'] = ['append after recovery: replay failed']

        def receipt_identity(x):
            grant = x.c.prepare_dispatch('lead-1', 1, seconds=60, resources=[], adapter_id='fixture-owner')
            minimal = {key: grant[key] for key in ('dispatch_id', 'adapter_id')}
            before, usage = fingerprint(x.root), x.c.state()['usage']
            stored_before = sorted(str(p.relative_to(x.root)) for p in (x.root / 'receipts').rglob('*'))
            stored = x.attempt(lambda: str(x.c.store_receipt(minimal, observation(), adapter_id='fixture-owner')))
            stored_after = sorted(str(p.relative_to(x.root)) for p in (x.root / 'receipts').rglob('*'))
            x.check('incomplete grant cannot be stored', stored['status'] == 'rejected'
                    and stored_after == stored_before, outcome=stored)
            if stored['status'] == 'accepted':
                receipt = Path(stored['value'])
            else:
                receipt = x.c.store_receipt(grant, observation(), adapter_id='fixture-owner')
                malformed = json.loads(receipt.read_bytes())
                malformed['grant'] = minimal
                receipt.write_bytes(canonical(malformed))
            adopted = x.attempt(lambda: x.c.adopt_receipt(grant['dispatch_id'], receipt, adapter_id='fixture-owner'))
            x.check('incomplete grant cannot settle or release capacity', adopted['status'] == 'rejected'
                    and fingerprint(x.root) == before and x.c.state()['usage'] == usage, outcome=adopted)

        def unknown_recovery(x):
            grant = x.c.prepare_dispatch('lead-1', 1, seconds=60, resources=['source-main'], adapter_id='fixture-owner')
            marker = x.path / 'effect-count'
            marker.write_text('1')
            first = x.c.store_receipt(grant, observation('unknown', {'source-main': 'unknown'}, 1),
                                      adapter_id='fixture-owner')
            first_bytes = first.read_bytes()
            x.c.adopt_receipt(grant['dispatch_id'], first, adapter_id='fixture-owner')
            response = x.cli('status', '--engagement-root', x.root)
            x.check('unknown execution conservatively holds capacity across restart',
                    response.get('usage', {}).get('reserved_worker_seconds') == 60
                    and 'source-main' in response.get('resource_holds', {}))
            recovered = Controller(x.root)
            late = x.attempt(lambda: str(recovered.store_receipt(grant,
                observation('settled', {'source-main': 'unchanged'}), adapter_id='fixture-owner')))
            x.check('late protected terminal receipt preserves prior bytes', late['status'] == 'accepted'
                    and first.read_bytes() == first_bytes, outcome=late)
            if late['status'] != 'accepted':
                x.row['not_run'] = ['terminal settlement', 'duplicate settlement',
                                   'preserved observation history', 'dispatch after settlement']
                return
            second = Path(late['value'])
            adopted = x.attempt(lambda: recovered.adopt_receipt(grant['dispatch_id'], second, adapter_id='fixture-owner'))
            state = recovered.state()
            x.check('late receipt settles original invocation and releases its hold',
                adopted['status'] == 'accepted' and state['usage']['invocations'] == 1
                and state['usage']['worker_seconds'] == 2 and state['usage']['reserved_worker_seconds'] == 0
                and 'source-main' not in state['resource_holds'], outcome=adopted, usage=state['usage'])
            before = fingerprint(x.root)
            duplicate = x.attempt(lambda: recovered.adopt_receipt(grant['dispatch_id'], second, adapter_id='fixture-owner'))
            x.check('late receipt adoption is idempotent without repeating effect',
                duplicate['status'] == 'accepted' and fingerprint(x.root) == before and marker.read_text() == '1')
            events = [json.loads(p.read_bytes()) for p in sorted((x.root / 'events').glob('*.json'))]
            history = [e for e in events if e['type'] == 'dispatch_observed'
                       and e['payload']['dispatch_id'] == grant['dispatch_id']]
            x.check('unknown and settled observations remain immutable history',
                len(history) == 2 and first.read_bytes() == first_bytes and second != first,
                observation_count=len(history))
            next_dispatch = x.attempt(lambda: recovered.prepare_dispatch('lead-1', 1, seconds=1,
                resources=['source-main'], adapter_id='fixture-owner'))
            x.check('recovered resource can be dispatched again', next_dispatch['status'] == 'accepted', outcome=next_dispatch)

        def input_overlap(x):
            source = Path(x.contract.inputs['access_files']['source-main'])
            before = digest(canonical(source_manifest(source)))
            root = source / 'controller'
            response = x.cli('run', '--inputs', x.inputs, '--engagement-root', root)
            after = digest(canonical(source_manifest(source)))
            x.check('overlapping root rejected before writing', response['status'] == 'rejected'
                    and not root.exists() and before == after, status=response['status'],
                    code=response.get('code'), root_created=root.exists(), source_unchanged=before == after)

        def pagination(x):
            for number in range(66):
                x.submit('publish', publication(f'large-{number}', 'x' * 65000))
            before, revision = fingerprint(x.root), x.c.state()['revision']
            endpoint = x.socket()
            cursor, seen, pages = None, [], 0
            for _ in range(revision + 1):
                arguments = ['status', '--socket', endpoint, '--limit', '2']
                if cursor is not None:
                    arguments += ['--since', cursor]
                response = x.cli(*arguments)
                if response.get('status') != 'active':
                    x.check('large-publication status remains readable', False, response=response)
                    break
                pages += 1
                x.check('status page fits worker transport',
                    x.row['commands'][-1]['stdout_bytes'] <= 4 * 1024 * 1024,
                    bytes=x.row['commands'][-1]['stdout_bytes'])
                seen.extend(event['sequence'] for event in response['updates'])
                next_cursor = response['next_cursor']
                if not response['has_more']:
                    break
                if next_cursor == cursor:
                    x.check('pagination advances', False); break
                cursor = next_cursor
            x.check('all updates remain reachable exactly once without mutation',
                    seen == list(range(1, revision + 1)) and fingerprint(x.root) == before,
                    pages=pages, expected_events=revision, observed_events=len(seen), unique_events=len(set(seen)))

        def retries(x):
            endpoint = x.socket()
            request = x.request('publish', publication('lost-acknowledgment'))
            first = x.cli_submit(endpoint, request)
            grant = x.c.prepare_dispatch('lead-1', 1, seconds=1, resources=[], adapter_id='fixture-owner')
            x.cli('stop', '--engagement-root', x.root)
            before = fingerprint(x.root)
            retry = x.cli_submit(endpoint, request)
            x.check('accepted request replay survives stop without mutation', retry == first
                    and fingerprint(x.root) == before, first=first, retry=retry)
            changed = dict(request, payload=publication('lost-acknowledgment', 'Changed bytes.'))
            conflict = x.cli_submit(endpoint, changed)
            x.check('changed retry still conflicts after stop', conflict.get('code') == 'request_conflict'
                    and fingerprint(x.root) == before, response=conflict)
            capability = x.attempt(lambda: x.c.authorize_dispatch(grant))
            x.check('old receipt cannot restore stopped capability', capability['status'] == 'rejected'
                    and x.c.state()['status'] == 'stopped', outcome=capability)

        scenarios = [('ownership', ownership), ('workspaces', workspaces), ('crash', crash),
                     ('receipt_identity', receipt_identity), ('unknown_recovery', unknown_recovery),
                     ('input_overlap', input_overlap), ('pagination', pagination), ('retries', retries)]
        # Short paths keep AF_UNIX endpoints usable on macOS as well as Linux.
        with tempfile.TemporaryDirectory(prefix='m1-e2e-', dir='/tmp') as temporary:
            for index, (name, action) in enumerate(scenarios):
                row = {'id': name, 'status': 'failed'}
                result['scenarios'].append(row)
                directory = Path(temporary).resolve() / str(index)
                directory.mkdir(mode=0o700)
                case = None
                try:
                    case = Case(directory, row, initialize=name != 'input_overlap')
                    action(case)
                    row['status'] = 'passed' if all(c['status'] == 'passed' for c in row['checks']) else 'failed'
                except Exception as error:
                    row['error'] = type(error).__name__ + ': ' + str(error)
                finally:
                    if case is not None:
                        try:
                            case.close()
                        except Exception as error:
                            row.update(status='failed', cleanup_error=type(error).__name__ + ': ' + str(error))
        result['status'] = 'passed' if all(row['status'] == 'passed' for row in result['scenarios']) else 'failed'
    except Exception as error:
        result.update(status='unavailable', error=type(error).__name__ + ': ' + str(error))
    paths = [Path(__file__), Path(__file__).with_name('check_engagement_contract_e2e.py'),
             *(repository / 'tools' / name for name in ('engagement_contract.py', 'engagement_controller.py',
                                                       'native_engagement.py'))]
    result['source_hashes'] = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                               for path in paths if path.is_file()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'output': str(args.output),
                      'scenarios': [{key: row[key] for key in ('id', 'status')} for row in result['scenarios']]},
                     sort_keys=True))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    os.umask(0o077)
    raise SystemExit(main())
