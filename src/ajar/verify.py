"""AJAR Ring-0 mechanical C3 verification oracle, worktree isolation, and anti-gaming guard."""

from __future__ import annotations

import ast
import asyncio
import hashlib
import inspect
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

from ajar.cli import BuildRecipe, Candidate, CrashSignature, Verdict, scrub_subprocess_env
from ajar.llm import LLMClient, LLMResponse, resolve_role_model

DEFAULT_MOUNT_DEPS = ("node_modules", "vendor", "lib", ".venv", "target")
HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
HEX_ADDR_RE = re.compile(r"0x[0-9a-fA-F]+")
SAN_PID_RE = re.compile(r"==\d+==")
TMP_WT_RE = re.compile(r"/[^\s:]*ajar-wt-[^/\s:]+/work/")
PY_FRAME_RE = re.compile(r'File "([^"]+)", line (\d+), in ([^\s\n]+)')
SAN_FRAME_RE = re.compile(r"#\d+\s+0x[0-9a-fA-F]+\s+in\s+([^\s]+)\s+([^\s]+)")
FORBIDDEN_BUILD_NAMES = frozenset({
    "Makefile",
    "GNUmakefile",
    "makefile",
    "CMakeLists.txt",
    "build.sh",
    "setup.py",
    "pyproject.toml",
})
FORBIDDEN_PATCH_DIRS = frozenset({".ajar", "tests", "test", "docs", "doc", "benchmarks", "benchmark"})
SRC_FILE_RE = re.compile(r"[\w./-]+\.(?:c|h|cc|cpp|hpp|py|go|rs|sol|js|ts)\b", re.IGNORECASE)
OUTPUT_TRAP_RE = re.compile(
    r"^(?:(?:std::|fmt\.|os\.|sys\.|console\.|log\.)?"
    r"(?:printf|fprintf|sprintf|snprintf|puts|fputs|putchar|print|println|eprintln|echo"
    r"|write|fflush|abort|exit|_exit|panic|__builtin_trap)\b"
    r"|pass\b|\(void\)\s*\w+|if\s*\(?\s*(?:0|false)\s*\)?|;|\{\s*\})",
    re.IGNORECASE,
)
COMMENT_LINE_RE = re.compile(r"^(?://|#|/\*|\*|\*/|--)")
EXEC_STDLIB_MODS = frozenset({
    "subprocess",
    "socket",
    "http",
    "urllib",
    "ctypes",
    "asyncio",
    "multiprocessing",
    "pty",
    "importlib",
    "ssl",
})
FILE_READ_CALLS = frozenset({"open", "Path", "PurePath", "read_text", "read_bytes", "getsource", "getline", "getlines"})
SHELL_GREP_RE = re.compile(r"\b(?:grep|egrep|fgrep|rg|ag|ack|cat|head|tail|sed|awk)\b")
SHELL_TRIVIAL_RE = re.compile(r"^(?:set|export|echo|printf|sleep|exit|false|true|test|\[)\b")
HEX_PAYLOAD_RE = re.compile(r"(?<![0-9a-fA-F])([0-9a-fA-F]{16,})(?![0-9a-fA-F])")
QUOTED_LIT_RE = re.compile(r'["\']([^"\']{12,})["\']')
PY_BIN_RE = re.compile(r"^python3?(?:\.\d+)?$")


def _run_proc(
    cmd: str | list[str],
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: int = 120,
) -> tuple[int, str]:
    shell_args = ["/bin/sh", "-c", cmd] if isinstance(cmd, str) else cmd
    proc_env = scrub_subprocess_env() if env is None else env
    proc = subprocess.Popen(
        shell_args,
        cwd=str(cwd),
        env=proc_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        start_new_session=True,
    )
    try:
        out, _ = proc.communicate(timeout=timeout)
        return (proc.returncode if proc.returncode is not None else -1), (out or "")
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        part, _ = proc.communicate()
        return 124, f"{part or ''}\n[TIMEOUT]"
    finally:
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
            proc.wait()


def _parse_gitmodules_paths(repo: Path) -> list[str]:
    gm = repo / ".gitmodules"
    if not gm.is_file():
        return []
    paths: list[str] = []
    for line in gm.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped.startswith("path") and "=" in stripped:
            _, rhs = stripped.split("=", 1)
            sub = rhs.strip().strip("/")
            if sub:
                paths.append(sub)
    return paths


