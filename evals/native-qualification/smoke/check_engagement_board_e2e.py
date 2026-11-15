#!/usr/bin/env python3
"""Failure-first board, peer-message, native tool, and steering workflow check.

Run with --output FILE. Uses the real signed-fixture journal/controller and native
host tool, with a simulated steering endpoint. No provider, Docker daemon, or target.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'tools'), str(Path(__file__).parent)]

from check_engagement_evidence_e2e import Case, require
from engagement_controller import Controller, ControllerError, Principal, WorkerServer
from engagement_runner import Runner, WorkerContext


def submit(case, kind, payload, actor=None):
    case.serial += 1
    return case.c.submit(actor or case.lead, {'request_id': f'board-{case.serial}',
        'expected_revision': case.c.state()['revision'], 'type': kind, 'payload': payload})


def refused(code, call):
    try:
        call()
    except ControllerError as error:
        require(error.code == code, f'{error.code} != {code}')
    else:
        raise AssertionError(f'accepted forbidden operation: {code}')


def tool_json(response):
    require(not response.get('isError'), 'native host tool returned an error')
    return json.loads(response['content'][0]['text'])


def run(output):
    from check_engagement_native_boundary_e2e import simulated_boundary

    rows = []
    with tempfile.TemporaryDirectory(prefix='engagement-board-') as temporary:
        root = Path(temporary).resolve()
        work = root / 'native'; work.mkdir(mode=0o700)
        boundary, case, context, patches = simulated_boundary(work)
        with patches:
            native = boundary.NativeBoundary(context)
            identity = native.start()
            case.c.record_worker_started('lead-1', 1, identity['session_id'], context.workspace,
                owner_receipt=identity['owner_receipt'])
            specialist = case.worker('specialist-1', start=True)
            submit(case, 'task_create', {'task_id': 'task-board', 'question': 'board query needle',
                'priority': 1, 'resources': ['source-main'], 'prerequisites': [], 'evidence_refs': []})
            case.publication('board-observation')
            submit(case, 'publish', {'publication_id': 'board-correction', 'kind': 'observation',
                'subject': 'needle correction', 'body': 'Corrects the prior fixture observation.',
                'refs': ['board-observation'], 'supersedes': ['board-observation'], 'artifacts': []})
            case.instrument()
            submit(case, 'claim_propose', {'claim_id': 'claim-board', 'text': 'needle claim remains unconfirmed',
                'effect': None, 'control': None, 'replay': None, 'contrary': [], 'resources': [], 'supersedes': []})

            # Controller projection and the actual native host tool share the same bounded view.
            revision_before_board = case.c.state()['revision']
            first = case.c.board(case.lead, query='needle', kinds=['task', 'publication'], limit=1)
            require(first['view'] == 'board' and first['has_more'], 'board did not paginate matching rows')
            require(first['items'][0]['source_event']['sha256'].startswith('sha256:'), 'board omitted event provenance')
            require(first['items'][0]['author'], 'board omitted authenticated author')
            snapshot = first['snapshot_revision']
            publications = case.c.board(case.lead, kinds=['publication'])['items']
            correction = next(row for row in publications if row['id'] == 'board-correction')
            observation = next(row for row in publications if row['id'] == 'board-observation')
            instrument = case.c.board(case.lead, query='instrument-1', kinds=['instrument'])['items'][0]
            claim = case.c.board(case.lead, query='claim-board', kinds=['claim'])['items'][0]
            require(correction['record']['supersedes'] == ['board-observation'] and
                'board-correction' in observation['superseded_by'], 'correction provenance was lost')
            require(instrument['source_event']['sha256'].startswith('sha256:') and
                instrument['author'] == 'lead-1', 'instrument author/provenance was lost')
            require(claim['verification_state'] == 'unconfirmed' and
                claim['source_event']['sha256'].startswith('sha256:'),
                'unconfirmed claim was flattened or lost provenance')
            require(case.c.state()['revision'] == revision_before_board,
                'read-only board query changed journal state')
            submit(case, 'publish', {'publication_id': 'board-late', 'kind': 'observation',
                'subject': 'needle later', 'body': 'Added after page one.', 'refs': [],
                'supersedes': [], 'artifacts': []})
            next_page = case.c.board(case.lead, query='needle', kinds=['task', 'publication'],
                since=first['next_cursor'], limit=1)
            require(next_page['snapshot_revision'] == snapshot and
                all(row['id'] != 'board-late' for row in next_page['items']),
                'board cursor drifted to a newer snapshot')
            refused('board_cursor_invalid', lambda: case.c.board(case.lead, query='different',
                kinds=['task', 'publication'], since=first['next_cursor'], limit=1))
            refused('board_query_invalid', lambda: case.c.board(case.lead, query='q' * 1025))

            native_page = native.host_call('engagement_status', {'view': 'board', 'query': 'needle',
                'kinds': ['task', 'publication'], 'since': None, 'limit': 1}).wait()
            require(tool_json(native_page)['view'] == 'board',
                'native engagement_status board view failed')

            cli = subprocess.run([sys.executable, str(ROOT / 'tools/native_engagement.py'), 'status',
                '--engagement-root', str(case.c.root), '--view', 'board', '--query', 'needle',
                '--kind', 'task', '--kind', 'publication', '--limit', '1'],
                capture_output=True, text=True, timeout=15)
            require(cli.returncode == 0 and json.loads(cli.stdout)['view'] == 'board',
                'native_engagement status CLI board view failed')
            sockets = root / 's'; sockets.mkdir(mode=0o700)
            server = WorkerServer(case.c.root, Principal('worker', 'lead-1', 1), sockets / 'worker.sock')
            server.start()
            try:
                worker_cli = subprocess.run([sys.executable, str(ROOT / 'tools/native_engagement.py'), 'status',
                    '--socket', str(sockets / 'worker.sock'), '--view', 'board', '--query', 'needle',
                    '--kind', 'task', '--kind', 'publication', '--limit', '1'],
                    capture_output=True, text=True, timeout=15)
                require(worker_cli.returncode == 0 and json.loads(worker_cli.stdout)['view'] == 'board',
                    'authenticated worker socket board view failed')
            finally:
                server.close()
            rows.append({'name': 'search_snapshot_native_tool', 'status': 'pass',
                'snapshot_revision': snapshot, 'first_page_items': len(first['items'])})

            # Typed peer messages are journal records authored from the authenticated principal.
            result = submit(case, 'team_message', {'message_id': 'msg-1',
                'recipient_ids': ['specialist-1'], 'subject': 'Needle lead',
                'body': 'Please inspect the corrected observation.', 'refs': ['board-correction']})
            message = case.c.state()['messages']['msg-1']
            message_row = next(row for row in case.c.board(case.lead, query='msg-1')['items']
                if row['id'] == 'msg-1')
            require(message['author'] == 'lead-1' and
                message_row['source_event']['sequence'] == result['revision'] and
                message_row['source_event']['sha256'].startswith('sha256:'),
                'message author/event reference not bound to accepted journal event')
            before = case.c.state()
            refused('message_recipient_invalid', lambda: submit(case, 'team_message', {
                'message_id': 'msg-invalid', 'recipient_ids': ['ghost'], 'subject': 'x',
                'body': 'x', 'refs': []}))
            refused('message_invalid', lambda: submit(case, 'team_message', {
                'message_id': 'msg-malformed', 'recipient_ids': ['specialist-1'], 'subject': 'x',
                'body': '', 'refs': []}))
            require(case.c.state()['workers'] == before['workers'] and case.c.state()['scope'] == before['scope'],
                'peer message changed authority')

            # Native host tool can submit through the same authenticated boundary.
            host_result = native.host_call('engagement_submit', {'request': {
                'request_id': 'native-message', 'expected_revision': case.c.state()['revision'],
                'type': 'team_message', 'payload': {'message_id': 'msg-2',
                    'recipient_ids': ['specialist-1'], 'subject': 'Native message',
                    'body': 'Published through host tool.', 'refs': []}}}).wait()
            require(not host_result.get('isError'), 'native typed message submit rejected')
            submit(case, 'team_message', {'message_id': 'msg-peer', 'recipient_ids': ['lead-1'],
                'subject': 'Peer update', 'body': 'Specialist confirms the correction is relevant.',
                'refs': ['board-correction']}, actor=specialist)

            # Runner sends each relevant journal notice once; refs remain stable and data is not authority.
            runner = Runner(case.c, boundary_factory=lambda _: None)
            worker = case.c.state()['workers']['lead-1']
            worker_context = WorkerContext(runner, worker, context.grant, context.workspace)

            class Steering:
                def __init__(self): self.sent = []; self.runtime = self; self.active = True
                def steer(self, text): self.sent.append(text); return {'delivered': True}

            steering = Steering()
            delivered = runner._updates(worker_context, steering, 0)
            require(delivered > 0 and steering.sent, 'no journal update was steered')
            notice = '\n'.join(steering.sent)
            require('Peer update' in notice and 'sha256:' in notice,
                'steered peer notice lacks stable event reference')
            require('msg-1' not in notice, 'sender received its own message as a peer notice')
            second = runner._updates(worker_context, steering, delivered)
            require(second == delivered and len(steering.sent) == 1, 'same notice was steered twice')

            status = tool_json(native.host_call('engagement_status', {'since': None, 'limit': 100}).wait())
            cursor = status['next_cursor']
            ack = native.host_call('engagement_submit', {'request': {'request_id': 'native-ack',
                'expected_revision': case.c.state()['revision'], 'type': 'updates_ack',
                'payload': {'cursor': cursor}}}).wait()
            require(not ack.get('isError'), 'native cursor acknowledgement failed')
            restored = Controller(case.c.root)
            require(restored.state()['workers']['lead-1']['cursor'] == cursor,
                'acknowledged cursor did not survive controller reconstruction')
            recovered = restored.status(specialist, since=cursor, limit=100)
            cursor_sequence = restored._cursor(restored.state(), restored._events(), cursor)
            require(all(row['sequence'] > cursor_sequence for row in recovered['updates']),
                'explicit acknowledged cursor replayed old updates')
            no_replay = restored.notices(case.lead, since=0, limit=30)
            require('Peer update' not in json.dumps(no_replay), 'durable ACK replayed an old notice')
            submit(case, 'team_message', {'message_id': 'msg-after-ack', 'recipient_ids': ['lead-1'],
                'subject': 'After ACK', 'body': 'New journal update after saved cursor.', 'refs': []}, actor=specialist)
            recovered_notice = restored.notices(case.lead, since=0, limit=30)
            require('After ACK' in json.dumps(recovered_notice),
                'new notice was lost after controller reconstruction')
            rows.append({'name': 'peer_message_steering_ack_recovery', 'status': 'pass',
                'steered_notices': len(steering.sent), 'cursor': cursor})

            # Revocation invalidates the old principal and cannot be undone by its message.
            case.c.revoke_worker('specialist-1', 1, reason='fixture_revocation')
            refused('worker_stale', lambda: submit(case, 'team_message', {
                'message_id': 'stale-message', 'recipient_ids': ['lead-1'],
                'subject': 'late', 'body': 'must not revive worker', 'refs': []}, actor=specialist))
            refused('worker_stale', lambda: case.c.submit(specialist, {'request_id': 'stale-ack',
                'expected_revision': case.c.state()['revision'], 'type': 'updates_ack',
                'payload': {'cursor': cursor}}))
            refused('message_recipient_invalid', lambda: submit(case, 'team_message', {
                'message_id': 'revoked-recipient', 'recipient_ids': ['specialist-1'],
                'subject': 'late delivery', 'body': 'must not reach a revoked worker', 'refs': []}))
            stale_context = WorkerContext(runner, case.c.state()['workers']['specialist-1'],
                context.grant, context.workspace)
            sent_before_revoke = len(steering.sent)
            refused('worker_stale', lambda: runner._updates(stale_context, steering, 0))
            require(len(steering.sent) == sent_before_revoke, 'queued notice was steered to revoked worker')
            require(case.c.state()['workers']['specialist-1']['status'] == 'revoked',
                'late peer message revived revoked worker')
            rows.append({'name': 'revoked_worker_cannot_message_or_revive', 'status': 'pass'})
            native.finish()

            export = work / 'board-export'
            require(case.c.export(export)['status'] == 'exported', 'engagement export failed')
            board_export = json.loads((export / 'board.json').read_bytes())
            require(any(row['id'] == 'msg-peer' and row['author'] == 'specialist-1'
                for row in board_export['items']), 'exported derived board omitted peer provenance')
            rows.append({'name': 'cli_socket_and_export', 'status': 'pass',
                'export_revision': board_export['snapshot_revision']})

    report = {'kind': 'engagement-board-steering-e2e-v1', 'classification': 'engineering_simulation',
        'provider_calls': 0, 'docker_calls': 0, 'target_calls': 0, 'research_acceptance': 'not_run',
        'scenarios': rows}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output), sort_keys=True))


if __name__ == '__main__':
    main()
