"""4-Arm Counterfactual Micro-Patch Source Reproduction Engine (`SourceAdapter`).

Proves causal root-cause attribution on source targets while keeping `workspace/target/`
100% read-only:
- Builds a bare git mirror (`repro/repo.git`) once per run
- Leases a fixed-path worktree (`repro/slot-<k>`) + incremental build cache (`repro/cache-<k>`)
- Validates micro-patches pre-flight (no test/build/sanitizer tampering, bounded diff size)
- Runs 4 sequential causal arms in the same worktree path (`clean+PoC`, `clean+control`,
  `micropatch+PoC`, `micropatch+control`), bumping `mtime` monotonically (`+2s`) on apply
  and reset so incremental compilers (`cargo`, `make`, `go`, `pyc`) never serve stale artifacts
- Supports `probabilistic_race` multi-trial verification and warm cross-kill deduplication
"""

from __future__ import annotations

import fcntl
import hashlib
import os
import pathlib
import re
import secrets
import shutil
import signal
import socket
import subprocess
import tempfile
import time
from typing import Any, Mapping

from ajar.redact import scrub_text, scrubbed_subprocess_env

_UNSHARE_AVAILABLE: bool | None = None

FORBIDDEN_PATCH_PATH_RE = re.compile(
    r"(^|/)(?:tests?|specs?|benches|__tests__|testdata)/"
    r"|(^|/)test_[^/]+\.[A-Za-z0-9]+$"
    r"|_test\.[A-Za-z0-9]+$"
    r"|\.spec\.[A-Za-z0-9]+$"
    r"|(^|/)(?:Cargo\.toml|Cargo\.lock|Makefile|CMakeLists\.txt|build\.gradle|pom\.xml|"
    r"package\.json|pyproject\.toml|setup\.py|setup\.cfg|go\.mod|go\.sum|foundry\.toml)$",
    re.IGNORECASE,
)

FORBIDDEN_PATCH_ADDED_LINE_RE = re.compile(
    r"\b(?:ASAN_OPTIONS|UBSAN_OPTIONS|pytest\.skip|unittest\.skip|t\.Skip|t\.SkipNow)\b"
    r"|#\[\s*(?:allow|ignore)\b",
    re.IGNORECASE,
)


def unshare_netns_available() -> bool:
    global _UNSHARE_AVAILABLE
    if _UNSHARE_AVAILABLE is None:
        try:
            proc = subprocess.run(
                ["unshare", "-rn", "true"],
                capture_output=True,
                timeout=3,
                check=False,
            )
            _UNSHARE_AVAILABLE = proc.returncode == 0
        except (FileNotFoundError, OSError, subprocess.SubprocessError):
            _UNSHARE_AVAILABLE = False
    return _UNSHARE_AVAILABLE


def _allocate_ephemeral_ports(count: int = 4) -> list[int]:
    socks: list[socket.socket] = []
    ports: list[int] = []
    try:
        for _ in range(count):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("127.0.0.1", 0))
            ports.append(int(s.getsockname()[1]))
            socks.append(s)
    finally:
        for s in socks:
            s.close()
    return ports


def _reap_by_arm_token(arm_token: str) -> None:
    """Reap any orphaned background child processes carrying `AJAR_ARM_TOKEN`."""
    proc_root = pathlib.Path("/proc")
    if not proc_root.is_dir():
        return
    needle = f"AJAR_ARM_TOKEN={arm_token}".encode("utf-8")
    my_pid = os.getpid()
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid == my_pid:
            continue
        try:
            env_bytes = (entry / "environ").read_bytes()
            if needle in env_bytes:
                os.kill(pid, signal.SIGKILL)
        except (OSError, PermissionError):
            continue


def _copy_writable_tree(src: pathlib.Path, dst: pathlib.Path) -> None:
    shutil.copytree(
        src,
        dst,
        symlinks=False,
        ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", "target", "node_modules", ".ajar"),
    )
    for root, dirs, files in os.walk(dst):
        os.chmod(root, 0o755)
        for d in dirs:
            os.chmod(os.path.join(root, d), 0o755)
        for f in files:
            p = os.path.join(root, f)
            st = os.stat(p)
            os.chmod(p, st.st_mode | 0o600)


