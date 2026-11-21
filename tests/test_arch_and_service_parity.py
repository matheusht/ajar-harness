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

            # 1. NO_RAW_SQL_IN_MCP (including INSERT OR REPLACE, f-strings, executescript)
            (root / "ajar" / "mcp.py").write_text(
                'def bad(conn, tbl):\n'
                '    conn.execute("INSERT OR REPLACE INTO surfaces(surface_id) VALUES (?)", ("s1",))\n'
                '    conn.execute(f"UPDATE {tbl} SET status = \'done\'")\n'
                '    conn.executescript("DELETE FROM tasks WHERE 1=0;")\n',
                encoding="utf-8",
            )
            v_mcp = self.lint.check_no_raw_sql_in_mcp(root)
            self.assertEqual(len(v_mcp), 3)
            self.assertTrue(all(v.rule == "NO_RAW_SQL_IN_MCP" and v.fix_hint for v in v_mcp))

            # 2. CLI_RAW_SQL_RATCHET
            (root / "ajar" / "cli.py").write_text(
                'def f(conn):\n    conn.execute("REPLACE INTO tasks(task_id) VALUES (?)", ("t1",))\n'
                '    conn.execute("DELETE FROM tasks WHERE task_id = ?", ("t1",))\n',
                encoding="utf-8",
            )
            v_cli = self.lint.check_cli_raw_sql_ratchet(root, max_writes=1)
            self.assertEqual([v.rule for v in v_cli], ["CLI_RAW_SQL_RATCHET"])
            self.assertTrue(v_cli[0].fix_hint)

            # 3. LAYER_DAG_BOUNDARY (absolute + relative imports) & ZERO_LLM_ENGINE
            (root / "ajar" / "db.py").write_text("X = 1\n", encoding="utf-8")
            (root / "ajar" / "domain" / "bad_dom.py").write_text(
                "import ajar.db\nfrom ..db import X\n",
                encoding="utf-8",
            )
            (root / "ajar" / "store" / "bad_store.py").write_text(
                "import ajar.services.workflow\nfrom .. import services\n",
                encoding="utf-8",
            )
            (root / "ajar" / "services" / "bad_svc.py").write_text(
                "import ajar.cli\nfrom .. import cli\nfrom ..cli import main\n",
                encoding="utf-8",
            )
            (root / "ajar" / "bad_llm.py").write_text(
                "import openai\nfrom tools.legacy import foo\n",
                encoding="utf-8",
            )
            v_dag = self.lint.check_layer_dag_boundaries(root)
            rules = [v.rule for v in v_dag]
            self.assertEqual(rules.count("LAYER_DAG_BOUNDARY"), 8)
            self.assertEqual(rules.count("ZERO_LLM_ENGINE"), 1)
            self.assertTrue(all(v.fix_hint for v in v_dag))

            # 4. NO_HARDCODED_DEVBOX_PATH (construct dynamically so this test stays clean)
            bad_path = "/" + "home/" + "antigravity/secret"
            (root / "docs" / "bad.md").write_text(f"Do not run {bad_path}\n", encoding="utf-8")
            v_path = self.lint.check_no_hardcoded_devbox_paths(root)
            self.assertEqual([v.rule for v in v_path], ["NO_HARDCODED_DEVBOX_PATH"])
            self.assertTrue(v_path[0].fix_hint)

            # 5. NO_AMBIENT_ENV_MUTATION (assign, del, pop, update, putenv)
            (root / "tests" / "test_bad_env.py").write_text(
                'import os\n'
                'os.environ["HOME"] = "/tmp/x"\n'
                'del os.environ["PATH"]\n'
                'os.environ.pop("HOME", None)\n'
                'os.environ.update({"PATH": "/bin"})\n'
                'os.putenv("HOME", "/tmp/y")\n',
                encoding="utf-8",
            )
            v_env = self.lint.check_no_ambient_env_mutation_in_tests(root)
            self.assertEqual(len(v_env), 5)
            self.assertTrue(all(v.rule == "NO_AMBIENT_ENV_MUTATION" and v.fix_hint for v in v_env))

            # 6. NO_UNFILTERED_TAR_EXTRACT (missing filter, filter=None, filter='fully_trusted'; ignore zipfile)
            (root / "ajar" / "bad_tar.py").write_text(
                "import tarfile\n"
                "def extract_it(tar, m, d):\n"
                "    tar.extract(m, path=d)\n"
                "    tar.extract(m, path=d, filter=None)\n"
                "    tar.extractall(path=d, filter='fully_trusted')\n"
                "    tar.extract(m, path=d, filter='tar')\n",
                encoding="utf-8",
            )
            (root / "ajar" / "ok_zip.py").write_text(
                "import zipfile\n"
                "def unpack(zf, d):\n"
                "    zf.extractall(d)\n",
                encoding="utf-8",
            )
            v_tar = self.lint.check_no_unfiltered_tar_extract(root)
            self.assertEqual(len(v_tar), 3)
            self.assertTrue(all(v.rule == "NO_UNFILTERED_TAR_EXTRACT" and v.path == "ajar/bad_tar.py" for v in v_tar))

            # 7. NO_COMMIT_NOOP
            (root / "ajar" / "bad_tx.py").write_text(
                "def bad_commit(conn):\n"
                "    conn.execute('UPDATE runs SET status = \"active\"')\n"
                "    conn.execute('DELETE FROM tasks WHERE 1=0')\n"
                "    conn.commit()\n"
                "\n"
                "def good_tx(conn):\n"
                "    with immediate_tx(conn):\n"
                "        conn.execute('UPDATE runs SET status = \"active\"')\n"
                "        conn.execute('DELETE FROM tasks WHERE 1=0')\n",
                encoding="utf-8",
            )
            v_commit = self.lint.check_no_commit_noop(root)
            self.assertEqual([v.rule for v in v_commit], ["NO_COMMIT_NOOP"])
            self.assertTrue(v_commit[0].fix_hint)

            # 8. MULTI_WRITE_REQUIRES_IMMEDIATE_TX
            v_multi = self.lint.check_multi_write_requires_immediate_tx(root)
            bad_tx_multi = [v for v in v_multi if v.path == "ajar/bad_tx.py"]
            self.assertEqual(len(bad_tx_multi), 1)
            self.assertEqual(bad_tx_multi[0].rule, "MULTI_WRITE_REQUIRES_IMMEDIATE_TX")
            self.assertIn("bad_commit", bad_tx_multi[0].message)
            self.assertTrue(bad_tx_multi[0].fix_hint)


