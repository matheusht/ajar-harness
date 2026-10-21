#!/usr/bin/env python3
"""Independent exact-producer stop owner for one prepared native run."""
import json
import os
from pathlib import Path
import select
import stat
import sys
import time

from native_run import snapshot, stop_producers, stop_reason
from producer_stop import Producers


def main():
    if len(sys.argv)!=7: return 64
    lifetime_fd,ready_fd=map(int,sys.argv[1:3])
    manifest,state=Path(sys.argv[3]),Path(sys.argv[4])
    producers=Producers(manifest,None if sys.argv[5]=='-' else sys.argv[5],
                        None if sys.argv[6]=='-' else sys.argv[6])
    record=snapshot(state)
    if (record['manifest_sha256']!=producers.digest or record['nonce']!=producers.manifest['nonce'] or
            record['ids']!=[p['id'] for p in producers.items]):return 65

    def event(kind,data):
        fd=os.open(state/'stop-owner.jsonl',os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as stream:
            info=os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode & 0o077:
                raise ValueError('native_stop_owner_log_permissions')
            stream.write(json.dumps({'kind':kind,'data':data,'monotonic':time.monotonic()},sort_keys=True)+'\n')
            stream.flush();os.fsync(stream.fileno())

    event('stop_owner_armed',{'pid':os.getpid(),'ids':record['ids'],'manifest_sha256':producers.digest})
    if os.write(ready_fd,b'1')!=1:return 65
    os.close(ready_fd)
    while True:
        reason=stop_reason(state)
        if reason:break
        if select.select([lifetime_fd],[],[],.1)[0]:
            if not os.read(lifetime_fd,4096):
                reason='connect_exited'
                break
    evidence_ok=True
    def record(kind,data):
        nonlocal evidence_ok
        try:event(kind,data)
        except Exception:evidence_ok=False
    record('stop_owner_triggered',{'reason':reason})
    stopped=stop_producers(state,producers,record,reason,lambda:evidence_ok)
    record('stop_owner_finished',{'producers_verified_stopped':stopped})
    return 0 if stopped else 66


if __name__=='__main__':raise SystemExit(main())
