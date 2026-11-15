#!/usr/bin/env python3
"""Self-check bounded OMP terminal-frame capture and secret redaction."""
import sys
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2] / 'tools')]

from check_linux_model_native_e2e import (diagnostic_omp_frame, observe_omp_native_events,
                                          diagnostic_omp_model_state, provider_request_diagnostic,
                                          NetworkDenialObserver)
from engagement_network import NetworkDenied

SECRET = b'synthetic-omp-key-9071'


def main():
    terminal = diagnostic_omp_frame({'type': 'prompt_result', 'status': 'error',
                                     'sessionSettled': False}, (SECRET,))
    assert terminal == {'event': 'prompt_result', 'status': 'error', 'session_settled': False}, terminal
    response_error = diagnostic_omp_frame({'type': 'prompt_result', 'status': 'error',
        'sessionSettled': True, 'errorMessage': 'request failed: synthetic-omp-key-9071'}, (SECRET,))
    assert 'error_message' not in response_error, response_error
    wire_error = diagnostic_omp_frame({'type': 'prompt_result', 'status': 'error',
        'sessionSettled': True, 'error': {'message': 'provider error: synthetic-omp-key-9071',
            'debugToken': 'do-not-copy'}}, (SECRET,))
    assert wire_error['error_message'] == '[diagnostic redacted]', wire_error
    assert 'debugToken' not in repr(wire_error) and 'synthetic-omp-key-9071' not in repr(wire_error)

    late_secret = diagnostic_omp_frame({'type': 'message_end', 'message': {
        'role': 'assistant', 'errorMessage': 'x' * 1800 + 'synthetic-omp-key-9071'}}, (SECRET,))
    assert late_secret['error_message'] == '[diagnostic redacted]', late_secret

    failed_message = diagnostic_omp_frame({'type': 'message_end', 'message': {
        'role': 'assistant', 'errorMessage': 'provider failed: synthetic-omp-key-9071',
        'content': [{'type': 'text', 'text': 'do not retain this assistant body'}]}}, (SECRET,))
    assert failed_message['error_message'] == '[diagnostic redacted]', failed_message
    assert 'do not retain this assistant body' not in repr(failed_message)
    assert 'synthetic-omp-key-9071' not in repr(failed_message)

    oversized = diagnostic_omp_frame({'type': 'message_end', 'message': {
        'role': 'assistant', 'errorMessage': 'x' * 3000}}, (SECRET,))
    assert len(oversized['error_message'].encode()) <= 1024, oversized
    assert diagnostic_omp_frame({'type': 'message_end', 'message': {
        'role': 'assistant', 'content': [{'type': 'text', 'text': 'ordinary output'}]}}, (SECRET,)) is None
    assert diagnostic_omp_frame({'type': 'ready'}, (SECRET,)) is None

    forwarded = []
    transport = SimpleNamespace(on_event=forwarded.append)
    runtime = SimpleNamespace(transport=transport)
    report = {}
    observe_omp_native_events(runtime, report, (SECRET,))
    for _ in range(15):
        transport.on_event({'type': 'prompt_result', 'status': 'error', 'sessionSettled': False})
    assert len(forwarded) == 15
    assert len(report['omp_native_events']['events']) == 12
    assert report['omp_native_events']['truncated'] is True

    route = provider_request_diagnostic('GET', '/v1/models', {'Authorization': 'Bearer ' + SECRET.decode()})
    assert route == {'method': 'GET', 'route': 'openai_models_v1', 'query_present': False,
                     'authorization_present': True}, route
    hidden_query = provider_request_diagnostic('GET', '/v1/models?key=' + SECRET.decode(),
                                               {'Authorization': 'Bearer ' + SECRET.decode()})
    assert hidden_query == {'method': 'GET', 'route': 'openai_models_v1', 'query_present': True,
                            'authorization_present': True}, hidden_query
    unknown = provider_request_diagnostic('GET', '/unexpected/' + SECRET.decode(),
                                          {'X-Test': SECRET.decode()})
    assert unknown == {'method': 'GET', 'route': 'other', 'query_present': False,
                       'authorization_present': False}, unknown
    assert SECRET.decode() not in repr((route, hidden_query, unknown))
    absolute = provider_request_diagnostic('GET', 'https://provider.invalid/v1/models?key=' + SECRET.decode(), {})
    assert absolute == {'method': 'GET', 'route': 'other', 'query_present': True,
                        'authorization_present': False}, absolute
    assert SECRET.decode() not in repr(absolute)
    malformed = provider_request_diagnostic('GET', 'https://[malformed/v1/models', {})
    assert malformed == {'method': 'GET', 'route': 'other', 'query_present': False,
                         'authorization_present': False}, malformed

    expected_url = 'https://provider.invalid:443/v1'
    state = diagnostic_omp_model_state({'api': 'openai-completions', 'baseUrl': expected_url,
        'provider': 'openai', 'id': 'fixture-model'}, expected_url, 'openai', 'fixture-model')
    assert state == {'api': 'openai-completions', 'base_url_matches': True,
                     'provider_matches': True, 'model_matches': True}, state
    mismatched = diagnostic_omp_model_state({'api': SECRET.decode(), 'baseUrl': SECRET.decode(),
        'provider': SECRET.decode(), 'id': SECRET.decode()}, expected_url, 'openai', 'fixture-model')
    assert mismatched == {'api': 'other', 'base_url_matches': False,
                          'provider_matches': False, 'model_matches': False}, mismatched
    assert SECRET.decode() not in repr((state, mismatched))

    module = SimpleNamespace(NetworkDenied=NetworkDenied)
    denials = NetworkDenialObserver(module)
    assert denials.original_type is NetworkDenied
    denials.install()
    try:
        try:
            raise module.NetworkDenied('network_destination_not_granted')
        except NetworkDenied as error:
            assert isinstance(error, NetworkDenied)
        for _ in range(16):
            try:
                raise module.NetworkDenied('network_method_invalid')
            except NetworkDenied:
                pass
        try:
            raise module.NetworkDenied(SECRET.decode())
        except NetworkDenied:
            pass
        summary = denials.snapshot()
        assert summary == {'codes': ['network_destination_not_granted'] + ['network_method_invalid'] * 15,
                           'total': 18, 'truncated': True}, summary
        assert SECRET.decode() not in repr(summary)
    finally:
        denials.restore()
    assert module.NetworkDenied is NetworkDenied
    print('OMP invocation diagnostic self-check passed')


if __name__ == '__main__':
    main()
