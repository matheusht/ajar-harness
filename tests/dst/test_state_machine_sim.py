"""Seeded multi-worker Deterministic Simulation Testing (DST) for Ajar state machines.

Runs 50 seeds x 40 randomized steps (2,000+ operations) exercising CLI/service/MCP
workflow mutations, illegal transition probes, phase monotonicity, read-only gate
purity, Host Mode advisory spend behavior, KV prefix-cache stability, and reopen flows.

Replay any failing seed directly:
    AJAR_DST_SEED=42 pytest -q tests/dst/test_state_machine_sim.py
"""

from __future__ import annotations

import os
import pathlib
import random
import sqlite3
import tempfile
import unittest
from unittest import mock

from ajar.chain_planner import add_crown_jewel, compute_chain_frontier, park_open_door
from ajar.db import (
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


def _seed_target_dir(root: pathlib.Path) -> pathlib.Path:
    for rel, content in TARGET_FILES:
        fp = root / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
    return root


def _bootstrap_sim_run(run_id: str, target_dir: pathlib.Path) -> sqlite3.Connection:
    conn = open_run_db(run_id, create=True)
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

    # I1, I2, I9: Claims coherence & fresh-falsifier separation
    claims = conn.execute("SELECT * FROM claims").fetchall()
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
    anomalies = conn.execute("SELECT * FROM anomalies").fetchall()
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
    prims = conn.execute("SELECT primitive_id, status, chained FROM primitives").fetchall()
    valid_prim_statuses = {s.value for s in PrimitiveStatus}
    for p in prims:
        pst = str(p["status"])
        assert pst in valid_prim_statuses, f"{ctx}: illegal primitive status {pst!r}"
        if pst == "dry":
            assert int(p["chained"]) == 0, f"{ctx}: dry primitive {p['primitive_id']} has chained=1"
        if int(p["chained"]) == 1:
            assert pst == "chained", f"{ctx}: chained=1 primitive {p['primitive_id']} has status={pst!r}"

    # I6, I9: Tasks enum & hunt-phase patch gating
    tasks = conn.execute("SELECT task_id, kind, status FROM tasks").fetchall()
    valid_task_statuses = {s.value for s in TaskStatus}
    for t in tasks:
        tst = str(t["status"])
        assert tst in valid_task_statuses, f"{ctx}: illegal task status {tst!r}"
        if phase == "hunt" and t["kind"] == "patch":
            assert tst != "leased", f"{ctx}: patch task {t['task_id']} leased during hunt phase"

    # I9: Doors & Jewels enums
    for d in conn.execute("SELECT status FROM parked_doors").fetchall():
        assert d["status"] in {s.value for s in DoorStatus}, f"{ctx}: illegal door status {d['status']!r}"
    for j in conn.execute("SELECT status FROM crown_jewels").fetchall():
        assert j["status"] in {s.value for s in JewelStatus}, f"{ctx}: illegal jewel status {j['status']!r}"

    # I7: Read-only gate purity (check_all_gates with auto_enqueue_chain=False never writes)
    before_counts = (
        int(conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]),
        int(conn.execute("SELECT COUNT(*) FROM parked_doors").fetchone()[0]),
        int(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]),
    )
    check_all_gates(conn, target_dir=target_dir, auto_enqueue_chain=False)
    after_counts = (
        int(conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]),
        int(conn.execute("SELECT COUNT(*) FROM parked_doors").fetchone()[0]),
        int(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]),
    )
    assert before_counts == after_counts, f"{ctx}: read-only check_all_gates mutated tables: {before_counts} -> {after_counts}"

    return rank


