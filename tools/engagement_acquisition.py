"""Protected acquisition provenance; never grants target or provider authority."""
from urllib.parse import urlsplit
import re

from engagement_contract import canonical, digest
from engagement_controller import fail, identifier, keys
from target_accounts import _route_origin

KIND = 'acquisition-network-observation-v1'
COMMON = {'kind', 'phase', 'operation_id', 'origin', 'method', 'path_sha256', 'display_url'}
RESULT = {'status', 'http_status', 'request_bytes', 'response_bytes', 'body_complete',
          'body_kind', 'response_sha256'}


def validate_observation(value):
    phase = value.get('phase') if isinstance(value, dict) else None
    keys(value, COMMON | (RESULT if phase == 'result' else set()), 'network_observation_invalid')
    if value['kind'] != KIND or phase not in ('intent', 'result') or value['method'] not in ('GET', 'HEAD'):
        fail('network_observation_invalid')
    identifier(value['operation_id'])
    if not isinstance(value['path_sha256'], str) or not re.fullmatch('sha256:[0-9a-f]{64}', value['path_sha256']):
        fail('network_observation_invalid')
    try:
        parsed = urlsplit(value['origin'])
        host = '[' + parsed.hostname + ']' if ':' in parsed.hostname else parsed.hostname
        if (parsed.scheme not in ('http', 'https') or parsed.username is not None or parsed.password is not None
                or parsed.path or parsed.query or parsed.fragment
                or value['origin'] != f'{parsed.scheme}://{host}:{parsed.port}'):
            fail('network_observation_invalid')
        display = value['display_url']
        if display is not None:
            shown = urlsplit(display)
            if (not isinstance(display, str) or len(display) > 8192 or shown.query or shown.fragment
                    or shown.username is not None or shown.password is not None
                    or (shown.scheme, shown.hostname, shown.port) != (parsed.scheme, parsed.hostname, parsed.port)):
                fail('network_observation_invalid')
    except (TypeError, ValueError, AttributeError):
        fail('network_observation_invalid')
    if phase == 'result':
        code = value['http_status']
        if (value['status'] not in ('settled', 'unknown')
                or (code is not None and (type(code) is not int or not 100 <= code <= 599))
                or type(value['request_bytes']) is not int or value['request_bytes'] != 0
                or type(value['response_bytes']) is not int or value['response_bytes'] < 0
                or type(value['body_complete']) is not bool or value['body_kind'] not in ('absent', 'range', 'whole')):
            fail('network_observation_invalid')
        complete, kind, sha = value['body_complete'], value['body_kind'], value['response_sha256']
        absent = value['method'] == 'HEAD' or code in (204, 304) or (code is not None and 100 <= code < 200)
        expected = 'absent' if absent or code is None else 'range' if code == 206 else 'whole'
        if (kind != expected or (complete and (value['status'] != 'settled' or code is None))
                or (kind == 'absent' and value['response_bytes'] != 0)):
            fail('network_observation_invalid')
        if complete and kind != 'absent':
            if not isinstance(sha, str) or not re.fullmatch('sha256:[0-9a-f]{64}', sha):
                fail('network_observation_invalid')
        elif sha is not None:
            fail('network_observation_invalid')
    return phase


def record(c, grant, profile_id, nonce, observation, *, target_nonce=None):
    phase = validate_observation(observation)
    if target_nonce is not None:
        fail('network_application_state_invalid')
    with c.lock():
        state = c.state()
        c.bind_grant(state, grant)
        scope = state['scope']
        environment = state['environments'].get(nonce)
        if (environment is None or environment['profile_id'] != profile_id
                or environment['worker_id'] != grant['worker_id'] or environment['generation'] != grant['generation']):
            fail('network_environment_invalid')
        origin = observation['origin']
        if (origin not in {_route_origin(row) for row in scope['network']['acquisition']}
                or origin in {_route_origin(row) for group in ('target', 'provider') for row in scope['network'][group]}
                or not any(row['profile_id'] == profile_id and 'acquisition' in row['capabilities'] for row in scope['environments'])):
            fail('network_effect_forbidden')
        document = {'grant': grant, 'profile_id': profile_id, 'environment_nonce': nonce, 'observation': observation}
        sha = digest(canonical(document))
        prior = state['network_operations'].get(observation['operation_id'])
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
                    or any(prior['intent'][key] != observation[key] for key in COMMON - {'phase'})
                    or (prior['result'] is not None and not
                        (prior['result']['status'] == 'unknown' and observation['status'] == 'settled'))):
                fail('network_operation_conflict')
        sha = c.store_object(canonical(document))
        return c._host('evidence_recorded', {'action': 'network_observation',
            'data': {**document, 'receipt_sha256': sha}, '_objects': [sha]})


def projection(row):
    """Bind comparison to transfer facts, without treating download as execution."""
    return {**{key: row['intent'][key] for key in ('origin', 'method', 'path_sha256')},
            **{key: row['result'][key] for key in ('http_status', 'body_complete', 'body_kind', 'response_sha256')}}
