"""Evidence-locked ASD-STE100 vulnerability report renderer (`ajar report`).

Strictly separates confirmed (`reproduced`) findings and verified `chains` from
disproved research candidates (`DEC-0045` / `DEC-0048`), attaches pre-submit
commitment hashes (`ajar-research-ledger/1`), records run-derived attribution
(`DEC-0071`), and summarizes `Code` unit economics (`DEC-0122`).
"""

from __future__ import annotations

import sqlite3
from typing import Any

from ajar.db import list_rows, list_steers
from ajar.gates import check_all_gates
from ajar.redact import scrub_text


def build_report_data(
    conn: sqlite3.Connection,
    *,
    include_rejected_appendix: bool = False,
) -> dict[str, Any]:
    run_row = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
    run = dict(run_row) if run_row else {}

    findings = list_rows(
        conn,
        """
        SELECT f.*, c.falsifier_worker_id, c.falsification_prediction,
               c.customer_state, c.remediation_state
        FROM findings f
        JOIN claims c ON f.claim_id = c.claim_id
        ORDER BY CASE f.severity
            WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END,
            f.created_at ASC
        """,
    )
    chains = list_rows(conn, "SELECT * FROM chains WHERE verified = 1 ORDER BY created_at ASC")
    surfaces = list_rows(conn, "SELECT * FROM surfaces ORDER BY priority ASC, created_at ASC")
    dry_controls = list_rows(
        conn,
        "SELECT task_id, title, dry_control_locus, dry_control_reason FROM tasks WHERE status = 'dry' ORDER BY updated_at ASC",
    )
    blocked_claims = list_rows(
        conn,
        "SELECT claim_id, title, locus, blocker_reason FROM claims WHERE status = 'blocked'",
    )
    active_steers = list_steers(conn, active_only=True)
    patch_verifications = list_rows(
        conn,
        "SELECT verification_id, finding_id, claim_id, passed, caller_audit, sibling_audit, arm9_revert_poc_json, created_at FROM patch_verifications ORDER BY created_at ASC",
    )
    epistemic_hooks = list_rows(
        conn,
        "SELECT hook_id, hook_code, subsystem, target_locus, status, leases_seen FROM epistemic_hooks ORDER BY created_at ASC",
    )
    primitive_helpers = list_rows(
        conn,
        "SELECT helper_id, primitive_id, module_name, callable_name, provides_tags_json, verified FROM primitive_helpers ORDER BY created_at ASC",
    )
    coverage_spans = list_rows(
        conn,
        "SELECT span_id, task_id, rel_path, start_line, end_line, file_sha256 FROM coverage_spans ORDER BY rel_path ASC, start_line ASC",
    )
    claim_counts = {
        r["status"]: int(r["c"])
        for r in conn.execute("SELECT status, COUNT(*) AS c FROM claims GROUP BY status").fetchall()
    }
    gates = check_all_gates(conn, auto_enqueue_chain=False)

    data: dict[str, Any] = {
        "schema": "ajar-report/3",
        "run_id": run.get("run_id", ""),
        "target_path": run.get("target_path", ""),
        "target_mode": run.get("target_mode", "source"),
        "diff_range": run.get("diff_range", ""),
        "goal": run.get("goal", ""),
        "status": run.get("status", ""),
        "commitment_hash": run.get("commitment_hash", ""),
        "created_at": run.get("created_at", ""),
        "finished_at": run.get("finished_at"),
        "findings": findings,
        "verified_chains": chains,
        "patch_verifications": patch_verifications,
        "epistemic_hooks": epistemic_hooks,
        "primitive_helpers": primitive_helpers,
        "coverage_spans": coverage_spans,
        "active_steers": active_steers,
        "surfaces_covered": surfaces,
        "dry_controls": dry_controls,
        "blocked_items": blocked_claims,
        "claim_summary_counts": claim_counts,
        "gates": gates["gates"],
        "gates_passed": gates["passed"],
        "economics": gates["economics"],
    }
    if include_rejected_appendix:
        data["rejected_claims_appendix"] = list_rows(
            conn,
            """
            SELECT claim_id, title, locus, status, falsify_notes, falsify_control_locus
            FROM claims
            WHERE status IN ('falsified', 'rejected_repro', 'duplicate_root_cause', 'config_gated')
            ORDER BY updated_at ASC
            """,
        )
    return data


