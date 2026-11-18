"""Command-line interface for Ajar (`ajar` CLI).

Provides one deterministic interface across Host Mode (Codex, Antigravity,
Claude Code, OMP) and Standalone Product Mode (`ajar run`).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import sqlite3
import subprocess
import sys
import time
from typing import Any, Sequence

from ajar import EXIT_GATE_BLOCKED, EXIT_OK, EXIT_USER_ERROR, __version__
from ajar.db import (
    AjarError,
    check_dead_end_repetition,
    compute_task_salience,
    infer_subsystem,
    lease_next_task,
    list_rows,
    log_event,
    maybe_auto_pulse,
    new_id,
    normalize_mechanism_key,
    open_run_db,
    record_repro_failure,
    render_task_context,
    resolve_run_id,
    run_dir_for,
    run_pulse,
    set_certified_binding,
    utc_now_iso,
)
from ajar.gates import check_all_gates, finding_attribution_for_claim, validate_dry_locus
from ajar.hooks import evaluate_claude_stop_hook, run_host_continuation_loop
from ajar.mcp import serve_mcp_stdio
from ajar.oracles import query_oracle
from ajar.redact import scrub_text, scrubbed_subprocess_env
from ajar.repomap import build_repomap
from ajar.report import build_report_data, render_markdown_report
from ajar.repro_binary_live import run_binary_reproduction, run_live_reproduction
from ajar.repro_source import run_source_reproduction, unshare_netns_available
from ajar.runner import run_autonomous_schedule
from ajar.workspace import init_run_workspace


def _emit(payload: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif isinstance(payload, str):
        print(payload)
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))


def _check_sqlite_fts5() -> bool:
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE VIRTUAL TABLE t USING fts5(x);")
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        conn.close()


def cmd_doctor(args: argparse.Namespace) -> int:
    tools = ("git", "rg", "ctags", "gcc", "gdb", "go", "cargo", "node", "forge")
    found = {t: shutil.which(t) for t in tools}
    fts5_ok = _check_sqlite_fts5()
    py_ok = sys.version_info >= (3, 11)
    report = {
        "ajar_version": __version__,
        "python_version": sys.version.split()[0],
        "python_ok": py_ok,
        "sqlite_version": sqlite3.sqlite_version,
        "sqlite_fts5_ok": fts5_ok,
        "unshare_netns_available": unshare_netns_available(),
        "isolation_mode": "unshare_netns" if unshare_netns_available() else "ephemeral_port_pgid_reaper",
        "toolchains": {k: bool(v) for k, v in found.items()},
        "toolchain_paths": {k: v for k, v in found.items() if v},
    }
    _emit(report, bool(args.json))
    return EXIT_OK if (py_ok and fts5_ok and bool(found["git"])) else EXIT_USER_ERROR


def cmd_init(args: argparse.Namespace) -> int:
    ws_mode = "in_place" if args.in_place else "envelope"
    info = init_run_workspace(
        target=args.target,
        target_mode=args.mode,
        workspace_mode=ws_mode,
        goal=args.goal,
        stopping_criterion=args.until,
        budget_usd=args.budget,
        allowed_hosts=args.allow_host or [],
        allow_live_requests=bool(args.allow_live_requests),
        allow_live_mutations=bool(args.allow_live_mutations),
        run_id=args.run_id,
    )
    if args.json:
        _emit(info, True)
    else:
        print(f"Initialized Ajar run: {info['run_id']}")
        print(f"  Workspace ({info['workspace_mode']}): {info['workspace_path']}")
        print(f"  Target ({info['target_mode']}):    {info['target_path']}")
        print(f"  In-scope LoC:           {info['in_scope_loc']} (Code quote cap: ${info['code_quote_usd']:.2f})")
        print(f"  Commitment SHA-256:     {info['commitment_hash']}")
        print(f"  Export for shell:       export AJAR_RUN_ID={info['run_id']}")
    return EXIT_OK


def cmd_status(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    conn = open_run_db(rid)
    try:
        run = dict(conn.execute("SELECT * FROM runs LIMIT 1").fetchone())
        tpath = pathlib.Path(run["target_path"])
        gates = check_all_gates(conn, target_dir=tpath, auto_enqueue_chain=False)
        payload = {
            "run": run,
            "surfaces_count": conn.execute("SELECT COUNT(*) AS c FROM surfaces").fetchone()["c"],
            "tasks_by_status": {
                r["status"]: int(r["c"])
                for r in conn.execute("SELECT status, COUNT(*) AS c FROM tasks GROUP BY status").fetchall()
            },
            "claims_by_status": {
                r["status"]: int(r["c"])
                for r in conn.execute("SELECT status, COUNT(*) AS c FROM claims GROUP BY status").fetchall()
            },
            "unexplained_anomalies": conn.execute(
                "SELECT COUNT(*) AS c FROM anomalies WHERE status = 'unexplained'"
            ).fetchone()["c"],
            "findings_count": gates["findings_count"],
            "gates_passed": gates["passed"],
            "blockers": gates["blockers"],
            "economics": gates["economics"],
        }
    finally:
        conn.close()
    _emit(payload, True)
    return EXIT_OK


def cmd_context(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    conn = open_run_db(rid)
    try:
        ctx = render_task_context(conn, args.task)
    finally:
        conn.close()
    if args.json:
        _emit(ctx, True)
    else:
        print(ctx["rendered"])
    return EXIT_OK


def cmd_pulse(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    conn = open_run_db(rid)
    try:
        run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
        tpath = pathlib.Path(run["target_path"]) if run else None
        res = run_pulse(conn, target_dir=tpath)
    finally:
        conn.close()
    _emit(res, True)
    return EXIT_OK


def cmd_map(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    conn = open_run_db(rid)
    try:
        run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
        tpath = pathlib.Path(run["target_path"])
        res = build_repomap(
            conn,
            tpath,
            focus_files=args.focus_file or (),
            focus_symbols=args.focus_symbol or (),
            budget_tokens=args.budget_tokens,
        )
    finally:
        conn.close()
    if args.json:
        _emit(res, True)
    else:
        print(res["rendered"])
    return EXIT_OK


def cmd_ref_query(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    conn = open_run_db(rid)
    try:
        hits = query_oracle(conn, args.kind, args.query, limit=args.limit)
    finally:
        conn.close()
    _emit({"kind": args.kind, "query": args.query, "results": hits}, True)
    return EXIT_OK


def cmd_surface(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    conn = open_run_db(rid)
    try:
        if args.surface_cmd == "add":
            sid = new_id("surf")
            now_iso = utc_now_iso()
            sub = args.subsystem or infer_subsystem(args.locus)
            conn.execute(
                """
                INSERT INTO surfaces(surface_id, name, kind, subsystem, locus, priority, trust_boundary, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sid,
                    scrub_text(args.name),
                    args.kind,
                    sub,
                    args.locus,
                    args.priority,
                    scrub_text(args.trust_boundary or ""),
                    now_iso,
                ),
            )
            log_event(conn, "worker", "surface_added", sid, {"name": args.name, "locus": args.locus})
            _emit({"surface_id": sid, "subsystem": sub, "priority": args.priority}, True)
            return EXIT_OK
        rows = list_rows(conn, "SELECT * FROM surfaces ORDER BY created_at ASC")
        _emit({"surfaces": rows}, True)
        return EXIT_OK
    finally:
        conn.close()


