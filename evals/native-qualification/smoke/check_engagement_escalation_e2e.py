#!/usr/bin/env python3
"""Signed declared-effect transitions and real local HTTP effect selection.

Run --output FILE with Python 3 and ssh-keygen. Protected source observations are
explicit simulations; local HTTP receivers/proxy requests are real. No provider,
external target, Docker or SSH is contacted. Shared-application reset and semantic
containment are not established, and current artifact/human gates stay active.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import http.server
import json
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'tools'), str(Path(__file__).parent)]
from check_engagement_evidence_e2e import Case, fixture, require, refused
from check_engagement_network_journal_e2e import case as application, observation, record
from engagement_contract import canonical, digest
from engagement_controller import Controller
from engagement_network import NetworkGate, NetworkDenied
from target_accounts import TargetAccountResolver


def make(path, modify=None):
    original = fixture.resign_fixture
    def sign(inputs, scope):
        scope['escalation_ceiling'] = 'cross_user'
        scope['effects'][0]['rung'] = 'self'
        initial = scope['effects'][0]
        scope['effects'] = [initial, *[dict(initial, id=rung + '-source', rung=rung) for rung in ('stored', 'cross_user')]]
        if modify:
            modify(inputs, scope)
        return original(inputs, scope)
    with patch.object(fixture, 'resign_fixture', sign):
        return Case(path)


def confirmed(x):
    x.publication('contrary'); x.instrument()
    x.experiment('effect')
    x.experiment('control', purpose='control', explains={'experiment_id': 'effect', 'variable': 'fixture-switch'})
    x.claim()
    actor, packet = x.packet('claim', 'claim-1')
    x.experiment('replay', actor, purpose='replay', explains={'experiment_id': 'effect', 'variable': None}, nonce='2' * 32)
    x.review('claim-1', actor, packet, evidence=['replay'], contrary=['contrary'])


def transition(x, next_effect='stored-source', *, accept=True, name='transition', claim_id='claim-1'):
    actor = x.worker(name + '-reviewer', 'reviewer', start=False)
    x.request('review_request', {'review_id': name, 'kind': 'escalation', 'subject_id': claim_id,
        'reviewer_id': actor.id, 'next_effect_id': next_effect})
    review = x.c.state()['reviews'][name]
    x.start(actor.id)
    if accept:
        state = x.c.state(); claim = state['claims'][claim_id]
        prior_review = state['reviews'][claim['review_id']]
        evidence = sorted({claim['effect'], claim['control'], *prior_review['result']['evidence_refs']})
        x.request('review_result', {'review_id': name, 'packet_sha256': review['packet_sha256'],
            'disposition': 'accept', 'checks': {key: True for key in
                ('measurement', 'permissions', 'causal_control', 'clean_replay', 'completeness')},
            'evidence_refs': evidence, 'contrary_refs': claim['contrary'],
            'reason': 'The exact already-signed next effect follows the independently confirmed prior effect.'}, actor)
    return actor, review


def environment_request(x, effect='stored-source', *, name='next-operation', grant=None, phase='intent', identity=None):
    grant = grant or x.grant(resources=['source-main'])
    if identity is None:
        identity = x.observe(grant, 'setup-' + name, '3' * 32)
    event = {'kind': 'environment-observation-v2', 'operation': 'execute', 'operation_id': name,
        'identity': identity, 'phase': phase}
    if phase == 'intent':
        event['request_sha256'] = digest(b'harmless explicit transition')
    else:
        event.update(status='settled', returncode=0, output_sha256=digest(b'harmless transition result'))
    x.c.record_environment_observation(grant, 'lab-main', event, effect_id=effect)
    return grant, identity, event


def missing_predecessor(path):
    x = make(path)
    grant = x.grant(resources=['source-main']); identity = x.observe(grant, 'initial-self', '3' * 32)
    for rung in ('stored', 'cross_user'):
        refused('effect_escalation_review_required', lambda: environment_request(x, rung + '-source',
            name=rung, grant=grant, identity=identity))
    require(len(x.c.state()['environment_operations']) == 1, 'forbidden intent persisted')


def supported_is_insufficient(path):
    x = make(path); x.publication('contrary'); x.instrument(); x.experiment('effect')
    x.experiment('control', purpose='control', explains={'experiment_id': 'effect', 'variable': 'fixture-switch'}); x.claim()
    refused('escalation_prior_claim_unconfirmed', lambda: transition(x))


def accepted_transition(path):
    x = make(path); confirmed(x)
    _, review = transition(x)
    packet = json.loads(x.c.read_object(review['packet_sha256']))
    require(packet['material']['next_effect']['id'] == 'stored-source', 'packet omitted next signed effect')
    require(packet['material']['prior_effect']['id'] == 'read-source', 'packet did not derive protected predecessor')
    grant, identity, _ = environment_request(x)
    refused('effect_escalation_review_required', lambda: environment_request(x, 'cross_user-source',
        name='skip-later', grant=grant, identity=identity))
    require(Controller(x.c.root).state()['claims']['claim-1']['state'] == 'independently_confirmed',
        'transition acceptance rewrote claim state')


def rung_skip(path):
    x = make(path); confirmed(x)
    refused('escalation_rung_invalid', lambda: transition(x, 'cross_user-source'))


def full_chain(path):
    x = make(path); confirmed(x); transition(x)
    original = x.c.record_environment_observation
    def stored(*args, **kwargs):
        kwargs['effect_id'] = 'stored-source'
        return original(*args, **kwargs)
    with patch.object(x.c, 'record_environment_observation', stored):
        x.experiment('stored-effect', nonce='4' * 32)
        x.experiment('stored-control', purpose='control', explains={'experiment_id': 'stored-effect', 'variable': 'switch'}, nonce='4' * 32)
        x.request('claim_propose', {'claim_id': 'claim-stored', 'text': 'Harmless stored fixture.',
            'effect': 'stored-effect', 'control': 'stored-control', 'replay': None,
            'contrary': ['contrary'], 'resources': ['source-main'], 'supersedes': []})
        actor, packet = x.packet('claim', 'claim-stored', reviewer='stored-reviewer')
        x.experiment('stored-replay', actor, purpose='replay', explains={'experiment_id': 'stored-effect', 'variable': None}, nonce='5' * 32)
        x.review('claim-stored', actor, packet, evidence=['stored-replay'], contrary=['contrary'])
    transition(x, 'cross_user-source', name='cross-transition', claim_id='claim-stored')
    environment_request(x, 'cross_user-source', name='cross-effect')


def account_context(path):
    def change(inputs, scope):
        scope['access'][0]['account_refs'] = ['other-principal']
        scope['effects'][1]['account_refs'] = ['other-principal']
    x = make(path, change); confirmed(x)
    refused('escalation_context_invalid', lambda: transition(x))


def resource_context(path):
    def change(inputs, scope):
        import shutil
        values = json.loads(inputs.read_bytes())
        other = inputs.parent / 'other-source'
        shutil.copytree(values['access_files']['source-main'], other, dirs_exist_ok=True)
        values['access_files']['source-other'] = str(other)
        inputs.write_bytes(canonical(values))
        if len(scope['access']) == 1:
            scope['access'].append(dict(scope['access'][0], id='source-other'))
        scope['effects'][1]['access_ids'] = ['source-other']
    x = make(path, change); confirmed(x)
    refused('escalation_context_invalid', lambda: transition(x))


def malformed_effect(path):
    x = make(path); confirmed(x)
    refused('identifier_invalid', lambda: transition(x, [], name='malformed'))
    refused('escalation_effect_invalid', lambda: transition(x, 'not-signed', name='unsigned'))


def unrelated_claim(path):
    x = make(path); confirmed(x)
    x.request('claim_propose', {'claim_id': 'claim-unrelated', 'text': 'An unsupported separate effect.',
        'effect': None, 'control': None, 'replay': None, 'contrary': [], 'resources': ['source-main'], 'supersedes': []})
    actor = x.worker('unrelated-reviewer', 'reviewer', start=False)
    refused('escalation_prior_claim_unconfirmed', lambda: x.request('review_request', {
        'review_id': 'unrelated-transition', 'kind': 'escalation', 'subject_id': 'claim-unrelated',
        'reviewer_id': actor.id, 'next_effect_id': 'stored-source'}))


def stale_material(path):
    x = make(path); confirmed(x); transition(x)
    grant, identity, intent = environment_request(x)
    x.instrument('instrument-2', supersedes=['instrument-1'])
    refused('effect_escalation_review_required', lambda: environment_request(x,
        name='after-supersession', grant=grant, identity=identity))
    read = dict(intent, phase='result', operation='read_artifact', operation_id='late-new-read', status='settled')
    read.pop('request_sha256')
    refused('effect_escalation_review_required', lambda: x.c.record_environment_observation(
        grant, 'lab-main', read, effect_id='stored-source'))
    x.c.revoke_worker('lead-1', 1, reason='fixture-revoked')
    environment_request(x, name=intent['operation_id'], grant=grant, identity=identity, phase='result')
    cleanup = dict(intent, operation='remove', operation_id='owned-cleanup')
    x.c.record_environment_observation(grant, 'lab-main', cleanup, effect_id='stored-source')
    require(x.c.state()['environment_operations']['next-operation']['result']['status'] == 'settled',
        'matching late result lost after stale review/revocation')


def stale_pending_review(path):
    x = make(path); confirmed(x); actor, review = transition(x, accept=False)
    x.instrument('instrument-2', supersedes=['instrument-1'])
    refused('review_stale', lambda: x.request('review_result', {'review_id': 'transition',
        'packet_sha256': review['packet_sha256'], 'disposition': 'accept',
        'checks': {key: True for key in ('measurement', 'permissions', 'causal_control', 'clean_replay', 'completeness')},
        'evidence_refs': ['effect', 'control', 'replay'], 'contrary_refs': ['contrary'], 'reason': 'Stale fixture.'}, actor))


def review_evidence_required(path):
    x = make(path); confirmed(x); actor, review = transition(x, accept=False)
    refused('review_evidence_incomplete', lambda: x.request('review_result', {'review_id': 'transition',
        'packet_sha256': review['packet_sha256'], 'disposition': 'accept',
        'checks': {key: True for key in ('measurement', 'permissions', 'causal_control', 'clean_replay', 'completeness')},
        'evidence_refs': [], 'contrary_refs': ['contrary'], 'reason': 'Flags are not execution evidence.'}, actor))


def reopened_claim(path):
    x = make(path); confirmed(x); transition(x)
    actor = x.worker('reopen-reviewer', 'reviewer', start=False)
    x.request('review_request', {'review_id': 'reopen-claim', 'kind': 'claim', 'subject_id': 'claim-1', 'reviewer_id': actor.id})
    review = x.c.state()['reviews']['reopen-claim']; x.start(actor.id)
    x.request('review_result', {'review_id': 'reopen-claim', 'packet_sha256': review['packet_sha256'],
        'disposition': 'reopen', 'checks': {key: False for key in
            ('measurement', 'permissions', 'causal_control', 'clean_replay', 'completeness')},
        'evidence_refs': [], 'contrary_refs': [], 'reason': 'The premise needs another check.'}, actor)
    refused('effect_escalation_review_required', lambda: environment_request(x))


def decide_transition(x, actor, review, name, disposition):
    return x.request('review_result', {'review_id': name, 'packet_sha256': review['packet_sha256'],
        'disposition': disposition, 'checks': {key: disposition == 'accept' for key in
            ('measurement', 'permissions', 'causal_control', 'clean_replay', 'completeness')},
        'evidence_refs': ['effect', 'control', 'replay'], 'contrary_refs': ['contrary'],
        'reason': 'A fresh verdict on this exact transition.'}, actor)


def replaced_transition(path):
    for disposition in ('reject', 'reopen', 'unresolved'):
        x = make(path / disposition); confirmed(x); _, original = transition(x)
        frozen = x.c.read_object(original['packet_sha256'])
        grant, identity, intent = environment_request(x)
        actor, latest = transition(x, accept=False, name='fresh-transition')
        refused('effect_escalation_review_required', lambda: environment_request(x,
            name='during-fresh-review', grant=grant, identity=identity))
        decide_transition(x, actor, latest, 'fresh-transition', disposition)
        refused('effect_escalation_review_required', lambda: environment_request(x,
            name='after-fresh-review', grant=grant, identity=identity))
        environment_request(x, name=intent['operation_id'], grant=grant, identity=identity, phase='result')
        cleanup = dict(intent, operation='remove', operation_id='owned-cleanup')
        x.c.record_environment_observation(grant, 'lab-main', cleanup, effect_id='stored-source')
        state = x.c.state()
        require(state['reviews']['transition']['status'] == 'stale' and
                state['reviews']['transition']['result']['disposition'] == 'accept', 'prior verdict lost or still active')
        require(x.c.read_object(original['packet_sha256']) == frozen, 'historical packet rewritten')


def superseded_pending_review(path):
    x = make(path); confirmed(x)
    old_actor, older = transition(x, accept=False, name='older-review')
    new_actor, newer = transition(x, accept=False, name='newer-review')
    decide_transition(x, new_actor, newer, 'newer-review', 'reject')
    refused('review_stale', lambda: decide_transition(x, old_actor, older, 'older-review', 'accept'))
    refused('effect_escalation_review_required', lambda: environment_request(x))


def unrelated_transition_review(path):
    def change(inputs, scope):
        scope['effects'].append(dict(scope['effects'][1], id='stored-alternative'))
    x = make(path, change); confirmed(x); transition(x)
    actor, other = transition(x, 'stored-alternative', accept=False, name='other-transition')
    grant, identity, _ = environment_request(x)
    decide_transition(x, actor, other, 'other-transition', 'reject')
    environment_request(x, name='after-unrelated-review', grant=grant, identity=identity)
    refused('effect_escalation_review_required', lambda: environment_request(x, 'stored-alternative',
        name='unapproved-alternative', grant=grant, identity=identity))


def application_gate(path):
    from check_engagement_network_journal_e2e import fixture as app_fixture
    original = app_fixture.resign_fixture
    def sign(inputs, scope):
        if not any(row['kind'] == 'application' for row in scope['access']):
            return original(inputs, scope)
        scope['escalation_ceiling'] = 'cross_user'
        for effect in scope['effects']:
            effect['rung'] = 'self'
        scope['effects'].append(dict(scope['effects'][0], id='stored-app', rung='stored'))
        return original(inputs, scope)
    with patch.object(app_fixture, 'resign_fixture', sign):
        x = application(path)
    record(x, observation('self-request'))
    refused('effect_escalation_review_required', lambda: record(x, observation('stored-request', effect_id='stored-app')))
    require('stored-request' not in x.c.state()['network_operations'], 'higher-rung intent admitted without predecessor')


def artifact_gate(path):
    def change(inputs, scope):
        scope['access'][0]['permissions'] = ['read', 'execute', 'write']
        scope['effects'].append(dict(scope['effects'][0], id='artifact', kind='artifact_create',
            artifact_classes=['harmless-file'], cleanup_required=True))
    x = make(path, change)
    refused('artifact_effect_unsupported', lambda: environment_request(x, 'artifact'))


def effect_selection(path):
    hits, observed = [], []
    class Receiver(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append((self.server.server_port, self.headers.get('X-OSLit-Effect')))
            if self.path == '/redirect':
                self.send_response(302); self.send_header('Location', second_url + '/done')
                self.send_header('Content-Length', '0'); self.end_headers(); return
            self.send_response(200); self.send_header('Content-Length', '2'); self.end_headers(); self.wfile.write(b'ok')
        def log_message(self, *_): pass
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Receiver)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    second = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Receiver)
    other_thread = threading.Thread(target=second.serve_forever, daemon=True); other_thread.start()
    second_url = 'http://127.0.0.1:' + str(second.server_port)
    url = 'http://127.0.0.1:' + str(server.server_port)
    route = {'protocol': 'http', 'host': '127.0.0.1', 'port': server.server_port,
        'address_policy': {'public_only': False, 'cidrs': ['127.0.0.1/32']}}
    access = {'id': 'app', 'kind': 'application', 'identity': {'base_url': url, 'version': 'fixture'},
        'account_refs': [], 'permissions': ['read']}
    effect = {'id': 'read-self', 'kind': 'read', 'access_ids': ['app'], 'environment_ids': ['lab'],
        'account_refs': [], 'rung': 'self', 'artifact_classes': [], 'cleanup_required': False}
    other_route = dict(route, port=second.server_port)
    other_access = dict(access, id='other', identity={'base_url': second_url, 'version': 'fixture'})
    other_effect = dict(effect, id='read-other', access_ids=['other'])
    scope = {'access': [access, other_access], 'effects': [effect, dict(effect, id='read-stored', rung='stored'), other_effect],
        'network': {'target': [route, other_route], 'provider': [], 'acquisition': []}}
    resolver = TargetAccountResolver(None, scope, lambda: {'resources': ['app', 'other']}, observed.append,
        environment_profile_id='lab')
    gate = NetworkGate([route, other_route], lambda: True, dispatch_guard=lambda: nullcontext(), request_binder=resolver.bind)
    try:
        def rejected(headers):
            before = len(hits)
            try: gate.fetch(url, headers=headers)
            except NetworkDenied: pass
            else: raise AssertionError('ambiguous or invalid effect reached receiver')
            require(len(hits) == before, 'rejected request reached receiver')
        rejected({})
        rejected({'X-OSLit-Effect': 'outside'})
        result = gate.fetch(url, headers={'X-OSLit-Effect': 'read-stored'})
        require(result['status'] == 200 and hits == [(server.server_port, None)], 'effect selector leaked or request failed')
        require(observed[0]['effect_id'] == 'read-stored', 'explicit effect replaced with first match')
        result = gate.fetch(url + '/redirect', headers={'X-OSLit-Effect': 'read-self'})
        require(result['status'] == 200 and hits[-1] == (second.server_port, None), 'cross-origin effect selector carried over')
        require(observed[-1]['effect_id'] == 'read-other', 'redirect inherited previous effect authority')
    finally:
        gate.close(); resolver.close(); server.shutdown(); server.server_close(); thread.join(2)
        second.shutdown(); second.server_close(); other_thread.join(2)


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); rows = []
    for check in (missing_predecessor, supported_is_insufficient, accepted_transition, rung_skip, full_chain, account_context, resource_context, malformed_effect, unrelated_claim,
                  stale_material, stale_pending_review, review_evidence_required, reopened_claim, replaced_transition, superseded_pending_review, unrelated_transition_review, application_gate, artifact_gate, effect_selection):
        try:
            with tempfile.TemporaryDirectory(prefix='oslit-escalation-') as temporary:
                check(Path(temporary).resolve())
            rows.append({'scenario': check.__name__, 'status': 'pass'})
        except Exception as error:
            rows.append({'scenario': check.__name__, 'status': 'fail', 'error': str(error)})
    report = {'classification': 'signed_simulated_execution_and_actual_local_http', 'provider_calls': 0,
        'external_target_calls': 0, 'status': 'pass' if all(row['status'] == 'pass' for row in rows) else 'fail',
        'scenarios': rows, 'unverified': ['shared application reset', 'native semantic effect containment', 'artifact classes']}
    args.output.write_text(json.dumps(report, indent=2) + '\n'); print(json.dumps(report)); return report['status'] != 'pass'

if __name__ == '__main__': raise SystemExit(main())
