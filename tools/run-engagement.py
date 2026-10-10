#!/usr/bin/env python3
"""Canonical public command for Decision 0005 engagement records.

This command records and validates research state. It never drives a target.
"""

from __future__ import annotations

import argparse
import base64
import copy
import ctypes
import errno
import json
import math
import os
import re
import runpy
import secrets
import stat
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack, nullcontext
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path

from engagement_records import (
    RecordError,
    _reject_duplicate_pairs,
    build_reference_index,
    canonical_json_bytes,
    detect_secret_classes,
    legacy_finding_inventory,
    load_json,
    resolve_schema_name,
    scan_file_secret_classes,
    sha256_bytes,
    sha256_file,
    validate_fixture_suite,
    validate_record,
    validate_schema_documents,
    validate_record_with_references,
    validate_record_references,
    write_canonical_json,
)
from engagement_state import (
    append_attempt,
    append_event,
    _append_kernel_event,
    _append_kernel_event_idempotent,
    _governed_root,
    _governed_file_exists,
    _governed_optional_regular_digest,
    _governed_sha256_file,
    _open_parent_fd,
    atomic_write,
    append_ledger_record,
    assert_resume_current,
    attempt_ledger_context,
    base_event as _base_event,
    blocking_work_identities,
    bound_engagement_lock,
    bound_engagement_source,
    engagement_lock,
    find_engagement_root,
    initialize_engagement,
    materialize_ledger_record,
    persist_scope_snapshot,
    project_current_terminal_work_state,
    read_governed_file,
    read_ledger,
    reduce_engagement,
    _reduce_engagement_unchecked,
    quarantine_authority_context,
    quarantine_control_lock,
    require_not_quarantined,
    require_approved_authority,
    require_repair_authority_from_intact_prefix,
    require_scope_zone2_authorized,
    revise_finding_target_is_current,
    _validate_revise_finding_v2_action,
    register_artifact,
    repair_ledger_tail,
    write_snapshot,
    _scope_metadata,
)
from engagement_views import render_views, write_views
from environment_preflight import collect_preflight as collect_agent_preflight, review_preflight
from finding_review import claim_tuple_hash, render_claim_proof
from ledger_health import probe_ledger_health
from memory_disposition import close_engagement, record_memory_disposition
from completion_claims import assert_completion_claims_clear, assert_completion_claims_clear_bound, assert_completion_claims_token_current_bound
from reporting import accept_report, generate_report, record_submission
from research_telemetry import _remove_published_output, export_telemetry, score_telemetry
from decision6_capabilities import artifact_variant, classify_command, classify_event, load_capability_matrix, require_actor
from engagement_quarantine import QUARANTINE_REASONS, _open_directory, _require_bound_parent_safe, atomic_publish_offline_tree, atomic_write_offline, clear_marker_exact, create_marker_exclusive, inspect_quarantine, read_safe_offline_file, read_safe_offline_tree, require_safe_offline_input, require_safe_offline_output
from work_queue_actions import (
    QUEUE_INSPECTION_COMMANDS,
    queue_command_error_payload,
    queue_command_payload,
    queue_gate_exit,
)
from driver_action_admission import consume_action_admission, forward_action_to_broker
from frozen_corpus import require_enumerated_count_matches, resolve_frozen_corpus_denominator
from operator_signature import (
    encode_operator_signature_proof,
    ending_override_action,
    operator_challenge_bytes,
    verify_operator_signature_bytes,
)


_EMIT_BUFFER: ContextVar[bytearray | None] = ContextVar("run_engagement_emit_buffer", default=None)
_AUTHENTICATED_RUNTIME: ContextVar[dict[str, object] | None] = ContextVar(
    "run_engagement_authenticated_runtime", default=None
)
REVIEW_SIGNATURE_MAX_BYTES = 256 * 1024
REVIEW_ALLOWED_SIGNERS_MAX_BYTES = 1024 * 1024
SSH_VERIFY_TIMEOUT_SECONDS = 5.0
REVIEW_STAGING_TIMEOUT_SECONDS = 10.0
REVIEW_STAGING_MAX_ENTRIES = 10_000
REVIEW_STAGING_MAX_ALLOCATED_BYTES = 512 * 1024 * 1024
REVIEW_STAGING_MAX_DEPTH = 64


def base_event(*args: object, **kwargs: object) -> dict[str, object]:
    """Build an event and, inside the trusted broker, stamp its authenticated producer."""

    event = _base_event(*args, **kwargs)  # type: ignore[arg-type]
    runtime = _AUTHENTICATED_RUNTIME.get()
    if isinstance(runtime, dict):
        runtime_session_ref = runtime.get("runtime_session_ref")
        runtime_model = runtime.get("model")
        if not isinstance(runtime_session_ref, str) or not runtime_session_ref:
            raise RecordError("driver_authenticated_runtime_invalid", "runtime_session_ref")
        if not isinstance(runtime_model, str) or not runtime_model:
            raise RecordError("driver_authenticated_runtime_invalid", "model")
        provenance = event["provenance"]
        provenance["runtime_session_ref"] = runtime_session_ref
        provenance["model"] = runtime_model
        provenance["provider"] = runtime.get("provider")
    return event


def emit(value: object) -> None:
    data = canonical_json_bytes(value)
    buffer = _EMIT_BUFFER.get()
    if buffer is None:
        sys.stdout.buffer.write(data)
    else:
        buffer.extend(data)


def _command_json(args: argparse.Namespace, attribute: str) -> dict[str, object]:
    admitted = getattr(args, "_driver_admitted_documents", {})
    if isinstance(admitted, dict) and attribute in admitted:
        value = admitted[attribute].get("value")
        if not isinstance(value, dict):
            raise RecordError("driver_action_predicate_input_invalid", attribute)
        return copy.deepcopy(value)
    return load_json(getattr(args, attribute))


def _command_bytes(
    args: argparse.Namespace, attribute: str, *, max_bytes: int | None = None
) -> bytes:
    admitted = getattr(args, "_driver_admitted_documents", {})
    if isinstance(admitted, dict) and attribute in admitted:
        value = admitted[attribute].get("bytes")
        if not isinstance(value, bytes) or (
            max_bytes is not None and len(value) > max_bytes
        ):
            raise RecordError("driver_action_predicate_input_invalid", attribute)
        return bytes(value)
    return _read_regular_file_once(
        Path(getattr(args, attribute)), max_bytes=max_bytes
    )[0]


def _require_offline_output(path: Path) -> None:
    try:
        require_safe_offline_output(path)
    except ValueError as exc:
        raise RecordError("offline_output_forbidden", "offline output destination is governed or quarantined") from exc


def _require_bound_source_current(logical: Path, bound: Path, *, label: str) -> None:
    try:
        opened = os.fstat(int(bound.parts[3]))
        named = os.stat(logical, follow_symlinks=False)
    except (OSError, ValueError, IndexError) as exc:
        raise RecordError("engagement_source_changed", f"{label} source changed") from exc
    if (
        stat.S_ISLNK(named.st_mode)
        or not stat.S_ISDIR(named.st_mode)
        or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
        or inspect_quarantine(bound)["quarantined"]
        or inspect_quarantine(logical)["quarantined"]
    ):
        raise RecordError("engagement_source_changed", f"{label} source changed")


def _offline_file_preimage(path: Path) -> tuple[bool, bytes | None]:
    require_safe_offline_output(path)
    try:
        os.stat(path, follow_symlinks=False)
    except FileNotFoundError:
        return False, None
    return True, read_safe_offline_file(path)


def _rollback_offline_file(path: Path, published: bytes, existed: bool, prior: bytes | None) -> None:
    try:
        if read_safe_offline_file(path) != published:
            return
        if existed and prior is not None:
            atomic_write_offline(path, prior)
        else:
            _remove_published_output(path, published)
    except (FileNotFoundError, OSError, ValueError):
        return


def _remove_exact_offline_tree(path: Path, expected: dict[str, bytes]) -> None:
    """Remove only the exact newly published tree after source admission fails."""

    try:
        if read_safe_offline_tree(path) != expected:
            return
    except (OSError, ValueError):
        return
    absolute = Path(os.path.abspath(path))
    resolved_parent = absolute.parent.resolve(strict=True)
    parent_fd = _open_directory(resolved_parent)
    rollback = f".{absolute.name}.{os.getpid()}.{secrets.token_hex(8)}.rollback"

    def remove(directory_fd: int) -> None:
        for name in os.listdir(directory_fd):
            entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if stat.S_ISDIR(entry.st_mode) and not stat.S_ISLNK(entry.st_mode):
                child = os.open(name, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
                try:
                    remove(child)
                finally:
                    os.close(child)
                os.rmdir(name, dir_fd=directory_fd)
            elif stat.S_ISREG(entry.st_mode) and not stat.S_ISLNK(entry.st_mode):
                os.unlink(name, dir_fd=directory_fd)
            else:
                raise ValueError("offline rollback tree changed")

    try:
        _require_bound_parent_safe(parent_fd, resolved_parent, absolute.name, output=True)
        tree_fd = os.open(absolute.name, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd)
        try:
            opened = os.fstat(tree_fd)
        finally:
            os.close(tree_fd)
        current = os.stat(absolute.name, dir_fd=parent_fd, follow_symlinks=False)
        if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
            return
        os.rename(absolute.name, rollback, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        moved = os.stat(rollback, dir_fd=parent_fd, follow_symlinks=False)
        if (opened.st_dev, opened.st_ino) != (moved.st_dev, moved.st_ino):
            os.rename(rollback, absolute.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            return
        if read_safe_offline_tree(resolved_parent / rollback) != expected:
            os.rename(rollback, absolute.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            return
        rollback_fd = os.open(rollback, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd)
        try:
            remove(rollback_fd)
        finally:
            os.close(rollback_fd)
        os.rmdir(rollback, dir_fd=parent_fd)
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)


def _governed_entry_stat(path: Path) -> os.stat_result:
    root, parts = _governed_root(path)
    parent_fd, name = _open_parent_fd(root, parts, create=False)
    try:
        return os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    finally:
        os.close(parent_fd)


def _governed_regular_bytes_or_none(path: Path) -> bytes | None:
    try:
        return read_governed_file(path)
    except FileNotFoundError:
        return None


def _open_governed_regular(path: Path) -> int:
    root, parts = _governed_root(path)
    parent_fd, name = _open_parent_fd(root, parts, create=False)
    try:
        fd = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
            dir_fd=parent_fd,
        )
    finally:
        os.close(parent_fd)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise RecordError("unsafe_governed_path", "governed entry is not a regular file")
    return fd


def _unlink_governed_file(path: Path) -> None:
    root, parts = _governed_root(path)
    parent_fd, name = _open_parent_fd(root, parts, create=False)
    try:
        entry = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(entry.st_mode):
            raise RecordError("unsafe_governed_path", "governed entry is not a regular file")
        os.unlink(name, dir_fd=parent_fd)
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)


def _chmod_governed_file(path: Path, mode: int) -> None:
    fd = _open_governed_regular(path)
    try:
        os.fchmod(fd, mode)
        os.fsync(fd)
    finally:
        os.close(fd)


def _mkdir_governed(path: Path) -> None:
    root, parts = _governed_root(path)
    parent_fd, name = _open_parent_fd(root, parts, create=True)
    try:
        try:
            os.mkdir(name, 0o700, dir_fd=parent_fd)
        except FileExistsError:
            entry = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if not stat.S_ISDIR(entry.st_mode) or stat.S_ISLNK(entry.st_mode):
                raise RecordError("unsafe_governed_path", "governed directory entry is unsafe")
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)


def _relative_regular_files(engagement: Path, top: str, *, suffix: str | None = None) -> set[str]:
    """Enumerate one governed subtree through dirfds, including on macOS /dev/fd aliases."""

    root, parts = _governed_root(engagement / top)
    try:
        parent_fd, name = _open_parent_fd(root, parts, create=False)
        try:
            directory_fd = os.open(
                name,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=parent_fd,
            )
        finally:
            os.close(parent_fd)
    except FileNotFoundError:
        return set()
    result: set[str] = set()

    def visit(directory_fd: int, prefix: tuple[str, ...]) -> None:
        for child_name in sorted(os.listdir(directory_fd)):
            child = os.stat(child_name, dir_fd=directory_fd, follow_symlinks=False)
            relative = (*prefix, child_name)
            if stat.S_ISDIR(child.st_mode) and not stat.S_ISLNK(child.st_mode):
                child_fd = os.open(
                    child_name,
                    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=directory_fd,
                )
                try:
                    visit(child_fd, relative)
                finally:
                    os.close(child_fd)
            elif stat.S_ISREG(child.st_mode) and not stat.S_ISLNK(child.st_mode):
                value = Path(top, *relative).as_posix()
                if child_name != ".gitkeep" and (suffix is None or child_name.endswith(suffix)):
                    result.add(value)

    try:
        visit(directory_fd, ())
        return result
    finally:
        os.close(directory_fd)


def command_validate(args: argparse.Namespace) -> int:
    if args.schema_documents:
        problems = validate_schema_documents()
        result = {"valid": not problems, "problems": problems}
    elif args.fixture_suite:
        result = validate_fixture_suite(Path(args.fixture_suite) if isinstance(args.fixture_suite, str) else None)
        result["valid"] = not result["failures"]
    elif args.legacy_root:
        if args.output:
            _require_offline_output(args.output)
        inventory = legacy_finding_inventory(args.legacy_root)
        if args.output:
            write_canonical_json(args.output, inventory)
        result = inventory
        result["valid"] = inventory["counts"]["parse_error"] == 0
    elif args.file:
        if args.engagement:
            logical = args.engagement.absolute()
            try:
                relative = args.file.absolute().relative_to(logical)
            except ValueError:
                relative = None
            with bound_engagement_source(logical) as bound:
                pending_error: RecordError | None = None
                result = None
                try:
                    data = (
                        read_governed_file(bound / relative)
                        if relative is not None
                        else read_safe_offline_file(args.file)
                    )
                    record = json.loads(
                        data.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs
                    )
                    schema_name = resolve_schema_name(record, args.schema)
                    errors = validate_record(record, schema_name)
                    if not errors:
                        errors = validate_record_references(
                            record, schema_name, build_reference_index(bound)
                        )
                    result = {"valid": not errors, "schema": schema_name, "file": str(args.file), "errors": errors}
                except (UnicodeDecodeError, json.JSONDecodeError, OSError, ValueError, RecordError) as exc:
                    pending_error = RecordError("validation_input_invalid", "validation input could not be read")
                _require_bound_source_current(logical, bound, label="validation")
                if pending_error is not None:
                    raise pending_error
                assert result is not None
                emit(result)
                return 0 if result.get("valid") else 1
        record = load_json(args.file)
        schema_name = resolve_schema_name(record, args.schema)
        if args.schema_only or schema_name == "finding-v2-legacy":
            errors = validate_record(record, schema_name)
        else:
            raise RecordError("engagement_context_required", "new records require --engagement for reference validation; use --schema-only only for isolated fixture work")
        result = {"valid": not errors, "schema": schema_name, "file": str(args.file), "errors": errors}
    else:
        raise RecordError("validation_input_required", "choose --schema-documents, --fixture-suite, --legacy-root, or --file")
    emit(result)
    return 0 if result.get("valid") else 1


def command_runtime_identity(args: argparse.Namespace) -> int:
    actor_id, session_id = _local_identity(args.role); emit({"actor_role": args.role, "actor_id": actor_id, "session_id": session_id}); return 0


def command_init(args: argparse.Namespace) -> int:
    metadata=_scope_metadata(args.engagement.absolute()/"scope.md");operator_id=re.sub(r"[^A-Za-z0-9._:-]+","-",metadata["operator"]).strip("-") or "operator";_enforce_mutation(classify_command("init"),args.engagement,"operator",operator_id,f"initialize-engagement:{args.recorded_at}")
    snapshot = initialize_engagement(args.engagement, args.recorded_at)
    emit({"ok": True, "engagement_id": snapshot["engagement_id"], "scope_hash": snapshot["scope_hash"], "event_count": snapshot["event_count"]})
    return 0


def _require_bound_operator_signature(*, engagement: Path, operator_id: str, operation: str,
                                      scope_hash: str, scope_bytes: bytes,
                                      ledger_hash: str | None, signer_pin: str | None = None,
                                      engagement_id: str | None = None,
                                      include_proof: bool = False) -> str | dict[str, str]:
    if signer_pin is None:
        signer_match=re.search(rb"Operator allowed signers SHA256:\s*(sha256:[0-9a-f]{64})",scope_bytes)
        signer_pin=signer_match.group(1).decode() if signer_match is not None else None
    challenge_bytes=operator_challenge_bytes(engagement_id=engagement_id or engagement.name,scope_hash=scope_hash,ledger_hash=ledger_hash,operation=operation,operator_id=operator_id);challenge_digest=sha256_bytes(challenge_bytes);sys.stderr.write("Operator signature challenge:\n"+challenge_bytes.decode());sys.stderr.flush()
    signature_name=os.environ.get("HARNESS_OPERATOR_SIGNATURE_FILE");signers_name=os.environ.get("HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE")
    if signer_pin is None or not signature_name or not signers_name:raise RecordError("operator_signature_required",challenge_digest)
    try:signature_bytes,_=_read_regular_file_once(Path(signature_name),max_bytes=REVIEW_SIGNATURE_MAX_BYTES);signers_bytes,_=_read_regular_file_once(Path(signers_name),max_bytes=REVIEW_ALLOWED_SIGNERS_MAX_BYTES)
    except (OSError,RecordError) as exc:raise RecordError("operator_signature_invalid",challenge_digest) from exc
    if detect_secret_classes(signature_bytes) or detect_secret_classes(signers_bytes):raise RecordError("operator_signature_invalid",challenge_digest)
    if sha256_bytes(signers_bytes)!=signer_pin:raise RecordError("operator_signature_invalid",challenge_digest)
    signer_fingerprint=verify_operator_signature_bytes(scope_bytes=scope_bytes,operator_id=operator_id,challenge_bytes=challenge_bytes,signature_bytes=signature_bytes,allowed_signers_bytes=signers_bytes)
    return encode_operator_signature_proof(challenge_bytes=challenge_bytes,signature_bytes=signature_bytes,allowed_signers_bytes=signers_bytes,signer_fingerprint=signer_fingerprint) if include_proof else challenge_digest


def _require_operator_console(engagement: Path, operator_id: str, operation: str, *, include_proof: bool = False) -> str | dict[str, str]:
    engagement=engagement.absolute();events=read_ledger(engagement,"event")
    if events:
        attestation=next(event for event in reversed(events) if event["event_type"]=="scope.attested");signed=attestation["payload"]["operator_id"];scope_hash=attestation["payload"]["scope_hash"];scope_bytes=read_governed_file(engagement/attestation["payload"]["scope_snapshot_path"]);ledger_hash=events[-1]["record_hash"];logical_engagement_id=attestation["engagement_id"]
    else:
        metadata=_scope_metadata(engagement/"scope.md");signed=re.sub(r"[^A-Za-z0-9._:-]+","-",metadata["operator"]).strip("-") or "operator";scope_hash=metadata["scope_hash"];scope_bytes=read_governed_file(engagement/"scope.md");ledger_hash=None;logical_engagement_id=engagement.name
    if sha256_bytes(scope_bytes)!=scope_hash:raise RecordError("operator_scope_snapshot_invalid",scope_hash)
    if operator_id!=signed:raise RecordError("operator_authority_invalid","operator id does not match the active attested scope")
    return _require_bound_operator_signature(engagement=engagement,operator_id=operator_id,operation=operation,scope_hash=scope_hash,scope_bytes=scope_bytes,ledger_hash=ledger_hash,engagement_id=logical_engagement_id,include_proof=include_proof)


def _require_session(provenance: dict[str, object], operation: str) -> str:
    if not isinstance(provenance.get("session_id"), str) or not provenance["session_id"]:
        raise RecordError("session_provenance_required", operation)
    return str(provenance["session_id"])


def _local_identity(role: str) -> tuple[str, str]:
    uid = os.getuid(); session = os.getsid(0)
    return f"local-uid-{uid}:{role}", f"session-posix-{uid}-{session}"


def _require_local_provenance(role: str, actor_id: str, session_id: str) -> None:
    expected_actor, expected_session = _local_identity("broker")
    if role != "broker" or actor_id != expected_actor or session_id != expected_session:
        raise RecordError("runtime_provenance_not_principal_bound", role)


def _require_local_orchestrator_provenance(actor_id: str, session_id: str) -> None:
    expected_actor, expected_session = _local_identity("orchestrator")
    if actor_id != expected_actor or session_id != expected_session:
        raise RecordError("runtime_provenance_not_principal_bound", "orchestrator")


def _require_local_session(session_id: str) -> None:
    if session_id != _local_identity("operator")[1]:
        raise RecordError("runtime_session_not_process_bound", "operator")


ARTIFACT_PERMIT_FIELDS = {"schema_version", "classification_id", "classification_event_ref", "artifact_id", "engagement_id", "relative_path", "advisory_zone", "operation_class", "metadata_digest", "scope_hash", "environment_ref", "classified_at", "expires_at", "source_digest", "source_size", "action_digest", "file_absent_at_classification", "decision"}


def _zone2_plan(metadata: dict[str, object], *, planned_sha256: str, planned_size: int, relative_path: str, scope_hash: str, environment_ref: str, cleanup_obligation_ref: str) -> dict[str, object]:
    return {"artifact_id": metadata.get("artifact_id"), "metadata_digest": sha256_bytes(canonical_json_bytes(metadata)), "planned_sha256": planned_sha256, "planned_size": planned_size, "relative_path": relative_path, "scope_hash": scope_hash, "environment_ref": environment_ref, "cleanup_obligation_ref": cleanup_obligation_ref, "cleanup_obligation_id": metadata.get("cleanup_obligation_id")}


def _authority_action(action_kind: str, **fields: object) -> dict[str, object]:
    return {"action_kind": action_kind, **fields}


def _read_regular_file_once(
    path: Path, *, max_bytes: int | None = None
) -> tuple[bytes, os.stat_result]:
    fd = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
    ); data = bytearray()
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode): raise RecordError("bound_input_not_regular", str(path))
        if max_bytes is not None and before.st_size > max_bytes:
            raise RecordError("bound_input_oversize", str(path))
        while True:
            remaining = None if max_bytes is None else max_bytes - len(data)
            chunk = os.read(
                fd,
                1024 * 1024 if remaining is None else min(1024 * 1024, remaining + 1),
            )
            if not chunk: break
            data.extend(chunk)
            if max_bytes is not None and len(data) > max_bytes:
                raise RecordError("bound_input_oversize", str(path))
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns): raise RecordError("bound_input_changed_during_read", str(path))
        return bytes(data), after
    finally: os.close(fd)


def _read_migration_authority_input(path: Path) -> tuple[bytes, os.stat_result]:
    """Buffer a migration authority input only while its source is admissible."""

    try:
        data = read_safe_offline_file(path)
        resolved = path.resolve(strict=True)
        identity = resolved.stat(follow_symlinks=False)
        require_safe_offline_input(resolved)
    except ValueError as exc:
        raise RecordError("migration_authority_input_quarantined", "migration authority input is quarantined or governed") from exc
    except OSError as exc:
        raise RecordError("migration_authority_input_invalid", "migration authority input is unavailable") from exc
    return data, identity


def _require_migration_authority_inputs_current(inputs: tuple[tuple[Path, os.stat_result], ...]) -> None:
    """Final source-state and identity check before authority consumption or effects."""

    for path, expected in inputs:
        try:
            require_safe_offline_input(path)
            current_path = path.resolve(strict=True)
            require_safe_offline_input(current_path)
            current = current_path.stat(follow_symlinks=False)
        except ValueError as exc:
            raise RecordError("migration_authority_input_quarantined", "migration authority input is quarantined or governed") from exc
        except (OSError, RuntimeError) as exc:
            raise RecordError("migration_authority_input_changed", "migration authority input changed") from exc
        if (
            stat.S_ISLNK(current.st_mode)
            or not stat.S_ISREG(current.st_mode)
            or (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns)
            != (expected.st_dev, expected.st_ino, expected.st_size, expected.st_mtime_ns)
        ):
            raise RecordError("migration_authority_input_changed", "migration authority input changed")


