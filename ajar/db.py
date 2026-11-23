"""SQLite WAL state store and long-horizon coordination primitives for Ajar.

Stores all run state outside the target tree (`~/.ajar/runs/<run_id>/run.db`),
enforces `O_NOFOLLOW` symlink checks, scrubs secret patterns before persistence,
and implements:
- Work axis: `surfaces`, `surface_drivers`, `tasks` (with leases & integer salience)
- Truth axis: `claims`, `findings`, `chains`
- Long-horizon memory: `anomalies` (survive claim disproof), `primitives`,
  `certified_bindings` (`< 4 KB` context frames), 2-fail telemetry pivot, and
  `pulse` sweeps every 8 closed tasks
- Economics & attribution: `human_touches`, `spend_ledger`, `scope_rules`
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sqlite3
import time
from typing import Any, Sequence

from ajar import EXIT_GATE_BLOCKED, EXIT_USER_ERROR
from ajar.chain_planner import reconcile_door_bridge_tasks
from ajar.domain.models import AjarError as AjarError
from ajar.domain.transitions import assert_valid_primitive_transition
from ajar.epistemic_hooks import (
    detect_capability_bridges,
    expire_stale_hooks,
    record_hook_lease_exposure,
    select_active_hooks_for_task,
)
from ajar.redact import scrub_text
from ajar.store.migrations import (
    SCHEMA_SQL as SCHEMA_SQL,
)
from ajar.store.migrations import (
    _ensure_v31_schema as _ensure_v31_schema,
)
from ajar.store.migrations import (
    _ensure_v32_schema as _ensure_v32_schema,
)
from ajar.store.migrations import (
    _ensure_v33_schema as _ensure_v33_schema,
)
from ajar.store.migrations import (
    _ensure_v34_schema as _ensure_v34_schema,
)
from ajar.store.migrations import (
    _ensure_v322_schema as _ensure_v322_schema,
)
from ajar.store.tx import CURRENT_SCHEMA_VERSION as CURRENT_SCHEMA_VERSION
from ajar.store.tx import immediate_tx
from ajar.store.util import (
    PRIORITY_BASE_SALIENCE as PRIORITY_BASE_SALIENCE,
)
from ajar.store.util import (
    _assert_no_symlink_components as _assert_no_symlink_components,
)
from ajar.store.util import (
    compute_commitment_hash as compute_commitment_hash,
)
from ajar.store.util import (
    compute_harness_code_sha256 as compute_harness_code_sha256,
)
from ajar.store.util import (
    compute_lead_ev_formula as compute_lead_ev_formula,
)
from ajar.store.util import (
    compute_root_plateau_throttles as compute_root_plateau_throttles,
)
from ajar.store.util import (
    compute_task_salience as compute_task_salience,
)
from ajar.store.util import (
    get_ajar_home as get_ajar_home,
)
from ajar.store.util import (
    infer_subsystem as infer_subsystem,
)
from ajar.store.util import (
    list_rows as list_rows,
)
from ajar.store.util import (
    log_event as log_event,
)
from ajar.store.util import (
    new_id as new_id,
)
from ajar.store.util import (
    normalize_mechanism_key as normalize_mechanism_key,
)
from ajar.store.util import (
    open_run_db as open_run_db,
)
from ajar.store.util import (
    parse_tag_list,
)
from ajar.store.util import (
    recompute_all_open_salience as recompute_all_open_salience,
)
from ajar.store.util import (
    resolve_run_id as resolve_run_id,
)
from ajar.store.util import (
    run_dir_for as run_dir_for,
)
from ajar.store.util import (
    utc_now_iso as utc_now_iso,
)


def check_dead_end_repetition(
    conn: sqlite3.Connection,
    *,
    locus: str,
    mechanism: str,
    consume_anomaly_id: str | None = None,
) -> None:
    """Pre-flight `< 5 ms` guard blocking repetitive dead-end hypotheses."""
    if consume_anomaly_id:
        anom = conn.execute(
            "SELECT status FROM anomalies WHERE anomaly_id = ?",
            (consume_anomaly_id,),
        ).fetchone()
        if anom and anom["status"] == "unexplained":
            return

    mech_key = normalize_mechanism_key(mechanism)
    prior_claim = conn.execute(
        """
        SELECT claim_id, status, falsify_notes FROM claims
        WHERE locus = ? AND mechanism_key = ?
          AND status IN ('falsified', 'rejected_repro', 'duplicate_root_cause')
        LIMIT 1
        """,
        (locus.strip(), mech_key),
    ).fetchone()
    if prior_claim:
        raise AjarError(
            f"Blocked repetitive hypothesis at {locus}: matches prior {prior_claim['status']} "
            f"claim {prior_claim['claim_id']} ({prior_claim['falsify_notes'][:120]}). "
            "Cite a fresh unexplained --consume-anomaly <id> if target behavior changed.",
            EXIT_GATE_BLOCKED,
            {"prior_claim_id": prior_claim["claim_id"], "status": prior_claim["status"]},
        )

    prior_dry = conn.execute(
        """
        SELECT task_id, dry_control_locus, dry_control_reason FROM tasks
        WHERE status = 'dry' AND locus = ?
        LIMIT 1
        """,
        (locus.strip(),),
    ).fetchone()
    if prior_dry and mech_key:
        dry_key = normalize_mechanism_key(prior_dry["dry_control_reason"] or "")
        mech_words = set(mech_key.split())
        dry_words = set(dry_key.split())
        if mech_words and len(mech_words & dry_words) >= max(2, len(mech_words) // 2):
            raise AjarError(
                f"Blocked repetitive hypothesis at {locus}: already closed dry in {prior_dry['task_id']} "
                f"via control {prior_dry['dry_control_locus']}. Cite --consume-anomaly <id> to reopen.",
                EXIT_GATE_BLOCKED,
                {"prior_task_id": prior_dry["task_id"]},
            )


def lease_next_task(
    conn: sqlite3.Connection,
    *,
    worker_id: str,
    kind: str | None = None,
    ttl_sec: int = 900,
    recover: bool = False,
) -> dict[str, Any] | None:
    """Atomically lease the highest-salience open task with portfolio balance and Zero-Skill quota."""
    now = time.time()
    now_iso = utc_now_iso()
    with immediate_tx(conn):
        conn.execute(
            """
            UPDATE tasks
            SET status = 'open',
                worker_id = NULL,
                lease_expires_at = NULL,
                attempt_count = attempt_count + 1,
                updated_at = ?
            WHERE status = 'leased' AND lease_expires_at IS NOT NULL AND lease_expires_at < ?
            """,
            (now_iso, now),
        )

        if recover:
            existing = conn.execute(
                "SELECT * FROM tasks WHERE status = 'leased' AND worker_id = ? ORDER BY updated_at DESC LIMIT 1",
                (worker_id,),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE tasks SET lease_expires_at = ?, updated_at = ? WHERE task_id = ?",
                    (now + ttl_sec, now_iso, existing["task_id"]),
                )
                out = dict(existing)
                out["suppress_domain_skills"] = out["skill_mode"] == "zero_skill"
                return out

        run_row = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
        verify_only = bool(run_row and run_row["status"] == "verify_only")
        in_hunt_phase = bool(
            run_row and "campaign_phase" in run_row.keys() and str(run_row["campaign_phase"] or "hunt") == "hunt"
        )

        row: sqlite3.Row | None = None
        if kind:
            if (verify_only and kind in ("map", "investigate", "bridge")) or (in_hunt_phase and kind == "patch"):
                return None
            row = conn.execute(
                """
                SELECT * FROM tasks
                WHERE status = 'open' AND kind = ?
                ORDER BY salience_score DESC, created_at ASC
                LIMIT 1
                """,
                (kind,),
            ).fetchone()
        elif verify_only:
            allowed = ("falsify", "reproduce", "instrument", "chain", "escalate") if in_hunt_phase else (
                "falsify", "reproduce", "instrument", "chain", "patch", "escalate"
            )
            placeholders = ",".join("?" for _ in allowed)
            row = conn.execute(
                f"""
                SELECT * FROM tasks
                WHERE status = 'open' AND kind IN ({placeholders})
                ORDER BY salience_score DESC, created_at ASC
                LIMIT 1
                """,
                allowed,
            ).fetchone()
        else:
            # 1. Woken Open-Door / Percolated `chain` tasks (`salience >= 96`) take top priority unless one is already leased.
            leased_chain = conn.execute(
                "SELECT COUNT(*) AS c FROM tasks WHERE status = 'leased' AND kind = 'chain'"
            ).fetchone()["c"]
            if int(leased_chain) == 0:
                row = conn.execute(
                    """
                    SELECT * FROM tasks
                    WHERE status = 'open' AND kind = 'chain' AND salience_score >= 95
                    ORDER BY salience_score DESC, created_at ASC
                    LIMIT 1
                    """
                ).fetchone()

            # 2. Portfolio anti-starvation between greenfield `investigate` and missing-link `bridge`.
            if row is None:
                recent_explore = [
                    str(r["kind"])
                    for r in conn.execute(
                        """
                        SELECT kind FROM tasks
                        WHERE kind IN ('investigate', 'bridge') AND status IN ('leased', 'done', 'dry')
                        ORDER BY updated_at DESC LIMIT 3
                        """
                    ).fetchall()
                ]
                has_open_inv = (
                    conn.execute("SELECT 1 FROM tasks WHERE status = 'open' AND kind IN ('map', 'investigate') LIMIT 1").fetchone()
                    is not None
                )
                has_open_bridge = (
                    conn.execute("SELECT 1 FROM tasks WHERE status = 'open' AND kind = 'bridge' LIMIT 1").fetchone()
                    is not None
                )
                bridge_share_high = recent_explore.count("bridge") >= 1 and len(recent_explore) <= 3
                if has_open_inv and has_open_bridge:
                    if len(recent_explore) >= 2 and all(k == "investigate" for k in recent_explore[:2]):
                        row = conn.execute(
                            "SELECT * FROM tasks WHERE status = 'open' AND kind = 'bridge' ORDER BY salience_score DESC, created_at ASC LIMIT 1"
                        ).fetchone()
                    elif bridge_share_high:
                        row = conn.execute(
                            """
                            SELECT * FROM tasks
                            WHERE status = 'open' AND kind != 'bridge' AND (? = 0 OR kind != 'patch')
                            ORDER BY salience_score DESC, created_at ASC
                            LIMIT 1
                            """,
                            (1 if in_hunt_phase else 0,),
                        ).fetchone()

            if row is None:
                row = conn.execute(
                    """
                    SELECT * FROM tasks
                    WHERE status = 'open' AND (? = 0 OR kind != 'patch')
                    ORDER BY salience_score DESC, created_at ASC
                    LIMIT 1
                    """,
                    (1 if in_hunt_phase else 0,),
                ).fetchone()

        if row is None:
            return None

        skill_mode = "domain"
        if row["kind"] == "investigate" and run_row is not None:
            prev_mode = conn.execute(
                """
                SELECT skill_mode FROM tasks
                WHERE worker_id = ? AND kind = 'investigate'
                ORDER BY updated_at DESC LIMIT 1
                """,
                (worker_id,),
            ).fetchone()
            if prev_mode is not None:
                skill_mode = prev_mode["skill_mode"]
            else:
                distinct_prev_workers = conn.execute(
                    "SELECT COUNT(DISTINCT worker_id) AS c FROM tasks WHERE kind = 'investigate' AND worker_id IS NOT NULL AND worker_id != ?",
                    (worker_id,),
                ).fetchone()["c"]
                if distinct_prev_workers >= 1 and int(run_row["zero_skill_leases"]) == 0:
                    skill_mode = "zero_skill"

            if skill_mode == "zero_skill":
                conn.execute("UPDATE runs SET zero_skill_leases = zero_skill_leases + 1")
            else:
                conn.execute("UPDATE runs SET domain_skill_leases = domain_skill_leases + 1")

        conn.execute(
            """
            UPDATE tasks
            SET status = 'leased', worker_id = ?, skill_mode = ?, lease_expires_at = ?, updated_at = ?
            WHERE task_id = ?
            """,
            (worker_id, skill_mode, now + ttl_sec, now_iso, row["task_id"]),
        )
        log_event(
            conn,
            worker_id,
            "task_leased",
            row["task_id"],
            {"kind": row["kind"], "skill_mode": skill_mode, "salience_score": row["salience_score"]},
        )
        updated = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (row["task_id"],)).fetchone()
        out = dict(updated)
        out["suppress_domain_skills"] = skill_mode == "zero_skill"
        return out


def maybe_auto_pulse(conn: sqlite3.Connection, target_dir: pathlib.Path | None = None) -> dict[str, Any] | None:
    """Increment closed_task_counter and trigger `run_pulse` every 8 closed tasks."""
    conn.execute("UPDATE runs SET closed_task_counter = closed_task_counter + 1")
    cnt = conn.execute("SELECT closed_task_counter FROM runs LIMIT 1").fetchone()["closed_task_counter"]
    recompute_all_open_salience(conn)
    if int(cnt) % 8 == 0:
        return run_pulse(conn, target_dir=target_dir)
    return None


def file_locus_sha256(target_dir: pathlib.Path, locus: str) -> tuple[str, int, int]:
    """Compute SHA-256 of the referenced line slice (`file:start-end` or `file:line`)."""
    raw_file, _, span = locus.partition(":")
    rel_file = raw_file.strip().lstrip("/")
    fpath = (target_dir / rel_file).resolve()
    try:
        fpath.relative_to(target_dir.resolve())
    except ValueError:
        return ("", 0, 0)
    if not fpath.is_file():
        return ("", 0, 0)

    lines = fpath.read_bytes().splitlines(keepends=True)
    start_line = 1
    end_line = len(lines)
    if span:
        m = re.match(r"^(\d+)(?:-(\d+))?", span.strip())
        if m:
            start_line = max(1, int(m.group(1)))
            end_line = int(m.group(2)) if m.group(2) else start_line
            end_line = min(len(lines), max(start_line, end_line))
    excerpt = b"".join(lines[start_line - 1 : end_line])
    return (hashlib.sha256(excerpt).hexdigest(), start_line, end_line)


def set_certified_binding(
    conn: sqlite3.Connection,
    *,
    target_dir: pathlib.Path,
    name: str,
    value: str,
    locus: str,
    task_id: str | None = None,
    actor: str = "worker",
) -> dict[str, Any]:
    sha, s_line, e_line = file_locus_sha256(target_dir, locus)
    now_iso = utc_now_iso()
    clean_val = scrub_text(value)
    with immediate_tx(conn):
        existing = conn.execute("SELECT binding_id FROM certified_bindings WHERE name = ?", (name,)).fetchone()
        binding_id = existing["binding_id"] if existing else new_id("bind")
        conn.execute(
            """
            INSERT INTO certified_bindings(
                binding_id, task_id, name, value, locus, file_sha256, line_start, line_end, valid, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                task_id = excluded.task_id,
                value = excluded.value,
                locus = excluded.locus,
                file_sha256 = excluded.file_sha256,
                line_start = excluded.line_start,
                line_end = excluded.line_end,
                valid = 1,
                updated_at = excluded.updated_at
            """,
            (binding_id, task_id, name, clean_val, locus, sha, s_line, e_line, now_iso, now_iso),
        )
        # Recording new target binding also satisfies pending instrumentation on matching locus!
        conn.execute(
            """
            UPDATE claims
            SET instrumented_since_fail = 1,
                status = CASE WHEN status = 'needs_instrumentation' THEN 'survived_falsify' ELSE status END,
                updated_at = ?
            WHERE locus = ? AND status IN ('needs_instrumentation', 'survived_falsify')
            """,
            (now_iso, locus),
        )
        log_event(conn, actor, "binding_certified", binding_id, {"name": name, "locus": locus})
    return {
        "binding_id": binding_id,
        "name": name,
        "value": clean_val,
        "locus": locus,
        "file_sha256": sha,
        "valid": 1,
    }


def add_steer(
    conn: sqlite3.Connection,
    *,
    rule_text: str,
    scope: str = "global",
    target_filter: str = "",
    author: str = "operator",
    touch_kind: str = "scope_authority",
    record_human_touch: bool = True,
) -> dict[str, Any]:
    """Persist an attributable workspace Steer (`DEC-0049` / `DEC-0061`)."""
    if scope not in ("global", "subsystem", "path"):
        raise AjarError(f"Unsupported steer scope: {scope!r}", EXIT_USER_ERROR)
    if touch_kind not in ("scope_authority", "research_steering"):
        raise AjarError(f"Unsupported steer touch_kind: {touch_kind!r}", EXIT_USER_ERROR)
    clean_rule = scrub_text(rule_text.strip())
    if len(clean_rule) < 5:
        raise AjarError("Steer rule_text must be at least 5 characters.", EXIT_USER_ERROR)

    sid = new_id("str")
    now_iso = utc_now_iso()
    clean_filter = scrub_text(target_filter.strip())
    clean_author = scrub_text(author.strip() or "operator")
    touch_id = None
    with immediate_tx(conn):
        conn.execute(
            """
            INSERT INTO steers(steer_id, scope, target_filter, rule_text, author, touch_kind, active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (sid, scope, clean_filter, clean_rule, clean_author, touch_kind, now_iso),
        )
        if record_human_touch and clean_author != "system":
            touch_id = new_id("tch")
            conn.execute(
                "INSERT INTO human_touches(touch_id, kind, actor, notes, created_at) VALUES (?, ?, ?, ?, ?)",
                (touch_id, touch_kind, clean_author, f"steer {sid} [{scope}:{clean_filter or '*'}]: {clean_rule[:160]}", now_iso),
            )
        log_event(
            conn,
            clean_author,
            "steer_added",
            sid,
            {"scope": scope, "target_filter": clean_filter, "touch_kind": touch_kind, "touch_id": touch_id},
        )
    return {
        "steer_id": sid,
        "scope": scope,
        "target_filter": clean_filter,
        "rule_text": clean_rule,
        "author": clean_author,
        "touch_kind": touch_kind,
        "touch_id": touch_id,
        "active": 1,
    }


def list_steers(
    conn: sqlite3.Connection,
    *,
    active_only: bool = False,
    subsystem: str = "",
    locus: str = "",
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM steers"
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY steer_id ASC"
    rows = [dict(r) for r in conn.execute(sql).fetchall()]
    if not subsystem and not locus:
        return rows
    matched: list[dict[str, Any]] = []
    loc_file = locus.split(":", 1)[0].strip().lstrip("./")
    for r in rows:
        sc = r["scope"]
        flt = (r["target_filter"] or "").strip().lstrip("./")
        if sc == "global" or not flt:
            matched.append(r)
        elif sc == "subsystem" and subsystem and (subsystem == flt or subsystem.startswith(flt + "/")):
            matched.append(r)
        elif sc == "path" and loc_file and (loc_file.startswith(flt) or flt in loc_file):
            matched.append(r)
    return matched


def revoke_steer(
    conn: sqlite3.Connection,
    *,
    steer_id: str,
    reason: str,
    actor: str = "operator",
) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM steers WHERE steer_id = ?", (steer_id,)).fetchone()
    if row is None:
        raise AjarError(f"Unknown steer_id: {steer_id}", EXIT_USER_ERROR)
    now_iso = utc_now_iso()
    clean_reason = scrub_text(reason.strip() or "revoked")
    conn.execute(
        "UPDATE steers SET active = 0, revoked_at = ?, revoke_reason = ? WHERE steer_id = ?",
        (now_iso, clean_reason, steer_id),
    )
    log_event(conn, actor, "steer_revoked", steer_id, {"reason": clean_reason})
    return {"steer_id": steer_id, "active": 0, "revoked_at": now_iso, "revoke_reason": clean_reason}


def rescope_claim(
    conn: sqlite3.Connection,
    *,
    claim_id: str,
    worker_id: str,
    reason: str,
    title: str | None = None,
    locus: str | None = None,
    mechanism: str | None = None,
    severity: str | None = None,
    falsification_prediction: str | None = None,
    falsification_test: str | None = None,
) -> dict[str, Any]:
    """Re-scope a candidate claim when locus, preconditions, or severity shift (`claim_mismatch` recovery)."""
    clm = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (claim_id,)).fetchone()
    if clm is None:
        raise AjarError(f"Unknown claim_id: {claim_id}", EXIT_USER_ERROR)
    if clm["status"] == "reproduced":
        raise AjarError(
            f"Truth-axis monotonicity gate: verified reproduced claim {claim_id} cannot be rescoped in place.",
            EXIT_GATE_BLOCKED,
        )
    if len(reason.strip()) < 8:
        raise AjarError("Claim rescope --reason must be at least 8 characters.", EXIT_USER_ERROR)

    new_title = scrub_text(title.strip()) if title else str(clm["title"])
    new_locus = locus.strip() if locus else str(clm["locus"])
    new_mech = scrub_text(mechanism.strip()) if mechanism else str(clm["mechanism"])
    new_sev = severity.strip() if severity else str(clm["severity"])
    new_pred = scrub_text(falsification_prediction.strip()) if falsification_prediction else str(clm["falsification_prediction"])
    new_test = scrub_text(falsification_test.strip()) if falsification_test else str(clm["falsification_test"])
    new_sub = infer_subsystem(new_locus)
    new_mech_key = normalize_mechanism_key(new_mech)

    # Re-run independent falsification whenever root-cause locus or mechanism changed.
    root_changed = (new_locus != clm["locus"]) or (new_mech_key != clm["mechanism_key"])
    new_status = "proposed" if root_changed or clm["status"] in ("falsified", "rejected_repro") else str(clm["status"])
    new_falsifier = None if new_status == "proposed" else clm["falsifier_worker_id"]
    now_iso = utc_now_iso()

    conn.execute(
        """
        UPDATE claims
        SET title = ?, subsystem = ?, locus = ?, mechanism = ?, mechanism_key = ?,
            severity = ?, falsification_prediction = ?, falsification_test = ?,
            status = ?, falsifier_worker_id = ?, research_state = 'candidate',
            evidence_state = CASE WHEN ? = 'proposed' THEN 'unverified' ELSE evidence_state END,
            failed_repro_count = CASE WHEN ? THEN 0 ELSE failed_repro_count END,
            updated_at = ?
        WHERE claim_id = ?
        """,
        (
            new_title,
            new_sub,
            new_locus,
            new_mech,
            new_mech_key,
            new_sev,
            new_pred,
            new_test,
            new_status,
            new_falsifier,
            new_status,
            1 if root_changed else 0,
            now_iso,
            claim_id,
        ),
    )
    log_event(
        conn,
        worker_id,
        "claim_rescoped",
        claim_id,
        {
            "old_locus": clm["locus"],
            "new_locus": new_locus,
            "old_severity": clm["severity"],
            "new_severity": new_sev,
            "new_status": new_status,
            "reason": scrub_text(reason[:200]),
        },
    )
    return {
        "claim_id": claim_id,
        "status": new_status,
        "locus": new_locus,
        "severity": new_sev,
        "root_changed": root_changed,
    }


def checkpoint_task(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    worker_id: str,
    state_dict: dict[str, Any],
) -> dict[str, Any]:
    """Persist structured trajectory checkpoint JSON onto `tasks.checkpoint_json` for clean session resume."""
    row = conn.execute("SELECT task_id FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
    if row is None:
        raise AjarError(f"Unknown task_id: {task_id}", EXIT_USER_ERROR)
    clean_json = scrub_text(json.dumps(state_dict, sort_keys=True))
    if len(clean_json.encode("utf-8")) > 2048:
        raise AjarError("Task checkpoint exceeds 2 KB limit; store concise loci and verified facts only.", EXIT_USER_ERROR)
    now_iso = utc_now_iso()
    conn.execute(
        "UPDATE tasks SET checkpoint_json = ?, updated_at = ? WHERE task_id = ?",
        (clean_json, now_iso, task_id),
    )
    log_event(conn, worker_id, "task_checkpointed", task_id, {"keys": sorted(state_dict.keys())})
    return {"task_id": task_id, "checkpoint": json.loads(clean_json), "updated_at": now_iso}


def record_coverage_span(
    conn: sqlite3.Connection,
    *,
    target_dir: pathlib.Path,
    task_id: str | None,
    worker_id: str,
    rel_path: str,
    start_line: int,
    end_line: int,
) -> dict[str, Any]:
    """Record an audited source line range (`coverage_spans`) bound to file SHA-256."""
    clean_rel = rel_path.strip().lstrip("./")
    if start_line < 1 or end_line < start_line:
        raise AjarError(f"Invalid line span {start_line}..{end_line} for {clean_rel}.", EXIT_USER_ERROR)
    sha, s_ln, e_ln = file_locus_sha256(target_dir, f"{clean_rel}:{start_line}-{end_line}")
    if not sha:
        raise AjarError(f"Target file not found for coverage span: {clean_rel}", EXIT_USER_ERROR)
    sid = new_id("cov")
    now_iso = utc_now_iso()
    conn.execute(
        """
        INSERT INTO coverage_spans(span_id, task_id, worker_id, rel_path, start_line, end_line, file_sha256, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (sid, task_id, scrub_text(worker_id), clean_rel, s_ln, e_ln, sha, now_iso),
    )
    return {
        "span_id": sid,
        "task_id": task_id,
        "rel_path": clean_rel,
        "start_line": s_ln,
        "end_line": e_ln,
        "file_sha256": sha,
    }


def render_task_context(
    conn: sqlite3.Connection,
    task_id: str,
    *,
    record_exposure: bool = False,
) -> dict[str, Any]:
    """Build a prefix-stable `< 4 KB` (`<= 50` lines) certified context projection.

    Places run-invariant sections (`Goal`, `Active Workspace Steers`, sorted `Certified Bindings`)
    at the top of the prompt so multi-worker LLM calls hit provider KV prompt caches, followed
    by the task-specific delta (`Capability Bridges`, `Active Epistemic Hooks`, `Dead Ends`) at the tail.
    """
    task = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
    if task is None:
        raise AjarError(f"Unknown task_id: {task_id}", EXIT_USER_ERROR)
    run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()

    lineage: list[str] = []
    cur = task
    depth = 0
    while cur is not None and depth < 6:
        lineage.append(f"{cur['task_id']}[{cur['kind']}] {cur['title']}")
        parent_id = cur["parent_task_id"]
        cur = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (parent_id,)).fetchone() if parent_id else None
        depth += 1
    lineage.reverse()

    # Deterministic name-sorted bindings keep the top prompt prefix byte-identical across tasks.
    bindings = conn.execute(
        "SELECT name, value, locus FROM certified_bindings WHERE valid = 1 ORDER BY name ASC LIMIT 8"
    ).fetchall()
    sub = task["subsystem"] or infer_subsystem(task["locus"] or "")
    direction = str(task["direction"] if "direction" in task.keys() and task["direction"] else "outside_in")
    # Global steers only in the invariant prefix so cross-subsystem tasks share identical top bytes;
    # path/subsystem steers appear in Task Delta if present.
    all_active_steers = list_steers(conn, active_only=True, subsystem=sub, locus=str(task["locus"] or ""))
    global_steers = [s for s in all_active_steers if s["scope"] == "global"][:5]
    scoped_steers = [s for s in all_active_steers if s["scope"] != "global"][:5]

    anomalies = conn.execute(
        """
        SELECT anomaly_id, locus, observation FROM anomalies
        WHERE status = 'unexplained' AND (subsystem = ? OR subsystem = '')
        ORDER BY created_at DESC LIMIT 3
        """,
        (sub,),
    ).fetchall()
    guarded_prims = conn.execute(
        """
        SELECT primitive_id, locus, kind, guarded_by_locus FROM primitives
        WHERE chained = 0 AND status != 'dry' AND guarded_by_locus != ''
          AND (subsystem = ? OR locus = ? OR guarded_by_locus = ?)
        ORDER BY created_at DESC LIMIT 3
        """,
        (sub, task["locus"], task["locus"]),
    ).fetchall()
    task_door_id = str(task["door_id"] if "door_id" in task.keys() else "")
    open_doors = conn.execute(
        """
        SELECT door_id, status, anchor_locus, blocker_locus, missing_link_summary, snapshot_id
        FROM parked_doors
        WHERE status IN ('ready', 'bridging', 'parked')
          AND (door_id = ? OR status = 'ready' OR subsystem = ?)
        ORDER BY CASE status WHEN 'ready' THEN 0 WHEN 'bridging' THEN 1 ELSE 2 END, updated_at DESC
        LIMIT 2
        """,
        (task_door_id, sub),
    ).fetchall()
    dead_claims = conn.execute(
        """
        SELECT claim_id, locus, mechanism, status, diff_state FROM claims
        WHERE (subsystem = ? OR locus = ?)
          AND status IN ('falsified', 'rejected_repro', 'duplicate_root_cause', 'config_gated')
        ORDER BY updated_at DESC LIMIT 3
        """,
        (sub, task["locus"]),
    ).fetchall()
    dry_controls = conn.execute(
        """
        SELECT task_id, dry_control_locus, dry_control_reason FROM tasks
        WHERE status = 'dry' AND subsystem = ?
        ORDER BY updated_at DESC LIMIT 3
        """,
        (sub,),
    ).fetchall()

    bridges = detect_capability_bridges(conn, subsystem=sub, locus=str(task["locus"] or ""), limit=2)
    active_hooks = select_active_hooks_for_task(conn, task, limit=2)
    if active_hooks and record_exposure:
        record_hook_lease_exposure(conn, [str(h["hook_id"]) for h in active_hooks])

    # 1. Run-Invariant Cacheable Prefix (100% byte-identical across all tasks in the run!)
    prefix_lines: list[str] = [
        f"# Certified Run Prefix: {(run['run_id'] if run else 'run')}",
        f"Goal: {(run['goal'] if run else '')[:160]}",
    ]
    if global_steers:
        prefix_lines.append("## Active Workspace Steers (operator threat-model boundaries)")
        for st in global_steers:
            prefix_lines.append(f"- [{st['scope']}:{st['target_filter'] or '*'}] {st['rule_text'][:110]}")
    if bindings:
        prefix_lines.append("## Certified Bindings (valid=1)")
        for b in bindings:
            prefix_lines.append(f"- {b['name']} = {b['value'][:90]} @ {b['locus']}")

    # 2. Task-Specific Delta
    delta_lines: list[str] = [
        f"## Task Delta: {task['task_id']}",
        f"Mode: skill_mode={task['skill_mode']} | kind={task['kind']} | direction={direction} | salience={task['salience_score']}",
    ]
    if task["skill_mode"] == "zero_skill":
        delta_lines.append("Rule: ZERO-SKILL FIRST-PRINCIPLES LEASE. Do NOT read skills/domains/*; derive invariants strictly from target code.")
    delta_lines.append(f"Target Locus: {task['locus'] or '(unassigned)'} (subsystem: {sub or 'root'})")
    delta_lines.append("Lineage: " + " -> ".join(lineage))
    if scoped_steers:
        for st in scoped_steers[:2]:
            delta_lines.append(f"Subsystem Steer [{st['scope']}:{st['target_filter']}]: {st['rule_text'][:100]}")

    raw_ckpt = str(task["checkpoint_json"] if "checkpoint_json" in task.keys() else "{}") or "{}"
    if raw_ckpt != "{}":
        delta_lines.append(f"## Trajectory Checkpoint: {raw_ckpt[:180]}")

    if open_doors:
        delta_lines.append("## Open Doors (suspended chain subgoals)")
        for od in open_doors:
            snap_s = f" snap={od['snapshot_id']}" if od["snapshot_id"] else ""
            blk_s = f" blocked_at={od['blocker_locus']}" if od["blocker_locus"] else ""
            delta_lines.append(
                f"- {od['door_id']} [{od['status']}] @ {od['anchor_locus']}{blk_s}{snap_s}: {str(od['missing_link_summary'])[:75]}"
            )

    if bridges:
        delta_lines.append("## Cross-Subsystem Capability Bridges")
        for br in bridges:
            if br["bridge_type"] == "guarded_sink_upstream_audit":
                delta_lines.append(
                    f"- [guard_ref] {br['sink_id']}@{br['sink_locus']} ({br['sink_subsystem']}) blocked by {br['guard_locus']}"
                )
            elif br["providers"]:
                pv = br["providers"][0]
                hlp = f" helper={pv['helper']}" if pv.get("helper") else ""
                mtags = ",".join(br["matched_tags"][:2])
                delta_lines.append(
                    f"- [{br['bridge_type']}] {pv['primitive_id']}@{pv['locus']} ({pv['subsystem']}) -> "
                    f"{br['sink_id']}@{br['sink_locus']} tags=[{mtags}]{hlp}"
                )
            else:
                delta_lines.append(
                    f"- [missing_provider] {br['sink_id']}@{br['sink_locus']} needs tags=[{','.join(br['missing_tags'][:2])}]"
                )

    violated_assumptions = conn.execute(
        """
        SELECT assumption_id, assumption_text, evidence_ref FROM threat_assumptions
        WHERE status = 'violated'
          AND (subsystem = ? OR subsystem = '' OR dependent_surface_id = ?)
        ORDER BY updated_at DESC LIMIT 2
        """,
        (sub, str(task["surface_id"] or "")),
    ).fetchall()
    if violated_assumptions:
        delta_lines.append("## Adaptive Threat-Model Shift (assumption violated)")
        for va in violated_assumptions:
            ev = f" by {va['evidence_ref']}" if va["evidence_ref"] else ""
            delta_lines.append(f"- {va['assumption_id']} [violated{ev}]: {va['assumption_text'][:85]}")

    if active_hooks:
        delta_lines.append("## Active Epistemic Hooks (obey Kill Rule to close dry fast)")
        for hk in active_hooks:
            delta_lines.append(f"- [{hk['hook_code']}] {hk['directive_text']} | Kill Rule: {hk['kill_rule']}")

    if guarded_prims:
        delta_lines.append("## Guarded Primitives (anti-premature-dry: test guard break before closing dry)")
        for gp in guarded_prims:
            delta_lines.append(f"- {gp['primitive_id']} [{gp['kind']}] @ {gp['locus']} guarded_by={gp['guarded_by_locus']}")
    if anomalies:
        delta_lines.append("## Unexplained Anomalies (must explain or consume)")
        for a in anomalies:
            delta_lines.append(f"- {a['anomaly_id']} @ {a['locus']}: {a['observation'][:100]}")
    if dead_claims or dry_controls:
        delta_lines.append("## Subsystem Dead Ends (do NOT repeat)")
        for dc in dead_claims:
            dtag = f"{dc['status']}:{dc['diff_state']}" if dc["diff_state"] else str(dc["status"])
            delta_lines.append(f"- {dc['claim_id']} [{dtag}] @ {dc['locus']}: {dc['mechanism'][:80]}")
        for dr in dry_controls:
            delta_lines.append(f"- {dr['task_id']} [dry] guard @ {dr['dry_control_locus']}: {(dr['dry_control_reason'] or '')[:80]}")

    # Enforce strict <= 50 lines and < 4096 bytes.
    max_delta = max(4, 48 - len(prefix_lines))
    delta_lines = delta_lines[:max_delta]
    certified_prefix = "\n".join(prefix_lines)
    task_delta = "\n".join(delta_lines)
    markdown = certified_prefix + "\n" + task_delta
    if len(markdown.encode("utf-8")) > 3900:
        markdown = markdown.encode("utf-8")[:3900].decode("utf-8", errors="ignore")

    return {
        "task_id": task["task_id"],
        "skill_mode": task["skill_mode"],
        "direction": direction,
        "suppress_domain_skills": task["skill_mode"] == "zero_skill",
        "salience_score": task["salience_score"],
        "steers_count": len(all_active_steers),
        "bindings_count": len(bindings),
        "open_doors_count": len(open_doors),
        "bridges_count": len(bridges),
        "active_hooks_count": len(active_hooks),
        "active_hooks": [str(h["hook_code"]) for h in active_hooks],
        "unexplained_anomalies_count": len(anomalies),
        "dead_ends_count": len(dead_claims) + len(dry_controls),
        "certified_prefix": certified_prefix,
        "task_delta": task_delta,
        "rendered": markdown,
    }


def calibrate_finding(
    conn: sqlite3.Connection,
    *,
    finding_id: str,
    reason: str,
    severity: str | None = None,
    title: str | None = None,
    worker_id: str = "operator",
) -> dict[str, Any]:
    """Calibrate severity/title on a confirmed finding without ad-hoc SQL edits."""
    clean_reason = scrub_text((reason or "").strip())
    if len(clean_reason) < 8:
        raise AjarError("Finding calibration --reason must be at least 8 characters.", EXIT_USER_ERROR)
    now_iso = utc_now_iso()
    with immediate_tx(conn):
        frow = conn.execute("SELECT * FROM findings WHERE finding_id = ?", (finding_id,)).fetchone()
        if frow is None:
            raise AjarError(f"Unknown finding_id: {finding_id}", EXIT_USER_ERROR)
        new_sev = (severity or str(frow["severity"])).strip().lower()
        if new_sev not in ("critical", "high", "medium", "low"):
            raise AjarError(f"Unsupported severity: {new_sev!r}", EXIT_USER_ERROR)
        new_title = scrub_text(title.strip()) if title and title.strip() else str(frow["title"])
        cur_tier = str(frow["realism_tier"] if "realism_tier" in frow.keys() else "stepping_stone")
        new_tier = "stepping_stone" if new_sev in ("medium", "low") else cur_tier

        conn.execute(
            """
            UPDATE findings
            SET severity = ?, title = ?, realism_tier = ?, calibration_notes = ?
            WHERE finding_id = ?
            """,
            (new_sev, new_title, new_tier, clean_reason, finding_id),
        )
        conn.execute(
            "UPDATE claims SET severity = ?, title = ?, updated_at = ? WHERE claim_id = ?",
            (new_sev, new_title, now_iso, str(frow["claim_id"])),
        )
        if worker_id == "operator":
            conn.execute(
                "INSERT INTO human_touches(touch_id, kind, actor, notes, created_at) VALUES (?, 'scope_authority', 'operator', ?, ?)",
                (new_id("tch"), f"calibrate {finding_id} -> {new_sev}: {clean_reason[:140]}", now_iso),
            )
        log_event(
            conn,
            worker_id,
            "finding_calibrated",
            finding_id,
            {
                "old_severity": frow["severity"],
                "new_severity": new_sev,
                "new_title": new_title,
                "realism_tier": new_tier,
                "reason": clean_reason[:200],
            },
        )
    return {
        "finding_id": finding_id,
        "claim_id": str(frow["claim_id"]),
        "old_severity": str(frow["severity"]),
        "severity": new_sev,
        "title": new_title,
        "realism_tier": new_tier,
        "calibration_notes": clean_reason,
    }


def mark_primitive_dry(
    conn: sqlite3.Connection,
    *,
    target_dir: pathlib.Path,
    target_mode: str,
    primitive_id: str,
    worker_id: str,
    locus: str,
    reason: str,
) -> dict[str, Any]:
    """Close an unchained guarded primitive as `dry` with a verified upstream guard locus."""
    prow = conn.execute("SELECT * FROM primitives WHERE primitive_id = ?", (primitive_id,)).fetchone()
    if prow is None:
        raise AjarError(f"Unknown primitive_id: {primitive_id}", EXIT_USER_ERROR)
    cur_status = "chained" if int(prow["chained"] or 0) == 1 else str(prow["status"] if "status" in prow.keys() else "active")
    assert_valid_primitive_transition(cur_status, "dry", primitive_id=primitive_id)
    clean_locus = (locus or "").strip()
    clean_reason = scrub_text((reason or "").strip())
    if not clean_locus or len(clean_reason) < 8:
        raise AjarError(
            "`ajar primitive dry` requires --locus <file:line> and --reason (>= 8 chars).",
            EXIT_USER_ERROR,
        )
    if target_mode == "source":
        sha, _, _ = file_locus_sha256(target_dir, clean_locus)
        if not sha:
            raise AjarError(
                f"Guard control locus not found in target repository: {clean_locus}",
                EXIT_USER_ERROR,
            )
    with immediate_tx(conn):
        conn.execute(
            """
            UPDATE primitives
            SET status = 'dry', dry_locus = ?, dry_reason = ?
            WHERE primitive_id = ?
            """,
            (clean_locus, clean_reason, primitive_id),
        )
        recompute_all_open_salience(conn)
        log_event(
            conn,
            worker_id,
            "primitive_marked_dry",
            primitive_id,
            {"dry_control_locus": clean_locus, "dry_reason": clean_reason[:200]},
        )
    return {
        "primitive_id": primitive_id,
        "status": "dry",
        "dry_control_locus": clean_locus,
        "dry_reason": clean_reason,
    }


def run_pulse(conn: sqlite3.Connection, *, target_dir: pathlib.Path | None = None) -> dict[str, Any]:
    """Deterministic maintenance sweep: expire leases/hooks, verify bindings, bridge tags, reopen unblocked tasks."""
    now = time.time()
    now_iso = utc_now_iso()

    with immediate_tx(conn):
        cur_exp = conn.execute(
            """
            UPDATE tasks
            SET status = 'open',
                worker_id = NULL,
                lease_expires_at = NULL,
                attempt_count = attempt_count + 1,
                updated_at = ?
            WHERE status = 'leased' AND lease_expires_at IS NOT NULL AND lease_expires_at < ?
            """,
            (now_iso, now),
        )
        expired_leases = int(cur_exp.rowcount or 0)
        expired_hooks = expire_stale_hooks(conn)
        exhausted_doors = reconcile_door_bridge_tasks(conn)

        invalidated_bindings = 0
        if target_dir is not None and target_dir.is_dir():
            for b in conn.execute("SELECT binding_id, locus, file_sha256 FROM certified_bindings WHERE valid = 1").fetchall():
                if b["file_sha256"]:
                    cur_sha, _, _ = file_locus_sha256(target_dir, b["locus"])
                    if cur_sha and cur_sha != b["file_sha256"]:
                        conn.execute(
                            "UPDATE certified_bindings SET valid = 0, updated_at = ? WHERE binding_id = ?",
                            (now_iso, b["binding_id"]),
                        )
                        invalidated_bindings += 1

        # Check `conditional_blocked` tasks against newly discovered capability tags, primitives, anomalies, and findings.
        reopened_tasks: list[str] = []
        blocked_rows = conn.execute("SELECT * FROM tasks WHERE status = 'conditional_blocked'").fetchall()
        if blocked_rows:
            signal_blobs: list[str] = []
            provided_tag_set: set[str] = set()
            for p in conn.execute(
                "SELECT locus, kind, postconditions, guarded_by_locus, provides_tags_json FROM primitives WHERE status != 'dry'"
            ).fetchall():
                ptags = parse_tag_list(p["provides_tags_json"])
                provided_tag_set.update(ptags)
                signal_blobs.append(
                    f"{p['locus']} {p['kind']} {p['postconditions']} {p['guarded_by_locus']} {' '.join(ptags)}".lower()
                )
            for a in conn.execute("SELECT locus, observation FROM anomalies WHERE status = 'unexplained'").fetchall():
                signal_blobs.append(f"{a['locus']} {a['observation']}".lower())
            for f in conn.execute("SELECT locus, title, root_cause FROM findings").fetchall():
                signal_blobs.append(f"{f['locus']} {f['title']} {f['root_cause']}".lower())
            combined_signals = "\n".join(signal_blobs)

            for brow in blocked_rows:
                check_loc = (brow["blocker_check_locus"] or "").strip().lower()
                pred = (brow["blocker_predicate"] or "").strip().lower()
                matched = False
                pred_tags = [t for t in parse_tag_list(pred) if ":" in t]
                if pred_tags and any(pt in provided_tag_set for pt in pred_tags):
                    matched = True
                elif check_loc and check_loc in combined_signals:
                    matched = True
                elif pred:
                    pred_tokens = [t for t in re.findall(r"[a-z0-9_]{4,}", pred) if t not in {"need", "when", "until", "with", "from"}]
                    if pred_tokens and all(tok in combined_signals for tok in pred_tokens[:2]):
                        matched = True
                if matched:
                    conn.execute(
                        """
                        UPDATE tasks
                        SET status = 'open', reopened_boost = reopened_boost + 12, updated_at = ?
                        WHERE task_id = ?
                        """,
                        (now_iso, brow["task_id"]),
                    )
                    reopened_tasks.append(brow["task_id"])

        rescored = recompute_all_open_salience(conn)
        result = {
            "expired_leases": expired_leases,
            "expired_hooks": expired_hooks,
            "exhausted_doors": exhausted_doors,
            "invalidated_bindings": invalidated_bindings,
            "reopened_tasks": reopened_tasks,
            "rescored_open_tasks": rescored,
        }
        log_event(conn, "system", "pulse", "", result)
    return result


def record_repro_failure(
    conn: sqlite3.Connection,
    *,
    claim: sqlite3.Row | dict[str, Any],
    worker_id: str,
    observation_hash: str,
    reason: str,
) -> dict[str, Any]:
    """Apply the 2-fail telemetry pivot (`KVMEscape` rule) when blind PoC retries stall."""
    now_iso = utc_now_iso()
    claim_id = str(claim["claim_id"])
    prev_fails = int(claim["failed_repro_count"] or 0) + 1
    same_obs = bool(claim["last_observation_hash"] and claim["last_observation_hash"] == observation_hash)

    pivoted = prev_fails >= 2 or same_obs
    new_status = "needs_instrumentation" if pivoted else "survived_falsify"
    instrument_task_id = None

    with immediate_tx(conn):
        conn.execute(
            """
            UPDATE claims
            SET failed_repro_count = ?,
                last_observation_hash = ?,
                instrumented_since_fail = CASE WHEN ? THEN 0 ELSE instrumented_since_fail END,
                status = ?,
                updated_at = ?
            WHERE claim_id = ?
            """,
            (prev_fails, observation_hash, 1 if pivoted else 0, new_status, now_iso, claim_id),
        )

        if pivoted:
            instrument_task_id = new_id("task")
            sub = str(claim["subsystem"] or infer_subsystem(str(claim["locus"])))
            conn.execute(
                """
                INSERT INTO tasks(
                    task_id, parent_claim_id, surface_id, kind, title, subsystem, locus, priority,
                    status, salience_score, summary, created_at, updated_at
                ) VALUES (?, ?, ?, 'instrument', ?, ?, ?, 'critical', 'open', 85, ?, ?, ?)
                """,
                (
                    instrument_task_id,
                    claim_id,
                    claim["surface_id"],
                    f"Instrument target state for stalled reproduction of {claim_id}",
                    sub,
                    claim["locus"],
                    scrub_text(f"2 failed PoC attempts ({reason[:120]}). Capture target trace/binding before retrying."),
                    now_iso,
                    now_iso,
                ),
            )
        log_event(
            conn,
            worker_id,
            "claim_repro_failed",
            claim_id,
            {
                "failed_repro_count": prev_fails,
                "pivoted_to_instrumentation": pivoted,
                "instrument_task_id": instrument_task_id,
                "reason": reason[:200],
            },
        )
    return {
        "claim_id": claim_id,
        "status": new_status,
        "failed_repro_count": prev_fails,
        "pivoted_to_instrumentation": pivoted,
        "instrument_task_id": instrument_task_id,
    }


def upsert_threat_model(
    conn: sqlite3.Connection,
    *,
    principals: Sequence[str],
    assets: Sequence[str],
    consumer_tiers: Sequence[str] = (),
    summary: str = "",
) -> dict[str, Any]:
    """Create or update the structured Threat Model for the active run (incrementing `revision`)."""
    run = conn.execute("SELECT run_id FROM runs LIMIT 1").fetchone()
    rid = str(run["run_id"]) if run else "run"
    existing = conn.execute("SELECT * FROM threat_models WHERE run_id = ?", (rid,)).fetchone()
    now_iso = utc_now_iso()
    clean_p = [scrub_text(p.strip()) for p in principals if p and p.strip()]
    clean_a = [scrub_text(a.strip()) for a in assets if a and a.strip()]
    clean_c = [scrub_text(c.strip()) for c in consumer_tiers if c and c.strip()]
    clean_sum = scrub_text(summary.strip())
    rev = (int(existing["revision"]) + 1) if existing else 1
    conn.execute(
        """
        INSERT INTO threat_models(
            run_id, principals_json, assets_json, consumer_tiers_json, summary, revision, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(run_id) DO UPDATE SET
            principals_json = excluded.principals_json,
            assets_json = excluded.assets_json,
            consumer_tiers_json = excluded.consumer_tiers_json,
            summary = excluded.summary,
            revision = excluded.revision,
            updated_at = excluded.updated_at
        """,
        (rid, json.dumps(clean_p), json.dumps(clean_a), json.dumps(clean_c), clean_sum, rev, now_iso),
    )
    log_event(conn, "mapper", "threat_model_upserted", rid, {"revision": rev, "principals": len(clean_p), "assets": len(clean_a)})
    return {
        "run_id": rid,
        "principals": clean_p,
        "assets": clean_a,
        "consumer_tiers": clean_c,
        "summary": clean_sum,
        "revision": rev,
        "updated_at": now_iso,
    }


def add_threat_assumption(
    conn: sqlite3.Connection,
    *,
    subsystem: str,
    assumption_text: str,
    trust_boundary: str = "",
    check_locus: str = "",
    invalidated_by_tags: Sequence[str] = (),
    dependent_surface_id: str = "",
    escalate_priority: str = "critical",
) -> dict[str, Any]:
    """Register a falsifiable architectural trust assumption linked to downstream surfaces/tasks."""
    if escalate_priority not in ("critical", "high"):
        raise AjarError(f"Unsupported --escalate-priority {escalate_priority!r}", EXIT_USER_ERROR)
    aid = new_id("tma")
    now_iso = utc_now_iso()
    norm_tags = parse_tag_list(list(invalidated_by_tags))
    clean_sub = scrub_text(subsystem.strip()) or infer_subsystem(check_locus)
    clean_txt = scrub_text(assumption_text.strip())
    clean_tb = scrub_text(trust_boundary.strip())
    clean_loc = check_locus.strip()
    dep_sid = dependent_surface_id.strip()
    conn.execute(
        """
        INSERT INTO threat_assumptions(
            assumption_id, subsystem, trust_boundary, assumption_text, check_locus,
            invalidated_by_tags_json, dependent_surface_id, escalate_priority,
            status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'assumed', ?, ?)
        """,
        (
            aid,
            clean_sub,
            clean_tb,
            clean_txt,
            clean_loc,
            json.dumps(norm_tags),
            dep_sid,
            escalate_priority,
            now_iso,
            now_iso,
        ),
    )
    log_event(conn, "mapper", "threat_assumption_added", aid, {"subsystem": clean_sub, "dependent_surface_id": dep_sid, "tags": norm_tags})
    return {
        "assumption_id": aid,
        "subsystem": clean_sub,
        "trust_boundary": clean_tb,
        "assumption_text": clean_txt,
        "check_locus": clean_loc,
        "invalidated_by_tags": norm_tags,
        "dependent_surface_id": dep_sid,
        "escalate_priority": escalate_priority,
        "status": "assumed",
    }


def transition_threat_assumption(
    conn: sqlite3.Connection,
    assumption_id: str,
    *,
    new_status: str,
    evidence_ref: str = "",
    notes: str = "",
) -> dict[str, Any]:
    """Verify (`verified_holds`) or violate (`violated`) a threat assumption.

    When an assumption transitions to `violated`, Ajar adaptively bumps `threat_models.revision`,
    upgrades `dependent_surface_id` priority, unblocks parked tasks (`+30` salience), and spawns
    an escalation task if the newly exposed surface has no open work.
    """
    if new_status not in ("verified_holds", "violated", "assumed"):
        raise AjarError(f"Invalid assumption status {new_status!r}", EXIT_USER_ERROR)

    now_iso = utc_now_iso()
    clean_ev = scrub_text(evidence_ref.strip())
    clean_notes = scrub_text(notes.strip())
    unblocked_tasks = 0
    upgraded_surface = ""
    spawned_task_id = ""
    new_revision = 1

    with immediate_tx(conn):
        row = conn.execute("SELECT * FROM threat_assumptions WHERE assumption_id = ?", (assumption_id,)).fetchone()
        if row is None:
            raise AjarError(f"Unknown assumption_id: {assumption_id}", EXIT_USER_ERROR)
        prev_status = str(row["status"])
        conn.execute(
            """
            UPDATE threat_assumptions
            SET status = ?, evidence_ref = ?, notes = ?, updated_at = ?
            WHERE assumption_id = ?
            """,
            (new_status, clean_ev, clean_notes, now_iso, assumption_id),
        )

        if new_status == "violated" and prev_status != "violated":
            run = conn.execute("SELECT run_id FROM runs LIMIT 1").fetchone()
            rid = str(run["run_id"]) if run else "run"
            tm = conn.execute("SELECT revision FROM threat_models WHERE run_id = ?", (rid,)).fetchone()
            if tm is not None:
                new_revision = int(tm["revision"]) + 1
                conn.execute("UPDATE threat_models SET revision = ?, updated_at = ? WHERE run_id = ?", (new_revision, now_iso, rid))
            else:
                new_revision = 2
                conn.execute(
                    "INSERT INTO threat_models(run_id, summary, revision, updated_at) VALUES (?, ?, ?, ?)",
                    (rid, f"Auto-initialized on violation of {assumption_id}", new_revision, now_iso),
                )

            dep_sid = str(row["dependent_surface_id"] or "").strip()
            esc_prio = str(row["escalate_priority"] or "critical")
            prio_rank = {"low": 1, "medium": 2, "high": 3, "critical": 4}
            if dep_sid:
                srow = conn.execute("SELECT surface_id, priority, locus, subsystem, name FROM surfaces WHERE surface_id = ?", (dep_sid,)).fetchone()
                if srow is not None:
                    if prio_rank.get(str(srow["priority"]), 1) < prio_rank.get(esc_prio, 4):
                        conn.execute("UPDATE surfaces SET priority = ? WHERE surface_id = ?", (esc_prio, dep_sid))
                        upgraded_surface = dep_sid

            chk_loc = str(row["check_locus"] or "").strip()
            cur = conn.execute(
                """
                UPDATE tasks
                SET status = 'open',
                    reopened_boost = reopened_boost + 30,
                    salience_score = MIN(100, salience_score + 30),
                    updated_at = ?
                WHERE status = 'conditional_blocked'
                  AND (
                      (? != '' AND blocker_check_locus = ?)
                      OR (? != '' AND surface_id = ?)
                      OR blocker_predicate LIKE ?
                  )
                """,
                (now_iso, chk_loc, chk_loc, dep_sid, dep_sid, f"%{assumption_id}%"),
            )
            unblocked_tasks = int(cur.rowcount or 0)

            if dep_sid:
                open_on_surf = conn.execute(
                    "SELECT task_id FROM tasks WHERE surface_id = ? AND status IN ('open', 'leased') LIMIT 1",
                    (dep_sid,),
                ).fetchone()
                if open_on_surf is None:
                    srow = conn.execute("SELECT locus, subsystem, name FROM surfaces WHERE surface_id = ?", (dep_sid,)).fetchone()
                    if srow is not None:
                        spawned_task_id = new_id("task")
                        conn.execute(
                            """
                            INSERT INTO tasks(
                                task_id, surface_id, kind, direction, title, subsystem, locus,
                                priority, status, salience_score, reopened_boost, summary, created_at, updated_at
                            ) VALUES (?, ?, 'investigate', 'outside_in', ?, ?, ?, ?, 'open', 92, 30, ?, ?, ?)
                            """,
                            (
                                spawned_task_id,
                                dep_sid,
                                f"Adaptive threat-model escalation on {srow['name']} ({assumption_id} violated)",
                                str(srow["subsystem"] or row["subsystem"] or ""),
                                str(srow["locus"] or ""),
                                esc_prio,
                                f"Trust assumption {assumption_id} ({str(row['assumption_text'])[:90]}) was violated by {clean_ev or 'new evidence'}.",
                                now_iso,
                                now_iso,
                            ),
                        )

            log_event(
                conn,
                "engine",
                "threat_assumption_violated",
                assumption_id,
                {
                    "evidence_ref": clean_ev,
                    "upgraded_surface": upgraded_surface,
                    "unblocked_tasks": unblocked_tasks,
                    "spawned_task_id": spawned_task_id,
                    "threat_model_revision": new_revision,
                },
            )
        else:
            log_event(conn, "worker", "threat_assumption_updated", assumption_id, {"status": new_status, "evidence_ref": clean_ev})

    return {
        "assumption_id": assumption_id,
        "status": new_status,
        "evidence_ref": clean_ev,
        "upgraded_surface": upgraded_surface,
        "unblocked_tasks": unblocked_tasks,
        "spawned_task_id": spawned_task_id,
        "threat_model_revision": new_revision,
    }


def evaluate_adaptive_threat_assumptions(
    conn: sqlite3.Connection,
    *,
    evidence_ref: str,
    confirmed_locus: str = "",
    provided_tags: Sequence[str] = (),
) -> list[dict[str, Any]]:
    """Automatically violate matching `assumed` threat assumptions when new capabilities or findings land."""
    tag_set = set(parse_tag_list(list(provided_tags)))
    loc_norm = confirmed_locus.strip()
    loc_file = loc_norm.split(":", 1)[0].strip().lstrip("./") if loc_norm else ""

    rows = conn.execute("SELECT * FROM threat_assumptions WHERE status = 'assumed'").fetchall()
    triggered: list[dict[str, Any]] = []
    for r in rows:
        inv_tags = set(parse_tag_list(r["invalidated_by_tags_json"]))
        matched_tags = sorted(tag_set & inv_tags)
        chk = str(r["check_locus"] or "").strip()
        chk_file = chk.split(":", 1)[0].strip().lstrip("./") if chk else ""
        locus_hit = bool(loc_norm and chk and (loc_norm == chk or (loc_file and loc_file == chk_file and ":" not in chk)))
        if matched_tags or locus_hit:
            why = (
                f"Auto-violated by capability tags {matched_tags}"
                if matched_tags
                else f"Auto-violated by confirmed finding at {loc_norm}"
            )
            res = transition_threat_assumption(
                conn,
                str(r["assumption_id"]),
                new_status="violated",
                evidence_ref=evidence_ref,
                notes=why,
            )
            triggered.append(res)
    return triggered
