"""Living Adaptive Threat Model (`.ajar/REALITY.md`), 5 Cross-Seam Lenses, & D6 Comment-Strip Guard."""

from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path

from ajar.schemas import ajar_dir
from ajar.worktree import BUILD_PROFILES

FIVE_CROSS_SEAM_LENSES: tuple[tuple[str, str], ...] = (
    (
        "L1_PARSER_DIFFERENTIAL",
        "Gatekeeper-vs-Consumer parser disagreement (e.g. offset-0 '%!PS' check vs. '\\n%!PS' or EPT header skip).",
    ),
    (
        "L2_POLICY_ALIAS_GAP",
        "Incomplete policy, format-alias, or in-process library ('--with-gslib' / libgs) coverage.",
    ),
    (
        "L3_WRAPPER_ENGINE_SEAM",
        "High-level wrapper (Pillow/libvips/SDK) vs. 1-hop native codec/engine (libde265/libgs/zlib) geometry/buffer seam.",
    ),
    (
        "L4_MID_OP_RESIDUE",
        "Mid-operation error or callback abort leaving temp files, partial state mutation, or unrolled accounting.",
    ),
    (
        "L5_LIFETIME_ARENA_SEAM",
        "Inner reference surviving outer arena reset, save/restore boundary (systemdict UAF), or reentrant callback.",
    ),
)

SOURCE_SUFFIXES = {".py", ".c", ".cc", ".cpp", ".h", ".hpp", ".rs", ".go", ".sol", ".js", ".ts"}
SINK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("command_exec", re.compile(r"\b(system|popen|execve|execvp|subprocess\.Popen|subprocess\.run|child_process\.exec)\s*\(")),
    ("dynamic_load_or_eval", re.compile(r"\b(dlopen|eval|exec|Function)\s*\(")),
    ("memory_or_arena", re.compile(r"\b(memcpy|memmove|realloc|free)\s*\(")),
    ("filesystem_write", re.compile(r"\b(fopen|open|unlink|rename|chmod|write_text|write_bytes)\s*\(")),
    ("value_or_delegatecall", re.compile(r"\b(delegatecall|call\{value:|transferFrom|safeTransferFrom)\b")),
)
ENTRYPOINT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("cli_or_main", re.compile(r"\b(int\s+main\s*\(|def\s+main\s*\(|fn\s+main\s*\()")),
    ("http_rpc_route", re.compile(r"(@app\.(get|post|put|delete)|router\.(get|post)|def\s+handle_|func\s+ServeHTTP)")),
    ("parser_or_decoder", re.compile(r"\b(def|fn|int|bool|void)\s+[A-Za-z0-9_]*(parse|decode|read_header|unpack|load)[A-Za-z0-9_]*\s*\(")),
    ("solidity_external", re.compile(r"\bfunction\s+[A-Za-z0-9_]+\s*\([^)]*\)\s*(external|public)\b")),
)
GUARD_RE = re.compile(r"\b(if\s*\(|if\s+[^:\n]+:|require\s*\(|assert\s*\(|ensure!|if\s+err\s*!=\s*nil)")
DELEGATE_RE = re.compile(r"\b(libde265|libheif|libgs|ghostscript|zlib|libwebp|dav1d|openjpeg|libarchive|openssl)\b", re.I)


def strip_comments_and_docstrings(source: str, suffix: str) -> str:
    """Strip comments and Python docstrings while preserving line numbers (D6 prompt-injection immunity)."""
    if suffix == ".py":
        doc_ranges: list[tuple[int, int]] = []
        try:
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
                    first = node.body[0]
                    if (
                        isinstance(first, ast.Expr)
                        and isinstance(first.value, ast.Constant)
                        and isinstance(first.value.value, str)
                    ):
                        doc_ranges.append((first.lineno, getattr(first, "end_lineno", first.lineno)))
        except SyntaxError:
            pass
        lines = source.splitlines()
        try:
            for tok in tokenize.generate_tokens(io.StringIO(source).readline):
                if tok.type == tokenize.COMMENT:
                    ln_idx = tok.start[0] - 1
                    col = tok.start[1]
                    if 0 <= ln_idx < len(lines):
                        lines[ln_idx] = lines[ln_idx][:col]
        except tokenize.TokenError:
            pass
        for start_ln, end_ln in doc_ranges:
            for idx in range(start_ln - 1, min(end_ln, len(lines))):
                lines[idx] = ""
        return "\n".join(lines)

    def _blank_block(match: re.Match[str]) -> str:
        return "\n" * match.group(0).count("\n")

    no_block = re.sub(r"/\*.*?\*/", _blank_block, source, flags=re.S)
    return re.sub(r"//[^\n]*", "", no_block)


def has_real_code_guard(source: str, suffix: str, sink_lineno: int, window: int = 10) -> bool:
    """Return True only when comment-stripped code above `sink_lineno` contains an actual guard branch."""
    stripped_lines = strip_comments_and_docstrings(source, suffix).splitlines()
    lo = max(0, sink_lineno - 1 - window)
    hi = min(len(stripped_lines), sink_lineno)
    snippet = "\n".join(stripped_lines[lo:hi])
    return bool(GUARD_RE.search(snippet))


