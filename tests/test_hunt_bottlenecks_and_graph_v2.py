"""Unit and integration tests for Weeks 1–2 Hunt Bottlenecks (B1–B5) and `ajar-platform-graph/2`."""

from __future__ import annotations

import fcntl
import io
import json
import os
import pathlib
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from ajar import EXIT_GATE_BLOCKED
from ajar.chain_planner import (
    add_crown_jewel,
    detect_percolated_multi_hop_paths,
    evaluate_precondition_realism,
    park_open_door,
)
from ajar.cli import main as cli_main
from ajar.db import add_steer, add_threat_assumption, open_run_db, upsert_threat_model
from ajar.diff_sync import sync_pr_differential_state
from ajar.domain.models import AjarError
from ajar.graph import SCOPE_NOTICE, export_attack_flow_graph
from ajar.redact import scrubbed_subprocess_env
from ajar.repomap import REPOMAP_EDGE_CAP, _extract_regex_symbols, build_repomap
from ajar.repro_compose import (
    run_chain_reproduction,
    run_claim_instrumentation,
    run_snapshot_chain_probe,
)
from ajar.repro_source import (
    _prepare_slot_worktree,
    _run_shell_in_slot,
    _snapshot_clean_build_outputs,
    _try_clean_arm_preserving_build,
    aggregate_failure_telemetry,
    capture_slot_post_state_snapshot,
    init_source_mirror,
    resolve_local_build_cache_dir,
    resolve_shared_compiler_cache_env,
    run_source_reproduction,
)
from ajar.services import (
    add_anomaly,
    add_primitive,
    add_surface,
    add_task,
    close_task_dry,
    propose_claim,
    record_reproduction_outcome,
    survive_claim,
)
from ajar.swarm import build_swarm_packet, complete_swarm_dispatch, escalate_swarm_fallback
from ajar.workspace import init_run_workspace


def _git_init_repo(repo_dir: pathlib.Path, files: dict[str, str]) -> None:
    repo_dir.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        fp = repo_dir / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Ajar Test",
        "GIT_AUTHOR_EMAIL": "test@example.invalid",
        "GIT_COMMITTER_NAME": "Ajar Test",
        "GIT_COMMITTER_EMAIL": "test@example.invalid",
    }
    subprocess.run(["git", "-C", str(repo_dir), "init", "-q"], check=True, env=env)
    subprocess.run(["git", "-C", str(repo_dir), "add", "-A"], check=True, env=env)
    subprocess.run(["git", "-C", str(repo_dir), "commit", "-q", "-m", "initial"], check=True, env=env)


class TestRepomapB1(unittest.TestCase):
    def test_edge_cap_sorts_by_weight_desc_and_preserves_z_subsystem(self) -> None:
        self.assertEqual(REPOMAP_EDGE_CAP, 25_000)
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            # Create many low-weight edges in `a_*` files referencing a shared symbol defined in 9 files (IDF = 1/3).
            for idx in range(9):
                (root / f"a_def_{idx:02d}.py").write_text("def shared_helper():\n    return 1\n", encoding="utf-8")
            for idx in range(15):
                (root / f"a_caller_{idx:02d}.py").write_text(
                    f"def a_fn_{idx:02d}():\n    return shared_helper()\n",
                    encoding="utf-8",
                )

            # High-weight `z_*` edge referencing 3 unique symbols (summed IDF = 3.0).
            (root / "z_sink.py").write_text(
                "def z_critical_alpha():\n    return 1\n"
                "def z_critical_beta():\n    return 2\n"
                "def z_critical_gamma():\n    return 3\n",
                encoding="utf-8",
            )
            (root / "z_caller.py").write_text(
                "def z_entry():\n"
                "    return z_critical_alpha() + z_critical_beta() + z_critical_gamma()\n",
                encoding="utf-8",
            )

            conn = sqlite3.connect(":memory:", isolation_level=None)
            conn.row_factory = sqlite3.Row
            try:
                res = build_repomap(conn, root, max_edges=10)
                self.assertEqual(res["edges_indexed"], 10)
                self.assertGreater(res["edges_total"], 10)

                rows = conn.execute(
                    "SELECT src_file, dst_file, symbol, weight FROM repomap_edges"
                ).fetchall()
                self.assertEqual(len(rows), 10)

                # Highest-weight `z_caller.py -> z_sink.py` edge must survive capping and appear first!
                self.assertEqual(rows[0]["src_file"], "z_caller.py")
                self.assertEqual(rows[0]["dst_file"], "z_sink.py")
                self.assertAlmostEqual(float(rows[0]["weight"]), 3.0, places=3)
                self.assertEqual(rows[0]["symbol"], "z_critical_alpha")

                # Edges must be deduplicated per (src_file, dst_file) and strictly sorted by (-weight, src, dst).
                pairs = [(str(r["src_file"]), str(r["dst_file"])) for r in rows]
                self.assertEqual(len(pairs), len(set(pairs)))
                sort_keys = [(-float(r["weight"]), str(r["src_file"]), str(r["dst_file"])) for r in rows]
                self.assertEqual(sort_keys, sorted(sort_keys))
            finally:
                conn.close()

    def test_multiline_c_cpp_and_new_language_symbol_extraction(self) -> None:
        c_src = """\
extern int
forward_proto(int a,
              int b);

static const char *
internal_helper(const char *buf,
                size_t len)
{
    return buf;
}

const struct node *
resolve_entry(struct table *t,
              int idx)
{
    return 0;
}
"""
        c_syms = _extract_regex_symbols("src/parser.c", ".c", c_src)
        by_name = {str(s["name"]): s for s in c_syms}
        self.assertNotIn("forward_proto", by_name)
        self.assertIn("internal_helper", by_name)
        self.assertTrue(by_name["internal_helper"]["file_local"])
        self.assertIn("resolve_entry", by_name)
        self.assertFalse(by_name["resolve_entry"]["file_local"])

        cpp_src = """\
class FrameDecoder : public BaseDecoder {
public:
    int run();
};

std::string
FrameDecoder::decode_payload(const uint8_t *data,
                             size_t len)
{
    return "";
}
"""
        cpp_syms = _extract_regex_symbols("src/decoder.cpp", ".cpp", cpp_src)
        cpp_names = {str(s["name"]) for s in cpp_syms}
        self.assertIn("FrameDecoder", cpp_names)
        self.assertIn("decode_payload", cpp_names)

        java_src = """\
public final class TokenVerifier {
    public static boolean verifySignature(byte[] sig) {
        return true;
    }
}
"""
        java_names = {str(s["name"]) for s in _extract_regex_symbols("TokenVerifier.java", ".java", java_src)}
        self.assertEqual(java_names, {"TokenVerifier", "verifySignature"})

        php_src = """\
<?php
final class SessionGuard {
    public static function checkSession($tok) {
        return true;
    }
}
function parse_cookie($raw) {
    return $raw;
}
"""
        php_names = {str(s["name"]) for s in _extract_regex_symbols("guard.php", ".php", php_src)}
        self.assertEqual(php_names, {"SessionGuard", "checkSession", "parse_cookie"})

        move_src = """\
module vault::treasury {
    public struct VaultCap has key {}
    public entry fun withdraw_funds(amount: u64) {}
}
"""
        move_names = {str(s["name"]) for s in _extract_regex_symbols("treasury.move", ".move", move_src)}
        self.assertEqual(move_names, {"treasury", "VaultCap", "withdraw_funds"})

        zig_src = """\
pub const FrameHeader = packed struct {
    len: u32,
};
pub export fn parseHeader(buf: []const u8) !FrameHeader {
    return undefined;
}
"""
        zig_names = {str(s["name"]) for s in _extract_regex_symbols("frame.zig", ".zig", zig_src)}
        self.assertEqual(zig_names, {"FrameHeader", "parseHeader"})


