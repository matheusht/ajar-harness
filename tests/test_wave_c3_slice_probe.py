"""Integration and CLI/MCP parity tests for Track C3 (`ajar repro slice-probe` / `ajar_repro_slice_probe`)."""

from __future__ import annotations

import io
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from typing import Any
from unittest import mock

from ajar.cli import main as cli_main
from ajar.db import open_run_db, record_repro_failure
from ajar.domain import AjarError
from ajar.mcp import MCP_TOOLS, dispatch_mcp_tool, handle_jsonrpc_message


def _run_cli_raw(argv: list[str]) -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = cli_main(argv)
    return rc, out.getvalue(), err.getvalue()


def _run_cli_json(argv: list[str]) -> tuple[int, dict[str, Any]]:
    rc, raw_out, raw_err = _run_cli_raw(argv)
    stripped = raw_out.strip()
    data: dict[str, Any] = json.loads(stripped) if stripped.startswith("{") else {"raw": stripped}
    if raw_err.strip():
        data["_stderr"] = raw_err.strip()
    return rc, data


def _init_git_repo(repo_dir: pathlib.Path, files: dict[str, str]) -> pathlib.Path:
    repo_dir.mkdir(parents=True, exist_ok=True)
    for rel_path, content in files.items():
        fp = repo_dir / rel_path
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_dir, check=True)
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial target commit"], cwd=repo_dir, check=True)
    return repo_dir


