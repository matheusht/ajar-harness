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
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack, nullcontext
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from pathlib import Path

from engagement_records import (
    RecordError,
    _reject_duplicate_pairs,
    build_reference_index,
    build_registry,
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
    validate_reference_fixture_suite,
    validate_schema_documents,
    validate_record_with_references,
    validate_record_references,
    write_canonical_json,
)
from engagement_state import (
    WORK_QUEUE_CLASS_ORDER,
    WORK_QUEUE_RULES,
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
    compute_work_queue,
    compute_record_hash,
    compute_review_input_hash,
    engagement_may_end,
    finding_revision_lane_id,
    hypothesis_dispositions_hash,
    bound_engagement_lock,
    bound_engagement_source,
    engagement_lock,
    find_engagement_root,
    initialize_engagement,
    materialize_ledger_record,
    persist_scope_snapshot,
    project_current_terminal_work_state,
    project_terminal_work_state,
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
    _filing_blocking_review_error,
    register_artifact,
    _register_legacy_artifact,
    repair_ledger_tail,
    write_snapshot,
    _scope_metadata,
)
from engagement_views import assert_views_current, render_views, write_views
from environment_preflight import collect_preflight as collect_agent_preflight, _collect_legacy_preflight, review_preflight
from finding_review import claim_tuple_hash, render_claim_proof
from ledger_health import probe_ledger_health
from memory_disposition import _validate_promotable_abstraction, close_engagement, record_memory_disposition
from completion_claims import assert_completion_claims_clear, assert_completion_claims_clear_bound, assert_completion_claims_token_current_bound
from reporting import accept_report, generate_report, record_submission
from research_telemetry import _remove_published_output, export_telemetry, score_telemetry
from decision6_capabilities import artifact_variant, classify_command, classify_event, load_capability_matrix, require_actor
from engagement_quarantine import QUARANTINE_REASONS, _open_directory, _require_bound_parent_safe, atomic_publish_offline_tree, atomic_write_offline, clear_marker_exact, create_marker_exclusive, inspect_quarantine, quarantined_ancestor, read_safe_offline_file, read_safe_offline_tree, require_safe_offline_input, require_safe_offline_output
from work_queue_actions import (
    QUEUE_INSPECTION_COMMANDS,
    decorate_work_queue_item,
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
        fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd)
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
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)); data = bytearray()
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
    if attestation is None or attestation.get("payload",{}).get("record_kernel")!="decision-0006-v1": raise RecordError("decision6_kernel_not_selected","signed scope must select decision-0006-v1 for autonomous broker or async-authority commands")


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
    signer_match = re.search(rb"Operator allowed signers SHA256:\s*(sha256:[0-9a-f]{64})", draft_bytes)
    signature_name = os.environ.get("HARNESS_OPERATOR_SIGNATURE_FILE")
    signers_name = os.environ.get("HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE")
    if signer_match is None or not signature_name or not signers_name:
        raise RecordError("operator_signature_required", "migrate-kernel requires an operator SSH signature bound in the draft scope")
    challenge = {"schema_version": 1, "namespace": "llm-redteam-harness-operator-v1",
                 "engagement_id": engagement.name, "scope_hash": draft_meta["scope_hash"],
                 "source_scope_hash": prior["payload"]["scope_hash"], "ledger_hash": events[-1]["record_hash"],
                 "operation": f"migrate-kernel:{draft_meta['scope_hash']}", "operator_id": args.operator_id}
    challenge_bytes = canonical_json_bytes(challenge)
    challenge_digest = sha256_bytes(challenge_bytes)
    try:
        signature_bytes, _ = _read_regular_file_once(Path(signature_name))
        signers_bytes, _ = _read_regular_file_once(Path(signers_name))
    except (OSError, RecordError) as exc:
        raise RecordError("operator_signature_invalid", challenge_digest, [str(exc)]) from exc
    if sha256_bytes(signers_bytes) != signer_match.group(1).decode():
        raise RecordError("operator_signature_invalid", challenge_digest)
    with tempfile.TemporaryDirectory(prefix="migrate-kernel-signature-") as temporary:
        temporary_root = Path(temporary)
        signature_copy = temporary_root / "operator.sig"
        signers_copy = temporary_root / "allowed_signers"
        signature_copy.write_bytes(signature_bytes)
        signers_copy.write_bytes(signers_bytes)
        result = subprocess.run(
            ["/usr/bin/ssh-keygen", "-Y", "verify", "-f", str(signers_copy), "-I", args.operator_id,
             "-n", "llm-redteam-harness-operator-v1", "-s", str(signature_copy)],
            input=challenge_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"}, check=False,
        )
    if result.returncode != 0:
        raise RecordError("operator_signature_invalid", challenge_digest)

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
        from engagement_views import write_views
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
        if action.get("action_kind") == "revise-finding" and action.get("action_version") == 2 and isinstance(action.get("target"), dict):
            locked_events = read_ledger(bound_engagement, "event")
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
        state = reduce_engagement(bound_engagement)
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
    snapshot = reduce_engagement(engagement)
    write_snapshot(engagement, snapshot)
    write_views(engagement, snapshot)
    assert_views_current(engagement, snapshot)
    if read_governed_file(engagement / "state.snapshot.json") != canonical_json_bytes(snapshot):
        raise RecordError("record_review_staging_projection_invalid", str(event.get("event_id", "unknown")))
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
    mapping = {"claim_adjudication": "claim.adjudicated", "coverage": "review.coverage_completed", "regrade": "review.regrade_completed", "pocinator": "review.pocinator_completed", "higher_impact_route": "review.higher_impact_route_completed"}
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
        with tempfile.TemporaryDirectory(prefix="record-review-transaction-") as temporary:
            staged_engagement = Path(temporary) / engagement_id
            _copy_engagement_for_review_staging(
                bound_engagement, staged_engagement, deadline=deadline
            )
            with engagement_lock(staged_engagement) as bound_staged_engagement:
                _apply_record_review_transaction(
                    bound_staged_engagement,
                    relative=relative,
                    data=data,
                    commit=commit,
                    event=event,
                )
        _require_record_review_prewrite_time(deadline, "live commit")
        applied = _apply_record_review_transaction(
            bound_engagement,
            relative=relative,
            data=data,
            commit=commit,
            event=event,
        )
    emit({"valid": True, "review_id": review["review_id"], "event_id": applied["event_id"], "claim_truth_self_accepted": False}); return 0


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
    pre_state = reduce_engagement(engagement); request = pre_state["authority_requests"].get(args.authority_request_id); target = request.get("target") if request else None
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
            or stored_action.get("action_version") != 2
            or stored_action.get("lane_id") != args.lane_id
            or stored_action.get("operator_id") != args.operator_id
            or stored_action.get("file_digest") != digest
            or stored_action.get("target") != target
            or stored_action.get("proposal") != finding
        ):
            raise RecordError("approved_revision_action_record_invalid", str(args.authority_request_id))
        action = stored_action
    else:
        digest = raw_digest
        if explicit_resolutions: raise RecordError("legacy_finding_authority_cannot_bind_resolutions", finding.get("finding_id", "unknown"))
        resolutions = []
        action = _authority_action("revise-finding", lane_id=args.lane_id, executor_id=args.executor_id, session_id=args.session_id, file_digest=digest, operator_id=args.operator_id, recorded_at=args.recorded_at)
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
        if prior_bytes is not None and prior_bytes != data and activated:
            raise RecordError("finding_revision_collision", f"{finding_id}:{revision}")
        repaired_commit_id = None
        if prior_bytes is not None and prior_bytes != data and not activated and existing_commit is not None:
            # Repair an un-activated partial commit: the revision was committed but never activated
            # (no finding.revised event). Overwrite with the corrected bytes and append a NEW commit
            # event under a distinct id recording the corrected digest. The old commit event stays as
            # a historical record of the aborted attempt; the file now matches the repair commit.
            atomic_write(destination, data)
            repaired_commit_id = f"event-{finding_id}-r{revision}-repair-{int(__import__('time').time())}"
        if prior_bytes is None: atomic_write(destination, data)
        commit_id = repaired_commit_id or f"event-{finding_id}-r{revision}-commit"
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


def _run_in_pty(argv: list[str], stdin_text: str) -> str:
    """Run argv attached to a pseudo-TTY and return combined stdout+stderr. Portable across BSD and
    util-linux (unlike `/usr/bin/script`, whose command-invocation syntax differs between them). Used
    only by the self-test to prove an agent-allocated TTY alone cannot satisfy operator authority."""
    import pty, select, errno, time as _time
    master, slave = pty.openpty()
    proc = subprocess.Popen(argv, stdin=slave, stdout=slave, stderr=slave, close_fds=True)
    os.close(slave)
    try: os.write(master, stdin_text.encode())
    except OSError: pass
    chunks = bytearray(); deadline = _time.monotonic() + 30
    while _time.monotonic() < deadline:
        try: ready, _, _ = select.select([master], [], [], 1)
        except (OSError, ValueError): break
        if ready:
            try: data = os.read(master, 4096)
            except OSError as exc:
                if exc.errno == errno.EIO: break   # Linux signals PTY EOF as EIO
                raise
            if not data: break
            chunks.extend(data)
        elif proc.poll() is not None:
            break
    try: os.close(master)
    except OSError: pass
    if proc.poll() is None: proc.kill()
    proc.wait()
    return chunks.decode(errors="replace")


def state_self_test() -> list[tuple[str, bool, str]]:
    append_event = _append_kernel_event
    collect_preflight = _collect_legacy_preflight
    checks: list[tuple[str, bool, str]] = []

    def test_corpus_documents(*, row_count: int, frozen_at: str) -> tuple[bytes, bytes]:
        from corpus_enumeration import CAVEAT, COLUMNS
        rows = [
            ["enumerated", "fixture", "1.0.0", "a" * 40, f"entry-{index}.js", "declared", f"{index + 1:064x}"]
            for index in range(row_count)
        ]
        tsv_bytes = ("\n".join([CAVEAT, "\t".join(COLUMNS), *("\t".join(row) for row in rows)]) + "\n").encode()
        raw_digest = sha256_bytes(tsv_bytes).removeprefix("sha256:")
        linked = {"path": "corpus-enumeration.tsv", "sha256": raw_digest}
        manifest = {
            "schema_version": 1,
            "artifact_type": "corpus-enumeration",
            "frozen_at": frozen_at,
            "generated_by": {
                "tool": "tools/corpus_enumeration.py",
                "tool_sha256": "4" * 64,
                "mode": "syntactic",
                "model_involvement": False,
                "parser_versions": {"tree-sitter": "test", "tree-sitter-javascript": "test", "tree-sitter-typescript": "test"},
            },
            "granularity": ["package", "entrypoint"],
            "columns": COLUMNS,
            "coverage_semantics": {"closes_on": "visitation", "does_not_establish": "understanding", "necessary_for_coverage": True, "sufficient_for_coverage": False},
            "artifact": {**linked, "row_count": row_count, "package_count": 1},
            "source": {"pins_path": "package-pins.tsv", "tarballs_path": "tarballs"},
            "frozen_inputs_base": "manifest",
            "frozen_inputs": {
                "corpus-enumeration": linked,
                "package-pins": {"path": "package-pins.tsv", "sha256": "5" * 64},
                "enumerator": {"path": "../../tools/corpus_enumeration.py", "sha256": "4" * 64},
                "schema": {"path": "../../schemas/corpus-enumeration.schema.json", "sha256": "6" * 64},
                "tarball:0000": {"path": "tarballs/fixture.tgz", "sha256": "7" * 64},
            },
        }
        return tsv_bytes, canonical_json_bytes(manifest)

    def scope_with_corpus_pin(scope_text: str, manifest_bytes: bytes) -> str:
        pin = f"- Frozen corpus enumeration SHA256: `{sha256_bytes(manifest_bytes)}`\n"
        return scope_text.replace("## Authorization\n", "## Authorization\n" + pin, 1)

    def register_test_corpus(target: Path, *, row_count: int = 5, created_at: str = "2026-07-10T00:02:00Z", documents: tuple[bytes, bytes] | None = None) -> tuple[str, str]:
        state = reduce_engagement(target)
        suffix = re.sub(r"[^A-Za-z0-9._:-]+", "-", state["engagement_id"])
        tsv_ref = f"artifact-corpus-tsv-{suffix}"
        manifest_ref = f"artifact-corpus-manifest-{suffix}"
        evidence = target / "evidence"
        evidence.mkdir(exist_ok=True)
        tsv_bytes, manifest_bytes = documents or test_corpus_documents(row_count=row_count, frozen_at=created_at)
        tsv_path = evidence / "corpus-enumeration.tsv"
        tsv_path.write_bytes(tsv_bytes)
        common = {
            "schema_version": 1,
            "engagement_id": state["engagement_id"],
            "created_at": created_at,
            "producer": {"role": "operator", "id": "operator-selftest"},
            "acquisition_method": "generated_local",
            "target_refs": [],
            "environment_ref": None,
            "sensitivity": "internal",
            "redaction_status": "not_needed",
            "contains_executable_capability": False,
            "advisory_zone": "clear_local",
            "escalation_confirmation_event_ref": None,
            "cleanup_obligation_ref": None,
            "supersedes_artifact_id": None,
        }
        _register_legacy_artifact(target, tsv_path, {**common, "artifact_id": tsv_ref, "media_type": "text/tab-separated-values"})
        manifest_path = evidence / "corpus-enumeration.freeze.json"
        manifest_path.write_bytes(manifest_bytes)
        _register_legacy_artifact(target, manifest_path, {**common, "artifact_id": manifest_ref, "media_type": "application/json"})
        return manifest_ref, tsv_ref

    with tempfile.TemporaryDirectory(prefix="engagement-state-selftest-") as tmp:
        root = Path(tmp).resolve(); reviewer_key = root / "reviewer-ed25519"; subprocess.run(["/usr/bin/ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(reviewer_key)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); public_parts = reviewer_key.with_suffix(".pub").read_text().split(); allowed_signers_path = root / "allowed-signers"; allowed_signers_path.write_text(f"reviewer-external-canonical {public_parts[0]} {public_parts[1]}\noperator-selftest {public_parts[0]} {public_parts[1]}\n"); allowed_signers_digest = sha256_file(allowed_signers_path)
        engagement = root / "eng-selftest"
        engagement.mkdir()
        scope = f"""# Scope — self-test

## Surfaces in scope
- Local fixture only.
## Benign safe-objective set
- Deterministic ledger test.
## Escalation ceiling
- Local records only.
## Impact-demo authorization
- impact_demo_authorized: `yes`
- zone2_authorized_categories: `zone2_artifact_creation`
- zone2_escalation_ceiling: `artifact_creation`
- zone2_containment: `synthetic temporary-directory fixture`
## Accounts / fixtures
- None.
## Independent reviewer identity
- Reviewer allowed signers SHA256: {allowed_signers_digest}
## Authorization
- Operator allowed signers SHA256: {allowed_signers_digest}
- Operator: operator-selftest
- Date: 2026-07-10
- Signed: [x]
- Record kernel: `decision-0006-v1`
"""
        (engagement / "scope.md").write_text(scope, encoding="utf-8")
        init_cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), "init", "--engagement", str(engagement), "--recorded-at", "2026-07-10T00:00:00Z"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        try: init_console_gate = init_cli.returncode != 0 and json.loads(init_cli.stdout)["error"]["code"] == "operator_signature_required"
        except (json.JSONDecodeError, KeyError): init_console_gate = False
        checks.append(("fresh public init reaches the cryptographic operator gate without requiring a prior ledger", init_console_gate, init_cli.stdout + init_cli.stderr))
        pty_output=_run_in_pty([sys.executable,str(Path(__file__).resolve()),"init","--engagement",str(engagement),"--recorded-at","2026-07-10T00:00:00Z"],"initialize-engagement operator-selftest\n");checks.append(("agent-created pseudo-TTY cannot satisfy operator authority without a scoped signature","operator_signature_required" in pty_output and not (engagement/"events.jsonl").exists(),pty_output))
        init_challenge={"schema_version":1,"namespace":"llm-redteam-harness-operator-v1","engagement_id":engagement.name,"scope_hash":sha256_file(engagement/"scope.md"),"ledger_hash":None,"operation":"initialize-engagement:2026-07-10T00:00:00Z","operator_id":"operator-selftest"};init_challenge_path=root/"init-challenge.json";init_challenge_path.write_bytes(canonical_json_bytes(init_challenge));subprocess.run(["/usr/bin/ssh-keygen","-Y","sign","-f",str(reviewer_key),"-n","llm-redteam-harness-operator-v1",str(init_challenge_path)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);signed_env={**os.environ,"HARNESS_OPERATOR_SIGNATURE_FILE":str(init_challenge_path)+".sig","HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE":str(allowed_signers_path)};signed_init=subprocess.run([sys.executable,str(Path(__file__).resolve()),"init","--engagement",str(engagement),"--recorded-at","2026-07-10T00:00:00Z"],env=signed_env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False);checks.append(("public init accepts an exact scoped operator signature",signed_init.returncode==0,signed_init.stdout+signed_init.stderr))
        snapshot = initialize_engagement(engagement, "2026-07-10T00:00:00Z")
        checks.append(("signed-scope init creates one attested event", snapshot["event_count"] == 1 and read_ledger(engagement, "event")[0]["event_type"] == "scope.attested", str(snapshot)))
        initial_event_bytes = (engagement / "events.jsonl").read_bytes()
        initial_reduction = reduce_engagement(engagement)
        expected_coverage_item = {
            "class": "coverage_review_missing",
            "entity": {"type": "engagement", "id": engagement.name, "detail": None},
            "blocking": True,
            "predicate": "coverage is active and no other work queue item exists",
            "closes_when": "coverage is not active",
        }
        checks.append(("reducer projects the work queue without appending a ledger event", initial_reduction["work_queue"] == [expected_coverage_item] and (engagement / "events.jsonl").read_bytes() == initial_event_bytes and len(read_ledger(engagement, "event")) == 1, str(initial_reduction.get("work_queue"))))

        queue_cli_results: dict[str, tuple[subprocess.CompletedProcess[str], dict[str, object]]] = {}
        for queue_command, expected_returncode in (("next", 0), ("list", 0), ("gate", 3)):
            process = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), queue_command, "--engagement", str(engagement)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            try:
                payload = json.loads(process.stdout)
            except json.JSONDecodeError:
                payload = {}
            queue_cli_results[queue_command] = (process, payload)
            common_ok = (
                process.returncode == expected_returncode
                and payload.get("schema_version") == 1
                and payload.get("command") == queue_command
                and payload.get("ok") is True
                and payload.get("engagement_id") == engagement.name
                and payload.get("state_hash") == sha256_bytes(canonical_json_bytes(initial_reduction))
                and payload.get("ledger_hash") == initial_reduction["ledger_hash"]
                and payload.get("source_hashes") == initial_reduction["source_hashes"]
                and payload.get("queue") == {
                    "blocking_count": 1,
                    "control_status": "active",
                    "coverage_status": "active",
                    "decision": "block",
                    "has_blocking_work": True,
                    "nonblocking_count": 0,
                    "should_block": True,
                    "total_count": 1,
                }
                and process.stdout.encode() == canonical_json_bytes(payload)
                and process.stderr == ""
            )
            checks.append((f"{queue_command} emits the canonical read-only queue envelope and documented exit", common_ok, process.stdout + process.stderr))
        next_payload = queue_cli_results["next"][1]
        list_payload = queue_cli_results["list"][1]
        gate_payload = queue_cli_results["gate"][1]
        coverage_action = next_payload.get("item", {}).get("next_action", {})
        checks.append(("next returns exactly the first queue item plus one reducer-valid next action", isinstance(next_payload.get("item"), dict) and next_payload["item"]["class"] == "coverage_review_missing" and coverage_action.get("action_id") == "record_cold_coverage_review" and coverage_action.get("effect") == "conditional" and coverage_action.get("recompute_after") is True and "closure" not in next_payload["item"] and "items" not in next_payload, str(next_payload)))
        checks.append(("list mirrors raw reducer truth in exact order without stale lower-ranked actions, and gate duplicates no item data", [item["class"] for item in list_payload.get("items", [])] == [item["class"] for item in initial_reduction["work_queue"]] and all("next_action" not in item for item in list_payload.get("items", [])) and "items" not in gate_payload, str((list_payload, gate_payload))))
        checks.append(("queue inspection never mutates the ledger", (engagement / "events.jsonl").read_bytes() == initial_event_bytes and len(read_ledger(engagement, "event")) == 1, "queue inspection changed the event ledger"))

        caller_order = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "next", "--engagement", str(engagement), "--class", "awaiting_operator"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        checks.append(("next exposes no caller-controlled class, filter, or ordering knob", caller_order.returncode == 2 and caller_order.stdout == "", caller_order.stdout + caller_order.stderr))

        corrupted = root / "eng-corrupted-queue-cli"
        shutil.copytree(engagement, corrupted)
        (corrupted / "attempts.jsonl").write_text("{\n", encoding="utf-8")
        corrupt_gate = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "gate", "--engagement", str(corrupted)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        try:
            corrupt_payload = json.loads(corrupt_gate.stdout)
        except json.JSONDecodeError:
            corrupt_payload = {}
        checks.append(("gate returns exit 1 with a sanitized machine error for an invalid record", corrupt_gate.returncode == 1 and corrupt_payload.get("schema_version") == 1 and corrupt_payload.get("command") == "gate" and corrupt_payload.get("ok") is False and set(corrupt_payload.get("error", {})) == {"code"} and str(corrupted) not in corrupt_gate.stdout and corrupt_gate.stderr == "", corrupt_gate.stdout + corrupt_gate.stderr))

        unavailable_gate = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "gate", "--engagement", str(root / "missing-engagement")],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        try:
            unavailable_payload = json.loads(unavailable_gate.stdout)
        except json.JSONDecodeError:
            unavailable_payload = {}
        checks.append(("gate keeps an unavailable source machine-readable and path-sanitized", unavailable_gate.returncode == 1 and unavailable_payload == {"schema_version": 1, "command": "gate", "ok": False, "error": {"code": "queue_record_unavailable"}} and str(root) not in unavailable_gate.stdout and unavailable_gate.stderr == "", unavailable_gate.stdout + unavailable_gate.stderr))

        forged_expiry = base_event(
            event_id="event-forged-authority-expiry",
            engagement_id=engagement.name,
            recorded_at="2099-01-01T00:00:00Z",
            actor_role="broker",
            actor_id="broker-forged",
            event_type="authority.expired",
            rationale="A future-dated generic append must not expire authority.",
            payload={"request_id": "request-forged", "request_event_ref": "event-request-forged", "action_digest": "sha256:" + "0" * 64, "expires_at": "2098-01-01T00:00:00Z", "status": "expired"},
            entity_refs=["event-request-forged"],
            session_id="session-forged",
            operation_class="notebook",
        )
        forged_expiry_path = root / "forged-authority-expiry.json"
        forged_expiry_path.write_bytes(canonical_json_bytes(forged_expiry))
        forged_expiry_cli = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "append-event", "--engagement", str(engagement), "--file", str(forged_expiry_path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        try:
            forged_expiry_cli_code = json.loads(forged_expiry_cli.stdout)["error"]["code"]
        except (json.JSONDecodeError, KeyError):
            forged_expiry_cli_code = None
        from engagement_state import append_event as public_append_event
        try:
            public_append_event(engagement, forged_expiry)
            forged_expiry_helper_code = None
        except RecordError as exc:
            forged_expiry_helper_code = exc.code
        checks.append(("generic CLI and public notebook append boundaries cannot future-forge objective authority expiry", forged_expiry_cli.returncode == 1 and forged_expiry_cli_code == "canonical_notebook_command_required" and forged_expiry_helper_code == "canonical_notebook_command_required", forged_expiry_cli.stdout + forged_expiry_cli.stderr + str(forged_expiry_helper_code)))

        synthetic_queue_state = copy.deepcopy(initial_reduction)
        synthetic_queue_state["intake"] = {"source_path": "inert-source.txt", "source_hash": "sha256:" + "1" * 64, "source_size": 1, "card_ids": ["pattern.legacy-route-differential"], "observation_ref": "event-synthetic-source-observation", "routing_ref": "event-synthetic-source-routing", "environment_ref": "preflight-selftest"}
        synthetic_queue_state["hypotheses"] = {
            "entity-hypothesis_ran_unadjudicated": {"status": "running", "next_route": None, "unresolved_questions": []},
            "entity-hypothesis_running_unattempted": {"status": "running", "running_event_ref": "event-entity-hypothesis-running", "next_route": None, "unresolved_questions": []},
            "entity-hypothesis_unrouted": {"status": "selected", "next_route": None, "unresolved_questions": []},
            "entity-hypothesis_open_route": {"status": "running", "next_route": "detail", "unresolved_questions": []},
            "entity-hypothesis_unresolved_question": {"status": "running", "next_route": None, "unresolved_questions": ["detail"]},
        }
        synthetic_queue_state["work_queue_context"] = {
            "artifacts": {},
            "pending_attempts": {
                "entity-hypothesis_ran_unadjudicated": [
                    {
                        "attempt_id": "attempt-synthetic-unadjudicated",
                        "kind": "primary",
                        "recorded_at": "2026-07-10T00:00:01Z",
                        "evidence": [],
                    }
                ]
            }
        }
        synthetic_queue_state["findings"] = {
            "entity-claim_unadjudicated": {"revision": 1, "status": "needs_review"},
            "entity-finding_revision_pending": {"revision": 1, "status": "confirmed"},
            "entity-finding_unproved": {"revision": 1, "status": "confirmed", "claim_tuple_hash": "sha256:" + "2" * 64, "revision_event_ref": "event-entity-finding-unproved-revision"},
        }
        synthetic_queue_state["claim_adjudications"] = {
            "entity-claim_unadjudicated": {"status": "needs_review", "event_ref": "event-claim-needs-review", "review_ref": "review-claim-needs-review", "reviewer_run_id": "run-claim-needs-review", "reviewed_revision": 1, "expected_filing_revision": 2},
            "entity-finding_revision_pending": {"status": "confirmed", "event_ref": "event-claim-confirmed", "review_ref": "review-claim-confirmed", "reviewer_run_id": "run-claim-confirmed", "reviewed_revision": 1, "expected_filing_revision": 2},
            "entity-finding_unproved": {"status": "confirmed", "event_ref": "event-claim-unproved", "review_ref": "review-claim-unproved", "reviewer_run_id": "run-claim-unproved", "reviewed_revision": 1, "expected_filing_revision": 2},
        }
        synthetic_queue_state["outstanding_reviews"] = [{
            "review_type": "regrade",
            "entity_ref": "finding-review-obligation",
            "review_ref": "review-obligation-open",
            "reason": "Synthetic workflow mapping test.",
            "status": "pending",
            "hypothesis_ref": None,
            "opened_at": "2026-07-10T00:00:00Z",
        }]
        synthetic_queue_state["candidates"] = {
            "entity-candidate_undisposed": {"status": "selected"},
            "entity-deferred_candidate_unreviewed": {"status": "deferred"},
        }
        synthetic_queue_state["control_candidates"] = [{"routing_event_id": "entity-control_candidate_unverified", "source_observation_ref": "event-observation-control", "card_ids": ["card-control"], "status": "likely_held", "rationale": "Synthetic control.", "hypothesis_ref": None, "primary_attempt_ref": None}]
        synthetic_queue_state["regrade_reviews"] = {}
        synthetic_queue_state["latest_coverage_review"] = None
        entity_types = {
            "source_unobserved": "engagement",
            "source_unrouted": "engagement",
            "source_unhypothesized": "engagement",
            "hypothesis_ran_unadjudicated": "hypothesis",
            "hypothesis_running_unattempted": "hypothesis",
            "hypothesis_unrouted": "hypothesis",
            "hypothesis_open_route": "hypothesis",
            "hypothesis_unresolved_question": "hypothesis",
            "claim_unadjudicated": "finding",
            "finding_revision_pending": "finding",
            "finding_unproved": "finding",
            "review_obligation_open": "review_obligation",
            "candidate_undisposed": "candidate",
            "deferred_candidate_unreviewed": "candidate",
            "control_candidate_unverified": "control_candidate",
            "awaiting_operator": "authority_request",
            "coverage_review_missing": "engagement",
        }
        entity_ids = {item_class: f"entity-{item_class}" for item_class in WORK_QUEUE_CLASS_ORDER}
        entity_ids["review_obligation_open"] = "review-obligation-open"
        expected_actions = {
            "source_unobserved": "record_source_observation",
            "source_unrouted": "route_source_observation",
            "source_unhypothesized": "create_source_hypothesis",
            "hypothesis_ran_unadjudicated": "record_hypothesis_disposition",
            "hypothesis_running_unattempted": "requeue_unattempted_hypothesis",
            "hypothesis_unrouted": "record_hypothesis_disposition",
            "hypothesis_open_route": "record_hypothesis_disposition",
            "hypothesis_unresolved_question": "record_hypothesis_disposition",
            "claim_unadjudicated": "record_claim_adjudication",
            "finding_revision_pending": "request_finding_revision_authority",
            "finding_unproved": "record_current_revision_regrade",
            "review_obligation_open": "route_review_obligation",
            "candidate_undisposed": "create_candidate_hypothesis",
            "deferred_candidate_unreviewed": "record_candidate_skipped",
            "control_candidate_unverified": "create_control_hypothesis",
            "awaiting_operator": "operator_resolve_authority",
            "coverage_review_missing": "record_cold_coverage_review",
        }
        raw_items = []
        mapped_items = []
        for item_class in WORK_QUEUE_CLASS_ORDER:
            predicate, closes_when = WORK_QUEUE_RULES[item_class]
            raw_item = {
                "class": item_class,
                "entity": {"type": entity_types[item_class], "id": entity_ids[item_class], "detail": "detail" if item_class in {"hypothesis_open_route", "hypothesis_unresolved_question"} else None},
                "blocking": item_class != "awaiting_operator",
                "predicate": predicate,
                "closes_when": closes_when,
            }
            raw_items.append(raw_item)
            mapped_items.append(decorate_work_queue_item(raw_item, synthetic_queue_state, engagement.absolute()))
        matrix_commands = load_capability_matrix()["commands"]
        actions_ok = all(
            item["next_action"]["action_id"] == expected_actions[item["class"]]
            and item["next_action"]["command"] in matrix_commands
            and item["next_action"]["operation"] == {"tool": "run-engagement", "command": item["next_action"]["command"]}
            and item["next_action"]["arguments"][:2] == ["--engagement", str(engagement.absolute())]
            and item["next_action"]["local_invocation"]["schema_version"] == 1
            and item["next_action"]["local_invocation"]["argv"][2] == item["next_action"]["command"]
            and item["next_action"]["session_kind"] in {"ordinary_bounded", "fresh_independent_reviewer", "operator_required"}
            and item["next_action"]["principal"] in {"orchestrator", "hunter", "broker", "independent_reviewer", "operator_only"}
            and item["next_action"]["execution_principal"] in {"broker", "operator_only"}
            and item["next_action"]["execution_principal"] == ("broker" if item["next_action"]["launchable"] else "operator_only")
            and item["next_action"]["effect"] in {"closes_item", "advances_item", "conditional"}
            and isinstance(item["next_action"]["required_inputs"], list)
            and item["next_action"]["recompute_after"] is True
            and "closure" not in item
            for item in mapped_items
        )
        operator_action = next(item["next_action"] for item in mapped_items if item["class"] == "awaiting_operator")
        deferred_action = next(item["next_action"] for item in mapped_items if item["class"] == "deferred_candidate_unreviewed")
        checks.append(("every reducer queue class maps to one closed-shape capability-classified next action", actions_ok and len(mapped_items) == len(WORK_QUEUE_CLASS_ORDER) and operator_action["session_kind"] == "operator_required" and operator_action["principal"] == "operator_only" and operator_action["execution_principal"] == "operator_only" and operator_action["launchable"] is False, str([(item["class"], item["next_action"]["action_id"]) for item in mapped_items])))
        checks.append(("skipping a deferred candidate advances state without claiming the candidate debt is closed", deferred_action["effect"] == "advances_item", str(deferred_action)))

        attempt_stage_state = copy.deepcopy(synthetic_queue_state)
        attempt_stage_state["control_candidates"][0]["hypothesis_ref"] = "entity-hypothesis_ran_unadjudicated"
        attempt_stage_state["hypotheses"]["entity-hypothesis_ran_unadjudicated"]["status"] = "running"
        mediated_attempt = decorate_work_queue_item(raw_items[WORK_QUEUE_CLASS_ORDER.index("control_candidate_unverified")], attempt_stage_state, engagement.absolute())["next_action"]
        checks.append(("broker-mediated actions keep the cognitive producer distinct from the process-bound recorder", mediated_attempt["principal"] == "hunter" and mediated_attempt["execution_principal"] == "broker" and "process-bound broker recorder identity" in str(mediated_attempt["required_inputs"]), str(mediated_attempt)))
        independent_action_text = " ".join(
            requirement
            for item in mapped_items
            if item["next_action"]["session_kind"] == "fresh_independent_reviewer"
            for required_input in item["next_action"]["required_inputs"]
            for requirement in required_input["requirements"]
        )
        checks.append(("fresh independent actions record outcome-open reviews rather than prescribing favorable verdicts", all(fragment not in independent_action_text for fragment in ("verdict is confirmed", "verdict is verified", "verdict is reward_hacked", "verdict is coverage_dry")), independent_action_text))

        poc_blocked_state = copy.deepcopy(synthetic_queue_state)
        poc_blocked_state["findings"]["finding-poc-blocked"] = {"revision": 1, "status": "confirmed", "claim_tuple_hash": "sha256:" + "3" * 64, "revision_event_ref": "event-finding-poc-blocked-revision"}
        poc_blocked_state["outstanding_reviews"] = [{"review_type": "pocinator", "entity_ref": "finding-poc-blocked", "review_ref": "event-poc-blocked", "reason": "Fresh proof review could not run.", "status": "blocked", "hypothesis_ref": None, "opened_at": "2026-07-10T00:00:00Z", "opening_reviewer_run_id": "run-poc-blocked"}]
        poc_blocked_item = {"class": "review_obligation_open", "entity": {"type": "review_obligation", "id": "event-poc-blocked", "detail": "finding-poc-blocked"}, "blocking": True, "predicate": WORK_QUEUE_RULES["review_obligation_open"][0], "closes_when": WORK_QUEUE_RULES["review_obligation_open"][1]}
        poc_blocked_action = decorate_work_queue_item(poc_blocked_item, poc_blocked_state, engagement.absolute())["next_action"]
        checks.append(("blocked Pocinator debt maps to exact prior-run supersession without prescribing its outcome", poc_blocked_action["action_id"] == "supersede_blocked_review_obligation" and "event-poc-blocked" in str(poc_blocked_action["required_inputs"]) and all(fragment not in str(poc_blocked_action["required_inputs"]) for fragment in ("verdict is verified", "verdict is reward_hacked")), str(poc_blocked_action)))

        target_like_cwd = root / "target-like-cwd"; target_like_cwd.mkdir()
        local_prefix = coverage_action["local_invocation"]["argv"][:2]
        local_help = subprocess.run([*local_prefix, "--help"], cwd=target_like_cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        checks.append(("local invocation preserves the active venv and executes from a target-repo cwd while semantics stay tool-relative", local_help.returncode == 0 and local_prefix[0] == str(Path(sys.executable).absolute()) and coverage_action["operation"] == {"tool": "run-engagement", "command": "record-review"} and coverage_action["arguments"][0] == "--engagement", local_help.stdout + local_help.stderr))

        coverage_fresh_state = copy.deepcopy(initial_reduction)
        coverage_fresh_state["hypotheses"] = {"hypothesis-terminal": {"status": "closed"}}
        coverage_fresh_state["event_count"] = 12
        coverage_fresh_state["coverage_relevant_sequence"] = 11
        coverage_fresh_state["latest_coverage_review"] = {
            "event_ref": "event-coverage-review-current",
            "event_sequence": 11,
            "review_refs": ["review-coverage-current"],
            "verdict": "coverage_dry",
            "hypothesis_dispositions_hash": hypothesis_dispositions_hash(coverage_fresh_state["hypotheses"]),
        }
        coverage_item = next(item for item in raw_items if item["class"] == "coverage_review_missing")
        neutral_end_action = decorate_work_queue_item(coverage_item, coverage_fresh_state, engagement.absolute())["next_action"]
        coverage_stale_state = copy.deepcopy(coverage_fresh_state)
        coverage_stale_state["coverage_relevant_sequence"] = 12
        substantive_action = decorate_work_queue_item(coverage_item, coverage_stale_state, engagement.absolute())["next_action"]
        checks.append(("neutral session end checks preserve a current cold review while any later substantive event invalidates it", neutral_end_action["action_id"] == "record_coverage_dry" and substantive_action["action_id"] == "record_cold_coverage_review", str((neutral_end_action, substantive_action))))

        coverage_continue_state = copy.deepcopy(coverage_fresh_state)
        coverage_continue_state["latest_coverage_review"]["verdict"] = "continue"
        coverage_continue_action = decorate_work_queue_item(coverage_item, coverage_continue_state, engagement.absolute())["next_action"]
        checks.append(("a current continue verdict advances through one exact cold-review-grounded hypothesis instead of confirmation-shopping or re-reviewing", coverage_continue_action["action_id"] == "create_coverage_followup_hypothesis" and coverage_continue_action["effect"] == "advances_item" and "review-coverage-current" in str(coverage_continue_action["required_inputs"]) and coverage_continue_action["session_kind"] == "ordinary_bounded" and coverage_continue_action["principal"] == "orchestrator", str(coverage_continue_action)))

        first_blocking_state = copy.deepcopy(synthetic_queue_state)
        first_blocking_state["work_queue"] = [
            next(item for item in raw_items if item["class"] == "awaiting_operator"),
            next(item for item in raw_items if item["class"] == "hypothesis_unrouted"),
        ]
        first_blocking = queue_command_payload("next", first_blocking_state, engagement.absolute())
        operator_only_state = copy.deepcopy(initial_reduction)
        operator_only_state["work_queue"] = [next(item for item in raw_items if item["class"] == "awaiting_operator")]
        operator_only_gate = queue_command_payload("gate", operator_only_state, engagement.absolute())
        parked_blocking_state = copy.deepcopy(first_blocking_state)
        parked_blocking_state["queue_control"]["status"] = "parked"
        parked_blocking_gate = queue_command_payload("gate", parked_blocking_state, engagement.absolute())
        terminal_coverage_gates = {}
        for coverage_status in ("budget_bounded", "blocked", "coverage_dry"):
            terminal_state = copy.deepcopy(first_blocking_state)
            terminal_state["coverage"] = coverage_status
            terminal_coverage_gates[coverage_status] = queue_command_payload("gate", terminal_state, engagement.absolute())
        checks.append(("next chooses the first blocking item and active blocking work exits 3", first_blocking["item"]["class"] == "hypothesis_unrouted" and first_blocking["queue"]["has_blocking_work"] is True and first_blocking["queue"]["should_block"] is True and first_blocking["queue"]["decision"] == "block" and queue_gate_exit(first_blocking) == 3, str(first_blocking)))
        checks.append(("gate releases operator-only and signed parked queues without hiding blocking record truth", operator_only_gate["queue"]["has_blocking_work"] is False and operator_only_gate["queue"]["decision"] == "release" and queue_gate_exit(operator_only_gate) == 0 and parked_blocking_gate["queue"]["control_status"] == "parked" and parked_blocking_gate["queue"]["blocking_count"] == 1 and parked_blocking_gate["queue"]["has_blocking_work"] is True and parked_blocking_gate["queue"]["should_block"] is False and parked_blocking_gate["queue"]["decision"] == "release" and queue_gate_exit(parked_blocking_gate) == 0, str((operator_only_gate, parked_blocking_gate))))
        checks.append(("terminal and blocked coverage release without hiding invariant-violating queue rows", all(payload["queue"]["coverage_status"] == coverage_status and payload["queue"]["blocking_count"] == 1 and payload["queue"]["has_blocking_work"] is True and payload["queue"]["should_block"] is False and payload["queue"]["decision"] == "release" and queue_gate_exit(payload) == 0 for coverage_status, payload in terminal_coverage_gates.items()), str(terminal_coverage_gates)))

        queue_state = {
            "engagement_id": "eng-queue-selftest",
            "coverage": "active",
            "hypotheses": {
                "hypothesis-unrouted": {"status": "selected", "origin_type": "operator_prior", "origin_ref": "prior-1", "experiment_refs": [], "unresolved_questions": [], "next_route": "route-selected"},
                "hypothesis-route": {"status": "running", "origin_type": "operator_prior", "origin_ref": "prior-2", "experiment_refs": ["experiment-route"], "unresolved_questions": ["question-z", "", "question-z", "question-a"], "next_route": "route-z"},
                "hypothesis-terminal-route": {"status": "closed", "origin_type": "operator_prior", "origin_ref": "prior-terminal", "experiment_refs": [], "control_refs": [], "unresolved_questions": [], "next_route": "route-terminal"},
                "hypothesis-ran": {"status": "queued", "origin_type": "operator_prior", "origin_ref": "prior-3", "experiment_refs": ["unrelated-attempt-ref"], "control_refs": [], "unresolved_questions": [], "next_route": None},
                "hypothesis-cites-candidate": {"status": "held", "origin_type": "candidate", "origin_ref": "candidate-cited", "experiment_refs": ["experiment-cited"], "unresolved_questions": [], "next_route": None},
                "hypothesis-adjudicated": {"status": "running", "origin_type": "operator_prior", "origin_ref": "prior-4", "experiment_refs": ["attempt-hypothesis-adjudicated"], "control_refs": [], "unresolved_questions": [], "next_route": None},
            },
            "findings": {
                "finding-verified": {"revision": 3, "status": "confirmed", "adjudication_review_ref": "review-verified", "adjudication_event_ref": "event-claim-verified"},
                "finding-proof": {"revision": 2, "status": "confirmed", "adjudication_review_ref": "review-proof", "adjudication_event_ref": "event-claim-proof"},
                "finding-claim": {"revision": 1, "status": "needs_review", "adjudication_review_ref": "review-claim", "adjudication_event_ref": "event-claim-needs-review"},
                "finding-filing": {"revision": 1, "status": "supported", "adjudication_review_ref": "review-filing-old", "adjudication_event_ref": "event-claim-filing-old"},
            },
            "claim_adjudications": {
                "finding-verified": {"status": "confirmed", "event_ref": "event-claim-verified", "review_ref": "review-verified", "reviewed_revision": 2, "expected_filing_revision": 3},
                "finding-proof": {"status": "confirmed", "event_ref": "event-claim-proof", "review_ref": "review-proof", "reviewed_revision": 1, "expected_filing_revision": 2},
                "finding-claim": {"status": "needs_review", "event_ref": "event-claim-needs-review", "review_ref": "review-claim", "reviewed_revision": None, "expected_filing_revision": 1},
                "finding-filing": {"status": "confirmed", "event_ref": "event-claim-filing", "review_ref": "review-filing-new", "reviewed_revision": 1, "expected_filing_revision": 2},
            },
            "proof_reviews": {
                "finding-verified:r3": {"terminal_status": "verified"},
                "finding-proof:r1": {"terminal_status": "verified"},
            },
            "outstanding_reviews": [
                {"review_type": "pocinator", "entity_ref": "finding-verified", "review_ref": "event-review-z", "reason": "Proof review remains blocked.", "status": "blocked", "hypothesis_ref": None, "opened_at": "2026-07-10T00:00:02Z"},
                {"review_type": "regrade", "entity_ref": "finding-verified", "review_ref": "event-review-a", "reason": "Confirmed claim still requires a correction.", "status": "correction_required", "hypothesis_ref": None, "opened_at": "2026-07-10T00:00:01Z"},
            ],
            "candidates": {
                "candidate-selected": {"status": "selected"},
                "candidate-cited": {"status": "selected"},
                "candidate-deferred": {"status": "deferred"},
                "candidate-closed": {"status": "closed"},
            },
            "control_candidates": [
                {"routing_event_id": "event-control-verified", "status": "likely_held"},
                {"routing_event_id": "event-control-candidate", "status": "likely_held"},
            ],
            "authority_requests": {
                "request-approved": {"request_id": "request-approved", "status": "approved"},
                "request-pending": {"request_id": "request-pending", "status": "pending_authority"},
            },
        }
        queue_attempts = [
            {"attempt_id": "attempt-control-wrong-kind", "hypothesis_ref": None, "experiment_ref": "event-control-candidate", "kind": "primary"},
            {"attempt_id": "attempt-control-wrong-ref", "hypothesis_ref": None, "experiment_ref": "event-other", "kind": "negative_control"},
            {"attempt_id": "attempt-control-verified", "hypothesis_ref": None, "experiment_ref": "event-control-verified", "kind": "positive_control"},
            {"attempt_id": "attempt-hypothesis-adjudicated", "hypothesis_ref": "hypothesis-adjudicated", "experiment_ref": "experiment-adjudicated", "kind": "primary"},
            {"attempt_id": "attempt-hypothesis-ran", "hypothesis_ref": "hypothesis-ran", "experiment_ref": "experiment-ran", "kind": "primary"},
            {"attempt_id": "attempt-terminal-late", "hypothesis_ref": "hypothesis-terminal-route", "experiment_ref": "experiment-terminal", "kind": "primary"},
        ]
        expected_review_a = {"class": "review_obligation_open", "entity": {"type": "review_obligation", "id": "event-review-a", "detail": "finding-verified"}, "blocking": True, "predicate": "review_ref is present in outstanding_reviews", "closes_when": "review_ref is absent from outstanding_reviews"}
        expected_review_z = {"class": "review_obligation_open", "entity": {"type": "review_obligation", "id": "event-review-z", "detail": "finding-verified"}, "blocking": True, "predicate": "review_ref is present in outstanding_reviews", "closes_when": "review_ref is absent from outstanding_reviews"}
        expected_queue = [
            {"class": "hypothesis_ran_unadjudicated", "entity": {"type": "hypothesis", "id": "hypothesis-ran", "detail": None}, "blocking": True, "predicate": "a matching attempt_id is absent from experiment_refs and control_refs", "closes_when": "every matching attempt_id is present in experiment_refs or control_refs"},
            {"class": "hypothesis_ran_unadjudicated", "entity": {"type": "hypothesis", "id": "hypothesis-terminal-route", "detail": None}, "blocking": True, "predicate": "a matching attempt_id is absent from experiment_refs and control_refs", "closes_when": "every matching attempt_id is present in experiment_refs or control_refs"},
            {"class": "hypothesis_running_unattempted", "entity": {"type": "hypothesis", "id": "hypothesis-route", "detail": None}, "blocking": True, "predicate": "status is running and no matching attempt is recorded", "closes_when": "a matching attempt is recorded or status is outside running"},
            {"class": "hypothesis_unrouted", "entity": {"type": "hypothesis", "id": "hypothesis-ran", "detail": None}, "blocking": True, "predicate": "status in {queued, selected}", "closes_when": "status is outside {queued, selected}"},
            {"class": "hypothesis_unrouted", "entity": {"type": "hypothesis", "id": "hypothesis-unrouted", "detail": None}, "blocking": True, "predicate": "status in {queued, selected}", "closes_when": "status is outside {queued, selected}"},
            {"class": "hypothesis_open_route", "entity": {"type": "hypothesis", "id": "hypothesis-route", "detail": "route-z"}, "blocking": True, "predicate": "next_route is not null", "closes_when": "next_route is null"},
            {"class": "hypothesis_open_route", "entity": {"type": "hypothesis", "id": "hypothesis-terminal-route", "detail": "route-terminal"}, "blocking": True, "predicate": "next_route is not null", "closes_when": "next_route is null"},
            {"class": "hypothesis_open_route", "entity": {"type": "hypothesis", "id": "hypothesis-unrouted", "detail": "route-selected"}, "blocking": True, "predicate": "next_route is not null", "closes_when": "next_route is null"},
            {"class": "hypothesis_unresolved_question", "entity": {"type": "hypothesis", "id": "hypothesis-route", "detail": ""}, "blocking": True, "predicate": "unresolved_questions contains this exact question", "closes_when": "this exact question is absent from unresolved_questions"},
            {"class": "hypothesis_unresolved_question", "entity": {"type": "hypothesis", "id": "hypothesis-route", "detail": "question-a"}, "blocking": True, "predicate": "unresolved_questions contains this exact question", "closes_when": "this exact question is absent from unresolved_questions"},
            {"class": "hypothesis_unresolved_question", "entity": {"type": "hypothesis", "id": "hypothesis-route", "detail": "question-z"}, "blocking": True, "predicate": "unresolved_questions contains this exact question", "closes_when": "this exact question is absent from unresolved_questions"},
            {"class": "claim_unadjudicated", "entity": {"type": "finding", "id": "finding-claim", "detail": None}, "blocking": True, "predicate": "effective claim status in {needs_review, supported}", "closes_when": "effective claim status in {confirmed, contaminated, refuted}"},
            expected_review_a,
            expected_review_z,
            {"class": "finding_revision_pending", "entity": {"type": "finding", "id": "finding-filing", "detail": None}, "blocking": True, "predicate": "latest fileable claim adjudication is not reflected by its expected finding revision", "closes_when": "the expected finding revision reflects the latest adjudication, or a newer adjudication supersedes it"},
            {"class": "finding_unproved", "entity": {"type": "finding", "id": "finding-proof", "detail": None}, "blocking": True, "predicate": "status in {supported, confirmed} and the current revision has no verified proof review", "closes_when": "the current revision has a proof review with terminal_status verified or status is outside {supported, confirmed}"},
            {"class": "candidate_undisposed", "entity": {"type": "candidate", "id": "candidate-closed", "detail": None}, "blocking": True, "predicate": "status in {queued, selected, closed} and no hypothesis cites this candidate as origin", "closes_when": "a hypothesis has origin_type candidate and origin_ref equal to this candidate id"},
            {"class": "candidate_undisposed", "entity": {"type": "candidate", "id": "candidate-selected", "detail": None}, "blocking": True, "predicate": "status in {queued, selected, closed} and no hypothesis cites this candidate as origin", "closes_when": "a hypothesis has origin_type candidate and origin_ref equal to this candidate id"},
            {"class": "deferred_candidate_unreviewed", "entity": {"type": "candidate", "id": "candidate-deferred", "detail": None}, "blocking": True, "predicate": "status is deferred", "closes_when": "status is not deferred"},
            {"class": "control_candidate_unverified", "entity": {"type": "control_candidate", "id": "event-control-candidate", "detail": None}, "blocking": True, "predicate": "status is likely_held and no control-kind attempt references this routing event", "closes_when": "a negative_control or positive_control attempt has experiment_ref equal to this routing event id"},
            {"class": "awaiting_operator", "entity": {"type": "authority_request", "id": "request-pending", "detail": None}, "blocking": False, "predicate": "status is pending_authority", "closes_when": "status is not pending_authority"},
        ]
        computed_queue = compute_work_queue(queue_state, queue_attempts)
        reordered_state = copy.deepcopy(queue_state)
        for key in ("hypotheses", "findings", "claim_adjudications", "proof_reviews", "candidates", "authority_requests"):
            reordered_state[key] = dict(reversed(list(reordered_state[key].items())))
        reordered_state["control_candidates"].reverse()
        reordered_state["outstanding_reviews"].reverse()
        for hypothesis_state in reordered_state["hypotheses"].values():
            hypothesis_state["unresolved_questions"].reverse()
        reordered_queue = compute_work_queue(reordered_state, list(reversed(queue_attempts)))
        checks.append(("computed work queue covers every debt class in canonical order with exact overlapping predicates", computed_queue == expected_queue, str(computed_queue)))
        checks.append(("computed work queue is independent of source insertion order", canonical_json_bytes(computed_queue) == canonical_json_bytes(reordered_queue), str(reordered_queue)))
        checks.append(("only pending operator authority is nonblocking and it suppresses coverage review", [item for item in computed_queue if not item["blocking"]] == [expected_queue[-1]] and all(item["class"] != "coverage_review_missing" for item in computed_queue), str(computed_queue)))
        checks.append(("the one ending predicate permits empty or operator-only queues and fails closed on blocking, missing, or malformed queue state", engagement_may_end({"work_queue": []}) and engagement_may_end({"work_queue": [expected_queue[-1]]}) and not engagement_may_end({"work_queue": [expected_queue[0]]}) and not engagement_may_end({}) and not engagement_may_end({"work_queue": {}}), "ending predicate admitted malformed or blocking work"))

        operator_only_state = {**queue_state, "hypotheses": {}, "findings": {}, "claim_adjudications": {}, "proof_reviews": {}, "outstanding_reviews": [], "candidates": {}, "control_candidates": [], "authority_requests": {"request-pending": queue_state["authority_requests"]["request-pending"]}}
        terminal_debt_state = {
            **operator_only_state,
            "coverage": "active",
            "authority_requests": {},
            "hypotheses": {
                "hypothesis-running-unattempted": {
                    "status": "running",
                    "running_event_ref": "event-hypothesis-running-unattempted",
                    "origin_type": "operator_prior",
                    "origin_ref": "prior-running-unattempted",
                    "experiment_refs": [],
                    "control_refs": [],
                    "unresolved_questions": [],
                    "next_route": None,
                }
            },
            "candidates": {"candidate-queued": {"status": "queued"}},
        }
        terminal_debt_projection = project_terminal_work_state(
            terminal_debt_state,
            [],
            coverage="coverage_dry",
            recorded_at="2026-07-10T00:00:10Z",
        )
        terminal_debt_actions = {
            item["class"]: decorate_work_queue_item(item, terminal_debt_projection, engagement.absolute())["next_action"]
            for item in terminal_debt_projection["work_queue"]
        }
        checks.append((
            "terminal projection keeps queued candidates and running unattempted hypotheses blocking with deterministic next actions",
            [item["class"] for item in terminal_debt_projection["work_queue"]] == ["hypothesis_running_unattempted", "candidate_undisposed"]
            and not engagement_may_end(terminal_debt_projection)
            and terminal_debt_actions["hypothesis_running_unattempted"]["action_id"] == "requeue_unattempted_hypothesis"
            and terminal_debt_actions["hypothesis_running_unattempted"]["effect"] == "advances_item"
            and terminal_debt_actions["candidate_undisposed"]["action_id"] == "select_candidate"
            and terminal_debt_actions["candidate_undisposed"]["effect"] == "advances_item",
            str((terminal_debt_projection["work_queue"], terminal_debt_actions)),
        ))
        specialized_running_state = {
            **operator_only_state,
            "coverage": "coverage_dry",
            "scope_hash": initial_reduction["scope_hash"],
            "active_environment_ref": "environment-specialized",
            "authority_requests": {},
            "outstanding_reviews": [{
                "review_type": "regrade",
                "entity_ref": "finding-specialized-review",
                "review_ref": "review-specialized-running",
                "reason": "The exact routed review owns this running hypothesis.",
                "status": "routed",
                "hypothesis_ref": "hypothesis-specialized-review",
                "opened_at": "2026-07-10T00:00:00Z",
            }],
            "hypotheses": {
                "hypothesis-specialized-review": {"status": "running", "running_event_ref": "event-specialized-review-running", "next_route": "review experiment", "unresolved_questions": []},
                "hypothesis-specialized-control": {"status": "running", "running_event_ref": "event-specialized-control-running", "next_route": "control experiment", "unresolved_questions": []},
            },
            "control_candidates": [{
                "routing_event_id": "event-specialized-control-routing",
                "status": "likely_held",
                "hypothesis_ref": "hypothesis-specialized-control",
                "primary_attempt_ref": None,
            }],
            "work_queue_context": {
                "pending_attempts": {},
                "artifacts": {
                    "artifact-specialized-review": {
                        "created_at": "2026-07-10T00:00:01Z",
                        "environment_ref": "environment-specialized",
                    }
                },
            },
        }
        specialized_running_state["work_queue"] = compute_work_queue(specialized_running_state, [])
        specialized_review_item = next(item for item in specialized_running_state["work_queue"] if item["class"] == "review_obligation_open")
        specialized_control_item = next(item for item in specialized_running_state["work_queue"] if item["class"] == "control_candidate_unverified")
        specialized_review_action = decorate_work_queue_item(specialized_review_item, specialized_running_state, engagement.absolute())["next_action"]
        specialized_control_action = decorate_work_queue_item(specialized_control_item, specialized_running_state, engagement.absolute())["next_action"]
        from work_queue_admission import build_action_admission
        specialized_control_admission = build_action_admission(specialized_control_item, specialized_control_action, specialized_running_state, engagement.absolute())
        specialized_control_experiment_constraints = [
            constraint
            for constraint in specialized_control_admission["constraints"]
            if constraint["document"] == "proposal" and constraint["path"] == ["experiment_ref"]
        ]
        checks.append((
            "running review and control hypotheses retain their exact specialized evidence actions",
            [item["class"] for item in specialized_running_state["work_queue"]] == ["review_obligation_open", "control_candidate_unverified"]
            and specialized_review_action["action_id"] == "collect_review_evidence"
            and specialized_control_action["action_id"] == "record_control_primary"
            and specialized_control_experiment_constraints == [{"document": "proposal", "path": ["experiment_ref"], "operator": "equals", "value": "event-specialized-control-routing"}],
            str((specialized_running_state["work_queue"], specialized_review_action, specialized_control_action, specialized_control_admission)),
        ))
        review_only_state = {**operator_only_state, "findings": {"finding-verified": queue_state["findings"]["finding-verified"]}, "proof_reviews": {"finding-verified:r3": queue_state["proof_reviews"]["finding-verified:r3"]}, "outstanding_reviews": [queue_state["outstanding_reviews"][1]], "authority_requests": {}}
        resolved_review_state = {**review_only_state, "outstanding_reviews": []}
        expected_queue_coverage = {**expected_coverage_item, "entity": {**expected_coverage_item["entity"], "id": queue_state["engagement_id"]}}
        checks.append(("confirmed and proof-verified review debt blocks coverage until the exact outstanding row is removed", compute_work_queue(review_only_state, []) == [expected_review_a] and compute_work_queue(resolved_review_state, []) == [expected_queue_coverage], str(compute_work_queue(review_only_state, []))))
        stage_base = {**operator_only_state, "authority_requests": {}, "coverage": "active"}
        initial_supported = {**stage_base, "claim_adjudications": {"finding-initial": {"status": "supported", "event_ref": "event-claim-initial", "review_ref": "review-claim-initial", "reviewed_revision": None, "expected_filing_revision": 1}}}
        initial_needs_review = {**stage_base, "claim_adjudications": {"finding-needs-review": {"status": "needs_review", "event_ref": "event-claim-needs-review-new", "review_ref": "review-needs-review-new", "reviewed_revision": None, "expected_filing_revision": 1}}}
        reflected_supported = {**initial_supported, "findings": {"finding-initial": {"revision": 1, "status": "supported", "adjudication_review_ref": "review-claim-initial", "adjudication_event_ref": "event-claim-initial"}}}
        newer_confirmed = {**stage_base, "findings": {"finding-current": {"revision": 1, "status": "supported", "adjudication_review_ref": "review-old", "adjudication_event_ref": "event-old"}}, "claim_adjudications": {"finding-current": {"status": "confirmed", "event_ref": "event-claim-new", "review_ref": "review-new", "reviewed_revision": 1, "expected_filing_revision": 2, "recorded_at": "2026-07-10T00:00:10Z", "event_sequence": 10}}}
        reflected_confirmed = {**newer_confirmed, "findings": {"finding-current": {"revision": 2, "status": "confirmed", "adjudication_review_ref": "review-new", "adjudication_event_ref": "event-claim-new"}}}
        stage_classes = lambda snapshot: [(item["class"], item["entity"]["id"]) for item in compute_work_queue(snapshot, [])]
        checks.append(("claim stage distinguishes initial review, filing, reflected review, and current-revision proof debt", stage_classes(initial_needs_review) == [("claim_unadjudicated", "finding-needs-review")] and stage_classes(initial_supported) == [("claim_unadjudicated", "finding-initial"), ("finding_revision_pending", "finding-initial")] and stage_classes(reflected_supported) == [("claim_unadjudicated", "finding-initial"), ("finding_unproved", "finding-initial")] and stage_classes(newer_confirmed) == [("finding_revision_pending", "finding-current")] and stage_classes(reflected_confirmed) == [("finding_unproved", "finding-current")], str([stage_classes(item) for item in (initial_needs_review, initial_supported, reflected_supported, newer_confirmed, reflected_confirmed)])))

        legacy_overlap = copy.deepcopy(reflected_supported)
        legacy_overlap["outstanding_reviews"] = [{"review_type": "legacy_adjudication", "entity_ref": "finding-initial", "review_ref": "event-legacy-import", "reason": "Imported claim needs exact review.", "status": "pending", "hypothesis_ref": None, "opened_at": "2026-07-10T00:00:01Z"}]
        legacy_claim_item = next(item for item in compute_work_queue(legacy_overlap, []) if item["class"] == "claim_unadjudicated")
        legacy_claim_action = decorate_work_queue_item(legacy_claim_item, legacy_overlap, engagement.absolute())["next_action"]
        refuted_overlap = copy.deepcopy(reflected_supported)
        refuted_overlap["outstanding_reviews"] = [{"review_type": "regrade", "entity_ref": "finding-initial", "review_ref": "event-regrade-refuted", "reason": "Independent regrade refuted the claim.", "status": "correction_required", "hypothesis_ref": None, "opened_at": "2026-07-10T00:00:02Z", "required_claim_status": "refuted"}]
        refuted_claim_item = next(item for item in compute_work_queue(refuted_overlap, []) if item["class"] == "claim_unadjudicated")
        refuted_claim_action = decorate_work_queue_item(refuted_claim_item, refuted_overlap, engagement.absolute())["next_action"]
        legacy_requirements = " ".join(requirement for value in legacy_claim_action["required_inputs"] for requirement in value["requirements"])
        refuted_requirements = " ".join(requirement for value in refuted_claim_action["required_inputs"] for requirement in value["requirements"])
        checks.append(("claim-first overlap actions bind exact legacy and refuted review debt", "event-legacy-import" in legacy_requirements and "event-regrade-refuted" in refuted_requirements and "verdict is exactly refuted" in refuted_requirements, str((legacy_claim_action, refuted_claim_action))))

        eligible_reviews = [
            {"review_type": "regrade", "entity_ref": "finding-current", "review_ref": "review-correction", "status": "correction_required", "opened_at": "2026-07-10T00:00:01Z"},
            {"review_type": "regrade_escalation", "entity_ref": "finding-current", "review_ref": "review-escalation", "status": "evidence_collected", "opened_at": "2026-07-10T00:00:02Z"},
            {"review_type": "pocinator", "entity_ref": "finding-current", "review_ref": "review-poc", "status": "correction_required", "opened_at": "2026-07-10T00:00:03Z"},
            {"review_type": "legacy_adjudication", "entity_ref": "finding-current", "review_ref": "review-legacy", "status": "pending", "opened_at": "2026-07-10T00:00:04Z"},
        ]
        blocking_regrade_reviews = [
            {"review_type": "regrade", "entity_ref": "finding-current", "review_ref": "review-pending", "status": "pending", "opened_at": "2026-07-10T00:00:05Z"},
            {"review_type": "regrade", "entity_ref": "finding-current", "review_ref": "review-routed", "status": "routed", "opened_at": "2026-07-10T00:00:06Z"},
        ]
        ineligible_reviews = [
            {"review_type": "pocinator", "entity_ref": "finding-current", "review_ref": "review-blocked", "status": "blocked", "opened_at": "2026-07-10T00:00:07Z"},
        ]
        target = {"type": "finding", "id": "finding-current", "expected_revision": 2, "claim_state": "confirmed", "adjudication_event_ref": "event-claim-new", "adjudication_review_ref": "review-new", "resolves_review_refs": sorted(item["review_ref"] for item in eligible_reviews), "file_digest": "sha256:" + "7" * 64}
        pending_request = {"request_id": "request-v2-pending", "action_kind": "revise-finding", "status": "pending_authority", "lane_id": finding_revision_lane_id(target), "target": target}
        pending_filing = copy.deepcopy({**newer_confirmed, "outstanding_reviews": eligible_reviews, "authority_requests": {"request-v2-pending": pending_request}})
        pending_filing["claim_adjudications"]["finding-current"]["input_refs"] = sorted(item["review_ref"] for item in eligible_reviews)
        pending_keys = stage_classes(pending_filing)
        past_deadline_pending = copy.deepcopy(pending_filing); past_deadline_pending["authority_requests"]["request-v2-pending"]["expires_at"] = "2000-01-01T00:00:00Z"
        checks.append(("current v2 pending authority suppresses its exact filing-ready rows and expiry remains explicit record state", pending_keys == [("awaiting_operator", "request-v2-pending")] and stage_classes(past_deadline_pending) == pending_keys, str(pending_keys)))
        blocked_poc_filing = {**pending_filing, "outstanding_reviews": [*eligible_reviews, *ineligible_reviews]}
        blocked_poc_keys = stage_classes(blocked_poc_filing)
        checks.append(("blocked pocinator debt prevents filing suppression and remains ahead of revision work", ("finding_revision_pending", "finding-current") in blocked_poc_keys and ("review_obligation_open", "review-blocked") in blocked_poc_keys and blocked_poc_keys.index(("review_obligation_open", "review-blocked")) < blocked_poc_keys.index(("finding_revision_pending", "finding-current")), str(blocked_poc_keys)))
        blocked_filing = {**pending_filing, "outstanding_reviews": [*pending_filing["outstanding_reviews"], *blocking_regrade_reviews]}
        blocked_keys = stage_classes(blocked_filing)
        blocked_filing["work_queue"] = compute_work_queue(blocked_filing, [])
        blocked_list = queue_command_payload("list", blocked_filing, engagement.absolute())
        checks.append(("pending and routed regrade debt blocks filing and list never advertises a stale lower-ranked authority action", ("finding_revision_pending", "finding-current") in blocked_keys and all(("review_obligation_open", item["review_ref"]) in blocked_keys for item in blocking_regrade_reviews) and all("next_action" not in item for item in blocked_list["items"]), str((blocked_keys, blocked_list))))
        new_eligible = {"review_type": "pocinator", "entity_ref": "finding-current", "review_ref": "review-new-debt", "status": "correction_required", "opened_at": "2026-07-10T00:00:11Z"}
        stale_review_set = {**pending_filing, "outstanding_reviews": [*pending_filing["outstanding_reviews"], new_eligible]}
        stale_adjudication = copy.deepcopy(pending_filing); stale_adjudication["claim_adjudications"]["finding-current"] = {**stale_adjudication["claim_adjudications"]["finding-current"], "event_ref": "event-claim-newer", "review_ref": "review-newer"}
        wrong_lane = copy.deepcopy(pending_filing); wrong_lane["authority_requests"]["request-v2-pending"]["lane_id"] = "caller-controlled-lane"
        approved_overlap = copy.deepcopy(pending_filing); approved_overlap["authority_requests"] = {"request-v2-approved": {
            **pending_request,
            "request_id": "request-v2-approved",
            "status": "approved",
            "expires_at": "2099-01-01T00:00:00Z",
            "application": {"action_path": "authority/requests/request-v2-approved.action.json", "executor_id": "broker-approved", "session_id": "session-approved", "operator_id": "operator-approved"},
        }}
        explicitly_expired = copy.deepcopy(pending_filing); explicitly_expired["authority_requests"]["request-v2-pending"]["status"] = "expired"
        checks.append(("stale adjudication, changed filing-ready debt, wrong lane, approved overlap, and explicit expiry all re-expose filing debt", all(("finding_revision_pending", "finding-current") in stage_classes(item) for item in (stale_review_set, stale_adjudication, wrong_lane, approved_overlap, explicitly_expired)), str([stage_classes(item) for item in (stale_review_set, stale_adjudication, wrong_lane, approved_overlap, explicitly_expired)])))
        approved_overlap["work_queue"] = compute_work_queue(approved_overlap, [])
        approved_review_item = next(item for item in approved_overlap["work_queue"] if item["class"] == "review_obligation_open")
        approved_finding_item = next(item for item in approved_overlap["work_queue"] if item["class"] == "finding_revision_pending")

        class _EarlyQueueClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 1, 1, tzinfo=tz)

        class _LateQueueClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2100, 1, 1, tzinfo=tz)

        from unittest.mock import patch
        with patch("work_queue_actions.datetime", _EarlyQueueClock):
            early_approved_action = decorate_work_queue_item(approved_review_item, approved_overlap, engagement.absolute())["next_action"]
        with patch("work_queue_actions.datetime", _LateQueueClock):
            late_approved_action = decorate_work_queue_item(approved_review_item, approved_overlap, engagement.absolute())["next_action"]
        approved_finding_action = decorate_work_queue_item(approved_finding_item, approved_overlap, engagement.absolute())["next_action"]
        checks.append(("approved revision actions are identical across wall time and route both higher review debt and revision work through one atomic settlement", canonical_json_bytes(early_approved_action) == canonical_json_bytes(late_approved_action) and early_approved_action["action_id"] == approved_finding_action["action_id"] == "settle_approved_finding_revision" and early_approved_action["command"] == "settle-approved-revision" and early_approved_action["effect"] == "conditional", str((early_approved_action, late_approved_action, approved_finding_action))))
        stale_filing = copy.deepcopy(pending_filing)
        stale_filing["claim_adjudications"]["finding-current"].update({"recorded_at": "2026-07-10T00:00:01Z", "input_refs": []})
        stale_review_item = next(item for item in compute_work_queue(stale_filing, []) if item["class"] == "review_obligation_open")
        stale_review_action = decorate_work_queue_item(stale_review_item, stale_filing, engagement.absolute())["next_action"]
        checks.append(("a pre-opening or input-unbound adjudication never advances review debt to revision authority", _filing_blocking_review_error(stale_filing, "finding-current") in {"review_adjudication_not_fresh", "review_adjudication_inputs_missing"} and stale_review_action["action_id"] == "record_claim_adjudication", str(stale_review_action)))
        current_proposal = {"finding_id": "finding-current", "revision": 2, "supersedes_revision": 1, "claim_state": "confirmed", "adjudication": {"review_ref": "review-new"}}
        current_target = {**target, "resolves_review_refs": [], "file_digest": sha256_bytes(canonical_json_bytes(current_proposal))}; current_request = {**pending_request, "lane_id": finding_revision_lane_id(current_target), "target": current_target}; current_target_state = {**newer_confirmed, "outstanding_reviews": []}
        stale_same_status_state = copy.deepcopy(current_target_state); stale_same_status_state["claim_adjudications"]["finding-current"].update({"event_ref": "event-confirmed-newer", "review_ref": "review-confirmed-newer"})
        checks.append(("v2 apply-time currentness rejects a newer same-status adjudication", revise_finding_target_is_current(current_target_state, current_request, current_proposal) and not revise_finding_target_is_current(stale_same_status_state, current_request, current_proposal), str(stale_same_status_state["claim_adjudications"])))
        second_finding = {**pending_filing, "findings": {**pending_filing["findings"], "finding-other": {"revision": 1, "status": "supported", "adjudication_review_ref": "review-other-old", "adjudication_event_ref": "event-other-old"}}, "claim_adjudications": {**pending_filing["claim_adjudications"], "finding-other": {"status": "confirmed", "event_ref": "event-other-new", "review_ref": "review-other-new", "reviewed_revision": 1, "expected_filing_revision": 2}}}
        legacy_pending = {**newer_confirmed, "authority_requests": {"request-legacy": {"request_id": "request-legacy", "action_kind": "revise-finding", "status": "pending_authority", "lane_id": "legacy-lane", "target": None}}}
        checks.append(("v2 suppression is finding-scoped and legacy pending authority never hides filing debt", ("finding_revision_pending", "finding-other") in stage_classes(second_finding) and ("finding_revision_pending", "finding-current") in stage_classes(legacy_pending), str([stage_classes(second_finding), stage_classes(legacy_pending)])))
        terminal_queues = [compute_work_queue({**queue_state, "coverage": status}, queue_attempts) for status in ("coverage_dry", "budget_bounded")]
        checks.append(("coverage review is the sole last item only when active work is otherwise empty", compute_work_queue({**operator_only_state, "authority_requests": {}}, []) == [expected_queue_coverage] and compute_work_queue(operator_only_state, []) == [expected_queue[-1]], "coverage or operator-only queue mismatch"))
        terminal_classes = [{item["class"] for item in queue if item["blocking"]} for queue in terminal_queues]
        checks.append(("terminal coverage removes only its sentinel and preserves unadjudicated claims, deferred candidates, closed candidates, and unverified controls", all({"claim_unadjudicated", "deferred_candidate_unreviewed", "candidate_undisposed", "control_candidate_unverified"}.issubset(classes) for classes in terminal_classes) and all("coverage_review_missing" not in classes for classes in terminal_classes), str(terminal_queues)))
        healthy_cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), "ledger-health", "--engagement", str(engagement)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        try: healthy_status = json.loads(healthy_cli.stdout)
        except json.JSONDecodeError: healthy_status = {}
        checks.append(("public ledger health reports a reducible engagement as healthy", healthy_cli.returncode == 0 and healthy_status.get("status") == "healthy" and healthy_status.get("reducible") is True and healthy_status.get("error") is None, healthy_cli.stdout + healthy_cli.stderr))
        invalid_health = root / "invalid-health"; invalid_health.mkdir(); invalid_health.joinpath("scope.md").write_text(scope.replace("self-test", "invalid-health"), encoding="utf-8"); initialize_engagement(invalid_health, "2026-07-10T00:00:01Z")
        sensitive_marker = "health-probe-redaction-" + "x" * 32; invalid_event = copy.deepcopy(read_ledger(invalid_health, "event")[0]); invalid_event["event_type"] = sensitive_marker; invalid_event["record_hash"] = compute_record_hash(invalid_event); (invalid_health / "events.jsonl").write_bytes(canonical_json_bytes(invalid_event))
        invalid_bytes = (invalid_health / "events.jsonl").read_bytes(); raw_read_code = None; raw_reduce_code = None; raw_append_code = None
        try: read_ledger(invalid_health, "event")
        except RecordError as exc: raw_read_code = exc.code
        try: reduce_engagement(invalid_health)
        except RecordError as exc: raw_reduce_code = exc.code
        invalid_proposal = base_event(event_id="event-health-invalid-append", engagement_id=invalid_health.name, recorded_at="2026-07-10T00:00:02Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="observation.recorded", rationale="Prove the existing append refusal remains unchanged.", payload={"entity_id": "invalid-health", "entity_type": "ledger_health_control", "status": "invalid", "reason": "The invalid ledger must refuse mutation."}, session_id="session-health-invalid", operation_class="notebook")
        try: append_event(invalid_health, invalid_proposal)
        except RecordError as exc: raw_append_code = exc.code
        invalid_cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), "ledger-health", "--engagement", str(invalid_health)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        try: invalid_status = json.loads(invalid_cli.stdout)
        except json.JSONDecodeError: invalid_status = {}
        checks.append(("public ledger health reports an invalid ledger as sanitized status without raising", invalid_cli.returncode == 0 and invalid_status.get("status") == "invalid" and invalid_status.get("reducible") is False and invalid_status.get("error", {}).get("code") == raw_reduce_code and invalid_status.get("error", {}).get("details") == [] and sensitive_marker not in (invalid_cli.stdout + invalid_cli.stderr), invalid_cli.stdout + invalid_cli.stderr))
        checks.append(("raw read, reduce, and append paths still refuse the invalid ledger unchanged", raw_read_code == "ledger_schema_invalid" and raw_reduce_code == raw_read_code and raw_append_code == raw_read_code and (invalid_health / "events.jsonl").read_bytes() == invalid_bytes, f"read={raw_read_code} reduce={raw_reduce_code} append={raw_append_code}"))
        unreadable_cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), "ledger-health", "--engagement", str(root / "missing-health")], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        try: unreadable_status = json.loads(unreadable_cli.stdout)
        except json.JSONDecodeError: unreadable_status = {}
        checks.append(("public ledger health distinguishes an unreadable engagement from an invalid ledger", unreadable_cli.returncode == 0 and unreadable_status.get("status") == "unreadable" and unreadable_status.get("reducible") is False and unreadable_status.get("error", {}).get("code") == "ledger_unreadable", unreadable_cli.stdout + unreadable_cli.stderr))
        signature_events=read_ledger(engagement,"event");signature_challenge={"schema_version":1,"namespace":"llm-redteam-harness-operator-v1","engagement_id":engagement.name,"scope_hash":snapshot["scope_hash"],"ledger_hash":signature_events[-1]["record_hash"],"operation":"selftest-signed-operation","operator_id":"operator-selftest"};challenge_path=root/"operator-challenge.json";challenge_path.write_bytes(canonical_json_bytes(signature_challenge));subprocess.run(["/usr/bin/ssh-keygen","-Y","sign","-f",str(reviewer_key),"-n","llm-redteam-harness-operator-v1",str(challenge_path)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);prior_signature=os.environ.get("HARNESS_OPERATOR_SIGNATURE_FILE");prior_signers=os.environ.get("HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE");os.environ["HARNESS_OPERATOR_SIGNATURE_FILE"]=str(challenge_path)+".sig";os.environ["HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE"]=str(allowed_signers_path);signed_gate_passed=True
        try:
            _require_operator_console(engagement,"operator-selftest","selftest-signed-operation");swapped_blocked=False
            try:_require_operator_console(engagement,"operator-selftest","selftest-swapped-operation")
            except RecordError as exc:swapped_blocked=exc.code=="operator_signature_invalid"
            signed_gate_passed=signed_gate_passed and swapped_blocked
        except RecordError:signed_gate_passed=False
        finally:
            if prior_signature is None:os.environ.pop("HARNESS_OPERATOR_SIGNATURE_FILE",None)
            else:os.environ["HARNESS_OPERATOR_SIGNATURE_FILE"]=prior_signature
            if prior_signers is None:os.environ.pop("HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE",None)
            else:os.environ["HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE"]=prior_signers
        checks.append(("scoped SSH signature authorizes only the exact operator challenge",signed_gate_passed,"valid operator signature rejected"))
        denied = root/"zone2-denied"; denied.mkdir(); denied.joinpath("scope.md").write_text(scope.replace("impact_demo_authorized: `yes`", "impact_demo_authorized: `no`").replace("zone2_authorized_categories: `zone2_artifact_creation`", "zone2_authorized_categories: `none`").replace("zone2_escalation_ceiling: `artifact_creation`", "zone2_escalation_ceiling: `none`")); denied_state = initialize_engagement(denied, "2026-07-10T00:00:00Z"); denied_blocked = False
        try: require_scope_zone2_authorized(denied, denied_state["scope_hash"])
        except RecordError as exc: denied_blocked = exc.code == "zone2_not_authorized_by_scope"
        checks.append(("signed scope denial mechanically blocks Zone-2 before confirmation", denied_blocked, "impact-demo denial was ignored"))
        legacy_kernel=root/"legacy-kernel";legacy_kernel.mkdir();legacy_kernel.joinpath("scope.md").write_text(scope.replace("decision-0006-v1","decision-0005-v1"));initialize_engagement(legacy_kernel,"2026-07-10T00:00:00Z");legacy_broker_blocked=False
        try:_require_decision6_kernel(legacy_kernel)
        except RecordError as exc:legacy_broker_blocked=exc.code=="decision6_kernel_not_selected"
        checks.append(("Decision-0005 signed scope cannot invoke Decision-0006 broker authority model",legacy_broker_blocked,"legacy kernel enabled autonomous broker commands"))
        # migrate-kernel: decision-0005 -> decision-0006 with orphan reconciliation, operator-signed.
        mig_root = root / "migrate-kernel-eng"
        mig_root.mkdir()
        mig_scope = scope.replace("self-test", "migrate-kernel-eng").replace("decision-0006-v1", "decision-0005-v1")
        mig_root.joinpath("scope.md").write_text(mig_scope)
        initialize_engagement(mig_root, "2026-07-10T00:00:00Z")
        # create orphan evidence + report draft
        mig_evidence = mig_root / "evidence"
        mig_evidence.mkdir(exist_ok=True)
        mig_evidence.joinpath("orphan-canary.md").write_text("# orphan evidence canary\n", encoding="utf-8")
        mig_reports = mig_root / "reports"
        mig_reports.mkdir(exist_ok=True)
        mig_reports.joinpath("draft-report.md").write_text("# draft report canary\n", encoding="utf-8")
        # 0005 cannot register a finding/report; a 0006-only command must be refused pre-migration
        mig_draft = root / "migrate-kernel-draft.md"
        mig_draft.write_text(scope.replace("self-test", "migrate-kernel-eng"))  # selects decision-0006-v1
        # sign the migration challenge with the operator key
        mig_challenge = {"schema_version": 1, "namespace": "llm-redteam-harness-operator-v1",
                         "engagement_id": mig_root.name, "scope_hash": sha256_file(mig_draft),
                         "source_scope_hash": next(e["payload"]["scope_hash"] for e in reversed(read_ledger(mig_root, "event")) if e["event_type"] == "scope.attested"),
                         "ledger_hash": read_ledger(mig_root, "event")[-1]["record_hash"],
                         "operation": f"migrate-kernel:{sha256_file(mig_draft)}", "operator_id": "operator-selftest"}
        mig_challenge_path = root / "migrate-kernel-challenge.json"
        mig_challenge_path.write_bytes(canonical_json_bytes(mig_challenge))
        subprocess.run(["/usr/bin/ssh-keygen", "-Y", "sign", "-f", str(reviewer_key), "-n", "llm-redteam-harness-operator-v1", str(mig_challenge_path)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        prior_signature = os.environ.get("HARNESS_OPERATOR_SIGNATURE_FILE"); prior_signers = os.environ.get("HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE")
        os.environ["HARNESS_OPERATOR_SIGNATURE_FILE"] = str(mig_challenge_path) + ".sig"
        os.environ["HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE"] = str(allowed_signers_path)
        try:
            mig_result = command_migrate_kernel(argparse.Namespace(
                engagement=mig_root, draft=mig_draft, operator_id="operator-selftest",
                recorded_at="2026-07-10T00:00:02Z", reason="self-test kernel upgrade",
                executor_id="broker-selftest", session_id="session-selftest",
                attest_synthetic=True))
            mig_ok = mig_result == 0
            mig_err = ""
        except RecordError as exc:
            mig_ok = False
            mig_err = exc.code + ": " + str(exc.details)
        finally:
            if prior_signature is None: os.environ.pop("HARNESS_OPERATOR_SIGNATURE_FILE", None)
            else: os.environ["HARNESS_OPERATOR_SIGNATURE_FILE"] = prior_signature
            if prior_signers is None: os.environ.pop("HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE", None)
            else: os.environ["HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE"] = prior_signers
        mig_state = reduce_engagement(mig_root) if mig_ok else None
        mig_attested = mig_state is not None and mig_state["scope_hash"] == sha256_file(mig_draft)
        mig_0006 = mig_state is not None and any(e["event_type"] == "scope.attested" and e["payload"].get("record_kernel") == "decision-0006-v1" for e in read_ledger(mig_root, "event"))
        mig_reconciled = mig_state is not None and not (mig_root / "reports/draft-report.md").exists() and (mig_root / "report-drafts/draft-report.md").is_file()
        mig_artifact = mig_state is not None and any(a["relative_path"] == "evidence/orphan-canary.md" for a in read_ledger(mig_root, "artifact"))
        checks.append(("migrate-kernel upgrades decision-0005 to decision-0006 with orphan reconciliation", mig_ok and mig_attested and mig_0006 and mig_reconciled and mig_artifact, f"mig_ok={mig_ok} attested={mig_attested} 0006={mig_0006} drafts={mig_reconciled} artifact={mig_artifact} err={mig_err}"))
        mig_refuse_bad_source = False
        try:
            command_migrate_kernel(argparse.Namespace(engagement=mig_root, draft=mig_draft, operator_id="operator-selftest", recorded_at="2026-07-10T00:00:03Z", reason="double migration", executor_id="broker-selftest", session_id="session-selftest"))
        except RecordError as exc:
            mig_refuse_bad_source = exc.code == "migrate_kernel_source_invalid"
        checks.append(("migrate-kernel refuses a non-decision-0005 source", mig_refuse_bad_source, "double migration was not refused"))
        migration_tree = root / "migration-tree-symlink"
        migration_source = migration_tree / "engagements" / "source-fixture"
        migration_source.joinpath("nested", "deeper").mkdir(parents=True)
        migration_source.joinpath("scope.md").write_text(scope, encoding="utf-8")
        migration_outside = root / "migration-tree-outside"
        migration_outside.mkdir()
        migration_source.joinpath("nested", "deeper", "redirect").symlink_to(
            migration_outside, target_is_directory=True
        )
        migration_destination = root / "migration-tree-destination"
        migration_destination.mkdir()
        migration_destination.joinpath("scope.md").write_text(scope, encoding="utf-8")
        migration_root_fd = os.open(migration_tree, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        migration_destination_fd = os.open(
            migration_destination, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        )
        migration_nested_symlink_blocked = False
        try:
            try:
                _require_migration_tree_safety(
                    migration_root_fd,
                    migration_destination_fd,
                    canonical_json_bytes({"engagement_id": "source-fixture"}),
                )
            except RecordError as exc:
                migration_nested_symlink_blocked = exc.code == "migration_source_symlink_rejected"
        finally:
            os.close(migration_root_fd)
            os.close(migration_destination_fd)
        checks.append((
            "migration tree safety finds nested symlinks through dirfd recursion",
            migration_nested_symlink_blocked,
            "nested source symlink was skipped",
        ))
        symlink_root = root/"symlink-ledger"; symlink_root.mkdir(); symlink_root.joinpath("scope.md").write_text(scope); outside_ledger = root/"outside-ledger"; outside_ledger.write_bytes(b""); symlink_root.joinpath("events.jsonl").symlink_to(outside_ledger); symlink_ledger_blocked = False
        try: initialize_engagement(symlink_root, "2026-07-10T00:00:00Z")
        except (OSError, RecordError): symlink_ledger_blocked = outside_ledger.read_bytes() == b""
        checks.append(("preexisting ledger symlink is rejected before external append", symlink_ledger_blocked, "ledger symlink redirected a write"))
        symlink_parent_root = root/"symlink-parent"; symlink_parent_root.mkdir(); symlink_parent_root.joinpath("scope.md").write_text(scope); outside_dir = root/"outside-dir"; outside_dir.mkdir(); symlink_parent_root.joinpath("authority").symlink_to(outside_dir, target_is_directory=True); symlink_parent_blocked = False
        try: atomic_write(symlink_parent_root/"authority/requests/action.json", b"{}\n")
        except (OSError, RecordError): symlink_parent_blocked = not any(outside_dir.iterdir())
        checks.append(("preexisting governed parent symlink is rejected before file write", symlink_parent_blocked, "parent symlink redirected a write"))
        root_target = root/"engagement-root-target"; root_target.mkdir(); root_target.joinpath("scope.md").write_text(scope); root_link = root/"engagement-root-link"; root_link.symlink_to(root_target, target_is_directory=True); root_link_blocked = False
        try: initialize_engagement(root_link, "2026-07-10T00:00:00Z")
        except (OSError, RecordError): root_link_blocked = not root_target.joinpath("events.jsonl").exists()
        checks.append(("preexisting engagement-root symlink is rejected before initialization", root_link_blocked, "engagement-root symlink redirected initialization"))
        ancestor_target = root/"ancestor-target"; ancestor_target.mkdir(); ancestor_engagement = ancestor_target/"eng"; ancestor_engagement.mkdir(); ancestor_engagement.joinpath("scope.md").write_text(scope); ancestor_link = root/"ancestor-link"; ancestor_link.symlink_to(ancestor_target, target_is_directory=True); ancestor_identity = ancestor_engagement.stat(); ancestor_alias_bound = False
        try:
            alias_snapshot = initialize_engagement(ancestor_link/"eng", "2026-07-10T00:00:00Z")
            alias_identity = os.stat(ancestor_link/"eng", follow_symlinks=False)
            ancestor_alias_bound = (
                alias_snapshot["engagement_id"] == "eng"
                and (alias_identity.st_dev, alias_identity.st_ino)
                == (ancestor_identity.st_dev, ancestor_identity.st_ino)
                and ancestor_link.is_symlink()
                and ancestor_engagement.joinpath("events.jsonl").is_file()
            )
        except (OSError, RecordError):
            ancestor_alias_bound = False
        checks.append(("intermediate ancestor aliases resolve once and initialize only the bound terminal inode", ancestor_alias_bound, "ancestor alias did not remain bound to the resolved terminal inode"))
        checks.append(("init writes deterministic snapshot and six generated views", (engagement / "state.snapshot.json").read_bytes() == canonical_json_bytes(snapshot) and len(render_views(snapshot)) == 6 and all((engagement / name).is_file() for name in render_views(snapshot)), "missing/stale initialization output"))

        authority_engagement = root / "authority-lanes"; authority_engagement.mkdir(); authority_engagement.joinpath("scope.md").write_text(scope.replace("self-test", "authority-lanes"), encoding="utf-8"); initialize_engagement(authority_engagement, "2026-07-10T00:00:00Z")
        action = _authority_action("test-authority", lane_id="lane-main", value="exact"); action_digest = sha256_bytes(canonical_json_bytes(action)); authority_scope = reduce_engagement(authority_engagement)["scope_hash"]
        request_event = base_event(event_id="event-authority-request-main", engagement_id=authority_engagement.name, recorded_at="2026-07-10T00:00:01Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="authority.requested", rationale="Request one exact lane-local test action.", payload={"request_id": "request-main", "action_kind": "test-authority", "action_digest": action_digest, "lane_id": "lane-main", "request_status": "pending_authority", "scope_hash": authority_scope, "environment_ref": None, "expires_at": "2099-07-10T00:10:00Z"}, session_id="session-authority-request", operation_class="notebook"); append_event(authority_engagement, request_event)
        unrelated = base_event(event_id="event-authority-unrelated", engagement_id=authority_engagement.name, recorded_at="2026-07-10T00:00:02Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="observation.recorded", rationale="Unrelated lane continues while authority is pending.", payload={"entity_id": "unrelated-observation", "entity_type": "observation", "status": "recorded"}, session_id="session-authority-request", operation_class="notebook"); append_event(authority_engagement, unrelated)
        retrospective_blocked = False
        try: require_approved_authority(authority_engagement, "request-main", "test-authority", action_digest, "lane-main", "2026-07-10T00:00:02Z")
        except RecordError as exc: retrospective_blocked = exc.code == "approved_authority_request_required"
        resolution = base_event(event_id="event-authority-resolution-main", engagement_id=authority_engagement.name, recorded_at="2026-07-10T00:00:03Z", actor_role="operator", actor_id="operator-selftest", event_type="authority.resolved", rationale="Approve the exact pending action.", payload={"request_id": "request-main", "request_event_ref": "event-authority-request-main", "action_digest": action_digest, "resolution": "approved", "resolved_at": "2026-07-10T00:00:03Z"}, entity_refs=["event-authority-request-main"], session_id="session-operator-authority", operation_class="authority"); append_event(authority_engagement, resolution)
        exact_approved = require_approved_authority(authority_engagement, "request-main", "test-authority", action_digest, "lane-main", "2026-07-10T00:00:04Z")["status"] == "approved"
        consumed = base_event(event_id="event-authority-consumed", engagement_id=authority_engagement.name, recorded_at="2026-07-10T00:00:04Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="observation.recorded", rationale="Consume the exact approval without changing another lane.", payload={"entity_id": "authority-consumption", "entity_type": "authority_application", "status": "recorded", "authority_request_ref": "request-main"}, session_id="session-authority-request", operation_class="notebook"); append_event(authority_engagement, consumed)
        reuse_blocked = False
        try: require_approved_authority(authority_engagement, "request-main", "test-authority", action_digest, "lane-main", "2026-07-10T00:00:05Z")
        except RecordError as exc: reuse_blocked = exc.code == "authority_request_already_consumed"
        resolutions = (("rejected", "2026-07-10T00:00:07Z", "2026-07-10T00:00:08Z", "2026-07-10T00:10:00Z"), ("expired", "2026-07-10T00:00:09Z", "2026-07-10T00:00:11Z", "2026-07-10T00:00:10Z"), ("superseded", "2026-07-10T00:00:12Z", "2026-07-10T00:00:13Z", "2026-07-10T00:10:00Z"))
        for resolution_name, requested_at, resolved_at, expires in resolutions:
            request_id = f"request-{resolution_name}"; request_ref = f"event-authority-request-{resolution_name}"
            append_event(authority_engagement, base_event(event_id=request_ref, engagement_id=authority_engagement.name, recorded_at=requested_at, actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="authority.requested", rationale=f"Request for {resolution_name} test.", payload={"request_id": request_id, "action_kind": "test-authority", "action_digest": action_digest, "lane_id": f"lane-{resolution_name}", "request_status": "pending_authority", "scope_hash": authority_scope, "environment_ref": None, "expires_at": expires}, session_id=f"session-{resolution_name}", operation_class="notebook"))
            append_event(authority_engagement, base_event(event_id=f"event-authority-resolution-{resolution_name}", engagement_id=authority_engagement.name, recorded_at=resolved_at, actor_role="operator", actor_id="operator-selftest", event_type="authority.resolved", rationale=f"Resolve request as {resolution_name}.", payload={"request_id": request_id, "request_event_ref": request_ref, "action_digest": action_digest, "resolution": resolution_name, "resolved_at": resolved_at}, entity_refs=[request_ref], session_id="session-operator-authority", operation_class="authority"))
        authority_state = reduce_engagement(authority_engagement); states_seen = {item["status"] for item in authority_state["authority_requests"].values()}
        checks.append(("digest-bound async authority is lane-local, non-retrospective, one-use, and state-complete", retrospective_blocked and exact_approved and reuse_blocked and {"approved", "rejected", "expired", "superseded"}.issubset(states_seen), str(authority_state["authority_requests"])))

        invalid = base_event(event_id="event-invalid", engagement_id=engagement.name, recorded_at="2026-07-10T00:01:00Z", actor_role="reviewer", actor_id="reviewer-selftest", event_type="claim.adjudicated", rationale="Invalid direct confirmation must not append.", payload={"entity_id": "claim-1", "status": "confirmed", "review_ref": "review-invalid", "review_digest": "sha256:" + "0" * 64}, state_changes=[{"dimension": "claim", "entity_id": "claim-1", "previous": None, "current": "confirmed"}])
        invalid_caught = False
        before = (engagement / "events.jsonl").read_bytes()
        try:
            append_event(engagement, invalid)
        except RecordError as exc:
            invalid_caught = exc.code in {"invalid_state_transition", "record_reference_invalid"}
        checks.append(("invalid confirmation shortcut is rejected before append", invalid_caught and (engagement / "events.jsonl").read_bytes() == before, "invalid event changed ledger"))
        zero_cost = {"wall_seconds": 0, "model_seconds": 0, "tool_seconds": 0, "target_calls": 0, "model_calls": 0, "input_tokens": None, "output_tokens": None, "cost_usd": None, "human_review_seconds": 0}
        mismatch = base_event(event_id="event-mismatch", engagement_id=engagement.name, recorded_at="2026-07-10T00:01:30Z", actor_role="operator", actor_id="operator-selftest", event_type="candidate.proposed", rationale="Payload/state entity mismatch must fail.", payload={"candidate_id": "candidate-a", "source_observation_ref": "event-source", "routing_review_ref": "event-route", "activation_strength": "strong", "card_ids": ["card-1"], "status": "queued", "expected_information_gain": 1, "safety_class": "clear_local", "cost_estimate": zero_cost}, entity_refs=["event-source", "event-route"], state_changes=[{"dimension": "search", "entity_id": "candidate-b", "previous": None, "current": "queued"}]); mismatch["ex_ante"] = {"probability": 0.5, "ordinal": "strong", "recorded_before_outcome": True}
        mismatch_caught = False
        try:
            append_event(engagement, mismatch)
        except RecordError as exc:
            mismatch_caught = exc.code == "event_state_entity_mismatch"
        checks.append(("event type, payload entity, and state change are inseparable", mismatch_caught and (engagement / "events.jsonl").read_bytes() == before, "mismatched event appended"))

        observation = base_event(event_id="event-observation-c1", engagement_id=engagement.name, recorded_at="2026-07-10T00:01:31Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="observation.recorded", rationale="Bounded source observation.", payload={"entity_id": "observation-c1", "entity_type": "observation", "status": "recorded"})
        append_event(engagement, observation)
        routing = base_event(event_id="event-routing-c1", engagement_id=engagement.name, recorded_at="2026-07-10T00:01:32Z", actor_role="reviewer", actor_id="reviewer-selftest", event_type="routing.assessed", rationale="Signal independently routed to one card.", payload={"entity_id": "routing-c1", "source_observation_ref": "event-observation-c1", "activation_strength": "strong", "card_ids": ["card-selftest"], "status": "assessed"}, entity_refs=["event-observation-c1"])
        append_event(engagement, routing)
        negative_route = base_event(event_id="event-routing-negative", engagement_id=engagement.name, recorded_at="2026-07-10T00:01:32Z", actor_role="reviewer", actor_id="reviewer-selftest", event_type="routing.assessed", rationale="Observed control appears to hold and becomes a positive-control candidate.", payload={"entity_id": "routing-negative", "source_observation_ref": "event-observation-c1", "activation_strength": "negative", "card_ids": ["card-control"], "status": "likely_held"}, entity_refs=["event-observation-c1"])
        append_event(engagement, negative_route)
        candidate = base_event(event_id="event-candidate-c1", engagement_id=engagement.name, recorded_at="2026-07-10T00:01:33Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="candidate.proposed", rationale="Candidate is justified by the routed observation.", payload={"candidate_id": "candidate-c1", "source_observation_ref": "event-observation-c1", "routing_review_ref": "event-routing-c1", "activation_strength": "strong", "card_ids": ["card-selftest"], "status": "queued", "expected_information_gain": 1, "safety_class": "clear_local", "cost_estimate": zero_cost}, entity_refs=["event-observation-c1", "event-routing-c1"], state_changes=[{"dimension": "search", "entity_id": "candidate-c1", "previous": None, "current": "queued"}]); candidate["ex_ante"] = {"probability": 0.6, "ordinal": "strong", "recorded_before_outcome": True}
        append_event(engagement, candidate)
        negative_candidate = json.loads(json.dumps(candidate)); negative_candidate["event_id"] = "event-candidate-negative"; negative_candidate["payload"]["candidate_id"] = "candidate-negative"; negative_candidate["payload"]["activation_strength"] = "negative"; negative_candidate["state_changes"][0]["entity_id"] = "candidate-negative"
        negative_blocked = False
        try:
            append_event(engagement, negative_candidate)
        except RecordError as exc:
            negative_blocked = exc.code == "negative_signal_not_candidate"
        checks.append(("negative routing signal remains a control candidate, never a research candidate", negative_blocked, "negative signal entered candidate queue"))
        selection = base_event(event_id="event-candidate-selected", engagement_id=engagement.name, recorded_at="2026-07-10T00:01:34Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="candidate.selected", rationale="Highest bounded information gain.", payload={"candidate_id": "candidate-c1", "status": "selected", "reason": "highest bounded information gain"}, state_changes=[{"dimension": "search", "entity_id": "candidate-c1", "previous": "queued", "current": "selected"}])
        append_event(engagement, selection)
        hypothesis = base_event(event_id="event-hypothesis-h1", engagement_id=engagement.name, recorded_at="2026-07-10T00:01:35Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="hypothesis.created", rationale="Bounded hypothesis derived from selected candidate.", payload={"hypothesis_id": "hypothesis-h1", "origin_type": "candidate", "origin_ref": "candidate-c1", "candidate_ref": "candidate-c1", "hypothesis_statement": "The local branch omits the expected check.", "suspected_invariant": "The guard should dominate the local state transition.", "trust_boundary": "local caller to guarded state", "attacker_path": ["entry", "branch", "state transition"], "impact_ceiling": "owned fixture only", "bounded_space": "One pinned branch and matched sibling.", "lens_ids": ["authorization"], "card_ids": ["card-selftest"], "expected_confirming_evidence": [{"evidence_type": "trace", "description": "primary guard trace", "required": True}, {"evidence_type": "control", "description": "matched sibling trace", "required": True}], "decisive_falsifiers": ["matched sibling proves the guard is irrelevant"], "cost_estimate": zero_cost, "constraints": ["local only"], "next_experiment": "trace primary and sibling branches", "completion_criteria": ["primary trace", "matched negative control"], "status": "queued"}, entity_refs=["candidate-c1"], state_changes=[{"dimension": "search", "entity_id": "hypothesis-h1", "previous": None, "current": "queued"}])
        append_event(engagement, hypothesis)
        for status, previous, suffix in (("selected", "queued", "selected"), ("running", "selected", "running")):
            change = base_event(event_id=f"event-hypothesis-{suffix}", engagement_id=engagement.name, recorded_at="2026-07-10T00:01:36Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="hypothesis.status_changed", rationale=f"Hypothesis {status} under the bounded search plan.", payload={"hypothesis_id": "hypothesis-h1", "status": status, "reason": "bounded lifecycle", "experiment_refs": [], "control_refs": [], "supporting_evidence_refs": [], "conflicting_evidence_refs": [], "disposition_rationale": f"Hypothesis moved to {status} before execution.", "unresolved_questions": ["execution pending"], "next_route": "primary trace"}, state_changes=[{"dimension": "search", "entity_id": "hypothesis-h1", "previous": previous, "current": status}])
            if status == "running": change["provenance"].update({"session_id": "session-origin-selftest", "model": "origin-model"})
            append_event(engagement, change)
        model_prior = base_event(event_id="event-prior-model", engagement_id=engagement.name, recorded_at="2026-07-10T00:01:37Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="operator_prior.recorded", rationale="A model cannot mint operator authority.", payload={"prior_id": "prior-model", "prior_statement": "Unauthorized prior.", "strength": "strong", "reason": "invalid authority"})
        model_prior_blocked = False
        try:
            append_event(engagement, model_prior)
        except RecordError as exc:
            model_prior_blocked = exc.code == "operator_prior_actor_unauthorized"
        checks.append(("model cannot mint an operator prior", model_prior_blocked, "model prior appended"))
        prior = base_event(event_id="event-prior-p1", engagement_id=engagement.name, recorded_at="2026-07-10T00:01:38Z", actor_role="operator", actor_id="operator-selftest", event_type="operator_prior.recorded", rationale="Operator prior deepens search but proves no claim.", payload={"prior_id": "prior-p1", "prior_statement": "Inspect the sibling branch before declaring dry.", "strength": "strong", "reason": "operator source familiarity"}, entity_refs=["hypothesis-h1"])
        append_event(engagement, prior)
        search_state = reduce_engagement(engagement)
        checks.append(("candidate→selection→hypothesis lifecycle preserves separate search/claim/coverage state", search_state["candidates"]["candidate-c1"]["status"] == "selected" and search_state["hypotheses"]["hypothesis-h1"]["status"] == "running" and len(search_state["operator_priors"]) == 1 and len(search_state["control_candidates"]) == 1 and search_state["findings"] == {} and search_state["coverage"] == "active", str(search_state)))

        candidate_skip_case = root / "candidate-skip-accounting"; candidate_skip_case.mkdir(); candidate_skip_case.joinpath("scope.md").write_text(scope.replace("self-test", "candidate-skip-accounting"), encoding="utf-8"); initialize_engagement(candidate_skip_case, "2026-07-10T00:01:30Z")
        append_event(candidate_skip_case, base_event(event_id="event-skip-observation", engagement_id=candidate_skip_case.name, recorded_at="2026-07-10T00:01:31Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="observation.recorded", rationale="Candidate skip accounting observation.", payload={"entity_id": "observation-skip", "entity_type": "observation", "status": "recorded"}))
        append_event(candidate_skip_case, base_event(event_id="event-skip-routing", engagement_id=candidate_skip_case.name, recorded_at="2026-07-10T00:01:32Z", actor_role="reviewer", actor_id="reviewer-selftest", event_type="routing.assessed", rationale="Route one candidate for skip accounting.", payload={"entity_id": "routing-skip", "source_observation_ref": "event-skip-observation", "activation_strength": "strong", "card_ids": ["card-selftest"], "status": "assessed"}, entity_refs=["event-skip-observation"]))
        skip_candidate = base_event(event_id="event-skip-candidate", engagement_id=candidate_skip_case.name, recorded_at="2026-07-10T00:01:33Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="candidate.proposed", rationale="Propose one candidate whose skip must stay accounted.", payload={"candidate_id": "candidate-skip", "source_observation_ref": "event-skip-observation", "routing_review_ref": "event-skip-routing", "activation_strength": "strong", "card_ids": ["card-selftest"], "status": "queued", "expected_information_gain": 1, "safety_class": "clear_local", "cost_estimate": zero_cost}, entity_refs=["event-skip-observation", "event-skip-routing"], state_changes=[{"dimension": "search", "entity_id": "candidate-skip", "previous": None, "current": "queued"}]); skip_candidate["ex_ante"] = {"probability": 0.5, "ordinal": "strong", "recorded_before_outcome": True}; append_event(candidate_skip_case, skip_candidate)
        append_event(candidate_skip_case, base_event(event_id="event-skip-deferred", engagement_id=candidate_skip_case.name, recorded_at="2026-07-10T00:01:34Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="candidate.deferred", rationale="Defer the candidate for operator disposition.", payload={"candidate_id": "candidate-skip", "status": "deferred", "reason": "bounded prioritization"}, state_changes=[{"dimension": "search", "entity_id": "candidate-skip", "previous": "queued", "current": "deferred"}]))
        append_event(candidate_skip_case, base_event(event_id="event-skip-closed", engagement_id=candidate_skip_case.name, recorded_at="2026-07-10T00:01:35Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="candidate.skipped", rationale="Record the skip without erasing the lead.", payload={"candidate_id": "candidate-skip", "status": "closed", "reason": "bounded prioritization"}, state_changes=[{"dimension": "search", "entity_id": "candidate-skip", "previous": "deferred", "current": "closed"}]))
        skipped_candidate_state = reduce_engagement(candidate_skip_case)
        append_event(candidate_skip_case, base_event(event_id="event-skip-reopened", engagement_id=candidate_skip_case.name, recorded_at="2026-07-10T00:01:36Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="candidate.reopened", rationale="Reopen the exact candidate for explicit routing.", payload={"candidate_id": "candidate-skip", "status": "selected", "reason": "Reopen the exact candidate for explicit routing."}, state_changes=[{"dimension": "search", "entity_id": "candidate-skip", "previous": "closed", "current": "selected"}]))
        reopened_candidate_state = reduce_engagement(candidate_skip_case)
        routed_payload = json.loads(json.dumps(hypothesis["payload"])); routed_payload.update({"hypothesis_id": "hypothesis-from-skipped-candidate", "origin_ref": "candidate-skip", "candidate_ref": "candidate-skip", "status": "queued"})
        append_event(candidate_skip_case, base_event(event_id="event-skip-hypothesis", engagement_id=candidate_skip_case.name, recorded_at="2026-07-10T00:01:37Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="hypothesis.created", rationale="Route the retained candidate into explicit work.", payload=routed_payload, entity_refs=["candidate-skip"], state_changes=[{"dimension": "search", "entity_id": "hypothesis-from-skipped-candidate", "previous": None, "current": "queued"}]))
        routed_candidate_state = reduce_engagement(candidate_skip_case)
        candidate_debt = lambda value: [item for item in value["work_queue"] if item["class"] == "candidate_undisposed" and item["entity"]["id"] == "candidate-skip"]
        skipped_candidate_action = decorate_work_queue_item(
            candidate_debt(skipped_candidate_state)[0],
            skipped_candidate_state,
            candidate_skip_case,
        )["next_action"]
        reopened_candidate_action = decorate_work_queue_item(
            candidate_debt(reopened_candidate_state)[0],
            reopened_candidate_state,
            candidate_skip_case,
        )["next_action"]
        checks.append(("a skipped candidate remains blocking through close and reopen until an explicit candidate-origin hypothesis accounts for it", len(candidate_debt(skipped_candidate_state)) == 1 and len(candidate_debt(reopened_candidate_state)) == 1 and not candidate_debt(routed_candidate_state), str((skipped_candidate_state["work_queue"], reopened_candidate_state["work_queue"], routed_candidate_state["work_queue"]))))
        checks.append(("the feedback loop reopens a closed candidate before offering hypothesis creation, so free-text skip cannot bypass lifecycle accounting", skipped_candidate_action["action_id"] == "reopen_candidate" and skipped_candidate_action["effect"] == "advances_item" and reopened_candidate_action["action_id"] == "create_candidate_hypothesis" and reopened_candidate_action["effect"] == "closes_item", str((skipped_candidate_action, reopened_candidate_action))))

        mediation_case = root / "queue-action-broker-mediation"; shutil.copytree(engagement, mediation_case)
        # Attempts are admissible only against an environment that was active at
        # their immutable recorded time.  Keep this action-contract fixture
        # self-contained instead of relying on the main lifecycle's later
        # preflight setup.
        mediation_package = root / "mediation-package-fixture.bin"; mediation_package.write_bytes(b"broker mediation fixture\n")
        mediation_runtime = Path(sys.executable).resolve()
        collect_preflight(mediation_case, preflight_id="preflight-broker-mediation", mode="package", target=mediation_package, expected_identity=sha256_file(mediation_package), runtime=mediation_runtime, reproduction_argv=[str(mediation_runtime), "-c", "pass"], operator_id="operator-selftest", recorded_at="2026-07-10T00:01:38.500000Z", operator_redaction_attested=True, endpoint_identity="local", account_role="owner")
        mediation_broker_id, mediation_broker_session = _local_identity("broker")
        def execute_emitted_file_action(action: dict[str, Any], proposal_path: Path) -> subprocess.CompletedProcess[str]:
            argv = list(action["local_invocation"]["argv"])
            argv[argv.index("--file") + 1] = str(proposal_path)
            return subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)

        mediation_state = reduce_engagement(mediation_case)
        mediation_control_item = next(item for item in mediation_state["work_queue"] if item["class"] == "control_candidate_unverified" and item["entity"]["id"] == "event-routing-negative")
        mediation_create_action = decorate_work_queue_item(mediation_control_item, mediation_state, mediation_case)["next_action"]
        mediation_hypothesis = base_event(event_id="event-control-hypothesis-created", engagement_id=engagement.name, recorded_at="2026-07-10T00:01:39Z", actor_role="broker", actor_id=mediation_broker_id, event_type="hypothesis.created", rationale="Broker records the orchestrator's bounded matched-control hypothesis.", payload={"hypothesis_id": "hypothesis-control", "origin_type": "reviewer_challenge", "origin_ref": "event-routing-negative", "hypothesis_statement": "The likely-held route should remain held under one matched bounded control.", "suspected_invariant": "The negative route's guard should reject the matched primary condition.", "trust_boundary": "owned fixture input to guarded branch", "attacker_path": ["owned fixture", "guarded branch"], "impact_ceiling": "owned fixture only", "bounded_space": "One matched primary and one negative control.", "lens_ids": ["authorization"], "card_ids": ["card-control"], "expected_confirming_evidence": [{"evidence_type": "control", "description": "matched control remains held", "required": True}], "decisive_falsifiers": ["matched control exhibits the primary signal"], "cost_estimate": zero_cost, "constraints": ["local only"], "next_experiment": "record matched primary then negative control", "completion_criteria": ["primary and linked control recorded"], "status": "queued"}, entity_refs=["event-routing-negative"], state_changes=[{"dimension": "search", "entity_id": "hypothesis-control", "previous": None, "current": "queued"}], session_id=mediation_broker_session, operation_class="notebook")
        mediation_create_path = root / "mediation-control-hypothesis.json"; mediation_create_path.write_bytes(canonical_json_bytes(mediation_hypothesis)); mediation_create_cli = execute_emitted_file_action(mediation_create_action, mediation_create_path)

        mediation_stage_results = []
        for status, previous, recorded_at in (("selected", "queued", "2026-07-10T00:01:40Z"), ("running", "selected", "2026-07-10T00:01:41Z")):
            mediation_state = reduce_engagement(mediation_case)
            mediation_control_item = next(item for item in mediation_state["work_queue"] if item["class"] == "control_candidate_unverified" and item["entity"]["id"] == "event-routing-negative")
            mediation_stage_action = decorate_work_queue_item(mediation_control_item, mediation_state, mediation_case)["next_action"]
            mediation_transition = base_event(event_id=f"event-control-hypothesis-{status}", engagement_id=engagement.name, recorded_at=recorded_at, actor_role="broker", actor_id=mediation_broker_id, event_type="hypothesis.status_changed", rationale=f"Broker records bounded control hypothesis {status}.", payload={"hypothesis_id": "hypothesis-control", "status": status, "reason": "bounded control progression", "experiment_refs": [], "control_refs": [], "supporting_evidence_refs": [], "conflicting_evidence_refs": [], "disposition_rationale": "Advance only the current matched-control stage.", "unresolved_questions": [], "next_route": "matched control"}, state_changes=[{"dimension": "search", "entity_id": "hypothesis-control", "previous": previous, "current": status}], session_id=mediation_broker_session, operation_class="notebook")
            mediation_transition_path = root / f"mediation-control-{status}.json"; mediation_transition_path.write_bytes(canonical_json_bytes(mediation_transition)); mediation_stage_results.append(execute_emitted_file_action(mediation_stage_action, mediation_transition_path))

        def mediated_control_attempt(attempt_id: str, recorded_at: str, kind: str, assessment: str, control_of: list[str]) -> dict[str, Any]:
            return {"schema_version": 2, "attempt_id": attempt_id, "engagement_id": engagement.name, "recorded_at": recorded_at, "actor": {"role": "broker", "id": mediation_broker_id}, "operation_class": "notebook", "provenance": {"actor": {"role": "broker", "id": mediation_broker_id}, "provider": "selftest", "model": "broker-recorder", "prompt_version": "queue-action-selftest", "tool_versions": ["source-inspection-v1"], "card_versions": ["card-control"], "session_id": mediation_broker_session}, "scope_hash": mediation_state["scope_hash"], "environment_ref": mediation_state["active_environment_ref"], "escalation_confirmation_event_ref": None, "hypothesis_ref": "hypothesis-control", "experiment_ref": "event-routing-negative", "surface": "owned local fixture", "action_summary": "Record one bounded matched-control observation.", "redaction_attestation": True, "observation": {"source": "broker", "statement": "Matched control observation recorded by the broker from the bounded hunter result."}, "evidence_refs": [], "kind": kind, "control_of": control_of, "assessment": assessment, "contamination": {"status": "none_observed", "sources": [], "note": ""}, "cost": {**zero_cost, "wall_seconds": 1, "tool_seconds": 1}}

        mediation_state = reduce_engagement(mediation_case)
        mediation_control_item = next(item for item in mediation_state["work_queue"] if item["class"] == "control_candidate_unverified" and item["entity"]["id"] == "event-routing-negative")
        mediation_primary_action = decorate_work_queue_item(mediation_control_item, mediation_state, mediation_case)["next_action"]
        mediation_primary = mediated_control_attempt("attempt-control-primary", "2026-07-10T00:01:42Z", "primary", "suspected_signal", []); mediation_primary_path = root / "mediation-control-primary.json"; mediation_primary_path.write_bytes(canonical_json_bytes(mediation_primary)); mediation_primary_cli = execute_emitted_file_action(mediation_primary_action, mediation_primary_path)
        mediation_state = reduce_engagement(mediation_case)
        mediation_control_item = next(item for item in mediation_state["work_queue"] if item["class"] == "control_candidate_unverified" and item["entity"]["id"] == "event-routing-negative")
        mediation_control_action = decorate_work_queue_item(mediation_control_item, mediation_state, mediation_case)["next_action"]
        mediation_control = mediated_control_attempt("attempt-control-negative", "2026-07-10T00:01:43Z", "negative_control", "held", ["attempt-control-primary"]); mediation_control_path = root / "mediation-control-negative.json"; mediation_control_path.write_bytes(canonical_json_bytes(mediation_control)); mediation_control_cli = execute_emitted_file_action(mediation_control_action, mediation_control_path)
        mediation_final_state = reduce_engagement(mediation_case)
        checks.append(("advertised staged control actions execute under broker mediation while retaining orchestrator and hunter cognitive principals", mediation_create_cli.returncode == 0 and all(result.returncode == 0 for result in mediation_stage_results) and mediation_primary_cli.returncode == 0 and mediation_control_cli.returncode == 0 and mediation_create_action["principal"] == "orchestrator" and mediation_create_action["execution_principal"] == "broker" and mediation_primary_action["principal"] == "hunter" and mediation_primary_action["execution_principal"] == "broker" and mediation_control_action["principal"] == "hunter" and not any(item["class"] == "control_candidate_unverified" and item["entity"]["id"] == "event-routing-negative" for item in mediation_final_state["work_queue"]), str({"create": mediation_create_cli.stdout + mediation_create_cli.stderr, "stages": [(item.returncode, item.stdout, item.stderr) for item in mediation_stage_results], "primary": mediation_primary_cli.stdout + mediation_primary_cli.stderr, "control": mediation_control_cli.stdout + mediation_control_cli.stderr, "queue": mediation_final_state["work_queue"]})))

        blocked = base_event(event_id="event-blocked", engagement_id=engagement.name, recorded_at="2026-07-10T00:02:00Z", actor_role="operator", actor_id="operator-selftest", event_type="engagement.blocked", rationale="Self-test blocker.", payload={"entity_id": engagement.name, "status": "blocked", "reason": "fixture"}, state_changes=[{"dimension": "engagement", "entity_id": engagement.name, "previous": "active", "current": "blocked"}, {"dimension": "coverage", "entity_id": engagement.name, "previous": "active", "current": "blocked"}])
        try:
            append_event(engagement, blocked)
            ordinary_block_code = None
        except RecordError as exc:
            ordinary_block_code = exc.code
        pre_override_state = reduce_engagement(engagement)
        override_projection = project_current_terminal_work_state(
            pre_override_state,
            read_ledger(engagement, "attempt"),
            coverage="blocked",
        )
        override_blockers = blocking_work_identities(override_projection)
        blocked_override_reason = "Self-test blocker with exact unfinished work recorded."
        blocked_override_time = "2026-07-10T00:02:00Z"
        blocked_override_session = _local_identity("operator")[1]
        blocked_override_payload = {
            "entity_id": engagement.name,
            "terminal_kind": "engagement",
            "status": "blocked",
            "reason": blocked_override_reason,
            "operator_id": "operator-selftest",
            "scope_hash": pre_override_state["scope_hash"],
            "blocking_items": override_blockers,
            "blocking_queue_digest": sha256_bytes(canonical_json_bytes(override_blockers)),
            **attempt_ledger_context(read_ledger(engagement, "attempt")),
        }
        blocked_override_changes = [
            {"dimension": "engagement", "entity_id": engagement.name, "previous": "active", "current": "blocked"},
            {"dimension": "coverage", "entity_id": engagement.name, "previous": "active", "current": "blocked"},
        ]
        blocked_override_action = ending_override_action(
            engagement_id=engagement.name,
            recorded_at=blocked_override_time,
            actor={"role": "operator", "id": "operator-selftest"},
            payload=blocked_override_payload,
            entity_refs=[],
            evidence_refs=[],
            state_changes=blocked_override_changes,
            session_id=blocked_override_session,
        )
        blocked_override_action_digest = sha256_bytes(canonical_json_bytes(blocked_override_action))
        blocked_override_challenge = operator_challenge_bytes(
            engagement_id=engagement.name,
            scope_hash=pre_override_state["scope_hash"],
            ledger_hash=read_ledger(engagement, "event")[-1]["record_hash"],
            operation=f"override-ending:{blocked_override_action_digest}",
            operator_id="operator-selftest",
        )
        forged_payload = copy.deepcopy(blocked_override_payload)
        forged_payload["operator_signature"] = {
            "challenge_digest": sha256_bytes(blocked_override_challenge),
            "signature_base64": base64.b64encode(b"forged-signature").decode("ascii"),
            "allowed_signers_base64": base64.b64encode(allowed_signers_path.read_bytes()).decode("ascii"),
            "signer_fingerprint": "sha256:" + "0" * 64,
        }
        forged_override = base_event(
            event_id=f"event-ending-override-{blocked_override_action_digest[-12:]}",
            engagement_id=engagement.name,
            recorded_at=blocked_override_time,
            actor_role="operator",
            actor_id="operator-selftest",
            event_type="engagement.ending_overridden",
            rationale=blocked_override_reason,
            payload=forged_payload,
            state_changes=blocked_override_changes,
            session_id=blocked_override_session,
            operation_class="authority",
        )
        before_forged_override = (engagement / "events.jsonl").read_bytes()
        try:
            append_event(engagement, forged_override)
            forged_override_code = None
        except RecordError as exc:
            forged_override_code = exc.code
        forged_override_left_ledger_unchanged = (
            engagement / "events.jsonl"
        ).read_bytes() == before_forged_override
        blocked_override_challenge_path = root / "blocked-ending-override-challenge.json"
        blocked_override_challenge_path.write_bytes(blocked_override_challenge)
        subprocess.run(
            [
                "/usr/bin/ssh-keygen", "-q", "-Y", "sign",
                "-f", str(reviewer_key),
                "-n", "llm-redteam-harness-operator-v1",
                str(blocked_override_challenge_path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        blocked_override_argv = [
            sys.executable,
            str(Path(__file__).resolve()),
            "override-ending",
            "--engagement", str(engagement),
            "--terminal-kind", "engagement",
            "--status", "blocked",
            "--operator-id", "operator-selftest",
            "--session-id", blocked_override_session,
            "--recorded-at", blocked_override_time,
            "--reason", blocked_override_reason,
        ]
        blocked_override_env = {
            **os.environ,
            "HARNESS_OPERATOR_SIGNATURE_FILE": str(blocked_override_challenge_path) + ".sig",
            "HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE": str(allowed_signers_path),
        }
        blocked_override_cli = subprocess.run(
            blocked_override_argv,
            env=blocked_override_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        reduced_once = reduce_engagement(engagement)
        reduced_twice = reduce_engagement(engagement)
        override_retry_case = root / "ending-override-retry"; shutil.copytree(engagement, override_retry_case)
        override_retry_argv = list(blocked_override_argv)
        override_retry_argv[override_retry_argv.index(str(engagement))] = str(override_retry_case)
        exact_blocked_override_retry = subprocess.run(override_retry_argv, env=blocked_override_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        try:
            exact_blocked_override_retry_payload = json.loads(exact_blocked_override_retry.stdout)
        except json.JSONDecodeError:
            exact_blocked_override_retry_payload = {}
        changed_blocked_override_retry = subprocess.run([*override_retry_argv, "--coverage-review-ref", "review-changed-after-signing"], env=blocked_override_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        override_retry_count = len(read_ledger(override_retry_case, "event"))
        _append_kernel_event(override_retry_case, base_event(
            event_id="event-ending-override-reopened",
            engagement_id=engagement.name,
            recorded_at="2026-07-10T00:02:00.500000Z",
            actor_role="operator",
            actor_id="operator-selftest",
            event_type="engagement.reopened",
            rationale="Reopen the synthetic fixture to prove an old override cannot self-apply again.",
            payload={"entity_id": engagement.name, "status": "active", "operator_id": "operator-selftest"},
            state_changes=[
                {"dimension": "engagement", "entity_id": engagement.name, "previous": "blocked", "current": "active"},
                {"dimension": "coverage", "entity_id": engagement.name, "previous": "blocked", "current": "active"},
            ],
            operation_class="authority",
        ))
        reopened_blocked_override_retry = subprocess.run(override_retry_argv, env=blocked_override_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        reopened_override_state = reduce_engagement(override_retry_case)
        checks.append(("reducer is byte-deterministic", canonical_json_bytes(reduced_once) == canonical_json_bytes(reduced_twice), "same ledgers reduced differently"))
        checks.append(("coverage cannot leave active with blocking work unless the reducer verifies an exact operator-signed first-class override", ordinary_block_code == "coverage_terminal_work_remaining" and forged_override_code == "operator_signature_invalid" and forged_override_left_ledger_unchanged and blocked_override_cli.returncode == 0 and reduced_once["coverage"] == "blocked" and reduced_once["active_blockers"] and reduced_once["ending_overrides"][-1]["blocking_items"] == override_blockers, str({"ordinary": ordinary_block_code, "forged": forged_override_code, "forged_ledger_unchanged": forged_override_left_ledger_unchanged, "cli": blocked_override_cli.stdout + blocked_override_cli.stderr, "state": reduced_once})))
        checks.append((
            "ending override idempotency accepts only the exact unchanged tail and cannot return false success after changed inputs or reopen",
            exact_blocked_override_retry.returncode == 0
            and exact_blocked_override_retry_payload.get("override") == reduced_once["ending_overrides"][-1]
            and "allowed_signers_base64" not in exact_blocked_override_retry.stdout
            and "signature_base64" not in exact_blocked_override_retry.stdout
            and changed_blocked_override_retry.returncode != 0
            and override_retry_count == len(read_ledger(override_retry_case, "event")) - 1
            and reopened_blocked_override_retry.returncode != 0
            and reopened_override_state["coverage"] == "active"
            and not reopened_override_state["active_blockers"]
            and len(reopened_override_state["ending_overrides"]) == len(reduced_once["ending_overrides"]),
            str({"exact": exact_blocked_override_retry.stdout + exact_blocked_override_retry.stderr, "changed": changed_blocked_override_retry.stdout + changed_blocked_override_retry.stderr, "reopened": reopened_blocked_override_retry.stdout + reopened_blocked_override_retry.stderr, "state": reopened_override_state}),
        ))

        secret_signers_path = root / "allowed-signers-with-secret-comment"
        secret_signers_path.write_bytes(allowed_signers_path.read_bytes() + b"# password=synthetic-secret-value\n")
        secret_signers_digest = sha256_file(secret_signers_path)
        secret_signers_case = root / "secret-signers-override"
        secret_signers_case.mkdir()
        secret_signers_case.joinpath("scope.md").write_text(
            scope.replace(allowed_signers_digest, secret_signers_digest),
            encoding="utf-8",
        )
        initialize_engagement(secret_signers_case, "2026-07-10T00:00:00Z")
        secret_prior = base_event(
            event_id="event-secret-signers-prior",
            engagement_id=secret_signers_case.name,
            recorded_at="2026-07-10T00:00:01Z",
            actor_role="operator",
            actor_id="operator-selftest",
            event_type="operator_prior.recorded",
            rationale="Seed one bounded hypothesis so an ending override is required.",
            payload={"prior_id": "prior-secret-signers", "prior_statement": "The bounded fixture branch requires adjudication.", "strength": "strong", "reason": "secret-signers self-test setup"},
        )
        append_event(secret_signers_case, secret_prior)
        secret_hypothesis_payload = json.loads(json.dumps(hypothesis["payload"]))
        secret_hypothesis_payload.update({"hypothesis_id": "hypothesis-secret-signers", "origin_type": "operator_prior", "origin_ref": secret_prior["event_id"], "status": "queued"})
        secret_hypothesis_payload.pop("candidate_ref", None)
        append_event(secret_signers_case, base_event(
            event_id="event-secret-signers-hypothesis",
            engagement_id=secret_signers_case.name,
            recorded_at="2026-07-10T00:00:02Z",
            actor_role="orchestrator",
            actor_id="orchestrator-selftest",
            event_type="hypothesis.created",
            rationale="Create one bounded blocking hypothesis for the secret-signers regression.",
            payload=secret_hypothesis_payload,
            entity_refs=[secret_prior["event_id"]],
            state_changes=[{"dimension": "search", "entity_id": "hypothesis-secret-signers", "previous": None, "current": "queued"}],
        ))
        secret_signers_state = reduce_engagement(secret_signers_case)
        secret_signers_attempts = read_ledger(secret_signers_case, "attempt")
        secret_signers_blockers = blocking_work_identities(project_current_terminal_work_state(secret_signers_state, secret_signers_attempts, coverage="blocked"))
        secret_signers_time = "2026-07-10T00:00:03Z"
        secret_signers_reason = "Operator accepts the exact bounded residual queue for this redaction regression."
        secret_signers_session = _local_identity("operator")[1]
        secret_signers_payload = {
            "entity_id": secret_signers_case.name,
            "terminal_kind": "engagement",
            "status": "blocked",
            "reason": secret_signers_reason,
            "operator_id": "operator-selftest",
            "scope_hash": secret_signers_state["scope_hash"],
            "blocking_items": secret_signers_blockers,
            "blocking_queue_digest": sha256_bytes(canonical_json_bytes(secret_signers_blockers)),
            **attempt_ledger_context(secret_signers_attempts),
        }
        secret_signers_action = ending_override_action(
            engagement_id=secret_signers_case.name,
            recorded_at=secret_signers_time,
            actor={"role": "operator", "id": "operator-selftest"},
            payload=secret_signers_payload,
            entity_refs=[],
            evidence_refs=[],
            state_changes=[
                {"dimension": "engagement", "entity_id": secret_signers_case.name, "previous": "active", "current": "blocked"},
                {"dimension": "coverage", "entity_id": secret_signers_case.name, "previous": "active", "current": "blocked"},
            ],
            session_id=secret_signers_session,
        )
        secret_signers_action_digest = sha256_bytes(canonical_json_bytes(secret_signers_action))
        secret_signers_challenge = operator_challenge_bytes(
            engagement_id=secret_signers_case.name,
            scope_hash=secret_signers_state["scope_hash"],
            ledger_hash=read_ledger(secret_signers_case, "event")[-1]["record_hash"],
            operation=f"override-ending:{secret_signers_action_digest}",
            operator_id="operator-selftest",
        )
        secret_signers_challenge_path = root / "secret-signers-override-challenge.json"
        secret_signers_challenge_path.write_bytes(secret_signers_challenge)
        subprocess.run(["/usr/bin/ssh-keygen", "-q", "-Y", "sign", "-f", str(reviewer_key), "-n", "llm-redteam-harness-operator-v1", str(secret_signers_challenge_path)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        secret_signers_before = (secret_signers_case / "events.jsonl").read_bytes()
        secret_signers_cli = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "override-ending", "--engagement", str(secret_signers_case), "--terminal-kind", "engagement", "--status", "blocked", "--operator-id", "operator-selftest", "--session-id", secret_signers_session, "--recorded-at", secret_signers_time, "--reason", secret_signers_reason],
            env={**os.environ, "HARNESS_OPERATOR_SIGNATURE_FILE": str(secret_signers_challenge_path) + ".sig", "HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE": str(secret_signers_path)},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        try:
            secret_signers_error = json.loads(secret_signers_cli.stdout)["error"]["code"]
        except (json.JSONDecodeError, KeyError):
            secret_signers_error = None
        secret_signers_embedded_payload = copy.deepcopy(secret_signers_payload)
        secret_signers_embedded_payload["operator_signature"] = encode_operator_signature_proof(
            challenge_bytes=secret_signers_challenge,
            signature_bytes=Path(str(secret_signers_challenge_path) + ".sig").read_bytes(),
            allowed_signers_bytes=secret_signers_path.read_bytes(),
            signer_fingerprint=reduced_once["ending_overrides"][-1]["operator_signer_fingerprint"],
        )
        secret_signers_embedded_event = base_event(
            event_id=f"event-ending-override-{secret_signers_action_digest[-12:]}",
            engagement_id=secret_signers_case.name,
            recorded_at=secret_signers_time,
            actor_role="operator",
            actor_id="operator-selftest",
            event_type="engagement.ending_overridden",
            rationale=secret_signers_reason,
            payload=secret_signers_embedded_payload,
            state_changes=[
                {"dimension": "engagement", "entity_id": secret_signers_case.name, "previous": "active", "current": "blocked"},
                {"dimension": "coverage", "entity_id": secret_signers_case.name, "previous": "active", "current": "blocked"},
            ],
            session_id=secret_signers_session,
            operation_class="authority",
        )
        try:
            _append_kernel_event(secret_signers_case, secret_signers_embedded_event)
            secret_signers_replay_error = None
        except RecordError as exc:
            secret_signers_replay_error = exc.code
        checks.append((
            "operator ending override construction and replay refuse secret-shaped raw signer material",
            secret_signers_blockers
            and secret_signers_cli.returncode != 0
            and secret_signers_error == "operator_signature_invalid"
            and secret_signers_replay_error == "operator_signature_invalid"
            and (secret_signers_case / "events.jsonl").read_bytes() == secret_signers_before
            and "synthetic-secret-value" not in secret_signers_cli.stdout + secret_signers_cli.stderr,
            secret_signers_cli.stdout + secret_signers_cli.stderr + str(secret_signers_replay_error),
        ))

        def run_signed_queue_commands(target: Path, command_name: str, previous_status: str, status: str, recorded_at: str, reason: str, *, concurrency: int = 1) -> list[subprocess.CompletedProcess[str]]:
            session_id = _local_identity("operator")[1]
            target_state = reduce_engagement(target); target_events = read_ledger(target, "event")
            action = {"command": command_name, "entity_id": target_state["engagement_id"], "previous_status": previous_status, "reason": reason, "recorded_at": recorded_at, "session_id": session_id, "status": status}
            action_digest = sha256_bytes(canonical_json_bytes(action))
            challenge = {"schema_version": 1, "namespace": "llm-redteam-harness-operator-v1", "engagement_id": target_state["engagement_id"], "scope_hash": target_state["scope_hash"], "ledger_hash": target_events[-1]["record_hash"], "operation": f"{command_name}:{action_digest}", "operator_id": "operator-selftest"}
            challenge_path = root / f"{command_name}-challenge.json"; challenge_path.write_bytes(canonical_json_bytes(challenge))
            subprocess.run(["/usr/bin/ssh-keygen", "-q", "-Y", "sign", "-f", str(reviewer_key), "-n", "llm-redteam-harness-operator-v1", str(challenge_path)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            command_env = {**os.environ, "HARNESS_OPERATOR_SIGNATURE_FILE": str(challenge_path) + ".sig", "HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE": str(allowed_signers_path)}
            argv = [sys.executable, str(Path(__file__).resolve()), command_name, "--engagement", str(target), "--operator-id", "operator-selftest", "--session-id", session_id, "--recorded-at", recorded_at, "--reason", reason]
            processes = [subprocess.Popen(argv, env=command_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(concurrency)]
            results = []
            for process in processes:
                stdout, stderr = process.communicate(timeout=30)
                results.append(subprocess.CompletedProcess(argv, process.returncode, stdout, stderr))
            return results

        operator_control = root / "operator-control"; shutil.copytree(engagement, operator_control)
        stop_reason = "Operator deliberately parks this bounded run for an external scheduling decision."
        stop_clis = run_signed_queue_commands(operator_control, "operator-stop", "active", "parked", "2026-07-10T00:02:00.100000Z", stop_reason, concurrency=4)
        stopped_state = reduce_engagement(operator_control); stopped_events = read_ledger(operator_control, "event"); stopped_progress = (operator_control / "progress.md").read_text(encoding="utf-8")
        stopped_control = stopped_state.get("queue_control", {})
        stop_detail = "".join(result.stdout + result.stderr for result in stop_clis) + str(stopped_control)
        checks.append(("concurrent signed operator-stop retries all succeed and append one typed reason without pretending the run exhausted", all(result.returncode == 0 for result in stop_clis) and sum(event["event_type"] == "operator_stop.recorded" for event in stopped_events) == 1 and stopped_control.get("status") == "parked" and stopped_control.get("last_stop", {}).get("reason") == stop_reason and stopped_events[-1]["event_type"] == "operator_stop.recorded" and stopped_state["coverage"] == "blocked" and "Work queue: `parked`" in stopped_progress and stop_reason in stopped_progress, stop_detail))

        resume_reason = "The operator's scheduling constraint is resolved."
        resume_cli = run_signed_queue_commands(operator_control, "operator-resume", "parked", "active", "2026-07-10T00:02:00.200000Z", resume_reason)[0]
        resumed_state = reduce_engagement(operator_control); resumed_events = read_ledger(operator_control, "event"); resumed_control = resumed_state.get("queue_control", {})
        checks.append(("signed operator resume makes the parked queue runnable while preserving the stop/resume record", resume_cli.returncode == 0 and resumed_control.get("status") == "active" and resumed_control.get("last_stop", {}).get("reason") == stop_reason and resumed_control.get("last_resume", {}).get("reason") == resume_reason and [event["event_type"] for event in resumed_events[-2:]] == ["operator_stop.recorded", "operator_resume.recorded"] and resumed_state["coverage"] == "blocked", resume_cli.stdout + resume_cli.stderr + str(resumed_control)))

        forged_control = root / "forged-operator-control"; shutil.copytree(engagement, forged_control); forged_before = (forged_control / "events.jsonl").read_bytes()
        forged_stop = base_event(event_id="event-forged-operator-stop", engagement_id=engagement.name, recorded_at="2026-07-10T00:02:00.100000Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="operator_stop.recorded", rationale="An orchestrator cannot manufacture an operator stop.", payload={"entity_id": engagement.name, "status": "parked", "reason": "An orchestrator cannot manufacture an operator stop.", "operator_id": "operator-selftest"}, state_changes=[{"dimension": "queue", "entity_id": engagement.name, "previous": "active", "current": "parked"}], session_id="session-orchestrator-selftest", operation_class="authority")
        forged_stop_blocked = False
        try: append_event(forged_control, forged_stop)
        except RecordError as exc: forged_stop_blocked = exc.code in {"actor_capability_invalid", "operator_queue_control_invalid"}
        checks.append(("non-operator principals cannot manufacture the deliberate-stop record", forged_stop_blocked and (forged_control / "events.jsonl").read_bytes() == forged_before and reduce_engagement(forged_control)["queue_control"]["status"] == "active", "forged operator stop changed the ledger"))

        budget_documents = test_corpus_documents(
            row_count=5,
            frozen_at="2026-07-09T23:59:00Z",
        )
        budget_base = root / "budget-base"; budget_base.mkdir(); budget_base.joinpath("scope.md").write_text(scope_with_corpus_pin(scope.replace("self-test", "budget-base"), budget_documents[1]), encoding="utf-8"); initialize_engagement(budget_base, "2026-07-10T00:00:00Z")
        budget_prior = base_event(event_id="event-budget-prior", engagement_id=budget_base.name, recorded_at="2026-07-10T00:00:01Z", actor_role="operator", actor_id="operator-selftest", event_type="operator_prior.recorded", rationale="Seed one already-disposed hypothesis for the reopening control.", payload={"prior_id": "prior-budget", "prior_statement": "The bounded fixture branch was already resolved.", "strength": "strong", "reason": "self-test setup"})
        append_event(budget_base, budget_prior)
        budget_hypothesis_payload = json.loads(json.dumps(hypothesis["payload"])); budget_hypothesis_payload.update({"hypothesis_id": "hypothesis-budget", "origin_type": "operator_prior", "origin_ref": "event-budget-prior", "status": "queued"}); budget_hypothesis_payload.pop("candidate_ref", None)
        append_event(budget_base, base_event(event_id="event-budget-hypothesis", engagement_id=budget_base.name, recorded_at="2026-07-10T00:00:02Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="hypothesis.created", rationale="Create the bounded reopening-control hypothesis.", payload=budget_hypothesis_payload, entity_refs=["event-budget-prior"], state_changes=[{"dimension": "search", "entity_id": "hypothesis-budget", "previous": None, "current": "queued"}]))
        append_event(budget_base, base_event(event_id="event-budget-hypothesis-closed", engagement_id=budget_base.name, recorded_at="2026-07-10T00:00:03Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="hypothesis.status_changed", rationale="Dispose the bounded setup hypothesis before terminal coverage.", payload={"hypothesis_id": "hypothesis-budget", "status": "closed", "reason": "setup disposed", "experiment_refs": [], "control_refs": [], "supporting_evidence_refs": [], "conflicting_evidence_refs": [], "disposition_rationale": "The synthetic setup branch is already disposed.", "unresolved_questions": [], "next_route": None}, state_changes=[{"dimension": "search", "entity_id": "hypothesis-budget", "previous": "queued", "current": "closed"}]))
        budget_manifest_ref, budget_tsv_ref = register_test_corpus(
            budget_base,
            row_count=5,
            documents=budget_documents,
        )
        budget_bounded = root / "budget-bounded"; shutil.copytree(budget_base, budget_bounded); budget_broker_id, budget_broker_session = _local_identity("broker")
        budget_event = base_event(event_id="event-budget-bounded", engagement_id=budget_base.name, recorded_at="2026-07-10T00:02:01Z", actor_role="broker", actor_id=budget_broker_id, event_type="coverage.status_changed", rationale="The configured ceiling fired after disposing three queue items against a frozen five-row corpus denominator.", payload={"entity_id": budget_base.name, "status": "budget_bounded", "disposed_count": 3, "enumerated_count": 5, "corpus_enumeration_ref": budget_manifest_ref}, evidence_refs=[budget_manifest_ref, budget_tsv_ref], state_changes=[{"dimension": "coverage", "entity_id": budget_base.name, "previous": "active", "current": "budget_bounded"}], session_id=budget_broker_session, operation_class="notebook")
        budget_state = None; budget_detail = ""
        try:
            _append_kernel_event(budget_bounded, budget_event)
            budget_state = reduce_engagement(budget_bounded); budget_progress = (budget_bounded / "progress.md").read_text(encoding="utf-8")
            budget_reached = budget_state["coverage"] == "budget_bounded" and budget_state["coverage_counts"]["enumerated_count"] == 5 and budget_state["coverage_counts"]["corpus_enumeration_ref"] == budget_manifest_ref and "Coverage: `budget_bounded`" in budget_progress and "Frozen corpus denominator: `5` package-entrypoint rows" in budget_progress and "Declared disposed rows (not mechanically cross-checked): `3`" in budget_progress
            budget_detail = str(budget_state)
        except RecordError as exc:
            budget_reached = False; budget_detail = exc.code
        checks.append(("budget-bounded coverage binds its enumerated count to registered frozen corpus evidence without presenting mixed units as a fraction", budget_reached, budget_detail))
        checks.append(("run exhaustion does not fabricate an operator stop or park the queue", budget_state is not None and budget_state["queue_control"] == {"status": "active", "last_stop": None, "last_resume": None}, str((budget_state or {}).get("queue_control"))))

        generic_budget = root / "budget-generic-public"; shutil.copytree(budget_base, generic_budget); budget_proposal_path = root / "budget-bounded-event.json"; budget_proposal_path.write_bytes(canonical_json_bytes(budget_event)); budget_cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), "append-event", "--engagement", str(generic_budget), "--file", str(budget_proposal_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        try: generic_budget_code = json.loads(budget_cli.stdout)["error"]["code"]
        except (json.JSONDecodeError, KeyError): generic_budget_code = None
        checks.append(("generic model-reachable append cannot set the outer driver's budget boundary", budget_cli.returncode != 0 and generic_budget_code == "external_driver_budget_boundary_required" and reduce_engagement(generic_budget)["coverage"] == "active", budget_cli.stdout + budget_cli.stderr))

        missing_count_refusals = []
        for missing_field in ("disposed_count", "enumerated_count"):
            missing_counts = root / f"budget-missing-{missing_field}"; shutil.copytree(budget_base, missing_counts)
            invalid_budget = json.loads(json.dumps(budget_event)); invalid_budget["event_id"] = f"event-budget-missing-{missing_field}"; invalid_budget["payload"].pop(missing_field)
            try: _append_kernel_event(missing_counts, invalid_budget); invalid_code = None
            except RecordError as exc: invalid_code = exc.code
            missing_count_refusals.append(invalid_code is not None and reduce_engagement(missing_counts)["coverage"] == "active")
        checks.append(("budget-bounded coverage refuses either missing count", all(missing_count_refusals), str(missing_count_refusals)))

        mismatched_denominator = root / "budget-mismatched-denominator"; shutil.copytree(budget_base, mismatched_denominator); mismatched_budget = json.loads(json.dumps(budget_event)); mismatched_budget["event_id"] = "event-budget-mismatched-denominator"; mismatched_budget["payload"].update({"disposed_count": 1, "enumerated_count": 1})
        try: _append_kernel_event(mismatched_denominator, mismatched_budget); mismatched_code = None
        except RecordError as exc: mismatched_code = exc.code
        checks.append(("a self-declared 1/1 budget boundary is refused against the registered five-row frozen denominator", mismatched_code == "coverage_enumerated_count_mismatch" and reduce_engagement(mismatched_denominator)["coverage"] == "active", str(mismatched_code)))

        incoherent_counts = root / "budget-incoherent-counts"; shutil.copytree(budget_base, incoherent_counts); incoherent_budget = json.loads(json.dumps(budget_event)); incoherent_budget["event_id"] = "event-budget-incoherent-counts"; incoherent_budget["payload"].update({"disposed_count": 6, "enumerated_count": 5})
        try: _append_kernel_event(incoherent_counts, incoherent_budget); incoherent_code = None
        except RecordError as exc: incoherent_code = exc.code
        checks.append(("budget-bounded disposed count cannot exceed its enumerated denominator", incoherent_code == "budget_bounded_counts_invalid" and reduce_engagement(incoherent_counts)["coverage"] == "active", str(incoherent_code)))

        active_budget_documents = test_corpus_documents(
            row_count=1,
            frozen_at="2026-07-10T00:01:59Z",
        )
        active_budget = root / "budget-active"; active_budget.mkdir(); active_budget.joinpath("scope.md").write_text(scope_with_corpus_pin(scope.replace("self-test", "budget-active"), active_budget_documents[1]), encoding="utf-8"); initialize_engagement(active_budget, "2026-07-10T00:02:00Z"); active_manifest_ref, active_tsv_ref = register_test_corpus(active_budget, row_count=1, documents=active_budget_documents); active_event = json.loads(json.dumps(budget_event)); active_event["event_id"] = "event-budget-from-active"; active_event["engagement_id"] = active_budget.name; active_event["payload"].update({"entity_id": active_budget.name, "disposed_count": 0, "enumerated_count": 1, "corpus_enumeration_ref": active_manifest_ref}); active_event["evidence_refs"] = [active_manifest_ref, active_tsv_ref]; active_event["state_changes"] = [{"dimension": "coverage", "entity_id": active_budget.name, "previous": "active", "current": "budget_bounded"}]
        try: _append_kernel_event(active_budget, active_event); active_code = None
        except RecordError as exc: active_code = exc.code
        checks.append(("active coverage can end budget-bounded only against its registered frozen denominator", active_code is None and reduce_engagement(active_budget)["coverage_counts"]["enumerated_count"] == 1, str(active_code)))

        identity_cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), "runtime-identity", "--role", "orchestrator"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        try: orchestrator_identity = json.loads(identity_cli.stdout)
        except json.JSONDecodeError: orchestrator_identity = {"actor_id": "unavailable", "session_id": "unavailable"}
        orchestrator_id, orchestrator_session = orchestrator_identity["actor_id"], orchestrator_identity["session_id"]
        forged_orchestrator_reopenable = root / "budget-forged-orchestrator-reopen"; shutil.copytree(budget_bounded, forged_orchestrator_reopenable)
        forged_orchestrator_cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), "reopen-coverage", "--engagement", str(forged_orchestrator_reopenable), "--recorded-at", "2026-07-10T00:02:02Z", "--reason", "A forged identity must not reopen coverage.", "--actor-id", "orchestrator-selftest", "--session-id", orchestrator_session], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        checks.append(("public coverage reopen requires a process-bound orchestrator identity", forged_orchestrator_cli.returncode != 0 and reduce_engagement(forged_orchestrator_reopenable)["coverage"] == "budget_bounded", forged_orchestrator_cli.stdout + forged_orchestrator_cli.stderr))
        concurrent_reopenable = root / "budget-concurrent-orchestrator-reopen"; shutil.copytree(budget_bounded, concurrent_reopenable); before_concurrent_reopen_events = len(read_ledger(concurrent_reopenable, "event"))
        concurrent_reopen_command = [sys.executable, str(Path(__file__).resolve()), "reopen-coverage", "--engagement", str(concurrent_reopenable), "--recorded-at", "2026-07-10T00:02:01Z", "--reason", "Concurrent retries describe one orchestrator decision.", "--actor-id", orchestrator_id, "--session-id", orchestrator_session]
        concurrent_reopen_processes = [subprocess.Popen(concurrent_reopen_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(8)]
        concurrent_reopen_outcomes = [process.communicate(timeout=30) + (process.returncode,) for process in concurrent_reopen_processes]
        try: concurrent_reopen_event_ids = {json.loads(outcome[0])["event_id"] for outcome in concurrent_reopen_outcomes}
        except (json.JSONDecodeError, KeyError): concurrent_reopen_event_ids = set()
        concurrent_reopened_state = reduce_engagement(concurrent_reopenable)
        checks.append(("concurrent public coverage-reopen retries all succeed and append one event", all(outcome[2] == 0 for outcome in concurrent_reopen_outcomes) and len(concurrent_reopen_event_ids) == 1 and len(read_ledger(concurrent_reopenable, "event")) == before_concurrent_reopen_events + 1 and concurrent_reopened_state["coverage"] == "active" and concurrent_reopened_state["coverage_counts"] is None, str(concurrent_reopen_outcomes)))
        orchestrator_reopenable = root / "budget-orchestrator-reopen"; shutil.copytree(budget_bounded, orchestrator_reopenable); before_reopen_events = len(read_ledger(orchestrator_reopenable, "event"))
        reopen_command = [sys.executable, str(Path(__file__).resolve()), "reopen-coverage", "--engagement", str(orchestrator_reopenable), "--recorded-at", "2026-07-10T00:02:02Z", "--reason", "A materially distinct bounded branch remains to be tested.", "--actor-id", orchestrator_id, "--session-id", orchestrator_session]
        orchestrator_reopen_cli = subprocess.run(reopen_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False); orchestrator_reopen_retry = subprocess.run(reopen_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        active_reopen_cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), "reopen-coverage", "--engagement", str(orchestrator_reopenable), "--recorded-at", "2026-07-10T00:02:03Z", "--reason", "Active coverage is not a terminal state.", "--actor-id", orchestrator_id, "--session-id", orchestrator_session], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        orchestrator_reopened_state = reduce_engagement(orchestrator_reopenable); orchestrator_reopened_event = read_ledger(orchestrator_reopenable, "event")[-1]
        try: reopen_result, retry_result = json.loads(orchestrator_reopen_cli.stdout), json.loads(orchestrator_reopen_retry.stdout)
        except json.JSONDecodeError: reopen_result = retry_result = {}
        expected_orchestrator = {"role": "orchestrator", "id": orchestrator_id}
        checks.append(("public orchestrator command reopens only terminal budget-bounded coverage with exact identity and idempotence", identity_cli.returncode == 0 and orchestrator_reopen_cli.returncode == 0 and orchestrator_reopen_retry.returncode == 0 and active_reopen_cli.returncode != 0 and orchestrator_reopened_state["coverage"] == "active" and orchestrator_reopened_state["coverage_counts"] is None and not orchestrator_reopened_state["authority_requests"] and len(read_ledger(orchestrator_reopenable, "event")) == before_reopen_events + 1 and reopen_result.get("event_id") == retry_result.get("event_id") == orchestrator_reopened_event["event_id"] and orchestrator_reopened_event["event_type"] == "coverage.reopened" and orchestrator_reopened_event["actor"] == expected_orchestrator and orchestrator_reopened_event["provenance"]["actor"] == expected_orchestrator and orchestrator_reopened_event["provenance"]["session_id"] == orchestrator_session and orchestrator_reopened_event["payload"]["reason"] == "A materially distinct bounded branch remains to be tested.", orchestrator_reopen_cli.stdout + orchestrator_reopen_cli.stderr + orchestrator_reopen_retry.stdout + orchestrator_reopen_retry.stderr + active_reopen_cli.stdout + active_reopen_cli.stderr))

        broker_reopenable = root / "budget-broker-reopen"; shutil.copytree(budget_bounded, broker_reopenable)
        broker_reopen = base_event(event_id="event-coverage-reopened-broker", engagement_id=budget_base.name, recorded_at="2026-07-10T00:02:02Z", actor_role="broker", actor_id=budget_broker_id, event_type="coverage.reopened", rationale="A broker must not obscure who reopened coverage.", payload={"entity_id": budget_base.name, "status": "active", "reason": "A broker must not obscure who reopened coverage."}, state_changes=[{"dimension": "coverage", "entity_id": budget_base.name, "previous": "budget_bounded", "current": "active"}], session_id=budget_broker_session, operation_class="notebook")
        broker_reopen_path = root / "budget-broker-reopen.json"; broker_reopen_path.write_bytes(canonical_json_bytes(broker_reopen)); broker_reopen_cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), "append-event", "--engagement", str(broker_reopenable), "--file", str(broker_reopen_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        checks.append(("generic broker append cannot obscure the orchestrator coverage-reopen actor", broker_reopen_cli.returncode != 0 and reduce_engagement(broker_reopenable)["coverage"] == "budget_bounded", broker_reopen_cli.stdout + broker_reopen_cli.stderr))

        missing_reopen_reason = root / "budget-reopen-missing-reason"; shutil.copytree(budget_bounded, missing_reopen_reason)
        no_reason_cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), "reopen-coverage", "--engagement", str(missing_reopen_reason), "--recorded-at", "2026-07-10T00:02:02Z", "--reason", "", "--actor-id", orchestrator_id, "--session-id", orchestrator_session], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        no_reason_state = reduce_engagement(missing_reopen_reason)
        checks.append(("coverage reopen is refused without a recorded reason", no_reason_cli.returncode != 0 and no_reason_state["coverage"] == "budget_bounded" and no_reason_state["coverage_counts"]["enumerated_count"] == 5 and no_reason_state["coverage_counts"]["corpus_enumeration_ref"] == budget_manifest_ref, no_reason_cli.stdout + no_reason_cli.stderr))

        untyped_reopenable = root / "budget-untyped-reopen"; shutil.copytree(budget_bounded, untyped_reopenable)
        untyped_reopen = json.loads(json.dumps(broker_reopen)); untyped_reopen["event_id"] = "event-budget-untyped-reopen"; untyped_reopen["event_type"] = "coverage.status_changed"; untyped_reopen["payload"] = {"entity_id": budget_base.name, "status": "active", "coverage_review_ref": "event-budget-bounded"}
        untyped_reopen_path = root / "budget-untyped-reopen.json"; untyped_reopen_path.write_bytes(canonical_json_bytes(untyped_reopen)); untyped_reopen_cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), "append-event", "--engagement", str(untyped_reopenable), "--file", str(untyped_reopen_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        checks.append(("terminal coverage cannot reopen through the untyped status-change path", untyped_reopen_cli.returncode != 0 and reduce_engagement(untyped_reopenable)["coverage"] == "budget_bounded", untyped_reopen_cli.stdout + untyped_reopen_cli.stderr))

        operator_reopen_bypass = root / "operator-reopen-without-authority"; shutil.copytree(engagement, operator_reopen_bypass)
        operator_reopen = base_event(event_id="event-operator-reopen-without-authority", engagement_id=engagement.name, recorded_at="2026-07-10T00:02:02Z", actor_role="broker", actor_id=budget_broker_id, event_type="engagement.reopened", rationale="Attempt to bypass the existing operator reopen authority.", payload={"entity_id": engagement.name, "status": "active", "operator_id": "operator-selftest", "executor_id": budget_broker_id}, state_changes=[{"dimension": "engagement", "entity_id": engagement.name, "previous": "blocked", "current": "active"}, {"dimension": "coverage", "entity_id": engagement.name, "previous": "blocked", "current": "active"}], session_id=budget_broker_session, operation_class="authority")
        operator_reopen_path = root / "operator-reopen-without-authority.json"; operator_reopen_path.write_bytes(canonical_json_bytes(operator_reopen)); operator_reopen_cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), "append-event", "--engagement", str(operator_reopen_bypass), "--file", str(operator_reopen_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        operator_reopen_state = reduce_engagement(operator_reopen_bypass)
        checks.append(("existing engagement reopen remains authority-gated and distinct", operator_reopen_cli.returncode != 0 and bool(operator_reopen_state["active_blockers"]) and operator_reopen_state["coverage"] == "blocked" and all(event["event_type"] != "engagement.reopened" for event in read_ledger(operator_reopen_bypass, "event")), operator_reopen_cli.stdout + operator_reopen_cli.stderr))

        budget_reopen = base_event(event_id="event-budget-reopened-by-prior", engagement_id=budget_base.name, recorded_at="2026-07-10T00:02:02Z", actor_role="operator", actor_id="operator-selftest", event_type="operator_prior.recorded", rationale="A new material branch reopens the budget-bounded run.", payload={"prior_id": "prior-budget-reopen", "prior_statement": "A materially distinct branch remains.", "strength": "strong", "reason": "operator target-model knowledge", "reopen_hypothesis_id": "hypothesis-budget", "reopening_condition": "Test the distinct branch."}, entity_refs=["hypothesis-budget"], state_changes=[{"dimension": "search", "entity_id": "hypothesis-budget", "previous": "closed", "current": "queued"}, {"dimension": "coverage", "entity_id": budget_base.name, "previous": "budget_bounded", "current": "active"}]); append_event(budget_bounded, budget_reopen); reopened_budget = reduce_engagement(budget_bounded)
        checks.append(("budget-bounded coverage can reopen to active and clears terminal denominator accounting", reopened_budget["coverage"] == "active" and reopened_budget["coverage_counts"] is None, str(reopened_budget)))
        append_event(budget_bounded, base_event(event_id="event-budget-hypothesis-selected", engagement_id=budget_base.name, recorded_at="2026-07-10T00:02:02.100000Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="hypothesis.status_changed", rationale="Select the reopened bounded branch.", payload={"hypothesis_id": "hypothesis-budget", "status": "selected", "reason": "execute the reopened bounded branch", "experiment_refs": [], "control_refs": [], "supporting_evidence_refs": [], "conflicting_evidence_refs": [], "disposition_rationale": "The reopened branch is now selected.", "unresolved_questions": [], "next_route": budget_hypothesis_payload["next_experiment"]}, state_changes=[{"dimension": "search", "entity_id": "hypothesis-budget", "previous": "queued", "current": "selected"}]))
        append_event(budget_bounded, base_event(event_id="event-budget-hypothesis-running", engagement_id=budget_base.name, recorded_at="2026-07-10T00:02:02.200000Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="hypothesis.status_changed", rationale="Begin the reopened bounded branch without recording an attempt yet.", payload={"hypothesis_id": "hypothesis-budget", "status": "running", "reason": "begin the reopened bounded branch", "experiment_refs": [], "control_refs": [], "supporting_evidence_refs": [], "conflicting_evidence_refs": [], "disposition_rationale": "The reopened branch is running and still requires its first attempt.", "unresolved_questions": [], "next_route": budget_hypothesis_payload["next_experiment"]}, state_changes=[{"dimension": "search", "entity_id": "hypothesis-budget", "previous": "selected", "current": "running"}]))
        budget_escape = json.loads(json.dumps(budget_event)); budget_escape["event_id"] = "event-budget-escape-with-work"; budget_escape["recorded_at"] = "2026-07-10T00:02:03Z"; budget_escape["state_changes"][0]["previous"] = "active"
        budget_escape_before = (budget_bounded / "events.jsonl").read_bytes()
        try:
            _append_kernel_event(budget_bounded, budget_escape)
            budget_escape_code = None
        except RecordError as exc:
            budget_escape_code = exc.code
        budget_escape_state = reduce_engagement(budget_bounded)
        checks.append(("budget_bounded cannot be used as a free ending after a queued-selected-running lifecycle records zero attempts", budget_escape_code == "coverage_terminal_work_remaining" and (budget_bounded / "events.jsonl").read_bytes() == budget_escape_before and budget_escape_state["coverage"] == "active" and any(item["class"] == "hypothesis_running_unattempted" and item["entity"]["id"] == "hypothesis-budget" for item in budget_escape_state["work_queue"]), str((budget_escape_code, budget_escape_state["work_queue"]))))

        cycle_case = root / "budget-redeclaration-cycle"; shutil.copytree(budget_base, cycle_case)
        first_cycle_budget = json.loads(json.dumps(budget_event)); first_cycle_budget["event_id"] = "event-budget-cycle-1"
        _append_kernel_event(cycle_case, first_cycle_budget)
        append_event(cycle_case, base_event(event_id="event-budget-cycle-reopen", engagement_id=budget_base.name, recorded_at="2026-07-10T00:02:02Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="coverage.reopened", rationale="Repeat the same bounded declaration without disposing work.", payload={"entity_id": budget_base.name, "status": "active", "reason": "Repeat the same bounded declaration without disposing work."}, state_changes=[{"dimension": "coverage", "entity_id": budget_base.name, "previous": "budget_bounded", "current": "active"}], session_id="session-cycle-reopen", operation_class="notebook"))
        second_cycle_budget = json.loads(json.dumps(budget_event)); second_cycle_budget["event_id"] = "event-budget-cycle-2"; second_cycle_budget["recorded_at"] = "2026-07-10T00:02:03Z"; second_cycle_budget["state_changes"][0]["previous"] = "active"
        _append_kernel_event(cycle_case, second_cycle_budget)
        cycle_state = reduce_engagement(cycle_case)
        cycle_facts = cycle_state["budget_redeclaration_cycles"]
        checks.append(("consecutive budget redeclarations without intervening work disposition surface as deterministic reduced facts", len(cycle_facts) == 1 and cycle_facts[0]["first_event_ref"] == "event-budget-cycle-1" and cycle_facts[0]["redeclaration_event_ref"] == "event-budget-cycle-2" and cycle_facts[0]["recorded_at"] == "2026-07-10T00:02:03Z" and "event-budget-cycle-1" in (cycle_case / "progress.md").read_text(), str(cycle_facts)))

        progress = engagement / "progress.md"
        expected_progress = progress.read_bytes()
        progress.write_text("operator edit to generated view\n", encoding="utf-8")
        stale_view_caught = False
        try:
            assert_views_current(engagement, reduced_once)
        except RecordError as exc:
            stale_view_caught = exc.code == "stale_derived_views"
        write_views(engagement, reduced_once)
        checks.append(("derived-view edits are detected and deterministically overwritten", stale_view_caught and progress.read_bytes() == expected_progress, "generated view edit survived"))

        crash_event = base_event(event_id="event-crash-boundary", engagement_id=engagement.name, recorded_at="2026-07-10T00:03:00Z", actor_role="operator", actor_id="operator-selftest", event_type="observation.recorded", rationale="Ledger commit succeeds before simulated projection crash.", payload={"entity_id": "observation-1", "entity_type": "observation", "status": "recorded"})
        append_ledger_record(engagement, "event", crash_event)
        stale_snapshot = (engagement / "state.snapshot.json").read_bytes() != canonical_json_bytes(reduce_engagement(engagement))
        recovered = reduce_engagement(engagement); write_snapshot(engagement, recovered); write_views(engagement, recovered)
        checks.append(("resume recovers a ledger commit made before projection crash", stale_snapshot and recovered["last_event_id"] == "event-crash-boundary", "authoritative event was lost"))

        before_concurrent_count = len(read_ledger(engagement, "event")); local_broker_id, local_broker_session = _local_identity("broker")
        processes = []
        for number in range(4):
            proposal = base_event(event_id=f"event-concurrent-{number}", engagement_id=engagement.name, recorded_at="2026-07-10T00:10:00Z", actor_role="broker", actor_id=local_broker_id, event_type="observation.recorded", rationale=f"Concurrent append {number}.", payload={"entity_id": f"observation-{number + 2}", "entity_type": "observation", "status": "recorded"}, session_id=local_broker_session, operation_class="notebook")
            proposal_path = root / f"proposal-{number}.json"
            proposal_path.write_bytes(canonical_json_bytes(proposal))
            processes.append(subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "append-event", "--engagement", str(engagement), "--file", str(proposal_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
        for _ in range(2):
            processes.append(subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "reduce", "--engagement", str(engagement)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
        outcomes = [process.communicate(timeout=30) + (process.returncode,) for process in processes]
        concurrent_records = read_ledger(engagement, "event")
        current = reduce_engagement(engagement)
        checks.append(("concurrent writers serialize without loss or stale projections", all(result[2] == 0 for result in outcomes) and len(concurrent_records) == before_concurrent_count + 4 and (engagement / "state.snapshot.json").read_bytes() == canonical_json_bytes(current), str(outcomes)))
        forged=base_event(event_id="event-forged-operator",engagement_id=engagement.name,recorded_at="2026-07-10T00:10:01Z",actor_role="operator",actor_id="operator-selftest",event_type="observation.recorded",rationale="Attempt noninteractive operator impersonation.",payload={"entity_id":"observation-forged","entity_type":"observation","status":"recorded"});forged_path=root/"forged-operator.json";forged_path.write_bytes(canonical_json_bytes(forged));forged_run=subprocess.run([sys.executable,str(Path(__file__).resolve()),"append-event","--engagement",str(engagement),"--file",str(forged_path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
        try:forged_payload=json.loads(forged_run.stdout);forged_blocked=forged_run.returncode!=0 and forged_payload.get("error",{}).get("code")=="operator_signature_required"
        except json.JSONDecodeError:forged_blocked=False
        checks.append(("noninteractive caller cannot impersonate signed operator through generic append",forged_blocked,forged_run.stdout+forged_run.stderr))
        snapshot_bytes = (engagement / "state.snapshot.json").read_bytes()
        stale_value = json.loads(snapshot_bytes); stale_value["event_count"] -= 1
        (engagement / "state.snapshot.json").write_bytes(canonical_json_bytes(stale_value))
        stale_resume_caught = False
        try:
            assert_resume_current(engagement)
        except RecordError as exc:
            stale_resume_caught = exc.code == "stale_state_snapshot"
        (engagement / "state.snapshot.json").write_bytes(snapshot_bytes)
        checks.append(("check-resume rejects a stale snapshot", stale_resume_caught, "stale snapshot accepted"))

        package_fixture = root / "package-fixture.bin"; package_fixture.write_bytes(b"pinned package fixture\n"); package_digest = sha256_file(package_fixture); runtime_fixture = Path(sys.executable).resolve()
        blocked_environment = collect_preflight(engagement, preflight_id="preflight-wrong-identity", mode="package", target=package_fixture, expected_identity="sha256:" + "f" * 64, runtime=runtime_fixture, reproduction_argv=[str(runtime_fixture), "-c", "pass"], operator_id="operator-selftest", recorded_at="2026-07-10T00:13:00Z", operator_redaction_attested=True)
        review_environment = collect_preflight(engagement, preflight_id="preflight-zone-review", mode="package", target=package_fixture, expected_identity=package_digest, runtime=runtime_fixture, reproduction_argv=[str(runtime_fixture), "-c", "pass"], operator_id="operator-selftest", recorded_at="2026-07-10T00:13:01Z", operator_redaction_attested=True, advisory_zone="unknown")
        environment_record = collect_preflight(engagement, preflight_id="preflight-selftest", mode="package", target=package_fixture, expected_identity=package_digest, runtime=runtime_fixture, reproduction_argv=[str(runtime_fixture), "-c", "pass"], operator_id="operator-selftest", recorded_at="2026-07-10T00:13:02Z", operator_redaction_attested=True, endpoint_identity="local", account_role="owner")
        retry_event_count = reduce_engagement(engagement)["event_count"]; retried_environment = collect_preflight(engagement, preflight_id="preflight-selftest", mode="package", target=package_fixture, expected_identity=package_digest, runtime=runtime_fixture, reproduction_argv=[str(runtime_fixture), "-c", "pass"], operator_id="operator-selftest", recorded_at="2026-07-10T00:13:02Z", operator_redaction_attested=True, endpoint_identity="local", account_role="owner")
        environment_state = reduce_engagement(engagement)
        checks.append(("preflight retry is byte-idempotent after record and event commit", retried_environment == environment_record and environment_state["event_count"] == retry_event_count, "preflight retry appended or changed immutable bytes"))
        checks.append(("wrong identity blocks and advisory Zone never authorizes or replaces a ready preflight", environment_record["status"] == "ready" and blocked_environment["status"] == "blocked" and review_environment["status"] == "needs_review" and environment_state["active_environment_ref"] == "preflight-selftest" and not any(item["safety"]["zone2_authorization_granted"] for item in (environment_record, blocked_environment, review_environment)), str(environment_state["environment_preflights"])))
        local_broker_id, local_broker_session = _local_identity("broker")
        collector_engagement = root / "collector-modes"; collector_engagement.mkdir(); collector_engagement.joinpath("scope.md").write_text(scope.replace("self-test", "collector-modes"), encoding="utf-8"); initialize_engagement(collector_engagement, "2026-07-10T00:13:10Z")
        agent_source_path = root / "agent-artifact-source.txt"; agent_source_path.write_text("benign agent evidence\n", encoding="utf-8"); source_time = datetime.fromisoformat("2026-07-10T00:13:09Z".replace("Z", "+00:00")).timestamp(); os.utime(agent_source_path, (source_time, source_time))
        agent_preflight_run = subprocess.run([sys.executable, str(Path(__file__).resolve()), "preflight", "--engagement", str(collector_engagement), "--preflight-id", "preflight-agent", "--mode", "package", "--target", str(package_fixture), "--expected-identity", package_digest, "--runtime", str(runtime_fixture), "--reproduction-argv", json.dumps([str(runtime_fixture), "-c", "pass"]), "--actor-role", "broker", "--actor-id", local_broker_id, "--session-id", local_broker_session, "--recorded-at", "2026-07-10T00:13:10.500000Z"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        agent_record = load_json(collector_engagement / "environment" / "preflight-preflight-agent.json") if agent_preflight_run.returncode == 0 else {}
        checks.append(("agent clear-local preflight is noninteractive, truthful, and separately collected", agent_preflight_run.returncode == 0 and agent_record.get("schema_version") == 2 and agent_record.get("status") == "ready" and agent_record.get("provenance", {}).get("actor") == {"role": "broker", "id": local_broker_id} and agent_record.get("provenance", {}).get("session_id") == local_broker_session and "operator_redaction_attested" not in agent_record.get("safety", {}), agent_preflight_run.stdout + agent_preflight_run.stderr))
        review_candidate = collect_agent_preflight(collector_engagement, preflight_id="preflight-agent-review", mode="package", target=package_fixture, expected_identity=package_digest, runtime=runtime_fixture, reproduction_argv=[str(runtime_fixture), "-c", "pass"], operator_id=local_broker_id, recorded_at="2026-07-10T00:13:10.510000Z", advisory_zone="unknown", actor_role="broker", actor_id=local_broker_id, session_id=local_broker_session)
        review_action = _authority_action("review-preflight", lane_id="lane-preflight-review", executor_id=local_broker_id, session_id=local_broker_session, preflight_id="preflight-agent-review", verdict="accepted", reason="Identity is exact; advisory zone remains non-authorizing.", operator_id="operator-selftest", recorded_at="2026-07-10T00:13:10.540000Z"); review_action_digest = sha256_bytes(canonical_json_bytes(review_action)); review_action_relative = "authority/requests/request-preflight-review.action.json"; atomic_write(collector_engagement / review_action_relative, canonical_json_bytes(review_action)); review_scope = reduce_engagement(collector_engagement)["scope_hash"]
        append_event(collector_engagement, base_event(event_id="event-authority-request-preflight-review", engagement_id=collector_engagement.name, recorded_at="2026-07-10T00:13:10.520000Z", actor_role="broker", actor_id=local_broker_id, event_type="authority.requested", rationale="Request operator review of immutable preflight facts.", payload={"request_id": "request-preflight-review", "action_kind": "review-preflight", "action_digest": review_action_digest, "action_path": review_action_relative, "lane_id": "lane-preflight-review", "request_status": "pending_authority", "scope_hash": review_scope, "environment_ref": None, "expires_at": "2099-07-10T00:00:00Z"}, session_id=local_broker_session, operation_class="notebook"))
        append_event(collector_engagement, base_event(event_id="event-authority-resolution-preflight-review", engagement_id=collector_engagement.name, recorded_at="2026-07-10T00:13:10.530000Z", actor_role="operator", actor_id="operator-selftest", event_type="authority.resolved", rationale="Accept exact identity facts without granting Zone-2 authority.", payload={"request_id": "request-preflight-review", "request_event_ref": "event-authority-request-preflight-review", "action_digest": review_action_digest, "resolution": "approved", "resolved_at": "2026-07-10T00:13:10.530000Z"}, entity_refs=["event-authority-request-preflight-review"], session_id="session-operator-review", operation_class="authority"))
        preflight_bytes = (collector_engagement / "environment" / "preflight-preflight-agent-review.json").read_bytes(); preflight_review = review_preflight(collector_engagement, "preflight-agent-review", "accepted", "Identity is exact; advisory zone remains non-authorizing.", "operator-selftest", "2026-07-10T00:13:10.540000Z", "request-preflight-review", "lane-preflight-review", local_broker_id, local_broker_session); reviewed_state = reduce_engagement(collector_engagement)
        checks.append(("preflight collection is immutable and separate from digest-bound operator review", review_candidate["status"] == "needs_review" and preflight_review["review_type"] == "operator" and (collector_engagement / "environment" / "preflight-preflight-agent-review.json").read_bytes() == preflight_bytes and reviewed_state["environment_preflights"]["preflight-agent-review"]["status"] == "ready" and reviewed_state["active_environment_ref"] == "preflight-agent-review" and review_candidate["safety"]["zone2_authorization_granted"] is False, str(reviewed_state["environment_preflights"])))
        agent_metadata = {"schema_version": 1, "artifact_id": "artifact-agent", "engagement_id": collector_engagement.name, "created_at": "2026-07-10T00:13:10.700000Z", "producer": {"role": "broker", "id": local_broker_id}, "producer_session_id": local_broker_session, "operation_class": "notebook", "acquisition_method": "source_inspection", "target_refs": [], "environment_ref": "preflight-agent-review", "sensitivity": "internal", "redaction_status": "not_needed", "contains_executable_capability": False, "advisory_zone": "clear_local", "escalation_confirmation_event_ref": None, "cleanup_obligation_ref": None, "supersedes_artifact_id": None, "media_type": "text/plain"}
        agent_metadata_path = root / "agent-artifact-metadata.json"; agent_metadata_path.write_bytes(canonical_json_bytes(agent_metadata)); classification_path = root / "agent-artifact-classification.json"
        classify_run = subprocess.run([sys.executable, str(Path(__file__).resolve()), "classify-artifact", "--engagement", str(collector_engagement), "--metadata", str(agent_metadata_path), "--source", str(agent_source_path), "--relative-path", "evidence/agent-artifact.txt", "--recorded-at", "2026-07-10T00:13:10.600000Z", "--actor-role", "broker", "--actor-id", local_broker_id, "--session-id", local_broker_session, "--output", str(classification_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        agent_artifact_path = collector_engagement / "evidence" / "agent-artifact.txt"; agent_artifact_path.parent.mkdir(exist_ok=True)
        if classify_run.returncode == 0: shutil.copyfile(agent_source_path, agent_artifact_path)
        register_run = subprocess.run([sys.executable, str(Path(__file__).resolve()), "register-artifact", "--engagement", str(collector_engagement), "--file", str(agent_artifact_path), "--metadata", str(agent_metadata_path), "--classification", str(classification_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        if register_run.returncode != 0: agent_artifact_path.unlink(missing_ok=True)
        dangling_destination=collector_engagement/"evidence"/"dangling-artifact.txt"; dangling_target=root/"outside-dangling-target"; dangling_destination.symlink_to(dangling_target); dangling_metadata=dict(agent_metadata); dangling_metadata["artifact_id"]="artifact-dangling"; dangling_metadata_path=root/"dangling-metadata.json"; dangling_metadata_path.write_bytes(canonical_json_bytes(dangling_metadata)); dangling_run=subprocess.run([sys.executable,str(Path(__file__).resolve()),"classify-artifact","--engagement",str(collector_engagement),"--metadata",str(dangling_metadata_path),"--source",str(agent_source_path),"--relative-path","evidence/dangling-artifact.txt","--recorded-at","2026-07-10T00:13:10.750000Z","--actor-role","broker","--actor-id",local_broker_id,"--session-id",local_broker_session],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False); checks.append(("clear-local classification rejects dangling destination symlink before permit",dangling_run.returncode!=0 and not dangling_target.exists(),dangling_run.stdout+dangling_run.stderr)); dangling_destination.unlink()
        zone2_metadata = dict(agent_metadata); zone2_metadata["artifact_id"] = "artifact-zone2-blocked"; zone2_metadata["advisory_zone"] = "review_required"; zone2_metadata["operation_class"] = "real_world"; zone2_path = root / "zone2-metadata.json"; zone2_path.write_bytes(canonical_json_bytes(zone2_metadata)); blocked_zone2_path = collector_engagement / "evidence" / "zone2-blocked.bin"
        classify_zone2 = subprocess.run([sys.executable, str(Path(__file__).resolve()), "classify-artifact", "--engagement", str(collector_engagement), "--metadata", str(zone2_path), "--planned-sha256", sha256_file(agent_source_path), "--planned-size", str(agent_source_path.stat().st_size), "--relative-path", "evidence/zone2-blocked.bin", "--recorded-at", "2026-07-10T00:13:10.800000Z", "--actor-role", "broker", "--actor-id", local_broker_id, "--session-id", local_broker_session], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        try: zone2_error = json.loads(classify_zone2.stdout).get("error", {}).get("code")
        except json.JSONDecodeError: zone2_error = None
        checks.append(("artifact creation is classified before bytes and Zone-2 fails before creation", classify_run.returncode == 0 and register_run.returncode == 0 and not blocked_zone2_path.exists() and zone2_error == "artifact_creation_requires_fresh_confirmation", classify_run.stdout + register_run.stdout + classify_zone2.stdout))
        secret_package = root / "secret-package.txt"; secret_package.write_text("Authorization: Bearer synthetic-credential-shape-1234567890\n", encoding="utf-8"); secret_preflight = collect_agent_preflight(collector_engagement, preflight_id="preflight-secret-blocked", mode="package", target=secret_package, expected_identity=sha256_file(secret_package), runtime=runtime_fixture, reproduction_argv=[str(runtime_fixture), "-c", "pass"], operator_id=local_broker_id, recorded_at="2026-07-10T00:13:10.900000Z", actor_role="broker", actor_id=local_broker_id, session_id=local_broker_session)
        checks.append(("automatic preflight scanning blocks secret-shaped target bytes without storing values", secret_preflight["status"] == "blocked" and secret_preflight["safety"]["credentials_present"] is True and secret_preflight["safety"]["secret_scan_status"] == "blocked" and "authorization_header" in secret_preflight["safety"]["secret_pattern_classes"] and "synthetic-credential" not in canonical_json_bytes(secret_preflight).decode("utf-8"), str(secret_preflight["safety"])))
        checks.append(("secret scanner distinguishes assignments from absolute-path bind mounts", "password_assignment" in detect_secret_classes(b'password=\"synthetic-password-value\"') and "password_assignment" in detect_secret_classes(b'password: synthetic-password-value') and "password_assignment" not in detect_secret_classes(b'/etc/passwd:/etc/passwd:ro'), str(detect_secret_classes(b'/etc/passwd:/etc/passwd:ro'))))
        git_fixture = root / "git-fixture"; git_fixture.mkdir(); subprocess.run(["git", "init", "-q", str(git_fixture)], check=True); subprocess.run(["git", "-C", str(git_fixture), "config", "user.email", "fixture@example.invalid"], check=True); subprocess.run(["git", "-C", str(git_fixture), "config", "user.name", "Fixture"], check=True); git_fixture.joinpath("fixture.txt").write_text("fixture\n"); subprocess.run(["git", "-C", str(git_fixture), "add", "fixture.txt"], check=True); subprocess.run(["git", "-C", str(git_fixture), "commit", "-qm", "fixture"], check=True); git_commit = subprocess.check_output(["git", "-C", str(git_fixture), "rev-parse", "HEAD"], text=True).strip(); fsmonitor_sentinel = root / "fsmonitor-ran"; fsmonitor_hook = root / "fsmonitor-hook.sh"; fsmonitor_hook.write_text(f"#!/bin/sh\ntouch '{fsmonitor_sentinel}'\nexit 0\n"); fsmonitor_hook.chmod(0o700); subprocess.run(["git", "-C", str(git_fixture), "config", "core.fsmonitor", str(fsmonitor_hook)], check=True)
        git_preflight = collect_preflight(collector_engagement, preflight_id="preflight-git", mode="git", target=git_fixture, expected_identity=git_commit, runtime=runtime_fixture, reproduction_argv=[str(Path(sys.executable).resolve()), "-c", "pass"], operator_id="operator-selftest", recorded_at="2026-07-10T00:13:11Z", operator_redaction_attested=True); fsmonitor_suppressed = not fsmonitor_sentinel.exists()
        git_fixture.joinpath("secret.txt").write_text("Authorization: Bearer synthetic-git-credential-1234567890\n"); subprocess.run(["git", "-C", str(git_fixture), "add", "secret.txt"], check=True); subprocess.run(["git", "-C", str(git_fixture), "commit", "-qm", "secret fixture"], check=True); secret_git_commit = subprocess.check_output(["git", "-C", str(git_fixture), "rev-parse", "HEAD"], text=True).strip()
        secret_git_preflight = collect_agent_preflight(collector_engagement, preflight_id="preflight-git-secret", mode="git", target=git_fixture, expected_identity=secret_git_commit, runtime=runtime_fixture, reproduction_argv=[str(Path(sys.executable).resolve()), "-c", "pass"], operator_id=local_broker_id, recorded_at="2026-07-10T00:13:11.500000Z", actor_role="broker", actor_id=local_broker_id, session_id=local_broker_session)
        local_preflight = collect_preflight(collector_engagement, preflight_id="preflight-local-runtime", mode="local_runtime", target=package_fixture, expected_identity=package_digest, runtime=runtime_fixture, reproduction_argv=[str(Path(sys.executable).resolve()), "-c", "pass"], operator_id="operator-selftest", recorded_at="2026-07-10T00:13:12Z", operator_redaction_attested=True)
        checks.append(("demonstrated Git, package, and local-runtime collectors pin identity without executing reproduction argv", git_preflight["status"] == "ready" and fsmonitor_suppressed and secret_git_preflight["status"] == "blocked" and "authorization_header" in secret_git_preflight["safety"]["secret_pattern_classes"] and local_preflight["status"] == "ready" and reduce_engagement(collector_engagement)["active_environment_ref"] == "preflight-local-runtime", str((git_preflight["status"], local_preflight["status"]))))
        cleanup_event = base_event(event_id="event-cleanup-open", engagement_id=collector_engagement.name, recorded_at="2026-07-10T00:13:13Z", actor_role="operator", actor_id="operator-selftest", event_type="cleanup.updated", rationale="Track an unresolved local fixture cleanup obligation.", payload={"entity_id": "cleanup-selftest", "status": "open", "scope_hash": reduce_engagement(collector_engagement)["scope_hash"], "operator_id": "operator-selftest", "updated_at": "2026-07-10T00:13:13Z", "cleanup_obligations": [{"obligation_id": "cleanup-selftest", "kind": "local_fixture", "status": "open", "artifact_refs": [], "rationale": "Fixture cleanup remains open.", "closed_at": None}]}, state_changes=[{"dimension": "cleanup", "entity_id": "cleanup-selftest", "previous": None, "current": "open"}]); append_event(collector_engagement, cleanup_event)
        cleanup_blocked = collect_preflight(collector_engagement, preflight_id="preflight-cleanup-debt", mode="package", target=package_fixture, expected_identity=package_digest, runtime=runtime_fixture, reproduction_argv=[str(runtime_fixture), "-c", "pass"], operator_id="operator-selftest", recorded_at="2026-07-10T00:13:14Z", operator_redaction_attested=True)
        checks.append(("reduced cleanup debt blocks and invalidates environment activation", cleanup_blocked["status"] == "blocked" and cleanup_blocked["safety"]["cleanup_open_count"] == 1 and reduce_engagement(collector_engagement)["active_environment_ref"] is None, str(cleanup_blocked)))
        second_cleanup = base_event(event_id="event-cleanup-second", engagement_id=collector_engagement.name, recorded_at="2026-07-10T00:13:15Z", actor_role="operator", actor_id="operator-selftest", event_type="cleanup.updated", rationale="A delta update must not erase an earlier open obligation.", payload={"entity_id": "cleanup-second", "status": "open", "scope_hash": reduce_engagement(collector_engagement)["scope_hash"], "operator_id": "operator-selftest", "updated_at": "2026-07-10T00:13:15Z", "cleanup_obligations": [{"obligation_id": "cleanup-second", "kind": "local_fixture", "status": "open", "artifact_refs": [], "rationale": "Second fixture cleanup remains open.", "closed_at": None}]}, state_changes=[{"dimension": "cleanup", "entity_id": "cleanup-second", "previous": None, "current": "open"}]); append_event(collector_engagement, second_cleanup)
        checks.append(("cleanup delta cannot silently drop an earlier open obligation", reduce_engagement(collector_engagement)["cleanup"]["open_count"] == 2, str(reduce_engagement(collector_engagement)["cleanup"])))
        normalization_engagement = root / "operator-normalization"; normalization_engagement.mkdir(); normalization_engagement.joinpath("scope.md").write_text(scope.replace("self-test", "operator-normalization").replace("operator-selftest", "Operator Name!"), encoding="utf-8"); initialize_engagement(normalization_engagement, "2026-07-10T00:13:15Z")
        empty_argv = collect_preflight(normalization_engagement, preflight_id="preflight-empty-argv", mode="package", target=package_fixture, expected_identity=package_digest, runtime=runtime_fixture, reproduction_argv=[], operator_id="Operator Name!", recorded_at="2026-07-10T00:13:16Z", operator_redaction_attested=True)
        unattested = collect_preflight(normalization_engagement, preflight_id="preflight-unattested", mode="package", target=package_fixture, expected_identity=package_digest, runtime=runtime_fixture, reproduction_argv=[str(runtime_fixture), "-c", "pass"], operator_id="Operator Name!", recorded_at="2026-07-10T00:13:17Z")
        checks.append(("empty argv records blocked, redaction requires attestation, and operator labels normalize once", empty_argv["status"] == "blocked" and empty_argv["collector"]["reproduction_argv"] == [] and unattested["status"] == "blocked" and empty_argv["provenance"]["actor"]["id"] == "Operator-Name", str((empty_argv, unattested))))
        secret_engagement = root / "secret-artifact"; shutil.copytree(engagement, secret_engagement); secret_file = secret_engagement / "evidence" / "secret.txt"; secret_file.parent.mkdir(exist_ok=True); secret_file.write_text("Authorization: Bearer not-a-real-token-value-123456\n")
        secret_blocked = False
        try:
            _register_legacy_artifact(secret_engagement, secret_file, {"schema_version": 1, "artifact_id": "artifact-secret", "engagement_id": engagement.name, "created_at": "2026-07-10T00:13:13Z", "producer": {"role": "operator", "id": "operator-selftest"}, "acquisition_method": "operator", "target_refs": [], "environment_ref": "preflight-selftest", "sensitivity": "secret", "redaction_status": "pending", "contains_executable_capability": False, "advisory_zone": "unknown", "escalation_confirmation_event_ref": None, "cleanup_obligation_ref": None, "supersedes_artifact_id": None, "media_type": "text/plain"})
        except RecordError as exc:
            secret_blocked = exc.code == "secret_shaped_artifact_content" and all("not-a-real" not in str(item) for item in exc.details)
        checks.append(("secret-shaped artifact content is rejected without echoing the value", secret_blocked, "secret-shaped artifact accepted or disclosed"))

        evidence_file = engagement / "evidence" / "artifact.txt"; evidence_file.write_text("benign evidence\n", encoding="utf-8")
        artifact_metadata = {"schema_version": 1, "artifact_id": "artifact-selftest", "engagement_id": engagement.name, "created_at": "2026-07-10T00:15:00Z", "producer": {"role": "operator", "id": "operator-selftest"}, "acquisition_method": "operator", "target_refs": [], "environment_ref": "preflight-selftest", "sensitivity": "internal", "redaction_status": "not_needed", "contains_executable_capability": False, "advisory_zone": "clear_local", "escalation_confirmation_event_ref": None, "cleanup_obligation_ref": None, "supersedes_artifact_id": None, "media_type": "text/plain"}
        registered = _register_legacy_artifact(engagement, evidence_file, artifact_metadata)
        checks.append(("register-artifact derives and commits path/digest/size", registered["sha256"] == sha256_file(evidence_file) and reduce_engagement(engagement)["artifact_count"] == 1, str(registered)))
        artifact_boundary = (engagement / "artifacts.jsonl").read_bytes(); duplicate_metadata = json.loads(json.dumps(artifact_metadata)); duplicate_metadata["artifact_id"] = "artifact-duplicate-path"; duplicate_metadata["created_at"] = "2026-07-10T00:15:01Z"
        duplicate_registration_rolled_back = False
        try:
            _register_legacy_artifact(engagement, evidence_file, duplicate_metadata)
        except RecordError as exc:
            duplicate_registration_rolled_back = exc.code == "duplicate_artifact_path"
        checks.append(("artifact append rolls back when prospective reduction rejects", duplicate_registration_rolled_back and (engagement / "artifacts.jsonl").read_bytes() == artifact_boundary, "rejected artifact remained committed"))

        def attempt_proposal(attempt_id: str, recorded_at: str, kind: str, assessment: str, statement: str, control_of: list[str]) -> dict:
            return {"schema_version": 2, "attempt_id": attempt_id, "engagement_id": engagement.name, "recorded_at": recorded_at, "actor": {"role": "hunter", "id": "hunter-selftest"}, "provenance": {"actor": {"role": "hunter", "id": "hunter-selftest"}, "provider": "selftest", "model": "semantic-researcher", "prompt_version": "decision5-selftest", "tool_versions": ["source-inspection-v1"], "card_versions": ["card-selftest"]}, "scope_hash": snapshot["scope_hash"], "environment_ref": "preflight-selftest", "escalation_confirmation_event_ref": None, "hypothesis_ref": "hypothesis-h1", "experiment_ref": "event-hypothesis-running", "surface": "owned local fixture", "action_summary": statement, "redaction_attestation": True, "observation": {"source": "source_inspection", "statement": statement}, "evidence_refs": ["artifact-selftest"], "kind": kind, "control_of": control_of, "assessment": assessment, "contamination": {"status": "none_observed", "sources": [], "note": ""}, "cost": {"wall_seconds": 1, "model_seconds": 0, "tool_seconds": 1, "target_calls": 0, "model_calls": 0, "input_tokens": None, "output_tokens": None, "cost_usd": None, "human_review_seconds": 0}}
        attempt_specs = [
            ("attempt-primary", "2026-07-10T00:15:10Z", "primary", "suspected_signal", "Primary trace reaches the bounded missing guard.", []),
            ("attempt-negative", "2026-07-10T00:15:11Z", "negative_control", "no_signal", "Matched guarded sibling does not exhibit the signal.", ["attempt-primary"]),
            ("attempt-positive", "2026-07-10T00:15:12Z", "positive_control", "suspected_signal", "Owned known-positive fixture emits the expected marker.", ["attempt-primary"]),
            ("attempt-replay", "2026-07-10T00:15:13Z", "replay", "suspected_signal", "Fresh-state replay reproduces the bounded trace.", ["attempt-primary"]),
        ]
        for spec in attempt_specs:
            append_attempt(engagement, attempt_proposal(*spec))
        routing_control = attempt_proposal(
            "attempt-routing-negative-control",
            "2026-07-10T00:15:13.500000Z",
            "negative_control",
            "no_signal",
            "The likely-held routing control remains held under its bounded matched check.",
            ["attempt-primary"],
        )
        routing_control["experiment_ref"] = "event-routing-negative"
        append_attempt(engagement, routing_control)
        proof_state = reduce_engagement(engagement)
        checks.append(("baseline evidence→primary→matched controls→fresh replay is structured and linked", proof_state["attempt_count"] == 5 and [item["kind"] for item in read_ledger(engagement, "attempt")] == ["primary", "negative_control", "positive_control", "replay", "negative_control"] and not any(item["class"] == "control_candidate_unverified" and item["entity"]["id"] == "event-routing-negative" for item in proof_state["work_queue"]), str(proof_state["attempt_count"])))

        same_identity_retry = root / "override-same-identity-attempt"; shutil.copytree(engagement, same_identity_retry)
        _append_kernel_event(same_identity_retry, base_event(
            event_id="event-same-identity-reopened",
            engagement_id=engagement.name,
            recorded_at="2026-07-10T00:15:13.600000Z",
            actor_role="operator",
            actor_id="operator-selftest",
            event_type="engagement.reopened",
            rationale="Reopen before recording a fresh exact ending context.",
            payload={"entity_id": engagement.name, "status": "active", "operator_id": "operator-selftest"},
            state_changes=[
                {"dimension": "engagement", "entity_id": engagement.name, "previous": "blocked", "current": "active"},
                {"dimension": "coverage", "entity_id": engagement.name, "previous": "blocked", "current": "active"},
            ],
            operation_class="authority",
        ))
        same_identity_state = reduce_engagement(same_identity_retry)
        same_identity_attempts = read_ledger(same_identity_retry, "attempt")
        same_identity_blockers = blocking_work_identities(project_current_terminal_work_state(same_identity_state, same_identity_attempts, coverage="blocked"))
        same_identity_reason = "Operator accepts this exact synthetic residual queue and attempt ledger context."
        same_identity_time = "2026-07-10T00:15:14Z"
        same_identity_session = _local_identity("operator")[1]
        same_identity_payload = {
            "entity_id": engagement.name,
            "terminal_kind": "engagement",
            "status": "blocked",
            "reason": same_identity_reason,
            "operator_id": "operator-selftest",
            "scope_hash": same_identity_state["scope_hash"],
            "blocking_items": same_identity_blockers,
            "blocking_queue_digest": sha256_bytes(canonical_json_bytes(same_identity_blockers)),
            **attempt_ledger_context(same_identity_attempts),
        }
        same_identity_changes = [
            {"dimension": "engagement", "entity_id": engagement.name, "previous": "active", "current": "blocked"},
            {"dimension": "coverage", "entity_id": engagement.name, "previous": "active", "current": "blocked"},
        ]
        same_identity_action = ending_override_action(
            engagement_id=engagement.name,
            recorded_at=same_identity_time,
            actor={"role": "operator", "id": "operator-selftest"},
            payload=same_identity_payload,
            entity_refs=[],
            evidence_refs=[],
            state_changes=same_identity_changes,
            session_id=same_identity_session,
        )
        same_identity_action_digest = sha256_bytes(canonical_json_bytes(same_identity_action))
        same_identity_challenge = operator_challenge_bytes(
            engagement_id=engagement.name,
            scope_hash=same_identity_state["scope_hash"],
            ledger_hash=read_ledger(same_identity_retry, "event")[-1]["record_hash"],
            operation=f"override-ending:{same_identity_action_digest}",
            operator_id="operator-selftest",
        )
        same_identity_challenge_path = root / "same-identity-override-challenge.json"
        same_identity_challenge_path.write_bytes(same_identity_challenge)
        subprocess.run(["/usr/bin/ssh-keygen", "-q", "-Y", "sign", "-f", str(reviewer_key), "-n", "llm-redteam-harness-operator-v1", str(same_identity_challenge_path)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        same_identity_argv = [sys.executable, str(Path(__file__).resolve()), "override-ending", "--engagement", str(same_identity_retry), "--terminal-kind", "engagement", "--status", "blocked", "--operator-id", "operator-selftest", "--session-id", same_identity_session, "--recorded-at", same_identity_time, "--reason", same_identity_reason]
        same_identity_env = {**os.environ, "HARNESS_OPERATOR_SIGNATURE_FILE": str(same_identity_challenge_path) + ".sig", "HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE": str(allowed_signers_path)}
        same_identity_override = subprocess.run(same_identity_argv, env=same_identity_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        equal_time_replay = root / "override-equal-time-later-attempt"; shutil.copytree(same_identity_retry, equal_time_replay)
        _append_kernel_event(equal_time_replay, base_event(
            event_id="event-equal-time-override-reopened",
            engagement_id=engagement.name,
            recorded_at=same_identity_time,
            actor_role="operator",
            actor_id="operator-selftest",
            event_type="engagement.reopened",
            rationale="Reopen the exact prior ending before recording later work at the same timestamp precision.",
            payload={"entity_id": engagement.name, "status": "active", "operator_id": "operator-selftest"},
            state_changes=[
                {"dimension": "engagement", "entity_id": engagement.name, "previous": "blocked", "current": "active"},
                {"dimension": "coverage", "entity_id": engagement.name, "previous": "blocked", "current": "active"},
            ],
            operation_class="authority",
        ))
        equal_time_before_attempt = reduce_engagement(equal_time_replay)
        try:
            append_attempt(equal_time_replay, attempt_proposal("attempt-equal-time-after-reopen", same_identity_time, "primary", "suspected_signal", "Later append order, not timestamp precision, separates this attempt from the prior signed ending.", []))
            equal_time_replay_state = reduce_engagement(equal_time_replay)
            equal_time_replay_error = None
        except RecordError as exc:
            equal_time_replay_state = None
            equal_time_replay_error = exc.code
        checks.append((
            "historical override replay uses its signed attempt prefix so later equal-timestamp work after reopen stays reducible",
            same_identity_override.returncode == 0
            and equal_time_replay_error is None
            and equal_time_replay_state is not None
            and equal_time_replay_state["coverage"] == "active"
            and equal_time_replay_state["attempt_count"] == equal_time_before_attempt["attempt_count"] + 1
            and equal_time_replay_state["ending_overrides"][-1]["attempt_ledger_count"] == same_identity_payload["attempt_ledger_count"],
            str({"override": same_identity_override.stdout + same_identity_override.stderr, "error": equal_time_replay_error, "state": equal_time_replay_state}),
        ))
        before_same_identity_attempt = reduce_engagement(same_identity_retry)
        blocker_identity_before = blocking_work_identities(before_same_identity_attempt)
        late_same_identity_attempt = attempt_proposal("attempt-same-identity-later", "2026-07-10T00:15:14.100000Z", "primary", "suspected_signal", "A later attempt preserves the same unadjudicated-hypothesis queue identity.", [])
        append_attempt(same_identity_retry, late_same_identity_attempt)
        after_same_identity_attempt = reduce_engagement(same_identity_retry)
        same_identity_event_count = len(read_ledger(same_identity_retry, "event"))
        stale_same_identity_retry = subprocess.run(same_identity_argv, env=same_identity_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        checks.append((
            "a later same-hypothesis attempt keeps the coarse blocker identity but invalidates the signed override and its retry",
            same_identity_override.returncode == 0
            and blocker_identity_before == blocking_work_identities(after_same_identity_attempt)
            and after_same_identity_attempt["attempt_count"] == before_same_identity_attempt["attempt_count"] + 1
            and after_same_identity_attempt["source_hashes"]["attempts.jsonl"] != before_same_identity_attempt["source_hashes"]["attempts.jsonl"]
            and stale_same_identity_retry.returncode != 0
            and len(read_ledger(same_identity_retry, "event")) == same_identity_event_count,
            str({"first": same_identity_override.stdout + same_identity_override.stderr, "retry": stale_same_identity_retry.stdout + stale_same_identity_retry.stderr, "before": blocker_identity_before, "after": blocking_work_identities(after_same_identity_attempt)}),
        ))

        supported_negative = root / "supported-negative"; shutil.copytree(engagement, supported_negative)
        exhausted = base_event(event_id="event-hypothesis-exhausted", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:14Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="hypothesis.status_changed", rationale="Matched controls and fresh replay exhaust the bounded mechanism without manufacturing a finding.", payload={"hypothesis_id": "hypothesis-h1", "status": "exhausted", "reason": "matched controls refute the bounded path", "experiment_refs": ["attempt-primary", "attempt-replay"], "control_refs": ["attempt-negative", "attempt-positive", "attempt-routing-negative-control"], "supporting_evidence_refs": ["artifact-selftest"], "conflicting_evidence_refs": ["attempt-negative"], "disposition_rationale": "The primary anomaly does not survive the matched guarded sibling while detector and replay controls are healthy.", "unresolved_questions": [], "next_route": None}, evidence_refs=["attempt-primary", "attempt-negative", "attempt-positive", "attempt-replay", "attempt-routing-negative-control", "artifact-selftest"], state_changes=[{"dimension": "search", "entity_id": "hypothesis-h1", "previous": "running", "current": "exhausted"}]); append_event(supported_negative, exhausted)
        backdated_terminal = root / "backdated-terminal"; shutil.copytree(supported_negative, backdated_terminal)
        late_unadjudicated = attempt_proposal("attempt-late-unadjudicated", "2026-07-10T00:15:20Z", "primary", "suspected_signal", "A ledgered attempt must not disappear behind a backdated terminal timestamp.", [])
        append_attempt(backdated_terminal, late_unadjudicated)
        backdated_state = reduce_engagement(backdated_terminal)
        backdated_attempts = read_ledger(backdated_terminal, "attempt")
        historical_backdated_projection = project_terminal_work_state(backdated_state, backdated_attempts, coverage=backdated_state["coverage"], recorded_at="2026-07-10T00:15:14.500000Z")
        current_backdated_projection = project_current_terminal_work_state(backdated_state, backdated_attempts, coverage=backdated_state["coverage"])
        prior_engagement_status = "active"
        for prior_event in read_ledger(backdated_terminal, "event"):
            for change in prior_event["state_changes"]:
                if change["dimension"] == "engagement" and change["entity_id"] == backdated_state["engagement_id"]:
                    prior_engagement_status = change["current"]
        backdated_close = base_event(
            event_id="event-backdated-close",
            engagement_id=backdated_state["engagement_id"],
            recorded_at="2026-07-10T00:15:14.500000Z",
            actor_role="broker",
            actor_id=_local_identity("broker")[0],
            event_type="engagement.closed",
            rationale="A caller timestamp cannot hide an attempt already committed to the ledger.",
            payload={"entity_id": backdated_state["engagement_id"], "status": "closed", "scope_hash": backdated_state["scope_hash"], "operator_id": "operator-selftest", "disposition_ref": "memory-not-reached", "disposition_digest": "sha256:" + "0" * 64},
            state_changes=[{"dimension": "engagement", "entity_id": backdated_state["engagement_id"], "previous": prior_engagement_status, "current": "closed"}],
            session_id=_local_identity("broker")[1],
            operation_class="authority",
        )
        backdated_before = (backdated_terminal / "events.jsonl").read_bytes()
        try:
            _append_kernel_event(backdated_terminal, backdated_close)
            backdated_terminal_code = None
        except RecordError as exc:
            backdated_terminal_code = exc.code
        checks.append((
            "current terminal admission sees every already-ledgered attempt even when the proposed ending timestamp is backdated",
            engagement_may_end(historical_backdated_projection)
            and not engagement_may_end(current_backdated_projection)
            and blocking_work_identities(current_backdated_projection) == [{"class": "hypothesis_ran_unadjudicated", "entity": {"type": "hypothesis", "id": "hypothesis-h1", "detail": None}}]
            and backdated_terminal_code == "terminal_event_precedes_recorded_attempt"
            and (backdated_terminal / "events.jsonl").read_bytes() == backdated_before,
            str({"historical": historical_backdated_projection["work_queue"], "current": current_backdated_projection["work_queue"], "code": backdated_terminal_code}),
        ))
        negative_review = {"schema_version": 1, "review_id": "review-coverage-negative", "engagement_id": engagement.name, "review_type": "coverage", "proposed_finding_id": None, "entity_ref": engagement.name, "finding_revision": None, "recorded_at": "2026-07-10T00:15:15Z", "input_refs": ["attempt-primary", "attempt-negative", "attempt-positive", "attempt-replay"], "input_hash": "sha256:" + "5" * 64, "evidence_refs": ["attempt-primary", "attempt-negative", "attempt-positive", "attempt-replay", "artifact-selftest"], "conflicting_evidence": [], "independence": {"reviewer_id": "coverage-reviewer", "reviewer_model": "cold-reviewer", "reviewer_run_id": "run-coverage-negative", "originating_run_id": "event-hypothesis-running", "fresh_context": True, "prior_verdict_visible": False, "disconfirming_objective": "Find an omitted materially distinct path."}, "verdict": "coverage_dry", "rationale": "The bounded hypothesis is decisively exhausted by healthy matched controls.", "corrections": [], "required_next_actions": [], "bounded_space": "One owned-fixture branch and matched guarded sibling.", "hypothesis_dispositions": [{"hypothesis_ref": "hypothesis-h1", "status": "exhausted", "rationale": "Matched negative plus healthy positive and replay controls exhaust the route."}], "omitted_branch_challenge": "Cold review found no unmodeled sibling in the declared bounded space.", "residual_uncertainty": ["future versions not assessed"]}
        negative_review["input_hash"] = compute_review_input_hash(supported_negative, negative_review, build_reference_index(supported_negative))
        negative_review_path = supported_negative / "reviews" / "coverage-negative.json"; negative_review_path.write_bytes(canonical_json_bytes(negative_review))
        negative_review_commit = base_event(event_id="event-coverage-negative-commit", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:16Z", actor_role="operator", actor_id="operator-selftest", event_type="record.committed", rationale="Commit cold negative coverage review.", payload={"record_path": "reviews/coverage-negative.json", "record_digest": sha256_file(negative_review_path), "record_type": "review", "record_id": "review-coverage-negative", "record_revision": None}); append_event(supported_negative, negative_review_commit)
        negative_review_event = base_event(event_id="event-coverage-negative-reviewed", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:17Z", actor_role="reviewer", actor_id="coverage-reviewer", event_type="review.coverage_completed", rationale="Cold reviewer closes every material hypothesis in the bounded negative engagement.", payload={"review_type": "coverage", "verdict": "coverage_dry"}, review_refs=["review-coverage-negative"]); append_event(supported_negative, negative_review_event)
        negative_dry = base_event(event_id="event-coverage-negative-dry", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:18Z", actor_role="operator", actor_id="operator-selftest", event_type="coverage.status_changed", rationale="Supported negative reaches coverage dry without a finding.", payload={"entity_id": engagement.name, "status": "coverage_dry", "coverage_review_ref": "event-coverage-negative-reviewed"}, entity_refs=["event-coverage-negative-reviewed"], state_changes=[{"dimension": "coverage", "entity_id": engagement.name, "previous": "blocked", "current": "coverage_dry"}]); append_event(supported_negative, negative_dry)
        negative_state = reduce_engagement(supported_negative)
        checks.append(("well-supported negative reaches cold-reviewed coverage_dry without a finding", negative_state["coverage"] == "coverage_dry" and negative_state["hypotheses"]["hypothesis-h1"]["status"] == "exhausted" and negative_state["findings"] == {}, str(negative_state)))
        dry_reopenable = root / "coverage-dry-orchestrator-reopen"; shutil.copytree(supported_negative, dry_reopenable)
        dry_reopen_cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), "reopen-coverage", "--engagement", str(dry_reopenable), "--recorded-at", "2026-07-10T00:15:18.250000Z", "--reason", "Cold review omitted a materially distinct bounded branch.", "--actor-id", orchestrator_id, "--session-id", orchestrator_session], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        dry_reopened_state = reduce_engagement(dry_reopenable)
        checks.append(("public orchestrator command reopens coverage_dry without changing claim or search state", dry_reopen_cli.returncode == 0 and dry_reopened_state["coverage"] == "active" and dry_reopened_state["hypotheses"] == negative_state["hypotheses"] and dry_reopened_state["findings"] == negative_state["findings"], dry_reopen_cli.stdout + dry_reopen_cli.stderr))
        late_payload = json.loads(json.dumps(hypothesis["payload"])); late_payload["hypothesis_id"] = "hypothesis-after-dry"
        late_hypothesis = base_event(event_id="event-hypothesis-after-dry", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:18.500000Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="hypothesis.created", rationale="Must explicitly reopen coverage before introducing new search material.", payload=late_payload, entity_refs=["candidate-c1"], state_changes=[{"dimension": "search", "entity_id": "hypothesis-after-dry", "previous": None, "current": "queued"}])
        late_hypothesis_blocked = False
        try: append_event(supported_negative, late_hypothesis)
        except RecordError as exc: late_hypothesis_blocked = exc.code == "search_material_after_closed_coverage"
        checks.append(("new hypotheses cannot preserve a false coverage_dry state", late_hypothesis_blocked, "hypothesis appended after dry coverage without reopening"))
        reopen_prior = base_event(event_id="event-prior-reopens-negative", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:19Z", actor_role="operator", actor_id="operator-selftest", event_type="operator_prior.recorded", rationale="A strong operator prior reopens bounded search but supplies no claim evidence.", payload={"prior_id": "prior-reopen-negative", "prior_statement": "One materially distinct parser branch was not represented.", "strength": "strong", "reason": "operator target-model knowledge", "reopen_hypothesis_id": "hypothesis-h1", "reopening_condition": "Test the newly identified materially distinct parser branch."}, entity_refs=["hypothesis-h1"], state_changes=[{"dimension": "search", "entity_id": "hypothesis-h1", "previous": "exhausted", "current": "queued"}, {"dimension": "coverage", "entity_id": engagement.name, "previous": "coverage_dry", "current": "active"}]); append_event(supported_negative, reopen_prior)
        reopened_negative = reduce_engagement(supported_negative)
        checks.append(("strong operator prior reopens search and coverage without proving a claim", reopened_negative["coverage"] == "active" and reopened_negative["hypotheses"]["hypothesis-h1"]["status"] == "queued" and reopened_negative["findings"] == {}, str(reopened_negative)))
        telemetry = export_telemetry(supported_negative); telemetry_score = score_telemetry(telemetry)
        telemetry_states = telemetry["candidates"][0]["funnel_states"]
        checks.append(("complete-funnel export retains eligible, selected, and reopened states", telemetry["denominator"] == {"eligible_count": 1, "exported_count": 1, "complete": True} and all(value in telemetry_states for value in ("eligible", "selected", "reopened")), str(telemetry)))
        checks.append(("missing independent outcomes remains telemetry, never fake calibration", telemetry["classification"] == "telemetry" and "missing_independent_outcome" in telemetry["calibration_eligibility"]["reasons"] and telemetry_score["brier_score"] is None and telemetry_score["automatic_actions"] == [] and telemetry_score["bandit_enabled"] is False, str(telemetry_score)))

        artifact_tampered = root / "artifact-tampered"; shutil.copytree(engagement, artifact_tampered); (artifact_tampered / "evidence" / "artifact.txt").write_text("changed\n")
        artifact_tamper_caught = False
        try:
            reduce_engagement(artifact_tampered)
        except RecordError as exc:
            artifact_tamper_caught = exc.code == "artifact_file_digest_mismatch"
        checks.append(("modified registered artifact fails reduction", artifact_tamper_caught, "artifact modification accepted"))
        artifact_orphan = root / "artifact-orphan"; shutil.copytree(engagement, artifact_orphan); (artifact_orphan / "evidence" / "orphan.txt").write_text("orphan\n")
        artifact_orphan_caught = False
        try:
            reduce_engagement(artifact_orphan)
        except RecordError as exc:
            artifact_orphan_caught = exc.code == "orphan_artifact_file"
        checks.append(("orphan evidence file fails reduction", artifact_orphan_caught, "orphan artifact accepted"))

        reviews_dir = engagement / "reviews"; reviews_dir.mkdir(exist_ok=True)
        def claim_review(review_id: str, recorded_at: str, verdict: str, entity_ref: str, finding_revision: int | None, origin_run: str) -> dict:
            return {"schema_version": 1, "review_id": review_id, "engagement_id": engagement.name, "review_type": "claim_adjudication", "proposed_finding_id": "F-selftest", "entity_ref": entity_ref, "finding_revision": finding_revision, "recorded_at": recorded_at, "input_refs": ["attempt-primary", "attempt-negative", "attempt-positive", "attempt-replay", "preflight-selftest"], "input_hash": "sha256:" + ("3" if finding_revision is None else "4") * 64, "evidence_refs": ["attempt-primary", "attempt-negative", "attempt-positive", "attempt-replay", "artifact-selftest"], "conflicting_evidence": [], "independence": {"reviewer_id": "reviewer-selftest", "reviewer_model": "independent-reviewer", "reviewer_run_id": f"run-{review_id}", "reviewer_session_id": f"session-{review_id}", "originating_run_id": origin_run, "fresh_context": True, "prior_verdict_visible": False, "disconfirming_objective": "Refute the bounded mechanism and control linkage."}, "verdict": verdict, "rationale": "Primary trace, matched controls, and replay support only the bounded claim.", "corrections": [], "required_next_actions": ["preserve bounded language"], "control_applicability": [{"attempt_ref": "attempt-negative", "applicable": True, "rationale": "Matched negative branch."}, {"attempt_ref": "attempt-positive", "applicable": True, "rationale": "Known-positive detector check."}, {"attempt_ref": "attempt-replay", "applicable": True, "rationale": "Fresh-state replay."}]}
        review1_path = reviews_dir / "review-claim-1.json"; review1 = claim_review("review-claim-1", "2026-07-10T00:15:20Z", "supported", "F-selftest", None, "event-hypothesis-running"); review1["input_hash"] = compute_review_input_hash(engagement, review1, build_reference_index(engagement)); review1_path.write_bytes(canonical_json_bytes(review1))
        review1_commit = base_event(event_id="event-review-claim-1-commit", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:21Z", actor_role="operator", actor_id="operator-selftest", event_type="record.committed", rationale="Commit independent claim review.", payload={"record_path": "reviews/review-claim-1.json", "record_digest": sha256_file(review1_path), "record_type": "review", "record_id": "review-claim-1", "record_revision": None}); append_event(engagement, review1_commit)
        adjudication1 = base_event(event_id="event-claim-supported", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:22Z", actor_role="reviewer", actor_id="reviewer-selftest", event_type="claim.adjudicated", rationale="Independent review supports the bounded primitive.", payload={"entity_id": "F-selftest", "status": "supported", "review_ref": "review-claim-1", "review_digest": sha256_file(review1_path)}, review_refs=["review-claim-1"], state_changes=[{"dimension": "claim", "entity_id": "F-selftest", "previous": None, "current": "supported"}]); append_event(engagement, adjudication1)

        suite_records = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "engagement-records" / "suite.json").read_text())["cases"]
        finding1 = json.loads(json.dumps(next(case["record"] for case in suite_records if case["id"] == "finding-v3-rich")))
        finding1.update({"finding_id": "F-selftest", "engagement_id": engagement.name, "revision": 1, "supersedes_revision": None, "recorded_at": "2026-07-10T00:15:23Z", "change_reason": "Initial bounded adjudication.", "claim_state": "supported"})
        finding1["scope_provenance"].update({"scope_hash": snapshot["scope_hash"], "environment_ref": "preflight-selftest", "target_refs": []}); finding1["scope_provenance"]["provenance"]["actor"] = {"role": "reviewer", "id": "reviewer-selftest"}
        finding1["adjudication"] = {"review_ref": "review-claim-1", "justification": "Independent review bound primary evidence, both controls, and replay."}; finding1["search_linkage"] = {"candidate_refs": ["candidate-c1"], "hypothesis_refs": ["hypothesis-h1"]}
        for claim_name in ("mechanism", "reachability"): finding1["claims"][claim_name]["evidence_refs"] = ["artifact-selftest"]
        for impact in finding1["claims"]["impact_claims"]: impact["evidence_refs"] = ["artifact-selftest"]
        proof = finding1["proof"]; proof.update({"primary_attempt_refs": ["attempt-primary"], "negative_control_refs": ["attempt-negative"], "positive_control_refs": ["attempt-positive"], "replay_refs": ["attempt-replay"], "evidence_refs": ["artifact-selftest"], "control_applicability": {"negative": "required", "positive": "required", "replay": "required", "rationale": "Matched negative, known-positive, and fresh replay are all required."}})
        for mapping in proof["claim_proofs"]: mapping.update({"attempt_refs": ["attempt-primary"], "artifact_refs": ["artifact-selftest"], "control_refs": ["attempt-negative", "attempt-positive"], "replay_refs": ["attempt-replay"]})
        finding_dir = engagement / "findings" / "F-selftest"; finding_dir.mkdir(parents=True); finding1_path = finding_dir / "rev-1.json"; finding1_path.write_bytes(canonical_json_bytes(finding1))
        finding1_commit = base_event(event_id="event-finding-1-commit", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:24Z", actor_role="operator", actor_id="operator-selftest", event_type="record.committed", rationale="Commit finding revision one.", payload={"record_path": "findings/F-selftest/rev-1.json", "record_digest": sha256_file(finding1_path), "record_type": "finding-v3", "record_id": "F-selftest", "record_revision": 1}); append_event(engagement, finding1_commit)
        filing1 = base_event(event_id="event-finding-revision-1", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:25Z", actor_role="operator", actor_id="operator-selftest", event_type="finding.revised", rationale="Operator files the independently supported bounded claim.", payload={"finding_id": "F-selftest", "finding_revision": 1, "status": "supported", "finding_digest": sha256_file(finding1_path), "adjudication_review_ref": "review-claim-1", "adjudication_review_digest": sha256_file(review1_path), "adjudication_event_ref": "event-claim-supported", "supersedes_revision": None, "change_reason": "Initial bounded adjudication."}, entity_refs=["F-selftest", "event-claim-supported"], finding_refs=["F-selftest"], review_refs=["review-claim-1"]); append_event(engagement, filing1)

        review2_path = reviews_dir / "review-claim-2.json"; review2 = claim_review("review-claim-2", "2026-07-10T00:15:26Z", "confirmed", "F-selftest", 1, "event-hypothesis-running"); review2["input_refs"].append("F-selftest"); review2["input_hash"] = compute_review_input_hash(engagement, review2, build_reference_index(engagement)); review2_path.write_bytes(canonical_json_bytes(review2))
        review2_commit = base_event(event_id="event-review-claim-2-commit", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:27Z", actor_role="operator", actor_id="operator-selftest", event_type="record.committed", rationale="Commit fresh confirmation review.", payload={"record_path": "reviews/review-claim-2.json", "record_digest": sha256_file(review2_path), "record_type": "review", "record_id": "review-claim-2", "record_revision": None}); append_event(engagement, review2_commit)
        adjudication2 = base_event(event_id="event-claim-confirmed", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:28Z", actor_role="reviewer", actor_id="reviewer-selftest", event_type="claim.adjudicated", rationale="Fresh independent review confirms the bounded primitive.", payload={"entity_id": "F-selftest", "status": "confirmed", "review_ref": "review-claim-2", "review_digest": sha256_file(review2_path)}, review_refs=["review-claim-2"], state_changes=[{"dimension": "claim", "entity_id": "F-selftest", "previous": "supported", "current": "confirmed"}]); append_event(engagement, adjudication2)
        finding2 = json.loads(json.dumps(finding1)); finding2.update({"revision": 2, "supersedes_revision": 1, "recorded_at": "2026-07-10T00:15:29Z", "change_reason": "Fresh independent replay review confirmed the bounded primitive.", "claim_state": "confirmed"}); finding2["adjudication"] = {"review_ref": "review-claim-2", "justification": "Fresh reviewer confirmed the exact bounded claim tuple."}
        finding2_path = finding_dir / "rev-2.json"; finding2_path.write_bytes(canonical_json_bytes(finding2))
        finding2_commit = base_event(event_id="event-finding-2-commit", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:29Z", actor_role="operator", actor_id="operator-selftest", event_type="record.committed", rationale="Commit contiguous finding revision two.", payload={"record_path": "findings/F-selftest/rev-2.json", "record_digest": sha256_file(finding2_path), "record_type": "finding-v3", "record_id": "F-selftest", "record_revision": 2}); append_event(engagement, finding2_commit)
        filing2 = base_event(event_id="event-finding-revision-2", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:30Z", actor_role="operator", actor_id="operator-selftest", event_type="finding.revised", rationale="Operator files contiguous confirmed revision without rewriting revision one.", payload={"finding_id": "F-selftest", "finding_revision": 2, "status": "confirmed", "finding_digest": sha256_file(finding2_path), "adjudication_review_ref": "review-claim-2", "adjudication_review_digest": sha256_file(review2_path), "adjudication_event_ref": "event-claim-confirmed", "supersedes_revision": 1, "change_reason": "Fresh independent replay review confirmed the bounded primitive."}, entity_refs=["F-selftest", "event-claim-confirmed"], finding_refs=["F-selftest"], review_refs=["review-claim-2"]); append_event(engagement, filing2)
        chain_hypothesis = base_event(event_id="event-hypothesis-chain", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:31Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="hypothesis.created", rationale="Confirmed primitive opens bounded chainability search without broadening the finding.", payload={"hypothesis_id": "hypothesis-chain", "origin_type": "confirmed_primitive", "origin_ref": "F-selftest", "hypothesis_statement": "The confirmed local primitive may compose with one adjacent owned-fixture transition.", "suspected_invariant": "Composition must not cross the adjacent trust boundary.", "trust_boundary": "confirmed primitive to adjacent owned state", "attacker_path": ["confirmed primitive", "adjacent transition"], "impact_ceiling": "owned fixture composition only", "bounded_space": "One adjacent transition.", "lens_ids": ["composition"], "card_ids": ["card-selftest"], "expected_confirming_evidence": [{"evidence_type": "trace", "description": "end-to-end adjacent trace", "required": True}], "decisive_falsifiers": ["adjacent transition rejects primitive output"], "cost_estimate": zero_cost, "constraints": ["no target contact"], "next_experiment": "trace adjacent owned transition", "completion_criteria": ["trace or decisive rejection"], "status": "queued"}, entity_refs=["F-selftest"], finding_refs=["F-selftest"], state_changes=[{"dimension": "search", "entity_id": "hypothesis-chain", "previous": None, "current": "queued"}]); append_event(engagement, chain_hypothesis)
        finding_state = reduce_engagement(engagement)
        checks.append(("revisioned finding history and active chainability search coexist", finding_state["findings"]["F-selftest"]["revision"] == 2 and finding_state["findings"]["F-selftest"]["status"] == "confirmed" and finding_state["hypotheses"]["hypothesis-chain"]["status"] == "queued" and finding1_path.read_bytes() == canonical_json_bytes(finding1), str(finding_state["findings"])))
        forged_filing = copy.deepcopy(filing2); forged_filing["event_id"] = "event-finding-forged-operator"; forged_filing["recorded_at"] = "2026-07-10T00:15:32Z"; forged_filing["actor"] = {"role": "operator", "id": "other-operator"}; forged_filing["provenance"]["actor"] = forged_filing["actor"]
        before_forged = (engagement / "events.jsonl").read_bytes(); forged_blocked = False
        try:
            append_event(engagement, forged_filing)
        except RecordError as exc:
            forged_blocked = exc.code == "finding_filing_not_scope_operator"
        checks.append(("only the active signed-scope operator can file a finding revision", forged_blocked and (engagement / "events.jsonl").read_bytes() == before_forged, "forged operator filing appended"))
        skip_revision = copy.deepcopy(filing2); skip_revision["event_id"] = "event-finding-revision-4"; skip_revision["recorded_at"] = "2026-07-10T00:15:33Z"; skip_revision["payload"]["finding_revision"] = 4; skip_revision["payload"]["supersedes_revision"] = 2
        before_skip = (engagement / "events.jsonl").read_bytes(); skip_blocked = False
        try:
            append_event(engagement, skip_revision)
        except RecordError as exc:
            skip_blocked = exc.code == "finding_revision_not_contiguous"
        checks.append(("finding revision cannot skip history", skip_blocked and (engagement / "events.jsonl").read_bytes() == before_skip, "skipped revision appended"))

        tuple_hash = claim_tuple_hash(finding2)
        regrade = {"schema_version": 1, "review_id": "review-regrade-selftest", "engagement_id": engagement.name, "review_type": "regrade", "proposed_finding_id": "F-selftest", "recorded_at": "2026-07-10T00:15:34Z", "entity_ref": "F-selftest", "finding_revision": 2, "input_refs": ["F-selftest", "attempt-primary", "attempt-negative", "attempt-replay"], "input_hash": "sha256:" + "0" * 64, "evidence_refs": ["attempt-primary", "attempt-negative", "attempt-replay", "artifact-selftest"], "rationale": "Fresh regrade identifies a distinct adjacent composition that still needs evidence.", "conflicting_evidence": [], "verdict": "escalation_found", "corrections": [], "required_next_actions": ["collect evidence before revising impact"], "independence": {"reviewer_id": "regrade-reviewer", "reviewer_run_id": "run-regrade-selftest", "reviewer_model": "independent-regrader", "fresh_context": True, "prior_verdict_visible": False, "disconfirming_objective": "Refute the adjacent composition.", "originating_run_id": "event-finding-revision-2"}, "control_applicability": [{"attempt_ref": "attempt-negative", "applicable": True, "rationale": "Matched negative remains applicable."}], "claim_tuple_hash": tuple_hash, "replay_freshness": [{"attempt_ref": "attempt-replay", "fresh": True, "rationale": "Fresh-state replay."}], "prior_review_run_ids": ["run-review-claim-2"], "escalation_claims": ["Adjacent owned transition may compose with the confirmed primitive."], "blocked_reason": None}
        regrade["input_hash"] = compute_review_input_hash(engagement, regrade, build_reference_index(engagement)); regrade_path = reviews_dir / "regrade-selftest.json"; regrade_path.write_bytes(canonical_json_bytes(regrade))
        regrade_commit = base_event(event_id="event-regrade-commit", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:35Z", actor_role="operator", actor_id="operator-selftest", event_type="record.committed", rationale="Commit fresh regrade review.", payload={"record_path": "reviews/regrade-selftest.json", "record_digest": sha256_file(regrade_path), "record_type": "review", "record_id": "review-regrade-selftest", "record_revision": None}); append_event(engagement, regrade_commit)
        regrade_event = base_event(event_id="event-regrade-escalation", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:36Z", actor_role="reviewer", actor_id="regrade-reviewer", event_type="review.regrade_completed", rationale="Escalation is a search obligation, not a finding claim.", payload={"review_ref": "review-regrade-selftest", "finding_id": "F-selftest", "finding_revision": 2, "verdict": "escalation_found", "claim_tuple_hash": tuple_hash}, review_refs=["review-regrade-selftest"], finding_refs=["F-selftest"]); append_event(engagement, regrade_event)
        premature_revision = copy.deepcopy(filing2); premature_revision["event_id"] = "event-premature-escalation-revision"; premature_revision["recorded_at"] = "2026-07-10T00:15:37Z"; premature_revision["payload"]["finding_revision"] = 3; premature_revision["payload"]["supersedes_revision"] = 2
        premature_blocked = False
        try:
            append_event(engagement, premature_revision)
        except RecordError as exc:
            premature_blocked = exc.code == "escalation_evidence_not_collected"
        checks.append(("regrade escalation routes to evidence collection before finding revision", premature_blocked, "escalation directly revised finding"))
        escalation_hypothesis = base_event(event_id="event-hypothesis-escalation", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:38Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="hypothesis.created", rationale="Route reviewer escalation into bounded evidence collection.", payload={"hypothesis_id": "hypothesis-escalation", "origin_type": "reviewer_challenge", "origin_ref": "event-regrade-escalation", "hypothesis_statement": "The adjacent owned transition composes with the confirmed primitive.", "suspected_invariant": "Primitive output must not cross the adjacent boundary.", "trust_boundary": "primitive to adjacent owned transition", "attacker_path": ["primitive", "adjacent transition"], "impact_ceiling": "owned fixture only", "bounded_space": "One adjacent transition.", "lens_ids": ["composition"], "card_ids": ["card-selftest"], "expected_confirming_evidence": [{"evidence_type": "trace", "description": "end-to-end composition trace", "required": True}], "decisive_falsifiers": ["adjacent transition rejects primitive output"], "cost_estimate": zero_cost, "constraints": ["offline fixture"], "next_experiment": "trace composition", "completion_criteria": ["trace or decisive rejection"], "status": "queued"}, entity_refs=["event-regrade-escalation"], finding_refs=["F-selftest"], state_changes=[{"dimension": "search", "entity_id": "hypothesis-escalation", "previous": None, "current": "queued"}]); append_event(engagement, escalation_hypothesis)
        escalation_evidence_path = engagement / "evidence" / "escalation.txt"; escalation_evidence_path.write_text("new bounded escalation trace\n", encoding="utf-8")
        escalation_artifact = json.loads(json.dumps(artifact_metadata)); escalation_artifact.update({"artifact_id": "artifact-escalation", "created_at": "2026-07-10T00:15:40.500000Z", "acquisition_method": "source_inspection"}); _register_legacy_artifact(engagement, escalation_evidence_path, escalation_artifact)
        for status, previous, timestamp in (("selected", "queued", "2026-07-10T00:15:39Z"), ("running", "selected", "2026-07-10T00:15:40Z")):
            transition = base_event(event_id=f"event-escalation-{status}", engagement_id=engagement.name, recorded_at=timestamp, actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="hypothesis.status_changed", rationale=f"Escalation hypothesis {status}.", payload={"hypothesis_id": "hypothesis-escalation", "status": status, "reason": "bounded escalation evidence route", "experiment_refs": [], "control_refs": [], "supporting_evidence_refs": [], "conflicting_evidence_refs": [], "disposition_rationale": "Bounded evidence route recorded without changing finding truth.", "unresolved_questions": [], "next_route": "independent composition trace"}, state_changes=[{"dimension": "search", "entity_id": "hypothesis-escalation", "previous": previous, "current": status}]); append_event(engagement, transition)
        escalation_attempt = attempt_proposal("attempt-escalation", "2026-07-10T00:15:40.600000Z", "primary", "suspected_signal", "Fresh bounded trace exercises the reviewer-routed adjacent composition.", [])
        escalation_attempt.update({"hypothesis_ref": "hypothesis-escalation", "experiment_ref": "event-regrade-escalation", "evidence_refs": ["artifact-escalation"]})
        append_attempt(engagement, escalation_attempt)
        escalation_attempt_state = reduce_engagement(engagement)
        escalation_attempt_item = next(item for item in escalation_attempt_state["work_queue"] if item["class"] == "hypothesis_ran_unadjudicated" and item["entity"]["id"] == "hypothesis-escalation")
        escalation_attempt_action = decorate_work_queue_item(escalation_attempt_item, escalation_attempt_state, engagement.absolute())["next_action"]
        checks.append(("routed review evidence progression exposes the fresh attempt as required supporting evidence", "includes every fresh matching attempt in supporting_evidence_refs" in str(escalation_attempt_action["required_inputs"]), str(escalation_attempt_action)))
        escalation_held = base_event(event_id="event-escalation-held", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:41Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="hypothesis.status_changed", rationale="Escalation hypothesis held with fresh bounded evidence.", payload={"hypothesis_id": "hypothesis-escalation", "status": "held", "reason": "bounded escalation evidence route", "experiment_refs": ["attempt-escalation"], "control_refs": [], "supporting_evidence_refs": ["attempt-escalation", "artifact-escalation"], "conflicting_evidence_refs": [], "disposition_rationale": "Bounded evidence route recorded without changing finding truth.", "unresolved_questions": ["composition impact remains unproven"], "next_route": "independent composition trace"}, evidence_refs=["attempt-escalation", "artifact-escalation"], state_changes=[{"dimension": "search", "entity_id": "hypothesis-escalation", "previous": "running", "current": "held"}]); append_event(engagement, escalation_held)
        escalation_evidence_state = reduce_engagement(engagement)
        escalation_row = next(item for item in escalation_evidence_state["outstanding_reviews"] if item["review_ref"] == "event-regrade-escalation")
        checks.append(("pending review routes through a bound hypothesis and only fresh cited evidence reaches evidence_collected", escalation_row["status"] == "evidence_collected" and escalation_row["resolution_input_refs"] == ["attempt-escalation", "artifact-escalation"], str(escalation_row)))

        def poc_review(review_id: str, recorded_at: str, reviewer_id: str, run_id: str, verdict: str, prior_runs: list[str], mismatches: list[str], reward_indicators: list[str]) -> dict:
            value = {"schema_version": 1, "review_id": review_id, "engagement_id": engagement.name, "review_type": "pocinator", "proposed_finding_id": "F-selftest", "recorded_at": recorded_at, "entity_ref": "F-selftest", "finding_revision": 2, "input_refs": ["F-selftest", "artifact-selftest"], "input_hash": "sha256:" + "0" * 64, "evidence_refs": ["artifact-selftest"], "rationale": f"Pocinator outcome: {verdict}.", "conflicting_evidence": [], "verdict": verdict, "corrections": mismatches, "required_next_actions": ["route back without changing finding truth"] if verdict != "verified" else [], "independence": {"reviewer_id": reviewer_id, "reviewer_run_id": run_id, "reviewer_signer_fingerprint": sha256_bytes(reviewer_id.encode("utf-8")), "reviewer_model": "pocinator-reviewer", "fresh_context": True, "prior_verdict_visible": False, "disconfirming_objective": "Break the exact claim tuple and composition.", "originating_run_id": "event-finding-revision-2"}, "claim_tuple_hash": tuple_hash, "high_value": True, "proof_profile_ref": "artifact-selftest", "claim_mismatches": mismatches, "reward_hack_indicators": reward_indicators, "module_level_only": True, "end_to_end_composition_reviewed": False, "blocked_reason": None, "prior_review_run_ids": prior_runs}
            value["input_hash"] = compute_review_input_hash(engagement, value, build_reference_index(engagement)); return value
        poc_specs = [
            ("review-poc-mismatch", "2026-07-10T00:15:42Z", "poc-reviewer", "run-poc-mismatch", "claim_mismatch", ["run-regrade-selftest"], ["Proof demonstrates only the module-level mechanism."], []),
            ("review-poc-reward-1", "2026-07-10T00:15:45Z", "poc-reward-reviewer-1", "run-poc-reward-1", "reward_hacked", ["run-poc-mismatch"], [], ["Evaluator marker without end-to-end proof."]),
            ("review-poc-reward-2", "2026-07-10T00:15:48Z", "poc-reward-reviewer-2", "run-poc-reward-2", "reward_hacked", ["run-poc-reward-1"], [], ["Independent reviewer confirms reward-only optimization."]),
        ]
        mismatch_state = None
        reward_one_state = None
        reward_one_action = None
        for offset, spec in enumerate(poc_specs):
            review_value = poc_review(*spec); review_path = reviews_dir / f"{spec[0]}.json"; review_path.write_bytes(canonical_json_bytes(review_value))
            commit_time = ["2026-07-10T00:15:43Z", "2026-07-10T00:15:46Z", "2026-07-10T00:15:49Z"][offset]; event_time = ["2026-07-10T00:15:44Z", "2026-07-10T00:15:47Z", "2026-07-10T00:15:50Z"][offset]
            commit = base_event(event_id=f"event-{spec[0]}-commit", engagement_id=engagement.name, recorded_at=commit_time, actor_role="operator", actor_id="operator-selftest", event_type="record.committed", rationale="Commit typed Pocinator review.", payload={"record_path": f"reviews/{spec[0]}.json", "record_digest": sha256_file(review_path), "record_type": "review", "record_id": spec[0], "record_revision": None}); append_event(engagement, commit)
            reviewed = base_event(event_id=f"event-{spec[0]}", engagement_id=engagement.name, recorded_at=event_time, actor_role="reviewer", actor_id=spec[2], event_type="review.pocinator_completed", rationale="Pocinator result routes proof state only.", payload={"review_ref": spec[0], "finding_id": "F-selftest", "finding_revision": 2, "verdict": spec[4], "claim_tuple_hash": tuple_hash, "high_value": True}, review_refs=[spec[0]], finding_refs=["F-selftest"]); append_event(engagement, reviewed)
            if offset == 0: mismatch_state = reduce_engagement(engagement)
            if offset == 1:
                reward_one_state = reduce_engagement(engagement)
                reward_one_row = next(item for item in reward_one_state["work_queue"] if item["class"] == "review_obligation_open" and item["entity"]["id"] == "event-review-poc-reward-1")
                reward_one_action = decorate_work_queue_item(reward_one_row, reward_one_state, engagement.absolute())["next_action"]
        typed_state = reduce_engagement(engagement); proof_review = typed_state["proof_reviews"]["F-selftest:r2"]
        checks.append(("claim_mismatch routes correction without refuting finding", mismatch_state is not None and mismatch_state["findings"]["F-selftest"]["status"] == "confirmed" and mismatch_state["proof_reviews"]["F-selftest:r2"]["terminal_status"] == "route_back", str(mismatch_state)))
        checks.append(("first high-value reward_hacked blocks filing and requests one distinct independent second review", reward_one_state is not None and reward_one_state["proof_reviews"]["F-selftest:r2"]["terminal_status"] == "pending_second_review" and _filing_blocking_review_error(reward_one_state, "F-selftest") == "pocinator_second_review_pending" and reward_one_action is not None and reward_one_action["action_id"] == "record_distinct_pocinator_second_review" and "run-poc-reward-1" in str(reward_one_action["required_inputs"]), str((reward_one_state, reward_one_action))))
        reward_one_row_after_second = next(item for item in typed_state["outstanding_reviews"] if item["review_ref"] == "event-review-poc-reward-1")
        checks.append(("definite high-value reward_hacked requires two independent reviewers and binds the second review as correction evidence", proof_review["terminal_status"] == "second_review_confirmed" and proof_review["reviewer_run_ids"] == ["run-poc-reward-1", "run-poc-reward-2"] and reward_one_row_after_second.get("resolution_input_refs") == ["review-poc-reward-2"] and typed_state["findings"]["F-selftest"]["status"] == "confirmed", str((proof_review, reward_one_row_after_second))))
        report_manifest = generate_report(engagement, "F-selftest", 2, ["claim-mechanism", "claim-reach", "claim-impact"], [], "operator-selftest", "2026-07-10T00:15:50.500000Z")
        report_state = reduce_engagement(engagement); checks.append(("report generation binds exact finding revision, review, claims, proof matrix, and bytes", report_state["reports"][report_manifest["report_id"]]["status"] == "draft" and (engagement / report_manifest["report_path"]).is_file(), str(report_manifest)))

        correction = {"schema_version": 1, "review_id": "review-regrade-correction", "engagement_id": engagement.name, "review_type": "regrade", "proposed_finding_id": "F-selftest", "recorded_at": "2026-07-10T00:15:51Z", "entity_ref": "F-selftest", "finding_revision": 2, "input_refs": ["F-selftest", "attempt-negative", "attempt-replay"], "input_hash": "sha256:" + "0" * 64, "evidence_refs": ["attempt-negative", "attempt-replay"], "rationale": "Finding remains real but residual uncertainty must be narrowed.", "conflicting_evidence": [], "verdict": "confirmed_with_correction", "corrections": ["Narrow the residual uncertainty to future versions only."], "required_next_actions": ["file contiguous corrected revision"], "independence": {"reviewer_id": "correction-reviewer", "reviewer_run_id": "run-regrade-correction", "reviewer_model": "independent-regrader", "fresh_context": True, "prior_verdict_visible": False, "disconfirming_objective": "Find unsupported breadth in the claim.", "originating_run_id": "event-finding-revision-2"}, "control_applicability": [{"attempt_ref": "attempt-negative", "applicable": True, "rationale": "Matched negative bounds breadth."}], "claim_tuple_hash": tuple_hash, "replay_freshness": [{"attempt_ref": "attempt-replay", "fresh": True, "rationale": "Fresh replay remains valid."}], "prior_review_run_ids": ["run-regrade-selftest"], "escalation_claims": [], "blocked_reason": None}
        correction["input_hash"] = compute_review_input_hash(engagement, correction, build_reference_index(engagement)); correction_path = reviews_dir / "regrade-correction.json"; correction_path.write_bytes(canonical_json_bytes(correction))
        correction_commit = base_event(event_id="event-regrade-correction-commit", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:52Z", actor_role="operator", actor_id="operator-selftest", event_type="record.committed", rationale="Commit correction regrade.", payload={"record_path": "reviews/regrade-correction.json", "record_digest": sha256_file(correction_path), "record_type": "review", "record_id": "review-regrade-correction", "record_revision": None}); append_event(engagement, correction_commit)
        correction_event = base_event(event_id="event-regrade-correction", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:53Z", actor_role="reviewer", actor_id="correction-reviewer", event_type="review.regrade_completed", rationale="Correction must become a contiguous revision before closure.", payload={"review_ref": "review-regrade-correction", "finding_id": "F-selftest", "finding_revision": 2, "verdict": "confirmed_with_correction", "claim_tuple_hash": tuple_hash}, review_refs=["review-regrade-correction"], finding_refs=["F-selftest"]); append_event(engagement, correction_event)
        unresolved_correction = copy.deepcopy(filing2); unresolved_correction["event_id"] = "event-unresolved-correction"; unresolved_correction["recorded_at"] = "2026-07-10T00:15:53.500000Z"; unresolved_correction["payload"]["finding_revision"] = 3; unresolved_correction["payload"]["supersedes_revision"] = 2
        correction_block_code = None
        try:
            append_event(engagement, unresolved_correction)
        except RecordError as exc:
            correction_block_code = exc.code
        checks.append(("confirmed_with_correction blocks filing until a fresh correction-bound adjudication", correction_block_code == "review_adjudication_not_fresh", str(correction_block_code or "unresolved correction allowed finding revision")))
        review3_path = reviews_dir / "review-claim-3.json"; review3 = claim_review("review-claim-3", "2026-07-10T00:15:54Z", "confirmed", "F-selftest", 2, "event-regrade-correction"); review3["input_refs"].extend(["event-regrade-escalation", "attempt-escalation", "artifact-escalation", "event-regrade-correction", "event-review-poc-mismatch", "event-review-poc-reward-1", "review-poc-reward-2"]); review3["input_refs"] = sorted(set(review3["input_refs"])); review3["input_hash"] = compute_review_input_hash(engagement, review3, build_reference_index(engagement)); review3_path.write_bytes(canonical_json_bytes(review3))
        review3_commit = base_event(event_id="event-review-claim-3-commit", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:55Z", actor_role="operator", actor_id="operator-selftest", event_type="record.committed", rationale="Commit correction adjudication.", payload={"record_path": "reviews/review-claim-3.json", "record_digest": sha256_file(review3_path), "record_type": "review", "record_id": "review-claim-3", "record_revision": None}); append_event(engagement, review3_commit)
        adjudication3 = base_event(event_id="event-claim-correction-confirmed", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:56Z", actor_role="reviewer", actor_id="reviewer-selftest", event_type="claim.adjudicated", rationale="Independent review confirms corrected bounded claim.", payload={"entity_id": "F-selftest", "status": "confirmed", "review_ref": "review-claim-3", "review_digest": sha256_file(review3_path)}, review_refs=["review-claim-3"], state_changes=[{"dimension": "claim", "entity_id": "F-selftest", "previous": "confirmed", "current": "confirmed"}]); append_event(engagement, adjudication3)
        adjudicated_correction_state = reduce_engagement(engagement)
        missing_escalation_evidence = copy.deepcopy(adjudicated_correction_state); missing_escalation_evidence["claim_adjudications"]["F-selftest"]["input_refs"].remove("artifact-escalation")
        missing_second_review = copy.deepcopy(adjudicated_correction_state); missing_second_review["claim_adjudications"]["F-selftest"]["input_refs"].remove("review-poc-reward-2")
        checks.append(("filing adjudication binds both routed evidence and the distinct second Pocinator review", _filing_blocking_review_error(adjudicated_correction_state, "F-selftest") is None and _filing_blocking_review_error(missing_escalation_evidence, "F-selftest") == "review_adjudication_inputs_missing" and _filing_blocking_review_error(missing_second_review, "F-selftest") == "review_adjudication_inputs_missing", str(adjudicated_correction_state["outstanding_reviews"])))
        finding3 = json.loads(json.dumps(finding2)); finding3.update({"revision": 3, "supersedes_revision": 2, "recorded_at": "2026-07-10T00:15:57Z", "change_reason": "Resolve regrade correction and evidence-routed escalation.", "claim_state": "confirmed"}); finding3["claims"]["uncertainty"] = ["future versions not assessed"]; finding3["adjudication"] = {"review_ref": "review-claim-3", "justification": "Fresh review confirms the corrected bounded tuple."}
        finding3_path = finding_dir / "rev-3.json"; finding3_path.write_bytes(canonical_json_bytes(finding3)); finding3_commit = base_event(event_id="event-finding-3-commit", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:57.500000Z", actor_role="operator", actor_id="operator-selftest", event_type="record.committed", rationale="Commit corrected finding revision three.", payload={"record_path": "findings/F-selftest/rev-3.json", "record_digest": sha256_file(finding3_path), "record_type": "finding-v3", "record_id": "F-selftest", "record_revision": 3}); append_event(engagement, finding3_commit)
        filing3 = base_event(event_id="event-finding-revision-3", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:58Z", actor_role="operator", actor_id="operator-selftest", event_type="finding.revised", rationale="Operator files correction-bound contiguous revision.", payload={"finding_id": "F-selftest", "finding_revision": 3, "status": "confirmed", "finding_digest": sha256_file(finding3_path), "adjudication_review_ref": "review-claim-3", "adjudication_review_digest": sha256_file(review3_path), "adjudication_event_ref": "event-claim-correction-confirmed", "supersedes_revision": 2, "change_reason": "Resolve regrade correction and evidence-routed escalation.", "resolves_review_refs": ["event-regrade-escalation", "event-regrade-correction"]}, entity_refs=["F-selftest", "event-claim-correction-confirmed"], finding_refs=["F-selftest"], review_refs=["review-claim-3"]); append_event(engagement, filing3)
        corrected_state = reduce_engagement(engagement)
        checks.append(("correction review closes only through a contiguous adjudicated revision", corrected_state["findings"]["F-selftest"]["revision"] == 3 and not any(item["review_ref"] in {"event-regrade-escalation", "event-regrade-correction"} for item in corrected_state["outstanding_reviews"]), str(corrected_state["outstanding_reviews"])))
        checks.append(("finding revision makes prior report visibly historical", corrected_state["reports"][report_manifest["report_id"]]["status"] == "historical" and "revision 3" in corrected_state["reports"][report_manifest["report_id"]]["historical_reason"], str(corrected_state["reports"])))

        tuple_hash3 = claim_tuple_hash(finding3)

        refuted_case = root / "regrade-refuted-debt"; shutil.copytree(engagement, refuted_case); refuted_reviews = refuted_case / "reviews"
        refuted_regrade = json.loads(json.dumps(correction)); refuted_regrade.update({"review_id": "review-regrade-refuted", "recorded_at": "2026-07-10T00:15:59Z", "finding_revision": 3, "verdict": "refuted", "rationale": "Independent regrade refutes the current bounded claim.", "corrections": ["Adjudicate the independent refutation before any revision."], "required_next_actions": ["record a fresh refutation-bound claim adjudication"], "claim_tuple_hash": tuple_hash3, "prior_review_run_ids": ["run-review-claim-3"], "escalation_claims": [], "blocked_reason": None}); refuted_regrade["independence"].update({"reviewer_id": "refutation-reviewer", "reviewer_run_id": "run-regrade-refuted", "originating_run_id": "event-finding-revision-3"}); refuted_regrade["input_hash"] = compute_review_input_hash(refuted_case, refuted_regrade, build_reference_index(refuted_case)); refuted_regrade_path = refuted_reviews / "regrade-refuted.json"; refuted_regrade_path.write_bytes(canonical_json_bytes(refuted_regrade))
        _append_kernel_event(refuted_case, base_event(event_id="event-regrade-refuted-commit", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:59.100000Z", actor_role="operator", actor_id="operator-selftest", event_type="record.committed", rationale="Commit independent refutation.", payload={"record_path": "reviews/regrade-refuted.json", "record_digest": sha256_file(refuted_regrade_path), "record_type": "review", "record_id": "review-regrade-refuted", "record_revision": None}))
        _append_kernel_event(refuted_case, base_event(event_id="event-regrade-refuted", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:59.200000Z", actor_role="reviewer", actor_id="refutation-reviewer", event_type="review.regrade_completed", rationale="Independent refutation becomes explicit filing debt.", payload={"review_ref": "review-regrade-refuted", "finding_id": "F-selftest", "finding_revision": 3, "verdict": "refuted", "claim_tuple_hash": tuple_hash3}, review_refs=["review-regrade-refuted"], finding_refs=["F-selftest"]))
        refuted_open_state = reduce_engagement(refuted_case)
        refuted_row = next(item for item in refuted_open_state["outstanding_reviews"] if item["review_ref"] == "event-regrade-refuted")

        confirmation_shop = claim_review("review-claim-confirmation-shop", "2026-07-10T00:15:59.300000Z", "confirmed", "F-selftest", 3, "event-regrade-refuted"); confirmation_shop["input_refs"] = sorted({*review3["input_refs"], "event-regrade-refuted"}); confirmation_shop["input_hash"] = compute_review_input_hash(refuted_case, confirmation_shop, build_reference_index(refuted_case)); confirmation_shop_path = refuted_reviews / "claim-confirmation-shop.json"; confirmation_shop_path.write_bytes(canonical_json_bytes(confirmation_shop))
        _append_kernel_event(refuted_case, base_event(event_id="event-claim-confirmation-shop-commit", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:59.400000Z", actor_role="operator", actor_id="operator-selftest", event_type="record.committed", rationale="Commit an adversarial later confirmation review.", payload={"record_path": "reviews/claim-confirmation-shop.json", "record_digest": sha256_file(confirmation_shop_path), "record_type": "review", "record_id": "review-claim-confirmation-shop", "record_revision": None}))
        confirmation_shop_code = None
        try:
            _append_kernel_event(refuted_case, base_event(event_id="event-claim-confirmation-shop", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:59.500000Z", actor_role="reviewer", actor_id="reviewer-selftest", event_type="claim.adjudicated", rationale="A later confirmation must not erase independent refutation debt.", payload={"entity_id": "F-selftest", "status": "confirmed", "review_ref": "review-claim-confirmation-shop", "review_digest": sha256_file(confirmation_shop_path)}, review_refs=["review-claim-confirmation-shop"], state_changes=[{"dimension": "claim", "entity_id": "F-selftest", "previous": "confirmed", "current": "confirmed"}]))
        except RecordError as exc:
            confirmation_shop_code = exc.code

        refutation_claim = claim_review("review-claim-refuted", "2026-07-10T00:15:59.600000Z", "refuted", "F-selftest", 3, "event-regrade-refuted"); refutation_claim["input_refs"] = sorted({*review3["input_refs"], "event-regrade-refuted"}); refutation_claim["input_hash"] = compute_review_input_hash(refuted_case, refutation_claim, build_reference_index(refuted_case)); refutation_claim_path = refuted_reviews / "claim-refuted.json"; refutation_claim_path.write_bytes(canonical_json_bytes(refutation_claim))
        _append_kernel_event(refuted_case, base_event(event_id="event-claim-refuted-commit", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:59.700000Z", actor_role="operator", actor_id="operator-selftest", event_type="record.committed", rationale="Commit the refutation-bound claim review.", payload={"record_path": "reviews/claim-refuted.json", "record_digest": sha256_file(refutation_claim_path), "record_type": "review", "record_id": "review-claim-refuted", "record_revision": None}))
        _append_kernel_event(refuted_case, base_event(event_id="event-claim-refuted", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:59.800000Z", actor_role="reviewer", actor_id="reviewer-selftest", event_type="claim.adjudicated", rationale="Fresh claim adjudication records the independent refutation.", payload={"entity_id": "F-selftest", "status": "refuted", "review_ref": "review-claim-refuted", "review_digest": sha256_file(refutation_claim_path)}, review_refs=["review-claim-refuted"], state_changes=[{"dimension": "claim", "entity_id": "F-selftest", "previous": "confirmed", "current": "refuted"}]))
        refuted_adjudicated_state = reduce_engagement(refuted_case); refuted_queue_row = next(item for item in refuted_adjudicated_state["work_queue"] if item["class"] == "review_obligation_open" and item["entity"]["id"] == "event-regrade-refuted"); refuted_next_action = decorate_work_queue_item(refuted_queue_row, refuted_adjudicated_state, refuted_case)["next_action"]
        checks.append(("refuted regrade becomes disposition-bound debt that rejects confirmation-shopping and advances only after a fresh exact refutation adjudication", refuted_row.get("required_claim_status") == "refuted" and confirmation_shop_code == "claim_review_obligation_disposition_mismatch" and refuted_adjudicated_state["claim_adjudications"]["F-selftest"]["status"] == "refuted" and _filing_blocking_review_error(refuted_adjudicated_state, "F-selftest") is None and refuted_next_action["action_id"] == "request_finding_revision_authority", str({"row": refuted_row, "shop": confirmation_shop_code, "action": refuted_next_action})))

        blocked_review = json.loads(json.dumps(correction)); blocked_review.update({"review_id": "review-regrade-blocked", "recorded_at": "2026-07-10T00:15:59Z", "finding_revision": 3, "verdict": "blocked", "rationale": "Pinned proof environment is unavailable; truth remains unchanged.", "corrections": [], "required_next_actions": ["restore pinned environment"], "claim_tuple_hash": tuple_hash3, "prior_review_run_ids": ["run-review-claim-3"], "escalation_claims": [], "blocked_reason": "Pinned proof environment unavailable."}); blocked_review["independence"].update({"reviewer_id": "blocked-reviewer", "reviewer_run_id": "run-regrade-blocked", "originating_run_id": "event-finding-revision-3"}); blocked_review["input_hash"] = compute_review_input_hash(engagement, blocked_review, build_reference_index(engagement)); blocked_path = reviews_dir / "regrade-blocked.json"; blocked_path.write_bytes(canonical_json_bytes(blocked_review))
        blocked_commit = base_event(event_id="event-regrade-blocked-commit", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:59.200000Z", actor_role="operator", actor_id="operator-selftest", event_type="record.committed", rationale="Commit blocked regrade.", payload={"record_path": "reviews/regrade-blocked.json", "record_digest": sha256_file(blocked_path), "record_type": "review", "record_id": "review-regrade-blocked", "record_revision": None}); append_event(engagement, blocked_commit)
        blocked_event = base_event(event_id="event-regrade-blocked", engagement_id=engagement.name, recorded_at="2026-07-10T00:15:59.500000Z", actor_role="reviewer", actor_id="blocked-reviewer", event_type="review.regrade_completed", rationale="Blocked review records no truth change.", payload={"review_ref": "review-regrade-blocked", "finding_id": "F-selftest", "finding_revision": 3, "verdict": "blocked", "claim_tuple_hash": tuple_hash3}, review_refs=["review-regrade-blocked"], finding_refs=["F-selftest"]); append_event(engagement, blocked_event)
        blocked_state = reduce_engagement(engagement); checks.append(("typed blocked regrade preserves finding truth and names blocker", blocked_state["findings"]["F-selftest"]["status"] == "confirmed" and _filing_blocking_review_error(blocked_state, "F-selftest") == "regrade_review_blocked" and any(item["status"] == "blocked" for item in blocked_state["outstanding_reviews"]), str(blocked_state["outstanding_reviews"])))
        blocked_source = root / "blocked-review-source"; shutil.copytree(engagement, blocked_source)
        blocked_manual_filing = copy.deepcopy(filing3); blocked_manual_filing["event_id"] = "event-blocked-manual-filing"; blocked_manual_filing["recorded_at"] = "2026-07-10T00:16:00Z"; blocked_manual_filing["payload"].update({"finding_revision": 4, "supersedes_revision": 3, "resolves_review_refs": []})
        try:
            _append_kernel_event(blocked_source, blocked_manual_filing)
            blocked_manual_code = None
        except RecordError as exc:
            blocked_manual_code = exc.code
        blocked_queue_row = next(item for item in blocked_state["work_queue"] if item["class"] == "review_obligation_open" and item["entity"]["id"] == "event-regrade-blocked")
        blocked_next_action = decorate_work_queue_item(blocked_queue_row, blocked_state, engagement.absolute())["next_action"]

        def supersede_blocked_regrade(case: Path, suffix: str, verdict: str) -> dict[str, Any]:
            fresh = json.loads(json.dumps(blocked_review)); fresh.update({"review_id": f"review-regrade-supersede-{suffix}", "recorded_at": "2026-07-10T00:16:00.100000Z", "verdict": verdict, "rationale": f"Fresh independent review records {verdict} without hiding prior debt.", "corrections": [], "required_next_actions": ["preserve the replacement blocker"] if verdict == "blocked" else [], "prior_review_run_ids": ["run-regrade-blocked"], "blocked_reason": "Fresh review remains blocked." if verdict == "blocked" else None}); fresh["independence"].update({"reviewer_id": f"superseding-reviewer-{suffix}", "reviewer_run_id": f"run-regrade-supersede-{suffix}", "originating_run_id": "event-finding-revision-3"}); fresh["input_hash"] = compute_review_input_hash(case, fresh, build_reference_index(case)); fresh_path = case / "reviews" / f"regrade-supersede-{suffix}.json"; fresh_path.write_bytes(canonical_json_bytes(fresh))
            _append_kernel_event(case, base_event(event_id=f"event-regrade-supersede-{suffix}-commit", engagement_id=engagement.name, recorded_at="2026-07-10T00:16:00.200000Z", actor_role="operator", actor_id="operator-selftest", event_type="record.committed", rationale="Commit fresh exact superseding regrade.", payload={"record_path": f"reviews/regrade-supersede-{suffix}.json", "record_digest": sha256_file(fresh_path), "record_type": "review", "record_id": fresh["review_id"], "record_revision": None}))
            _append_kernel_event(case, base_event(event_id=f"event-regrade-supersede-{suffix}", engagement_id=engagement.name, recorded_at="2026-07-10T00:16:00.300000Z", actor_role="reviewer", actor_id=fresh["independence"]["reviewer_id"], event_type="review.regrade_completed", rationale="Explicitly supersede only the exact named blocked row.", payload={"review_ref": fresh["review_id"], "finding_id": "F-selftest", "finding_revision": 3, "verdict": verdict, "claim_tuple_hash": tuple_hash3, "resolves_review_refs": ["event-regrade-blocked"]}, review_refs=[fresh["review_id"]], finding_refs=["F-selftest"]))
            return reduce_engagement(case)

        supersede_confirmed_case = root / "blocked-review-superseded-confirmed"; shutil.copytree(blocked_source, supersede_confirmed_case); superseded_confirmed_state = supersede_blocked_regrade(supersede_confirmed_case, "confirmed", "confirmed")
        supersede_blocked_case = root / "blocked-review-superseded-blocked"; shutil.copytree(blocked_source, supersede_blocked_case); superseded_blocked_state = supersede_blocked_regrade(supersede_blocked_case, "blocked", "blocked")
        replacement_blocked_rows = [row for row in superseded_blocked_state["outstanding_reviews"] if row.get("review_type") == "regrade" and row.get("status") == "blocked"]
        blocked_action_text = str(blocked_next_action["required_inputs"])
        checks.append(("blocked review debt rejects filing and supports only exact prior-run supersession; blocked-to-blocked replaces rather than erases debt", blocked_manual_code == "regrade_review_blocked" and blocked_next_action["action_id"] == "supersede_blocked_review_obligation" and "event-regrade-blocked" in blocked_action_text and "verdict is confirmed" not in blocked_action_text and not any(row.get("review_ref") == "event-regrade-blocked" for row in superseded_confirmed_state["outstanding_reviews"]) and _filing_blocking_review_error(superseded_confirmed_state, "F-selftest") is None and superseded_confirmed_state["findings"]["F-selftest"]["status"] == "confirmed" and len(replacement_blocked_rows) == 1 and replacement_blocked_rows[0]["review_ref"] == "event-regrade-supersede-blocked" and superseded_blocked_state["findings"]["F-selftest"]["status"] == "confirmed", str({"manual": blocked_manual_code, "action": blocked_next_action, "confirmed": superseded_confirmed_state["outstanding_reviews"], "blocked": replacement_blocked_rows})))
        current_report = generate_report(engagement, "F-selftest", 3, ["claim-mechanism", "claim-reach", "claim-impact"], [], "operator-selftest", "2026-07-10T00:15:59.600000Z")
        accept_report(engagement, current_report["report_id"], "operator-selftest", "Claims and proof links match revision three.", "2026-07-10T00:15:59.700000Z")
        submission_path = engagement / "submissions" / "F-selftest.txt"; submission_path.write_text("Operator-authored external submission for F-selftest revision 3.\n", encoding="utf-8")
        submission_id = record_submission(engagement, current_report["report_id"], submission_path, "selftest-program", "operator-selftest", "2026-07-10T00:15:59.800000Z")
        submitted_state = reduce_engagement(engagement); checks.append(("external submission remains separate, operator-authored, and reduced from events", submitted_state["reports"][current_report["report_id"]]["status"] == "submitted" and submission_id in submitted_state["submission_refs"] and submission_path.read_bytes() != (engagement / current_report["report_path"]).read_bytes(), str(submitted_state["reports"])))
        package_fixture.write_bytes(b"changed pinned package fixture\n"); changed_digest = sha256_file(package_fixture); collect_preflight(engagement, preflight_id="preflight-changed-target", mode="package", target=package_fixture, expected_identity=changed_digest, runtime=runtime_fixture, reproduction_argv=[str(Path(sys.executable).resolve()), "-c", "pass"], operator_id="operator-selftest", recorded_at="2026-07-10T00:15:59.850000Z", operator_redaction_attested=True)
        stale_attempt = attempt_proposal("attempt-stale-environment", "2026-07-10T00:15:59.900000Z", "environment_check", "no_signal", "Attempt incorrectly tries to reuse the superseded target identity.", []); stale_environment_blocked = False
        try:
            append_attempt(engagement, stale_attempt)
        except RecordError as exc:
            stale_environment_blocked = exc.code == "attempt_environment_not_active"
        checks.append(("changing target identity prevents stale preflight reuse", stale_environment_blocked and reduce_engagement(engagement)["active_environment_ref"] == "preflight-changed-target" and all(item["attempt_id"] != "attempt-stale-environment" for item in read_ledger(engagement, "attempt")), "stale preflight was reused"))

        rendered = render_claim_proof(finding2)
        checks.append(("claim-to-proof rendering binds every atomic claim and preserves inferred impact labels", tuple_hash in rendered and all(claim_id in rendered for claim_id in ("claim-mechanism", "claim-reach", "claim-impact")) and "demonstrated" in rendered, rendered))

        manifest_path = engagement / "legacy" / "migration-manifest.json"; manifest_path.parent.mkdir(exist_ok=True); manifest_path.write_bytes(canonical_json_bytes({"schema_version": 1, "migration_id": "migration-selftest", "engagement_id": engagement.name, "recorded_at": "2026-07-10T00:16:00Z", "source_inventory_hash": "sha256:" + "0" * 64, "operator": {"role": "operator", "id": "operator-selftest"}, "entries": [], "outcome_counts": {"imported": 0, "needs_review": 0, "skipped": 0, "errors": 0}}))
        commit_event = base_event(event_id="event-record-committed", engagement_id=engagement.name, recorded_at="2026-07-10T00:16:00Z", actor_role="operator", actor_id="operator-selftest", event_type="record.committed", rationale="Commit immutable self-test migration manifest.", payload={"record_path": "legacy/migration-manifest.json", "record_digest": sha256_file(manifest_path), "record_type": "migration-manifest", "record_id": "migration-selftest", "record_revision": None})
        append_event(engagement, commit_event)
        checks.append(("record.committed binds an existing immutable file digest", reduce_engagement(engagement)["last_event_id"] == "event-record-committed", "committed file not reducible"))
        missing_commit = base_event(event_id="event-missing-record", engagement_id=engagement.name, recorded_at="2026-07-10T00:16:30Z", actor_role="operator", actor_id="operator-selftest", event_type="record.committed", rationale="Missing committed file must fail.", payload={"record_path": "reports/missing.manifest.json", "record_digest": "sha256:" + "0" * 64, "record_type": "report-manifest", "record_id": "report-manifest-missing", "record_revision": None})
        before_missing_commit = (engagement / "events.jsonl").read_bytes(); missing_commit_caught = False
        try:
            append_event(engagement, missing_commit)
        except RecordError as exc:
            missing_commit_caught = exc.code == "committed_file_missing"
        checks.append(("record.committed cannot point to a missing file", missing_commit_caught and (engagement / "events.jsonl").read_bytes() == before_missing_commit, "missing file commit appended"))
        committed_tampered = root / "committed-tampered"; shutil.copytree(engagement, committed_tampered); (committed_tampered / "legacy" / "migration-manifest.json").write_text("{}\n")
        committed_tamper_caught = False
        try:
            reduce_engagement(committed_tampered)
        except RecordError as exc:
            committed_tamper_caught = exc.code == "committed_file_digest_mismatch"
        checks.append(("modified committed record fails reduction", committed_tamper_caught, "modified committed record accepted"))
        report_tampered = root / "report-tampered"; shutil.copytree(engagement, report_tampered); (report_tampered / "reports" / "F-selftest-r3.md").write_text("tampered report\n", encoding="utf-8")
        report_tamper_blocked = False
        try:
            reduce_engagement(report_tampered)
        except RecordError as exc:
            report_tamper_blocked = exc.code == "report_manifest_binding_mismatch"
        checks.append(("report byte replacement fails revision-bound reduction", report_tamper_blocked, "tampered report reduced"))
        record_orphan = root / "record-orphan"; shutil.copytree(engagement, record_orphan); (record_orphan / "reports" / "orphan.manifest.json").write_text("{}\n")
        record_orphan_caught = False
        try:
            reduce_engagement(record_orphan)
        except RecordError as exc:
            record_orphan_caught = exc.code == "orphan_immutable_record"
        checks.append(("orphan immutable record fails reduction", record_orphan_caught, "orphan record accepted"))
        report_orphan = root / "report-orphan"; shutil.copytree(engagement, report_orphan); (report_orphan / "reports" / "rogue.md").write_text("# unbound advisory\n", encoding="utf-8")
        report_orphan_blocked = False
        try:
            reduce_engagement(report_orphan)
        except RecordError as exc:
            report_orphan_blocked = exc.code == "orphan_report_file"
        checks.append(("unbound advisory Markdown fails reduction", report_orphan_blocked, "unbound advisory accepted"))

        current = reduce_engagement(engagement)
        tampered = root / "tampered"; shutil.copytree(engagement, tampered)
        lines = (tampered / "events.jsonl").read_text().splitlines(); value = json.loads(lines[1]); value["rationale"] += " tampered"; lines[1] = json.dumps(value, sort_keys=True, separators=(",", ":")); (tampered / "events.jsonl").write_text("\n".join(lines) + "\n")
        tamper_caught = False
        try:
            read_ledger(tampered, "event")
        except RecordError as exc:
            tamper_caught = exc.code == "ledger_record_hash_mismatch"
        checks.append(("one-byte-equivalent ledger tamper is detected", tamper_caught, "tampered event accepted"))
        noncanonical = root / "noncanonical"; shutil.copytree(engagement, noncanonical)
        lines = (noncanonical / "events.jsonl").read_text().splitlines(); first_value = json.loads(lines[0]); lines[0] = json.dumps(dict(reversed(list(first_value.items()))), separators=(",", ":")); (noncanonical / "events.jsonl").write_text("\n".join(lines) + "\n")
        noncanonical_caught = False
        try:
            read_ledger(noncanonical, "event")
        except RecordError as exc:
            noncanonical_caught = exc.code == "ledger_noncanonical_line"
        checks.append(("noncanonical historical JSONL text fails even when values are unchanged", noncanonical_caught, "noncanonical line accepted"))
        blank = root / "blank-line"; shutil.copytree(engagement, blank)
        lines = (blank / "events.jsonl").read_bytes().splitlines(keepends=True); (blank / "events.jsonl").write_bytes(lines[0] + b"\n" + b"".join(lines[1:]))
        blank_caught = False
        try:
            read_ledger(blank, "event")
        except RecordError as exc:
            blank_caught = exc.code == "ledger_blank_line"
        checks.append(("blank physical JSONL lines fail", blank_caught, "blank line accepted"))

        cross_ledger = root / "cross-ledger"; shutil.copytree(engagement, cross_ledger)
        artifact_lines = [json.loads(line) for line in (cross_ledger / "artifacts.jsonl").read_text().splitlines()]; artifact_lines[-1]["engagement_id"] = "eng-other"; artifact_lines[-1]["record_hash"] = compute_record_hash(artifact_lines[-1]); (cross_ledger / "artifacts.jsonl").write_bytes(b"".join(canonical_json_bytes(item) for item in artifact_lines))
        cross_caught = False
        try:
            reduce_engagement(cross_ledger)
        except RecordError as exc:
            cross_caught = exc.code == "cross_engagement_ledger_record"
        checks.append(("direct-ledger cross-engagement records fail reduction", cross_caught, "cross-engagement artifact reduced"))
        dangling = root / "dangling-ref"; shutil.copytree(engagement, dangling)
        artifact_lines = [json.loads(line) for line in (dangling / "artifacts.jsonl").read_text().splitlines()]; artifact_lines[-1]["target_refs"] = ["target-missing"]; artifact_lines[-1]["record_hash"] = compute_record_hash(artifact_lines[-1]); (dangling / "artifacts.jsonl").write_bytes(b"".join(canonical_json_bytes(item) for item in artifact_lines))
        dangling_caught = False
        try:
            reduce_engagement(dangling)
        except RecordError as exc:
            dangling_caught = exc.code == "record_reference_invalid"
        checks.append(("direct-ledger dangling references fail reduction", dangling_caught, "dangling artifact reference reduced"))
        collision = root / "cross-type-id-collision"; shutil.copytree(engagement, collision)
        collision_event = base_event(event_id="artifact-selftest", engagement_id=engagement.name, recorded_at="2026-07-10T00:17:00Z", actor_role="operator", actor_id="operator-selftest", event_type="observation.recorded", rationale="Cross-type ID collision attack.", payload={"entity_id": "collision-observation", "entity_type": "observation", "status": "recorded"}); append_ledger_record(collision, "event", collision_event)
        collision_blocked = False
        try:
            reduce_engagement(collision)
        except RecordError as exc:
            collision_blocked = exc.code == "cross_type_record_id_collision"
        checks.append(("record IDs cannot collide across event/attempt/artifact/review types", collision_blocked, "cross-type collision reduced"))

        interrupted = root / "interrupted"; shutil.copytree(engagement, interrupted)
        with open(interrupted / "events.jsonl", "ab") as handle: handle.write(b'{\"partial\"')
        interrupted_caught = False
        try:
            read_ledger(interrupted, "event")
        except RecordError as exc:
            interrupted_caught = exc.code == "ledger_unterminated_tail"
        checks.append(("interrupted JSONL tail fails closed without truncation", interrupted_caught, "partial tail accepted"))
        repaired = repair_ledger_tail(interrupted, "event", "operator-selftest", "injected partial append", "2026-07-10T00:17:30Z")
        checks.append(("operator repair quarantines the partial tail and records recovery", (interrupted / repaired["quarantine_path"]).read_bytes() == b'{\"partial\"' and read_ledger(interrupted, "event")[-1]["event_id"] == repaired["event_id"], str(repaired)))

        pending = root / "pending-repair"; shutil.copytree(engagement, pending)
        pending_tail = b'{\"pending\"'; pending_path = pending / "events.jsonl"; prefix = pending_path.read_bytes(); pending_path.write_bytes(prefix + pending_tail)
        pending_digest = sha256_bytes(pending_tail); quarantine_rel = f"legacy/quarantine/event-tail-{pending_digest[-12:]}.bin"; (pending / "legacy" / "quarantine").mkdir(parents=True, exist_ok=True); (pending / quarantine_rel).write_bytes(pending_tail)
        marker = {"schema_version": 1, "ledger_kind": "event", "ledger_path": "events.jsonl", "prefix_digest": sha256_bytes(prefix), "quarantine_path": quarantine_rel, "quarantine_digest": pending_digest, "operator_id": "operator-selftest", "reason": "resume fixture", "recorded_at": "2026-07-10T00:17:45Z"}; (pending / "legacy" / "tail-repair.pending.json").write_bytes(canonical_json_bytes(marker))
        resumed = repair_ledger_tail(pending, "event", "operator-selftest", "resume fixture", "2026-07-10T00:17:45Z")
        checks.append(("repair resumes deterministically after crash between truncation and event", not (pending / "legacy" / "tail-repair.pending.json").exists() and read_ledger(pending, "event")[-1]["event_id"] == resumed["event_id"], str(resumed)))

        authorized_repair = root / "authorized-repair"; shutil.copytree(engagement, authorized_repair); broker_id, broker_session = _local_identity("broker"); repair_now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"); repair_action = _authority_action("repair-ledger-tail", lane_id="lane-repair", executor_id=broker_id, session_id=broker_session, ledger="attempt", operator_id="operator-selftest", reason="repair approved interrupted attempt tail", recorded_at=repair_now); repair_digest = sha256_bytes(canonical_json_bytes(repair_action)); repair_action_relative = "authority/requests/request-repair.action.json"; atomic_write(authorized_repair / repair_action_relative, canonical_json_bytes(repair_action)); repair_state = reduce_engagement(authorized_repair)
        append_event(authorized_repair, base_event(event_id="event-request-repair", engagement_id=repair_state["engagement_id"], recorded_at=repair_now, actor_role="broker", actor_id=broker_id, event_type="authority.requested", rationale="Request exact interrupted-tail repair.", payload={"request_id": "request-repair", "action_kind": "repair-ledger-tail", "action_digest": repair_digest, "action_path": repair_action_relative, "lane_id": "lane-repair", "request_status": "pending_authority", "scope_hash": repair_state["scope_hash"], "environment_ref": repair_state["active_environment_ref"], "expires_at": "2099-07-10T00:00:00Z"}, session_id=broker_session, operation_class="notebook")); append_event(authorized_repair, base_event(event_id="event-resolution-repair", engagement_id=repair_state["engagement_id"], recorded_at=repair_now, actor_role="operator", actor_id="operator-selftest", event_type="authority.resolved", rationale="Approve exact repair only.", payload={"request_id": "request-repair", "request_event_ref": "event-request-repair", "action_digest": repair_digest, "resolution": "approved", "resolved_at": repair_now}, entity_refs=["event-request-repair"], session_id=broker_session, operation_class="authority"))
        with open(authorized_repair / "attempts.jsonl", "ab") as handle: handle.write(b'{"interrupted-attempt"')
        command_repair_tail(argparse.Namespace(engagement=authorized_repair, ledger="attempt", operator_id="operator-selftest", reason="repair approved interrupted attempt tail", recorded_at=repair_now, authority_request_id="request-repair", lane_id="lane-repair", executor_id=broker_id, session_id=broker_session)); checks.append(("approved tail repair verifies authority from intact event prefix before reducing damaged ledger", (authorized_repair / "attempts.jsonl").read_bytes().endswith(b"\n") and read_ledger(authorized_repair, "event")[-1]["payload"].get("authority_request_ref") == "request-repair", "authorized repair did not recover"))

        rollback_event = base_event(event_id="event-short-write", engagement_id=engagement.name, recorded_at="2026-07-10T00:18:00Z", actor_role="operator", actor_id="operator-selftest", event_type="observation.recorded", rationale="Injected short write must roll back.", payload={"entity_id": "observation-short", "entity_type": "observation", "status": "recorded"})
        before_short = (engagement / "events.jsonl").read_bytes(); real_write = __import__("os").write; write_calls = [0]
        def injected_write(fd, data):
            write_calls[0] += 1
            if write_calls[0] == 1:
                return real_write(fd, data[:5])
            raise OSError("injected append interruption")
        short_rolled_back = False
        from unittest.mock import patch
        try:
            with patch("engagement_state.os.write", side_effect=injected_write):
                append_ledger_record(engagement, "event", rollback_event)
        except RecordError as exc:
            short_rolled_back = exc.code == "ledger_append_rolled_back"
        checks.append(("partial append is truncated to the last verified boundary", short_rolled_back and (engagement / "events.jsonl").read_bytes() == before_short and len(read_ledger(engagement, "event")) == current["event_count"], "short write left a tail"))

        forged_prior = base_event(event_id="event-prior-forged-operator", engagement_id=engagement.name, recorded_at="2026-07-10T00:18:05Z", actor_role="operator", actor_id="other-operator", event_type="operator_prior.recorded", rationale="Role label alone must not grant signed-scope authority.", payload={"prior_id": "prior-forged", "prior_statement": "Forged authority.", "strength": "strong", "reason": "adversarial fixture"})
        forged_prior_blocked = False
        try:
            append_event(engagement, forged_prior)
        except RecordError as exc:
            forged_prior_blocked = exc.code == "operator_prior_not_scope_authorized"
        checks.append(("operator prior actor is bound to active signed-scope operator", forged_prior_blocked and (engagement / "events.jsonl").read_bytes() == before_short, "forged operator prior appended"))

        future_refs = root / "future-candidate-refs"; shutil.copytree(engagement, future_refs)
        future_candidate = base_event(event_id="event-candidate-future", engagement_id=engagement.name, recorded_at="2026-07-10T00:18:10Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="candidate.proposed", rationale="Adversarial candidate references later provenance.", payload={"candidate_id": "candidate-future", "source_observation_ref": "event-observation-future", "routing_review_ref": "event-routing-future", "activation_strength": "strong", "card_ids": ["card-selftest"], "status": "queued", "expected_information_gain": 1, "safety_class": "clear_local", "cost_estimate": zero_cost}, entity_refs=["event-observation-future", "event-routing-future"], state_changes=[{"dimension": "search", "entity_id": "candidate-future", "previous": None, "current": "queued"}]); future_candidate["ex_ante"] = {"probability": 0.9, "ordinal": "strong", "recorded_before_outcome": True}
        append_ledger_record(future_refs, "event", future_candidate)
        future_observation = base_event(event_id="event-observation-future", engagement_id=engagement.name, recorded_at="2026-07-10T00:18:11Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="observation.recorded", rationale="Later observation.", payload={"entity_id": "observation-future", "entity_type": "observation", "status": "recorded"}); append_ledger_record(future_refs, "event", future_observation)
        future_routing = base_event(event_id="event-routing-future", engagement_id=engagement.name, recorded_at="2026-07-10T00:18:12Z", actor_role="reviewer", actor_id="reviewer-selftest", event_type="routing.assessed", rationale="Later routing assessment.", payload={"entity_id": "routing-future", "source_observation_ref": "event-observation-future", "activation_strength": "strong", "card_ids": ["card-selftest"], "status": "assessed"}, entity_refs=["event-observation-future"]); append_ledger_record(future_refs, "event", future_routing)
        future_ref_blocked = False
        try:
            reduce_engagement(future_refs)
        except RecordError as exc:
            future_ref_blocked = exc.code == "candidate_source_not_prior_observation"
        checks.append(("candidate provenance must exist earlier in the event ledger", future_ref_blocked, "candidate referenced future provenance"))

        precommit = root / "precommit-reference"; shutil.copytree(engagement, precommit); (precommit / "reviews").mkdir(exist_ok=True)
        review_record = {"schema_version": 1, "review_id": "review-precommit", "engagement_id": engagement.name, "review_type": "signal", "proposed_finding_id": None, "entity_ref": "event-observation-c1", "finding_revision": None, "recorded_at": "2026-07-10T00:18:20Z", "input_refs": ["event-observation-c1"], "input_hash": "sha256:" + "0" * 64, "evidence_refs": [], "conflicting_evidence": [], "independence": {"reviewer_id": "reviewer-selftest", "reviewer_model": "selftest", "reviewer_run_id": "run-review-precommit", "originating_run_id": "event-observation-c1", "fresh_context": True, "prior_verdict_visible": False, "disconfirming_objective": "Refute the routing signal."}, "verdict": "strong", "rationale": "Signal review fixture.", "corrections": [], "required_next_actions": ["route candidate"]}
        review_record["input_hash"] = compute_review_input_hash(precommit, review_record, build_reference_index(precommit))
        review_path = precommit / "reviews" / "precommit.json"; review_path.write_bytes(canonical_json_bytes(review_record))
        precommit_candidate = base_event(event_id="event-candidate-precommit", engagement_id=engagement.name, recorded_at="2026-07-10T00:18:30Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="candidate.proposed", rationale="Adversarial pre-commit review reference.", payload={"candidate_id": "candidate-precommit", "source_observation_ref": "event-observation-c1", "routing_review_ref": "review-precommit", "activation_strength": "strong", "card_ids": ["card-selftest"], "status": "queued", "expected_information_gain": 1, "safety_class": "clear_local", "cost_estimate": zero_cost}, entity_refs=["event-observation-c1", "review-precommit"], state_changes=[{"dimension": "search", "entity_id": "candidate-precommit", "previous": None, "current": "queued"}]); precommit_candidate["ex_ante"] = {"probability": 0.5, "ordinal": "strong", "recorded_before_outcome": True}; append_ledger_record(precommit, "event", precommit_candidate)
        later_commit = base_event(event_id="event-review-later-commit", engagement_id=engagement.name, recorded_at="2026-07-10T00:18:31Z", actor_role="operator", actor_id="operator-selftest", event_type="record.committed", rationale="Commit arrives after forbidden use.", payload={"record_path": "reviews/precommit.json", "record_digest": sha256_file(review_path), "record_type": "review", "record_id": "review-precommit", "record_revision": None}); append_ledger_record(precommit, "event", later_commit)
        precommit_blocked = False
        try:
            reduce_engagement(precommit)
        except RecordError as exc:
            precommit_blocked = exc.code == "record_reference_precedes_commit"
        checks.append(("immutable review must be committed before it can influence search", precommit_blocked, "future record commitment authorized prior reference"))

        dry_bypass = root / "dry-bypass"; shutil.copytree(engagement, dry_bypass)
        fake_review_event = base_event(event_id="event-coverage-review-fake", engagement_id=engagement.name, recorded_at="2026-07-10T00:18:20Z", actor_role="reviewer", actor_id="reviewer-selftest", event_type="review.coverage_completed", rationale="Missing cold review record.", payload={"review_type": "coverage", "verdict": "coverage_dry"}); append_ledger_record(dry_bypass, "event", fake_review_event)
        dry_event = base_event(event_id="event-dry-bypass", engagement_id=engagement.name, recorded_at="2026-07-10T00:18:21Z", actor_role="operator", actor_id="operator-selftest", event_type="coverage.status_changed", rationale="Attempt to close coverage around active work.", payload={"entity_id": engagement.name, "status": "coverage_dry", "coverage_review_ref": "event-coverage-review-fake"}, entity_refs=["event-coverage-review-fake"], state_changes=[{"dimension": "coverage", "entity_id": engagement.name, "previous": "blocked", "current": "coverage_dry"}]); append_ledger_record(dry_bypass, "event", dry_event)
        dry_bypass_blocked = False
        try:
            reduce_engagement(dry_bypass)
        except RecordError as exc:
            dry_bypass_blocked = exc.code == "coverage_review_event_invalid"
        checks.append(("coverage_dry cannot bypass a committed cold coverage review", dry_bypass_blocked, "dry coverage accepted without cold review"))

        drifted = root / "scope-drift"; shutil.copytree(engagement, drifted)
        with open(drifted / "scope.md", "a", encoding="utf-8") as handle: handle.write("\nchanged\n")
        before_drift_write = (drifted / "events.jsonl").read_bytes(); old_scope_after_drift = reduce_engagement(drifted)["scope_hash"]
        broker_id, broker_session = _local_identity("broker"); ordinary_after_drift = base_event(event_id="event-after-scope-drift", engagement_id=engagement.name, recorded_at="2026-07-10T00:19:00Z", actor_role="broker", actor_id=broker_id, event_type="observation.recorded", rationale="Continue a lane already bounded by the prior attestation.", payload={"entity_id": "observation-drift", "entity_type": "observation", "status": "recorded"}, session_id=broker_session, operation_class="notebook"); append_event(drifted, ordinary_after_drift)
        command_propose_scope(argparse.Namespace(engagement=drifted, draft=drifted/"scope.md", actor_id=broker_id, session_id=broker_session, recorded_at="2026-07-10T00:19:01Z", reason="Preserve drifted bytes without activating them.")); drift_state = reduce_engagement(drifted)
        checks.append(("scope drift is preserved as an unattested draft while old-scope lanes continue", old_scope_after_drift == current["scope_hash"] and drift_state["scope_hash"] == current["scope_hash"] and drift_state["scope_drafts"] and (drifted/str(drift_state["scope_drafts"][-1]["draft_path"])).is_file() and (drifted / "events.jsonl").read_bytes().startswith(before_drift_write), "scope drift was activated, lost, or globally stalled"))
        operator_drift = root/"operator-drift"; shutil.copytree(engagement, operator_drift); operator_drift.joinpath("scope.md").write_text(operator_drift.joinpath("scope.md").read_text().replace("Operator: operator-selftest", "Operator: attacker")); redirected_operator_blocked = False
        try: _require_operator_console(operator_drift, "attacker", "resolve-authority")
        except RecordError as exc: redirected_operator_blocked = exc.code == "operator_authority_invalid"
        checks.append(("drifted scope bytes cannot redirect active operator authority", redirected_operator_blocked, "draft operator replaced attested operator"))
        active_hash = current["scope_hash"]
        new_hash = sha256_file(drifted / "scope.md")
        model_reattestation = base_event(event_id="event-model-scope", engagement_id=engagement.name, recorded_at="2026-07-10T00:19:30Z", actor_role="orchestrator", actor_id="model-orchestrator", event_type="scope.attested", rationale="Model must not re-attest scope.", payload={"scope_hash": new_hash, "operator_id": "operator-selftest", "signed_date": "2026-07-10", "record_kernel": "decision-0006-v1", "supersedes_scope_hash": active_hash}, entity_refs=[engagement.name])
        model_scope_blocked = False
        try:
            append_event(drifted, model_reattestation)
        except RecordError as exc:
            model_scope_blocked = exc.code in {"scope_attestation_not_operator_bound", "scope_reattestation_not_operator_bound"}
        checks.append(("model-role scope re-attestation is rejected", model_scope_blocked and reduce_engagement(drifted)["scope_hash"] == active_hash, "model re-attested scope"))
        model_injected = root / "model-scope-injected"; shutil.copytree(drifted, model_injected); injected_proposal = json.loads(json.dumps(model_reattestation)); injected_proposal["payload"]["scope_snapshot_path"] = persist_scope_snapshot(model_injected, new_hash); append_ledger_record(model_injected, "event", injected_proposal)
        injected_scope_caught = False
        try:
            reduce_engagement(model_injected)
        except RecordError as exc:
            injected_scope_caught = exc.code in {"scope_attestation_not_operator_bound", "historical_scope_attestation_mismatch"}
        checks.append(("reducer rejects directly injected model scope authority", injected_scope_caught, "direct model scope event reduced"))
        reattestation = base_event(event_id="event-scope-reattested", engagement_id=engagement.name, recorded_at="2026-07-10T00:20:00Z", actor_role="operator", actor_id="operator-selftest", event_type="scope.attested", rationale="Operator re-attests changed scope bytes.", payload={"scope_hash": new_hash, "operator_id": "operator-selftest", "signed_date": "2026-07-10", "record_kernel": "decision-0006-v1", "supersedes_scope_hash": active_hash}, entity_refs=[engagement.name])
        append_event(drifted, reattestation)
        checks.append(("fresh operator scope re-attestation activates the draft without mutating history", reduce_engagement(drifted)["scope_hash"] == new_hash and (drifted / "events.jsonl").read_bytes().startswith(before_drift_write), "scope re-attestation failed or rewrote ledger"))

        closure_documents = test_corpus_documents(
            row_count=3,
            frozen_at="2026-07-10T00:20:59Z",
        )
        closure = root / "memory-closure"; closure.mkdir(); closure.joinpath("scope.md").write_text(scope_with_corpus_pin(scope.replace("self-test", "memory-closure"), closure_documents[1]), encoding="utf-8"); initialize_engagement(closure, "2026-07-10T00:21:00Z"); closure_state = reduce_engagement(closure)
        append_event(closure, base_event(event_id="event-closure-blocked", engagement_id=closure.name, recorded_at="2026-07-10T00:21:01Z", actor_role="operator", actor_id="operator-selftest", event_type="engagement.blocked", rationale="Exercise an evidence-preserving blocked closure.", payload={"entity_id": closure.name, "status": "blocked", "reason": "A bounded fixture blocker prevents coverage completion."}, state_changes=[{"dimension": "engagement", "entity_id": closure.name, "previous": "active", "current": "blocked"}, {"dimension": "coverage", "entity_id": closure.name, "previous": "active", "current": "blocked"}]))
        append_event(closure, base_event(event_id="event-cleanup-na", engagement_id=closure.name, recorded_at="2026-07-10T00:21:02Z", actor_role="operator", actor_id="operator-selftest", event_type="cleanup.updated", rationale="No live artifact cleanup exists.", payload={"entity_id": "cleanup-none", "status": "not_applicable", "scope_hash": closure_state["scope_hash"], "operator_id": "operator-selftest", "updated_at": "2026-07-10T00:21:02Z", "cleanup_obligations": [{"obligation_id": "cleanup-none", "kind": "no_live_artifacts", "status": "not_applicable", "artifact_refs": [], "rationale": "The engagement created no live target artifacts.", "closed_at": "2026-07-10T00:21:02Z"}]}, state_changes=[{"dimension": "cleanup", "entity_id": "cleanup-none", "previous": None, "current": "not_applicable"}]))
        missing_memory_blocked = False
        try: close_engagement(closure, "operator-selftest", "Must not close without memory disposition.", "2026-07-10T00:21:03Z")
        except RecordError as exc: missing_memory_blocked = exc.code == "engagement_closure_memory_missing"
        memory_proposal = {"schema_version": 1, "disposition_id": "memory-closure-final", "engagement_id": closure.name, "recorded_at": "2026-07-10T00:21:04Z", "scope_hash": closure_state["scope_hash"], "disposition": "no_novel_lesson", "lesson_kind": "none", "lesson_summary": None, "rationale": "Independent operator review found no reusable lesson.", "candidate_refs": [], "source_refs": {key: [] for key in ("event_refs", "candidate_refs", "hypothesis_refs", "attempt_refs", "artifact_refs", "review_refs", "finding_refs", "environment_refs")}, "sanitization": {"status": "not_applicable", "secret_scan_status": "clean", "target_identifiers_removed": True, "credential_values_removed": True, "harmful_recipe_removed": True, "target_terms_checked": [], "notes": "No lesson body exists to promote."}, "human_review": {"reviewer": {"role": "operator", "id": "operator-selftest"}, "reviewed_at": "2026-07-10T00:21:04Z", "decision": "no_novel_lesson", "rationale": "No novel lesson survived review.", "source_material_compared": True, "abstraction_only": True, "plane1_pr_required": True}, "reopening_condition": None, "provenance": {"actor": {"role": "operator", "id": "operator-selftest"}}}
        unsafe_promotion = json.loads(json.dumps(memory_proposal)); unsafe_promotion.update({"disposition": "promote", "lesson_kind": "negative", "lesson_summary": "A target-neutral defensive lesson.", "candidate_refs": ["candidate-c1"]}); unsafe_promotion["sanitization"].update({"status": "sanitized", "target_terms_checked": [closure.name]}); unsafe_promotion["human_review"]["decision"] = "promote"; unsafe_promotion["human_review"]["rationale"] = "Run curl against a retained endpoint."
        unsafe_promotion_blocked = False
        try: _validate_promotable_abstraction(unsafe_promotion)
        except RecordError as exc: unsafe_promotion_blocked = exc.code == "memory_abstraction_not_sanitized"
        checks.append(("promote scrubbing covers every retained human text field", unsafe_promotion_blocked, "unsafe review rationale passed promotion scrub"))
        proposal_path = root / "memory-proposal.json"; write_canonical_json(proposal_path, memory_proposal); recorded_memory = record_memory_disposition(closure, proposal_path, "operator-selftest"); retry_count = reduce_engagement(closure)["event_count"]; record_memory_disposition(closure, proposal_path, "operator-selftest")
        closure_manifest_ref, closure_tsv_ref = register_test_corpus(
            closure,
            row_count=3,
            created_at="2026-07-10T00:21:04Z",
            documents=closure_documents,
        )
        nonblocking_closure = root / "closure-with-awaiting-operator"
        shutil.copytree(closure, nonblocking_closure)
        pending_action = _authority_action(
            "test-authority",
            lane_id="lane-nonblocking-close",
            value="operator-may-answer-later",
        )
        pending_action_digest = sha256_bytes(canonical_json_bytes(pending_action))
        append_event(
            nonblocking_closure,
            base_event(
                event_id="event-nonblocking-close-authority-request",
                engagement_id=closure.name,
                recorded_at="2026-07-10T00:21:04.100000Z",
                actor_role="orchestrator",
                actor_id="orchestrator-selftest",
                event_type="authority.requested",
                rationale="Leave one operator decision pending without representing executable work.",
                payload={
                    "request_id": "request-nonblocking-close",
                    "action_kind": "test-authority",
                    "action_digest": pending_action_digest,
                    "lane_id": "lane-nonblocking-close",
                    "request_status": "pending_authority",
                    "scope_hash": closure_state["scope_hash"],
                    "environment_ref": None,
                    "expires_at": None,
                },
                session_id="session-nonblocking-close",
                operation_class="notebook",
            ),
        )
        nonblocking_before = reduce_engagement(nonblocking_closure)
        nonblocking_closed = close_engagement(
            nonblocking_closure,
            "operator-selftest",
            "Only a nonblocking operator decision remains.",
            "2026-07-10T00:21:04.200000Z",
        )
        checks.append((
            "actual engagement closure is permitted when the only queued row awaits the operator and is explicitly nonblocking",
            len(nonblocking_before["work_queue"]) == 1
            and nonblocking_before["work_queue"][0]["class"] == "awaiting_operator"
            and nonblocking_before["work_queue"][0]["blocking"] is False
            and nonblocking_closed["authority_requests"]["request-nonblocking-close"]["status"] == "pending_authority"
            and all(item["blocking"] is False for item in nonblocking_closed["work_queue"]),
            str({"before": nonblocking_before["work_queue"], "after": nonblocking_closed["work_queue"]}),
        ))
        budget_closure = root / "budget-closure"; shutil.copytree(closure, budget_closure); _append_kernel_event(budget_closure, base_event(event_id="event-budget-closure-bounded", engagement_id=closure.name, recorded_at="2026-07-10T00:21:04.500000Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="coverage.status_changed", rationale="The bounded closure records two queue disposals against a frozen three-row corpus denominator.", payload={"entity_id": closure.name, "status": "budget_bounded", "disposed_count": 2, "enumerated_count": 3, "corpus_enumeration_ref": closure_manifest_ref}, evidence_refs=[closure_manifest_ref, closure_tsv_ref], state_changes=[{"dimension": "coverage", "entity_id": closure.name, "previous": "blocked", "current": "budget_bounded"}])); budget_closed = close_engagement(budget_closure, "operator-selftest", "Cleanup, budget-bounded coverage, reports, and memory are terminal.", "2026-07-10T00:21:05Z")
        checks.append(("budget-bounded is terminal coverage accepted by closure only with its frozen denominator and an empty blocking queue", budget_closed["coverage"] == "budget_bounded" and budget_closed["coverage_counts"]["enumerated_count"] == 3 and budget_closed["coverage_counts"]["corpus_enumeration_ref"] == closure_manifest_ref, str(budget_closed)))

        close_escape = root / "close-with-blocking-work"; shutil.copytree(closure, close_escape)
        append_event(close_escape, base_event(event_id="event-close-escape-prior", engagement_id=closure.name, recorded_at="2026-07-10T00:21:04.100000Z", actor_role="operator", actor_id="operator-selftest", event_type="operator_prior.recorded", rationale="Introduce one explicit unresolved branch after terminal coverage.", payload={"prior_id": "prior-close-escape", "prior_statement": "A branch remains unresolved.", "strength": "strong", "reason": "adversarial closure repro"}))
        close_escape_hypothesis = json.loads(json.dumps(hypothesis["payload"])); close_escape_hypothesis.update({"hypothesis_id": "hypothesis-close-escape", "origin_type": "operator_prior", "origin_ref": "event-close-escape-prior", "status": "queued"}); close_escape_hypothesis.pop("candidate_ref", None)
        append_event(close_escape, base_event(event_id="event-close-escape-hypothesis", engagement_id=closure.name, recorded_at="2026-07-10T00:21:04.200000Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="hypothesis.created", rationale="Leave one blocking hypothesis on the record.", payload=close_escape_hypothesis, entity_refs=["event-close-escape-prior"], state_changes=[{"dimension": "search", "entity_id": "hypothesis-close-escape", "previous": None, "current": "queued"}]))
        append_event(close_escape, base_event(event_id="event-close-escape-hypothesis-selected", engagement_id=closure.name, recorded_at="2026-07-10T00:21:04.250000Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="hypothesis.status_changed", rationale="Select the unresolved closure-control branch.", payload={"hypothesis_id": "hypothesis-close-escape", "status": "selected", "reason": "execute the closure-control branch", "experiment_refs": [], "control_refs": [], "supporting_evidence_refs": [], "conflicting_evidence_refs": [], "disposition_rationale": "The closure-control branch is selected.", "unresolved_questions": [], "next_route": close_escape_hypothesis["next_experiment"]}, state_changes=[{"dimension": "search", "entity_id": "hypothesis-close-escape", "previous": "queued", "current": "selected"}]))
        append_event(close_escape, base_event(event_id="event-close-escape-hypothesis-running", engagement_id=closure.name, recorded_at="2026-07-10T00:21:04.300000Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="hypothesis.status_changed", rationale="Begin the closure-control branch while leaving its first attempt unrecorded.", payload={"hypothesis_id": "hypothesis-close-escape", "status": "running", "reason": "begin the closure-control branch", "experiment_refs": [], "control_refs": [], "supporting_evidence_refs": [], "conflicting_evidence_refs": [], "disposition_rationale": "The branch is running and has no attempt yet.", "unresolved_questions": [], "next_route": close_escape_hypothesis["next_experiment"]}, state_changes=[{"dimension": "search", "entity_id": "hypothesis-close-escape", "previous": "selected", "current": "running"}]))
        append_event(close_escape, base_event(event_id="event-close-escape-observation", engagement_id=closure.name, recorded_at="2026-07-10T00:21:04.310000Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="observation.recorded", rationale="Record one source observation for a candidate that must remain queued.", payload={"entity_id": "observation-close-escape", "entity_type": "observation", "status": "recorded"}))
        append_event(close_escape, base_event(event_id="event-close-escape-routing", engagement_id=closure.name, recorded_at="2026-07-10T00:21:04.320000Z", actor_role="reviewer", actor_id="reviewer-selftest", event_type="routing.assessed", rationale="Route the closure-control observation into one bounded candidate.", payload={"entity_id": "routing-close-escape", "source_observation_ref": "event-close-escape-observation", "activation_strength": "strong", "card_ids": ["card-selftest"], "status": "assessed"}, entity_refs=["event-close-escape-observation"]))
        close_escape_candidate = base_event(event_id="event-close-escape-candidate", engagement_id=closure.name, recorded_at="2026-07-10T00:21:04.330000Z", actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="candidate.proposed", rationale="Leave one valid proposed candidate queued at the closure gate.", payload={"candidate_id": "candidate-close-escape", "source_observation_ref": "event-close-escape-observation", "routing_review_ref": "event-close-escape-routing", "activation_strength": "strong", "card_ids": ["card-selftest"], "status": "queued", "expected_information_gain": 1, "safety_class": "clear_local", "cost_estimate": zero_cost}, entity_refs=["event-close-escape-observation", "event-close-escape-routing"], state_changes=[{"dimension": "search", "entity_id": "candidate-close-escape", "previous": None, "current": "queued"}]); close_escape_candidate["ex_ante"] = {"probability": 0.5, "ordinal": "strong", "recorded_before_outcome": True}; append_event(close_escape, close_escape_candidate)
        close_escape_before = (close_escape / "events.jsonl").read_bytes()
        try:
            close_engagement(close_escape, "operator-selftest", "Attempt to close around blocking work.", "2026-07-10T00:21:05Z")
            close_escape_code = None
        except RecordError as exc:
            close_escape_code = exc.code
        close_escape_state = reduce_engagement(close_escape)
        close_escape_running_item = next((item for item in close_escape_state["work_queue"] if item["class"] == "hypothesis_running_unattempted" and item["entity"]["id"] == "hypothesis-close-escape"), None)
        close_escape_candidate_item = next((item for item in close_escape_state["work_queue"] if item["class"] == "candidate_undisposed" and item["entity"]["id"] == "candidate-close-escape"), None)
        close_escape_actions = {
            "hypothesis-close-escape": decorate_work_queue_item(close_escape_running_item, close_escape_state, close_escape)["next_action"]["action_id"] if close_escape_running_item else None,
            "candidate-close-escape": decorate_work_queue_item(close_escape_candidate_item, close_escape_state, close_escape)["next_action"]["action_id"] if close_escape_candidate_item else None,
        }
        checks.append(("engagement close refuses a real queued-selected-running zero-attempt hypothesis and a still-queued candidate", close_escape_code == "engagement_closure_work_remaining" and (close_escape / "events.jsonl").read_bytes() == close_escape_before and close_escape_running_item is not None and close_escape_candidate_item is not None and close_escape_actions == {"hypothesis-close-escape": "requeue_unattempted_hypothesis", "candidate-close-escape": "select_candidate"}, str((close_escape_code, close_escape_state["work_queue"], close_escape_actions))))

        override_reason = "Operator accepts the exact listed residual work and closes this synthetic fixture on the record."
        override_items = blocking_work_identities(project_current_terminal_work_state(close_escape_state, read_ledger(close_escape, "attempt"), coverage=close_escape_state["coverage"]))
        override_digest = sha256_bytes(canonical_json_bytes(override_items))
        override_session = _local_identity("operator")[1]
        override_payload = {
            "entity_id": closure.name,
            "terminal_kind": "engagement",
            "status": "closed",
            "reason": override_reason,
            "operator_id": "operator-selftest",
            "scope_hash": close_escape_state["scope_hash"],
            "blocking_items": override_items,
            "blocking_queue_digest": override_digest,
            **attempt_ledger_context(read_ledger(close_escape, "attempt")),
            "disposition_ref": close_escape_state["memory_disposition"]["disposition_ref"],
            "disposition_digest": close_escape_state["memory_disposition"]["disposition_digest"],
        }
        override_entity_refs = [close_escape_state["memory_disposition"]["disposition_ref"]]
        override_state_changes = [{
            "dimension": "engagement",
            "entity_id": closure.name,
            "previous": "blocked",
            "current": "closed",
        }]
        override_action = ending_override_action(
            engagement_id=closure.name,
            recorded_at="2026-07-10T00:21:05.500000Z",
            actor={"role": "operator", "id": "operator-selftest"},
            payload=override_payload,
            entity_refs=override_entity_refs,
            evidence_refs=[],
            state_changes=override_state_changes,
            session_id=override_session,
        )
        override_action_digest = sha256_bytes(canonical_json_bytes(override_action))
        override_events = read_ledger(close_escape, "event")
        override_challenge = operator_challenge_bytes(
            engagement_id=closure.name,
            scope_hash=close_escape_state["scope_hash"],
            ledger_hash=override_events[-1]["record_hash"],
            operation=f"override-ending:{override_action_digest}",
            operator_id="operator-selftest",
        )
        override_challenge_path = root / "ending-override-challenge.json"; override_challenge_path.write_bytes(override_challenge)
        override_argv = [sys.executable, str(Path(__file__).resolve()), "override-ending", "--engagement", str(close_escape), "--terminal-kind", "engagement", "--status", "closed", "--operator-id", "operator-selftest", "--session-id", override_session, "--recorded-at", "2026-07-10T00:21:05.500000Z", "--reason", override_reason]
        unsigned_env = {key: value for key, value in os.environ.items() if key not in {"HARNESS_OPERATOR_SIGNATURE_FILE", "HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE"}}
        unsigned_override = subprocess.run(override_argv, env=unsigned_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        subprocess.run(["/usr/bin/ssh-keygen", "-q", "-Y", "sign", "-f", str(reviewer_key), "-n", "llm-redteam-harness-operator-v1", str(override_challenge_path)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        override_env = {**unsigned_env, "HARNESS_OPERATOR_SIGNATURE_FILE": str(override_challenge_path) + ".sig", "HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE": str(allowed_signers_path)}
        signed_override = subprocess.run(override_argv, env=override_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        overridden_state = reduce_engagement(close_escape)
        try:
            unsigned_override_code = json.loads(unsigned_override.stdout)["error"]["code"]
        except (json.JSONDecodeError, KeyError):
            unsigned_override_code = None
        closed_retry_claim = root / "closed-override-retry-claim"; shutil.copytree(close_escape, closed_retry_claim)
        closed_retry_claim.joinpath("operator-note.txt").write_text("The engagement is complete.\n", encoding="utf-8")
        closed_retry_claim_argv = list(override_argv)
        closed_retry_claim_argv[closed_retry_claim_argv.index(str(close_escape))] = str(closed_retry_claim)
        closed_retry_claim_before = (closed_retry_claim / "events.jsonl").read_bytes()
        closed_retry_claim_cli = subprocess.run(closed_retry_claim_argv, env=override_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        try:
            closed_retry_claim_code = json.loads(closed_retry_claim_cli.stdout)["error"]["code"]
        except (json.JSONDecodeError, KeyError):
            closed_retry_claim_code = None
        checks.append(("only an operator-signed first-class override can end with exact blocking identities while non-queue closure gates remain intact", unsigned_override.returncode != 0 and unsigned_override_code == "operator_signature_required" and signed_override.returncode == 0 and overridden_state["ending_overrides"][-1]["blocking_queue_digest"] == override_digest and overridden_state["ending_overrides"][-1]["blocking_items"] == override_items and overridden_state["ending_overrides"][-1]["operator_signature_challenge_digest"] == sha256_bytes(override_challenge) and overridden_state["ending_overrides"][-1]["operator_signer_fingerprint"].startswith("sha256:") and any(item["blocking"] for item in overridden_state["work_queue"]), unsigned_override.stdout + unsigned_override.stderr + signed_override.stdout + signed_override.stderr + str(overridden_state["ending_overrides"])))
        checks.append((
            "exact closed-override retry re-runs the local completion-claim precondition before reporting success",
            closed_retry_claim_cli.returncode != 0
            and closed_retry_claim_code == "completion_claims_unjustified"
            and (closed_retry_claim / "events.jsonl").read_bytes() == closed_retry_claim_before,
            closed_retry_claim_cli.stdout + closed_retry_claim_cli.stderr,
        ))
        closed = close_engagement(closure, "operator-selftest", "Cleanup, blocked coverage, reports, and memory are terminal.", "2026-07-10T00:21:05Z")
        checks.append(("closure requires one operator-reviewed memory disposition and accepts no_novel_lesson", missing_memory_blocked and recorded_memory["disposition"] == "no_novel_lesson" and retry_count + 1 == closed["event_count"] and closed["memory_disposition"]["disposition"] == "no_novel_lesson", str(closed)))
        checks.append(("memory disposition never writes Plane-1", not (closure / "skills").exists() and not (closure / "casebooks").exists(), "record-memory created Plane-1 content"))

        broker_id, broker_session = _local_identity("broker"); now_dt = datetime.now(timezone.utc); now_text = now_dt.isoformat(timespec="seconds").replace("+00:00", "Z"); current_environment = reduce_engagement(engagement)["active_environment_ref"]
        canonical_source = root / "canonical-public-source.txt"; canonical_source.write_text("canonical inert evidence\n"); canonical_artifact_path = engagement / "evidence" / "canonical-public.txt"; canonical_metadata = {"schema_version": 1, "artifact_id": "artifact-canonical-public", "engagement_id": engagement.name, "created_at": now_text, "producer": {"role": "broker", "id": broker_id}, "producer_session_id": broker_session, "operation_class": "notebook", "acquisition_method": "source_inspection", "target_refs": [], "environment_ref": current_environment, "sensitivity": "internal", "redaction_status": "not_needed", "contains_executable_capability": False, "advisory_zone": "clear_local", "escalation_confirmation_event_ref": None, "cleanup_obligation_ref": None, "supersedes_artifact_id": None, "media_type": "text/plain"}; canonical_metadata_path = root / "canonical-artifact-metadata.json"; canonical_metadata_path.write_bytes(canonical_json_bytes(canonical_metadata)); canonical_classification_path = root / "canonical-artifact-classification.json"
        command_classify_artifact(argparse.Namespace(engagement=engagement, metadata=canonical_metadata_path, source=canonical_source, planned_sha256=None, planned_size=None, relative_path=Path("evidence/canonical-public.txt"), recorded_at=now_text, actor_role="broker", actor_id=broker_id, session_id=broker_session, output=canonical_classification_path, model=None, provider=None, tool_version=[])); shutil.copyfile(canonical_source, canonical_artifact_path); command_register_artifact(argparse.Namespace(engagement=engagement, file=canonical_artifact_path, metadata=canonical_metadata_path, classification=canonical_classification_path))
        prior_attempts = {item["attempt_id"]: item for item in read_ledger(engagement, "attempt")}
        canonical_attempt_specs = (("attempt-canonical-primary", "attempt-primary", []), ("attempt-canonical-negative", "attempt-negative", ["attempt-canonical-primary"]), ("attempt-canonical-positive", "attempt-positive", ["attempt-canonical-primary"]), ("attempt-canonical-replay", "attempt-replay", ["attempt-canonical-primary"]))
        for new_id, source_id, controls in canonical_attempt_specs:
            attempt = {key: value for key, value in json.loads(json.dumps(prior_attempts[source_id])).items() if key not in {"sequence", "previous_hash", "record_hash"}}; attempt.update({"attempt_id": new_id, "recorded_at": now_text, "actor": {"role": "broker", "id": broker_id}, "environment_ref": current_environment, "evidence_refs": ["artifact-canonical-public"], "control_of": controls, "operation_class": "notebook"}); attempt["provenance"].update({"actor": {"role": "broker", "id": broker_id}, "session_id": broker_session}); append_attempt(engagement, attempt)
        canonical_review = claim_review("review-canonical-public", now_text, "supported", "F-canonical-public", None, "event-hypothesis-running"); canonical_review["proposed_finding_id"] = "F-canonical-public"; canonical_review["entity_ref"] = "F-canonical-public"; canonical_review["input_refs"] = ["attempt-canonical-primary", "attempt-canonical-negative", "attempt-canonical-positive", "attempt-canonical-replay", current_environment]; canonical_review["evidence_refs"] = ["attempt-canonical-primary", "attempt-canonical-negative", "attempt-canonical-positive", "attempt-canonical-replay", "artifact-canonical-public"]; canonical_review["control_applicability"] = [{"attempt_ref": "attempt-canonical-negative", "applicable": True, "rationale": "Matched negative branch."}, {"attempt_ref": "attempt-canonical-positive", "applicable": True, "rationale": "Known-positive detector check."}, {"attempt_ref": "attempt-canonical-replay", "applicable": True, "rationale": "Fresh-state replay."}]; canonical_review["independence"]["reviewer_id"] = "reviewer-external-canonical"; canonical_review["input_hash"] = compute_review_input_hash(engagement, canonical_review, build_reference_index(engagement)); canonical_review_path = root / "canonical-review.json"; canonical_review_path.write_bytes(canonical_json_bytes(canonical_review))
        canonical_event = base_event(event_id="event-canonical-claim-supported", engagement_id=engagement.name, recorded_at=now_text, actor_role="broker", actor_id=broker_id, event_type="claim.adjudicated", rationale="Record an external independent supported verdict without self-filing.", payload={"entity_id": "F-canonical-public", "status": "supported", "review_ref": canonical_review["review_id"], "reviewer_id": "reviewer-external-canonical", "review_digest": sha256_file(canonical_review_path)}, review_refs=[canonical_review["review_id"]], state_changes=[{"dimension": "claim", "entity_id": "F-canonical-public", "previous": None, "current": "supported"}], session_id=broker_session, operation_class="notebook"); canonical_event_path = root / "canonical-review-event.json"; canonical_event_path.write_bytes(canonical_json_bytes(canonical_event))
        subprocess.run(["/usr/bin/ssh-keygen", "-q", "-Y", "sign", "-f", str(reviewer_key), "-n", "llm-redteam-harness-review-v1", str(canonical_review_path)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); review_signature = Path(str(canonical_review_path) + ".sig")
        review_cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), "record-review", "--engagement", str(engagement), "--file", str(canonical_review_path), "--event", str(canonical_event_path), "--actor-id", broker_id, "--session-id", broker_session, "--signature", str(review_signature), "--allowed-signers", str(allowed_signers_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        if review_cli.returncode != 0: raise RecordError("canonical_review_subprocess_failed", review_cli.stdout + review_cli.stderr)
        forged_event = json.loads(json.dumps(canonical_event)); forged_event["event_id"] = "event-forged-reviewer"; forged_event["payload"]["reviewer_id"] = "forged-reviewer"; forged_path = root / "forged-review-event.json"; forged_path.write_bytes(canonical_json_bytes(forged_event)); forged_reviewer_blocked = False
        forged_cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), "record-review", "--engagement", str(engagement), "--file", str(canonical_review_path), "--event", str(forged_path), "--actor-id", broker_id, "--session-id", broker_session, "--signature", str(review_signature), "--allowed-signers", str(allowed_signers_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        try: forged_reviewer_blocked = forged_cli.returncode != 0 and json.loads(forged_cli.stdout)["error"]["code"] == "canonical_review_binding_invalid"
        except (json.JSONDecodeError, KeyError): forged_reviewer_blocked = False
        # The preceding hermetic subprocess checks can exceed the production authority window on
        # slower hosts. Bind the synthetic filing request to its actual application time instead of
        # reusing the earlier review timestamp.
        now_text = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        canonical_finding = json.loads(json.dumps(finding1)); canonical_finding.update({"finding_id": "F-canonical-public", "revision": 1, "supersedes_revision": None, "recorded_at": now_text, "change_reason": "File the separately adjudicated canonical review.", "claim_state": "supported"}); canonical_finding["adjudication"] = {"review_ref": canonical_review["review_id"], "justification": "Canonical independent review supports the bounded claim."}; canonical_finding["scope_provenance"]["provenance"].update({"actor": {"role": "reviewer", "id": "reviewer-external-canonical"}, "session_id": canonical_review["independence"]["reviewer_session_id"], "model": canonical_review["independence"]["reviewer_model"], "provider": canonical_review.get("provenance", {}).get("provider")}); canonical_finding["scope_provenance"]["environment_ref"] = current_environment
        for claim_name in ("mechanism", "reachability"): canonical_finding["claims"][claim_name]["evidence_refs"] = ["artifact-canonical-public"]
        for impact in canonical_finding["claims"]["impact_claims"]: impact["evidence_refs"] = ["artifact-canonical-public"]
        canonical_finding["proof"].update({"primary_attempt_refs": ["attempt-canonical-primary"], "negative_control_refs": ["attempt-canonical-negative"], "positive_control_refs": ["attempt-canonical-positive"], "replay_refs": ["attempt-canonical-replay"], "evidence_refs": ["artifact-canonical-public"]})
        for mapping in canonical_finding["proof"]["claim_proofs"]: mapping.update({"attempt_refs": ["attempt-canonical-primary"], "artifact_refs": ["artifact-canonical-public"], "control_refs": ["attempt-canonical-negative", "attempt-canonical-positive"], "replay_refs": ["attempt-canonical-replay"]})
        canonical_finding_path = root / "canonical-finding.json"; canonical_finding_path.write_bytes(canonical_json_bytes(canonical_finding)); finding_digest = sha256_file(canonical_finding_path)

        v2_source = root / "v2-finding-source"; shutil.copytree(engagement, v2_source)
        def prepare_v2_request(target_engagement: Path, request_name: str, proposal: dict[str, Any], request_time: str, *, action_executor: str | None = None, request_environment: object = ..., expires_at: str | None = "2099-07-10T00:00:00Z") -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
            request_state = reduce_engagement(target_engagement); metadata = request_state["claim_adjudications"][proposal["finding_id"]]; proposal_digest = sha256_bytes(canonical_json_bytes(proposal))
            target_value = {"type": "finding", "id": proposal["finding_id"], "expected_revision": metadata["expected_filing_revision"], "claim_state": metadata["status"], "adjudication_event_ref": metadata["event_ref"], "adjudication_review_ref": metadata["review_ref"], "resolves_review_refs": [], "file_digest": proposal_digest}
            action_value = _authority_action("revise-finding", action_version=2, lane_id=finding_revision_lane_id(target_value), executor_id=action_executor or broker_id, session_id=broker_session, file_digest=proposal_digest, operator_id="operator-selftest", proposal=proposal, target=target_value)
            relative = f"authority/requests/{request_name}.action.json"; atomic_write(target_engagement / relative, canonical_json_bytes(action_value)); action_value_digest = sha256_bytes(canonical_json_bytes(action_value))
            environment_value = request_state["active_environment_ref"] if request_environment is ... else request_environment
            request_event = base_event(event_id=f"event-{request_name}", engagement_id=request_state["engagement_id"], recorded_at=request_time, actor_role="broker", actor_id=broker_id, event_type="authority.requested", rationale="Request one fully bound v2 finding revision.", payload={"request_id": request_name, "action_kind": "revise-finding", "action_digest": action_value_digest, "action_path": relative, "lane_id": action_value["lane_id"], "request_status": "pending_authority", "scope_hash": request_state["scope_hash"], "environment_ref": environment_value, "expires_at": expires_at}, session_id=broker_session, operation_class="notebook")
            return action_value, target_value, request_event

        v2_clock = datetime.now(timezone.utc); v2_request_time = v2_clock.isoformat(timespec="seconds").replace("+00:00", "Z"); v2_resolution_time = (v2_clock + timedelta(seconds=1)).isoformat(timespec="seconds").replace("+00:00", "Z"); v2_apply_time = (v2_clock + timedelta(seconds=2)).isoformat(timespec="seconds").replace("+00:00", "Z")
        v2_valid = root / "v2-finding-valid"; shutil.copytree(v2_source, v2_valid); v2_action, v2_target, v2_request_event = prepare_v2_request(v2_valid, "request-v2-finding", canonical_finding, v2_request_time, expires_at=None); append_event(v2_valid, v2_request_event); v2_pending_state = reduce_engagement(v2_valid)
        v2_pending_classes = [(item["class"], item["entity"]["id"]) for item in v2_pending_state["work_queue"]]
        v2_digest = sha256_bytes(canonical_json_bytes(v2_action)); append_event(v2_valid, base_event(event_id="event-resolution-v2-finding", engagement_id=v2_pending_state["engagement_id"], recorded_at=v2_resolution_time, actor_role="operator", actor_id="operator-selftest", event_type="authority.resolved", rationale="Approve the exact v2 proposal after its request time.", payload={"request_id": "request-v2-finding", "request_event_ref": v2_request_event["event_id"], "action_digest": v2_digest, "resolution": "approved", "resolved_at": v2_resolution_time}, entity_refs=[v2_request_event["event_id"]], session_id=broker_session, operation_class="authority"))
        v2_partial_path = v2_valid / "findings/F-canonical-public/rev-1.json"; atomic_write(v2_partial_path, canonical_json_bytes(canonical_finding)); append_event(v2_valid, base_event(event_id="event-F-canonical-public-r1-commit", engagement_id=v2_pending_state["engagement_id"], recorded_at=v2_apply_time, actor_role="broker", actor_id=broker_id, event_type="record.committed", rationale="Simulate a same-digest v2 crash after commit but before activation.", payload={"record_path": "findings/F-canonical-public/rev-1.json", "record_digest": v2_target["file_digest"], "record_type": "finding-v3", "record_id": "F-canonical-public", "record_revision": 1, "authority_request_ref": "request-v2-finding"}, session_id=broker_session, operation_class="authority"))
        command_settle_approved_revision(argparse.Namespace(engagement=v2_valid, file=canonical_finding_path, resolve_review=None, operator_id="operator-selftest", recorded_at=v2_apply_time, authority_request_id="request-v2-finding", lane_id=v2_action["lane_id"], executor_id=broker_id, session_id=broker_session)); v2_applied_state = reduce_engagement(v2_valid); v2_applied_event = read_ledger(v2_valid, "event")[-1]
        checks.append(("atomic settlement applies a live nullable-expiry v2 target, resumes a same-digest partial commit, and propagates exact resolutions", v2_pending_state["authority_requests"]["request-v2-finding"]["target"] == v2_target and v2_pending_state["authority_requests"]["request-v2-finding"]["expires_at"] is None and ("finding_revision_pending", "F-canonical-public") not in v2_pending_classes and ("claim_unadjudicated", "F-canonical-public") in v2_pending_classes and ("awaiting_operator", "request-v2-finding") in v2_pending_classes and v2_applied_state["findings"]["F-canonical-public"]["adjudication_event_ref"] == v2_target["adjudication_event_ref"] and v2_applied_event["payload"].get("resolves_review_refs") == [], str({"pending": v2_pending_classes, "finding": v2_applied_state["findings"].get("F-canonical-public")})))

        expiry_deadline_dt = v2_clock + timedelta(seconds=3)
        expiry_deadline = expiry_deadline_dt.isoformat(timespec="seconds").replace("+00:00", "Z")
        expiry_settlement_dt = v2_clock + timedelta(seconds=120)
        expiry_settlement_time = expiry_settlement_dt.isoformat(timespec="seconds").replace("+00:00", "Z")
        v2_expired = root / "v2-finding-expired"; shutil.copytree(v2_source, v2_expired)
        expiry_action, _, expiry_request = prepare_v2_request(v2_expired, "request-v2-expired", canonical_finding, v2_request_time, expires_at=expiry_deadline)
        append_event(v2_expired, expiry_request)
        append_event(v2_expired, base_event(event_id="event-resolution-v2-expired", engagement_id=reduce_engagement(v2_expired)["engagement_id"], recorded_at=v2_resolution_time, actor_role="operator", actor_id="operator-selftest", event_type="authority.resolved", rationale="Approve the exact revision until its objective deadline.", payload={"request_id": "request-v2-expired", "request_event_ref": expiry_request["event_id"], "action_digest": sha256_bytes(canonical_json_bytes(expiry_action)), "resolution": "approved", "resolved_at": v2_resolution_time}, entity_refs=[expiry_request["event_id"]], session_id=broker_session, operation_class="authority"))
        early_expiry_event = base_event(event_id="event-authority-expired-request-v2-expired-early", engagement_id=reduce_engagement(v2_expired)["engagement_id"], recorded_at=v2_apply_time, actor_role="broker", actor_id=broker_id, event_type="authority.expired", rationale="An approval cannot expire before its recorded deadline.", payload={"request_id": "request-v2-expired", "request_event_ref": expiry_request["event_id"], "action_digest": sha256_bytes(canonical_json_bytes(expiry_action)), "expires_at": expiry_deadline, "status": "expired"}, entity_refs=[expiry_request["event_id"]], session_id=broker_session, operation_class="notebook")
        try:
            _append_kernel_event(v2_expired, early_expiry_event)
            early_expiry_code = None
        except RecordError as exc:
            early_expiry_code = exc.code

        class _ExpiredSettlementClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return expiry_settlement_dt

        expired_args = argparse.Namespace(engagement=v2_expired, file=canonical_finding_path, resolve_review=None, operator_id="operator-selftest", recorded_at=expiry_settlement_time, authority_request_id="request-v2-expired", lane_id=expiry_action["lane_id"], executor_id=broker_id, session_id=broker_session)
        with patch(f"{__name__}.datetime", _ExpiredSettlementClock), patch(f"{__name__}.emit"):
            stale_settlement_code = None
            try:
                command_settle_approved_revision(argparse.Namespace(**{**vars(expired_args), "recorded_at": v2_apply_time}))
            except RecordError as exc:
                stale_settlement_code = exc.code
            before_expiry_events = len(read_ledger(v2_expired, "event"))
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=2) as executor:
                settlement_results = list(executor.map(lambda _: command_settle_approved_revision(expired_args), range(2)))
        expired_state = reduce_engagement(v2_expired)
        expiry_events = [event for event in read_ledger(v2_expired, "event") if event["event_type"] == "authority.expired" and event["payload"].get("request_id") == "request-v2-expired"]
        expired_revision_item = next(item for item in expired_state["work_queue"] if item["class"] == "finding_revision_pending" and item["entity"]["id"] == "F-canonical-public")
        after_expiry_action = decorate_work_queue_item(expired_revision_item, expired_state, v2_expired)["next_action"]
        checks.append(("atomic settlement rejects early and stale-time expiry, serializes concurrent retries to one event, writes no finding bytes, and reopens a new request action", early_expiry_code == "approved_authority_expiry_invalid" and stale_settlement_code == "authority_settlement_time_not_current" and settlement_results == [0, 0] and len(expiry_events) == 1 and len(read_ledger(v2_expired, "event")) == before_expiry_events + 1 and expired_state["authority_requests"]["request-v2-expired"]["status"] == "expired" and not (v2_expired / "findings/F-canonical-public/rev-1.json").exists() and after_expiry_action["action_id"] == "request_finding_revision_authority", str({"early": early_expiry_code, "stale": stale_settlement_code, "results": settlement_results, "events": expiry_events, "next": after_expiry_action})))

        v2_duplicate = root / "v2-finding-duplicate"; shutil.copytree(v2_source, v2_duplicate); duplicate_first_action, _, duplicate_first_event = prepare_v2_request(v2_duplicate, "request-v2-first", canonical_finding, v2_request_time); append_event(v2_duplicate, duplicate_first_event); changed_proposal = copy.deepcopy(canonical_finding); changed_proposal["change_reason"] = "A different digest cannot open the same active generation."; _, _, duplicate_second_event = prepare_v2_request(v2_duplicate, "request-v2-second", changed_proposal, v2_request_time); duplicate_replay_blocked = False
        try: append_event(v2_duplicate, duplicate_second_event)
        except RecordError as exc: duplicate_replay_blocked = exc.code == "duplicate_active_finding_revision_request"
        checks.append(("reducer replay rejects a second active v2 request for the same generation even with a different proposal digest", duplicate_replay_blocked, "duplicate active generation reduced"))

        def rejected_v2_case(name: str, proposal: dict[str, Any], *, action_executor: str | None = None, request_environment: object = ...) -> str | None:
            case_engagement = root / name; shutil.copytree(v2_source, case_engagement); _, _, request_event = prepare_v2_request(case_engagement, f"request-{name}", proposal, v2_request_time, action_executor=action_executor, request_environment=request_environment)
            try: append_event(case_engagement, request_event)
            except RecordError as exc: return exc.code
            return None
        future_proposal = copy.deepcopy(canonical_finding); future_proposal["recorded_at"] = (v2_clock + timedelta(seconds=10)).isoformat(timespec="seconds").replace("+00:00", "Z")
        early_proposal = copy.deepcopy(canonical_finding); early_proposal["recorded_at"] = "2026-07-10T00:00:00Z"
        principal_code = rejected_v2_case("v2-impossible-principal", canonical_finding, action_executor="broker-impossible")
        environment_code = rejected_v2_case("v2-null-environment", canonical_finding, request_environment=None)
        future_code = rejected_v2_case("v2-future-proposal", future_proposal)
        temporal_code = rejected_v2_case("v2-early-proposal", early_proposal)
        checks.append(("v2 admission rejects impossible principals, non-current environment, future proposals, and pre-reference chronology", principal_code == "revise_finding_v2_principal_binding_invalid" and environment_code == "revise_finding_v2_principal_binding_invalid" and future_code == "revise_finding_v2_proposal_from_future" and temporal_code == "revise_finding_v2_reference_from_future", str({"principal": principal_code, "environment": environment_code, "future": future_code, "temporal": temporal_code})))

        unsafe_path_codes: list[str | None] = []
        for unsafe_name, make_unsafe in (("v2-symlink-parent", lambda path: os.symlink("../reviews", path / "findings/F-canonical-public")), ("v2-directory-leaf", lambda path: (path / "findings/F-canonical-public/rev-1.json").mkdir(parents=True))):
            unsafe_engagement = root / unsafe_name; shutil.copytree(v2_source, unsafe_engagement); _, _, unsafe_request = prepare_v2_request(unsafe_engagement, f"request-{unsafe_name}", canonical_finding, v2_request_time); make_unsafe(unsafe_engagement); unsafe_code = None
            try: append_event(unsafe_engagement, unsafe_request)
            except (OSError, RecordError) as exc: unsafe_code = exc.code if isinstance(exc, RecordError) else "os_error"
            unsafe_path_codes.append(unsafe_code)
        checks.append(("v2 admission rejects symlinked parents and non-regular destination leaves before projecting target debt", all(code is not None for code in unsafe_path_codes), str(unsafe_path_codes)))

        v2_locked = root / "v2-finding-locked-recheck"; shutil.copytree(v2_source, v2_locked); locked_action, _, locked_request = prepare_v2_request(v2_locked, "request-v2-locked", canonical_finding, v2_request_time); append_event(v2_locked, locked_request); locked_before_events = len(read_ledger(v2_locked, "event")); locked_blocked = False
        try:
            with patch(f"{__name__}._require_async_authority", return_value=None): command_revise_finding(argparse.Namespace(engagement=v2_locked, file=canonical_finding_path, resolve_review=None, operator_id="operator-selftest", recorded_at=v2_apply_time, authority_request_id="request-v2-locked", lane_id=locked_action["lane_id"], executor_id=broker_id, session_id=broker_session))
        except RecordError as exc: locked_blocked = exc.code == "approved_authority_request_required"
        checks.append(("revise-finding revalidates approved authority under the held lock before any destination write", locked_blocked and not (v2_locked / "findings/F-canonical-public/rev-1.json").exists() and len(read_ledger(v2_locked, "event")) == locked_before_events, "stale authority wrote or committed a revision"))

        v2_wrong_operator = root / "v2-finding-wrong-operator"; shutil.copytree(v2_source, v2_wrong_operator); wrong_operator_action, _, wrong_operator_request = prepare_v2_request(v2_wrong_operator, "request-v2-wrong-operator", canonical_finding, v2_request_time); append_event(v2_wrong_operator, wrong_operator_request); append_event(v2_wrong_operator, base_event(event_id="event-resolution-v2-wrong-operator", engagement_id=reduce_engagement(v2_wrong_operator)["engagement_id"], recorded_at=v2_resolution_time, actor_role="operator", actor_id="operator-selftest", event_type="authority.resolved", rationale="Approve the exact v2 proposal for principal binding testing.", payload={"request_id": "request-v2-wrong-operator", "request_event_ref": wrong_operator_request["event_id"], "action_digest": sha256_bytes(canonical_json_bytes(wrong_operator_action)), "resolution": "approved", "resolved_at": v2_resolution_time}, entity_refs=[wrong_operator_request["event_id"]], session_id=broker_session, operation_class="authority")); wrong_operator_before = len(read_ledger(v2_wrong_operator, "event")); wrong_operator_blocked = False
        try:
            with patch(f"{__name__}._require_async_authority", return_value=None): command_revise_finding(argparse.Namespace(engagement=v2_wrong_operator, file=canonical_finding_path, resolve_review=None, operator_id="operator-impossible", recorded_at=v2_apply_time, authority_request_id="request-v2-wrong-operator", lane_id=wrong_operator_action["lane_id"], executor_id=broker_id, session_id=broker_session))
        except RecordError as exc: wrong_operator_blocked = exc.code in {"approved_authority_request_required", "approved_revision_action_record_invalid"}
        checks.append(("revise-finding binds the active signed-scope operator under lock before mutation", wrong_operator_blocked and not (v2_wrong_operator / "findings/F-canonical-public/rev-1.json").exists() and len(read_ledger(v2_wrong_operator, "event")) == wrong_operator_before, "wrong operator wrote or committed a revision"))

        v2_conflict = root / "v2-finding-conflict"; shutil.copytree(v2_source, v2_conflict); conflicting_finding = copy.deepcopy(canonical_finding); conflicting_finding["change_reason"] = "Pre-existing unactivated bytes conflict with the requested proposal."; conflicting_path = v2_conflict / "findings/F-canonical-public/rev-1.json"; atomic_write(conflicting_path, canonical_json_bytes(conflicting_finding)); conflict_state = reduce_engagement(v2_conflict, allowed_record_orphans={"findings/F-canonical-public/rev-1.json"}); append_event(v2_conflict, base_event(event_id="event-v2-conflicting-commit", engagement_id=conflict_state["engagement_id"], recorded_at=v2_request_time, actor_role="broker", actor_id=broker_id, event_type="record.committed", rationale="Commit an unactivated conflicting revision for admission testing.", payload={"record_path": "findings/F-canonical-public/rev-1.json", "record_digest": sha256_bytes(canonical_json_bytes(conflicting_finding)), "record_type": "finding-v3", "record_id": "F-canonical-public", "record_revision": 1}, session_id=broker_session, operation_class="authority")); _, _, conflict_request = prepare_v2_request(v2_conflict, "request-v2-conflict", canonical_finding, v2_request_time); conflict_code = None
        try: append_event(v2_conflict, conflict_request)
        except RecordError as exc: conflict_code = exc.code
        checks.append(("v2 admission rejects a conflicting unactivated expected revision", conflict_code == "revise_finding_v2_conflicting_unactivated_revision", str(conflict_code)))

        legacy_null = root / "legacy-finding-null-authority-fields"; shutil.copytree(v2_source, legacy_null); legacy_apply_time = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"); legacy_lane = "lane-legacy-null-fields"; legacy_action = _authority_action("revise-finding", lane_id=legacy_lane, executor_id=broker_id, session_id=broker_session, file_digest=finding_digest, operator_id="operator-selftest", recorded_at=legacy_apply_time); legacy_action_digest = sha256_bytes(canonical_json_bytes(legacy_action)); legacy_state = reduce_engagement(legacy_null); legacy_request_id = "request-legacy-null-fields"
        append_event(legacy_null, base_event(event_id="event-request-legacy-null-fields", engagement_id=legacy_state["engagement_id"], recorded_at=legacy_apply_time, actor_role="orchestrator", actor_id="orchestrator-selftest", event_type="authority.requested", rationale="Exercise the pre-v2 nullable authority fields.", payload={"request_id": legacy_request_id, "action_kind": "revise-finding", "action_digest": legacy_action_digest, "lane_id": legacy_lane, "request_status": "pending_authority", "scope_hash": legacy_state["scope_hash"], "environment_ref": None, "expires_at": None}, session_id="session-legacy-null-fields", operation_class="notebook")); append_event(legacy_null, base_event(event_id="event-resolution-legacy-null-fields", engagement_id=legacy_state["engagement_id"], recorded_at=legacy_apply_time, actor_role="operator", actor_id="operator-selftest", event_type="authority.resolved", rationale="Approve the exact legacy finding action.", payload={"request_id": legacy_request_id, "request_event_ref": "event-request-legacy-null-fields", "action_digest": legacy_action_digest, "resolution": "approved", "resolved_at": legacy_apply_time}, entity_refs=["event-request-legacy-null-fields"], session_id=broker_session, operation_class="authority")); command_revise_finding(argparse.Namespace(engagement=legacy_null, file=canonical_finding_path, resolve_review=None, operator_id="operator-selftest", recorded_at=legacy_apply_time, authority_request_id=legacy_request_id, lane_id=legacy_lane, executor_id=broker_id, session_id=broker_session)); legacy_null_state = reduce_engagement(legacy_null)
        checks.append(("legacy target-null revise authority retains nullable action path, environment, and expiry compatibility", legacy_null_state["authority_requests"][legacy_request_id]["target"] is None and legacy_null_state["findings"]["F-canonical-public"]["revision"] == 1, str(legacy_null_state["authority_requests"][legacy_request_id])))

        now_text = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        action = _authority_action("revise-finding", lane_id="lane-canonical-finding", executor_id=broker_id, session_id=broker_session, file_digest=finding_digest, operator_id="operator-selftest", recorded_at=now_text); action_digest = sha256_bytes(canonical_json_bytes(action)); canonical_action_relative = "authority/requests/request-canonical-finding.action.json"; atomic_write(engagement / canonical_action_relative, canonical_json_bytes(action)); scope_hash = reduce_engagement(engagement)["scope_hash"]; request_id = "request-canonical-finding"
        append_event(engagement, base_event(event_id="event-request-canonical-finding", engagement_id=engagement.name, recorded_at=now_text, actor_role="broker", actor_id=broker_id, event_type="authority.requested", rationale="Request filing of one exact separately adjudicated revision.", payload={"request_id": request_id, "action_kind": "revise-finding", "action_digest": action_digest, "action_path": canonical_action_relative, "lane_id": "lane-canonical-finding", "request_status": "pending_authority", "scope_hash": scope_hash, "environment_ref": reduce_engagement(engagement)["active_environment_ref"], "expires_at": None}, session_id=broker_session, operation_class="notebook"))
        append_event(engagement, base_event(event_id="event-resolution-canonical-finding", engagement_id=engagement.name, recorded_at=now_text, actor_role="operator", actor_id="operator-selftest", event_type="authority.resolved", rationale="Approve only the digest-bound canonical revision.", payload={"request_id": request_id, "request_event_ref": "event-request-canonical-finding", "action_digest": action_digest, "resolution": "approved", "resolved_at": now_text}, entity_refs=["event-request-canonical-finding"], session_id=broker_session, operation_class="authority"))
        partial_destination = engagement / "findings/F-canonical-public/rev-1.json"; atomic_write(partial_destination, canonical_json_bytes(canonical_finding)); partial_commit = base_event(event_id="event-F-canonical-public-r1-commit", engagement_id=engagement.name, recorded_at=now_text, actor_role="broker", actor_id=broker_id, event_type="record.committed", rationale="Commit immutable operator-authorized finding revision.", payload={"record_path": "findings/F-canonical-public/rev-1.json", "record_digest": finding_digest, "record_type": "finding-v3", "record_id": "F-canonical-public", "record_revision": 1, "authority_request_ref": request_id}, session_id=broker_session, operation_class="authority"); append_event(engagement, partial_commit)
        revise_cli = subprocess.run([sys.executable, str(Path(__file__).resolve()), "revise-finding", "--engagement", str(engagement), "--file", str(canonical_finding_path), "--operator-id", "operator-selftest", "--recorded-at", now_text, "--authority-request-id", request_id, "--lane-id", "lane-canonical-finding", "--executor-id", broker_id, "--session-id", broker_session], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        if revise_cli.returncode != 0: raise RecordError("canonical_finding_subprocess_failed", revise_cli.stdout + revise_cli.stderr)
        canonical_state = reduce_engagement(engagement)
        checks.append(("canonical public review and finding revision preserve reviewer, broker, adjudication, and filing separation", forged_reviewer_blocked and canonical_state["findings"]["F-canonical-public"]["revision"] == 1 and canonical_state["findings"]["F-canonical-public"]["status"] == "supported" and read_ledger(engagement, "event")[-1]["actor"] == {"role": "broker", "id": broker_id}, str(canonical_state["findings"].get("F-canonical-public"))))
        def approve_action(request_name: str, lane: str, action_value: dict[str, Any]) -> None:
            relative = f"authority/requests/{request_name}.action.json"; atomic_write(engagement/relative, canonical_json_bytes(action_value)); digest = sha256_bytes(canonical_json_bytes(action_value)); current_state = reduce_engagement(engagement)
            append_event(engagement, base_event(event_id=f"event-request-{request_name}", engagement_id=engagement.name, recorded_at=now_text, actor_role="broker", actor_id=broker_id, event_type="authority.requested", rationale="Exercise an exact canonical authority path.", payload={"request_id": request_name, "action_kind": action_value["action_kind"], "action_digest": digest, "action_path": relative, "lane_id": lane, "request_status": "pending_authority", "scope_hash": current_state["scope_hash"], "environment_ref": current_state["active_environment_ref"], "expires_at": "2099-07-10T00:00:00Z"}, session_id=broker_session, operation_class="notebook")); append_event(engagement, base_event(event_id=f"event-resolution-{request_name}", engagement_id=engagement.name, recorded_at=now_text, actor_role="operator", actor_id="operator-selftest", event_type="authority.resolved", rationale="Approve exact synthetic transition.", payload={"request_id": request_name, "request_event_ref": f"event-request-{request_name}", "action_digest": digest, "resolution": "approved", "resolved_at": now_text}, entity_refs=[f"event-request-{request_name}"], session_id=broker_session, operation_class="authority"))
        now_text = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"); prior_action = _authority_action("record-operator-prior", lane_id="lane-prior-public", executor_id=broker_id, session_id=broker_session, operator_id="operator-selftest", recorded_at=now_text, prior_id="prior-public", prior_statement="Synthetic operator direction, not claim evidence.", strength="weak", reason="Exercise canonical prior authority."); approve_action("request-prior-public", "lane-prior-public", prior_action); command_record_operator_prior(argparse.Namespace(engagement=engagement, prior_id="prior-public", prior_statement="Synthetic operator direction, not claim evidence.", strength="weak", operator_id="operator-selftest", recorded_at=now_text, reason="Exercise canonical prior authority.", authority_request_id="request-prior-public", lane_id="lane-prior-public", executor_id=broker_id, session_id=broker_session))
        now_text = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"); cleanup_proposal = {"entity_id": "cleanup-public", "status": "not_applicable", "cleanup_obligations": [{"obligation_id": "cleanup-public", "kind": "synthetic_local", "status": "not_applicable", "artifact_refs": [], "rationale": "No live effect exists.", "closed_at": now_text}]}; cleanup_path = root/"cleanup-public.json"; cleanup_path.write_bytes(canonical_json_bytes(cleanup_proposal)); cleanup_action = _authority_action("record-cleanup", lane_id="lane-cleanup-public", executor_id=broker_id, session_id=broker_session, operator_id="operator-selftest", recorded_at=now_text, reason="Exercise canonical cleanup authority.", **cleanup_proposal); approve_action("request-cleanup-public", "lane-cleanup-public", cleanup_action); command_record_cleanup(argparse.Namespace(engagement=engagement, file=cleanup_path, operator_id="operator-selftest", recorded_at=now_text, reason="Exercise canonical cleanup authority.", authority_request_id="request-cleanup-public", lane_id="lane-cleanup-public", executor_id=broker_id, session_id=broker_session))
        public_state = reduce_engagement(engagement); reopened = True; operator_reopen_record = None
        if public_state["active_blockers"]:
            now_text = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"); reopen_action = _authority_action("reopen", lane_id="lane-reopen-public", executor_id=broker_id, session_id=broker_session, operator_id="operator-selftest", recorded_at=now_text, reason="Exercise canonical reopening authority."); approve_action("request-reopen-public", "lane-reopen-public", reopen_action); command_reopen(argparse.Namespace(engagement=engagement, operator_id="operator-selftest", recorded_at=now_text, reason="Exercise canonical reopening authority.", authority_request_id="request-reopen-public", lane_id="lane-reopen-public", executor_id=broker_id, session_id=broker_session)); reopened = not reduce_engagement(engagement)["active_blockers"]; operator_reopen_record = read_ledger(engagement, "event")[-1]
        checks.append(("canonical public prior, cleanup, and reopening transitions use exact one-use async authority", public_state["authority_requests"]["request-prior-public"]["status"] == "approved" and public_state["authority_requests"]["request-cleanup-public"]["status"] == "approved" and any(item["prior_id"] == "prior-public" for item in public_state["operator_priors"]) and any(item["obligation_id"] == "cleanup-public" for item in public_state["cleanup"]["obligations"]) and reopened and operator_reopen_record is not None and operator_reopen_record["event_type"] == "engagement.reopened" and operator_reopen_record["payload"]["operator_id"] == "operator-selftest" and operator_reopen_record["operation_class"] == "authority", "public authority transition missing"))
    return checks


def self_test() -> int:
    checks: list[tuple[str, bool, str]] = []

    schema_problems = validate_schema_documents()
    checks.append(("new Draft 2020-12 schemas pass metaschema and local-ref validation", not schema_problems, str(schema_problems)))

    suite = validate_fixture_suite()
    checks.append(("valid/invalid fixture suite uses the canonical validator", not suite["failures"], str(suite["failures"])))
    reference_suite = validate_reference_fixture_suite()
    checks.append(("missing/wrong-type/cross-engagement/stale references fail", not reference_suite["failures"], str(reference_suite["failures"])))
    finding_case = next(case["record"] for case in load_json(Path(__file__).resolve().parents[1] / "fixtures" / "engagement-records" / "suite.json")["cases"] if case["id"] == "finding-v3-minimum")
    dispatch_ok = resolve_schema_name(finding_case) == "finding-v3"
    mismatch_caught = False
    try:
        resolve_schema_name(finding_case, "attempt-v2")
    except RecordError as exc:
        mismatch_caught = exc.code == "schema_dispatch_mismatch"
    checks.append(("record identity/version dispatch is authoritative", dispatch_ok and mismatch_caught, "caller-selected schema overrode dispatch"))
    ids = {case["id"] for case in suite["results"] if case["passed"]}
    for required in ("finding-v3-unknown-property", "finding-v3-duplicate-claim-id", "finding-v3-incomplete-claim-proof-map", "finding-v3-required-positive-control-missing", "finding-v3-empty-per-claim-proof", "finding-v3-positive-control-not-bound-per-claim", "attempt-v2-confirmed-outcome", "artifact-missing-conditional", "review-missing-conditional", "engagement-event-unknown-type", "state-snapshot-unknown-property", "environment-preflight-unknown-property", "report-manifest-unknown-property", "memory-disposition-unknown-property", "migration-manifest-unknown-property", "research-telemetry-unknown-property"):
        checks.append((f"negative fixture rejected: {required}", required in ids, "missing/failed fixture"))

    telemetry_fixture = load_json(Path(__file__).resolve().parents[1] / "fixtures" / "engagement-records" / "suite.json")
    calibration_record = json.loads(json.dumps(next(case["record"] for case in telemetry_fixture["cases"] if case["id"] == "research-telemetry-rich")))
    template_row = calibration_record["candidates"][0]; calibration_record["candidates"] = []
    for index_number in range(30):
        row = json.loads(json.dumps(template_row)); row["candidate_id"] = f"candidate-{index_number:02d}"; row["funnel_history"][0]["source_ref"] = f"event-eligible-{index_number:02d}"; row["funnel_history"][1]["source_ref"] = f"event-selected-{index_number:02d}"; row["funnel_history"][2]["source_ref"] = f"review-outcome-{index_number:02d}"; row["outcome"]["review_ref"] = f"review-outcome-{index_number:02d}"; row["review_refs"] = [row["outcome"]["review_ref"]]; calibration_record["candidates"].append(row)
    calibration_record["denominator"] = {"eligible_count": 30, "exported_count": 30, "complete": True}; calibration_record["classification"] = "calibration"; calibration_record["calibration_eligibility"] = {"eligible": True, "reasons": []}; calibration_score = score_telemetry(calibration_record)
    checks.append(("eligible ex-ante probabilities produce offline Brier and reliability telemetry only", calibration_score["brier_score"] == 0.0625 and calibration_score["small_sample"] is False and calibration_score["automatic_actions"] == [] and calibration_score["bandit_enabled"] is False, str(calibration_score)))

    canonical = canonical_json_bytes({"b": 2, "a": 1})
    checks.append(("canonical JSON is sorted and newline terminated", canonical == b'{"a":1,"b":2}\n', repr(canonical)))

    with tempfile.TemporaryDirectory(prefix="engagement-record-selftest-") as tmp:
        duplicate = Path(tmp) / "duplicate.json"
        duplicate.write_text('{"a":1,"a":2}\n', encoding="utf-8")
        caught = False
        try:
            load_json(duplicate)
        except RecordError as exc:
            caught = exc.code == "duplicate_json_key"
        checks.append(("duplicate JSON keys fail closed", caught, "duplicate key accepted"))

    # A record schema whose only property points at an unregistered URI must not degrade to success.
    broken = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "https://example.invalid/broken", "$ref": "https://example.invalid/missing"}
    broken_failed = False
    try:
        from jsonschema import Draft202012Validator
        list(Draft202012Validator(broken, registry=build_registry()).iter_errors({}))
    except Exception:
        broken_failed = True
    checks.append(("unresolved schema references fail closed", broken_failed, "missing $ref accepted"))

    duplicate_id_failed = False
    duplicate_schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "https://example.invalid/duplicate", "type": "object"}
    try:
        build_registry({"one.schema.json": duplicate_schema, "two.schema.json": duplicate_schema})
    except RecordError as exc:
        duplicate_id_failed = exc.code == "duplicate_schema_id"
    checks.append(("duplicate schema IDs fail closed", duplicate_id_failed, "duplicate $id accepted"))

    unavailable = subprocess.run(
        [sys.executable, "-S", str(Path(__file__).resolve()), "validate", "--schema-documents"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False,
    )
    try:
        unavailable_payload = json.loads(unavailable.stdout)
        unavailable_ok = unavailable.returncode != 0 and unavailable_payload.get("error", {}).get("code") == "validator_unavailable"
    except json.JSONDecodeError:
        unavailable_ok = False
    checks.append(("missing validator emits structured fail-closed output", unavailable_ok, unavailable.stdout + unavailable.stderr))
    checks.extend(state_self_test())
    quarantine_test = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("quarantine-self-test.py"))],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    checks.append((
        "quarantine health, mutation, measurement, KB, and dynamic casebook exclusions fail closed",
        quarantine_test.returncode == 0
        and "QUARANTINE SELF-TEST: PASS" in quarantine_test.stdout,
        quarantine_test.stdout + quarantine_test.stderr,
    ))

    for label, ok, detail in checks:
        print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" :: {detail}"))
    failed = [label for label, ok, _ in checks if not ok]
    print(f"RUN-ENGAGEMENT SELF-TEST: {'PASS' if not failed else 'FAIL'}")
    return 0 if not failed else 1


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
