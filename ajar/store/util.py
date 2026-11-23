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
from ajar.store.tx import CURRENT_SCHEMA_VERSION, immediate_tx

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


_GENERIC_TOP_DIRS: frozenset[str] = frozenset(
    {"src", "lib", "pkg", "crates", "packages", "internal", "cmd", "apps", "modules", "core"}
)

_PROBE_TELEMETRY_ACTIONS: tuple[str, ...] = (
    "chain_snapshot_probed",
    "claim_instrumented",
    "slice_probed",
    "anomaly_added",
    "binding_certified",
)


def canonical_island_key(locus: str = "", subsystem: str = "") -> str:
    """Map a file locus or subsystem label onto a deterministic subsystem island key (`isl:<name>`)."""
    raw_path = (locus or "").split(":", 1)[0].strip().lstrip("./")
    parts = [p for p in raw_path.split("/") if p]
    if not parts:
        sub_clean = (subsystem or "").strip().lstrip("./")
        if not sub_clean or sub_clean == "root":
            return "isl:root"
        first = sub_clean.split("/")[0].split(".")[0]
        stem = re.split(r"[-_]", first)[0]
        return f"isl:{stem if len(stem) >= 4 else first}".lower()
    if len(parts) == 1:
        base = pathlib.PurePosixPath(parts[0]).stem.lower()
        prefix = re.split(r"[-_]", base)[0]
        return f"isl:{prefix if len(prefix) >= 4 else base}"
    top = parts[0].lower()
    if top in _GENERIC_TOP_DIRS:
        if len(parts) >= 3:
            return f"isl:{top}/{parts[1].lower()}"
        base = pathlib.PurePosixPath(parts[1]).stem.lower()
        prefix = re.split(r"[-_]", base)[0]
        return f"isl:{top}/{prefix if len(prefix) >= 4 else base}"
    return f"isl:{top}"


