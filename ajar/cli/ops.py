"""Lifecycle, diagnostics, reporting, and swarm CLI handlers."""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import sqlite3
import sys
from typing import Any

from ajar import (
    EXIT_GATE_BLOCKED,
    EXIT_OK,
    EXIT_USER_ERROR,
    __version__,
)
from ajar.cli.common import _check_sqlite_fts5, _emit
from ajar.db import (
    AjarError,
    add_steer,
    add_threat_assumption,
    compute_root_plateau_throttles,
    list_rows,
    list_steers,
    log_event,
    open_run_db,
    render_task_context,
    resolve_run_id,
    revoke_steer,
    run_dir_for,
    run_pulse,
    transition_threat_assumption,
    upsert_threat_model,
)
from ajar.gates import check_all_gates
from ajar.graph import export_attack_flow_graph
from ajar.hooks import (
    evaluate_claude_stop_hook,
    run_host_continuation_loop,
)
from ajar.oracles import query_oracle
from ajar.redact import scrub_text
from ajar.repomap import (
    build_repomap,
    compute_quote_summary,
)
from ajar.report import (
    build_report_data,
    render_markdown_report,
)
from ajar.repro_source import aggregate_failure_telemetry, unshare_netns_available
from ajar.runner import run_autonomous_schedule
from ajar.services import (
    advance_phase,
    build_commit_preimage,
    cast_lead_vote,
    export_run_economics,
    finish_run,
    rank_leads,
    record_human_touch,
    record_spend_entry,
    write_restricted_json,
)
from ajar.swarm import (
    build_swarm_packet,
    complete_swarm_dispatch,
    escalate_swarm_fallback,
    reopen_run,
    sync_run_to_shared_mirror,
)
from ajar.target_check import (
    compute_disk_free_gib,
    evaluate_target_readiness,
)
from ajar.workspace import init_run_workspace


def _dir_size_bytes(path: pathlib.Path) -> int:
    total = 0
    if path.is_symlink() or not path.exists():
        return 0
    for item in path.rglob("*"):
        if item.is_file() and not item.is_symlink():
            try:
                total += item.stat().st_size
            except OSError:
                pass
    return total


def _diagnose_run_health(run_id: str, *, prune_slots: bool = False) -> dict[str, Any]:
    import fcntl
    import time

    rdir = run_dir_for(run_id)
    conn = open_run_db(run_id)
    try:
        qc_rows = [str(r[0]) for r in conn.execute("PRAGMA quick_check;").fetchall()]
        quick_check_ok = qc_rows == ["ok"]
        ver_row = conn.execute("PRAGMA user_version;").fetchone()
        schema_version = int(ver_row[0]) if ver_row is not None else 0
        run_row = conn.execute("SELECT status, campaign_phase FROM runs LIMIT 1").fetchone()
        open_tasks = int(conn.execute("SELECT COUNT(*) AS c FROM tasks WHERE status = 'open'").fetchone()["c"])
        leased_tasks = int(conn.execute("SELECT COUNT(*) AS c FROM tasks WHERE status = 'leased'").fetchone()["c"])
        now_ep = time.time()
        stale_leases = int(
            conn.execute(
                "SELECT COUNT(*) AS c FROM tasks WHERE status = 'leased' AND lease_expires_at IS NOT NULL AND lease_expires_at < ?",
                (now_ep,),
            ).fetchone()["c"]
        )
    finally:
        conn.close()

    repro_dir = rdir / "repro"
    slots_info: list[dict[str, Any]] = []
    pruned_slots: list[str] = []
    reclaimed_bytes = 0
    if repro_dir.is_dir():
        for slot_dir in sorted(
            p for p in repro_dir.iterdir() if not p.is_symlink() and p.is_dir() and p.name.startswith("slot-")
        ):
            lock_path = repro_dir / f"{slot_dir.name}.lock"
            locked = False
            fh = open(lock_path, "a+", encoding="utf-8")
            try:
                try:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    locked = True
                size_bytes = _dir_size_bytes(slot_dir)
                stale_git_locks = [
                    name
                    for name in ("index.lock", "shallow.lock")
                    if (slot_dir / ".git" / name).is_file()
                ]
                pruned = False
                if prune_slots and not locked:
                    shutil.rmtree(slot_dir, ignore_errors=True)
                    pruned = not slot_dir.exists()
                    if pruned:
                        pruned_slots.append(slot_dir.name)
                        reclaimed_bytes += size_bytes
                slots_info.append(
                    {
                        "name": slot_dir.name,
                        "locked": locked,
                        "size_mib": round(size_bytes / (1024 * 1024), 3),
                        "stale_git_locks": stale_git_locks,
                        "pruned": pruned,
                    }
                )
            finally:
                if not locked:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                fh.close()

    failures_dir = repro_dir / "failures"
    failure_artifacts = len(list(failures_dir.glob("*.json"))) if failures_dir.is_dir() else 0

    return {
        "run_id": run_id,
        "run_dir": str(rdir),
        "db_quick_check_ok": quick_check_ok,
        "db_quick_check": qc_rows,
        "schema_version": schema_version,
        "run_status": str(run_row["status"]) if run_row else "unknown",
        "campaign_phase": str(run_row["campaign_phase"]) if run_row else "unknown",
        "open_tasks": open_tasks,
        "leased_tasks": leased_tasks,
        "stale_leases": stale_leases,
        "failure_artifacts": failure_artifacts,
        "slots": slots_info,
        "pruned_slots": pruned_slots,
        "reclaimed_bytes": reclaimed_bytes,
        "healthy": quick_check_ok,
    }


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
    run_ok = True
    run_arg = getattr(args, "run", None)
    want_failures = bool(getattr(args, "failures", False))
    if run_arg or want_failures:
        rid = resolve_run_id(run_arg)
        if run_arg:
            rh = _diagnose_run_health(
                rid,
                prune_slots=bool(getattr(args, "prune_slots", False)),
            )
            report["run_health"] = rh
            run_ok = bool(rh["healthy"])
        if want_failures:
            rdir = run_dir_for(rid)
            conn = open_run_db(rid)
            try:
                ft = aggregate_failure_telemetry(rdir, conn=conn)
            finally:
                conn.close()
            ft["run_id"] = rid
            report["failure_telemetry"] = ft
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
        if not base_ok or not run_ok:
            return EXIT_USER_ERROR
        return EXIT_OK if tc["passed"] else EXIT_GATE_BLOCKED
    _emit(report, bool(args.json))
    return EXIT_OK if (base_ok and run_ok) else EXIT_USER_ERROR


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
            unvisited_only=bool(getattr(args, "unvisited", False)),
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
            res = record_human_touch(conn, kind=args.kind, actor=args.actor, notes=args.notes)
            _emit(res, True)
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
            res = record_spend_entry(
                conn,
                worker_id=args.worker,
                surface_id=getattr(args, "surface", None) or "",
                phase=args.phase,
                model=args.model or "",
                tokens_in=int(args.tokens_in),
                tokens_out=int(args.tokens_out),
                cost_usd=float(args.cost_usd),
                notes=args.notes or "",
            )
            _emit(res, True)
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

        res = advance_phase(
            conn,
            run_id=rid,
            to_phase=str(args.to),
            notes=str(args.notes or ""),
            actor="operator",
            force=bool(getattr(args, "force", False)),
        )
        _emit(res, True)
        return EXIT_OK
    finally:
        conn.close()


