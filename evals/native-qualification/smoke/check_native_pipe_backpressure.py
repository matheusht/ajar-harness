#!/usr/bin/env python3
"""Public native pipe workflow: an unresponsive peer cannot hold admission forever."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'tools'))

def run():
    from native_runtime_transport import RuntimeError, Transport
    with tempfile.TemporaryDirectory() as directory:
        transport=Transport([sys.executable,'-c','import time;time.sleep(30)'],{},directory,lambda frame:None)
        failures=[];done=threading.Event()
        def send():
            try:transport.send({'method':'fixture','params':{'payload':'x'*500000}})
            except RuntimeError as error:failures.append(str(error))
            finally:done.set()
        worker=threading.Thread(target=send,daemon=True);worker.start()
        started=time.monotonic();bounded=done.wait(6)
        if not bounded:transport.process.kill()
        closed=transport.close();worker.join(timeout=1)
        assert bounded and failures==['native_write_timeout'], ('unbounded native pipe write',failures)
        assert closed['process_exited']
        return {'status':'passed','evidence':'actual_unresponsive_pipe_peer','write_seconds':round(time.monotonic()-started,2),'failure':failures[0],'close':closed}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args();result=run()
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status']}))
