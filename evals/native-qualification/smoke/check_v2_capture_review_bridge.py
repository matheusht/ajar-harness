#!/usr/bin/env python3
"""Owned file-to-packet-to-final-receipt check; no Docker, model or provider."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import runpy
import shutil
import tempfile


ROOT = Path(__file__).resolve().parents[3]
RUNNER = ROOT / 'evals/native-qualification/smoke/opencode_v2_managed_owned.py'
OBSERVATION = ROOT / 'experiments/native-observation-qualification/native_observation.py'
FIXTURE = ROOT / 'evals/native-qualification/smoke'
SCENARIO = 'owned-t02-bridge-run'
SESSION = 'owned-research-session'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def receipt(case_id, request, response, sequence):
    effect = sha(b'unchanged owned state')
    return {'case_id': case_id, 'effect': 'unchanged',
            'effect_after_sha256': effect, 'effect_before_sha256': effect,
            'method': 'GET', 'outcome': 'authorized', 'path_class': 'owned_read',
            'request_sha256': sha(request), 'response_sha256': sha(response),
            'route_class': 'observer', 'sequence': sequence, 'status_code': 200}


def synthetic_capture(observation, note, source):
    claim_sha = sha(note.read_bytes())
    manifest = {'dependencies': {}, 'files': {'message.php': sha(source.read_bytes())},
                'parent_version_ids': [], 'source_id': 'owned-synthetic-php',
                'version_id': 'owned-bridge-fixture-v1'}
    source_pins = {'manifest': manifest, 'manifest_sha256': observation['digest'](manifest)}
    original = receipt('native-read', b'native request', b'native result', 11)
    replay = receipt('host-replay', b'host request', b'host result', 21)
    run = {
        'cases': [
            {'application_receipts': [original], 'bypass_receipts': [], 'case_id': 'native-read',
             'dispatch': {'close_sequence': 12, 'dispatch_id': 'owned-dispatch',
                          'open_sequence': 10, 'request_intent_sha256': original['request_sha256'],
                          'session_binding': SESSION, 'tool_binding': 'owned-tool'},
             'host_activity': [], 'producer_observer_visible': False,
             'producer_observer_writable': False,
             'response': {'sha256': original['response_sha256'], 'status_code': 200},
             'trace': {'attribution_verified': True,
                       'connects': [{'address_class': 'owned_loopback', 'admitted': True,
                                     'destination_class': 'observer'}],
                       'process_binding': 'exact_spawned_subtree',
                       'raw_trace_retained': False, 'subtree_exit': 'observed_zero'}},
            {'application_receipts': [replay], 'bypass_receipts': [], 'case_id': 'host-replay',
             'dispatch': None, 'host_activity': [
                 {'case_id': 'host-replay', 'kind': 'host_client_open', 'sequence': 20},
                 {'case_id': 'host-replay', 'kind': 'host_client_close', 'sequence': 22}],
             'producer_observer_visible': None, 'producer_observer_writable': None,
             'response': {'sha256': replay['response_sha256'], 'status_code': 200},
             'trace': None}],
        'chain_state': {'consumed': [], 'contrary_results': [], 'missing_transitions': [],
                        'produced': [], 'unfinished_conditions': [
                            {'condition': 'managed native capture and fresh review', 'status': 'not_run'}]},
        'hypothesis': {'agent_discovery_credited': False, 'allowed_effects': [],
                       'authority': 'owned_synthetic_local_only',
                       'conditions': {'claim_sha256': claim_sha},
                       'hypothesis_id': 'owned-bridge-hypothesis',
                       'next_test': 'qualify managed native observation',
                       'nonclaims': ['managed_native_capture', 'fresh_independent_review'],
                       'objective': 'check the file handoff', 'origin': 'operator_authored_fixture',
                       'statement': 'The owned synthetic request has a distinct host replay.',
                       'status': 'owned_fixture_only'},
        'observer_boundary': {'allowed_address_classes': ['owned_loopback'],
                              'allowed_nonroute_destination_classes': [], 'available': True,
                              'declared_route': 'observer',
                              'producer_storage_visibility': 'absent_from_producer_namespace',
                              'qualification_scope': 'owned_fixture_only_managed_native_unavailable',
                              'route_completeness_claimed': False, 'storage_owner': 'host_fixture'},
        'repeatability': {'normalized_match': None, 'runs': 1},
        'scenario_id': SCENARIO, 'schema_version': 1, 'source_pins': source_pins,
    }
    bundle = observation['evaluate_capture_run'](run)
    assert bundle['result']['status'] == 'observation_capture_ready_not_finalized'
    return bundle, source_pins['manifest_sha256']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('t02_capture_bridge', RUNNER)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    observation = runpy.run_path(str(OBSERVATION))
    with tempfile.TemporaryDirectory(prefix='t02-capture-bridge-') as temporary:
        root = Path(temporary)
        originals, candidate = root / 'originals', root / 'candidate'
        originals.mkdir()
        candidate.mkdir()
        for name in runner.PACKET_SOURCE_NAMES:
            data = (FIXTURE / name).read_bytes()
            (originals / name).write_bytes(data)
            (candidate / name).write_bytes(data)
        message = candidate / 'message.php'
        message.write_text(message.read_text().replace("return 'before';", "return 'after';"))
        note = candidate / 'research-note.md'
        note.write_text('Harmless local change: message() returns after; php check.php passed.\n')
        capture_bundle, source_sha = synthetic_capture(observation, note, message)
        capture = root / 'capture'
        observation['write_bundle'](capture_bundle, capture)
        capture_sha = observation['capture_manifest_sha256'](capture)
        expected = {'path': capture, 'manifest_sha256': capture_sha,
                    'source_manifest_sha256': source_sha,
                    'scenario_id': SCENARIO, 'session_id': SESSION}
        stream = json.dumps({'type': 'tool_use', 'part': {'type': 'tool', 'tool': 'shell',
            'state': {'status': 'completed', 'input': {'command': 'php check.php'},
                      'output': 'check passed\n'}}}) + '\n'
        before = {name: sha((originals / name).read_bytes()) for name in runner.PACKET_SOURCE_NAMES}
        after = {name: sha((candidate / name).read_bytes()) for name in runner.PACKET_SOURCE_NAMES}
        checks = {'baseline': {'source_sha256': before, 'results': []},
                  'candidate': {'source_sha256': after, 'results': []}}

        def publish(folder, supplied=expected):
            folder.mkdir()
            return runner.publish_review_packet(folder, originals, candidate, note, stream,
                checks, 'local_' + 'a' * 32, forbidden_paths=(str(root),),
                protected_observation=supplied)

        packet = root / 'packet'
        pin = publish(packet)
        assert runner.verify_review_packet(packet, pin)
        request = json.loads((packet / 'REQUEST.json').read_text())
        assert request['original_observation']['status'] == 'unavailable'
        assert request['capture_candidate']['status'] == 'observation_capture_ready_not_finalized'
        assert request['capture_candidate']['capture_manifest_sha256'] == capture_sha
        assert request['capture_candidate']['source_manifest_sha256'] == source_sha
        assert request['capture_candidate']['scenario_id'] == SCENARIO
        assert request['capture_candidate']['session_id'] == SESSION
        assert request['claim_version'] == sha(note.read_bytes())
        assert request['capture_candidate']['qualification'] == 'caller_supplied_unqualified'
        for name in ('hypothesis.json', 'observation.json', 'evidence.json', 'result.json'):
            assert (packet / ('CAPTURE-' + name)).read_bytes() == (capture / name).read_bytes()
        observed = json.loads((packet / 'CAPTURE-observation.json').read_text())
        assert {case['case_id']: case['status'] for case in observed['case_observations']} == {
            'native-read': 'observed', 'host-replay': 'host_replay'}
        assert 'CAPTURE-observation.json' in (packet / 'PROMPT.txt').read_text()
        archive = root / 'archive'
        runner.archive_review_packet(packet, archive, pin)

        for label, altered in (
            ('capture', {'manifest_sha256': '0' * 64}),
            ('source', {'source_manifest_sha256': '0' * 64}),
            ('run', {'scenario_id': 'wrong-run'}),
            ('session', {'session_id': 'wrong-session'}),
        ):
            rejected = root / ('reject-' + label)
            try:
                publish(rejected, {**expected, **altered})
            except Exception:
                assert not list(rejected.iterdir()), label
            else:
                raise AssertionError(label)
        changed_note = candidate / 'changed-note.md'
        changed_note.write_text('Different claim.\n')
        original_note = note.read_bytes()
        note.write_bytes(changed_note.read_bytes())
        try:
            rejected = root / 'reject-claim'
            publish(rejected)
        except Exception:
            assert not list(rejected.iterdir())
        else:
            raise AssertionError('claim')
        note.write_bytes(original_note)

        for label in ('changed', 'missing', 'symlink', 'extra'):
            damaged = root / ('damaged-' + label)
            shutil.copytree(capture, damaged)
            target = damaged / 'observation.json'
            if label == 'changed':
                target.write_bytes(target.read_bytes() + b' ')
            elif label == 'missing':
                target.unlink()
            elif label == 'symlink':
                target.unlink()
                target.symlink_to(capture / 'observation.json')
            else:
                (damaged / 'extra.json').write_text('{}')
            rejected = root / ('reject-' + label)
            try:
                publish(rejected, {**expected, 'path': damaged})
            except Exception:
                assert not list(rejected.iterdir()), label
            else:
                raise AssertionError(label)

        secret = root / 'secret-capture'
        shutil.copytree(capture, secret)
        hypothesis = json.loads((secret / 'hypothesis.json').read_text())
        hypothesis['conditions']['Authorization'] = 'Bearer test-only'
        (secret / 'hypothesis.json').write_bytes(observation['canonical_bytes'](hypothesis))
        result = json.loads((secret / 'result.json').read_text())
        result['artifacts']['hypothesis.json'] = sha((secret / 'hypothesis.json').read_bytes())
        (secret / 'result.json').write_bytes(observation['canonical_bytes'](result))
        secret_manifest = observation['digest']({p.name: sha(p.read_bytes()) for p in secret.iterdir()})
        rejected = root / 'reject-secret'
        try:
            publish(rejected, {**expected, 'path': secret, 'manifest_sha256': secret_manifest})
        except Exception:
            assert not list(rejected.iterdir())
        else:
            raise AssertionError('secret')

        stopped = {'run_verified': True, 'provider_admission_closed': True,
                   'exact_producers_stopped': True, 'ordered_monotonic': True}
        cleanup = {'cleanup_complete': True, 'temporary_secret_files_removed': True,
                   'source_pins_stable': True}
        final_cleanup = {'checks': {name: True for name in observation['CLEANUP_CHECK_KEYS']},
                         'status': 'complete', 'stop_verified': True}
        for label, stop, clean, projection in (
            ('run', {**stopped, 'run_verified': False}, cleanup, final_cleanup),
            ('producer', {**stopped, 'exact_producers_stopped': False}, cleanup, final_cleanup),
            ('cleanup', stopped, {**cleanup, 'cleanup_complete': False}, final_cleanup),
            ('observer', stopped, cleanup, {**final_cleanup, 'checks':
                                           {**final_cleanup['checks'], 'observer_processes_stopped': False}}),
        ):
            receipt_path = root / ('reject-final-' + label)
            try:
                runner.finalize_review_capture(capture, pin, archive, stop, clean,
                                               projection, receipt_path)
            except Exception:
                assert not receipt_path.exists(), label
            else:
                raise AssertionError(label)
        (archive / 'CAPTURE-observation.json').write_bytes(b'changed')
        receipt_path = root / 'reject-final-packet'
        try:
            runner.finalize_review_capture(capture, pin, archive, stopped, cleanup,
                                           final_cleanup, receipt_path)
        except Exception:
            assert not receipt_path.exists()
        else:
            raise AssertionError('packet drift')
        shutil.copy2(packet / 'CAPTURE-observation.json', archive / 'CAPTURE-observation.json')
        final_path = root / 'final-receipt'
        final = runner.finalize_review_capture(capture, pin, archive, stopped, cleanup,
                                               final_cleanup, final_path)
        assert final['status'] == 'observation_capture_finalized'
        assert final['qualification_scope'] == 'capture_lifecycle_only'
        assert final['review_status'] == 'not_observed'
        assert final['scenario_id'] == SCENARIO
        assert final['capture_manifest_sha256'] == capture_sha
        assert json.loads((final_path / 'finalization.json').read_text()) == final
        assert observation['capture_manifest_sha256'](capture) == capture_sha

        ordinary = root / 'ordinary-packet'
        publish(ordinary, None)
        ordinary_request = json.loads((ordinary / 'REQUEST.json').read_text())
        assert ordinary_request['original_observation']['status'] == 'unavailable'
        assert 'capture_candidate' not in ordinary_request
        receipt = {
            'classification': 'owned synthetic source bridge; no managed native capture or review',
            'status': 'pass', 'provider_calls': 0, 'target_calls': 0,
            'capture_status': capture_bundle['result']['status'],
            'capture_manifest_sha256': capture_sha,
            'packet_request_sha256': sha((packet / 'REQUEST.json').read_bytes()),
            'finalization_status': final['status'],
            'qualification_scope': final['qualification_scope'],
            'review_status': final['review_status'],
            'scenario_id': final['scenario_id'],
            'original_observation_status': request['original_observation']['status'],
            'checks': {'sealed_capture_and_exact_copy': True,
                       'source_run_session_claim_binding': True,
                       'malformed_secret_and_drift_rejected': True,
                       'host_replay_distinct': True,
                       'global_stop_and_cleanup_required': True,
                       'ordinary_packet_unchanged': True},
            'source_sha256': {'runner': sha(RUNNER.read_bytes()),
                              'observation_evaluator': sha(OBSERVATION.read_bytes())},
        }
        if args.output:
            output = args.output
            if not output.is_absolute() or output.exists() or output.is_symlink() or not output.parent.is_dir():
                raise ValueError('output_must_be_absent_with_existing_parent')
            output.mkdir(mode=0o700)
            result = output / 'result.json'
            result.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
            result.chmod(0o600)
    print('PASS: synthetic capture to fixed review packet to guarded final receipt; no Docker/model/provider')


if __name__ == '__main__':
    main()
