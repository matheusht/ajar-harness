"""One worker's loopback proxy over private stdio to its fixed host policy gate.

Run this same file with ``relay`` inside the worker. It needs only Python's
standard library. The host supplies no destination in response to worker frames;
every stream reaches the one pre-bound NetworkGate Unix socket.
"""
from __future__ import annotations

import base64
import json
import os
import queue
import select
import signal
import socket
import subprocess
import sys
import threading

MAX_FRAME = 24576
MAX_DATA = 16384
MAX_STREAMS = 8


class BridgeUnavailable(RuntimeError):
    pass


def _pairs(rows):
    value = {}
    for key, item in rows:
        if key in value:
            raise ValueError('duplicate_field')
        value[key] = item
    return value


def _decode(line):
    if len(line) > MAX_FRAME or not line.endswith(b'\n'):
        raise ValueError('frame_size')
    value = json.loads(line, object_pairs_hook=_pairs)
    if not isinstance(value, dict):
        raise ValueError('frame_object')
    kind = value.get('type')
    required = {'ready': {'type', 'port'}, 'open': {'type', 'id'},
                'data': {'type', 'id', 'data'}, 'end': {'type', 'id'}, 'close': {'type', 'id'}}
    if kind not in required or set(value) != required[kind]:
        raise ValueError('frame_fields')
    if kind == 'ready':
        if type(value['port']) is not int or not 1 <= value['port'] <= 65535:
            raise ValueError('frame_port')
    elif type(value['id']) is not int or not 1 <= value['id'] < 2 ** 63:
        raise ValueError('frame_id')
    if kind == 'data':
        data = base64.b64decode(value['data'], validate=True)
        if not 0 < len(data) <= MAX_DATA:
            raise ValueError('frame_data')
        value['data'] = data
    return value


class _Channel:
    """The bounded byte protocol shared by both ends; it carries no authority."""
    def __init__(self, reader, writer, *, opener=None, on_ready=None):
        self.reader, self.writer = reader, writer
        self.opener, self.on_ready = opener, on_ready
        self.closed = threading.Event()
        self.failure = None
        self.frames = queue.Queue(maxsize=64)
        self.lock = threading.Lock()
        self.peers = {}
        self.highest = 0
        self.ready_seen = on_ready is None
        os.set_blocking(writer.fileno(), False)
        self.read_thread = threading.Thread(target=self._read, daemon=True)
        self.write_thread = threading.Thread(target=self._write, daemon=True)

    def start(self):
        self.write_thread.start(); self.read_thread.start()

    def emit(self, value):
        if self.closed.is_set():
            return
        try:
            encoded = json.dumps(value, separators=(',', ':'), allow_nan=False).encode() + b'\n'
            if len(encoded) > MAX_FRAME:
                raise ValueError('frame_size')
            while not self.closed.is_set():
                try:
                    self.frames.put(encoded, timeout=.05)
                    return
                except queue.Full:
                    continue
        except ValueError:
            self.stop('bridge_output_overflow')

    def _write(self):
        try:
            while not self.closed.is_set():
                try: pending = memoryview(self.frames.get(timeout=.05))
                except queue.Empty: continue
                while pending and not self.closed.is_set():
                    if select.select([], [self.writer], [], .05)[1]:
                        try: count = os.write(self.writer.fileno(), pending)
                        except BlockingIOError: continue
                        pending = pending[count:]
        except (OSError, ValueError):
            self.stop('bridge_pipe_closed')

    def _read(self):
        try:
            while not self.closed.is_set():
                line = self.reader.readline(MAX_FRAME + 1)
                if not line:
                    self.stop('bridge_pipe_closed'); return
                frame = _decode(line)
                kind = frame['type']
                if kind == 'ready':
                    if self.ready_seen or self.on_ready is None:
                        raise ValueError('unexpected_ready')
                    self.ready_seen = True; self.on_ready(frame['port']); continue
                identity = frame['id']
                if not self.ready_seen:
                    raise ValueError('ready_missing')
                if kind == 'open':
                    if self.opener is None or identity != self.highest + 1:
                        raise ValueError('stream_identity')
                    self.highest = identity
                    with self.lock:
                        available = len(self.peers) < MAX_STREAMS
                    if not available:
                        self.emit({'type': 'close', 'id': identity}); continue
                    try: peer = self.opener()
                    except Exception:
                        self.stop('bridge_gate_unavailable'); return
                    self._add(peer, identity)
                    continue
                with self.lock:
                    row = self.peers.get(identity)
                if row is None:
                    if identity > self.highest:
                        raise ValueError('stream_unknown')
                    continue
                if kind == 'data':
                    try: row['socket'].sendall(frame['data'])
                    except OSError: self._drop(identity, notify=True)
                elif kind == 'close':
                    self._drop(identity)
                else:
                    row['received_end'] = True
                    try: row['socket'].shutdown(socket.SHUT_WR)
                    except OSError: pass
                    if row['sent_end']:
                        self._drop(identity)
        except (ValueError, TypeError, KeyError, OSError):
            self.stop('bridge_protocol_invalid')

    def _add(self, peer, identity, *, start=True):
        peer.settimeout(1)
        with self.lock:
            if self.closed.is_set():
                peer.close(); return False
            self.peers[identity] = {'socket': peer, 'sent_end': False, 'received_end': False}
        if start:
            threading.Thread(target=self._pump, args=(identity,), daemon=True).start()
        return True

    def accept(self, peer):
        with self.lock:
            if self.closed.is_set() or len(self.peers) >= MAX_STREAMS:
                peer.close(); return
            self.highest += 1
            identity = self.highest
        if not self._add(peer, identity, start=False):
            return
        # Register first, but emit open before pumping an immediate TLS greeting.
        self.emit({'type': 'open', 'id': identity})
        threading.Thread(target=self._pump, args=(identity,), daemon=True).start()

    def _pump(self, identity):
        with self.lock:
            row = self.peers.get(identity)
        if row is None:
            return
        try:
            while not self.closed.is_set():
                try: data = row['socket'].recv(MAX_DATA)
                except socket.timeout: continue
                if not data:
                    row['sent_end'] = True
                    self.emit({'type': 'end', 'id': identity})
                    if row['received_end']:
                        self._drop(identity)
                    return
                self.emit({'type': 'data', 'id': identity, 'data': base64.b64encode(data).decode('ascii')})
        except OSError:
            self._drop(identity, notify=True)

    def _drop(self, identity, *, notify=False):
        with self.lock:
            row = self.peers.pop(identity, None)
        if row:
            try: row['socket'].shutdown(socket.SHUT_RDWR)
            except OSError: pass
            row['socket'].close()
            if notify:
                self.emit({'type': 'close', 'id': identity})

    def stop(self, failure=None):
        if failure and not self.closed.is_set() and self.failure is None:
            self.failure = failure
        self.closed.set()
        with self.lock:
            identities = list(self.peers)
        for identity in identities:
            self._drop(identity)


