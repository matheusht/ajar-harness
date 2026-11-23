"""Wave-C Track C1 tests: conjunctive percolation, full-pair AH-PUCT cut-lemma scoring, and H9_INVARIANT_SYMMETRY."""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock

from ajar import EXIT_OK
from ajar.chain_planner import (
    add_crown_jewel,
    ah_puct_score,
    detect_percolated_multi_hop_paths,
    mark_chain_doors_and_jewels_resolved,
)
from ajar.cli import main as cli_main
from ajar.db import open_run_db, render_task_context, run_pulse, utc_now_iso
from ajar.domain.enums import HookCode
from ajar.epistemic_hooks import HOOK_CODES
from ajar.services import add_primitive, add_surface
from ajar.workspace import init_run_workspace


def _git_init_repo(repo_dir: pathlib.Path, files: dict[str, str]) -> None:
    repo_dir.mkdir(parents=True, exist_ok=True)
    for rel, body in files.items():
        fpath = repo_dir / rel
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(body, encoding="utf-8")
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }
    subprocess.run(["git", "-C", str(repo_dir), "init", "-q"], check=True, env=env)
    subprocess.run(["git", "-C", str(repo_dir), "add", "."], check=True, env=env)
    subprocess.run(["git", "-C", str(repo_dir), "commit", "-q", "-m", "init"], check=True, env=env)


def _run_cli(argv: list[str], ajar_home: pathlib.Path) -> tuple[int, dict[str, object]]:
    out, err = io.StringIO(), io.StringIO()
    with (
        mock.patch.dict(os.environ, {"AJAR_HOME": str(ajar_home)}),
        contextlib.redirect_stdout(out),
        contextlib.redirect_stderr(err),
    ):
        try:
            rc = int(cli_main(argv) or 0)
        except SystemExit as exc:
            rc = int(exc.code or 0)
    raw = out.getvalue().strip() or err.getvalue().strip()
    payload: dict[str, object] = {}
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                payload = parsed
        except json.JSONDecodeError:
            payload = {"raw": raw}
    return rc, payload


