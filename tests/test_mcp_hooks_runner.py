from __future__ import annotations

import io
import json
import os
import pathlib
import stat
import tempfile
import unittest

from ajar.db import open_run_db, utc_now_iso
from ajar.hooks import evaluate_claude_stop_hook
from ajar.mcp import handle_jsonrpc_message, serve_mcp_stdio
from ajar.oracles import query_oracle
from ajar.repomap import build_repomap
from ajar.runner import run_autonomous_schedule
from ajar.workspace import init_run_workspace, unlock_run_dir_permissions


class TestMcpHooksRunner(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = pathlib.Path(self._tmp.name)
        self.ajar_home = self.tmp_path / "ajar_home"
        self.src_target = self.tmp_path / "sample_repo"
        self.src_target.mkdir()
        # Plant untrusted agent config inside target to verify --envelope strips it!
        (self.src_target / ".mcp.json").write_text('{"evil": true}\n', encoding="utf-8")
        (self.src_target / ".claude").mkdir()
        (self.src_target / ".claude" / "settings.json").write_text('{"hooks": "evil"}\n', encoding="utf-8")
        (self.src_target / "vault.py").write_text(
            "def withdraw(user: str, amount: int) -> int:\n"
            "    return transfer_funds(user, amount)\n\n"
            "def transfer_funds(dest: str, val: int) -> int:\n"
            "    return val\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        if self.ajar_home.exists():
            for child in (self.ajar_home / "runs").glob("*") if (self.ajar_home / "runs").exists() else []:
                unlock_run_dir_permissions(child)
        self._tmp.cleanup()

    def test_envelope_readonly_and_in_place_zero_footprint(self) -> None:
        # 1. --envelope mode: read-only target/, stripped untrusted .mcp.json/.claude inside target/, generated Host Mode configs!
        env_info = init_run_workspace(
            target=str(self.src_target),
            target_mode="source",
            workspace_mode="envelope",
            run_id="run-env-1",
            ajar_home=self.ajar_home,
        )
        ws = pathlib.Path(env_info["workspace_path"])
        target_snap = ws / "target"
        self.assertTrue((ws / ".mcp.json").is_file())
        self.assertTrue((ws / ".claude" / "settings.json").is_file())
        self.assertTrue((ws / "AGENTS.md").is_file())
        self.assertFalse((target_snap / ".mcp.json").exists(), "Untrusted .mcp.json inside target must be stripped")
        self.assertFalse((target_snap / ".claude").exists(), "Untrusted .claude/ inside target must be stripped")
        mode_bits = os.stat(target_snap / "vault.py").st_mode
        self.assertEqual(mode_bits & stat.S_IWUSR, 0, "Envelope target snapshot must be read-only")

        # 2. --in-place mode: ZERO files created or modified inside src_target!
        before_entries = sorted(p.name for p in self.src_target.iterdir())
        init_run_workspace(
            target=str(self.src_target),
            target_mode="source",
            workspace_mode="in_place",
            run_id="run-inplace-1",
            ajar_home=self.ajar_home,
        )
        after_entries = sorted(p.name for p in self.src_target.iterdir())
        self.assertEqual(before_entries, after_entries, "--in-place must write zero files into target directory")

    def test_mcp_stdio_newline_and_content_length_framing(self) -> None:
        init_run_workspace(
            target=str(self.src_target),
            target_mode="source",
            workspace_mode="in_place",
            run_id="run-mcp-1",
            ajar_home=self.ajar_home,
        )

        # Direct JSON-RPC initialize & tools/list
        init_resp = handle_jsonrpc_message(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            run_id="run-mcp-1",
            ajar_home=self.ajar_home,
        )
        self.assertIsNotNone(init_resp)
        self.assertIn("protocolVersion", init_resp["result"])

        # Stream test mixing newline-delimited JSON-RPC and Content-Length framed JSON-RPC
        msg1 = json.dumps({"jsonrpc": "2.0", "id": 10, "method": "tools/list", "params": {}}).encode("utf-8") + b"\n"
        body2 = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 11,
                "method": "tools/call",
                "params": {"name": "ajar_status", "arguments": {}},
            }
        ).encode("utf-8")
        msg2 = f"Content-Length: {len(body2)}\r\n\r\n".encode("ascii") + body2

        in_buf = io.BytesIO(msg1 + msg2)
        out_buf = io.BytesIO()
        serve_mcp_stdio(explicit_run_id="run-mcp-1", stdin=in_buf, stdout=out_buf, ajar_home=self.ajar_home)
        raw_out = out_buf.getvalue().decode("utf-8")
        self.assertIn('"ajar_claim_propose"', raw_out)
        self.assertIn("run-mcp-1", raw_out)

    def test_claude_stop_hook_blocks_then_releases_after_three_stalls(self) -> None:
        init_run_workspace(
            target=str(self.src_target),
            target_mode="source",
            workspace_mode="in_place",
            run_id="run-hook-1",
            ajar_home=self.ajar_home,
        )
        conn = open_run_db("run-hook-1", ajar_home=self.ajar_home)
        try:
            # Check 1 (initial event exists -> stalls=0, decision=block)
            rc0, p0 = evaluate_claude_stop_hook(conn, target_dir=self.src_target)
            self.assertNotEqual(rc0, 0)
            self.assertEqual(p0["decision"], "block")

            # Checks with zero new non-hook events -> stalls=1, 2, then 3 releases!
            rc1, p1 = evaluate_claude_stop_hook(conn, target_dir=self.src_target)
            self.assertEqual(p1["decision"], "block")
            rc2, p2 = evaluate_claude_stop_hook(conn, target_dir=self.src_target)
            self.assertEqual(p2["decision"], "block")
            rc3, p3 = evaluate_claude_stop_hook(conn, target_dir=self.src_target)
            self.assertEqual(rc3, 0)
            self.assertEqual(p3["decision"], "approve")
            self.assertTrue(p3.get("stalled_release"))
        finally:
            conn.close()

    def test_repomap_pagerank_and_fts5_syntax_safe_queries(self) -> None:
        init_run_workspace(
            target=str(self.src_target),
            target_mode="source",
            workspace_mode="in_place",
            run_id="run-map-1",
            ajar_home=self.ajar_home,
        )
        conn = open_run_db("run-map-1", ajar_home=self.ajar_home)
        try:
            rmap = build_repomap(conn, self.src_target, focus_symbols=["withdraw"], budget_tokens=800)
            self.assertIn("withdraw", rmap["rendered"])
            self.assertIn("transfer_funds", rmap["rendered"])

            # Adversarial FTS5 punctuation query must never throw sqlite3.OperationalError!
            hits = query_oracle(conn, "all", 'withdraw("foo"::bar) AND OR NOT * [unclosed', limit=5)
            self.assertIsInstance(hits, list)
        finally:
            conn.close()

    def test_standalone_runner_80_20_verify_only_reserve_cutoff(self) -> None:
        init_run_workspace(
            target=str(self.src_target),
            target_mode="source",
            workspace_mode="envelope",
            budget_usd=10.0,
            run_id="run-sched-1",
            ajar_home=self.ajar_home,
        )
        conn = open_run_db("run-sched-1", ajar_home=self.ajar_home)
        try:
            now = utc_now_iso()
            # Spend $8.50 of $10.00 (85% >= 80% explore cutoff!) and leave 1 open investigate + 1 proposed claim!
            conn.execute(
                "INSERT INTO spend_ledger(entry_id, worker_id, phase, model, tokens_in, tokens_out, cost_usd, created_at) VALUES ('sp-1', 'w0', 'explore', 'test', 1000, 500, 8.50, ?)",
                (now,),
            )
            conn.execute(
                "INSERT INTO surfaces(surface_id, name, kind, subsystem, locus, priority, created_at) VALUES ('s1', 'withdraw', 'fn', 'vault.py', 'vault.py:1', 'high', ?)",
                (now,),
            )
            conn.execute(
                """
                INSERT INTO tasks(task_id, surface_id, kind, title, subsystem, locus, priority, status, salience_score, created_at, updated_at)
                VALUES ('t-inv', 's1', 'investigate', 'Explore more', 'vault.py', 'vault.py:1', 'high', 'open', 80, ?, ?)
                """,
                (now, now),
            )
            conn.execute(
                """
                INSERT INTO claims(
                    claim_id, surface_id, proposer_worker_id, title, subsystem, locus, mechanism, mechanism_key,
                    severity, falsification_prediction, falsification_test, status, created_at, updated_at
                ) VALUES ('clm-v1', 's1', 'worker-0', 'Bogus claim', 'vault.py', 'vault.py:1', 'none', 'none', 'high', 'returns val', 'python3 -c true', 'proposed', ?, ?)
                """,
                (now, now),
            )
        finally:
            conn.close()

        # Worker script falsifies proposed claim when AJAR_TASK_KIND == falsify, and closes task!
        worker_cmd = (
            "if [ \"$AJAR_TASK_KIND\" = \"falsify\" ]; then "
            "ajar claim falsify clm-v1 --worker \"$AJAR_WORKER_ID\" --notes 'Disproved in verify reserve' --run \"$AJAR_RUN_ID\"; "
            "ajar task done \"$AJAR_TASK_ID\" --worker \"$AJAR_WORKER_ID\" --summary 'Falsified clm-v1' --run \"$AJAR_RUN_ID\"; "
            "fi"
        )
        res = run_autonomous_schedule(
            target=str(self.src_target),
            run_id="run-sched-1",
            budget_usd=10.0,
            workers=2,
            worker_cmd=worker_cmd,
            max_steps=5,
            ajar_home=self.ajar_home,
        )
        self.assertTrue(res["verify_cutoff_triggered"], res)
        self.assertTrue(pathlib.Path(res["report_markdown_path"]).is_file())
        self.assertTrue(pathlib.Path(res["report_json_path"]).is_file())

        conn2 = open_run_db("run-sched-1", ajar_home=self.ajar_home)
        try:
            # Verify `t-inv` (`investigate`) was NOT leased during `verify_only`, while `clm-v1` WAS falsified!
            t_inv = conn2.execute("SELECT status FROM tasks WHERE task_id = 't-inv'").fetchone()
            clm_v1 = conn2.execute("SELECT status FROM claims WHERE claim_id = 'clm-v1'").fetchone()
            self.assertEqual(t_inv["status"], "open")
            self.assertEqual(clm_v1["status"], "falsified")
        finally:
            conn2.close()


if __name__ == "__main__":
    unittest.main()
