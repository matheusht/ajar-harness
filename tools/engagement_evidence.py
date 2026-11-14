"""Typed evidence transitions on the engagement's existing immutable journal."""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from urllib.parse import urlsplit

from engagement_contract import canonical, digest, read_json
from engagement_controller import GRANT_KEYS, Principal, fail, identifier, integer, keys

REQUESTS = {'instrument_register', 'experiment_record', 'experiment_compare', 'claim_propose',
            'strategy_challenge', 'review_request', 'review_result', 'review_response',
            'closure_request', 'patch_propose'}
LEAD_ONLY = {'review_request', 'review_response', 'closure_request'}
COLLECTIONS = ('instruments', 'experiments', 'comparisons', 'claims', 'obligations', 'reviews',
               'closures', 'patches', 'environment_operations', 'network_operations', 'environments', 'support_inputs')
CLEANUP_OPERATIONS = {'revoke', 'remove', 'stop_stage', 'remove_stage', 'remove_input_image'}
OPERATIONS = CLEANUP_OPERATIONS | {'create_stage', 'stage_input', 'snapshot_input', 'create',
    'execute', 'start', 'renew', 'launch_stdio', 'readback_input', 'stage_support', 'readback_support',
    'read_workspace_manifest', 'read_artifact'}
IDENTITY_KEYS = {'kind', 'nonce', 'container_id', 'container_name', 'stage_container_id',
    'stage_container_name', 'prepared_image_id', 'prepared_image_name', 'unsettled',
    'daemon_id', 'image_id', 'profile_sha256', 'access', 'support_inputs'}
CHECKS = {'measurement', 'permissions', 'causal_control', 'clean_replay', 'completeness'}


def initialize(state):
    state.update({name: {} for name in COLLECTIONS})
    state.update(evidence_objects={}, replacement_required=False, decision_checkpoints={})


def text(value, limit=8192):
    if not isinstance(value, str) or not value.strip() or len(value.encode()) > limit:
        fail('evidence_text_invalid')


def mapping(value):
    if not isinstance(value, dict) or len(canonical(value)) > 65536:
        fail('evidence_conditions_invalid')


def references(state, values, collections, *, nonempty=False):
    if (not isinstance(values, list) or len(values) > 256 or not all(isinstance(v, str) for v in values)
            or len(set(values)) != len(values) or (nonempty and not values)):
        fail('evidence_references_invalid')
    available = set().union(*(set(state[name]) for name in collections))
    if not all(isinstance(value, str) and value in available for value in values):
        fail('evidence_reference_missing')


def unique(state, collection, value):
    identifier(value)
    if value in state[collection]:
        fail('evidence_exists')


def binding(c, state, grant):
    return c.bind_grant(state, grant)


def identity(c, state, grant, profile_id, value):
    keys(value, IDENTITY_KEYS, 'environment_identity_invalid')
    signed = next((row for row in state['scope']['environments'] if row['profile_id'] == profile_id), None)
    if signed is None:
        fail('environment_profile_forbidden')
    profile = read_json(c.root / 'contract/environments' / (profile_id + '.json'), private=True)
    expected_digest = digest(json.dumps(profile, sort_keys=True, separators=(',', ':')).encode())
    nonce = value['nonce']
    if (value['kind'] != 'research-environment-receipt-v2' or not isinstance(nonce, str)
            or not re.fullmatch('[0-9a-f]{32}', nonce)
            or value['container_name'] != 'oslit-' + nonce
            or value['stage_container_name'] != 'oslit-' + nonce + '-stage'
            or value['prepared_image_name'] != 'oslit-input-' + nonce + ':latest'
            or value['image_id'] != profile['image_id'] or value['profile_sha256'] != expected_digest
            or not isinstance(value['daemon_id'], str) or not value['daemon_id']
            or (profile['daemon_id'] is not None and value['daemon_id'] != profile['daemon_id'])):
        fail('environment_identity_invalid')
    for key in ('container_id', 'stage_container_id', 'prepared_image_id'):
        pattern = 'sha256:[0-9a-f]{64}' if key == 'prepared_image_id' else '[0-9a-f]{64}'
        if value[key] is not None and (not isinstance(value[key], str) or not re.fullmatch(pattern, value[key])):
            fail('environment_identity_invalid')
    if (not isinstance(value['unsettled'], list) or
            any(v not in ('create_stage', 'snapshot_input', 'create') for v in value['unsettled'])):
        fail('environment_identity_invalid')
    accesses = {row['id']: {k: row[k] for k in ('id', 'kind', 'identity')} for row in state['scope']['access']}
    if not isinstance(value['access'], list) or len(value['access']) > len(accesses):
        fail('environment_access_invalid')
    observed = []
    for row in value['access']:
        keys(row, ('id', 'kind', 'identity'), 'environment_access_invalid')
        if row['id'] not in grant['resources'] or row != accesses.get(row['id']) or row['id'] in observed:
            fail('environment_access_invalid')
        observed.append(row['id'])
    runtime = read_json(c.root / 'contract/runtimes' / (grant['profile_id'] + '.json'), private=True)
    support = value['support_inputs']
    if not isinstance(support, list) or len(support) > 33:
        fail('environment_support_invalid')
    registered = state['support_inputs'].get(grant['dispatch_id'], {})
    support_names = set()
    for row in support:
        keys(row, ('id', 'manifest_sha256'), 'environment_support_invalid')
        identifier(row['id'])
        if (row['id'] in accesses or row['id'] in support_names or
                (row['manifest_sha256'] != runtime['tool_bundle']['manifest_sha256'] and registered.get(row['id']) != row['manifest_sha256'])):
            fail('environment_support_invalid')
        support_names.add(row['id'])
    prior = state['environments'].get(nonce)
    if prior:
        if prior['profile_id'] != profile_id or prior['worker_id'] != grant['worker_id'] or prior['generation'] != grant['generation']:
            fail('environment_owner_mismatch')
        for key in IDENTITY_KEYS - {'unsettled'}:
            old = prior['identity'][key]
            if old is not None and old != value[key]:
                fail('environment_identity_changed')
    return signed


