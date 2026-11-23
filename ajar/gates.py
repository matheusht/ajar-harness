"""Deterministic SQL closeout gates (`G1`–`G5`), anti-gaming guards, and attribution.

Evaluates run completion strictly from SQLite state without any LLM calls:
- `G1`: Surface & priority task coverage (exhaustive-high vs first-verified-high)
- `G2`: Zero unresolved claims (`proposed`, `survived_falsify`, `needs_instrumentation`)
- `G3`: 4-arm causal proof + fresh falsifier separation (`proposer != falsifier`)
- `G4`: Zero-Skill First-Principles worker quota (`>= 1` when `>= 2` workers run)
        + anti-bulk-dismissal guard on `dry` tasks
- `G5`: Orphaned `unexplained` anomalies resolved + multi-primitive `chain` check
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
from typing import Any

from ajar.db import log_event, new_id, utc_now_iso


def compute_attribution_and_economics(conn: sqlite3.Connection) -> dict[str, Any]:
    """Compute human-touch passes (`DEC-0061`/`0071`) and `Code` unit economics (`DEC-0122`)."""
    run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
    touches = conn.execute("SELECT kind, COUNT(*) AS c FROM human_touches GROUP BY kind").fetchall()
    touch_counts = {r["kind"]: int(r["c"]) for r in touches}

    steering_count = touch_counts.get("research_steering", 0) + touch_counts.get("poc_repair", 0)
    rescue_count = touch_counts.get("env_rescue", 0)

    research_independence_pass = steering_count == 0
    product_operability_pass = rescue_count == 0

    default_attribution = (
        "found_autonomously_by_ajar" if research_independence_pass else "found_with_ajar"
    )

    spend_row = conn.execute(
        """
        SELECT COALESCE(SUM(cost_usd), 0.0) AS total_usd,
               COALESCE(SUM(CASE WHEN phase = 'explore' THEN cost_usd ELSE 0.0 END), 0.0) AS explore_usd,
               COALESCE(SUM(CASE WHEN phase = 'verify' THEN cost_usd ELSE 0.0 END), 0.0) AS verify_usd,
               COALESCE(SUM(tokens_in), 0) AS tokens_in,
               COALESCE(SUM(tokens_out), 0) AS tokens_out
        FROM spend_ledger
        """
    ).fetchone()

    total_usd = round(float(spend_row["total_usd"] or 0.0), 4)
    loc = int(run["in_scope_loc"] if run else 0)
    budget_usd = float(run["budget_usd"] if run else 14.0)
    code_quote_usd = float(run["code_quote_usd"] if run else 10.0)
    run_keys = set(run.keys()) if run is not None else set()
    cogs_cap_usd = float(run["cogs_cap_usd"]) if "cogs_cap_usd" in run_keys else round(0.35 * code_quote_usd, 2)
    pricing_mode = str(run["pricing_mode"]) if "pricing_mode" in run_keys else "commercial_code"
    cost_usd_per_kloc = round((total_usd / (loc / 1000.0)), 4) if loc > 0 else 0.0
    if pricing_mode == "uncapped_research" or budget_usd <= 0.0:
        gross_margin_floor_pass = True
    elif pricing_mode == "commercial_code":
        gross_margin_floor_pass = total_usd <= cogs_cap_usd
    else:
        gross_margin_floor_pass = total_usd <= budget_usd

    return {
        "in_scope_loc": loc,
        "code_quote_usd": code_quote_usd,
        "cogs_cap_usd": cogs_cap_usd,
        "pricing_mode": pricing_mode,
        "budget_usd": budget_usd,
        "total_spend_usd": total_usd,
        "explore_spend_usd": round(float(spend_row["explore_usd"] or 0.0), 4),
        "verify_spend_usd": round(float(spend_row["verify_usd"] or 0.0), 4),
        "tokens_in": int(spend_row["tokens_in"] or 0),
        "tokens_out": int(spend_row["tokens_out"] or 0),
        "cost_usd_per_kloc": cost_usd_per_kloc,
        "within_code_cogs_target": (cost_usd_per_kloc <= 2.0) if loc > 0 else True,
        "gross_margin_floor_pass": gross_margin_floor_pass,
        "human_touch_counts": touch_counts,
        "research_independence_pass": research_independence_pass,
        "product_operability_pass": product_operability_pass,
        "default_finding_attribution": default_attribution,
    }


def finding_attribution_for_claim(conn: sqlite3.Connection, claim_row: sqlite3.Row | dict[str, Any]) -> str:
    if int(claim_row["seeded_by_human"] or 0) == 1:
        return "validated_by_ajar"
    econ = compute_attribution_and_economics(conn)
    return str(econ["default_finding_attribution"])


def validate_dry_locus(target_dir: pathlib.Path | None, target_mode: str, locus: str, reason: str) -> tuple[bool, str]:
    """Verify `dry` task closure cites a real file locus and substantive guard explanation."""
    if not locus or ":" not in locus:
        return (False, "dry --locus must include file:line (for example `src/auth.py:42-55`).")
    if not reason or len(reason.strip()) < 15:
        return (False, "dry --control must explain the concrete guard in at least 15 characters.")
    if target_mode == "source" and target_dir is not None and target_dir.is_dir():
        rel_file = locus.split(":", 1)[0].strip().lstrip("/")
        candidate = (target_dir / rel_file).resolve()
        try:
            candidate.relative_to(target_dir.resolve())
        except ValueError:
            return (False, f"dry --locus {rel_file!r} escapes target directory.")
        if not candidate.is_file():
            return (False, f"dry --locus file does not exist in target: {rel_file}")
    return (True, "ok")


def check_guarded_primitive_dry_block(
    conn: sqlite3.Connection,
    *,
    task_row: sqlite3.Row | dict[str, Any],
    dry_locus: str,
) -> tuple[bool, str]:
    """Anti-Premature-`dry` Rule (`Sovereign` lesson):

    When a real dangerous sink or invariant flaw was recorded as a `primitive` with
    `guarded_by_locus`, block closing the investigation task as permanently `dry` unless
    a `conditional_blocked` guard-watch task or a `chain` task tracks breaking that guard.
    """
    if str(task_row["kind"]) != "investigate":
        return (True, "ok")
    t_surf = str(task_row["surface_id"] or "")
    t_loc = str(task_row["locus"] or "")
    guarded = conn.execute(
        """
        SELECT primitive_id, locus, kind, guarded_by_locus FROM primitives
        WHERE chained = 0 AND status != 'dry' AND guarded_by_locus != ''
          AND (
              (? != '' AND surface_id = ?)
              OR (? != '' AND locus = ?)
              OR guarded_by_locus = ?
          )
        """,
        (t_surf, t_surf, t_loc, t_loc, dry_locus.strip()),
    ).fetchall()
    if not guarded:
        return (True, "ok")

    cur_tid = str(task_row["task_id"])
    for gp in guarded:
        gloc = str(gp["guarded_by_locus"])
        ploc = str(gp["locus"])
        pid = str(gp["primitive_id"])
        if t_loc == gloc and ploc != gloc and dry_locus.strip() == gloc:
            continue
        door_tracked = conn.execute(
            """
            SELECT 1 FROM parked_doors
            WHERE blocker_locus = ? OR anchor_locus = ? OR held_ids_json LIKE '%' || ? || '%'
            LIMIT 1
            """,
            (gloc, ploc, pid),
        ).fetchone()
        if door_tracked is not None:
            continue
        tracked = conn.execute(
            """
            SELECT 1 FROM tasks
            WHERE task_id != ?
              AND (
                  (status = 'conditional_blocked' AND blocker_check_locus = ?)
                  OR (
                      kind IN ('chain', 'bridge') AND status IN ('open', 'leased', 'done', 'dry')
                      AND (locus = ? OR summary LIKE '%' || ? || '%' OR summary LIKE '%' || ? || '%')
                  )
                  OR (
                      kind = 'investigate' AND status IN ('done', 'dry')
                      AND locus = ?
                  )
              )
            LIMIT 1
            """,
            (cur_tid, gloc, gloc, gloc, pid, gloc),
        ).fetchone()
        if not tracked:
            return (
                False,
                f"Anti-premature-dry gate: guarded primitive {pid} ({gp['kind']} @ {gp['locus']}) "
                f"is only blocked by upstream guard {gloc}. Park an Open Door (`ajar door park --anchor-locus {ploc} "
                f"--blocker-locus {gloc} --missing '...'`) or audit {gloc} before closing `dry`.",
            )
    return (True, "ok")


def evaluate_dry_surface_breaker(
    conn: sqlite3.Connection,
    *,
    max_zero_signal_share: float = 0.25,
) -> list[dict[str, Any]]:
    """Throttle speculative `investigate` tasks on any surface burning `> 25%` of COGS cap with zero signal."""
    run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
    if run is None:
        return []
    cap = float(run["budget_usd"] or 0.0)
    if cap <= 0.0:
        return []
    threshold = cap * float(max_zero_signal_share)

    rows = conn.execute(
        """
        SELECT surface_id, COALESCE(SUM(cost_usd), 0.0) AS surf_spend
        FROM spend_ledger
        WHERE surface_id != '' AND phase = 'explore'
        GROUP BY surface_id
        HAVING surf_spend > ?
        """,
        (threshold,),
    ).fetchall()

    tripped: list[dict[str, Any]] = []
    now_iso = utc_now_iso()
    for r in rows:
        sid = str(r["surface_id"])
        anom_c = conn.execute("SELECT COUNT(*) AS c FROM anomalies WHERE surface_id = ?", (sid,)).fetchone()["c"]
        prim_c = conn.execute("SELECT COUNT(*) AS c FROM primitives WHERE surface_id = ?", (sid,)).fetchone()["c"]
        clm_c = conn.execute("SELECT COUNT(*) AS c FROM claims WHERE surface_id = ?", (sid,)).fetchone()["c"]
        if (int(anom_c) + int(prim_c) + int(clm_c)) > 0:
            continue
        cur = conn.execute(
            """
            UPDATE tasks
            SET status = 'conditional_blocked',
                blocker_predicate = 'dry_surface_breaker: >25% explore budget spent with zero anomalies/primitives/claims; reopen on cross-surface primitive',
                updated_at = ?
            WHERE surface_id = ? AND kind = 'investigate' AND status = 'open'
            """,
            (now_iso, sid),
        )
        throttled = int(cur.rowcount or 0)
        if throttled > 0:
            entry = {
                "surface_id": sid,
                "explore_spend_usd": round(float(r["surf_spend"]), 4),
                "threshold_usd": round(threshold, 4),
                "throttled_tasks": throttled,
            }
            tripped.append(entry)
            log_event(conn, "scheduler", "dry_surface_breaker_tripped", sid, entry)
    return tripped


def check_all_gates(
    conn: sqlite3.Connection,
    *,
    target_dir: pathlib.Path | None = None,
    auto_enqueue_chain: bool = True,
    reconcile: bool | None = None,
) -> dict[str, Any]:
    """Evaluate gates `G1` through `G5` and return structured pass/blocker details.

    When `auto_enqueue_chain=False` and `reconcile` is not explicitly `True`, this function
    is strictly read-only and performs zero database mutations.
    """
    from ajar.chain_planner import reconcile_door_bridge_tasks

    run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
    if run is None:
        return {"passed": False, "gates": {}, "blockers": ["Run metadata missing in run.db."]}

    do_reconcile = auto_enqueue_chain if reconcile is None else reconcile
    if do_reconcile:
        reconcile_door_bridge_tasks(conn)

    stopping = str(run["stopping_criterion"] or "exhaustive-high")
    target_mode = str(run["target_mode"] or "source")
    in_hunt_phase = bool("campaign_phase" in run.keys() and str(run["campaign_phase"] or "hunt") == "hunt")
    gates: dict[str, dict[str, Any]] = {}
    all_blockers: list[str] = []

    # --- G1: Surface & Task Coverage ---
    g1_issues: list[str] = []
    surface_count = conn.execute("SELECT COUNT(*) AS c FROM surfaces").fetchone()["c"]
    high_findings = conn.execute(
        "SELECT COUNT(*) AS c FROM findings WHERE severity IN ('critical', 'high')"
    ).fetchone()["c"]
    crown_jewels_reached = conn.execute(
        "SELECT COUNT(*) AS c FROM crown_jewels WHERE status = 'reached'"
    ).fetchone()["c"]
    crown_jewel_chains = conn.execute(
        "SELECT COUNT(*) AS c FROM chains WHERE verified = 1 AND realism_tier = 'crown_jewel'"
    ).fetchone()["c"]
    crown_jewel_findings = conn.execute(
        "SELECT COUNT(*) AS c FROM findings WHERE realism_tier = 'crown_jewel' AND severity IN ('critical', 'high')"
    ).fetchone()["c"]
    has_crown_jewel_win = (int(crown_jewels_reached) + int(crown_jewel_chains) + int(crown_jewel_findings)) >= 1

    if stopping == "first-verified-high" and int(high_findings) >= 1:
        leased_active = conn.execute(
            "SELECT COUNT(*) AS c FROM tasks WHERE status = 'leased' AND kind IN ('falsify', 'reproduce')"
        ).fetchone()["c"]
        if leased_active > 0:
            g1_issues.append(f"{leased_active} active verification task(s) still leased.")
    elif stopping == "crown-jewel" and has_crown_jewel_win:
        leased_active = conn.execute(
            "SELECT COUNT(*) AS c FROM tasks WHERE status = 'leased' AND kind IN ('falsify', 'reproduce', 'chain')"
        ).fetchone()["c"]
        if leased_active > 0:
            g1_issues.append(f"{leased_active} active verification/chain task(s) still leased.")
    else:
        if surface_count == 0:
            g1_issues.append("No surfaces mapped yet (`ajar surface add`).")
        open_high = conn.execute(
            """
            SELECT t.task_id, t.kind, t.title
            FROM tasks t
            LEFT JOIN surfaces s ON t.surface_id = s.surface_id
            WHERE t.status IN ('open', 'leased')
              AND (? = 0 OR t.kind != 'patch')
              AND (t.priority IN ('critical', 'high') OR s.priority IN ('critical', 'high'))
            """,
            (1 if in_hunt_phase else 0,),
        ).fetchall()
        if open_high:
            sample = ", ".join(f"{r['task_id']}[{r['kind']}]" for r in open_high[:5])
            g1_issues.append(f"{len(open_high)} critical/high task(s) remain open or leased: {sample}.")

        uncovered_surfaces = conn.execute(
            """
            SELECT s.surface_id, s.name FROM surfaces s
            WHERE s.priority IN ('critical', 'high')
              AND NOT EXISTS (
                  SELECT 1 FROM tasks t
                  WHERE t.surface_id = s.surface_id AND t.status IN ('done', 'dry', 'conditional_blocked')
              )
            """
        ).fetchall()
        if uncovered_surfaces:
            sample = ", ".join(f"{r['surface_id']}({r['name']})" for r in uncovered_surfaces[:5])
            g1_issues.append(f"{len(uncovered_surfaces)} critical/high surface(s) have zero completed tasks: {sample}.")

        if stopping == "crown-jewel" and not has_crown_jewel_win:
            bridging_doors = conn.execute(
                "SELECT door_id, anchor_locus FROM parked_doors WHERE status = 'bridging'"
            ).fetchall()
            if bridging_doors:
                sample = ", ".join(f"{r['door_id']}@{r['anchor_locus']}" for r in bridging_doors[:4])
                g1_issues.append(f"{len(bridging_doors)} Open Door(s) still actively bridging ({sample}).")

    gates["G1_surface_coverage"] = {"passed": len(g1_issues) == 0, "issues": g1_issues}
    all_blockers.extend(f"[G1] {m}" for m in g1_issues)

    # --- G2: Zero Unresolved Claims ---
    g2_issues: list[str] = []
    unresolved_claims = conn.execute(
        """
        SELECT c.claim_id, c.status, c.title FROM claims c
        WHERE c.status IN ('proposed', 'survived_falsify', 'needs_instrumentation')
           OR (
               c.status = 'config_gated'
               AND EXISTS (
                   SELECT 1 FROM tasks t
                   WHERE t.parent_claim_id = c.claim_id AND t.status IN ('open', 'leased')
               )
           )
        """
    ).fetchall()
    if unresolved_claims:
        sample = ", ".join(f"{r['claim_id']}[{r['status']}]" for r in unresolved_claims[:6])
        g2_issues.append(f"{len(unresolved_claims)} claim(s) still unresolved: {sample}.")
    gates["G2_claim_resolution"] = {"passed": len(g2_issues) == 0, "issues": g2_issues}
    all_blockers.extend(f"[G2] {m}" for m in g2_issues)

    # --- G3: 4-Arm Causal Proof + Fresh Falsifier Separation + Release UB Gate ---
    g3_issues: list[str] = []
    finding_rows = conn.execute(
        """
        SELECT f.*, c.proposer_worker_id, c.falsifier_worker_id,
               c.falsification_prediction, c.falsification_test, c.status AS claim_status
        FROM findings f
        JOIN claims c ON f.claim_id = c.claim_id
        """
    ).fetchall()
    for f in finding_rows:
        fid = f["finding_id"]
        if not f["falsifier_worker_id"]:
            g3_issues.append(f"Finding {fid} lacks an independent falsifier record.")
        elif f["proposer_worker_id"] == f["falsifier_worker_id"]:
            g3_issues.append(
                f"Finding {fid} violated fresh-falsifier separation (worker {f['proposer_worker_id']!r} both proposed and falsified)."
            )
        if not (f["falsification_prediction"] or "").strip() or not (f["falsification_test"] or "").strip():
            g3_issues.append(f"Finding {fid} missing pre-reproduction falsification prediction/test.")
        ub_cls = str(f["ub_divergence_class"] or "") if "ub_divergence_class" in f.keys() else ""
        if ub_cls == "debug_assert_only" and str(f["severity"]) in ("critical", "high"):
            g3_issues.append(
                f"Finding {fid} classified as debug_assert_only under --release-cmd; cannot hold {f['severity']} severity."
            )
        for arm_col in ("arm1_clean_poc_json", "arm2_clean_ctrl_json", "arm3_patch_poc_json", "arm4_patch_ctrl_json"):
            try:
                arm_data = json.loads(f[arm_col] or "{}")
            except json.JSONDecodeError:
                arm_data = {}
            if not arm_data.get("arm_passed", False):
                g3_issues.append(f"Finding {fid} failed causal check in {arm_col}.")
    gates["G3_causal_reproduction"] = {"passed": len(g3_issues) == 0, "issues": g3_issues}
    all_blockers.extend(f"[G3] {m}" for m in g3_issues)

    # --- G4: Zero-Skill Quota & Anti-Bulk-Dismissal ---
    g4_issues: list[str] = []
    distinct_inv_workers = conn.execute(
        "SELECT COUNT(DISTINCT worker_id) AS c FROM tasks WHERE kind = 'investigate' AND worker_id IS NOT NULL"
    ).fetchone()["c"]
    if int(distinct_inv_workers) >= 2 and int(run["zero_skill_leases"] or 0) < 1:
        g4_issues.append(
            f"{distinct_inv_workers} workers ran `investigate` tasks, but zero leases ran in `zero_skill` mode."
        )

    dry_tasks = conn.execute(
        "SELECT task_id, worker_id, dry_control_locus, dry_control_reason, closed_epoch FROM tasks WHERE status = 'dry' ORDER BY closed_epoch ASC"
    ).fetchall()
    for dt in dry_tasks:
        ok, msg = validate_dry_locus(
            target_dir, target_mode, str(dt["dry_control_locus"] or ""), str(dt["dry_control_reason"] or "")
        )
        if not ok:
            g4_issues.append(f"Task {dt['task_id']} invalid dry control: {msg}")

    # Detect >= 5 tasks closed dry within < 2 seconds by same worker with identical reason.
    by_worker: dict[str, list[sqlite3.Row]] = {}
    for dt in dry_tasks:
        by_worker.setdefault(str(dt["worker_id"] or ""), []).append(dt)
    for wid, w_rows in by_worker.items():
        if len(w_rows) >= 5:
            for idx in range(len(w_rows) - 4):
                window = w_rows[idx : idx + 5]
                t0 = float(window[0]["closed_epoch"] or 0.0)
                t4 = float(window[4]["closed_epoch"] or 0.0)
                reasons = {str(r["dry_control_reason"] or "").strip() for r in window}
                if t0 > 0 and (t4 - t0) < 2.0 and len(reasons) == 1:
                    g4_issues.append(
                        f"Bulk-dismissal detected: worker {wid!r} closed 5 tasks dry in {t4 - t0:.2f}s with identical reason."
                    )
                    break

    from ajar.swarm import (
        ENV_BLOCKER_KINDS,
        POLICY_REFUSAL_BLOCK_RE,
        ZERO_ATTEMPT_EXEMPT_ENV_BLOCKERS,
    )

    blocked_claims = conn.execute("SELECT * FROM claims WHERE status = 'blocked' ORDER BY created_at ASC").fetchall()
    zero_attempt_blocked = 0
    for bc in blocked_claims:
        cid = str(bc["claim_id"])
        breason = str(bc["blocker_reason"] or "")
        env_b = str(bc["env_blocker"] or "").strip() if "env_blocker" in bc.keys() else ""
        if POLICY_REFUSAL_BLOCK_RE.search(breason):
            g4_issues.append(
                f"Claim {cid} blocked via policy/refusal deferral ({breason[:90]!r}); re-dispatch via `ajar swarm fallback`."
            )
        if env_b not in ENV_BLOCKER_KINDS:
            g4_issues.append(
                f"Claim {cid} missing concrete --env-blocker ({', '.join(ENV_BLOCKER_KINDS)})."
            )
        fails = int(bc["failed_repro_count"] or 0)
        inst = int(bc["instrumented_since_fail"] or 0)
        if target_mode == "source" and fails == 0 and inst == 0 and env_b not in ZERO_ATTEMPT_EXEMPT_ENV_BLOCKERS:
            zero_attempt_blocked += 1

    if zero_attempt_blocked >= 3:
        g4_issues.append(
            f"Bulk zero-attempt claim blocking detected: {zero_attempt_blocked} source claims marked `blocked` with 0 reproduction attempts."
        )

    gates["G4_zero_skill_and_dry_rigor"] = {"passed": len(g4_issues) == 0, "issues": g4_issues}
    all_blockers.extend(f"[G4] {m}" for m in g4_issues)

    # --- G5: Stage-5 Converge (Orphaned Anomalies, Woken Open Doors, Invariant-Pair Guard Breaking & Multi-Primitive Chains) ---
    g5_issues: list[str] = []
    unexplained = conn.execute(
        "SELECT anomaly_id, locus, observation FROM anomalies WHERE status = 'unexplained'"
    ).fetchall()
    if unexplained:
        sample = ", ".join(f"{r['anomaly_id']}@{r['locus']}" for r in unexplained[:5])
        g5_issues.append(
            f"{len(unexplained)} execution anomaly(ies) remain unexplained ({sample}). "
            "Explain via `ajar anomaly explain` or consume in a claim/chain."
        )

    ready_doors = conn.execute(
        "SELECT door_id, anchor_locus FROM parked_doors WHERE status = 'ready'"
    ).fetchall()
    if ready_doors:
        sample = ", ".join(f"{r['door_id']}@{r['anchor_locus']}" for r in ready_doors[:4])
        g5_issues.append(
            f"{len(ready_doors)} woken Open Door(s) (`ready`) await chain verification (`ajar chain propose`): {sample}."
        )

    nonterminal_high_chains = conn.execute(
        """
        SELECT task_id, status, salience_score
        FROM tasks
        WHERE kind = 'chain' AND salience_score >= 95 AND status NOT IN ('done', 'dry')
        ORDER BY salience_score DESC, created_at ASC
        """
    ).fetchall()
    if nonterminal_high_chains:
        sample = ", ".join(
            f"{r['task_id']}[{r['status']}:{r['salience_score']}]"
            for r in nonterminal_high_chains[:5]
        )
        g5_issues.append(
            f"{len(nonterminal_high_chains)} high-salience chain task(s) remain nonterminal: {sample}."
        )

    prim_count = conn.execute("SELECT COUNT(*) AS c FROM primitives WHERE status != 'dry'").fetchone()["c"]
    guarded_prim_count = conn.execute(
        "SELECT COUNT(*) AS c FROM primitives WHERE status != 'dry' AND guarded_by_locus != '' AND chained = 0"
    ).fetchone()["c"]
    closed_chain_tasks = conn.execute(
        "SELECT COUNT(*) AS c FROM tasks WHERE kind = 'chain' AND status IN ('done', 'dry')"
    ).fetchone()["c"]
    open_chain_tasks = conn.execute(
        "SELECT COUNT(*) AS c FROM tasks WHERE kind = 'chain' AND status IN ('open', 'leased')"
    ).fetchone()["c"]
    needs_converge = int(prim_count) >= 2 or int(guarded_prim_count) >= 1
    if needs_converge and int(closed_chain_tasks) == 0 and not (stopping == "crown-jewel" and has_crown_jewel_win):
        if auto_enqueue_chain and int(open_chain_tasks) == 0:
            cid = new_id("task")
            now_iso = utc_now_iso()
            conn.execute(
                """
                INSERT INTO tasks(
                    task_id, kind, title, priority, status, salience_score, summary, created_at, updated_at
                ) VALUES (?, 'chain', 'Run Stage-5 Converge: evaluate invariant-pair guard breaks and multi-step chains', 'high', 'open', 75, ?, ?, ?)
                """,
                (
                    cid,
                    f"Auto-enqueued by G5: {prim_count} active primitives ({guarded_prim_count} guarded) and {len(finding_rows)} findings.",
                    now_iso,
                    now_iso,
                ),
            )
            g5_issues.append(
                f"Stage-5 Converge required ({prim_count} active primitives, {guarded_prim_count} guarded); enqueued chain task {cid}."
            )
        else:
            g5_issues.append(f"{prim_count} active primitives exist; complete open `chain` task before finishing.")

    gates["G5_anomalies_and_chains"] = {"passed": len(g5_issues) == 0, "issues": g5_issues}
    all_blockers.extend(f"[G5] {m}" for m in g5_issues)

    return {
        "passed": len(all_blockers) == 0,
        "stopping_criterion": stopping,
        "crown_jewel_reached": has_crown_jewel_win,
        "findings_count": len(finding_rows),
        "high_or_critical_findings": int(high_findings),
        "gates": gates,
        "blockers": all_blockers,
        "economics": compute_attribution_and_economics(conn),
    }
