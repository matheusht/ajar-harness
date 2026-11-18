"""Fail-closed, target-local engagement quarantine marker handling.

The marker is deliberately denial-only metadata outside the append-only ledgers.  Its
presence prevents reducers and mutation paths from treating the engagement as sound.  A
malformed marker is still a quarantine signal; parsing it is never a reason to fail open.

This module has no dependency on the record kernel so corpus tools can ask the narrow
question "is this engagement quarantined?" without opening an untrusted ledger.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
import fcntl
from datetime import datetime
from pathlib import Path
from typing import Any


MARKER_PARTS = ("legacy", "quarantine", "ledger-quarantined.json")
MARKER_RELATIVE = "/".join(MARKER_PARTS)
QUARANTINE_REASONS = frozenset(
    {
        "ledger-integrity-unresolved",
        "legacy-record-untrusted",
        "provenance-unresolved",
        "operator-integrity-review",
        "underlying-ledger-verified-healthy",
    }
)
_MARKER_KEYS = {
    "schema_version",
    "status",
    "operator_id",
    "reason",
    "recorded_at",
    "authority_challenge_digest",
    "record_fingerprint",
}
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_OPERATOR = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_MAX_MARKER_BYTES = 64 * 1024


def _duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _open_directory(path: Path) -> int:
    absolute = Path(os.path.abspath(path))
    if len(absolute.parts) == 4 and absolute.parts[1:3] == ("dev", "fd") and absolute.parts[3].isdigit():
        duplicate = os.dup(int(absolute.parts[3]))
        if not stat.S_ISDIR(os.fstat(duplicate).st_mode):
            os.close(duplicate)
            raise OSError("terminal directory is unsafe")
        return duplicate
    try:
        terminal = absolute.lstat()
        if stat.S_ISLNK(terminal.st_mode) or not stat.S_ISDIR(terminal.st_mode):
            raise OSError("terminal directory is unsafe")
        resolved_parent = absolute.parent.resolve(strict=True)
    except OSError:
        raise
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open("/", flags)
    try:
        for part in (*resolved_parent.parts[1:], absolute.name):
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except Exception:
        os.close(fd)
        raise


def _open_marker_parent(engagement: Path, *, create: bool) -> int:
    fd = _open_directory(engagement)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        for part in MARKER_PARTS[:-1]:
            if create:
                try:
                    os.mkdir(part, 0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except Exception:
        os.close(fd)
        raise


def _entry_identity(value: os.stat_result, component: int) -> dict[str, int]:
    return {
        "device": value.st_dev,
        "inode": value.st_ino,
        "size": value.st_size,
        "mtime_ns": value.st_mtime_ns,
        "mode": value.st_mode,
        "component": component,
    }


def _locate_marker_entry(engagement: Path) -> dict[str, int] | None:
    """Locate the leaf or first unsafe parent component without following any entry."""

    fd = _open_directory(engagement)
    try:
        for component, part in enumerate(MARKER_PARTS):
            try:
                entry = os.stat(part, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                return None
            identity = _entry_identity(entry, component)
            if component == len(MARKER_PARTS) - 1 or not stat.S_ISDIR(entry.st_mode):
                return identity
            child = os.open(
                part,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=fd,
            )
            os.close(fd)
            fd = child
    finally:
        os.close(fd)
    return None


def _read_marker(engagement: Path) -> tuple[bytes, dict[str, int]]:
    parent_fd = _open_marker_parent(engagement, create=False)
    try:
        fd = os.open(MARKER_PARTS[-1], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_size > _MAX_MARKER_BYTES:
                raise ValueError("marker is not a bounded regular file")
            chunks: list[bytes] = []
            remaining = _MAX_MARKER_BYTES + 1
            while remaining > 0:
                chunk = os.read(fd, min(1024 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            data = b"".join(chunks)
            after = os.fstat(fd)
            identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            if identity != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
                raise ValueError("marker changed during read")
            if len(data) > _MAX_MARKER_BYTES:
                raise ValueError("marker is too large")
            return data, {
                "device": before.st_dev,
                "inode": before.st_ino,
                "size": before.st_size,
                "mtime_ns": before.st_mtime_ns,
                "mode": before.st_mode,
            }
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)


def _valid_marker(value: Any) -> bool:
    if not isinstance(value, dict) or set(value) != _MARKER_KEYS:
        return False
    if value.get("schema_version") != 1 or value.get("status") != "quarantined":
        return False
    if not isinstance(value.get("operator_id"), str) or not _OPERATOR.fullmatch(value["operator_id"]):
        return False
    if value.get("reason") not in QUARANTINE_REASONS:
        return False
    if not isinstance(value.get("recorded_at"), str):
        return False
    try:
        timestamp = datetime.fromisoformat(value["recorded_at"].replace("Z", "+00:00"))
    except ValueError:
        return False
    if timestamp.tzinfo is None:
        return False
    return bool(
        isinstance(value.get("authority_challenge_digest"), str)
        and _DIGEST.fullmatch(value["authority_challenge_digest"])
        and isinstance(value.get("record_fingerprint"), str)
        and _DIGEST.fullmatch(value["record_fingerprint"])
    )


def inspect_quarantine(engagement: Path) -> dict[str, Any]:
    """Return a sanitized marker state; any present-but-unusable entry fails closed."""

    try:
        entry_identity = _locate_marker_entry(engagement)
    except Exception:
        return {"quarantined": True, "marker_status": "malformed", "fingerprint": None, "identity": None}
    if entry_identity is None:
        return {"quarantined": False, "marker_status": "absent", "fingerprint": None, "identity": None}
    if entry_identity["component"] != len(MARKER_PARTS) - 1:
        identity_bytes = json.dumps(entry_identity, sort_keys=True, separators=(",", ":")).encode("ascii")
        return {
            "quarantined": True,
            "marker_status": "malformed",
            "fingerprint": "sha256:" + hashlib.sha256(identity_bytes).hexdigest(),
            "identity": entry_identity,
        }
    if not stat.S_ISREG(entry_identity["mode"]):
        identity_bytes = json.dumps(entry_identity, sort_keys=True, separators=(",", ":")).encode("ascii")
        return {
            "quarantined": True,
            "marker_status": "malformed",
            "fingerprint": "sha256:" + hashlib.sha256(identity_bytes).hexdigest(),
            "identity": entry_identity,
        }
    try:
        data, identity = _read_marker(engagement)
    except Exception:
        identity_bytes = json.dumps(entry_identity, sort_keys=True, separators=(",", ":")).encode("ascii")
        return {
            "quarantined": True,
            "marker_status": "malformed",
            "fingerprint": "sha256:" + hashlib.sha256(identity_bytes).hexdigest(),
            "identity": entry_identity,
        }
    identity["component"] = len(MARKER_PARTS) - 1
    if any(identity[key] != entry_identity[key] for key in entry_identity):
        identity_bytes = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("ascii")
        return {
            "quarantined": True,
            "marker_status": "malformed",
            "fingerprint": "sha256:" + hashlib.sha256(identity_bytes).hexdigest(),
            "identity": identity,
        }
    fingerprint = "sha256:" + hashlib.sha256(data).hexdigest()
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_duplicates)
        canonical = (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
        valid = data == canonical and _valid_marker(value)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        valid = False
    return {
        "quarantined": True,
        "marker_status": "valid" if valid else "malformed",
        "fingerprint": fingerprint,
        "identity": identity,
    }


def is_quarantined(engagement: Path) -> bool:
    return bool(inspect_quarantine(engagement)["quarantined"])


def _marker_entry_present(engagement: Path) -> bool:
    """Detect the exact marker entry without trusting mutable ``scope.md`` bytes.

    This deliberately does not call ``inspect_quarantine`` on every filesystem ancestor: platform
    aliases such as macOS ``/var`` are symlinks and must not make every temporary path look marked.
    Instead it follows no marker-path component and only returns true once an exact leaf exists.
    """

    current = engagement
    try:
        terminal = current.lstat()
        if stat.S_ISLNK(terminal.st_mode) or not stat.S_ISDIR(terminal.st_mode):
            return False
        for index, component in enumerate(MARKER_PARTS):
            current = current / component
            entry = current.lstat()
            if index == len(MARKER_PARTS) - 1:
                return True
            if stat.S_ISLNK(entry.st_mode) or not stat.S_ISDIR(entry.st_mode):
                # ``inspect_quarantine`` treats the first unsafe marker-parent entry as
                # malformed quarantine. Ancestor and offline I/O gates must make the same
                # denial-only decision even when ``scope.md`` is missing or unusable.
                return True
    except FileNotFoundError:
        return False
    except OSError:
        # An unreadable existing marker path is denial-only evidence, never an absence proof.
        return True
    return False


def quarantined_ancestor(path: Path) -> bool:
    """True when ``path`` or any existing parent carries the exact marker."""

    absolute = Path(os.path.abspath(path))
    candidates = [absolute]
    try:
        resolved = absolute.resolve(strict=False)
    except (OSError, RuntimeError):
        resolved = absolute
    if resolved != absolute:
        candidates.append(resolved)
    for value in candidates:
        candidate = value if value.is_dir() else value.parent
        for parent in (candidate, *candidate.parents):
            if _marker_entry_present(parent):
                return True
    return False


def targets_quarantine_control(path: Path) -> bool:
    """True for an engagement's exact marker or either marker-parent directory.

    Offline output commands must not be able to synthesize even a malformed unsigned marker or
    replace its control directories. These exact suffixes are globally reserved: mutable or
    missing ``scope.md`` bytes cannot be allowed to turn the denial-only control back into an
    ordinary output path.
    """

    absolute = Path(os.path.abspath(path))
    for length in range(1, len(MARKER_PARTS) + 1):
        if absolute.parts[-length:] != MARKER_PARTS[:length]:
            continue
        return True
    return False


def _governed_ancestor(path: Path) -> bool:
    absolute = Path(os.path.abspath(path))
    candidates = [absolute]
    try:
        resolved = absolute.resolve(strict=False)
    except (OSError, RuntimeError):
        resolved = absolute
    if resolved != absolute:
        candidates.append(resolved)
    for value in candidates:
        parent = value if value.is_dir() else value.parent
        for candidate in (parent, *parent.parents):
            try:
                scope = (candidate / "scope.md").lstat()
            except OSError:
                continue
            if stat.S_ISREG(scope.st_mode) and not stat.S_ISLNK(scope.st_mode):
                return True
    return False


def require_safe_offline_output(path: Path) -> None:
    """Reject an offline output sink that would cross the quarantine control boundary."""

    if quarantined_ancestor(path) or targets_quarantine_control(path) or _governed_ancestor(path):
        raise ValueError("offline output destination is quarantined or reserved")


def require_safe_offline_input(path: Path) -> None:
    """Reject engagement-governed evidence at an offline portable-input seam."""

    if quarantined_ancestor(path) or targets_quarantine_control(path) or _governed_ancestor(path):
        raise ValueError("offline input source is quarantined or governed")


def _current_directory_path(fd: int) -> Path | None:
    """Return the current path of a bound directory where the host exposes one."""

    getpath = getattr(fcntl, "F_GETPATH", None)
    if getpath is not None:
        try:
            value = fcntl.fcntl(fd, getpath, b"\0" * 1024)
            if isinstance(value, bytes):
                text = value.split(b"\0", 1)[0].decode("utf-8")
                if text:
                    return Path(text)
        except (OSError, UnicodeDecodeError):
            return None
    proc_link = Path(f"/proc/self/fd/{fd}")
    try:
        return Path(os.readlink(proc_link))
    except OSError:
        return None


def _require_bound_parent_safe(
    parent_fd: int,
    canonical_parent: Path,
    leaf_name: str,
    *,
    output: bool,
) -> None:
    """Require both the canonical name and bound inode to remain outside governed evidence."""

    try:
        opened = os.fstat(parent_fd)
        named = os.stat(canonical_parent, follow_symlinks=False)
    except OSError as exc:
        raise ValueError("offline boundary parent changed") from exc
    if (
        not stat.S_ISDIR(opened.st_mode)
        or stat.S_ISLNK(named.st_mode)
        or not stat.S_ISDIR(named.st_mode)
        or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
    ):
        raise ValueError("offline boundary parent changed")
    current = _current_directory_path(parent_fd)
    if current is not None:
        try:
            current_identity = current.stat(follow_symlinks=False)
        except OSError as exc:
            raise ValueError("offline boundary parent changed") from exc
        if (
            stat.S_ISLNK(current_identity.st_mode)
            or not stat.S_ISDIR(current_identity.st_mode)
            or (opened.st_dev, opened.st_ino)
            != (current_identity.st_dev, current_identity.st_ino)
        ):
            raise ValueError("offline boundary parent changed")
        boundary = current / leaf_name
        (require_safe_offline_output if output else require_safe_offline_input)(boundary)


def read_safe_offline_file(path: Path) -> bytes:
    """Read a portable input through one safe, identity-bound parent directory."""

    absolute = Path(os.path.abspath(path))
    require_safe_offline_input(absolute)
    try:
        resolved = absolute.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError("offline input source is unavailable") from exc
    require_safe_offline_input(resolved)
    parent_fd = _open_directory(resolved.parent)
    try:
        _require_bound_parent_safe(
            parent_fd, resolved.parent, resolved.name, output=False
        )
        fd = os.open(
            resolved.name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd,
        )
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                raise ValueError("offline input source is not a regular file")
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
            ) != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            ):
                raise ValueError("offline input source changed during read")
        finally:
            os.close(fd)
        _require_bound_parent_safe(
            parent_fd, resolved.parent, resolved.name, output=False
        )
        try:
            final = absolute.resolve(strict=True)
            final_identity = final.stat(follow_symlinks=False)
        except (OSError, RuntimeError) as exc:
            raise ValueError("offline input source changed") from exc
        if final != resolved or (
            final_identity.st_dev,
            final_identity.st_ino,
            final_identity.st_size,
            final_identity.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise ValueError("offline input source changed")
        return b"".join(chunks)
    finally:
        os.close(parent_fd)


def read_safe_offline_tree(path: Path) -> dict[str, bytes]:
    """Snapshot a portable input directory through one identity-bound root FD."""

    absolute = Path(os.path.abspath(path))
    require_safe_offline_input(absolute)
    try:
        resolved = absolute.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError("offline input directory is unavailable") from exc
    require_safe_offline_input(resolved)
    root_fd = _open_directory(resolved)

    def snapshot(
        directory_fd: int,
        prefix: tuple[str, ...],
        canonical_directory: Path,
    ) -> dict[str, bytes]:
        _require_bound_parent_safe(
            directory_fd, canonical_directory, ".", output=False
        )
        directory_before = os.fstat(directory_fd)
        result: dict[str, bytes] = {}
        names = sorted(os.listdir(directory_fd))
        for name in names:
            if name in {".", ".."} or "/" in name:
                raise ValueError("offline input directory contains an unsafe entry")
            entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            relative = "/".join((*prefix, name))
            if stat.S_ISLNK(entry.st_mode):
                raise ValueError("offline input directory contains a symbolic link")
            if stat.S_ISDIR(entry.st_mode):
                child = os.open(
                    name,
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=directory_fd,
                )
                try:
                    result.update(
                        snapshot(
                            child,
                            (*prefix, name),
                            canonical_directory / name,
                        )
                    )
                finally:
                    os.close(child)
                continue
            if not stat.S_ISREG(entry.st_mode):
                raise ValueError("offline input directory contains a non-regular entry")
            fd = os.open(
                name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=directory_fd,
            )
            try:
                before = os.fstat(fd)
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
                ) != (
                    after.st_dev,
                    after.st_ino,
                    after.st_size,
                    after.st_mtime_ns,
                ):
                    raise ValueError("offline input directory changed during snapshot")
            finally:
                os.close(fd)
            result[relative] = b"".join(chunks)
        directory_after = os.fstat(directory_fd)
        if (
            directory_before.st_dev,
            directory_before.st_ino,
            directory_before.st_mtime_ns,
            directory_before.st_ctime_ns,
        ) != (
            directory_after.st_dev,
            directory_after.st_ino,
            directory_after.st_mtime_ns,
            directory_after.st_ctime_ns,
        ) or names != sorted(os.listdir(directory_fd)):
            raise ValueError("offline input directory changed during snapshot")
        _require_bound_parent_safe(
            directory_fd, canonical_directory, ".", output=False
        )
        return result

    try:
        _require_bound_parent_safe(root_fd, resolved, ".", output=False)
        result = snapshot(root_fd, (), resolved)
        _require_bound_parent_safe(root_fd, resolved, ".", output=False)
        try:
            final = absolute.resolve(strict=True)
            final_identity = final.stat(follow_symlinks=False)
            opened = os.fstat(root_fd)
        except (OSError, RuntimeError) as exc:
            raise ValueError("offline input directory changed") from exc
        if final != resolved or (
            final_identity.st_dev,
            final_identity.st_ino,
        ) != (opened.st_dev, opened.st_ino):
            raise ValueError("offline input directory changed")
        return result
    finally:
        os.close(root_fd)


def atomic_write_offline(path: Path, data: bytes, *, overwrite: bool = True) -> None:
    """Publish offline output without following a leaf or symlink-parent into governed evidence."""

    absolute = Path(os.path.abspath(path))
    require_safe_offline_output(absolute)
    if not absolute.parent.is_dir():
        raise ValueError("offline output parent must already exist")
    resolved_parent = absolute.parent.resolve(strict=True)
    destination = resolved_parent / absolute.name
    require_safe_offline_output(destination)
    parent_fd = _open_directory(resolved_parent)
    temporary = f".{absolute.name}.{os.getpid()}.{secrets.token_hex(8)}"
    backup = f".{absolute.name}.{os.getpid()}.{secrets.token_hex(8)}.previous"
    published = False
    backed_up = False
    try:
        _require_bound_parent_safe(
            parent_fd, resolved_parent, absolute.name, output=True
        )
        try:
            existing = os.stat(absolute.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        if existing is not None and (
            stat.S_ISLNK(existing.st_mode) or not stat.S_ISREG(existing.st_mode) or not overwrite
        ):
            raise ValueError("offline output leaf is unsafe or already exists")
        fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=parent_fd,
        )
        try:
            view = memoryview(data)
            written = 0
            while written < len(view):
                count = os.write(fd, view[written:])
                if count <= 0:
                    raise OSError("offline output write made no progress")
                written += count
            os.fsync(fd)
        finally:
            os.close(fd)
        _require_bound_parent_safe(
            parent_fd, resolved_parent, absolute.name, output=True
        )
        try:
            if existing is not None:
                os.rename(
                    absolute.name,
                    backup,
                    src_dir_fd=parent_fd,
                    dst_dir_fd=parent_fd,
                )
                backed_up = True
                _require_bound_parent_safe(
                    parent_fd, resolved_parent, absolute.name, output=True
                )
            os.replace(temporary, absolute.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            published = True
            _require_bound_parent_safe(
                parent_fd, resolved_parent, absolute.name, output=True
            )
            os.fsync(parent_fd)
            _require_bound_parent_safe(
                parent_fd, resolved_parent, absolute.name, output=True
            )
        except Exception:
            if published:
                try:
                    os.unlink(absolute.name, dir_fd=parent_fd)
                except FileNotFoundError:
                    pass
            if backed_up:
                os.rename(
                    backup,
                    absolute.name,
                    src_dir_fd=parent_fd,
                    dst_dir_fd=parent_fd,
                )
                backed_up = False
            os.fsync(parent_fd)
            raise
        if backed_up:
            os.unlink(backup, dir_fd=parent_fd)
            backed_up = False
            os.fsync(parent_fd)
    finally:
        try:
            os.unlink(temporary, dir_fd=parent_fd)
        except FileNotFoundError:
            pass
        if backed_up:
            try:
                os.rename(
                    backup,
                    absolute.name,
                    src_dir_fd=parent_fd,
                    dst_dir_fd=parent_fd,
                )
            except OSError:
                pass
        os.close(parent_fd)


def atomic_publish_offline_tree(path: Path, files: dict[str, bytes]) -> None:
    """Publish a new portable directory tree through one identity-bound parent FD."""

    if not files:
        raise ValueError("offline output tree must contain at least one file")
    normalized: dict[tuple[str, ...], bytes] = {}
    for relative, data in files.items():
        parts = Path(relative).parts
        if (
            not parts
            or Path(relative).is_absolute()
            or any(part in {"", ".", ".."} or "/" in part for part in parts)
            or not isinstance(data, bytes)
        ):
            raise ValueError("offline output tree entry is invalid")
        normalized[parts] = data
    absolute = Path(os.path.abspath(path))
    require_safe_offline_output(absolute)
    if not absolute.parent.is_dir():
        raise ValueError("offline output parent must already exist")
    resolved_parent = absolute.parent.resolve(strict=True)
    destination = resolved_parent / absolute.name
    require_safe_offline_output(destination)
    parent_fd = _open_directory(resolved_parent)
    temporary = f".{absolute.name}.{os.getpid()}.{secrets.token_hex(8)}.tree"
    published = False

    def remove_tree(directory_fd: int) -> None:
        for name in os.listdir(directory_fd):
            entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if stat.S_ISDIR(entry.st_mode) and not stat.S_ISLNK(entry.st_mode):
                child = os.open(
                    name,
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=directory_fd,
                )
                try:
                    remove_tree(child)
                finally:
                    os.close(child)
                os.rmdir(name, dir_fd=directory_fd)
            else:
                os.unlink(name, dir_fd=directory_fd)

    try:
        _require_bound_parent_safe(
            parent_fd, resolved_parent, absolute.name, output=True
        )
        try:
            os.stat(absolute.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ValueError("offline output tree already exists")
        os.mkdir(temporary, 0o700, dir_fd=parent_fd)
        tree_fd = os.open(
            temporary,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd,
        )
        try:
            for parts, data in sorted(normalized.items()):
                current = os.dup(tree_fd)
                try:
                    for component in parts[:-1]:
                        try:
                            os.mkdir(component, 0o700, dir_fd=current)
                        except FileExistsError:
                            pass
                        child = os.open(
                            component,
                            os.O_RDONLY
                            | getattr(os, "O_DIRECTORY", 0)
                            | getattr(os, "O_NOFOLLOW", 0),
                            dir_fd=current,
                        )
                        os.close(current)
                        current = child
                    fd = os.open(
                        parts[-1],
                        os.O_WRONLY
                        | os.O_CREAT
                        | os.O_EXCL
                        | getattr(os, "O_NOFOLLOW", 0),
                        0o600,
                        dir_fd=current,
                    )
                    try:
                        view = memoryview(data)
                        written = 0
                        while written < len(view):
                            count = os.write(fd, view[written:])
                            if count <= 0:
                                raise OSError("offline output tree write made no progress")
                            written += count
                        os.fsync(fd)
                    finally:
                        os.close(fd)
                    os.fsync(current)
                finally:
                    os.close(current)
            os.fsync(tree_fd)
        finally:
            os.close(tree_fd)
        _require_bound_parent_safe(
            parent_fd, resolved_parent, absolute.name, output=True
        )
        os.rename(
            temporary,
            absolute.name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        published = True
        try:
            _require_bound_parent_safe(
                parent_fd, resolved_parent, absolute.name, output=True
            )
            os.fsync(parent_fd)
            _require_bound_parent_safe(
                parent_fd, resolved_parent, absolute.name, output=True
            )
        except Exception:
            os.rename(
                absolute.name,
                temporary,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
            published = False
            raise
    finally:
        try:
            cleanup_stat = os.stat(temporary, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            cleanup_stat = None
        if cleanup_stat is not None:
            cleanup_fd = os.open(
                temporary,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=parent_fd,
            )
            try:
                remove_tree(cleanup_fd)
            finally:
                os.close(cleanup_fd)
            os.rmdir(temporary, dir_fd=parent_fd)
        os.close(parent_fd)


def canonical_marker(marker: dict[str, Any]) -> bytes:
    if not _valid_marker(marker):
        raise ValueError("invalid quarantine marker")
    return (json.dumps(marker, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def create_marker_exclusive(engagement: Path, marker: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    """Create without overwrite.  An exact valid retry is idempotent."""

    data = canonical_marker(marker)
    existing = inspect_quarantine(engagement)
    if existing["quarantined"]:
        if existing["marker_status"] == "valid" and existing["fingerprint"] == "sha256:" + hashlib.sha256(data).hexdigest():
            return False, existing
        raise FileExistsError("quarantine marker already exists")
    parent_fd = _open_marker_parent(engagement, create=True)
    temporary = f".ledger-quarantined.{os.getpid()}.{secrets.token_hex(8)}"
    try:
        fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=parent_fd,
        )
        try:
            view = memoryview(data)
            written = 0
            while written < len(view):
                count = os.write(fd, view[written:])
                if count <= 0:
                    raise OSError("marker write made no progress")
                written += count
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            os.link(
                temporary,
                MARKER_PARTS[-1],
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
                follow_symlinks=False,
            )
            created = True
        except FileExistsError:
            raced = inspect_quarantine(engagement)
            if raced["marker_status"] == "valid" and raced["fingerprint"] == "sha256:" + hashlib.sha256(data).hexdigest():
                created = False
            else:
                raise
        os.fsync(parent_fd)
    finally:
        try:
            os.unlink(temporary, dir_fd=parent_fd)
        except FileNotFoundError:
            pass
        os.close(parent_fd)
    state = inspect_quarantine(engagement)
    if state["marker_status"] != "valid":
        raise OSError("marker verification failed")
    return created, state


def clear_marker_exact(engagement: Path, expected: dict[str, Any]) -> None:
    """Remove only the exact entry inspected under the caller's engagement lock.

    Regular files and symlinks are unlinked without following. A directory-shaped malformed
    marker is renamed to a non-marker recovery name so a non-empty directory is recoverable without
    recursive deletion or loss of its bytes.
    """

    current = inspect_quarantine(engagement)
    if current.get("fingerprint") is None or current.get("identity") is None:
        raise ValueError("marker is not an exactly clearable entry")
    if current["fingerprint"] != expected.get("fingerprint") or current["identity"] != expected.get("identity"):
        raise ValueError("marker changed before clear")
    identity = current["identity"]
    component = identity.get("component")
    if not isinstance(component, int) or component not in range(len(MARKER_PARTS)):
        raise ValueError("marker component identity is invalid")
    parent_fd = _open_directory(engagement)
    try:
        for part in MARKER_PARTS[:component]:
            child = os.open(part, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd)
            os.close(parent_fd)
            parent_fd = child
        entry_name = MARKER_PARTS[component]
        before = os.stat(entry_name, dir_fd=parent_fd, follow_symlinks=False)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_mode) != (
            identity["device"], identity["inode"], identity["size"], identity["mtime_ns"], identity["mode"]
        ):
            raise ValueError("marker changed before clear")
        if component < len(MARKER_PARTS) - 1 or stat.S_ISDIR(before.st_mode):
            recovery_name = (
                f".ledger-quarantined.cleared-{current['fingerprint'][-16:]}"
                if component == len(MARKER_PARTS) - 1
                else f".{entry_name}.quarantine-cleared-{current['fingerprint'][-16:]}"
            )
            try:
                os.stat(recovery_name, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise ValueError("marker recovery entry already exists")
            os.rename(entry_name, recovery_name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        else:
            os.unlink(entry_name, dir_fd=parent_fd)
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)