def record_environment_observation(c, grant, profile_id, observation, output=None, *, effect_id, account_refs=()):
    with c.lock():
        state = c.state()
        binding(c, state, grant)
        common = {'kind', 'phase', 'operation', 'operation_id', 'identity'}
        if not isinstance(observation, dict) or not common <= set(observation) or observation['kind'] != 'environment-observation-v2':
            fail('environment_observation_invalid')
        op, phase, opid = observation['operation'], observation['phase'], identifier(observation['operation_id'])
        if op not in OPERATIONS or phase not in ('intent', 'result'):
            fail('environment_observation_invalid')
        allowed_extra = {'request_sha256', 'seconds', 'role'} if phase == 'intent' else {
            'status', 'returncode', 'output_sha256', 'manifest_sha256', 'files', 'native_acknowledgment', 'role', 'path', 'bytes'}
        if not set(observation) <= common | allowed_extra:
            fail('environment_observation_invalid')
        identity(c, state, grant, profile_id, observation['identity'])
        effect = next((row for row in state['scope']['effects'] if row['id'] == effect_id), None)
        accounts = list(account_refs)
        access_ids = [row['id'] for row in observation['identity']['access']]
        if (effect is None or profile_id not in effect['environment_ids'] or
                not set(access_ids) <= set(effect['access_ids']) or not set(accounts) <= set(effect['account_refs'])):
            fail('environment_effect_forbidden')
        prior = state['environment_operations'].get(opid)
        document = {'grant': grant, 'profile_id': profile_id, 'effect_id': effect_id,
            'account_refs': accounts, 'observation': observation}
        sha = digest(canonical(document))
        if prior and sha in prior['receipts']:
            return {'status': 'recorded', 'receipt': sha}
        if phase == 'intent':
            if prior:
                fail('environment_operation_conflict')
            if op in CLEANUP_OPERATIONS:
                if observation['identity']['nonce'] not in state['environments']:
                    fail('environment_observation_missing')
            else:
                c._authorize(state, grant)
        elif prior:
            if (prior['grant'] != grant or prior['profile_id'] != profile_id or prior['operation'] != op
                    or prior['effect_id'] != effect_id or prior['account_refs'] != accounts):
                fail('environment_operation_conflict')
            if prior.get('result') is not None and not (prior['result'].get('status') in ('unknown', 'dispatched')
                                                       and observation.get('status') == 'settled'):
                fail('environment_operation_conflict')
        elif op not in ('readback_input', 'readback_support', 'read_workspace_manifest', 'read_artifact'):
            fail('environment_intent_missing')
        else:
            c._authorize(state, grant)
        if phase == 'result' and observation.get('status') not in ('settled', 'unknown', 'unavailable', 'dispatched'):
            fail('environment_observation_invalid')
        for name in ('request_sha256', 'output_sha256', 'manifest_sha256'):
            if name in observation and (not isinstance(observation[name], str) or not re.fullmatch('sha256:[0-9a-f]{64}', observation[name])):
                fail('environment_observation_invalid')
        sha = c.store_object(canonical(document))
        result = c._host('evidence_recorded', {'action': 'environment_observation', 'data': {
            **document, 'receipt_sha256': sha, 'session_id': state['workers'][grant['worker_id']]['session_id']}, '_objects': [sha]})
        if output is not None:
            record_environment_output(c, grant, profile_id, opid, output)
        return result


def record_environment_output(c, grant, profile_id, operation_id, output):
    with c.lock():
        state = c.state()
        binding(c, state, grant)
        operation = state['environment_operations'].get(operation_id)
        if (operation is None or operation['grant'] != grant or operation['profile_id'] != profile_id
                or operation.get('result') is None):
            fail('environment_observation_missing')
        if type(output) is not bytes or operation['result'].get('output_sha256') != digest(output):
            fail('environment_output_mismatch')
        if operation.get('output_sha256') is not None:
            return {'status': 'recorded', 'receipt': operation['output_sha256']}
        sha = c.store_object(output)
        return c._host('evidence_recorded', {'action': 'environment_output',
            'data': {'operation_id': operation_id, 'output_sha256': sha}, '_objects': [sha]})


def record_network_observation(c, grant, profile_id, nonce, observation):
    with c.lock():
        state = c.state()
        binding(c, state, grant)
        common = {'kind', 'phase', 'operation_id', 'access_id', 'effect_id', 'account_ref',
                  'origin', 'method', 'path_sha256'}
        phase = observation.get('phase') if isinstance(observation, dict) else None
        keys(observation, common | ({'status', 'http_status', 'request_bytes', 'response_bytes'}
                                   if phase == 'result' else set()), 'network_observation_invalid')
        if (observation['kind'] != 'target-network-observation-v1' or phase not in ('intent', 'result')
                or not isinstance(observation['method'], str)
                or not re.fullmatch('[A-Z]{1,32}', observation['method'])
                or not isinstance(observation['path_sha256'], str)
                or not re.fullmatch('sha256:[0-9a-f]{64}', observation['path_sha256'])):
            fail('network_observation_invalid')
        opid = identifier(observation['operation_id'])
        for name in ('access_id', 'effect_id'):
            identifier(observation[name])
        account = observation['account_ref']
        if account is not None:
            identifier(account)
        origin = observation['origin']
        try:
            parsed = urlsplit(origin)
            host = '[' + parsed.hostname + ']' if ':' in parsed.hostname else parsed.hostname
            if (parsed.scheme not in ('http', 'https') or parsed.username is not None
                    or parsed.password is not None or parsed.path or parsed.query or parsed.fragment
                    or origin != f'{parsed.scheme}://{host}:{parsed.port}'):
                fail('network_observation_invalid')
        except (TypeError, ValueError, AttributeError):
            fail('network_observation_invalid')
        if phase == 'result':
            if (observation['status'] not in ('settled', 'unknown')
                    or (observation['http_status'] is not None and
                        (type(observation['http_status']) is not int or not 100 <= observation['http_status'] <= 599))
                    or any(type(observation[k]) is not int or observation[k] < 0
                           for k in ('request_bytes', 'response_bytes'))):
                fail('network_observation_invalid')
        environment = state['environments'].get(nonce)
        if (environment is None or environment['profile_id'] != profile_id
                or environment['worker_id'] != grant['worker_id'] or environment['generation'] != grant['generation']):
            fail('network_environment_invalid')
        access = next((row for row in state['scope']['access'] if row['id'] == observation['access_id']), None)
        effect = next((row for row in state['scope']['effects'] if row['id'] == observation['effect_id']), None)
        permission = 'read' if observation['method'] in ('GET', 'HEAD', 'OPTIONS') else 'write'
        if (access is None or access['kind'] != 'application' or effect is None
                or access['id'] not in grant['resources']
                or access['id'] not in {row['id'] for row in environment['identity']['access']}
                or access['id'] not in effect['access_ids'] or profile_id not in effect['environment_ids']
                or effect['kind'] != permission or permission not in access['permissions']
                or (account is None and effect['account_refs'])
                or (account is not None and (account not in access['account_refs'] or account not in effect['account_refs']))):
            fail('network_effect_forbidden')
        target = urlsplit(access['identity']['base_url'])
        if (parsed.scheme, parsed.hostname, parsed.port) != (target.scheme, target.hostname,
                target.port or (443 if target.scheme == 'https' else 80)):
            fail('network_effect_forbidden')
        document = {'grant': grant, 'profile_id': profile_id, 'environment_nonce': nonce, 'observation': observation}
        sha = digest(canonical(document))
        prior = state['network_operations'].get(opid)
        if prior and sha in prior['receipts']:
            return {'status': 'recorded', 'receipt': sha}
        if phase == 'intent':
            if prior:
                fail('network_operation_conflict')
            if (environment.get('stopped') or environment.get('cleanup') == 'verified' or not any(
                    row['identity']['nonce'] == nonce and row['grant']['dispatch_id'] == grant['dispatch_id']
                    for row in state['environment_operations'].values())):
                fail('network_environment_invalid')
            c._authorize(state, grant)
        else:
            if prior is None:
                fail('network_intent_missing')
            if (prior['grant'] != grant or prior['profile_id'] != profile_id or prior['environment_nonce'] != nonce
                    or any(prior['intent'][key] != observation[key] for key in common - {'phase'})
                    or (prior['result'] is not None and not
                        (prior['result']['status'] == 'unknown' and observation['status'] == 'settled'))):
                fail('network_operation_conflict')
        sha = c.store_object(canonical(document))
        return c._host('evidence_recorded', {'action': 'network_observation', 'data': {
            **document, 'receipt_sha256': sha}, '_objects': [sha]})


