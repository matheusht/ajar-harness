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
import re
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
from ajar.gates import (
    check_all_gates,
    compute_attribution_and_economics,
    evaluate_dry_surface_breaker,
)
from ajar.redact import scrub_text
from ajar.report import build_report_data, render_markdown_report
from ajar.workspace import init_run_workspace

REASON_TASK_KINDS: frozenset[str] = frozenset({"map", "falsify", "chain", "bridge", "patch", "escalate"})
REFUSAL_MARKERS: tuple[str, ...] = (
    "i cannot assist",
    "i can't assist",
    "i'm sorry, but i can't",
    "unable to help with",
    "cannot fulfill this request",
)

SOLILOQUY_FENCE_RE = re.compile(
    r"```(?:console|shell-session|bash|sh|gdb)?\n\s*(?:\$\s+\S+|\(gdb\)\s+\S+|root@\S+[:#])",
    re.IGNORECASE,
)


def detect_soliloquy_transcript(text: str, *, state_mutations_recorded: int = 0) -> tuple[bool, str]:
    """Detect fabricated shell/gdb transcripts (`OmegaPWN` anti-soliloquizing guard) or zero-tool monologues."""
    if not text:
        return (False, "")
    if state_mutations_recorded == 0 and SOLILOQUY_FENCE_RE.search(text):
        return (
            True,
            "Fabricated shell/debugger transcript detected with zero real execution or SQLite state mutations.",
        )
    est_tokens = len(text) // 4
    if state_mutations_recorded == 0 and est_tokens > 3000:
        return (
            True,
            f"Extended monologue ({est_tokens} est. tokens) with zero ajar state mutations; checkpoint and run real commands.",
        )
    return (False, "")


