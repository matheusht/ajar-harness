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

import dataclasses
import fcntl
import hashlib
import json
import os
import pathlib
import re
import secrets
import shutil
import signal
import socket
import sqlite3
import stat
import subprocess
import tarfile
import tempfile
import time
from typing import Any, Mapping

from ajar.redact import scrub_json_value, scrub_text, scrubbed_subprocess_env
from ajar.repro_helpers import ensure_helpers_runtime
from ajar.store import new_id, utc_now_iso

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
    eff_helpers = helpers_dir or ensure_helpers_runtime(slot_dir.parent.parent)
    ports = _allocate_ephemeral_ports(4)
    arm_token = secrets.token_hex(12)
    tmp_dir = cache_dir / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    has_netns = unshare_netns_available()

    shared_cc_env = resolve_shared_compiler_cache_env(slot_dir.parent.parent)
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
        **shared_cc_env,
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

    env = scrubbed_subprocess_env(
        overrides=overrides,
        tmp_dir=tmp_dir,
        run_dir=slot_dir.parent.parent.resolve(),
    )
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


SYNTHETIC_C_OBJECT_STUB_RE = re.compile(
    r"\b(?:gcc|clang|cc|g\+\+|clang\+\+)\b[^\n;|&]*(?:\b\S+\.(?:c|cc|cpp|cxx)\b[^\n;|&]*\b\S+\.(?:o|lo|a)\b|\b\S+\.(?:o|lo|a)\b[^\n;|&]*\b\S+\.(?:c|cc|cpp|cxx)\b)",
    re.IGNORECASE,
)
LIBRARY_SURFACE_KINDS: frozenset[str] = frozenset(
    {"library", "library_api", "sdk", "ffi", "ffi_boundary", "internal_fn"}
)
PRESERVED_BUILD_GLOBS: tuple[str, ...] = (
    "*.o",
    "*.lo",
    "*.a",
    "*.la",
    "*.d",
    ".deps/",
    "CMakeCache.txt",
    "CMakeFiles/",
    "config.status",
    "config.mak.autogen",
    "config.mak.uname",
)


def resolve_local_build_cache_dir(run_dir: pathlib.Path | str, slot_name: str = "slot-0") -> pathlib.Path:
    """Place heavy compiler caches (`CARGO_TARGET_DIR`, `GOCACHE`, `CCACHE_DIR`) on local SSD `/tmp`."""
    raw_root = os.environ.get("AJAR_BUILD_CACHE_ROOT", "").strip()
    cache_root = pathlib.Path(raw_root).expanduser() if raw_root else (pathlib.Path(tempfile.gettempdir()) / "ajar-build-cache")
    cdir = cache_root / pathlib.Path(run_dir).name / slot_name
    cdir.mkdir(parents=True, exist_ok=True)
    return cdir


