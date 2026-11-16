#!/usr/bin/env python3
"""OMP Responses tool-call correlation through the native host-tool boundary."""
import argparse
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
from native_runtime_omp import Runtime
from native_runtime_transport import HostOperation


def run(first='call-public-lead-1|fc_public-lead-1'):
    calls, replies, checks = [], [], []
    class Transport:
        io_lock = threading.RLock()
        def send(self, frame): replies.append(frame)
    peer = Runtime.__new__(Runtime)
    peer.transport = Transport()
    peer.session_id, peer.invocation_id = 'owned-session', 'owned-turn'
    peer.calls, peer.events, peer.active = {}, [], True
    peer.accepting_tools, peer.tool_replies, peer.tool_requests = True, [], {}
    peer.host_tools = {'engagement_status': {}}
    peer._admission = nullcontext
    def host_call(name, arguments):
        calls.append((name, arguments))
        return HostOperation(lambda: {'content': [{'type': 'text', 'text': 'owned result'}]}, lambda: None)
    peer.host_call = host_call
    def send(request_id, call_id, arguments):
        peer._event({'type': 'host_tool_call', 'id': request_id, 'toolCallId': call_id,
                     'toolName': 'engagement_status', 'arguments': arguments})
        pending = peer.tool_requests[request_id]
        if not pending.ready.wait(5): raise ValueError('owned_tool_wait_timeout')
        peer._flush_tool_replies()
    def record(name, function):
        try:
            function(); checks.append({'name': name, 'passed': True})
        except Exception as error:
            checks.append({'name': name, 'passed': False, 'error': getattr(error, 'code', type(error).__name__)})
    def composite():
        send('request-1', first, {'n': 1})
        assert calls == [('engagement_status', {'n': 1})]
        assert replies[-1]['id'] == 'request-1' and replies[-1]['type'] == 'host_tool_result'
    record('composite call reaches tool and correlates reply', composite)
    def duplicate():
        send('request-2', first, {'n': 1})
        assert len(calls) == 1 and replies[-1]['id'] == 'request-2'
    record('same composite and arguments dispatch once', duplicate)
    def changed():
        try: send('request-3', first, {'n': 2})
        except Exception as error:
            assert getattr(error, 'code', None) == 'native_tool_call_changed'; return
        raise AssertionError('changed arguments accepted')
    record('same composite with changed arguments refused', changed)
    def distinct():
        send('request-4', 'call-public-lead-1|fc_public-lead-2', {'n': 1})
        assert len(calls) == 2 and replies[-1]['id'] == 'request-4'
    record('distinct second component remains distinct', distinct)
    def maximum():
        send('request-max', 'x' * 160 + '|' + 'y' * 160, {'n': 3})
        assert len(calls) == 3 and replies[-1]['id'] == 'request-max'
    record('maximum valid composite identifier accepted', maximum)
    def invalid():
        for value in ('', '|fc', 'call|', 'call|one|two', 'call|a/b', 'call|a\\b', 'call|a\n', 'x' * 161, 'x' * 161 + '|fc', 'call|' + 'x' * 161):
            try: send('invalid-request', value, {})
            except Exception as error:
                assert getattr(error, 'code', None) == 'native_identifier_invalid'; continue
            raise AssertionError('invalid identifier accepted')
    record('empty multi-pipe control slash backslash and oversized identifiers refused', invalid)
    return checks


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--parser-output', type=Path)
    args = parser.parse_args()
    first = 'call-public-lead-1|fc_public-lead-1'
    if args.parser_output:
        parsed = json.loads(args.parser_output.read_text())
        if parsed.get('stopReason') != 'toolUse' or parsed.get('toolNames') != ['bash'] or len(parsed.get('toolIds', [])) != 1:
            raise ValueError('native_parser_receipt_invalid')
        first = parsed['toolIds'][0]
    checks = run(first)
    result = {'kind': 'omp-responses-tool-id-e2e-v1', 'classification': 'actual_native_adapter_with_owned_host_operation',
              'checks': checks, 'status': 'passed' if all(row['passed'] for row in checks) else 'failed',
              'source_sha256': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in (Path(__file__), ROOT / 'tools/native_runtime_omp.py', ROOT / 'tools/native_runtime_transport.py')}}
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'checks': checks}))
    return 0 if result['status'] == 'passed' else 1

if __name__ == '__main__': raise SystemExit(main())
