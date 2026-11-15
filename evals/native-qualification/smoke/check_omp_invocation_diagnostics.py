#!/usr/bin/env python3
"""Self-check bounded OMP terminal-frame capture and secret redaction."""
import sys
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2] / 'tools')]

from check_linux_model_native_e2e import diagnostic_omp_frame, observe_omp_native_events

SECRET = b'synthetic-omp-key-9071'


def main():
    terminal = diagnostic_omp_frame({'type': 'prompt_result', 'status': 'error',
                                     'sessionSettled': False}, (SECRET,))
    assert terminal == {'event': 'prompt_result', 'status': 'error', 'session_settled': False}, terminal
    response_error = diagnostic_omp_frame({'type': 'prompt_result', 'status': 'error',
        'sessionSettled': True, 'errorMessage': 'request failed: synthetic-omp-key-9071'}, (SECRET,))
    assert response_error['error_message'] == '[diagnostic redacted]', response_error
    assert 'synthetic-omp-key-9071' not in repr(response_error)

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
    print('OMP invocation diagnostic self-check passed')


if __name__ == '__main__':
    main()