@contextmanager
def clean_worktree(repo: Path, mount_deps: Sequence[str] | None = None) -> Iterator[Path]:
    """Sole Ring-0/Ring-1 entrypoint using git worktree with copytree fallback."""
    src_repo = Path(repo).resolve()
    tmp_root = Path(tempfile.mkdtemp(prefix="ajar-wt-"))
    wt = tmp_root / "work"
    used_worktree = False
    try:
        if (src_repo / ".git").exists():
            wt_cmd = ["git", "-C", str(src_repo), "worktree", "add", "--detach", "--force", str(wt), "HEAD"]
            rc, _ = _run_proc(wt_cmd, cwd=src_repo, timeout=60)
            used_worktree = rc == 0 and wt.is_dir()
        if not used_worktree:
            if wt.exists():
                shutil.rmtree(wt, ignore_errors=True)
            shutil.copytree(
                src_repo,
                wt,
                symlinks=True,
                ignore=shutil.ignore_patterns(".git", "__pycache__"),
            )
        src_build_sh = src_repo / ".ajar" / "build.sh"
        wt_build_sh = wt / ".ajar" / "build.sh"
        if src_build_sh.is_symlink() or wt_build_sh.is_symlink():
            wt_build_sh.unlink(missing_ok=True)
        elif src_build_sh.is_file():
            wt_build_sh.parent.mkdir(parents=True, exist_ok=True)
            if wt_build_sh.exists():
                wt_build_sh.unlink()
            shutil.copyfile(src_build_sh, wt_build_sh)
            os.chmod(wt_build_sh, 0o555)
        elif wt_build_sh.is_file():
            os.chmod(wt_build_sh, 0o555)
        deps_to_link = list(mount_deps if mount_deps is not None else DEFAULT_MOUNT_DEPS)
        for sub_path in _parse_gitmodules_paths(src_repo):
            if sub_path not in deps_to_link:
                deps_to_link.append(sub_path)
        for rel_dep in deps_to_link:
            src_dep = src_repo / rel_dep
            dst_dep = wt / rel_dep
            if not src_dep.exists():
                continue
            if dst_dep.is_dir() and not dst_dep.is_symlink() and not any(dst_dep.iterdir()):
                dst_dep.rmdir()
            if not dst_dep.exists() and not dst_dep.is_symlink():
                dst_dep.parent.mkdir(parents=True, exist_ok=True)
                dst_dep.symlink_to(src_dep)
        yield wt
    finally:
        if used_worktree:
            rm_cmd = ["git", "-C", str(src_repo), "worktree", "remove", "--force", str(wt)]
            _run_proc(rm_cmd, cwd=src_repo, timeout=30)
            _run_proc(["git", "-C", str(src_repo), "worktree", "prune"], cwd=src_repo, timeout=30)
        shutil.rmtree(tmp_root, ignore_errors=True)


def _strip_diff_prefix(raw: str) -> str:
    path_token = raw.split("\t", 1)[0].strip()
    if path_token in ("/dev/null", "dev/null"):
        return "/dev/null"
    if path_token.startswith(("a/", "b/")):
        return path_token[2:]
    return path_token


def _align_and_apply_hunks(wt: Path, patch_diff: str, max_drift: int = 40) -> tuple[bool, str]:
    lines = patch_diff.splitlines()
    idx = 0
    planned_writes: dict[Path, str | None] = {}
    wt_real = wt.resolve()

    while idx < len(lines):
        if not lines[idx].startswith("--- "):
            idx += 1
            continue
        old_rel = _strip_diff_prefix(lines[idx][4:])
        idx += 1
        if idx >= len(lines) or not lines[idx].startswith("+++ "):
            return False, "malformed unified diff missing +++ header"
        new_rel = _strip_diff_prefix(lines[idx][4:])
        idx += 1

        chosen_rel = old_rel if new_rel == "/dev/null" else new_rel
        target = (wt_real / chosen_rel).resolve()
        if target != wt_real and wt_real not in target.parents:
            return False, f"patch path escapes worktree: {chosen_rel}"

        if old_rel == "/dev/null":
            cur_lines: list[str] = []
        else:
            if not target.is_file():
                return False, f"missing target file: {chosen_rel}"
            cur_lines = target.read_text(encoding="utf-8", errors="replace").splitlines()

        offset = 0
        min_pos = 0
        hunk_count = 0
        while idx < len(lines) and lines[idx].startswith("@@ "):
            m = HUNK_HEADER_RE.match(lines[idx])
            if not m:
                return False, f"invalid hunk header: {lines[idx]}"
            orig_start = int(m.group(1))
            idx += 1
            hunk_count += 1
            expected: list[str] = []
            replacement: list[str] = []
            while idx < len(lines):
                hline = lines[idx]
                if hline.startswith(("@@ ", "--- ", "diff --git ")):
                    break
                if hline.startswith("\\"):
                    idx += 1
                    continue
                if hline == "":
                    expected.append("")
                    replacement.append("")
                elif hline.startswith(" "):
                    expected.append(hline[1:])
                    replacement.append(hline[1:])
                elif hline.startswith("-"):
                    expected.append(hline[1:])
                elif hline.startswith("+"):
                    replacement.append(hline[1:])
                else:
                    return False, f"unexpected hunk line: {hline}"
                idx += 1

            if not expected and not cur_lines:
                cur_lines = list(replacement)
                continue

            nominal = max(0, orig_start - 1 + offset)
            lo = max(min_pos, nominal - max_drift)
            hi = min(len(cur_lines) - len(expected), nominal + max_drift)
            matches = [
                pos
                for pos in range(lo, hi + 1)
                if cur_lines[pos : pos + len(expected)] == expected
            ]
            if not matches:
                matches = [
                    pos
                    for pos in range(lo, hi + 1)
                    if [s.rstrip() for s in cur_lines[pos : pos + len(expected)]]
                    == [e.rstrip() for e in expected]
                ]
            if len(matches) != 1:
                reason = "no match" if not matches else f"ambiguous ({len(matches)} matches)"
                return False, f"hunk align failed ({reason}) in {chosen_rel}"
            pos = matches[0]
            cur_lines = cur_lines[:pos] + replacement + cur_lines[pos + len(expected) :]
            offset += len(replacement) - len(expected)
            min_pos = pos + len(replacement)

        if hunk_count == 0:
            return False, f"no hunks parsed for {chosen_rel}"
        planned_writes[target] = None if new_rel == "/dev/null" else ("\n".join(cur_lines) + "\n")

    if not planned_writes:
        return False, "no file diffs found in patch"

    for dst, content in planned_writes.items():
        if content is None:
            if dst.exists():
                dst.unlink()
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(content, encoding="utf-8")
    return True, "applied via +-40-line unique-context hunk aligner"