def cmd_driver(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    conn = open_run_db(rid)
    try:
        if args.driver_cmd == "add":
            did = new_id("drv")
            conn.execute(
                """
                INSERT INTO surface_drivers(driver_id, surface_id, setup_cmd, invoke_template, teardown_cmd, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    did,
                    args.surface,
                    scrub_text(args.setup_cmd),
                    scrub_text(args.invoke_template),
                    scrub_text(args.teardown_cmd or ""),
                    scrub_text(args.notes or ""),
                    utc_now_iso(),
                ),
            )
            log_event(conn, "worker", "driver_added", did, {"surface_id": args.surface})
            _emit({"driver_id": did, "surface_id": args.surface}, True)
            return EXIT_OK
        rows = list_rows(conn, "SELECT * FROM surface_drivers ORDER BY created_at ASC")
        _emit({"drivers": rows}, True)
        return EXIT_OK
    finally:
        conn.close()


def cmd_task(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    conn = open_run_db(rid)
    try:
        run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
        tpath = pathlib.Path(run["target_path"]) if run else None

        if args.task_cmd == "add":
            tid = new_id("task")
            now_iso = utc_now_iso()
            sub = args.subsystem or infer_subsystem(args.locus or "")
            draft = {
                "priority": args.priority,
                "subsystem": sub,
                "locus": args.locus or "",
                "reopened_boost": 0,
            }
            sal = compute_task_salience(conn, draft)
            conn.execute(
                """
                INSERT INTO tasks(
                    task_id, parent_task_id, surface_id, kind, title, subsystem, locus,
                    priority, status, salience_score, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)
                """,
                (
                    tid,
                    args.parent,
                    args.surface,
                    args.kind,
                    scrub_text(args.title),
                    sub,
                    args.locus or "",
                    args.priority,
                    sal,
                    now_iso,
                    now_iso,
                ),
            )
            log_event(conn, "worker", "task_added", tid, {"kind": args.kind, "salience_score": sal})
            _emit({"task_id": tid, "salience_score": sal, "subsystem": sub}, True)
            return EXIT_OK

        if args.task_cmd == "lease":
            leased = lease_next_task(
                conn,
                worker_id=args.worker,
                kind=args.kind,
                ttl_sec=args.ttl,
                recover=bool(args.recover),
            )
            if leased is not None:
                leased["context"] = render_task_context(conn, leased["task_id"])["rendered"]
            _emit({"leased": leased}, True)
            return EXIT_OK

        if args.task_cmd == "done":
            now_iso = utc_now_iso()
            cur = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (args.task_id,)).fetchone()
            if cur is None:
                raise AjarError(f"Unknown task_id: {args.task_id}", EXIT_USER_ERROR)
            conn.execute(
                """
                UPDATE tasks
                SET status = 'done', worker_id = ?, summary = ?, lease_expires_at = NULL,
                    closed_epoch = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (args.worker, scrub_text(args.summary or ""), time.time(), now_iso, args.task_id),
            )
            # If completing an `instrument` task, unlock stalled claims at that locus!
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
            log_event(conn, args.worker, "task_done", args.task_id, {"kind": cur["kind"]})
            pulse = maybe_auto_pulse(conn, tpath)
            _emit({"task_id": args.task_id, "status": "done", "pulse": pulse}, True)
            return EXIT_OK

        if args.task_cmd == "dry":
            ok, msg = validate_dry_locus(
                tpath, str(run["target_mode"] if run else "source"), args.locus, args.control
            )
            if not ok:
                raise AjarError(msg, EXIT_GATE_BLOCKED)
            now_iso = utc_now_iso()
            conn.execute(
                """
                UPDATE tasks
                SET status = 'dry', worker_id = ?, dry_control_locus = ?, dry_control_reason = ?,
                    lease_expires_at = NULL, closed_epoch = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (
                    args.worker,
                    args.locus,
                    scrub_text(args.control),
                    time.time(),
                    now_iso,
                    args.task_id,
                ),
            )
            log_event(conn, args.worker, "task_dry", args.task_id, {"locus": args.locus})
            pulse = maybe_auto_pulse(conn, tpath)
            _emit({"task_id": args.task_id, "status": "dry", "pulse": pulse}, True)
            return EXIT_OK

        if args.task_cmd == "block":
            now_iso = utc_now_iso()
            conn.execute(
                """
                UPDATE tasks
                SET status = 'conditional_blocked', worker_id = ?, blocker_predicate = ?,
                    blocker_check_locus = ?, lease_expires_at = NULL, updated_at = ?
                WHERE task_id = ?
                """,
                (
                    args.worker,
                    scrub_text(args.predicate),
                    args.check_locus or "",
                    now_iso,
                    args.task_id,
                ),
            )
            log_event(conn, args.worker, "task_conditional_blocked", args.task_id, {"predicate": args.predicate})
            _emit({"task_id": args.task_id, "status": "conditional_blocked"}, True)
            return EXIT_OK

        rows = list_rows(conn, "SELECT * FROM tasks ORDER BY salience_score DESC, created_at ASC")
        _emit({"tasks": rows}, True)
        return EXIT_OK
    finally:
        conn.close()


def cmd_anomaly(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    conn = open_run_db(rid)
    try:
        if args.anomaly_cmd == "add":
            aid = new_id("anom")
            now_iso = utc_now_iso()
            sub = infer_subsystem(args.locus)
            conn.execute(
                """
                INSERT INTO anomalies(
                    anomaly_id, surface_id, source_claim_id, subsystem, locus, observation, repro_cmd, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'unexplained', ?, ?)
                """,
                (
                    aid,
                    args.surface,
                    args.claim,
                    sub,
                    args.locus,
                    scrub_text(args.observation),
                    scrub_text(args.repro_cmd or ""),
                    now_iso,
                    now_iso,
                ),
            )
            # Recording a concrete target observation unlocks stalled claims on that claim/locus.
            if args.claim:
                conn.execute(
                    """
                    UPDATE claims
                    SET instrumented_since_fail = 1,
                        status = CASE WHEN status = 'needs_instrumentation' THEN 'survived_falsify' ELSE status END,
                        updated_at = ?
                    WHERE claim_id = ?
                    """,
                    (now_iso, args.claim),
                )
            log_event(conn, "worker", "anomaly_added", aid, {"locus": args.locus})
            _emit({"anomaly_id": aid, "status": "unexplained", "subsystem": sub}, True)
            return EXIT_OK

        if args.anomaly_cmd == "explain":
            if len(args.reason.strip()) < 12:
                raise AjarError("Explanation --reason must be at least 12 characters.", EXIT_USER_ERROR)
            now_iso = utc_now_iso()
            conn.execute(
                """
                UPDATE anomalies
                SET status = 'benign_explained', explanation_locus = ?, explanation_reason = ?, updated_at = ?
                WHERE anomaly_id = ?
                """,
                (args.locus, scrub_text(args.reason), now_iso, args.anomaly_id),
            )
            log_event(conn, "worker", "anomaly_explained", args.anomaly_id, {"locus": args.locus})
            _emit({"anomaly_id": args.anomaly_id, "status": "benign_explained"}, True)
            return EXIT_OK

        rows = list_rows(conn, "SELECT * FROM anomalies ORDER BY created_at ASC")
        _emit({"anomalies": rows}, True)
        return EXIT_OK
    finally:
        conn.close()


def cmd_primitive(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    conn = open_run_db(rid)
    try:
        if args.primitive_cmd == "add":
            pid = new_id("prim")
            sub = infer_subsystem(args.locus)
            conn.execute(
                """
                INSERT INTO primitives(
                    primitive_id, subsystem, locus, kind, preconditions, postconditions, evidence_cmd, evidence_output, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pid,
                    sub,
                    args.locus,
                    args.kind,
                    scrub_text(args.preconditions),
                    scrub_text(args.postconditions),
                    scrub_text(args.evidence_cmd),
                    scrub_text(args.evidence_output or ""),
                    utc_now_iso(),
                ),
            )
            log_event(conn, "worker", "primitive_added", pid, {"locus": args.locus, "kind": args.kind})
            _emit({"primitive_id": pid, "subsystem": sub}, True)
            return EXIT_OK

        rows = list_rows(conn, "SELECT * FROM primitives ORDER BY created_at ASC")
        _emit({"primitives": rows}, True)
        return EXIT_OK
    finally:
        conn.close()


def cmd_binding(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    conn = open_run_db(rid)
    try:
        if args.binding_cmd == "set":
            run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
            tpath = pathlib.Path(run["target_path"])
            res = set_certified_binding(
                conn,
                target_dir=tpath,
                name=args.name,
                value=args.value,
                locus=args.locus,
                task_id=args.task,
            )
            _emit(res, True)
            return EXIT_OK

        rows = list_rows(conn, "SELECT * FROM certified_bindings ORDER BY updated_at DESC")
        _emit({"bindings": rows}, True)
        return EXIT_OK
    finally:
        conn.close()


def cmd_claim(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    rdir = run_dir_for(rid)
    conn = open_run_db(rid)
    try:
        run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
        tpath = pathlib.Path(run["target_path"])
        tmode = str(run["target_mode"])

        if args.claim_cmd == "propose":
            if len(args.falsification_prediction.strip()) < 10 or len(args.falsification_test.strip()) < 5:
                raise AjarError(
                    "DEC-0128 gate: --falsification-prediction and --falsification-test are required before proposing a claim.",
                    EXIT_GATE_BLOCKED,
                )
            check_dead_end_repetition(
                conn,
                locus=args.locus,
                mechanism=args.mechanism,
                consume_anomaly_id=args.consume_anomaly,
            )
            cid = new_id("clm")
            now_iso = utc_now_iso()
            sub = infer_subsystem(args.locus)
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
                    args.surface,
                    args.worker,
                    1 if args.seeded_by_human else 0,
                    scrub_text(args.title),
                    sub,
                    args.locus,
                    scrub_text(args.mechanism),
                    normalize_mechanism_key(args.mechanism),
                    args.severity,
                    scrub_text(args.falsification_prediction),
                    scrub_text(args.falsification_test),
                    now_iso,
                    now_iso,
                ),
            )
            if args.consume_anomaly:
                conn.execute(
                    "UPDATE anomalies SET status = 'consumed_by_claim', consumed_by_id = ?, updated_at = ? WHERE anomaly_id = ?",
                    (cid, now_iso, args.consume_anomaly),
                )
            log_event(conn, args.worker, "claim_proposed", cid, {"locus": args.locus, "severity": args.severity})
            _emit({"claim_id": cid, "status": "proposed", "subsystem": sub}, True)
            return EXIT_OK

        if args.claim_cmd == "falsify":
            clm = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (args.claim_id,)).fetchone()
            if clm is None:
                raise AjarError(f"Unknown claim_id: {args.claim_id}", EXIT_USER_ERROR)
            now_iso = utc_now_iso()
            conn.execute(
                """
                UPDATE claims
                SET status = 'falsified', falsifier_worker_id = ?, falsify_notes = ?,
                    falsify_control_locus = ?, research_state = 'rejected_during_research',
                    evidence_state = 'falsified', updated_at = ?
                WHERE claim_id = ?
                """,
                (args.worker, scrub_text(args.notes), args.control_locus, now_iso, args.claim_id),
            )
            # Orphaned Anomaly Survival: restore any anomaly tentatively consumed by this disproved claim!
            conn.execute(
                """
                UPDATE anomalies
                SET status = 'unexplained', consumed_by_id = NULL, updated_at = ?
                WHERE consumed_by_id = ? AND status = 'consumed_by_claim'
                """,
                (now_iso, args.claim_id),
            )
            log_event(conn, args.worker, "claim_falsified", args.claim_id, {})
            _emit({"claim_id": args.claim_id, "status": "falsified"}, True)
            return EXIT_OK

        if args.claim_cmd == "survive":
            clm = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (args.claim_id,)).fetchone()
            if clm is None:
                raise AjarError(f"Unknown claim_id: {args.claim_id}", EXIT_USER_ERROR)
            if clm["proposer_worker_id"] == args.worker:
                raise AjarError(
                    f"Fresh-falsifier separation gate: proposer {args.worker!r} cannot validate its own claim. "
                    "Use an independent falsifier worker.",
                    EXIT_GATE_BLOCKED,
                )
            now_iso = utc_now_iso()
            conn.execute(
                "UPDATE claims SET status = 'survived_falsify', falsifier_worker_id = ?, falsify_notes = ?, updated_at = ? WHERE claim_id = ?",
                (args.worker, scrub_text(args.notes), now_iso, args.claim_id),
            )
            log_event(conn, args.worker, "claim_survived_falsify", args.claim_id, {})
            _emit({"claim_id": args.claim_id, "status": "survived_falsify"}, True)
            return EXIT_OK

        if args.claim_cmd == "block":
            now_iso = utc_now_iso()
            conn.execute(
                "UPDATE claims SET status = 'blocked', blocker_reason = ?, updated_at = ? WHERE claim_id = ?",
                (scrub_text(args.reason), now_iso, args.claim_id),
            )
            log_event(conn, args.worker, "claim_blocked", args.claim_id, {"reason": args.reason})
            _emit({"claim_id": args.claim_id, "status": "blocked"}, True)
            return EXIT_OK

        if args.claim_cmd == "reproduce":
            clm = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (args.claim_id,)).fetchone()
            if clm is None:
                raise AjarError(f"Unknown claim_id: {args.claim_id}", EXIT_USER_ERROR)
            if clm["status"] == "needs_instrumentation" and int(clm["instrumented_since_fail"] or 0) == 0:
                raise AjarError(
                    f"Telemetry-pivot gate (`KVMEscape` rule): claim {args.claim_id} failed 2 PoC runs with unchanged observation. "
                    "Complete its `instrument` task or record a target trace (`ajar anomaly add --claim` / `ajar binding set`) before retrying.",
                    EXIT_GATE_BLOCKED,
                )
            if clm["status"] not in ("survived_falsify", "reproduced"):
                raise AjarError(
                    f"Claim {args.claim_id} has status {clm['status']!r}; must pass independent `ajar claim survive` before reproduction.",
                    EXIT_GATE_BLOCKED,
                )
            if not clm["falsifier_worker_id"] or clm["falsifier_worker_id"] == clm["proposer_worker_id"]:
                raise AjarError("Claim lacks an independent falsifier (`proposer != falsifier`).", EXIT_GATE_BLOCKED)

            eff_mode = args.mode or tmode
            oracle_dict = json.loads(args.oracle_json) if args.oracle_json else None

            if eff_mode == "source":
                if not args.micropatch:
                    raise AjarError("Source reproduction requires --micropatch <patch_file>.", EXIT_USER_ERROR)
                siblings = [
                    {"claim_id": r["claim_id"], "poc_cmd": args.sibling_poc_cmd or ""}
                    for r in conn.execute(
                        "SELECT claim_id FROM claims WHERE status = 'survived_falsify' AND claim_id != ?",
                        (args.claim_id,),
                    ).fetchall()
                ] if args.sibling_poc_cmd else None
                res = run_source_reproduction(
                    run_dir=rdir,
                    target_dir=tpath,
                    claim_id=args.claim_id,
                    poc_cmd=args.poc_cmd,
                    control_cmd=args.control_cmd,
                    micropatch_path=pathlib.Path(args.micropatch),
                    oracle=oracle_dict,
                    determinism=args.determinism,
                    trials=args.trials,
                    timeout_sec=args.timeout,
                    warm_cross_kill_claims=siblings,
                )
            elif eff_mode == "binary":
                bin_p = pathlib.Path(args.binary) if args.binary else tpath
                poc_io = json.loads(args.poc_io_json) if args.poc_io_json else {"args": [args.poc_cmd]}
                ctrl_io = json.loads(args.control_io_json) if args.control_io_json else {"args": [args.control_cmd]}
                guard_d = json.loads(args.guard_json) if args.guard_json else None
                abl_d = json.loads(args.ablation_json) if args.ablation_json else None
                res = run_binary_reproduction(
                    run_dir=rdir,
                    binary_path=bin_p,
                    claim_id=args.claim_id,
                    poc_args_or_stdin=poc_io,
                    control_args_or_stdin=ctrl_io,
                    guard_spec=guard_d,
                    ablation_spec=abl_d,
                    timeout_sec=args.timeout,
                )
            elif eff_mode == "live":
                sc_row = conn.execute("SELECT * FROM scope_rules LIMIT 1").fetchone()
                scope_d = {
                    "allowed_hosts": json.loads(sc_row["allowed_hosts_json"]) if sc_row else [],
                    "allow_live_requests": bool(sc_row["allow_live_requests"]) if sc_row else False,
                    "allow_live_mutations": bool(sc_row["allow_live_mutations"]) if sc_row else False,
                }
                res = run_live_reproduction(
                    run_dir=rdir,
                    scope=scope_d,
                    claim_id=args.claim_id,
                    seed_cmd=args.seed_cmd or "",
                    poc_cmd=args.poc_cmd,
                    control_cmd=args.control_cmd,
                    teardown_cmd=args.teardown_cmd or "true",
                    target_url=args.target_url or str(run["target_path"]),
                    timeout_sec=args.timeout,
                )
            else:
                raise AjarError(f"Unsupported reproduction mode: {eff_mode}", EXIT_USER_ERROR)

            if not res["passed"]:
                pivot = record_repro_failure(
                    conn,
                    claim=clm,
                    worker_id=args.worker,
                    observation_hash=str(res.get("observation_hash", "")),
                    reason=str(res.get("reason", "")),
                )
                _emit({"reproduction": res, "claim_update": pivot}, True)
                return EXIT_GATE_BLOCKED

            # Promote to `findings`!
            now_iso = utc_now_iso()
            existing_f = conn.execute("SELECT finding_id FROM findings WHERE claim_id = ?", (args.claim_id,)).fetchone()
            fid = existing_f["finding_id"] if existing_f else new_id("fnd")
            attr = finding_attribution_for_claim(conn, clm)
            conn.execute(
                """
                UPDATE claims
                SET status = 'reproduced', research_state = 'confirmed', evidence_state = 'reproduced',
                    remediation_state = CASE WHEN ? != '' THEN 'micropatched' ELSE remediation_state END,
                    updated_at = ?
                WHERE claim_id = ?
                """,
                (str(res.get("micropatch_diff") or ""), now_iso, args.claim_id),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO findings(
                    finding_id, claim_id, title, severity, locus, root_cause, poc_cmd, control_cmd,
                    micropatch_path, micropatch_diff, arm1_clean_poc_json, arm2_clean_ctrl_json,
                    arm3_patch_poc_json, arm4_patch_ctrl_json, attribution, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fid,
                    args.claim_id,
                    clm["title"],
                    clm["severity"],
                    clm["locus"],
                    clm["mechanism"],
                    scrub_text(args.poc_cmd),
                    scrub_text(args.control_cmd),
                    str(args.micropatch or ""),
                    str(res.get("micropatch_diff") or ""),
                    json.dumps(res["arm1_clean_poc"], sort_keys=True),
                    json.dumps(res["arm2_clean_control"], sort_keys=True),
                    json.dumps(res["arm3_patch_poc"], sort_keys=True),
                    json.dumps(res["arm4_patch_control"], sort_keys=True),
                    attr,
                    now_iso,
                ),
            )
            # Mark warm cross-killed sibling claims as `duplicate_root_cause`.
            for dup_id in res.get("cross_killed_claim_ids") or []:
                conn.execute(
                    """
                    UPDATE claims
                    SET status = 'duplicate_root_cause', duplicate_of_claim_id = ?,
                        research_state = 'rejected_during_research', updated_at = ?
                    WHERE claim_id = ?
                    """,
                    (args.claim_id, now_iso, dup_id),
                )
            log_event(conn, args.worker, "finding_reproduced", fid, {"claim_id": args.claim_id, "attribution": attr})
            _emit({"finding_id": fid, "attribution": attr, "reproduction": res}, True)
            return EXIT_OK

        rows = list_rows(conn, "SELECT * FROM claims ORDER BY created_at ASC")
        _emit({"claims": rows}, True)
        return EXIT_OK
    finally:
        conn.close()


