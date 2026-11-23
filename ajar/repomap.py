"""In-scope LoC accounting (`DEC-0122`) and pure-Python Personalized PageRank RepoMap.

Provides fast, zero-dependency code sizing (`Code` hard-cap quote calculator) and
symbol graph ranking so workers inspect high-centrality trust boundaries within
a bounded token budget (`--budget-tokens 1500`).
"""

from __future__ import annotations

import ast
import math
import os
import pathlib
import re
import sqlite3
from typing import Any, Sequence

from ajar.store import immediate_tx

SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        "vendor",
        "target",
        "dist",
        "build",
        "out",
        "__pycache__",
        ".venv",
        "venv",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".ajar",
        ".next",
        "coverage",
    }
)

SKIP_FILES: frozenset[str] = frozenset(
    {
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "Cargo.lock",
        "go.sum",
        "poetry.lock",
        "uv.lock",
        "composer.lock",
    }
)

CODE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".py",
        ".rs",
        ".go",
        ".c",
        ".h",
        ".cc",
        ".cpp",
        ".cxx",
        ".hpp",
        ".sol",
        ".move",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".mjs",
        ".java",
        ".kt",
        ".rb",
        ".php",
        ".sh",
        ".zig",
    }
)
SOURCE_EXTENSIONS = CODE_EXTENSIONS

REPOMAP_EDGE_CAP = 25_000

_C_EXTENSIONS: frozenset[str] = frozenset({".c", ".h", ".cc", ".cpp", ".cxx", ".hpp"})
_C_SOURCE_EXTENSIONS: frozenset[str] = frozenset({".c", ".cc", ".cpp", ".cxx"})
_IGNORED_SYMBOL_NAMES: frozenset[str] = frozenset(
    {"if", "for", "while", "switch", "return", "sizeof", "else", "catch", "case", "goto", "delete", "new"}
)
_C_MULTILINE_FN_NAME_RE = re.compile(
    r"^\*?(?:[A-Za-z_][A-Za-z0-9_]*::)?([A-Za-z_][A-Za-z0-9_]*)\s*\([^;]*$"
)
_C_RETURN_TYPE_LINE_RE = re.compile(
    r"^(?:(?:static|inline|extern|virtual|constexpr|const|volatile|unsigned|signed|struct|enum|union|"
    r"__attribute__\s*\(\([^)]*\)\))\s+)*[A-Za-z_][A-Za-z0-9_:<>]*[\s\*&]*$"
)