def apply_patch_fuzzy(wt: Path, patch_diff: str) -> tuple[bool, str]:
    if not patch_diff or not patch_diff.strip():
        return False, "empty patch_diff"
    patch_text = patch_diff if patch_diff.endswith("\n") else (patch_diff + "\n")
    with tempfile.NamedTemporaryFile("w", suffix=".patch", encoding="utf-8", delete=False) as tf:
        tf.write(patch_text)
        patch_file = Path(tf.name)
    try:
        chk_rc, _ = _run_proc(["git", "apply", "--check", str(patch_file)], cwd=wt, timeout=20)
        if chk_rc == 0:
            app_rc, app_out = _run_proc(["git", "apply", str(patch_file)], cwd=wt, timeout=20)
            if app_rc == 0:
                return True, "applied via git apply"
            return False, f"git apply failed: {app_out.strip()}"
    finally:
        patch_file.unlink(missing_ok=True)
    return _align_and_apply_hunks(wt, patch_text, max_drift=40)


def _normalize_trace_text(raw: str) -> str:
    cleaned = TMP_WT_RE.sub("", raw)
    cleaned = SAN_PID_RE.sub("==PID==", cleaned)
    cleaned = HEX_ADDR_RE.sub("0xADDR", cleaned)
    return cleaned.strip()


def parse_crash_signature(output: str, rc: int) -> CrashSignature | None:
    text = output or ""
    lower = text.lower()
    if (
        "SyntaxError" in text
        or "ImportError" in text
        or "ModuleNotFoundError" in text
        or "command not found" in lower
    ):
        return None

    kind = ""
    if "AddressSanitizer" in text:
        kind = "ASAN"
    elif "MemorySanitizer" in text:
        kind = "MSAN"
    elif "UndefinedBehaviorSanitizer" in text:
        kind = "UBSAN"
    elif "ThreadSanitizer" in text or "DATA RACE" in text:
        kind = "TSAN"
    elif "[FAIL" in text:
        kind = "FOUNDRY_FAIL"
    elif rc != 0 and ("AssertionError" in text or "RuntimeError" in text):
        py_frames = [
            f"{Path(fp).name}:{ln}:{fn}"
            for fp, ln, fn in PY_FRAME_RE.findall(text)
            if fp not in ("<string>", "<stdin>")
        ]
        if not py_frames:
            return None
        kind = "ASSERTION_ERROR" if "AssertionError" in text else "RUNTIME_ERROR"
    elif rc in (134, -6):
        kind = "SIGABRT"
    elif rc in (139, -11):
        kind = "SIGSEGV"
    elif rc in (132, -4, 133, -5):
        kind = "SIGTRAP"
    else:
        return None

    frames: list[str] = []
    for fn, loc in SAN_FRAME_RE.findall(text):
        frames.append(_normalize_trace_text(f"{fn}@{Path(loc).name}"))
    for fp, ln, fn in PY_FRAME_RE.findall(text):
        if fp not in ("<string>", "<stdin>"):
            frames.append(f"{Path(fp).name}:{ln}:{fn}")
    if not frames:
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("[FAIL") or "Sanitizer:" in s or "DATA RACE" in s:
                frames.append(_normalize_trace_text(s)[:120])
    top_frames = frames[:5]
    summary_line = next(
        (_normalize_trace_text(ln) for ln in reversed(text.splitlines()) if ln.strip()),
        kind,
    )[:160]
    basis = f"{kind}|{'|'.join(top_frames)}" if top_frames else f"{kind}|{summary_line}"
    stack_hash = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]
    return CrashSignature(kind=kind, summary=summary_line, top_frames=top_frames, stack_hash=stack_hash)


