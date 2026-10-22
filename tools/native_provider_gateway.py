"""Host-only key injection behind the native run's metered CONNECT transport.

No request/response logging. Only the fixed OpenCode Go model endpoint is served.
TLS private material and the real provider key never enter the run directory.
"""
import base64
import hmac
import http.client
import json
import socket
import socketserver
import ssl
import threading


PATH = '/inference/go/openai/v1/chat/completions'
MODEL = 'deepseek-v4.1-flash'


def validate_request(method, path, body):
    def unique(rows):
        value = {}
        for key, item in rows:
            if key in value:
                raise ValueError('duplicate_request_field')
            value[key] = item
        return value
    if method != 'POST' or path != PATH or not 0 < len(body) <= 2 * 1024 * 1024:
        raise ValueError('provider_request_not_allowed')
    document = json.loads(body, object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError('invalid_number')))
    if (not isinstance(document, dict) or document.get('model') != MODEL or
            not isinstance(document.get('messages'), list) or
            type(document.get('stream', False)) is not bool):
        raise ValueError('provider_request_not_allowed')


def _headers(stream):
    total, rows = 0, {}
    while True:
        line = stream.readline(8193)
        total += len(line)
        if len(line) > 8192 or total > 16384 or not line.endswith(b'\r\n'):
            raise ValueError('invalid_http_headers')
        if line == b'\r\n':
            return rows
        name, colon, value = line[:-2].partition(b':')
        name = name.decode('ascii').lower()
        value = value.decode('ascii').strip()
        if (not colon or not name or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in name)
                or name in rows or any(ord(c) < 32 or ord(c) == 127 for c in value)):
            raise ValueError('invalid_http_headers')
        rows[name] = value


class Gateway:
    def __init__(self, key, certificate, private_key, capability, active, dispatch_guard):
        if not 8 <= len(key) <= 1024 or any(ord(c) <= 32 or ord(c) >= 127 for c in key):
            raise ValueError('provider_key_invalid')
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.set_alpn_protocols(['http/1.1'])
        context.load_cert_chain(str(certificate), str(private_key))
        authorization = 'Basic ' + base64.b64encode(('host:' + capability).encode()).decode()
        self.key = key
        self.sockets = set()
        self.lock = threading.Lock()
        self.closed = threading.Event()
        gateway = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                connection = self.request
                upstream = None
                with gateway.lock:
                    gateway.sockets.add(connection)
                try:
                    connection.settimeout(15)
                    # Unbuffered: TLS bytes must not disappear into an HTTP reader.
                    stream = connection.makefile('rb', buffering=0)
                    if stream.readline(8193) != b'CONNECT opencode.ai:443 HTTP/1.1\r\n':
                        return
                    headers = _headers(stream)
                    if (set(headers) != {'host', 'proxy-authorization'} or
                            headers['host'] != 'opencode.ai:443' or
                            not hmac.compare_digest(headers['proxy-authorization'], authorization) or
                            not active() or gateway.closed.is_set()):
                        return
                    stream.close()
                    connection.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
                    encrypted = context.wrap_socket(connection, server_side=True)
                    with gateway.lock:
                        gateway.sockets.discard(connection)
                        gateway.sockets.add(encrypted)
                    connection = encrypted
                    stream = connection.makefile('rb')
                    request = stream.readline(8193).decode('ascii').strip().split(' ')
                    if len(request) != 3 or request[2] != 'HTTP/1.1':
                        return
                    headers = _headers(stream)
                    length = headers.get('content-length', '')
                    if (not length.isdecimal() or not 0 < int(length) <= 2 * 1024 * 1024
                            or 'transfer-encoding' in headers or 'expect' in headers
                            or headers.get('host') not in ('opencode.ai', 'opencode.ai:443')
                            or headers.get('content-type', '').split(';')[0] != 'application/json'):
                        return
                    body = stream.read(int(length))
                    if len(body) != int(length):
                        return
                    validate_request(request[0], request[1], body)
                    upstream = http.client.HTTPSConnection('opencode.ai', 443, timeout=5,
                                                           context=ssl.create_default_context())
                    with dispatch_guard():
                        if not active() or gateway.closed.is_set():
                            return
                        upstream.connect()
                        with gateway.lock:
                            gateway.sockets.add(upstream.sock)
                        if not active() or gateway.closed.is_set():
                            return
                        upstream.request('POST', PATH, body=body,
                                         headers={'Authorization': 'Bearer ' + gateway.key,
                                                  'Content-Type': 'application/json',
                                                  'Accept': 'text/event-stream, application/json'})
                    upstream.sock.settimeout(45)
                    response = upstream.getresponse()
                    if not 200 <= response.status < 300:
                        connection.sendall(b'HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
                        return
                    content_type = ('text/event-stream' if response.getheader('Content-Type', '').startswith(
                        'text/event-stream') else 'application/json')
                    connection.sendall(('HTTP/1.1 200 OK\r\nContent-Type: ' + content_type +
                                        '\r\nConnection: close\r\n\r\n').encode())
                    pending = b''
                    secret = gateway.key.encode()
                    while active() and not gateway.closed.is_set():
                        chunk = response.read1(16384)
                        pending += chunk
                        # Hold a possible cross-chunk key prefix; never echo credentials.
                        pending = pending.replace(secret, b'[redacted]')
                        safe = len(pending) if not chunk else max(0, len(pending) - len(secret) + 1)
                        if safe:
                            connection.sendall(pending[:safe])
                            pending = pending[safe:]
                        if not chunk:
                            break
                except Exception:
                    # Errors contain neither upstream text nor credentials in logs.
                    return
                finally:
                    if upstream is not None:
                        with gateway.lock:
                            gateway.sockets.discard(upstream.sock)
                        upstream.close()
                    with gateway.lock:
                        gateway.sockets.discard(connection)
                    connection.close()

        class Server(socketserver.ThreadingTCPServer):
            daemon_threads = True
            allow_reuse_address = False
            def handle_error(self, request, client_address):
                pass

        self.server = Server(('127.0.0.1', 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.closed.set()
        with self.lock:
            for connection in self.sockets:
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                connection.close()
            self.sockets.clear()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.key = ''