def render_markdown_report(
    conn: sqlite3.Connection,
    *,
    include_rejected_appendix: bool = False,
) -> str:
    data = build_report_data(conn, include_rejected_appendix=include_rejected_appendix)
    econ = data["economics"]
    cap_label = (
        "uncapped_research"
        if econ.get("pricing_mode") == "uncapped_research"
        else f"${econ['cogs_cap_usd']:.2f}"
    )
    lines: list[str] = [
        f"# Security Verification Report — `{data['run_id']}`",
        "",
        f"- **Target:** `{data['target_path']}` (`{data['target_mode']}`)",
        f"- **Run Status:** `{data['status']}` (Closeout gates passed: `{data['gates_passed']}`)",
        f"- **Commitment Hash (`ajar-research-ledger/1`):** `{data['commitment_hash']}`",
        f"- **In-Scope Code Size:** `{econ['in_scope_loc']}` LoC (`Code` cap quote: `${econ['code_quote_usd']:.2f}`, COGS cap: `{cap_label}`)",
        f"- **Measured Compute Spend:** `${econ['total_spend_usd']:.4f}` (`${econ['cost_usd_per_kloc']:.4f} / 1K LoC`)",
        f"- **Autonomy Checks:** `research_independence_pass={econ['research_independence_pass']}`, "
        f"`product_operability_pass={econ['product_operability_pass']}`",
        "",
        "## 1. Confirmed Findings",
        "",
    ]

    findings = data["findings"]
    if not findings:
        lines.append("No confirmed vulnerabilities reproduced within the tested scope.")
        lines.append("")
    else:
        for idx, f in enumerate(findings, start=1):
            lines.extend(
                [
                    f"### 1.{idx} [{str(f['severity']).upper()}] {f['title']} (`{f['finding_id']}`)",
                    "",
                    f"- **Location:** `{f['locus']}`",
                    f"- **Attribution:** `{f['attribution']}`",
                    f"- **Remediation State:** `{f['remediation_state']}`",
                    f"- **Claim & Independent Skeptic:** `{f['claim_id']}` (verified by `{f['falsifier_worker_id']}`)",
                    f"- **Root Cause:** {f['root_cause']}",
                    f"- **Reproduction Command (Arm 1):** `{f['poc_cmd']}`",
                    f"- **Benign Control Command (Arm 2):** `{f['control_cmd']}`",
                ]
            )
            if f.get("ub_divergence_class"):
                lines.append(f"- **Release UB Differential (Arms 5A/5B):** `{f['ub_divergence_class']}`")
            lines.append("")
            if f.get("micropatch_diff"):
                lines.extend(
                    [
                        "**Verified Counterfactual Micro-Patch (Arms 3 & 4):**",
                        "",
                        "```diff",
                        str(f["micropatch_diff"]).rstrip(),
                        "```",
                        "",
                    ]
                )

    if data["verified_chains"]:
        lines.extend(["## 2. Verified Multi-Step Chains", ""])
        for c in data["verified_chains"]:
            lines.append(
                f"- **[{str(c['severity']).upper()}] {c['title']} (`{c['chain_id']}`):** "
                f"Steps `{c['step_ids_json']}` | Ablation `{c.get('ablation_matrix_json', '[]')}` | PoC: `{c['e2e_poc_cmd']}`"
            )
        lines.append("")

    if data["active_steers"]:
        lines.extend(["## Workspace Steers Applied", ""])
        for st in data["active_steers"]:
            lines.append(
                f"- `{st['steer_id']}` [`{st['scope']}:{st['target_filter'] or '*'}`] (`{st['touch_kind']}` by `{st['author']}`): {st['rule_text']}"
            )
        lines.append("")

    lines.extend(["## 3. Audited Surfaces and Verified Guards (`dry`)", ""])
    if not data["dry_controls"]:
        lines.append("No separate `dry` guard closures recorded.")
    else:
        for d in data["dry_controls"]:
            lines.append(f"- `{d['dry_control_locus']}` (`{d['task_id']}`): {d['dry_control_reason']}")
    lines.append("")

    rejected_count = (
        data["claim_summary_counts"].get("falsified", 0)
        + data["claim_summary_counts"].get("rejected_repro", 0)
        + data["claim_summary_counts"].get("duplicate_root_cause", 0)
    )
    lines.extend(
        [
            "## 4. Hypothesis Funnel and Scope Limits",
            "",
            f"- **Confirmed findings:** `{len(findings)}`",
            f"- **Disproved or deduplicated hypotheses withheld from findings:** `{rejected_count}`",
            f"- **Blocked items:** `{len(data['blocked_items'])}`",
            "- **Scope notice:** A dry path records the concrete guard inspected at this revision; it does not claim proof that zero bugs exist.",
            "",
        ]
    )

    if data["blocked_items"]:
        lines.extend(["### Stated Blockers", ""])
        for b in data["blocked_items"]:
            lines.append(f"- `{b['claim_id']}` @ `{b['locus']}`: {b['blocker_reason'] or b['title']}")
        lines.append("")

    if include_rejected_appendix and data.get("rejected_claims_appendix"):
        lines.extend(["## Appendix: Disproved Research Hypotheses", ""])
        for rc in data["rejected_claims_appendix"]:
            lines.append(
                f"- `{rc['claim_id']}` [`{rc['status']}`] @ `{rc['locus']}`: {rc['falsify_notes'][:160]}"
            )
        lines.append("")

    return scrub_text("\n".join(lines))
