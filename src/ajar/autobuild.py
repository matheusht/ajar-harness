"""Ring-1 polyglot .ajar/build.sh generator, write-jailed Build Doctor, and Input Encoder fuzzer."""

from __future__ import annotations

import ast
import contextlib
import hashlib
import inspect
import json
import os
import random
import re
import shlex
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from ajar.agent import SpanTracker, WorkspaceTools
from ajar.cli import BuildRecipe
from ajar.llm import LLMClient
from ajar.verify import clean_worktree, parse_crash_signature
from ajar.whiteboard import Section, StigmergicWhiteboard

SANITIZER_FLAGS = "-fsanitize=address,undefined -fno-omit-frame-pointer"
DEFAULT_ASAN_OPTIONS = "detect_leaks=0:abort_on_error=1:symbolize=1"
DEFAULT_UBSAN_OPTIONS = "print_stacktrace=1:halt_on_error=1"

BUILD_PROFILES: dict[str, dict[str, str]] = {
    "upstream": {
        "CFLAGS": f"-O1 -g {SANITIZER_FLAGS}",
        "CXXFLAGS": f"-O1 -g {SANITIZER_FLAGS}",
        "LDFLAGS": SANITIZER_FLAGS,
        "ASAN_OPTIONS": DEFAULT_ASAN_OPTIONS,
        "UBSAN_OPTIONS": DEFAULT_UBSAN_OPTIONS,
        "CMAKE_BUILD_PARALLEL_LEVEL": "4",
        "MAKEFLAGS": "-j4",
        "CARGO_BUILD_JOBS": "4",
    },
    "debian": {
        "CFLAGS": f"-O1 -g -fPIC -DDEBIAN_BUILD=1 {SANITIZER_FLAGS}",
        "CXXFLAGS": f"-O1 -g -fPIC -DDEBIAN_BUILD=1 {SANITIZER_FLAGS}",
        "LDFLAGS": SANITIZER_FLAGS,
        "PKG_CONFIG_PATH": "/usr/lib/x86_64-linux-gnu/pkgconfig:/usr/share/pkgconfig",
        "ASAN_OPTIONS": DEFAULT_ASAN_OPTIONS,
        "UBSAN_OPTIONS": DEFAULT_UBSAN_OPTIONS,
        "CMAKE_BUILD_PARALLEL_LEVEL": "4",
        "MAKEFLAGS": "-j4",
        "CARGO_BUILD_JOBS": "4",
    },
    "al2023": {
        "CFLAGS": f"-O1 -g -fPIC -U_FORTIFY_SOURCE -D_FORTIFY_SOURCE=0 {SANITIZER_FLAGS}",
        "CXXFLAGS": f"-O1 -g -fPIC -U_FORTIFY_SOURCE -D_FORTIFY_SOURCE=0 {SANITIZER_FLAGS}",
        "LDFLAGS": SANITIZER_FLAGS,
        "PKG_CONFIG_PATH": "/usr/lib64/pkgconfig:/usr/share/pkgconfig",
        "ASAN_OPTIONS": DEFAULT_ASAN_OPTIONS,
        "UBSAN_OPTIONS": DEFAULT_UBSAN_OPTIONS,
        "CMAKE_BUILD_PARALLEL_LEVEL": "4",
        "MAKEFLAGS": "-j4",
        "CARGO_BUILD_JOBS": "4",
    },
}

_BLOCKED_ENCODER_IMPORTS = frozenset({
    "ctypes",
    "http",
    "multiprocessing",
    "os",
    "pathlib",
    "pty",
    "shutil",
    "signal",
    "socket",
    "subprocess",
    "sys",
    "threading",
    "urllib",
})