def cmd_export_graph(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    conn = open_run_db(rid)
    try:
        graph = export_attack_flow_graph(
            conn,
            schema=str(getattr(args, "schema", "v2") or "v2"),
            visibility=str(getattr(args, "visibility", "internal_full") or "internal_full"),
            include_snippets=bool(getattr(args, "include_snippets", False)),
            repo_slug=str(getattr(args, "repo_slug", "") or ""),
        )
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
        res = finish_run(conn, run_id=rid, target_dir=tpath, actor="operator")
        if not res["passed"]:
            _emit(res, True)
            return EXIT_GATE_BLOCKED
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


def cmd_economics(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    conn = open_run_db(rid)
    try:
        res = export_run_economics(conn)
    finally:
        conn.close()
    if getattr(args, "output", None):
        out_p = pathlib.Path(args.output)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(res, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _emit(res, True)
    return EXIT_OK


def cmd_ledger(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    conn = open_run_db(rid)
    try:
        res = build_commit_preimage(
            conn,
            finding_id=args.finding_id,
            commit_sha=str(args.commit_sha or ""),
            target_slug=str(args.target_slug or ""),
            salt=args.salt,
        )
    finally:
        conn.close()
    if args.public_out:
        pub_p = pathlib.Path(args.public_out)
        pub_p.parent.mkdir(parents=True, exist_ok=True)
        pub_p.write_text(json.dumps(res["public_record"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.preimage_out:
        write_restricted_json(pathlib.Path(args.preimage_out), res["private_preimage"], mode=0o600)
        emit_payload: dict[str, Any] = {
            "schema_version": res["schema_version"],
            "commitment_sha256": res["commitment_sha256"],
            "public_record": res["public_record"],
            "preimage_out": str(args.preimage_out),
        }
        if args.public_out:
            emit_payload["public_out"] = str(args.public_out)
        _emit(emit_payload, True)
        return EXIT_OK
    _emit(res, True)
    return EXIT_OK


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


def cmd_lead(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    conn = open_run_db(rid)
    try:
        if args.lead_cmd == "vote":
            res = cast_lead_vote(
                conn,
                worker_id=args.worker,
                target_kind=args.target_kind,
                target_id=args.target_id or "",
                locus=args.locus or "",
                subsystem=args.subsystem or "",
                impact_score=int(args.impact),
                plausibility_score=int(args.plausibility),
                chainability_score=int(args.chainability),
                effort_cost=int(args.effort),
                rationale=args.rationale or "",
            )
            _emit(res, True)
            return EXIT_OK
        if args.lead_cmd == "rank":
            res = rank_leads(
                conn,
                target_kind=args.target_kind or "",
                limit=int(args.limit),
            )
            _emit(res, True)
            return EXIT_OK
        throttles = compute_root_plateau_throttles(conn)
        _emit({"run_id": rid, "root_plateau_throttles": list(throttles.values())}, True)
        return EXIT_OK
    finally:
        conn.close()

