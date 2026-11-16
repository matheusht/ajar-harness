"""Public CLI -> real Runner and native sessions -> reviewed owned-fixture closure.

Provider responses are deterministic test data, not model-directed research. The
signed fixture, native runtimes, tool boundary, reviewer and cleanup are real.
"""
from __future__ import annotations

import json
from datetime import datetime
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import uuid

from check_linux_model_native_e2e import Provider, check, signed_inputs, verify_engagement_export
from check_engagement_contract_e2e import fixture_scope, resign_fixture
from engagement_controller import Controller

ROOT = Path(__file__).resolve().parents[3]


def content_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from content_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from content_strings(child)


def classify_lane(body, issued=None, compact_markers=None):
    previous = body.get('previous_response_id', '')
    for lane in ('lead', 'reviewer', 'helper'):
        if previous.startswith('public-' + lane + '-'):
            return lane
    messages = body.get('messages', body.get('input', []))
    messages = [{'role': 'user', 'content': messages}] if isinstance(messages, str) else messages
    matches = set()
    for message in messages:
        if not isinstance(message, dict):
            continue
        if message.get('type') == 'function_call':
            recorded = (issued or {}).get(message.get('call_id'))
            if recorded and message.get('name') == recorded[1]:
                matches.add(recorded[0])
        if message.get('role') == 'user':
            for value in content_strings(message.get('content', '')):
                for marker, lane in (compact_markers or {}).items():
                    if marker == value:
                        matches.add(lane)
        if message.get('role') != 'assistant':
            continue
        for call in message.get('tool_calls', []):
            if not isinstance(call, dict):
                continue
            recorded = (issued or {}).get(call.get('id'))
            function = call.get('function')
            if recorded and isinstance(function, dict) and function.get('name') == recorded[1]:
                matches.add(recorded[0])
    if len(matches) > 1:
        raise ValueError('public_lane_unavailable')
    if matches:
        return matches.pop()
    for message in messages:
        if not isinstance(message, dict) or message.get('role') != 'user':
            continue
        for text in content_strings(message.get('content', '')):
            if 'internal helper acting under the parent' in text:
                return 'helper'
            marker = 'Role and assignment:\n'
            if marker in text:
                assignment, _ = json.JSONDecoder().raw_decode(text.split(marker, 1)[1].lstrip())
                if assignment.get('role') in ('lead', 'reviewer'):
                    return assignment['role']
    raise ValueError('public_lane_unavailable')


def lane_shape(body, path=None):
    allowed = {'messages', 'input', 'previous_response_id', 'metadata', 'user', 'model', 'stream'}
    messages = body.get('messages', body.get('input', []))
    messages = [{'role': 'user', 'content': messages}] if isinstance(messages, str) else messages
    messages = messages if isinstance(messages, list) else []
    roles, user_markers = [], []
    omp_compaction_system = compaction_conversation = False
    for message in messages[:128]:
        if not isinstance(message, dict):
            roles.append('non_object')
            continue
        role = message.get('role')
        roles.append(role if role in ('user', 'assistant', 'system', 'developer', 'tool') else 'other')
        text = '\n'.join(content_strings(message.get('content', '')))
        if role in ('system', 'developer'):
            omp_compaction_system |= text.startswith('Summarize user–AI coding-assistant conversations in the exact specified structured format.')
        if role == 'user':
            compaction_conversation |= text.startswith('<conversation>\n')
            user_markers.append({'assignment': 'Role and assignment:\n' in text,
                'helper': 'internal helper acting under the parent' in text,
                'continuation': 'Continue the assigned research using the current native context.' in text})
    metadata = body.get('metadata')
    return {'path': path if path in ('/v1/chat/completions', '/v1/responses/compact', '/v1/responses') else 'other',
            'keys': sorted(key for key in body if key in allowed), 'message_count': len(messages),
            'roles': roles, 'user_markers': user_markers,
            'omp_compaction_system': omp_compaction_system, 'compaction_conversation': compaction_conversation,
            'has_tools': bool(body.get('tools')),
            'metadata_keys': sorted(key for key in metadata if key in ('session_id', 'thread_id', 'user_id'))
                if isinstance(metadata, dict) else [],
            'has_previous_response_id': isinstance(body.get('previous_response_id'), str)}


