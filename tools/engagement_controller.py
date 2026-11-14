"""The v2 engagement journal and authenticated worker interface.

Only the host imports this module. Workers reach a private endpoint bound to one
principal; a native session ID or submitted role never establishes identity.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import socket
import socketserver
import stat
import threading
import uuid

from engagement_contract import (ContractError, VerifiedInputs, canonical, digest,
                                 read_bytes, read_json, safe_publication, MAX_PUBLICATION_BYTES)

ID = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}\Z')
DIGEST = re.compile(r'sha256:[0-9a-f]{64}\Z')
EVENT_KEYS = {'kind', 'engagement_id', 'sequence', 'previous_sha256', 'at', 'actor',
              'request_id', 'request_sha256', 'type', 'payload', 'sha256'}
SUBMIT_TYPES = {'claim', 'publish', 'task_create', 'task_priority', 'task_assign',
                'worker_request', 'task_result', 'updates_ack'}
LEAD_TYPES = {'task_priority', 'task_assign', 'worker_request'}
GRANT_KEYS = {'dispatch_id', 'worker_id', 'generation', 'assignment', 'profile_id',
              'scope_sha256', 'seconds', 'resources', 'lease_expires_at', 'adapter_id'}


class ControllerError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def fail(code):
    raise ControllerError(code)


def identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        fail('identifier_invalid')
    return value


def keys(value, expected, code='payload_invalid'):
    if not isinstance(value, dict) or set(value) != set(expected):
        fail(code)


def integer(value, minimum=0, maximum=10**12):
    return type(value) is int and minimum <= value <= maximum


def instant(value):
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if result.tzinfo is None:
            fail('timestamp_invalid')
        return result
    except (ValueError, TypeError, AttributeError):
        fail('timestamp_invalid')


def private_directory(path):
    path = Path(path)
    try:
        info = path.lstat()
        if (not path.is_absolute() or path.resolve(strict=True) != path
                or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077):
            fail('private_root_invalid')
    except OSError:
        fail('private_root_invalid')
    return path


def overlap(left, right):
    return left == right or left in right.parents or right in left.parents


def publish_file(path, data):
    """Publish once; a complete file plus directory sync is the commit point."""
    temporary = path.with_name('.pending-' + uuid.uuid4().hex)
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        # All publishers hold the controller lock or own a newly created directory.
        if path.exists() or path.is_symlink():
            raise FileExistsError(path)
        os.rename(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


@dataclass(frozen=True)
class Principal:
    kind: str
    id: str
    generation: int = 0

    def record(self):
        return {'kind': self.kind, 'id': self.id, 'generation': self.generation}


class Controller:
    def __init__(self, root: Path, *, clock=None):
        self.root = private_directory(root)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._thread_lock = threading.RLock()
        self._lock_depth = 0

    @classmethod
    def initialize(cls, root: Path, contract: VerifiedInputs, *, evidence_class='native'):
        if evidence_class not in ('native', 'engineering_simulation'):
            fail('evidence_class_invalid')
        root = Path(root)
        if not root.is_absolute() or root.exists() or root.is_symlink():
            fail('engagement_root_exists_or_invalid')
        if root.parent.resolve(strict=True) != root.parent:
            fail('engagement_root_invalid')
        protected = [Path(value) for value in contract.inputs['access_files'].values()]
        protected.extend(Path(profile['tool_bundle']['path']) for profile in contract.runtime_profiles.values())
        if any(overlap(root, path) for path in protected):
            fail('engagement_root_overlap')
        root.mkdir(mode=0o700)
        c = cls(root)
        for directory in ('contract', 'events', 'objects', 'receipts'):
            (root / directory).mkdir(mode=0o700)
        files = {}
        for name, data in contract.frozen_files.items():
            relative = Path(name)
            if relative.is_absolute() or '..' in relative.parts:
                fail('contract_path_invalid')
            target = root / 'contract' / relative
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            safe_publication(data)
            publish_file(target, data)
            files[name] = digest(data)
        choices = [assignment for assignment in contract.scope['runtime_assignments']
                   if 'lead' in assignment['roles']]
        if not choices:
            fail('lead_runtime_missing')
        with c.lock():
            c._append([], Principal('operator', contract.scope['operator_id']), 'initialize',
                digest(canonical(contract.scope)), 'initialized',
                {'scope': contract.scope, 'scope_sha256': digest(contract.frozen_files['scope.md']),
                 'contract_files': files, 'evidence_class': evidence_class,
                 'lead_profile': choices[0]['profile_id']})
        return c

    @contextmanager
    def lock(self):
        with self._thread_lock:
            if self._lock_depth:
                self._lock_depth += 1
                try:
                    yield
                finally:
                    self._lock_depth -= 1
                return
            private_directory(self.root)
            fd = os.open(self.root / 'controller.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            try:
                info = os.fstat(fd)
                if info.st_uid != os.getuid() or info.st_mode & 0o077 or not stat.S_ISREG(info.st_mode):
                    fail('controller_lock_invalid')
                fcntl.flock(fd, fcntl.LOCK_EX)
                self._lock_depth = 1
                yield
            finally:
                self._lock_depth = 0
                os.close(fd)

    def _events(self):
        private_directory(self.root / 'events')
        entries = sorted((self.root / 'events').iterdir())
        events = []
        previous = None
        for path in entries:
            if path.name.startswith('.pending-'):
                continue
            if path.name != f'{len(events) + 1:012d}.json':
                fail('journal_corrupt')
            try:
                event = read_json(path, private=True)
                keys(event, EVENT_KEYS, 'journal_corrupt')
                content = {key: value for key, value in event.items() if key != 'sha256'}
                if (event['kind'] != 'engagement-event-v2'
                        or event['sequence'] != len(events) + 1
                        or event['previous_sha256'] != previous
                        or digest(canonical(content)) != event['sha256']):
                    fail('journal_corrupt')
            except (ContractError, ValueError, KeyError, TypeError):
                fail('journal_corrupt')
            events.append(event)
            previous = event['sha256']
        if not events or events[0]['type'] != 'initialized':
            fail('journal_corrupt')
        return events

    def _append(self, events, principal, request_id, request_sha, kind, payload):
        scope = payload['scope'] if kind == 'initialized' else events[0]['payload']['scope']
        event = {'kind': 'engagement-event-v2', 'engagement_id': scope['engagement_id'],
                 'sequence': len(events) + 1, 'previous_sha256': events[-1]['sha256'] if events else None,
                 'at': self.clock().isoformat(), 'actor': principal.record(),
                 'request_id': request_id, 'request_sha256': request_sha, 'type': kind, 'payload': payload}
        try:
            data = safe_publication(canonical(event))
        except ContractError:
            fail('publication_secret')
        event['sha256'] = digest(data)
        publish_file(self.root / 'events' / f'{event["sequence"]:012d}.json', canonical(event))
        return event

    def _replay(self, events):
        initial = events[0]['payload']
        scope = initial['scope']
        for name, sha in initial['contract_files'].items():
            try:
                if digest(read_bytes(self.root / 'contract' / name, private=True, max_bytes=MAX_PUBLICATION_BYTES)) != sha:
                    fail('contract_changed')
            except ContractError:
                fail('contract_changed')
        state = {'engagement_id': scope['engagement_id'], 'scope': scope,
                 'scope_sha256': initial['scope_sha256'], 'evidence_class': initial['evidence_class'],
                 'status': 'active', 'revision': 0, 'workers': {}, 'tasks': {}, 'publications': {},
                 'directions': [], 'dispatches': {}, 'resource_holds': {}, 'cleanup': 'pending',
                 'usage': {'invocations': 0, 'worker_seconds': 0, 'reserved_worker_seconds': 0,
                           'tokens': {}, 'cost': None, 'missing': ['billed_cost', 'provider_requests']}}
        seen = set()
        for event in events:
            if event['engagement_id'] != state['engagement_id']:
                fail('journal_corrupt')
            key = (canonical(event['actor']), event['request_id'])
            if key in seen:
                fail('journal_corrupt')
            seen.add(key)
            try:
                self._reduce(state, event)
            except (KeyError, TypeError, ValueError):
                fail('journal_corrupt')
            state['revision'] = event['sequence']
        for publication in state['publications'].values():
            for artifact in publication['artifacts']:
                self.read_object(artifact['sha256'])
        for event in events:
            if event['type'] == 'dispatch_observed':
                self.read_object(event['payload']['receipt'])
            elif event['type'] == 'effect_reconciled':
                self.read_object(event['payload']['evidence'])
        return state

    def state(self):
        with self.lock():
            return self._replay(self._events())

    def _reduce(self, state, event):
        payload, kind = event['payload'], event['type']
        if kind == 'initialized':
            state['workers']['lead-1'] = {'id': 'lead-1', 'role': 'lead', 'generation': 1,
                'profile_id': payload['lead_profile'], 'status': 'pending', 'assignment': None,
                'workspace': None, 'session_id': None, 'cursor': None}
        elif kind == 'worker_preparing':
            worker = state['workers'][payload['grant']['worker_id']]
            worker.update(status='preparing', workspace=payload['workspace'])
            grant = payload['grant']
            state['dispatches'][grant['dispatch_id']] = dict(grant, status='pending', receipt=None, preparation=True)
            state['usage']['invocations'] += 1
            state['usage']['reserved_worker_seconds'] += grant['seconds']
        elif kind == 'worker_session_observed':
            state['workers'][payload['worker_id']]['session_id'] = payload['session_id']
        elif kind == 'worker_revoked':
            worker = state['workers'][payload['worker_id']]
            worker.update(status='revoked', revoke_reason=payload['reason'])
            for dispatch in state['dispatches'].values():
                if dispatch['worker_id'] == worker['id'] and dispatch['generation'] == worker['generation'] and dispatch['status'] in ('pending', 'unknown'):
                    for resource in dispatch['resources']:
                        holds = state['resource_holds'].setdefault(resource, [])
                        if dispatch['dispatch_id'] not in holds:
                            holds.append(dispatch['dispatch_id'])
        elif kind == 'worker_started':
            worker = state['workers'][payload['worker_id']]
            worker.update(status='active', session_id=payload['session_id'], workspace=payload['workspace'])
        elif kind == 'request_accepted':
            self._reduce_request(state, event['actor']['id'], payload['type'], payload['payload'])
        elif kind == 'dispatch_intended':
            state['dispatches'][payload['dispatch_id']] = dict(payload, status='pending', receipt=None)
            state['usage']['invocations'] += 1
            state['usage']['reserved_worker_seconds'] += payload['seconds']
        elif kind == 'dispatch_observed':
            dispatch = state['dispatches'][payload['dispatch_id']]
            observation = payload['observation']
            dispatch.update(status=observation['status'], receipt=payload['receipt'],
                            adapter_id=payload['adapter_id'], observation=observation)
            if observation['status'] == 'settled':
                state['usage']['reserved_worker_seconds'] -= dispatch['seconds']
                state['usage']['worker_seconds'] += observation['worker_seconds']
                for key, amount in (observation['usage'].get('tokens') or {}).items():
                    state['usage']['tokens'][key] = state['usage']['tokens'].get(key, 0) + amount
            for resource, status in observation['resources'].items():
                holds = state['resource_holds'].get(resource, [])
                if status == 'unknown':
                    if payload['dispatch_id'] not in holds:
                        holds = [*holds, payload['dispatch_id']]
                else:
                    holds = [item for item in holds if item != payload['dispatch_id']]
                if holds:
                    state['resource_holds'][resource] = holds
                else:
                    state['resource_holds'].pop(resource, None)
        elif kind == 'effect_reconciled':
            for resource in payload['resources']:
                holds = state['resource_holds'].get(resource, [])
                state['resource_holds'][resource] = [item for item in holds if item != payload['dispatch_id']]
                if not state['resource_holds'][resource]:
                    del state['resource_holds'][resource]
        elif kind == 'direction_recorded':
            state['directions'].append(dict(payload, event_sequence=event['sequence']))
        elif kind == 'stop_requested':
            state['status'] = 'stopped'
            state['stop_reason'] = payload['reason']
            for worker in state['workers'].values():
                if worker['status'] in ('pending', 'preparing', 'active'):
                    worker['status'] = 'revoked'
            for dispatch in state['dispatches'].values():
                if dispatch['status'] in ('pending', 'unknown'):
                    for resource in dispatch['resources']:
                        holds = state['resource_holds'].setdefault(resource, [])
                        if dispatch['dispatch_id'] not in holds:
                            holds.append(dispatch['dispatch_id'])
        elif kind == 'worker_stop_observed':
            state['workers'][payload['worker_id']]['status'] = 'stopped'
        elif kind == 'cleanup_observed':
            state['cleanup'] = payload['status']
        else:
            fail('journal_corrupt')

    def _reduce_request(self, state, actor, kind, data):
        if kind == 'worker_request':
            state['workers'][data['worker_id']] = {'id': data['worker_id'], 'role': data['role'],
                'generation': 1, 'profile_id': data['profile_id'], 'status': 'pending',
                'question': data['question'], 'assignment': None, 'workspace': None,
                'session_id': None, 'cursor': None}
        elif kind == 'task_create':
            state['tasks'][data['task_id']] = dict(data, status='ready', owner=None,
                generation=0, created_order=len(state['tasks']))
        elif kind == 'task_priority':
            state['tasks'][data['task_id']]['priority'] = data['priority']
        elif kind in ('claim', 'task_assign'):
            task = state['tasks'][data['task_id']]
            task.update(status='assigned', owner=data['worker_id'], generation=task['generation'] + 1)
            state['workers'][data['worker_id']]['assignment'] = {'task_id': data['task_id'],
                                                               'generation': task['generation']}
        elif kind == 'publish':
            state['publications'][data['publication_id']] = dict(data, author=actor)
        elif kind == 'task_result':
            task = state['tasks'][data['task_id']]
            task.update(status=data['disposition'], result=data['result'], evidence_refs=data['evidence_refs'])
            state['workers'][actor]['assignment'] = None
        elif kind == 'updates_ack':
            state['workers'][actor]['cursor'] = data['cursor']
        else:
            fail('journal_corrupt')

    def _authority(self, state):
        if state['status'] != 'active':
            fail('engagement_stopped')
        expires = state['scope'].get('expires_at')
        if expires is not None and self.clock() >= instant(expires):
            fail('authority_expired')

    def _worker(self, state, principal):
        if principal.kind != 'worker':
            fail('worker_identity_required')
        worker = state['workers'].get(principal.id)
        if (worker is None or worker['generation'] != principal.generation
                or worker['status'] != 'active'):
            fail('worker_stale')
        return worker

    def _references(self, state, values):
        if not isinstance(values, list) or len(values) > 256:
            fail('references_invalid')
        for value in values:
            if not isinstance(value, str) or value not in state['publications']:
                fail('reference_missing')

    def _resources(self, state, values):
        allowed = {access['id'] for access in state['scope']['access']}
        if (not isinstance(values, list) or not all(isinstance(value, str) for value in values)
                or len(values) != len(set(values)) or not set(values) <= allowed):
            fail('resources_invalid')

    def _eligible(self, state, task):
        if task['status'] != 'ready':
            return False
        if any(state['tasks'][dependency]['status'] not in ('completed', 'reviewed_complete')
               for dependency in task['prerequisites']):
            return False
        if any(resource in state['resource_holds'] for resource in task['resources']):
            return False
        busy = {resource for other in state['tasks'].values() if other['status'] == 'assigned'
                for resource in other['resources']}
        pending = {resource for dispatch in state['dispatches'].values()
                   if dispatch['status'] in ('pending', 'unknown') for resource in dispatch['resources']}
        return not set(task['resources']) & (busy | pending)

    def _dispatch_resources(self, state, worker, resources):
        self._resources(state, resources)
        assignment = worker['assignment']
        if assignment is None:
            if resources and worker['role'] != 'lead':
                fail('assignment_required')
        else:
            task = state['tasks'][assignment['task_id']]
            if (task['status'] != 'assigned' or task['owner'] != worker['id']
                    or task['generation'] != assignment['generation']
                    or not set(resources) <= set(task['resources'])):
                fail('assignment_resource_forbidden')
        if any(task['status'] == 'assigned' and task['owner'] != worker['id']
               and set(resources) & set(task['resources']) for task in state['tasks'].values()):
            fail('resource_owned')

    def _validate_request(self, state, worker, kind, data):
        if kind in LEAD_TYPES and worker['role'] != 'lead':
            fail('role_forbidden')
        if kind not in SUBMIT_TYPES:
            fail('role_forbidden')
        if kind == 'worker_request':
            keys(data, ('worker_id', 'role', 'profile_id', 'question'))
            identifier(data['worker_id'])
            if data['worker_id'] in state['workers'] or data['role'] not in ('specialist', 'reviewer'):
                fail('worker_request_invalid')
            allowed = any(row['profile_id'] == data['profile_id'] and data['role'] in row['roles']
                          for row in state['scope']['runtime_assignments'])
            if not allowed:
                fail('runtime_assignment_forbidden')
            if sum(w['status'] in ('pending', 'preparing', 'active') for w in state['workers'].values()) >= state['scope']['limits']['max_workers']:
                fail('worker_limit')
            if not isinstance(data['question'], str) or not 1 <= len(data['question']) <= 8192:
                fail('question_invalid')
        elif kind == 'task_create':
            keys(data, ('task_id', 'question', 'priority', 'resources', 'prerequisites', 'evidence_refs'))
            identifier(data['task_id'])
            if data['task_id'] in state['tasks']:
                fail('task_exists')
            if not isinstance(data['question'], str) or not 1 <= len(data['question']) <= 8192:
                fail('question_invalid')
            if not integer(data['priority'], 0, 10**6) or (worker['role'] != 'lead' and data['priority'] != 0):
                fail('priority_forbidden')
            self._resources(state, data['resources'])
            if (not isinstance(data['prerequisites'], list) or len(data['prerequisites']) > 256
                    or any(item not in state['tasks'] for item in data['prerequisites'])):
                fail('prerequisite_missing')
            self._references(state, data['evidence_refs'])
        elif kind == 'task_priority':
            keys(data, ('task_id', 'priority'))
            if data['task_id'] not in state['tasks'] or not integer(data['priority'], 0, 10**6):
                fail('task_priority_invalid')
        elif kind in ('claim', 'task_assign'):
            keys(data, () if kind == 'claim' else ('task_id', 'worker_id'))
            assignee = worker if kind == 'claim' else state['workers'].get(data['worker_id'])
            if assignee is None or assignee['status'] not in (('active',) if kind == 'claim' else ('pending', 'active')) or assignee['assignment'] is not None:
                fail('worker_assignment_conflict')
            if kind == 'claim':
                tasks = sorted(state['tasks'].values(), key=lambda task: (-task['priority'], task['created_order']))
                task = next((task for task in tasks if self._eligible(state, task)), None)
            else:
                task = state['tasks'].get(data['task_id'])
                if task is not None and not self._eligible(state, task):
                    task = None
            if task is None:
                fail('no_ready_task')
            data = {'task_id': task['task_id'], 'worker_id': assignee['id']}
        elif kind == 'publish':
            keys(data, ('publication_id', 'kind', 'subject', 'body', 'refs', 'supersedes', 'artifacts'))
            identifier(data['publication_id'])
            if data['publication_id'] in state['publications']:
                fail('publication_exists')
            if data['kind'] not in ('observation', 'hypothesis', 'instrument', 'experiment', 'claim', 'challenge'):
                fail('publication_kind_invalid')
            if (not isinstance(data['subject'], str) or not 1 <= len(data['subject']) <= 1024
                    or not isinstance(data['body'], str) or not 1 <= len(data['body']) <= 65536):
                fail('publication_invalid')
            self._references(state, data['refs'])
            self._references(state, data['supersedes'])
            if not isinstance(data['artifacts'], list) or len(data['artifacts']) > 32:
                fail('artifacts_invalid')
            artifacts = []
            for item in data['artifacts']:
                keys(item, ('path',), 'artifact_path_invalid')
                path = Path(item['path'])
                if path.is_absolute() or '..' in path.parts or not path.parts:
                    fail('artifact_path_invalid')
                source = Path(worker['workspace']) / path
                try:
                    content = read_bytes(source, max_bytes=4 * 1024 * 1024)
                except ContractError:
                    fail('artifact_path_invalid')
                artifacts.append({'name': str(path), 'sha256': self.store_object(content), 'size': len(content)})
            data = dict(data, artifacts=artifacts)
        elif kind == 'task_result':
            keys(data, ('task_id', 'generation', 'disposition', 'result', 'evidence_refs'))
            task = state['tasks'].get(data['task_id'])
            if (task is None or task['owner'] != worker['id'] or task['generation'] != data['generation']
                    or worker['assignment'] != {'task_id': data['task_id'], 'generation': data['generation']}):
                fail('assignment_stale')
            if any(dispatch['worker_id'] == worker['id'] and dispatch['status'] in ('pending', 'unknown')
                   for dispatch in state['dispatches'].values()):
                fail('assignment_effect_unsettled')
            if data['disposition'] not in ('completed', 'blocked', 'deferred'):
                fail('task_result_invalid')
            if not isinstance(data['result'], str) or not 1 <= len(data['result']) <= 65536:
                fail('task_result_invalid')
            self._references(state, data['evidence_refs'])
        elif kind == 'updates_ack':
            keys(data, ('cursor',))
            self._cursor(state, self._events(), data['cursor'])
            if worker['cursor'] is not None:
                old = self._cursor(state, self._events(), worker['cursor'])
                if self._cursor(state, self._events(), data['cursor']) < old:
                    fail('cursor_regression')
        return data

    def submit(self, principal, request):
        if (not isinstance(principal, Principal) or principal.kind != 'worker'
                or not integer(principal.generation, 1)):
            fail('worker_identity_required')
        identifier(principal.id)
        keys(request, ('request_id', 'expected_revision', 'type', 'payload'), 'request_invalid')
        identifier(request['request_id'])
        if not integer(request['expected_revision']) or not isinstance(request['type'], str) or not isinstance(request['payload'], dict):
            fail('request_invalid')
        try:
            raw = safe_publication(canonical(request))
        except ContractError:
            fail('publication_secret')
        if len(raw) > 1024 * 1024:
            fail('request_invalid')
        request_sha = digest(raw)
        with self.lock():
            events = self._events()
            state = self._replay(events)
            for event in events:
                if event['actor'] == principal.record() and event['request_id'] == request['request_id']:
                    if event['request_sha256'] != request_sha:
                        fail('request_conflict')
                    return self._receipt(event)
            self._authority(state)
            worker = self._worker(state, principal)
            if request['expected_revision'] != state['revision']:
                fail('revision_conflict')
            data = self._validate_request(state, worker, request['type'], request['payload'])
            event = self._append(events, principal, request['request_id'], request_sha,
                                 'request_accepted', {'type': request['type'], 'payload': data})
            return self._receipt(event)

    @staticmethod
    def _receipt(event):
        return {'status': 'accepted', 'revision': event['sequence'], 'event_sha256': event['sha256'],
                'request_id': event['request_id'], 'result': event['payload']}

    def _host(self, kind, data, *, actor='controller', request_id=None):
        with self.lock():
            events = self._events()
            self._replay(events)
            event = self._append(events, Principal(actor, actor), request_id or uuid.uuid4().hex,
                                 digest(canonical(data)), kind, data)
            return self._receipt(event)

    def _workspace(self, state, workspace, worker_id):
        workspace = Path(workspace)
        inputs = read_json(self.root / 'contract/inputs.json', private=True)
        protected = [self.root, *[Path(value) for value in inputs['access_files'].values()]]
        for assignment in state['scope']['runtime_assignments']:
            profile = read_json(self.root / 'contract/runtimes' / (assignment['profile_id'] + '.json'), private=True)
            protected.append(Path(profile['tool_bundle']['path']))
        protected.extend(Path(other['workspace']) for other in state['workers'].values()
                         if other['workspace'] is not None and other['id'] != worker_id)
        if any(overlap(workspace, path) for path in protected):
            fail('worker_workspace_overlap')
        return private_directory(workspace)

    def _session(self, events, session_id):
        if not isinstance(session_id, str) or not 1 <= len(session_id) <= 256:
            fail('session_invalid')
        if any(event['type'] in ('worker_started', 'worker_session_observed') and
               event['payload']['session_id'] == session_id for event in events):
            fail('session_reused')

    def record_worker_started(self, worker_id, generation, session_id, workspace):
        with self.lock():
            events = self._events()
            state = self._replay(events)
            self._authority(state)
            worker = state['workers'].get(worker_id)
            if worker is None or worker['generation'] != generation or worker['status'] not in ('pending', 'preparing'):
                fail('worker_stale')
            workspace = self._workspace(state, workspace, worker_id)
            if worker['workspace'] is not None and worker['workspace'] != str(workspace):
                fail('worker_workspace_overlap')
            self._session(events, session_id)
            event = self._append(events, Principal('runtime', worker_id, generation), uuid.uuid4().hex,
                digest(canonical([worker_id, generation, session_id])), 'worker_started',
                {'worker_id': worker_id, 'generation': generation,
                 'session_id': session_id, 'workspace': str(workspace)})
            return self._receipt(event)

    def record_worker_session(self, worker_id, generation, session_id, *, reason):
        with self.lock():
            events = self._events()
            state = self._replay(events)
            self._authority(state)
            self._worker(state, Principal('worker', worker_id, generation))
            if any(d['worker_id'] == worker_id and d['status'] in ('pending', 'unknown') for d in state['dispatches'].values()):
                fail('session_dispatch_pending')
            self._session(events, session_id)
            if not isinstance(reason, str) or not 1 <= len(reason) <= 1024:
                fail('session_invalid')
            return self._host('worker_session_observed', {'worker_id': worker_id, 'generation': generation,
                'session_id': session_id, 'reason': reason})

    def _grant(self, state, worker, *, seconds, resources, adapter_id):
        limits, usage = state['scope']['limits'], state['usage']
        if not integer(seconds, 1, limits['max_worker_lease_seconds']):
            fail('reservation_invalid')
        self._dispatch_resources(state, worker, resources)
        if any(resource in state['resource_holds'] for resource in resources):
            fail('resource_held')
        if any(d['status'] in ('pending', 'unknown') and
               (d['worker_id'] == worker['id'] or set(d['resources']) & set(resources))
               for d in state['dispatches'].values()):
            fail('dispatch_conflict')
        if (usage['invocations'] >= limits['hard']['invocations'] or
                usage['worker_seconds'] + usage['reserved_worker_seconds'] + seconds > limits['hard']['worker_seconds']):
            fail('resource_exhausted')
        lease = self.clock() + timedelta(seconds=seconds)
        if state['scope'].get('expires_at') is not None:
            lease = min(lease, instant(state['scope']['expires_at']))
        return {'dispatch_id': uuid.uuid4().hex, 'worker_id': worker['id'], 'generation': worker['generation'],
            'assignment': worker['assignment'], 'profile_id': worker['profile_id'],
            'scope_sha256': state['scope_sha256'], 'seconds': seconds, 'resources': resources,
            'lease_expires_at': lease.isoformat(), 'adapter_id': identifier(adapter_id)}

    def prepare_dispatch(self, worker_id, generation, *, seconds, resources, adapter_id):
        with self.lock():
            events = self._events()
            state = self._replay(events)
            self._authority(state)
            worker = self._worker(state, Principal('worker', worker_id, generation))
            grant = self._grant(state, worker, seconds=seconds, resources=resources, adapter_id=adapter_id)
            self._append(events, Principal('controller', 'controller'), grant['dispatch_id'],
                         digest(canonical(grant)), 'dispatch_intended', grant)
            return grant

    def prepare_worker_dispatch(self, worker_id, generation, workspace, *, seconds, resources, adapter_id):
        with self.lock():
            events = self._events()
            state = self._replay(events)
            self._authority(state)
            worker = state['workers'].get(worker_id)
            if worker is None or worker['generation'] != generation or worker['status'] not in ('pending', 'preparing'):
                fail('worker_stale')
            workspace = self._workspace(state, workspace, worker_id)
            if worker['status'] == 'preparing':
                prior = next(d for d in state['dispatches'].values() if d.get('preparation') and
                             d['worker_id'] == worker_id and d['generation'] == generation)
                if worker['workspace'] != str(workspace) or any(prior[k] != v for k, v in
                        {'seconds': seconds, 'resources': resources, 'adapter_id': adapter_id}.items()):
                    fail('preparation_conflict')
                grant = {key: prior[key] for key in GRANT_KEYS}
                self._authorize(state, grant)
                return grant
            grant = self._grant(state, worker, seconds=seconds, resources=resources, adapter_id=adapter_id)
            self._append(events, Principal('controller', 'controller'), grant['dispatch_id'],
                digest(canonical(grant)), 'worker_preparing', {'grant': grant, 'workspace': str(workspace)})
            return grant

    def revoke_worker(self, worker_id, generation, *, reason):
        with self.lock():
            state = self._replay(self._events())
            worker = state['workers'].get(worker_id)
            if worker is None or worker['generation'] != generation:
                fail('worker_stale')
            if not isinstance(reason, str) or not 1 <= len(reason) <= 1024:
                fail('stop_reason_invalid')
            if worker['status'] in ('revoked', 'stopped'):
                return {'status': worker['status']}
            return self._host('worker_revoked', {'worker_id': worker_id, 'generation': generation, 'reason': reason})

    def authorize_dispatch(self, grant):
        state = self.state()
        return self._authorize(state, grant)

    @contextmanager
    def dispatch_guard(self, grant):
        with self.lock():
            state = self._replay(self._events())
            self._authorize(state, grant)
            yield

    def _authorize(self, state, grant):
        keys(grant, GRANT_KEYS, 'dispatch_identity_invalid')
        self._authority(state)
        worker = state['workers'].get(grant['worker_id'])
        if worker is None or worker['generation'] != grant['generation'] or worker['status'] not in ('active', 'preparing'):
            fail('worker_stale')
        dispatch = state['dispatches'].get(grant['dispatch_id'])
        if dispatch is None or canonical(grant) != canonical({key: dispatch[key] for key in GRANT_KEYS}):
            fail('dispatch_identity_invalid')
        if worker['status'] == 'preparing' and not dispatch.get('preparation'):
            fail('worker_stale')
        if dispatch['status'] != 'pending':
            fail('dispatch_settled')
        if worker['assignment'] != dispatch['assignment']:
            fail('assignment_stale')
        self._dispatch_resources(state, worker, grant['resources'])
        if self.clock() >= instant(dispatch['lease_expires_at']):
            fail('lease_expired')
        if any(resource in state['resource_holds'] for resource in grant['resources']):
            fail('resource_held')
        return True

    def store_object(self, content):
        try:
            safe_publication(content)
        except ContractError:
            fail('publication_secret')
        sha = digest(content)
        path = self.root / 'objects' / sha.removeprefix('sha256:')
        with self.lock():
            if path.exists():
                if read_bytes(path, private=True, max_bytes=4 * 1024 * 1024) != content:
                    fail('object_corrupt')
            else:
                publish_file(path, content)
        return sha

    def read_object(self, sha):
        if not isinstance(sha, str) or not DIGEST.fullmatch(sha):
            fail('object_reference_invalid')
        try:
            content = read_bytes(self.root / 'objects' / sha[7:], private=True, max_bytes=4 * 1024 * 1024)
        except ContractError:
            fail('object_unavailable')
        if digest(content) != sha:
            fail('object_corrupt')
        return content

    def store_receipt(self, grant, observation, *, adapter_id):
        keys(grant, GRANT_KEYS, 'receipt_identity_invalid')
        if adapter_id != grant['adapter_id']:
            fail('receipt_owner_invalid')
        document = {'kind': 'engagement-executor-receipt-v2', 'grant': grant,
                    'adapter_id': adapter_id, 'observation': observation}
        content = canonical(document)
        try:
            safe_publication(content)
        except ContractError:
            fail('publication_secret')
        with self.lock():
            state = self._replay(self._events())
            dispatch = state['dispatches'].get(grant['dispatch_id'])
            if dispatch is None or canonical(grant) != canonical({key: dispatch[key] for key in GRANT_KEYS}):
                fail('receipt_identity_invalid')
            path = self.root / 'receipts' / (grant['dispatch_id'] + '-' + digest(content)[7:] + '.json')
            if path.exists():
                if read_bytes(path, private=True) != content:
                    fail('receipt_conflict')
            else:
                publish_file(path, content)
        return path

    def adopt_receipt(self, dispatch_id, receipt_file, *, adapter_id):
        identifier(dispatch_id)
        receipt_file = Path(receipt_file)
        if receipt_file.parent != self.root / 'receipts':
            fail('receipt_path_invalid')
        try:
            content = read_bytes(receipt_file, private=True)
            receipt = json.loads(content, object_pairs_hook=unique_pairs)
            if canonical(receipt) != content:
                fail('receipt_invalid')
        except (ContractError, ValueError):
            fail('receipt_invalid')
        sha = digest(content)
        if receipt_file.name != dispatch_id + '-' + sha[7:] + '.json':
            fail('receipt_path_invalid')
        keys(receipt, ('kind', 'grant', 'adapter_id', 'observation'), 'receipt_invalid')
        keys(receipt['grant'], GRANT_KEYS, 'receipt_identity_invalid')
        with self.lock():
            events = self._events()
            state = self._replay(events)
            dispatch = state['dispatches'].get(dispatch_id)
            if (dispatch is None or receipt['kind'] != 'engagement-executor-receipt-v2'
                    or adapter_id != dispatch['adapter_id'] or receipt['adapter_id'] != adapter_id
                    or canonical(receipt['grant']) != canonical({key: dispatch[key] for key in GRANT_KEYS})):
                fail('receipt_identity_invalid')
            if any(event['type'] == 'dispatch_observed' and event['payload']['dispatch_id'] == dispatch_id
                   and event['payload']['receipt'] == sha for event in events):
                return {'status': 'adopted', 'receipt': sha}
            if dispatch['status'] == 'settled':
                fail('receipt_conflict')
            observation = receipt['observation']
            keys(observation, ('status', 'worker_seconds', 'resources', 'usage', 'cleanup'), 'receipt_invalid')
            if (observation['status'] not in ('settled', 'unknown')
                    or not integer(observation['worker_seconds'], 0, dispatch['seconds'])
                    or not isinstance(observation['resources'], dict)
                    or set(observation['resources']) != set(dispatch['resources'])
                    or any(value not in ('unchanged', 'reset', 'unknown') for value in observation['resources'].values())
                    or observation['cleanup'] not in ('pending', 'verified', 'unresolved')):
                fail('receipt_invalid')
            keys(observation['usage'], ('tokens', 'cost'), 'receipt_invalid')
            tokens = observation['usage']['tokens']
            if tokens is not None and (not isinstance(tokens, dict) or
                    any(key not in ('input', 'output', 'cached_input', 'cache_write', 'reasoning', 'total') or not integer(value)
                        for key, value in tokens.items())):
                fail('receipt_invalid')
            cost = observation['usage']['cost']
            if cost is not None and (type(cost) not in (int, float) or cost < 0):
                fail('receipt_invalid')
            prior = dispatch.get('observation')
            if prior is not None:
                previous_tokens = prior['usage']['tokens'] or {}
                previous_cost = prior['usage']['cost']
                if (observation['worker_seconds'] < prior['worker_seconds']
                        or any((tokens or {}).get(key, -1) < amount
                               for key, amount in previous_tokens.items())
                        or (previous_cost is not None and (cost is None or cost < previous_cost))):
                    fail('receipt_usage_regression')
            self.store_object(content)
            self._append(events, Principal('runtime', adapter_id), 'receipt-' + dispatch_id + '-' + sha[7:], sha,
                'dispatch_observed', {'dispatch_id': dispatch_id, 'receipt': sha,
                                      'adapter_id': adapter_id, 'observation': observation})
            return {'status': 'adopted', 'receipt': sha}

    def reconcile(self, dispatch_id, resources, *, adapter_id):
        with self.lock():
            events = self._events()
            state = self._replay(events)
            dispatch = state['dispatches'].get(dispatch_id)
            if dispatch is None or adapter_id != dispatch['adapter_id']:
                fail('receipt_owner_invalid')
            if not isinstance(resources, dict) or not set(resources) <= set(dispatch['resources']) or not resources:
                fail('readback_invalid')
            if any(value not in ('unchanged', 'reset') for value in resources.values()):
                fail('readback_invalid')
            data = {'dispatch_id': dispatch_id, 'resources': resources, 'adapter_id': adapter_id}
            evidence = self.store_object(canonical(data))
            event = self._append(events, Principal('environment', adapter_id), uuid.uuid4().hex,
                evidence, 'effect_reconciled', dict(data, evidence=evidence))
            return self._receipt(event)

    def direction(self, text):
        if not isinstance(text, str) or not 1 <= len(text) <= 65536:
            fail('direction_invalid')
        return self._host('direction_recorded', {'text': text, 'authority_changed': False}, actor='operator')

    def stop(self, reason):
        if not isinstance(reason, str) or not 1 <= len(reason) <= 1024:
            fail('stop_reason_invalid')
        if self.state()['status'] == 'stopped':
            return {'status': 'stopped', 'cleanup': self.state()['cleanup']}
        return self._host('stop_requested', {'reason': reason}, actor='operator')

    @staticmethod
    def _encode_cursor(state, event):
        value = [state['engagement_id'], event['sequence'], event['sha256']]
        return base64.urlsafe_b64encode(canonical(value)).decode().rstrip('=')

    def _cursor(self, state, events, cursor):
        if cursor is None:
            return 0
        try:
            value = json.loads(base64.urlsafe_b64decode(cursor + '=' * (-len(cursor) % 4)))
            if (not isinstance(value, list) or len(value) != 3 or value[0] != state['engagement_id']
                    or not integer(value[1], 1, len(events)) or value[2] != events[value[1] - 1]['sha256']):
                fail('cursor_invalid')
            return value[1]
        except (ValueError, TypeError, IndexError, UnicodeError):
            fail('cursor_invalid')

    def status(self, principal=None, *, since=None, limit=100):
        if not integer(limit, 1, 1000):
            fail('page_limit_invalid')
        with self.lock():
            events = self._events()
            state = self._replay(events)
            worker = self._worker(state, principal) if principal is not None else None
            start = self._cursor(state, events, since)
            updates = []
            page_bytes = 0
            for event in events[start:start + limit]:
                item = {key: event[key] for key in ('sequence', 'sha256', 'at', 'type', 'actor')}
                if event['type'] in ('request_accepted', 'direction_recorded', 'stop_requested'):
                    item['payload'] = event['payload']
                size = len(canonical(item))
                if updates and page_bytes + size > 512 * 1024:
                    break
                updates.append(item)
                page_bytes += size
            summary_limit = min(limit, 25)
            fields = {'tasks': ('task_id', 'status', 'owner', 'generation', 'priority'),
                      'publications': ('publication_id', 'kind', 'subject', 'author'),
                      'workers': ('id', 'role', 'generation', 'profile_id', 'status', 'assignment')}
            summaries = {name: {key: {field: row[field] for field in selected}
                                for key, row in list(state[name].items())[:summary_limit]}
                         for name, selected in fields.items()}
            end = start + len(updates)
            return {'status': state['status'], 'revision': state['revision'],
                'engagement_id': state['engagement_id'], 'evidence_class': state['evidence_class'],
                'assignment': worker['assignment'] if worker else None,
                **summaries, 'summary_counts': {name: len(state[name]) for name in fields},
                'summaries_truncated': {name: len(state[name]) > summary_limit for name in fields},
                'usage': state['usage'], 'resource_holds': state['resource_holds'], 'cleanup': state['cleanup'],
                'updates': updates, 'has_more': end < len(events),
                'next_cursor': self._encode_cursor(state, events[end - 1]) if updates else since}

    def export(self, output):
        output = Path(output)
        if not output.is_absolute() or output.exists() or output.is_symlink() or output.parent.resolve() != output.parent:
            fail('export_path_invalid')
        with self.lock():
            events = self._events()
            state = self._replay(events)
            files = {}
            for path in (self.root / 'contract').rglob('*'):
                if path.is_file():
                    files[str(path.relative_to(self.root))] = read_bytes(path, private=True, max_bytes=MAX_PUBLICATION_BYTES)
            for event in events:
                files[f'events/{event["sequence"]:012d}.json'] = canonical(event)
            for publication in state['publications'].values():
                for artifact in publication['artifacts']:
                    files['objects/' + artifact['sha256'][7:]] = self.read_object(artifact['sha256'])
            for event in events:
                if event['type'] in ('dispatch_observed', 'effect_reconciled'):
                    sha = event['payload']['receipt' if event['type'] == 'dispatch_observed' else 'evidence']
                    files['objects/' + sha[7:]] = self.read_object(sha)
            files['result.json'] = canonical({'engagement_id': state['engagement_id'],
                'scope_sha256': state['scope_sha256'], 'evidence_class': state['evidence_class'],
                'status': state['status'], 'claim_acceptance': 'not_established', 'tasks': state['tasks'],
                'directions': state['directions'], 'usage': state['usage'], 'cleanup': state['cleanup'],
                'resource_holds': state['resource_holds'], 'external_action_authorized': False})
            for data in files.values():
                try:
                    safe_publication(data)
                except ContractError:
                    fail('publication_secret')
            output.mkdir(mode=0o700)
            for name, data in files.items():
                path = output / name
                path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                publish_file(path, data)
            manifest = {'kind': 'engagement-result-bundle-v2', 'engagement_id': state['engagement_id'],
                'revision': state['revision'], 'files': {name: digest(data) for name, data in sorted(files.items())}}
            publish_file(output / 'manifest.json', canonical(manifest))
            return {'status': 'exported', 'output': str(output), 'revision': state['revision']}


class WorkerServer:
    """One isolated worker mount receives one socket; identity is a host closure."""
    def __init__(self, root, principal, path):
        self.path = Path(path)
        private_directory(self.path.parent)
        if self.path.exists() or self.path.is_symlink():
            fail('worker_socket_exists')
        controller = Controller(root)

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                self.request.settimeout(5)
                try:
                    line = self.rfile.readline(1024 * 1024 + 1)
                    if not line.endswith(b'\n') or len(line) > 1024 * 1024:
                        fail('request_invalid')
                    request = json.loads(line, object_pairs_hook=unique_pairs)
                    if request.get('operation') == 'status':
                        keys(request, ('operation', 'since', 'limit'), 'request_invalid')
                        result = controller.status(principal, since=request['since'], limit=request['limit'])
                    elif request.get('operation') == 'submit':
                        keys(request, ('operation', 'request'), 'request_invalid')
                        result = controller.submit(principal, request['request'])
                    else:
                        fail('request_invalid')
                except (ControllerError, ContractError) as error:
                    result = {'status': 'rejected', 'code': error.code}
                except (ValueError, TypeError, KeyError, OSError):
                    result = {'status': 'rejected', 'code': 'request_invalid'}
                self.wfile.write(canonical(result) + b'\n')

        self.server = socketserver.ThreadingUnixStreamServer(str(self.path), Handler)
        self.server.daemon_threads = True
        os.chmod(self.path, 0o600)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self):
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.path.unlink(missing_ok=True)


def unique_pairs(rows):
    value = {}
    for key, item in rows:
        if key in value:
            fail('request_invalid')
        value[key] = item
    return value


def worker_call(path, request):
    path = Path(path)
    if path.is_symlink() or path.parent.resolve(strict=True) != path.parent:
        fail('worker_socket_invalid')
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(10)
        client.connect(str(path))
        client.sendall(canonical(request) + b'\n')
        with client.makefile('rb') as stream:
            line = stream.readline(4 * 1024 * 1024 + 1)
        if not line.endswith(b'\n') or len(line) > 4 * 1024 * 1024:
            fail('worker_response_invalid')
        return json.loads(line, object_pairs_hook=unique_pairs)
