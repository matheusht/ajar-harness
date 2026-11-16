"""Public CLI -> real Runner and native sessions -> reviewed owned-fixture closure.

Provider responses are deterministic test data, not model-directed research. The
signed fixture, native runtimes, tool boundary, reviewer and cleanup are real.
"""
from __future__ import annotations

import json
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


def classify_lane(body):
    previous = body.get('previous_response_id', '')
    for lane in ('lead', 'reviewer', 'helper'):
        if previous.startswith('public-' + lane + '-'):
            return lane
    messages = body.get('messages', body.get('input', []))
    messages = [{'role': 'user', 'content': messages}] if isinstance(messages, str) else messages
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


def lane_shape(body):
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
    return {'keys': sorted(key for key in body if key in allowed), 'message_count': len(messages),
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
    shape = lane_shape({'messages': [{'role': 'user', 'content': 'private fixture sentinel'}],
                        'metadata': {'session_id': 'private fixture sentinel'}})
    assert 'private fixture sentinel' not in json.dumps(shape)


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

    def __call__(self, body, sequence):
        with self.lock:
            try:
                lane = classify_lane(body)
            except ValueError:
                if len(self.lane_diagnostics) < 8:
                    self.lane_diagnostics.append(lane_shape(body))
                raise
            self.counts[lane] += 1
            identity = 'public-' + lane + '-' + str(self.counts[lane])
            controller = Controller(self.engagement)
            state = controller.state()
            outputs = [row.get('output') for row in body.get('input', []) if isinstance(row, dict) and row.get('call_id')]
            outputs += [row.get('content') for row in body.get('messages', []) if isinstance(row, dict) and row.get('role') == 'tool']
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
            return frames(self.runtime, identity, name, arguments)

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


def frames(runtime, identity, name, arguments):
    if runtime == 'codex':
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
    delta = ({'role': 'assistant', 'tool_calls': [{'index': 0, 'id': 'call-' + identity, 'type': 'function',
              'function': {'name': name, 'arguments': json.dumps(arguments)}}]} if name else
             {'role': 'assistant', 'content': 'Fixture turn complete.'})
    chunks = [{'delta': delta, 'finish_reason': None}, {'delta': {}, 'finish_reason': 'tool_calls' if name else 'stop'}]
    return [('data: ' + json.dumps({'id': identity, 'object': 'chat.completion.chunk', 'created': 0,
            'model': 'fixture-model', 'choices': [{'index': 0, **chunk}]}) + '\n\n').encode()
            for chunk in chunks] + [b'data: [DONE]\n\n']


def run_public(root, fixture, result):
    from check_linux_model_native_e2e import tool_bundle
    routing_self_check()
    packet_self_check()
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
        result['public_cli'] = {'returncode': child.returncode, 'status': cli_status, 'code': cli_code}
        state = Controller(engagement).state()
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
                  'provider_errors': provider.errors[:8], 'provider_error_frames': provider.error_frames,
                  'provider_fixture_error_codes': provider.public_error_codes,
                  'provider_json_parse_diagnostics': provider.json_parse_diagnostics,
                  'provider_lane_diagnostics': script.lane_diagnostics}
        result['public_runner'] = public
        if state['cleanup'] != 'verified':
            result['boundary_cleanup_error'] = 'public_cleanup_unresolved'
        check(result, 'public CLI closes reviewed owned fixture', child.returncode == 0 and state['status'] == 'closed'
              and state['cleanup'] == 'verified' and public['review_status'] == 'accepted'
              and public['lead_session_present'] and public['reviewer_session_present'] and public['sessions_distinct']
              and public['source_output_observed'] and public['review_packet_observed'])
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
