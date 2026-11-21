"""Seeded multi-worker Deterministic Simulation Testing (DST) for Ajar state machines.

Runs 20 seeds x 40 randomized steps (800+ operations by default; configurable via
`AJAR_DST_SEEDS`) exercising service, CLI (`ajar spend add`), and MCP workflow
mutations, illegal transition probes, phase monotonicity, read-only gate purity,
Host Mode advisory spend behavior, KV prefix-cache stability, and finish/reopen cycles.

Replay any failing seed directly:
    AJAR_DST_SEED=7 pytest -q tests/dst/test_state_machine_sim.py
"""

from __future__ import annotations

import io
import os
import pathlib
import random
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from unittest import mock

import ajar.chain_planner as chain_planner_mod
import ajar.db as db_mod
import ajar.epistemic_hooks as epistemic_hooks_mod
import ajar.reactions as reactions_mod
import ajar.services.workflow as workflow_mod
import ajar.store.util as store_util_mod
import ajar.swarm as swarm_mod
from ajar.chain_planner import (
    VALID_DOOR_DIRECTIONS,
    add_crown_jewel,
    compute_chain_frontier,
    park_open_door,
)
from ajar.cli import main as cli_main
from ajar.db import (
    add_steer,
    compute_task_salience,
    lease_next_task,
    mark_primitive_dry,
    new_id,
    open_run_db,
    render_task_context,
    utc_now_iso,
)
from ajar.domain import (
    AjarError,
    AnomalyStatus,
    CampaignPhase,
    ClaimStatus,
    DoorStatus,
    InvalidTransitionError,
    JewelStatus,
    PrimitiveStatus,
    RunStatus,
    TaskStatus,
    derive_claim_axes,
)
from ajar.gates import check_all_gates
from ajar.mcp import dispatch_mcp_tool
from ajar.services import (
    add_anomaly,
    add_surface,
    advance_phase,
    block_claim,
    block_task,
    close_task_done,
    close_task_dry,
    explain_anomaly,
    falsify_claim,
    finish_run,
    propose_claim,
    rescope_claim_service,
    survive_claim,
)
from ajar.store import immediate_tx
from ajar.swarm import reopen_run

WORKERS: tuple[str, ...] = ("w-alpha", "w-beta", "w-gamma")
PHASE_RANK: dict[str, int] = {"hunt": 0, "remediate": 1, "full": 2}
TARGET_FILES: tuple[tuple[str, str], ...] = (
    (
        "src/auth.py",
        "def verify_token(tok: str) -> bool:\n"
        "    if not tok:\n"
        "        return False\n"
        "    return tok == 'expected_secret'\n",
    ),
    (
        "src/parser.py",
        "def parse_frame(buf: bytes) -> int:\n"
        "    if len(buf) < 4:\n"
        "        return -1\n"
        "    return int.from_bytes(buf[:4], 'big')\n",
    ),
    (
        "src/vault.py",
        "def withdraw(bal: int, amt: int) -> int:\n"
        "    if amt < 0 or amt > bal:\n"
        "        raise ValueError('bounds')\n"
        "    return bal - amt\n",
    ),
)


class _DeterministicClock:
    """Monotonic logical clock eliminating wall-clock second-boundary flakiness."""

    def __init__(self, base_epoch: int = 1795132800) -> None:
        self._tick = 0
        self._base = base_epoch

    def iso(self) -> str:
        self._tick += 1
        secs = self._tick
        mm, ss = divmod(secs, 60)
        hh, mm = divmod(mm, 60)
        return f"2026-11-21T{hh:02d}:{mm:02d}:{ss:02d}Z"

    def epoch(self) -> float:
        self._tick += 1
        return float(self._base + self._tick)


def _seed_target_dir(root: pathlib.Path) -> pathlib.Path:
    for rel, content in TARGET_FILES:
        fp = root / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
    return root


def _bootstrap_sim_run(
    run_id: str,
    target_dir: pathlib.Path,
    *,
    ajar_home: pathlib.Path | None = None,
    template_db: pathlib.Path | None = None,
) -> sqlite3.Connection:
    if template_db is not None and ajar_home is not None:
        rdir = ajar_home / "runs" / run_id
        rdir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(template_db, rdir / "run.db")
        conn = open_run_db(run_id, create=False, ajar_home=ajar_home)
    else:
        conn = open_run_db(run_id, create=True, ajar_home=ajar_home)
    now = utc_now_iso()
    with immediate_tx(conn):
        conn.execute(
            """
            INSERT INTO runs(
                run_id, target_path, workspace_path, target_mode, workspace_mode,
                goal, stopping_criterion, campaign_phase, status,
                code_quote_usd, cogs_cap_usd, commitment_hash, created_at
            ) VALUES (?, ?, ?, 'source', 'in_place', 'dst simulation', 'exhaustive-high', 'hunt', 'active', 100.0, 35.0, 'dst-commit', ?)
            """,
            (run_id, str(target_dir), str(target_dir), now),
        )
    return conn


def _table_snapshot(conn: sqlite3.Connection) -> tuple[object, ...]:
    return (
        [tuple(r) for r in conn.execute("SELECT task_id, status, updated_at FROM tasks ORDER BY rowid ASC").fetchall()],
        [tuple(r) for r in conn.execute("SELECT door_id, status, updated_at FROM parked_doors ORDER BY rowid ASC").fetchall()],
        int(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]),
    )


