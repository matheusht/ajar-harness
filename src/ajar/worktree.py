"""Clean-room git worktree sandbox, 1-hop delegate mounting (D1), 3-profile matrix (D2), & net isolation (D6)."""

from __future__ import annotations

import functools
import os
import shutil
import subprocess
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

BUILD_PROFILES: dict[str, dict[str, str]] = {
    "upstream": {
        "CFLAGS": "-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer",
        "CXXFLAGS": "-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer",
        "ASAN_OPTIONS": "detect_leaks=0:abort_on_error=1:symbolize=1",
        "UBSAN_OPTIONS": "print_stacktrace=1:halt_on_error=1",
    },
    "debian": {
        "CFLAGS": "-O2 -g -D_FORTIFY_SOURCE=2 -fstack-protector-strong -fsanitize=address,undefined",
        "CXXFLAGS": "-O2 -g -D_FORTIFY_SOURCE=2 -fstack-protector-strong -fsanitize=address,undefined",
        "ASAN_OPTIONS": "detect_leaks=0:abort_on_error=1:symbolize=1",
    },
    "al2023": {
        "CFLAGS": "-O2 -g -D_FORTIFY_SOURCE=2 -fPIE -fsanitize=address,undefined",
        "CXXFLAGS": "-O2 -g -D_FORTIFY_SOURCE=2 -fPIE -fsanitize=address,undefined",
        "ASAN_OPTIONS": "detect_leaks=0:abort_on_error=1:symbolize=1",
    },
}


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str
    duration_s: float


@functools.lru_cache(maxsize=1)
def _can_unshare_net() -> bool:
    if shutil.which("unshare") is None:
        return False
    probe = subprocess.run(
        ["unshare", "-rn", "true"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return probe.returncode == 0


def _is_git_repo(repo: Path) -> bool:
    probe = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", "HEAD"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return probe.returncode == 0


@contextmanager
def clean_worktree(
    repo: Path,
    mount_deps: list[Path] | None = None,
) -> Iterator[tuple[Path, dict[str, str]]]:
    """Create a disposable clean checkout plus optional 1-hop delegate mounts (D1)."""
    repo = repo.resolve()
    tmp_root = Path(tempfile.mkdtemp(prefix="ajar-wt-"))
    wt_dir = tmp_root / "tree"
    used_git_wt = False
    try:
        if _is_git_repo(repo):
            res = subprocess.run(
                ["git", "-C", str(repo), "worktree", "add", "--detach", str(wt_dir), "HEAD"],
                capture_output=True,
                text=True,
                check=False,
            )
            used_git_wt = res.returncode == 0
        if not used_git_wt:
            shutil.copytree(
                repo,
                wt_dir,
                symlinks=True,
                ignore=shutil.ignore_patterns(".ajar", "__pycache__", ".pytest_cache"),
            )
        dep_env: dict[str, str] = {}
        if mount_deps:
            deps_root = wt_dir / ".ajar-deps"
            deps_root.mkdir(parents=True, exist_ok=True)
            lib_dirs: list[str] = []
            pc_dirs: list[str] = []
            for dep in mount_deps:
                dep_resolved = dep.resolve()
                link_path = deps_root / dep_resolved.name
                if not link_path.exists():
                    os.symlink(dep_resolved, link_path)
                for sub in ("", "lib", "build"):
                    cand = link_path / sub if sub else link_path
                    if cand.is_dir():
                        lib_dirs.append(str(cand))
                pc_cand = link_path / "pkgconfig"
                if pc_cand.is_dir():
                    pc_dirs.append(str(pc_cand))
            dep_env["AJAR_DEPS_DIR"] = str(deps_root)
            if lib_dirs:
                dep_env["LD_LIBRARY_PATH"] = ":".join(lib_dirs)
            if pc_dirs:
                dep_env["PKG_CONFIG_PATH"] = ":".join(pc_dirs)
        yield wt_dir, dep_env
    finally:
        if used_git_wt:
            subprocess.run(
                ["git", "-C", str(repo), "worktree", "remove", "--force", str(wt_dir)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        shutil.rmtree(tmp_root, ignore_errors=True)


def run_hermetic(
    cmd: str | list[str],
    cwd: Path,
    timeout: int = 120,
    profile: str = "upstream",
    extra_env: dict[str, str] | None = None,
    isolate_net: bool = True,
) -> CommandResult:
    """Execute a command inside a locked build profile with fail-closed network isolation (D2, D6)."""
    if profile not in BUILD_PROFILES:
        raise ValueError(f"Unsupported build profile {profile!r}; allowed: {sorted(BUILD_PROFILES)}")
    env = os.environ.copy()
    env.update(BUILD_PROFILES[profile])
    if isolate_net:
        env["HTTP_PROXY"] = "http://127.0.0.1:0"
        env["HTTPS_PROXY"] = "http://127.0.0.1:0"
        env["NO_PROXY"] = ""
    if extra_env:
        env.update(extra_env)
    argv = ["bash", "-c", cmd] if isinstance(cmd, str) else list(cmd)
    if isolate_net and _can_unshare_net():
        argv = ["unshare", "-rn", "--", *argv]
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return CommandResult(proc.returncode, proc.stdout, proc.stderr, time.monotonic() - t0)
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        err = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return CommandResult(124, out, err + "\n[AJAR_TIMEOUT]", time.monotonic() - t0)
