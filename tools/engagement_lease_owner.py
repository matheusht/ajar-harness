"""Independent renewable owner for a host-launched process, with Docker readback."""
from __future__ import annotations

import json
import inspect
import math
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import threading
import time


def _duration(value, maximum):
    if (isinstance(value, bool) or not isinstance(value, (int, float)) or
            not math.isfinite(value) or not 0 < value <= maximum):
        raise RuntimeError('worker_lease_invalid')
    return value


def _stop_docker(identity):
    """Check the current daemon and exact nonce before stopping a known container."""
    def call(*args):
        return subprocess.run([identity['binary'], '--host', identity['endpoint'], *args],
                              capture_output=True, timeout=5, check=False)
    daemon = call('info', '--format', '{{.ID}}')
    if daemon.returncode or daemon.stdout.decode().strip() != identity['daemon_id']:
        return False
    result = call('container', 'inspect', identity['id'])
    if result.returncode:
        return False
    rows = json.loads(result.stdout)
    if len(rows) != 1:
        return False
    info = rows[0]
    if (info['Id'] != identity['id'] or
            info.get('Config', {}).get('Labels', {}).get('io.oslit.engagement') != identity['nonce']):
        return False
    if info['State']['Running'] and call('container', 'kill', identity['id']).returncode:
        return False
    after = call('container', 'inspect', identity['id'])
    return not after.returncode and json.loads(after.stdout)[0]['State']['Running'] is False


def command_environment():
    return {key: os.environ[key] for key in ('PATH', 'LANG', 'LC_ALL', 'SYSTEMROOT') if key in os.environ}


def _container_watch(nonce, maximum):
    import json
    import math
    import os
    import re
    import select
    import signal
    import sys
    import time

    maximum = float(maximum)
    if not re.fullmatch('[0-9a-f]{32}', nonce) or not math.isfinite(maximum) or not 0 < maximum <= 2 ** 31:
        raise ValueError('container_lease_invalid')
    if sys.platform == 'linux':
        clock = lambda: time.clock_gettime(time.CLOCK_BOOTTIME)
    else:
        clock = time.monotonic
    deadline = clock() + min(maximum, 5)
    sequence, pending, stopped = -1, b'', [False]
    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, lambda *_: stopped.__setitem__(0, True))
    os.set_blocking(0, False)
    os.set_blocking(1, False)
    while not stopped[0] and clock() < deadline:
        for _ in range(256):
            try:
                child, _status = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                break
            if child == 0:
                break
        if not select.select([0], [], [], min(.05, max(0, deadline - clock())))[0]:
            continue
        chunk = os.read(0, 4096)
        if not chunk:
            return
        pending += chunk
        if len(pending) > 4096:
            raise ValueError('container_lease_frame_invalid')
        while b'\n' in pending:
            if clock() >= deadline:
                return
            line, pending = pending.split(b'\n', 1)
            value = json.loads(line)
            common = {'kind', 'nonce', 'sequence'}
            if (not isinstance(value, dict) or not common <= set(value)
                    or value['kind'] != 'container-lease-v1' or value['nonce'] != nonce
                    or type(value['sequence']) is not int or value['sequence'] != sequence + 1):
                raise ValueError('container_lease_frame_invalid')
            if set(value) == common | {'revoke'} and value['revoke'] is True:
                return
            if set(value) != common | {'seconds', 'expires_at_unix'}:
                raise ValueError('container_lease_frame_invalid')
            seconds, expires = value['seconds'], value['expires_at_unix']
            if (type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0 < seconds <= maximum
                    or type(expires) not in (int, float) or not math.isfinite(expires)):
                raise ValueError('container_lease_invalid')
            remaining = min(seconds, expires - time.time())
            if remaining <= 0:
                raise ValueError('container_lease_expired')
            deadline, sequence = clock() + remaining, value['sequence']
            acknowledgment = {'kind': 'container-lease-v1', 'nonce': nonce, 'sequence': sequence,
                              'accepted': True, 'expires_at_unix': expires}
            data = (json.dumps(acknowledgment, allow_nan=False) + '\n').encode()
            if os.write(1, data) != len(data):
                raise ValueError('container_lease_acknowledgment_failed')


def guardian_command(nonce, maximum):
    import re
    if not isinstance(nonce, str) or not re.fullmatch('[0-9a-f]{32}', nonce):
        raise RuntimeError('worker_owner_nonce_invalid')
    _duration(maximum, 2 ** 31)
    source = ('import sys\n' + inspect.getsource(_container_watch) +
              '\ntry:\n    _container_watch(sys.argv[1], sys.argv[2])\n'
              'except (ValueError, TypeError, OSError, AttributeError):\n    raise SystemExit(2)\n')
    return ['python3', '-I', '-S', '-c', source, nonce, str(maximum)]