def compute_island_illumination(conn: sqlite3.Connection) -> dict[str, Any]:
    """Compute `QD-Islands` subsystem illumination and explore-lease deme quotas across the repository."""
    existing_tables = {
        str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    islands_set: set[str] = set()
    island_files: dict[str, set[str]] = {}

    def _reg(locus_val: str = "", sub_val: str = "") -> str:
        isl = canonical_island_key(locus_val, sub_val)
        islands_set.add(isl)
        rel_f = (locus_val or "").split(":", 1)[0].strip().lstrip("./")
        if rel_f:
            island_files.setdefault(isl, set()).add(rel_f)
        return isl

    if "repomap_symbols" in existing_tables:
        for r in conn.execute("SELECT DISTINCT rel_path FROM repomap_symbols").fetchall():
            rpath = str(r["rel_path"] or "").strip()
            if rpath:
                _reg(rpath, "")

    if "surfaces" in existing_tables:
        for r in conn.execute("SELECT locus, subsystem FROM surfaces").fetchall():
            loc_s = str(r["locus"] or "").strip()
            sub_s = str(r["subsystem"] or "").strip()
            if loc_s or sub_s:
                _reg(loc_s, sub_s)

    covered_files_by_isl: dict[str, set[str]] = {}
    if "coverage_spans" in existing_tables:
        for r in conn.execute("SELECT DISTINCT rel_path FROM coverage_spans").fetchall():
            rpath = str(r["rel_path"] or "").strip().lstrip("./")
            if rpath:
                isl = _reg(rpath, "")
                covered_files_by_isl.setdefault(isl, set()).add(rpath)

    explore_leases_by_isl: dict[str, int] = {}
    open_explore_by_isl: dict[str, int] = {}
    dry_verified_by_isl: dict[str, int] = {}
    closed_explore_ts_by_isl: dict[str, list[str]] = {}
    if "tasks" in existing_tables:
        for t in conn.execute(
            "SELECT kind, status, locus, subsystem, dry_control_locus, updated_at FROM tasks"
        ).fetchall():
            tkind = str(t["kind"] or "")
            tstatus = str(t["status"] or "")
            tloc = str(t["locus"] or "").strip()
            tsub = str(t["subsystem"] or "").strip()
            if not (tloc or tsub):
                continue
            isl = _reg(tloc, tsub)
            if tkind in ("investigate", "bridge", "escalate"):
                if tstatus in ("leased", "done", "dry"):
                    explore_leases_by_isl[isl] = explore_leases_by_isl.get(isl, 0) + 1
                elif tstatus == "open":
                    open_explore_by_isl[isl] = open_explore_by_isl.get(isl, 0) + 1
                if tstatus in ("done", "dry"):
                    closed_explore_ts_by_isl.setdefault(isl, []).append(str(t["updated_at"] or ""))
            if tstatus == "dry" and str(t["dry_control_locus"] or "").strip():
                dry_verified_by_isl[isl] = dry_verified_by_isl.get(isl, 0) + 1

    active_prims_by_isl: dict[str, int] = {}
    prim_isl_by_id: dict[str, str] = {}
    if "primitives" in existing_tables:
        for p in conn.execute("SELECT primitive_id, locus, subsystem, status FROM primitives").fetchall():
            ploc = str(p["locus"] or "").strip()
            psub = str(p["subsystem"] or "").strip()
            if ploc or psub:
                isl = _reg(ploc, psub)
                prim_isl_by_id[str(p["primitive_id"] or "")] = isl
                if str(p["status"] or "active") != "dry":
                    active_prims_by_isl[isl] = active_prims_by_isl.get(isl, 0) + 1

    findings_by_isl: dict[str, int] = {}
    jewel_ts_by_isl: dict[str, str] = {}
    fnd_isl_by_id: dict[str, str] = {}
    if "findings" in existing_tables:
        for f in conn.execute("SELECT finding_id, locus, realism_tier, created_at FROM findings").fetchall():
            floc = str(f["locus"] or "").strip()
            if floc:
                isl = _reg(floc, "")
                fnd_isl_by_id[str(f["finding_id"] or "")] = isl
                findings_by_isl[isl] = findings_by_isl.get(isl, 0) + 1
                if str(f["realism_tier"] or "") == "crown_jewel":
                    fts = str(f["created_at"] or "")
                    if fts >= jewel_ts_by_isl.get(isl, ""):
                        jewel_ts_by_isl[isl] = fts

    jewel_isl_by_id: dict[str, str] = {}
    if "crown_jewels" in existing_tables:
        for cj in conn.execute("SELECT jewel_id, locus, subsystem, status, updated_at FROM crown_jewels").fetchall():
            cjloc = str(cj["locus"] or "").strip()
            cjsub = str(cj["subsystem"] or "").strip()
            if cjloc or cjsub:
                isl = _reg(cjloc, cjsub)
                jewel_isl_by_id[str(cj["jewel_id"] or "")] = isl
                if str(cj["status"] or "") == "reached":
                    cjts = str(cj["updated_at"] or "")
                    if cjts >= jewel_ts_by_isl.get(isl, ""):
                        jewel_ts_by_isl[isl] = cjts

    if "chains" in existing_tables:
        for ch in conn.execute(
            "SELECT step_ids_json, jewel_id, created_at FROM chains WHERE verified = 1 AND realism_tier = 'crown_jewel'"
        ).fetchall():
            chts = str(ch["created_at"] or "")
            jid = str(ch["jewel_id"] or "")
            if jid and jid in jewel_isl_by_id:
                jisl = jewel_isl_by_id[jid]
                if chts >= jewel_ts_by_isl.get(jisl, ""):
                    jewel_ts_by_isl[jisl] = chts
            try:
                sids = json.loads(str(ch["step_ids_json"] or "[]"))
            except (ValueError, TypeError):
                sids = []
            if isinstance(sids, list):
                for sid in sids:
                    s_isl = prim_isl_by_id.get(str(sid)) or fnd_isl_by_id.get(str(sid))
                    if s_isl and chts >= jewel_ts_by_isl.get(s_isl, ""):
                        jewel_ts_by_isl[s_isl] = chts

    ready_door_islands: set[str] = set()
    if "parked_doors" in existing_tables:
        for dr in conn.execute("SELECT anchor_locus, blocker_locus, subsystem, status FROM parked_doors").fetchall():
            aloc = str(dr["anchor_locus"] or "").strip()
            bloc = str(dr["blocker_locus"] or "").strip()
            dsub = str(dr["subsystem"] or "").strip()
            isl_a = _reg(aloc, dsub) if (aloc or dsub) else ""
            isl_b = _reg(bloc, dsub) if bloc else ""
            if str(dr["status"] or "") == "ready":
                if isl_a:
                    ready_door_islands.add(isl_a)
                if isl_b:
                    ready_door_islands.add(isl_b)

    m_count = len(islands_set)
    m_eff = max(1, m_count)
    total_files = sum(len(fs) for fs in island_files.values())
    total_explore = sum(explore_leases_by_isl.values())

    raw_illum: dict[str, bool] = {}
    for isl in sorted(islands_set):
        cov_cnt = len(covered_files_by_isl.get(isl, set()))
        ver_cnt = (
            findings_by_isl.get(isl, 0)
            + active_prims_by_isl.get(isl, 0)
            + dry_verified_by_isl.get(isl, 0)
        )
        l_i = explore_leases_by_isl.get(isl, 0)
        raw_illum[isl] = bool(cov_cnt >= 1 or ver_cnt >= 1 or l_i >= 1)

    illum_cnt = sum(1 for v in raw_illum.values() if v)
    global_illumination = (float(illum_cnt) / float(m_count)) if m_count > 0 else 0.0
    summary_fair_cap = (
        1.0
        if m_count <= 1
        else 0.65
        if m_count == 2
        else max(2.0 / float(m_count), (1.0 / float(m_count)) + 0.15)
    )

    islands_out: dict[str, dict[str, Any]] = {}
    for isl in sorted(islands_set):
        file_cnt = len(island_files.get(isl, set()))
        w0_i = (float(file_cnt) / float(total_files)) if total_files > 0 else (1.0 / float(m_eff))
        if m_count <= 1:
            fair_cap_i = 1.0
        elif m_count == 2:
            fair_cap_i = min(0.75, max(0.65, w0_i + 0.15))
        else:
            fair_cap_i = min(0.85, max(2.0 / float(m_count), w0_i + 0.15))

        l_i = explore_leases_by_isl.get(isl, 0)
        cov_cnt = len(covered_files_by_isl.get(isl, set()))
        ver_cnt = (
            findings_by_isl.get(isl, 0)
            + active_prims_by_isl.get(isl, 0)
            + dry_verified_by_isl.get(isl, 0)
        )
        is_illum = raw_illum[isl]
        has_ready = isl in ready_door_islands
        j_ts = jewel_ts_by_isl.get(isl, "")
        closed_ts = sorted(closed_explore_ts_by_isl.get(isl, []), reverse=True)
        has_recent_jewel = bool(j_ts and (len(closed_ts) < 2 or j_ts >= closed_ts[1]))
        share_i = (float(l_i) / float(total_explore)) if total_explore > 0 else 0.0

        if m_count <= 1 or total_explore == 0:
            under_explored = False
            over_mined = False
            sal_adj = 0
        else:
            under_explored = bool(l_i == 0 and (not is_illum) and global_illumination < 0.75)
            over_mined = bool(
                total_explore >= 2
                and l_i >= 2
                and share_i > fair_cap_i
                and (not has_ready)
                and (not has_recent_jewel)
            )
            sal_adj = 12 if under_explored else (-25 if over_mined else 0)

        islands_out[isl] = {
            "island": isl,
            "file_count": file_cnt,
            "prior_weight": round(w0_i, 4),
            "fair_share_cap": round(fair_cap_i, 4),
            "explore_leases": l_i,
            "open_explore_tasks": open_explore_by_isl.get(isl, 0),
            "explore_share": round(share_i, 4),
            "covered_files": cov_cnt,
            "verified_artifacts": ver_cnt,
            "illuminated": is_illum,
            "has_ready_door": has_ready,
            "has_recent_jewel_progress": has_recent_jewel,
            "under_explored": under_explored,
            "over_mined": over_mined,
            "salience_adjustment": sal_adj,
        }

    return {
        "island_count": m_count,
        "illuminated_count": illum_cnt,
        "global_illumination": round(global_illumination, 4),
        "total_explore_leases": total_explore,
        "fair_share_cap": round(summary_fair_cap, 4),
        "islands": islands_out,
    }


def compute_epistemic_potential(conn: sqlite3.Connection) -> dict[str, Any]:
    """Compute strictly grounded Lyapunov epistemic potential `Phi(t) >= 0.0` over run.db."""
    existing_tables = {
        str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }

    covered_loc = 0
    if "coverage_spans" in existing_tables:
        seen_spans: set[tuple[str, int, int]] = set()
        per_task_loc: dict[str, int] = {}
        for r in conn.execute(
            "SELECT COALESCE(task_id, '') AS tid, rel_path, start_line, end_line FROM coverage_spans ORDER BY rowid ASC"
        ).fetchall():
            rpath = str(r["rel_path"] or "").strip().lstrip("./")
            s_ln = int(r["start_line"] or 0)
            e_ln = int(r["end_line"] or 0)
            if not rpath or s_ln < 1 or e_ln < s_ln:
                continue
            skey = (rpath, s_ln, e_ln)
            if skey in seen_spans:
                continue
            seen_spans.add(skey)
            span_loc = e_ln - s_ln + 1
            tid = str(r["tid"] or "")
            used = per_task_loc.get(tid, 0)
            credit = max(0, min(span_loc, 2000 - used))
            per_task_loc[tid] = used + credit
        covered_loc = sum(per_task_loc.values())

    bindings = 0
    if "certified_bindings" in existing_tables:
        bindings = int(
            conn.execute(
                "SELECT COUNT(DISTINCT locus) AS c FROM certified_bindings WHERE valid = 1 AND COALESCE(TRIM(file_sha256), '') != ''"
            ).fetchone()["c"]
        )

    dry_loci: set[str] = set()
    if "tasks" in existing_tables:
        for r in conn.execute(
            "SELECT DISTINCT TRIM(dry_control_locus) AS loc FROM tasks WHERE status = 'dry' AND COALESCE(TRIM(dry_control_locus), '') != ''"
        ).fetchall():
            if r["loc"]:
                dry_loci.add(str(r["loc"]))
    if "primitives" in existing_tables:
        for r in conn.execute(
            "SELECT DISTINCT TRIM(dry_locus) AS loc FROM primitives WHERE status = 'dry' AND COALESCE(TRIM(dry_locus), '') != ''"
        ).fetchall():
            if r["loc"]:
                dry_loci.add(str(r["loc"]))
    dry_closures = len(dry_loci)

    active_primitives = 0
    if "primitives" in existing_tables:
        active_primitives = int(
            conn.execute(
                "SELECT COUNT(*) AS c FROM primitives WHERE status IN ('active', 'chained') AND COALESCE(TRIM(evidence_cmd), '') != ''"
            ).fetchone()["c"]
        )

    settled_claims = 0
    if "claims" in existing_tables:
        settled_claims = int(
            conn.execute(
                "SELECT COUNT(*) AS c FROM claims WHERE status IN ('falsified', 'reproduced', 'config_gated')"
            ).fetchone()["c"]
        )

    woken_doors = 0
    if "parked_doors" in existing_tables:
        woken_doors = int(
            conn.execute(
                "SELECT COUNT(*) AS c FROM parked_doors WHERE status IN ('ready', 'chained')"
            ).fetchone()["c"]
        )

    findings_cnt = 0
    if "findings" in existing_tables:
        findings_cnt += int(conn.execute("SELECT COUNT(*) AS c FROM findings").fetchone()["c"])
    if "chains" in existing_tables:
        findings_cnt += int(conn.execute("SELECT COUNT(*) AS c FROM chains WHERE verified = 1").fetchone()["c"])

    reached_jewels = 0
    if "crown_jewels" in existing_tables:
        reached_jewels = int(
            conn.execute("SELECT COUNT(*) AS c FROM crown_jewels WHERE status = 'reached'").fetchone()["c"]
        )

    phi = round(
        (float(covered_loc) / 1000.0)
        + (2.0 * float(bindings))
        + (4.0 * float(dry_closures))
        + (6.0 * float(active_primitives))
        + (8.0 * float(settled_claims))
        + (12.0 * float(woken_doors))
        + (25.0 * float(findings_cnt))
        + (60.0 * float(reached_jewels)),
        4,
    )
    return {
        "epistemic_potential": phi,
        "components": {
            "covered_loc": covered_loc,
            "bindings": bindings,
            "dry_closures": dry_closures,
            "active_primitives": active_primitives,
            "settled_claims": settled_claims,
            "woken_doors": woken_doors,
            "findings": findings_cnt,
            "reached_jewels": reached_jewels,
        },
    }


def compute_epistemic_delta(
    conn: sqlite3.Connection,
    *,
    reference_actions: Sequence[str] = ("pulse", "stop_hook_check"),
) -> dict[str, Any]:
    """Compare current Lyapunov potential `Phi(t)` against the most recent checkpoint event."""
    cur = compute_epistemic_potential(conn)
    phi_now = float(cur["epistemic_potential"])
    prev_phi: float | None = None

    has_events = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='events'"
    ).fetchone()
    clean_actions = [a.strip() for a in reference_actions if a and a.strip()]
    if has_events and clean_actions:
        placeholders = ",".join("?" for _ in clean_actions)
        rows = conn.execute(
            f"SELECT payload_json FROM events WHERE action IN ({placeholders}) ORDER BY event_id DESC LIMIT 20",
            tuple(clean_actions),
        ).fetchall()
        for r in rows:
            try:
                payload = json.loads(str(r["payload_json"] or "{}"))
            except (ValueError, TypeError):
                payload = {}
            if isinstance(payload, dict) and payload.get("epistemic_potential") is not None:
                prev_phi = float(payload["epistemic_potential"])
                break

    return {
        "epistemic_potential": phi_now,
        "previous_potential": prev_phi,
        "delta_phi": round(phi_now - (prev_phi if prev_phi is not None else 0.0), 4),
        "has_prior_checkpoint": prev_phi is not None,
        "components": cur["components"],
    }


