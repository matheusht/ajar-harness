"""Standalone Product Mode Scheduler (`ajar run <target> --budget <USD>`).

Drives multi-worker autonomous verification over the exact same `run.db` engine
used in Host Mode, enforcing:
- `80/20` Explore-vs-Verify budget split (at `>= 80%` spend, halts new exploration
  and drains `proposed -> falsify` and `survived_falsify -> reproduce`)
- Zero-Skill First-Principles worker rotation (`worker-0` domain, `worker-1` zero_skill,
  `falsifier-k` dedicated fresh-context skeptic)
- Automatic `pulse` sweeps and final `report.md` + `report.json` export
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import urllib.request
from typing import Any

from ajar.db import (
    lease_next_task,
    log_event,
    new_id,
    open_run_db,
    render_task_context,
    run_dir_for,
    run_pulse,
    utc_now_iso,
)
from ajar.gates import check_all_gates, compute_attribution_and_economics
from ajar.redact import scrub_text
from ajar.report import build_report_data, render_markdown_report
from ajar.workspace import init_run_workspace


def _enqueue_verification_drain_tasks(conn: Any) -> int:
    """Ensure every `proposed` or `survived_falsify` claim has an open verification task."""
    created = 0
    now_iso = utc_now_iso()

    for c in conn.execute("SELECT * FROM claims WHERE status = 'proposed'").fetchall():
        existing = conn.execute(
            "SELECT 1 FROM tasks WHERE kind = 'falsify' AND status IN ('open', 'leased') AND summary LIKE ?",
            (f"%{c['claim_id']}%",),
        ).fetchone()
        if not existing:
            tid = new_id("task")
            conn.execute(
                """
                INSERT INTO tasks(
                    task_id, surface_id, kind, title, subsystem, locus, priority,
                    status, salience_score, summary, created_at, updated_at
                ) VALUES (?, ?, 'falsify', ?, ?, ?, ?, 'open', 92, ?, ?, ?)
                """,
                (
                    tid,
                    c["surface_id"],
                    f"Falsify claim {c['claim_id']}: {c['title'][:80]}",
                    c["subsystem"],
                    c["locus"],
                    c["severity"],
                    f"Verify or disprove {c['claim_id']} using falsification_test.",
                    now_iso,
                    now_iso,
                ),
            )
            created += 1

    for c in conn.execute("SELECT * FROM claims WHERE status = 'survived_falsify'").fetchall():
        existing = conn.execute(
            "SELECT 1 FROM tasks WHERE kind = 'reproduce' AND status IN ('open', 'leased') AND summary LIKE ?",
            (f"%{c['claim_id']}%",),
        ).fetchone()
        if not existing:
            tid = new_id("task")
            conn.execute(
                """
                INSERT INTO tasks(
                    task_id, surface_id, kind, title, subsystem, locus, priority,
                    status, salience_score, summary, created_at, updated_at
                ) VALUES (?, ?, 'reproduce', ?, ?, ?, ?, 'open', 95, ?, ?, ?)
                """,
                (
                    tid,
                    c["surface_id"],
                    f"Reproduce claim {c['claim_id']} with 4-arm proof",
                    c["subsystem"],
                    c["locus"],
                    c["severity"],
                    f"Execute 4-arm counterfactual reproduction for {c['claim_id']}.",
                    now_iso,
                    now_iso,
                ),
            )
            created += 1
    return created


def _invoke_worker_cmd(
    worker_cmd: str,
    *,
    run_id: str,
    workspace_path: pathlib.Path,
    task: dict[str, Any],
    worker_id: str,
    ajar_home: pathlib.Path | str | None,
) -> dict[str, Any]:
    env = dict(os.environ)
    env["AJAR_RUN_ID"] = run_id
    env["AJAR_TASK_ID"] = str(task["task_id"])
    env["AJAR_TASK_KIND"] = str(task["kind"])
    env["AJAR_WORKER_ID"] = worker_id
    env["AJAR_SKILL_MODE"] = str(task["skill_mode"])
    env["AJAR_WORKSPACE"] = str(workspace_path)
    if ajar_home is not None:
        env["AJAR_HOME"] = str(ajar_home)

    repo_bin = pathlib.Path(__file__).resolve().parents[1] / "bin"
    env["PATH"] = f"{repo_bin}:{env.get('PATH', '')}"

    proc = subprocess.run(
        ["bash", "-c", worker_cmd],
        cwd=str(workspace_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    return {
        "exit_code": int(proc.returncode),
        "stdout": scrub_text(proc.stdout[:2000]),
        "stderr": scrub_text(proc.stderr[:2000]),
    }


def _invoke_openai_compatible_step(
    *,
    run_id: str,
    task: dict[str, Any],
    context_md: str,
) -> dict[str, Any]:
    """Minimal zero-dependency HTTPS worker call when OPENAI_API_KEY is configured."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return {"skipped": True, "reason": "No --worker-cmd or OPENAI_API_KEY configured."}
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("AJAR_MODEL", "gpt-4.1-mini")

    body = json.dumps(
        {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are an Ajar security verification worker. Output concise JSON summary.",
                },
                {"role": "user", "content": context_md},
            ],
            "max_tokens": 400,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    usage = payload.get("usage") or {}
    return {
        "skipped": False,
        "model": model,
        "tokens_in": int(usage.get("prompt_tokens", 0)),
        "tokens_out": int(usage.get("completion_tokens", 0)),
    }