class OwnedProcess:
    """The host owns argv. This is lifetime control, not arbitrary-code isolation."""
    def __init__(self, argv, *, lease_seconds, maximum_lease_seconds, docker_identity=None,
                 owner_command=None, guardian_nonce=None):
        self.maximum = _duration(maximum_lease_seconds, 2 ** 31)
        self.lease = _duration(lease_seconds, self.maximum)
        self.argv = argv
        self.docker_identity = docker_identity
        if guardian_nonce is not None and (not docker_identity or guardian_nonce != docker_identity['nonce']):
            raise RuntimeError('worker_owner_nonce_invalid')
        self.guardian_nonce = guardian_nonce
        self.owner_command = owner_command or [sys.executable, str(Path(__file__).resolve()), 'watch']
        self.process = None
        self.condition = threading.Condition()
        self.control_lock = threading.RLock()
        self.sequence = 0
        self.failure = None
        self.state = {'running': False, 'pid': None, 'status': 'not_started'}

    def start(self):
        if self.process is not None:
            raise RuntimeError('worker_owner_already_started')
        self.process = subprocess.Popen(self.owner_command, env=command_environment(),
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True, start_new_session=True)
        def read():
            try:
                while line := self.process.stdout.readline(16385):
                    if len(line) > 16384 or not line.endswith('\n'):
                        raise ValueError('owner_frame_invalid')
                    value = json.loads(line)
                    if (not isinstance(value, dict) or type(value.get('running')) is not bool
                            or value.get('running') and type(value.get('sequence')) is not int):
                        raise ValueError('owner_frame_invalid')
                    with self.condition:
                        self.state = value
                        self.condition.notify_all()
            except (ValueError, OSError):
                with self.condition:
                    self.failure = 'owner_protocol_invalid'
                try: self.process.stdin.close()
                except OSError: pass
            finally:
                with self.condition:
                    self.condition.notify_all()
        threading.Thread(target=read, daemon=True).start()
        self._send({'argv': self.argv, 'lease_seconds': self.lease,
                    'maximum_lease_seconds': self.maximum, 'docker_identity': self.docker_identity,
                    'guardian_nonce': self.guardian_nonce,
                    'expires_at_unix': time.time() + self.lease})
        try:
            self._acknowledged(0)
        except RuntimeError:
            self.process.kill(); self.process.wait()
            raise
        return self.readback()

    def _acknowledged(self, sequence):
        deadline = time.monotonic() + 5
        with self.condition:
            while True:
                if self.failure or self.process.poll() is not None:
                    raise RuntimeError('worker_owner_acknowledgment_unavailable')
                if self.state.get('running') and self.state.get('sequence') == sequence:
                    return
                if self.state.get('status') != 'not_started' and not self.state.get('running'):
                    raise RuntimeError('worker_owner_acknowledgment_unavailable')
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError('worker_owner_acknowledgment_unavailable')
                self.condition.wait(min(.05, remaining))

    def _send(self, value):
        if self.process is None or self.process.poll() is not None:
            raise RuntimeError('worker_owner_inactive')
        try:
            self.process.stdin.write(json.dumps(value) + '\n'); self.process.stdin.flush()
        except (OSError, ValueError) as error:
            raise RuntimeError('worker_owner_inactive') from error

    def renew(self, seconds):
        with self.control_lock:
            if not self.readback()['running']:
                raise RuntimeError('worker_owner_inactive')
            self.sequence += 1
            self._send({'renew': _duration(seconds, self.maximum), 'expires_at_unix': time.time() + seconds,
                        'sequence': self.sequence})
            self._acknowledged(self.sequence)

    def readback(self):
        with self.condition:
            state = dict(self.state)
            if self.process is not None and self.process.poll() is not None and state.get('running'):
                state.update(running=False, status='owner_lost', cleanup_verified=False)
            if self.failure:
                state.update(running=False, status=self.failure, cleanup_verified=False)
            return state

    def revoke(self):
        if self.process is None:
            return self.readback()
        if self.process.poll() is None:
            try:
                self._send({'revoke': True})
            except RuntimeError:
                pass
            try:
                self.process.wait(timeout=12)
            except subprocess.TimeoutExpired:
                self.process.kill(); self.process.wait()
        self.process.stdin.close()
        time.sleep(.02)
        return self.readback()


def _clock():
    return time.clock_gettime(time.CLOCK_BOOTTIME) if sys.platform == 'linux' else time.monotonic()


