"""Component & Attack-Flow Graph Exporter (`ajar export-graph` — `Platform` whiteboard).

Compiles the SQLite run store (`surfaces`, `repomap_edges`, `tasks`, `primitives`,
`anomalies`, `claims`, `findings`, `chains`, `patch_verifications`, `crown_jewels`,
`parked_doors`, `steers`, `epistemic_hooks`, `primitive_helpers`, and `threat_models`)
into a deterministic, scrubbed JSON graph:
- `ajar-platform-graph/2` (default): zero dangling edges, visibility-scoped local-path
  sanitization (`internal_full`, `customer_private`, `public_disclosure`), concrete
  `guard_locus` / `crown_jewel` / `open_door` nodes, ordered `chain_transition` edges,
  separated `code_graph.repomap_edges`, full 4-arm/9-arm `findings_detail`,
  `chains_detail`, optional bounded `code_snippets`, and `verification_summary`.
- `ajar-platform-graph/1` (`--schema v1`): backward-compatible legacy projection.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sqlite3
import subprocess
from typing import Any, Mapping, Sequence

from ajar import EXIT_USER_ERROR
from ajar.db import list_rows, list_steers
from ajar.domain.models import AjarError
from ajar.gates import check_all_gates
from ajar.redact import scrub_json_value, scrub_text, scrubbed_subprocess_env
from ajar.store import infer_subsystem, parse_tag_list

VALID_GRAPH_SCHEMAS: tuple[str, ...] = ("v1", "v2")
VALID_GRAPH_VISIBILITIES: tuple[str, ...] = (
    "internal_full",
    "customer_private",
    "public_disclosure",
)

SCOPE_NOTICE = (
    "Verification results cover only the audited revision, mapped surfaces, and executed checks; "
    "a dry guard or passing gate records concrete controls inspected and does not claim proof of complete security."
)

MAX_CODE_SNIPPETS = 32
SNIPPET_CONTEXT_LINES = 6
MAX_SNIPPET_LINES = 25
MAX_SNIPPET_CHARS = 2048

_LOCAL_PATH_BODY = (
    r"(?:"
    r"/(?:home|Users)/[A-Za-z0-9._-]+(?:/[^\s'\",;:)}\]]*)?"
    r"|/(?:private/)?(?:tmp|var/tmp|var/folders)(?:/[^\s'\",;:)}\]]*)?"
    r"|/root(?:/[^\s'\",;:)}\]]*)?"
    r"|/shared/user(?:/[^\s'\",;:)}\]]*)?"
    r")"
)
_FILE_URI_LOCAL_PATH_RE = re.compile(r"file://" + _LOCAL_PATH_BODY)
_FLAG_LOCAL_PATH_RE = re.compile(r"((?:^|[\s'\"(=,;])-[A-Za-z])" + _LOCAL_PATH_BODY)
_ABS_LOCAL_PATH_RE = re.compile(r"(?<![A-Za-z0-9_.+/-])" + _LOCAL_PATH_BODY)
_GIT_SLUG_RE = re.compile(r"[:/]([A-Za-z0-9._-]+/[A-Za-z0-9._-]+?)(?:\.git)?/?$")
_SEVERITY_RANK: dict[str, int] = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _safe_json_loads(raw: Any, default: Any) -> Any:
    if raw is None or raw == "":
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        parsed = json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default
    return parsed


def _infer_repo_slug(explicit_slug: str, target_path: str) -> str:
    clean_explicit = (explicit_slug or "").strip()
    if clean_explicit:
        return clean_explicit
    tpath = pathlib.Path(target_path) if target_path else None
    if tpath is not None and tpath.is_dir() and (tpath / ".git").exists():
        try:
            cp = subprocess.run(
                ["git", "-C", str(tpath), "config", "--get", "remote.origin.url"],
                capture_output=True,
                text=True,
                timeout=2,
                env=scrubbed_subprocess_env(),
                check=False,
            )
            url = (cp.stdout or "").strip()
            if url and not url.startswith(("/", "file://", "./", "../")):
                # Strip any embedded URL credentials before parsing owner/repo.
                sanitized_url = re.sub(r"://[^/@]+@", "://", url)
                m = _GIT_SLUG_RE.search(sanitized_url)
                if m:
                    return m.group(1)
        except (OSError, subprocess.SubprocessError):
            pass
    if tpath is not None and tpath.name:
        return tpath.name
    return "unknown-target"


def _resolve_head_sha(run: dict[str, Any], target_path: str) -> str:
    existing = str(run.get("head_sha") or "").strip()
    if existing:
        return existing
    tpath = pathlib.Path(target_path) if target_path else None
    if tpath is not None and tpath.is_dir() and (tpath / ".git").exists():
        try:
            cp = subprocess.run(
                ["git", "-C", str(tpath), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=2,
                env=scrubbed_subprocess_env(),
                check=False,
            )
            sha = (cp.stdout or "").strip()
            if cp.returncode == 0 and sha:
                return sha
        except (OSError, subprocess.SubprocessError):
            pass
    return ""


def _collect_local_roots(
    target_path: str,
    workspace_path: str,
    conn: sqlite3.Connection | None = None,
) -> tuple[list[str], list[str]]:
    target_roots: list[str] = []
    other_roots: list[str] = []

    def _add_path_variants(raw: str, bucket: list[str]) -> None:
        s = (raw or "").strip().rstrip("/")
        if not s or len(s) <= 1:
            return
        if s not in bucket:
            bucket.append(s)
        try:
            res = str(pathlib.Path(s).resolve()).rstrip("/")
            if res and len(res) > 1 and res not in bucket:
                bucket.append(res)
        except OSError:
            pass

    _add_path_variants(target_path, target_roots)
    _add_path_variants(workspace_path, other_roots)
    if workspace_path:
        ws_parent = pathlib.Path(workspace_path).parent
        if ws_parent.name:
            _add_path_variants(str(ws_parent), other_roots)
    if conn is not None:
        try:
            for db_row in conn.execute("PRAGMA database_list").fetchall():
                db_file = str(db_row[2] or "").strip()
                if not db_file or db_file == ":memory:":
                    continue
                run_dir = pathlib.Path(db_file).parent
                _add_path_variants(str(run_dir), other_roots)
                if run_dir.parent.name == "runs" and run_dir.parent.parent.name:
                    _add_path_variants(str(run_dir.parent.parent), other_roots)
        except sqlite3.Error:
            pass
    ajar_home_env = os.environ.get("AJAR_HOME", "").strip()
    if ajar_home_env:
        _add_path_variants(ajar_home_env, other_roots)
    try:
        home_s = str(pathlib.Path.home()).rstrip("/")
        if home_s and len(home_s) > 1:
            _add_path_variants(home_s, other_roots)
    except RuntimeError:
        pass

    target_roots.sort(key=len, reverse=True)
    other_roots.sort(key=len, reverse=True)
    return target_roots, other_roots


def _sanitize_external_text(text: str, *, target_roots: Sequence[str], other_roots: Sequence[str]) -> str:
    if not text:
        return text
    out = text
    for root in target_roots:
        out = out.replace("file://" + root + "/", "")
        out = out.replace("file://" + root, "<REPO>")
        out = out.replace(root + "/", "")
        out = out.replace(root, "<REPO>")
    for root in other_roots:
        out = out.replace("file://" + root + "/", "<RUN_DIR>/")
        out = out.replace("file://" + root, "<RUN_DIR>")
        out = out.replace(root + "/", "<RUN_DIR>/")
        out = out.replace(root, "<RUN_DIR>")
    out = _FILE_URI_LOCAL_PATH_RE.sub("<REDACTED_LOCAL_PATH>", out)
    out = _FLAG_LOCAL_PATH_RE.sub(r"\1<REDACTED_LOCAL_PATH>", out)
    out = _ABS_LOCAL_PATH_RE.sub("<REDACTED_LOCAL_PATH>", out)
    return out


def _sanitize_external_paths(value: Any, *, target_roots: Sequence[str], other_roots: Sequence[str]) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _sanitize_external_text(value, target_roots=target_roots, other_roots=other_roots)
    if isinstance(value, Mapping):
        return {
            _sanitize_external_text(str(k), target_roots=target_roots, other_roots=other_roots): _sanitize_external_paths(
                v, target_roots=target_roots, other_roots=other_roots
            )
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize_external_paths(item, target_roots=target_roots, other_roots=other_roots) for item in value]
    return _sanitize_external_text(str(value), target_roots=target_roots, other_roots=other_roots)


def _parse_locus_span(locus: str) -> tuple[str, int, int]:
    raw = (locus or "").strip().lstrip("./")
    if not raw:
        return ("", 0, 0)
    if ":" not in raw:
        return (raw, 1, 1)
    file_part, line_part = raw.split(":", 1)
    m = re.match(r"(\d+)(?:\s*-\s*(\d+))?", line_part.strip())
    if not m:
        return (file_part.strip(), 1, 1)
    start = max(1, int(m.group(1)))
    end = max(start, int(m.group(2))) if m.group(2) else start
    return (file_part.strip(), start, end)


def _extract_bounded_code_snippets(
    target_dir: pathlib.Path | None,
    loci: Sequence[str],
) -> list[dict[str, Any]]:
    if target_dir is None or not target_dir.is_dir():
        return []
    root_resolved = target_dir.resolve()
    snippets: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, int, int]] = set()

    for raw_locus in loci:
        if len(snippets) >= MAX_CODE_SNIPPETS:
            break
        rel_file, hl_start, hl_end = _parse_locus_span(raw_locus)
        if not rel_file or rel_file.startswith("/"):
            continue
        candidate = (root_resolved / rel_file).resolve()
        try:
            rel_clean = candidate.relative_to(root_resolved).as_posix()
        except ValueError:
            continue
        if not candidate.is_file():
            continue
        try:
            raw_bytes = candidate.read_bytes()
        except OSError:
            continue
        if b"\x00" in raw_bytes[:4096]:
            continue
        lines = raw_bytes.decode("utf-8", errors="replace").splitlines()
        if not lines:
            continue
        clamped_start = min(max(1, hl_start), len(lines))
        clamped_end = min(max(clamped_start, hl_end), len(lines))
        win_start = max(1, clamped_start - SNIPPET_CONTEXT_LINES)
        win_end = min(len(lines), clamped_end + SNIPPET_CONTEXT_LINES)
        if (win_end - win_start + 1) > MAX_SNIPPET_LINES:
            win_end = min(len(lines), win_start + MAX_SNIPPET_LINES - 1)

        dedup_key = (rel_clean, win_start, win_end)
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        numbered_lines = [
            f"{ln}: {lines[ln - 1]}"
            for ln in range(win_start, win_end + 1)
        ]
        code_text = scrub_text("\n".join(numbered_lines))
        truncated = False
        if len(code_text) > MAX_SNIPPET_CHARS:
            code_text = code_text[:MAX_SNIPPET_CHARS]
            truncated = True

        snippets.append(
            {
                "locus": raw_locus.strip(),
                "rel_path": rel_clean,
                "start_line": win_start,
                "end_line": win_end,
                "highlight_start": clamped_start,
                "highlight_end": clamped_end,
                "truncated": truncated,
                "code": code_text,
            }
        )
    return snippets


def _summarize_arm(arm: Any, *, visibility: str) -> dict[str, Any]:
    data = arm if isinstance(arm, dict) else {}
    out: dict[str, Any] = {
        "arm_passed": bool(data.get("arm_passed", False)),
        "exit_code": data.get("exit_code"),
        "defect_hits": data.get("defect_hits"),
        "trials": data.get("trials"),
        "timed_out": bool(data.get("timed_out", False)),
    }
    if visibility != "public_disclosure":
        stdout_raw = str(data.get("stdout") or "")
        stderr_raw = str(data.get("stderr") or "")
        if stdout_raw:
            out["stdout_excerpt"] = stdout_raw[:500]
        if stderr_raw:
            out["stderr_excerpt"] = stderr_raw[:500]
    return out


def _export_v1_graph(
    conn: sqlite3.Connection,
    *,
    visibility: str,
) -> dict[str, Any]:
    """Export backward-compatible `ajar-platform-graph/1` JSON structure."""
    run_row = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
    run = dict(run_row) if run_row else {}
    raw_target_path = str(run.get("target_path", ""))
    raw_workspace_path = str(run.get("workspace_path", ""))

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
        steps = _safe_json_loads(ch["step_ids_json"], [])
        if not isinstance(steps, list):
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

    payload: dict[str, Any] = {
        "schema": "ajar-platform-graph/1",
        "run_id": run.get("run_id", ""),
        "target_path": raw_target_path if visibility == "internal_full" else "",
        "target_mode": run.get("target_mode", "source"),
        "diff_range": run.get("diff_range", ""),
        "commitment_hash": run.get("commitment_hash", ""),
        "threat_model": threat_model,
        "threat_assumptions": threat_assumptions,
        "nodes": nodes,
        "edges": edges,
        "active_steers": steers if visibility != "public_disclosure" else [],
        "epistemic_hooks": epistemic_hooks if visibility == "internal_full" else [],
        "primitive_helpers": primitive_helpers if visibility != "public_disclosure" else [],
        "summary": {
            "surfaces_total": len(surfaces),
            "surfaces_with_findings": len(finding_surfaces),
            "surfaces_guarded_dry": len(dry_surfaces),
            "primitives_total": len(primitives),
            "primitive_helpers_verified": sum(1 for h in primitive_helpers if h["verified"]),
            "unchained_primitives": sum(
                1 for p in primitives if not p["chained"] and p.get("status", "active") != "dry"
            ),
            "unexplained_anomalies": sum(1 for a in anomalies if a["status"] == "unexplained"),
            "confirmed_findings": len(findings),
            "verified_chains": sum(1 for c in chains if c["verified"]),
            "active_steers": len(steers) if visibility != "public_disclosure" else 0,
            "epistemic_hooks_total": len(epistemic_hooks) if visibility == "internal_full" else 0,
            "threat_assumptions_total": len(threat_assumptions),
            "threat_assumptions_violated": sum(1 for ta in threat_assumptions if ta["status"] == "violated"),
            "coverage_spans_total": int(cov_row["spans"] or 0),
            "coverage_files_total": int(cov_row["files"] or 0),
        },
    }
    if visibility in ("customer_private", "public_disclosure"):
        t_roots, o_roots = _collect_local_roots(raw_target_path, raw_workspace_path, conn=conn)
        payload = _sanitize_external_paths(payload, target_roots=t_roots, other_roots=o_roots)
    scrubbed = scrub_json_value(payload)
    assert isinstance(scrubbed, dict)
    return scrubbed


def _export_v2_graph(
    conn: sqlite3.Connection,
    *,
    visibility: str,
    include_snippets: bool,
    repo_slug: str,
) -> dict[str, Any]:
    """Export `ajar-platform-graph/2` with 0 dangling edges and full proof projections."""
    run_row = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
    run = dict(run_row) if run_row else {}
    raw_target_path = str(run.get("target_path") or "")
    raw_workspace_path = str(run.get("workspace_path") or "")
    target_dir = pathlib.Path(raw_target_path) if raw_target_path else None
    resolved_slug = _infer_repo_slug(repo_slug, raw_target_path)
    resolved_head_sha = _resolve_head_sha(run, raw_target_path)

    run_obj: dict[str, Any] = {
        "run_id": str(run.get("run_id") or ""),
        "repo_slug": resolved_slug,
        "target_mode": str(run.get("target_mode") or "source"),
        "campaign_phase": str(run.get("campaign_phase") or "hunt"),
        "stopping_criterion": str(run.get("stopping_criterion") or "exhaustive-high"),
        "status": str(run.get("status") or ""),
        "diff_range": str(run.get("diff_range") or ""),
        "base_sha": str(run.get("base_sha") or ""),
        "head_sha": resolved_head_sha,
        "commitment_hash": str(run.get("commitment_hash") or ""),
        "created_at": str(run.get("created_at") or ""),
        "finished_at": run.get("finished_at"),
    }
    if visibility == "internal_full":
        run_obj["target_path"] = raw_target_path
        run_obj["workspace_path"] = raw_workspace_path
        run_obj["workspace_mode"] = str(run.get("workspace_mode") or "")
        run_obj["parent_run_id"] = str(run.get("parent_run_id") or "")

    surfaces = list_rows(conn, "SELECT * FROM surfaces ORDER BY priority ASC, surface_id ASC")
    primitives = list_rows(conn, "SELECT * FROM primitives ORDER BY primitive_id ASC")
    anomalies = list_rows(conn, "SELECT * FROM anomalies ORDER BY anomaly_id ASC")
    findings = list_rows(
        conn,
        """
        SELECT f.*, c.surface_id, c.proposer_worker_id, c.falsifier_worker_id,
               c.customer_state, c.remediation_state
        FROM findings f
        JOIN claims c ON f.claim_id = c.claim_id
        ORDER BY f.finding_id ASC
        """,
    )
    chains = list_rows(conn, "SELECT * FROM chains ORDER BY chain_id ASC")
    crown_jewels = list_rows(conn, "SELECT * FROM crown_jewels ORDER BY created_at ASC, jewel_id ASC")
    open_doors = list_rows(conn, "SELECT * FROM parked_doors ORDER BY created_at ASC, door_id ASC")
    patch_verifications = list_rows(
        conn,
        "SELECT * FROM patch_verifications ORDER BY passed DESC, created_at DESC, verification_id DESC",
    )
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
        "SELECT src_file, dst_file, symbol, weight FROM repomap_edges ORDER BY weight DESC, src_file ASC, dst_file ASC LIMIT 200",
    )
    sym_files_rows = conn.execute("SELECT DISTINCT rel_path FROM repomap_symbols ORDER BY rel_path ASC").fetchall()
    sym_count_row = conn.execute("SELECT COUNT(*) AS c FROM repomap_symbols").fetchone()
    steers = list_steers(conn, active_only=True)
    epistemic_hooks = list_rows(conn, "SELECT * FROM epistemic_hooks ORDER BY created_at ASC")
    primitive_helpers = list_rows(
        conn,
        "SELECT helper_id, primitive_id, module_name, callable_name, provides_tags_json, verified FROM primitive_helpers ORDER BY created_at ASC",
    )
    tm_row = conn.execute("SELECT * FROM threat_models LIMIT 1").fetchone()
    threat_model = dict(tm_row) if tm_row else None
    threat_assumptions = list_rows(conn, "SELECT * FROM threat_assumptions ORDER BY created_at ASC")

    finding_surfaces = {str(f["surface_id"]) for f in findings if f.get("surface_id")}
    dry_surfaces = {str(t["surface_id"]) for t in dry_tasks if t.get("surface_id")}
    done_surfaces = {str(t["surface_id"]) for t in done_tasks if t.get("surface_id")}

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    node_by_id: dict[str, dict[str, Any]] = {}
    edge_keys: set[tuple[str, str, str, str]] = set()

    def _add_node(node: dict[str, Any]) -> None:
        nid = str(node["id"])
        if nid not in node_by_id:
            node_by_id[nid] = node
            nodes.append(node)

    def _add_edge(edge: dict[str, Any]) -> None:
        src = str(edge["src"])
        dst = str(edge["dst"])
        if src not in node_by_id or dst not in node_by_id:
            return
        dedup = (
            src,
            dst,
            str(edge.get("edge_type") or ""),
            f"{edge.get('chain_id', '')}:{edge.get('step_order', '')}",
        )
        if dedup in edge_keys:
            return
        edge_keys.add(dedup)
        edges.append(edge)

    def _ensure_guard_locus_node(locus: str, *, assumption: str = "") -> str:
        clean_loc = locus.strip()
        gid = f"locus:{clean_loc}"
        if gid not in node_by_id:
            _add_node(
                {
                    "id": gid,
                    "node_type": "guard_locus",
                    "label": clean_loc,
                    "locus": clean_loc,
                    "subsystem": infer_subsystem(clean_loc),
                    "guard_assumption": assumption,
                }
            )
        return gid

    # 1. Surfaces
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
        _add_node(
            {
                "id": sid,
                "node_type": "surface",
                "label": str(s["name"]),
                "kind": str(s["kind"]),
                "subsystem": str(s["subsystem"]),
                "locus": str(s["locus"]),
                "priority": str(s["priority"]),
                "trust_boundary": str(s["trust_boundary"]),
                "requires_tags": parse_tag_list(str(s.get("requires_tags_json") or "[]")),
                "coverage_state": cov,
            }
        )

    # 2. Verified dry guards
    for dt in dry_tasks:
        guard_id = f"guard:{dt['task_id']}"
        _add_node(
            {
                "id": guard_id,
                "node_type": "verified_guard",
                "label": str(dt["dry_control_locus"] or ""),
                "locus": str(dt["dry_control_locus"] or ""),
                "reason": str(dt["dry_control_reason"] or ""),
                "surface_id": str(dt.get("surface_id") or ""),
            }
        )
        if dt.get("surface_id"):
            _add_edge(
                {
                    "src": str(dt["surface_id"]),
                    "dst": guard_id,
                    "edge_type": "protected_by_guard",
                    "label": "dry guard",
                }
            )

    # 3. Primitives + concrete `guard_locus` nodes (zero dangling `guarded_by` edges)
    for p in primitives:
        pid = str(p["primitive_id"])
        gloc = str(p.get("guarded_by_locus") or "").strip()
        _add_node(
            {
                "id": pid,
                "node_type": "primitive",
                "label": f"{p['kind']} @ {p['locus']}",
                "kind": str(p["kind"]),
                "role": str(p.get("role") or "capability"),
                "subsystem": str(p["subsystem"]),
                "locus": str(p["locus"]),
                "preconditions": str(p["preconditions"]),
                "postconditions": str(p["postconditions"]),
                "guarded_by_locus": gloc,
                "provides_tags": parse_tag_list(str(p.get("provides_tags_json") or "[]")),
                "requires_tags": parse_tag_list(str(p.get("requires_tags_json") or "[]")),
                "chained": bool(p["chained"]),
                "status": str(p.get("status") or "active"),
            }
        )
        if p.get("surface_id"):
            _add_edge(
                {
                    "src": str(p["surface_id"]),
                    "dst": pid,
                    "edge_type": "yields_primitive",
                    "label": str(p["kind"]),
                }
            )
        if gloc:
            gnode_id = _ensure_guard_locus_node(gloc, assumption=str(p.get("guard_assumption") or ""))
            _add_edge(
                {
                    "src": pid,
                    "dst": gnode_id,
                    "edge_type": "guarded_by",
                    "label": str(p.get("guard_assumption") or "upstream guard"),
                }
            )

    # 4. Anomalies
    for a in anomalies:
        aid = str(a["anomaly_id"])
        _add_node(
            {
                "id": aid,
                "node_type": "anomaly",
                "label": str(a["observation"])[:80],
                "subsystem": str(a.get("subsystem") or infer_subsystem(str(a["locus"]))),
                "locus": str(a["locus"]),
                "status": str(a["status"]),
            }
        )
        if a.get("surface_id"):
            _add_edge(
                {
                    "src": str(a["surface_id"]),
                    "dst": aid,
                    "edge_type": "exhibits_anomaly",
                    "label": str(a["status"]),
                }
            )

    # 5. Findings
    for f in findings:
        fid = str(f["finding_id"])
        _add_node(
            {
                "id": fid,
                "node_type": "finding",
                "claim_id": str(f["claim_id"]),
                "label": str(f["title"]),
                "severity": str(f["severity"]),
                "subsystem": infer_subsystem(str(f["locus"])),
                "locus": str(f["locus"]),
                "attribution": str(f["attribution"]),
                "remediation_state": str(f.get("remediation_state") or "unpatched"),
                "realism_tier": str(f.get("realism_tier") or "stepping_stone"),
                "ub_divergence_class": str(f.get("ub_divergence_class") or ""),
                "provides_tags": parse_tag_list(str(f.get("provides_tags_json") or "[]")),
            }
        )
        if f.get("surface_id"):
            _add_edge(
                {
                    "src": str(f["surface_id"]),
                    "dst": fid,
                    "edge_type": "confirmed_finding",
                    "label": str(f["severity"]),
                }
            )

    # 6. Crown Jewels
    for cj in crown_jewels:
        jid = str(cj["jewel_id"])
        _add_node(
            {
                "id": jid,
                "node_type": "crown_jewel",
                "label": str(cj["name"]),
                "subsystem": str(cj["subsystem"]),
                "locus": str(cj["locus"]),
                "impact_class": str(cj["impact_class"]),
                "status": str(cj["status"]),
                "reached_by_id": str(cj.get("reached_by_id") or ""),
                "max_interaction_steps": int(cj.get("max_interaction_steps") or 1),
            }
        )

    def _ensure_step_node(step_id: str) -> None:
        clean_id = step_id.strip()
        if not clean_id or clean_id in node_by_id:
            return
        crow = conn.execute(
            "SELECT claim_id, title, severity, locus, status, subsystem FROM claims WHERE claim_id = ?",
            (clean_id,),
        ).fetchone()
        if crow is not None:
            _add_node(
                {
                    "id": str(crow["claim_id"]),
                    "node_type": "claim",
                    "label": str(crow["title"]),
                    "severity": str(crow["severity"]),
                    "subsystem": str(crow["subsystem"] or infer_subsystem(str(crow["locus"]))),
                    "locus": str(crow["locus"]),
                    "status": str(crow["status"]),
                }
            )
        else:
            _add_node(
                {
                    "id": clean_id,
                    "node_type": "chain_step_ref",
                    "label": clean_id,
                }
            )

    # 7. Open Doors
    for d in open_doors:
        did = str(d["door_id"])
        blocker_loc = str(d.get("blocker_locus") or "").strip()
        _add_node(
            {
                "id": did,
                "node_type": "open_door",
                "label": str(d["missing_link_summary"])[:80],
                "direction": str(d["direction"]),
                "subsystem": str(d["subsystem"]),
                "anchor_locus": str(d["anchor_locus"]),
                "blocker_locus": blocker_loc,
                "status": str(d["status"]),
                "jewel_id": str(d.get("jewel_id") or ""),
                "wanted_tags": parse_tag_list(str(d.get("wanted_tags_json") or "[]")),
            }
        )
        if blocker_loc:
            gnode_id = _ensure_guard_locus_node(blocker_loc, assumption=str(d["missing_link_summary"])[:120])
            _add_edge(
                {
                    "src": did,
                    "dst": gnode_id,
                    "edge_type": "blocked_by_guard",
                    "label": "blocker guard",
                }
            )
        if d.get("jewel_id"):
            _add_edge(
                {
                    "src": did,
                    "dst": str(d["jewel_id"]),
                    "edge_type": "targets_crown_jewel",
                    "label": str(d["status"]),
                }
            )
        held_ids = _safe_json_loads(d.get("held_ids_json"), [])
        if isinstance(held_ids, list):
            for hid in held_ids:
                hid_str = str(hid).strip()
                if not hid_str:
                    continue
                _ensure_step_node(hid_str)
                _add_edge(
                    {
                        "src": hid_str,
                        "dst": did,
                        "edge_type": "door_holds_step",
                        "label": "held",
                    }
                )
        matched_entries = _safe_json_loads(d.get("matched_by_json"), [])
        if isinstance(matched_entries, list):
            for me in matched_entries:
                if isinstance(me, dict) and me.get("id"):
                    mid_str = str(me["id"]).strip()
                    if not mid_str:
                        continue
                    _ensure_step_node(mid_str)
                    modes = me.get("modes")
                    mode_lbl = ",".join(str(m) for m in modes) if isinstance(modes, list) and modes else "matched"
                    _add_edge(
                        {
                            "src": mid_str,
                            "dst": did,
                            "edge_type": "wakes_open_door",
                            "label": mode_lbl,
                        }
                    )

    # 8. Chains + ordered `chain_transition` edges (resolving any `clm-*` step nodes cleanly)
    for ch in chains:
        cid = str(ch["chain_id"])
        raw_steps = _safe_json_loads(ch["step_ids_json"], [])
        steps = [str(st).strip() for st in raw_steps if str(st).strip()] if isinstance(raw_steps, list) else []

        for step_id in steps:
            _ensure_step_node(step_id)

        _add_node(
            {
                "id": cid,
                "node_type": "chain",
                "label": str(ch["title"]),
                "severity": str(ch["severity"]),
                "verified": bool(ch["verified"]),
                "realism_tier": str(ch.get("realism_tier") or "stepping_stone"),
                "step_count": len(steps),
                "jewel_id": str(ch.get("jewel_id") or ""),
                "door_id": str(ch.get("door_id") or ""),
            }
        )
        for idx, step_id in enumerate(steps, start=1):
            _add_edge(
                {
                    "src": step_id,
                    "dst": cid,
                    "edge_type": "chain_step",
                    "chain_id": cid,
                    "step_order": idx,
                }
            )
        for idx in range(len(steps) - 1):
            _add_edge(
                {
                    "src": steps[idx],
                    "dst": steps[idx + 1],
                    "edge_type": "chain_transition",
                    "chain_id": cid,
                    "step_order": idx + 1,
                }
            )
        if ch.get("jewel_id"):
            _add_edge(
                {
                    "src": cid,
                    "dst": str(ch["jewel_id"]),
                    "edge_type": "reaches_crown_jewel",
                    "label": str(ch.get("realism_tier") or "reached"),
                }
            )
        if ch.get("door_id"):
            _add_edge(
                {
                    "src": cid,
                    "dst": str(ch["door_id"]),
                    "edge_type": "resolves_open_door",
                    "label": "chained",
                }
            )

    # Link single-step findings/chains recorded on `crown_jewels.reached_by_id`
    for cj in crown_jewels:
        reached_by = str(cj.get("reached_by_id") or "").strip()
        if reached_by:
            _add_edge(
                {
                    "src": reached_by,
                    "dst": str(cj["jewel_id"]),
                    "edge_type": "reaches_crown_jewel",
                    "label": "reached",
                }
            )

    # 9. Threat assumptions
    for ta in threat_assumptions:
        aid = str(ta["assumption_id"])
        _add_node(
            {
                "id": aid,
                "node_type": "threat_assumption",
                "label": str(ta["assumption_text"])[:80],
                "subsystem": str(ta["subsystem"]),
                "trust_boundary": str(ta["trust_boundary"]),
                "status": str(ta["status"]),
                "evidence_ref": str(ta["evidence_ref"]),
            }
        )
        if ta.get("dependent_surface_id"):
            _add_edge(
                {
                    "src": aid,
                    "dst": str(ta["dependent_surface_id"]),
                    "edge_type": "assumes_boundary_for",
                    "label": str(ta["status"]),
                }
            )

    # 10. Separate background code graph (`code_graph.repomap_edges`, zero `file:` dangling refs in `edges`)
    code_files: set[str] = {str(r["rel_path"]) for r in sym_files_rows if r["rel_path"]}
    exported_repomap_edges: list[dict[str, Any]] = []
    for re_edge in repomap_edges:
        sf = str(re_edge["src_file"])
        df = str(re_edge["dst_file"])
        code_files.add(sf)
        code_files.add(df)
        exported_repomap_edges.append(
            {
                "src_file": sf,
                "dst_file": df,
                "symbol": str(re_edge["symbol"]),
                "weight": float(re_edge["weight"]),
            }
        )
    code_graph: dict[str, Any] = {
        "files": sorted(code_files),
        "repomap_edges": exported_repomap_edges,
        "symbols_total": int(sym_count_row["c"] or 0) if sym_count_row else 0,
        "edges_exported": len(exported_repomap_edges),
    }

    # 11. `findings_detail` projection (4-arm repro + `fix_9arm` + `proposer != falsifier` + `realism_tier`)
    best_pv_by_finding: dict[str, dict[str, Any]] = {}
    for pv in patch_verifications:
        fid_pv = str(pv["finding_id"])
        if fid_pv not in best_pv_by_finding:
            best_pv_by_finding[fid_pv] = pv

    findings_sorted = sorted(
        findings,
        key=lambda f: (_SEVERITY_RANK.get(str(f["severity"]).lower(), 9), str(f["finding_id"])),
    )
    findings_detail: list[dict[str, Any]] = []
    for f in findings_sorted:
        fid = str(f["finding_id"])
        arm1 = _safe_json_loads(f.get("arm1_clean_poc_json"), {})
        arm2 = _safe_json_loads(f.get("arm2_clean_ctrl_json"), {})
        arm3 = _safe_json_loads(f.get("arm3_patch_poc_json"), {})
        arm4 = _safe_json_loads(f.get("arm4_patch_ctrl_json"), {})
        arm5a = _safe_json_loads(f.get("arm5a_release_poc_json"), {})
        arm5b = _safe_json_loads(f.get("arm5b_release_ctrl_json"), {})
        realism_parsed = _safe_json_loads(f.get("realism_json"), {})

        proposer = str(f.get("proposer_worker_id") or "")
        falsifier = str(f.get("falsifier_worker_id") or "")
        independent_falsifier = bool(proposer and falsifier and proposer != falsifier)
        falsifier_sep: dict[str, Any] = {
            "independent_falsifier_verified": independent_falsifier,
            "proposer_equals_falsifier": bool(proposer and falsifier and proposer == falsifier),
        }
        if visibility != "public_disclosure":
            falsifier_sep["proposer_worker_id"] = proposer
            falsifier_sep["falsifier_worker_id"] = falsifier

        repro_4arm: dict[str, Any] = {
            "all_4_arms_passed": all(
                isinstance(a, dict) and bool(a.get("arm_passed", False)) for a in (arm1, arm2, arm3, arm4)
            ),
            "arm1_clean_poc": _summarize_arm(arm1, visibility=visibility),
            "arm2_clean_control": _summarize_arm(arm2, visibility=visibility),
            "arm3_patch_poc": _summarize_arm(arm3, visibility=visibility),
            "arm4_patch_control": _summarize_arm(arm4, visibility=visibility),
            "arm5a_release_poc": _summarize_arm(arm5a, visibility=visibility) if isinstance(arm5a, dict) and arm5a else None,
            "arm5b_release_control": _summarize_arm(arm5b, visibility=visibility) if isinstance(arm5b, dict) and arm5b else None,
            "ub_divergence_class": str(f.get("ub_divergence_class") or ""),
        }
        if visibility != "public_disclosure":
            repro_4arm["poc_cmd"] = str(f.get("poc_cmd") or "")
            repro_4arm["control_cmd"] = str(f.get("control_cmd") or "")
            repro_4arm["build_cmd"] = str(f.get("build_cmd") or "")
            repro_4arm["micropatch_diff"] = str(f.get("micropatch_diff") or "")
        if visibility == "internal_full":
            repro_4arm["micropatch_path"] = str(f.get("micropatch_path") or "")

        pv_row = best_pv_by_finding.get(fid)
        fix_9arm: dict[str, Any] | None = None
        if pv_row is not None:
            pv_arms = _safe_json_loads(pv_row.get("arms_json"), {})
            pv_variants = _safe_json_loads(pv_row.get("variant_cmds_json"), [])
            pv_arm9 = _safe_json_loads(pv_row.get("arm9_revert_poc_json"), {})
            arm_statuses = (
                {
                    str(k): bool(v.get("arm_passed", False))
                    for k, v in sorted(pv_arms.items())
                    if isinstance(v, dict)
                }
                if isinstance(pv_arms, dict)
                else {}
            )
            fix_9arm = {
                "verification_id": str(pv_row["verification_id"]),
                "passed": bool(pv_row["passed"]),
                "created_at": str(pv_row["created_at"]),
                "caller_audit": str(pv_row["caller_audit"]),
                "sibling_audit": str(pv_row["sibling_audit"]),
                "variant_count": len(pv_variants) if isinstance(pv_variants, list) else 0,
                "arm_statuses": arm_statuses,
                "arm9_revert_passed": bool(pv_arm9.get("arm_passed", False)) if isinstance(pv_arm9, dict) else False,
            }
            if visibility != "public_disclosure":
                fix_9arm["patch_diff"] = str(pv_row.get("patch_diff") or "")
                fix_9arm["suite_cmd"] = str(pv_row.get("suite_cmd") or "")
            if visibility == "internal_full":
                fix_9arm["patch_path"] = str(pv_row.get("patch_path") or "")

        findings_detail.append(
            {
                "finding_id": fid,
                "claim_id": str(f["claim_id"]),
                "surface_id": str(f.get("surface_id") or ""),
                "title": str(f["title"]),
                "severity": str(f["severity"]),
                "locus": str(f["locus"]),
                "subsystem": infer_subsystem(str(f["locus"])),
                "root_cause": str(f["root_cause"]),
                "attribution": str(f["attribution"]),
                "remediation_state": str(f.get("remediation_state") or "unpatched"),
                "customer_state": str(f.get("customer_state") or "pending"),
                "realism_tier": str(f.get("realism_tier") or "stepping_stone"),
                "realism": realism_parsed if isinstance(realism_parsed, dict) else {},
                "provides_tags": parse_tag_list(str(f.get("provides_tags_json") or "[]")),
                "diff_state": str(f.get("diff_state") or ""),
                "falsifier_separation": falsifier_sep,
                "reproduction_4arm": repro_4arm,
                "fix_9arm": fix_9arm,
                "created_at": str(f["created_at"]),
            }
        )

    # 12. `chains_detail` projection (ordered steps + ablation proof)
    chains_detail: list[dict[str, Any]] = []
    for ch in chains:
        cid = str(ch["chain_id"])
        raw_steps = _safe_json_loads(ch["step_ids_json"], [])
        steps = [str(st).strip() for st in raw_steps if str(st).strip()] if isinstance(raw_steps, list) else []
        raw_ablation = _safe_json_loads(ch.get("ablation_matrix_json"), [])
        ablation_matrix = raw_ablation if isinstance(raw_ablation, list) else []
        evidence_parsed = _safe_json_loads(ch.get("evidence_json"), {})
        if not isinstance(evidence_parsed, dict):
            evidence_parsed = {}
        realism_parsed = _safe_json_loads(ch.get("realism_json"), {})
        if not isinstance(realism_parsed, dict):
            realism_parsed = {}

        ordered_steps: list[dict[str, Any]] = []
        for idx, step_id in enumerate(steps, start=1):
            snode = node_by_id.get(step_id, {})
            ordered_steps.append(
                {
                    "step_order": idx,
                    "step_id": step_id,
                    "node_type": str(snode.get("node_type") or "unknown"),
                    "locus": str(snode.get("locus") or ""),
                    "label": str(snode.get("label") or step_id),
                }
            )

        clean_ablation: list[dict[str, Any]] = []
        for entry in ablation_matrix:
            if not isinstance(entry, dict):
                continue
            if visibility == "public_disclosure":
                clean_ablation.append(
                    {
                        "step_id": str(entry.get("step_id") or ""),
                        "ablated_via": str(entry.get("ablated_via") or ""),
                        "causally_required": bool(entry.get("causally_required", False)),
                        "defect_still_fired": bool(entry.get("defect_still_fired", False)),
                    }
                )
            else:
                clean_ablation.append(dict(entry))

        ch_item: dict[str, Any] = {
            "chain_id": cid,
            "title": str(ch["title"]),
            "severity": str(ch["severity"]),
            "verified": bool(ch["verified"]),
            "realism_tier": str(ch.get("realism_tier") or "stepping_stone"),
            "realism": realism_parsed,
            "jewel_id": str(ch.get("jewel_id") or ""),
            "door_id": str(ch.get("door_id") or ""),
            "ordered_steps": ordered_steps,
            "ablation_proof": {
                "steps_ablated": len(clean_ablation),
                "all_steps_causally_required": bool(clean_ablation)
                and all(bool(e.get("causally_required", False)) for e in clean_ablation),
                "ablation_matrix": clean_ablation,
                "reason": str(evidence_parsed.get("reason") or ""),
            },
            "created_at": str(ch["created_at"]),
        }
        if visibility != "public_disclosure":
            ch_item["e2e_poc_cmd"] = str(ch.get("e2e_poc_cmd") or "")
            ch_item["control_cmd"] = str(ch.get("control_cmd") or "")
            ch_item["build_cmd"] = str(evidence_parsed.get("build_cmd") or "")
        chains_detail.append(ch_item)

    # 13. Optional bounded scrubbed `code_snippets`
    code_snippets: list[dict[str, Any]] = []
    if include_snippets:
        snippet_loci: list[str] = []
        for f in findings_sorted:
            if f.get("locus"):
                snippet_loci.append(str(f["locus"]))
        for ch_d in chains_detail:
            for st in ch_d["ordered_steps"]:
                if st.get("locus"):
                    snippet_loci.append(str(st["locus"]))
        for cj in crown_jewels:
            if cj.get("locus"):
                snippet_loci.append(str(cj["locus"]))
        for n in nodes:
            if n["node_type"] in ("guard_locus", "verified_guard") and n.get("locus"):
                snippet_loci.append(str(n["locus"]))
        for p in primitives:
            if p.get("locus"):
                snippet_loci.append(str(p["locus"]))
        code_snippets = _extract_bounded_code_snippets(target_dir, snippet_loci)

    # 14. `verification_summary` (`G1–G5` + funnel + economics + `scope_notice`)
    gates_res = check_all_gates(
        conn,
        target_dir=target_dir if (target_dir is not None and target_dir.is_dir()) else None,
        auto_enqueue_chain=False,
        reconcile=False,
    )
    claim_counts = {
        str(r["status"]): int(r["c"])
        for r in conn.execute("SELECT status, COUNT(*) AS c FROM claims GROUP BY status").fetchall()
    }
    rejected_claims = (
        claim_counts.get("falsified", 0)
        + claim_counts.get("rejected_repro", 0)
        + claim_counts.get("duplicate_root_cause", 0)
        + claim_counts.get("config_gated", 0)
    )
    econ_raw = dict(gates_res.get("economics") or {})
    if visibility == "public_disclosure":
        econ_out: dict[str, Any] = {
            "in_scope_loc": econ_raw.get("in_scope_loc", 0),
            "research_independence_pass": econ_raw.get("research_independence_pass", True),
            "product_operability_pass": econ_raw.get("product_operability_pass", True),
            "default_finding_attribution": econ_raw.get("default_finding_attribution", "found_autonomously_by_ajar"),
        }
    else:
        econ_out = econ_raw

    gates_out: dict[str, dict[str, Any]] = {}
    raw_gates = gates_res.get("gates") or {}
    if isinstance(raw_gates, dict):
        for gname, gval in sorted(raw_gates.items()):
            gdict = gval if isinstance(gval, dict) else {}
            if visibility == "public_disclosure":
                gates_out[str(gname)] = {
                    "passed": bool(gdict.get("passed", False)),
                    "issue_count": len(gdict.get("issues") or []),
                }
            else:
                gates_out[str(gname)] = {
                    "passed": bool(gdict.get("passed", False)),
                    "issues": list(gdict.get("issues") or []),
                }

    verification_summary: dict[str, Any] = {
        "gates_passed": bool(gates_res.get("passed", False)),
        "crown_jewel_reached": bool(gates_res.get("crown_jewel_reached", False)),
        "gates": gates_out,
        "funnel": {
            "surfaces_total": len(surfaces),
            "surfaces_covered": len(finding_surfaces | dry_surfaces | done_surfaces),
            "surfaces_guarded_dry": len(dry_surfaces),
            "claims_total": sum(claim_counts.values()),
            "claims_by_status": claim_counts,
            "claims_rejected_or_deduped": rejected_claims,
            "confirmed_findings": len(findings),
            "verified_chains": sum(1 for c in chains if c["verified"]),
            "patch_verifications_passed": sum(1 for pv in patch_verifications if pv["passed"]),
        },
        "economics": econ_out,
        "scope_notice": SCOPE_NOTICE,
    }

    cov_row = conn.execute(
        "SELECT COUNT(*) AS spans, COUNT(DISTINCT rel_path) AS files FROM coverage_spans"
    ).fetchone()
    dangling_edges = sum(1 for e in edges if e["src"] not in node_by_id or e["dst"] not in node_by_id)

    payload: dict[str, Any] = {
        "schema": "ajar-platform-graph/2",
        "visibility": visibility,
        "run": run_obj,
        "nodes": nodes,
        "edges": edges,
        "code_graph": code_graph,
        "findings_detail": findings_detail,
        "chains_detail": chains_detail,
        "code_snippets": code_snippets,
        "verification_summary": verification_summary,
        "threat_model": threat_model,
        "threat_assumptions": threat_assumptions,
        "active_steers": steers if visibility != "public_disclosure" else [],
        "epistemic_hooks": epistemic_hooks if visibility == "internal_full" else [],
        "primitive_helpers": primitive_helpers if visibility != "public_disclosure" else [],
        "summary": {
            "surfaces_total": len(surfaces),
            "surfaces_with_findings": len(finding_surfaces),
            "surfaces_guarded_dry": len(dry_surfaces),
            "primitives_total": len(primitives),
            "primitive_helpers_verified": sum(1 for h in primitive_helpers if h["verified"]),
            "unchained_primitives": sum(
                1 for p in primitives if not p["chained"] and p.get("status", "active") != "dry"
            ),
            "unexplained_anomalies": sum(1 for a in anomalies if a["status"] == "unexplained"),
            "confirmed_findings": len(findings),
            "verified_chains": sum(1 for c in chains if c["verified"]),
            "crown_jewels_total": len(crown_jewels),
            "crown_jewels_reached": sum(1 for cj in crown_jewels if cj["status"] == "reached"),
            "open_doors_total": len(open_doors),
            "open_doors_ready": sum(1 for d in open_doors if d["status"] == "ready"),
            "guard_loci_total": sum(1 for n in nodes if n["node_type"] == "guard_locus"),
            "active_steers": len(steers) if visibility != "public_disclosure" else 0,
            "epistemic_hooks_total": len(epistemic_hooks) if visibility == "internal_full" else 0,
            "threat_assumptions_total": len(threat_assumptions),
            "threat_assumptions_violated": sum(1 for ta in threat_assumptions if ta["status"] == "violated"),
            "coverage_spans_total": int(cov_row["spans"] or 0),
            "coverage_files_total": int(cov_row["files"] or 0),
            "dangling_edges": dangling_edges,
        },
    }

    if visibility in ("customer_private", "public_disclosure"):
        t_roots, o_roots = _collect_local_roots(raw_target_path, raw_workspace_path, conn=conn)
        payload = _sanitize_external_paths(payload, target_roots=t_roots, other_roots=o_roots)
    scrubbed = scrub_json_value(payload)
    assert isinstance(scrubbed, dict)
    return scrubbed


def export_attack_flow_graph(
    conn: sqlite3.Connection,
    *,
    schema: str = "v2",
    visibility: str = "internal_full",
    include_snippets: bool = False,
    repo_slug: str = "",
) -> dict[str, Any]:
    """Export deterministic `ajar-platform-graph/2` (or legacy `v1`) JSON graph."""
    schema_clean = (schema or "v2").strip().lower()
    if schema_clean not in VALID_GRAPH_SCHEMAS:
        raise AjarError(
            f"Unsupported --schema {schema!r}; choose from {', '.join(VALID_GRAPH_SCHEMAS)}.",
            EXIT_USER_ERROR,
        )
    vis_clean = (visibility or "internal_full").strip().lower()
    if vis_clean not in VALID_GRAPH_VISIBILITIES:
        raise AjarError(
            f"Unsupported --visibility {visibility!r}; choose from {', '.join(VALID_GRAPH_VISIBILITIES)}.",
            EXIT_USER_ERROR,
        )
    if schema_clean == "v1":
        return _export_v1_graph(conn, visibility=vis_clean)
    return _export_v2_graph(
        conn,
        visibility=vis_clean,
        include_snippets=bool(include_snippets),
        repo_slug=repo_slug,
    )
