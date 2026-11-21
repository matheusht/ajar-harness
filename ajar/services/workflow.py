"""Unified transactional workflow services shared by `ajar/cli.py` and `ajar/mcp.py`.

Every core state mutation (`surfaces`, `tasks`, `anomalies`, `claims`, `campaign_phase`,
`runs.finish`) lives here once, acquiring `immediate_tx(conn)` BEFORE reading mutable rows
so `assert_run_mutable`, typed transition guards, `derive_claim_axes`, and epistemic hooks
are atomic under SQLite WAL concurrency and identical across CLI and MCP interfaces.
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
import time
from typing import Any

from ajar import EXIT_GATE_BLOCKED, EXIT_USER_ERROR
from ajar.chain_planner import evaluate_precondition_realism
from ajar.db import (
    check_dead_end_repetition,
    compute_task_salience,
    infer_subsystem,
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
    on_anomaly_or_claim_recorded,
    on_claim_config_gated,
    on_claim_survived,
    on_finding_confirmed,
    on_primitive_added,
    parse_tag_list,
    register_epistemic_hook,
    scan_source_for_epistemic_signals,
)
from ajar.gates import (
    check_guarded_primitive_dry_block,
    finding_attribution_for_claim,
    validate_dry_locus,
)
from ajar.redact import scrub_text
from ajar.repro_source import validate_micropatch_diff
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
    with immediate_tx(conn):
        assert_run_mutable(conn, operation="claim_propose")
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
                status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'proposed', ?, ?)
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
        log_event(conn, wid, "claim_proposed", cid, {"locus": locus, "severity": severity})
    return {
        "claim_id": cid,
        "status": "proposed",
        "subsystem": sub,
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
) -> dict[str, Any]:
    new_phase = to_phase.strip()
    if new_phase not in ("hunt", "remediate", "full"):
        raise AjarError(f"Unsupported phase {new_phase!r}; choose hunt, remediate, or full.", EXIT_USER_ERROR)
    with immediate_tx(conn):
        assert_run_mutable(conn, operation="phase_advance")
        run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
        if run is None:
            raise AjarError("Run metadata missing in run.db.", EXIT_USER_ERROR)
        prev_phase = str(run["campaign_phase"] if "campaign_phase" in run.keys() else "hunt") or "hunt"
        assert_valid_phase_transition(prev_phase, new_phase, run_id=run_id)
        conn.execute("UPDATE runs SET campaign_phase = ? WHERE run_id = ?", (new_phase, run_id))
        recompute_all_open_salience(conn)
        log_event(
            conn,
            actor.strip() or "operator",
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
                WHERE claim_id = ?
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