def comparable(left, right):
    return all(left[key] == right[key] for key in ('instrument_id', 'conditions', 'input_identity',
        'environment_profile_id', 'effect_id', 'account_refs', 'resources'))


def related(left, right, purpose, *, independent=False):
    if not comparable(left, right) or right['purpose'] != purpose:
        return False
    explains = right['explains']
    if explains is None or explains['experiment_id'] != left['experiment_id']:
        return False
    if purpose == 'control':
        return bool(explains['variable'])
    if right['candidate_sha256'] != left['candidate_sha256'] or right['probe_sha256'] != left['probe_sha256']:
        return False
    return not independent or (right['session_id'] != left['session_id'] and right['environment_nonce'] != left['environment_nonce'] and right['clean_start'])


def dependencies(state, kind, subject):
    if kind == 'claim':
        claim = state['claims'][subject]
        experiments = [state['experiments'][name] for name in (claim['effect'], claim['control'], claim['replay']) if name]
        return {'claim': claim, 'experiments': experiments,
            'instruments': [state['instruments'][name] for name in sorted({row['instrument_id'] for row in experiments})],
            'contrary': {name: state['publications'][name] for name in claim['contrary']}}
    collection = {'strategy': 'obligations', 'closure': 'closures', 'patch': 'patches'}[kind]
    return {kind: state[collection][subject]}


