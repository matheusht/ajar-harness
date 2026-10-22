#!/usr/bin/env python3
"""Provider-free setup E2E for a fresh native review; no model or target call."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fresh_review import (prepare_packet, verify_packet, invoke_fresh_review,
                          assess_review, validate_public_bytes)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def rejected(action):
    try:
        action()
    except (ValueError, RuntimeError):
        return
    raise AssertionError('invalid fresh review input accepted')


def require(condition, name):
    if not condition:
        raise RuntimeError('setup check failed: ' + name)


def main():
    with tempfile.TemporaryDirectory(prefix='t03-fresh-review-') as tmp:
        root = Path(tmp)
        observer = root / 'observer'
        observer.mkdir()
        material = {
            'CLAIM.md': b'C1 v1: a local branch might retain a note. Supported base only.\n',
            'CONDITIONS.json': encoded({'actor': 'synthetic', 'state': 'draft present'}),
            'source.py': b'def retain(note):\n    return note\n',
            'RAW.json': encoded({'attempts': [{'result': 'note retained'}]}),
            'CONTRARY.json': encoded({'attempts': [{'result': 'no note without draft'}]}),
            'UNFINISHED.json': encoded({'leads': [{'id': 'B', 'basis': 'source branch',
                'uncertain_condition': 'draft is reachable', 'next_check': 'execute local branch'}]}),
        }
        for name, data in material.items():
            (observer / name).write_bytes(data)
        source_map = {'source.py': sha(material['source.py'])}
        source_manifest_sha256 = sha(json.dumps(source_map, sort_keys=True).encode())
        (root / 'plan.json').write_bytes(encoded({'source_manifest_sha256': source_manifest_sha256,
                                                 'source_sha256': source_map}))
        selection = {'claim_id': 'C1', 'claim_version': 'v1',
            'source_manifest_sha256': source_manifest_sha256,
            'source_paths': {'source.py': 'source.py'},
            'roles': {'claim': ['CLAIM.md'], 'conditions': ['CONDITIONS.json'],
                      'source': ['source.py'], 'raw': ['RAW.json'],
                      'contrary': ['CONTRARY.json'], 'unfinished': ['UNFINISHED.json']},
            'files': {name: sha(data) for name, data in material.items()}}
        manifest = root / 'SELECTION.json'
        manifest.write_bytes(encoded(selection))
        handoff = root / 'handoff' / 'reviewer-1'
        handoff.mkdir(parents=True)
        pin = prepare_packet(observer, manifest, sha(manifest.read_bytes()), handoff,
                             public_bytes=validate_public_bytes)
        require(verify_packet(handoff, pin), 'frozen packet')
        request = json.loads((handoff / 'REQUEST.json').read_text())
        require(request['input_id'] == pin['input_id'], 'input identity')
        require(request['roles']['contrary'] == ['CONTRARY.json'], 'contrary role')
        require(set(request['files']) == set(material), 'exact material inventory')
        require((handoff / 'RAW.json').read_bytes() == material['RAW.json'], 'raw byte copy')
        require((observer / 'RAW.json').read_bytes() == material['RAW.json'], 'source unchanged')

        changed = observer / 'CONTRARY.json'
        changed.write_bytes(b'{}\n')
        second = root / 'changed-source-packet'
        second.mkdir()
        rejected(lambda: prepare_packet(observer, manifest, sha(manifest.read_bytes()), second,
                                        public_bytes=validate_public_bytes))
        require(not list(second.iterdir()), 'rejected packet stays empty')
        changed.write_bytes(material['CONTRARY.json'])
        (observer / 'extra-answer.txt').write_text('expected answer')
        rejected(lambda: prepare_packet(observer, manifest, sha(manifest.read_bytes()), second,
                                        public_bytes=validate_public_bytes))
        (observer / 'extra-answer.txt').unlink()

        class Native:
            sessions = []
            calls = []
            counters = 3

            def api(self, run_root, role, *parts):
                require(run_root == root and role == 'reviewer-1', 'reviewer API role')
                self.calls.append(('api', role, parts[0]))
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

            def invoke_native(self, run_root, role, session, prompt, *, include_raw=False):
                require(run_root == root and role == 'reviewer-1', 'reviewer native role')
                self.calls.append(('run', role, session))
                require(session == 'ses_Fresh1', 'fresh session')
                require('/handoff/REQUEST.json' in prompt and 'CONTRARY.json' in prompt,
                        'neutral prompt includes contrary material')
                require(include_raw, 'transient raw trace requested')
                self.counters += 1
                return {'status': 'acknowledged', 'role': role, 'session_id': session,
                        'dispatch_id': 'd1', 'stdout_sha256': sha(b''), '_raw_stdout': '',
                        'review_target_id': 'clean-target-1',
                        'review_target_source_sha256': source_manifest_sha256}

            def allowance_snapshot(self, run_root):
                require(run_root == root, 'same run root')
                return {'run_identity': {'manifest_sha256': 'b' * 64, 'nonce': 'n',
                    'ids': ['researcher', 'reviewer'], 'deadline_monotonic': 9999999999,
                    'created_monotonic': 1},
                    'hard_limits': {'max_connections': 5, 'max_bytes': 999,
                                    'pool_deadline': 9999999999},
                    'used_tunnels': self.counters, 'charged_tunnel_bytes': self.counters,
                    'active': True}

            def run_active(self, run_root):
                require(run_root == root, 'active same run')
                return True

        native = Native()
        invocation = invoke_fresh_review(
            root, handoff, pin, 'reviewer-1', native_api=native.api, invoke_native=native.invoke_native,
            allowance_snapshot=native.allowance_snapshot, run_active=native.run_active,
            public_bytes=validate_public_bytes)
        require(invocation['status'] == 'native_turn_observed_unassessed', 'observed turn')
        require(invocation['session_id'] == 'ses_Fresh1', 'fresh session recorded')
        require(native.calls.index(('api', 'reviewer-1', 'session.create')) < native.calls.index(
            ('run', 'reviewer-1', 'ses_Fresh1')), 'session before inference')
        require(invocation['allowance_after']['charged_tunnel_bytes'] >
                invocation['allowance_before']['charged_tunnel_bytes'], 'same allowance used')
        require(invocation['assessment']['status'] == 'unfinished', 'no fake qualification')
        require(assess_review(handoff, pin, invocation, '', None)['status'] == 'unfinished',
                'missing trace remains unfinished')
        require(verify_packet(handoff, pin), 'packet survives turn')
        (handoff / 'RAW.json').chmod(0o600)
        (handoff / 'RAW.json').write_bytes(b'changed\n')
        require(not verify_packet(handoff, pin), 'post-run drift rejected')

    print(json.dumps({'status': 'provider_free_setup_passed', 'native_model_review': 'not_run',
                      'live_provider_calls': 0, 'hidden_case': 'not_used'}, sort_keys=True))


if __name__ == '__main__':
    main()
