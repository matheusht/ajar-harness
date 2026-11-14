#!/usr/bin/env python3
"""Actual local HTTP/lease workflows; Docker/SSH availability is reported separately."""
from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import nullcontext

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'tools'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = {'kind': 'environment-engineering-e2e-v2', 'checks': [],
              'classification': 'actual_local_harmless_controls',
              'unverified': ['Docker isolation', 'SSH host', 'native HTTPS proxy',
                             'provider behavior', 'fresh-target research']}
    def check(name, condition):
        result['checks'].append({'name': name, 'passed': bool(condition)})
        assert condition, name
    try:
        from engagement_network import NetworkGate, NetworkDenied
        from engagement_lease_owner import OwnedProcess
        from research_environment import inspect_profile
        hits = []
        bodies = []
        class Receiver(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                hits.append(self.path)
                if self.path == '/redirect':
                    self.send_response(302)
                    self.send_header('Location', 'http://denied.invalid/no')
                    self.end_headers()
                else:
                    self.send_response(200); self.end_headers(); self.wfile.write(b'allowed')
            def log_message(self, *_):
                pass
            def do_POST(self):
                bodies.append(self.rfile.read(int(self.headers['Content-Length'])))
                self.send_response(200); self.end_headers(); self.wfile.write(b'accepted')
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Receiver)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with tempfile.TemporaryDirectory(prefix='environment-e2e-') as name:
                root = Path(name); active = [True]
                port = server.server_port
                routes = [{'protocol': 'http', 'host': '127.0.0.1', 'port': port,
                           'address_policy': {'public_only': False, 'cidrs': ['127.0.0.1/32']}}]
                gate = NetworkGate(routes, lambda: active[0], maximum_bytes=4096, dispatch_guard=nullcontext)
                good = f'http://127.0.0.1:{port}/ok'
                response = gate.fetch(good)
                check('admitted receiver actually observed request', response['body'] == b'allowed' and hits == ['/ok'])
                for label, url in [('denied host', 'http://denied.invalid/no'),
                                   ('userinfo', f'http://user:pass@127.0.0.1:{port}/no'),
                                   ('redirect', f'http://127.0.0.1:{port}/redirect')]:
                    before = len(hits)
                    try: gate.fetch(url)
                    except NetworkDenied: pass
                    else: raise AssertionError(label)
                    check(label + ' denied without forbidden receiver effect', len(hits) == before + (label == 'redirect'))
                public = NetworkGate([{**routes[0], 'address_policy': {'public_only': True, 'cidrs': []}}], lambda: True, dispatch_guard=nullcontext)
                try: public.fetch(good)
                except NetworkDenied: pass
                else: raise AssertionError('private resolution accepted')
                check('address class checked before connect', hits.count('/ok') == 1)
                public.close()
                endpoint = root / 'proxy.sock'
                gate.serve(endpoint)
                with socket.socket(socket.AF_UNIX) as peer:
                    peer.connect(str(endpoint)); peer.sendall(f'GET {good} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n\r\n'.encode())
                    reply = b''
                    while chunk := peer.recv(4096): reply += chunk
                check('ordinary HTTP proxy reaches real receiver', b'200' in reply and reply.endswith(b'allowed'))
                with socket.socket(socket.AF_UNIX) as peer:
                    peer.connect(str(endpoint))
                    peer.sendall(f'POST {good} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nContent-Length: 6\r\n\r\nab'.encode())
                    time.sleep(.05)
                    try: peer.sendall(b'cdef')
                    except BrokenPipeError: pass
                    reply = b''
                    while chunk := peer.recv(4096): reply += chunk
                check('fragmented request body reaches receiver completely', bodies == [b'abcdef'] and reply.endswith(b'accepted'))
                active[0] = False
                before = len(hits)
                try: gate.fetch(good)
                except NetworkDenied: pass
                else: raise AssertionError('revoked route accepted')
                check('revoked generation denies subsequent effect', len(hits) == before)
                time.sleep(.1); active[0] = True
                try: gate.fetch(good)
                except NetworkDenied: pass
                else: raise AssertionError('retired route revived')
                check('retired network capability cannot revive', len(hits) == before)
                gate.close()
                check('proxy endpoint removed on cleanup', not endpoint.exists())
                replaced = NetworkGate(routes, lambda: True, dispatch_guard=nullcontext)
                replaced.serve(endpoint); endpoint.unlink(); endpoint.write_text('unrelated')
                try: replaced.close()
                except NetworkDenied: pass
                else: raise AssertionError('replaced socket path was treated as owned')
                check('socket cleanup preserves replaced filesystem object', endpoint.read_text() == 'unrelated')
                endpoint.unlink()

                command = [sys.executable, '-c', 'import time; time.sleep(60)']
                owner = OwnedProcess(command, lease_seconds=0.6, maximum_lease_seconds=2)
                owner.start()
                check('actual owned process starts', owner.readback()['running'])
                time.sleep(0.25); owner.renew(0.8); time.sleep(0.45)
                check('renewal extends only worker lifetime', owner.readback()['running'])
                owner.revoke()
                check('revocation observes process exit', not owner.readback()['running'])
                try: owner.renew(1)
                except RuntimeError: pass
                else: raise AssertionError('retired owner revived')
                check('retirement cannot renew', not owner.readback()['running'])
                expired = OwnedProcess(command, lease_seconds=0.25, maximum_lease_seconds=1)
                expired.start(); time.sleep(0.6)
                check('unrenewed local owner expires', not expired.readback()['running'])
                expired.revoke()
                # Parent loss is tested in a separate process so EOF is a real OS event.
                launcher = ('import sys,time; sys.path.insert(0,sys.argv[1]); '
                            'from engagement_lease_owner import OwnedProcess; '
                            'p=OwnedProcess([sys.executable,"-c","import time;time.sleep(60)"],lease_seconds=20,maximum_lease_seconds=20); '
                            'p.start(); print(p.readback()["pid"],flush=True); time.sleep(60)')
                parent = subprocess.Popen([sys.executable, '-c', launcher, str(REPO/'tools')], stdout=subprocess.PIPE, text=True)
                child_pid = int(parent.stdout.readline()); parent.kill(); parent.wait(); parent.stdout.close()
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    try: os.kill(child_pid, 0)
                    except ProcessLookupError: break
                    time.sleep(.05)
                try: os.kill(child_pid, 0)
                except ProcessLookupError: gone = True
                else: gone = False
                check('controller loss stops owned process', gone)

                profile = {'kind': 'research-environment-profile-v2', 'transport': 'docker',
                           'docker_binary': '/nonexistent/oslit-docker', 'docker_endpoint': 'unix:///nonexistent/docker.sock',
                           'daemon_id': None, 'image_id': 'sha256:'+'0'*64, 'platform': 'linux/arm64',
                           'uid': os.getuid() or 1000, 'gid': os.getgid(), 'ssh': None}
                preflight = inspect_profile(profile)
                check('offline inspect reports missing binary without daemon contact', preflight['status'] == 'unavailable' and preflight['contacted_environment'] is False)
        finally:
            server.shutdown(); server.server_close(); thread.join()
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
