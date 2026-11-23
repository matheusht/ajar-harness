"""Unified transactional workflow services shared by `ajar/cli.py` and `ajar/mcp.py`.

Every core state mutation (`surfaces`, `tasks`, `anomalies`, `claims`, `campaign_phase`,
`runs.finish`) lives here once, acquiring `immediate_tx(conn)` BEFORE reading mutable rows
so `assert_run_mutable`, typed transition guards, `derive_claim_axes`, and epistemic hooks
are atomic under SQLite WAL concurrency and identical across CLI and MCP interfaces.
"""

from __future__ import annotations

import json
import pathlib
import re
import sqlite3
import time
from typing import Any

from ajar import EXIT_GATE_BLOCKED, EXIT_USER_ERROR
from ajar.catalog import search_issue_catalog, trace_backward_sink_slices
from ajar.chain_planner import (
    detect_percolated_multi_hop_paths,
    evaluate_precondition_realism,
    list_crown_jewels,
)
from ajar.db import (
    check_dead_end_repetition,
    compute_task_salience,
    infer_subsystem,
    list_steers,
    log_event,
    maybe_auto_pulse,
    new_id,
    normalize_mechanism_key,
    recompute_all_open_salience,
    rescope_claim,
    utc_now_iso,
)
from ajar.domain import (
    AjarError,
    assert_valid_anomaly_transition,
    assert_valid_claim_transition,
    assert_valid_phase_transition,
    assert_valid_primitive_transition,
    assert_valid_task_transition,
    derive_claim_axes,
)
from ajar.epistemic_hooks import (
    consume_hooks_for_locus,
    on_claim_config_gated,
    on_claim_survived,
    register_epistemic_hook,
    scan_source_for_epistemic_signals,
    select_active_hooks_for_task,
)
from ajar.gates import (
    check_guarded_primitive_dry_block,
    finding_attribution_for_claim,
    validate_dry_locus,
)
from ajar.reactions import (
    on_anomaly_or_claim_recorded,
    on_finding_confirmed,
    on_primitive_added,
)
from ajar.redact import scrub_text
from ajar.repomap import list_unvisited_slices
from ajar.repro_source import validate_micropatch_diff
from ajar.store import (
    assert_run_mutable,
    compute_lead_ev_formula,
    compute_root_plateau_throttles,
    immediate_tx,
    parse_tag_list,
)
from ajar.swarm import validate_claim_block_request, validate_structural_claim_prose