class ProxyBridge:
    """The host binds one trusted launch to one fixed, per-worker policy socket."""
    def __init__(self, launcher, command, gate, authorize, *, dispatch_guard):
        self.gate, self.authorize, self.guard = gate, authorize, dispatch_guard
        self.port = None
        self.ready = threading.Event()
        self.close_lock = threading.Lock()
        if not gate.endpoint or not callable(dispatch_guard) or not self._active():
            raise BridgeUnavailable('bridge_grant_inactive')
        with dispatch_guard():
            if not self._active():
                raise BridgeUnavailable('bridge_grant_inactive')
            self.process = launcher(command)
        if self.process.stdin is None or self.process.stdout is None:
            if self.process.poll() is None:
                self.process.terminate()
                try: self.process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    self.process.kill(); self.process.wait(timeout=1)
            raise BridgeUnavailable('bridge_private_pipes_required')
        self.channel = _Channel(self.process.stdout, self.process.stdin, opener=self._open,
                                on_ready=self._ready)
        self.closed = self.channel.closed
        self.channel.start()
        self.watcher = threading.Thread(target=self._watch, daemon=True); self.watcher.start()
        if not self.ready.wait(5) or self.closed.is_set():
            self.close()
            raise BridgeUnavailable('bridge_startup_unavailable')

    def _active(self):
        try: return self.authorize() is True and self.gate._active()
        except Exception: return False

    def _ready(self, port):
        self.port = port; self.ready.set()

    def _open(self):
        with self.guard():
            if not self._active():
                raise BridgeUnavailable('bridge_grant_inactive')
            info = self.gate.endpoint.lstat()
            if (info.st_dev, info.st_ino) != self.gate.endpoint_identity:
                raise BridgeUnavailable('bridge_gate_changed')
            peer = socket.socket(socket.AF_UNIX)
            try:
                peer.settimeout(1); peer.connect(str(self.gate.endpoint)); return peer
            except Exception:
                peer.close(); raise

    def _watch(self):
        while not self.closed.wait(.05):
            if not self._active():
                self.channel.stop('bridge_grant_inactive')
        self.close()

    def environment(self, ca_path):
        if self.closed.is_set() or not self._active() or not isinstance(ca_path, str) or not ca_path.startswith('/'):
            raise BridgeUnavailable('bridge_unavailable')
        proxy = f'http://127.0.0.1:{self.port}'
        return {'HTTP_PROXY': proxy, 'HTTPS_PROXY': proxy, 'http_proxy': proxy, 'https_proxy': proxy,
                'NO_PROXY': 'localhost,127.0.0.1,::1', 'no_proxy': 'localhost,127.0.0.1,::1',
                'SSL_CERT_FILE': ca_path, 'CURL_CA_BUNDLE': ca_path, 'NODE_EXTRA_CA_CERTS': ca_path}

    def close(self):
        with self.close_lock:
            self.channel.stop()
            self.channel.write_thread.join(timeout=1)
            if not self.process.stdin.closed:
                self.process.stdin.close()
            try: self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                try: os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                self.process.wait(timeout=2)
            if threading.current_thread() is not self.channel.read_thread:
                self.channel.read_thread.join(timeout=1)
            if not self.channel.read_thread.is_alive() and not self.process.stdout.closed:
                self.process.stdout.close()
            return {'host_process_exited': self.process.poll() is not None,
                    'native_exit': 'environment_readback_required', 'failure': self.channel.failure}


def relay_main():
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(('127.0.0.1', 0)); listener.listen(MAX_STREAMS); listener.settimeout(.1)
    channel = _Channel(sys.stdin.buffer, sys.stdout.buffer)
    channel.start(); channel.emit({'type': 'ready', 'port': listener.getsockname()[1]})
    try:
        while not channel.closed.is_set():
            try: peer, _ = listener.accept()
            except socket.timeout: continue
            channel.accept(peer)
    finally:
        listener.close(); channel.stop()
        channel.write_thread.join(timeout=1)
    return 1 if channel.failure else 0


if __name__ == '__main__':
    if sys.argv[1:] != ['relay']:
        raise SystemExit(64)
    raise SystemExit(relay_main())
