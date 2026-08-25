#!/usr/bin/env python3
"""One-shot admission for reducer-selected work-queue mutations.

The outer driver arms one exact reducer action before starting a fresh runtime.  A public
``run-engagement`` mutation in that runtime must consume the admission atomically before its
first write.  The record is target-local; a short-lived process-session registry prevents an
unset scope environment from silently falling back to an ordinary unscoped command.
"""

from __future__ import annotations

import copy
import base64
import fcntl
import importlib.util
import json
import math
import os
import secrets
import socket
import stat
import struct
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from engagement_records import RecordError, _reject_duplicate_pairs, canonical_json_bytes, sha256_bytes
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
TOKEN_ENV = "HARNESS_EXPECTED_ACTION_TOKEN"
SESSION_ENV = "HARNESS_EXPECTED_RUNTIME_SESSION_REF"
BROKER_ENDPOINT_ENV = "HARNESS_DRIVER_ACTION_BROKER"
_RPC_LIMIT = 4 * 1024 * 1024
_MODEL_JSON_LIMIT = _RPC_LIMIT
_REVIEW_SIGNATURE_LIMIT = 256 * 1024
_REVIEW_ALLOWED_SIGNERS_LIMIT = 1024 * 1024
_BROKER_IO_TIMEOUT_SECONDS = 2.0
_STOP_BLOCK_BUDGET = 6
_STOP_REQUEST_BUDGET = _STOP_BLOCK_BUDGET + 1
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
OPERATOR_GOVERNANCE_COMMANDS = frozenset({"operator-stop", "operator-resume"})
_ALLOWED_ADMISSION_KEYS = {
    "schema_version",
    "status",
    "driver_run_ref",
    "token_hash",
    "runtime_session_ref",
    "runtime_model",
    "runtime_session_kind",
    "hook_session_ref",
    "os_session_id",
    "engagement_identity",
    "state_binding",
    "item_ref",
    "item_identity",
    "action_id",
    "command",
    "argument_template",
    "action_hash",
    "predicate",
}


def new_admission_token() -> str:
    return secrets.token_urlsafe(32)


