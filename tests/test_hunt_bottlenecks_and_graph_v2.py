"""Unit and integration tests for Weeks 1–2 Hunt Bottlenecks (B1–B5) and `ajar-platform-graph/2`."""

from __future__ import annotations

import fcntl
import json
import os
import pathlib
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from unittest import mock

from ajar.db import open_run_db
from ajar.redact import scrubbed_subprocess_env
from ajar.repomap import REPOMAP_EDGE_CAP, _extract_regex_symbols, build_repomap
from ajar.repro_compose import run_claim_instrumentation, run_snapshot_chain_probe
from ajar.repro_source import (
    _run_shell_in_slot,
    capture_slot_post_state_snapshot,
    init_source_mirror,
    resolve_local_build_cache_dir,
    resolve_shared_compiler_cache_env,
    run_source_reproduction,
)
from ajar.services import add_surface, propose_claim
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
                    "OPENAI_API_KEY": "sk-proj-secret1234567890abcdef",
                }
            )
            self.assertEqual(env["RUSTC_WRAPPER"], "sccache")
            self.assertEqual(env["SCCACHE_DIR"], str(base / "custom-sccache"))
            self.assertEqual(env["CCACHE_DIR"], str(base / "custom-ccache"))
            self.assertNotIn("OPENAI_API_KEY", env)


if __name__ == "__main__":
    unittest.main()