def evaluate_chain_failure_streak(
    conn: sqlite3.Connection,
    *,
    steps: Sequence[str],
    door_id: str = "",
) -> dict[str, Any]:
    """Count consecutive unverified `chain propose` attempts on `steps`/`door_id` since the last runtime probe."""
    step_key = tuple(sorted(s.strip() for s in steps if s and s.strip()))
    clean_door = (door_id or "").strip()
    existing_tables = {
        str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    snap_ids: list[str] = []
    if "repro_snapshots" in existing_tables:
        snap_ids = [
            str(r["snapshot_id"])
            for r in conn.execute("SELECT snapshot_id FROM repro_snapshots ORDER BY created_at DESC LIMIT 3").fetchall()
            if r["snapshot_id"]
        ]

    if (not step_key and not clean_door) or "events" not in existing_tables:
        return {
            "unprobed_failures": 0,
            "chain_probe_required": False,
            "gate_blocked": False,
            "last_probe_event_id": 0,
            "available_snapshots": snap_ids,
        }

    probe_placeholders = ",".join("?" for _ in _PROBE_TELEMETRY_ACTIONS)
    probe_row = conn.execute(
        f"SELECT COALESCE(MAX(event_id), 0) AS m FROM events WHERE action IN ({probe_placeholders})",
        _PROBE_TELEMETRY_ACTIONS,
    ).fetchone()
    last_probe_event_id = int(probe_row["m"] or 0) if probe_row is not None else 0

    chain_meta: dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]] = {}
    if "chains" in existing_tables:
        for crow in conn.execute(
            "SELECT chain_id, door_id, step_ids_json, evidence_json FROM chains"
        ).fetchall():
            cid = str(crow["chain_id"] or "")
            cdoor = str(crow["door_id"] or "").strip()
            try:
                raw_s = json.loads(str(crow["step_ids_json"] or "[]"))
                csteps = tuple(sorted(str(x).strip() for x in raw_s if str(x).strip())) if isinstance(raw_s, list) else ()
            except (ValueError, TypeError):
                csteps = ()
            try:
                ev_obj = json.loads(str(crow["evidence_json"] or "{}"))
                req_s = ev_obj.get("requested_steps") if isinstance(ev_obj, dict) else None
                rsteps = tuple(sorted(str(x).strip() for x in req_s if str(x).strip())) if isinstance(req_s, list) else ()
            except (ValueError, TypeError):
                rsteps = ()
            chain_meta[cid] = (cdoor, csteps, rsteps)

    count = 0
    for ev in conn.execute(
        "SELECT entity_id, payload_json FROM events WHERE action = 'chain_proposed' AND event_id > ? ORDER BY event_id ASC",
        (last_probe_event_id,),
    ).fetchall():
        cid = str(ev["entity_id"] or "")
        try:
            payload = json.loads(str(ev["payload_json"] or "{}"))
        except (ValueError, TypeError):
            payload = {}
        if not isinstance(payload, dict):
            continue
        ev_steps_raw = payload.get("steps") or []
        ev_steps = (
            tuple(sorted(str(x).strip() for x in ev_steps_raw if str(x).strip()))
            if isinstance(ev_steps_raw, list)
            else ()
        )
        req_steps_raw = payload.get("requested_steps") or []
        req_steps = (
            tuple(sorted(str(x).strip() for x in req_steps_raw if str(x).strip()))
            if isinstance(req_steps_raw, list)
            else ()
        )
        ev_door = str(payload.get("door_id") or "").strip()
        meta_door, meta_steps, meta_req_steps = chain_meta.get(cid, ("", (), ()))
        eff_door = ev_door or meta_door

        step_match = bool(
            step_key
            and (
                ev_steps == step_key
                or req_steps == step_key
                or meta_steps == step_key
                or meta_req_steps == step_key
            )
        )
        door_match = bool(clean_door and eff_door == clean_door)
        if step_match or door_match:
            if bool(payload.get("verified")):
                count = 0
            else:
                count += 1

    return {
        "unprobed_failures": count,
        "chain_probe_required": count >= 2,
        "gate_blocked": count >= 2,
        "last_probe_event_id": last_probe_event_id,
        "available_snapshots": snap_ids,
    }


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