def select_model_for_task(task: dict[str, Any], *, fallback: bool = False) -> str:
    """Route tasks across reasoning (`map`/`falsify`/`chain`/`bridge`/`patch`/`escalate` + `zero_skill` `investigate`), hunting, and refusal fallback tiers."""
    default_model = os.environ.get("AJAR_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini"
    if fallback:
        return os.environ.get("AJAR_MODEL_FALLBACK", "").strip() or default_model
    kind = str(task.get("kind") or "investigate")
    skill_mode = str(task.get("skill_mode") or "domain")
    if kind in REASON_TASK_KINDS or (kind == "investigate" and skill_mode == "zero_skill"):
        return os.environ.get("AJAR_MODEL_REASON", "").strip() or default_model
    return os.environ.get("AJAR_MODEL_HUNT", "").strip() or default_model


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
    env["AJAR_TASK_DIRECTION"] = str(task.get("direction") or "outside_in")
    env["AJAR_WORKER_ID"] = worker_id
    env["AJAR_SKILL_MODE"] = str(task["skill_mode"])
    env["AJAR_SELECTED_MODEL"] = select_model_for_task(task)
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


def _call_chat_completion(base_url: str, api_key: str, model: str, context_md: str) -> dict[str, Any]:
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
        return json.loads(resp.read().decode("utf-8"))


def _invoke_openai_compatible_step(
    *,
    run_id: str,
    task: dict[str, Any],
    context_md: str,
) -> dict[str, Any]:
    """Minimal zero-dependency HTTPS worker call with role-tier routing and refusal fallback."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return {"skipped": True, "reason": "No --worker-cmd or OPENAI_API_KEY configured."}
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = select_model_for_task(task, fallback=False)
    payload = _call_chat_completion(base_url, api_key, model, context_md)
    choices = payload.get("choices") or []
    reply_text = str(((choices[0].get("message") or {}).get("content") or "") if choices else "").lower()

    used_fallback = False
    fallback_model = select_model_for_task(task, fallback=True)
    if fallback_model != model and any(marker in reply_text for marker in REFUSAL_MARKERS):
        payload = _call_chat_completion(base_url, api_key, fallback_model, context_md)
        model = fallback_model
        used_fallback = True

    usage = payload.get("usage") or {}
    return {
        "skipped": False,
        "model": model,
        "used_fallback": used_fallback,
        "tokens_in": int(usage.get("prompt_tokens", 0)),
        "tokens_out": int(usage.get("completion_tokens", 0)),
    }


def _seed_discover_passes(conn: Any, discover_passes: int) -> int:
    """Seed complementary Best-of-N discovery passes (`outside_in`, `inside_out`, `native_ffi`, `peer_symmetry`)."""
    n_passes = max(1, min(8, int(discover_passes)))
    now_iso = utc_now_iso()
    templates = [
        ("map", "outside_in", "critical", 90, "Map entrypoints, trust boundaries, and high-risk surfaces"),
        ("investigate", "inside_out", "high", 84, "Audit state-mutation, arithmetic, and privilege sinks inside-out"),
        ("investigate", "native_ffi", "high", 82, "Audit native FFI, unsafe memory boundaries, and parser sinks"),
        ("investigate", "peer_symmetry", "high", 80, "Audit sibling routes and peer lifecycle hooks for missing guards"),
    ]
    created = 0
    for idx in range(n_passes):
        kind, direction, prio, sal, base_title = templates[idx % len(templates)]
        title = base_title if idx < len(templates) else f"{base_title} (pass {idx + 1})"
        conn.execute(
            """
            INSERT INTO tasks(
                task_id, kind, direction, title, subsystem, locus, priority, status, salience_score, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'root', '', ?, 'open', ?, ?, ?)
            """,
            (new_id("task"), kind, direction, title, prio, sal - idx, now_iso, now_iso),
        )
        created += 1
    return created


def run_autonomous_schedule(
    *,
    target: str,
    run_id: str | None = None,
    target_mode: str = "source",
    goal: str = "Identify, falsify, and reproduce high-severity software vulnerabilities.",
    stopping_criterion: str = "exhaustive-high",
    campaign_phase: str = "hunt",
    budget_usd: float | None = None,
    workers: int = 2,
    discover_passes: int = 1,
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
            campaign_phase=campaign_phase,
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

        # Seed initial Best-of-N discovery passes if task board is empty.
        task_total = conn.execute("SELECT COUNT(*) AS c FROM tasks").fetchone()["c"]
        if int(task_total) == 0:
            _seed_discover_passes(conn, discover_passes)
    finally:
        conn.close()

    n_workers = max(1, int(workers))
    steps_executed = 0
    stop_reason = "max_steps_reached"
    verify_cutoff_triggered = False
    dry_breaker_events: list[dict[str, Any]] = []

    for step in range(max_steps):
        conn = open_run_db(rid, ajar_home=ajar_home)
        try:
            run_row = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
            econ = compute_attribution_and_economics(conn)
            spent = float(econ["total_spend_usd"])
            cap = float(run_row["budget_usd"])

            if cap > 0.0 and spent >= cap:
                stop_reason = "budget_cap_reached"
                conn.execute(
                    "UPDATE runs SET status = 'blocked', stop_reason = ?, finished_at = ?",
                    (stop_reason, utc_now_iso()),
                )
                break

            tripped = evaluate_dry_surface_breaker(conn)
            if tripped:
                dry_breaker_events.extend(tripped)

            # 80/20 Explore-vs-Verify Reserve Cutoff (active only when a finite budget cap exists):
            if cap > 0.0 and spent >= 0.80 * cap and run_row["status"] == "active":
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
        "discover_passes": max(1, int(discover_passes)),
        "stop_reason": stop_reason,
        "verify_cutoff_triggered": verify_cutoff_triggered,
        "dry_surface_breaker_events": dry_breaker_events,
        "gates_passed": bool(final_gates["passed"]),
        "findings_count": int(final_gates["findings_count"]),
        "economics": final_gates["economics"],
        "report_markdown_path": str(md_path),
        "report_json_path": str(js_path),
    }