def _open_bound_directory(path: Path) -> tuple[int, Path, dict[str, int]]:
    absolute = Path(os.path.abspath(path))
    try:
        terminal = absolute.lstat()
    except OSError as exc:
        raise RecordError("migration_directory_identity_invalid", "migration directory unavailable") from exc
    if stat.S_ISLNK(terminal.st_mode) or not stat.S_ISDIR(terminal.st_mode):
        raise RecordError("migration_directory_identity_invalid", "migration directory must be a regular directory")
    resolved_parent = absolute.parent.resolve(strict=True)
    components = (*resolved_parent.parts[1:], absolute.name)
    current = os.open("/", os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        for component in components:
            following = os.open(component, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0), dir_fd=current); os.close(current); current = following
        result = os.fstat(current); return current, Path(os.path.realpath(absolute)), {"device": result.st_dev, "inode": result.st_ino}
    except Exception:
        os.close(current); raise


def _require_bound_directory_current(fd: int, resolved: Path, identity: dict[str, int], reference: str) -> None:
    try:
        fd_stat = os.fstat(fd)
        path_stat = os.stat(resolved, follow_symlinks=False)
    except OSError as exc:
        raise RecordError("migration_directory_identity_changed", reference) from exc
    expected = (identity["device"], identity["inode"])
    if (
        (fd_stat.st_dev, fd_stat.st_ino) != expected
        or (path_stat.st_dev, path_stat.st_ino) != expected
        or not stat.S_ISDIR(fd_stat.st_mode)
        or stat.S_ISLNK(path_stat.st_mode)
        or not stat.S_ISDIR(path_stat.st_mode)
    ):
        raise RecordError("migration_directory_identity_changed", reference)


def _require_migration_directories_separate(source: Path, destination: Path) -> None:
    """Reject aliases and nesting using real canonical paths, never ``/dev/fd`` aliases."""

    try:
        source_is_ancestor = any(
            os.path.samefile(source, candidate)
            for candidate in (destination, *destination.parents)
            if candidate.exists()
        )
        destination_is_ancestor = any(
            os.path.samefile(destination, candidate)
            for candidate in (source, *source.parents)
            if candidate.exists()
        )
    except OSError as exc:
        raise RecordError(
            "migration_directory_identity_invalid",
            "migration directory ancestry unavailable",
        ) from exc
    if source_is_ancestor or destination_is_ancestor:
        raise RecordError(
            "migration_directory_alias",
            "migration source and destination must be filesystem-separate",
        )


def _validated_migration_engagement_id(value: object) -> str:
    if not isinstance(value, str) or value in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", value):
        raise RecordError("migration_proposal_identity_invalid", "engagement_id")
    return value


def _migration_proposal_identity(proposal_bytes: bytes) -> str:
    def closed_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        value: dict[str, object] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate")
            value[key] = item
        return value
    try:
        proposal = json.loads(proposal_bytes, object_pairs_hook=closed_object)
        return _validated_migration_engagement_id(proposal["engagement_id"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise RecordError("migration_proposal_identity_invalid", "engagement_id") from exc


def _require_migration_tree_safety(root_fd: int, destination_fd: int, proposal_bytes: bytes, *, resume: bool = False, bound_source_fd: int | None = None) -> None:
    engagement_id = _migration_proposal_identity(proposal_bytes)
    if not resume and set(os.listdir(destination_fd)) not in ({"scope.md"}, {"scope.md", ".record-kernel.lock"}): raise RecordError("migration_destination_not_pristine", "destination must contain only a regular signed scope.md")
    scope_fd = os.open("scope.md", os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=destination_fd)
    try:
        if not stat.S_ISREG(os.fstat(scope_fd).st_mode): raise RecordError("migration_destination_scope_invalid", "scope.md")
    finally: os.close(scope_fd)
    base_fd = root_fd
    try:
        if bound_source_fd is None:
            try: candidate = os.open("engagements", os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0), dir_fd=root_fd)
            except FileNotFoundError: candidate = -1
            if candidate >= 0: base_fd = candidate
            source_fd = os.open(engagement_id, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0), dir_fd=base_fd)
        else:
            source_fd = os.dup(bound_source_fd)
        try:
            def reject_symlinks(directory_fd: int) -> None:
                for name in sorted(os.listdir(directory_fd)):
                    entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                    if stat.S_ISLNK(entry.st_mode):
                        raise RecordError("migration_source_symlink_rejected", "migration source contains a symbolic link")
                    if stat.S_ISDIR(entry.st_mode):
                        child_fd = os.open(
                            name,
                            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                            dir_fd=directory_fd,
                        )
                        try:
                            reject_symlinks(child_fd)
                        finally:
                            os.close(child_fd)
            reject_symlinks(source_fd)
        finally: os.close(source_fd)
    finally:
        if base_fd != root_fd: os.close(base_fd)


def _require_decision6_kernel(engagement: Path) -> None:
    events=read_ledger(engagement.absolute(),"event"); attestation=next((event for event in reversed(events) if event["event_type"]=="scope.attested"),None)
    if attestation is None or attestation.get("payload",{}).get("record_kernel") not in {"decision-0006-v1", "decision-0006-v2"}: raise RecordError("decision6_kernel_not_selected","signed scope must select a decision-0006 kernel for autonomous broker or async-authority commands")


def _require_async_authority(args: argparse.Namespace, action: dict[str, object], applied_at: str) -> None:
    _require_decision6_kernel(args.engagement)
    _require_local_provenance("broker", args.executor_id, args.session_id)
    if abs((datetime.fromisoformat(applied_at.replace("Z", "+00:00")) - datetime.now(timezone.utc)).total_seconds()) > 60:
        raise RecordError("authority_application_time_not_current", str(action["action_kind"]))
    request_id = getattr(args, "authority_request_id", None)
    if not request_id:
        raise RecordError("approved_authority_request_required", action["action_kind"])
    lane_id = action.get("lane_id")
    if not isinstance(lane_id, str) or not lane_id:
        raise RecordError("authority_action_lane_required", str(action["action_kind"]))
    require_approved_authority(args.engagement.absolute(), request_id, str(action["action_kind"]), sha256_bytes(canonical_json_bytes(action)), lane_id, applied_at)


def _enforce_mutation(capability: dict[str, object], engagement: Path, actor_role: str, actor_id: str, operation: str) -> None:
    if actor_role == "broker": _require_decision6_kernel(engagement)
    if actor_role == "operator" and capability["tier"] == "notebook":
        _require_operator_console(engagement, actor_id, operation)
    require_actor(capability, actor_role)
    if capability["tier"] in {"authority", "real_world"}:
        if actor_role != "operator":
            raise RecordError("operator_authority_invalid", operation)
        _require_operator_console(engagement, actor_id, operation)


def command_append_event(args: argparse.Namespace) -> int:
    proposal = _command_json(args, "file")
    capability = classify_event(proposal.get("event_type", ""), proposal.get("payload", {}))
    actor = proposal.get("actor", {})
    if capability["tier"] != "notebook":
        raise RecordError("canonical_authority_command_required", proposal.get("event_type", "unknown"))
    if proposal.get("event_type") in {"environment.preflight_recorded", "artifact.classified", "scope.amendment_proposed", "authority.requested", "authority.expired", "coverage.reopened"}:
        raise RecordError("canonical_notebook_command_required", proposal.get("event_type", "unknown"))
    if proposal.get("event_type") == "observation.recorded" and proposal.get("payload", {}).get("entity_type") == "task_notice":
        raise RecordError("canonical_task_notice_command_required", proposal.get("event_id", "unknown"))
    if proposal.get("event_type") == "coverage.status_changed" and proposal.get("payload", {}).get("status") == "budget_bounded":
        raise RecordError("external_driver_budget_boundary_required", "budget_bounded")
    _enforce_mutation(capability, args.engagement, actor.get("role", ""), actor.get("id", ""), f"append-event:{proposal.get('event_type','event')}:{proposal.get('event_id','unknown')}:{sha256_bytes(canonical_json_bytes(proposal))}")
    if proposal.get("operation_class") != capability["tier"]:
        raise RecordError("event_operation_class_mismatch", proposal.get("event_type", "unknown"))
    if capability["tier"] == "notebook":
        session_id = _require_session(proposal.get("provenance", {}), proposal.get("event_type", "event")); _require_local_provenance(str(actor.get("role", "")), str(actor.get("id", "")), session_id)
    record = append_event(args.engagement.absolute(), proposal)
    emit({"ok": True, "event_id": record["event_id"], "sequence": record["sequence"], "record_hash": record["record_hash"]})
    return 0


def command_classify_artifact(args: argparse.Namespace) -> int:
    if args.output:
        _require_offline_output(args.output)
    metadata = load_json(args.metadata)
    metadata_secret_classes=detect_secret_classes(canonical_json_bytes(metadata))
    if metadata_secret_classes: raise RecordError("secret_shaped_artifact_metadata","artifact metadata blocked before classification",[{"class":value} for value in metadata_secret_classes])
    _require_local_provenance(args.actor_role, args.actor_id, args.session_id)
    variant = artifact_variant(metadata)
    caller = {"role": args.actor_role, "id": args.actor_id}
    if variant == "clear_local":
        if args.source is None:
            raise RecordError("artifact_source_required", metadata.get("artifact_id", "unknown"))
        source = args.source.resolve(strict=True)
        if args.source.is_symlink() or not source.is_file():
            raise RecordError("artifact_source_invalid", str(args.source))
        if scan_file_secret_classes(source):
            raise RecordError("secret_shaped_artifact_content", "planned artifact source contains a forbidden secret shape")
        source_executable = bool(source.stat().st_mode & 0o111)
        if source_executable != bool(metadata.get("contains_executable_capability")):
            raise RecordError("artifact_source_executable_mismatch", metadata.get("artifact_id", "unknown"))
        source_digest, source_size = sha256_file(source), source.stat().st_size
    else:
        if args.source is not None or not args.planned_sha256 or args.planned_size is None:
            raise RecordError("zone2_planned_bytes_contract_required", metadata.get("artifact_id", "unknown"))
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", args.planned_sha256) or args.planned_size < 0:
            raise RecordError("zone2_planned_bytes_contract_invalid", metadata.get("artifact_id", "unknown"))
        source_digest, source_size = args.planned_sha256, args.planned_size
    if metadata.get("advisory_zone") not in ({"clear_local"} if variant == "clear_local" else {"review_required", "unknown"}):
        raise RecordError("artifact_zone_underclassified", metadata.get("artifact_id", "unknown"))
    capability = classify_command("classify-artifact", variant=variant)
    if caller["role"]=="broker": _require_decision6_kernel(args.engagement)
    actor = metadata.get("producer", {})
    if capability["tier"] == "notebook" and (caller != actor or args.session_id != metadata.get("producer_session_id")):
        raise RecordError("artifact_classifier_identity_mismatch", metadata.get("artifact_id", "unknown"))
    require_actor(capability, caller["role"])
    if metadata.get("operation_class") != capability["tier"] or not metadata.get("producer_session_id"):
        raise RecordError("artifact_provenance_invalid", metadata.get("artifact_id", "unknown"))
    relative = args.relative_path.as_posix()
    if args.relative_path.is_absolute() or ".." in args.relative_path.parts or not relative.startswith("evidence/"):
        raise RecordError("artifact_path_not_contained", relative)
    engagement = args.engagement.absolute(); destination = engagement / relative; governed_root, governed_parts = _governed_root(destination)
    if governed_root != engagement or tuple(governed_parts) != tuple(args.relative_path.parts): raise RecordError("artifact_path_not_contained", relative)
    try:
        parent_fd, leaf = _open_parent_fd(governed_root, governed_parts, create=False)
        try:
            try: os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError: pass
            else: raise RecordError("artifact_bytes_precede_classification", relative)
        finally: os.close(parent_fd)
    except FileNotFoundError: raise RecordError("artifact_path_not_contained", relative)
    state = reduce_engagement(args.engagement.absolute())
    if metadata.get("engagement_id") != state["engagement_id"] or metadata.get("environment_ref") != state["active_environment_ref"]:
        raise RecordError("artifact_environment_not_active", metadata.get("artifact_id", "unknown"))
    action_digest = None
    if capability["tier"] == "real_world":
        if metadata.get("advisory_zone") != "review_required": raise RecordError("zone2_advisory_zone_invalid", metadata.get("artifact_id", "unknown"))
        plan = _zone2_plan(metadata, planned_sha256=source_digest, planned_size=source_size, relative_path=relative, scope_hash=state["scope_hash"], environment_ref=state["active_environment_ref"], cleanup_obligation_ref=metadata.get("cleanup_obligation_ref") or "")
        action_digest = sha256_bytes(canonical_json_bytes(plan))
        confirmation = next((event for event in read_ledger(args.engagement.absolute(), "event") if event["event_id"] == metadata.get("escalation_confirmation_event_ref")), None)
        if confirmation is None or confirmation["event_type"] != "escalation.confirmed" or confirmation["payload"].get("entity_id") != metadata.get("artifact_id") or confirmation["payload"].get("environment_ref") != state["active_environment_ref"] or confirmation["payload"].get("action_digest") != action_digest:
            raise RecordError("artifact_creation_requires_fresh_confirmation", metadata.get("artifact_id", "unknown"))
        expiry = datetime.fromisoformat(confirmation["payload"]["expires_at"].replace("Z", "+00:00"))
        if datetime.fromisoformat(args.recorded_at.replace("Z", "+00:00")) > expiry:
            raise RecordError("artifact_confirmation_expired", metadata.get("artifact_id", "unknown"))
        decision = "allow_confirmed_creation"; expires_at = confirmation["payload"]["expires_at"]
    else:
        decision = "allow_local_creation"; expires_at = None
    permit_body = {"schema_version": 1, "classification_id": f"classification-{metadata['artifact_id']}", "artifact_id": metadata["artifact_id"], "engagement_id": state["engagement_id"], "relative_path": relative, "advisory_zone": metadata["advisory_zone"], "operation_class": capability["tier"], "metadata_digest": sha256_bytes(canonical_json_bytes(metadata)), "scope_hash": state["scope_hash"], "environment_ref": state["active_environment_ref"], "classified_at": args.recorded_at, "expires_at": expires_at, "source_digest": source_digest, "source_size": source_size, "action_digest": action_digest, "file_absent_at_classification": True, "decision": decision}
    classification_digest = sha256_bytes(canonical_json_bytes(permit_body)); event_id = f"event-{permit_body['classification_id']}"
    existing = next((event for event in read_ledger(args.engagement.absolute(), "event") if event["event_id"] == event_id), None)
    if existing is None:
        classified_event = base_event(event_id=event_id, engagement_id=state["engagement_id"], recorded_at=args.recorded_at, actor_role=caller["role"], actor_id=caller["id"], event_type="artifact.classified", rationale="Bind planned artifact bytes before destination creation.", payload={"classification_id": permit_body["classification_id"], "classification_digest": classification_digest, "artifact_id": metadata["artifact_id"], "source_digest": permit_body["source_digest"], "source_size": permit_body["source_size"], **({"action_digest": action_digest} if action_digest else {}), "advisory_zone": metadata["advisory_zone"], "scope_hash": state["scope_hash"], "environment_ref": state["active_environment_ref"], "classified_at": args.recorded_at, "expires_at": expires_at}, session_id=args.session_id, operation_class=capability["tier"], model=args.model, provider=args.provider, tool_versions=["decision6-artifact-classifier-v1", *args.tool_version])
        existing = _append_kernel_event(args.engagement.absolute(), classified_event)
    elif existing.get("payload", {}).get("classification_digest") != classification_digest:
        raise RecordError("artifact_classification_event_conflict", event_id)
    permit = {**permit_body, "classification_event_ref": event_id}
    if args.output:
        write_canonical_json(args.output, permit)
    emit(permit)
    return 0


def command_propose_scope(args: argparse.Namespace) -> int:
    _require_decision6_kernel(args.engagement)
    _require_local_provenance("broker", args.actor_id, args.session_id); data = args.draft.read_bytes()
    if not data or detect_secret_classes(data): raise RecordError("scope_draft_invalid", "empty or secret-shaped scope draft")
    engagement = args.engagement.absolute(); digest = sha256_bytes(data); relative = f"scope-drafts/{digest.removeprefix('sha256:')}.md"
    with engagement_lock(engagement) as bound_engagement:
        destination = bound_engagement / relative
        state = reduce_engagement(bound_engagement)
        existing = next((event for event in read_ledger(bound_engagement, "event") if event["event_type"] == "scope.amendment_proposed" and event["payload"].get("draft_digest") == digest), None)
        if existing is not None:
            record = existing
        else:
            prior_bytes = _governed_regular_bytes_or_none(destination)
            if prior_bytes is not None and prior_bytes != data: raise RecordError("scope_draft_collision", relative)
            if prior_bytes is None: atomic_write(destination, data)
            event = base_event(event_id=f"event-scope-draft-{digest[-12:]}", engagement_id=state["engagement_id"], recorded_at=args.recorded_at, actor_role="broker", actor_id=args.actor_id, event_type="scope.amendment_proposed", rationale=args.reason, payload={"draft_path": relative, "draft_digest": digest, "supersedes_scope_hash": state["scope_hash"]}, session_id=args.session_id, operation_class="notebook"); record = _append_kernel_event_idempotent(bound_engagement, event, lock_held=True)
    emit({"valid": True, "draft_path": relative, "draft_digest": digest, "event_id": record["event_id"], "authority_changed": False}); return 0


def command_reattest_scope(args: argparse.Namespace) -> int:
    _require_decision6_kernel(args.engagement)
    _require_local_provenance("broker", args.executor_id, args.session_id); engagement = args.engagement.absolute(); draft = args.draft.resolve(strict=True); draft_bytes = draft.read_bytes(); draft_digest = sha256_bytes(draft_bytes); action = _authority_action("reattest-scope", lane_id=args.lane_id, executor_id=args.executor_id, session_id=args.session_id, draft_digest=draft_digest, operator_id=args.operator_id, recorded_at=args.recorded_at); action_digest = sha256_bytes(canonical_json_bytes(action)); require_repair_authority_from_intact_prefix(engagement, args.authority_request_id, "reattest-scope", action_digest, args.lane_id, args.recorded_at)
    draft_metadata = _scope_metadata(draft); normalized_operator = re.sub(r"[^A-Za-z0-9._:-]+", "-", draft_metadata["operator"]).strip("-") or "operator"; active_operator = next(event["payload"]["operator_id"] for event in reversed(read_ledger(engagement, "event")) if event["event_type"] == "scope.attested")
    if normalized_operator != args.operator_id or args.operator_id != active_operator or draft_metadata["scope_hash"] != draft_digest: raise RecordError("scope_reattestation_invalid", "scope amendment cannot silently replace the active operator identity")
    if not any(event["event_type"] == "scope.amendment_proposed" and event["payload"].get("draft_digest") == draft_digest for event in read_ledger(engagement, "event")): raise RecordError("scope_draft_not_proposed", draft_digest)
    with engagement_lock(engagement) as bound_engagement:
        prior_events = read_ledger(bound_engagement, "event"); prior_scope = next(event["payload"]["scope_hash"] for event in reversed(prior_events) if event["event_type"] == "scope.attested"); atomic_write(bound_engagement / "scope.md", draft_bytes); snapshot_path = persist_scope_snapshot(bound_engagement, draft_digest)
        event = base_event(event_id=f"event-scope-{draft_digest[-12:]}", engagement_id=prior_events[0]["engagement_id"], recorded_at=args.recorded_at, actor_role="operator", actor_id=args.operator_id, event_type="scope.attested", rationale=args.reason, payload={"scope_hash": draft_digest, "scope_snapshot_path": snapshot_path, "operator_id": args.operator_id, "signed_date": draft_metadata["date"], "record_kernel": draft_metadata["record_kernel"], "supersedes_scope_hash": prior_scope, "authority_request_ref": args.authority_request_id, "executor_id": args.executor_id}, entity_refs=[prior_events[0]["engagement_id"]], session_id=args.session_id, operation_class="authority"); applied = _append_kernel_event_idempotent(bound_engagement, event, lock_held=True)
    emit({"valid": True, "scope_hash": draft_digest, "event_id": applied["event_id"], "prior_scope_preserved": True}); return 0


def command_migrate_kernel(args: argparse.Namespace) -> int:
    """Upgrade a decision-0005 engagement to decision-0006 in place.

    Operator-console-signed (like `init`), not async-authority: the async-authority path itself calls
    `reduce_engagement` which the pre-migration orphan state blocks, so it cannot bootstrap. This is
    the one authority event that unlocks the kernel; the operator's SSH signature over the canonical
    challenge is required (see ADR 0009).

    It also reconciles the two orphan classes that block reduce after the switch:
      * unregistered `evidence/**` files are registered as artifacts (clear_local, digest-bound);
      * unbound `reports/*.md` drafts are moved to `report-drafts/` per decision-0006 section 7.1.
    """
    engagement = args.engagement.absolute()
    require_not_quarantined(engagement)
    events = read_ledger(engagement, "event")
    if not events:
        raise RecordError("scope_attestation_missing", "initialize engagement first")
    prior = next(event for event in reversed(events) if event["event_type"] == "scope.attested")
    prior_kernel = prior["payload"].get("record_kernel")
    if prior_kernel != "decision-0005-v1":
        raise RecordError("migrate_kernel_source_invalid",
                          f"source kernel is {prior_kernel!r}; only decision-0005-v1 may be upgraded")

    draft = args.draft.resolve(strict=True)
    if draft.is_symlink() or not draft.is_file():
        raise RecordError("scope_draft_invalid", "draft must be a regular file")
    draft_bytes = _read_regular_file_once(draft)[0]
    if not draft_bytes or detect_secret_classes(draft_bytes):
        raise RecordError("scope_draft_invalid", "empty or secret-shaped scope draft")
    draft_meta = _scope_metadata(draft)
    if draft_meta["record_kernel"] != "decision-0006-v1":
        raise RecordError("migrate_kernel_draft_invalid",
                          f"draft must select decision-0006-v1, got {draft_meta['record_kernel']!r}")
    active_operator = prior["payload"]["operator_id"]
    normalized_operator = re.sub(r"[^A-Za-z0-9._:-]+", "-", draft_meta["operator"]).strip("-") or "operator"
    if normalized_operator != args.operator_id or args.operator_id != active_operator:
        raise RecordError("scope_reattestation_invalid", "kernel migration cannot replace the active operator identity")
    if draft_meta["scope_hash"] != sha256_bytes(draft_bytes):
        raise RecordError("scope_draft_invalid", "draft metadata does not match draft bytes")

    # Operator console signature over the migration challenge. The signature is checked against the
    # DRAFT's signer binding (the draft is what becomes the new attested scope), so the binding is
    # introduced by this one operator-signed migration, exactly as init introduces it for a new
    # engagement.
    signature_name = os.environ.get("HARNESS_OPERATOR_SIGNATURE_FILE")
    signers_name = os.environ.get("HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE")
    if not signature_name or not signers_name:
        raise RecordError("operator_signature_required", "migrate-kernel requires an operator SSH signature bound in the draft scope")
    challenge = {"schema_version": 1, "namespace": "llm-redteam-harness-operator-v1",
                 "engagement_id": engagement.name, "scope_hash": draft_meta["scope_hash"],
                 "source_scope_hash": prior["payload"]["scope_hash"], "ledger_hash": events[-1]["record_hash"],
                 "operation": f"migrate-kernel:{draft_meta['scope_hash']}", "operator_id": args.operator_id}
    challenge_bytes = canonical_json_bytes(challenge)
    challenge_digest = sha256_bytes(challenge_bytes)
    try:
        signature_bytes, _ = _read_regular_file_once(
            Path(signature_name), max_bytes=REVIEW_SIGNATURE_MAX_BYTES
        )
        signers_bytes, _ = _read_regular_file_once(
            Path(signers_name), max_bytes=REVIEW_ALLOWED_SIGNERS_MAX_BYTES
        )
    except (OSError, RecordError) as exc:
        raise RecordError("operator_signature_invalid", challenge_digest, [str(exc)]) from exc
    verify_operator_signature_bytes(
        scope_bytes=draft_bytes,
        operator_id=args.operator_id,
        challenge_bytes=challenge_bytes,
        signature_bytes=signature_bytes,
        allowed_signers_bytes=signers_bytes,
    )

    with engagement_lock(engagement) as bound_engagement:
        locked_events = read_ledger(bound_engagement, "event")
        locked_prior = next(event for event in reversed(locked_events) if event["event_type"] == "scope.attested")
        if (
            locked_events[-1]["record_hash"] != challenge["ledger_hash"]
            or locked_prior["record_hash"] != prior["record_hash"]
            or _read_regular_file_once(draft)[0] != draft_bytes
        ):
            raise RecordError("operator_signature_stale", challenge_digest)
        # Reconciliation and scope activation are one marker-linearized transaction. Marker creation
        # waits on this lock; if it won first, the guard above refuses before any orphan move/write.
        registered, moved = _migrate_kernel_reconcile(
            bound_engagement, args.recorded_at, args.operator_id, args.executor_id, args.session_id,
            engagement_id=locked_events[0]["engagement_id"],
            attest_synthetic=args.attest_synthetic, lock_held=True,
        )
        prior_scope = locked_prior["payload"]["scope_hash"]
        atomic_write(bound_engagement / "scope.md", draft_bytes)
        snapshot_path = persist_scope_snapshot(bound_engagement, draft_meta["scope_hash"])
        event = base_event(
            event_id=f"event-scope-{draft_meta['scope_hash'][-12:]}",
            engagement_id=locked_events[0]["engagement_id"], recorded_at=args.recorded_at,
            actor_role="operator", actor_id=args.operator_id, event_type="scope.attested",
            rationale=args.reason,
            payload={"scope_hash": draft_meta["scope_hash"], "scope_snapshot_path": snapshot_path,
                     "operator_id": args.operator_id, "signed_date": draft_meta["date"],
                     "record_kernel": "decision-0006-v1", "supersedes_scope_hash": prior_scope,
                     "executor_id": args.executor_id},
            entity_refs=[locked_events[0]["engagement_id"]], session_id=args.session_id,
            operation_class="authority",
        )
        applied = _append_kernel_event_idempotent(bound_engagement, event, lock_held=True)
        snapshot = reduce_engagement(bound_engagement)
        write_snapshot(bound_engagement, snapshot)
        write_views(bound_engagement, snapshot)
    emit({"valid": True, "scope_hash": draft_meta["scope_hash"], "event_id": applied["event_id"],
          "registered_artifacts": registered, "moved_report_drafts": moved})
    return 0


