"""Unit & resilience tests for PR 4: unified 8-slot `repro try`, stale git lock auto-heal,
replayable failure receipts, self-healing transition/MCP errors, semantic stall progress,
inline structured swarm packets, and `ajar doctor --run [--prune-slots]`.
"""

from __future__ import annotations

import contextlib
import fcntl
import io
import json
import os
import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock

from ajar.cli import main as cli_main
from ajar.db import checkpoint_task, open_run_db
from ajar.domain import (
    InvalidTransitionError,
    assert_valid_claim_transition,
    assert_valid_phase_transition,
)
from ajar.hooks import evaluate_claude_stop_hook
from ajar.mcp import handle_jsonrpc_message
from ajar.repro_source import (
    _prepare_slot_worktree,
    init_source_mirror,
    run_repro_try,
    run_source_reproduction,
)
from ajar.services import (
    add_surface,
    add_task,
    propose_claim,
    record_human_touch,
    record_spend_entry,
)
from ajar.swarm import build_swarm_packet
from ajar.workspace import init_run_workspace


def _make_git_target(base: pathlib.Path) -> pathlib.Path:
    repo = base / "target_repo"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "app.py").write_text(
        "def check(token: str) -> bool:\n"
        "    return token == 'secret-expected'\n",
        encoding="utf-8",
    )
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Ajar Test",
        "GIT_AUTHOR_EMAIL": "ajar@example.com",
        "GIT_COMMITTER_NAME": "Ajar Test",
        "GIT_COMMITTER_EMAIL": "ajar@example.com",
    }
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True, env=env)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, env=env)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "init"], check=True, env=env)
    return repo


def _run_cli(argv: list[str]) -> tuple[int, dict[str, object]]:
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = cli_main(argv)
    raw = (out.getvalue() or err.getvalue()).strip()
    return rc, (json.loads(raw) if raw.startswith("{") else {"raw": raw})


