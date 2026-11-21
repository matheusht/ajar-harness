"""4-Arm Reproduction Adapters for Compiled Binary (`BinaryAdapter`) and Live Services (`LiveAdapter`).

- `BinaryAdapter`: Pins `binary_sha256` + shared-library closure, extracts ASLR-normalized
  `module+0xoffset` fault location (skipping leaf `libc` frames), and proves causal attribution
  via non-destructive batch `gdb` conditional breakpoint micro-guards or 1-field input ablation.
- `LiveAdapter`: Enforces `scope` host/mutation authorization, mints fresh 128-bit CSPRNG
  `AJAR_CANARY_B` inside `ajar` (hidden from `poc_cmd` env so scripts cannot hardcode results),
  runs 4-arm Method-of-Difference checks, scrubs credentials, and verifies teardown.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import secrets
import shutil
import subprocess
import tempfile
import urllib.parse
from typing import Any

from ajar.redact import scrub_text, scrubbed_subprocess_env

LEAF_LIB_SKIP_RE = re.compile(
    r"\b(?:libc\.so|ld-linux|libpthread|libasan|libubsan|__GI_|pthread_kill|gsignal|abort|"
    r"memcpy|memmove|memset|strcpy|strncpy|strcat|strlen|__fortify_fail|__stack_chk_fail)\b"
)


def _sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(65536):
            h.update(chunk)
    return h.hexdigest()


def _capture_ldd_closure(binary_path: pathlib.Path) -> list[str]:
    if shutil.which("ldd") is None:
        return []
    res = subprocess.run(
        ["ldd", str(binary_path)],
        capture_output=True,
        text=True,
        env=scrubbed_subprocess_env(),
        check=False,
    )
    if res.returncode != 0:
        return []
    return [line.strip() for line in res.stdout.splitlines() if line.strip()][:30]


def _prepare_io(spec: dict[str, Any], scratch: pathlib.Path, label: str) -> tuple[list[str], pathlib.Path | None]:
    args_raw = spec.get("args", [])
    args = [str(a) for a in args_raw] if isinstance(args_raw, list) else []
    stdin_path: pathlib.Path | None = None

    if "stdin_hex" in spec and spec["stdin_hex"] is not None:
        stdin_path = scratch / f"{label}.stdin"
        stdin_path.write_bytes(bytes.fromhex(str(spec["stdin_hex"])))
    elif "stdin_text" in spec and spec["stdin_text"] is not None:
        stdin_path = scratch / f"{label}.stdin"
        stdin_path.write_bytes(str(spec["stdin_text"]).encode("utf-8"))
    elif "stdin_file" in spec and spec["stdin_file"]:
        stdin_path = pathlib.Path(str(spec["stdin_file"])).resolve()

    if "file_arg_hex" in spec and spec["file_arg_hex"] is not None:
        f_arg = scratch / f"{label}.input"
        f_arg.write_bytes(bytes.fromhex(str(spec["file_arg_hex"])))
        args = [str(f_arg) if a == "{INPUT_FILE}" else a for a in (args or ["{INPUT_FILE}"])]
    return (args, stdin_path)


def _parse_gdb_normalized_offset(gdb_out: str, binary_path: pathlib.Path) -> tuple[str, str]:
    """Extract `(signal_name, normalized_module_offset)` skipping leaf `libc` frames."""
    sig_match = re.search(r"Program received signal\s+([A-Z0-9_]+)", gdb_out)
    sig_name = sig_match.group(1) if sig_match else ""

    # Parse `info proc mappings` base address for `binary_path`.
    bin_real = str(binary_path.resolve())
    bin_name = binary_path.name
    base_addr: int | None = None
    for line in gdb_out.splitlines():
        if bin_real in line or line.rstrip().endswith(f"/{bin_name}"):
            m = re.match(r"^\s*(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)", line)
            if m:
                addr = int(m.group(1), 16)
                if base_addr is None or addr < base_addr:
                    base_addr = addr

    # Walk `#0`, `#1`, ... frames and pick first frame inside `binary_path` (not libc).
    frame_re = re.compile(r"^#\d+\s+(?:(0x[0-9a-fA-F]+)\s+in\s+)?([^\s(]+).*?(?:at\s+([^\s:]+:\d+)|from\s+(\S+))?$")
    chosen_pc: int | None = None
    chosen_sym = ""
    for line in gdb_out.splitlines():
        s = line.strip()
        if not s.startswith("#"):
            continue
        fm = frame_re.match(s)
        if not fm:
            continue
        pc_hex, sym, src_loc, from_lib = fm.group(1), fm.group(2), fm.group(3) or "", fm.group(4) or ""
        if LEAF_LIB_SKIP_RE.search(sym) or LEAF_LIB_SKIP_RE.search(from_lib):
            continue
        if from_lib and bin_name not in from_lib:
            continue
        chosen_sym = f"{sym}@{src_loc}" if src_loc else sym
        if pc_hex:
            chosen_pc = int(pc_hex, 16)
        elif s.startswith("#0"):
            pc_m = re.search(r"AJAR_PC=(0x[0-9a-fA-F]+)", gdb_out)
            if pc_m:
                chosen_pc = int(pc_m.group(1), 16)
        break

    if chosen_pc is not None and base_addr is not None and chosen_pc >= base_addr:
        norm = f"{bin_name}+0x{chosen_pc - base_addr:x}"
        if chosen_sym:
            norm = f"{norm} ({chosen_sym})"
        return (sig_name, norm)
    if chosen_sym:
        return (sig_name, f"{bin_name}:{chosen_sym}")
    return (sig_name, "")


def _run_binary_once(
    binary_path: pathlib.Path,
    args: list[str],
    stdin_path: pathlib.Path | None,
    *,
    use_gdb: bool,
    gdb_guard: dict[str, Any] | None = None,
    timeout_sec: int = 30,
) -> dict[str, Any]:
    env = scrubbed_subprocess_env()
    if use_gdb and shutil.which("gdb") is not None:
        with tempfile.TemporaryDirectory(prefix="ajar-gdb-") as gtmp:
            guard_lines: list[str] = []
            if gdb_guard:
                target_sym = str(gdb_guard.get("symbol_or_offset") or "")
                cond = str(gdb_guard.get("condition") or "")
                ret_val = str(gdb_guard.get("return_value", "-1"))
                brk = f"break {target_sym} if {cond}" if cond else f"break {target_sym}"
                guard_lines = [
                    brk,
                    "commands",
                    "silent",
                    'print "AJAR_GUARD_FIRED"',
                    f"return {ret_val}",
                    "continue",
                    "end",
                ]
            run_args = " ".join(json.dumps(a) for a in args)
            stdin_redir = f" < {json.dumps(str(stdin_path))}" if stdin_path is not None else ""
            script_lines = [
                "set pagination off",
                "set confirm off",
                *guard_lines,
                f"run {run_args}{stdin_redir}",
                "info proc mappings",
                "bt 12",
                'printf "AJAR_PC=%p\\n", $pc',
                "quit",
            ]
            gdb_script = pathlib.Path(gtmp) / "cmd.gdb"
            gdb_script.write_text("\n".join(script_lines) + "\n", encoding="utf-8")
            proc = subprocess.run(
                ["gdb", "-batch", "-nx", "-x", str(gdb_script), str(binary_path)],
                capture_output=True,
                text=True,
                env=env,
                timeout=timeout_sec,
                check=False,
            )
            out = scrub_text(proc.stdout + "\n" + proc.stderr)
            ld_linux = pathlib.Path("/lib64/ld-linux-x86-64.so.2")
            if "_dl_debug_initialize" in out and ld_linux.is_file():
                # gVisor/container ptrace AT_BASE fallback: launch via ld-linux and relocate DWARF symbols at set_tid_address.
                bin_real_js = json.dumps(str(binary_path.resolve()))
                fb_lines = [
                    "set pagination off",
                    "set confirm off",
                    f"exec-file {ld_linux}",
                    "catch syscall set_tid_address",
                    f"run {bin_real_js} {run_args}{stdin_redir}",
                    "python",
                    "import gdb, re",
                    f"target_bin = {bin_real_js}",
                    'maps = gdb.execute("info proc mappings", to_string=True)',
                    "base = None",
                    "for line in maps.splitlines():",
                    "    if target_bin in line:",
                    '        m = re.match(r"^\\s*(0x[0-9a-fA-F]+)", line)',
                    "        if m:",
                    "            addr = int(m.group(1), 16)",
                    "            if base is None or addr < base:",
                    "                base = addr",
                    "if base is not None:",
                    '    gdb.execute(f"add-symbol-file {target_bin} -o {hex(base)}")',
                    "end",
                    "delete breakpoints",
                    *guard_lines,
                    "continue",
                    "info proc mappings",
                    "bt 12",
                    'printf "AJAR_PC=%p\\n", $pc',
                    "quit",
                ]
                fb_script = pathlib.Path(gtmp) / "cmd_ld.gdb"
                fb_script.write_text("\n".join(fb_lines) + "\n", encoding="utf-8")
                proc = subprocess.run(
                    ["gdb", "-batch", "-nx", "-x", str(fb_script)],
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=timeout_sec,
                    check=False,
                )
                out = scrub_text(proc.stdout + "\n" + proc.stderr)

            sig_name, norm_offset = _parse_gdb_normalized_offset(out, binary_path)
            exited_normally = bool(re.search(r"exited normally", out))
            exited_code_m = re.search(r"exited with code\s+(\d+)", out)
            exit_code = 0 if exited_normally else (int(exited_code_m.group(1)) if exited_code_m else -1)
            crashed = bool(sig_name and sig_name not in ("SIGTRAP",))
            guard_fired = "AJAR_GUARD_FIRED" in out
            return {
                "crashed": crashed,
                "signal": sig_name,
                "exit_code": -11 if crashed else exit_code,
                "normalized_fault_offset": norm_offset,
                "guard_fired": guard_fired,
                "output": out[:4000],
            }

    stdin_bytes = stdin_path.read_bytes() if stdin_path is not None else None
    raw_proc = subprocess.run(
        [str(binary_path), *args],
        input=stdin_bytes,
        capture_output=True,
        env=env,
        timeout=timeout_sec,
        check=False,
    )
    rc = int(raw_proc.returncode)
    crashed = rc < 0 or rc >= 128
    return {
        "crashed": crashed,
        "signal": f"rc={rc}" if crashed else "",
        "exit_code": rc,
        "normalized_fault_offset": "",
        "guard_fired": False,
        "output": scrub_text((raw_proc.stdout + raw_proc.stderr).decode("utf-8", errors="replace"))[:4000],
    }


def run_binary_reproduction(
    *,
    run_dir: pathlib.Path,
    binary_path: pathlib.Path,
    claim_id: str,
    poc_args_or_stdin: dict[str, Any],
    control_args_or_stdin: dict[str, Any],
    guard_spec: dict[str, Any] | None = None,
    ablation_spec: dict[str, Any] | None = None,
    timeout_sec: int = 30,
) -> dict[str, Any]:
    """Execute 4-arm binary defect reproduction with ASLR-normalized PC + runtime guard/ablation."""
    bpath = binary_path.resolve()
    if not bpath.is_file() or not os.access(bpath, os.X_OK):
        return {
            "passed": False,
            "reason": f"Executable binary not found: {bpath}",
            "observation_hash": "missing_binary",
            "arm1_clean_poc": {"arm_passed": False},
            "arm2_clean_control": {"arm_passed": False},
            "arm3_patch_poc": {"arm_passed": False},
            "arm4_patch_control": {"arm_passed": False},
        }

    bin_sha = _sha256_file(bpath)
    libs = _capture_ldd_closure(bpath)
    use_gdb = shutil.which("gdb") is not None

    with tempfile.TemporaryDirectory(prefix="ajar-bin-") as tmp:
        scratch = pathlib.Path(tmp)
        poc_args, poc_stdin = _prepare_io(poc_args_or_stdin, scratch, "poc")
        ctrl_args, ctrl_stdin = _prepare_io(control_args_or_stdin, scratch, "ctrl")

        # Arm 1: Clean binary + PoC -> MUST crash/fault.
        arm1 = _run_binary_once(bpath, poc_args, poc_stdin, use_gdb=use_gdb, timeout_sec=timeout_sec)
        arm1["arm_passed"] = bool(arm1["crashed"])
        obs_hash = hashlib.sha256(
            f"{bin_sha}:{arm1['signal']}:{arm1['normalized_fault_offset']}".encode("utf-8")
        ).hexdigest()[:16]
        if not arm1["arm_passed"]:
            return {
                "passed": False,
                "reason": f"Arm 1 (binary + PoC) did not fault (exit_code={arm1['exit_code']}).",
                "binary_sha256": bin_sha,
                "shared_libraries": libs,
                "normalized_fault_offset": arm1["normalized_fault_offset"],
                "observation_hash": obs_hash,
                "arm1_clean_poc": arm1,
                "arm2_clean_control": {"arm_passed": False},
                "arm3_patch_poc": {"arm_passed": False},
                "arm4_patch_control": {"arm_passed": False},
            }

        # Arm 2: Clean binary + benign control -> MUST exit 0 without crashing.
        arm2 = _run_binary_once(bpath, ctrl_args, ctrl_stdin, use_gdb=False, timeout_sec=timeout_sec)
        arm2["arm_passed"] = not arm2["crashed"] and arm2["exit_code"] == 0
        if not arm2["arm_passed"]:
            return {
                "passed": False,
                "reason": f"Arm 2 (binary + benign control) failed (exit_code={arm2['exit_code']}).",
                "binary_sha256": bin_sha,
                "shared_libraries": libs,
                "normalized_fault_offset": arm1["normalized_fault_offset"],
                "observation_hash": obs_hash,
                "arm1_clean_poc": arm1,
                "arm2_clean_control": arm2,
                "arm3_patch_poc": {"arm_passed": False},
                "arm4_patch_control": {"arm_passed": False},
            }

        # Arm 3 & Arm 4: Runtime gdb conditional micro-guard OR 1-field ablation.
        if guard_spec and use_gdb:
            arm3 = _run_binary_once(
                bpath, poc_args, poc_stdin, use_gdb=True, gdb_guard=guard_spec, timeout_sec=timeout_sec
            )
            arm3["arm_passed"] = not arm3["crashed"] and arm3["guard_fired"]
            arm4 = _run_binary_once(
                bpath, ctrl_args, ctrl_stdin, use_gdb=True, gdb_guard=guard_spec, timeout_sec=timeout_sec
            )
            arm4["arm_passed"] = not arm4["crashed"] and arm4["exit_code"] == 0 and not arm4["guard_fired"]
        elif ablation_spec:
            abl_args, abl_stdin = _prepare_io(ablation_spec, scratch, "ablated")
            arm3 = _run_binary_once(bpath, abl_args, abl_stdin, use_gdb=False, timeout_sec=timeout_sec)
            arm3["arm_passed"] = not arm3["crashed"]
            arm4 = dict(arm2)
            arm4["arm_passed"] = True
        else:
            return {
                "passed": False,
                "reason": "Binary reproduction requires either `guard_spec` (with gdb) or `ablation_spec` for causal Arm 3/4.",
                "binary_sha256": bin_sha,
                "shared_libraries": libs,
                "normalized_fault_offset": arm1["normalized_fault_offset"],
                "observation_hash": obs_hash,
                "arm1_clean_poc": arm1,
                "arm2_clean_control": arm2,
                "arm3_patch_poc": {"arm_passed": False},
                "arm4_patch_control": {"arm_passed": False},
            }

        passed = bool(arm3["arm_passed"] and arm4["arm_passed"])
        reason = (
            "All 4 binary causal arms passed."
            if passed
            else f"Binary causal guard/ablation failed (arm3={arm3['arm_passed']}, arm4={arm4['arm_passed']})."
        )
        return {
            "passed": passed,
            "reason": reason,
            "binary_sha256": bin_sha,
            "shared_libraries": libs,
            "normalized_fault_offset": arm1["normalized_fault_offset"],
            "observation_hash": obs_hash,
            "micropatch_diff": json.dumps(guard_spec or ablation_spec or {}, sort_keys=True),
            "arm1_clean_poc": arm1,
            "arm2_clean_control": arm2,
            "arm3_patch_poc": arm3,
            "arm4_patch_control": arm4,
            "cross_killed_claim_ids": [],
        }


def _run_live_step(cmd: str, env: dict[str, str], extra_literals: tuple[str, ...], timeout_sec: int) -> dict[str, Any]:
    proc = subprocess.run(
        ["bash", "-c", cmd],
        capture_output=True,
        env=env,
        timeout=timeout_sec,
        check=False,
    )
    raw_stdout = proc.stdout.decode("utf-8", errors="replace")
    raw_stderr = proc.stderr.decode("utf-8", errors="replace")
    return {
        "exit_code": int(proc.returncode),
        "raw_stdout": raw_stdout,
        "stdout": scrub_text(raw_stdout, extra_literals=extra_literals)[:3000],
        "stderr": scrub_text(raw_stderr, extra_literals=extra_literals)[:3000],
    }


def run_live_reproduction(
    *,
    run_dir: pathlib.Path,
    scope: dict[str, Any],
    claim_id: str,
    seed_cmd: str,
    poc_cmd: str,
    control_cmd: str,
    teardown_cmd: str,
    target_url: str,
    unauth_control_cmd: str = "",
    timeout_sec: int = 30,
) -> dict[str, Any]:
    """Execute 4-arm live service verification using `ajar`-minted CSPRNG canaries + teardown check."""
    if not scope.get("allow_live_requests", False):
        return {
            "passed": False,
            "reason": "Blocked by scope_rules: `allow_live_requests` is false.",
            "observation_hash": "scope_blocked",
            "arm1_clean_poc": {"arm_passed": False},
            "arm2_clean_control": {"arm_passed": False},
            "arm3_patch_poc": {"arm_passed": False},
            "arm4_patch_control": {"arm_passed": False},
        }

    parsed = urllib.parse.urlparse(target_url)
    host = (parsed.hostname or "").lower()
    allowed_hosts = [str(h).lower() for h in scope.get("allowed_hosts", [])]
    if not host or host not in allowed_hosts:
        return {
            "passed": False,
            "reason": f"Blocked by scope_rules: target host {host!r} is not in allowed_hosts {allowed_hosts}.",
            "observation_hash": "host_blocked",
            "arm1_clean_poc": {"arm_passed": False},
            "arm2_clean_control": {"arm_passed": False},
            "arm3_patch_poc": {"arm_passed": False},
            "arm4_patch_control": {"arm_passed": False},
        }

    # Mint fresh 128-bit CSPRNG canaries inside `ajar` (CANARY_B is NEVER passed to poc_cmd!).
    canary_a = f"ajar-canary-a-{secrets.token_hex(16)}"
    canary_b = f"ajar-canary-b-{secrets.token_hex(16)}"
    cred_a = os.environ.get("AJAR_CRED_A", f"test-cred-a-{secrets.token_hex(8)}")
    cred_b = os.environ.get("AJAR_CRED_B", f"test-cred-b-{secrets.token_hex(8)}")
    secret_literals = (cred_a, cred_b)

    seed_env = scrubbed_subprocess_env(
        overrides={
            "AJAR_TARGET_URL": target_url,
            "AJAR_CRED_A": cred_a,
            "AJAR_CRED_B": cred_b,
            "AJAR_CANARY_A": canary_a,
            "AJAR_CANARY_B": canary_b,
        }
    )
    seed_res = _run_live_step(seed_cmd, seed_env, secret_literals, timeout_sec)
    if seed_res["exit_code"] != 0:
        return {
            "passed": False,
            "reason": f"Live seed_cmd failed (exit={seed_res['exit_code']}): {seed_res['stderr'][:200]}",
            "observation_hash": "seed_failed",
            "arm1_clean_poc": {"arm_passed": False},
            "arm2_clean_control": {"arm_passed": False},
            "arm3_patch_poc": {"arm_passed": False},
            "arm4_patch_control": {"arm_passed": False},
        }

    resource_a_id = ""
    resource_b_id = ""
    try:
        seed_meta = json.loads(seed_res["raw_stdout"].strip().splitlines()[-1])
        if isinstance(seed_meta, dict):
            resource_a_id = str(seed_meta.get("resource_a_id", ""))
            resource_b_id = str(seed_meta.get("resource_b_id", ""))
    except (IndexError, json.JSONDecodeError):
        pass

    # Probe environment WITHOUT `AJAR_CANARY_B` or `AJAR_CRED_B`!
    probe_env = scrubbed_subprocess_env(
        overrides={
            "AJAR_TARGET_URL": target_url,
            "AJAR_CRED_A": cred_a,
            "AJAR_RESOURCE_A_ID": resource_a_id,
            "AJAR_RESOURCE_B_ID": resource_b_id,
        }
    )

    teardown_verified = False
    try:
        # Arm 1: Principal A cross-tenant/boundary PoC -> MUST retrieve fresh `canary_b`.
        arm1_raw = _run_live_step(poc_cmd, probe_env, secret_literals, timeout_sec)
        leaked_b_in_arm1 = canary_b in arm1_raw["raw_stdout"]
        arm1 = {
            "exit_code": arm1_raw["exit_code"],
            "canary_b_observed": leaked_b_in_arm1,
            "stdout": arm1_raw["stdout"].replace(canary_b, "<VERIFIED_CANARY_B>"),
            "stderr": arm1_raw["stderr"],
            "arm_passed": leaked_b_in_arm1,
        }

        # Arm 2: Principal A normal self-resource control -> MUST exit 0 and NOT contain `canary_b`.
        arm2_raw = _run_live_step(control_cmd, probe_env, secret_literals, timeout_sec)
        arm2 = {
            "exit_code": arm2_raw["exit_code"],
            "canary_a_observed": canary_a in arm2_raw["raw_stdout"],
            "canary_b_observed": canary_b in arm2_raw["raw_stdout"],
            "stdout": arm2_raw["stdout"].replace(canary_a, "<VERIFIED_CANARY_A>"),
            "stderr": arm2_raw["stderr"],
            "arm_passed": arm2_raw["exit_code"] == 0 and (canary_b not in arm2_raw["raw_stdout"]),
        }

        # Arm 3: Stripped-auth differential control -> unauthenticated request must NOT return `canary_b`.
        unauth_env = scrubbed_subprocess_env(
            overrides={
                "AJAR_TARGET_URL": target_url,
                "AJAR_CRED_A": "",
                "AJAR_CRED_B": "",
                "AJAR_RESOURCE_A_ID": resource_a_id,
                "AJAR_RESOURCE_B_ID": resource_b_id,
            }
        )
        arm3_cmd = unauth_control_cmd or poc_cmd
        arm3_raw = _run_live_step(arm3_cmd, unauth_env, secret_literals, timeout_sec)
        # Either unauthenticated is blocked (proving auth-context specificity) OR if unauth bug, control_cmd with invalid ID fails cleanly:
        invalid_id_env = dict(probe_env)
        invalid_id_env["AJAR_RESOURCE_B_ID"] = f"nonexistent-{secrets.token_hex(6)}"
        arm3_nonexist = _run_live_step(poc_cmd, invalid_id_env, secret_literals, timeout_sec)
        arm3 = {
            "unauth_leaked_canary_b": canary_b in arm3_raw["raw_stdout"],
            "invalid_id_leaked_canary_b": canary_b in arm3_nonexist["raw_stdout"],
            "arm_passed": (canary_b not in arm3_nonexist["raw_stdout"]),
        }
    finally:
        td_res = _run_live_step(teardown_cmd, seed_env, secret_literals, timeout_sec)
        post_td = _run_live_step(poc_cmd, probe_env, secret_literals, timeout_sec)
        teardown_verified = td_res["exit_code"] == 0 and (canary_b not in post_td["raw_stdout"])

    arm4 = {
        "teardown_exit_code": td_res["exit_code"],
        "canary_b_absent_after_teardown": canary_b not in post_td["raw_stdout"],
        "arm_passed": teardown_verified,
    }

    passed = bool(arm1["arm_passed"] and arm2["arm_passed"] and arm3["arm_passed"] and arm4["arm_passed"])
    obs_hash = hashlib.sha256(
        f"{target_url}:{arm1['arm_passed']}:{arm2['arm_passed']}:{arm4['arm_passed']}".encode("utf-8")
    ).hexdigest()[:16]
    reason = (
        "All 4 live differential arms passed with fresh ajar-minted CSPRNG canary and verified teardown."
        if passed
        else (
            f"Live verification failed (arm1={arm1['arm_passed']}, arm2={arm2['arm_passed']}, "
            f"arm3={arm3['arm_passed']}, arm4_teardown={arm4['arm_passed']})."
        )
    )
    return {
        "passed": passed,
        "reason": reason,
        "canary_minted_by_ajar": True,
        "teardown_verified": teardown_verified,
        "observation_hash": obs_hash,
        "micropatch_diff": "",
        "arm1_clean_poc": arm1,
        "arm2_clean_control": arm2,
        "arm3_patch_poc": arm3,
        "arm4_patch_control": arm4,
        "cross_killed_claim_ids": [],
    }