def routing_self_check():
    lead = 'Role and assignment:\n{"id":"lead-1","role":"lead","assignment":null}'
    reviewer = 'Role and assignment:\n{"id":"reviewer-1","role":"reviewer","assignment":null}'
    helper = 'You are an internal helper acting under the parent\'s identity and permissions.'
    assert classify_lane({'messages': [{'role': 'user', 'content': lead},
        {'role': 'assistant', 'tool_calls': [{'arguments': '{"role":"reviewer"}'}]},
        {'role': 'tool', 'content': '{"role":"reviewer","status":"pending"}'}]}) == 'lead'
    assert classify_lane({'messages': [{'role': 'user', 'content': reviewer}]}) == 'reviewer'
    assert classify_lane({'input': helper}) == 'helper'
    assert classify_lane({'previous_response_id': 'public-lead-2', 'input': reviewer}) == 'lead'
    continued = {'messages': [{'role': 'system', 'content': 'fixture'},
        {'role': 'system', 'content': 'fixture'}, {'role': 'user', 'content': 'fixture'},
        {'role': 'assistant', 'tool_calls': [{'id': 'call-public-lead-1', 'type': 'function',
            'function': {'name': 'bash', 'arguments': '{}'}}]},
        {'role': 'tool', 'content': 'result'}, {'role': 'assistant', 'content': 'done'},
        {'role': 'user', 'content': 'Continue the assigned research using the current native context.'}]}
    assert classify_lane(continued, {'call-public-lead-1': ('lead', 'bash')}) == 'lead'
    for issued in ({}, {'call-public-lead-1': ('lead', 'engagement_status')}):
        try:
            classify_lane(continued, issued)
            raise AssertionError('unknown or mismatched call accepted')
        except ValueError:
            pass
    mixed = {'messages': continued['messages'] + [{'role': 'assistant', 'tool_calls': [
        {'id': 'call-public-reviewer-1', 'function': {'name': 'engagement_read'}}]}]}
    try:
        classify_lane(mixed, {'call-public-lead-1': ('lead', 'bash'),
                              'call-public-reviewer-1': ('reviewer', 'engagement_read')})
        raise AssertionError('ambiguous issued calls accepted')
    except ValueError:
        pass
    compact = {'input': [{'type': 'function_call', 'call_id': 'call-public-lead-1',
                          'name': 'bash', 'arguments': '{}'}]}
    assert classify_lane(compact, {'call-public-lead-1': ('lead', 'bash')}) == 'lead'
    for body in ({'input': []}, {'input': [{'type': 'function_call', 'call_id': 'call-public-lead-1', 'name': 'other'}]}):
        try:
            classify_lane(body, {'call-public-lead-1': ('lead', 'bash')})
            raise AssertionError('unrecognized compact history accepted')
        except ValueError:
            pass
    shape = lane_shape({'messages': [{'role': 'user', 'content': 'private fixture sentinel'}],
                        'metadata': {'session_id': 'private fixture sentinel'}})
    assert 'private fixture sentinel' not in json.dumps(shape)


def expected_closure_cancellation(*, authorized, expected_bytes, received_bytes, started, finished, events, status, workers):
    if (authorized is not True or type(expected_bytes) is not int or type(received_bytes) is not int
            or not 0 <= received_bytes < expected_bytes or status not in ('closing', 'closed')
            or not workers or any(worker not in ('revoked', 'stopped') for worker in workers)
            or not isinstance(started, datetime) or not isinstance(finished, datetime) or finished < started):
        return False
    for event in events:
        try:
            if (event['type'] == 'closure_stopping' and event['payload']['reason'] == 'reviewed_closure'
                    and type(event['sequence']) is int and event['sequence'] > 0
                    and re.fullmatch(r'sha256:[0-9a-f]{64}', event['sha256'])
                    and started <= datetime.fromisoformat(event['at']) <= finished):
                return True
        except (KeyError, TypeError, ValueError):
            continue
    return False


def compact_self_check():
    script = Script('omp', None)
    script.issued_calls['call-public-lead-1'] = ('lead', 'bash')
    compact = {'input': [{'type': 'function_call', 'call_id': 'call-public-lead-1', 'name': 'bash'}]}
    output = script.compact_response(compact)['output']
    assert output[-1]['type'] == 'compaction_summary' and script.compaction_count == 1
    assert classify_lane({'messages': [output[0]]}, script.issued_calls, script.compact_markers) == 'lead'
    try:
        script.compact_response({'input': []})
        raise AssertionError('unknown compact history accepted')
    except ValueError:
        pass


