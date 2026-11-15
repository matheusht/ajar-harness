#!/usr/bin/env python3
"""Failure-first request-header checks and owned TLS proxy E2E for NetworkGate."""
from __future__ import annotations

from contextlib import nullcontext
import argparse
import hashlib
import http.client
import http.server
import io
import json
import os
from pathlib import Path
import re
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))


def request_bytes(headers):
    return b'POST /v1/chat/completions HTTP/1.1\r\nHost: 127.0.0.1\r\n' + headers + b'\r\n'


def connect_tls_peer(gate_port, upstream_port, trust):
    authority = f'127.0.0.1:{upstream_port}'
    peer = socket.create_connection(('127.0.0.1', gate_port), timeout=5)
    peer.sendall(f'CONNECT {authority} HTTP/1.1\r\nHost: {authority}\r\n\r\n'.encode())
    response = bytearray()
    while not response.endswith(b'\r\n\r\n'):
        chunk = peer.recv(1)
        if not chunk:
            peer.close()
            raise RuntimeError('owned TLS CONNECT closed before response')
        response.extend(chunk)
    if not response.startswith(b'HTTP/1.1 200'):
        peer.close()
        raise RuntimeError('owned TLS CONNECT failed')
    return trust.wrap_socket(peer, server_hostname='127.0.0.1')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    import engagement_network as network
    original_denied = network.NetworkDenied
    denial_codes = []

    class ObservedNetworkDenied(original_denied):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            candidate = args[0] if args else None
            code = candidate if isinstance(candidate, str) and re.fullmatch(r'[a-z_]{1,100}', candidate) else 'unclassified'
            if len(denial_codes) < 32:
                denial_codes.append(code)

    network.NetworkDenied = ObservedNetworkDenied
    result = {'kind': 'network-header-denials-e2e-v1', 'classification': 'actual_local_owned_tls_proxy',
              'checks': [], 'failures': [], 'http_denials': []}

    def check(name, condition, detail=None):
        row = {'name': name, 'passed': bool(condition)}
        if detail is not None:
            row['detail'] = detail
        result['checks'].append(row)
        if not condition:
            result['failures'].append(name)

    def parser_case(name, headers, expected):
        before = len(denial_codes)
        try:
            network._request(io.BytesIO(request_bytes(headers)))
        except original_denied as error:
            caught = isinstance(error, original_denied)
        except Exception:
            caught = False
        else:
            caught = False
        observed = denial_codes[before] if len(denial_codes) > before else 'no_network_denied'
        check(name, caught and observed == expected, {'expected': expected, 'observed': observed})

    def forward_case(name, headers, expected):
        before = len(denial_codes)
        try:
            forwarded = list(network._forward_headers(headers, request=True))
        except original_denied as error:
            caught = isinstance(error, original_denied)
            forwarded = None
        except Exception:
            caught, forwarded = False, None
        else:
            caught = False
        observed = denial_codes[before] if len(denial_codes) > before else 'no_network_denied'
        check(name, caught and observed == expected, {'expected': expected, 'observed': observed})
        return forwarded

    try:
        parser_case('missing CRLF is classified as an invalid header line', b'X-Test: value\n',
                    'network_header_line_invalid')
        parser_case('oversized header line is classified as an invalid header line',
                    b'X-Large: ' + b'a' * 8192 + b'\r\n', 'network_header_line_invalid')
        parser_case('aggregate header limit has its own fixed code',
                    b'X-A: ' + b'a' * 6000 + b'\r\n' + b'X-B: ' + b'b' * 6000 + b'\r\n'
                    + b'X-C: ' + b'c' * 6000 + b'\r\n', 'network_headers_too_large')
        parser_case('invalid header name has its own fixed code', b'X@Bad: value\r\n',
                    'network_header_name_invalid')
        rfc_token_names = [f"X{ord(char):02X}{char}" for char in "!#$%&'*+-.^_`|~" +
            "0123456789" + "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"]
        try:
            parsed_names = network._request(io.BytesIO(request_bytes(
                ''.join(f'{name}: value\r\n' for name in rfc_token_names).encode())))[2]
        except original_denied:
            parsed_names = {}
        except Exception:
            parsed_names = {}
        check('request parser accepts every RFC token character in header names',
              set(parsed_names) == {'host', *[name.lower() for name in rfc_token_names]},
              {'expected_count': len(rfc_token_names) + 1, 'observed_count': len(parsed_names)})
        parser_case('case-insensitive duplicate header has its own fixed code',
                    b'X-Test: one\r\nx-test: two\r\n', 'network_header_duplicate')
        parser_case('Expect remains rejected with a specific code', b'Expect: 100-continue\r\n',
                    'network_header_expect_unavailable')
        parser_case('Proxy-Authorization remains rejected with a specific code',
                    b'Proxy-Authorization: forbidden\r\n',
                    'network_header_proxy_authorization_unavailable')
        parser_case('control characters in values remain rejected with a specific code',
                    b'X-Test: value\x01blocked\r\n', 'network_header_value_invalid')
        forward_case('forwarding aggregate header limit has its own fixed code',
            [('X-A', 'a' * 6000), ('X-B', 'b' * 6000), ('X-C', 'c' * 6000)],
            'network_headers_too_large')
        forward_case('forwarding individual header limit has its own fixed code',
            [('X-Large', 'a' * 8192)], 'network_header_line_invalid')
        forward_case('forwarding invalid token name has its own fixed code',
            [('X@Bad', 'value')], 'network_header_name_invalid')
        forward_case('forwarding control value has its own fixed code',
            [('X-Test', 'value\x01blocked')], 'network_header_value_invalid')
        valid_underscore = list(network._forward_headers([('X_Test', 'legal-token-name')], request=True))
        check('forwarding keeps legal underscore token name behavior',
              valid_underscore == [('X_Test', 'legal-token-name')])

        with tempfile.TemporaryDirectory(prefix='network-header-gate-e2e-') as directory:
            root = Path(directory)
            certificate, key = root / 'certificate.pem', root / 'private.pem'
            subprocess.run([shutil.which('openssl') or '/usr/bin/openssl', 'req', '-x509', '-newkey', 'rsa:2048',
                '-nodes', '-keyout', str(key), '-out', str(certificate), '-days', '1', '-subj', '/CN=127.0.0.1',
                '-addext', 'subjectAltName=IP:127.0.0.1'], stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, check=True, timeout=15)
            key.chmod(0o600)
            hits = []
            session_ids = []

            class Receiver(http.server.BaseHTTPRequestHandler):
                def do_GET(self):
                    hits.append(('GET', self.path, b''))
                    self.send_response(200); self.send_header('Content-Length', '6'); self.end_headers()
                    self.wfile.write(b'GET_OK')

                def do_POST(self):
                    body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
                    session_ids.append(self.headers.get('session_id'))
                    hits.append(('POST', self.path, body))
                    self.send_response(200); self.send_header('Content-Length', '7'); self.end_headers()
                    self.wfile.write(b'POST_OK')

                def log_message(self, *_):
                    pass

            upstream = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Receiver)
            server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            server_context.load_cert_chain(certificate, key)
            upstream.socket = server_context.wrap_socket(upstream.socket, server_side=True)
            thread = threading.Thread(target=upstream.serve_forever, daemon=True)
            thread.start()
            trust = ssl.create_default_context(cafile=str(certificate))
            route = {'protocol': 'https', 'host': '127.0.0.1', 'port': upstream.server_port,
                     'address_policy': {'public_only': False, 'cidrs': ['127.0.0.1/32']}}
            gate = network.NetworkGate([route], lambda: True, dispatch_guard=nullcontext,
                                       upstream_context=trust)
            gate_port = gate.serve_tcp(certificate=certificate, private_key=key)

            def client():
                connection = http.client.HTTPSConnection('127.0.0.1', gate_port, context=trust, timeout=5)
                connection.set_tunnel('127.0.0.1', upstream.server_port,
                                      headers={'Host': f'127.0.0.1:{upstream.server_port}'})
                return connection

            try:
                connection = client(); connection.request('GET', '/get'); response = connection.getresponse()
                get_ok = response.status == 200 and response.read() == b'GET_OK'; connection.close()
                check('owned TLS GET crosses the actual Python proxy', get_ok and hits == [('GET', '/get', b'')])
                connection = client(); connection.request('POST', '/post', body=b'owned-body',
                    headers={'Content-Type': 'application/octet-stream', 'session_id': 'synthetic-safe-value'}); response = connection.getresponse()
                post_status, post_body = response.status, response.read(); connection.close()
                post_ok = (post_status == 200 and post_body == b'POST_OK' and session_ids[-1] == 'synthetic-safe-value')
                check('owned TLS POST crosses the actual Python proxy', post_ok
                      and hits[-1] == ('POST', '/post', b'owned-body'),
                      {'status': post_status, 'session_id_received': bool(session_ids and session_ids[-1] == 'synthetic-safe-value')})

                authority = f'127.0.0.1:{upstream.server_port}'
                peer = connect_tls_peer(gate_port, upstream.server_port, trust)
                check('owned TLS CONNECT is established for malformed-header replay', True)
                before_codes, before_hits = len(denial_codes), list(hits)
                peer.sendall((f'POST /blocked HTTP/1.1\r\nHost: {authority}\r\n'
                              'X-Test: one\r\nx-test: two\r\n\r\n').encode())
                denied = http.client.HTTPResponse(peer); denied.begin(); denied.read(); peer.close()
                code = denial_codes[before_codes] if len(denial_codes) > before_codes else 'no_network_denied'
                result['http_denials'].append({'method': 'POST', 'route': 'other', 'status': denied.status,
                                               'code': code, 'upstream_unchanged': hits == before_hits})
                check('duplicate-header TLS request remains an HTTP 403 without upstream dispatch',
                      denied.status == 403 and code == 'network_header_duplicate' and hits == before_hits,
                      {'expected': 'network_header_duplicate', 'observed': code})

                for label, invalid_name in [('space', 'X Bad'), ('at sign', 'X@Bad'),
                        ('parenthesis', 'X(Bad'), ('control', 'X\x01Bad')]:
                    peer = connect_tls_peer(gate_port, upstream.server_port, trust)
                    before_codes, before_hits = len(denial_codes), list(hits)
                    peer.sendall((f'POST /blocked HTTP/1.1\r\nHost: {authority}\r\n'
                        + f'{invalid_name}: value\r\n\r\n').encode())
                    denied = http.client.HTTPResponse(peer); denied.begin(); denied.read(); peer.close()
                    code = denial_codes[before_codes] if len(denial_codes) > before_codes else 'no_network_denied'
                    result['http_denials'].append({'method': 'POST', 'route': 'other', 'status': denied.status,
                        'code': code, 'upstream_unchanged': hits == before_hits, 'case': label})
                    check(f'{label} in a header name remains an HTTP 403 without upstream dispatch',
                        denied.status == 403 and code == 'network_header_name_invalid' and hits == before_hits,
                        {'expected': 'network_header_name_invalid', 'observed': code})
            finally:
                gate.close(); upstream.shutdown(); upstream.server_close(); thread.join()
        result['status'] = 'passed' if not result['failures'] else 'failed'
    except Exception as error:
        result['status'] = 'failed'
        result['error'] = type(error).__name__
    finally:
        network.NetworkDenied = original_denied
    result['source_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'checks': len(result['checks']),
                      'output': str(args.output)}))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
