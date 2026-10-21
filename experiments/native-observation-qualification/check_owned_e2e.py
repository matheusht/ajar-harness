"""Run the owned, provider-free original-application observation check."""

from __future__ import annotations

import argparse
import copy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import tempfile
import threading
import time
from typing import Any
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener, urlopen

from native_observation import (
    CLEANUP_CHECK_KEYS,
    EvidenceError,
    canonical_bytes,
    evaluate_observation_run,
    publish_atomic,
    write_bundle,
)


HERE = Path(__file__).resolve().parent
EXPECTED_PATH = HERE / "fixtures" / "expected-owned-e2e.json"
HANDOFF_MANIFEST = (
    HERE.parent
    / "native-review-qualification"
    / "T03-NATIVE-HANDOFF-PREFLIGHT-20261020"
    / "HANDOFF.json"
)
HANDOFF_MANIFEST_SHA256 = "26056e8abd33e6b55cfac99929e611b7f8bc8b9193bf914c589c4592c15f7f74"
CLIENT_CODE = r'''import hashlib,json,os,sys
from urllib.error import HTTPError
from urllib.request import Request,urlopen
url,action,case_id,observer_path=sys.argv[1:]
try:
    os.lstat(observer_path)
    visibility="present"
except FileNotFoundError:
    visibility="absent"
except OSError:
    visibility="inaccessible"
try:
    with open(observer_path,"ab") as stream:
        stream.write(b"x")
    probe="writable"
except OSError:
    probe="denied"
payload=json.dumps({"action":action,"case_id":case_id},sort_keys=True,separators=(",", ":")).encode()
request=Request(url,data=payload,method="POST",headers={"Content-Type":"application/json","X-Observation-Case":case_id})
try:
    response=urlopen(request,timeout=4)
    status=response.status
    body=response.read()
except HTTPError as error:
    status=error.code
    body=error.read()
print(json.dumps({"http_status":status,"observer_probe":probe,"observer_visibility":visibility,"response_sha256":hashlib.sha256(body).hexdigest()},sort_keys=True))
'''
CONNECT_RE = re.compile(
    r"connect\([^,]+, \{sa_family=AF_INET, sin_port=htons\((\d+)\), "
    r"sin_addr=inet_addr\(\"([^\"]+)\"\)\}"
)
CONNECT_RESULT_RE = re.compile(r"\},\s*\d+\)\s*=\s*(.+)$")
CONNECT_PENDING_RE = re.compile(r"^-1 EINPROGRESS(?:\s|$)")
OWNED_CLEANUP_CHECKS = CLEANUP_CHECK_KEYS
SENSITIVE_ALIAS_FIXTURES = (
    "access_token",
    "accessToken",
    "api_key",
    "auth",
    "authorization_header",
    "client_secret",
    "credential",
    "jwt",
    "private_key",
    "proxy_authorization",
    "secret",
    "session_token",
    "set-cookie",
    "token",
    "x_api_key",
)
SENSITIVE_VALUE_FIXTURES = (
    "sk_live_abcdefghijklmnop",
    "sk-proj-abcdefghijklmnop",
    "eyJabcdefghijk.abcdefghijkl.abcdefghijkl",
    "https://owned.invalid/?X-Amz-Signature=not-retained",
)
FROZEN_FAILURE_CHECKS = (
    "source_pin_mismatch",
    "observer_unavailable",
    "observer_channel_exposed",
    "trace_incomplete",
    "session_binding_missing",
    "tool_binding_missing",
    "request_binding_ambiguous",
    "host_replay_miscredited",
    "host_activity_in_researcher_window",
    "causal_order_invalid",
    "authorized_result_mismatch",
    "denied_effect_changed",
    "unexpected_route",
    "capture_completeness_unproven",
    "producer_can_write_observer",
    "sensitive_evidence_detected",
    "stop_unverified",
    "cleanup_incomplete",
    "normalized_repeat_mismatch",
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def state_digest(value: dict[str, Any]) -> str:
    return sha256(canonical_bytes(value))


def request_bytes(case_id: str, action: str) -> bytes:
    return json.dumps(
        {"action": action, "case_id": case_id},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def request_identity(raw: bytes) -> str:
    return sha256(
        canonical_bytes(
            {
                "body_sha256": sha256(raw),
                "method": "POST",
                "path_class": "owned_action",
            }
        )
    )


class OrderedRecorder:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sequence = 0
        self.events: list[dict[str, Any]] = []

    def record(self, kind: str, case_id: str) -> int:
        with self._lock:
            self._sequence += 1
            self.events.append(
                {"sequence": self._sequence, "kind": kind, "case_id": case_id}
            )
            return self._sequence


class OwnedState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.value = "initial"

    def handle(self, action: str, route_class: str) -> tuple[int, str, str, str, bytes]:
        with self._lock:
            before = state_digest({"value": self.value})
            if route_class == "bypass":
                status, outcome = 200, "bypass_response"
            elif action in {"read_public", "read_effect"}:
                status, outcome = 200, "authorized"
            elif action == "denied_private_change":
                status, outcome = 403, "denied"
            elif action == "apply_effect":
                self.value = "changed"
                status, outcome = 200, "effect_applied"
            else:
                status, outcome = 400, "invalid_request"
            after = state_digest({"value": self.value})
            response = canonical_bytes(
                {"outcome": outcome, "state_sha256": after, "status": status}
            )
            return status, outcome, before, after, response


class OwnedServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self,
        route_class: str,
        state: OwnedState,
        recorder: OrderedRecorder,
    ) -> None:
        self.route_class = route_class
        self.state = state
        self.recorder = recorder
        self.receipts: list[dict[str, Any]] = []
        self.receipt_lock = threading.Lock()
        super().__init__(("127.0.0.1", 0), OwnedHandler)


class OwnedHandler(BaseHTTPRequestHandler):
    server: OwnedServer

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path != "/owned":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "-1"))
        case_id = self.headers.get("X-Observation-Case", "")
        if length < 0 or length > 4096 or not case_id:
            self.send_error(400)
            return
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw)
            if payload != {
                "action": payload.get("action"),
                "case_id": case_id,
            } or payload.get("case_id") != case_id:
                raise ValueError("unexpected request shape")
            action = payload["action"]
        except (AttributeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            self.send_error(400)
            return
        status, outcome, before, after, response = self.server.state.handle(
            action, self.server.route_class
        )
        sequence = self.server.recorder.record(
            f"{self.server.route_class}_receipt", case_id
        )
        receipt = {
            "case_id": case_id,
            "effect": "changed" if before != after else "unchanged",
            "effect_after_sha256": after,
            "effect_before_sha256": before,
            "method": "POST",
            "outcome": outcome,
            "path_class": "owned_action",
            "request_sha256": request_identity(raw),
            "response_sha256": sha256(response),
            "route_class": self.server.route_class,
            "sequence": sequence,
            "status_code": status,
        }
        with self.server.receipt_lock:
            self.server.receipts.append(receipt)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)


def run_git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def source_pins(expected: dict[str, Any]) -> dict[str, Any]:
    repo = HERE.parents[1]
    handoff = expected["handoff_commit"]
    if run_git(repo, "rev-parse", f"{handoff}^") != expected["base_commit"]:
        raise RuntimeError("source_pin_mismatch: handoff parent")
    paths = [
        HERE / "FAILURE-CHECKS.md",
        HERE / "README.md",
        HERE / "native_observation.py",
        HERE / "check_owned_e2e.py",
        EXPECTED_PATH,
        HERE.parent
        / "native-review-qualification"
        / "OBSERVATION-INTEGRATION-SEAM-20261021.md",
    ]
    relative_paths = [str(path.relative_to(repo)) for path in paths]
    implementation = run_git(
        repo, "log", "-1", "--format=%H", "--", *relative_paths
    )
    if not implementation:
        raise RuntimeError("source_pin_mismatch: implementation version")
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", handoff, implementation],
        cwd=repo,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    if ancestry.returncode != 0:
        raise RuntimeError("source_pin_mismatch: handoff is not an ancestor")
    if sha256(HANDOFF_MANIFEST.read_bytes()) != HANDOFF_MANIFEST_SHA256:
        raise RuntimeError("source_pin_mismatch: handoff manifest")
    source_diff = subprocess.run(
        ["git", "diff", "--quiet", implementation, "--", *relative_paths],
        cwd=repo,
        stderr=subprocess.PIPE,
        text=True,
    )
    if source_diff.returncode != 0:
        raise RuntimeError("source_pin_mismatch: source differs from implementation")
    files = {}
    for path in paths:
        files[str(path.relative_to(repo))] = sha256(path.read_bytes())
    manifest = {
        "dependencies": {
            "native_review_handoff_manifest": HANDOFF_MANIFEST_SHA256,
        },
        "files": files,
        "parent_version_ids": [handoff],
        "source_id": "redteam-harness:native-observation-qualification",
        "version_id": implementation,
    }
    return {"manifest": manifest, "manifest_sha256": sha256(canonical_bytes(manifest))}