def public_worker_failures_acceptable(failures, status, cleanup, review_status):
    if not isinstance(failures, dict):
        return False
    if not failures:
        return True
    return (status == 'closed' and cleanup == 'verified' and review_status == 'accepted'
            and all(worker in ('lead-1', 'reviewer-1') and code == 'engagement_stopped'
                    for worker, code in failures.items()))


def worker_failure_self_check():
    assert public_worker_failures_acceptable({}, 'closed', 'verified', 'accepted')
    assert public_worker_failures_acceptable({'lead-1': 'engagement_stopped'}, 'closed', 'verified', 'accepted')
    assert not public_worker_failures_acceptable({'lead-1': 'native_usage_invalid'}, 'closed', 'verified', 'accepted')
    assert not public_worker_failures_acceptable({'lead-1': 'engagement_stopped'}, 'active', 'verified', 'accepted')
    assert not public_worker_failures_acceptable({'lead-1': 'engagement_stopped'}, 'closed', 'pending', 'accepted')
    assert not public_worker_failures_acceptable({'lead-1': 'engagement_stopped'}, 'closed', 'verified', 'pending')
    assert not public_worker_failures_acceptable({'unknown': 'engagement_stopped'}, 'closed', 'verified', 'accepted')
    assert not public_worker_failures_acceptable({'lead-1': None}, 'closed', 'verified', 'accepted')
    assert not public_worker_failures_acceptable(['native_usage_invalid'], 'closed', 'verified', 'accepted')
    assert not public_worker_failures_acceptable(None, 'closed', 'verified', 'accepted')


def cancellation_self_check():
    start = datetime.fromisoformat('2026-11-16T12:00:00+00:00')
    end = datetime.fromisoformat('2026-11-16T12:00:02+00:00')
    event = {'type': 'closure_stopping', 'at': '2026-11-16T12:00:01+00:00',
             'sequence': 7, 'sha256': 'sha256:' + '1' * 64, 'payload': {'reason': 'reviewed_closure'}}
    good = {'authorized': True, 'expected_bytes': 100, 'received_bytes': 30,
            'started': start, 'finished': end, 'events': [event], 'status': 'closed',
            'workers': ['revoked', 'stopped']}
    assert expected_closure_cancellation(**good)
    for changes in ({'authorized': False}, {'received_bytes': 100}, {'events': []},
                    {'finished': start}, {'status': 'active'}, {'workers': ['running']},
                    {'events': [{**event, 'at': '2026-11-16T12:00:03+00:00'}]},
                    {'events': [{**event, 'payload': {'reason': 'other'}}]}):
        assert not expected_closure_cancellation(**{**good, **changes})


def packet_read_update(current, row, sha):
    try:
        if row['sha256'] != sha or row['source'] != 'published_evidence' or row['encoding'] != 'utf-8':
            raise ValueError()
        offset, size, total, following = (row[key] for key in ('offset', 'bytes', 'total_bytes', 'next_offset'))
        raw = row['content'].encode('utf-8')
        if (any(type(value) is not int for value in (offset, size, total)) or offset < 0
                or size != len(raw) or offset + size > total or offset > len(current)):
            raise ValueError()
        if offset < len(current):
            if current[offset:offset + size] != raw:
                raise ValueError()
            return current, False
        current += raw
        if following is not None:
            if type(following) is not int or following != len(current) or following >= total:
                raise ValueError()
            return current, False
        if (len(current) != total or 'sha256:' + hashlib.sha256(current).hexdigest() != sha
                or json.loads(current).get('kind') != 'engagement-review-packet-v2'):
            raise ValueError()
        return current, True
    except (KeyError, TypeError, AttributeError, ValueError, UnicodeError):
        raise ValueError('review_packet_invalid') from None