def validate_request(c, state, worker, kind, data):
    if kind in LEAD_ONLY and worker['role'] != 'lead':
        fail('role_forbidden')
    objects = []
    if kind == 'instrument_register':
        keys(data, ('instrument_id', 'artifact_sha256', 'metric', 'reset', 'conditions', 'supersedes'))
        unique(state, 'instruments', data['instrument_id'])
        c.read_object(data['artifact_sha256']); objects.append(data['artifact_sha256'])
        text(data['metric'], 1024); text(data['reset'], 4096); mapping(data['conditions'])
        references(state, data['supersedes'], ('instruments',))
    elif kind == 'experiment_record':
        keys(data, ('experiment_id', 'instrument_id', 'candidate_sha256', 'probe_sha256', 'operation_id',
            'purpose', 'conditions', 'score', 'resources', 'explains', 'supersedes'))
        unique(state, 'experiments', data['experiment_id'])
        references(state, [data['instrument_id']], ('instruments',))
        operation = state['environment_operations'].get(data['operation_id'])
        if operation is None or operation.get('result') is None or operation.get('output_sha256') is None:
            fail('environment_observation_missing')
        if (operation['grant']['worker_id'] != worker['id'] or operation['grant']['generation'] != worker['generation']
                or operation['operation'] != 'execute' or operation['result']['status'] != 'settled'):
            fail('experiment_observation_invalid')
        measurement = operation.get('measurement')
        if measurement is None or any(measurement[key] != data[key] for key in ('instrument_id', 'candidate_sha256', 'probe_sha256', 'conditions')):
            fail('experiment_execution_unbound')
        dispatch = state['dispatches'][operation['grant']['dispatch_id']]
        if dispatch['status'] != 'settled':
            fail('experiment_observation_unsettled')
        c._resources(state, data['resources'])
        if set(data['resources']) != set(operation['grant']['resources']):
            fail('experiment_resources_mismatch')
        for name in ('candidate_sha256', 'probe_sha256'):
            c.read_object(data[name]); objects.append(data[name])
        if data['purpose'] not in ('effect', 'control', 'replay', 'normal_function', 'variant', 'exploration'):
            fail('experiment_purpose_invalid')
        mapping(data['conditions'])
        if data['score'] is not None and (type(data['score']) not in (int, float) or not math.isfinite(data['score'])):
            fail('experiment_score_invalid')
        if data['explains'] is not None:
            keys(data['explains'], ('experiment_id', 'variable'))
            references(state, [data['explains']['experiment_id']], ('experiments',))
            if data['explains']['variable'] is not None:
                text(data['explains']['variable'], 1024)
        references(state, data['supersedes'], ('experiments',))
        data = dict(data, session_id=operation['session_id'], worker_id=worker['id'], generation=worker['generation'],
            environment_nonce=operation['identity']['nonce'], environment_profile_id=operation['profile_id'],
            input_identity=operation['identity']['access'], effect_id=operation['effect_id'],
            account_refs=operation['account_refs'], output_sha256=operation['output_sha256'],
            receipt_sha256=dispatch['receipt'], environment_receipts=operation['receipts'], patch_copy=operation.get('patch_copy'),
            execution_receipt_sha256=operation['execution_receipt_sha256'], clean_start=measurement['clean_start'])
    elif kind == 'experiment_compare':
        keys(data, ('comparison_id', 'experiments'))
        unique(state, 'comparisons', data['comparison_id'])
        references(state, data['experiments'], ('experiments',), nonempty=True)
        first = state['experiments'][data['experiments'][0]]
        if len(data['experiments']) < 2 or any(not comparable(first, state['experiments'][name]) for name in data['experiments'][1:]):
            fail('experiment_not_comparable')
    elif kind == 'claim_propose':
        keys(data, ('claim_id', 'text', 'effect', 'control', 'replay', 'contrary', 'resources', 'supersedes'))
        unique(state, 'claims', data['claim_id']); text(data['text'])
        references(state, [name for name in (data['effect'], data['control'], data['replay']) if name is not None], ('experiments',))
        references(state, data['contrary'], ('publications',)); references(state, data['supersedes'], ('claims',))
        c._resources(state, data['resources'])
        effect = state['experiments'].get(data['effect'])
        if effect and (effect['purpose'] != 'effect' or set(data['resources']) != set(effect['resources'])):
            fail('claim_evidence_invalid')
        if data['control'] and (not effect or not related(effect, state['experiments'][data['control']], 'control')):
            fail('claim_control_invalid')
        if data['replay'] and (not effect or not related(effect, state['experiments'][data['replay']], 'replay', independent=True)):
            fail('claim_replay_invalid')
        data = dict(data, state='supported' if effect else 'unconfirmed')
    elif kind == 'strategy_challenge':
        keys(data, ('obligation_id', 'kind', 'refs', 'resources', 'reason'))
        unique(state, 'obligations', data['obligation_id'])
        if data['kind'] not in ('contradiction', 'repetition', 'strong_lead_dismissal'):
            fail('obligation_kind_invalid')
        references(state, data['refs'], ('publications', 'experiments', 'claims'), nonempty=True)
        c._resources(state, data['resources']); text(data['reason'])
        if data['kind'] == 'repetition':
            rows = [state['experiments'].get(name) for name in data['refs']]
            if len(rows) < 2 or any(row is None for row in rows) or any(
                    not comparable(rows[0], row) or any(rows[0][k] != row[k] for k in ('candidate_sha256', 'probe_sha256')) for row in rows[1:]):
                fail('repetition_unproven')
    elif kind == 'review_request':
        keys(data, ('review_id', 'kind', 'subject_id', 'reviewer_id'))
        unique(state, 'reviews', data['review_id'])
        collection = {'claim': 'claims', 'strategy': 'obligations', 'closure': 'closures', 'patch': 'patches'}.get(data['kind'])
        if collection is None or data['subject_id'] not in state[collection]:
            fail('review_subject_missing')
        reviewer = state['workers'].get(data['reviewer_id'])
        if reviewer is None or reviewer['role'] != 'reviewer' or reviewer['status'] != 'pending' or reviewer['session_id'] is not None:
            fail('reviewer_not_fresh')
        if any(row['reviewer_id'] == reviewer['id'] for row in state['reviews'].values()):
            fail('reviewer_not_fresh')
        material = dependencies(state, data['kind'], data['subject_id'])
        subject = state[collection][data['subject_id']]
        resources = subject.get('resources', [])
        packet = {'kind': 'engagement-review-packet-v2', 'scope_sha256': state['scope_sha256'],
            'evidence_class': state['evidence_class'], 'review': data, 'material': material,
            'permissions': [row for row in state['scope']['access'] if row['id'] in resources],
            'resources': resources, 'publication_snapshot': state['publications'],
            'contract_files': c._events()[0]['payload']['contract_files']}
        sha = c.store_object(canonical(packet)); objects.append(sha)
        data = dict(data, packet_sha256=sha, resources=resources, status='pending',
            subject_version=digest(canonical(subject)))
    elif kind == 'review_result':
        keys(data, ('review_id', 'packet_sha256', 'disposition', 'checks', 'evidence_refs', 'contrary_refs', 'reason'))
        review = state['reviews'].get(data['review_id'])
        if (review is None or review['reviewer_id'] != worker['id'] or worker['role'] != 'reviewer'
                or review['status'] != 'pending' or data['packet_sha256'] != review['packet_sha256']):
            fail('review_identity_invalid')
        if data['disposition'] not in ('accept', 'reject', 'reopen', 'unresolved'):
            fail('review_disposition_invalid')
        keys(data['checks'], CHECKS)
        if any(type(value) is not bool for value in data['checks'].values()):
            fail('review_checks_invalid')
        text(data['reason']); references(state, data['evidence_refs'], ('experiments',))
        references(state, data['contrary_refs'], ('publications',))
        if data['disposition'] == 'accept':
            if not all(data['checks'].values()):
                fail('review_checks_incomplete')
            if review['kind'] == 'claim':
                claim = state['claims'][review['subject_id']]
                if set(claim['contrary']) - set(data['contrary_refs']):
                    fail('review_contrary_missing')
                effect = state['experiments'].get(claim['effect'])
                control = state['experiments'].get(claim['control'])
                replays = [state['experiments'][name] for name in data['evidence_refs']]
                if (not effect or not control or not related(effect, control, 'control') or
                    not any(row['worker_id'] == worker['id'] and row['session_id'] == worker['session_id']
                        and related(effect, row, 'replay', independent=True) for row in replays)):
                    fail('review_evidence_incomplete')
                if state['instruments'][effect['instrument_id']].get('superseded_by'):
                    fail('review_stale')
            elif review['kind'] == 'closure':
                if not current_closure(state, state['closures'][review['subject_id']]):
                    fail('review_stale')
            elif review['kind'] == 'patch':
                patch_checks(state, review, worker, data['evidence_refs'])
    elif kind == 'review_response':
        keys(data, ('obligation_id', 'action', 'refs', 'reason'))
        obligation = state['obligations'].get(data['obligation_id'])
        if obligation is None or obligation['state'] not in ('pending', 'disputed'):
            fail('obligation_missing')
        collection = {'task': 'tasks', 'experiment': 'experiments', 'rebuttal': 'publications', 'review': 'reviews'}.get(data['action'])
        if collection is None:
            fail('obligation_response_invalid')
        references(state, data['refs'], (collection,), nonempty=True); text(data['reason'])
        if data['action'] == 'review' and any(state['reviews'][name]['subject_id'] != data['obligation_id'] for name in data['refs']):
            fail('obligation_response_invalid')
    elif kind == 'closure_request':
        keys(data, ('closure_id', 'outcome', 'claim_ids', 'remaining', 'reason'))
        unique(state, 'closures', data['closure_id'])
        if data['outcome'] not in ('goal_met', 'covered_dry', 'blocked'):
            fail('closure_outcome_invalid')
        references(state, data['claim_ids'], ('claims',)); references(state, data['remaining'], ('tasks',))
        text(data['reason'])
        unresolved = {name for name, row in state['tasks'].items() if row['status'] not in ('completed', 'reviewed_complete')}
        if not unresolved <= set(data['remaining']):
            fail('closure_incomplete')
        if data['outcome'] == 'goal_met':
            if (not data['claim_ids'] or any(state['claims'][name]['state'] != 'independently_confirmed' for name in data['claim_ids'])
                    or (state['scope']['goal_mode'] == 'broad' and unresolved)):
                fail('closure_incomplete')
            if state['scope']['patch_required'] and not any(row.get('state') == 'accepted' for row in state['patches'].values()):
                fail('patch_required')
        if any(d['status'] == 'unknown' for d in state['dispatches'].values()) or state['resource_holds']:
            fail('closure_effects_unsettled')
        data = dict(data, resources=[row['id'] for row in state['scope']['access']], state='pending')
    elif kind == 'patch_propose':
        data, objects = freeze_patch(c, state, data)
    else:
        fail('role_forbidden')
    return dict(data, _objects=objects)


