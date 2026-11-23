"""Unit and integration tests for Wave-C Track C2 (`QD-Islands`, Lyapunov `Phi(t)`, and 2-strike chain pivot)."""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import subprocess
import tempfile
import time
import unittest
from unittest import mock

from ajar import EXIT_GATE_BLOCKED, EXIT_OK
from ajar.cli import main as cli_main
from ajar.db import (
    canonical_island_key,
    checkpoint_task,
    compute_epistemic_delta,
    compute_epistemic_potential,
    compute_island_illumination,
    compute_task_salience,
    evaluate_chain_failure_streak,
    lease_next_task,
    log_event,
    open_run_db,
    record_coverage_span,
    run_dir_for,
    set_certified_binding,
    utc_now_iso,
)
from ajar.domain import AjarError
from ajar.hooks import evaluate_claude_stop_hook
from ajar.repro_source import capture_slot_post_state_snapshot
from ajar.services import (
    build_worker_dispatch_brief,
    detect_worker_stagnation,
    plan_swarm_wave,
    preflight_chain_proposal,
)
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
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Ajar Test",
        "GIT_AUTHOR_EMAIL": "ajar@example.com",
        "GIT_COMMITTER_NAME": "Ajar Test",
        "GIT_COMMITTER_EMAIL": "ajar@example.com",
    }
    subprocess.run(["git", "init", "-q"], cwd=repo_dir, check=True, env=env)
    for rel, content in files.items():
        fp = repo_dir / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, env=env)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo_dir, check=True, env=env)


