"""Zero-dependency `@VISITED` / `@UNREACHED` line-coverage and sanitizer slice probe.

Executes exploratory commands or micro-drivers inside an isolated `repro/slot-<k>`
worktree (never mutating `target_dir`), collects exact per-line hit counts via:
- Python 3.11+ `sys.settrace` (`sitecustomize.py` chaining `repro/helpers/sitecustomize.py`
  first so `AJAR_BLOCK_EXTERNAL_NET=1` loopback socket isolation stays enforced), or
- Stock GCC `gcov --json-format --stdout -b` across `slot_dir.rglob("*.gcda")`
  (handling both `sub/foo.gcda` and `prog-foo.gcda` single-step object naming),
and renders compact `@VISITED` / `@UNREACHED` annotations plus ASan/UBSan crash frames.
"""

from __future__ import annotations

import ast
import fcntl
import gzip
import json
import os
import pathlib
import re
import shutil
import sqlite3
import subprocess
import types
from typing import Any

from ajar import EXIT_USER_ERROR
from ajar.db import AjarError, record_coverage_span
from ajar.redact import scrub_json_value, scrub_text, scrubbed_subprocess_env
from ajar.repro_helpers import ensure_helpers_runtime
from ajar.repro_source import (
    _acquire_slot,
    _bump_files_mtime,
    _clean_slot_preserving_objects,
    _clear_stale_slot_git_locks,
    _detect_build_or_env_failure,
    _neutralize_python_pth_escapes,
    _prepare_slot_worktree,
    _run_shell_in_slot,
    init_source_mirror,
    resolve_local_build_cache_dir,
)
from ajar.store import assert_run_mutable, immediate_tx, log_event, utc_now_iso

VALID_SLICE_TRACERS: tuple[str, ...] = ("auto", "python", "gcov", "none")
PYTHON_SOURCE_EXTS: frozenset[str] = frozenset({".py", ".pyw"})
GCOV_SOURCE_EXTS: frozenset[str] = frozenset({".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh", ".inc"})

_LOCUS_SPAN_RE = re.compile(r"^(\d+)(?:-(\d+))?$")
_GUARD_KEYWORD_RE = re.compile(r"\b(?:if|elif|switch|case|while|for)\b|\?")
_C_BRACE_OR_COMMENT_RE = re.compile(r"^(?:[{};]+|//.*|/\*.*\*\/|\*.*)$")

_ASAN_HEADER_RE = re.compile(r"ERROR:\s*(AddressSanitizer|LeakSanitizer):\s*([A-Za-z0-9_.-]+)")
_TSAN_MSAN_RE = re.compile(r"WARNING:\s*(ThreadSanitizer|MemorySanitizer):\s*([^\n(]+)")
_UBSAN_LINE_RE = re.compile(r"([^\s:][^:\n]*):(\d+)(?::\d+)?:\s*runtime error:\s*([^\n]+)")
_SAN_FRAME_RE = re.compile(
    r"^\s*#(\d+)\s+0x[0-9a-fA-F]+\s+in\s+([^\s]+)\s+([^\s():]+):(\d+)(?::\d+)?",
    re.MULTILINE,
)

_PY_TRACER_SITECUSTOMIZE = '''"""Chained Ajar slice-probe Python line-coverage collector."""

from __future__ import annotations

import atexit
import json
import os
import pathlib
import sys
import threading
from types import FrameType
from typing import Any

# 1. Chain `repro/helpers/sitecustomize.py` FIRST so `AJAR_BLOCK_EXTERNAL_NET=1`
#    loopback socket enforcement remains 100% active before any user code runs.
_helpers_dir = os.environ.get("AJAR_HELPERS_DIR", "").strip()
if _helpers_dir:
    _helper_sc = pathlib.Path(_helpers_dir) / "sitecustomize.py"
    if _helper_sc.is_file():
        exec(compile(_helper_sc.read_bytes(), str(_helper_sc), "exec"), globals())

# 2. Register zero-dependency `sys.settrace` line recorder for files under `slot_dir`.
if os.environ.get("AJAR_SLICE_TRACE_ACTIVE") == "1":
    _slot_env = os.environ.get("AJAR_SLICE_SLOT_REAL", "").strip()
    _out_env = os.environ.get("AJAR_SLICE_TRACE_OUT", "").strip()
    if _slot_env and _out_env:
        _slot_real = os.path.realpath(_slot_env)
        _slot_prefix = _slot_real if _slot_real.endswith(os.sep) else (_slot_real + os.sep)
        _file_cache: dict[str, str | None] = {}
        _hits: dict[str, dict[int, int]] = {}

        def _resolve_in_slot(co_filename: str) -> str | None:
            if co_filename in _file_cache:
                return _file_cache[co_filename]
            if not co_filename or co_filename.startswith("<"):
                _file_cache[co_filename] = None
                return None
            try:
                rp = os.path.realpath(co_filename)
            except OSError:
                _file_cache[co_filename] = None
                return None
            if rp == _slot_real or rp.startswith(_slot_prefix):
                rel = os.path.relpath(rp, _slot_real).replace(os.sep, "/")
                _file_cache[co_filename] = rel
                return rel
            _file_cache[co_filename] = None
            return None

        def _make_local_tracer(file_hits: dict[int, int]) -> Any:
            def _local_trace(frame: FrameType, event: str, _arg: Any) -> Any:
                if event == "line":
                    ln = frame.f_lineno
                    file_hits[ln] = file_hits.get(ln, 0) + 1
                return _local_trace

            return _local_trace

        def _global_trace(frame: FrameType, event: str, _arg: Any) -> Any:
            if event != "call":
                return None
            rel = _resolve_in_slot(frame.f_code.co_filename)
            if rel is None:
                return None
            bucket = _hits.setdefault(rel, {})
            return _make_local_tracer(bucket)

        def _dump_pytrace() -> None:
            if not _hits:
                return
            try:
                out_dir = pathlib.Path(_out_env)
                out_dir.mkdir(parents=True, exist_ok=True)
                payload = {
                    "pid": os.getpid(),
                    "files": {
                        rel: {str(ln): int(cnt) for ln, cnt in sorted(fmap.items())}
                        for rel, fmap in sorted(_hits.items())
                    },
                }
                nonce = os.urandom(4).hex()
                tmp_file = out_dir / f".pytrace-{os.getpid()}-{nonce}.tmp"
                dst_file = out_dir / f"pytrace-{os.getpid()}-{nonce}.json"
                tmp_file.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
                os.replace(tmp_file, dst_file)
            except OSError:
                pass

        atexit.register(_dump_pytrace)
        threading.settrace(_global_trace)  # type: ignore[arg-type]
        sys.settrace(_global_trace)
'''

