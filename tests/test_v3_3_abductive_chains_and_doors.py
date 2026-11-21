from __future__ import annotations

import io
import json
import os
import pathlib
import sqlite3
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

import pytest

from ajar import EXIT_GATE_BLOCKED, EXIT_OK
from ajar.cli import main
from ajar.db import open_run_db
from ajar.redact import scrubbed_subprocess_env

pytestmark = pytest.mark.integration


def _run_cli(argv: list[str], ajar_home: pathlib.Path) -> tuple[int, dict[str, object] | str]:
    old_home = os.environ.get("AJAR_HOME")
    os.environ["AJAR_HOME"] = str(ajar_home)
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    try:
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            rc = main(argv)
    finally:
        if old_home is None:
            os.environ.pop("AJAR_HOME", None)
        else:
            os.environ["AJAR_HOME"] = old_home
    raw = out_buf.getvalue().strip() or err_buf.getvalue().strip()
    try:
        return rc, json.loads(raw)
    except json.JSONDecodeError:
        return rc, raw


class TestV33AbductiveChainsAndDoors(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="ajar-test-v33-")
        self.tmp_path = pathlib.Path(self._tmp.name)
        self.ajar_home = self.tmp_path / "ajar-home"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _init_git_repo(self, repo: pathlib.Path) -> None:
        env = scrubbed_subprocess_env()
        for cmd in (
            ["git", "init", "-q"],
            ["git", "config", "user.email", "test@ajar.local"],
            ["git", "config", "user.name", "ajar-test"],
            ["git", "add", "-A"],
            ["git", "commit", "-q", "-m", "initial"],
        ):
            subprocess.run(cmd, cwd=str(repo), env=env, check=True, capture_output=True)

    def _create_two_stage_c_target(self) -> pathlib.Path:
        repo = self.tmp_path / "c-two-stage"
        (repo / "src").mkdir(parents=True)
        # Both C files define a `static int parse_entry(...)` helper to verify repomap excludes C file-local statics!
        (repo / "src" / "stage_writer.c").write_text(
            "#include <stdio.h>\n"
            "#include <stdlib.h>\n"
            "#include <string.h>\n"
            "#include <sys/stat.h>\n"
            "#include <unistd.h>\n\n"
            "static int parse_entry(const char *s) { return s ? (int)strlen(s) : 0; }\n\n"
            "int write_stage_config(const char *mode, const char *out_dir) {\n"
            "    if (parse_entry(mode) <= 0) return 2;\n"
            "    mkdir(out_dir, 0755);\n"
            "    char path[256];\n"
            "    if (strcmp(mode, \"legacy_rename\") == 0) {\n"
            "        snprintf(path, sizeof(path), \"%s/override.cfg\", out_dir);\n"
            "        FILE *fp = fopen(path, \"w\");\n"
            "        if (!fp) return 3;\n"
            "        fprintf(fp, \"trusted_sink=enabled\\n\");\n"
            "        fclose(fp);\n"
            "        char lnk[256];\n"
            "        snprintf(lnk, sizeof(lnk), \"%s/active.lnk\", out_dir);\n"
            "        unlink(lnk);\n"
            "        symlink(\"override.cfg\", lnk);\n"
            "        return 1;\n"
            "    }\n"
            "    snprintf(path, sizeof(path), \"%s/normal.cfg\", out_dir);\n"
            "    FILE *fp = fopen(path, \"w\");\n"
            "    if (!fp) return 3;\n"
            "    fprintf(fp, \"trusted_sink=disabled\\n\");\n"
            "    fclose(fp);\n"
            "    return 0;\n"
            "}\n\n"
            "int main(int argc, char **argv) {\n"
            "    if (argc < 3) return 2;\n"
            "    return write_stage_config(argv[1], argv[2]);\n"
            "}\n",
            encoding="utf-8",
        )
        (repo / "src" / "sink_loader.c").write_text(
            "#include <stdio.h>\n"
            "#include <string.h>\n\n"
            "static int parse_entry(const char *s) { return s ? 1 : 0; }\n\n"
            "int load_trusted_manifest(const char *state_dir) {\n"
            "    if (!parse_entry(state_dir)) return 2;\n"
            "    char path[256];\n"
            "    snprintf(path, sizeof(path), \"%s/override.cfg\", state_dir);\n"
            "    FILE *fp = fopen(path, \"r\");\n"
            "    if (fp) {\n"
            "        char buf[128] = {0};\n"
            "        fgets(buf, sizeof(buf), fp);\n"
            "        fclose(fp);\n"
            "        if (strstr(buf, \"trusted_sink=enabled\") != NULL) {\n"
            "            printf(\"CROWN_JEWEL_SINK_REACHED\\n\");\n"
            "            return 9;\n"
            "        }\n"
            "    }\n"
            "    return 0;\n"
            "}\n\n"
            "int main(int argc, char **argv) {\n"
            "    if (argc < 2) return 2;\n"
            "    return load_trusted_manifest(argv[1]);\n"
            "}\n",
            encoding="utf-8",
        )
        self._init_git_repo(repo)
        return repo

    def test_parked_open_door_wakeup_snapshot_probe_and_zero_boilerplate_chain(self) -> None:
        repo = self._create_two_stage_c_target()
        rc, init_out = _run_cli(
            ["init", str(repo), "--run-id", "run-door", "--stopping", "crown-jewel", "--uncapped", "--json"],
            self.ajar_home,
        )
        self.assertEqual(rc, EXIT_OK, init_out)
        self.assertEqual(init_out["campaign_phase"], "hunt")  # type: ignore[index]
        self.assertEqual(init_out["stopping_criterion"], "crown-jewel")  # type: ignore[index]

        # Build repomap and verify C `static int parse_entry` does NOT create false cross-file edges!
        rc_map, _ = _run_cli(["map", "--run", "run-door", "--json"], self.ajar_home)
        self.assertEqual(rc_map, EXIT_OK)
        conn = open_run_db("run-door", ajar_home=self.ajar_home)
        try:
            static_edges = conn.execute(
                "SELECT COUNT(*) AS c FROM repomap_edges WHERE symbol = 'parse_entry'"
            ).fetchone()["c"]
            self.assertEqual(int(static_edges), 0)
        finally:
            conn.close()

        # Register surface + Crown-Jewel sink + park an Open Door (`sink_to_source`).
        _, surf = _run_cli(
            [
                "surface",
                "add",
                "--run",
                "run-door",
                "--name",
                "stage-cli",
                "--kind",
                "cli",
                "--locus",
                "src/stage_writer.c:8",
                "--priority",
                "critical",
            ],
            self.ajar_home,
        )
        sid = str(surf["surface_id"])  # type: ignore[index]

        rc_cj, cj = _run_cli(
            [
                "door",
                "jewel-add",
                "--run",
                "run-door",
                "--name",
                "trusted-manifest-loader",
                "--locus",
                "src/sink_loader.c:6",
                "--impact-class",
                "rce",
                "--symbols",
                "load_trusted_manifest,CROWN_JEWEL_SINK_REACHED",
                "--max-steps",
                "2",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_cj, EXIT_OK, cj)
        jewel_id = str(cj["jewel_id"])  # type: ignore[index]

        rc_pk, pk = _run_cli(
            [
                "door",
                "park",
                "--run",
                "run-door",
                "--jewel",
                jewel_id,
                "--direction",
                "sink_to_source",
                "--anchor-locus",
                "src/sink_loader.c:6",
                "--blocker-locus",
                "src/stage_writer.c:12",
                "--missing",
                "Upstream writer producing override.cfg inside state_dir",
                "--wanted-tags",
                "fs:override_cfg",
                "--wanted-symbols",
                "write_stage_config,override.cfg",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_pk, EXIT_OK, pk)
        door_id = str(pk["door_id"])  # type: ignore[index]
        self.assertEqual(pk["status"], "bridging")  # type: ignore[index]
        self.assertGreaterEqual(len(pk["spawned_bridge_tasks"]), 1)  # type: ignore[index]
        self.assertLessEqual(len(pk["spawned_bridge_tasks"]), 2)  # type: ignore[index]

        # Add two tasks in different subsystems and confirm Certified Run Prefix stays 100% byte-identical!
        _, t1 = _run_cli(
            ["task", "add", "--run", "run-door", "--kind", "investigate", "--surface", sid, "--locus", "src/sink_loader.c:6", "--title", "Audit sink"],
            self.ajar_home,
        )
        _, t2 = _run_cli(
            ["task", "add", "--run", "run-door", "--kind", "investigate", "--surface", sid, "--locus", "src/stage_writer.c:8", "--title", "Audit writer"],
            self.ajar_home,
        )
        _, ctx1 = _run_cli(["context", "--run", "run-door", "--task", str(t1["task_id"]), "--json"], self.ajar_home)  # type: ignore[index]
        _, ctx2 = _run_cli(["context", "--run", "run-door", "--task", str(t2["task_id"]), "--json"], self.ajar_home)  # type: ignore[index]
        self.assertEqual(ctx1["certified_prefix"], ctx2["certified_prefix"])  # type: ignore[index]
        self.assertIn("Open Doors", str(ctx1["task_delta"]))  # type: ignore[index]
        self.assertLessEqual(len(str(ctx1["rendered"]).splitlines()), 50)  # type: ignore[index]

        # Propose, survive, and 4-arm reproduce Stage 1 with `--save-post-state state_out --provides-tags fs:override_cfg`.
        mpatch = self.tmp_path / "stage1.diff"
        mpatch.write_text(
            "--- a/src/stage_writer.c\n"
            "+++ b/src/stage_writer.c\n"
            "@@ -10,6 +10,6 @@\n"
            "     if (parse_entry(mode) <= 0) return 2;\n"
            "     mkdir(out_dir, 0755);\n"
            "     char path[256];\n"
            "-    if (strcmp(mode, \"legacy_rename\") == 0) {\n"
            "+    if (0 && strcmp(mode, \"legacy_rename\") == 0) {\n"
            "         snprintf(path, sizeof(path), \"%s/override.cfg\", out_dir);\n"
            "         FILE *fp = fopen(path, \"w\");\n",
            encoding="utf-8",
        )
        _, clm = _run_cli(
            [
                "claim",
                "propose",
                "--run",
                "run-door",
                "--worker",
                "w-inv",
                "--surface",
                sid,
                "--title",
                "Unchecked legacy_rename branch writes override.cfg",
                "--locus",
                "src/stage_writer.c:12",
                "--mechanism",
                "write_stage_config permits legacy_rename to emit override.cfg",
                "--severity",
                "medium",
                "--falsification-prediction",
                "Caller rejects legacy_rename mode before write_stage_config",
                "--falsification-test",
                "./stage_writer legacy_rename state_out",
            ],
            self.ajar_home,
        )
        cid = str(clm["claim_id"])  # type: ignore[index]
        _run_cli(["claim", "survive", cid, "--run", "run-door", "--worker", "w-fal", "--notes", "Reachable from CLI"], self.ajar_home)

        rc_rep, rep = _run_cli(
            [
                "claim",
                "reproduce",
                cid,
                "--run",
                "run-door",
                "--worker",
                "w-rep",
                "--build-cmd",
                "cc -O1 src/stage_writer.c -o stage_writer",
                "--poc-cmd",
                "./stage_writer legacy_rename state_out",
                "--control-cmd",
                "./stage_writer standard state_out",
                "--micropatch",
                str(mpatch),
                "--save-post-state",
                "state_out",
                "--provides-tags",
                "fs:override_cfg",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_rep, EXIT_OK, rep)
        fid = str(rep["finding_id"])  # type: ignore[index]
        snap_id = str(rep["snapshot_id"])  # type: ignore[index]
        self.assertTrue(snap_id.startswith("snp-"))

        # Confirm Open Door automatically woke up (`ready`) and linked `snap_id`!
        _, doors_now = _run_cli(["door", "list", "--run", "run-door", "--status", "ready"], self.ajar_home)
        ready_list = doors_now["open_doors"]  # type: ignore[index]
        self.assertEqual(len(ready_list), 1)
        self.assertEqual(ready_list[0]["door_id"], door_id)
        self.assertEqual(ready_list[0]["snapshot_id"], snap_id)

        # Hydrate Stage-1 post-state snapshot into `slot-inst` (`ajar chain probe --from-snapshot`) without re-running Stage 1!
        rc_prb, prb = _run_cli(
            [
                "chain",
                "probe",
                "--run",
                "run-door",
                "--from-snapshot",
                snap_id,
                "--cmd",
                "test -L state_out/active.lnk && cc -O1 src/sink_loader.c -o sink_loader && ./sink_loader state_out",
                "--oracle-json",
                '{"expect_regex": "CROWN_JEWEL_SINK_REACHED", "expect_exit_code": 9}',
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_prb, EXIT_OK, prb)
        self.assertTrue(prb["defect_fired"])  # type: ignore[index]

        # Record `sink_loader.c` as a `trust_gadget` (normal code trusting `override.cfg` invariant) and compose ZERO-StageContext chain!
        _, gad = _run_cli(
            [
                "primitive",
                "add",
                "--run",
                "run-door",
                "--locus",
                "src/sink_loader.c:6",
                "--kind",
                "manifest_consumer",
                "--role",
                "trust_gadget",
                "--trusted-invariant",
                "state_out/override.cfg cannot be created by untrusted mode",
                "--symbols",
                "load_trusted_manifest",
                "--requires-tags",
                "fs:override_cfg",
                "--preconditions",
                "override.cfg present in state_out",
                "--postconditions",
                "Reaches load_trusted_manifest enabled branch",
                "--evidence-cmd",
                "./sink_loader state_out",
            ],
            self.ajar_home,
        )
        gad_id = str(gad["primitive_id"])  # type: ignore[index]

        rc_ch, ch = _run_cli(
            [
                "chain",
                "propose",
                "--run",
                "run-door",
                "--title",
                "Stage writer override.cfg into sink_loader Crown Jewel",
                "--steps",
                f"{fid},{gad_id}",
                "--door",
                door_id,
                "--jewel",
                jewel_id,
                "--declared-steps",
                "1",
                "--poc-cmd",
                "cc -O1 src/stage_writer.c -o stage_writer && cc -O1 src/sink_loader.c -o sink_loader && ./stage_writer legacy_rename state_out || true; ./sink_loader state_out",
                "--control-cmd",
                "cc -O1 src/stage_writer.c -o stage_writer && cc -O1 src/sink_loader.c -o sink_loader && ./stage_writer standard state_out && ./sink_loader state_out",
                "--oracle-json",
                '{"expect_regex": "CROWN_JEWEL_SINK_REACHED", "expect_exit_code": 9}',
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_ch, EXIT_OK, ch)
        self.assertTrue(ch["verified"])  # type: ignore[index]
        self.assertEqual(ch["realism_tier"], "crown_jewel")  # type: ignore[index]
        self.assertIn(door_id, ch["resolved_doors"])  # type: ignore[index]

        # Close remaining tasks and verify `G1-G5` pass with `crown_jewel_reached == True`!
        _run_cli(["task", "done", str(t1["task_id"]), "--run", "run-door", "--worker", "w-inv", "--summary", "done"], self.ajar_home)  # type: ignore[index]
        _run_cli(["task", "done", str(t2["task_id"]), "--run", "run-door", "--worker", "w-inv", "--summary", "done"], self.ajar_home)  # type: ignore[index]
        rc_gt, gt = _run_cli(["gate", "check", "--run", "run-door"], self.ajar_home)
        self.assertEqual(rc_gt, EXIT_OK, gt)
        self.assertTrue(gt["crown_jewel_reached"])  # type: ignore[index]

    def test_multi_hop_middle_unicorn_percolation_snaps_4_step_chain(self) -> None:
        repo = self._create_two_stage_c_target()
        _run_cli(["init", str(repo), "--run-id", "run-perc", "--stopping", "crown-jewel", "--uncapped", "--json"], self.ajar_home)

        _, cj = _run_cli(
            [
                "door",
                "jewel-add",
                "--run",
                "run-perc",
                "--name",
                "terminal-sink",
                "--locus",
                "src/sink_loader.c:14",
                "--symbols",
                "sink:terminal_exec",
            ],
            self.ajar_home,
        )
        jid = str(cj["jewel_id"])  # type: ignore[index]

        # Prefix: P1 (low quirk) -> P2 (trust_gadget).
        _, p1 = _run_cli(
            [
                "primitive",
                "add",
                "--run",
                "run-perc",
                "--locus",
                "src/stage_writer.c:9",
                "--kind",
                "header_quirk",
                "--provides-tags",
                "cap:hop1",
                "--preconditions",
                "untrusted input",
                "--postconditions",
                "emits cap:hop1",
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
                "run-perc",
                "--locus",
                "src/stage_writer.c:18",
                "--kind",
                "state_forwarder",
                "--role",
                "trust_gadget",
                "--requires-tags",
                "cap:hop1",
                "--provides-tags",
                "cap:hop2",
                "--preconditions",
                "cap:hop1",
                "--postconditions",
                "emits cap:hop2",
                "--evidence-cmd",
                "true",
            ],
            self.ajar_home,
        )
        # Disconnected Suffix: [?] -> P4 -> Crown Jewel `jid`.
        _, p4 = _run_cli(
            [
                "primitive",
                "add",
                "--run",
                "run-perc",
                "--locus",
                "src/sink_loader.c:10",
                "--kind",
                "sink_dispatch",
                "--role",
                "trust_gadget",
                "--requires-tags",
                "cap:hop3",
                "--provides-tags",
                "sink:terminal_exec",
                "--symbols",
                "sink:terminal_exec",
                "--preconditions",
                "cap:hop3",
                "--postconditions",
                "reaches terminal sink",
                "--evidence-cmd",
                "true",
            ],
            self.ajar_home,
        )

        # Before middle unicorn P3 arrives: 0 percolated paths, 1-link Unicorn Gap `[P1, P2] -> [?] -> [P4, jid]`!
        _, fr_before = _run_cli(["chain", "frontier", "--run", "run-perc"], self.ajar_home)
        self.assertEqual(fr_before["percolated_paths"], [])  # type: ignore[index]
        gaps = fr_before["unicorn_gaps"]  # type: ignore[index]
        self.assertGreaterEqual(len(gaps), 1)
        self.assertEqual(
            gaps[0]["forward_prefix"],
            [p1["primitive_id"], p2["primitive_id"]],  # type: ignore[index]
        )
        self.assertEqual(gaps[0]["backward_entry_id"], p4["primitive_id"])  # type: ignore[index]
        self.assertEqual(gaps[0]["unmet_requires"], ["cap:hop3"])

        # Now greenfield hunter finds the 8th-in-the-middle unicorn `P3` (`cap:hop2 -> cap:hop3`)!
        _, p3 = _run_cli(
            [
                "primitive",
                "add",
                "--run",
                "run-perc",
                "--locus",
                "src/stage_writer.c:24",
                "--kind",
                "middle_unicorn_bridge",
                "--requires-tags",
                "cap:hop2",
                "--provides-tags",
                "cap:hop3",
                "--preconditions",
                "cap:hop2",
                "--postconditions",
                "unlocks cap:hop3",
                "--evidence-cmd",
                "true",
            ],
            self.ajar_home,
        )

        # Full 4-step path `[P1, P2, P3, P4] -> jid` snaps together reactively and spawns a salience-98 `chain` task!
        _, fr_after = _run_cli(["chain", "frontier", "--run", "run-perc"], self.ajar_home)
        paths = fr_after["percolated_paths"]  # type: ignore[index]
        self.assertEqual(len(paths), 1)
        expected_steps = [
            p1["primitive_id"],  # type: ignore[index]
            p2["primitive_id"],  # type: ignore[index]
            p3["primitive_id"],  # type: ignore[index]
            p4["primitive_id"],  # type: ignore[index]
        ]
        self.assertEqual(paths[0]["step_ids"], expected_steps)
        self.assertEqual(paths[0]["jewel_id"], jid)

        _, tasks_out = _run_cli(["task", "list", "--run", "run-perc"], self.ajar_home)
        chain_tasks = [t for t in tasks_out["tasks"] if t["kind"] == "chain" and int(t["salience_score"]) >= 98]  # type: ignore[index]
        self.assertEqual(len(chain_tasks), 1)
        self.assertIn(",".join(expected_steps), str(chain_tasks[0]["summary"]))

    def test_hunt_phase_gate_anti_delusion_non_satisficing_calibrate_and_primitive_dry(self) -> None:
        repo = self._create_two_stage_c_target()
        _run_cli(["init", str(repo), "--run-id", "run-guard", "--stopping", "crown-jewel", "--uncapped", "--json"], self.ajar_home)
        _, surf = _run_cli(
            ["surface", "add", "--run", "run-guard", "--name", "writer", "--kind", "cli", "--locus", "src/stage_writer.c:8", "--priority", "high"],
            self.ajar_home,
        )
        sid = str(surf["surface_id"])  # type: ignore[index]
        _run_cli(
            ["door", "jewel-add", "--run", "run-guard", "--name", "jewel", "--locus", "src/sink_loader.c:14", "--max-steps", "1"],
            self.ajar_home,
        )

        # 1. Gadget-only chain (`all role == 'trust_gadget'`) MUST be rejected (`EXIT_GATE_BLOCKED`).
        _, g1 = _run_cli(
            [
                "primitive",
                "add",
                "--run",
                "run-guard",
                "--locus",
                "src/sink_loader.c:6",
                "--kind",
                "normal_loader",
                "--role",
                "trust_gadget",
                "--preconditions",
                "file exists",
                "--postconditions",
                "loads file",
                "--evidence-cmd",
                "true",
            ],
            self.ajar_home,
        )
        rc_gad_only, err_gad = _run_cli(
            [
                "chain",
                "propose",
                "--run",
                "run-guard",
                "--title",
                "Invalid gadget-only chain",
                "--steps",
                str(g1["primitive_id"]),  # type: ignore[index]
                "--poc-cmd",
                "false",
                "--control-cmd",
                "true",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_gad_only, EXIT_GATE_BLOCKED)
        self.assertIn("Gadget-only chain rejected", str(err_gad))

        # 2. Self-override CLI flag (`-c core.sshCommand=...`) on `claim reproduce` MUST be blocked with 0 strikes!
        mpatch = self.tmp_path / "m.diff"
        mpatch.write_text(
            "--- a/src/stage_writer.c\n"
            "+++ b/src/stage_writer.c\n"
            "@@ -10,6 +10,6 @@\n"
            "     if (parse_entry(mode) <= 0) return 2;\n"
            "     mkdir(out_dir, 0755);\n"
            "     char path[256];\n"
            "-    if (strcmp(mode, \"legacy_rename\") == 0) {\n"
            "+    if (0 && strcmp(mode, \"legacy_rename\") == 0) {\n"
            "         snprintf(path, sizeof(path), \"%s/override.cfg\", out_dir);\n"
            "         FILE *fp = fopen(path, \"w\");\n",
            encoding="utf-8",
        )
        _, clm = _run_cli(
            [
                "claim",
                "propose",
                "--run",
                "run-guard",
                "--worker",
                "w1",
                "--surface",
                sid,
                "--title",
                "Multi-step stepping stone write",
                "--locus",
                "src/stage_writer.c:12",
                "--mechanism",
                "legacy_rename writes override.cfg",
                "--severity",
                "high",
                "--falsification-prediction",
                "Blocked upstream",
                "--falsification-test",
                "./stage_writer legacy_rename out",
            ],
            self.ajar_home,
        )
        cid = str(clm["claim_id"])  # type: ignore[index]
        _run_cli(["claim", "survive", cid, "--run", "run-guard", "--worker", "w2", "--notes", "ok"], self.ajar_home)

        rc_del, err_del = _run_cli(
            [
                "claim",
                "reproduce",
                cid,
                "--run",
                "run-guard",
                "--worker",
                "w2",
                "--poc-cmd",
                "git -c core.sshCommand=false status",
                "--control-cmd",
                "git status",
                "--micropatch",
                str(mpatch),
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_del, EXIT_GATE_BLOCKED)
        self.assertIn("precondition_realism_gate", str(err_del))

        # Reproduce cleanly as a 3-step `stepping_stone` `High` finding -> triggers H5 escalation & does NOT short-circuit `crown-jewel`!
        rc_rep, rep = _run_cli(
            [
                "claim",
                "reproduce",
                cid,
                "--run",
                "run-guard",
                "--worker",
                "w2",
                "--build-cmd",
                "cc -O1 src/stage_writer.c -o stage_writer",
                "--poc-cmd",
                "./stage_writer legacy_rename out",
                "--control-cmd",
                "./stage_writer standard out",
                "--micropatch",
                str(mpatch),
                "--declared-steps",
                "3",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_rep, EXIT_OK, rep)
        self.assertEqual(rep["realism_tier"], "stepping_stone")  # type: ignore[index]
        self.assertIn("post_confirm_escalation", rep)  # type: ignore[index]
        fid = str(rep["finding_id"])  # type: ignore[index]

        # 3. `ajar patch verify` MUST be blocked while `campaign_phase == 'hunt'`.
        rc_pv_hunt, err_pv_hunt = _run_cli(
            [
                "patch",
                "verify",
                fid,
                "--run",
                "run-guard",
                "--patch",
                str(mpatch),
                "--suite-cmd",
                "true",
                "--variant-cmd",
                "a",
                "--variant-cmd",
                "b",
                "--variant-cmd",
                "c",
                "--caller-audit",
                "All callers handle non-zero return safely.",
                "--sibling-audit",
                "No sibling config writers exist in src/.",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_pv_hunt, EXIT_GATE_BLOCKED)
        self.assertIn("campaign_phase='hunt'", str(err_pv_hunt))

        # 4. Under `--stopping crown-jewel`, a `stepping_stone` High finding does NOT short-circuit `G1`!
        rc_g_early, g_early = _run_cli(["gate", "check", "--run", "run-guard"], self.ajar_home)
        self.assertEqual(rc_g_early, EXIT_GATE_BLOCKED)
        self.assertFalse(g_early["crown_jewel_reached"])  # type: ignore[index]

        # 5. `ajar finding calibrate` & `ajar primitive dry` work in 1 command without raw SQL!
        rc_cal, cal = _run_cli(
            [
                "finding",
                "calibrate",
                fid,
                "--run",
                "run-guard",
                "--severity",
                "medium",
                "--reason",
                "Requires 3 manual steps without reaching sink_loader.",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_cal, EXIT_OK, cal)
        self.assertEqual(cal["severity"], "medium")  # type: ignore[index]

        _, guarded_p = _run_cli(
            [
                "primitive",
                "add",
                "--run",
                "run-guard",
                "--locus",
                "src/sink_loader.c:10",
                "--kind",
                "guarded_sink",
                "--guarded-by",
                "src/stage_writer.c:8",
                "--preconditions",
                "needs guard bypass",
                "--postconditions",
                "reaches sink",
                "--evidence-cmd",
                "true",
            ],
            self.ajar_home,
        )
        rc_pdry, pdry = _run_cli(
            [
                "primitive",
                "dry",
                str(guarded_p["primitive_id"]),  # type: ignore[index]
                "--run",
                "run-guard",
                "--locus",
                "src/stage_writer.c:8",
                "--reason",
                "parse_entry rejects empty mode inline before mkdir.",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_pdry, EXIT_OK, pdry)

        # Complete open tasks -> bounded exhaustion allows clean `gate check` pass even without a Crown Jewel!
        _, tlist = _run_cli(["task", "list", "--run", "run-guard"], self.ajar_home)
        for t in tlist["tasks"]:  # type: ignore[index]
            if t["status"] == "open":
                _run_cli(["task", "done", str(t["task_id"]), "--run", "run-guard", "--worker", "w1", "--summary", "audited"], self.ajar_home)
        rc_g_end, g_end = _run_cli(["gate", "check", "--run", "run-guard"], self.ajar_home)
        self.assertEqual(rc_g_end, EXIT_OK, g_end)

    def test_toolchain_env_non_strike_build_errors_repro_try_packets_and_v322_migration(self) -> None:
        # 1. Toolchain & rustup/SDKROOT preservation + dangling symlink cleanup in `scrubbed_subprocess_env`.
        fake_home = self.tmp_path / "fake-home"
        cargo_bin = fake_home / ".cargo" / "bin"
        rustup_bin = fake_home / ".rustup" / "toolchains" / "stable-x86_64" / "bin"
        cargo_bin.mkdir(parents=True)
        rustup_bin.mkdir(parents=True)
        dangling_dir = self.tmp_path / "dangling-bin"
        dangling_dir.symlink_to(self.tmp_path / "nonexistent-target")
        fake_run_dir = self.tmp_path / "sample-run"

        dummy_env: dict[str, str] = {
            "HOME": str(fake_home),
            "SDKROOT": "/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk",
            "DEVELOPER_DIR": "/Library/Developer/CommandLineTools",
            "PKG_CONFIG_PATH": "/opt/homebrew/lib/pkgconfig",
            "PATH": f"{dangling_dir}{os.pathsep}/usr/bin:/bin",
        }
        dummy_env["OPENAI_" + "API_KEY"] = "sk-proj-" + ("x" * 24)
        scrubbed = scrubbed_subprocess_env(base_env=dummy_env, run_dir=fake_run_dir)

        self.assertNotIn("OPENAI_API_KEY", scrubbed)
        self.assertEqual(scrubbed.get("SDKROOT"), "/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk")
        self.assertEqual(scrubbed.get("DEVELOPER_DIR"), "/Library/Developer/CommandLineTools")
        self.assertEqual(scrubbed.get("PKG_CONFIG_PATH"), "/opt/homebrew/lib/pkgconfig")
        self.assertEqual(scrubbed.get("CARGO_NET_OFFLINE"), "true")
        self.assertEqual(scrubbed.get("AJAR_RUN_DIR"), str(fake_run_dir))
        path_parts = scrubbed["PATH"].split(os.pathsep)
        self.assertIn(str(cargo_bin), path_parts)
        self.assertIn(str(rustup_bin), path_parts)
        self.assertNotIn(str(dangling_dir), path_parts)

        # 2. Strike-free `ajar repro try` + `build_or_env_error` zero-strike separation on `ajar claim reproduce`.
        repo = self._create_two_stage_c_target()
        _run_cli(["init", str(repo), "--run-id", "run-bld", "--uncapped", "--json"], self.ajar_home)
        rc_try, out_try = _run_cli(
            [
                "repro",
                "try",
                "--run",
                "run-bld",
                "--build-cmd",
                "cc -O1 src/stage_writer.c -o stage_writer",
                "--cmd",
                "test -n \"$AJAR_RUN_DIR\" && ./stage_writer legacy_rename out_try",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_try, EXIT_OK, out_try)
        self.assertTrue(out_try["defect_fired"])  # type: ignore[index]

        mpatch = self.tmp_path / "b.diff"
        mpatch.write_text(
            "--- a/src/stage_writer.c\n"
            "+++ b/src/stage_writer.c\n"
            "@@ -10,6 +10,6 @@\n"
            "     if (parse_entry(mode) <= 0) return 2;\n"
            "     mkdir(out_dir, 0755);\n"
            "     char path[256];\n"
            "-    if (strcmp(mode, \"legacy_rename\") == 0) {\n"
            "+    if (0 && strcmp(mode, \"legacy_rename\") == 0) {\n"
            "         snprintf(path, sizeof(path), \"%s/override.cfg\", out_dir);\n"
            "         FILE *fp = fopen(path, \"w\");\n",
            encoding="utf-8",
        )
        _, clm = _run_cli(
            [
                "claim",
                "propose",
                "--run",
                "run-bld",
                "--worker",
                "w1",
                "--title",
                "Writer mode check",
                "--locus",
                "src/stage_writer.c:12",
                "--mechanism",
                "legacy_rename writes override.cfg",
                "--severity",
                "high",
                "--falsification-prediction",
                "Rejected upstream",
                "--falsification-test",
                "./stage_writer legacy_rename out",
            ],
            self.ajar_home,
        )
        cid = str(clm["claim_id"])  # type: ignore[index]
        _run_cli(["claim", "survive", cid, "--run", "run-bld", "--worker", "w2", "--notes", "ok"], self.ajar_home)

        # Two broken compiler invocations (`nonexistent_compiler_xyz`) MUST NOT burn `failed_repro_count` strikes!
        for _ in range(2):
            rc_b, out_b = _run_cli(
                [
                    "claim",
                    "reproduce",
                    cid,
                    "--run",
                    "run-bld",
                    "--worker",
                    "w2",
                    "--build-cmd",
                    "nonexistent_compiler_xyz src/stage_writer.c",
                    "--poc-cmd",
                    "./stage_writer legacy_rename out",
                    "--control-cmd",
                    "true",
                    "--micropatch",
                    str(mpatch),
                ],
                self.ajar_home,
            )
            self.assertEqual(rc_b, EXIT_GATE_BLOCKED)
            self.assertEqual(out_b["reproduction"]["error_class"], "build_or_env_error")  # type: ignore[index]
            self.assertEqual(out_b["claim_update"]["failed_repro_count"], 0)  # type: ignore[index]
            self.assertFalse(out_b["claim_update"]["strike_recorded"])  # type: ignore[index]

        # Claim is STILL `survived_falsify` (not locked in `needs_instrumentation`) and reproduces immediately once compiler is fixed!
        rc_ok, out_ok = _run_cli(
            [
                "claim",
                "reproduce",
                cid,
                "--run",
                "run-bld",
                "--worker",
                "w2",
                "--build-cmd",
                "cc -O1 src/stage_writer.c -o stage_writer",
                "--poc-cmd",
                "./stage_writer legacy_rename out",
                "--control-cmd",
                "./stage_writer standard out",
                "--micropatch",
                str(mpatch),
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_ok, EXIT_OK, out_ok)

        # 3. `swarm packet --stage portfolio` & `--stage bridge` line budget (`<= 45` lines).
        _run_cli(["door", "park", "--run", "run-bld", "--anchor-locus", "src/sink_loader.c:6", "--missing", "need upstream writer"], self.ajar_home)
        _run_cli(["door", "park", "--run", "run-bld", "--anchor-locus", "src/sink_loader.c:10", "--missing", "need archive extractor token"], self.ajar_home)
        _run_cli(["task", "add", "--run", "run-bld", "--kind", "investigate", "--locus", "src/stage_writer.c:8", "--title", "Greenfield cone"], self.ajar_home)
        for stg in ("bridge", "portfolio", "chain"):
            rc_pk, pkt = _run_cli(["swarm", "packet", "--run", "run-bld", "--stage", stg, "--json"], self.ajar_home)
            self.assertEqual(rc_pk, EXIT_OK, pkt)
            self.assertLessEqual(int(pkt["line_count"]), 45)  # type: ignore[index]
            self.assertNotIn("$HOME/.ajar/runs", str(pkt["packet_markdown"]))  # type: ignore[index]

        # 4. Legacy `v3.2.2` SQLite table-rebuild migration test (`runs`, `tasks`, `claims`, `swarm_dispatches`).
        legacy_dir = self.ajar_home / "runs" / "legacy-v322"
        legacy_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(legacy_dir, 0o700)
        ldb = legacy_dir / "run.db"
        raw_conn = sqlite3.connect(str(ldb))
        raw_conn.executescript(
            """
            CREATE TABLE runs (
                run_id TEXT PRIMARY KEY,
                target_path TEXT NOT NULL,
                target_mode TEXT NOT NULL DEFAULT 'source',
                workspace_mode TEXT NOT NULL DEFAULT 'envelope',
                workspace_path TEXT NOT NULL,
                goal TEXT NOT NULL,
                stopping_criterion TEXT NOT NULL DEFAULT 'exhaustive-high'
                    CHECK(stopping_criterion IN ('exhaustive-high', 'first-verified-high')),
                budget_usd REAL NOT NULL DEFAULT 10.0,
                in_scope_loc INTEGER NOT NULL DEFAULT 100,
                code_quote_usd REAL NOT NULL DEFAULT 10.0,
                commitment_hash TEXT NOT NULL DEFAULT 'abc',
                status TEXT NOT NULL DEFAULT 'active',
                zero_skill_leases INTEGER NOT NULL DEFAULT 0,
                domain_skill_leases INTEGER NOT NULL DEFAULT 0,
                closed_task_counter INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT '2026-11-19T00:00:00Z'
            );
            INSERT INTO runs(run_id, target_path, workspace_path, goal) VALUES ('legacy-v322', '/tmp/t', '/tmp/w', 'g');
            CREATE TABLE tasks (
                task_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL CHECK(kind IN ('map', 'investigate', 'falsify', 'reproduce', 'chain', 'patch')),
                title TEXT NOT NULL,
                priority TEXT NOT NULL DEFAULT 'high',
                status TEXT NOT NULL DEFAULT 'open',
                salience_score INTEGER NOT NULL DEFAULT 80,
                created_at TEXT NOT NULL DEFAULT '2026-11-19T00:00:00Z',
                updated_at TEXT NOT NULL DEFAULT '2026-11-19T00:00:00Z'
            );
            CREATE TABLE claims (
                claim_id TEXT PRIMARY KEY,
                proposer_worker_id TEXT NOT NULL,
                title TEXT NOT NULL,
                locus TEXT NOT NULL,
                mechanism TEXT NOT NULL,
                mechanism_key TEXT NOT NULL,
                severity TEXT NOT NULL DEFAULT 'high',
                falsification_prediction TEXT NOT NULL,
                falsification_test TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'proposed',
                remediation_state TEXT NOT NULL DEFAULT 'unpatched'
                    CHECK(remediation_state IN ('unpatched', 'micropatched', 'maintainer_patched')),
                created_at TEXT NOT NULL DEFAULT '2026-11-19T00:00:00Z',
                updated_at TEXT NOT NULL DEFAULT '2026-11-19T00:00:00Z'
            );
            CREATE TABLE swarm_dispatches (
                dispatch_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                stage TEXT NOT NULL CHECK(stage IN ('investigate', 'falsify', 'reproduce', 'chain')),
                wire_profile TEXT NOT NULL DEFAULT 'direct',
                item_ids_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'dispatched',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT '2026-11-19T00:00:00Z',
                updated_at TEXT NOT NULL DEFAULT '2026-11-19T00:00:00Z'
            );
            """
        )
        raw_conn.commit()
        raw_conn.close()

        mig_conn = open_run_db("legacy-v322", ajar_home=self.ajar_home)
        try:
            mig_conn.execute("UPDATE runs SET stopping_criterion = 'crown-jewel', campaign_phase = 'remediate'")
            mig_conn.execute(
                "INSERT INTO tasks(task_id, kind, title, created_at, updated_at) VALUES ('task-b1', 'bridge', 'b', 'now', 'now')"
            )
            mig_conn.execute(
                "INSERT INTO swarm_dispatches(dispatch_id, worker_id, stage, wire_profile, created_at, updated_at) VALUES ('dsp-1', 'w-1', 'portfolio', 'direct', 'now', 'now')"
            )
        finally:
            mig_conn.close()


if __name__ == "__main__":
    unittest.main()