class TestWaveC2QdIslandsLyapunovAndStagnation(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="ajar-wave-c2-")
        self.base = pathlib.Path(self._tmp.name)
        self.ajar_home = self.base / "ajar-home"
        self.target = self.base / "target"
        _init_git_repo(
            self.target,
            {
                "unpack.c": "int unpack_entry_patch(int x) { return x + 1; }\n",
                "unpack-check.c": "int check_patch(int x) { return x > 0; }\n",
                "unpack-links.c": "int check_sym(int x) { return x > 1; }\n",
                "merge.c": "int merge_trees(int x) { return x * 2; }\n",
                "pack.c": "int unpack_entry(int x) { return x - 1; }\n",
                "channel.c": "int recv_frame(int x) { return x + 3; }\n",
                "indexdb.c": "int resolve_idx(int x) { return x + 4; }\n",
                "chain_app.py": (
                    "import os, sys\n"
                    "ablate = set(filter(None, os.environ.get('AJAR_ABLATE_STEPS', '').split(',')))\n"
                    "mode = sys.argv[1] if len(sys.argv) > 1 else 'benign'\n"
                    "if mode == 'exploit' and not ablate:\n"
                    "    print('CHAIN_DEFECT_FIRED')\n"
                    "    raise SystemExit(1)\n"
                    "raise SystemExit(0)\n"
                ),
            },
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_qd_islands_uncapped_deme_firewall_ready_door_exemption_and_wave_cap(self) -> None:
        # Inconsistent `--subsystem` labels on sibling files must resolve to the same canonical island.
        self.assertEqual(canonical_island_key("unpack.c:10", "unpack.c"), "isl:unpack")
        self.assertEqual(canonical_island_key("unpack-check.c:5", "unpack-hooks"), "isl:unpack")
        self.assertEqual(canonical_island_key("src/auth/login.py:4", "auth"), "isl:src/auth")

        rc, init_out = _run_cli(
            [
                "init",
                str(self.target),
                "--run-id",
                "run-c2-qd",
                "--stopping",
                "crown-jewel",
                "--phase",
                "hunt",
                "--uncapped",
                "--allow-historical-target",
                "--json",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc, EXIT_OK, init_out)
        self.assertEqual(init_out["pricing_mode"], "uncapped_research")
        self.assertEqual(float(init_out["cogs_cap_usd"]), 0.0)  # type: ignore[arg-type]

        conn = open_run_db("run-c2-qd", ajar_home=self.ajar_home)
        try:
            now = utc_now_iso()
            with immediate_tx(conn):
                for idx, rel in enumerate(
                    ("unpack.c", "unpack-check.c", "unpack-links.c", "merge.c", "pack.c", "channel.c", "indexdb.c")
                ):
                    conn.execute(
                        "INSERT INTO repomap_symbols(symbol_id, rel_path, name, kind, line_no, pagerank) VALUES (?, ?, ?, 'fn', 1, 0.1)",
                        (f"sym-{idx}", rel, f"fn_{idx}"),
                    )

                # Enqueue initial explore tasks across 5 islands (`L_explore == 0`).
                for tid, loc, sub in (
                    ("t-unpack-1", "unpack.c:1", "unpack.c"),
                    ("t-unpack-2", "unpack-check.c:1", "unpack-hooks"),
                    ("t-unpack-3", "unpack-links.c:1", "unpack-sym"),
                    ("t-unpack-4", "unpack-check.c:2", "unpack-hooks"),
                    ("t-unpack-5", "unpack-links.c:2", "unpack-sym"),
                    ("t-merge-1", "merge.c:1", "merge"),
                    ("t-pack-1", "pack.c:1", "pack"),
                    ("t-trans-1", "channel.c:1", "transport"),
                    ("t-refs-1", "indexdb.c:1", "refs"),
                ):
                    sal0 = compute_task_salience(
                        conn,
                        {"kind": "investigate", "priority": "high", "locus": loc, "subsystem": sub},
                    )
                    # At L_explore == 0, salience_adjustment MUST be 0 (exact baseline 60).
                    self.assertEqual(sal0, 60)
                    conn.execute(
                        """
                        INSERT INTO tasks(
                            task_id, kind, direction, title, subsystem, locus,
                            priority, status, salience_score, created_at, updated_at
                        ) VALUES (?, 'investigate', 'outside_in', ?, ?, ?, 'high', 'open', ?, ?, ?)
                        """,
                        (tid, f"Audit {loc}", sub, loc, sal0, now, now),
                    )

                # Consume 3 explore leases inside `isl:unpack` and record a `stepping_stone` finding (`consecutive_dry == 0`).
                for done_tid in ("t-unpack-1", "t-unpack-2", "t-unpack-3"):
                    conn.execute(
                        "UPDATE tasks SET status = 'done', worker_id = 'w-1', closed_epoch = ?, updated_at = ? WHERE task_id = ?",
                        (time.time(), now, done_tid),
                    )
                conn.execute(
                    """
                    INSERT INTO claims(
                        claim_id, proposer_worker_id, falsifier_worker_id, title, subsystem, locus,
                        mechanism, mechanism_key, severity, falsification_prediction, falsification_test,
                        status, research_state, evidence_state, created_at, updated_at
                    ) VALUES (
                        'clm-app1', 'w1', 'w2', 'Stepping stone in unpack', 'unpack.c', 'unpack.c:1',
                        'm', 'm', 'medium', 'pred', 'test', 'reproduced', 'confirmed', 'reproduced', ?, ?
                    )
                    """,
                    (now, now),
                )
                conn.execute(
                    """
                    INSERT INTO findings(
                        finding_id, claim_id, title, severity, locus, root_cause, poc_cmd, control_cmd,
                        arm1_clean_poc_json, arm2_clean_ctrl_json, arm3_patch_poc_json, arm4_patch_ctrl_json,
                        realism_tier, attribution, created_at
                    ) VALUES (
                        'fnd-app1', 'clm-app1', 'Stepping stone in unpack', 'medium', 'unpack.c:1', 'm', 'true', 'true',
                        '{}', '{}', '{}', '{}', 'stepping_stone', 'found_autonomously_by_ajar', ?
                    )
                    """,
                    (now,),
                )

            illum = compute_island_illumination(conn)
            self.assertEqual(illum["island_count"], 5)
            self.assertEqual(illum["illuminated_count"], 1)
            self.assertAlmostEqual(float(illum["global_illumination"]), 0.20, places=3)
            self.assertTrue(illum["islands"]["isl:unpack"]["over_mined"])
            self.assertEqual(illum["islands"]["isl:unpack"]["salience_adjustment"], -25)
            for untouched in ("isl:merge", "isl:pack", "isl:channel", "isl:indexdb"):
                self.assertTrue(illum["islands"][untouched]["under_explored"])
                self.assertEqual(illum["islands"][untouched]["salience_adjustment"], 12)

            # Wave planner with max_workers=4 fills all 4 slots with untouched `+12` islands (`0` slots wasted on `isl:unpack`).
            plan = plan_swarm_wave(conn, max_workers=4, enqueue_missing=False)
            self.assertEqual(plan["island_illumination"]["island_count"], 5)
            wave_islands = [w["island"] for w in plan["wave"]]
            self.assertEqual(
                set(wave_islands),
                {"isl:merge", "isl:pack", "isl:channel", "isl:indexdb"},
            )

            # With max_workers=5 (`ceil(0.25 * 4) == 1` vs `ceil(0.25 * 5) == 2`): add a 3rd distinct-file apply task
            # so `isl:unpack` hits `over_mined_wave_cap` even when spare worker slots remain!
            with immediate_tx(conn):
                conn.execute(
                    """
                    INSERT INTO tasks(
                        task_id, kind, direction, title, subsystem, locus,
                        priority, status, salience_score, created_at, updated_at
                    ) VALUES ('t-unpack-6', 'investigate', 'outside_in', 'Audit unpack.c extra', 'unpack', 'unpack.c:2', 'high', 'open', 60, ?, ?)
                    """,
                    (now, now),
                )
            plan_cap = plan_swarm_wave(conn, max_workers=8, enqueue_missing=False)
            # For max_workers=8, over_mined_wave_cap = ceil(0.25 * 8) = 2, while 3 distinct-file unpack tasks are open (`unpack.c`, `unpack-check.c`, `unpack-links.c`)!
            unpack_in_wave = [w for w in plan_cap["wave"] if w["island"] == "isl:unpack"]
            self.assertEqual(len(unpack_in_wave), 2)
            self.assertEqual(len(plan_cap["deferred_island_cap_tasks"]), 1)

            # `lease_next_task` dispatches an untouched `+12` island next (`72 > 55`)!
            leased = lease_next_task(conn, worker_id="w-2", kind="investigate")
            self.assertIsNotNone(leased)
            assert leased is not None
            self.assertIn(leased["task_id"], {"t-merge-1", "t-pack-1", "t-trans-1", "t-refs-1"})

            # Ready Open Door in `isl:unpack` exempts `isl:unpack` from over-mined throttling!
            with immediate_tx(conn):
                conn.execute(
                    """
                    INSERT INTO parked_doors(
                        door_id, direction, anchor_locus, blocker_locus, subsystem,
                        missing_link_summary, wishlist_query, status, created_at, updated_at
                    ) VALUES (
                        'door-ready-1', 'sink_to_source', 'unpack-check.c:2', 'unpack.c:1', 'unpack',
                        'Ready bridge into unpack sink', 'unpack_entry_patch', 'ready', ?, ?
                    )
                    """,
                    (now, now),
                )
            illum_exempt = compute_island_illumination(conn)
            self.assertTrue(illum_exempt["islands"]["isl:unpack"]["has_ready_door"])
            self.assertFalse(illum_exempt["islands"]["isl:unpack"]["over_mined"])
            self.assertEqual(illum_exempt["islands"]["isl:unpack"]["salience_adjustment"], 0)
        finally:
            conn.close()

        # Verify `ajar lead throttles` and `ajar status` surface `island_illumination`.
        rc_lt, lt_out = _run_cli(["lead", "throttles", "--run", "run-c2-qd"], self.ajar_home)
        self.assertEqual(rc_lt, EXIT_OK, lt_out)
        self.assertIn("island_illumination", lt_out)
        self.assertIn("over_mined_islands", lt_out)

        rc_st, st_out = _run_cli(["status", "--run", "run-c2-qd"], self.ajar_home)
        self.assertEqual(rc_st, EXIT_OK, st_out)
        self.assertIn("island_illumination", st_out)
        self.assertIn("epistemic_potential", st_out)
        self.assertIn("delta_phi", st_out)

    def test_lyapunov_epistemic_potential_zero_churn_stop_hook_pulse_and_status(self) -> None:
        rc, _ = _run_cli(
            [
                "init",
                str(self.target),
                "--run-id",
                "run-c2-phi",
                "--allow-historical-target",
                "--json",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc, EXIT_OK)

        conn = open_run_db("run-c2-phi", ajar_home=self.ajar_home)
        try:
            now = utc_now_iso()
            with immediate_tx(conn):
                conn.execute(
                    """
                    INSERT INTO surfaces(surface_id, name, kind, subsystem, locus, priority, created_at)
                    VALUES ('surf-phi', 'Unpack', 'cli', 'unpack', 'unpack.c:1', 'high', ?)
                    """,
                    (now,),
                )
                conn.execute(
                    """
                    INSERT INTO tasks(task_id, surface_id, kind, title, subsystem, locus, priority, status, salience_score, created_at, updated_at)
                    VALUES ('tsk-phi', 'surf-phi', 'investigate', 'Explore unpack', 'unpack', 'unpack.c:1', 'high', 'open', 60, ?, ?)
                    """,
                    (now, now),
                )

            self.assertEqual(compute_epistemic_potential(conn)["epistemic_potential"], 0.0)

            # Check #1: establishes baseline (`has_prior_checkpoint == False`) -> `stalls == 0`, blocks exit.
            rc1, p1 = evaluate_claude_stop_hook(conn, target_dir=self.target)
            self.assertNotEqual(rc1, EXIT_OK)
            self.assertEqual(p1["decision"], "block")
            self.assertEqual(p1["stalls"], 0)
            self.assertEqual(p1["epistemic_potential"], 0.0)

            # Emit 10 bureaucratic / unverified churn events between stop checks -> `delta_phi` MUST stay 0.0!
            churn_events = [
                ("operator", "finding_calibrated", "fnd-0", {"new_severity": "medium"}),
                ("operator", "chain_calibrated", "chn-0", {"realism_tier": "stepping_stone"}),
                ("w-1", "lead_vote_cast", "vot-1", {"ev_score": 88.0}),
                ("w-1", "task_leased", "tsk-phi", {"kind": "investigate"}),
                ("w-1", "task_checkpointed", "tsk-phi", {"step": 1}),
                ("w-1", "claim_proposed", "clm-tmp", {"locus": "unpack.c:1"}),
                ("w-2", "claim_survived_falsify", "clm-tmp", {}),
                ("w-2", "claim_repro_failed", "clm-tmp", {"failed_repro_count": 1}),
                ("w-2", "chain_proposed", "chn-unv", {"verified": False, "steps": ["prim-x"]}),
                ("w-2", "claim_marked_duplicate", "clm-dup", {"duplicate_of_claim_id": "clm-tmp"}),
            ]
            with immediate_tx(conn):
                conn.execute(
                    """
                    INSERT INTO claims(
                        claim_id, proposer_worker_id, title, subsystem, locus, mechanism, mechanism_key,
                        severity, falsification_prediction, falsification_test, status, created_at, updated_at
                    ) VALUES ('clm-tmp', 'w-1', 'Candidate', 'unpack', 'unpack.c:1', 'm', 'm', 'high', 'pred', 'true', 'survived_falsify', ?, ?)
                    """,
                    (now, now),
                )
                conn.execute(
                    """
                    INSERT INTO chains(chain_id, title, severity, step_ids_json, e2e_poc_cmd, control_cmd, verified, created_at)
                    VALUES ('chn-unv', 'Unverified chain', 'high', '["prim-x"]', 'false', 'true', 0, ?)
                    """,
                    (now,),
                )
                for actor, action, eid, pld in churn_events:
                    log_event(conn, actor, action, eid, pld)

            ep_after_churn = compute_epistemic_delta(conn, reference_actions=("stop_hook_check",))
            self.assertEqual(ep_after_churn["epistemic_potential"], 0.0)
            self.assertEqual(ep_after_churn["delta_phi"], 0.0)

            # Checks #2, #3 increment stalls to 1, 2; Check #4 trips `stalled_release`!
            _, p2 = evaluate_claude_stop_hook(conn, target_dir=self.target)
            self.assertEqual(p2["stalls"], 1)
            self.assertEqual(p2["delta_phi"], 0.0)

            _, p3 = evaluate_claude_stop_hook(conn, target_dir=self.target)
            self.assertEqual(p3["stalls"], 2)

            rc4, p4 = evaluate_claude_stop_hook(conn, target_dir=self.target)
            self.assertEqual(rc4, EXIT_OK)
            self.assertEqual(p4["decision"], "approve")
            self.assertTrue(p4.get("stalled_release"))
            self.assertEqual(p4["delta_phi"], 0.0)

            # Genuine SHA-bound certified binding (`+2.0`) resets stalls to `0`!
            conn.execute("UPDATE runs SET consecutive_stall_checks = 2, stop_reason = ''")
            set_certified_binding(
                conn,
                target_dir=self.target,
                name="MAX_PATCH_DEPTH",
                value="64",
                locus="unpack.c:1",
                task_id="tsk-phi",
                actor="w-1",
            )
            rc5, p5 = evaluate_claude_stop_hook(conn, target_dir=self.target)
            self.assertNotEqual(rc5, EXIT_OK)
            self.assertEqual(p5["stalls"], 0)
            self.assertEqual(p5["epistemic_potential"], 2.0)
            self.assertEqual(p5["delta_phi"], 2.0)

            # Duplicate coverage spans yield `delta_phi == 0.0`, and per-task LOC is capped at 2000 (`<= +2.0`).
            record_coverage_span(
                conn,
                target_dir=self.target,
                task_id="tsk-phi",
                worker_id="w-1",
                rel_path="unpack.c",
                start_line=1,
                end_line=1,
            )
            phi_cov1 = compute_epistemic_potential(conn)["epistemic_potential"]
            record_coverage_span(
                conn,
                target_dir=self.target,
                task_id="tsk-phi",
                worker_id="w-1",
                rel_path="unpack.c",
                start_line=1,
                end_line=1,
            )
            phi_cov_dup = compute_epistemic_potential(conn)["epistemic_potential"]
            self.assertEqual(phi_cov1, phi_cov_dup)
        finally:
            conn.close()

        # Verify `ajar pulse` surfaces `epistemic_potential` and `delta_phi == 0.0` on repeat pulse.
        rc_pl1, pl1 = _run_cli(["pulse", "--run", "run-c2-phi"], self.ajar_home)
        self.assertEqual(rc_pl1, EXIT_OK, pl1)
        self.assertGreater(float(pl1["epistemic_potential"]), 2.0)  # type: ignore[arg-type]

        rc_pl2, pl2 = _run_cli(["pulse", "--run", "run-c2-phi"], self.ajar_home)
        self.assertEqual(rc_pl2, EXIT_OK, pl2)
        self.assertEqual(float(pl2["delta_phi"]), 0.0)  # type: ignore[arg-type]

    def test_two_strike_chain_telemetry_pivot_and_worker_stagnation_guard(self) -> None:
        _run_cli(
            [
                "init",
                str(self.target),
                "--run-id",
                "run-c2-chain",
                "--stopping",
                "crown-jewel",
                "--phase",
                "hunt",
                "--allow-historical-target",
                "--json",
            ],
            self.ajar_home,
        )
        _, p1 = _run_cli(
            [
                "primitive",
                "add",
                "--run",
                "run-c2-chain",
                "--locus",
                "unpack.c:1",
                "--kind",
                "stage_write",
                "--role",
                "capability",
                "--preconditions",
                "untrusted patch",
                "--postconditions",
                "stages file",
                "--provides-tags",
                "cap:stage1",
                "--evidence-cmd",
                "true",
            ],
            self.ajar_home,
        )
        _, p2 = _run_cli(
            [
                "primitive",
                "add",
                "--run",
                "run-c2-chain",
                "--locus",
                "chain_app.py:2",
                "--kind",
                "stage_exec",
                "--role",
                "capability",
                "--preconditions",
                "cap:stage1",
                "--postconditions",
                "triggers defect",
                "--requires-tags",
                "cap:stage1",
                "--provides-tags",
                "cap:rce",
                "--evidence-cmd",
                "true",
            ],
            self.ajar_home,
        )
        prim1 = str(p1["primitive_id"])
        prim2 = str(p2["primitive_id"])

        # Seed a real Stage-1 post-state snapshot (`snp-*`) so `chain probe --from-snapshot` can hydrate it.
        rdir = run_dir_for("run-c2-chain", self.ajar_home)
        slot0 = rdir / "repro" / "slot-0"
        slot0.mkdir(parents=True, exist_ok=True)
        (slot0 / "stage1_state.txt").write_text("SNAPSHOT_OK\n", encoding="utf-8")
        snap = capture_slot_post_state_snapshot(
            run_dir=rdir,
            slot_dir=slot0,
            claim_id="clm-snap",
            rel_dir=".",
            source_cmd="true",
        )
        snap_id = str(snap["snapshot_id"])

        conn = open_run_db("run-c2-chain", ajar_home=self.ajar_home)
        try:
            now = utc_now_iso()
            with immediate_tx(conn):
                conn.execute(
                    """
                    INSERT INTO repro_snapshots(
                        snapshot_id, claim_id, rel_dir, archive_path, sha256, size_bytes, manifest_json, source_cmd, created_at
                    ) VALUES (?, 'clm-snap', '.', ?, ?, ?, '{}', 'true', ?)
                    """,
                    (snap_id, str(snap["archive_path"]), str(snap["sha256"]), int(snap["size_bytes"]), now),
                )
                conn.execute(
                    """
                    INSERT INTO tasks(
                        task_id, kind, direction, title, subsystem, locus, priority, status, salience_score, summary, created_at, updated_at
                    ) VALUES (
                        'tsk-chain-1', 'chain', 'outside_in', ?, 'chain_app.py', 'chain_app.py:2', 'critical', 'open', 98, ?, ?, ?
                    )
                    """,
                    (f"Compose {prim1},{prim2}", f"Percolated multi-hop path [{prim1},{prim2}]", now, now),
                )
        finally:
            conn.close()

        # Strike 1: unverified chain proposal -> `chain_probe_required == False`, `unprobed_failures == 1`.
        rc_f1, out_f1 = _run_cli(
            [
                "chain",
                "propose",
                "--run",
                "run-c2-chain",
                "--worker",
                "w-chain",
                "--title",
                "Blind attempt 1",
                "--steps",
                f"{prim1},{prim2}",
                "--poc-cmd",
                "python3 chain_app.py benign # $AJAR_ABLATE_STEPS",
                "--control-cmd",
                "python3 chain_app.py benign",
                "--oracle-json",
                '{"expect_regex":"CHAIN_DEFECT_FIRED"}',
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_f1, EXIT_GATE_BLOCKED, out_f1)
        self.assertFalse(out_f1["verified"])
        self.assertEqual(out_f1["unprobed_failures"], 1)
        self.assertFalse(out_f1["chain_probe_required"])

        # Strike 2: 2nd consecutive unverified proposal -> `chain_probe_required == True` + `pivot_hint`!
        rc_f2, out_f2 = _run_cli(
            [
                "chain",
                "propose",
                "--run",
                "run-c2-chain",
                "--worker",
                "w-chain",
                "--title",
                "Blind attempt 2",
                "--steps",
                f"{prim1},{prim2}",
                "--poc-cmd",
                "python3 chain_app.py benign # $AJAR_ABLATE_STEPS",
                "--control-cmd",
                "python3 chain_app.py benign",
                "--oracle-json",
                '{"expect_regex":"CHAIN_DEFECT_FIRED"}',
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_f2, EXIT_GATE_BLOCKED, out_f2)
        self.assertFalse(out_f2["verified"])
        self.assertEqual(out_f2["unprobed_failures"], 2)
        self.assertTrue(out_f2["chain_probe_required"])
        self.assertIn(f"ajar chain probe --from-snapshot {snap_id}", str(out_f2["pivot_hint"]))

        # Worker dispatch brief surfaces `chain_probe_required == True` and actionable `--from-snapshot` guidance.
        conn = open_run_db("run-c2-chain", ajar_home=self.ajar_home)
        try:
            brief = build_worker_dispatch_brief(conn, task_id="tsk-chain-1", worker_id="w-chain")
            self.assertTrue(brief["chain_probe_required"])
            self.assertIn(f"ajar chain probe --from-snapshot {snap_id}", str(brief["rendered_brief"]))
            self.assertLess(len(str(brief["rendered_brief"]).splitlines()), 40)

            with self.assertRaises(AjarError) as pf_ctx:
                preflight_chain_proposal(conn, [prim1, prim2])
            self.assertEqual(pf_ctx.exception.exit_code, EXIT_GATE_BLOCKED)
            self.assertTrue(pf_ctx.exception.details.get("chain_probe_required"))
        finally:
            conn.close()

        # Strike 3 (blind CLI retry without probing): hard-blocked by pre-flight gate!
        rc_f3, out_f3 = _run_cli(
            [
                "chain",
                "propose",
                "--run",
                "run-c2-chain",
                "--worker",
                "w-chain",
                "--title",
                "Blind attempt 3",
                "--steps",
                f"{prim1},{prim2}",
                "--poc-cmd",
                "python3 chain_app.py exploit # $AJAR_ABLATE_STEPS",
                "--control-cmd",
                "python3 chain_app.py benign",
                "--oracle-json",
                '{"expect_regex":"CHAIN_DEFECT_FIRED"}',
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_f3, EXIT_GATE_BLOCKED)
        self.assertIn("Chain telemetry-pivot gate", str(out_f3.get("_stderr") or out_f3))

        # Running `ajar chain probe --from-snapshot <snp_id>` records intermediate telemetry and unblocks `chain propose`!
        rc_prb, out_prb = _run_cli(
            [
                "chain",
                "probe",
                "--run",
                "run-c2-chain",
                "--worker",
                "w-chain",
                "--from-snapshot",
                snap_id,
                "--cmd",
                "test -f stage1_state.txt",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_prb, EXIT_OK, out_prb)

        conn = open_run_db("run-c2-chain", ajar_home=self.ajar_home)
        try:
            streak_after = evaluate_chain_failure_streak(conn, steps=[prim1, prim2])
            self.assertEqual(streak_after["unprobed_failures"], 0)
            self.assertFalse(streak_after["chain_probe_required"])
        finally:
            conn.close()

        rc_ok, out_ok = _run_cli(
            [
                "chain",
                "propose",
                "--run",
                "run-c2-chain",
                "--worker",
                "w-chain",
                "--title",
                "Probed verified chain",
                "--steps",
                f"{prim1},{prim2}",
                "--poc-cmd",
                "python3 chain_app.py exploit # $AJAR_ABLATE_STEPS",
                "--control-cmd",
                "python3 chain_app.py benign",
                "--oracle-json",
                '{"expect_regex":"CHAIN_DEFECT_FIRED"}',
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_ok, EXIT_OK, out_ok)
        self.assertTrue(out_ok["verified"])
        self.assertFalse(out_ok["chain_probe_required"])

        # Test intra-worker stagnation detection (`>= 3` zero-Phi checkpoints) + expired lease direction rotation!
        conn = open_run_db("run-c2-chain", ajar_home=self.ajar_home)
        try:
            now = utc_now_iso()
            with immediate_tx(conn):
                conn.execute(
                    """
                    INSERT INTO tasks(
                        task_id, kind, direction, title, subsystem, locus, priority,
                        status, worker_id, lease_expires_at, attempt_count, salience_score, created_at, updated_at
                    ) VALUES (
                        'tsk-stag-inv', 'investigate', 'outside_in', 'Stuck outer trace', 'merge', 'merge.c:1', 'high',
                        'leased', 'w-stuck', ?, 1, 60, ?, ?
                    )
                    """,
                    (time.time() - 30.0, now, now),
                )
            for idx in range(3):
                checkpoint_task(conn, task_id="tsk-stag-inv", worker_id="w-stuck", state_dict={"iter": idx})
            stag = detect_worker_stagnation(conn, worker_id="w-stuck", task_id="tsk-stag-inv")
            self.assertTrue(stag["stagnant"])
            self.assertGreaterEqual(int(stag["consecutive_zero_phi_events"]), 3)

            plan = plan_swarm_wave(conn, max_workers=4)
            stag_wids = {s["worker_id"] for s in plan["stagnant_workers"]}
            self.assertIn("w-stuck", stag_wids)

            rot_row = conn.execute(
                "SELECT status, attempt_count, direction FROM tasks WHERE task_id = 'tsk-stag-inv'"
            ).fetchone()
            self.assertEqual(rot_row["status"], "open")
            self.assertEqual(int(rot_row["attempt_count"]), 2)
            self.assertEqual(rot_row["direction"], "inside_out")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
