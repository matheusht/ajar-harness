"""Host Mode persistence adapters (`claude-stop` hook and `codex`/`omp` recovery loop).

Prevents premature Host Mode stopping while closeout gates `G1–G5` remain unmet,
with a 3-check zero-progress circuit breaker so stuck sessions never loop forever.
"""

from __future__ import annotations

import os
import pathlib
import shlex
import subprocess
from typing import Any

from ajar import EXIT_OK, EXIT_STALLED_RELEASE, EXIT_USER_ERROR
from ajar.db import log_event, open_run_db
from ajar.gates import check_all_gates
from ajar.redact import scrub_text

MAX_CONSECUTIVE_STALLS = 3


def evaluate_claude_stop_hook(
    conn: Any,
    *,
    target_dir: pathlib.Path | None = None,
) -> tuple[int, dict[str, Any]]:
    """Evaluate Claude Code `Stop` hook against `run.db` gates and stall counter.

    Returns `(exit_code, payload)`:
    - `0` allows the host session to stop cleanly (gates passed, already finished, or stalled 3x)
    - `2` blocks stop and returns specific missing closeout gates so the agent continues
    """
    run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
    if run is None or run["status"] in ("finished", "blocked"):
        return (EXIT_OK, {"decision": "approve", "reason": "Run is already finished or blocked."})

    gate_res = check_all_gates(conn, target_dir=target_dir, auto_enqueue_chain=True)
    if gate_res["passed"]:
        return (EXIT_OK, {"decision": "approve", "reason": "All closeout gates G1-G5 passed."})

    # Measure database progress since previous stop check (`events` monotonic `event_id`).
    max_ev = int(
        conn.execute("SELECT COALESCE(MAX(event_id), 0) AS m FROM events WHERE action != 'stop_hook_check'").fetchone()["m"]
    )
    prev_ev = int(run["last_stop_event_id"] or 0)
    stalls = int(run["consecutive_stall_checks"] or 0)

    if max_ev <= prev_ev:
        stalls += 1
    else:
        stalls = 0

    conn.execute(
        "UPDATE runs SET last_stop_event_id = ?, consecutive_stall_checks = ?",
        (max_ev, stalls),
    )
    log_event(
        conn,
        "host_hook",
        "stop_hook_check",
        run["run_id"],
        {"stalls": stalls, "blockers_count": len(gate_res["blockers"])},
    )

    if stalls >= MAX_CONSECUTIVE_STALLS:
        reason = (
            f"Released stalled host session after {stalls} consecutive stop checks with zero new run events."
        )
        conn.execute("UPDATE runs SET stop_reason = ? WHERE run_id = ?", (reason, run["run_id"]))
        return (
            EXIT_OK,
            {
                "decision": "approve",
                "stalled_release": True,
                "exit_hint": EXIT_STALLED_RELEASE,
                "reason": reason,
                "remaining_blockers": gate_res["blockers"][:6],
            },
        )

    summary = "; ".join(gate_res["blockers"][:5])
    return (
        EXIT_USER_ERROR,
        {
            "decision": "block",
            "reason": f"Run {run['run_id']} cannot finish yet: {summary}",
            "stalls": stalls,
            "blockers": gate_res["blockers"],
        },
    )


def run_host_continuation_loop(
    *,
    host_kind: str,
    run_id: str,
    cmd_template: str | None = None,
    max_rounds: int = 12,
    ajar_home: pathlib.Path | str | None = None,
) -> dict[str, Any]:
    """Outer continuation loop for `codex`, `omp`, or custom CLI host sessions."""
    rounds_run = 0
    stalled_rounds = 0
    last_event_id = 0

    default_templates: dict[str, str] = {
        "codex": "codex exec {prompt}",
        "omp": "omp run {prompt}",
    }
    template = cmd_template or default_templates.get(host_kind, "")
    if not template:
        return {
            "completed": False,
            "rounds_run": 0,
            "reason": f"Pass --cmd template for host {host_kind!r}.",
        }

    for round_idx in range(1, max_rounds + 1):
        conn = open_run_db(run_id, ajar_home=ajar_home)
        try:
            run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
            tpath = pathlib.Path(run["target_path"]) if run else None
            gate_res = check_all_gates(conn, target_dir=tpath, auto_enqueue_chain=True)
            if gate_res["passed"] or (run and run["status"] == "finished"):
                return {"completed": True, "rounds_run": rounds_run, "gates": gate_res}
            cur_event_id = int(conn.execute("SELECT COALESCE(MAX(event_id), 0) AS m FROM events").fetchone()["m"])
            ws_path = str(run["workspace_path"]) if run else "."
            blocker_prompt = "Continue Ajar run " + run_id + ". Remaining gates: " + " | ".join(gate_res["blockers"][:4])
        finally:
            conn.close()

        rounds_run = round_idx
        safe_prompt = shlex.quote(blocker_prompt)
        normalized_tpl = template.replace('"{prompt}"', "{prompt}").replace("'{prompt}'", "{prompt}")
        rendered_cmd = (
            normalized_tpl.format(prompt=safe_prompt, run_id=shlex.quote(run_id))
            if "{prompt}" in normalized_tpl or "{run_id}" in normalized_tpl
            else normalized_tpl
        )
        env = dict(os.environ)
        env["AJAR_RUN_ID"] = run_id
        env["AJAR_HOST_PROMPT"] = blocker_prompt
        subprocess.run(["bash", "-c", rendered_cmd], cwd=ws_path, env=env, check=False)

        conn2 = open_run_db(run_id, ajar_home=ajar_home)
        try:
            after_event_id = int(conn2.execute("SELECT COALESCE(MAX(event_id), 0) AS m FROM events").fetchone()["m"])
            if after_event_id <= cur_event_id and after_event_id <= last_event_id:
                stalled_rounds += 1
            else:
                stalled_rounds = 0
            last_event_id = after_event_id
            if stalled_rounds >= MAX_CONSECUTIVE_STALLS:
                return {
                    "completed": False,
                    "rounds_run": rounds_run,
                    "stalled": True,
                    "reason": scrub_text(f"Host loop stalled after {stalled_rounds} zero-progress rounds."),
                }
        finally:
            conn2.close()

    conn_end = open_run_db(run_id, ajar_home=ajar_home)
    try:
        final_gates = check_all_gates(conn_end)
    finally:
        conn_end.close()
    return {"completed": bool(final_gates["passed"]), "rounds_run": rounds_run, "gates": final_gates}
