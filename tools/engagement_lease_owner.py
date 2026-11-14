"""Independent renewable owner for a host-launched process, with Docker readback."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import queue
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


class OwnedProcess:
    """The host owns argv. This is lifetime control, not arbitrary-code isolation."""
    def __init__(self, argv, *, lease_seconds, maximum_lease_seconds, docker_identity=None,
                 owner_command=None):
        self.maximum = _duration(maximum_lease_seconds, 2 ** 31)
        self.lease = _duration(lease_seconds, self.maximum)
        self.argv = argv
        self.docker_identity = docker_identity
        self.owner_command = owner_command or [sys.executable, str(Path(__file__).resolve()), 'watch']
        self.process = None
        self.events = queue.Queue(maxsize=64)
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
                    if not isinstance(value, dict) or type(value.get('running')) is not bool:
                        raise ValueError('owner_frame_invalid')
                    self.events.put_nowait(value)
            except (ValueError, queue.Full, OSError):
                self.failure = 'owner_protocol_invalid'
                try: self.process.stdin.close()
                except OSError: pass
        threading.Thread(target=read, daemon=True).start()
        self._send({'argv': self.argv, 'lease_seconds': self.lease,
                    'maximum_lease_seconds': self.maximum, 'docker_identity': self.docker_identity,
                    'expires_at_unix': time.time() + self.lease})
        try:
            self.state = self.events.get(timeout=5)
        except queue.Empty as error:
            self.process.kill(); self.process.wait()
            raise RuntimeError('worker_owner_not_ready') from error
        if not self.state.get('running'):
            raise RuntimeError('worker_owner_start_failed')
        return self.readback()

    def _send(self, value):
        if self.process is None or self.process.poll() is not None:
            raise RuntimeError('worker_owner_inactive')
        try:
            self.process.stdin.write(json.dumps(value) + '\n'); self.process.stdin.flush()
        except (OSError, ValueError) as error:
            raise RuntimeError('worker_owner_inactive') from error

    def renew(self, seconds):
        if not self.readback()['running']:
            raise RuntimeError('worker_owner_inactive')
        self._send({'renew': _duration(seconds, self.maximum), 'expires_at_unix': time.time() + seconds})

    def readback(self):
        while True:
            try:
                self.state = self.events.get_nowait()
            except queue.Empty:
                break
        if self.process is not None and self.process.poll() is not None and self.state.get('running'):
            self.state = {**self.state, 'running': False, 'status': 'owner_lost', 'cleanup_verified': False}
        if self.failure:
            self.state = {**self.state, 'running': False, 'status': self.failure, 'cleanup_verified': False}
        return dict(self.state)

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


def _watch():
    configuration = json.loads(sys.stdin.readline())
    maximum = _duration(configuration['maximum_lease_seconds'], 2 ** 31)
    duration = min(configuration['lease_seconds'], configuration['expires_at_unix'] - time.time())
    deadline = time.monotonic() + _duration(duration, maximum)
    child = subprocess.Popen(configuration['argv'], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
    stopped = [False]
    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, lambda *_: stopped.__setitem__(0, True))
    print(json.dumps({'running': True, 'pid': child.pid, 'status': 'running'}), flush=True)
    reason = 'lease_expired'
    try:
        while not stopped[0] and time.monotonic() < deadline:
            if child.poll() is not None:
                reason = 'process_exited'; break
            if select.select([sys.stdin], [], [], min(.05, max(0, deadline-time.monotonic())))[0]:
                line = sys.stdin.readline()
                if not line:
                    reason = 'controller_lost'; break
                update = json.loads(line)
                if update == {'revoke': True}:
                    reason = 'revoked'; break
                if set(update) != {'renew', 'expires_at_unix'}:
                    raise RuntimeError('worker_lease_update_invalid')
                duration = min(update['renew'], update['expires_at_unix'] - time.time())
                deadline = time.monotonic() + _duration(duration, maximum)
    finally:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=1)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL); child.wait()
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
    if sys.argv[1:] != ['watch']:
        raise SystemExit(64)
    _watch()