def invalidate(state, supersedes):
    if not supersedes:
        return
    changed = set(supersedes)
    changed_bytes = {artifact['sha256'] for name in changed if name in state['publications']
        for artifact in state['publications'][name]['artifacts']}

    def experiment_dependencies(names):
        rows = [state['experiments'][name] for name in names if name in state['experiments']]
        identifiers = {value for row in rows for value in (row['experiment_id'], row['instrument_id'])}
        byte_refs = {value for row in rows for value in (row['candidate_sha256'], row['probe_sha256'],
            state['instruments'][row['instrument_id']]['artifact_sha256'])}
        return identifiers, byte_refs

    for collection, subject_key in (('claims', 'claim_id'), ('patches', 'patch_id'), ('closures', 'closure_id')):
        for subject in state[collection].values():
            subject_id = subject[subject_key]
            reviews = [row for row in state['reviews'].values() if row['subject_id'] == subject_id
                and row['kind'] == {'claims': 'claim', 'patches': 'patch', 'closures': 'closure'}[collection]]
            experiments = [name for review in reviews for name in review.get('result', {}).get('evidence_refs', [])]
            relevant = {subject_id}
            if collection == 'claims':
                experiments.extend(name for name in (subject['effect'], subject['control'], subject['replay']) if name)
                relevant.update(subject['contrary'])
            elif collection == 'patches':
                relevant.add(subject['claim_id'])
            else:
                relevant.update(subject['claim_ids'])
            experiment_ids, byte_refs = experiment_dependencies(experiments)
            if (relevant | experiment_ids) & changed or byte_refs & changed_bytes:
                subject['state'] = 'reopened' if collection == 'closures' else 'needs_review'
                changed.add(subject_id)
                for review in reviews:
                    review['status'] = 'stale'


def reduce_request(state, actor, kind, data):
    state['evidence_objects'].update({sha: True for sha in data.get('_objects', [])})
    data = {key: value for key, value in data.items() if key != '_objects'}
    collections = {'instrument_register': ('instruments', 'instrument_id'),
        'experiment_record': ('experiments', 'experiment_id'), 'experiment_compare': ('comparisons', 'comparison_id'),
        'claim_propose': ('claims', 'claim_id'), 'review_request': ('reviews', 'review_id'),
        'closure_request': ('closures', 'closure_id'), 'patch_propose': ('patches', 'patch_id')}
    if kind in collections:
        collection, id_key = collections[kind]
        state[collection][data[id_key]] = dict(data, author=actor)
        for old in data.get('supersedes', []):
            state[collection][old]['superseded_by'] = data[id_key]
        invalidate(state, data.get('supersedes', []))
    elif kind == 'strategy_challenge':
        state['obligations'][data['obligation_id']] = dict(data, author=actor, state='pending',
            opportunities=0, deliveries={}, checkpoints=[], response=None)
    elif kind == 'review_response':
        obligation = state['obligations'][data['obligation_id']]
        obligation.update(state='disputed' if data['action'] == 'rebuttal' else 'responded', response=data)
        state['replacement_required'] = any(o['state'] == 'pending' and o['opportunities'] >= 2 for o in state['obligations'].values())
    elif kind == 'review_result':
        review = state['reviews'][data['review_id']]
        review.update(status='accepted' if data['disposition'] == 'accept' else data['disposition'], result=data)
        if review['kind'] == 'claim':
            claim = state['claims'][review['subject_id']]
            claim['state'] = {'accept': 'independently_confirmed', 'reject': 'refuted'}.get(data['disposition'], 'needs_review')
            claim['review_id'] = data['review_id']
        elif review['kind'] == 'strategy':
            state['obligations'][review['subject_id']]['state'] = 'resolved' if data['disposition'] == 'accept' else 'pending'
        elif review['kind'] == 'patch':
            state['patches'][review['subject_id']]['state'] = 'accepted' if data['disposition'] == 'accept' else 'needs_review'
            state['patches'][review['subject_id']]['review_id'] = data['review_id']
        elif review['kind'] == 'closure':
            closure = state['closures'][review['subject_id']]
            closure['state'] = 'reviewed' if data['disposition'] == 'accept' else 'reopened'
            closure['review_id'] = data['review_id']
            if data['disposition'] != 'accept':
                name = 'reopen-' + review['subject_id']
                state['obligations'][name] = {'obligation_id': name, 'kind': 'reopen', 'refs': [review['subject_id']],
                    'resources': closure['resources'], 'reason': data['reason'], 'state': 'pending',
                    'opportunities': 0, 'deliveries': {}, 'checkpoints': [], 'response': None}
    else:
        fail('journal_corrupt')