def init_source_mirror(run_dir: pathlib.Path, target_dir: pathlib.Path) -> pathlib.Path:
    """Create `run_dir / 'repro' / 'repo.git'` bare mirror without modifying `target_dir`."""
    repro_dir = run_dir / "repro"
    repro_dir.mkdir(parents=True, exist_ok=True)
    mirror_dir = repro_dir / "repo.git"
    if (mirror_dir / "HEAD").is_file():
        return mirror_dir

    src = target_dir.resolve()
    env = scrubbed_subprocess_env()

    # Check if `src` is a clean git repo with at least one commit and zero dirty/untracked files.
    can_fast_clone = False
    if (src / ".git").exists():
        head_chk = subprocess.run(
            ["git", "-C", str(src), "rev-parse", "--verify", "HEAD"],
            capture_output=True,
            env=env,
            check=False,
        )
        status_chk = subprocess.run(
            ["git", "-C", str(src), "status", "--porcelain"],
            capture_output=True,
            env=env,
            check=False,
        )
        if head_chk.returncode == 0 and status_chk.returncode == 0 and not status_chk.stdout.strip():
            can_fast_clone = True

    if can_fast_clone:
        res = subprocess.run(
            ["git", "clone", "--bare", "--shared", str(src), str(mirror_dir)],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        if res.returncode == 0:
            return mirror_dir
        shutil.rmtree(mirror_dir, ignore_errors=True)

    # Snapshot arbitrary directory or dirty working tree via temporary staging repo.
    with tempfile.TemporaryDirectory(prefix="ajar-stage-") as tmp:
        stage_dir = pathlib.Path(tmp) / "src"
        if src.is_file():
            stage_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, stage_dir / src.name)
            os.chmod(stage_dir / src.name, 0o644)
        else:
            _copy_writable_tree(src, stage_dir)

        for cmd in (
            ["git", "init", "-q"],
            ["git", "config", "user.email", "ajar@local.invalid"],
            ["git", "config", "user.name", "ajar-snapshot"],
            ["git", "add", "-A"],
            ["git", "commit", "-q", "--allow-empty", "-m", "ajar baseline snapshot"],
        ):
            subprocess.run(cmd, cwd=str(stage_dir), capture_output=True, env=env, check=True)

        subprocess.run(
            ["git", "clone", "--bare", "--no-hardlinks", str(stage_dir), str(mirror_dir)],
            capture_output=True,
            text=True,
            env=env,
            check=True,
        )
    return mirror_dir


