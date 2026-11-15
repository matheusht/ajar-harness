"""The v2 engagement journal and authenticated worker interface.

Only the host imports this module. Workers reach a private endpoint bound to one
principal; a native session ID or submitted role never establishes identity.
"""
from __future__ import annotations

import base64
import copy
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import fcntl
import json
import math
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
                'worker_request', 'task_result', 'updates_ack', 'team_message'}
LEAD_TYPES = {'task_priority', 'task_assign', 'worker_request'}
GRANT_KEYS = {'dispatch_id', 'worker_id', 'generation', 'assignment', 'profile_id',
              'scope_sha256', 'seconds', 'resources', 'lease_expires_at', 'adapter_id'}
BUNDLED_GUIDANCE = {name: Path(__file__).resolve().parents[1] / 'engine' / source
                    for name, source in (('methodology.md', 'native-engagement-method.md'),
                                         ('protocol.md', 'native-engagement-protocol.md'))}


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
        frozen = dict(contract.frozen_files)
        if set(frozen) & set(BUNDLED_GUIDANCE):
            fail('research_guidance_conflict')
        try:
            frozen.update({name: safe_publication(read_bytes(path, max_bytes=1024 * 1024))
                           for name, path in BUNDLED_GUIDANCE.items()})
        except ContractError:
            fail('research_guidance_unavailable')
        root.mkdir(mode=0o700)
        c = cls(root)
        for directory in ('contract', 'events', 'objects', 'receipts'):
            (root / directory).mkdir(mode=0o700)
        files = {}
        for name, data in frozen.items():
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
                 'provider_accounting': 'proxy-attempts-v1',
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
                 'status': 'active', 'revision': 0, 'workers': {}, 'tasks': {}, 'publications': {}, 'messages': {},
                 'directions': [], 'dispatches': {}, 'invocations': {}, 'provider_requests': {},
                 'resource_holds': {}, 'cleanup': 'pending',
                 'usage': {'invocations': 0, 'worker_seconds': 0, 'reserved_worker_seconds': 0,
                           'tokens': {}, 'cost': None, 'known_estimated_cost': 0,
                           'observed_token_dimensions': {}, 'cost_observations': 0,
                           'missing': ['billed_cost', 'provider_requests']}}
        from engagement_evidence import initialize as initialize_evidence
        initialize_evidence(state)
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
        for sha in state['evidence_objects']:
            self.read_object(sha)
        for publication in state['publications'].values():
            for artifact in publication['artifacts']:
                self.read_object(artifact['sha256'])
        for event in events:
            if event['type'] == 'dispatch_observed':
                self.read_object(event['payload']['receipt'])
            elif event['type'] == 'effect_reconciled':
                self.read_object(event['payload']['evidence'])
        state['usage']['native_invocations_admitted'] = len(state['invocations'])
        state['usage']['native_invocations_observed'] = sum(row['status'] not in ('pending', 'stopped_unobserved')
                                                         for row in state['invocations'].values())
        state['usage']['native_usage_incomplete'] = any(
            row['status'] in ('pending', 'stopped_unobserved') or
            'total' not in (row.get('usage', {}).get('tokens') or {})
            for row in state['invocations'].values())
        usage = state['usage']
        requests = list(state['provider_requests'].values())
        usage['provider_requests'] = len(requests)
        usage['provider_requests_completed'] = sum(row['status'] == 'completed' for row in requests)
        usage['provider_requests_unknown'] = sum(row['status'] != 'completed' for row in requests)
        usage['provider_requests_complete'] = initial.get('provider_accounting') == 'proxy-attempts-v1'
        if usage['provider_requests_complete']:
            usage['missing'].remove('provider_requests')
        usage['billed_cost'] = None
        usage['billed_cost_unavailable_reason'] = 'provider_billing_receipt_unavailable'
        usage['native_usage_observations'] = sum(row['status'] != 'pending' for row in state['invocations'].values())
        usage['native_token_totals_complete'] = bool(state['invocations']) and all(
            'total' in (row.get('usage', {}).get('tokens') or {}) for row in state['invocations'].values())
        usage['estimated_cost_complete'] = bool(state['invocations']) and all(
            row.get('usage', {}).get('cost') is not None for row in state['invocations'].values())
        usage['cost'] = usage['known_estimated_cost'] if usage['estimated_cost_complete'] else None
        for operation in state['environment_operations'].values():
            if (operation.get('result') or {}).get('status') != 'unknown':
                continue
            grant = operation['grant']
            environment = state['environments'][operation['identity']['nonce']]
            for resource in grant['resources']:
                if environment.get('cleanup') == 'verified':
                    from engagement_evidence import application_released
                    if not self._shared(state, [resource]) or application_released(state, grant['dispatch_id'], resource):
                        continue
                holds = state['resource_holds'].setdefault(resource, [])
                if grant['dispatch_id'] not in holds:
                    holds.append(grant['dispatch_id'])
        for operation in state['network_operations'].values():
            if operation['intent']['kind'] == 'acquisition-network-observation-v1':
                # Missing transfer readback remains an obligation, never a target-state hold.
                if operation['result'] is None or operation['result']['status'] == 'unknown':
                    state['cleanup'] = 'pending'
                continue
            dispatch = state['dispatches'][operation['grant']['dispatch_id']]
            result = operation['result']
            if operation.get('target_nonce') and state['environments'][operation['target_nonce']].get('cleanup') == 'verified':
                continue
            if ((result and result['status'] == 'unknown') or
                    (result is None and dispatch['status'] != 'pending')):
                holds = state['resource_holds'].setdefault(operation['intent']['access_id'], [])
                if dispatch['dispatch_id'] not in holds:
                    holds.append(dispatch['dispatch_id'])
        for artifact in state['lab_artifacts'].values():
            if artifact['state'] == 'clean':
                continue
            state['cleanup'] = 'pending'
            if state['dispatches'][artifact['dispatch_id']]['status'] != 'pending':
                for resource in artifact['resources']:
                    holds = state['resource_holds'].setdefault(resource, [])
                    if artifact['dispatch_id'] not in holds:
                        holds.append(artifact['dispatch_id'])
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
            state['cleanup'] = 'pending'
            worker = state['workers'][payload['grant']['worker_id']]
            worker.update(status='preparing', workspace=payload['workspace'])
            grant = payload['grant']
            state['dispatches'][grant['dispatch_id']] = dict(grant, status='pending', receipt=None, preparation=True)
            state['usage']['invocations'] += 1
            state['usage']['reserved_worker_seconds'] += grant['seconds']
        elif kind == 'worker_session_observed':
            state['workers'][payload['worker_id']].update(session_id=payload['session_id'], runtime_owner_sha256=payload.get('runtime_owner_sha256'))
            if payload.get('runtime_owner_sha256'):
                state['evidence_objects'][payload['runtime_owner_sha256']] = True
        elif kind == 'preparation_setup_started':
            state['dispatches'][payload['dispatch_id']]['setup_started_at'] = event['at']
        elif kind == 'preparation_native_admitted':
            state['dispatches'][payload['dispatch_id']]['native_admitted'] = True
        elif kind in ('preparation_cancelled', 'preparation_settled'):
            dispatch = state['dispatches'][payload['dispatch_id']]
            sha = payload['receipt_sha256']
            dispatch.update(status='settled', receipt=sha)
            dispatch['cancelled_receipt' if kind == 'preparation_cancelled' else 'setup_receipt'] = sha
            worker = state['workers'][dispatch['worker_id']]
            worker.update(status='stopped', stop_receipt=sha)
            state['evidence_objects'][sha] = True
            state['usage']['reserved_worker_seconds'] -= dispatch['seconds']
            state['usage']['invocations'] -= 1
            state['usage']['worker_seconds'] += payload.get('worker_seconds', 0)
            for nonce in payload.get('environment_nonces', []):
                state['environments'][nonce].update(stopped=True, cleanup='verified', cleanup_receipt=sha)
            for resource in dispatch['resources']:
                holds = [value for value in state['resource_holds'].get(resource, []) if value != dispatch['dispatch_id']]
                if holds:
                    state['resource_holds'][resource] = holds
                else:
                    state['resource_holds'].pop(resource, None)
            if (all(row.get('cleanup') == 'verified' for row in state['environments'].values())
                    and all(row['status'] == 'stopped' for row in state['workers'].values())):
                state['cleanup'] = 'verified'
        elif kind == 'runtime_preparation_owner':
            sha = payload['receipt_sha256']
            state['dispatches'][payload['dispatch_id']].setdefault('runtime_owner_receipts', []).append(sha)
            state['workers'][payload['worker_id']].update(runtime_owner_sha256=sha, session_id=payload['session_id'])
            state['evidence_objects'][sha] = True
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
            state['cleanup'] = 'pending'
            worker = state['workers'][payload['worker_id']]
            worker.update(status='active', session_id=payload['session_id'], workspace=payload['workspace'],
                          runtime_owner_sha256=payload.get('runtime_owner_sha256'))
            if payload.get('runtime_owner_sha256'):
                state['evidence_objects'][payload['runtime_owner_sha256']] = True
        elif kind == 'request_accepted':
            self._reduce_request(state, event['actor']['id'], payload['type'], payload['payload'])
        elif kind == 'task_claimed':
            self._reduce_request(state, payload['worker_id'], 'claim', payload)
        elif kind == 'worker_resumed':
            worker = state['workers'][payload['worker_id']]
            worker.setdefault('history', []).append({key: value for key, value in worker.items() if key != 'history'})
            worker.update(generation=worker['generation'] + 1, status='pending', workspace=None,
                          session_id=None, runtime_owner_sha256=None, resume_reason=payload['reason'])
            worker.pop('stop_receipt', None)
        elif kind == 'dispatch_intended':
            state['dispatches'][payload['dispatch_id']] = dict(payload, status='pending', receipt=None)
            state['usage']['invocations'] += 1
            state['usage']['reserved_worker_seconds'] += payload['seconds']
        elif kind == 'capture_intended':
            grant = payload['grant']
            state['dispatches'][grant['dispatch_id']] = dict(grant, status='pending', receipt=None,
                parent_dispatch_id=payload['parent_dispatch_id'], session_id=payload['session_id'])
            state['usage']['reserved_worker_seconds'] += grant['seconds']
        elif kind == 'dispatch_renewed':
            dispatch = state['dispatches'][payload['grant']['dispatch_id']]
            dispatch.setdefault('prior_grants', []).append(payload['previous'])
            state['usage']['reserved_worker_seconds'] += payload['grant']['seconds'] - dispatch['seconds']
            dispatch.update(payload['grant'])
        elif kind == 'invocation_intended':
            dispatch = state['dispatches'][payload['dispatch_id']]
            if dispatch.get('invocations'):
                state['usage']['invocations'] += 1
            dispatch.setdefault('invocations', []).append(payload['invocation_id'])
            state['invocations'][payload['invocation_id']] = dict(payload, status='pending')
        elif kind == 'invocation_observed':
            invocation = state['invocations'][payload['invocation_id']]
            invocation.update(payload['observation'])
            self._accumulate_usage(state['usage'], payload['observation']['usage'])
        elif kind == 'provider_request_started':
            state['provider_requests'][payload['request_id']] = dict(payload, status='started')
        elif kind == 'provider_request_finished':
            state['provider_requests'][payload['request_id']]['status'] = payload['status']
        elif kind == 'task_outcome_pending':
            state['workers'][payload['worker_id']]['outcome_pending'] = payload['request']
        elif kind == 'task_outcome_finalized':
            worker = state['workers'][payload['worker_id']]
            self._reduce_request(state, worker['id'], 'task_result', worker.pop('outcome_pending')['payload'])
        elif kind == 'specialist_continued':
            worker = state['workers'][payload['grant']['worker_id']]
            self._reduce_request(state, worker['id'], 'task_result', worker.pop('outcome_pending')['payload'])
            self._reduce_request(state, worker['id'], 'claim', {'task_id': payload['grant']['assignment']['task_id'],
                                                             'worker_id': worker['id']})
            dispatch = state['dispatches'][payload['grant']['dispatch_id']]
            dispatch.setdefault('prior_grants', []).append(payload['previous'])
            dispatch.update(payload['grant'])
        elif kind == 'runtime_stop_observed':
            state['workers'][payload['worker_id']].update(status='stopped', stop_receipt=payload['receipt'])
            state['evidence_objects'][payload['receipt']] = True
            if not state['environments'] and all(row['status'] == 'stopped' for row in state['workers'].values()):
                state['cleanup'] = 'verified'
        elif kind == 'dispatch_observed':
            dispatch = state['dispatches'][payload['dispatch_id']]
            observation = payload['observation']
            dispatch.update(status=observation['status'], receipt=payload['receipt'],
                            adapter_id=payload['adapter_id'], observation=observation)
            if observation['status'] == 'settled':
                state['usage']['reserved_worker_seconds'] -= dispatch['seconds']
                state['usage']['worker_seconds'] += observation['worker_seconds']
                if not dispatch.get('invocations'):
                    self._accumulate_usage(state['usage'], observation['usage'])
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
        elif kind in ('stop_requested', 'closure_stopping'):
            state['status'] = 'closing' if kind == 'closure_stopping' else 'stopped'
            state['stop_reason'] = payload['reason']
            if kind == 'closure_stopping':
                state['closing_id'] = payload['closure_id']
            for worker in state['workers'].values():
                if worker['status'] in ('pending', 'preparing', 'active'):
                    dispatched = any(row['worker_id'] == worker['id'] and row['generation'] == worker['generation']
                                     for row in state['dispatches'].values())
                    untouched = worker['status'] == 'pending' and not dispatched and not worker.get('runtime_owner_sha256')
                    worker['status'] = 'stopped' if untouched else 'revoked'
            for dispatch in state['dispatches'].values():
                if dispatch['status'] in ('pending', 'unknown'):
                    for resource in dispatch['resources']:
                        holds = state['resource_holds'].setdefault(resource, [])
                        if dispatch['dispatch_id'] not in holds:
                            holds.append(dispatch['dispatch_id'])
            if not state['environments'] and all(row['status'] == 'stopped' for row in state['workers'].values()):
                state['cleanup'] = 'verified'
        elif kind == 'evidence_recorded':
            from engagement_evidence import reduce_host
            reduce_host(state, payload)
        elif kind == 'worker_stop_observed':
            state['workers'][payload['worker_id']]['status'] = 'stopped'
        elif kind == 'cleanup_observed':
            state['cleanup'] = payload['status']
        else:
            fail('journal_corrupt')

    def _reduce_request(self, state, actor, kind, data):
        from engagement_evidence import REQUESTS, reduce_request
        if kind in REQUESTS:
            reduce_request(state, actor, kind, data)
            return
        if kind == 'worker_request':
            state['workers'][data['worker_id']] = {'id': data['worker_id'], 'role': data['role'],
                'generation': 1, 'profile_id': data['profile_id'], 'status': 'pending',
                'question': data['question'], 'assignment': None, 'workspace': None,
                'session_id': None, 'cursor': None}
        elif kind == 'task_create':
            state['tasks'][data['task_id']] = dict(data, status='ready', owner=None,
                generation=0, created_order=len(state['tasks']))
            for closure in state['closures'].values():
                if closure['state'] == 'reviewed':
                    closure['state'] = 'reopened'
                    state['reviews'][closure['review_id']]['status'] = 'stale'
        elif kind == 'task_priority':
            state['tasks'][data['task_id']]['priority'] = data['priority']
        elif kind in ('claim', 'task_assign'):
            task = state['tasks'][data['task_id']]
            task.update(status='assigned', owner=data['worker_id'], generation=task['generation'] + 1)
            state['workers'][data['worker_id']]['assignment'] = {'task_id': data['task_id'],
                                                               'generation': task['generation']}
        elif kind == 'publish':
            state['publications'][data['publication_id']] = dict(data, author=actor)
            from engagement_evidence import invalidate
            invalidate(state, data['supersedes'])
        elif kind == 'team_message':
            state['messages'][data['message_id']] = dict(data, author=actor)
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

    def _shared(self, state, resources):
        shared = {row['id'] for row in state['scope']['access'] if row['kind'] == 'application'}
        return set(resources) & shared

    def _held(self, state, worker, resources):
        for resource in resources:
            for dispatch_id in state['resource_holds'].get(resource, []):
                dispatch = state['dispatches'][dispatch_id]
                if self._shared(state, [resource]) or (dispatch['worker_id'] == worker['id'] and
                                                       dispatch['generation'] == worker['generation']):
                    return True
        return False

    def _eligible(self, state, task, worker):
        if task['status'] != 'ready':
            return False
        if any(state['tasks'][dependency]['status'] not in ('completed', 'reviewed_complete')
               for dependency in task['prerequisites']):
            return False
        if self._held(state, worker, task['resources']):
            return False
        busy = {resource for other in state['tasks'].values() if other['status'] == 'assigned'
                for resource in self._shared(state, other['resources'])}
        pending = {resource for dispatch in state['dispatches'].values()
                   if dispatch['status'] in ('pending', 'unknown') and not (
                       dispatch['status'] == 'pending' and dispatch['worker_id'] == worker['id']
                       and worker['assignment'] is None and dispatch.get('invocations')
                       and not dispatch.get('parent_dispatch_id')) for resource in
                   (dispatch['resources'] if dispatch['worker_id'] == worker['id'] else self._shared(state, dispatch['resources']))}
        return not set(task['resources']) & (busy | pending)

    def _dispatch_resources(self, state, worker, resources):
        self._resources(state, resources)
        review = next((row for row in state['reviews'].values() if row['reviewer_id'] == worker['id'] and row['status'] == 'pending'), None)
        if worker['role'] != 'reviewer' and any(row['state'] in ('pending', 'disputed') and set(resources) & set(row['resources']) for row in state['obligations'].values()):
            fail('direction_held')
        assignment = worker['assignment']
        if assignment is None:
            if resources and worker['role'] != 'lead' and not (review and set(resources) <= set(review['resources'])):
                fail('assignment_required')
        else:
            task = state['tasks'][assignment['task_id']]
            if (task['status'] != 'assigned' or task['owner'] != worker['id']
                    or task['generation'] != assignment['generation']
                    or not set(resources) <= set(task['resources'])):
                fail('assignment_resource_forbidden')
        if any(task['status'] == 'assigned' and task['owner'] != worker['id']
               and self._shared(state, resources) & set(task['resources']) for task in state['tasks'].values()):
            fail('resource_owned')

    def _validate_request(self, state, worker, kind, data):
        from engagement_evidence import REQUESTS, validate_request
        if kind in REQUESTS:
            return validate_request(self, state, worker, kind, data)
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
                task = next((task for task in tasks if self._eligible(state, task, assignee)), None)
            else:
                task = state['tasks'].get(data['task_id'])
                if task is not None and not self._eligible(state, task, assignee):
                    task = None
            if task is None:
                fail('no_ready_task')
            data = {'task_id': task['task_id'], 'worker_id': assignee['id']}
        elif kind == 'team_message':
            keys(data, ('message_id', 'recipient_ids', 'subject', 'body', 'refs'))
            identifier(data['message_id'])
            if data['message_id'] in state['messages']:
                fail('message_exists')
            recipients = data['recipient_ids']
            if (not isinstance(recipients, list) or not 1 <= len(recipients) <= 16 or
                    any(not isinstance(name, str) or name not in state['workers'] or
                        state['workers'][name]['status'] not in ('pending', 'preparing', 'active') for name in recipients) or
                    len(recipients) != len(set(recipients))):
                fail('message_recipient_invalid')
            if (not isinstance(data['subject'], str) or not 1 <= len(data['subject']) <= 1024 or
                    not isinstance(data['body'], str) or not 1 <= len(data['body']) <= 8192):
                fail('message_invalid')
            self._references(state, data['refs'])
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
            if worker.get('outcome_pending'):
                fail('worker_finishing')
            if request['expected_revision'] != state['revision']:
                fail('revision_conflict')
            data = self._validate_request(state, worker, request['type'], request['payload'])
            if request['type'] == 'task_result' and any(dispatch['worker_id'] == worker['id'] and
                    dispatch['status'] in ('pending', 'unknown') for dispatch in state['dispatches'].values()):
                event = self._append(events, principal, request['request_id'], request_sha,
                    'task_outcome_pending', {'worker_id': worker['id'], 'request': request})
                return self._receipt(event)
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

    def record_runtime_preparation_owner(self, grant, receipt):
        from engagement_evidence import runtime_owner
        with self.lock():
            state = self.state()
            dispatch = self.bind_grant(state, grant)
            worker = state['workers'][grant['worker_id']]
            if worker['status'] == 'active':
                self._authorize(state, grant)
                sha = digest(canonical(receipt))
                if sha != worker.get('runtime_owner_sha256') or sha not in dispatch.get('runtime_owner_receipts', []):
                    fail('worker_stale')
                return {'status': 'recorded', 'receipt': sha}
            if worker['generation'] != grant['generation'] or worker['status'] != 'preparing':
                fail('worker_stale')
            if not isinstance(receipt, dict):
                fail('runtime_owner_invalid')
            sha = runtime_owner(self, state, worker, receipt.get('session_id'), receipt, preparing=True)
            if worker.get('runtime_owner_sha256') and receipt.get('kind') == 'native-runtime-owner-v2':
                from native_runtime_linux import require_monotonic_owner
                from native_runtime_transport import RuntimeError as NativeRuntimeError
                prior = json.loads(self.read_object(worker['runtime_owner_sha256']))
                try:
                    require_monotonic_owner(prior, receipt)
                except (ValueError, KeyError, TypeError, NativeRuntimeError):
                    fail('runtime_owner_changed')
            if sha in dispatch.get('runtime_owner_receipts', []):
                return {'status': 'recorded', 'receipt': sha}
            if worker.get('runtime_owner_sha256'):
                prior = json.loads(self.read_object(worker['runtime_owner_sha256']))
                if any(receipt.get(key) != prior[key] for key in ('process', 'bridge_process') if key in prior):
                    fail('runtime_owner_changed')
            return self._host('runtime_preparation_owner', {'worker_id': worker['id'],
                'dispatch_id': grant['dispatch_id'], 'receipt_sha256': sha, 'session_id': receipt['session_id']})

    def record_worker_started(self, worker_id, generation, session_id, workspace, *, owner_receipt=None):
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
            from engagement_evidence import runtime_owner
            owner_sha = runtime_owner(self, state, worker, session_id, owner_receipt)
            event = self._append(events, Principal('runtime', worker_id, generation), uuid.uuid4().hex,
                digest(canonical([worker_id, generation, session_id])), 'worker_started',
                {'worker_id': worker_id, 'generation': generation,
                 'session_id': session_id, 'workspace': str(workspace), 'runtime_owner_sha256': owner_sha})
            return self._receipt(event)

    def record_worker_session(self, worker_id, generation, session_id, *, reason, owner_receipt=None):
        with self.lock():
            events = self._events()
            state = self._replay(events)
            self._authority(state)
            worker = self._worker(state, Principal('worker', worker_id, generation))
            if any(d['worker_id'] == worker_id and d['status'] in ('pending', 'unknown') for d in state['dispatches'].values()):
                fail('session_dispatch_pending')
            self._session(events, session_id)
            if not isinstance(reason, str) or not 1 <= len(reason) <= 1024:
                fail('session_invalid')
            from engagement_evidence import runtime_owner
            owner_sha = runtime_owner(self, state, worker, session_id, owner_receipt)
            return self._host('worker_session_observed', {'worker_id': worker_id, 'generation': generation,
                'session_id': session_id, 'reason': reason, 'runtime_owner_sha256': owner_sha})

    def _grant(self, state, worker, *, seconds, resources, adapter_id, parent=None):
        limits, usage = state['scope']['limits'], state['usage']
        if not integer(seconds, 1, limits['max_worker_lease_seconds']):
            fail('reservation_invalid')
        self._dispatch_resources(state, worker, resources)
        if self._held(state, worker, resources):
            fail('resource_held')
        if sum(d['status'] in ('pending', 'unknown') for d in state['dispatches'].values()) >= limits['max_workers']:
            fail('resource_exhausted')
        if any(d['status'] in ('pending', 'unknown') and d['dispatch_id'] != parent and
               (d['worker_id'] == worker['id'] or self._shared(state, d['resources']) & set(resources))
               for d in state['dispatches'].values()):
            fail('dispatch_conflict')
        if ((parent is None and usage['invocations'] >= limits['hard']['invocations']) or
                usage['worker_seconds'] + usage['reserved_worker_seconds'] + seconds > limits['hard']['worker_seconds']):
            fail('resource_exhausted')
        lease = self.clock() + timedelta(seconds=seconds)
        if state['scope'].get('expires_at') is not None:
            lease = min(lease, instant(state['scope']['expires_at']))
        return {'dispatch_id': uuid.uuid4().hex, 'worker_id': worker['id'], 'generation': worker['generation'],
            'assignment': worker['assignment'], 'profile_id': worker['profile_id'],
            'scope_sha256': state['scope_sha256'], 'seconds': seconds, 'resources': resources,
            'lease_expires_at': lease.isoformat(), 'adapter_id': identifier(adapter_id)}

    def prepare_capture_dispatch(self, parent_grant, *, seconds, resources):
        with self.lock():
            state = self.state()
            self._authorize(state, parent_grant)
            parent = state['dispatches'][parent_grant['dispatch_id']]
            if parent.get('parent_dispatch_id'):
                fail('capture_parent_invalid')
            self._resources(state, resources)
            if not set(resources) <= set(parent_grant['resources']):
                fail('capture_resources_unavailable')
            if any(d.get('parent_dispatch_id') == parent_grant['dispatch_id'] and
                    d['status'] in ('pending', 'unknown') for d in state['dispatches'].values()):
                fail('capture_in_progress')
            worker = self._worker(state, Principal('worker', parent_grant['worker_id'], parent_grant['generation']))
            grant = self._grant(state, worker, seconds=seconds, resources=resources,
                adapter_id=parent_grant['adapter_id'], parent=parent_grant['dispatch_id'])
            grant['lease_expires_at'] = min(instant(grant['lease_expires_at']),
                                           instant(parent_grant['lease_expires_at'])).isoformat()
            self._host('capture_intended', {'grant': grant, 'parent_dispatch_id': parent_grant['dispatch_id'],
                                            'session_id': worker['session_id']})
            return grant

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

    def resume_worker(self, worker_id, generation, *, reason):
        with self.lock():
            state = self.state()
            self._authority(state)
            worker = state['workers'].get(worker_id)
            if (worker is None or worker['generation'] != generation or worker['status'] != 'stopped'
                    or not worker.get('stop_receipt') or worker.get('outcome_pending')
                    or any(row['worker_id'] == worker_id and row['status'] != 'settled'
                           for row in state['dispatches'].values())):
                fail('worker_resume_unsettled')
            if reason not in ('controller_resume', 'next_task', 'review_obligation'):
                fail('worker_resume_reason_invalid')
            return self._host('worker_resumed', {'worker_id': worker_id, 'generation': generation, 'reason': reason})

    def claim_ready_task(self, worker_id, generation):
        with self.lock():
            state = self.state()
            self._authority(state)
            worker = state['workers'].get(worker_id)
            if (worker is None or worker['generation'] != generation or worker['role'] != 'specialist'
                    or worker['status'] != 'pending' or worker['assignment'] is not None):
                fail('worker_assignment_conflict')
            tasks = sorted(state['tasks'].values(), key=lambda task: (-task['priority'], task['created_order']))
            task = next((row for row in tasks if self._eligible(state, row, worker)), None)
            if task is None:
                return {'status': 'no_ready_task'}
            return self._host('task_claimed', {'task_id': task['task_id'], 'worker_id': worker_id})

    def continue_specialist(self, grant):
        """Keep an idle native owner for the next task without changing its authority."""
        with self.lock():
            state = self.state()
            self._authorize(state, grant)
            worker = state['workers'][grant['worker_id']]
            outcome = worker.get('outcome_pending')
            if (worker['role'] != 'specialist' or worker['status'] != 'active' or not outcome
                    or outcome['payload']['disposition'] != 'completed' or not worker.get('runtime_owner_sha256')
                    or not worker.get('session_id') or worker['profile_id'] != grant['profile_id']):
                return None
            dispatch = state['dispatches'][grant['dispatch_id']]
            invocations = [state['invocations'][name] for name in dispatch.get('invocations', [])]
            if (not invocations or invocations[-1]['status'] != 'completed'
                    or any(row['status'] == 'pending' for row in invocations)):
                return None
            owned = {name for name, row in state['dispatches'].items()
                if row['worker_id'] == worker['id'] and row['generation'] == worker['generation']}
            if any(name != grant['dispatch_id'] and state['dispatches'][name]['status'] != 'settled' for name in owned):
                return None
            for operation in state['network_operations'].values():
                if operation['grant']['dispatch_id'] in owned and (operation.get('result') or {}).get('status') != 'settled':
                    return None
            for operation in state['environment_operations'].values():
                if operation['grant']['dispatch_id'] not in owned:
                    continue
                environment = state['environments'][operation['identity']['nonce']]
                if environment['identity']['unsettled'] or environment.get('cleanup') == 'unresolved':
                    return None
                result = operation.get('result') or {}
                if result.get('status') == 'settled':
                    continue
                role = operation.get('intent', {}).get('role')
                if (operation['operation'] == 'launch_stdio' and result.get('status') == 'dispatched'
                        and role in ('native_tools', 'network_proxy') and result.get('role') == role
                        and (operation['grant']['dispatch_id'] == grant['dispatch_id'] or
                             environment.get('cleanup') == 'verified')):
                    continue
                return None
            projected = copy.deepcopy(state)
            self._reduce_request(projected, worker['id'], 'task_result', outcome['payload'])
            projected_worker = projected['workers'][worker['id']]
            tasks = sorted(projected['tasks'].values(), key=lambda row: (-row['priority'], row['created_order']))
            task = next((row for row in tasks if self._eligible(projected, row, projected_worker)), None)
            if task is None or set(task['resources']) != set(grant['resources']):
                return None
            self._reduce_request(projected, worker['id'], 'claim', {'task_id': task['task_id'], 'worker_id': worker['id']})
            self._dispatch_resources(projected, projected_worker, grant['resources'])
            continued = dict(grant, assignment=projected_worker['assignment'])
            self._host('specialist_continued', {'previous': grant, 'grant': continued})
            return continued

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
        parent_id = dispatch.get('parent_dispatch_id')
        if parent_id:
            parent = state['dispatches'][parent_id]
            self._authorize(state, {key: parent[key] for key in GRANT_KEYS})
        if worker['assignment'] != dispatch['assignment']:
            fail('assignment_stale')
        self._dispatch_resources(state, worker, grant['resources'])
        if self.clock() >= instant(dispatch['lease_expires_at']):
            fail('lease_expired')
        if self._held(state, worker, grant['resources']):
            fail('resource_held')
        return True

    def bind_grant(self, state, grant):
        keys(grant, GRANT_KEYS, 'dispatch_identity_invalid')
        dispatch = state['dispatches'].get(grant['dispatch_id'])
        if dispatch is None or grant not in [
                {key: dispatch[key] for key in GRANT_KEYS}, *dispatch.get('prior_grants', [])]:
            fail('dispatch_identity_invalid')
        return dispatch

    def renew_dispatch(self, grant, *, seconds):
        with self.lock():
            state = self.state()
            self._authorize(state, grant)
            limits, usage = state['scope']['limits'], state['usage']
            if not integer(seconds, 1, limits['max_worker_lease_seconds']):
                fail('reservation_invalid')
            expiry = self.clock() + timedelta(seconds=seconds)
            if state['scope'].get('expires_at'):
                expiry = min(expiry, instant(state['scope']['expires_at']))
            parent = state['dispatches'][grant['dispatch_id']].get('parent_dispatch_id')
            if parent:
                expiry = min(expiry, instant(state['dispatches'][parent]['lease_expires_at']))
            extra = max(0, math.ceil((expiry - instant(grant['lease_expires_at'])).total_seconds()))
            if extra == 0:
                return grant
            if usage['worker_seconds'] + usage['reserved_worker_seconds'] + extra > limits['hard']['worker_seconds']:
                fail('resource_exhausted')
            renewed = dict(grant, seconds=grant['seconds'] + extra, lease_expires_at=expiry.isoformat())
            self._host('dispatch_renewed', {'previous': grant, 'grant': renewed})
            return renewed

    def begin_invocation(self, grant):
        with self.lock():
            state = self.state()
            self._authorize(state, grant)
            dispatch = state['dispatches'][grant['dispatch_id']]
            prior = dispatch.get('invocations', [])
            if any(state['invocations'][identity]['status'] == 'pending' for identity in prior):
                fail('invocation_unsettled')
            if prior and state['usage']['invocations'] >= state['scope']['limits']['hard']['invocations']:
                fail('resource_exhausted')
            identity = uuid.uuid4().hex
            self._host('invocation_intended', {'invocation_id': identity, 'dispatch_id': grant['dispatch_id'],
                'grant': grant, 'session_id': state['workers'][grant['worker_id']]['session_id']})
            return identity

    def record_invocation_observed(self, grant, invocation_id, observation):
        with self.lock():
            state = self.state()
            self.bind_grant(state, grant)
            prior = state['invocations'].get(invocation_id)
            if prior is None or prior['dispatch_id'] != grant['dispatch_id']:
                fail('invocation_identity_invalid')
            keys(observation, ('status', 'usage'), 'invocation_observation_invalid')
            if observation['status'] not in ('completed', 'interrupted', 'failed', 'aborted', 'error', 'local_only', 'stopped_unobserved'):
                fail('invocation_observation_invalid')
            self._check_usage(observation['usage'])
            if prior['status'] != 'pending':
                if all(prior[key] == value for key, value in observation.items()):
                    return {'status': 'recorded'}
                fail('invocation_observation_conflict')
            return self._host('invocation_observed', {'invocation_id': invocation_id, 'observation': observation})

    def record_provider_request(self, grant, observation):
        """Persist a proxy attempt before sending; completion can arrive after revocation."""
        with self.lock():
            state = self.state()
            dispatch = self.bind_grant(state, grant)
            keys(observation, ('request_id', 'status'), 'provider_observation_invalid')
            request_id = identifier(observation['request_id'])
            status = observation['status']
            if status not in ('started', 'completed', 'unknown'):
                fail('provider_observation_invalid')
            prior = state['provider_requests'].get(request_id)
            if prior is not None and prior['dispatch_id'] != grant['dispatch_id']:
                fail('provider_observation_conflict')
            if status == 'started':
                if prior is not None:
                    return {'status': 'recorded'}
                self._authorize(state, grant)
                pending = [name for name in dispatch.get('invocations', [])
                           if state['invocations'][name]['status'] == 'pending']
                return self._host('provider_request_started', {
                    'request_id': request_id, 'dispatch_id': grant['dispatch_id'],
                    'worker_id': grant['worker_id'], 'generation': grant['generation'],
                    'profile_id': grant['profile_id'], 'invocation_id': pending[-1] if pending else None})
            if prior is None:
                fail('provider_request_not_started')
            if prior['status'] != 'started':
                if prior['status'] == status:
                    return {'status': 'recorded'}
                fail('provider_observation_conflict')
            return self._host('provider_request_finished', {'request_id': request_id, 'status': status})

    @staticmethod
    def _accumulate_usage(total, usage):
        for key, amount in (usage['tokens'] or {}).items():
            total['tokens'][key] = total['tokens'].get(key, 0) + amount
            total['observed_token_dimensions'][key] = total['observed_token_dimensions'].get(key, 0) + 1
        if usage['cost'] is not None:
            total['known_estimated_cost'] += usage['cost']
            total['cost_observations'] += 1

    @staticmethod
    def _check_usage(usage):
        keys(usage, ('tokens', 'cost'), 'receipt_invalid')
        tokens = usage['tokens']
        if tokens is not None and (not isinstance(tokens, dict) or any(
                key not in ('input', 'output', 'cached_input', 'cache_write', 'reasoning', 'total') or not integer(value)
                for key, value in tokens.items())):
            fail('receipt_invalid')
        cost = usage['cost']
        if cost is not None and (type(cost) not in (int, float) or not math.isfinite(cost) or cost < 0):
            fail('receipt_invalid')

    def record_preparation_setup(self, grant):
        with self.lock():
            state = self.state()
            self._authorize(state, grant)
            dispatch = state['dispatches'][grant['dispatch_id']]
            if (not dispatch.get('preparation') or dispatch.get('native_admitted')
                    or dispatch.get('invocations') or dispatch.get('runtime_owner_receipts')
                    or state['workers'][grant['worker_id']].get('runtime_owner_sha256')
                    or state['workers'][grant['worker_id']].get('session_id')
                    or any(row.get('parent_dispatch_id') == grant['dispatch_id'] for row in state['dispatches'].values())):
                fail('preparation_already_admitted')
            if dispatch.get('setup_started_at'):
                return {'status': 'recorded'}
            if any(row['grant']['dispatch_id'] == grant['dispatch_id'] for row in
                   [*state['environment_operations'].values(), *state['network_operations'].values()]):
                fail('preparation_already_admitted')
            return self._host('preparation_setup_started', {'dispatch_id': grant['dispatch_id']})

    def record_native_admission(self, grant):
        with self.lock():
            state = self.state()
            self._authorize(state, grant)
            dispatch = state['dispatches'][grant['dispatch_id']]
            if not dispatch.get('preparation') or not dispatch.get('setup_started_at'):
                fail('preparation_phase_missing')
            from engagement_lab_artifacts import execute_effect
            for row in state['lab_artifacts'].values():
                if row['dispatch_id'] == grant['dispatch_id']:
                    if row['state'] != 'ready':
                        fail('lab_artifact_not_ready')
                    execute_effect(state['scope'], grant, row['environment_profile_id'])
            if dispatch.get('native_admitted'):
                return {'status': 'recorded'}
            return self._host('preparation_native_admitted', {'dispatch_id': grant['dispatch_id']})

    def preparation_without_native(self, grant):
        with self.lock():
            state = self.state()
            dispatch = self.bind_grant(state, grant)
            worker = state['workers'][grant['worker_id']]
            if (grant != {key: dispatch[key] for key in GRANT_KEYS} or not dispatch.get('preparation')
                    or not dispatch.get('setup_started_at') or dispatch.get('native_admitted')
                    or dispatch['status'] not in ('pending', 'unknown')
                    or worker['generation'] != grant['generation'] or worker['profile_id'] != grant['profile_id']
                    or worker['assignment'] != grant['assignment'] or worker['status'] not in ('preparing', 'revoked')
                    or dispatch.get('invocations') or dispatch.get('runtime_owner_receipts')
                    or worker.get('runtime_owner_sha256') or worker.get('session_id')
                    or any(row['grant']['dispatch_id'] == grant['dispatch_id'] for row in state['network_operations'].values())
                    or any(row.get('parent_dispatch_id') == grant['dispatch_id'] or
                        (row['dispatch_id'] != grant['dispatch_id'] and row['worker_id'] == grant['worker_id']
                         and row['generation'] == grant['generation'] and row['status'] != 'settled')
                        for row in state['dispatches'].values())):
                return False
            from engagement_evidence import CLEANUP_OPERATIONS
            setup = CLEANUP_OPERATIONS | {'create_stage', 'stage_input', 'snapshot_input', 'create',
                'start', 'readback_input', 'stage_support', 'readback_support'}
            nonces = {row['identity']['nonce'] for row in state['environment_operations'].values()
                      if row['grant']['dispatch_id'] == grant['dispatch_id']}
            if any(row['identity']['nonce'] in nonces and row['grant']['dispatch_id'] != grant['dispatch_id']
                   for row in state['environment_operations'].values()):
                return False
            return all(row['operation'] in setup for row in state['environment_operations'].values()
                       if row['grant']['dispatch_id'] == grant['dispatch_id'])

    def settle_preparation(self, grant, environments, *, worker_seconds):
        from engagement_evidence import identity
        with self.lock():
            state = self.state()
            dispatch = self.bind_grant(state, grant)
            if dispatch.get('setup_receipt'):
                return {'status': 'settled', 'receipt': dispatch['setup_receipt']}
            if (not self.preparation_without_native(grant) or
                    state['workers'][grant['worker_id']]['status'] != 'revoked'):
                fail('preparation_absence_unverified')
            if not integer(worker_seconds, 0, grant['seconds']) or not isinstance(environments, list):
                fail('preparation_cleanup_unverified')
            expected = {row['identity']['nonce'] for row in state['environment_operations'].values()
                        if row['grant']['dispatch_id'] == grant['dispatch_id']}
            expected.update(row['nonce'] for row in state['lab_artifacts'].values()
                if row['dispatch_id'] == grant['dispatch_id'])
            observed = set()
            for row in environments:
                keys(row, ('profile_id', 'environment', 'cleanup'), 'preparation_cleanup_unverified')
                stopped, cleanup = row['environment'], row['cleanup']
                if (not isinstance(stopped, dict) or not isinstance(cleanup, dict)
                        or stopped.get('status') not in ('stopped', 'absent') or stopped.get('running', False) is not False
                        or cleanup.get('status') != 'clean' or cleanup.get('owned_workspace') != 'container_removed'
                        or stopped.get('identity') != cleanup.get('identity')):
                    fail('preparation_cleanup_unverified')
                value = stopped['identity']
                identity(self, state, grant, row['profile_id'], value)
                nonce = value['nonce']
                if nonce not in expected or nonce in observed or value['unsettled']:
                    fail('preparation_cleanup_unverified')
                observed.add(nonce)
            if observed != expected:
                fail('preparation_cleanup_unverified')
            from engagement_lab_artifacts import require_clean
            require_clean(state, grant['dispatch_id'])
            sha = self.store_object(canonical({'kind': 'native-preparation-settled-v1', 'grant': grant,
                'environments': environments, 'worker_seconds': worker_seconds, 'native_admitted': False}))
            return self._host('preparation_settled', {'dispatch_id': grant['dispatch_id'],
                'receipt_sha256': sha, 'worker_seconds': worker_seconds, 'environment_nonces': sorted(observed)})

    def cancel_preparation(self, grant, readback):
        keys(readback, ('execution_admitted', 'cleanup'), 'preparation_cancellation_invalid')
        if readback['execution_admitted'] is not False or readback['cleanup'] != 'verified':
            fail('preparation_cancellation_invalid')
        with self.lock():
            state = self.state()
            dispatch = self.bind_grant(state, grant)
            document = {'kind': 'native-preparation-cancelled-v1', 'grant': grant, 'readback': readback}
            sha = digest(canonical(document))
            if dispatch.get('cancelled_receipt') == sha:
                return {'status': 'cancelled', 'receipt': sha}
            worker = state['workers'][grant['worker_id']]
            if (not dispatch.get('preparation') or dispatch['status'] not in ('pending', 'unknown')
                    or worker['generation'] != grant['generation'] or worker['status'] not in ('preparing', 'revoked')
                    or dispatch.get('invocations') or dispatch.get('runtime_owner_receipts') or dispatch.get('native_admitted')
                    or worker.get('runtime_owner_sha256') or worker.get('session_id')
                    or any(row['grant']['dispatch_id'] == grant['dispatch_id']
                           for row in [*state['environment_operations'].values(), *state['network_operations'].values()])
                    or any(row.get('parent_dispatch_id') == grant['dispatch_id'] for row in state['dispatches'].values())
                    or any(row['dispatch_id'] == grant['dispatch_id'] for row in state['lab_artifacts'].values())):
                fail('preparation_already_admitted')
            sha = self.store_object(canonical(document))
            return self._host('preparation_cancelled', {'dispatch_id': grant['dispatch_id'], 'receipt_sha256': sha})

    def record_runtime_stopped(self, grant, readback):
        with self.lock():
            state = self.state()
            self.bind_grant(state, grant)
            worker = state['workers'][grant['worker_id']]
            if (worker['generation'] != grant['generation'] or worker['status'] not in ('revoked', 'stopped')
                    or worker.get('runtime_owner_sha256') is None
                    or readback.get('owner_receipt_sha256') != worker['runtime_owner_sha256']
                    or readback.get('session_id') != worker['session_id']
                    or readback.get('process_exited') is not True or readback.get('child_absence') != 'verified'
                    or readback.get('capabilities_revoked') is not True
                    or any(row['worker_id'] == worker['id'] and row['generation'] == worker['generation']
                           for row in state['environments'].values())):
                fail('worker_stop_unverified')
            sha = self.store_object(canonical(readback))
            return self._host('runtime_stop_observed', {'worker_id': worker['id'], 'receipt': sha})

    def finalize_worker_outcome(self, worker_id, generation):
        with self.lock():
            state = self.state()
            worker = state['workers'][worker_id]
            if (worker['generation'] != generation or worker['status'] != 'stopped' or
                    any(d['worker_id'] == worker_id and d['status'] in ('pending', 'unknown')
                        for d in state['dispatches'].values())):
                fail('worker_outcome_unsettled')
            if not worker.get('outcome_pending'):
                return {'status': 'no_outcome'}
            return self._host('task_outcome_finalized', {'worker_id': worker_id, 'generation': generation})

    def store_object(self, content):
        if type(content) is not bytes or len(content) > 4 * 1024 * 1024:
            fail('object_size_limit')
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
                    or any(value not in ('unchanged', 'reset', 'unknown', 'retained') for value in observation['resources'].values())
                    or observation['cleanup'] not in ('pending', 'verified', 'unresolved')):
                fail('receipt_invalid')
            if (observation['status'] == 'settled' or observation['cleanup'] == 'verified'
                    or any(value != 'unknown' for value in observation['resources'].values())):
                from engagement_lab_artifacts import require_clean
                require_clean(state, dispatch_id)
            retained = {name for name, value in observation['resources'].items() if value == 'retained'}
            if retained:
                parent = state['dispatches'].get(dispatch.get('parent_dispatch_id'))
                if (parent is None or observation['status'] != 'settled' or observation['cleanup'] != 'verified'
                        or not retained <= set(parent['resources']) or self._shared(state, retained) != retained):
                    fail('receipt_retention_invalid')
                try:
                    self._authorize(state, {key: parent[key] for key in GRANT_KEYS})
                except ControllerError:
                    fail('receipt_retention_invalid')
            self._check_usage(observation['usage'])
            if dispatch.get('invocations') and observation['usage'] != {'tokens': None, 'cost': None}:
                fail('receipt_usage_already_recorded')
            tokens = observation['usage']['tokens']
            cost = observation['usage']['cost']
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
            from engagement_lab_artifacts import require_clean
            require_clean(state, dispatch_id)
            data = {'dispatch_id': dispatch_id, 'resources': resources, 'adapter_id': adapter_id}
            evidence = self.store_object(canonical(data))
            event = self._append(events, Principal('environment', adapter_id), uuid.uuid4().hex,
                evidence, 'effect_reconciled', dict(data, evidence=evidence))
            return self._receipt(event)

    def record_lab_artifact_intent(self, grant, profile_id, effect_id, identity):
        from engagement_lab_artifacts import record_intent
        return record_intent(self, grant, profile_id, effect_id, identity)

    def record_lab_artifact_ready(self, grant, profile_id, readback):
        from engagement_lab_artifacts import record_ready
        return record_ready(self, grant, profile_id, readback)

    def record_artifact_staging(self, grant, artifact_nonce, path, paths):
        from engagement_lab_artifacts import record_staging
        return record_staging(self, grant, artifact_nonce, path, paths)

    def record_lab_artifact_cleanup(self, grant, profile_id, readback):
        from engagement_lab_artifacts import record_cleanup
        return record_cleanup(self, grant, profile_id, readback)

    def record_environment_observation(self, grant, environment_profile_id, observation, output=None, *, effect_id, account_refs=()):
        from engagement_evidence import record_environment_observation
        return record_environment_observation(self, grant, environment_profile_id, observation, output,
            effect_id=effect_id, account_refs=account_refs)

    def record_environment_output(self, grant, environment_profile_id, operation_id, output):
        from engagement_evidence import record_environment_output
        return record_environment_output(self, grant, environment_profile_id, operation_id, output)

    def record_network_observation(self, grant, environment_profile_id, environment_nonce, observation, *, target_nonce=None):
        from engagement_evidence import record_network_observation
        return record_network_observation(self, grant, environment_profile_id, environment_nonce, observation, target_nonce=target_nonce)

    def record_application_start(self, grant, environment_profile_id, receipt):
        from engagement_evidence import record_application_start
        return record_application_start(self, grant, environment_profile_id, receipt)

    def register_support_inputs(self, grant, inputs):
        from engagement_evidence import register_support_inputs
        return register_support_inputs(self, grant, inputs)

    def record_experiment_execution(self, grant, environment_profile_id, operation_id, measurement):
        from engagement_evidence import record_experiment_execution
        return record_experiment_execution(self, grant, environment_profile_id, operation_id, measurement)

    def record_patch_execution(self, grant, environment_profile_id, operation_id, patch_id, arm, manifest):
        from engagement_evidence import record_patch_execution
        return record_patch_execution(self, grant, environment_profile_id, operation_id, patch_id, arm, manifest)

    def record_worker_stopped(self, grant, environment_profile_id, readback):
        from engagement_evidence import record_worker_stopped
        return record_worker_stopped(self, grant, environment_profile_id, readback)

    def record_environment_cleanup(self, grant, environment_profile_id, readback):
        from engagement_evidence import record_environment_cleanup
        return record_environment_cleanup(self, grant, environment_profile_id, readback)

    def record_obligation_delivery(self, obligation_id, worker_id, generation, *, dispatch_id, invocation_id=None):
        with self.lock():
            state = self.state()
            worker = state['workers'].get(worker_id)
            dispatch = state['dispatches'].get(dispatch_id)
            if worker is None or worker['role'] != 'lead' or worker['generation'] != generation:
                fail('worker_stale')
            if dispatch is None or dispatch['worker_id'] != worker_id or dispatch['generation'] != generation:
                fail('dispatch_identity_invalid')
            if invocation_id is None and dispatch.get('invocations'):
                fail('invocation_checkpoint_required')
            obligation = state['obligations'].get(obligation_id)
            if obligation is None:
                fail('obligation_missing')
            checkpoint = invocation_id or dispatch_id
            if checkpoint in obligation['deliveries']:
                return {'status': 'recorded'}
            if dispatch['status'] != 'pending':
                fail('delivery_after_completion')
            if invocation_id is not None:
                invocation = state['invocations'].get(invocation_id)
                if invocation is None or invocation['dispatch_id'] != dispatch_id or invocation['status'] != 'pending':
                    fail('delivery_after_completion')
            return self._host('evidence_recorded', {'action': 'obligation_delivery', 'data': {
                'obligation_id': obligation_id, 'worker_id': worker_id, 'generation': generation,
                'dispatch_id': dispatch_id, 'checkpoint_id': checkpoint}, '_objects': []})

    def record_decision_checkpoint(self, grant, *, invocation_id=None):
        from engagement_evidence import binding
        with self.lock():
            state = self.state()
            dispatch = binding(self, state, grant)
            if invocation_id is None and dispatch.get('invocations'):
                fail('invocation_checkpoint_required')
            checkpoint = invocation_id or grant['dispatch_id']
            if checkpoint in state['decision_checkpoints']:
                return {'status': 'recorded'}
            invocation = state['invocations'].get(invocation_id) if invocation_id is not None else None
            if ((invocation_id is None and dispatch['status'] != 'settled') or
                    (invocation_id is not None and (invocation is None or
                     invocation['dispatch_id'] != grant['dispatch_id'] or invocation['status'] != 'completed'))):
                fail('checkpoint_unsettled')
            worker = state['workers'][grant['worker_id']]
            if worker['role'] != 'lead' or worker['generation'] != grant['generation']:
                fail('worker_stale')
            delivered = [name for name, row in state['obligations'].items() if checkpoint in row['deliveries']]
            if not delivered:
                fail('obligation_not_delivered')
            return self._host('evidence_recorded', {'action': 'decision_checkpoint', 'data': {
                'dispatch_id': grant['dispatch_id'], 'checkpoint_id': checkpoint,
                'obligations': delivered}, '_objects': []})

    def replace_lead(self, worker_id, generation, *, profile_id=None):
        with self.lock():
            state = self.state()
            self._authority(state)
            worker = state['workers'].get(worker_id)
            if worker is None or worker['role'] != 'lead' or worker['generation'] != generation:
                fail('worker_stale')
            if not state['replacement_required']:
                fail('replacement_not_required')
            if worker['status'] != 'stopped' or not worker.get('stop_receipt'):
                fail('worker_not_stopped')
            profile_id = profile_id or worker['profile_id']
            if not any(row['profile_id'] == profile_id and 'lead' in row['roles'] for row in state['scope']['runtime_assignments']):
                fail('runtime_assignment_forbidden')
            return self._host('evidence_recorded', {'action': 'lead_replaced', 'data': {
                'worker_id': worker_id, 'generation': generation, 'profile_id': profile_id}, '_objects': []})

    def finalize_closure(self, closure_id):
        with self.lock():
            state = self.state()
            closure = state['closures'].get(closure_id)
            if closure is None or closure['state'] != 'reviewed':
                fail('closure_not_reviewed')
            from engagement_evidence import current_closure
            if not current_closure(state, closure):
                fail('closure_stale')
            if any(row['status'] != 'stopped' for row in state['workers'].values()) or state['cleanup'] != 'verified':
                fail('closure_cleanup_unverified')
            if (any(row['state'] != 'clean' for row in state['lab_artifacts'].values())
                    or state['resource_holds'] or any(d['status'] != 'settled' for d in state['dispatches'].values())):
                fail('closure_effects_unsettled')
            return self._host('evidence_recorded', {'action': 'closure_finalized', 'data': {
                'closure_id': closure_id}, '_objects': []})

    def begin_closure(self, closure_id):
        from engagement_evidence import current_closure
        with self.lock():
            state = self.state()
            self._authority(state)
            closure = state['closures'].get(closure_id)
            if closure is None or closure['state'] != 'reviewed' or not current_closure(state, closure):
                fail('closure_not_reviewed')
            return self._host('closure_stopping', {'closure_id': closure_id, 'reason': 'reviewed_closure'})

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

    def board(self, principal=None, *, query='', kinds=None, since=None, limit=30):
        from engagement_board import page
        with self.lock():
            events = self._events()
            state = self._replay(events)
            worker = self._worker(state, principal) if principal is not None else None
            return page(self, events, state, worker, query=query, kinds=kinds, since=since, limit=limit)

    def notices(self, principal, *, since=0, limit=30):
        from engagement_board import notices
        with self.lock():
            events = self._events()
            state = self._replay(events)
            worker = self._worker(state, principal)
            return notices(self, events, state, worker, since=since, limit=limit)

    def status(self, principal=None, *, since=None, limit=100, view='updates', query='', kinds=None):
        if view == 'board':
            return self.board(principal, query=query, kinds=kinds, since=since, limit=limit)
        if view != 'updates' or query or kinds is not None:
            fail('status_view_invalid')
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
                if event['type'] in ('request_accepted', 'direction_recorded', 'stop_requested', 'evidence_recorded',
                                     'task_claimed', 'worker_resumed', 'specialist_continued', 'closure_stopping'):
                    item['payload'] = event['payload']
                size = len(canonical(item))
                if updates and page_bytes + size > 512 * 1024:
                    break
                updates.append(item)
                page_bytes += size
            summary_limit = min(limit, 25)
            fields = {'tasks': ('task_id', 'status', 'owner', 'generation', 'priority'),
                      'publications': ('publication_id', 'kind', 'subject', 'author'),
                      'workers': ('id', 'role', 'generation', 'profile_id', 'status', 'assignment'),
                      'claims': ('claim_id', 'state'), 'reviews': ('review_id', 'kind', 'subject_id', 'reviewer_id', 'status', 'packet_sha256'),
                      'obligations': ('obligation_id', 'kind', 'state', 'opportunities', 'resources'),
                      'closures': ('closure_id', 'outcome', 'state'), 'patches': ('patch_id', 'claim_id', 'state')}
            summaries = {name: {key: {field: row[field] for field in selected}
                                for key, row in list(state[name].items())[:summary_limit]}
                         for name, selected in fields.items()}
            baselines = {row['access_id']: read_json(self.root / 'contract/applications' / (row['access_id'] + '.json'),
                private=True)['baseline_id'] for row in state['scope'].get('application_states', [])}
            end = start + len(updates)
            return {'status': state['status'], 'revision': state['revision'],
                'engagement_id': state['engagement_id'], 'evidence_class': state['evidence_class'],
                'assignment': worker['assignment'] if worker else None,
                'application_baselines': baselines,
                **summaries, 'summary_counts': {name: len(state[name]) for name in fields},
                'summaries_truncated': {name: len(state[name]) > summary_limit for name in fields},
                'usage': state['usage'], 'resource_holds': state['resource_holds'], 'cleanup': state['cleanup'],
                'replacement_required': state['replacement_required'],
                'lab_state_artifacts': {'classes': {name: sum(row['artifact_class'] == name for row in state['lab_artifacts'].values())
                    for name in sorted({row['artifact_class'] for row in state['lab_artifacts'].values()})},
                    'count': len(state['lab_artifacts']),
                    'pending_cleanup': sum(row['state'] != 'clean' for row in state['lab_artifacts'].values()),
                    'retained_evidence_objects': len(state['evidence_objects'])},
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
            for sha in state['evidence_objects']:
                files['objects/' + sha[7:]] = self.read_object(sha)
            from engagement_board import rows as board_rows
            files['board.json'] = canonical({'engagement_id': state['engagement_id'],
                'snapshot_revision': state['revision'], 'evidence_class': state['evidence_class'],
                'items': board_rows(state, events)})
            files['result.json'] = canonical({'engagement_id': state['engagement_id'],
                'scope_sha256': state['scope_sha256'], 'evidence_class': state['evidence_class'],
                'status': state['status'], 'claim_acceptance': 'per_claim', 'tasks': state['tasks'],
                'claims': state['claims'], 'closures': state['closures'], 'reviews': state['reviews'],
                'obligations': state['obligations'], 'experiments': state['experiments'], 'patches': state['patches'],
                'network_operations': state['network_operations'],
                'lab_artifacts': state['lab_artifacts'],
                'retained_evidence_objects': len(state['evidence_objects']),
                'research_guidance': {name: events[0]['payload']['contract_files'][name]
                    for name in ('methodology.md', 'protocol.md') if name in events[0]['payload']['contract_files']},
                'directions': state['directions'], 'messages': state['messages'],
                'usage': state['usage'], 'cleanup': state['cleanup'],
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
                        if (not {'operation', 'since', 'limit'} <= set(request) or
                                set(request) - {'operation', 'since', 'limit', 'view', 'query', 'kinds'}):
                            fail('request_invalid')
                        result = controller.status(principal, since=request['since'], limit=request['limit'],
                            view=request.get('view', 'updates'), query=request.get('query', ''), kinds=request.get('kinds'))
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
