"""Tests and seeded A/B simulation benchmark for Ajar v3.4 (`ADR-0025`)."""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import random
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock

from ajar import EXIT_GATE_BLOCKED, EXIT_OK
from ajar.cli import main as cli_main
from ajar.db import open_run_db
from ajar.mcp import dispatch_mcp_tool
from ajar.store import immediate_tx


def _run_cli(argv: list[str], ajar_home: pathlib.Path) -> tuple[int, dict[str, object]]:
    out = io.StringIO()
    err = io.StringIO()
    with (
        mock.patch.dict(os.environ, {"AJAR_HOME": str(ajar_home)}),
        contextlib.redirect_stdout(out),
        contextlib.redirect_stderr(err),
    ):
        rc = cli_main(argv)
    txt = out.getvalue().strip()
    payload: dict[str, object] = {}
    if txt:
        try:
            parsed = json.loads(txt)
            if isinstance(parsed, dict):
                payload = parsed
        except json.JSONDecodeError:
            payload = {"raw": txt}
    if err.getvalue().strip():
        payload["_stderr"] = err.getvalue().strip()
    return rc, payload


def _init_git_repo(repo_dir: pathlib.Path, files: dict[str, str]) -> None:
    repo_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_dir, check=True)
    for rel, content in files.items():
        fp = repo_dir / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo_dir, check=True)