def compute_task_salience(
    conn: sqlite3.Connection,
    task_row: sqlite3.Row | dict[str, Any],
    *,
    _illumination: dict[str, Any] | None = None,
    _throttles: dict[str, dict[str, Any]] | None = None,
) -> int:
    keys = set(task_row.keys())
    kind = str(task_row["kind"] if "kind" in keys else "") or "investigate"
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

    if kind == "bridge" and ("[unicorn-bridge]" in summary or existing_salience >= 90):
        return max(90, existing_salience or 90)

    priority = str(task_row["priority"] or "high") if "priority" in keys else "high"
    subsystem = str(task_row["subsystem"] or "") if "subsystem" in keys else ""
    locus = str(task_row["locus"] or "") if "locus" in keys else ""
    surface_id = str(task_row["surface_id"] or "") if "surface_id" in keys else ""
    reopened_boost = int(task_row["reopened_boost"] or 0) if "reopened_boost" in keys else 0

    base_floor = KIND_SALIENCE_FLOORS.get(kind, 0)
    if kind == "investigate" and "[stall-breaker]" in summary:
        base_floor = max(base_floor, 74)
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
            throttles = _throttles if _throttles is not None else compute_root_plateau_throttles(conn)
            if rfile in throttles and throttles[rfile]["throttled"]:
                score -= int(throttles[rfile]["salience_penalty"])

    # Apply `QD-Islands` Subsystem Deme Reservation Firewall (`+12` unvisited boost, `-25` over-mined penalty).
    if (locus or subsystem) and kind in ("investigate", "escalate"):
        illum = _illumination if _illumination is not None else compute_island_illumination(conn)
        isl = canonical_island_key(locus, subsystem)
        islands_map = illum.get("islands") or {}
        if isl in islands_map:
            isl_info = islands_map[isl]
            score += int(isl_info["salience_adjustment"])
            if bool(isl_info.get("over_mined")):
                score = min(score, 55)
        elif int(illum.get("total_explore_leases") or 0) > 0:
            eff_m = int(illum.get("island_count") or 0) + 1
            eff_glob = float(illum.get("illuminated_count") or 0) / float(max(1, eff_m))
            if eff_m >= 2 and eff_glob < 0.75:
                score += 12

    if base_floor > 0 and kind in ("reproduce", "falsify", "instrument", "bridge"):
        return max(base_floor, score)
    return max(1, score)


