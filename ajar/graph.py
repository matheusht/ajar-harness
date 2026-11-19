"""Component & Attack-Flow Graph Exporter (`ajar export-graph` — `Platform` whiteboard).

Compiles the SQLite run store (`surfaces`, `repomap_edges`, `tasks`, `primitives`,
`anomalies`, `findings`, `chains`, and `steers`) into a deterministic JSON graph
(`ajar-platform-graph/1`) so operators can inspect trust boundaries, verified guards,
active Steers, and multi-step exploit chains on a single canvas.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from ajar.db import list_rows, list_steers


def export_attack_flow_graph(conn: sqlite3.Connection) -> dict[str, Any]:
    """Export deterministic `ajar-platform-graph/1` nodes, edges, and coverage summary."""
    run_row = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
    run = dict(run_row) if run_row else {}

    surfaces = list_rows(conn, "SELECT * FROM surfaces ORDER BY priority ASC, surface_id ASC")
    primitives = list_rows(conn, "SELECT * FROM primitives ORDER BY primitive_id ASC")
    anomalies = list_rows(conn, "SELECT * FROM anomalies ORDER BY anomaly_id ASC")
    findings = list_rows(
        conn,
        """
        SELECT f.*, c.surface_id, c.remediation_state
        FROM findings f
        JOIN claims c ON f.claim_id = c.claim_id
        ORDER BY f.finding_id ASC
        """,
    )
    chains = list_rows(conn, "SELECT * FROM chains ORDER BY chain_id ASC")
    dry_tasks = list_rows(
        conn,
        "SELECT task_id, surface_id, locus, dry_control_locus, dry_control_reason FROM tasks WHERE status = 'dry' ORDER BY task_id ASC",
    )
    done_tasks = list_rows(
        conn,
        "SELECT task_id, surface_id FROM tasks WHERE status = 'done' ORDER BY task_id ASC",
    )
    repomap_edges = list_rows(
        conn,
        "SELECT src_file, dst_file, symbol, weight FROM repomap_edges ORDER BY weight DESC, src_file ASC LIMIT 200",
    )
    steers = list_steers(conn, active_only=True)

    finding_surfaces = {str(f["surface_id"]) for f in findings if f.get("surface_id")}
    dry_surfaces = {str(t["surface_id"]) for t in dry_tasks if t.get("surface_id")}
    done_surfaces = {str(t["surface_id"]) for t in done_tasks if t.get("surface_id")}

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    for s in surfaces:
        sid = str(s["surface_id"])
        if sid in finding_surfaces:
            cov = "confirmed_vulnerability"
        elif sid in dry_surfaces:
            cov = "guarded_dry"
        elif sid in done_surfaces:
            cov = "covered"
        else:
            cov = "open"
        nodes.append(
            {
                "id": sid,
                "node_type": "surface",
                "label": s["name"],
                "kind": s["kind"],
                "subsystem": s["subsystem"],
                "locus": s["locus"],
                "priority": s["priority"],
                "trust_boundary": s["trust_boundary"],
                "coverage_state": cov,
            }
        )

    for dt in dry_tasks:
        guard_id = f"guard:{dt['task_id']}"
        nodes.append(
            {
                "id": guard_id,
                "node_type": "verified_guard",
                "label": dt["dry_control_locus"],
                "locus": dt["dry_control_locus"],
                "reason": dt["dry_control_reason"],
            }
        )
        if dt.get("surface_id"):
            edges.append(
                {
                    "src": str(dt["surface_id"]),
                    "dst": guard_id,
                    "edge_type": "protected_by_guard",
                    "label": "dry guard",
                }
            )

    for p in primitives:
        pid = str(p["primitive_id"])
        nodes.append(
            {
                "id": pid,
                "node_type": "primitive",
                "label": f"{p['kind']} @ {p['locus']}",
                "subsystem": p["subsystem"],
                "locus": p["locus"],
                "preconditions": p["preconditions"],
                "postconditions": p["postconditions"],
                "guarded_by_locus": p.get("guarded_by_locus", ""),
                "chained": bool(p["chained"]),
            }
        )
        if p.get("surface_id"):
            edges.append(
                {
                    "src": str(p["surface_id"]),
                    "dst": pid,
                    "edge_type": "yields_primitive",
                    "label": p["kind"],
                }
            )
        if p.get("guarded_by_locus"):
            edges.append(
                {
                    "src": pid,
                    "dst": f"locus:{p['guarded_by_locus']}",
                    "edge_type": "guarded_by",
                    "label": p.get("guard_assumption") or "upstream guard",
                }
            )

    for a in anomalies:
        aid = str(a["anomaly_id"])
        nodes.append(
            {
                "id": aid,
                "node_type": "anomaly",
                "label": a["observation"][:80],
                "locus": a["locus"],
                "status": a["status"],
            }
        )
        if a.get("surface_id"):
            edges.append(
                {
                    "src": str(a["surface_id"]),
                    "dst": aid,
                    "edge_type": "exhibits_anomaly",
                    "label": a["status"],
                }
            )

    for f in findings:
        fid = str(f["finding_id"])
        nodes.append(
            {
                "id": fid,
                "node_type": "finding",
                "label": f["title"],
                "severity": f["severity"],
                "locus": f["locus"],
                "attribution": f["attribution"],
                "remediation_state": f["remediation_state"],
            }
        )
        if f.get("surface_id"):
            edges.append(
                {
                    "src": str(f["surface_id"]),
                    "dst": fid,
                    "edge_type": "confirmed_finding",
                    "label": f["severity"],
                }
            )

    for ch in chains:
        cid = str(ch["chain_id"])
        nodes.append(
            {
                "id": cid,
                "node_type": "chain",
                "label": ch["title"],
                "severity": ch["severity"],
                "verified": bool(ch["verified"]),
            }
        )
        try:
            steps = json.loads(ch["step_ids_json"] or "[]")
        except json.JSONDecodeError:
            steps = []
        for idx, step_id in enumerate(steps, start=1):
            edges.append(
                {
                    "src": str(step_id),
                    "dst": cid,
                    "edge_type": "chain_step",
                    "step_order": idx,
                }
            )

    for re_edge in repomap_edges:
        edges.append(
            {
                "src": f"file:{re_edge['src_file']}",
                "dst": f"file:{re_edge['dst_file']}",
                "edge_type": "symbol_call",
                "symbol": re_edge["symbol"],
                "weight": re_edge["weight"],
            }
        )

    epistemic_hooks = list_rows(conn, "SELECT * FROM epistemic_hooks ORDER BY created_at ASC")
    primitive_helpers = list_rows(
        conn,
        "SELECT helper_id, primitive_id, module_name, callable_name, provides_tags_json, verified FROM primitive_helpers ORDER BY created_at ASC",
    )
    tm_row = conn.execute("SELECT * FROM threat_models LIMIT 1").fetchone()
    threat_model = dict(tm_row) if tm_row else None
    threat_assumptions = list_rows(conn, "SELECT * FROM threat_assumptions ORDER BY created_at ASC")
    for ta in threat_assumptions:
        aid = str(ta["assumption_id"])
        nodes.append(
            {
                "id": aid,
                "node_type": "threat_assumption",
                "label": ta["assumption_text"][:80],
                "subsystem": ta["subsystem"],
                "trust_boundary": ta["trust_boundary"],
                "status": ta["status"],
                "evidence_ref": ta["evidence_ref"],
            }
        )
        if ta.get("dependent_surface_id"):
            edges.append(
                {
                    "src": aid,
                    "dst": str(ta["dependent_surface_id"]),
                    "edge_type": "assumes_boundary_for",
                    "label": ta["status"],
                }
            )
    cov_row = conn.execute(
        "SELECT COUNT(*) AS spans, COUNT(DISTINCT rel_path) AS files FROM coverage_spans"
    ).fetchone()

    return {
        "schema": "ajar-platform-graph/1",
        "run_id": run.get("run_id", ""),
        "target_path": run.get("target_path", ""),
        "target_mode": run.get("target_mode", "source"),
        "diff_range": run.get("diff_range", ""),
        "commitment_hash": run.get("commitment_hash", ""),
        "threat_model": threat_model,
        "threat_assumptions": threat_assumptions,
        "nodes": nodes,
        "edges": edges,
        "active_steers": steers,
        "epistemic_hooks": epistemic_hooks,
        "primitive_helpers": primitive_helpers,
        "summary": {
            "surfaces_total": len(surfaces),
            "surfaces_with_findings": len(finding_surfaces),
            "surfaces_guarded_dry": len(dry_surfaces),
            "primitives_total": len(primitives),
            "primitive_helpers_verified": sum(1 for h in primitive_helpers if h["verified"]),
            "unchained_primitives": sum(1 for p in primitives if not p["chained"]),
            "unexplained_anomalies": sum(1 for a in anomalies if a["status"] == "unexplained"),
            "confirmed_findings": len(findings),
            "verified_chains": sum(1 for c in chains if c["verified"]),
            "active_steers": len(steers),
            "epistemic_hooks_total": len(epistemic_hooks),
            "threat_assumptions_total": len(threat_assumptions),
            "threat_assumptions_violated": sum(1 for ta in threat_assumptions if ta["status"] == "violated"),
            "coverage_spans_total": int(cov_row["spans"] or 0),
            "coverage_files_total": int(cov_row["files"] or 0),
        },
    }