def add_surface(
    conn: sqlite3.Connection,
    *,
    name: str,
    kind: str,
    locus: str,
    subsystem: str | None = None,
    priority: str = "high",
    trust_boundary: str = "",
    requires_tags: str | list[str] | None = None,
    actor: str = "worker",
) -> dict[str, Any]:
    sid = new_id("surf")
    sub = (subsystem or "").strip() or infer_subsystem(locus)
    req_tags = parse_tag_list(requires_tags)
    now_iso = utc_now_iso()
    fired_codes: list[str] = []

    with immediate_tx(conn):
        assert_run_mutable(conn, operation="surface_add")
        conn.execute(
            """
            INSERT INTO surfaces(
                surface_id, name, kind, subsystem, locus, priority,
                trust_boundary, requires_tags_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sid,
                scrub_text(name),
                kind,
                sub,
                locus,
                priority,
                scrub_text(trust_boundary or ""),
                json.dumps(req_tags),
                now_iso,
            ),
        )
        run = conn.execute("SELECT target_path FROM runs LIMIT 1").fetchone()
        tpath = pathlib.Path(str(run["target_path"])) if run is not None else None
        rel_file = locus.split(":", 1)[0].strip().lstrip("./")
        if tpath is not None and rel_file:
            cand = (tpath / rel_file).resolve()
            try:
                cand.relative_to(tpath.resolve())
                if cand.is_file():
                    src_txt = cand.read_text(encoding="utf-8", errors="ignore")
                    for hcode, directive, kill_r in scan_source_for_epistemic_signals(rel_file, src_txt):
                        register_epistemic_hook(
                            conn,
                            hook_code=hcode,
                            trigger_cmd="surface.add",
                            source_entity_id=sid,
                            dedup_material=f"{rel_file}:{hcode}",
                            subsystem=sub,
                            target_locus=locus,
                            directive_text=directive,
                            kill_rule=kill_r,
                        )
                        fired_codes.append(hcode)
            except ValueError:
                pass
        log_event(
            conn,
            actor.strip() or "worker",
            "surface_added",
            sid,
            {"name": name, "locus": locus, "requires_tags": req_tags, "hooks": fired_codes},
        )
    return {
        "surface_id": sid,
        "subsystem": sub,
        "priority": priority,
        "requires_tags": req_tags,
        "hooks_triggered": fired_codes,
    }


def close_task_done(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    worker_id: str,
    summary: str = "",
    target_dir: pathlib.Path | None = None,
) -> dict[str, Any]:
    wid = worker_id.strip() or "worker"
    now_iso = utc_now_iso()
    with immediate_tx(conn):
        assert_run_mutable(conn, operation="task_done")
        cur = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if cur is None:
            raise AjarError(f"Unknown task_id: {task_id}", EXIT_USER_ERROR)
        assert_valid_task_transition(str(cur["status"]), "done", task_id=task_id)
        conn.execute(
            """
            UPDATE tasks
            SET status = 'done', worker_id = ?, summary = ?, lease_expires_at = NULL,
                closed_epoch = ?, updated_at = ?
            WHERE task_id = ?
            """,
            (wid, scrub_text(summary or ""), time.time(), now_iso, task_id),
        )
        if cur["kind"] == "instrument" and cur["locus"]:
            conn.execute(
                """
                UPDATE claims
                SET instrumented_since_fail = 1,
                    status = CASE WHEN status = 'needs_instrumentation' THEN 'survived_falsify' ELSE status END,
                    updated_at = ?
                WHERE locus = ?
                """,
                (now_iso, cur["locus"]),
            )
        if cur["kind"] == "escalate" and cur["locus"]:
            consume_hooks_for_locus(conn, locus=str(cur["locus"]), hook_code="H5_POST_CONFIRM_ESCALATION")
        log_event(conn, wid, "task_done", task_id, {"kind": cur["kind"]})
    pulse = maybe_auto_pulse(conn, target_dir)
    return {"task_id": task_id, "status": "done", "pulse": pulse}


def close_task_dry(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    worker_id: str,
    locus: str,
    control_reason: str,
    target_dir: pathlib.Path | None = None,
    target_mode: str = "source",
) -> dict[str, Any]:
    wid = worker_id.strip() or "worker"
    ok, msg = validate_dry_locus(target_dir, target_mode, locus, control_reason)
    if not ok:
        raise AjarError(msg, EXIT_GATE_BLOCKED)
    now_iso = utc_now_iso()
    with immediate_tx(conn):
        assert_run_mutable(conn, operation="task_dry")
        cur = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if cur is None:
            raise AjarError(f"Unknown task_id: {task_id}", EXIT_USER_ERROR)
        assert_valid_task_transition(str(cur["status"]), "dry", task_id=task_id)
        ok_gp, msg_gp = check_guarded_primitive_dry_block(conn, task_row=cur, dry_locus=locus)
        if not ok_gp:
            raise AjarError(msg_gp, EXIT_GATE_BLOCKED)
        conn.execute(
            """
            UPDATE tasks
            SET status = 'dry', worker_id = ?, dry_control_locus = ?, dry_control_reason = ?,
                lease_expires_at = NULL, closed_epoch = ?, updated_at = ?
            WHERE task_id = ?
            """,
            (wid, locus, scrub_text(control_reason), time.time(), now_iso, task_id),
        )
        consume_hooks_for_locus(conn, locus=locus)
        if cur["locus"]:
            consume_hooks_for_locus(conn, locus=str(cur["locus"]))
        log_event(conn, wid, "task_dry", task_id, {"locus": locus})
    pulse = maybe_auto_pulse(conn, target_dir)
    return {"task_id": task_id, "status": "dry", "pulse": pulse}


def block_task(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    worker_id: str,
    predicate: str,
    check_locus: str = "",
) -> dict[str, Any]:
    wid = worker_id.strip() or "worker"
    now_iso = utc_now_iso()
    with immediate_tx(conn):
        assert_run_mutable(conn, operation="task_block")
        cur = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if cur is None:
            raise AjarError(f"Unknown task_id: {task_id}", EXIT_USER_ERROR)
        assert_valid_task_transition(str(cur["status"]), "conditional_blocked", task_id=task_id)
        conn.execute(
            """
            UPDATE tasks
            SET status = 'conditional_blocked', worker_id = ?, blocker_predicate = ?,
                blocker_check_locus = ?, lease_expires_at = NULL, updated_at = ?
            WHERE task_id = ?
            """,
            (wid, scrub_text(predicate), check_locus or "", now_iso, task_id),
        )
        log_event(conn, wid, "task_conditional_blocked", task_id, {"predicate": predicate})
    return {"task_id": task_id, "status": "conditional_blocked"}


def add_anomaly(
    conn: sqlite3.Connection,
    *,
    locus: str,
    observation: str,
    surface_id: str | None = None,
    source_claim_id: str | None = None,
    repro_cmd: str = "",
    target_dir: pathlib.Path | None = None,
    actor: str = "worker",
) -> dict[str, Any]:
    aid = new_id("anom")
    now_iso = utc_now_iso()
    sub = infer_subsystem(locus)
    with immediate_tx(conn):
        assert_run_mutable(conn, operation="anomaly_add")
        conn.execute(
            """
            INSERT INTO anomalies(
                anomaly_id, surface_id, source_claim_id, subsystem, locus, observation, repro_cmd, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'unexplained', ?, ?)
            """,
            (
                aid,
                surface_id,
                source_claim_id,
                sub,
                locus,
                scrub_text(observation),
                scrub_text(repro_cmd or ""),
                now_iso,
                now_iso,
            ),
        )
        if source_claim_id:
            conn.execute(
                """
                UPDATE claims
                SET instrumented_since_fail = 1,
                    status = CASE WHEN status = 'needs_instrumentation' THEN 'survived_falsify' ELSE status END,
                    updated_at = ?
                WHERE claim_id = ?
                """,
                (now_iso, source_claim_id),
            )
        hooks = on_anomaly_or_claim_recorded(
            conn,
            entity_id=aid,
            trigger_cmd="anomaly.add",
            subsystem=sub,
            locus=locus,
            text_blob=observation,
            target_dir=target_dir,
        )
        log_event(conn, actor.strip() or "worker", "anomaly_added", aid, {"locus": locus})
    return {
        "anomaly_id": aid,
        "status": "unexplained",
        "subsystem": sub,
        "hooks_triggered": [h["hook_code"] for h in hooks],
    }


def explain_anomaly(
    conn: sqlite3.Connection,
    *,
    anomaly_id: str,
    locus: str,
    reason: str,
    actor: str = "worker",
) -> dict[str, Any]:
    if len(reason.strip()) < 12:
        raise AjarError("Explanation --reason must be at least 12 characters.", EXIT_USER_ERROR)
    now_iso = utc_now_iso()
    with immediate_tx(conn):
        assert_run_mutable(conn, operation="anomaly_explain")
        anom = conn.execute("SELECT status FROM anomalies WHERE anomaly_id = ?", (anomaly_id,)).fetchone()
        if anom is None:
            raise AjarError(f"Unknown anomaly_id: {anomaly_id}", EXIT_USER_ERROR)
        assert_valid_anomaly_transition(str(anom["status"]), "benign_explained", anomaly_id=anomaly_id)
        conn.execute(
            """
            UPDATE anomalies
            SET status = 'benign_explained', explanation_locus = ?, explanation_reason = ?, updated_at = ?
            WHERE anomaly_id = ?
            """,
            (locus, scrub_text(reason), now_iso, anomaly_id),
        )
        log_event(conn, actor.strip() or "worker", "anomaly_explained", anomaly_id, {"locus": locus})
    return {"anomaly_id": anomaly_id, "status": "benign_explained"}


def propose_claim(
    conn: sqlite3.Connection,
    *,
    worker_id: str,
    title: str,
    locus: str,
    mechanism: str,
    falsification_prediction: str,
    falsification_test: str,
    surface_id: str | None = None,
    severity: str = "high",
    seeded_by_human: bool = False,
    consume_anomaly_id: str | None = None,
    same_root_of: str | None = None,
    target_dir: pathlib.Path | None = None,
    target_mode: str = "source",
) -> dict[str, Any]:
    wid = worker_id.strip()
    if not wid:
        raise AjarError("claim propose requires a non-empty worker_id.", EXIT_GATE_BLOCKED)
    if len(falsification_prediction.strip()) < 10 or len(falsification_test.strip()) < 5:
        raise AjarError(
            "DEC-0128 gate: --falsification-prediction and --falsification-test are required before proposing a claim.",
            EXIT_GATE_BLOCKED,
        )
    ok_prose, prose_msg = validate_structural_claim_prose(title, mechanism, falsification_prediction)
    if not ok_prose:
        raise AjarError(prose_msg, EXIT_GATE_BLOCKED)
    cid = new_id("clm")
    now_iso = utc_now_iso()
    sub = infer_subsystem(locus)
    clean_root = (same_root_of or "").strip() or None
    with immediate_tx(conn):
        assert_run_mutable(conn, operation="claim_propose")
        if clean_root is not None:
            parent_clm = conn.execute("SELECT claim_id FROM claims WHERE claim_id = ?", (clean_root,)).fetchone()
            if parent_clm is None:
                raise AjarError(f"Unknown --same-root-of claim_id: {clean_root}", EXIT_USER_ERROR)
        check_dead_end_repetition(
            conn,
            locus=locus,
            mechanism=mechanism,
            consume_anomaly_id=consume_anomaly_id,
        )
        conn.execute(
            """
            INSERT INTO claims(
                claim_id, surface_id, proposer_worker_id, seeded_by_human, title, subsystem, locus,
                mechanism, mechanism_key, severity, falsification_prediction, falsification_test,
                status, same_root_claim_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'proposed', ?, ?, ?)
            """,
            (
                cid,
                surface_id,
                wid,
                1 if seeded_by_human else 0,
                scrub_text(title),
                sub,
                locus,
                scrub_text(mechanism),
                normalize_mechanism_key(mechanism),
                severity,
                scrub_text(falsification_prediction),
                scrub_text(falsification_test),
                clean_root,
                now_iso,
                now_iso,
            ),
        )
        if consume_anomaly_id:
            conn.execute(
                "UPDATE anomalies SET status = 'consumed_by_claim', consumed_by_id = ?, updated_at = ? WHERE anomaly_id = ?",
                (cid, now_iso, consume_anomaly_id),
            )
        hooks = on_anomaly_or_claim_recorded(
            conn,
            entity_id=cid,
            trigger_cmd="claim.propose",
            subsystem=sub,
            locus=locus,
            text_blob=f"{title} {mechanism}",
            target_dir=target_dir if target_mode == "source" else None,
        )
        log_event(
            conn,
            wid,
            "claim_proposed",
            cid,
            {"locus": locus, "severity": severity, "same_root_claim_id": clean_root or ""},
        )
    return {
        "claim_id": cid,
        "status": "proposed",
        "subsystem": sub,
        "same_root_claim_id": clean_root,
        "hooks_triggered": [h["hook_code"] for h in hooks],
    }


def rescope_claim_service(
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
    wid = worker_id.strip()
    if not wid:
        raise AjarError("claim rescope requires a non-empty worker_id.", EXIT_GATE_BLOCKED)
    ok_prose, prose_msg = validate_structural_claim_prose(title, mechanism, falsification_prediction)
    if not ok_prose:
        raise AjarError(prose_msg, EXIT_GATE_BLOCKED)
    with immediate_tx(conn):
        assert_run_mutable(conn, operation="claim_rescope")
        return rescope_claim(
            conn,
            claim_id=claim_id,
            worker_id=wid,
            reason=reason,
            title=title,
            locus=locus,
            mechanism=mechanism,
            severity=severity,
            falsification_prediction=falsification_prediction,
            falsification_test=falsification_test,
        )


def falsify_claim(
    conn: sqlite3.Connection,
    *,
    claim_id: str,
    worker_id: str,
    notes: str,
    control_locus: str | None = None,
    config_gate: str = "",
) -> dict[str, Any]:
    wid = worker_id.strip()
    if not wid:
        raise AjarError("claim falsify requires a non-empty worker_id.", EXIT_GATE_BLOCKED)
    now_iso = utc_now_iso()
    cfg_gate = (config_gate or "").strip()
    with immediate_tx(conn):
        assert_run_mutable(conn, operation="claim_falsify")
        clm = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (claim_id,)).fetchone()
        if clm is None:
            raise AjarError(f"Unknown claim_id: {claim_id}", EXIT_USER_ERROR)
        proposer = str(clm["proposer_worker_id"] or "").strip()
        if proposer == wid:
            raise AjarError(
                f"Fresh-falsifier separation gate: proposer {wid!r} cannot falsify its own claim. "
                "Use an independent falsifier worker.",
                EXIT_GATE_BLOCKED,
            )
        if cfg_gate:
            assert_valid_claim_transition(str(clm["status"]), "config_gated", claim_id=claim_id)
            axes = derive_claim_axes("config_gated")
            conn.execute(
                """
                UPDATE claims
                SET status = 'config_gated', config_gate = ?, falsifier_worker_id = ?,
                    falsify_notes = ?, falsify_control_locus = ?,
                    research_state = ?, evidence_state = ?, updated_at = ?
                WHERE claim_id = ?
                """,
                (
                    scrub_text(cfg_gate),
                    wid,
                    scrub_text(notes),
                    control_locus,
                    axes.research_state.value,
                    axes.evidence_state.value,
                    now_iso,
                    claim_id,
                ),
            )
            probe = on_claim_config_gated(conn, claim_row=clm, config_predicate=cfg_gate)
            log_event(
                conn,
                wid,
                "claim_config_gated",
                claim_id,
                {"config_gate": cfg_gate, "probe_task_id": probe["probe_task_id"]},
            )
            return {
                "claim_id": claim_id,
                "status": "config_gated",
                "config_gate": cfg_gate,
                "probe_task_id": probe["probe_task_id"],
            }

        assert_valid_claim_transition(str(clm["status"]), "falsified", claim_id=claim_id)
        axes = derive_claim_axes("falsified")
        conn.execute(
            """
            UPDATE claims
            SET status = 'falsified', falsifier_worker_id = ?, falsify_notes = ?,
                falsify_control_locus = ?, research_state = ?,
                evidence_state = ?, updated_at = ?
            WHERE claim_id = ?
            """,
            (
                wid,
                scrub_text(notes),
                control_locus,
                axes.research_state.value,
                axes.evidence_state.value,
                now_iso,
                claim_id,
            ),
        )
        conn.execute(
            """
            UPDATE anomalies
            SET status = 'unexplained', consumed_by_id = NULL, updated_at = ?
            WHERE consumed_by_id = ? AND status = 'consumed_by_claim'
            """,
            (now_iso, claim_id),
        )
        consume_hooks_for_locus(conn, source_entity_id=claim_id)
        log_event(conn, wid, "claim_falsified", claim_id, {})
    return {"claim_id": claim_id, "status": "falsified"}


def survive_claim(
    conn: sqlite3.Connection,
    *,
    claim_id: str,
    worker_id: str,
    notes: str,
) -> dict[str, Any]:
    wid = worker_id.strip()
    if not wid:
        raise AjarError("claim survive requires a non-empty worker_id.", EXIT_GATE_BLOCKED)
    now_iso = utc_now_iso()
    with immediate_tx(conn):
        assert_run_mutable(conn, operation="claim_survive")
        clm = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (claim_id,)).fetchone()
        if clm is None:
            raise AjarError(f"Unknown claim_id: {claim_id}", EXIT_USER_ERROR)
        proposer = str(clm["proposer_worker_id"] or "").strip()
        if proposer == wid:
            raise AjarError(
                f"Fresh-falsifier separation gate: proposer {wid!r} cannot validate its own claim. "
                "Use an independent falsifier worker.",
                EXIT_GATE_BLOCKED,
            )
        assert_valid_claim_transition(str(clm["status"]), "survived_falsify", claim_id=claim_id)
        axes = derive_claim_axes("survived_falsify")
        conn.execute(
            """
            UPDATE claims
            SET status = 'survived_falsify', falsifier_worker_id = ?, falsify_notes = ?,
                research_state = ?, evidence_state = ?, env_blocker = '', blocker_reason = '',
                updated_at = ?
            WHERE claim_id = ?
            """,
            (
                wid,
                scrub_text(notes),
                axes.research_state.value,
                axes.evidence_state.value,
                now_iso,
                claim_id,
            ),
        )
        updated_clm = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (claim_id,)).fetchone()
        hooks = on_claim_survived(conn, claim_row=updated_clm)
        log_event(conn, wid, "claim_survived_falsify", claim_id, {})
    return {
        "claim_id": claim_id,
        "status": "survived_falsify",
        "hooks_triggered": [h["hook_code"] for h in hooks],
    }


def block_claim(
    conn: sqlite3.Connection,
    *,
    claim_id: str,
    worker_id: str,
    reason: str,
    env_blocker: str = "",
    target_mode: str = "source",
) -> dict[str, Any]:
    wid = worker_id.strip() or "worker"
    env_b = (env_blocker or "").strip()
    now_iso = utc_now_iso()
    with immediate_tx(conn):
        assert_run_mutable(conn, operation="claim_block")
        clm = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (claim_id,)).fetchone()
        if clm is None:
            raise AjarError(f"Unknown claim_id: {claim_id}", EXIT_USER_ERROR)
        assert_valid_claim_transition(str(clm["status"]), "blocked", claim_id=claim_id)
        ok_blk, blk_msg = validate_claim_block_request(
            clm,
            reason=reason,
            env_blocker=env_b,
            target_mode=target_mode,
        )
        if not ok_blk:
            raise AjarError(blk_msg, EXIT_GATE_BLOCKED)
        axes = derive_claim_axes("blocked")
        conn.execute(
            """
            UPDATE claims
            SET status = 'blocked', blocker_reason = ?, env_blocker = ?,
                research_state = ?, evidence_state = ?, updated_at = ?
            WHERE claim_id = ?
            """,
            (
                scrub_text(reason),
                env_b,
                axes.research_state.value,
                axes.evidence_state.value,
                now_iso,
                claim_id,
            ),
        )
        log_event(
            conn,
            wid,
            "claim_blocked",
            claim_id,
            {"env_blocker": env_b, "reason": reason},
        )
    return {"claim_id": claim_id, "status": "blocked", "env_blocker": env_b}


def advance_phase(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    to_phase: str,
    notes: str = "",
    actor: str = "operator",
    force: bool = False,
) -> dict[str, Any]:
    from ajar.gates import check_all_gates

    new_phase = to_phase.strip()
    if new_phase not in ("hunt", "remediate", "full"):
        raise AjarError(f"Unsupported phase {new_phase!r}; choose hunt, remediate, or full.", EXIT_USER_ERROR)
    clean_actor = actor.strip() or "operator"
    clean_notes = scrub_text((notes or "").strip())
    if force and len(clean_notes) < 8:
        raise AjarError(
            "Forcing phase advance (`--force`) requires `--notes` (>= 8 chars) explaining why remediation cannot wait.",
            EXIT_USER_ERROR,
        )
    with immediate_tx(conn):
        assert_run_mutable(conn, operation="phase_advance")
        run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
        if run is None:
            raise AjarError("Run metadata missing in run.db.", EXIT_USER_ERROR)
        prev_phase = str(run["campaign_phase"] if "campaign_phase" in run.keys() else "hunt") or "hunt"
        assert_valid_phase_transition(prev_phase, new_phase, run_id=run_id)

        if prev_phase == "hunt" and new_phase in ("remediate", "full") and not force:
            all_gates = check_all_gates(conn, auto_enqueue_chain=False, reconcile=False)
            g5 = all_gates["gates"]["G5_anomalies_and_chains"]
            crit_hunt = int(
                conn.execute(
                    """
                    SELECT COUNT(*) AS c FROM tasks
                    WHERE status IN ('open', 'leased')
                      AND priority = 'critical'
                      AND kind IN ('investigate', 'bridge', 'falsify', 'reproduce', 'chain')
                    """
                ).fetchone()["c"]
            )
            if not g5["passed"] or crit_hunt > 0:
                reasons: list[str] = []
                if not g5["passed"]:
                    reasons.append(f"G5 convergence incomplete ({g5.get('issues')})")
                if crit_hunt > 0:
                    reasons.append(f"{crit_hunt} critical hunt/chain/verify task(s) remain open or leased")
                raise AjarError(
                    "Cannot advance from `hunt` to `"
                    + new_phase
                    + "` while high-value hunt/chain frontier remains unfinished: "
                    + "; ".join(reasons)
                    + ". Finish convergence or pass `--force --notes <reason>` for explicit operator override.",
                    EXIT_GATE_BLOCKED,
                )

        conn.execute("UPDATE runs SET campaign_phase = ? WHERE run_id = ?", (new_phase, run_id))
        recompute_all_open_salience(conn)
        if force and prev_phase == "hunt" and new_phase in ("remediate", "full"):
            tid = new_id("tch")
            conn.execute(
                "INSERT INTO human_touches(touch_id, kind, actor, notes, created_at) VALUES (?, 'scope_authority', ?, ?, ?)",
                (tid, clean_actor, f"[phase_advance --force {prev_phase}->{new_phase}] {clean_notes}", utc_now_iso()),
            )
        log_event(
            conn,
            clean_actor,
            "campaign_phase_advanced",
            run_id,
            {
                "previous_phase": prev_phase,
                "campaign_phase": new_phase,
                "forced": bool(force),
                "notes": clean_notes,
            },
        )
    return {
        "run_id": run_id,
        "previous_phase": prev_phase,
        "campaign_phase": new_phase,
        "forced": bool(force),
    }


def finish_run(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    target_dir: pathlib.Path | None = None,
    actor: str = "operator",
) -> dict[str, Any]:
    from ajar.gates import check_all_gates

    with immediate_tx(conn):
        assert_run_mutable(conn, operation="finish_run")
        gates = check_all_gates(conn, target_dir=target_dir, auto_enqueue_chain=True)
        if gates["passed"]:
            now_iso = utc_now_iso()
            conn.execute(
                "UPDATE runs SET status = 'finished', stop_reason = 'all_gates_passed', finished_at = ? WHERE run_id = ?",
                (now_iso, run_id),
            )
            log_event(
                conn,
                actor.strip() or "operator",
                "run_finished",
                run_id,
                {"findings_count": gates.get("findings_count", 0)},
            )
    return gates


def add_surface_driver(
    conn: sqlite3.Connection,
    *,
    surface_id: str,
    setup_cmd: str,
    invoke_template: str,
    teardown_cmd: str = "",
    notes: str = "",
    actor: str = "worker",
) -> dict[str, Any]:
    did = new_id("drv")
    now_iso = utc_now_iso()
    with immediate_tx(conn):
        assert_run_mutable(conn, operation="driver_add")
        conn.execute(
            """
            INSERT INTO surface_drivers(driver_id, surface_id, setup_cmd, invoke_template, teardown_cmd, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                did,
                surface_id,
                scrub_text(setup_cmd),
                scrub_text(invoke_template),
                scrub_text(teardown_cmd or ""),
                scrub_text(notes or ""),
                now_iso,
            ),
        )
        log_event(conn, actor.strip() or "worker", "driver_added", did, {"surface_id": surface_id})
    return {"driver_id": did, "surface_id": surface_id}