def _assert_global_invariants(
    conn: sqlite3.Connection,
    *,
    target_dir: pathlib.Path,
    seed: int,
    step: int,
    prev_phase_rank: int,
) -> int:
    ctx = f"seed={seed} step={step}"
    run = conn.execute("SELECT status, campaign_phase FROM runs LIMIT 1").fetchone()
    assert run is not None, f"{ctx}: missing runs row"
    assert run["status"] in {s.value for s in RunStatus}, f"{ctx}: illegal run status {run['status']!r}"
    phase = str(run["campaign_phase"])
    assert phase in {p.value for p in CampaignPhase}, f"{ctx}: illegal phase {phase!r}"
    rank = PHASE_RANK[phase]
    assert rank >= prev_phase_rank, f"{ctx}: campaign_phase regressed {prev_phase_rank} -> {rank}"

    # I1, I2, I9: Claims 5-axis coherence & fresh-falsifier separation
    claims = conn.execute("SELECT * FROM claims ORDER BY rowid ASC").fetchall()
    valid_claim_statuses = {s.value for s in ClaimStatus}
    for c in claims:
        st = str(c["status"])
        assert st in valid_claim_statuses, f"{ctx}: illegal claim status {st!r}"
        expected = derive_claim_axes(st)
        assert c["research_state"] == expected.research_state.value, (
            f"{ctx}: claim {c['claim_id']} research_state={c['research_state']!r} != {expected.research_state.value!r} for status={st!r}"
        )
        assert c["evidence_state"] == expected.evidence_state.value, (
            f"{ctx}: claim {c['claim_id']} evidence_state={c['evidence_state']!r} != {expected.evidence_state.value!r} for status={st!r}"
        )
        prop = str(c["proposer_worker_id"] or "").strip()
        fals = str(c["falsifier_worker_id"] or "").strip()
        if fals:
            assert prop != fals, f"{ctx}: fresh-falsifier violation on {c['claim_id']}: proposer == falsifier == {prop!r}"

    # I3, I9: Orphaned anomaly survival
    anomalies = conn.execute("SELECT * FROM anomalies ORDER BY rowid ASC").fetchall()
    valid_anom_statuses = {s.value for s in AnomalyStatus}
    claim_status_by_id = {str(c["claim_id"]): str(c["status"]) for c in claims}
    for a in anomalies:
        ast = str(a["status"])
        assert ast in valid_anom_statuses, f"{ctx}: illegal anomaly status {ast!r}"
        if ast == "consumed_by_claim" and a["consumed_by_id"]:
            cid = str(a["consumed_by_id"])
            assert claim_status_by_id.get(cid) != "falsified", (
                f"{ctx}: anomaly {a['anomaly_id']} still consumed by falsified claim {cid}"
            )

    # I4, I9: Primitive chained <-> status sync
    prims = conn.execute("SELECT primitive_id, status, chained FROM primitives ORDER BY rowid ASC").fetchall()
    valid_prim_statuses = {s.value for s in PrimitiveStatus}
    for p in prims:
        pst = str(p["status"])
        assert pst in valid_prim_statuses, f"{ctx}: illegal primitive status {pst!r}"
        if pst == "dry":
            assert int(p["chained"]) == 0, f"{ctx}: dry primitive {p['primitive_id']} has chained=1"
        if int(p["chained"]) == 1:
            assert pst == "chained", f"{ctx}: chained=1 primitive {p['primitive_id']} has status={pst!r}"

    # I6, I9: Tasks enum & hunt-phase patch gating
    tasks = conn.execute("SELECT task_id, kind, status FROM tasks ORDER BY rowid ASC").fetchall()
    valid_task_statuses = {s.value for s in TaskStatus}
    for t in tasks:
        tst = str(t["status"])
        assert tst in valid_task_statuses, f"{ctx}: illegal task status {tst!r}"
        if phase == "hunt" and t["kind"] == "patch":
            assert tst != "leased", f"{ctx}: patch task {t['task_id']} leased during hunt phase"

    # I9: Doors & Jewels enums
    for d in conn.execute("SELECT status FROM parked_doors ORDER BY rowid ASC").fetchall():
        assert d["status"] in {s.value for s in DoorStatus}, f"{ctx}: illegal door status {d['status']!r}"
    for j in conn.execute("SELECT status FROM crown_jewels ORDER BY rowid ASC").fetchall():
        assert j["status"] in {s.value for s in JewelStatus}, f"{ctx}: illegal jewel status {j['status']!r}"

    # I7: Strict read-only gate purity (detects inserts AND in-place updates)
    before_snap = _table_snapshot(conn)
    check_all_gates(conn, target_dir=target_dir, auto_enqueue_chain=False)
    after_snap = _table_snapshot(conn)
    assert before_snap == after_snap, f"{ctx}: read-only check_all_gates mutated tables!"

    return rank


