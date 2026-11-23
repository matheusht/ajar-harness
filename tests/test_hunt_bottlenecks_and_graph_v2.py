"""Unit and integration tests for Weeks 1–2 Hunt Bottlenecks (B1–B5) and `ajar-platform-graph/2`."""

from __future__ import annotations

import fcntl
import io
import json
import os
import pathlib
import shutil
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
from ajar.db import open_run_db
from ajar.diff_sync import sync_pr_differential_state
from ajar.domain.models import AjarError
from ajar.redact import scrubbed_subprocess_env
from ajar.repomap import REPOMAP_EDGE_CAP, _extract_regex_symbols, build_repomap
from ajar.repro_compose import (
    run_chain_reproduction,
    run_claim_instrumentation,
    run_snapshot_chain_probe,
)
from ajar.repro_source import (
    _run_shell_in_slot,
    aggregate_failure_telemetry,
    capture_slot_post_state_snapshot,
    init_source_mirror,
    resolve_local_build_cache_dir,
    resolve_shared_compiler_cache_env,
    run_source_reproduction,
)
from ajar.services import (
    add_surface,
    add_task,
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


if __name__ == "__main__":
    unittest.main()