def reduce_host(state, payload):
    action, data = payload['action'], payload['data']
    state['evidence_objects'].update({sha: True for sha in payload.get('_objects', [])})
    if action == 'support_inputs_registered':
        state['support_inputs'][data['grant']['dispatch_id']] = data['inputs']
    elif action == 'network_observation':
        observation = data['observation']
        operation = state['network_operations'].setdefault(observation['operation_id'], {
            'grant': data['grant'], 'profile_id': data['profile_id'],
            'environment_nonce': data['environment_nonce'], 'receipts': [], 'result': None})
        operation['receipts'].append(data['receipt_sha256'])
        operation[observation['phase']] = observation
    elif action == 'environment_observation':
        observation, grant = data['observation'], data['grant']
        nonce, opid = observation['identity']['nonce'], observation['operation_id']
        state['environments'][nonce] = dict(state['environments'].get(nonce, {}),
            identity=observation['identity'], profile_id=data['profile_id'], worker_id=grant['worker_id'], generation=grant['generation'])
        operation = state['environment_operations'].setdefault(opid, {'grant': grant, 'profile_id': data['profile_id'],
            'operation': observation['operation'], 'effect_id': data['effect_id'], 'account_refs': data['account_refs'],
            'session_id': data['session_id'], 'receipts': [], 'result': None})
        operation['identity'] = observation['identity']
        operation['receipts'].append(data['receipt_sha256'])
        operation[observation['phase']] = observation
    elif action == 'experiment_execution':
        state['environment_operations'][data['operation_id']].update(measurement=data['measurement'], execution_receipt_sha256=data['receipt_sha256'])
    elif action == 'patch_execution':
        state['environment_operations'][data['operation_id']]['patch_copy'] = data
    elif action == 'environment_output':
        state['environment_operations'][data['operation_id']]['output_sha256'] = data['output_sha256']
    elif action == 'obligation_delivery':
        state['obligations'][data['obligation_id']]['deliveries'][data.get('checkpoint_id', data['dispatch_id'])] = data
    elif action == 'decision_checkpoint':
        checkpoint = data.get('checkpoint_id', data['dispatch_id'])
        state['decision_checkpoints'][checkpoint] = True
        for name in data['obligations']:
            row = state['obligations'][name]
            row['checkpoints'].append(checkpoint)
            if row['state'] == 'pending':
                row['opportunities'] += 1
        state['replacement_required'] = any(o['state'] == 'pending' and o['opportunities'] >= 2 for o in state['obligations'].values())
    elif action == 'worker_stopped':
        state['environments'][data['nonce']]['stopped'] = True
        worker = state['workers'][data['worker_id']]
        owned = [row for row in state['environments'].values() if row['worker_id'] == worker['id'] and row['generation'] == worker['generation']]
        if all(row.get('stopped') or row.get('cleanup') == 'verified' for row in owned):
            worker.update(status='stopped', stop_receipt=data['receipt_sha256'])
    elif action == 'environment_cleanup':
        state['environments'][data['nonce']]['cleanup'] = 'verified'
        state['environments'][data['nonce']]['cleanup_receipt'] = data['receipt_sha256']
        state['cleanup'] = 'verified' if all(row.get('cleanup') == 'verified' for row in state['environments'].values()) else 'pending'
    elif action == 'lead_replaced':
        old = state['workers'][data['worker_id']]
        old.setdefault('history', []).append({key: value for key, value in old.items() if key != 'history'})
        for task in state['tasks'].values():
            if task['owner'] == old['id'] and task['status'] == 'assigned':
                task.update(status='ready', owner=None)
        old.update(generation=old['generation'] + 1, profile_id=data['profile_id'], status='pending',
            assignment=None, workspace=None, session_id=None, cursor=None, runtime_owner_sha256=None)
        for obligation in state['obligations'].values():
            obligation.setdefault('prior_opportunities', []).append(obligation['opportunities'])
            obligation['opportunities'] = 0
        old.pop('stop_receipt', None)
        state['replacement_required'] = False
    elif action == 'closure_finalized':
        state['status'] = 'closed'
        state['closures'][data['closure_id']]['state'] = 'closed'
        state['result'] = {'closure_id': data['closure_id'], 'outcome': state['closures'][data['closure_id']]['outcome']}
    else:
        fail('journal_corrupt')


def runtime_owner(c, state, worker, session_id, receipt, *, preparing=False):
    if receipt is None:
        return None
    required = {'kind', 'runtime', 'session_id', 'profile_sha256', 'boundary'}
    if (not isinstance(receipt, dict) or not required <= set(receipt)
            or not set(receipt) <= required | {'process', 'bridge_process'}
            or not {'process', 'bridge_process'} & set(receipt) or not preparing and 'process' not in receipt):
        fail('runtime_owner_invalid')
    assignment = next(row for row in state['scope']['runtime_assignments'] if row['profile_id'] == worker['profile_id'])
    profile = read_json(c.root / 'contract/runtimes' / (worker['profile_id'] + '.json'), private=True)
    if (receipt['kind'] != 'native-runtime-owner-v1' or receipt['runtime'] != profile['kind']
            or receipt['session_id'] != session_id or receipt['profile_sha256'] != assignment['profile_sha256']
            or receipt['boundary'] != 'darwin-no-fork-v1'):
        fail('runtime_owner_invalid')
    for name in ('process', 'bridge_process'):
        if name not in receipt:
            continue
        process = receipt[name]
        keys(process, ('pid', 'pgid', 'uid', 'started_seconds', 'started_microseconds'), 'runtime_owner_invalid')
        if (not integer(process['pid'], 1) or not integer(process['pgid'], 1) or not integer(process['uid'])
                or not integer(process['started_seconds']) or not integer(process['started_microseconds'], 0, 999999)):
            fail('runtime_owner_invalid')
    return c.store_object(canonical(receipt))


