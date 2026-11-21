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

from ajar import EXIT_USER_ERROR, __version__
from ajar.db import (
    AjarError,
    lease_next_task,
    list_rows,
    list_steers,
    open_run_db,
    render_task_context,
    resolve_run_id,
)
from ajar.gates import check_all_gates
from ajar.graph import export_attack_flow_graph
from ajar.oracles import query_oracle
from ajar.redact import scrub_text
from ajar.repomap import build_repomap
from ajar.services import (
    add_anomaly,
    add_surface,
    close_task_done,
    close_task_dry,
    falsify_claim,
    finish_run,
    propose_claim,
    rescope_claim_service,
    survive_claim,
)

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
                "trust_boundary": {"type": "string"},
                "requires_tags": {
                    "oneOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}},
                    ]
                },
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
                "surface_id": {"type": "string"},
                "source_claim_id": {"type": "string"},
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
                "surface_id": {"type": "string"},
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
        "description": "Mark a claim disproved (or `config_gated`) after running its falsification test.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "claim_id": {"type": "string"},
                "worker_id": {"type": "string"},
                "notes": {"type": "string"},
                "control_locus": {"type": "string"},
                "config_gate": {"type": "string"},
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
                "falsification_prediction": {"type": "string"},
                "falsification_test": {"type": "string"},
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
            return add_surface(
                conn,
                name=str(args["name"]),
                kind=str(args["kind"]),
                subsystem=str(args.get("subsystem") or ""),
                locus=str(args["locus"]),
                priority=str(args.get("priority", "high")),
                trust_boundary=str(args.get("trust_boundary") or ""),
                requires_tags=args.get("requires_tags"),
                actor="mcp",
            )
        if tool_name == "ajar_task_lease":
            leased = lease_next_task(
                conn,
                worker_id=str(args["worker_id"]),
                kind=args.get("kind"),
                recover=bool(args.get("recover", False)),
            )
            return {"leased": leased}
        if tool_name == "ajar_task_close":
            tid = str(args["task_id"])
            wid = str(args["worker_id"])
            outcome = str(args["outcome"]).strip()
            if outcome == "dry":
                return close_task_dry(
                    conn,
                    task_id=tid,
                    worker_id=wid,
                    locus=str(args.get("control_locus") or ""),
                    control_reason=str(args.get("control_reason") or ""),
                    target_dir=tpath,
                    target_mode=str(run["target_mode"] if run else "source"),
                )
            if outcome != "done":
                raise AjarError(f"Unsupported task close outcome {outcome!r}; choose 'done' or 'dry'.", EXIT_USER_ERROR)
            return close_task_done(
                conn,
                task_id=tid,
                worker_id=wid,
                summary=str(args.get("summary") or ""),
                target_dir=tpath,
            )
        if tool_name == "ajar_anomaly_add":
            return add_anomaly(
                conn,
                locus=str(args["locus"]),
                observation=str(args["observation"]),
                surface_id=args.get("surface_id"),
                source_claim_id=args.get("source_claim_id"),
                repro_cmd=str(args.get("repro_cmd") or ""),
                target_dir=tpath,
                actor="mcp",
            )
        if tool_name == "ajar_claim_propose":
            wid = str(args.get("worker_id") or args.get("worker") or "")
            return propose_claim(
                conn,
                worker_id=wid,
                title=str(args["title"]),
                locus=str(args["locus"]),
                mechanism=str(args["mechanism"]),
                falsification_prediction=str(args.get("falsification_prediction") or ""),
                falsification_test=str(args.get("falsification_test") or ""),
                surface_id=args.get("surface_id"),
                severity=str(args.get("severity", "high")),
                consume_anomaly_id=args.get("consume_anomaly_id"),
                target_dir=tpath,
                target_mode=str(run["target_mode"] if run else "source"),
            )
        if tool_name == "ajar_claim_falsify":
            wid = str(args.get("worker_id") or args.get("worker") or "")
            return falsify_claim(
                conn,
                claim_id=str(args["claim_id"]),
                worker_id=wid,
                notes=str(args["notes"]),
                control_locus=args.get("control_locus"),
                config_gate=str(args.get("config_gate") or ""),
            )
        if tool_name == "ajar_claim_survive":
            wid = str(args.get("worker_id") or args.get("worker") or "")
            return survive_claim(
                conn,
                claim_id=str(args["claim_id"]),
                worker_id=wid,
                notes=str(args["notes"]),
            )
        if tool_name == "ajar_claim_rescope":
            wid = str(args.get("worker_id") or args.get("worker") or "")
            return rescope_claim_service(
                conn,
                claim_id=str(args["claim_id"]),
                worker_id=wid,
                reason=str(args["reason"]),
                title=args.get("title"),
                locus=args.get("locus"),
                mechanism=args.get("mechanism"),
                severity=args.get("severity"),
                falsification_prediction=args.get("falsification_prediction"),
                falsification_test=args.get("falsification_test"),
            )
        if tool_name == "ajar_steer_list":
            return {"steers": list_steers(conn, active_only=bool(args.get("active_only", True)))}
        if tool_name == "ajar_export_graph":
            return export_attack_flow_graph(conn)
        if tool_name == "ajar_finish":
            return finish_run(conn, run_id=run_id, target_dir=tpath, actor="mcp")
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
        except AjarError as exc:
            err_payload = {
                "error": scrub_text(str(exc)),
                "error_type": type(exc).__name__,
                "exit_code": int(exc.exit_code),
                "details": json.loads(scrub_text(json.dumps(exc.details, sort_keys=True, default=str))),
            }
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(err_payload, indent=2, sort_keys=True)}],
                    "isError": True,
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
