"""Regression tests for fail-closed Arm-3 proof, micropatch-vs-PoC strike separation, and FK-safe migrations."""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import sqlite3
import subprocess
import tempfile
import unittest
from typing import Any
from unittest import mock

from ajar.cli import main as cli_main
from ajar.db import open_run_db
from ajar.repro_source import init_source_mirror, run_source_reproduction


def _run_cli(argv: list[str], ajar_home: pathlib.Path, run_id: str) -> tuple[int, dict[str, Any]]:
    out = io.StringIO()
    err = io.StringIO()
    with (
        mock.patch.dict(os.environ, {"AJAR_HOME": str(ajar_home), "AJAR_RUN_ID": run_id}),
        contextlib.redirect_stdout(out),
        contextlib.redirect_stderr(err),
    ):
        try:
            rc = int(cli_main(argv) or 0)
        except SystemExit as exc:
            rc = int(exc.code or 0)
    raw = out.getvalue().strip()
    payload: dict[str, Any] = json.loads(raw) if raw.startswith("{") else {"raw": raw}
    if err.getvalue().strip():
        payload["_stderr"] = err.getvalue().strip()
    return rc, payload


class TestArm3FailClosedAndPatchStrikes(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="ajar-arm3-")
        self.tmp_path = pathlib.Path(self._tmp.name)
        self.ajar_home = self.tmp_path / "ajar_home"
        self.repo = self.tmp_path / "target_repo"
        self.repo.mkdir()
        (self.repo / "gate.py").write_text(
            "def allow(x: int) -> bool:\n"
            "    if x == -1:\n"
            "        return True\n"
            "    return x > 0\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.email", "dev@example.com"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.name", "Dev"], cwd=self.repo, check=True)
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=self.repo, check=True)

        self.good_patch = self.tmp_path / "good.diff"
        self.good_patch.write_text(
            "--- a/gate.py\n"
            "+++ b/gate.py\n"
            "@@ -1,4 +1,2 @@\n"
            " def allow(x: int) -> bool:\n"
            "-    if x == -1:\n"
            "-        return True\n"
            "     return x > 0\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_eight_arm3_mutants_all_fail_closed_while_clean_pass_succeeds(self) -> None:
        rdir = self.tmp_path / "run-mutants"
        rdir.mkdir()
        init_source_mirror(rdir, self.repo)

        arm1_ok = {"exit_code": 1, "timed_out": False, "stdout": "VULN", "stderr": "", "trials": 4, "defect_hits": 4, "clean_passes": 0, "total_duration_ms": 1.0}
        arm2_ok = {"exit_code": 0, "timed_out": False, "stdout": "OK", "stderr": "", "trials": 4, "defect_hits": 0, "clean_passes": 4, "total_duration_ms": 1.0}
        arm4_ok = {"exit_code": 0, "timed_out": False, "stdout": "OK", "stderr": "", "trials": 4, "defect_hits": 0, "clean_passes": 4, "total_duration_ms": 1.0}

        bad_arm3_cases: list[tuple[str, dict[str, Any], str]] = [
            (
                "exit_70_harness_failure",
                {"exit_code": 70, "timed_out": False, "stdout": "", "stderr": "HARNESS_FAILURE: missing fixture\n", "trials": 4, "defect_hits": 0, "clean_passes": 0, "total_duration_ms": 1.0},
                "build_or_env_error",
            ),
            (
                "negative_sigkill",
                {"exit_code": -9, "timed_out": False, "stdout": "", "stderr": "", "trials": 4, "defect_hits": 0, "clean_passes": 0, "total_duration_ms": 1.0},
                "target_negative",
            ),
            (
                "exit_137_oom_kill",
                {"exit_code": 137, "timed_out": False, "stdout": "", "stderr": "Killed\n", "trials": 4, "defect_hits": 0, "clean_passes": 0, "total_duration_ms": 1.0},
                "target_negative",
            ),
            (
                "arbitrary_nonzero_23",
                {"exit_code": 23, "timed_out": False, "stdout": "", "stderr": "runner error\n", "trials": 4, "defect_hits": 0, "clean_passes": 0, "total_duration_ms": 1.0},
                "micropatch_error",
            ),
            (
                "timeout_zero_hits",
                {"exit_code": -9, "timed_out": True, "stdout": "", "stderr": "", "trials": 4, "defect_hits": 0, "clean_passes": 0, "total_duration_ms": 100.0},
                "target_negative",
            ),
            (
                "defect_still_hits",
                {"exit_code": 1, "timed_out": False, "stdout": "VULN", "stderr": "", "trials": 4, "defect_hits": 2, "clean_passes": 2, "total_duration_ms": 1.0},
                "micropatch_error",
            ),
            (
                "partial_clean_passes_3_of_4",
                {"exit_code": 2, "timed_out": False, "stdout": "", "stderr": "", "trials": 4, "defect_hits": 0, "clean_passes": 3, "total_duration_ms": 1.0},
                "micropatch_error",
            ),
            (
                "malformed_zero_clean_passes",
                {"exit_code": 0, "timed_out": False, "stdout": "", "stderr": "", "trials": 4, "defect_hits": 0, "clean_passes": 0, "total_duration_ms": 1.0},
                "micropatch_error",
            ),
        ]

        for label, bad_arm3, expected_cls in bad_arm3_cases:
            with self.subTest(case=label):
                with mock.patch("ajar.repro_source._run_trials", side_effect=[dict(arm1_ok), dict(arm2_ok), dict(bad_arm3)]):
                    res = run_source_reproduction(
                        run_dir=rdir,
                        target_dir=self.repo,
                        claim_id=f"clm-{label}",
                        poc_cmd="python3 -c 'import gate; raise SystemExit(1 if gate.allow(-1) else 0)'",
                        control_cmd="python3 -c 'import gate; assert gate.allow(5)'",
                        micropatch_path=self.good_patch,
                        determinism="probabilistic_race",
                        trials=4,
                        claim_locus="gate.py:1-4",
                    )
                self.assertFalse(res["passed"], f"Case {label} must fail closed: {res}")
                self.assertTrue(res.get("poc_proven"), f"Case {label} should preserve poc_proven=True")
                self.assertEqual(res["error_class"], expected_cls)

        # Warm cross-kill must NOT cross-kill a sibling if the sibling run crashed instead of passing cleanly.
        arm3_ok = {"exit_code": 0, "timed_out": False, "stdout": "", "stderr": "", "trials": 1, "defect_hits": 0, "clean_passes": 1, "total_duration_ms": 1.0}
        sib_crash = {"exit_code": 70, "timed_out": False, "stdout": "", "stderr": "HARNESS_FAILURE: crash", "trials": 1, "defect_hits": 0, "clean_passes": 0, "total_duration_ms": 1.0}
        with mock.patch(
            "ajar.repro_source._run_trials",
            side_effect=[
                {**arm1_ok, "trials": 1, "defect_hits": 1},
                {**arm2_ok, "trials": 1, "clean_passes": 1},
                dict(arm3_ok),
                {**arm4_ok, "trials": 1, "clean_passes": 1},
                dict(sib_crash),
            ],
        ):
            res_valid = run_source_reproduction(
                run_dir=rdir,
                target_dir=self.repo,
                claim_id="clm-valid",
                poc_cmd="python3 -c 'import gate; raise SystemExit(1 if gate.allow(-1) else 0)'",
                control_cmd="python3 -c 'import gate; assert gate.allow(5)'",
                micropatch_path=self.good_patch,
                warm_cross_kill_claims=[{"claim_id": "clm-sib", "poc_cmd": "python3 -c 'raise SystemExit(70)'"}],
                claim_locus="gate.py:1-4",
            )
        self.assertTrue(res_valid["passed"], res_valid)
        self.assertEqual(res_valid["cross_killed_claim_ids"], [])

    def test_micropatch_failures_do_not_burn_poc_strikes_and_snapshot_fails_closed(self) -> None:
        rc_init, init_out = _run_cli(
            ["init", "--in-place", "--allow-historical-target", "--run-id", "run-p0-strikes", "--json", str(self.repo)],
            self.ajar_home,
            "run-p0-strikes",
        )
        self.assertEqual(rc_init, 0, init_out)
        _, surf = _run_cli(
            ["surface", "add", "--name", "allow_gate", "--kind", "auth_boundary", "--locus", "gate.py:1"],
            self.ajar_home,
            "run-p0-strikes",
        )
        _, clm = _run_cli(
            [
                "claim",
                "propose",
                "--worker",
                "w-prop",
                "--surface",
                str(surf["surface_id"]),
                "--title",
                "gate.py allow() accepts sentinel -1 bypassing positive check",
                "--locus",
                "gate.py:1-4",
                "--mechanism",
                "allow(x) returns True when x == -1 before checking x > 0",
                "--falsification-prediction",
                "Passing x == -1 returns False",
                "--falsification-test",
                "Call allow(-1)",
            ],
            self.ajar_home,
            "run-p0-strikes",
        )
        cid = str(clm["claim_id"])
        rc_s, _ = _run_cli(["claim", "survive", cid, "--worker", "w-fal", "--notes", "confirmed"], self.ajar_home, "run-p0-strikes")
        self.assertEqual(rc_s, 0)

        noop_patch = self.tmp_path / "noop.diff"
        noop_patch.write_text(
            "--- a/gate.py\n"
            "+++ b/gate.py\n"
            "@@ -1,4 +1,4 @@\n"
            " def allow(x: int) -> bool:\n"
            "-    if x == -1:\n"
            "+    if x == -1 or False:\n"
            "         return True\n"
            "     return x > 0\n",
            encoding="utf-8",
        )
        destr_patch = self.tmp_path / "destr.diff"
        destr_patch.write_text(
            "--- a/gate.py\n"
            "+++ b/gate.py\n"
            "@@ -1,4 +1,2 @@\n"
            " def allow(x: int) -> bool:\n"
            "-    if x == -1:\n"
            "-        return True\n"
            "-    return x > 0\n"
            "+    return False\n",
            encoding="utf-8",
        )

        # Missing --save-post-state path must fail closed as preflight_error with 0 strikes.
        rc_snap, snap_out = _run_cli(
            [
                "claim",
                "reproduce",
                cid,
                "--worker",
                "w-rep",
                "--poc-cmd",
                "python3 -c 'import gate; raise SystemExit(1 if gate.allow(-1) else 0)'",
                "--control-cmd",
                "python3 -c 'import gate; assert gate.allow(5)'",
                "--micropatch",
                str(self.good_patch),
                "--save-post-state",
                "nonexistent_dir_after_arm1",
            ],
            self.ajar_home,
            "run-p0-strikes",
        )
        self.assertNotEqual(rc_snap, 0)
        self.assertEqual(snap_out["reproduction"]["error_class"], "preflight_error")
        self.assertEqual(snap_out["claim_update"]["failed_repro_count"], 0)

        # Bad Arm-3 micropatch and destructive Arm-4 micropatch must NOT increment failed_repro_count or pivot to needs_instrumentation!
        for idx, bad_diff in enumerate((noop_patch, destr_patch, noop_patch), start=1):
            rc_bad, bad_out = _run_cli(
                [
                    "claim",
                    "reproduce",
                    cid,
                    "--worker",
                    "w-rep",
                    "--poc-cmd",
                    "python3 -c 'import gate; raise SystemExit(1 if gate.allow(-1) else 0)'",
                    "--control-cmd",
                    "python3 -c 'import gate; assert gate.allow(5)'",
                    "--micropatch",
                    str(bad_diff),
                ],
                self.ajar_home,
                "run-p0-strikes",
            )
            self.assertNotEqual(rc_bad, 0, f"Attempt {idx} should reject bad micropatch")
            self.assertEqual(bad_out["reproduction"]["error_class"], "micropatch_error")
            self.assertTrue(bad_out["claim_update"]["poc_proven"])
            self.assertFalse(bad_out["claim_update"]["strike_recorded"])
            self.assertEqual(bad_out["claim_update"]["failed_repro_count"], 0)
            self.assertEqual(bad_out["claim_update"]["status"], "survived_falsify")

        # Valid micropatch + post-state snapshot + `chain probe --build-cmd` succeeds cleanly!
        rc_ok, ok_out = _run_cli(
            [
                "claim",
                "reproduce",
                cid,
                "--worker",
                "w-rep",
                "--poc-cmd",
                "python3 -c 'import pathlib, gate; pathlib.Path(\"post_state.txt\").write_text(\"s1\"); raise SystemExit(1 if gate.allow(-1) else 0)'",
                "--control-cmd",
                "python3 -c 'import gate; assert gate.allow(5)'",
                "--micropatch",
                str(self.good_patch),
                "--max-changed-lines",
                "8",
                "--save-post-state",
                "post_state.txt",
            ],
            self.ajar_home,
            "run-p0-strikes",
        )
        self.assertEqual(rc_ok, 0, ok_out)
        snp_id = str(ok_out["snapshot_id"])
        self.assertTrue(snp_id.startswith("snp-"))

        rc_prb, prb_out = _run_cli(
            [
                "chain",
                "probe",
                "--from-snapshot",
                snp_id,
                "--build-cmd",
                "python3 -c 'import pathlib; pathlib.Path(\"built.marker\").write_text(\"ok\")'",
                "--cmd",
                "python3 -c 'import pathlib; assert pathlib.Path(\"post_state.txt\").read_text() == \"s1\" and pathlib.Path(\"built.marker\").is_file()'",
                "--oracle-json",
                '{"expect_exit_code": 0}',
            ],
            self.ajar_home,
            "run-p0-strikes",
        )
        self.assertEqual(rc_prb, 0, prb_out)
        self.assertTrue(prb_out["defect_fired"])
        self.assertEqual(prb_out["build"]["exit_code"], 0)

    def test_v33_table_rebuild_preserves_findings_foreign_key_target(self) -> None:
        old_db = self.tmp_path / "v32_fk.db"
        raw = sqlite3.connect(str(old_db), isolation_level=None)
        raw.executescript(
            """
            CREATE TABLE runs (
                run_id TEXT PRIMARY KEY, target_path TEXT NOT NULL, workspace_path TEXT NOT NULL,
                target_mode TEXT NOT NULL, workspace_mode TEXT NOT NULL, goal TEXT NOT NULL,
                stopping_criterion TEXT NOT NULL DEFAULT 'exhaustive-high',
                budget_usd REAL NOT NULL DEFAULT 14.0, in_scope_loc INTEGER NOT NULL DEFAULT 0,
                code_quote_usd REAL NOT NULL DEFAULT 10.0, cogs_cap_usd REAL NOT NULL DEFAULT 3.5,
                pricing_mode TEXT NOT NULL DEFAULT 'commercial_code', commitment_hash TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active', stop_reason TEXT DEFAULT '',
                closed_task_counter INTEGER NOT NULL DEFAULT 0, zero_skill_leases INTEGER NOT NULL DEFAULT 0,
                domain_skill_leases INTEGER NOT NULL DEFAULT 0, consecutive_stall_checks INTEGER NOT NULL DEFAULT 0,
                last_stop_event_id INTEGER NOT NULL DEFAULT 0, diff_range TEXT NOT NULL DEFAULT '',
                base_sha TEXT NOT NULL DEFAULT '', head_sha TEXT NOT NULL DEFAULT '',
                parent_run_id TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, finished_at TEXT
            );
            CREATE TABLE claims (
                claim_id TEXT PRIMARY KEY, surface_id TEXT, proposer_worker_id TEXT NOT NULL,
                seeded_by_human INTEGER NOT NULL DEFAULT 0, title TEXT NOT NULL,
                subsystem TEXT NOT NULL DEFAULT '', locus TEXT NOT NULL, mechanism TEXT NOT NULL,
                mechanism_key TEXT NOT NULL, severity TEXT NOT NULL DEFAULT 'high',
                falsification_prediction TEXT NOT NULL, falsification_test TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'proposed', falsifier_worker_id TEXT,
                falsify_notes TEXT NOT NULL DEFAULT '', falsify_control_locus TEXT,
                config_gate TEXT NOT NULL DEFAULT '', diff_state TEXT NOT NULL DEFAULT '',
                failed_repro_count INTEGER NOT NULL DEFAULT 0, last_observation_hash TEXT NOT NULL DEFAULT '',
                instrumented_since_fail INTEGER NOT NULL DEFAULT 0, research_state TEXT NOT NULL DEFAULT 'candidate',
                evidence_state TEXT NOT NULL DEFAULT 'unverified', customer_state TEXT NOT NULL DEFAULT 'pending',
                remediation_state TEXT NOT NULL DEFAULT 'unpatched' CHECK(remediation_state IN ('unpatched', 'micropatched', 'maintainer_patched')),
                duplicate_of_claim_id TEXT, env_blocker TEXT NOT NULL DEFAULT '',
                blocker_reason TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE findings (
                finding_id TEXT PRIMARY KEY, claim_id TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
                severity TEXT NOT NULL, locus TEXT NOT NULL, root_cause TEXT NOT NULL,
                poc_cmd TEXT NOT NULL, control_cmd TEXT NOT NULL, micropatch_path TEXT NOT NULL DEFAULT '',
                micropatch_diff TEXT NOT NULL DEFAULT '', arm1_clean_poc_json TEXT NOT NULL,
                arm2_clean_ctrl_json TEXT NOT NULL, arm3_patch_poc_json TEXT NOT NULL,
                arm4_patch_ctrl_json TEXT NOT NULL, attribution TEXT NOT NULL, created_at TEXT NOT NULL,
                FOREIGN KEY(claim_id) REFERENCES claims(claim_id)
            );
            CREATE TABLE tasks (
                task_id TEXT PRIMARY KEY, parent_task_id TEXT, surface_id TEXT, kind TEXT NOT NULL,
                title TEXT NOT NULL, subsystem TEXT NOT NULL DEFAULT '', locus TEXT NOT NULL DEFAULT '',
                priority TEXT NOT NULL DEFAULT 'high', status TEXT NOT NULL DEFAULT 'open', worker_id TEXT,
                skill_mode TEXT NOT NULL DEFAULT 'domain', lease_expires_at REAL, dry_control_locus TEXT,
                dry_control_reason TEXT, blocker_predicate TEXT, blocker_check_locus TEXT,
                salience_score INTEGER NOT NULL DEFAULT 60, reopened_boost INTEGER NOT NULL DEFAULT 0,
                attempt_count INTEGER NOT NULL DEFAULT 0, summary TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, closed_epoch REAL
            );
            INSERT INTO claims(
                claim_id, proposer_worker_id, title, locus, mechanism, mechanism_key,
                falsification_prediction, falsification_test, status, created_at, updated_at
            ) VALUES (
                'clm-fk1', 'w1', 'Test FK', 'gate.py:1', 'mech', 'mech',
                'pred', 'test', 'reproduced', '2026-11-20T00:00:00Z', '2026-11-20T00:00:00Z'
            );
            INSERT INTO findings(
                finding_id, claim_id, title, severity, locus, root_cause, poc_cmd, control_cmd,
                arm1_clean_poc_json, arm2_clean_ctrl_json, arm3_patch_poc_json, arm4_patch_ctrl_json,
                attribution, created_at
            ) VALUES (
                'fnd-fk1', 'clm-fk1', 'Test FK', 'high', 'gate.py:1', 'mech', 'true', 'true',
                '{}', '{}', '{}', '{}', 'autonomous', '2026-11-20T00:00:00Z'
            );
            """
        )
        raw.close()

        conn = open_run_db(old_db, create=False)
        try:
            f_sql = str(
                conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='findings'").fetchone()[0]
            )
            self.assertIn("REFERENCES claims(claim_id)", f_sql)
            self.assertNotIn("_claims_v32_old", f_sql)
            fk_errs = conn.execute("PRAGMA foreign_key_check;").fetchall()
            self.assertEqual(fk_errs, [])
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
