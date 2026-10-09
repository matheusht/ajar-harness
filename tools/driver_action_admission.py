#!/usr/bin/env python3
"""One-shot admission for reducer-selected work-queue mutations.

The outer driver arms one exact reducer action before starting a fresh runtime.  A public
``run-engagement`` mutation in that runtime must consume the admission atomically before its
first write.  The record is target-local; a short-lived process-session registry prevents an
unset scope environment from silently falling back to an ordinary unscoped command.
"""

from __future__ import annotations

import base64
import binascii
import copy
import fcntl
import hashlib
import hmac
import http.client
import importlib.util
import json
import math
import os
import re
import secrets
import socket
import stat
import struct
import sys
import tempfile
import threading
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any

from engagement_records import RecordError, _reject_duplicate_pairs, canonical_json_bytes, detect_secret_classes, sha256_bytes
from engagement_state import (
    _reduce_engagement_unchecked,
    append_event,
    atomic_write,
    base_event,
    bound_engagement_lock,
    engagement_lock,
    read_governed_file,
    read_ledger,
    unlink_governed_file,
    utc_now,
)
from work_queue_actions import queue_command_payload


ADMISSION_FILE = ".work-queue-action-admission.json"
NETWORK_RECEIPTS_FILE = ".work-queue-network-receipts.jsonl"
NETWORK_RECEIPTS_MAX_BYTES = 256 * 1024
NETWORK_RECEIPTS_MAX_ROWS = 256
TOKEN_ENV = "HARNESS_EXPECTED_ACTION_TOKEN"
SESSION_ENV = "HARNESS_EXPECTED_RUNTIME_SESSION_REF"
BROKER_ENDPOINT_ENV = "HARNESS_DRIVER_ACTION_BROKER"
_RPC_LIMIT = 4 * 1024 * 1024
_MODEL_JSON_LIMIT = _RPC_LIMIT
_REVIEW_SIGNATURE_LIMIT = 256 * 1024
_REVIEW_ALLOWED_SIGNERS_LIMIT = 1024 * 1024
_BROKER_IO_TIMEOUT_SECONDS = 2.0
_CONTAINER_SESSION_KEY_BYTES = 32
_CONTAINER_NONCE_BYTES = 32
_CONTAINER_FRAME_LIMIT = 12 * 1024 * 1024
_CONTAINER_RAW_INPUT_LIMIT = _RPC_LIMIT
_PROVIDER_MAX_OUTPUT_TOKENS = 32768
_CONTAINER_ACTION_NONCE_BUDGET = 32
_CONTAINER_PROVIDER_NONCE_BUDGET = 32
_CONTAINER_TARGET_FETCH_NONCE_BUDGET = 32
_CONTAINER_REQUEST_DOMAIN = b"llm-redteam-harness:container-broker:request:v1\0"
_CONTAINER_RESPONSE_DOMAIN = b"llm-redteam-harness:container-broker:response:v1\0"
_TARGET_FETCH_ID_DOMAIN = b"llm-redteam-harness:target-fetch-id:v1\0"
_CONTAINER_ID_RE = re.compile(r"[0-9a-f]{64}\Z")
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_STOP_BLOCK_BUDGET = 6
_STOP_REQUEST_BUDGET = _STOP_BLOCK_BUDGET + 1
_PROVIDER_FORBIDDEN_CAPABILITY_FIELDS = frozenset(
    {"container", "mcp_servers", "skills"}
)
_PROVIDER_INFERENCE_FIELDS = frozenset(
    {
        "cache_control",
        "context_management",
        "inference_geo",
        "max_tokens",
        "messages",
        "metadata",
        "model",
        "output_config",
        "output_format",
        "service_tier",
        "speed",
        "stop_sequences",
        "stream",
        "system",
        "temperature",
        "thinking",
        "tool_choice",
        "tools",
        "top_k",
        "top_p",
    }
)
_PROVIDER_CLIENT_TOOL_FIELDS = frozenset(
    {
        "allowed_callers",
        "cache_control",
        "description",
        "input_examples",
        "input_schema",
        "name",
        "strict",
        "type",
    }
)
_SESSION_AUDIT_STATE_KEYS = frozenset(
    {"event_count", "last_event_id", "ledger_hash", "source_hashes"}
)
READ_ONLY_COMMANDS = frozenset(
    {
        "validate",
        "runtime-identity",
        "ledger-health",
        "check-completion-claims",
        "check-resume",
        "render-proof",
        "next",
        "list",
        "gate",
    }
)
OPERATOR_GOVERNANCE_COMMANDS = frozenset({"operator-stop", "operator-resume", "override-ending"})
_ALLOWED_ADMISSION_KEYS = {
    "schema_version",
    "status",
    "driver_run_ref",
    "token_hash",
    "runtime_session_ref",
    "runtime_model",
    "provider_max_tokens",
    "runtime_session_kind",
    "hook_session_ref",
    "os_session_id",
    "runtime_identity",
    "engagement_identity",
    "state_binding",
    "item_ref",
    "item_identity",
    "action_id",
    "command",
    "argument_template",
    "action_hash",
    "predicate",
    "cognitive_principal",
    "view_type",
    "view_digest",
    "input_corpus_digest",
    "treatment",
}


def new_admission_token() -> str:
    return secrets.token_urlsafe(32)


def new_container_broker_session_key() -> bytes:
    """Return a fresh 256-bit key for exactly one Docker broker/runtime pair."""

    return secrets.token_bytes(_CONTAINER_SESSION_KEY_BYTES)


def _token_hash(token: str) -> str:
    return sha256_bytes(token.encode("utf-8"))


def _posix_runtime_identity(os_session_id: int) -> dict[str, Any]:
    if type(os_session_id) is not int or os_session_id <= 0:
        raise RecordError("driver_action_os_session_invalid", str(os_session_id))
    return {"kind": "posix_session", "os_session_id": os_session_id}


def _docker_runtime_identity(
    container_id: str, container_config_digest: str
) -> dict[str, Any]:
    if (
        not isinstance(container_id, str)
        or _CONTAINER_ID_RE.fullmatch(container_id) is None
        or not isinstance(container_config_digest, str)
        or _SHA256_RE.fullmatch(container_config_digest) is None
    ):
        raise RecordError("driver_action_container_identity_invalid", "docker container")
    return {
        "kind": "docker_container",
        "container_id": container_id,
        "container_config_digest": container_config_digest,
    }


def _active_runtime_identity(record: dict[str, Any]) -> dict[str, Any] | None:
    """Return one validated runtime identity, accepting legacy in-memory POSIX test records."""

    identity = record.get("runtime_identity")
    if identity is None:
        legacy_session = record.get("os_session_id")
        if type(legacy_session) is int and legacy_session > 0:
            return _posix_runtime_identity(legacy_session)
        return None
    if not isinstance(identity, dict):
        raise RecordError("driver_action_runtime_identity_invalid", "runtime identity")
    if identity.get("kind") == "posix_session" and set(identity) == {
        "kind",
        "os_session_id",
    }:
        validated = _posix_runtime_identity(identity.get("os_session_id"))
        if record.get("os_session_id") != validated["os_session_id"]:
            raise RecordError("driver_action_runtime_identity_invalid", "POSIX identity")
        return validated
    if identity.get("kind") == "docker_container" and set(identity) == {
        "kind",
        "container_id",
        "container_config_digest",
    }:
        if record.get("os_session_id") is not None:
            raise RecordError("driver_action_runtime_identity_invalid", "Docker identity")
        return _docker_runtime_identity(
            identity.get("container_id"), identity.get("container_config_digest")
        )
    raise RecordError("driver_action_runtime_identity_invalid", "runtime identity")


def _container_hmac(
    key: bytes, domain: bytes, value: dict[str, Any]
) -> bytes:
    return hmac.new(
        key, domain + canonical_json_bytes(value), hashlib.sha256
    ).digest()


def _deadline_ref(
    *, admission: dict[str, Any], identity: dict[str, Any], deadline: float
) -> str:
    return sha256_bytes(
        canonical_json_bytes(
            {
                "schema_version": 1,
                "runtime_session_ref": admission.get("runtime_session_ref"),
                "action_id": admission.get("action_id"),
                "runtime_identity": identity,
                "deadline_monotonic_ns": int(deadline * 1_000_000_000),
            }
        )
    )


def _registry_root() -> Path:
    return Path(tempfile.gettempdir()) / f"llm-redteam-harness-driver-{os.getuid()}"


def _registry_path(os_session_id: int) -> Path:
    return _registry_root() / f"session-{os_session_id}.json"


def _ensure_registry_root() -> Path:
    root = _registry_root()
    try:
        root.mkdir(mode=0o700)
    except FileExistsError:
        pass
    entry = root.lstat()
    if stat.S_ISLNK(entry.st_mode) or not stat.S_ISDIR(entry.st_mode) or entry.st_uid != os.getuid():
        raise RecordError("driver_admission_registry_unsafe", "runtime registry")
    if stat.S_IMODE(entry.st_mode) & 0o077:
        os.chmod(root, 0o700)
    return root


def _ensure_broker_root() -> Path:
    """Use a short private path: Darwin limits AF_UNIX names to roughly 104 bytes."""

    root = Path("/tmp") / f"lrh-action-broker-{os.getuid()}"
    try:
        root.mkdir(mode=0o700)
    except FileExistsError:
        pass
    entry = root.lstat()
    if stat.S_ISLNK(entry.st_mode) or not stat.S_ISDIR(entry.st_mode) or entry.st_uid != os.getuid():
        raise RecordError("driver_action_broker_unavailable", "unsafe root")
    if stat.S_IMODE(entry.st_mode) & 0o077:
        os.chmod(root, 0o700)
    return root


def _read_regular_bytes(
    path: Path, *, max_bytes: int, error_code: str
) -> bytes:
    """Read one stable regular file without following its leaf and without over-allocation."""

    if max_bytes < 0:
        raise ValueError("max_bytes must be non-negative")
    # O_NONBLOCK prevents a model-supplied FIFO from wedging the authenticated broker before the
    # regular-file fstat gate. It has no effect on ordinary regular-file reads.
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        absolute = Path(os.path.abspath(path))
        if len(absolute.parts) == 5 and absolute.parts[1:3] == ("dev", "fd") and absolute.parts[3].isdigit():
            fd = os.open(absolute.parts[4], flags, dir_fd=int(absolute.parts[3]))
        else:
            fd = os.open(absolute, flags)
    except OSError as exc:
        raise RecordError(error_code, path.name) from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > max_bytes:
            raise RecordError(error_code, path.name)
        raw = bytearray()
        while True:
            remaining = max_bytes - len(raw)
            chunk = os.read(fd, min(1024 * 1024, remaining + 1))
            if not chunk:
                break
            raw.extend(chunk)
            if len(raw) > max_bytes:
                raise RecordError(error_code, path.name)
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise RecordError(error_code, path.name)
    finally:
        os.close(fd)
    return bytes(raw)


def _read_regular_json_bytes(path: Path, *, error_code: str) -> tuple[dict[str, Any], bytes]:
    raw = _read_regular_bytes(
        path,
        max_bytes=_MODEL_JSON_LIMIT,
        error_code=error_code,
    )
    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_pairs)
    except RecordError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise RecordError(error_code, path.name) from exc
    if not isinstance(value, dict):
        raise RecordError(error_code, path.name)
    return value, raw


def _read_regular_json(path: Path, *, error_code: str) -> dict[str, Any]:
    return _read_regular_json_bytes(path, error_code=error_code)[0]


def _identity(path: Path) -> dict[str, int]:
    try:
        absolute = Path(os.path.abspath(path))
        if len(absolute.parts) >= 4 and absolute.parts[1:3] == ("dev", "fd") and absolute.parts[3].isdigit():
            entry = os.fstat(int(absolute.parts[3]))
        else:
            entry = os.stat(absolute, follow_symlinks=False)
    except OSError as exc:
        raise RecordError("driver_admission_engagement_unavailable", str(path)) from exc
    if not stat.S_ISDIR(entry.st_mode):
        raise RecordError("driver_admission_engagement_unavailable", str(path))
    return {"device": entry.st_dev, "inode": entry.st_ino}


def _item_identity(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "class": item.get("class"),
        "entity": copy.deepcopy(item.get("entity")),
        "predicate": item.get("predicate"),
        "closes_when": item.get("closes_when"),
        "blocking": item.get("blocking"),
    }


def _computed_item_ref(item: dict[str, Any]) -> str:
    stable = {
        "class": item.get("class"),
        "entity": item.get("entity"),
        "predicate": item.get("predicate"),
        "closes_when": item.get("closes_when"),
    }
    return sha256_bytes(canonical_json_bytes(stable))


def _normalized_action(action: dict[str, Any]) -> dict[str, Any]:
    """Remove only the render-time engagement spelling from an action contract.

    A broker executes against ``/dev/fd/N`` after binding the engagement inode.  Reducer output
    rendered before launch contains the operator's absolute pathname instead.  Those spellings
    name the same authority boundary; every other byte of the action remains immutable.
    """

    normalized = copy.deepcopy(action)
    arguments = normalized.get("arguments")
    if isinstance(arguments, list) and len(arguments) >= 2 and arguments[0] == "--engagement":
        arguments[1] = "<bound-engagement>"
    invocation = normalized.get("local_invocation")
    argv = invocation.get("argv") if isinstance(invocation, dict) else None
    command = normalized.get("command")
    if (
        isinstance(argv, list)
        and isinstance(command, str)
        and len(argv) >= 5
        and argv[2] == command
        and argv[3] == "--engagement"
    ):
        argv[4] = "<bound-engagement>"
    return normalized


