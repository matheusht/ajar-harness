"""Flat `.ajar/` JSONL schemas and Diagonal Kill Matrix primitives (`0` SQLite tables)."""

from __future__ import annotations

import fcntl
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

KILL_ROWS = ("reachability", "controllability", "boundary_validity", "impact_and_patch")
KILL_COLS = ("static_code", "clean_replay", "shipped_profile")
DIAGONAL_REQUIRED = (
    "reachability:static_code",
    "controllability:clean_replay",
    "boundary_validity:shipped_profile",
    "impact_and_patch:clean_replay",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ajar_dir(repo: Path) -> Path:
    root = repo.resolve() / ".ajar"
    (root / "workers").mkdir(parents=True, exist_ok=True)
    return root


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, sort_keys=True) + "\n"
    with path.open("a", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            fh.write(line)
            fh.flush()
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_SH)
        try:
            return [json.loads(ln) for ln in fh if ln.strip()]
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(r, sort_keys=True) + "\n" for r in records)
    with path.open("w", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            fh.write(payload)
            fh.flush()
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


@dataclass
class Primitive:
    id: str
    kind: str  # "CAN" or "WISH"
    capability: str
    seam_tag: str
    location: str
    preconditions: list[str] = field(default_factory=list)
    bridge_hint: str = ""
    repro_cmd: str = ""
    worker_id: str = "worker-0"
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ChainCandidate:
    id: str
    can_id: str
    wish_id: str
    bridge_feature: str
    seam_tag: str
    e2e_repro_script: str = ""
    build_profile: str = "upstream"
    status: str = "CANDIDATE"  # CANDIDATE | PROVED | KILLED
    notes: str = ""
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Finding:
    id: str
    title: str
    severity: str
    category: str  # "advisory" | "hardening" (D7 closing Q3)
    lens: str
    entry_to_sink: list[str]
    sink_symbol: str
    build_profile: str = "upstream"
    repro_script: str = ""
    patch_diff: str = ""
    root_cause: str = ""
    impact: str = ""
    red_rc: int = 0
    green_rc: int = -1
    kill_matrix: dict[str, str] = field(default_factory=dict)
    critic_verdict: str = "PENDING"
    status: str = "CANDIDATE"
    withdrawn: bool = False
    notes: str = ""
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_kill_matrix(matrix: dict[str, str]) -> tuple[bool, list[str]]:
    """Enforce the 4x3 Diagonal Kill Matrix: zero FALSIFIED cells and all 4 diagonal cells VERIFIED."""
    reasons: list[str] = []
    for cell, state in sorted(matrix.items()):
        if state.upper().startswith("FALSIFIED"):
            reasons.append(f"falsified:{cell}={state}")
    for req in DIAGONAL_REQUIRED:
        if matrix.get(req) != "VERIFIED":
            reasons.append(f"unverified_diagonal:{req}={matrix.get(req, 'MISSING')}")
    return (len(reasons) == 0, reasons)
