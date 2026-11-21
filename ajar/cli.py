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
from ajar.chain_planner import (
    VALID_DOOR_DIRECTIONS,
    VALID_IMPACT_CLASSES,
    _parse_symbol_list,
    add_crown_jewel,
    compute_chain_frontier,
    evaluate_precondition_realism,
    list_crown_jewels,
    park_open_door,
)
from ajar.db import (
    AjarError,
    add_steer,
    add_threat_assumption,
    calibrate_finding,
    check_dead_end_repetition,
    checkpoint_task,
    compute_task_salience,
    infer_subsystem,
    lease_next_task,
    list_rows,
    list_steers,
    log_event,
    mark_primitive_dry,
    maybe_auto_pulse,
    new_id,
    normalize_mechanism_key,
    open_run_db,
    recompute_all_open_salience,
    record_coverage_span,
    record_repro_failure,
    render_task_context,
    rescope_claim,
    resolve_run_id,
    revoke_steer,
    run_dir_for,
    run_pulse,
    set_certified_binding,
    transition_threat_assumption,
    upsert_threat_model,
    utc_now_iso,
)
from ajar.domain import (
    InvalidTransitionError,
    assert_valid_anomaly_transition,
    assert_valid_claim_transition,
    assert_valid_phase_transition,
    assert_valid_task_transition,
    derive_claim_axes,
)
from ajar.epistemic_hooks import (
    claim_requires_release_ub_diff,
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
    check_all_gates,
    check_guarded_primitive_dry_block,
    finding_attribution_for_claim,
    validate_dry_locus,
)
from ajar.graph import export_attack_flow_graph
from ajar.hooks import evaluate_claude_stop_hook, run_host_continuation_loop
from ajar.mcp import serve_mcp_stdio
from ajar.oracles import query_oracle
from ajar.patch_verify import run_8arm_patch_verification
from ajar.redact import scrub_text, scrubbed_subprocess_env
from ajar.repomap import build_repomap, compute_quote_summary
from ajar.report import build_report_data, render_markdown_report
from ajar.repro_binary_live import run_binary_reproduction, run_live_reproduction
from ajar.repro_compose import (
    _parse_step_micropatches,
    promote_primitive_helper,
    run_chain_reproduction,
    run_claim_instrumentation,
    run_snapshot_chain_probe,
)
from ajar.repro_source import (
    run_repro_try,
    run_source_reproduction,
    unshare_netns_available,
    validate_micropatch_diff,
)
from ajar.runner import run_autonomous_schedule
from ajar.store import assert_run_mutable, immediate_tx
from ajar.swarm import (
    ENV_BLOCKER_KINDS,
    VALID_FALLBACK_REASONS,
    VALID_SWARM_STAGES,
    WIRE_PROFILE_LADDER,
    build_swarm_packet,
    complete_swarm_dispatch,
    escalate_swarm_fallback,
    reopen_run,
    sync_run_to_shared_mirror,
    validate_claim_block_request,
    validate_structural_claim_prose,
)
from ajar.target_check import compute_disk_free_gib, evaluate_target_readiness
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
    report: dict[str, Any] = {
        "ajar_version": __version__,
        "python_version": sys.version.split()[0],
        "python_ok": py_ok,
        "sqlite_version": sqlite3.sqlite_version,
        "sqlite_fts5_ok": fts5_ok,
        "unshare_netns_available": unshare_netns_available(),
        "isolation_mode": "unshare_netns" if unshare_netns_available() else "loopback_socket_guard_pgid_reaper",
        "disk": compute_disk_free_gib(),
        "toolchains": {k: bool(v) for k, v in found.items()},
        "toolchain_paths": {k: v for k, v in found.items() if v},
    }
    base_ok = py_ok and fts5_ok and bool(found["git"])
    if getattr(args, "target", None):
        tc = evaluate_target_readiness(
            args.target,
            subdir=getattr(args, "subdir", "") or "",
            ref=getattr(args, "ref", "") or "",
            peers=getattr(args, "peer", None) or (),
            max_age_days=int(getattr(args, "max_age_days", 90)),
            check_remote=not bool(getattr(args, "no_remote", False)),
        )
        report["target_check"] = tc
        _emit(report, bool(args.json))
        if not base_ok:
            return EXIT_USER_ERROR
        return EXIT_OK if tc["passed"] else EXIT_GATE_BLOCKED
    _emit(report, bool(args.json))
    return EXIT_OK if base_ok else EXIT_USER_ERROR


def cmd_quote(args: argparse.Namespace) -> int:
    tpath = pathlib.Path(args.target).expanduser().resolve()
    if not tpath.exists():
        raise AjarError(f"Target path does not exist: {tpath}", EXIT_USER_ERROR)
    try:
        summary = compute_quote_summary(tpath, diff_range=args.diff)
    except ValueError as exc:
        raise AjarError(str(exc), EXIT_USER_ERROR) from exc
    _emit(summary, True)
    return EXIT_OK


def cmd_init(args: argparse.Namespace) -> int:
    ws_mode = "in_place" if args.in_place else "envelope"
    info = init_run_workspace(
        target=args.target,
        target_mode=args.mode,
        workspace_mode=ws_mode,
        goal=args.goal,
        stopping_criterion=args.until,
        campaign_phase=getattr(args, "phase", "hunt") or "hunt",
        budget_usd=args.budget,
        uncapped=bool(args.uncapped),
        brief_file=args.brief_file,
        allowed_hosts=args.allow_host or [],
        allow_live_requests=bool(args.allow_live_requests),
        allow_live_mutations=bool(args.allow_live_mutations),
        allow_historical_target=bool(getattr(args, "allow_historical_target", False)),
        run_id=args.run_id,
        diff_range=args.diff,
        parent_run_id=args.parent_run,
    )
    if args.json:
        _emit(info, True)
    else:
        cap_str = (
            "uncapped [uncapped_research]"
            if info["pricing_mode"] == "uncapped_research"
            else f"${info['cogs_cap_usd']:.2f} [{info['pricing_mode']}]"
        )
        print(f"Initialized Ajar run: {info['run_id']}")
        print(f"  Workspace ({info['workspace_mode']}): {info['workspace_path']}")
        print(f"  Target ({info['target_mode']}):    {info['target_path']}")
        print(f"  Phase / Stopping:       {info['campaign_phase']} / {info['stopping_criterion']}")
        print(f"  In-scope LoC:           {info['in_scope_loc']} (Code quote: ${info['code_quote_usd']:.2f}, COGS cap: {cap_str})")
        if info.get("brief_path"):
            print(f"  Campaign Brief:         {info['brief_path']}")
        if info.get("diff_range"):
            print(f"  PR Diff Range:          {info['diff_range']}")
        print(f"  Commitment SHA-256:     {info['commitment_hash']}")
        print(f"  Export for shell:       export AJAR_RUN_ID={info['run_id']}")
    return EXIT_OK