def _guardian_exchange(child, frame, deadline):
    data = (json.dumps(frame, allow_nan=False) + '\n').encode()
    incoming = b''
    for stream in (child.stdin, child.stdout):
        os.set_blocking(stream.fileno(), False)
    while data:
        remaining = min(5, deadline - _clock())
        if remaining <= 0 or not select.select([], [child.stdin], [], remaining)[1]:
            raise RuntimeError('worker_guardian_acknowledgment_unavailable')
        count = os.write(child.stdin.fileno(), data)
        data = data[count:]
    while b'\n' not in incoming:
        remaining = min(5, deadline - _clock())
        if remaining <= 0 or not select.select([child.stdout], [], [], remaining)[0]:
            raise RuntimeError('worker_guardian_acknowledgment_unavailable')
        chunk = os.read(child.stdout.fileno(), 4096)
        if not chunk or len(incoming) + len(chunk) > 4096:
            raise RuntimeError('worker_guardian_acknowledgment_unavailable')
        incoming += chunk
    expected = {'kind': 'container-lease-v1', 'nonce': frame['nonce'], 'sequence': frame['sequence'],
                'accepted': True, 'expires_at_unix': frame['expires_at_unix']}
    if incoming.count(b'\n') != 1 or not incoming.endswith(b'\n') or json.loads(incoming) != expected:
        raise RuntimeError('worker_guardian_acknowledgment_invalid')


def _watch():
    configuration = json.loads(sys.stdin.readline())
    maximum = _duration(configuration['maximum_lease_seconds'], 2 ** 31)
    duration = min(configuration['lease_seconds'], configuration['expires_at_unix'] - time.time())
    deadline = _clock() + _duration(duration, maximum)
    nonce = configuration.get('guardian_nonce')
    child = subprocess.Popen(configuration['argv'], stdin=subprocess.PIPE if nonce else subprocess.DEVNULL,
                             stdout=subprocess.PIPE if nonce else subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
    stopped = [False]
    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, lambda *_: stopped.__setitem__(0, True))
    sequence, pending = 0, b''
    reason = 'lease_expired'
    try:
        if nonce:
            _guardian_exchange(child, {'kind': 'container-lease-v1', 'nonce': nonce, 'sequence': sequence,
                'seconds': configuration['lease_seconds'], 'expires_at_unix': configuration['expires_at_unix']}, deadline)
        print(json.dumps({'running': True, 'pid': child.pid, 'status': 'running', 'sequence': sequence}), flush=True)
        while not stopped[0] and _clock() < deadline:
            if child.poll() is not None:
                reason = 'process_exited'; break
            if select.select([sys.stdin], [], [], min(.05, max(0, deadline - _clock())))[0]:
                chunk = os.read(sys.stdin.fileno(), 4096)
                if not chunk:
                    reason = 'controller_lost'; break
                pending += chunk
                if len(pending) > 4096:
                    raise RuntimeError('worker_lease_update_invalid')
            while b'\n' in pending:
                if _clock() >= deadline:
                    break
                line, pending = pending.split(b'\n', 1)
                update = json.loads(line)
                if update == {'revoke': True}:
                    reason = 'revoked'; stopped[0] = True; break
                if (set(update) != {'renew', 'expires_at_unix', 'sequence'}
                        or type(update['sequence']) is not int or update['sequence'] != sequence + 1):
                    raise RuntimeError('worker_lease_update_invalid')
                duration = min(update['renew'], update['expires_at_unix'] - time.time())
                renewed_deadline = _clock() + _duration(duration, maximum)
                if nonce:
                    _guardian_exchange(child, {'kind': 'container-lease-v1', 'nonce': nonce,
                        'sequence': update['sequence'], 'seconds': update['renew'],
                        'expires_at_unix': update['expires_at_unix']}, deadline)
                deadline, sequence = renewed_deadline, update['sequence']
                print(json.dumps({'running': True, 'pid': child.pid, 'status': 'running', 'sequence': sequence}), flush=True)
    finally:
        if child.stdin:
            child.stdin.close()
        if child.poll() is None:
            try: os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError: pass
            try:
                child.wait(timeout=1)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL); child.wait()
        if child.stdout:
            child.stdout.close()
        cleanup = False
        if configuration.get('docker_identity'):
            try:
                cleanup = _stop_docker(configuration['docker_identity'])
            except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
                cleanup = False
        print(json.dumps({'running': False, 'pid': child.pid, 'status': reason,
                          'exit_code': child.returncode, 'cleanup_verified': cleanup,
                          'child_absence': 'container_stopped' if cleanup else 'not_observed'}), flush=True)


if __name__ == '__main__':
    if sys.argv[1:] == ['watch']:
        _watch()
    elif len(sys.argv) == 4 and sys.argv[1] == 'container-watch':
        try:
            _container_watch(sys.argv[2], sys.argv[3])
        except (ValueError, TypeError, OSError, AttributeError):
            raise SystemExit(2)
    else:
        raise SystemExit(64)
