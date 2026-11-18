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

from ajar.db import new_id, utc_now_iso


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
    budget_usd = float(run["budget_usd"] if run else 40.0)
    code_quote_usd = float(run["code_quote_usd"] if run else 10.0)
    cost_usd_per_kloc = round((total_usd / (loc / 1000.0)), 4) if loc > 0 else 0.0

    return {
        "in_scope_loc": loc,
        "code_quote_usd": code_quote_usd,
        "budget_usd": budget_usd,
        "total_spend_usd": total_usd,
        "explore_spend_usd": round(float(spend_row["explore_usd"] or 0.0), 4),
        "verify_spend_usd": round(float(spend_row["verify_usd"] or 0.0), 4),
        "tokens_in": int(spend_row["tokens_in"] or 0),
        "tokens_out": int(spend_row["tokens_out"] or 0),
        "cost_usd_per_kloc": cost_usd_per_kloc,
        "within_code_cogs_target": (cost_usd_per_kloc <= 2.0) if loc > 0 else True,
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


def check_all_gates(
    conn: sqlite3.Connection,
    *,
    target_dir: pathlib.Path | None = None,
    auto_enqueue_chain: bool = True,
) -> dict[str, Any]:
    """Evaluate gates `G1` through `G5` and return structured pass/blocker details."""
    run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
    if run is None:
        return {"passed": False, "gates": {}, "blockers": ["Run metadata missing in run.db."]}

    stopping = str(run["stopping_criterion"] or "exhaustive-high")
    target_mode = str(run["target_mode"] or "source")
    gates: dict[str, dict[str, Any]] = {}
    all_blockers: list[str] = []

    # --- G1: Surface & Task Coverage ---
    g1_issues: list[str] = []
    surface_count = conn.execute("SELECT COUNT(*) AS c FROM surfaces").fetchone()["c"]
    high_findings = conn.execute(
        "SELECT COUNT(*) AS c FROM findings WHERE severity IN ('critical', 'high')"
    ).fetchone()["c"]

    if stopping == "first-verified-high" and high_findings >= 1:
        leased_active = conn.execute(
            "SELECT COUNT(*) AS c FROM tasks WHERE status = 'leased' AND kind IN ('falsify', 'reproduce')"
        ).fetchone()["c"]
        if leased_active > 0:
            g1_issues.append(f"{leased_active} active verification task(s) still leased.")
    else:
        if surface_count == 0:
            g1_issues.append("No surfaces mapped yet (`ajar surface add`).")
        open_high = conn.execute(
            """
            SELECT t.task_id, t.kind, t.title
            FROM tasks t
            LEFT JOIN surfaces s ON t.surface_id = s.surface_id
            WHERE t.status IN ('open', 'leased')
              AND (t.priority IN ('critical', 'high') OR s.priority IN ('critical', 'high'))
            """
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
                  WHERE t.surface_id = s.surface_id AND t.status IN ('done', 'dry')
              )
            """
        ).fetchall()
        if uncovered_surfaces:
            sample = ", ".join(f"{r['surface_id']}({r['name']})" for r in uncovered_surfaces[:5])
            g1_issues.append(f"{len(uncovered_surfaces)} critical/high surface(s) have zero completed tasks: {sample}.")

        if stopping == "first-verified-high" and high_findings == 0 and surface_count > 0 and not open_high:
            # Exhausted all high tasks dry without finding a high bug: valid dry completion!
            pass

    gates["G1_surface_coverage"] = {"passed": len(g1_issues) == 0, "issues": g1_issues}
    all_blockers.extend(f"[G1] {m}" for m in g1_issues)

    # --- G2: Zero Unresolved Claims ---
    g2_issues: list[str] = []
    unresolved_claims = conn.execute(
        """
        SELECT claim_id, status, title FROM claims
        WHERE status IN ('proposed', 'survived_falsify', 'needs_instrumentation')
        """
    ).fetchall()
    if unresolved_claims:
        sample = ", ".join(f"{r['claim_id']}[{r['status']}]" for r in unresolved_claims[:6])
        g2_issues.append(f"{len(unresolved_claims)} claim(s) still unresolved: {sample}.")
    gates["G2_claim_resolution"] = {"passed": len(g2_issues) == 0, "issues": g2_issues}
    all_blockers.extend(f"[G2] {m}" for m in g2_issues)

    # --- G3: 4-Arm Causal Proof + Fresh Falsifier Separation ---
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

    gates["G4_zero_skill_and_dry_rigor"] = {"passed": len(g4_issues) == 0, "issues": g4_issues}
    all_blockers.extend(f"[G4] {m}" for m in g4_issues)

    # --- G5: Orphaned Anomalies & Unchained Primitives ---
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

    prim_count = conn.execute("SELECT COUNT(*) AS c FROM primitives").fetchone()["c"]
    closed_chain_tasks = conn.execute(
        "SELECT COUNT(*) AS c FROM tasks WHERE kind = 'chain' AND status IN ('done', 'dry')"
    ).fetchone()["c"]
    open_chain_tasks = conn.execute(
        "SELECT COUNT(*) AS c FROM tasks WHERE kind = 'chain' AND status IN ('open', 'leased')"
    ).fetchone()["c"]
    if int(prim_count) >= 2 and int(closed_chain_tasks) == 0:
        if auto_enqueue_chain and int(open_chain_tasks) == 0:
            cid = new_id("task")
            now_iso = utc_now_iso()
            conn.execute(
                """
                INSERT INTO tasks(
                    task_id, kind, title, priority, status, salience_score, summary, created_at, updated_at
                ) VALUES (?, 'chain', 'Evaluate composition chains across discovered primitives', 'high', 'open', 75, ?, ?, ?)
                """,
                (cid, f"Auto-enqueued by G5: {prim_count} verified primitives exist.", now_iso, now_iso),
            )
            g5_issues.append(
                f"{prim_count} primitives exist with zero completed chain analysis; enqueued chain task {cid}."
            )
        else:
            g5_issues.append(f"{prim_count} primitives exist; complete open `chain` task before finishing.")

    gates["G5_anomalies_and_chains"] = {"passed": len(g5_issues) == 0, "issues": g5_issues}
    all_blockers.extend(f"[G5] {m}" for m in g5_issues)

    return {
        "passed": len(all_blockers) == 0,
        "stopping_criterion": stopping,
        "findings_count": len(finding_rows),
        "high_or_critical_findings": int(high_findings),
        "gates": gates,
        "blockers": all_blockers,
        "economics": compute_attribution_and_economics(conn),
    }
