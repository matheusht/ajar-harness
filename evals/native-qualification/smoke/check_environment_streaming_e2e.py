#!/usr/bin/env python3
"""Harmless local HTTP transfers through the actual bounded stdio proxy."""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import hashlib
import http.client
import http.server
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import tracemalloc

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'tools'))
CHUNK = b'controlled-package-bytes-' * 682 + b'end!'
CHUNK = CHUNK.ljust(16384, b'.')
COUNT = 384
SIZE = len(CHUNK) * COUNT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = {'kind': 'environment-streaming-e2e-v2',
              'classification': 'actual_local_http_and_stdio_controls', 'checks': [],
              'unverified': ['Docker containment', 'SSH transport', 'external acquisition', 'provider behavior']}

    def check(name, condition):
        result['checks'].append({'name': name, 'passed': bool(condition)})
        assert condition, name

    try:
        from engagement_network import NetworkGate, NetworkDenied
        from engagement_network_bridge import ProxyBridge
        active = [True]
        first_received = threading.Event()
        release_revoked = threading.Event()
        server_streamed = threading.Event()
        uploaded = []
        credentials = []

        class Receiver(http.server.BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def do_GET(self):
                try:
                    if self.path == '/package':
                        self.send_response(200)
                        self.send_header('Content-Length', str(SIZE))
                        self.send_header('Content-Type', 'application/x-controlled-package')
                        self.end_headers()
                        self.wfile.write(CHUNK); self.wfile.flush()
                        if not first_received.wait(2):
                            return
                        server_streamed.set()
                        for _ in range(COUNT - 1):
                            self.wfile.write(CHUNK)
                    elif self.path == '/declared-limit':
                        self.send_response(200); self.send_header('Content-Length', str(SIZE + 1)); self.end_headers()
                    elif self.path in ('/chunked-limit', '/chunked', '/revoke'):
                        self.send_response(200); self.send_header('Transfer-Encoding', 'chunked'); self.end_headers()
                        count = COUNT + 1 if self.path == '/chunked-limit' else 2
                        for index in range(count):
                            self.wfile.write(f'{len(CHUNK):x}\r\n'.encode() + CHUNK + b'\r\n'); self.wfile.flush()
                            if self.path == '/revoke' and index == 0:
                                release_revoked.wait(3)
                        self.wfile.write(b'0\r\n\r\n')
                    elif self.path == '/short':
                        self.send_response(200); self.send_header('Content-Length', '100'); self.end_headers()
                        self.wfile.write(b'short'); self.close_connection = True
                    elif self.path == '/session':
                        self.send_response(302)
                        self.send_header('Location', '/session-next')
                        self.send_header('Set-Cookie', 'fixture_one=local; Path=/')
                        self.send_header('Set-Cookie', 'fixture_two=local; Path=/')
                        self.send_header('Content-Type', 'text/plain')
                        self.send_header('Connection', 'close, X-Remove')
                        self.send_header('X-Remove', 'must-not-forward')
                        self.send_header('Content-Length', '0'); self.end_headers()
                    elif self.path == '/session-next':
                        self.send_response(200 if self.headers.get('Cookie') == 'fixture_one=local; fixture_two=local' else 401)
                        self.send_header('Content-Length', '0'); self.end_headers()
                    elif self.path == '/cross-origin':
                        self.send_response(302); self.send_header('Location', f'http://127.0.0.1:{second.server_port}/credentials')
                        self.send_header('Content-Length', '0'); self.end_headers()
                    elif self.path == '/credentials':
                        credentials.append((self.headers.get('Authorization'), self.headers.get('Cookie')))
                        self.send_response(200); self.send_header('Content-Length', '0'); self.end_headers()
                    else:
                        self.send_error(404)
                except OSError:
                    pass

            def do_POST(self):
                digest = hashlib.sha256(); total = 0
                try:
                    if self.headers.get('Transfer-Encoding') == 'chunked':
                        while True:
                            length = int(self.rfile.readline(), 16)
                            if length == 0:
                                self.rfile.readline(); break
                            data = self.rfile.read(length); self.rfile.read(2)
                            total += len(data); digest.update(data)
                    else:
                        remaining = int(self.headers['Content-Length'])
                        while remaining:
                            data = self.rfile.read(min(16384, remaining))
                            if not data: break
                            digest.update(data); total += len(data); remaining -= len(data)
                    uploaded.append((total, digest.hexdigest()))
                    self.send_response(200); self.send_header('Content-Length', '0'); self.end_headers()
                except (OSError, ValueError):
                    pass

            def log_message(self, *_):
                pass

        servers = [http.server.ThreadingHTTPServer(('127.0.0.1', 0), Receiver) for _ in range(2)]
        first, second = servers
        for server in servers:
            threading.Thread(target=server.serve_forever, daemon=True).start()
        routes = [{'protocol': 'http', 'host': '127.0.0.1', 'port': server.server_port,
                   'address_policy': {'public_only': False, 'cidrs': ['127.0.0.1/32']}} for server in servers]
        with tempfile.TemporaryDirectory(prefix='streaming-e2e-') as name:
            gate = NetworkGate(routes, lambda: active[0], maximum_bytes=SIZE, dispatch_guard=nullcontext)
            gate.serve(Path(name) / 'gate.sock')
            def launch(command):
                return subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, start_new_session=True,
                                        env={k: os.environ[k] for k in ('PATH', 'LANG') if k in os.environ})
            bridge = ProxyBridge(launch, [sys.executable, str(REPO / 'tools/engagement_network_bridge.py'), 'relay'],
                                 gate, lambda: active[0], dispatch_guard=nullcontext)
            def client():
                return http.client.HTTPConnection('127.0.0.1', bridge.port, timeout=5)
            def url(path):
                return f'http://127.0.0.1:{first.server_port}' + path
            expected = hashlib.sha256()
            for _ in range(COUNT): expected.update(CHUNK)
            try:
                tracemalloc.start()
                connection = client(); connection.request('GET', url('/package')); response = connection.getresponse()
                data = response.read(len(CHUNK)); first_received.set()
                digest = hashlib.sha256(data); total = len(data)
                while data:
                    data = response.read(16384); digest.update(data); total += len(data)
                peak = tracemalloc.get_traced_memory()[1]; tracemalloc.stop(); connection.close()
                check('package streams before upstream completion with exact bytes', server_streamed.is_set() and total == SIZE and digest.hexdigest() == expected.hexdigest())
                check('host transfer memory stays below body size', peak < SIZE)
                result['package_bytes'] = SIZE; result['host_tracemalloc_peak_bytes'] = peak
                check('content type survives streaming', response.getheader('Content-Type') == 'application/x-controlled-package')

                for path, incomplete in [('/declared-limit', False), ('/chunked-limit', True), ('/short', True)]:
                    connection = client(); connection.request('GET', url(path)); response = connection.getresponse()
                    failed = False
                    try:
                        if path == '/short':
                            response.read()
                        else:
                            while response.read(16384): pass
                    except (http.client.IncompleteRead, OSError): failed = True
                    connection.close()
                    check(path[1:] + ' refuses clean oversized or incomplete success', failed if incomplete else response.status == 403)

                connection = client(); connection.request('GET', url('/chunked')); response = connection.getresponse()
                check('ordinary chunked response completes exactly', response.read() == CHUNK * 2); connection.close()
                connection = client(); connection.request('GET', url('/session')); response = connection.getresponse(); response.read()
                cookies = [value for key, value in response.getheaders() if key.lower() == 'set-cookie']
                check('redirect and duplicate session headers survive without hop headers', response.status == 302 and response.getheader('Location') == '/session-next' and len(cookies) == 2 and response.getheader('X-Remove') is None)
                connection.close(); connection = client()
                connection.request('GET', url('/session-next'), headers={'Cookie': '; '.join(value.split(';')[0] for value in cookies)})
                response = connection.getresponse(); response.read()
                check('client follows session redirect with transient cookies', response.status == 200); connection.close()
                gate.fetch(url('/cross-origin'), headers={'Authorization': 'fixture-transient', 'Cookie': 'fixture=transient'})
                check('cross-origin direct fetch strips credentials', credentials == [(None, None)])

                for chunked in (False, True):
                    connection = client()
                    connection.request('POST', url('/upload'), body=iter([CHUNK] * COUNT),
                                       headers={} if chunked else {'Content-Length': str(SIZE)}, encode_chunked=chunked)
                    response = connection.getresponse(); response.read(); connection.close()
                    check(('chunked' if chunked else 'declared') + ' upload streams exact bytes', response.status == 200 and uploaded[-1] == (SIZE, expected.hexdigest()))

                connection = client()
                connection.request('POST', url('/upload'), headers={'Content-Length': str(SIZE + 1)})
                response = connection.getresponse(); response.read(); connection.close()
                check('declared upload cap rejects before forwarding', response.status == 403 and len(uploaded) == 2)
                connection = client(); rejected = False
                try:
                    connection.request('POST', url('/upload'), body=iter([CHUNK] * (COUNT + 1)), encode_chunked=True)
                    response = connection.getresponse(); response.read(); rejected = response.status == 403
                except (OSError, http.client.HTTPException): rejected = True
                connection.close()
                check('chunked upload cap rejects excess bytes', rejected and all(total <= SIZE for total, _ in uploaded))

                connection = client(); connection.request('GET', url('/revoke')); response = connection.getresponse()
                check('revocation scenario receives initial bytes', response.read(len(CHUNK)) == CHUNK)
                active[0] = False; release_revoked.set(); rejected = False
                try: response.read()
                except (OSError, http.client.HTTPException): rejected = True
                connection.close()
                check('midstream revocation prevents clean completion', rejected)
            finally:
                first_received.set(); release_revoked.set()
                if tracemalloc.is_tracing(): tracemalloc.stop()
                bridge.close(); gate.close()
                for server in servers: server.shutdown(); server.server_close()
        result['status'] = 'passed'
    except Exception as error:
        result['status'] = 'failed'; result['error'] = type(error).__name__ + ': ' + str(error)
    result['source_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'checks': len(result['checks']), 'output': str(args.output)}))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