def add_task(
    conn: sqlite3.Connection,
    *,
    kind: str,
    title: str,
    locus: str = "",
    subsystem: str | None = None,
    priority: str = "medium",
    direction: str = "outside_in",
    parent_task_id: str | None = None,
    surface_id: str | None = None,
    actor: str = "worker",
) -> dict[str, Any]:
    tid = new_id("task")
    now_iso = utc_now_iso()
    sub = (subsystem or "").strip() or infer_subsystem(locus or "")
    clean_dir = (direction or "outside_in").strip() or "outside_in"
    draft = {
        "priority": priority,
        "subsystem": sub,
        "locus": locus or "",
        "reopened_boost": 0,
    }
    with immediate_tx(conn):
        assert_run_mutable(conn, operation="task_add")
        sal = compute_task_salience(conn, draft)
        conn.execute(
            """
            INSERT INTO tasks(
                task_id, parent_task_id, surface_id, kind, direction, title, subsystem, locus,
                priority, status, salience_score, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)
            """,
            (
                tid,
                parent_task_id,
                surface_id,
                kind,
                clean_dir,
                scrub_text(title),
                sub,
                locus or "",
                priority,
                sal,
                now_iso,
                now_iso,
            ),
        )
        log_event(
            conn,
            actor.strip() or "worker",
            "task_added",
            tid,
            {"kind": kind, "direction": clean_dir, "salience_score": sal},
        )
    return {
        "task_id": tid,
        "kind": kind,
        "direction": clean_dir,
        "subsystem": sub,
        "salience_score": sal,
    }


def add_primitive(
    conn: sqlite3.Connection,
    *,
    locus: str,
    kind: str,
    preconditions: str,
    postconditions: str,
    evidence_cmd: str,
    evidence_output: str = "",
    surface_id: str | None = None,
    subsystem: str | None = None,
    role: str = "capability",
    trusted_invariant: str = "",
    symbols: list[str] | None = None,
    guarded_by_locus: str = "",
    guard_assumption: str = "",
    provides_tags: str | list[str] | None = None,
    requires_tags: str | list[str] | None = None,
    micropatch_path: str | None = None,
    snapshot_id: str = "",
    actor: str = "worker",
) -> dict[str, Any]:
    clean_role = (role or "capability").strip() or "capability"
    if clean_role not in ("capability", "trust_gadget"):
        raise AjarError(f"Unsupported --role {clean_role!r}; choose 'capability' or 'trust_gadget'.", EXIT_USER_ERROR)
    clean_inv = scrub_text((trusted_invariant or "").strip())

    mp_diff = ""
    if micropatch_path and micropatch_path.strip():
        mp_file = pathlib.Path(micropatch_path.strip()).expanduser()
        if not mp_file.is_file():
            raise AjarError(f"Primitive --micropatch file not found: {mp_file}", EXIT_USER_ERROR)
        raw_mp = mp_file.read_text(encoding="utf-8", errors="replace")
        ok_mp, mp_msg, _ = validate_micropatch_diff(raw_mp, max_changed_lines=24, claim_locus=locus)
        if not ok_mp:
            raise AjarError(f"Primitive --micropatch invalid: {mp_msg}", EXIT_GATE_BLOCKED)
        mp_diff = scrub_text(raw_mp[:4000])

    pid = new_id("prim")
    sub = (subsystem or "").strip() or infer_subsystem(locus)
    syms = [s.strip() for s in (symbols or []) if s.strip()]
    guarded_by = (guarded_by_locus or "").strip()
    guard_assump = scrub_text(guard_assumption or "")
    prov_tags = parse_tag_list(provides_tags)
    req_tags = parse_tag_list(requires_tags)
    snap_id = (snapshot_id or "").strip()
    now_iso = utc_now_iso()

    with immediate_tx(conn):
        assert_run_mutable(conn, operation="primitive_add")
        conn.execute(
            """
            INSERT INTO primitives(
                primitive_id, surface_id, subsystem, locus, kind, role, trusted_invariant,
                symbols_json, preconditions, postconditions, guarded_by_locus, guard_assumption,
                provides_tags_json, requires_tags_json, micropatch_diff, snapshot_id,
                evidence_cmd, evidence_output, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
            """,
            (
                pid,
                surface_id,
                sub,
                locus,
                kind,
                clean_role,
                clean_inv,
                json.dumps(syms),
                scrub_text(preconditions),
                scrub_text(postconditions),
                guarded_by,
                guard_assump,
                json.dumps(prov_tags),
                json.dumps(req_tags),
                mp_diff,
                snap_id,
                scrub_text(evidence_cmd),
                scrub_text(evidence_output or ""),
                now_iso,
            ),
        )
        hooks = on_primitive_added(
            conn,
            primitive_id=pid,
            subsystem=sub,
            locus=locus,
            kind=kind,
            guarded_by_locus=guarded_by,
            provides_tags=prov_tags,
            requires_tags=req_tags,
            role=clean_role,
            trusted_invariant=clean_inv,
            symbols=syms,
            snapshot_id=snap_id,
            postconditions=postconditions,
        )
        woken_doors = [
            str(r["door_id"])
            for r in conn.execute(
                "SELECT door_id FROM parked_doors WHERE status = 'ready' AND matched_by_json LIKE '%' || ? || '%'",
                (pid,),
            ).fetchall()
        ]
        log_event(
            conn,
            actor.strip() or "worker",
            "primitive_added",
            pid,
            {
                "locus": locus,
                "kind": kind,
                "role": clean_role,
                "guarded_by_locus": guarded_by,
                "provides_tags": prov_tags,
                "requires_tags": req_tags,
                "woken_doors": woken_doors,
            },
        )
    return {
        "primitive_id": pid,
        "role": clean_role,
        "subsystem": sub,
        "guarded_by_locus": guarded_by,
        "provides_tags": prov_tags,
        "requires_tags": req_tags,
        "symbols": syms,
        "woken_doors": woken_doors,
        "hooks_triggered": [h["hook_code"] for h in hooks],
    }