def _run_simulation_seed(
    seed: int,
    *,
    steps: int,
    target_dir: pathlib.Path,
    ajar_home: pathlib.Path,
    stats: dict[str, int] | None = None,
    deterministic_ids: bool = False,
    template_db: pathlib.Path | None = None,
) -> None:
    rng = random.Random(seed)
    clock = _DeterministicClock()
    id_seq = 0

    def _det_new_id(prefix: str) -> str:
        nonlocal id_seq
        id_seq += 1
        return f"{prefix}-{seed:04d}{id_seq:04d}"

    def _bump(key: str, n: int = 1) -> None:
        if stats is not None:
            stats[key] = stats.get(key, 0) + n

    run_id = f"dst-seed-{seed:04d}"
    with ExitStack() as stack:
        stack.enter_context(mock.patch.dict(os.environ, {"AJAR_HOME": str(ajar_home)}))
        stack.enter_context(mock.patch.object(db_mod, "utc_now_iso", side_effect=clock.iso))
        stack.enter_context(mock.patch.object(store_util_mod, "utc_now_iso", side_effect=clock.iso))
        stack.enter_context(mock.patch.object(epistemic_hooks_mod, "utc_now_iso", side_effect=clock.iso))
        stack.enter_context(mock.patch.object(reactions_mod, "utc_now_iso", side_effect=clock.iso))
        stack.enter_context(mock.patch.object(workflow_mod, "utc_now_iso", side_effect=clock.iso))
        stack.enter_context(mock.patch.object(chain_planner_mod, "utc_now_iso", side_effect=clock.iso))
        stack.enter_context(mock.patch.object(swarm_mod, "utc_now_iso", side_effect=clock.iso))
        stack.enter_context(mock.patch.object(db_mod.time, "time", side_effect=clock.epoch))
        stack.enter_context(mock.patch.object(workflow_mod.time, "time", side_effect=clock.epoch))
        if deterministic_ids:
            stack.enter_context(mock.patch.object(db_mod, "new_id", side_effect=_det_new_id))
            stack.enter_context(mock.patch.object(store_util_mod, "new_id", side_effect=_det_new_id))
            stack.enter_context(mock.patch.object(epistemic_hooks_mod, "new_id", side_effect=_det_new_id))
            stack.enter_context(mock.patch.object(reactions_mod, "new_id", side_effect=_det_new_id))
            stack.enter_context(mock.patch.object(workflow_mod, "new_id", side_effect=_det_new_id))
            stack.enter_context(mock.patch.object(chain_planner_mod, "new_id", side_effect=_det_new_id))
            stack.enter_context(mock.patch.object(swarm_mod, "new_id", side_effect=_det_new_id))

        conn = _bootstrap_sim_run(run_id, target_dir, ajar_home=ajar_home, template_db=template_db)
        try:
            # Seed one global steer so Certified Run Prefix exercises non-trivial steering content.
            add_steer(conn, rule_text="DST invariant: never skip auth boundary", scope="global")
            phase_rank = 0
            loci = [
                "src/auth.py:1",
                "src/auth.py:4",
                "src/parser.py:1",
                "src/parser.py:4",
                "src/vault.py:1",
                "src/vault.py:4",
            ]
            ops = (
                "surface_add",
                "task_add",
                "task_lease",
                "task_done",
                "task_dry",
                "task_block",
                "anomaly_add",
                "anomaly_explain",
                "claim_propose",
                "claim_falsify",
                "claim_config_gate",
                "claim_survive",
                "claim_rescope",
                "claim_block",
                "primitive_add",
                "primitive_dry",
                "door_park",
                "phase_advance",
                "spend_over_cap",
                "illegal_probe",
            )

            for step in range(steps):
                op = rng.choice(ops)
                worker = rng.choice(WORKERS)
                locus = rng.choice(loci)
                use_mcp = rng.random() < 0.35

                if op == "surface_add":
                    if use_mcp:
                        dispatch_mcp_tool(
                            run_id,
                            "ajar_surface_add",
                            {
                                "name": f"surf_{step}",
                                "kind": "entry_point",
                                "locus": locus,
                                "priority": rng.choice(["critical", "high", "medium", "low"]),
                            },
                        )
                    else:
                        add_surface(
                            conn,
                            name=f"surf_{step}",
                            kind="entry_point",
                            locus=locus,
                            priority=rng.choice(["critical", "high", "medium", "low"]),
                        )
                    _bump("surfaces_added")

                elif op == "task_add":
                    uncovered = conn.execute(
                        """
                        SELECT surface_id, locus FROM surfaces s
                        WHERE NOT EXISTS (SELECT 1 FROM tasks t WHERE t.surface_id = s.surface_id)
                        ORDER BY s.rowid ASC LIMIT 1
                        """
                    ).fetchone()
                    surf_id = str(uncovered["surface_id"]) if uncovered is not None else None
                    task_locus = str(uncovered["locus"]) if uncovered is not None else locus
                    tid = _det_new_id("tsk") if deterministic_ids else new_id("tsk")
                    kind = rng.choice(["investigate", "falsify", "patch"])
                    pri = rng.choice(["critical", "high", "medium", "low"])
                    now = clock.iso()
                    sal = compute_task_salience(
                        conn,
                        {
                            "priority": pri,
                            "kind": kind,
                            "subsystem": task_locus.split("/", 1)[0],
                            "locus": task_locus,
                            "reopened_boost": 0,
                        },
                    )
                    with immediate_tx(conn):
                        conn.execute(
                            """
                            INSERT INTO tasks(
                                task_id, surface_id, kind, title, subsystem, locus, priority, salience_score,
                                status, created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)
                            """,
                            (
                                tid,
                                surf_id,
                                kind,
                                f"Task {step} ({kind})",
                                task_locus.split("/", 1)[0],
                                task_locus,
                                pri,
                                sal,
                                now,
                                now,
                            ),
                        )
                    _bump("tasks_added")

                elif op == "task_lease":
                    kind_opt = rng.choice([None, "investigate", "patch"])
                    leased = lease_next_task(conn, worker_id=worker, kind=kind_opt, recover=True)
                    phase_now = str(conn.execute("SELECT campaign_phase FROM runs LIMIT 1").fetchone()["campaign_phase"])
                    if leased is not None and phase_now == "hunt":
                        assert leased["kind"] != "patch", f"seed={seed} step={step}: leased patch during hunt"

                elif op == "task_done":
                    row = conn.execute(
                        "SELECT task_id FROM tasks WHERE status IN ('open', 'leased') ORDER BY rowid ASC LIMIT 1"
                    ).fetchone()
                    if row is not None:
                        if use_mcp:
                            dispatch_mcp_tool(
                                run_id,
                                "ajar_task_close",
                                {
                                    "task_id": str(row["task_id"]),
                                    "worker_id": worker,
                                    "outcome": "done",
                                    "summary": f"Completed step {step}",
                                },
                            )
                        else:
                            close_task_done(
                                conn,
                                task_id=str(row["task_id"]),
                                worker_id=worker,
                                summary=f"Completed step {step}",
                                target_dir=target_dir,
                            )

                elif op == "task_dry":
                    row = conn.execute(
                        "SELECT task_id FROM tasks WHERE status IN ('open', 'leased') ORDER BY rowid ASC LIMIT 1"
                    ).fetchone()
                    if row is not None:
                        try:
                            if use_mcp:
                                dispatch_mcp_tool(
                                    run_id,
                                    "ajar_task_close",
                                    {
                                        "task_id": str(row["task_id"]),
                                        "worker_id": worker,
                                        "outcome": "dry",
                                        "control_locus": locus,
                                        "control_reason": "Bounds guard enforces length and range invariant before write",
                                    },
                                )
                            else:
                                close_task_dry(
                                    conn,
                                    task_id=str(row["task_id"]),
                                    worker_id=worker,
                                    locus=locus,
                                    control_reason="Bounds guard enforces length and range invariant before write",
                                    target_dir=target_dir,
                                    target_mode="source",
                                )
                        except AjarError:
                            # Guarded-primitive dry block is a legitimate gate block.
                            pass

                elif op == "task_block":
                    row = conn.execute(
                        "SELECT task_id FROM tasks WHERE status IN ('open', 'leased') ORDER BY rowid ASC LIMIT 1"
                    ).fetchone()
                    if row is not None:
                        block_task(
                            conn,
                            task_id=str(row["task_id"]),
                            worker_id=worker,
                            predicate="waiting_for_guard_bypass",
                            check_locus=locus,
                        )

                elif op == "anomaly_add":
                    if use_mcp:
                        dispatch_mcp_tool(
                            run_id,
                            "ajar_anomaly_add",
                            {
                                "locus": locus,
                                "observation": f"Unexpected parser edge state observed at step {step}",
                            },
                        )
                    else:
                        add_anomaly(
                            conn,
                            locus=locus,
                            observation=f"Unexpected parser edge state observed at step {step}",
                            target_dir=target_dir,
                        )

                elif op == "anomaly_explain":
                    row = conn.execute(
                        "SELECT anomaly_id FROM anomalies WHERE status = 'unexplained' ORDER BY rowid ASC LIMIT 1"
                    ).fetchone()
                    if row is not None:
                        explain_anomaly(
                            conn,
                            anomaly_id=str(row["anomaly_id"]),
                            locus=locus,
                            reason="Verified benign fallback path returns error without side effect",
                        )

                elif op == "claim_propose":
                    anom = conn.execute(
                        "SELECT anomaly_id FROM anomalies WHERE status = 'unexplained' ORDER BY rowid ASC LIMIT 1"
                    ).fetchone()
                    anom_id = str(anom["anomaly_id"]) if (anom is not None and rng.random() < 0.6) else None
                    try:
                        if use_mcp:
                            dispatch_mcp_tool(
                                run_id,
                                "ajar_claim_propose",
                                {
                                    "worker_id": worker,
                                    "title": f"Boundary condition defect #{step}",
                                    "locus": locus,
                                    "mechanism": f"Input bypasses validation branch #{step} at {locus} reaching sink",
                                    "falsification_prediction": f"Crafted input #{step} passes check and alters state",
                                    "falsification_test": "python3 -c 'print(1)'",
                                    "severity": rng.choice(["critical", "high", "medium", "low"]),
                                    "consume_anomaly_id": anom_id,
                                },
                            )
                        else:
                            propose_claim(
                                conn,
                                worker_id=worker,
                                title=f"Boundary condition defect #{step}",
                                locus=locus,
                                mechanism=f"Input bypasses validation branch #{step} at {locus} reaching sink",
                                falsification_prediction=f"Crafted input #{step} passes check and alters state",
                                falsification_test="python3 -c 'print(1)'",
                                severity=rng.choice(["critical", "high", "medium", "low"]),
                                consume_anomaly_id=anom_id,
                                target_dir=target_dir,
                                target_mode="source",
                            )
                        _bump("claims_proposed")
                    except AjarError:
                        # Dead-end repetition guard may reject duplicate locus/mechanism.
                        pass

                elif op in ("claim_falsify", "claim_config_gate"):
                    row = conn.execute(
                        "SELECT claim_id, proposer_worker_id FROM claims WHERE status IN ('proposed', 'config_gated') ORDER BY rowid ASC LIMIT 1"
                    ).fetchone()
                    if row is not None:
                        other_workers = [w for w in WORKERS if w != row["proposer_worker_id"]]
                        falsifier = rng.choice(other_workers)
                        cfg = f"FLAG_{step}=1" if op == "claim_config_gate" else ""
                        if use_mcp:
                            dispatch_mcp_tool(
                                run_id,
                                "ajar_claim_falsify",
                                {
                                    "claim_id": str(row["claim_id"]),
                                    "worker_id": falsifier,
                                    "notes": f"Checked guard at {locus}",
                                    "control_locus": locus,
                                    "config_gate": cfg,
                                },
                            )
                        else:
                            falsify_claim(
                                conn,
                                claim_id=str(row["claim_id"]),
                                worker_id=falsifier,
                                notes=f"Checked guard at {locus}",
                                control_locus=locus,
                                config_gate=cfg,
                            )

                elif op == "claim_survive":
                    row = conn.execute(
                        "SELECT claim_id, proposer_worker_id FROM claims WHERE status IN ('proposed', 'config_gated') ORDER BY rowid ASC LIMIT 1"
                    ).fetchone()
                    if row is not None:
                        other_workers = [w for w in WORKERS if w != row["proposer_worker_id"]]
                        falsifier = rng.choice(other_workers)
                        if use_mcp:
                            dispatch_mcp_tool(
                                run_id,
                                "ajar_claim_survive",
                                {
                                    "claim_id": str(row["claim_id"]),
                                    "worker_id": falsifier,
                                    "notes": f"Independent check confirmed reachability at {locus}",
                                },
                            )
                        else:
                            survive_claim(
                                conn,
                                claim_id=str(row["claim_id"]),
                                worker_id=falsifier,
                                notes=f"Independent check confirmed reachability at {locus}",
                            )

                elif op == "claim_rescope":
                    row = conn.execute(
                        "SELECT claim_id FROM claims WHERE status IN ('proposed', 'survived_falsify', 'needs_instrumentation') ORDER BY rowid ASC LIMIT 1"
                    ).fetchone()
                    if row is not None:
                        rescope_claim_service(
                            conn,
                            claim_id=str(row["claim_id"]),
                            worker_id=worker,
                            reason=f"Refined locus to {locus}",
                            locus=locus,
                        )

                elif op == "claim_block":
                    row = conn.execute(
                        "SELECT claim_id FROM claims WHERE status = 'proposed' ORDER BY rowid ASC LIMIT 1"
                    ).fetchone()
                    if row is not None:
                        block_claim(
                            conn,
                            claim_id=str(row["claim_id"]),
                            worker_id=worker,
                            reason="Requires external HSM hardware unavailable in sandbox",
                            env_blocker="missing_hardware",
                            target_mode="source",
                        )

                elif op == "primitive_add":
                    pid = _det_new_id("prim") if deterministic_ids else new_id("prim")
                    now = clock.iso()
                    with immediate_tx(conn):
                        conn.execute(
                            """
                            INSERT INTO primitives(
                                primitive_id, kind, role, subsystem, locus,
                                preconditions, postconditions, evidence_cmd,
                                status, chained, created_at
                            ) VALUES (?, 'state_corrupt', 'capability', 'src', ?, 'pre', 'post', 'true', 'active', 0, ?)
                            """,
                            (pid, locus, now),
                        )

                elif op == "primitive_dry":
                    row = conn.execute(
                        "SELECT primitive_id FROM primitives WHERE status = 'active' ORDER BY rowid ASC LIMIT 1"
                    ).fetchone()
                    if row is not None:
                        mark_primitive_dry(
                            conn,
                            target_dir=target_dir,
                            target_mode="source",
                            primitive_id=str(row["primitive_id"]),
                            worker_id=worker,
                            locus=locus,
                            reason="Guard strictly rejects crafted offset before memory write",
                        )

                elif op == "door_park":
                    jrow = conn.execute("SELECT jewel_id FROM crown_jewels ORDER BY rowid ASC LIMIT 1").fetchone()
                    if jrow is None:
                        jres = add_crown_jewel(
                            conn,
                            name="Vault Balance Integrity",
                            locus="src/vault.py:1",
                            impact_class="fund_drain",
                            symbols=["withdraw"],
                            worker_id=worker,
                        )
                        jewel_id = str(jres["jewel_id"])
                    else:
                        jewel_id = str(jrow["jewel_id"])
                    direction = rng.choice(VALID_DOOR_DIRECTIONS)
                    park_open_door(
                        conn,
                        anchor_locus=locus,
                        missing_link_summary=f"Need authenticated token bridge #{step}",
                        jewel_id=jewel_id,
                        direction=direction,
                        wanted_tags="auth_bypass",
                        spawn_hunters=False,
                        worker_id=worker,
                    )
                    compute_chain_frontier(conn)
                    _bump("doors_parked")

                elif op == "phase_advance":
                    target_phase = rng.choice(["hunt", "remediate", "full"])
                    cur_phase = str(conn.execute("SELECT campaign_phase FROM runs LIMIT 1").fetchone()["campaign_phase"])
                    if PHASE_RANK[target_phase] < PHASE_RANK[cur_phase]:
                        try:
                            advance_phase(conn, run_id=run_id, to_phase=target_phase)
                            raise AssertionError(
                                f"seed={seed} step={step}: illegal phase {cur_phase}->{target_phase} succeeded!"
                            )
                        except InvalidTransitionError:
                            _bump("illegal_probes_rejected")
                    else:
                        advance_phase(conn, run_id=run_id, to_phase=target_phase)

                elif op == "spend_over_cap":
                    # Host Mode advisory check: record spend > 100% of cogs_cap_usd via CLI,
                    # then verify `runs.status` stays active AND `lease_next_task` still leases work!
                    out_buf, err_buf = io.StringIO(), io.StringIO()
                    with redirect_stdout(out_buf), redirect_stderr(err_buf):
                        rc_sp = cli_main(
                            [
                                "spend",
                                "add",
                                "--run",
                                run_id,
                                "--worker",
                                worker,
                                "--phase",
                                "explore",
                                "--model",
                                "host-model",
                                "--tokens-in",
                                "1000",
                                "--tokens-out",
                                "500",
                                "--cost-usd",
                                "50.0",
                            ]
                        )
                    assert rc_sp == 0, f"seed={seed} step={step}: ajar spend add failed: {err_buf.getvalue()}"
                    check_all_gates(conn, target_dir=target_dir, auto_enqueue_chain=False)
                    st_after = str(conn.execute("SELECT status FROM runs LIMIT 1").fetchone()["status"])
                    assert st_after == "active", f"seed={seed} step={step}: spend_ledger mutated Host Mode run status to {st_after!r}!"
                    # Enqueue a fresh investigate task if none open, then prove Host Mode STILL leases it.
                    open_inv = conn.execute(
                        "SELECT task_id FROM tasks WHERE status = 'open' AND kind = 'investigate' ORDER BY rowid ASC LIMIT 1"
                    ).fetchone()
                    if open_inv is None:
                        with immediate_tx(conn):
                            conn.execute(
                                """
                                INSERT INTO tasks(
                                    task_id, kind, title, subsystem, locus, priority, salience_score,
                                    status, created_at, updated_at
                                ) VALUES (?, 'investigate', 'Advisory budget lease probe', 'src', ?, 'high', 80, 'open', ?, ?)
                                """,
                                (_det_new_id("tsk") if deterministic_ids else new_id("tsk"), locus, clock.iso(), clock.iso()),
                            )
                    leased_over_cap = lease_next_task(conn, worker_id=worker, kind="investigate", recover=False)
                    assert leased_over_cap is not None, (
                        f"seed={seed} step={step}: Host Mode blocked task leasing after spend exceeded cogs_cap_usd!"
                    )
                    _bump("spend_over_cap_leases")

                elif op == "illegal_probe":
                    clm = conn.execute("SELECT claim_id, proposer_worker_id FROM claims ORDER BY rowid ASC LIMIT 1").fetchone()
                    if clm is not None:
                        try:
                            falsify_claim(
                                conn,
                                claim_id=str(clm["claim_id"]),
                                worker_id=f" {clm['proposer_worker_id']} ",
                                notes="whitespace self-falsify attempt",
                            )
                            raise AssertionError(f"seed={seed} step={step}: whitespace self-falsify bypassed!")
                        except AjarError:
                            _bump("illegal_probes_rejected")

                    fal = conn.execute(
                        "SELECT claim_id, proposer_worker_id FROM claims WHERE status = 'falsified' ORDER BY rowid ASC LIMIT 1"
                    ).fetchone()
                    if fal is not None:
                        other = next(w for w in WORKERS if w != fal["proposer_worker_id"])
                        try:
                            survive_claim(conn, claim_id=str(fal["claim_id"]), worker_id=other, notes="resurrect")
                            raise AssertionError(f"seed={seed} step={step}: falsified -> survived_falsify succeeded!")
                        except InvalidTransitionError:
                            _bump("illegal_probes_rejected")

                phase_rank = _assert_global_invariants(
                    conn,
                    target_dir=target_dir,
                    seed=seed,
                    step=step,
                    prev_phase_rank=phase_rank,
                )

            # Verify KV prefix-cache byte identity across distinct tasks (with real steer in prefix)
            t_rows = conn.execute("SELECT task_id FROM tasks ORDER BY rowid ASC LIMIT 2").fetchall()
            if len(t_rows) < 2:
                for idx in range(2 - len(t_rows)):
                    with immediate_tx(conn):
                        conn.execute(
                            """
                            INSERT INTO tasks(
                                task_id, kind, title, subsystem, locus, priority, salience_score,
                                status, created_at, updated_at
                            ) VALUES (?, 'investigate', ?, 'src', ?, 'medium', 40, 'open', ?, ?)
                            """,
                            (_det_new_id("tsk") if deterministic_ids else new_id("tsk"), f"Prefix check {idx}", loci[idx], clock.iso(), clock.iso()),
                        )
                t_rows = conn.execute("SELECT task_id FROM tasks ORDER BY rowid ASC LIMIT 2").fetchall()
            ctx_a = render_task_context(conn, str(t_rows[0]["task_id"]))["rendered"]
            ctx_b = render_task_context(conn, str(t_rows[1]["task_id"]))["rendered"]
            marker = "## Task Delta"
            assert marker in ctx_a and marker in ctx_b, f"seed={seed}: render_task_context missing {marker!r}"
            assert "DST invariant: never skip auth boundary" in ctx_a.split(marker, 1)[0]
            assert ctx_a.split(marker, 1)[0] == ctx_b.split(marker, 1)[0], (
                f"seed={seed}: Certified Run Prefix drifted between tasks!"
            )

            # Explicit closeout -> finish -> post-finish immutability -> reopen_run lifecycle verification!
            # (Runs on every 4th seed so every test run exercises finish + post-finish rejection + reopen axis sync!)
            if seed % 4 == 1:
                # 1. Ensure >= 1 surface exists, cover any remaining uncovered high/critical surfaces, and resolve open blockers.
                if int(conn.execute("SELECT COUNT(*) FROM surfaces").fetchone()[0]) == 0:
                    add_surface(conn, name="closeout_surf", kind="entry_point", locus="src/auth.py:1", priority="high")
                for srow in conn.execute(
                    """
                    SELECT surface_id, locus FROM surfaces s
                    WHERE priority IN ('critical', 'high')
                      AND NOT EXISTS (SELECT 1 FROM tasks t WHERE t.surface_id = s.surface_id)
                    ORDER BY s.rowid ASC
                    """
                ).fetchall():
                    tid = _det_new_id("tsk") if deterministic_ids else new_id("tsk")
                    with immediate_tx(conn):
                        conn.execute(
                            """
                            INSERT INTO tasks(
                                task_id, surface_id, kind, title, subsystem, locus, priority, salience_score,
                                status, created_at, updated_at
                            ) VALUES (?, ?, 'investigate', 'Closeout coverage', 'src', ?, 'high', 60, 'open', ?, ?)
                            """,
                            (tid, str(srow["surface_id"]), str(srow["locus"]), clock.iso(), clock.iso()),
                        )
                for trow in conn.execute(
                    "SELECT task_id FROM tasks WHERE status IN ('open', 'leased') ORDER BY rowid ASC"
                ).fetchall():
                    close_task_done(conn, task_id=str(trow["task_id"]), worker_id="w-alpha", summary="closeout", target_dir=target_dir)
                for crow in conn.execute(
                    "SELECT claim_id, proposer_worker_id, locus, status FROM claims WHERE status IN ('proposed', 'config_gated', 'survived_falsify', 'needs_instrumentation') ORDER BY rowid ASC"
                ).fetchall():
                    other = next(w for w in WORKERS if w != crow["proposer_worker_id"])
                    if crow["status"] in ("proposed", "config_gated"):
                        falsify_claim(
                            conn,
                            claim_id=str(crow["claim_id"]),
                            worker_id=other,
                            notes="Disproved during closeout verification",
                            control_locus=str(crow["locus"]),
                        )
                    else:
                        block_claim(
                            conn,
                            claim_id=str(crow["claim_id"]),
                            worker_id=other,
                            reason="Requires privileged kernel lab unavailable in closeout",
                            env_blocker="privileged_kernel",
                            target_mode="source",
                        )
                for arow in conn.execute(
                    "SELECT anomaly_id, locus FROM anomalies WHERE status = 'unexplained' ORDER BY rowid ASC"
                ).fetchall():
                    explain_anomaly(
                        conn,
                        anomaly_id=str(arow["anomaly_id"]),
                        locus=str(arow["locus"]),
                        reason="Verified benign during closeout pass",
                    )
                # Ensure one non-exempt policy-blocked claim exists so `reopen_run` exercises claim unblocking + axis sync!
                reopen_clm = propose_claim(
                    conn,
                    worker_id="w-alpha",
                    title="Reopen axis coherence check claim",
                    locus="src/auth.py:4",
                    mechanism="Synthetic policy-blocked claim to verify reopen_run updates research_state and evidence_state",
                    falsification_prediction="Reopen restores proposed state and synchronized research_state",
                    falsification_test="python3 -c 'print(1)'",
                    target_dir=target_dir,
                    target_mode="source",
                )
                blk_axes = derive_claim_axes("blocked")
                with immediate_tx(conn):
                    conn.execute(
                        """
                        UPDATE claims
                        SET status = 'blocked', research_state = ?, evidence_state = ?,
                            blocker_reason = 'External staging API unreachable during sandbox run',
                            env_blocker = 'external_service', updated_at = ?
                        WHERE claim_id = ?
                        """,
                        (blk_axes.research_state.value, blk_axes.evidence_state.value, clock.iso(), reopen_clm["claim_id"]),
                    )
                for prow in conn.execute(
                    "SELECT primitive_id, locus FROM primitives WHERE status = 'active' ORDER BY rowid ASC"
                ).fetchall():
                    mark_primitive_dry(
                        conn,
                        target_dir=target_dir,
                        target_mode="source",
                        primitive_id=str(prow["primitive_id"]),
                        worker_id="w-alpha",
                        locus=str(prow["locus"]),
                        reason="Verified non-exploitable guard during closeout pass",
                    )

                fin = finish_run(conn, run_id=run_id, target_dir=target_dir, actor="operator")
                assert fin["passed"], f"seed={seed}: expected closeout finish_run to pass, got {fin}"
                _bump("runs_finished")

                # Post-finish immutability check
                try:
                    add_surface(conn, name="post_finish_illegal", kind="entry_point", locus="src/auth.py:1")
                    raise AssertionError(f"seed={seed}: post-finish add_surface succeeded!")
                except InvalidTransitionError:
                    _bump("illegal_probes_rejected")

                # Reopen cycle + verify claim axes stay 100% coherent after reopen_run!
                reopened = reopen_run(run_id, ajar_home=ajar_home)
                assert reopen_clm["claim_id"] in reopened["unblocked_claim_ids"], (
                    f"seed={seed}: reopen_run did not unblock policy-blocked claim {reopen_clm['claim_id']}"
                )
                _bump("runs_reopened")
                phase_rank = _assert_global_invariants(
                    conn,
                    target_dir=target_dir,
                    seed=seed,
                    step=steps + 1,
                    prev_phase_rank=phase_rank,
                )

            qc = conn.execute("PRAGMA quick_check").fetchone()
            assert qc is not None and qc[0] == "ok", f"seed={seed}: SQLite quick_check failed: {qc}"
        finally:
            conn.close()


