#!/usr/bin/env python3
"""Pure-stdlib client for the container-to-host action broker protocol.

Inside a model container, this client talks to a PID-1 relay over one bounded local socket.  Only
that supervisor receives the 32-byte session key and can authenticate to the host broker.  Direct
manifest/key loading remains available for the host-side protocol self-test, not the model child.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import socket
import stat
import struct
import sys
import time
from pathlib import Path
from typing import Any, Sequence


MANIFEST_ENV = "HARNESS_CONTAINER_BROKER_MANIFEST"
MANIFEST_FILE_ENV = "HARNESS_CONTAINER_BROKER_MANIFEST_FILE"
KEY_FD_ENV = "HARNESS_CONTAINER_BROKER_KEY_FD"
KEY_FILE_ENV = "HARNESS_CONTAINER_BROKER_KEY_FILE"
RELAY_SOCKET_ENV = "HARNESS_CONTAINER_BROKER_RELAY_SOCKET"
PROTOCOL_VERSION = 1
SESSION_KEY_BYTES = 32
NONCE_BYTES = 32
FRAME_LIMIT = 12 * 1024 * 1024
RAW_INPUT_LIMIT = 4 * 1024 * 1024
IO_TIMEOUT_SECONDS = 2.0
MAX_STOP_HOOK_STDIN_BYTES = 1024 * 1024
REQUEST_DOMAIN = b"llm-redteam-harness:container-broker:request:v1\0"
RESPONSE_DOMAIN = b"llm-redteam-harness:container-broker:response:v1\0"
TARGET_FETCH_ID_DOMAIN = b"llm-redteam-harness:target-fetch-id:v1\0"
STOP_SESSION_DOMAIN = b"llm-redteam-harness:session-end:v1:"
STOP_REQUEST_DOMAIN = b"llm-redteam-harness:session-end-request:v1:"
CONTAINER_ID_RE = re.compile(r"[0-9a-f]{64}\Z")
SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
RELAY_PATH_RE = re.compile(r"/scratch/[A-Za-z0-9._-]{1,128}\Z")


class ContainerBrokerClientError(RuntimeError):
    """The authenticated broker exchange could not be completed safely."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _mac(key: bytes, domain: bytes, value: dict[str, Any]) -> str:
    return base64.b64encode(
        hmac.new(key, domain + canonical_json_bytes(value), hashlib.sha256).digest()
    ).decode("ascii")


def _read_stable_regular(
    path: Path, *, max_bytes: int, require_private: bool = False
) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ContainerBrokerClientError("container_broker_input_invalid") from exc
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size > max_bytes
            or (
                require_private
                and (
                    before.st_uid != os.geteuid()
                    or stat.S_IMODE(before.st_mode) & 0o077
                )
            )
        ):
            raise ContainerBrokerClientError("container_broker_input_invalid")
        data = bytearray()
        while True:
            remaining = max_bytes - len(data)
            chunk = os.read(descriptor, min(1024 * 1024, remaining + 1))
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > max_bytes:
                raise ContainerBrokerClientError("container_broker_input_invalid")
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise ContainerBrokerClientError("container_broker_input_invalid")
        return bytes(data)
    finally:
        os.close(descriptor)


def _option_values(arguments: Sequence[str]) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    index = 0
    while index < len(arguments):
        option = arguments[index]
        if option.startswith("--") and index + 1 < len(arguments) and not arguments[index + 1].startswith("--"):
            values.setdefault(option, []).append(arguments[index + 1])
            index += 2
        else:
            index += 1
    return values


