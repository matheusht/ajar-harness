#!/usr/bin/env python3
"""One CONNECT-owned native run and transport-neutral final-send guard."""
import argparse
from contextlib import contextmanager
import fcntl
import json
import math
import os
from pathlib import Path
import select
import stat
import subprocess
import sys
import time
import uuid


class RunStopped(RuntimeError):
    pass


STOP_LOCK_WAIT_SECONDS = 35


def _directory(path):
    path = Path(path).absolute()
    if path.is_symlink(): raise ValueError('native_run_directory_symlink')
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o077: raise ValueError('native_run_directory_permissions')
    return path.resolve()


@contextmanager
def _lock(path, name='dispatch.lock', timeout=20, with_fd=False):
    path = _directory(path)
    fd = os.open(path/name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('native_run_lock_permissions')
        deadline=time.monotonic()+timeout
        while True:
            try:fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB);break
            except BlockingIOError:
                if time.monotonic()>=deadline:
                    raise RunStopped('native_run_stop_lock_unavailable' if name=='stop.lock' else 'native_run_dispatch_lock_unavailable')
                time.sleep(.01)
        yield (path,fd) if with_fd else path
    finally: os.close(fd)


def _write_once(path, name, value):
    try: fd = os.open(path/name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError: return
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, sort_keys=True); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    directory = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(directory)
    finally: os.close(directory)