def json_objects(value, depth=0):
    if depth > 12:
        return
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from json_objects(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            yield from json_objects(child, depth + 1)
    elif isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (ValueError, TypeError):
            return
        if isinstance(decoded, (dict, list)):
            yield from json_objects(decoded, depth + 1)


def packet_self_check():
    raw = b'{"kind":"engagement-review-packet-v2","data":"fixture"}'
    sha = 'sha256:' + hashlib.sha256(raw).hexdigest()
    def chunk(start, end):
        return {'sha256': sha, 'source': 'published_evidence', 'encoding': 'utf-8',
                'offset': start, 'bytes': end - start, 'total_bytes': len(raw),
                'next_offset': end if end < len(raw) else None, 'content': raw[start:end].decode()}
    content, done = packet_read_update(b'', chunk(0, 20), sha)
    assert not done and content == raw[:20]
    assert packet_read_update(content, chunk(20, len(raw)), sha) == (raw, True)
    nested = [{'output': json.dumps({'content': [{'type': 'text', 'text': json.dumps(chunk(0, 20))}]})}]
    assert any(row.get('sha256') == sha for row in json_objects(nested))
    corrupt = chunk(20, len(raw)); corrupt['content'] = 'x' * (len(raw) - 20)
    try:
        packet_read_update(content, corrupt, sha)
        raise AssertionError('changed packet bytes were accepted')
    except ValueError:
        pass


class Script:
    def __init__(self, runtime, engagement):
        self.runtime, self.engagement = runtime, engagement
        self.lock = threading.Lock()
        self.counts = {'lead': 0, 'reviewer': 0, 'helper': 0}
        self.lead_probe = self.spawned = self.reviewer_read = False
        self.source_observed = self.packet_observed = False
        self.helper_read = self.helper_read_observed = False
        self.helper_status_observed = False
        self.packet_bytes = b''
        self.lane_diagnostics = []
        self.issued_calls = {}
        self.compact_markers = {}
        self.compaction_count = 0
        self.tool_error_codes = set()

    def status_snapshot(self, started, finished):
        try:
            controller = Controller(self.engagement)
            with controller.lock():
                journal = controller._events()
                state = controller._replay(journal)
            allowed = {'active', 'blocked', 'closed', 'closing', 'completed', 'pending', 'preparing', 'rejected', 'running',
                       'started', 'stopped', 'stopping', 'revoked'}
            def safe(value):
                return value if value in allowed else 'other'
            events = [event for event in journal
                      if event.get('type') in ('closure_stopping', 'stop_requested')
                      and started <= datetime.fromisoformat(event['at']) <= finished]
            lifecycle = []
            for event in journal:
                if event.get('type') not in ('worker_revoked', 'worker_resumed', 'worker_started'):
                    continue
                if datetime.fromisoformat(event['at']) > finished:
                    continue
                payload = event.get('payload', {})
                worker = payload.get('worker_id')
                reason = payload.get('reason')
                lifecycle.append({'sequence': event['sequence'], 'sha256': event['sha256'],
                    'type': event['type'], 'at': event['at'],
                    'worker_id': worker if worker in ('lead-1', 'reviewer-1') else 'other',
                    'generation': payload.get('generation') if type(payload.get('generation')) is int else None,
                    'reason': reason if reason in ('worker_segment_ended', 'coordinator_exit', 'controller_resume', 'next_task',
                                         'review_obligation', 'native-boundary-finish', 'native-boundary-recovery') else 'other'})
            return {'read_started': started.isoformat(), 'read_finished': finished.isoformat(),
                    'worker_lifecycle': lifecycle[-12:],
                    'stop_events': [{**{key: event[key] for key in ('sequence', 'sha256', 'type', 'at')},
                                     'payload': {'reason': 'reviewed_closure'}} for event in events
                                    if event.get('type') == 'closure_stopping'
                                    and event.get('payload', {}).get('reason') == 'reviewed_closure'],
                    'engagement': safe(state.get('status')),
                    'lead': safe(state.get('workers', {}).get('lead-1', {}).get('status')),
                    'reviewer': safe(state.get('workers', {}).get('reviewer-1', {}).get('status')),
                    'lead_generation': state.get('workers', {}).get('lead-1', {}).get('generation'),
                    'reviewer_generation': state.get('workers', {}).get('reviewer-1', {}).get('generation')}
        except Exception:
            return {'status': 'unavailable'}

    def compact_response(self, body):
        with self.lock:
            lane = classify_lane(body, self.issued_calls, self.compact_markers)
            marker = 'owned-fixture-compact-' + uuid.uuid4().hex
            self.compact_markers[marker] = lane
            self.compaction_count += 1
            return {'output': [{'type': 'message', 'role': 'user',
                                'content': [{'type': 'input_text', 'text': marker}]},
                               {'type': 'compaction_summary', 'summary': 'Owned deterministic fixture continuation.'}]}

    def __call__(self, body, sequence, path=None):
        with self.lock:
            try:
                lane = classify_lane(body, self.issued_calls, self.compact_markers)
            except ValueError:
                if len(self.lane_diagnostics) < 8:
                    self.lane_diagnostics.append(lane_shape(body, path))
                raise
            self.counts[lane] += 1
            identity = 'public-' + lane + '-' + str(self.counts[lane])
            controller = Controller(self.engagement)
            state = controller.state()
            outputs = [row.get('output') for row in body.get('input', []) if isinstance(row, dict) and row.get('call_id')]
            outputs += [row.get('content') for row in body.get('messages', []) if isinstance(row, dict) and row.get('role') == 'tool']
            for row in json_objects(outputs):
                for key in ('code', 'error'):
                    value = row.get(key)
                    if isinstance(value, str) and re.fullmatch(r'[a-z][a-z_]{2,79}', value):
                        self.tool_error_codes.add(value)
            output_text = '\n'.join(content_strings(outputs))
            if lane == 'helper' and self.counts[lane] > 1:
                self.helper_status_observed |= 'lead-1' in output_text and '"assignment":' in output_text
            self.source_observed |= 'HARMLESS_SOURCE' in output_text
            helpers = list(state['helpers'].values())
            self.helper_read_observed |= bool(self.helper_read and helpers and helpers[0]['helper_id'] in output_text
                                              and '"status":"completed"' in output_text)
            review = state['reviews'].get('review-dry', {})
            if lane == 'reviewer' and review.get('packet_sha256') and not self.packet_observed:
                for row in json_objects(outputs):
                    if row.get('sha256') == review['packet_sha256'] and row.get('source') == 'published_evidence':
                        self.packet_bytes, self.packet_observed = packet_read_update(
                            self.packet_bytes, row, review['packet_sha256'])
                        if self.packet_observed:
                            break
            name, arguments = self.action(lane, state)
            if name:
                self.issued_calls['call-' + identity] = (lane, name)
            return responses_frames(identity, name, arguments)

    def action(self, lane, state):
        if lane == 'helper':
            if self.counts[lane] == 1:
                return 'engagement_status', {'since': None, 'limit': 10}
            if not self.helper_status_observed:
                raise ValueError('helper_authority_not_observed')
            return None, None
        if lane == 'reviewer':
            review = state['reviews'].get('review-dry')
            if not review:
                return None, None
            if not self.packet_observed:
                self.reviewer_read = True
                return 'engagement_read', {'sha256': review['packet_sha256'],
                                           'offset': len(self.packet_bytes), 'max_bytes': 4096}
            if review['status'] == 'pending':
                return self.submit(state, 'review_result', {'review_id': 'review-dry',
                    'packet_sha256': review['packet_sha256'], 'disposition': 'accept',
                    'evidence_refs': [], 'contrary_refs': ['owned-observation'],
                    'reason': 'Independent review is limited to this harmless owned fixture.'})
            return None, None
        if not self.lead_probe:
            self.lead_probe = True
            if self.runtime == 'codex':
                return 'exec_command', {'cmd': 'cat /input/source-main/main.py', 'max_output_tokens': 200}
            return 'bash', {'command': 'cat /input/source-main/main.py', 'timeout': 10}
        if not self.spawned:
            if not self.source_observed:
                raise ValueError('source_output_not_observed')
            self.spawned = True
            return 'engagement_helper', {'action': 'spawn', 'prompt': 'Read the current assignment through the protected status tool.'}
        helpers = list(state['helpers'].values())
        if not helpers or helpers[0]['status'] in ('starting', 'active'):
            time.sleep(.25)
            return None, None
        if helpers[0]['status'] != 'completed':
            raise ValueError('helper_not_completed')
        if not self.helper_read:
            self.helper_read = True
            return 'engagement_helper', {'action': 'read', 'helper_id': helpers[0]['helper_id']}
        if not self.helper_read_observed:
            raise ValueError('helper_output_not_observed')
        if 'owned-observation' not in state['publications']:
            return self.submit(state, 'publish', {'publication_id': 'owned-observation', 'kind': 'observation',
                'subject': 'Owned source inspection', 'body': 'The lead read the harmless fixture source.',
                'refs': [], 'supersedes': [], 'artifacts': []})
        if 'dry' not in state['closures']:
            return self.submit(state, 'closure_request', {'closure_id': 'dry', 'outcome': 'covered_dry',
                'claim_ids': [], 'reason': 'Only the harmless owned fixture was inspected.'})
        if 'reviewer-1' not in state['workers']:
            return self.submit(state, 'worker_request', {'worker_id': 'reviewer-1', 'role': 'reviewer',
                'profile_id': 'runtime-main', 'question': 'Review the bounded owned fixture evidence.'})
        if 'review-dry' not in state['reviews']:
            return self.submit(state, 'review_request', {'review_id': 'review-dry', 'kind': 'closure',
                'subject_id': 'dry', 'reviewer_id': 'reviewer-1'})
        time.sleep(.25)
        return None, None

    @staticmethod
    def submit(state, kind, payload):
        return 'engagement_submit', {'request': {'request_id': uuid.uuid4().hex,
            'expected_revision': state['revision'], 'type': kind, 'payload': payload}}


def responses_frames(identity, name, arguments):
    item = ({'id': 'fc_' + identity, 'type': 'function_call', 'call_id': 'call-' + identity,
             'name': name, 'arguments': json.dumps(arguments)} if name else
            {'id': 'msg_' + identity, 'type': 'message', 'role': 'assistant',
             'content': [{'type': 'output_text', 'text': 'Fixture turn complete.'}]})
    response = {'id': identity, 'object': 'response', 'status': 'completed', 'output': [item],
                'usage': {'input_tokens': 10, 'output_tokens': 10, 'total_tokens': 20}}
    events = [{'type': 'response.created', 'response': {**response, 'status': 'in_progress', 'output': []}},
              {'type': 'response.output_item.added', 'output_index': 0, 'item': item},
              {'type': 'response.output_item.done', 'output_index': 0, 'item': item},
              {'type': 'response.completed', 'response': response}]
    return [('event: ' + event['type'] + '\ndata: ' + json.dumps(dict(event, sequence_number=i)) + '\n\n').encode()
            for i, event in enumerate(events)]

def run_public(root, fixture, result):
    from check_linux_model_native_e2e import tool_bundle
    routing_self_check()
    packet_self_check()
    cancellation_self_check()
    worker_failure_self_check()
    compact_self_check()
    fixture.public_run = True
    root.mkdir(mode=0o700)
    installed = result.get('tool_installation', {})
    bundle = installed.get('tool_bundle') or installed.get('profile_fields', {}).get('tool_bundle')
    if bundle is None:
        bundle = tool_bundle(fixture, result)
    provider = Provider(root / 'provider-tls', fixture.runtime, 'fake-public-run-' + uuid.uuid4().hex)
    provider.command = 'unused'
    engagement = root / 'engagement'
    script = Script(fixture.runtime, engagement)
    provider.public_frames = script
    child = None
    try:
        inputs = signed_inputs(root, fixture, provider, bundle, getattr(fixture, 'codex_tool_policy', None))
        scope = fixture_scope(inputs)
        scope['limits']['hard']['invocations'] = 200
        resign_fixture(inputs, scope)
        home = root / 'home'; home.mkdir(mode=0o700)
        environment = dict(os.environ, HOME=str(home), OPENAI_API_KEY=provider.secret, SSL_CERT_FILE=str(provider.ca))
        command = [sys.executable, str(ROOT / 'tools/native_engagement.py'), 'run', '--inputs', str(inputs),
                   '--engagement-root', str(engagement)]
        child = subprocess.Popen(command, env=environment, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        try:
            stdout, _ = child.communicate(timeout=200)
        except subprocess.TimeoutExpired:
            subprocess.run([sys.executable, str(ROOT / 'tools/native_engagement.py'), 'stop', '--engagement-root', str(engagement)],
                           env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
            stdout, _ = child.communicate(timeout=30)
        try:
            cli = json.loads(stdout)
        except (ValueError, TypeError):
            cli = {}
        allowed_statuses = {'active', 'blocked', 'closed', 'completed', 'rejected', 'stopped', 'stopping'}
        cli_status = cli.get('status') if cli.get('status') in allowed_statuses else 'unavailable'
        cli_code = cli.get('code')
        if not isinstance(cli_code, str) or not re.fullmatch(r'[a-z_]{1,100}', cli_code):
            cli_code = None
        failures = cli.get('failures')
        safe_failures = {worker: code for worker, code in failures.items()
                         if worker in ('lead-1', 'reviewer-1') and isinstance(code, str)
                         and re.fullmatch(r'[a-z_]{1,100}', code)} if isinstance(failures, dict) else {}
        result['public_cli'] = {'returncode': child.returncode, 'status': cli_status, 'code': cli_code,
                                'worker_failures': safe_failures}
        state = Controller(engagement).state()
        result['public_cli']['invocation_statuses'] = [
            row.get('status') if row.get('status') in ('pending', 'completed', 'aborted', 'error', 'local_only', 'unknown') else 'other'
            for row in list(state.get('invocations', {}).values())[-16:]]
        public = {'cli_returncode': child.returncode, 'cli_status': cli_status,
                  'status': state['status'], 'cleanup': state['cleanup'], 'provider_lanes': script.counts,
                  'helper_statuses': [row.get('status') for row in state['helpers'].values()],
                  'review_status': state['reviews'].get('review-dry', {}).get('status'),
                  'lead_session_present': bool(state['workers']['lead-1'].get('session_id')),
                  'reviewer_session_present': bool(state['workers'].get('reviewer-1', {}).get('session_id')),
                  'source_output_observed': script.source_observed, 'review_packet_observed': script.packet_observed,
                  'helper_read_observed': script.helper_read_observed,
                  'helper_status_observed': script.helper_status_observed,
                  'sessions_distinct': state['workers']['lead-1'].get('session_id') !=
                                       state['workers'].get('reviewer-1', {}).get('session_id'),
                  'provider_errors': provider.errors[:8], 'tool_error_codes': sorted(script.tool_error_codes)[:32],
                  'compaction_count': script.compaction_count,
                  'provider_error_frames': provider.error_frames,
                  'provider_fixture_error_codes': provider.public_error_codes,
                  'provider_json_parse_diagnostics': provider.json_parse_diagnostics,
                  'provider_lane_diagnostics': script.lane_diagnostics}
        result['public_runner'] = public
        if state['cleanup'] != 'verified':
            result['boundary_cleanup_error'] = 'public_cleanup_unresolved'
        check(result, 'public Runner has no unexpected worker failures',
              public_worker_failures_acceptable(failures, state['status'], state['cleanup'], public['review_status']))
        check(result, 'public CLI closes reviewed owned fixture', child.returncode == 0 and state['status'] == 'closed'
              and state['cleanup'] == 'verified' and public['review_status'] == 'accepted'
              and public['lead_session_present'] and public['reviewer_session_present'] and public['sessions_distinct']
              and public['source_output_observed'] and public['review_packet_observed'])
        cancellation_rows = []
        for row in provider.json_parse_diagnostics:
            snapshot = row.get('controller_snapshot', {})
            try:
                matched = expected_closure_cancellation(
                    authorized=row.get('authenticated'), expected_bytes=row['expected_bytes'],
                    received_bytes=row['received_bytes'], started=datetime.fromisoformat(snapshot['read_started']),
                    finished=datetime.fromisoformat(snapshot['read_finished']), events=snapshot['stop_events'],
                    status=state['status'], workers=[worker['status'] for worker in state['workers'].values()])
            except (KeyError, TypeError, ValueError):
                matched = False
            cancellation_rows.append(matched)
        cancellation_count = provider.errors.count('incomplete_authenticated_request')
        public['verified_closure_cancellations'] = sum(cancellation_rows)
        check(result, 'public Runner provider has no unexpected transport or fixture errors',
              len(provider.errors) == cancellation_count == len(cancellation_rows)
              and all(cancellation_rows))
        check(result, 'public Runner native helper completes', public['helper_statuses'] == ['completed']
              and public['helper_read_observed'] and public['helper_status_observed'])
        result['native_execution'] = 'public_runner_native_sessions_completed'
        result['public_runner']['not_covered'] = ['live_model_direction', 'active_helper_stop', 'usage_count_once',
            'reference_fetch_retention_failure', 'reference_version_update',
            'independent_technique_evaluation_and_withdrawal']
        verify_engagement_export(Controller(engagement), root, result)
        check(result, 'public Runner export verified', result['export_verification']['status'] == 'passed')
    finally:
        if child is not None and child.poll() is None:
            result['boundary_cleanup_error'] = 'public_runner_still_active'
            provider.close()
            raise RuntimeError('public_fixture_cleanup_unresolved')
        provider.close()
