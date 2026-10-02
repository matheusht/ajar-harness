#!/usr/bin/env python3
"""Read-only retrieval over provenance-attested, scrubbed casebooks.

Engagement-derived casebooks are portable, but their origin is resolved only through a
target-local resolver. Every reuse rechecks that local source under its engagement lock. A
missing resolver, an unhealthy source, or a quarantine marker excludes the casebook. Existing
casebooks without the closed provenance record therefore fail closed until explicitly reimported.

The retrieval result remains a non-authoritative sensor: it never carries a verdict or grants an
action. ``attest`` is the import/promotion boundary; it writes only opaque provenance to the
portable casebook and keeps the source path in the explicitly supplied local resolver.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import secrets
import stat
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from engagement_records import RecordError, canonical_json_bytes, sha256_bytes
from engagement_state import bound_engagement_lock, read_ledger, reduce_engagement
from engagement_quarantine import (
    _open_directory as _open_offline_directory,
    _require_bound_parent_safe,
    quarantined_ancestor,
    read_safe_offline_file,
    read_safe_offline_tree,
    require_safe_offline_output,
)
from ledger_health import probe_ledger_health


ROOT = Path(__file__).resolve().parent.parent
CASEBOOKS = ROOT / "casebooks"
PROVENANCE_NAME = "source-provenance.json"
LOCK_NAME = ".source-provenance.lock"
FORBIDDEN_KEYS = ("verdict", "confirmed", "allow", "authorizes")
SOURCE_KINDS = frozenset({"engagement", "synthetic", "public"})
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_CASEBOOK_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_PROVENANCE_KEYS = frozenset(
    {"schema_version", "casebook_id", "source_kind", "origin_ref", "source_instance_ref", "content_digest"}
)
_MAX_JSON_BYTES = 1024 * 1024


class ProvenanceError(Exception):
    """A deliberately detail-free failure at the portable/local provenance boundary."""


def _open_directory(path: Path) -> int:
    absolute = Path(os.path.abspath(path))
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        terminal = absolute.lstat()
        if stat.S_ISLNK(terminal.st_mode) or not stat.S_ISDIR(terminal.st_mode):
            raise ProvenanceError()
        resolved_parent = absolute.parent.resolve(strict=True)
        fd = os.open("/", flags)
        for component in (*resolved_parent.parts[1:], absolute.name):
            child = os.open(component, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except OSError as exc:
        if "fd" in locals():
            os.close(fd)
        raise ProvenanceError() from exc


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProvenanceError()
        result[key] = value
    return result


def _decode_closed_json(data: bytes) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError, ProvenanceError) as exc:
        raise ProvenanceError() from exc
    if not isinstance(value, dict) or canonical_json_bytes(value) != data:
        raise ProvenanceError()
    return value


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _casebook_snapshot_bytes(
    casebook_id: str,
    files: dict[str, bytes],
) -> tuple[str, dict[str, str]]:
    """Derive a casebook digest only from one already-bound portable tree snapshot."""

    if not _CASEBOOK_ID.fullmatch(casebook_id):
        raise ProvenanceError()
    manifest: list[dict[str, Any]] = []
    documents: dict[str, str] = {}
    try:
        for relative, data in sorted(files.items()):
            if relative in {PROVENANCE_NAME, LOCK_NAME}:
                continue
            if len(data) > 4 * 1024 * 1024:
                raise ProvenanceError()
            manifest.append(
                {"path": relative, "size": len(data), "digest": sha256_bytes(data)}
            )
            if relative in {"lessons.md", "promotion-notes.md"}:
                documents[relative] = data.decode("utf-8")
    except (UnicodeDecodeError, ProvenanceError) as exc:
        raise ProvenanceError() from exc
    if not documents:
        raise ProvenanceError()
    manifest.sort(key=lambda row: row["path"])
    return sha256_bytes(canonical_json_bytes(manifest)), documents


def _casebook_snapshot(casebook: Path) -> tuple[str, dict[str, str]]:
    """Bind every portable casebook byte while returning only retrievable documents."""

    try:
        files = read_safe_offline_tree(casebook)
    except (OSError, ValueError) as exc:
        raise ProvenanceError() from exc
    return _casebook_snapshot_bytes(casebook.name, files)


def _valid_provenance(value: Any, *, expected_casebook: str) -> bool:
    if not isinstance(value, dict) or set(value) != _PROVENANCE_KEYS:
        return False
    if (
        type(value.get("schema_version")) is not int
        or value["schema_version"] != 1
        or value.get("casebook_id") != expected_casebook
    ):
        return False
    source_kind = value.get("source_kind")
    if source_kind not in SOURCE_KINDS:
        return False
    if not isinstance(value.get("content_digest"), str) or not _DIGEST.fullmatch(value["content_digest"]):
        return False
    origin = value.get("origin_ref")
    instance = value.get("source_instance_ref")
    return (
        isinstance(origin, str)
        and bool(_DIGEST.fullmatch(origin))
        and isinstance(instance, str)
        and bool(_DIGEST.fullmatch(instance))
        if source_kind == "engagement"
        else origin is None and instance is None
    )


def _source_origin(source: Path) -> str:
    health = probe_ledger_health(source)
    if health.get("status") != "healthy":
        raise ProvenanceError()
    state = reduce_engagement(source)
    events = read_ledger(source, "event")
    if not events or events[0].get("event_type") != "scope.attested":
        raise ProvenanceError()
    return sha256_bytes(
        canonical_json_bytes(
            {
                "schema_version": 1,
                "engagement_id": state["engagement_id"],
                "genesis_record_hash": events[0]["record_hash"],
                "scope_hash": state["scope_hash"],
            }
        )
    )


def _identity_token(identity: os.stat_result, *, directory: bool) -> dict[str, int | None]:
    expected = stat.S_ISDIR(identity.st_mode) if directory else stat.S_ISREG(identity.st_mode)
    if stat.S_ISLNK(identity.st_mode) or not expected:
        raise ProvenanceError()
    birthtime = getattr(identity, "st_birthtime", None)
    generation = getattr(identity, "st_gen", None)
    return {
        "device": identity.st_dev,
        "inode": identity.st_ino,
        "birthtime_ns": int(float(birthtime) * 1_000_000_000) if birthtime is not None else None,
        "generation": int(generation) if type(generation) is int and generation > 0 else None,
    }


def _open_relative_regular(root_fd: int, relative: str) -> int:
    path = Path(relative)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ProvenanceError()
    directory_fd = os.dup(root_fd)
    try:
        for component in path.parts[:-1]:
            child_fd = os.open(
                component,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=directory_fd,
            )
            os.close(directory_fd)
            directory_fd = child_fd
        fd = os.open(
            path.parts[-1],
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
            dir_fd=directory_fd,
        )
    except OSError as exc:
        raise ProvenanceError() from exc
    finally:
        os.close(directory_fd)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise ProvenanceError()
    return fd


def _source_instance(source_fd: int) -> dict[str, dict[str, int | None]]:
    bound = Path(f"/dev/fd/{source_fd}")
    events = read_ledger(bound, "event")
    attestation = next(
        (event for event in reversed(events) if event.get("event_type") == "scope.attested"),
        None,
    )
    snapshot_path = (attestation or {}).get("payload", {}).get("scope_snapshot_path")
    if not isinstance(snapshot_path, str):
        raise ProvenanceError()
    events_fd = _open_relative_regular(source_fd, "events.jsonl")
    snapshot_fd = _open_relative_regular(source_fd, snapshot_path)
    try:
        return {
            "root": _identity_token(os.fstat(source_fd), directory=True),
            "events": _identity_token(os.fstat(events_fd), directory=False),
            "scope_snapshot": _identity_token(os.fstat(snapshot_fd), directory=False),
        }
    finally:
        os.close(events_fd)
        os.close(snapshot_fd)


def _valid_instance(value: Any) -> bool:
    if not isinstance(value, dict) or set(value) != {"root", "events", "scope_snapshot"}:
        return False
    for token in value.values():
        if not isinstance(token, dict) or set(token) != {"device", "inode", "birthtime_ns", "generation"}:
            return False
        if type(token.get("device")) is not int or token["device"] < 0:
            return False
        if type(token.get("inode")) is not int or token["inode"] <= 0:
            return False
        if token.get("birthtime_ns") is not None and (
            type(token["birthtime_ns"]) is not int or token["birthtime_ns"] <= 0
        ):
            return False
        if token.get("generation") is not None and (
            type(token["generation"]) is not int or token["generation"] <= 0
        ):
            return False
    return True


def _source_instance_ref(origin: str, instance: dict[str, dict[str, int | None]]) -> str:
    if not _valid_instance(instance):
        raise ProvenanceError()
    return sha256_bytes(canonical_json_bytes({"origin_ref": origin, "instance": instance}))


def _open_bound_source(source: Path) -> tuple[int, Path, os.stat_result]:
    """Open one terminal directory without following it and bind its canonical identity."""

    fd = -1
    try:
        absolute = Path(os.path.abspath(source))
        terminal = absolute.lstat()
        if stat.S_ISLNK(terminal.st_mode) or not stat.S_ISDIR(terminal.st_mode):
            raise ProvenanceError()
        resolved = absolute.resolve(strict=True)
        fd = os.open(
            absolute,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        identity = os.fstat(fd)
        current = resolved.lstat()
    except OSError as exc:
        if fd >= 0:
            os.close(fd)
        raise ProvenanceError() from exc
    if (
        not stat.S_ISDIR(identity.st_mode)
        or stat.S_ISLNK(current.st_mode)
        or not stat.S_ISDIR(current.st_mode)
        or (identity.st_dev, identity.st_ino) != (current.st_dev, current.st_ino)
    ):
        os.close(fd)
        raise ProvenanceError()
    return fd, resolved, identity


def _require_bound_source_current(source: Path, fd: int, identity: os.stat_result) -> None:
    try:
        bound = os.fstat(fd)
        current = source.lstat()
    except OSError as exc:
        raise ProvenanceError() from exc
    expected = (identity.st_dev, identity.st_ino)
    if (
        (bound.st_dev, bound.st_ino) != expected
        or not stat.S_ISDIR(bound.st_mode)
        or stat.S_ISLNK(current.st_mode)
        or not stat.S_ISDIR(current.st_mode)
        or (current.st_dev, current.st_ino) != expected
    ):
        raise ProvenanceError()


def _parse_resolver(data: bytes) -> dict[str, dict[str, Any]]:
    value = _decode_closed_json(data)
    if (
        set(value) != {"schema_version", "origins"}
        or type(value.get("schema_version")) is not int
        or value["schema_version"] != 1
    ):
        raise ProvenanceError()
    origins = value.get("origins")
    if not isinstance(origins, dict) or len(origins) > 10000:
        raise ProvenanceError()
    result: dict[str, dict[str, Any]] = {}
    for origin, binding in origins.items():
        source_path = binding.get("path") if isinstance(binding, dict) else None
        if (
            not isinstance(origin, str)
            or not _DIGEST.fullmatch(origin)
            or not isinstance(binding, dict)
            or set(binding) != {"path", "instance"}
            or not isinstance(source_path, str)
            or not source_path
            or "\n" in source_path
            or len(source_path) > 4096
            or not Path(source_path).is_absolute()
            or not _valid_instance(binding.get("instance"))
        ):
            raise ProvenanceError()
        result[origin] = binding
    return result


def _load_resolver(path: Path) -> dict[str, dict[str, Any]]:
    """Load one portable resolver through a single identity-bound parent."""

    try:
        return _parse_resolver(read_safe_offline_file(path.absolute()))
    except (OSError, ValueError) as exc:
        raise ProvenanceError() from exc


@dataclass(frozen=True)
class _BoundOutputParent:
    requested: Path
    canonical_parent: Path
    parent_fd: int

    @property
    def leaf_name(self) -> str:
        return self.requested.name


def _require_output_parent_current(
    bound: _BoundOutputParent,
    *,
    leaf_name: str | None = None,
) -> None:
    """Recheck both the requested name and the current location of one bound parent."""

    name = leaf_name or bound.leaf_name
    requested_leaf = bound.requested.with_name(name)
    try:
        require_safe_offline_output(requested_leaf)
        _require_bound_parent_safe(
            bound.parent_fd,
            bound.canonical_parent,
            name,
            output=True,
        )
        current_parent = bound.requested.parent.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ProvenanceError() from exc
    if current_parent != bound.canonical_parent:
        raise ProvenanceError()


@contextmanager
def _bound_output_parent(path: Path) -> Iterator[_BoundOutputParent]:
    absolute = Path(os.path.abspath(path))
    try:
        require_safe_offline_output(absolute)
        canonical_parent = absolute.parent.resolve(strict=True)
        require_safe_offline_output(canonical_parent / absolute.name)
        parent_fd = _open_offline_directory(canonical_parent)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ProvenanceError() from exc
    bound = _BoundOutputParent(absolute, canonical_parent, parent_fd)
    try:
        _require_output_parent_current(bound)
        yield bound
    finally:
        os.close(parent_fd)


def _read_regular_at(
    parent_fd: int,
    name: str,
    *,
    limit: int = _MAX_JSON_BYTES,
) -> bytes:
    try:
        fd = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
            dir_fd=parent_fd,
        )
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise ProvenanceError() from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise ProvenanceError()
        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(fd, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        after = os.fstat(fd)
        if len(data) > limit or (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise ProvenanceError()
        return data
    finally:
        os.close(fd)


def _load_resolver_bound(bound: _BoundOutputParent) -> dict[str, dict[str, Any]]:
    _require_output_parent_current(bound)
    try:
        data = _read_regular_at(bound.parent_fd, bound.leaf_name)
    except FileNotFoundError:
        _require_output_parent_current(bound)
        return {}
    _require_output_parent_current(bound)
    return _parse_resolver(data)


def _entry_identity(value: os.stat_result) -> tuple[int, int, int]:
    return value.st_dev, value.st_ino, value.st_mode


def _regular_entry_or_none(bound: _BoundOutputParent) -> os.stat_result | None:
    try:
        value = os.stat(bound.leaf_name, dir_fd=bound.parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(value.st_mode) or not stat.S_ISREG(value.st_mode):
        raise ProvenanceError()
    return value


def _unlink_exact(parent_fd: int, name: str, expected: tuple[int, int, int]) -> None:
    try:
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if _entry_identity(current) != expected:
        raise ProvenanceError()
    os.unlink(name, dir_fd=parent_fd)


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    written = 0
    while written < len(view):
        count = os.write(fd, view[written:])
        if count <= 0:
            raise ProvenanceError()
        written += count
    os.fsync(fd)


def _atomic_write_bound(bound: _BoundOutputParent, data: bytes) -> None:
    """Replace one resolver leaf using only its lock-bound parent, with rollback."""

    _require_output_parent_current(bound)
    existing = _regular_entry_or_none(bound)
    existing_identity = _entry_identity(existing) if existing is not None else None
    temporary = f".{bound.leaf_name}.{os.getpid()}.{secrets.token_hex(8)}"
    backup = f".{bound.leaf_name}.{os.getpid()}.{secrets.token_hex(8)}.previous"
    temporary_identity: tuple[int, int, int] | None = None
    published = False
    backed_up = False
    try:
        fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=bound.parent_fd,
        )
        try:
            temporary_identity = _entry_identity(os.fstat(fd))
            # A parent can move after open(2) returns. Check before writing any bytes through it.
            _require_output_parent_current(bound)
            _write_all(fd, data)
        finally:
            os.close(fd)
        _require_output_parent_current(bound)
        if existing_identity is not None:
            current = _regular_entry_or_none(bound)
            if current is None or _entry_identity(current) != existing_identity:
                raise ProvenanceError()
            os.rename(
                bound.leaf_name,
                backup,
                src_dir_fd=bound.parent_fd,
                dst_dir_fd=bound.parent_fd,
            )
            backed_up = True
            _require_output_parent_current(bound)
        os.replace(
            temporary,
            bound.leaf_name,
            src_dir_fd=bound.parent_fd,
            dst_dir_fd=bound.parent_fd,
        )
        published = True
        _require_output_parent_current(bound)
        os.fsync(bound.parent_fd)
        _require_output_parent_current(bound)
        if backed_up:
            os.unlink(backup, dir_fd=bound.parent_fd)
            backed_up = False
            os.fsync(bound.parent_fd)
    except Exception as exc:
        try:
            if published and temporary_identity is not None:
                _unlink_exact(bound.parent_fd, bound.leaf_name, temporary_identity)
                published = False
            if backed_up:
                os.rename(
                    backup,
                    bound.leaf_name,
                    src_dir_fd=bound.parent_fd,
                    dst_dir_fd=bound.parent_fd,
                )
                backed_up = False
            os.fsync(bound.parent_fd)
        except Exception as rollback_exc:
            raise ProvenanceError() from rollback_exc
        if isinstance(exc, ProvenanceError):
            raise
        raise ProvenanceError() from exc
    finally:
        if temporary_identity is not None:
            try:
                _unlink_exact(bound.parent_fd, temporary, temporary_identity)
            except FileNotFoundError:
                pass
        if backed_up:
            try:
                os.rename(
                    backup,
                    bound.leaf_name,
                    src_dir_fd=bound.parent_fd,
                    dst_dir_fd=bound.parent_fd,
                )
            except OSError:
                pass


def _write_exclusive(path: Path, data: bytes) -> bool:
    """Publish a complete file exactly once; an exact concurrent retry is idempotent."""

    with _bound_output_parent(path) as bound:
        temporary = f".{bound.leaf_name}.{os.getpid()}.{secrets.token_hex(8)}"
        temporary_identity: tuple[int, int, int] | None = None
        published = False
        try:
            fd = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=bound.parent_fd,
            )
            try:
                temporary_identity = _entry_identity(os.fstat(fd))
                _require_output_parent_current(bound)
                _write_all(fd, data)
            finally:
                os.close(fd)
            _require_output_parent_current(bound)
            try:
                os.link(
                    temporary,
                    bound.leaf_name,
                    src_dir_fd=bound.parent_fd,
                    dst_dir_fd=bound.parent_fd,
                    follow_symlinks=False,
                )
                published = True
                created = True
            except FileExistsError:
                if _read_regular_at(bound.parent_fd, bound.leaf_name) != data:
                    raise ProvenanceError()
                created = False
            _require_output_parent_current(bound)
            os.fsync(bound.parent_fd)
            _require_output_parent_current(bound)
            return created
        except Exception as exc:
            try:
                if published and temporary_identity is not None:
                    _unlink_exact(bound.parent_fd, bound.leaf_name, temporary_identity)
                    published = False
                os.fsync(bound.parent_fd)
            except Exception as rollback_exc:
                raise ProvenanceError() from rollback_exc
            if isinstance(exc, ProvenanceError):
                raise
            raise ProvenanceError() from exc
        finally:
            if temporary_identity is not None:
                try:
                    _unlink_exact(bound.parent_fd, temporary, temporary_identity)
                except FileNotFoundError:
                    pass


@contextmanager
def _resolver_lock(path: Path) -> Iterator[_BoundOutputParent]:
    lock_path = path.with_name(f".{path.name}.lock")
    with _bound_output_parent(path) as bound:
        try:
            require_safe_offline_output(lock_path)
            _require_output_parent_current(bound, leaf_name=lock_path.name)
            fd = os.open(
                lock_path.name,
                os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=bound.parent_fd,
            )
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ProvenanceError()
            _require_output_parent_current(bound, leaf_name=lock_path.name)
            fcntl.flock(fd, fcntl.LOCK_EX)
            _require_output_parent_current(bound, leaf_name=lock_path.name)
            yield bound
            _require_output_parent_current(bound, leaf_name=lock_path.name)
        except (OSError, ValueError) as exc:
            raise ProvenanceError() from exc
        finally:
            if "fd" in locals():
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                finally:
                    os.close(fd)


def _write_resolver(
    path: Path,
    origin: str,
    source: Path,
    instance: dict[str, dict[str, int | None]],
) -> None:
    if not source.is_absolute() or not _valid_instance(instance):
        raise ProvenanceError()
    binding = {
        "path": str(source),
        "instance": instance,
    }
    with _resolver_lock(path) as bound:
        origins = _load_resolver_bound(bound)
        existing = origins.get(origin)
        if existing is not None and existing != binding:
            raise ProvenanceError()
        if existing == binding:
            return
        origins[origin] = binding
        _atomic_write_bound(
            bound,
            canonical_json_bytes({"schema_version": 1, "origins": origins}),
        )


def attest_casebook(
    casebook: Path,
    *,
    source_kind: str | None = None,
    source_engagement: Path | None = None,
    source_resolver: Path | None = None,
) -> dict[str, Any]:
    """Create or refresh portable provenance only after the source gate succeeds."""

    if bool(source_kind) == bool(source_engagement):
        raise ProvenanceError()
    casebook = casebook.absolute()
    try:
        require_safe_offline_output(casebook / PROVENANCE_NAME)
        if source_resolver is not None:
            require_safe_offline_output(source_resolver.absolute())
    except ValueError as exc:
        raise ProvenanceError() from exc
    if source_kind is not None:
        if source_kind not in {"synthetic", "public"} or source_resolver is not None:
            raise ProvenanceError()
        content_digest, _ = _casebook_snapshot(casebook)
        provenance = {
            "schema_version": 1,
            "casebook_id": casebook.name,
            "source_kind": source_kind,
            "origin_ref": None,
            "source_instance_ref": None,
            "content_digest": content_digest,
        }
        provenance_bytes = canonical_json_bytes(provenance)
        _write_exclusive(casebook / PROVENANCE_NAME, provenance_bytes)
        return provenance

    if source_resolver is None:
        raise ProvenanceError()
    source_fd, source, identity = _open_bound_source(source_engagement)
    try:
        # The lock and every health/origin read use the same directory FD. A pathname ABA can
        # therefore neither hide a quarantine marker nor substitute copied ledger bytes.
        with bound_engagement_lock(source_fd, create=False):
            bound_source = Path(f"/dev/fd/{source_fd}")
            origin = _source_origin(bound_source)
            instance = _source_instance(source_fd)
            source_instance_ref = _source_instance_ref(origin, instance)
            content_digest, _ = _casebook_snapshot(casebook)
            provenance = {
                "schema_version": 1,
                "casebook_id": casebook.name,
                "source_kind": "engagement",
                "origin_ref": origin,
                "source_instance_ref": source_instance_ref,
                "content_digest": content_digest,
            }
            provenance_bytes = canonical_json_bytes(provenance)
            _require_bound_source_current(source, source_fd, identity)
            _write_resolver(source_resolver.absolute(), origin, source, instance)
            _require_bound_source_current(source, source_fd, identity)
            _write_exclusive(casebook / PROVENANCE_NAME, provenance_bytes)
            return provenance
    finally:
        os.close(source_fd)


def _casebook_items(
    casebook: Path,
    provenance: dict[str, Any],
    resolver: dict[str, dict[str, Any]] | None,
    *,
    snapshot: dict[str, bytes] | None = None,
) -> list[dict[str, Any]]:
    if not _valid_provenance(provenance, expected_casebook=casebook.name):
        raise ProvenanceError()

    def build() -> list[dict[str, Any]]:
        digest, documents = (
            _casebook_snapshot_bytes(casebook.name, snapshot)
            if snapshot is not None
            else _casebook_snapshot(casebook)
        )
        if digest != provenance["content_digest"]:
            raise ProvenanceError()
        return [
            {
                "id": f"{casebook.name}:{filename}",
                "source_type": "casebook",
                "sanitized_text": text,
                "allowed_planes": ["plane-3", "plane-4"],
                "redaction_attestation": {"redacted": True, "by": "casebook-anonymization"},
                "_tokens": _tokens(text),
                "_source_ref": f"casebooks/{casebook.name}/{filename}",
                "_casebook_id": casebook.name,
                "_source_kind": provenance["source_kind"],
            }
            for filename, text in sorted(documents.items())
        ]

    if provenance["source_kind"] != "engagement":
        return build()
    origin = provenance["origin_ref"]
    if resolver is None or origin not in resolver:
        raise ProvenanceError()
    binding = resolver[origin]
    source = Path(binding["path"])
    source_fd, canonical_source, identity = _open_bound_source(source)
    try:
        with bound_engagement_lock(source_fd, create=False):
            if (
                not stat.S_ISDIR(identity.st_mode)
                or _source_instance(source_fd) != binding["instance"]
                or _source_instance_ref(origin, binding["instance"]) != provenance["source_instance_ref"]
            ):
                raise ProvenanceError()
            if _source_origin(Path(f"/dev/fd/{source_fd}")) != origin:
                raise ProvenanceError()
            # Keep both the source lock and bound directory FD through the portable read. The
            # canonical pathname check is the final reuse linearization point.
            items = build()
            _require_bound_source_current(canonical_source, source_fd, identity)
            final_instance = _source_instance(source_fd)
            if final_instance != binding["instance"] or _source_instance_ref(origin, final_instance) != provenance["source_instance_ref"]:
                raise ProvenanceError()
            return items
    except OSError as exc:
        raise ProvenanceError() from exc
    finally:
        os.close(source_fd)


def _load_index(
    *,
    casebooks: Path = CASEBOOKS,
    source_resolver: Path | None = None,
) -> list[dict[str, Any]]:
    """Build the admissible index. Malformed, unresolved, or unhealthy inputs are excluded."""

    items: list[dict[str, Any]] = []
    resolver: dict[str, dict[str, Any]] | None = None
    if source_resolver is not None:
        if quarantined_ancestor(source_resolver):
            return items
        try:
            resolver = _load_resolver(source_resolver.absolute())
        except ProvenanceError:
            resolver = None
        if quarantined_ancestor(source_resolver):
            return items
    try:
        portable_tree = read_safe_offline_tree(casebooks)
    except (OSError, ValueError):
        return items
    casebook_names = sorted(
        {
            parts[0]
            for relative in portable_tree
            if len(parts := Path(relative).parts) >= 2
        }
    )
    for casebook_name in casebook_names:
        if casebook_name.startswith("_") or not _CASEBOOK_ID.fullmatch(casebook_name):
            continue
        casebook = casebooks / casebook_name
        prefix = f"{casebook_name}/"
        casebook_snapshot = {
            relative[len(prefix):]: data
            for relative, data in portable_tree.items()
            if relative.startswith(prefix)
        }
        try:
            provenance = _decode_closed_json(casebook_snapshot[PROVENANCE_NAME])
            items.extend(
                _casebook_items(
                    casebook,
                    provenance,
                    resolver,
                    snapshot=casebook_snapshot,
                )
            )
        except (KeyError, OSError, ProvenanceError, RecordError):
            continue
    try:
        final_tree = read_safe_offline_tree(casebooks)
    except (OSError, ValueError):
        return []
    if final_tree != portable_tree or (
        source_resolver is not None and quarantined_ancestor(source_resolver)
    ):
        return []
    return items


def _retrieve_from_index(
    query: str,
    top_k: int,
    index: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    q = _tokens(query)
    scored = []
    for item in index:
        overlap = len(q & item["_tokens"])
        if overlap == 0:
            continue
        score = overlap / (len(q) or 1)
        excerpt = item["sanitized_text"].strip().replace("\n", " ")[:240]
        scored.append(
            {
                "kind": "retrieved_prior",
                "authoritative": False,
                "casebook_id": item["_casebook_id"],
                "scrubbed_excerpt": excerpt,
                "score": round(score, 3),
                "source_ref": item["_source_ref"],
            }
        )
    scored.sort(key=lambda row: row["score"], reverse=True)
    return scored[: max(0, top_k)]


def retrieve(
    query: str,
    top_k: int = 3,
    *,
    casebooks: Path = CASEBOOKS,
    source_resolver: Path | None = None,
) -> list[dict[str, Any]]:
    """Return non-authoritative priors after a fresh provenance and source-health pass."""

    return _retrieve_from_index(
        query,
        top_k,
        _load_index(casebooks=casebooks, source_resolver=source_resolver),
    )


def self_test() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="casebook-index-self-test-") as temporary:
        root = Path(temporary).resolve()
        casebook = root / "casebooks" / "synthetic-positive"
        casebook.mkdir(parents=True)
        casebook.joinpath("lessons.md").write_text(
            "client supplied selector tenant authorization\n", encoding="utf-8"
        )
        unattested = root / "casebooks" / "unattested"
        unattested.mkdir()
        unattested.joinpath("lessons.md").write_text("untrusted legacy lesson\n", encoding="utf-8")
        attest_casebook(casebook, source_kind="synthetic")
        index = _load_index(casebooks=root / "casebooks")
        if not index:
            failures.append("explicit synthetic attestation did not produce an admissible index row")
        if any(item["_casebook_id"] == "unattested" for item in index):
            failures.append("unattested legacy casebook entered the index")
        for item in index:
            for key in FORBIDDEN_KEYS:
                if key in item:
                    failures.append("index record carries a forbidden judge key")
            for required in (
                "id", "source_type", "sanitized_text", "allowed_planes", "redaction_attestation"
            ):
                if required not in item:
                    failures.append("index record is missing a memory-item field")
            if "plane-1" in item.get("allowed_planes", []):
                failures.append("index record claims plane-1 write access")
        results = _retrieve_from_index("client supplied selector tenant authorization", 3, index)
        if len(results) != 1:
            failures.append("positive attested fixture was not retrieved")
        for result in results:
            if result.get("authoritative") is not False or result.get("kind") != "retrieved_prior":
                failures.append("result is not a non-authoritative retrieved prior")
            if any(key in result for key in FORBIDDEN_KEYS):
                failures.append("result carries a forbidden judge key")

    print(
        f"  {'ok  ' if not any('unattested' in failure for failure in failures) else 'FAIL'} "
        "unattested casebooks fail closed"
    )
    print(
        f"  {'ok  ' if not any('positive' in failure or 'synthetic' in failure for failure in failures) else 'FAIL'} "
        "explicit synthetic attestation provides a positive fixture"
    )
    print(f"  {'ok  ' if not failures else 'FAIL'} firewall: retrieval remains non-authoritative")
    for failure in failures:
        print(f"  FAIL {failure}")
    print("CASEBOOK-RETRIEVAL-INDEX: " + ("PASS" if not failures else "FAIL"))
    return 0 if not failures else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="provenance-gated, read-only casebook retrieval index"
    )
    parser.add_argument("--casebooks", type=Path, default=CASEBOOKS)
    parser.add_argument("--source-resolver", type=Path)
    parser.add_argument("--query")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--self-test", action="store_true")
    subparsers = parser.add_subparsers(dest="command")
    attest = subparsers.add_parser("attest")
    attest.add_argument("--casebook", type=Path, required=True)
    source = attest.add_mutually_exclusive_group(required=True)
    source.add_argument("--source-engagement", type=Path)
    source.add_argument("--source-kind", choices=["synthetic", "public"])
    attest.add_argument("--source-resolver", type=Path)
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if args.command == "attest":
        try:
            provenance = attest_casebook(
                args.casebook,
                source_kind=args.source_kind,
                source_engagement=args.source_engagement,
                source_resolver=args.source_resolver,
            )
        except Exception:
            print("REJECTED: casebook source provenance could not be verified.", file=sys.stderr)
            return 1
        print(json.dumps({"status": "attested", "source_kind": provenance["source_kind"]}))
        return 0
    if args.query is not None:
        print(
            json.dumps(
                retrieve(
                    args.query,
                    args.top_k,
                    casebooks=args.casebooks,
                    source_resolver=args.source_resolver,
                ),
                indent=2,
            )
        )
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
