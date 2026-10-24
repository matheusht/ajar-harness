#!/usr/bin/env python3
"""Provider-free Kanboard actor-route E2E. Write checks before broker code.

See T02-KANBOARD-CREDENTIAL-ROUTE-CHECKS-20261022.md for failure inventory.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import http.client
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
from urllib.parse import urlencode

import check_kanboard_native_effect as effect


HERE = Path(__file__).resolve().parent
BROKER = HERE / "kanboard_role_broker.php"


def require(ok: bool, code: str) -> None:
    if not ok:
        raise RuntimeError(code)


def port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def ready(port_number: int) -> None:
    for _ in range(60):
        try:
            with socket.create_connection(("127.0.0.1", port_number), .1):
                return
        except OSError:
            time.sleep(.1)
    raise RuntimeError("service_unavailable")


def request(port_number: int, actor: str, method: str, path: str,
            body: str = "", headers: dict[str, str] | None = None) -> tuple[int, dict, bytes]:
    conn = http.client.HTTPConnection("127.0.0.1", port_number, timeout=5)
    provided = {"X-Native-Actor": actor, **(headers or {})}
    if method == "POST":
        provided.setdefault("Content-Type", "application/x-www-form-urlencoded")
    conn.request(method, path, body=body.encode() if method == "POST" else None,
                 headers=provided)
    response = conn.getresponse()
    result = response.status, {key.lower(): value for key, value in response.getheaders()}, response.read()
    conn.close()
    return result


def path(controller: str, action: str, **values: int) -> str:
    return "/?" + urlencode({"controller": controller, "action": action, **values})


def raw_status(port_number: int, request_bytes: bytes) -> int:
    with socket.create_connection(("127.0.0.1", port_number), 5) as sock:
        sock.sendall(request_bytes)
        line = sock.recv(256).split(b"\r\n", 1)[0]
    match = re.fullmatch(rb"HTTP/1\.1 (\d{3}) [^\r\n]+", line)
    require(match is not None, "raw_response_invalid")
    return int(match[1])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    s10 = effect.load_s10()
    seed_input, baseline = effect.seed(s10, args.source, args.output, Path("php"))
    app, data = args.output / "app", args.output / "seed-data"
    app_port, broker_port = port(), port()
    actor_map = args.output / "actors.json"
    actor_map.write_text(json.dumps({key: seed_input["users"][key]["username"]
                                     for key in ("A", "B", "C")}))
    actor_map.chmod(0o600)
    app_env = {"DB_FILENAME": str(data / "db.sqlite"), "REVERSE_PROXY_AUTH": "true",
               "REVERSE_PROXY_USER_HEADER": "HTTP_X_LRH_ACTOR"}
    import os
    app_proc = subprocess.Popen(["php", "-S", f"127.0.0.1:{app_port}", "-t", str(app)],
                                env={**os.environ, **app_env}, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
    broker_proc = None
    result = {"kind": "provider-free-kanboard-role-broker-v1", "status": "failed"}
    try:
        ready(app_port)
        broker_proc = subprocess.Popen(["php", str(BROKER), f"127.0.0.1:{broker_port}",
                                        str(actor_map), f"127.0.0.1:{app_port}"],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ready(broker_port)
        task = path("TaskViewController", "show", task_id=seed_input["T"])
        denied, denied_headers, denied_body = request(broker_port, "B", "GET", task)
        require(denied == 403 and seed_input["marker"].encode() not in denied_body,
                "B_private_task_not_denied")
        form_path = path("ProjectPermissionController", "index", project_id=seed_input["S"])
        form_status, form_headers, form_body = request(broker_port, "A", "GET", form_path)
        require(form_status == 200 and b'name="csrf_token" value="broker-managed"' in form_body,
                "A_form_or_broker_token_unavailable")
        require(not any("set-cookie" in headers for headers in (denied_headers, form_headers)),
                "backend_cookie_exposed")
        require(re.search(rb'name="csrf_token" value="(?!broker-managed)[^"]+"', form_body) is None,
                "backend_csrf_exposed")
        post = path("ProjectPermissionController", "addUser", project_id=seed_input["S"])
        values = {"csrf_token": "invalid", "project_id": seed_input["Q"],
                  "user_id": seed_input["users"]["B"]["id"], "role": "project-manager"}
        invalid, _, _ = request(broker_port, "A", "POST", post, urlencode(values))
        require(invalid in (400, 403, 302) and
                effect.protected_state(s10, data, seed_input) == baseline,
                "invalid_csrf_changed_state")
        values["csrf_token"] = "broker-managed"
        success, success_headers, _ = request(broker_port, "A", "POST", post, urlencode(values),
                                {"Cookie": "KB_SID=forged", "Authorization": "Basic forged",
                                 "X-LRH-Actor": seed_input["users"]["C"]["username"],
                                 "X-LRH-Request-ID": "0" * 32})
        request_id = success_headers.get("x-lrh-request-id", "")
        require(re.fullmatch(r"[0-9a-f]{32}", request_id) is not None and
                request_id != "0" * 32, "broker_request_id_spoofed_or_missing")
        final = effect.protected_state(s10, data, seed_input)
        require(success in (200, 302, 303) and final["roles"]["B"]["Q"] == "project-manager"
                and final["roles"]["B"]["S"] is None, "A_effect_missing_or_wrong_actor")
        allowed, allowed_headers, allowed_body = request(broker_port, "B", "GET", task,
                                                           headers={"Cookie": "KB_SID=forged"})
        require(allowed == 200 and seed_input["marker"].encode() in allowed_body,
                "fresh_B_read_missing")
        forged, _, _ = request(broker_port, "D", "GET", task,
                               headers={"X-LRH-Actor": seed_input["users"]["A"]["username"]})
        require(forged in (400, 403), "unknown_actor_accepted")
        private_data, _, _ = request(broker_port, "A", "GET", "/data/db.sqlite")
        require(private_data == 400, "private_data_route_exposed")
        duplicate_length = raw_status(broker_port,
            b"POST / HTTP/1.1\r\nHost: localhost\r\nX-Native-Actor: A\r\n"
            b"Content-Length: 0\r\nContent-Length: 0\r\n\r\n")
        transfer_encoding = raw_status(broker_port,
            b"POST / HTTP/1.1\r\nHost: localhost\r\nX-Native-Actor: A\r\n"
            b"Transfer-Encoding: chunked\r\n\r\n")
        require(duplicate_length == transfer_encoding == 400, "malformed_request_forwarded")
        result.update(status="pass", statuses={"B_denied": denied, "A_form": form_status,
                                               "invalid_csrf": invalid, "A_effect": success,
                                               "B_fresh": allowed, "forged_actor": forged,
                                               "private_data": private_data,
                                               "duplicate_length": duplicate_length,
                                               "transfer_encoding": transfer_encoding},
                      before_sha256=hashlib.sha256(json.dumps(baseline, sort_keys=True).encode()).hexdigest(),
                      after_sha256=hashlib.sha256(json.dumps(final, sort_keys=True).encode()).hexdigest(),
                      app_source_sha256=s10.SOURCE_CONTROLLER_SHA256,
                      claim="local_app_route_only; native_origin_held")
    finally:
        for proc in (broker_proc, app_proc):
            if proc is not None:
                proc.terminate()
                with contextlib.suppress(subprocess.TimeoutExpired):
                    proc.wait(timeout=3)
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()
        actor_map.unlink(missing_ok=True)
        (args.output / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    require(result["status"] == "pass", "broker_e2e_failed")


if __name__ == "__main__":
    main()
