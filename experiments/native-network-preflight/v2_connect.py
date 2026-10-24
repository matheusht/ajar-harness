#!/usr/bin/env python3
"""Opaque fixed-host CONNECT transport; model requests/tokens are not inspected."""
import argparse
from contextlib import nullcontext
import base64
import fcntl
import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import Path
import re
import select
import socket
import socketserver
import sqlite3
import stat
import subprocess
import sys
import threading
import time
from urllib.parse import unquote, urlsplit

AUTHORITY = "opencode.ai:443"
PRIVATE_IPV4 = tuple(ipaddress.IPv4Network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
STOP_EVENTS = ('stop_detected', 'producer_pause_failed', 'producer_frozen',
               'producer_set_frozen', 'producer_stop_failed', 'provider_shutdown_unsafe', 'authority_ended')


def private_ipv4(value):
    address=ipaddress.IPv4Address(value)
    if not any(address in network for network in PRIVATE_IPV4):raise ValueError('private_listener_address')
    return str(address)


def proxy_from_environment(name):
    value=os.environ.get(name,'')
    if not value or len(value)>4096 or not value.isascii() or any(c.isspace() or ord(c)<32 or ord(c)==127 for c in value):
        raise ValueError('upstream_proxy_configuration')
    parsed=urlsplit(value);host=parsed.hostname;port=parsed.port if parsed.port is not None else 80
    if parsed.scheme!='http' or not host or not 1<=port<=65535 or parsed.path not in ('','/') or '?' in value or '#' in value or any(c in host for c in '/?#@%'):
        raise ValueError('upstream_proxy_configuration')
    authorization=None
    if parsed.username is not None:
        username=unquote(parsed.username,errors='strict');password=unquote(parsed.password or '',errors='strict')
        if not username or ':' in username or any(ord(c)<32 or ord(c)==127 for c in username+password):
            raise ValueError('upstream_proxy_configuration')
        authorization='Basic '+base64.b64encode((username+':'+password).encode()).decode()
    return host,port,authorization


def proxy_connect_request(authorization):
    request=('CONNECT '+AUTHORITY+' HTTP/1.1\r\nHost: '+AUTHORITY+'\r\n').encode()
    if authorization:request+=('Proxy-Authorization: '+authorization+'\r\n').encode()
    return request+b'\r\n'


def accept_proxy_tunnel(upstream, deadline):
    response=bytearray()
    while not response.endswith(b'\r\n\r\n'):
        remaining=deadline-time.monotonic()
        if remaining<=0:raise TimeoutError('upstream_proxy_timeout')
        if len(response)>=16384:raise ValueError('upstream_proxy_header_limit')
        upstream.settimeout(remaining);data=upstream.recv(1)
        if not data:raise ValueError('upstream_proxy_short_header')
        response.extend(data)
    lines=bytes(response).split(b'\r\n');status=lines[0].split(b' ',2)
    if len(status)!=3 or status[0] not in (b'HTTP/1.0',b'HTTP/1.1') or status[1]!=b'200' or any(c<32 and c!=9 or c==127 for c in lines[0]):
        raise ValueError('upstream_proxy_status')
    for line in lines[1:-2]:
        key,separator,value=line.partition(b':')
        if not separator or not re.fullmatch(rb"[!#$%&'*+\-.^_`|~0-9A-Za-z]+",key) or any(c<32 and c!=9 or c==127 for c in value):
            raise ValueError('upstream_proxy_header')
    upstream.settimeout(5)


class Pool:
    def __init__(self, args):
        self.args = args
        args.state_dir.mkdir(mode=0o700, exist_ok=True)
        if args.state_dir.is_symlink() or args.state_dir.stat().st_uid != os.getuid() or args.state_dir.stat().st_mode & 0o077:
            raise ValueError("host_state_permissions")
        self.lockfile = (args.state_dir / "process.lock").open("a")
        fcntl.flock(self.lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.db = sqlite3.connect(args.state_dir / "tunnel.sqlite3", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript('''CREATE TABLE IF NOT EXISTS pool(config TEXT,created REAL,bytes INTEGER);
          CREATE TABLE IF NOT EXISTS tunnels(id INTEGER PRIMARY KEY, phase TEXT, uploaded INTEGER DEFAULT 0,
          downloaded INTEGER DEFAULT 0, reason TEXT, up_sha256 TEXT, down_sha256 TEXT);
          CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,timestamp REAL,kind TEXT,data TEXT);''')
        os.chmod(args.state_dir / "tunnel.sqlite3", 0o600)
        self.lock, self.sockets = threading.RLock(), set()
        descriptor = os.open(args.capability_file, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "r") as file:
            metadata = os.fstat(file.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid() or metadata.st_mode & 0o077:
                raise ValueError("local_capability_permissions")
            capability = file.read(257).strip()
        if not 24 <= len(capability) <= 128 or not capability.isascii() or any(c.isspace() for c in capability):
            raise ValueError("invalid_local_capability")
        self.auth = "Basic " + base64.b64encode(("run:" + capability).encode()).decode()
        self.redactions = (capability, self.auth, self.auth.removeprefix("Basic "))
        config = json.dumps({"authority": AUTHORITY, "max_connections": args.max_connections,
            "max_bytes": args.max_bytes, "duration": args.duration, "dummy_port": args.dummy_port,
            "capability_sha256": hashlib.sha256(capability.encode()).hexdigest()}, sort_keys=True)
        if getattr(args,'relay_peer',None):
            config=json.dumps({**json.loads(config),'private_listener':{
                'listen_address':args.listen_address,'relay_peer':args.relay_peer}},sort_keys=True)
        self.proxy=getattr(args,'upstream_proxy',None)
        if self.proxy:
            host,port,authorization=self.proxy
            identity={'mode':'http_connect','env':args.upstream_proxy_env,'host':host,'port':port,
                      'auth_hmac_sha256':hmac.new(capability.encode(),(authorization or '').encode(),hashlib.sha256).hexdigest()}
            config=json.dumps({**json.loads(config),'upstream_proxy':identity},sort_keys=True)
            if authorization:self.redactions+=(authorization,authorization.removeprefix('Basic '))
        if getattr(args, 'producers', None):
            config = json.dumps({**json.loads(config), 'producer_manifest_sha256': args.producers.digest}, sort_keys=True)
        if getattr(args,'native_run_state',None):
            config = json.dumps({**json.loads(config), 'native_run_state_sha256':hashlib.sha256(str(args.native_run_state.resolve()).encode()).hexdigest(),
                                 'native_run_duration':args.native_run_duration},sort_keys=True)
        row = self.db.execute("SELECT * FROM pool").fetchone()
        if row:
            if row["config"] != config:
                raise ValueError("frozen_pool_mismatch")
            self.created = row["created"]
        else:
            self.created = time.time()
            self.db.execute("INSERT INTO pool VALUES(?,?,0)", (config, self.created))
            self.db.commit()
        self.stale = bool(self.db.execute("SELECT count(*) FROM tunnels WHERE phase='active'").fetchone()[0]) or bool(self.db.execute("SELECT 1 FROM events WHERE kind='event_limit'").fetchone())
        # Resolve only the selected hop; explicit proxy mode never resolves the provider.
        if self.proxy:
            host,port,_=self.proxy
            self.destination=(socket.getaddrinfo(host,port,type=socket.SOCK_STREAM)[0][4][0],port)
        else:self.destination = ("127.0.0.1", args.dummy_port) if args.dummy_port else (
            socket.getaddrinfo("opencode.ai", 443, socket.AF_INET, socket.SOCK_STREAM)[0][4][0], 443)

    def active(self, check_run=True):
        allowed = not self.stale and not (self.args.state_dir / "REVOKED").exists() and time.time() < self.created + self.args.duration
        if allowed and check_run and getattr(self.args,'native_run_state',None):
            allowed = self.args.native_control.active(self.args.native_run_state)
        return allowed

    def event(self, kind, data):
        with self.lock, self.db:
            count = self.db.execute("SELECT count(*) FROM events").fetchone()[0]
            if count >= 4095:
                # Audit exhaustion ends provider admission; only verified freeze may publish REVOKED.
                self.stale = True
                if not self.db.execute("SELECT 1 FROM events WHERE kind='event_limit'").fetchone():
                    self.db.execute("INSERT INTO events(timestamp,kind,data) VALUES(?,?,?)",
                        (time.time(), 'event_limit', json.dumps({'provider_admission': 'closed', 'target_stop': 'unverified'})))
                # One watcher over at most eight producers needs fewer than 32 terminal records.
                marks = ','.join('?' for _ in STOP_EVENTS)
                terminal = self.db.execute('SELECT count(*) FROM events WHERE kind IN (' + marks + ')', STOP_EVENTS).fetchone()[0]
                if kind not in STOP_EVENTS or terminal >= 32:
                    return
            encoded = json.dumps(data, sort_keys=True)
            for value in self.redactions:
                encoded = encoded.replace(value, "[LOCAL-CAPABILITY]")
            self.db.execute("INSERT INTO events(timestamp,kind,data) VALUES(?,?,?)",
                (time.time(), kind, encoded))

    def admit(self):
        with self.lock, self.db:
            if not self.active() or self.db.execute("SELECT count(*) FROM tunnels").fetchone()[0] >= self.args.max_connections:
                raise ValueError("admission_limit")
            cur = self.db.execute("INSERT INTO tunnels(phase) VALUES('active')")
            return cur.lastrowid

    def charge(self, number, direction, amount):
        with self.lock, self.db:
            used = self.db.execute("SELECT bytes FROM pool").fetchone()[0]
            if not self.active() or used + amount > self.args.max_bytes:
                raise ValueError("byte_or_authority_limit")
            self.db.execute("UPDATE pool SET bytes=bytes+?", (amount,))
            self.db.execute("UPDATE tunnels SET " + direction + "=" + direction + "+? WHERE id=?", (amount, number))


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        pool, client = self.server.pool, self.request
        upstream, number, reason = None, None, "closed"
        audit = {}
        digests = {"uploaded": hashlib.sha256(), "downloaded": hashlib.sha256()}
        with pool.lock:
            pool.sockets.add(client)
        try:
            header, deadline = bytearray(), time.monotonic() + 5
            while not header.endswith(b"\r\n\r\n"):
                remaining = deadline - time.monotonic()
                if remaining <= 0 or len(header) >= 16384:
                    raise ValueError("header_limit")
                client.settimeout(remaining)
                data = client.recv(1)
                if not data:
                    raise ValueError("short_header")
                header.extend(data)
            lines = header.decode("ascii").split("\r\n")
            parts = lines[0].split(" ")
            if len(parts) == 3:
                method, target, version = parts
                parsed = urlsplit(target if "://" in target else "//" + target)
                audit = {"method": method if method in {"CONNECT", "GET", "POST"} else "other",
                    "version": version if version in {"HTTP/1.0", "HTTP/1.1", "HTTP/2.0"} else "other",
                    "target_form": "absolute_uri" if "://" in target else "authority"}
                if parsed.hostname in {"opencode.ai", "models.opencode.ai", "127.0.0.1", "localhost", "::1"}:
                    audit["hostname"] = parsed.hostname
                    audit["port"] = parsed.port
                else:
                    audit["hostname_class"] = "other_not_logged"
            if lines[0] not in {"CONNECT " + AUTHORITY + " HTTP/1.1", "CONNECT " + AUTHORITY + " HTTP/1.0"}:
                raise ValueError("authority_or_method")
            headers = {}
            for line in lines[1:]:
                if line:
                    key, value = line.split(":", 1)
                    key = key.lower()
                    if key in headers:
                        raise ValueError("duplicate_header")
                    headers[key] = value.strip()
            if headers.get("host", AUTHORITY) != AUTHORITY or not hmac.compare_digest(headers.get("proxy-authorization", ""), pool.auth):
                raise ValueError("proxy_authorization_or_host")
            number = pool.admit()
            guard=pool.args.native_control.dispatch_guard(pool.args.native_run_state) if getattr(pool.args,'native_run_state',None) else nullcontext()
            with guard:
                if not pool.active():raise ValueError('authority_ended')
                deadline=time.monotonic()+5
                upstream = socket.create_connection(pool.destination, timeout=5)
                with pool.lock:pool.sockets.add(upstream)
                if pool.proxy:
                    remaining=deadline-time.monotonic()
                    if remaining<=0:raise TimeoutError('upstream_proxy_timeout')
                    upstream.settimeout(remaining)
                    upstream.sendall(proxy_connect_request(pool.proxy[2]))
            if pool.proxy:accept_proxy_tunnel(upstream,deadline)
            guard=pool.args.native_control.dispatch_guard(pool.args.native_run_state) if getattr(pool.args,'native_run_state',None) else nullcontext()
            with guard:
                if not pool.active():raise ValueError('authority_ended')
                client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            client.settimeout(5)
            upstream.settimeout(5)
            pool.event("opened", {"tunnel_id": number, "authority": AUTHORITY, "peer_ip": pool.destination[0], **({"upstream_transport":"http_connect"} if pool.proxy else {})})
            idle = time.monotonic() + 60
            while pool.active():
                ready, _, _ = select.select([client, upstream], [], [], .2)
                if not ready:
                    if time.monotonic() > idle:
                        reason = "idle_limit"
                        break
                    continue
                for source in ready:
                    data = source.recv(65536)
                    if not data:
                        return
                    direction, destination = ("uploaded", upstream) if source is client else ("downloaded", client)
                    pool.charge(number, direction, len(data))
                    digests[direction].update(data)
                    held=False
                    hook=getattr(pool.args,'test_send_window',None)
                    if direction=='uploaded' and hook:
                        with pool.lock:
                            if (hook/'ARM').exists() and not getattr(pool,'test_send_held',False):
                                pool.test_send_held=True;held=True;(hook/'ARM').unlink()
                        if held:
                            (hook/'CHARGED').write_text(json.dumps({'charged':len(data),'tunnel_id':number}))
                            deadline=time.monotonic()+30
                            while not (hook/'RELEASE_SEND').exists() and time.monotonic()<deadline:time.sleep(.01)
                    sent=False
                    try:
                        guard=pool.args.native_control.dispatch_guard(pool.args.native_run_state) if getattr(pool.args,'native_run_state',None) else nullcontext()
                        with guard:
                            if not pool.active():raise ValueError('authority_ended')
                            destination.sendall(data)
                            sent=True
                    finally:
                        if held:(hook/'SEND_FINISHED').write_text(json.dumps({'sent':sent}))
                    idle = time.monotonic() + 60
        except Exception as error:
            safe_reasons = {"header_limit", "short_header", "authority_or_method", "duplicate_header",
                            "proxy_authorization_or_host", "admission_limit", "authority_ended", "byte_or_authority_limit",
                            "upstream_proxy_status", "upstream_proxy_header", "upstream_proxy_header_limit", "upstream_proxy_short_header"}
            reason = str(error) if str(error) in safe_reasons else type(error).__name__
            if number is None:
                try:
                    client.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                except OSError:
                    pass
                pool.event("rejected", {"reason": reason, **audit})
        finally:
            if number is not None:
                with pool.lock, pool.db:
                    pool.db.execute("UPDATE tunnels SET phase='closed',reason=?,up_sha256=?,down_sha256=? WHERE id=?",
                        (reason, digests["uploaded"].hexdigest(), digests["downloaded"].hexdigest(), number))
                pool.event("closed", {"tunnel_id": number, "reason": reason})
            for connection in [client, upstream]:
                if connection:
                    with pool.lock:
                        pool.sockets.discard(connection)
                    connection.close()


class Server(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, address, handler):
        self.workers = threading.BoundedSemaphore(4)
        super().__init__(address, handler)

    def verify_request(self, request, address):
        peer=getattr(self.pool.args,'relay_peer',None)
        return peer is None or address[0]==peer

    def process_request(self, request, address):
        if not self.workers.acquire(blocking=False):
            self.shutdown_request(request)
            return
        super().process_request(request, address)

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.workers.release()


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--capability-file", type=Path, required=True)
    parser.add_argument("--max-connections", type=int, required=True)
    parser.add_argument("--max-bytes", type=int, required=True)
    parser.add_argument("--duration", type=int, required=True)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--listen-address", help="explicit RFC1918 IPv4 listener; requires --relay-peer")
    parser.add_argument("--relay-peer", help="exact RFC1918 IPv4 TCP peer; requires --listen-address")
    parser.add_argument("--dummy-port", type=int)
    parser.add_argument("--upstream-proxy-env", help="explicit HTTP_PROXY or HTTPS_PROXY HTTP CONNECT hop")
    parser.add_argument("--producer-manifest", type=Path)
    parser.add_argument("--test-pause-failure-id")
    parser.add_argument("--test-kill-failure-id")
    parser.add_argument('--native-run-state',type=Path)
    parser.add_argument('--native-run-duration',type=float,default=600)
    parser.add_argument('--native-owner-pid',type=int)
    parser.add_argument('--test-send-window',type=Path)
    parser.add_argument('--test-startup-delay',type=float,default=0)
    parser.add_argument('--test-start-failure-after',type=int)
    parser.add_argument('--test-start-hold-dir',type=Path)
    args = parser.parse_args()
    if args.listen_address is not None or args.relay_peer is not None:
        if args.listen_address is None or args.relay_peer is None:parser.error('private_listener_requires_address_and_peer')
        try:
            args.listen_address=private_ipv4(args.listen_address);args.relay_peer=private_ipv4(args.relay_peer)
        except ValueError:parser.error('private_listener_requires_rfc1918_ipv4')
    else:args.listen_address='127.0.0.1'
    args.upstream_proxy=None
    if args.upstream_proxy_env is not None:
        if args.upstream_proxy_env not in ('HTTP_PROXY','HTTPS_PROXY') or args.dummy_port is not None:
            parser.error('upstream_proxy_selection_invalid')
        try:args.upstream_proxy=proxy_from_environment(args.upstream_proxy_env)
        except (ValueError,UnicodeError):parser.error('upstream_proxy_configuration_invalid')
    if any(v <= 0 for v in [args.max_connections, args.max_bytes, args.duration]):
        parser.error("finite positive limits required")
    if args.dummy_port is not None and not 1 <= args.dummy_port <= 65535:
        parser.error("invalid owned loopback dummy port")
    if (args.test_pause_failure_id or args.test_kill_failure_id or args.test_send_window or args.test_startup_delay or args.test_start_failure_after or args.test_start_hold_dir) and not args.dummy_port:
        parser.error('fault injection is restricted to the owned dummy experiment')
    if not 0<=args.test_startup_delay<=5:parser.error('bounded startup delay required')
    if args.test_start_hold_dir:
        entry=args.test_start_hold_dir
        if not entry.is_dir() or entry.is_symlink() or entry.stat().st_uid!=os.getuid() or entry.stat().st_mode & 0o077:
            parser.error('private owned startup hold directory required')
    if args.producer_manifest and not args.dummy_port and not args.native_run_state:
        parser.error('real CONNECT producer ownership requires native run state')
    if args.native_run_state and args.native_run_state.resolve()==args.state_dir.resolve():
        parser.error('provider and native run state directories must be separate')
    if args.native_run_state and not args.producer_manifest:
        parser.error('native run requires sealed producer manifest')
    if (args.test_pause_failure_id or args.test_kill_failure_id) and not args.producer_manifest:
        parser.error('pause failure requires the bound producer manifest')
    args.producers = None
    if args.test_startup_delay:time.sleep(args.test_startup_delay)
    if args.producer_manifest:
        sys.path.insert(0, str(Path(__file__).resolve().parent / 'v2-effect-windows'))
        from producer_stop import Producers
        args.producers = Producers(args.producer_manifest, args.test_pause_failure_id, args.test_kill_failure_id)
    if args.native_run_state:
        sys.path.insert(0,str(Path(__file__).resolve().parent/'v2-effect-windows'))
        import native_run
        args.native_control=native_run
    pool = Pool(args)
    server = Server((args.listen_address, args.port), Handler)
    if args.test_send_window:server.daemon_threads=False
    server.pool = pool
    parent = args.native_owner_pid or os.getppid()
    stop_owner=None;stop_owner_fd=None
    if args.producers:
        if not pool.active(check_run=False):
            server.server_close()
            raise ValueError('producer_grant_inactive')
        if args.native_run_state:
            controls=[args.state_dir,args.capability_file]
            if args.test_send_window:controls.append(args.test_send_window)
            if args.test_start_hold_dir:controls.append(args.test_start_hold_dir)
            args.native_control.prepare(args.native_run_state,args.producer_manifest,args.producers,args.native_run_duration,controls)
        try:
            if args.native_run_state:
                stop_owner,stop_owner_fd=args.native_control.arm_stop_owner(
                    args.native_run_state,args.producer_manifest,args.test_pause_failure_id,args.test_kill_failure_id)
            if os.getppid()!=parent:raise RuntimeError('native_owner_lost_before_start')
            if stop_owner and stop_owner.poll() is not None:raise RuntimeError('native_stop_owner_lost_before_start')
            if args.native_run_state:
                args.native_control.start_producers(args.native_run_state,args.producers,args.test_start_failure_after,args.test_start_hold_dir)
            else:args.producers.start(args.test_start_failure_after)
            if stop_owner and stop_owner.poll() is not None:raise RuntimeError('native_stop_owner_lost_during_start')
        except Exception:
            pool.stale=True;(args.state_dir/'REVOKED').touch()
            try:
                if args.native_run_state:
                    stopped=args.native_control.stop_producers(args.native_run_state,args.producers,pool.event,'startup_failure')
                    if not stopped:raise RuntimeError('producer_stop_failed')
                else:args.producers.freeze(pool.event)
            except Exception:
                pool.event('provider_shutdown_unsafe',{'target_stop':'failed_or_unknown','phase':'startup'})
            finally:
                if stop_owner_fd is not None:os.close(stop_owner_fd)
                server.server_close()
            raise

    def watch():
        while os.getppid() == parent and pool.active() and (stop_owner is None or stop_owner.poll() is None):
            time.sleep(.1)
        reason='owner_lost' if os.getppid()!=parent else ('stop_owner_lost' if stop_owner and stop_owner.poll() is not None else 'provider_authority_ended')
        if args.native_run_state:
            reason=args.native_control.stop_reason(args.native_run_state) or reason
            pool.stale=True
            (args.state_dir/'REVOKED').touch()  # Provider-only; never the run's verified-stop marker.
        pool.event('stop_detected', {'parent_lost': os.getppid() != parent, 'monotonic': time.monotonic(),'reason':reason})
        if args.producers:
            try:
                if args.native_run_state:
                    stopped=args.native_control.stop_producers(args.native_run_state,args.producers,pool.event,reason)
                    if not stopped:raise RuntimeError('producer_stop_failed')
                else:args.producers.freeze(pool.event)
            except Exception:
                # Closing provider admission cannot prove target stop when Docker stop failed.
                pool.stale = True
                pool.stop_unsafe=True
                with pool.lock:
                    for connection in list(pool.sockets):
                        try:
                            connection.shutdown(socket.SHUT_RDWR)
                        except OSError:
                            pass
                pool.event('provider_shutdown_unsafe', {'target_stop': 'failed_or_unknown', 'monotonic': time.monotonic()})
                server.shutdown()
                return
        (args.state_dir / "REVOKED").touch()
        if args.test_send_window:
            (args.test_send_window/'STOP_PUBLISHED').touch()
            deadline=time.monotonic()+30
            while not (args.test_send_window/'RELEASE_CLOSE').exists() and time.monotonic()<deadline:time.sleep(.01)
        with pool.lock:
            for connection in list(pool.sockets):
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
        pool.event("authority_ended", {"parent_lost": os.getppid() != parent})
        server.shutdown()

    threading.Thread(target=watch, daemon=True).start()
    print(json.dumps({"host": server.server_address[0], "port": server.server_address[1],
        "authority": AUTHORITY, "dummy": bool(args.dummy_port), "hard_limits": ["connections", "charged_tunnel_bytes", "wall", "workers"],
        **({"stop_owner_pid":stop_owner.pid} if stop_owner else {}),
        **({"upstream_transport":"http_connect"} if pool.proxy else {})}), flush=True)
    try:
        server.serve_forever(poll_interval=.1)
    finally:
        server.server_close()
        if stop_owner_fd is not None:os.close(stop_owner_fd)
        if stop_owner is not None:
            try:stop_owner.wait(timeout=10)
            except subprocess.TimeoutExpired:pass  # NativeRun.close reports the surviving owner.
    if getattr(pool,'stop_unsafe',False):raise RuntimeError('producer_stop_unsafe')


if __name__ == "__main__":
    main()
