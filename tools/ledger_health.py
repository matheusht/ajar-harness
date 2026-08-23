"""Read-only, non-raising health probe for an engagement ledger.

The reducer remains the authority for whether a ledger is usable.  This module
only translates expected reduction/read failures into a status that callers can
inspect; it does not repair, relax, or bypass any reducer invariant.
"""

from __future__ import annotations

import stat
from pathlib import Path
from typing import Any

from engagement_records import RecordError
from engagement_state import reduce_engagement


_UNREADABLE_RECORD_CODES = frozenset(
    {
        "governed_file_changed_during_read",
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


def probe_ledger_health(engagement: Path) -> dict[str, Any]:
    """Return ``healthy``, ``invalid``, or ``unreadable`` without mutating state.

    A handled unhealthy result is a successful probe, so callers receive the
    reducer's stable error code in the payload instead of an exception.
    """

    engagement = engagement.absolute()
    try:
        engagement_stat = engagement.lstat()
    except OSError as exc:
        return _unreadable(engagement, code="ledger_unreadable", exception=exc)
    if stat.S_ISLNK(engagement_stat.st_mode) or not stat.S_ISDIR(engagement_stat.st_mode):
        return _unreadable(engagement, code="unsafe_engagement_path")
    try:
        snapshot = reduce_engagement(engagement)
    except RecordError as exc:
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
        return _unreadable(engagement, code="ledger_unreadable", exception=exc)
    return {
        "engagement_id": snapshot["engagement_id"],
        "status": "healthy",
        "reducible": True,
        "event_count": snapshot["event_count"],
        "ledger_hash": snapshot["ledger_hash"],
        "error": None,
    }