def _token_hash(token: str) -> str:
    return sha256_bytes(token.encode("utf-8"))


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
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
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
        "runtime_session_kind": action.get("session_kind"),
        "hook_session_ref": sha256_bytes(
            b"llm-redteam-harness:session-end:v1:" + runtime_session_ref.encode("utf-8")
        ),
        "os_session_id": None,
        "engagement_identity": {"device": opened.st_dev, "inode": opened.st_ino},
        "state_binding": {
            "ledger_hash": state.get("ledger_hash"),
            "source_hashes": copy.deepcopy(source_hashes),
            "event_count": state.get("event_count"),
        },
        "item_ref": item_ref,
        "item_identity": _item_identity(item),
        "action_id": action.get("action_id"),
        "command": action.get("command"),
        "argument_template": copy.deepcopy(action.get("arguments")),
        "action_hash": sha256_bytes(canonical_json_bytes(_normalized_action(action))),
        "predicate": copy.deepcopy(action["admission"]),
    }
    if (
        set(record) != _ALLOWED_ADMISSION_KEYS
        or not isinstance(record["action_id"], str)
        or not isinstance(record["command"], str)
        or not isinstance(record["argument_template"], list)
        or any(not isinstance(value, str) for value in record["argument_template"])
        or record["runtime_session_kind"] not in {"ordinary_bounded", "fresh_independent_reviewer"}
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

    if not isinstance(os_session_id, int) or os_session_id <= 0:
        raise RecordError("driver_action_os_session_invalid", str(os_session_id))
    with bound_engagement_lock(engagement_fd, create=False) as bound:
        record = _read_regular_json(bound / ADMISSION_FILE, error_code="driver_action_admission_invalid")
        if record.get("status") != "armed" or record.get("token_hash") != _token_hash(token) or record.get("os_session_id") is not None:
            raise RecordError("driver_action_admission_not_armed", str(record.get("action_id")))
        record["os_session_id"] = os_session_id
        atomic_write(bound / ADMISSION_FILE, canonical_json_bytes(record))
    if admission is not None:
        if (
            admission.get("status") != "armed"
            or admission.get("token_hash") != _token_hash(token)
            or admission.get("os_session_id") is not None
        ):
            raise RecordError("driver_action_admission_not_armed", str(admission.get("action_id")))
        admission["os_session_id"] = os_session_id
    registry = {
        "schema_version": 1,
        "os_session_id": os_session_id,
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
    for expected, received in zip(template, actual, strict=True):
        is_placeholder = expected.startswith("<") and expected.endswith(">")
        if not is_placeholder and expected != received:
            raise RecordError("driver_action_arguments_mismatch", expected)
        if is_placeholder:
            if not received or (received.startswith("<") and received.endswith(">")):
                raise RecordError("driver_action_input_unresolved", expected)
            prior = replacements.setdefault(expected, received)
            if prior != received:
                raise RecordError("driver_action_input_inconsistent", expected)


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


def _load_predicate_documents(
    predicate: dict[str, Any], arguments: list[str]
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
        value, raw = _read_regular_json_bytes(Path(paths[0]), error_code="driver_action_predicate_input_invalid")
        result[name] = value
        attribute = argument.removeprefix("--").replace("-", "_")
        admitted[attribute] = {"value": value, "bytes": raw}
    return result, admitted


def _evaluate_predicate(
    predicate: dict[str, Any], arguments: list[str]
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    if predicate.get("schema_version") != 1 or set(predicate) != {"schema_version", "documents", "constraints"}:
        raise RecordError("driver_action_predicate_invalid", "shape")
    documents, admitted = _load_predicate_documents(predicate, arguments)
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
) -> dict[str, dict[str, Any]]:
    """Replace forgeable recorder metadata while retaining authenticated producer identity.

    The POSIX actor/session identify the parent process performing the append.  The immutable model
    and runtime UUID identify the model process that produced the semantic content.  Both identities
    are persisted so provenance checks never compare a reviewer UUID with a POSIX recorder session.
    """

    actor_id, session_id = _parent_recorder_identity()
    stamped = copy.deepcopy(admitted)
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
        elif command == "request-authority" and value.get("action_version") == 2:
            value["executor_id"] = actor_id
            value["session_id"] = session_id
        entry["bytes"] = canonical_json_bytes(value)
    return stamped


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

    The model is given only a Unix endpoint.  It can request the selected mutation, or replace the
    endpoint and cause denial, but it never receives the parent-held admission token and never
    executes a mutation itself.  All authority used below is the in-memory record returned by
    :func:`arm_action_admission`; target-local sidecars and registries are not consulted.
    """

    def __init__(
        self,
        *,
        engagement_fd: int,
        logical_engagement: Path,
        admission: dict[str, Any],
        execution_deadline: float | None = None,
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
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            root = _ensure_broker_root()
            self.endpoint = root / f"b-{os.getpid()}-{secrets.token_hex(8)}.sock"
            self._server.bind(str(self.endpoint))
        except BaseException:
            self._server.close()
            os.close(self._engagement_fd)
            raise
        endpoint_identity: tuple[int, int] | None = None
        try:
            os.chmod(self.endpoint, 0o600)
            endpoint_stat = self.endpoint.lstat()
            if not stat.S_ISSOCK(endpoint_stat.st_mode) or endpoint_stat.st_uid != os.getuid():
                raise RecordError("driver_action_broker_unavailable", "unsafe endpoint")
            endpoint_identity = (endpoint_stat.st_dev, endpoint_stat.st_ino)
            self._endpoint_identity = endpoint_identity
            self._server.listen(8)
            self._server.settimeout(0.1)
            # Freeze the mutation implementation and all of its imports before the untrusted
            # process starts.  Broker correctness cannot depend on a later pathname lookup.
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

    def activate(self, os_session_id: int) -> None:
        with self._lock:
            if self._admission.get("status") != "armed" or self._admission.get("os_session_id") is not None:
                raise RecordError(
                    "driver_action_admission_not_armed",
                    str(self._admission.get("action_id")),
                )
            self._admission["os_session_id"] = os_session_id

    def _peer_is_runtime(self, connection: socket.socket) -> bool:
        expected_session = self._admission.get("os_session_id")
        if not isinstance(expected_session, int):
            return False
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
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
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

    def _admit(self, request: dict[str, Any]) -> dict[str, dict[str, Any]]:
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
            or not isinstance(record.get("os_session_id"), int)
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
            documents, admitted = _evaluate_predicate(record.get("predicate", {}), arguments)
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
                admitted[attribute] = {
                    "bytes": _read_regular_bytes(
                        Path(paths[0]),
                        max_bytes=limit,
                        error_code="driver_action_predicate_input_invalid",
                    )
                }
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
                or not isinstance(record.get("os_session_id"), int)
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

    def _execute(self, request: dict[str, Any]) -> tuple[int, bytes]:
        with self._lock:
            try:
                admitted = self._admit(request)
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

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                connection, _ = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                return
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
            # Cancellation is unsafe once an admitted transaction starts.  The broker retains its
            # duplicated engagement descriptor and shutdown requires worker quiescence.
            self._thread.join()
            os.close(self._engagement_fd)
            self._engagement_fd = -1
            self._closed = True
            try:
                entry = self.endpoint.lstat()
            except FileNotFoundError:
                pass
            else:
                if (entry.st_dev, entry.st_ino) == self._endpoint_identity:
                    self.endpoint.unlink()

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