def _write_atomic_once(path, name, value):
    # A killed writer must never leave an empty STOPPING or REVOKED marker.
    temporary=path/('.'+name+'-'+uuid.uuid4().hex)
    try:
        fd=os.open(temporary,os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as stream:
            json.dump(value,stream,sort_keys=True);stream.write('\n');stream.flush();os.fsync(stream.fileno())
        os.link(temporary,path/name)
        directory=os.open(path,os.O_RDONLY | os.O_DIRECTORY)
        try:os.fsync(directory)
        finally:os.close(directory)
    finally:temporary.unlink(missing_ok=True)


def snapshot(path):
    path = _directory(path)
    fd = os.open(path/'RUN.json', os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size>32768:
            raise ValueError('native_run_state_permissions')
        return json.load(stream)


def active(path):
    try:
        path = _directory(path); state = snapshot(path)
        return (path/'READY').exists() and time.monotonic()<state['deadline_monotonic'] and not any(
            (path/name).exists() for name in ('STOP_REQUEST','STOPPING','REVOKED','UNSAFE'))
    except (OSError,ValueError,KeyError): return False


@contextmanager
def dispatch_guard(state_dir):
    with _lock(state_dir) as path:
        if not active(path): raise RunStopped('native_run_dispatch_closed')
        yield


def request_stop(state_dir, reason='operator_stop'):
    if not isinstance(reason,str) or not 1<=len(reason)<=128: raise ValueError('native_run_stop_reason')
    with _lock(state_dir) as path:
        if not (path/'REVOKED').exists() and not (path/'UNSAFE').exists():
            _write_once(path,'STOP_REQUEST',{'reason':reason,'monotonic':time.monotonic()})


def prepare(state_dir, manifest_path, producers, timeout_seconds, control_paths=()):
    if not isinstance(timeout_seconds,(int,float)) or not math.isfinite(timeout_seconds) or not 0<timeout_seconds<=86400:
        raise ValueError('native_run_duration')
    with _lock(state_dir) as path:
        if any((path/name).exists() for name in ('RUN.json','REVOKED','UNSAFE','STOPPING','STOP_REQUEST')):
            raise ValueError('native_run_cannot_restart')
        controls = (path,Path(manifest_path).resolve(),*(Path(p).resolve() for p in control_paths))
        mount_proof = []
        for item in producers.items:
            info = producers.inspect(item)
            for mount in info['Mounts']:
                source = Path(mount['Source']).resolve()
                if any(p==source or source in p.parents for p in controls):
                    raise ValueError('native_run_control_exposed_by_producer_mount')
            mount_proof.append({'id':item['id'],'binding':item['binding'],'control_paths_outside_producer_mounts':True})
        state = {'version':1,'manifest_sha256':producers.digest,'ids':[p['id'] for p in producers.items],
                 'nonce':producers.manifest['nonce'],'deadline_monotonic':time.monotonic()+timeout_seconds,
                 'created_monotonic':time.monotonic(),'mount_proof':mount_proof}
        _write_once(path,'RUN.json',state)
        return state


def mark_ready(state_dir):
    with _lock(state_dir) as path:
        if any((path/n).exists() for n in ('STOP_REQUEST','STOPPING','REVOKED','UNSAFE')):
            raise RunStopped('native_run_stopped_before_ready')
        _write_once(path,'READY',{'monotonic':time.monotonic()})


def stop_reason(state_dir):
    with _lock(state_dir) as path:
        if (path/'STOP_REQUEST').exists():
            try:
                fd=os.open(path/'STOP_REQUEST',os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(fd) as stream:
                    info=os.fstat(stream.fileno())
                    if not stat.S_ISREG(info.st_mode) or info.st_size>32768:raise ValueError('invalid_stop_record')
                    reason=json.load(stream)['reason']
                    if not isinstance(reason,str) or not 1<=len(reason)<=128:raise ValueError('invalid_stop_reason')
                    return reason
            except (OSError,ValueError,KeyError,TypeError):
                return 'stop_request_unreadable'
        if time.monotonic()>=snapshot(path)['deadline_monotonic']: return 'monotonic_timeout'
        return None


def begin_stop(state_dir, reason):
    with _lock(state_dir) as path:
        _write_once(path,'STOP_REQUEST',{'reason':reason,'monotonic':time.monotonic()})
        if not (path/'STOPPING').exists():
            _write_atomic_once(path,'STOPPING',{'reason':reason,'monotonic':time.monotonic()})


def finish_stop(state_dir, stopped, proof=None):
    with _lock(state_dir) as path:
        if not (path/'STOPPING').exists(): raise ValueError('native_run_stop_not_started')
        if (path/'REVOKED').exists() or (path/'UNSAFE').exists():
            raise ValueError('native_run_stop_already_terminal')
        value={'producers_verified_stopped':bool(stopped),'monotonic':time.monotonic()}
        if stopped:
            state=snapshot(path)
            if (not isinstance(proof,dict) or proof.get('manifest_sha256')!=state['manifest_sha256']
                    or proof.get('ids')!=state['ids'] or not isinstance(proof.get('frozen_monotonic'),(int,float))
                    or not math.isfinite(proof['frozen_monotonic'])
                    or proof['frozen_monotonic']>value['monotonic']):
                raise ValueError('native_run_stop_proof_invalid')
            value.update(proof)
        _write_atomic_once(path,'REVOKED' if stopped else 'UNSAFE',value)


def start_producers(state_dir, producers, fail_after=None, hold_dir=None):
    with _lock(state_dir, 'stop.lock', 600, with_fd=True) as (path,lock_fd):
        if stop_reason(state_dir): raise RunStopped('native_stop_before_start')
        marker=path/'START_IN_FLIGHT'
        def record_start(item,phase):
            if phase=='begin':
                if marker.exists():raise RunStopped('native_start_uncertain')
                _write_once(path,'START_IN_FLIGHT',{'id':item['id'],'monotonic':time.monotonic()})
            else:
                marker.unlink()
                directory=os.open(path,os.O_RDONLY | os.O_DIRECTORY)
                try:os.fsync(directory)
                finally:os.close(directory)
        producers.start(fail_after, lambda: stop_reason(state_dir), hold_dir, lock_fd, record_start)
        if stop_reason(state_dir): raise RunStopped('native_stop_during_start')
        mark_ready(state_dir)


def stop_producers(state_dir, producers, event, reason, evidence_ok=lambda: True):
    # The process that wins this lock owns the entire stop and terminal marker.
    request_stop(state_dir,reason)  # Close final dispatch before waiting for a start CLI that may outlive Python.
    try:
        with _lock(state_dir, 'stop.lock', STOP_LOCK_WAIT_SECONDS):
            path = _directory(state_dir)
            if (path/'UNSAFE').exists(): return False
            if (path/'REVOKED').exists():
                try: return json.loads((path/'REVOKED').read_text())['producers_verified_stopped'] is True
                except (OSError,ValueError,KeyError,TypeError): return False
            uncertain_start=(path/'START_IN_FLIGHT').exists()
            begin_stop(path, reason)
            event_failed=False
            def record(kind,data):
                nonlocal event_failed
                try:event(kind,data)
                except Exception:event_failed=True
            try: frozen=producers.freeze(record)
            except Exception:
                finish_stop(path, False)
                return False
            try: state=snapshot(path)
            except (OSError,ValueError,KeyError,TypeError):state={}
            sealed=(state.get('manifest_sha256')==producers.digest and
                    state.get('ids')==[item['id'] for item in producers.items])
            if uncertain_start or event_failed or not evidence_ok() or not sealed or not isinstance(frozen,dict):
                finish_stop(path, False)
                return False
            finish_stop(path, True, {'manifest_sha256':frozen['manifest_sha256'],
                                     'ids':frozen['ids'],
                                     'frozen_monotonic':frozen['monotonic']})
            return True
    except RunStopped as error:
        if str(error)!='native_run_stop_lock_unavailable':raise
        # An inherited CLI may hold stop.lock indefinitely. Preserve the closed
        # dispatch gate and report uncertainty without claiming a producer freeze.
        with _lock(state_dir) as path:
            if (path/'REVOKED').exists():
                try:return json.loads((path/'REVOKED').read_text())['producers_verified_stopped'] is True
                except (OSError,ValueError,KeyError,TypeError):return False
            if (path/'UNSAFE').exists():return False
            if not (path/'STOPPING').exists():
                _write_atomic_once(path,'STOPPING',{'reason':reason,'monotonic':time.monotonic()})
            _write_atomic_once(path,'UNSAFE',{'producers_verified_stopped':False,'stop_lock_timeout':True,'monotonic':time.monotonic()})
            return False


def arm_stop_owner(state_dir, manifest, fault_id=None, kill_fault_id=None):
    lifetime_read,lifetime_write=os.pipe();ready_read,ready_write=os.pipe()
    process=None
    try:
        command=[sys.executable,str(Path(__file__).with_name('_native_stop_owner.py')),
                 str(lifetime_read),str(ready_write),str(manifest),str(state_dir),
                 fault_id or '-',kill_fault_id or '-']
        process=subprocess.Popen(command,pass_fds=(lifetime_read,ready_write),
                                 stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                                 start_new_session=True)
        os.close(lifetime_read);lifetime_read=-1
        os.close(ready_write);ready_write=-1
        if not select.select([ready_read],[],[],10)[0] or os.read(ready_read,1)!=b'1' or process.poll() is not None:
            raise RunStopped('native_stop_owner_unavailable')
        return process,lifetime_write
    except Exception:
        os.close(lifetime_write)
        if process is not None:
            try:process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill();process.wait(timeout=2)
        raise
    finally:
        if lifetime_read>=0:os.close(lifetime_read)
        if ready_write>=0:os.close(ready_write)
        os.close(ready_read)


def _armed_stop_owner_pid(state_dir):
    path=_directory(state_dir)
    log=path/'stop-owner.jsonl'
    if not log.exists():return None
    fd=os.open(log,os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode & 0o077 or info.st_size>65536:
            raise RunStopped('native_stop_owner_identity_unavailable')
        try:armed=json.loads(stream.readline())
        except (ValueError,TypeError):raise RunStopped('native_stop_owner_identity_unavailable')
    pid=armed.get('data',{}).get('pid') if armed.get('kind')=='stop_owner_armed' else None
    if type(pid) is not int or pid<=0:raise RunStopped('native_stop_owner_identity_unavailable')
    return pid


def _wait_stop_owner(state_dir, expected_pid=None):
    pid=_armed_stop_owner_pid(state_dir)
    if expected_pid is not None and pid!=expected_pid:raise RunStopped('native_stop_owner_identity_mismatch')
    if pid is None:
        if (_directory(state_dir)/'READY').exists():raise RunStopped('native_stop_owner_identity_unavailable')
        return
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        try:os.kill(pid,0)
        except ProcessLookupError:return
        time.sleep(.02)
    raise RunStopped('native_stop_owner_cleanup_unresolved')


class NativeRun:
    """Thin launcher for the CONNECT watcher and its run-scoped stop owner."""
    def __init__(self, manifest, state_dir, timeout_seconds, proxy_args):
        self.manifest=Path(manifest);self.state_dir=Path(state_dir);self.process=None;self.producers=None
        self.argv=[sys.executable,str(Path(__file__).resolve().parent.parent/'v2_connect.py'),*proxy_args,
                   '--producer-manifest',str(self.manifest),'--native-run-state',str(self.state_dir),
                   '--native-run-duration',str(timeout_seconds),'--native-owner-pid',str(os.getpid())]

    def start(self, timeout_seconds=20):
        if self.process is not None: raise RuntimeError('native_run_already_started')
        from producer_stop import Producers
        self.producers=Producers(self.manifest)
        self.process=subprocess.Popen(self.argv,stdout=subprocess.PIPE,text=True)
        try:
            data=bytearray();deadline=time.monotonic()+timeout_seconds
            while b'\n' not in data:
                remaining=deadline-time.monotonic()
                if remaining<=0 or not select.select([self.process.stdout],[],[],remaining)[0]:raise RuntimeError('native_run_startup_timeout')
                chunk=os.read(self.process.stdout.fileno(),4096)
                if not chunk or len(data)+len(chunk)>16384:raise RuntimeError('native_run_startup_failed')
                data.extend(chunk)
            self.info=json.loads(data.partition(b'\n')[0]);state=snapshot(self.state_dir)
            return {'watcher_pid':self.process.pid,'proxy_info':self.info,'manifest_sha256':state['manifest_sha256'],'ids':state['ids']}
        except Exception as error:
            outcome=self.close()
            raise RuntimeError('native_run_startup_failed:'+outcome['status']) from error

    def close(self):
        if self.process is None:return {'status':'not_started'}
        if self.process.poll() is None:
            try:
                request_stop(self.state_dir,'owner_close')
                self.process.wait(timeout=45)
            except Exception as error:
                self.close_result={'status':'unresolved','child_alive':self.process.poll() is None}
                raise RunStopped('native_run_stop_unresolved') from error
        state=_directory(self.state_dir)
        if not any((state/n).exists() for n in ('REVOKED','UNSAFE','STARTUP_CLOSED')):
            # Only the observed exited child's parent takes over; never race a live watcher.
            def event(kind,data):
                fd=os.open(state/'parent-stop.jsonl',os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW,0o600)
                with os.fdopen(fd,'w') as stream:
                    stream.write(json.dumps({'kind':kind,'data':data,'monotonic':time.monotonic()})+'\n')
                    stream.flush();os.fsync(stream.fileno())
            event('parent_stop_takeover',{'child_pid':self.process.pid,'returncode':self.process.returncode})
            if (state/'RUN.json').exists():
                if not stop_producers(state,self.producers,event,'child_exited_without_stop'):
                    self.close_result={'status':'unsafe','child_alive':False,'returncode':self.process.returncode}
                    raise RunStopped('native_run_parent_stop_unsafe')
            else:
                with _lock(state,'stop.lock',600):
                    begin_stop(state,'child_exited_before_prepare')
                    try:self.producers.freeze(event)
                    except Exception as error:
                        finish_stop(state,False)
                        self.close_result={'status':'unsafe','child_alive':False,'returncode':self.process.returncode}
                        raise RunStopped('native_run_parent_stop_unsafe') from error
                    with _lock(state):_write_once(state,'STARTUP_CLOSED',{'producers_verified_stopped':True,'monotonic':time.monotonic()})
        status='stopped' if (state/'REVOKED').exists() else ('unsafe' if (state/'UNSAFE').exists() else ('closed_before_activation' if (state/'STARTUP_CLOSED').exists() else 'unresolved'))
        self.close_result={'status':status,'child_alive':False,'returncode':self.process.returncode}
        if status=='unresolved':raise RunStopped('native_run_stop_unresolved')
        _wait_stop_owner(state,self.info.get('stop_owner_pid') if hasattr(self,'info') else None)
        return self.close_result

    def __enter__(self): self.start();return self
    def __exit__(self,*_):
        if self.close()['status']=='unsafe':raise RunStopped('native_run_target_stop_unsafe')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--state-dir',type=Path,required=True)
    parser.add_argument('--timeout',type=float,required=True)
    parser.add_argument('proxy_args',nargs=argparse.REMAINDER)
    args=parser.parse_args();proxy_args=args.proxy_args[1:] if args.proxy_args[:1]==['--'] else args.proxy_args
    run=NativeRun(args.manifest,args.state_dir,args.timeout,proxy_args)
    try:
        print(json.dumps(run.start()),flush=True)
        returncode=run.process.wait()
    finally: outcome=run.close()
    return returncode if outcome['status'] in ('stopped','closed_before_activation') else (returncode or 1)


if __name__=='__main__': raise SystemExit(main())