def _split_cmd(cmd: str) -> list[str]:
    try:
        return shlex.split(cmd)
    except ValueError:
        return cmd.split()


def _norm_rel(raw: str) -> str:
    rel = raw.strip().replace("\\", "/")
    while rel.startswith("./"):
        rel = rel[2:]
    return rel


def _extract_patch_paths(patch_diff: str) -> list[str]:
    paths: list[str] = []
    for line in patch_diff.splitlines():
        if line.startswith(("--- ", "+++ ")):
            rel = _norm_rel(_strip_diff_prefix(line[4:]))
            if rel and rel != "/dev/null" and rel not in paths:
                paths.append(rel)
    return paths


def _is_repro_script_name(rel: str) -> bool:
    p = Path(rel)
    lname = p.name.lower()
    if ".ajar" in p.parts or lname.endswith((".sh", ".bash")):
        return True
    return any(tok in lname for tok in ("repro", "poc", "pov", "exploit"))


def _resolve_repro_scripts(repro_cmd: str, root: Path | None) -> list[tuple[str, Path]]:
    if root is None:
        return []
    root_real = root.resolve()
    found: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for tok in _split_cmd(repro_cmd):
        if not tok or tok.startswith("-") or "=" in tok:
            continue
        rel = _norm_rel(tok)
        if not rel or rel in seen or rel.startswith("/"):
            continue
        cand_path = (root_real / rel).resolve()
        if root_real not in cand_path.parents or not cand_path.is_file():
            continue
        if cand_path.suffix.lower() in (".sh", ".bash", ".py") or ".ajar" in Path(rel).parts:
            seen.add(rel)
            found.append((rel, cand_path))
    return found


def _check_patch_policy(cand: Candidate) -> tuple[bool, str]:
    paths = _extract_patch_paths(cand.patch_diff)
    if not paths:
        return False, "patch contains no target file paths"
    repro_toks = {_norm_rel(t) for t in _split_cmd(cand.repro_cmd)}
    for rel in paths:
        p = Path(rel)
        parts = p.parts
        lname = p.name.lower()
        if rel.startswith("/") or ".." in parts:
            return False, f"forbidden path traversal in patch: {rel}"
        if ".ajar" in parts or any(part.lower() in FORBIDDEN_PATCH_DIRS for part in parts[:-1]):
            return False, f"forbidden test/build/repro patch path: {rel}"
        if p.name in FORBIDDEN_BUILD_NAMES:
            return False, f"forbidden test/build/repro patch path: {rel}"
        is_test = (
            lname.endswith(("_test.go", "_test.py", ".t.sol"))
            or (lname.startswith("test_") and lname.endswith(".py"))
            or ".spec." in lname
            or ".test." in lname
        )
        if is_test:
            return False, f"forbidden test/build/repro patch path: {rel}"
        if rel in repro_toks and _is_repro_script_name(rel):
            return False, f"forbidden repro script patch path: {rel}"
    return True, ""


def _check_output_suppression_patch(patch_diff: str) -> tuple[bool, str]:
    rem_code: list[str] = []
    add_code: list[str] = []
    for line in patch_diff.splitlines():
        if line.startswith("-") and not line.startswith("---"):
            s = line[1:].strip()
            if s and not COMMENT_LINE_RE.match(s):
                rem_code.append(s)
        elif line.startswith("+") and not line.startswith("+++"):
            s = line[1:].strip()
            if s and not COMMENT_LINE_RE.match(s):
                add_code.append(s)
    if rem_code and all(OUTPUT_TRAP_RE.match(ln) for ln in rem_code):
        if all(OUTPUT_TRAP_RE.match(ln) for ln in add_code):
            return False, "output/trap suppression patch without root-cause fix"
    return True, ""


def _check_literal_overfit_patch(cand: Candidate) -> tuple[bool, str]:
    tokens = _split_cmd(cand.repro_cmd)
    payload_args: list[str] = []
    for idx, tok in enumerate(tokens):
        if idx == 0 and "=" not in tok:
            continue
        val = tok.split("=", 1)[1] if tok.startswith("--") and "=" in tok else tok
        if val.startswith("-") or ("=" in tok and not tok.startswith("--")):
            continue
        if len(val) >= 12 and not SRC_FILE_RE.fullmatch(val):
            payload_args.append(val)
    hex_payloads = [h.lower() for h in HEX_PAYLOAD_RE.findall(cand.repro_cmd)]
    add_lines = [
        ln[1:]
        for ln in cand.patch_diff.splitlines()
        if ln.startswith("+") and not ln.startswith("+++")
    ]
    for add_ln in add_lines:
        low_ln = add_ln.lower()
        if any(hx in low_ln for hx in hex_payloads):
            return False, "literal-overfit patch embeds repro payload"
        if any(arg in add_ln for arg in payload_args):
            return False, "literal-overfit patch embeds repro payload"
        for lit in QUOTED_LIT_RE.findall(add_ln):
            low_lit = lit.lower()
            if any(lit in arg for arg in payload_args) or any(low_lit in hx for hx in hex_payloads):
                return False, "literal-overfit patch embeds repro payload"
    return True, ""