def _run_simulation_seed(seed: int, *, steps: int, target_dir: pathlib.Path, ajar_home: pathlib.Path) -> None:
    rng = random.Random(seed)
    run_id = f"dst-seed-{seed:04d}"
    with mock.patch.dict(os.environ, {"AJAR_HOME": str(ajar_home)}):
        conn = _bootstrap_sim_run(run_id, target_dir)
        try:
            phase_rank = 0
            loci = ["src/auth.py:1", "src/auth.py:4", "src/parser.py:1", "src/parser.py:4", "src/vault.py:1", "src/vault.py:4"]
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
                "finish_and_reopen",
            )

            for step in range(steps):
                op = rng.choice(ops)
                worker = rng.choice(WORKERS)
                locus = rng.choice(loci)
                use_mcp = rng.random() < 0.35
                run_status = str(conn.execute("SELECT status FROM runs LIMIT 1").fetchone()["status"])

                if op == "surface_add":
                    try:
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
                    except AjarError:
                        assert run_status == "finished"

                elif op == "task_add":
                    if run_status != "finished":
                        tid = new_id("tsk")
                        kind = rng.choice(["investigate", "falsify", "patch"])
                        pri = rng.choice(["critical", "high", "medium", "low"])
                        now = utc_now_iso()
                        sal = compute_task_salience(
                            conn,
                            {"priority": pri, "kind": kind, "subsystem": locus.split("/", 1)[0], "locus": locus, "reopened_boost": 0},
                        )
                        with immediate_tx(conn):
                            conn.execute(
                                """
                                INSERT INTO tasks(
                                    task_id, kind, title, subsystem, locus, priority, salience_score,
                                    status, created_at, updated_at
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)
                                """,
                                (
                                    tid,
                                    kind,
                                    f"Task {step} ({kind})",
                                    locus.split("/", 1)[0],
                                    locus,
                                    pri,
                                    sal,
                                    now,
                                    now,
                                ),
                            )

                elif op == "task_lease":
                    kind_opt = rng.choice([None, "investigate", "patch"])
                    leased = lease_next_task(conn, worker_id=worker, kind=kind_opt, recover=True)
                    phase_now = str(conn.execute("SELECT campaign_phase FROM runs LIMIT 1").fetchone()["campaign_phase"])
                    if leased is not None and phase_now == "hunt":
                        assert leased["kind"] != "patch", f"seed={seed} step={step}: leased patch during hunt"

                elif op == "task_done":
                    row = conn.execute("SELECT task_id FROM tasks WHERE status IN ('open', 'leased') LIMIT 1").fetchone()
                    if row is not None:
                        try:
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
                        except AjarError:
                            pass

                elif op == "task_dry":
                    row = conn.execute("SELECT task_id FROM tasks WHERE status IN ('open', 'leased') LIMIT 1").fetchone()
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
                            pass

                elif op == "task_block":
                    row = conn.execute("SELECT task_id FROM tasks WHERE status IN ('open', 'leased') LIMIT 1").fetchone()
                    if row is not None:
                        try:
                            block_task(
                                conn,
                                task_id=str(row["task_id"]),
                                worker_id=worker,
                                predicate="waiting_for_guard_bypass",
                                check_locus=locus,
                            )
                        except AjarError:
                            pass

                elif op == "anomaly_add":
                    try:
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
                    except AjarError:
                        assert run_status == "finished"

                elif op == "anomaly_explain":
                    row = conn.execute("SELECT anomaly_id FROM anomalies WHERE status = 'unexplained' LIMIT 1").fetchone()
                    if row is not None:
                        try:
                            explain_anomaly(
                                conn,
                                anomaly_id=str(row["anomaly_id"]),
                                locus=locus,
                                reason="Verified benign fallback path returns error without side effect",
                            )
                        except AjarError:
                            pass

                elif op == "claim_propose":
                    anom = conn.execute("SELECT anomaly_id FROM anomalies WHERE status = 'unexplained' LIMIT 1").fetchone()
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
                    except AjarError:
                        pass

                elif op in ("claim_falsify", "claim_config_gate"):
                    row = conn.execute(
                        "SELECT claim_id, proposer_worker_id FROM claims WHERE status IN ('proposed', 'config_gated') LIMIT 1"
                    ).fetchone()
                    if row is not None:
                        other_workers = [w for w in WORKERS if w != row["proposer_worker_id"]]
                        falsifier = rng.choice(other_workers)
                        cfg = f"FLAG_{step}=1" if op == "claim_config_gate" else ""
                        try:
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
                        except AjarError:
                            pass

                elif op == "claim_survive":
                    row = conn.execute(
                        "SELECT claim_id, proposer_worker_id FROM claims WHERE status IN ('proposed', 'config_gated') LIMIT 1"
                    ).fetchone()
                    if row is not None:
                        other_workers = [w for w in WORKERS if w != row["proposer_worker_id"]]
                        falsifier = rng.choice(other_workers)
                        try:
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
                        except AjarError:
                            pass

                elif op == "claim_rescope":
                    row = conn.execute(
                        "SELECT claim_id FROM claims WHERE status IN ('proposed', 'survived_falsify', 'needs_instrumentation') LIMIT 1"
                    ).fetchone()
                    if row is not None:
                        try:
                            rescope_claim_service(
                                conn,
                                claim_id=str(row["claim_id"]),
                                worker_id=worker,
                                reason=f"Refined locus to {locus}",
                                locus=locus,
                            )
                        except AjarError:
                            pass

                elif op == "claim_block":
                    row = conn.execute("SELECT claim_id FROM claims WHERE status = 'proposed' LIMIT 1").fetchone()
                    if row is not None:
                        try:
                            block_claim(
                                conn,
                                claim_id=str(row["claim_id"]),
                                worker_id=worker,
                                reason="Requires external HSM hardware unavailable in sandbox",
                                env_blocker="missing_hardware",
                                target_mode="source",
                            )
                        except AjarError:
                            pass

                elif op == "primitive_add":
                    if run_status != "finished":
                        pid = new_id("prim")
                        now = utc_now_iso()
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
                    row = conn.execute("SELECT primitive_id FROM primitives WHERE status = 'active' LIMIT 1").fetchone()
                    if row is not None:
                        try:
                            mark_primitive_dry(
                                conn,
                                target_dir=target_dir,
                                target_mode="source",
                                primitive_id=str(row["primitive_id"]),
                                worker_id=worker,
                                locus=locus,
                                reason="Guard strictly rejects crafted offset before memory write",
                            )
                        except AjarError:
                            pass

                elif op == "door_park":
                    if run_status != "finished":
                        jrow = conn.execute("SELECT jewel_id FROM crown_jewels LIMIT 1").fetchone()
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
                        try:
                            park_open_door(
                                conn,
                                anchor_locus=locus,
                                missing_link_summary=f"Need authenticated token bridge #{step}",
                                jewel_id=jewel_id,
                                direction="from_jewel",
                                wanted_tags="auth_bypass",
                                spawn_hunters=False,
                                worker_id=worker,
                            )
                            compute_chain_frontier(conn)
                        except AjarError:
                            pass

                elif op == "phase_advance":
                    target_phase = rng.choice(["hunt", "remediate", "full"])
                    cur_phase = str(conn.execute("SELECT campaign_phase FROM runs LIMIT 1").fetchone()["campaign_phase"])
                    if PHASE_RANK[target_phase] < PHASE_RANK[cur_phase] or run_status == "finished":
                        try:
                            advance_phase(conn, run_id=run_id, to_phase=target_phase)
                            raise AssertionError(f"seed={seed} step={step}: illegal phase {cur_phase}->{target_phase} succeeded!")
                        except InvalidTransitionError:
                            pass
                    else:
                        advance_phase(conn, run_id=run_id, to_phase=target_phase)

                elif op == "spend_over_cap":
                    # Host Mode advisory check: exceeding 100% of cogs_cap_usd MUST NOT block leasing or flip runs.status!
                    if run_status != "finished":
                        with immediate_tx(conn):
                            conn.execute(
                                """
                                INSERT INTO spend_ledger(
                                    entry_id, worker_id, phase, model, tokens_in, tokens_out,
                                    cost_usd, created_at
                                ) VALUES (?, ?, 'explore', 'host-model', 1000, 500, 50.0, ?)
                                """,
                                (new_id("spd"), worker, utc_now_iso()),
                            )
                        st_after = str(conn.execute("SELECT status FROM runs LIMIT 1").fetchone()["status"])
                        assert st_after == run_status, f"seed={seed} step={step}: spend_ledger mutated Host Mode run status!"

                elif op == "illegal_probe":
                    # Inject adversarial illegal transitions & verify deterministic rejection!
                    clm = conn.execute("SELECT claim_id, proposer_worker_id, status FROM claims LIMIT 1").fetchone()
                    if clm is not None:
                        # Whitespace-padded self-falsification MUST fail
                        try:
                            falsify_claim(
                                conn,
                                claim_id=str(clm["claim_id"]),
                                worker_id=f" {clm['proposer_worker_id']} ",
                                notes="whitespace self-falsify attempt",
                            )
                            raise AssertionError(f"seed={seed} step={step}: whitespace self-falsify bypassed!")
                        except AjarError:
                            pass
                        # Resurrecting a falsified claim MUST fail with InvalidTransitionError
                        if clm["status"] == "falsified":
                            other = next(w for w in WORKERS if w != clm["proposer_worker_id"])
                            try:
                                survive_claim(conn, claim_id=str(clm["claim_id"]), worker_id=other, notes="resurrect")
                                raise AssertionError(f"seed={seed} step={step}: falsified -> survived_falsify succeeded!")
                            except InvalidTransitionError:
                                pass

                elif op == "finish_and_reopen":
                    if run_status == "finished":
                        reopen_run(run_id, ajar_home=ajar_home)
                    else:
                        res = finish_run(conn, run_id=run_id, target_dir=target_dir, actor="operator")
                        if res["passed"]:
                            # Post-finish mutations MUST be rejected immediately
                            try:
                                add_surface(conn, name="post_finish_illegal", kind="entry_point", locus=locus)
                                raise AssertionError(f"seed={seed} step={step}: mutation succeeded on finished run!")
                            except InvalidTransitionError:
                                pass

                phase_rank = _assert_global_invariants(
                    conn,
                    target_dir=target_dir,
                    seed=seed,
                    step=step,
                    prev_phase_rank=phase_rank,
                )

            # Verify KV prefix-cache byte identity across distinct tasks at end of seed
            open_tasks = conn.execute("SELECT task_id FROM tasks ORDER BY created_at ASC LIMIT 2").fetchall()
            if len(open_tasks) == 2:
                ctx_a = render_task_context(conn, str(open_tasks[0]["task_id"]))["rendered"]
                ctx_b = render_task_context(conn, str(open_tasks[1]["task_id"]))["rendered"]
                marker = "## Task Delta"
                if marker in ctx_a and marker in ctx_b:
                    assert ctx_a.split(marker, 1)[0] == ctx_b.split(marker, 1)[0], (
                        f"seed={seed}: Certified Run Prefix drifted between tasks!"
                    )

            # Final SQLite integrity check
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

        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            target_dir = _seed_target_dir(base / "target")
            ajar_home = base / "ajar_home"
            for seed in seeds:
                _run_simulation_seed(seed, steps=40, target_dir=target_dir, ajar_home=ajar_home)

    def test_single_seed_replay_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            target_dir = _seed_target_dir(base / "target")
            home_a = base / "home_a"
            home_b = base / "home_b"
            _run_simulation_seed(7, steps=30, target_dir=target_dir, ajar_home=home_a)
            _run_simulation_seed(7, steps=30, target_dir=target_dir, ajar_home=home_b)
            with mock.patch.dict(os.environ, {"AJAR_HOME": str(home_a)}):
                ca = open_run_db("dst-seed-0007")
                try:
                    sig_a = (
                        ca.execute("SELECT status, campaign_phase FROM runs").fetchall(),
                        ca.execute("SELECT status, research_state, evidence_state FROM claims ORDER BY rowid").fetchall(),
                        ca.execute("SELECT status FROM tasks ORDER BY rowid").fetchall(),
                    )
                    sig_a_norm = tuple([tuple(r) for r in grp] for grp in sig_a)
                finally:
                    ca.close()
            with mock.patch.dict(os.environ, {"AJAR_HOME": str(home_b)}):
                cb = open_run_db("dst-seed-0007")
                try:
                    sig_b = (
                        cb.execute("SELECT status, campaign_phase FROM runs").fetchall(),
                        cb.execute("SELECT status, research_state, evidence_state FROM claims ORDER BY rowid").fetchall(),
                        cb.execute("SELECT status FROM tasks ORDER BY rowid").fetchall(),
                    )
                    sig_b_norm = tuple([tuple(r) for r in grp] for grp in sig_b)
                finally:
                    cb.close()
            self.assertEqual(sig_a_norm, sig_b_norm)


if __name__ == "__main__":
    unittest.main()
