#!/usr/bin/env python3
"""Offline provider-attempt and native-usage accounting through public boundaries.

Uses one signed temporary engagement, the real NetworkGate, a loopback provider,
and Controller journal APIs. It never contacts a real provider or target.
"""
from __future__ import annotations
import argparse
from contextlib import nullcontext
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'tools'), str(Path(__file__).resolve().parent)]
from check_engagement_contract_e2e import make_fixture, fixture_scope, resign_fixture
from engagement_contract import canonical, digest, load_inputs
from engagement_controller import Controller, ControllerError
from engagement_network import NetworkGate, NetworkDenied
from engagement_runner import Runner


def require(value, message):
    if not value:
        raise AssertionError(message)


def run(root):
    hits, holding, release = [], threading.Event(), threading.Event()

    class Provider(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get('Content-Length', '0'))
            self.rfile.read(length)
            hits.append(self.path)
            if self.path == '/hold':
                holding.set()
                release.wait(5)
            self.send_response(503 if self.path == '/retry' else 200)
            self.send_header('Content-Length', '2')
            self.end_headers()
            try:
                self.wfile.write(b'ok')
            except OSError:
                pass

        def log_message(self, *_):
            pass

    provider = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
    thread = threading.Thread(target=provider.serve_forever, daemon=True)
    thread.start()
    gate = None
    pending = []
    result = {'external_provider_calls': 0}
    try:
        inputs = make_fixture(root / 'input')
        scope = fixture_scope(inputs)
        host = 'provider.fixture.invalid'
        port = provider.server_port
        scope['network']['provider'] = [{'protocol': 'http', 'host': host, 'port': port,
            'address_policy': {'public_only': False, 'cidrs': ['127.0.0.1/32']}}]
        resign_fixture(inputs, scope)
        controller = Controller.initialize(root / 'engagement', load_inputs(inputs),
                                           evidence_class='engineering_simulation')
        workspace = root / 'workspace'
        workspace.mkdir(mode=0o700)
        grant = controller.prepare_worker_dispatch('lead-1', 1, workspace, seconds=30,
            resources=['source-main'], adapter_id='native-runner')
        controller.record_worker_started('lead-1', 1, 'accounting-session', workspace)
        first = controller.begin_invocation(grant)
        route = scope['network']['provider'][0]
        origin = f"http://{host}:{port}"
        gate = NetworkGate([route], lambda: controller.authorize_dispatch(grant),
            dispatch_guard=nullcontext,
            target_connectors={origin: lambda _: socket.create_connection(('127.0.0.1', port), timeout=5)},
            request_observer=lambda observation: (pending.append(dict(observation)),
                controller.record_provider_request(grant, observation)))

        # One successful response and one provider error followed by a retry.
        for path in ('/round', '/retry', '/round'):
            reply = gate.fetch(origin + path, method='POST', body=b'{}')
            require(reply['status'] in (200, 503), 'fixture response missing')
        attempts = [row for row in pending if row['status'] == 'started']
        finished = [row for row in pending if row['status'] == 'completed']
        require(len(attempts) == len(finished) == 3, 'provider attempts/retry not counted individually')
        require(len({row['request_id'] for row in attempts}) == 3, 'attempt IDs are not unique')
        require(hits == ['/round', '/retry', '/round'], 'loopback provider saw unexpected requests')

        # A denied route never reaches the request observer/provider.
        before = len(pending)
        try:
            gate.fetch('http://denied.fixture.invalid:1/nope')
            raise AssertionError('ungranted provider route admitted')
        except NetworkDenied:
            pass
        require(len(pending) == before and len(hits) == 3, 'denied route counted as provider attempt')

        native_usage = {'input_tokens': 20, 'output_tokens': 5, 'total_tokens': 25,
                        'estimated_cost': 0.012, 'monetary_spend': None, 'provider_requests': None}
        usage = Runner._usage(SimpleNamespace(usage=native_usage))
        require(usage == {'tokens': {'input': 20, 'output': 5, 'total': 25}, 'cost': 0.012},
                'native usage adapter changed tokens or estimated cost')
        controller.record_invocation_observed(grant, first, {'status': 'completed', 'usage': usage})
        controller.record_invocation_observed(grant, first, {'status': 'completed', 'usage': usage})
        state = controller.state()
        require(state['usage']['tokens']['total'] == 25, 'replayed invocation charged twice')
        require(state['usage']['native_token_totals_complete'], 'complete native token totals not recognized')
        require(state['usage']['known_estimated_cost'] == 0.012 and state['usage']['cost'] == 0.012,
                'native estimated cost was lost or mislabeled')
        require(state['usage']['billed_cost'] is None and
                state['usage']['billed_cost_unavailable_reason'] == 'provider_billing_receipt_unavailable',
                'estimated cost was presented as billed cost')

        # Identical public request replay is harmless; conflicting settlement is refused.
        first_id = attempts[0]['request_id']
        controller.record_provider_request(grant, {'request_id': first_id, 'status': 'started'})
        controller.record_provider_request(grant, {'request_id': first_id, 'status': 'completed'})
        try:
            controller.record_provider_request(grant, {'request_id': first_id, 'status': 'unknown'})
            raise AssertionError('conflicting provider settlement accepted')
        except ControllerError as error:
            require(error.code == 'provider_observation_conflict', error.code)
        state = controller.state()
        require(state['usage']['provider_requests'] == 3 and
                state['usage']['provider_requests_completed'] == 3 and
                state['usage']['provider_requests_unknown'] == 0,
                'provider replay changed attempt totals')
        require(state['usage']['provider_requests_complete'] and
                'provider_requests' not in state['usage']['missing'], 'proxy coverage not declared')

        # A valid grant from another journal cannot reuse this request ID.
        foreign_inputs = make_fixture(root / 'foreign-input')
        foreign = Controller.initialize(root / 'foreign-engagement', load_inputs(foreign_inputs),
                                         evidence_class='engineering_simulation')
        foreign_workspace = root / 'foreign-workspace'
        foreign_workspace.mkdir(mode=0o700)
        foreign_grant = foreign.prepare_worker_dispatch('lead-1', 1, foreign_workspace, seconds=30,
            resources=['source-main'], adapter_id='native-runner')
        before_foreign = controller.state()['usage'].copy()
        try:
            controller.record_provider_request(foreign_grant, {'request_id': first_id, 'status': 'started'})
            raise AssertionError('foreign dispatch reused provider request ID')
        except ControllerError:
            pass
        require(controller.state()['usage'] == before_foreign, 'foreign request attempt mutated totals')

        # A second admitted request interrupted after upstream acceptance remains unknown.
        second = controller.begin_invocation(grant)
        errors = []
        def interrupted_call():
            try:
                gate.fetch(origin + '/hold', method='POST', body=b'{}')
            except Exception as error:
                errors.append(type(error).__name__)
        request = threading.Thread(target=interrupted_call, daemon=True)
        request.start()
        require(holding.wait(3), 'provider did not accept interrupted fixture request')
        controller.revoke_worker('lead-1', 1, reason='fixture_interrupted')
        gate.close()
        request.join(3)
        release.set()
        require(not request.is_alive(), 'interrupted proxy request did not return')
        interrupted = [row for row in pending if row['status'] == 'unknown']
        require(len(interrupted) == 1, 'interrupted provider attempt not retained as unknown')
        controller.record_invocation_observed(grant, second, {'status': 'interrupted',
            'usage': {'tokens': None, 'cost': None}})
        state = controller.state()
        require(state['usage']['provider_requests'] == 4 and
                state['usage']['provider_requests_completed'] == 3 and
                state['usage']['provider_requests_unknown'] == 1,
                'interruption was omitted or treated as completed')
        require(state['provider_requests'][interrupted[0]['request_id']]['invocation_id'] == second,
                'interrupted provider attempt was attached to the wrong invocation')
        require(state['usage']['native_usage_incomplete'] and
                not state['usage']['native_token_totals_complete'] and
                not state['usage']['estimated_cost_complete'] and state['usage']['cost'] is None,
                'missing second invocation usage treated as zero/complete')
        require(state['usage']['known_estimated_cost'] == 0.012 and
                state['usage']['billed_cost'] is None,
                'known estimate or missing billed cost changed after interruption')
        legacy_inputs = make_fixture(root / 'legacy-input')
        legacy = Controller.initialize(root / 'legacy-engagement', load_inputs(legacy_inputs),
                                       evidence_class='engineering_simulation')
        event_file = legacy.root / 'events/000000000001.json'
        event = json.loads(event_file.read_bytes())
        event.pop('sha256')
        event['payload'].pop('provider_accounting')
        event['sha256'] = digest(canonical(event))
        event_file.write_bytes(canonical(event))
        event_file.chmod(0o600)
        legacy_usage = Controller(legacy.root).state()['usage']
        require(not legacy_usage['provider_requests_complete'] and
                'provider_requests' in legacy_usage['missing'],
                'legacy journal without proxy marker declared provider coverage complete')
        result.update(status='passed', evidence='public_network_gate_and_controller_journal',
            attempts=state['provider_requests'], usage=state['usage'], interrupted_errors=errors,
            loopback_provider_requests=len(hits), coverage=['started', 'completed', 'unknown', 'denied route',
                'native usage replay', 'provider settlement replay', 'missing usage', 'billed cost unknown'])
        return result
    finally:
        release.set()
        if gate is not None:
            gate.close()
        provider.shutdown()
        provider.server_close()
        thread.join(timeout=2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='provider-accounting-e2e-') as temporary:
        root = Path(temporary).resolve()
        try:
            result = run(root)
        except Exception as error:
            result = {'status': 'failed', 'error': type(error).__name__ + ': ' + str(error),
                      'external_provider_calls': 0}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'output': str(args.output)}))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
