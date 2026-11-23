"""Cross-module event reaction orchestrators (`primitive`, `anomaly/claim`, `finding`).

Sits cleanly above `store`, `epistemic_hooks`, `chain_planner`, and `db` so
cross-subsystem hook registration, Open-Door wakeup, and threat-assumption
re-evaluation execute without circular imports.
"""

from __future__ import annotations

import pathlib
import sqlite3
from typing import Any, Sequence

from ajar.chain_planner import wake_matching_doors_for_artifact
from ajar.db import evaluate_adaptive_threat_assumptions
from ajar.epistemic_hooks import (
    UNWIND_SIGNAL_RE,
    consume_hooks_for_locus,
    detect_capability_bridges,
    register_epistemic_hook,
    register_invariant_symmetry_hook,
    scan_source_for_epistemic_signals,
)
from ajar.store import (
    compute_task_salience,
    immediate_tx,
    infer_subsystem,
    new_id,
    utc_now_iso,
)


def on_primitive_added(
    conn: sqlite3.Connection,
    *,
    primitive_id: str,
    subsystem: str,
    locus: str,
    kind: str,
    guarded_by_locus: str = "",
    provides_tags: Sequence[str] = (),
    requires_tags: Sequence[str] = (),
    role: str = "capability",
    trusted_invariant: str = "",
    symbols: Sequence[str] = (),
    snapshot_id: str = "",
    postconditions: str = "",
    spawn_guard_task: bool = True,
) -> list[dict[str, Any]]:
    """Evaluate `H1`, `H9`, `H4`, Open-Door wakeup, and Adaptive Threat-Model assumptions when a primitive is recorded."""
    fired: list[dict[str, Any]] = []
    now_iso = utc_now_iso()
    with immediate_tx(conn):
        if provides_tags:
            evaluate_adaptive_threat_assumptions(
                conn,
                evidence_ref=primitive_id,
                provided_tags=provides_tags,
            )

        # H1 + H9: Guarded inner primitive -> register guard-symmetry hook, invariant-symmetry hook (for capabilities),
        # and optional inside-out guard task.
        gloc = guarded_by_locus.strip()
        if gloc:
            spawned_tid: str | None = None
            if spawn_guard_task:
                existing_guard_task = conn.execute(
                    """
                    SELECT task_id FROM tasks
                    WHERE locus = ? AND kind IN ('investigate', 'chain')
                      AND status IN ('open', 'leased', 'done', 'dry')
                    LIMIT 1
                    """,
                    (gloc,),
                ).fetchone()
                if existing_guard_task is None:
                    gsub = infer_subsystem(gloc)
                    draft = {"priority": "high", "subsystem": gsub, "locus": gloc, "reopened_boost": 8}
                    sal = max(82, compute_task_salience(conn, draft))
                    spawned_tid = new_id("task")
                    conn.execute(
                        """
                        INSERT INTO tasks(
                            task_id, kind, direction, title, subsystem, locus,
                            priority, status, salience_score, summary, created_at, updated_at
                        ) VALUES (?, 'investigate', 'inside_out', ?, ?, ?, 'high', 'open', ?, ?, ?, ?)
                        """,
                        (
                            spawn_guard_task and spawned_tid or "",
                            f"Audit upstream guard {gloc} blocking {primitive_id} ({kind})",
                            gsub,
                            gloc,
                            sal,
                            f"Auto-enqueued by H1_GUARD_SYMMETRY for {primitive_id} @ {locus}.",
                            now_iso,
                            now_iso,
                        ),
                    )
            gsub = infer_subsystem(gloc)
            h1 = register_epistemic_hook(
                conn,
                hook_code="H1_GUARD_SYMMETRY",
                trigger_cmd="primitive.add",
                source_entity_id=primitive_id,
                dedup_material=f"{gloc}:{locus}",
                subsystem=gsub,
                target_locus=gloc,
                spawned_task_id=spawned_tid,
                directive_text=(
                    f"Audit guard {gloc} in isolation: check shared bit-width, mask/modulus, "
                    f"normalization, or fail-open branch with {primitive_id}@{locus}."
                ),
                kill_rule=(
                    f"STOP and mark dry if {gloc} enforces widening/checked bounds on immutable "
                    "server state with zero shared truncation."
                ),
            )
            fired.append(h1)
            if (role or "capability").strip() == "capability":
                h9 = register_invariant_symmetry_hook(
                    conn,
                    primitive_id=primitive_id,
                    capability_locus=locus,
                    guarded_by_locus=gloc,
                    subsystem=gsub,
                    spawned_task_id=spawned_tid,
                )
                fired.append(h9)

        # H4: Typed state bridge across subsystems (`provides_tags <-> requires_tags`).
        if provides_tags or requires_tags:
            bridges = detect_capability_bridges(conn, limit=8)
            for br in bridges:
                if br["bridge_type"] != "complete_bridge" or not br["providers"]:
                    continue
                prov0 = br["providers"][0]
                if prov0["primitive_id"] != primitive_id and br["sink_id"] != primitive_id:
                    continue
                tags_s = ",".join(br["matched_tags"][:3])
                existing_chain = conn.execute(
                    """
                    SELECT task_id FROM tasks
                    WHERE kind = 'chain' AND status IN ('open', 'leased')
                      AND summary LIKE ?
                    LIMIT 1
                    """,
                    (f"%{br['sink_id']}%",),
                ).fetchone()
                chain_tid: str | None = None
                if existing_chain is None:
                    chain_tid = new_id("task")
                    conn.execute(
                        """
                        INSERT INTO tasks(
                            task_id, kind, direction, title, subsystem, locus,
                            priority, status, salience_score, summary, created_at, updated_at
                        ) VALUES (?, 'chain', 'outside_in', ?, ?, ?, 'high', 'open', 86, ?, ?, ?)
                        """,
                        (
                            chain_tid,
                            f"Bridge {prov0['primitive_id']} -> {br['sink_id']} via [{tags_s}]",
                            br["sink_subsystem"],
                            br["sink_locus"],
                            f"Cross-subsystem bridge: {prov0['primitive_id']}@{prov0['locus']} provides [{tags_s}] required by {br['sink_id']}@{br['sink_locus']}.",
                            now_iso,
                            now_iso,
                        ),
                    )
                h4 = register_epistemic_hook(
                    conn,
                    hook_code="H4_TYPED_STATE_BRIDGE",
                    trigger_cmd="primitive.add",
                    source_entity_id=primitive_id,
                    dedup_material=f"{prov0['primitive_id']}->{br['sink_id']}:{tags_s}",
                    subsystem=br["sink_subsystem"],
                    target_locus=br["sink_locus"],
                    spawned_task_id=chain_tid,
                    directive_text=(
                        f"Bridge {prov0['primitive_id']}@{prov0['locus']} provides [{tags_s}] "
                        f"required by {br['sink_id']}@{br['sink_locus']}; prove end-to-end via ajar chain propose."
                    ),
                    kill_rule=(
                        f"STOP and mark dry if {br['sink_locus']} re-verifies principal and digest "
                        f"inline from authoritative state independent of [{tags_s}]."
                    ),
                )
                fired.append(h4)

        wake_matching_doors_for_artifact(
            conn,
            artifact_id=primitive_id,
            artifact_kind=role or "capability",
            locus=locus,
            subsystem=subsystem,
            text_blob=f"{kind} {postconditions} {trusted_invariant}",
            provides_tags=provides_tags,
            symbols=symbols,
            snapshot_id=snapshot_id,
            trigger_cmd="primitive.add",
        )
    return fired