_GCOV_FLUSH_HEADER_C = """#ifndef AJAR_GCOV_FLUSH_H
#define AJAR_GCOV_FLUSH_H
#if defined(__GNUC__) && !defined(__clang__)
#include <signal.h>
#ifdef __cplusplus
extern "C" {
#endif
extern void __gcov_dump(void);
#ifdef __SANITIZE_ADDRESS__
extern void __sanitizer_set_death_callback(void (*callback)(void));
#endif
#ifdef __cplusplus
}
#endif
static volatile sig_atomic_t _ajar_gcov_dumped = 0;
__attribute__((unused)) static void _ajar_gcov_do_dump(void) {
    if (!_ajar_gcov_dumped) {
        _ajar_gcov_dumped = 1;
        __gcov_dump();
    }
}
__attribute__((unused)) static void _ajar_gcov_sig_handler(int sig) {
    _ajar_gcov_do_dump();
    signal(sig, SIG_DFL);
    raise(sig);
}
__attribute__((constructor, unused)) static void _ajar_init_gcov_flush(void) {
#ifdef __SANITIZE_ADDRESS__
    __sanitizer_set_death_callback(_ajar_gcov_do_dump);
#endif
    signal(SIGABRT, _ajar_gcov_sig_handler);
}
#endif
#endif
"""


def _parse_focus_locus_spec(focus_locus: str) -> tuple[str, int | None, int | None]:
    raw = (focus_locus or "").strip()
    if not raw:
        raise AjarError("`focus_locus` must be a non-empty `<file[:start[-end]]>` path.", EXIT_USER_ERROR)
    raw_file, sep, raw_span = raw.partition(":")
    clean_raw = raw_file.strip()
    if not clean_raw or clean_raw.startswith("/") or "\\" in clean_raw:
        raise AjarError(f"Invalid relative file path in `focus_locus`: {focus_locus!r}", EXIT_USER_ERROR)
    if re.match(r"^[A-Za-z]:", clean_raw):
        raise AjarError(f"Drive-prefixed path forbidden in `focus_locus`: {focus_locus!r}", EXIT_USER_ERROR)
    norm_rel = clean_raw.lstrip("./")
    p_parts = pathlib.PurePosixPath(norm_rel).parts
    if not p_parts or "." in p_parts or ".." in p_parts:
        raise AjarError(f"Path traversal forbidden in `focus_locus`: {focus_locus!r}", EXIT_USER_ERROR)
    rel_posix = "/".join(p_parts)

    if not sep:
        return (rel_posix, None, None)
    span_str = raw_span.strip()
    m = _LOCUS_SPAN_RE.match(span_str)
    if m is None:
        raise AjarError(
            f"Invalid line span in `focus_locus` {focus_locus!r}; expected `<file>`, `<file>:<line>`, or `<file>:<start>-<end>`.",
            EXIT_USER_ERROR,
        )
    start_ln = int(m.group(1))
    end_ln = int(m.group(2)) if m.group(2) is not None else start_ln
    if start_ln < 1 or end_ln < start_ln:
        raise AjarError(f"Invalid line range {start_ln}..{end_ln} in `focus_locus` {focus_locus!r}.", EXIT_USER_ERROR)
    return (rel_posix, start_ln, end_ln)


def _compute_display_window(
    *,
    total_lines: int,
    focus_start: int | None,
    focus_end: int | None,
    context_lines: int,
    max_rendered_lines: int,
) -> tuple[int, int]:
    cap = max(1, min(60, int(max_rendered_lines)))
    if total_lines <= 0:
        return (1, 1)
    if focus_start is None or focus_end is None:
        return (1, min(total_lines, cap))
    if focus_start > total_lines:
        raise AjarError(
            f"`focus_locus` start line {focus_start} exceeds file length ({total_lines} lines).",
            EXIT_USER_ERROR,
        )
    clamped_end = min(total_lines, focus_end)
    ctx = max(0, int(context_lines))
    win_start = max(1, focus_start - ctx)
    win_end = min(total_lines, clamped_end + ctx)
    if (win_end - win_start + 1) > cap:
        mid = (focus_start + clamped_end) // 2
        half = cap // 2
        win_start = max(1, mid - half)
        win_end = min(total_lines, win_start + cap - 1)
        win_start = max(1, win_end - cap + 1)
    return (win_start, win_end)


def _purge_gcov_artifacts(slot_dir: pathlib.Path) -> int:
    """Delete stale `*.gcda`, `*.gcno`, and `*.gcov*` files across `slot_dir` (including `CMakeFiles/`)."""
    if not slot_dir.is_dir() or slot_dir.is_symlink():
        return 0
    removed = 0
    for root, dirs, files in os.walk(slot_dir, followlinks=False):
        rel_root = pathlib.Path(root).relative_to(slot_dir)
        dirs[:] = [d for d in dirs if not (rel_root == pathlib.Path(".") and d == ".git")]
        for fname in files:
            low = fname.lower()
            if low.endswith((".gcda", ".gcno", ".gcov", ".gcov.json.gz")):
                fp = pathlib.Path(root) / fname
                try:
                    fp.unlink(missing_ok=True)
                    removed += 1
                except OSError:
                    pass
    return removed


