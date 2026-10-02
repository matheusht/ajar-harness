#!/usr/bin/env python3
"""Signed-scope network policy and pinned parent-side HTTP transport."""

from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import math
import re
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any, Callable


POLICY_START = b"```json network-policy-v1\n"
POLICY_END = b"\n```"
MAX_POLICY_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_REDIRECTS = 3
HOST_RE = re.compile(
    r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?\Z"
)
PATH_RE = re.compile(r"/[A-Za-z0-9._~/-]{0,4095}\Z")


class NetworkScopeError(RuntimeError):
    pass


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise NetworkScopeError("network_policy_duplicate_key")
        value[key] = item
    return value


@dataclass(frozen=True)
class NetworkPermission:
    operation: str
    scheme: str
    host: str
    port: int
    path: str
    method: str


@dataclass(frozen=True)
class NetworkPolicy:
    permissions: tuple[NetworkPermission, ...]

    def allows(
        self,
        operation: str,
        scheme: str,
        host: str,
        port: int,
        path: str,
        method: str,
    ) -> bool:
        candidate = NetworkPermission(
            operation, scheme.lower(), host.lower().rstrip("."), port, path, method.upper()
        )
        return candidate in self.permissions


def parse_network_policy(scope: bytes, *, expected_scope_hash: str) -> NetworkPolicy:
    if not isinstance(scope, bytes) or sha256_bytes(scope) != expected_scope_hash:
        raise NetworkScopeError("network_policy_scope_hash_mismatch")
    starts = scope.count(POLICY_START)
    if starts == 0:
        return NetworkPolicy(())
    if starts != 1:
        raise NetworkScopeError("network_policy_ambiguous")
    start = scope.index(POLICY_START) + len(POLICY_START)
    end = scope.find(POLICY_END, start)
    if end < 0 or end - start > MAX_POLICY_BYTES:
        raise NetworkScopeError("network_policy_invalid")
    raw = scope[start:end]
    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_pairs)
    except NetworkScopeError:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise NetworkScopeError("network_policy_invalid") from exc
    if (
        not isinstance(value, dict)
        or set(value) != {"schema_version", "permissions"}
        or type(value.get("schema_version")) is not int
        or value["schema_version"] != 1
    ):
        raise NetworkScopeError("network_policy_invalid")
    entries = value.get("permissions")
    if not isinstance(entries, list) or len(entries) > 64:
        raise NetworkScopeError("network_policy_invalid")
    permissions: list[NetworkPermission] = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {
            "operation", "scheme", "host", "port", "path", "method"
        }:
            raise NetworkScopeError("network_policy_invalid")
        operation = entry.get("operation")
        scheme = entry.get("scheme")
        host = entry.get("host")
        port = entry.get("port")
        path = entry.get("path")
        method = entry.get("method")
        if (
            operation != "target_fetch"
            or scheme not in {"http", "https"}
            or not isinstance(host, str)
            or not host
            or host != host.lower().rstrip(".")
            or HOST_RE.fullmatch(host) is None
            or type(port) is not int
            or not 1 <= port <= 65535
            or port != (443 if scheme == "https" else 80)
            or not isinstance(path, str)
            or PATH_RE.fullmatch(path) is None
            or method not in {"GET", "HEAD"}
        ):
            raise NetworkScopeError("network_policy_invalid")
        permission = NetworkPermission(operation, scheme, host, port, path, method)
        if permission in permissions:
            raise NetworkScopeError("network_policy_invalid")
        permissions.append(permission)
    return NetworkPolicy(tuple(permissions))


