from __future__ import annotations

import json
import pathlib
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

from ajar.repro_binary_live import run_binary_reproduction, run_live_reproduction
from ajar.repro_source import init_source_mirror, run_source_reproduction, validate_micropatch_diff

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
POLYGLOT = REPO_ROOT / "benchmarks" / "polyglot"


class TestReproAdapters(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = pathlib.Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_micropatch_diff_preflight_guard(self) -> None:
        bad_test_diff = (
            "--- a/tests/test_auth.py\n"
            "+++ b/tests/test_auth.py\n"
            "@@ -1,2 +1,2 @@\n"
            "-assert False\n"
            "+assert True\n"
        )
        ok, msg, _ = validate_micropatch_diff(bad_test_diff)
        self.assertFalse(ok)
        self.assertIn("forbidden", msg.lower())

        bad_asan_diff = (
            "--- a/src/parser.c\n"
            "+++ b/src/parser.c\n"
            "@@ -1,2 +1,2 @@\n"
            "-int x = 1;\n"
            "+const char *opt = \"ASAN_OPTIONS=detect_leaks=0\";\n"
        )
        ok2, msg2, _ = validate_micropatch_diff(bad_asan_diff)
        self.assertFalse(ok2)
        self.assertIn("suppression", msg2.lower())

    def test_source_adapter_c_parser_valid_destructive_and_wrong_locus(self) -> None:
        c_dir = POLYGLOT / "c_parser"
        rdir = self.tmp_path / "run-c"
        rdir.mkdir()
        init_source_mirror(rdir, c_dir)

        poc_cmd = "make -s clean all && ./parser --hex 421441414141414141414141414141414141deadbeef"
        ctrl_cmd = "make -s clean all && ./parser --selftest"

        # 1. Valid 1-line fix passes all 4 arms!
        res_ok = run_source_reproduction(
            run_dir=rdir,
            target_dir=c_dir,
            claim_id="clm-c-ok",
            poc_cmd=poc_cmd,
            control_cmd=ctrl_cmd,
            micropatch_path=c_dir / "patches" / "valid_fix.patch",
        )
        self.assertTrue(res_ok["passed"], res_ok)
        self.assertTrue(res_ok["arm1_clean_poc"]["arm_passed"])
        self.assertTrue(res_ok["arm2_clean_control"]["arm_passed"])
        self.assertTrue(res_ok["arm3_patch_poc"]["arm_passed"])
        self.assertTrue(res_ok["arm4_patch_control"]["arm_passed"])

        # 2. Destructive patch stops PoC (Arm 3) but FAILS benign control (Arm 4)!
        res_destr = run_source_reproduction(
            run_dir=rdir,
            target_dir=c_dir,
            claim_id="clm-c-destr",
            poc_cmd=poc_cmd,
            control_cmd=ctrl_cmd,
            micropatch_path=c_dir / "patches" / "bad_destructive.patch",
        )
        self.assertFalse(res_destr["passed"])
        self.assertTrue(res_destr["arm3_patch_poc"]["arm_passed"])
        self.assertFalse(res_destr["arm4_patch_control"]["arm_passed"])

        # 3. Wrong-locus patch FAILS Arm 3 (PoC still crashes)!
        res_wrong = run_source_reproduction(
            run_dir=rdir,
            target_dir=c_dir,
            claim_id="clm-c-wrong",
            poc_cmd=poc_cmd,
            control_cmd=ctrl_cmd,
            micropatch_path=c_dir / "patches" / "wrong_locus.patch",
        )
        self.assertFalse(res_wrong["passed"])
        self.assertFalse(res_wrong["arm3_patch_poc"]["arm_passed"])

        # 4. Warm cross-kill deduplication detects duplicate sibling claim!
        res_xkill = run_source_reproduction(
            run_dir=rdir,
            target_dir=c_dir,
            claim_id="clm-c-primary",
            poc_cmd=poc_cmd,
            control_cmd=ctrl_cmd,
            micropatch_path=c_dir / "patches" / "valid_fix.patch",
            warm_cross_kill_claims=[{"claim_id": "clm-c-dup-sibling", "poc_cmd": poc_cmd}],
        )
        self.assertTrue(res_xkill["passed"])
        self.assertIn("clm-c-dup-sibling", res_xkill["cross_killed_claim_ids"])

    def test_source_adapter_go_ledger_and_rust_vault(self) -> None:
        # Go ledger
        go_dir = POLYGLOT / "go_ledger"
        rdir_go = self.tmp_path / "run-go"
        rdir_go.mkdir()
        init_source_mirror(rdir_go, go_dir)

        res_go = run_source_reproduction(
            run_dir=rdir_go,
            target_dir=go_dir,
            claim_id="clm-go-ok",
            poc_cmd="RUN_POC=1 go test -count=1 -run TestPoCSelfTransferConservation ./...",
            control_cmd="go test -count=1 -run TestBenignTransfers ./...",
            micropatch_path=go_dir / "patches" / "valid_fix.patch",
        )
        self.assertTrue(res_go["passed"], res_go)

        res_go_bad = run_source_reproduction(
            run_dir=rdir_go,
            target_dir=go_dir,
            claim_id="clm-go-bad",
            poc_cmd="RUN_POC=1 go test -count=1 -run TestPoCSelfTransferConservation ./...",
            control_cmd="go test -count=1 -run TestBenignTransfers ./...",
            micropatch_path=go_dir / "patches" / "bad_destructive.patch",
        )
        self.assertFalse(res_go_bad["passed"])
        self.assertFalse(res_go_bad["arm4_patch_control"]["arm_passed"])

        # Rust share vault (`CARGO_TARGET_DIR` incremental reuse + mtime watermark)
        rs_dir = POLYGLOT / "rust_vault"
        rdir_rs = self.tmp_path / "run-rs"
        rdir_rs.mkdir()
        init_source_mirror(rdir_rs, rs_dir)

        res_rs = run_source_reproduction(
            run_dir=rdir_rs,
            target_dir=rs_dir,
            claim_id="clm-rs-ok",
            poc_cmd="RUN_POC=1 cargo test --quiet test_poc_rounding_drain",
            control_cmd="cargo test --quiet test_benign_roundtrip",
            micropatch_path=rs_dir / "patches" / "valid_fix.patch",
            timeout_sec=90,
        )
        self.assertTrue(res_rs["passed"], res_rs)

        res_rs_wrong = run_source_reproduction(
            run_dir=rdir_rs,
            target_dir=rs_dir,
            claim_id="clm-rs-wrong",
            poc_cmd="RUN_POC=1 cargo test --quiet test_poc_rounding_drain",
            control_cmd="cargo test --quiet test_benign_roundtrip",
            micropatch_path=rs_dir / "patches" / "wrong_locus.patch",
            timeout_sec=90,
        )
        self.assertFalse(res_rs_wrong["passed"])
        self.assertFalse(res_rs_wrong["arm3_patch_poc"]["arm_passed"])

    def test_source_adapter_neutralizes_python_pth_escape(self) -> None:
        py_src = self.tmp_path / "py_pth_target"
        py_src.mkdir()
        pwn_marker = self.tmp_path / "pth_executed_marker"
        # Malicious .pth file inside repository executes arbitrary code if site module loads cwd/.pth!
        (py_src / "evil.pth").write_text(
            f"import pathlib; pathlib.Path({str(pwn_marker)!r}).write_text('pwned')\n",
            encoding="utf-8",
        )
        (py_src / "calc.py").write_text(
            "def divide_fee(x: int) -> int:\n    return x // 0 if x == 42 else x // 2\n",
            encoding="utf-8",
        )
        patch_file = self.tmp_path / "fix.patch"
        patch_file.write_text(
            "--- a/calc.py\n"
            "+++ b/calc.py\n"
            "@@ -1,2 +1,2 @@\n"
            " def divide_fee(x: int) -> int:\n"
            "-    return x // 0 if x == 42 else x // 2\n"
            "+    return 21 if x == 42 else x // 2\n",
            encoding="utf-8",
        )
        rdir = self.tmp_path / "run-pth"
        rdir.mkdir()
        init_source_mirror(rdir, py_src)
        res = run_source_reproduction(
            run_dir=rdir,
            target_dir=py_src,
            claim_id="clm-pth",
            poc_cmd="python3 -S -c 'import calc; assert calc.divide_fee(42) == 21'",
            control_cmd="python3 -S -c 'import calc; assert calc.divide_fee(10) == 5'",
            micropatch_path=patch_file,
        )
        self.assertTrue(res["passed"], res)
        self.assertFalse(pwn_marker.exists(), ".pth payload must be stripped and never executed")

    def test_binary_adapter_aslr_normalized_fault_and_gdb_micro_guard(self) -> None:
        bin_dir = self.tmp_path / "bin_build"
        bin_dir.mkdir()
        elf_path = bin_dir / "parser_elf"
        subprocess.run(
            [
                "gcc",
                "-g",
                "-O0",
                "-fno-omit-frame-pointer",
                "-fno-stack-protector",
                "-o",
                str(elf_path),
                str(POLYGLOT / "c_parser" / "parser.c"),
            ],
            check=True,
        )

        rdir = self.tmp_path / "run-bin"
        rdir.mkdir()
        res = run_binary_reproduction(
            run_dir=rdir,
            binary_path=elf_path,
            claim_id="clm-bin-1",
            poc_args_or_stdin={"args": ["--hex", "421441414141414141414141414141414141deadbeef"]},
            control_args_or_stdin={"args": ["--selftest"]},
            guard_spec={
                "symbol_or_offset": "parser.c:39",
                "condition": "decl_len > 16",
                "return_value": "-3",
            },
        )
        self.assertTrue(res["passed"], res)
        self.assertIn("parser_elf+0x", res["normalized_fault_offset"])
        self.assertNotIn("libc", res["normalized_fault_offset"])
        self.assertEqual(len(res["binary_sha256"]), 64)

    def test_live_adapter_csprng_canary_scope_guard_and_teardown(self) -> None:
        # Allocate ephemeral port on 127.0.0.1 and launch py_live_service
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()

        srv = subprocess.Popen(
            [sys.executable, str(POLYGLOT / "py_live_service" / "app.py"), "--serve", str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            url = f"http://127.0.0.1:{port}"
            for _ in range(30):
                try:
                    with urllib.request.urlopen(f"{url}/health", timeout=0.5) as resp:
                        if resp.status == 200:
                            break
                except Exception:
                    time.sleep(0.05)

            rdir = self.tmp_path / "run-live"
            rdir.mkdir()

            # 1. Out-of-scope host MUST be rejected immediately.
            blocked = run_live_reproduction(
                run_dir=rdir,
                scope={"allow_live_requests": True, "allowed_hosts": ["127.0.0.1"]},
                claim_id="clm-live-blocked",
                seed_cmd="true",
                poc_cmd="true",
                control_cmd="true",
                teardown_cmd="true",
                target_url="https://evil.example.com",
            )
            self.assertFalse(blocked["passed"])
            self.assertEqual(blocked["observation_hash"], "host_blocked")

            # 2. Authorized localhost 4-arm CSPRNG canary IDOR verification + teardown!
            seed_cmd = (
                "python3 -c 'import json, os, urllib.request; "
                "u=os.environ[\"AJAR_TARGET_URL\"]; "
                "req1=urllib.request.Request(u+\"/seed\", json.dumps({\"tenant\":\"tenant_a\",\"note_id\":\"n_a\",\"body\":os.environ[\"AJAR_CANARY_A\"]}).encode(), {\"Content-Type\":\"application/json\"}); "
                "urllib.request.urlopen(req1).read(); "
                "req2=urllib.request.Request(u+\"/seed\", json.dumps({\"tenant\":\"tenant_b\",\"note_id\":\"n_b\",\"body\":os.environ[\"AJAR_CANARY_B\"]}).encode(), {\"Content-Type\":\"application/json\"}); "
                "urllib.request.urlopen(req2).read(); "
                "print(json.dumps({\"resource_a_id\":\"n_a\",\"resource_b_id\":\"n_b\"}))'"
            )
            # Notice poc_cmd does NOT know AJAR_CANARY_B — it queries tenant_b's note as requester=tenant_a!
            poc_cmd = (
                "python3 -c 'import os, urllib.request; "
                "assert \"AJAR_CANARY_B\" not in os.environ; "
                "u=os.environ[\"AJAR_TARGET_URL\"]; rid=os.environ[\"AJAR_RESOURCE_B_ID\"]; "
                "print(urllib.request.urlopen(f\"{u}/notes/tenant_b/{rid}?requester=tenant_a\").read().decode())'"
            )
            ctrl_cmd = (
                "python3 -c 'import os, urllib.request; "
                "u=os.environ[\"AJAR_TARGET_URL\"]; rid=os.environ[\"AJAR_RESOURCE_A_ID\"]; "
                "print(urllib.request.urlopen(f\"{u}/notes/tenant_a/{rid}?requester=tenant_a\").read().decode())'"
            )
            teardown_cmd = (
                "python3 -c 'import json, os, urllib.request; "
                "u=os.environ[\"AJAR_TARGET_URL\"]; "
                "req=urllib.request.Request(u+\"/teardown\", json.dumps({\"tenant\":\"tenant_b\",\"note_id\":\"n_b\"}).encode(), {\"Content-Type\":\"application/json\"}); "
                "urllib.request.urlopen(req).read()'"
            )

            live_res = run_live_reproduction(
                run_dir=rdir,
                scope={"allow_live_requests": True, "allow_live_mutations": True, "allowed_hosts": ["127.0.0.1"]},
                claim_id="clm-live-idor",
                seed_cmd=seed_cmd,
                poc_cmd=poc_cmd,
                control_cmd=ctrl_cmd,
                teardown_cmd=teardown_cmd,
                target_url=url,
            )
            self.assertTrue(live_res["passed"], json.dumps(live_res, indent=2))
            self.assertTrue(live_res["canary_minted_by_ajar"])
            self.assertTrue(live_res["teardown_verified"])
        finally:
            srv.terminate()
            srv.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
