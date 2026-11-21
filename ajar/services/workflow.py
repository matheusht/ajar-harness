"""Unified transactional workflow services shared by `ajar/cli.py` and `ajar/mcp.py`.

Every core state mutation (`surfaces`, `tasks`, `anomalies`, `claims`, `campaign_phase`)
lives here once, enforcing `assert_run_mutable`, typed transition guards, `derive_claim_axes`,
epistemic hooks, and `immediate_tx` identically across CLI and MCP interfaces.
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
import time
from typing import Any

from ajar import EXIT_GATE_BLOCKED, EXIT_USER_ERROR
from ajar.db import (
    check_dead_end_repetition,
    infer_subsystem,
    log_event,
    maybe_auto_pulse,
    new_id,
    normalize_mechanism_key,
    recompute_all_open_salience,
    utc_now_iso,
)
from ajar.domain import (
    AjarError,
    assert_valid_anomaly_transition,
    assert_valid_claim_transition,
    assert_valid_phase_transition,
    assert_valid_task_transition,
    derive_claim_axes,
)
from ajar.epistemic_hooks import (
    consume_hooks_for_locus,
    on_anomaly_or_claim_recorded,
    on_claim_config_gated,
    on_claim_survived,
    parse_tag_list,
    register_epistemic_hook,
    scan_source_for_epistemic_signals,
)
from ajar.gates import check_guarded_primitive_dry_block, validate_dry_locus
from ajar.redact import scrub_text
from ajar.store import assert_run_mutable, immediate_tx
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
    assert_run_mutable(conn, operation="surface_add")
    sid = new_id("surf")
    sub = (subsystem or "").strip() or infer_subsystem(locus)
    req_tags = parse_tag_list(requires_tags)
    now_iso = utc_now_iso()
    fired_codes: list[str] = []

    with immediate_tx(conn):
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
            actor,
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
    assert_run_mutable(conn, operation="task_done")
    cur = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
    if cur is None:
        raise AjarError(f"Unknown task_id: {task_id}", EXIT_USER_ERROR)
    assert_valid_task_transition(str(cur["status"]), "done", task_id=task_id)
    now_iso = utc_now_iso()
    with immediate_tx(conn):
        conn.execute(
            """
            UPDATE tasks
            SET status = 'done', worker_id = ?, summary = ?, lease_expires_at = NULL,
                closed_epoch = ?, updated_at = ?
            WHERE task_id = ?
            """,
            (worker_id, scrub_text(summary or ""), time.time(), now_iso, task_id),
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
        log_event(conn, worker_id, "task_done", task_id, {"kind": cur["kind"]})
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
    assert_run_mutable(conn, operation="task_dry")
    cur = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
    if cur is None:
        raise AjarError(f"Unknown task_id: {task_id}", EXIT_USER_ERROR)
    assert_valid_task_transition(str(cur["status"]), "dry", task_id=task_id)
    ok, msg = validate_dry_locus(target_dir, target_mode, locus, control_reason)
    if not ok:
        raise AjarError(msg, EXIT_GATE_BLOCKED)
    ok_gp, msg_gp = check_guarded_primitive_dry_block(conn, task_row=cur, dry_locus=locus)
    if not ok_gp:
        raise AjarError(msg_gp, EXIT_GATE_BLOCKED)
    now_iso = utc_now_iso()
    with immediate_tx(conn):
        conn.execute(
            """
            UPDATE tasks
            SET status = 'dry', worker_id = ?, dry_control_locus = ?, dry_control_reason = ?,
                lease_expires_at = NULL, closed_epoch = ?, updated_at = ?
            WHERE task_id = ?
            """,
            (worker_id, locus, scrub_text(control_reason), time.time(), now_iso, task_id),
        )
        consume_hooks_for_locus(conn, locus=locus)
        if cur["locus"]:
            consume_hooks_for_locus(conn, locus=str(cur["locus"]))
        log_event(conn, worker_id, "task_dry", task_id, {"locus": locus})
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
    assert_run_mutable(conn, operation="task_block")
    cur = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
    if cur is None:
        raise AjarError(f"Unknown task_id: {task_id}", EXIT_USER_ERROR)
    assert_valid_task_transition(str(cur["status"]), "conditional_blocked", task_id=task_id)
    now_iso = utc_now_iso()
    with immediate_tx(conn):
        conn.execute(
            """
            UPDATE tasks
            SET status = 'conditional_blocked', worker_id = ?, blocker_predicate = ?,
                blocker_check_locus = ?, lease_expires_at = NULL, updated_at = ?
            WHERE task_id = ?
            """,
            (worker_id, scrub_text(predicate), check_locus or "", now_iso, task_id),
        )
        log_event(conn, worker_id, "task_conditional_blocked", task_id, {"predicate": predicate})
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
    assert_run_mutable(conn, operation="anomaly_add")
    aid = new_id("anom")
    now_iso = utc_now_iso()
    sub = infer_subsystem(locus)
    with immediate_tx(conn):
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
        log_event(conn, actor, "anomaly_added", aid, {"locus": locus})
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
    assert_run_mutable(conn, operation="anomaly_explain")
    if len(reason.strip()) < 12:
        raise AjarError("Explanation --reason must be at least 12 characters.", EXIT_USER_ERROR)
    anom = conn.execute("SELECT status FROM anomalies WHERE anomaly_id = ?", (anomaly_id,)).fetchone()
    if anom is None:
        raise AjarError(f"Unknown anomaly_id: {anomaly_id}", EXIT_USER_ERROR)
    assert_valid_anomaly_transition(str(anom["status"]), "benign_explained", anomaly_id=anomaly_id)
    now_iso = utc_now_iso()
    with immediate_tx(conn):
        conn.execute(
            """
            UPDATE anomalies
            SET status = 'benign_explained', explanation_locus = ?, explanation_reason = ?, updated_at = ?
            WHERE anomaly_id = ?
            """,
            (locus, scrub_text(reason), now_iso, anomaly_id),
        )
        log_event(conn, actor, "anomaly_explained", anomaly_id, {"locus": locus})
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
    target_dir: pathlib.Path | None = None,
    target_mode: str = "source",
) -> dict[str, Any]:
    assert_run_mutable(conn, operation="claim_propose")
    if len(falsification_prediction.strip()) < 10 or len(falsification_test.strip()) < 5:
        raise AjarError(
            "DEC-0128 gate: --falsification-prediction and --falsification-test are required before proposing a claim.",
            EXIT_GATE_BLOCKED,
        )
    ok_prose, prose_msg = validate_structural_claim_prose(title, mechanism, falsification_prediction)
    if not ok_prose:
        raise AjarError(prose_msg, EXIT_GATE_BLOCKED)
    check_dead_end_repetition(
        conn,
        locus=locus,
        mechanism=mechanism,
        consume_anomaly_id=consume_anomaly_id,
    )
    cid = new_id("clm")
    now_iso = utc_now_iso()
    sub = infer_subsystem(locus)
    with immediate_tx(conn):
        conn.execute(
            """
            INSERT INTO claims(
                claim_id, surface_id, proposer_worker_id, seeded_by_human, title, subsystem, locus,
                mechanism, mechanism_key, severity, falsification_prediction, falsification_test,
                status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'proposed', ?, ?)
            """,
            (
                cid,
                surface_id,
                worker_id,
                1 if seeded_by_human else 0,
                scrub_text(title),
                sub,
                locus,
                scrub_text(mechanism),
                normalize_mechanism_key(mechanism),
                severity,
                scrub_text(falsification_prediction),
                scrub_text(falsification_test),
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
        log_event(conn, worker_id, "claim_proposed", cid, {"locus": locus, "severity": severity})
    return {
        "claim_id": cid,
        "status": "proposed",
        "subsystem": sub,
        "hooks_triggered": [h["hook_code"] for h in hooks],
    }


def falsify_claim(
    conn: sqlite3.Connection,
    *,
    claim_id: str,
    worker_id: str,
    notes: str,
    control_locus: str | None = None,
    config_gate: str = "",
) -> dict[str, Any]:
    assert_run_mutable(conn, operation="claim_falsify")
    if not worker_id.strip():
        raise AjarError("claim falsify requires a non-empty worker_id.", EXIT_GATE_BLOCKED)
    clm = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (claim_id,)).fetchone()
    if clm is None:
        raise AjarError(f"Unknown claim_id: {claim_id}", EXIT_USER_ERROR)
    if clm["proposer_worker_id"] == worker_id:
        raise AjarError(
            f"Fresh-falsifier separation gate: proposer {worker_id!r} cannot falsify its own claim. "
            "Use an independent falsifier worker.",
            EXIT_GATE_BLOCKED,
        )
    now_iso = utc_now_iso()
    cfg_gate = (config_gate or "").strip()
    if cfg_gate:
        assert_valid_claim_transition(str(clm["status"]), "config_gated", claim_id=claim_id)
        axes = derive_claim_axes("config_gated")
        with immediate_tx(conn):
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
                    worker_id,
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
                worker_id,
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
    with immediate_tx(conn):
        conn.execute(
            """
            UPDATE claims
            SET status = 'falsified', falsifier_worker_id = ?, falsify_notes = ?,
                falsify_control_locus = ?, research_state = ?,
                evidence_state = ?, updated_at = ?
            WHERE claim_id = ?
            """,
            (
                worker_id,
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
        log_event(conn, worker_id, "claim_falsified", claim_id, {})
    return {"claim_id": claim_id, "status": "falsified"}


def survive_claim(
    conn: sqlite3.Connection,
    *,
    claim_id: str,
    worker_id: str,
    notes: str,
) -> dict[str, Any]:
    assert_run_mutable(conn, operation="claim_survive")
    if not worker_id.strip():
        raise AjarError("claim survive requires a non-empty worker_id.", EXIT_GATE_BLOCKED)
    clm = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (claim_id,)).fetchone()
    if clm is None:
        raise AjarError(f"Unknown claim_id: {claim_id}", EXIT_USER_ERROR)
    if clm["proposer_worker_id"] == worker_id:
        raise AjarError(
            f"Fresh-falsifier separation gate: proposer {worker_id!r} cannot validate its own claim. "
            "Use an independent falsifier worker.",
            EXIT_GATE_BLOCKED,
        )
    assert_valid_claim_transition(str(clm["status"]), "survived_falsify", claim_id=claim_id)
    axes = derive_claim_axes("survived_falsify")
    now_iso = utc_now_iso()
    with immediate_tx(conn):
        conn.execute(
            """
            UPDATE claims
            SET status = 'survived_falsify', falsifier_worker_id = ?, falsify_notes = ?,
                research_state = ?, evidence_state = ?, env_blocker = '', blocker_reason = '',
                updated_at = ?
            WHERE claim_id = ?
            """,
            (
                worker_id,
                scrub_text(notes),
                axes.research_state.value,
                axes.evidence_state.value,
                now_iso,
                claim_id,
            ),
        )
        updated_clm = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (claim_id,)).fetchone()
        hooks = on_claim_survived(conn, claim_row=updated_clm)
        log_event(conn, worker_id, "claim_survived_falsify", claim_id, {})
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
    assert_run_mutable(conn, operation="claim_block")
    clm = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (claim_id,)).fetchone()
    if clm is None:
        raise AjarError(f"Unknown claim_id: {claim_id}", EXIT_USER_ERROR)
    assert_valid_claim_transition(str(clm["status"]), "blocked", claim_id=claim_id)
    env_b = (env_blocker or "").strip()
    ok_blk, blk_msg = validate_claim_block_request(
        clm,
        reason=reason,
        env_blocker=env_b,
        target_mode=target_mode,
    )
    if not ok_blk:
        raise AjarError(blk_msg, EXIT_GATE_BLOCKED)
    axes = derive_claim_axes("blocked")
    now_iso = utc_now_iso()
    with immediate_tx(conn):
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
            worker_id,
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
) -> dict[str, Any]:
    run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
    if run is None:
        raise AjarError("Run metadata missing in run.db.", EXIT_USER_ERROR)
    prev_phase = str(run["campaign_phase"] if "campaign_phase" in run.keys() else "hunt") or "hunt"
    new_phase = to_phase.strip()
    if new_phase not in ("hunt", "remediate", "full"):
        raise AjarError(f"Unsupported phase {new_phase!r}; choose hunt, remediate, or full.", EXIT_USER_ERROR)
    assert_run_mutable(conn, operation="phase_advance")
    assert_valid_phase_transition(prev_phase, new_phase, run_id=run_id)
    with immediate_tx(conn):
        conn.execute("UPDATE runs SET campaign_phase = ? WHERE run_id = ?", (new_phase, run_id))
        recompute_all_open_salience(conn)
        log_event(
            conn,
            actor,
            "campaign_phase_advanced",
            run_id,
            {"previous_phase": prev_phase, "campaign_phase": new_phase, "notes": scrub_text(notes or "")},
        )
    return {"run_id": run_id, "previous_phase": prev_phase, "campaign_phase": new_phase}


def finish_run(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    target_dir: pathlib.Path | None = None,
    actor: str = "operator",
) -> dict[str, Any]:
    from ajar.gates import check_all_gates

    gates = check_all_gates(conn, target_dir=target_dir, auto_enqueue_chain=True)
    if gates["passed"]:
        now_iso = utc_now_iso()
        with immediate_tx(conn):
            conn.execute(
                "UPDATE runs SET status = 'finished', stop_reason = 'all_gates_passed', finished_at = ? WHERE run_id = ?",
                (now_iso, run_id),
            )
            log_event(conn, actor, "run_finished", run_id, {"findings_count": gates.get("findings_count", 0)})
    return gates