class TestSlotPoolAndBuildReuseB3(unittest.TestCase):
    def test_probe_and_instrument_use_shared_slot_pool(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            ajar_home = base / "ajar_home"
            target = base / "target"
            _git_init_repo(target, {"app.py": "def ok():\n    return 42\n"})
            with mock.patch.dict(os.environ, {"AJAR_HOME": str(ajar_home)}):
                init_run_workspace(
                    target=str(target),
                    target_mode="source",
                    workspace_mode="in_place",
                    run_id="run-b3-pool",
                    ajar_home=ajar_home,
                )
                rdir = ajar_home / "runs" / "run-b3-pool"
                repro_dir = rdir / "repro"
                repro_dir.mkdir(parents=True, exist_ok=True)
                conn = open_run_db("run-b3-pool", ajar_home=ajar_home)
                try:
                    surf = add_surface(
                        conn,
                        name="App",
                        kind="cli",
                        subsystem="app",
                        locus="app.py:1",
                        priority="high",
                        trust_boundary="ext->app",
                    )
                    clm = propose_claim(
                        conn,
                        worker_id="w1",
                        title="Check instrument slot",
                        locus="app.py:1",
                        severity="high",
                        mechanism="Returns constant",
                        surface_id=str(surf["surface_id"]),
                        falsification_prediction="Returns 42",
                        falsification_test="Call ok()",
                    )
                    cid = str(clm["claim_id"])

                    # Hold slot-0.lock -> run_claim_instrumentation MUST use slot-1 (never slot-inst)!
                    lock0 = open(repro_dir / "slot-0.lock", "a+", encoding="utf-8")
                    fcntl.flock(lock0.fileno(), fcntl.LOCK_EX)
                    try:
                        inst = run_claim_instrumentation(
                            conn,
                            run_dir=rdir,
                            target_dir=target,
                            claim_id=cid,
                            probe_cmd="python3 -c 'import app; print(app.ok())'",
                            worker_id="w-inst",
                        )
                        self.assertEqual(inst["slot_index"], 1)
                        self.assertFalse((repro_dir / "slot-inst").exists())
                        self.assertFalse((repro_dir / "slot-inst.lock").exists())
                    finally:
                        fcntl.flock(lock0.fileno(), fcntl.LOCK_UN)
                        lock0.close()

                    # Create a valid snapshot and hold slot-0 + slot-1 -> run_snapshot_chain_probe MUST use slot-2!
                    stage_dir = repro_dir / "slot-1"
                    (stage_dir / "state_out").mkdir(exist_ok=True)
                    (stage_dir / "state_out" / "flag.txt").write_text("stage1-ok", encoding="utf-8")
                    snap = capture_slot_post_state_snapshot(
                        run_dir=rdir,
                        slot_dir=stage_dir,
                        rel_dir="state_out",
                        claim_id=cid,
                        source_cmd="true",
                    )
                    self.assertTrue(snap["ok"])
                    conn.execute(
                        """
                        INSERT INTO repro_snapshots(
                            snapshot_id, claim_id, rel_dir, archive_path, sha256,
                            size_bytes, manifest_json, source_cmd, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            snap["snapshot_id"],
                            cid,
                            snap["rel_dir"],
                            snap["archive_path"],
                            snap["sha256"],
                            snap["size_bytes"],
                            json.dumps(snap["manifest"]),
                            snap["source_cmd"],
                            snap["created_at"],
                        ),
                    )
                    lock0 = open(repro_dir / "slot-0.lock", "a+", encoding="utf-8")
                    lock1 = open(repro_dir / "slot-1.lock", "a+", encoding="utf-8")
                    fcntl.flock(lock0.fileno(), fcntl.LOCK_EX)
                    fcntl.flock(lock1.fileno(), fcntl.LOCK_EX)
                    try:
                        prb = run_snapshot_chain_probe(
                            conn,
                            run_dir=rdir,
                            target_dir=target,
                            snapshot_id=str(snap["snapshot_id"]),
                            cmd="test \"$(cat state_out/flag.txt)\" = 'stage1-ok'",
                            worker_id="w-probe",
                        )
                        self.assertEqual(prb["slot_index"], 2)
                        self.assertEqual(prb["probe"]["exit_code"], 0)
                        self.assertFalse((repro_dir / "slot-inst").exists())
                        # Cleanup must have removed hydrated state_out from slot-2.
                        self.assertFalse((repro_dir / "slot-2" / "state_out").exists())
                    finally:
                        fcntl.flock(lock1.fileno(), fcntl.LOCK_UN)
                        lock1.close()
                        fcntl.flock(lock0.fileno(), fcntl.LOCK_UN)
                        lock0.close()
                finally:
                    conn.close()

    def test_clean_head_build_reuse_and_fallback_on_mutation(self) -> None:
        if not shutil.which("cc"):
            self.skipTest("C compiler `cc` not available")
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            ajar_home = base / "ajar_home"
            target = base / "c_target"
            _git_init_repo(
                target,
                {
                    "src/tool.c": (
                        "#include <stdio.h>\n"
                        "#include <string.h>\n"
                        "int main(int argc, char **argv) {\n"
                        "    if (argc > 1 && strcmp(argv[1], \"bad\") == 0) {\n"
                        "        puts(\"DEFECT_HIT\");\n"
                        "        return 2;\n"
                        "    }\n"
                        "    puts(\"OK\");\n"
                        "    return 0;\n"
                        "}\n"
                    )
                },
            )
            mpatch = base / "fix.diff"
            mpatch.write_text(
                "--- a/src/tool.c\n"
                "+++ b/src/tool.c\n"
                "@@ -2,6 +2,6 @@\n"
                " #include <string.h>\n"
                " int main(int argc, char **argv) {\n"
                "-    if (argc > 1 && strcmp(argv[1], \"bad\") == 0) {\n"
                "+    if (0 && argc > 1 && strcmp(argv[1], \"bad\") == 0) {\n"
                "         puts(\"DEFECT_HIT\");\n"
                "         return 2;\n"
                "     }\n",
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {"AJAR_HOME": str(ajar_home)}):
                init_run_workspace(
                    target=str(target),
                    target_mode="source",
                    workspace_mode="in_place",
                    run_id="run-b3-reuse",
                    ajar_home=ajar_home,
                )
                rdir = ajar_home / "runs" / "run-b3-reuse"
                counter_clean = base / "builds_clean.log"
                res_reused = run_source_reproduction(
                    run_dir=rdir,
                    target_dir=target,
                    claim_id="clm-reuse-1",
                    build_cmd=f"echo b >> {counter_clean} && cc -O0 src/tool.c -o tool",
                    poc_cmd="./tool bad || { rc=$?; mkdir -p scratch_dir && echo tmp > scratch_dir/arm1.tmp; exit $rc; }",
                    control_cmd="test ! -e scratch_dir && ./tool good",
                    micropatch_path=mpatch,
                    claim_locus="src/tool.c:4",
                )
                self.assertTrue(res_reused["passed"], res_reused)
                self.assertTrue(res_reused["arm2_clean_control"]["arm2_build_reused"])
                # Exactly 2 builds: clean HEAD before Arm 1 + patched before Arm 3 (Arm 2 reused clean build!).
                self.assertEqual(len(counter_clean.read_text(encoding="utf-8").splitlines()), 2)

                # Case B: PoC mutates the compiled binary `./tool` -> MUST detect mutation and rebuild for Arm 2!
                counter_dirty = base / "builds_dirty.log"
                res_rebuilt = run_source_reproduction(
                    run_dir=rdir,
                    target_dir=target,
                    claim_id="clm-reuse-2",
                    build_cmd=f"echo b >> {counter_dirty} && cc -O0 src/tool.c -o tool",
                    poc_cmd="./tool bad || { rc=$?; rm -f tool; exit $rc; }",
                    control_cmd="./tool good",
                    micropatch_path=mpatch,
                    claim_locus="src/tool.c:4",
                )
                self.assertTrue(res_rebuilt["passed"], res_rebuilt)
                self.assertFalse(res_rebuilt["arm2_clean_control"]["arm2_build_reused"])
                # 3 builds: Arm 1 clean + Arm 2 fallback rebuild + Arm 3 patched!
                self.assertEqual(len(counter_dirty.read_text(encoding="utf-8").splitlines()), 3)

    def test_shared_ccache_sccache_env_across_slots(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            rdir = base / "runs" / "run-cc"
            target = base / "repo"
            _git_init_repo(target, {"x.txt": "hello\n"})
            mirror = init_source_mirror(rdir, target)
            self.assertTrue(mirror.is_dir())

            # Shared cache dirs must match across slot-0 and slot-1 while per-slot CARGO_TARGET_DIR stays isolated.
            with mock.patch.dict(os.environ, {"AJAR_BUILD_CACHE_ROOT": str(base / "bcache")}, clear=False):
                cc_env = resolve_shared_compiler_cache_env(rdir, base_env={})
                self.assertTrue(cc_env["CCACHE_DIR"].endswith("/run-cc/shared/ccache"))
                self.assertTrue(cc_env["SCCACHE_DIR"].endswith("/run-cc/shared/sccache"))
                self.assertEqual(cc_env["CCACHE_NOHASHDIR"], "true")
                self.assertEqual(cc_env["CCACHE_BASEDIR"], str((rdir / "repro").resolve()))

                slot0 = rdir / "repro" / "slot-0"
                slot1 = rdir / "repro" / "slot-1"
                slot0.mkdir(parents=True, exist_ok=True)
                slot1.mkdir(parents=True, exist_ok=True)
                cache0 = resolve_local_build_cache_dir(rdir, "cache-0")
                cache1 = resolve_local_build_cache_dir(rdir, "cache-1")

                probe_cmd = "printf '%s|%s|%s|%s\\n' \"$CCACHE_DIR\" \"$SCCACHE_DIR\" \"$CCACHE_NOHASHDIR\" \"$CARGO_TARGET_DIR\""
                r0 = _run_shell_in_slot(probe_cmd, slot_dir=slot0, cache_dir=cache0, timeout_sec=15)
                r1 = _run_shell_in_slot(probe_cmd, slot_dir=slot1, cache_dir=cache1, timeout_sec=15)
                p0 = r0["stdout"].strip().split("|")
                p1 = r1["stdout"].strip().split("|")
                self.assertEqual(p0[0], p1[0])  # shared CCACHE_DIR
                self.assertEqual(p0[1], p1[1])  # shared SCCACHE_DIR
                self.assertEqual(p0[2], "true")
                self.assertNotEqual(p0[3], p1[3])  # per-slot CARGO_TARGET_DIR isolated

            # scrubbed_subprocess_env passes through explicit RUSTC_WRAPPER & compiler launcher env vars.
            env = scrubbed_subprocess_env(
                base_env={
                    "PATH": "/usr/bin:/bin",
                    "RUSTC_WRAPPER": "sccache",
                    "SCCACHE_DIR": str(base / "custom-sccache"),
                    "CCACHE_DIR": str(base / "custom-ccache"),
                    "OPENAI_API_KEY": "sk-" + "proj-dummy1234567890abcdef",
                }
            )
            self.assertEqual(env["RUSTC_WRAPPER"], "sccache")
            self.assertEqual(env["SCCACHE_DIR"], str(base / "custom-sccache"))
            self.assertEqual(env["CCACHE_DIR"], str(base / "custom-ccache"))
            self.assertNotIn("OPENAI_API_KEY", env)


class TestChainAndDiffSyncBuildCmdB2(unittest.TestCase):
    def test_chain_propose_ablation_inherits_and_rebuilds_compiled_target(self) -> None:
        if not shutil.which("cc"):
            self.skipTest("C compiler `cc` not available")
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            ajar_home = base / "ajar_home"
            target = base / "c_chain"
            _git_init_repo(
                target,
                {
                    "src/stage1.c": (
                        "int stage1_bypass(const char *arg) {\n"
                        "    return arg && arg[0] == 'X';\n"
                        "}\n"
                    ),
                    "src/stage2.c": (
                        "#include <stdio.h>\n"
                        "int stage1_bypass(const char *arg);\n"
                        "int stage2_sink(int ok) {\n"
                        "    return ok ? 1 : 0;\n"
                        "}\n"
                        "int main(int argc, char **argv) {\n"
                        "    const char *a = argc > 1 ? argv[1] : \"\";\n"
                        "    if (stage1_bypass(a) && stage2_sink(1)) {\n"
                        "        puts(\"CHAIN_HIT\");\n"
                        "        return 3;\n"
                        "    }\n"
                        "    puts(\"SAFE\");\n"
                        "    return 0;\n"
                        "}\n"
                    ),
                },
            )
            p1_diff = (
                "--- a/src/stage1.c\n"
                "+++ b/src/stage1.c\n"
                "@@ -1,3 +1,3 @@\n"
                " int stage1_bypass(const char *arg) {\n"
                "-    return arg && arg[0] == 'X';\n"
                "+    return 0;\n"
                " }\n"
            )
            p2_diff = (
                "--- a/src/stage2.c\n"
                "+++ b/src/stage2.c\n"
                "@@ -2,4 +2,4 @@\n"
                " int stage1_bypass(const char *arg);\n"
                " int stage2_sink(int ok) {\n"
                "-    return ok ? 1 : 0;\n"
                "+    return 0;\n"
                " }\n"
            )
            build_cmd = "cc -O0 src/stage1.c src/stage2.c -o chain_app"
            with mock.patch.dict(os.environ, {"AJAR_HOME": str(ajar_home)}):
                init_run_workspace(
                    target=str(target),
                    target_mode="source",
                    workspace_mode="in_place",
                    run_id="run-b2-chain",
                    ajar_home=ajar_home,
                )
                rdir = ajar_home / "runs" / "run-b2-chain"
                conn = open_run_db("run-b2-chain", ajar_home=ajar_home)
                try:
                    surf = add_surface(
                        conn,
                        name="ChainCLI",
                        kind="cli",
                        subsystem="src",
                        locus="src/stage2.c:6",
                        priority="critical",
                        trust_boundary="ext->cli",
                    )
                    fids: list[str] = []
                    for idx, (loc, diff_txt) in enumerate(
                        [("src/stage1.c:2", p1_diff), ("src/stage2.c:4", p2_diff)], start=1
                    ):
                        clm = propose_claim(
                            conn,
                            worker_id="w-prop",
                            title=f"Stage {idx} compiled defect",
                            locus=loc,
                            severity="high",
                            mechanism=f"Stage {idx} allows bypass into sink",
                            surface_id=str(surf["surface_id"]),
                            falsification_prediction="Guard rejects input",
                            falsification_test="Run chain_app",
                        )
                        cid = str(clm["claim_id"])
                        survive_claim(conn, claim_id=cid, worker_id="w-fals", notes="Confirmed in C source")
                        out = record_reproduction_outcome(
                            conn,
                            claim_id=cid,
                            worker_id="w-repro",
                            poc_cmd="./chain_app X",
                            control_cmd="./chain_app ok",
                            build_cmd=build_cmd,
                            repro_result={
                                "passed": True,
                                "observation_hash": f"obs-b2-{idx}",
                                "micropatch_diff": diff_txt,
                                "arm1_clean_poc": {"arm_passed": True},
                                "arm2_clean_control": {"arm_passed": True},
                                "arm3_patch_poc": {"arm_passed": True},
                                "arm4_patch_control": {"arm_passed": True},
                            },
                        )
                        fids.append(str(out["finding_id"]))

                    # Omit explicit `build_cmd` -> MUST auto-inherit `build_cmd` from step findings and recompile per step!
                    chain_res = run_chain_reproduction(
                        conn,
                        run_dir=rdir,
                        target_dir=target,
                        title="Two-stage compiled C chain",
                        steps=fids,
                        poc_cmd="./chain_app X",
                        control_cmd="./chain_app ok",
                        oracle={"expect_regex": "CHAIN_HIT", "expect_exit_code": 3},
                        worker_id="w-chain",
                    )
                    self.assertTrue(chain_res["verified"], chain_res)
                    self.assertEqual(chain_res["build_cmd"], build_cmd)
                    self.assertEqual(len(chain_res["ablation_matrix"]), 2)
                    for row in chain_res["ablation_matrix"]:
                        self.assertEqual(row["ablated_via"], "step_micropatch")
                        self.assertTrue(row["causally_required"])
                finally:
                    conn.close()

    def test_diff_sync_executes_build_cmd_and_preserves_objects(self) -> None:
        if not shutil.which("cc"):
            self.skipTest("C compiler `cc` not available")
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            ajar_home = base / "ajar_home"
            target = base / "c_diff"
            git_env = {
                **os.environ,
                "GIT_AUTHOR_NAME": "Ajar Test",
                "GIT_AUTHOR_EMAIL": "test@example.invalid",
                "GIT_COMMITTER_NAME": "Ajar Test",
                "GIT_COMMITTER_EMAIL": "test@example.invalid",
            }
            _git_init_repo(
                target,
                {
                    "src/app.c": (
                        "#include <string.h>\n"
                        "int main(int argc, char **argv) {\n"
                        "    return (argc > 1 && strcmp(argv[1], \"bad\") == 0) ? 2 : 0;\n"
                        "}\n"
                    ),
                    "README.md": "v1\n",
                },
            )
            base_sha = subprocess.check_output(
                ["git", "-C", str(target), "rev-parse", "HEAD"], text=True, env=git_env
            ).strip()
            # PR commit 1: unrelated README edit -> compiled bug still fires when build_cmd executes.
            (target / "README.md").write_text("v2\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(target), "add", "-A"], check=True, env=git_env)
            subprocess.run(["git", "-C", str(target), "commit", "-q", "-m", "docs"], check=True, env=git_env)
            pr1_sha = subprocess.check_output(
                ["git", "-C", str(target), "rev-parse", "HEAD"], text=True, env=git_env
            ).strip()

            bcmd = "cc -O0 -c src/app.c -o app.o && cc -O0 app.o -o app"
            with mock.patch.dict(os.environ, {"AJAR_HOME": str(ajar_home)}):
                init_run_workspace(
                    target=str(target),
                    target_mode="source",
                    workspace_mode="in_place",
                    run_id="run-b2-parent",
                    ajar_home=ajar_home,
                )
                pconn = open_run_db("run-b2-parent", ajar_home=ajar_home)
                try:
                    surf = add_surface(
                        pconn,
                        name="App",
                        kind="cli",
                        subsystem="src",
                        locus="src/app.c:2",
                        priority="high",
                        trust_boundary="ext->cli",
                    )
                    clm = propose_claim(
                        pconn,
                        worker_id="w-p",
                        title="Bad arg crashes",
                        locus="src/app.c:3",
                        severity="high",
                        mechanism="Returns error on bad arg",
                        surface_id=str(surf["surface_id"]),
                        falsification_prediction="Returns exit status 0 on bad input",
                        falsification_test="Run compiled app with bad arg",
                    )
                    cid = str(clm["claim_id"])
                    survive_claim(pconn, claim_id=cid, worker_id="w-f", notes="Confirmed")
                    record_reproduction_outcome(
                        pconn,
                        claim_id=cid,
                        worker_id="w-r",
                        poc_cmd="./app bad",
                        control_cmd="./app good",
                        build_cmd=bcmd,
                        repro_result={
                            "passed": True,
                            "observation_hash": "obs-b2-diff",
                            "micropatch_diff": "--- a/src/app.c\n+++ b/src/app.c\n",
                            "arm1_clean_poc": {"arm_passed": True},
                            "arm2_clean_control": {"arm_passed": True},
                            "arm3_patch_poc": {"arm_passed": True},
                            "arm4_patch_control": {"arm_passed": True},
                        },
                    )
                finally:
                    pconn.close()

                # Sync PR 1 -> finding MUST be kept (proves build_cmd ran!) and app.o preserved in slot-0!
                init_run_workspace(
                    target=str(target),
                    target_mode="source",
                    workspace_mode="in_place",
                    run_id="run-b2-child1",
                    ajar_home=ajar_home,
                )
                c1_dir = ajar_home / "runs" / "run-b2-child1"
                c1 = open_run_db("run-b2-child1", ajar_home=ajar_home)
                try:
                    sync1 = sync_pr_differential_state(
                        c1,
                        run_dir=c1_dir,
                        target_dir=target,
                        diff_range=f"{base_sha}..{pr1_sha}",
                        parent_run_id="run-b2-parent",
                        ajar_home=ajar_home,
                    )
                    self.assertEqual(len(sync1["kept_findings"]), 1)
                    self.assertEqual(len(sync1["closed_findings"]), 0)
                    self.assertTrue((c1_dir / "repro" / "slot-0" / "app.o").is_file())
                    self.assertFalse((c1_dir / "repro" / "cache-0").exists())
                finally:
                    c1.close()

                # PR commit 2: fix the bug -> diff_sync recompiles with build_cmd and closes finding!
                (target / "src" / "app.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")
                subprocess.run(["git", "-C", str(target), "add", "-A"], check=True, env=git_env)
                subprocess.run(["git", "-C", str(target), "commit", "-q", "-m", "fix"], check=True, env=git_env)
                pr2_sha = subprocess.check_output(
                    ["git", "-C", str(target), "rev-parse", "HEAD"], text=True, env=git_env
                ).strip()

                init_run_workspace(
                    target=str(target),
                    target_mode="source",
                    workspace_mode="in_place",
                    run_id="run-b2-child2",
                    ajar_home=ajar_home,
                )
                c2_dir = ajar_home / "runs" / "run-b2-child2"
                c2 = open_run_db("run-b2-child2", ajar_home=ajar_home)
                try:
                    sync2 = sync_pr_differential_state(
                        c2,
                        run_dir=c2_dir,
                        target_dir=target,
                        diff_range=f"{pr1_sha}..{pr2_sha}",
                        parent_run_id="run-b2-parent",
                        ajar_home=ajar_home,
                    )
                    self.assertEqual(len(sync2["kept_findings"]), 0)
                    self.assertEqual(len(sync2["closed_findings"]), 1)
                finally:
                    c2.close()


class TestPlannerAndSwarmB4(unittest.TestCase):
    def _record_confirmed_finding(
        self,
        conn: sqlite3.Connection,
        *,
        surface_id: str,
        title: str,
        locus: str,
        provides_tags: list[str],
    ) -> str:
        clm = propose_claim(
            conn,
            worker_id="w-prop",
            title=title,
            locus=locus,
            mechanism=f"{title} violates boundary invariant at {locus}",
            falsification_prediction="Guard rejects crafted input",
            falsification_test="Run PoC against locus",
            surface_id=surface_id,
            severity="high",
        )
        cid = str(clm["claim_id"])
        survive_claim(conn, claim_id=cid, worker_id="w-fals", notes="Verified reachable")
        out = record_reproduction_outcome(
            conn,
            claim_id=cid,
            worker_id="w-repro",
            poc_cmd="./app trigger",
            control_cmd="./app safe",
            provides_tags=provides_tags,
            repro_result={
                "passed": True,
                "observation_hash": f"obs-{cid}",
                "micropatch_diff": f"--- a/{locus.split(':', 1)[0]}\n+++ b/{locus.split(':', 1)[0]}\n",
                "arm1_clean_poc": {"arm_passed": True},
                "arm2_clean_control": {"arm_passed": True},
                "arm3_patch_poc": {"arm_passed": True},
                "arm4_patch_control": {"arm_passed": True},
            },
        )
        return str(out["finding_id"])

    def test_percolation_allows_finding_to_finding_edges_and_prevents_cycles(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            ajar_home = base / "ajar_home"
            target = base / "repo"
            _git_init_repo(
                target,
                {
                    "src/entry.c": "int entry_fn(void) { return 0; }\n",
                    "src/sink.c": "int sink_exec(void) { return 0; }\n",
                },
            )
            with mock.patch.dict(os.environ, {"AJAR_HOME": str(ajar_home)}):
                init_run_workspace(
                    target=str(target),
                    target_mode="source",
                    workspace_mode="in_place",
                    run_id="run-b4-perc",
                    ajar_home=ajar_home,
                )
                conn = open_run_db("run-b4-perc", ajar_home=ajar_home)
                try:
                    s1 = add_surface(conn, name="entry", kind="cli", locus="src/entry.c:1", priority="high")
                    s2 = add_surface(
                        conn,
                        name="privileged-sink",
                        kind="cli",
                        locus="src/sink.c:1",
                        priority="critical",
                        requires_tags=["cap:stage1_token"],
                    )
                    jwl = add_crown_jewel(
                        conn,
                        name="Terminal exec",
                        locus="src/sink.c:1",
                        impact_class="rce",
                        symbols=["sink:rce"],
                    )

                    f1 = self._record_confirmed_finding(
                        conn,
                        surface_id=str(s1["surface_id"]),
                        title="Stage 1 token forge",
                        locus="src/entry.c:1",
                        provides_tags=["cap:stage1_token"],
                    )
                    f2 = self._record_confirmed_finding(
                        conn,
                        surface_id=str(s2["surface_id"]),
                        title="Stage 2 sink trigger",
                        locus="src/sink.c:1",
                        provides_tags=["sink:rce"],
                    )

                    perc = detect_percolated_multi_hop_paths(conn, enqueue_tasks=False)
                    self.assertEqual(len(perc["percolated_paths"]), 1)
                    self.assertEqual(perc["percolated_paths"][0]["step_ids"], [f1, f2])
                    self.assertEqual(perc["percolated_paths"][0]["jewel_id"], str(jwl["jewel_id"]))

                    # Also verify cycle safety when a ready door wires a reverse edge f2 -> f1!
                    park_open_door(
                        conn,
                        anchor_locus="src/entry.c:1",
                        missing_link_summary="Cycle test reverse door",
                        jewel_id=str(jwl["jewel_id"]),
                        held_ids=[f2],
                        wanted_tags=["cap:stage1_token"],
                        spawn_hunters=False,
                    )
                    perc_cyclic = detect_percolated_multi_hop_paths(conn, enqueue_tasks=False)
                    self.assertEqual(len(perc_cyclic["percolated_paths"]), 1)
                    self.assertEqual(len(set(perc_cyclic["percolated_paths"][0]["step_ids"])), 2)
                finally:
                    conn.close()

    def test_swarm_packet_excludes_active_dispatched_items_across_parallel_dispatches(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            ajar_home = base / "ajar_home"
            target = base / "repo"
            _git_init_repo(target, {"src/app.py": "def run():\n    return 0\n"})
            with mock.patch.dict(os.environ, {"AJAR_HOME": str(ajar_home)}):
                init_run_workspace(
                    target=str(target),
                    target_mode="source",
                    workspace_mode="in_place",
                    run_id="run-b4-swarm",
                    ajar_home=ajar_home,
                )
                conn = open_run_db("run-b4-swarm", ajar_home=ajar_home)
                try:
                    surf = add_surface(conn, name="api", kind="http", locus="src/app.py:1", priority="high")
                    sid = str(surf["surface_id"])
                    cids: list[str] = []
                    for i in range(4):
                        c = propose_claim(
                            conn,
                            worker_id="w-inv",
                            title=f"Boundary bug {i}",
                            locus=f"src/app.py:{i + 1}",
                            mechanism=f"Missing check #{i} allows bypass",
                            falsification_prediction="Guard rejects request",
                            falsification_test="Call endpoint",
                            surface_id=sid,
                        )
                        cids.append(str(c["claim_id"]))

                    t_inv = add_task(
                        conn,
                        kind="investigate",
                        title="Audit remaining cone",
                        surface_id=sid,
                        locus="src/app.py:1",
                    )

                    # Two parallel falsify dispatches of limit=2 must receive disjoint item sets!
                    pkt1 = build_swarm_packet(conn, stage="falsify", limit=2, worker_id="w-f1")
                    pkt2 = build_swarm_packet(conn, stage="falsify", limit=2, worker_id="w-f2")
                    self.assertEqual(len(pkt1["item_ids"]), 2)
                    self.assertEqual(len(pkt2["item_ids"]), 2)
                    self.assertTrue(set(pkt1["item_ids"]).isdisjoint(set(pkt2["item_ids"])))
                    self.assertEqual(set(pkt1["item_ids"]) | set(pkt2["item_ids"]), set(cids))

                    # Third parallel falsify dispatch must fail cleanly (0 remaining undispatched items).
                    with self.assertRaises(AjarError):
                        build_swarm_packet(conn, stage="falsify", limit=2, worker_id="w-f3")

                    # Cross-stage `portfolio` also excludes actively dispatched claims and picks the undispatched task!
                    pkt_port = build_swarm_packet(conn, stage="portfolio", limit=4, worker_id="w-port")
                    self.assertEqual(pkt_port["item_ids"], [str(t_inv["task_id"])])

                    # Completing dispatch 1 releases its items so they can be dispatched again if still open.
                    complete_swarm_dispatch(conn, target=str(pkt1["dispatch_id"]), notes="done")
                    pkt_re = build_swarm_packet(conn, stage="falsify", limit=2, worker_id="w-f4")
                    self.assertEqual(set(pkt_re["item_ids"]), set(pkt1["item_ids"]))
                finally:
                    conn.close()

    def test_precondition_realism_defaults_to_one_step_ignoring_shell_helpers(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            ajar_home = base / "ajar_home"
            target = base / "repo"
            _git_init_repo(target, {"src/sink.c": "int sink(void) { return 0; }\n"})
            with mock.patch.dict(os.environ, {"AJAR_HOME": str(ajar_home)}):
                init_run_workspace(
                    target=str(target),
                    target_mode="source",
                    workspace_mode="in_place",
                    run_id="run-b4-realism",
                    ajar_home=ajar_home,
                )
                conn = open_run_db("run-b4-realism", ajar_home=ajar_home)
                try:
                    jwl = add_crown_jewel(
                        conn,
                        name="Single-step RCE",
                        locus="src/sink.c:1",
                        impact_class="rce",
                        max_interaction_steps=1,
                    )
                    # Multiple shell fixture/verification helpers joined by `&&` and `;` must NOT inflate step count!
                    res_default = evaluate_precondition_realism(
                        conn,
                        poc_cmd="python3 gen_fixture.py && ./target_bin --input fixture.dat && test -f pwned; grep -q OK pwned",
                        control_cmd="./target_bin --input benign.dat",
                        severity="critical",
                        target_locus="src/sink.c:1",
                        explicit_jewel_id=str(jwl["jewel_id"]),
                    )
                    self.assertEqual(res_default["interaction_steps"], 1)
                    self.assertEqual(res_default["realism_tier"], "crown_jewel")

                    # Explicit `--declared-steps 3` still records 3 steps and downgrades to `stepping_stone`.
                    res_explicit = evaluate_precondition_realism(
                        conn,
                        poc_cmd="./target_bin --input fixture.dat",
                        control_cmd="./target_bin --input benign.dat",
                        severity="critical",
                        declared_steps=3,
                        target_locus="src/sink.c:1",
                        explicit_jewel_id=str(jwl["jewel_id"]),
                    )
                    self.assertEqual(res_explicit["interaction_steps"], 3)
                    self.assertEqual(res_explicit["realism_tier"], "stepping_stone")

                    # Delusional self-override flags remain blocked.
                    with self.assertRaises(AjarError) as ctx:
                        evaluate_precondition_realism(
                            conn,
                            poc_cmd="git -c core.sshCommand=sh status",
                            control_cmd="git status",
                        )
                    self.assertEqual(ctx.exception.exit_code, EXIT_GATE_BLOCKED)
                finally:
                    conn.close()


class TestFailureTelemetryB5(unittest.TestCase):
    def _run_cli(self, argv: list[str]) -> tuple[int, dict[str, object]]:
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            rc = cli_main(argv)
        raw = out_buf.getvalue().strip() or err_buf.getvalue().strip()
        return rc, json.loads(raw)

    def test_doctor_failures_empty_and_populated_receipts_with_swarm_fallbacks(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            ajar_home = base / "ajar_home"
            target = base / "repo"
            _git_init_repo(target, {"src/app.py": "def check(x):\n    return x == 'ok'\n"})

            with mock.patch.dict(os.environ, {"AJAR_HOME": str(ajar_home)}):
                init_run_workspace(
                    target=str(target),
                    target_mode="source",
                    workspace_mode="in_place",
                    run_id="run-b5-doc",
                    ajar_home=ajar_home,
                )
                rdir = ajar_home / "runs" / "run-b5-doc"

                # 1. Empty run: 0 receipts, 0 timeouts, 0 swarm fallbacks.
                rc_empty, doc_empty = self._run_cli(["doctor", "--run", "run-b5-doc", "--failures", "--json"])
                self.assertEqual(rc_empty, 0)
                ft_empty = doc_empty["failure_telemetry"]
                assert isinstance(ft_empty, dict)
                self.assertEqual(ft_empty["schema"], "ajar-failure-telemetry/1")
                self.assertEqual(ft_empty["run_id"], "run-b5-doc")
                self.assertEqual(ft_empty["total_receipts"], 0)
                self.assertEqual(ft_empty["malformed_receipts"], 0)
                self.assertEqual(ft_empty["timeout_count"], 0)
                self.assertEqual(ft_empty["by_error_class"], {})
                self.assertEqual(ft_empty["by_rejection_reason"], {})
                self.assertEqual(ft_empty["swarm_dispatches"]["fallback_total"], 0)

                # 2. Populate failure receipts (1 real preflight + 3 synthetic + 1 malformed JSON) + swarm fallbacks.
                run_source_reproduction(
                    run_dir=rdir,
                    target_dir=target,
                    claim_id="clm-preflight",
                    poc_cmd="python3 -c 'pass'",
                    control_cmd="python3 -c 'pass'",
                    micropatch_path=rdir / "missing.diff",
                )
                fdir = rdir / "repro" / "failures"
                fdir.mkdir(parents=True, exist_ok=True)
                (fdir / "clm-neg-1.json").write_text(
                    json.dumps(
                        {
                            "schema": "ajar-repro-failure/1",
                            "claim_id": "clm-neg",
                            "error_class": "target_negative",
                            "reason": "Arm 1 (clean + PoC) did not trigger defect (0/1 hits, exit=0).",
                            "arms": {"arm1_clean_poc": {"arm_passed": False, "timed_out": True}},
                        }
                    ),
                    encoding="utf-8",
                )
                (fdir / "clm-neg-2.json").write_text(
                    json.dumps(
                        {
                            "schema": "ajar-repro-failure/1",
                            "claim_id": "clm-neg",
                            "error_class": "target_negative",
                            "reason": "Arm 1 (clean + PoC) did not trigger defect (0/1 hits, exit=1).",
                            "arms": {"arm1_clean_poc": {"arm_passed": False, "timed_out": False}},
                        }
                    ),
                    encoding="utf-8",
                )
                (fdir / "clm-bld-1.json").write_text(
                    json.dumps(
                        {
                            "schema": "ajar-repro-failure/1",
                            "claim_id": "clm-bld",
                            "error_class": "build_or_env_error",
                            "reason": "Clean-HEAD --build-cmd failed (exit=124): command timed out",
                            "arms": {},
                        }
                    ),
                    encoding="utf-8",
                )
                (fdir / "corrupt.json").write_text("{not valid json", encoding="utf-8")

                conn = open_run_db("run-b5-doc", ajar_home=ajar_home)
                try:
                    surf = add_surface(conn, name="api", kind="http", locus="src/app.py:1")
                    for idx in range(2):
                        c = propose_claim(
                            conn,
                            worker_id="w-inv",
                            title=f"Bug {idx}",
                            locus="src/app.py:1",
                            mechanism=f"Missing guard #{idx}",
                            falsification_prediction="Guard rejects bad input",
                            falsification_test="Call check()",
                            surface_id=str(surf["surface_id"]),
                        )
                        survive_claim(conn, claim_id=str(c["claim_id"]), worker_id="w-fal", notes="ok")
                    pkt = build_swarm_packet(conn, stage="reproduce", limit=2, worker_id="w-rep-1")
                    fb1 = escalate_swarm_fallback(conn, target=str(pkt["dispatch_id"]), reason="filter_blocked")
                    fb_child = fb1["recovery_packets"][0]["dispatch_id"]
                    fb2 = escalate_swarm_fallback(conn, target=str(fb_child), reason="idle_no_return")
                    complete_swarm_dispatch(conn, target=str(fb2["recovery_packets"][0]["dispatch_id"]), notes="ok")

                    direct = aggregate_failure_telemetry(rdir, conn=conn)
                    self.assertEqual(direct["total_receipts"], 4)
                    self.assertEqual(direct["malformed_receipts"], 1)
                    self.assertEqual(direct["timeout_count"], 2)
                    self.assertEqual(direct["timeouts_by_arm"], {"arm1_clean_poc": 1})
                    self.assertEqual(
                        direct["by_error_class"],
                        {
                            "build_or_env_error": 1,
                            "preflight_error": 1,
                            "target_negative": 2,
                        },
                    )
                    self.assertEqual(
                        direct["by_rejection_reason"]["Arm 1 (clean + PoC) did not trigger defect"],
                        2,
                    )
                    self.assertEqual(direct["by_claim_id"]["clm-neg"], 2)
                    self.assertEqual(direct["swarm_dispatches"]["fallback_total"], 2)
                    self.assertEqual(
                        direct["swarm_dispatches"]["fallback_by_reason"],
                        {"filter_blocked": 1, "idle_no_return": 1},
                    )
                finally:
                    conn.close()

                # 3. CLI works with explicit `--run` AND via `$AJAR_RUN_ID` when `--run` is omitted.
                with mock.patch.dict(os.environ, {"AJAR_RUN_ID": "run-b5-doc"}):
                    rc_pop, doc_pop = self._run_cli(["doctor", "--failures", "--json"])
                self.assertEqual(rc_pop, 0)
                ft_pop = doc_pop["failure_telemetry"]
                assert isinstance(ft_pop, dict)
                self.assertEqual(ft_pop["total_receipts"], 4)
                self.assertEqual(ft_pop["timeout_count"], 2)
                self.assertEqual(ft_pop["swarm_dispatches"]["fallback_total"], 2)


class TestPlatformGraphV2(unittest.TestCase):
    def _run_cli(self, argv: list[str]) -> tuple[int, dict[str, object]]:
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            rc = cli_main(argv)
        raw = out_buf.getvalue().strip() or err_buf.getvalue().strip()
        return rc, json.loads(raw)

    def test_graph_v2_zero_dangling_edges_visibility_projections_snippets_and_v1_compat(self) -> None:
        fake_tok = "ghp_" + ("1234567890" * 3) + "abcdef"
        fake_cookie = "Cook" + "ie: session=secretvalue987654"
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            ajar_home = base / "ajar_home"
            target = base / "demo-target"
            _git_init_repo(
                target,
                {
                    "src/entry.py": (
                        "from src.guard import validate_request\n"
                        "from src.sink import execute_payload\n\n"
                        "def handle_request(req):\n"
                        "    if validate_request(req):\n"
                        "        return execute_payload(req)\n"
                        "    return 0\n"
                    ),
                    "src/guard.py": (
                        "def validate_request(req):\n"
                        "    # Boundary guard checked on ingress\n"
                        "    return bool(req and not req.startswith('..'))\n"
                    ),
                    "src/sink.py": (
                        f"# fixture token comment {fake_tok}\n"
                        "def execute_payload(req):\n"
                        "    return len(req)\n"
                    ),
                },
            )
            fake_patch_path = base / "local_secret_fix.diff"
            fake_patch_path.write_text("--- a/src/entry.py\n+++ b/src/entry.py\n", encoding="utf-8")

            with mock.patch.dict(os.environ, {"AJAR_HOME": str(ajar_home)}):
                init_run_workspace(
                    target=str(target),
                    target_mode="source",
                    workspace_mode="in_place",
                    run_id="run-g2",
                    ajar_home=ajar_home,
                )
                conn = open_run_db("run-g2", ajar_home=ajar_home)
                try:
                    build_repomap(conn, target)
                    s1 = add_surface(conn, name="http-entry", kind="http", locus="src/entry.py:4", priority="critical")
                    s2 = add_surface(conn, name="guard-check", kind="http", locus="src/guard.py:1", priority="high")
                    sid1 = str(s1["surface_id"])
                    sid2 = str(s2["surface_id"])

                    # Dry verified guard on s2
                    tdry = add_task(conn, kind="investigate", title="Audit guard", surface_id=sid2, locus="src/guard.py:1")
                    conn.execute(
                        "UPDATE tasks SET status = 'leased', worker_id = 'w-dry' WHERE task_id = ?",
                        (str(tdry["task_id"]),),
                    )
                    close_task_dry(
                        conn,
                        task_id=str(tdry["task_id"]),
                        worker_id="w-dry",
                        locus="src/guard.py:3",
                        control_reason="Prefix check blocks relative path traversal at src/guard.py:3.",
                        target_dir=target,
                    )

                    # Guarded primitive (would dangle in v1!) + anomaly + steer + threat model
                    prim = add_primitive(
                        conn,
                        locus="src/sink.py:2",
                        kind="sink_reach",
                        role="trust_gadget",
                        preconditions="requires cap:bypass_guard",
                        postconditions="reaches execute_payload",
                        evidence_cmd=f"curl -H '{fake_cookie}' http://127.0.0.1/",
                        surface_id=sid1,
                        guarded_by_locus="src/guard.py:3",
                        guard_assumption="validate_request blocks traversal",
                        requires_tags=["cap:bypass_guard"],
                    )
                    pid = str(prim["primitive_id"])
                    add_anomaly(
                        conn,
                        locus="src/entry.py:5",
                        observation=f"Unexpected path accepted with {fake_tok}",
                        surface_id=sid1,
                    )
                    add_steer(conn, rule_text=f"Ignore paths outside {target}/src", scope="global")
                    upsert_threat_model(
                        conn,
                        principals=["unauthenticated_http"],
                        assets=["code_execution"],
                        summary="HTTP ingress boundary",
                    )
                    add_threat_assumption(
                        conn,
                        subsystem="src",
                        assumption_text="validate_request cannot be bypassed",
                        dependent_surface_id=sid1,
                    )

                    # Crown Jewel + Open Door
                    jwl = add_crown_jewel(
                        conn,
                        name="Payload execution sink",
                        locus="src/sink.py:2",
                        impact_class="rce",
                        symbols=["execute_payload"],
                    )
                    jid = str(jwl["jewel_id"])
                    door = park_open_door(
                        conn,
                        anchor_locus="src/sink.py:2",
                        blocker_locus="src/guard.py:3",
                        missing_link_summary="Need bypass of validate_request",
                        jewel_id=jid,
                        held_ids=[pid],
                        wanted_tags=["cap:bypass_guard"],
                        spawn_hunters=False,
                    )
                    did = str(door["door_id"])

                    # Confirmed finding (proposer != falsifier) + 9-arm patch verification + verified chain
                    clm = propose_claim(
                        conn,
                        worker_id="w-prop",
                        title="Guard bypass in handle_request",
                        locus="src/entry.py:5",
                        mechanism="handle_request accepts crafted prefix bypassing src/guard.py:3",
                        falsification_prediction="validate_request rejects encoded prefix",
                        falsification_test="Run handle_request('%2e%2e')",
                        surface_id=sid1,
                        severity="critical",
                    )
                    cid = str(clm["claim_id"])
                    survive_claim(conn, claim_id=cid, worker_id="w-fals", notes="Confirmed bypassable")
                    fnd_out = record_reproduction_outcome(
                        conn,
                        claim_id=cid,
                        worker_id="w-repro",
                        poc_cmd=f"python3 {target}/src/entry.py --token {fake_tok}",
                        control_cmd=f"python3 {target}/src/entry.py --safe",
                        build_cmd="true",
                        micropatch_path=str(fake_patch_path),
                        provides_tags=["cap:bypass_guard"],
                        repro_result={
                            "passed": True,
                            "observation_hash": "obs-g2",
                            "micropatch_diff": "--- a/src/entry.py\n+++ b/src/entry.py\n@@ -5 +5 @@\n-    if validate_request(req):\n+    if False:\n",
                            "arm1_clean_poc": {"arm_passed": True, "exit_code": 1, "defect_hits": 1, "trials": 1, "stdout": f"leak {fake_tok}"},
                            "arm2_clean_control": {"arm_passed": True, "exit_code": 0, "defect_hits": 0, "trials": 1},
                            "arm3_patch_poc": {"arm_passed": True, "exit_code": 0, "defect_hits": 0, "trials": 1},
                            "arm4_patch_control": {"arm_passed": True, "exit_code": 0, "defect_hits": 0, "trials": 1},
                        },
                    )
                    fid = str(fnd_out["finding_id"])

                    # Insert a passing 9-arm patch verification row
                    conn.execute(
                        """
                        INSERT INTO patch_verifications(
                            verification_id, finding_id, claim_id, patch_path, patch_diff,
                            suite_cmd, variant_cmds_json, caller_audit, sibling_audit,
                            arms_json, baseline_suite_json, arm7_caller_cmd, arm8_sibling_cmd,
                            arm9_revert_poc_json, passed, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, '2026-11-22T00:00:00Z')
                        """,
                        (
                            "pvf-g2-1",
                            fid,
                            cid,
                            str(fake_patch_path),
                            "--- a/src/entry.py\n+++ b/src/entry.py\n",
                            "pytest -q",
                            json.dumps(["v1", "v2", "v3"]),
                            "All callers handle false return cleanly without crash.",
                            "No sibling ingress routes bypass validate_request.",
                            json.dumps(
                                {
                                    "arm1_clean_poc": {"arm_passed": True},
                                    "arm5_full_suite": {"arm_passed": True},
                                    "arm6_bypass_variants": {"arm_passed": True},
                                    "arm7_caller_audit": {"arm_passed": True},
                                    "arm8_sibling_audit": {"arm_passed": True},
                                    "arm9_revert_poc": {"arm_passed": True},
                                }
                            ),
                            json.dumps({"passed": True}),
                            "",
                            "",
                            json.dumps({"arm_passed": True, "exit_code": 1}),
                        ),
                    )
                    conn.execute("UPDATE claims SET remediation_state = 'verified_local' WHERE claim_id = ?", (cid,))

                    # Insert a verified 2-step chain [fid, pid] + a second chain referencing a claim ID directly
                    clm2 = propose_claim(
                        conn,
                        worker_id="w-prop",
                        title="Unreproduced companion claim",
                        locus="src/guard.py:2",
                        mechanism="Secondary guard observation",
                        falsification_prediction="Guard validates normalized path before execute_payload",
                        falsification_test="Check guard.py",
                        surface_id=sid2,
                    )
                    cid2 = str(clm2["claim_id"])
                    conn.execute(
                        """
                        INSERT INTO chains(
                            chain_id, title, severity, step_ids_json, e2e_poc_cmd, control_cmd,
                            verified, evidence_json, slot_index, oracle_json, ablation_matrix_json,
                            realism_tier, realism_json, jewel_id, door_id, created_at
                        ) VALUES (?, ?, 'critical', ?, ?, ?, 1, ?, 0, '{}', ?, 'crown_jewel', ?, ?, ?, '2026-11-22T00:00:00Z')
                        """,
                        (
                            "chn-g2-1",
                            "Bypass guard into execute_payload Crown Jewel",
                            json.dumps([fid, pid]),
                            f"python3 {target}/src/entry.py --chain {fake_tok}",
                            "python3 src/entry.py --safe",
                            json.dumps({"reason": "Verified 2-step chain", "build_cmd": "true"}),
                            json.dumps(
                                [
                                    {"step_id": fid, "ablated_via": "step_micropatch", "causally_required": True, "defect_still_fired": False},
                                    {"step_id": pid, "ablated_via": "stage_context_env", "causally_required": True, "defect_still_fired": False},
                                ]
                            ),
                            json.dumps({"realism_tier": "crown_jewel", "interaction_steps": 1}),
                            jid,
                            did,
                        ),
                    )
                    conn.execute(
                        """
                        INSERT INTO chains(
                            chain_id, title, severity, step_ids_json, e2e_poc_cmd, control_cmd,
                            verified, evidence_json, slot_index, oracle_json, ablation_matrix_json,
                            realism_tier, realism_json, jewel_id, door_id, created_at
                        ) VALUES ('chn-g2-2', 'Claim step ref chain', 'high', ?, 'true', 'true', 0, '{}', 0, '{}', '[]', 'stepping_stone', '{}', '', '', '2026-11-22T00:01:00Z')
                        """,
                        (json.dumps([cid2, pid]),),
                    )

                    # 1. Default v2 (`internal_full`) with `--include-snippets --repo-slug acme/demo-target`
                    g_int = export_attack_flow_graph(
                        conn,
                        schema="v2",
                        visibility="internal_full",
                        include_snippets=True,
                        repo_slug="acme/demo-target",
                    )
                    self.assertEqual(g_int["schema"], "ajar-platform-graph/2")
                    self.assertEqual(g_int["visibility"], "internal_full")
                    self.assertEqual(g_int["run"]["repo_slug"], "acme/demo-target")
                    self.assertEqual(g_int["run"]["target_path"], str(target.resolve()))
                    self.assertTrue(g_int["run"]["head_sha"])
                    self.assertEqual(g_int["summary"]["dangling_edges"], 0)

                    # Zero dangling edges invariant!
                    node_ids = {n["id"] for n in g_int["nodes"]}
                    for edge in g_int["edges"]:
                        self.assertIn(edge["src"], node_ids, f"Dangling src: {edge}")
                        self.assertIn(edge["dst"], node_ids, f"Dangling dst: {edge}")
                        self.assertNotEqual(edge["edge_type"], "symbol_call")
                        self.assertFalse(str(edge["src"]).startswith("file:"))
                        self.assertFalse(str(edge["dst"]).startswith("file:"))

                    # Concrete `guard_locus`, `crown_jewel`, `open_door` nodes & `chain_transition` edges
                    self.assertTrue(any(n["id"] == "locus:src/guard.py:3" and n["node_type"] == "guard_locus" for n in g_int["nodes"]))
                    self.assertTrue(any(n["id"] == jid and n["node_type"] == "crown_jewel" for n in g_int["nodes"]))
                    self.assertTrue(any(n["id"] == did and n["node_type"] == "open_door" for n in g_int["nodes"]))
                    self.assertTrue(
                        any(
                            e["edge_type"] == "chain_transition"
                            and e["src"] == fid
                            and e["dst"] == pid
                            and e["step_order"] == 1
                            and e["chain_id"] == "chn-g2-1"
                            for e in g_int["edges"]
                        )
                    )
                    self.assertGreaterEqual(len(g_int["code_graph"]["repomap_edges"]), 1)

                    # Rich projections: findings_detail (4-arm + 9-arm + proposer != falsifier + realism_tier), chains_detail, snippets, verification_summary
                    self.assertEqual(len(g_int["findings_detail"]), 1)
                    fd = g_int["findings_detail"][0]
                    self.assertEqual(fd["finding_id"], fid)
                    self.assertTrue(fd["reproduction_4arm"]["all_4_arms_passed"])
                    self.assertTrue(fd["falsifier_separation"]["independent_falsifier_verified"])
                    self.assertIsNotNone(fd["fix_9arm"])
                    self.assertTrue(fd["fix_9arm"]["passed"])
                    self.assertTrue(fd["fix_9arm"]["arm9_revert_passed"])
                    self.assertEqual(fd["fix_9arm"]["variant_count"], 3)

                    ch1 = next(c for c in g_int["chains_detail"] if c["chain_id"] == "chn-g2-1")
                    self.assertEqual([s["step_id"] for s in ch1["ordered_steps"]], [fid, pid])
                    self.assertEqual([s["step_order"] for s in ch1["ordered_steps"]], [1, 2])
                    self.assertTrue(ch1["ablation_proof"]["all_steps_causally_required"])

                    # Code snippets bounded & scrubbed (no secret token!)
                    self.assertGreaterEqual(len(g_int["code_snippets"]), 1)
                    self.assertTrue(all(not sn["rel_path"].startswith("/") for sn in g_int["code_snippets"]))
                    raw_int = json.dumps(g_int)
                    self.assertNotIn(fake_tok, raw_int)
                    self.assertNotIn("secretvalue987654", raw_int)

                    # Verification summary
                    vs = g_int["verification_summary"]
                    self.assertEqual(vs["scope_notice"], SCOPE_NOTICE)
                    for gate_key in (
                        "G1_surface_coverage",
                        "G2_claim_resolution",
                        "G3_causal_reproduction",
                        "G4_zero_skill_and_dry_rigor",
                        "G5_anomalies_and_chains",
                    ):
                        self.assertIn(gate_key, vs["gates"])
                    self.assertEqual(vs["funnel"]["confirmed_findings"], 1)
                    self.assertEqual(vs["funnel"]["patch_verifications_passed"], 1)
                finally:
                    conn.close()

                # 2. CLI `--visibility customer_private` and `public_disclosure`: ZERO absolute local paths & ZERO secrets!
                for vis in ("customer_private", "public_disclosure"):
                    rc_v, g_v = self._run_cli(
                        [
                            "export-graph",
                            "--run",
                            "run-g2",
                            "--visibility",
                            vis,
                            "--repo-slug",
                            "acme/demo-target",
                            "--include-snippets",
                        ]
                    )
                    self.assertEqual(rc_v, 0)
                    self.assertEqual(g_v["schema"], "ajar-platform-graph/2")
                    self.assertEqual(g_v["visibility"], vis)
                    run_meta = g_v["run"]
                    assert isinstance(run_meta, dict)
                    self.assertNotIn("target_path", run_meta)
                    self.assertNotIn("workspace_path", run_meta)
                    self.assertEqual(run_meta["repo_slug"], "acme/demo-target")
                    raw_v = json.dumps(g_v)
                    self.assertNotIn(str(target), raw_v)
                    self.assertNotIn(str(target.resolve()), raw_v)
                    self.assertNotIn(str(ajar_home), raw_v)
                    self.assertNotIn(str(fake_patch_path), raw_v)
                    self.assertNotIn(fake_tok, raw_v)
                    self.assertNotIn("secretvalue987654", raw_v)
                    if vis == "public_disclosure":
                        self.assertEqual(g_v["active_steers"], [])
                        self.assertEqual(g_v["epistemic_hooks"], [])
                        f_pub = g_v["findings_detail"][0]  # type: ignore[index]
                        self.assertNotIn("poc_cmd", f_pub["reproduction_4arm"])
                        self.assertTrue(f_pub["falsifier_separation"]["independent_falsifier_verified"])
                        self.assertNotIn("proposer_worker_id", f_pub["falsifier_separation"])
                        self.assertNotIn("total_spend_usd", g_v["verification_summary"]["economics"])  # type: ignore[index]

                # 3. Snippets omitted by default when `--include-snippets` is not passed
                rc_nosnip, g_nosnip = self._run_cli(["export-graph", "--run", "run-g2"])
                self.assertEqual(rc_nosnip, 0)
                self.assertEqual(g_nosnip["code_snippets"], [])

                # 4. `--schema v1` stays 100% backward compatible and scrubbed
                rc_v1, g_v1 = self._run_cli(["export-graph", "--schema", "v1", "--run", "run-g2"])
                self.assertEqual(rc_v1, 0)
                self.assertEqual(g_v1["schema"], "ajar-platform-graph/1")
                self.assertEqual(g_v1["run_id"], "run-g2")
                self.assertTrue(any(e["edge_type"] == "symbol_call" for e in g_v1["edges"]))  # type: ignore[index]
                self.assertNotIn(fake_tok, json.dumps(g_v1))


class TestPR243ReviewRegressions(unittest.TestCase):
    def test_b3_clean_arm_unlinks_fifo_and_unix_socket_and_rejects_deleted_build_dir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            target = base / "repo"
            rdir = base / "run"
            _git_init_repo(target, {"src/app.py": "print('ok')\n"})
            mirror = init_source_mirror(rdir, target)
            slot_dir = rdir / "repro" / "slot-0"
            _prepare_slot_worktree(mirror, slot_dir)

            # Simulate build_cmd creating a compiled artifact and an empty runtime directory.
            (slot_dir / "app.bin").write_text("bin", encoding="utf-8")
            rt_dir = slot_dir / "build" / "runtime_dir"
            rt_dir.mkdir(parents=True, exist_ok=True)
            snap = _snapshot_clean_build_outputs(slot_dir)
            self.assertIsNotNone(snap)
            assert snap is not None
            self.assertIn("build/runtime_dir", snap.dirs)

            # 1. Arm-1 creates a FIFO and a Unix domain socket inside a new scratch directory.
            fifo_path = slot_dir / "arm1.fifo"
            os.mkfifo(fifo_path)
            sock_dir = slot_dir / "arm1_ipc"
            sock_dir.mkdir()
            sock_path = sock_dir / "s.sock"
            srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                srv.bind(str(sock_path))
            finally:
                srv.close()

            self.assertTrue(_try_clean_arm_preserving_build(slot_dir, snap))
            self.assertFalse(fifo_path.exists())
            self.assertFalse(sock_path.exists())
            self.assertFalse(sock_dir.exists())
            self.assertTrue((slot_dir / "app.bin").is_file())
            self.assertTrue(rt_dir.is_dir())

            # 2. If Arm-1 deletes a build_cmd runtime directory, cleanup must return False to force rebuild.
            rt_dir.rmdir()
            self.assertFalse(_try_clean_arm_preserving_build(slot_dir, snap))

            # 3. Replacing a snapshot directory with a symlink must also return False.
            rt_dir.symlink_to(slot_dir / "src")
            self.assertFalse(_try_clean_arm_preserving_build(slot_dir, snap))
            rt_dir.unlink(missing_ok=True)
            rt_dir.mkdir(exist_ok=True)

            # 4. Non-empty Arm-1 scratch directory that cannot be removed fails closed (returns False).
            stuck_dir = slot_dir / "arm1_stuck"
            stuck_dir.mkdir()
            with mock.patch("pathlib.Path.rmdir", side_effect=OSError("Directory not empty")):
                self.assertFalse(_try_clean_arm_preserving_build(slot_dir, snap))

    def test_b5_end_to_end_real_build_cmd_timeout_counted_by_telemetry(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            ajar_home = base / "ajar_home"
            target = base / "repo"
            _git_init_repo(target, {"src/app.c": "int main(void) { return 0; }\n"})
            mpatch = base / "fix.diff"
            mpatch.write_text(
                "--- a/src/app.c\n"
                "+++ b/src/app.c\n"
                "@@ -1 +1 @@\n"
                "-int main(void) { return 0; }\n"
                "+int main(void) { return 1; }\n",
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {"AJAR_HOME": str(ajar_home)}):
                init_run_workspace(
                    target=str(target),
                    target_mode="source",
                    workspace_mode="in_place",
                    run_id="run-b5-e2e-to",
                    ajar_home=ajar_home,
                )
                rdir = ajar_home / "runs" / "run-b5-e2e-to"

                orig_run_shell = _run_shell_in_slot

                def _short_timeout_shell(*args: object, **kwargs: object) -> dict[str, object]:
                    kwargs["timeout_sec"] = 1
                    return orig_run_shell(*args, **kwargs)  # type: ignore[arg-type]

                with mock.patch("ajar.repro_source._run_shell_in_slot", side_effect=_short_timeout_shell):
                    res = run_source_reproduction(
                        run_dir=rdir,
                        target_dir=target,
                        claim_id="clm-b5-timeout",
                        poc_cmd="./app",
                        control_cmd="./app",
                        build_cmd="sleep 5",
                        micropatch_path=mpatch,
                        timeout_sec=1,
                    )

                self.assertFalse(res["passed"])
                self.assertEqual(res["error_class"], "build_or_env_error")
                self.assertTrue(res["timed_out"])
                self.assertIn("timed out", str(res["reason"]).lower())
                rel_art = str(res["failure_artifact"])
                receipt = json.loads((rdir / rel_art).read_text(encoding="utf-8"))
                self.assertTrue(receipt["timed_out"])
                self.assertTrue(receipt["build_clean"]["timed_out"])

                telemetry = aggregate_failure_telemetry(rdir)
                self.assertEqual(telemetry["total_receipts"], 1)
                self.assertEqual(telemetry["timeout_count"], 1)
                self.assertEqual(telemetry["timeouts_by_arm"], {"build_clean": 1})
                self.assertEqual(telemetry["by_error_class"], {"build_or_env_error": 1})

    def test_graph_v2_sanitizes_flag_path_file_uri_non_home_ajar_home_local_origin_and_door_claims(self) -> None:
        alice_home = "/" + "home" + "/alice"
        bob_users = "/" + "Users" + "/bob"
        var_tmp_p = "/var/tmp/build_scratch/out.bin"
        root_p = "/root/private/tools"
        shared_p = "/shared/user/mirror/run-1"
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            # Non-$HOME AJAR_HOME combined with workspace_mode="in_place" (workspace_path != ajar_home!)
            custom_ajar_home = base / "custom-ajar-store"
            target = base / "sample-repo"
            _git_init_repo(target, {"src/app.c": "int main(void) { return 0; }\n"})
            # Set local filesystem path as remote.origin.url -> must NOT leak into repo_slug!
            subprocess.run(
                ["git", "-C", str(target), "remote", "add", "origin", f"{alice_home}/mirrors/sample-repo.git"],
                check=True,
                capture_output=True,
            )

            with mock.patch.dict(os.environ, {"AJAR_HOME": str(custom_ajar_home)}):
                init_run_workspace(
                    target=str(target),
                    target_mode="source",
                    workspace_mode="in_place",
                    run_id="run-g2-san",
                    ajar_home=custom_ajar_home,
                )
                conn = open_run_db("run-g2-san", ajar_home=custom_ajar_home)
                try:
                    surf = add_surface(conn, name="cli", kind="cli", locus="src/app.c:1", priority="high")
                    sid = str(surf["surface_id"])

                    # Unreproduced claim held by an Open Door (Polish #2: must keep `door_holds_step` edge!)
                    clm_held = propose_claim(
                        conn,
                        worker_id="w-inv",
                        title="Held door claim",
                        locus="src/app.c:1",
                        mechanism="Candidate flaw parked on open door",
                        falsification_prediction="Guard blocks malformed input before main",
                        falsification_test="Run ./app malformed",
                        surface_id=sid,
                    )
                    cid_held = str(clm_held["claim_id"])
                    door = park_open_door(
                        conn,
                        anchor_locus="src/app.c:1",
                        missing_link_summary="Needs upstream trigger",
                        held_ids=[cid_held],
                        spawn_hunters=False,
                    )
                    did = str(door["door_id"])

                    # Embed tricky local path forms AND legitimate http(s) URLs in steer + finding
                    add_steer(
                        conn,
                        rule_text=(
                            f"PATH=/usr/bin:{alice_home}/bin:{var_tmp_p} "
                            f"gcc -I{alice_home}/inc -L{alice_home}/lib -Wl,-rpath,{alice_home}/lib -o{var_tmp_p} "
                            "args=/tmp/csv_a,/tmp/csv_b "
                            f"file://{bob_users}/repo/src/app.c {root_p} {shared_p} "
                            f"state={custom_ajar_home}/runs/run-g2-san/artifacts/a.txt "
                            "docs=https://example.com/home/guide health=http://127.0.0.1:8080/tmp/health"
                        ),
                        scope="global",
                    )

                    g_cust = export_attack_flow_graph(conn, schema="v2", visibility="customer_private")
                    self.assertEqual(g_cust["run"]["repo_slug"], "sample-repo")
                    self.assertEqual(g_cust["summary"]["dangling_edges"], 0)

                    # Verify Polish #2: `clm-*` in open_door held_ids gets a claim node & `door_holds_step` edge!
                    node_ids = {n["id"] for n in g_cust["nodes"]}
                    self.assertIn(cid_held, node_ids)
                    self.assertTrue(
                        any(
                            e["src"] == cid_held and e["dst"] == did and e["edge_type"] == "door_holds_step"
                            for e in g_cust["edges"]
                        )
                    )
                    for edge in g_cust["edges"]:
                        self.assertIn(edge["src"], node_ids)
                        self.assertIn(edge["dst"], node_ids)

                    raw_cust = json.dumps(g_cust)
                    for forbidden in (
                        "alice",
                        "bob",
                        "/tmp/csv_a",
                        "/tmp/csv_b",
                        var_tmp_p,
                        root_p,
                        shared_p,
                        str(custom_ajar_home),
                        str(target),
                    ):
                        self.assertNotIn(forbidden, raw_cust, f"Leaked local path fragment: {forbidden}")
                    # Legitimate HTTP(S) URLs must remain intact!
                    self.assertIn("https://example.com/home/guide", raw_cust)
                    self.assertIn("http://127.0.0.1:8080/tmp/health", raw_cust)
                finally:
                    conn.close()

    def test_b2_diff_sync_build_cmd_failure_does_not_mark_prior_finding_falsified_or_closed(self) -> None:
        if not shutil.which("cc"):
            self.skipTest("C compiler `cc` not available")
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            ajar_home = base / "ajar_home"
            target = base / "c-diff-fail"
            _git_init_repo(
                target,
                {
                    "src/app.c": (
                        "#include <string.h>\n"
                        "int main(int argc, char **argv) {\n"
                        "    return (argc > 1 && strcmp(argv[1], \"bad\") == 0) ? 1 : 0;\n"
                        "}\n"
                    ),
                },
            )
            git_env = {
                **os.environ,
                "GIT_AUTHOR_NAME": "Ajar Test",
                "GIT_AUTHOR_EMAIL": "test@example.invalid",
                "GIT_COMMITTER_NAME": "Ajar Test",
                "GIT_COMMITTER_EMAIL": "test@example.invalid",
            }
            base_sha = subprocess.check_output(
                ["git", "-C", str(target), "rev-parse", "HEAD"], text=True, env=git_env
            ).strip()

            # PR commit changes signature / breaks prior build_cmd without proving the bug was fixed.
            (target / "src" / "app.c").write_text("int main(void) { return UNDEFINED_SYMBOL; }\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(target), "add", "-A"], check=True, env=git_env)
            subprocess.run(["git", "-C", str(target), "commit", "-q", "-m", "break build"], check=True, env=git_env)
            head_sha = subprocess.check_output(
                ["git", "-C", str(target), "rev-parse", "HEAD"], text=True, env=git_env
            ).strip()

            with mock.patch.dict(os.environ, {"AJAR_HOME": str(ajar_home)}):
                init_run_workspace(
                    target=str(target),
                    target_mode="source",
                    workspace_mode="in_place",
                    run_id="run-b2-bf-parent",
                    ajar_home=ajar_home,
                )
                pconn = open_run_db("run-b2-bf-parent", ajar_home=ajar_home)
                try:
                    surf = add_surface(pconn, name="cli", kind="cli", locus="src/app.c:2")
                    clm = propose_claim(
                        pconn,
                        worker_id="w-p",
                        title="CLI accepts bad arg",
                        locus="src/app.c:3",
                        mechanism="main returns 1 on bad arg",
                        falsification_prediction="main ignores argv[1]",
                        falsification_test="run ./app bad",
                        surface_id=str(surf["surface_id"]),
                    )
                    cid = str(clm["claim_id"])
                    survive_claim(pconn, claim_id=cid, worker_id="w-f", notes="ok")
                    fnd = record_reproduction_outcome(
                        pconn,
                        claim_id=cid,
                        worker_id="w-r",
                        poc_cmd="./app bad",
                        control_cmd="./app good",
                        build_cmd="cc -O1 src/app.c -o app",
                        repro_result={
                            "passed": True,
                            "observation_hash": "obs-b2-bf",
                            "micropatch_diff": "--- a/src/app.c\n+++ b/src/app.c\n",
                            "arm1_clean_poc": {"arm_passed": True},
                            "arm2_clean_control": {"arm_passed": True},
                            "arm3_patch_poc": {"arm_passed": True},
                            "arm4_patch_control": {"arm_passed": True},
                        },
                    )
                    pfid = str(fnd["finding_id"])
                finally:
                    pconn.close()

                init_run_workspace(
                    target=str(target),
                    target_mode="source",
                    workspace_mode="in_place",
                    run_id="run-b2-bf-child",
                    ajar_home=ajar_home,
                )
                cdir = ajar_home / "runs" / "run-b2-bf-child"
                cconn = open_run_db("run-b2-bf-child", ajar_home=ajar_home)
                try:
                    sync = sync_pr_differential_state(
                        cconn,
                        run_dir=cdir,
                        target_dir=target,
                        diff_range=f"{base_sha}..{head_sha}",
                        parent_run_id="run-b2-bf-parent",
                        ajar_home=ajar_home,
                    )
                    self.assertEqual(sync["kept_findings"], [])
                    self.assertEqual(sync["closed_findings"], [])
                    self.assertEqual(len(sync["build_failed_findings"]), 1)
                    bf = sync["build_failed_findings"][0]
                    self.assertEqual(bf["finding_id"], pfid)

                    # Must NOT have inserted a falsified / closed claim!
                    falsified_cnt = cconn.execute(
                        "SELECT COUNT(*) AS c FROM claims WHERE status = 'falsified' OR diff_state = 'closed'"
                    ).fetchone()["c"]
                    self.assertEqual(int(falsified_cnt), 0)

                    # Must have enqueued an open high-salience investigate task for re-verification!
                    trow = cconn.execute(
                        "SELECT kind, status, salience_score, diff_state FROM tasks WHERE task_id = ?",
                        (bf["reverify_task_id"],),
                    ).fetchone()
                    self.assertIsNotNone(trow)
                    self.assertEqual(str(trow["kind"]), "investigate")
                    self.assertEqual(str(trow["status"]), "open")
                    self.assertEqual(str(trow["diff_state"]), "build_failed")
                    self.assertGreaterEqual(int(trow["salience_score"]), 90)
                finally:
                    cconn.close()


if __name__ == "__main__":
    unittest.main()
