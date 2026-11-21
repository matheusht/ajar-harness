"""Swarm Packet Dispatcher, Wire-Profile Fallback Ladder, Prose Hygiene & Run Reopen (`Ajar v3.2.2`).

Implements empirical multi-agent coordination safeguards:
- Stage-split `"Just-Enough-Context"` worker packets (`ajar swarm packet`) using `direct`
  `"Swarm Worker"` tuples `(id, severity, file:line)` as the engagement-wide default.
- Deterministic `--wire-profile` fallback ladder (`direct -> swarm_patch_first -> regression_tdd`)
  stepped only when a worker stalls/refuses (`ajar swarm fallback`), excluding noisy `qa_persona`.
- Structural claim prose validation (blocking shellcode/hook payload literals in `run.db`).
- Policy-refusal `ajar claim block` rejection (`ENV_BLOCKER_KINDS` hardware/service/OS gates only).
- Hybrid Local-SSD build cache (`/tmp/ajar-build-cache/<run_id>`) + Shared-Ledger mirroring
  (`/shared/user/.gemini/ajar/runs/<run_id>`) and fresh-VM `ajar reopen`.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import sqlite3
import subprocess
from typing import Any, Sequence

from ajar import EXIT_USER_ERROR
from ajar.db import (
    AjarError,
    get_ajar_home,
    log_event,
    new_id,
    open_run_db,
    run_dir_for,
    utc_now_iso,
)
from ajar.redact import scrub_text, scrubbed_subprocess_env

WIRE_PROFILE_LADDER: tuple[str, ...] = ("direct", "swarm_patch_first", "regression_tdd")
VALID_SWARM_STAGES: tuple[str, ...] = ("investigate", "falsify", "reproduce", "chain", "bridge", "portfolio")
VALID_FALLBACK_REASONS: tuple[str, ...] = ("idle_no_return", "filter_blocked", "refused")

ENV_BLOCKER_KINDS: tuple[str, ...] = (
    "missing_hardware",
    "external_service",
    "privileged_kernel",
    "license_or_key",
    "host_os_mismatch",
)
ZERO_ATTEMPT_EXEMPT_ENV_BLOCKERS: frozenset[str] = frozenset(
    {"missing_hardware", "privileged_kernel", "host_os_mismatch"}
)

WEAPONIZED_CLAIM_PROSE_RE = re.compile(
    r"(?:#!/bin/(?:ba)?sh\b"
    r"|\.git/hooks/(?:post-checkout|post-merge|pre-commit|post-rewrite|fsmonitor-watchman)"
    r"|/dev/tcp/[0-9A-Za-z._-]+"
    r"|\bbash\s+-i\s+>&"
    r"|\bnc\s+-e\s+/bin/(?:ba)?sh)",
    re.IGNORECASE,
)

LEGACY_HOOK_TAIL_SENTENCE_RE = re.compile(
    r"[^.!?\n]*(?:\.git/hooks/(?:post-checkout|post-merge|pre-commit|post-rewrite)|#!/bin/(?:ba)?sh)[^.!?\n]*[.!?]?",
    re.IGNORECASE,
)

POLICY_REFUSAL_BLOCK_RE = re.compile(
    r"(?:\bwithheld\b"
    r"|\bsafety\s+policy\b"
    r"|\bdefensive\s+(?:safety\s+)?policy\b"
    r"|\bpolicy\s+restriction\b"
    r"|\bstatically\s+verified\b"
    r"|\bconceptual\s+placeholder\b"
    r"|\brefus(?:ed|al)\b"
    r"|\bweaponized\b)",
    re.IGNORECASE,
)

STAGE_ROLE_LABELS: dict[str, str] = {
    "investigate": "Swarm Investigator",
    "falsify": "Swarm Falsifier",
    "reproduce": "Swarm Reproducer",
    "chain": "Swarm Chain Worker",
    "bridge": "Swarm Bridge Hunter",
    "portfolio": "Swarm Portfolio Coordinator",
}

STAGE_SKILL_PATHS: dict[str, str] = {
    "investigate": "skills/ajar-investigate/SKILL.md",
    "falsify": "skills/ajar-falsify/SKILL.md",
    "reproduce": "skills/ajar-reproduce/SKILL.md",
    "chain": "skills/ajar-chain/SKILL.md",
    "bridge": "skills/ajar-chain/SKILL.md",
    "portfolio": "skills/ajar-investigate/SKILL.md",
}


def validate_structural_claim_prose(*texts: str | None) -> tuple[bool, str]:
    """Ensure `claims` prose states structural code transitions without shellcode or OS hook payloads."""
    for raw in texts:
        if not raw:
            continue
        m = WEAPONIZED_CLAIM_PROSE_RE.search(raw)
        if m:
            return (
                False,
                f"structural_prose_gate: claim text embeds shellcode or post-exploitation hook literal ({m.group(0)!r}). "
                "State structural code transitions and boundary violations (for example `prepare_symlink_changes skips "
                "SYMLINK_IN_RESULT when old_mode == 0`), not OS hook shell payloads.",
            )
    return (True, "ok")


def scrub_weaponized_hook_prose(text: str) -> tuple[str, bool]:
    """Strip legacy post-exploitation `.git/hooks/*` or `#!/bin/sh` tails when reopening older runs."""
    if not text or not WEAPONIZED_CLAIM_PROSE_RE.search(text):
        return (text, False)
    cleaned = LEGACY_HOOK_TAIL_SENTENCE_RE.sub("", text)
    cleaned = WEAPONIZED_CLAIM_PROSE_RE.sub("[structural-boundary-impact]", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    if not cleaned:
        cleaned = "Structural boundary invariant violation at claimed locus."
    return (cleaned, cleaned != text)


def validate_claim_block_request(
    claim_row: sqlite3.Row | dict[str, Any],
    *,
    reason: str,
    env_blocker: str,
    target_mode: str = "source",
) -> tuple[bool, str]:
    """Reject safety-policy / refusal deferrals on `ajar claim block`; enforce concrete `env_blocker`."""
    clean_env = (env_blocker or "").strip()
    if clean_env not in ENV_BLOCKER_KINDS:
        return (
            False,
            f"Invalid or missing --env-blocker {clean_env!r}; must be one of {', '.join(ENV_BLOCKER_KINDS)}.",
        )
    if len((reason or "").strip()) < 15:
        return (False, "Block --reason must describe the concrete environmental constraint (>= 15 chars).")
    if POLICY_REFUSAL_BLOCK_RE.search(reason or ""):
        return (
            False,
            "policy_refusal_block_rejected: safety-policy deferral, static-only review, or model refusal is never a valid "
            "`blocked` state. Re-dispatch verification via `ajar swarm fallback` (`swarm_patch_first` -> `regression_tdd`).",
        )
    if target_mode == "source" and clean_env not in ZERO_ATTEMPT_EXEMPT_ENV_BLOCKERS:
        fails = int(claim_row["failed_repro_count"] or 0)
        inst = int(claim_row["instrumented_since_fail"] or 0)
        if fails < 1 and inst < 1:
            return (
                False,
                f"zero_attempt_block_rejected: source claim {claim_row['claim_id']} has 0 reproduction/instrumentation attempts "
                f"and cannot be marked blocked under --env-blocker={clean_env!r} without first attempting `ajar claim reproduce` "
                "or `ajar claim instrument`.",
            )
    return (True, "ok")


def _profile_batch_cap(profile: str, requested_limit: int) -> int:
    req = max(1, int(requested_limit))
    if profile == "regression_tdd":
        return 1
    if profile == "swarm_patch_first":
        return min(req, 2)
    return req


def _resolve_auto_profile_for_items(conn: sqlite3.Connection, stage: str, item_ids: Sequence[str]) -> str:
    """Resolve highest wire-profile tier previously escalated for any of `item_ids`."""
    rows = conn.execute(
        "SELECT wire_profile, item_ids_json, status FROM swarm_dispatches WHERE stage = ? ORDER BY created_at ASC",
        (stage,),
    ).fetchall()
    target_set = set(item_ids)
    max_idx = 0
    for r in rows:
        try:
            r_items = set(json.loads(r["item_ids_json"] or "[]"))
        except json.JSONDecodeError:
            r_items = set()
        if not (r_items & target_set):
            continue
        prof = str(r["wire_profile"] or "direct")
        idx = WIRE_PROFILE_LADDER.index(prof) if prof in WIRE_PROFILE_LADDER else 0
        status = str(r["status"] or "")
        if status in VALID_FALLBACK_REASONS:
            idx = min(idx + 1, len(WIRE_PROFILE_LADDER) - 1)
        if idx > max_idx:
            max_idx = idx
    return WIRE_PROFILE_LADDER[max_idx]


def _select_stage_items(
    conn: sqlite3.Connection,
    *,
    stage: str,
    explicit_ids: Sequence[str] = (),
    limit: int = 4,
) -> list[dict[str, str]]:
    clean_explicit = [i.strip() for i in explicit_ids if i and i.strip()]
    items: list[dict[str, str]] = []
    cap = max(1, int(limit))

    if stage in ("falsify", "reproduce"):
        if clean_explicit:
            placeholders = ",".join("?" for _ in clean_explicit)
            rows = conn.execute(
                f"SELECT claim_id, severity, locus, status FROM claims WHERE claim_id IN ({placeholders})",
                tuple(clean_explicit),
            ).fetchall()
        elif stage == "falsify":
            rows = conn.execute(
                """
                SELECT claim_id, severity, locus, status FROM claims
                WHERE status = 'proposed'
                ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, created_at ASC
                LIMIT ?
                """,
                (cap,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT claim_id, severity, locus, status FROM claims
                WHERE status IN ('survived_falsify', 'needs_instrumentation')
                ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, created_at ASC
                LIMIT ?
                """,
                (cap,),
            ).fetchall()
        for r in rows:
            items.append(
                {
                    "id": str(r["claim_id"]),
                    "priority": str(r["severity"]),
                    "locus": str(r["locus"]),
                    "status": str(r["status"]),
                }
            )
        return items

    if stage == "portfolio":
        # Multi-lane portfolio reservation: 1 woken chain + 1 verify + 1 bridge + greenfield investigate.
        woken_ch = conn.execute(
            "SELECT task_id, priority, locus, title, status FROM tasks WHERE kind = 'chain' AND status = 'open' ORDER BY salience_score DESC LIMIT 1"
        ).fetchone()
        if woken_ch is not None and len(items) < cap:
            items.append({"id": str(woken_ch["task_id"]), "priority": f"chain:{woken_ch['priority']}", "locus": str(woken_ch["locus"] or woken_ch["title"]), "status": "open"})

        ver_clm = conn.execute(
            "SELECT claim_id, severity, locus, status FROM claims WHERE status IN ('proposed', 'survived_falsify') ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        if ver_clm is not None and len(items) < cap:
            lane = "falsify" if str(ver_clm["status"]) == "proposed" else "reproduce"
            items.append({"id": str(ver_clm["claim_id"]), "priority": f"{lane}:{ver_clm['severity']}", "locus": str(ver_clm["locus"]), "status": str(ver_clm["status"])})

        br_task = conn.execute(
            "SELECT task_id, priority, locus, title, status FROM tasks WHERE kind = 'bridge' AND status = 'open' ORDER BY salience_score DESC LIMIT 1"
        ).fetchone()
        if br_task is not None and len(items) < cap:
            items.append({"id": str(br_task["task_id"]), "priority": f"bridge:{br_task['priority']}", "locus": str(br_task["locus"] or br_task["title"]), "status": "open"})

        inv_rows = conn.execute(
            "SELECT task_id, priority, locus, title, status FROM tasks WHERE kind IN ('investigate', 'map') AND status = 'open' ORDER BY salience_score DESC, created_at ASC LIMIT ?",
            (cap,),
        ).fetchall()
        for ir in inv_rows:
            if len(items) >= cap:
                break
            items.append({"id": str(ir["task_id"]), "priority": f"investigate:{ir['priority']}", "locus": str(ir["locus"] or ir["title"]), "status": "open"})
        return items

    if stage == "bridge":
        if clean_explicit:
            placeholders = ",".join("?" for _ in clean_explicit)
            brows = conn.execute(
                f"SELECT task_id, priority, locus, title, status FROM tasks WHERE task_id IN ({placeholders})",
                tuple(clean_explicit),
            ).fetchall()
        else:
            brows = conn.execute(
                "SELECT task_id, priority, locus, title, status FROM tasks WHERE kind = 'bridge' AND status IN ('open', 'leased') ORDER BY salience_score DESC, created_at ASC LIMIT ?",
                (cap,),
            ).fetchall()
        for r in brows:
            items.append({"id": str(r["task_id"]), "priority": str(r["priority"]), "locus": str(r["locus"] or r["title"]), "status": str(r["status"])})
        if not items:
            drows = conn.execute(
                "SELECT door_id, status, anchor_locus FROM parked_doors WHERE status IN ('bridging', 'parked') ORDER BY updated_at DESC LIMIT ?",
                (cap,),
            ).fetchall()
            for dr in drows:
                items.append({"id": str(dr["door_id"]), "priority": "high", "locus": str(dr["anchor_locus"]), "status": str(dr["status"])})
        return items

    if stage == "chain":
        if clean_explicit:
            for eid in clean_explicit[:cap]:
                prow = conn.execute("SELECT primitive_id, kind, locus FROM primitives WHERE primitive_id = ?", (eid,)).fetchone()
                if prow:
                    items.append({"id": str(prow["primitive_id"]), "priority": str(prow["kind"]), "locus": str(prow["locus"]), "status": "unchained"})
                    continue
                frow = conn.execute("SELECT finding_id, severity, locus FROM findings WHERE finding_id = ?", (eid,)).fetchone()
                if frow:
                    items.append({"id": str(frow["finding_id"]), "priority": str(frow["severity"]), "locus": str(frow["locus"]), "status": "reproduced"})
                    continue
                drow = conn.execute("SELECT door_id, status, anchor_locus FROM parked_doors WHERE door_id = ?", (eid,)).fetchone()
                if drow:
                    items.append({"id": str(drow["door_id"]), "priority": "door", "locus": str(drow["anchor_locus"]), "status": str(drow["status"])})
                    continue
                arow = conn.execute("SELECT anomaly_id, locus, status FROM anomalies WHERE anomaly_id = ?", (eid,)).fetchone()
                if arow:
                    items.append({"id": str(arow["anomaly_id"]), "priority": "anomaly", "locus": str(arow["locus"]), "status": str(arow["status"])})
                    continue
                trow = conn.execute("SELECT task_id, priority, locus, title, status FROM tasks WHERE task_id = ?", (eid,)).fetchone()
                if trow:
                    items.append({"id": str(trow["task_id"]), "priority": str(trow["priority"]), "locus": str(trow["locus"] or trow["title"]), "status": str(trow["status"])})
            return items

        for rd in conn.execute("SELECT door_id, anchor_locus FROM parked_doors WHERE status = 'ready' ORDER BY updated_at DESC LIMIT ?", (cap,)).fetchall():
            if len(items) < cap:
                items.append({"id": str(rd["door_id"]), "priority": "ready_door", "locus": str(rd["anchor_locus"]), "status": "ready"})
        for r in conn.execute("SELECT primitive_id, kind, locus FROM primitives WHERE chained = 0 AND status != 'dry' ORDER BY created_at ASC LIMIT ?", (cap,)).fetchall():
            if len(items) < cap:
                items.append({"id": str(r["primitive_id"]), "priority": str(r["kind"]), "locus": str(r["locus"]), "status": "unchained"})
        for f in conn.execute("SELECT finding_id, severity, locus FROM findings ORDER BY created_at ASC LIMIT ?", (cap,)).fetchall():
            if len(items) < cap:
                items.append({"id": str(f["finding_id"]), "priority": str(f["severity"]), "locus": str(f["locus"]), "status": "reproduced"})
        if items:
            return items

    # `investigate` (or fallback `chain` tasks when no primitives/findings match)
    if clean_explicit:
        placeholders = ",".join("?" for _ in clean_explicit)
        trows = conn.execute(
            f"SELECT task_id, priority, locus, title, status FROM tasks WHERE task_id IN ({placeholders})",
            tuple(clean_explicit),
        ).fetchall()
    else:
        trows = conn.execute(
            """
            SELECT task_id, priority, locus, title, status FROM tasks
            WHERE kind = ? AND status IN ('open', 'leased')
            ORDER BY salience_score DESC, created_at ASC
            LIMIT ?
            """,
            (stage, cap),
        ).fetchall()
    for r in trows:
        items.append(
            {
                "id": str(r["task_id"]),
                "priority": str(r["priority"]),
                "locus": str(r["locus"] or r["title"]),
                "status": str(r["status"]),
            }
        )
    return items


def _render_packet_markdown(
    *,
    run_id: str,
    target_path: str,
    stage: str,
    wire_profile: str,
    worker_id: str,
    dispatch_id: str,
    items: Sequence[dict[str, str]],
) -> str:
    role_title = (
        "Swarm Verification Worker"
        if wire_profile == "regression_tdd"
        else STAGE_ROLE_LABELS.get(stage, "Swarm Worker")
    )
    skill_rel = STAGE_SKILL_PATHS.get(stage, f"skills/ajar-{stage}/SKILL.md")
    id_csv = ", ".join(f"'{it['id']}'" for it in items)
    bullets = "\n".join(f"- `{it['id']}` (`{it['priority']}`, `{it['locus']}`)" for it in items)

    lines: list[str] = [
        f"You are {role_title} (`worker_id = {worker_id}`, `dispatch_id = {dispatch_id}`) on Ajar campaign `{run_id}` targeting `{target_path}`.",
        "",
        "## Mandatory First Steps",
        f"1. Read `{skill_rel}`.",
        f"2. In every shell command, export `AJAR_RUN_ID={run_id}` and `AJAR_BUILD_CACHE_ROOT=/tmp/ajar-build-cache`.",
        f"3. Keep `{target_path}` untouched (`git -C {target_path} status --porcelain` must remain empty). Make zero live network calls.",
        "",
        f"## Assigned Scope (`wire_profile = {wire_profile}`, {len(items)} item(s))",
        bullets,
        "",
    ]

    if stage in ("falsify", "reproduce"):
        lines.append(
            f"Query `run.db` (`SELECT claim_id, title, locus, mechanism, falsification_prediction, falsification_test FROM claims WHERE claim_id IN ({id_csv})`) and inspect the exact source lines in `{target_path}`."
        )
    elif stage == "chain":
        lines.append(
            f"Run `ajar chain frontier` and inspect `{target_path}` for `{id_csv}` (`fnd-*`, `prim-*`, and `ready` Open Doors)."
        )
    elif stage == "bridge":
        lines.append(
            f"Load `ajar context --task <task_id>` and `ajar door list`; hunt the missing link in `{target_path}` without forcing speculative prose."
        )
    else:
        lines.append(
            f"Load `ajar context --task <task_id>` for each assigned task and audit the exact call cone in `{target_path}`."
        )
    lines.append("")

    if wire_profile == "swarm_patch_first":
        lines.extend(
            [
                "## Patch-First Execution Protocol",
                "1. Author the minimal root-cause unified diff (`1-12` changed lines at the claimed locus) in `$AJAR_RUN_DIR/artifacts/` BEFORE writing the runtime verification harness.",
                "2. Build and execute the real target binary/test entrypoint inside isolated `repro/slot-<k>` via `ajar claim reproduce` (or `ajar chain propose`).",
                "3. Never use `<conceptual_placeholder>`, static source-file grepping, or standalone `.o` stub linking on non-library surfaces.",
            ]
        )
    elif wire_profile == "regression_tdd":
        lines.extend(
            [
                "## Root-Cause Differential Regression Protocol",
                "1. Author the minimal root-cause fix diff (`micropatch.diff`) enforcing the structural boundary invariant at the assigned locus.",
                "2. Write a deterministic local boundary regression test + normal control test exercising the compiled target binary inside `repro/slot-<k>`.",
                "3. Run `ajar claim reproduce` (4-arm differential check: unpatched fails invariant, patched holds invariant, control passes on both). Never substitute `<conceptual_placeholder>` or static source-text checks.",
            ]
        )
    else:
        if stage in ("investigate", "portfolio"):
            lines.extend(
                [
                    "## Stage Rules",
                    "- Derive conservation, state-machine, and boundary invariants directly from code; record both capability bugs and `trust_gadget` steps (`ajar primitive add --role trust_gadget`).",
                    "- Park deep blocked sinks via `ajar door park` and record claims using concise structural state transitions (zero shellcode or OS hook payload literals).",
                ]
            )
        elif stage == "bridge":
            lines.extend(
                [
                    "## Stage Rules",
                    "- Check whether the assigned cone breaks the Open Door's `blocker_locus` or emits its missing state (`ajar primitive add` / `ajar claim propose`).",
                    "- Obey the hook Kill Rule: close `dry` cleanly if the cone sanitizes state inline.",
                ]
            )
        elif stage == "falsify":
            lines.extend(
                [
                    "## Stage Rules",
                    f"- Enforce independent falsifier separation (`--worker {worker_id}` != `proposer_worker_id`).",
                    "- Disprove via concrete code guards (`ajar claim falsify --control-locus ...`) or promote (`ajar claim survive`).",
                ]
            )
        elif stage == "chain":
            lines.extend(
                [
                    "## Stage Rules",
                    "- Probe post-state snapshots (`ajar chain probe --from-snapshot <snp_id>`) and compose `fnd-*`/`prim-*` steps directly via `ajar chain propose` (micropatches auto-inherit).",
                    "- Never inject self-override CLI/env flags in `--poc-cmd`, `<conceptual_placeholder>`, or static source grepping.",
                ]
            )
        else:
            lines.extend(
                [
                    "## Stage Rules",
                    f"- Smoke-test builds strike-free via `ajar repro try`, then verify via `ajar claim reproduce --worker {worker_id}` (`--save-post-state <dir>` when producing reusable state).",
                    "- Exercise the real target binary/CLI entrypoint (`make` / `cargo` / `go` / `forge`); never link synthetic `main()` C stubs against internal `.o`/`.a` on non-library surfaces.",
                    "- Never mark a source claim `blocked` for policy/refusal reasons.",
                ]
            )

    lines.extend(
        [
            "",
            f"When finished, run `ajar swarm complete {dispatch_id}` and report concise per-item outcomes.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_swarm_packet(
    conn: sqlite3.Connection,
    *,
    stage: str,
    wire_profile: str = "auto",
    item_ids: Sequence[str] = (),
    limit: int = 4,
    worker_id: str = "",
) -> dict[str, Any]:
    """Generate and persist a stripped `"Just-Enough-Context"` worker assignment packet."""
    if stage not in VALID_SWARM_STAGES:
        raise AjarError(f"Invalid --stage {stage!r}; expected one of {VALID_SWARM_STAGES}.", EXIT_USER_ERROR)
    if wire_profile != "auto" and wire_profile not in WIRE_PROFILE_LADDER:
        raise AjarError(
            f"Invalid --wire-profile {wire_profile!r}; expected 'auto' or one of {WIRE_PROFILE_LADDER}.",
            EXIT_USER_ERROR,
        )

    run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
    if run is None:
        raise AjarError("Run metadata missing in run.db.", EXIT_USER_ERROR)
    run_id = str(run["run_id"])
    target_path = str(run["target_path"])

    candidates = _select_stage_items(conn, stage=stage, explicit_ids=item_ids, limit=limit)
    if not candidates:
        raise AjarError(
            f"No eligible items found for stage={stage!r} (explicit_ids={list(item_ids)}).",
            EXIT_USER_ERROR,
        )

    cand_ids = [c["id"] for c in candidates]
    resolved_profile = (
        _resolve_auto_profile_for_items(conn, stage, cand_ids) if wire_profile == "auto" else wire_profile
    )
    cap = _profile_batch_cap(resolved_profile, limit)
    selected = candidates[:cap]
    selected_ids = [c["id"] for c in selected]

    dispatch_id = new_id("dsp")
    eff_worker = (worker_id or "").strip() or f"w-{stage[:5]}-{dispatch_id[-4:]}"
    now_iso = utc_now_iso()

    packet_md = _render_packet_markdown(
        run_id=run_id,
        target_path=target_path,
        stage=stage,
        wire_profile=resolved_profile,
        worker_id=eff_worker,
        dispatch_id=dispatch_id,
        items=selected,
    )

    conn.execute(
        """
        INSERT INTO swarm_dispatches(
            dispatch_id, worker_id, stage, wire_profile, item_ids_json, status, notes, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, 'dispatched', '', ?, ?)
        """,
        (dispatch_id, eff_worker, stage, resolved_profile, json.dumps(selected_ids), now_iso, now_iso),
    )
    log_event(
        conn,
        "orchestrator",
        "swarm_packet_dispatched",
        dispatch_id,
        {
            "worker_id": eff_worker,
            "stage": stage,
            "wire_profile": resolved_profile,
            "item_ids": selected_ids,
        },
    )
    return {
        "dispatch_id": dispatch_id,
        "worker_id": eff_worker,
        "stage": stage,
        "wire_profile": resolved_profile,
        "item_ids": selected_ids,
        "line_count": len(packet_md.splitlines()),
        "packet_markdown": packet_md,
    }


def escalate_swarm_fallback(
    conn: sqlite3.Connection,
    *,
    target: str,
    reason: str = "idle_no_return",
    notes: str = "",
) -> dict[str, Any]:
    """Record a stalled/filter-blocked dispatch and emit stepped-down fallback packet(s)."""
    if reason not in VALID_FALLBACK_REASONS:
        raise AjarError(f"Invalid --reason {reason!r}; expected one of {VALID_FALLBACK_REASONS}.", EXIT_USER_ERROR)

    row = conn.execute(
        """
        SELECT * FROM swarm_dispatches
        WHERE dispatch_id = ? OR worker_id = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (target.strip(), target.strip()),
    ).fetchone()
    if row is None:
        raise AjarError(
            f"No swarm dispatch found matching dispatch_id or worker_id {target!r}.",
            EXIT_USER_ERROR,
        )

    prev_id = str(row["dispatch_id"])
    stage = str(row["stage"])
    prev_profile = str(row["wire_profile"] or "direct")
    try:
        item_ids = [str(x) for x in json.loads(row["item_ids_json"] or "[]") if str(x).strip()]
    except json.JSONDecodeError:
        item_ids = []
    if not item_ids:
        raise AjarError(f"Dispatch {prev_id} has zero tracked item IDs to re-dispatch.", EXIT_USER_ERROR)

    now_iso = utc_now_iso()
    conn.execute(
        "UPDATE swarm_dispatches SET status = ?, notes = ?, updated_at = ? WHERE dispatch_id = ?",
        (reason, scrub_text(notes or f"Escalated due to {reason}"), now_iso, prev_id),
    )

    prev_idx = WIRE_PROFILE_LADDER.index(prev_profile) if prev_profile in WIRE_PROFILE_LADDER else 0
    at_ceiling = prev_idx >= (len(WIRE_PROFILE_LADDER) - 1)
    next_profile = WIRE_PROFILE_LADDER[min(prev_idx + 1, len(WIRE_PROFILE_LADDER) - 1)]
    chunk_size = _profile_batch_cap(next_profile, len(item_ids))

    # Filter out items that were already resolved (`reproduced`, `falsified`, `done`, `dry`) before partial stall!
    unresolved_candidates = _select_stage_items(conn, stage=stage, explicit_ids=item_ids, limit=len(item_ids))
    unresolved_ids = [
        c["id"]
        for c in unresolved_candidates
        if c["status"] not in ("reproduced", "falsified", "duplicate_root_cause", "done", "dry")
    ] or item_ids

    recovery_packets: list[dict[str, Any]] = []
    for offset in range(0, len(unresolved_ids), chunk_size):
        batch = unresolved_ids[offset : offset + chunk_size]
        pkt = build_swarm_packet(
            conn,
            stage=stage,
            wire_profile=next_profile,
            item_ids=batch,
            limit=chunk_size,
        )
        recovery_packets.append(pkt)

    log_event(
        conn,
        "orchestrator",
        "swarm_wire_profile_escalated",
        prev_id,
        {
            "reason": reason,
            "previous_profile": prev_profile,
            "next_profile": next_profile,
            "at_ladder_ceiling": at_ceiling,
            "recovery_dispatch_ids": [p["dispatch_id"] for p in recovery_packets],
        },
    )
    return {
        "previous_dispatch_id": prev_id,
        "previous_worker_id": str(row["worker_id"]),
        "stage": stage,
        "reason": reason,
        "previous_profile": prev_profile,
        "next_profile": next_profile,
        "at_ladder_ceiling": at_ceiling,
        "recovery_packets": recovery_packets,
    }


def complete_swarm_dispatch(
    conn: sqlite3.Connection,
    *,
    target: str,
    notes: str = "",
) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT * FROM swarm_dispatches
        WHERE dispatch_id = ? OR worker_id = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (target.strip(), target.strip()),
    ).fetchone()
    if row is None:
        raise AjarError(f"No swarm dispatch found matching {target!r}.", EXIT_USER_ERROR)
    did = str(row["dispatch_id"])
    now_iso = utc_now_iso()
    conn.execute(
        "UPDATE swarm_dispatches SET status = 'completed', notes = ?, updated_at = ? WHERE dispatch_id = ?",
        (scrub_text(notes), now_iso, did),
    )
    return {"dispatch_id": did, "worker_id": str(row["worker_id"]), "status": "completed"}


def resolve_shared_mirror_root(
    explicit_root: str | pathlib.Path | None = None,
    *,
    ajar_home: pathlib.Path | str | None = None,
) -> pathlib.Path | None:
    """Resolve persistent shared ledger root (`/shared/user/.gemini/ajar/runs`) when enabled."""
    if explicit_root is not None:
        raw = str(explicit_root).strip()
        if not raw or raw.lower() in ("off", "none", "false", "0"):
            return None
        return pathlib.Path(raw).expanduser().resolve()

    env_mirror = os.environ.get("AJAR_SHARED_MIRROR_DIR", "").strip()
    if env_mirror:
        if env_mirror.lower() in ("off", "none", "false", "0"):
            return None
        return pathlib.Path(env_mirror).expanduser().resolve()

    # Do not auto-mirror temporary unit-test runs that override `AJAR_HOME` unless explicitly configured.
    if ajar_home is not None or os.environ.get("AJAR_HOME", "").strip():
        return None

    default_shared_base = pathlib.Path("/shared/user/.gemini")
    if default_shared_base.is_dir():
        return default_shared_base / "ajar" / "runs"
    return None


def _backup_sqlite_file(src_db: pathlib.Path, dst_db: pathlib.Path) -> None:
    dst_db.parent.mkdir(parents=True, exist_ok=True)
    tmp_dst = dst_db.with_suffix(".db.tmp")
    if tmp_dst.exists():
        tmp_dst.unlink()
    src_conn = sqlite3.connect(str(src_db), timeout=30.0)
    dst_conn = sqlite3.connect(str(tmp_dst), timeout=30.0)
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()
    os.replace(tmp_dst, dst_db)


def _copy2_overwriting_readonly(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> str:
    dst_p = pathlib.Path(dst)
    parent = dst_p.parent
    if parent.is_dir():
        try:
            pst = parent.stat().st_mode
            if (pst & 0o200) == 0:
                parent.chmod(pst | 0o700)
        except OSError:
            pass
    if dst_p.exists() or dst_p.is_symlink():
        try:
            dst_p.chmod(0o600)
        except OSError:
            pass
        dst_p.unlink(missing_ok=True)
    return shutil.copy2(os.fspath(src), os.fspath(dst))


def _copytree_readonly_safe(src: pathlib.Path, dst: pathlib.Path) -> None:
    if dst.is_dir():
        for root, dirs, _ in os.walk(dst):
            for p in [pathlib.Path(root), *(pathlib.Path(root) / d for d in dirs)]:
                try:
                    mode = p.stat().st_mode
                    if (mode & 0o200) == 0:
                        p.chmod(mode | 0o700)
                except OSError:
                    pass
    shutil.copytree(src, dst, dirs_exist_ok=True, copy_function=_copy2_overwriting_readonly)


def _sync_bare_repo_portable(src_repo_git: pathlib.Path, dst_repo_git: pathlib.Path) -> None:
    """Copy bare `repo.git` (excluding ephemeral slot worktrees/caches) and inline alternates for cross-VM portability."""
    if not (src_repo_git / "HEAD").is_file():
        return
    dst_repo_git.mkdir(parents=True, exist_ok=True)
    for scalar in ("HEAD", "config", "description", "packed-refs", "shallow"):
        sp = src_repo_git / scalar
        if sp.is_file():
            _copy2_overwriting_readonly(sp, dst_repo_git / scalar)
    for sub in ("info", "refs", "objects"):
        sdir = src_repo_git / sub
        ddir = dst_repo_git / sub
        if sdir.is_dir():
            _copytree_readonly_safe(sdir, ddir)

    alt_file = dst_repo_git / "objects" / "info" / "alternates"
    if alt_file.is_file():
        env = scrubbed_subprocess_env()
        repack = subprocess.run(
            ["git", "--git-dir", str(dst_repo_git), "repack", "-a", "-d", "-q"],
            capture_output=True,
            env=env,
            check=False,
        )
        if repack.returncode == 0:
            alt_file.unlink(missing_ok=True)


def sync_run_to_shared_mirror(
    run_id: str,
    *,
    ajar_home: pathlib.Path | str | None = None,
    shared_root: str | pathlib.Path | None = None,
) -> dict[str, Any] | None:
    """Mirror compact run ledger (`run.db`, `brief.md`, `repro/repo.git`, `repro/helpers`, `repro/snapshots`, `artifacts`) to shared storage."""
    mirror_root = resolve_shared_mirror_root(shared_root, ajar_home=ajar_home)
    if mirror_root is None:
        return None

    rdir = run_dir_for(run_id, ajar_home).resolve()
    dst_dir = (mirror_root / run_id).resolve()
    if rdir == dst_dir or not (rdir / "run.db").is_file():
        return None

    dst_dir.mkdir(parents=True, exist_ok=True)
    _backup_sqlite_file(rdir / "run.db", dst_dir / "run.db")

    if (rdir / "brief.md").is_file():
        _copy2_overwriting_readonly(rdir / "brief.md", dst_dir / "brief.md")

    if (rdir / "artifacts").is_dir():
        _copytree_readonly_safe(rdir / "artifacts", dst_dir / "artifacts")

    if (rdir / "repro" / "helpers").is_dir():
        (dst_dir / "repro").mkdir(parents=True, exist_ok=True)
        _copytree_readonly_safe(rdir / "repro" / "helpers", dst_dir / "repro" / "helpers")

    if (rdir / "repro" / "snapshots").is_dir():
        (dst_dir / "repro").mkdir(parents=True, exist_ok=True)
        _copytree_readonly_safe(rdir / "repro" / "snapshots", dst_dir / "repro" / "snapshots")

    if (rdir / "repro" / "repo.git" / "HEAD").is_file():
        (dst_dir / "repro").mkdir(parents=True, exist_ok=True)
        _sync_bare_repo_portable(rdir / "repro" / "repo.git", dst_dir / "repro" / "repo.git")

    return {"run_id": run_id, "mirror_dir": str(dst_dir)}


def _hydrate_run_from_shared_mirror(
    run_id: str,
    *,
    local_rdir: pathlib.Path,
    shared_root: pathlib.Path | None,
) -> bool:
    if (local_rdir / "run.db").is_file() or shared_root is None:
        return False
    src_dir = (shared_root / run_id).resolve()
    if not (src_dir / "run.db").is_file():
        return False

    local_rdir.mkdir(parents=True, exist_ok=True)
    _backup_sqlite_file(src_dir / "run.db", local_rdir / "run.db")
    if (src_dir / "brief.md").is_file():
        _copy2_overwriting_readonly(src_dir / "brief.md", local_rdir / "brief.md")
    if (src_dir / "artifacts").is_dir():
        _copytree_readonly_safe(src_dir / "artifacts", local_rdir / "artifacts")
    if (src_dir / "repro" / "helpers").is_dir():
        (local_rdir / "repro").mkdir(parents=True, exist_ok=True)
        _copytree_readonly_safe(src_dir / "repro" / "helpers", local_rdir / "repro" / "helpers")
    if (src_dir / "repro" / "snapshots").is_dir():
        (local_rdir / "repro").mkdir(parents=True, exist_ok=True)
        _copytree_readonly_safe(src_dir / "repro" / "snapshots", local_rdir / "repro" / "snapshots")
    if (src_dir / "repro" / "repo.git" / "HEAD").is_file():
        (local_rdir / "repro").mkdir(parents=True, exist_ok=True)
        _copytree_readonly_safe(src_dir / "repro" / "repo.git", local_rdir / "repro" / "repo.git")
    return True


def _ensure_target_checkout_from_mirror(
    conn: sqlite3.Connection,
    *,
    local_rdir: pathlib.Path,
    run_row: sqlite3.Row,
) -> tuple[str, bool]:
    """Reconstruct missing target working tree on a fresh VM directly from `repro/repo.git`."""
    orig_target = pathlib.Path(str(run_row["target_path"]))
    if orig_target.exists():
        return (str(orig_target), False)

    mirror_git = local_rdir / "repro" / "repo.git"
    if not (mirror_git / "HEAD").is_file():
        return (str(orig_target), False)

    # Restore at original path when under HOME or /tmp; otherwise materialize inside `<run_dir>/workspace/target`.
    home_root = pathlib.Path.home().resolve()
    tmp_root = pathlib.Path("/tmp").resolve()
    restore_path = orig_target
    try:
        orig_parent_resolved = orig_target.expanduser().resolve(strict=False)
        under_writable = (
            str(orig_parent_resolved).startswith(str(home_root) + "/")
            or str(orig_parent_resolved).startswith(str(tmp_root) + "/")
        )
    except OSError:
        under_writable = False
    if not under_writable:
        restore_path = local_rdir / "workspace" / "target"

    restore_path.parent.mkdir(parents=True, exist_ok=True)
    env = scrubbed_subprocess_env()
    subprocess.run(
        ["git", "-C", str(mirror_git), "config", "safe.directory", "*"],
        capture_output=True,
        env=env,
        check=False,
    )
    clone_res = subprocess.run(
        ["git", "-c", "safe.directory=*", "clone", str(mirror_git), str(restore_path)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if clone_res.returncode != 0:
        return (str(orig_target), False)

    if str(restore_path) != str(orig_target):
        ws_mode = str(run_row["workspace_mode"] or "in_place")
        new_ws = str(restore_path.parent) if ws_mode == "envelope" else str(restore_path)
        conn.execute(
            "UPDATE runs SET target_path = ?, workspace_path = ? WHERE run_id = ?",
            (str(restore_path), new_ws, str(run_row["run_id"])),
        )
    return (str(restore_path), True)


def reopen_run(
    run_id: str,
    *,
    unblock_zero_attempt_claims: bool = True,
    shared_root: str | pathlib.Path | None = None,
    ajar_home: pathlib.Path | None = None,
) -> dict[str, Any]:
    """Hydrate and reopen a finished/stalled run, unblocking zero-attempt policy-deferred claims."""
    base_home = ajar_home or get_ajar_home()
    local_rdir = run_dir_for(run_id, base_home)
    eff_shared = (
        resolve_shared_mirror_root(shared_root, ajar_home=ajar_home)
        if shared_root is not None
        else (
            resolve_shared_mirror_root(None, ajar_home=ajar_home)
            or (pathlib.Path("/shared/user/.gemini/ajar/runs") if pathlib.Path("/shared/user/.gemini/ajar/runs").is_dir() else None)
        )
    )
    hydrated = _hydrate_run_from_shared_mirror(run_id, local_rdir=local_rdir, shared_root=eff_shared)
    if not (local_rdir / "run.db").is_file():
        raise AjarError(
            f"Run {run_id!r} not found in {local_rdir} or shared mirror {eff_shared}.",
            EXIT_USER_ERROR,
        )

    conn = open_run_db(run_id, ajar_home=base_home)
    try:
        run_row = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
        if run_row is None:
            raise AjarError(f"Run metadata missing in {local_rdir / 'run.db'}.", EXIT_USER_ERROR)

        target_path, target_reconstructed = _ensure_target_checkout_from_mirror(
            conn, local_rdir=local_rdir, run_row=run_row
        )

        now_iso = utc_now_iso()
        conn.execute(
            "UPDATE runs SET status = 'active', stop_reason = '', finished_at = NULL WHERE run_id = ?",
            (run_id,),
        )
        (base_home / "current_run").write_text(f"{run_id}\n", encoding="utf-8")

        # Scrub any legacy `.git/hooks/*` or `#!/bin/sh` tails in `claims.mechanism` so fresh workers stay clean.
        scrubbed_claim_ids: list[str] = []
        all_claims = conn.execute("SELECT claim_id, mechanism FROM claims").fetchall()
        for crow in all_claims:
            cleaned_mech, changed = scrub_weaponized_hook_prose(str(crow["mechanism"] or ""))
            if changed:
                conn.execute(
                    "UPDATE claims SET mechanism = ?, updated_at = ? WHERE claim_id = ?",
                    (scrub_text(cleaned_mech), now_iso, crow["claim_id"]),
                )
                scrubbed_claim_ids.append(str(crow["claim_id"]))

        unblocked_claim_ids: list[str] = []
        if unblock_zero_attempt_claims:
            blocked_rows = conn.execute("SELECT * FROM claims WHERE status = 'blocked' ORDER BY created_at ASC").fetchall()
            for bc in blocked_rows:
                fails = int(bc["failed_repro_count"] or 0)
                env_b = str(bc["env_blocker"] or "").strip() if "env_blocker" in bc.keys() else ""
                is_policy_deferred = bool(POLICY_REFUSAL_BLOCK_RE.search(str(bc["blocker_reason"] or "")))
                if not is_policy_deferred and env_b in ZERO_ATTEMPT_EXEMPT_ENV_BLOCKERS:
                    continue
                if is_policy_deferred or fails == 0:
                    has_falsifier = bool(str(bc["falsifier_worker_id"] or "").strip()) and (
                        str(bc["falsifier_worker_id"]) != str(bc["proposer_worker_id"])
                    )
                    next_status = "survived_falsify" if has_falsifier else "proposed"
                    preserved_notes = str(bc["falsify_notes"] or "").strip()
                    if not preserved_notes and bc["blocker_reason"]:
                        stripped_note = POLICY_REFUSAL_BLOCK_RE.sub("", str(bc["blocker_reason"])).strip()
                        preserved_notes = stripped_note[:600]
                    conn.execute(
                        """
                        UPDATE claims
                        SET status = ?, blocker_reason = '', env_blocker = '',
                            falsify_notes = ?, updated_at = ?
                        WHERE claim_id = ?
                        """,
                        (next_status, scrub_text(preserved_notes), now_iso, bc["claim_id"]),
                    )
                    conn.execute(
                        """
                        UPDATE tasks
                        SET status = 'open', updated_at = ?
                        WHERE parent_claim_id = ? AND kind IN ('reproduce', 'falsify') AND status IN ('done', 'dry')
                        """,
                        (now_iso, bc["claim_id"]),
                    )
                    unblocked_claim_ids.append(str(bc["claim_id"]))

        # Ensure Stage-5 Converge (`chain`) re-evaluates once unblocked claims reproduce!
        if unblocked_claim_ids:
            conn.execute(
                "UPDATE tasks SET status = 'open', updated_at = ? WHERE kind = 'chain' AND status IN ('done', 'dry')",
                (now_iso,),
            )

        ready_repro = conn.execute(
            "SELECT claim_id FROM claims WHERE status = 'survived_falsify' ORDER BY created_at ASC"
        ).fetchall()
        ready_falsify = conn.execute(
            "SELECT claim_id FROM claims WHERE status = 'proposed' ORDER BY created_at ASC"
        ).fetchall()

        log_event(
            conn,
            "operator",
            "run_reopened",
            run_id,
            {
                "hydrated_from_shared_mirror": hydrated,
                "target_reconstructed": target_reconstructed,
                "unblocked_claim_ids": unblocked_claim_ids,
                "scrubbed_claim_ids": scrubbed_claim_ids,
            },
        )
    finally:
        conn.close()

    return {
        "run_id": run_id,
        "status": "active",
        "run_dir": str(local_rdir),
        "target_path": target_path,
        "hydrated_from_shared_mirror": hydrated,
        "target_reconstructed": target_reconstructed,
        "unblocked_claim_ids": unblocked_claim_ids,
        "scrubbed_claim_ids": scrubbed_claim_ids,
        "ready_reproduce_claims": [str(r["claim_id"]) for r in ready_repro],
        "ready_falsify_claims": [str(r["claim_id"]) for r in ready_falsify],
        "local_build_cache_dir": f"/tmp/ajar-build-cache/{run_id}",
        "next_command": (
            f"AJAR_RUN_ID={run_id} ajar swarm packet --stage reproduce --limit 3"
            if ready_repro
            else f"AJAR_RUN_ID={run_id} ajar status"
        ),
    }
