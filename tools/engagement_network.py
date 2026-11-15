"""Per-worker network admission. Provider routes never enter this lab gateway."""
from __future__ import annotations

import http.client
from contextlib import contextmanager
import copy
import ipaddress
import os
from pathlib import Path
import queue
import re
import socket
import socketserver
import ssl
import threading
from urllib.parse import urljoin, urlsplit


class NetworkDenied(RuntimeError):
    pass


def _request(stream):
    line = stream.readline(8193)
    method, target, version = line.decode('ascii').rstrip('\r\n').split(' ')
    if len(line) > 8192 or not line.endswith(b'\r\n') or version not in ('HTTP/1.0', 'HTTP/1.1'):
        raise NetworkDenied('network_request_invalid')
    headers, total = {}, 0
    while True:
        row = stream.readline(8193); total += len(row)
        if not row.endswith(b'\r\n') or len(row) > 8192:
            raise NetworkDenied('network_header_line_invalid')
        if total > 16384:
            raise NetworkDenied('network_headers_too_large')
        if row == b'\r\n':
            return method, target, headers
        key, value = row.decode('ascii').rstrip('\r\n').split(':', 1)
        key, value = key.lower(), value.strip()
        if not re.fullmatch('[a-z0-9-]+', key):
            raise NetworkDenied('network_header_name_invalid')
        if key in headers:
            raise NetworkDenied('network_header_duplicate')
        if key == 'proxy-authorization':
            raise NetworkDenied('network_header_proxy_authorization_unavailable')
        if key == 'expect':
            raise NetworkDenied('network_header_expect_unavailable')
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise NetworkDenied('network_header_value_invalid')
        headers[key] = value


_HOP_HEADERS = {'connection', 'proxy-connection', 'keep-alive', 'proxy-authenticate',
                'proxy-authorization', 'te', 'trailer', 'transfer-encoding', 'upgrade'}


def _forward_headers(headers, *, request=False):
    blocked = _HOP_HEADERS | {'content-length'} | ({'host'} if request else set())
    for key, value in headers:
        if key.lower() == 'connection':
            blocked |= {token.strip().lower() for token in value.split(',')}
    total = 0
    for key, value in headers:
        total += len(key) + len(value) + 4
        if total > 16384:
            raise NetworkDenied('network_headers_too_large')
        if len(key) + len(value) > 8192:
            raise NetworkDenied('network_header_line_invalid')
        if not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", key):
            raise NetworkDenied('network_header_name_invalid')
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise NetworkDenied('network_header_value_invalid')
        if key.lower() not in blocked:
            yield key, value


