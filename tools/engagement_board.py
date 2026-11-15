"""Read-only shared research views over the controller's existing journal."""
from __future__ import annotations

import base64
import copy
import json

from engagement_contract import canonical
from engagement_controller import fail, integer

COLLECTIONS = {'task': 'tasks', 'publication': 'publications', 'instrument': 'instruments',
               'experiment': 'experiments', 'claim': 'claims', 'review': 'reviews',
               'obligation': 'obligations', 'message': 'messages'}
CREATES = {'task_create': ('task', 'task_id'), 'publish': ('publication', 'publication_id'),
           'instrument_register': ('instrument', 'instrument_id'), 'experiment_record': ('experiment', 'experiment_id'),
           'claim_propose': ('claim', 'claim_id'), 'review_request': ('review', 'review_id'),
           'strategy_challenge': ('obligation', 'obligation_id'), 'team_message': ('message', 'message_id')}


def rows(state, events):
    sources = {}
    for event in events:
        request = event['payload'] if event['type'] == 'request_accepted' else {}
        if request.get('type') in CREATES:
            kind, key = CREATES[request['type']]
            sources[kind, request['payload'][key]] = {
                name: event[name] for name in ('sequence', 'sha256', 'actor', 'at')}
    result = []
    for kind, collection in COLLECTIONS.items():
        corrections = {}
        for identity, record in state[collection].items():
            for old in record.get('supersedes', []):
                corrections.setdefault(old, []).append(identity)
        for identity, record in state[collection].items():
            source = sources.get((kind, identity))
            result.append({'kind': kind, 'id': identity, 'record': copy.deepcopy(record),
                'author': record.get('author') or (source['actor']['id'] if source else None),
                'source_event': source, 'superseded_by': corrections.get(identity, []),
                'verification_state': record['state'] if kind == 'claim' else
                    ('published_unverified' if kind in ('publication', 'message') else 'not_a_claim')})
    return sorted(result, key=lambda row: (row['kind'], row['id']))


def page(controller, events, state, worker, *, query, kinds, since, limit):
    if not isinstance(query, str) or len(query.encode()) > 1024:
        fail('board_query_invalid')
    if kinds is None:
        kinds = sorted(COLLECTIONS)
    if (not isinstance(kinds, list) or not kinds or
            any(not isinstance(kind, str) or kind not in COLLECTIONS for kind in kinds) or
            len(kinds) != len(set(kinds))):
        fail('board_kinds_invalid')
    kinds = sorted(kinds)
    if not integer(limit, 1, 100):
        fail('page_limit_invalid')
    revision, offset = len(events), 0
    snapshot = controller._encode_cursor(state, events[-1])
    if since is not None:
        try:
            if not isinstance(since, str) or len(since) > 8192:
                fail('board_cursor_invalid')
            value = json.loads(base64.urlsafe_b64decode(since + '=' * (-len(since) % 4)))
            if (not isinstance(value, list) or len(value) != 5 or value[0] != 'board-v1'
                    or not integer(value[2]) or value[3:] != [query, kinds]):
                fail('board_cursor_invalid')
            snapshot, offset = value[1:3]
            revision = controller._cursor(state, events, snapshot)
            if not revision:
                fail('board_cursor_invalid')
        except (ValueError, TypeError, UnicodeError):
            fail('board_cursor_invalid')
    frozen = state if revision == len(events) else controller._replay(events[:revision])
    matches = [row for row in rows(frozen, events[:revision]) if row['kind'] in kinds and
               query.casefold() in canonical(row).decode().casefold()]
    if offset > len(matches):
        fail('board_cursor_invalid')
    selected, size = [], 0
    for row in matches[offset:offset + limit]:
        amount = len(canonical(row))
        if selected and size + amount > 512 * 1024:
            break
        selected.append(row)
        size += amount
    end = offset + len(selected)
    more = end < len(matches)
    cursor = base64.urlsafe_b64encode(canonical(['board-v1', snapshot, end, query, kinds])).decode().rstrip('=') if more else None
    return {'view': 'board', 'engagement_id': state['engagement_id'], 'status': state['status'],
            'authority_policy': state['scope'].get('authority_policy', 'legacy-confirmation'),
            'revision': state['revision'], 'snapshot_revision': revision,
            'evidence_class': state['evidence_class'], 'assignment': worker['assignment'] if worker else None,
            'query': query, 'kinds': kinds, 'items': selected, 'total_matches': len(matches),
            'has_more': more, 'next_cursor': cursor}


def notices(controller, events, state, worker, *, since, limit):
    if not integer(since, 0, len(events)) or not integer(limit, 1, 100):
        fail('notice_cursor_invalid')
    acknowledged = controller._cursor(state, events, worker['cursor'])
    start = max(since, acknowledged)
    selected = events[start:start + limit]
    items = []
    assignment = worker['assignment']
    resources = set(state['tasks'][assignment['task_id']]['resources']) if assignment else set()
    for event in selected:
        if event['actor'].get('kind') == 'worker' and event['actor'].get('id') == worker['id']:
            continue
        request = event['payload'] if event['type'] == 'request_accepted' else {}
        kind, data = request.get('type'), request.get('payload', {})
        if kind not in CREATES and kind not in ('task_result', 'review_result', 'review_response', 'task_assign'):
            continue
        if kind == 'team_message':
            relevant = worker['id'] in data['recipient_ids']
        else:
            task = state['tasks'].get(data.get('task_id'), {})
            review = state['reviews'].get(data.get('review_id'), {})
            related = set(data.get('resources', task.get('resources', review.get('resources', []))))
            relevant = (worker['role'] == 'lead' or kind in ('publish', 'instrument_register') or
                        data.get('worker_id') == worker['id'] or review.get('reviewer_id') == worker['id'] or
                        bool(resources & related))
        if not relevant:
            continue
        preview = str(data.get('body', data.get('result', data.get('reason', ''))))
        subject = str(data.get('subject', data.get('question', kind)))
        items.append({name: event[name] for name in ('sequence', 'sha256', 'actor')})
        items[-1].update(type=kind, subject=subject[:256], preview=preview[:1024],
            truncated=len(subject) > 256 or len(preview) > 1024,
            read_since=controller._encode_cursor(state, events[event['sequence'] - 2]) if event['sequence'] > 1 else None)
    return {'items': items, 'next_sequence': start + len(selected)}
