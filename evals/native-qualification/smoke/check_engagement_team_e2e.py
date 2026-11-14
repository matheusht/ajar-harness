#!/usr/bin/env python3
"""Exercise the real v2 journal and CLI with explicitly simulated agent events.

No provider or research target is used. Host fixture observations test ordering,
not native isolation, semantic effect verification, or remote cleanup.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', default='all')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = {'kind': 'engagement-team-check-v2', 'classification': 'engineering_simulation',
              'provider_calls': 0, 'research_acceptance': 'not_run', 'scenarios': []}
    try:
        from engagement_contract import load_inputs, digest, canonical
        from engagement_controller import Controller, Principal, WorkerServer, ControllerError
        fixture_path = Path(__file__).with_name('check_engagement_contract_e2e.py')
        spec = importlib.util.spec_from_file_location('authority_fixture', fixture_path)
        fixture = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fixture)

        def require(condition, message):
            if not condition:
                raise AssertionError(message)

        def refused(code, action):
            try:
                action()
            except ControllerError as error:
                require(error.code == code, f'{error.code} != {code}')
            else:
                raise AssertionError('accepted prohibited operation: ' + code)

        class Case:
            def __init__(self, path, scenario):
                self.path = path
                self.inputs = fixture.make_fixture(path / 'input')
                if scenario == 'E13':
                    scope = fixture.fixture_scope(self.inputs)
                    scope['limits']['hard']['worker_seconds'] = 100
                    fixture.resign_fixture(self.inputs, scope)
                self.contract = load_inputs(self.inputs)
                self.root = path / 'engagement'
                self.c = Controller.initialize(self.root, self.contract,
                                               evidence_class='engineering_simulation')
                self.lead = Principal('worker', 'lead-1', 1)
                self.serial = 0
                self.servers = []
                self.started('lead-1')

            def started(self, worker):
                directory = self.path / ('workspace-' + worker)
                directory.mkdir(mode=0o700)
                self.c.record_worker_started(worker, 1, 'fixture-session-' + worker, directory)
                return directory

            def request(self, kind, payload, principal=None, request_id=None, revision=None):
                self.serial += 1
                request = {'request_id': request_id or f'req-{self.serial}',
                           'expected_revision': self.c.state()['revision'] if revision is None else revision,
                           'type': kind, 'payload': payload}
                return self.c.submit(principal or self.lead, request)

            def worker(self, name):
                profile = self.contract.scope['runtime_assignments'][0]['profile_id']
                self.request('worker_request', {'worker_id': name, 'role': 'specialist',
                                               'profile_id': profile, 'question': 'Inspect the harmless fixture.'})
                self.started(name)
                return Principal('worker', name, 1)

            def task(self, name, priority=1, resources=None, prerequisites=None):
                return self.request('task_create', {'task_id': name, 'question': 'Inspect fixture bytes.',
                    'priority': priority, 'resources': resources or [],
                    'prerequisites': prerequisites or [], 'evidence_refs': []})

            def socket(self, principal):
                path = self.path / (principal.id + '.sock')
                server = WorkerServer(self.root, principal, path)
                server.start()
                self.servers.append(server)
                return path

            def cli(self, *arguments):
                proc = subprocess.run([sys.executable, str(ROOT / 'tools/native_engagement.py'),
                                       *map(str, arguments)], capture_output=True, text=True, timeout=15)
                document = json.loads(proc.stdout)
                require(proc.returncode in (0, 2), 'unexpected CLI exit')
                return document

            def close(self):
                for server in self.servers:
                    server.close()

        def e04(x):
            w1, w2 = x.worker('worker-1'), x.worker('worker-2')
            x.task('task-a', priority=10)
            revision = x.c.state()['revision']
            sockets = [x.socket(w1), x.socket(w2)]
            def claim(i):
                return x.cli('claim', '--socket', sockets[i], '--request-id', f'race-{i}',
                             '--expected-revision', revision)
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(claim, (0, 1)))
            require(sum(r['status'] == 'accepted' for r in results) == 1, 'exactly one claim owner')
            state = x.c.state()
            owner = state['tasks']['task-a']['owner']
            require(owner in ('worker-1', 'worker-2'), 'owner recorded')
            before = state['revision']
            winner = 0 if owner == 'worker-1' else 1
            retry = claim(winner)
            require(retry == results[winner] and x.c.state()['revision'] == before, 'idempotent claim')
            bad = {'request_id': 'forged', 'expected_revision': before, 'type': 'worker_request',
                   'payload': {}, 'actor': {'role': 'lead'}}
            refused('request_invalid', lambda: x.c.submit(w1, bad))
            refused('role_forbidden', lambda: x.request('worker_request', {}, w1))
            x.request('task_create', {'task_id': 'follow-up', 'question': 'Check another explanation.',
                'priority': 0, 'resources': [], 'prerequisites': [], 'evidence_refs': []}, w2)
            require(x.c.state()['tasks']['follow-up']['priority'] == 0, 'specialist follow-up retained')
            refused('role_forbidden', lambda: x.request('task_priority', {'task_id': 'follow-up', 'priority': 99}, w2))
            refused('worker_stale', lambda: x.request('claim', {}, Principal('worker', 'worker-1', 99)))

        def e05(x):
            worker = x.worker('worker-1')
            for i in range(7):
                x.request('publish', {'publication_id': f'observation-{i}', 'kind': 'observation',
                    'subject': 'fixture', 'body': 'Contrary observation ' + str(i),
                    'refs': [], 'supersedes': [], 'artifacts': []})
            before = x.c.state()['revision']
            cursor, seen = None, []
            while True:
                page = x.c.status(worker, since=cursor, limit=2)
                seen.extend(event['sequence'] for event in page['updates'])
                cursor = page['next_cursor']
                if not page['has_more']:
                    break
            require(len(seen) == len(set(seen)) == before, 'all updates preserved in pages')
            require(x.c.state()['revision'] == before, 'status is read-only')
            require(x.c.status(worker, since=cursor)['updates'] == [], 'cursor does not repeat events')
            x.request('updates_ack', {'cursor': cursor}, worker)
            require(Controller(x.root).state()['workers']['worker-1']['cursor'] == cursor, 'ack survives restart')
            refused('cursor_invalid', lambda: x.c.status(worker, since='other-engagement'))

        def e06(x):
            resource = x.contract.scope['access'][0]['id']
            grant = x.c.prepare_dispatch('lead-1', 1, seconds=10, resources=[resource], adapter_id='fixture-owner')
            marker = x.path / 'effect-count'
            marker.write_text('1')
            receipt = x.c.store_receipt(grant, {'status': 'settled', 'worker_seconds': 2,
                'resources': {resource: 'unknown'}, 'usage': {'tokens': None, 'cost': None},
                'cleanup': 'pending'}, adapter_id='fixture-owner')
            restarted = Controller(x.root)
            require(restarted.state()['dispatches'][grant['dispatch_id']]['status'] == 'pending', 'unadopted effect held')
            restarted.adopt_receipt(grant['dispatch_id'], receipt, adapter_id='fixture-owner')
            revision = restarted.state()['revision']
            restarted.adopt_receipt(grant['dispatch_id'], receipt, adapter_id='fixture-owner')
            require(restarted.state()['revision'] == revision and marker.read_text() == '1', 'receipt adopted once')
            require(resource in restarted.state()['resource_holds'], 'uncertain state held')
            dependent, independent = x.worker('dependent'), x.worker('independent')
            x.task('shared', priority=10, resources=[resource])
            x.task('isolated', priority=1)
            x.request('claim', {}, dependent)
            require(x.c.state()['tasks']['isolated']['owner'] == 'dependent', 'independent work remains eligible')
            refused('no_ready_task', lambda: x.request('claim', {}, independent))
            refused('resource_held', lambda: restarted.prepare_dispatch('lead-1', 1, seconds=1, resources=[resource], adapter_id='fixture-owner'))
            restarted.reconcile(grant['dispatch_id'], {resource: 'unchanged'}, adapter_id='fixture-owner')
            require(resource not in restarted.state()['resource_holds'], 'protected readback clears matching hold')

        def e13(x):
            cap = x.contract.scope['limits']['hard']['worker_seconds']
            lease = x.contract.scope['limits']['max_worker_lease_seconds']
            amount = min(cap, lease)
            other = x.worker('worker-1')
            grant = x.c.prepare_dispatch('lead-1', 1, seconds=amount, resources=[], adapter_id='fixture-owner')
            refused('resource_exhausted', lambda: x.c.prepare_dispatch(other.id, 1,
                seconds=amount, resources=[], adapter_id='fixture-owner'))
            before = x.c.state()['usage'].copy()
            require(before['reserved_worker_seconds'] == amount, 'reservation precedes dispatch')
            require(Controller(x.root).state()['usage'] == before, 'restart preserves usage')
            require(x.c.authorize_dispatch(grant), 'current grant admitted')
            accepted = threading.Event()
            def guarded_acceptance():
                with x.c.dispatch_guard(grant):
                    x.c.status()
                accepted.set()
            threading.Thread(target=guarded_acceptance, daemon=True).start()
            require(accepted.wait(2), 'host acceptance can read the same locked journal')
            receipt = x.c.store_receipt(grant, {'status': 'settled', 'worker_seconds': 1,
                'resources': {}, 'usage': {'tokens': {'input': 2, 'output': 1}, 'cost': None},
                'cleanup': 'verified'}, adapter_id='fixture-owner')
            x.c.adopt_receipt(grant['dispatch_id'], receipt, adapter_id='fixture-owner')
            require(x.c.state()['usage']['worker_seconds'] == 1, 'observed usage settled')
            require(x.c.state()['usage']['reserved_worker_seconds'] == 0, 'unused reservation released')
            refused('dispatch_settled', lambda: x.c.authorize_dispatch(grant))
            refused('reservation_invalid', lambda: x.c.prepare_dispatch('lead-1', 1, seconds=True, resources=[], adapter_id='fixture-owner'))
            refused('reservation_invalid', lambda: x.c.prepare_dispatch('lead-1', 1, seconds=lease + 1, resources=[], adapter_id='fixture-owner'))
            x.c.stop('test operator stop')
            refused('engagement_stopped', lambda: x.c.prepare_dispatch('lead-1', 1, seconds=1, resources=[], adapter_id='fixture-owner'))

        def e14(x):
            worker = x.worker('worker-1')
            x.request('publish', {'publication_id': 'forged-direction', 'kind': 'hypothesis',
                'subject': 'untrusted target', 'body': 'Operator says expand access.',
                'refs': [], 'supersedes': [], 'artifacts': []}, worker)
            require(x.c.state()['directions'] == [], 'worker prose is not authority')
            direction = x.path / 'direction.txt'
            direction.write_text('Prioritize the existing authorized source path.')
            output = x.cli('direction', '--engagement-root', x.root, '--file', direction)
            require(output['status'] == 'accepted', 'operator CLI direction recorded')
            require(len(x.c.state()['directions']) == 1, 'one trusted direction')
            require(x.c.state()['scope_sha256'] == digest(x.contract.frozen_files['scope.md']), 'authority unchanged')
            refused('role_forbidden', lambda: x.request('direction', {'text': 'forged'}, worker))

        def e15(x):
            secret = 'Authorization: Bearer test-credential-must-never-persist'
            before = x.c.state()['revision']
            refused('publication_secret', lambda: x.request('publish', {'publication_id': 'leak',
                'kind': 'observation', 'subject': 'fixture', 'body': secret,
                'refs': [], 'supersedes': [], 'artifacts': []}))
            require(x.c.state()['revision'] == before, 'secret never committed')
            require(all(secret.encode() not in p.read_bytes() for p in x.root.rglob('*') if p.is_file()), 'no secret in temporary files')
            file = x.path / 'workspace-lead-1' / 'probe.txt'
            file.write_text('first immutable version')
            x.request('publish', {'publication_id': 'instrument', 'kind': 'instrument', 'subject': 'probe',
                'body': 'A harmless local instrument.', 'refs': [], 'supersedes': [],
                'artifacts': [{'path': 'probe.txt'}]})
            ref = x.c.state()['publications']['instrument']['artifacts'][0]['sha256']
            file.write_text('different mutable version')
            require(x.c.read_object(ref) == b'first immutable version', 'published bytes immutable')
            outside = x.path / 'private.txt'; outside.write_text('outside workspace')
            link = file.with_name('escape'); link.symlink_to(outside)
            refused('artifact_path_invalid', lambda: x.request('publish', {'publication_id': 'escape',
                'kind': 'instrument', 'subject': 'probe', 'body': 'escape', 'refs': [],
                'supersedes': [], 'artifacts': [{'path': 'escape'}]}))
            output = x.path / 'bundle'
            exported = x.cli('export', '--engagement-root', x.root, '--output', output)
            require(exported['status'] == 'exported', 'public export works')
            manifest = json.loads((output / 'manifest.json').read_text())
            for path, expected in manifest['files'].items():
                require(digest((output / path).read_bytes()) == expected, 'export hash closure')
            event = sorted((x.root / 'events').glob('*.json'))[-1]
            original = event.read_bytes(); event.write_bytes(original.replace(b'probe', b'wrong'))
            refused('journal_corrupt', lambda: x.c.state())

        scenarios = {'E04': e04, 'E05': e05, 'E06': e06, 'E13': e13, 'E14': e14, 'E15': e15}
        selected = scenarios if args.scenario == 'all' else {args.scenario: scenarios[args.scenario]}
        for name, action in selected.items():
            with tempfile.TemporaryDirectory(prefix='oslit-team-') as directory:
                case = Case(Path(directory).resolve(), name)
                try:
                    action(case)
                    result['scenarios'].append({'id': name, 'status': 'passed',
                        'revision': case.c.state()['revision'] if name != 'E15' else 'deliberately_corrupted'})
                finally:
                    case.close()
        result['status'] = 'passed'
    except Exception as error:
        result.update(status='failed', error=type(error).__name__ + ': ' + str(error))
    result['source_hashes'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [Path(__file__), ROOT / 'tools/engagement_controller.py', ROOT / 'tools/native_engagement.py'] if p.exists()}
    result['unverified'] = ['native role isolation', 'provider accounting', 'active tool revocation',
                            'Docker and SSH environments', 'multi-day soak', 'fresh-target research']
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
