#!/usr/bin/env python3
"""Actual loopback proxy/TLS controls for host-native clients, without a provider."""
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

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'tools'))


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = {'kind': 'environment-tcp-gate-e2e-v2',
              'classification': 'actual_local_loopback_tls_controls', 'checks': [],
              'unverified': ['native model client proxy behavior', 'provider behavior', 'macOS sandbox containment']}
    def check(name, condition):
        result['checks'].append({'name': name, 'passed': bool(condition)}); assert condition, name
    try:
        from engagement_network import NetworkGate, NetworkDenied
        with tempfile.TemporaryDirectory(prefix='tcp-gate-e2e-') as name:
            root = Path(name); cert = root / 'ca.pem'; key = root / 'private.pem'
            subprocess.run([shutil.which('openssl') or '/usr/bin/openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                            '-keyout', str(key), '-out', str(cert), '-days', '1', '-subj', '/CN=localhost',
                            '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=15)
            key.chmod(0o600); active = [True]; hits = []; waiting = threading.Event(); release = threading.Event()
            class Receiver(http.server.BaseHTTPRequestHandler):
                def do_GET(self):
                    hits.append(self.path)
                    self.send_response(200); self.send_header('Content-Length', '16'); self.end_headers()
                    try:
                        self.wfile.write(b'first123'); self.wfile.flush()
                        if self.path == '/wait': waiting.set(); release.wait(3)
                        self.wfile.write(b'last4567')
                    except OSError:
                        pass
                def log_message(self, *_): pass
            receiver = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Receiver)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.load_cert_chain(cert, key)
            receiver.socket = context.wrap_socket(receiver.socket, server_side=True)
            threading.Thread(target=receiver.serve_forever, daemon=True).start()
            trust = ssl.create_default_context(cafile=str(cert))
            route = {'protocol': 'https', 'host': '127.0.0.1', 'port': receiver.server_port,
                     'address_policy': {'public_only': False, 'cidrs': ['127.0.0.1/32']}}
            gate = NetworkGate([route], lambda: active[0], dispatch_guard=nullcontext, upstream_context=trust)
            try:
                port = gate.serve_tcp(certificate=cert, private_key=key)
                check('TCP proxy binds only ephemeral loopback', gate.server.server_address == ('127.0.0.1', port) and port > 0)
                def client():
                    connection = http.client.HTTPSConnection('127.0.0.1', port, context=trust, timeout=5)
                    connection.set_tunnel('127.0.0.1', receiver.server_port,
                                          headers={'Host': f'127.0.0.1:{receiver.server_port}'})
                    return connection
                connection = client(); connection.request('GET', '/ok'); response = connection.getresponse()
                check('ordinary HTTPS proxy client verifies both TLS legs', response.status == 200 and response.read() == b'first123last4567' and hits == ['/ok'])
                connection.close()
                try: gate.serve_tcp(certificate=cert, private_key=key)
                except NetworkDenied: denied = True
                else: denied = False
                check('one gate cannot acquire a second listener', denied)
                forbidden = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
                forbidden.request('GET', 'http://denied.invalid/no'); response = forbidden.getresponse(); response.read()
                check('TCP listener preserves route denial', response.status == 403 and hits == ['/ok']); forbidden.close()
                connection = client(); connection.request('GET', '/wait'); response = connection.getresponse()
                check('active TCP transfer reaches its first chunk', response.read(8) == b'first123' and waiting.wait(1))
                active[0] = False; release.set(); incomplete = False
                try: response.read()
                except (OSError, http.client.HTTPException): incomplete = True
                connection.close()
                check('revocation interrupts loopback TLS transfer', incomplete)
            finally:
                release.set(); gate.close(); receiver.shutdown(); receiver.server_close()
            try: peer = socket.create_connection(('127.0.0.1', port), timeout=.2); peer.close(); available = True
            except OSError: available = False
            check('cleanup closes TCP listener', not available and cert.exists() and key.exists())
        result['status'] = 'passed'
    except Exception as error:
        result['status'] = 'failed'; result['error'] = type(error).__name__ + ': ' + str(error)
    result['source_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'checks': len(result['checks']), 'output': str(args.output)}))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__': raise SystemExit(main())
