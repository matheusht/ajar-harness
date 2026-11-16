#!/usr/bin/env python3
"""Actual large HTTPS upload through the relay/gate, with explicit revocation."""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import hashlib
import http.client
import http.server
import json
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
from engagement_network import NetworkGate
from engagement_network_bridge import ProxyBridge


def scenario(root, *, revoke):
    size = 652488
    prefix, suffix = b'{"fixture":"', b'"}\n'
    payload = prefix + b'x' * (size - len(prefix) - len(suffix)) + suffix
    certificate, key = root / 'certificate.pem', root / 'private.pem'
    context = ssl.create_default_context(cafile=str(certificate))
    class SmallSendContext(ssl.SSLContext):
        def wrap_socket(self, *args, **kwargs):
            peer = super().wrap_socket(*args, **kwargs)
            peer.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
            return peer
    upstream = SmallSendContext(ssl.PROTOCOL_TLS_CLIENT)
    upstream.load_verify_locations(cafile=str(certificate))
    active = [True]
    headers_received, release, body_done = threading.Event(), threading.Event(), threading.Event()
    state = {'expected_bytes': size, 'observations': []}
    class Receiver(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_POST(self):
            state['request_started'] = time.monotonic()
            headers_received.set()
            release.wait(5)
            try:
                raw = self.rfile.read(int(self.headers['Content-Length']))
                state.update(body_read_ended=time.monotonic(), received_bytes=len(raw),
                    exact_bytes=raw == payload, received_sha256=hashlib.sha256(raw).hexdigest())
                self.send_response(200); self.send_header('Content-Length', '0'); self.end_headers()
            except OSError as error:
                state['receiver_error'] = type(error).__name__
            finally: body_done.set()
    class Server(http.server.ThreadingHTTPServer):
        def handle_error(self, *_): pass
    server = Server(('127.0.0.1', 0), Receiver)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(certificate, key)
    server.socket = tls.wrap_socket(server.socket, server_side=True)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True); server_thread.start()
    route = {'protocol': 'https', 'host': '127.0.0.1', 'port': server.server_port,
             'address_policy': {'public_only': False, 'cidrs': ['127.0.0.1/32']}}
    gate = NetworkGate([route], lambda: active[0], maximum_bytes=2 * 1024 * 1024,
        dispatch_guard=nullcontext, upstream_context=upstream,
        request_observer=lambda row: state['observations'].append(dict(row)))
    endpoint = root / ('revoked.sock' if revoke else 'complete.sock')
    gate.serve(endpoint, certificate=certificate, private_key=key)
    bridge = ProxyBridge(lambda command: subprocess.Popen(command, stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True),
        [sys.executable, '-I', '-S', str(ROOT / 'tools/engagement_network_bridge.py'), 'relay'],
        gate, lambda: active[0], dispatch_guard=nullcontext)
    client_done = threading.Event()
    def upload():
        peer = None
        try:
            peer = socket.create_connection(('127.0.0.1', bridge.port), timeout=10)
            authority = f'127.0.0.1:{server.server_port}'
            peer.sendall(f'CONNECT {authority} HTTP/1.1\r\nHost: {authority}\r\n\r\n'.encode())
            header = b''
            while not header.endswith(b'\r\n\r\n'):
                part = peer.recv(1)
                if not part: raise RuntimeError('connect_incomplete')
                header += part
            if not header.startswith(b'HTTP/1.1 200'): raise RuntimeError('connect_refused')
            peer = context.wrap_socket(peer, server_hostname='127.0.0.1')
            peer.sendall(f'POST /owned HTTP/1.1\r\nHost: {authority}\r\nContent-Type: application/json\r\nContent-Length: {size}\r\n\r\n'.encode())
            for offset in range(0, len(payload), 4096):
                peer.sendall(payload[offset:offset + 4096]); time.sleep(.002)
            response = http.client.HTTPResponse(peer); response.begin()
            state['client_status'] = response.status; response.read(); response.close()
        except (OSError, http.client.HTTPException, RuntimeError) as error:
            state['client_error'] = type(error).__name__
        finally:
            if peer is not None: peer.close()
            client_done.set()
    client_thread = threading.Thread(target=upload, daemon=True); client_thread.start()
    try:
        if not headers_received.wait(5): raise RuntimeError('provider_not_reached')
        if revoke:
            time.sleep(.15)
            state['authority_revoked_at'] = time.monotonic(); active[0] = False
            deadline = time.monotonic() + 2
            while not bridge.closed.is_set() and time.monotonic() < deadline: time.sleep(.01)
        else:
            time.sleep(1.4)
        release.set()
        if not body_done.wait(8) or not client_done.wait(8): raise RuntimeError('upload_not_settled')
        deadline = time.monotonic() + 2
        while not any(row['status'] != 'started' for row in state['observations']) and time.monotonic() < deadline:
            time.sleep(.01)
        state['expected_sha256'] = hashlib.sha256(payload).hexdigest()
    finally:
        active[0] = False; release.set(); state['cleanup'] = bridge.close()['host_process_exited']
        gate.close(); server.shutdown(); server.server_close()
        client_thread.join(timeout=2); server_thread.join(timeout=2)
    return state


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = {'kind': 'network-upload-e2e-v1', 'classification': 'actual_owned_tls_proxy_and_stdio',
              'checks': [], 'not_covered': ['Docker isolation', 'native model behavior', 'external provider']}
    try:
        with tempfile.TemporaryDirectory(prefix='oslit-upload-') as temporary:
            root = Path(temporary)
            subprocess.run([shutil.which('openssl') or '/usr/bin/openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                '-keyout', str(root / 'private.pem'), '-out', str(root / 'certificate.pem'), '-days', '1', '-subj', '/CN=localhost',
                '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1'], check=True, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=15)
            (root / 'private.pem').chmod(0o600)
            result['complete'] = scenario(root, revoke=False)
            result['revoked'] = scenario(root, revoke=True)
        complete, revoked = result['complete'], result['revoked']
        result['checks'] = [
            {'name': 'fragmented 652488-byte HTTPS upload survives consumer pause intact',
             'passed': complete.get('exact_bytes') is True and complete.get('client_status') == 200
                       and [row['status'] for row in complete['observations']] == ['started', 'completed']},
            {'name': 'authority revocation precedes partial EOF and marks request unknown',
             'passed': revoked.get('exact_bytes') is False
                       and revoked['request_started'] < revoked['authority_revoked_at'] <= revoked.get('body_read_ended', 0)
                       and [row['status'] for row in revoked['observations']] == ['started', 'unknown']},
            {'name': 'both owned relay processes stop', 'passed': complete['cleanup'] and revoked['cleanup']}]
        result['status'] = 'passed' if all(row['passed'] for row in result['checks']) else 'failed'
    except Exception as error: result.update(status='failed', error=type(error).__name__)
    result['source_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [Path(__file__), ROOT / 'tools/engagement_network.py', ROOT / 'tools/engagement_network_bridge.py']}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'checks': result['checks'], 'output': str(args.output)}))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__': raise SystemExit(main())