def _resolve_effective_tracer(tracer: str, focus_file: str) -> str:
    clean = (tracer or "auto").strip().lower()
    if clean not in VALID_SLICE_TRACERS:
        raise AjarError(
            f"Unsupported `--tracer` {tracer!r}; choose from {list(VALID_SLICE_TRACERS)}.",
            EXIT_USER_ERROR,
        )
    if clean != "auto":
        return clean
    ext = pathlib.PurePosixPath(focus_file).suffix.lower()
    if ext in PYTHON_SOURCE_EXTS:
        return "python"
    if ext in GCOV_SOURCE_EXTS:
        return "gcov"
    return "none"


def _python_executable_lines(source_text: str, filename: str) -> tuple[set[int], set[int]]:
    """Return `(executable_lines, docstring_only_lines)` using Python 3.11+ PEP 626 `co_lines()`."""
    docstring_lines: set[int] = set()
    try:
        tree = ast.parse(source_text, filename=filename)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
                first_stmt = node.body[0]
                if (
                    isinstance(first_stmt, ast.Expr)
                    and isinstance(first_stmt.value, ast.Constant)
                    and isinstance(first_stmt.value.value, str)
                ):
                    end_ln = getattr(first_stmt, "end_lineno", first_stmt.lineno) or first_stmt.lineno
                    for ln in range(first_stmt.lineno, end_ln + 1):
                        docstring_lines.add(ln)
        code_obj = compile(source_text, filename, "exec")
    except SyntaxError:
        fallback: set[int] = set()
        for idx, raw_ln in enumerate(source_text.splitlines(), start=1):
            st = raw_ln.strip()
            if not st or st.startswith("#") or st in ("else:", "try:", "finally:", ")", "]", "}"):
                continue
            fallback.add(idx)
        return (fallback, set())

    def _walk_code(co: types.CodeType) -> set[int]:
        lines = {int(ln) for _s, _e, ln in co.co_lines() if ln is not None and ln > 0}
        for const in co.co_consts:
            if isinstance(const, types.CodeType):
                lines |= _walk_code(const)
        return lines

    exec_set = _walk_code(code_obj)
    return (exec_set, docstring_lines)