def validate_manifest(value: Any) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "schema_version",
            "transport",
            "endpoint",
            "runtime_identity",
            "runtime_session_ref",
            "action_id",
            "deadline_ref",
            "inline_inputs",
            "frame_limit",
            "raw_input_limit",
        }
        or type(value.get("schema_version")) is not int
        or value["schema_version"] != PROTOCOL_VERSION
        or value.get("transport") != "tcp_hmac_sha256"
    ):
        raise ContainerBrokerClientError("container_broker_manifest_invalid")
    endpoint = value.get("endpoint")
    identity = value.get("runtime_identity")
    if (
        not isinstance(endpoint, dict)
        or set(endpoint) != {"host", "port"}
        or not isinstance(endpoint.get("host"), str)
        or not endpoint["host"]
        or type(endpoint.get("port")) is not int
        or not 1 <= endpoint["port"] <= 65535
        or not isinstance(identity, dict)
        or set(identity) != {"kind", "container_id", "container_config_digest"}
        or identity.get("kind") != "docker_container"
        or not isinstance(identity.get("container_id"), str)
        or CONTAINER_ID_RE.fullmatch(identity["container_id"]) is None
        or not isinstance(identity.get("container_config_digest"), str)
        or SHA256_RE.fullmatch(identity["container_config_digest"]) is None
        or not isinstance(value.get("runtime_session_ref"), str)
        or not value["runtime_session_ref"]
        or "\x00" in value["runtime_session_ref"]
        or not isinstance(value.get("action_id"), str)
        or not value["action_id"]
        or "\x00" in value["action_id"]
        or not isinstance(value.get("deadline_ref"), str)
        or SHA256_RE.fullmatch(value["deadline_ref"]) is None
        or value.get("frame_limit") != FRAME_LIMIT
        or value.get("raw_input_limit") != RAW_INPUT_LIMIT
        or not isinstance(value.get("inline_inputs"), list)
    ):
        raise ContainerBrokerClientError("container_broker_manifest_invalid")
    seen: set[str] = set()
    for entry in value["inline_inputs"]:
        if (
            not isinstance(entry, dict)
            or set(entry) != {"argument", "attribute", "format", "max_bytes"}
            or not isinstance(entry.get("argument"), str)
            or not entry["argument"].startswith("--")
            or not isinstance(entry.get("attribute"), str)
            or not isinstance(entry.get("format"), str)
            or entry.get("format") not in {"bytes", "json"}
            or type(entry.get("max_bytes")) is not int
            or not 0 <= entry["max_bytes"] <= RAW_INPUT_LIMIT
            or entry["argument"] in seen
        ):
            raise ContainerBrokerClientError("container_broker_manifest_invalid")
        seen.add(entry["argument"])
    return value


def load_manifest_from_environment() -> dict[str, Any]:
    inline = os.environ.get(MANIFEST_ENV)
    filename = os.environ.get(MANIFEST_FILE_ENV)
    if bool(inline) == bool(filename):
        raise ContainerBrokerClientError("container_broker_manifest_missing")
    try:
        if inline:
            raw = inline.encode("utf-8")
            if len(raw) > 256 * 1024:
                raise ContainerBrokerClientError("container_broker_manifest_invalid")
        else:
            raw = _read_stable_regular(Path(str(filename)), max_bytes=256 * 1024)
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_pairs)
    except ContainerBrokerClientError as exc:
        raise ContainerBrokerClientError("container_broker_manifest_invalid") from exc
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ContainerBrokerClientError("container_broker_manifest_invalid") from exc
    return validate_manifest(value)


def load_key_from_environment() -> bytes:
    raw_fd = os.environ.get(KEY_FD_ENV)
    filename = os.environ.get(KEY_FILE_ENV)
    if bool(raw_fd) == bool(filename):
        raise ContainerBrokerClientError("container_broker_key_missing")
    try:
        if raw_fd:
            descriptor = int(raw_fd)
            data = b""
            while len(data) <= SESSION_KEY_BYTES:
                chunk = os.read(descriptor, SESSION_KEY_BYTES + 1 - len(data))
                if not chunk:
                    break
                data += chunk
        else:
            data = _read_stable_regular(
                Path(str(filename)),
                max_bytes=SESSION_KEY_BYTES,
                require_private=True,
            )
    except ContainerBrokerClientError as exc:
        raise ContainerBrokerClientError("container_broker_key_invalid") from exc
    except (OSError, TypeError, ValueError) as exc:
        raise ContainerBrokerClientError("container_broker_key_invalid") from exc
    if len(data) != SESSION_KEY_BYTES:
        raise ContainerBrokerClientError("container_broker_key_invalid")
    return data


def _inline_inputs(manifest: dict[str, Any], arguments: Sequence[str]) -> list[dict[str, Any]]:
    option_values = _option_values(arguments)
    result: list[dict[str, Any]] = []
    total = 0
    for spec in manifest["inline_inputs"]:
        paths = option_values.get(spec["argument"], [])
        if len(paths) != 1 or not paths[0]:
            raise ContainerBrokerClientError("container_broker_input_missing")
        data = _read_stable_regular(Path(paths[0]), max_bytes=spec["max_bytes"])
        total += len(data)
        if total > manifest["raw_input_limit"]:
            raise ContainerBrokerClientError("container_broker_input_oversize")
        result.append(
            {
                "argument": spec["argument"],
                "size": len(data),
                "sha256": _sha256(data),
                "content_base64": base64.b64encode(data).decode("ascii"),
            }
        )
    return result