def start_server(
    route_class: str,
    state: OwnedState,
    recorder: OrderedRecorder,
    owned_ports: list[int],
) -> tuple[OwnedServer, threading.Thread]:
    server = OwnedServer(route_class, state, recorder)
    owned_ports.append(server.server_address[1])
    thread = threading.Thread(
        target=server.serve_forever,
        name=f"owned-{route_class}-listener",
        daemon=True,
    )
    try:
        thread.start()
    except BaseException:
        server.server_close()
        raise
    if not thread.is_alive():
        server.server_close()
        raise RuntimeError(f"observer_unavailable: {route_class}")
    return server, thread


def stop_server(server: OwnedServer, thread: threading.Thread) -> bool:
    shutdown_ok = close_ok = True
    try:
        server.shutdown()
    except BaseException:
        shutdown_ok = False
    finally:
        try:
            server.server_close()
        except BaseException:
            close_ok = False
        finally:
            thread.join(timeout=5)
    return shutdown_ok and close_ok and not thread.is_alive()


def process_group_gone(process_group: int) -> bool:
    try:
        os.killpg(process_group, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False


def stop_process_group(process: subprocess.Popen[str]) -> bool:
    for stop_signal in (signal.SIGTERM, signal.SIGKILL):
        if process.poll() is not None and process_group_gone(process.pid):
            return True
        try:
            os.killpg(process.pid, stop_signal)
        except ProcessLookupError:
            pass
        try:
            process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            continue
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and not process_group_gone(process.pid):
            time.sleep(0.05)
    return process.poll() is not None and process_group_gone(process.pid)


def port_can_rebind(port: int) -> bool:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        probe.close()


def receipt_projection(server: OwnedServer, case_id: str) -> list[dict[str, Any]]:
    with server.receipt_lock:
        return [copy.deepcopy(item) for item in server.receipts if item["case_id"] == case_id]


def parse_trace(raw: str) -> list[dict[str, Any]]:
    if "unfinished ..." in raw or "resumed>" in raw:
        raise RuntimeError("trace_incomplete: unfinished syscall")
    connects = []
    for line in raw.splitlines():
        if "connect(" not in line:
            continue
        if "sa_family=AF_INET," in line:
            match = CONNECT_RE.search(line)
            result = CONNECT_RESULT_RE.search(line)
            if match is None or result is None:
                raise RuntimeError("trace_incomplete: undecodable AF_INET connect")
            result_text = result.group(1).strip()
            admitted = result_text == "0" or CONNECT_PENDING_RE.match(
                result_text
            ) is not None
            connects.append(
                {
                    "address": match.group(2),
                    "admitted": admitted,
                    "kind": "inet" if admitted else "inet_failed",
                    "port": int(match.group(1)),
                }
            )
        elif (
            "sa_family=AF_UNIX" in line
            and 'sun_path="/var/run/nscd/socket"' in line
            and "ENOENT" in line
        ):
            connects.append(
                {"admitted": False, "kind": "local_name_service_absent"}
            )
        else:
            connects.append({"admitted": True, "kind": "unsupported"})
    return connects


def run_sandboxed_client(
    *,
    action: str,
    case_id: str,
    observer_private_path: Path,
    port: int,
    producer_status: dict[str, bool],
    raw_trace_paths: list[Path],
    scratch: Path,
) -> dict[str, Any]:
    trace_path = scratch / f"{case_id}.trace"
    raw_trace_paths.append(trace_path)
    strace = shutil.which("strace")
    bwrap = shutil.which("bwrap")
    if not strace or not bwrap:
        raise RuntimeError("observer_unavailable: strace or bwrap missing")
    command = [
        strace,
        "-f",
        "-qq",
        "-ttt",
        "-yy",
        "-e",
        "trace=connect",
        "-e",
        "signal=none",
        "-o",
        str(trace_path),
        "--",
        bwrap,
        "--unshare-user",
        "--unshare-pid",
        "--unshare-ipc",
        "--unshare-uts",
        "--uid",
        "65534",
        "--gid",
        "65534",
        "--ro-bind",
        "/",
        "/",
        "--tmpfs",
        "/tmp",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--chdir",
        "/tmp",
        "--die-with-parent",
        "/usr/bin/python3",
        "-c",
        CLIENT_CODE,
        f"http://127.0.0.1:{port}/owned",
        action,
        case_id,
        str(observer_private_path),
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
        env={
            "ALL_PROXY": "",
            "FTP_PROXY": "",
            "HTTP_PROXY": "",
            "HTTPS_PROXY": "",
            "LANG": "C.UTF-8",
            "NO_PROXY": "127.0.0.1",
            "PATH": "/usr/bin:/bin",
            "PYTHONHASHSEED": "0",
            "all_proxy": "",
            "http_proxy": "",
            "https_proxy": "",
            "no_proxy": "127.0.0.1",
        },
    )
    producer_status["stopped"] = False
    try:
        stdout, stderr = process.communicate(timeout=15)
    except subprocess.TimeoutExpired:
        producer_status["stopped"] = stop_process_group(process)
        code = "trace_incomplete: client timeout"
        if not producer_status["stopped"]:
            code = "stop_unverified: client process group"
        raise RuntimeError(code) from None
    except BaseException as error:
        producer_status["stopped"] = stop_process_group(process)
        if not producer_status["stopped"]:
            raise RuntimeError("stop_unverified: client process group") from error
        raise
    producer_status["stopped"] = process_group_gone(process.pid)
    if not producer_status["stopped"]:
        producer_status["stopped"] = stop_process_group(process)
        raise RuntimeError("stop_unverified: client process group")
    raw_trace = trace_path.read_text() if trace_path.is_file() else ""
    trace_path.unlink(missing_ok=True)
    if process.returncode != 0:
        raise RuntimeError(
            "trace_incomplete: client exit "
            f"{process.returncode}; stderr_class={'present' if stderr else 'empty'}"
        )
    try:
        projection = json.loads(stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("trace_incomplete: invalid client projection") from error
    if set(projection) != {
        "http_status",
        "observer_probe",
        "observer_visibility",
        "response_sha256",
    }:
        raise RuntimeError("trace_incomplete: unexpected client projection")
    if (
        projection["observer_probe"] not in {"denied", "writable"}
        or projection["observer_visibility"] not in {
            "absent",
            "inaccessible",
            "present",
        }
        or not isinstance(projection["http_status"], int)
        or not isinstance(projection["response_sha256"], str)
        or re.fullmatch(r"[0-9a-f]{64}", projection["response_sha256"]) is None
    ):
        raise RuntimeError("trace_incomplete: invalid client projection")
    connects = parse_trace(raw_trace)
    return {
        "client": projection,
        "connects": connects,
        "attribution_verified": True,
        "process_binding": "exact_spawned_subtree",
        "raw_trace_retained": False,
        "subtree_exit": "observed_zero",
    }


def host_request(case_id: str, action: str, port: int) -> dict[str, Any]:
    raw = request_bytes(case_id, action)
    request = Request(
        f"http://127.0.0.1:{port}/owned",
        data=raw,
        method="POST",
        headers={"Content-Type": "application/json", "X-Observation-Case": case_id},
    )
    opener = build_opener(ProxyHandler({}))
    try:
        response = opener.open(request, timeout=4)
        status = response.status
        body = response.read()
    except HTTPError as error:
        status = error.code
        body = error.read()
    return {"http_status": status, "response_sha256": sha256(body)}


def researcher_case(
    *,
    action: str,
    case_id: str,
    destination_class: str,
    main: OwnedServer,
    bypass: OwnedServer,
    observer_private_path: Path,
    producer_status: dict[str, bool],
    raw_trace_paths: list[Path],
    recorder: OrderedRecorder,
    scratch: Path,
) -> dict[str, Any]:
    destination = main if destination_class == "observer" else bypass
    open_sequence = recorder.record("dispatch_open", case_id)
    intent = request_identity(request_bytes(case_id, action))
    traced = run_sandboxed_client(
        action=action,
        case_id=case_id,
        observer_private_path=observer_private_path,
        port=destination.server_address[1],
        producer_status=producer_status,
        raw_trace_paths=raw_trace_paths,
        scratch=scratch,
    )
    close_sequence = recorder.record("dispatch_close", case_id)
    host_activity = [
        event
        for event in recorder.events
        if event["kind"].startswith("host_")
        and open_sequence < event["sequence"] < close_sequence
    ]
    connects = []
    for item in traced["connects"]:
        if item["kind"] == "inet":
            connects.append(
                {
                    "address_class": (
                        "owned_loopback"
                        if item["address"] == "127.0.0.1"
                        else "unexpected"
                    ),
                    "admitted": item["admitted"],
                    "destination_class": (
                        destination_class
                        if item["port"] == destination.server_address[1]
                        else "unexpected"
                    ),
                }
            )
        elif item["kind"] == "inet_failed":
            connects.append(
                {
                    "address_class": (
                        "owned_loopback"
                        if item["address"] == "127.0.0.1"
                        else "unexpected"
                    ),
                    "admitted": False,
                    "destination_class": "failed_network_attempt",
                }
            )
        elif item["kind"] == "local_name_service_absent":
            connects.append(
                {
                    "address_class": "local_unix",
                    "admitted": False,
                    "destination_class": "local_name_service_absent",
                }
            )
        else:
            connects.append(
                {
                    "address_class": "unexpected",
                    "admitted": True,
                    "destination_class": "unexpected",
                }
            )
    return {
        "application_receipts": receipt_projection(main, case_id),
        "bypass_receipts": receipt_projection(bypass, case_id),
        "case_id": case_id,
        "dispatch": {
            "close_sequence": close_sequence,
            "dispatch_id": f"dispatch:{case_id}",
            "open_sequence": open_sequence,
            "request_intent_sha256": intent,
            "session_binding": "owned-session-v1",
            "tool_binding": f"owned-tool:{case_id}",
        },
        "host_activity": host_activity,
        "trace": {
            "attribution_verified": traced["attribution_verified"],
            "connects": connects,
            "process_binding": traced["process_binding"],
            "raw_trace_retained": traced["raw_trace_retained"],
            "subtree_exit": traced["subtree_exit"],
        },
        "producer_observer_writable": traced["client"]["observer_probe"]
        == "writable",
        "producer_observer_visible": traced["client"]["observer_visibility"]
        != "absent",
        "response": {
            "sha256": traced["client"]["response_sha256"],
            "status_code": traced["client"]["http_status"],
        },
    }


class OwnedRunError(RuntimeError):
    def __init__(self, code: str, cleanup: dict[str, Any]) -> None:
        super().__init__(code)
        self.code = code
        self.cleanup = copy.deepcopy(cleanup)


class OwnedAcceptanceError(RuntimeError):
    def __init__(self, failed_checks: list[str]) -> None:
        super().__init__(failed_checks[0])
        self.code = failed_checks[0]
        self.failed_checks = list(failed_checks)


def execute_once(expected: dict[str, Any], pins: dict[str, Any]) -> dict[str, Any]:
    scratch: Path | None = None
    raw_trace_paths: list[Path] = []
    recorder = OrderedRecorder()
    state = OwnedState()
    main = bypass = None
    main_thread = bypass_thread = None
    cases: list[dict[str, Any]] = []
    cleanup_checks = {
        "observer_endpoints_released": False,
        "observer_processes_stopped": False,
        "owned_resources_only": True,
        "private_scratch_removed": False,
        "producer_processes_stopped": True,
        "raw_capture_removed": False,
    }
    cleanup = {
        "checks": cleanup_checks,
        "status": "incomplete",
        "stop_verified": False,
    }
    ports: list[int] = []
    producer_status = {"stopped": True}
    primary_error: BaseException | None = None
    try:
        scratch = Path(tempfile.mkdtemp(prefix="native-observation-owned-"))
        os.chmod(scratch, 0o700)
        observer_private_path = scratch / "observer-private.jsonl"
        observer_private_path.write_bytes(b"")
        os.chmod(observer_private_path, 0o600)
        main, main_thread = start_server("observer", state, recorder, ports)
        bypass, bypass_thread = start_server("bypass", state, recorder, ports)

        case_id = "host-replay"
        host_open = recorder.record("host_client_open", case_id)
        replay_response = host_request(case_id, "read_public", ports[0])
        host_close = recorder.record("host_client_close", case_id)
        cases.append(
            {
                "application_receipts": receipt_projection(main, case_id),
                "bypass_receipts": [],
                "case_id": case_id,
                "dispatch": None,
                "host_activity": [
                    {"case_id": case_id, "kind": "host_client_open", "sequence": host_open},
                    {"case_id": case_id, "kind": "host_client_close", "sequence": host_close},
                ],
                "producer_observer_visible": None,
                "producer_observer_writable": None,
                "response": {
                    "sha256": replay_response["response_sha256"],
                    "status_code": replay_response["http_status"],
                },
                "trace": None,
            }
        )

        for case_id, action, destination in [
            ("authorized-read", "read_public", "observer"),
            ("denied-change", "denied_private_change", "observer"),
            ("effect-write", "apply_effect", "observer"),
            ("state-consumption", "read_effect", "observer"),
            ("direct-bypass", "read_effect", "bypass"),
        ]:
            cases.append(
                researcher_case(
                    action=action,
                    case_id=case_id,
                    destination_class=destination,
                    main=main,
                    bypass=bypass,
                    observer_private_path=observer_private_path,
                    producer_status=producer_status,
                    raw_trace_paths=raw_trace_paths,
                    recorder=recorder,
                    scratch=scratch,
                )
            )
    except BaseException as error:
        primary_error = error
    finally:
        stop_results = []
        for server, thread in ((main, main_thread), (bypass, bypass_thread)):
            if server is None or thread is None:
                continue
            try:
                stop_results.append(stop_server(server, thread))
            except BaseException:
                stop_results.append(False)
        cleanup_checks["observer_processes_stopped"] = all(stop_results)
        rebind_results = []
        for port in ports:
            try:
                rebind_results.append(port_can_rebind(port))
            except BaseException:
                rebind_results.append(False)
        cleanup_checks["observer_endpoints_released"] = all(rebind_results)
        cleanup_checks["producer_processes_stopped"] = producer_status["stopped"]
        if scratch is not None:
            try:
                shutil.rmtree(scratch)
            except BaseException:
                pass
        cleanup_checks["private_scratch_removed"] = (
            scratch is not None and not scratch.exists()
        )
        cleanup_checks["raw_capture_removed"] = all(
            not path.exists() for path in raw_trace_paths
        )
        cleanup["stop_verified"] = (
            cleanup_checks["producer_processes_stopped"]
            and cleanup_checks["observer_processes_stopped"]
        )
        cleanup["status"] = (
            "complete" if all(cleanup_checks.values()) else "incomplete"
        )

    if primary_error is not None:
        raise OwnedRunError(failure_code(primary_error), cleanup) from None
    if cleanup["status"] != "complete":
        code = "cleanup_incomplete"
        if cleanup["stop_verified"] is False:
            code = "stop_unverified"
        raise OwnedRunError(code, cleanup)
    effect = next(case for case in cases if case["case_id"] == "effect-write")
    consumed = next(case for case in cases if case["case_id"] == "state-consumption")
    produced_sha = effect["application_receipts"][0]["effect_after_sha256"]
    consumed_sha = consumed["application_receipts"][0]["effect_before_sha256"]
    return {
        "cases": cases,
        "chain_state": {
            "consumed": [
                {
                    "consumer_case_id": "state-consumption",
                    "observed_sha256": consumed_sha,
                    "state_id": "owned-effect-state-v1",
                }
            ],
            "contrary_results": [
                {
                    "case_id": "denied-change",
                    "meaning": "private change denied and state unchanged",
                },
                {
                    "case_id": "direct-bypass",
                    "meaning": "direct route exists outside application observer",
                },
            ],
            "missing_transitions": [
                {
                    "case_id": "direct-bypass",
                    "transition": "application-observer-receipt",
                }
            ],
            "produced": [
                {
                    "producer_case_id": "effect-write",
                    "state_id": "owned-effect-state-v1",
                    "state_sha256": produced_sha,
                }
            ],
            "unfinished_conditions": [
                {
                    "condition": "managed launcher supplies protected native process attribution",
                    "status": "unavailable_in_this_lane",
                },
                {
                    "condition": "evidence changes a later native investigation action",
                    "status": "not_run",
                },
            ],
        },
        "cleanup": cleanup,
        "hypothesis": {
            "agent_discovery_credited": False,
            "allowed_effects": ["effect_applied"],
            "authority": "owned_synthetic_local_only",
            "conditions": {
                "application": "harmless_owned_synthetic",
                "observer": "host_owned_independent_receiver",
                "process_attribution": "exact_owned_spawned_subtree",
                "route_enforcement": "not_established",
            },
            "hypothesis_id": expected["scenario_id"],
            "next_test": "qualify the exact managed-native process boundary",
            "nonclaims": expected["nonclaims"],
            "objective": "qualify protected original application observation",
            "origin": "operator_authored_fixture",
            "statement": (
                "A protected receipt can bind one exact owned dispatch while host "
                "replay and an unobserved route remain distinct."
            ),
            "status": "supported_for_owned_fixture_with_bypass_limitation",
        },
        "observer_boundary": {
            "allowed_address_classes": ["owned_loopback"],
            "allowed_nonroute_destination_classes": [
                "local_name_service_absent"
            ],
            "available": True,
            "declared_route": "observer",
            "producer_storage_visibility": "absent_from_producer_namespace",
            "qualification_scope": "owned_fixture_only_managed_native_unavailable",
            "route_completeness_claimed": False,
            "storage_owner": "host_fixture",
        },
        "scenario_id": expected["scenario_id"],
        "schema_version": 1,
        "source_pins": pins,
    }


def owned_semantics(
    run: dict[str, Any], bundle: dict[str, Any], expected: dict[str, Any]
) -> tuple[dict[str, bool], dict[str, str]]:
    cases = {case["case_id"]: case for case in run["cases"]}
    core = bundle["result"]["checks"]

    def receipt(case_id: str, route: str = "application_receipts") -> dict[str, Any]:
        selected = cases[case_id][route]
        return selected[0] if len(selected) == 1 else {}

    authorized = all(
        receipt(case_id).get("status_code") == 200
        and receipt(case_id).get("outcome") == "authorized"
        and receipt(case_id).get("effect") == "unchanged"
        for case_id in ("authorized-read", "state-consumption")
    )
    effect = receipt("effect-write")
    authorized = authorized and (
        effect.get("status_code") == 200
        and effect.get("outcome") == "effect_applied"
        and effect.get("effect") == "changed"
        and effect.get("effect_before_sha256") != effect.get("effect_after_sha256")
    )
    denied = receipt("denied-change")
    denied_valid = (
        denied.get("status_code") == 403
        and denied.get("outcome") == "denied"
        and denied.get("effect") == "unchanged"
        and denied.get("effect_before_sha256") == denied.get("effect_after_sha256")
    )
    bypass = receipt("direct-bypass", "bypass_receipts")
    bypass_valid = (
        bundle["result"]["case_outcomes"].get("direct-bypass")
        == "capture_claim_refused"
        and bypass.get("effect") == "unchanged"
    )
    outcomes = {
        case_id: ("supported" if outcome == "observed" else outcome)
        for case_id, outcome in bundle["result"]["case_outcomes"].items()
    }
    cleanup_exact = (
        set(run["cleanup"]["checks"]) == OWNED_CLEANUP_CHECKS
        and run["cleanup"]["status"] == "complete"
        and all(run["cleanup"]["checks"].values())
    )
    repeatability_exact = run["repeatability"] == {
        "normalized_match": True,
        "runs": 2,
    }
    checks = {
        "authorized_result_mismatch": authorized
        and core["effects_within_declared_authority"],
        "capture_completeness_unproven": bypass_valid
        and run["observer_boundary"]["route_completeness_claimed"] is False
        and core["capture_limitations_preserved"],
        "causal_order_invalid": core["causal_order_valid"]
        and core["chain_state_consistent"],
        "cleanup_incomplete": core["cleanup_complete"] and cleanup_exact,
        "denied_effect_changed": denied_valid,
        "host_activity_in_researcher_window": core[
            "host_activity_absent_during_dispatch"
        ],
        "host_replay_miscredited": core["provided_host_replays_valid"]
        and run["hypothesis"]["agent_discovery_credited"] is False,
        "normalized_repeat_mismatch": core["repeatability_record_consistent"]
        and repeatability_exact,
        "observer_channel_exposed": core["observer_channel_protected"],
        "observer_unavailable": core["observer_available"],
        "producer_can_write_observer": core["producer_cannot_write_observer"],
        "request_binding_ambiguous": core["request_binding_unambiguous"],
        "sensitive_evidence_detected": core["sensitive_patterns_not_detected"],
        "session_binding_missing": core["dispatch_binding_complete"],
        "source_pin_mismatch": core["source_manifest_self_integrity"],
        "stop_unverified": core["stop_verified"],
        "tool_binding_missing": core["dispatch_binding_complete"],
        "trace_incomplete": core["trace_complete"],
        "unexpected_route": core["provided_route_evidence_classified"]
        and bypass_valid,
    }
    if outcomes != expected["case_outcomes"]:
        checks["request_binding_ambiguous"] = False
    return checks, outcomes


def apply_owned_acceptance(
    run: dict[str, Any], bundle: dict[str, Any], expected: dict[str, Any]
) -> dict[str, Any]:
    checks, outcomes = owned_semantics(run, bundle, expected)
    result = bundle["result"]
    result["core_status"] = result["status"]
    bundle["evidence"]["collection"]["provider_calls"] = 0
    bundle["evidence"]["collection"]["target_calls"] = 0
    bundle["evidence"]["collection"]["network_scope"] = "owned_loopback_only"
    bundle["evidence"]["collection"]["application_bodies_retained"] = False
    result["case_outcomes"] = outcomes
    result["failure_checks"] = checks
    result["nonclaims"] = expected["nonclaims"]
    result["provider_calls"] = 0
    result["target_calls"] = 0
    result["status"] = (
        expected["expected_status"]
        if result["core_status"] == "observation_packet_valid"
        and all(checks.values())
        and outcomes == expected["case_outcomes"]
        else "owned_e2e_failed"
    )
    return bundle


def validate_expected(bundle: dict[str, Any], expected: dict[str, Any]) -> None:
    result = bundle["result"]
    if sorted(result["failure_checks"]) != sorted(expected["failure_checks"]):
        raise RuntimeError("failure check inventory mismatch")
    failed = [
        name
        for name in expected["failure_checks"]
        if result["failure_checks"][name] is not True
    ]
    if failed:
        raise OwnedAcceptanceError(failed)
    if result["case_outcomes"] != expected["case_outcomes"]:
        raise RuntimeError("case outcome mismatch")
    if result["nonclaims"] != expected["nonclaims"]:
        raise RuntimeError("nonclaim mismatch")
    if result["status"] != expected["expected_status"]:
        raise RuntimeError(f"unexpected status: {result['status']}")


def mutation_checks(
    run: dict[str, Any], expected: dict[str, Any]
) -> dict[str, bool]:
    checks = {}

    def relabel_admitted_route(item: dict[str, Any]) -> None:
        admitted = [
            connect
            for connect in item["cases"][5]["trace"]["connects"]
            if connect["admitted"]
        ]
        if len(admitted) != 1:
            raise RuntimeError("trace_incomplete: mutation route cardinality")
        admitted[0]["destination_class"] = "observer"

    mutations = {
        "source_pin_mismatch": lambda item: item["source_pins"]["manifest"].update(
            {"version_id": "0" * 40}
        ),
        "observer_channel_exposed": lambda item: item["observer_boundary"].update(
            {"producer_storage_visibility": "mounted"}
        ),
        "observer_unavailable": lambda item: item["observer_boundary"].update(
            {"available": False}
        ),
        "trace_incomplete": lambda item: item["cases"][1]["trace"].update(
            {"connects": []}
        ),
        "session_binding_missing": lambda item: item["cases"][1]["dispatch"].update(
            {"session_binding": ""}
        ),
        "tool_binding_missing": lambda item: item["cases"][1]["dispatch"].update(
            {"tool_binding": ""}
        ),
        "request_binding_ambiguous": lambda item: item["cases"][1][
            "application_receipts"
        ].append(copy.deepcopy(item["cases"][1]["application_receipts"][0])),
        "host_replay_miscredited": lambda item: item["hypothesis"].update(
            {"agent_discovery_credited": True}
        ),
        "host_activity_in_researcher_window": lambda item: item["cases"][1][
            "host_activity"
        ].append(
            {"case_id": "authorized-read", "kind": "host_client_open", "sequence": 0}
        ),
        "causal_order_invalid": lambda item: item["cases"][1][
            "application_receipts"
        ][0].update(
            {"sequence": item["cases"][1]["dispatch"]["open_sequence"]}
        ),
        "authorized_result_mismatch": lambda item: item["cases"][1][
            "application_receipts"
        ][0].update({"outcome": "denied"}),
        "denied_effect_changed": lambda item: item["cases"][2][
            "application_receipts"
        ][0].update({"effect": "changed"}),
        "unexpected_route": relabel_admitted_route,
        "capture_completeness_unproven": lambda item: item[
            "observer_boundary"
        ].update({"route_completeness_claimed": True}),
        "producer_can_write_observer": lambda item: item["cases"][1].update(
            {"producer_observer_writable": True}
        ),
        "sensitive_evidence_detected": lambda item: item.update(
            {"token": "fixture-value-not-retained"}
        ),
        "stop_unverified": lambda item: item["cleanup"].update(
            {"stop_verified": False}
        ),
        "cleanup_incomplete": lambda item: (
            item["cleanup"]["checks"].update({"private_scratch_removed": False}),
            item["cleanup"].update({"status": "incomplete"}),
        ),
        "normalized_repeat_mismatch": lambda item: item.update(
            {"repeatability": {"normalized_match": False, "runs": 2}}
        ),
    }
    expected_errors = {
        "denied_effect_changed": "receipt_effect_digest_mismatch",
        "host_replay_miscredited": "discovery_credit_unsupported",
        "sensitive_evidence_detected": "sensitive_evidence_detected",
        "session_binding_missing": "session_binding_missing",
        "tool_binding_missing": "tool_binding_missing",
    }
    for name, mutate in mutations.items():
        candidate = copy.deepcopy(run)
        mutate(candidate)
        if name != "normalized_repeat_mismatch":
            candidate["repeatability"] = {"normalized_match": True, "runs": 2}
        try:
            bundle = apply_owned_acceptance(
                candidate, evaluate_observation_run(candidate), expected
            )
            checks[name] = (
                bundle["result"]["failure_checks"][name] is False
                and bundle["result"]["status"] == "owned_e2e_failed"
            )
        except EvidenceError as error:
            checks[name] = error.code == expected_errors.get(name)
    return checks


def offline_fixture_checks(
    run: dict[str, Any], cleanup_projection: dict[str, Any]
) -> dict[str, Any]:
    evaluator_source_key = (
        "experiments/native-observation-qualification/native_observation.py"
    )
    pinned_evaluator_sha256 = run["source_pins"]["manifest"]["files"][
        evaluator_source_key
    ]
    parser_rejections = []
    for raw in (
        '1.0 connect(3, {sa_family=AF_INET6, sin6_port=htons(9)}, 28) = 0\n',
        '1.0 connect(3, {sa_family=AF_UNIX, sun_path="/tmp/x"}, 16) = 0\n',
    ):
        parsed = parse_trace(raw)
        represented = parsed == [{"admitted": True, "kind": "unsupported"}]
        candidate = copy.deepcopy(run)
        candidate["cases"][1]["trace"]["connects"].append(
            {
                "address_class": "unexpected",
                "admitted": True,
                "destination_class": "unexpected",
            }
        )
        result = evaluate_observation_run(candidate)["result"]
        parser_rejections.append(
            represented
            and result["status"] == "observation_packet_invalid"
            and result["checks"]["trace_complete"] is False
        )

    failed_inet_raw = (
        '1.0 connect(3, {sa_family=AF_INET, sin_port=htons(9), '
        'sin_addr=inet_addr("127.0.0.1")}, 16) = -1 ECONNREFUSED '
        '(Connection refused)\n'
    )
    failed_inet_parsed = parse_trace(failed_inet_raw)
    failed_inet_candidate = copy.deepcopy(run)
    failed_inet_candidate["cases"][1]["trace"]["connects"].append(
        {
            "address_class": "owned_loopback",
            "admitted": False,
            "destination_class": "failed_network_attempt",
        }
    )
    failed_inet_result = evaluate_observation_run(failed_inet_candidate)["result"]
    failed_inet_rejected = (
        failed_inet_parsed
        == [
            {
                "address": "127.0.0.1",
                "admitted": False,
                "kind": "inet_failed",
                "port": 9,
            }
        ]
        and failed_inet_result["status"] == "observation_packet_invalid"
        and failed_inet_result["checks"]["trace_complete"] is False
    )

    pending_inet_raw = (
        '1.0 connect(3, {sa_family=AF_INET, sin_port=htons(9), '
        'sin_addr=inet_addr("127.0.0.1")}, 16) = -1 EINPROGRESS '
        '(Operation now in progress)\n'
    )
    pending_inet_admitted = parse_trace(pending_inet_raw) == [
        {
            "address": "127.0.0.1",
            "admitted": True,
            "kind": "inet",
            "port": 9,
        }
    ]

    missing_cleanup = copy.deepcopy(run)
    missing_cleanup["cleanup"]["checks"].pop("observer_endpoints_released")
    try:
        evaluate_observation_run(missing_cleanup)
        cleanup_schema_rejected = False
    except EvidenceError as error:
        cleanup_schema_rejected = error.code == "cleanup_schema_mismatch"

    unknown = copy.deepcopy(run)
    unknown["unknown_critical_field"] = True
    try:
        evaluate_observation_run(unknown)
        unknown_schema_rejected = False
    except EvidenceError as error:
        unknown_schema_rejected = error.code == "input_schema_mismatch"

    aliases_rejected = []
    for key in SENSITIVE_ALIAS_FIXTURES:
        candidate = copy.deepcopy(run)
        candidate["hypothesis"]["conditions"][key] = "not-retained"
        try:
            evaluate_observation_run(candidate)
            aliases_rejected.append(False)
        except EvidenceError as error:
            aliases_rejected.append(error.code == "sensitive_evidence_detected")

    values_rejected = []
    for value in SENSITIVE_VALUE_FIXTURES:
        candidate = copy.deepcopy(run)
        candidate["hypothesis"]["statement"] = value
        try:
            evaluate_observation_run(candidate)
            values_rejected.append(False)
        except EvidenceError as error:
            values_rejected.append(error.code == "sensitive_evidence_detected")

    pair_shaped = copy.deepcopy(run)
    pair_shaped["hypothesis"]["conditions"]["header_pairs"] = [
        ["Authorization", "opaque-sensitive-material"]
    ]
    try:
        evaluate_observation_run(pair_shaped)
        sensitive_pair_rejected = False
    except EvidenceError as error:
        sensitive_pair_rejected = error.code == "sensitive_evidence_detected"

    boolean_integer_rejections = []
    boolean_mutations = (
        lambda item: item.update({"schema_version": True}),
        lambda item: item["cases"][1]["application_receipts"][0].update(
            {"sequence": True}
        ),
        lambda item: item["cases"][1]["application_receipts"][0].update(
            {"status_code": True}
        ),
        lambda item: item["cases"][1]["response"].update({"status_code": True}),
        lambda item: item["cases"][1]["dispatch"].update({"open_sequence": True}),
        lambda item: item["cases"][0]["host_activity"][0].update(
            {"sequence": True}
        ),
        lambda item: item.update(
            {"repeatability": {"normalized_match": None, "runs": True}}
        ),
    )
    for mutate in boolean_mutations:
        candidate = copy.deepcopy(run)
        mutate(candidate)
        try:
            evaluate_observation_run(candidate)
            boolean_integer_rejections.append(False)
        except EvidenceError:
            boolean_integer_rejections.append(True)

    malformed_chain = copy.deepcopy(run)
    malformed_chain["chain_state"]["contrary_results"][0]["case_id"] = []
    try:
        evaluate_observation_run(malformed_chain)
        malformed_chain_rejected = False
    except EvidenceError:
        malformed_chain_rejected = True

    unsupported_process_bindings = []
    for process_binding in ("container_source_ip", "unavailable"):
        candidate = copy.deepcopy(run)
        candidate["cases"][1]["trace"]["process_binding"] = process_binding
        try:
            evaluate_observation_run(candidate)
            unsupported_process_bindings.append(False)
        except EvidenceError as error:
            unsupported_process_bindings.append(
                error.code == "process_attribution_unsupported"
            )

    generic = copy.deepcopy(run)
    selected = copy.deepcopy(generic["cases"][1])
    selected["case_id"] = "arbitrary-app-probe"
    for receipt in selected["application_receipts"]:
        receipt["case_id"] = selected["case_id"]
    selected["dispatch"]["dispatch_id"] = "dispatch:arbitrary-app-probe"
    selected["dispatch"]["tool_binding"] = "portable-tool-binding"
    generic["cases"] = [selected]
    generic["chain_state"] = {
        "consumed": [],
        "contrary_results": [],
        "missing_transitions": [],
        "produced": [],
        "unfinished_conditions": [
            {"condition": "caller-selected next check", "status": "pending"}
        ],
    }
    generic["hypothesis"].update(
        {
            "hypothesis_id": "caller-defined-hypothesis",
            "objective": "caller-defined objective",
            "statement": "caller-defined statement",
        }
    )
    generic["scenario_id"] = "caller-defined-scenario"
    generic["source_pins"]["manifest"].update(
        {
            "dependencies": {},
            "files": {"caller/app.php": sha256(b"caller-selected-source\n")},
            "source_id": "caller-defined-source",
            "version_id": "caller-defined-version",
        }
    )
    generic["source_pins"]["manifest_sha256"] = sha256(
        canonical_bytes(generic["source_pins"]["manifest"])
    )
    generic_bundle = evaluate_observation_run(generic)
    generic_packet_accepted = (
        generic_bundle["result"]["status"] == "observation_packet_valid"
        and generic_bundle["result"]["case_outcomes"]
        == {"arbitrary-app-probe": "observed"}
        and generic_bundle["hypothesis"] == generic["hypothesis"]
        and generic_bundle["evidence"]["coverage"]
        == {
            "capture_refusal_cases": [],
            "host_replay_cases": [],
            "observed_cases": ["arbitrary-app-probe"],
            "unavailable_cases": [],
        }
    )

    single_run = copy.deepcopy(generic)
    single_run["repeatability"] = {"normalized_match": None, "runs": 1}
    single_run_accepted = (
        evaluate_observation_run(single_run)["result"]["status"]
        == "observation_packet_valid"
    )

    reversed_chain = copy.deepcopy(run)
    effect_receipt = reversed_chain["cases"][3]["application_receipts"][0]
    effect_receipt["sequence"] = reversed_chain["cases"][4]["dispatch"][
        "open_sequence"
    ]
    reversed_result = evaluate_observation_run(reversed_chain)["result"]
    invented_chain = copy.deepcopy(run)
    invented_chain["chain_state"]["produced"][0]["state_sha256"] = "0" * 64
    invented_chain["chain_state"]["consumed"][0]["observed_sha256"] = "0" * 64
    invented_result = evaluate_observation_run(invented_chain)["result"]
    omitted_chain = copy.deepcopy(run)
    omitted_chain["chain_state"]["produced"] = []
    omitted_chain["chain_state"]["consumed"] = []
    omitted_chain_result = evaluate_observation_run(omitted_chain)["result"]
    overlapping_chain = copy.deepcopy(run)
    producer_sequence = overlapping_chain["cases"][3]["application_receipts"][0][
        "sequence"
    ]
    overlapping_chain["cases"][4]["dispatch"]["open_sequence"] = producer_sequence
    overlapping_result = evaluate_observation_run(overlapping_chain)["result"]
    false_change = copy.deepcopy(run)
    false_change_receipt = false_change["cases"][3]["application_receipts"][0]
    false_change_receipt["effect_after_sha256"] = false_change_receipt[
        "effect_before_sha256"
    ]
    effect_consistency_rejections = []
    for candidate in (false_change,):
        try:
            evaluate_observation_run(candidate)
            effect_consistency_rejections.append(False)
        except EvidenceError as error:
            effect_consistency_rejections.append(
                error.code == "receipt_effect_digest_mismatch"
            )
    false_unchanged = copy.deepcopy(run)
    false_unchanged["cases"][1]["application_receipts"][0][
        "effect_after_sha256"
    ] = "0" * 64
    try:
        evaluate_observation_run(false_unchanged)
        effect_consistency_rejections.append(False)
    except EvidenceError as error:
        effect_consistency_rejections.append(
            error.code == "receipt_effect_digest_mismatch"
        )
    invalid_effect = copy.deepcopy(run)
    invalid_effect["cases"][1]["application_receipts"][0]["effect"] = "unknown"
    try:
        evaluate_observation_run(invalid_effect)
        invalid_effect_classification_rejected = False
    except EvidenceError as error:
        invalid_effect_classification_rejected = (
            error.code == "receipt_effect_schema_mismatch"
        )
    nonfinite_packet = copy.deepcopy(run)
    nonfinite_packet["hypothesis"]["conditions"]["score"] = float("nan")
    try:
        evaluate_observation_run(nonfinite_packet)
        nonfinite_packet_rejected = False
    except EvidenceError as error:
        nonfinite_packet_rejected = error.code == "nonportable_json_value"
    nonportable_shape_rejections = []
    for value in ({1: "numeric-key"}, ("tuple", "value")):
        candidate = copy.deepcopy(run)
        candidate["hypothesis"]["conditions"] = value
        try:
            evaluate_observation_run(candidate)
            nonportable_shape_rejections.append(False)
        except EvidenceError as error:
            nonportable_shape_rejections.append(
                error.code == "nonportable_json_value"
            )
    unauthorized_effect = copy.deepcopy(run)
    unauthorized_effect["hypothesis"]["allowed_effects"] = []
    unauthorized_effect_result = evaluate_observation_run(unauthorized_effect)[
        "result"
    ]
    changed_effect_requires_authority = (
        unauthorized_effect_result["status"] == "observation_packet_invalid"
        and unauthorized_effect_result["checks"][
            "effects_within_declared_authority"
        ]
        is False
    )
    chain_causality_rejected = all(
        result["status"] == "observation_packet_invalid"
        and result["checks"]["chain_state_consistent"] is False
        for result in (reversed_result, invented_result, overlapping_result)
    )
    changed_effect_requires_produced_state = (
        omitted_chain_result["status"] == "observation_packet_invalid"
        and omitted_chain_result["checks"]["chain_state_consistent"] is False
    )

    missing_bypass_transition = copy.deepcopy(run)
    missing_bypass_transition["chain_state"]["missing_transitions"] = []
    missing_bypass_result = evaluate_observation_run(missing_bypass_transition)[
        "result"
    ]
    bypass_transition_required = (
        missing_bypass_result["status"] == "observation_packet_invalid"
        and missing_bypass_result["checks"]["capture_limitations_preserved"]
        is False
    )
    spurious_bypass_transition = copy.deepcopy(run)
    spurious_bypass_transition["chain_state"]["missing_transitions"][0][
        "case_id"
    ] = "authorized-read"
    spurious_bypass_result = evaluate_observation_run(spurious_bypass_transition)[
        "result"
    ]
    spurious_bypass_transition_rejected = (
        spurious_bypass_result["status"] == "observation_packet_invalid"
        and spurious_bypass_result["checks"]["capture_limitations_preserved"]
        is False
    )

    discovery_credit = copy.deepcopy(run)
    discovery_credit["hypothesis"]["agent_discovery_credited"] = True
    try:
        evaluate_observation_run(discovery_credit)
        unsupported_discovery_credit_rejected = False
    except EvidenceError as error:
        unsupported_discovery_credit_rejected = (
            error.code == "discovery_credit_unsupported"
        )

    atomic_scratch: Path | None = None
    atomic_chmod_failure_cleaned = False
    atomic_dangling_output_rejected = False
    atomic_partial_output_absent = False
    atomic_relative_output_rejected = False
    try:
        atomic_scratch = Path(tempfile.mkdtemp(prefix="native-observation-atomic-"))
        os.chmod(atomic_scratch, 0o700)
        atomic_output = atomic_scratch / "partial"
        publish_atomic(atomic_output, {"first.json": b"{}\n", "invalid": None})
    except TypeError:
        atomic_partial_output_absent = (
            atomic_scratch is not None
            and not (atomic_scratch / "partial").exists()
            and list(atomic_scratch.iterdir()) == []
        )
        relative_output = Path(atomic_scratch.name) / "relative-output"
        try:
            publish_atomic(relative_output, {"result.json": b"{}\n"})
        except EvidenceError as error:
            atomic_relative_output_rejected = (
                error.code == "output_must_be_absent_with_existing_parent"
                and not os.path.lexists(relative_output)
            )
        dangling_target = atomic_scratch / "absent-target"
        dangling_output = atomic_scratch / "dangling-output"
        dangling_output.symlink_to(dangling_target)
        try:
            publish_atomic(dangling_output, {"result.json": b"{}\n"})
        except EvidenceError as error:
            atomic_dangling_output_rejected = (
                error.code == "output_must_be_absent_with_existing_parent"
                and dangling_output.is_symlink()
                and not dangling_target.exists()
            )
        finally:
            dangling_output.unlink(missing_ok=True)
        real_chmod = os.chmod

        def injected_chmod(path: os.PathLike[str] | str, mode: int) -> None:
            candidate = Path(path)
            if (
                atomic_scratch is not None
                and candidate.parent == atomic_scratch
                and candidate.name.startswith(".chmod-failure.")
            ):
                raise OSError("injected chmod failure")
            real_chmod(path, mode)

        os.chmod = injected_chmod
        try:
            try:
                publish_atomic(
                    atomic_scratch / "chmod-failure", {"result.json": b"{}\n"}
                )
            except OSError:
                atomic_chmod_failure_cleaned = not any(
                    path.name.startswith(".chmod-failure.")
                    for path in atomic_scratch.iterdir()
                )
        finally:
            os.chmod = real_chmod
    finally:
        if atomic_scratch is not None:
            shutil.rmtree(atomic_scratch, ignore_errors=True)
        atomic_fixture_scratch_removed = (
            atomic_scratch is not None and not atomic_scratch.exists()
        )
        cleanup_projection["atomic_fixture_scratch_removed"] = (
            atomic_fixture_scratch_removed
        )

    cli_scratch: Path | None = None
    cli_success = False
    cli_failure_preserved = False
    cli_duplicate_key_rejected = False
    cli_dangling_output_rejected = False
    failure_publication_error_preserved = False
    failure_receipt_details_preserved = False
    cli_nonfinite_rejected = False
    cli_relative_output_rejected = False
    try:
        cli_scratch = Path(tempfile.mkdtemp(prefix="native-observation-cli-"))
        os.chmod(cli_scratch, 0o700)
        python = shutil.which("python3")
        if python is None:
            raise RuntimeError("public CLI Python unavailable")
        evaluator_path = cli_scratch / "native_observation.py"
        shutil.copyfile(HERE / "native_observation.py", evaluator_path)
        os.chmod(evaluator_path, 0o600)
        if sha256(evaluator_path.read_bytes()) != pinned_evaluator_sha256:
            raise RuntimeError("public CLI source pin mismatch")
        cli_env = {
            "ALL_PROXY": "",
            "FTP_PROXY": "",
            "HTTP_PROXY": "",
            "HTTPS_PROXY": "",
            "LANG": "C.UTF-8",
            "NO_PROXY": "*",
            "PATH": "/usr/bin:/bin",
            "PYTHONDONTWRITEBYTECODE": "1",
            "all_proxy": "",
            "http_proxy": "",
            "https_proxy": "",
            "no_proxy": "*",
        }
        packet_path = cli_scratch / "packet.json"
        packet_path.write_bytes(canonical_bytes(generic))
        os.chmod(packet_path, 0o600)
        good_output = cli_scratch / "good"
        completed = subprocess.run(
            [
                python,
                str(evaluator_path),
                "--input",
                str(packet_path),
                "--output",
                str(good_output),
            ],
            check=False,
            env=cli_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
        )
        cli_projection = json.loads(completed.stdout)
        cli_result = json.loads((good_output / "result.json").read_text())
        cli_success = (
            completed.returncode == 0
            and completed.stderr == ""
            and cli_projection["status"] == "observation_packet_valid"
            and cli_result["case_outcomes"]
            == {"arbitrary-app-probe": "observed"}
            and (good_output.stat().st_mode & 0o777) == 0o700
            and all(
                (path.stat().st_mode & 0o777) == 0o600
                for path in good_output.iterdir()
            )
        )

        dangling_target = cli_scratch / "absent-cli-target"
        dangling_output = cli_scratch / "dangling-cli-output"
        dangling_output.symlink_to(dangling_target)
        dangling_run = subprocess.run(
            [
                python,
                str(evaluator_path),
                "--input",
                str(packet_path),
                "--output",
                str(dangling_output),
            ],
            check=False,
            env=cli_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
        )
        cli_dangling_output_rejected = (
            dangling_run.returncode != 0
            and dangling_output.is_symlink()
            and not dangling_target.exists()
        )
        dangling_output.unlink()
        relative_run = subprocess.run(
            [
                python,
                str(evaluator_path),
                "--input",
                str(packet_path),
                "--output",
                "relative-cli-output",
            ],
            check=False,
            cwd=cli_scratch,
            env=cli_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
        )
        cli_relative_output_rejected = (
            relative_run.returncode != 0
            and not os.path.lexists(cli_scratch / "relative-cli-output")
        )

        owned_failure_output = cli_scratch / "owned-failure-receipt"
        write_failure(
            owned_failure_output,
            OwnedAcceptanceError(["trace_incomplete"]),
            {"fixture_cleanup": "complete"},
            run["source_pins"],
        )
        owned_failure = json.loads(
            (owned_failure_output / "result.json").read_text()
        )
        failure_receipt_details_preserved = (
            owned_failure["failed_checks"] == ["trace_incomplete"]
            and owned_failure["provider_calls"] == 0
            and owned_failure["target_calls"] == 0
            and owned_failure["source_pins"] == run["source_pins"]
            and (owned_failure_output.stat().st_mode & 0o777) == 0o700
            and (owned_failure_output / "result.json").stat().st_mode & 0o777
            == 0o600
        )
        real_publish_atomic = globals()["publish_atomic"]

        def injected_publish_failure(
            output: Path, files: dict[str, bytes]
        ) -> None:
            raise OSError("injected failure receipt publication error")

        globals()["publish_atomic"] = injected_publish_failure
        unpublished_output = cli_scratch / "unpublished-failure-receipt"
        try:
            failure_publication_error_preserved = (
                publish_failure_best_effort(
                    unpublished_output,
                    OwnedAcceptanceError(["trace_incomplete"]),
                    {"fixture_cleanup": "complete"},
                    run["source_pins"],
                )
                is False
                and not os.path.lexists(unpublished_output)
            )
        finally:
            globals()["publish_atomic"] = real_publish_atomic

        def cli_rejection(name: str, payload: bytes, code: str) -> bool:
            rejected_path = cli_scratch / f"{name}.json"
            rejected_path.write_bytes(payload)
            os.chmod(rejected_path, 0o600)
            rejected_output = cli_scratch / (name + "-failure")
            failed = subprocess.run(
                [
                    python,
                    str(evaluator_path),
                    "--input",
                    str(rejected_path),
                    "--output",
                    str(rejected_output),
                ],
                check=False,
                env=cli_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=15,
            )
            projection = json.loads(failed.stdout)
            failure_result = json.loads(
                (rejected_output / "result.json").read_text()
            )
            return (
                failed.returncode == 1
                and failed.stderr == ""
                and projection
                == {
                    "failure_code": code,
                    "status": "observation_packet_rejected",
                }
                and failure_result["failure_code"] == code
                and failure_result["provider_calls"] == "not_observed"
                and failure_result["target_calls"] == "not_observed"
                and (rejected_output.stat().st_mode & 0o777) == 0o700
                and (rejected_output / "result.json").stat().st_mode & 0o777
                == 0o600
            )

        cli_failure_preserved = cli_rejection(
            "malformed", b"{", "input_json_invalid"
        )
        cli_duplicate_key_rejected = cli_rejection(
            "duplicate",
            b'{"schema_version":1,"schema_version":1}\n',
            "input_json_duplicate_key",
        )
        cli_nonfinite_rejected = cli_rejection(
            "nonfinite", b'{"score":NaN}\n', "input_json_nonfinite"
        )
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError):
        pass
    finally:
        if cli_scratch is not None:
            shutil.rmtree(cli_scratch, ignore_errors=True)
        cli_scratch_removed = cli_scratch is not None and not cli_scratch.exists()
        cleanup_projection["public_cli_scratch_removed"] = cli_scratch_removed
    return {
        "atomic_fixture_scratch_removed": atomic_fixture_scratch_removed,
        "atomic_chmod_failure_cleaned": atomic_chmod_failure_cleaned,
        "atomic_dangling_output_rejected": atomic_dangling_output_rejected,
        "atomic_partial_output_absent": atomic_partial_output_absent,
        "atomic_relative_output_rejected": atomic_relative_output_rejected,
        "boolean_integer_confusion_rejected": all(boolean_integer_rejections),
        "bypass_missing_transition_rejected": bypass_transition_required,
        "chain_causality_rejected": chain_causality_rejected,
        "changed_effect_requires_authority": changed_effect_requires_authority,
        "changed_effect_requires_produced_state": (
            changed_effect_requires_produced_state
        ),
        "cleanup_missing_key_rejected": cleanup_schema_rejected,
        "failed_inet_connect_rejected": failed_inet_rejected,
        "failure_publication_error_preserved": (
            failure_publication_error_preserved
        ),
        "failure_receipt_details_preserved": failure_receipt_details_preserved,
        "generic_arbitrary_packet_accepted": generic_packet_accepted,
        "generic_single_run_packet_accepted": single_run_accepted,
        "inconsistent_effect_digest_rejected": all(
            effect_consistency_rejections
        ),
        "invalid_effect_classification_rejected": (
            invalid_effect_classification_rejected
        ),
        "malformed_chain_reference_rejected": malformed_chain_rejected,
        "nonfinite_packet_rejected": nonfinite_packet_rejected,
        "nonportable_json_shapes_rejected": all(nonportable_shape_rejections),
        "pending_inet_connect_admitted": pending_inet_admitted,
        "public_cli_failure_preserved": cli_failure_preserved,
        "public_cli_duplicate_key_rejected": cli_duplicate_key_rejected,
        "public_cli_dangling_output_rejected": cli_dangling_output_rejected,
        "public_cli_nonfinite_rejected": cli_nonfinite_rejected,
        "public_cli_relative_output_rejected": cli_relative_output_rejected,
        "public_cli_scratch_removed": cli_scratch_removed,
        "public_cli_succeeded": cli_success,
        "sensitive_key_alias_count": len(aliases_rejected),
        "sensitive_key_aliases_rejected": all(aliases_rejected),
        "sensitive_pair_shape_rejected": sensitive_pair_rejected,
        "sensitive_value_pattern_count": len(values_rejected),
        "sensitive_value_patterns_rejected": all(values_rejected),
        "spurious_bypass_transition_rejected": (
            spurious_bypass_transition_rejected
        ),
        "unsupported_connect_families_rejected": all(parser_rejections),
        "unsupported_process_attribution_rejected": all(
            unsupported_process_bindings
        ),
        "unsupported_discovery_credit_rejected": (
            unsupported_discovery_credit_rejected
        ),
        "unknown_critical_field_rejected": unknown_schema_rejected,
    }


def failure_code(error: Exception) -> str:
    if isinstance(error, (EvidenceError, OwnedAcceptanceError, OwnedRunError)):
        return error.code
    message = str(error)
    for name in FROZEN_FAILURE_CHECKS:
        if name in message:
            return name
    if "negative fixture" in message:
        return "offline_failure_fixture"
    if "unexpected status" in message or "outcome mismatch" in message:
        return "expected_result_mismatch"
    if "source" in message and "mismatch" in message:
        return "source_pin_mismatch"
    return "internal_" + type(error).__name__.lower()


def write_failure(
    output: Path,
    error: Exception,
    cleanup: dict[str, Any] | None,
    pins: dict[str, Any] | None,
) -> None:
    receipt = {
        "cleanup": cleanup if cleanup is not None else "unavailable",
        "error_class": type(error).__name__,
        "failed_checks": (
            error.failed_checks
            if isinstance(error, OwnedAcceptanceError)
            else (
                [failure_code(error)]
                if failure_code(error) in FROZEN_FAILURE_CHECKS
                else []
            )
        ),
        "failure_code": failure_code(error),
        "provider_calls": 0,
        "schema_version": 1,
        "source_pins": pins if pins is not None else "unavailable_before_resolution",
        "status": "owned_e2e_failed",
        "target_calls": 0,
    }
    publish_atomic(output, {"result.json": canonical_bytes(receipt)})


def publish_failure_best_effort(
    output: Path,
    error: Exception,
    cleanup: dict[str, Any] | None,
    pins: dict[str, Any] | None,
) -> bool:
    if os.path.lexists(output):
        return False
    try:
        write_failure(output, error, cleanup, pins)
    except Exception:
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if (
        not args.output.is_absolute()
        or args.output.is_symlink()
        or os.path.lexists(args.output)
        or not args.output.parent.is_dir()
    ):
        raise SystemExit("--output must be absent under an existing absolute parent")
    output = args.output.resolve()
    offline_cleanup: dict[str, Any] = {
        "atomic_fixture_scratch_removed": "not_run",
        "public_cli_scratch_removed": "not_run",
    }
    cleanup_receipt: dict[str, Any] = {
        "offline_boundaries": offline_cleanup,
        "owned_runs": [],
    }
    pins: dict[str, Any] | None = None
    try:
        expected = json.loads(EXPECTED_PATH.read_text())
        pins = source_pins(expected)
        first = execute_once(expected, pins)
        cleanup_receipt["owned_runs"].append(first["cleanup"])
        second = execute_once(expected, pins)
        cleanup_receipt["owned_runs"].append(second["cleanup"])
        normalized_match = canonical_bytes(first) == canonical_bytes(second)
        first["repeatability"] = {"normalized_match": normalized_match, "runs": 2}
        second["repeatability"] = {"normalized_match": normalized_match, "runs": 2}
        first_bundle = apply_owned_acceptance(
            first, evaluate_observation_run(first), expected
        )
        second_bundle = apply_owned_acceptance(
            second, evaluate_observation_run(second), expected
        )
        if canonical_bytes(first_bundle) != canonical_bytes(second_bundle):
            raise RuntimeError("normalized_repeat_mismatch: bundle")
        validate_expected(first_bundle, expected)
        mutations = mutation_checks(first, expected)
        if not all(mutations.values()):
            raise RuntimeError("negative fixture failure")
        offline = offline_fixture_checks(first, offline_cleanup)
        expected_counts = {
            "sensitive_key_alias_count": len(SENSITIVE_ALIAS_FIXTURES),
            "sensitive_value_pattern_count": len(SENSITIVE_VALUE_FIXTURES),
        }
        if not all(
            value == expected_counts[key] if key in expected_counts else value is True
            for key, value in offline.items()
        ):
            raise RuntimeError("offline fixture failure")
        first_bundle["evidence"]["offline_failure_fixtures"] = mutations
        first_bundle["evidence"]["offline_boundary_fixtures"] = offline
        if source_pins(expected) != pins:
            raise RuntimeError("source_pin_mismatch: source changed during run")
        write_bundle(first_bundle, output)
    except Exception as error:
        if isinstance(error, OwnedRunError):
            cleanup_receipt["owned_runs"].append(error.cleanup)
        failure_receipt_published = publish_failure_best_effort(
            output, error, cleanup_receipt, pins
        )
        print(
            json.dumps(
                {
                    "error_class": type(error).__name__,
                    "failed_checks": (
                        error.failed_checks
                        if isinstance(error, OwnedAcceptanceError)
                        else (
                            [failure_code(error)]
                            if failure_code(error) in FROZEN_FAILURE_CHECKS
                            else []
                        )
                    ),
                    "failure_code": failure_code(error),
                    "failure_receipt_published": failure_receipt_published,
                    "provider_calls": 0,
                    "status": "owned_e2e_failed",
                    "target_calls": 0,
                },
                sort_keys=True,
            )
        )
        return 1
    print(
        json.dumps(
            {
                "provider_calls": 0,
                "status": expected["expected_status"],
                "target_calls": 0,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
