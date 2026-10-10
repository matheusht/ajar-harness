#!/usr/bin/env python3
"""Resolve a registered corpus freeze into a trustworthy coverage denominator.

The corpus enumerator deliberately writes offline files.  A terminal coverage event may use those
files only after both the freeze manifest and its TSV have entered the engagement artifact ledger.
This module binds the manifest bytes, TSV bytes, artifact records, and event time without rerunning
the package parser or trusting a caller-supplied count.
"""

from __future__ import annotations

import json
import os
import posixpath
import re
import stat
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from corpus_enumeration import EnumerationError, _read_artifact
from engagement_records import RecordError, sha256_bytes, validate_record


def _scope_frozen_manifest_pin(scope_bytes: bytes) -> str:
    """Extract the one operator-signed corpus-manifest pin, or fail closed."""

    if not isinstance(scope_bytes, bytes):
        raise RecordError("frozen_corpus_scope_invalid", "signed scope bytes are required")
    try:
        text = scope_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RecordError("frozen_corpus_scope_invalid", "signed scope is not UTF-8") from exc

    signed_markers = re.findall(r"^- Signed:\s*\[[xX]\]\s*$", text, re.MULTILINE)
    if len(signed_markers) != 1:
        raise RecordError(
            "frozen_corpus_scope_unsigned",
            "scope must contain exactly one checked Signed marker",
        )

    pins = re.findall(
        r"^- Frozen corpus enumeration SHA256: `(none|sha256:[0-9a-f]{64})`[ \t]*$",
        text,
        re.MULTILINE,
    )
    if not pins:
        raise RecordError(
            "frozen_corpus_scope_pin_missing",
            "signed scope has no exact Frozen corpus enumeration SHA256 pin",
        )
    if len(pins) != 1:
        raise RecordError(
            "frozen_corpus_scope_pin_ambiguous",
            "signed scope must contain one Frozen corpus enumeration SHA256 pin",
        )
    if pins[0] == "none":
        raise RecordError(
            "frozen_corpus_scope_pin_none",
            "signed scope does not authorize a frozen corpus manifest",
        )
    return pins[0]


def _timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise RecordError("frozen_corpus_time_invalid", field)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RecordError("frozen_corpus_time_invalid", field) from exc
    if parsed.tzinfo is None:
        raise RecordError("frozen_corpus_time_invalid", field)
    return parsed.astimezone(timezone.utc)


