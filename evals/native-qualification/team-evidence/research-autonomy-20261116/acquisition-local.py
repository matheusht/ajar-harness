#!/usr/bin/env python3
"""Owned local TLS acquisition transport; no native runtime or Docker lab."""
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

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'tools'))
from acquisition_network import LabRequestBinder
from engagement_network import NetworkGate


def main(output):
    observed, hits, checks = [], [], []
    def check(name, condition):
        checks.append({'name': name, 'passed': bool(condition)})
        if not condition:
            raise AssertionError(name)
    result = {'kind': 'owned-local-acquisition-e2e', 'classification': 'actual_local_tls_and_acquisition_binder',
              'native_runtime': False, 'docker_lab': False, 'checks': checks, 'status': 'failed'}
    gate = server = thread = None
    try:
        with tempfile.TemporaryDirectory(prefix='oslit-acquisition-') as temporary:
            root = Path(temporary).resolve(); cert = root / 'cert.pem'; key = root / 'key.pem'
            subprocess.run([shutil.which('openssl') or 'openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                '-keyout', str(key), '-out', str(cert), '-days', '1', '-subj', '/CN=localhost',
                '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1'],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
            key.chmod(0o600)
            class Handler(http.server.BaseHTTPRequestHandler):
                def do_GET(self):
                    hits.append(self.path)
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/octet-stream')
                    self.send_header('Content-Length', '30' if self.path == '/short' else '6')
                    self.end_headers(); self.wfile.write(b'abc123')
                def log_message(self, *_): pass
            server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            server_tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); server_tls.load_cert_chain(cert, key)
            server.socket = server_tls.wrap_socket(server.socket, server_side=True)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            port = server.server_port
            route = {'protocol': 'https', 'host': '127.0.0.1', 'port': port,
                     'address_policy': {'public_only': False, 'cidrs': ['127.0.0.1/32']}}
            scope = {'network': {'provider': [], 'target': [], 'acquisition': [route]},
                     'environments': [{'profile_id': 'lab', 'capabilities': ['acquisition']}]}
            binder = LabRequestBinder(scope, 'lab', lambda: None, observed.append)
            tls = ssl.create_default_context(cafile=str(cert))
            gate = NetworkGate([route], lambda: True, dispatch_guard=nullcontext,
                               request_binder=binder.bind, upstream_context=tls)
            endpoint = root / 'gate.sock'; gate.serve(endpoint, certificate=cert, private_key=key)
            def request(method, path, headers='', inner_host=None):
                peer = socket.socket(socket.AF_UNIX); peer.settimeout(5); peer.connect(str(endpoint))
                authority = '127.0.0.1:' + str(port)
                peer.sendall(('CONNECT ' + authority + ' HTTP/1.1\r\nHost: ' + authority + '\r\n\r\n').encode())
                data = b''
                while not data.endswith(b'\r\n\r\n'): data += peer.recv(1)
                assert data.startswith(b'HTTP/1.1 200')
                stream = tls.wrap_socket(peer, server_hostname='127.0.0.1')
                stream.sendall((method + ' ' + path + ' HTTP/1.1\r\nHost: ' + (inner_host or authority) + '\r\n' + headers + '\r\n').encode())
                response = http.client.HTTPResponse(stream); response.begin()
                try: body = response.read()
                except http.client.IncompleteRead as error: body = error.partial
                except OSError: body = b''
                status = response.status; response.close(); stream.close()
                return status, body
            def receipt_for(path):
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    row = next((item for item in observed if item.get('phase') == 'result'
                                and (item.get('display_url') or '').endswith(path)), None)
                    if row is not None:
                        return row
                    time.sleep(.02)
                return None
            status, body = request('GET', '/artifact')
            check('owned HTTPS GET returns original bytes', status == 200 and body == b'abc123')
            record = receipt_for('/artifact')
            check('complete receipt binds exact bytes', record is not None and record['body_complete']
                  and record['response_sha256'] == 'sha256:' + hashlib.sha256(body).hexdigest())
            prior = len(hits)
            status, _ = request('GET', '/credential', 'Authorization: Bearer harmless-test\r\n')
            check('credential header refused before origin', status == 403 and len(hits) == prior)
            status, _ = request('POST', '/mutation')
            check('mutation refused before origin', status == 403 and len(hits) == prior)
            status, _ = request('GET', '/outside', inner_host='ungranted.invalid')
            check('ungranted host refused before origin', status == 403 and len(hits) == prior)
            status, body = request('GET', '/short')
            short = receipt_for('/short')
            check('interrupted transfer is not complete', status == 200 and short is not None
                  and short.get('body_complete') is False and short.get('response_sha256') is None)
            result['status'] = 'passed'
    except Exception as error:
        result['error'] = type(error).__name__
        import traceback
        result['error_frames'] = [{'file': Path(frame.filename).name, 'line': frame.lineno, 'function': frame.name}
                                  for frame in traceback.extract_tb(error.__traceback__)[-5:]]
    finally:
        if gate: gate.close()
        if server: server.shutdown(); server.server_close()
        if thread: thread.join(timeout=3)
    result['source_sha256'] = {str(path.relative_to(ROOT)): 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()
                               for path in (Path(__file__), ROOT / 'tools/acquisition_network.py',
                                            ROOT / 'tools/engagement_network.py')}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, sort_keys=True, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'checks': checks}))
    return result['status'] != 'passed'


if __name__ == '__main__':
    raise SystemExit(main(Path(sys.argv[1])))
