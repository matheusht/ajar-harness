"""Proof, chain, patch, and finding CLI handlers (`claim`, `chain`, `patch`, `repro`, `finding`)."""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess

from ajar import (
    EXIT_GATE_BLOCKED,
    EXIT_OK,
    EXIT_USER_ERROR,
)
from ajar.chain_planner import (
    compute_chain_frontier,
    evaluate_precondition_realism,
)
from ajar.cli.common import _emit
from ajar.db import (
    AjarError,
    calibrate_finding,
    list_rows,
    log_event,
    open_run_db,
    record_repro_failure,
    resolve_run_id,
    run_dir_for,
)
from ajar.epistemic_hooks import (
    claim_requires_release_ub_diff,
    parse_tag_list,
)
from ajar.patch_verify import run_8arm_patch_verification
from ajar.redact import (
    scrub_text,
    scrubbed_subprocess_env,
)
from ajar.repro_binary_live import (
    run_binary_reproduction,
    run_live_reproduction,
)
from ajar.repro_compose import (
    _parse_step_micropatches,
    run_chain_reproduction,
    run_claim_instrumentation,
    run_snapshot_chain_probe,
)
from ajar.repro_source import (
    run_repro_try,
    run_source_reproduction,
)
from ajar.services import (
    block_claim,
    falsify_claim,
    preflight_chain_proposal,
    propose_claim,
    record_chain_proposal,
    record_reproduction_outcome,
    rescope_claim_service,
    survive_claim,
)
from ajar.store import assert_run_mutable
from ajar.swarm import sync_run_to_shared_mirror


def cmd_claim(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    rdir = run_dir_for(rid)
    conn = open_run_db(rid)
    try:
        run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
        tpath = pathlib.Path(run["target_path"])
        tmode = str(run["target_mode"])

        if args.claim_cmd == "propose":
            res = propose_claim(
                conn,
                worker_id=args.worker,
                title=args.title,
                locus=args.locus,
                mechanism=args.mechanism,
                falsification_prediction=args.falsification_prediction,
                falsification_test=args.falsification_test,
                surface_id=args.surface,
                severity=args.severity,
                seeded_by_human=bool(args.seeded_by_human),
                consume_anomaly_id=args.consume_anomaly,
                target_dir=tpath,
                target_mode=tmode,
            )
            _emit(res, True)
            return EXIT_OK

        if args.claim_cmd == "rescope":
            res = rescope_claim_service(
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
            res = falsify_claim(
                conn,
                claim_id=args.claim_id,
                worker_id=args.worker,
                notes=args.notes,
                control_locus=args.control_locus,
                config_gate=str(getattr(args, "config_gate", None) or ""),
            )
            _emit(res, True)
            return EXIT_OK

        if args.claim_cmd == "survive":
            res = survive_claim(
                conn,
                claim_id=args.claim_id,
                worker_id=args.worker,
                notes=args.notes,
            )
            _emit(res, True)
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
            res = block_claim(
                conn,
                claim_id=args.claim_id,
                worker_id=args.worker,
                reason=args.reason,
                env_blocker=str(getattr(args, "env_blocker", None) or ""),
                target_mode=tmode,
            )
            _emit(res, True)
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

            out_payload = record_reproduction_outcome(
                conn,
                claim_id=args.claim_id,
                worker_id=args.worker,
                poc_cmd=args.poc_cmd,
                control_cmd=args.control_cmd,
                repro_result=res,
                build_cmd=str(getattr(args, "build_cmd", None) or ""),
                micropatch_path=str(args.micropatch or ""),
                oracle_dict=oracle_dict,
                provides_tags=prov_tags,
                declared_steps=decl_steps,
            )
            sync_run_to_shared_mirror(rid)
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

            preflight_chain_proposal(conn, steps)

            cwd = run["workspace_path"] if run else "."
            env = scrubbed_subprocess_env()
            p1 = subprocess.run(["bash", "-c", args.poc_cmd], cwd=cwd, env=env, capture_output=True, timeout=60, check=False)
            p2 = subprocess.run(["bash", "-c", args.control_cmd], cwd=cwd, env=env, capture_output=True, timeout=60, check=False)
            verified = p1.returncode != 0 and p2.returncode == 0
            ev = {
                "poc_exit": int(p1.returncode),
                "control_exit": int(p2.returncode),
                "poc_stdout": scrub_text(p1.stdout.decode("utf-8", errors="replace")[:1500]),
            }
            out = record_chain_proposal(
                conn,
                title=args.title,
                severity=args.severity,
                steps=steps,
                poc_cmd=args.poc_cmd,
                control_cmd=args.control_cmd,
                verified=verified,
                evidence=ev,
            )
            _emit(out, True)
            return EXIT_OK if verified else EXIT_GATE_BLOCKED

        rows = list_rows(conn, "SELECT * FROM chains ORDER BY created_at ASC")
        _emit({"chains": rows}, True)
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