def _extract_python_c(cmd: str) -> str | None:
    toks = _split_cmd(cmd)
    for i, tok in enumerate(toks):
        if not PY_BIN_RE.match(Path(tok).name):
            continue
        for j in range(i + 1, len(toks)):
            if toks[j] == "-c" and j + 1 < len(toks):
                return toks[j + 1]
            if toks[j].startswith("-c") and len(toks[j]) > 2:
                return toks[j][2:]
            if not toks[j].startswith("-"):
                break
    return None


def _check_python_repro_ast(
    code: str,
    patch_paths: Sequence[str],
    require_target_exec: bool,
) -> tuple[bool, str]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return True, "invalid inline python repro syntax"
    imports: set[str] = set()
    calls: set[str] = set()
    lits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add((node.module or "").split(".")[0] if node.level == 0 else "<rel>")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            lits.append(node.value)
    refs_src = any(
        SRC_FILE_RE.search(s) or any(p in s or Path(p).name in s for p in patch_paths)
        for s in lits
    )
    proc_calls = {"system", "popen", "run", "Popen", "check_output", "check_call"}
    greps_src = bool(calls & proc_calls) and any(SHELL_GREP_RE.search(s) for s in lits)
    if (bool(calls & FILE_READ_CALLS) or greps_src) and refs_src:
        return True, "python repro reads tracked source files instead of executing target"
    if require_target_exec:
        non_stdlib = {m for m in imports if m and m not in sys.stdlib_module_names}
        execs = (
            bool(non_stdlib)
            or bool(imports & EXEC_STDLIB_MODS)
            or bool(calls & {"system", "popen", "execv", "execvp", "execve", "spawnv", "fork"})
        )
        if not execs:
            return True, "static python repro neither imports nor executes target"
    return False, ""


def _is_tautological_repro(
    repro_cmd: str | Candidate,
    wt: Path | None = None,
    patch_paths: Sequence[str] = (),
) -> tuple[bool, str]:
    if isinstance(repro_cmd, Candidate):
        cmd = repro_cmd.repro_cmd.strip()
        p_paths = list(patch_paths) or _extract_patch_paths(repro_cmd.patch_diff)
    else:
        cmd = repro_cmd.strip()
        p_paths = list(patch_paths)
    if not cmd:
        return True, "empty repro_cmd"
    if re.match(r"^(?:false|/bin/false|exit\s+[1-9]\d*)$", cmd):
        return True, "trivial shell failure command"
    if re.match(r"^(?:grep|egrep|fgrep|rg|ag|ack)\b", cmd):
        return True, "static grep command is not a dynamic reproducer"
    if SHELL_GREP_RE.search(cmd) and (
        SRC_FILE_RE.search(cmd) or any(p in cmd or Path(p).name in cmd for p in p_paths)
    ):
        return True, "repro command statically reads or greps source files"
    py_code = _extract_python_c(cmd)
    if py_code is not None:
        bad, reason = _check_python_repro_ast(py_code, p_paths, require_target_exec=True)
        if bad:
            return True, reason
    for rel, spath in _resolve_repro_scripts(cmd, wt):
        body = spath.read_text(encoding="utf-8", errors="replace")
        is_repro = _is_repro_script_name(rel)
        if rel.endswith(".py"):
            other_p = p_paths if is_repro else [p for p in p_paths if _norm_rel(p) != rel]
            if is_repro or other_p:
                bad, reason = _check_python_repro_ast(body, other_p, require_target_exec=is_repro)
                if bad:
                    return True, f"repro script {rel}: {reason}"
        elif is_repro:
            active = [
                ln.strip()
                for ln in body.splitlines()
                if ln.strip() and not ln.lstrip().startswith("#")
            ]
            for ln in active:
                if SHELL_GREP_RE.search(ln) and (
                    SRC_FILE_RE.search(ln) or any(p in ln or Path(p).name in ln for p in p_paths)
                ):
                    return True, f"repro script {rel} statically greps source files"
                sub_py = _extract_python_c(ln)
                if sub_py is not None:
                    bad, reason = _check_python_repro_ast(sub_py, p_paths, require_target_exec=True)
                    if bad:
                        return True, f"repro script {rel}: {reason}"
            if active and all(SHELL_TRIVIAL_RE.match(ln) for ln in active):
                return True, f"repro script {rel} does not execute target"
    return False, ""


