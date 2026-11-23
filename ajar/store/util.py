"""Core SQLite connection, path-safety, event-logging, and salience helpers for Ajar."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import secrets
import sqlite3
import stat
from datetime import datetime, timezone
from typing import Any, Sequence

from ajar import EXIT_USER_ERROR
from ajar.domain.models import AjarError
from ajar.redact import scrub_text
from ajar.store.migrations import (
    SCHEMA_SQL,
    _ensure_v31_schema,
    _ensure_v32_schema,
    _ensure_v33_schema,
    _ensure_v34_schema,
    _ensure_v322_schema,
)
from ajar.store.tx import CURRENT_SCHEMA_VERSION

PRIORITY_BASE_SALIENCE: dict[str, int] = {
    "critical": 80,
    "high": 60,
    "medium": 40,
    "low": 20,
}

KIND_SALIENCE_FLOORS: dict[str, int] = {
    "reproduce": 95,
    "falsify": 92,
    "chain": 86,
    "instrument": 85,
    "escalate": 82,
    "bridge": 78,
}


def compute_harness_code_sha256(ajar_pkg_dir: pathlib.Path | None = None) -> str:
    """Compute a deterministic SHA-256 digest over all `ajar/**/*.py` engine files."""
    pkg = ajar_pkg_dir or pathlib.Path(__file__).resolve().parents[1]
    h = hashlib.sha256()
    for py_path in sorted(pkg.rglob("*.py")):
        if py_path.is_symlink() or "__pycache__" in py_path.parts:
            continue
        rel = py_path.relative_to(pkg).as_posix()
        h.update(rel.encode("utf-8") + b"\x00")
        h.update(py_path.read_bytes() + b"\x00")
    return h.hexdigest()


def compute_lead_ev_formula(
    *,
    impact_score: float,
    plausibility_score: float,
    chainability_score: float,
    effort_cost: float,
    voter_count: int = 1,
) -> float:
    """Compute bounded Expected-Value lead score (`0..100`) from multi-agent `1..10` votes."""
    weighted_gain = (
        (0.35 * float(impact_score))
        + (0.35 * float(chainability_score))
        + (0.30 * float(plausibility_score))
    )
    cost_divisor = 1.0 + (0.08 * max(0.0, float(effort_cost) - 1.0))
    quorum_bonus = 4.0 * float(min(max(0, int(voter_count) - 1), 3))
    raw = (10.0 * (weighted_gain / cost_divisor)) + quorum_bonus
    return round(max(1.0, min(100.0, raw)), 2)


def parse_tag_list(raw: str | Sequence[str] | None) -> list[str]:
    """Normalize comma-separated or sequence tag inputs into sorted unique `ns:name` strings."""
    if raw is None:
        return []
    items: list[str] = []
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return []
        if s.startswith("["):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    items = [str(x) for x in parsed]
                else:
                    items = [s]
            except json.JSONDecodeError:
                items = s.split(",")
        else:
            items = s.split(",")
    else:
        for entry in raw:
            items.extend(str(entry).split(","))

    cleaned: set[str] = set()
    for item in items:
        tok = re.sub(r"[^A-Za-z0-9_:./-]+", "", item.strip().lower())
        if tok:
            cleaned.add(tok[:64])
    return sorted(cleaned)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(4)}"


def get_ajar_home(explicit_home: pathlib.Path | str | None = None) -> pathlib.Path:
    raw = explicit_home or os.environ.get("AJAR_HOME") or (pathlib.Path.home() / ".ajar")
    return pathlib.Path(raw).expanduser()


def run_dir_for(run_id: str, ajar_home: pathlib.Path | str | None = None) -> pathlib.Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,79}", run_id):
        raise AjarError(f"Invalid run_id {run_id!r}.", EXIT_USER_ERROR)
    return get_ajar_home(ajar_home) / "runs" / run_id


def _assert_no_symlink_components(base_dir: pathlib.Path, target_path: pathlib.Path) -> None:
    """Reject symlink traversal anywhere under `base_dir` (`O_NOFOLLOW` equivalent)."""
    if base_dir.is_symlink():
        raise AjarError(f"Refusing symlinked AJAR_HOME: {base_dir}", EXIT_USER_ERROR)
    cur = base_dir
    try:
        rel_parts = target_path.relative_to(base_dir).parts
    except ValueError:
        if target_path.is_symlink():
            raise AjarError(f"Refusing symlinked database path: {target_path}", EXIT_USER_ERROR) from None
        return
    for part in rel_parts:
        cur = cur / part
        if cur.exists() or cur.is_symlink():
            st = os.lstat(cur)
            if stat.S_ISLNK(st.st_mode):
                raise AjarError(f"Refusing symlink component in run store: {cur}", EXIT_USER_ERROR)
            if cur == target_path and hasattr(os, "O_NOFOLLOW"):
                fd = os.open(str(cur), os.O_RDONLY | os.O_NOFOLLOW)
                os.close(fd)


def resolve_run_id(
    explicit_run_id: str | None = None,
    *,
    cwd: pathlib.Path | None = None,
    ajar_home: pathlib.Path | str | None = None,
) -> str:
    if explicit_run_id:
        return explicit_run_id.strip()
    env_id = os.environ.get("AJAR_RUN_ID", "").strip()
    if env_id:
        return env_id
    work = cwd or pathlib.Path.cwd()
    for candidate_dir in (work, *work.parents):
        marker = candidate_dir / ".ajar-run-id"
        if marker.is_file() and not marker.is_symlink():
            val = marker.read_text(encoding="utf-8").strip()
            if val:
                return val
    cur_file = get_ajar_home(ajar_home) / "current_run"
    if cur_file.is_file() and not cur_file.is_symlink():
        val = cur_file.read_text(encoding="utf-8").strip()
        if val:
            return val
    raise AjarError(
        "No active run ID found. Pass --run <id>, set AJAR_RUN_ID, or run `ajar init <target>`.",
        EXIT_USER_ERROR,
    )


def open_run_db(
    run_id_or_path: str | pathlib.Path,
    *,
    create: bool = False,
    ajar_home: pathlib.Path | str | None = None,
) -> sqlite3.Connection:
    home = get_ajar_home(ajar_home)
    p = pathlib.Path(run_id_or_path)
    if p.suffix == ".db" or "/" in str(run_id_or_path):
        db_path = p
    else:
        db_path = run_dir_for(str(run_id_or_path), home) / "run.db"

    if create:
        home.mkdir(parents=True, exist_ok=True)
        _assert_no_symlink_components(home, db_path.parent)
        db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _assert_no_symlink_components(home, db_path)

    if not create and not db_path.is_file():
        raise AjarError(f"Run database does not exist: {db_path}", EXIT_USER_ERROR)

    existed_nonempty = db_path.is_file() and db_path.stat().st_size > 0
    conn = sqlite3.connect(str(db_path), timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=30000;")
    if create and not existed_nonempty:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.executescript(SCHEMA_SQL)
        conn.execute(f"PRAGMA user_version={CURRENT_SCHEMA_VERSION};")
    else:
        ver_row = conn.execute("PRAGMA user_version;").fetchone()
        schema_ver = int(ver_row[0]) if ver_row is not None else 0
        if schema_ver < CURRENT_SCHEMA_VERSION:
            conn.execute("PRAGMA journal_mode=WAL;")
            if create:
                conn.executescript(SCHEMA_SQL)
            _ensure_v31_schema(conn)
            _ensure_v32_schema(conn)
            _ensure_v322_schema(conn)
            _ensure_v33_schema(conn)
            _ensure_v34_schema(conn)
            conn.execute(f"PRAGMA user_version={CURRENT_SCHEMA_VERSION};")
    return conn


def log_event(
    conn: sqlite3.Connection,
    actor: str,
    action: str,
    entity_id: str = "",
    payload: dict[str, Any] | None = None,
) -> int:
    clean_payload = scrub_text(json.dumps(payload or {}, sort_keys=True))
    cur = conn.execute(
        "INSERT INTO events(ts, actor, action, entity_id, payload_json) VALUES (?, ?, ?, ?, ?)",
        (utc_now_iso(), scrub_text(actor), action, entity_id, clean_payload),
    )
    return int(cur.lastrowid or 0)


def normalize_mechanism_key(mechanism: str) -> str:
    tokens = re.findall(r"[a-z0-9_]+", mechanism.lower())
    stop = {"the", "a", "an", "in", "on", "to", "of", "at", "by", "with", "via", "when", "is", "are"}
    filtered = [t for t in tokens if t not in stop]
    return " ".join(filtered[:16])


def infer_subsystem(locus: str) -> str:
    path_part = locus.split(":", 1)[0].strip().lstrip("./")
    parts = [p for p in path_part.split("/") if p]
    if len(parts) >= 2:
        return "/".join(parts[:2])
    return parts[0] if parts else "root"


def compute_commitment_hash(target_sha256: str, goal: str, stopping_criterion: str, created_at: str) -> str:
    canonical = json.dumps(
        {
            "created_at": created_at,
            "goal": goal,
            "schema": "ajar-research-ledger/1",
            "stopping_criterion": stopping_criterion,
            "target_sha256": target_sha256,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def compute_root_plateau_throttles(
    conn: sqlite3.Connection,
    *,
    max_post_repro_attempts: int = 2,
) -> dict[str, dict[str, Any]]:
    """Identify already-reproduced root files spinning in diminishing-returns corroboration/patch loops."""
    has_findings = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='findings'"
    ).fetchone()
    if not has_findings:
        return {}

    root_first_ts: dict[str, str] = {}
    root_findings: dict[str, list[str]] = {}
    root_has_jewel: set[str] = set()
    for f in conn.execute("SELECT finding_id, locus, realism_tier, created_at FROM findings ORDER BY created_at ASC").fetchall():
        rfile = str(f["locus"] or "").split(":", 1)[0].strip().lstrip("./")
        if not rfile:
            continue
        ts = str(f["created_at"] or "")
        if rfile not in root_first_ts or (ts and ts < root_first_ts[rfile]):
            root_first_ts[rfile] = ts
        root_findings.setdefault(rfile, []).append(str(f["finding_id"]))
        if str(f["realism_tier"] or "") == "crown_jewel":
            root_has_jewel.add(rfile)

    if not root_first_ts:
        return {}

    ready_files: set[str] = set()
    has_doors = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='parked_doors'"
    ).fetchone()
    if has_doors:
        for dr in conn.execute("SELECT anchor_locus FROM parked_doors WHERE status = 'ready'").fetchall():
            dfile = str(dr["anchor_locus"] or "").split(":", 1)[0].strip().lstrip("./")
            if dfile:
                ready_files.add(dfile)

    throttles: dict[str, dict[str, Any]] = {}
    for rfile, first_ts in sorted(root_first_ts.items()):
        post_tasks = int(
            conn.execute(
                """
                SELECT COUNT(*) AS c FROM tasks
                WHERE status IN ('done', 'dry')
                  AND (locus = ? OR locus LIKE ? || ':%')
                  AND updated_at > ?
                """,
                (rfile, rfile, first_ts),
            ).fetchone()["c"]
        )
        throttled = (
            post_tasks >= max_post_repro_attempts
            and rfile not in root_has_jewel
            and rfile not in ready_files
        )
        throttles[rfile] = {
            "root_file": rfile,
            "finding_ids": root_findings.get(rfile, []),
            "first_reproduced_at": first_ts,
            "post_repro_closed_tasks": post_tasks,
            "max_post_repro_attempts": max_post_repro_attempts,
            "throttled": throttled,
            "salience_penalty": 35 if throttled else 0,
        }
    return throttles


def compute_task_salience(conn: sqlite3.Connection, task_row: sqlite3.Row | dict[str, Any]) -> int:
    keys = set(task_row.keys())
    kind = str(task_row["kind"] if "kind" in keys else "")
    door_id = str(task_row["door_id"] if "door_id" in keys else "")
    summary = str(task_row["summary"] if "summary" in keys else "")
    existing_salience = int(task_row["salience_score"] or 0) if "salience_score" in keys else 0

    if kind == "chain" and (
        door_id
        or "Percolated multi-hop path" in summary
        or "[chain-calibration:" in summary
        or existing_salience >= 96
    ):
        return max(96, existing_salience or 96)

    priority = str(task_row["priority"] or "high") if "priority" in keys else "high"
    subsystem = str(task_row["subsystem"] or "") if "subsystem" in keys else ""
    locus = str(task_row["locus"] or "") if "locus" in keys else ""
    surface_id = str(task_row["surface_id"] or "") if "surface_id" in keys else ""
    reopened_boost = int(task_row["reopened_boost"] or 0) if "reopened_boost" in keys else 0

    base_floor = KIND_SALIENCE_FLOORS.get(kind, 0)
    score = max(PRIORITY_BASE_SALIENCE.get(priority, 60), base_floor) + reopened_boost

    # Subtract -3 per consecutive recent `dry` sibling in the same subsystem (forces subsystem pivot).
    if subsystem:
        recent_siblings = conn.execute(
            """
            SELECT status FROM tasks
            WHERE subsystem = ? AND status IN ('done', 'dry')
            ORDER BY closed_epoch DESC, updated_at DESC
            LIMIT 10
            """,
            (subsystem,),
        ).fetchall()
        consecutive_dry = 0
        for r in recent_siblings:
            if r["status"] == "dry":
                consecutive_dry += 1
            else:
                break
        score -= 3 * consecutive_dry

        unexplained_anom = conn.execute(
            "SELECT COUNT(*) AS c FROM anomalies WHERE status = 'unexplained' AND (subsystem = ? OR locus = ?)",
            (subsystem, locus),
        ).fetchone()["c"]
        if unexplained_anom > 0:
            score += 10

    if locus:
        unchained_prim = conn.execute(
            "SELECT COUNT(*) AS c FROM primitives WHERE chained = 0 AND status != 'dry' AND (locus = ? OR subsystem = ?)",
            (locus, subsystem),
        ).fetchone()["c"]
        if unchained_prim > 0:
            score += 8

    # Apply multi-agent Expected-Value (`lead_votes`) boost (`-15..+15`).
    has_votes = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='lead_votes'"
    ).fetchone()
    if has_votes:
        vote_row = conn.execute(
            """
            SELECT AVG(ev_score) AS avg_ev, COUNT(*) AS cnt
            FROM lead_votes
            WHERE (target_id != '' AND target_id IN (?, ?))
               OR (locus != '' AND locus = ?)
               OR (target_kind = 'subsystem' AND subsystem != '' AND subsystem = ?)
            """,
            (surface_id, door_id, locus, subsystem),
        ).fetchone()
        if vote_row is not None and int(vote_row["cnt"] or 0) > 0:
            avg_ev = float(vote_row["avg_ev"] or 50.0)
            score += int(round((avg_ev - 50.0) * 0.30))

    # Apply Per-Root Diminishing-Returns Plateau Breaker (`-35` on non-chain churn on already-reproduced files).
    if locus and kind in ("investigate", "escalate", "patch"):
        rfile = locus.split(":", 1)[0].strip().lstrip("./")
        if rfile:
            throttles = compute_root_plateau_throttles(conn)
            if rfile in throttles and throttles[rfile]["throttled"]:
                score -= int(throttles[rfile]["salience_penalty"])

    if base_floor > 0 and kind in ("reproduce", "falsify", "instrument", "bridge"):
        return max(base_floor, score)
    return max(1, score)


def recompute_all_open_salience(conn: sqlite3.Connection) -> int:
    rows = conn.execute("SELECT * FROM tasks WHERE status = 'open'").fetchall()
    for row in rows:
        new_score = compute_task_salience(conn, row)
        conn.execute("UPDATE tasks SET salience_score = ? WHERE task_id = ?", (new_score, row["task_id"]))
    return len(rows)


def list_rows(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]