class SwarmResilienceAndSelfHealingTests(unittest.TestCase):
    def test_self_healing_transition_errors_and_structured_mcp_json(self) -> None:
        with self.assertRaises(InvalidTransitionError) as ctx:
            assert_valid_claim_transition("proposed", "reproduced", claim_id="clm-1")
        exc = ctx.exception
        self.assertIn("survived_falsify", exc.allowed_targets)
        self.assertEqual(exc.details["allowed_targets"], list(exc.allowed_targets))
        self.assertIn("ajar claim survive", exc.fix_hint)
        self.assertEqual(exc.details["fix_hint"], exc.fix_hint)
        self.assertIn("allowed:", str(exc))

        with self.assertRaises(InvalidTransitionError) as pctx:
            assert_valid_phase_transition("remediate", "hunt", run_id="run-1")
        self.assertIn("full", pctx.exception.allowed_targets)
        self.assertTrue(pctx.exception.fix_hint)

        # MCP tools/call returns structured JSON containing exit_code, error_type, and details
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            ajar_home = base / "ajar_home"
            target = _make_git_target(base)
            with mock.patch.dict(os.environ, {"AJAR_HOME": str(ajar_home)}):
                init_run_workspace(
                    target=str(target),
                    target_mode="source",
                    workspace_mode="in_place",
                    run_id="run-mcp-err",
                    ajar_home=ajar_home,
                )
                resp = handle_jsonrpc_message(
                    {
                        "jsonrpc": "2.0",
                        "id": 9,
                        "method": "tools/call",
                        "params": {
                            "name": "ajar_claim_survive",
                            "arguments": {"claim_id": "clm-missing", "worker_id": "w1", "notes": "t"},
                        },
                    },
                    run_id="run-mcp-err",
                    ajar_home=ajar_home,
                )
                self.assertIsNotNone(resp)
                assert resp is not None
                self.assertTrue(resp["result"]["isError"])
                parsed = json.loads(resp["result"]["content"][0]["text"])
                self.assertEqual(parsed["error_type"], "AjarError")
                self.assertIn("exit_code", parsed)
                self.assertIn("details", parsed)
                self.assertIn("clm-missing", parsed["error"])

    def test_semantic_stall_breaker_ignores_noise_events(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            ajar_home = base / "ajar_home"
            target = _make_git_target(base)
            with mock.patch.dict(os.environ, {"AJAR_HOME": str(ajar_home)}):
                init_run_workspace(
                    target=str(target),
                    target_mode="source",
                    workspace_mode="in_place",
                    run_id="run-stall-noise",
                    ajar_home=ajar_home,
                )
                conn = open_run_db("run-stall-noise", ajar_home=ajar_home)
                try:
                    t = add_task(conn, kind="investigate", title="Investigate check", locus="app.py:1", priority="high")
                    tid = str(t["task_id"])

                    # Initial stop check records baseline semantic event id (stalls=0).
                    rc0, p0 = evaluate_claude_stop_hook(conn, target_dir=target)
                    self.assertNotEqual(rc0, 0)
                    self.assertEqual(p0["stalls"], 0)

                    # Emit 3 noisy non-progress events between stop checks -> stalls MUST still increment to 1, 2, 3!
                    record_spend_entry(
                        conn,
                        worker_id="w1",
                        phase="explore",
                        model="test",
                        tokens_in=10,
                        tokens_out=5,
                        cost_usd=0.01,
                    )
                    rc1, p1 = evaluate_claude_stop_hook(conn, target_dir=target)
                    self.assertEqual(p1["stalls"], 1)

                    checkpoint_task(conn, task_id=tid, worker_id="w1", state_dict={"note": "still thinking"})
                    rc2, p2 = evaluate_claude_stop_hook(conn, target_dir=target)
                    self.assertEqual(p2["stalls"], 2)

                    record_human_touch(conn, kind="research_steering", actor="op", notes="nudged")
                    rc3, p3 = evaluate_claude_stop_hook(conn, target_dir=target)
                    self.assertEqual(rc3, 0)
                    self.assertTrue(p3.get("stalled_release"))
                finally:
                    conn.close()

    def test_swarm_packet_embeds_structured_claims_without_raw_sql(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            ajar_home = base / "ajar_home"
            target = _make_git_target(base)
            with mock.patch.dict(os.environ, {"AJAR_HOME": str(ajar_home)}):
                init_run_workspace(
                    target=str(target),
                    target_mode="source",
                    workspace_mode="in_place",
                    run_id="run-pkt-inline",
                    ajar_home=ajar_home,
                )
                conn = open_run_db("run-pkt-inline", ajar_home=ajar_home)
                try:
                    surf = add_surface(
                        conn,
                        name="Auth",
                        kind="http",
                        subsystem="app",
                        locus="app.py:1",
                        priority="high",
                        trust_boundary="ext->app",
                    )
                    clm = propose_claim(
                        conn,
                        worker_id="w1",
                        title="Empty token accepted",
                        locus="app.py:1",
                        severity="high",
                        mechanism="Prefix comparison omits length check",
                        surface_id=str(surf["surface_id"]),
                        falsification_prediction="Empty string returns False",
                        falsification_test="Call check('')",
                    )
                    pkt = build_swarm_packet(
                        conn,
                        stage="falsify",
                        worker_id="w-fals",
                    )
                    self.assertEqual(pkt["items"][0]["id"], clm["claim_id"])
                    self.assertEqual(pkt["items"][0]["title"], "Empty token accepted")
                    self.assertIn("Prefix comparison", pkt["items"][0]["mechanism"])
                    self.assertIn("Empty string returns False", pkt["packet_markdown"])
                    self.assertIn("Call check('')", pkt["packet_markdown"])
                    self.assertNotIn("SELECT claim_id", pkt["packet_markdown"])
                finally:
                    conn.close()

    def test_repro_try_slot_pool_stale_git_lock_heal_failure_receipt_and_doctor_prune(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            ajar_home = base / "ajar_home"
            target = _make_git_target(base)
            with mock.patch.dict(os.environ, {"AJAR_HOME": str(ajar_home)}):
                init_run_workspace(
                    target=str(target),
                    target_mode="source",
                    workspace_mode="in_place",
                    run_id="run-repro-ops",
                    ajar_home=ajar_home,
                )
                rdir = ajar_home / "runs" / "run-repro-ops"

                # 1. Hold slot-0.lock -> run_repro_try MUST acquire slot-1 (non-contending 8-slot pool)!
                repro_dir = rdir / "repro"
                repro_dir.mkdir(parents=True, exist_ok=True)
                lock0 = open(repro_dir / "slot-0.lock", "a+", encoding="utf-8")
                fcntl.flock(lock0.fileno(), fcntl.LOCK_EX)
                try:
                    res_try = run_repro_try(
                        run_dir=rdir,
                        target_dir=target,
                        cmd="python3 -c 'import app; assert app.check(\"secret-expected\")'",
                    )
                    self.assertTrue(res_try["ok"])
                    self.assertEqual(res_try["slot_index"], 1)
                    self.assertTrue((repro_dir / "slot-1").is_dir())
                finally:
                    fcntl.flock(lock0.fileno(), fcntl.LOCK_UN)
                    lock0.close()

                # 2. Plant stale .git/index.lock inside slot-1 -> _prepare_slot_worktree auto-heals it!
                mirror_dir = init_source_mirror(rdir, target)
                slot1 = repro_dir / "slot-1"
                stale_lock = slot1 / ".git" / "index.lock"
                stale_lock.write_text("stale", encoding="utf-8")
                self.assertTrue(stale_lock.is_file())
                _prepare_slot_worktree(mirror_dir, slot1)
                self.assertFalse(stale_lock.exists())

                # 3. Failing run_source_reproduction persists replayable scrubbed failure receipt!
                fake_tok = "ghp_" + ("1234567890" * 3) + "123456"
                res_fail = run_source_reproduction(
                    run_dir=rdir,
                    target_dir=target,
                    claim_id="clm-fail-1",
                    poc_cmd=f"python3 -c 'print(\"token={fake_tok}\")'",
                    control_cmd="python3 -c 'pass'",
                    micropatch_path=rdir / "does-not-exist.diff",
                )
                self.assertFalse(res_fail["passed"])
                rel_art = str(res_fail.get("failure_artifact") or "")
                self.assertTrue(rel_art.startswith("repro/failures/clm-fail-1-"))
                art_path = rdir / rel_art
                self.assertTrue(art_path.is_file())
                art_raw = art_path.read_text(encoding="utf-8")
                self.assertNotIn(fake_tok, art_raw)
                art_json = json.loads(art_raw)
                self.assertEqual(art_json["schema"], "ajar-repro-failure/1")
                self.assertEqual(art_json["claim_id"], "clm-fail-1")

                # 4. `ajar doctor --run <id> --prune-slots` reports health, skips locked slots, prunes unlocked slots!
                slot0 = repro_dir / "slot-0"
                _prepare_slot_worktree(mirror_dir, slot0)
                lock0b = open(repro_dir / "slot-0.lock", "a+", encoding="utf-8")
                fcntl.flock(lock0b.fileno(), fcntl.LOCK_EX)
                try:
                    rc_doc, doc = _run_cli(["doctor", "--run", "run-repro-ops", "--prune-slots", "--json"])
                    self.assertEqual(rc_doc, 0)
                    rh = doc["run_health"]
                    assert isinstance(rh, dict)
                    self.assertTrue(rh["db_quick_check_ok"])
                    self.assertEqual(rh["failure_artifacts"], 1)
                    self.assertIn("slot-1", rh["pruned_slots"])
                    self.assertNotIn("slot-0", rh["pruned_slots"])
                    self.assertTrue(slot0.exists())
                    self.assertFalse(slot1.exists())
                finally:
                    fcntl.flock(lock0b.fileno(), fcntl.LOCK_UN)
                    lock0b.close()


if __name__ == "__main__":
    unittest.main()
