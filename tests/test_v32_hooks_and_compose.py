from __future__ import annotations

import io
import json
import os
import pathlib
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from ajar import EXIT_GATE_BLOCKED, EXIT_OK
from ajar.cli import main as cli_main
from ajar.db import open_run_db, render_task_context, run_dir_for
from ajar.oracles import index_target_oracles, query_oracle
from ajar.runner import detect_soliloquy_transcript
from ajar.workspace import unlock_run_dir_permissions


def _run_cli(argv: list[str], ajar_home: pathlib.Path) -> tuple[int, dict[str, object]]:
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    with patch.dict(os.environ, {"AJAR_HOME": str(ajar_home)}, clear=False):
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            rc = cli_main(argv)
    raw = out_buf.getvalue().strip() or err_buf.getvalue().strip()
    payload = json.loads(raw) if raw else {}
    return rc, payload


class TestV32HooksAndComposableRepro(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = pathlib.Path(self._tmp.name)
        self.ajar_home = self.tmp_path / "ajar-home"
        self.ajar_home.mkdir()

    def tearDown(self) -> None:
        runs_root = self.ajar_home / "runs"
        if runs_root.is_dir():
            for child in runs_root.iterdir():
                unlock_run_dir_permissions(child)
        self._tmp.cleanup()

    def _init_git_repo(self, repo: pathlib.Path) -> None:
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "test@ajar.dev"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "Ajar Test"], cwd=repo, check=True)
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=repo, check=True)

    def test_zero_overhead_plain_code_vs_epistemic_hooks_and_prefix_cache_identity(self) -> None:
        repo = self.tmp_path / "plain-app"
        (repo / "src").mkdir(parents=True)
        (repo / "src" / "guard.py").write_text(
            "def enforce_positive(amount: int) -> bool:\n"
            "    return isinstance(amount, int) and amount > 0\n",
            encoding="utf-8",
        )
        (repo / "src" / "service.py").write_text(
            "from src.guard import enforce_positive\n\n"
            "def credit(balance: int, amount: int) -> int:\n"
            "    if not enforce_positive(amount):\n"
            "        raise ValueError('bad amount')\n"
            "    return balance + amount\n",
            encoding="utf-8",
        )
        self._init_git_repo(repo)

        rc, _ = _run_cli(["init", str(repo), "--in-place", "--run-id", "run-hooks", "--json"], self.ajar_home)
        self.assertEqual(rc, EXIT_OK)
        rc, surf = _run_cli(
            [
                "surface",
                "add",
                "--run",
                "run-hooks",
                "--name",
                "credit_api",
                "--kind",
                "http",
                "--subsystem",
                "src",
                "--locus",
                "src/service.py:3",
                "--priority",
                "high",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc, EXIT_OK)
        self.assertEqual(surf["hooks_triggered"], [])

        rc, t1 = _run_cli(
            [
                "task",
                "add",
                "--run",
                "run-hooks",
                "--kind",
                "investigate",
                "--surface",
                str(surf["surface_id"]),
                "--subsystem",
                "src",
                "--locus",
                "src/service.py:3",
                "--title",
                "Audit credit service",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc, EXIT_OK)

        conn = open_run_db("run-hooks", ajar_home=self.ajar_home)
        try:
            ctx_plain = render_task_context(conn, str(t1["task_id"]))
        finally:
            conn.close()
        self.assertEqual(ctx_plain["active_hooks_count"], 0)
        self.assertNotIn("Active Epistemic Hooks", str(ctx_plain["rendered"]))
        prefix_before = ctx_plain["certified_prefix"]

        # Register a guarded inner primitive -> triggers H1_GUARD_SYMMETRY and spawns inside_out guard task.
        rc, prim = _run_cli(
            [
                "primitive",
                "add",
                "--run",
                "run-hooks",
                "--surface",
                str(surf["surface_id"]),
                "--locus",
                "src/service.py:6",
                "--kind",
                "unchecked_add",
                "--preconditions",
                "caller bypasses enforce_positive",
                "--postconditions",
                "negative credit reduces balance",
                "--guarded-by",
                "src/guard.py:1",
                "--guard-assumption",
                "enforce_positive blocks non-positive integers",
                "--evidence-cmd",
                "python3 -c 'print(1)'",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc, EXIT_OK)
        self.assertIn("H1_GUARD_SYMMETRY", prim["hooks_triggered"])  # type: ignore[arg-type]

        # Lease the auto-spawned guard task; verify prefix byte-identity and mandatory Kill Rule in Task Delta.
        rc, lease1 = _run_cli(["task", "lease", "--run", "run-hooks", "--worker", "w1"], self.ajar_home)
        self.assertEqual(rc, EXIT_OK)
        leased_obj = lease1["leased"]  # type: ignore[index]
        self.assertIsNotNone(leased_obj)
        guard_tid = str(leased_obj["task_id"])  # type: ignore[index]

        conn = open_run_db("run-hooks", ajar_home=self.ajar_home)
        try:
            ctx_hook = render_task_context(conn, guard_tid)
        finally:
            conn.close()
        self.assertEqual(ctx_hook["certified_prefix"], prefix_before)
        self.assertGreaterEqual(int(ctx_hook["active_hooks_count"]), 1)
        self.assertIn("H1_GUARD_SYMMETRY", str(ctx_hook["task_delta"]))
        self.assertIn("Kill Rule:", str(ctx_hook["task_delta"]))

        # GAP-01 regression test: adding an `open` chain task must NOT allow premature `task dry` on t1!
        rc, _ = _run_cli(
            [
                "task",
                "add",
                "--run",
                "run-hooks",
                "--kind",
                "chain",
                "--subsystem",
                "src",
                "--locus",
                "src/service.py:6",
                "--title",
                "Unexecuted chain task",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc, EXIT_OK)
        rc_premature, _ = _run_cli(
            [
                "task",
                "dry",
                str(t1["task_id"]),
                "--run",
                "run-hooks",
                "--worker",
                "w1",
                "--locus",
                "src/guard.py:1",
                "--control",
                "enforce_positive blocks negative values at entry",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_premature, EXIT_GATE_BLOCKED)

        # Once the guard audit task on `src/guard.py:1` closes `dry`, `t1` can close `dry` and H1 hook is consumed.
        rc_gdry, _ = _run_cli(
            [
                "task",
                "dry",
                guard_tid,
                "--run",
                "run-hooks",
                "--worker",
                "w1",
                "--locus",
                "src/guard.py:1",
                "--control",
                "enforce_positive enforces strict positive int check without wraparound",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_gdry, EXIT_OK)

        rc_t1_dry, _ = _run_cli(
            [
                "task",
                "dry",
                str(t1["task_id"]),
                "--run",
                "run-hooks",
                "--worker",
                "w1",
                "--locus",
                "src/guard.py:1",
                "--control",
                "upstream guard verified dry in dedicated guard audit task",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_t1_dry, EXIT_OK)

        rc_hlist, hlist = _run_cli(["hooks", "list", "--run", "run-hooks", "--status", "consumed"], self.ajar_home)
        self.assertEqual(rc_hlist, EXIT_OK)
        self.assertGreaterEqual(len(hlist["epistemic_hooks"]), 1)  # type: ignore[arg-type]

    def test_capability_bridge_stage_context_helper_and_chain_causal_ablation(self) -> None:
        repo = self.tmp_path / "chain-app"
        (repo / "auth").mkdir(parents=True)
        (repo / "billing").mkdir(parents=True)
        (repo / "auth" / "skew.py").write_text("SKEW_ENABLED = True\n", encoding="utf-8")
        (repo / "billing" / "settle.py").write_text(
            "import sys\n"
            "if __name__ == '__main__':\n"
            "    mode = sys.argv[1]\n"
            "    sys.exit(1 if mode == 'skew_and_drift' else 0)\n",
            encoding="utf-8",
        )
        self._init_git_repo(repo)

        rc, _ = _run_cli(["init", str(repo), "--run-id", "run-chain", "--json"], self.ajar_home)
        self.assertEqual(rc, EXIT_OK)

        rc, p1 = _run_cli(
            [
                "primitive",
                "add",
                "--run",
                "run-chain",
                "--locus",
                "auth/skew.py:1",
                "--kind",
                "header_skew",
                "--preconditions",
                "unauthenticated request",
                "--postconditions",
                "sets state:skew",
                "--provides-tags",
                "state:skew",
                "--evidence-cmd",
                "python3 -c 'print(1)'",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc, EXIT_OK)

        rc, p2 = _run_cli(
            [
                "primitive",
                "add",
                "--run",
                "run-chain",
                "--locus",
                "billing/settle.py:1",
                "--kind",
                "drift_commit",
                "--preconditions",
                "requires state:skew",
                "--postconditions",
                "commits unauthorized settlement",
                "--requires-tags",
                "state:skew",
                "--provides-tags",
                "impact:settle_bypass",
                "--evidence-cmd",
                "python3 -c 'print(1)'",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc, EXIT_OK)
        self.assertIn("H4_TYPED_STATE_BRIDGE", p2["hooks_triggered"])  # type: ignore[arg-type]

        p1_id = str(p1["primitive_id"])
        p2_id = str(p2["primitive_id"])

        # Promote StageContext helpers for p1 and p2 outside slot-<k>.
        h1_file = self.tmp_path / "helper_s1.py"
        h1_file.write_text(
            f"def step1(ctx):\n"
            f"    ctx.state['s1'] = not ctx.is_ablated('{p1_id}')\n",
            encoding="utf-8",
        )
        h2_file = self.tmp_path / "helper_s2.py"
        h2_file.write_text(
            f"def step2(ctx):\n"
            f"    ctx.state['s2'] = not ctx.is_ablated('{p2_id}')\n",
            encoding="utf-8",
        )

        rc, h1_res = _run_cli(
            ["primitive", "promote-helper", p1_id, "--run", "run-chain", "--file", str(h1_file), "--callable", "step1"],
            self.ajar_home,
        )
        self.assertEqual(rc, EXIT_OK)
        rc, h2_res = _run_cli(
            ["primitive", "promote-helper", p2_id, "--run", "run-chain", "--file", str(h2_file), "--callable", "step2"],
            self.ajar_home,
        )
        self.assertEqual(rc, EXIT_OK)

        rdir = run_dir_for("run-chain", self.ajar_home)
        h1_installed = rdir / str(h1_res["rel_helper_path"])
        self.assertTrue(h1_installed.is_file())
        self.assertEqual(stat.S_IMODE(h1_installed.stat().st_mode), 0o444)

        imp1 = str(h1_res["import_path"])
        imp2 = str(h2_res["import_path"])
        chain_poc = (
            f"{sys.executable} -c \""
            f"from ajar_helpers import StageContext; "
            f"import {imp1} as m1, {imp2} as m2, subprocess, sys; "
            f"ctx = StageContext.from_env(); m1.step1(ctx); m2.step2(ctx); "
            f"mode = 'skew_and_drift' if (ctx.state.get('s1') and ctx.state.get('s2')) else 'benign'; "
            f"sys.exit(subprocess.call([sys.executable, 'billing/settle.py', mode]))\""
        )
        chain_ctrl = f"{sys.executable} billing/settle.py benign"

        # Genuine 2-step chain passes full + control + per-step causal ablation!
        rc_ok, ch_ok = _run_cli(
            [
                "chain",
                "propose",
                "--run",
                "run-chain",
                "--title",
                "Auth skew -> Billing drift settlement bypass",
                "--steps",
                f"{p1_id},{p2_id}",
                "--poc-cmd",
                chain_poc,
                "--control-cmd",
                chain_ctrl,
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_ok, EXIT_OK)
        self.assertTrue(ch_ok["verified"])
        self.assertEqual(len(ch_ok["ablation_matrix"]), 2)  # type: ignore[arg-type]

        # Adding a redundant 3rd primitive `p_pad` MUST fail causal ablation!
        rc, p_pad = _run_cli(
            [
                "primitive",
                "add",
                "--run",
                "run-chain",
                "--locus",
                "auth/skew.py:1",
                "--kind",
                "noop_pad",
                "--preconditions",
                "none",
                "--postconditions",
                "none",
                "--evidence-cmd",
                "python3 -c 'print(1)'",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc, EXIT_OK)
        pad_id = str(p_pad["primitive_id"])
        rc_pad, ch_pad = _run_cli(
            [
                "chain",
                "propose",
                "--run",
                "run-chain",
                "--title",
                "Padded 3-step chain",
                "--steps",
                f"{p1_id},{p2_id},{pad_id}",
                "--poc-cmd",
                chain_poc,
                "--control-cmd",
                chain_ctrl,
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_pad, EXIT_GATE_BLOCKED)
        self.assertFalse(ch_pad["verified"])
        self.assertIn(pad_id, str(ch_pad["reason"]))

    def test_container_loopback_socket_guard_blocks_external_egress(self) -> None:
        from ajar.repro_compose import ensure_helpers_runtime

        rdir = self.tmp_path / "guard-run"
        helpers_dir = ensure_helpers_runtime(rdir)
        env = dict(os.environ)
        env["PYTHONPATH"] = str(helpers_dir)
        env["AJAR_BLOCK_EXTERNAL_NET"] = "1"

        # Non-loopback connect must raise PermissionError immediately without touching network.
        ext_proc = subprocess.run(
            [
                sys.executable,
                "-c",
                "import socket, sys\n"
                "s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
                "try:\n"
                "    s.connect(('8.8.8.8', 53))\n"
                "    sys.exit(1)\n"
                "except PermissionError:\n"
                "    sys.exit(0)\n",
            ],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(ext_proc.returncode, 0, ext_proc.stderr)

        # Loopback 127.0.0.1 bind + connect must remain allowed for local test servers.
        lo_proc = subprocess.run(
            [
                sys.executable,
                "-c",
                "import socket\n"
                "srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
                "srv.bind(('127.0.0.1', 0))\n"
                "srv.listen(1)\n"
                "port = srv.getsockname()[1]\n"
                "cli = socket.create_connection(('127.0.0.1', port), timeout=2)\n"
                "conn, _ = srv.accept()\n"
                "cli.close(); conn.close(); srv.close()\n",
            ],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(lo_proc.returncode, 0, lo_proc.stderr)

    def test_release_profile_ub_differential_h6_and_post_confirm_escalation_h5(self) -> None:
        repo = self.tmp_path / "c-sim"
        (repo / "src").mkdir(parents=True)
        # Simulated compiled source file (.c extension triggers H6_RELEASE_UB_DIFF on overflow claims)
        (repo / "src" / "quota.c").write_text(
            "/* quota check */\n"
            "int check_quota(int count, int price) {\n"
            "    int total = count * price; // BUG: signed 32-bit overflow\n"
            "    return total <= 1000;\n"
            "}\n",
            encoding="utf-8",
        )
        (repo / "src" / "sim_runner.py").write_text(
            "import pathlib, sys\n"
            "profile = sys.argv[1]  # debug | release_noop | release_wrap\n"
            "kind = sys.argv[2]     # poc | ctrl\n"
            "code = pathlib.Path('src/quota.c').read_text(encoding='utf-8')\n"
            "patched = 'checked_mul' in code\n"
            "if kind == 'ctrl' or patched:\n"
            "    sys.exit(0)\n"
            "if profile == 'debug':\n"
            "    sys.stderr.write('runtime error: signed integer overflow in quota.c\\n')\n"
            "    sys.exit(134)\n"
            "if profile == 'release_noop':\n"
            "    sys.exit(0)\n"
            "if profile == 'release_wrap':\n"
            "    sys.stdout.write('overflow_wrap unauthorized quota bypass\\n')\n"
            "    sys.exit(1)\n",
            encoding="utf-8",
        )
        self._init_git_repo(repo)

        micropatch = self.tmp_path / "quota_fix.diff"
        micropatch.write_text(
            "diff --git a/src/quota.c b/src/quota.c\n"
            "--- a/src/quota.c\n"
            "+++ b/src/quota.c\n"
            "@@ -1,5 +1,5 @@\n"
            " /* quota check */\n"
            " int check_quota(int count, int price) {\n"
            "-    int total = count * price; // BUG: signed 32-bit overflow\n"
            "+    int total = checked_mul(count, price);\n"
            "     return total <= 1000;\n"
            " }\n",
            encoding="utf-8",
        )

        rc, _ = _run_cli(["init", str(repo), "--run-id", "run-ub", "--json"], self.ajar_home)
        self.assertEqual(rc, EXIT_OK)

        rc, clm = _run_cli(
            [
                "claim",
                "propose",
                "--run",
                "run-ub",
                "--worker",
                "w-prop",
                "--title",
                "Signed int32_t overflow in check_quota",
                "--locus",
                "src/quota.c:3",
                "--mechanism",
                "Unchecked signed integer overflow wraps negative and bypasses quota cap",
                "--severity",
                "high",
                "--falsification-prediction",
                "Caller caps count and price to <= 100 before check_quota",
                "--falsification-test",
                "Inspect callers of check_quota",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc, EXIT_OK)
        cid = str(clm["claim_id"])

        rc, surv = _run_cli(
            ["claim", "survive", cid, "--run", "run-ub", "--worker", "w-fals", "--notes", "No caller bounds check"],
            self.ajar_home,
        )
        self.assertEqual(rc, EXIT_OK)
        self.assertIn("H6_RELEASE_UB_DIFF", surv["hooks_triggered"])  # type: ignore[arg-type]

        # 1) Omitting --release-cmd when H6_RELEASE_UB_DIFF is active MUST block!
        rc_no_rel, err_no_rel = _run_cli(
            [
                "claim",
                "reproduce",
                cid,
                "--run",
                "run-ub",
                "--worker",
                "w-rep",
                "--poc-cmd",
                f"{sys.executable} src/sim_runner.py debug poc",
                "--control-cmd",
                f"{sys.executable} src/sim_runner.py debug ctrl",
                "--micropatch",
                str(micropatch),
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_no_rel, EXIT_GATE_BLOCKED)
        self.assertIn("H6_RELEASE_UB_DIFF", str(err_no_rel))

        # 2) Supplying --release-cmd that exits 0 cleanly (`debug_assert_only`) on `high` severity MUST block!
        rc_dbg_only, err_dbg_only = _run_cli(
            [
                "claim",
                "reproduce",
                cid,
                "--run",
                "run-ub",
                "--worker",
                "w-rep",
                "--poc-cmd",
                f"{sys.executable} src/sim_runner.py debug poc",
                "--control-cmd",
                f"{sys.executable} src/sim_runner.py debug ctrl",
                "--release-cmd",
                f"{sys.executable} src/sim_runner.py release_noop poc",
                "--release-control-cmd",
                f"{sys.executable} src/sim_runner.py release_noop ctrl",
                "--micropatch",
                str(micropatch),
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_dbg_only, EXIT_GATE_BLOCKED)
        self.assertIn("debug_assert_only", str(err_dbg_only))

        # 3) Rescope severity to `medium` and run with `release_wrap` -> confirms `silent_wrap_escalated` + spawns H5 `escalate`!
        rc_rsc, _ = _run_cli(
            [
                "claim",
                "rescope",
                cid,
                "--run",
                "run-ub",
                "--worker",
                "w-rep",
                "--severity",
                "medium",
                "--reason",
                "Scoped standalone quota wrap to medium pending consumer escalation check",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_rsc, EXIT_OK)

        rc_ok, rep_ok = _run_cli(
            [
                "claim",
                "reproduce",
                cid,
                "--run",
                "run-ub",
                "--worker",
                "w-rep",
                "--poc-cmd",
                f"{sys.executable} src/sim_runner.py debug poc",
                "--control-cmd",
                f"{sys.executable} src/sim_runner.py debug ctrl",
                "--release-cmd",
                f"{sys.executable} src/sim_runner.py release_wrap poc",
                "--release-control-cmd",
                f"{sys.executable} src/sim_runner.py release_wrap ctrl",
                "--micropatch",
                str(micropatch),
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_ok, EXIT_OK)
        repro_dict = rep_ok["reproduction"]  # type: ignore[index]
        self.assertEqual(repro_dict["ub_divergence_class"], "silent_wrap_escalated")  # type: ignore[index]
        self.assertIn("post_confirm_escalation", rep_ok)

    def test_hardened_9arm_patch_verify_baseline_variants_and_arm9_revert(self) -> None:
        repo = self.tmp_path / "patch-app"
        (repo / "src").mkdir(parents=True)
        (repo / "src" / "auth.py").write_text(
            "import sys\n\n"
            "def is_admin(role: str) -> bool:\n"
            "    return role.strip().lower().startswith('admin')\n\n"
            "if __name__ == '__main__':\n"
            "    arg = sys.argv[1]\n"
            "    if arg == 'suite':\n"
            "        # Pre-existing unrelated broken test on clean HEAD (`AISLE` baseline case)\n"
            "        print('FAIL test_legacy_unrelated')\n"
            "        sys.exit(1)\n"
            "    res = is_admin(arg)\n"
            "    if arg.strip().lower() != 'admin' and res:\n"
            "        sys.exit(1)  # bypass triggered!\n"
            "    if arg == 'admin' and not res:\n"
            "        sys.exit(2)\n"
            "    sys.exit(0)\n",
            encoding="utf-8",
        )
        self._init_git_repo(repo)

        fix_patch = self.tmp_path / "prod_fix.diff"
        fix_patch.write_text(
            "diff --git a/src/auth.py b/src/auth.py\n"
            "--- a/src/auth.py\n"
            "+++ b/src/auth.py\n"
            "@@ -1,6 +1,6 @@\n"
            " import sys\n"
            " \n"
            " def is_admin(role: str) -> bool:\n"
            "-    return role.strip().lower().startswith('admin')\n"
            "+    return role.strip() == 'admin'\n"
            " \n"
            " if __name__ == '__main__':\n",
            encoding="utf-8",
        )

        rc, _ = _run_cli(["init", str(repo), "--run-id", "run-fix", "--json"], self.ajar_home)
        self.assertEqual(rc, EXIT_OK)
        rc, clm = _run_cli(
            [
                "claim",
                "propose",
                "--run",
                "run-fix",
                "--worker",
                "w1",
                "--title",
                "Prefix role check bypass in is_admin",
                "--locus",
                "src/auth.py:4",
                "--mechanism",
                "startswith('admin') accepts admin_guest and ADMIN_shadow",
                "--severity",
                "critical",
                "--falsification-prediction",
                "Router restricts role values to enum before is_admin",
                "--falsification-test",
                "Run src/auth.py admin_guest",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc, EXIT_OK)
        cid = str(clm["claim_id"])
        rc, _ = _run_cli(["claim", "survive", cid, "--run", "run-fix", "--worker", "w2", "--notes", "confirmed"], self.ajar_home)
        self.assertEqual(rc, EXIT_OK)
        rc, rep = _run_cli(
            [
                "claim",
                "reproduce",
                cid,
                "--run",
                "run-fix",
                "--worker",
                "w2",
                "--poc-cmd",
                f"{sys.executable} src/auth.py admin_guest",
                "--control-cmd",
                f"{sys.executable} src/auth.py admin",
                "--micropatch",
                str(fix_patch),
            ],
            self.ajar_home,
        )
        self.assertEqual(rc, EXIT_OK)
        fid = str(rep["finding_id"])

        # 1) Variants that NEVER trigger on clean HEAD (noop commands) MUST fail Arm 6!
        rc_noop, res_noop = _run_cli(
            [
                "patch",
                "verify",
                fid,
                "--run",
                "run-fix",
                "--patch",
                str(fix_patch),
                "--suite-cmd",
                f"{sys.executable} src/auth.py suite",
                "--variant-cmd",
                f"{sys.executable} src/auth.py guest_1",
                "--variant-cmd",
                f"{sys.executable} src/auth.py guest_2",
                "--variant-cmd",
                f"{sys.executable} src/auth.py guest_3",
                "--caller-audit",
                "Verified all callers handle boolean return without nil deref",
                "--sibling-audit",
                "Verified CLI entrypoint shares is_admin check",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_noop, EXIT_GATE_BLOCKED)
        self.assertIn("zero --variant-cmd commands triggered", str(res_noop["reason"]))

        # 2) Real variants + pre-existing broken suite baseline diff + caller/sibling cmds + Arm 9 git apply -R pass!
        rc_pass, res_pass = _run_cli(
            [
                "patch",
                "verify",
                fid,
                "--run",
                "run-fix",
                "--patch",
                str(fix_patch),
                "--suite-cmd",
                f"{sys.executable} src/auth.py suite",
                "--variant-cmd",
                f"{sys.executable} src/auth.py admin_v2",
                "--variant-cmd",
                f"{sys.executable} src/auth.py ADMIN_UPPER",
                "--variant-cmd",
                f"{sys.executable} src/auth.py ' admin_space '",
                "--caller-audit",
                "Verified all callers handle boolean return without nil deref",
                "--sibling-audit",
                "Verified CLI entrypoint shares is_admin check",
                "--caller-cmd",
                f"{sys.executable} src/auth.py viewer",
                "--sibling-cmd",
                f"{sys.executable} src/auth.py admin",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_pass, EXIT_OK, str(res_pass))
        self.assertTrue(res_pass["passed"])
        self.assertEqual(res_pass["remediation_state"], "maintainer_patched")
        arms = res_pass["arms"]  # type: ignore[index]
        self.assertEqual(arms["arm5_full_suite"]["baseline_exit_code"], 1)  # type: ignore[index]
        self.assertEqual(arms["arm5_full_suite"]["new_regressions"], [])  # type: ignore[index]
        self.assertTrue(arms["arm9_revert_poc"]["arm_passed"])  # type: ignore[index]

    def test_pr_diff_sync_slices_coverage_checkpoint_instrument_config_gate_and_soliloquy(self) -> None:
        repo = self.tmp_path / "pr-app"
        (repo / "src").mkdir(parents=True)
        (repo / "docs").mkdir(parents=True)
        (repo / "docs" / "SECURITY.md").write_text(
            "All admin endpoints enforce strict mTLS authentication in router.\n",
            encoding="utf-8",
        )
        (repo / "src" / "auth.py").write_text(
            "import sys\n"
            "def check(tok: str) -> bool:\n"
            "    return tok.startswith('ok')\n"
            "if __name__ == '__main__':\n"
            "    t = sys.argv[1]\n"
            "    sys.exit(1 if (t != 'ok' and check(t)) else 0)\n",
            encoding="utf-8",
        )
        (repo / "src" / "guard_kept.py").write_text(
            "def safe_kept(x: int) -> bool:\n    return x >= 0\n",
            encoding="utf-8",
        )
        (repo / "src" / "guard_edited.py").write_text(
            "def guard_v1(x: int) -> bool:\n    return x >= 0\n",
            encoding="utf-8",
        )
        self._init_git_repo(repo)

        fix_auth = self.tmp_path / "fix_auth.diff"
        fix_auth.write_text(
            "diff --git a/src/auth.py b/src/auth.py\n"
            "--- a/src/auth.py\n"
            "+++ b/src/auth.py\n"
            "@@ -1,4 +1,4 @@\n"
            " import sys\n"
            " def check(tok: str) -> bool:\n"
            "-    return tok.startswith('ok')\n"
            "+    return tok == 'ok'\n"
            " if __name__ == '__main__':\n",
            encoding="utf-8",
        )

        # Baseline run: 1 reproduced finding + 1 kept dry guard + 1 dry guard that PR will edit
        rc, _ = _run_cli(["init", str(repo), "--run-id", "run-base", "--json"], self.ajar_home)
        self.assertEqual(rc, EXIT_OK)

        # Check FTS5 untrusted target doc provenance tag
        conn_b = open_run_db("run-base", ajar_home=self.ajar_home)
        try:
            index_target_oracles(conn_b, repo)
            hits = query_oracle(conn_b, "intent", "mTLS")
        finally:
            conn_b.close()
        self.assertTrue(any("[UNTRUSTED_TARGET_DOC: verify in code]" in str(h["snippet"]) for h in hits))

        rc, tk_kept = _run_cli(
            ["task", "add", "--run", "run-base", "--kind", "investigate", "--locus", "src/guard_kept.py:1", "--title", "Kept guard"],
            self.ajar_home,
        )
        self.assertEqual(rc, EXIT_OK)
        rc, _ = _run_cli(
            [
                "task",
                "dry",
                str(tk_kept["task_id"]),
                "--run",
                "run-base",
                "--worker",
                "w1",
                "--locus",
                "src/guard_kept.py:1",
                "--control",
                "safe_kept enforces non-negative integer bound",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc, EXIT_OK)

        rc, tk_edit = _run_cli(
            ["task", "add", "--run", "run-base", "--kind", "investigate", "--locus", "src/guard_edited.py:1", "--title", "Edited guard"],
            self.ajar_home,
        )
        self.assertEqual(rc, EXIT_OK)
        rc, _ = _run_cli(
            [
                "task",
                "dry",
                str(tk_edit["task_id"]),
                "--run",
                "run-base",
                "--worker",
                "w1",
                "--locus",
                "src/guard_edited.py:1",
                "--control",
                "guard_v1 enforces non-negative integer bound",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc, EXIT_OK)

        rc, clm_b = _run_cli(
            [
                "claim",
                "propose",
                "--run",
                "run-base",
                "--worker",
                "w1",
                "--title",
                "Token prefix bug",
                "--locus",
                "src/auth.py:3",
                "--mechanism",
                "startswith('ok') accepts ok_attacker",
                "--severity",
                "high",
                "--falsification-prediction",
                "Caller validates exact token length",
                "--falsification-test",
                "Run src/auth.py ok_attacker",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc, EXIT_OK)
        cid_b = str(clm_b["claim_id"])
        _run_cli(["claim", "survive", cid_b, "--run", "run-base", "--worker", "w2", "--notes", "ok"], self.ajar_home)

        # Trigger 2 unchanged repro failures -> `needs_instrumentation`, then unlock via `ajar claim instrument`!
        for _ in range(2):
            rc_fail, _ = _run_cli(
                [
                    "claim",
                    "reproduce",
                    cid_b,
                    "--run",
                    "run-base",
                    "--worker",
                    "w2",
                    "--poc-cmd",
                    f"{sys.executable} src/auth.py ok",
                    "--control-cmd",
                    f"{sys.executable} src/auth.py ok",
                    "--micropatch",
                    str(fix_auth),
                ],
                self.ajar_home,
            )
            self.assertEqual(rc_fail, EXIT_GATE_BLOCKED)

        rc_inst, inst_res = _run_cli(
            [
                "claim",
                "instrument",
                cid_b,
                "--run",
                "run-base",
                "--worker",
                "w2",
                "--probe-cmd",
                f"{sys.executable} -c \"print('trace check(ok_bad)=', True)\"",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_inst, EXIT_OK)
        self.assertEqual(inst_res["status"], "survived_falsify")

        rc_rep, _ = _run_cli(
            [
                "claim",
                "reproduce",
                cid_b,
                "--run",
                "run-base",
                "--worker",
                "w2",
                "--poc-cmd",
                f"{sys.executable} src/auth.py ok_bad",
                "--control-cmd",
                f"{sys.executable} src/auth.py ok",
                "--micropatch",
                str(fix_auth),
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_rep, EXIT_OK)

        # Commit PR fixing src/auth.py and modifying src/guard_edited.py!
        (repo / "src" / "auth.py").write_text(
            "import sys\n"
            "def check(tok: str) -> bool:\n"
            "    return tok == 'ok'\n"
            "if __name__ == '__main__':\n"
            "    t = sys.argv[1]\n"
            "    sys.exit(1 if (t != 'ok' and check(t)) else 0)\n",
            encoding="utf-8",
        )
        (repo / "src" / "guard_edited.py").write_text(
            "def guard_v1(x: int) -> bool:\n    return x >= -1  # modified in PR!\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "PR fix auth and edit guard"], cwd=repo, check=True)

        # Initialize incremental PR run (`--diff HEAD~1..HEAD --parent-run run-base`)!
        rc_pr, info_pr = _run_cli(
            [
                "init",
                str(repo),
                "--diff",
                "HEAD~1..HEAD",
                "--parent-run",
                "run-base",
                "--run-id",
                "run-pr",
                "--json",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_pr, EXIT_OK)
        ds = info_pr["diff_sync"]  # type: ignore[index]
        self.assertEqual(len(ds["closed_findings"]), 1)  # type: ignore[arg-type,index]
        self.assertEqual(len(ds["kept_dry_tasks"]), 1)  # type: ignore[arg-type,index]
        self.assertEqual(len(ds["invalidated_guards"]), 1)  # type: ignore[arg-type,index]

        # Test map --slice-cap, coverage record, task checkpoint, and config_gated claim probe
        rc_map, mp = _run_cli(["map", "--run", "run-pr", "--slice-cap", "20", "--json"], self.ajar_home)
        self.assertEqual(rc_map, EXIT_OK)
        self.assertGreaterEqual(int(mp["slice_count"]), 1)  # type: ignore[arg-type]
        self.assertLessEqual(len(str(mp["skeleton_md"]).encode("utf-8")), 1024)

        rc_cov, cov = _run_cli(
            ["coverage", "record", "src/guard_edited.py", "--start-line", "1", "--end-line", "2", "--run", "run-pr"],
            self.ajar_home,
        )
        self.assertEqual(rc_cov, EXIT_OK)
        self.assertTrue(str(cov["file_sha256"]))

        rc_tl, tlist = _run_cli(["task", "list", "--run", "run-pr"], self.ajar_home)
        self.assertEqual(rc_tl, EXIT_OK)
        open_tid = str([t for t in tlist["tasks"] if t["status"] == "open"][0]["task_id"])  # type: ignore[index]
        rc_chk, chk = _run_cli(
            [
                "task",
                "checkpoint",
                open_tid,
                "--run",
                "run-pr",
                "--worker",
                "w-pr",
                "--state-json",
                '{"reviewed":"guard_edited.py:1-2"}',
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_chk, EXIT_OK)
        self.assertEqual(chk["checkpoint"]["reviewed"], "guard_edited.py:1-2")  # type: ignore[index]

        rc_cg_p, cg_clm = _run_cli(
            [
                "claim",
                "propose",
                "--run",
                "run-pr",
                "--worker",
                "w1",
                "--title",
                "Negative bound allowed when LEGACY_NEG=1",
                "--locus",
                "src/guard_edited.py:2",
                "--mechanism",
                "guard_v1 permits -1",
                "--severity",
                "medium",
                "--falsification-prediction",
                "Feature flag LEGACY_NEG is off by default",
                "--falsification-test",
                "Check config defaults",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_cg_p, EXIT_OK)
        rc_cg_f, cg_res = _run_cli(
            [
                "claim",
                "falsify",
                str(cg_clm["claim_id"]),
                "--run",
                "run-pr",
                "--worker",
                "w2",
                "--config-gate",
                "LEGACY_NEG == 1",
                "--notes",
                "Default off unless tenant enables LEGACY_NEG",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_cg_f, EXIT_OK)
        self.assertEqual(cg_res["status"], "config_gated")
        self.assertTrue(str(cg_res["probe_task_id"]).startswith("task-"))

        # Verify anti-soliloquy guard catches simulated shell transcripts with 0 state mutations
        flagged, reason = detect_soliloquy_transcript(
            "Here is what happened:\n```bash\n$ gdb ./app\n```\n", state_mutations_recorded=0
        )
        self.assertTrue(flagged)
        self.assertIn("Fabricated shell/debugger transcript", reason)
        flagged_real, _ = detect_soliloquy_transcript(
            "Here is what happened:\n```bash\n$ gdb ./app\n```\n", state_mutations_recorded=1
        )
        self.assertFalse(flagged_real)

    def test_uncapped_campaign_brief_and_cohesive_15k_slice_cap(self) -> None:
        repo = self.tmp_path / "large_c_repo"
        repo.mkdir(parents=True, exist_ok=True)
        # Write a 5,200-line cohesive C state machine (previously split at 3,500 LoC!)
        c_lines = ["int merge_step(int x) { return x + 1; }"] + [f"// state line {i}" for i in range(5198)] + ["int merge_finish(int x) { return merge_step(x); }"]
        (repo / "merge_ort.c").write_text("\n".join(c_lines) + "\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "test@ajar.local"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "Ajar Test"], cwd=repo, check=True)
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "initial 5200-line C file"], cwd=repo, check=True)

        brief_md = self.tmp_path / "campaign_brief.md"
        brief_md.write_text(
            "# Lead Orchestrator Campaign Brief\n"
            "## Critical-Class Catalog\n"
            "- C1: Untrusted repository RCE or out-of-worktree write.\n"
            "- C5: Unattended server/CI queue exploitation.\n",
            encoding="utf-8",
        )

        rc_init, info = _run_cli(
            [
                "init",
                str(repo),
                "--in-place",
                "--uncapped",
                "--brief-file",
                str(brief_md),
                "--goal",
                "Find and reproduce untrusted repo RCE or arbitrary write.",
                "--run-id",
                "run-uncapped",
                "--json",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_init, EXIT_OK)
        self.assertEqual(info["pricing_mode"], "uncapped_research")  # type: ignore[index]
        self.assertEqual(float(info["budget_usd"]), 0.0)  # type: ignore[arg-type,index]
        self.assertTrue(str(info["brief_path"]).endswith("brief.md"))  # type: ignore[index]

        # Default `ajar map` keeps 5,200-line `merge_ort.c` intact as 1 cohesive slice (`slice_cap=15000`)
        rc_map, mp = _run_cli(["map", "--run", "run-uncapped", "--json"], self.ajar_home)
        self.assertEqual(rc_map, EXIT_OK)
        self.assertEqual(int(mp["slice_cap"]), 15000)  # type: ignore[arg-type,index]
        self.assertEqual(int(mp["slice_count"]), 1)  # type: ignore[arg-type,index]
        self.assertEqual(mp["call_slices"][0]["seed_locus"], "merge_ort.c:1")  # type: ignore[index]

        # `ajar brief` returns the full Lead Orchestrator brief, while worker `ajar context` stays unbloated
        rc_brf, brf = _run_cli(["brief", "--run", "run-uncapped", "--json"], self.ajar_home)
        self.assertEqual(rc_brf, EXIT_OK)
        self.assertTrue(brf["has_campaign_brief"])  # type: ignore[index]
        self.assertIn("Critical-Class Catalog", str(brf["brief_markdown"]))  # type: ignore[index]

        rc_surf, surf = _run_cli(
            [
                "surface",
                "add",
                "--run",
                "run-uncapped",
                "--name",
                "merge_ort",
                "--kind",
                "parser",
                "--subsystem",
                "merge",
                "--locus",
                "merge_ort.c:1",
                "--priority",
                "high",
                "--trust-boundary",
                "untrusted tree -> merge state",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_surf, EXIT_OK)
        sid = str(surf["surface_id"])  # type: ignore[index]
        rc_tsk, tsk = _run_cli(
            [
                "task",
                "add",
                "--run",
                "run-uncapped",
                "--kind",
                "investigate",
                "--title",
                "Audit merge_ort state machine",
                "--surface",
                sid,
                "--locus",
                "merge_ort.c:1",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_tsk, EXIT_OK)
        tid = str(tsk["task_id"])  # type: ignore[index]

        rc_ctx, ctx = _run_cli(["context", "--task", tid, "--run", "run-uncapped", "--json"], self.ajar_home)
        self.assertEqual(rc_ctx, EXIT_OK)
        self.assertNotIn("Critical-Class Catalog", str(ctx["rendered"]))  # type: ignore[index]

        # Record $250.00 explore spend on uncapped run -> zero budget throttling and gross_margin_floor_pass=True
        rc_sp, _ = _run_cli(
            [
                "spend",
                "add",
                "--run",
                "run-uncapped",
                "--worker",
                "w1",
                "--phase",
                "explore",
                "--surface",
                sid,
                "--cost-usd",
                "250.0",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_sp, EXIT_OK)
        rc_stat, stat = _run_cli(["status", "--run", "run-uncapped"], self.ajar_home)
        self.assertEqual(rc_stat, EXIT_OK)
        self.assertTrue(stat["has_campaign_brief"])  # type: ignore[index]
        self.assertTrue(stat["economics"]["gross_margin_floor_pass"])  # type: ignore[index]

    def test_adaptive_threat_model_auto_violation_and_surface_escalation(self) -> None:
        repo = self.tmp_path / "tm_repo"
        repo.mkdir(parents=True, exist_ok=True)
        (repo / "apply.c").write_text("int check_path(const char *p) { return 0; }\n", encoding="utf-8")
        (repo / "hooks.c").write_text("int run_hook(const char *h) { return 0; }\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "test@ajar.local"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "Ajar Test"], cwd=repo, check=True)
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init tm repo"], cwd=repo, check=True)

        rc_init, _ = _run_cli(
            [
                "init",
                str(repo),
                "--in-place",
                "--uncapped",
                "--goal",
                "Prove clone or apply boundary escape to code execution.",
                "--run-id",
                "run-tm",
                "--json",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_init, EXIT_OK)

        # 1. Campaign-start Threat Model synthesis (`rev 1`)
        rc_tm, tm_out = _run_cli(
            [
                "threat-model",
                "set",
                "--run",
                "run-tm",
                "--principals",
                "untrusted remote repo, malicious submodule",
                "--assets",
                "host worktree outside repo, .git/hooks execution",
                "--consumer-tiers",
                "developer CLI clone, CI runner",
                "--summary",
                "Untrusted trees/patches must never write inside .git/ or execute hooks.",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_tm, EXIT_OK)
        self.assertEqual(int(tm_out["revision"]), 1)  # type: ignore[arg-type,index]

        # 2. Register upstream `apply` surface and downstream `hooks` surface (`medium` while boundary holds)
        _, surf_up = _run_cli(
            [
                "surface",
                "add",
                "--run",
                "run-tm",
                "--name",
                "apply_path_gate",
                "--kind",
                "parser",
                "--subsystem",
                "apply",
                "--locus",
                "apply.c:1",
                "--priority",
                "high",
                "--trust-boundary",
                "untrusted patch -> verify_path",
            ],
            self.ajar_home,
        )
        _, surf_down = _run_cli(
            [
                "surface",
                "add",
                "--run",
                "run-tm",
                "--name",
                "git_hooks_exec",
                "--kind",
                "dispatcher",
                "--subsystem",
                "hooks",
                "--locus",
                "hooks.c:1",
                "--priority",
                "medium",
                "--trust-boundary",
                "assumed local-only .git/hooks -> execve",
            ],
            self.ajar_home,
        )
        sid_up = str(surf_up["surface_id"])  # type: ignore[index]
        sid_down = str(surf_down["surface_id"])  # type: ignore[index]

        # Park a downstream hook-execution task until `.git/` write protection breaks
        _, tsk_down = _run_cli(
            [
                "task",
                "add",
                "--run",
                "run-tm",
                "--kind",
                "investigate",
                "--title",
                "Trace hook execution post-.git write",
                "--surface",
                sid_down,
                "--locus",
                "hooks.c:1",
            ],
            self.ajar_home,
        )
        tid_down = str(tsk_down["task_id"])  # type: ignore[index]
        _, ctx_before = _run_cli(["context", "--task", tid_down, "--run", "run-tm", "--json"], self.ajar_home)
        prefix_before = str(ctx_before["certified_prefix"])  # type: ignore[index]

        _run_cli(["task", "lease", "--run", "run-tm", "--worker", "w1", "--kind", "investigate"], self.ajar_home)
        _run_cli(
            [
                "task",
                "block",
                tid_down,
                "--run",
                "run-tm",
                "--worker",
                "w1",
                "--predicate",
                "Requires primitive writing inside .git/",
                "--check-locus",
                "apply.c:1",
            ],
            self.ajar_home,
        )

        # Register falsifiable threat assumption linking `fs:dotgit_escape` -> `sid_down` (`critical`)
        rc_add_a, assump = _run_cli(
            [
                "threat-model",
                "assumption-add",
                "--run",
                "run-tm",
                "--subsystem",
                "hooks",
                "--trust-boundary",
                ".git/hooks local-only boundary",
                "--assumption",
                "verify_path blocks any patch or tree entry targeting .git/",
                "--check-locus",
                "apply.c:1",
                "--invalidated-by-tags",
                "fs:dotgit_escape",
                "--dependent-surface",
                sid_down,
                "--escalate-priority",
                "critical",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_add_a, EXIT_OK)
        aid = str(assump["assumption_id"])  # type: ignore[index]

        # 3. Upstream worker discovers a `.git` case-folding/symlink write primitive -> auto-violates assumption!
        rc_prim, _ = _run_cli(
            [
                "primitive",
                "add",
                "--run",
                "run-tm",
                "--surface",
                sid_up,
                "--locus",
                "apply.c:1",
                "--kind",
                "arbitrary_dotgit_write",
                "--preconditions",
                "crafted symlink + rename patch",
                "--postconditions",
                "writes attacker payload inside .git/hooks/",
                "--provides-tags",
                "fs:dotgit_escape",
                "--evidence-cmd",
                "true",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_prim, EXIT_OK)

        # Verify: revision bumped to 2, assumption is `violated`, `sid_down` upgraded `medium -> critical`,
        # parked task `tid_down` auto-unblocked to `open`, and `Certified Run Prefix` remained 100% byte-identical!
        _, tm_show = _run_cli(["threat-model", "show", "--run", "run-tm", "--json"], self.ajar_home)
        self.assertEqual(int(tm_show["threat_model"]["revision"]), 2)  # type: ignore[arg-type,index]
        self.assertEqual(int(tm_show["counts"]["violated"]), 1)  # type: ignore[arg-type,index]
        self.assertEqual(tm_show["assumptions"][0]["assumption_id"], aid)  # type: ignore[index]
        self.assertEqual(tm_show["assumptions"][0]["status"], "violated")  # type: ignore[index]

        _, surfs_after = _run_cli(["surface", "list", "--run", "run-tm"], self.ajar_home)
        down_row = [s for s in surfs_after["surfaces"] if s["surface_id"] == sid_down][0]  # type: ignore[index]
        self.assertEqual(down_row["priority"], "critical")

        _, ctx_after = _run_cli(["context", "--task", tid_down, "--run", "run-tm", "--json"], self.ajar_home)
        self.assertEqual(str(ctx_after["certified_prefix"]), prefix_before)  # type: ignore[index]
        self.assertIn("Adaptive Threat-Model Shift", str(ctx_after["task_delta"]))  # type: ignore[index]

        _, st = _run_cli(["status", "--run", "run-tm"], self.ajar_home)
        self.assertEqual(int(st["threat_model_revision"]), 2)  # type: ignore[arg-type,index]
        self.assertEqual(int(st["violated_threat_assumptions"]), 1)  # type: ignore[arg-type,index]

        _, g_out = _run_cli(["export-graph", "--run", "run-tm"], self.ajar_home)
        self.assertEqual(int(g_out["summary"]["threat_assumptions_violated"]), 1)  # type: ignore[arg-type,index]


if __name__ == "__main__":
    unittest.main()