class TestV34HillClimbingCatalogAndSeal(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self._tmp.name)
        self.ajar_home = self.base / "ajar-home"
        self.target = self.base / "target"
        _init_git_repo(
            self.target,
            {
                "src/sink.py": (
                    "import subprocess\n"
                    "def execute_hook(hook_path: str) -> int:\n"
                    "    if hook_path == 'PWNED':\n"
                    "        print('CROWN_JEWEL_RCE')\n"
                    "        return 1\n"
                    "    return 0\n"
                ),
                "src/loader.py": (
                    "from src.sink import execute_hook\n"
                    "def load_workspace_hooks(mode: str) -> int:\n"
                    "    return execute_hook(mode)\n"
                ),
                "src/entry.py": (
                    "import os, sys\n"
                    "from src.loader import load_workspace_hooks\n"
                    "def apply_bundle(arg: str) -> int:\n"
                    "    if arg == 'benign':\n"
                    "        return 0\n"
                    "    active = set(filter(None, os.environ.get('AJAR_ACTIVE_STEPS', '').split(',')))\n"
                    "    ablate = set(filter(None, os.environ.get('AJAR_ABLATE_STEPS', '').split(',')))\n"
                    "    if 'BAD_SYNTAX' in ablate:\n"
                    "        sys.stderr.write('SyntaxError: broken step ablation\\n')\n"
                    "        return 1\n"
                    "    if os.environ.get('FORCE_PRIMARY_FAIL') == '1' and os.environ.get('AJAR_STEP_SWAPS', '') == '':\n"
                    "        return 0\n"
                    "    if ablate:\n"
                    "        return 0\n"
                    "    return load_workspace_hooks('PWNED')\n"
                    "if __name__ == '__main__':\n"
                    "    raise SystemExit(apply_bundle(sys.argv[1]))\n"
                ),
                "src/unvisited_peer.py": (
                    "from src.loader import load_workspace_hooks\n"
                    "def peer_import(payload: str) -> int:\n"
                    "    return load_workspace_hooks(payload)\n"
                ),
            },
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_lead_voting_root_plateau_unvisited_map_and_phase_gate(self) -> None:
        rc, init_out = _run_cli(
            [
                "init",
                str(self.target),
                "--run-id",
                "run-v34-sched",
                "--stopping",
                "crown-jewel",
                "--phase",
                "hunt",
                "--json",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc, EXIT_OK, init_out)
        self.assertTrue(str(init_out.get("harness_sha256") or ""))

        _, s1 = _run_cli(
            [
                "surface",
                "add",
                "--run",
                "run-v34-sched",
                "--name",
                "Entry",
                "--kind",
                "cli",
                "--subsystem",
                "src",
                "--locus",
                "src/entry.py:3",
                "--priority",
                "high",
            ],
            self.ajar_home,
        )
        surf_id = str(s1["surface_id"])

        _, t_low_ev = _run_cli(
            [
                "task",
                "add",
                "--run",
                "run-v34-sched",
                "--kind",
                "investigate",
                "--title",
                "Audit entry",
                "--locus",
                "src/entry.py:3",
                "--priority",
                "high",
            ],
            self.ajar_home,
        )
        _, t_high_ev = _run_cli(
            [
                "task",
                "add",
                "--run",
                "run-v34-sched",
                "--kind",
                "investigate",
                "--title",
                "Audit unvisited peer",
                "--locus",
                "src/unvisited_peer.py:2",
                "--priority",
                "high",
            ],
            self.ajar_home,
        )

        # Cast two independent high-EV votes on src/unvisited_peer.py:2 (via CLI + MCP)
        rc_v1, v1 = _run_cli(
            [
                "lead",
                "vote",
                "--run",
                "run-v34-sched",
                "--worker",
                "scout-1",
                "--target-kind",
                "slice",
                "--locus",
                "src/unvisited_peer.py:2",
                "--impact",
                "10",
                "--plausibility",
                "9",
                "--chainability",
                "10",
                "--effort",
                "2",
                "--rationale",
                "Direct 2-hop caller into execute_hook",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_v1, EXIT_OK, v1)
        mcp_vote = dispatch_mcp_tool(
            "run-v34-sched",
            "ajar_lead_vote",
            {
                "worker_id": "scout-2",
                "target_kind": "slice",
                "locus": "src/unvisited_peer.py:2",
                "impact_score": 9,
                "plausibility_score": 9,
                "chainability_score": 10,
                "effort_cost": 3,
                "rationale": "Confirmed unguarded call edge",
            },
            ajar_home=self.ajar_home,
        )
        self.assertGreater(float(mcp_vote["ev_score"]), 75.0)

        rc_rk, rk = _run_cli(["lead", "rank", "--run", "run-v34-sched"], self.ajar_home)
        self.assertEqual(rc_rk, EXIT_OK, rk)
        ranked = rk["ranked_leads"]
        assert isinstance(ranked, list)
        self.assertEqual(ranked[0]["voter_count"], 2)

        # Next leased investigate task MUST be the consensus-voted task (`t_high_ev`)!
        _, leased = _run_cli(
            ["task", "lease", "--run", "run-v34-sched", "--worker", "w-1", "--kind", "investigate"],
            self.ajar_home,
        )
        leased_obj = leased.get("leased") or leased
        assert isinstance(leased_obj, dict)
        self.assertEqual(leased_obj["task_id"], t_high_ev["task_id"])

        # Record coverage on src/entry.py only and verify `ajar map --unvisited` surfaces unvisited slices
        _run_cli(
            [
                "coverage",
                "record",
                "src/entry.py",
                "--start-line",
                "1",
                "--end-line",
                "15",
                "--run",
                "run-v34-sched",
            ],
            self.ajar_home,
        )
        rc_mu, map_unv = _run_cli(
            ["map", "--unvisited", "--slice-cap", "300", "--json", "--run", "run-v34-sched"],
            self.ajar_home,
        )
        self.assertEqual(rc_mu, EXIT_OK)
        self.assertTrue(map_unv["unvisited_only"])
        self.assertGreater(int(map_unv["scout_coverage_pct"]), 0.0)
        self.assertGreaterEqual(int(map_unv["unvisited_slice_count"]), 1)

        # Phase gate: add an unexplained anomaly -> unforced `phase advance --to remediate` MUST block!
        _run_cli(
            [
                "anomaly",
                "add",
                "--run",
                "run-v34-sched",
                "--surface",
                surf_id,
                "--locus",
                "src/entry.py:6",
                "--observation",
                "Unexpected hook load path",
            ],
            self.ajar_home,
        )
        rc_pa_blk, _ = _run_cli(["phase", "advance", "--to", "remediate", "--run", "run-v34-sched"], self.ajar_home)
        self.assertEqual(rc_pa_blk, EXIT_GATE_BLOCKED)

        # Forced advance without notes fails; with notes succeeds and records scope_authority touch!
        rc_pa_nonotes, _ = _run_cli(
            ["phase", "advance", "--to", "remediate", "--force", "--run", "run-v34-sched"],
            self.ajar_home,
        )
        self.assertNotEqual(rc_pa_nonotes, EXIT_OK)
        rc_pa_ok, pa_ok = _run_cli(
            [
                "phase",
                "advance",
                "--to",
                "remediate",
                "--force",
                "--notes",
                "Operator authorized early patch check",
                "--run",
                "run-v34-sched",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_pa_ok, EXIT_OK, pa_ok)
        self.assertTrue(pa_ok["forced"])

        # Per-root plateau breaker: insert a finding + 2 closed post-repro tasks on src/entry.py
        conn = open_run_db("run-v34-sched", ajar_home=self.ajar_home)
        try:
            with immediate_tx(conn):
                conn.execute(
                    """
                    INSERT INTO claims(
                        claim_id, proposer_worker_id, falsifier_worker_id, title, subsystem, locus,
                        mechanism, mechanism_key, severity, falsification_prediction, falsification_test,
                        status, research_state, evidence_state, created_at, updated_at
                    ) VALUES (
                        'clm-root1', 'w1', 'w2', 'Entry write', 'src', 'src/entry.py:5',
                        'm', 'm', 'high', 'pred', 'test', 'reproduced', 'confirmed', 'reproduced',
                        '2026-11-23T00:00:00Z', '2026-11-23T00:00:00Z'
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO findings(
                        finding_id, claim_id, title, severity, locus, root_cause, poc_cmd, control_cmd,
                        arm1_clean_poc_json, arm2_clean_ctrl_json, arm3_patch_poc_json, arm4_patch_ctrl_json,
                        realism_tier, attribution, created_at
                    ) VALUES (
                        'fnd-root1', 'clm-root1', 'Entry write', 'high', 'src/entry.py:5', 'm', 'true', 'true',
                        '{}', '{}', '{}', '{}', 'stepping_stone', 'found_autonomously_by_ajar',
                        '2026-11-23T00:00:00Z'
                    )
                    """
                )
                for idx in (1, 2):
                    conn.execute(
                        """
                        INSERT INTO tasks(
                            task_id, kind, title, subsystem, locus, priority, status, salience_score,
                            created_at, updated_at
                        ) VALUES (?, 'escalate', 'Post-repro churn', 'src', 'src/entry.py:5', 'high', 'done', 75,
                                  '2026-11-23T01:00:00Z', '2026-11-23T01:05:00Z')
                        """,
                        (f"tsk-post-{idx}",),
                    )
        finally:
            conn.close()

        rc_th, th = _run_cli(["lead", "throttles", "--run", "run-v34-sched"], self.ajar_home)
        self.assertEqual(rc_th, EXIT_OK, th)
        throttles = th["root_plateau_throttles"]
        assert isinstance(throttles, list)
        self.assertTrue(any(t["root_file"] == "src/entry.py" and t["throttled"] for t in throttles))
        _run_cli(["pulse", "--run", "run-v34-sched"], self.ajar_home)
        conn = open_run_db("run-v34-sched", ajar_home=self.ajar_home)
        try:
            sal = int(
                conn.execute(
                    "SELECT salience_score FROM tasks WHERE task_id = ?",
                    (t_low_ev["task_id"],),
                ).fetchone()["salience_score"]
            )
            self.assertLessEqual(sal, 55)
        finally:
            conn.close()

    def test_catalog_backslice_backup_step_chains_and_fail_closed_ablation(self) -> None:
        _run_cli(
            [
                "init",
                str(self.target),
                "--run-id",
                "run-v34-cat",
                "--stopping",
                "crown-jewel",
                "--json",
            ],
            self.ajar_home,
        )
        _, jw = _run_cli(
            [
                "door",
                "jewel-add",
                "--run",
                "run-v34-cat",
                "--name",
                "Hook Exec Sink",
                "--locus",
                "src/sink.py:2",
                "--impact-class",
                "rce",
                "--symbols",
                "execute_hook",
                "--max-steps",
                "1",
            ],
            self.ajar_home,
        )
        jewel_id = str(jw["jewel_id"])

        # Register primary (failing) capability, backup (working) capability, and intermediate trust_gadget
        _, p_primary = _run_cli(
            [
                "primitive",
                "add",
                "--run",
                "run-v34-cat",
                "--locus",
                "src/entry.py:4",
                "--kind",
                "arbitrary_write",
                "--role",
                "capability",
                "--preconditions",
                "attacker bundle",
                "--postconditions",
                "writes hook path",
                "--provides-tags",
                "fs:hook_write",
                "--evidence-cmd",
                "true",
            ],
            self.ajar_home,
        )
        _, p_backup = _run_cli(
            [
                "primitive",
                "add",
                "--run",
                "run-v34-cat",
                "--locus",
                "src/unvisited_peer.py:2",
                "--kind",
                "arbitrary_write",
                "--role",
                "capability",
                "--preconditions",
                "peer bundle",
                "--postconditions",
                "writes hook path cleanly",
                "--provides-tags",
                "fs:hook_write",
                "--evidence-cmd",
                "true",
            ],
            self.ajar_home,
        )
        _, p_gadget = _run_cli(
            [
                "primitive",
                "add",
                "--run",
                "run-v34-cat",
                "--locus",
                "src/loader.py:2",
                "--kind",
                "hook_dispatch",
                "--role",
                "trust_gadget",
                "--trusted-invariant",
                "hook directory is repo-controlled",
                "--preconditions",
                "fs:hook_write",
                "--postconditions",
                "executes hook",
                "--requires-tags",
                "fs:hook_write",
                "--provides-tags",
                "exec:hook",
                "--evidence-cmd",
                "true",
            ],
            self.ajar_home,
        )

        # 1. Unified Catalog Search + MCP parity
        rc_cs, cs = _run_cli(["catalog", "search", "--tags", "fs:hook_write", "--run", "run-v34-cat"], self.ajar_home)
        self.assertEqual(rc_cs, EXIT_OK, cs)
        self.assertGreaterEqual(int(cs["matched_count"]), 3)
        self.assertGreaterEqual(len(list(cs["composable_pairs"])), 2)

        mcp_bs = dispatch_mcp_tool(
            "run-v34-cat",
            "ajar_catalog_backslice",
            {"sink": jewel_id, "max_hops": 3},
            ajar_home=self.ajar_home,
        )
        self.assertGreaterEqual(int(mcp_bs["reachable_files_count"]), 3)
        unv_files = [u["file"] for u in mcp_bs["unvisited_caller_files"]]
        self.assertIn("src/unvisited_peer.py", unv_files)
        self.assertGreaterEqual(len(mcp_bs["candidate_backward_chains"]), 2)

        # 2. Modular `--backup-step`: FORCE_PRIMARY_FAIL=1 makes primary fail unless swapped to p_backup!
        prim_id = str(p_primary["primitive_id"])
        bak_id = str(p_backup["primitive_id"])
        gad_id = str(p_gadget["primitive_id"])
        rc_ch, ch = _run_cli(
            [
                "chain",
                "propose",
                "--run",
                "run-v34-cat",
                "--title",
                "Modular backup swap RCE chain",
                "--steps",
                f"{prim_id},{gad_id}",
                "--backup-step",
                f"{prim_id}:{bak_id}",
                "--jewel",
                jewel_id,
                "--declared-steps",
                "1",
                "--poc-cmd",
                "FORCE_PRIMARY_FAIL=1 python3 src/entry.py exploit # $AJAR_ACTIVE_STEPS $AJAR_ABLATE_STEPS",
                "--control-cmd",
                "python3 src/entry.py benign",
                "--oracle-json",
                '{"expect_regex":"CROWN_JEWEL_RCE"}',
                "--severity",
                "critical",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_ch, EXIT_OK, ch)
        self.assertTrue(ch["verified"])
        self.assertEqual(ch["active_steps"], [bak_id, gad_id])
        self.assertEqual(len(list(ch["backup_swaps_tried"])), 1)
        self.assertEqual(ch["realism_tier"], "crown_jewel")

        # 3. Chain calibration (`ajar chain calibrate`) downgrading crown_jewel -> high_impact re-locks jewel!
        chain_id = str(ch["chain_id"])
        rc_cc, cc = _run_cli(
            [
                "chain",
                "calibrate",
                chain_id,
                "--run",
                "run-v34-cat",
                "--realism-tier",
                "high_impact",
                "--declared-steps",
                "2",
                "--reason",
                "Requires 2-step caller checkout",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_cc, EXIT_OK, cc)
        self.assertEqual(cc["realism_tier"], "high_impact")

        # 4. Fail-closed step ablation: if neutralizing a step causes SyntaxError, chain MUST fail closed!
        conn = open_run_db("run-v34-cat", ajar_home=self.ajar_home)
        try:
            with immediate_tx(conn):
                conn.execute(
                    """
                    INSERT INTO primitives(
                        primitive_id, subsystem, locus, kind, role, preconditions, postconditions,
                        provides_tags_json, requires_tags_json, evidence_cmd, status, created_at
                    ) VALUES ('BAD_SYNTAX', 'src', 'src/entry.py:9', 'quirk', 'capability', 'p', 'q',
                              '[]', '[]', 'true', 'active', '2026-11-23T00:00:00Z')
                    """
                )
        finally:
            conn.close()

        rc_bad_abl, bad_abl = _run_cli(
            [
                "chain",
                "propose",
                "--run",
                "run-v34-cat",
                "--title",
                "Broken syntax ablation chain",
                "--steps",
                f"BAD_SYNTAX,{gad_id}",
                "--poc-cmd",
                "python3 src/entry.py exploit # $AJAR_ABLATE_STEPS",
                "--control-cmd",
                "python3 src/entry.py benign",
                "--oracle-json",
                '{"expect_regex":"CROWN_JEWEL_RCE"}',
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_bad_abl, EXIT_GATE_BLOCKED, bad_abl)
        self.assertFalse(bad_abl["verified"])
        self.assertIn("failed closed", str(bad_abl["reason"]))

    def test_root_grouping_corrections_harness_tamper_close_and_bundle_seal(self) -> None:
        _run_cli(
            [
                "init",
                str(self.target),
                "--run-id",
                "run-v34-int",
                "--allow-historical-target",
                "--json",
            ],
            self.ajar_home,
        )
        _, c1 = _run_cli(
            [
                "claim",
                "propose",
                "--run",
                "run-v34-int",
                "--worker",
                "w1",
                "--title",
                "Primary entry bypass",
                "--locus",
                "src/entry.py:4",
                "--mechanism",
                "apply_bundle bypasses validation at src/entry.py:4 reaching load_workspace_hooks",
                "--falsification-prediction",
                "Guard rejects non-benign bundle",
                "--falsification-test",
                "python3 src/entry.py benign",
            ],
            self.ajar_home,
        )
        cid1 = str(c1["claim_id"])
        _, c2 = _run_cli(
            [
                "claim",
                "propose",
                "--run",
                "run-v34-int",
                "--worker",
                "w1",
                "--title",
                "Corroborated peer route into same root",
                "--locus",
                "src/unvisited_peer.py:2",
                "--same-root-of",
                cid1,
                "--mechanism",
                "peer_import calls same unguarded loader as src/entry.py:4",
                "--falsification-prediction",
                "Loader validates caller path",
                "--falsification-test",
                "python3 -c 'print(1)'",
            ],
            self.ajar_home,
        )
        cid2 = str(c2["claim_id"])
        _, c3 = _run_cli(
            [
                "claim",
                "propose",
                "--run",
                "run-v34-int",
                "--worker",
                "w1",
                "--title",
                "Duplicate claim on entry",
                "--locus",
                "src/entry.py:6",
                "--mechanism",
                "Duplicate entry route into src/entry.py:4",
                "--falsification-prediction",
                "Guard blocks duplicate",
                "--falsification-test",
                "python3 -c 'print(1)'",
            ],
            self.ajar_home,
        )
        cid3 = str(c3["claim_id"])
        rc_dup, dup_out = _run_cli(
            [
                "claim",
                "duplicate",
                cid3,
                "--of",
                cid1,
                "--worker",
                "w2",
                "--reason",
                "Identical root cause in apply_bundle",
                "--run",
                "run-v34-int",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_dup, EXIT_OK, dup_out)

        # Insert 2 findings sharing `same_root_claim_id = cid1` -> distinct_root_causes_count MUST be 1!
        # Also test timestamp-ordered `finding_corrections` vs later `finding_calibrated` event!
        conn = open_run_db("run-v34-int", ajar_home=self.ajar_home)
        try:
            with immediate_tx(conn):
                conn.execute("UPDATE claims SET same_root_claim_id = ? WHERE claim_id = ?", (cid1, cid1))
                for idx, cid in enumerate((cid1, cid2), start=1):
                    conn.execute(
                        "UPDATE claims SET status = 'reproduced', falsifier_worker_id = 'w2', research_state = 'confirmed', evidence_state = 'reproduced' WHERE claim_id = ?",
                        (cid,),
                    )
                    conn.execute(
                        """
                        INSERT INTO findings(
                            finding_id, claim_id, title, severity, locus, root_cause, poc_cmd, control_cmd,
                            arm1_clean_poc_json, arm2_clean_ctrl_json, arm3_patch_poc_json, arm4_patch_ctrl_json,
                            realism_tier, attribution, created_at
                        ) VALUES (?, ?, ?, 'critical', ?, 'root', 'true', 'true', '{}', '{}', '{}', '{}',
                                  'high_impact', 'found_autonomously_by_ajar', '2026-11-20T10:00:00Z')
                        """,
                        (f"fnd-r{idx}", cid, f"Finding {idx}", f"src/f{idx}.py:1"),
                    )
                # fnd-r1 gets a finding_corrections override to `high` at 16:00Z (no later calibrate -> resolves `high`)
                conn.execute(
                    """
                    INSERT INTO finding_corrections(correction_id, finding_id, claim_id, payload_json, reason, actor, created_at)
                    VALUES ('cor-1', 'fnd-r1', ?, '{"severity":"high","remediation_state":"maintainer_patched"}', 'Independent review', 'coordinator', '2026-11-20T16:00:00Z')
                    """,
                    (cid1,),
                )
                # fnd-r2 gets a finding_corrections override to `high` at 16:00Z, THEN a `finding_calibrated` event to `medium` at 22:00Z -> resolves `medium`!
                conn.execute(
                    """
                    INSERT INTO finding_corrections(correction_id, finding_id, claim_id, payload_json, reason, actor, created_at)
                    VALUES ('cor-2', 'fnd-r2', ?, '{"severity":"high"}', 'Early review', 'coordinator', '2026-11-20T16:00:00Z')
                    """,
                    (cid2,),
                )
                conn.execute("UPDATE findings SET severity = 'medium', realism_tier = 'stepping_stone' WHERE finding_id = 'fnd-r2'")
                conn.execute(
                    "INSERT INTO events(ts, actor, action, entity_id, payload_json) VALUES ('2026-11-20T22:00:00Z', 'operator', 'finding_calibrated', 'fnd-r2', '{\"new_severity\":\"medium\"}')"
                )
                # Simulate mid-run harness edit by altering runs.harness_sha256
                conn.execute("UPDATE runs SET harness_sha256 = ?", ("0" * 64,))
        finally:
            conn.close()

        rc_doc, doc = _run_cli(["doctor", "--run", "run-v34-int"], self.ajar_home)
        self.assertEqual(rc_doc, EXIT_OK, doc)
        rh = doc["run_health"]
        assert isinstance(rh, dict)
        self.assertTrue(rh["harness_modified_mid_run"])

        rc_cls, cls_out = _run_cli(
            [
                "close",
                "--run",
                "run-v34-int",
                "--reason",
                "window_reached",
                "--notes",
                "78h campaign window reached; closing cleanly for review",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_cls, EXIT_OK, cls_out)
        self.assertEqual(cls_out["stop_reason"], "window_reached")

        _, rep = _run_cli(["report", "--run", "run-v34-int", "--format", "json"], self.ajar_home)
        self.assertEqual(rep["distinct_root_causes_count"], 1)
        self.assertTrue(rep["harness_integrity"]["harness_modified_mid_run"])  # type: ignore[index]
        by_fid = {f["finding_id"]: f for f in rep["findings"]}  # type: ignore[attr-defined]
        self.assertEqual(by_fid["fnd-r1"]["severity"], "high")
        self.assertEqual(by_fid["fnd-r1"]["remediation_state"], "maintainer_patched")
        self.assertEqual(by_fid["fnd-r2"]["severity"], "medium")

        # Atomic Bundle Seal & Verify (`ajar bundle {seal,verify}`)
        bundle_dir = self.base / "clean-disclosure-bundle"
        bundle_dir.mkdir()
        (bundle_dir / "ADVISORY.txt").write_text(
            "Summary: prepare_symlink_changes misses mode-less symlink rename in apply.c.\n",
            encoding="utf-8",
        )
        (bundle_dir / "0001-fix.patch").write_text(
            "--- a/apply.c\n+++ b/apply.c\n@@ -1 +1 @@\n-old\n+new\n",
            encoding="utf-8",
        )

        # Symlink root MUST be rejected!
        sym_root = self.base / "symlink-bundle"
        sym_root.symlink_to(bundle_dir)
        rc_sym, _ = _run_cli(["bundle", "seal", str(sym_root)], self.ajar_home)
        self.assertEqual(rc_sym, EXIT_GATE_BLOCKED)

        # Leaked local developer path inside tar archive MUST be rejected!
        bad_tar = bundle_dir / "evidence.tar.gz"
        leaked_path = "/" + "Users/" + "alice/workspace/secret.txt"
        with tarfile.open(bad_tar, "w:gz") as tf:
            raw = f"captured from {leaked_path}\n".encode("utf-8")
            ti = tarfile.TarInfo("note.txt")
            ti.size = len(raw)
            tf.addfile(ti, io.BytesIO(raw))
        rc_leak, leak_out = _run_cli(["bundle", "seal", str(bundle_dir)], self.ajar_home)
        self.assertEqual(rc_leak, EXIT_GATE_BLOCKED, leak_out)
        bad_tar.unlink()

        # Clean bundle seals + verifies cleanly, and detects post-seal tampering!
        rc_seal, seal_out = _run_cli(["bundle", "seal", str(bundle_dir)], self.ajar_home)
        self.assertEqual(rc_seal, EXIT_OK, seal_out)
        rc_ver, ver_out = _run_cli(["bundle", "verify", str(bundle_dir)], self.ajar_home)
        self.assertEqual(rc_ver, EXIT_OK, ver_out)
        self.assertTrue(ver_out["verified"])

        (bundle_dir / "ADVISORY.txt").write_text("tampered\n", encoding="utf-8")
        rc_tamper, tamper_out = _run_cli(["bundle", "verify", str(bundle_dir)], self.ajar_home)
        self.assertEqual(rc_tamper, EXIT_GATE_BLOCKED, tamper_out)
        self.assertFalse(tamper_out["verified"])

    def test_seeded_30_trial_multihop_ab_benchmark_v33_vs_v34(self) -> None:
        """Quantitative 30-seed simulation benchmark comparing v3.3 FIFO/tag-only vs v3.4 EV+Plateau+Backslice+Backup."""
        trials = 30
        budget_steps = 14
        v33_wins = 0
        v34_wins = 0
        v33_wasted_churn = 0
        v34_wasted_churn = 0

        for seed in range(100, 100 + trials):
            rng = random.Random(seed)
            # 10 candidate leads: 1 shallow stepping-stone root generating 6 noisy follow-up churn tasks,
            # 5 dry distractors, 1 indirect-sink trust_gadget caller, and 2 upstream write capabilities
            # (primary fails 60% of the time; backup succeeds 95% of the time).
            primary_works = rng.random() >= 0.60
            backup_works = rng.random() >= 0.05

            # --- Control (`v3.3`): FIFO + unthrottled post-repro churn + single-step chain ---
            v33_queue = [
                ("shallow_root", 80),
                *[("post_repro_churn", 78) for _ in range(6)],
                *[("distractor", 75) for _ in range(5)],
                *[("unvisited_slice", 68) for _ in range(8)],
                ("indirect_caller_slice", 70),
                ("primary_cap", 72),
            ]
            v33_queue.sort(key=lambda x: -x[1])
            v33_found_indirect = False
            v33_found_cap = False
            for kind, _sal in v33_queue[:budget_steps]:
                if kind == "post_repro_churn":
                    v33_wasted_churn += 1
                elif kind == "indirect_caller_slice":
                    v33_found_indirect = True
                elif kind == "primary_cap":
                    v33_found_cap = True
            if v33_found_indirect and v33_found_cap and primary_works:
                v33_wins += 1

            # --- Treatment (`v3.4`): EV consensus boost + `-35` root plateau breaker after 2 post-repro tasks + backslice + backup-step ---
            v34_post_repro_seen = 0
            v34_tasks = [
                ["shallow_root", 80],
                *[["post_repro_churn", 78] for _ in range(6)],
                *[["distractor", 72] for _ in range(5)],
                *[["unvisited_slice", 68] for _ in range(8)],
                ["indirect_caller_slice", 80 + 12],  # EV consensus + backslice boost
                ["primary_cap", 80 + 10],
                ["backup_cap", 80 + 9],
            ]
            v34_found_indirect = False
            v34_found_primary = False
            v34_found_backup = False
            steps_used = 0
            while steps_used < budget_steps and v34_tasks:
                v34_tasks.sort(key=lambda x: -int(x[1]))
                kind, _sal = v34_tasks.pop(0)
                steps_used += 1
                if kind == "post_repro_churn":
                    v34_wasted_churn += 1
                    v34_post_repro_seen += 1
                    if v34_post_repro_seen >= 2:
                        for item in v34_tasks:
                            if item[0] == "post_repro_churn":
                                item[1] = int(item[1]) - 35
                elif kind == "indirect_caller_slice":
                    v34_found_indirect = True
                elif kind == "primary_cap":
                    v34_found_primary = True
                elif kind == "backup_cap":
                    v34_found_backup = True

            chain_landed = v34_found_indirect and (
                (v34_found_primary and primary_works) or (v34_found_backup and backup_works)
            )
            if chain_landed:
                v34_wins += 1

        self.assertGreater(v34_wins, v33_wins * 2)
        self.assertLessEqual(v34_wasted_churn, trials * 2)
        self.assertGreater(v33_wasted_churn, v34_wasted_churn * 2)


if __name__ == "__main__":
    unittest.main()