SYMBOL_PATTERNS: dict[str, tuple[tuple[str, re.Pattern[str]], ...]] = {
    ".rs": (
        ("fn", re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:unsafe\s+)?fn\s+([A-Za-z_][A-Za-z0-9_]*)")),
        ("struct", re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?struct\s+([A-Za-z_][A-Za-z0-9_]*)")),
        ("enum", re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?enum\s+([A-Za-z_][A-Za-z0-9_]*)")),
        ("trait", re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?trait\s+([A-Za-z_][A-Za-z0-9_]*)")),
    ),
    ".go": (
        ("func", re.compile(r"^\s*func\s+(?:\([^)]+\)\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*\(")),
        ("type", re.compile(r"^\s*type\s+([A-Za-z_][A-Za-z0-9_]*)\s+(?:struct|interface)\b")),
    ),
    ".sol": (
        ("contract", re.compile(r"^\s*(?:abstract\s+)?(?:contract|library|interface)\s+([A-Za-z_][A-Za-z0-9_]*)")),
        ("function", re.compile(r"^\s*function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")),
        ("modifier", re.compile(r"^\s*modifier\s+([A-Za-z_][A-Za-z0-9_]*)\b")),
    ),
    ".ts": (
        ("function", re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*[(<]")),
        ("class", re.compile(r"^\s*(?:export\s+)?class\s+([A-Za-z_$][A-Za-z0-9_$]*)")),
        ("interface", re.compile(r"^\s*(?:export\s+)?interface\s+([A-Za-z_$][A-Za-z0-9_$]*)")),
    ),
    ".c": (
        (
            "func",
            re.compile(
                r"^(?:(?:static|inline|extern|virtual|constexpr|const|volatile|unsigned|signed|struct|enum|union)\s+)*"
                r"[A-Za-z_][A-Za-z0-9_:*&<>]*[\s\*&]+(?:[A-Za-z_][A-Za-z0-9_]*::)?([A-Za-z_][A-Za-z0-9_]*)\s*\([^;]*$"
            ),
        ),
        ("struct", re.compile(r"^\s*typedef\s+struct\s+([A-Za-z_][A-Za-z0-9_]*)")),
        ("struct", re.compile(r"^\s*(?:struct|class|enum|union)\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?::[^{;]+)?\{")),
    ),
    ".java": (
        (
            "class",
            re.compile(
                r"^\s*(?:(?:public|protected|private|abstract|final|static|sealed|non-sealed)\s+)*"
                r"(?:class|interface|enum|record)\s+([A-Za-z_][A-Za-z0-9_]*)"
            ),
        ),
        (
            "method",
            re.compile(
                r"^\s*(?:(?:public|protected|private|static|final|synchronized|abstract|native|default)\s+)+"
                r"(?:<[^>{;]+>\s+)?[A-Za-z_][A-Za-z0-9_<>\[\].,?\s]*\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("
            ),
        ),
    ),
    ".php": (
        (
            "class",
            re.compile(
                r"^\s*(?:(?:abstract|final|readonly)\s+)*(?:class|interface|trait|enum)\s+([A-Za-z_][A-Za-z0-9_]*)"
            ),
        ),
        (
            "function",
            re.compile(
                r"^\s*(?:(?:public|protected|private|static|final|abstract)\s+)*function\s+&?([A-Za-z_][A-Za-z0-9_]*)\s*\("
            ),
        ),
    ),
    ".move": (
        ("module", re.compile(r"^\s*module\s+(?:[A-Za-z0-9_]+::)?([A-Za-z_][A-Za-z0-9_]*)")),
        (
            "fun",
            re.compile(
                r"^\s*(?:public(?:\([^)]*\))?\s+)?(?:entry\s+)?(?:native\s+)?(?:inline\s+)?fun\s+([A-Za-z_][A-Za-z0-9_]*)"
            ),
        ),
        ("struct", re.compile(r"^\s*(?:public\s+)?struct\s+([A-Za-z_][A-Za-z0-9_]*)")),
    ),
    ".zig": (
        (
            "fn",
            re.compile(
                r'^\s*(?:pub\s+)?(?:export\s+)?(?:extern(?:\s+"[^"]*")?\s+)?(?:inline\s+|noinline\s+)?fn\s+([A-Za-z_][A-Za-z0-9_]*)\s*\('
            ),
        ),
        (
            "type",
            re.compile(
                r"^\s*(?:pub\s+)?const\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:packed\s+|extern\s+)?(?:struct|enum|union)\b"
            ),
        ),
    ),
}
for _alias, _src in (
    (".tsx", ".ts"),
    (".js", ".ts"),
    (".jsx", ".ts"),
    (".mjs", ".ts"),
    (".h", ".c"),
    (".cc", ".c"),
    (".cpp", ".c"),
    (".cxx", ".c"),
    (".hpp", ".c"),
):
    SYMBOL_PATTERNS[_alias] = SYMBOL_PATTERNS[_src]

IDENT_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b")


def compute_code_quote_usd(total_loc: int) -> float:
    """Compute `Code` hard-cap run price (`DEC-0122`):
    4¢/line, $10 min, $40 cap up to 8,000 LoC, +$5/1K LoC up to 50,000 LoC.
    """
    if total_loc <= 0:
        return 10.0
    if total_loc <= 8000:
        return round(max(10.0, min(40.0, 0.04 * total_loc)), 2)
    extra_kloc = (min(total_loc, 50_000) - 8000) / 1000.0
    return round(40.0 + 5.0 * extra_kloc, 2)


def iter_source_files(target_dir: pathlib.Path) -> list[pathlib.Path]:
    root = target_dir.resolve()
    if root.is_file():
        return [root]
    out: list[pathlib.Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        rel_dir = pathlib.Path(dirpath).relative_to(root)
        dirnames[:] = sorted(
            d
            for d in dirnames
            if d not in SKIP_DIRS
            and not (rel_dir == pathlib.Path("tools") and d == "legacy")
            and not (rel_dir == pathlib.Path(".") and d == "engagements")
        )
        for fname in sorted(filenames):
            if fname in SKIP_FILES:
                continue
            fpath = pathlib.Path(dirpath) / fname
            if fpath.is_symlink():
                continue
            if fpath.suffix.lower() in CODE_EXTENSIONS:
                out.append(fpath)
    return out


def count_in_scope_loc(target_dir: pathlib.Path) -> dict[str, Any]:
    """Count non-blank, non-comment in-scope lines of code and compute `Code` quote."""
    files = iter_source_files(target_dir)
    total_loc = 0
    by_ext: dict[str, int] = {}
    counted_files = 0

    for fpath in files:
        try:
            raw = fpath.read_bytes()
        except OSError:
            continue
        if b"\x00" in raw[:4096]:
            continue
        text = raw.decode("utf-8", errors="ignore")
        ext = fpath.suffix.lower()
        file_loc = 0
        in_block_comment = False
        for line in text.splitlines():
            s = line.strip()
            if not s:
                continue
            if in_block_comment:
                if "*/" in s:
                    in_block_comment = False
                continue
            if s.startswith("/*"):
                if "*/" not in s[2:]:
                    in_block_comment = True
                continue
            if ext in (".py", ".sh", ".rb") and s.startswith("#"):
                continue
            if ext not in (".py", ".sh", ".rb") and (s.startswith("//") or s.startswith("*")):
                continue
            file_loc += 1
        total_loc += file_loc
        counted_files += 1
        by_ext[ext] = by_ext.get(ext, 0) + file_loc

    return {
        "total_loc": total_loc,
        "files_counted": counted_files,
        "by_ext": dict(sorted(by_ext.items())),
        "code_quote_usd": compute_code_quote_usd(total_loc),
        "exceeds_single_run_cap": total_loc > 50_000,
    }


def compute_cogs_cap_usd(code_quote_usd: float, ratio: float = 0.35) -> float:
    """Compute default commercial COGS cap (`<= 0.35 * quote`, preserving `>= 65%` gross margin)."""
    return round(max(1.0, float(code_quote_usd) * float(ratio)), 2)


def count_diff_loc(target_dir: pathlib.Path, diff_range: str) -> dict[str, Any]:
    """Count changed code lines in a git diff range (`base..head`) for PR `Code` sizing."""
    import subprocess

    root = target_dir.resolve()
    if root.is_file():
        root = root.parent
    proc = subprocess.run(
        ["git", "-C", str(root), "diff", "--numstat", diff_range],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise ValueError(f"git diff --numstat failed for {diff_range!r}: {proc.stderr.strip()[:200]}")

    changed_loc = 0
    files_counted = 0
    by_ext: dict[str, int] = {}
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        added_s, deleted_s, rel_path = parts[0].strip(), parts[1].strip(), parts[2].strip()
        if added_s == "-" or deleted_s == "-":
            continue
        p = pathlib.PurePosixPath(rel_path)
        if p.name in SKIP_FILES or any(seg in SKIP_DIRS for seg in p.parts):
            continue
        ext = p.suffix.lower()
        if ext not in CODE_EXTENSIONS:
            continue
        delta = int(added_s) + int(deleted_s)
        if delta <= 0:
            continue
        changed_loc += delta
        files_counted += 1
        by_ext[ext] = by_ext.get(ext, 0) + delta

    quote_usd = compute_code_quote_usd(changed_loc)
    return {
        "total_loc": changed_loc,
        "files_counted": files_counted,
        "by_ext": dict(sorted(by_ext.items())),
        "code_quote_usd": quote_usd,
        "exceeds_single_run_cap": changed_loc > 50_000,
        "diff_range": diff_range,
    }


def compute_quote_summary(target_dir: pathlib.Path, diff_range: str | None = None) -> dict[str, Any]:
    """Build deterministic pre-run `Code` quote and default `0.35 * quote` COGS budget cap."""
    import hashlib
    import json

    sizing = count_diff_loc(target_dir, diff_range) if diff_range else count_in_scope_loc(target_dir)
    quote_usd = float(sizing["code_quote_usd"])
    cogs_cap = compute_cogs_cap_usd(quote_usd)
    canonical = json.dumps(
        {
            "diff_range": diff_range or "",
            "files_counted": sizing["files_counted"],
            "in_scope_loc": sizing["total_loc"],
            "target": str(target_dir.resolve()),
        },
        sort_keys=True,
    ).encode("utf-8")
    quote_id = "qte-" + hashlib.sha256(canonical).hexdigest()[:10]
    return {
        "quote_id": quote_id,
        "target_path": str(target_dir.resolve()),
        "scope_mode": "diff" if diff_range else "full_repo",
        "diff_range": diff_range or "",
        "in_scope_loc": int(sizing["total_loc"]),
        "files_counted": int(sizing["files_counted"]),
        "by_ext": sizing["by_ext"],
        "code_quote_usd": quote_usd,
        "cogs_cap_usd": cogs_cap,
        "recommended_cogs_cap_usd": cogs_cap,
        "gross_margin_floor_pct": 65.0,
        "exceeds_single_run_cap": bool(sizing["exceeds_single_run_cap"]),
    }


def _extract_python_symbols(rel_path: str, text: str) -> list[dict[str, Any]]:
    symbols: list[dict[str, Any]] = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return symbols
    lines = text.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            kind = "class" if isinstance(node, ast.ClassDef) else "def"
            lineno = int(getattr(node, "lineno", 1))
            sig = lines[lineno - 1].strip() if 1 <= lineno <= len(lines) else f"{kind} {node.name}"
            symbols.append(
                {
                    "rel_path": rel_path,
                    "name": node.name,
                    "kind": kind,
                    "line_no": lineno,
                    "signature": sig[:120],
                }
            )
    return sorted(symbols, key=lambda x: int(x["line_no"]))


def _c_looks_like_definition(lines: list[str], start_idx: int) -> bool:
    """Return True if a C/C++ function signature starting at `start_idx` opens a `{` body rather than ending with `;`."""
    depth = 0
    seen_open = False
    limit = min(len(lines), start_idx + 14)
    for j in range(start_idx, limit):
        raw = lines[j]
        code = raw.split("//", 1)[0]
        for ch in code:
            if ch == "(":
                depth += 1
                seen_open = True
            elif ch == ")":
                if depth > 0:
                    depth -= 1
            elif seen_open and depth == 0:
                if ch == "{":
                    return True
                if ch == ";":
                    return False
    return False


def _is_c_return_type_header(line: str) -> bool:
    if not line or line[0].isspace():
        return False
    stripped = line.split("//", 1)[0].strip()
    if not stripped or stripped.startswith(("#", "/*", "*", "{", "}", ";")):
        return False
    if stripped.endswith((";", "{", "}", ":", ",")) or "=" in stripped:
        return False
    if stripped in _IGNORED_SYMBOL_NAMES or stripped in {"do", "try"}:
        return False
    return _C_RETURN_TYPE_LINE_RE.match(stripped) is not None


def _extract_regex_symbols(rel_path: str, ext: str, text: str) -> list[dict[str, Any]]:
    patterns = SYMBOL_PATTERNS.get(ext, ())
    if not patterns:
        return []
    is_c_like = ext in _C_EXTENSIONS
    is_c_source = ext in _C_SOURCE_EXTENSIONS
    lines = text.splitlines()
    symbols: list[dict[str, Any]] = []
    for idx, line in enumerate(lines, start=1):
        matched = False
        for kind, pat in patterns:
            m = pat.search(line)
            if m:
                matched = True
                name = m.group(1)
                if name not in _IGNORED_SYMBOL_NAMES:
                    file_local = bool(is_c_source and re.match(r"^\s*static\b", line))
                    symbols.append(
                        {
                            "rel_path": rel_path,
                            "name": name,
                            "kind": kind,
                            "line_no": idx,
                            "signature": line.strip()[:120],
                            "file_local": file_local,
                        }
                    )
                break
        if not matched and is_c_like and idx >= 2 and line and not line[0].isspace():
            mm = _C_MULTILINE_FN_NAME_RE.match(line)
            if mm:
                name = mm.group(1)
                prev_idx = idx - 2
                if (
                    name not in _IGNORED_SYMBOL_NAMES
                    and _is_c_return_type_header(lines[prev_idx])
                    and _c_looks_like_definition(lines, idx - 1)
                ):
                    header_parts = [lines[prev_idx].strip()]
                    if prev_idx >= 1 and _is_c_return_type_header(lines[prev_idx - 1]):
                        header_parts.insert(0, lines[prev_idx - 1].strip())
                    header_prefix = " ".join(header_parts)
                    file_local = bool(is_c_source and re.search(r"\bstatic\b", header_prefix))
                    symbols.append(
                        {
                            "rel_path": rel_path,
                            "name": name,
                            "kind": "func",
                            "line_no": idx,
                            "signature": f"{header_prefix} {line.strip()}"[:120],
                            "file_local": file_local,
                        }
                    )
    return symbols


def _personalized_pagerank(
    nodes: Sequence[str],
    out_edges: dict[str, dict[str, float]],
    personalization: dict[str, float],
    *,
    damping: float = 0.85,
    iterations: int = 25,
) -> dict[str, float]:
    n = len(nodes)
    if n == 0:
        return {}
    p_total = sum(personalization.values())
    if p_total <= 0:
        p = {u: 1.0 / n for u in nodes}
    else:
        p = {u: personalization.get(u, 0.0) / p_total for u in nodes}

    ranks = dict(p)
    for _ in range(iterations):
        nxt = {u: (1.0 - damping) * p[u] for u in nodes}
        dangling_mass = 0.0
        for u in nodes:
            nbrs = out_edges.get(u)
            if not nbrs:
                dangling_mass += ranks[u]
                continue
            w_sum = sum(nbrs.values())
            if w_sum <= 0:
                dangling_mass += ranks[u]
                continue
            share = damping * ranks[u] / w_sum
            for v, w in nbrs.items():
                nxt[v] = nxt.get(v, 0.0) + share * w
        if dangling_mass > 0:
            for u in nodes:
                nxt[u] += damping * dangling_mass * p[u]
        ranks = nxt
    return ranks


def _partition_call_slices(
    ranked_files: Sequence[str],
    file_locs: dict[str, int],
    out_edges: dict[str, dict[str, float]],
    symbols_by_file: dict[str, list[dict[str, Any]]],
    *,
    slice_cap: int = 15000,
) -> list[dict[str, Any]]:
    """Partition ranked files + 1-hop call neighbors into cohesive subsystem call cones (`<= slice_cap` LoC)."""
    cap = max(250, int(slice_cap))
    assigned_files: set[str] = set()
    slices: list[dict[str, Any]] = []

    for seed in ranked_files:
        if seed in assigned_files:
            continue
        seed_loc = max(1, int(file_locs.get(seed, 1)))
        if seed_loc > cap:
            # Split oversized file along symbol boundaries into `<= cap` line ranges.
            assigned_files.add(seed)
            syms = symbols_by_file.get(seed, [])
            cur_start = 1
            while cur_start <= seed_loc:
                cur_end = min(seed_loc, cur_start + cap - 1)
                # Snap `cur_end` to the last symbol start inside `(cur_start + cap//2 .. cur_end)` if possible.
                boundary_syms = [
                    int(s["line_no"]) - 1
                    for s in syms
                    if (cur_start + cap // 2) <= int(s["line_no"]) <= cur_end
                ]
                if boundary_syms and cur_end < seed_loc:
                    cur_end = max(cur_start, boundary_syms[-1])
                span_loc = cur_end - cur_start + 1
                slices.append(
                    {
                        "slice_id": f"slc-{len(slices) + 1:03d}",
                        "seed_locus": f"{seed}:{cur_start}-{cur_end}",
                        "files": [f"{seed}:{cur_start}-{cur_end}"],
                        "total_loc": span_loc,
                    }
                )
                cur_start = cur_end + 1
            continue

        assigned_files.add(seed)
        cluster = [seed]
        cluster_loc = seed_loc
        nbrs = sorted(out_edges.get(seed, {}).items(), key=lambda kv: (-kv[1], kv[0]))
        for nbr_file, _w in nbrs:
            if nbr_file in assigned_files:
                continue
            n_loc = max(1, int(file_locs.get(nbr_file, 1)))
            if cluster_loc + n_loc <= cap:
                assigned_files.add(nbr_file)
                cluster.append(nbr_file)
                cluster_loc += n_loc

        slices.append(
            {
                "slice_id": f"slc-{len(slices) + 1:03d}",
                "seed_locus": f"{seed}:1",
                "files": cluster,
                "total_loc": cluster_loc,
            }
        )
    return slices


def build_repomap(
    conn: sqlite3.Connection,
    target_dir: pathlib.Path,
    *,
    focus_files: Sequence[str] = (),
    focus_symbols: Sequence[str] = (),
    budget_tokens: int = 1500,
    slice_cap: int = 15000,
    max_edges: int = REPOMAP_EDGE_CAP,
    unvisited_only: bool = False,
) -> dict[str, Any]:
    """Extract symbols, compute Personalized PageRank + cohesive subsystem call cones (`<= slice_cap` LoC), and render under `budget_tokens`."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS repomap_symbols (
            symbol_id TEXT PRIMARY KEY,
            rel_path TEXT NOT NULL,
            name TEXT NOT NULL,
            kind TEXT NOT NULL,
            line_no INTEGER NOT NULL,
            pagerank REAL NOT NULL DEFAULT 0.0,
            signature TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS repomap_edges (
            src_file TEXT NOT NULL,
            dst_file TEXT NOT NULL,
            symbol TEXT NOT NULL,
            weight REAL NOT NULL DEFAULT 1.0
        );
        """
    )

    root = target_dir.resolve()
    files = iter_source_files(root)
    base_root = root.parent if root.is_file() else root

    file_texts: dict[str, str] = {}
    file_locs: dict[str, int] = {}
    symbols_by_file: dict[str, list[dict[str, Any]]] = {}
    defs_by_name: dict[str, set[str]] = {}
    subsystems_loc: dict[str, int] = {}

    for fpath in files:
        try:
            raw = fpath.read_bytes()
        except OSError:
            continue
        if b"\x00" in raw[:4096]:
            continue
        rel = str(fpath.relative_to(base_root))
        text = raw.decode("utf-8", errors="ignore")
        file_texts[rel] = text
        loc_n = max(1, len(text.splitlines()))
        file_locs[rel] = loc_n
        parts = [p for p in rel.split("/") if p]
        sub_key = "/".join(parts[:2]) if len(parts) >= 2 else (parts[0] if parts else "root")
        subsystems_loc[sub_key] = subsystems_loc.get(sub_key, 0) + loc_n
        ext = fpath.suffix.lower()
        syms = _extract_python_symbols(rel, text) if ext == ".py" else _extract_regex_symbols(rel, ext, text)
        symbols_by_file[rel] = syms
        for s in syms:
            if not s.get("file_local", False):
                defs_by_name.setdefault(str(s["name"]), set()).add(rel)

    nodes = sorted(file_texts.keys())
    out_edges: dict[str, dict[str, float]] = {u: {} for u in nodes}
    # Aggregate per `(src_file, dst_file)`: summed IDF weight + highest-weight symbol.
    agg_edges: dict[tuple[str, str], tuple[float, float, str]] = {}

    for src_rel in nodes:
        text = file_texts[src_rel]
        mentioned = set(IDENT_RE.findall(text))
        for ident in mentioned:
            definers = defs_by_name.get(ident)
            if not definers or len(definers) > 25:
                continue
            idf_weight = 1.0 / math.sqrt(len(definers))
            for dst_rel in definers:
                if dst_rel == src_rel:
                    continue
                out_edges[src_rel][dst_rel] = out_edges[src_rel].get(dst_rel, 0.0) + idf_weight
                key = (src_rel, dst_rel)
                prev = agg_edges.get(key)
                if prev is None:
                    agg_edges[key] = (idf_weight, idf_weight, ident)
                else:
                    total_w, top_w, top_sym = prev
                    if (idf_weight > top_w) or (idf_weight == top_w and ident < top_sym):
                        top_w, top_sym = idf_weight, ident
                    agg_edges[key] = (total_w + idf_weight, top_w, top_sym)

    edge_rows: list[tuple[str, str, str, float]] = [
        (src_rel, dst_rel, top_sym, round(total_w, 4))
        for (src_rel, dst_rel), (total_w, _top_w, top_sym) in agg_edges.items()
    ]
    edge_rows.sort(key=lambda row: (-row[3], row[0], row[1]))
    edge_cap = max(1, int(max_edges))
    persisted_edges = edge_rows[:edge_cap]

    focus_file_set = {f.strip().lstrip("./") for f in focus_files if f.strip()}
    focus_sym_set = {s.strip() for s in focus_symbols if s.strip()}
    personalization: dict[str, float] = {}
    for u in nodes:
        w = 1.0
        if u in focus_file_set or any(u.endswith(ff) for ff in focus_file_set):
            w += 10.0
        if focus_sym_set and any(s["name"] in focus_sym_set for s in symbols_by_file.get(u, [])):
            w += 10.0
        personalization[u] = w

    file_ranks = _personalized_pagerank(nodes, out_edges, personalization)

    all_symbols: list[dict[str, Any]] = []
    symbol_params: list[tuple[str, str, str, str, int, float, str]] = []
    for rel, syms in symbols_by_file.items():
        f_rank = round(float(file_ranks.get(rel, 0.0)), 6)
        for s in syms:
            sym_boost = 1.5 if s["name"] in focus_sym_set else 1.0
            s_rank = round(f_rank * sym_boost, 6)
            sym_id = f"{rel}:{s['line_no']}:{s['name']}"
            row = {**s, "symbol_id": sym_id, "pagerank": s_rank}
            all_symbols.append(row)
            symbol_params.append((sym_id, rel, s["name"], s["kind"], s["line_no"], s_rank, s["signature"]))

    with immediate_tx(conn):
        conn.execute("DELETE FROM repomap_symbols")
        conn.execute("DELETE FROM repomap_edges")
        if symbol_params:
            conn.executemany(
                """
                INSERT OR REPLACE INTO repomap_symbols(
                    symbol_id, rel_path, name, kind, line_no, pagerank, signature
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                symbol_params,
            )
        if persisted_edges:
            conn.executemany(
                "INSERT INTO repomap_edges(src_file, dst_file, symbol, weight) VALUES (?, ?, ?, ?)",
                persisted_edges,
            )

    visited_files: set[str] = set()
    has_cov = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='coverage_spans'"
    ).fetchone()
    if has_cov:
        for r in conn.execute("SELECT DISTINCT rel_path FROM coverage_spans").fetchall():
            rp = str(r[0] or "").strip().lstrip("./")
            if rp in file_locs:
                visited_files.add(rp)
    has_tasks = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='tasks'"
    ).fetchone()
    if has_tasks:
        for r in conn.execute("SELECT locus FROM tasks WHERE status IN ('done', 'dry') AND locus != ''").fetchall():
            rp = str(r[0] or "").split(":", 1)[0].strip().lstrip("./")
            if rp in file_locs:
                visited_files.add(rp)

    total_loc = sum(file_locs.values())
    visited_loc = sum(file_locs[f] for f in visited_files)
    scout_coverage_pct = round((100.0 * visited_loc / total_loc), 2) if total_loc > 0 else 0.0

    ranked_files = sorted(nodes, key=lambda u: (-file_ranks.get(u, 0.0), u))
    all_call_slices = _partition_call_slices(
        ranked_files, file_locs, out_edges, symbols_by_file, slice_cap=slice_cap
    )
    unvisited_slices = [
        slc
        for slc in all_call_slices
        if any(f.split(":", 1)[0] not in visited_files for f in slc["files"])
    ]
    call_slices = unvisited_slices if unvisited_only else all_call_slices
    render_files = (
        [f for f in ranked_files if f not in visited_files]
        if unvisited_only
        else ranked_files
    )

    # Compact `< 1 KB` structural skeleton for 100K+ LoC repositories.
    top_subs = sorted(subsystems_loc.items(), key=lambda kv: (-kv[1], kv[0]))[:8]
    skel_lines = [
        f"# Repo Skeleton ({len(nodes)} files, {total_loc} lines, {len(call_slices)} slice(s) <= {int(slice_cap)} LoC, scout_coverage={scout_coverage_pct:.1f}%)",
        "Subsystems: " + ", ".join(f"{k}({v}L)" for k, v in top_subs),
    ]
    for slc in call_slices[:8]:
        skel_lines.append(f"- {slc['slice_id']}: {slc['seed_locus']} ({slc['total_loc']}L, {len(slc['files'])} file(s))")
    skeleton_md = "\n".join(skel_lines)
    if len(skeleton_md.encode("utf-8")) > 960:
        skeleton_md = skeleton_md.encode("utf-8")[:960].decode("utf-8", errors="ignore")

    char_budget = max(256, int(budget_tokens) * 4)
    mode_lbl = " [unvisited only]" if unvisited_only else ""
    lines: list[str] = [
        f"# Repository Map{mode_lbl} ({len(render_files)}/{len(nodes)} files, {len(call_slices)} slices <= {int(slice_cap)} LoC, scout_coverage={scout_coverage_pct:.1f}%)"
    ]
    used_chars = len(lines[0]) + 1

    included_symbols: list[dict[str, Any]] = []
    for rel in render_files:
        header = f"\n## {rel} (rank={file_ranks.get(rel, 0.0):.4f}, lines={file_locs.get(rel, 0)})"
        if used_chars + len(header) + 1 > char_budget:
            break
        lines.append(header)
        used_chars += len(header) + 1
        syms = symbols_by_file.get(rel, [])
        for s in syms[:16]:
            entry = f"  L{s['line_no']}: {s['signature']}"
            if used_chars + len(entry) + 1 > char_budget:
                break
            lines.append(entry)
            used_chars += len(entry) + 1
            included_symbols.append({**s, "pagerank": round(file_ranks.get(rel, 0.0), 6)})

    rendered = "\n".join(lines)
    return {
        "files_indexed": len(nodes),
        "visited_files_count": len(visited_files),
        "scout_coverage_pct": scout_coverage_pct,
        "unvisited_only": bool(unvisited_only),
        "symbols_indexed": len(all_symbols),
        "edges_indexed": len(persisted_edges),
        "edges_total": len(edge_rows),
        "slice_cap": int(slice_cap),
        "slice_count": len(call_slices),
        "unvisited_slice_count": len(unvisited_slices),
        "call_slices": call_slices,
        "unvisited_slices": unvisited_slices,
        "skeleton_md": skeleton_md,
        "token_estimate": max(1, len(rendered) // 4),
        "symbols": included_symbols,
        "rendered": rendered,
    }


def list_unvisited_slices(
    conn: sqlite3.Connection,
    *,
    target_dir: pathlib.Path | None = None,
    slice_cap: int = 15000,
    limit: int = 25,
    populate_if_empty: bool = False,
) -> list[dict[str, Any]]:
    """Return PageRank-ordered unvisited repository call slices (`coverage_spans` + closed `tasks` excluded)."""
    tables = {
        str(r[0])
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    resolved_target = target_dir
    target_mode = "source"
    if resolved_target is None and "runs" in tables:
        rrow = conn.execute("SELECT target_path, target_mode FROM runs LIMIT 1").fetchone()
        if rrow is not None:
            target_mode = str(rrow["target_mode"] or "source")
            raw_tp = str(rrow["target_path"] or "").strip()
            if raw_tp and target_mode == "source":
                resolved_target = pathlib.Path(raw_tp)

    sym_count = (
        int(conn.execute("SELECT COUNT(*) AS c FROM repomap_symbols").fetchone()["c"])
        if "repomap_symbols" in tables
        else 0
    )
    if (
        populate_if_empty
        and sym_count == 0
        and target_mode == "source"
        and resolved_target is not None
        and resolved_target.exists()
    ):
        build_repomap(conn, resolved_target, slice_cap=slice_cap, unvisited_only=True)
        tables.update({"repomap_symbols", "repomap_edges"})

    visited_files: set[str] = set()
    if "coverage_spans" in tables:
        for r in conn.execute("SELECT DISTINCT rel_path FROM coverage_spans").fetchall():
            rp = str(r[0] or "").strip().lstrip("./")
            if rp:
                visited_files.add(rp)
    if "tasks" in tables:
        for r in conn.execute("SELECT locus FROM tasks WHERE status IN ('done', 'dry') AND locus != ''").fetchall():
            rp = str(r[0] or "").split(":", 1)[0].strip().lstrip("./")
            if rp:
                visited_files.add(rp)

    file_ranks: dict[str, float] = {}
    file_locs: dict[str, int] = {}
    symbols_by_file: dict[str, list[dict[str, Any]]] = {}
    out_edges: dict[str, dict[str, float]] = {}

    if "repomap_symbols" in tables:
        for r in conn.execute(
            "SELECT rel_path, name, kind, line_no, pagerank, signature FROM repomap_symbols ORDER BY rel_path ASC, line_no ASC"
        ).fetchall():
            rel = str(r["rel_path"] or "").strip().lstrip("./")
            if not rel:
                continue
            pr = float(r["pagerank"] or 0.0)
            if pr > file_ranks.get(rel, -1.0):
                file_ranks[rel] = pr
            lno = int(r["line_no"] or 1)
            if lno > file_locs.get(rel, 0):
                file_locs[rel] = lno
            symbols_by_file.setdefault(rel, []).append(
                {
                    "rel_path": rel,
                    "name": str(r["name"]),
                    "kind": str(r["kind"]),
                    "line_no": lno,
                    "signature": str(r["signature"] or ""),
                }
            )
    if "repomap_edges" in tables:
        for r in conn.execute("SELECT src_file, dst_file, weight FROM repomap_edges").fetchall():
            sf = str(r["src_file"] or "").strip().lstrip("./")
            df = str(r["dst_file"] or "").strip().lstrip("./")
            if sf and df and sf != df:
                out_edges.setdefault(sf, {})[df] = float(r["weight"] or 1.0)

    if target_mode == "source" and resolved_target is not None and resolved_target.exists():
        root = resolved_target.resolve()
        base_root = root.parent if root.is_file() else root
        for fpath in iter_source_files(root):
            try:
                raw = fpath.read_bytes()
            except OSError:
                continue
            if b"\x00" in raw[:4096]:
                continue
            rel = str(fpath.relative_to(base_root))
            file_locs[rel] = max(file_locs.get(rel, 0), max(1, len(raw.splitlines())))
            file_ranks.setdefault(rel, 0.0)

    unvisited_ranked = sorted(
        (f for f in file_locs if f not in visited_files),
        key=lambda u: (-file_ranks.get(u, 0.0), u),
    )
    if not unvisited_ranked:
        return []

    unvisited_set = set(unvisited_ranked)
    unvisited_edges: dict[str, dict[str, float]] = {
        u: {v: w for v, w in out_edges.get(u, {}).items() if v in unvisited_set}
        for u in unvisited_ranked
    }
    raw_slices = _partition_call_slices(
        unvisited_ranked,
        file_locs,
        unvisited_edges,
        symbols_by_file,
        slice_cap=slice_cap,
    )
    enriched: list[dict[str, Any]] = []
    for slc in raw_slices[: max(1, int(limit))]:
        seed_file = str(slc["seed_locus"]).split(":", 1)[0]
        enriched.append(
            {
                **slc,
                "file": seed_file,
                "pagerank": round(float(file_ranks.get(seed_file, 0.0)), 6),
            }
        )
    return enriched