def _collect_python_coverage(
    trace_out_dir: pathlib.Path,
    focus_file: str,
) -> tuple[bool, dict[int, int]]:
    if not trace_out_dir.is_dir():
        return (False, {})
    trace_files = sorted(p for p in trace_out_dir.glob("pytrace-*.json") if p.is_file() and not p.is_symlink())
    if not trace_files:
        return (False, {})

    line_hits: dict[int, int] = {}
    saw_any_payload = False
    focus_name = pathlib.PurePosixPath(focus_file).name
    all_seen_files: set[str] = set()
    by_rel: dict[str, dict[int, int]] = {}

    for tf in trace_files:
        try:
            obj = json.loads(tf.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(obj, dict):
            continue
        files_map = obj.get("files")
        if not isinstance(files_map, dict):
            continue
        saw_any_payload = True
        for rel_k, hits_obj in files_map.items():
            if not isinstance(hits_obj, dict):
                continue
            norm_k = str(rel_k).strip().lstrip("./")
            all_seen_files.add(norm_k)
            dst = by_rel.setdefault(norm_k, {})
            for ln_s, cnt in hits_obj.items():
                try:
                    ln_i = int(ln_s)
                    cnt_i = int(cnt)
                except (TypeError, ValueError):
                    continue
                if ln_i >= 1 and cnt_i > 0:
                    dst[ln_i] = dst.get(ln_i, 0) + cnt_i

    if focus_file in by_rel:
        line_hits = dict(by_rel[focus_file])
        return (True, line_hits)

    basename_matches = [k for k in all_seen_files if pathlib.PurePosixPath(k).name == focus_name]
    if len(basename_matches) == 1:
        return (True, dict(by_rel[basename_matches[0]]))

    return (saw_any_payload, {})


def _normalize_gcov_entry_rel(
    raw_file: str,
    gcov_cwd: str,
    slot_real: pathlib.Path,
) -> str:
    cleaned = raw_file.strip()
    if not cleaned:
        return ""
    cand = pathlib.Path(cleaned)
    if not cand.is_absolute() and gcov_cwd:
        cand = pathlib.Path(gcov_cwd) / cand
    try:
        resolved = cand.resolve()
        return resolved.relative_to(slot_real).as_posix()
    except (OSError, ValueError):
        return cleaned.replace("\\", "/").lstrip("./")


def _gcov_file_matches_focus(
    cand_rel: str,
    focus_file: str,
    *,
    unique_basename_in_slot: bool,
) -> bool:
    if not cand_rel:
        return False
    if cand_rel == focus_file:
        return True
    if cand_rel.endswith("/" + focus_file) or focus_file.endswith("/" + cand_rel):
        return True
    if unique_basename_in_slot and pathlib.PurePosixPath(cand_rel).name == pathlib.PurePosixPath(focus_file).name:
        return True
    return False


def _parse_gcov_json_blobs(raw_stdout: bytes) -> list[dict[str, Any]]:
    if not raw_stdout:
        return []
    if raw_stdout[:2] == b"\x1f\x8b":
        try:
            text = gzip.decompress(raw_stdout).decode("utf-8", errors="replace")
        except OSError:
            text = raw_stdout.decode("utf-8", errors="replace")
    else:
        text = raw_stdout.decode("utf-8", errors="replace")

    blobs: list[dict[str, Any]] = []
    for raw_line in text.splitlines():
        st = raw_line.strip()
        if not st or not st.startswith("{"):
            continue
        try:
            parsed = json.loads(st)
            if isinstance(parsed, dict):
                blobs.append(parsed)
        except json.JSONDecodeError:
            continue
    if not blobs and text.strip().startswith("{"):
        try:
            whole = json.loads(text)
            if isinstance(whole, dict):
                blobs.append(whole)
        except json.JSONDecodeError:
            pass
    return blobs


def _collect_gcov_coverage(
    *,
    slot_dir: pathlib.Path,
    focus_file: str,
    sanitizer_crash_lines: set[int],
) -> tuple[bool, dict[int, int], dict[int, str]]:
    """Run `gcov --json-format --stdout -b` over generated `*.gcda` files in `slot_dir`."""
    if shutil.which("gcov") is None:
        return (False, {}, {})

    slot_real = slot_dir.resolve()
    focus_name = pathlib.PurePosixPath(focus_file).name
    same_name_count = sum(
        1
        for p in slot_dir.rglob(focus_name)
        if p.is_file() and not p.is_symlink() and ".git" not in p.relative_to(slot_dir).parts
    )
    unique_basename = same_name_count == 1

    gcda_files = sorted(
        p.relative_to(slot_dir).as_posix()
        for p in slot_dir.rglob("*.gcda")
        if p.is_file() and not p.is_symlink() and ".git" not in p.relative_to(slot_dir).parts
    )

    using_gcno_crash_fallback = False
    target_inputs = gcda_files
    if not target_inputs and sanitizer_crash_lines:
        gcno_files = sorted(
            p.relative_to(slot_dir).as_posix()
            for p in slot_dir.rglob("*.gcno")
            if p.is_file() and not p.is_symlink() and ".git" not in p.relative_to(slot_dir).parts
        )
        if gcno_files:
            target_inputs = gcno_files
            using_gcno_crash_fallback = True

    if not target_inputs:
        return (False, {}, {})

    proc = subprocess.run(
        ["gcov", "--json-format", "--stdout", "-b", *target_inputs],
        cwd=str(slot_dir),
        capture_output=True,
        env=scrubbed_subprocess_env(),
        timeout=30,
        check=False,
    )
    blobs = _parse_gcov_json_blobs(proc.stdout)
    if not blobs:
        return (False, {}, {})

    line_hits: dict[int, int] = {}
    branch_counts: dict[int, list[int]] = {}
    matched_focus = False

    for doc in blobs:
        gcov_cwd = str(doc.get("current_working_directory") or "")
        files_arr = doc.get("files")
        if not isinstance(files_arr, list):
            continue
        for fobj in files_arr:
            if not isinstance(fobj, dict):
                continue
            cand_rel = _normalize_gcov_entry_rel(str(fobj.get("file") or ""), gcov_cwd, slot_real)
            if not _gcov_file_matches_focus(cand_rel, focus_file, unique_basename_in_slot=unique_basename):
                continue
            matched_focus = True
            lines_arr = fobj.get("lines")
            if not isinstance(lines_arr, list):
                continue
            for lobj in lines_arr:
                if not isinstance(lobj, dict):
                    continue
                try:
                    ln_no = int(lobj["line_number"])
                    cnt = max(0, int(lobj.get("count", 0)))
                except (KeyError, TypeError, ValueError):
                    continue
                if ln_no < 1:
                    continue
                line_hits[ln_no] = line_hits.get(ln_no, 0) + cnt

                raw_branches = lobj.get("branches")
                if isinstance(raw_branches, list) and len(raw_branches) >= 2:
                    b_counts = [max(0, int(b.get("count", 0))) for b in raw_branches if isinstance(b, dict)]
                    if len(b_counts) >= 2:
                        prev_b = branch_counts.get(ln_no)
                        if prev_b is None or len(prev_b) != len(b_counts):
                            branch_counts[ln_no] = b_counts
                        else:
                            branch_counts[ln_no] = [a + b for a, b in zip(prev_b, b_counts, strict=True)]

    if not matched_focus:
        return (False, {}, {})

    branch_tags: dict[int, str] = {}
    for ln_no, b_list in branch_counts.items():
        taken = sum(1 for c in b_list if c > 0)
        if 0 < taken < len(b_list):
            branch_tags[ln_no] = f"@BRANCH_PARTIAL taken={taken}/{len(b_list)}"

    if using_gcno_crash_fallback:
        for crash_ln in sorted(sanitizer_crash_lines):
            line_hits[crash_ln] = max(1, line_hits.get(crash_ln, 0))
            branch_tags[crash_ln] = "@SANITIZER_CRASH"

    return (True, line_hits, branch_tags)


def _normalize_frame_path(raw_path: str, slot_real: pathlib.Path) -> tuple[str, bool]:
    """Return `(clean_path, is_in_slot)` stripping internal `slot-<k>` paths."""
    cleaned = raw_path.strip()
    if not cleaned:
        return ("", False)
    p = pathlib.Path(cleaned)
    if p.is_absolute():
        try:
            rel = p.resolve().relative_to(slot_real).as_posix()
            return (rel, True)
        except (OSError, ValueError):
            return (p.name, False)
    norm = cleaned.replace("\\", "/").lstrip("./")
    if norm.startswith("../") or "/libsanitizer/" in norm or norm.startswith(("sysdeps/", "csu/")):
        return (pathlib.PurePosixPath(norm).name, False)
    if (slot_real / norm).exists():
        return (norm, True)
    return (norm, False)


def _extract_sanitizer_summary(
    *,
    stdout: str,
    stderr: str,
    slot_dir: pathlib.Path,
    focus_file: str,
) -> tuple[bool, dict[str, Any], set[int]]:
    """Parse ASan/LSan/TSan/MSan/UBSan diagnostics and map stack frames into repo-relative loci."""
    combined = f"{stderr or ''}\n{stdout or ''}"
    slot_real = slot_dir.resolve()
    san_kind = ""
    san_msg = ""
    ubsan_locus = ""
    focus_crash_lines: set[int] = set()

    m_asan = _ASAN_HEADER_RE.search(combined)
    if m_asan:
        san_kind = f"{m_asan.group(1)}:{m_asan.group(2)}"
        san_msg = scrub_text(m_asan.group(0).strip())

    m_ub = _UBSAN_LINE_RE.search(combined)
    if m_ub:
        ub_file, is_in_slot = _normalize_frame_path(m_ub.group(1), slot_real)
        ub_line = int(m_ub.group(2))
        if is_in_slot and ub_file:
            ubsan_locus = f"{ub_file}:{ub_line}"
            if ub_file == focus_file or pathlib.PurePosixPath(ub_file).name == pathlib.PurePosixPath(focus_file).name:
                focus_crash_lines.add(ub_line)
        if not san_kind:
            san_kind = "UndefinedBehaviorSanitizer"
            san_msg = scrub_text(f"runtime error: {m_ub.group(3).strip()}"[:240])

    if not san_kind:
        m_tm = _TSAN_MSAN_RE.search(combined)
        if m_tm:
            san_kind = f"{m_tm.group(1)}:{m_tm.group(2).strip()}"
            san_msg = scrub_text(m_tm.group(0).strip()[:240])

    if not san_kind:
        return (
            False,
            {
                "triggered": False,
                "kind": "",
                "message": "",
                "crash_locus": "",
                "frames": [],
            },
            set(),
        )

    frames: list[str] = []
    crash_locus = ""
    for fm in _SAN_FRAME_RE.finditer(combined):
        idx_s, fn_name, raw_p, ln_s = fm.group(1), fm.group(2), fm.group(3), fm.group(4)
        if fn_name.startswith(("__interceptor_", "__asan_", "__ubsan_", "_ajar_gcov_")):
            continue
        rel_p, in_slot = _normalize_frame_path(raw_p, slot_real)
        ln_i = int(ln_s)
        if in_slot and rel_p:
            loc = f"{rel_p}:{ln_i}"
            if not crash_locus:
                crash_locus = loc
            frames.append(scrub_text(f"#{idx_s} {fn_name} at {loc}"))
            if rel_p == focus_file or pathlib.PurePosixPath(rel_p).name == pathlib.PurePosixPath(focus_file).name:
                focus_crash_lines.add(ln_i)
            if len(frames) >= 8:
                break

    if not crash_locus and ubsan_locus:
        crash_locus = ubsan_locus

    summary = {
        "triggered": True,
        "kind": scrub_text(san_kind),
        "message": san_msg,
        "crash_locus": scrub_text(crash_locus),
        "frames": frames,
    }
    return (True, summary, focus_crash_lines)


def _render_annotated_slice(
    *,
    focus_file: str,
    file_lines: list[str],
    win_start: int,
    win_end: int,
    eff_tracer: str,
    cov_collected: bool,
    line_hits: dict[int, int],
    branch_tags: dict[int, str],
    py_exec_lines: set[int],
    py_docstring_lines: set[int],
    san_triggered: bool,
    san_summary: dict[str, Any],
) -> tuple[str, list[int], list[int], int | None]:
    is_py = pathlib.PurePosixPath(focus_file).suffix.lower() in PYTHON_SOURCE_EXTS
    visited_in_win: list[int] = []
    unreached_in_win: list[int] = []
    first_blocker_line: int | None = None
    after_visited_guard = False
    saw_any_visited = False

    header = (
        f"# Slice Probe: {focus_file}:{win_start}-{win_end} "
        f"(tracer={eff_tracer}, coverage={'on' if cov_collected else 'off'})"
    )
    rendered_lines: list[str] = [header]

    for ln_no in range(win_start, win_end + 1):
        raw_src = file_lines[ln_no - 1] if 1 <= ln_no <= len(file_lines) else ""
        stripped = raw_src.strip()
        marker = ""

        if cov_collected:
            hits = int(line_hits.get(ln_no, 0))
            if hits > 0:
                visited_in_win.append(ln_no)
                saw_any_visited = True
                btag = branch_tags.get(ln_no, "")
                bsuffix = f", {btag}" if btag else ""
                if is_py:
                    marker = f"  # @VISITED (hits={hits}{bsuffix})"
                else:
                    marker = f"  /* @VISITED (hits={hits}{bsuffix}) */"
                if btag or _GUARD_KEYWORD_RE.search(stripped):
                    after_visited_guard = True
            else:
                is_unreached_stmt = False
                if eff_tracer == "python":
                    is_unreached_stmt = (
                        ln_no in py_exec_lines
                        and ln_no not in py_docstring_lines
                        and bool(stripped)
                        and not stripped.startswith("#")
                    )
                elif eff_tracer == "gcov":
                    is_unreached_stmt = (
                        ln_no in line_hits
                        and bool(stripped)
                        and not _C_BRACE_OR_COMMENT_RE.match(stripped)
                    )

                if is_unreached_stmt:
                    unreached_in_win.append(ln_no)
                    is_first_blocker = first_blocker_line is None and (after_visited_guard or saw_any_visited)
                    if is_first_blocker:
                        first_blocker_line = ln_no
                        if is_py:
                            marker = "  # @UNREACHED <-- FIRST_UNREACHED_AFTER_GUARD"
                        else:
                            marker = "  /* @UNREACHED <-- FIRST_UNREACHED_AFTER_GUARD */"
                    else:
                        marker = "  # @UNREACHED" if is_py else "  /* @UNREACHED */"

        rendered_lines.append(f"{ln_no:4d} | {raw_src}{marker}")

    if san_triggered:
        crash_loc = san_summary.get("crash_locus") or "unknown"
        rendered_lines.append(
            f"# @SANITIZER_TRIGGERED kind={san_summary.get('kind', '')} locus={crash_loc} msg={san_summary.get('message', '')}"
        )
        for fr in san_summary.get("frames", [])[:4]:
            rendered_lines.append(f"#   {fr}")

    return (
        scrub_text("\n".join(rendered_lines)),
        visited_in_win,
        unreached_in_win,
        first_blocker_line,
    )


def _coalesce_visited_spans(
    visited_lines: list[int],
    unreached_lines: set[int],
    *,
    max_gap: int = 3,
    max_spans: int = 32,
) -> list[tuple[int, int]]:
    """Merge nearby `@VISITED` line numbers into compact spans without crossing any `@UNREACHED` line."""
    if not visited_lines:
        return []
    ordered = sorted(set(ln for ln in visited_lines if ln >= 1))
    spans: list[tuple[int, int]] = []
    cur_s = ordered[0]
    cur_e = ordered[0]
    for ln in ordered[1:]:
        has_unreached_between = any((cur_e < u < ln) for u in unreached_lines)
        if not has_unreached_between and (ln - cur_e) <= max_gap:
            cur_e = ln
        else:
            spans.append((cur_s, cur_e))
            cur_s = ln
            cur_e = ln
    spans.append((cur_s, cur_e))
    return spans[:max_spans]


def _record_slice_probe_db_effects(
    conn: sqlite3.Connection,
    *,
    target_dir: pathlib.Path,
    worker_id: str,
    focus_locus: str,
    focus_file: str,
    slot_idx: int,
    eff_tracer: str,
    cov_collected: bool,
    all_visited_lines: list[int],
    all_unreached_lines: set[int],
    visited_in_window: list[int],
    unreached_in_window: list[int],
    first_blocker_line: int | None,
    san_triggered: bool,
    san_summary: dict[str, Any],
    exit_code: int,
    claim_id: str,
    record_coverage: bool,
    task_id: str | None,
    has_patch: bool,
) -> tuple[bool, str, list[dict[str, Any]]]:
    """Persist `slice_probed` telemetry, optional `coverage_spans`, and optional `claim_id` unblock atomically."""
    clean_claim = claim_id.strip()
    clean_worker = worker_id.strip() or "worker"
    recorded_spans: list[dict[str, Any]] = []
    claim_unblocked = False
    updated_claim_status = ""
    now_iso = utc_now_iso()

    with immediate_tx(conn):
        if clean_claim or record_coverage:
            assert_run_mutable(conn, operation="slice_probe")

        if record_coverage and all_visited_lines and not has_patch and (target_dir / focus_file).is_file():
            for s_ln, e_ln in _coalesce_visited_spans(all_visited_lines, all_unreached_lines):
                recorded_spans.append(
                    record_coverage_span(
                        conn,
                        target_dir=target_dir,
                        task_id=task_id,
                        worker_id=clean_worker,
                        rel_path=focus_file,
                        start_line=s_ln,
                        end_line=e_ln,
                    )
                )

        if clean_claim:
            clm = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (clean_claim,)).fetchone()
            if clm is None:
                raise AjarError(f"Unknown claim_id: {clean_claim}", EXIT_USER_ERROR)
            prev_status = str(clm["status"])
            prev_inst = int(clm["instrumented_since_fail"] or 0)
            conn.execute(
                """
                UPDATE claims
                SET instrumented_since_fail = 1,
                    status = CASE WHEN status = 'needs_instrumentation' THEN 'survived_falsify' ELSE status END,
                    updated_at = ?
                WHERE claim_id = ?
                """,
                (now_iso, clean_claim),
            )
            conn.execute(
                """
                UPDATE tasks
                SET status = 'done', worker_id = ?, summary = ?, updated_at = ?
                WHERE kind = 'instrument' AND status IN ('open', 'leased')
                  AND (parent_claim_id = ? OR locus = ?)
                """,
                (
                    clean_worker,
                    f"Completed slot-{slot_idx} slice-probe for {clean_claim} ({focus_locus})",
                    now_iso,
                    clean_claim,
                    str(clm["locus"]),
                ),
            )
            new_row = conn.execute("SELECT status FROM claims WHERE claim_id = ?", (clean_claim,)).fetchone()
            updated_claim_status = str(new_row["status"]) if new_row is not None else prev_status
            claim_unblocked = bool(prev_status == "needs_instrumentation" or prev_inst == 0)

        run_row = conn.execute("SELECT status FROM runs LIMIT 1").fetchone()
        if run_row is None or str(run_row["status"]) not in ("finished", "blocked"):
            log_event(
                conn,
                clean_worker,
                "slice_probed",
                clean_claim or focus_locus,
                {
                    "slot_index": slot_idx,
                    "focus_locus": focus_locus,
                    "tracer_used": eff_tracer,
                    "coverage_collected": cov_collected,
                    "visited_count": len(visited_in_window),
                    "unreached_count": len(unreached_in_window),
                    "first_blocker_line": first_blocker_line,
                    "sanitizer_triggered": san_triggered,
                    "sanitizer_kind": san_summary.get("kind", ""),
                    "exit_code": exit_code,
                    "claim_unblocked": claim_unblocked,
                    "coverage_spans_count": len(recorded_spans),
                },
            )

    return (claim_unblocked, updated_claim_status, recorded_spans)


