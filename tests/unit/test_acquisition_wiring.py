"""Pure acquisition policy/provenance tests; no sockets, runtimes or files."""
import copy
from contextlib import nullcontext
import hashlib
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from acquisition_network import LabRequestBinder
from engagement_acquisition import validate_observation, record, projection
from engagement_contract import canonical, digest
from engagement_controller import ControllerError, Controller as RealController
from engagement_evidence import comparable
from engagement_network import NetworkDenied


def route(host):
    return {'protocol': 'https', 'host': host, 'port': 443}


def scope():
    return {'network': {'provider': [route('provider.invalid')], 'target': [route('target.invalid')],
                        'acquisition': [route('packages.invalid')]},
            'environments': [{'profile_id': 'lab', 'capabilities': ['source', 'acquisition']}]}


def intent():
    return {'kind': 'acquisition-network-observation-v1', 'phase': 'intent', 'operation_id': 'download-1',
            'origin': 'https://packages.invalid:443', 'method': 'GET',
            'path_sha256': 'sha256:' + 'a'*64, 'display_url': 'https://packages.invalid:443/pkg'}


def result():
    return dict(intent(), phase='result', status='settled', http_status=200, request_bytes=0,
                response_bytes=3, body_complete=True, body_kind='whole', response_sha256=digest(b'abc'))


class Controller:
    def __init__(self):
        self.grant = {'worker_id': 'worker', 'generation': 1, 'dispatch_id': 'dispatch', 'resources': ['source']}
        self.value = {'scope': scope(), 'environments': {'nonce': {'profile_id': 'lab', 'worker_id': 'worker', 'generation': 1}},
            'environment_operations': {'operation': {'identity': {'nonce': 'nonce'}, 'grant': self.grant}},
            'network_operations': {}}
        self.authorizations = 0
    def lock(self): return nullcontext()
    def state(self): return self.value
    def bind_grant(self, state, grant):
        if grant != self.grant: raise ControllerError('grant_invalid')
    def _authorize(self, state, grant): self.authorizations += 1
    def store_object(self, data): return digest(data)
    def _host(self, kind, event):
        data = event['data']; observation = data['observation']
        row = self.value['network_operations'].setdefault(observation['operation_id'],
            {'grant': data['grant'], 'profile_id': data['profile_id'], 'environment_nonce': data['environment_nonce'],
             'receipts': [], 'result': None})
        row[observation['phase']] = observation
        row['receipts'].append(data['receipt_sha256'])
        return {'status': 'recorded', 'receipt': data['receipt_sha256']}