def _find_security_md(repo: Path) -> Path | None:
    for rel in ("SECURITY.md", ".github/SECURITY.md", "docs/SECURITY.md"):
        cand = repo / rel
        if cand.is_file():
            return cand
    return None


def record_falsified_hypothesis(repo: Path, summary: str) -> None:
    reality_path = ajar_dir(repo) / "REALITY.md"
    if not reality_path.exists():
        build_reality_model(repo)
    text = reality_path.read_text(encoding="utf-8")
    bullet = f"- {summary.strip()}\n"
    if bullet in text:
        return
    with reality_path.open("a", encoding="utf-8") as fh:
        fh.write(bullet)


def build_reality_model(repo: Path, profiles: tuple[str, ...] = ("upstream",)) -> Path:
    """Build or refresh `<repo>/.ajar/REALITY.md` (works with or without `SECURITY.md`)."""
    repo = repo.resolve()
    for prof in profiles:
        if prof not in BUILD_PROFILES:
            raise ValueError(f"Unknown profile {prof!r}")
    out_path = ajar_dir(repo) / "REALITY.md"
    preserved_falsified: list[str] = []
    if out_path.exists():
        old = out_path.read_text(encoding="utf-8")
        if "## Falsified Hypotheses (Do Not Repeat)" in old:
            tail = old.split("## Falsified Hypotheses (Do Not Repeat)", 1)[1]
            preserved_falsified = [ln for ln in tail.splitlines() if ln.strip().startswith("- ")]

    sec_md = _find_security_md(repo)
    entrypoints: list[str] = []
    sinks: list[str] = []
    delegates: set[str] = set()

    for path in sorted(repo.rglob("*")):
        if not path.is_file() or any(p.startswith(".ajar") or p == ".git" for p in path.parts):
            continue
        rel = path.relative_to(repo)
        if path.name in {"CMakeLists.txt", "Cargo.toml", "pyproject.toml", "package.json", "Makefile"}:
            txt = path.read_text(encoding="utf-8", errors="ignore")
            delegates.update(m.group(1).lower() for m in DELEGATE_RE.finditer(txt))
        if path.suffix not in SOURCE_SUFFIXES:
            continue
        raw = path.read_text(encoding="utf-8", errors="ignore")
        stripped = strip_comments_and_docstrings(raw, path.suffix)
        for lineno, line in enumerate(stripped.splitlines(), start=1):
            if len(entrypoints) < 40:
                for kind, pat in ENTRYPOINT_PATTERNS:
                    if pat.search(line):
                        entrypoints.append(f"- `{rel}:{lineno}` (`{kind}`): `{line.strip()[:90]}`")
                        break
            if len(sinks) < 60:
                for kind, pat in SINK_PATTERNS:
                    if pat.search(line):
                        tag = "[CODE-GUARDED]" if has_real_code_guard(raw, path.suffix, lineno) else "[UNGUARDED IN CODE]"
                        sinks.append(f"- `{rel}:{lineno}` (`{kind}`) {tag}: `{line.strip()[:90]}`")
                        break

    mode_line = (
        f"DOCUMENTED + ADAPTIVE (Anchored to `{sec_md.relative_to(repo)}`)"
        if sec_md
        else "ADAPTIVE (No `SECURITY.md` found — synthesized directly from entrypoints & Crown-Jewel sinks)"
    )
    sec_excerpt = ""
    if sec_md:
        sec_excerpt = "\n".join(sec_md.read_text(encoding="utf-8", errors="ignore").splitlines()[:25]).strip()

    sections = [
        f"# Living Reality & Threat Model — `{repo.name}`",
        "",
        f"- **Threat Model Mode:** {mode_line}",
        f"- **Locked Shipped Build Profiles (`D2`):** `{', '.join(profiles)}`",
        f"- **1-Hop Data-Plane Delegates Detected (`D1`):** `{', '.join(sorted(delegates)) or 'none detected'}`",
        "",
    ]
    if sec_excerpt:
        sections.extend(["## Maintainer Security Claims (`SECURITY.md` Excerpt)", "```text", sec_excerpt, "```", ""])
    sections.extend(["## Five Cross-Seam 'Bug Brain' Lenses", ""])
    for code, desc in FIVE_CROSS_SEAM_LENSES:
        sections.append(f"- **`{code}`**: {desc}")
    sections.extend(
        [
            "",
            "## Untrusted Entrypoints (Front Doors)",
            *(entrypoints or ["- None auto-indexed; inspect public CLI/API surfaces with `rg`."]),
            "",
            "## Backwards Crown-Jewel Sinks (Comment-Stripped Guard Check `D6`)",
            *(sinks or ["- None auto-indexed; map domain-specific accounting/state sinks."]),
            "",
            "## Falsified Hypotheses (Do Not Repeat)",
            *preserved_falsified,
            "",
        ]
    )
    out_path.write_text("\n".join(sections), encoding="utf-8")
    return out_path