class DeterministicStateMachineSimTests(unittest.TestCase):
    def test_seeded_multi_worker_simulation_preserves_all_invariants(self) -> None:
        single_seed = os.environ.get("AJAR_DST_SEED")
        if single_seed is not None:
            seeds = [int(single_seed)]
        else:
            count = int(os.environ.get("AJAR_DST_SEEDS", "20"))
            seeds = list(range(1, count + 1))

        stats: dict[str, int] = {}
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            target_dir = _seed_target_dir(base / "target")
            ajar_home = base / "ajar_home"
            tpl_home = base / "tpl_home"
            tpl_conn = open_run_db("dst-template", create=True, ajar_home=tpl_home)
            tpl_conn.close()
            template_db = tpl_home / "runs" / "dst-template" / "run.db"
            for seed in seeds:
                _run_simulation_seed(
                    seed,
                    steps=40,
                    target_dir=target_dir,
                    ajar_home=ajar_home,
                    stats=stats,
                    template_db=template_db,
                )

        if single_seed is None:
            for key in (
                "surfaces_added",
                "tasks_added",
                "claims_proposed",
                "doors_parked",
                "spend_over_cap_leases",
                "runs_finished",
                "runs_reopened",
                "illegal_probes_rejected",
            ):
                self.assertGreater(stats.get(key, 0), 0, f"DST branch {key!r} was vacuous (0 executions): {stats}")

    def test_single_seed_replay_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            target_dir = _seed_target_dir(base / "target")
            home_a = base / "home_a"
            home_b = base / "home_b"
            _run_simulation_seed(7, steps=35, target_dir=target_dir, ajar_home=home_a, deterministic_ids=True)
            _run_simulation_seed(7, steps=35, target_dir=target_dir, ajar_home=home_b, deterministic_ids=True)

            def _dump(home: pathlib.Path) -> tuple[object, ...]:
                with mock.patch.dict(os.environ, {"AJAR_HOME": str(home)}):
                    c = open_run_db("dst-seed-0007")
                    try:
                        return (
                            [tuple(r) for r in c.execute("SELECT status, campaign_phase FROM runs").fetchall()],
                            [
                                tuple(r)
                                for r in c.execute(
                                    "SELECT claim_id, status, research_state, evidence_state FROM claims ORDER BY rowid ASC"
                                ).fetchall()
                            ],
                            [tuple(r) for r in c.execute("SELECT task_id, status FROM tasks ORDER BY rowid ASC").fetchall()],
                            [tuple(r) for r in c.execute("SELECT door_id, status FROM parked_doors ORDER BY rowid ASC").fetchall()],
                        )
                    finally:
                        c.close()

            self.assertEqual(_dump(home_a), _dump(home_b))

    def test_two_strike_repro_failure_pivots_to_instrumentation_and_enqueues_task(self) -> None:
        from ajar.db import record_repro_failure

        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            target_dir = _seed_target_dir(base / "target")
            ajar_home = base / "ajar_home"
            with mock.patch.dict(os.environ, {"AJAR_HOME": str(ajar_home)}):
                conn = _bootstrap_sim_run("dst-2strike", target_dir, ajar_home=ajar_home)
                try:
                    surf = add_surface(
                        conn,
                        name="Auth handler",
                        kind="http",
                        subsystem="src",
                        locus="src/auth.py:1",
                        priority="high",
                        trust_boundary="ext->auth",
                    )
                    clm = propose_claim(
                        conn,
                        worker_id="w-prop",
                        title="Bypass check on empty token",
                        locus="src/auth.py:1",
                        severity="high",
                        mechanism="Unchecked prefix match allows empty token bypass",
                        surface_id=str(surf["surface_id"]),
                        falsification_prediction="Empty token fails auth",
                        falsification_test="Submit empty token",
                    )
                    cid = str(clm["claim_id"])
                    survive_claim(
                        conn,
                        claim_id=cid,
                        worker_id="w-fals",
                        notes="Confirmed reachable via verify()",
                    )

                    # Strike 1: stays survived_falsify.
                    clm_row0 = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (cid,)).fetchone()
                    r1 = record_repro_failure(
                        conn,
                        claim=clm_row0,
                        worker_id="w-repro",
                        observation_hash="neg-hash-1",
                        reason="Arm 1 exit 0",
                    )
                    self.assertFalse(r1["pivoted_to_instrumentation"])
                    self.assertEqual(r1["failed_repro_count"], 1)

                    # Strike 2 (identical observation hash): pivots to needs_instrumentation + spawns instrument task.
                    clm_row1 = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (cid,)).fetchone()
                    r2 = record_repro_failure(
                        conn,
                        claim=clm_row1,
                        worker_id="w-repro",
                        observation_hash="neg-hash-1",
                        reason="Arm 1 exit 0 again",
                    )
                    self.assertTrue(r2["pivoted_to_instrumentation"])
                    self.assertTrue(r2["instrument_task_id"])
                    clm_row = conn.execute("SELECT status FROM claims WHERE claim_id = ?", (cid,)).fetchone()
                    self.assertEqual(str(clm_row["status"]), "needs_instrumentation")
                    inst_row = conn.execute(
                        "SELECT kind, status FROM tasks WHERE task_id = ?",
                        (str(r2["instrument_task_id"]),),
                    ).fetchone()
                    self.assertEqual(str(inst_row["kind"]), "instrument")
                    self.assertEqual(str(inst_row["status"]), "open")
                    _assert_global_invariants(conn, target_dir=target_dir, seed=901, step=1, prev_phase_rank=0)
                finally:
                    conn.close()

    def test_primitive_addition_wakes_parked_door_and_percolates_multi_hop_path(self) -> None:
        from ajar.chain_planner import detect_percolated_multi_hop_paths
        from ajar.services import add_primitive

        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            target_dir = _seed_target_dir(base / "target")
            ajar_home = base / "ajar_home"
            with mock.patch.dict(os.environ, {"AJAR_HOME": str(ajar_home)}):
                conn = _bootstrap_sim_run("dst-percolate", target_dir, ajar_home=ajar_home)
                try:
                    jwl = add_crown_jewel(
                        conn,
                        name="Admin token mint",
                        impact_class="auth_bypass",
                        locus="src/auth.py:4",
                    )
                    door = park_open_door(
                        conn,
                        anchor_locus="src/auth.py:4",
                        missing_link_summary="Requires cap:forge_cookie to mint admin session",
                        jewel_id=str(jwl["jewel_id"]),
                        blocker_locus="src/auth.py:1",
                        wanted_tags=["cap:forge_cookie"],
                        direction="sink_to_source",
                        spawn_hunters=False,
                    )
                    door_id = str(door["door_id"])

                    # Hop 1: untrusted entry in billing.py -> cap:leak_secret
                    add_primitive(
                        conn,
                        kind="info_leak",
                        locus="src/billing.py:1",
                        preconditions="unauthenticated request",
                        postconditions="leaks hmac secret",
                        evidence_cmd="python3 -c 'print(1)'",
                        provides_tags=["cap:leak_secret"],
                        requires_tags=[],
                    )
                    # Hop 2: cap:leak_secret -> cap:forge_cookie (wakes door + completes 2-hop percolation!)
                    add_primitive(
                        conn,
                        kind="auth_bypass",
                        locus="src/auth.py:4",
                        preconditions="requires cap:leak_secret",
                        postconditions="mints forged session cookie",
                        evidence_cmd="python3 -c 'print(2)'",
                        provides_tags=["cap:forge_cookie"],
                        requires_tags=["cap:leak_secret"],
                    )

                    drow = conn.execute("SELECT status FROM parked_doors WHERE door_id = ?", (door_id,)).fetchone()
                    self.assertEqual(str(drow["status"]), "ready")
                    perc = detect_percolated_multi_hop_paths(conn, enqueue_tasks=False)
                    self.assertGreaterEqual(len(perc["percolated_paths"]), 1)
                    self.assertGreaterEqual(perc["percolated_paths"][0]["hop_count"], 2)
                    _assert_global_invariants(conn, target_dir=target_dir, seed=902, step=1, prev_phase_rank=0)
                finally:
                    conn.close()

    def test_diff_sync_preserves_build_cmd_and_global_invariants(self) -> None:
        import subprocess

        from ajar.diff_sync import sync_pr_differential_state
        from ajar.services import record_reproduction_outcome

        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            target_dir = _seed_target_dir(base / "target")
            ajar_home = base / "ajar_home"
            env = {
                **os.environ,
                "GIT_AUTHOR_NAME": "DST",
                "GIT_AUTHOR_EMAIL": "dst@example.com",
                "GIT_COMMITTER_NAME": "DST",
                "GIT_COMMITTER_EMAIL": "dst@example.com",
            }
            subprocess.run(["git", "-C", str(target_dir), "init", "-q"], check=True, env=env)
            subprocess.run(["git", "-C", str(target_dir), "add", "."], check=True, env=env)
            subprocess.run(["git", "-C", str(target_dir), "commit", "-q", "-m", "base"], check=True, env=env)
            base_sha = subprocess.check_output(
                ["git", "-C", str(target_dir), "rev-parse", "HEAD"], text=True, env=env
            ).strip()

            # Commit an unrelated change in src/billing.py so src/auth.py finding carries forward cleanly.
            (target_dir / "src" / "billing.py").write_text("def charge(n: int) -> int:\n    return max(0, n)\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(target_dir), "add", "."], check=True, env=env)
            subprocess.run(["git", "-C", str(target_dir), "commit", "-q", "-m", "head"], check=True, env=env)
            head_sha = subprocess.check_output(
                ["git", "-C", str(target_dir), "rev-parse", "HEAD"], text=True, env=env
            ).strip()

            with mock.patch.dict(os.environ, {"AJAR_HOME": str(ajar_home)}):
                parent_conn = _bootstrap_sim_run("dst-parent", target_dir, ajar_home=ajar_home)
                child_conn = _bootstrap_sim_run("dst-child", target_dir, ajar_home=ajar_home)
                try:
                    surf = add_surface(
                        parent_conn,
                        name="Auth",
                        kind="http",
                        subsystem="src",
                        locus="src/auth.py:1",
                        priority="high",
                        trust_boundary="ext->auth",
                    )
                    clm = propose_claim(
                        parent_conn,
                        worker_id="w-p",
                        title="Auth token check bug",
                        locus="src/auth.py:1",
                        severity="high",
                        mechanism="Accepts malformed prefix",
                        surface_id=str(surf["surface_id"]),
                        falsification_prediction="Rejects prefix",
                        falsification_test="Run prefix test",
                    )
                    cid = str(clm["claim_id"])
                    survive_claim(
                        parent_conn,
                        claim_id=cid,
                        worker_id="w-f",
                        notes="Verified by inspecting auth.py",
                    )
                    record_reproduction_outcome(
                        parent_conn,
                        claim_id=cid,
                        worker_id="w-repro",
                        poc_cmd="python3 -c 'raise SystemExit(1)'",
                        control_cmd="python3 -c 'raise SystemExit(0)'",
                        build_cmd="echo build-ok",
                        repro_result={
                            "passed": True,
                            "observation_hash": "obs-sync-1",
                            "micropatch_diff": "--- a/src/auth.py\n+++ b/src/auth.py\n",
                            "arm1_clean_poc": {"arm_passed": True},
                            "arm2_clean_control": {"arm_passed": True},
                            "arm3_patch_poc": {"arm_passed": True},
                            "arm4_patch_control": {"arm_passed": True},
                        },
                    )
                    child_run_dir = ajar_home / "runs" / "dst-child"
                    sync_res = sync_pr_differential_state(
                        child_conn,
                        run_dir=child_run_dir,
                        target_dir=target_dir,
                        diff_range=f"{base_sha}..{head_sha}",
                        parent_run_id="dst-parent",
                        ajar_home=ajar_home,
                    )
                    self.assertGreaterEqual(len(sync_res["kept_findings"]), 1)
                    kept_row = child_conn.execute("SELECT build_cmd FROM findings LIMIT 1").fetchone()
                    self.assertEqual(str(kept_row["build_cmd"]), "echo build-ok")
                    _assert_global_invariants(child_conn, target_dir=target_dir, seed=903, step=1, prev_phase_rank=0)
                finally:
                    parent_conn.close()
                    child_conn.close()

    def test_concurrent_two_connection_wal_immediate_tx_contention(self) -> None:
        import concurrent.futures

        from ajar.services import add_task

        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            target_dir = _seed_target_dir(base / "target")
            ajar_home = base / "ajar_home"
            with mock.patch.dict(os.environ, {"AJAR_HOME": str(ajar_home)}):
                seed_conn = _bootstrap_sim_run("dst-wal", target_dir, ajar_home=ajar_home)
                try:
                    for i in range(16):
                        add_task(
                            seed_conn,
                            kind="investigate",
                            title=f"Concurrent task {i}",
                            locus=f"src/auth.py:{(i % 5) + 1}",
                            priority="high",
                        )
                finally:
                    seed_conn.close()

                def _worker(worker_idx: int) -> list[str]:
                    leased: list[str] = []
                    conn = open_run_db("dst-wal", ajar_home=ajar_home)
                    try:
                        for j in range(10):
                            add_anomaly(
                                conn,
                                locus=f"src/auth.py:{(j % 5) + 1}",
                                observation=f"Concurrent anomaly w{worker_idx}-{j}",
                            )
                            res = lease_next_task(conn, worker_id=f"wal-worker-{worker_idx}")
                            if res is not None:
                                leased.append(str(res["task_id"]))
                    finally:
                        conn.close()
                    return leased

                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                    f1 = pool.submit(_worker, 1)
                    f2 = pool.submit(_worker, 2)
                    leased1 = f1.result()
                    leased2 = f2.result()

                # Zero duplicate leases across concurrent connections!
                self.assertEqual(len(set(leased1) & set(leased2)), 0)
                self.assertEqual(len(leased1) + len(leased2), 16)

                verify_conn = open_run_db("dst-wal", ajar_home=ajar_home)
                try:
                    anom_count = int(verify_conn.execute("SELECT COUNT(*) AS c FROM anomalies").fetchone()["c"])
                    self.assertEqual(anom_count, 20)
                    qc = verify_conn.execute("PRAGMA quick_check").fetchone()
                    self.assertEqual(qc[0], "ok")
                finally:
                    verify_conn.close()


if __name__ == "__main__":
    unittest.main()
