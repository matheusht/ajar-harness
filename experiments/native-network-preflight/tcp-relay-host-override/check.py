#!/usr/bin/env python3
"""End-to-end TCP check of the relay host override; no Docker or provider."""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import shutil
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import time


HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'tcp_relay.go'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def port_free():
    with socket.socket() as probe:
        try:
            probe.bind(('0.0.0.0', 8080))
        except OSError:
            return False
    return True


class Receiver(socketserver.BaseRequestHandler):
    def handle(self):
        if self.client_address[0] != self.server.private_host:
            self.server.rejected_peers += 1
            return
        self.request.settimeout(7)
        parts = []
        while chunk := self.request.recv(4096):
            parts.append(chunk)
            if sum(map(len, parts)) > 64:
                self.server.oversized_requests += 1
                return
        payload = b''.join(parts)
        self.server.received.append(payload)
        self.request.sendall(b'owned-ack:' + payload)


def relay_call(process, marker):
    for _ in range(50):
        if process.poll() is not None:
            raise RuntimeError('relay_exited_before_client')
        try:
            client = socket.create_connection(('127.0.0.1', 8080), timeout=1)
            break
        except ConnectionRefusedError:
            time.sleep(.1)
    else:
        raise RuntimeError('relay_listener_unavailable')
    with client:
        client.settimeout(7)
        try:
            client.sendall(marker)
            client.shutdown(socket.SHUT_WR)
            return client.recv(4096)
        except (BrokenPipeError, ConnectionResetError):
            return b''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--private-host', required=True)
    args = parser.parse_args()
    try:
        address = ipaddress.ip_address(args.private_host)
        octets = address.packed
        if address.version != 4 or not (octets[0] == 10 or
                octets[0] == 172 and 16 <= octets[1] <= 31 or
                octets[0] == 192 and octets[1] == 168):
            raise ValueError('not RFC1918 IPv4')
    except ValueError:
        parser.error('--private-host must be an assigned literal RFC1918 IPv4')
    if not port_free():
        parser.error('local port 8080 is occupied')
    go = shutil.which('go')
    if not go:
        parser.error('Go is required')
    output = args.output.resolve()
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    output.chmod(0o700)
    report = {'status': 'running', 'source_sha256': sha(SOURCE),
              'checks_sha256': sha(HERE / 'CHECKS.md'), 'check_sha256': sha(Path(__file__)),
              'go_version': subprocess.check_output([go, 'version'], text=True).strip(),
              'python_version': sys.version.split()[0], 'checks': []}
    process = None
    receiver = None
    thread = None

    def check(name, passed, observation):
        report['checks'].append({'name': name, 'pass': bool(passed), 'observation': observation})
        if not passed:
            raise AssertionError(name)

    try:
        addresses = set()
        try:
            addresses = {item[4][0] for item in socket.getaddrinfo(
                'host.docker.internal', 0, type=socket.SOCK_STREAM)}
        except socket.gaierror:
            pass
        check('default name does not resolve to owned private receiver',
              args.private_host not in addresses,
              {'resolved_addresses': sorted(addresses)})
        with tempfile.TemporaryDirectory(prefix='tcp-relay-override-') as temporary:
            binary = Path(temporary) / 'relay'
            build_env = dict(os.environ, CGO_ENABLED='0', GOWORK='off', GO111MODULE='off',
                             GOTOOLCHAIN='local', GOPROXY='off', GOSUMDB='off')
            build = subprocess.run([go, 'build', '-trimpath', '-o', str(binary), str(SOURCE)],
                                   env=build_env, capture_output=True, text=True, timeout=90)
            check('native relay build', build.returncode == 0,
                  {'exit_code': build.returncode, 'error_type': 'build_failed' if build.returncode else None})
            report['binary_sha256'] = sha(binary)
            receiver = socketserver.ThreadingTCPServer((args.private_host, 0), Receiver)
            receiver.daemon_threads = True
            receiver.received = []
            receiver.private_host = args.private_host
            receiver.rejected_peers = 0
            receiver.oversized_requests = 0
            thread = threading.Thread(target=receiver.serve_forever, daemon=True)
            thread.start()
            report['receiver'] = f'{args.private_host}:{receiver.server_address[1]}'

            for invalid in ('8.8.8.8', 'example.com', '0.0.0.0', '127.0.0.1',
                            '169.254.1.1', '172.15.0.1', '172.32.0.1', 'fd00::1'):
                env = os.environ.copy()
                env['HOST_GATEWAY_HOST'] = invalid
                env['HOST_GATEWAY_PORT'] = str(receiver.server_address[1])
                before = len(receiver.received)
                process = subprocess.Popen([str(binary)], env=env, stdout=subprocess.DEVNULL,
                                           stderr=subprocess.DEVNULL)
                code = process.wait(timeout=5)
                process = None
                check('reject_' + invalid, code == 2 and port_free() and
                      len(receiver.received) == before,
                      {'host_setting': invalid, 'exit_code': code, 'listener_closed': port_free()})

            for name, override, marker in (
                ('explicit_override', args.private_host, b'explicit-override'),
                ('unset_default', None, b'unset-default'),
                ('empty_default', '', b'empty-default'),
            ):
                env = os.environ.copy()
                env['HOST_GATEWAY_PORT'] = str(receiver.server_address[1])
                if override is None:
                    env.pop('HOST_GATEWAY_HOST', None)
                else:
                    env['HOST_GATEWAY_HOST'] = override
                before = len(receiver.received)
                process = subprocess.Popen([str(binary)], env=env, stdout=subprocess.DEVNULL,
                                           stderr=subprocess.DEVNULL)
                try:
                    response = relay_call(process, marker)
                    time.sleep(.1)
                    arrivals = receiver.received[before:]
                    passed = (response == b'owned-ack:' + marker and arrivals == [marker]) if name == 'explicit_override' else marker not in arrivals
                    check(name, passed, {'host_setting': '<unset>' if override is None else override,
                                         'port': receiver.server_address[1],
                                         'receiver_markers': [item.decode('ascii') for item in arrivals],
                                         'response_class': 'exact_ack' if response == b'owned-ack:' + marker else 'no_exact_ack'})
                finally:
                    process.terminate()
                    process.wait(timeout=5)
                    process = None
                check(name + '_cleanup', port_free(), {'relay_exited': True, 'port_8080_free': port_free()})
            check('receiver accepted only bounded self-route traffic',
                  receiver.rejected_peers == receiver.oversized_requests == 0,
                  {'rejected_peers': receiver.rejected_peers,
                   'oversized_requests': receiver.oversized_requests})
    except Exception as error:
        report['error'] = {'type': type(error).__name__, 'message': str(error)[:160]}
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if receiver is not None:
            receiver.shutdown()
            receiver.server_close()
        if thread is not None:
            thread.join(timeout=5)
        report['source_stable'] = sha(SOURCE) == report['source_sha256']
        report['relay_port_free'] = port_free()
        report['status'] = 'pass' if report['checks'] and all(row['pass'] for row in report['checks']) \
            and report['source_stable'] and report['relay_port_free'] and 'error' not in report else 'fail'
        (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'output': str(output)}))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