def run_autonomous_schedule(
    *,
    target: str,
    run_id: str | None = None,
    target_mode: str = "source",
    goal: str = "Identify, falsify, and reproduce high-severity software vulnerabilities.",
    stopping_criterion: str = "exhaustive-high",
    budget_usd: float = 40.0,
    workers: int = 2,
    worker_cmd: str | None = None,
    max_steps: int = 50,
    ajar_home: pathlib.Path | str | None = None,
) -> dict[str, Any]:
    """Run the Standalone `ajar run` scheduler with 80/20 verification budget reserve."""
    rdir_existing = run_dir_for(run_id, ajar_home) if run_id else None
    if rdir_existing is not None and (rdir_existing / "run.db").is_file():
        rid = str(run_id)
    else:
        init_info = init_run_workspace(
            target=target,
            target_mode=target_mode,
            workspace_mode="envelope",
            goal=goal,
            stopping_criterion=stopping_criterion,
            budget_usd=budget_usd,
            run_id=run_id,
            ajar_home=ajar_home,
        )
        rid = str(init_info["run_id"])

    rdir = run_dir_for(rid, ajar_home)
    conn = open_run_db(rid, ajar_home=ajar_home)
    try:
        run_row = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
        ws_path = pathlib.Path(run_row["workspace_path"])
        tpath = pathlib.Path(run_row["target_path"])

        # Seed initial `map` task if task board is empty.
        task_total = conn.execute("SELECT COUNT(*) AS c FROM tasks").fetchone()["c"]
        if int(task_total) == 0:
            now_iso = utc_now_iso()
            conn.execute(
                """
                INSERT INTO tasks(
                    task_id, kind, title, subsystem, locus, priority, status, salience_score, created_at, updated_at
                ) VALUES (?, 'map', 'Map entrypoints, trust boundaries, and high-risk surfaces', 'root', '', 'critical', 'open', 90, ?, ?)
                """,
                (new_id("task"), now_iso, now_iso),
            )
    finally:
        conn.close()

    n_workers = max(1, int(workers))
    steps_executed = 0
    stop_reason = "max_steps_reached"
    verify_cutoff_triggered = False

    for step in range(max_steps):
        conn = open_run_db(rid, ajar_home=ajar_home)
        try:
            run_row = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
            econ = compute_attribution_and_economics(conn)
            spent = float(econ["total_spend_usd"])
            cap = float(run_row["budget_usd"])

            if spent >= cap:
                stop_reason = "budget_cap_reached"
                conn.execute(
                    "UPDATE runs SET status = 'blocked', stop_reason = ?, finished_at = ?",
                    (stop_reason, utc_now_iso()),
                )
                break

            # 80/20 Explore-vs-Verify Reserve Cutoff:
            if spent >= 0.80 * cap and run_row["status"] == "active":
                verify_cutoff_triggered = True
                conn.execute("UPDATE runs SET status = 'verify_only'")
                drained = _enqueue_verification_drain_tasks(conn)
                log_event(
                    conn,
                    "scheduler",
                    "verify_only_cutoff",
                    rid,
                    {"spent_usd": spent, "budget_usd": cap, "enqueued_verification_tasks": drained},
                )
            else:
                _enqueue_verification_drain_tasks(conn)

            gates = check_all_gates(conn, target_dir=tpath, auto_enqueue_chain=True)
            if gates["passed"]:
                stop_reason = "all_gates_passed"
                conn.execute(
                    "UPDATE runs SET status = 'finished', stop_reason = ?, finished_at = ?",
                    (stop_reason, utc_now_iso()),
                )
                log_event(conn, "scheduler", "run_finished", rid, {})
                break

            # Pick worker ID: use dedicated `falsifier-0` when open `falsify` tasks exist.
            open_falsify = conn.execute(
                "SELECT proposer_worker_id FROM claims WHERE status = 'proposed' LIMIT 1"
            ).fetchone()
            if open_falsify is not None:
                prop_id = str(open_falsify["proposer_worker_id"])
                wid = "falsifier-1" if prop_id == "falsifier-0" else "falsifier-0"
                leased = lease_next_task(conn, worker_id=wid, kind="falsify")
                if leased is None:
                    wid = f"worker-{step % n_workers}"
                    leased = lease_next_task(conn, worker_id=wid)
            else:
                wid = f"worker-{step % n_workers}"
                leased = lease_next_task(conn, worker_id=wid)

            if leased is None:
                # Re-check gates when queue is empty.
                gates_after = check_all_gates(conn, target_dir=tpath, auto_enqueue_chain=True)
                if gates_after["passed"]:
                    stop_reason = "all_gates_passed"
                    conn.execute(
                        "UPDATE runs SET status = 'finished', stop_reason = ?, finished_at = ?",
                        (stop_reason, utc_now_iso()),
                    )
                else:
                    stop_reason = (
                        "verify_queue_drained"
                        if run_row["status"] == "verify_only"
                        else "no_leasable_tasks_gates_unmet"
                    )
                    conn.execute("UPDATE runs SET stop_reason = ?", (stop_reason,))
                break

            ctx = render_task_context(conn, str(leased["task_id"]))
        finally:
            conn.close()

        steps_executed += 1
        if worker_cmd:
            _invoke_worker_cmd(
                worker_cmd,
                run_id=rid,
                workspace_path=ws_path,
                task=leased,
                worker_id=wid,
                ajar_home=ajar_home,
            )
        else:
            api_res = _invoke_openai_compatible_step(run_id=rid, task=leased, context_md=ctx["rendered"])
            if api_res.get("skipped"):
                stop_reason = "no_worker_backend_configured"
                break

        if steps_executed % 8 == 0:
            c_pulse = open_run_db(rid, ajar_home=ajar_home)
            try:
                run_pulse(c_pulse, target_dir=tpath)
            finally:
                c_pulse.close()

    # Render final report artifacts (`report.md` and `report.json`).
    conn_final = open_run_db(rid, ajar_home=ajar_home)
    try:
        md_report = render_markdown_report(conn_final)
        json_report = build_report_data(conn_final, include_rejected_appendix=True)
        final_gates = check_all_gates(conn_final, auto_enqueue_chain=False)
    finally:
        conn_final.close()

    art_dir = rdir / "artifacts"
    art_dir.mkdir(parents=True, exist_ok=True)
    md_path = art_dir / "report.md"
    js_path = art_dir / "report.json"
    md_path.write_text(md_report, encoding="utf-8")
    js_path.write_text(json.dumps(json_report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return {
        "run_id": rid,
        "steps_executed": steps_executed,
        "stop_reason": stop_reason,
        "verify_cutoff_triggered": verify_cutoff_triggered,
        "gates_passed": bool(final_gates["passed"]),
        "findings_count": int(final_gates["findings_count"]),
        "economics": final_gates["economics"],
        "report_markdown_path": str(md_path),
        "report_json_path": str(js_path),
    }
