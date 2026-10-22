#!/usr/bin/env python3
"""Provider-free packet to native receipt check for bounded reviewer material."""

import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from fresh_review import invoke_fresh_review, prepare_packet, validate_public_bytes


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def need(value, name, checks):
    checks.append({'name': name, 'pass': bool(value)})
    if not value:
        raise AssertionError(name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    output = parser.parse_args().output
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    report = {'status': 'fail', 'classification': 'synthetic reviewer material only',
              'provider_calls': 0, 'docker_calls': 0, 'target_calls': 0, 'checks': []}
    checks = report['checks']
    try:
        with tempfile.TemporaryDirectory(prefix='t03-live-review-material-') as temporary:
            root = Path(temporary)
            observer = root / 'observer'
            observer.mkdir()
            files = {'CLAIM.md': b'C1: possible local note.\n',
                     'CONDITIONS.json': b'{"actor":"synthetic"}\n',
                     'source.py': b'def note(): return 1\n',
                     'RAW.json': b'{"result":"one"}\n',
                     'CONTRARY.json': b'{"result":"control held"}\n',
                     'UNFINISHED.json': b'{"next":"check original effect"}\n'}
            for name, data in files.items():
                (observer / name).write_bytes(data)
            source = {'source.py': sha(files['source.py'])}
            source_digest = sha(json.dumps(source, sort_keys=True).encode())
            (root / 'plan.json').write_bytes(encoded({'source_manifest_sha256': source_digest,
                                                      'source_sha256': source}))
            selection = {'claim_id': 'C1', 'claim_version': 'v1',
                         'source_manifest_sha256': source_digest,
                         'source_paths': {'source.py': 'source.py'},
                         'roles': {'claim': ['CLAIM.md'], 'conditions': ['CONDITIONS.json'],
                                   'source': ['source.py'], 'raw': ['RAW.json'],
                                   'contrary': ['CONTRARY.json'],
                                   'unfinished': ['UNFINISHED.json']},
                         'files': {name: sha(data) for name, data in files.items()}}
            manifest = root / 'SELECTION.json'
            manifest.write_bytes(encoded(selection))
            packet = root / 'handoff/reviewer-1'
            packet.mkdir(parents=True)
            pin = prepare_packet(observer, manifest, sha(manifest.read_bytes()), packet,
                                 public_bytes=validate_public_bytes)
            request = json.loads((packet / 'REQUEST.json').read_text())
            conclusion = {'input_id': pin['input_id'], 'decision': 'unfinished',
                          'checked_link': 'possible local note', 'valid_base': ['source branch'],
                          'missing_transitions': ['original effect'], 'contrary': ['control held'],
                          'lead_dispositions': [{'basis_examined': 'source branch',
                                                 'uncertain_condition': 'actor state',
                                                 'next_check': 'observe original effect',
                                                 'decision': 'unfinished'}],
                          'limits': ['synthetic only'], 'next_check': 'original effect'}

            def stream(*, session='ses_Fresh1', shell_session=None, shell_output='private-tool-body',
                       shell_status='completed', omit_read=False, outcome=None):
                rows = []
                for name in ('REQUEST.json', *request['files']):
                    if omit_read and name == 'CONTRARY.json':
                        continue
                    rows.append({'sessionID': session, 'part': {'type': 'tool', 'tool': 'read',
                        'state': {'status': 'completed', 'input': {'filePath': '/handoff/' + name},
                                  'output': 'read', 'error': None}}})
                rows.append({'sessionID': shell_session or session,
                    'part': {'type': 'tool', 'tool': 'shell',
                             'state': {'status': shell_status,
                                       'input': {'command': 'printf checked'},
                                       'output': shell_output,
                                       'error': 'failed' if shell_status != 'completed' else None}}})
                rows.append({'sessionID': session, 'part': {'type': 'text',
                                                              'text': json.dumps(conclusion) if outcome is None else outcome}})
                return ''.join(json.dumps(row) + '\n' for row in rows)

            class Native:
                def __init__(self, stdout, *, reported_digest=None):
                    self.stdout = stdout
                    self.reported_digest = reported_digest or sha(stdout.encode())
                    self.sessions = []
                    self.tunnels = 1

                def api(self, run_root, role, *parts):
                    assert run_root == root and role == 'reviewer-1'
                    if parts[0] == 'session.list':
                        return {'data': [{'id': sid} for sid in self.sessions]}
                    if parts[0] == 'session.create':
                        self.sessions.append('ses_Fresh1')
                        return {'data': {'id': 'ses_Fresh1'}}
                    if parts[0] == 'session.message.list':
                        return {'data': []}
                    if parts[0] == 'session.get':
                        return {'data': {'id': 'ses_Fresh1', 'cost': None, 'tokens': None}}
                    raise AssertionError(parts)

                def invoke(self, run_root, role, session, prompt, *, include_raw=False):
                    assert run_root == root and role == 'reviewer-1' and include_raw
                    assert session == 'ses_Fresh1' and '/handoff/REQUEST.json' in prompt
                    self.tunnels += 1
                    return {'status': 'acknowledged', 'dispatch_id': 'd' * 32,
                            'role': role, 'session_id': session,
                            'stdout_sha256': self.reported_digest,
                            'native_trace_sha256': 'e' * 64,
                            'review_target_id': 'f' * 64,
                            'review_target_source_sha256': source_digest,
                            '_raw_stdout': self.stdout}

                def allowance(self, run_root):
                    return {'run_identity': {'nonce': 'synthetic', 'manifest_sha256': 'a' * 64},
                            'hard_limits': {'max_connections': 8, 'max_bytes': 10000},
                            'used_tunnels': self.tunnels,
                            'charged_tunnel_bytes': self.tunnels, 'active': True}

                def active(self, run_root):
                    return True

            def review(stdout, *, reported_digest=None):
                native = Native(stdout, reported_digest=reported_digest)
                return invoke_fresh_review(root, packet, pin, 'reviewer-1',
                                           native_api=native.api, invoke_native=native.invoke,
                                           allowance_snapshot=native.allowance,
                                           run_active=native.active,
                                           public_bytes=validate_public_bytes)

            receipt = review(stream())
            material = receipt['material']
            need(receipt['assessment']['status'] == 'unfinished',
                 'live assessment remains unfinished', checks)
            need(material['status'] == 'captured' and material['kind'] == 'native-review-material-v1',
                 'structured material captured', checks)
            need(material['input_id'] == pin['input_id']
                 and material['packet_pin'] == pin
                 and material['packet_request_sha256'] == pin['files']['REQUEST.json']
                 and material['source_revision'] == request['source_revision']
                 and material['evidence_revision'] == request['evidence_revision']
                 and material['dispatch_id'] == 'd' * 32
                 and material['session_id'] == 'ses_Fresh1'
                 and material['native_trace_sha256'] == 'e' * 64,
                 'packet dispatch session and trace bound', checks)
            action = material['shell_actions'][0]
            need(len(material['shell_actions']) == 1 and action['line'] > 0
                 and action['command_sha256'] == sha(b'printf checked')
                 and len(action['input_sha256']) == len(action['output_sha256']) == 64,
                 'completed shell action hashes captured', checks)
            serialized = encoded(receipt)
            need(b'private-tool-body' not in serialized and b'printf checked' not in serialized
                 and b'_raw_stdout' not in serialized,
                 'raw tool body command and stdout omitted', checks)
            need(review(stream(), reported_digest='0' * 64)['material']['status'] == 'held',
                 'changed stdout digest held', checks)
            need(review(stream(shell_session='ses_Other1'))['material']['status'] == 'held',
                 'other session shell held', checks)
            need(review(stream(shell_status='failed'))['material']['status'] == 'held',
                 'failed shell held', checks)
            need(review(stream(shell_output=''))['material']['status'] == 'held',
                 'empty shell output held', checks)
            need(review(stream(omit_read=True))['material']['status'] == 'held',
                 'missing packet read held', checks)
            unsafe = dict(conclusion, limits=['Authorization: Bearer abcdefghijklmnopqrstuvwxyz'])
            held = review(stream(outcome=json.dumps(unsafe)))['material']
            need(held['status'] == 'held' and 'outcome' not in held,
                 'unsafe conclusion omitted', checks)
            duplicate = '{"input_id":"' + pin['input_id'] + '","input_id":"' + pin['input_id'] + '"}'
            need(review(stream(outcome=duplicate))['material']['status'] == 'held',
                 'duplicate conclusion keys held', checks)
            need(review(stream(outcome='{"value":NaN}'))['material']['status'] == 'held',
                 'nonfinite conclusion held', checks)
        report['status'] = 'pass'
        print('PASS: bounded reviewer material projection; provider/Docker/target calls: 0')
    finally:
        (output / 'result.json').write_bytes(encoded(report))


if __name__ == '__main__':
    main()