def _as_of(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise RecordError("frozen_corpus_time_invalid", "as_of")
        return value.astimezone(timezone.utc)
    return _timestamp(value, "as_of")


def _artifact_index(artifacts: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for artifact in artifacts:
        artifact_id = artifact.get("artifact_id") if isinstance(artifact, dict) else None
        if not isinstance(artifact_id, str):
            continue
        if artifact_id in indexed:
            raise RecordError("frozen_corpus_artifact_ambiguous", artifact_id)
        indexed[artifact_id] = artifact
    return indexed


def _registered_relative(record: dict[str, Any]) -> str:
    relative = record.get("relative_path")
    if not isinstance(relative, str) or "\\" in relative:
        raise RecordError("frozen_corpus_artifact_path_invalid", str(record.get("artifact_id", "unknown")))
    path = PurePosixPath(relative)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise RecordError("frozen_corpus_artifact_path_invalid", str(record.get("artifact_id", "unknown")))
    if not path.parts or path.parts[0] != "evidence":
        raise RecordError("frozen_corpus_artifact_path_invalid", str(record.get("artifact_id", "unknown")))
    return path.as_posix()


def _open_root(engagement: Path) -> int:
    absolute = Path(os.path.abspath(engagement))
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    if (
        len(absolute.parts) >= 4
        and absolute.parts[1:3] == ("dev", "fd")
        and absolute.parts[3].isdigit()
    ):
        root = os.dup(int(absolute.parts[3]))
        try:
            if not stat.S_ISDIR(os.fstat(root).st_mode):
                raise OSError("bound engagement root is not a directory")
            for component in absolute.parts[4:]:
                child = os.open(component, flags, dir_fd=root)
                os.close(root)
                root = child
            return root
        except Exception:
            os.close(root)
            raise
    root = os.open(absolute, flags)
    if not stat.S_ISDIR(os.fstat(root).st_mode):
        os.close(root)
        raise OSError("engagement root is not a directory")
    return root


def _read_registered_bytes(engagement: Path, record: dict[str, Any]) -> bytes:
    relative = _registered_relative(record)
    try:
        root = _open_root(engagement)
    except OSError as exc:
        raise RecordError("frozen_corpus_artifact_unavailable", str(record.get("artifact_id"))) from exc
    parent = root
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        parts = PurePosixPath(relative).parts
        for component in parts[:-1]:
            child = os.open(component, directory_flags, dir_fd=parent)
            os.close(parent)
            parent = child
        fd = os.open(
            parts[-1],
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
            dir_fd=parent,
        )
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_size != record.get("size"):
                raise RecordError("frozen_corpus_artifact_size_mismatch", str(record.get("artifact_id")))
            chunks: list[bytes] = []
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            after = os.fstat(fd)
            if (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
            ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
                raise RecordError("frozen_corpus_artifact_changed", str(record.get("artifact_id")))
            data = b"".join(chunks)
        finally:
            os.close(fd)
    except RecordError:
        raise
    except OSError as exc:
        raise RecordError("frozen_corpus_artifact_unavailable", str(record.get("artifact_id"))) from exc
    finally:
        os.close(parent)
    if sha256_bytes(data) != record.get("sha256"):
        raise RecordError("frozen_corpus_artifact_digest_mismatch", str(record.get("artifact_id")))
    return data


def _load_manifest(data: bytes) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise RecordError("duplicate_json_key", f"duplicate corpus manifest key: {key}")
            result[key] = value
        return result

    try:
        manifest = json.loads(data.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except RecordError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RecordError("frozen_corpus_manifest_invalid", "manifest is not canonical JSON data") from exc
    problems = validate_record(manifest, "corpus-enumeration")
    if problems:
        raise RecordError("frozen_corpus_manifest_invalid", "corpus freeze schema validation failed", problems)
    return manifest


def _linked_enumeration_relative(manifest_relative: str, linked_path: str) -> str:
    if not isinstance(linked_path, str) or not linked_path or "\\" in linked_path:
        raise RecordError("frozen_corpus_link_invalid", "artifact.path")
    if PurePosixPath(linked_path).is_absolute():
        raise RecordError("frozen_corpus_link_invalid", "artifact.path")
    normalized = posixpath.normpath(posixpath.join(posixpath.dirname(manifest_relative), linked_path))
    path = PurePosixPath(normalized)
    if path.is_absolute() or not path.parts or path.parts[0] != "evidence" or ".." in path.parts:
        raise RecordError("frozen_corpus_link_invalid", "artifact.path")
    return path.as_posix()


def _registered_record(
    indexed: dict[str, dict[str, Any]],
    artifact_ref: str,
    cutoff: datetime,
) -> dict[str, Any]:
    record = indexed.get(artifact_ref)
    if record is None:
        raise RecordError("frozen_corpus_artifact_unregistered", artifact_ref)
    problems = validate_record(record, "artifact")
    if problems:
        raise RecordError("frozen_corpus_artifact_invalid", artifact_ref, problems)
    if _timestamp(record.get("created_at"), f"{artifact_ref}.created_at") > cutoff:
        raise RecordError("frozen_corpus_artifact_from_future", artifact_ref)
    _registered_relative(record)
    return record


def resolve_frozen_corpus_denominator(
    engagement: Path,
    artifacts: Iterable[dict[str, Any]],
    manifest_ref: str,
    as_of: str | datetime,
    scope_bytes: bytes,
    scope_attested_at: str | datetime,
) -> dict[str, Any]:
    """Return the exact registered package + entrypoint denominator as of an event time.

    Both files must be immutable artifact-ledger entries no newer than ``as_of``.  The registered
    manifest digest must also be the single exact corpus pin in the genesis signed scope bytes,
    and the manifest's own freeze time must not be later than that attestation.  The returned
    ``row_count`` is the only value a budget-bounded declaration should compare with its
    ``enumerated_count``.
    """

    scope_pin = _scope_frozen_manifest_pin(scope_bytes)
    if not isinstance(manifest_ref, str) or not manifest_ref:
        raise RecordError("frozen_corpus_artifact_unregistered", "manifest reference missing")
    cutoff = _as_of(as_of)
    indexed = _artifact_index(artifacts)
    manifest_record = _registered_record(indexed, manifest_ref, cutoff)
    if manifest_record.get("sha256") != scope_pin:
        raise RecordError(
            "frozen_corpus_scope_pin_mismatch",
            f"scope pin does not match registered manifest {manifest_ref}",
        )
    manifest_relative = _registered_relative(manifest_record)
    manifest = _load_manifest(_read_registered_bytes(engagement, manifest_record))
    frozen_at = _timestamp(manifest.get("frozen_at"), "frozen_at")
    if frozen_at > _as_of(scope_attested_at):
        raise RecordError(
            "frozen_corpus_manifest_not_precommitted",
            "corpus manifest was not frozen before genesis scope attestation",
        )
    if frozen_at > cutoff:
        raise RecordError("frozen_corpus_manifest_from_future", manifest_ref)

    artifact_spec = manifest["artifact"]
    frozen_link = manifest["frozen_inputs"]["corpus-enumeration"]
    if frozen_link != {"path": artifact_spec["path"], "sha256": artifact_spec["sha256"]}:
        raise RecordError("frozen_corpus_link_invalid", "frozen_inputs.corpus-enumeration")
    enumeration_relative = _linked_enumeration_relative(manifest_relative, artifact_spec["path"])
    matching = [
        record
        for record in indexed.values()
        if isinstance(record.get("relative_path"), str)
        and record.get("relative_path") == enumeration_relative
    ]
    if not matching:
        raise RecordError("frozen_corpus_artifact_unregistered", enumeration_relative)
    if len(matching) != 1:
        raise RecordError("frozen_corpus_artifact_ambiguous", enumeration_relative)
    enumeration_record = _registered_record(indexed, matching[0]["artifact_id"], cutoff)
    if enumeration_record.get("engagement_id") != manifest_record.get("engagement_id"):
        raise RecordError("frozen_corpus_cross_engagement_link", enumeration_record["artifact_id"])
    enumeration_bytes = _read_registered_bytes(engagement, enumeration_record)
    raw_digest = sha256_bytes(enumeration_bytes).removeprefix("sha256:")
    if raw_digest != artifact_spec["sha256"]:
        raise RecordError("frozen_corpus_link_digest_mismatch", enumeration_record["artifact_id"])
    try:
        rows = _read_artifact(engagement / enumeration_relative, enumeration_bytes)
    except EnumerationError as exc:
        raise RecordError("frozen_corpus_enumeration_invalid", enumeration_record["artifact_id"]) from exc
    row_count = len(rows)
    package_count = len({(row.package, row.version) for row in rows})
    if artifact_spec["row_count"] != row_count:
        raise RecordError("frozen_corpus_row_count_mismatch", manifest_ref)
    if artifact_spec["package_count"] != package_count:
        raise RecordError("frozen_corpus_package_count_mismatch", manifest_ref)
    return {
        "manifest_artifact_ref": manifest_ref,
        "enumeration_artifact_ref": enumeration_record["artifact_id"],
        "frozen_at": manifest["frozen_at"],
        "row_count": row_count,
        "package_count": package_count,
    }


def require_enumerated_count_matches(enumerated_count: Any, denominator: dict[str, Any]) -> None:
    """Reject a self-declared count that differs from the resolved frozen row count."""

    expected = denominator.get("row_count")
    if type(enumerated_count) is not int or type(expected) is not int or enumerated_count != expected:
        raise RecordError(
            "coverage_enumerated_count_mismatch",
            f"enumerated_count={enumerated_count!r}; frozen row_count={expected!r}",
        )