def arm_action_admission(
    *,
    engagement_fd: int,
    state: dict[str, Any],
    item: dict[str, Any],
    item_ref: str,
    driver_run_ref: str,
    runtime_session_ref: str,
    runtime_model: str,
    token: str,
    view_binding: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Arm an unactivated one-shot record on the already-bound engagement inode."""

    action = item.get("next_action")
    principal_pair_valid = isinstance(action, dict) and (
        (action.get("session_kind") == "fresh_independent_reviewer" and action.get("principal") == "independent_reviewer")
        or (action.get("session_kind") == "ordinary_bounded" and action.get("principal") in {"orchestrator", "hunter", "broker"})
    )
    if (
        not isinstance(action, dict)
        or not isinstance(action.get("admission"), dict)
        or action.get("execution_principal") != "broker"
        or action.get("launchable") is not True
        or action.get("recompute_after") is not True
        or not principal_pair_valid
    ):
        raise RecordError("driver_action_predicate_missing", str(item.get("class")))
    source_hashes = state.get("source_hashes")
    if not isinstance(source_hashes, dict):
        raise RecordError("driver_action_state_binding_invalid", "source hashes")
    opened = os.fstat(engagement_fd)
    record = {
        "schema_version": 1,
        "status": "armed",
        "driver_run_ref": driver_run_ref,
        "token_hash": _token_hash(token),
        "runtime_session_ref": runtime_session_ref,
        "runtime_model": runtime_model,
        "provider_max_tokens": _PROVIDER_MAX_OUTPUT_TOKENS,
        "runtime_session_kind": action.get("session_kind"),
        "hook_session_ref": sha256_bytes(
            b"llm-redteam-harness:session-end:v1:" + runtime_session_ref.encode("utf-8")
        ),
        "os_session_id": None,
        "runtime_identity": None,
        "engagement_identity": {"device": opened.st_dev, "inode": opened.st_ino},
        "state_binding": {
            "ledger_hash": state.get("ledger_hash"),
            "source_hashes": copy.deepcopy(source_hashes),
            "event_count": state.get("event_count"),
            "scope_hash": state.get("scope_hash"),
        },
        "item_ref": item_ref,
        "item_identity": _item_identity(item),
        "action_id": action.get("action_id"),
        "command": action.get("command"),
        "argument_template": copy.deepcopy(action.get("arguments")),
        "action_hash": sha256_bytes(canonical_json_bytes(_normalized_action(action))),
        "predicate": copy.deepcopy(action["admission"]),
        "cognitive_principal": None,
        "view_type": None,
        "view_digest": None,
        "input_corpus_digest": None,
        "treatment": None,
    }
    if view_binding is not None:
        required_view = {"cognitive_principal", "view_type", "view_digest", "input_corpus_digest", "treatment"}
        if (
            set(view_binding) != required_view
            or action.get("principal") != "hunter"
            or view_binding.get("cognitive_principal") != "hunter"
            or view_binding.get("view_type") != "hunter-current-v1"
            or view_binding.get("treatment") not in {"compiled_current_only", "compiled_current_only_with_task_notices"}
            or _SHA256_RE.fullmatch(str(view_binding.get("view_digest"))) is None
            or _SHA256_RE.fullmatch(str(view_binding.get("input_corpus_digest"))) is None
        ):
            raise RecordError("driver_action_view_binding_invalid", str(record.get("action_id")))
        record.update(view_binding)
    if action.get("principal") == "hunter" and not all(record[key] for key in ("cognitive_principal", "view_type", "view_digest", "input_corpus_digest", "treatment")):
        raise RecordError("driver_action_view_binding_missing", str(record.get("action_id")))
    if (
        set(record) != _ALLOWED_ADMISSION_KEYS
        or not isinstance(record["action_id"], str)
        or not isinstance(record["command"], str)
        or not isinstance(record["argument_template"], list)
        or any(not isinstance(value, str) for value in record["argument_template"])
        or record["runtime_session_kind"] not in {"ordinary_bounded", "fresh_independent_reviewer"}
        or type(record["provider_max_tokens"]) is not int
        or record["provider_max_tokens"] <= 0
    ):
        raise RecordError("driver_action_admission_invalid", str(record.get("action_id")))
    with bound_engagement_lock(engagement_fd, create=False) as bound:
        current = _reduce_engagement_unchecked(bound)
        if sha256_bytes(canonical_json_bytes(current)) != sha256_bytes(canonical_json_bytes(state)):
            raise RecordError("driver_action_state_changed", str(record["action_id"]))
        atomic_write(bound / ADMISSION_FILE, canonical_json_bytes(record))
    # The returned copy, held only by the outer driver, is the authority.  The target-local
    # sidecar is deliberately just an observable fail-closed marker: a same-UID model process can
    # rewrite it, so no mutation decision may ever be recovered from it.
    return copy.deepcopy(record)


def activate_action_admission(
    *,
    engagement_fd: int,
    token: str,
    os_session_id: int,
    admission: dict[str, Any] | None = None,
) -> None:
    """Bind the armed record to the launched OS session before releasing its exec gate."""

    runtime_identity = _posix_runtime_identity(os_session_id)
    with bound_engagement_lock(engagement_fd, create=False) as bound:
        record = _read_regular_json(bound / ADMISSION_FILE, error_code="driver_action_admission_invalid")
        if (
            record.get("status") != "armed"
            or record.get("token_hash") != _token_hash(token)
            or record.get("os_session_id") is not None
            or record.get("runtime_identity") is not None
        ):
            raise RecordError("driver_action_admission_not_armed", str(record.get("action_id")))
        record["os_session_id"] = os_session_id
        record["runtime_identity"] = runtime_identity
        atomic_write(bound / ADMISSION_FILE, canonical_json_bytes(record))
    if admission is not None:
        if (
            admission.get("status") != "armed"
            or admission.get("token_hash") != _token_hash(token)
            or admission.get("os_session_id") is not None
            or admission.get("runtime_identity") is not None
        ):
            raise RecordError("driver_action_admission_not_armed", str(admission.get("action_id")))
        admission["os_session_id"] = os_session_id
        admission["runtime_identity"] = runtime_identity
    registry = {
        "schema_version": 1,
        "os_session_id": os_session_id,
        "runtime_identity": runtime_identity,
        "runtime_session_ref": record["runtime_session_ref"],
        "token_hash": record["token_hash"],
        "engagement_identity": record["engagement_identity"],
    }
    root = _ensure_registry_root()
    path = root / _registry_path(os_session_id).name
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise RecordError("driver_admission_registry_exists", str(os_session_id)) from exc
    try:
        data = canonical_json_bytes(registry)
        total = 0
        while total < len(data):
            total += os.write(fd, data[total:])
        os.fsync(fd)
    finally:
        os.close(fd)


def activate_docker_action_admission(
    *,
    engagement_fd: int,
    token: str,
    container_id: str,
    container_config_digest: str,
    admission: dict[str, Any] | None = None,
) -> None:
    """Bind an armed action to one exact Docker container without POSIX peer claims."""

    runtime_identity = _docker_runtime_identity(container_id, container_config_digest)
    with bound_engagement_lock(engagement_fd, create=False) as bound:
        record = _read_regular_json(
            bound / ADMISSION_FILE, error_code="driver_action_admission_invalid"
        )
        if (
            record.get("status") != "armed"
            or record.get("token_hash") != _token_hash(token)
            or record.get("os_session_id") is not None
            or record.get("runtime_identity") is not None
        ):
            raise RecordError(
                "driver_action_admission_not_armed", str(record.get("action_id"))
            )
        record["runtime_identity"] = runtime_identity
        atomic_write(bound / ADMISSION_FILE, canonical_json_bytes(record))
    if admission is not None:
        if (
            admission.get("status") != "armed"
            or admission.get("token_hash") != _token_hash(token)
            or admission.get("os_session_id") is not None
            or admission.get("runtime_identity") is not None
        ):
            raise RecordError(
                "driver_action_admission_not_armed", str(admission.get("action_id"))
            )
        admission["runtime_identity"] = copy.deepcopy(runtime_identity)


def disarm_action_admission(*, engagement_fd: int, token: str, os_session_id: int | None) -> None:
    """Remove only the caller's ephemeral admission and matching session registry."""

    # The sidecar and registry are untrusted markers.  Cleanup is keyed by the bound engagement
    # inode / OS-session name owned by this driver, not by mutable target-local contents.
    with bound_engagement_lock(engagement_fd, create=False) as bound:
        try:
            unlink_governed_file(bound / ADMISSION_FILE)
        except (FileNotFoundError, RecordError):
            pass
    if os_session_id is not None:
        path = _registry_path(os_session_id)
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _current_session_registry() -> dict[str, Any] | None:
    path = _registry_path(os.getsid(0))
    try:
        return _read_regular_json(path, error_code="driver_admission_registry_invalid")
    except RecordError:
        if not path.exists():
            return None
        raise


def _workspace_driver_lock_active(path: Path) -> bool:
    """Detect the outer structural workspace lock without relying on child environment state."""

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError:
        return False
    try:
        try:
            # A shared probe conflicts with the outer driver's exclusive lock but not with other
            # concurrent diagnostic probes.  Using an exclusive probe made ordinary CLIs
            # spuriously classify each other as an active driver.
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        else:
            fcntl.flock(fd, fcntl.LOCK_UN)
            return False
    finally:
        os.close(fd)


def _raw_argument_values(arguments: list[str]) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    index = 0
    while index < len(arguments):
        option = arguments[index]
        if not option.startswith("--"):
            index += 1
            continue
        if index + 1 < len(arguments) and not arguments[index + 1].startswith("--"):
            values.setdefault(option, []).append(arguments[index + 1])
            index += 2
        else:
            values.setdefault(option, []).append("")
            index += 1
    return values


def _match_argument_template(template: list[str], actual: list[str]) -> None:
    if len(template) != len(actual):
        raise RecordError("driver_action_arguments_mismatch", "length")
    replacements: dict[str, str] = {}
    prior_option = None
    for expected, received in zip(template, actual, strict=True):
        is_placeholder = expected.startswith("<") and expected.endswith(">")
        engagement_alias = prior_option == "--engagement" and received == "/workspace"
        if not is_placeholder and expected != received and not engagement_alias:
            raise RecordError("driver_action_arguments_mismatch", expected)
        if is_placeholder:
            if not received or (received.startswith("<") and received.endswith(">")):
                raise RecordError("driver_action_input_unresolved", expected)
            prior = replacements.setdefault(expected, received)
            if prior != received:
                raise RecordError("driver_action_input_inconsistent", expected)
        prior_option = expected


def _document_value(document: Any, path: list[str]) -> Any:
    value = document
    for part in path:
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            raise RecordError("driver_action_predicate_mismatch", "/" + "/".join(path))
    return value


def _string_set(value: Any) -> set[str] | None:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        return None
    result = set(value)
    return result if len(result) == len(value) else None


def _json_document_from_bytes(raw: bytes, *, error_code: str) -> dict[str, Any]:
    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_pairs)
    except RecordError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise RecordError(error_code, "inline JSON") from exc
    if not isinstance(value, dict):
        raise RecordError(error_code, "inline JSON")
    return value


