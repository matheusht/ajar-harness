#!/usr/bin/env python3
"""Owned IPC byte transfer under backpressure, cancellation and revoked authority."""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
from engagement_network_bridge import ProxyBridge


def scenario(root, *, revoke):
    payload = bytes(range(256)) * 800
    endpoint = root / ('revoke.sock' if revoke else 'drain.sock')
    listener = socket.socket(socket.AF_UNIX)
    listener.bind(str(endpoint)); listener.listen(1); listener.settimeout(5)
    identity = endpoint.lstat()
    active = [True]
    gate = SimpleNamespace(endpoint=endpoint, endpoint_identity=(identity.st_dev, identity.st_ino),
                           _active=lambda: active[0])
    accepted, release, done = threading.Event(), threading.Event(), threading.Event()
    received = bytearray()
    state = {}
    def receive():
        peer = None
        try:
            peer, _ = listener.accept()
            peer.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
            peer.settimeout(5)
            accepted.set()
            release.wait(5)
            while data := peer.recv(16384):
                received.extend(data)
        except OSError as error:
            state['receiver_error'] = type(error).__name__
        finally:
            if peer is not None: peer.close()
            done.set()
    receiver = threading.Thread(target=receive, daemon=True); receiver.start()
    relay = ROOT / 'tools/engagement_network_bridge.py'
    bridge = ProxyBridge(lambda command: subprocess.Popen(command, stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True),
        [sys.executable, '-I', '-S', str(relay), 'relay'], gate, lambda: active[0],
        dispatch_guard=nullcontext)
    original_open = bridge.channel.opener
    def bounded_socket():
        peer = original_open()
        peer.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
        return peer
    bridge.channel.opener = bounded_socket
    client = socket.create_connection(('127.0.0.1', bridge.port), timeout=5)
    sender_done = threading.Event()
    def send():
        try:
            client.sendall(payload)
            client.shutdown(socket.SHUT_WR)
        except OSError as error:
            state['sender_error'] = type(error).__name__
        finally: sender_done.set()
    sender = threading.Thread(target=send, daemon=True); sender.start()
    cleanup = None
    try:
        if not accepted.wait(5): raise RuntimeError('owned_gate_not_reached')
        # The production socket timeout is one second. Hold the actual receiver
        # longer, with a small kernel send buffer, before draining or revoking.
        time.sleep(1.4)
        state['peer_retained_during_pause'] = bool(bridge.channel.peers)
        if revoke:
            started = time.monotonic(); active[0] = False
            deadline = started + 2
            while not bridge.closed.is_set() and time.monotonic() < deadline:
                time.sleep(.01)
            cleanup = bridge.close()
            state['revoked_in_seconds'] = round(time.monotonic() - started, 3)
            state['revoked'] = bridge.closed.is_set() and cleanup['host_process_exited']
        release.set()
        if not done.wait(5): raise RuntimeError('owned_receiver_not_settled')
        sender.join(timeout=2)
        state.update(expected_bytes=len(payload), received_bytes=len(received),
            exact_bytes=bytes(received) == payload,
            expected_sha256=hashlib.sha256(payload).hexdigest(),
            received_sha256=hashlib.sha256(received).hexdigest(), sender_settled=sender_done.is_set())
    finally:
        active[0] = False; release.set()
        if cleanup is None: cleanup = bridge.close()
        client.close(); listener.close(); receiver.join(timeout=2); sender.join(timeout=2)
        state['relay_stopped'] = cleanup['host_process_exited']
    return state


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = {'kind': 'proxy-backpressure-e2e-v1', 'classification': 'actual_owned_socket_and_stdio_transfer',
              'checks': [], 'not_covered': ['Docker isolation', 'TLS provider behavior', 'research efficacy']}
    try:
        with tempfile.TemporaryDirectory(prefix='oslit-proxy-backpressure-') as temporary:
            root = Path(temporary)
            result['drain'] = scenario(root, revoke=False)
            result['revocation'] = scenario(root, revoke=True)
        drain, revoked = result['drain'], result['revocation']
        result['checks'] = [
            {'name': 'paused consumer retains stream and all 200 KiB without truncation or duplication',
             'passed': drain['peer_retained_during_pause'] and drain['exact_bytes'] and drain['sender_settled']},
            {'name': 'revocation stops a backpressured stream promptly',
             'passed': revoked['peer_retained_during_pause'] and revoked['revoked']
                       and revoked['revoked_in_seconds'] < 2 and not revoked['exact_bytes']},
            {'name': 'owned relays and sender work settle',
             'passed': drain['relay_stopped'] and revoked['relay_stopped'] and revoked['sender_settled']}]
        result['status'] = 'passed' if all(row['passed'] for row in result['checks']) else 'failed'
    except Exception as error:
        result.update(status='failed', error=type(error).__name__)
    result['source_sha256'] = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (Path(__file__), ROOT / 'tools/engagement_network_bridge.py')}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'output': str(args.output), 'checks': result['checks']}))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__': raise SystemExit(main())
