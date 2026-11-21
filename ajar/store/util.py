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
    _ensure_v322_schema,
)
from ajar.store.tx import CURRENT_SCHEMA_VERSION

PRIORITY_BASE_SALIENCE: dict[str, int] = {
    "critical": 80,
    "high": 60,
    "medium": 40,
    "low": 20,
}


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


def compute_task_salience(conn: sqlite3.Connection, task_row: sqlite3.Row | dict[str, Any]) -> int:
    kind = str(task_row["kind"] if "kind" in task_row.keys() else "")
    door_id = str(task_row["door_id"] if "door_id" in task_row.keys() else "")
    if kind == "chain" and door_id:
        return max(96, int(task_row["salience_score"] or 96))

    priority = str(task_row["priority"] or "high")
    subsystem = str(task_row["subsystem"] or "")
    locus = str(task_row["locus"] or "")
    reopened_boost = int(task_row["reopened_boost"] or 0)

    score = PRIORITY_BASE_SALIENCE.get(priority, 60) + reopened_boost

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

    return max(1, score)


def recompute_all_open_salience(conn: sqlite3.Connection) -> int:
    rows = conn.execute("SELECT * FROM tasks WHERE status = 'open'").fetchall()
    for row in rows:
        new_score = compute_task_salience(conn, row)
        conn.execute("UPDATE tasks SET salience_score = ? WHERE task_id = ?", (new_score, row["task_id"]))
    return len(rows)


def list_rows(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]