def recompute_all_open_salience(conn: sqlite3.Connection) -> int:
    rows = conn.execute("SELECT * FROM tasks WHERE status = 'open'").fetchall()
    if not rows:
        return 0
    illum = compute_island_illumination(conn)
    throttles = compute_root_plateau_throttles(conn)
    with immediate_tx(conn):
        for row in rows:
            new_score = compute_task_salience(conn, row, _illumination=illum, _throttles=throttles)
            conn.execute("UPDATE tasks SET salience_score = ? WHERE task_id = ?", (new_score, row["task_id"]))
    return len(rows)


def list_rows(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def apply_latest_finding_corrections(
    conn: sqlite3.Connection,
    findings: list[dict[str, Any]],
    *,
    preserve_order: bool = False,
) -> list[dict[str, Any]]:
    """Deterministically project latest `finding_corrections` onto finding dicts, superseded by newer `finding_calibrated` events."""
    if not findings:
        return findings
    has_fc = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='finding_corrections'"
    ).fetchone()
    if not has_fc:
        return findings

    fc_rows = conn.execute(
        "SELECT * FROM finding_corrections ORDER BY created_at DESC, rowid DESC"
    ).fetchall()
    if not fc_rows:
        return findings

    latest_fc: dict[str, sqlite3.Row] = {}
    for row in fc_rows:
        fid = str(row["finding_id"] or "")
        if fid and fid not in latest_fc:
            latest_fc[fid] = row

    latest_cal_ts: dict[str, str] = {}
    has_events = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='events'"
    ).fetchone()
    if has_events:
        for ev in conn.execute(
            "SELECT entity_id, ts FROM events WHERE action = 'finding_calibrated' ORDER BY ts DESC, event_id DESC"
        ).fetchall():
            efid = str(ev["entity_id"] or "")
            if efid and efid not in latest_cal_ts:
                latest_cal_ts[efid] = str(ev["ts"] or "")

    merged: list[dict[str, Any]] = []
    for item in findings:
        out = dict(item)
        fid = str(out.get("finding_id") or "")
        fc = latest_fc.get(fid)
        if fc is not None:
            fc_ts = str(fc["created_at"] or "")
            cal_ts = latest_cal_ts.get(fid, "")
            if not cal_ts or fc_ts >= cal_ts:
                try:
                    payload = json.loads(str(fc["payload_json"] or "{}"))
                except (ValueError, TypeError):
                    payload = {}
                if isinstance(payload, dict):
                    sev = str(payload.get("severity") or "").strip().lower()
                    if sev in ("critical", "high", "medium", "low"):
                        out["severity"] = sev
                        if sev in ("medium", "low") and out.get("realism_tier") != "stepping_stone":
                            out["realism_tier"] = "stepping_stone"
                    ttl = str(payload.get("title") or "").strip()
                    if ttl:
                        out["title"] = scrub_text(ttl)
                    rem = str(payload.get("remediation_state") or "").strip()
                    if rem in ("unpatched", "micropatched", "verified_local", "maintainer_patched") and "remediation_state" in out:
                        out["remediation_state"] = rem
                    rtier = str(payload.get("realism_tier") or "").strip()
                    if rtier in ("crown_jewel", "high_impact", "stepping_stone"):
                        out["realism_tier"] = rtier
                out["applied_correction_id"] = str(fc["correction_id"])
        merged.append(out)

    if not preserve_order:
        sev_rank = {"critical": 1, "high": 2, "medium": 3, "low": 4}
        merged.sort(key=lambda d: (sev_rank.get(str(d.get("severity") or "low"), 5), str(d.get("created_at") or "")))
    return merged