def address_allowed(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return address.version == 4 and address.is_global


class NetworkGateway:
    """Small exactly-once budget shared by provider and target relay operations."""

    def __init__(self, *, request_budget: int, deadline: float) -> None:
        if type(request_budget) is not int or not 1 <= request_budget <= 1024:
            raise NetworkScopeError("network_budget_invalid")
        if not isinstance(deadline, (int, float)) or not math.isfinite(deadline):
            raise NetworkScopeError("network_deadline_invalid")
        self.request_budget = request_budget
        self.deadline = float(deadline)
        self._started: set[str] = set()
        self._uncertain: set[str] = set()
        self._lock = threading.Lock()

    def begin(self, request_id: str) -> None:
        with self._lock:
            if (
                not isinstance(request_id, str)
                or not request_id
                or request_id in self._started
                or request_id in self._uncertain
                or len(self._started) >= self.request_budget
                or time.monotonic() >= self.deadline
            ):
                raise NetworkScopeError("network_request_not_admitted")
            self._started.add(request_id)

    def mark_uncertain(self, request_id: str) -> None:
        with self._lock:
            self._uncertain.add(request_id)


def resolve_pinned(host: str, port: int, *, deadline: float | None = None) -> str:
    """Resolve in a killable child so a stuck resolver cannot outlive the session deadline."""

    timeout = None if deadline is None else _remaining(deadline)
    program = (
        "import json,socket,sys;"
        "v=socket.getaddrinfo(sys.argv[1],int(sys.argv[2]),socket.AF_INET,socket.SOCK_STREAM,socket.IPPROTO_TCP);"
        "print(json.dumps(sorted({x[4][0] for x in v if len(x)>=5})))"
    )
    try:
        completed = subprocess.run(
            [sys.executable, "-I", "-c", program, host, str(port)],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            check=False, timeout=timeout,
        )
        addresses = json.loads(completed.stdout) if completed.returncode == 0 else []
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as exc:
        raise NetworkScopeError("network_dns_failed") from exc
    if not isinstance(addresses, list) or not addresses or any(
        not isinstance(item, str) or not address_allowed(item) for item in addresses
    ):
        raise NetworkScopeError("network_address_forbidden")
    # Multiple public answers are allowed, but one answer is selected and pinned for this connection.
    return addresses[0]


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise NetworkScopeError("network_deadline_exceeded")
    return remaining


def _read_response(sock: socket.socket, *, method: str, deadline: float) -> tuple[int, list[tuple[str, str]], bytes]:
    sock.settimeout(_remaining(deadline))
    response = http.client.HTTPResponse(sock, method=method)
    response.begin()
    headers = [(key.lower(), value) for key, value in response.getheaders()]
    sock.settimeout(_remaining(deadline))
    body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise NetworkScopeError("network_response_oversize")
    return response.status, headers, body


def pinned_request(
    *,
    policy: NetworkPolicy,
    operation: str,
    url: str,
    method: str,
    headers: dict[str, str] | None = None,
    body: bytes = b"",
    timeout: float = 10.0,
    deadline: float | None = None,
    resolver: Callable[[str, int], str] = resolve_pinned,
) -> tuple[int, list[tuple[str, str]], bytes]:
    absolute_deadline = time.monotonic() + timeout if deadline is None else float(deadline)
    if not math.isfinite(absolute_deadline):
        raise NetworkScopeError("network_deadline_invalid")
    current = url
    for redirect_count in range(MAX_REDIRECTS + 1):
        _remaining(absolute_deadline)
        parsed = urllib.parse.urlsplit(current)
        if (
            parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.scheme not in {"http", "https"}
        ):
            raise NetworkScopeError("network_url_invalid")
        scheme = parsed.scheme.lower()
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port or (443 if scheme == "https" else 80)
        path = parsed.path or "/"
        canonical = f"{scheme}://{host}{'' if port == (443 if scheme == 'https' else 80) else ':' + str(port)}{path}"
        if current != canonical or HOST_RE.fullmatch(host) is None or PATH_RE.fullmatch(path) is None:
            raise NetworkScopeError("network_url_invalid")
        if not policy.allows(operation, scheme, host, port, path, method):
            raise NetworkScopeError("network_policy_denied")
        supplied = headers or {}
        if any(
            not isinstance(name, str)
            or not isinstance(value, str)
            or name.lower() in {"authorization", "proxy-authorization", "host", "connection", "content-length", "transfer-encoding"}
            or re.fullmatch(r"[A-Za-z0-9-]+", name) is None
            or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
            or not value.isascii()
            for name, value in supplied.items()
        ):
            raise NetworkScopeError("network_header_invalid")
        _remaining(absolute_deadline)
        address = (
            resolver(host, port, deadline=absolute_deadline)
            if resolver is resolve_pinned
            else resolver(host, port)
        )
        if not isinstance(address, str) or not address_allowed(address):
            raise NetworkScopeError("network_address_forbidden")
        raw = socket.create_connection((address, port), timeout=_remaining(absolute_deadline))
        connection: socket.socket = raw
        try:
            if scheme == "https":
                raw.settimeout(_remaining(absolute_deadline))
                connection = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
            elif scheme == "http":
                connection = raw
            else:
                raise NetworkScopeError("network_scheme_denied")
            request_headers = {"Host": host, "Connection": "close", **supplied}
            payload = (
                f"{method} {path} HTTP/1.1\r\n"
                + "".join(f"{key}: {value}\r\n" for key, value in request_headers.items())
                + f"Content-Length: {len(body)}\r\n\r\n"
            ).encode("ascii") + body
            connection.settimeout(_remaining(absolute_deadline))
            connection.sendall(payload)
            status, response_headers, response_body = _read_response(connection, method=method, deadline=absolute_deadline)
        finally:
            connection.close()
        locations = [value for key, value in response_headers if key == "location"]
        if len(locations) > 1:
            raise NetworkScopeError("network_redirect_ambiguous")
        location = locations[0] if locations else None
        if status not in {301, 302, 303, 307, 308} or location is None:
            return status, response_headers, response_body
        if redirect_count == MAX_REDIRECTS:
            raise NetworkScopeError("network_redirect_limit")
        current = urllib.parse.urljoin(current, location)
    raise NetworkScopeError("network_redirect_limit")