def record_worker_stopped(c, grant, profile_id, readback):
    with c.lock():
        state = c.state()
        binding(c, state, grant)
        keys(readback, ('environment', 'runtime'), 'worker_stop_unverified')
        env, runtime = readback['environment'], readback['runtime']
        if not isinstance(env, dict) or not isinstance(runtime, dict):
            fail('worker_stop_unverified')
        worker = state['workers'][grant['worker_id']]
        if worker['generation'] != grant['generation'] or worker['status'] not in ('revoked', 'stopped'):
            fail('worker_not_revoked')
        if (env.get('status') not in ('stopped', 'absent') or env.get('running', False) is not False
                or runtime.get('process_exited') is not True or runtime.get('child_absence') != 'verified'
                or runtime.get('capabilities_revoked') is not True or runtime.get('session_id') != worker['session_id']
                or worker.get('runtime_owner_sha256') is None
                or runtime.get('owner_receipt_sha256') != worker['runtime_owner_sha256']):
            fail('worker_stop_unverified')
        identity(c, state, grant, profile_id, env.get('identity'))
        nonce = env['identity']['nonce']
        if nonce not in state['environments'] or env['identity']['unsettled']:
            fail('worker_stop_unverified')
        sha = c.store_object(canonical({'grant': grant, 'profile_id': profile_id, 'readback': readback}))
        return c._host('evidence_recorded', {'action': 'worker_stopped', 'data': {
            'worker_id': grant['worker_id'], 'generation': grant['generation'], 'nonce': nonce,
            'receipt_sha256': sha}, '_objects': [sha]})


def record_environment_cleanup(c, grant, profile_id, readback):
    with c.lock():
        state = c.state()
        binding(c, state, grant)
        keys(readback, ('status', 'identity', 'owned_workspace'), 'cleanup_unverified')
        if readback['status'] != 'clean' or readback['owned_workspace'] != 'container_removed':
            fail('cleanup_unverified')
        identity(c, state, grant, profile_id, readback['identity'])
        nonce = readback['identity']['nonce']
        if nonce not in state['environments'] or readback['identity']['unsettled']:
            fail('cleanup_unverified')
        sha = c.store_object(canonical({'grant': grant, 'profile_id': profile_id, 'readback': readback}))
        return c._host('evidence_recorded', {'action': 'environment_cleanup', 'data': {
            'nonce': nonce, 'receipt_sha256': sha}, '_objects': [sha]})


def freeze_patch(c, state, data):
    import os
    import tempfile
    from engagement_contract import read_bytes, source_manifest, ContractError
    from native_patch_check import _apply, PatchCheckError
    if not state['scope']['patch_required']:
        fail('patch_not_requested')
    keys(data, ('patch_id', 'claim_id', 'source_access', 'diff_sha256', 'supersedes'))
    unique(state, 'patches', data['patch_id'])
    references(state, [data['claim_id']], ('claims',))
    references(state, data['supersedes'], ('patches',))
    access = next((row for row in state['scope']['access'] if row['id'] == data['source_access'] and row['kind'] == 'source'), None)
    if access is None or data['source_access'] not in state['claims'][data['claim_id']]['resources']:
        fail('patch_source_invalid')
    diff = c.read_object(data['diff_sha256'])
    try:
        diff.decode('utf-8')
    except UnicodeError:
        fail('patch_diff_unsafe')
    if (not 0 < len(diff) <= 1024 * 1024 or b'\x00' in diff or b'GIT binary patch' in diff or
            re.search(rb'(?m)^(?:(?:new |old )?file mode|new mode|old mode) 120000\s*$', diff)):
        fail('patch_diff_unsafe')
    inputs = read_json(c.root / 'contract/inputs.json', private=True)
    source = Path(inputs['access_files'][data['source_access']])
    try:
        original = source_manifest(source)
    except ContractError:
        fail('patch_source_changed')
    if digest(canonical(original)) != access['identity']['manifest_sha256']:
        fail('patch_source_changed')
    limit = min(16 * 1024 * 1024, max(row['limits']['workspace_bytes'] for row in state['scope']['environments']))
    if sum(row['size'] for row in original.values()) > limit:
        fail('patch_snapshot_limit')
    objects = [data['diff_sha256']]
    with tempfile.TemporaryDirectory(prefix='oslit-patch-') as temporary:
        directory = Path(temporary).resolve()
        for name, row in original.items():
            try:
                content = read_bytes(source / name, max_bytes=4 * 1024 * 1024)
            except ContractError:
                fail('patch_source_changed')
            if digest(content) != row['sha256']:
                fail('patch_source_changed')
            objects.append(c.store_object(content))
            target = directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            target.chmod(row['mode'])
        if source_manifest(source) != original:
            fail('patch_source_changed')
        try:
            _apply(directory, diff)
            patched = source_manifest(directory)
        except (PatchCheckError, ContractError):
            fail('patch_diff_unsafe')
        if patched == original:
            fail('patch_diff_empty')
        if sum(row['size'] for row in patched.values()) > limit:
            fail('patch_snapshot_limit')
        for name, row in patched.items():
            content = read_bytes(directory / name, max_bytes=4 * 1024 * 1024)
            if digest(content) != row['sha256']:
                fail('patch_source_changed')
            objects.append(c.store_object(content))
    original_sha = c.store_object(canonical(original)); patched_sha = c.store_object(canonical(patched))
    objects.extend((original_sha, patched_sha))
    return dict(data, original_manifest_sha256=original_sha, patched_manifest_sha256=patched_sha,
        resources=[data['source_access']], state='proposed'), sorted(set(objects))


