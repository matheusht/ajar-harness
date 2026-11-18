"""Pure-stdlib JSON-RPC 2.0 STDIO MCP server (`ajar mcp --run <id>`).

Supports both newline-delimited JSON-RPC (MCP 2024-11-05 / 2025-03-26 STDIO spec)
and `Content-Length` framed JSON-RPC automatically, exposing Ajar's SQLite state
and verification operations as structured tools for Host Mode agents.
"""

from __future__ import annotations

import json
import pathlib
import sys
from typing import Any, BinaryIO

from ajar import __version__
from ajar.db import (
    AjarError,
    check_dead_end_repetition,
    infer_subsystem,
    lease_next_task,
    list_rows,
    list_steers,
    log_event,
    maybe_auto_pulse,
    new_id,
    open_run_db,
    render_task_context,
    rescope_claim,
    resolve_run_id,
    utc_now_iso,
)
from ajar.gates import check_all_gates, check_guarded_primitive_dry_block, validate_dry_locus
from ajar.graph import export_attack_flow_graph
from ajar.oracles import query_oracle
from ajar.redact import scrub_text
from ajar.repomap import build_repomap

MCP_TOOLS: list[dict[str, Any]] = [
    {
        "name": "ajar_status",
        "description": "Return run metadata, task/claim counts, and closeout gate status.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "ajar_context",
        "description": "Render < 4 KB certified context frame for a leased task.",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        },
    },
    {
        "name": "ajar_map",
        "description": "Build Personalized PageRank repository symbol map within a token budget.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "focus_files": {"type": "array", "items": {"type": "string"}},
                "focus_symbols": {"type": "array", "items": {"type": "string"}},
                "budget_tokens": {"type": "integer", "default": 1500},
            },
        },
    },
    {
        "name": "ajar_ref_query",
        "description": "Search FTS5 index across intent, reachability, or precedent.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["intent", "reachability", "precedent", "all"]},
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 8},
            },
            "required": ["kind", "query"],
        },
    },
    {
        "name": "ajar_surface_add",
        "description": "Register an entry point, contract, or trust boundary surface.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "kind": {"type": "string"},
                "subsystem": {"type": "string"},
                "locus": {"type": "string"},
                "priority": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
            },
            "required": ["name", "kind", "subsystem", "locus"],
        },
    },
    {
        "name": "ajar_task_lease",
        "description": "Atomically lease the highest-salience open task.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "worker_id": {"type": "string"},
                "kind": {"type": "string"},
                "recover": {"type": "boolean", "default": False},
            },
            "required": ["worker_id"],
        },
    },
    {
        "name": "ajar_task_close",
        "description": "Close a leased task as `done` or `dry` (citing concrete guard locus).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "worker_id": {"type": "string"},
                "outcome": {"type": "string", "enum": ["done", "dry"]},
                "summary": {"type": "string"},
                "control_locus": {"type": "string"},
                "control_reason": {"type": "string"},
            },
            "required": ["task_id", "worker_id", "outcome"],
        },
    },
    {
        "name": "ajar_anomaly_add",
        "description": "Record an unexplained execution observation (survives claim disproof).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "locus": {"type": "string"},
                "observation": {"type": "string"},
                "repro_cmd": {"type": "string"},
            },
            "required": ["locus", "observation"],
        },
    },
    {
        "name": "ajar_claim_propose",
        "description": "Propose a falsifiable vulnerability claim with pre-reproduction falsification prediction and test.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "worker_id": {"type": "string"},
                "title": {"type": "string"},
                "locus": {"type": "string"},
                "mechanism": {"type": "string"},
                "severity": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
                "falsification_prediction": {"type": "string"},
                "falsification_test": {"type": "string"},
                "consume_anomaly_id": {"type": "string"},
            },
            "required": [
                "worker_id",
                "title",
                "locus",
                "mechanism",
                "falsification_prediction",
                "falsification_test",
            ],
        },
    },
    {
        "name": "ajar_claim_falsify",
        "description": "Mark a claim disproved after running its falsification test.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "claim_id": {"type": "string"},
                "worker_id": {"type": "string"},
                "notes": {"type": "string"},
                "control_locus": {"type": "string"},
            },
            "required": ["claim_id", "worker_id", "notes"],
        },
    },
    {
        "name": "ajar_claim_survive",
        "description": "Mark a claim as surviving independent falsification (`proposer != falsifier`).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "claim_id": {"type": "string"},
                "worker_id": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["claim_id", "worker_id", "notes"],
        },
    },
    {
        "name": "ajar_claim_rescope",
        "description": "Re-scope a claim's locus, preconditions, or severity instead of discarding a real defect (`claim_mismatch` recovery).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "claim_id": {"type": "string"},
                "worker_id": {"type": "string"},
                "reason": {"type": "string"},
                "title": {"type": "string"},
                "locus": {"type": "string"},
                "mechanism": {"type": "string"},
                "severity": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
            },
            "required": ["claim_id", "worker_id", "reason"],
        },
    },
    {
        "name": "ajar_steer_list",
        "description": "List active workspace Steers (threat-model scope boundaries and trusted invariants).",
        "inputSchema": {"type": "object", "properties": {"active_only": {"type": "boolean", "default": True}}},
    },
    {
        "name": "ajar_export_graph",
        "description": "Export deterministic `ajar-platform-graph/1` component and attack-flow whiteboard JSON.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "ajar_finish",
        "description": "Check all 5 SQL closeout gates (`G1`–`G5`) and mark the run finished if green.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def dispatch_mcp_tool(
    run_id: str,
    tool_name: str,
    args: dict[str, Any],
    *,
    ajar_home: pathlib.Path | str | None = None,
) -> dict[str, Any]:
    conn = open_run_db(run_id, ajar_home=ajar_home)
    try:
        run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
        tpath = pathlib.Path(run["target_path"]) if run else pathlib.Path(".")

        if tool_name == "ajar_status":
            gates = check_all_gates(conn, target_dir=tpath, auto_enqueue_chain=False)
            return {
                "run": dict(run) if run else {},
                "tasks": list_rows(conn, "SELECT status, COUNT(*) AS c FROM tasks GROUP BY status"),
                "claims": list_rows(conn, "SELECT status, COUNT(*) AS c FROM claims GROUP BY status"),
                "gates": gates,
            }
        if tool_name == "ajar_context":
            return render_task_context(conn, str(args["task_id"]))
        if tool_name == "ajar_map":
            return build_repomap(
                conn,
                tpath,
                focus_files=args.get("focus_files") or (),
                focus_symbols=args.get("focus_symbols") or (),
                budget_tokens=int(args.get("budget_tokens", 1500)),
            )
        if tool_name == "ajar_ref_query":
            return {
                "results": query_oracle(
                    conn,
                    str(args["kind"]),
                    str(args["query"]),
                    limit=int(args.get("limit", 8)),
                )
            }
        if tool_name == "ajar_surface_add":
            sid = new_id("surf")
            now_iso = utc_now_iso()
            conn.execute(
                """
                INSERT INTO surfaces(surface_id, name, kind, subsystem, locus, priority, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sid,
                    scrub_text(str(args["name"])),
                    str(args["kind"]),
                    str(args["subsystem"]),
                    str(args["locus"]),
                    str(args.get("priority", "high")),
                    now_iso,
                ),
            )
            log_event(conn, "mcp", "surface_added", sid, {"locus": args["locus"]})
            return {"surface_id": sid}
        if tool_name == "ajar_task_lease":
            leased = lease_next_task(
                conn,
                worker_id=str(args["worker_id"]),
                kind=args.get("kind"),
                recover=bool(args.get("recover", False)),
            )
            return {"leased": leased}
        if tool_name == "ajar_task_close":
            from ajar import EXIT_GATE_BLOCKED, EXIT_USER_ERROR

            tid = str(args["task_id"])
            wid = str(args["worker_id"])
            outcome = str(args["outcome"])
            cur_task = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (tid,)).fetchone()
            if cur_task is None:
                raise AjarError(f"Unknown task_id: {tid}", EXIT_USER_ERROR)
            now_iso = utc_now_iso()
            import time as _t

            if outcome == "dry":
                cloc = str(args.get("control_locus") or "")
                creason = str(args.get("control_reason") or "")
                ok, msg = validate_dry_locus(tpath, str(run["target_mode"] if run else "source"), cloc, creason)
                if not ok:
                    raise AjarError(msg, EXIT_GATE_BLOCKED)
                ok_gp, msg_gp = check_guarded_primitive_dry_block(conn, task_row=cur_task, dry_locus=cloc)
                if not ok_gp:
                    raise AjarError(msg_gp, EXIT_GATE_BLOCKED)
                conn.execute(
                    """
                    UPDATE tasks
                    SET status = 'dry', worker_id = ?, dry_control_locus = ?, dry_control_reason = ?,
                        closed_epoch = ?, updated_at = ?
                    WHERE task_id = ?
                    """,
                    (wid, cloc, scrub_text(creason), _t.time(), now_iso, tid),
                )
            else:
                conn.execute(
                    "UPDATE tasks SET status = 'done', worker_id = ?, summary = ?, closed_epoch = ?, updated_at = ? WHERE task_id = ?",
                    (wid, scrub_text(str(args.get("summary") or "")), _t.time(), now_iso, tid),
                )
            log_event(conn, wid, f"task_{outcome}", tid, {})
            pulse = maybe_auto_pulse(conn, tpath)
            return {"task_id": tid, "status": outcome, "pulse": pulse}
        if tool_name == "ajar_anomaly_add":
            aid = new_id("anom")
            loc = str(args["locus"])
            now_iso = utc_now_iso()
            conn.execute(
                """
                INSERT INTO anomalies(anomaly_id, subsystem, locus, observation, repro_cmd, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'unexplained', ?, ?)
                """,
                (
                    aid,
                    infer_subsystem(loc),
                    loc,
                    scrub_text(str(args["observation"])),
                    scrub_text(str(args.get("repro_cmd") or "")),
                    now_iso,
                    now_iso,
                ),
            )
            log_event(conn, "mcp", "anomaly_added", aid, {"locus": loc})
            return {"anomaly_id": aid, "status": "unexplained"}
        if tool_name == "ajar_claim_propose":
            from ajar import EXIT_GATE_BLOCKED
            from ajar.db import normalize_mechanism_key

            fpred = str(args.get("falsification_prediction") or "").strip()
            ftest = str(args.get("falsification_test") or "").strip()
            if len(fpred) < 10 or len(ftest) < 5:
                raise AjarError(
                    "DEC-0128 gate: falsification_prediction and falsification_test are required before proposing a claim.",
                    EXIT_GATE_BLOCKED,
                )
            loc = str(args["locus"])
            mech = str(args["mechanism"])
            anom_id = args.get("consume_anomaly_id")
            check_dead_end_repetition(conn, locus=loc, mechanism=mech, consume_anomaly_id=anom_id)
            cid = new_id("clm")
            now_iso = utc_now_iso()
            wid = str(args["worker_id"])
            conn.execute(
                """
                INSERT INTO claims(
                    claim_id, proposer_worker_id, title, subsystem, locus, mechanism, mechanism_key,
                    severity, falsification_prediction, falsification_test, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'proposed', ?, ?)
                """,
                (
                    cid,
                    wid,
                    scrub_text(str(args["title"])),
                    infer_subsystem(loc),
                    loc,
                    scrub_text(mech),
                    normalize_mechanism_key(mech),
                    str(args.get("severity", "high")),
                    scrub_text(fpred),
                    scrub_text(ftest),
                    now_iso,
                    now_iso,
                ),
            )
            if anom_id:
                conn.execute(
                    "UPDATE anomalies SET status = 'consumed_by_claim', consumed_by_id = ?, updated_at = ? WHERE anomaly_id = ?",
                    (cid, now_iso, str(anom_id)),
                )
            log_event(conn, wid, "claim_proposed", cid, {"locus": loc})
            return {"claim_id": cid, "status": "proposed"}
        if tool_name == "ajar_claim_falsify":
            from ajar import EXIT_GATE_BLOCKED

            cid = str(args["claim_id"])
            wid = str(args["worker_id"])
            clm = conn.execute("SELECT status FROM claims WHERE claim_id = ?", (cid,)).fetchone()
            if clm is None:
                raise AjarError(f"Unknown claim_id {cid}")
            if clm["status"] == "reproduced":
                raise AjarError(
                    f"Truth-axis monotonicity gate: verified reproduced claim {cid} cannot be downgraded to falsified.",
                    EXIT_GATE_BLOCKED,
                )
            now_iso = utc_now_iso()
            conn.execute(
                """
                UPDATE claims
                SET status = 'falsified', falsifier_worker_id = ?, falsify_notes = ?,
                    falsify_control_locus = ?, research_state = 'rejected_during_research',
                    evidence_state = 'falsified', updated_at = ?
                WHERE claim_id = ?
                """,
                (wid, scrub_text(str(args["notes"])), args.get("control_locus"), now_iso, cid),
            )
            conn.execute(
                """
                UPDATE anomalies
                SET status = 'unexplained', consumed_by_id = NULL, updated_at = ?
                WHERE consumed_by_id = ? AND status = 'consumed_by_claim'
                """,
                (now_iso, cid),
            )
            log_event(conn, wid, "claim_falsified", cid, {})
            return {"claim_id": cid, "status": "falsified"}
        if tool_name == "ajar_claim_survive":
            from ajar import EXIT_GATE_BLOCKED

            cid = str(args["claim_id"])
            wid = str(args["worker_id"])
            clm = conn.execute("SELECT proposer_worker_id, status FROM claims WHERE claim_id = ?", (cid,)).fetchone()
            if clm is None:
                raise AjarError(f"Unknown claim_id {cid}")
            if clm["status"] == "reproduced":
                raise AjarError(
                    f"Truth-axis monotonicity gate: verified reproduced claim {cid} cannot be downgraded.",
                    EXIT_GATE_BLOCKED,
                )
            if clm["proposer_worker_id"] == wid:
                raise AjarError(
                    "Fresh-falsifier rule: proposer_worker_id cannot mark its own claim survived.",
                    EXIT_GATE_BLOCKED,
                )
            now_iso = utc_now_iso()
            conn.execute(
                "UPDATE claims SET status = 'survived_falsify', falsifier_worker_id = ?, falsify_notes = ?, updated_at = ? WHERE claim_id = ?",
                (wid, scrub_text(str(args["notes"])), now_iso, cid),
            )
            log_event(conn, wid, "claim_survived_falsify", cid, {})
            return {"claim_id": cid, "status": "survived_falsify"}
        if tool_name == "ajar_claim_rescope":
            return rescope_claim(
                conn,
                claim_id=str(args["claim_id"]),
                worker_id=str(args["worker_id"]),
                reason=str(args["reason"]),
                title=args.get("title"),
                locus=args.get("locus"),
                mechanism=args.get("mechanism"),
                severity=args.get("severity"),
            )
        if tool_name == "ajar_steer_list":
            return {"steers": list_steers(conn, active_only=bool(args.get("active_only", True)))}
        if tool_name == "ajar_export_graph":
            return export_attack_flow_graph(conn)
        if tool_name == "ajar_finish":
            gates = check_all_gates(conn, target_dir=tpath, auto_enqueue_chain=True)
            if gates["passed"]:
                now_iso = utc_now_iso()
                conn.execute(
                    "UPDATE runs SET status = 'finished', stop_reason = 'all_gates_passed', finished_at = ?",
                    (now_iso,),
                )
                log_event(conn, "mcp", "run_finished", run_id, {})
            return gates
        raise AjarError(f"Unknown MCP tool: {tool_name}")
    finally:
        conn.close()


def handle_jsonrpc_message(
    msg: dict[str, Any],
    *,
    run_id: str,
    ajar_home: pathlib.Path | str | None = None,
) -> dict[str, Any] | None:
    method = str(msg.get("method") or "")
    req_id = msg.get("id")
    params = msg.get("params") or {}

    if method.startswith("notifications/"):
        return None
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "ajar-mcp", "version": __version__},
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": MCP_TOOLS}}
    if method == "tools/call":
        tname = str(params.get("name") or "")
        targs = params.get("arguments") or {}
        try:
            res = dispatch_mcp_tool(run_id, tname, targs, ajar_home=ajar_home)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(res, indent=2, sort_keys=True)}],
                    "isError": False,
                },
            }
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": scrub_text(str(exc))}],
                    "isError": True,
                },
            }
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


MAX_MCP_MESSAGE_BYTES = 4 * 1024 * 1024


def serve_mcp_stdio(
    *,
    explicit_run_id: str | None = None,
    stdin: BinaryIO | None = None,
    stdout: BinaryIO | None = None,
    ajar_home: pathlib.Path | str | None = None,
) -> None:
    run_id = resolve_run_id(explicit_run_id, ajar_home=ajar_home)
    inp = stdin or sys.stdin.buffer
    out = stdout or sys.stdout.buffer

    while True:
        first_line = inp.readline()
        if not first_line:
            break
        stripped = first_line.strip()
        if not stripped:
            continue

        use_framing = False
        if stripped.lower().startswith(b"content-length:"):
            use_framing = True
            try:
                length = int(stripped.split(b":", 1)[1].strip())
            except ValueError:
                continue
            while True:
                hdr = inp.readline()
                if not hdr or hdr in (b"\r\n", b"\n"):
                    break
            if length < 0 or length > MAX_MCP_MESSAGE_BYTES:
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32600, "message": f"Invalid Content-Length: {length}"},
                }
                encoded_err = json.dumps(err_resp, separators=(",", ":")).encode("utf-8")
                out.write(f"Content-Length: {len(encoded_err)}\r\n\r\n".encode("ascii") + encoded_err)
                out.flush()
                continue
            body = inp.read(length)
        else:
            if len(stripped) > MAX_MCP_MESSAGE_BYTES:
                continue
            body = stripped

        try:
            msg = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue

        resp = handle_jsonrpc_message(msg, run_id=run_id, ajar_home=ajar_home)
        if resp is None:
            continue
        encoded = json.dumps(resp, separators=(",", ":")).encode("utf-8")
        if use_framing:
            out.write(f"Content-Length: {len(encoded)}\r\n\r\n".encode("ascii") + encoded)
        else:
            out.write(encoded + b"\n")
        out.flush()