def cmd_chain(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    conn = open_run_db(rid)
    try:
        if args.chain_cmd == "propose":
            run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
            cwd = run["workspace_path"] if run else "."
            env = scrubbed_subprocess_env()
            p1 = subprocess.run(["bash", "-c", args.poc_cmd], cwd=cwd, env=env, capture_output=True, timeout=60, check=False)
            p2 = subprocess.run(["bash", "-c", args.control_cmd], cwd=cwd, env=env, capture_output=True, timeout=60, check=False)
            verified = p1.returncode != 0 and p2.returncode == 0
            steps = [s.strip() for s in args.steps.split(",") if s.strip()]
            cid = new_id("chn")
            now_iso = utc_now_iso()
            ev = {
                "poc_exit": int(p1.returncode),
                "control_exit": int(p2.returncode),
                "poc_stdout": scrub_text(p1.stdout.decode("utf-8", errors="replace")[:1500]),
            }
            conn.execute(
                """
                INSERT INTO chains(chain_id, title, severity, step_ids_json, e2e_poc_cmd, control_cmd, verified, evidence_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cid,
                    scrub_text(args.title),
                    args.severity,
                    json.dumps(steps),
                    scrub_text(args.poc_cmd),
                    scrub_text(args.control_cmd),
                    1 if verified else 0,
                    json.dumps(ev, sort_keys=True),
                    now_iso,
                ),
            )
            if verified:
                for sid in steps:
                    conn.execute("UPDATE primitives SET chained = 1 WHERE primitive_id = ?", (sid,))
                    conn.execute(
                        "UPDATE anomalies SET status = 'consumed_by_chain', consumed_by_id = ?, updated_at = ? WHERE anomaly_id = ?",
                        (cid, now_iso, sid),
                    )
            log_event(conn, "worker", "chain_proposed", cid, {"verified": verified, "steps": steps})
            _emit({"chain_id": cid, "verified": verified, "evidence": ev}, True)
            return EXIT_OK if verified else EXIT_GATE_BLOCKED

        rows = list_rows(conn, "SELECT * FROM chains ORDER BY created_at ASC")
        _emit({"chains": rows}, True)
        return EXIT_OK
    finally:
        conn.close()


def cmd_touch(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    conn = open_run_db(rid)
    try:
        if args.touch_cmd == "add":
            tid = new_id("tch")
            conn.execute(
                "INSERT INTO human_touches(touch_id, kind, actor, notes, created_at) VALUES (?, ?, ?, ?, ?)",
                (tid, args.kind, scrub_text(args.actor), scrub_text(args.notes), utc_now_iso()),
            )
            log_event(conn, args.actor, "human_touch_recorded", tid, {"kind": args.kind})
            _emit({"touch_id": tid, "kind": args.kind}, True)
            return EXIT_OK
        rows = list_rows(conn, "SELECT * FROM human_touches ORDER BY created_at ASC")
        _emit({"human_touches": rows}, True)
        return EXIT_OK
    finally:
        conn.close()


def cmd_spend(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    conn = open_run_db(rid)
    try:
        if args.spend_cmd == "add":
            eid = new_id("spd")
            conn.execute(
                """
                INSERT INTO spend_ledger(entry_id, worker_id, phase, model, tokens_in, tokens_out, cost_usd, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    eid,
                    args.worker,
                    args.phase,
                    args.model or "",
                    int(args.tokens_in),
                    int(args.tokens_out),
                    float(args.cost_usd),
                    scrub_text(args.notes or ""),
                    utc_now_iso(),
                ),
            )
            _emit({"entry_id": eid, "cost_usd": float(args.cost_usd)}, True)
            return EXIT_OK
        rows = list_rows(conn, "SELECT * FROM spend_ledger ORDER BY created_at ASC")
        _emit({"spend_entries": rows}, True)
        return EXIT_OK
    finally:
        conn.close()


def cmd_gate_check(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    conn = open_run_db(rid)
    try:
        run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
        tpath = pathlib.Path(run["target_path"]) if run else None
        res = check_all_gates(conn, target_dir=tpath, auto_enqueue_chain=True)
    finally:
        conn.close()
    _emit(res, True)
    return EXIT_OK if res["passed"] else EXIT_GATE_BLOCKED


def cmd_finish(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    rdir = run_dir_for(rid)
    conn = open_run_db(rid)
    try:
        run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
        tpath = pathlib.Path(run["target_path"]) if run else None
        res = check_all_gates(conn, target_dir=tpath, auto_enqueue_chain=True)
        if not res["passed"]:
            _emit(res, True)
            return EXIT_GATE_BLOCKED
        now_iso = utc_now_iso()
        conn.execute(
            "UPDATE runs SET status = 'finished', stop_reason = 'all_gates_passed', finished_at = ?",
            (now_iso,),
        )
        log_event(conn, "operator", "run_finished", rid, {"findings_count": res["findings_count"]})
        md = render_markdown_report(conn)
        js = build_report_data(conn, include_rejected_appendix=True)
    finally:
        conn.close()

    art_dir = rdir / "artifacts"
    art_dir.mkdir(parents=True, exist_ok=True)
    (art_dir / "report.md").write_text(md, encoding="utf-8")
    (art_dir / "report.json").write_text(json.dumps(js, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    res["report_markdown_path"] = str(art_dir / "report.md")
    res["report_json_path"] = str(art_dir / "report.json")
    _emit(res, True)
    return EXIT_OK


def cmd_report(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    conn = open_run_db(rid)
    try:
        if args.format == "json":
            out_str = json.dumps(
                build_report_data(conn, include_rejected_appendix=bool(args.include_rejected_appendix)),
                indent=2,
                sort_keys=True,
            )
        else:
            out_str = render_markdown_report(conn, include_rejected_appendix=bool(args.include_rejected_appendix))
    finally:
        conn.close()

    if args.output:
        out_p = pathlib.Path(args.output)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(out_str + ("\n" if not out_str.endswith("\n") else ""), encoding="utf-8")
    else:
        print(out_str)
    return EXIT_OK


def cmd_hook(args: argparse.Namespace) -> int:
    try:
        rid = resolve_run_id(args.run)
    except AjarError:
        if args.if_active:
            return EXIT_OK
        raise
    conn = open_run_db(rid)
    try:
        run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
        tpath = pathlib.Path(run["target_path"]) if run else None
        rc, payload = evaluate_claude_stop_hook(conn, target_dir=tpath)
    finally:
        conn.close()
    if rc != EXIT_OK:
        sys.stderr.write(payload["reason"] + "\n")
    print(json.dumps(payload, sort_keys=True))
    return rc


def cmd_loop(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    res = run_host_continuation_loop(
        host_kind=args.host,
        run_id=rid,
        cmd_template=args.cmd,
        max_rounds=args.max_rounds,
    )
    _emit(res, True)
    return EXIT_OK if res.get("completed") else EXIT_GATE_BLOCKED


def cmd_run(args: argparse.Namespace) -> int:
    res = run_autonomous_schedule(
        target=args.target,
        run_id=args.run_id,
        target_mode=args.mode,
        goal=args.goal,
        stopping_criterion=args.until,
        budget_usd=args.budget,
        workers=args.workers,
        worker_cmd=args.worker_cmd,
        max_steps=args.max_steps,
    )
    _emit(res, True)
    return EXIT_OK if res["gates_passed"] else EXIT_GATE_BLOCKED


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ajar",
        description="Ajar: find, disprove, reproduce, and patch software vulnerabilities.",
    )
    p.add_argument("--version", action="version", version=f"ajar {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    # doctor
    p_doc = sub.add_parser("doctor", help="Check local Python, SQLite FTS5, compilers, and sandbox isolation.")
    p_doc.add_argument("--json", action="store_true", default=True)
    p_doc.set_defaults(func=cmd_doctor)

    # init
    p_init = sub.add_parser("init", help="Initialize a new verification run in --envelope or --in-place mode.")
    p_init.add_argument("target", help="Target directory, binary path, or URL.")
    p_init.add_argument("--mode", choices=("source", "binary", "live"), default="source")
    grp_ws = p_init.add_mutually_exclusive_group()
    grp_ws.add_argument("--envelope", action="store_true", default=True, help="Create isolated workspace with read-only target snapshot (default).")
    grp_ws.add_argument("--in-place", action="store_true", help="Write zero files into target directory.")
    p_init.add_argument("--goal", default="Identify, falsify, and reproduce high-severity software vulnerabilities.")
    p_init.add_argument("--until", choices=("exhaustive-high", "first-verified-high"), default="exhaustive-high")
    p_init.add_argument("--budget", type=float, default=40.0)
    p_init.add_argument("--allow-host", action="append", help="Allowed live target hostname.")
    p_init.add_argument("--allow-live-requests", action="store_true")
    p_init.add_argument("--allow-live-mutations", action="store_true")
    p_init.add_argument("--run-id", help="Optional explicit run identifier.")
    p_init.add_argument("--json", action="store_true")
    p_init.set_defaults(func=cmd_init)

    # status
    p_stat = sub.add_parser("status", help="Inspect current run progress, gates, and spend.")
    p_stat.add_argument("--run", help="Run ID.")
    p_stat.add_argument("--json", action="store_true", default=True)
    p_stat.set_defaults(func=cmd_status)

    # context
    p_ctx = sub.add_parser("context", help="Render < 4 KB certified context frame for a task.")
    p_ctx.add_argument("--task", required=True)
    p_ctx.add_argument("--run")
    p_ctx.add_argument("--json", action="store_true")
    p_ctx.set_defaults(func=cmd_context)

    # pulse
    p_pls = sub.add_parser("pulse", help="Expire stale leases, check certified bindings, and rescore salience.")
    p_pls.add_argument("--run")
    p_pls.add_argument("--json", action="store_true", default=True)
    p_pls.set_defaults(func=cmd_pulse)

    # map
    p_map = sub.add_parser("map", help="Build Personalized PageRank repository symbol map.")
    p_map.add_argument("--focus-file", action="append")
    p_map.add_argument("--focus-symbol", action="append")
    p_map.add_argument("--budget-tokens", type=int, default=1500)
    p_map.add_argument("--run")
    p_map.add_argument("--json", action="store_true")
    p_map.set_defaults(func=cmd_map)

    # ref query + precedent search alias
    p_ref = sub.add_parser("ref", help="Query FTS5 index across intent, reachability, and precedent.")
    ref_sub = p_ref.add_subparsers(dest="ref_cmd", required=True)
    p_rq = ref_sub.add_parser("query")
    p_rq.add_argument("--kind", choices=("intent", "reachability", "precedent", "all"), default="all")
    p_rq.add_argument("query")
    p_rq.add_argument("--limit", type=int, default=10)
    p_rq.add_argument("--run")
    p_rq.set_defaults(func=cmd_ref_query)

    p_prec = sub.add_parser("precedent", help="Search curated CVE, chain, and false-positive precedent corpora.")
    prec_sub = p_prec.add_subparsers(dest="prec_cmd", required=True)
    p_ps = prec_sub.add_parser("search")
    p_ps.add_argument("query")
    p_ps.add_argument("--limit", type=int, default=10)
    p_ps.add_argument("--run")
    p_ps.set_defaults(func=cmd_ref_query, kind="precedent")

    # surface
    p_surf = sub.add_parser("surface", help="Manage target entrypoints and trust-boundary surfaces.")
    surf_sub = p_surf.add_subparsers(dest="surface_cmd", required=True)
    ps_add = surf_sub.add_parser("add")
    ps_add.add_argument("--name", required=True)
    ps_add.add_argument("--kind", required=True)
    ps_add.add_argument("--subsystem", default="")
    ps_add.add_argument("--locus", required=True)
    ps_add.add_argument("--priority", choices=("critical", "high", "medium", "low"), default="high")
    ps_add.add_argument("--trust-boundary", default="")
    ps_add.add_argument("--run")
    ps_list = surf_sub.add_parser("list")
    ps_list.add_argument("--run")
    p_surf.set_defaults(func=cmd_surface)

    # driver
    p_drv = sub.add_parser("driver", help="Cache reusable surface setup and invocation commands.")
    drv_sub = p_drv.add_subparsers(dest="driver_cmd", required=True)
    pd_add = drv_sub.add_parser("add")
    pd_add.add_argument("--surface", required=True)
    pd_add.add_argument("--setup-cmd", required=True)
    pd_add.add_argument("--invoke-template", required=True)
    pd_add.add_argument("--teardown-cmd", default="")
    pd_add.add_argument("--notes", default="")
    pd_add.add_argument("--run")
    pd_list = drv_sub.add_parser("list")
    pd_list.add_argument("--run")
    p_drv.set_defaults(func=cmd_driver)

    # task
    p_tsk = sub.add_parser("task", help="Coordinate bounded work tasks (`lease`, `done`, `dry`, `block`).")
    tsk_sub = p_tsk.add_subparsers(dest="task_cmd", required=True)
    pt_add = tsk_sub.add_parser("add")
    pt_add.add_argument("--kind", choices=("map", "investigate", "falsify", "reproduce", "instrument", "chain", "patch"), required=True)
    pt_add.add_argument("--title", required=True)
    pt_add.add_argument("--surface")
    pt_add.add_argument("--parent")
    pt_add.add_argument("--subsystem")
    pt_add.add_argument("--locus")
    pt_add.add_argument("--priority", choices=("critical", "high", "medium", "low"), default="high")
    pt_add.add_argument("--run")

    pt_lease = tsk_sub.add_parser("lease")
    pt_lease.add_argument("--worker", required=True)
    pt_lease.add_argument("--kind", choices=("map", "investigate", "falsify", "reproduce", "instrument", "chain", "patch"))
    pt_lease.add_argument("--ttl", type=int, default=900)
    pt_lease.add_argument("--recover", action="store_true")
    pt_lease.add_argument("--run")

    pt_done = tsk_sub.add_parser("done")
    pt_done.add_argument("task_id")
    pt_done.add_argument("--worker", required=True)
    pt_done.add_argument("--summary", default="")
    pt_done.add_argument("--run")

    pt_dry = tsk_sub.add_parser("dry")
    pt_dry.add_argument("task_id")
    pt_dry.add_argument("--worker", required=True)
    pt_dry.add_argument("--locus", required=True, help="Exact guard file:lines.")
    pt_dry.add_argument("--control", required=True, help="Why the concrete guard prevents the bug.")
    pt_dry.add_argument("--run")

    pt_blk = tsk_sub.add_parser("block")
    pt_blk.add_argument("task_id")
    pt_blk.add_argument("--worker", required=True)
    pt_blk.add_argument("--predicate", required=True)
    pt_blk.add_argument("--check-locus", default="")
    pt_blk.add_argument("--run")

    pt_lst = tsk_sub.add_parser("list")
    pt_lst.add_argument("--run")
    p_tsk.set_defaults(func=cmd_task)

    # anomaly
    p_an = sub.add_parser("anomaly", help="Record or explain execution anomalies (decoupled from claim survival).")
    an_sub = p_an.add_subparsers(dest="anomaly_cmd", required=True)
    pa_add = an_sub.add_parser("add")
    pa_add.add_argument("--locus", required=True)
    pa_add.add_argument("--observation", required=True)
    pa_add.add_argument("--repro-cmd", default="")
    pa_add.add_argument("--surface")
    pa_add.add_argument("--claim")
    pa_add.add_argument("--run")
    pa_exp = an_sub.add_parser("explain")
    pa_exp.add_argument("anomaly_id")
    pa_exp.add_argument("--locus", required=True)
    pa_exp.add_argument("--reason", required=True)
    pa_exp.add_argument("--run")
    pa_lst = an_sub.add_parser("list")
    pa_lst.add_argument("--run")
    p_an.set_defaults(func=cmd_anomaly)

    # primitive
    p_pr = sub.add_parser("primitive", help="Register verified non-standalone behaviors for multi-step chaining.")
    pr_sub = p_pr.add_subparsers(dest="primitive_cmd", required=True)
    pp_add = pr_sub.add_parser("add")
    pp_add.add_argument("--locus", required=True)
    pp_add.add_argument("--kind", required=True)
    pp_add.add_argument("--preconditions", required=True)
    pp_add.add_argument("--postconditions", required=True)
    pp_add.add_argument("--evidence-cmd", required=True)
    pp_add.add_argument("--evidence-output", default="")
    pp_add.add_argument("--run")
    pp_lst = pr_sub.add_parser("list")
    pp_lst.add_argument("--run")
    p_pr.set_defaults(func=cmd_primitive)

    # binding
    p_bd = sub.add_parser("binding", help="Certify exact file-hash-bound constants and offsets.")
    bd_sub = p_bd.add_subparsers(dest="binding_cmd", required=True)
    pb_set = bd_sub.add_parser("set")
    pb_set.add_argument("--name", required=True)
    pb_set.add_argument("--value", required=True)
    pb_set.add_argument("--locus", required=True)
    pb_set.add_argument("--task")
    pb_set.add_argument("--run")
    pb_lst = bd_sub.add_parser("list")
    pb_lst.add_argument("--run")
    p_bd.set_defaults(func=cmd_binding)

    # claim
    p_cl = sub.add_parser("claim", help="Manage vulnerability hypotheses (`propose`, `falsify`, `survive`, `reproduce`).")
    cl_sub = p_cl.add_subparsers(dest="claim_cmd", required=True)
    pc_prop = cl_sub.add_parser("propose")
    pc_prop.add_argument("--worker", required=True)
    pc_prop.add_argument("--title", required=True)
    pc_prop.add_argument("--locus", required=True)
    pc_prop.add_argument("--mechanism", required=True)
    pc_prop.add_argument("--severity", choices=("critical", "high", "medium", "low"), default="high")
    pc_prop.add_argument("--falsification-prediction", required=True)
    pc_prop.add_argument("--falsification-test", required=True)
    pc_prop.add_argument("--surface")
    pc_prop.add_argument("--consume-anomaly")
    pc_prop.add_argument("--seeded-by-human", action="store_true")
    pc_prop.add_argument("--run")

    pc_fal = cl_sub.add_parser("falsify")
    pc_fal.add_argument("claim_id")
    pc_fal.add_argument("--worker", required=True)
    pc_fal.add_argument("--notes", required=True)
    pc_fal.add_argument("--control-locus")
    pc_fal.add_argument("--run")

    pc_sur = cl_sub.add_parser("survive")
    pc_sur.add_argument("claim_id")
    pc_sur.add_argument("--worker", required=True)
    pc_sur.add_argument("--notes", required=True)
    pc_sur.add_argument("--run")

    pc_blk = cl_sub.add_parser("block")
    pc_blk.add_argument("claim_id")
    pc_blk.add_argument("--worker", required=True)
    pc_blk.add_argument("--reason", required=True)
    pc_blk.add_argument("--run")

    pc_rep = cl_sub.add_parser("reproduce")
    pc_rep.add_argument("claim_id")
    pc_rep.add_argument("--worker", required=True)
    pc_rep.add_argument("--mode", choices=("source", "binary", "live"))
    pc_rep.add_argument("--poc-cmd", default="")
    pc_rep.add_argument("--control-cmd", default="")
    pc_rep.add_argument("--micropatch", help="Path to 1-5 line counterfactual unified diff (source mode).")
    pc_rep.add_argument("--oracle-json", help="Optional JSON oracle rules (`expect_regex`, `expect_exit_code`).")
    pc_rep.add_argument("--determinism", choices=("deterministic", "probabilistic_race"), default="deterministic")
    pc_rep.add_argument("--trials", type=int, default=8)
    pc_rep.add_argument("--timeout", type=int, default=60)
    pc_rep.add_argument("--sibling-poc-cmd", help="Optional sibling PoC command for warm cross-kill dedup.")
    pc_rep.add_argument("--binary", help="Executable path override for binary mode.")
    pc_rep.add_argument("--poc-io-json", help="Binary PoC args/stdin JSON.")
    pc_rep.add_argument("--control-io-json", help="Binary control args/stdin JSON.")
    pc_rep.add_argument("--guard-json", help="Binary gdb runtime guard JSON.")
    pc_rep.add_argument("--ablation-json", help="Binary 1-field input ablation JSON.")
    pc_rep.add_argument("--seed-cmd", help="Live mode synthetic state seeder.")
    pc_rep.add_argument("--teardown-cmd", help="Live mode teardown command.")
    pc_rep.add_argument("--target-url", help="Live mode target URL.")
    pc_rep.add_argument("--run")

    pc_lst = cl_sub.add_parser("list")
    pc_lst.add_argument("--run")
    p_cl.set_defaults(func=cmd_claim)

    # chain
    p_ch = sub.add_parser("chain", help="Compose verified primitives and findings into multi-step chains.")
    ch_sub = p_ch.add_subparsers(dest="chain_cmd", required=True)
    pch_p = ch_sub.add_parser("propose")
    pch_p.add_argument("--title", required=True)
    pch_p.add_argument("--steps", required=True, help="Comma-separated primitive/anomaly/finding IDs.")
    pch_p.add_argument("--poc-cmd", required=True)
    pch_p.add_argument("--control-cmd", required=True)
    pch_p.add_argument("--severity", choices=("critical", "high", "medium", "low"), default="critical")
    pch_p.add_argument("--run")
    pch_l = ch_sub.add_parser("list")
    pch_l.add_argument("--run")
    p_ch.set_defaults(func=cmd_chain)

    # touch
    p_tc = sub.add_parser("touch", help="Record human touches for run attribution (`DEC-0061`/`0071`).")
    tc_sub = p_tc.add_subparsers(dest="touch_cmd", required=True)
    ptc_a = tc_sub.add_parser("add")
    ptc_a.add_argument("--kind", choices=("scope_authority", "env_rescue", "research_steering", "poc_repair", "review_signoff"), required=True)
    ptc_a.add_argument("--notes", required=True)
    ptc_a.add_argument("--actor", default="operator")
    ptc_a.add_argument("--run")
    ptc_l = tc_sub.add_parser("list")
    ptc_l.add_argument("--run")
    p_tc.set_defaults(func=cmd_touch)

    # spend
    p_sp = sub.add_parser("spend", help="Record model token and USD spend (`DEC-0122`).")
    sp_sub = p_sp.add_subparsers(dest="spend_cmd", required=True)
    psp_a = sp_sub.add_parser("add")
    psp_a.add_argument("--worker", required=True)
    psp_a.add_argument("--cost-usd", type=float, required=True)
    psp_a.add_argument("--phase", choices=("explore", "verify"), default="explore")
    psp_a.add_argument("--model", default="")
    psp_a.add_argument("--tokens-in", type=int, default=0)
    psp_a.add_argument("--tokens-out", type=int, default=0)
    psp_a.add_argument("--notes", default="")
    psp_a.add_argument("--run")
    psp_l = sp_sub.add_parser("list")
    psp_l.add_argument("--run")
    p_sp.set_defaults(func=cmd_spend)

    # gate check
    p_gt = sub.add_parser("gate", help="Check SQL closeout gates `G1`–`G5`.")
    gt_sub = p_gt.add_subparsers(dest="gate_cmd", required=True)
    pg_c = gt_sub.add_parser("check")
    pg_c.add_argument("--run")
    pg_c.add_argument("--json", action="store_true", default=True)
    pg_c.set_defaults(func=cmd_gate_check)

    # finish
    p_fin = sub.add_parser("finish", help="Verify all closeout gates pass and finalize run report.")
    p_fin.add_argument("--run")
    p_fin.add_argument("--json", action="store_true", default=True)
    p_fin.set_defaults(func=cmd_finish)

    # report
    p_rep = sub.add_parser("report", help="Render Markdown or JSON security verification report.")
    p_rep.add_argument("--run")
    p_rep.add_argument("--format", choices=("md", "json"), default="md")
    p_rep.add_argument("--output")
    p_rep.add_argument("--include-rejected-appendix", action="store_true")
    p_rep.set_defaults(func=cmd_report)

    # mcp
    p_mcp = sub.add_parser("mcp", help="Run STDIO JSON-RPC 2.0 MCP server for Host Mode agents.")
    p_mcp.add_argument("--run")
    p_mcp.set_defaults(func=lambda a: (serve_mcp_stdio(explicit_run_id=a.run), EXIT_OK)[1])

    # hook
    p_hk = sub.add_parser("hook", help="Host Mode persistence hooks.")
    hk_sub = p_hk.add_subparsers(dest="hook_cmd", required=True)
    ph_cs = hk_sub.add_parser("claude-stop")
    ph_cs.add_argument("--run")
    ph_cs.add_argument("--if-active", action="store_true")
    ph_cs.set_defaults(func=cmd_hook)

    # loop
    p_lp = sub.add_parser("loop", help="Host Mode continuation loop for Codex, OMP, or custom CLIs.")
    p_lp.add_argument("host", choices=("codex", "omp", "custom"))
    p_lp.add_argument("--cmd", help="Shell command template (`{prompt}` placeholder supported).")
    p_lp.add_argument("--max-rounds", type=int, default=12)
    p_lp.add_argument("--run")
    p_lp.set_defaults(func=cmd_loop)

    # run (Standalone Mode)
    p_run = sub.add_parser("run", help="Run Standalone autonomous verification with 80/20 budget reserve.")
    p_run.add_argument("target")
    p_run.add_argument("--run-id")
    p_run.add_argument("--mode", choices=("source", "binary", "live"), default="source")
    p_run.add_argument("--goal", default="Identify, falsify, and reproduce high-severity software vulnerabilities.")
    p_run.add_argument("--until", choices=("exhaustive-high", "first-verified-high"), default="exhaustive-high")
    p_run.add_argument("--budget", type=float, default=40.0)
    p_run.add_argument("--workers", type=int, default=2)
    p_run.add_argument("--worker-cmd", help="Worker command executed per leased task.")
    p_run.add_argument("--max-steps", type=int, default=50)
    p_run.add_argument("--json", action="store_true", default=True)
    p_run.set_defaults(func=cmd_run)

    return p


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except AjarError as exc:
        err_obj = {"error": scrub_text(str(exc)), "exit_code": exc.exit_code, **exc.details}
        sys.stderr.write(json.dumps(err_obj, sort_keys=True) + "\n")
        return int(exc.exit_code)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