def _migrate_kernel_reconcile(engagement: Path, recorded_at: str, operator_id: str,
                              executor_id: str, session_id: str,
                              *, engagement_id: str,
                              attest_synthetic: bool = False,
                              lock_held: bool = False) -> tuple[list[str], list[str]]:
    """Register unregistered evidence files as artifacts and move unbound report drafts to report-drafts/.

    Both orphan classes block `reduce_engagement` after the kernel switch, and the normal
    registration paths themselves call reduce, so the migration reconciles them directly (the
    migration command is the authority). Returns (registered_relative_paths, moved_draft_relative_paths).
    """
    import mimetypes

    engagement = engagement.absolute()
    if not lock_held:
        raise RecordError("migration_lock_required", "kernel migration reconciliation requires the engagement lock")
    require_not_quarantined(engagement)
    artifacts = read_ledger(engagement, "artifact")
    registered_paths = {a["relative_path"] for a in artifacts}
    events = read_ledger(engagement, "event")

    # Move unbound report drafts to report-drafts/ FIRST: every later reduce (including the artifact
    # registration path) fails on report orphans, so they must be gone before any evidence artifact is
    # registered.
    bound_reports = set()
    for e in events:
        if e["event_type"] == "record.committed" and e["payload"].get("record_type") == "report-manifest":
            try:
                rel = e["payload"]["record_path"]
                manifest = load_json(engagement / rel)
                bound_reports.add(manifest.get("report_path"))
            except (KeyError, OSError, RecordError):
                pass
    moved: list[str] = []
    drafts_dir = engagement / "report-drafts"
    _mkdir_governed(drafts_dir)
    for rel in sorted(_report_draft_relpaths(engagement) - bound_reports):
        source = engagement / rel
        destination = drafts_dir / source.name
        source_bytes = read_governed_file(source)
        destination_bytes = _governed_regular_bytes_or_none(destination)
        if destination_bytes is not None and destination_bytes != source_bytes:
            raise RecordError("report_draft_collision", rel)
        if destination_bytes is None:
            atomic_write(destination, source_bytes)
        _unlink_governed_file(source)
        moved.append(rel)

    state = reduce_engagement(engagement, allowed_artifact_orphans=_evidence_relpaths(engagement))
    environment_ref = state["active_environment_ref"]

    registered: list[str] = []
    # Bulk-register evidence orphans via the low-level append path. The per-file registration command
    # internally re-reduces with only THAT file allowed, which fails while sibling orphans still exist,
    # so the migration appends artifact records directly (the migration command is the authority).
    # Artifact created_at is set to the last PRE-migration event time: the migration's own
    # scope.attested resets the environment timeline to None, so artifacts created at/after it would
    # fail the environment-not-active check. Pre-migration times keep the active deps environment.
    prior_events = [e for e in events if e["event_type"] != "scope.attested"]
    artifact_created_at = prior_events[-1]["recorded_at"] if prior_events else recorded_at
    artifact_records = read_ledger(engagement, "artifact")
    index = build_reference_index(engagement)
    for rel in sorted(_evidence_relpaths(engagement) - registered_paths):
        source = engagement / rel
        try:
            data = read_governed_file(source)
        except (OSError, RecordError):
            continue
        secret_classes = detect_secret_classes(data)
        mime, _ = mimetypes.guess_type(source.name)
        artifact_id = f"artifact-migration-{sha256_bytes(data)[:16]}"
        proposal = {
            "schema_version": 1, "artifact_id": artifact_id, "engagement_id": engagement_id,
            "created_at": artifact_created_at, "producer": {"role": "migration", "id": executor_id},
            "acquisition_method": "migration", "target_refs": [], "environment_ref": environment_ref,
            "sensitivity": "internal", "redaction_status": "not_needed",
            "contains_executable_capability": bool(_governed_entry_stat(source).st_mode & 0o111),
            "advisory_zone": "clear_local", "escalation_confirmation_event_ref": None,
            "cleanup_obligation_ref": None, "supersedes_artifact_id": None,
            "media_type": mime or "text/plain",
            "relative_path": rel, "sha256": sha256_bytes(data), "size": len(data), "immutable": True,
        }
        if secret_classes and not attest_synthetic:
            continue
        preview = materialize_ledger_record("artifact", proposal, artifact_records)
        reference_errors = validate_record_references(preview, "artifact", index)
        if reference_errors:
            continue
        record = append_ledger_record(engagement, "artifact", proposal, lock_held=True)
        artifact_records.append(record)
        registered.append(rel)
    return registered, moved


def _evidence_relpaths(engagement: Path) -> set[str]:
    return _relative_regular_files(engagement, "evidence")


def _report_draft_relpaths(engagement: Path) -> set[str]:
    return {
        path
        for path in _relative_regular_files(engagement, "reports", suffix=".md")
        if not path.endswith(".manifest.json")
    }


def command_record_cleanup(args: argparse.Namespace) -> int:
    _require_local_provenance("broker", args.executor_id, args.session_id); engagement = args.engagement.absolute(); state = reduce_engagement(engagement); proposal = load_json(args.file)
    required = {"entity_id", "status", "cleanup_obligations"}
    if set(proposal) != required: raise RecordError("cleanup_proposal_fields_invalid", f"expected {sorted(required)}")
    action = _authority_action("record-cleanup", lane_id=args.lane_id, executor_id=args.executor_id, session_id=args.session_id, operator_id=args.operator_id, recorded_at=args.recorded_at, reason=args.reason, **proposal); _require_async_authority(args, action, args.recorded_at)
    previous = next((item["status"] for item in state["cleanup"]["obligations"] if item["obligation_id"] == proposal["entity_id"]), None)
    payload = {**proposal, "scope_hash": state["scope_hash"], "operator_id": args.operator_id, "updated_at": args.recorded_at, "authority_request_ref": args.authority_request_id, "executor_id": args.executor_id}
    event = base_event(event_id=f"event-cleanup-{args.authority_request_id}", engagement_id=state["engagement_id"], recorded_at=args.recorded_at, actor_role="broker", actor_id=args.executor_id, event_type="cleanup.updated", rationale=args.reason, payload=payload, state_changes=[{"dimension": "cleanup", "entity_id": proposal["entity_id"], "previous": previous, "current": proposal["status"]}], session_id=args.session_id, operation_class="authority"); applied = _append_kernel_event_idempotent(engagement, event); emit({"valid": True, "event_id": applied["event_id"]}); return 0


def command_record_operator_prior(args: argparse.Namespace) -> int:
    _require_local_provenance("broker", args.executor_id, args.session_id); engagement = args.engagement.absolute(); state = reduce_engagement(engagement)
    action = _authority_action("record-operator-prior", lane_id=args.lane_id, executor_id=args.executor_id, session_id=args.session_id, operator_id=args.operator_id, recorded_at=args.recorded_at, prior_id=args.prior_id, prior_statement=args.prior_statement, strength=args.strength, reason=args.reason); _require_async_authority(args, action, args.recorded_at)
    payload = {"prior_id": args.prior_id, "prior_statement": args.prior_statement, "strength": args.strength, "reason": args.reason, "operator_id": args.operator_id, "authority_request_ref": args.authority_request_id, "executor_id": args.executor_id}
    event = base_event(event_id=f"event-prior-{args.authority_request_id}", engagement_id=state["engagement_id"], recorded_at=args.recorded_at, actor_role="broker", actor_id=args.executor_id, event_type="operator_prior.recorded", rationale=args.reason, payload=payload, session_id=args.session_id, operation_class="authority"); applied = _append_kernel_event_idempotent(engagement, event); emit({"valid": True, "event_id": applied["event_id"]}); return 0


def command_reopen(args: argparse.Namespace) -> int:
    _require_local_provenance("broker", args.executor_id, args.session_id); engagement = args.engagement.absolute(); state = reduce_engagement(engagement); events = read_ledger(engagement, "event")
    current = {"engagement": None, "coverage": None}
    for event in events:
        for change in event.get("state_changes", []):
            if change["entity_id"] == state["engagement_id"] and change["dimension"] in current: current[change["dimension"]] = change["current"]
    if current["engagement"] not in {"blocked", "closed"} or current["coverage"] not in {"blocked", "coverage_dry"}: raise RecordError("engagement_reopen_not_applicable", str(current))
    action = _authority_action("reopen", lane_id=args.lane_id, executor_id=args.executor_id, session_id=args.session_id, operator_id=args.operator_id, recorded_at=args.recorded_at, reason=args.reason); _require_async_authority(args, action, args.recorded_at)
    payload = {"entity_id": state["engagement_id"], "status": "active", "operator_id": args.operator_id, "authority_request_ref": args.authority_request_id, "executor_id": args.executor_id}; changes = [{"dimension": dimension, "entity_id": state["engagement_id"], "previous": current[dimension], "current": "active"} for dimension in ("engagement", "coverage")]
    event = base_event(event_id=f"event-reopen-{args.authority_request_id}", engagement_id=state["engagement_id"], recorded_at=args.recorded_at, actor_role="broker", actor_id=args.executor_id, event_type="engagement.reopened", rationale=args.reason, payload=payload, state_changes=changes, session_id=args.session_id, operation_class="authority"); applied = _append_kernel_event_idempotent(engagement, event); emit({"valid": True, "event_id": applied["event_id"]}); return 0


def command_reopen_coverage(args: argparse.Namespace) -> int:
    capability = classify_command("reopen-coverage")
    require_actor(capability, "orchestrator")
    engagement = args.engagement.absolute()
    _require_decision6_kernel(engagement)
    _require_local_orchestrator_provenance(args.actor_id, args.session_id)
    if not args.reason.strip():
        raise RecordError("coverage_reopen_reason_required", "reason must be nonblank")

    state = reduce_engagement(engagement)
    event_identity = {
        "engagement_id": state["engagement_id"],
        "recorded_at": args.recorded_at,
        "actor_id": args.actor_id,
        "session_id": args.session_id,
        "reason": args.reason,
    }
    event_id = f"event-coverage-reopen-{sha256_bytes(canonical_json_bytes(event_identity))[-12:]}"
    existing = next((event for event in read_ledger(engagement, "event") if event["event_id"] == event_id), None)
    if existing is None:
        previous = state["coverage"]
        if previous not in {"coverage_dry", "budget_bounded"}:
            raise RecordError("coverage_reopen_not_applicable", str(previous))
    else:
        matching_changes = [
            change
            for change in existing.get("state_changes", [])
            if change.get("dimension") == "coverage" and change.get("entity_id") == state["engagement_id"]
        ]
        if len(matching_changes) != 1 or matching_changes[0].get("previous") not in {"coverage_dry", "budget_bounded"}:
            raise RecordError("event_id_collision", event_id)
        previous = matching_changes[0]["previous"]

    event = base_event(
        event_id=event_id,
        engagement_id=state["engagement_id"],
        recorded_at=args.recorded_at,
        actor_role="orchestrator",
        actor_id=args.actor_id,
        event_type="coverage.reopened",
        rationale=args.reason,
        payload={"entity_id": state["engagement_id"], "status": "active", "reason": args.reason},
        state_changes=[{"dimension": "coverage", "entity_id": state["engagement_id"], "previous": previous, "current": "active"}],
        session_id=args.session_id,
        operation_class=str(capability["tier"]),
    )
    applied = _append_kernel_event_idempotent(engagement, event)
    emit({"valid": True, "event_id": applied["event_id"], "coverage": reduce_engagement(engagement)["coverage"]})
    return 0


def _command_operator_queue_control(args: argparse.Namespace, *, command_name: str, status: str) -> int:
    engagement = args.engagement.absolute()
    _require_local_session(args.session_id)
    if not args.reason.strip():
        raise RecordError("operator_queue_reason_required", "reason must be nonblank")
    previous_status = "active" if status == "parked" else "parked"
    event_type = "operator_stop.recorded" if status == "parked" else "operator_resume.recorded"
    capability = classify_command(command_name)
    with engagement_lock(engagement) as bound_engagement:
        state = reduce_engagement(bound_engagement)
        action = {"command": command_name, "entity_id": state["engagement_id"], "previous_status": previous_status, "reason": args.reason, "recorded_at": args.recorded_at, "session_id": args.session_id, "status": status}
        if detect_secret_classes(canonical_json_bytes(action)):
            raise RecordError("secret_shaped_operator_queue_reason", "operator queue-control reason contains a forbidden secret shape")
        action_digest = sha256_bytes(canonical_json_bytes(action))
        event_id = f"event-{command_name}-{action_digest[-12:]}"
        event = base_event(
            event_id=event_id,
            engagement_id=state["engagement_id"],
            recorded_at=args.recorded_at,
            actor_role="operator",
            actor_id=args.operator_id,
            event_type=event_type,
            rationale=args.reason,
            payload={"entity_id": state["engagement_id"], "status": status, "reason": args.reason, "operator_id": args.operator_id},
            state_changes=[{"dimension": "queue", "entity_id": state["engagement_id"], "previous": previous_status, "current": status}],
            session_id=args.session_id,
            operation_class=str(capability["tier"]),
        )
        existing = next((item for item in read_ledger(bound_engagement, "event") if item["event_id"] == event_id), None)
        if existing is None:
            if state["queue_control"]["status"] != previous_status:
                raise RecordError("operator_queue_control_not_applicable", f"{command_name} requires queue status {previous_status}")
            _enforce_mutation(capability, bound_engagement, "operator", args.operator_id, f"{command_name}:{action_digest}")
        applied = _append_kernel_event_idempotent(bound_engagement, event, lock_held=True)
        queue_control = reduce_engagement(bound_engagement)["queue_control"]
    emit({"valid": True, "event_id": applied["event_id"], "queue_control": queue_control})
    return 0


def command_operator_stop(args: argparse.Namespace) -> int:
    return _command_operator_queue_control(args, command_name="operator-stop", status="parked")


def command_operator_resume(args: argparse.Namespace) -> int:
    return _command_operator_queue_control(args, command_name="operator-resume", status="active")