def on_anomaly_or_claim_recorded(
    conn: sqlite3.Connection,
    *,
    entity_id: str,
    trigger_cmd: str,
    subsystem: str,
    locus: str,
    text_blob: str,
    target_dir: pathlib.Path | None = None,
) -> list[dict[str, Any]]:
    """Evaluate `H2`, `H7`, `H8`, and Open-Door wakeup on new anomalies/claims or their target source file."""
    fired: list[dict[str, Any]] = []
    combined = text_blob
    rel_file = locus.split(":", 1)[0].strip().lstrip("./")
    if target_dir is not None and rel_file:
        candidate = (target_dir / rel_file).resolve()
        try:
            candidate.relative_to(target_dir.resolve())
            if candidate.is_file():
                src_text = candidate.read_text(encoding="utf-8", errors="ignore")
                for hcode, directive, kill_r in scan_source_for_epistemic_signals(rel_file, src_text):
                    fired.append(
                        register_epistemic_hook(
                            conn,
                            hook_code=hcode,
                            trigger_cmd=trigger_cmd,
                            source_entity_id=entity_id,
                            dedup_material=f"{rel_file}:{hcode}",
                            subsystem=subsystem,
                            target_locus=locus,
                            directive_text=directive,
                            kill_rule=kill_r,
                        )
                    )
        except ValueError:
            pass

    if UNWIND_SIGNAL_RE.search(combined):
        fired.append(
            register_epistemic_hook(
                conn,
                hook_code="H2_DIRTY_UNWIND",
                trigger_cmd=trigger_cmd,
                source_entity_id=entity_id,
                dedup_material=locus,
                subsystem=subsystem,
                target_locus=locus,
                directive_text=(
                    f"Send benign request N+1 on same worker/store after fault N at {locus}; "
                    "check unreset globals, pending credits, or locks."
                ),
                kill_rule="STOP and mark dry if fault N aborts isolated process state or rolls back atomically.",
            )
        )

    if entity_id.startswith("anom-"):
        wake_matching_doors_for_artifact(
            conn,
            artifact_id=entity_id,
            artifact_kind="anomaly",
            locus=locus,
            subsystem=subsystem,
            text_blob=text_blob,
            trigger_cmd=trigger_cmd,
        )
    return fired


