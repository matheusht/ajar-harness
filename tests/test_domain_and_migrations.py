"""Phase 1 tests: typed state machines, enum-vs-SQL parity, PRAGMA user_version fast-path, and transition guards."""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import re
import sqlite3
import tempfile
import unittest

from ajar.cli import main as cli_main
from ajar.db import SCHEMA_SQL, open_run_db, utc_now_iso
from ajar.domain import (
    AjarError,
    AnomalyStatus,
    AssumptionStatus,
    CampaignPhase,
    ClaimStatus,
    CustomerState,
    DispatchStatus,
    DoorDirection,
    DoorStatus,
    EvidenceState,
    HookStatus,
    ImpactClass,
    InvalidTransitionError,
    JewelStatus,
    LeadTargetKind,
    PricingMode,
    PrimitiveRole,
    PrimitiveStatus,
    Priority,
    RealismTier,
    RemediationState,
    ResearchState,
    RunStatus,
    SkillMode,
    SpendPhase,
    SteerScope,
    StoppingCriterion,
    SwarmStage,
    TargetMode,
    TaskDirection,
    TaskKind,
    TaskStatus,
    TouchKind,
    WireProfile,
    WorkspaceMode,
    derive_claim_axes,
)
from ajar.gates import check_all_gates
from ajar.mcp import dispatch_mcp_tool
from ajar.store import CURRENT_SCHEMA_VERSION, immediate_tx
from ajar.workspace import init_run_workspace


def _run_inproc(argv: list[str], ajar_home: pathlib.Path, run_id: str) -> tuple[int, str, str]:
    old_h, old_r = os.environ.get("AJAR_HOME"), os.environ.get("AJAR_RUN_ID")
    os.environ["AJAR_HOME"] = str(ajar_home)
    os.environ["AJAR_RUN_ID"] = run_id
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli_main(argv)
        return int(rc or 0), out.getvalue(), err.getvalue()
    except SystemExit as exc:
        return int(exc.code or 0), out.getvalue(), err.getvalue()
    finally:
        if old_h is None:
            os.environ.pop("AJAR_HOME", None)
        else:
            os.environ["AJAR_HOME"] = old_h
        if old_r is None:
            os.environ.pop("AJAR_RUN_ID", None)
        else:
            os.environ["AJAR_RUN_ID"] = old_r