def _mutate_hex_repro_cmds(repro_cmd: str) -> list[str]:
    m = HEX_PAYLOAD_RE.search(repro_cmd)
    if not m or len(m.group(1)) % 2 != 0:
        return []
    raw = bytearray.fromhex(m.group(1))
    m1 = bytearray(raw)
    m1[-1] ^= 0x01
    m2 = bytearray(raw)
    if len(raw) >= 4 and raw[1] == len(raw) - 2 and raw[1] < 255:
        m2[1] += 1
        m2.append(raw[-1] ^ 0x01)
    else:
        m2[len(m2) // 2] ^= 0x01
    lo, hi = m.span(1)
    out: list[str] = []
    for buf in (m1, m2):
        cand_cmd = repro_cmd[:lo] + buf.hex() + repro_cmd[hi:]
        if cand_cmd != repro_cmd and cand_cmd not in out:
            out.append(cand_cmd)
    return out


def _collect_critic_evidence(
    repo: Path,
    wt: Path,
    cand: Candidate,
    pre_out: str,
    post_out: str,
    summary: str,
) -> dict[str, str]:
    reality_path = Path(repo) / ".ajar" / "REALITY.md"
    reality = (
        reality_path.read_text(encoding="utf-8", errors="replace")[:1500]
        if reality_path.is_file()
        else ""
    )
    scripts = _resolve_repro_scripts(cand.repro_cmd, wt) or _resolve_repro_scripts(cand.repro_cmd, repo)
    script_blocks = [
        f"Repro Script Contents ({rel}):\n{sp.read_text(encoding='utf-8', errors='replace')[:4000]}"
        for rel, sp in scripts
    ]
    return {
        "reality": reality,
        "scripts": "\n\n".join(script_blocks),
        "pre_out": pre_out[-2500:],
        "post_out": post_out[-2500:],
        "summary": summary,
    }


_STRICT_APPROVE_LINE_RE = re.compile(r"^\s*APPROVE(?:D)?(?:\s*$|\s*[:\-])")
_STRICT_REJECT_LINE_RE = re.compile(r"^\s*(?:REJECT(?:ED)?|DENY|INVALID)(?:\s*$|\s*[:\-])")


def _parse_critic_verdict(raw_text: str) -> tuple[str, str]:
    """Fail-closed Critic verdict parser: accepts only strict JSON or leading APPROVE line."""
    text = (raw_text or "").strip()
    if not text:
        return "REJECTED", "empty critic response"

    json_candidate = text
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        json_candidate = fence.group(1).strip()
    if json_candidate.startswith("{") and json_candidate.endswith("}"):
        try:
            obj = json.loads(json_candidate)
        except ValueError:
            return "REJECTED", f"malformed critic json: {text[:200]}"
        if isinstance(obj, dict):
            verdict = str(obj.get("verdict", "")).strip().upper()
            reason = str(obj.get("reason") or obj.get("notes") or text)[:240]
            if verdict in ("APPROVE", "APPROVED"):
                return "APPROVED", reason
            return "REJECTED", reason
        return "REJECTED", text[:240]

    first_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    if _STRICT_APPROVE_LINE_RE.match(first_line):
        return "APPROVED", text[:240]
    if _STRICT_REJECT_LINE_RE.match(first_line):
        return "REJECTED", text[:240]
    return "REJECTED", text[:240]


def _check_build_sh_integrity(root: Path, recipe: BuildRecipe) -> tuple[bool, str]:
    root_real = Path(root).resolve()
    build_sh = root_real / ".ajar" / "build.sh"
    if build_sh.is_symlink():
        resolved = build_sh.resolve()
        if resolved != root_real and root_real not in resolved.parents:
            return False, "build.sh symlink escapes repository"
        return False, "build.sh must not be a symlink"
    if recipe.build_script_sha256:
        if not build_sh.is_file():
            return False, "build.sh missing for pinned sha256"
        actual = hashlib.sha256(build_sh.read_bytes()).hexdigest()
        if actual != recipe.build_script_sha256:
            return False, "build.sh sha256 mismatch: tampering detected"
    return True, ""


def _invoke_critic_sync(
    llm: LLMClient,
    cand: Candidate,
    sig: CrashSignature,
    evidence: dict[str, str] | None = None,
) -> LLMResponse:
    critic_spec = resolve_role_model("critic")
    ev = evidence or {}
    sections = [
        f"Candidate ID: {cand.id}",
        (
            f"Target Metadata: severity={cand.severity} entry_span={cand.entry_span} "
            f"sink_symbol={cand.sink_symbol} build_profile={cand.build_profile}"
        ),
        f"Repro Command: {cand.repro_cmd}",
        f"Crash Signature: {sig.kind} ({sig.summary}) frames={sig.top_frames}",
        f"Mutated PoV / Control Summary: {ev.get('summary', 'none')}",
    ]
    if ev.get("reality"):
        sections.append(f"Reality Excerpt (.ajar/REALITY.md):\n{ev['reality'][:1500]}")
    if ev.get("scripts"):
        sections.append(ev["scripts"])
    sections.append(f"Pre-patch Output:\n{ev.get('pre_out', '')[-2500:]}")
    sections.append(f"Post-patch Output:\n{ev.get('post_out', '')[-2500:]}")
    sections.append(f"Patch Diff:\n{cand.patch_diff[:4000]}")
    sections.append(
        "Verify from mechanical evidence alone whether the repro triggers a genuine target "
        "defect and the patch fixes the root cause without masking symptoms. "
        'Reply ONLY with strict JSON: {"verdict": "APPROVE" | "REJECT", "reason": "..."}'
    )
    msgs = [{"role": "user", "content": "\n\n".join(sections)}]
    sys_msg = "You are an adversarial Blind Cross-Family C3 Security Critic."
    if hasattr(llm, "complete_sync"):
        return llm.complete_sync(
            msgs, role="critic", model=critic_spec, system=sys_msg, allow_drain_reserve=True
        )
    coro = llm.complete(
        msgs, role="critic", model=critic_spec, system=sys_msg, allow_drain_reserve=True
    )
    if inspect.isawaitable(coro):
        return asyncio.run(coro)
    raise TypeError("LLMClient returned non-awaitable response")


def _match_pre_failure(cand: Candidate, out: str, rc: int) -> CrashSignature | None:
    sig = parse_crash_signature(out, rc)
    if sig is not None:
        return sig
    if rc != 0 and cand.failure_oracle and cand.failure_oracle in out:
        lower = out.lower()
        if not any(
            bad in out or bad in lower
            for bad in ("SyntaxError", "ImportError", "ModuleNotFoundError", "command not found")
        ):
            digest = hashlib.sha256(cand.failure_oracle.encode("utf-8")).hexdigest()[:16]
            return CrashSignature("ORACLE_FAILURE", cand.failure_oracle, [], digest)
    return None


def verify_candidate(
    repo: Path,
    cand: Candidate,
    recipe: BuildRecipe | None = None,
    llm: LLMClient | None = None,
    runs: int = 3,
) -> Verdict:
    active_recipe = recipe
    if active_recipe is None:
        build_sh = Path(repo) / ".ajar" / "build.sh"
        script_cmd = "bash .ajar/build.sh" if build_sh.is_file() else ""
        active_recipe = BuildRecipe(profile=cand.build_profile, build_script=script_cmd)

    if cand.withdrawn:
        return Verdict(cand.id, "WITHDRAWN", "C0", 0, 0, critic_verdict="SKIPPED", notes="withdrawn")
    if active_recipe.static_only or not cand.repro_cmd.strip() or not cand.patch_diff.strip():
        return Verdict(cand.id, "UNVERIFIED", "C1", 0, 0, critic_verdict="SKIPPED", notes="static/incomplete")

    for ok, reason in (
        _check_build_sh_integrity(repo, active_recipe),
        _check_patch_policy(cand),
        _check_output_suppression_patch(cand.patch_diff),
        _check_literal_overfit_patch(cand),
    ):
        if not ok:
            return Verdict(cand.id, "REJECTED", "C0", 0, 0, critic_verdict="SKIPPED", notes=reason)
    taut, taut_reason = _is_tautological_repro(cand, repo)
    if taut:
        return Verdict(cand.id, "REJECTED", "C0", 0, 0, critic_verdict="SKIPPED", notes=taut_reason)

    req_runs = max(1, int(runs))
    run_env = scrub_subprocess_env(active_recipe.env)
    last_pre_out = ""
    last_post_out = ""
    ctrl_cmd = cand.control_cmd.strip()

    with clean_worktree(repo) as wt:
        ok_wt_build, wt_build_reason = _check_build_sh_integrity(wt, active_recipe)
        if not ok_wt_build:
            return Verdict(cand.id, "REJECTED", "C0", 0, 0, critic_verdict="SKIPPED", notes=wt_build_reason)
        if active_recipe.build_script.strip():
            b_rc, _ = _run_proc(active_recipe.build_script, cwd=wt, env=run_env, timeout=180)
            if b_rc != 0:
                return Verdict(cand.id, "REJECTED", "C0", 0, 0, notes=f"initial build failed rc={b_rc}")

        if ctrl_cmd:
            c_rc, _ = _run_proc(ctrl_cmd, cwd=wt, env=run_env, timeout=120)
            if c_rc != 0:
                return Verdict(cand.id, "REJECTED", "C0", 0, 0, notes=f"pre-patch control_cmd failed rc={c_rc}")

        pre_failed = 0
        ref_sig: CrashSignature | None = None
        for _ in range(req_runs):
            rc, out = _run_proc(cand.repro_cmd, cwd=wt, env=run_env, timeout=120)
            last_pre_out = out
            sig = _match_pre_failure(cand, out, rc)
            if sig is None:
                return Verdict(cand.id, "REJECTED", "C0", pre_failed, 0, notes="pre-patch repro did not crash")
            if cand.failure_oracle and cand.failure_oracle not in out:
                return Verdict(cand.id, "REJECTED", "C0", pre_failed, 0, notes="failure_oracle mismatch")
            if cand.sink_symbol and cand.sink_symbol not in out:
                return Verdict(
                    cand.id, "REJECTED", "C0", pre_failed, 0, asdict(sig),
                    notes=f"sink_symbol '{cand.sink_symbol}' missing from trace",
                )
            if ref_sig is None:
                ref_sig = sig
            elif sig.stack_hash != ref_sig.stack_hash:
                return Verdict(cand.id, "REJECTED", "C0", pre_failed, 0, asdict(sig), notes="flaky stack_hash")
            pre_failed += 1

        assert ref_sig is not None
        mutant_cmds = _mutate_hex_repro_cmds(cand.repro_cmd)
        confirmed_mutants: list[str] = []
        for m_cmd in mutant_cmds:
            m_rc, m_out = _run_proc(m_cmd, cwd=wt, env=run_env, timeout=120)
            if _match_pre_failure(cand, m_out, m_rc) is not None:
                confirmed_mutants.append(m_cmd)

        ok_patch, patch_note = apply_patch_fuzzy(wt, cand.patch_diff)
        if not ok_patch:
            return Verdict(cand.id, "REJECTED", "C0", pre_failed, 0, asdict(ref_sig), notes=patch_note)

        if active_recipe.build_script.strip():
            ok_rb_build, rb_reason = _check_build_sh_integrity(wt, active_recipe)
            if not ok_rb_build:
                return Verdict(
                    cand.id, "REJECTED", "C0", pre_failed, 0, asdict(ref_sig),
                    critic_verdict="SKIPPED", notes=rb_reason,
                )
            rb_rc, _ = _run_proc(active_recipe.build_script, cwd=wt, env=run_env, timeout=180)
            if rb_rc != 0:
                return Verdict(
                    cand.id, "REJECTED", "C0", pre_failed, 0, asdict(ref_sig),
                    notes=f"post-patch rebuild failed rc={rb_rc}",
                )

        post_passed = 0
        for _ in range(req_runs):
            rc, out = _run_proc(cand.repro_cmd, cwd=wt, env=run_env, timeout=120)
            last_post_out = out
            if rc != 0 or parse_crash_signature(out, rc) is not None:
                return Verdict(cand.id, "REJECTED", "C0", pre_failed, post_passed, asdict(ref_sig), notes="post-patch failed")
            if cand.failure_oracle and cand.failure_oracle in out:
                return Verdict(cand.id, "REJECTED", "C0", pre_failed, post_passed, asdict(ref_sig), notes="oracle persisted")
            post_passed += 1

        for m_cmd in confirmed_mutants:
            m_rc, m_out = _run_proc(m_cmd, cwd=wt, env=run_env, timeout=120)
            if (
                m_rc != 0
                or parse_crash_signature(m_out, m_rc) is not None
                or (cand.failure_oracle and cand.failure_oracle in m_out)
            ):
                return Verdict(
                    cand.id, "REJECTED", "C0", pre_failed, post_passed, asdict(ref_sig),
                    notes="bandaid patch: mutated PoV still fails post-patch",
                )

        if ctrl_cmd:
            c_rc, _ = _run_proc(ctrl_cmd, cwd=wt, env=run_env, timeout=120)
            if c_rc != 0:
                return Verdict(
                    cand.id, "REJECTED", "C0", pre_failed, post_passed, asdict(ref_sig),
                    notes=f"post-patch control_cmd failed rc={c_rc}",
                )

        if active_recipe.test_cmd.strip():
            t_rc, _ = _run_proc(active_recipe.test_cmd, cwd=wt, env=run_env, timeout=300)
            if t_rc != 0:
                return Verdict(
                    cand.id, "REJECTED", "C0", pre_failed, post_passed, asdict(ref_sig),
                    notes=f"regression test_cmd failed rc={t_rc}",
                )

        summary = (
            f"control_cmd={'PASS(pre+post)' if ctrl_cmd else 'none'}; "
            f"mutated_pov={len(confirmed_mutants)}/{len(mutant_cmds)} confirmed+fixed"
        )
        evidence = _collect_critic_evidence(repo, wt, cand, last_pre_out, last_post_out, summary)

    if llm is None:
        return Verdict(
            cand.id, "VERIFIED", "C2", pre_failed, post_passed, asdict(ref_sig), critic_verdict="SKIPPED"
        )

    critic_resp = _invoke_critic_sync(llm, cand, ref_sig, evidence=evidence)
    critic_verdict, critic_notes = _parse_critic_verdict(critic_resp.content)
    if critic_verdict == "APPROVED":
        return Verdict(
            cand.id, "VERIFIED", "C3", pre_failed, post_passed, asdict(ref_sig),
            critic_verdict="APPROVED", notes=critic_notes,
        )
    return Verdict(
        cand.id, "REJECTED", "C2", pre_failed, post_passed, asdict(ref_sig),
        critic_verdict="REJECTED", notes=critic_notes,
    )