class CliMcpDifferentialParityTests(unittest.TestCase):
    def test_cli_and_mcp_produce_identical_workflow_state_and_errors(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            ajar_home = base / "ajar_home"
            target = _make_git_target(base)

            with mock.patch.dict(os.environ, {"AJAR_HOME": str(ajar_home)}):
                rc1, init_cli = _run_cli(["init", "--in-place", "--json", str(target)])
                rc2, init_mcp = _run_cli(["init", "--in-place", "--json", str(target)])
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

                # 2. Task close (dry + invalid outcome rejection) parity
                rc_t1, t1_cli = _run_cli(
                    [
                        "task",
                        "add",
                        "--run",
                        rid_cli,
                        "--kind",
                        "investigate",
                        "--title",
                        "Audit auth boundary",
                        "--locus",
                        "auth.py:1",
                    ]
                )
                rc_t2, t1_mcp = _run_cli(
                    [
                        "task",
                        "add",
                        "--run",
                        rid_mcp,
                        "--kind",
                        "investigate",
                        "--title",
                        "Audit auth boundary",
                        "--locus",
                        "auth.py:1",
                    ]
                )
                self.assertEqual(rc_t1, 0)
                self.assertEqual(rc_t2, 0)
                with self.assertRaises(AjarError):
                    dispatch_mcp_tool(
                        rid_mcp,
                        "ajar_task_close",
                        {"task_id": str(t1_mcp["task_id"]), "worker_id": "w1", "outcome": "bogus"},
                    )
                rc_td, dry_cli = _run_cli(
                    [
                        "task",
                        "dry",
                        "--run",
                        rid_cli,
                        "--worker",
                        "w1",
                        str(t1_cli["task_id"]),
                        "--locus",
                        "auth.py:3",
                        "--control",
                        "Exact string comparison enforces strict token equality check",
                    ]
                )
                self.assertEqual(rc_td, 0)
                dry_mcp = dispatch_mcp_tool(
                    rid_mcp,
                    "ajar_task_close",
                    {
                        "task_id": str(t1_mcp["task_id"]),
                        "worker_id": "w1",
                        "outcome": "dry",
                        "control_locus": "auth.py:3",
                        "control_reason": "Exact string comparison enforces strict token equality check",
                    },
                )
                self.assertEqual(dry_cli["status"], "dry")
                self.assertEqual(dry_mcp["status"], "dry")

                # 3. Anomaly add parity
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

                # 4. Claim propose consuming anomaly parity
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

                # 5. Self-falsification & whitespace-padded worker_id bypass rejection parity
                for bad_worker in ("w-prop", "w-prop ", " w-prop"):
                    rc_sf, _ = _run_cli(
                        [
                            "claim",
                            "falsify",
                            "--run",
                            rid_cli,
                            "--worker",
                            bad_worker,
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
                                "worker_id": bad_worker,
                                "notes": "self check must fail",
                            },
                        )
                    with self.assertRaises(AjarError):
                        dispatch_mcp_tool(
                            rid_mcp,
                            "ajar_claim_survive",
                            {
                                "claim_id": str(clm_mcp["claim_id"]),
                                "worker_id": bad_worker,
                                "notes": "self survive must fail",
                            },
                        )

                # 6. config_gated probe spawning parity
                rc_cg, cg_cli = _run_cli(
                    [
                        "claim",
                        "falsify",
                        "--run",
                        rid_cli,
                        "--worker",
                        "w-fals",
                        str(clm_cli["claim_id"]),
                        "--notes",
                        "Requires ALLOW_EMPTY_TOKEN=1",
                        "--config-gate",
                        "ALLOW_EMPTY_TOKEN=1",
                    ]
                )
                self.assertEqual(rc_cg, 0)
                cg_mcp = dispatch_mcp_tool(
                    rid_mcp,
                    "ajar_claim_falsify",
                    {
                        "claim_id": str(clm_mcp["claim_id"]),
                        "worker_id": "w-fals",
                        "notes": "Requires ALLOW_EMPTY_TOKEN=1",
                        "config_gate": "ALLOW_EMPTY_TOKEN=1",
                    },
                )
                self.assertEqual(cg_cli["status"], "config_gated")
                self.assertEqual(cg_mcp["status"], "config_gated")
                self.assertTrue(cg_cli.get("probe_task_id"))
                self.assertTrue(cg_mcp.get("probe_task_id"))

                # 7. Independent falsification restores consumed anomaly identically on both paths
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

                # 8. Resurrecting a falsified claim via survive is rejected as InvalidTransitionError identically
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

                # 9. Happy-path claim survive parity on a second claim
                rc_p2, c2_cli = _run_cli(
                    [
                        "claim",
                        "propose",
                        "--run",
                        rid_cli,
                        "--worker",
                        "w-prop",
                        "--title",
                        "Constant-time comparison missing in check_session",
                        "--locus",
                        "auth.py:3",
                        "--mechanism",
                        "Direct == comparison leaks secret prefix bytes via timing side-channel",
                        "--falsification-prediction",
                        "Early-exit equality terminates faster on mismatched first byte",
                        "--falsification-test",
                        "python3 -c 'import auth; auth.check_session(\"x\")'",
                        "--severity",
                        "medium",
                    ]
                )
                self.assertEqual(rc_p2, 0)
                c2_mcp = dispatch_mcp_tool(
                    rid_mcp,
                    "ajar_claim_propose",
                    {
                        "worker_id": "w-prop",
                        "title": "Constant-time comparison missing in check_session",
                        "locus": "auth.py:3",
                        "mechanism": "Direct == comparison leaks secret prefix bytes via timing side-channel",
                        "falsification_prediction": "Early-exit equality terminates faster on mismatched first byte",
                        "falsification_test": "python3 -c 'import auth; auth.check_session(\"x\")'",
                        "severity": "medium",
                    },
                )
                rc_sv, sv_cli = _run_cli(
                    [
                        "claim",
                        "survive",
                        "--run",
                        rid_cli,
                        "--worker",
                        "w-fals",
                        str(c2_cli["claim_id"]),
                        "--notes",
                        "Verified no hmac.compare_digest guard exists",
                    ]
                )
                self.assertEqual(rc_sv, 0)
                sv_mcp = dispatch_mcp_tool(
                    rid_mcp,
                    "ajar_claim_survive",
                    {
                        "claim_id": str(c2_mcp["claim_id"]),
                        "worker_id": "w-fals",
                        "notes": "Verified no hmac.compare_digest guard exists",
                    },
                )
                self.assertEqual(sv_cli["status"], "survived_falsify")
                self.assertEqual(sv_mcp["status"], "survived_falsify")

                # 10. Claim rescope structural prose validation parity (rejects OS hook literals on both CLI and MCP)
                rc_rs, _ = _run_cli(
                    [
                        "claim",
                        "rescope",
                        "--run",
                        rid_cli,
                        "--worker",
                        "w-fals",
                        str(c2_cli["claim_id"]),
                        "--reason",
                        "narrow locus",
                        "--mechanism",
                        "Writes #!/bin/sh payload into .git/hooks/post-checkout",
                    ]
                )
                self.assertNotEqual(rc_rs, 0)
                with self.assertRaises(AjarError):
                    dispatch_mcp_tool(
                        rid_mcp,
                        "ajar_claim_rescope",
                        {
                            "claim_id": str(c2_mcp["claim_id"]),
                            "worker_id": "w-fals",
                            "reason": "narrow locus",
                            "mechanism": "Writes #!/bin/sh payload into .git/hooks/post-checkout",
                        },
                    )

                # 11. Compare resulting DB state across both runs
                conn_cli = open_run_db(rid_cli)
                conn_mcp = open_run_db(rid_mcp)
                try:
                    c1 = [
                        dict(r)
                        for r in conn_cli.execute(
                            "SELECT status, research_state, evidence_state FROM claims ORDER BY created_at ASC"
                        ).fetchall()
                    ]
                    c2 = [
                        dict(r)
                        for r in conn_mcp.execute(
                            "SELECT status, research_state, evidence_state FROM claims ORDER BY created_at ASC"
                        ).fetchall()
                    ]
                    self.assertEqual(c1, c2)
                    a1 = dict(conn_cli.execute("SELECT status, consumed_by_id FROM anomalies").fetchone())
                    a2 = dict(conn_mcp.execute("SELECT status, consumed_by_id FROM anomalies").fetchone())
                    self.assertEqual(a1, {"status": "unexplained", "consumed_by_id": None})
                    self.assertEqual(a1, a2)
                finally:
                    conn_cli.close()
                    conn_mcp.close()

    def test_finish_run_rejects_already_finished_run(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            ajar_home = base / "ajar_home"
            target = _make_git_target(base)

            with mock.patch.dict(os.environ, {"AJAR_HOME": str(ajar_home)}):
                rc_init, init_res = _run_cli(["init", "--in-place", "--json", str(target)])
                self.assertEqual(rc_init, 0)
                rid = str(init_res["run_id"])
                conn = open_run_db(rid)
                try:
                    conn.execute("UPDATE runs SET status = 'finished', finished_at = '2026-01-01T00:00:00Z'")
                finally:
                    conn.close()
                with self.assertRaises(InvalidTransitionError):
                    dispatch_mcp_tool(rid, "ajar_finish", {})

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

    def test_repro_outcome_persists_build_cmd_and_sealed_run_rejects_cli_writes(self) -> None:
        from ajar.services import (
            add_primitive,
            add_surface_driver,
            add_task,
            propose_claim,
            record_human_touch,
            record_reproduction_outcome,
            record_spend_entry,
            survive_claim,
        )

        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            target = _make_git_target(root)
            ajar_home = root / "ajar_home"
            rid = "run-build-cmd-001"
            with mock.patch.dict(os.environ, {"AJAR_HOME": str(ajar_home)}):
                rc, _ = _run_cli(
                    [
                        "init",
                        str(target),
                        "--run-id",
                        rid,
                        "--goal",
                        "Verify findings.build_cmd and sealed-run write guards",
                        "--in-place",
                        "--allow-historical-target",
                    ]
                )
                self.assertEqual(rc, 0)
                conn = open_run_db(rid, ajar_home=ajar_home)
                try:
                    c1 = propose_claim(
                        conn,
                        worker_id="w1",
                        title="Auth token bypass",
                        locus="auth.py:1",
                        mechanism="Weak token equality accepts forged input",
                        falsification_prediction="Forge fails if strict HMAC check runs",
                        falsification_test="pytest -k test_auth",
                        severity="high",
                        target_dir=target,
                        target_mode="source",
                    )
                    c2 = propose_claim(
                        conn,
                        worker_id="w1",
                        title="Sibling auth bypass",
                        locus="auth.py:2",
                        mechanism="Same weak token check from second entrypoint",
                        falsification_prediction="Forge fails if strict HMAC check runs",
                        falsification_test="pytest -k test_auth_2",
                        severity="high",
                        target_dir=target,
                        target_mode="source",
                    )
                    survive_claim(conn, claim_id=str(c1["claim_id"]), worker_id="w2", notes="verified")
                    survive_claim(conn, claim_id=str(c2["claim_id"]), worker_id="w2", notes="verified")

                    out = record_reproduction_outcome(
                        conn,
                        claim_id=str(c1["claim_id"]),
                        worker_id="w2",
                        poc_cmd="python3 -c 'raise SystemExit(1)'",
                        control_cmd="python3 -c 'raise SystemExit(0)'",
                        build_cmd="make -j4 auth_bin",
                        micropatch_path="fix.diff",
                        repro_result={
                            "passed": True,
                            "micropatch_diff": "--- a/auth.py\n+++ b/auth.py\n@@ -1 +1 @@\n-bad\n+good\n",
                            "arm1_clean_poc": {"exit_code": 1, "arm_passed": True, "stdout": "", "stderr": ""},
                            "arm2_clean_control": {"exit_code": 0, "arm_passed": True, "stdout": "", "stderr": ""},
                            "arm3_patch_poc": {"exit_code": 0, "arm_passed": True, "stdout": "", "stderr": ""},
                            "arm4_patch_control": {"exit_code": 0, "arm_passed": True, "stdout": "", "stderr": ""},
                            "cross_killed_claim_ids": [str(c2["claim_id"])],
                        },
                    )
                    frow = conn.execute(
                        "SELECT build_cmd FROM findings WHERE finding_id = ?",
                        (str(out["finding_id"]),),
                    ).fetchone()
                    self.assertIsNotNone(frow)
                    self.assertEqual(str(frow["build_cmd"]), "make -j4 auth_bin")

                    dup_row = conn.execute(
                        "SELECT status, research_state, evidence_state, duplicate_of_claim_id FROM claims WHERE claim_id = ?",
                        (str(c2["claim_id"]),),
                    ).fetchone()
                    self.assertEqual(str(dup_row["status"]), "duplicate_root_cause")
                    self.assertEqual(str(dup_row["research_state"]), "rejected_during_research")
                    self.assertEqual(str(dup_row["evidence_state"]), "unverified")
                    self.assertEqual(str(dup_row["duplicate_of_claim_id"]), str(c1["claim_id"]))

                    # Seal run and prove all newly unified CLI write services reject mutations.
                    conn.execute("UPDATE runs SET status = 'finished' WHERE run_id = ?", (rid,))
                    with self.assertRaises(InvalidTransitionError):
                        add_surface_driver(conn, surface_id="surf-1", setup_cmd="true", invoke_template="true")
                    with self.assertRaises(InvalidTransitionError):
                        add_task(conn, kind="investigate", title="Post-finish task", locus="auth.py:1")
                    with self.assertRaises(InvalidTransitionError):
                        add_primitive(
                            conn,
                            locus="auth.py:1",
                            kind="auth_bypass",
                            preconditions="p",
                            postconditions="q",
                            evidence_cmd="true",
                        )
                    with self.assertRaises(InvalidTransitionError):
                        record_human_touch(conn, kind="scope_authority", actor="op", notes="sealed")
                    with self.assertRaises(InvalidTransitionError):
                        record_spend_entry(conn, worker_id="w1", phase="hunt", cost_usd=1.0)
                finally:
                    conn.close()


if __name__ == "__main__":
    unittest.main()
