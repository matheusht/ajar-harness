"""Focused regression tests for Phase 0 hunt-killer and environment-isolation fixes."""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from ajar.db import add_steer, open_run_db, render_task_context, utc_now_iso
from ajar.gates import check_all_gates
from ajar.hooks import run_host_continuation_loop
from ajar.repro_source import capture_slot_post_state_snapshot
from ajar.swarm import _hydrate_run_from_shared_mirror, sync_run_to_shared_mirror
from ajar.workspace import init_run_workspace


class TestPhase0Regressions(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="ajar-p0-")
        self.tmp_path = pathlib.Path(self._tmp.name)
        self.ajar_home = self.tmp_path / "ajar_home"
        self.target = self.tmp_path / "target"
        self.target.mkdir()
        (self.target / "app.py").write_text("def handle(x):\n    return x\n", encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_global_steers_survive_many_scoped_steers_in_prefix(self) -> None:
        init_run_workspace(
            target=str(self.target),
            goal="prefix-test",
            run_id="run-p0-steer",
            ajar_home=self.ajar_home,
            allow_historical_target=True,
        )
        conn = open_run_db("run-p0-steer", ajar_home=self.ajar_home)
        try:
            for idx in range(6):
                add_steer(conn, rule_text=f"Scoped auth rule {idx}", scope="subsystem", target_filter="auth")
            add_steer(conn, rule_text="GLOBAL_PREFIX_ANCHOR_RULE", scope="global")
            now = utc_now_iso()
            conn.execute(
                """
                INSERT INTO tasks(task_id, kind, title, subsystem, locus, priority, status, salience_score, created_at, updated_at)
                VALUES ('task-a', 'investigate', 'Auth A', 'auth', 'app.py:1', 'high', 'open', 80, ?, ?),
                       ('task-b', 'investigate', 'Net B', 'net', 'app.py:2', 'high', 'open', 80, ?, ?)
                """,
                (now, now, now, now),
            )
            ctx_a = render_task_context(conn, "task-a")
            ctx_b = render_task_context(conn, "task-b")
            text_a = str(ctx_a["rendered"])
            text_b = str(ctx_b["rendered"])
            prefix_a = text_a.split("# Task Delta", 1)[0]
            prefix_b = text_b.split("# Task Delta", 1)[0]
            self.assertIn("GLOBAL_PREFIX_ANCHOR_RULE", prefix_a)
            self.assertEqual(prefix_a, prefix_b)
        finally:
            conn.close()

    def test_host_loop_stalls_at_exactly_three_zero_progress_rounds(self) -> None:
        init_run_workspace(
            target=str(self.target),
            goal="stall-test",
            run_id="run-p0-stall",
            ajar_home=self.ajar_home,
            allow_historical_target=True,
        )
        res = run_host_continuation_loop(
            run_id="run-p0-stall",
            host_kind="custom",
            cmd_template="true",
            max_rounds=10,
            ajar_home=self.ajar_home,
        )
        self.assertTrue(res.get("stalled"))
        self.assertEqual(res.get("rounds_run"), 3)

    def test_snapshot_path_is_relative_and_mirrored_across_vms(self) -> None:
        res = init_run_workspace(
            target=str(self.target),
            goal="snap-mirror",
            run_id="run-p0-snap",
            ajar_home=self.ajar_home,
            allow_historical_target=True,
        )
        rdir = pathlib.Path(res["run_dir"])
        slot_dir = rdir / "repro" / "slot-0"
        slot_dir.mkdir(parents=True, exist_ok=True)
        (slot_dir / "state.txt").write_text("stage1-ok\n", encoding="utf-8")

        snap = capture_slot_post_state_snapshot(
            run_dir=rdir,
            slot_dir=slot_dir,
            claim_id="clm-test1",
            rel_dir=".",
            source_cmd="true",
        )
        self.assertTrue(snap["ok"])
        self.assertFalse(pathlib.Path(snap["archive_path"]).is_absolute())
        self.assertTrue((rdir / snap["archive_path"]).is_file())

        shared_root = self.tmp_path / "shared_mirror"
        sync_run_to_shared_mirror("run-p0-snap", ajar_home=self.ajar_home, shared_root=shared_root)
        self.assertTrue((shared_root / "run-p0-snap" / snap["archive_path"]).is_file())

        fresh_local = self.tmp_path / "fresh_vm_home" / "runs" / "run-p0-snap"
        hydrated = _hydrate_run_from_shared_mirror("run-p0-snap", local_rdir=fresh_local, shared_root=shared_root)
        self.assertTrue(hydrated)
        self.assertTrue((fresh_local / snap["archive_path"]).is_file())

    def test_g3_accepts_kept_finding_with_arm_passed(self) -> None:
        init_run_workspace(
            target=str(self.target),
            goal="g3-test",
            run_id="run-p0-g3",
            ajar_home=self.ajar_home,
            allow_historical_target=True,
        )
        conn = open_run_db("run-p0-g3", ajar_home=self.ajar_home)
        try:
            now = utc_now_iso()
            conn.execute(
                """
                INSERT INTO claims(
                    claim_id, proposer_worker_id, title, subsystem, locus, mechanism, mechanism_key,
                    severity, falsification_prediction, falsification_test, status, falsifier_worker_id,
                    research_state, evidence_state, created_at, updated_at
                ) VALUES ('clm-1', 'w1', 'Bug', 'app', 'app.py:1', 'mech', 'app:mech', 'high', 'pred', 'test', 'reproduced', 'w2', 'confirmed', 'reproduced', ?, ?)
                """,
                (now, now),
            )
            arm_ok = json.dumps({"exit_code": 0, "arm_passed": True})
            conn.execute(
                """
                INSERT INTO findings(
                    finding_id, claim_id, title, severity, locus, root_cause, poc_cmd, control_cmd,
                    arm1_clean_poc_json, arm2_clean_ctrl_json, arm3_patch_poc_json, arm4_patch_ctrl_json,
                    attribution, created_at
                ) VALUES ('fnd-1', 'clm-1', 'Bug', 'high', 'app.py:1', 'mech', 'false', 'true', ?, ?, ?, ?, 'found_autonomously_by_ajar', ?)
                """,
                (arm_ok, arm_ok, arm_ok, arm_ok, now),
            )
            g = check_all_gates(conn, target_dir=self.target, auto_enqueue_chain=False)
            self.assertTrue(g["gates"]["G3_causal_reproduction"]["passed"], g["gates"]["G3_causal_reproduction"])
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