def record_patch_execution(c, grant, profile_id, operation_id, patch_id, arm, manifest):
    with c.lock():
        state = c.state()
        binding(c, state, grant)
        patch = state['patches'].get(patch_id)
        operation = state['environment_operations'].get(operation_id)
        if patch is None or arm not in ('original', 'patched'):
            fail('patch_identity_invalid')
        if (operation is None or operation['grant'] != grant or operation['profile_id'] != profile_id
                or operation['operation'] != 'execute' or operation.get('result') is None
                or operation['result']['status'] != 'settled'):
            fail('environment_observation_missing')
        logical = json.loads(c.read_object(patch[arm + '_manifest_sha256']))
        readonly = {name: dict(row, mode=0o555 if row['mode'] & 0o111 else 0o444) for name, row in logical.items()}
        if patch['source_access'] not in grant['resources'] or manifest not in (logical, readonly):
            fail('patch_copy_mismatch')
        data = {'operation_id': operation_id, 'patch_id': patch_id, 'arm': arm,
            'manifest_sha256': patch[arm + '_manifest_sha256']}
        if operation.get('patch_copy') is not None:
            if all(operation['patch_copy'][key] == value for key, value in data.items()):
                return {'status': 'recorded'}
            fail('patch_copy_conflict')
        sha = c.store_object(canonical({'grant': grant, 'profile_id': profile_id, **data, 'manifest': manifest}))
        return c._host('evidence_recorded', {'action': 'patch_execution', 'data': dict(data, receipt_sha256=sha), '_objects': [sha]})


def patch_checks(state, review, worker, references):
    patch_id = review['subject_id']
    rows = [state['experiments'][name] for name in references]
    for purpose in ('effect', 'control', 'normal_function', 'variant'):
        arms = {}
        for row in rows:
            binding = row.get('patch_copy')
            if (row['purpose'] == purpose and row['worker_id'] == worker['id'] and row['session_id'] == worker['session_id']
                    and binding and binding['patch_id'] == patch_id):
                arms.setdefault(binding['arm'], []).append(row)
        if set(arms) != {'original', 'patched'} or not any(comparable(left, right)
                and left['candidate_sha256'] == right['candidate_sha256'] and left['probe_sha256'] == right['probe_sha256']
                and left['environment_nonce'] != right['environment_nonce'] and left['clean_start'] and right['clean_start']
                for left in arms['original'] for right in arms['patched']):
            fail('patch_checks_incomplete')


def record_experiment_execution(c, grant, profile_id, operation_id, measurement):
    """Accept executor observations only; the worker channel cannot invoke this."""
    with c.lock():
        state = c.state()
        binding(c, state, grant)
        operation = state['environment_operations'].get(operation_id)
        if (operation is None or operation['grant'] != grant or operation['profile_id'] != profile_id
                or operation['operation'] != 'execute' or operation.get('result') is None
                or operation['result']['status'] != 'settled'):
            fail('environment_observation_missing')
        keys(measurement, ('instrument_id', 'instrument_sha256', 'candidate_sha256', 'probe_sha256',
            'conditions', 'reset', 'clean_start'), 'experiment_execution_invalid')
        instrument = state['instruments'].get(measurement['instrument_id'])
        if (instrument is None or instrument['artifact_sha256'] != measurement['instrument_sha256']
                or instrument['reset'] != measurement['reset'] or type(measurement['clean_start']) is not bool):
            fail('experiment_execution_invalid')
        mapping(measurement['conditions'])
        for name in ('instrument_sha256', 'candidate_sha256', 'probe_sha256'):
            c.read_object(measurement[name])
        if operation.get('measurement') is not None:
            if operation['measurement'] == measurement:
                return {'status': 'recorded'}
            fail('experiment_execution_conflict')
        sha = c.store_object(canonical({'grant': grant, 'profile_id': profile_id,
            'operation_id': operation_id, 'measurement': measurement}))
        return c._host('evidence_recorded', {'action': 'experiment_execution',
            'data': {'operation_id': operation_id, 'measurement': measurement, 'receipt_sha256': sha},
            '_objects': [sha, measurement['instrument_sha256'], measurement['candidate_sha256'], measurement['probe_sha256']]})


def current_closure(state, closure):
    unresolved = {name for name, row in state['tasks'].items() if row['status'] not in ('completed', 'reviewed_complete')}
    if not unresolved <= set(closure['remaining']):
        return False
    if closure['outcome'] == 'goal_met':
        if (not closure['claim_ids'] or any(state['claims'][name]['state'] != 'independently_confirmed' for name in closure['claim_ids'])
                or (state['scope']['goal_mode'] == 'broad' and unresolved)):
            return False
        if state['scope']['patch_required'] and not all(any(patch['claim_id'] == name and patch['state'] == 'accepted'
                for patch in state['patches'].values()) for name in closure['claim_ids']):
            return False
    return not any(row['state'] in ('pending', 'disputed') for row in state['obligations'].values())


def register_support_inputs(c, grant, inputs):
    from engagement_contract import source_manifest, read_bytes, ContractError
    with c.lock():
        state = c.state()
        c._authorize(state, grant)
        if not isinstance(inputs, dict) or not 1 <= len(inputs) <= 32:
            fail('support_inputs_invalid')
        registered, objects = {}, []
        for name, value in inputs.items():
            identifier(name)
            if name in {row['id'] for row in state['scope']['access']}:
                fail('support_inputs_invalid')
            keys(value, ('path', 'manifest_sha256'), 'support_inputs_invalid')
            try:
                source = Path(value['path'])
                manifest = source_manifest(source)
                if digest(canonical(manifest)) != value['manifest_sha256']:
                    fail('support_manifest_changed')
                if sum(row['size'] for row in manifest.values()) > 16 * 1024 * 1024:
                    fail('support_manifest_limit')
                for name_in_tree, row in manifest.items():
                    content = read_bytes(source / name_in_tree, max_bytes=4 * 1024 * 1024)
                    if digest(content) != row['sha256']:
                        fail('support_manifest_changed')
                    objects.append(c.store_object(content))
                if source_manifest(source) != manifest:
                    fail('support_manifest_changed')
            except (ContractError, TypeError):
                fail('support_manifest_changed')
            objects.append(c.store_object(canonical(manifest)))
            registered[name] = value['manifest_sha256']
        prior = state['support_inputs'].get(grant['dispatch_id'])
        if prior == registered:
            return {'status': 'recorded'}
        if any(row['grant']['dispatch_id'] == grant['dispatch_id'] for row in state['environment_operations'].values()):
            fail('support_registration_late')
        if prior is not None:
            fail('support_registration_conflict')
        return c._host('evidence_recorded', {'action': 'support_inputs_registered', 'data': {
            'grant': grant, 'inputs': registered}, '_objects': sorted(set(objects))})