def cmd_brief(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    rdir = run_dir_for(rid)
    bpath = rdir / "brief.md"
    if args.set_file:
        src = pathlib.Path(args.set_file).expanduser().resolve()
        if not src.is_file():
            raise AjarError(f"Campaign brief file does not exist: {src}", EXIT_USER_ERROR)
        raw = src.read_text(encoding="utf-8", errors="ignore")
        cleaned = scrub_text(raw).strip() + "\n"
        bpath.write_text(cleaned, encoding="utf-8")
        conn = open_run_db(rid)
        try:
            log_event(conn, "operator", "campaign_brief_updated", rid, {"brief_path": str(bpath), "bytes": len(cleaned)})
        finally:
            conn.close()
    text = bpath.read_text(encoding="utf-8", errors="ignore") if bpath.is_file() else ""
    if args.json:
        _emit(
            {
                "run_id": rid,
                "has_campaign_brief": bool(text.strip()),
                "brief_path": str(bpath) if bpath.is_file() else "",
                "brief_markdown": text,
            },
            True,
        )
    else:
        if text:
            print(text, end="" if text.endswith("\n") else "\n")
        else:
            print(f"(No campaign brief set for run {rid}; pass `ajar brief --set-file <brief.md>`.)")
    return EXIT_OK


def cmd_status(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    rdir = run_dir_for(rid)
    bpath = rdir / "brief.md"
    conn = open_run_db(rid)
    try:
        run = dict(conn.execute("SELECT * FROM runs LIMIT 1").fetchone())
        tpath = pathlib.Path(run["target_path"])
        gates = check_all_gates(conn, target_dir=tpath, auto_enqueue_chain=False)
        tm_row = conn.execute("SELECT revision FROM threat_models LIMIT 1").fetchone()
        payload = {
            "run": run,
            "campaign_phase": str(run.get("campaign_phase", "hunt")),
            "crown_jewel_reached": gates["crown_jewel_reached"],
            "has_campaign_brief": bpath.is_file(),
            "brief_path": str(bpath) if bpath.is_file() else "",
            "has_threat_model": tm_row is not None,
            "threat_model_revision": int(tm_row["revision"]) if tm_row is not None else 0,
            "violated_threat_assumptions": conn.execute(
                "SELECT COUNT(*) AS c FROM threat_assumptions WHERE status = 'violated'"
            ).fetchone()["c"],
            "surfaces_count": conn.execute("SELECT COUNT(*) AS c FROM surfaces").fetchone()["c"],
            "open_doors_by_status": {
                r["status"]: int(r["c"])
                for r in conn.execute("SELECT status, COUNT(*) AS c FROM parked_doors GROUP BY status").fetchall()
            },
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
            "active_epistemic_hooks": conn.execute(
                "SELECT COUNT(*) AS c FROM epistemic_hooks WHERE status = 'active'"
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


def cmd_threat_model(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    conn = open_run_db(rid)
    try:
        subcmd = args.tm_cmd
        if subcmd == "set":
            principals = [x.strip() for x in (args.principals or "").split(",") if x.strip()]
            assets = [x.strip() for x in (args.assets or "").split(",") if x.strip()]
            tiers = [x.strip() for x in (args.consumer_tiers or "").split(",") if x.strip()]
            res = upsert_threat_model(
                conn,
                principals=principals,
                assets=assets,
                consumer_tiers=tiers,
                summary=args.summary or "",
            )
            _emit(res, True)
        elif subcmd == "show":
            tm = conn.execute("SELECT * FROM threat_models LIMIT 1").fetchone()
            assumptions = list_rows(conn, "SELECT * FROM threat_assumptions ORDER BY created_at ASC")
            counts = {
                "total": len(assumptions),
                "assumed": sum(1 for a in assumptions if a["status"] == "assumed"),
                "verified_holds": sum(1 for a in assumptions if a["status"] == "verified_holds"),
                "violated": sum(1 for a in assumptions if a["status"] == "violated"),
            }
            _emit(
                {
                    "run_id": rid,
                    "threat_model": dict(tm) if tm else None,
                    "counts": counts,
                    "assumptions": assumptions,
                },
                True,
            )
        elif subcmd == "assumption-add":
            tags = [x.strip() for x in (args.invalidated_by_tags or "").split(",") if x.strip()]
            res = add_threat_assumption(
                conn,
                subsystem=args.subsystem or "",
                assumption_text=args.assumption,
                trust_boundary=args.trust_boundary or "",
                check_locus=args.check_locus or "",
                invalidated_by_tags=tags,
                dependent_surface_id=args.dependent_surface or "",
                escalate_priority=args.escalate_priority,
            )
            _emit(res, True)
        elif subcmd == "assumption-list":
            rows = list_rows(conn, "SELECT * FROM threat_assumptions ORDER BY created_at ASC")
            _emit({"assumptions": rows}, True)
        elif subcmd == "verify":
            res = transition_threat_assumption(
                conn,
                args.assumption_id,
                new_status="verified_holds",
                evidence_ref=args.locus or "",
                notes=args.notes or "",
            )
            _emit(res, True)
        elif subcmd == "invalidate":
            res = transition_threat_assumption(
                conn,
                args.assumption_id,
                new_status="violated",
                evidence_ref=args.evidence or "",
                notes=args.notes or "",
            )
            _emit(res, True)
    finally:
        conn.close()
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
            slice_cap=args.slice_cap,
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
            req_tags = parse_tag_list(getattr(args, "requires_tags", None))
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
                    scrub_text(args.name),
                    args.kind,
                    sub,
                    args.locus,
                    args.priority,
                    scrub_text(args.trust_boundary or ""),
                    json.dumps(req_tags),
                    now_iso,
                ),
            )
            fired_codes: list[str] = []
            run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
            tpath = pathlib.Path(run["target_path"]) if run else None
            rel_file = args.locus.split(":", 1)[0].strip().lstrip("./")
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
                                target_locus=args.locus,
                                directive_text=directive,
                                kill_rule=kill_r,
                            )
                            fired_codes.append(hcode)
                except ValueError:
                    pass
            log_event(
                conn,
                "worker",
                "surface_added",
                sid,
                {"name": args.name, "locus": args.locus, "requires_tags": req_tags, "hooks": fired_codes},
            )
            _emit(
                {
                    "surface_id": sid,
                    "subsystem": sub,
                    "priority": args.priority,
                    "requires_tags": req_tags,
                    "hooks_triggered": fired_codes,
                },
                True,
            )
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
            direction = getattr(args, "direction", "outside_in") or "outside_in"
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
                    task_id, parent_task_id, surface_id, kind, direction, title, subsystem, locus,
                    priority, status, salience_score, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)
                """,
                (
                    tid,
                    args.parent,
                    args.surface,
                    args.kind,
                    direction,
                    scrub_text(args.title),
                    sub,
                    args.locus or "",
                    args.priority,
                    sal,
                    now_iso,
                    now_iso,
                ),
            )
            log_event(conn, "worker", "task_added", tid, {"kind": args.kind, "direction": direction, "salience_score": sal})
            _emit({"task_id": tid, "direction": direction, "salience_score": sal, "subsystem": sub}, True)
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
                leased["context"] = render_task_context(
                    conn, leased["task_id"], record_exposure=not bool(args.recover)
                )["rendered"]
            _emit({"leased": leased}, True)
            return EXIT_OK

        if args.task_cmd == "checkpoint":
            try:
                parsed_state = json.loads(args.state_json)
            except json.JSONDecodeError as exc:
                raise AjarError(f"Invalid --state-json JSON object: {exc}", EXIT_USER_ERROR) from exc
            if not isinstance(parsed_state, dict):
                raise AjarError("--state-json must decode to a JSON object (`{...}`).", EXIT_USER_ERROR)
            res = checkpoint_task(
                conn,
                task_id=args.task_id,
                worker_id=args.worker,
                state_dict=parsed_state,
            )
            _emit(res, True)
            return EXIT_OK

        if args.task_cmd == "done":
            assert_run_mutable(conn, operation="task_done")
            now_iso = utc_now_iso()
            cur = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (args.task_id,)).fetchone()
            if cur is None:
                raise AjarError(f"Unknown task_id: {args.task_id}", EXIT_USER_ERROR)
            assert_valid_task_transition(str(cur["status"]), "done", task_id=args.task_id)
            with immediate_tx(conn):
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
                if cur["kind"] == "escalate" and cur["locus"]:
                    consume_hooks_for_locus(conn, locus=str(cur["locus"]), hook_code="H5_POST_CONFIRM_ESCALATION")
                log_event(conn, args.worker, "task_done", args.task_id, {"kind": cur["kind"]})
            pulse = maybe_auto_pulse(conn, tpath)
            _emit({"task_id": args.task_id, "status": "done", "pulse": pulse}, True)
            return EXIT_OK

        if args.task_cmd == "dry":
            assert_run_mutable(conn, operation="task_dry")
            cur = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (args.task_id,)).fetchone()
            if cur is None:
                raise AjarError(f"Unknown task_id: {args.task_id}", EXIT_USER_ERROR)
            assert_valid_task_transition(str(cur["status"]), "dry", task_id=args.task_id)
            ok, msg = validate_dry_locus(
                tpath, str(run["target_mode"] if run else "source"), args.locus, args.control
            )
            if not ok:
                raise AjarError(msg, EXIT_GATE_BLOCKED)
            ok_gp, msg_gp = check_guarded_primitive_dry_block(conn, task_row=cur, dry_locus=args.locus)
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
                    (
                        args.worker,
                        args.locus,
                        scrub_text(args.control),
                        time.time(),
                        now_iso,
                        args.task_id,
                    ),
                )
                consume_hooks_for_locus(conn, locus=args.locus)
                if cur["locus"]:
                    consume_hooks_for_locus(conn, locus=str(cur["locus"]))
                log_event(conn, args.worker, "task_dry", args.task_id, {"locus": args.locus})
            pulse = maybe_auto_pulse(conn, tpath)
            _emit({"task_id": args.task_id, "status": "dry", "pulse": pulse}, True)
            return EXIT_OK

        if args.task_cmd == "block":
            assert_run_mutable(conn, operation="task_block")
            cur = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (args.task_id,)).fetchone()
            if cur is None:
                raise AjarError(f"Unknown task_id: {args.task_id}", EXIT_USER_ERROR)
            assert_valid_task_transition(str(cur["status"]), "conditional_blocked", task_id=args.task_id)
            now_iso = utc_now_iso()
            with immediate_tx(conn):
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


def cmd_coverage(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    conn = open_run_db(rid)
    try:
        if args.coverage_cmd == "record":
            run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
            tpath = pathlib.Path(run["target_path"])
            res = record_coverage_span(
                conn,
                target_dir=tpath,
                task_id=args.task,
                worker_id=args.worker,
                rel_path=args.rel_path,
                start_line=int(args.start_line),
                end_line=int(args.end_line),
            )
            _emit(res, True)
            return EXIT_OK

        rows = list_rows(conn, "SELECT * FROM coverage_spans ORDER BY rel_path ASC, start_line ASC")
        _emit({"coverage_spans": rows}, True)
        return EXIT_OK
    finally:
        conn.close()


def cmd_anomaly(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    conn = open_run_db(rid)
    try:
        if args.anomaly_cmd == "add":
            run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
            tpath = pathlib.Path(run["target_path"]) if run else None
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
            hooks = on_anomaly_or_claim_recorded(
                conn,
                entity_id=aid,
                trigger_cmd="anomaly.add",
                subsystem=sub,
                locus=args.locus,
                text_blob=args.observation,
                target_dir=tpath,
            )
            log_event(conn, "worker", "anomaly_added", aid, {"locus": args.locus})
            _emit(
                {
                    "anomaly_id": aid,
                    "status": "unexplained",
                    "subsystem": sub,
                    "hooks_triggered": [h["hook_code"] for h in hooks],
                },
                True,
            )
            return EXIT_OK

        if args.anomaly_cmd == "explain":
            assert_run_mutable(conn, operation="anomaly_explain")
            if len(args.reason.strip()) < 12:
                raise AjarError("Explanation --reason must be at least 12 characters.", EXIT_USER_ERROR)
            anom = conn.execute("SELECT status FROM anomalies WHERE anomaly_id = ?", (args.anomaly_id,)).fetchone()
            if anom is None:
                raise AjarError(f"Unknown anomaly_id: {args.anomaly_id}", EXIT_USER_ERROR)
            assert_valid_anomaly_transition(str(anom["status"]), "benign_explained", anomaly_id=args.anomaly_id)
            now_iso = utc_now_iso()
            with immediate_tx(conn):
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
    rdir = run_dir_for(rid)
    conn = open_run_db(rid)
    try:
        if args.primitive_cmd == "add":
            pid = new_id("prim")
            sub = infer_subsystem(args.locus)
            role = (getattr(args, "role", None) or "capability").strip()
            if role not in ("capability", "trust_gadget"):
                raise AjarError(f"Unsupported --role {role!r}; choose 'capability' or 'trust_gadget'.", EXIT_USER_ERROR)
            trusted_inv = scrub_text((getattr(args, "trusted_invariant", None) or "").strip())
            syms = _parse_symbol_list(getattr(args, "symbols", None))
            snap_id = (getattr(args, "snapshot", None) or "").strip()
            mp_diff = ""
            mp_arg = (getattr(args, "micropatch", None) or "").strip()
            if mp_arg:
                mp_file = pathlib.Path(mp_arg).expanduser().resolve()
                if not mp_file.is_file():
                    raise AjarError(f"Primitive --micropatch file not found: {mp_file}", EXIT_USER_ERROR)
                raw_mp = mp_file.read_text(encoding="utf-8", errors="replace")
                ok_mp, mp_msg, _ = validate_micropatch_diff(raw_mp, max_changed_lines=24, claim_locus=args.locus)
                if not ok_mp:
                    raise AjarError(f"Primitive --micropatch invalid: {mp_msg}", EXIT_GATE_BLOCKED)
                mp_diff = scrub_text(raw_mp[:4000])

            guarded_by = (getattr(args, "guarded_by", None) or "").strip()
            guard_assumption = scrub_text(getattr(args, "guard_assumption", None) or "")
            prov_tags = parse_tag_list(getattr(args, "provides_tags", None))
            req_tags = parse_tag_list(getattr(args, "requires_tags", None))
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
                    getattr(args, "surface", None),
                    sub,
                    args.locus,
                    args.kind,
                    role,
                    trusted_inv,
                    json.dumps(syms),
                    scrub_text(args.preconditions),
                    scrub_text(args.postconditions),
                    guarded_by,
                    guard_assumption,
                    json.dumps(prov_tags),
                    json.dumps(req_tags),
                    mp_diff,
                    snap_id,
                    scrub_text(args.evidence_cmd),
                    scrub_text(args.evidence_output or ""),
                    utc_now_iso(),
                ),
            )
            hooks = on_primitive_added(
                conn,
                primitive_id=pid,
                subsystem=sub,
                locus=args.locus,
                kind=args.kind,
                guarded_by_locus=guarded_by,
                provides_tags=prov_tags,
                requires_tags=req_tags,
                role=role,
                trusted_invariant=trusted_inv,
                symbols=syms,
                snapshot_id=snap_id,
                postconditions=args.postconditions,
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
                "worker",
                "primitive_added",
                pid,
                {
                    "locus": args.locus,
                    "kind": args.kind,
                    "role": role,
                    "guarded_by_locus": guarded_by,
                    "provides_tags": prov_tags,
                    "requires_tags": req_tags,
                    "woken_doors": woken_doors,
                },
            )
            _emit(
                {
                    "primitive_id": pid,
                    "role": role,
                    "subsystem": sub,
                    "guarded_by_locus": guarded_by,
                    "provides_tags": prov_tags,
                    "requires_tags": req_tags,
                    "symbols": syms,
                    "woken_doors": woken_doors,
                    "hooks_triggered": [h["hook_code"] for h in hooks],
                },
                True,
            )
            return EXIT_OK

        if args.primitive_cmd == "dry":
            run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
            tpath = pathlib.Path(run["target_path"]) if run else pathlib.Path(".")
            tmode = str(run["target_mode"]) if run else "source"
            res = mark_primitive_dry(
                conn,
                target_dir=tpath,
                target_mode=tmode,
                primitive_id=args.primitive_id,
                worker_id=args.worker,
                locus=args.locus,
                reason=args.reason,
            )
            _emit(res, True)
            return EXIT_OK

        if args.primitive_cmd == "promote-helper":
            run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
            tpath = pathlib.Path(run["target_path"])
            res = promote_primitive_helper(
                conn,
                run_dir=rdir,
                target_dir=tpath,
                primitive_id=args.primitive_id,
                helper_file=pathlib.Path(args.file),
                callable_name=args.callable,
                provides_tags=args.provides_tags,
                requires_tags=args.requires_tags,
                self_test_cmd=args.self_test_cmd or "",
                timeout_sec=args.timeout,
                worker_id=args.worker,
            )
            _emit(res, True)
            return EXIT_OK

        if args.primitive_cmd == "helpers":
            rows = list_rows(conn, "SELECT * FROM primitive_helpers ORDER BY created_at ASC")
            _emit({"primitive_helpers": rows}, True)
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
            assert_run_mutable(conn, operation="claim_propose")
            if len(args.falsification_prediction.strip()) < 10 or len(args.falsification_test.strip()) < 5:
                raise AjarError(
                    "DEC-0128 gate: --falsification-prediction and --falsification-test are required before proposing a claim.",
                    EXIT_GATE_BLOCKED,
                )
            ok_prose, prose_msg = validate_structural_claim_prose(
                args.title, args.mechanism, args.falsification_prediction
            )
            if not ok_prose:
                raise AjarError(prose_msg, EXIT_GATE_BLOCKED)
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
            hooks = on_anomaly_or_claim_recorded(
                conn,
                entity_id=cid,
                trigger_cmd="claim.propose",
                subsystem=sub,
                locus=args.locus,
                text_blob=f"{args.title} {args.mechanism}",
                target_dir=tpath if tmode == "source" else None,
            )
            log_event(conn, args.worker, "claim_proposed", cid, {"locus": args.locus, "severity": args.severity})
            _emit(
                {
                    "claim_id": cid,
                    "status": "proposed",
                    "subsystem": sub,
                    "hooks_triggered": [h["hook_code"] for h in hooks],
                },
                True,
            )
            return EXIT_OK

        if args.claim_cmd == "rescope":
            ok_prose, prose_msg = validate_structural_claim_prose(
                args.title, args.mechanism, args.falsification_prediction
            )
            if not ok_prose:
                raise AjarError(prose_msg, EXIT_GATE_BLOCKED)
            res = rescope_claim(
                conn,
                claim_id=args.claim_id,
                worker_id=args.worker,
                reason=args.reason,
                title=args.title,
                locus=args.locus,
                mechanism=args.mechanism,
                severity=args.severity,
                falsification_prediction=args.falsification_prediction,
                falsification_test=args.falsification_test,
            )
            _emit(res, True)
            return EXIT_OK

        if args.claim_cmd == "falsify":
            assert_run_mutable(conn, operation="claim_falsify")
            clm = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (args.claim_id,)).fetchone()
            if clm is None:
                raise AjarError(f"Unknown claim_id: {args.claim_id}", EXIT_USER_ERROR)
            if clm["proposer_worker_id"] == args.worker:
                raise AjarError(
                    f"Fresh-falsifier separation gate: proposer {args.worker!r} cannot falsify its own claim. "
                    "Use an independent falsifier worker.",
                    EXIT_GATE_BLOCKED,
                )
            now_iso = utc_now_iso()
            cfg_gate = (getattr(args, "config_gate", None) or "").strip()
            if cfg_gate:
                assert_valid_claim_transition(str(clm["status"]), "config_gated", claim_id=args.claim_id)
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
                            args.worker,
                            scrub_text(args.notes),
                            args.control_locus,
                            axes.research_state.value,
                            axes.evidence_state.value,
                            now_iso,
                            args.claim_id,
                        ),
                    )
                    probe = on_claim_config_gated(conn, claim_row=clm, config_predicate=cfg_gate)
                    log_event(
                        conn,
                        args.worker,
                        "claim_config_gated",
                        args.claim_id,
                        {"config_gate": cfg_gate, "probe_task_id": probe["probe_task_id"]},
                    )
                _emit(
                    {
                        "claim_id": args.claim_id,
                        "status": "config_gated",
                        "config_gate": cfg_gate,
                        "probe_task_id": probe["probe_task_id"],
                    },
                    True,
                )
                return EXIT_OK

            assert_valid_claim_transition(str(clm["status"]), "falsified", claim_id=args.claim_id)
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
                        args.worker,
                        scrub_text(args.notes),
                        args.control_locus,
                        axes.research_state.value,
                        axes.evidence_state.value,
                        now_iso,
                        args.claim_id,
                    ),
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
                consume_hooks_for_locus(conn, source_entity_id=args.claim_id)
                log_event(conn, args.worker, "claim_falsified", args.claim_id, {})
            _emit({"claim_id": args.claim_id, "status": "falsified"}, True)
            return EXIT_OK

        if args.claim_cmd == "survive":
            assert_run_mutable(conn, operation="claim_survive")
            clm = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (args.claim_id,)).fetchone()
            if clm is None:
                raise AjarError(f"Unknown claim_id: {args.claim_id}", EXIT_USER_ERROR)
            if clm["proposer_worker_id"] == args.worker:
                raise AjarError(
                    f"Fresh-falsifier separation gate: proposer {args.worker!r} cannot validate its own claim. "
                    "Use an independent falsifier worker.",
                    EXIT_GATE_BLOCKED,
                )
            assert_valid_claim_transition(str(clm["status"]), "survived_falsify", claim_id=args.claim_id)
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
                        args.worker,
                        scrub_text(args.notes),
                        axes.research_state.value,
                        axes.evidence_state.value,
                        now_iso,
                        args.claim_id,
                    ),
                )
                updated_clm = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (args.claim_id,)).fetchone()
                hooks = on_claim_survived(conn, claim_row=updated_clm)
                log_event(conn, args.worker, "claim_survived_falsify", args.claim_id, {})
            _emit(
                {
                    "claim_id": args.claim_id,
                    "status": "survived_falsify",
                    "hooks_triggered": [h["hook_code"] for h in hooks],
                },
                True,
            )
            return EXIT_OK

        if args.claim_cmd == "instrument":
            assert_run_mutable(conn, operation="claim_instrument")
            if tmode != "source":
                raise AjarError("`ajar claim instrument` requires source mode.", EXIT_USER_ERROR)
            probe_p = pathlib.Path(args.probe_patch) if args.probe_patch else None
            res = run_claim_instrumentation(
                conn,
                run_dir=rdir,
                target_dir=tpath,
                claim_id=args.claim_id,
                probe_cmd=args.probe_cmd,
                probe_patch=probe_p,
                timeout_sec=args.timeout,
                worker_id=args.worker,
            )
            _emit(res, True)
            return EXIT_OK

        if args.claim_cmd == "block":
            assert_run_mutable(conn, operation="claim_block")
            clm = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (args.claim_id,)).fetchone()
            if clm is None:
                raise AjarError(f"Unknown claim_id: {args.claim_id}", EXIT_USER_ERROR)
            assert_valid_claim_transition(str(clm["status"]), "blocked", claim_id=args.claim_id)
            env_b = (getattr(args, "env_blocker", None) or "").strip()
            ok_blk, blk_msg = validate_claim_block_request(
                clm,
                reason=args.reason,
                env_blocker=env_b,
                target_mode=tmode,
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
                        scrub_text(args.reason),
                        env_b,
                        axes.research_state.value,
                        axes.evidence_state.value,
                        now_iso,
                        args.claim_id,
                    ),
                )
                log_event(
                    conn,
                    args.worker,
                    "claim_blocked",
                    args.claim_id,
                    {"env_blocker": env_b, "reason": args.reason},
                )
            _emit({"claim_id": args.claim_id, "status": "blocked", "env_blocker": env_b}, True)
            return EXIT_OK

        if args.claim_cmd == "reproduce":
            clm = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (args.claim_id,)).fetchone()
            if clm is None:
                raise AjarError(f"Unknown claim_id: {args.claim_id}", EXIT_USER_ERROR)
            if clm["status"] == "needs_instrumentation" and int(clm["instrumented_since_fail"] or 0) == 0:
                raise AjarError(
                    f"Telemetry-pivot gate (`KVMEscape` rule): claim {args.claim_id} failed 2 PoC runs with unchanged observation. "
                    "Run `ajar claim instrument` or record a target trace (`ajar anomaly add --claim` / `ajar binding set`) before retrying.",
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
            decl_steps = getattr(args, "declared_steps", None)
            prov_tags = parse_tag_list(getattr(args, "provides_tags", None))

            # Pre-flight realism check (blocks self-override CLI/env flags in `< 1 ms` with zero strike burn).
            evaluate_precondition_realism(
                conn,
                poc_cmd=args.poc_cmd,
                control_cmd=args.control_cmd,
                severity=str(clm["severity"]),
                config_gate=str(clm["config_gate"] if "config_gate" in clm.keys() else ""),
                declared_steps=decl_steps,
                target_locus=str(clm["locus"]),
            )

            if eff_mode == "source":
                if not args.micropatch:
                    raise AjarError("Source reproduction requires --micropatch <patch_file>.", EXIT_USER_ERROR)
                rel_cmd = (getattr(args, "release_cmd", None) or "").strip()
                rel_ctrl_cmd = (getattr(args, "release_control_cmd", None) or "").strip()
                surf_kind = ""
                if clm["surface_id"]:
                    srow = conn.execute(
                        "SELECT kind FROM surfaces WHERE surface_id = ?",
                        (clm["surface_id"],),
                    ).fetchone()
                    if srow is not None:
                        surf_kind = str(srow["kind"] or "")
                h6_active = conn.execute(
                    """
                    SELECT hook_id FROM epistemic_hooks
                    WHERE hook_code = 'H6_RELEASE_UB_DIFF' AND source_entity_id = ? AND status = 'active'
                    LIMIT 1
                    """,
                    (args.claim_id,),
                ).fetchone()
                if (
                    h6_active is not None
                    and claim_requires_release_ub_diff(str(clm["locus"]), f"{clm['title']} {clm['mechanism']}")
                    and not rel_cmd
                ):
                    raise AjarError(
                        f"H6_RELEASE_UB_DIFF gate: compiled UB/overflow claim {args.claim_id} requires --release-cmd "
                        "(`-O2` / `--release` without debug asserts or `-ftrapv`) to classify production impact.",
                        EXIT_GATE_BLOCKED,
                    )
                siblings = [
                    {"claim_id": r["claim_id"], "poc_cmd": args.sibling_poc_cmd or ""}
                    for r in conn.execute(
                        """
                        SELECT claim_id FROM claims
                        WHERE status = 'survived_falsify' AND claim_id != ?
                          AND (locus = ? OR mechanism_key = ?)
                        """,
                        (args.claim_id, str(clm["locus"]), str(clm["mechanism_key"])),
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
                    claim_locus=str(clm["locus"]),
                    shared_guard_locus=str(getattr(args, "shared_guard_locus", None) or ""),
                    release_cmd=rel_cmd,
                    release_control_cmd=rel_ctrl_cmd,
                    surface_kind=surf_kind,
                    build_cmd=str(getattr(args, "build_cmd", None) or ""),
                    save_post_state=getattr(args, "save_post_state", None),
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
                err_cls = str(res.get("error_class") or "target_negative")
                if str(clm["status"]) == "reproduced":
                    log_event(
                        conn,
                        args.worker,
                        "claim_repro_rerun_failed_preserved",
                        args.claim_id,
                        {"error_class": err_cls, "reason": str(res.get("reason", ""))[:200]},
                    )
                    pivot = {
                        "claim_id": args.claim_id,
                        "status": "reproduced",
                        "error_class": err_cls,
                        "strike_recorded": False,
                        "failed_repro_count": int(clm["failed_repro_count"] or 0),
                        "pivoted_to_instrumentation": False,
                    }
                elif err_cls == "target_negative":
                    pivot = record_repro_failure(
                        conn,
                        claim=clm,
                        worker_id=args.worker,
                        observation_hash=str(res.get("observation_hash", "")),
                        reason=str(res.get("reason", "")),
                    )
                else:
                    log_event(
                        conn,
                        args.worker,
                        "claim_repro_non_strike_error",
                        args.claim_id,
                        {"error_class": err_cls, "reason": str(res.get("reason", ""))[:200]},
                    )
                    pivot = {
                        "claim_id": args.claim_id,
                        "status": str(clm["status"]),
                        "error_class": err_cls,
                        "strike_recorded": False,
                        "failed_repro_count": int(clm["failed_repro_count"] or 0),
                        "pivoted_to_instrumentation": False,
                    }
                _emit({"reproduction": res, "claim_update": pivot}, True)
                return EXIT_GATE_BLOCKED

            ub_div = str(res.get("ub_divergence_class") or "")
            if ub_div == "debug_assert_only" and str(clm["severity"]) in ("critical", "high"):
                raise AjarError(
                    f"Release-profile UB differential classified {args.claim_id} as debug_assert_only "
                    f"(clean --release-cmd exited 0 without post-state violation); rescope severity to low/medium "
                    "via `ajar claim rescope` before confirming.",
                    EXIT_GATE_BLOCKED,
                )

            # Persist optional Arm-1 post-state snapshot (`repro_snapshots`).
            snap_meta = res.get("post_state_snapshot")
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
                        args.claim_id,
                        str(snap_meta["rel_dir"]),
                        str(snap_meta["archive_path"]),
                        str(snap_meta["sha256"]),
                        int(snap_meta["size_bytes"]),
                        json.dumps(snap_meta.get("manifest") or {}, sort_keys=True),
                        str(snap_meta.get("source_cmd") or ""),
                        str(snap_meta.get("created_at") or utc_now_iso()),
                    ),
                )

            arm1_obj = res.get("arm1_clean_poc") or {}
            realism = evaluate_precondition_realism(
                conn,
                poc_cmd=args.poc_cmd,
                control_cmd=args.control_cmd,
                stdout=str(arm1_obj.get("stdout", "")),
                stderr=str(arm1_obj.get("stderr", "")),
                severity=str(clm["severity"]),
                config_gate=str(clm["config_gate"] if "config_gate" in clm.keys() else ""),
                declared_steps=decl_steps,
                target_locus=str(clm["locus"]),
            )

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
                UPDATE tasks
                SET status = 'done', worker_id = ?, lease_expires_at = NULL, updated_at = ?
                WHERE parent_claim_id = ? AND kind = 'reproduce' AND status IN ('open', 'leased')
                """,
                (args.worker, now_iso, args.claim_id),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO findings(
                    finding_id, claim_id, title, severity, locus, root_cause, poc_cmd, control_cmd,
                    micropatch_path, micropatch_diff, arm1_clean_poc_json, arm2_clean_ctrl_json,
                    arm3_patch_poc_json, arm4_patch_ctrl_json, oracle_json,
                    arm5a_release_poc_json, arm5b_release_ctrl_json, ub_divergence_class,
                    provides_tags_json, snapshot_id, realism_tier, realism_json,
                    attribution, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    json.dumps(oracle_dict or {}, sort_keys=True),
                    json.dumps(res.get("arm5a_release_poc") or {}, sort_keys=True),
                    json.dumps(res.get("arm5b_release_control") or {}, sort_keys=True),
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
                args.worker,
                "finding_reproduced",
                fid,
                {
                    "claim_id": args.claim_id,
                    "attribution": attr,
                    "realism_tier": realism["realism_tier"],
                    "snapshot_id": snap_id,
                    "ub_divergence_class": ub_div,
                },
            )
            conn.commit()
            sync_run_to_shared_mirror(rid)
            out_payload: dict[str, Any] = {
                "finding_id": fid,
                "attribution": attr,
                "realism_tier": realism["realism_tier"],
                "snapshot_id": snap_id,
                "reproduction": res,
            }
            if esc is not None:
                out_payload["post_confirm_escalation"] = esc
            _emit(out_payload, True)
            return EXIT_OK

        rows = list_rows(conn, "SELECT * FROM claims ORDER BY created_at ASC")
        _emit({"claims": rows}, True)
        return EXIT_OK
    finally:
        conn.close()


def cmd_chain(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    rdir = run_dir_for(rid)
    conn = open_run_db(rid)
    try:
        if args.chain_cmd == "frontier":
            _emit(compute_chain_frontier(conn), True)
            return EXIT_OK

        if args.chain_cmd == "probe":
            run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
            tpath = pathlib.Path(run["target_path"])
            oracle_dict = json.loads(args.oracle_json) if getattr(args, "oracle_json", None) else None
            patch_p = pathlib.Path(args.patch) if getattr(args, "patch", None) else None
            res = run_snapshot_chain_probe(
                conn,
                run_dir=rdir,
                target_dir=tpath,
                snapshot_id=args.from_snapshot,
                cmd=args.cmd,
                patch_path=patch_p,
                oracle=oracle_dict,
                timeout_sec=int(getattr(args, "timeout", 60)),
                worker_id=str(getattr(args, "worker", "worker")),
            )
            _emit(res, True)
            return EXIT_OK

        if args.chain_cmd == "propose":
            run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
            tmode = str(run["target_mode"]) if run else "source"
            steps = [s.strip() for s in args.steps.split(",") if s.strip()]
            oracle_dict = json.loads(args.oracle_json) if getattr(args, "oracle_json", None) else None

            if run is not None and tmode == "source":
                patch_map = _parse_step_micropatches(getattr(args, "step_micropatch", None))
                res = run_chain_reproduction(
                    conn,
                    run_dir=rdir,
                    target_dir=pathlib.Path(run["target_path"]),
                    title=args.title,
                    steps=steps,
                    poc_cmd=args.poc_cmd,
                    control_cmd=args.control_cmd,
                    severity=args.severity,
                    oracle=oracle_dict,
                    step_micropatches=patch_map,
                    ablate_steps=not bool(getattr(args, "no_ablate", False)),
                    door_id=str(getattr(args, "door", None) or ""),
                    jewel_id=str(getattr(args, "jewel", None) or ""),
                    declared_steps=getattr(args, "declared_steps", None),
                    timeout_sec=int(getattr(args, "timeout", 60)),
                    worker_id=str(getattr(args, "worker", "worker")),
                )
                _emit(res, True)
                return EXIT_OK if res["verified"] else EXIT_GATE_BLOCKED

            cwd = run["workspace_path"] if run else "."
            env = scrubbed_subprocess_env()
            p1 = subprocess.run(["bash", "-c", args.poc_cmd], cwd=cwd, env=env, capture_output=True, timeout=60, check=False)
            p2 = subprocess.run(["bash", "-c", args.control_cmd], cwd=cwd, env=env, capture_output=True, timeout=60, check=False)
            verified = p1.returncode != 0 and p2.returncode == 0
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
                    conn.execute("UPDATE primitives SET chained = 1, status = 'chained' WHERE primitive_id = ?", (sid,))
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


def cmd_epistemic_hooks(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    conn = open_run_db(rid)
    try:
        if args.status:
            rows = list_rows(
                conn,
                "SELECT * FROM epistemic_hooks WHERE status = ? ORDER BY created_at ASC",
                (args.status,),
            )
        else:
            rows = list_rows(conn, "SELECT * FROM epistemic_hooks ORDER BY created_at ASC")
        _emit({"epistemic_hooks": rows}, True)
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
            surf = (getattr(args, "surface", None) or "").strip()
            conn.execute(
                """
                INSERT INTO spend_ledger(entry_id, worker_id, surface_id, phase, model, tokens_in, tokens_out, cost_usd, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    eid,
                    args.worker,
                    surf,
                    args.phase,
                    args.model or "",
                    int(args.tokens_in),
                    int(args.tokens_out),
                    float(args.cost_usd),
                    scrub_text(args.notes or ""),
                    utc_now_iso(),
                ),
            )
            _emit({"entry_id": eid, "surface_id": surf, "cost_usd": float(args.cost_usd)}, True)
            return EXIT_OK
        rows = list_rows(conn, "SELECT * FROM spend_ledger ORDER BY created_at ASC")
        _emit({"spend_entries": rows}, True)
        return EXIT_OK
    finally:
        conn.close()


def cmd_steer(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    conn = open_run_db(rid)
    try:
        if args.steer_cmd == "add":
            res = add_steer(
                conn,
                rule_text=args.rule,
                scope=args.scope,
                target_filter=args.filter or "",
                author=args.author,
                touch_kind=args.kind,
            )
            _emit(res, True)
            return EXIT_OK
        if args.steer_cmd == "revoke":
            res = revoke_steer(
                conn,
                steer_id=args.steer_id,
                reason=args.reason,
                actor=args.actor,
            )
            _emit(res, True)
            return EXIT_OK
        rows = list_steers(conn, active_only=not bool(args.all))
        _emit({"steers": rows}, True)
        return EXIT_OK
    finally:
        conn.close()


def cmd_patch(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    rdir = run_dir_for(rid)
    conn = open_run_db(rid)
    try:
        if args.patch_cmd == "verify":
            run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
            tpath = pathlib.Path(run["target_path"])
            oracle_dict = json.loads(args.oracle_json) if args.oracle_json else None
            res = run_8arm_patch_verification(
                conn,
                run_dir=rdir,
                target_dir=tpath,
                finding_id=args.finding_id,
                patch_path=pathlib.Path(args.patch),
                suite_cmd=args.suite_cmd,
                variant_cmds=args.variant_cmd or [],
                caller_audit=args.caller_audit,
                sibling_audit=args.sibling_audit,
                caller_cmd=args.caller_cmd or "",
                sibling_cmd=args.sibling_cmd or "",
                oracle=oracle_dict,
                shared_guard_locus=args.shared_guard_locus or "",
                max_changed_lines=args.max_changed_lines,
                timeout_sec=args.timeout,
                suite_timeout_sec=int(getattr(args, "suite_timeout", 1800)),
                build_cmd=str(getattr(args, "build_cmd", None) or ""),
                worker_id=args.worker,
            )
            _emit(res, True)
            return EXIT_OK if res["passed"] else EXIT_GATE_BLOCKED

        rows = list_rows(conn, "SELECT * FROM patch_verifications ORDER BY created_at ASC")
        _emit({"patch_verifications": rows}, True)
        return EXIT_OK
    finally:
        conn.close()


def cmd_phase(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    conn = open_run_db(rid)
    try:
        run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
        if run is None:
            raise AjarError("Run metadata missing in run.db.", EXIT_USER_ERROR)
        prev_phase = str(run["campaign_phase"] if "campaign_phase" in run.keys() else "hunt") or "hunt"
        if args.phase_cmd == "show":
            _emit({"run_id": rid, "campaign_phase": prev_phase}, True)
            return EXIT_OK

        new_phase = str(args.to).strip()
        if new_phase not in ("hunt", "remediate", "full"):
            raise AjarError(f"Unsupported phase {new_phase!r}; choose hunt, remediate, or full.", EXIT_USER_ERROR)
        assert_run_mutable(conn, operation="phase_advance")
        assert_valid_phase_transition(prev_phase, new_phase, run_id=rid)
        with immediate_tx(conn):
            conn.execute("UPDATE runs SET campaign_phase = ? WHERE run_id = ?", (new_phase, rid))
            recompute_all_open_salience(conn)
            log_event(
                conn,
                "operator",
                "campaign_phase_advanced",
                rid,
                {"previous_phase": prev_phase, "campaign_phase": new_phase, "notes": scrub_text(args.notes or "")},
            )
        _emit({"run_id": rid, "previous_phase": prev_phase, "campaign_phase": new_phase}, True)
        return EXIT_OK
    finally:
        conn.close()


def cmd_door(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    conn = open_run_db(rid)
    try:
        if args.door_cmd == "jewel-add":
            res = add_crown_jewel(
                conn,
                name=args.name,
                locus=args.locus,
                subsystem=args.subsystem or "",
                impact_class=args.impact_class,
                symbols=args.symbols,
                max_interaction_steps=int(args.max_steps),
                require_default_config=not bool(args.allow_nondefault_config),
                forbid_visible_error=not bool(args.allow_visible_error),
                worker_id=args.worker,
            )
            _emit(res, True)
            return EXIT_OK

        if args.door_cmd == "jewel-list":
            _emit({"crown_jewels": list_crown_jewels(conn)}, True)
            return EXIT_OK

        if args.door_cmd == "park":
            res = park_open_door(
                conn,
                anchor_locus=args.anchor_locus,
                missing_link_summary=args.missing,
                wishlist_query=args.wishlist or "",
                jewel_id=args.jewel or "",
                direction=args.direction,
                blocker_locus=args.blocker_locus or "",
                subsystem=args.subsystem or "",
                held_ids=args.held_ids,
                snapshot_id=args.snapshot or "",
                wanted_tags=args.wanted_tags,
                wanted_symbols=args.wanted_symbols,
                max_bridge_attempts=int(args.max_bridge_attempts),
                spawn_hunters=not bool(args.no_spawn_hunters),
                worker_id=args.worker,
            )
            _emit(res, True)
            return EXIT_OK

        if getattr(args, "status", None):
            rows = list_rows(
                conn,
                "SELECT * FROM parked_doors WHERE status = ? ORDER BY updated_at DESC",
                (args.status,),
            )
        else:
            rows = list_rows(conn, "SELECT * FROM parked_doors ORDER BY updated_at DESC")
        _emit({"open_doors": rows}, True)
        return EXIT_OK
    finally:
        conn.close()


def cmd_repro(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    rdir = run_dir_for(rid)
    conn = open_run_db(rid)
    try:
        if args.repro_cmd == "try":
            run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
            tpath = pathlib.Path(run["target_path"])
            oracle_dict = json.loads(args.oracle_json) if getattr(args, "oracle_json", None) else None
            patch_p = pathlib.Path(args.patch) if getattr(args, "patch", None) else None
            res = run_repro_try(
                run_dir=rdir,
                target_dir=tpath,
                cmd=args.cmd,
                patch_path=patch_p,
                build_cmd=args.build_cmd or "",
                oracle=oracle_dict,
                timeout_sec=int(args.timeout),
            )
            _emit(res, True)
            return EXIT_OK

        rows = list_rows(conn, "SELECT * FROM repro_snapshots ORDER BY created_at DESC")
        _emit({"snapshots": rows}, True)
        return EXIT_OK
    finally:
        conn.close()


def cmd_finding(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    conn = open_run_db(rid)
    try:
        if args.finding_cmd == "calibrate":
            res = calibrate_finding(
                conn,
                finding_id=args.finding_id,
                reason=args.reason,
                severity=args.severity,
                title=args.title,
                worker_id=args.worker,
            )
            _emit(res, True)
            return EXIT_OK

        rows = list_rows(
            conn,
            """
            SELECT f.*, c.remediation_state
            FROM findings f
            JOIN claims c ON f.claim_id = c.claim_id
            ORDER BY f.created_at ASC
            """,
        )
        _emit({"findings": rows}, True)
        return EXIT_OK
    finally:
        conn.close()


def cmd_export_graph(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    conn = open_run_db(rid)
    try:
        graph = export_attack_flow_graph(conn)
    finally:
        conn.close()

    out_str = json.dumps(graph, indent=2, sort_keys=True)
    if args.output:
        out_p = pathlib.Path(args.output)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(out_str + "\n", encoding="utf-8")
    else:
        print(out_str)
    return EXIT_OK


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
    mirror_info = sync_run_to_shared_mirror(rid)
    if mirror_info is not None:
        res["shared_mirror_dir"] = mirror_info["mirror_dir"]
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
        campaign_phase=getattr(args, "phase", "hunt") or "hunt",
        budget_usd=args.budget,
        workers=args.workers,
        discover_passes=args.discover_passes,
        worker_cmd=args.worker_cmd,
        max_steps=args.max_steps,
    )
    _emit(res, True)
    return EXIT_OK if res["gates_passed"] else EXIT_GATE_BLOCKED


def cmd_swarm(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    conn = open_run_db(rid)
    try:
        if args.swarm_cmd == "packet":
            raw_items = [s.strip() for s in (args.items or "").split(",") if s.strip()]
            res = build_swarm_packet(
                conn,
                stage=args.stage,
                wire_profile=args.wire_profile,
                item_ids=raw_items,
                limit=args.limit,
                worker_id=args.worker or "",
            )
            if args.json:
                _emit(res, True)
            else:
                print(res["packet_markdown"], end="")
            return EXIT_OK

        if args.swarm_cmd == "fallback":
            res = escalate_swarm_fallback(
                conn,
                target=args.target,
                reason=args.reason,
                notes=args.notes or "",
            )
            _emit(res, True)
            return EXIT_OK

        if args.swarm_cmd == "complete":
            res = complete_swarm_dispatch(
                conn,
                target=args.target,
                notes=args.notes or "",
            )
            _emit(res, True)
            return EXIT_OK

        rows = list_rows(conn, "SELECT * FROM swarm_dispatches ORDER BY created_at ASC")
        _emit({"swarm_dispatches": rows}, True)
        return EXIT_OK
    finally:
        conn.close()


def cmd_reopen(args: argparse.Namespace) -> int:
    res = reopen_run(
        args.run_id,
        unblock_zero_attempt_claims=not bool(args.keep_blocked),
        shared_root=args.from_shared,
    )
    _emit(res, True)
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ajar",
        description="Ajar: verification-backed security engine for Code, Fixes, Security reviews, and Supply chain.",
    )
    p.add_argument("--version", action="version", version=f"ajar {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    # doctor
    p_doc = sub.add_parser("doctor", help="Check local toolchains, sandbox, disk headroom, and optional target liveness.")
    p_doc.add_argument("--target", help="Optional local path, `owner/repo` slug, or git URL to verify freshness and scope readiness.")
    p_doc.add_argument("--subdir", default="", help="Optional in-scope subdirectory inside `--target` monorepo.")
    p_doc.add_argument("--ref", default="", help="Optional remote branch, tag, or commit SHA to verify instead of default_branch.")
    p_doc.add_argument("--peer", action="append", help="Optional sibling reference/contract checkout path to verify.")
    p_doc.add_argument("--max-age-days", type=int, default=90, help="Maximum allowed git HEAD age in days (default: 90).")
    p_doc.add_argument("--no-remote", action="store_true", help="Skip live remote `gh api` / `git ls-remote` upstream checks.")
    p_doc.add_argument("--json", action="store_true", default=True)
    p_doc.set_defaults(func=cmd_doctor)

    # quote
    p_qt = sub.add_parser("quote", help="Preview deterministic Code LOC quote and 35%% COGS cap before running.")
    p_qt.add_argument("target", help="Target repository directory or file path.")
    p_qt.add_argument("--diff", help="Optional git diff range (`base..head`) for PR/commit differential quoting.")
    p_qt.add_argument("--json", action="store_true", default=True)
    p_qt.set_defaults(func=cmd_quote)

    stopping_choices = ("exhaustive-high", "first-verified-high", "crown-jewel")
    phase_choices = ("hunt", "remediate", "full")

    # init
    p_init = sub.add_parser("init", help="Initialize a new verification run in --envelope or --in-place mode.")
    p_init.add_argument("target", help="Target directory, binary path, or URL.")
    p_init.add_argument("--mode", choices=("source", "binary", "live"), default="source")
    grp_ws = p_init.add_mutually_exclusive_group()
    grp_ws.add_argument("--envelope", action="store_true", default=True, help="Create isolated workspace with read-only target snapshot (default).")
    grp_ws.add_argument("--in-place", action="store_true", help="Write zero files into target directory.")
    p_init.add_argument("--goal", default="Identify, falsify, and reproduce high-severity software vulnerabilities.")
    p_init.add_argument("--brief-file", help="Optional Markdown campaign brief persisted for the Lead Orchestrator (`brief.md`, omitted from worker contexts).")
    p_init.add_argument("--until", choices=stopping_choices, default="exhaustive-high")
    p_init.add_argument("--stopping", dest="until", choices=stopping_choices, help="Alias for --until (`exhaustive-high`, `first-verified-high`, `crown-jewel`).")
    p_init.add_argument("--phase", choices=phase_choices, default="hunt", help="Campaign phase (`hunt` defers 9-arm `patch verify` until `remediate`).")
    p_init.add_argument("--budget", type=float, default=None, help="Explicit COGS cap override in USD (defaults to 0.35 * Code quote).")
    p_init.add_argument("--cogs-cap", dest="budget", type=float, help="Alias for --budget explicit COGS cap override in USD.")
    p_init.add_argument("--uncapped", action="store_true", help="Disable finite COGS budget caps and 25%%/80%% budget throttles (`uncapped_research`).")
    p_init.add_argument("--diff", help="Optional git diff range (`base..head`) for PR differential Code runs.")
    p_init.add_argument("--parent-run", help="Optional baseline/parent run ID to carry forward kept findings and guards.")
    p_init.add_argument("--allow-host", action="append", help="Allowed live target hostname.")
    p_init.add_argument("--allow-live-requests", action="store_true")
    p_init.add_argument("--allow-live-mutations", action="store_true")
    p_init.add_argument("--allow-historical-target", action="store_true", help="Allow initializing on archived or >90-day-old historical snapshots.")
    p_init.add_argument("--run-id", help="Optional explicit run identifier.")
    p_init.add_argument("--json", action="store_true")
    p_init.set_defaults(func=cmd_init)

    # phase
    p_phs = sub.add_parser("phase", help="Inspect or advance campaign phase (`hunt` -> `remediate` -> `full`).")
    phs_sub = p_phs.add_subparsers(dest="phase_cmd", required=True)
    pph_s = phs_sub.add_parser("show")
    pph_s.add_argument("--run")
    pph_a = phs_sub.add_parser("advance")
    pph_a.add_argument("--to", choices=phase_choices, required=True)
    pph_a.add_argument("--notes", default="")
    pph_a.add_argument("--run")
    p_phs.set_defaults(func=cmd_phase)

    # brief
    p_brf = sub.add_parser("brief", help="Read or update the Lead Orchestrator campaign brief (`brief.md`) without bloating worker task prefixes.")
    p_brf.add_argument("--set-file", help="Path to Markdown campaign brief file to store in the run directory.")
    p_brf.add_argument("--run", help="Run ID.")
    p_brf.add_argument("--json", action="store_true")
    p_brf.set_defaults(func=cmd_brief)

    # status
    p_stat = sub.add_parser("status", help="Inspect current run progress, gates, and spend.")
    p_stat.add_argument("--run", help="Run ID.")
    p_stat.add_argument("--json", action="store_true", default=True)
    p_stat.set_defaults(func=cmd_status)

    # context
    p_ctx = sub.add_parser("context", help="Render prefix-stable < 4 KB certified context frame for a task.")
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
    p_map.add_argument("--slice-cap", type=int, default=15000, help="Soft target LoC per cohesive subsystem call cone.")
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

    # threat-model
    p_tm = sub.add_parser("threat-model", help="Synthesize initial Threat Model and track adaptive trust assumptions.")
    tm_sub = p_tm.add_subparsers(dest="tm_cmd", required=True)
    ptm_set = tm_sub.add_parser("set", help="Set or revise attacker principals, crown-jewel assets, and consumer tiers.")
    ptm_set.add_argument("--principals", required=True, help="Comma-separated untrusted/semi-trusted attacker principals.")
    ptm_set.add_argument("--assets", required=True, help="Comma-separated protected assets or impact classes.")
    ptm_set.add_argument("--consumer-tiers", default="", help="Comma-separated downstream caller tiers (`CLI,Gitaly,guest-VM`).")
    ptm_set.add_argument("--summary", default="", help="Concise architectural threat-model summary.")
    ptm_set.add_argument("--json", action="store_true")
    ptm_set.add_argument("--run")
    ptm_show = tm_sub.add_parser("show", help="Inspect current Threat Model revision and trust assumptions.")
    ptm_show.add_argument("--json", action="store_true")
    ptm_show.add_argument("--run")
    ptm_add = tm_sub.add_parser("assumption-add", help="Register a falsifiable architectural trust assumption.")
    ptm_add.add_argument("--subsystem", default="")
    ptm_add.add_argument("--trust-boundary", default="")
    ptm_add.add_argument("--assumption", required=True)
    ptm_add.add_argument("--check-locus", default="")
    ptm_add.add_argument("--invalidated-by-tags", default="", help="Comma-separated capability tags (`ns:name`) that auto-violate this assumption.")
    ptm_add.add_argument("--dependent-surface", default="", help="Surface ID whose priority escalates if this assumption breaks.")
    ptm_add.add_argument("--escalate-priority", choices=("critical", "high"), default="critical")
    ptm_add.add_argument("--json", action="store_true")
    ptm_add.add_argument("--run")
    ptm_lst = tm_sub.add_parser("assumption-list")
    ptm_lst.add_argument("--json", action="store_true")
    ptm_lst.add_argument("--run")
    ptm_ver = tm_sub.add_parser("verify", help="Mark an assumption verified in code (`verified_holds`).")
    ptm_ver.add_argument("assumption_id")
    ptm_ver.add_argument("--locus", required=True)
    ptm_ver.add_argument("--notes", default="")
    ptm_ver.add_argument("--json", action="store_true")
    ptm_ver.add_argument("--run")
    ptm_inv = tm_sub.add_parser("invalidate", help="Violate a broken assumption and adaptively re-score surfaces/tasks.")
    ptm_inv.add_argument("assumption_id")
    ptm_inv.add_argument("--evidence", required=True, help="Primitive ID, Finding ID, or file:line proving the assumption failed.")
    ptm_inv.add_argument("--notes", default="")
    ptm_inv.add_argument("--json", action="store_true")
    ptm_inv.add_argument("--run")
    p_tm.set_defaults(func=cmd_threat_model)

    # door (`Crown Jewels` + suspended `Open Doors`)
    p_dr = sub.add_parser("door", help="Manage Crown-Jewel terminal sinks and suspended Open-Door chain subgoals.")
    dr_sub = p_dr.add_subparsers(dest="door_cmd", required=True)
    pdr_ja = dr_sub.add_parser("jewel-add", help="Register a target-derived Crown-Jewel terminal sink.")
    pdr_ja.add_argument("--name", required=True)
    pdr_ja.add_argument("--locus", required=True)
    pdr_ja.add_argument("--subsystem", default="")
    pdr_ja.add_argument("--impact-class", choices=VALID_IMPACT_CLASSES, default="rce")
    pdr_ja.add_argument("--symbols", default="", help="Comma-separated sink function/symbol/tag identifiers.")
    pdr_ja.add_argument("--max-steps", type=int, default=1, help="Max victim interaction steps for Crown-Jewel realism.")
    pdr_ja.add_argument("--allow-nondefault-config", action="store_true")
    pdr_ja.add_argument("--allow-visible-error", action="store_true")
    pdr_ja.add_argument("--worker", default="mapper")
    pdr_ja.add_argument("--run")
    pdr_jl = dr_sub.add_parser("jewel-list", help="List Crown-Jewel terminal sinks.")
    pdr_jl.add_argument("--run")
    pdr_pk = dr_sub.add_parser("park", help="Park a blocked deep chain lead as an Open Door and spawn bounded bridge hunters.")
    pdr_pk.add_argument("--anchor-locus", required=True, help="Target sink or partial-chain locus (`file:lines`).")
    pdr_pk.add_argument("--missing", required=True, help="Concise description of the missing upstream/downstream link.")
    pdr_pk.add_argument("--wishlist", default="", help="Optional lexical/symbol FTS5 query describing what unlocks this door.")
    pdr_pk.add_argument("--jewel", default="", help="Optional Crown-Jewel ID (`cjw-...`).")
    pdr_pk.add_argument("--direction", choices=VALID_DOOR_DIRECTIONS, default="sink_to_source")
    pdr_pk.add_argument("--blocker-locus", default="", help="Upstream guard locus (`file:lines`) currently blocking the door.")
    pdr_pk.add_argument("--subsystem", default="")
    pdr_pk.add_argument("--held-ids", default="", help="Comma-separated `fnd-*` / `prim-*` IDs already held on this chain.")
    pdr_pk.add_argument("--snapshot", default="", help="Optional `snp-*` post-state snapshot ID.")
    pdr_pk.add_argument("--wanted-tags", default="", help="Comma-separated capability tags (`ns:name`) that unlock this door.")
    pdr_pk.add_argument("--wanted-symbols", default="", help="Comma-separated code symbols or file paths that unlock this door.")
    pdr_pk.add_argument("--max-bridge-attempts", type=int, default=2)
    pdr_pk.add_argument("--no-spawn-hunters", action="store_true")
    pdr_pk.add_argument("--worker", default="worker")
    pdr_pk.add_argument("--run")
    pdr_ls = dr_sub.add_parser("list", help="List Open Doors (`ready`, `bridging`, `parked`, `chained`, `exhausted_locked`).")
    pdr_ls.add_argument("--status", choices=("parked", "bridging", "ready", "chained", "exhausted_locked"))
    pdr_ls.add_argument("--run")
    p_dr.set_defaults(func=cmd_door)

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
    ps_add.add_argument("--requires-tags", default="", help="Comma-separated capability tags required to reach or trigger this sink.")
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
    task_kinds = ("map", "investigate", "bridge", "falsify", "reproduce", "instrument", "chain", "patch", "escalate")
    p_tsk = sub.add_parser("task", help="Coordinate bounded work tasks (`lease`, `checkpoint`, `done`, `dry`, `block`).")
    tsk_sub = p_tsk.add_subparsers(dest="task_cmd", required=True)
    pt_add = tsk_sub.add_parser("add")
    pt_add.add_argument("--kind", choices=task_kinds, required=True)
    pt_add.add_argument(
        "--direction",
        choices=("outside_in", "inside_out", "native_ffi", "peer_symmetry"),
        default="outside_in",
        help="Investigation direction (`outside_in`, `inside_out`, `native_ffi`, `peer_symmetry`).",
    )
    pt_add.add_argument("--title", required=True)
    pt_add.add_argument("--surface")
    pt_add.add_argument("--parent")
    pt_add.add_argument("--subsystem")
    pt_add.add_argument("--locus")
    pt_add.add_argument("--priority", choices=("critical", "high", "medium", "low"), default="high")
    pt_add.add_argument("--run")

    pt_lease = tsk_sub.add_parser("lease")
    pt_lease.add_argument("--worker", required=True)
    pt_lease.add_argument("--kind", choices=task_kinds)
    pt_lease.add_argument("--ttl", type=int, default=900)
    pt_lease.add_argument("--recover", action="store_true")
    pt_lease.add_argument("--run")

    pt_chk = tsk_sub.add_parser("checkpoint")
    pt_chk.add_argument("task_id")
    pt_chk.add_argument("--worker", required=True)
    pt_chk.add_argument("--state-json", required=True, help="Concise JSON object (`<= 2 KB`) persisting progress for session resume.")
    pt_chk.add_argument("--run")

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

    # coverage
    p_cov = sub.add_parser("coverage", help="Record or inspect audited source line spans (`coverage_spans`).")
    cov_sub = p_cov.add_subparsers(dest="coverage_cmd", required=True)
    pcv_r = cov_sub.add_parser("record")
    pcv_r.add_argument("rel_path", help="Relative file path inside target.")
    pcv_r.add_argument("--start-line", type=int, required=True)
    pcv_r.add_argument("--end-line", type=int, required=True)
    pcv_r.add_argument("--task")
    pcv_r.add_argument("--worker", default="worker")
    pcv_r.add_argument("--run")
    pcv_l = cov_sub.add_parser("list")
    pcv_l.add_argument("--run")
    p_cov.set_defaults(func=cmd_coverage)

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
    p_pr = sub.add_parser("primitive", help="Register capabilities or trust-laundering gadgets and promote composable helpers.")
    pr_sub = p_pr.add_subparsers(dest="primitive_cmd", required=True)
    pp_add = pr_sub.add_parser("add")
    pp_add.add_argument("--locus", required=True)
    pp_add.add_argument("--kind", required=True)
    pp_add.add_argument("--role", choices=("capability", "trust_gadget"), default="capability", help="`capability` (invariant-breaking quirk) or `trust_gadget` (normal code trusting an upstream invariant).")
    pp_add.add_argument("--trusted-invariant", default="", help="Upstream invariant trusted by a `trust_gadget` step.")
    pp_add.add_argument("--symbols", default="", help="Comma-separated code symbols or file paths touched by this primitive.")
    pp_add.add_argument("--preconditions", required=True)
    pp_add.add_argument("--postconditions", required=True)
    pp_add.add_argument("--evidence-cmd", required=True)
    pp_add.add_argument("--evidence-output", default="")
    pp_add.add_argument("--micropatch", default="", help="Optional counterfactual unified diff file stored for zero-ceremony `ajar chain propose` ablation.")
    pp_add.add_argument("--snapshot", default="", help="Optional associated `snp-*` post-state snapshot ID.")
    pp_add.add_argument("--surface", help="Optional associated surface ID.")
    pp_add.add_argument("--guarded-by", help="Upstream guard locus (`file:lines`) blocking standalone exploitation.")
    pp_add.add_argument("--guard-assumption", default="", help="Invariant assumed by the upstream guard.")
    pp_add.add_argument("--provides-tags", default="", help="Comma-separated capability tags provided by this primitive (`ns:name`).")
    pp_add.add_argument("--requires-tags", default="", help="Comma-separated capability tags required by this primitive (`ns:name`).")
    pp_add.add_argument("--run")

    pp_dry = pr_sub.add_parser("dry", help="Close an unchained guarded primitive as `dry` with a verified guard locus.")
    pp_dry.add_argument("primitive_id")
    pp_dry.add_argument("--worker", default="worker")
    pp_dry.add_argument("--locus", required=True)
    pp_dry.add_argument("--reason", required=True)
    pp_dry.add_argument("--run")

    pp_prm = pr_sub.add_parser("promote-helper", help="Verify and mount a read-only `StageContext` Python helper outside `slot-<k>`.")
    pp_prm.add_argument("primitive_id")
    pp_prm.add_argument("--file", required=True, help="Path to Python helper module.")
    pp_prm.add_argument("--callable", required=True, help="Callable function name accepting `(ctx: StageContext)`.")
    pp_prm.add_argument("--provides-tags", default="", help="Additional comma-separated `provides_tags`.")
    pp_prm.add_argument("--requires-tags", default="", help="Additional comma-separated `requires_tags`.")
    pp_prm.add_argument("--self-test-cmd", default="", help="Optional custom dual-mode verification command.")
    pp_prm.add_argument("--timeout", type=int, default=30)
    pp_prm.add_argument("--worker", default="worker")
    pp_prm.add_argument("--run")

    pp_hlp = pr_sub.add_parser("helpers", help="List promoted `StageContext` helpers.")
    pp_hlp.add_argument("--run")

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
    p_cl = sub.add_parser("claim", help="Manage vulnerability hypotheses (`propose`, `rescope`, `falsify`, `survive`, `instrument`, `reproduce`).")
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

    pc_rsc = cl_sub.add_parser("rescope")
    pc_rsc.add_argument("claim_id")
    pc_rsc.add_argument("--worker", required=True)
    pc_rsc.add_argument("--reason", required=True)
    pc_rsc.add_argument("--title")
    pc_rsc.add_argument("--locus")
    pc_rsc.add_argument("--mechanism")
    pc_rsc.add_argument("--severity", choices=("critical", "high", "medium", "low"))
    pc_rsc.add_argument("--falsification-prediction")
    pc_rsc.add_argument("--falsification-test")
    pc_rsc.add_argument("--run")

    pc_fal = cl_sub.add_parser("falsify")
    pc_fal.add_argument("claim_id")
    pc_fal.add_argument("--worker", required=True)
    pc_fal.add_argument("--notes", required=True)
    pc_fal.add_argument("--control-locus")
    pc_fal.add_argument("--config-gate", default="", help="Optional runtime config predicate gating reachability (`config_gated` probe).")
    pc_fal.add_argument("--run")

    pc_sur = cl_sub.add_parser("survive")
    pc_sur.add_argument("claim_id")
    pc_sur.add_argument("--worker", required=True)
    pc_sur.add_argument("--notes", required=True)
    pc_sur.add_argument("--run")

    pc_ins = cl_sub.add_parser("instrument", help="Run an isolated diagnostic probe inside scratch `slot-inst` to unblock `needs_instrumentation`.")
    pc_ins.add_argument("claim_id")
    pc_ins.add_argument("--worker", required=True)
    pc_ins.add_argument("--probe-cmd", required=True)
    pc_ins.add_argument("--probe-patch", default="", help="Optional temporary diagnostic diff applied only inside `slot-inst`.")
    pc_ins.add_argument("--timeout", type=int, default=60)
    pc_ins.add_argument("--run")

    pc_blk = cl_sub.add_parser("block")
    pc_blk.add_argument("claim_id")
    pc_blk.add_argument("--worker", required=True)
    pc_blk.add_argument(
        "--env-blocker",
        choices=ENV_BLOCKER_KINDS,
        default="",
        help="Concrete environmental blocker kind (safety-policy/refusal deferrals are rejected).",
    )
    pc_blk.add_argument("--reason", required=True)
    pc_blk.add_argument("--run")

    pc_rep = cl_sub.add_parser("reproduce")
    pc_rep.add_argument("claim_id")
    pc_rep.add_argument("--worker", required=True)
    pc_rep.add_argument("--mode", choices=("source", "binary", "live"))
    pc_rep.add_argument("--poc-cmd", default="")
    pc_rep.add_argument("--control-cmd", default="")
    pc_rep.add_argument("--build-cmd", default="", help="Optional compile command run on clean and micropatched trees without burning PoC strikes on build errors.")
    pc_rep.add_argument("--micropatch", help="Path to 1-16 line counterfactual unified diff (source mode).")
    pc_rep.add_argument("--save-post-state", default="", help="Optional relative directory/file inside `slot-<k>` to snapshot into `repro/snapshots/<snp_id>.tar.gz` after Arm 1.")
    pc_rep.add_argument("--provides-tags", default="", help="Optional comma-separated capability tags emitted by this confirmed finding (`ns:name`).")
    pc_rep.add_argument("--declared-steps", type=int, default=None, help="Optional explicit victim interaction step count for realism scoring.")
    pc_rep.add_argument("--shared-guard-locus", default="", help="Optional shared upstream guard locus when micropatch fixes a shared chokepoint.")
    pc_rep.add_argument("--release-cmd", default="", help="Arm 5A release-profile PoC command (`-O2` / `--release` without debug asserts).")
    pc_rep.add_argument("--release-control-cmd", default="", help="Arm 5B release-profile benign control command.")
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

    # repro (Strike-free smoke-test & snapshots)
    p_rpr = sub.add_parser("repro", help="Run strike-free build/PoC smoke tests (`ajar repro try`) and inspect post-state snapshots.")
    rpr_sub = p_rpr.add_subparsers(dest="repro_cmd", required=True)
    prp_t = rpr_sub.add_parser("try", help="Run a strike-free command inside scratch `slot-inst` without incrementing `failed_repro_count`.")
    prp_t.add_argument("--cmd", required=True)
    prp_t.add_argument("--patch", default="", help="Optional candidate diff applied temporarily inside `slot-inst`.")
    prp_t.add_argument("--build-cmd", default="", help="Optional compile command run before `--cmd`.")
    prp_t.add_argument("--oracle-json", help="Optional JSON oracle rules.")
    prp_t.add_argument("--timeout", type=int, default=60)
    prp_t.add_argument("--run")
    prp_s = rpr_sub.add_parser("snapshots", help="List captured Arm-1 post-state snapshots (`snp-*`).")
    prp_s.add_argument("--run")
    p_rpr.set_defaults(func=cmd_repro)

    # finding (Operator calibration & listing)
    p_fnd = sub.add_parser("finding", help="Inspect confirmed findings and calibrate severity/titles without raw SQL.")
    fnd_sub = p_fnd.add_subparsers(dest="finding_cmd", required=True)
    pfn_c = fnd_sub.add_parser("calibrate", help="Calibrate severity or title on a confirmed finding.")
    pfn_c.add_argument("finding_id")
    pfn_c.add_argument("--severity", choices=("critical", "high", "medium", "low"))
    pfn_c.add_argument("--title")
    pfn_c.add_argument("--reason", required=True)
    pfn_c.add_argument("--worker", default="operator")
    pfn_c.add_argument("--run")
    pfn_l = fnd_sub.add_parser("list", help="List confirmed findings.")
    pfn_l.add_argument("--run")
    p_fnd.set_defaults(func=cmd_finding)

    # chain
    p_ch = sub.add_parser("chain", help="Compose verified findings, capabilities, and trust gadgets into ablated multi-step chains.")
    ch_sub = p_ch.add_subparsers(dest="chain_cmd", required=True)
    pch_p = ch_sub.add_parser("propose")
    pch_p.add_argument("--title", required=True)
    pch_p.add_argument("--steps", required=True, help="Comma-separated `fnd-*`, `clm-*`, `prim-*`, or `anom-*` IDs.")
    pch_p.add_argument("--poc-cmd", required=True)
    pch_p.add_argument("--control-cmd", required=True)
    pch_p.add_argument("--severity", choices=("critical", "high", "medium", "low"), default="critical")
    pch_p.add_argument("--oracle-json", help="Optional JSON oracle rules (`expect_regex`, `expect_exit_code`).")
    pch_p.add_argument("--step-micropatch", action="append", help="Per-step counterfactual patch `<step_id>:<path/to/step.diff>` (auto-inherited for `fnd-*` and `prim-*` with `--micropatch`).")
    pch_p.add_argument("--door", default="", help="Optional Open Door ID (`door-*`) resolved by this chain.")
    pch_p.add_argument("--jewel", default="", help="Optional Crown Jewel ID (`cjw-*`) reached by this chain.")
    pch_p.add_argument("--declared-steps", type=int, default=None, help="Optional explicit victim interaction step count.")
    pch_p.add_argument("--no-ablate", action="store_true", help="Skip automated per-step ablation (single-anomaly chains only).")
    pch_p.add_argument("--timeout", type=int, default=60)
    pch_p.add_argument("--worker", default="worker")
    pch_p.add_argument("--run")

    pch_pr = ch_sub.add_parser("probe", help="Hydrate a Stage-1 post-state snapshot (`snp-*`) into `slot-inst` (`< 50 ms`) and probe Stage 2.")
    pch_pr.add_argument("--from-snapshot", required=True, help="Snapshot ID (`snp-*`) from `ajar claim reproduce --save-post-state`.")
    pch_pr.add_argument("--cmd", required=True, help="Stage-2 probe command executed inside hydrated `slot-inst`.")
    pch_pr.add_argument("--patch", default="", help="Optional temporary diff applied inside `slot-inst`.")
    pch_pr.add_argument("--oracle-json", help="Optional JSON oracle rules.")
    pch_pr.add_argument("--timeout", type=int, default=60)
    pch_pr.add_argument("--worker", default="worker")
    pch_pr.add_argument("--run")

    pch_fr = ch_sub.add_parser("frontier", help="Compile Crown-Jewel, Open-Door, multi-hop Percolation, and Unicorn-Gap frontier.")
    pch_fr.add_argument("--run")

    pch_l = ch_sub.add_parser("list")
    pch_l.add_argument("--run")
    p_ch.set_defaults(func=cmd_chain)

    # hooks (epistemic micro-hooks inspection)
    p_eh = sub.add_parser("hooks", help="Inspect event-driven epistemic micro-hooks (`H1`–`H8`).")
    eh_sub = p_eh.add_subparsers(dest="hooks_cmd", required=True)
    peh_l = eh_sub.add_parser("list")
    peh_l.add_argument("--status", choices=("active", "consumed", "expired"))
    peh_l.add_argument("--run")
    p_eh.set_defaults(func=cmd_epistemic_hooks)

    # patch (9-Arm Production Fixes Gate)
    p_ptc = sub.add_parser("patch", help="Verify production Fixes with the hardened 9-Arm Remediation Gate (`ajar patch verify`).")
    ptc_sub = p_ptc.add_subparsers(dest="patch_cmd", required=True)
    ppt_v = ptc_sub.add_parser("verify")
    ppt_v.add_argument("finding_id")
    ppt_v.add_argument("--patch", required=True, help="Path to unified diff production patch.")
    ppt_v.add_argument("--suite-cmd", required=True, help="Arm 5 full project test suite command.")
    ppt_v.add_argument("--variant-cmd", action="append", required=True, help="Arm 6 bypass variant command (repeat >= 3 times; >= 1 must trigger on clean HEAD).")
    ppt_v.add_argument("--caller-audit", required=True, help="Arm 7 caller NULL/error-return safety audit note (>= 20 chars).")
    ppt_v.add_argument("--sibling-audit", required=True, help="Arm 8 sibling-route / peer-hook symmetry audit note (>= 20 chars).")
    ppt_v.add_argument("--caller-cmd", default="", help="Optional executable Arm 7 caller error-propagation test command.")
    ppt_v.add_argument("--sibling-cmd", default="", help="Optional executable Arm 8 sibling-route symmetry test command.")
    ppt_v.add_argument("--oracle-json", help="Optional JSON oracle rules for PoC/variant checks.")
    ppt_v.add_argument("--shared-guard-locus", default="", help="Optional shared guard locus when patching a common chokepoint.")
    ppt_v.add_argument("--max-changed-lines", type=int, default=120)
    ppt_v.add_argument("--timeout", type=int, default=90)
    ppt_v.add_argument("--suite-timeout", type=int, default=1800, help="Timeout in seconds for Arm 5 full project test suite (default: 1800).")
    ppt_v.add_argument("--build-cmd", default="", help="Optional build command run before clean/patched/reverted verification steps.")
    ppt_v.add_argument("--worker", default="worker")
    ppt_v.add_argument("--run")
    ppt_l = ptc_sub.add_parser("list")
    ppt_l.add_argument("--run")
    p_ptc.set_defaults(func=cmd_patch)

    # steer
    p_st = sub.add_parser("steer", help="Manage attributable workspace Steers (`DEC-0049` / `DEC-0061`).")
    st_sub = p_st.add_subparsers(dest="steer_cmd", required=True)
    pst_a = st_sub.add_parser("add")
    pst_a.add_argument("--rule", required=True, help="Threat-model or scope rule text.")
    pst_a.add_argument("--scope", choices=("global", "subsystem", "path"), default="global")
    pst_a.add_argument("--filter", default="", help="Subsystem name or path prefix when scope != global.")
    pst_a.add_argument("--author", default="operator")
    pst_a.add_argument(
        "--kind",
        choices=("scope_authority", "research_steering"),
        default="scope_authority",
        help="`scope_authority` preserves autonomous attribution; `research_steering` marks human-guided.",
    )
    pst_a.add_argument("--run")
    pst_l = st_sub.add_parser("list")
    pst_l.add_argument("--all", action="store_true", help="Include revoked Steers.")
    pst_l.add_argument("--run")
    pst_r = st_sub.add_parser("revoke")
    pst_r.add_argument("steer_id")
    pst_r.add_argument("--reason", required=True)
    pst_r.add_argument("--actor", default="operator")
    pst_r.add_argument("--run")
    p_st.set_defaults(func=cmd_steer)

    # export-graph (Platform whiteboard feed)
    p_eg = sub.add_parser("export-graph", help="Export deterministic Platform component & attack-flow JSON graph.")
    p_eg.add_argument("--output", help="Optional output file path.")
    p_eg.add_argument("--run")
    p_eg.set_defaults(func=cmd_export_graph)

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
    psp_a.add_argument("--surface", default="", help="Optional surface ID for dry-surface breaker tracking.")
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
    def _cmd_mcp(a: argparse.Namespace) -> int:
        serve_mcp_stdio(explicit_run_id=a.run)
        return EXIT_OK

    p_mcp = sub.add_parser("mcp", help="Run STDIO JSON-RPC 2.0 MCP server for Host Mode agents.")
    p_mcp.add_argument("--run")
    p_mcp.set_defaults(func=_cmd_mcp)

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
    p_run.add_argument("--until", choices=stopping_choices, default="exhaustive-high")
    p_run.add_argument("--stopping", dest="until", choices=stopping_choices, help="Alias for --until.")
    p_run.add_argument("--phase", choices=phase_choices, default="hunt", help="Campaign phase (`hunt` defers 9-arm `patch verify` until `remediate`).")
    p_run.add_argument("--budget", type=float, default=None, help="Explicit COGS cap override in USD (defaults to 0.35 * Code quote).")
    p_run.add_argument("--cogs-cap", dest="budget", type=float, help="Alias for --budget explicit COGS cap override in USD.")
    p_run.add_argument("--workers", type=int, default=2)
    p_run.add_argument("--discover-passes", type=int, default=1, help="Keep-biased Best-of-N discovery passes across directions before funneling.")
    p_run.add_argument("--worker-cmd", help="Worker command executed per leased task.")
    p_run.add_argument("--max-steps", type=int, default=50)
    p_run.add_argument("--json", action="store_true", default=True)
    p_run.set_defaults(func=cmd_run)

    # swarm (Stage-split stripped packet dispatcher + wire-profile fallback ladder)
    p_swm = sub.add_parser(
        "swarm",
        help="Generate stripped Swarm Worker packets and step down `--wire-profile` fallback tiers.",
    )
    swm_sub = p_swm.add_subparsers(dest="swarm_cmd", required=True)
    psw_p = swm_sub.add_parser("packet", help="Emit a stripped Just-Enough-Context worker assignment packet.")
    psw_p.add_argument("--stage", choices=VALID_SWARM_STAGES, required=True)
    psw_p.add_argument(
        "--wire-profile",
        choices=("auto", *WIRE_PROFILE_LADDER),
        default="auto",
        help="Wire framing tier (`auto` defaults to `direct` Swarm Worker and honors prior fallback escalations).",
    )
    psw_p.add_argument("--items", default="", help="Optional comma-separated task/claim/primitive/finding/door IDs.")
    psw_p.add_argument("--limit", type=int, default=4, help="Max items per packet (`regression_tdd` forces 1, `swarm_patch_first` <= 2).")
    psw_p.add_argument("--worker", default="", help="Explicit worker ID override.")
    psw_p.add_argument("--json", action="store_true", help="Emit JSON metadata + packet_markdown instead of raw Markdown.")
    psw_p.add_argument("--run")

    psw_f = swm_sub.add_parser("fallback", help="Record a stalled/filter-blocked worker and emit stepped-down fallback packet(s).")
    psw_f.add_argument("target", help="Dispatch ID (`dsp-...`) or worker ID (`w-...`) that stalled or refused.")
    psw_f.add_argument("--reason", choices=VALID_FALLBACK_REASONS, default="idle_no_return")
    psw_f.add_argument("--notes", default="")
    psw_f.add_argument("--run")

    psw_c = swm_sub.add_parser("complete", help="Mark a swarm dispatch completed.")
    psw_c.add_argument("target", help="Dispatch ID (`dsp-...`) or worker ID (`w-...`).")
    psw_c.add_argument("--notes", default="")
    psw_c.add_argument("--run")

    psw_s = swm_sub.add_parser("status", help="List swarm dispatches and wire-profile escalations.")
    psw_s.add_argument("--run")
    p_swm.set_defaults(func=cmd_swarm)

    # reopen (Hydrate from shared mirror and unblock zero-attempt blocked claims)
    p_reo = sub.add_parser(
        "reopen",
        help="Hydrate a run from shared storage and reopen zero-attempt policy-blocked claims.",
    )
    p_reo.add_argument("run_id", help="Run ID to hydrate and reopen (for example `git-wave1a`).")
    p_reo.add_argument("--keep-blocked", action="store_true", help="Keep zero-attempt blocked claims untouched.")
    p_reo.add_argument("--from-shared", default=None, help="Explicit shared mirror directory override.")
    p_reo.add_argument("--json", action="store_true", default=True)
    p_reo.set_defaults(func=cmd_reopen)

    return p


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (AjarError, InvalidTransitionError) as exc:
        err_obj = {"error": scrub_text(str(exc)), "exit_code": exc.exit_code, **exc.details}
        sys.stderr.write(json.dumps(err_obj, sort_keys=True) + "\n")
        return int(exc.exit_code)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