class TestDomainAndMigrations(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="ajar-p1-")
        self.tmp_path = pathlib.Path(self._tmp.name)
        self.ajar_home = self.tmp_path / "ajar_home"
        self.target = self.tmp_path / "target"
        self.target.mkdir()
        (self.target / "app.py").write_text(
            "def handle(x):\n    if x > 0:\n        return x\n    return 0\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_all_domain_enums_match_schema_sql_check_constraints(self) -> None:
        checks = re.findall(r"CHECK\(([a-z_]+)\s+IN\s*\(([^)]+)\)\)", SCHEMA_SQL, flags=re.IGNORECASE | re.DOTALL)
        expected_enums = [
            ("target_mode", TargetMode),
            ("workspace_mode", WorkspaceMode),
            ("stopping_criterion", StoppingCriterion),
            ("campaign_phase", CampaignPhase),
            ("pricing_mode", PricingMode),
            ("priority", Priority),
            ("kind", TaskKind),
            ("direction", TaskDirection),
            ("skill_mode", SkillMode),
            ("research_state", ResearchState),
            ("evidence_state", EvidenceState),
            ("customer_state", CustomerState),
            ("remediation_state", RemediationState),
            ("role", PrimitiveRole),
            ("impact_class", ImpactClass),
            ("realism_tier", RealismTier),
            ("phase", SpendPhase),
            ("scope", SteerScope),
            ("kind", TouchKind),
            ("stage", SwarmStage),
            ("wire_profile", WireProfile),
            ("target_kind", LeadTargetKind),
        ]
        # Verify every distinct SQL CHECK set matches its corresponding domain enum
        by_col: dict[str, list[set[str]]] = {}
        for col, raw_vals in checks:
            vals = set(re.findall(r"'([^']+)'", raw_vals))
            by_col.setdefault(col, []).append(vals)

        for col, enum_cls in expected_enums:
            enum_vals = {e.value for e in enum_cls}
            self.assertIn(col, by_col, f"Missing SQL CHECK for {col}")
            self.assertIn(enum_vals, by_col[col], f"Enum {enum_cls.__name__} disagrees with SCHEMA_SQL {col}: {by_col[col]}")

        status_enums = [
            RunStatus,
            TaskStatus,
            ClaimStatus,
            PrimitiveStatus,
            AnomalyStatus,
            DoorStatus,
            JewelStatus,
            HookStatus,
            AssumptionStatus,
            DispatchStatus,
        ]
        for enum_cls in status_enums:
            enum_vals = {e.value for e in enum_cls}
            self.assertIn(enum_vals, by_col["status"], f"Status enum {enum_cls.__name__} missing from SCHEMA_SQL")
        self.assertIn({e.value for e in DoorDirection}, by_col["direction"])

        from ajar.domain import AjarError, HookCode
        from ajar.epistemic_hooks import HOOK_CODES

        self.assertTrue(issubclass(InvalidTransitionError, AjarError))
        self.assertEqual(tuple(h.value for h in HookCode), HOOK_CODES)

    def test_warm_open_run_db_uses_pragma_user_version_fast_path(self) -> None:
        res = init_run_workspace(
            target=str(self.target),
            goal="fast-open",
            run_id="run-p1-fast",
            ajar_home=self.ajar_home,
            allow_historical_target=True,
        )
        db_path = pathlib.Path(res["run_dir"]) / "run.db"

        stmts: list[str] = []
        orig_connect = sqlite3.connect

        def traced_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
            c = orig_connect(*args, **kwargs)  # type: ignore[arg-type]
            c.set_trace_callback(stmts.append)
            return c

        sqlite3.connect = traced_connect  # type: ignore[assignment]
        try:
            conn = open_run_db(db_path)
            ver = int(conn.execute("PRAGMA user_version;").fetchone()[0])
            conn.close()
        finally:
            sqlite3.connect = orig_connect  # type: ignore[assignment]

        self.assertEqual(ver, CURRENT_SCHEMA_VERSION)
        self.assertLessEqual(len(stmts), 5, f"Expected <= 5 SQL stmts on warm open, got {len(stmts)}: {stmts}")

    def test_migrated_v30_database_has_full_v33_column_parity(self) -> None:
        fresh_db = self.tmp_path / "fresh.db"
        c_fresh = open_run_db(fresh_db, create=True)
        try:
            fresh_tables = {
                r[0]
                for r in c_fresh.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '%_fts%'").fetchall()
            }
            fresh_cols = {
                t: {r[1] for r in c_fresh.execute(f"PRAGMA table_info({t})").fetchall()}
                for t in fresh_tables
            }
        finally:
            c_fresh.close()

        # Construct a minimal v3.0 database (user_version = 0) and open it via open_run_db(create=False)
        old_db = self.tmp_path / "v30.db"
        raw = sqlite3.connect(str(old_db), isolation_level=None)
        raw.executescript(
            """
            CREATE TABLE runs (run_id TEXT PRIMARY KEY, target_path TEXT NOT NULL, workspace_path TEXT NOT NULL,
                target_mode TEXT NOT NULL, workspace_mode TEXT NOT NULL, goal TEXT NOT NULL,
                stopping_criterion TEXT NOT NULL DEFAULT 'exhaustive-high', budget_usd REAL NOT NULL DEFAULT 14.0,
                in_scope_loc INTEGER NOT NULL DEFAULT 0, code_quote_usd REAL NOT NULL DEFAULT 10.0,
                commitment_hash TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active', stop_reason TEXT DEFAULT '',
                closed_task_counter INTEGER NOT NULL DEFAULT 0, zero_skill_leases INTEGER NOT NULL DEFAULT 0,
                domain_skill_leases INTEGER NOT NULL DEFAULT 0, consecutive_stall_checks INTEGER NOT NULL DEFAULT 0,
                last_stop_event_id INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, finished_at TEXT);
            CREATE TABLE surfaces (surface_id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL,
                subsystem TEXT NOT NULL, locus TEXT NOT NULL, priority TEXT NOT NULL DEFAULT 'high',
                trust_boundary TEXT NOT NULL DEFAULT '', invariants_json TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL);
            CREATE TABLE tasks (task_id TEXT PRIMARY KEY, parent_task_id TEXT, surface_id TEXT, kind TEXT NOT NULL,
                title TEXT NOT NULL, subsystem TEXT NOT NULL DEFAULT '', locus TEXT NOT NULL DEFAULT '',
                priority TEXT NOT NULL DEFAULT 'high', status TEXT NOT NULL DEFAULT 'open', worker_id TEXT,
                skill_mode TEXT NOT NULL DEFAULT 'domain', lease_expires_at REAL, dry_control_locus TEXT,
                dry_control_reason TEXT, blocker_predicate TEXT, blocker_check_locus TEXT,
                salience_score INTEGER NOT NULL DEFAULT 60, reopened_boost INTEGER NOT NULL DEFAULT 0,
                attempt_count INTEGER NOT NULL DEFAULT 0, summary TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, closed_epoch REAL);
            CREATE TABLE primitives (primitive_id TEXT PRIMARY KEY, subsystem TEXT NOT NULL DEFAULT '',
                locus TEXT NOT NULL, kind TEXT NOT NULL, preconditions TEXT NOT NULL, postconditions TEXT NOT NULL,
                evidence_cmd TEXT NOT NULL, evidence_output TEXT NOT NULL DEFAULT '', chained INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL);
            CREATE TABLE claims (claim_id TEXT PRIMARY KEY, surface_id TEXT, proposer_worker_id TEXT NOT NULL,
                seeded_by_human INTEGER NOT NULL DEFAULT 0, title TEXT NOT NULL, subsystem TEXT NOT NULL DEFAULT '',
                locus TEXT NOT NULL, mechanism TEXT NOT NULL, mechanism_key TEXT NOT NULL,
                severity TEXT NOT NULL DEFAULT 'high', falsification_prediction TEXT NOT NULL,
                falsification_test TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'proposed', falsifier_worker_id TEXT,
                falsify_notes TEXT NOT NULL DEFAULT '', falsify_control_locus TEXT,
                failed_repro_count INTEGER NOT NULL DEFAULT 0, last_observation_hash TEXT NOT NULL DEFAULT '',
                instrumented_since_fail INTEGER NOT NULL DEFAULT 0, research_state TEXT NOT NULL DEFAULT 'candidate',
                evidence_state TEXT NOT NULL DEFAULT 'unverified', customer_state TEXT NOT NULL DEFAULT 'pending',
                remediation_state TEXT NOT NULL DEFAULT 'unpatched', duplicate_of_claim_id TEXT,
                blocker_reason TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE findings (finding_id TEXT PRIMARY KEY, claim_id TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
                severity TEXT NOT NULL, locus TEXT NOT NULL, root_cause TEXT NOT NULL, poc_cmd TEXT NOT NULL,
                control_cmd TEXT NOT NULL, micropatch_path TEXT NOT NULL DEFAULT '', micropatch_diff TEXT NOT NULL DEFAULT '',
                arm1_clean_poc_json TEXT NOT NULL, arm2_clean_ctrl_json TEXT NOT NULL,
                arm3_patch_poc_json TEXT NOT NULL, arm4_patch_ctrl_json TEXT NOT NULL,
                attribution TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE chains (chain_id TEXT PRIMARY KEY, title TEXT NOT NULL, severity TEXT NOT NULL DEFAULT 'critical',
                step_ids_json TEXT NOT NULL, e2e_poc_cmd TEXT NOT NULL, control_cmd TEXT NOT NULL,
                verified INTEGER NOT NULL DEFAULT 0, evidence_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL);
            CREATE TABLE spend_ledger (entry_id TEXT PRIMARY KEY, worker_id TEXT NOT NULL, phase TEXT NOT NULL DEFAULT 'explore',
                model TEXT NOT NULL DEFAULT '', tokens_in INTEGER NOT NULL DEFAULT 0, tokens_out INTEGER NOT NULL DEFAULT 0,
                cost_usd REAL NOT NULL DEFAULT 0.0, notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
            CREATE TABLE oracle_docs (doc_id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL,
                locus TEXT NOT NULL, body TEXT NOT NULL);
            """
        )
        raw.close()

        c_mig = open_run_db(old_db, create=False)
        try:
            ver = int(c_mig.execute("PRAGMA user_version;").fetchone()[0])
            self.assertEqual(ver, CURRENT_SCHEMA_VERSION)
            for tbl in ("runs", "surfaces", "tasks", "primitives", "claims", "findings", "chains", "spend_ledger", "oracle_docs"):
                mig_cols = {r[1] for r in c_mig.execute(f"PRAGMA table_info({tbl})").fetchall()}
                missing = fresh_cols[tbl] - mig_cols
                self.assertEqual(missing, set(), f"Migrated table {tbl} missing columns: {missing}")
        finally:
            c_mig.close()

    def test_all_illegal_state_transitions_are_mechanically_blocked(self) -> None:
        run_id = "run-p1-sm"
        res = init_run_workspace(
            target=str(self.target),
            goal="sm-guards",
            run_id=run_id,
            ajar_home=self.ajar_home,
            allow_historical_target=True,
        )
        db_path = pathlib.Path(res["run_dir"]) / "run.db"

        # Probe 1: falsified -> survive must be blocked (no split-brain claim state!)
        rc1, out1, _ = _run_inproc(
            [
                "claim", "propose", "--worker", "w1", "--title", "Bug 1", "--locus", "app.py:2",
                "--mechanism", "Attacker sends x=-1 bypassing app.py:2 and reaching sink app.py:3",
                "--falsification-prediction", "Guard blocks negative", "--falsification-test", "handle(-1)",
            ],
            self.ajar_home,
            run_id,
        )
        self.assertEqual(rc1, 0)
        cid1 = json.loads(out1)["claim_id"]

        # Probe 4 (CLI & MCP): self-falsify by proposer w1 must be rejected!
        rc_sf, _, _ = _run_inproc(
            ["claim", "falsify", cid1, "--worker", "w1", "--notes", "Self falsify", "--control-locus", "app.py:2"],
            self.ajar_home,
            run_id,
        )
        self.assertNotEqual(rc_sf, 0)
        with self.assertRaises(AjarError):
            dispatch_mcp_tool(
                run_id,
                "ajar_claim_falsify",
                {"claim_id": cid1, "worker": "w1", "notes": "Self falsify"},
                ajar_home=self.ajar_home,
            )

        # Independent falsify by w2 succeeds, then resurrect via survive MUST fail!
        rc_f, _, _ = _run_inproc(
            ["claim", "falsify", cid1, "--worker", "w2", "--notes", "Refuted by guard", "--control-locus", "app.py:2"],
            self.ajar_home,
            run_id,
        )
        self.assertEqual(rc_f, 0)
        rc_resurrect, _, _ = _run_inproc(
            ["claim", "survive", cid1, "--worker", "w2", "--notes", "Trying to resurrect"],
            self.ajar_home,
            run_id,
        )
        self.assertNotEqual(rc_resurrect, 0)
        with self.assertRaises(InvalidTransitionError):
            dispatch_mcp_tool(
                run_id,
                "ajar_claim_survive",
                {"claim_id": cid1, "worker_id": "w2", "notes": "Trying MCP resurrect"},
                ajar_home=self.ajar_home,
            )

        # Probe 2: blocked -> survive must be blocked (no stale env_blocker left behind!)
        rc2, out2, _ = _run_inproc(
            [
                "claim", "propose", "--worker", "w1", "--title", "Bug 2", "--locus", "app.py:2",
                "--mechanism", "Attacker sends x=-2 bypassing app.py:2 and reaching sink app.py:3",
                "--falsification-prediction", "Guard blocks negative", "--falsification-test", "handle(-2)",
            ],
            self.ajar_home,
            run_id,
        )
        self.assertEqual(rc2, 0)
        cid2 = json.loads(out2)["claim_id"]
        rc_blk, _, _ = _run_inproc(
            ["claim", "block", cid2, "--worker", "w2", "--reason", "Missing target hardware", "--env-blocker", "missing_hardware"],
            self.ajar_home,
            run_id,
        )
        self.assertEqual(rc_blk, 0)
        rc_b2s, _, _ = _run_inproc(
            ["claim", "survive", cid2, "--worker", "w2", "--notes", "Trying blocked->survive"],
            self.ajar_home,
            run_id,
        )
        self.assertNotEqual(rc_b2s, 0)

        # Probe 5: campaign_phase hunt -> remediate succeeds, remediate -> hunt MUST fail!
        rc_p1, _, _ = _run_inproc(["phase", "advance", "--to", "remediate"], self.ajar_home, run_id)
        self.assertEqual(rc_p1, 0)
        rc_p2, _, _ = _run_inproc(["phase", "advance", "--to", "hunt"], self.ajar_home, run_id)
        self.assertNotEqual(rc_p2, 0)

        # Probe 6: task done -> dry MUST fail!
        _, tout, _ = _run_inproc(
            ["task", "add", "--kind", "investigate", "--title", "T1", "--locus", "app.py:1"],
            self.ajar_home,
            run_id,
        )
        tid = json.loads(tout)["task_id"]
        rc_d1, _, _ = _run_inproc(["task", "done", tid, "--worker", "w1", "--summary", "done"], self.ajar_home, run_id)
        self.assertEqual(rc_d1, 0)
        rc_d2, _, _ = _run_inproc(
            ["task", "dry", tid, "--worker", "w1", "--locus", "app.py:2", "--control", "Trying overwrite done->dry"],
            self.ajar_home,
            run_id,
        )
        self.assertNotEqual(rc_d2, 0)

        # Probe 7: read-only check_all_gates(auto_enqueue_chain=False) MUST NOT mutate parked_doors!
        _, dout, _ = _run_inproc(
            [
                "door", "park", "--anchor-locus", "app.py:3", "--blocker-locus", "app.py:1",
                "--missing", "Need bypass for app.py:1", "--wanted-tags", "impossible_tag",
                "--subsystem", "auth", "--worker", "w1",
            ],
            self.ajar_home,
            run_id,
        )
        did = json.loads(dout)["door_id"]
        conn = open_run_db(db_path)
        try:
            conn.execute(
                "UPDATE tasks SET status = 'dry', dry_control_locus = 'app.py:1', dry_control_reason = 'Blocked strictly by guard' WHERE door_id = ?",
                (did,),
            )
            before = conn.execute("SELECT status FROM parked_doors WHERE door_id = ?", (did,)).fetchone()["status"]
            check_all_gates(conn, auto_enqueue_chain=False)
            after = conn.execute("SELECT status FROM parked_doors WHERE door_id = ?", (did,)).fetchone()["status"]
            self.assertEqual(before, after)

            # Probe 9: finished run rejects claim propose!
            conn.execute("UPDATE runs SET status = 'finished' WHERE run_id = ?", (run_id,))
        finally:
            conn.close()

        rc_zombie, _, _ = _run_inproc(
            [
                "claim", "propose", "--worker", "w1", "--title", "Zombie", "--locus", "app.py:2",
                "--mechanism", "Attacker sends x=-99 after run finished",
                "--falsification-prediction", "Guard blocks negative", "--falsification-test", "handle(-99)",
            ],
            self.ajar_home,
            run_id,
        )
        self.assertNotEqual(rc_zombie, 0)

    def test_derive_claim_axes_and_nested_immediate_tx(self) -> None:
        self.assertEqual(derive_claim_axes(ClaimStatus.REPRODUCED).research_state, ResearchState.CONFIRMED)
        self.assertEqual(derive_claim_axes(ClaimStatus.FALSIFIED).evidence_state, EvidenceState.FALSIFIED)
        self.assertEqual(derive_claim_axes(ClaimStatus.PROPOSED).research_state, ResearchState.CANDIDATE)

        db_p = self.tmp_path / "tx.db"
        conn = open_run_db(db_p, create=True)
        try:
            now = utc_now_iso()
            with immediate_tx(conn):
                conn.execute(
                    "INSERT INTO surfaces(surface_id, name, kind, subsystem, locus, priority, created_at) VALUES ('s1', 'a', 'http', 'auth', 'app.py:1', 'high', ?)",
                    (now,),
                )
                with self.assertRaises(RuntimeError):
                    with immediate_tx(conn):
                        conn.execute(
                            "INSERT INTO surfaces(surface_id, name, kind, subsystem, locus, priority, created_at) VALUES ('s2', 'b', 'http', 'auth', 'app.py:2', 'high', ?)",
                            (now,),
                        )
                        raise RuntimeError("inner savepoint rollback")
            ids = [r[0] for r in conn.execute("SELECT surface_id FROM surfaces ORDER BY surface_id").fetchall()]
            self.assertEqual(ids, ["s1"])
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