def on_finding_confirmed(
    conn: sqlite3.Connection,
    *,
    finding_id: str,
    claim_row: sqlite3.Row | dict[str, Any],
    provides_tags: Sequence[str] = (),
    snapshot_id: str = "",
    realism_tier: str = "stepping_stone",
) -> dict[str, Any] | None:
    """Evaluate Open-Door wakeup, Adaptive Threat-Model assumptions, and `H5_POST_CONFIRM_ESCALATION`."""
    sev = str(claim_row["severity"] or "").lower()
    cid = str(claim_row["claim_id"])
    loc = str(claim_row["locus"] or "")
    sub = str(claim_row["subsystem"] or "")
    consume_hooks_for_locus(conn, locus=loc, source_entity_id=cid, hook_code="H6_RELEASE_UB_DIFF")
    evaluate_adaptive_threat_assumptions(
        conn,
        evidence_ref=finding_id,
        confirmed_locus=loc,
        provided_tags=provides_tags,
    )
    woken = wake_matching_doors_for_artifact(
        conn,
        artifact_id=finding_id,
        artifact_kind="finding",
        locus=loc,
        subsystem=sub,
        text_blob=f"{claim_row['title']} {claim_row['mechanism']}",
        provides_tags=provides_tags,
        snapshot_id=snapshot_id,
        trigger_cmd="claim.reproduce",
    )

    should_escalate = sev in ("low", "medium") or (sev == "high" and realism_tier == "stepping_stone")
    if not should_escalate:
        return {"woken_doors": woken} if woken else None

    rel_file = loc.split(":", 1)[0].strip().lstrip("./")
    callers: list[str] = []
    for r in conn.execute(
        "SELECT src_file FROM repomap_edges WHERE dst_file = ? ORDER BY weight DESC LIMIT 8",
        (rel_file,),
    ).fetchall():
        sf = str(r["src_file"])
        if sf and sf not in callers:
            callers.append(sf)
        if len(callers) >= 4:
            break
    caller_hint = ", ".join(callers) if callers else "1-hop callers"

    esc_tid = new_id("task")
    now_iso = utc_now_iso()
    conn.execute(
        """
        INSERT INTO tasks(
            task_id, surface_id, parent_claim_id, kind, direction, title, subsystem, locus,
            priority, status, salience_score, summary, created_at, updated_at
        ) VALUES (?, ?, ?, 'escalate', 'outside_in', ?, ?, ?, 'high', 'open', 80, ?, ?, ?)
        """,
        (
            esc_tid,
            claim_row["surface_id"],
            cid,
            f"Evaluate post-confirm escalation consumers of {finding_id} ({sev}/{realism_tier})",
            sub,
            loc,
            f"Single-pass ceiling-breaker (`max_leases=1`): check whether {caller_hint} trust output from {finding_id}@{loc} or park as an Open Door.",
            now_iso,
            now_iso,
        ),
    )
    hook = register_epistemic_hook(
        conn,
        hook_code="H5_POST_CONFIRM_ESCALATION",
        trigger_cmd="claim.reproduce",
        source_entity_id=finding_id,
        dedup_material=finding_id,
        subsystem=sub,
        target_locus=loc,
        spawned_task_id=esc_tid,
        max_leases=1,
        directive_text=(
            f"Finding {finding_id} ({sev}/{realism_tier}) is proven at {loc}; check consumers ({caller_hint}) "
            "or park an Open Door (`ajar door park`) if a downstream sink needs one missing link."
        ),
        kill_rule="STOP and mark done unless every escalation hop uses verified code paths in target modules.",
    )
    return {"escalate_task_id": esc_tid, "hook": hook, "woken_doors": woken}