def resolve_shared_compiler_cache_env(
    run_dir: pathlib.Path | str,
    *,
    base_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return cross-slot `ccache`/`sccache` env vars shared across `slot-0..7` without breaking dirty-tree isolation.

    `CCACHE_BASEDIR` + `CCACHE_NOHASHDIR=true` allow `slot-1..7` to hit objects compiled
    in `slot-0` even under `-g` debug flags while keeping each slot's working tree and
    per-slot `CARGO_TARGET_DIR`/`GOCACHE`/`TMPDIR` fully isolated.
    """
    src = os.environ if base_env is None else base_env
    rdir = pathlib.Path(run_dir)
    shared_root = resolve_local_build_cache_dir(rdir, "shared")
    ccache_dir = (src.get("CCACHE_DIR") or "").strip() or str(shared_root / "ccache")
    sccache_dir = (src.get("SCCACHE_DIR") or "").strip() or str(shared_root / "sccache")
    for dpath in (ccache_dir, sccache_dir):
        try:
            pathlib.Path(dpath).mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    repro_dir = (rdir / "repro").resolve()
    env_map: dict[str, str] = {
        "CCACHE_DIR": ccache_dir,
        "CCACHE_BASEDIR": str(repro_dir),
        "CCACHE_NOHASHDIR": "true",
        "SCCACHE_DIR": sccache_dir,
    }
    ccache_bin = shutil.which("ccache")
    if ccache_bin:
        env_map["AJAR_CCACHE_BIN"] = ccache_bin
        if not (src.get("CMAKE_C_COMPILER_LAUNCHER") or "").strip():
            env_map["CMAKE_C_COMPILER_LAUNCHER"] = ccache_bin
        if not (src.get("CMAKE_CXX_COMPILER_LAUNCHER") or "").strip():
            env_map["CMAKE_CXX_COMPILER_LAUNCHER"] = ccache_bin
    sccache_bin = shutil.which("sccache")
    if sccache_bin:
        env_map["AJAR_SCCACHE_BIN"] = sccache_bin
    return env_map


def _clean_slot_preserving_objects(slot_dir: pathlib.Path, *, check: bool = True) -> None:
    """Clean untracked PoC/scratch artifacts while preserving compiled C/C++ `.o`/`.a` objects."""
    cmd = ["git", "-C", str(slot_dir), "clean", "-fdx"]
    for pat in PRESERVED_BUILD_GLOBS:
        cmd.extend(["-e", pat])
    subprocess.run(cmd, capture_output=True, env=scrubbed_subprocess_env(), check=check)


@dataclasses.dataclass(frozen=True)
class _CleanBuildSnapshot:
    files: dict[str, tuple[int, int, int, int, str]]
    dirs: frozenset[str]


def _fingerprint_slot_file(
    path: pathlib.Path,
    *,
    hash_budget: list[int],
    force_hash: bool = False,
) -> tuple[int, int, int, int, str] | None:
    try:
        st = os.lstat(path)
    except OSError:
        return None
    if path.is_symlink():
        try:
            return (st.st_mode, st.st_size, st.st_mtime_ns, st.st_ino, f"symlink:{os.readlink(path)}")
        except OSError:
            return None
    if not path.is_file():
        return None
    digest = ""
    if force_hash or (st.st_size <= 8 * 1024 * 1024 and hash_budget[0] >= st.st_size):
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if not force_hash:
                hash_budget[0] -= st.st_size
        except OSError:
            return None
    return (st.st_mode, st.st_size, st.st_mtime_ns, st.st_ino, digest)


def _snapshot_clean_build_outputs(
    slot_dir: pathlib.Path,
    *,
    max_files: int = 5000,
) -> _CleanBuildSnapshot | None:
    """Capture clean-HEAD build outputs so Arm 2 can safely reuse the build when Arm 1 leaves HEAD and artifacts intact."""
    env = scrubbed_subprocess_env()
    status_proc = subprocess.run(
        ["git", "-C", str(slot_dir), "status", "--porcelain", "--untracked-files=no"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if status_proc.returncode != 0 or status_proc.stdout.strip():
        return None

    ls_proc = subprocess.run(
        ["git", "-C", str(slot_dir), "ls-files", "--others", "-z"],
        capture_output=True,
        env=env,
        check=False,
    )
    if ls_proc.returncode != 0:
        return None

    raw_entries = [item.decode("utf-8", errors="surrogateescape") for item in ls_proc.stdout.split(b"\x00") if item]
    if len(raw_entries) > max_files:
        return None

    files_fp: dict[str, tuple[int, int, int, int, str]] = {}
    hash_budget = [64 * 1024 * 1024]
    for rel in raw_entries:
        if rel.endswith("/"):
            return None
        p = slot_dir / rel
        fp = _fingerprint_slot_file(p, hash_budget=hash_budget)
        if fp is None:
            return None
        files_fp[rel] = fp

    dirs: set[str] = set()
    for root, dirnames, filenames in os.walk(slot_dir, followlinks=False):
        rel_root = pathlib.Path(root).relative_to(slot_dir)
        dirnames[:] = [d for d in dirnames if not (rel_root == pathlib.Path(".") and d == ".git")]
        for fname in filenames:
            if rel_root == pathlib.Path(".") and fname == ".git":
                continue
            try:
                st_f = os.lstat(pathlib.Path(root) / fname)
            except OSError:
                return None
            if (
                stat.S_ISFIFO(st_f.st_mode)
                or stat.S_ISSOCK(st_f.st_mode)
                or stat.S_ISCHR(st_f.st_mode)
                or stat.S_ISBLK(st_f.st_mode)
            ):
                return None
        for d in dirnames:
            dp = pathlib.Path(root) / d
            try:
                st_d = os.lstat(dp)
            except OSError:
                return None
            if (
                stat.S_ISFIFO(st_d.st_mode)
                or stat.S_ISSOCK(st_d.st_mode)
                or stat.S_ISCHR(st_d.st_mode)
                or stat.S_ISBLK(st_d.st_mode)
            ):
                return None
            if stat.S_ISDIR(st_d.st_mode):
                dirs.add((rel_root / d).as_posix())
    return _CleanBuildSnapshot(files=files_fp, dirs=frozenset(dirs))


def _is_special_file_mode(mode: int) -> bool:
    return stat.S_ISFIFO(mode) or stat.S_ISSOCK(mode) or stat.S_ISCHR(mode) or stat.S_ISBLK(mode)


def _try_clean_arm_preserving_build(
    slot_dir: pathlib.Path,
    snapshot: _CleanBuildSnapshot | None,
) -> bool:
    """Remove Arm-1 scratch files/dirs while preserving verified clean-HEAD build outputs; return False to force full rebuild."""
    if snapshot is None:
        return False

    env = scrubbed_subprocess_env()
    status_proc = subprocess.run(
        ["git", "-C", str(slot_dir), "status", "--porcelain", "--untracked-files=no"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if status_proc.returncode != 0 or status_proc.stdout.strip():
        return False

    ls_proc = subprocess.run(
        ["git", "-C", str(slot_dir), "ls-files", "--others", "-z"],
        capture_output=True,
        env=env,
        check=False,
    )
    if ls_proc.returncode != 0:
        return False

    cur_untracked = [item.decode("utf-8", errors="surrogateescape") for item in ls_proc.stdout.split(b"\x00") if item]
    for rel in cur_untracked:
        clean_rel = rel.rstrip("/")
        if clean_rel in snapshot.files:
            continue
        p = slot_dir / clean_rel
        try:
            st = os.lstat(p)
            if stat.S_ISLNK(st.st_mode) or stat.S_ISREG(st.st_mode) or _is_special_file_mode(st.st_mode):
                p.unlink(missing_ok=True)
            elif stat.S_ISDIR(st.st_mode):
                shutil.rmtree(p)
        except FileNotFoundError:
            continue
        except OSError:
            return False

    # Inspect every non-`.git` entry bottom-up:
    # - Unlink special files (FIFOs, Unix sockets, device nodes) that `git ls-files --others` omits.
    # - Remove any Arm-1 directory absent from `snapshot.dirs`; if non-empty or unremovable, fail closed.
    for root, dirnames, filenames in os.walk(slot_dir, topdown=False, followlinks=False):
        rel_root = pathlib.Path(root).relative_to(slot_dir)
        if rel_root.parts and rel_root.parts[0] == ".git":
            continue
        for fname in filenames:
            if rel_root == pathlib.Path(".") and fname == ".git":
                continue
            fp = pathlib.Path(root) / fname
            try:
                st_f = os.lstat(fp)
            except OSError:
                return False
            if _is_special_file_mode(st_f.st_mode):
                try:
                    fp.unlink()
                except OSError:
                    return False
        for d in dirnames:
            if rel_root == pathlib.Path(".") and d == ".git":
                continue
            dp = pathlib.Path(root) / d
            d_rel = (rel_root / d).as_posix()
            try:
                st_d = os.lstat(dp)
            except OSError:
                return False
            if _is_special_file_mode(st_d.st_mode):
                try:
                    dp.unlink()
                except OSError:
                    return False
                continue
            if d_rel not in snapshot.dirs:
                try:
                    if stat.S_ISLNK(st_d.st_mode):
                        dp.unlink()
                    elif stat.S_ISDIR(st_d.st_mode):
                        dp.rmdir()
                    else:
                        return False
                except OSError:
                    return False

    # Verify every directory present after the clean build still exists as a real non-symlink directory.
    for d_rel in snapshot.dirs:
        dp = slot_dir / d_rel
        if dp.is_symlink() or not dp.is_dir():
            return False

    # Verify every recorded clean-HEAD build artifact still exists and matches its exact fingerprint.
    dummy_budget = [0]
    for rel, expected_fp in snapshot.files.items():
        p = slot_dir / rel
        need_hash = bool(expected_fp[4]) and not expected_fp[4].startswith("symlink:")
        cur_fp = _fingerprint_slot_file(p, hash_budget=dummy_budget, force_hash=need_hash)
        if cur_fp != expected_fp:
            return False

    if _neutralize_python_pth_escapes(slot_dir) > 0:
        return False

    recheck = subprocess.run(
        ["git", "-C", str(slot_dir), "status", "--porcelain", "--untracked-files=no"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    return recheck.returncode == 0 and not recheck.stdout.strip()


def validate_entrypoint_fidelity(poc_cmd: str, *, surface_kind: str = "") -> tuple[bool, str]:
    """Reject synthetic C/C++ `main()` stubs linked directly against internal `.o`/`lib*.a` objects on CLI/daemon claims."""
    sk = surface_kind.strip().lower()
    if sk in LIBRARY_SURFACE_KINDS or any(tok in sk for tok in ("lib", "sdk", "ffi")):
        return (True, "ok")
    if SYNTHETIC_C_OBJECT_STUB_RE.search(poc_cmd or ""):
        return (
            False,
            "entrypoint_fidelity_violation: PoC compiles a standalone C/C++ stub linked directly against internal `.o`/`.a` "
            "objects on a non-library surface. Exercise the real target binary/CLI entrypoint (`make` + `./<binary>`), "
            "or register an explicit `library_api` / `ffi_boundary` surface when auditing a library.",
        )
    return (True, "ok")


COMPILED_SOURCE_EXTS: frozenset[str] = frozenset(
    {".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".rs", ".go", ".sol", ".zig", ".java", ".kt", ".swift"}
)
PLACEHOLDER_TOKEN_RE = re.compile(
    r"<\s*(?:conceptual_placeholder|placeholder_payload|todo_payload|redacted_payload)\s*>",
    re.IGNORECASE,
)
SCRIPT_PATH_TOKEN_RE = re.compile(r"(?:^|[\s'\"=])((?:/|\./|\.\./|[A-Za-z0-9_.-]+/)[^\s'\";|&]+\.(?:py|sh|bash))(?:$|[\s'\"])")
READ_MODE_OPEN_RE = re.compile(
    r"\bopen\s*\([^)\n]*(?:,\s*['\"]r[bt+]*['\"]|,\s*encoding\s*=|\))",
    re.IGNORECASE,
)
COMPILER_TOKEN_RE = re.compile(r"\b(?:gcc|clang|cc|g\+\+|clang\+\+|rustc)\b")


def _extract_referenced_script_texts(
    poc_cmd: str,
    search_roots: tuple[pathlib.Path, ...] = (),
    *,
    exclude_root: pathlib.Path | None = None,
) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    seen: set[pathlib.Path] = set()
    excl_resolved = exclude_root.resolve() if exclude_root is not None and exclude_root.exists() else None
    for m in SCRIPT_PATH_TOKEN_RE.finditer(poc_cmd or ""):
        raw = m.group(1).strip()
        candidates = [pathlib.Path(raw)]
        if not pathlib.Path(raw).is_absolute():
            for root in search_roots:
                candidates.append(root / raw)
        for cand in candidates:
            try:
                resolved = cand.resolve()
            except OSError:
                continue
            if resolved in seen or not resolved.is_file():
                continue
            if excl_resolved is not None:
                try:
                    resolved.relative_to(excl_resolved)
                    continue
                except ValueError:
                    pass
            seen.add(resolved)
            try:
                txt = resolved.read_text(encoding="utf-8", errors="ignore")[:131072]
                found.append((str(resolved), txt))
            except OSError:
                continue
    return found


def validate_no_static_source_cheat(
    poc_cmd: str,
    touched_files: list[str] | tuple[str, ...],
    *,
    search_roots: tuple[pathlib.Path, ...] = (),
    target_dir: pathlib.Path | None = None,
) -> tuple[bool, str]:
    """Reject placeholder PoCs or worker scripts that read/grep patched source files instead of executing the target."""
    cmd_text = poc_cmd or ""
    if PLACEHOLDER_TOKEN_RE.search(cmd_text):
        return (
            False,
            "static_source_cheat: PoC command contains a non-executable `<conceptual_placeholder>` token. "
            "Execute a concrete input against the target inside the isolated `slot-<k>` sandbox.",
        )

    clean_touched = [tf.strip().lstrip("./") for tf in touched_files if tf and tf.strip()]
    basenames = [pathlib.PurePosixPath(tf).name for tf in clean_touched if pathlib.PurePosixPath(tf).name]

    for bname in basenames:
        grep_re = re.compile(
            rf"\b(?:grep|egrep|fgrep|rg)\b[^\n;|&]*\b{re.escape(bname)}\b",
            re.IGNORECASE,
        )
        if grep_re.search(cmd_text):
            return (
                False,
                f"static_source_cheat: PoC greps patched source file {bname!r} instead of executing the target.",
            )

    scripts = [
        ("inline_poc_cmd", cmd_text),
        *_extract_referenced_script_texts(cmd_text, search_roots, exclude_root=target_dir),
    ]
    compiled_basenames = [
        pathlib.PurePosixPath(tf).name
        for tf in clean_touched
        if pathlib.PurePosixPath(tf).suffix.lower() in COMPILED_SOURCE_EXTS
    ]

    for label, text in scripts:
        if PLACEHOLDER_TOKEN_RE.search(text):
            return (
                False,
                f"static_source_cheat: verifier script {label} contains `<conceptual_placeholder>` instead of a concrete input.",
            )
        if not compiled_basenames:
            continue
        reads_text_files = (
            ".read_text(" in text
            or ".read_bytes(" in text
            or bool(READ_MODE_OPEN_RE.search(text))
        )
        if not reads_text_files:
            continue
        for cb in compiled_basenames:
            if cb not in text:
                continue
            # Allow scripts that only pass `src/foo.c` into a compiler argv or mention filenames in comments/headers.
            non_compiler_mentions = [
                ln
                for ln in text.splitlines()
                if cb in ln
                and not ln.lstrip().startswith(("#", "--- ", "+++ "))
                and not COMPILER_TOKEN_RE.search(ln)
            ]
            if non_compiler_mentions and (".read_text(" in text or ".read_bytes(" in text or not COMPILER_TOKEN_RE.search(text)):
                return (
                    False,
                    f"static_source_cheat: verifier {label} reads patched source file {cb!r} directly to fake Arm 1 vs Arm 3. "
                    "Execute the compiled binary or test harness on concrete runtime inputs.",
                )
    return (True, "ok")


BUILD_OR_ENV_ERROR_RE = re.compile(
    r"(?:"
    r"command not found"
    r"|No such file or directory.*\b(?:cargo|rustc|clang|gcc|cc|make|cmake|go|solc|forge)\b"
    r"|fatal error:\s*['\"<][^'\">\n]+['\">]\s*file not found"
    r"|cannot find -l[A-Za-z0-9_+-]+"
    r"|No rule to make target"
    r"|error:\s*failed to get `[^`]+` as a dependency"
    r"|error:\s*no matching package named"
    r"|error:\s*attempting to make an HTTP request,\s*but --offline was specified"
    r"|xcrun:\s*error:"
    r"|error\[E0463\]:\s*can't find crate"
    r"|collect2:\s*error:\s*ld returned"
    r"|clang(?:\+\+)?:\s*error:\s*linker command failed"
    r"|CMake Error"
    r")",
    re.IGNORECASE,
)


def _detect_build_or_env_failure(exit_code: int, stdout: str, stderr: str) -> bool:
    """Distinguish compiler/linker/SDK/toolchain failures from genuine target-negative runs."""
    combined = f"{stdout or ''}\n{stderr or ''}"
    if DEBUG_ABORT_SIGNAL_RE.search(combined):
        return False
    if int(exit_code) == getattr(os, "EX_SOFTWARE", 70) and re.search(r"(?m)^HARNESS_FAILURE:", combined):
        return True
    if int(exit_code) == 127:
        return True
    return bool(BUILD_OR_ENV_ERROR_RE.search(combined))


SNAPSHOT_SKIP_NAMES: frozenset[str] = frozenset(
    {".deps", "CMakeFiles", "__pycache__", ".pytest_cache", "node_modules"}
)
SNAPSHOT_SKIP_SUFFIXES: frozenset[str] = frozenset(
    {".o", ".lo", ".a", ".la", ".d"}
)


def capture_slot_post_state_snapshot(
    *,
    run_dir: pathlib.Path,
    slot_dir: pathlib.Path,
    rel_dir: str,
    claim_id: str = "",
    source_cmd: str = "",
) -> dict[str, Any]:
    """Archive a relative directory/file produced by Arm 1 inside `slot-<k>` into `repro/snapshots/<snp_id>.tar.gz`."""
    raw_rel = (rel_dir or ".").strip() or "."
    norm_rel = pathlib.PurePosixPath(raw_rel)
    if norm_rel.is_absolute() or ".." in norm_rel.parts:
        return {"ok": False, "reason": f"Invalid --save-post-state relative path: {raw_rel!r}"}

    slot_real = slot_dir.resolve()
    rel_str = "" if str(norm_rel) == "." else str(norm_rel)
    root_target = slot_dir / rel_str if rel_str else slot_dir
    if not root_target.exists() and not root_target.is_symlink():
        return {"ok": False, "reason": f"--save-post-state path {raw_rel!r} does not exist after Arm 1."}

    snap_dir = run_dir / "repro" / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    snap_id = new_id("snp")
    archive_path = snap_dir / f"{snap_id}.tar.gz"

    entries: list[str] = []
    skipped_symlinks = 0

    def _safe_arcname(p: pathlib.Path) -> str:
        return p.relative_to(slot_dir).as_posix()

    def _add_path(tar: tarfile.TarFile, p: pathlib.Path) -> None:
        nonlocal skipped_symlinks
        arc = _safe_arcname(p)
        if not arc or arc == ".":
            return
        parts = pathlib.PurePosixPath(arc).parts
        if any(pt in SNAPSHOT_SKIP_NAMES for pt in parts):
            return
        if len(parts) >= 2 and parts[0] == ".git" and parts[1] == "objects":
            return
        if p.suffix.lower() in SNAPSHOT_SKIP_SUFFIXES and not p.is_symlink():
            return
        if p.is_symlink():
            link_dest = os.readlink(p)
            if os.path.isabs(link_dest):
                skipped_symlinks += 1
                return
            joined = os.path.normpath(os.path.join(os.path.dirname(arc), link_dest))
            if joined == ".." or joined.startswith("../"):
                skipped_symlinks += 1
                return
            tar.add(str(p), arcname=arc, recursive=False)
            entries.append(f"{arc} -> {link_dest}")
            return
        if p.is_dir():
            tar.add(str(p), arcname=arc, recursive=False)
            for child in sorted(p.iterdir(), key=lambda x: x.name):
                _add_path(tar, child)
        elif p.is_file():
            try:
                resolved = p.resolve()
                resolved.relative_to(slot_real)
            except ValueError:
                return
            tar.add(str(p), arcname=arc, recursive=False)
            entries.append(arc)

    with tarfile.open(archive_path, "w:gz") as tar:
        if root_target == slot_dir:
            for child in sorted(slot_dir.iterdir(), key=lambda x: x.name):
                _add_path(tar, child)
        else:
            _add_path(tar, root_target)

    raw_bytes = archive_path.read_bytes()
    sha256_hex = hashlib.sha256(raw_bytes).hexdigest()
    try:
        stored_archive_path = str(archive_path.relative_to(run_dir))
    except ValueError:
        stored_archive_path = str(archive_path)
    return {
        "ok": True,
        "snapshot_id": snap_id,
        "claim_id": claim_id,
        "rel_dir": raw_rel,
        "archive_path": stored_archive_path,
        "sha256": sha256_hex,
        "size_bytes": len(raw_bytes),
        "manifest": {"entry_count": len(entries), "sample_entries": entries[:24], "skipped_external_symlinks": skipped_symlinks},
        "source_cmd": scrub_text(source_cmd[:500]),
        "created_at": utc_now_iso(),
    }


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


def _clear_stale_slot_git_locks(slot_dir: pathlib.Path) -> list[str]:
    """Remove stale git index/shallow lock files inside a slot worktree while holding `slot-<k>.lock`."""
    git_dir = slot_dir / ".git"
    if git_dir.is_symlink() or not git_dir.is_dir():
        return []
    cleared: list[str] = []
    for lock_name in ("index.lock", "shallow.lock"):
        lock_file = git_dir / lock_name
        if lock_file.is_file() and not lock_file.is_symlink():
            lock_file.unlink(missing_ok=True)
            cleared.append(lock_name)
    return cleared


def _prepare_slot_worktree(mirror_dir: pathlib.Path, slot_dir: pathlib.Path) -> None:
    env = scrubbed_subprocess_env()
    if not (slot_dir / ".git").exists():
        shutil.rmtree(slot_dir, ignore_errors=True)
        subprocess.run(
            ["git", "-C", str(mirror_dir), "config", "safe.directory", "*"],
            capture_output=True,
            env=env,
            check=False,
        )
        subprocess.run(
            ["git", "-c", "safe.directory=*", "clone", "--shared", str(mirror_dir), str(slot_dir)],
            capture_output=True,
            text=True,
            env=env,
            check=True,
        )
    else:
        _clear_stale_slot_git_locks(slot_dir)
        subprocess.run(["git", "-C", str(slot_dir), "reset", "--hard", "HEAD"], capture_output=True, env=env, check=True)
        _clean_slot_preserving_objects(slot_dir, check=True)
    _neutralize_python_pth_escapes(slot_dir)


def _persist_repro_failure_artifact(
    *,
    run_dir: pathlib.Path,
    claim_id: str,
    poc_cmd: str,
    control_cmd: str,
    build_cmd: str,
    micropatch_path: pathlib.Path,
    result: dict[str, Any],
) -> str:
    """Persist a scrubbed, replayable JSON failure receipt under `repro/failures/<claim_id>-<n>.json`."""
    failures_dir = run_dir / "repro" / "failures"
    failures_dir.mkdir(parents=True, exist_ok=True)
    safe_cid = re.sub(r"[^A-Za-z0-9_.-]+", "_", (claim_id or "claim").strip())[:64] or "claim"
    arms_payload = {
        "arm1_clean_poc": result.get("arm1_clean_poc") or {},
        "arm2_clean_control": result.get("arm2_clean_control") or {},
        "arm3_patch_poc": result.get("arm3_patch_poc") or {},
        "arm4_patch_control": result.get("arm4_patch_control") or {},
        "arm5a_release_poc": result.get("arm5a_release_poc") or {},
        "arm5b_release_control": result.get("arm5b_release_control") or {},
    }
    build_keys = ("build_clean", "build_arm2", "build_patched")
    any_timed_out = bool(result.get("timed_out", False)) or any(
        isinstance(v, dict) and bool(v.get("timed_out", False)) for v in arms_payload.values()
    )
    raw_receipt: dict[str, Any] = {
        "schema": "ajar-repro-failure/1",
        "recorded_at": utc_now_iso(),
        "claim_id": claim_id,
        "error_class": str(result.get("error_class") or ""),
        "poc_proven": bool(result.get("poc_proven", False)),
        "reason": str(result.get("reason") or ""),
        "observation_hash": str(result.get("observation_hash") or ""),
        "replay": {
            "poc_cmd": poc_cmd,
            "control_cmd": control_cmd,
            "build_cmd": build_cmd,
            "micropatch_path": str(micropatch_path),
        },
        "arms": arms_payload,
    }
    for bk in build_keys:
        bval = result.get(bk)
        if isinstance(bval, dict) and bval:
            raw_receipt[bk] = bval
            if bool(bval.get("timed_out", False)):
                any_timed_out = True
    raw_receipt["timed_out"] = any_timed_out
    receipt = scrub_json_value(raw_receipt)
    encoded = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8")
    seq = 1
    while True:
        fname = f"{safe_cid}-{seq}.json"
        dest = failures_dir / fname
        try:
            fd = os.open(str(dest), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            seq += 1
            continue
        with os.fdopen(fd, "wb") as fh:
            fh.write(encoded)
        return f"repro/failures/{fname}"


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
    surface_kind: str = "",
    build_cmd: str = "",
    save_post_state: str | None = None,
) -> dict[str, Any]:
    """Execute 4-arm counterfactual source reproduction (+ optional Arm 5A/5B Release UB Differential & post-state snapshot)."""
    res = _run_source_reproduction_impl(
        run_dir=run_dir,
        target_dir=target_dir,
        claim_id=claim_id,
        poc_cmd=poc_cmd,
        control_cmd=control_cmd,
        micropatch_path=micropatch_path,
        oracle=oracle,
        determinism=determinism,
        trials=trials,
        timeout_sec=timeout_sec,
        warm_cross_kill_claims=warm_cross_kill_claims,
        claim_locus=claim_locus,
        shared_guard_locus=shared_guard_locus,
        max_changed_lines=max_changed_lines,
        release_cmd=release_cmd,
        release_control_cmd=release_control_cmd,
        surface_kind=surface_kind,
        build_cmd=build_cmd,
        save_post_state=save_post_state,
    )
    if not res.get("passed"):
        res["failure_artifact"] = _persist_repro_failure_artifact(
            run_dir=run_dir,
            claim_id=claim_id,
            poc_cmd=poc_cmd,
            control_cmd=control_cmd,
            build_cmd=build_cmd,
            micropatch_path=micropatch_path,
            result=res,
        )
    return res


def _run_source_reproduction_impl(
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
    surface_kind: str = "",
    build_cmd: str = "",
    save_post_state: str | None = None,
) -> dict[str, Any]:
    ep_ok, ep_msg = validate_entrypoint_fidelity(poc_cmd, surface_kind=surface_kind)
    if not ep_ok:
        return {
            "passed": False,
            "error_class": "preflight_error",
            "reason": ep_msg,
            "observation_hash": hashlib.sha256(ep_msg.encode("utf-8")).hexdigest()[:16],
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

    if not micropatch_path.is_file():
        return {
            "passed": False,
            "error_class": "preflight_error",
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
            "error_class": "preflight_error",
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

    cheat_ok, cheat_msg = validate_no_static_source_cheat(
        poc_cmd,
        touched_files,
        search_roots=(run_dir,),
        target_dir=target_dir,
    )
    if not cheat_ok:
        return {
            "passed": False,
            "error_class": "preflight_error",
            "reason": cheat_msg,
            "observation_hash": hashlib.sha256(cheat_msg.encode("utf-8")).hexdigest()[:16],
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

    helpers_dir = ensure_helpers_runtime(run_dir)
    mirror_dir = init_source_mirror(run_dir, target_dir)
    repro_dir = run_dir / "repro"
    slot_idx, lock_fh = _acquire_slot(repro_dir)
    slot_dir = repro_dir / f"slot-{slot_idx}"
    cache_dir = resolve_local_build_cache_dir(run_dir, f"cache-{slot_idx}")
    watermark_file = cache_dir / "watermark_ns"

    n_trials = max(4, int(trials)) if determinism == "probabilistic_race" else 1
    min_race_hits = max(3, n_trials // 2) if determinism == "probabilistic_race" else 1
    captured_snapshot: dict[str, Any] | None = None
    verified_success = False
    clean_build_snapshot: _CleanBuildSnapshot | None = None

    try:
        _prepare_slot_worktree(mirror_dir, slot_dir)

        if build_cmd.strip():
            bld_clean = _run_shell_in_slot(
                build_cmd.strip(),
                slot_dir=slot_dir,
                cache_dir=cache_dir,
                timeout_sec=max(int(timeout_sec), 180),
                helpers_dir=helpers_dir,
            )
            if bld_clean["exit_code"] != 0 or bld_clean["timed_out"]:
                bld_desc = "timed out" if bld_clean["timed_out"] else f"failed (exit={bld_clean['exit_code']})"
                return {
                    "passed": False,
                    "error_class": "build_or_env_error",
                    "timed_out": bool(bld_clean["timed_out"]),
                    "reason": f"Clean-HEAD --build-cmd {bld_desc}: {bld_clean['stderr'][:240]}",
                    "observation_hash": hashlib.sha256(f"bld1:{bld_clean['exit_code']}".encode("utf-8")).hexdigest()[:16],
                    "micropatch_diff": scrub_text(diff_text[:4000]),
                    "build_clean": bld_clean,
                    "arm1_clean_poc": {"arm_passed": False},
                    "arm2_clean_control": {"arm_passed": False},
                    "arm3_patch_poc": {"arm_passed": False},
                    "arm4_patch_control": {"arm_passed": False},
                    "arm5a_release_poc": {},
                    "arm5b_release_control": {},
                    "ub_divergence_class": "",
                    "cross_killed_claim_ids": [],
                }
            clean_build_snapshot = _snapshot_clean_build_outputs(slot_dir)

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
            is_build_err = _detect_build_or_env_failure(
                int(arm1["exit_code"]), str(arm1.get("stdout", "")), str(arm1.get("stderr", ""))
            )
            err_cls = "build_or_env_error" if is_build_err else "target_negative"
            prefix = "Build/toolchain error during Arm 1" if is_build_err else "Arm 1 (clean + PoC) did not trigger defect"
            return {
                "passed": False,
                "error_class": err_cls,
                "reason": f"{prefix} ({arm1['defect_hits']}/{n_trials} hits, exit={arm1['exit_code']}).",
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

        # Capture post-state snapshot right after Arm 1 succeeds (before `git reset --hard`) when requested!
        if save_post_state is not None and save_post_state.strip():
            snap_res = capture_slot_post_state_snapshot(
                run_dir=run_dir,
                slot_dir=slot_dir,
                rel_dir=save_post_state.strip(),
                claim_id=claim_id,
                source_cmd=poc_cmd,
            )
            if not snap_res.get("ok"):
                snap_reason = str(snap_res.get("reason") or "Post-state snapshot capture failed.")
                return {
                    "passed": False,
                    "error_class": "preflight_error",
                    "reason": snap_reason,
                    "observation_hash": hashlib.sha256(f"{obs_seed}|snapshot:{snap_reason}".encode("utf-8")).hexdigest()[:16],
                    "micropatch_diff": scrub_text(diff_text[:4000]),
                    "arm1_clean_poc": arm1,
                    "arm2_clean_control": {"arm_passed": False, "not_run": True},
                    "arm3_patch_poc": {"arm_passed": False, "not_run": True},
                    "arm4_patch_control": {"arm_passed": False, "not_run": True},
                    "arm5a_release_poc": {},
                    "arm5b_release_control": {},
                    "ub_divergence_class": "",
                    "cross_killed_claim_ids": [],
                }
            captured_snapshot = snap_res

        # Clean Arm-1 scratch state between Arm 1 and Arm 2; reuse verified clean-HEAD build outputs when untouched.
        arm2_build_reused = False
        if build_cmd.strip() and _try_clean_arm_preserving_build(slot_dir, clean_build_snapshot):
            arm2_build_reused = True
        else:
            subprocess.run(["git", "-C", str(slot_dir), "reset", "--hard", "HEAD"], capture_output=True, check=True)
            _clean_slot_preserving_objects(slot_dir, check=True)
            if build_cmd.strip():
                bld_arm2 = _run_shell_in_slot(
                    build_cmd.strip(),
                    slot_dir=slot_dir,
                    cache_dir=cache_dir,
                    timeout_sec=max(int(timeout_sec), 180),
                    helpers_dir=helpers_dir,
                )
                if bld_arm2["exit_code"] != 0 or bld_arm2["timed_out"]:
                    bld_desc = (
                        "timed out after reset"
                        if bld_arm2["timed_out"]
                        else f"failed after reset (exit={bld_arm2['exit_code']})"
                    )
                    return {
                        "passed": False,
                        "error_class": "build_or_env_error",
                        "timed_out": bool(bld_arm2["timed_out"]),
                        "reason": f"Arm-2 --build-cmd {bld_desc}: {bld_arm2['stderr'][:240]}",
                        "observation_hash": hashlib.sha256(f"bld2:{bld_arm2['exit_code']}".encode("utf-8")).hexdigest()[:16],
                        "micropatch_diff": scrub_text(diff_text[:4000]),
                        "build_arm2": bld_arm2,
                        "arm1_clean_poc": arm1,
                        "arm2_clean_control": {"arm_passed": False},
                        "arm3_patch_poc": {"arm_passed": False},
                        "arm4_patch_control": {"arm_passed": False},
                        "arm5a_release_poc": {},
                        "arm5b_release_control": {},
                        "ub_divergence_class": "",
                        "cross_killed_claim_ids": [],
                    }

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
        arm2["arm2_build_reused"] = arm2_build_reused
        arm2["arm_passed"] = arm2["defect_hits"] == 0 and arm2["clean_passes"] == n_trials
        if not arm2["arm_passed"]:
            is_build_err = _detect_build_or_env_failure(
                int(arm2["exit_code"]), str(arm2.get("stdout", "")), str(arm2.get("stderr", ""))
            )
            return {
                "passed": False,
                "error_class": "build_or_env_error" if is_build_err else "target_negative",
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
        _clean_slot_preserving_objects(slot_dir, check=True)
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
                "poc_proven": True,
                "error_class": "preflight_error",
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

        if build_cmd.strip():
            bld_patch = _run_shell_in_slot(
                build_cmd.strip(),
                slot_dir=slot_dir,
                cache_dir=cache_dir,
                timeout_sec=max(int(timeout_sec), 180),
                helpers_dir=helpers_dir,
            )
            if bld_patch["exit_code"] != 0 or bld_patch["timed_out"]:
                bld_desc = (
                    "timed out compiling micro-patch"
                    if bld_patch["timed_out"]
                    else f"failed to compile micro-patch (exit={bld_patch['exit_code']})"
                )
                return {
                    "passed": False,
                    "poc_proven": True,
                    "error_class": "build_or_env_error",
                    "timed_out": bool(bld_patch["timed_out"]),
                    "reason": f"Patched --build-cmd {bld_desc}: {bld_patch['stderr'][:240]}",
                    "observation_hash": hashlib.sha256(f"bld3:{bld_patch['exit_code']}".encode("utf-8")).hexdigest()[:16],
                    "micropatch_diff": scrub_text(diff_text[:4000]),
                    "build_patched": bld_patch,
                    "arm1_clean_poc": arm1,
                    "arm2_clean_control": arm2,
                    "arm3_patch_poc": {"arm_passed": False},
                    "arm4_patch_control": {"arm_passed": False},
                    "arm5a_release_poc": {},
                    "arm5b_release_control": {},
                    "ub_divergence_class": "",
                    "cross_killed_claim_ids": [],
                }

        # Arm 3: Micro-patched target + PoC -> defect MUST stop firing (0 hits) AND complete cleanly across all trials!
        arm3 = _run_trials(
            poc_cmd,
            slot_dir=slot_dir,
            cache_dir=cache_dir,
            timeout_sec=timeout_sec,
            oracle=oracle,
            trials=n_trials,
            helpers_dir=helpers_dir,
        )
        arm3["arm_passed"] = arm3["defect_hits"] == 0 and arm3["clean_passes"] == n_trials
        if not arm3["arm_passed"]:
            if arm3["defect_hits"]:
                a3_error_class = "micropatch_error"
                a3_reason = (
                    f"Arm 3 (micro-patch + PoC) still triggered defect ({arm3['defect_hits']}/{n_trials} hits). "
                    "Arms 1 & 2 passed (`poc_proven=true`); refine `--micropatch` without rewriting the PoC."
                )
            else:
                is_build_err = _detect_build_or_env_failure(
                    int(arm3["exit_code"]), str(arm3.get("stdout", "")), str(arm3.get("stderr", ""))
                )
                a3_exit = int(arm3["exit_code"])
                is_signal_death = a3_exit < 0 or a3_exit >= 128
                a3_error_class = (
                    "build_or_env_error"
                    if is_build_err
                    else ("target_negative" if is_signal_death else "micropatch_error")
                )
                a3_reason = (
                    "Arm 3 (micro-patch + PoC) failed to complete cleanly "
                    f"(clean_passes={arm3['clean_passes']}/{n_trials}, exit={arm3['exit_code']}, "
                    f"timed_out={arm3['timed_out']})."
                )
            return {
                "passed": False,
                "poc_proven": True,
                "error_class": a3_error_class,
                "reason": a3_reason,
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
            is_build_err = _detect_build_or_env_failure(
                int(arm4["exit_code"]), str(arm4.get("stdout", "")), str(arm4.get("stderr", ""))
            )
            return {
                "passed": False,
                "poc_proven": True,
                "error_class": "build_or_env_error" if is_build_err else "micropatch_error",
                "reason": (
                    f"Arm 4 (micro-patch + benign control) broke normal behavior (exit={arm4['exit_code']}). "
                    "Arms 1 & 2 passed (`poc_proven=true`); destructive or over-broad micro-patches are rejected."
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
                if sib_res["defect_hits"] == 0 and sib_res["clean_passes"] == 1:
                    cross_killed.append(sib_id)

        # Optional Arm 5A / Arm 5B: Release-Profile UB Differential (`-O2` / `--release`).
        arm5a: dict[str, Any] = {}
        arm5b: dict[str, Any] = {}
        ub_divergence_class = ""
        if release_cmd.strip():
            subprocess.run(["git", "-C", str(slot_dir), "reset", "--hard", "HEAD"], capture_output=True, check=True)
            _clean_slot_preserving_objects(slot_dir, check=True)
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
            _clean_slot_preserving_objects(slot_dir, check=True)

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
                    "error_class": "target_negative",
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

        verified_success = True
        return {
            "passed": True,
            "error_class": "",
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
            "post_state_snapshot": captured_snapshot,
        }
    finally:
        try:
            if not verified_success and captured_snapshot and captured_snapshot.get("archive_path"):
                raw_snap = pathlib.Path(str(captured_snapshot["archive_path"]))
                snap_file = raw_snap if raw_snap.is_absolute() else (run_dir / raw_snap)
                snap_file.unlink(missing_ok=True)
            if (slot_dir / ".git").exists():
                _clear_stale_slot_git_locks(slot_dir)
                subprocess.run(["git", "-C", str(slot_dir), "reset", "--hard", "HEAD"], capture_output=True, check=False)
                _clean_slot_preserving_objects(slot_dir, check=False)
                _bump_files_mtime(slot_dir, touched_files, watermark_file)
        finally:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)
            lock_fh.close()


def run_repro_try(
    *,
    run_dir: pathlib.Path,
    target_dir: pathlib.Path,
    cmd: str,
    patch_path: pathlib.Path | None = None,
    build_cmd: str = "",
    oracle: dict[str, Any] | None = None,
    timeout_sec: int = 60,
) -> dict[str, Any]:
    """Execute a strike-free exploratory build/PoC smoke test inside the shared 8-slot pool (`slot-<k>`)."""
    helpers_dir = ensure_helpers_runtime(run_dir)
    mirror_dir = init_source_mirror(run_dir, target_dir)
    repro_dir = run_dir / "repro"
    slot_idx, lock_fh = _acquire_slot(repro_dir)
    slot_dir = repro_dir / f"slot-{slot_idx}"
    cache_dir = resolve_local_build_cache_dir(run_dir, f"cache-{slot_idx}")
    watermark_file = cache_dir / "watermark_ns"
    touched: list[str] = []

    try:
        _prepare_slot_worktree(mirror_dir, slot_dir)
        if patch_path is not None:
            if not patch_path.is_file():
                return {
                    "ok": False,
                    "slot_index": slot_idx,
                    "error_class": "preflight_error",
                    "reason": f"Patch file not found: {patch_path}",
                }
            ap = subprocess.run(
                ["git", "-C", str(slot_dir), "apply", "--whitespace=nowarn", str(patch_path.resolve())],
                capture_output=True,
                text=True,
                env=scrubbed_subprocess_env(),
                check=False,
            )
            if ap.returncode != 0:
                return {
                    "ok": False,
                    "slot_index": slot_idx,
                    "error_class": "preflight_error",
                    "reason": f"Patch failed `git apply`: {scrub_text(ap.stderr[:240])}",
                }
            for ln in patch_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if ln.startswith("+++ ") and ln[4:].strip() != "/dev/null":
                    touched.append(re.sub(r"^b/", "", ln[4:].split("\t", 1)[0].strip()))
            _neutralize_python_pth_escapes(slot_dir)
            _bump_files_mtime(slot_dir, touched, watermark_file)

        build_res: dict[str, Any] = {}
        if build_cmd.strip():
            build_res = _run_shell_in_slot(
                build_cmd.strip(),
                slot_dir=slot_dir,
                cache_dir=cache_dir,
                timeout_sec=max(int(timeout_sec), 180),
                helpers_dir=helpers_dir,
            )
            if build_res["exit_code"] != 0 or build_res["timed_out"]:
                return {
                    "ok": False,
                    "slot_index": slot_idx,
                    "error_class": "build_or_env_error",
                    "reason": f"--build-cmd failed (exit={build_res['exit_code']})",
                    "build": build_res,
                }

        res = _run_shell_in_slot(
            cmd,
            slot_dir=slot_dir,
            cache_dir=cache_dir,
            timeout_sec=timeout_sec,
            helpers_dir=helpers_dir,
        )
        fired = _evaluate_defect_fired(res["exit_code"], res["stdout"], res["stderr"], res["timed_out"], oracle)
        is_bld = (not fired) and _detect_build_or_env_failure(res["exit_code"], res["stdout"], res["stderr"])
        return {
            "ok": True,
            "slot_index": slot_idx,
            "defect_fired": fired,
            "error_class": "build_or_env_error" if is_bld else "",
            "build": build_res,
            "result": res,
        }
    finally:
        try:
            if (slot_dir / ".git").exists():
                _clear_stale_slot_git_locks(slot_dir)
                subprocess.run(["git", "-C", str(slot_dir), "reset", "--hard", "HEAD"], capture_output=True, check=False)
                _clean_slot_preserving_objects(slot_dir, check=False)
                if touched:
                    _bump_files_mtime(slot_dir, touched, watermark_file)
        finally:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)
            lock_fh.close()


_FALLBACK_DISPATCH_STATUSES: frozenset[str] = frozenset({"idle_no_return", "filter_blocked", "refused"})


def _normalize_failure_reason(reason: str) -> str:
    """Group per-attempt failure reasons into stable, scrubbed rejection categories."""
    clean = scrub_text((reason or "").strip())
    if not clean:
        return "unspecified"
    head = clean.splitlines()[0].split(": ", 1)[0].strip()
    head = re.sub(r"\s*\([^)]*(?:exit=|hits|timed_out|line|lines)[^)]*\)\s*\.?$", "", head).strip()
    return (head or clean)[:120]


def aggregate_failure_telemetry(
    run_dir: pathlib.Path,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Aggregate `repro/failures/*.json` receipts by error class, reason, timeouts, and swarm fallback breakdown."""
    failures_dir = run_dir / "repro" / "failures"
    total_receipts = 0
    malformed_receipts = 0
    timeout_count = 0
    timeouts_by_arm: dict[str, int] = {}
    by_error_class: dict[str, int] = {}
    by_rejection_reason: dict[str, int] = {}
    by_claim_id: dict[str, int] = {}

    if failures_dir.is_dir() and not failures_dir.is_symlink():
        for fpath in sorted(p for p in failures_dir.glob("*.json") if p.is_file() and not p.is_symlink()):
            try:
                raw = json.loads(fpath.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                malformed_receipts += 1
                continue
            if not isinstance(raw, dict):
                malformed_receipts += 1
                continue

            total_receipts += 1
            err_cls = str(raw.get("error_class") or "").strip() or "unknown"
            by_error_class[err_cls] = by_error_class.get(err_cls, 0) + 1

            raw_reason = str(raw.get("reason") or "")
            norm_reason = _normalize_failure_reason(raw_reason)
            by_rejection_reason[norm_reason] = by_rejection_reason.get(norm_reason, 0) + 1

            cid = str(raw.get("claim_id") or "").strip() or "unknown"
            by_claim_id[cid] = by_claim_id.get(cid, 0) + 1

            receipt_timed_out = bool(raw.get("timed_out", False))
            arms_obj = raw.get("arms")
            if isinstance(arms_obj, dict):
                for arm_name, arm_val in arms_obj.items():
                    if isinstance(arm_val, dict) and bool(arm_val.get("timed_out", False)):
                        receipt_timed_out = True
                        ak = str(arm_name)
                        timeouts_by_arm[ak] = timeouts_by_arm.get(ak, 0) + 1
            for build_key in ("build_clean", "build_arm2", "build_patched", "build_patch", "build"):
                b_obj = raw.get(build_key)
                if isinstance(b_obj, dict) and bool(b_obj.get("timed_out", False)):
                    receipt_timed_out = True
                    timeouts_by_arm[build_key] = timeouts_by_arm.get(build_key, 0) + 1
            if not receipt_timed_out and re.search(r"\btimed?\s*out\b", raw_reason, re.IGNORECASE):
                receipt_timed_out = True
            if receipt_timed_out:
                timeout_count += 1

    swarm_summary: dict[str, Any] = {
        "total_dispatches": 0,
        "by_status": {},
        "by_wire_profile": {},
        "by_stage": {},
        "fallback_total": 0,
        "fallback_by_reason": {},
        "fallback_by_stage": {},
        "fallback_by_profile": {},
    }
    if conn is not None:
        has_swarm = (
            conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='swarm_dispatches'").fetchone()
            is not None
        )
        if has_swarm:
            by_status: dict[str, int] = {}
            by_profile: dict[str, int] = {}
            by_stage: dict[str, int] = {}
            fb_reason: dict[str, int] = {}
            fb_stage: dict[str, int] = {}
            fb_profile: dict[str, int] = {}
            rows = conn.execute("SELECT stage, wire_profile, status FROM swarm_dispatches").fetchall()
            for r in rows:
                st = str(r["status"] or "unknown")
                prof = str(r["wire_profile"] or "direct")
                stg = str(r["stage"] or "unknown")
                by_status[st] = by_status.get(st, 0) + 1
                by_profile[prof] = by_profile.get(prof, 0) + 1
                by_stage[stg] = by_stage.get(stg, 0) + 1
                if st in _FALLBACK_DISPATCH_STATUSES:
                    fb_reason[st] = fb_reason.get(st, 0) + 1
                    fb_stage[stg] = fb_stage.get(stg, 0) + 1
                    fb_profile[prof] = fb_profile.get(prof, 0) + 1
            swarm_summary = {
                "total_dispatches": len(rows),
                "by_status": dict(sorted(by_status.items())),
                "by_wire_profile": dict(sorted(by_profile.items())),
                "by_stage": dict(sorted(by_stage.items())),
                "fallback_total": sum(fb_reason.values()),
                "fallback_by_reason": dict(sorted(fb_reason.items())),
                "fallback_by_stage": dict(sorted(fb_stage.items())),
                "fallback_by_profile": dict(sorted(fb_profile.items())),
            }

    payload: dict[str, Any] = {
        "schema": "ajar-failure-telemetry/1",
        "total_receipts": total_receipts,
        "malformed_receipts": malformed_receipts,
        "timeout_count": timeout_count,
        "timeouts_by_arm": dict(sorted(timeouts_by_arm.items())),
        "by_error_class": dict(sorted(by_error_class.items())),
        "by_rejection_reason": dict(sorted(by_rejection_reason.items(), key=lambda kv: (-kv[1], kv[0]))),
        "by_claim_id": dict(sorted(by_claim_id.items(), key=lambda kv: (-kv[1], kv[0]))),
        "swarm_dispatches": swarm_summary,
    }
    scrubbed = scrub_json_value(payload)
    assert isinstance(scrubbed, dict)
    return scrubbed

