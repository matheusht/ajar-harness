"""Tests for mechanical architecture guardrails (`tools/arch_lint.py`) and CLI-vs-MCP service parity."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from types import ModuleType
from unittest import mock

from ajar.cli import main as cli_main
from ajar.db import open_run_db
from ajar.domain import AjarError, InvalidTransitionError
from ajar.mcp import dispatch_mcp_tool

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_arch_lint() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ajar_arch_lint", REPO_ROOT / "tools" / "arch_lint.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ajar_arch_lint"] = mod
    spec.loader.exec_module(mod)
    return mod


def _run_cli(argv: list[str]) -> tuple[int, dict[str, object]]:
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = cli_main(argv)
    raw = out.getvalue().strip()
    data: dict[str, object] = json.loads(raw) if raw.startswith("{") else {"raw": raw}
    if err.getvalue().strip():
        data["_stderr"] = err.getvalue().strip()
    return rc, data


def _make_git_target(root: pathlib.Path) -> pathlib.Path:
    repo = root / "target_repo"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "auth.py").write_text(
        "def check_session(tok: str) -> bool:\n"
        "    # verify auth boundary\n"
        "    return tok == 'ok'\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "dev@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Dev"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)
    return repo


class ArchLintSelfTests(unittest.TestCase):
    def setUp(self) -> None:
        self.lint = _load_arch_lint()

    def test_live_repository_passes_arch_lint_with_zero_violations(self) -> None:
        violations = self.lint.run_all_checks(REPO_ROOT)
        self.assertEqual(violations, [], f"Live repo failed arch_lint: {violations}")

    def test_every_lint_rule_rejects_synthetic_violation_with_fix_hint(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / "ajar" / "domain").mkdir(parents=True)
            (root / "ajar" / "store").mkdir(parents=True)
            (root / "ajar" / "services").mkdir(parents=True)
            (root / "tests").mkdir(parents=True)
            (root / "docs").mkdir(parents=True)

            # 1. NO_RAW_SQL_IN_MCP
            (root / "ajar" / "mcp.py").write_text(
                'def bad(conn):\n    conn.execute("INSERT INTO surfaces(surface_id) VALUES (?)", ("s1",))\n',
                encoding="utf-8",
            )
            v_mcp = self.lint.check_no_raw_sql_in_mcp(root)
            self.assertEqual([v.rule for v in v_mcp], ["NO_RAW_SQL_IN_MCP"])
            self.assertTrue(v_mcp[0].fix_hint)

            # 2. CLI_RAW_SQL_RATCHET
            (root / "ajar" / "cli.py").write_text(
                'def f(conn):\n    conn.execute("UPDATE tasks SET status = ? WHERE task_id = ?", ("done", "t1"))\n'
                '    conn.execute("DELETE FROM tasks WHERE task_id = ?", ("t1",))\n',
                encoding="utf-8",
            )
            v_cli = self.lint.check_cli_raw_sql_ratchet(root, max_writes=1)
            self.assertEqual([v.rule for v in v_cli], ["CLI_RAW_SQL_RATCHET"])
            self.assertTrue(v_cli[0].fix_hint)

            # 3. LAYER_DAG_BOUNDARY & ZERO_LLM_ENGINE
            (root / "ajar" / "db.py").write_text("X = 1\n", encoding="utf-8")
            (root / "ajar" / "domain" / "bad_dom.py").write_text("import ajar.db\n", encoding="utf-8")
            (root / "ajar" / "store" / "bad_store.py").write_text("import ajar.services.workflow\n", encoding="utf-8")
            (root / "ajar" / "services" / "bad_svc.py").write_text("import ajar.cli\n", encoding="utf-8")
            (root / "ajar" / "bad_llm.py").write_text("import openai\nfrom tools.legacy import foo\n", encoding="utf-8")
            v_dag = self.lint.check_layer_dag_boundaries(root)
            rules = [v.rule for v in v_dag]
            self.assertGreaterEqual(rules.count("LAYER_DAG_BOUNDARY"), 4)
            self.assertIn("ZERO_LLM_ENGINE", rules)
            self.assertTrue(all(v.fix_hint for v in v_dag))

            # 4. NO_HARDCODED_DEVBOX_PATH (construct dynamically so this test stays clean)
            bad_path = "/" + "home/" + "antigravity/secret"
            (root / "docs" / "bad.md").write_text(f"Do not run {bad_path}\n", encoding="utf-8")
            v_path = self.lint.check_no_hardcoded_devbox_paths(root)
            self.assertEqual([v.rule for v in v_path], ["NO_HARDCODED_DEVBOX_PATH"])
            self.assertTrue(v_path[0].fix_hint)

            # 5. NO_AMBIENT_ENV_MUTATION
            (root / "tests" / "test_bad_env.py").write_text(
                'import os\nos.environ["HOME"] = "/tmp/x"\n',
                encoding="utf-8",
            )
            v_env = self.lint.check_no_ambient_env_mutation_in_tests(root)
            self.assertEqual([v.rule for v in v_env], ["NO_AMBIENT_ENV_MUTATION"])
            self.assertTrue(v_env[0].fix_hint)

            # 6. NO_UNFILTERED_TAR_EXTRACT
            (root / "ajar" / "bad_tar.py").write_text(
                "def extract_it(tar, m, d):\n    tar.extract(m, path=d)\n",
                encoding="utf-8",
            )
            v_tar = self.lint.check_no_unfiltered_tar_extract(root)
            self.assertEqual([v.rule for v in v_tar], ["NO_UNFILTERED_TAR_EXTRACT"])
            self.assertTrue(v_tar[0].fix_hint)


class CliMcpDifferentialParityTests(unittest.TestCase):
    def test_cli_and_mcp_produce_identical_workflow_state_and_errors(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            ajar_home = base / "ajar_home"
            target = _make_git_target(base)

            with mock.patch.dict(os.environ, {"AJAR_HOME": str(ajar_home)}):
                rc1, init_cli = _run_cli(["init", "--json", str(target)])
                rc2, init_mcp = _run_cli(["init", "--json", str(target)])
                self.assertEqual(rc1, 0)
                self.assertEqual(rc2, 0)
                rid_cli = str(init_cli["run_id"])
                rid_mcp = str(init_mcp["run_id"])

                # 1. Surface add parity
                rc_s, surf_cli = _run_cli(
                    [
                        "surface",
                        "add",
                        "--run",
                        rid_cli,
                        "--name",
                        "session_check",
                        "--kind",
                        "auth_boundary",
                        "--locus",
                        "auth.py:1",
                        "--priority",
                        "high",
                    ]
                )
                self.assertEqual(rc_s, 0)
                surf_mcp = dispatch_mcp_tool(
                    rid_mcp,
                    "ajar_surface_add",
                    {
                        "name": "session_check",
                        "kind": "auth_boundary",
                        "locus": "auth.py:1",
                        "priority": "high",
                    },
                )
                self.assertEqual(surf_cli["subsystem"], surf_mcp["subsystem"])
                self.assertEqual(surf_cli["priority"], surf_mcp["priority"])
                self.assertEqual(surf_cli["hooks_triggered"], surf_mcp["hooks_triggered"])

                # 2. Anomaly add parity
                rc_a, anom_cli = _run_cli(
                    [
                        "anomaly",
                        "add",
                        "--run",
                        rid_cli,
                        "--locus",
                        "auth.py:3",
                        "--observation",
                        "Empty token bypasses comparison when session table is uninitialized",
                    ]
                )
                self.assertEqual(rc_a, 0)
                anom_mcp = dispatch_mcp_tool(
                    rid_mcp,
                    "ajar_anomaly_add",
                    {
                        "locus": "auth.py:3",
                        "observation": "Empty token bypasses comparison when session table is uninitialized",
                    },
                )
                self.assertEqual(anom_cli["status"], anom_mcp["status"])
                self.assertEqual(anom_cli["subsystem"], anom_mcp["subsystem"])

                # 3. Claim propose consuming anomaly parity
                claim_kwargs = {
                    "title": "Session token equality check accepts empty secret",
                    "locus": "auth.py:3",
                    "mechanism": "Unvalidated tok string reaches check_session and evaluates equality without length guard",
                    "falsification_prediction": "Empty string token returns True when expected secret is empty",
                    "falsification_test": "python3 -c 'import auth; assert auth.check_session(\"\")'",
                    "severity": "high",
                }
                rc_p, clm_cli = _run_cli(
                    [
                        "claim",
                        "propose",
                        "--run",
                        rid_cli,
                        "--worker",
                        "w-prop",
                        "--title",
                        claim_kwargs["title"],
                        "--locus",
                        claim_kwargs["locus"],
                        "--mechanism",
                        claim_kwargs["mechanism"],
                        "--falsification-prediction",
                        claim_kwargs["falsification_prediction"],
                        "--falsification-test",
                        claim_kwargs["falsification_test"],
                        "--severity",
                        claim_kwargs["severity"],
                        "--consume-anomaly",
                        str(anom_cli["anomaly_id"]),
                    ]
                )
                self.assertEqual(rc_p, 0)
                clm_mcp = dispatch_mcp_tool(
                    rid_mcp,
                    "ajar_claim_propose",
                    {
                        **claim_kwargs,
                        "worker_id": "w-prop",
                        "consume_anomaly_id": str(anom_mcp["anomaly_id"]),
                    },
                )
                self.assertEqual(clm_cli["status"], clm_mcp["status"])
                self.assertEqual(clm_cli["subsystem"], clm_mcp["subsystem"])

                # 4. Self-falsification rejection parity
                rc_sf, _ = _run_cli(
                    [
                        "claim",
                        "falsify",
                        "--run",
                        rid_cli,
                        "--worker",
                        "w-prop",
                        str(clm_cli["claim_id"]),
                        "--notes",
                        "self check must fail",
                    ]
                )
                self.assertNotEqual(rc_sf, 0)
                with self.assertRaises(AjarError):
                    dispatch_mcp_tool(
                        rid_mcp,
                        "ajar_claim_falsify",
                        {
                            "claim_id": str(clm_mcp["claim_id"]),
                            "worker_id": "w-prop",
                            "notes": "self check must fail",
                        },
                    )

                # 5. Independent falsification restores consumed anomaly identically on both paths
                rc_f, fal_cli = _run_cli(
                    [
                        "claim",
                        "falsify",
                        "--run",
                        rid_cli,
                        "--worker",
                        "w-fals",
                        str(clm_cli["claim_id"]),
                        "--notes",
                        "Constant 'ok' never matches empty string",
                        "--control-locus",
                        "auth.py:3",
                    ]
                )
                self.assertEqual(rc_f, 0)
                fal_mcp = dispatch_mcp_tool(
                    rid_mcp,
                    "ajar_claim_falsify",
                    {
                        "claim_id": str(clm_mcp["claim_id"]),
                        "worker_id": "w-fals",
                        "notes": "Constant 'ok' never matches empty string",
                        "control_locus": "auth.py:3",
                    },
                )
                self.assertEqual(fal_cli["status"], "falsified")
                self.assertEqual(fal_mcp["status"], "falsified")

                # 6. Resurrecting a falsified claim via survive is rejected as InvalidTransitionError identically
                rc_s2, _ = _run_cli(
                    [
                        "claim",
                        "survive",
                        "--run",
                        rid_cli,
                        "--worker",
                        "w-fals",
                        str(clm_cli["claim_id"]),
                        "--notes",
                        "cannot resurrect falsified claim",
                    ]
                )
                self.assertNotEqual(rc_s2, 0)
                with self.assertRaises(InvalidTransitionError):
                    dispatch_mcp_tool(
                        rid_mcp,
                        "ajar_claim_survive",
                        {
                            "claim_id": str(clm_mcp["claim_id"]),
                            "worker_id": "w-fals",
                            "notes": "cannot resurrect falsified claim",
                        },
                    )

                # 7. Compare resulting DB state across both runs
                conn_cli = open_run_db(rid_cli)
                conn_mcp = open_run_db(rid_mcp)
                try:
                    c1 = dict(conn_cli.execute("SELECT status, research_state, evidence_state FROM claims").fetchone())
                    c2 = dict(conn_mcp.execute("SELECT status, research_state, evidence_state FROM claims").fetchone())
                    self.assertEqual(c1, c2)
                    a1 = dict(conn_cli.execute("SELECT status, consumed_by_id FROM anomalies").fetchone())
                    a2 = dict(conn_mcp.execute("SELECT status, consumed_by_id FROM anomalies").fetchone())
                    self.assertEqual(a1, {"status": "unexplained", "consumed_by_id": None})
                    self.assertEqual(a1, a2)
                finally:
                    conn_cli.close()
                    conn_mcp.close()

    def test_non_source_chain_propose_rejects_dry_primitive(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            ajar_home = base / "ajar_home"
            fake_bin = base / "target.bin"
            fake_bin.write_bytes(b"\x7fELF" + b"\x00" * 64)

            with mock.patch.dict(os.environ, {"AJAR_HOME": str(ajar_home)}):
                rc_init, init_res = _run_cli(["init", "--json", "--mode", "binary", str(fake_bin)])
                self.assertEqual(rc_init, 0)
                rid = str(init_res["run_id"])
                rc_p, prim = _run_cli(
                    [
                        "primitive",
                        "add",
                        "--run",
                        rid,
                        "--kind",
                        "memory_write",
                        "--locus",
                        "0x401000",
                        "--preconditions",
                        "attacker controls input buffer length",
                        "--postconditions",
                        "controlled 8-byte write past stack frame",
                        "--evidence-cmd",
                        "true",
                        "--role",
                        "capability",
                    ]
                )
                self.assertEqual(rc_p, 0)
                rc_d, _ = _run_cli(
                    [
                        "primitive",
                        "dry",
                        "--run",
                        rid,
                        str(prim["primitive_id"]),
                        "--locus",
                        "0x401004",
                        "--reason",
                        "Stack canary prevents overwrite from reaching return address",
                    ]
                )
                self.assertEqual(rc_d, 0)
                rc_c, out_c = _run_cli(
                    [
                        "chain",
                        "propose",
                        "--run",
                        rid,
                        "--title",
                        "Illegal chain using dry primitive",
                        "--steps",
                        str(prim["primitive_id"]),
                        "--poc-cmd",
                        "exit 1",
                        "--control-cmd",
                        "exit 0",
                    ]
                )
                self.assertNotEqual(rc_c, 0)
                self.assertIn("Invalid primitive.status transition", str(out_c))


if __name__ == "__main__":
    unittest.main()