def record_reproduction_outcome(
    conn: sqlite3.Connection,
    *,
    claim_id: str,
    worker_id: str,
    poc_cmd: str,
    control_cmd: str,
    repro_result: dict[str, Any],
    build_cmd: str = "",
    micropatch_path: str = "",
    oracle_dict: dict[str, Any] | None = None,
    provides_tags: list[str] | None = None,
    declared_steps: int | None = None,
) -> dict[str, Any]:
    """Atomically promote a passed causal reproduction to `findings` with full axis coherence."""
    clean_worker = worker_id.strip() or "worker"
    prov_tags = list(provides_tags or [])
    ub_div = str(repro_result.get("ub_divergence_class") or "")
    snap_meta = repro_result.get("post_state_snapshot")
    arm1_obj = repro_result.get("arm1_clean_poc") or {}
    clean_build_cmd = scrub_text((build_cmd or "").strip())

    with immediate_tx(conn):
        assert_run_mutable(conn, operation="claim_reproduce")
        clm = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (claim_id,)).fetchone()
        if clm is None:
            raise AjarError(f"Unknown claim_id: {claim_id}", EXIT_USER_ERROR)
        assert_valid_claim_transition(str(clm["status"]), "reproduced", claim_id=claim_id)

        if ub_div == "debug_assert_only" and str(clm["severity"]) in ("critical", "high"):
            raise AjarError(
                f"Release-profile UB differential classified {claim_id} as debug_assert_only "
                "(clean --release-cmd exited 0 without post-state violation); rescope severity to low/medium "
                "via `ajar claim rescope` before confirming.",
                EXIT_GATE_BLOCKED,
            )

        now_iso = utc_now_iso()
        snap_id = ""
        if isinstance(snap_meta, dict) and snap_meta.get("ok") and snap_meta.get("snapshot_id"):
            snap_id = str(snap_meta["snapshot_id"])
            conn.execute(
                """
                INSERT OR REPLACE INTO repro_snapshots(
                    snapshot_id, claim_id, rel_dir, archive_path, sha256,
                    size_bytes, manifest_json, source_cmd, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snap_id,
                    claim_id,
                    str(snap_meta["rel_dir"]),
                    str(snap_meta["archive_path"]),
                    str(snap_meta["sha256"]),
                    int(snap_meta["size_bytes"]),
                    json.dumps(snap_meta.get("manifest") or {}, sort_keys=True),
                    str(snap_meta.get("source_cmd") or ""),
                    str(snap_meta.get("created_at") or now_iso),
                ),
            )

        realism = evaluate_precondition_realism(
            conn,
            poc_cmd=poc_cmd,
            control_cmd=control_cmd,
            stdout=str(arm1_obj.get("stdout", "")),
            stderr=str(arm1_obj.get("stderr", "")),
            severity=str(clm["severity"]),
            config_gate=str(clm["config_gate"] if "config_gate" in clm.keys() else ""),
            declared_steps=declared_steps,
            target_locus=str(clm["locus"]),
        )

        existing_f = conn.execute("SELECT finding_id FROM findings WHERE claim_id = ?", (claim_id,)).fetchone()
        fid = str(existing_f["finding_id"]) if existing_f else new_id("fnd")
        attr = finding_attribution_for_claim(conn, clm)
        axes = derive_claim_axes("reproduced")
        conn.execute(
            """
            UPDATE claims
            SET status = 'reproduced', research_state = ?, evidence_state = ?,
                remediation_state = CASE WHEN ? != '' THEN 'micropatched' ELSE remediation_state END,
                updated_at = ?
            WHERE claim_id = ?
            """,
            (
                axes.research_state.value,
                axes.evidence_state.value,
                str(repro_result.get("micropatch_diff") or ""),
                now_iso,
                claim_id,
            ),
        )
        conn.execute(
            """
            UPDATE tasks
            SET status = 'done', worker_id = ?, lease_expires_at = NULL, updated_at = ?
            WHERE parent_claim_id = ? AND kind = 'reproduce' AND status IN ('open', 'leased')
            """,
            (clean_worker, now_iso, claim_id),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO findings(
                finding_id, claim_id, title, severity, locus, root_cause, poc_cmd, control_cmd,
                build_cmd, micropatch_path, micropatch_diff, arm1_clean_poc_json, arm2_clean_ctrl_json,
                arm3_patch_poc_json, arm4_patch_ctrl_json, oracle_json,
                arm5a_release_poc_json, arm5b_release_ctrl_json, ub_divergence_class,
                provides_tags_json, snapshot_id, realism_tier, realism_json,
                attribution, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fid,
                claim_id,
                clm["title"],
                clm["severity"],
                clm["locus"],
                clm["mechanism"],
                scrub_text(poc_cmd),
                scrub_text(control_cmd),
                clean_build_cmd,
                str(micropatch_path or ""),
                str(repro_result.get("micropatch_diff") or ""),
                json.dumps(repro_result["arm1_clean_poc"], sort_keys=True),
                json.dumps(repro_result["arm2_clean_control"], sort_keys=True),
                json.dumps(repro_result["arm3_patch_poc"], sort_keys=True),
                json.dumps(repro_result["arm4_patch_control"], sort_keys=True),
                json.dumps(oracle_dict or {}, sort_keys=True),
                json.dumps(repro_result.get("arm5a_release_poc") or {}, sort_keys=True),
                json.dumps(repro_result.get("arm5b_release_control") or {}, sort_keys=True),
                ub_div,
                json.dumps(prov_tags),
                snap_id,
                str(realism["realism_tier"]),
                json.dumps(realism, sort_keys=True),
                attr,
                now_iso,
            ),
        )
        if realism["realism_tier"] == "crown_jewel" and realism.get("jewel_id"):
            conn.execute(
                "UPDATE crown_jewels SET status = 'reached', reached_by_id = ?, updated_at = ? WHERE jewel_id = ?",
                (fid, now_iso, str(realism["jewel_id"])),
            )

        dup_axes = derive_claim_axes("duplicate_root_cause")
        for dup_id in repro_result.get("cross_killed_claim_ids") or []:
            conn.execute(
                """
                UPDATE claims
                SET status = 'duplicate_root_cause', duplicate_of_claim_id = ?,
                    research_state = ?, evidence_state = ?, updated_at = ?
                WHERE claim_id = ? AND status = 'survived_falsify'
                """,
                (
                    claim_id,
                    dup_axes.research_state.value,
                    dup_axes.evidence_state.value,
                    now_iso,
                    dup_id,
                ),
            )

        esc = on_finding_confirmed(
            conn,
            finding_id=fid,
            claim_row=clm,
            provides_tags=prov_tags,
            snapshot_id=snap_id,
            realism_tier=str(realism["realism_tier"]),
        )
        log_event(
            conn,
            clean_worker,
            "finding_reproduced",
            fid,
            {
                "claim_id": claim_id,
                "attribution": attr,
                "realism_tier": realism["realism_tier"],
                "snapshot_id": snap_id,
                "ub_divergence_class": ub_div,
            },
        )

    out_payload: dict[str, Any] = {
        "finding_id": fid,
        "attribution": attr,
        "realism_tier": realism["realism_tier"],
        "snapshot_id": snap_id,
        "reproduction": repro_result,
    }
    if esc is not None:
        out_payload["post_confirm_escalation"] = esc
    return out_payload


def preflight_chain_proposal(conn: sqlite3.Connection, steps: list[str]) -> None:
    """Fail fast before running PoC subprocesses if run is sealed or any step primitive is terminal."""
    assert_run_mutable(conn, operation="chain_propose")
    for sid in steps:
        prow = conn.execute("SELECT status FROM primitives WHERE primitive_id = ?", (sid,)).fetchone()
        if prow is not None:
            assert_valid_primitive_transition(str(prow["status"]), "chained", primitive_id=sid)


def record_chain_proposal(
    conn: sqlite3.Connection,
    *,
    title: str,
    severity: str,
    steps: list[str],
    poc_cmd: str,
    control_cmd: str,
    verified: bool,
    evidence: dict[str, Any],
    actor: str = "worker",
) -> dict[str, Any]:
    cid = new_id("chn")
    now_iso = utc_now_iso()
    with immediate_tx(conn):
        assert_run_mutable(conn, operation="chain_propose")
        for sid in steps:
            prow = conn.execute("SELECT status FROM primitives WHERE primitive_id = ?", (sid,)).fetchone()
            if prow is not None:
                assert_valid_primitive_transition(str(prow["status"]), "chained", primitive_id=sid)
        conn.execute(
            """
            INSERT INTO chains(chain_id, title, severity, step_ids_json, e2e_poc_cmd, control_cmd, verified, evidence_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cid,
                scrub_text(title),
                severity,
                json.dumps(steps),
                scrub_text(poc_cmd),
                scrub_text(control_cmd),
                1 if verified else 0,
                json.dumps(evidence, sort_keys=True),
                now_iso,
            ),
        )
        if verified:
            for sid in steps:
                conn.execute(
                    "UPDATE primitives SET chained = 1, status = 'chained' WHERE primitive_id = ?",
                    (sid,),
                )
                conn.execute(
                    "UPDATE anomalies SET status = 'consumed_by_chain', consumed_by_id = ?, updated_at = ? WHERE anomaly_id = ?",
                    (cid, now_iso, sid),
                )
        log_event(conn, actor.strip() or "worker", "chain_proposed", cid, {"verified": verified, "steps": steps})
    return {"chain_id": cid, "verified": verified, "evidence": evidence}


def record_human_touch(
    conn: sqlite3.Connection,
    *,
    kind: str,
    actor: str,
    notes: str,
) -> dict[str, Any]:
    tid = new_id("tch")
    now_iso = utc_now_iso()
    clean_actor = scrub_text(actor.strip() or "operator")
    with immediate_tx(conn):
        assert_run_mutable(conn, operation="touch_add")
        conn.execute(
            "INSERT INTO human_touches(touch_id, kind, actor, notes, created_at) VALUES (?, ?, ?, ?, ?)",
            (tid, kind, clean_actor, scrub_text(notes), now_iso),
        )
        log_event(conn, clean_actor, "human_touch_recorded", tid, {"kind": kind})
    return {"touch_id": tid, "kind": kind}


def record_spend_entry(
    conn: sqlite3.Connection,
    *,
    worker_id: str,
    phase: str,
    cost_usd: float,
    surface_id: str = "",
    model: str = "",
    tokens_in: int = 0,
    tokens_out: int = 0,
    notes: str = "",
) -> dict[str, Any]:
    eid = new_id("spd")
    surf = (surface_id or "").strip()
    now_iso = utc_now_iso()
    with immediate_tx(conn):
        assert_run_mutable(conn, operation="spend_add")
        conn.execute(
            """
            INSERT INTO spend_ledger(entry_id, worker_id, surface_id, phase, model, tokens_in, tokens_out, cost_usd, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                eid,
                worker_id,
                surf,
                phase,
                model or "",
                int(tokens_in),
                int(tokens_out),
                float(cost_usd),
                scrub_text(notes or ""),
                now_iso,
            ),
        )
    return {"entry_id": eid, "surface_id": surf, "cost_usd": float(cost_usd)}


def cast_lead_vote(
    conn: sqlite3.Connection,
    *,
    worker_id: str,
    target_kind: str,
    target_id: str = "",
    locus: str = "",
    subsystem: str = "",
    impact_score: int = 7,
    plausibility_score: int = 7,
    chainability_score: int = 7,
    effort_cost: int = 5,
    rationale: str = "",
) -> dict[str, Any]:
    wid = (worker_id or "").strip()
    if not wid:
        raise AjarError("lead vote requires a non-empty --worker.", EXIT_USER_ERROR)
    tk = (target_kind or "").strip()
    if tk not in ("surface", "door", "slice", "chain", "subsystem", "claim", "primitive", "finding"):
        raise AjarError(
            f"Unsupported --target-kind {tk!r}; choose surface, door, slice, chain, subsystem, claim, primitive, or finding.",
            EXIT_USER_ERROR,
        )
    tid = (target_id or "").strip()
    loc = (locus or "").strip()
    sub = (subsystem or "").strip() or (infer_subsystem(loc) if loc else "")
    if not (tid or loc or sub):
        raise AjarError(
            "lead vote requires at least one of --target-id, --locus, or --subsystem.",
            EXIT_USER_ERROR,
        )
    for name, val in (
        ("impact_score", impact_score),
        ("plausibility_score", plausibility_score),
        ("chainability_score", chainability_score),
        ("effort_cost", effort_cost),
    ):
        if not (1 <= int(val) <= 10):
            raise AjarError(f"{name} must be an integer between 1 and 10 (got {val}).", EXIT_USER_ERROR)

    ev = compute_lead_ev_formula(
        impact_score=int(impact_score),
        plausibility_score=int(plausibility_score),
        chainability_score=int(chainability_score),
        effort_cost=int(effort_cost),
    )
    clean_rat = scrub_text((rationale or "").strip())
    now_iso = utc_now_iso()

    with immediate_tx(conn):
        assert_run_mutable(conn, operation="lead_vote")
        existing = conn.execute(
            """
            SELECT vote_id FROM lead_votes
            WHERE worker_id = ? AND target_kind = ? AND target_id = ? AND locus = ? AND subsystem = ?
            """,
            (wid, tk, tid, loc, sub),
        ).fetchone()
        if existing is not None:
            vid = str(existing["vote_id"])
            conn.execute(
                """
                UPDATE lead_votes
                SET impact_score = ?, plausibility_score = ?, chainability_score = ?,
                    effort_cost = ?, ev_score = ?, rationale = ?, updated_at = ?
                WHERE vote_id = ?
                """,
                (
                    int(impact_score),
                    int(plausibility_score),
                    int(chainability_score),
                    int(effort_cost),
                    float(ev),
                    clean_rat,
                    now_iso,
                    vid,
                ),
            )
        else:
            vid = new_id("vot")
            conn.execute(
                """
                INSERT INTO lead_votes(
                    vote_id, worker_id, target_kind, target_id, locus, subsystem,
                    impact_score, plausibility_score, chainability_score, effort_cost,
                    ev_score, rationale, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    vid,
                    wid,
                    tk,
                    tid,
                    loc,
                    sub,
                    int(impact_score),
                    int(plausibility_score),
                    int(chainability_score),
                    int(effort_cost),
                    float(ev),
                    clean_rat,
                    now_iso,
                    now_iso,
                ),
            )
        rescored = recompute_all_open_salience(conn)
        log_event(
            conn,
            wid,
            "lead_vote_cast",
            vid,
            {
                "target_kind": tk,
                "target_id": tid,
                "locus": loc,
                "subsystem": sub,
                "ev_score": ev,
                "tasks_rescored": rescored,
            },
        )
    return {
        "vote_id": vid,
        "worker_id": wid,
        "target_kind": tk,
        "target_id": tid,
        "locus": loc,
        "subsystem": sub,
        "ev_score": ev,
        "tasks_rescored": rescored,
    }


def rank_leads(
    conn: sqlite3.Connection,
    *,
    target_kind: str = "",
    limit: int = 25,
) -> dict[str, Any]:
    tk = (target_kind or "").strip()
    params: list[Any] = []
    where = ""
    if tk:
        where = "WHERE target_kind = ?"
        params.append(tk)
    params.append(max(1, int(limit)))
    rows = conn.execute(
        f"""
        SELECT
            target_kind,
            target_id,
            locus,
            subsystem,
            COUNT(DISTINCT worker_id) AS voter_count,
            ROUND(AVG(ev_score), 2) AS mean_ev,
            ROUND(MAX(ev_score), 2) AS max_ev,
            ROUND(AVG(impact_score), 2) AS mean_impact,
            ROUND(AVG(plausibility_score), 2) AS mean_plausibility,
            ROUND(AVG(chainability_score), 2) AS mean_chainability,
            ROUND(AVG(effort_cost), 2) AS mean_effort_cost,
            ROUND(AVG(ev_score) + MIN(12.0, (COUNT(DISTINCT worker_id) - 1) * 4.0), 2) AS consensus_ev
        FROM lead_votes
        {where}
        GROUP BY target_kind, target_id, locus, subsystem
        ORDER BY consensus_ev DESC, voter_count DESC, mean_ev DESC
        LIMIT ?
        """,
        tuple(params),
    ).fetchall()
    throttles = compute_root_plateau_throttles(conn)
    ranked: list[dict[str, Any]] = []
    for idx, r in enumerate(rows, start=1):
        d = dict(r)
        d["rank"] = idx
        rfile = str(d.get("locus") or "").split(":", 1)[0].strip().lstrip("./")
        d["root_throttled"] = bool(throttles.get(rfile, {}).get("throttled", False)) if rfile else False
        ranked.append(d)
    return {
        "ranked_leads": ranked,
        "total_votes": int(conn.execute("SELECT COUNT(*) AS c FROM lead_votes").fetchone()["c"]),
        "root_plateau_throttles": list(throttles.values()),
    }