def _validate_provider_inference_body(
    raw: bytes, *, expected_model: str, max_tokens: int
) -> None:
    """Admit inference plus client tools, never provider-side network capabilities."""

    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_pairs)
    except (RecordError, UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise RecordError("driver_provider_request_invalid", "JSON") from exc
    if (
        not isinstance(value, dict)
        or _PROVIDER_FORBIDDEN_CAPABILITY_FIELDS.intersection(value)
        or not set(value).issubset(_PROVIDER_INFERENCE_FIELDS)
        or value.get("model") != expected_model
        or type(value.get("max_tokens")) is not int
        or value["max_tokens"] <= 0
        or value["max_tokens"] > max_tokens
        or not isinstance(value.get("messages"), list)
    ):
        raise RecordError("driver_provider_capability_denied", "request capability")
    tools = value.get("tools", [])
    if not isinstance(tools, list):
        raise RecordError("driver_provider_request_invalid", "tools")
    for tool in tools:
        if (
            not isinstance(tool, dict)
            or not set(tool).issubset(_PROVIDER_CLIENT_TOOL_FIELDS)
            or tool.get("type", "custom") != "custom"
            or not isinstance(tool.get("name"), str)
            or not tool["name"]
            or not isinstance(tool.get("input_schema"), dict)
        ):
            raise RecordError("driver_provider_capability_denied", "tool")

    pending: list[Any] = [value.get("messages"), value.get("system")]
    while pending:
        item = pending.pop()
        if isinstance(item, list):
            pending.extend(item)
        elif isinstance(item, dict):
            source = item.get("source")
            if (
                item.get("type") in {"document", "image"}
                and isinstance(source, dict)
                and (source.get("type") == "url" or "url" in source)
            ):
                raise RecordError("driver_provider_capability_denied", "remote content")
            pending.extend(item.values())


def _expected_inline_inputs(record: dict[str, Any]) -> list[dict[str, Any]]:
    predicate = record.get("predicate")
    definitions = predicate.get("documents") if isinstance(predicate, dict) else None
    if not isinstance(definitions, list) or not definitions:
        raise RecordError("driver_action_predicate_invalid", "documents")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for definition in definitions:
        if not isinstance(definition, dict) or set(definition) != {"name", "argument"}:
            raise RecordError("driver_action_predicate_invalid", "document")
        argument = definition.get("argument")
        if (
            not isinstance(argument, str)
            or not argument.startswith("--")
            or argument in seen
        ):
            raise RecordError("driver_action_predicate_invalid", "document argument")
        seen.add(argument)
        result.append(
            {
                "argument": argument,
                "attribute": argument.removeprefix("--").replace("-", "_"),
                "format": "json",
                "max_bytes": _MODEL_JSON_LIMIT,
            }
        )
    if record.get("command") == "record-review":
        for argument, attribute, limit in (
            ("--signature", "signature", _REVIEW_SIGNATURE_LIMIT),
            ("--allowed-signers", "allowed_signers", _REVIEW_ALLOWED_SIGNERS_LIMIT),
        ):
            if argument in seen:
                raise RecordError("driver_action_predicate_invalid", argument)
            seen.add(argument)
            result.append(
                {
                    "argument": argument,
                    "attribute": attribute,
                    "format": "bytes",
                    "max_bytes": limit,
                }
            )
    return result


def _load_predicate_documents(
    predicate: dict[str, Any],
    arguments: list[str],
    inline_inputs: dict[str, bytes] | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    raw_values = _raw_argument_values(arguments)
    definitions = predicate.get("documents")
    if not isinstance(definitions, list) or not definitions:
        raise RecordError("driver_action_predicate_invalid", "documents")
    result: dict[str, Any] = {}
    admitted: dict[str, dict[str, Any]] = {}
    for definition in definitions:
        if not isinstance(definition, dict) or set(definition) != {"name", "argument"}:
            raise RecordError("driver_action_predicate_invalid", "document")
        name, argument = definition.get("name"), definition.get("argument")
        paths = raw_values.get(argument, [])
        if not isinstance(name, str) or not isinstance(argument, str) or len(paths) != 1 or not paths[0]:
            raise RecordError("driver_action_predicate_input_missing", str(argument))
        if inline_inputs is None:
            value, raw = _read_regular_json_bytes(
                Path(paths[0]), error_code="driver_action_predicate_input_invalid"
            )
        else:
            raw = inline_inputs.get(argument)
            if not isinstance(raw, bytes) or len(raw) > _MODEL_JSON_LIMIT:
                raise RecordError("driver_action_predicate_input_invalid", str(argument))
            value = _json_document_from_bytes(
                raw, error_code="driver_action_predicate_input_invalid"
            )
        result[name] = value
        attribute = argument.removeprefix("--").replace("-", "_")
        admitted[attribute] = {"value": value, "bytes": raw}
    return result, admitted


def _evaluate_predicate(
    predicate: dict[str, Any],
    arguments: list[str],
    inline_inputs: dict[str, bytes] | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    if predicate.get("schema_version") != 1 or set(predicate) != {"schema_version", "documents", "constraints"}:
        raise RecordError("driver_action_predicate_invalid", "shape")
    documents, admitted = _load_predicate_documents(
        predicate, arguments, inline_inputs
    )
    constraints = predicate.get("constraints")
    if not isinstance(constraints, list) or not constraints:
        raise RecordError("driver_action_predicate_invalid", "constraints")
    for constraint in constraints:
        if not isinstance(constraint, dict) or set(constraint) != {"document", "path", "operator", "value"}:
            raise RecordError("driver_action_predicate_invalid", "constraint")
        document = documents.get(constraint.get("document"))
        path, operator, expected = constraint.get("path"), constraint.get("operator"), constraint.get("value")
        if document is None or not isinstance(path, list) or any(not isinstance(part, str) for part in path):
            raise RecordError("driver_action_predicate_invalid", "constraint target")
        missing = False
        try:
            actual = _document_value(document, path)
        except RecordError:
            if operator == "absent_or_set_equals":
                missing = True
                actual = None
            else:
                raise
        matched = False
        if operator == "equals":
            matched = actual == expected
        elif operator == "one_of":
            matched = isinstance(expected, list) and actual in expected
        elif operator == "not_one_of":
            matched = isinstance(expected, list) and actual not in expected
        elif operator == "document_path_equals":
            if (
                isinstance(expected, dict)
                and set(expected) == {"document", "path"}
                and isinstance(expected.get("document"), str)
                and isinstance(expected.get("path"), list)
                and all(isinstance(part, str) for part in expected["path"])
                and expected["document"] in documents
            ):
                try:
                    matched = actual == _document_value(
                        documents[expected["document"]], expected["path"]
                    )
                except RecordError:
                    matched = False
        elif operator == "contains":
            matched = isinstance(actual, list) and expected in actual
        elif operator == "set_equals":
            actual_set, expected_set = _string_set(actual), _string_set(expected)
            matched = actual_set is not None and expected_set is not None and actual_set == expected_set
        elif operator == "absent_or_set_equals":
            actual_set, expected_set = _string_set(actual), _string_set(expected)
            matched = missing or (actual_set is not None and expected_set is not None and actual_set == expected_set)
        elif operator == "contains_all":
            actual_set, expected_set = _string_set(actual), _string_set(expected)
            matched = actual_set is not None and expected_set is not None and expected_set.issubset(actual_set)
        elif operator == "nonempty_subset_of":
            actual_set, expected_set = _string_set(actual), _string_set(expected)
            matched = (
                actual_set is not None
                and expected_set is not None
                and bool(actual_set)
                and actual_set.issubset(expected_set)
            )
        elif operator == "length_equals":
            matched = isinstance(actual, list) and isinstance(expected, int) and not isinstance(expected, bool) and len(actual) == expected
        elif operator == "timestamp_after":
            try:
                actual_time = datetime.fromisoformat(actual.replace("Z", "+00:00"))
                expected_time = datetime.fromisoformat(expected.replace("Z", "+00:00"))
            except (AttributeError, TypeError, ValueError):
                matched = False
            else:
                matched = actual_time > expected_time
        elif operator == "canonical_sha256_equals":
            matched = isinstance(expected, str) and sha256_bytes(canonical_json_bytes(actual)) == expected
        else:
            raise RecordError("driver_action_predicate_invalid", str(operator))
        if not matched:
            raise RecordError("driver_action_predicate_mismatch", "/" + "/".join(path))
    return documents, admitted


def _neutral_tail_is_allowed(record: dict[str, Any], state: dict[str, Any], engagement: Path) -> bool:
    binding = record.get("state_binding", {})
    sources = state.get("source_hashes", {})
    expected_sources = binding.get("source_hashes", {})
    if sources.get("attempts.jsonl") != expected_sources.get("attempts.jsonl") or sources.get("artifacts.jsonl") != expected_sources.get("artifacts.jsonl"):
        return False
    if state.get("ledger_hash") == binding.get("ledger_hash"):
        return True
    event_count = binding.get("event_count")
    events = read_ledger(engagement, "event")
    if not isinstance(event_count, int) or event_count < 1 or len(events) <= event_count:
        return False
    if events[event_count - 1].get("record_hash") != binding.get("ledger_hash"):
        return False
    expected_hook_session = record.get("hook_session_ref")
    if not isinstance(expected_hook_session, str):
        return False
    return all(
        event.get("event_type") == "session.end_checked"
        and event.get("actor") == {"role": "broker", "id": "session-end-backstop"}
        and event.get("provenance", {}).get("actor")
        == {"role": "broker", "id": "session-end-backstop"}
        and event.get("provenance", {}).get("session_id") == expected_hook_session
        and event.get("payload", {}).get("session_ref") == expected_hook_session
        and all(
            not event.get(field)
            for field in ("entity_refs", "evidence_refs", "review_refs", "finding_refs", "state_changes")
        )
        for event in events[event_count:]
    )


def _state_binding(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "ledger_hash": state.get("ledger_hash"),
        "source_hashes": copy.deepcopy(state.get("source_hashes")),
        "event_count": state.get("event_count"),
        "scope_hash": state.get("scope_hash"),
    }


def _assert_stop_append_is_audit_only(
    before: dict[str, Any], after: dict[str, Any], recorded: dict[str, Any]
) -> None:
    before_domain = {
        key: value for key, value in before.items() if key not in _SESSION_AUDIT_STATE_KEYS
    }
    after_domain = {
        key: value for key, value in after.items() if key not in _SESSION_AUDIT_STATE_KEYS
    }
    before_sources = before.get("source_hashes")
    after_sources = after.get("source_hashes")
    if (
        after_domain != before_domain
        or type(before.get("event_count")) is not int
        or after.get("event_count") != before["event_count"] + 1
        or after.get("last_event_id") != recorded.get("event_id")
        or after.get("ledger_hash") != recorded.get("record_hash")
        or not isinstance(before_sources, dict)
        or not isinstance(after_sources, dict)
        or after_sources.get("attempts.jsonl") != before_sources.get("attempts.jsonl")
        or after_sources.get("artifacts.jsonl") != before_sources.get("artifacts.jsonl")
        or after_sources.get("events.jsonl") == before_sources.get("events.jsonl")
    ):
        raise RecordError("stop_hook_mutated_domain_state", "broker audit append")


def _stop_output(
    *,
    decision: str,
    reason_code: str,
    streak: int,
    blocking_count: int,
    total_count: int,
    queue_digest: str,
) -> dict[str, str]:
    item_word = "item" if blocking_count == 1 else "items"
    total_word = "item" if total_count == 1 else "items"
    remainder = (
        f"{blocking_count} blocking {item_word} remain "
        f"({total_count} total {total_word}; queue digest {queue_digest}). "
        "Run the harness work-queue next command for the exact next action."
    )
    if decision == "block":
        return {
            "decision": "block",
            "reason": (
                f"{remainder} Session end backstop continuation {streak} "
                f"of {_STOP_BLOCK_BUDGET}."
            ),
        }
    if reason_code == "block_budget_exhausted":
        return {
            "systemMessage": (
                f"Session end backstop released after {_STOP_BLOCK_BUDGET} consecutive "
                f"continuations; {remainder}"
            )
        }
    return {
        "systemMessage": (
            "Session end backstop released at the outer driver's one-action boundary; "
            f"{remainder}"
        )
    }


def _verify_current_selected_action(record: dict[str, Any], state: dict[str, Any], engagement: Path) -> None:
    try:
        from work_queue_actions import queue_command_payload
    except ImportError as exc:
        raise RecordError("driver_queue_contract_unavailable", "admission") from exc
    payload = queue_command_payload("next", state, engagement)
    item = payload.get("item")
    action = item.get("next_action") if isinstance(item, dict) else None
    if (
        not isinstance(item, dict)
        or not isinstance(action, dict)
        or _item_identity(item) != record.get("item_identity")
        or _computed_item_ref(item) != record.get("item_ref")
        or action.get("action_id") != record.get("action_id")
        or action.get("command") != record.get("command")
        or _normalized_action({"arguments": action.get("arguments")}).get("arguments")
        != _normalized_action({"arguments": record.get("argument_template")}).get("arguments")
        or action.get("admission") != record.get("predicate")
        or action.get("session_kind") != record.get("runtime_session_kind")
        or action.get("execution_principal") != "broker"
        or action.get("launchable") is not True
        or action.get("recompute_after") is not True
        or not (
            (action.get("session_kind") == "fresh_independent_reviewer" and action.get("principal") == "independent_reviewer")
            or (action.get("session_kind") == "ordinary_bounded" and action.get("principal") in {"orchestrator", "hunter", "broker"})
        )
        or sha256_bytes(canonical_json_bytes(_normalized_action(action))) != record.get("action_hash")
    ):
        raise RecordError("driver_action_selection_stale", str(record.get("action_id")))


def _broker_error(exc: RecordError) -> tuple[int, bytes]:
    return 1, canonical_json_bytes({"valid": False, "error": exc.as_dict()})


def _replace_engagement_argument(arguments: list[str], engagement_fd: int) -> list[str]:
    result = list(arguments)
    indexes = [index for index, value in enumerate(result) if value == "--engagement"]
    if len(indexes) != 1 or indexes[0] + 1 >= len(result):
        raise RecordError("driver_action_arguments_mismatch", "--engagement")
    result[indexes[0] + 1] = f"/dev/fd/{engagement_fd}"
    return result


def _parent_recorder_identity() -> tuple[str, str]:
    uid = os.getuid()
    return f"local-uid-{uid}:broker", f"session-posix-{uid}-{os.getsid(0)}"


def _stamp_parent_recorder_arguments(arguments: list[str]) -> list[str]:
    actor_id, session_id = _parent_recorder_identity()
    result = list(arguments)
    for index, option in enumerate(result[:-1]):
        if option in {"--actor-id", "--executor-id"}:
            result[index + 1] = actor_id
        elif option == "--session-id":
            result[index + 1] = session_id
    return result


def _stamp_parent_recorder_documents(
    admitted: dict[str, dict[str, Any]],
    *,
    command: str,
    runtime_session_ref: str,
    runtime_model: str,
    view_binding: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Replace forgeable recorder metadata while retaining authenticated producer identity.

    The POSIX actor/session identify the parent process performing the append.  The immutable model
    and runtime UUID identify the model process that produced the semantic content.  Both identities
    are persisted so provenance checks never compare a reviewer UUID with a POSIX recorder session.
    """

    actor_id, session_id = _parent_recorder_identity()
    stamped = copy.deepcopy(admitted)
    def stamp_attempt(attempt: dict[str, Any]) -> None:
        attempt["actor"] = {"role": "broker", "id": actor_id}
        provenance = attempt.get("provenance")
        if not isinstance(provenance, dict):
            provenance = {}
            attempt["provenance"] = provenance
        provenance["actor"] = {"role": "broker", "id": actor_id}
        provenance["session_id"] = session_id
        provenance["runtime_session_ref"] = runtime_session_ref
        provenance["model"] = runtime_model
        provenance["provider"] = None
        if view_binding is not None:
            provenance.update(view_binding)

    for entry in stamped.values():
        value = entry.get("value")
        if not isinstance(value, dict):
            continue
        if isinstance(value.get("event_type"), str):
            value["actor"] = {"role": "broker", "id": actor_id}
            provenance = value.get("provenance")
            if not isinstance(provenance, dict):
                provenance = {}
                value["provenance"] = provenance
            provenance["actor"] = {"role": "broker", "id": actor_id}
            provenance["session_id"] = session_id
            provenance["runtime_session_ref"] = runtime_session_ref
            provenance["model"] = runtime_model
            provenance["provider"] = None
        elif value.get("schema_version") == 2 and isinstance(value.get("attempt_id"), str):
            stamp_attempt(value)
        elif command == "record-hunter-pair" and value.get("schema_version") == 1:
            for name in ("primary", "control"):
                attempt = value.get(name)
                if not isinstance(attempt, dict):
                    raise RecordError("driver_hunter_pair_invalid", name)
                stamp_attempt(attempt)
        elif command == "request-authority" and value.get("action_version") in {2, 3}:
            value["executor_id"] = actor_id
            value["session_id"] = session_id
        entry["bytes"] = canonical_json_bytes(value)
    return stamped


def _decode_container_inline_inputs(
    record: dict[str, Any], value: Any
) -> dict[str, bytes]:
    """Decode the exact reducer-required input set without consulting host paths."""

    if not isinstance(value, list):
        raise RecordError("driver_action_broker_request_invalid", "inline inputs")
    expected = {
        spec["argument"]: spec for spec in _expected_inline_inputs(record)
    }
    decoded: dict[str, bytes] = {}
    total = 0
    for item in value:
        if (
            not isinstance(item, dict)
            or set(item) != {"argument", "size", "sha256", "content_base64"}
            or not isinstance(item.get("argument"), str)
            or type(item.get("size")) is not int
            or item["size"] < 0
            or not isinstance(item.get("sha256"), str)
            or not isinstance(item.get("content_base64"), str)
        ):
            raise RecordError("driver_action_broker_request_invalid", "inline input shape")
        argument = item["argument"]
        spec = expected.get(argument)
        if spec is None:
            raise RecordError("driver_action_predicate_input_invalid", "extra inline input")
        if argument in decoded:
            raise RecordError("driver_action_predicate_input_invalid", "duplicate inline input")
        try:
            raw = base64.b64decode(item["content_base64"], validate=True)
        except (binascii.Error, TypeError, ValueError) as exc:
            raise RecordError(
                "driver_action_predicate_input_invalid", argument
            ) from exc
        if (
            len(raw) != item["size"]
            or len(raw) > spec["max_bytes"]
            or item["sha256"] != sha256_bytes(raw)
        ):
            raise RecordError("driver_action_predicate_input_invalid", argument)
        total += len(raw)
        if total > _CONTAINER_RAW_INPUT_LIMIT:
            raise RecordError("driver_action_predicate_input_invalid", "aggregate oversize")
        decoded[argument] = raw
    if set(decoded) != set(expected):
        raise RecordError("driver_action_predicate_input_missing", "inline input")
    return decoded


def _recv_exact(connection: socket.socket, size: int) -> bytes:
    result = bytearray()
    while len(result) < size:
        chunk = connection.recv(size - len(result))
        if not chunk:
            raise RecordError("driver_action_broker_request_invalid", "short frame")
        result.extend(chunk)
    return bytes(result)


def _recv_container_frame(connection: socket.socket) -> dict[str, Any]:
    try:
        length = struct.unpack("!I", _recv_exact(connection, 4))[0]
    except struct.error as exc:
        raise RecordError("driver_action_broker_request_invalid", "frame") from exc
    if length <= 0 or length > _CONTAINER_FRAME_LIMIT:
        raise RecordError("driver_action_broker_request_invalid", "oversize frame")
    try:
        value = json.loads(
            _recv_exact(connection, length), object_pairs_hook=_reject_duplicate_pairs
        )
    except RecordError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise RecordError("driver_action_broker_request_invalid", "json") from exc
    if not isinstance(value, dict):
        raise RecordError("driver_action_broker_request_invalid", "shape")
    return value


def _send_container_frame(connection: socket.socket, value: dict[str, Any]) -> None:
    data = canonical_json_bytes(value)
    if len(data) > _CONTAINER_FRAME_LIMIT:
        raise RecordError("driver_action_broker_response_invalid", "oversize frame")
    connection.sendall(struct.pack("!I", len(data)) + data)


_RUN_ENGAGEMENT_MODULE: Any | None = None
_RUN_ENGAGEMENT_MODULE_LOCK = threading.Lock()


def _run_engagement_module() -> Any:
    """Load the public command implementation into this trusted parent process once."""

    global _RUN_ENGAGEMENT_MODULE
    with _RUN_ENGAGEMENT_MODULE_LOCK:
        if _RUN_ENGAGEMENT_MODULE is None:
            path = Path(__file__).with_name("run-engagement.py")
            spec = importlib.util.spec_from_file_location("_driver_broker_run_engagement", path)
            if spec is None or spec.loader is None:
                raise RecordError("driver_action_broker_unavailable", "run-engagement loader")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            _RUN_ENGAGEMENT_MODULE = module
    return _RUN_ENGAGEMENT_MODULE


class DriverActionBroker:
    """Parent-resident, one-success broker for one immutable reducer action.

    POSIX sessions use the existing peer-authenticated Unix endpoint by default.  A Docker caller
    may instead supply one exact container identity and a fresh session key, selecting an
    authenticated loopback TCP endpoint whose predicate inputs travel inline.  In both cases the
    model never receives the parent-held admission token and never executes a mutation itself.
    All authority used below is the in-memory record returned by :func:`arm_action_admission`;
    target-local sidecars and registries are not consulted.
    """

    def __init__(
        self,
        *,
        engagement_fd: int,
        logical_engagement: Path,
        admission: dict[str, Any],
        execution_deadline: float | None = None,
        docker_identity: dict[str, str] | None = None,
        docker_session_key: bytes | None = None,
        provider_fixture_origin: str | None = None,
        hunter_view: Any | None = None,
        source_workspace: Path | None = None,
    ) -> None:
        if execution_deadline is not None and (
            not isinstance(execution_deadline, (int, float))
            or isinstance(execution_deadline, bool)
            or not math.isfinite(float(execution_deadline))
            or execution_deadline <= 0
        ):
            raise RecordError("driver_action_broker_deadline_invalid", "execution deadline")
        self._engagement_fd = os.dup(engagement_fd)
        self._logical_engagement = Path(os.path.abspath(logical_engagement))
        self._admission = copy.deepcopy(admission)
        self._hunter_view = hunter_view
        self._source_workspace = source_workspace
        self._execution_deadline = (
            float(execution_deadline) if execution_deadline is not None else None
        )
        self._stop_state_binding: dict[str, Any] | None = copy.deepcopy(
            admission.get("state_binding")
        )
        self._stop_request_results: dict[str, tuple[int, bytes]] = {}
        self._stop_release_recorded = False
        self._post_consumption_release_recorded = False
        self._lock = threading.Lock()
        self._close_lock = threading.Lock()
        self._closed = False
        self._stop = threading.Event()
        self._transport_kind = "unix"
        self._docker_identity: dict[str, Any] | None = None
        self._docker_session_key = b""
        self._container_nonces: dict[str, str] = {}
        self._container_nonce_lock = threading.Lock()
        self._container_workers: set[threading.Thread] = set()
        self._container_workers_lock = threading.Lock()
        self._container_connections: set[socket.socket] = set()
        self._container_connections_lock = threading.Lock()
        self._provider_upstreams: set[socket.socket] = set()
        self._provider_upstreams_lock = threading.Lock()
        self._container_deadline_ref: str | None = None
        configured_provider = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
        self._provider_base_url = provider_fixture_origin or configured_provider
        self._provider_fixture = provider_fixture_origin is not None
        self._provider_api_key = os.environ.get("ANTHROPIC_API_KEY")
        # Network/TLS libraries stay parent-only. Model children import this module solely for the
        # local action client and must not acquire extra dynamic-library read requirements.
        import network_scope
        self._network_scope = network_scope
        self._network_gateway = (
            self._network_scope.NetworkGateway(request_budget=32, deadline=self._execution_deadline)
            if self._execution_deadline is not None
            else None
        )
        self.network_audit: list[dict[str, Any]] = []
        try:
            self._load_network_receipts()
        except BaseException:
            os.close(self._engagement_fd)
            raise
        self.tcp_endpoint: tuple[str, int] | None = None
        try:
            if docker_identity is None and docker_session_key is None:
                self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            elif docker_identity is not None and docker_session_key is not None:
                if execution_deadline is None:
                    raise RecordError(
                        "driver_action_broker_deadline_invalid", "Docker deadline"
                    )
                if not isinstance(docker_identity, dict):
                    raise RecordError(
                        "driver_action_container_identity_invalid", "docker container"
                    )
                identity = _docker_runtime_identity(
                    docker_identity.get("container_id"),
                    docker_identity.get("container_config_digest"),
                )
                if (
                    not isinstance(docker_session_key, bytes)
                    or len(docker_session_key) != _CONTAINER_SESSION_KEY_BYTES
                ):
                    raise RecordError(
                        "driver_action_broker_key_invalid", "Docker session key"
                    )
                self._transport_kind = "tcp_hmac_sha256"
                self._docker_identity = identity
                self._docker_session_key = bytes(docker_session_key)
                self._container_deadline_ref = _deadline_ref(
                    admission=self._admission,
                    identity=identity,
                    deadline=self._execution_deadline,
                )
                self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            else:
                raise RecordError(
                    "driver_action_broker_transport_invalid", "partial Docker transport"
                )
        except BaseException:
            os.close(self._engagement_fd)
            raise

        try:
            if self._transport_kind == "unix":
                root = _ensure_broker_root()
                self.endpoint: Path | None = root / (
                    f"b-{os.getpid()}-{secrets.token_hex(8)}.sock"
                )
                self._server.bind(str(self.endpoint))
            else:
                self.endpoint = None
                self._server.bind(("127.0.0.1", 0))
                host, port = self._server.getsockname()[:2]
                if host != "127.0.0.1" or type(port) is not int or port <= 0:
                    raise RecordError(
                        "driver_action_broker_unavailable", "unsafe TCP endpoint"
                    )
                self.tcp_endpoint = (host, port)
        except BaseException:
            self._server.close()
            os.close(self._engagement_fd)
            raise
        endpoint_identity: tuple[int, int] | None = None
        try:
            if self._transport_kind == "unix":
                assert self.endpoint is not None
                os.chmod(self.endpoint, 0o600)
                endpoint_stat = self.endpoint.lstat()
                if not stat.S_ISSOCK(endpoint_stat.st_mode) or endpoint_stat.st_uid != os.getuid():
                    raise RecordError("driver_action_broker_unavailable", "unsafe endpoint")
                endpoint_identity = (endpoint_stat.st_dev, endpoint_stat.st_ino)
            self._endpoint_identity = endpoint_identity
            self._server.listen(8)
            self._server.settimeout(0.1)
            # Freeze the mutation implementation and all of its imports before the untrusted
            # process starts. Broker correctness cannot depend on a later pathname lookup.
            _run_engagement_module()
            self._thread = threading.Thread(
                target=self._serve,
                name=f"work-queue-action-broker-{os.getpid()}",
                daemon=True,
            )
            self._thread.start()
        except BaseException:
            self._server.close()
            os.close(self._engagement_fd)
            if self.endpoint is not None:
                try:
                    entry = self.endpoint.lstat()
                except FileNotFoundError:
                    pass
                else:
                    if endpoint_identity is not None and (
                        entry.st_dev,
                        entry.st_ino,
                    ) == endpoint_identity:
                        self.endpoint.unlink()
            raise

    def _load_network_receipts(self) -> None:
        """Recover bounded redacted receipts so a restarted parent sees uncertainty."""

        with bound_engagement_lock(self._engagement_fd, create=False) as bound:
            try:
                raw = read_governed_file(
                    bound / NETWORK_RECEIPTS_FILE, require_single_link=True
                )
            except FileNotFoundError:
                return
            except (OSError, RecordError) as exc:
                raise RecordError("driver_network_receipt_invalid", "unsafe path") from exc
        recovered = self._decode_network_receipts(raw)
        self.network_audit.extend(recovered)
        if self._network_gateway is not None:
            for receipt in recovered:
                if (
                    receipt["operation"] == "target_fetch"
                    and receipt["runtime_session_ref"] == self._admission.get("runtime_session_ref")
                    and receipt["action_id"] == self._admission.get("action_id")
                ):
                    # A persisted completion or uncertainty receipt proves that this logical
                    # request began. Restore it as a tombstone without charging an unrelated
                    # historical request against this admission's fresh request budget.
                    self._network_gateway.mark_uncertain(receipt["request_id"])

    @staticmethod
    def _decode_network_receipts(raw: bytes) -> list[dict[str, Any]]:
        """Validate the complete bounded receipt file before it can be extended or trusted."""

        if len(raw) > NETWORK_RECEIPTS_MAX_BYTES:
            raise RecordError("driver_network_receipt_invalid", "oversize")
        lines = raw.splitlines()
        if len(lines) > NETWORK_RECEIPTS_MAX_ROWS or (raw and not raw.endswith(b"\n")):
            raise RecordError("driver_network_receipt_invalid", "bounds")
        recovered: list[dict[str, Any]] = []
        common = {
            "schema_version", "runtime_session_ref", "action_id", "operation",
            "method", "status",
        }
        operation_fields = {
            "provider_request": {"host", "path", "request_bytes", "response_bytes"},
            "target_fetch": {"request_id", "url_sha256", "request_bytes", "response_bytes"},
        }
        for line in lines:
            try:
                row = json.loads(line, object_pairs_hook=_reject_duplicate_pairs)
            except (UnicodeDecodeError, json.JSONDecodeError, RecordError) as exc:
                raise RecordError("driver_network_receipt_invalid", "JSON") from exc
            operation = row.get("operation") if isinstance(row, dict) else None
            allowed = common | operation_fields.get(operation, set())
            if (
                not isinstance(row, dict)
                or operation not in operation_fields
                or not common.issubset(row)
                or not set(row).issubset(allowed)
                or row.get("schema_version") != 1
                or not isinstance(row.get("runtime_session_ref"), str)
                or not isinstance(row.get("action_id"), str)
                or not isinstance(row.get("method"), str)
                or type(row.get("status")) not in {str, int}
                or (
                    operation == "target_fetch"
                    and (
                        _SHA256_RE.fullmatch(str(row.get("request_id"))) is None
                        or _SHA256_RE.fullmatch(str(row.get("url_sha256"))) is None
                    )
                )
            ):
                raise RecordError("driver_network_receipt_invalid", "shape")
            recovered.append(copy.deepcopy(row))
        return recovered

    def _persist_network_receipt(self, receipt: dict[str, Any]) -> None:
        """Persist one redacted bounded receipt before returning network completion."""

        row = {
            "schema_version": 1,
            "runtime_session_ref": self._admission.get("runtime_session_ref"),
            "action_id": self._admission.get("action_id"),
            **receipt,
        }
        data = canonical_json_bytes(row)
        self._decode_network_receipts(data)
        with bound_engagement_lock(self._engagement_fd, create=False) as bound:
            path = bound / NETWORK_RECEIPTS_FILE
            try:
                prior = read_governed_file(path, require_single_link=True)
            except FileNotFoundError:
                prior = b""
            prior_records = self._decode_network_receipts(prior)
            rows = prior.splitlines(keepends=True)
            combined = b"".join(rows) + data
            while (len(rows) >= NETWORK_RECEIPTS_MAX_ROWS or len(combined) > NETWORK_RECEIPTS_MAX_BYTES) and rows:
                removable = next((index for index, old in enumerate(prior_records) if not (
                    old["operation"] == "target_fetch"
                    and old["status"] == "begun"
                    and old["runtime_session_ref"] == self._admission.get("runtime_session_ref")
                    and old["action_id"] == self._admission.get("action_id")
                )), None)
                if removable is None:
                    raise RecordError("driver_network_receipt_oversize", str(row.get("operation")))
                rows.pop(removable)
                prior_records.pop(removable)
                combined = b"".join(rows) + data
            if len(combined) > NETWORK_RECEIPTS_MAX_BYTES:
                raise RecordError("driver_network_receipt_oversize", str(row.get("operation")))
            atomic_write(path, combined)
        self.network_audit.append(copy.deepcopy(receipt))

    def activate(self, os_session_id: int) -> None:
        runtime_identity = _posix_runtime_identity(os_session_id)
        with self._lock:
            if (
                self._transport_kind != "unix"
                or self._admission.get("status") != "armed"
                or self._admission.get("os_session_id") is not None
                or self._admission.get("runtime_identity") is not None
            ):
                raise RecordError(
                    "driver_action_admission_not_armed",
                    str(self._admission.get("action_id")),
                )
            self._admission["os_session_id"] = os_session_id
            self._admission["runtime_identity"] = runtime_identity

    def activate_docker(self) -> None:
        """Activate the broker for the exact constructor-bound Docker identity."""

        with self._lock:
            if (
                self._transport_kind != "tcp_hmac_sha256"
                or self._docker_identity is None
                or self._admission.get("status") != "armed"
                or self._admission.get("os_session_id") is not None
                or self._admission.get("runtime_identity") is not None
            ):
                raise RecordError(
                    "driver_action_admission_not_armed",
                    str(self._admission.get("action_id")),
                )
            self._admission["runtime_identity"] = copy.deepcopy(
                self._docker_identity
            )

    def container_manifest(self, *, advertised_host: str | None = None) -> dict[str, Any]:
        """Return non-secret transport metadata for the exact Docker supervisor."""

        if (
            self._transport_kind != "tcp_hmac_sha256"
            or self._docker_identity is None
            or self.tcp_endpoint is None
            or self._container_deadline_ref is None
        ):
            raise RecordError(
                "driver_action_broker_transport_invalid", "not a Docker broker"
            )
        host = self.tcp_endpoint[0] if advertised_host is None else advertised_host
        if not isinstance(host, str) or not host or "\x00" in host:
            raise RecordError(
                "driver_action_broker_transport_invalid", "advertised host"
            )
        return {
            "schema_version": 1,
            "transport": "tcp_hmac_sha256",
            "endpoint": {"host": host, "port": self.tcp_endpoint[1]},
            "runtime_identity": copy.deepcopy(self._docker_identity),
            "runtime_session_ref": self._admission.get("runtime_session_ref"),
            "action_id": self._admission.get("action_id"),
            "deadline_ref": self._container_deadline_ref,
            "inline_inputs": _expected_inline_inputs(self._admission),
            "frame_limit": _CONTAINER_FRAME_LIMIT,
            "raw_input_limit": _CONTAINER_RAW_INPUT_LIMIT,
        }

    def _peer_is_runtime(self, connection: socket.socket) -> bool:
        try:
            identity = _active_runtime_identity(self._admission)
        except RecordError:
            return False
        if not isinstance(identity, dict) or identity.get("kind") != "posix_session":
            return False
        expected_session = identity["os_session_id"]
        peer_pid: int | None = None
        if hasattr(socket, "SO_PEERCRED"):
            try:
                raw = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
                peer_pid, peer_uid, _peer_gid = struct.unpack("3i", raw)
                if peer_uid != os.getuid():
                    return False
            except (OSError, struct.error):
                return False
        elif sys.platform == "darwin":
            # Darwin exposes the connected AF_UNIX peer PID through LOCAL_PEERPID.  Python does
            # not currently publish these constants, so use their stable sys/socket.h values.
            try:
                raw = connection.getsockopt(0, 0x002, struct.calcsize("i"))
                (peer_pid,) = struct.unpack("i", raw)
            except (OSError, struct.error):
                return False
        if not isinstance(peer_pid, int) or peer_pid <= 0:
            return False
        try:
            return os.getsid(peer_pid) == expected_session
        except OSError:
            return False

    @staticmethod
    def _read_request(connection: socket.socket) -> dict[str, Any]:
        chunks: list[bytes] = []
        size = 0
        while True:
            chunk = connection.recv(min(65536, _RPC_LIMIT + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > _RPC_LIMIT:
                raise RecordError("driver_action_broker_request_invalid", "oversize")
        try:
            request = json.loads(b"".join(chunks), object_pairs_hook=_reject_duplicate_pairs)
        except RecordError:
            raise
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
            raise RecordError("driver_action_broker_request_invalid", "json") from exc
        action_request = bool(
            isinstance(request, dict)
            and set(request)
            == {"schema_version", "command", "arguments", "runtime_session_ref"}
            and request.get("schema_version") == 1
            and isinstance(request.get("command"), str)
            and isinstance(request.get("arguments"), list)
            and all(isinstance(value, str) for value in request["arguments"])
            and isinstance(request.get("runtime_session_ref"), str)
        )
        stop_request = bool(
            isinstance(request, dict)
            and set(request)
            == {
                "schema_version",
                "request_kind",
                "runtime_session_ref",
                "hook_session_ref",
                "stop_hook_active",
                "request_ref",
            }
            and request.get("schema_version") == 1
            and request.get("request_kind") == "session_end_check"
            and isinstance(request.get("runtime_session_ref"), str)
            and isinstance(request.get("hook_session_ref"), str)
            and type(request.get("stop_hook_active")) is bool
            and isinstance(request.get("request_ref"), str)
            and len(request["request_ref"]) == 71
            and request["request_ref"].startswith("sha256:")
            and all(value in "0123456789abcdef" for value in request["request_ref"][7:])
        )
        if not action_request and not stop_request:
            raise RecordError("driver_action_broker_request_invalid", "shape")
        return request

    def _admit_hunter_pair(
        self, proposal: dict[str, Any], admitted: dict[str, dict[str, Any]],
        state: dict[str, Any], engagement: Path,
    ) -> None:
        if self._hunter_view is None or self._source_workspace is None or self._admission.get("cognitive_principal") != "hunter":
            raise RecordError("driver_hunter_source_view_missing", "record_hunter_pair")
        if set(proposal) != {"schema_version", "primary", "control", "primary_raw_sha256", "control_raw_sha256"}:
            raise RecordError("driver_hunter_pair_invalid", "shape")
        primary, control = proposal.get("primary"), proposal.get("control")
        if not isinstance(primary, dict) or not isinstance(control, dict) or control.get("control_of") != [primary.get("attempt_id")]:
            raise RecordError("driver_hunter_pair_invalid", "control link")
        if detect_secret_classes(admitted["file"]["bytes"]):
            raise RecordError("driver_hunter_output_secret_shaped", "proposal")
        item = queue_command_payload("next", state, engagement).get("item")
        try:
            from hunter_view import HunterViewError
            self._hunter_view.assert_current(
                workspace=self._source_workspace, engagement=engagement, state=state,
                item=item, methodology_root=Path(__file__).resolve().parents[1] / "skills",
            )
        except (HunterViewError, TypeError) as exc:
            raise RecordError("driver_hunter_source_changed", "current view") from exc
        comparison = state["hypotheses"][primary["hypothesis_ref"]]["source_comparison"]
        signal = comparison["signal"].encode("ascii")
        observed: dict[str, bytes] = {}
        for name, path in (("primary", comparison["primary_path"]), ("control", comparison["control_path"])):
            rows = [row for row in self._hunter_view.manifest["target_inputs"] if row["target_relative_path"] == path]
            if len(rows) != 1:
                raise RecordError("driver_hunter_source_mismatch", name)
            row = rows[0]
            raw = _read_regular_bytes(
                self._hunter_view.projection / "target-inputs" / row["slot"],
                max_bytes=_MODEL_JSON_LIMIT, error_code="driver_hunter_source_unavailable",
            )
            digest = sha256_bytes(raw)
            if digest != row["digest"] or digest != proposal[f"{name}_raw_sha256"]:
                raise RecordError("driver_hunter_output_mismatch", name)
            if detect_secret_classes(raw):
                raise RecordError("driver_hunter_output_secret_shaped", name)
            observed[name] = raw
            attempt = proposal[name]
            attempt["action_summary"] = f"Compared allowlisted source {path}."
            attempt["observation"] = {"source": "broker", "statement": f"{path} raw={digest} bytes={len(raw)} signal={'present' if signal in raw else 'absent'}"}
            attempt["recorded_at"] = utc_now()
            attempt["redaction_attestation"] = True
        if signal not in observed["primary"] or signal in observed["control"]:
            raise RecordError("driver_hunter_signal_mismatch", "matched source pair")
        admitted["file"]["value"] = proposal

    def _admit(
        self,
        request: dict[str, Any],
        inline_inputs: dict[str, bytes] | None = None,
    ) -> dict[str, dict[str, Any]]:
        record = self._admission
        command = request["command"]
        arguments = request["arguments"]
        if record.get("status") != "armed":
            raise RecordError("driver_action_admission_consumed", str(record.get("action_id")))
        if (
            self._execution_deadline is not None
            and time.monotonic() >= self._execution_deadline
        ):
            raise RecordError(
                "driver_action_execution_deadline_exceeded",
                str(record.get("action_id")),
            )
        if (
            record.get("runtime_session_ref") != request.get("runtime_session_ref")
            or _active_runtime_identity(record) is None
        ):
            raise RecordError("driver_action_scope_mismatch", command)
        opened = os.fstat(self._engagement_fd)
        if record.get("engagement_identity") != {"device": opened.st_dev, "inode": opened.st_ino}:
            raise RecordError("driver_action_engagement_mismatch", command)
        if command != record.get("command"):
            raise RecordError("driver_action_command_mismatch", command)
        template = record.get("argument_template")
        if not isinstance(template, list):
            raise RecordError("driver_action_admission_invalid", command)
        _match_argument_template(template, arguments)
        with bound_engagement_lock(self._engagement_fd, create=False) as bound:
            state = _reduce_engagement_unchecked(bound)
            if not _neutral_tail_is_allowed(record, state, bound):
                raise RecordError("driver_action_state_changed", str(record.get("action_id")))
            _verify_current_selected_action(record, state, bound)
            documents, admitted = _evaluate_predicate(
                record.get("predicate", {}), arguments, inline_inputs
            )
            if command == "record-hunter-pair":
                self._admit_hunter_pair(documents["proposal"], admitted, state, bound)
        if command == "record-review":
            raw_values = _raw_argument_values(arguments)
            for option, attribute, limit in (
                ("--signature", "signature", _REVIEW_SIGNATURE_LIMIT),
                (
                    "--allowed-signers",
                    "allowed_signers",
                    _REVIEW_ALLOWED_SIGNERS_LIMIT,
                ),
            ):
                paths = raw_values.get(option, [])
                if len(paths) != 1 or not paths[0]:
                    raise RecordError("driver_action_predicate_input_missing", option)
                if inline_inputs is None:
                    raw = _read_regular_bytes(
                        Path(paths[0]),
                        max_bytes=limit,
                        error_code="driver_action_predicate_input_invalid",
                    )
                else:
                    raw = inline_inputs.get(option)
                    if not isinstance(raw, bytes) or len(raw) > limit:
                        raise RecordError(
                            "driver_action_predicate_input_invalid", option
                        )
                admitted[attribute] = {"bytes": raw}
        if record.get("runtime_session_kind") == "fresh_independent_reviewer":
            review = documents.get("proposal")
            independence = review.get("independence") if isinstance(review, dict) else None
            if (
                not isinstance(independence, dict)
                or independence.get("reviewer_session_id") != record.get("runtime_session_ref")
                or independence.get("reviewer_model") != record.get("runtime_model")
            ):
                raise RecordError(
                    "driver_reviewer_runtime_binding_mismatch",
                    str(record.get("action_id")),
                )
        # All model-controlled document reads and predicate work are pre-admission. A request that
        # entered just before the outer deadline may not cross it during validation and then commit.
        if (
            self._execution_deadline is not None
            and time.monotonic() >= self._execution_deadline
        ):
            raise RecordError(
                "driver_action_execution_deadline_exceeded",
                str(record.get("action_id")),
            )
        return admitted

    def _execute_stop(self, request: dict[str, Any]) -> tuple[int, bytes]:
        with self._lock:
            record = self._admission
            request_ref = request["request_ref"]
            cached = self._stop_request_results.get(request_ref)
            if cached is not None:
                return cached
            if (
                request.get("runtime_session_ref") != record.get("runtime_session_ref")
                or request.get("hook_session_ref") != record.get("hook_session_ref")
                or _active_runtime_identity(record) is None
                or record.get("status") not in {"armed", "consumed"}
                or not isinstance(self._stop_state_binding, dict)
            ):
                return _broker_error(
                    RecordError("driver_stop_hook_scope_mismatch", str(record.get("action_id")))
                )
            if (
                len(self._stop_request_results) >= _STOP_REQUEST_BUDGET
                or self._stop_release_recorded
            ):
                return _broker_error(
                    RecordError("driver_stop_hook_budget_exhausted", str(record.get("action_id")))
                )
            opened = os.fstat(self._engagement_fd)
            if record.get("engagement_identity") != {
                "device": opened.st_dev,
                "inode": opened.st_ino,
            }:
                return _broker_error(
                    RecordError("driver_action_engagement_mismatch", "session_end_check")
                )
            appended = False
            decision = ""
            status_at_request = record.get("status")
            try:
                with bound_engagement_lock(self._engagement_fd, create=False) as bound:
                    before = _reduce_engagement_unchecked(bound)
                    neutral_record = {
                        "state_binding": self._stop_state_binding,
                        "hook_session_ref": record["hook_session_ref"],
                    }
                    if not _neutral_tail_is_allowed(neutral_record, before, bound):
                        raise RecordError(
                            "driver_stop_hook_state_changed", str(record.get("action_id"))
                        )
                    if sha256_bytes(read_governed_file(bound / "scope.md")) != before.get(
                        "scope_hash"
                    ):
                        raise RecordError("stop_hook_scope_drift", "active scope bytes drifted")
                    gate_payload = queue_command_payload("gate", before, bound)
                    summary = gate_payload.get("queue")
                    queue = before.get("work_queue")
                    if (
                        gate_payload.get("ok") is not True
                        or not isinstance(summary, dict)
                        or not isinstance(queue, list)
                        or type(summary.get("blocking_count")) is not int
                        or type(summary.get("total_count")) is not int
                        or type(summary.get("should_block")) is not bool
                        or summary.get("total_count") != len(queue)
                        or summary.get("blocking_count")
                        != sum(item.get("blocking") is True for item in queue)
                    ):
                        raise RecordError("stop_gate_contract_invalid", "broker gate")
                    if summary["should_block"] is not True:
                        result = (0, canonical_json_bytes({}))
                        self._stop_request_results[request_ref] = result
                        return result

                    events = read_ledger(bound, "event")
                    previous = next(
                        (
                            event
                            for event in reversed(events)
                            if event.get("event_type") == "session.end_checked"
                            and event.get("payload", {}).get("session_ref")
                            == record["hook_session_ref"]
                        ),
                        None,
                    )
                    if status_at_request == "consumed":
                        if self._post_consumption_release_recorded:
                            raise RecordError(
                                "driver_stop_hook_budget_exhausted",
                                str(record.get("action_id")),
                            )
                        decision, reason_code, streak = "release", "reentrant_state_unmatched", 0
                    elif request["stop_hook_active"] is not True:
                        if previous is not None:
                            raise RecordError(
                                "driver_stop_hook_state_changed",
                                str(record.get("action_id")),
                            )
                        decision, reason_code, streak = "block", "blocking_work_remaining", 1
                    elif (
                        isinstance(previous, dict)
                        and previous.get("payload", {}).get("decision") == "block"
                        and type(
                            previous.get("payload", {}).get("confirmed_consecutive_blocks")
                        )
                        is int
                        and 1
                        <= previous["payload"]["confirmed_consecutive_blocks"]
                        <= _STOP_BLOCK_BUDGET
                    ):
                        prior = previous["payload"]["confirmed_consecutive_blocks"]
                        if prior >= _STOP_BLOCK_BUDGET:
                            decision, reason_code, streak = (
                                "release",
                                "block_budget_exhausted",
                                _STOP_BLOCK_BUDGET,
                            )
                        else:
                            decision, reason_code, streak = (
                                "block",
                                "blocking_work_remaining",
                                prior + 1,
                            )
                    else:
                        decision, reason_code, streak = (
                            "release",
                            "reentrant_state_unmatched",
                            0,
                        )
                    queue_digest = sha256_bytes(canonical_json_bytes(queue))
                    event = base_event(
                        event_id=f"event-session-end-{secrets.token_hex(12)}",
                        engagement_id=before["engagement_id"],
                        recorded_at=utc_now(),
                        actor_role="broker",
                        actor_id="session-end-backstop",
                        event_type="session.end_checked",
                        rationale=(
                            "Session end backstop found blocking work and requested continuation."
                            if decision == "block"
                            else "Session end backstop released at the outer driver boundary."
                        ),
                        payload={
                            "session_ref": record["hook_session_ref"],
                            "decision": decision,
                            "reason_code": reason_code,
                            "confirmed_consecutive_blocks": streak,
                            "blocking_work_count": summary["blocking_count"],
                            "remaining_work_count": summary["total_count"],
                            "queue_digest": queue_digest,
                            "observed_state_hash": gate_payload["state_hash"],
                        },
                        session_id=record["hook_session_ref"],
                        operation_class="notebook",
                        model=record["runtime_model"],
                    )
                    event["provenance"]["runtime_session_ref"] = record[
                        "runtime_session_ref"
                    ]
                    recorded = append_event(bound, event, lock_held=True)
                    appended = True
                    after = _reduce_engagement_unchecked(bound)
                    _assert_stop_append_is_audit_only(before, after, recorded)
                result = (0, canonical_json_bytes(
                    _stop_output(
                        decision=decision,
                        reason_code=reason_code,
                        streak=streak,
                        blocking_count=summary["blocking_count"],
                        total_count=summary["total_count"],
                        queue_digest=queue_digest,
                    )
                ))
                self._stop_request_results[request_ref] = result
                if decision == "release":
                    self._stop_release_recorded = True
                    if status_at_request == "consumed":
                        self._post_consumption_release_recorded = True
                return result
            except RecordError as exc:
                result = _broker_error(exc)
                # An invariant failure after append must be idempotent too: the audit row exists,
                # so retrying the same delivery may never append a second row.
                if appended:
                    self._stop_request_results[request_ref] = result
                    if decision == "release":
                        self._stop_release_recorded = True
                        if status_at_request == "consumed":
                            self._post_consumption_release_recorded = True
                return result

    def _execute(
        self,
        request: dict[str, Any],
        inline_inputs: dict[str, bytes] | None = None,
    ) -> tuple[int, bytes]:
        with self._lock:
            try:
                admitted = self._admit(request, inline_inputs)
            except RecordError as exc:
                return _broker_error(exc)
            # From here onward no retry is safe: a command can contain a multi-record transaction
            # and a crash may have committed an idempotent prefix.  Predicate/shape failures above
            # remain retryable; an admitted dispatch is exactly once.
            self._admission["status"] = "executing"
            try:
                module = _run_engagement_module()
                runtime_session_ref = str(self._admission["runtime_session_ref"])
                runtime_model = str(self._admission["runtime_model"])
                stamped_documents = _stamp_parent_recorder_documents(
                    admitted,
                    command=request["command"],
                    runtime_session_ref=runtime_session_ref,
                    runtime_model=runtime_model,
                    view_binding=(
                        {key: self._admission[key] for key in ("cognitive_principal", "view_type", "view_digest", "input_corpus_digest", "treatment")}
                        if self._admission.get("cognitive_principal") is not None else None
                    ),
                )
                returncode, output = module.execute_broker_command(
                    command=request["command"],
                    arguments=_stamp_parent_recorder_arguments(
                        _replace_engagement_argument(
                            request["arguments"], self._engagement_fd
                        )
                    ),
                    admitted_documents=stamped_documents,
                    authenticated_runtime={
                        "runtime_session_ref": runtime_session_ref,
                        "model": runtime_model,
                        "provider": None,
                        "deadline_monotonic": self._execution_deadline,
                    },
                )
            except RecordError as exc:
                returncode, output = _broker_error(exc)
            except BaseException:
                returncode, output = _broker_error(
                    RecordError("driver_action_broker_execution_failed", str(self._admission.get("action_id")))
                )
            finally:
                self._admission["status"] = "consumed"
                try:
                    with bound_engagement_lock(self._engagement_fd, create=False) as bound:
                        self._stop_state_binding = _state_binding(
                            _reduce_engagement_unchecked(bound)
                        )
                except (OSError, RecordError):
                    self._stop_state_binding = None
            return returncode, output

    @staticmethod
    def _container_nonce(value: Any) -> str:
        if not isinstance(value, str):
            raise RecordError("driver_action_broker_request_invalid", "nonce")
        try:
            raw = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise RecordError("driver_action_broker_request_invalid", "nonce") from exc
        if (
            len(raw) != _CONTAINER_NONCE_BYTES
            or base64.b64encode(raw).decode("ascii") != value
        ):
            raise RecordError("driver_action_broker_request_invalid", "nonce")
        return value

    def _authenticate_container_request(
        self, envelope: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, bytes] | None, str]:
        expected_keys = {
            "schema_version",
            "message_kind",
            "runtime_identity",
            "runtime_session_ref",
            "action_id",
            "deadline_ref",
            "nonce",
            "payload_sha256",
            "payload",
            "mac_base64",
        }
        if set(envelope) != expected_keys:
            raise RecordError("driver_action_broker_request_invalid", "envelope")
        unsigned = dict(envelope)
        raw_mac = unsigned.pop("mac_base64")
        if not isinstance(raw_mac, str):
            raise RecordError("driver_action_broker_request_invalid", "MAC")
        try:
            received_mac = base64.b64decode(raw_mac, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise RecordError("driver_action_broker_request_invalid", "MAC") from exc
        try:
            expected_mac = _container_hmac(
                self._docker_session_key, _CONTAINER_REQUEST_DOMAIN, unsigned
            )
        except (
            UnicodeError,
            TypeError,
            ValueError,
            RecursionError,
            OverflowError,
        ) as exc:
            raise RecordError(
                "driver_action_broker_request_invalid", "canonical envelope"
            ) from exc
        if not hmac.compare_digest(received_mac, expected_mac):
            raise RecordError("driver_action_broker_auth_invalid", "request MAC")
        nonce = self._container_nonce(envelope.get("nonce"))
        payload = envelope.get("payload")
        try:
            payload_digest = sha256_bytes(canonical_json_bytes(payload))
        except (
            UnicodeError,
            TypeError,
            ValueError,
            RecursionError,
            OverflowError,
        ) as exc:
            raise RecordError(
                "driver_action_broker_request_invalid", "canonical payload"
            ) from exc
        if (
            envelope.get("schema_version") != 1
            or envelope.get("message_kind") != "request"
            or envelope.get("runtime_identity") != self._docker_identity
            or envelope.get("runtime_session_ref")
            != self._admission.get("runtime_session_ref")
            or envelope.get("action_id") != self._admission.get("action_id")
            or envelope.get("deadline_ref") != self._container_deadline_ref
            or not isinstance(payload, dict)
            or envelope.get("payload_sha256") != payload_digest
            or _active_runtime_identity(self._admission) != self._docker_identity
        ):
            raise RecordError("driver_action_scope_mismatch", "Docker envelope")
        if (
            self._execution_deadline is None
            or time.monotonic() >= self._execution_deadline
        ):
            raise RecordError(
                "driver_action_execution_deadline_exceeded",
                str(self._admission.get("action_id")),
            )
        request_kind = payload.get("request_kind")
        if request_kind == "action":
            if (
                set(payload)
                != {
                    "request_kind",
                    "command",
                    "arguments",
                    "runtime_session_ref",
                    "inline_inputs",
                }
                or not isinstance(payload.get("command"), str)
                or not isinstance(payload.get("arguments"), list)
                or any(not isinstance(value, str) for value in payload["arguments"])
                or payload.get("runtime_session_ref")
                != self._admission.get("runtime_session_ref")
            ):
                raise RecordError("driver_action_broker_request_invalid", "action")
            inline_inputs = _decode_container_inline_inputs(
                self._admission, payload.get("inline_inputs")
            )
            self._remember_container_nonce(nonce, "action")
            return (
                {
                    "command": payload["command"],
                    "arguments": payload["arguments"],
                    "runtime_session_ref": payload["runtime_session_ref"],
                },
                inline_inputs,
                nonce,
            )
        if request_kind == "session_end_check":
            if (
                set(payload)
                != {
                    "request_kind",
                    "runtime_session_ref",
                    "hook_session_ref",
                    "stop_hook_active",
                    "request_ref",
                }
                or payload.get("runtime_session_ref")
                != self._admission.get("runtime_session_ref")
                or not isinstance(payload.get("hook_session_ref"), str)
                or payload.get("hook_session_ref")
                != self._admission.get("hook_session_ref")
                or type(payload.get("stop_hook_active")) is not bool
                or not isinstance(payload.get("request_ref"), str)
                or len(payload["request_ref"]) != 71
                or not payload["request_ref"].startswith("sha256:")
                or any(value not in "0123456789abcdef" for value in payload["request_ref"][7:])
            ):
                raise RecordError("driver_action_broker_request_invalid", "Stop")
            self._remember_container_nonce(nonce, "session_end_check")
            return copy.deepcopy(payload), None, nonce
        if request_kind == "provider_request":
            if (
                set(payload) != {
                    "request_kind", "method", "path", "headers", "body_base64", "runtime_session_ref"
                }
                or payload.get("method") != "POST"
                or payload.get("path") not in {"/v1/messages", "/v1/messages?beta=true"}
                or payload.get("runtime_session_ref") != self._admission.get("runtime_session_ref")
                or not isinstance(payload.get("headers"), dict)
                or any(
                    not isinstance(name, str)
                    or not isinstance(value, str)
                    or name not in {"accept", "content-type", "anthropic-version", "anthropic-beta"}
                    or "\r" in value
                    or "\n" in value
                    for name, value in payload["headers"].items()
                )
                or not isinstance(payload.get("body_base64"), str)
            ):
                raise RecordError("driver_provider_request_invalid", "shape")
            try:
                body = base64.b64decode(payload["body_base64"], validate=True)
            except (binascii.Error, ValueError) as exc:
                raise RecordError("driver_provider_request_invalid", "body") from exc
            if len(body) > _CONTAINER_RAW_INPUT_LIMIT:
                raise RecordError("driver_provider_request_invalid", "body")
            _validate_provider_inference_body(
                body,
                expected_model=str(self._admission.get("runtime_model")),
                max_tokens=int(self._admission.get("provider_max_tokens", 0)),
            )
            self._remember_container_nonce(nonce, "provider_request")
            request = copy.deepcopy(payload)
            request["body"] = body
            del request["body_base64"]
            return request, None, nonce
        if request_kind == "target_fetch":
            expected_request_id = sha256_bytes(
                _TARGET_FETCH_ID_DOMAIN
                + canonical_json_bytes(
                    {
                        "runtime_session_ref": payload.get("runtime_session_ref"),
                        "action_id": self._admission.get("action_id"),
                        "url": payload.get("url"),
                        "method": payload.get("method"),
                    }
                )
            )
            if (
                set(payload) != {
                    "request_kind", "operation", "request_id", "url", "method", "runtime_session_ref"
                }
                or payload.get("operation") != "target_fetch"
                or payload.get("runtime_session_ref") != self._admission.get("runtime_session_ref")
                or not isinstance(payload.get("request_id"), str)
                or payload["request_id"] != expected_request_id
                or not isinstance(payload.get("url"), str)
                or not 1 <= len(payload["url"]) <= 8192
                or payload.get("method") not in {"GET", "HEAD"}
            ):
                raise RecordError("driver_target_fetch_invalid", "shape")
            self._remember_container_nonce(nonce, "target_fetch")
            return copy.deepcopy(payload), None, nonce
        raise RecordError("driver_action_broker_request_invalid", "request kind")

    def _remember_container_nonce(self, nonce: str, request_kind: str) -> None:
        budgets = {
            "action": _CONTAINER_ACTION_NONCE_BUDGET,
            "session_end_check": _STOP_REQUEST_BUDGET,
            "provider_request": _CONTAINER_PROVIDER_NONCE_BUDGET,
            "target_fetch": _CONTAINER_TARGET_FETCH_NONCE_BUDGET,
        }
        budget = budgets.get(request_kind)
        if budget is None:
            raise RecordError("driver_action_broker_request_invalid", "request kind")
        with self._container_nonce_lock:
            if nonce in self._container_nonces:
                raise RecordError("driver_action_broker_replay", "nonce")
            used = sum(
                kind == request_kind for kind in self._container_nonces.values()
            )
            if used >= budget:
                raise RecordError(
                    "driver_action_broker_request_budget_exhausted", request_kind
                )
            self._container_nonces[nonce] = request_kind

    def _container_response(
        self, *, request_nonce: str, returncode: int, output: bytes
    ) -> dict[str, Any]:
        if (
            type(returncode) is not int
            or not 0 <= returncode <= 255
            or not isinstance(output, bytes)
            or len(output) > _RPC_LIMIT
            or self._docker_identity is None
            or self._container_deadline_ref is None
        ):
            returncode, output = _broker_error(
                RecordError("driver_action_broker_response_invalid", "container response")
            )
        payload = {
            "returncode": returncode,
            "stdout_base64": base64.b64encode(output).decode("ascii"),
        }
        unsigned = {
            "schema_version": 1,
            "message_kind": "response",
            "runtime_identity": copy.deepcopy(self._docker_identity),
            "runtime_session_ref": self._admission.get("runtime_session_ref"),
            "action_id": self._admission.get("action_id"),
            "deadline_ref": self._container_deadline_ref,
            "request_nonce": request_nonce,
            "payload_sha256": sha256_bytes(canonical_json_bytes(payload)),
            "payload": payload,
        }
        return {
            **unsigned,
            "mac_base64": base64.b64encode(
                _container_hmac(
                    self._docker_session_key,
                    _CONTAINER_RESPONSE_DOMAIN,
                    unsigned,
                )
            ).decode("ascii"),
        }

    def _serve_provider_stream(
        self, connection: socket.socket, request: dict[str, Any], nonce: str
    ) -> None:
        parsed = urllib.parse.urlsplit(self._provider_base_url)
        production = (
            not self._provider_fixture
            and parsed.scheme == "https"
            and parsed.hostname == "api.anthropic.com"
            and parsed.port in {None, 443}
            and parsed.path in {"", "/"}
            and not parsed.query
            and not parsed.fragment
            and parsed.username is None
        )
        fixture = (
            self._provider_fixture
            and parsed.scheme == "http"
            and parsed.hostname in {"127.0.0.1", "localhost"}
            and parsed.port is not None
            and parsed.path in {"", "/"}
            and not parsed.query
            and not parsed.fragment
            and parsed.username is None
        )
        if not (production or fixture) or request.get("path") not in {"/v1/messages", "/v1/messages?beta=true"} or not self._provider_api_key:
            raise RecordError("driver_provider_unavailable", "configuration")
        with bound_engagement_lock(self._engagement_fd, create=False) as bound:
            state = _reduce_engagement_unchecked(bound)
            scope = read_governed_file(bound / "scope.md")
            if (
                sha256_bytes(scope) != state.get("scope_hash")
                or self._admission.get("state_binding", {}).get("scope_hash")
                != state.get("scope_hash")
                or not _neutral_tail_is_allowed(self._admission, state, bound)
            ):
                raise RecordError("driver_provider_scope_stale", "scope")
        port = parsed.port or 443
        deadline = self._execution_deadline or time.monotonic()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RecordError("driver_provider_failed", "deadline")
        address = "127.0.0.1" if fixture else self._network_scope.resolve_pinned(
            parsed.hostname, port, deadline=deadline
        )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RecordError("driver_provider_failed", "deadline")
        upstream = socket.create_connection(
            (address, port), timeout=min(30.0, remaining)
        )
        with self._provider_upstreams_lock:
            self._provider_upstreams.add(upstream)
        total = 0
        sent_headers = False
        try:
            if production:
                import ssl
                upstream.settimeout(max(0.001, deadline - time.monotonic()))
                wrapped = ssl.create_default_context().wrap_socket(
                    upstream, server_hostname=parsed.hostname
                )
                with self._provider_upstreams_lock:
                    self._provider_upstreams.discard(upstream)
                    self._provider_upstreams.add(wrapped)
                upstream = wrapped
            headers = {
                name.lower(): value
                for name, value in request["headers"].items()
                if name.lower() in {"accept", "content-type", "anthropic-version", "anthropic-beta"}
            }
            headers["host"] = parsed.hostname
            headers["x-api-key"] = self._provider_api_key
            headers["content-length"] = str(len(request["body"]))
            headers["connection"] = "close"
            request_path = request["path"]
            raw = (
                f"POST {request_path} HTTP/1.1\r\n"
                + "".join(f"{name}: {value}\r\n" for name, value in headers.items())
                + "\r\n"
            ).encode("ascii") + request["body"]
            upstream.settimeout(max(0.001, deadline - time.monotonic()))
            upstream.sendall(raw)
            upstream.settimeout(max(0.001, deadline - time.monotonic()))
            response = http.client.HTTPResponse(upstream, method="POST")
            response.begin()
            response_headers = [
                [name.lower(), value]
                for name, value in response.getheaders()
                if name.lower() in {"content-type", "request-id", "anthropic-request-id"}
                and "\r" not in value
                and "\n" not in value
            ]
            _send_container_frame(
                connection,
                self._container_response(
                    request_nonce=nonce,
                    returncode=0,
                    output=canonical_json_bytes({
                        "stream": "headers",
                        "status": response.status,
                        "headers": response_headers,
                    }),
                ),
            )
            sent_headers = True
            sequence = 0
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RecordError("driver_provider_failed", "deadline")
                upstream.settimeout(min(30.0, remaining))
                chunk = response.read1(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > _CONTAINER_RAW_INPUT_LIMIT:
                    raise RecordError("driver_provider_response_oversize", "body")
                _send_container_frame(
                    connection,
                    self._container_response(
                        request_nonce=nonce,
                        returncode=0,
                        output=canonical_json_bytes({
                            "stream": "chunk",
                            "sequence": sequence,
                            "body_base64": base64.b64encode(chunk).decode("ascii"),
                        }),
                    ),
                )
                sequence += 1
            self._persist_network_receipt({
                "operation": "provider_request",
                "method": "POST",
                "host": parsed.hostname,
                "path": request_path,
                "status": response.status,
                "request_bytes": len(request["body"]),
                "response_bytes": total,
            })
            _send_container_frame(
                connection,
                self._container_response(
                    request_nonce=nonce,
                    returncode=0,
                    output=canonical_json_bytes({"stream": "end", "sequence": sequence}),
                ),
            )
        except BaseException:
            self._persist_network_receipt({
                "operation": "provider_request",
                "method": "POST",
                "host": parsed.hostname,
                "path": request.get("path"),
                "status": "uncertain" if sent_headers else "failed",
            })
            raise
        finally:
            with self._provider_upstreams_lock:
                self._provider_upstreams.discard(upstream)
            upstream.close()

    def _execute_target_fetch(self, request: dict[str, Any]) -> tuple[int, bytes]:
        request_id = request["request_id"]
        try:
            if self._network_gateway is None:
                raise self._network_scope.NetworkScopeError("network_gateway_unavailable")
            self._network_gateway.begin(request_id)
            with bound_engagement_lock(self._engagement_fd, create=False) as bound:
                state = _reduce_engagement_unchecked(bound)
                scope = read_governed_file(bound / "scope.md")
                policy = self._network_scope.parse_network_policy(
                    scope, expected_scope_hash=str(state.get("scope_hash"))
                )
                if (
                    self._admission.get("state_binding", {}).get("scope_hash")
                    != state.get("scope_hash")
                    or not _neutral_tail_is_allowed(self._admission, state, bound)
                ):
                    raise RecordError("driver_target_fetch_state_stale", "admission")
            self._persist_network_receipt({
                "operation": "target_fetch",
                "request_id": request_id,
                "method": request["method"],
                "url_sha256": sha256_bytes(request["url"].encode("utf-8")),
                "status": "begun",
            })
            status, headers, body = self._network_scope.pinned_request(
                policy=policy,
                operation="target_fetch",
                url=request["url"],
                method=request["method"],
                deadline=self._execution_deadline,
            )
            safe_headers = [
                [name, value]
                for name, value in headers
                if name in {"content-type", "content-length", "etag", "last-modified"}
            ]
            output = canonical_json_bytes({
                "status": status,
                "headers": safe_headers,
                "body_base64": base64.b64encode(body).decode("ascii"),
            })
            self._persist_network_receipt({
                "operation": "target_fetch",
                "request_id": request_id,
                "method": request["method"],
                "url_sha256": sha256_bytes(request["url"].encode("utf-8")),
                "status": status,
                "response_bytes": len(body),
            })
            return 0, output
        except (self._network_scope.NetworkScopeError, OSError, TimeoutError, RecordError) as exc:
            if self._network_gateway is not None:
                self._network_gateway.mark_uncertain(request_id)
            self._persist_network_receipt({
                "operation": "target_fetch",
                "request_id": request_id,
                "method": request.get("method"),
                "url_sha256": sha256_bytes(str(request.get("url", "")).encode("utf-8")),
                "status": "denied_or_uncertain",
            })
            return _broker_error(RecordError("driver_target_fetch_denied", type(exc).__name__))

    def _serve_container_connection(self, connection: socket.socket) -> None:
        envelope: dict[str, Any] | None = None
        try:
            envelope = _recv_container_frame(connection)
            request, inline_inputs, nonce = self._authenticate_container_request(
                envelope
            )
            if request.get("request_kind") == "session_end_check":
                returncode, output = self._execute_stop(request)
            elif request.get("request_kind") == "provider_request":
                self._serve_provider_stream(connection, request, nonce)
                return
            elif request.get("request_kind") == "target_fetch":
                returncode, output = self._execute_target_fetch(request)
            else:
                returncode, output = self._execute(request, inline_inputs)
        except RecordError as exc:
            if envelope is None:
                return
            try:
                nonce = self._container_nonce(envelope.get("nonce"))
            except RecordError:
                return
            returncode, output = _broker_error(exc)
        response = self._container_response(
            request_nonce=nonce, returncode=returncode, output=output
        )
        try:
            _send_container_frame(connection, response)
        except (OSError, RecordError):
            pass

    def _serve_container_worker(self, connection: socket.socket) -> None:
        try:
            with connection:
                connection.settimeout(_BROKER_IO_TIMEOUT_SECONDS)
                try:
                    self._serve_container_connection(connection)
                except (
                    OSError,
                    TimeoutError,
                    UnicodeError,
                    TypeError,
                    ValueError,
                    RecursionError,
                    OverflowError,
                ):
                    # A peer that stalls or truncates a frame has no authenticated nonce to bind
                    # a response to. Close only this connection.
                    pass
        finally:
            with self._container_connections_lock:
                self._container_connections.discard(connection)
            with self._container_workers_lock:
                self._container_workers.discard(threading.current_thread())

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                connection, _ = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            if self._transport_kind == "tcp_hmac_sha256":
                worker = threading.Thread(
                    target=self._serve_container_worker,
                    args=(connection,),
                    daemon=True,
                )
                with self._container_connections_lock:
                    self._container_connections.add(connection)
                with self._container_workers_lock:
                    self._container_workers.add(worker)
                worker.start()
                continue
            with connection:
                connection.settimeout(_BROKER_IO_TIMEOUT_SECONDS)
                try:
                    if not self._peer_is_runtime(connection):
                        raise RecordError("driver_action_scope_mismatch", "peer session")
                    request = self._read_request(connection)
                    if request.get("request_kind") == "session_end_check":
                        returncode, output = self._execute_stop(request)
                    else:
                        returncode, output = self._execute(request)
                    response = canonical_json_bytes(
                        {
                            "schema_version": 1,
                            "returncode": returncode,
                            "stdout_base64": base64.b64encode(output).decode("ascii"),
                        }
                    )
                except socket.timeout:
                    returncode, output = _broker_error(
                        RecordError("driver_action_broker_request_invalid", "timeout")
                    )
                    response = canonical_json_bytes(
                        {
                            "schema_version": 1,
                            "returncode": returncode,
                            "stdout_base64": base64.b64encode(output).decode("ascii"),
                        }
                    )
                except RecordError as exc:
                    returncode, output = _broker_error(exc)
                    response = canonical_json_bytes(
                        {
                            "schema_version": 1,
                            "returncode": returncode,
                            "stdout_base64": base64.b64encode(output).decode("ascii"),
                        }
                    )
                try:
                    connection.sendall(response)
                except OSError:
                    pass

    def close(self) -> None:
        with self._close_lock:
            if self._closed:
                return
            self._stop.set()
            self._server.close()
            connections_lock = getattr(self, "_container_connections_lock", None)
            connections_set = getattr(self, "_container_connections", None)
            if connections_lock is not None and connections_set is not None:
                with connections_lock:
                    connections = tuple(connections_set)
            else:
                connections = ()
            for connection in connections:
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                connection.close()
            upstreams_lock = getattr(self, "_provider_upstreams_lock", None)
            upstreams_set = getattr(self, "_provider_upstreams", None)
            if upstreams_lock is not None and upstreams_set is not None:
                with upstreams_lock:
                    upstreams = tuple(upstreams_set)
            else:
                upstreams = ()
            for upstream in upstreams:
                try:
                    upstream.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                upstream.close()
            # Network workers share one parent-owned absolute session deadline. Closing their
            # sockets cancels blocked I/O; the deadline bounds DNS and any remaining teardown.
            shutdown_deadline = getattr(self, "_execution_deadline", None)
            cleanup_deadline = (
                None
                if shutdown_deadline is None
                else max(shutdown_deadline, time.monotonic() + 0.25)
            )
            if shutdown_deadline is None:
                self._thread.join()
            else:
                self._thread.join(timeout=max(0.0, cleanup_deadline - time.monotonic()))
            workers_lock = getattr(self, "_container_workers_lock", None)
            workers_set = getattr(self, "_container_workers", None)
            shutdown_timed_out = False
            if workers_lock is not None and workers_set is not None:
                while True:
                    with workers_lock:
                        workers = tuple(workers_set)
                    if not workers:
                        break
                    for worker in workers:
                        timeout = None if cleanup_deadline is None else max(
                            0.0, cleanup_deadline - time.monotonic()
                        )
                        worker.join(timeout=timeout)
                    if cleanup_deadline is not None and time.monotonic() >= cleanup_deadline:
                        with workers_lock:
                            if workers_set:
                                shutdown_timed_out = True
                                break
            os.close(self._engagement_fd)
            self._engagement_fd = -1
            self._closed = True
            endpoint = getattr(self, "endpoint", None)
            if isinstance(endpoint, Path):
                try:
                    entry = endpoint.lstat()
                except FileNotFoundError:
                    pass
                else:
                    if (entry.st_dev, entry.st_ino) == self._endpoint_identity:
                        endpoint.unlink()
            self._docker_session_key = b""
            if shutdown_timed_out:
                raise RecordError(
                    "driver_action_broker_shutdown_timeout",
                    str(self._admission.get("action_id")),
                )

    def __enter__(self) -> "DriverActionBroker":
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.close()


def forward_action_to_broker(
    *, command: str, arguments: list[str]
) -> tuple[int, bytes] | None:
    """Forward a scoped model mutation to its parent; never execute it in the model process."""

    endpoint = os.environ.get(BROKER_ENDPOINT_ENV)
    if command in READ_ONLY_COMMANDS or command in OPERATOR_GOVERNANCE_COMMANDS or endpoint is None:
        return None
    runtime_session_ref = os.environ.get(SESSION_ENV)
    if not runtime_session_ref:
        raise RecordError("driver_action_scope_missing", command)
    endpoint_path = Path(endpoint)
    if not endpoint_path.is_absolute() or "\x00" in endpoint:
        raise RecordError("driver_action_broker_unavailable", command)
    request = canonical_json_bytes(
        {
            "schema_version": 1,
            "command": command,
            "arguments": arguments,
            "runtime_session_ref": runtime_session_ref,
        }
    )
    if len(request) > _RPC_LIMIT:
        raise RecordError("driver_action_broker_request_invalid", "oversize")
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.settimeout(_BROKER_IO_TIMEOUT_SECONDS)
    try:
        connection.connect(endpoint)
        connection.sendall(request)
        connection.shutdown(socket.SHUT_WR)
        # The parent owns the semantic deadline.  A model-local fixed response timeout can expire
        # while the trusted mutation is still running and must not be mistaken for cancellation.
        connection.settimeout(None)
        chunks: list[bytes] = []
        size = 0
        while True:
            chunk = connection.recv(min(65536, _RPC_LIMIT + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > _RPC_LIMIT:
                raise RecordError("driver_action_broker_response_invalid", "oversize")
    except (OSError, TimeoutError) as exc:
        raise RecordError("driver_action_broker_unavailable", command) from exc
    finally:
        connection.close()
    try:
        response = json.loads(b"".join(chunks), object_pairs_hook=_reject_duplicate_pairs)
        if (
            not isinstance(response, dict)
            or set(response) != {"schema_version", "returncode", "stdout_base64"}
            or response.get("schema_version") != 1
            or type(response.get("returncode")) is not int
            or not 0 <= response["returncode"] <= 255
            or not isinstance(response.get("stdout_base64"), str)
        ):
            raise ValueError("shape")
        output = base64.b64decode(response["stdout_base64"], validate=True)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise RecordError("driver_action_broker_response_invalid", command) from exc
    return response["returncode"], output


def forward_stop_check_to_broker(
    *, hook_session_ref: str, stop_hook_active: bool, request_ref: str
) -> dict[str, str]:
    """Ask the authenticated parent to compute and append one audit-only Stop check."""

    endpoint = os.environ.get(BROKER_ENDPOINT_ENV)
    runtime_session_ref = os.environ.get(SESSION_ENV)
    if not endpoint or not runtime_session_ref:
        raise RecordError("driver_stop_hook_scope_missing", "session_end_check")
    if not Path(endpoint).is_absolute() or "\x00" in endpoint:
        raise RecordError("driver_action_broker_unavailable", "session_end_check")
    request = canonical_json_bytes(
        {
            "schema_version": 1,
            "request_kind": "session_end_check",
            "runtime_session_ref": runtime_session_ref,
            "hook_session_ref": hook_session_ref,
            "stop_hook_active": stop_hook_active,
            "request_ref": request_ref,
        }
    )
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.settimeout(_BROKER_IO_TIMEOUT_SECONDS)
    try:
        connection.connect(endpoint)
        connection.sendall(request)
        connection.shutdown(socket.SHUT_WR)
        connection.settimeout(None)
        chunks: list[bytes] = []
        size = 0
        while True:
            chunk = connection.recv(min(65536, _RPC_LIMIT + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > _RPC_LIMIT:
                raise RecordError("driver_action_broker_response_invalid", "session_end_check")
    except (OSError, TimeoutError) as exc:
        raise RecordError("driver_action_broker_unavailable", "session_end_check") from exc
    finally:
        connection.close()
    try:
        response = json.loads(b"".join(chunks), object_pairs_hook=_reject_duplicate_pairs)
        if (
            not isinstance(response, dict)
            or set(response) != {"schema_version", "returncode", "stdout_base64"}
            or response.get("schema_version") != 1
            or type(response.get("returncode")) is not int
            or not isinstance(response.get("stdout_base64"), str)
        ):
            raise ValueError("shape")
        output = base64.b64decode(response["stdout_base64"], validate=True)
        result = json.loads(output, object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise RecordError("driver_action_broker_response_invalid", "session_end_check") from exc
    if response["returncode"] != 0:
        raise RecordError("driver_stop_hook_rejected", "session_end_check")
    if not isinstance(result, dict):
        raise RecordError("driver_action_broker_response_invalid", "session_end_check")
    valid = (
        result == {}
        or (
            set(result) == {"decision", "reason"}
            and result.get("decision") == "block"
            and isinstance(result.get("reason"), str)
            and bool(result["reason"])
        )
        or (
            set(result) == {"systemMessage"}
            and isinstance(result.get("systemMessage"), str)
            and bool(result["systemMessage"])
        )
    )
    if not valid:
        raise RecordError("driver_action_broker_response_invalid", "session_end_check")
    return result


def consume_action_admission(
    *, engagement: Path, command: str, arguments: list[str], namespace: Any
) -> bool:
    """Consume the current runtime's exact mutation admission, or allow a normal unscoped CLI.

    Returns ``True`` only when a scoped one-shot admission was consumed.  Read-only commands do
    not consume it.  A session registry is authoritative over environment omission.
    """

    if command in READ_ONLY_COMMANDS or command in OPERATOR_GOVERNANCE_COMMANDS:
        return False
    registry = _current_session_registry()
    token = os.environ.get(TOKEN_ENV)
    runtime_session_ref = os.environ.get(SESSION_ENV)
    engagement = engagement.absolute()
    sidecar_path = engagement / ADMISSION_FILE
    sidecar_exists = sidecar_path.exists()
    lexical_workspace = engagement.parent.parent
    cwd_driver_active = _workspace_driver_lock_active(Path.cwd())
    engagement_driver_active = _workspace_driver_lock_active(lexical_workspace)
    driver_active = cwd_driver_active or engagement_driver_active
    if registry is None and not sidecar_exists and not driver_active:
        if token is not None or runtime_session_ref is not None:
            raise RecordError("driver_action_admission_missing", command)
        return False
    # There is no legacy target-side admission path.  During a driver run, only the parent broker
    # may execute a mutation; a child that unsets/replaces its endpoint or rewrites every marker
    # remains unable to turn those same-UID files into authority.  Outside a driver, any leftover
    # marker is a fail-closed recovery condition rather than a mutation credential.
    raise RecordError(
        "driver_action_broker_required" if driver_active else "driver_action_admission_stale",
        command,
    )