def _detect_tier0_commands(repo: Path) -> tuple[str, list[str], str]:
    if (repo / "oss-fuzz" / "build.sh").is_file():
        cmds = [
            'export OUT="${OUT:-$PWD/.ajar-out}"',
            'export WORK="${WORK:-$PWD/.ajar-work}"',
            'export SRC="${SRC:-$PWD}"',
            'mkdir -p "$OUT" "$WORK"',
            "bash oss-fuzz/build.sh",
        ]
        return ("oss-fuzz", cmds, "")
    if (repo / "foundry.toml").is_file():
        cmds = [
            "forge build",
            'if [ "${AJAR_RUN_TESTS:-0}" = "1" ]',
            "then",
            "    forge test",
            "fi",
        ]
        return ("foundry", cmds, "forge test")
    if (repo / "CMakeLists.txt").is_file():
        cmake_cfg = (
            "cmake -B .ajar-build "
            '-DCMAKE_C_FLAGS="$CFLAGS" '
            '-DCMAKE_CXX_FLAGS="$CXXFLAGS" '
            '-DCMAKE_EXE_LINKER_FLAGS="$LDFLAGS" '
            '-DCMAKE_SHARED_LINKER_FLAGS="$LDFLAGS"'
        )
        cmake_bld = 'cmake --build .ajar-build -j "${CMAKE_BUILD_PARALLEL_LEVEL:-4}"'
        return ("cmake", [cmake_cfg, cmake_bld], "ctest --test-dir .ajar-build")
    if (repo / "meson.build").is_file():
        cmds = [
            "if [ ! -d .ajar-meson ]",
            "then",
            "    meson setup .ajar-meson",
            "fi",
            'meson compile -C .ajar-meson -j "${CMAKE_BUILD_PARALLEL_LEVEL:-4}"',
        ]
        return ("meson", cmds, "meson test -C .ajar-meson")
    if (repo / "Cargo.toml").is_file():
        cmds = ['CARGO_BUILD_JOBS="${CMAKE_BUILD_PARALLEL_LEVEL:-4}" cargo build --tests']
        return ("cargo", cmds, "cargo test")
    if (repo / "go.mod").is_file():
        cmds = ["go build -race ./..."]
        return ("go", cmds, "go test -race ./...")
    for mk in ("Makefile", "GNUmakefile", "makefile"):
        if (repo / mk).is_file():
            make_cmd = (
                'make -j "${CMAKE_BUILD_PARALLEL_LEVEL:-4}" '
                'CFLAGS="$CFLAGS" CXXFLAGS="$CXXFLAGS" LDFLAGS="$LDFLAGS"'
            )
            return ("make", [make_cmd], "make test")
    if (repo / "pyproject.toml").is_file():
        return ("pyproject", ["pytest -q"], "pytest -q")
    if (repo / "package.json").is_file():
        return ("npm", ["npm test"], "npm test")
    return ("static", ['echo "No Tier-0 build recipe detected" >&2', "exit 2"], "")


def synthesize_build_recipe(repo: Path, profile: str = "upstream") -> BuildRecipe:
    repo_path = Path(repo)
    if profile not in BUILD_PROFILES:
        raise ValueError(f"Unknown build profile: {profile}")
    prof_env = dict(BUILD_PROFILES[profile])
    script_file = repo_path / ".ajar" / "build.sh"
    if script_file.is_file():
        return BuildRecipe(
            profile=profile,
            build_script="bash .ajar/build.sh",
            test_cmd="",
            static_only=False,
            verified=False,
            build_system="existing",
            env=prof_env,
        )
    build_system, body_lines, test_cmd = _detect_tier0_commands(repo_path)
    script_file.parent.mkdir(parents=True, exist_ok=True)
    header_lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        'cd "$(dirname "$0")/.."',
        f'export CFLAGS="${{CFLAGS:-{prof_env["CFLAGS"]}}}"',
        f'export CXXFLAGS="${{CXXFLAGS:-{prof_env["CXXFLAGS"]}}}"',
        f'export LDFLAGS="${{LDFLAGS:-{prof_env["LDFLAGS"]}}}"',
        f'export ASAN_OPTIONS="${{ASAN_OPTIONS:-{prof_env["ASAN_OPTIONS"]}}}"',
        f'export UBSAN_OPTIONS="${{UBSAN_OPTIONS:-{prof_env["UBSAN_OPTIONS"]}}}"',
        "export CMAKE_BUILD_PARALLEL_LEVEL="
        f'"${{CMAKE_BUILD_PARALLEL_LEVEL:-{prof_env["CMAKE_BUILD_PARALLEL_LEVEL"]}}}"',
    ]
    if "PKG_CONFIG_PATH" in prof_env:
        header_lines.append(
            f'export PKG_CONFIG_PATH="${{PKG_CONFIG_PATH:-{prof_env["PKG_CONFIG_PATH"]}}}"'
        )
    script_text = "\n".join(header_lines + [""] + body_lines) + "\n"
    script_file.write_text(script_text, encoding="utf-8")
    os.chmod(script_file, 0o755)
    return BuildRecipe(
        profile=profile,
        build_script="bash .ajar/build.sh" if build_system != "static" else "",
        test_cmd=test_cmd,
        static_only=build_system == "static",
        verified=False,
        build_system=build_system,
        env=prof_env,
    )