def mark_claim_duplicate(
    conn: sqlite3.Connection,
    *,
    claim_id: str,
    duplicate_of_claim_id: str,
    worker_id: str,
    reason: str,
) -> dict[str, Any]:
    wid = (worker_id or "").strip() or "worker"
    parent_id = (duplicate_of_claim_id or "").strip()
    clean_reason = scrub_text((reason or "").strip())
    if not parent_id or parent_id == claim_id:
        raise AjarError("--of must reference a distinct existing claim_id.", EXIT_USER_ERROR)
    if len(clean_reason) < 8:
        raise AjarError("claim duplicate --reason must be at least 8 characters.", EXIT_USER_ERROR)
    now_iso = utc_now_iso()
    with immediate_tx(conn):
        assert_run_mutable(conn, operation="claim_duplicate")
        clm = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (claim_id,)).fetchone()
        if clm is None:
            raise AjarError(f"Unknown claim_id: {claim_id}", EXIT_USER_ERROR)
        parent = conn.execute("SELECT claim_id FROM claims WHERE claim_id = ?", (parent_id,)).fetchone()
        if parent is None:
            raise AjarError(f"Unknown parent claim_id: {parent_id}", EXIT_USER_ERROR)
        assert_valid_claim_transition(str(clm["status"]), "duplicate_root_cause", claim_id=claim_id)
        axes = derive_claim_axes("duplicate_root_cause")
        conn.execute(
            """
            UPDATE claims
            SET status = 'duplicate_root_cause',
                duplicate_of_claim_id = ?,
                same_root_claim_id = ?,
                research_state = ?,
                evidence_state = ?,
                falsify_notes = ?,
                updated_at = ?
            WHERE claim_id = ?
            """,
            (
                parent_id,
                parent_id,
                axes.research_state.value,
                axes.evidence_state.value,
                clean_reason,
                now_iso,
                claim_id,
            ),
        )
        conn.execute(
            """
            UPDATE tasks
            SET status = 'done', worker_id = ?, summary = ?, lease_expires_at = NULL, updated_at = ?
            WHERE parent_claim_id = ? AND status IN ('open', 'leased')
            """,
            (wid, f"Closed as duplicate_root_cause of {parent_id}: {clean_reason[:120]}", now_iso, claim_id),
        )
        consume_hooks_for_locus(conn, source_entity_id=claim_id)
        log_event(
            conn,
            wid,
            "claim_marked_duplicate",
            claim_id,
            {"duplicate_of_claim_id": parent_id, "reason": clean_reason[:200]},
        )
    return {
        "claim_id": claim_id,
        "status": "duplicate_root_cause",
        "duplicate_of_claim_id": parent_id,
    }


def calibrate_chain(
    conn: sqlite3.Connection,
    *,
    chain_id: str,
    reason: str,
    realism_tier: str | None = None,
    severity: str | None = None,
    declared_steps: int | None = None,
    worker_id: str = "operator",
) -> dict[str, Any]:
    clean_reason = scrub_text((reason or "").strip())
    if len(clean_reason) < 8:
        raise AjarError("Chain calibration --reason must be at least 8 characters.", EXIT_USER_ERROR)
    if realism_tier and realism_tier not in ("crown_jewel", "high_impact", "stepping_stone"):
        raise AjarError(f"Unsupported --realism-tier: {realism_tier!r}", EXIT_USER_ERROR)
    if severity and severity not in ("critical", "high", "medium", "low"):
        raise AjarError(f"Unsupported --severity: {severity!r}", EXIT_USER_ERROR)
    wid = (worker_id or "").strip() or "operator"
    now_iso = utc_now_iso()

    with immediate_tx(conn):
        assert_run_mutable(conn, operation="chain_calibrate")
        crow = conn.execute("SELECT * FROM chains WHERE chain_id = ?", (chain_id,)).fetchone()
        if crow is None:
            raise AjarError(f"Unknown chain_id: {chain_id}", EXIT_USER_ERROR)
        new_sev = (severity or str(crow["severity"])).strip().lower()
        cur_tier = str(crow["realism_tier"] if "realism_tier" in crow.keys() else "stepping_stone")
        new_tier = realism_tier if realism_tier else ("stepping_stone" if new_sev in ("medium", "low") else cur_tier)
        try:
            r_obj = json.loads(str(crow["realism_json"] or "{}"))
        except (ValueError, TypeError):
            r_obj = {}
        if declared_steps is not None:
            r_obj["declared_steps"] = max(1, int(declared_steps))
            r_obj["estimated_steps"] = max(1, int(declared_steps))
        r_obj["realism_tier"] = new_tier
        r_obj["calibration_notes"] = clean_reason

        conn.execute(
            """
            UPDATE chains
            SET severity = ?, realism_tier = ?, realism_json = ?
            WHERE chain_id = ?
            """,
            (new_sev, new_tier, json.dumps(r_obj, sort_keys=True), chain_id),
        )
        j_id = str(crow["jewel_id"] or "").strip()
        if j_id and cur_tier == "crown_jewel" and new_tier != "crown_jewel":
            conn.execute(
                """
                UPDATE crown_jewels
                SET status = 'locked', reached_by_id = '', updated_at = ?
                WHERE jewel_id = ? AND reached_by_id = ?
                """,
                (now_iso, j_id, chain_id),
            )
        elif j_id and new_tier == "crown_jewel" and int(crow["verified"] or 0) == 1:
            conn.execute(
                """
                UPDATE crown_jewels
                SET status = 'reached', reached_by_id = ?, updated_at = ?
                WHERE jewel_id = ?
                """,
                (chain_id, now_iso, j_id),
            )
        if wid == "operator":
            conn.execute(
                "INSERT INTO human_touches(touch_id, kind, actor, notes, created_at) VALUES (?, 'scope_authority', 'operator', ?, ?)",
                (new_id("tch"), f"calibrate chain {chain_id} -> {new_sev}/{new_tier}: {clean_reason[:140]}", now_iso),
            )
        log_event(
            conn,
            wid,
            "chain_calibrated",
            chain_id,
            {
                "old_severity": crow["severity"],
                "new_severity": new_sev,
                "old_realism_tier": cur_tier,
                "realism_tier": new_tier,
                "declared_steps": declared_steps,
                "reason": clean_reason[:200],
            },
        )
    return {
        "chain_id": chain_id,
        "severity": new_sev,
        "realism_tier": new_tier,
        "declared_steps": r_obj.get("declared_steps"),
        "reason": clean_reason,
    }


def close_run_early(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    stop_reason: str,
    notes: str,
    target_dir: pathlib.Path | None = None,
    actor: str = "operator",
) -> dict[str, Any]:
    """Explicitly close a run without claiming `all_gates_passed` when stopped by operator or window."""
    from ajar.gates import check_all_gates

    sr = (stop_reason or "").strip()
    if sr not in ("stopped_by_operator", "window_reached", "superseded"):
        raise AjarError(
            f"Unsupported --reason {sr!r}; choose stopped_by_operator, window_reached, or superseded.",
            EXIT_USER_ERROR,
        )
    clean_notes = scrub_text((notes or "").strip())
    if len(clean_notes) < 8:
        raise AjarError("`ajar close` requires `--notes` (>= 8 chars) recording why the run stopped.", EXIT_USER_ERROR)
    clean_actor = (actor or "").strip() or "operator"
    now_iso = utc_now_iso()

    with immediate_tx(conn):
        assert_run_mutable(conn, operation="close_run")
        gates = check_all_gates(conn, target_dir=target_dir, auto_enqueue_chain=False, reconcile=False)
        conn.execute(
            "UPDATE runs SET status = 'finished', stop_reason = ?, finished_at = ? WHERE run_id = ?",
            (sr, now_iso, run_id),
        )
        conn.execute(
            "INSERT INTO human_touches(touch_id, kind, actor, notes, created_at) VALUES (?, 'scope_authority', ?, ?, ?)",
            (new_id("tch"), clean_actor, f"[ajar close:{sr}] {clean_notes}", now_iso),
        )
        log_event(
            conn,
            clean_actor,
            "run_closed_early",
            run_id,
            {
                "stop_reason": sr,
                "gates_passed": bool(gates["passed"]),
                "findings_count": gates.get("findings_count", 0),
                "notes": clean_notes[:240],
            },
        )
    return {
        "run_id": run_id,
        "status": "finished",
        "stop_reason": sr,
        "gates_passed": bool(gates["passed"]),
        "findings_count": gates.get("findings_count", 0),
        "blockers_at_close": gates.get("blockers", []),
    }


_CLAIM_ID_TOKEN_RE = re.compile(r"\bclm-[A-Za-z0-9_-]{4,}\b")
_DOOR_ID_TOKEN_RE = re.compile(r"\bdoor-[A-Za-z0-9_-]{4,}\b")

TASK_KIND_SKILL_PATHS: dict[str, str] = {
    "map": "skills/ajar-map/SKILL.md",
    "investigate": "skills/ajar-investigate/SKILL.md",
    "bridge": "skills/ajar-chain/SKILL.md",
    "falsify": "skills/ajar-falsify/SKILL.md",
    "reproduce": "skills/ajar-reproduce/SKILL.md",
    "instrument": "skills/ajar-reproduce/SKILL.md",
    "chain": "skills/ajar-chain/SKILL.md",
    "escalate": "skills/ajar-chain/SKILL.md",
    "patch": "skills/ajar-patch/SKILL.md",
    "report": "skills/ajar-report/SKILL.md",
}

TASK_KIND_ROLE_LABELS: dict[str, str] = {
    "map": "Swarm Mapper",
    "investigate": "Swarm Investigator",
    "bridge": "Swarm Bridge Hunter",
    "falsify": "Swarm Falsifier",
    "reproduce": "Swarm Reproducer",
    "instrument": "Swarm Instrumentor",
    "chain": "Swarm Chain Worker",
    "escalate": "Swarm Escalation Hunter",
    "patch": "Swarm Patch Verifier",
    "report": "Swarm Reporter",
}


def _norm_locus_file(locus: str) -> str:
    return (locus or "").split(":", 1)[0].strip().lstrip("./")


def _single_line(text: str, max_chars: int = 140) -> str:
    cleaned = re.sub(r"\s+", " ", scrub_text(text or "").replace("\r", " ").replace("\n", " ")).strip()
    return cleaned[:max_chars]


def _resolve_task_door_id(task_row: sqlite3.Row | dict[str, Any]) -> str:
    keys = set(task_row.keys())
    explicit = str(task_row["door_id"] or "").strip() if "door_id" in keys else ""
    if explicit:
        return explicit
    blob = f"{task_row['title'] if 'title' in keys else ''} {task_row['summary'] if 'summary' in keys else ''}"
    m = _DOOR_ID_TOKEN_RE.search(blob)
    return m.group(0) if m else ""


def _resolve_task_claim(
    conn: sqlite3.Connection,
    task_row: sqlite3.Row | dict[str, Any],
) -> dict[str, Any] | None:
    keys = set(task_row.keys())
    parent_cid = str(task_row["parent_claim_id"] or "").strip() if "parent_claim_id" in keys else ""
    if parent_cid:
        crow = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (parent_cid,)).fetchone()
        if crow is not None:
            return dict(crow)

    blob = f"{task_row['title'] if 'title' in keys else ''} {task_row['summary'] if 'summary' in keys else ''}"
    m = _CLAIM_ID_TOKEN_RE.search(blob)
    if m:
        crow = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (m.group(0),)).fetchone()
        if crow is not None:
            return dict(crow)

    kind = str(task_row["kind"] or "") if "kind" in keys else ""
    loc = str(task_row["locus"] or "").strip() if "locus" in keys else ""
    if kind in ("falsify", "reproduce", "instrument", "patch") and loc:
        want_statuses = (
            ("proposed",)
            if kind == "falsify"
            else ("survived_falsify", "needs_instrumentation")
            if kind in ("reproduce", "instrument")
            else ("reproduced",)
        )
        placeholders = ",".join("?" for _ in want_statuses)
        crow = conn.execute(
            f"""
            SELECT * FROM claims
            WHERE locus = ? AND status IN ({placeholders})
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (loc, *want_statuses),
        ).fetchone()
        if crow is not None:
            return dict(crow)
        loc_file = _norm_locus_file(loc)
        if loc_file and kind == "falsify":
            crow = conn.execute(
                """
                SELECT * FROM claims
                WHERE status = 'proposed' AND (locus = ? OR locus LIKE ? || ':%')
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (loc_file, loc_file),
            ).fetchone()
            if crow is not None:
                return dict(crow)
    return None


