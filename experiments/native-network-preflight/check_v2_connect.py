#!/usr/bin/env python3
"""Owned TLS dummy E2E for opaque CONNECT; no Console or model access."""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import select
import socket
import socketserver
import sqlite3
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import uuid

HERE = Path(__file__).resolve().parent


def enable_orphan_reaping():
    if sys.platform != 'linux':
        return False
    import ctypes
    libc = ctypes.CDLL(None, use_errno=True)
    # PR_SET_CHILD_SUBREAPER adopts the owner's gateway without depending on PID 1.
    if libc.prctl(36, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'child_subreaper_unavailable')
    return True


def wait_gateway_exit(pid, subreaper, timeout=5):
    deadline = time.monotonic() + timeout
    while True:
        if subreaper:
            try:
                observed, status = os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                return {'exited': False, 'reason': 'gateway_not_adopted'}
            if observed == pid:
                return {'exited': True, 'reaped': True, 'exit_code': os.waitstatus_to_exitcode(status)}
        else:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return {'exited': True, 'reaped': False, 'exit_code': None}
        if time.monotonic() >= deadline:
            return {'exited': False, 'reason': 'gateway_exit_timeout'}
        time.sleep(.02)


class TLSHandler(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            with self.server.context.wrap_socket(self.request, server_side=True) as tls:
                data = tls.recv(4096)
                self.server.rows.append({"input_sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
                tls.sendall(b"owned-tls-response")
        except (ssl.SSLError, OSError):
            pass


class ByteCollector(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(3)
        try:
            data = self.request.recv(4096)
            self.server.rows.append(len(data))
            if data:
                self.request.sendall(b"ACK")
        except OSError:
            self.server.rows.append(0)


class HeldCollector(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(5)
        try:
            while True:
                data = self.request.recv(4096)
                if not data:
                    break
                self.server.rows.append({"payload": data.decode(), "monotonic": time.monotonic()})
                self.request.sendall(b"ACK")
        except OSError:
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.absolute()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    report = {"classification": "dummy TLS transport only", "provider_calls": 0,
        "checks": [], "commands": [], "processes": [],
        "limits": ["CONNECT authority only; TLS SNI/HTTP host/path not enforced", "no model/API-request/token/usage visibility"],
        "source_sha256": {n: hashlib.sha256((HERE / n).read_bytes()).hexdigest()
            for n in ["v2_connect.py", "tcp_relay.go", "check_v2_connect.py", "V2-TUNNEL-CHECKS.md"]}}
    processes = []

    def check(name, passed):
        report["checks"].append({"check": name, "passed": bool(passed)})

    with tempfile.TemporaryDirectory(prefix="lrh-owned-tls-") as temporary:
        root = Path(temporary)
        capability = "local_" + uuid.uuid4().hex
        capability_file = root / "capability"
        capability_file.write_text(capability)
        os.chmod(capability_file, 0o600)
        cert, key = root / "cert.pem", root / "key.pem"
        command = ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                   "-subj", "/CN=owned.fixture", "-addext", "subjectAltName=DNS:owned.fixture",
                   "-keyout", str(key), "-out", str(cert)]
        result = subprocess.run(command, capture_output=True, timeout=20)
        report["commands"].append({"argv": command, "returncode": result.returncode})
        assert result.returncode == 0
        server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), TLSHandler)
        server.daemon_threads = True
        server.rows, server.sni = [], []
        server.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server.context.load_cert_chain(cert, key)
        server.context.set_servername_callback(lambda sock, name, ctx: server.sni.append(name))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        collector = socketserver.ThreadingTCPServer(("127.0.0.1", 0), ByteCollector)
        collector.daemon_threads, collector.rows = True, []
        threading.Thread(target=collector.serve_forever, daemon=True).start()
        held = socketserver.ThreadingTCPServer(("127.0.0.1", 0), HeldCollector)
        held.daemon_threads, held.rows = True, []
        threading.Thread(target=held.serve_forever, daemon=True).start()
        auth = "Basic " + base64.b64encode(("run:" + capability).encode()).decode()

        def start(name, *, connections=4, byte_cap=32768, duration=120, dummy_port=None, cap_path=None):
            command = [sys.executable, str(HERE / "v2_connect.py"), "--state-dir", str(output / name),
                "--capability-file", str(cap_path or capability_file), "--max-connections", str(connections),
                "--max-bytes", str(byte_cap), "--duration", str(duration),
                "--dummy-port", str(dummy_port or server.server_address[1])]
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            processes.append(process)
            report["commands"].append({"argv": command})
            assert select.select([process.stdout], [], [], 5)[0]
            line = process.stdout.readline()
            startup = json.loads(line) if line else None
            if startup is None:
                process.wait(timeout=5)
            report["processes"].append({"pid": process.pid, "startup": startup, "state": name})
            return process, startup["port"] if startup else None

        def stop(process):
            if process.poll() is None:
                process.terminate()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=5)

        def connect(port, authority="opencode.ai:443", credential=auth, method="CONNECT"):
            connection = socket.create_connection(("127.0.0.1", port), timeout=5)
            connection.sendall((f"{method} {authority} HTTP/1.1\r\nHost: {authority}\r\nProxy-Authorization: {credential}\r\n\r\n").encode())
            response = bytearray()
            while not response.endswith(b"\r\n\r\n"):
                chunk = connection.recv(1)
                if not chunk:
                    break
                response.extend(chunk)
            return connection, bytes(response)

        def tls_request(port):
            connection, response = connect(port)
            if b" 200 " not in response:
                connection.close()
                return False
            context = ssl.create_default_context(cafile=cert)
            with context.wrap_socket(connection, server_hostname="owned.fixture") as tls:
                tls.sendall(b"owned-tls-input")
                return tls.recv(4096) == b"owned-tls-response"

        try:
            report['linux_child_subreaper'] = enable_orphan_reaping()
            loose = root / "loose-capability"
            loose.write_text(capability)
            os.chmod(loose, 0o644)
            rejected, rejected_port = start("loose-file", cap_path=loose)
            check("loose capability file refused", rejected_port is None and rejected.returncode != 0)
            linked = root / "linked-capability"
            linked.symlink_to(capability_file)
            rejected, rejected_port = start("symlink-file", cap_path=linked)
            check("symlink capability file refused", rejected_port is None and rejected.returncode != 0)
            process, port = start("count", connections=2)
            for header in [b"", b"CONNECT opencode.ai:443 HTTP/1.1\r\n"]:
                connection = socket.create_connection(("127.0.0.1", port), timeout=3)
                connection.sendall(header)
                connection.shutdown(socket.SHUT_WR)
                response = connection.recv(4096)
                connection.close()
                check("short header rejected with receipt", b" 403 " in response)
            for label, kwargs in [("wrong authority", {"authority": "outside.invalid:443"}),
                    ("IP literal", {"authority": "127.0.0.1:443"}),
                    ("wrong port", {"authority": "opencode.ai:444"}),
                    ("suffix", {"authority": "opencode.ai.outside.invalid:443"}),
                    ("method", {"method": "GET"}), ("auth", {"credential": "Basic wrong"})]:
                connection, response = connect(port, **kwargs)
                connection.close()
                check(label, b" 403 " in response)
            check("owned TLS certificate and bytes preserved", tls_request(port))
            check("SNI is opaque, not authority enforcement", server.sni == ["owned.fixture"])
            check("second context shares pool", tls_request(port))
            connection, response = connect(port)
            connection.close()
            check("connection cap", b" 403 " in response)
            time.sleep(.2)
            stop(process)
            process, port = start("count", connections=2)
            connection, response = connect(port)
            connection.close()
            check("restart retains cap", b" 403 " in response)
            stop(process)
            changed, changed_port = start("count", connections=3)
            check("changed cap refused", changed_port is None and changed.returncode != 0)
            process, port = start("idle-stop")
            stop(process)
            process, port = start("idle-stop")
            check("SIGTERM alone is restartable process stop", tls_request(port))
            time.sleep(.2)
            (output / "idle-stop/REVOKED").touch()
            stop(process)
            process, port = start("idle-stop")
            try:
                connection, response = connect(port)
                connection.close()
                blocked = b" 200 " not in response
            except OSError:
                blocked = True
            check("marker before stop durably blocks same-pool restart", blocked)

            _, port = start("bytes", connections=4, byte_cap=1000, dummy_port=collector.server_address[1])
            def upload(_):
                connection, response = connect(port)
                assert b" 200 " in response
                try:
                    connection.sendall(b"x" * 700)
                    received = connection.recv(64)
                except (OSError, TimeoutError):
                    received = b""
                connection.close()
                return {"attempted_bytes": 700, "acknowledged": received == b"ACK"}
            with ThreadPoolExecutor(max_workers=2) as pool:
                uploads = list(pool.map(upload, range(2)))
            time.sleep(.2)
            with sqlite3.connect(output / "bytes/tunnel.sqlite3") as db:
                charged = db.execute("SELECT bytes FROM pool").fetchone()[0]
                rows = db.execute("SELECT uploaded,reason FROM tunnels").fetchall()
            report["concurrent_byte_case"] = {"attempts": uploads, "attempted_total": 1400,
                "cap": 1000, "charged": charged, "independent_receiver_bytes": collector.rows, "tunnel_rows": rows}
            check("concurrent second upload denied before forwarding", sum(r["acknowledged"] for r in uploads) == 1
                and sum(collector.rows) == 700 and sum(r[0] for r in rows) == 700
                and any(r[1] == "byte_or_authority_limit" for r in rows) and 0 < charged <= 1000)

            _, port = start("revoke")
            connection, _ = connect(port)
            (output / "revoke/REVOKED").touch()
            connection.settimeout(3)
            check("revocation closes active tunnel", connection.recv(64) == b"")
            connection.close()
            _, port = start("deadline", duration=1)
            time.sleep(1.3)
            try:
                connection, response = connect(port)
                connection.close()
                stopped = b" 200 " not in response
            except OSError:
                stopped = True
            check("duration closes admission", stopped and (output / "deadline/REVOKED").exists())
            _, port = start("held-deadline", duration=2, dummy_port=held.server_address[1])
            connection, response = connect(port)
            assert b" 200 " in response
            connection.sendall(b"before-deadline")
            assert connection.recv(3) == b"ACK"
            time.sleep(2.3)
            try:
                connection.sendall(b"after-deadline")
                ended = connection.recv(64) == b""
            except OSError:
                ended = True
            connection.close()
            time.sleep(.1)
            report["held_deadline_observer"] = held.rows
            check("held connection forwards no post-deadline payload", ended and
                  [row["payload"] for row in held.rows] == ["before-deadline"])

            process, port = start("crash")
            connection, _ = connect(port)
            process.kill()
            process.communicate(timeout=5)
            connection.close()
            _, port = start("crash")
            time.sleep(.3)
            check("crashed active tunnel freezes restart", (output / "crash/REVOKED").exists())

            process, _ = start("parent")
            parent_command = report["commands"][-1]["argv"]
            stop(process)
            program = ('import json,subprocess,sys; p=subprocess.Popen(json.loads(sys.argv[1]),stdout=subprocess.PIPE); '
                       'line=p.stdout.readline(); print(json.dumps({"pid":p.pid,"startup":json.loads(line)}),flush=True);sys.stdin.read()')
            parent = subprocess.Popen([sys.executable, "-c", program, json.dumps(parent_command)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            processes.append(parent)
            assert select.select([parent.stdout], [], [], 5)[0]
            child = json.loads(parent.stdout.readline())
            report["parent_child"] = child
            parent.kill()
            parent.wait(timeout=5)
            time.sleep(.5)
            check("parent loss persists revocation", (output / "parent/REVOKED").exists())
        except Exception as error:
            report["error"] = type(error).__name__ + ": " + str(error)
            check("scenario completed", False)
        finally:
            for path in output.glob("*/tunnel.sqlite3"):
                (path.parent / "REVOKED").touch()
            for process in processes:
                stop(process)
            if "child" in locals():
                outcome = wait_gateway_exit(child['pid'], report['linux_child_subreaper'])
                report['parent_gateway_exit'] = outcome
                check("parent-loss gateway already exited", outcome['exited'])
                if report['linux_child_subreaper']:
                    check("parent-loss gateway exited cleanly", outcome.get('reaped') is True and outcome.get('exit_code') == 0)
                if not outcome['exited']:
                    try:
                        os.kill(child['pid'], 9)
                    except ProcessLookupError:
                        pass
                    report['parent_gateway_forced_cleanup'] = wait_gateway_exit(
                        child['pid'], report['linux_child_subreaper'], timeout=2)
            server.shutdown()
            server.server_close()
            collector.shutdown()
            collector.server_close()
            held.shutdown()
            held.server_close()
            report["tls_rows"], report["tls_sni"] = server.rows, server.sni
            report["ledgers"] = {}
            for path in output.glob("*/tunnel.sqlite3"):
                with sqlite3.connect(path) as db:
                    db.row_factory = sqlite3.Row
                    report["ledgers"][path.parent.name] = {"integrity": db.execute("PRAGMA quick_check").fetchone()[0],
                        "pool": [dict(r) for r in db.execute("SELECT * FROM pool")],
                        "tunnels": [dict(r) for r in db.execute("SELECT * FROM tunnels")],
                        "events": [dict(r) for r in db.execute("SELECT * FROM events")]}
            check("all owned direct host processes stopped", all(p.poll() is not None for p in processes))
    check("temporary capability and generated TLS private key removed", not root.exists())
    report["source_sha256_after"] = {n: hashlib.sha256((HERE / n).read_bytes()).hexdigest() for n in report["source_sha256"]}
    check("source pins stable", report["source_sha256_after"] == report["source_sha256"])
    report["status"] = "pass" if all(c["passed"] for c in report["checks"]) else "fail"
    (output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "checks": len(report["checks"]), "output": str(output)}))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
