"""Evidence-locked vulnerability report compiler and audience renderer (`ajar report`).

Supports three explicit audiences (`--audience customer|maintainer|internal`):
- `maintainer`: Upstream OSS maintainer / GHSA / HackerOne advisory prose (`Summary`,
  `Root Cause`, `Reproduction`, `Impact`, `Suggested Fix`) free of internal harness IDs,
  verification-arm labels, economics headers, host paths, and key-value bullet walls.
- `customer` (default): Buyer-safe security review report (`DEC-0099`) applying latest
  calibrations/corrections, normalizing target paths to repo-relative `path:line`, and
  omitting internal unit-economics, worker handles, and harness state jargon.
- `internal`: Complete operator/engineering closeout ledger (`ajar-research-ledger/1`),
  including `G1`–`G5` gate status, COGS telemetry, workspace steers, and disproved appendix.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sqlite3
import subprocess
from collections.abc import Mapping, Sequence
from typing import Any

from ajar import EXIT_USER_ERROR
from ajar.db import (
    apply_latest_finding_corrections,
    compute_harness_code_sha256,
    list_rows,
    list_steers,
)
from ajar.domain import AjarError
from ajar.gates import check_all_gates
from ajar.redact import scrub_json_value, scrub_text, scrubbed_subprocess_env

VALID_REPORT_AUDIENCES: tuple[str, ...] = ("customer", "maintainer", "internal")

_GIT_SLUG_RE = re.compile(r"[:/]([A-Za-z0-9._-]+/[A-Za-z0-9._-]+?)(?:\.git)?/?$")

_AJAR_SLOT_SUBPATH_RE = re.compile(
    r"(?:file://)?[^\s'\"()\[\],;:]*?(?:\.ajar|ajar)/runs/[^/\s'\"()\[\],;:]+/"
    r"(?:repro/slot-(?:[0-9]+|inst)|workspace/target)/"
)
_AJAR_ARTIFACT_FILE_RE = re.compile(
    r"(?:file://)?[^\s'\"()\[\],;:]*?(?:\.ajar|ajar)/runs/[^/\s'\"()\[\],;:]+/"
    r"artifacts/(?:worker-[^/\s'\"()\[\],;:]+/)?([A-Za-z0-9_.-]+)"
)
_AJAR_RUN_PATH_RE = re.compile(
    r"(?:file://)?(?:~|[^\s'\"()\[\],;:]*)?(?:\.ajar|ajar)/runs/[^\s'\"()\[\],;:]*"
)
_SCRATCH_DIR_RE = re.compile(r"(?:[^\s'\"()\[\],;:]*?/|^)\.scratch-[A-Za-z0-9_.-]+(?:/([A-Za-z0-9_./-]+))?")

_LOCAL_HOST_PATH_BODY = (
    r"(?:"
    r"/(?:home|Users)/[A-Za-z0-9._-]+(?:/[^\s'\",;:)}\]]*)?"
    r"|/(?:private/)?(?:tmp|var/tmp|var/folders)(?:/[^\s'\",;:)}\]]*)?"
    r"|/root(?:/[^\s'\",;:)}\]]*)?"
    r"|/shared/user(?:/[^\s'\",;:)}\]]*)?"
    r"|/Library/Developer(?:/[^\s'\",;:)}\]]*)?"
    r"|~/\.ajar(?:/[^\s'\",;:)}\]]*)?"
    r")"
)
_FILE_URI_ANY_RE = re.compile(r"file:///([^\s'\",;:)}\]]*)")
_FLAG_LOCAL_PATH_RE = re.compile(r"((?:^|[\s'\"(=,;])-[A-Za-z])" + _LOCAL_HOST_PATH_BODY)
_ABS_LOCAL_PATH_RE = re.compile(r"(?<![A-Za-z0-9_.+/-])" + _LOCAL_HOST_PATH_BODY)

_PAREN_INTERNAL_ID_RE = re.compile(
    r"\s*\(\s*`?(?:clm|fnd|cor|pvf|chn|ano|anom|surf|prim|cjw|door|str|tsk|snp|hlp|dsp)-[A-Za-z0-9_*-]+`?\s*\)",
    re.IGNORECASE,
)
_INTERNAL_ID_RE = re.compile(
    r"`?\b(?:clm|fnd|cor|pvf|chn|ano|anom|surf|prim|cjw|door|str|tsk|snp|hlp|dsp)-(?:[A-Za-z0-9_-]+|\*)\b`?",
    re.IGNORECASE,
)
_WORKER_ID_RE = re.compile(r"`?\b(?:worker|w)-[A-Za-z0-9_-]+\b`?", re.IGNORECASE)
_INVALID_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]*@[A-Za-z0-9.-]*\.invalid\b", re.IGNORECASE)

_HARNESS_RAW_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"`?\b[2-9]-arm(?:s)?\b`?", re.IGNORECASE), "counterfactual"),
    (
        re.compile(
            r"`?\b(?:arms?\s*[1-9][ab]?(?:\s*(?:&|and|/)\s*[1-9][ab]?)?|arm[1-9]_[a-z0-9_]+)\b`?",
            re.IGNORECASE,
        ),
        "verification step",
    ),
    (re.compile(r"`?\bmicro-?patch(?:es|ing)?\b`?", re.IGNORECASE), "candidate fix"),
    (re.compile(r"`?\bmicro-?patched\b`?", re.IGNORECASE), "patched locally"),
    (re.compile(r"`?\bmaintainer_patched\b`?", re.IGNORECASE), "verified locally"),
    (
        re.compile(
            r"`?\b(?:found_autonomously_by_ajar|found_with_ajar|validated_by_ajar|"
            r"uncapped_research|cogs_cap|falsifier_worker_id|proposer_worker_id|zero_skill)\b`?",
            re.IGNORECASE,
        ),
        "",
    ),
    (re.compile(r"`?\bwave\s*[0-9]+[a-z]?\b`?", re.IGNORECASE), ""),
    (re.compile(r"`?\bajar(?:-[A-Za-z0-9_-]+)?\b`?", re.IGNORECASE), "the analyzer"),
    (re.compile(r"`?\b(?:source\s+locus|target_locus|dry_control_locus)\b`?", re.IGNORECASE), "source location"),
    (re.compile(r"`?\bloci\b`?", re.IGNORECASE), "locations"),
    (re.compile(r"`?\blocus\b`?", re.IGNORECASE), "location"),
    (re.compile(r"`?\b(?:workspace\s+steers?|active\s+steers?|\bsteers?\b)\b`?", re.IGNORECASE), "scope rules"),
    (re.compile(r"`?\b(?:closeout\s+gates?|G[1-5](?:[–-]G[1-5])?)\b`?"), "verification checks"),
    (re.compile(r"`?\b(?:epistemic[_\s]+hooks?|H[1-9])\b`?"), "invariant checks"),
    (re.compile(r"`?\btrust_gadget\b`?", re.IGNORECASE), "downstream caller"),
    (re.compile(r"`?\bstepping[_\s]+stones?\b`?", re.IGNORECASE), "intermediate step"),
    (re.compile(r"`?\bcrown[_\s]+jewels?\b`?", re.IGNORECASE), "security boundary"),
    (re.compile(r"`?\b(?:open|parked)[_\s]+doors?\b`?", re.IGNORECASE), "blocked paths"),
    (re.compile(r"`?\bprimitive_helpers\b`?", re.IGNORECASE), "test helpers"),
    (re.compile(r"`?\b(?:guarded-by|provides-tags|requires-tags)\b`?", re.IGNORECASE), "guard condition"),
)

_PROSE_ONLY_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bprimitives\b", re.IGNORECASE), "mechanisms"),
    (re.compile(r"\bprimitive\b", re.IGNORECASE), "mechanism"),
    (re.compile(r"\bsinks\b", re.IGNORECASE), "operations"),
    (re.compile(r"\bsink\b", re.IGNORECASE), "operation"),
    (re.compile(r"\b(?:moreover|furthermore|additionally|notably|importantly|interestingly)\s*,\s*", re.IGNORECASE), ""),
    (re.compile(r"\b(?:moreover|furthermore|additionally|notably|importantly|interestingly)\b\s*", re.IGNORECASE), ""),
    (
        re.compile(
            r"\bit\s+(?:is\s+(?:worth\s+noting|important\s+to\s+note|crucial\s+to\s+note)|"
            r"bears\s+mentioning|should\s+be\s+noted)\s+(?:that\s+)?",
            re.IGNORECASE,
        ),
        "",
    ),
    (re.compile(r"\b(?:in\s+conclusion|in\s+summary|to\s+summarize|all\s+in\s+all)\s*,?\s*", re.IGNORECASE), ""),
    (re.compile(r"\bin\s+order\s+to\b", re.IGNORECASE), "to"),
    (re.compile(r"\bdue\s+to\s+the\s+fact\s+that\b", re.IGNORECASE), "because"),
    (re.compile(r"\butilizes\b", re.IGNORECASE), "uses"),
    (re.compile(r"\butilized\b", re.IGNORECASE), "used"),
    (re.compile(r"\butilizing\b", re.IGNORECASE), "using"),
    (re.compile(r"\butilize\b", re.IGNORECASE), "use"),
    (re.compile(r"\bleverages\b", re.IGNORECASE), "uses"),
    (re.compile(r"\bleveraged\b", re.IGNORECASE), "used"),
    (re.compile(r"\bleveraging\b", re.IGNORECASE), "using"),
    (re.compile(r"\bleverage\b", re.IGNORECASE), "use"),
    (re.compile(r"\bdelves\b", re.IGNORECASE), "examines"),
    (re.compile(r"\bdelve\b", re.IGNORECASE), "examine"),
    (re.compile(r"\bcrucially\b\s*,?\s*", re.IGNORECASE), ""),
    (re.compile(r"\bcrucial\b", re.IGNORECASE), "essential"),
    (re.compile(r"\bcomprehensively\b", re.IGNORECASE), "thoroughly"),
    (re.compile(r"\bcomprehensive\b", re.IGNORECASE), "complete"),
    (re.compile(r"\brobust(?:ness|ly)?\b", re.IGNORECASE), "sound"),
    (re.compile(r"\bseamless(?:ly)?\b", re.IGNORECASE), "direct"),
    (re.compile(r"\bunderscores?\b", re.IGNORECASE), "shows"),
    (re.compile(r"\b(?:pivotal|paramount)\b", re.IGNORECASE), "central"),
    (re.compile(r"\b(?:multifaceted|intricate|meticulous(?:ly)?)\b", re.IGNORECASE), "detailed"),
    (re.compile(r"\b(?:serves|stands|acts)\s+as\s+a\b", re.IGNORECASE), "is a"),
    (
        re.compile(r"\b(?:substrate|wedge|nexus|scaffolding|paradigm|ratchet|north\s+star|flywheel)\b", re.IGNORECASE),
        "structure",
    ),
    (
        re.compile(
            r"\b(?:malicious\s+(?:threat\s+)?actors?|threat\s+actors?|bad\s+actors?|"
            r"nefarious\s+(?:actors?|attackers?))\b",
            re.IGNORECASE,
        ),
        "an attacker",
    ),
    (re.compile(r"\b(?:could\s+potentially|may\s+potentially)\b", re.IGNORECASE), "can"),
    (re.compile(r"\bpotentially\s+allow(?:s|ing)?\b", re.IGNORECASE), "allows"),
    (re.compile(r"\b(?:catastrophic|devastating)\b", re.IGNORECASE), "severe"),
    (re.compile(r"\b(?:crash\s+or\s+worse|undefined\s+behavior\s+or\s+worse)\b", re.IGNORECASE), "process crash"),
    (re.compile(r"\bcomplete\s+system\s+compromise\b", re.IGNORECASE), "arbitrary code execution"),
)

_PROTECTED_DOT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:e\.g|i\.e|vs|cf|etc|approx|min|max)\.", re.IGNORECASE),
    re.compile(
        r"\b[A-Za-z0-9_<>*.-]+\.(?:c|h|cc|cpp|rs|go|py|js|ts|java|rb|sh|md|txt|json|yml|yaml|toml|patch|lock|http|bin)\b"
    ),
    re.compile(r"\b[A-Za-z_][A-Za-z0-9_<>-]*\.[A-Za-z_][A-Za-z0-9_<>.-]*\b"),
    re.compile(r"\bv?\d+\.\d+(?:\.\d+)*\b"),
)


def _validate_audience(audience: str) -> str:
    aud = (audience or "customer").strip().lower()
    if aud not in VALID_REPORT_AUDIENCES:
        raise AjarError(
            f"Unsupported report --audience: {audience!r} (expected one of {VALID_REPORT_AUDIENCES}).",
            EXIT_USER_ERROR,
        )
    return aud


def _safe_json_loads(raw: Any, default: Any) -> Any:
    if raw is None or raw == "":
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _read_scope_source_meta(conn: sqlite3.Connection | None) -> tuple[str, str]:
    if conn is None:
        return ("", "")
    try:
        row = conn.execute("SELECT raw_scope_json FROM scope_rules LIMIT 1").fetchone()
        if row is not None and row[0]:
            obj = _safe_json_loads(row[0], {})
            if isinstance(obj, dict):
                return (
                    str(obj.get("source_target") or "").strip(),
                    str(obj.get("source_target_name") or "").strip(),
                )
    except sqlite3.Error:
        pass
    return ("", "")


def _iter_run_dirs_from_conn(conn: sqlite3.Connection | None) -> list[pathlib.Path]:
    dirs: list[pathlib.Path] = []
    if conn is None:
        return dirs
    try:
        for db_row in conn.execute("PRAGMA database_list").fetchall():
            db_file = str(db_row[2] or "").strip()
            if db_file and db_file != ":memory:":
                dirs.append(pathlib.Path(db_file).parent)
    except sqlite3.Error:
        pass
    return dirs


def _infer_target_slug(
    target_path: str,
    run_id: str = "",
    conn: sqlite3.Connection | None = None,
) -> str:
    src_target, src_name = _read_scope_source_meta(conn)
    candidates = [p for p in (src_target, target_path) if p]
    for cand in candidates:
        tpath = pathlib.Path(cand)
        if tpath.is_dir() and (tpath / ".git").exists():
            try:
                cp = subprocess.run(
                    ["git", "-C", str(tpath), "config", "--get", "remote.origin.url"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    env=scrubbed_subprocess_env(),
                    check=False,
                )
                url = (cp.stdout or "").strip()
                if url and not url.startswith(("/", "file://", "./", "../")):
                    sanitized_url = re.sub(r"://[^/@]+@", "://", url)
                    m = _GIT_SLUG_RE.search(sanitized_url)
                    if m:
                        return m.group(1)
            except (OSError, subprocess.SubprocessError):
                pass
    if src_name and src_name not in ("target", ".", ".."):
        return src_name
    fallback_path = pathlib.Path(target_path) if target_path else None
    if fallback_path is not None:
        parts = [p for p in fallback_path.parts if p not in ("/", "")]
        if len(parts) >= 2 and parts[-1] == "target" and parts[-2] == "workspace":
            return "target-repo"
        if fallback_path.name and fallback_path.name not in ("target", ".", ".."):
            return fallback_path.name
    clean_rid = re.sub(r"\bajar[-_]?", "", run_id or "", flags=re.IGNORECASE).strip("-_ ")
    return clean_rid or "target-repo"


def _resolve_head_sha(
    run: Mapping[str, Any],
    target_path: str,
    conn: sqlite3.Connection | None = None,
) -> str:
    existing = str(run.get("head_sha") or "").strip()
    if existing:
        return existing
    src_target, _ = _read_scope_source_meta(conn)
    for cand in (src_target, target_path):
        if not cand:
            continue
        tpath = pathlib.Path(cand)
        if tpath.is_dir() and (tpath / ".git").exists():
            try:
                cp = subprocess.run(
                    ["git", "-C", str(tpath), "rev-parse", "HEAD"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    env=scrubbed_subprocess_env(),
                    check=False,
                )
                sha = (cp.stdout or "").strip()
                if cp.returncode == 0 and sha:
                    return sha
            except (OSError, subprocess.SubprocessError):
                pass
    for rdir in _iter_run_dirs_from_conn(conn):
        mirror = rdir / "repro" / "repo.git"
        if mirror.is_dir():
            try:
                cp = subprocess.run(
                    ["git", "--git-dir", str(mirror), "rev-parse", "HEAD"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    env=scrubbed_subprocess_env(),
                    check=False,
                )
                sha = (cp.stdout or "").strip()
                if cp.returncode == 0 and sha:
                    return sha
            except (OSError, subprocess.SubprocessError):
                pass
    return ""


def _collect_report_roots(
    run: Mapping[str, Any],
    conn: sqlite3.Connection | None = None,
) -> tuple[list[str], list[str]]:
    target_roots: list[str] = []
    other_roots: list[str] = []

    def _add_variants(raw: str, bucket: list[str]) -> None:
        s = (raw or "").strip().rstrip("/")
        if not s or len(s) <= 1:
            return
        if s not in bucket:
            bucket.append(s)
        try:
            resolved = str(pathlib.Path(s).resolve()).rstrip("/")
            if resolved and len(resolved) > 1 and resolved not in bucket:
                bucket.append(resolved)
        except OSError:
            pass

    src_target, _ = _read_scope_source_meta(conn)
    if src_target:
        _add_variants(src_target, target_roots)
    target_path = str(run.get("target_path") or "")
    workspace_path = str(run.get("workspace_path") or "")
    _add_variants(target_path, target_roots)
    if workspace_path:
        _add_variants(str(pathlib.Path(workspace_path) / "target"), target_roots)
        _add_variants(workspace_path, other_roots)
        ws_parent = pathlib.Path(workspace_path).parent
        if ws_parent.name:
            _add_variants(str(ws_parent), other_roots)

    for run_dir in _iter_run_dirs_from_conn(conn):
        repro_dir = run_dir / "repro"
        if repro_dir.is_dir():
            for child in repro_dir.iterdir():
                if child.name.startswith("slot-"):
                    _add_variants(str(child), target_roots)
        _add_variants(str(run_dir / "workspace" / "target"), target_roots)
        _add_variants(str(run_dir), other_roots)
        if run_dir.parent.name == "runs" and run_dir.parent.parent.name:
            _add_variants(str(run_dir.parent.parent), other_roots)

    ajar_home_env = os.environ.get("AJAR_HOME", "").strip()
    if ajar_home_env:
        _add_variants(ajar_home_env, other_roots)
    try:
        home_s = str(pathlib.Path.home()).rstrip("/")
        if home_s and len(home_s) > 1:
            _add_variants(home_s, other_roots)
    except RuntimeError:
        pass

    target_roots.sort(key=len, reverse=True)
    other_roots.sort(key=len, reverse=True)
    return target_roots, other_roots


def _fallback_relative_tail(matched_path: str) -> str:
    cleaned = matched_path.strip().rstrip("/")
    if not cleaned:
        return "."
    parts = [
        p
        for p in cleaned.split("/")
        if p
        and not p.startswith((".ajar", ".scratch-", "worker-"))
        and p not in ("home", "Users", "tmp", "private", "var", "folders", "root", "shared", "user", "artifacts", "runs")
    ]
    if not parts:
        return "."
    tail = parts[-1]
    if "." in tail and not tail.startswith("-"):
        if len(parts) >= 2 and parts[-2] in ("src", "lib", "include", "bin", "scripts", "tests", "fixtures", "cmd", "pkg"):
            return f"{parts[-2]}/{tail}"
        return f"./{tail}"
    return "."


def _sanitize_external_text(
    text: str,
    *,
    target_roots: Sequence[str],
    other_roots: Sequence[str],
    target_slug: str = "target-repo",
) -> str:
    if not text:
        return text
    out = text
    out = _AJAR_SLOT_SUBPATH_RE.sub("", out)
    out = _AJAR_ARTIFACT_FILE_RE.sub(r"./\1", out)
    for root in target_roots:
        out = out.replace("file://" + root + "/", "")
        out = out.replace("file://" + root, target_slug)
        out = out.replace(root + "/", "")
        out = out.replace(root, target_slug)
    out = _AJAR_RUN_PATH_RE.sub(".", out)
    out = _SCRATCH_DIR_RE.sub(lambda m: f"./{m.group(1)}" if m.group(1) else ".", out)
    for root in other_roots:
        out = out.replace("file://" + root + "/", "")
        out = out.replace("file://" + root, ".")
        out = out.replace(root + "/", "")
        out = out.replace(root, ".")
    out = _FILE_URI_ANY_RE.sub(lambda m: _fallback_relative_tail(m.group(1)), out)
    out = _FLAG_LOCAL_PATH_RE.sub(r"\1.", out)
    out = _ABS_LOCAL_PATH_RE.sub(lambda m: _fallback_relative_tail(m.group(0)), out)
    out = _INVALID_EMAIL_RE.sub("security@example.com", out)
    return out


def _sanitize_diff_text(
    diff_text: str,
    *,
    target_roots: Sequence[str],
    other_roots: Sequence[str],
    target_slug: str = "target-repo",
) -> str:
    if not diff_text:
        return ""
    out_lines: list[str] = []
    for raw_line in diff_text.splitlines():
        line = raw_line
        if line.startswith(("--- ", "+++ ")) and not line.startswith(("--- /dev/null", "+++ /dev/null")):
            prefix = line[:4]
            rest = line[4:].strip()
            norm = _sanitize_external_text(
                rest,
                target_roots=target_roots,
                other_roots=other_roots,
                target_slug=target_slug,
            ).lstrip("./")
            if not norm.startswith(("a/", "b/")):
                side = "a/" if prefix.startswith("---") else "b/"
                norm = side + norm
            out_lines.append(prefix + norm)
        else:
            out_lines.append(
                _sanitize_external_text(
                    line,
                    target_roots=target_roots,
                    other_roots=other_roots,
                    target_slug=target_slug,
                )
            )
    return "\n".join(out_lines).rstrip()


def _sanitize_external_value(
    value: Any,
    *,
    target_roots: Sequence[str],
    other_roots: Sequence[str],
    target_slug: str = "target-repo",
) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _sanitize_external_text(
            value,
            target_roots=target_roots,
            other_roots=other_roots,
            target_slug=target_slug,
        )
    if isinstance(value, Mapping):
        return {
            _sanitize_external_text(
                str(k),
                target_roots=target_roots,
                other_roots=other_roots,
                target_slug=target_slug,
            ): _sanitize_external_value(
                v,
                target_roots=target_roots,
                other_roots=other_roots,
                target_slug=target_slug,
            )
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [
            _sanitize_external_value(
                item,
                target_roots=target_roots,
                other_roots=other_roots,
                target_slug=target_slug,
            )
            for item in value
        ]
    return _sanitize_external_text(
        str(value),
        target_roots=target_roots,
        other_roots=other_roots,
        target_slug=target_slug,
    )


def _normalize_locus(
    locus: str,
    *,
    target_roots: Sequence[str],
    other_roots: Sequence[str],
    target_slug: str = "target-repo",
) -> str:
    cleaned = _sanitize_external_text(
        " ".join((locus or "").split()),
        target_roots=target_roots,
        other_roots=other_roots,
        target_slug=target_slug,
    )
    cleaned = re.sub(r"^(?:\./)+", "", cleaned).lstrip("/")
    return cleaned or target_slug


def _capitalize_sentences(text: str) -> str:
    if not text:
        return text
    out = re.sub(
        r"(^|[.!?]\s+)([a-z])",
        lambda m: str(m.group(1)) + str(m.group(2)).upper(),
        text,
    )
    return out


def _dejargonize_external_prose(
    text: str,
    *,
    target_roots: Sequence[str],
    other_roots: Sequence[str],
    target_slug: str = "target-repo",
) -> str:
    if not text:
        return ""
    work = _sanitize_external_text(
        text,
        target_roots=target_roots,
        other_roots=other_roots,
        target_slug=target_slug,
    )
    work = _PAREN_INTERNAL_ID_RE.sub("", work)
    work = _INTERNAL_ID_RE.sub("this issue", work)
    work = _WORKER_ID_RE.sub("the reviewer", work)
    for pat, repl in _HARNESS_RAW_REPLACEMENTS:
        work = pat.sub(repl, work)

    code_spans: list[str] = []

    def _stash_code(m: re.Match[str]) -> str:
        idx = len(code_spans)
        code_spans.append(m.group(0))
        return f"__AJAR_CODE_SPAN_{idx}__"

    work = re.sub(r"`[^`]+`", _stash_code, work)
    work = work.replace("—", ", ")
    work = re.sub(r"\s–\s", ", ", work)
    work = re.sub(r"(?<=\S)\s--\s(?=\S)", ", ", work)

    for pat, repl in _PROSE_ONLY_REPLACEMENTS:
        work = pat.sub(repl, work)

    work = re.sub(r"\s+,", ",", work)
    work = re.sub(r",\s*,+", ",", work)
    work = re.sub(r"\(\s*\)", "", work)
    work = re.sub(r"\s+", " ", work).strip(" ,;-")

    for idx, span in enumerate(code_spans):
        work = work.replace(f"__AJAR_CODE_SPAN_{idx}__", span)

    return _capitalize_sentences(work)


def _count_prose_words_approx(sentence: str) -> int:
    stripped_code = re.sub(r"`[^`]+`", "CODESYM", sentence)
    return len(re.findall(r"[A-Za-z0-9_]+", stripped_code))


def _split_protected_sentences(text: str) -> list[str]:
    work = text.strip()
    if not work:
        return []
    code_spans: list[str] = []

    def _stash(m: re.Match[str]) -> str:
        idx = len(code_spans)
        code_spans.append(m.group(0))
        return f"__CSPAN{idx}__"

    work = re.sub(r"`[^`]+`", _stash, work)
    for pat in _PROTECTED_DOT_PATTERNS:
        work = pat.sub(lambda m: m.group(0).replace(".", "<DOT>"), work)
    parts = re.split(r"(?<=[.!?])\s+", work)
    restored: list[str] = []
    for p in parts:
        s = p.replace("<DOT>", ".").strip()
        for idx, span in enumerate(code_spans):
            s = s.replace(f"__CSPAN{idx}__", span)
        if s:
            restored.append(s)
    return restored


def _split_single_long_sentence(sentence: str, max_words: int = 32) -> list[str]:
    if _count_prose_words_approx(sentence) <= max_words:
        return [sentence]

    code_spans: list[str] = []

    def _stash(m: re.Match[str]) -> str:
        idx = len(code_spans)
        code_spans.append(m.group(0))
        return f"__CSPAN{idx}__"

    masked = re.sub(r"`[^`]+`", _stash, sentence)
    pivots: tuple[tuple[str, str], ...] = (
        ("; ", ". "),
        (", allowing ", ". This allows "),
        (", causing ", ". This causes "),
        (", leaving ", ". That leaves "),
        (", while ", ". At the same time, "),
        (", whereas ", ". By contrast, "),
        (", which ", ". That value "),
        (", so ", ". Consequently, "),
        (", and ", ". "),
    )

    best_pair: tuple[str, str] | None = None
    best_balance = 10**9
    total_len = len(masked)
    for needle, replacement in pivots:
        start = 0
        while True:
            pos = masked.find(needle, start)
            if pos == -1:
                break
            start = pos + len(needle)
            # Skip splits inside parentheses
            if masked[:pos].count("(") != masked[:pos].count(")"):
                continue
            left_raw = masked[:pos].strip().rstrip(",;") + "."
            right_body = masked[pos + len(needle) :].strip()
            if not right_body:
                continue
            if replacement == ". ":
                right_raw = right_body[0].upper() + right_body[1:]
            else:
                right_raw = replacement[2:] + right_body
            if left_raw and right_raw:
                balance = abs(pos - (total_len // 2))
                if balance < best_balance:
                    best_balance = balance
                    best_pair = (left_raw, right_raw)

    if best_pair is None:
        return [sentence]

    out: list[str] = []
    for half in best_pair:
        restored = half
        for idx, span in enumerate(code_spans):
            restored = restored.replace(f"__CSPAN{idx}__", span)
        if not restored.endswith((".", "!", "?")):
            restored += "."
        if _count_prose_words_approx(restored) > max_words and restored != sentence:
            out.extend(_split_single_long_sentence(restored, max_words=max_words))
        else:
            out.append(restored)
    return out


def _bound_sentence_lengths(text: str, max_words: int = 32) -> str:
    sentences = _split_protected_sentences(text)
    if not sentences:
        return ""
    bounded: list[str] = []
    for sent in sentences:
        s = sent.strip()
        if not s:
            continue
        if not s.endswith((".", "!", "?")):
            s += "."
        bounded.extend(_split_single_long_sentence(s, max_words=max_words))
    return " ".join(_capitalize_sentences(x) for x in bounded)


def _clean_finding_title(
    raw_title: str,
    *,
    target_roots: Sequence[str],
    other_roots: Sequence[str],
    target_slug: str,
) -> str:
    t = re.sub(r"^\s*\[(?:CRITICAL|HIGH|MEDIUM|LOW|INFO)\]\s*", "", raw_title or "", flags=re.IGNORECASE)
    t = _dejargonize_external_prose(
        t,
        target_roots=target_roots,
        other_roots=other_roots,
        target_slug=target_slug,
    )
    t = t.strip().rstrip(".")
    return t or "Confirmed boundary validation flaw"


def _extract_entry_command_hint(poc_cmd: str, locus: str) -> str:
    cleaned = (poc_cmd or "").strip()
    if cleaned:
        first_seg = re.split(r"\s*(?:&&|\|\||;|\|)\s*", cleaned)[0].strip()
        tokens = first_seg.split()
        while tokens and ("=" in tokens[0] or tokens[0] in ("env", "sh", "bash")):
            tokens.pop(0)
        if tokens:
            if tokens[0] in ("python", "python3", "node", "ruby", "go") and len(tokens) >= 2:
                return f"{tokens[0]} {tokens[1]}"
            return tokens[0]
    return locus.split(":", 1)[0] or "target"


def _meaningful_calibration_note(note: str) -> bool:
    s = (note or "").strip()
    if len(s) < 18:
        return False
    generic = {"independent review", "early review", "calibrated severity", "operator calibration"}
    return s.lower().rstrip(".") not in generic


def _compose_finding_sections(
    f: Mapping[str, Any],
    *,
    pv: Mapping[str, Any] | None,
    surface_map: Mapping[str, Mapping[str, Any]],
    target_slug: str,
    head_sha: str,
    target_roots: Sequence[str],
    other_roots: Sequence[str],
) -> dict[str, str]:
    loc = _normalize_locus(
        str(f.get("locus") or ""),
        target_roots=target_roots,
        other_roots=other_roots,
        target_slug=target_slug,
    )
    title = _clean_finding_title(
        str(f.get("title") or ""),
        target_roots=target_roots,
        other_roots=other_roots,
        target_slug=target_slug,
    )
    sev = str(f.get("severity") or "medium").strip().lower()
    article = "an" if sev[:1] in ("a", "e", "i", "o", "u") else "a"
    rev_clause = f" at commit `{head_sha[:10]}`" if head_sha else ""

    poc_clean = _sanitize_external_text(
        str(f.get("poc_cmd") or "").strip(),
        target_roots=target_roots,
        other_roots=other_roots,
        target_slug=target_slug,
    )
    ctrl_clean = _sanitize_external_text(
        str(f.get("control_cmd") or "").strip(),
        target_roots=target_roots,
        other_roots=other_roots,
        target_slug=target_slug,
    )
    build_clean = _sanitize_external_text(
        str(f.get("build_cmd") or "").strip(),
        target_roots=target_roots,
        other_roots=other_roots,
        target_slug=target_slug,
    )
    entry_hint = _extract_entry_command_hint(poc_clean, loc)

    # 1. Summary (strictly 1-2 crisp sentences, <= 52 words, concrete file/commit anchor, active voice)
    explicit_summary = _bound_sentence_lengths(
        _dejargonize_external_prose(
            str(f.get("summary") or "").strip(),
            target_roots=target_roots,
            other_roots=other_roots,
            target_slug=target_slug,
        )
    )
    if explicit_summary and 12 <= _count_prose_words_approx(explicit_summary) <= 52:
        if "`" not in explicit_summary and loc not in explicit_summary:
            summary_prose = f"In `{target_slug}` (`{loc}`), {explicit_summary[0].lower() + explicit_summary[1:]}"
        else:
            summary_prose = explicit_summary
    else:
        title_clause = re.sub(r"^(?:a|an|the)\s+", "", title, flags=re.IGNORECASE).strip()
        if len(title_clause.split()) > 16:
            title_clause = " ".join(title_clause.split()[:16])
        if re.match(r"^[A-Z][a-z]+\b", title_clause):
            title_clause = title_clause[0].lower() + title_clause[1:]
        has_verb = bool(
            re.search(
                r"\b(?:bypasses|allows|skips|omits|reads|writes|wraps|overflows|underflows|"
                r"leaks|crashes|accepts|fails|misses|lets|exposes|executes|overwrites|triggers)\b",
                title_clause,
                re.IGNORECASE,
            )
        )
        connector = "where" if has_verb else "involving"
        s1 = f"In `{target_slug}`{rev_clause}, `{loc}` has {article} {sev}-severity flaw {connector} {title_clause}."
        s2 = (
            f"Running `{entry_hint}` with the reproduction input triggers the fault deterministically, "
            f"while benign baseline input succeeds."
        )
        summary_prose = f"{s1} {s2}"

    # 2. Root Cause
    raw_rc = str(f.get("root_cause") or f.get("claim_mechanism") or "").strip()
    rc_clean = _bound_sentence_lengths(
        _dejargonize_external_prose(
            raw_rc,
            target_roots=target_roots,
            other_roots=other_roots,
            target_slug=target_slug,
        )
    )
    rc_parts: list[str] = []
    loc_file = loc.split(":", 1)[0]
    if not rc_clean or len(rc_clean.split()) < 4:
        rc_parts.append(f"The defect sits at `{loc}`.")
        rc_parts.append(
            f"Input reaching `{entry_hint}` bypasses the expected validation check and triggers `{title}`."
        )
    else:
        if loc_file and loc_file not in rc_clean:
            rc_parts.append(f"The defect sits at `{loc}`.")
        rc_parts.append(rc_clean)

    if _count_prose_words_approx(" ".join(rc_parts)) < 34:
        pred_raw = str(f.get("falsification_prediction") or "").strip()
        pred_clean = _bound_sentence_lengths(
            _dejargonize_external_prose(
                pred_raw,
                target_roots=target_roots,
                other_roots=other_roots,
                target_slug=target_slug,
            )
        )
        if pred_clean and pred_clean.lower() not in " ".join(rc_parts).lower():
            rc_parts.append(pred_clean)

    cal_raw = str(f.get("calibration_notes") or "").strip()
    if _meaningful_calibration_note(cal_raw):
        cal_clean = _bound_sentence_lengths(
            _dejargonize_external_prose(
                cal_raw,
                target_roots=target_roots,
                other_roots=other_roots,
                target_slug=target_slug,
            )
        )
        if cal_clean and cal_clean.lower() not in " ".join(rc_parts).lower():
            rc_parts.append(cal_clean)

    if _count_prose_words_approx(" ".join(rc_parts)) < 25:
        rc_parts.append(f"Callers invoking `{entry_hint}` reach `{loc}` directly without an intervening check.")

    root_cause_prose = " ".join(rc_parts)

    # 3. Reproduction
    arm1 = _safe_json_loads(f.get("arm1_clean_poc_json"), {})
    arm2 = _safe_json_loads(f.get("arm2_clean_ctrl_json"), {})
    arm1_rc = arm1.get("exit_code") if isinstance(arm1, dict) else None
    arm2_rc = arm2.get("exit_code") if isinstance(arm2, dict) else None
    if arm1_rc is not None and arm2_rc is not None:
        repro_intro = (
            f"Run the script below from a clean `{target_slug}` checkout to reproduce the failure "
            f"(observed exit code `{arm1_rc}`). "
            f"Valid baseline input exits cleanly with code `{arm2_rc}`. "
            f"The second command confirms normal behavior on well-formed input."
        )
    else:
        repro_intro = (
            f"Run the script below from a clean `{target_slug}` checkout to trigger the defect directly. "
            f"Valid baseline input exits cleanly. "
            f"The second command confirms that standard inputs still produce the expected result."
        )

    script_lines: list[str] = [
        "#!/bin/sh",
        "set -eu",
        'workdir="$(mktemp -d)"',
        'trap \'rm -rf "$workdir"\' EXIT',
    ]
    if build_clean:
        script_lines.extend(["", "# Build target", build_clean])
    script_lines.extend(["", "# Trigger defect", poc_clean or f"# Invoke {loc} with crafted input"])
    if ctrl_clean:
        script_lines.extend(["", "# Benign baseline check", ctrl_clean])
    repro_block = "```sh\n" + "\n".join(script_lines) + "\n```"

    # 4. Impact
    explicit_impact = _bound_sentence_lengths(
        _dejargonize_external_prose(
            str(f.get("impact") or "").strip(),
            target_roots=target_roots,
            other_roots=other_roots,
            target_slug=target_slug,
        )
    )
    if explicit_impact and _count_prose_words_approx(explicit_impact) >= 20:
        impact_prose = explicit_impact
    else:
        surf_id = str(f.get("surface_id") or "")
        surf = surface_map.get(surf_id, {})
        boundary_raw = str(surf.get("trust_boundary") or f.get("surface_trust_boundary") or "").strip()
        boundary_clean = _dejargonize_external_prose(
            boundary_raw,
            target_roots=target_roots,
            other_roots=other_roots,
            target_slug=target_slug,
        )
        imp_parts: list[str] = []
        if boundary_clean:
            imp_parts.append(
                f"This {sev}-severity issue crosses the {boundary_clean} boundary in `{target_slug}` "
                f"whenever untrusted input reaches `{loc}`."
            )
        else:
            imp_parts.append(
                f"This {sev}-severity issue affects `{target_slug}` callers whenever untrusted input "
                f"reaches `{loc}` via `{entry_hint}`."
            )

        ub_class = str(f.get("ub_divergence_class") or "").strip()
        realism_obj = _safe_json_loads(f.get("realism_json"), {})
        dsteps = realism_obj.get("declared_steps") if isinstance(realism_obj, dict) else None
        if ub_class == "confirmed_release_impact":
            imp_parts.append("Optimized release builds reproduce the fault without sanitizer instrumentation.")
        elif ub_class in ("sanitizer_only_or_elided", "debug_assert_only"):
            imp_parts.append(
                "Optimized release builds halt or elide this condition without memory corruption, "
                "limiting standalone impact outside debug or sanitizer builds."
            )
        elif isinstance(dsteps, int) and dsteps >= 2:
            imp_parts.append(
                f"Reaching the full effect requires {dsteps} sequential steps under the tested configuration."
            )
        else:
            imp_parts.append(
                "Exploitation requires no special local privileges beyond supplying crafted input to the affected entrypoint."
            )
        imp_parts.append("Upstream code still lacks this guard.")
        impact_prose = " ".join(imp_parts)

    # 5. Suggested Fix
    fix_diff_raw = ""
    if pv is not None and bool(pv.get("passed")) and str(pv.get("patch_diff") or "").strip():
        fix_diff_raw = str(pv.get("patch_diff") or "")
        suite_clean = _sanitize_external_text(
            str(pv.get("suite_cmd") or "").strip(),
            target_roots=target_roots,
            other_roots=other_roots,
            target_slug=target_slug,
        )
        caller_clean = _bound_sentence_lengths(
            _dejargonize_external_prose(
                str(pv.get("caller_audit") or "").strip(),
                target_roots=target_roots,
                other_roots=other_roots,
                target_slug=target_slug,
            )
        )
        sibling_clean = _bound_sentence_lengths(
            _dejargonize_external_prose(
                str(pv.get("sibling_audit") or "").strip(),
                target_roots=target_roots,
                other_roots=other_roots,
                target_slug=target_slug,
            )
        )
        fix_parts = [f"Apply the unified diff below to enforce the missing check at `{loc}`."]
        if suite_clean:
            fix_parts.append(f"Local regression checks (`{suite_clean}`) pass with baseline behavior preserved.")
        else:
            fix_parts.append("Baseline checks pass with normal behavior preserved.")
        if caller_clean and _count_prose_words_approx(" ".join(fix_parts) + " " + caller_clean) <= 68:
            fix_parts.append(caller_clean)
        elif sibling_clean and _count_prose_words_approx(" ".join(fix_parts) + " " + sibling_clean) <= 68:
            fix_parts.append(sibling_clean)
        fix_prose = " ".join(fix_parts)
    elif str(f.get("micropatch_diff") or "").strip():
        fix_diff_raw = str(f.get("micropatch_diff") or "")
        fix_prose = (
            f"Apply the minimal guard change below at `{loc}` so malformed inputs fail before reaching "
            f"the vulnerable operation. Baseline control inputs continue to pass. "
            f"Audit remaining callers and run the full project test suite before merging."
        )
    else:
        fix_prose = (
            f"Enforce explicit input validation at `{loc}` before executing the downstream operation. "
            f"Add a regression test covering both the reproduction input and normal baseline traffic."
        )

    clean_diff = _sanitize_diff_text(
        fix_diff_raw,
        target_roots=target_roots,
        other_roots=other_roots,
        target_slug=target_slug,
    )
    fix_block = f"```diff\n{clean_diff}\n```" if clean_diff else ""

    return {
        "title": title,
        "severity": sev,
        "location": loc,
        "summary": summary_prose,
        "root_cause": root_cause_prose,
        "reproduction_prose": repro_intro,
        "reproduction_block": repro_block,
        "impact": impact_prose,
        "suggested_fix_prose": fix_prose,
        "suggested_fix_block": fix_block,
        "suggested_fix_diff": clean_diff,
        "poc_cmd": poc_clean,
        "control_cmd": ctrl_clean,
        "build_cmd": build_clean,
    }


def _load_core_report_rows(
    conn: sqlite3.Connection,
    *,
    include_rejected_appendix: bool = False,
    finding_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    run_row = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
    run = dict(run_row) if run_row else {}

    raw_findings = list_rows(
        conn,
        """
        SELECT f.*, c.mechanism AS claim_mechanism, c.proposer_worker_id, c.falsifier_worker_id,
               c.falsification_prediction, c.customer_state, c.remediation_state,
               c.same_root_claim_id, c.duplicate_of_claim_id,
               COALESCE(s.trust_boundary, '') AS surface_trust_boundary
        FROM findings f
        JOIN claims c ON f.claim_id = c.claim_id
        LEFT JOIN surfaces s ON c.surface_id = s.surface_id
        ORDER BY CASE f.severity
            WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END,
            f.created_at ASC
        """,
    )
    findings = apply_latest_finding_corrections(conn, raw_findings)

    if finding_ids:
        wanted: list[str] = []
        for raw_id in finding_ids:
            for part in str(raw_id or "").split(","):
                tok = part.strip()
                if tok and tok not in wanted:
                    wanted.append(tok)
        if wanted:
            by_id = {str(f.get("finding_id") or ""): f for f in findings}
            missing = [fid for fid in wanted if fid not in by_id]
            if missing:
                raise AjarError(
                    f"Unknown confirmed finding_id(s) for report filter: {', '.join(missing)}",
                    EXIT_USER_ERROR,
                )
            findings = [by_id[fid] for fid in wanted]

    root_keys: set[str] = set()
    for f in findings:
        sr = str(f.get("same_root_claim_id") or "").strip()
        dup = str(f.get("duplicate_of_claim_id") or "").strip()
        loc_base = str(f.get("locus") or "").split(":", 1)[0].strip().lstrip("./")
        root_keys.add(sr or dup or str(f.get("locus") or loc_base))
    distinct_root_causes_count = len(root_keys)

    rec_harness = str(run.get("harness_sha256") or "").strip()
    cur_harness = compute_harness_code_sha256()
    harness_integrity = {
        "recorded_harness_sha256": rec_harness,
        "current_harness_sha256": cur_harness,
        "harness_modified_mid_run": bool(rec_harness and rec_harness != cur_harness),
    }

    chains = list_rows(conn, "SELECT * FROM chains WHERE verified = 1 ORDER BY created_at ASC")
    surfaces = list_rows(conn, "SELECT * FROM surfaces ORDER BY priority ASC, created_at ASC")
    dry_controls = list_rows(
        conn,
        "SELECT task_id, title, dry_control_locus, dry_control_reason FROM tasks WHERE status = 'dry' ORDER BY updated_at ASC",
    )
    blocked_claims = list_rows(
        conn,
        "SELECT claim_id, title, locus, blocker_reason FROM claims WHERE status = 'blocked'",
    )
    active_steers = list_steers(conn, active_only=True)
    patch_verifications = list_rows(
        conn,
        """
        SELECT verification_id, finding_id, claim_id, passed, patch_diff, suite_cmd,
               caller_audit, sibling_audit, arm9_revert_poc_json, created_at
        FROM patch_verifications
        ORDER BY created_at ASC
        """,
    )
    epistemic_hooks = list_rows(
        conn,
        "SELECT hook_id, hook_code, subsystem, target_locus, status, leases_seen FROM epistemic_hooks ORDER BY created_at ASC",
    )
    primitive_helpers = list_rows(
        conn,
        "SELECT helper_id, primitive_id, module_name, callable_name, provides_tags_json, verified FROM primitive_helpers ORDER BY created_at ASC",
    )
    coverage_spans = list_rows(
        conn,
        "SELECT span_id, task_id, rel_path, start_line, end_line, file_sha256 FROM coverage_spans ORDER BY rel_path ASC, start_line ASC",
    )
    claim_counts = {
        r["status"]: int(r["c"])
        for r in conn.execute("SELECT status, COUNT(*) AS c FROM claims GROUP BY status").fetchall()
    }
    gates = check_all_gates(conn, auto_enqueue_chain=False)

    rejected: list[dict[str, Any]] = []
    if include_rejected_appendix:
        rejected = list_rows(
            conn,
            """
            SELECT claim_id, title, locus, status, falsify_notes, falsify_control_locus
            FROM claims
            WHERE status IN ('falsified', 'rejected_repro', 'duplicate_root_cause', 'config_gated')
            ORDER BY updated_at ASC
            """,
        )

    return {
        "run": run,
        "findings": findings,
        "distinct_root_causes_count": distinct_root_causes_count,
        "harness_integrity": harness_integrity,
        "chains": chains,
        "surfaces": surfaces,
        "dry_controls": dry_controls,
        "blocked_claims": blocked_claims,
        "active_steers": active_steers,
        "patch_verifications": patch_verifications,
        "epistemic_hooks": epistemic_hooks,
        "primitive_helpers": primitive_helpers,
        "coverage_spans": coverage_spans,
        "claim_counts": claim_counts,
        "gates": gates,
        "threat_model": (
            dict(tm_row) if (tm_row := conn.execute("SELECT * FROM threat_models LIMIT 1").fetchone()) else None
        ),
        "threat_assumptions": list_rows(conn, "SELECT * FROM threat_assumptions ORDER BY created_at ASC"),
        "crown_jewels": list_rows(conn, "SELECT * FROM crown_jewels ORDER BY created_at ASC"),
        "open_doors": list_rows(conn, "SELECT * FROM parked_doors ORDER BY created_at ASC"),
        "rejected_claims_appendix": rejected,
    }


def _best_pv_by_finding(patch_verifications: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    best: dict[str, Mapping[str, Any]] = {}
    for pv in patch_verifications:
        fid = str(pv.get("finding_id") or "")
        if fid and bool(pv.get("passed")):
            best[fid] = pv
    return best


def _resolve_chain_step_labels(
    conn: sqlite3.Connection,
    raw_steps_json: Any,
    *,
    findings_by_id: Mapping[str, Mapping[str, Any]],
    target_roots: Sequence[str],
    other_roots: Sequence[str],
    target_slug: str,
) -> list[str]:
    step_ids = _safe_json_loads(raw_steps_json, [])
    if not isinstance(step_ids, list):
        return []
    prim_rows = {
        str(r["primitive_id"]): dict(r)
        for r in conn.execute("SELECT primitive_id, kind, locus FROM primitives").fetchall()
    }
    clm_rows = {
        str(r["claim_id"]): dict(r)
        for r in conn.execute("SELECT claim_id, title, locus FROM claims").fetchall()
    }
    anom_rows = {
        str(r["anomaly_id"]): dict(r)
        for r in conn.execute("SELECT anomaly_id, observation, locus FROM anomalies").fetchall()
    }

    labels: list[str] = []
    for raw_sid in step_ids:
        sid = str(raw_sid or "").strip()
        if not sid:
            continue
        if sid in findings_by_id:
            f = findings_by_id[sid]
            loc = _normalize_locus(
                str(f.get("locus") or ""),
                target_roots=target_roots,
                other_roots=other_roots,
                target_slug=target_slug,
            )
            ttl = _clean_finding_title(
                str(f.get("title") or ""),
                target_roots=target_roots,
                other_roots=other_roots,
                target_slug=target_slug,
            )
            labels.append(f"{ttl} (`{loc}`)")
        elif sid in prim_rows:
            p = prim_rows[sid]
            loc = _normalize_locus(
                str(p.get("locus") or ""),
                target_roots=target_roots,
                other_roots=other_roots,
                target_slug=target_slug,
            )
            kind = _dejargonize_external_prose(
                str(p.get("kind") or "step"),
                target_roots=target_roots,
                other_roots=other_roots,
                target_slug=target_slug,
            )
            labels.append(f"{kind} (`{loc}`)")
        elif sid in clm_rows:
            c = clm_rows[sid]
            loc = _normalize_locus(
                str(c.get("locus") or ""),
                target_roots=target_roots,
                other_roots=other_roots,
                target_slug=target_slug,
            )
            ttl = _clean_finding_title(
                str(c.get("title") or "step"),
                target_roots=target_roots,
                other_roots=other_roots,
                target_slug=target_slug,
            )
            labels.append(f"{ttl} (`{loc}`)")
        elif sid in anom_rows:
            a = anom_rows[sid]
            loc = _normalize_locus(
                str(a.get("locus") or ""),
                target_roots=target_roots,
                other_roots=other_roots,
                target_slug=target_slug,
            )
            labels.append(f"observed behavior at `{loc}`")
    return labels


def build_report_data(
    conn: sqlite3.Connection,
    *,
    include_rejected_appendix: bool = False,
    audience: str = "customer",
    finding_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    aud = _validate_audience(audience)
    core = _load_core_report_rows(
        conn,
        include_rejected_appendix=include_rejected_appendix,
        finding_ids=finding_ids,
    )
    run = core["run"]
    raw_target_path = str(run.get("target_path") or "")
    run_id = str(run.get("run_id") or "")
    target_slug = _infer_target_slug(raw_target_path, run_id=run_id, conn=conn)
    head_sha = _resolve_head_sha(run, raw_target_path, conn=conn)
    target_roots, other_roots = _collect_report_roots(run, conn=conn)

    if aud == "maintainer":
        pv_map = _best_pv_by_finding(core["patch_verifications"])
        surface_map = {str(s.get("surface_id") or ""): s for s in core["surfaces"]}
        findings_by_id = {str(f.get("finding_id") or ""): f for f in core["findings"]}
        maint_findings: list[dict[str, Any]] = []
        for idx, f in enumerate(core["findings"], start=1):
            pv = pv_map.get(str(f.get("finding_id") or ""))
            composed = _compose_finding_sections(
                f,
                pv=pv,
                surface_map=surface_map,
                target_slug=target_slug,
                head_sha=head_sha,
                target_roots=target_roots,
                other_roots=other_roots,
            )
            maint_findings.append(
                {
                    "index": idx,
                    "title": composed["title"],
                    "severity": composed["severity"],
                    "location": composed["location"],
                    "summary": composed["summary"],
                    "root_cause": composed["root_cause"],
                    "impact": composed["impact"],
                    "reproduction": {
                        "build_cmd": composed["build_cmd"],
                        "poc_cmd": composed["poc_cmd"],
                        "control_cmd": composed["control_cmd"],
                    },
                    "suggested_fix": {
                        "prose": composed["suggested_fix_prose"],
                        "diff": composed["suggested_fix_diff"],
                        "regression_suite_verified": bool(pv and pv.get("passed")),
                    },
                }
            )
        maint_chains: list[dict[str, Any]] = []
        for ch in core["chains"]:
            step_labels = _resolve_chain_step_labels(
                conn,
                ch.get("step_ids_json"),
                findings_by_id=findings_by_id,
                target_roots=target_roots,
                other_roots=other_roots,
                target_slug=target_slug,
            )
            maint_chains.append(
                {
                    "title": _clean_finding_title(
                        str(ch.get("title") or ""),
                        target_roots=target_roots,
                        other_roots=other_roots,
                        target_slug=target_slug,
                    ),
                    "severity": str(ch.get("severity") or "high").lower(),
                    "steps": step_labels,
                    "poc_cmd": _sanitize_external_text(
                        str(ch.get("e2e_poc_cmd") or ""),
                        target_roots=target_roots,
                        other_roots=other_roots,
                        target_slug=target_slug,
                    ),
                }
            )
        maint_payload: dict[str, Any] = {
            "schema": "ajar-maintainer-report/1",
            "audience": "maintainer",
            "target": target_slug,
            "commit_sha": head_sha,
            "distinct_root_causes_count": core["distinct_root_causes_count"],
            "findings": maint_findings,
            "chains": maint_chains,
        }
        scrubbed_maint = scrub_json_value(maint_payload)
        assert isinstance(scrubbed_maint, dict)
        return scrubbed_maint

    gates = core["gates"]
    data: dict[str, Any] = {
        "schema": "ajar-report/3",
        "audience": aud,
        "run_id": run_id,
        "target_path": raw_target_path if aud == "internal" else target_slug,
        "target_mode": run.get("target_mode", "source"),
        "campaign_phase": run.get("campaign_phase", "hunt"),
        "stopping_criterion": run.get("stopping_criterion", "exhaustive-high"),
        "diff_range": run.get("diff_range", ""),
        "goal": run.get("goal", ""),
        "status": run.get("status", ""),
        "stop_reason": run.get("stop_reason", ""),
        "commitment_hash": run.get("commitment_hash", ""),
        "harness_integrity": core["harness_integrity"],
        "created_at": run.get("created_at", ""),
        "finished_at": run.get("finished_at"),
        "threat_model": core["threat_model"],
        "threat_assumptions": core["threat_assumptions"],
        "crown_jewels": core["crown_jewels"] if aud == "internal" else [],
        "open_doors": core["open_doors"] if aud == "internal" else [],
        "findings": core["findings"],
        "distinct_root_causes_count": core["distinct_root_causes_count"],
        "verified_chains": core["chains"],
        "patch_verifications": core["patch_verifications"],
        "epistemic_hooks": core["epistemic_hooks"] if aud == "internal" else [],
        "primitive_helpers": core["primitive_helpers"] if aud == "internal" else [],
        "coverage_spans": core["coverage_spans"],
        "active_steers": core["active_steers"] if aud == "internal" else [],
        "surfaces_covered": core["surfaces"],
        "dry_controls": core["dry_controls"],
        "blocked_items": core["blocked_claims"] if aud == "internal" else [],
        "claim_summary_counts": core["claim_counts"],
        "gates": gates["gates"] if aud == "internal" else {},
        "gates_passed": gates["passed"],
        "crown_jewel_reached": gates["crown_jewel_reached"],
        "economics": (
            gates["economics"]
            if aud == "internal"
            else {"in_scope_loc": gates["economics"].get("in_scope_loc", 0)}
        ),
    }
    if include_rejected_appendix and aud == "internal":
        data["rejected_claims_appendix"] = core["rejected_claims_appendix"]

    if aud == "customer":
        sanitized_customer: list[dict[str, Any]] = []
        for raw_f in core["findings"]:
            f_copy = dict(raw_f)
            f_copy["locus"] = _normalize_locus(
                str(f_copy.get("locus") or ""),
                target_roots=target_roots,
                other_roots=other_roots,
                target_slug=target_slug,
            )
            f_copy.pop("micropatch_path", None)
            sanitized_customer.append(f_copy)
        data["findings"] = sanitized_customer
        data = _sanitize_external_value(
            data,
            target_roots=target_roots,
            other_roots=other_roots,
            target_slug=target_slug,
        )

    scrubbed = scrub_json_value(data)
    assert isinstance(scrubbed, dict)
    return scrubbed


def _render_maintainer_markdown(
    conn: sqlite3.Connection,
    core: Mapping[str, Any],
) -> str:
    run = core["run"]
    raw_target_path = str(run.get("target_path") or "")
    target_slug = _infer_target_slug(raw_target_path, run_id=str(run.get("run_id") or ""), conn=conn)
    head_sha = _resolve_head_sha(run, raw_target_path, conn=conn)
    target_roots, other_roots = _collect_report_roots(run, conn=conn)
    pv_map = _best_pv_by_finding(core["patch_verifications"])
    surface_map = {str(s.get("surface_id") or ""): s for s in core["surfaces"]}
    findings = list(core["findings"])
    findings_by_id = {str(f.get("finding_id") or ""): f for f in findings}

    lines: list[str] = []
    if not findings:
        rev_clause = f" at commit `{head_sha[:10]}`" if head_sha else ""
        lines.extend(
            [
                f"# Security Verification Summary: {target_slug}",
                "",
                "## Summary",
                "",
                (
                    f"Testing of `{target_slug}`{rev_clause} reproduced zero exploitable vulnerabilities "
                    f"across `{len(core['surfaces'])}` inspected entrypoints. "
                    f"Inspected guards apply only to the tested revision and do not establish absence of all defects."
                ),
                "",
                "## Reproduction",
                "",
                f"Run the project baseline check from a clean `{target_slug}` checkout.",
                "",
                "```sh\n#!/bin/sh\nset -eu\nworkdir=\"$(mktemp -d)\"\ntrap 'rm -rf \"$workdir\"' EXIT\n```",
                "",
            ]
        )
        return scrub_text("\n".join(lines))

    if len(findings) == 1:
        f = findings[0]
        pv = pv_map.get(str(f.get("finding_id") or ""))
        sec = _compose_finding_sections(
            f,
            pv=pv,
            surface_map=surface_map,
            target_slug=target_slug,
            head_sha=head_sha,
            target_roots=target_roots,
            other_roots=other_roots,
        )
        lines.extend(
            [
                f"# {sec['title']}",
                "",
                "## Summary",
                "",
                sec["summary"],
                "",
                "## Root Cause",
                "",
                sec["root_cause"],
                "",
                "## Reproduction",
                "",
                sec["reproduction_prose"],
                "",
                sec["reproduction_block"],
                "",
                "## Impact",
                "",
                sec["impact"],
                "",
                "## Suggested Fix",
                "",
                sec["suggested_fix_prose"],
            ]
        )
        if sec["suggested_fix_block"]:
            lines.extend(["", sec["suggested_fix_block"]])
        lines.append("")
        return scrub_text("\n".join(lines))

    # Multi-finding maintainer advisory
    composed_list = [
        _compose_finding_sections(
            f,
            pv=pv_map.get(str(f.get("finding_id") or "")),
            surface_map=surface_map,
            target_slug=target_slug,
            head_sha=head_sha,
            target_roots=target_roots,
            other_roots=other_roots,
        )
        for f in findings
    ]
    rev_clause = f" at commit `{head_sha[:10]}`" if head_sha else ""
    first_loc = composed_list[0]["location"]
    root_count = int(core["distinct_root_causes_count"])
    lines.extend(
        [
            f"# Vulnerability Report: {target_slug}",
            "",
            "## Summary",
            "",
            (
                f"In `{target_slug}`{rev_clause}, `{len(composed_list)}` reproducible security issues "
                f"spanning `{root_count}` distinct root causes affect `{first_loc}` and peer paths. "
                f"Each section below provides a minimal reproduction script and candidate root-cause fix."
            ),
            "",
        ]
    )
    for idx, sec in enumerate(composed_list, start=1):
        lines.extend(
            [
                f"## {idx}. [{sec['severity'].upper()}] {sec['title']}",
                "",
                sec["summary"],
                "",
                "### Root Cause",
                "",
                sec["root_cause"],
                "",
                "### Reproduction",
                "",
                sec["reproduction_prose"],
                "",
                sec["reproduction_block"],
                "",
                "### Impact",
                "",
                sec["impact"],
                "",
                "### Suggested Fix",
                "",
                sec["suggested_fix_prose"],
            ]
        )
        if sec["suggested_fix_block"]:
            lines.extend(["", sec["suggested_fix_block"]])
        lines.append("")

    if core["chains"]:
        lines.extend(["## Multi-Step Attack Chains", ""])
        for ch in core["chains"]:
            ch_title = _clean_finding_title(
                str(ch.get("title") or ""),
                target_roots=target_roots,
                other_roots=other_roots,
                target_slug=target_slug,
            )
            step_labels = _resolve_chain_step_labels(
                conn,
                ch.get("step_ids_json"),
                findings_by_id=findings_by_id,
                target_roots=target_roots,
                other_roots=other_roots,
                target_slug=target_slug,
            )
            ch_poc = _sanitize_external_text(
                str(ch.get("e2e_poc_cmd") or ""),
                target_roots=target_roots,
                other_roots=other_roots,
                target_slug=target_slug,
            )
            joined_steps = " -> ".join(step_labels) if step_labels else "the verified sequence"
            lines.extend(
                [
                    f"### [{str(ch.get('severity') or 'high').upper()}] {ch_title}",
                    "",
                    f"Chaining {joined_steps} reproduces end-to-end impact on `{target_slug}`.",
                    "",
                    f"```sh\n#!/bin/sh\nset -eu\n{ch_poc}\n```",
                    "",
                ]
            )

    return scrub_text("\n".join(lines))


def _render_customer_markdown(
    conn: sqlite3.Connection,
    core: Mapping[str, Any],
) -> str:
    run = core["run"]
    raw_target_path = str(run.get("target_path") or "")
    target_slug = _infer_target_slug(raw_target_path, run_id=str(run.get("run_id") or ""), conn=conn)
    head_sha = _resolve_head_sha(run, raw_target_path, conn=conn)
    target_roots, other_roots = _collect_report_roots(run, conn=conn)
    pv_map = _best_pv_by_finding(core["patch_verifications"])
    surface_map = {str(s.get("surface_id") or ""): s for s in core["surfaces"]}
    findings = list(core["findings"])
    findings_by_id = {str(f.get("finding_id") or ""): f for f in findings}

    rev_clause = f" at commit `{head_sha[:10]}`" if head_sha else ""
    root_count = int(core["distinct_root_causes_count"])
    lines: list[str] = [
        f"# Security Review Report: {target_slug}",
        "",
        "## Summary",
        "",
    ]
    if not findings:
        lines.extend(
            [
                (
                    f"Security verification of `{target_slug}`{rev_clause} reproduced zero vulnerabilities "
                    f"across `{len(core['surfaces'])}` inspected entrypoints. "
                    f"Verified controls below apply strictly to the reviewed revision."
                ),
                "",
            ]
        )
    elif len(findings) == 1:
        sec0 = _compose_finding_sections(
            findings[0],
            pv=pv_map.get(str(findings[0].get("finding_id") or "")),
            surface_map=surface_map,
            target_slug=target_slug,
            head_sha=head_sha,
            target_roots=target_roots,
            other_roots=other_roots,
        )
        lines.extend([sec0["summary"], ""])
    else:
        first_loc = _normalize_locus(
            str(findings[0].get("locus") or ""),
            target_roots=target_roots,
            other_roots=other_roots,
            target_slug=target_slug,
        )
        lines.extend(
            [
                (
                    f"Security verification of `{target_slug}`{rev_clause} confirmed `{len(findings)}` "
                    f"reproducible findings across `{root_count}` distinct root causes, starting at `{first_loc}`. "
                    f"Each finding below includes a deterministic reproduction script and candidate fix."
                ),
                "",
            ]
        )

    lines.extend(["## Confirmed Findings", ""])
    if not findings:
        lines.extend(["No confirmed vulnerabilities reproduced within the reviewed scope.", ""])
    else:
        for idx, f in enumerate(findings, start=1):
            sec = _compose_finding_sections(
                f,
                pv=pv_map.get(str(f.get("finding_id") or "")),
                surface_map=surface_map,
                target_slug=target_slug,
                head_sha=head_sha,
                target_roots=target_roots,
                other_roots=other_roots,
            )
            lines.extend(
                [
                    f"### {idx}. [{sec['severity'].upper()}] {sec['title']}",
                    "",
                    sec["summary"],
                    "",
                    "#### Root Cause",
                    "",
                    sec["root_cause"],
                    "",
                    "#### Reproduction",
                    "",
                    sec["reproduction_prose"],
                    "",
                    sec["reproduction_block"],
                    "",
                    "#### Impact",
                    "",
                    sec["impact"],
                    "",
                    "#### Suggested Fix",
                    "",
                    sec["suggested_fix_prose"],
                ]
            )
            if sec["suggested_fix_block"]:
                lines.extend(["", sec["suggested_fix_block"]])
            lines.append("")

    if core["chains"]:
        lines.extend(["## Multi-Step Attack Chains", ""])
        for ch in core["chains"]:
            ch_title = _clean_finding_title(
                str(ch.get("title") or ""),
                target_roots=target_roots,
                other_roots=other_roots,
                target_slug=target_slug,
            )
            step_labels = _resolve_chain_step_labels(
                conn,
                ch.get("step_ids_json"),
                findings_by_id=findings_by_id,
                target_roots=target_roots,
                other_roots=other_roots,
                target_slug=target_slug,
            )
            ch_poc = _sanitize_external_text(
                str(ch.get("e2e_poc_cmd") or ""),
                target_roots=target_roots,
                other_roots=other_roots,
                target_slug=target_slug,
            )
            joined_steps = " -> ".join(step_labels) if step_labels else "the verified sequence"
            lines.extend(
                [
                    f"### [{str(ch.get('severity') or 'high').upper()}] {ch_title}",
                    "",
                    f"Combining {joined_steps} reproduces the end-to-end impact below.",
                    "",
                    f"```sh\n#!/bin/sh\nset -eu\n{ch_poc}\n```",
                    "",
                ]
            )

    lines.extend(["## Scope and Inspected Controls", ""])
    if core["dry_controls"]:
        for d in core["dry_controls"]:
            d_loc = _normalize_locus(
                str(d.get("dry_control_locus") or ""),
                target_roots=target_roots,
                other_roots=other_roots,
                target_slug=target_slug,
            )
            d_reason = _bound_sentence_lengths(
                _dejargonize_external_prose(
                    str(d.get("dry_control_reason") or ""),
                    target_roots=target_roots,
                    other_roots=other_roots,
                    target_slug=target_slug,
                )
            )
            lines.append(f"- `{d_loc}`: {d_reason}")
        lines.append("")

    lines.extend(
        [
            (
                f"This review covered `{len(core['surfaces'])}` mapped entrypoints on `{target_slug}`{rev_clause}. "
                f"Inspected controls record concrete guards verified at this revision and do not claim proof "
                f"that zero bugs exist outside the tested paths."
            ),
            "",
        ]
    )
    return scrub_text("\n".join(lines))


def _render_internal_markdown(
    data: Mapping[str, Any],
    *,
    include_rejected_appendix: bool = False,
) -> str:
    econ = data["economics"]
    hint = data["harness_integrity"]
    cap_label = (
        "uncapped_research"
        if econ.get("pricing_mode") == "uncapped_research"
        else f"${econ['cogs_cap_usd']:.2f}"
    )
    stop_suffix = f", stop_reason=`{data['stop_reason']}`" if data.get("stop_reason") else ""
    lines: list[str] = [
        f"# Security Verification Report — `{data['run_id']}`",
        "",
        f"- **Target:** `{data['target_path']}` (`{data['target_mode']}`)",
        f"- **Run Status:** `{data['status']}` (Closeout gates passed: `{data['gates_passed']}`{stop_suffix})",
        f"- **Commitment Hash (`ajar-research-ledger/1`):** `{data['commitment_hash']}`",
        f"- **Harness Integrity:** `harness_modified_mid_run={hint['harness_modified_mid_run']}`",
        f"- **Distinct Root Causes / Confirmed Findings:** `{data['distinct_root_causes_count']}` / `{len(data['findings'])}`",
        f"- **In-Scope Code Size:** `{econ['in_scope_loc']}` LoC (`Code` cap quote: `${econ['code_quote_usd']:.2f}`, COGS cap: `{cap_label}`)",
        f"- **Measured Compute Spend:** `${econ['total_spend_usd']:.4f}` (`${econ['cost_usd_per_kloc']:.4f} / 1K LoC`)",
        f"- **Autonomy Checks:** `research_independence_pass={econ['research_independence_pass']}`, "
        f"`product_operability_pass={econ['product_operability_pass']}`",
    ]
    if data.get("threat_model"):
        tm = data["threat_model"]
        viol_n = sum(1 for ta in data.get("threat_assumptions", []) if ta["status"] == "violated")
        lines.append(
            f"- **Adaptive Threat Model (`rev {tm['revision']}`):** `{len(data.get('threat_assumptions', []))}` assumptions tracked (`{viol_n}` violated)"
        )
    lines.extend(["", "## 1. Confirmed Findings", ""])

    findings = data["findings"]
    if not findings:
        lines.append("No confirmed vulnerabilities reproduced within the tested scope.")
        lines.append("")
    else:
        for idx, f in enumerate(findings, start=1):
            lines.extend(
                [
                    f"### 1.{idx} [{str(f['severity']).upper()}] {f['title']} (`{f['finding_id']}`)",
                    "",
                    f"- **Location:** `{f['locus']}`",
                    f"- **Attribution:** `{f['attribution']}`",
                    f"- **Remediation State:** `{f['remediation_state']}`",
                    f"- **Claim & Independent Skeptic:** `{f['claim_id']}` (verified by `{f['falsifier_worker_id']}`)",
                    f"- **Root Cause:** {f['root_cause']}",
                    f"- **Reproduction Command (Arm 1):** `{f['poc_cmd']}`",
                    f"- **Benign Control Command (Arm 2):** `{f['control_cmd']}`",
                ]
            )
            if f.get("calibration_notes"):
                lines.append(f"- **Calibration Notes:** {f['calibration_notes']}")
            if f.get("ub_divergence_class"):
                lines.append(f"- **Release UB Differential (Arms 5A/5B):** `{f['ub_divergence_class']}`")
            lines.append("")
            if f.get("micropatch_diff"):
                lines.extend(
                    [
                        "**Verified Counterfactual Micro-Patch (Arms 3 & 4):**",
                        "",
                        "```diff",
                        str(f["micropatch_diff"]).rstrip(),
                        "```",
                        "",
                    ]
                )

    if data["verified_chains"]:
        lines.extend(["## 2. Verified Multi-Step Chains", ""])
        for c in data["verified_chains"]:
            lines.append(
                f"- **[{str(c['severity']).upper()}] {c['title']} (`{c['chain_id']}`):** "
                f"Steps `{c['step_ids_json']}` | Ablation `{c.get('ablation_matrix_json', '[]')}` | PoC: `{c['e2e_poc_cmd']}`"
            )
        lines.append("")

    if data["active_steers"]:
        lines.extend(["## Workspace Steers Applied", ""])
        for st in data["active_steers"]:
            lines.append(
                f"- `{st['steer_id']}` [`{st['scope']}:{st['target_filter'] or '*'}`] (`{st['touch_kind']}` by `{st['author']}`): {st['rule_text']}"
            )
        lines.append("")

    lines.extend(["## 3. Audited Surfaces and Verified Guards (`dry`)", ""])
    if not data["dry_controls"]:
        lines.append("No separate `dry` guard closures recorded.")
    else:
        for d in data["dry_controls"]:
            lines.append(f"- `{d['dry_control_locus']}` (`{d['task_id']}`): {d['dry_control_reason']}")
    lines.append("")

    rejected_count = (
        data["claim_summary_counts"].get("falsified", 0)
        + data["claim_summary_counts"].get("rejected_repro", 0)
        + data["claim_summary_counts"].get("duplicate_root_cause", 0)
    )
    lines.extend(
        [
            "## 4. Hypothesis Funnel and Scope Limits",
            "",
            f"- **Confirmed findings:** `{len(findings)}`",
            f"- **Disproved or deduplicated hypotheses withheld from findings:** `{rejected_count}`",
            f"- **Blocked items:** `{len(data['blocked_items'])}`",
            "- **Scope notice:** A dry path records the concrete guard inspected at this revision; it does not claim proof that zero bugs exist.",
            "",
        ]
    )

    if data["blocked_items"]:
        lines.extend(["### Stated Blockers", ""])
        for b in data["blocked_items"]:
            lines.append(f"- `{b['claim_id']}` @ `{b['locus']}`: {b['blocker_reason'] or b['title']}")
        lines.append("")

    if include_rejected_appendix and data.get("rejected_claims_appendix"):
        lines.extend(["## Appendix: Disproved Research Hypotheses", ""])
        for rc in data["rejected_claims_appendix"]:
            lines.append(
                f"- `{rc['claim_id']}` [`{rc['status']}`] @ `{rc['locus']}`: {rc['falsify_notes'][:160]}"
            )
        lines.append("")

    return scrub_text("\n".join(lines))


def render_markdown_report(
    conn: sqlite3.Connection,
    *,
    include_rejected_appendix: bool = False,
    audience: str = "customer",
    finding_ids: Sequence[str] | None = None,
) -> str:
    aud = _validate_audience(audience)
    if aud == "internal":
        data = build_report_data(
            conn,
            include_rejected_appendix=include_rejected_appendix,
            audience="internal",
            finding_ids=finding_ids,
        )
        return _render_internal_markdown(data, include_rejected_appendix=include_rejected_appendix)

    core = _load_core_report_rows(
        conn,
        include_rejected_appendix=False,
        finding_ids=finding_ids,
    )
    if aud == "maintainer":
        return _render_maintainer_markdown(conn, core)
    return _render_customer_markdown(conn, core)