def _exact_ending_override_retry(
    args: argparse.Namespace,
    state: dict[str, Any],
    events: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Return the prior event only when this is an exact, unchanged retry.

    The override must still be the event-ledger tail, every CLI input must
    match, and the current all-attempt queue projection must reproduce the
    signed blocking identities.  A reopen, a later event, or changed queue
    context therefore cannot masquerade as an idempotent success.
    """

    if not events:
        return None
    event = events[-1]
    payload = event.get("payload", {})
    if (
        event.get("event_type") != "engagement.ending_overridden"
        or event.get("recorded_at") != args.recorded_at
        or event.get("actor") != {"role": "operator", "id": args.operator_id}
        or event.get("rationale") != args.reason
        or event.get("provenance", {}).get("session_id") != args.session_id
        or payload.get("entity_id") != state.get("engagement_id")
        or payload.get("terminal_kind") != args.terminal_kind
        or payload.get("status") != args.status
        or payload.get("reason") != args.reason
        or payload.get("operator_id") != args.operator_id
        or payload.get("scope_hash") != state.get("scope_hash")
    ):
        return None

    optional_inputs = {
        "coverage_review_ref": args.coverage_review_ref,
        "disposed_count": args.disposed_count,
        "enumerated_count": args.enumerated_count,
        "corpus_enumeration_ref": args.corpus_enumeration_ref,
    }
    if any(
        (name in payload) != (value is not None) or payload.get(name) != value
        for name, value in optional_inputs.items()
    ):
        return None

    target_coverage = (
        args.status
        if args.terminal_kind == "coverage" or args.status == "blocked"
        else state.get("coverage")
    )
    if not isinstance(target_coverage, str):
        return None
    projected = project_current_terminal_work_state(
        state,
        attempts,
        coverage=target_coverage,
    )
    blockers = blocking_work_identities(projected)
    current_attempt_context = attempt_ledger_context(attempts)
    if (
        not blockers
        or payload.get("blocking_items") != blockers
        or payload.get("blocking_queue_digest")
        != sha256_bytes(canonical_json_bytes(blockers))
        or payload.get("attempt_ledger_count")
        != current_attempt_context["attempt_ledger_count"]
        or payload.get("attempt_ledger_digest")
        != current_attempt_context["attempt_ledger_digest"]
    ):
        return None
    if args.terminal_kind == "coverage" and state.get("coverage") != args.status:
        return None
    if args.terminal_kind == "engagement" and not any(
        change.get("dimension") == "engagement"
        and change.get("entity_id") == state.get("engagement_id")
        and change.get("current") == args.status
        for change in event.get("state_changes", [])
    ):
        return None
    memory = state.get("memory_disposition")
    if args.terminal_kind == "engagement" and args.status == "closed" and (
        not isinstance(memory, dict)
        or payload.get("disposition_ref") != memory.get("disposition_ref")
        or payload.get("disposition_digest") != memory.get("disposition_digest")
    ):
        return None
    return event


def command_override_ending(args: argparse.Namespace) -> int:
    """Record one signed, exact exception to the otherwise binding work queue."""

    engagement = args.engagement.absolute()
    capability = classify_command("override-ending")
    _require_local_session(args.session_id)
    if not args.reason.strip():
        raise RecordError("ending_override_reason_required", "reason must be nonblank")
    with engagement_lock(engagement) as bound_engagement:
        admission = assert_completion_claims_clear_bound(bound_engagement) if args.terminal_kind == "engagement" and args.status == "closed" else None
        state = admission.state if admission is not None else reduce_engagement(bound_engagement)
        attempts = read_ledger(bound_engagement, "attempt")
        events = read_ledger(bound_engagement, "event")
        existing = _exact_ending_override_retry(args, state, events, attempts)
        if existing is not None:
            existing_projection = next(
                item
                for item in reversed(state["ending_overrides"])
                if item["event_ref"] == existing["event_id"]
            )
            emit({"valid": True, "event_id": existing["event_id"], "override": existing_projection})
            return 0

        attempts = read_ledger(bound_engagement, "attempt")
        events = read_ledger(bound_engagement, "event")
        previous_engagement = "active"
        for event in events:
            for change in event.get("state_changes", []):
                if change["dimension"] == "engagement" and change["entity_id"] == state["engagement_id"]:
                    previous_engagement = change["current"]

        if args.terminal_kind == "coverage":
            if args.status not in {"coverage_dry", "budget_bounded", "blocked"}:
                raise RecordError("ending_override_status_invalid", args.status)
            previous = state["coverage"]
            target_coverage = args.status
            dimension = "coverage"
        else:
            if args.status not in {"closed", "blocked"}:
                raise RecordError("ending_override_status_invalid", args.status)
            previous = previous_engagement
            target_coverage = "blocked" if args.status == "blocked" else state["coverage"]
            dimension = "engagement"

        projected = project_current_terminal_work_state(
            state,
            attempts,
            coverage=target_coverage,
        )
        blockers = blocking_work_identities(projected)
        if not blockers:
            raise RecordError("ending_override_not_required", "use the ordinary terminal command when no blocking work remains")
        blocker_digest = sha256_bytes(canonical_json_bytes(blockers))
        payload: dict[str, object] = {
            "entity_id": state["engagement_id"],
            "terminal_kind": args.terminal_kind,
            "status": args.status,
            "reason": args.reason,
            "operator_id": args.operator_id,
            "scope_hash": state["scope_hash"],
            "blocking_items": blockers,
            "blocking_queue_digest": blocker_digest,
            **attempt_ledger_context(attempts),
        }
        evidence_refs: list[str] = []
        entity_refs: list[str] = []
        if args.terminal_kind == "engagement" and args.status == "closed":
            memory = state.get("memory_disposition")
            if memory is None:
                raise RecordError("engagement_closure_memory_missing", state["engagement_id"])
            payload.update({
                "disposition_ref": memory["disposition_ref"],
                "disposition_digest": memory["disposition_digest"],
            })
            entity_refs.append(memory["disposition_ref"])
        elif args.terminal_kind == "coverage" and args.status in {"coverage_dry", "blocked"}:
            if not args.coverage_review_ref:
                raise RecordError("coverage_review_ref_required", args.status)
            payload["coverage_review_ref"] = args.coverage_review_ref
        elif args.terminal_kind == "coverage":
            if args.disposed_count is None or args.enumerated_count is None or not args.corpus_enumeration_ref:
                raise RecordError("budget_bounded_denominator_required", "counts and --corpus-enumeration-ref are required")
            artifacts = read_ledger(bound_engagement, "artifact")
            genesis_scope = events[0]
            scope_bytes = read_governed_file(
                bound_engagement
                / genesis_scope["payload"]["scope_snapshot_path"]
            )
            denominator = resolve_frozen_corpus_denominator(
                bound_engagement,
                artifacts,
                args.corpus_enumeration_ref,
                args.recorded_at,
                scope_bytes,
                genesis_scope["recorded_at"],
            )
            require_enumerated_count_matches(args.enumerated_count, denominator)
            payload.update({
                "disposed_count": args.disposed_count,
                "enumerated_count": args.enumerated_count,
                "corpus_enumeration_ref": args.corpus_enumeration_ref,
            })
            evidence_refs.extend([
                denominator["manifest_artifact_ref"],
                denominator["enumeration_artifact_ref"],
            ])

        state_changes = [{
            "dimension": dimension,
            "entity_id": state["engagement_id"],
            "previous": previous,
            "current": args.status,
        }]
        if args.terminal_kind == "engagement" and args.status == "blocked":
            state_changes.append({
                "dimension": "coverage",
                "entity_id": state["engagement_id"],
                "previous": state["coverage"],
                "current": "blocked",
            })
        actor = {"role": "operator", "id": args.operator_id}
        action = ending_override_action(
            engagement_id=state["engagement_id"],
            recorded_at=args.recorded_at,
            actor=actor,
            payload=payload,
            entity_refs=entity_refs,
            evidence_refs=evidence_refs,
            state_changes=state_changes,
            session_id=args.session_id,
        )
        if detect_secret_classes(canonical_json_bytes(action)):
            raise RecordError("secret_shaped_ending_override", "override reason contains a forbidden secret shape")
        action_digest = sha256_bytes(canonical_json_bytes(action))
        require_actor(capability, "operator")
        signature_proof = _require_operator_console(
            bound_engagement,
            args.operator_id,
            f"override-ending:{action_digest}",
            include_proof=True,
        )
        if not isinstance(signature_proof, dict):
            raise RecordError("operator_signature_invalid", action_digest)
        payload["operator_signature"] = signature_proof
        event = base_event(
            event_id=f"event-ending-override-{action_digest[-12:]}",
            engagement_id=state["engagement_id"],
            recorded_at=args.recorded_at,
            actor_role="operator",
            actor_id=args.operator_id,
            event_type="engagement.ending_overridden",
            rationale=args.reason,
            payload=payload,
            entity_refs=entity_refs,
            evidence_refs=evidence_refs,
            state_changes=state_changes,
            session_id=args.session_id,
            operation_class=str(capability["tier"]),
        )
        if admission is None:
            applied = _append_kernel_event_idempotent(bound_engagement, event, lock_held=True)
        else:
            assert_completion_claims_token_current_bound(bound_engagement, admission.token)
            applied = _append_kernel_event(
                bound_engagement,
                event,
                lock_held=True,
                completion_claims_token=admission.token,
            )
        snapshot = reduce_engagement(bound_engagement)
    emit({"valid": True, "event_id": applied["event_id"], "override": snapshot["ending_overrides"][-1]})
    return 0


def command_request_authority(args: argparse.Namespace) -> int:
    action = _command_json(args, "action_file")
    if not isinstance(action, dict) or action.get("action_kind") != args.action_kind or action.get("lane_id") != args.lane_id or detect_secret_classes(canonical_json_bytes(action)):
        raise RecordError("authority_action_invalid", args.request_id)
    _require_local_provenance(args.actor_role, args.actor_id, args.session_id)
    now = datetime.now(timezone.utc); requested = datetime.fromisoformat(args.recorded_at.replace("Z", "+00:00")); expires = datetime.fromisoformat(args.expires_at.replace("Z", "+00:00"))
    if abs((requested - now).total_seconds()) > 60 or expires <= now or (expires - now).total_seconds() > 86400: raise RecordError("authority_request_time_invalid", args.request_id)
    capability = classify_command("request-authority"); _enforce_mutation(capability, args.engagement, args.actor_role, args.actor_id, "request-authority")
    engagement = args.engagement.absolute(); action_bytes = canonical_json_bytes(action); digest = sha256_bytes(action_bytes); action_relative = f"authority/requests/{args.request_id}.action.json"
    with engagement_lock(engagement) as bound_engagement:
        state = reduce_engagement(bound_engagement)
        if action.get("action_kind") == "revise-finding" and action.get("action_version") != 3:
            raise RecordError("historical_finding_action_not_activatable", args.request_id)
        if action.get("action_kind") == "revise-finding" and action.get("action_version") == 3 and isinstance(action.get("target"), dict):
            locked_events = read_ledger(bound_engagement, "event")
            active_kernel = next(event["payload"]["record_kernel"] for event in reversed(locked_events) if event["event_type"] == "scope.attested")
            if active_kernel != "decision-0006-v2":
                raise RecordError("filing_contract_not_activated", args.request_id)
            signed_operator = next(
                event["payload"]["operator_id"]
                for event in reversed(locked_events)
                if event["event_type"] == "scope.attested"
            )
            if (
                action.get("executor_id") != args.actor_id
                or action.get("session_id") != args.session_id
                or action.get("operator_id") != signed_operator
            ):
                raise RecordError("revise_finding_v2_principal_binding_invalid", args.request_id)
            committed_entity_ids = {
                event.get("payload", {}).get("record_id")
                for event in locked_events
                if event.get("event_type") == "record.committed"
                and isinstance(event.get("payload", {}).get("record_id"), str)
            }
            _validate_revise_finding_v2_action(
                action,
                state=state,
                engagement=bound_engagement,
                index=build_reference_index(bound_engagement),
                committed_entity_ids=committed_entity_ids,
                seen_events={event["event_id"]: event for event in locked_events},
                attempts=read_ledger(bound_engagement, "attempt"),
                artifacts=read_ledger(bound_engagement, "artifact"),
                requested_at=args.recorded_at,
                context=f"event-authority-request-{args.request_id}",
            )
            target = action["target"]
            generation = (target.get("id"), target.get("expected_revision"), target.get("adjudication_event_ref"), target.get("adjudication_review_ref"))
            duplicate = next((request for request in state["authority_requests"].values() if request.get("status") in {"pending_authority", "approved"} and isinstance(request.get("target"), dict) and (request.get("lane_id") == args.lane_id or (request["target"].get("id"), request["target"].get("expected_revision"), request["target"].get("adjudication_event_ref"), request["target"].get("adjudication_review_ref")) == generation)), None)
            if duplicate is not None:
                raise RecordError("duplicate_active_finding_revision_request", duplicate["request_id"])
        action_path = bound_engagement / action_relative
        prior_action = _governed_regular_bytes_or_none(action_path)
        if prior_action is not None and prior_action != action_bytes: raise RecordError("authority_action_id_collision", args.request_id)
        if prior_action is None: atomic_write(action_path, action_bytes)
        event = base_event(event_id=f"event-authority-request-{args.request_id}", engagement_id=state["engagement_id"], recorded_at=args.recorded_at, actor_role=args.actor_role, actor_id=args.actor_id, event_type="authority.requested", rationale=args.reason, payload={"request_id": args.request_id,"action_kind": args.action_kind, "action_digest": digest, "action_path": action_relative, "lane_id": args.lane_id, "request_status": "pending_authority", "scope_hash": state["scope_hash"], "environment_ref": state["active_environment_ref"], "expires_at": args.expires_at}, session_id=args.session_id, operation_class="notebook")
        record = _append_kernel_event_idempotent(bound_engagement, event, lock_held=True)
    emit({"ok": True, "request_id": args.request_id, "request_event_ref": record["event_id"], "action_digest": digest, "status": "pending_authority"})
    return 0


def command_resolve_authority(args: argparse.Namespace) -> int:
    capability = classify_command("resolve-authority"); _require_local_session(args.session_id)
    pending_state = reduce_engagement(args.engagement.absolute()); pending_request = pending_state["authority_requests"].get(args.request_id); action_path = args.engagement.absolute() / str((pending_request or {}).get("action_path", ""))
    try: action_bytes=read_governed_file(action_path)
    except (OSError,RecordError): action_bytes=b""
    if pending_request is None or sha256_bytes(action_bytes) != pending_request["action_digest"]: raise RecordError("authority_action_record_invalid", args.request_id)
    try: action_text=action_bytes.decode("utf-8")
    except UnicodeDecodeError: raise RecordError("authority_action_record_invalid",args.request_id)
    sys.stderr.write("Exact proposed action for operator review:\n" + action_text); sys.stderr.flush()
    _enforce_mutation(capability, args.engagement, "operator", args.operator_id, f"resolve-authority:{args.request_id}:{pending_request['action_digest']}:{args.resolution}:{args.recorded_at}")
    now = datetime.now(timezone.utc); recorded = datetime.fromisoformat(args.recorded_at.replace("Z", "+00:00"))
    if abs((recorded - now).total_seconds()) > 60: raise RecordError("authority_resolution_time_not_current", args.request_id)
    state = reduce_engagement(args.engagement.absolute()); request = state["authority_requests"].get(args.request_id)
    if request is None or request["status"] != "pending_authority":
        raise RecordError("authority_request_not_pending", args.request_id)
    event = base_event(event_id=f"event-authority-resolution-{args.request_id}-{args.resolution}", engagement_id=state["engagement_id"], recorded_at=args.recorded_at, actor_role="operator", actor_id=args.operator_id, event_type="authority.resolved", rationale=args.reason, payload={"request_id": args.request_id, "request_event_ref": request["request_event_ref"], "action_digest": request["action_digest"], "resolution": args.resolution, "resolved_at": args.recorded_at}, entity_refs=[request["request_event_ref"]], session_id=args.session_id, operation_class="authority")
    record = _append_kernel_event(args.engagement.absolute(), event)
    emit({"ok": True, "request_id": args.request_id, "resolution": args.resolution, "resolution_event_ref": record["event_id"]})
    return 0


def command_settle_approved_revision(args: argparse.Namespace) -> int:
    """Atomically apply a live approved revision or record its objective expiry."""

    capability = classify_command("settle-approved-revision")
    require_actor(capability, "broker")
    _require_decision6_kernel(args.engagement)
    _require_local_provenance("broker", args.executor_id, args.session_id)
    try:
        recorded = datetime.fromisoformat(args.recorded_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RecordError("authority_settlement_time_invalid", args.authority_request_id) from exc
    engagement = args.engagement.absolute()
    with engagement_lock(engagement) as bound_engagement:
        now = datetime.now(timezone.utc)
        if recorded.tzinfo is None or abs((recorded - now).total_seconds()) > 60:
            raise RecordError("authority_settlement_time_not_current", args.authority_request_id)
        supplied_finding = _command_json(args, "file")
        supplied_errors = validate_record(supplied_finding, "finding-v3")
        if supplied_errors:
            raise RecordError(
                "finding_revision_invalid",
                str(supplied_finding.get("finding_id", "unknown")),
                supplied_errors,
            )
        supplied_relative = (
            f"findings/{supplied_finding['finding_id']}/"
            f"rev-{supplied_finding['revision']}.json"
        )
        state = reduce_engagement(
            bound_engagement, allowed_record_orphans={supplied_relative}
        )
        request = state["authority_requests"].get(args.authority_request_id)
        application = request.get("application") if isinstance(request, dict) else None
        if (
            request is None
            or request.get("action_kind") != "revise-finding"
            or not isinstance(request.get("target"), dict)
            or not isinstance(application, dict)
            or request.get("lane_id") != args.lane_id
            or application.get("operator_id") != args.operator_id
        ):
            raise RecordError("approved_revision_settlement_invalid", args.authority_request_id)
        expiry_event_id = f"event-authority-expired-{args.authority_request_id}"
        if request.get("status") == "expired":
            existing = next((event for event in read_ledger(bound_engagement, "event") if event["event_id"] == expiry_event_id), None)
            if (
                not isinstance(existing, dict)
                or request.get("resolution_event_ref") != expiry_event_id
                or existing.get("recorded_at") != args.recorded_at
                or existing.get("actor") != {"role": "broker", "id": args.executor_id}
                or existing.get("provenance", {}).get("session_id") != args.session_id
                or existing.get("payload", {}).get("request_id") != args.authority_request_id
            ):
                raise RecordError("approved_revision_settlement_replay_invalid", args.authority_request_id)
            result: dict[str, object] = {"ok": True, "request_id": args.authority_request_id, "status": "expired", "event_ref": existing["event_id"], "replayed": True}
        elif request.get("status") != "approved":
            raise RecordError("approved_revision_settlement_invalid", args.authority_request_id)
        else:
            expires_at = datetime.fromisoformat(request["expires_at"].replace("Z", "+00:00")) if request.get("expires_at") is not None else None
            if expires_at is not None and now > expires_at:
                if recorded <= expires_at:
                    raise RecordError("authority_settlement_time_invalid", args.authority_request_id)
                event = base_event(
                    event_id=expiry_event_id,
                    engagement_id=state["engagement_id"],
                    recorded_at=args.recorded_at,
                    actor_role="broker",
                    actor_id=args.executor_id,
                    event_type="authority.expired",
                    rationale="Approved authority passed its recorded expiry before application.",
                    payload={
                        "request_id": args.authority_request_id,
                        "request_event_ref": request["request_event_ref"],
                        "action_digest": request["action_digest"],
                        "expires_at": request["expires_at"],
                        "status": "expired",
                    },
                    entity_refs=[request["request_event_ref"]],
                    session_id=args.session_id,
                    operation_class="notebook",
                )
                record = _append_kernel_event_idempotent(bound_engagement, event, lock_held=True)
                result = {"ok": True, "request_id": args.authority_request_id, "status": "expired", "event_ref": record["event_id"], "replayed": False}
            else:
                if expires_at is not None and recorded > expires_at:
                    raise RecordError("authority_settlement_time_invalid", args.authority_request_id)
                result = _apply_finding_revision(argparse.Namespace(**{**vars(args), "engagement": bound_engagement}), lock_held=True, evaluated_at=now)
                result = {**result, "request_id": args.authority_request_id, "status": "applied"}
    emit(result)
    return 0


def command_confirm_zone2(args: argparse.Namespace) -> int:
    proposal = load_json(args.file); plan = load_json(args.plan)
    capability = classify_command("confirm-zone2"); state = reduce_engagement(args.engagement.absolute())
    plan_keys = {"artifact_id", "metadata_digest", "planned_sha256", "planned_size", "relative_path", "scope_hash", "environment_ref", "cleanup_obligation_ref", "cleanup_obligation_id"}; action_digest = sha256_bytes(canonical_json_bytes(plan)) if set(plan) == plan_keys else None
    event_time = datetime.fromisoformat(proposal.get("recorded_at", "").replace("Z", "+00:00")); expiry = datetime.fromisoformat(proposal.get("payload", {}).get("expires_at", "").replace("Z", "+00:00")); now = datetime.now(timezone.utc)
    _require_local_session(str(proposal.get("provenance", {}).get("session_id", ""))); require_scope_zone2_authorized(args.engagement.absolute(), state["scope_hash"])
    if proposal.get("event_type") != "escalation.confirmed" or proposal.get("operation_class") != "real_world" or proposal.get("actor") != {"role": "operator", "id": args.operator_id} or not proposal.get("provenance", {}).get("session_id") or action_digest is None or proposal.get("payload", {}).get("action_digest") != action_digest or proposal.get("payload", {}).get("entity_id") != plan.get("artifact_id") or plan.get("scope_hash") != state["scope_hash"] or plan.get("environment_ref") != state["active_environment_ref"] or plan.get("cleanup_obligation_ref") != proposal.get("payload", {}).get("cleanup_obligation_ref") or plan.get("cleanup_obligation_id") != proposal.get("payload", {}).get("cleanup_obligation_id") or abs((event_time - now).total_seconds()) > 60 or not event_time < expiry or (expiry - event_time).total_seconds() > 1800:
        raise RecordError("zone2_confirmation_invalid", proposal.get("event_id", "unknown"))
    print(json.dumps({"zone2_confirmation_review": {"action_digest": action_digest, "plan": plan, "expires_at": proposal["payload"]["expires_at"], "operator_id": args.operator_id}}, sort_keys=True, separators=(",", ":")), file=sys.stderr, flush=True)
    _enforce_mutation(capability, args.engagement, "operator", args.operator_id, f"confirm-zone2:{action_digest}:{proposal['event_id']}:{proposal['recorded_at']}:{proposal['payload']['expires_at']}")
    record = _append_kernel_event_idempotent(args.engagement.absolute(), proposal)
    emit({"ok": True, "event_id": record["event_id"], "record_hash": record["record_hash"], "creates_artifact_bytes": False})
    return 0


def command_create_artifact(args: argparse.Namespace) -> int:
    _require_decision6_kernel(args.engagement)
    metadata = load_json(args.metadata); permit = load_json(args.classification); capability = classify_command("create-artifact")
    metadata_secret_classes=detect_secret_classes(canonical_json_bytes(metadata))
    if metadata_secret_classes: raise RecordError("secret_shaped_artifact_metadata","artifact metadata blocked before creation",[{"class":value} for value in metadata_secret_classes])
    _require_local_provenance("broker", args.actor_id, args.session_id); require_actor(capability, "broker")
    classification_body = {key: value for key, value in permit.items() if key != "classification_event_ref"}; classification_digest = sha256_bytes(canonical_json_bytes(classification_body))
    relative = Path(permit.get("relative_path", "")); engagement = args.engagement.absolute(); evidence = engagement / "evidence"; destination = engagement / relative
    if relative.is_absolute() or ".." in relative.parts or not relative.as_posix().startswith("evidence/") or evidence.is_symlink() or destination.is_symlink() or not destination.parent.is_dir() or any((engagement / Path(*relative.parts[:index])).is_symlink() for index in range(1, len(relative.parts))): raise RecordError("artifact_path_not_contained", relative.as_posix())
    data = sys.stdin.buffer.read(permit.get("source_size", -1) + 1)
    if len(data) != permit.get("source_size") or sha256_bytes(data) != permit.get("source_digest") or detect_secret_classes(data): raise RecordError("zone2_planned_bytes_mismatch", metadata.get("artifact_id", "unknown"))
    plan = _zone2_plan(metadata, planned_sha256=permit.get("source_digest", ""), planned_size=permit.get("source_size", -1), relative_path=relative.as_posix(), scope_hash=permit.get("scope_hash", ""), environment_ref=permit.get("environment_ref", ""), cleanup_obligation_ref=metadata.get("cleanup_obligation_ref") or ""); action_digest = sha256_bytes(canonical_json_bytes(plan))
    journal_path = engagement/"legacy"/"zone2-pending"/f"{metadata.get('artifact_id','unknown')}.json"; journal = {"schema_version":1,"artifact_id":metadata.get("artifact_id"),"action_digest":action_digest,"classification_digest":classification_digest,"relative_path":relative.as_posix(),"source_digest":permit.get("source_digest"),"source_size":permit.get("source_size"),"confirmation_event_ref":metadata.get("escalation_confirmation_event_ref")}; journal_bytes=canonical_json_bytes(journal)
    try: existing_journal = read_governed_file(journal_path)
    except FileNotFoundError: existing_journal = None
    if existing_journal is not None and existing_journal != journal_bytes: raise RecordError("zone2_resume_journal_mismatch", metadata.get("artifact_id", "unknown"))
    def exact_existing_record(root: Path = engagement) -> dict[str, object] | None:
        candidate=next((item for item in read_ledger(root,"artifact") if item["artifact_id"]==metadata.get("artifact_id")),None)
        return candidate if candidate is not None and candidate.get("relative_path")==relative.as_posix() and candidate.get("sha256")==permit.get("source_digest") and candidate.get("size")==permit.get("source_size") and candidate.get("precreation_classification_digest")==classification_digest and candidate.get("escalation_confirmation_event_ref")==metadata.get("escalation_confirmation_event_ref") else None
    resuming = destination.exists() and existing_journal is not None
    if destination.exists() and existing_journal is None:
        with engagement_lock(engagement) as bound_engagement:
            completed=exact_existing_record(bound_engagement)
            if completed is not None and read_governed_file(bound_engagement / relative)==data: emit({"ok":True,"artifact_id":completed["artifact_id"],"record_hash":completed["record_hash"],"created_after_confirmation":True,"resumed":True}); return 0
        raise RecordError("artifact_bytes_precede_creation_command", relative.as_posix())
    if destination.exists() and read_governed_file(destination) != data: raise RecordError("artifact_bytes_precede_creation_command", relative.as_posix())
    state = reduce_engagement(engagement, allowed_artifact_orphans={relative.as_posix()} if resuming else None); events = read_ledger(engagement, "event")
    event = next((item for item in events if item["event_id"] == permit.get("classification_event_ref")), None); confirmation = next((item for item in events if item["event_id"] == metadata.get("escalation_confirmation_event_ref")), None)
    expiry = datetime.fromisoformat((permit.get("expires_at") or "").replace("Z", "+00:00")) if permit.get("expires_at") else None
    try: artifact_time=datetime.fromisoformat(str(metadata.get("created_at","")).replace("Z","+00:00")); classification_time=datetime.fromisoformat(str(permit.get("classified_at","")).replace("Z","+00:00")); confirmation_time=datetime.fromisoformat(str(confirmation.get("recorded_at","") if confirmation else "").replace("Z","+00:00"))
    except ValueError: artifact_time=classification_time=confirmation_time=None
    chronology_valid=artifact_time is not None and classification_time is not None and confirmation_time is not None and confirmation_time<=artifact_time<=expiry and classification_time<=artifact_time if expiry is not None else False
    contract_valid = set(permit) == ARTIFACT_PERMIT_FIELDS and metadata.get("operation_class") == "real_world" and metadata.get("advisory_zone") == "review_required" and permit.get("advisory_zone") == "review_required" and permit.get("operation_class") == "real_world" and permit.get("decision") == "allow_confirmed_creation" and permit.get("artifact_id") == metadata.get("artifact_id") and permit.get("metadata_digest") == sha256_bytes(canonical_json_bytes(metadata)) and permit.get("scope_hash") == state["scope_hash"] and permit.get("environment_ref") == state["active_environment_ref"] and permit.get("action_digest") == action_digest
    event_valid = event is not None and event["event_type"] == "artifact.classified" and event["payload"].get("classification_digest") == classification_digest and event["payload"].get("action_digest") == action_digest and event["payload"].get("source_digest") == permit.get("source_digest") and event["payload"].get("source_size") == permit.get("source_size")
    confirmation_valid = confirmation is not None and confirmation["event_type"] == "escalation.confirmed" and confirmation["payload"].get("action_digest") == action_digest and confirmation["payload"].get("cleanup_obligation_ref") == metadata.get("cleanup_obligation_ref") and confirmation["payload"].get("cleanup_obligation_id") == metadata.get("cleanup_obligation_id")
    if not contract_valid or not event_valid or not confirmation_valid or expiry is None or not chronology_valid: raise RecordError("zone2_creation_authority_invalid", metadata.get("artifact_id", "unknown"))
    metadata["precreation_classification_digest"] = classification_digest; metadata["precreation_classification_event_ref"] = event["event_id"]; metadata["classified_source_digest"] = permit["source_digest"]; metadata["classified_source_size"] = permit["source_size"]; metadata["classified_at"] = permit["classified_at"]
    preview = {**metadata, "relative_path": relative.as_posix(), "sha256": permit["source_digest"], "size": permit["source_size"], "immutable": True}
    preview = materialize_ledger_record("artifact", {key: value for key, value in preview.items() if key not in {"sequence", "previous_hash", "record_hash"}}, read_ledger(engagement, "artifact"))
    reference_errors = validate_record_with_references(preview, "artifact", engagement)
    if reference_errors:
        raise RecordError("record_reference_invalid", "Zone-2 artifact metadata invalid before creation", reference_errors)
    with engagement_lock(engagement) as bound_engagement:
        bound_destination = bound_engagement / relative
        bound_journal_path = bound_engagement / "legacy" / "zone2-pending" / f"{metadata.get('artifact_id','unknown')}.json"
        final_state = reduce_engagement(bound_engagement, allowed_artifact_orphans={relative.as_posix()} if resuming else None)
        cleanup_id = confirmation["payload"].get("cleanup_obligation_id"); cleanup_open = any(item.get("obligation_id") == cleanup_id and item.get("status") == "open" for item in final_state["cleanup"]["obligations"])
        if (not resuming and (final_state["scope_hash"] != permit["scope_hash"] or final_state["active_environment_ref"] != permit["environment_ref"] or datetime.now(timezone.utc) > expiry)) or not cleanup_open:
            raise RecordError("zone2_creation_authority_expired", metadata.get("artifact_id", "unknown"))
        current_journal = _governed_regular_bytes_or_none(bound_journal_path)
        if current_journal is not None and current_journal != journal_bytes:
            raise RecordError("zone2_resume_journal_mismatch", metadata.get("artifact_id", "unknown"))
        if current_journal is None: atomic_write(bound_journal_path,journal_bytes)
        current_destination = _governed_regular_bytes_or_none(bound_destination)
        if current_destination is None:
            governed_root, governed_parts = _governed_root(bound_destination)
            if governed_root != bound_engagement or tuple(governed_parts) != tuple(relative.parts): raise RecordError("artifact_path_not_contained", relative.as_posix())
            parent_fd, destination_name = _open_parent_fd(governed_root, governed_parts, create=False)
            try:
                if datetime.now(timezone.utc) > expiry: raise RecordError("zone2_creation_authority_expired", metadata.get("artifact_id", "unknown"))
                fd = os.open(destination_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=parent_fd)
                try:
                    view = memoryview(data); written = 0
                    while written < len(view):
                        count = os.write(fd, view[written:])
                        if count <= 0: raise OSError("artifact write made no progress")
                        written += count
                    os.fsync(fd)
                finally: os.close(fd)
            finally: os.close(parent_fd)
        elif current_destination != data: raise RecordError("zone2_resume_bytes_mismatch", metadata["artifact_id"])
    existing_record = next((item for item in read_ledger(engagement,"artifact") if item["artifact_id"] == metadata["artifact_id"]),None)
    if existing_record is not None:
        exact_record=exact_existing_record()
        if exact_record is None or read_governed_file(destination)!=data: raise RecordError("zone2_resume_record_mismatch", metadata["artifact_id"])
        with engagement_lock(engagement) as bound_engagement:
            bound_journal_path = bound_engagement/"legacy"/"zone2-pending"/f"{metadata.get('artifact_id','unknown')}.json"
            if read_governed_file(bound_journal_path) != journal_bytes: raise RecordError("zone2_resume_journal_mismatch", metadata.get("artifact_id", "unknown"))
            _unlink_governed_file(bound_journal_path)
        emit({"ok":True,"artifact_id":exact_record["artifact_id"],"record_hash":exact_record["record_hash"],"created_after_confirmation":True,"resumed":True}); return 0
    try: record = register_artifact(engagement, destination, metadata, classification=permit)
    except RecordError:
        completed=exact_existing_record()
        if completed is None or read_governed_file(destination)!=data: raise
        record=completed
    with engagement_lock(engagement) as bound_engagement:
        bound_journal_path = bound_engagement/"legacy"/"zone2-pending"/f"{metadata.get('artifact_id','unknown')}.json"
        if read_governed_file(bound_journal_path) != journal_bytes: raise RecordError("zone2_resume_journal_mismatch", metadata.get("artifact_id", "unknown"))
        _unlink_governed_file(bound_journal_path)
    emit({"ok": True, "artifact_id": record["artifact_id"], "record_hash": record["record_hash"], "created_after_confirmation": True})
    return 0


def command_register_artifact(args: argparse.Namespace) -> int:
    metadata = load_json(args.metadata)
    permit = load_json(args.classification)
    variant = metadata.get("advisory_zone")
    derived_variant = artifact_variant(metadata)
    if variant not in ({"clear_local"} if derived_variant == "clear_local" else {"review_required", "unknown"}):
        raise RecordError("artifact_zone_underclassified", metadata.get("artifact_id", "unknown"))
    capability = classify_command("register-artifact", variant=variant)
    if capability["tier"] == "real_world":
        raise RecordError("canonical_zone2_creation_command_required", metadata.get("artifact_id", "unknown"))
    actor = metadata.get("producer", {})
    _require_local_provenance(str(actor.get("role", "")), str(actor.get("id", "")), str(metadata.get("producer_session_id", "")))
    require_actor(capability, actor.get("role", ""))
    if capability["tier"] == "notebook":
        _enforce_mutation(capability, args.engagement, actor.get("role", ""), actor.get("id", ""), "register-artifact")
    expected = ARTIFACT_PERMIT_FIELDS
    actual_file = args.file.absolute()
    try: actual_relative = actual_file.relative_to(args.engagement.absolute()).as_posix(); actual_bytes = read_governed_file(actual_file)
    except (ValueError, OSError, RecordError): raise RecordError("artifact_path_not_contained", metadata.get("artifact_id", "unknown"))
    expected_decision = "allow_local_creation" if capability["tier"] == "notebook" else "allow_confirmed_creation"
    state = reduce_engagement(args.engagement.absolute(), allowed_artifact_orphans={actual_relative}); classification_body = {key: value for key, value in permit.items() if key != "classification_event_ref"}; classification_digest = sha256_bytes(canonical_json_bytes(classification_body)); classification_event = next((event for event in read_ledger(args.engagement.absolute(), "event") if event["event_id"] == permit.get("classification_event_ref")), None)
    event_valid = classification_event is not None and classification_event["event_type"] == "artifact.classified" and classification_event["payload"].get("classification_digest") == classification_digest and classification_event["payload"].get("artifact_id") == metadata.get("artifact_id")
    bytes_valid = sha256_bytes(actual_bytes) == permit.get("source_digest") and len(actual_bytes) == permit.get("source_size")
    scope_valid = permit.get("scope_hash") == state["scope_hash"] and permit.get("environment_ref") == state["active_environment_ref"]
    timing_valid = permit.get("expires_at") is None
    if set(permit) != expected or permit.get("decision") != expected_decision or permit.get("file_absent_at_classification") is not True or permit.get("metadata_digest") != sha256_bytes(canonical_json_bytes(metadata)) or permit.get("artifact_id") != metadata.get("artifact_id") or permit.get("relative_path") != actual_relative or permit.get("advisory_zone") != metadata.get("advisory_zone") or permit.get("operation_class") != capability["tier"] or permit.get("engagement_id") != metadata.get("engagement_id") or not event_valid or not bytes_valid or not scope_valid or not timing_valid:
        raise RecordError("artifact_classification_mismatch", metadata.get("artifact_id", "unknown"))
    if not metadata.get("producer_session_id") or metadata.get("operation_class") != capability["tier"]:
        raise RecordError("artifact_provenance_invalid", metadata.get("artifact_id", "unknown"))
    metadata["precreation_classification_digest"] = classification_digest
    metadata["precreation_classification_event_ref"] = permit["classification_event_ref"]
    metadata["classified_source_digest"] = permit["source_digest"]
    metadata["classified_source_size"] = permit["source_size"]
    metadata["classified_at"] = permit["classified_at"]
    record = register_artifact(args.engagement.absolute(), args.file, metadata, classification=permit)
    emit({"ok": True, "artifact_id": record["artifact_id"], "sequence": record["sequence"], "record_hash": record["record_hash"], "sha256": record["sha256"]})
    return 0


def command_append_attempt(args: argparse.Namespace) -> int:
    proposal = _command_json(args, "file")
    capability = classify_command("append-attempt")
    actor = proposal.get("provenance", {}).get("actor", {})
    _enforce_mutation(capability, args.engagement, actor.get("role", ""), actor.get("id", ""), f"append-attempt:{proposal.get('attempt_id','unknown')}:{sha256_bytes(canonical_json_bytes(proposal))}")
    if proposal.get("operation_class") != "notebook" or proposal.get("actor") != actor:
        raise RecordError("attempt_provenance_invalid", proposal.get("attempt_id", "unknown"))
    session_id = _require_session(proposal.get("provenance", {}), "append-attempt"); _require_local_provenance(str(actor.get("role", "")), str(actor.get("id", "")), session_id)
    record = append_attempt(args.engagement.absolute(), proposal)
    emit({"ok": True, "attempt_id": record["attempt_id"], "sequence": record["sequence"], "record_hash": record["record_hash"]})
    return 0


def command_repair_tail(args: argparse.Namespace) -> int:
    _require_decision6_kernel(args.engagement)
    _require_local_provenance("broker", args.executor_id, args.session_id); action = _authority_action("repair-ledger-tail", lane_id=args.lane_id, executor_id=args.executor_id, session_id=args.session_id, ledger=args.ledger, operator_id=args.operator_id, reason=args.reason, recorded_at=args.recorded_at); action_digest = sha256_bytes(canonical_json_bytes(action)); require_repair_authority_from_intact_prefix(args.engagement, args.authority_request_id, "repair-ledger-tail", action_digest, args.lane_id, args.recorded_at)
    result = repair_ledger_tail(args.engagement.absolute(), args.ledger, args.operator_id, args.reason, args.recorded_at, args.authority_request_id, args.executor_id, args.session_id)
    emit({"ok": True, **result})
    return 0


def command_queue_inspection(args: argparse.Namespace) -> int:
    """Reduce once under the kernel's read lock and emit only that bound state."""

    try:
        state = reduce_engagement(args.engagement.absolute())
    except OSError as exc:
        raise RecordError("queue_record_unavailable", "queue record source is unavailable") from exc
    payload = queue_command_payload(args.command, state, args.engagement.absolute())
    emit(payload)
    return queue_gate_exit(payload) if args.command == "gate" else 0


def command_reduce(args: argparse.Namespace) -> int:
    engagement = args.engagement.absolute()
    with engagement_lock(engagement) as bound_engagement:
        admission = assert_completion_claims_clear_bound(bound_engagement)
        snapshot = admission.state
        # Validate once at the final boundary. Both projection writes then share this held
        # cooperative lock; validating again after the snapshot write would reject our own
        # intentional tree mutation before the generated views could be published.
        assert_completion_claims_token_current_bound(bound_engagement, admission.token)
        write_snapshot(bound_engagement, snapshot)
        write_views(bound_engagement, snapshot)
    emit({"ok": True, "event_count": snapshot["event_count"], "ledger_hash": snapshot["ledger_hash"]})
    return 0


def command_ledger_health(args: argparse.Namespace) -> int:
    emit(probe_ledger_health(args.engagement))
    return 0


def _validate_quarantine_action(args: argparse.Namespace, command: str) -> dict[str, object]:
    reason = args.reason.strip()
    if reason not in QUARANTINE_REASONS:
        raise RecordError("quarantine_reason_invalid", "reason must be a supported non-sensitive code")
    action = {"command": command, "reason": reason, "recorded_at": args.recorded_at, "operator_id": args.operator_id}
    try:
        timestamp = datetime.fromisoformat(args.recorded_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RecordError("quarantine_recorded_at_invalid", "recorded-at must be an ISO-8601 timestamp") from exc
    if timestamp.tzinfo is None:
        raise RecordError("quarantine_recorded_at_invalid", "recorded-at must include a timezone")
    if detect_secret_classes(canonical_json_bytes(action)):
        raise RecordError("secret_shaped_quarantine_reason", "quarantine reason contains a forbidden secret shape")
    return action


def command_quarantine_ledger(args: argparse.Namespace) -> int:
    """Create the denial-only marker using the last ledger-bound operator trust root."""

    engagement_path = args.engagement.absolute()
    action = _validate_quarantine_action(args, "quarantine-ledger")
    with quarantine_control_lock(engagement_path) as engagement:
        authority = quarantine_authority_context(engagement)
        if args.operator_id != authority["operator_id"]:
            raise RecordError("operator_authority_invalid", "operator id does not match the trusted scope attestation")
        action_digest = sha256_bytes(canonical_json_bytes({**action, "record_fingerprint": authority["record_fingerprint"]}))
        challenge_digest = _require_bound_operator_signature(
            engagement=engagement,
            operator_id=args.operator_id,
            operation=f"quarantine-ledger:{action_digest}",
            scope_hash=authority["scope_hash"],
            scope_bytes=authority["scope_bytes"],
            ledger_hash=authority["record_fingerprint"],
            signer_pin=authority["signer_pin"],
            engagement_id=authority["engagement_id"],
        )
        marker = {
            "schema_version": 1,
            "status": "quarantined",
            "operator_id": args.operator_id,
            "reason": action["reason"],
            "recorded_at": args.recorded_at,
            "authority_challenge_digest": challenge_digest,
            "record_fingerprint": authority["record_fingerprint"],
        }
        try:
            created, marker_state = create_marker_exclusive(engagement, marker)
        except (FileExistsError, OSError, ValueError) as exc:
            raise RecordError("quarantine_marker_conflict", "quarantine marker could not be created without overwrite") from exc
    emit({"ok": True, "status": "quarantined", "created": created, "marker_status": marker_state["marker_status"]})
    return 0


def command_clear_ledger_quarantine(args: argparse.Namespace) -> int:
    """Signed operator clear, allowed only after a full underlying reduction succeeds."""

    engagement_path = args.engagement.absolute()
    action = _validate_quarantine_action(args, "clear-ledger-quarantine")
    with quarantine_control_lock(engagement_path) as engagement:
        marker_state = inspect_quarantine(engagement)
        if not marker_state["quarantined"]:
            raise RecordError("quarantine_marker_missing", "engagement has no quarantine marker")
        # Private bypass: this proves the underlying ledgers and all committed records are healthy;
        # it performs no snapshot/view writes and is not exposed as a reducer option.
        try:
            snapshot = _reduce_engagement_unchecked(engagement)
        except (OSError, RecordError) as exc:
            raise RecordError(
                "quarantine_underlying_ledger_unhealthy",
                "underlying engagement evidence is not healthy enough to clear quarantine",
            ) from exc
        operation = sha256_bytes(canonical_json_bytes({
            **action,
            "marker_fingerprint": marker_state.get("fingerprint") or "malformed-nonregular",
            "ledger_hash": snapshot["ledger_hash"],
            "record_state_fingerprint": sha256_bytes(canonical_json_bytes(snapshot)),
        }))
        _require_operator_console(engagement, args.operator_id, f"clear-ledger-quarantine:{operation}")
        try:
            current_snapshot = _reduce_engagement_unchecked(engagement)
        except (OSError, RecordError) as exc:
            raise RecordError(
                "quarantine_underlying_ledger_unhealthy",
                "underlying engagement evidence changed or became unhealthy during clear",
            ) from exc
        if canonical_json_bytes(current_snapshot) != canonical_json_bytes(snapshot):
            raise RecordError(
                "quarantine_underlying_ledger_changed",
                "underlying engagement evidence changed during signed clear",
            )
        try:
            clear_marker_exact(engagement, marker_state)
        except (OSError, ValueError) as exc:
            raise RecordError("quarantine_marker_changed", "quarantine marker is not the exact clearable entry") from exc
    emit({"ok": True, "status": "healthy", "cleared": True})
    return 0


def command_render(args: argparse.Namespace) -> int:
    engagement = args.engagement.absolute()
    with engagement_lock(engagement) as bound_engagement:
        # The returned snapshot is lock-coordinated with the publication token we render.
        admission = assert_completion_claims_clear_bound(bound_engagement)
        write_views(bound_engagement, admission.state, completion_claims_token=admission.token)
    emit({"ok": True, "views": sorted(render_views(admission.state))})
    return 0


def command_check_completion_claims(args: argparse.Namespace) -> int:
    assert_completion_claims_clear(args.engagement.absolute())
    emit({"code": "completion_claims_clear", "valid": True})
    return 0


def command_export_telemetry(args: argparse.Namespace) -> int:
    if args.output:
        _require_offline_output(args.output)
    try:
        export = export_telemetry(args.engagement, args.output)
    except ValueError as exc:
        raise RecordError("offline_output_forbidden", "offline output destination is governed or quarantined") from exc
    emit(export if args.output is None else {"valid": True, "output": args.output.as_posix(), "classification": export["classification"], "candidate_count": len(export["candidates"])})
    return 0


def command_score_telemetry(args: argparse.Namespace) -> int:
    def parse_telemetry(data: bytes) -> dict[str, object]:
        try:
            value = json.loads(
                data.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs
            )
        except (UnicodeDecodeError, json.JSONDecodeError, RecordError) as exc:
            raise RecordError(
                "telemetry_input_invalid", "telemetry source is invalid JSON"
            ) from exc
        if not isinstance(value, dict):
            raise RecordError(
                "telemetry_input_invalid", "telemetry source is not a JSON object"
            )
        return value

    located = find_engagement_root(args.file)
    if located is not None:
        logical, relative = located
        with bound_engagement_source(logical) as bound:
            try:
                source = read_governed_file(bound.joinpath(*relative))
            except (OSError, RecordError) as exc:
                raise RecordError(
                    "telemetry_input_unavailable", "telemetry source could not be read"
                ) from exc
            result = score_telemetry(parse_telemetry(source))
            # The context performs the same check after the body. Checking immediately before the
            # irreversible stdout write prevents a swap that occurred during parse/score from
            # admitting bytes while the source's public name points at quarantined evidence.
            try:
                root_fd = int(bound.parts[3])
                opened = os.fstat(root_fd)
                named = os.stat(logical, follow_symlinks=False)
            except (OSError, ValueError, IndexError) as exc:
                raise RecordError(
                    "engagement_source_changed", "telemetry source changed"
                ) from exc
            if (
                stat.S_ISLNK(named.st_mode)
                or not stat.S_ISDIR(named.st_mode)
                or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
                or inspect_quarantine(bound)["quarantined"]
                or inspect_quarantine(logical)["quarantined"]
            ):
                raise RecordError(
                    "engagement_source_changed", "telemetry source changed"
                )
            emit(result)
        return 0

    try:
        source = read_safe_offline_file(args.file)
    except (OSError, ValueError) as exc:
        raise RecordError(
            "telemetry_input_unavailable", "telemetry source could not be read"
        ) from exc
    emit(score_telemetry(parse_telemetry(source)))
    return 0


def command_record_memory(args: argparse.Namespace) -> int:
    value = load_json(args.file); action = _authority_action("record-memory", lane_id=args.lane_id, executor_id=args.executor_id, session_id=args.session_id, file_digest=sha256_file(args.file), operator_id=args.operator_id); _require_async_authority(args, action, value["recorded_at"])
    record = record_memory_disposition(args.engagement, args.file, args.operator_id, args.authority_request_id, args.executor_id, args.session_id)
    emit({"valid": True, "disposition_id": record["disposition_id"], "disposition": record["disposition"], "plane1_modified": False})
    return 0


def command_close(args: argparse.Namespace) -> int:
    action = _authority_action("close", lane_id=args.lane_id, executor_id=args.executor_id, session_id=args.session_id, operator_id=args.operator_id, reason=args.reason, recorded_at=args.recorded_at); _require_async_authority(args, action, args.recorded_at)
    snapshot = close_engagement(args.engagement, args.operator_id, args.reason, args.recorded_at, args.authority_request_id, args.executor_id, args.session_id)
    emit({"valid": True, "engagement_id": snapshot["engagement_id"], "closed": True, "memory_disposition": snapshot["memory_disposition"]})
    return 0


def command_preflight(args: argparse.Namespace) -> int:
    _require_local_provenance(args.actor_role, args.actor_id, args.session_id)
    capability = classify_command("preflight")
    _enforce_mutation(capability, args.engagement, args.actor_role, args.actor_id, "environment-preflight")
    try:
        reproduction = json.loads(args.reproduction_argv)
        if not isinstance(reproduction, list) or any(not isinstance(item, str) or not item for item in reproduction):
            raise ValueError("reproduction argv must be a JSON array of strings; an empty array records a blocked preflight")
        record = collect_agent_preflight(args.engagement, preflight_id=args.preflight_id, mode=args.mode, target=args.target, expected_identity=args.expected_identity, runtime=args.runtime, reproduction_argv=reproduction, operator_id=args.actor_id, recorded_at=args.recorded_at, advisory_zone=args.advisory_zone, credentials_present=args.credentials_present, account_labels=args.account_label, configuration_files=args.configuration_file, endpoint_identity=args.endpoint_identity, account_role=args.account_role, feature_flags=args.feature_flag, actor_role=args.actor_role, actor_id=args.actor_id, session_id=args.session_id, model=args.model, provider=args.provider, tool_versions=args.tool_version)
    except (ValueError, json.JSONDecodeError) as exc:
        raise RecordError("preflight_invalid", str(exc)) from exc
    emit({"valid": True, "preflight_id": record["preflight_id"], "status": record["status"], "identity_hash": record["identity_hash"], "missing_fidelity": record["missing_fidelity"], "advisory_zone": record["safety"]["advisory_zone"], "zone2_authorization_granted": False})
    return 0


def _verify_review_signature(
    engagement: Path,
    review_bytes: bytes,
    reviewer_id: str,
    signature_bytes: bytes,
    allowed_signers_bytes: bytes,
    *,
    timeout_seconds: float = SSH_VERIFY_TIMEOUT_SECONDS,
) -> str:
    state = reduce_engagement(engagement.absolute()); latest_scope = next(event for event in reversed(read_ledger(engagement.absolute(), "event")) if event["event_type"] == "scope.attested"); scope_path = engagement.absolute()/latest_scope["payload"]["scope_snapshot_path"]
    try: scope_bytes = read_governed_file(scope_path)
    except (OSError, RecordError): raise RecordError("reviewer_signature_invalid", reviewer_id)
    if sha256_bytes(scope_bytes) != state["scope_hash"]: raise RecordError("reviewer_signature_invalid", reviewer_id)
    try: scope_text = scope_bytes.decode("utf-8")
    except UnicodeDecodeError: raise RecordError("reviewer_signature_invalid", reviewer_id)
    match = re.search(r"Reviewer allowed signers SHA256:\s*(sha256:[0-9a-f]{64})", scope_text)
    if (
        match is None
        or not isinstance(signature_bytes, bytes)
        or not isinstance(allowed_signers_bytes, bytes)
        or len(signature_bytes) > REVIEW_SIGNATURE_MAX_BYTES
        or len(allowed_signers_bytes) > REVIEW_ALLOWED_SIGNERS_MAX_BYTES
        or not isinstance(timeout_seconds, (int, float))
        or isinstance(timeout_seconds, bool)
        or timeout_seconds <= 0
    ): raise RecordError("reviewer_signature_invalid", reviewer_id)
    if sha256_bytes(allowed_signers_bytes) != match.group(1): raise RecordError("reviewer_signature_invalid", reviewer_id)
    with tempfile.TemporaryDirectory(prefix="review-signature-") as temporary:
        temporary_root = Path(temporary); signature_copy = temporary_root / "review.sig"; signers_copy = temporary_root / "allowed_signers"; signature_copy.write_bytes(signature_bytes); signers_copy.write_bytes(allowed_signers_bytes)
        command = ["/usr/bin/ssh-keygen", "-Y", "verify", "-f", str(signers_copy), "-I", reviewer_id, "-n", "llm-redteam-harness-review-v1", "-s", str(signature_copy)]
        try:
            result = subprocess.run(command, input=review_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"}, check=False, timeout=timeout_seconds)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RecordError("reviewer_signature_invalid", reviewer_id) from exc
    if result.returncode != 0: raise RecordError("reviewer_signature_invalid", reviewer_id)
    fingerprint_match = re.search(rb"\bkey\s+SHA256:([A-Za-z0-9+/=]+)\s*$", result.stdout.strip())
    if fingerprint_match is None:
        raise RecordError("reviewer_signature_identity_unavailable", reviewer_id)
    encoded = fingerprint_match.group(1)
    try:
        digest = base64.b64decode(encoded + b"=" * (-len(encoded) % 4), validate=True)
    except ValueError as exc:
        raise RecordError("reviewer_signature_identity_unavailable", reviewer_id) from exc
    if len(digest) != 32:
        raise RecordError("reviewer_signature_identity_unavailable", reviewer_id)
    return "sha256:" + digest.hex()


def _copy_engagement_for_review_staging(
    source: Path, destination: Path, *, deadline: float | None = None
) -> None:
    """Copy one locked engagement without following any source filesystem alias."""

    if deadline is None:
        deadline = time.monotonic() + REVIEW_STAGING_TIMEOUT_SECONDS
    if (
        not isinstance(deadline, (int, float))
        or isinstance(deadline, bool)
        or not math.isfinite(float(deadline))
        or deadline <= time.monotonic()
    ):
        raise RecordError("record_review_staging_budget_exceeded", "staging deadline")
    entry_count = 0
    allocated_bytes = 0

    def require_budget(detail: str) -> None:
        if time.monotonic() >= deadline:
            raise RecordError("record_review_staging_budget_exceeded", detail)

    def account_allocation(value: os.stat_result, detail: str) -> None:
        nonlocal allocated_bytes
        blocks = max(0, int(getattr(value, "st_blocks", 0)))
        allocated_bytes += blocks * 512
        if allocated_bytes > REVIEW_STAGING_MAX_ALLOCATED_BYTES:
            raise RecordError("record_review_staging_budget_exceeded", detail)

    def bounded_names(directory_fd: int, detail: str) -> list[str]:
        nonlocal entry_count
        names: list[str] = []
        require_budget(detail)
        with os.scandir(directory_fd) as entries:
            for entry in entries:
                require_budget(detail)
                entry_count += 1
                if entry_count > REVIEW_STAGING_MAX_ENTRIES:
                    raise RecordError("record_review_staging_budget_exceeded", detail)
                names.append(entry.name)
        names.sort()
        return names

    def require_same_names(
        directory_fd: int, expected: list[str], detail: str
    ) -> None:
        current: list[str] = []
        require_budget(detail)
        with os.scandir(directory_fd) as entries:
            for entry in entries:
                if len(current) > len(expected):
                    raise RecordError("record_review_staging_source_changed", detail)
                current.append(entry.name)
        if sorted(current) != expected:
            raise RecordError("record_review_staging_source_changed", detail)

    source = source.absolute()
    if (
        len(source.parts) == 4
        and source.parts[1:3] == ("dev", "fd")
        and source.parts[3].isdigit()
    ):
        source_fd = os.dup(int(source.parts[3]))
    else:
        source_fd = os.open(
            source,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
    source_root_stat = os.fstat(source_fd)
    if not stat.S_ISDIR(source_root_stat.st_mode):
        os.close(source_fd)
        raise RecordError(
            "record_review_staging_source_unsafe",
            "engagement source is not a directory",
        )
    account_allocation(source_root_stat, ".")

    destination.mkdir(mode=0o700)
    destination_fd = os.open(
        destination,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )

    def identity(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
        return (
            value.st_dev,
            value.st_ino,
            value.st_mode,
            value.st_size,
            value.st_mtime_ns,
            value.st_ctime_ns,
        )

    fclonefileat = None
    if sys.platform == "darwin":
        try:
            candidate = getattr(ctypes.CDLL(None, use_errno=True), "fclonefileat")
            candidate.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
            candidate.restype = ctypes.c_int
            fclonefileat = candidate
        except (AttributeError, OSError):
            fclonefileat = None

    def write_all(file_fd: int, data: bytes) -> None:
        remaining = memoryview(data)
        while remaining:
            written = os.write(file_fd, remaining)
            if written <= 0:
                raise OSError("short staging write")
            remaining = remaining[written:]

    def copy_bytes(source_file_fd: int, destination_file_fd: int, count: int) -> None:
        remaining = count
        while remaining:
            require_budget("source bytes")
            chunk = os.read(source_file_fd, min(1024 * 1024, remaining))
            if not chunk:
                raise RecordError(
                    "record_review_staging_source_changed",
                    "source file shortened during staging",
                )
            write_all(destination_file_fd, chunk)
            remaining -= len(chunk)

    def copy_sparse_or_stream(source_file_fd: int, destination_file_fd: int, size: int) -> None:
        """Bound memory and preserve sparse holes when a CoW clone is unavailable."""

        require_budget("sparse source")
        os.ftruncate(destination_file_fd, size)
        seek_data = getattr(os, "SEEK_DATA", None)
        seek_hole = getattr(os, "SEEK_HOLE", None)
        first_data: int | None = None
        sparse_supported = seek_data is not None and seek_hole is not None
        if sparse_supported and size:
            try:
                first_data = os.lseek(source_file_fd, 0, seek_data)
            except OSError as exc:
                if exc.errno == errno.ENXIO:
                    return
                if exc.errno in {errno.EINVAL, errno.ENOTSUP, getattr(errno, "EOPNOTSUPP", errno.ENOTSUP)}:
                    sparse_supported = False
                else:
                    raise
        if not sparse_supported:
            os.lseek(source_file_fd, 0, os.SEEK_SET)
            os.lseek(destination_file_fd, 0, os.SEEK_SET)
            copy_bytes(source_file_fd, destination_file_fd, size)
            return
        data_offset = first_data
        while data_offset is not None and data_offset < size:
            require_budget("sparse source")
            try:
                hole_offset = min(os.lseek(source_file_fd, data_offset, seek_hole), size)
            except OSError as exc:
                if exc.errno != errno.ENXIO:
                    raise
                hole_offset = size
            os.lseek(source_file_fd, data_offset, os.SEEK_SET)
            os.lseek(destination_file_fd, data_offset, os.SEEK_SET)
            copy_bytes(source_file_fd, destination_file_fd, hole_offset - data_offset)
            if hole_offset >= size:
                break
            try:
                data_offset = os.lseek(source_file_fd, hole_offset, seek_data)
            except OSError as exc:
                if exc.errno != errno.ENXIO:
                    raise
                data_offset = None

    def clone_file(source_file_fd: int, destination_directory_fd: int, name: str) -> bool:
        require_budget(name)
        if fclonefileat is None:
            return False
        ctypes.set_errno(0)
        # CLONE_NOFOLLOW | CLONE_NOOWNERCOPY: the source is already a no-follow fd and the
        # staging copy must not require ownership replication privileges.
        if fclonefileat(source_file_fd, destination_directory_fd, os.fsencode(name), 0x0003) == 0:
            return True
        error = ctypes.get_errno()
        try:
            failed_entry = os.stat(name, dir_fd=destination_directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            failed_entry = None
        if failed_entry is not None:
            if not stat.S_ISREG(failed_entry.st_mode) or stat.S_ISLNK(failed_entry.st_mode):
                raise RecordError("record_review_staging_destination_unsafe", name)
            os.unlink(name, dir_fd=destination_directory_fd)
        unsupported = {
            errno.EINVAL,
            errno.ENOSYS,
            errno.ENOTSUP,
            errno.EPERM,
            errno.EXDEV,
            getattr(errno, "EOPNOTSUPP", errno.ENOTSUP),
        }
        if error in unsupported:
            return False
        raise OSError(error, os.strerror(error), name)

    def copy_directory(source_directory_fd: int, destination_directory_fd: int, prefix: tuple[str, ...]) -> None:
        detail = Path(*prefix).as_posix() or "."
        if len(prefix) > REVIEW_STAGING_MAX_DEPTH:
            raise RecordError("record_review_staging_budget_exceeded", detail)
        names = bounded_names(source_directory_fd, detail)
        for name in names:
            relative = Path(*prefix, name).as_posix()
            require_budget(relative)
            before = os.stat(name, dir_fd=source_directory_fd, follow_symlinks=False)
            account_allocation(before, relative)
            if stat.S_ISDIR(before.st_mode) and not stat.S_ISLNK(before.st_mode):
                child_source_fd = os.open(
                    name,
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=source_directory_fd,
                )
                opened = os.fstat(child_source_fd)
                if not stat.S_ISDIR(opened.st_mode) or identity(opened) != identity(before):
                    os.close(child_source_fd)
                    raise RecordError("record_review_staging_source_changed", relative)
                os.mkdir(name, 0o700, dir_fd=destination_directory_fd)
                child_destination_fd = os.open(
                    name,
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=destination_directory_fd,
                )
                try:
                    copy_directory(child_source_fd, child_destination_fd, (*prefix, name))
                    named_after = os.stat(name, dir_fd=source_directory_fd, follow_symlinks=False)
                    if (named_after.st_dev, named_after.st_ino) != (opened.st_dev, opened.st_ino):
                        raise RecordError("record_review_staging_source_changed", relative)
                    os.fsync(child_destination_fd)
                finally:
                    os.close(child_destination_fd)
                    os.close(child_source_fd)
                continue
            if not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode):
                raise RecordError("record_review_staging_source_unsafe", relative)
            source_file_fd = os.open(
                name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=source_directory_fd,
            )
            try:
                opened = os.fstat(source_file_fd)
                if not stat.S_ISREG(opened.st_mode) or identity(opened) != identity(before):
                    raise RecordError("record_review_staging_source_changed", relative)
                if not clone_file(source_file_fd, destination_directory_fd, name):
                    destination_file_fd = os.open(
                        name,
                        os.O_RDWR
                        | os.O_CREAT
                        | os.O_EXCL
                        | getattr(os, "O_NOFOLLOW", 0),
                        0o600,
                        dir_fd=destination_directory_fd,
                    )
                    try:
                        copy_sparse_or_stream(source_file_fd, destination_file_fd, opened.st_size)
                        os.fsync(destination_file_fd)
                    finally:
                        os.close(destination_file_fd)
                after = os.fstat(source_file_fd)
                named_after = os.stat(name, dir_fd=source_directory_fd, follow_symlinks=False)
                if identity(opened) != identity(after) or identity(after) != identity(named_after):
                    raise RecordError("record_review_staging_source_changed", relative)
            finally:
                os.close(source_file_fd)
            destination_file_fd = os.open(
                name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=destination_directory_fd,
            )
            try:
                staged = os.fstat(destination_file_fd)
                if (
                    not stat.S_ISREG(staged.st_mode)
                    or staged.st_size != opened.st_size
                    or (staged.st_dev, staged.st_ino) == (opened.st_dev, opened.st_ino)
                ):
                    raise RecordError("record_review_staging_destination_unsafe", relative)
            finally:
                os.close(destination_file_fd)
        require_same_names(source_directory_fd, names, detail)

    try:
        copy_directory(source_fd, destination_fd, ())
        require_budget("staging fsync")
        os.fsync(destination_fd)
    finally:
        os.close(destination_fd)
        os.close(source_fd)


def _apply_record_review_transaction(
    engagement: Path,
    *,
    relative: str,
    data: bytes,
    commit: dict[str, object],
    event: dict[str, object],
) -> dict[str, object]:
    """Apply the exact idempotent review transaction to one already locked tree."""

    destination = engagement / relative
    prior_bytes = _governed_regular_bytes_or_none(destination)
    if prior_bytes is not None and prior_bytes != data:
        raise RecordError("review_id_collision", str(event.get("payload", {}).get("review_ref", "unknown")))
    if prior_bytes is None:
        atomic_write(destination, data)
    commit_event = next(
        (
            candidate
            for candidate in read_ledger(engagement, "event")
            if candidate.get("event_id") == commit["event_id"]
        ),
        None,
    )
    if commit_event is None or commit_event.get("payload", {}).get("record_digest") != commit["payload"]["record_digest"]:
        _append_kernel_event_idempotent(engagement, commit, lock_held=True)
    applied = _append_kernel_event_idempotent(engagement, event, lock_held=True)
    # Each kernel append already reduces the complete ledger and atomically publishes the snapshot
    # and views under this same lock. Repeating that full reduction here made review staging scale
    # as three reductions and could consume the fixed prewrite budget before the live commit.
    return applied


def _record_review_prewrite_deadline(args: argparse.Namespace) -> float:
    """Return the earlier local staging bound or trusted outer-driver wall deadline."""

    now = time.monotonic()
    deadline = now + REVIEW_STAGING_TIMEOUT_SECONDS
    authenticated_runtime = getattr(args, "_driver_authenticated_runtime", None)
    if isinstance(authenticated_runtime, dict):
        outer = authenticated_runtime.get("deadline_monotonic")
        if outer is not None:
            if (
                not isinstance(outer, (int, float))
                or isinstance(outer, bool)
                or not math.isfinite(float(outer))
                or outer <= now
            ):
                raise RecordError(
                    "record_review_staging_budget_exceeded", "outer driver deadline"
                )
            deadline = min(deadline, float(outer))
    return deadline


def _require_record_review_prewrite_time(deadline: float, detail: str) -> None:
    if time.monotonic() >= deadline:
        raise RecordError("record_review_staging_budget_exceeded", detail)


def command_record_review(args: argparse.Namespace) -> int:
    _require_decision6_kernel(args.engagement)
    _require_local_provenance("broker", args.actor_id, args.session_id); review = _command_json(args, "file"); event = _command_json(args, "event")
    mapping = {"claim_adjudication": "claim.adjudicated", "coverage": "review.coverage_completed", "regrade": "review.regrade_completed", "pocinator": "review.pocinator_completed"}
    expected_event = mapping.get(review.get("review_type")); reviewer_id = review.get("independence", {}).get("reviewer_id"); reviewer_session = review.get("independence", {}).get("reviewer_session_id")
    if not isinstance(reviewer_session, str) or not reviewer_session: raise RecordError("reviewer_session_unbound", str(reviewer_id or "unknown"))
    authenticated_runtime = getattr(args, "_driver_authenticated_runtime", None)
    if isinstance(authenticated_runtime, dict) and (
        reviewer_session != authenticated_runtime.get("runtime_session_ref")
        or review.get("independence", {}).get("reviewer_model") != authenticated_runtime.get("model")
    ):
        raise RecordError("driver_reviewer_runtime_binding_mismatch", str(review.get("review_id", "unknown")))
    review_secret_classes = detect_secret_classes(canonical_json_bytes(review))
    event_secret_classes = detect_secret_classes(canonical_json_bytes(event))
    if (review_secret_classes or event_secret_classes) and not args.attest_synthetic:
        raise RecordError("canonical_review_binding_invalid", review.get("review_id", "unknown"))
    if expected_event is None or event.get("event_type") != expected_event or event.get("operation_class") != "notebook" or event.get("actor") != {"role": "broker", "id": args.actor_id} or event.get("provenance", {}).get("session_id") != args.session_id or event.get("payload", {}).get("review_ref") != review.get("review_id") or event.get("payload", {}).get("reviewer_id") != reviewer_id or review.get("review_id") not in event.get("review_refs", []):
        raise RecordError("canonical_review_binding_invalid", review.get("review_id", "unknown"))
    review_errors = validate_record_with_references(review, "review", args.engagement)
    if review_errors: raise RecordError("canonical_review_invalid", review.get("review_id", "unknown"), review_errors)
    relative = f"reviews/{review['review_id']}.json"; data = canonical_json_bytes(review)
    with engagement_lock(args.engagement.absolute()) as bound_engagement:
        state = reduce_engagement(bound_engagement, allowed_record_orphans={relative})
        if review.get("engagement_id") != state["engagement_id"] or event.get("engagement_id") != state["engagement_id"]: raise RecordError("cross_engagement_review", review.get("review_id", "unknown"))
        deadline = _record_review_prewrite_deadline(args)
        try:
            signature_bytes = _command_bytes(
                args, "signature", max_bytes=REVIEW_SIGNATURE_MAX_BYTES
            )
            allowed_signers_bytes = _command_bytes(
                args,
                "allowed_signers",
                max_bytes=REVIEW_ALLOWED_SIGNERS_MAX_BYTES,
            )
        except (OSError, RecordError) as exc:
            raise RecordError("reviewer_signature_invalid", str(reviewer_id or "")) from exc
        _require_record_review_prewrite_time(deadline, "signature input")
        verified_signer_fingerprint = _verify_review_signature(
            bound_engagement,
            data,
            str(reviewer_id or ""),
            signature_bytes,
            allowed_signers_bytes,
            timeout_seconds=min(
                SSH_VERIFY_TIMEOUT_SECONDS,
                max(0.001, deadline - time.monotonic()),
            ),
        )
        _require_record_review_prewrite_time(deadline, "signature verification")
        proposed_signer_fingerprint = review.get("independence", {}).get("reviewer_signer_fingerprint")
        if proposed_signer_fingerprint is not None and proposed_signer_fingerprint != verified_signer_fingerprint:
            raise RecordError("reviewer_signature_identity_mismatch", str(reviewer_id or "unknown"))
        commit = base_event(event_id=f"event-{review['review_id']}-commit", engagement_id=state["engagement_id"], recorded_at=event["recorded_at"], actor_role="broker", actor_id=args.actor_id, event_type="record.committed", rationale="Commit immutable externally-produced independent review.", payload={"record_path": relative, "record_digest": sha256_bytes(data), "record_type": "review", "record_id": review["review_id"], "record_revision": None}, session_id=args.session_id, operation_class="notebook")
        engagement_id = str(state["engagement_id"])
        if Path(engagement_id).name != engagement_id or engagement_id in {"", ".", ".."}:
            raise RecordError("record_review_staging_engagement_id_invalid", engagement_id)
        copy_started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="record-review-transaction-") as temporary:
            staged_engagement = Path(temporary) / engagement_id
            _copy_engagement_for_review_staging(
                bound_engagement, staged_engagement, deadline=deadline
            )
            copy_finished = time.monotonic()
            with engagement_lock(staged_engagement) as bound_staged_engagement:
                _apply_record_review_transaction(
                    bound_staged_engagement,
                    relative=relative,
                    data=data,
                    commit=commit,
                    event=event,
                )
            staged_finished = time.monotonic()
        _require_record_review_prewrite_time(deadline, "live commit")
        remaining_before_live_commit = max(0.0, deadline - time.monotonic())
        applied = _apply_record_review_transaction(
            bound_engagement,
            relative=relative,
            data=data,
            commit=commit,
            event=event,
        )
    emit({"valid": True, "review_id": review["review_id"], "event_id": applied["event_id"], "claim_truth_self_accepted": False, "staging_timing_ms": {"copy_snapshot": round((copy_finished - copy_started) * 1000, 3), "staged_transaction": round((staged_finished - copy_finished) * 1000, 3), "remaining_before_live_commit": round(remaining_before_live_commit * 1000, 3), "declared_budget": round(REVIEW_STAGING_TIMEOUT_SECONDS * 1000, 3)}}); return 0


def command_review_preflight(args: argparse.Namespace) -> int:
    action = _authority_action("review-preflight", lane_id=args.lane_id, executor_id=args.executor_id, session_id=args.session_id, preflight_id=args.preflight_id, verdict=args.verdict, reason=args.reason, operator_id=args.operator_id, recorded_at=args.recorded_at); _require_async_authority(args, action, args.recorded_at)
    review = review_preflight(args.engagement, args.preflight_id, args.verdict, args.reason, args.operator_id, args.recorded_at, args.authority_request_id, args.lane_id, args.executor_id, args.session_id)
    emit({"valid": True, "review_id": review["review_id"], "preflight_id": args.preflight_id, "verdict": args.verdict}); return 0


def command_migrate(args: argparse.Namespace) -> int:
    for output_path in (args.output, args.migration_dir):
        if output_path is not None:
            _require_offline_output(output_path)
    if sum(value is not None for value in (args.propose_engagement,args.dry_run_engagement,args.apply_proposal))>1:raise RecordError("migration_mode_conflict","choose exactly one migration mode")
    variant = "apply" if args.apply_proposal else ("propose" if args.propose_engagement or args.dry_run_engagement else "inventory")
    capability = classify_command("migrate", variant=variant)
    if variant == "apply":
        if not all((args.authority_engagement, args.operator_id, args.recorded_at, args.destination, args.authority_request_id, args.lane_id, args.executor_id, args.session_id)): raise RecordError("migration_apply_args_missing", "apply requires destination, control engagement, operator, time, and exact authority binding")
        _require_local_provenance("broker", args.executor_id, args.session_id); control = args.authority_engagement.absolute()
        proposal_bytes, proposal_input_identity = _read_migration_authority_input(args.apply_proposal)
        review_bytes = None
        authority_inputs = [(args.apply_proposal, proposal_input_identity)]
        if args.artifact_review:
            review_bytes, review_input_identity = _read_migration_authority_input(args.artifact_review)
            authority_inputs.append((args.artifact_review, review_input_identity))
        authority_inputs = tuple(authority_inputs)
        proposal_digest = sha256_bytes(proposal_bytes); review_digest = sha256_bytes(review_bytes) if review_bytes is not None else None
        root_fd, root_resolved, root_identity = _open_bound_directory(args.root); destination_fd = source_fd = control_fd = -1
        try:
            destination_fd, destination_resolved, destination_identity = _open_bound_directory(args.destination)
            _require_migration_tree_safety(root_fd, destination_fd, proposal_bytes, resume=True)
            source_id = _migration_proposal_identity(proposal_bytes)
            source_base = root_resolved/"engagements" if (root_resolved/"engagements").is_dir() else root_resolved
            source_engagement = source_base/source_id
            source_fd, source_resolved, source_identity = _open_bound_directory(source_engagement)
            _require_migration_directories_separate(source_resolved, destination_resolved)
            control_fd, control_resolved, control_identity = _open_bound_directory(control)
            bound_entries = (
                (control_fd, control_resolved, control_identity),
                (source_fd, source_resolved, source_identity),
                (destination_fd, destination_resolved, destination_identity),
            )
            identities = {(identity["device"], identity["inode"]) for _, _, identity in bound_entries}
            if len(identities) != len(bound_entries):
                raise RecordError("migration_directory_alias", "control, source, and destination must be distinct directories")
            control_bound = Path(f"/dev/fd/{control_fd}")
            source_bound = Path(f"/dev/fd/{source_fd}")
            destination_bound = Path(f"/dev/fd/{destination_fd}")
            with ExitStack() as migration_locks:
                for directory_fd, _, identity in sorted(bound_entries, key=lambda entry: (entry[2]["device"], entry[2]["inode"])):
                    migration_locks.enter_context(bound_engagement_lock(directory_fd))
                for directory_fd, resolved, identity in bound_entries:
                    _require_bound_directory_current(directory_fd, resolved, identity, args.authority_request_id)
                for bound_engagement in (control_bound, source_bound, destination_bound):
                    require_not_quarantined(bound_engagement)
                _require_migration_authority_inputs_current(authority_inputs)
                _require_migration_tree_safety(root_fd, destination_fd, proposal_bytes, resume=True, bound_source_fd=source_fd)
                source_scope_bytes=read_governed_file(source_bound/"scope.md"); destination_scope_bytes=read_governed_file(destination_bound/"scope.md"); source_scope_hash=sha256_bytes(source_scope_bytes); destination_scope_hash=sha256_bytes(destination_scope_bytes)
                action = _authority_action(
                    "apply-migration",
                    lane_id=args.lane_id,
                    executor_id=args.executor_id,
                    session_id=args.session_id,
                    operator_id=args.operator_id,
                    recorded_at=args.recorded_at,
                    proposal_digest=proposal_digest,
                    artifact_review_digest=review_digest,
                    root=str(root_resolved),
                    root_identity=root_identity,
                    destination=str(destination_resolved),
                    destination_identity=destination_identity,
                    source_identity_digest=sha256_bytes(canonical_json_bytes(source_identity)),
                    control_identity_digest=sha256_bytes(canonical_json_bytes(control_identity)),
                    source_scope_hash=source_scope_hash,
                    destination_scope_hash=destination_scope_hash,
                    operator_redaction_attested=True,
                )
                action_digest = sha256_bytes(canonical_json_bytes(action)); journal_path=control_bound/"authority"/"migration-runs"/f"{action_digest.removeprefix('sha256:')}.json"; journal_bytes=canonical_json_bytes({"schema_version":1,"request_id":args.authority_request_id,"action_digest":action_digest,"action":action,"status":"authorized"})
                try: existing_journal=read_governed_file(journal_path)
                except FileNotFoundError: existing_journal=None
                if existing_journal is not None and existing_journal != journal_bytes: raise RecordError("migration_resume_journal_mismatch", args.authority_request_id)
                resume=existing_journal is not None; _require_migration_tree_safety(root_fd, destination_fd, proposal_bytes, resume=resume, bound_source_fd=source_fd)
                control_state=reduce_engagement(control_bound); authorization_id=f"event-migration-authorized-{args.authority_request_id}"; existing_authorization=next((event for event in read_ledger(control_bound,"event") if event["event_id"]==authorization_id),None)
                if resume:
                    if existing_authorization is None:
                        _require_migration_authority_inputs_current(authority_inputs)
                        authority_args=argparse.Namespace(engagement=control_bound,executor_id=args.executor_id,session_id=args.session_id,authority_request_id=args.authority_request_id); _require_async_authority(authority_args,action,args.recorded_at); authorization_event=base_event(event_id=authorization_id,engagement_id=control_state["engagement_id"],recorded_at=args.recorded_at,actor_role="broker",actor_id=args.executor_id,event_type="migration.apply_authorized",rationale="Resume exact authorized migration after journal persistence.",payload={"entity_id":args.authority_request_id,"status":"authorized","action_digest":action_digest,"proposal_digest":proposal_digest,"destination_digest":sha256_bytes(str(destination_resolved).encode()),"operator_id":args.operator_id,"authority_request_ref":args.authority_request_id,"executor_id":args.executor_id},session_id=args.session_id,operation_class="authority"); _append_kernel_event_idempotent(control_bound,authorization_event,lock_held=True)
                    elif existing_authorization.get("payload",{}).get("action_digest") != action_digest: raise RecordError("migration_resume_authorization_invalid", args.authority_request_id)
                else:
                    _require_migration_authority_inputs_current(authority_inputs)
                    authority_args = argparse.Namespace(engagement=control_bound, executor_id=args.executor_id, session_id=args.session_id, authority_request_id=args.authority_request_id); _require_async_authority(authority_args, action, args.recorded_at); atomic_write(journal_path,journal_bytes)
                    authorization_event = base_event(event_id=authorization_id, engagement_id=control_state["engagement_id"], recorded_at=args.recorded_at, actor_role="broker", actor_id=args.executor_id, event_type="migration.apply_authorized", rationale="Consume one exact migration authority before any migration effect, including bound-input persistence.", payload={"entity_id": args.authority_request_id, "status":"authorized", "action_digest":action_digest,"proposal_digest":proposal_digest,"destination_digest":sha256_bytes(str(destination_resolved).encode()),"operator_id":args.operator_id,"authority_request_ref":args.authority_request_id,"executor_id":args.executor_id},session_id=args.session_id,operation_class="authority"); _append_kernel_event_idempotent(control_bound,authorization_event,lock_held=True)
                inputs = control_bound/"authority"/"apply-inputs"; proposal_copy = inputs/f"{action_digest.removeprefix('sha256:')}.proposal.json"; review_copy = inputs/f"{action_digest.removeprefix('sha256:')}.review.json"
                for path, data in ((proposal_copy, proposal_bytes), (review_copy, review_bytes)):
                    if data is None: continue
                    try: prior=read_governed_file(path)
                    except FileNotFoundError: prior=None
                    if prior is not None and prior != data: raise RecordError("migration_bound_input_collision", str(path))
                    if prior is None: atomic_write(path, data); _chmod_governed_file(path, 0o400)
                _require_bound_directory_current(root_fd, root_resolved, root_identity, args.authority_request_id)
                for directory_fd, resolved, identity in bound_entries:
                    _require_bound_directory_current(directory_fd, resolved, identity, args.authority_request_id)
                proposal_copy_fd = _open_governed_regular(proposal_copy); review_copy_fd = _open_governed_regular(review_copy) if review_bytes is not None else -1
                try:
                    _require_migration_authority_inputs_current(authority_inputs)
                    implementation = runpy.run_path(str(Path(__file__).with_name("migrate-decision5.py"))); migrated = implementation["apply_proposal"](root_resolved, Path(f"/dev/fd/{proposal_copy_fd}"), destination_resolved, args.operator_id, args.recorded_at, operator_redaction_attested=True, artifact_review_path=Path(f"/dev/fd/{review_copy_fd}") if review_copy_fd >= 0 else None, bound_root_fd=root_fd, bound_source_fd=source_fd, bound_destination_fd=destination_fd, canonical_source_path=source_resolved, canonical_destination_path=destination_resolved, destination_engagement_id=destination_resolved.name, resume_authorized=resume, authority_request_ref=args.authority_request_id, authority_action_digest=action_digest, authority_control_engagement_id=control_state["engagement_id"], expected_source_scope_hash=source_scope_hash, expected_destination_scope_hash=destination_scope_hash, executor_id=args.executor_id, executor_session_id=args.session_id, locks_held=True, expected_source_engagement_id=source_id)
                finally:
                    os.close(proposal_copy_fd)
                    if review_copy_fd >= 0: os.close(review_copy_fd)
                _require_bound_directory_current(root_fd, root_resolved, root_identity, args.authority_request_id)
                for directory_fd, resolved, identity in bound_entries:
                    _require_bound_directory_current(directory_fd, resolved, identity, args.authority_request_id)
            emit({"valid": True, "migration": migrated, "authority_request_id": args.authority_request_id}); return 0
        finally:
            os.close(root_fd)
            if destination_fd >= 0: os.close(destination_fd)
            if source_fd >= 0: os.close(source_fd)
            if control_fd >= 0: os.close(control_fd)
    elif variant == "propose":
        source_id=_validated_migration_engagement_id(args.propose_engagement or args.dry_run_engagement); source_base=args.root.absolute()/"engagements" if (args.root.absolute()/"engagements").is_dir() else args.root.absolute(); source_engagement=source_base/source_id
        if not args.executor_id or not args.session_id: raise RecordError("migration_proposal_provenance_missing", "proposal requires local broker executor/session")
        _require_local_provenance("broker", args.executor_id, args.session_id); implementation = runpy.run_path(str(Path(__file__).with_name("migrate-decision5.py")))
        published_file: tuple[Path, bytes, bool, bytes | None] | None = None
        published_tree: tuple[Path, dict[str, bytes]] | None = None
        try:
            with bound_engagement_source(source_engagement) as source_bound:
                source_metadata=_scope_metadata(source_bound/"scope.md")
                if source_metadata["record_kernel"]!="decision-0006-v1": raise RecordError("decision6_kernel_not_selected","migration broker proposal requires source scope decision-0006-v1")
                with tempfile.TemporaryDirectory(prefix="migration-proposal-source-") as temporary:
                    snapshot_root = Path(temporary) / "engagements" / source_id
                    snapshot_root.parent.mkdir(parents=True)
                    implementation["_snapshot_bound_engagement"](int(source_bound.name), snapshot_root)
                    synthetic_root = Path(temporary)
                    if args.propose_engagement:
                        if not args.operator_id or not args.output or not args.recorded_at: raise RecordError("migration_proposal_args_missing", "proposal requires --operator-id and --output")
                        staged_output = Path(temporary) / "proposal-output.json"
                        proposal = implementation["write_proposal"](synthetic_root, source_id, args.operator_id, args.recorded_at, staged_output, producer_role="broker", producer_id=args.executor_id)
                        proposal_bytes = read_safe_offline_file(staged_output)
                        existed, prior = _offline_file_preimage(args.output)
                        _require_bound_source_current(source_engagement, source_bound, label="migration")
                        atomic_write_offline(args.output, proposal_bytes)
                        published_file = (args.output, proposal_bytes, existed, prior)
                        _require_bound_source_current(source_engagement, source_bound, label="migration")
                        emit({"valid": True, "proposal_digest": sha256_bytes(proposal_bytes), "proposal_only": proposal["proposal_only"]})
                        return 0
                    if not args.operator_id or not args.recorded_at or not args.migration_dir: raise RecordError("migration_dry_run_args_missing", "dry-run bundle requires --operator-id, --recorded-at and --migration-dir")
                    staged_bundle = Path(temporary) / "dry-run-output"
                    bundle = implementation["write_dry_run_bundle"](synthetic_root, source_id, args.operator_id, args.recorded_at, staged_bundle, producer_role="broker", producer_id=args.executor_id)
                    bundle_files = read_safe_offline_tree(staged_bundle)
                    _require_bound_source_current(source_engagement, source_bound, label="migration")
                    atomic_publish_offline_tree(args.migration_dir, bundle_files)
                    published_tree = (args.migration_dir, bundle_files)
                    _require_bound_source_current(source_engagement, source_bound, label="migration")
                    emit({"valid": True, "bundle": bundle})
                    return 0
        except Exception as exc:
            if published_file is not None:
                _rollback_offline_file(*published_file)
            if published_tree is not None:
                _remove_exact_offline_tree(*published_tree)
            if isinstance(exc, RecordError):
                raise
            if isinstance(exc, (OSError, ValueError)):
                raise RecordError(
                    "migration_proposal_failed",
                    "migration source or offline output could not be admitted",
                ) from exc
            raise
    command = [sys.executable, str(Path(__file__).with_name("migrate-decision5.py")), "--root", str(args.root)]
    if args.output: command += ["--output", str(args.output)]
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        raise RecordError("migration_command_failed", result.stderr or result.stdout)
    if result.stdout: print(result.stdout, end="")
    else: emit({"valid": True, "output": str(args.output)})
    return 0


def _apply_finding_revision(args: argparse.Namespace, *, lock_held: bool = False, evaluated_at: datetime | None = None) -> dict[str, object]:
    finding = _command_json(args, "file"); raw_digest = sha256_bytes(_command_bytes(args, "file")); canonical_digest = sha256_bytes(canonical_json_bytes(finding)); engagement = args.engagement.absolute()
    finding_id = finding.get("finding_id", "unknown"); revision = finding.get("revision", 0); relative = f"findings/{finding_id}/rev-{revision}.json"
    pre_state = reduce_engagement(engagement, allowed_record_orphans={relative}); request = pre_state["authority_requests"].get(args.authority_request_id); target = request.get("target") if request else None
    explicit_resolutions = getattr(args, "resolve_review", None)
    if isinstance(target, dict):
        digest = canonical_digest
        if not revise_finding_target_is_current(pre_state, request, finding): raise RecordError("finding_revision_authority_stale", finding.get("finding_id", "unknown"))
        resolutions = target["resolves_review_refs"]
        if explicit_resolutions is not None and (explicit_resolutions != sorted(set(explicit_resolutions)) or explicit_resolutions != resolutions): raise RecordError("finding_revision_resolution_set_mismatch", finding.get("finding_id", "unknown"))
        stored_action_path = request.get("action_path") if isinstance(request, dict) else None
        stored_action = load_json(engagement / stored_action_path) if isinstance(stored_action_path, str) and stored_action_path else {}
        if (
            not isinstance(stored_action, dict)
            or stored_action.get("action_kind") != "revise-finding"
            or stored_action.get("action_version") != 3
            or stored_action.get("lane_id") != args.lane_id
            or stored_action.get("operator_id") != args.operator_id
            or stored_action.get("file_digest") != digest
            or stored_action.get("target") != target
            or stored_action.get("proposal") != finding
        ):
            raise RecordError("approved_revision_action_record_invalid", str(args.authority_request_id))
        action = stored_action
    else:
        raise RecordError("historical_finding_action_not_activatable", finding.get("finding_id", "unknown"))
    if not lock_held:
        _require_async_authority(args, action, args.recorded_at)
    errors = validate_record_with_references(finding, "finding-v3", args.engagement)
    if errors: raise RecordError("finding_revision_invalid", finding.get("finding_id", "unknown"), errors)
    finding_id = finding["finding_id"]; revision = finding["revision"]; relative = f"findings/{finding_id}/rev-{revision}.json"; review_id = finding["adjudication"]["review_ref"]
    transaction = nullcontext(engagement) if lock_held else engagement_lock(engagement)
    with transaction as bound_engagement:
        destination = bound_engagement / relative
        state = reduce_engagement(bound_engagement, allowed_record_orphans={relative}); index = build_reference_index(bound_engagement); review_entry = next((item for item in index.get(review_id, []) if item["type"] == "review" and item.get("engagement_id") == state["engagement_id"]), None)
        current_request = state["authority_requests"].get(args.authority_request_id)
        action_digest = sha256_bytes(canonical_json_bytes(action)); applied_at = datetime.fromisoformat(args.recorded_at.replace("Z", "+00:00")); now = evaluated_at or datetime.now(timezone.utc)
        expires_at = datetime.fromisoformat(current_request["expires_at"].replace("Z", "+00:00")) if current_request and current_request.get("expires_at") else None; resolved_at = datetime.fromisoformat(current_request["resolved_at"].replace("Z", "+00:00")) if current_request and current_request.get("resolved_at") else None
        locked_events = read_ledger(bound_engagement, "event"); authority_consumed = any(item.get("event_type") != "record.committed" and item.get("payload", {}).get("authority_request_ref") == args.authority_request_id for item in locked_events)
        signed_operator = next(item["payload"]["operator_id"] for item in reversed(locked_events) if item["event_type"] == "scope.attested")
        current_target = current_request.get("target") if current_request else None; current_is_v2 = isinstance(current_target, dict)
        request_environment_valid = bool(current_request and (current_request["environment_ref"] == state["active_environment_ref"] if current_is_v2 else current_request["environment_ref"] in {None, state["active_environment_ref"]}))
        action_record_valid = True
        if current_is_v2:
            stored_action_path = (current_request or {}).get("action_path")
            action_record_valid = bool(isinstance(stored_action_path, str) and stored_action_path and _governed_file_exists(bound_engagement / stored_action_path) and _governed_sha256_file(bound_engagement / stored_action_path) == action_digest)
        application = current_request.get("application") if current_request else None
        historical_principal_valid = bool(
            not current_is_v2
            or (
                isinstance(application, dict)
                and action.get("executor_id") == application.get("executor_id")
                and action.get("session_id") == application.get("session_id")
                and action.get("operator_id") == application.get("operator_id")
            )
        )
        locked_authority_valid = bool(current_request and current_request["status"] == "approved" and current_request["action_kind"] == "revise-finding" and current_request["action_digest"] == action_digest and current_request["lane_id"] == args.lane_id and current_request["scope_hash"] == state["scope_hash"] and request_environment_valid and resolved_at is not None and applied_at >= resolved_at and (expires_at is None or (applied_at <= expires_at and now <= expires_at)) and not authority_consumed and action_record_valid and historical_principal_valid and action.get("operator_id") == args.operator_id == signed_operator)
        if not locked_authority_valid: raise RecordError("approved_authority_request_required", args.authority_request_id)
        if isinstance(target, dict) and (current_request is None or not revise_finding_target_is_current(state, current_request, finding)): raise RecordError("finding_revision_authority_stale", finding_id)
        existing_destination_digest = _governed_optional_regular_digest(destination)
        if isinstance(target, dict) and existing_destination_digest not in {None, canonical_digest}: raise RecordError("finding_revision_authority_conflicts_with_unactivated_file", finding_id)
        adjudication = next((event for event in reversed(read_ledger(bound_engagement, "event")) if event["event_type"] == "claim.adjudicated" and event["payload"].get("entity_id") == finding_id and event["payload"].get("review_ref") == review_id), None)
        if review_entry is None or adjudication is None or finding.get("engagement_id") != state["engagement_id"]: raise RecordError("finding_adjudication_missing", finding_id)
        latest_adjudication = state["claim_adjudications"].get(finding_id)
        if latest_adjudication is None or latest_adjudication.get("event_ref") != adjudication["event_id"] or latest_adjudication.get("review_ref") != review_id or latest_adjudication.get("status") != finding.get("claim_state") or latest_adjudication.get("expected_filing_revision") != revision: raise RecordError("finding_revision_adjudication_stale", finding_id)
        adjudication_review = load_json(bound_engagement / review_entry["path"])
        review_independence = adjudication_review.get("independence", {})
        review_provenance = adjudication_review.get("provenance", {})
        finding_provenance = finding.get("scope_provenance", {}).get("provenance", {})
        activation_runtime_session = review_independence.get("reviewer_session_id")
        activation_model = review_independence.get("reviewer_model")
        activation_provider = review_provenance.get("provider")
        if (
            not isinstance(activation_runtime_session, str)
            or not activation_runtime_session
            or not isinstance(activation_model, str)
            or not activation_model
            or finding_provenance.get("actor")
            != {"role": "reviewer", "id": review_independence.get("reviewer_id")}
            or finding_provenance.get("session_id")
            != review_independence.get("reviewer_session_id")
            or finding_provenance.get("model") != activation_model
            or finding_provenance.get("provider") != activation_provider
        ):
            raise RecordError("finding_revision_review_provenance_invalid", finding_id)

        def activation_event() -> dict[str, object]:
            event = base_event(
                event_id=f"event-{finding_id}-revision-{revision}",
                engagement_id=state["engagement_id"],
                recorded_at=args.recorded_at,
                actor_role="broker",
                actor_id=args.executor_id,
                event_type="finding.revised",
                rationale=finding["change_reason"],
                payload={
                    "finding_id": finding_id,
                    "finding_revision": revision,
                    "status": finding["claim_state"],
                    "finding_digest": digest,
                    "adjudication_review_ref": review_id,
                    "adjudication_review_digest": sha256_bytes(
                        read_governed_file(bound_engagement / review_entry["path"])
                    ),
                    "adjudication_event_ref": adjudication["event_id"],
                    "supersedes_revision": finding["supersedes_revision"],
                    "change_reason": finding["change_reason"],
                    "resolves_review_refs": resolutions,
                    "filing_contract_version": 1,
                    "operator_id": args.operator_id,
                    "authority_request_ref": args.authority_request_id,
                },
                entity_refs=[finding_id, adjudication["event_id"]],
                finding_refs=[finding_id],
                review_refs=[review_id],
                session_id=args.session_id,
                operation_class="authority",
                model=activation_model,
                provider=activation_provider,
            )
            # The broker/parent is the recorder, but the reviewed finding content belongs to the
            # independently authenticated claim reviewer.  Regrade independence binds to that
            # author, not to the later authority-settlement runtime.
            event["provenance"]["runtime_session_ref"] = activation_runtime_session
            event["provenance"]["model"] = activation_model
            event["provenance"]["provider"] = activation_provider
            return event
        data = canonical_json_bytes(finding)
        existing_commit = next((c for c in read_ledger(bound_engagement, "event")
                                if c.get("event_id") == f"event-{finding_id}-r{revision}-commit"), None)
        activated = any(e.get("event_type") == "finding.revised"
                        and e.get("payload", {}).get("finding_id") == finding_id
                        and e.get("payload", {}).get("finding_revision") == revision
                        for e in read_ledger(bound_engagement, "event"))
        prior_bytes = _governed_regular_bytes_or_none(destination)
        if prior_bytes is not None and prior_bytes != data:
            raise RecordError("finding_revision_collision", f"{finding_id}:{revision}")
        if prior_bytes is None: atomic_write(destination, data)
        commit_id = f"event-{finding_id}-r{revision}-commit"
        commit = base_event(event_id=commit_id, engagement_id=state["engagement_id"], recorded_at=args.recorded_at, actor_role="broker", actor_id=args.executor_id, event_type="record.committed", rationale="Commit immutable operator-authorized finding revision.", payload={"record_path": relative, "record_digest": digest, "record_type": "finding-v3", "record_id": finding_id, "record_revision": revision, "authority_request_ref": args.authority_request_id}, session_id=args.session_id, operation_class="authority")
        commit_events = [c for c in read_ledger(bound_engagement, "event") if c.get("event_id") == commit["event_id"]]
        if commit_events and commit_events[0].get("payload", {}).get("record_digest") == digest:
            # Crash-resume: the finding revision was already committed with identical bytes; skip
            # re-committing and only append the missing finding.revised activation event.
            event = activation_event(); applied = _append_kernel_event_idempotent(bound_engagement, event, lock_held=True)
        else:
            _append_kernel_event_idempotent(bound_engagement, commit, lock_held=True)
            event = activation_event(); applied = _append_kernel_event_idempotent(bound_engagement, event, lock_held=True)
    return {"valid": True, "finding_id": finding_id, "revision": revision, "event_id": applied["event_id"], "adjudication_separate": True}


def command_revise_finding(args: argparse.Namespace) -> int:
    emit(_apply_finding_revision(args))
    return 0


def command_accept_report(args: argparse.Namespace) -> int:
    action = _authority_action("accept-report", lane_id=args.lane_id, executor_id=args.executor_id, session_id=args.session_id, report_id=args.report_id, operator_id=args.operator_id, reason=args.reason, recorded_at=args.recorded_at); _require_async_authority(args, action, args.recorded_at)
    try:
        review = accept_report(args.engagement, args.report_id, args.operator_id, args.reason, args.recorded_at, args.authority_request_id, args.executor_id, args.session_id)
    except ValueError as exc:
        raise RecordError("report_acceptance_invalid", str(exc)) from exc
    emit({"valid": True, "review_id": review["review_id"], "report_id": args.report_id})
    return 0


def command_record_submission(args: argparse.Namespace) -> int:
    action = _authority_action("record-submission", lane_id=args.lane_id, executor_id=args.executor_id, session_id=args.session_id, report_id=args.report_id, file_digest=sha256_file(args.file), program=args.program, operator_id=args.operator_id, recorded_at=args.recorded_at); _require_async_authority(args, action, args.recorded_at)
    try:
        submission_id = record_submission(args.engagement, args.report_id, args.file, args.program, args.operator_id, args.recorded_at, args.authority_request_id, args.executor_id, args.session_id)
    except ValueError as exc:
        raise RecordError("submission_invalid", str(exc)) from exc
    emit({"valid": True, "submission_id": submission_id, "report_id": args.report_id})
    return 0


def command_generate_report(args: argparse.Namespace) -> int:
    omitted = []
    for value in args.omit_claim:
        if "=" not in value:
            raise RecordError("invalid_omitted_claim", "use --omit-claim claim-id=rationale")
        claim_id, rationale = value.split("=", 1); omitted.append({"claim_id": claim_id, "rationale": rationale})
    action = _authority_action("generate-report", lane_id=args.lane_id, executor_id=args.executor_id, session_id=args.session_id, finding_id=args.finding_id, revision=args.revision, included_claim_ids=args.include_claim, omitted_claims=omitted, operator_id=args.operator_id, recorded_at=args.recorded_at); _require_async_authority(args, action, args.recorded_at)
    try:
        manifest = generate_report(args.engagement, args.finding_id, args.revision, args.include_claim, omitted, args.operator_id, args.recorded_at, args.authority_request_id, args.executor_id, args.session_id)
    except ValueError as exc:
        raise RecordError("report_generation_invalid", str(exc)) from exc
    emit({"valid": True, "report_id": manifest["report_id"], "report_digest": manifest["report_digest"]})
    return 0


def command_render_proof(args: argparse.Namespace) -> int:
    engagement = args.engagement.absolute()
    with bound_engagement_source(engagement) as bound:
        pending_error: RecordError | None = None
        result = None
        try:
            reduce_engagement(bound)
            entry = next((item for item in build_reference_index(bound).get(args.finding_id, []) if item["type"] == "finding" and item.get("revision") == args.revision), None)
            if entry is None:
                raise RecordError("finding_revision_not_found", f"{args.finding_id}:{args.revision}")
            finding = load_json(bound / entry["path"])
            result = {"valid": True, "finding_id": args.finding_id, "revision": args.revision, "claim_tuple_hash": claim_tuple_hash(finding), "markdown": render_claim_proof(finding)}
        except RecordError as exc:
            pending_error = exc
        except (OSError, ValueError) as exc:
            pending_error = RecordError("proof_render_unavailable", "proof source could not be read")
        _require_bound_source_current(engagement, bound, label="proof")
        if pending_error is not None:
            raise pending_error
        assert result is not None
        emit(result)
        return 0


def command_check_resume(args: argparse.Namespace) -> int:
    engagement = args.engagement.absolute()
    with bound_engagement_source(engagement) as bound_engagement:
        expected = assert_resume_current(bound_engagement)
        try:
            root_fd = int(bound_engagement.parts[3])
            opened = os.fstat(root_fd)
            named = os.stat(engagement, follow_symlinks=False)
        except (OSError, ValueError, IndexError) as exc:
            raise RecordError(
                "engagement_source_changed", "resume source changed"
            ) from exc
        if (
            stat.S_ISLNK(named.st_mode)
            or not stat.S_ISDIR(named.st_mode)
            or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
            or inspect_quarantine(bound_engagement)["quarantined"]
            or inspect_quarantine(engagement)["quarantined"]
        ):
            raise RecordError("engagement_source_changed", "resume source changed")
        emit({"ok": True, "event_count": expected["event_count"], "ledger_hash": expected["ledger_hash"]})
        return 0


def self_test() -> int:
    from run_engagement_self_test import run_self_test
    return run_self_test(globals())


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--self-test", action="store_true", help="run hermetic schema/record tests")
    subcommands = result.add_subparsers(dest="command")
    validate = subcommands.add_parser("validate", help="validate schemas, records, fixtures, or a read-only legacy inventory")
    validate.add_argument("--schema", choices=["finding-v3", "attempt-v2", "artifact", "review", "engagement-event", "state-snapshot", "environment-preflight", "environment-preflight-v2", "report-manifest", "memory-disposition", "migration-manifest", "migration-artifact-review", "research-telemetry", "historical-case-manifest", "retrospective-evaluation", "ab-preregistration", "ab-study-evidence", "ab-readiness-report", "finding-v2-legacy"])
    validate.add_argument("--file", type=Path)
    validate.add_argument("--engagement", type=Path, help="engagement root used to resolve record references")
    validate.add_argument("--schema-only", action="store_true", help="fixture/schema work only; skip engagement reference resolution")
    validate.add_argument("--schema-documents", action="store_true")
    validate.add_argument("--fixture-suite", nargs="?", const=True)
    validate.add_argument("--legacy-root", type=Path)
    validate.add_argument("--output", type=Path)

    identity = subcommands.add_parser("runtime-identity", help="print OS-process-bound local provenance values")
    identity.add_argument("--role", choices=["broker", "operator", "orchestrator"], required=True)

    init = subcommands.add_parser("init", help="bind a signed scope and initialize the append-only record kernel")
    init.add_argument("--engagement", type=Path, required=True)
    init.add_argument("--recorded-at", help="explicit timestamp for deterministic replay/tests")
    ledger_health = subcommands.add_parser("ledger-health", help="report whether an engagement ledger is reducible without changing it")
    ledger_health.add_argument("--engagement", type=Path, required=True)
    for name in ("quarantine-ledger", "clear-ledger-quarantine"):
        command = subcommands.add_parser(name, help=("operator-sign a target-local evidence quarantine" if name == "quarantine-ledger" else "operator-sign removal of a quarantine after the underlying ledger proves healthy"))
        command.add_argument("--engagement", type=Path, required=True)
        command.add_argument("--operator-id", required=True)
        command.add_argument("--reason", required=True, choices=sorted(QUARANTINE_REASONS))
        command.add_argument("--recorded-at", required=True)
    for name in ("append-event", "append-attempt"):
        command = subcommands.add_parser(name, help=f"trusted {name} operation")
        command.add_argument("--engagement", type=Path, required=True)
        command.add_argument("--file", type=Path, required=True)
    reopen_coverage = subcommands.add_parser("reopen-coverage", help="reopen terminal coverage for a recorded orchestrator reason")
    reopen_coverage.add_argument("--engagement", type=Path, required=True)
    reopen_coverage.add_argument("--recorded-at", required=True)
    reopen_coverage.add_argument("--reason", required=True)
    reopen_coverage.add_argument("--actor-id", required=True)
    reopen_coverage.add_argument("--session-id", required=True)
    for name in ("operator-stop", "operator-resume"):
        command = subcommands.add_parser(name, help=f"record an operator decision to {'park' if name == 'operator-stop' else 'resume'} the work queue")
        command.add_argument("--engagement", type=Path, required=True)
        command.add_argument("--operator-id", required=True)
        command.add_argument("--session-id", required=True)
        command.add_argument("--recorded-at", required=True)
        command.add_argument("--reason", required=True)
    override_ending = subcommands.add_parser("override-ending", help="operator-sign one exact terminal transition with blocking work left on the record")
    override_ending.add_argument("--engagement", type=Path, required=True)
    override_ending.add_argument("--terminal-kind", choices=["coverage", "engagement"], required=True)
    override_ending.add_argument("--status", choices=["coverage_dry", "budget_bounded", "blocked", "closed"], required=True)
    override_ending.add_argument("--operator-id", required=True)
    override_ending.add_argument("--session-id", required=True)
    override_ending.add_argument("--recorded-at", required=True)
    override_ending.add_argument("--reason", required=True)
    override_ending.add_argument("--coverage-review-ref")
    override_ending.add_argument("--disposed-count", type=int)
    override_ending.add_argument("--enumerated-count", type=int)
    override_ending.add_argument("--corpus-enumeration-ref")
    classify_artifact = subcommands.add_parser("classify-artifact", help="classify a planned artifact before any bytes are created")
    classify_artifact.add_argument("--engagement", type=Path, required=True)
    classify_artifact.add_argument("--metadata", type=Path, required=True)
    classify_artifact.add_argument("--source", type=Path, help="pre-existing source for Notebook copies; forbidden for Zone-2")
    classify_artifact.add_argument("--planned-sha256", help="planned Zone-2 bytes digest; bytes must not exist yet")
    classify_artifact.add_argument("--planned-size", type=int)
    classify_artifact.add_argument("--relative-path", type=Path, required=True)
    classify_artifact.add_argument("--recorded-at", required=True)
    classify_artifact.add_argument("--actor-role", choices=["broker"], required=True)
    classify_artifact.add_argument("--actor-id", required=True)
    classify_artifact.add_argument("--session-id", required=True)
    classify_artifact.add_argument("--model")
    classify_artifact.add_argument("--provider")
    classify_artifact.add_argument("--tool-version", action="append", default=[])
    classify_artifact.add_argument("--output", type=Path)
    create_artifact = subcommands.add_parser("create-artifact", help="create exact digest-bound Zone-2 bytes only after fresh confirmation")
    create_artifact.add_argument("--engagement", type=Path, required=True)
    create_artifact.add_argument("--metadata", type=Path, required=True)
    create_artifact.add_argument("--classification", type=Path, required=True)
    create_artifact.add_argument("--actor-id", required=True)
    create_artifact.add_argument("--session-id", required=True)
    propose_scope = subcommands.add_parser("propose-scope", help="preserve an unattested scope amendment draft without changing authority")
    propose_scope.add_argument("--engagement", type=Path, required=True); propose_scope.add_argument("--draft", type=Path, required=True); propose_scope.add_argument("--actor-id", required=True); propose_scope.add_argument("--session-id", required=True); propose_scope.add_argument("--recorded-at", required=True); propose_scope.add_argument("--reason", required=True)
    reattest_scope = subcommands.add_parser("reattest-scope", help="activate one signed scope draft through exact async authority")
    reattest_scope.add_argument("--engagement", type=Path, required=True); reattest_scope.add_argument("--draft", type=Path, required=True); reattest_scope.add_argument("--operator-id", required=True); reattest_scope.add_argument("--recorded-at", required=True); reattest_scope.add_argument("--reason", required=True); reattest_scope.add_argument("--authority-request-id", required=True); reattest_scope.add_argument("--lane-id", required=True); reattest_scope.add_argument("--executor-id", required=True); reattest_scope.add_argument("--session-id", required=True)
    migrate_kernel = subcommands.add_parser("migrate-kernel", help="upgrade a decision-0005 engagement to decision-0006 in place (operator-console-signed, reconciles orphans)")
    migrate_kernel.add_argument("--engagement", type=Path, required=True); migrate_kernel.add_argument("--draft", type=Path, required=True); migrate_kernel.add_argument("--operator-id", required=True); migrate_kernel.add_argument("--recorded-at", required=True); migrate_kernel.add_argument("--reason", required=True); migrate_kernel.add_argument("--executor-id", required=True); migrate_kernel.add_argument("--session-id", required=True); migrate_kernel.add_argument("--attest-synthetic", action="store_true", help="operator-confirm that secret-flagged evidence files are synthetic test references and register them")
    record_cleanup = subcommands.add_parser("record-cleanup", help="apply one exact operator-approved cleanup transition")
    record_cleanup.add_argument("--engagement", type=Path, required=True); record_cleanup.add_argument("--file", type=Path, required=True); record_cleanup.add_argument("--operator-id", required=True); record_cleanup.add_argument("--recorded-at", required=True); record_cleanup.add_argument("--reason", required=True); record_cleanup.add_argument("--authority-request-id", required=True); record_cleanup.add_argument("--lane-id", required=True); record_cleanup.add_argument("--executor-id", required=True); record_cleanup.add_argument("--session-id", required=True)
    record_prior = subcommands.add_parser("record-operator-prior", help="apply one exact operator-approved prior without establishing truth")
    record_prior.add_argument("--engagement", type=Path, required=True); record_prior.add_argument("--prior-id", required=True); record_prior.add_argument("--prior-statement", required=True); record_prior.add_argument("--strength", choices=["weak", "strong"], required=True); record_prior.add_argument("--operator-id", required=True); record_prior.add_argument("--recorded-at", required=True); record_prior.add_argument("--reason", required=True); record_prior.add_argument("--authority-request-id", required=True); record_prior.add_argument("--lane-id", required=True); record_prior.add_argument("--executor-id", required=True); record_prior.add_argument("--session-id", required=True)
    reopen = subcommands.add_parser("reopen", help="apply one exact operator-approved engagement reopening")
    reopen.add_argument("--engagement", type=Path, required=True); reopen.add_argument("--operator-id", required=True); reopen.add_argument("--recorded-at", required=True); reopen.add_argument("--reason", required=True); reopen.add_argument("--authority-request-id", required=True); reopen.add_argument("--lane-id", required=True); reopen.add_argument("--executor-id", required=True); reopen.add_argument("--session-id", required=True)
    request_authority = subcommands.add_parser("request-authority", help="append one digest-bound lane-local authority request")
    request_authority.add_argument("--engagement", type=Path, required=True); request_authority.add_argument("--request-id", required=True); request_authority.add_argument("--action-kind", required=True); request_authority.add_argument("--action-file", type=Path, required=True); request_authority.add_argument("--lane-id", required=True); request_authority.add_argument("--actor-role", choices=["broker"], required=True); request_authority.add_argument("--actor-id", required=True); request_authority.add_argument("--session-id", required=True); request_authority.add_argument("--recorded-at", required=True); request_authority.add_argument("--expires-at", required=True); request_authority.add_argument("--reason", required=True)
    resolve_authority = subcommands.add_parser("resolve-authority", help="operator-resolve one exact pending authority request")
    resolve_authority.add_argument("--engagement", type=Path, required=True); resolve_authority.add_argument("--request-id", required=True); resolve_authority.add_argument("--resolution", choices=["approved", "rejected", "expired", "superseded"], required=True); resolve_authority.add_argument("--operator-id", required=True); resolve_authority.add_argument("--session-id", required=True); resolve_authority.add_argument("--recorded-at", required=True); resolve_authority.add_argument("--reason", required=True)
    settle_revision = subcommands.add_parser("settle-approved-revision", help="atomically apply one live approved finding revision or record its objective expiry")
    settle_revision.add_argument("--engagement", type=Path, required=True); settle_revision.add_argument("--file", type=Path, required=True); settle_revision.add_argument("--resolve-review", action="append"); settle_revision.add_argument("--operator-id", required=True); settle_revision.add_argument("--recorded-at", required=True); settle_revision.add_argument("--authority-request-id", required=True); settle_revision.add_argument("--lane-id", required=True); settle_revision.add_argument("--executor-id", required=True); settle_revision.add_argument("--session-id", required=True)
    confirm_zone2 = subcommands.add_parser("confirm-zone2", help="record one fresh operator confirmation before one Zone-2 artifact is created")
    confirm_zone2.add_argument("--engagement", type=Path, required=True)
    confirm_zone2.add_argument("--file", type=Path, required=True)
    confirm_zone2.add_argument("--plan", type=Path, required=True)
    confirm_zone2.add_argument("--operator-id", required=True)
    artifact = subcommands.add_parser("register-artifact", help="hash and register a pre-classified immutable evidence file")
    artifact.add_argument("--engagement", type=Path, required=True)
    artifact.add_argument("--file", type=Path, required=True)
    artifact.add_argument("--metadata", type=Path, required=True)
    artifact.add_argument("--classification", type=Path, required=True)
    repair = subcommands.add_parser("repair-ledger-tail", help="operator-only quarantine of an uncommitted partial JSONL tail")
    repair.add_argument("--engagement", type=Path, required=True)
    repair.add_argument("--ledger", choices=["event", "attempt", "artifact"], required=True)
    repair.add_argument("--operator-id", required=True)
    repair.add_argument("--reason", required=True)
    repair.add_argument("--recorded-at", required=True)
    repair.add_argument("--authority-request-id", required=True); repair.add_argument("--lane-id", required=True); repair.add_argument("--executor-id", required=True); repair.add_argument("--session-id", required=True)
    telemetry = subcommands.add_parser("export-telemetry", help="derive complete-funnel telemetry without changing routing")
    telemetry.add_argument("--engagement", type=Path, required=True); telemetry.add_argument("--output", type=Path)
    telemetry_score = subcommands.add_parser("score-telemetry", help="score telemetry or eligible calibration offline")
    telemetry_score.add_argument("--file", type=Path, required=True)
    memory = subcommands.add_parser("record-memory", help="operator-review and commit one terminal memory disposition without modifying Plane-1")
    memory.add_argument("--engagement", type=Path, required=True); memory.add_argument("--file", type=Path, required=True); memory.add_argument("--operator-id", required=True); memory.add_argument("--authority-request-id", required=True); memory.add_argument("--lane-id", required=True); memory.add_argument("--executor-id", required=True); memory.add_argument("--session-id", required=True)
    close = subcommands.add_parser("close", help="operator-only cleanup, coverage, report, and memory closure gate")
    close.add_argument("--engagement", type=Path, required=True); close.add_argument("--operator-id", required=True); close.add_argument("--reason", required=True); close.add_argument("--recorded-at", required=True); close.add_argument("--authority-request-id", required=True); close.add_argument("--lane-id", required=True); close.add_argument("--executor-id", required=True); close.add_argument("--session-id", required=True)
    record_review_parser = subcommands.add_parser("record-review", help="atomically commit one independent review and its typed notebook event")
    record_review_parser.add_argument("--engagement", type=Path, required=True); record_review_parser.add_argument("--file", type=Path, required=True); record_review_parser.add_argument("--event", type=Path, required=True); record_review_parser.add_argument("--actor-id", required=True); record_review_parser.add_argument("--session-id", required=True); record_review_parser.add_argument("--signature", type=Path, required=True); record_review_parser.add_argument("--allowed-signers", type=Path, required=True); record_review_parser.add_argument("--attest-synthetic", action="store_true", help="operator-confirm that secret-flagged review input references are synthetic test names and record the review")

    review_preflight_parser = subcommands.add_parser("review-preflight", help="apply an approved operator review to immutable preflight evidence")
    review_preflight_parser.add_argument("--engagement", type=Path, required=True); review_preflight_parser.add_argument("--preflight-id", required=True); review_preflight_parser.add_argument("--verdict", choices=["accepted", "rejected"], required=True); review_preflight_parser.add_argument("--reason", required=True); review_preflight_parser.add_argument("--operator-id", required=True); review_preflight_parser.add_argument("--recorded-at", required=True); review_preflight_parser.add_argument("--authority-request-id", required=True); review_preflight_parser.add_argument("--lane-id", required=True); review_preflight_parser.add_argument("--executor-id", required=True); review_preflight_parser.add_argument("--session-id", required=True)

    preflight = subcommands.add_parser("preflight", help="record offline Git/package/local-runtime identity and safety state")
    preflight.add_argument("--engagement", type=Path, required=True); preflight.add_argument("--preflight-id", required=True); preflight.add_argument("--mode", choices=["git", "package", "local_runtime"], required=True); preflight.add_argument("--target", type=Path, required=True); preflight.add_argument("--expected-identity", required=True); preflight.add_argument("--runtime", type=Path, required=True); preflight.add_argument("--reproduction-argv", required=True, help="JSON array; recorded but never executed by preflight"); preflight.add_argument("--actor-role", choices=["broker"], required=True); preflight.add_argument("--actor-id", required=True); preflight.add_argument("--session-id", required=True); preflight.add_argument("--model"); preflight.add_argument("--provider"); preflight.add_argument("--tool-version", action="append", default=[]); preflight.add_argument("--recorded-at", required=True); preflight.add_argument("--advisory-zone", choices=["clear_local", "review_required", "unknown"], default="clear_local"); preflight.add_argument("--credentials-present", action="store_true"); preflight.add_argument("--account-label", action="append", default=[]); preflight.add_argument("--configuration-file", type=Path, action="append", default=[]); preflight.add_argument("--endpoint-identity"); preflight.add_argument("--account-role"); preflight.add_argument("--feature-flag", action="append", default=[])
    migrate = subcommands.add_parser("migrate", help="read-only legacy inventory or signed-operator migration proposal")
    migrate.add_argument("--root", type=Path, default=Path(".")); migrate.add_argument("--output", type=Path); migrate.add_argument("--propose-engagement"); migrate.add_argument("--dry-run-engagement"); migrate.add_argument("--migration-dir",type=Path); migrate.add_argument("--apply-proposal", type=Path); migrate.add_argument("--destination", type=Path); migrate.add_argument("--artifact-review",type=Path); migrate.add_argument("--operator-id"); migrate.add_argument("--recorded-at"); migrate.add_argument("--authority-engagement", type=Path); migrate.add_argument("--authority-request-id"); migrate.add_argument("--lane-id"); migrate.add_argument("--executor-id"); migrate.add_argument("--session-id")
    revise = subcommands.add_parser("revise-finding", help="commit one contiguous operator-authorized finding revision")
    revise.add_argument("--engagement", type=Path, required=True); revise.add_argument("--file", type=Path, required=True); revise.add_argument("--resolve-review", action="append", default=None); revise.add_argument("--operator-id", required=True); revise.add_argument("--recorded-at", required=True); revise.add_argument("--authority-request-id", required=True); revise.add_argument("--lane-id", required=True); revise.add_argument("--executor-id", required=True); revise.add_argument("--session-id", required=True)

    accept = subcommands.add_parser("accept-report", help="operator review and acceptance of a current revision-bound report")
    accept.add_argument("--engagement", type=Path, required=True); accept.add_argument("--report-id", required=True); accept.add_argument("--operator-id", required=True); accept.add_argument("--reason", required=True); accept.add_argument("--recorded-at", required=True); accept.add_argument("--authority-request-id", required=True); accept.add_argument("--lane-id", required=True); accept.add_argument("--executor-id", required=True); accept.add_argument("--session-id", required=True)
    submission = subcommands.add_parser("record-submission", help="record separate operator-authored external submission text")
    submission.add_argument("--engagement", type=Path, required=True); submission.add_argument("--report-id", required=True); submission.add_argument("--file", type=Path, required=True); submission.add_argument("--program", required=True); submission.add_argument("--operator-id", required=True); submission.add_argument("--recorded-at", required=True); submission.add_argument("--authority-request-id", required=True); submission.add_argument("--lane-id", required=True); submission.add_argument("--executor-id", required=True); submission.add_argument("--session-id", required=True)
    report = subcommands.add_parser("generate-report", help="operator-only generation of a revision-bound internal report")
    report.add_argument("--engagement", type=Path, required=True); report.add_argument("--finding-id", required=True); report.add_argument("--revision", type=int, required=True); report.add_argument("--include-claim", action="append", default=[]); report.add_argument("--omit-claim", action="append", default=[]); report.add_argument("--operator-id", required=True); report.add_argument("--recorded-at", required=True); report.add_argument("--authority-request-id", required=True); report.add_argument("--lane-id", required=True); report.add_argument("--executor-id", required=True); report.add_argument("--session-id", required=True)
    proof = subcommands.add_parser("render-proof", help="render the exact structured claim-to-proof matrix for a committed finding revision")
    proof.add_argument("--engagement", type=Path, required=True)
    proof.add_argument("--finding-id", required=True)
    proof.add_argument("--revision", type=int, required=True)
    for name in ("next", "list", "gate"):
        command = subcommands.add_parser(name, help=f"read the reducer-owned work queue ({name})")
        command.add_argument("--engagement", type=Path, required=True)
    for name in ("reduce", "render", "check-resume", "check-completion-claims"):
        command = subcommands.add_parser(name, help=f"{name} deterministic engagement state")
        command.add_argument("--engagement", type=Path, required=True)
    return result


def _command_handlers() -> dict[str, object]:
    return {
            "validate": command_validate,
            "runtime-identity": command_runtime_identity,
            "init": command_init,
            "ledger-health": command_ledger_health,
            "quarantine-ledger": command_quarantine_ledger,
            "clear-ledger-quarantine": command_clear_ledger_quarantine,
            "append-event": command_append_event,
            "append-attempt": command_append_attempt,
            "classify-artifact": command_classify_artifact,
            "create-artifact": command_create_artifact,
            "propose-scope": command_propose_scope,
            "reattest-scope": command_reattest_scope,
            "record-cleanup": command_record_cleanup,
            "record-operator-prior": command_record_operator_prior,
            "reopen": command_reopen,
            "reopen-coverage": command_reopen_coverage,
            "operator-stop": command_operator_stop,
            "operator-resume": command_operator_resume,
            "override-ending": command_override_ending,
            "request-authority": command_request_authority,
            "resolve-authority": command_resolve_authority,
            "settle-approved-revision": command_settle_approved_revision,
            "confirm-zone2": command_confirm_zone2,
            "register-artifact": command_register_artifact,
            "repair-ledger-tail": command_repair_tail,
            "next": command_queue_inspection,
            "list": command_queue_inspection,
            "gate": command_queue_inspection,
            "reduce": command_reduce,
            "render": command_render,
            "check-completion-claims": command_check_completion_claims,
            "preflight": command_preflight,
            "record-review": command_record_review,
            "review-preflight": command_review_preflight,
            "record-memory": command_record_memory,
            "export-telemetry": command_export_telemetry,
            "score-telemetry": command_score_telemetry,
            "close": command_close,
            "migrate": command_migrate,
            "migrate-kernel": command_migrate_kernel,
            "revise-finding": command_revise_finding,
            "accept-report": command_accept_report,
            "record-submission": command_record_submission,
            "generate-report": command_generate_report,
            "render-proof": command_render_proof,
            "check-resume": command_check_resume,
        }


def _dispatch_parsed_command(
    args: argparse.Namespace,
    *,
    arguments: list[str],
    admission_already_consumed: bool,
) -> int:
    commands = _command_handlers()
    if args.command not in commands:
        parser().print_help()
        return 2
    engagement_argument = getattr(args, "engagement", None)
    if engagement_argument is not None and args.command not in {
        "ledger-health",
        "quarantine-ledger",
        "clear-ledger-quarantine",
        "check-completion-claims",
        *QUEUE_INSPECTION_COMMANDS,
    }:
        require_not_quarantined(engagement_argument.absolute())
    matrix = load_capability_matrix()
    if args.command not in matrix["commands"]:
        raise RecordError("operation_unclassified", f"command:{args.command}")
    if matrix["commands"][args.command]["tier"] not in {"event_dispatch", "variant_dispatch"}:
        classify_command(args.command, matrix=matrix)
    if engagement_argument is not None and not admission_already_consumed:
        consume_action_admission(
            engagement=engagement_argument,
            command=args.command,
            arguments=arguments,
            namespace=args,
        )
    handler = commands[args.command]
    return handler(args)  # type: ignore[operator]


def execute_broker_command(
    *,
    command: str,
    arguments: list[str],
    admitted_documents: dict[str, dict[str, object]],
    authenticated_runtime: dict[str, object],
) -> tuple[int, bytes]:
    """Execute one parent-admitted mutation without exposing authority to the model process."""

    output = bytearray()
    token = _EMIT_BUFFER.set(output)
    runtime_token = _AUTHENTICATED_RUNTIME.set(copy.deepcopy(authenticated_runtime))
    try:
        try:
            args = parser().parse_args([command, *arguments])
            setattr(args, "_driver_admitted_documents", copy.deepcopy(admitted_documents))
            setattr(args, "_driver_authenticated_runtime", copy.deepcopy(authenticated_runtime))
            returncode = _dispatch_parsed_command(
                args,
                arguments=arguments,
                admission_already_consumed=True,
            )
        except RecordError as exc:
            if command in QUEUE_INSPECTION_COMMANDS:
                emit(queue_command_error_payload(command, exc))
            else:
                emit({"valid": False, "error": exc.as_dict()})
            returncode = 1
        return returncode, bytes(output)
    finally:
        _AUTHENTICATED_RUNTIME.reset(runtime_token)
        _EMIT_BUFFER.reset(token)


def main() -> int:
    args = parser().parse_args()
    try:
        if args.self_test:
            return self_test()
        engagement_argument = getattr(args, "engagement", None)
        if engagement_argument is not None and isinstance(args.command, str):
            forwarded = forward_action_to_broker(
                command=args.command,
                arguments=sys.argv[2:],
            )
            if forwarded is not None:
                returncode, output = forwarded
                sys.stdout.buffer.write(output)
                return returncode
        return _dispatch_parsed_command(
            args,
            arguments=sys.argv[2:],
            admission_already_consumed=False,
        )
    except RecordError as exc:
        if getattr(args, "command", None) in QUEUE_INSPECTION_COMMANDS:
            emit(queue_command_error_payload(args.command, exc))
        else:
            emit({"valid": False, "error": exc.as_dict()})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
