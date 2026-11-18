from __future__ import annotations

import io
import json
import os
import pathlib
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from ajar import EXIT_GATE_BLOCKED, EXIT_OK
from ajar.cli import main as cli_main
from ajar.db import open_run_db, render_task_context
from ajar.gates import (
    check_all_gates,
    compute_attribution_and_economics,
    evaluate_dry_surface_breaker,
)
from ajar.runner import run_autonomous_schedule, select_model_for_task
from ajar.workspace import init_run_workspace


def _run_cli(argv: list[str], ajar_home: pathlib.Path) -> tuple[int, dict[str, object]]:
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    with patch.dict(os.environ, {"AJAR_HOME": str(ajar_home)}, clear=False):
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            rc = cli_main(argv)
    raw = out_buf.getvalue().strip() or err_buf.getvalue().strip()
    payload = json.loads(raw) if raw else {}
    return rc, payload


class TestV31BugBrainAndEconomics(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = pathlib.Path(self._tmp.name)
        self.ajar_home = self.tmp_path / "ajar-home"
        self.ajar_home.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _create_sample_git_target(self) -> pathlib.Path:
        repo = self.tmp_path / "sample-app"
        (repo / "src").mkdir(parents=True)
        (repo / "src" / "auth.py").write_text(
            "import sys\n\n"
            "def check_role(user_role: str, required: str) -> bool:\n"
            "    # BUG: prefix match lets 'admin_guest' pass 'admin' check!\n"
            "    return user_role.startswith(required)\n\n"
            "if __name__ == '__main__':\n"
            "    role = sys.argv[1]\n"
            "    allowed = check_role(role, 'admin')\n"
            "    if role != 'admin' and allowed:\n"
            "        sys.exit(1)  # exploit: unauthorized privilege escalation\n"
            "    if role == 'admin' and not allowed:\n"
            "        sys.exit(2)  # broken benign admin path\n"
            "    sys.exit(0)\n",
            encoding="utf-8",
        )
        (repo / "src" / "ledger.py").write_text(
            "def settle_balance(balance: int, delta: int) -> int:\n"
            "    if delta < 0 and abs(delta) > balance:\n"
            "        raise ValueError('insufficient funds')\n"
            "    return balance + delta\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "test@ajar.dev"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "Ajar Test"], cwd=repo, check=True)
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=repo, check=True)
        return repo

    def test_quote_full_and_diff_and_35_percent_cogs_cap(self) -> None:
        repo = self._create_sample_git_target()
        # Add a second commit touching only src/ledger.py
        (repo / "src" / "ledger.py").write_text(
            "def settle_balance(balance: int, delta: int) -> int:\n"
            "    if delta < 0 and abs(delta) > balance:\n"
            "        raise ValueError('insufficient funds')\n"
            "    if delta == 0:\n"
            "        return balance\n"
            "    return balance + delta\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "src/ledger.py"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "ledger zero fastpath"], cwd=repo, check=True)

        rc_full, q_full = _run_cli(["quote", str(repo)], self.ajar_home)
        self.assertEqual(rc_full, EXIT_OK)
        self.assertEqual(q_full["scope_mode"], "full_repo")
        self.assertEqual(q_full["code_quote_usd"], 10.0)
        self.assertEqual(q_full["cogs_cap_usd"], 3.5)

        rc_diff, q_diff = _run_cli(["quote", str(repo), "--diff", "HEAD~1..HEAD"], self.ajar_home)
        self.assertEqual(rc_diff, EXIT_OK)
        self.assertEqual(q_diff["scope_mode"], "diff")
        self.assertEqual(q_diff["in_scope_loc"], 2)
        self.assertEqual(q_diff["code_quote_usd"], 10.0)
        self.assertEqual(q_diff["cogs_cap_usd"], 3.5)

        # Commercial default run sets budget_usd == cogs_cap_usd == 0.35 * quote
        info_comm = init_run_workspace(target=str(repo), ajar_home=self.ajar_home, run_id="run-comm")
        self.assertEqual(info_comm["pricing_mode"], "commercial_code")
        self.assertEqual(info_comm["budget_usd"], 3.5)
        self.assertEqual(info_comm["cogs_cap_usd"], 3.5)

        # Explicit --cogs-cap override sets custom_or_bounty mode
        rc_bty, info_bty = _run_cli(
            ["init", str(repo), "--run-id", "run-bounty", "--cogs-cap", "120", "--json"],
            self.ajar_home,
        )
        self.assertEqual(rc_bty, EXIT_OK)
        self.assertEqual(info_bty["pricing_mode"], "custom_or_bounty")
        self.assertEqual(info_bty["budget_usd"], 120.0)

    def test_guarded_primitive_anti_premature_dry_and_stage5_converge(self) -> None:
        repo = self._create_sample_git_target()
        _run_cli(["init", str(repo), "--run-id", "run-gp", "--json"], self.ajar_home)

        _, surf = _run_cli(
            [
                "surface",
                "add",
                "--run",
                "run-gp",
                "--name",
                "ledger-settle",
                "--kind",
                "rpc",
                "--subsystem",
                "src",
                "--locus",
                "src/ledger.py:1",
                "--priority",
                "critical",
                "--trust-boundary",
                "caller -> ledger balance",
            ],
            self.ajar_home,
        )
        sid = str(surf["surface_id"])

        _, tsk = _run_cli(
            [
                "task",
                "add",
                "--run",
                "run-gp",
                "--kind",
                "investigate",
                "--direction",
                "inside_out",
                "--title",
                "Audit settle_balance sink",
                "--surface",
                sid,
                "--subsystem",
                "src",
                "--locus",
                "src/ledger.py:1",
                "--priority",
                "critical",
            ],
            self.ajar_home,
        )
        tid = str(tsk["task_id"])
        self.assertEqual(tsk["direction"], "inside_out")

        # Register an inner primitive guarded by src/ledger.py:2
        _run_cli(
            [
                "primitive",
                "add",
                "--run",
                "run-gp",
                "--surface",
                sid,
                "--locus",
                "src/ledger.py:6",
                "--kind",
                "unchecked_addition_sink",
                "--preconditions",
                "delta bypasses negative bounds check",
                "--postconditions",
                "arbitrary balance credit",
                "--guarded-by",
                "src/ledger.py:2",
                "--guard-assumption",
                "caller cannot pass overflowed delta",
                "--evidence-cmd",
                "python3 -c 'print(1)'",
            ],
            self.ajar_home,
        )

        # Premature `ajar task dry` MUST be blocked while guarded primitive has no chain/block test!
        rc_dry_blocked, err_dry = _run_cli(
            [
                "task",
                "dry",
                tid,
                "--run",
                "run-gp",
                "--worker",
                "w-1",
                "--locus",
                "src/ledger.py:2",
                "--control",
                "Upstream delta < 0 and abs(delta) > balance check prevents overdraft.",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_dry_blocked, EXIT_GATE_BLOCKED)
        self.assertIn("Anti-premature-dry", str(err_dry.get("error", "")))

        # Gate check G5 must auto-enqueue a Stage-5 Converge (`chain`) task for the guarded primitive!
        conn = open_run_db("run-gp", ajar_home=self.ajar_home)
        try:
            g_res = check_all_gates(conn, target_dir=repo, auto_enqueue_chain=True)
            self.assertFalse(g_res["gates"]["G5_anomalies_and_chains"]["passed"])
            chain_task = conn.execute("SELECT task_id FROM tasks WHERE kind = 'chain' LIMIT 1").fetchone()
            self.assertIsNotNone(chain_task)
            chain_tid = str(chain_task["task_id"])
        finally:
            conn.close()

        # Complete the Stage-5 `chain` evaluation task; now `ajar task dry` is permitted!
        _run_cli(["task", "done", chain_tid, "--run", "run-gp", "--worker", "w-chain", "--summary", "Verified no bypass breaks src/ledger.py:2"], self.ajar_home)
        rc_dry_ok, out_dry = _run_cli(
            [
                "task",
                "dry",
                tid,
                "--run",
                "run-gp",
                "--worker",
                "w-1",
                "--locus",
                "src/ledger.py:2",
                "--control",
                "Upstream delta < 0 and abs(delta) > balance check prevents overdraft.",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_dry_ok, EXIT_OK, out_dry)

    def test_locus_bound_4arm_claim_mismatch_rescope_and_8arm_patch_verify(self) -> None:
        repo = self._create_sample_git_target()
        _run_cli(["init", str(repo), "--run-id", "run-fix", "--json"], self.ajar_home)

        # Propose claim at WRONG locus (src/ledger.py:2 instead of src/auth.py:5)
        _, prop = _run_cli(
            [
                "claim",
                "propose",
                "--run",
                "run-fix",
                "--worker",
                "w-prop",
                "--title",
                "Prefix role bypass in check_role",
                "--locus",
                "src/ledger.py:2",
                "--mechanism",
                "startswith('admin') accepts 'admin_guest'",
                "--severity",
                "high",
                "--falsification-prediction",
                "Exact equality check blocks admin_guest",
                "--falsification-test",
                "python3 src/auth.py admin_guest",
            ],
            self.ajar_home,
        )
        cid = str(prop["claim_id"])
        _run_cli(["claim", "survive", cid, "--run", "run-fix", "--worker", "w-falsify-1", "--notes", "Verified reachable"], self.ajar_home)

        # Write 1-line micro-patch fixing src/auth.py:5
        mpatch = self.tmp_path / "micro.diff"
        mpatch.write_text(
            "--- a/src/auth.py\n"
            "+++ b/src/auth.py\n"
            "@@ -3,5 +3,5 @@\n"
            " def check_role(user_role: str, required: str) -> bool:\n"
            "     # BUG: prefix match lets 'admin_guest' pass 'admin' check!\n"
            "-    return user_role.startswith(required)\n"
            "+    return user_role == required\n"
            "\n"
            " if __name__ == '__main__':\n",
            encoding="utf-8",
        )

        # Reproduce MUST fail with `claim_mismatch:` because claim.locus is src/ledger.py:2!
        rc_mis, out_mis = _run_cli(
            [
                "claim",
                "reproduce",
                cid,
                "--run",
                "run-fix",
                "--worker",
                "w-repro",
                "--mode",
                "source",
                "--poc-cmd",
                "python3 src/auth.py admin_guest",
                "--control-cmd",
                "python3 src/auth.py admin",
                "--micropatch",
                str(mpatch),
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_mis, EXIT_GATE_BLOCKED)
        self.assertIn("claim_mismatch:", json.dumps(out_mis))

        # Recover via `ajar claim rescope` to true root cause `src/auth.py:5`!
        rc_rsc, out_rsc = _run_cli(
            [
                "claim",
                "rescope",
                cid,
                "--run",
                "run-fix",
                "--worker",
                "w-repro",
                "--locus",
                "src/auth.py:5",
                "--reason",
                "Root cause lives in src/auth.py:5 check_role, not ledger.py.",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_rsc, EXIT_OK)
        self.assertEqual(out_rsc["status"], "proposed")

        # Re-survive from independent falsifier and run 4-arm reproduction -> PASSES!
        _run_cli(["claim", "survive", cid, "--run", "run-fix", "--worker", "w-falsify-2", "--notes", "Verified locus src/auth.py:5"], self.ajar_home)
        rc_rep, out_rep = _run_cli(
            [
                "claim",
                "reproduce",
                cid,
                "--run",
                "run-fix",
                "--worker",
                "w-repro",
                "--mode",
                "source",
                "--poc-cmd",
                "python3 src/auth.py admin_guest",
                "--control-cmd",
                "python3 src/auth.py admin",
                "--micropatch",
                str(mpatch),
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_rep, EXIT_OK, out_rep)
        fid = str(out_rep["finding_id"])

        # 8-Arm `ajar patch verify`: < 3 variants MUST be rejected!
        rc_few, _ = _run_cli(
            [
                "patch",
                "verify",
                fid,
                "--run",
                "run-fix",
                "--patch",
                str(mpatch),
                "--suite-cmd",
                "python3 src/auth.py admin && python3 src/auth.py user",
                "--variant-cmd",
                "python3 src/auth.py admin_1",
                "--variant-cmd",
                "python3 src/auth.py admin_2",
                "--caller-audit",
                "Verified check_role returns bool with zero NULL deref across all callers.",
                "--sibling-audit",
                "Audited src/ledger.py and confirmed zero sibling role prefix checks.",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_few, EXIT_GATE_BLOCKED)

        # 8-Arm `ajar patch verify` with 3 distinct bypass variants + full suite -> PASSES & sets maintainer_patched!
        rc_pv, out_pv = _run_cli(
            [
                "patch",
                "verify",
                fid,
                "--run",
                "run-fix",
                "--patch",
                str(mpatch),
                "--suite-cmd",
                "python3 src/auth.py admin && python3 src/auth.py guest",
                "--variant-cmd",
                "python3 src/auth.py admin_bypass",
                "--variant-cmd",
                "python3 src/auth.py administrator",
                "--variant-cmd",
                "python3 src/auth.py 'admin '",
                "--caller-audit",
                "Verified check_role returns bool cleanly across all CLI and handler callers.",
                "--sibling-audit",
                "Checked all modules in src/ and verified zero parallel role-check helpers.",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_pv, EXIT_OK, out_pv)
        self.assertEqual(out_pv["remediation_state"], "maintainer_patched")

    def test_steers_attribution_prefix_caching_graph_and_dry_breaker(self) -> None:
        repo = self._create_sample_git_target()
        _run_cli(["init", str(repo), "--run-id", "run-plat", "--cogs-cap", "20", "--json"], self.ajar_home)

        # 1. Add scope_authority steer -> preserves autonomous attribution!
        _, st1 = _run_cli(
            [
                "steer",
                "add",
                "--run",
                "run-plat",
                "--scope",
                "global",
                "--kind",
                "scope_authority",
                "--rule",
                "Ignore DoS requiring local root privileges.",
            ],
            self.ajar_home,
        )
        steer_id = str(st1["steer_id"])

        _, surf = _run_cli(
            [
                "surface",
                "add",
                "--run",
                "run-plat",
                "--name",
                "auth-cli",
                "--kind",
                "cli",
                "--subsystem",
                "src",
                "--locus",
                "src/auth.py:3",
                "--priority",
                "high",
            ],
            self.ajar_home,
        )
        sid = str(surf["surface_id"])

        _run_cli(["binding", "set", "--run", "run-plat", "--name", "REQUIRED_ROLE", "--value", "admin", "--locus", "src/auth.py:9"], self.ajar_home)
        _, t1 = _run_cli(["task", "add", "--run", "run-plat", "--kind", "investigate", "--surface", sid, "--title", "Task A", "--locus", "src/auth.py:3"], self.ajar_home)
        _, t2 = _run_cli(["task", "add", "--run", "run-plat", "--kind", "investigate", "--surface", sid, "--title", "Task B", "--locus", "src/ledger.py:1"], self.ajar_home)

        conn = open_run_db("run-plat", ajar_home=self.ajar_home)
        try:
            econ1 = compute_attribution_and_economics(conn)
            self.assertTrue(econ1["research_independence_pass"])

            # Verify prefix-stable prompt caching across Task A and Task B!
            c1 = render_task_context(conn, str(t1["task_id"]))["rendered"]
            c2 = render_task_context(conn, str(t2["task_id"]))["rendered"]
            prefix1 = c1.split("## Task Delta:", 1)[0]
            prefix2 = c2.split("## Task Delta:", 1)[0]
            self.assertEqual(prefix1, prefix2)
            self.assertIn("Active Workspace Steers", prefix1)
            self.assertIn("REQUIRED_ROLE = admin", prefix1)
            self.assertLess(len(c1.encode("utf-8")), 4096)

            # Dry-Surface Token Breaker: spend > 25% of $20 ($6.00) on `sid` with 0 signal!
            conn.execute(
                """
                INSERT INTO spend_ledger(entry_id, worker_id, surface_id, phase, model, tokens_in, tokens_out, cost_usd, notes, created_at)
                VALUES ('spd-1', 'w-1', ?, 'explore', 'hunt-m', 1000, 500, 6.0, 'dry explore', '2026-11-18T00:00:00Z')
                """,
                (sid,),
            )
            tripped = evaluate_dry_surface_breaker(conn)
            self.assertEqual(len(tripped), 1)
            self.assertEqual(tripped[0]["surface_id"], sid)
            t1_status = conn.execute("SELECT status FROM tasks WHERE task_id = ?", (t1["task_id"],)).fetchone()["status"]
            self.assertEqual(t1_status, "conditional_blocked")
        finally:
            conn.close()

        # Export Platform graph (`ajar-platform-graph/1`)
        rc_gr, graph = _run_cli(["export-graph", "--run", "run-plat"], self.ajar_home)
        self.assertEqual(rc_gr, EXIT_OK)
        self.assertEqual(graph["schema"], "ajar-platform-graph/1")
        self.assertEqual(len(graph["active_steers"]), 1)
        self.assertTrue(any(n["id"] == sid for n in graph["nodes"]))

        # Adding `research_steering` flips research_independence_pass to False; revoking steer works cleanly
        _run_cli(
            [
                "steer",
                "add",
                "--run",
                "run-plat",
                "--scope",
                "subsystem",
                "--filter",
                "src",
                "--kind",
                "research_steering",
                "--rule",
                "Check startswith role comparison in auth.py.",
            ],
            self.ajar_home,
        )
        rc_rev, out_rev = _run_cli(["steer", "revoke", steer_id, "--run", "run-plat", "--reason", "Scope expanded"], self.ajar_home)
        self.assertEqual(rc_rev, EXIT_OK)
        self.assertEqual(out_rev["active"], 0)

        conn2 = open_run_db("run-plat", ajar_home=self.ajar_home)
        try:
            econ2 = compute_attribution_and_economics(conn2)
            self.assertFalse(econ2["research_independence_pass"])
        finally:
            conn2.close()

    def test_best_of_n_discover_passes_and_role_tier_model_routing(self) -> None:
        with patch.dict(
            os.environ,
            {
                "AJAR_MODEL_REASON": "claude-opus-reason",
                "AJAR_MODEL_HUNT": "gpt-hunt-fast",
            },
            clear=False,
        ):
            self.assertEqual(
                select_model_for_task({"kind": "investigate", "skill_mode": "zero_skill"}),
                "claude-opus-reason",
            )
            self.assertEqual(
                select_model_for_task({"kind": "chain", "skill_mode": "domain"}),
                "claude-opus-reason",
            )
            self.assertEqual(
                select_model_for_task({"kind": "investigate", "skill_mode": "domain"}),
                "gpt-hunt-fast",
            )
            self.assertEqual(
                select_model_for_task({"kind": "reproduce", "skill_mode": "domain"}),
                "gpt-hunt-fast",
            )

        repo = self._create_sample_git_target()
        res = run_autonomous_schedule(
            target=str(repo),
            run_id="run-disc",
            discover_passes=4,
            max_steps=0,
            ajar_home=self.ajar_home,
        )
        self.assertEqual(res["run_id"], "run-disc")
        conn = open_run_db("run-disc", ajar_home=self.ajar_home)
        try:
            dirs = {r["direction"] for r in conn.execute("SELECT direction FROM tasks").fetchall()}
            self.assertTrue({"outside_in", "inside_out", "native_ffi", "peer_symmetry"}.issubset(dirs))
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
