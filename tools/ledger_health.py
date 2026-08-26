"""Read-only, non-raising health probe for an engagement ledger.

The reducer remains the authority for whether a ledger is usable.  This module
only translates expected reduction/read failures into a status that callers can
inspect; it does not repair, relax, or bypass any reducer invariant.
"""

from __future__ import annotations

import os
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from engagement_records import RecordError
from engagement_state import _open_absolute_directory, bound_engagement_lock, reduce_engagement
from engagement_quarantine import inspect_quarantine


_UNREADABLE_RECORD_CODES = frozenset(
    {
        "governed_file_changed_during_read",
        "engagement_coordination_changed",
        "engagement_source_changed",
        "unsafe_governed_path",
        "unsafe_ledger_path",
    }
)


def _unreadable(engagement: Path, *, code: str, exception: OSError | None = None) -> dict[str, Any]:
    details = [] if exception is None else [{"errno": exception.errno, "exception_type": type(exception).__name__}]
    return {
        "engagement_id": engagement.name,
        "status": "unreadable",
        "reducible": False,
        "event_count": None,
        "ledger_hash": None,
        "error": {"code": code, "message": "engagement ledger could not be read", "details": details},
    }


def _quarantined(engagement: Path) -> dict[str, Any]:
    return {
        "engagement_id": engagement.name,
        "status": "quarantined",
        "reducible": False,
        "event_count": None,
        "ledger_hash": None,
        "error": {
            "code": "engagement_quarantined",
            "message": "engagement evidence is quarantined",
            "details": [],
        },
    }


def _named_quarantined(engagement: Path) -> bool:
    try:
        entry = engagement.lstat()
    except OSError:
        return False
    return bool(
        not stat.S_ISLNK(entry.st_mode)
        and stat.S_ISDIR(entry.st_mode)
        and inspect_quarantine(engagement)["quarantined"]
    )


@contextmanager
def _bound_health_source(engagement: Path):
    """Bind health reduction to one root inode without creating coordination state."""

    logical = Path(os.path.abspath(engagement))
    caller_bound = (
        len(logical.parts) == 4
        and logical.parts[1:3] == ("dev", "fd")
        and logical.parts[3].isdigit()
    )
    root_fd = _open_absolute_directory(logical)
    bound = Path(f"/dev/fd/{root_fd}")
    opened = os.fstat(root_fd)

    def require_public_identity() -> None:
        try:
            named = os.stat(logical, follow_symlinks=False)
        except OSError as exc:
            raise RecordError("engagement_source_changed", "health source changed") from exc
        if (
            stat.S_ISLNK(named.st_mode)
            or not stat.S_ISDIR(named.st_mode)
            or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
        ):
            raise RecordError("engagement_source_changed", "health source changed")

    try:
        if inspect_quarantine(bound)["quarantined"]:
            raise RecordError("engagement_quarantined", "engagement evidence is quarantined")
        if caller_bound:
            # Exact descriptor aliases are transaction capabilities supplied by a caller that
            # already owns the public-name check and (where governed) the kernel lock. Re-locking
            # a separately opened lock FD can self-deadlock; reopening a public path would discard
            # the binding the caller deliberately established.
            yield bound
            if inspect_quarantine(bound)["quarantined"]:
                raise RecordError("engagement_quarantined", "engagement evidence is quarantined")
            return
        require_public_identity()
        try:
            lock_entry = os.stat(".record-kernel.lock", dir_fd=root_fd, follow_symlinks=False)
        except FileNotFoundError:
            lock_entry = None
        if lock_entry is not None and (
            stat.S_ISLNK(lock_entry.st_mode) or not stat.S_ISREG(lock_entry.st_mode)
        ):
            raise RecordError("unsafe_governed_path", "health coordination entry is unsafe")

        if lock_entry is not None:
            with bound_engagement_lock(root_fd, create=False) as locked:
                yield locked
                if inspect_quarantine(locked)["quarantined"]:
                    raise RecordError("engagement_quarantined", "engagement evidence is quarantined")
                current_lock = os.stat(
                    ".record-kernel.lock", dir_fd=root_fd, follow_symlinks=False
                )
                if (lock_entry.st_dev, lock_entry.st_ino) != (
                    current_lock.st_dev,
                    current_lock.st_ino,
                ):
                    raise RecordError("engagement_source_changed", "health coordination changed")
                require_public_identity()
            return

        # Legacy status probing is intentionally read-only: no kernel lock is manufactured.
        yield bound
        if inspect_quarantine(bound)["quarantined"]:
            raise RecordError("engagement_quarantined", "engagement evidence is quarantined")
        try:
            os.stat(".record-kernel.lock", dir_fd=root_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise RecordError("engagement_coordination_changed", "health coordination changed")
        require_public_identity()
    finally:
        os.close(root_fd)


def probe_ledger_health(engagement: Path) -> dict[str, Any]:
    """Return ``healthy``, ``quarantined``, ``invalid``, or ``unreadable`` without mutation.

    A handled unhealthy result is a successful probe, so callers receive the
    reducer's stable error code in the payload instead of an exception.
    """

    engagement = engagement.absolute()
    try:
        with _bound_health_source(engagement) as bound:
            snapshot = reduce_engagement(bound)
    except RecordError as exc:
        if exc.code == "engagement_quarantined" or _named_quarantined(engagement):
            return _quarantined(engagement)
        status = "unreadable" if exc.code in _UNREADABLE_RECORD_CODES else "invalid"
        return {
            "engagement_id": engagement.name,
            "status": status,
            "reducible": False,
            "event_count": None,
            "ledger_hash": None,
            "error": {
                "code": exc.code,
                "message": "engagement ledger could not be read" if status == "unreadable" else "engagement ledger could not be reduced",
                "details": [],
            },
        }
    except OSError as exc:
        if _named_quarantined(engagement):
            return _quarantined(engagement)
        return _unreadable(engagement, code="ledger_unreadable", exception=exc)
    return {
        "engagement_id": snapshot["engagement_id"],
        "status": "healthy",
        "reducible": True,
        "event_count": snapshot["event_count"],
        "ledger_hash": snapshot["ledger_hash"],
        "error": None,
    }
