#!/usr/bin/env python3
"""Exercise guardian control through real pipes; optionally prove PID 1 in local Docker.

Repeatable protocol-only run:
  python3 evals/native-qualification/smoke/check_container_guardian_e2e.py --output /tmp/guardian.json

Actual Linux PID-1/reaping run additionally needs --endpoint unix:///... --image-id sha256:...
The image must be locally installed and contain python3. No provider or target is contacted.
Write these checks before implementation; protocol checks alone are not container evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import sys
import time
import uuid

REPO = Path(__file__).resolve().parents[3]
OWNER = REPO / 'tools/engagement_lease_owner.py'
sys.path.insert(0, str(REPO / 'tools'))


class Peer:
    def __init__(self, command, nonce, maximum):
        self.nonce, self.maximum, self.sequence = nonce, maximum, -1
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, start_new_session=True)

    def frame(self, duration, *, nonce=None, sequence=None, expires=None):
        return {'kind': 'container-lease-v1', 'nonce': self.nonce if nonce is None else nonce,
                'sequence': self.sequence + 1 if sequence is None else sequence,
                'seconds': duration, 'expires_at_unix': time.time() + duration if expires is None else expires}

    def send(self, frame):
        self.process.stdin.write(json.dumps(frame).encode() + b'\n')
        self.process.stdin.flush()

    def ack(self, frame):
        self.send(frame)
        if not select.select([self.process.stdout], [], [], 3)[0]:
            raise AssertionError('guardian acknowledgment timeout')
        line = self.process.stdout.readline(4097)
        expected = {'kind': 'container-lease-v1', 'nonce': self.nonce,
                    'sequence': frame['sequence'], 'accepted': True,
                    'expires_at_unix': frame['expires_at_unix']}
        if json.loads(line) != expected:
            raise AssertionError('guardian acknowledgment identity changed')
        self.sequence = frame['sequence']

    def exited(self, timeout=2):
        try:
            self.process.wait(timeout=timeout)
            return True
        except subprocess.TimeoutExpired:
            return False

    def close(self):
        if self.process.poll() is None:
            try:
                self.process.stdin.close()
            except OSError:
                pass
            if not self.exited():
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self.process.wait(timeout=2)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            if not stream.closed:
                try:
                    stream.close()
                except OSError:
                    pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--endpoint')
    parser.add_argument('--image-id')
    args = parser.parse_args()
    if bool(args.endpoint) != bool(args.image_id):
        parser.error('--endpoint and --image-id must be supplied together')
    result = {'kind': 'container-guardian-e2e-v1', 'classification': 'real_local_process_protocol',
              'checks': [], 'provider_calls': 0, 'external_target_calls': 0,
              'source_sha256': {str(path.relative_to(REPO)): hashlib.sha256(path.read_bytes()).hexdigest()
                               for path in (Path(__file__), OWNER)},
              'container_pid1_verified': False, 'unverified': ['Docker PID 1', 'adopted child reaping',
                'worker UID isolation', 'SSH transport', 'native model host', 'research qualification']}
    peers, containers = [], []
    docker = None

    def check(name, value):
        result['checks'].append({'name': name, 'passed': bool(value)})
        if not value:
            raise AssertionError(name)

    def peer(maximum=2):
        nonce = uuid.uuid4().hex
        value = Peer([sys.executable, '-I', '-S', str(OWNER), 'container-watch', nonce, str(maximum)],
                     nonce, maximum)
        peers.append(value)
        return value

    def call(*arguments, required=True):
        response = subprocess.run([docker, '--host', args.endpoint, *arguments],
                                  capture_output=True, text=True, timeout=15)
        if required and response.returncode:
            raise AssertionError('Docker fixture command failed: ' + arguments[0])
        return response

    try:
        p = peer(.4)
        check('unconfigured guardian expires cleanly', p.exited(1.2) and p.process.returncode == 0)

        p = peer(); p.ack(p.frame(.4))
        check('initial acknowledged lease expires without renewal', p.exited(1.2))

        p = peer(); p.ack(p.frame(.5)); time.sleep(.25); p.ack(p.frame(.7)); time.sleep(.4)
        check('valid renewal keeps owner alive past initial expiry', p.process.poll() is None)
        check('renewed owner still has a finite expiry', p.exited(1))

        p = peer(); p.ack(p.frame(1)); p.process.stdin.close()
        check('control channel EOF ends the guardian', p.exited(1))

        p = peer(); p.ack(p.frame(1)); p.send({'kind': 'container-lease-v1', 'nonce': p.nonce,
                                            'sequence': p.sequence + 1, 'revoke': True})
        check('explicit revocation ends the guardian', p.exited(1))

        p = peer(); p.ack(p.frame(.4)); p.process.stdin.write(b'{"seconds":'); p.process.stdin.flush()
        check('partial frame cannot block the expiry clock', p.exited(1.2))

        p = peer(); p.ack(p.frame(1)); p.send(p.frame(1, nonce=uuid.uuid4().hex))
        check('a different owner nonce is rejected', p.exited(1) and p.process.returncode != 0)

        p = peer(); initial = p.frame(1); p.ack(initial); p.send(initial)
        check('replayed renewal sequence is rejected', p.exited(1) and p.process.returncode != 0)

        p = peer(); p.ack(p.frame(1)); p.send(p.frame(3))
        check('renewal above the fixed maximum is rejected', p.exited(1) and p.process.returncode != 0)

        for name, change in (('skipped sequence', {'sequence': 3}),
                             ('boolean duration', {'seconds': True}),
                             ('nonfinite expiry', {'expires_at_unix': float('inf')}),
                             ('unexpected field', {'command': ['unsafe']})):
            p = peer(); p.ack(p.frame(1)); p.send({**p.frame(1), **change})
            check(name + ' is rejected', p.exited(1) and p.process.returncode != 0)

        p = peer(); p.ack(p.frame(1)); p.send(p.frame(.5, expires=time.time() - 1))
        check('expired queued renewal is not rebased on receipt', p.exited(1) and p.process.returncode != 0)

        p = peer(3); p.ack(p.frame(3)); delayed = p.frame(1.2); time.sleep(.7)
        delivered = time.monotonic(); p.ack(delayed)
        check('live queued renewal retains its original absolute expiry', p.exited(.9))
        result['delayed_renewal_seconds_after_delivery'] = round(time.monotonic() - delivered, 3)

        p = peer(); p.ack(p.frame(1))
        try:
            p.process.stdin.write(b'x' * 20000); p.process.stdin.flush()
        except BrokenPipeError:
            pass
        check('oversized input fails closed without blocking', p.exited(1) and p.process.returncode != 0)

        if args.endpoint:
            from engagement_lease_owner import guardian_command
            docker = shutil.which('docker')
            check('explicit local daemon selected', bool(docker) and args.endpoint.startswith('unix://'))
            image, = json.loads(call('image', 'inspect', args.image_id).stdout)
            check('Linux image pinned by complete content identity', image['Id'] == args.image_id and image['Os'] == 'linux')
            result['docker'] = {'daemon_id': call('info', '--format', '{{.ID}}').stdout.strip(),
                                'image_id': image['Id'], 'platform': image['Os'] + '/' + image['Architecture']}
            nonce = uuid.uuid4().hex
            command = guardian_command(nonce, 30)
            cid = call('container', 'create', '--name', 'oslit-guardian-check-' + nonce,
                '--label', 'io.oslit.guardian-check=' + nonce, '--network', 'none', '--cap-drop', 'ALL',
                '--security-opt', 'no-new-privileges=true', '--pids-limit', '32', '--memory', '268435456',
                '--memory-swap', '268435456', '--cpus', '1', '--user', '0:0', '--init=false', '--interactive',
                '--read-only', '--log-driver', 'none', '--restart', 'no', '--no-healthcheck',
                '--tmpfs', '/work:rw,nosuid,nodev,size=16777216,uid=1000,gid=1000,mode=0700',
                '--entrypoint', command[0], args.image_id, *command[1:]).stdout.strip()
            containers.append((cid, nonce))
            p = Peer([docker, '--host', args.endpoint, 'container', 'start', '--attach', '--interactive', cid], nonce, 30)
            peers.append(p); p.ack(p.frame(30))
            info, = json.loads(call('container', 'inspect', cid).stdout)
            check('guardian is actual root PID 1 without Docker init', info['Config']['User'] == '0:0'
                  and info['HostConfig']['Init'] is False and info['Path'] == command[0])
            probe = r'''import json,os,signal,time
from pathlib import Path
checks={"worker_nonroot":os.getuid()==1000}
guardian=Path("/proc/1/status").read_text()
checks["effective_guardian_root"]=next(line for line in guardian.splitlines() if line.startswith("Uid:")).split()[1:]==["0"]*4
checks["effective_guardian_no_capabilities"]="CapEff:\t0000000000000000" in guardian
checks["effective_guardian_command"]="_container_watch" in Path("/proc/1/cmdline").read_bytes().decode()
for name,operation in [("guardian_signal_denied",lambda:os.kill(1,signal.SIGTERM)),
                       ("guardian_control_fd_denied",lambda:os.open("/proc/1/fd/0",os.O_WRONLY))]:
    try:operation()
    except PermissionError:checks[name]=True
    else:checks[name]=False
for batch in range(25):
    for i in range(5):
        child=os.fork()
        if child==0:
            if os.fork()==0:os._exit(0)
            os._exit(0)
        os.waitpid(child,0)
    time.sleep(.06)
time.sleep(.2)
zombies=[]
for status in Path("/proc").glob("[0-9]*/status"):
    try:
        data=status.read_text()
        if "State:\tZ" in data:zombies.append(status.parent.name)
    except FileNotFoundError:pass
checks["adopted_children_reaped"]=not zombies
print(json.dumps({"checks":checks,"zombies":zombies},sort_keys=True))
assert all(checks.values()),checks
'''
            observation = json.loads(call('container', 'exec', '--user', '1000:1000', cid,
                                           command[0], '-I', '-S', '-c', probe).stdout)
            result['pid1_probe'] = observation
            for name, passed in observation['checks'].items():
                check(name, passed)
            # Arbitrary exec stdin belongs to that exec, not the guardian attach stream.
            forged = p.frame(30, sequence=p.sequence + 1)
            response = subprocess.run([docker, '--host', args.endpoint, 'container', 'exec', '--interactive',
                '--user', '1000:1000', cid, command[0], '-I', '-S', '-c',
                'import sys;sys.stdout.write(sys.stdin.readline())'], input=json.dumps(forged) + '\n',
                capture_output=True, text=True, timeout=5)
            check('worker exec stream is independent from renewal attach', response.returncode == 0
                  and json.loads(response.stdout) == forged)
            p.ack(p.frame(.5))
            check('guardian expiry ends its Docker attach stream', p.exited(2))
            info, = json.loads(call('container', 'inspect', cid).stdout)
            check('guardian expiry stops the entire container', info['State']['Running'] is False)
            result['container_pid1_verified'] = True
            result['classification'] = 'real_local_process_and_docker_pid1'
            result['unverified'] = ['SSH transport', 'native model host', 'research qualification']
        result['passed'] = True
    except Exception as error:
        result.update(passed=False, error=type(error).__name__ + ': ' + str(error))
    finally:
        process_cleanup = []
        for p in peers:
            try:
                p.close()
                process_cleanup.append({'pid': p.process.pid, 'exited': p.process.poll() is not None})
            except Exception:
                process_cleanup.append({'pid': p.process.pid, 'exited': False})
        result['process_cleanup'] = process_cleanup
        if any(not row['exited'] for row in process_cleanup):
            result['passed'] = False
        cleanup = []
        for cid, nonce in containers:
            try:
                if call('info', '--format', '{{.ID}}').stdout.strip() != result['docker']['daemon_id']:
                    raise AssertionError('cleanup daemon identity changed')
                info, = json.loads(call('container', 'inspect', cid).stdout)
                if info['Id'] != cid or info['Config']['Labels'].get('io.oslit.guardian-check') != nonce:
                    raise AssertionError('cleanup container identity changed')
                response = call('container', 'rm', '--force', cid, required=False)
                absent = call('container', 'inspect', cid, required=False).returncode != 0
                cleanup.append({'container_id': cid, 'removed': response.returncode == 0, 'absent': absent})
            except Exception:
                cleanup.append({'container_id': cid, 'removed': False, 'absent': False})
        result['cleanup'] = cleanup
        if any(not row['removed'] or not row['absent'] for row in cleanup):
            result['passed'] = False
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'passed': result['passed'], 'checks': len(result['checks']), 'output': str(args.output)}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