def run_slice_probe(
    conn: sqlite3.Connection | None = None,
    *,
    run_dir: pathlib.Path,
    target_dir: pathlib.Path,
    focus_locus: str,
    cmd: str,
    build_cmd: str = "",
    patch_path: pathlib.Path | None = None,
    tracer: str = "auto",
    sanitizer_flags: bool = False,
    sanitize: bool = False,
    record_coverage: bool = False,
    task_id: str | None = None,
    context_lines: int = 8,
    max_rendered_lines: int = 60,
    claim_id: str = "",
    timeout_sec: int = 60,
    worker_id: str = "worker",
) -> dict[str, Any]:
    """Run `cmd` inside an isolated `slot-<k>` worktree and annotate `focus_locus` with `@VISITED` / `@UNREACHED`."""
    if not (cmd or "").strip():
        raise AjarError("`slice-probe` requires a non-empty `--cmd`.", EXIT_USER_ERROR)

    focus_file, focus_start, focus_end = _parse_focus_locus_spec(focus_locus)
    eff_tracer = _resolve_effective_tracer(tracer, focus_file)
    use_sanitizer = bool(sanitizer_flags or sanitize)
    clean_claim = (claim_id or "").strip()
    clean_task = (task_id or "").strip() or None

    if conn is not None and (clean_claim or record_coverage):
        assert_run_mutable(conn, operation="slice_probe")
        if clean_claim:
            clm_chk = conn.execute("SELECT claim_id FROM claims WHERE claim_id = ?", (clean_claim,)).fetchone()
            if clm_chk is None:
                raise AjarError(f"Unknown claim_id: {clean_claim}", EXIT_USER_ERROR)
        if clean_task is not None:
            tsk_chk = conn.execute("SELECT task_id FROM tasks WHERE task_id = ?", (clean_task,)).fetchone()
            if tsk_chk is None:
                raise AjarError(f"Unknown task_id: {clean_task}", EXIT_USER_ERROR)

    if patch_path is not None and not patch_path.is_file():
        raise AjarError(f"Patch file not found: {patch_path}", EXIT_USER_ERROR)

    helpers_dir = ensure_helpers_runtime(run_dir)
    mirror_dir = init_source_mirror(run_dir, target_dir)
    repro_dir = run_dir / "repro"
    slot_idx, lock_fh = _acquire_slot(repro_dir)
    slot_dir = repro_dir / f"slot-{slot_idx}"
    cache_dir = resolve_local_build_cache_dir(run_dir, f"cache-{slot_idx}")
    watermark_file = cache_dir / "watermark_ns"
    shim_dir = cache_dir / "slice_trace_shim"
    trace_out_dir = cache_dir / "slice_trace_out"
    touched: list[str] = []

    try:
        _prepare_slot_worktree(mirror_dir, slot_dir)
        _purge_gcov_artifacts(slot_dir)
        shutil.rmtree(trace_out_dir, ignore_errors=True)
        shim_dir.mkdir(parents=True, exist_ok=True)

        if patch_path is not None:
            ap = subprocess.run(
                ["git", "-C", str(slot_dir), "apply", "--whitespace=nowarn", str(patch_path.resolve())],
                capture_output=True,
                text=True,
                env=scrubbed_subprocess_env(),
                check=False,
            )
            if ap.returncode != 0:
                raise AjarError(
                    f"Patch failed `git apply`: {scrub_text(ap.stderr[:240])}",
                    EXIT_USER_ERROR,
                )
            for ln in patch_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if ln.startswith("+++ ") and ln[4:].strip() != "/dev/null":
                    touched.append(re.sub(r"^b/", "", ln[4:].split("\t", 1)[0].strip()))
            _neutralize_python_pth_escapes(slot_dir)
            _bump_files_mtime(slot_dir, touched, watermark_file)

        slot_real = slot_dir.resolve()
        focus_path = slot_dir / focus_file
        if focus_path.is_symlink():
            try:
                focus_path.resolve().relative_to(slot_real)
            except ValueError as exc:
                raise AjarError(
                    f"`focus_locus` symlink escapes slot root: {focus_file!r}",
                    EXIT_USER_ERROR,
                ) from exc
        if not focus_path.is_file():
            raise AjarError(
                f"`focus_locus` file not found inside target worktree: {focus_file!r}",
                EXIT_USER_ERROR,
            )
        try:
            focus_real = focus_path.resolve()
            focus_real.relative_to(slot_real)
        except ValueError as exc:
            raise AjarError(
                f"`focus_locus` resolves outside slot root: {focus_file!r}",
                EXIT_USER_ERROR,
            ) from exc

        source_text = focus_real.read_text(encoding="utf-8", errors="replace")
        file_lines = source_text.splitlines()
        win_start, win_end = _compute_display_window(
            total_lines=len(file_lines),
            focus_start=focus_start,
            focus_end=focus_end,
            context_lines=context_lines,
            max_rendered_lines=max_rendered_lines,
        )

        gcov_hdr_path = shim_dir / "ajar_gcov_flush.h"
        gcov_hdr_path.write_text(_GCOV_FLUSH_HEADER_C, encoding="utf-8")
        hdr_str = str(gcov_hdr_path)
        inc_flag = f" -include {hdr_str}" if not any(ch.isspace() for ch in hdr_str) else ""
        cov_cflags = f"--coverage -O0 -g{inc_flag}"
        san_cflags = "-fsanitize=address,undefined -fno-omit-frame-pointer"

        base_extra_env: dict[str, str] = {
            "AJAR_COV_CFLAGS": cov_cflags,
            "AJAR_COV_LDFLAGS": "--coverage",
            "AJAR_SAN_CFLAGS": san_cflags if use_sanitizer else "",
            "AJAR_SANITIZER_CFLAGS": (
                f"-O0 -g -fsanitize=address,undefined --coverage -fno-omit-frame-pointer{inc_flag}"
                if use_sanitizer
                else ""
            ),
            "ASAN_OPTIONS": "detect_leaks=0:symbolize=1:abort_on_error=1",
            "UBSAN_OPTIONS": "print_stacktrace=1:halt_on_error=1:abort_on_error=1",
        }
        if use_sanitizer:
            base_extra_env.update(
                {
                    "CFLAGS": f"-O0 -g -fsanitize=address,undefined --coverage -fno-omit-frame-pointer{inc_flag}",
                    "CXXFLAGS": f"-O0 -g -fsanitize=address,undefined --coverage -fno-omit-frame-pointer{inc_flag}",
                    "LDFLAGS": "-fsanitize=address,undefined --coverage",
                }
            )

        build_res: dict[str, Any] = {}
        if build_cmd.strip():
            build_res = _run_shell_in_slot(
                build_cmd.strip(),
                slot_dir=slot_dir,
                cache_dir=cache_dir,
                timeout_sec=max(int(timeout_sec), 180),
                helpers_dir=helpers_dir,
                extra_env=base_extra_env,
            )
            if build_res["exit_code"] != 0 or build_res["timed_out"]:
                err_slice = scrub_text(
                    f"# Slice Probe Build Failed ({focus_file}:{win_start}-{win_end}, exit={build_res['exit_code']})\n"
                    f"{build_res.get('stderr') or build_res.get('stdout') or ''}"[:2000]
                )
                return {
                    "ok": False,
                    "error_class": "build_or_env_error",
                    "reason": f"--build-cmd failed (exit={build_res['exit_code']})",
                    "slot_index": slot_idx,
                    "focus_locus": focus_locus,
                    "focus_file": focus_file,
                    "window": [win_start, win_end],
                    "tracer_used": eff_tracer,
                    "coverage_collected": False,
                    "visited_lines_in_window": [],
                    "unreached_lines_in_window": [],
                    "first_blocker_line": None,
                    "sanitizer_triggered": False,
                    "sanitizer_summary": {
                        "triggered": False,
                        "kind": "",
                        "message": "",
                        "crash_locus": "",
                        "frames": [],
                    },
                    "annotated_slice": err_slice,
                    "claim_unblocked": False,
                    "claim_status": "",
                    "coverage_spans_recorded": [],
                    "build": build_res,
                    "result": build_res,
                }

        # Clear any `.gcda` generated during `--build-cmd` so hit counts reflect ONLY `--cmd`.
        for stale_gcda in slot_dir.rglob("*.gcda"):
            if stale_gcda.is_file() and not stale_gcda.is_symlink():
                stale_gcda.unlink(missing_ok=True)
        shutil.rmtree(trace_out_dir, ignore_errors=True)

        cmd_extra_env = dict(base_extra_env)
        if eff_tracer == "python":
            trace_out_dir.mkdir(parents=True, exist_ok=True)
            (shim_dir / "sitecustomize.py").write_text(_PY_TRACER_SITECUSTOMIZE, encoding="utf-8")
            cmd_extra_env.update(
                {
                    "AJAR_SLICE_TRACE_ACTIVE": "1",
                    "AJAR_SLICE_SLOT_REAL": str(slot_real),
                    "AJAR_SLICE_TRACE_OUT": str(trace_out_dir),
                    "PYTHONPATH": f"{shim_dir}{os.pathsep}{slot_dir}{os.pathsep}{helpers_dir}",
                }
            )

        run_res = _run_shell_in_slot(
            cmd,
            slot_dir=slot_dir,
            cache_dir=cache_dir,
            timeout_sec=int(timeout_sec),
            helpers_dir=helpers_dir,
            extra_env=cmd_extra_env,
        )

        san_triggered, san_summary, focus_crash_lines = _extract_sanitizer_summary(
            stdout=str(run_res.get("stdout") or ""),
            stderr=str(run_res.get("stderr") or ""),
            slot_dir=slot_dir,
            focus_file=focus_file,
        )

        cov_collected = False
        line_hits: dict[int, int] = {}
        branch_tags: dict[int, str] = {}
        py_exec_lines: set[int] = set()
        py_doc_lines: set[int] = set()

        if eff_tracer == "python":
            py_exec_lines, py_doc_lines = _python_executable_lines(source_text, focus_file)
            cov_collected, line_hits = _collect_python_coverage(trace_out_dir, focus_file)
        elif eff_tracer == "gcov":
            cov_collected, line_hits, branch_tags = _collect_gcov_coverage(
                slot_dir=slot_dir,
                focus_file=focus_file,
                sanitizer_crash_lines=focus_crash_lines if san_triggered else set(),
            )

        annotated_text, visited_in_win, unreached_in_win, first_blocker_line = _render_annotated_slice(
            focus_file=focus_file,
            file_lines=file_lines,
            win_start=win_start,
            win_end=win_end,
            eff_tracer=eff_tracer,
            cov_collected=cov_collected,
            line_hits=line_hits,
            branch_tags=branch_tags,
            py_exec_lines=py_exec_lines,
            py_docstring_lines=py_doc_lines,
            san_triggered=san_triggered,
            san_summary=san_summary,
        )

        all_visited = sorted(ln for ln, cnt in line_hits.items() if cnt > 0)
        if eff_tracer == "python":
            all_unreached = {
                ln for ln in py_exec_lines if ln not in py_doc_lines and int(line_hits.get(ln, 0)) == 0
            }
        elif eff_tracer == "gcov":
            all_unreached = {ln for ln, cnt in line_hits.items() if cnt == 0}
        else:
            all_unreached = set()

        is_build_err = (not san_triggered) and _detect_build_or_env_failure(
            int(run_res["exit_code"]),
            str(run_res.get("stdout") or ""),
            str(run_res.get("stderr") or ""),
        )
    finally:
        try:
            shutil.rmtree(trace_out_dir, ignore_errors=True)
            if (slot_dir / ".git").exists():
                _clear_stale_slot_git_locks(slot_dir)
                _purge_gcov_artifacts(slot_dir)
                subprocess.run(["git", "-C", str(slot_dir), "reset", "--hard", "HEAD"], capture_output=True, check=False)
                _clean_slot_preserving_objects(slot_dir, check=False)
                if touched:
                    _bump_files_mtime(slot_dir, touched, watermark_file)
        finally:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)
            lock_fh.close()

    claim_unblocked = False
    updated_claim_status = ""
    recorded_spans: list[dict[str, Any]] = []
    if conn is not None:
        claim_unblocked, updated_claim_status, recorded_spans = _record_slice_probe_db_effects(
            conn,
            target_dir=target_dir,
            worker_id=worker_id,
            focus_locus=focus_locus,
            focus_file=focus_file,
            slot_idx=slot_idx,
            eff_tracer=eff_tracer,
            cov_collected=cov_collected,
            all_visited_lines=all_visited,
            all_unreached_lines=all_unreached,
            visited_in_window=visited_in_win,
            unreached_in_window=unreached_in_win,
            first_blocker_line=first_blocker_line,
            san_triggered=san_triggered,
            san_summary=san_summary,
            exit_code=int(run_res["exit_code"]),
            claim_id=clean_claim,
            record_coverage=bool(record_coverage),
            task_id=clean_task,
            has_patch=patch_path is not None,
        )

    payload: dict[str, Any] = {
        "ok": not is_build_err,
        "error_class": "build_or_env_error" if is_build_err else "",
        "slot_index": slot_idx,
        "focus_locus": focus_locus,
        "focus_file": focus_file,
        "window": [win_start, win_end],
        "tracer_used": eff_tracer,
        "coverage_collected": cov_collected,
        "visited_lines_in_window": visited_in_win,
        "unreached_lines_in_window": unreached_in_win,
        "first_blocker_line": first_blocker_line,
        "sanitizer_triggered": san_triggered,
        "sanitizer_summary": san_summary,
        "annotated_slice": annotated_text,
        "claim_unblocked": claim_unblocked,
        "claim_status": updated_claim_status,
        "coverage_spans_recorded": recorded_spans,
        "build": build_res,
        "result": run_res,
    }
    scrubbed = scrub_json_value(payload)
    assert isinstance(scrubbed, dict)
    return scrubbed