class NetworkGate:
    def __init__(self, routes, authorize, *, maximum_bytes=1024 * 1024, dispatch_guard=None,
                 upstream_context=None, request_binder=None, target_connectors=None):
        self.request_binder = request_binder
        self.routes = copy.deepcopy(routes)
        self.target_connectors = dict(target_connectors or {})
        for origin, connector in self.target_connectors.items():
            parsed = urlsplit(origin)
            if (parsed.scheme != 'http' or not parsed.hostname or not parsed.hostname.endswith('.invalid')
                    or origin != f'http://{parsed.hostname}:{parsed.port}' or (connector is not None and not callable(connector))
                    or not any(r['protocol'] == 'http' and r['host'] == parsed.hostname
                               and r['port'] == parsed.port for r in self.routes)):
                raise NetworkDenied('network_owned_connector_invalid')
        self.authorize = authorize
        self.dispatch_guard = dispatch_guard
        self.maximum_bytes = maximum_bytes
        self.upstream_context = upstream_context or ssl.create_default_context()
        if self.upstream_context.verify_mode != ssl.CERT_REQUIRED or not self.upstream_context.check_hostname:
            raise NetworkDenied('network_tls_verification_required')
        self.sockets = set()
        self.lock = threading.Lock()
        self.closed = threading.Event()
        self.resolvers = threading.BoundedSemaphore(4)
        self.server = None
        self.endpoint = None
        self.watcher = threading.Thread(target=self._watch, daemon=True)
        self.watcher.start()

    def _active(self):
        try:
            return not self.closed.is_set() and self.authorize() is True
        except Exception:
            return False

    def _watch(self):
        while not self.closed.wait(.05):
            if not self._active():
                self.closed.set()
                self._close_sockets()

    def _close_sockets(self):
        with self.lock:
            for peer in list(self.sockets):
                try:
                    peer.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                peer.close()

    def _destination(self, url):
        if self.dispatch_guard is None:
            raise NetworkDenied('network_dispatch_guard_required')
        if not self._active():
            raise NetworkDenied('network_lease_inactive')
        parsed = urlsplit(url)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname or
                parsed.username is not None or parsed.password is not None or parsed.fragment or
                any(ord(c) < 32 or ord(c) == 127 for c in url)):
            raise NetworkDenied('network_url_invalid')
        try:
            port = parsed.port or (443 if parsed.scheme == 'https' else 80)
        except ValueError as error:
            raise NetworkDenied('network_port_invalid') from error
        host = parsed.hostname.lower()
        matching = [r for r in self.routes if
                    r['protocol'] == parsed.scheme and r['host'] == host and r['port'] == port]
        if len(matching) != 1:
            raise NetworkDenied('network_destination_not_granted')
        owned = f'{parsed.scheme}://{host}:{port}' in self.target_connectors
        if owned:
            if self.target_connectors[f'{parsed.scheme}://{host}:{port}'] is None:
                raise NetworkDenied('network_owned_connector_unavailable')
            policy = matching[0]['address_policy']
            if policy['public_only'] or not any(ipaddress.ip_address('127.0.0.1') in ipaddress.ip_network(cidr, strict=True)
                                              for cidr in policy['cidrs']):
                raise NetworkDenied('network_resolved_address_not_granted')
            return parsed, port, '127.0.0.1'
        answers = queue.Queue(maxsize=1)
        if not self.resolvers.acquire(blocking=False):
            raise NetworkDenied('network_resolution_unavailable')
        def resolve():
            try:
                answers.put(socket.getaddrinfo(host, port, type=socket.SOCK_STREAM))
            except OSError:
                answers.put(None)
            finally:
                self.resolvers.release()
        threading.Thread(target=resolve, daemon=True).start()
        try:
            rows = answers.get(timeout=3)
        except queue.Empty as error:
            raise NetworkDenied('network_resolution_unavailable') from error
        if not rows:
            raise NetworkDenied('network_resolution_unavailable')
        policy = matching[0]['address_policy']
        addresses = list(dict.fromkeys(row[4][0] for row in rows))
        networks = [ipaddress.ip_network(cidr, strict=True) for cidr in policy['cidrs']]
        for value in addresses:
            address = ipaddress.ip_address(value)
            if ((policy['public_only'] and not address.is_global) or
                    (not policy['public_only'] and not any(address in net for net in networks))):
                raise NetworkDenied('network_resolved_address_not_granted')
        if not self._active():
            raise NetworkDenied('network_lease_inactive')
        return parsed, port, addresses[0]

    @contextmanager
    def _exchange(self, url, method, headers, chunks, length):
        if method not in ('GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'):
            raise NetworkDenied('network_method_invalid')
        for name, value in headers.items():
            if (not isinstance(name, str) or not isinstance(value, str) or
                    not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name) or
                    any(ord(c) < 32 or ord(c) == 127 for c in value) or
                    name.lower() in _HOP_HEADERS | {'host', 'content-length'}):
                raise NetworkDenied('network_header_invalid')
        parsed, port, address = self._destination(url)
        peer = binding = response = None
        total = 0
        status = 'unknown'
        connection = http.client.HTTPConnection(parsed.hostname, port, timeout=5)
        try:
            with self.dispatch_guard():
                if not self._active():
                    raise NetworkDenied('network_lease_inactive')
                if self.request_binder is not None:
                    binding = self.request_binder(method, url, headers, request_length=length)
                    if binding is not None:
                        headers = binding.headers
                origin = f'{parsed.scheme}://{parsed.hostname}:{port}'
                connector = self.target_connectors.get(origin)
                peer = connector(origin) if connector is not None else socket.create_connection((address, port), timeout=5)
                peer.settimeout(5)
                with self.lock:
                    self.sockets.add(peer)
                if parsed.scheme == 'https':
                    wrapped = self.upstream_context.wrap_socket(peer, server_hostname=parsed.hostname)
                    with self.lock:
                        self.sockets.discard(peer); self.sockets.add(wrapped)
                    peer = wrapped
                connection.sock = peer
                if not self._active():
                    raise NetworkDenied('network_lease_inactive')
                path = (parsed.path or '/') + ('?' + parsed.query if parsed.query else '')
                connection.putrequest(method, path, skip_accept_encoding=True)
                for name, value in headers.items():
                    connection.putheader(name, value)
                connection.putheader('Connection', 'close')
                connection.putheader('Transfer-Encoding' if length is None else 'Content-Length',
                                     'chunked' if length is None else str(length))
                connection.endheaders()
            for chunk in chunks:
                if total + len(chunk) > self.maximum_bytes:
                    raise NetworkDenied('network_body_limit')
                with self.dispatch_guard():
                    if not self._active():
                        raise NetworkDenied('network_lease_inactive')
                    connection.send((f'{len(chunk):x}\r\n'.encode() + chunk + b'\r\n') if length is None else chunk)
                    total += len(chunk)
            if length is not None and total != length:
                raise NetworkDenied('network_body_incomplete')
            with self.dispatch_guard():
                if not self._active():
                    raise NetworkDenied('network_lease_inactive')
                if length is None:
                    connection.send(b'0\r\n\r\n')
            response = connection.getresponse()
            if not self._active():
                raise NetworkDenied('network_lease_inactive')
            if binding is not None:
                binding.accept_response(response)
            yield response, parsed, port, address, binding
            status = 'settled'
        finally:
            with self.lock:
                self.sockets.discard(peer)
            connection.close()
            if peer:
                peer.close()
            if binding is not None:
                binding.finish(status, response.status if response is not None else None, total)

    def _response_shape(self, response, method):
        lengths = response.headers.get_all('Content-Length', [])
        encodings = response.headers.get_all('Transfer-Encoding', [])
        if (len(lengths) > 1 or (lengths and not lengths[0].isdecimal()) or
                (encodings and encodings != ['chunked']) or (lengths and encodings) or
                response.status == 101):
            raise NetworkDenied('network_response_framing_invalid')
        no_body = method == 'HEAD' or response.status in (204, 304) or 100 <= response.status < 200
        length = int(lengths[0]) if lengths else None
        if not no_body and length is not None and length > self.maximum_bytes:
            raise NetworkDenied('network_response_limit')
        return length, no_body

    def _payload(self, response, length, no_body, *, limit=None, binding=None):
        total = 0
        if no_body:
            return
        limit = self.maximum_bytes if limit is None else limit
        while True:
            if not self._active():
                raise NetworkDenied('network_lease_inactive')
            chunk = response.read1(16384)
            if not self._active():
                raise NetworkDenied('network_lease_inactive')
            if not chunk:
                if length is not None and total != length:
                    raise NetworkDenied('network_response_incomplete')
                if binding is not None:
                    tail = binding.filter_chunk(b'', final=True)
                    if tail:
                        yield tail
                return
            total += len(chunk)
            if total > limit:
                raise NetworkDenied('network_response_limit')
            filtered = binding.filter_chunk(chunk) if binding is not None else chunk
            if filtered:
                yield filtered

    def _request_chunks(self, stream, length):
        total = 0
        while length is None or total < length:
            if not self._active():
                raise NetworkDenied('network_lease_inactive')
            if length is None:
                row = stream.readline(129)
                token = row.rstrip(b'\r\n').split(b';', 1)[0]
                if len(row) > 128 or not row.endswith(b'\r\n') or not re.fullmatch(b'[0-9a-fA-F]+', token):
                    raise NetworkDenied('network_body_framing_invalid')
                remaining = int(token, 16)
                if remaining == 0:
                    # Trailers cannot silently add credentials or change framing.
                    if stream.readline(3) != b'\r\n':
                        raise NetworkDenied('network_body_trailers_unavailable')
                    return
            else:
                remaining = length - total
            if total + remaining > self.maximum_bytes:
                raise NetworkDenied('network_body_limit')
            while remaining:
                chunk = stream.read(min(16384, remaining))
                if not chunk:
                    raise NetworkDenied('network_body_incomplete')
                remaining -= len(chunk); total += len(chunk)
                yield chunk
            if length is None and stream.read(2) != b'\r\n':
                raise NetworkDenied('network_body_framing_invalid')

    def fetch(self, url, *, method='GET', headers=None, body=b'', redirects=5):
        # This convenience API remains small; native clients use the streaming proxy.
        limit = min(self.maximum_bytes, 1024 * 1024)
        if not isinstance(body, bytes) or len(body) > limit:
            raise NetworkDenied('network_body_limit')
        headers = dict(headers or {})
        for attempt in range(redirects + 1):
            chunks = (body[index:index + 16384] for index in range(0, len(body), 16384))
            with self._exchange(url, method, headers, chunks, len(body)) as (response, parsed, port, address, binding):
                length, no_body = self._response_shape(response, method)
                if not no_body and length is not None and length > limit:
                    raise NetworkDenied('network_response_limit')
                payload = b''.join(self._payload(response, length, no_body, limit=limit, binding=binding))
                location = response.getheader('Location')
                if response.status in (301, 302, 303, 307, 308) and location:
                    if attempt == redirects:
                        raise NetworkDenied('network_redirect_limit')
                    next_url = urljoin(url, location)
                    next_parsed, next_port, _ = self._destination(next_url)
                    if (next_parsed.scheme, next_parsed.hostname, next_port) != (parsed.scheme, parsed.hostname, port):
                        headers = {k: v for k, v in headers.items() if k.lower() not in ('authorization', 'cookie', 'x-oslit-access', 'x-oslit-account', 'x-oslit-effect')}
                    if response.status == 303:
                        method, body = 'GET', b''
                    url = next_url
                    continue
                return {'status': response.status, 'body': payload,
                        'host': parsed.hostname, 'port': port, 'peer_address': address,
                        'content_type': response.getheader('Content-Type', 'application/octet-stream')}
        raise NetworkDenied('network_redirect_limit')

    def serve(self, endpoint: Path, *, certificate=None, private_key=None):
        self._serve(endpoint, certificate=certificate, private_key=private_key)

    def serve_tcp(self, *, certificate=None, private_key=None):
        self._serve(None, certificate=certificate, private_key=private_key)
        return self.server.server_address[1]

    def _serve(self, endpoint, *, certificate, private_key):
        if self.server is not None or (endpoint is not None and (endpoint.exists() or endpoint.is_symlink())):
            raise NetworkDenied('network_endpoint_exists')
        context = None
        if certificate is not None or private_key is not None:
            if certificate is None or private_key is None:
                raise NetworkDenied('network_tls_material_incomplete')
            key_path = Path(private_key)
            if key_path.is_symlink() or key_path.stat().st_mode & 0o077:
                raise NetworkDenied('network_tls_key_not_private')
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.set_alpn_protocols(['http/1.1'])
            context.load_cert_chain(str(certificate), str(private_key))
        gate = self
        slots = threading.BoundedSemaphore(8)
        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                if not slots.acquire(blocking=False):
                    return
                connection = self.request
                stream = None
                response_started = False
                connection.settimeout(5)
                with gate.lock:
                    gate.sockets.add(connection)
                try:
                    # Keep the first parser unbuffered so TLS bytes stay in the socket.
                    stream = connection.makefile('rb', buffering=0)
                    method, url, headers = _request(stream)
                    if method == 'CONNECT':
                        if context is None:
                            raise NetworkDenied('native_https_proxy_unavailable')
                        parsed, port, _ = gate._destination('https://' + url)
                        authority = ('[' + parsed.hostname + ']' if ':' in parsed.hostname else parsed.hostname) + ':' + str(port)
                        if url != authority or headers.get('host') != authority or parsed.path or headers.get('content-length', '0') != '0':
                            raise NetworkDenied('network_connect_invalid')
                        stream.close(); stream = None
                        connection.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
                        wrapped = context.wrap_socket(connection, server_side=True)
                        with gate.lock:
                            gate.sockets.discard(connection); gate.sockets.add(wrapped)
                        connection = wrapped
                        stream = connection.makefile('rb')
                        method, target, headers = _request(stream)
                        hosts = {authority}
                        if port == 443:
                            hosts.add(parsed.hostname)
                        if (headers.get('host') not in hosts or not target.startswith('/') or target.startswith('//')):
                            raise NetworkDenied('network_inner_authority_changed')
                        url = 'https://' + authority + target
                    encoding = headers.get('transfer-encoding')
                    length_text = headers.get('content-length', '0')
                    if (encoding is not None and (encoding != 'chunked' or 'content-length' in headers)):
                        raise NetworkDenied('network_body_framing_invalid')
                    if not length_text.isdecimal() or not 0 <= int(length_text) <= gate.maximum_bytes:
                        raise NetworkDenied('network_body_limit')
                    length = None if encoding else int(length_text)
                    forwarded = dict(_forward_headers(list(headers.items()), request=True))
                    chunks = gate._request_chunks(stream, length)
                    with gate._exchange(url, method, forwarded, chunks, length) as (response, _, _, _, binding):
                        response_length, no_body = gate._response_shape(response, method)
                        location = response.getheader('Location')
                        if response.status in (301, 302, 303, 307, 308) and location:
                            gate._destination(urljoin(url, location))
                        lines = [f'HTTP/1.1 {response.status} Response']
                        lines.extend(f'{key}: {value}' for key, value in _forward_headers(binding.response_headers if binding is not None else response.getheaders()))
                        if response_length is not None:
                            lines.append(f'Content-Length: {response_length}')
                        elif not no_body:
                            lines.append('Transfer-Encoding: chunked')
                        lines.append('Connection: close')
                        with gate.dispatch_guard():
                            if not gate._active():
                                raise NetworkDenied('network_lease_inactive')
                            response_started = True
                            connection.sendall(('\r\n'.join(lines) + '\r\n\r\n').encode('latin-1'))
                        for chunk in gate._payload(response, response_length, no_body, binding=binding):
                            with gate.dispatch_guard():
                                if not gate._active():
                                    raise NetworkDenied('network_lease_inactive')
                                connection.sendall((f'{len(chunk):x}\r\n'.encode() + chunk + b'\r\n') if response_length is None else chunk)
                        if response_length is None and not no_body:
                            with gate.dispatch_guard():
                                if not gate._active():
                                    raise NetworkDenied('network_lease_inactive')
                                connection.sendall(b'0\r\n\r\n')
                except (OSError, ValueError, NetworkDenied, http.client.HTTPException):
                    try:
                        if response_started:
                            return
                        connection.sendall(b'HTTP/1.1 403 Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
                    except OSError:
                        pass
                finally:
                    if stream:
                        stream.close()
                    with gate.lock:
                        gate.sockets.discard(connection)
                    connection.close(); slots.release()
        base = socketserver.TCPServer if endpoint is None else socketserver.UnixStreamServer
        class Server(socketserver.ThreadingMixIn, base):
            daemon_threads = True
            block_on_close = False
        address = ('127.0.0.1', 0) if endpoint is None else str(endpoint)
        self.server = Server(address, Handler)
        self.endpoint = endpoint
        if endpoint is not None:
            os.chmod(endpoint, 0o600)
            info = endpoint.lstat()
            self.endpoint_identity = info.st_dev, info.st_ino
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.closed.set(); self._close_sockets()
        replaced = False
        if self.server:
            self.server.shutdown(); self.server.server_close(); self.thread.join()
        if self.endpoint is not None:
            try:
                info = self.endpoint.lstat()
            except FileNotFoundError:
                pass
            else:
                if (info.st_dev, info.st_ino) == self.endpoint_identity:
                    self.endpoint.unlink()
                else:
                    replaced = True
        self.watcher.join(timeout=1)
        if replaced:
            raise NetworkDenied('network_endpoint_identity_changed')