def _count_discoveries_since_task(
    conn: sqlite3.Connection,
    oldest_task: sqlite3.Row | dict[str, Any],
) -> tuple[int, int]:
    """Count `(claims, active_primitives)` created after `oldest_task` finished (with `events.event_id` tie-breaking)."""
    oldest_tid = str(oldest_task["task_id"] or "")
    oldest_ts = str(oldest_task["updated_at"] or "")
    ev_row = conn.execute(
        "SELECT MAX(event_id) AS eid FROM events WHERE action IN ('task_done', 'task_dry') AND entity_id = ?",
        (oldest_tid,),
    ).fetchone()
    oldest_eid = int(ev_row["eid"] or 0) if ev_row is not None else 0

    claims_since = 0
    for crow in conn.execute("SELECT claim_id, created_at FROM claims").fetchall():
        cts = str(crow["created_at"] or "")
        if cts > oldest_ts:
            claims_since += 1
        elif cts == oldest_ts and oldest_eid > 0:
            ce = conn.execute(
                "SELECT MAX(event_id) AS eid FROM events WHERE action = 'claim_proposed' AND entity_id = ?",
                (str(crow["claim_id"]),),
            ).fetchone()
            if ce is not None and int(ce["eid"] or 0) > oldest_eid:
                claims_since += 1

    prims_since = 0
    for prow in conn.execute("SELECT primitive_id, created_at FROM primitives WHERE status != 'dry'").fetchall():
        pts = str(prow["created_at"] or "")
        if pts > oldest_ts:
            prims_since += 1
        elif pts == oldest_ts and oldest_eid > 0:
            pe = conn.execute(
                "SELECT MAX(event_id) AS eid FROM events WHERE action = 'primitive_added' AND entity_id = ?",
                (str(prow["primitive_id"]),),
            ).fetchone()
            if pe is not None and int(pe["eid"] or 0) > oldest_eid:
                prims_since += 1

    return (claims_since, prims_since)