def _run_build_script(repo: Path, profile: str, timeout: float = 90.0) -> tuple[int, str]:
    env = os.environ.copy()
    env.update(BUILD_PROFILES.get(profile, BUILD_PROFILES["upstream"]))
    script = repo / ".ajar" / "build.sh"
    if not script.is_file():
        return (127, ".ajar/build.sh missing")
    try:
        proc = subprocess.run(
            ["bash", str(script)],
            cwd=str(repo),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return (124, str(exc))
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    return (proc.returncode, combined[-4000:])


def _parse_doctor_edits(raw_text: str) -> list[tuple[str, str]]:
    match_json = re.search(r"\{.*\}", raw_text, flags=re.DOTALL)
    if match_json:
        with contextlib.suppress(ValueError):
            parsed = json.loads(match_json.group(0))
            if isinstance(parsed, dict) and ("content" in parsed or "script" in parsed):
                target = str(parsed.get("path") or parsed.get("file_path") or ".ajar/build.sh")
                body = str(parsed.get("content") or parsed.get("script") or "")
                return [(target, body)]
    match_sh = re.search(r"```(?:bash|sh)?\n(.*?)```", raw_text, flags=re.DOTALL)
    if match_sh:
        return [(".ajar/build.sh", match_sh.group(1))]
    if raw_text.lstrip().startswith("#!"):
        return [(".ajar/build.sh", raw_text)]
    return []


async def run_build_doctor(
    repo: Path,
    recipe: BuildRecipe,
    llm: LLMClient | None,
    spans: SpanTracker | None = None,
) -> BuildRecipe:
    repo_path = Path(repo)
    tools = WorkspaceTools(repo_path, spans=spans, write_allowlist={".ajar/build.sh"})
    rc, log_tail = _run_build_script(repo_path, recipe.profile)
    if rc == 0:
        return replace(recipe, static_only=False, verified=True, last_error="")
    if llm is None:
        return replace(recipe, static_only=True, verified=False, last_error=log_tail)

    sys_msg = (
        "You are Ring-1 Build Doctor. Repair ONLY .ajar/build.sh. "
        "Never modify repository source files. "
        'Respond with JSON: {"path": ".ajar/build.sh", "content": "#!/usr/bin/env bash..."}'
    )
    entries = sorted(p.name for p in repo_path.iterdir())[:40]
    for turn in range(2):
        script_path = repo_path / ".ajar" / "build.sh"
        cur_txt = script_path.read_text(encoding="utf-8", errors="replace") if script_path.is_file() else ""
        prompt = (
            f"Build turn {turn + 1}/2 failed (exit {rc}).\n"
            f"Repo files: {', '.join(entries)}\n"
            f"Current .ajar/build.sh:\n{cur_txt}\n"
            f"Error output:\n{log_tail}\n"
        )
        res = llm.complete([{"role": "user", "content": prompt}], role="doctor", system=sys_msg)
        resp = await res if inspect.isawaitable(res) else res
        edits = _parse_doctor_edits(resp.content)
        if not edits:
            continue
        for target_path, new_script in edits:
            tools.write_file(target_path, new_script)
        rc, log_tail = _run_build_script(repo_path, recipe.profile)
        if rc == 0:
            return replace(
                recipe,
                build_script="sh .ajar/build.sh",
                static_only=False,
                verified=True,
                last_error="",
            )
    return replace(recipe, static_only=True, verified=False, last_error=log_tail)


def _load_encoder_callable(code_str: str) -> Callable[[random.Random], bytes]:
    tree = ast.parse(code_str, mode="exec")
    has_emit = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "emit":
            has_emit = True
        elif isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in _BLOCKED_ENCODER_IMPORTS:
                    raise ValueError(f"Blocked import in encoder: {root}")
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            if root in _BLOCKED_ENCODER_IMPORTS:
                raise ValueError(f"Blocked import in encoder: {root}")
    if not has_emit:
        raise ValueError("Input encoder must define def emit(rng: random.Random) -> bytes")
    ns: dict[str, Any] = {"random": random}
    exec(compile(tree, "<ajar_encoder>", "exec"), ns)
    emit_fn = ns.get("emit")
    if not callable(emit_fn):
        raise ValueError("emit symbol is not callable")
    sample_a = emit_fn(random.Random(1337))
    sample_b = emit_fn(random.Random(1337))
    if not isinstance(sample_a, (bytes, bytearray)):
        raise TypeError("emit(rng) must return bytes")
    if bytes(sample_a) != bytes(sample_b):
        raise ValueError("emit(rng) must be strictly deterministic for a fixed seed")
    return lambda rng: bytes(emit_fn(rng))


def register_input_encoder(
    repo: Path,
    name: str,
    code_str: str,
    wb: StigmergicWhiteboard | None = None,
) -> Path:
    repo_path = Path(repo)
    _load_encoder_callable(code_str)
    clean_name = re.sub(r"[^a-zA-Z0-9_]+", "_", name).strip("_") or "encoder"
    digest = hashlib.sha256(code_str.encode("utf-8")).hexdigest()[:12]
    enc_dir = repo_path / ".ajar" / "encoders"
    enc_dir.mkdir(parents=True, exist_ok=True)
    target = enc_dir / f"{digest}_{clean_name}.py"
    if not target.is_file():
        tmp = enc_dir / f".{digest}_{clean_name}.py.tmp"
        tmp.write_text(code_str, encoding="utf-8")
        os.replace(tmp, target)
    if wb is not None:
        wb.post(Section.ENCODER, summary=f"Registered encoder {target.name}", target=str(target.name))
    return target


def _boundary_seeds(rng: random.Random) -> list[bytes]:
    return [
        b"",
        b"\x00",
        b"\xff" * 64,
        b"A" * 1024,
        b"-1\n",
        b"\x7f\xff\xff\xff\x80\x00\x00\x00",
        bytes(rng.getrandbits(8) for _ in range(48)),
    ]


def run_microfuzz_encoder(
    repo: Path,
    entrypoint_cmd_template: str,
    encoder_fn: Callable[[random.Random], bytes] | Path | str | None = None,
    iterations: int = 32,
    seed: int = 1337,
    profile: str = "upstream",
) -> list[dict[str, Any]]:
    repo_path = Path(repo)
    rng = random.Random(seed)
    resolved_fn: Callable[[random.Random], bytes] | None = None
    if isinstance(encoder_fn, (Path, str)):
        code = Path(encoder_fn).read_text(encoding="utf-8")
        resolved_fn = _load_encoder_callable(code)
    elif callable(encoder_fn):
        resolved_fn = encoder_fn

    payloads: list[bytes] = []
    if resolved_fn is not None:
        for _ in range(max(0, iterations)):
            payloads.append(bytes(resolved_fn(rng)))
        payloads.extend(_boundary_seeds(rng)[:4])
    else:
        base = _boundary_seeds(rng)
        for idx in range(max(0, iterations)):
            if idx < len(base):
                payloads.append(base[idx])
            else:
                payloads.append(bytes(rng.getrandbits(8) for _ in range(rng.randint(1, 128))))

    tokens = shlex.split(entrypoint_cmd_template)
    if not tokens:
        return []
    env = os.environ.copy()
    env.update(BUILD_PROFILES.get(profile, BUILD_PROFILES["upstream"]))
    crashes_by_hash: dict[str, dict[str, Any]] = {}

    with clean_worktree(repo_path) as wt:
        seed_file = wt / ".ajar_seed.bin"
        uses_file = any(
            ph in tok
            for tok in tokens
            for ph in ("{input}", "{input_file}", "@@")
        )
        for payload in payloads:
            if uses_file:
                seed_file.write_bytes(payload)
                cmd = [
                    tok.replace("{input_file}", str(seed_file))
                    .replace("{input}", str(seed_file))
                    .replace("@@", str(seed_file))
                    for tok in tokens
                ]
                stdin_data = None
            else:
                cmd = list(tokens)
                stdin_data = payload
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=str(wt),
                    env=env,
                    input=stdin_data,
                    capture_output=True,
                    timeout=5.0,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            combined = (
                proc.stdout.decode("utf-8", errors="replace")
                + "\n"
                + proc.stderr.decode("utf-8", errors="replace")
            )
            sig = parse_crash_signature(combined, proc.returncode)
            if sig is None:
                continue
            existing = crashes_by_hash.get(sig.stack_hash)
            if existing is None or len(payload) < len(existing["input_bytes"]):
                crashes_by_hash[sig.stack_hash] = {
                    "stack_hash": sig.stack_hash,
                    "signature": sig,
                    "kind": sig.kind,
                    "input_bytes": payload,
                    "input_hex": payload.hex(),
                    "returncode": proc.returncode,
                    "entrypoint": tokens[0],
                    "stderr_excerpt": combined[-1200:],
                }
    return list(crashes_by_hash.values())