class AcquisitionTests(unittest.TestCase):
    def binder(self, value=None):
        events = []
        return LabRequestBinder(value or scope(), 'lab', lambda: None, events.append), events

    def test_get_exact_binary_digest(self):
        binder, events = self.binder()
        binding = binder.bind('GET', 'https://packages.invalid/pkg', {}, request_length=0)
        class Response:
            status = 200
            def getheaders(self): return [('Content-Type', 'application/octet-stream')]
            def getheader(self, name, default=None): return default
        binding.accept_response(Response())
        body = b'\x00\xff\x01abc'
        self.assertEqual(binding.filter_chunk(body, final=True), body)
        binding.finish('settled', 200, 0)
        self.assertEqual(events[-1]['response_sha256'], digest(body))
        self.assertTrue(events[-1]['body_complete'])
        validate_observation(events[-1])

    def test_rejected_response_keeps_incomplete_provenance(self):
        binder, events = self.binder()
        binding = binder.bind('GET', 'https://packages.invalid/pkg', {}, request_length=0)
        class Response:
            status = 200
            def getheaders(self): return [('Content-Encoding', 'gzip')]
            def getheader(self, name, default=None): return 'gzip'
        with self.assertRaises(NetworkDenied): binding.accept_response(Response())
        binding.finish('unknown', 200, 0)
        validate_observation(events[-1])
        self.assertEqual(events[-1]['status'], 'unknown')
        self.assertFalse(events[-1]['body_complete'])
        self.assertIsNone(events[-1]['response_sha256'])
        self.assertEqual(events[-1]['body_kind'], 'whole')

    def test_reject_method_and_body_before_intent(self):
        for method, length in [('POST', 0), ('GET', None), ('GET', 1), ('GET', True)]:
            binder, events = self.binder()
            with self.assertRaises(NetworkDenied): binder.bind(method, 'https://packages.invalid/p', {}, request_length=length)
            self.assertFalse(events)

    def test_provider_and_unlisted_routes_denied(self):
        for host in ('provider.invalid', 'other.invalid', 'target.invalid'):
            binder, events = self.binder()
            with self.assertRaises(NetworkDenied): binder.bind('GET', 'https://' + host + '/p', {}, request_length=0)
            self.assertFalse(events)

    def test_target_delegate_preserves_binding_and_length(self):
        calls = []
        sentinel = object()
        class Targets:
            def bind(self, method, url, headers, *, request_length):
                calls.append((method, url, headers, request_length))
                return sentinel
        binder = LabRequestBinder(scope(), 'lab', lambda: None, lambda value: self.fail('unexpected acquisition record'), Targets())
        headers = {'X-OSLit-Access': 'app'}
        actual = binder.bind('POST', 'https://target.invalid/write', headers, request_length=9)
        self.assertIs(actual, sentinel)
        self.assertEqual(calls, [('POST', 'https://target.invalid/write', headers, 9)])

    def test_capability_required(self):
        value = scope(); value['environments'][0]['capabilities'] = ['source']
        binder, events = self.binder(value)
        with self.assertRaises(NetworkDenied): binder.bind('GET', 'https://packages.invalid/p', {}, request_length=0)
        self.assertFalse(events)

    def test_secret_in_url_rejected_before_intent(self):
        import threading
        secret = b'fixture-private-value'
        class Targets:
            lock = threading.Lock()
            secrets = [secret]
        encoded = ''.join('%%%02X' % value for value in secret)
        for location in ('/' + secret.decode(), '/?q=' + secret.decode(), '/' + encoded, '/?q=' + encoded):
            with self.subTest(location=location):
                events = []
                binder = LabRequestBinder(scope(), 'lab', lambda: None, events.append, Targets())
                with self.assertRaisesRegex(NetworkDenied, 'acquisition_credentials_forbidden'):
                    binder.bind('GET', 'https://packages.invalid' + location, {}, request_length=0)
                self.assertFalse(events)

    def test_forbidden_and_duplicate_headers(self):
        for headers in ({'Authorization': 'not-a-real-key'}, {'Cookie': 'a=b'}, {'X-OSLit-Effect': 'effect'}, {'Accept': 'a', 'accept': 'b'}):
            binder, events = self.binder()
            with self.assertRaises(NetworkDenied): binder.bind('GET', 'https://packages.invalid/p', headers, request_length=0)
            self.assertFalse(events)

    def test_shape_validation(self):
        for change in ({'access_id': 'target'}, {'method': 'POST'}, {'path_sha256': 'bad'}, {'origin': 'https://u:p@packages.invalid:443'}, {'display_url': 'https://other.invalid:443/pkg'}):
            with self.subTest(change=change), self.assertRaises(ControllerError): validate_observation(dict(intent(), **change))

    def test_result_invalid_relations(self):
        for change in ({'request_bytes': 1}, {'response_bytes': True}, {'body_complete': 1}, {'response_sha256': None},
                       {'status': 'unknown'}, {'http_status': None}, {'body_kind': 'range'}, {'http_status': True}):
            with self.subTest(change=change), self.assertRaises(ControllerError): validate_observation(dict(result(), **change))

    def test_absent_and_partial_body(self):
        validate_observation(dict(result(), method='HEAD', response_bytes=0, body_kind='absent', response_sha256=None))
        validate_observation(dict(result(), body_complete=False, response_sha256=None))
        validate_observation(dict(result(), http_status=206, body_kind='range'))

    def test_real_controller_network_entrypoint_routes_acquisition(self):
        c = Controller()
        first = RealController.record_network_observation(c, c.grant, 'lab', 'nonce', intent())
        final = RealController.record_network_observation(c, c.grant, 'lab', 'nonce', result())
        self.assertEqual(first['status'], 'recorded')
        self.assertEqual(final['status'], 'recorded')
        self.assertEqual(c.value['network_operations']['download-1']['result'], result())

    def test_environment_entrypoint_rejects_acquisition_shape(self):
        c = Controller()
        with self.assertRaisesRegex(ControllerError, 'environment_observation_invalid'):
            RealController.record_environment_observation(c, c.grant, 'lab', intent(), effect_id='read')

    def test_record_intent_result_duplicate(self):
        c = Controller()
        first = record(c, c.grant, 'lab', 'nonce', intent())
        self.assertEqual(first, record(c, c.grant, 'lab', 'nonce', intent()))
        final = record(c, c.grant, 'lab', 'nonce', result())
        self.assertEqual(final, record(c, c.grant, 'lab', 'nonce', result()))
        self.assertEqual(c.authorizations, 1)

    def test_result_requires_intent_and_exact_binding(self):
        c = Controller()
        with self.assertRaisesRegex(ControllerError, 'network_intent_missing'): record(c, c.grant, 'lab', 'nonce', result())
        record(c, c.grant, 'lab', 'nonce', intent())
        with self.assertRaisesRegex(ControllerError, 'network_operation_conflict'):
            record(c, c.grant, 'lab', 'nonce', dict(result(), path_sha256='sha256:'+'b'*64))

    def test_target_nonce_and_overlap_denied(self):
        c = Controller()
        with self.assertRaises(ControllerError): record(c, c.grant, 'lab', 'nonce', intent(), target_nonce='target')
        c.value['scope']['network']['target'].append(route('packages.invalid'))
        with self.assertRaises(ControllerError): record(c, c.grant, 'lab', 'nonce', intent())
        self.assertEqual(c.authorizations, 0)

    def test_stopped_environment_denies_intent(self):
        c = Controller(); c.value['environments']['nonce']['stopped'] = True
        with self.assertRaises(ControllerError): record(c, c.grant, 'lab', 'nonce', intent())

    def test_projection_changes_prevent_comparison(self):
        row = {'intent': intent(), 'result': result()}
        selected = projection(row)
        left = {k: None for k in ('instrument_id', 'conditions', 'input_identity', 'environment_profile_id', 'effect_id', 'account_refs', 'resources')}
        self.assertTrue(comparable(left, dict(left, acquisition_bindings=[])))
        left['acquisition_bindings'] = [selected]
        right = copy.deepcopy(left); right['acquisition_bindings'][0]['response_sha256'] = digest(b'changed')
        self.assertFalse(comparable(left, right))

if __name__ == '__main__': unittest.main()