HUNK_HEADER_RE = re.compile(r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@")


def _parse_locus_spec(locus: str) -> tuple[str, int | None, int | None]:
    raw_file, _, span = locus.strip().partition(":")
    clean_file = raw_file.strip().lstrip("./")
    if not span:
        return (clean_file, None, None)
    m = re.match(r"^(\d+)(?:-(\d+))?", span.strip())
    if not m:
        return (clean_file, None, None)
    start_l = int(m.group(1))
    end_l = int(m.group(2)) if m.group(2) else start_l
    return (clean_file, min(start_l, end_l), max(start_l, end_l))


def _file_matches_locus(touched_file: str, loc_file: str) -> bool:
    t = touched_file.strip().lstrip("./")
    lf = loc_file.strip().lstrip("./")
    if not lf:
        return True
    return t == lf or t.endswith("/" + lf) or lf.endswith("/" + t)


def validate_micropatch_diff(
    diff_text: str,
    *,
    max_changed_lines: int = 16,
    claim_locus: str = "",
    shared_guard_locus: str = "",
) -> tuple[bool, str, list[str]]:
    """Verify micro-patch touches only production source files, stays minimal, and matches claim.locus."""
    if not diff_text or not diff_text.strip():
        return (False, "Micro-patch diff is empty.", [])

    touched_files: list[str] = []
    hunks_by_file: dict[str, list[tuple[int, int]]] = {}
    current_file = ""
    changed_code_lines = 0
    saw_hunk = False

    for line in diff_text.splitlines():
        if line.startswith("+++ ") or line.startswith("--- "):
            raw_path = line[4:].strip()
            if raw_path == "/dev/null":
                continue
            clean_path = re.sub(r"^[ab]/", "", raw_path.split("\t", 1)[0]).strip()
            if ".." in pathlib.PurePosixPath(clean_path).parts or clean_path.startswith("/"):
                return (False, f"Micro-patch path escapes repository root: {clean_path}", [])
            if FORBIDDEN_PATCH_PATH_RE.search(clean_path):
                return (
                    False,
                    f"Micro-patch is forbidden from modifying test or build manifest file: {clean_path}",
                    [],
                )
            if line.startswith("+++ ") or not current_file:
                current_file = clean_path
            if clean_path not in touched_files:
                touched_files.append(clean_path)
        elif line.startswith("@@"):
            saw_hunk = True
            hm = HUNK_HEADER_RE.match(line)
            if hm and current_file:
                old_start = int(hm.group(1))
                old_cnt = int(hm.group(2)) if hm.group(2) is not None else 1
                hunks_by_file.setdefault(current_file, []).append((old_start, old_start + max(1, old_cnt)))
        elif saw_hunk and (line.startswith("+") or line.startswith("-")) and not line.startswith(("+++", "---")):
            body = line[1:].strip()
            if line.startswith("+") and FORBIDDEN_PATCH_ADDED_LINE_RE.search(body):
                return (False, f"Micro-patch contains forbidden assertion/sanitizer suppression: {body[:80]}", [])
            if body and not body.startswith(("//", "#", "/*", "*")):
                changed_code_lines += 1

    if not saw_hunk or not touched_files:
        return (False, "Micro-patch is not a valid unified diff with file hunks.", [])
    if changed_code_lines == 0:
        return (False, "Micro-patch makes zero non-comment code changes.", [])
    if changed_code_lines > max_changed_lines:
        return (
            False,
            f"Micro-patch changes {changed_code_lines} non-comment lines (max {max_changed_lines} for root-cause proof).",
            touched_files,
        )

    if claim_locus.strip():
        allowed_specs = [_parse_locus_spec(claim_locus)]
        if shared_guard_locus.strip():
            allowed_specs.append(_parse_locus_spec(shared_guard_locus))

        locus_matched = False
        for loc_file, loc_start, loc_end in allowed_specs:
            for tf in touched_files:
                if not _file_matches_locus(tf, loc_file):
                    continue
                if loc_start is None or loc_end is None:
                    locus_matched = True
                    break
                for h_start, h_end in hunks_by_file.get(tf, [(1, 1000000)]):
                    if (h_start - 60) <= loc_end and loc_start <= (h_end + 60):
                        locus_matched = True
                        break
                if locus_matched:
                    break
            if locus_matched:
                break

        if not locus_matched:
            return (
                False,
                f"claim_mismatch: micro-patch modifies {touched_files} outside claimed locus {claim_locus!r}. "
                "Re-scope the claim via `ajar claim rescope` or pass `--shared-guard-locus` if fixing an upstream guard.",
                touched_files,
            )

    return (True, "ok", touched_files)


def _neutralize_python_pth_escapes(slot_dir: pathlib.Path) -> int:
    """Remove or scrub `.pth` files and external symlinks inside `slot_dir`."""
    removed = 0
    slot_real = slot_dir.resolve()
    for root, dirs, files in os.walk(slot_dir, followlinks=False):
        for name in [*dirs, *files]:
            p = pathlib.Path(root) / name
            if p.is_symlink():
                target = p.resolve()
                try:
                    target.relative_to(slot_real)
                except ValueError:
                    p.unlink(missing_ok=True)
                    removed += 1
            elif p.suffix == ".pth" and p.is_file():
                p.unlink(missing_ok=True)
                removed += 1
    return removed


def _bump_files_mtime(slot_dir: pathlib.Path, rel_paths: list[str], watermark_file: pathlib.Path) -> int:
    prev_ns = 0
    if watermark_file.is_file():
        try:
            prev_ns = int(watermark_file.read_text(encoding="utf-8").strip())
        except ValueError:
            prev_ns = 0
    next_ns = max(time.time_ns(), prev_ns) + 2_000_000_000
    for rel in rel_paths:
        fp = slot_dir / rel
        if fp.is_file() and not fp.is_symlink():
            os.utime(fp, ns=(next_ns, next_ns))
    watermark_file.write_text(str(next_ns), encoding="utf-8")
    return next_ns


def _evaluate_defect_fired(
    exit_code: int,
    stdout: str,
    stderr: str,
    timed_out: bool,
    oracle: dict[str, Any] | None,
) -> bool:
    """Determine whether the defect signature triggered on this execution."""
    spec = oracle or {}
    combined = f"{stdout}\n{stderr}"

    if timed_out:
        return bool(spec.get("timeout_counts_as_defect", False))

    expect_regex = spec.get("expect_regex")
    if expect_regex:
        if not re.search(str(expect_regex), combined, re.MULTILINE):
            return False
        if spec.get("allow_zero_exit_on_regex", False):
            return True

    expect_exit = spec.get("expect_exit_code")
    if expect_exit is not None:
        return exit_code == int(expect_exit)

    return exit_code != 0


def _run_shell_in_slot(
    cmd: str,
    *,
    slot_dir: pathlib.Path,
    cache_dir: pathlib.Path,
    timeout_sec: int,
    helpers_dir: pathlib.Path | None = None,
    extra_env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    from ajar.repro_compose import ensure_helpers_runtime

    eff_helpers = helpers_dir or ensure_helpers_runtime(slot_dir.parent.parent)
    ports = _allocate_ephemeral_ports(4)
    arm_token = secrets.token_hex(12)
    tmp_dir = cache_dir / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    has_netns = unshare_netns_available()

    overrides: dict[str, str] = {
        "AJAR_ARM_TOKEN": arm_token,
        "AJAR_PORT_0": str(ports[0]),
        "AJAR_PORT_1": str(ports[1]),
        "AJAR_PORT_2": str(ports[2]),
        "AJAR_PORT_3": str(ports[3]),
        "AJAR_HELPERS_DIR": str(eff_helpers),
        "CARGO_TARGET_DIR": str(cache_dir / "cargo-target"),
        "GOCACHE": str(cache_dir / "go-cache"),
        "PYTHONPYCACHEPREFIX": str(cache_dir / "pycache"),
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": f"{slot_dir}{os.pathsep}{eff_helpers}",
        "GOFLAGS": "-count=1",
    }
    if not has_netns:
        overrides.update(
            {
                "AJAR_BLOCK_EXTERNAL_NET": "1",
                "NO_PROXY": "*",
                "no_proxy": "*",
                "HTTP_PROXY": "",
                "HTTPS_PROXY": "",
                "http_proxy": "",
                "https_proxy": "",
            }
        )
    if extra_env:
        for k, v in extra_env.items():
            overrides[str(k)] = str(v)

    env = scrubbed_subprocess_env(overrides=overrides, tmp_dir=tmp_dir)
    env["PATH"] = f"{eff_helpers / 'bin'}{os.pathsep}{env.get('PATH', '/usr/bin:/bin')}"
    argv = ["unshare", "-rn", "bash", "-c", cmd] if has_netns else ["bash", "-c", cmd]

    t0 = time.monotonic()
    timed_out = False
    proc = subprocess.Popen(
        argv,
        cwd=str(slot_dir),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        out_b, err_b = proc.communicate(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            proc.kill()
        out_b, err_b = proc.communicate()
    finally:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        _reap_by_arm_token(arm_token)

    elapsed_ms = round((time.monotonic() - t0) * 1000.0, 1)
    stdout = scrub_text(out_b[:65536].decode("utf-8", errors="replace"))
    stderr = scrub_text(err_b[:65536].decode("utf-8", errors="replace"))
    rc = int(proc.returncode if proc.returncode is not None else -9)
    return {
        "exit_code": rc,
        "timed_out": timed_out,
        "duration_ms": elapsed_ms,
        "stdout": stdout[:4000],
        "stderr": stderr[:4000],
    }


def _run_trials(
    cmd: str,
    *,
    slot_dir: pathlib.Path,
    cache_dir: pathlib.Path,
    timeout_sec: int,
    oracle: dict[str, Any] | None,
    trials: int,
    helpers_dir: pathlib.Path | None = None,
) -> dict[str, Any]:
    defect_hits = 0
    clean_passes = 0
    last_res: dict[str, Any] = {}
    total_ms = 0.0
    for _ in range(trials):
        res = _run_shell_in_slot(
            cmd,
            slot_dir=slot_dir,
            cache_dir=cache_dir,
            timeout_sec=timeout_sec,
            helpers_dir=helpers_dir,
        )
        total_ms += float(res["duration_ms"])
        fired = _evaluate_defect_fired(res["exit_code"], res["stdout"], res["stderr"], res["timed_out"], oracle)
        if fired:
            defect_hits += 1
        elif res["exit_code"] == 0 and not res["timed_out"]:
            clean_passes += 1
        last_res = res
    return {
        **last_res,
        "trials": trials,
        "defect_hits": defect_hits,
        "clean_passes": clean_passes,
        "total_duration_ms": round(total_ms, 1),
    }


DEBUG_ABORT_SIGNAL_RE = re.compile(
    r"(?:runtime error:|UndefinedBehaviorSanitizer|AddressSanitizer|panicked at|"
    r"assertion failed|attempt to (?:add|subtract|multiply|shift) with overflow|SIGABRT|SIGILL)",
    re.IGNORECASE,
)


def classify_release_ub_divergence(
    arm1_debug: dict[str, Any],
    arm5a_release_poc: dict[str, Any],
    arm5b_release_ctrl: dict[str, Any],
    *,
    min_hits: int = 1,
    n_trials: int = 1,
) -> str:
    """Classify compiler-profile UB divergence between Arm 1 (debug/sanitizer) and Arm 5A/5B (`-O2` / `--release`)."""
    if arm5b_release_ctrl["defect_hits"] > 0 or arm5b_release_ctrl["clean_passes"] < n_trials:
        return "release_control_failed"

    rel_fired = int(arm5a_release_poc["defect_hits"]) >= min_hits
    rel_rc = int(arm5a_release_poc["exit_code"])
    dbg_rc = int(arm1_debug["exit_code"])
    dbg_out = f"{arm1_debug.get('stdout', '')}\n{arm1_debug.get('stderr', '')}"
    rel_out = f"{arm5a_release_poc.get('stdout', '')}\n{arm5a_release_poc.get('stderr', '')}"

    if not rel_fired and rel_rc == 0 and not arm5a_release_poc.get("timed_out"):
        return "debug_assert_only"

    if not rel_fired and (rel_rc < 0 or rel_rc >= 128):
        return "trap_dos_only"

    dbg_trapped = bool(DEBUG_ABORT_SIGNAL_RE.search(dbg_out)) or dbg_rc < 0 or dbg_rc >= 128
    rel_trapped = bool(DEBUG_ABORT_SIGNAL_RE.search(rel_out)) or rel_rc < 0 or rel_rc >= 128

    if rel_fired and dbg_trapped and not rel_trapped:
        return "silent_wrap_escalated"
    if rel_trapped and not re.search(r"(?:corrupt|bypass|unauthorized|invariant|overflow_wrap)", rel_out, re.IGNORECASE):
        return "trap_dos_only"
    return "consistent"


def _acquire_slot(repro_dir: pathlib.Path, max_slots: int = 8) -> tuple[int, Any]:
    repro_dir.mkdir(parents=True, exist_ok=True)
    for idx in range(max_slots):
        lock_path = repro_dir / f"slot-{idx}.lock"
        fh = open(lock_path, "a+", encoding="utf-8")
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return (idx, fh)
        except BlockingIOError:
            fh.close()
    # All slots busy: wait on slot-0.
    fh0 = open(repro_dir / "slot-0.lock", "a+", encoding="utf-8")
    fcntl.flock(fh0.fileno(), fcntl.LOCK_EX)
    return (0, fh0)


def _prepare_slot_worktree(mirror_dir: pathlib.Path, slot_dir: pathlib.Path) -> None:
    env = scrubbed_subprocess_env()
    if not (slot_dir / ".git").exists():
        shutil.rmtree(slot_dir, ignore_errors=True)
        subprocess.run(
            ["git", "clone", "--shared", str(mirror_dir), str(slot_dir)],
            capture_output=True,
            text=True,
            env=env,
            check=True,
        )
    else:
        subprocess.run(["git", "-C", str(slot_dir), "reset", "--hard", "HEAD"], capture_output=True, env=env, check=True)
        subprocess.run(["git", "-C", str(slot_dir), "clean", "-fdx"], capture_output=True, env=env, check=True)
    _neutralize_python_pth_escapes(slot_dir)


def run_source_reproduction(
    *,
    run_dir: pathlib.Path,
    target_dir: pathlib.Path,
    claim_id: str,
    poc_cmd: str,
    control_cmd: str,
    micropatch_path: pathlib.Path,
    oracle: dict[str, Any] | None = None,
    determinism: str = "deterministic",
    trials: int = 8,
    timeout_sec: int = 60,
    warm_cross_kill_claims: list[dict[str, str]] | None = None,
    claim_locus: str = "",
    shared_guard_locus: str = "",
    max_changed_lines: int = 16,
    release_cmd: str = "",
    release_control_cmd: str = "",
) -> dict[str, Any]:
    """Execute 4-arm counterfactual source reproduction (+ optional Arm 5A/5B Release UB Differential)."""
    if not micropatch_path.is_file():
        return {
            "passed": False,
            "reason": f"Micro-patch file not found: {micropatch_path}",
            "observation_hash": hashlib.sha256(b"missing_patch").hexdigest()[:16],
            "micropatch_diff": "",
            "arm1_clean_poc": {"arm_passed": False},
            "arm2_clean_control": {"arm_passed": False},
            "arm3_patch_poc": {"arm_passed": False},
            "arm4_patch_control": {"arm_passed": False},
            "arm5a_release_poc": {},
            "arm5b_release_control": {},
            "ub_divergence_class": "",
            "cross_killed_claim_ids": [],
        }

    diff_text = micropatch_path.read_text(encoding="utf-8", errors="replace")
    valid_diff, diff_msg, touched_files = validate_micropatch_diff(
        diff_text,
        max_changed_lines=max_changed_lines,
        claim_locus=claim_locus,
        shared_guard_locus=shared_guard_locus,
    )
    if not valid_diff:
        return {
            "passed": False,
            "reason": f"Pre-flight micro-patch validation failed: {diff_msg}",
            "claim_mismatch": diff_msg.startswith("claim_mismatch:"),
            "observation_hash": hashlib.sha256(diff_msg.encode("utf-8")).hexdigest()[:16],
            "micropatch_diff": scrub_text(diff_text[:4000]),
            "arm1_clean_poc": {"arm_passed": False},
            "arm2_clean_control": {"arm_passed": False},
            "arm3_patch_poc": {"arm_passed": False},
            "arm4_patch_control": {"arm_passed": False},
            "arm5a_release_poc": {},
            "arm5b_release_control": {},
            "ub_divergence_class": "",
            "cross_killed_claim_ids": [],
        }

    from ajar.repro_compose import ensure_helpers_runtime

    helpers_dir = ensure_helpers_runtime(run_dir)
    mirror_dir = init_source_mirror(run_dir, target_dir)
    repro_dir = run_dir / "repro"
    slot_idx, lock_fh = _acquire_slot(repro_dir)
    slot_dir = repro_dir / f"slot-{slot_idx}"
    cache_dir = repro_dir / f"cache-{slot_idx}"
    cache_dir.mkdir(parents=True, exist_ok=True)
    watermark_file = cache_dir / "watermark_ns"

    n_trials = max(4, int(trials)) if determinism == "probabilistic_race" else 1
    min_race_hits = max(3, n_trials // 2) if determinism == "probabilistic_race" else 1

    try:
        _prepare_slot_worktree(mirror_dir, slot_dir)

        # Arm 1: Clean baseline + PoC -> MUST fire defect.
        arm1 = _run_trials(
            poc_cmd,
            slot_dir=slot_dir,
            cache_dir=cache_dir,
            timeout_sec=timeout_sec,
            oracle=oracle,
            trials=n_trials,
            helpers_dir=helpers_dir,
        )
        arm1["arm_passed"] = arm1["defect_hits"] >= min_race_hits
        obs_seed = f"a1:{arm1['exit_code']}:{arm1['stdout'][:240]}:{arm1['stderr'][:240]}"

        if not arm1["arm_passed"]:
            return {
                "passed": False,
                "reason": f"Arm 1 (clean + PoC) did not trigger defect ({arm1['defect_hits']}/{n_trials} hits, exit={arm1['exit_code']}).",
                "observation_hash": hashlib.sha256(obs_seed.encode("utf-8")).hexdigest()[:16],
                "micropatch_diff": scrub_text(diff_text[:4000]),
                "arm1_clean_poc": arm1,
                "arm2_clean_control": {"arm_passed": False},
                "arm3_patch_poc": {"arm_passed": False},
                "arm4_patch_control": {"arm_passed": False},
                "arm5a_release_poc": {},
                "arm5b_release_control": {},
                "ub_divergence_class": "",
                "cross_killed_claim_ids": [],
            }

        # Reset working tree between Arm 1 and Arm 2 in case PoC wrote scratch files.
        subprocess.run(["git", "-C", str(slot_dir), "reset", "--hard", "HEAD"], capture_output=True, check=True)
        subprocess.run(["git", "-C", str(slot_dir), "clean", "-fdx"], capture_output=True, check=True)

        # Arm 2: Clean baseline + benign control -> MUST pass cleanly with 0 defect hits.
        arm2 = _run_trials(
            control_cmd,
            slot_dir=slot_dir,
            cache_dir=cache_dir,
            timeout_sec=timeout_sec,
            oracle=oracle,
            trials=n_trials,
            helpers_dir=helpers_dir,
        )
        arm2["arm_passed"] = arm2["defect_hits"] == 0 and arm2["clean_passes"] == n_trials
        if not arm2["arm_passed"]:
            return {
                "passed": False,
                "reason": f"Arm 2 (clean + benign control) failed or triggered defect (exit={arm2['exit_code']}).",
                "observation_hash": hashlib.sha256((obs_seed + f"|a2:{arm2['exit_code']}").encode("utf-8")).hexdigest()[:16],
                "micropatch_diff": scrub_text(diff_text[:4000]),
                "arm1_clean_poc": arm1,
                "arm2_clean_control": arm2,
                "arm3_patch_poc": {"arm_passed": False},
                "arm4_patch_control": {"arm_passed": False},
                "arm5a_release_poc": {},
                "arm5b_release_control": {},
                "ub_divergence_class": "",
                "cross_killed_claim_ids": [],
            }

        # Apply counterfactual micro-patch and advance monotonic mtime watermark (+2s).
        subprocess.run(["git", "-C", str(slot_dir), "reset", "--hard", "HEAD"], capture_output=True, check=True)
        subprocess.run(["git", "-C", str(slot_dir), "clean", "-fdx"], capture_output=True, check=True)
        apply_proc = subprocess.run(
            ["git", "-C", str(slot_dir), "apply", "--whitespace=nowarn", str(micropatch_path.resolve())],
            capture_output=True,
            text=True,
            env=scrubbed_subprocess_env(),
            check=False,
        )
        if apply_proc.returncode != 0:
            err = scrub_text(apply_proc.stderr.strip()[:300])
            return {
                "passed": False,
                "reason": f"Micro-patch failed `git apply` cleanly: {err}",
                "observation_hash": hashlib.sha256((obs_seed + "|apply_fail").encode("utf-8")).hexdigest()[:16],
                "micropatch_diff": scrub_text(diff_text[:4000]),
                "arm1_clean_poc": arm1,
                "arm2_clean_control": arm2,
                "arm3_patch_poc": {"arm_passed": False, "stderr": err},
                "arm4_patch_control": {"arm_passed": False},
                "arm5a_release_poc": {},
                "arm5b_release_control": {},
                "ub_divergence_class": "",
                "cross_killed_claim_ids": [],
            }

        _neutralize_python_pth_escapes(slot_dir)
        _bump_files_mtime(slot_dir, touched_files, watermark_file)

        # Arm 3: Micro-patched target + PoC -> defect MUST stop firing (0 hits).
        arm3 = _run_trials(
            poc_cmd,
            slot_dir=slot_dir,
            cache_dir=cache_dir,
            timeout_sec=timeout_sec,
            oracle=oracle,
            trials=n_trials,
            helpers_dir=helpers_dir,
        )
        arm3["arm_passed"] = arm3["defect_hits"] == 0 and not arm3["timed_out"]
        if not arm3["arm_passed"]:
            return {
                "passed": False,
                "reason": (
                    f"Arm 3 (micro-patch + PoC) still triggered defect ({arm3['defect_hits']}/{n_trials} hits). "
                    "Micro-patch did not fix the root cause triggered by the PoC."
                ),
                "observation_hash": hashlib.sha256((obs_seed + f"|a3:{arm3['exit_code']}").encode("utf-8")).hexdigest()[:16],
                "micropatch_diff": scrub_text(diff_text[:4000]),
                "arm1_clean_poc": arm1,
                "arm2_clean_control": arm2,
                "arm3_patch_poc": arm3,
                "arm4_patch_control": {"arm_passed": False},
                "arm5a_release_poc": {},
                "arm5b_release_control": {},
                "ub_divergence_class": "",
                "cross_killed_claim_ids": [],
            }

        # Arm 4: Micro-patched target + benign control -> MUST still pass (blocks destructive patches!).
        arm4 = _run_trials(
            control_cmd,
            slot_dir=slot_dir,
            cache_dir=cache_dir,
            timeout_sec=timeout_sec,
            oracle=oracle,
            trials=n_trials,
            helpers_dir=helpers_dir,
        )
        arm4["arm_passed"] = arm4["defect_hits"] == 0 and arm4["clean_passes"] == n_trials
        if not arm4["arm_passed"]:
            return {
                "passed": False,
                "reason": (
                    f"Arm 4 (micro-patch + benign control) broke normal behavior (exit={arm4['exit_code']}). "
                    "Destructive or over-broad micro-patches are rejected."
                ),
                "observation_hash": hashlib.sha256((obs_seed + f"|a4:{arm4['exit_code']}").encode("utf-8")).hexdigest()[:16],
                "micropatch_diff": scrub_text(diff_text[:4000]),
                "arm1_clean_poc": arm1,
                "arm2_clean_control": arm2,
                "arm3_patch_poc": arm3,
                "arm4_patch_control": arm4,
                "arm5a_release_poc": {},
                "arm5b_release_control": {},
                "ub_divergence_class": "",
                "cross_killed_claim_ids": [],
            }

        # Optional warm cross-kill deduplication while `slot_dir` still holds the verified micro-patch.
        cross_killed: list[str] = []
        if warm_cross_kill_claims:
            for sib in warm_cross_kill_claims:
                sib_id = str(sib.get("claim_id") or "")
                sib_poc = str(sib.get("poc_cmd") or "")
                if not sib_id or sib_id == claim_id or not sib_poc:
                    continue
                sib_res = _run_trials(
                    sib_poc,
                    slot_dir=slot_dir,
                    cache_dir=cache_dir,
                    timeout_sec=timeout_sec,
                    oracle=oracle,
                    trials=1,
                    helpers_dir=helpers_dir,
                )
                if sib_res["defect_hits"] == 0 and not sib_res["timed_out"]:
                    cross_killed.append(sib_id)

        # Optional Arm 5A / Arm 5B: Release-Profile UB Differential (`-O2` / `--release`).
        arm5a: dict[str, Any] = {}
        arm5b: dict[str, Any] = {}
        ub_divergence_class = ""
        if release_cmd.strip():
            subprocess.run(["git", "-C", str(slot_dir), "reset", "--hard", "HEAD"], capture_output=True, check=True)
            subprocess.run(["git", "-C", str(slot_dir), "clean", "-fdx"], capture_output=True, check=True)
            _bump_files_mtime(slot_dir, touched_files, watermark_file)

            arm5a = _run_trials(
                release_cmd.strip(),
                slot_dir=slot_dir,
                cache_dir=cache_dir,
                timeout_sec=timeout_sec,
                oracle=oracle,
                trials=n_trials,
                helpers_dir=helpers_dir,
            )
            subprocess.run(["git", "-C", str(slot_dir), "reset", "--hard", "HEAD"], capture_output=True, check=True)
            subprocess.run(["git", "-C", str(slot_dir), "clean", "-fdx"], capture_output=True, check=True)

            eff_rel_ctrl = release_control_cmd.strip() or control_cmd
            arm5b = _run_trials(
                eff_rel_ctrl,
                slot_dir=slot_dir,
                cache_dir=cache_dir,
                timeout_sec=timeout_sec,
                oracle=oracle,
                trials=n_trials,
                helpers_dir=helpers_dir,
            )
            ub_divergence_class = classify_release_ub_divergence(
                arm1, arm5a, arm5b, min_hits=min_race_hits, n_trials=n_trials
            )
            arm5b["arm_passed"] = ub_divergence_class != "release_control_failed"
            if ub_divergence_class == "release_control_failed":
                return {
                    "passed": False,
                    "reason": f"Arm 5B (release-profile benign control) failed (exit={arm5b['exit_code']}).",
                    "observation_hash": hashlib.sha256((obs_seed + "|a5b_fail").encode("utf-8")).hexdigest()[:16],
                    "micropatch_diff": scrub_text(diff_text[:4000]),
                    "arm1_clean_poc": arm1,
                    "arm2_clean_control": arm2,
                    "arm3_patch_poc": arm3,
                    "arm4_patch_control": arm4,
                    "arm5a_release_poc": arm5a,
                    "arm5b_release_control": arm5b,
                    "ub_divergence_class": ub_divergence_class,
                    "cross_killed_claim_ids": cross_killed,
                }

        reason_msg = (
            "All 4 causal arms passed (clean PoC triggered, clean control passed, micro-patch mitigated PoC, patched control passed)."
        )
        if ub_divergence_class:
            reason_msg += f" Release UB differential={ub_divergence_class}."

        return {
            "passed": True,
            "reason": reason_msg,
            "observation_hash": hashlib.sha256((obs_seed + "|verified").encode("utf-8")).hexdigest()[:16],
            "slot_index": slot_idx,
            "touched_files": touched_files,
            "micropatch_diff": scrub_text(diff_text[:4000]),
            "arm1_clean_poc": arm1,
            "arm2_clean_control": arm2,
            "arm3_patch_poc": arm3,
            "arm4_patch_control": arm4,
            "arm5a_release_poc": arm5a,
            "arm5b_release_control": arm5b,
            "ub_divergence_class": ub_divergence_class,
            "cross_killed_claim_ids": cross_killed,
        }
    finally:
        if (slot_dir / ".git").exists():
            subprocess.run(["git", "-C", str(slot_dir), "reset", "--hard", "HEAD"], capture_output=True, check=False)
            subprocess.run(["git", "-C", str(slot_dir), "clean", "-fdx"], capture_output=True, check=False)
            _bump_files_mtime(slot_dir, touched_files, watermark_file)
        fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)
        lock_fh.close()
