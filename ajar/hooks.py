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
from ajar.store import compute_epistemic_delta, compute_epistemic_potential, immediate_tx

MAX_CONSECUTIVE_STALLS = 3


def evaluate_claude_stop_hook(
    conn: Any,
    *,
    target_dir: pathlib.Path | None = None,
) -> tuple[int, dict[str, Any]]:
    """Evaluate Claude Code `Stop` hook against `run.db` gates and Lyapunov `Phi(t)` stall counter.

    Returns `(exit_code, payload)`:
    - `0` allows the host session to stop cleanly (gates passed, already finished, or stalled 3x)
    - `2` blocks stop and returns specific missing closeout gates so the agent continues
    """
    run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
    if run is None or run["status"] in ("finished", "blocked"):
        ep_done = compute_epistemic_delta(conn, reference_actions=("stop_hook_check",)) if run is not None else {
            "epistemic_potential": 0.0,
            "delta_phi": 0.0,
        }
        return (
            EXIT_OK,
            {
                "decision": "approve",
                "reason": "Run is already finished or blocked.",
                "epistemic_potential": ep_done["epistemic_potential"],
                "delta_phi": ep_done["delta_phi"],
            },
        )

    gate_res = check_all_gates(conn, target_dir=target_dir, auto_enqueue_chain=True)
    if gate_res["passed"]:
        ep_pass = compute_epistemic_delta(conn, reference_actions=("stop_hook_check",))
        return (
            EXIT_OK,
            {
                "decision": "approve",
                "reason": "All closeout gates G1-G5 passed.",
                "epistemic_potential": ep_pass["epistemic_potential"],
                "delta_phi": ep_pass["delta_phi"],
            },
        )

    # Measure grounded Lyapunov progress `Delta Phi(t)` since previous stop check.
    with immediate_tx(conn):
        run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
        if run is None or run["status"] in ("finished", "blocked"):
            ep_done2 = compute_epistemic_delta(conn, reference_actions=("stop_hook_check",)) if run is not None else {
                "epistemic_potential": 0.0,
                "delta_phi": 0.0,
            }
            return (
                EXIT_OK,
                {
                    "decision": "approve",
                    "reason": "Run is already finished or blocked.",
                    "epistemic_potential": ep_done2["epistemic_potential"],
                    "delta_phi": ep_done2["delta_phi"],
                },
            )

        ep_state = compute_epistemic_delta(conn, reference_actions=("stop_hook_check",))
        max_ev = int(conn.execute("SELECT COALESCE(MAX(event_id), 0) AS m FROM events").fetchone()["m"])
        stalls = int(run["consecutive_stall_checks"] or 0)

        if not ep_state["has_prior_checkpoint"]:
            stalls = 0
        elif float(ep_state["delta_phi"]) <= 0.0:
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
            {
                "stalls": stalls,
                "blockers_count": len(gate_res["blockers"]),
                "epistemic_potential": ep_state["epistemic_potential"],
                "delta_phi": ep_state["delta_phi"],
                "components": ep_state["components"],
            },
        )

        if stalls >= MAX_CONSECUTIVE_STALLS:
            reason = (
                f"Released stalled host session after {stalls} consecutive stop checks with zero epistemic progress."
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
                    "epistemic_potential": ep_state["epistemic_potential"],
                    "delta_phi": ep_state["delta_phi"],
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
            "epistemic_potential": ep_state["epistemic_potential"],
            "delta_phi": ep_state["delta_phi"],
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
            before_phi = float(compute_epistemic_potential(conn)["epistemic_potential"])
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
            after_phi = float(compute_epistemic_potential(conn2)["epistemic_potential"])
            if after_phi <= before_phi:
                stalled_rounds += 1
            else:
                stalled_rounds = 0
            if stalled_rounds >= MAX_CONSECUTIVE_STALLS:
                return {
                    "completed": False,
                    "rounds_run": rounds_run,
                    "stalled": True,
                    "epistemic_potential": after_phi,
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