class TestWaveC1ChainPuctAndH9(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="ajar-c1-")
        self.tmp_path = pathlib.Path(self._tmp.name)
        self.ajar_home = self.tmp_path / "ajar_home"
        self.target = self.tmp_path / "target"
        _git_init_repo(
            self.target,
            {
                "src/entry.c": "int entry(int x) { return x; }\n",
                "src/guard.c": "int check_bounds(int x) { return x >= 0; }\n",
                "src/cap.c": "int run_cap(int x) { return x + 1; }\n",
                "src/manifest.c": "int manifest_parse(void) { return 0; }\n",
                "src/channel.c": "int chan_handoff(void) { return 0; }\n",
                "src/run_cmd.c": "int exec_sink(void) { return 0; }\n",
            },
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _open_initialized_run(self, run_id: str) -> None:
        with mock.patch.dict(os.environ, {"AJAR_HOME": str(self.ajar_home)}):
            init_run_workspace(
                target=str(self.target),
                target_mode="source",
                workspace_mode="in_place",
                stopping_criterion="crown-jewel",
                run_id=run_id,
                ajar_home=self.ajar_home,
                allow_historical_target=True,
            )

    def test_h9_invariant_symmetry_fires_on_guarded_capability_and_expires_after_one_lease(self) -> None:
        self.assertEqual(HookCode.H9_INVARIANT_SYMMETRY.value, "H9_INVARIANT_SYMMETRY")
        self.assertIn("H9_INVARIANT_SYMMETRY", HOOK_CODES)
        self.assertEqual(tuple(h.value for h in HookCode), HOOK_CODES)

        self._open_initialized_run("run-h9")
        rc, surf = _run_cli(
            [
                "surface",
                "add",
                "--run",
                "run-h9",
                "--name",
                "cap-entry",
                "--kind",
                "cli",
                "--locus",
                "src/entry.c:1",
                "--priority",
                "high",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc, EXIT_OK)
        rc, t_plain = _run_cli(
            [
                "task",
                "add",
                "--run",
                "run-h9",
                "--surface",
                str(surf["surface_id"]),
                "--kind",
                "investigate",
                "--locus",
                "src/entry.c:1",
                "--title",
                "Plain entry audit",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc, EXIT_OK)

        conn = open_run_db("run-h9", ajar_home=self.ajar_home)
        try:
            prefix_before = render_task_context(conn, str(t_plain["task_id"]))["certified_prefix"]
        finally:
            conn.close()

        # 1. `--role trust_gadget --guarded-by ...` triggers H1_GUARD_SYMMETRY ONLY (NOT H9_INVARIANT_SYMMETRY).
        rc_gad, prim_gad = _run_cli(
            [
                "primitive",
                "add",
                "--run",
                "run-h9",
                "--locus",
                "src/channel.c:1",
                "--kind",
                "handoff_gadget",
                "--role",
                "trust_gadget",
                "--trusted-invariant",
                "input already validated",
                "--guarded-by",
                "src/entry.c:1",
                "--preconditions",
                "reachable",
                "--postconditions",
                "forwards buffer",
                "--evidence-cmd",
                "true",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_gad, EXIT_OK)
        self.assertIn("H1_GUARD_SYMMETRY", prim_gad["hooks_triggered"])  # type: ignore[arg-type]
        self.assertNotIn("H9_INVARIANT_SYMMETRY", prim_gad["hooks_triggered"])  # type: ignore[arg-type]

        # 2. `--role capability --guarded-by src/guard.c:1` triggers BOTH H1 and H9 (`max_leases == 1`).
        rc_cap, prim_cap = _run_cli(
            [
                "primitive",
                "add",
                "--run",
                "run-h9",
                "--locus",
                "src/cap.c:1",
                "--kind",
                "signed_truncation",
                "--role",
                "capability",
                "--guarded-by",
                "src/guard.c:1",
                "--guard-assumption",
                "check_bounds blocks negative values",
                "--preconditions",
                "negative width slips past guard",
                "--postconditions",
                "signed truncation corrupts size",
                "--evidence-cmd",
                "true",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_cap, EXIT_OK)
        self.assertIn("H1_GUARD_SYMMETRY", prim_cap["hooks_triggered"])  # type: ignore[arg-type]
        self.assertIn("H9_INVARIANT_SYMMETRY", prim_cap["hooks_triggered"])  # type: ignore[arg-type]

        conn = open_run_db("run-h9", ajar_home=self.ajar_home)
        try:
            h9_row = conn.execute(
                "SELECT * FROM epistemic_hooks WHERE hook_code = 'H9_INVARIANT_SYMMETRY' AND source_entity_id = ?",
                (str(prim_cap["primitive_id"]),),
            ).fetchone()
            self.assertIsNotNone(h9_row)
            self.assertEqual(int(h9_row["max_leases"]), 1)
            self.assertEqual(int(h9_row["leases_seen"]), 0)
            self.assertEqual(str(h9_row["status"]), "active")
            self.assertIn("width/sign", str(h9_row["directive_text"]))
            self.assertIn("path-normalization/case-folding", str(h9_row["directive_text"]))
            self.assertIn("deferred-metadata", str(h9_row["directive_text"]))
            self.assertTrue(str(h9_row["kill_rule"]).startswith("STOP and mark dry"))
            spawned_tid = str(h9_row["spawned_task_id"])
            self.assertTrue(spawned_tid.startswith("task-"))

            # Verify Task Delta rendering and byte-identical Certified Run Prefix before exposure.
            ctx_guard = render_task_context(conn, spawned_tid, record_exposure=False)
            self.assertEqual(ctx_guard["certified_prefix"], prefix_before)
            self.assertIn("H9_INVARIANT_SYMMETRY", ctx_guard["active_hooks"])
            self.assertIn("H9_INVARIANT_SYMMETRY", str(ctx_guard["task_delta"]))
            self.assertIn("Kill Rule:", str(ctx_guard["task_delta"]))
        finally:
            conn.close()

        # 3. Lease the spawned guard task once (`leases_seen` becomes 1), close `done`, and run `ajar pulse`.
        rc_lease, lease_out = _run_cli(["task", "lease", "--run", "run-h9", "--worker", "w-guard"], self.ajar_home)
        self.assertEqual(rc_lease, EXIT_OK)
        leased_tid = str(lease_out["leased"]["task_id"])  # type: ignore[index]
        self.assertEqual(leased_tid, spawned_tid)
        self.assertIn("H9_INVARIANT_SYMMETRY", str(lease_out["leased"]["context"]))  # type: ignore[index]

        rc_cov, _ = _run_cli(
            [
                "coverage",
                "record",
                "src/guard.c",
                "--start-line",
                "1",
                "--end-line",
                "1",
                "--run",
                "run-h9",
                "--task",
                spawned_tid,
                "--worker",
                "w-guard",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_cov, EXIT_OK)
        rc_done, _ = _run_cli(
            [
                "task",
                "done",
                spawned_tid,
                "--run",
                "run-h9",
                "--worker",
                "w-guard",
                "--summary",
                "Completed single-pass invariant symmetry check on src/guard.c:1",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_done, EXIT_OK)

        conn = open_run_db("run-h9", ajar_home=self.ajar_home)
        try:
            pulse_res = run_pulse(conn, target_dir=self.target)
            self.assertGreaterEqual(int(pulse_res["expired_hooks"]), 1)
            h9_after = conn.execute(
                "SELECT status, leases_seen FROM epistemic_hooks WHERE hook_code = 'H9_INVARIANT_SYMMETRY' AND source_entity_id = ?",
                (str(prim_cap["primitive_id"]),),
            ).fetchone()
            h1_after = conn.execute(
                "SELECT status, leases_seen FROM epistemic_hooks WHERE hook_code = 'H1_GUARD_SYMMETRY' AND source_entity_id = ?",
                (str(prim_cap["primitive_id"]),),
            ).fetchone()
            self.assertEqual(str(h9_after["status"]), "expired")
            self.assertEqual(int(h9_after["leases_seen"]), 1)
            self.assertEqual(str(h1_after["status"]), "active")

            # Also verify `mark_chain_doors_and_jewels_resolved` consumes active H9 hooks on resolved chain steps.
            p2 = add_primitive(
                conn,
                kind="case_fold_desync",
                locus="src/manifest.c:1",
                preconditions="case-folded path",
                postconditions="bypasses check",
                evidence_cmd="true",
                guarded_by_locus="src/guard.c:1",
                role="capability",
            )
            p2_id = str(p2["primitive_id"])
            h9_p2_before = conn.execute(
                "SELECT status FROM epistemic_hooks WHERE hook_code = 'H9_INVARIANT_SYMMETRY' AND source_entity_id = ?",
                (p2_id,),
            ).fetchone()
            self.assertEqual(str(h9_p2_before["status"]), "active")
            mark_chain_doors_and_jewels_resolved(
                conn,
                chain_id="chn-resolved1",
                step_ids=[p2_id],
                realism_tier="high_impact",
            )
            h9_p2_after = conn.execute(
                "SELECT status FROM epistemic_hooks WHERE hook_code = 'H9_INVARIANT_SYMMETRY' AND source_entity_id = ?",
                (p2_id,),
            ).fetchone()
            self.assertEqual(str(h9_p2_after["status"]), "consumed")
        finally:
            conn.close()

    def test_conjunctive_three_tag_sink_rejects_partial_percolation_and_merges_sequential_and_parallel_roots(
        self,
    ) -> None:
        # Sub-test A: Sequential prefix accumulation (`P1 -> P2 -> P3 -> surf_conj`).
        self._open_initialized_run("run-conj-seq")
        conn = open_run_db("run-conj-seq", ajar_home=self.ajar_home)
        try:
            surf_conj = add_surface(
                conn,
                name="conjunctive-hook-sink",
                kind="cli",
                locus="src/run_cmd.c:1",
                priority="critical",
                requires_tags=["cap:path_norm", "cap:symlink_stage", "cap:hook_mode"],
            )
            sink_id = str(surf_conj["surface_id"])

            # 2-step partial decoy chain (`p0 -> p_decoy`) only provides 1 of 3 required tags (`cap:path_norm`).
            p0 = add_primitive(
                conn,
                kind="entry_seed",
                locus="src/entry.c:1",
                preconditions="untrusted archive",
                postconditions="emits cap:seed",
                evidence_cmd="true",
                provides_tags=["cap:seed"],
            )
            p_decoy = add_primitive(
                conn,
                kind="partial_norm",
                locus="src/manifest.c:1",
                preconditions="cap:seed",
                postconditions="emits cap:path_norm only",
                evidence_cmd="true",
                requires_tags=["cap:seed"],
                provides_tags=["cap:path_norm"],
                role="trust_gadget",
            )

            perc_1of3 = detect_percolated_multi_hop_paths(conn, enqueue_tasks=True)
            self.assertEqual(perc_1of3["percolated_paths"], [])
            self.assertEqual(perc_1of3["spawned_chain_tasks"], [])
            matching_gaps = [
                g
                for g in perc_1of3["unicorn_gaps"]
                if g["forward_tip_id"] == p_decoy["primitive_id"] and g["backward_entry_id"] == sink_id
            ]
            self.assertEqual(len(matching_gaps), 1)
            self.assertEqual(matching_gaps[0]["unmet_requires"], ["cap:hook_mode", "cap:symlink_stage"])
            self.assertEqual(matching_gaps[0]["forward_provides"], ["cap:path_norm", "cap:seed"])

            # 2 of 3 tags (`+ cap:symlink_stage`) still must NOT percolate prematurely!
            p2 = add_primitive(
                conn,
                kind="symlink_writer",
                locus="src/channel.c:1",
                preconditions="cap:path_norm",
                postconditions="emits cap:symlink_stage",
                evidence_cmd="true",
                requires_tags=["cap:path_norm"],
                provides_tags=["cap:symlink_stage"],
                role="trust_gadget",
            )
            perc_2of3 = detect_percolated_multi_hop_paths(conn, enqueue_tasks=True)
            self.assertEqual(perc_2of3["percolated_paths"], [])
            self.assertEqual(perc_2of3["spawned_chain_tasks"], [])
            gaps_2of3 = [
                g
                for g in perc_2of3["unicorn_gaps"]
                if g["forward_tip_id"] == p2["primitive_id"] and g["backward_entry_id"] == sink_id
            ]
            self.assertEqual(len(gaps_2of3), 1)
            self.assertEqual(gaps_2of3[0]["unmet_requires"], ["cap:hook_mode"])

            # Adding the 3rd tag along the sequential chain (`p2 -> p3`) unlocks all 3 conjuncts!
            p3 = add_primitive(
                conn,
                kind="hook_chmod",
                locus="src/cap.c:1",
                preconditions="cap:symlink_stage",
                postconditions="emits cap:hook_mode",
                evidence_cmd="true",
                requires_tags=["cap:symlink_stage"],
                provides_tags=["cap:hook_mode"],
                role="trust_gadget",
            )
            perc_3of3 = detect_percolated_multi_hop_paths(conn, enqueue_tasks=True)
            self.assertEqual(len(perc_3of3["percolated_paths"]), 1)
            self.assertEqual(
                perc_3of3["percolated_paths"][0]["step_ids"],
                [
                    str(p0["primitive_id"]),
                    str(p_decoy["primitive_id"]),
                    str(p2["primitive_id"]),
                    str(p3["primitive_id"]),
                ],
            )
            self.assertEqual(perc_3of3["percolated_paths"][0]["sink_id"], sink_id)
        finally:
            conn.close()

        # Sub-test B: Multi-root witness merge across independent grounded roots (`r1 + r2 + (r3a -> r3b) -> cjw`).
        self._open_initialized_run("run-conj-par")
        conn_par = open_run_db("run-conj-par", ajar_home=self.ajar_home)
        try:
            jwl = add_crown_jewel(
                conn_par,
                name="Conjunctive Crown Jewel",
                locus="src/run_cmd.c:1",
                impact_class="rce",
                symbols=["cap:path_norm", "cap:symlink_stage", "cap:hook_mode"],
            )
            r1 = add_primitive(
                conn_par,
                kind="root_norm",
                locus="src/entry.c:1",
                preconditions="untrusted input",
                postconditions="provides cap:path_norm",
                evidence_cmd="true",
                provides_tags=["cap:path_norm"],
            )
            r2 = add_primitive(
                conn_par,
                kind="root_symlink",
                locus="src/manifest.c:1",
                preconditions="untrusted input",
                postconditions="provides cap:symlink_stage",
                evidence_cmd="true",
                provides_tags=["cap:symlink_stage"],
            )
            # Only 2 of 3 independent roots present -> must NOT percolate yet.
            perc_par_2 = detect_percolated_multi_hop_paths(conn_par, enqueue_tasks=True)
            self.assertEqual(perc_par_2["percolated_paths"], [])

            # Add 2-step independent branch `r3a -> r3b` providing the 3rd conjunct `cap:hook_mode`.
            r3a = add_primitive(
                conn_par,
                kind="root_mode_seed",
                locus="src/channel.c:1",
                preconditions="untrusted input",
                postconditions="provides cap:mode_seed",
                evidence_cmd="true",
                provides_tags=["cap:mode_seed"],
            )
            r3b = add_primitive(
                conn_par,
                kind="mode_promoter",
                locus="src/cap.c:1",
                preconditions="cap:mode_seed",
                postconditions="provides cap:hook_mode",
                evidence_cmd="true",
                requires_tags=["cap:mode_seed"],
                provides_tags=["cap:hook_mode"],
                role="trust_gadget",
            )
            perc_par_3 = detect_percolated_multi_hop_paths(conn_par, enqueue_tasks=True)
            self.assertEqual(len(perc_par_3["percolated_paths"]), 1)
            merged_steps = perc_par_3["percolated_paths"][0]["step_ids"]
            self.assertEqual(perc_par_3["percolated_paths"][0]["jewel_id"], str(jwl["jewel_id"]))
            self.assertEqual(
                set(merged_steps),
                {
                    str(r1["primitive_id"]),
                    str(r2["primitive_id"]),
                    str(r3a["primitive_id"]),
                    str(r3b["primitive_id"]),
                },
            )
            self.assertLess(
                merged_steps.index(str(r3a["primitive_id"])),
                merged_steps.index(str(r3b["primitive_id"])),
            )
        finally:
            conn_par.close()

    def test_full_pair_unicorn_gaps_recovers_pair_past_index_8_and_ranks_with_ah_puct(self) -> None:
        self._open_initialized_run("run-trunc-12x10")
        conn = open_run_db("run-trunc-12x10", ajar_home=self.ajar_home)
        try:
            jwl = add_crown_jewel(
                conn,
                name="Run-Command RCE",
                locus="src/run_cmd.c:1",
                impact_class="rce",
                symbols=["sink:exec_rce"],
            )
            jid = str(jwl["jewel_id"])

            # Seed 2-hop structural call path: `src/manifest.c -> src/channel.c -> src/run_cmd.c`
            conn.executemany(
                "INSERT INTO repomap_edges(src_file, dst_file, symbol, weight) VALUES (?, ?, ?, ?)",
                [
                    ("src/manifest.c", "src/channel.c", "chan_handoff", 4.0),
                    ("src/channel.c", "src/run_cmd.c", "exec_sink", 4.5),
                ],
            )

            # Insert 11 unrelated forward tips FIRST (indices #0..#10, disconnected files, no snapshots).
            for idx in range(11):
                add_primitive(
                    conn,
                    kind=f"noise_fwd_{idx}",
                    locus=f"noise/fwd_{idx}.c:1",
                    preconditions="untrusted input",
                    postconditions=f"provides cap:noise_fwd_{idx}",
                    evidence_cmd="true",
                    provides_tags=[f"cap:noise_fwd_{idx}"],
                )

            # Insert true forward stepping stone at index #11 (past old `[:8]` slice!) with snapshot.
            now_iso = utc_now_iso()
            conn.execute(
                """
                INSERT INTO repro_snapshots(snapshot_id, claim_id, rel_dir, archive_path, sha256, size_bytes, created_at)
                VALUES ('snp-stage1', '', '.', 'snapshots/snp-stage1.tar.gz', 'deadbeef', 128, ?)
                """,
                (now_iso,),
            )
            stage1 = add_primitive(
                conn,
                kind="manifest_alias_write",
                locus="src/manifest.c:1",
                preconditions="untrusted manifest descriptor",
                postconditions="writes staged config alias",
                evidence_cmd="true",
                provides_tags=["cap:config_alias"],
                snapshot_id="snp-stage1",
            )
            stage1_id = str(stage1["primitive_id"])

            # Insert 8 noise backward surface sinks so `bwd_entries` has >= 10 entries total
            # (`[jid]` at #0 + 8 noise surface sinks at #1..#8 + `stage3` at #9, past `[:8]`!).
            for b_idx in range(8):
                add_surface(
                    conn,
                    name=f"noise-sink-{b_idx}",
                    kind="cli",
                    locus=f"noise/sink_{b_idx}.c:1",
                    priority="high",
                    requires_tags=[f"cap:noise_req_{b_idx}", f"cap:noise_extra_{b_idx}"],
                )

            stage3 = add_primitive(
                conn,
                kind="run_cmd_dispatch",
                locus="src/run_cmd.c:1",
                preconditions="cap:channel_handoff",
                postconditions="reaches sink:exec_rce",
                evidence_cmd="true",
                requires_tags=["cap:channel_handoff"],
                provides_tags=["sink:exec_rce"],
                role="trust_gadget",
            )
            stage3_id = str(stage3["primitive_id"])

            perc = detect_percolated_multi_hop_paths(conn, enqueue_tasks=False)
            gaps = perc["unicorn_gaps"]
            self.assertEqual(len(gaps), 8)
            # Optimal pair `(stage1_id, stage3_id)` at indices (#11, #9) MUST rank #1 (`Recall@8 == 1.0`, `MRR == 1.0`)!
            top_gap = gaps[0]
            self.assertEqual(top_gap["forward_tip_id"], stage1_id)
            self.assertEqual(top_gap["backward_entry_id"], stage3_id)
            self.assertEqual(top_gap["backward_suffix"], [stage3_id, jid])
            self.assertEqual(top_gap["call_hop_distance"], 2)
            self.assertTrue(top_gap["has_snapshot"])
            self.assertTrue(top_gap["reaches_crown_jewel"])
        finally:
            conn.close()

    def test_ah_puct_score_monotonicity_visit_decay_and_backward_cone_tie_break(self) -> None:
        # 1. Pure formula monotonicity checks
        s_0hop = ah_puct_score(reaches_crown_jewel=True, call_hop_distance=0, has_snapshot=True)
        s_1hop = ah_puct_score(reaches_crown_jewel=True, call_hop_distance=1, max_edge_weight=3.0, has_snapshot=True)
        s_2hop = ah_puct_score(reaches_crown_jewel=True, call_hop_distance=2, max_edge_weight=3.0, has_snapshot=True)
        s_disc = ah_puct_score(reaches_crown_jewel=True, call_hop_distance=None, has_snapshot=True)
        self.assertGreater(s_0hop, s_1hop)
        self.assertGreater(s_1hop, s_2hop)
        self.assertGreater(s_2hop, s_disc)

        s_no_snap = ah_puct_score(reaches_crown_jewel=True, call_hop_distance=2, max_edge_weight=3.0, has_snapshot=False)
        self.assertGreater(s_2hop, s_no_snap)

        s_non_jewel = ah_puct_score(reaches_crown_jewel=False, call_hop_distance=0, has_snapshot=True)
        self.assertGreater(s_0hop, s_non_jewel)

        # Upstream backward-cone step bonus (`[P4, jid]` > `[jid]`).
        s_cone_1 = ah_puct_score(reaches_crown_jewel=True, call_hop_distance=1, backward_proved_steps=1)
        s_cone_0 = ah_puct_score(reaches_crown_jewel=True, call_hop_distance=1, backward_proved_steps=0)
        self.assertGreater(s_cone_1, s_cone_0)

        # Visit decay: unvisited pair beats visited pair under identical structural priors.
        s_unvisited = ah_puct_score(
            reaches_crown_jewel=True,
            call_hop_distance=1,
            bridge_visits=0,
            total_bridge_visits=2,
        )
        s_visited_1 = ah_puct_score(
            reaches_crown_jewel=True,
            call_hop_distance=1,
            bridge_visits=1,
            total_bridge_visits=2,
        )
        s_visited_2 = ah_puct_score(
            reaches_crown_jewel=True,
            call_hop_distance=1,
            bridge_visits=2,
            total_bridge_visits=2,
        )
        self.assertGreater(s_unvisited, s_visited_1)
        self.assertGreater(s_visited_1, s_visited_2)

        # 2. End-to-end DB visit decay check: visiting `tip_a -> entry_b` promotes sibling `tip_b -> entry_b` to #1!
        self._open_initialized_run("run-visit-decay")
        conn = open_run_db("run-visit-decay", ajar_home=self.ajar_home)
        try:
            add_crown_jewel(
                conn,
                name="Sink Jewel",
                locus="src/run_cmd.c:1",
                impact_class="rce",
                symbols=["sink:rce"],
            )
            tip_a = add_primitive(
                conn,
                kind="tip_a",
                locus="src/entry.c:1",
                preconditions="untrusted",
                postconditions="cap:a",
                evidence_cmd="true",
                provides_tags=["cap:a"],
            )
            tip_b = add_primitive(
                conn,
                kind="tip_b",
                locus="src/entry.c:1",
                preconditions="untrusted",
                postconditions="cap:b",
                evidence_cmd="true",
                provides_tags=["cap:b"],
            )
            entry_b = add_primitive(
                conn,
                kind="sink_step",
                locus="src/run_cmd.c:1",
                preconditions="cap:need",
                postconditions="sink:rce",
                evidence_cmd="true",
                requires_tags=["cap:need"],
                provides_tags=["sink:rce"],
                role="trust_gadget",
            )
            ta_id = str(tip_a["primitive_id"])
            tb_id = str(tip_b["primitive_id"])
            eb_id = str(entry_b["primitive_id"])

            # Record a prior `bridge` task on `ta_id->eb_id`; verify `tb_id->eb_id` now outscores `ta_id->eb_id`!
            now_iso = utc_now_iso()
            conn.execute(
                """
                INSERT INTO tasks(
                    task_id, kind, direction, title, subsystem, locus,
                    priority, status, salience_score, summary, created_at, updated_at
                ) VALUES ('task-br-1', 'bridge', 'inside_out', ?, 'src', 'src/run_cmd.c:1', 'critical', 'dry', 90, ?, ?, ?)
                """,
                (
                    f"Bridge middle-unicorn gap {ta_id}->{eb_id} (cap:need)",
                    f"[unicorn-bridge] Bridge 1-link gap {ta_id}->{eb_id}",
                    now_iso,
                    now_iso,
                ),
            )
            perc = detect_percolated_multi_hop_paths(conn, enqueue_tasks=False)
            gaps = perc["unicorn_gaps"]
            by_pair = {(g["forward_tip_id"], g["backward_entry_id"]): g for g in gaps}
            self.assertGreater(
                float(by_pair[(tb_id, eb_id)]["ah_puct_score"]),
                float(by_pair[(ta_id, eb_id)]["ah_puct_score"]),
            )
            self.assertEqual(gaps[0]["forward_tip_id"], tb_id)
            self.assertEqual(gaps[0]["backward_entry_id"], eb_id)
        finally:
            conn.close()

    def test_guarded_backward_cone_proximity_and_intermediate_conjunctive_gadget(self) -> None:
        self._open_initialized_run("run-guard-cone")
        conn = open_run_db("run-guard-cone", ajar_home=self.ajar_home)
        try:
            jwl = add_crown_jewel(
                conn,
                name="Guarded Terminal Jewel",
                locus="src/run_cmd.c:1",
                impact_class="rce",
                symbols=["sink:exec"],
            )
            jid = str(jwl["jewel_id"])

            # 1-hop edge from `src/manifest.c` into `src/guard.c` (where `g_guarded`'s guard lives).
            conn.execute(
                "INSERT INTO repomap_edges(src_file, dst_file, symbol, weight) VALUES (?, ?, ?, ?)",
                ("src/manifest.c", "src/guard.c", "check_bounds", 4.0),
            )
            tip_far = add_primitive(
                conn,
                kind="far_root",
                locus="noise/far.c:1",
                preconditions="untrusted",
                postconditions="cap:far",
                evidence_cmd="true",
                provides_tags=["cap:far"],
            )
            tip_near = add_primitive(
                conn,
                kind="near_root",
                locus="src/manifest.c:1",
                preconditions="untrusted",
                postconditions="cap:near",
                evidence_cmd="true",
                provides_tags=["cap:near"],
            )
            g_guarded = add_primitive(
                conn,
                kind="guarded_exec_gadget",
                locus="src/cap.c:1",
                preconditions="guard check_bounds bypassed",
                postconditions="emits sink:exec",
                evidence_cmd="true",
                guarded_by_locus="src/guard.c:1",
                provides_tags=["sink:exec"],
                role="capability",
            )
            gg_id = str(g_guarded["primitive_id"])

            perc = detect_percolated_multi_hop_paths(conn, enqueue_tasks=False)
            self.assertEqual(perc["percolated_paths"], [])
            gaps = perc["unicorn_gaps"]
            self.assertEqual(gaps[0]["forward_tip_id"], str(tip_near["primitive_id"]))
            self.assertEqual(gaps[0]["backward_entry_id"], gg_id)
            self.assertEqual(gaps[0]["backward_suffix"], [gg_id, jid])
            self.assertEqual(gaps[0]["call_hop_distance"], 1)
            self.assertNotEqual(str(tip_far["primitive_id"]), gaps[0]["forward_tip_id"])
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