def _assert_clean_git_repo(tc: unittest.TestCase, repo_dir: pathlib.Path) -> None:
    st = subprocess.run(
        ["git", "-C", str(repo_dir), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    )
    tc.assertEqual(st.stdout.strip(), "", f"Target checkout was mutated:\n{st.stdout}")


class TestWaveC3SliceProbe(unittest.TestCase):
    def test_python_multi_branch_slice_probe_coverage_and_socket_guard(self) -> None:
        py_src = (
            '"""Parser module."""\n'
            "import socket\n"
            "\n"
            "def parse_packet(magic: int, mode: int = 0) -> int:\n"
            '    """Check packet framing."""\n'
            "    if magic == 0x1337:\n"
            "        inner_val = magic + 1\n"
            "        if mode == 9:\n"
            "            return inner_val * 2\n"
            "        return inner_val\n"
            "    elif magic == 0x2000:\n"
            "        return 7\n"
            "    return 0\n"
            "\n"
            "def try_external_connect() -> str:\n"
            "    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
            "    try:\n"
            "        s.connect(('198.51.100.1', 80))\n"
            "        return 'connected'\n"
            "    except PermissionError as exc:\n"
            "        return f'blocked:{exc}'\n"
            "    finally:\n"
            "        s.close()\n"
        )
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            ajar_home = base / "ajar_home"
            target = _init_git_repo(base / "py_target", {"pkg/app.py": py_src})

            with mock.patch.dict(os.environ, {"AJAR_HOME": str(ajar_home)}):
                rc_init, init_data = _run_cli_json(["init", "--in-place", "--json", str(target)])
                self.assertEqual(rc_init, 0)
                rid = str(init_data["run_id"])

                # 1. Blocked input (magic=0): outer checks visited, inner 0x1337 & 0x2000 branches unreached.
                rc_sp, res = _run_cli_json(
                    [
                        "repro",
                        "slice-probe",
                        "--run",
                        rid,
                        "--focus-locus",
                        "pkg/app.py:4-13",
                        "--cmd",
                        "python3 -c 'from pkg import app; assert app.parse_packet(0) == 0'",
                        "--record-coverage",
                        "--json",
                    ]
                )
                self.assertEqual(rc_sp, 0)
                self.assertTrue(res["ok"])
                self.assertEqual(res["tracer_used"], "python")
                self.assertTrue(res["coverage_collected"])
                self.assertIn(6, res["visited_lines_in_window"])   # if magic == 0x1337:
                self.assertIn(11, res["visited_lines_in_window"])  # elif magic == 0x2000:
                self.assertIn(13, res["visited_lines_in_window"])  # return 0
                self.assertIn(7, res["unreached_lines_in_window"]) # inner_val = magic + 1
                self.assertIn(8, res["unreached_lines_in_window"])
                self.assertIn(9, res["unreached_lines_in_window"])
                self.assertIn(10, res["unreached_lines_in_window"])
                self.assertIn(12, res["unreached_lines_in_window"])
                self.assertEqual(res["first_blocker_line"], 7)

                annotated = str(res["annotated_slice"])
                self.assertIn("# @VISITED (hits=1)", annotated)
                self.assertIn("# @UNREACHED <-- FIRST_UNREACHED_AFTER_GUARD", annotated)

                # Plain text output mode (without `--json`) emits the annotated slice directly.
                rc_txt, txt_out, _ = _run_cli_raw(
                    [
                        "repro",
                        "slice-probe",
                        "--run",
                        rid,
                        "--focus-locus",
                        "pkg/app.py:4-13",
                        "--cmd",
                        "python3 -c 'from pkg import app; app.parse_packet(0x1337, 0)'",
                    ]
                )
                self.assertEqual(rc_txt, 0)
                self.assertIn("7 |         inner_val = magic + 1  # @VISITED (hits=1)", txt_out)
                self.assertIn("9 |             return inner_val * 2  # @UNREACHED <-- FIRST_UNREACHED_AFTER_GUARD", txt_out)

                # Verify `--record-coverage` persisted SHA-bound spans without crossing unreached inner branches.
                conn = open_run_db(rid, ajar_home=ajar_home)
                try:
                    cov_rows = conn.execute(
                        "SELECT rel_path, start_line, end_line, file_sha256 FROM coverage_spans ORDER BY start_line ASC"
                    ).fetchall()
                finally:
                    conn.close()
                self.assertGreaterEqual(len(cov_rows), 2)
                for crow in cov_rows:
                    self.assertEqual(crow["rel_path"], "pkg/app.py")
                    self.assertTrue(bool(crow["file_sha256"]))
                    for lno in range(int(crow["start_line"]), int(crow["end_line"]) + 1):
                        self.assertNotIn(lno, {7, 8, 9, 10})

                # 2. Verify `repro/helpers/sitecustomize.py` is chained FIRST so `AJAR_BLOCK_EXTERNAL_NET=1`
                #    still blocks outbound non-loopback sockets inside the traced Python process,
                #    and secret tokens in stdout are scrubbed.
                dyn_tok = "ghp_" + ("X" * 36)
                rc_net, net_res = _run_cli_json(
                    [
                        "repro",
                        "slice-probe",
                        "--run",
                        rid,
                        "--focus-locus",
                        "pkg/app.py:15-24",
                        "--cmd",
                        (
                            f"AJAR_BLOCK_EXTERNAL_NET=1 python3 -c "
                            f"'from pkg import app; r = app.try_external_connect(); print(r, \"{dyn_tok}\")'"
                        ),
                        "--json",
                    ]
                )
                self.assertEqual(rc_net, 0)
                self.assertTrue(net_res["coverage_collected"])
                self.assertIn(18, net_res["visited_lines_in_window"])
                self.assertIn(21, net_res["visited_lines_in_window"])
                self.assertNotIn(19, net_res["visited_lines_in_window"])
                self.assertIn("blocked:Ajar source isolation blocked outbound non-loopback socket connect", net_res["result"]["stdout"])
                self.assertNotIn(dyn_tok, json.dumps(net_res))

                _assert_clean_git_repo(self, target)

    @unittest.skipUnless(shutil.which("gcc") and shutil.which("gcov"), "gcc and gcov required")
    def test_c_gcov_prog_foo_naming_asan_ubsan_and_gcda_cleanup(self) -> None:
        c_src = (
            "#include <limits.h>\n"
            "#include <stdlib.h>\n"
            "\n"
            "int process_frame(int tag, int delta) {\n"
            "    char *buf = (char *)malloc(8);\n"
            "    if (!buf) return -1;\n"
            "    if (tag == 4919) {\n"
            "        volatile int idx = 12;\n"
            "        buf[idx] = 0x41;\n"
            "        free(buf);\n"
            "        return 1;\n"
            "    }\n"
            "    if (tag == 7777) {\n"
            "        int ovf = INT_MAX + delta;\n"
            "        free(buf);\n"
            "        return ovf;\n"
            "    }\n"
            "    free(buf);\n"
            "    return 0;\n"
            "}\n"
            "\n"
            "int main(int argc, char **argv) {\n"
            "    int tag = argc > 1 ? atoi(argv[1]) : 0;\n"
            "    int delta = argc > 2 ? atoi(argv[2]) : 1;\n"
            "    return process_frame(tag, delta);\n"
            "}\n"
        )
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            ajar_home = base / "ajar_home"
            target = _init_git_repo(base / "c_target", {"sub/frame.c": c_src})

            with mock.patch.dict(os.environ, {"AJAR_HOME": str(ajar_home)}):
                rc_init, init_data = _run_cli_json(["init", "--in-place", "--json", str(target)])
                self.assertEqual(rc_init, 0)
                rid = str(init_data["run_id"])
                run_dir = ajar_home / "runs" / rid
                slot0 = run_dir / "repro" / "slot-0"

                # Run 1: single-step `-o prog` (`prog-frame.gcda` naming) on blocked input (`tag=0`).
                rc1, r1 = _run_cli_json(
                    [
                        "repro",
                        "slice-probe",
                        "--run",
                        rid,
                        "--focus-locus",
                        "sub/frame.c:4-20",
                        "--build-cmd",
                        "gcc $AJAR_COV_CFLAGS $AJAR_SAN_CFLAGS sub/frame.c -o prog",
                        "--cmd",
                        "./prog 0",
                        "--sanitize",
                        "--json",
                    ]
                )
                self.assertEqual(rc1, 0)
                self.assertTrue(r1["ok"])
                self.assertEqual(r1["tracer_used"], "gcov")
                self.assertTrue(r1["coverage_collected"])
                self.assertFalse(r1["sanitizer_triggered"])
                self.assertIn(7, r1["visited_lines_in_window"])    # if (tag == 4919)
                self.assertIn(13, r1["visited_lines_in_window"])   # if (tag == 7777)
                self.assertIn(18, r1["visited_lines_in_window"])   # free(buf);
                self.assertIn(8, r1["unreached_lines_in_window"])  # volatile int idx = 12;
                self.assertIn(9, r1["unreached_lines_in_window"])  # buf[idx] = 0x41;
                self.assertIn(14, r1["unreached_lines_in_window"]) # int ovf = INT_MAX + delta;
                self.assertEqual(r1["first_blocker_line"], 8)
                self.assertIn("/* @VISITED (hits=1, @BRANCH_PARTIAL taken=1/2) */", r1["annotated_slice"])
                self.assertIn("/* @UNREACHED <-- FIRST_UNREACHED_AFTER_GUARD */", r1["annotated_slice"])

                # Verify zero `*.gcda` or `*.gcno` files remain inside `slot-0` after release.
                self.assertEqual(list(slot0.rglob("*.gcda")), [])
                self.assertEqual(list(slot0.rglob("*.gcno")), [])

                # Run 2: triggering input (`tag=4919`) hits ASan heap-buffer-overflow AND flushes `.gcda`.
                rc2, r2 = _run_cli_json(
                    [
                        "repro",
                        "slice-probe",
                        "--run",
                        rid,
                        "--focus-locus",
                        "sub/frame.c:4-20",
                        "--build-cmd",
                        "gcc $AJAR_COV_CFLAGS $AJAR_SAN_CFLAGS sub/frame.c -o prog",
                        "--cmd",
                        "./prog 4919",
                        "--sanitize",
                        "--json",
                    ]
                )
                self.assertEqual(rc2, 0)
                self.assertTrue(r2["ok"])
                self.assertTrue(r2["coverage_collected"])
                self.assertTrue(r2["sanitizer_triggered"])
                self.assertIn("AddressSanitizer", r2["sanitizer_summary"]["kind"])
                self.assertEqual(r2["sanitizer_summary"]["crash_locus"], "sub/frame.c:9")
                self.assertNotIn("slot-", r2["sanitizer_summary"]["crash_locus"])
                self.assertIn(8, r2["visited_lines_in_window"])
                self.assertIn(9, r2["visited_lines_in_window"])
                self.assertIn(10, r2["unreached_lines_in_window"])  # post-crash line never reached
                self.assertIn("@SANITIZER_TRIGGERED", r2["annotated_slice"])

                # Run 3: triggering input (`tag=7777`) hits UBSan signed integer overflow.
                rc3, r3 = _run_cli_json(
                    [
                        "repro",
                        "slice-probe",
                        "--run",
                        rid,
                        "--focus-locus",
                        "sub/frame.c:4-20",
                        "--build-cmd",
                        "gcc $AJAR_COV_CFLAGS $AJAR_SAN_CFLAGS sub/frame.c -o prog",
                        "--cmd",
                        "./prog 7777 1",
                        "--sanitizer-flags",
                        "--json",
                    ]
                )
                self.assertEqual(rc3, 0)
                self.assertTrue(r3["coverage_collected"])
                self.assertTrue(r3["sanitizer_triggered"])
                self.assertEqual(r3["sanitizer_summary"]["kind"], "UndefinedBehaviorSanitizer")
                self.assertEqual(r3["sanitizer_summary"]["crash_locus"], "sub/frame.c:14")
                self.assertIn(14, r3["visited_lines_in_window"])

                self.assertEqual(list(slot0.rglob("*.gcda")), [])
                self.assertEqual(list(slot0.rglob("*.gcno")), [])
                _assert_clean_git_repo(self, target)

    def test_cli_mcp_parity_needs_instrumentation_unblock_and_path_guards(self) -> None:
        target_py = (
            "def verify_header(version: int, flags: int) -> bool:\n"
            "    if version != 2:\n"
            "        return False\n"
            "    if flags & 0x80:\n"
            "        raise ValueError('corrupt header flag')\n"
            "    return True\n"
        )
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            ajar_home = base / "ajar_home"
            target = _init_git_repo(base / "parity_target", {"hdr.py": target_py})

            with mock.patch.dict(os.environ, {"AJAR_HOME": str(ajar_home)}):
                tool_names = {t["name"] for t in MCP_TOOLS}
                self.assertIn("ajar_repro_slice_probe", tool_names)

                _, init_cli = _run_cli_json(["init", "--in-place", "--json", str(target)])
                _, init_mcp = _run_cli_json(["init", "--in-place", "--json", str(target)])
                rid_cli = str(init_cli["run_id"])
                rid_mcp = str(init_mcp["run_id"])

                claim_spec = {
                    "title": "Header flag bit 0x80 raises uncaught parser error",
                    "locus": "hdr.py:4",
                    "mechanism": "Unchecked flags integer reaches verify_header bitmask branch and raises ValueError",
                    "falsification_prediction": "Calling verify_header(2, 0x80) raises ValueError",
                    "falsification_test": "python3 -c 'import hdr; hdr.verify_header(2, 128)'",
                    "severity": "high",
                }

                # Create and survive claims on both runs, then drive both into 2-strike `needs_instrumentation`.
                clm_ids: dict[str, str] = {}
                for rid in (rid_cli, rid_mcp):
                    rc_p, cp = _run_cli_json(
                        [
                            "claim",
                            "propose",
                            "--run",
                            rid,
                            "--worker",
                            "w-prop",
                            "--title",
                            claim_spec["title"],
                            "--locus",
                            claim_spec["locus"],
                            "--mechanism",
                            claim_spec["mechanism"],
                            "--falsification-prediction",
                            claim_spec["falsification_prediction"],
                            "--falsification-test",
                            claim_spec["falsification_test"],
                            "--severity",
                            claim_spec["severity"],
                        ]
                    )
                    self.assertEqual(rc_p, 0)
                    cid = str(cp["claim_id"])
                    clm_ids[rid] = cid
                    rc_s, _ = _run_cli_json(
                        [
                            "claim",
                            "survive",
                            "--run",
                            rid,
                            "--worker",
                            "w-fals",
                            cid,
                            "--notes",
                            "Confirmed no upstream caller masks bit 0x80",
                        ]
                    )
                    self.assertEqual(rc_s, 0)

                    conn = open_run_db(rid, ajar_home=ajar_home)
                    try:
                        for _ in range(2):
                            clm_row = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (cid,)).fetchone()
                            piv = record_repro_failure(
                                conn,
                                claim=clm_row,
                                worker_id="w-repro",
                                observation_hash="same_obs_hash_01",
                                reason="Arm 1 exited 0 (wrong version=1)",
                            )
                        self.assertEqual(piv["status"], "needs_instrumentation")
                        inst_tasks = conn.execute(
                            "SELECT COUNT(*) AS c FROM tasks WHERE kind = 'instrument' AND status = 'open' AND parent_claim_id = ?",
                            (cid,),
                        ).fetchone()["c"]
                        self.assertEqual(int(inst_tasks), 1)
                    finally:
                        conn.close()

                # Unblock `rid_cli` via CLI `ajar repro slice-probe --claim` and `rid_mcp` via JSON-RPC MCP `tools/call`.
                probe_cmd = "python3 -c 'import hdr; hdr.verify_header(1, 128)'"
                rc_sp_cli, sp_cli = _run_cli_json(
                    [
                        "repro",
                        "slice-probe",
                        "--run",
                        rid_cli,
                        "--claim",
                        clm_ids[rid_cli],
                        "--worker",
                        "w-repro",
                        "--focus-locus",
                        "hdr.py:1-6",
                        "--cmd",
                        probe_cmd,
                        "--json",
                    ]
                )
                self.assertEqual(rc_sp_cli, 0)

                rpc_resp = handle_jsonrpc_message(
                    {
                        "jsonrpc": "2.0",
                        "id": 7,
                        "method": "tools/call",
                        "params": {
                            "name": "ajar_repro_slice_probe",
                            "arguments": {
                                "claim_id": clm_ids[rid_mcp],
                                "worker_id": "w-repro",
                                "focus_locus": "hdr.py:1-6",
                                "cmd": probe_cmd,
                            },
                        },
                    },
                    run_id=rid_mcp,
                    ajar_home=ajar_home,
                )
                assert rpc_resp is not None
                self.assertFalse(rpc_resp["result"]["isError"])
                sp_mcp = json.loads(rpc_resp["result"]["content"][0]["text"])

                # Exact structural parity across CLI and MCP.
                for key in (
                    "ok",
                    "tracer_used",
                    "coverage_collected",
                    "window",
                    "visited_lines_in_window",
                    "unreached_lines_in_window",
                    "first_blocker_line",
                    "annotated_slice",
                    "claim_unblocked",
                    "claim_status",
                ):
                    self.assertEqual(sp_cli[key], sp_mcp[key], f"Mismatch on {key!r}")

                self.assertTrue(sp_cli["claim_unblocked"])
                self.assertEqual(sp_cli["claim_status"], "survived_falsify")
                self.assertEqual(sp_cli["visited_lines_in_window"], [1, 2, 3])
                self.assertEqual(sp_cli["unreached_lines_in_window"], [4, 5, 6])
                self.assertEqual(sp_cli["first_blocker_line"], 4)

                # Verify DB state on both runs: claim back to `survived_falsify`, `instrument` task `done`, `slice_probed` event logged.
                for rid, cid in clm_ids.items():
                    conn = open_run_db(rid, ajar_home=ajar_home)
                    try:
                        crow = conn.execute(
                            "SELECT status, instrumented_since_fail FROM claims WHERE claim_id = ?",
                            (cid,),
                        ).fetchone()
                        self.assertEqual(crow["status"], "survived_falsify")
                        self.assertEqual(int(crow["instrumented_since_fail"]), 1)
                        open_inst = conn.execute(
                            "SELECT COUNT(*) AS c FROM tasks WHERE kind = 'instrument' AND status != 'done' AND parent_claim_id = ?",
                            (cid,),
                        ).fetchone()["c"]
                        self.assertEqual(int(open_inst), 0)
                        ev_cnt = conn.execute(
                            "SELECT COUNT(*) AS c FROM events WHERE action = 'slice_probed' AND entity_id = ?",
                            (cid,),
                        ).fetchone()["c"]
                        self.assertEqual(int(ev_cnt), 1)
                    finally:
                        conn.close()

                # Path-traversal rejection parity (`../` and absolute paths).
                for bad_locus in ("../outside.py:1-5", "/etc/passwd:1-5", "hdr.py:99-105"):
                    rc_bad, _ = _run_cli_json(
                        [
                            "repro",
                            "slice-probe",
                            "--run",
                            rid_cli,
                            "--focus-locus",
                            bad_locus,
                            "--cmd",
                            "true",
                            "--json",
                        ]
                    )
                    self.assertNotEqual(rc_bad, 0, f"Expected CLI rejection for {bad_locus!r}")
                    with self.assertRaises(AjarError):
                        dispatch_mcp_tool(
                            rid_mcp,
                            "ajar_repro_slice_probe",
                            {"focus_locus": bad_locus, "cmd": "true"},
                            ajar_home=ajar_home,
                        )

                _assert_clean_git_repo(self, target)

    @unittest.skipUnless(shutil.which("gcc") and shutil.which("gcov"), "gcc and gcov required")
    def test_patch_overlay_multi_tu_c_build_and_stale_gcda_preclean(self) -> None:
        lib_c = (
            "int evaluate_gate(int token) {\n"
            "    if (token == 42) {\n"
            "        return 100;\n"
            "    }\n"
            "    return 1;\n"
            "}\n"
        )
        main_c = (
            "#include <stdlib.h>\n"
            "int evaluate_gate(int token);\n"
            "int main(int argc, char **argv) {\n"
            "    int t = argc > 1 ? atoi(argv[1]) : 0;\n"
            "    return evaluate_gate(t) == 100 ? 0 : 2;\n"
            "}\n"
        )
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            ajar_home = base / "ajar_home"
            target = _init_git_repo(base / "multi_tu_target", {"src/gate.c": lib_c, "src/main.c": main_c})

            patch_file = base / "relax_gate.diff"
            patch_file.write_text(
                "--- a/src/gate.c\n"
                "+++ b/src/gate.c\n"
                "@@ -1,6 +1,6 @@\n"
                " int evaluate_gate(int token) {\n"
                "-    if (token == 42) {\n"
                "+    if (token >= 0) {\n"
                "         return 100;\n"
                "     }\n"
                "     return 1;\n"
                " }\n",
                encoding="utf-8",
            )

            with mock.patch.dict(os.environ, {"AJAR_HOME": str(ajar_home)}):
                _, init_data = _run_cli_json(["init", "--in-place", "--json", str(target)])
                rid = str(init_data["run_id"])
                slot0 = ajar_home / "runs" / rid / "repro" / "slot-0"

                build_multi = (
                    "mkdir -p CMakeFiles/app.dir && "
                    "gcc $AJAR_COV_CFLAGS -c src/gate.c -o CMakeFiles/app.dir/gate.c.o && "
                    "gcc $AJAR_COV_CFLAGS -c src/main.c -o CMakeFiles/app.dir/main.c.o && "
                    "gcc $AJAR_COV_LDFLAGS CMakeFiles/app.dir/gate.c.o CMakeFiles/app.dir/main.c.o -o app"
                )

                # Plant a stale `.gcda` inside `CMakeFiles/` (preserved across `git clean`) to prove pre-clean hygiene.
                (slot0 / "CMakeFiles" / "app.dir").mkdir(parents=True, exist_ok=True)
                (slot0 / "CMakeFiles" / "app.dir" / "stale.gcda").write_bytes(b"stale")

                # Without patch (`token=0`), line 3 (`return 100;`) is `@UNREACHED`.
                rc_clean, res_clean = _run_cli_json(
                    [
                        "repro",
                        "slice-probe",
                        "--run",
                        rid,
                        "--focus-locus",
                        "src/gate.c",
                        "--build-cmd",
                        build_multi,
                        "--cmd",
                        "./app 0",
                        "--json",
                    ]
                )
                self.assertEqual(rc_clean, 0)
                self.assertTrue(res_clean["coverage_collected"])
                self.assertIn(3, res_clean["unreached_lines_in_window"])
                self.assertIn(5, res_clean["visited_lines_in_window"])
                self.assertEqual(list(slot0.rglob("*.gcda")), [])
                self.assertEqual(list(slot0.rglob("*.gcno")), [])

                # With `--patch` (`if (token >= 0)`), line 3 (`return 100;`) becomes `@VISITED` while `target` stays untouched.
                rc_patched, res_patched = _run_cli_json(
                    [
                        "repro",
                        "slice-probe",
                        "--run",
                        rid,
                        "--focus-locus",
                        "src/gate.c:1-6",
                        "--patch",
                        str(patch_file),
                        "--build-cmd",
                        build_multi,
                        "--cmd",
                        "./app 0",
                        "--json",
                    ]
                )
                self.assertEqual(rc_patched, 0)
                self.assertTrue(res_patched["coverage_collected"])
                self.assertIn(3, res_patched["visited_lines_in_window"])
                self.assertIn(5, res_patched["unreached_lines_in_window"])
                self.assertEqual(target.joinpath("src/gate.c").read_text(encoding="utf-8"), lib_c)
                _assert_clean_git_repo(self, target)


if __name__ == "__main__":
    unittest.main()