def _envelope(
    manifest: dict[str, Any], key: bytes, payload: dict[str, Any], *, nonce: bytes | None = None
) -> dict[str, Any]:
    manifest = validate_manifest(manifest)
    if not isinstance(key, bytes) or len(key) != SESSION_KEY_BYTES:
        raise ContainerBrokerClientError("container_broker_key_invalid")
    nonce = os.urandom(NONCE_BYTES) if nonce is None else nonce
    if not isinstance(nonce, bytes) or len(nonce) != NONCE_BYTES:
        raise ContainerBrokerClientError("container_broker_nonce_invalid")
    try:
        unsigned = {
            "schema_version": PROTOCOL_VERSION,
            "message_kind": "request",
            "runtime_identity": manifest["runtime_identity"],
            "runtime_session_ref": manifest["runtime_session_ref"],
            "action_id": manifest["action_id"],
            "deadline_ref": manifest["deadline_ref"],
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "payload_sha256": _sha256(canonical_json_bytes(payload)),
            "payload": payload,
        }
        return {**unsigned, "mac_base64": _mac(key, REQUEST_DOMAIN, unsigned)}
    except (UnicodeError, TypeError, ValueError, RecursionError, OverflowError) as exc:
        raise ContainerBrokerClientError("container_broker_request_invalid") from exc


def send_frame(connection: socket.socket, value: dict[str, Any]) -> None:
    data = canonical_json_bytes(value)
    if len(data) > FRAME_LIMIT:
        raise ContainerBrokerClientError("container_broker_frame_oversize")
    connection.sendall(struct.pack("!I", len(data)) + data)


def _recv_exact(
    connection: socket.socket, size: int, *, deadline: float | None = None
) -> bytes:
    result = bytearray()
    previous_timeout = connection.gettimeout() if deadline is not None else None
    try:
        while len(result) < size:
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise socket.timeout("container broker frame deadline")
                timeout = (
                    remaining
                    if previous_timeout is None
                    else min(previous_timeout, remaining)
                )
                connection.settimeout(timeout)
            chunk = connection.recv(size - len(result))
            if not chunk:
                raise ContainerBrokerClientError("container_broker_response_invalid")
            result.extend(chunk)
    finally:
        if deadline is not None:
            connection.settimeout(previous_timeout)
    return bytes(result)