def _collect_backslice_unvisited_candidates(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Collect unvisited backward-sink-cone (`backslice`) caller files across Crown Jewels, Open Doors, and high surfaces."""
    sink_targets: list[tuple[int, str]] = []
    for cj in list_crown_jewels(conn):
        if str(cj.get("status") or "locked") != "reached":
            sink_targets.append((0, str(cj["jewel_id"])))
    for drow in conn.execute(
        "SELECT door_id FROM parked_doors WHERE status IN ('parked', 'bridging') ORDER BY updated_at DESC LIMIT 4"
    ).fetchall():
        sink_targets.append((1, str(drow["door_id"])))
    for srow in conn.execute(
        "SELECT locus FROM surfaces WHERE priority IN ('critical', 'high') ORDER BY created_at ASC LIMIT 4"
    ).fetchall():
        sloc = str(srow["locus"] or "").strip()
        if sloc:
            sink_targets.append((2, sloc))

    best_by_file: dict[str, dict[str, Any]] = {}
    for tier, sink_ref in sink_targets[:8]:
        bs = trace_backward_sink_slices(conn, sink=sink_ref, max_hops=4, limit=10)
        for u in bs.get("unvisited_caller_files") or []:
            ufile = _norm_locus_file(str(u.get("file") or ""))
            if not ufile:
                continue
            cand: dict[str, Any] = {
                "file": ufile,
                "locus": f"{ufile}:1",
                "tier": tier,
                "hop": int(u.get("hop") or 1),
                "path_weight": float(u.get("path_weight") or 0.0),
                "sink_resolved": str(bs.get("sink_resolved") or sink_ref),
                "via_symbols": list(u.get("via_symbols") or []),
            }
            prev = best_by_file.get(ufile)
            if prev is None or (int(cand["tier"]), int(cand["hop"]), -float(cand["path_weight"])) < (
                int(prev["tier"]),
                int(prev["hop"]),
                -float(prev["path_weight"]),
            ):
                best_by_file[ufile] = cand

    ranked = list(best_by_file.values())
    ranked.sort(key=lambda c: (int(c["tier"]), int(c["hop"]), -float(c["path_weight"]), str(c["file"])))
    return ranked


def plan_swarm_wave(
    conn: sqlite3.Connection,
    *,
    max_workers: int = 6,
    enqueue_missing: bool = True,
    stall_window: int = 6,
) -> dict[str, Any]:
    """Plan a disjoint parallel Swarm wave (`<= max_workers`), breaking discovery stalls and bridging Middle Unicorns."""
    if int(max_workers) < 1:
        raise AjarError("max_workers must be >= 1.", EXIT_USER_ERROR)
    if int(stall_window) < 1:
        raise AjarError("stall_window must be >= 1.", EXIT_USER_ERROR)

    cap_workers = int(max_workers)
    win = int(stall_window)
    can_enqueue = bool(enqueue_missing)

    run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
    if run is None:
        raise AjarError("Run metadata missing in run.db.", EXIT_USER_ERROR)
    run_id = str(run["run_id"])
    run_status = str(run["status"] or "active")
    campaign_phase = str(run["campaign_phase"] if "campaign_phase" in run.keys() else "hunt") or "hunt"
    tpath = pathlib.Path(str(run["target_path"])) if run["target_path"] else None

    spawned_stall_tasks: list[str] = []
    spawned_unicorn_tasks: list[str] = []
    spawned_verify_tasks: list[str] = []
    spawned_chain_tasks: list[str] = []

    if can_enqueue:
        with immediate_tx(conn):
            assert_run_mutable(conn, operation="swarm_plan")
            now_ep = time.time()
            now_iso = utc_now_iso()
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
                (now_iso, now_ep),
            )

            unvisited_slices = list_unvisited_slices(conn, target_dir=tpath, populate_if_empty=True)
            percolation = detect_percolated_multi_hop_paths(conn, enqueue_tasks=True)
            spawned_chain_tasks = list(percolation.get("spawned_chain_tasks") or [])

            # Ensure proposed / survived_falsify claims have open falsify / reproduce tasks in the queue.
            for clm in conn.execute("SELECT * FROM claims WHERE status = 'proposed' ORDER BY created_at ASC").fetchall():
                cid = str(clm["claim_id"])
                cloc = str(clm["locus"] or "")
                existing_fal = conn.execute(
                    """
                    SELECT 1 FROM tasks
                    WHERE kind = 'falsify' AND status IN ('open', 'leased')
                      AND (parent_claim_id = ? OR title LIKE '%' || ? || '%' OR summary LIKE '%' || ? || '%' OR locus = ?)
                    LIMIT 1
                    """,
                    (cid, cid, cid, cloc),
                ).fetchone()
                if existing_fal is None:
                    ftid = new_id("task")
                    conn.execute(
                        """
                        INSERT INTO tasks(
                            task_id, parent_claim_id, surface_id, kind, direction, title, subsystem, locus,
                            priority, status, salience_score, summary, created_at, updated_at
                        ) VALUES (?, ?, ?, 'falsify', 'outside_in', ?, ?, ?, ?, 'open', 92, ?, ?, ?)
                        """,
                        (
                            ftid,
                            cid,
                            clm["surface_id"],
                            f"Falsify claim {cid}: {str(clm['title'])[:72]}",
                            str(clm["subsystem"] or infer_subsystem(cloc)),
                            cloc,
                            str(clm["severity"] or "high"),
                            f"Independent falsification check (`worker != {clm['proposer_worker_id']}`) for {cid}.",
                            now_iso,
                            now_iso,
                        ),
                    )
                    spawned_verify_tasks.append(ftid)

            for clm in conn.execute(
                "SELECT * FROM claims WHERE status = 'survived_falsify' ORDER BY created_at ASC"
            ).fetchall():
                cid = str(clm["claim_id"])
                cloc = str(clm["locus"] or "")
                existing_rep = conn.execute(
                    """
                    SELECT 1 FROM tasks
                    WHERE kind = 'reproduce' AND status IN ('open', 'leased')
                      AND (parent_claim_id = ? OR title LIKE '%' || ? || '%' OR summary LIKE '%' || ? || '%' OR locus = ?)
                    LIMIT 1
                    """,
                    (cid, cid, cid, cloc),
                ).fetchone()
                if existing_rep is None:
                    rtid = new_id("task")
                    conn.execute(
                        """
                        INSERT INTO tasks(
                            task_id, parent_claim_id, surface_id, kind, direction, title, subsystem, locus,
                            priority, status, salience_score, summary, created_at, updated_at
                        ) VALUES (?, ?, ?, 'reproduce', 'outside_in', ?, ?, ?, ?, 'open', 95, ?, ?, ?)
                        """,
                        (
                            rtid,
                            cid,
                            clm["surface_id"],
                            f"Reproduce claim {cid} with 4-arm proof",
                            str(clm["subsystem"] or infer_subsystem(cloc)),
                            cloc,
                            str(clm["severity"] or "high"),
                            f"Execute 4-arm causal reproduction for {cid}.",
                            now_iso,
                            now_iso,
                        ),
                    )
                    spawned_verify_tasks.append(rtid)

            recent_terminal = conn.execute(
                """
                SELECT * FROM tasks
                WHERE status IN ('done', 'dry')
                ORDER BY COALESCE(closed_epoch, 0.0) DESC, updated_at DESC, rowid DESC
                LIMIT ?
                """,
                (win,),
            ).fetchall()
            claims_since_window = 0
            primitives_since_window = 0
            discovery_stalled = False
            if len(recent_terminal) >= win and len(unvisited_slices) > 0:
                claims_since_window, primitives_since_window = _count_discoveries_since_task(
                    conn, recent_terminal[-1]
                )
                discovery_stalled = claims_since_window == 0 and primitives_since_window == 0

            # 1. Discovery-Stall Circuit Breaker (hunt phase -> <= 2 fresh investigate tasks on unvisited slices)
            if discovery_stalled and campaign_phase == "hunt" and run_status != "verify_only":
                open_stall_cnt = int(
                    conn.execute(
                        """
                        SELECT COUNT(*) AS c FROM tasks
                        WHERE kind = 'investigate' AND status IN ('open', 'leased') AND summary LIKE '%[stall-breaker]%'
                        """
                    ).fetchone()["c"]
                )
                stall_budget = max(0, 2 - open_stall_cnt)
                active_explore_files = {
                    _norm_locus_file(str(r["locus"] or ""))
                    for r in conn.execute(
                        "SELECT locus FROM tasks WHERE status IN ('open', 'leased') AND locus != ''"
                    ).fetchall()
                }
                active_explore_files.discard("")

                stall_targets: list[tuple[str, str, str, str]] = []  # (file, locus, direction, note)
                for bc in _collect_backslice_unvisited_candidates(conn):
                    bf = str(bc["file"])
                    if bf in active_explore_files or any(x[0] == bf for x in stall_targets):
                        continue
                    syms_note = f" via {','.join(bc['via_symbols'][:2])}" if bc.get("via_symbols") else ""
                    stall_targets.append(
                        (
                            bf,
                            str(bc["locus"]),
                            "inside_out",
                            f"[stall-breaker] Unvisited {bc['hop']}-hop backward-sink slice into {bc['sink_resolved']}{syms_note}.",
                        )
                    )
                    if len(stall_targets) >= stall_budget:
                        break

                if len(stall_targets) < stall_budget:
                    for slc in unvisited_slices:
                        cand_loci = [str(slc["seed_locus"])]
                        for extra in slc.get("files") or []:
                            ef = _norm_locus_file(str(extra))
                            if ef and ef != _norm_locus_file(str(slc["seed_locus"])):
                                cand_loci.append(f"{ef}:1")
                        for cloc in cand_loci:
                            cf = _norm_locus_file(cloc)
                            if not cf or cf in active_explore_files or any(x[0] == cf for x in stall_targets):
                                continue
                            stall_targets.append(
                                (
                                    cf,
                                    cloc,
                                    "outside_in",
                                    f"[stall-breaker] Unvisited PageRank slice ({slc['slice_id']}, rank={slc['pagerank']:.4f}) after {win} zero-yield tasks.",
                                )
                            )
                            if len(stall_targets) >= stall_budget:
                                break
                        if len(stall_targets) >= stall_budget:
                            break

                for sfile, sloc, sdir, snote in stall_targets[:stall_budget]:
                    stid = new_id("task")
                    ssub = infer_subsystem(sloc)
                    draft = {"kind": "investigate", "priority": "high", "subsystem": ssub, "locus": sloc, "summary": snote}
                    ssal = max(74, compute_task_salience(conn, draft))
                    conn.execute(
                        """
                        INSERT INTO tasks(
                            task_id, kind, direction, title, subsystem, locus,
                            priority, status, salience_score, summary, created_at, updated_at
                        ) VALUES (?, 'investigate', ?, ?, ?, ?, 'high', 'open', ?, ?, ?, ?)
                        """,
                        (
                            stid,
                            sdir,
                            f"Audit unvisited slice {sfile} ({sdir})",
                            ssub,
                            sloc,
                            ssal,
                            snote,
                            now_iso,
                            now_iso,
                        ),
                    )
                    spawned_stall_tasks.append(stid)

            # 2. Middle-Unicorn Auto-Bridge (<= 2 salience=90 bridge tasks for narrowest Crown-Jewel unicorn_gaps)
            unicorn_gaps = list(percolation.get("unicorn_gaps") or [])
            jewel_gaps = [g for g in unicorn_gaps if bool(g.get("reaches_crown_jewel"))]
            target_gaps = jewel_gaps if jewel_gaps else unicorn_gaps
            if target_gaps and run_status != "verify_only":
                open_bridges = [
                    dict(r)
                    for r in conn.execute(
                        "SELECT task_id, locus, title, summary FROM tasks WHERE kind = 'bridge' AND status IN ('open', 'leased')"
                    ).fetchall()
                ]
                open_unicorn_cnt = sum(1 for b in open_bridges if "[unicorn-bridge]" in str(b.get("summary") or ""))
                bridge_budget = max(0, 2 - open_unicorn_cnt)
                used_bridge_files = {_norm_locus_file(str(b.get("locus") or "")) for b in open_bridges}
                used_bridge_files.discard("")
                covered_tip_sinks: set[tuple[str, str]] = set()
                for b in open_bridges:
                    btxt = f"{b.get('title', '')} {b.get('summary', '')}"
                    for g in target_gaps:
                        gtip = str(g["forward_tip_id"])
                        gsink = str((g.get("backward_suffix") or [""])[-1])
                        if gtip in btxt and gsink and f"sink={gsink}" in btxt:
                            covered_tip_sinks.add((gtip, gsink))

                for gap in target_gaps:
                    if len(spawned_unicorn_tasks) >= bridge_budget:
                        break
                    tip_id = str(gap["forward_tip_id"])
                    entry_id = str(gap["backward_entry_id"])
                    tail_sink = str((gap.get("backward_suffix") or [entry_id])[-1])
                    gap_sig = f"{tip_id}->{entry_id}"
                    already_open = (tip_id, tail_sink) in covered_tip_sinks or any(
                        gap_sig in f"{b.get('title', '')} {b.get('summary', '')}"
                        or (tip_id in f"{b.get('title', '')} {b.get('summary', '')}" and entry_id in f"{b.get('title', '')} {b.get('summary', '')}")
                        for b in open_bridges
                    )
                    if already_open:
                        continue
                    covered_tip_sinks.add((tip_id, tail_sink))

                    primary_loc = str(gap.get("backward_guard") or gap.get("backward_entry_locus") or "").strip()
                    alt_loc = str(gap.get("forward_tip_locus") or "").strip()
                    chosen_loc = primary_loc or alt_loc
                    if _norm_locus_file(chosen_loc) in used_bridge_files and alt_loc and _norm_locus_file(alt_loc) not in used_bridge_files:
                        chosen_loc = alt_loc
                    if _norm_locus_file(chosen_loc):
                        used_bridge_files.add(_norm_locus_file(chosen_loc))

                    btid = new_id("task")
                    bsub = infer_subsystem(chosen_loc)
                    bprio = "critical" if bool(gap.get("reaches_crown_jewel")) else "high"
                    unmet_s = ",".join(gap.get("unmet_requires") or []) or str(gap.get("backward_guard") or "guard")
                    bsum = (
                        f"[unicorn-bridge] Bridge 1-link gap {gap_sig}: "
                        f"{tip_id}@{gap['forward_tip_locus']} -> {entry_id}@{gap['backward_entry_locus']} "
                        f"(unmet={unmet_s}, sink={tail_sink}, hops={gap['total_chain_hops_if_bridged']})."
                    )
                    conn.execute(
                        """
                        INSERT INTO tasks(
                            task_id, kind, direction, title, subsystem, locus,
                            priority, status, salience_score, summary, created_at, updated_at
                        ) VALUES (?, 'bridge', 'inside_out', ?, ?, ?, ?, 'open', 90, ?, ?, ?)
                        """,
                        (
                            btid,
                            f"Bridge middle-unicorn gap {gap_sig} ({unmet_s[:48]})",
                            bsub,
                            chosen_loc,
                            bprio,
                            bsum,
                            now_iso,
                            now_iso,
                        ),
                    )
                    register_epistemic_hook(
                        conn,
                        hook_code="H4_TYPED_STATE_BRIDGE",
                        trigger_cmd="swarm.plan",
                        source_entity_id=entry_id,
                        dedup_material=f"unicorn_gap:{gap_sig}",
                        subsystem=bsub,
                        target_locus=chosen_loc,
                        spawned_task_id=btid,
                        max_leases=2,
                        directive_text=(
                            f"Hunt 1-link middle bridge ({gap_sig}): emit [{unmet_s[:50]}] from {tip_id} "
                            f"to unlock {entry_id}@{gap['backward_entry_locus']}."
                        ),
                        kill_rule=(
                            f"STOP and close dry if {chosen_loc or gap['backward_entry_locus']} enforces "
                            f"immutable caller validation blocking [{unmet_s[:40]}]."
                        ),
                    )
                    spawned_unicorn_tasks.append(btid)

            recompute_all_open_salience(conn)
            if spawned_stall_tasks or spawned_unicorn_tasks or spawned_verify_tasks or spawned_chain_tasks:
                log_event(
                    conn,
                    "planner",
                    "swarm_wave_planned",
                    run_id,
                    {
                        "discovery_stalled": discovery_stalled,
                        "spawned_stall_tasks": spawned_stall_tasks,
                        "spawned_unicorn_bridge_tasks": spawned_unicorn_tasks,
                        "spawned_verification_tasks": spawned_verify_tasks,
                        "spawned_chain_tasks": spawned_chain_tasks,
                    },
                )
    else:
        unvisited_slices = list_unvisited_slices(conn, target_dir=tpath, populate_if_empty=False)
        percolation = detect_percolated_multi_hop_paths(conn, enqueue_tasks=False)
        unicorn_gaps = list(percolation.get("unicorn_gaps") or [])
        recent_terminal = conn.execute(
            """
            SELECT * FROM tasks
            WHERE status IN ('done', 'dry')
            ORDER BY COALESCE(closed_epoch, 0.0) DESC, updated_at DESC, rowid DESC
            LIMIT ?
            """,
            (win,),
        ).fetchall()
        claims_since_window = 0
        primitives_since_window = 0
        discovery_stalled = False
        if len(recent_terminal) >= win and len(unvisited_slices) > 0:
            claims_since_window, primitives_since_window = _count_discoveries_since_task(
                conn, recent_terminal[-1]
            )
            discovery_stalled = claims_since_window == 0 and primitives_since_window == 0

    throttles = compute_root_plateau_throttles(conn)
    leads = rank_leads(conn, limit=50)
    lead_ev_by_key: dict[str, float] = {}
    for ld in leads["ranked_leads"]:
        cev = float(ld.get("consensus_ev") or 0.0)
        for key in (
            str(ld.get("target_id") or "").strip(),
            str(ld.get("locus") or "").strip(),
            str(ld.get("subsystem") or "").strip(),
        ):
            if key and cev > lead_ev_by_key.get(key, 0.0):
                lead_ev_by_key[key] = cev

    open_rows = conn.execute("SELECT * FROM tasks WHERE status = 'open'").fetchall()
    scored_candidates: list[tuple[int, float, str, str, sqlite3.Row]] = []
    for row in open_rows:
        eff_sal = compute_task_salience(conn, row)
        r_surf = str(row["surface_id"] or "").strip()
        r_door = _resolve_task_door_id(row)
        r_loc = str(row["locus"] or "").strip()
        r_sub = str(row["subsystem"] or "").strip()
        matched_ev = max(
            (lead_ev_by_key.get(k, 0.0) for k in (r_surf, r_door, r_loc, r_sub) if k),
            default=0.0,
        )
        eff_ev = round(float(eff_sal) + (0.05 * matched_ev), 2)
        scored_candidates.append((eff_sal, eff_ev, str(row["created_at"]), str(row["task_id"]), row))

    scored_candidates.sort(key=lambda item: (-item[0], -item[1], item[2], item[3]))

    wave: list[dict[str, Any]] = []
    locked_files: set[str] = set()
    locked_claims: set[str] = set()
    locked_doors: set[str] = set()
    excluded_phase_tasks: list[str] = []
    deferred_collision_tasks: list[str] = []

    for eff_sal, eff_ev, _created_at, tid, row in scored_candidates:
        kind = str(row["kind"])
        if campaign_phase == "hunt" and kind == "patch":
            excluded_phase_tasks.append(tid)
            continue
        if run_status == "verify_only" and kind in ("map", "investigate", "bridge"):
            excluded_phase_tasks.append(tid)
            continue

        loc = str(row["locus"] or "").strip()
        pfile = _norm_locus_file(loc)
        claim = _resolve_task_claim(conn, row)
        cid = str(claim["claim_id"]) if claim is not None else ""
        proposer_wid = str(claim["proposer_worker_id"] or "").strip() if claim is not None else ""
        did = _resolve_task_door_id(row)

        if kind != "chain":
            if (pfile and pfile in locked_files) or (cid and cid in locked_claims) or (did and did in locked_doors):
                deferred_collision_tasks.append(tid)
                continue

        if len(wave) >= cap_workers:
            continue

        if kind != "chain":
            if pfile:
                locked_files.add(pfile)
            if cid:
                locked_claims.add(cid)
            if did:
                locked_doors.add(did)

        must_differ = proposer_wid if kind == "falsify" else ""
        ind_note = (
            f"Falsifier worker MUST differ from proposer {proposer_wid!r}."
            if (kind == "falsify" and proposer_wid)
            else ""
        )
        wave.append(
            {
                "task_id": tid,
                "kind": kind,
                "direction": str(row["direction"] or "outside_in"),
                "title": scrub_text(str(row["title"] or "")),
                "subsystem": str(row["subsystem"] or infer_subsystem(loc)),
                "locus": loc,
                "primary_file": pfile,
                "priority": str(row["priority"] or "high"),
                "salience_score": eff_sal,
                "effective_ev": eff_ev,
                "skill_mode": str(row["skill_mode"] or "domain"),
                "skill_path": TASK_KIND_SKILL_PATHS.get(kind, "skills/ajar-investigate/SKILL.md"),
                "claim_id": cid,
                "door_id": did,
                "proposer_worker_id": proposer_wid,
                "must_differ_from_worker": must_differ,
                "independence_note": ind_note,
            }
        )

    return {
        "run_id": run_id,
        "campaign_phase": campaign_phase,
        "max_workers": cap_workers,
        "stall_window": win,
        "enqueue_missing": can_enqueue,
        "discovery_stalled": discovery_stalled,
        "recent_terminal_tasks_checked": len(recent_terminal),
        "claims_since_window": claims_since_window,
        "primitives_since_window": primitives_since_window,
        "unvisited_slice_count": len(unvisited_slices),
        "unvisited_slices": unvisited_slices[:8],
        "unicorn_gap_count": len(unicorn_gaps),
        "spawned_stall_tasks": spawned_stall_tasks,
        "spawned_unicorn_bridge_tasks": spawned_unicorn_tasks,
        "spawned_verification_tasks": spawned_verify_tasks,
        "spawned_chain_tasks": spawned_chain_tasks,
        "excluded_phase_tasks": excluded_phase_tasks,
        "deferred_collision_tasks": deferred_collision_tasks,
        "root_plateau_throttles": list(throttles.values()),
        "top_ranked_leads": leads["ranked_leads"][:5],
        "wave_size": len(wave),
        "wave": wave,
    }


def build_worker_dispatch_brief(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    worker_id: str = "w-1",
) -> dict[str, Any]:
    """Compile a deterministic Layer-0 Worker Dispatch Brief (`<= 40` lines) with phase lock & falsifier separation."""
    tid = (task_id or "").strip()
    if not tid:
        raise AjarError("task_id must be non-empty.", EXIT_USER_ERROR)
    raw_wid = (worker_id or "").strip()

    task = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (tid,)).fetchone()
    if task is None:
        raise AjarError(f"Unknown task_id: {tid}", EXIT_USER_ERROR)

    run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
    if run is None:
        raise AjarError("Run metadata missing in run.db.", EXIT_USER_ERROR)

    run_id = str(run["run_id"])
    target_path = str(run["target_path"] or "")
    campaign_phase = str(run["campaign_phase"] if "campaign_phase" in run.keys() else "hunt") or "hunt"
    kind = str(task["kind"] or "investigate")
    direction = str(task["direction"] or "outside_in")
    skill_mode = str(task["skill_mode"] or "domain")
    assigned_locus = str(task["locus"] or "").strip() or "(repo-wide)"
    sub = str(task["subsystem"] or infer_subsystem(str(task["locus"] or "")))

    if kind == "falsify" and not raw_wid:
        raise AjarError("Fresh-falsifier separation gate requires a non-empty worker_id.", EXIT_GATE_BLOCKED)
    wid = raw_wid or "w-1"

    claim = _resolve_task_claim(conn, task)
    proposer_wid = str(claim["proposer_worker_id"] or "").strip() if claim is not None else ""
    if kind == "falsify" and proposer_wid and wid == proposer_wid:
        raise AjarError(
            f"Fresh-falsifier separation gate: worker {wid!r} proposed claim {claim['claim_id'] if claim else ''} "
            "and cannot be dispatched as its falsifier. Assign an independent worker_id.",
            EXIT_GATE_BLOCKED,
            {
                "task_id": tid,
                "claim_id": str(claim["claim_id"]) if claim else "",
                "proposer_worker_id": proposer_wid,
                "worker_id": wid,
            },
        )

    skill_path = TASK_KIND_SKILL_PATHS.get(kind, "skills/ajar-investigate/SKILL.md")
    role = TASK_KIND_ROLE_LABELS.get(kind, "Swarm Worker")

    if campaign_phase == "hunt":
        phase_guardrail = (
            "PHASE LOCK (hunt): Do NOT write production patches or run ajar patch verify. "
            "Stop as soon as the claim is causally reproduced (4-arm), parked via ajar door park, or closed dry."
        )
    elif campaign_phase == "remediate":
        phase_guardrail = (
            "PHASE LOCK (remediate): Author and verify 9-arm production fixes (`ajar patch verify`) "
            "on confirmed findings inside isolated `repro/slot-<k>` without mutating target HEAD."
        )
    else:
        phase_guardrail = (
            "PHASE (full): Complete 4-arm causal reproduction (`ajar claim reproduce`) before running "
            "9-arm production remediation (`ajar patch verify`)."
        )

    # Resolve minimal door / unicorn-gap / claim context
    door_or_gap_context: dict[str, Any] = {}
    context_lines: list[str] = []
    did = _resolve_task_door_id(task)
    if did:
        drow = conn.execute("SELECT * FROM parked_doors WHERE door_id = ?", (did,)).fetchone()
        if drow is not None:
            wtags = parse_tag_list(drow["wanted_tags_json"])
            door_or_gap_context = {
                "kind": "open_door",
                "door_id": str(drow["door_id"]),
                "status": str(drow["status"]),
                "anchor_locus": str(drow["anchor_locus"]),
                "blocker_locus": str(drow["blocker_locus"] or ""),
                "missing_link_summary": _single_line(str(drow["missing_link_summary"]), 140),
                "wanted_tags": wtags,
                "snapshot_id": str(drow["snapshot_id"] or ""),
            }
            context_lines.append(
                f"- Door `{drow['door_id']}` (`{drow['status']}`) @ `{drow['anchor_locus']}`: "
                f"{_single_line(str(drow['missing_link_summary']), 105)}"
            )

    if not door_or_gap_context and kind in ("bridge", "chain"):
        perc = detect_percolated_multi_hop_paths(conn, enqueue_tasks=False)
        task_blob = f"{task['title']} {task['summary']}"
        pfile = _norm_locus_file(str(task["locus"] or ""))
        for gap in perc.get("unicorn_gaps") or []:
            gsig = f"{gap['forward_tip_id']}->{gap['backward_entry_id']}"
            g_files = {
                _norm_locus_file(str(gap.get("backward_guard") or "")),
                _norm_locus_file(str(gap.get("backward_entry_locus") or "")),
                _norm_locus_file(str(gap.get("forward_tip_locus") or "")),
            }
            if gsig in task_blob or (pfile and pfile in g_files):
                door_or_gap_context = {
                    "kind": "unicorn_gap",
                    "forward_tip_id": str(gap["forward_tip_id"]),
                    "forward_tip_locus": str(gap["forward_tip_locus"]),
                    "backward_entry_id": str(gap["backward_entry_id"]),
                    "backward_entry_locus": str(gap["backward_entry_locus"]),
                    "backward_guard": str(gap.get("backward_guard") or ""),
                    "unmet_requires": list(gap.get("unmet_requires") or []),
                    "reaches_crown_jewel": bool(gap.get("reaches_crown_jewel")),
                }
                unmet_lbl = ",".join(gap.get("unmet_requires") or []) or str(gap.get("backward_guard") or "guard")
                context_lines.append(
                    f"- Unicorn Gap `{gsig}`: `{gap['forward_tip_locus']}` -> `{gap['backward_entry_locus']}` (unmet=`{unmet_lbl}`)"
                )
                break

    if not door_or_gap_context and claim is not None:
        door_or_gap_context = {
            "kind": "claim",
            "claim_id": str(claim["claim_id"]),
            "status": str(claim["status"]),
            "severity": str(claim["severity"]),
            "proposer_worker_id": proposer_wid,
            "title": _single_line(str(claim["title"] or ""), 120),
            "falsification_prediction": _single_line(str(claim["falsification_prediction"] or ""), 140),
            "falsification_test": _single_line(str(claim["falsification_test"] or ""), 140),
        }
        context_lines.append(
            f"- Claim `{claim['claim_id']}` (`{claim['severity']}`, proposer=`{proposer_wid}`): "
            f"{_single_line(str(claim['title'] or ''), 95)}"
        )
        context_lines.append(
            f"- Disconfirm Test: `{_single_line(str(claim['falsification_test'] or ''), 105)}`"
        )

    steers = list_steers(conn, active_only=True, subsystem=sub, locus=str(task["locus"] or ""))[:3]
    active_hooks = select_active_hooks_for_task(conn, task, limit=2)

    if active_hooks:
        kill_rule = _single_line(str(active_hooks[0]["kill_rule"]), 160)
    elif kind == "falsify":
        kill_rule = (
            "Disprove immediately via `ajar claim falsify --control-locus <file:line>` if an upstream guard "
            "blocks reachability; otherwise promote via `ajar claim survive`."
        )
    elif kind == "reproduce":
        kill_rule = (
            "After 2 unchanged `target_negative` strikes, pivot to `ajar claim instrument` before retrying reproduction."
        )
    elif kind == "bridge":
        kill_rule = (
            "Close `dry` via `ajar task dry` if the assigned cone enforces invariant sanitization before the blocked door."
        )
    elif kind == "chain":
        kill_rule = (
            "Abort chain proposal and close/park cleanly if per-step ablation fails closed or requires caller self-override."
        )
    else:
        kill_rule = (
            "Close `dry` immediately via `ajar task dry` citing exact guard `file:line` if target code enforces "
            "a compensating invariant across reachable callers."
        )

    cat = search_issue_catalog(conn, subsystem=sub, include_unverified=True, limit=8)
    if not cat["items"]:
        cat = search_issue_catalog(conn, include_unverified=True, limit=8)
    skip_ids = {str(claim["claim_id"])} if claim is not None else set()
    if did:
        skip_ids.add(did)
    catalog_neighbors: list[dict[str, Any]] = []
    for it in cat["items"]:
        iid = str(it["item_id"])
        if iid in skip_ids:
            continue
        catalog_neighbors.append(
            {
                "item_id": iid,
                "item_kind": str(it["item_kind"]),
                "locus": str(it["locus"]),
                "provides_tags": list(it["provides_tags"]),
                "requires_tags": list(it["requires_tags"]),
                "summary": _single_line(str(it["summary"]), 100),
            }
        )
        if len(catalog_neighbors) >= 3:
            break

    zero_note = " ZERO-SKILL LEASE: Do NOT open `skills/domains/*`." if skill_mode == "zero_skill" else ""
    md_lines: list[str] = [
        f"# Swarm Dispatch Brief: {tid} ({role} | worker={wid})",
        f"Run: `{run_id}` | Target: `{target_path}` | Kind: `{kind}` (`{direction}`, `skill_mode={skill_mode}`)",
        f"Skill: Read `{skill_path}` first; export `AJAR_RUN_ID={run_id}`; keep target tree untouched.{zero_note}",
        phase_guardrail,
        "",
        "## Assigned Target",
        f"- Task: `{tid}` — {_single_line(str(task['title'] or ''), 110)}",
        f"- Locus: `{assigned_locus}` (subsystem: `{sub}`)",
    ]
    if task["summary"]:
        md_lines.append(f"- Summary: {_single_line(str(task['summary']), 120)}")
    md_lines.extend(context_lines[:2])

    if steers:
        md_lines.append("")
        md_lines.append("## Active Workspace Steers")
        for st in steers:
            md_lines.append(
                f"- [{st['scope']}:{st['target_filter'] or '*'}] {_single_line(str(st['rule_text']), 110)}"
            )

    md_lines.append("")
    md_lines.append("## Epistemic Hooks & Kill Rule")
    for hk in active_hooks[:2]:
        md_lines.append(f"- [{hk['hook_code']}] {_single_line(str(hk['directive_text']), 115)}")
    md_lines.append(f"- Kill Rule: {kill_rule}")

    if catalog_neighbors:
        md_lines.append("")
        md_lines.append("## Composable Catalog Neighbors (<= 3)")
        for nb in catalog_neighbors:
            tags_s = ",".join([*nb["provides_tags"][:2], *nb["requires_tags"][:1]])
            tag_lbl = f" tags=[{tags_s}]" if tags_s else ""
            md_lines.append(f"- `{nb['item_id']}` [{nb['item_kind']}] @ `{nb['locus']}`{tag_lbl}: {nb['summary']}")

    md_lines.extend(
        [
            "",
            "## Completion Contract",
            f"Record verified state via `ajar` CLI/MCP (`--worker {wid}`) and close `{tid}` (`done` / `dry` / `block`).",
        ]
    )
    rendered_brief = "\n".join(md_lines[:39]) + "\n"

    return {
        "run_id": run_id,
        "task_id": tid,
        "worker_id": wid,
        "task_kind": kind,
        "skill_mode": skill_mode,
        "role": role,
        "skill_path": skill_path,
        "campaign_phase": campaign_phase,
        "phase_guardrail": phase_guardrail,
        "assigned_locus": assigned_locus,
        "claim_id": str(claim["claim_id"]) if claim is not None else "",
        "proposer_worker_id": proposer_wid,
        "door_or_gap_context": door_or_gap_context,
        "active_steers": [
            {"steer_id": str(s["steer_id"]), "scope": str(s["scope"]), "rule_text": _single_line(str(s["rule_text"]), 120)}
            for s in steers
        ],
        "epistemic_hooks": [
            {
                "hook_code": str(h["hook_code"]),
                "directive_text": _single_line(str(h["directive_text"]), 120),
                "kill_rule": _single_line(str(h["kill_rule"]), 120),
            }
            for h in active_hooks[:2]
        ],
        "catalog_neighbors": catalog_neighbors,
        "kill_rule": kill_rule,
        "line_count": len(rendered_brief.splitlines()),
        "rendered_brief": rendered_brief,
    }




