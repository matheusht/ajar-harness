from __future__ import annotations

import concurrent.futures
import os
import pathlib
import shutil
import tempfile
import time
import unittest

from ajar.db import (
    AjarError,
    check_dead_end_repetition,
    compute_commitment_hash,
    lease_next_task,
    new_id,
    normalize_mechanism_key,
    open_run_db,
    record_repro_failure,
    render_task_context,
    run_dir_for,
    run_pulse,
    set_certified_binding,
    utc_now_iso,
)
from ajar.gates import check_all_gates, finding_attribution_for_claim
from ajar.repomap import compute_code_quote_usd
from ajar.workspace import init_run_workspace, unlock_run_dir_permissions


class TestDbAndGates(unittest.TestCase):
    _template_tmp: tempfile.TemporaryDirectory[str]
    _template_root: pathlib.Path
    _template_run_id: str = "run-test-001"

    @classmethod
    def setUpClass(cls) -> None:
        cls._template_tmp = tempfile.TemporaryDirectory(prefix="ajar-db-gates-tpl-")
        cls._template_root = pathlib.Path(cls._template_tmp.name)
        tpl_home = cls._template_root / "ajar_home"
        tpl_target = cls._template_root / "target"
        (tpl_target / "auth").mkdir(parents=True)
        (tpl_target / "auth" / "guard.py").write_text(
            "MAX_TOKEN_TTL = 3600\ndef check_owner(user, owner):\n    if user != owner:\n        raise PermissionError('denied')\n",
            encoding="utf-8",
        )
        init_run_workspace(
            target=str(tpl_target),
            target_mode="source",
            workspace_mode="in_place",
            goal="Verify auth subsystem invariants",
            budget_usd=20.0,
            run_id=cls._template_run_id,
            ajar_home=tpl_home,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        unlock_run_dir_permissions(run_dir_for(cls._template_run_id, cls._template_root / "ajar_home"))
        cls._template_tmp.cleanup()

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = pathlib.Path(self._tmp.name)
        self.ajar_home = self.tmp_path / "ajar_home"
        self.target_dir = self.tmp_path / "target"
        shutil.copytree(self._template_root / "target", self.target_dir)
        shutil.copytree(self._template_root / "ajar_home", self.ajar_home)
        self.run_id = self._template_run_id
        conn = open_run_db(self.run_id, ajar_home=self.ajar_home)
        try:
            conn.execute(
                "UPDATE runs SET target_path = ?, workspace_path = ? WHERE run_id = ?",
                (str(self.target_dir), str(self.target_dir), self.run_id),
            )
        finally:
            conn.close()

    def tearDown(self) -> None:
        unlock_run_dir_permissions(run_dir_for(self.run_id, self.ajar_home))
        self._tmp.cleanup()

    def test_o_nofollow_rejects_symlink_db(self) -> None:
        real_db = self.tmp_path / "real.db"
        real_db.write_bytes(b"")
        bad_run_dir = run_dir_for("run-symlink", self.ajar_home)
        bad_run_dir.mkdir(parents=True, exist_ok=True)
        os.symlink(real_db, bad_run_dir / "run.db")
        with self.assertRaises(AjarError):
            open_run_db("run-symlink", ajar_home=self.ajar_home)

    def test_20_worker_concurrent_wal_leasing_and_zero_skill_quota(self) -> None:
        conn = open_run_db(self.run_id, ajar_home=self.ajar_home)
        now = utc_now_iso()
        conn.execute("DELETE FROM tasks")
        for i in range(20):
            conn.execute(
                """
                INSERT INTO tasks(task_id, kind, title, subsystem, locus, priority, status, salience_score, created_at, updated_at)
                VALUES (?, 'investigate', ?, 'auth', 'auth/guard.py:1', 'high', 'open', ?, ?, ?)
                """,
                (f"task-{i:02d}", f"Task {i}", 50 + i, now, now),
            )
        conn.close()

        def worker_lease(idx: int) -> dict[str, object] | None:
            wconn = open_run_db(self.run_id, ajar_home=self.ajar_home)
            try:
                return lease_next_task(wconn, worker_id=f"worker-{idx:02d}")
            finally:
                wconn.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
            results = list(pool.map(worker_lease, range(20)))

        leased_ids = [r["task_id"] for r in results if r is not None]
        self.assertEqual(len(leased_ids), 20)
        self.assertEqual(len(set(leased_ids)), 20)
        zero_skill_count = sum(1 for r in results if r and r["skill_mode"] == "zero_skill")
        self.assertGreaterEqual(zero_skill_count, 1)

    def test_dead_end_guard_under_5ms_and_anomaly_override(self) -> None:
        conn = open_run_db(self.run_id, ajar_home=self.ajar_home)
        try:
            now = utc_now_iso()
            mech = "missing owner check in check_owner allows cross-tenant read"
            conn.execute(
                """
                INSERT INTO claims(
                    claim_id, proposer_worker_id, title, subsystem, locus, mechanism, mechanism_key,
                    severity, falsification_prediction, falsification_test, status, created_at, updated_at
                ) VALUES ('clm-dead', 'w1', 'Dead claim', 'auth', 'auth/guard.py:2', ?, ?, 'high', 'pred', 'pytest', 'falsified', ?, ?)
                """,
                (mech, normalize_mechanism_key(mech), now, now),
            )

            t0 = time.perf_counter()
            with self.assertRaises(AjarError):
                check_dead_end_repetition(conn, locus="auth/guard.py:2", mechanism=mech)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self.assertLess(elapsed_ms, 5.0)

            conn.execute(
                """
                INSERT INTO anomalies(anomaly_id, subsystem, locus, observation, repro_cmd, status, created_at, updated_at)
                VALUES ('anom-1', 'auth', 'auth/guard.py:2', 'admin token bypassed owner check', 'pytest -k admin', 'unexplained', ?, ?)
                """,
                (now, now),
            )
            check_dead_end_repetition(
                conn,
                locus="auth/guard.py:2",
                mechanism=mech,
                consume_anomaly_id="anom-1",
            )
        finally:
            conn.close()

    def test_orphaned_anomaly_survives_claim_falsification_and_blocks_g5(self) -> None:
        from ajar.mcp import dispatch_mcp_tool

        r1 = dispatch_mcp_tool(
            self.run_id,
            "ajar_anomaly_add",
            {"locus": "auth/guard.py:2", "observation": "HTTP 500 on null user", "repro_cmd": "pytest"},
            ajar_home=self.ajar_home,
        )
        aid = r1["anomaly_id"]

        c1 = dispatch_mcp_tool(
            self.run_id,
            "ajar_claim_propose",
            {
                "worker_id": "w-prop",
                "title": "RCE via null user",
                "locus": "auth/guard.py:2",
                "mechanism": "null user dereference executes code",
                "falsification_prediction": "raises TypeError without code execution",
                "falsification_test": "python3 -c 'import guard'",
                "consume_anomaly_id": aid,
            },
            ajar_home=self.ajar_home,
        )
        cid = c1["claim_id"]

        dispatch_mcp_tool(
            self.run_id,
            "ajar_claim_falsify",
            {"claim_id": cid, "worker_id": "w-falsify", "notes": "Only raises TypeError"},
            ajar_home=self.ajar_home,
        )

        conn = open_run_db(self.run_id, ajar_home=self.ajar_home)
        try:
            anom = conn.execute("SELECT status, consumed_by_id FROM anomalies WHERE anomaly_id = ?", (aid,)).fetchone()
            self.assertEqual(anom["status"], "unexplained")
            self.assertIsNone(anom["consumed_by_id"])

            gates = check_all_gates(conn, target_dir=self.target_dir)
            self.assertFalse(gates["gates"]["G5_anomalies_and_chains"]["passed"])
        finally:
            conn.close()

    def test_two_fail_telemetry_pivot_and_binding_unlock(self) -> None:
        conn = open_run_db(self.run_id, ajar_home=self.ajar_home)
        try:
            now = utc_now_iso()
            conn.execute(
                """
                INSERT INTO claims(
                    claim_id, proposer_worker_id, falsifier_worker_id, title, subsystem, locus,
                    mechanism, mechanism_key, severity, falsification_prediction, falsification_test,
                    status, created_at, updated_at
                ) VALUES ('clm-1', 'w1', 'w2', 'TTL bypass', 'auth', 'auth/guard.py:1-1', 'ttl overflow', 'ttl overflow', 'high', 'pred', 'test', 'survived_falsify', ?, ?)
                """,
                (now, now),
            )
            clm = conn.execute("SELECT * FROM claims WHERE claim_id = 'clm-1'").fetchone()
            r1 = record_repro_failure(conn, claim=clm, worker_id="w3", observation_hash="obs-a", reason="exit 0")
            self.assertFalse(r1["pivoted_to_instrumentation"])

            clm = conn.execute("SELECT * FROM claims WHERE claim_id = 'clm-1'").fetchone()
            r2 = record_repro_failure(conn, claim=clm, worker_id="w3", observation_hash="obs-b", reason="exit 0 again")
            self.assertTrue(r2["pivoted_to_instrumentation"])
            self.assertEqual(r2["status"], "needs_instrumentation")
            self.assertIsNotNone(r2["instrument_task_id"])

            set_certified_binding(
                conn,
                target_dir=self.target_dir,
                name="MAX_TOKEN_TTL",
                value="3600",
                locus="auth/guard.py:1-1",
            )
            unlocked = conn.execute("SELECT status, instrumented_since_fail FROM claims WHERE claim_id = 'clm-1'").fetchone()
            self.assertEqual(unlocked["status"], "survived_falsify")
            self.assertEqual(unlocked["instrumented_since_fail"], 1)

            (self.target_dir / "auth" / "guard.py").write_text(
                "MAX_TOKEN_TTL = 7200\ndef check_owner(user, owner):\n    if user != owner:\n        raise PermissionError('denied')\n",
                encoding="utf-8",
            )
            pulse_res = run_pulse(conn, target_dir=self.target_dir)
            self.assertEqual(pulse_res["invalidated_bindings"], 1)
        finally:
            conn.close()

    def test_pulse_reopens_conditional_blocked_and_context_fits_4kb(self) -> None:
        conn = open_run_db(self.run_id, ajar_home=self.ajar_home)
        try:
            now = utc_now_iso()
            conn.execute(
                """
                INSERT INTO tasks(
                    task_id, kind, title, subsystem, locus, priority, status,
                    blocker_predicate, blocker_check_locus, salience_score, created_at, updated_at
                ) VALUES ('t-blocked', 'investigate', 'Exploit token sink', 'auth', 'auth/guard.py:2', 'high', 'conditional_blocked', 'need header_leak primitive', 'auth/header.py', 50, ?, ?)
                """,
                (now, now),
            )
            conn.execute(
                """
                INSERT INTO primitives(primitive_id, subsystem, locus, kind, preconditions, postconditions, evidence_cmd, evidence_output, created_at)
                VALUES ('prim-1', 'auth', 'auth/header.py:10', 'header_leak', 'anon', 'leaks session nonce', 'pytest', 'ok', ?)
                """,
                (now,),
            )
            pulse = run_pulse(conn, target_dir=self.target_dir)
            self.assertIn("t-blocked", pulse["reopened_tasks"])

            for i in range(25):
                set_certified_binding(
                    conn,
                    target_dir=self.target_dir,
                    name=f"CONST_{i}",
                    value="x" * 120,
                    locus="auth/guard.py:1-2",
                )
            ctx = render_task_context(conn, "t-blocked")
            rendered = ctx["rendered"]
            self.assertLess(len(rendered.encode("utf-8")), 4096)
            self.assertLessEqual(len(rendered.splitlines()), 50)
        finally:
            conn.close()

    def test_bulk_dismissal_guard_attribution_and_loc_quote_math(self) -> None:
        self.assertEqual(compute_code_quote_usd(150), 10.0)
        self.assertEqual(compute_code_quote_usd(500), 20.0)
        self.assertEqual(compute_code_quote_usd(5_000), 40.0)
        self.assertEqual(compute_code_quote_usd(18_000), 90.0)

        conn = open_run_db(self.run_id, ajar_home=self.ajar_home)
        try:
            now_iso = utc_now_iso()
            now_ep = time.time()
            conn.execute(
                "INSERT INTO surfaces(surface_id, name, kind, subsystem, locus, priority, created_at) VALUES ('s1', 'guard', 'fn', 'auth', 'auth/guard.py:2', 'high', ?)",
                (now_iso,),
            )
            for i in range(5):
                conn.execute(
                    """
                    INSERT INTO tasks(
                        task_id, surface_id, worker_id, kind, title, subsystem, locus, priority, status,
                        dry_control_locus, dry_control_reason, closed_epoch, created_at, updated_at
                    ) VALUES (?, 's1', 'w-lazy', 'investigate', ?, 'auth', 'auth/guard.py:2', 'high', 'dry', 'auth/guard.py:3', 'checked owner equality guard ok', ?, ?, ?)
                    """,
                    (new_id("t"), f"Dry {i}", now_ep + i * 0.1, now_iso, now_iso),
                )
            gates = check_all_gates(conn, target_dir=self.target_dir)
            self.assertFalse(gates["gates"]["G4_zero_skill_and_dry_rigor"]["passed"])
            self.assertTrue(
                any("Bulk-dismissal" in m for m in gates["gates"]["G4_zero_skill_and_dry_rigor"]["issues"])
            )

            self.assertEqual(
                finding_attribution_for_claim(conn, {"claim_id": "c1", "seeded_by_human": 0}),
                "found_autonomously_by_ajar",
            )
            self.assertEqual(
                finding_attribution_for_claim(conn, {"claim_id": "c2", "seeded_by_human": 1}),
                "validated_by_ajar",
            )
            commit_hash = compute_commitment_hash("abc123", "goal", "exhaustive-high", "2026-11-18T00:00:00Z")
            self.assertEqual(len(commit_hash), 64)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