def recv_frame(
    connection: socket.socket, *, timeout: float | None = None
) -> dict[str, Any]:
    deadline = None if timeout is None else time.monotonic() + timeout
    length = struct.unpack("!I", _recv_exact(connection, 4, deadline=deadline))[0]
    if length <= 0 or length > FRAME_LIMIT:
        raise ContainerBrokerClientError("container_broker_response_invalid")
    try:
        value = json.loads(
            _recv_exact(connection, length, deadline=deadline),
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise ContainerBrokerClientError("container_broker_response_invalid") from exc
    if not isinstance(value, dict):
        raise ContainerBrokerClientError("container_broker_response_invalid")
    return value


def _validate_response(
    manifest: dict[str, Any], key: bytes, response: dict[str, Any], request_nonce: str
) -> dict[str, Any]:
    manifest = validate_manifest(manifest)
    if set(response) != {
        "schema_version",
        "message_kind",
        "runtime_identity",
        "runtime_session_ref",
        "action_id",
        "deadline_ref",
        "request_nonce",
        "payload_sha256",
        "payload",
        "mac_base64",
    }:
        raise ContainerBrokerClientError("container_broker_response_invalid")
    unsigned = dict(response)
    raw_mac = unsigned.pop("mac_base64")
    try:
        received_mac = base64.b64decode(raw_mac, validate=True)
    except (binascii.Error, TypeError, ValueError) as exc:
        raise ContainerBrokerClientError("container_broker_response_invalid") from exc
    expected_mac = base64.b64decode(_mac(key, RESPONSE_DOMAIN, unsigned), validate=True)
    if not hmac.compare_digest(received_mac, expected_mac):
        raise ContainerBrokerClientError("container_broker_response_auth_invalid")
    payload = response.get("payload")
    if (
        type(response.get("schema_version")) is not int
        or response["schema_version"] != PROTOCOL_VERSION
        or response.get("message_kind") != "response"
        or response.get("runtime_identity") != manifest["runtime_identity"]
        or response.get("runtime_session_ref") != manifest["runtime_session_ref"]
        or response.get("action_id") != manifest["action_id"]
        or response.get("deadline_ref") != manifest["deadline_ref"]
        or response.get("request_nonce") != request_nonce
        or response.get("payload_sha256") != _sha256(canonical_json_bytes(payload))
        or not isinstance(payload, dict)
        or set(payload) != {"returncode", "stdout_base64"}
        or type(payload.get("returncode")) is not int
        or not 0 <= payload["returncode"] <= 255
        or not isinstance(payload.get("stdout_base64"), str)
    ):
        raise ContainerBrokerClientError("container_broker_response_invalid")
    try:
        output = base64.b64decode(payload["stdout_base64"], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ContainerBrokerClientError("container_broker_response_invalid") from exc
    if len(output) > RAW_INPUT_LIMIT:
        raise ContainerBrokerClientError("container_broker_response_invalid")
    return {"returncode": payload["returncode"], "output": output}


def _exchange(
    manifest: dict[str, Any], key: bytes, payload: dict[str, Any], *, nonce: bytes | None = None
) -> dict[str, Any]:
    request = _envelope(manifest, key, payload, nonce=nonce)
    endpoint = manifest["endpoint"]
    connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    connection.settimeout(IO_TIMEOUT_SECONDS)
    try:
        connection.connect((endpoint["host"], endpoint["port"]))
        send_frame(connection, request)
        connection.shutdown(socket.SHUT_WR)
        # Admission is exactly once and the trusted mutation may legitimately outlive the fixed
        # connect/write timeout.  Once the complete authenticated frame is sent, a client-side
        # response timeout would create an ambiguous commit and tempt an unsafe retry.  The host
        # broker enforces its bound deadline; the outer container deadline remains the liveness
        # backstop if the host disappears.
        connection.settimeout(None)
        response = recv_frame(connection)
    except (OSError, TimeoutError) as exc:
        raise ContainerBrokerClientError("container_broker_unavailable") from exc
    finally:
        connection.close()
    return _validate_response(manifest, key, response, request["nonce"])


def forward_action(
    manifest: dict[str, Any], key: bytes, *, command: str, arguments: Sequence[str]
) -> tuple[int, bytes]:
    if (
        not isinstance(command, str)
        or not command
        or isinstance(arguments, (str, bytes))
        or not isinstance(arguments, Sequence)
    ):
        raise ContainerBrokerClientError("container_broker_request_invalid")
    frozen_arguments = list(arguments)
    if any(not isinstance(value, str) for value in frozen_arguments):
        raise ContainerBrokerClientError("container_broker_request_invalid")
    payload = {
        "request_kind": "action",
        "command": command,
        "arguments": frozen_arguments,
        "runtime_session_ref": manifest.get("runtime_session_ref"),
        "inline_inputs": _inline_inputs(
            validate_manifest(manifest), frozen_arguments
        ),
    }
    result = _exchange(manifest, key, payload)
    return result["returncode"], result["output"]


def forward_stop(
    manifest: dict[str, Any],
    key: bytes,
    *,
    hook_session_ref: str,
    stop_hook_active: bool,
    request_ref: str,
) -> tuple[int, bytes]:
    if (
        not isinstance(hook_session_ref, str)
        or SHA256_RE.fullmatch(hook_session_ref) is None
        or type(stop_hook_active) is not bool
        or not isinstance(request_ref, str)
        or SHA256_RE.fullmatch(request_ref) is None
    ):
        raise ContainerBrokerClientError("container_broker_request_invalid")
    payload = {
        "request_kind": "session_end_check",
        "runtime_session_ref": manifest.get("runtime_session_ref"),
        "hook_session_ref": hook_session_ref,
        "stop_hook_active": stop_hook_active,
        "request_ref": request_ref,
    }
    result = _exchange(validate_manifest(manifest), key, payload)
    return result["returncode"], result["output"]


def stream_provider(
    manifest: dict[str, Any],
    key: bytes,
    *,
    path: str,
    headers: dict[str, str],
    body: bytes,
    on_headers: Any,
    on_chunk: Any,
) -> int:
    """Receive authenticated provider frames and release each body chunk immediately."""

    if not callable(on_headers) or not callable(on_chunk):
        raise ContainerBrokerClientError("container_broker_provider_invalid")
    # Reuse the request validation and payload shape without performing a second exchange.
    if (
        path not in {"/v1/messages", "/v1/messages?beta=true"}
        or not isinstance(headers, dict)
        or any(
            not isinstance(name, str)
            or not isinstance(value, str)
            or name.lower() not in {"accept", "content-type", "anthropic-version", "anthropic-beta"}
            or "\r" in value
            or "\n" in value
            for name, value in headers.items()
        )
        or not isinstance(body, bytes)
        or len(body) > RAW_INPUT_LIMIT
    ):
        raise ContainerBrokerClientError("container_broker_provider_invalid")
    payload = {
        "request_kind": "provider_request",
        "method": "POST",
        "path": path,
        "headers": {name.lower(): value for name, value in headers.items()},
        "body_base64": base64.b64encode(body).decode("ascii"),
        "runtime_session_ref": manifest.get("runtime_session_ref"),
    }
    request = _envelope(validate_manifest(manifest), key, payload)
    endpoint = manifest["endpoint"]
    connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    connection.settimeout(IO_TIMEOUT_SECONDS)
    expected_sequence = 0
    total = 0
    saw_headers = False
    try:
        connection.connect((endpoint["host"], endpoint["port"]))
        send_frame(connection, request)
        connection.shutdown(socket.SHUT_WR)
        connection.settimeout(None)
        while True:
            authenticated = _validate_response(
                manifest, key, recv_frame(connection), request["nonce"]
            )
            if authenticated["returncode"] != 0:
                raise ContainerBrokerClientError("container_broker_provider_response_invalid")
            try:
                frame = json.loads(
                    authenticated["output"], object_pairs_hook=_reject_duplicate_pairs
                )
            except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
                raise ContainerBrokerClientError("container_broker_provider_response_invalid") from exc
            if not isinstance(frame, dict):
                raise ContainerBrokerClientError("container_broker_provider_response_invalid")
            if frame.get("stream") == "headers" and not saw_headers:
                if (
                    set(frame) != {"stream", "status", "headers"}
                    or type(frame.get("status")) is not int
                    or not 100 <= frame["status"] <= 599
                    or not isinstance(frame.get("headers"), list)
                ):
                    raise ContainerBrokerClientError("container_broker_provider_response_invalid")
                on_headers(frame["status"], frame["headers"])
                saw_headers = True
                continue
            if frame.get("stream") == "chunk" and saw_headers:
                if set(frame) != {"stream", "sequence", "body_base64"} or frame.get("sequence") != expected_sequence:
                    raise ContainerBrokerClientError("container_broker_provider_response_invalid")
                try:
                    chunk = base64.b64decode(frame["body_base64"], validate=True)
                except (binascii.Error, TypeError, ValueError) as exc:
                    raise ContainerBrokerClientError("container_broker_provider_response_invalid") from exc
                total += len(chunk)
                if not chunk or total > RAW_INPUT_LIMIT:
                    raise ContainerBrokerClientError("container_broker_provider_response_invalid")
                on_chunk(chunk)
                expected_sequence += 1
                continue
            if frame == {"stream": "end", "sequence": expected_sequence} and saw_headers:
                return total
            raise ContainerBrokerClientError("container_broker_provider_response_invalid")
    except (OSError, TimeoutError) as exc:
        raise ContainerBrokerClientError("container_broker_unavailable") from exc
    finally:
        connection.close()


def forward_target_fetch(
    manifest: dict[str, Any], key: bytes, *, request_id: str, url: str, method: str
) -> tuple[int, bytes]:
    expected_request_id = target_fetch_request_id(manifest, url=url, method=method)
    if (
        not isinstance(request_id, str)
        or request_id != expected_request_id
        or not isinstance(url, str)
        or not 1 <= len(url) <= 8192
        or not isinstance(method, str)
        or method not in {"GET", "HEAD"}
    ):
        raise ContainerBrokerClientError("container_broker_target_fetch_invalid")
    payload = {
        "request_kind": "target_fetch",
        "operation": "target_fetch",
        "request_id": request_id,
        "url": url,
        "method": method,
        "runtime_session_ref": manifest.get("runtime_session_ref"),
    }
    result = _exchange(validate_manifest(manifest), key, payload)
    return result["returncode"], result["output"]


def target_fetch_request_id(
    manifest: dict[str, Any], *, url: str, method: str
) -> str:
    validated = validate_manifest(manifest)
    return _sha256(
        TARGET_FETCH_ID_DOMAIN
        + canonical_json_bytes(
            {
                "runtime_session_ref": validated.get("runtime_session_ref"),
                "action_id": validated.get("action_id"),
                "url": url,
                "method": method,
            }
        )
    )


def _validate_relay_request(value: Any) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or type(value.get("schema_version")) is not int
        or value["schema_version"] != PROTOCOL_VERSION
    ):
        raise ContainerBrokerClientError("container_broker_relay_request_invalid")
    kind = value.get("request_kind")
    if kind == "action":
        if set(value) != {"schema_version", "request_kind", "command", "arguments"}:
            raise ContainerBrokerClientError("container_broker_relay_request_invalid")
        command = value.get("command")
        arguments = value.get("arguments")
        try:
            arguments_valid = bool(
                isinstance(arguments, list)
                and len(arguments) <= 1024
                and all(
                    isinstance(argument, str)
                    and "\x00" not in argument
                    and len(argument.encode("utf-8")) <= 128 * 1024
                    for argument in arguments
                )
            )
            command_valid = bool(
                isinstance(command, str)
                and command
                and "\x00" not in command
                and len(command.encode("utf-8")) <= 128 * 1024
            )
        except UnicodeError:
            arguments_valid = command_valid = False
        if (
            not command_valid
            or not arguments_valid
        ):
            raise ContainerBrokerClientError("container_broker_relay_request_invalid")
    elif kind == "session_end_check":
        if set(value) != {
            "schema_version",
            "request_kind",
            "hook_session_ref",
            "stop_hook_active",
            "request_ref",
        }:
            raise ContainerBrokerClientError("container_broker_relay_request_invalid")
        if (
            not isinstance(value.get("hook_session_ref"), str)
            or SHA256_RE.fullmatch(value["hook_session_ref"]) is None
            or type(value.get("stop_hook_active")) is not bool
            or not isinstance(value.get("request_ref"), str)
            or SHA256_RE.fullmatch(value["request_ref"]) is None
        ):
            raise ContainerBrokerClientError("container_broker_relay_request_invalid")
    elif kind == "target_fetch":
        if set(value) != {"schema_version", "request_kind", "request_id", "url", "method"}:
            raise ContainerBrokerClientError("container_broker_relay_request_invalid")
        if (
            not isinstance(value.get("request_id"), str)
            or SHA256_RE.fullmatch(value["request_id"]) is None
            or not isinstance(value.get("url"), str)
            or not 1 <= len(value["url"]) <= 8192
            or not isinstance(value.get("method"), str)
            or value["method"] not in {"GET", "HEAD"}
        ):
            raise ContainerBrokerClientError("container_broker_relay_request_invalid")
    else:
        raise ContainerBrokerClientError("container_broker_relay_request_invalid")
    return value


def handle_relay_request(
    manifest: dict[str, Any], key: bytes, request: dict[str, Any]
) -> tuple[int, bytes]:
    """Validate one local semantic operation and authenticate it to the host broker."""

    request = _validate_relay_request(request)
    if request["request_kind"] == "action":
        return forward_action(
            manifest,
            key,
            command=request["command"],
            arguments=request["arguments"],
        )
    if request["request_kind"] == "session_end_check":
        return forward_stop(
            manifest,
            key,
            hook_session_ref=request["hook_session_ref"],
            stop_hook_active=request["stop_hook_active"],
            request_ref=request["request_ref"],
        )
    return forward_target_fetch(
        manifest,
        key,
        request_id=request["request_id"],
        url=request["url"],
        method=request["method"],
    )


def relay_response(*, returncode: int, output: bytes) -> dict[str, Any]:
    if (
        type(returncode) is not int
        or not 0 <= returncode <= 255
        or not isinstance(output, bytes)
        or len(output) > RAW_INPUT_LIMIT
    ):
        raise ContainerBrokerClientError("container_broker_relay_response_invalid")
    return {
        "schema_version": PROTOCOL_VERSION,
        "returncode": returncode,
        "output_base64": base64.b64encode(output).decode("ascii"),
    }


def _relay_socket_from_environment() -> Path:
    value = os.environ.get(RELAY_SOCKET_ENV)
    if (
        not isinstance(value, str)
        or RELAY_PATH_RE.fullmatch(value) is None
        or any(os.environ.get(name) for name in (KEY_FD_ENV, KEY_FILE_ENV))
    ):
        raise ContainerBrokerClientError("container_broker_relay_missing")
    path = Path(value)
    if Path(os.path.normpath(value)) != path:
        raise ContainerBrokerClientError("container_broker_relay_missing")
    return path


def _relay_exchange(request: dict[str, Any]) -> tuple[int, bytes]:
    request = _validate_relay_request(request)
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.settimeout(IO_TIMEOUT_SECONDS)
    try:
        connection.connect(str(_relay_socket_from_environment()))
        send_frame(connection, request)
        connection.shutdown(socket.SHUT_WR)
        # Once the complete semantic request has reached PID 1, timing out would make a committed
        # host mutation indistinguishable from a failed relay and invite an unsafe retry.  The
        # host broker deadline and outer container timeout remain the liveness bounds.
        connection.settimeout(None)
        response = recv_frame(connection)
    except (OSError, TimeoutError) as exc:
        raise ContainerBrokerClientError("container_broker_relay_unavailable") from exc
    finally:
        connection.close()
    if (
        set(response) != {"schema_version", "returncode", "output_base64"}
        or type(response.get("schema_version")) is not int
        or response["schema_version"] != PROTOCOL_VERSION
        or type(response.get("returncode")) is not int
        or not 0 <= response["returncode"] <= 255
        or not isinstance(response.get("output_base64"), str)
    ):
        raise ContainerBrokerClientError("container_broker_relay_response_invalid")
    try:
        output = base64.b64decode(response["output_base64"], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ContainerBrokerClientError("container_broker_relay_response_invalid") from exc
    if len(output) > RAW_INPUT_LIMIT:
        raise ContainerBrokerClientError("container_broker_relay_response_invalid")
    return response["returncode"], output


def relay_action(*, command: str, arguments: Sequence[str]) -> tuple[int, bytes]:
    return _relay_exchange(
        {
            "schema_version": PROTOCOL_VERSION,
            "request_kind": "action",
            "command": command,
            "arguments": list(arguments),
        }
    )


def relay_stop(
    *, hook_session_ref: str, stop_hook_active: bool, request_ref: str
) -> tuple[int, bytes]:
    return _relay_exchange(
        {
            "schema_version": PROTOCOL_VERSION,
            "request_kind": "session_end_check",
            "hook_session_ref": hook_session_ref,
            "stop_hook_active": stop_hook_active,
            "request_ref": request_ref,
        }
    )


def relay_target_fetch(*, request_id: str, url: str, method: str) -> tuple[int, bytes]:
    return _relay_exchange({
        "schema_version": PROTOCOL_VERSION,
        "request_kind": "target_fetch",
        "request_id": request_id,
        "url": url,
        "method": method,
    })


def _parse_stop_hook_input(raw: bytes) -> tuple[str, bool, str]:
    """Reduce one Claude Stop delivery to the same three opaque fields as the POSIX hook."""

    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_STOP_HOOK_STDIN_BYTES:
        raise ContainerBrokerClientError("container_broker_stop_hook_invalid")
    try:
        incoming = json.loads(raw, object_pairs_hook=_reject_duplicate_pairs)
    except (
        UnicodeError,
        json.JSONDecodeError,
        ValueError,
        RecursionError,
    ) as exc:
        raise ContainerBrokerClientError("container_broker_stop_hook_invalid") from exc
    if not isinstance(incoming, dict) or "agent_id" in incoming or "agent_type" in incoming:
        raise ContainerBrokerClientError("container_broker_stop_hook_invalid")
    session_id = incoming.get("session_id")
    if (
        incoming.get("hook_event_name") != "Stop"
        or type(incoming.get("stop_hook_active")) is not bool
        or not isinstance(session_id, str)
        or not 1 <= len(session_id) <= 512
    ):
        raise ContainerBrokerClientError("container_broker_stop_hook_invalid")
    try:
        session_bytes = session_id.encode("utf-8")
    except UnicodeError as exc:
        raise ContainerBrokerClientError("container_broker_stop_hook_invalid") from exc
    return (
        _sha256(STOP_SESSION_DOMAIN + session_bytes),
        incoming["stop_hook_active"],
        _sha256(STOP_REQUEST_DOMAIN + raw),
    )


def _valid_stop_hook_output(output: bytes) -> bool:
    try:
        value = json.loads(output, object_pairs_hook=_reject_duplicate_pairs)
    except (
        UnicodeError,
        json.JSONDecodeError,
        ValueError,
        RecursionError,
    ):
        return False
    return bool(
        value == {}
        or (
            isinstance(value, dict)
            and set(value) == {"decision", "reason"}
            and value.get("decision") == "block"
            and isinstance(value.get("reason"), str)
            and bool(value["reason"])
        )
        or (
            isinstance(value, dict)
            and set(value) == {"systemMessage"}
            and isinstance(value.get("systemMessage"), str)
            and bool(value["systemMessage"])
        )
    )


def run_stop_hook() -> int:
    """Run the stdin-facing Claude Stop adapter; every local failure releases with ``{}``."""

    try:
        raw = sys.stdin.buffer.read(MAX_STOP_HOOK_STDIN_BYTES + 1)
        hook_session_ref, stop_hook_active, request_ref = _parse_stop_hook_input(raw)
        if os.environ.get(RELAY_SOCKET_ENV):
            returncode, output = relay_stop(
                hook_session_ref=hook_session_ref,
                stop_hook_active=stop_hook_active,
                request_ref=request_ref,
            )
        else:
            manifest = load_manifest_from_environment()
            key = load_key_from_environment()
            returncode, output = forward_stop(
                manifest,
                key,
                hook_session_ref=hook_session_ref,
                stop_hook_active=stop_hook_active,
                request_ref=request_ref,
            )
        if returncode != 0 or not _valid_stop_hook_output(output):
            raise ContainerBrokerClientError("container_broker_stop_hook_rejected")
    except Exception:
        # This executable is a Claude Stop hook boundary. Never echo raw deliveries, target paths,
        # transport details, or broker errors: exit-zero ``{}`` is the platform's fail-open form.
        output = canonical_json_bytes({})
    sys.stdout.buffer.write(output)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="mode", required=True)
    action = subcommands.add_parser("action")
    action.add_argument("--command", required=True)
    action.add_argument("--arguments-json", required=True)
    stop = subcommands.add_parser("stop")
    stop.add_argument("--hook-session-ref", required=True)
    stop.add_argument("--stop-hook-active", choices=("true", "false"), required=True)
    stop.add_argument("--request-ref", required=True)
    subcommands.add_parser("stop-hook")
    target = subcommands.add_parser("target-fetch")
    target.add_argument("--request-id", required=True)
    target.add_argument("--url", required=True)
    target.add_argument("--method", choices=("GET", "HEAD"), required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.mode == "stop-hook":
        return run_stop_hook()
    try:
        if args.mode == "target-fetch":
            if os.environ.get(RELAY_SOCKET_ENV):
                returncode, output = relay_target_fetch(
                    request_id=args.request_id, url=args.url, method=args.method
                )
            else:
                returncode, output = forward_target_fetch(
                    load_manifest_from_environment(), load_key_from_environment(),
                    request_id=args.request_id, url=args.url, method=args.method,
                )
        elif args.mode == "action":
            arguments = json.loads(args.arguments_json)
            if not isinstance(arguments, list) or any(not isinstance(v, str) for v in arguments):
                raise ContainerBrokerClientError("container_broker_request_invalid")
            if os.environ.get(RELAY_SOCKET_ENV):
                returncode, output = relay_action(
                    command=args.command, arguments=arguments
                )
            else:
                manifest = load_manifest_from_environment()
                key = load_key_from_environment()
                returncode, output = forward_action(
                    manifest, key, command=args.command, arguments=arguments
                )
        else:
            if os.environ.get(RELAY_SOCKET_ENV):
                returncode, output = relay_stop(
                    hook_session_ref=args.hook_session_ref,
                    stop_hook_active=args.stop_hook_active == "true",
                    request_ref=args.request_ref,
                )
            else:
                manifest = load_manifest_from_environment()
                key = load_key_from_environment()
                returncode, output = forward_stop(
                    manifest,
                    key,
                    hook_session_ref=args.hook_session_ref,
                    stop_hook_active=args.stop_hook_active == "true",
                    request_ref=args.request_ref,
                )
        sys.stdout.buffer.write(output)
        return returncode
    except (ContainerBrokerClientError, json.JSONDecodeError):
        sys.stdout.buffer.write(
            canonical_json_bytes(
                {"valid": False, "error": {"code": "container_broker_client_failed"}}
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
