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
        ("func", re.compile(r"^(?:static\s+|inline\s+|extern\s+)*[A-Za-z_][A-Za-z0-9_\s\*]+\s+\*?([A-Za-z_][A-Za-z0-9_]*)\s*\([^;]*$")),
        ("struct", re.compile(r"^\s*typedef\s+struct\s+([A-Za-z_][A-Za-z0-9_]*)")),
    ),
}
for _alias, _src in ((".tsx", ".ts"), (".js", ".ts"), (".jsx", ".ts"), (".mjs", ".ts"), (".h", ".c"), (".cc", ".c"), (".cpp", ".c"), (".hpp", ".c")):
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


def _extract_regex_symbols(rel_path: str, ext: str, text: str) -> list[dict[str, Any]]:
    patterns = SYMBOL_PATTERNS.get(ext, ())
    if not patterns:
        return []
    symbols: list[dict[str, Any]] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        for kind, pat in patterns:
            m = pat.search(line)
            if m:
                name = m.group(1)
                if name not in {"if", "for", "while", "switch", "return", "sizeof"}:
                    symbols.append(
                        {
                            "rel_path": rel_path,
                            "name": name,
                            "kind": kind,
                            "line_no": idx,
                            "signature": line.strip()[:120],
                        }
                    )
                break
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
            defs_by_name.setdefault(str(s["name"]), set()).add(rel)

    nodes = sorted(file_texts.keys())
    out_edges: dict[str, dict[str, float]] = {u: {} for u in nodes}
    edge_rows: list[tuple[str, str, str, float]] = []

    for src_rel, text in file_texts.items():
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
                edge_rows.append((src_rel, dst_rel, ident, round(idf_weight, 4)))

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

    conn.execute("DELETE FROM repomap_symbols")
    conn.execute("DELETE FROM repomap_edges")
    all_symbols: list[dict[str, Any]] = []
    for rel, syms in symbols_by_file.items():
        f_rank = round(float(file_ranks.get(rel, 0.0)), 6)
        for s in syms:
            sym_boost = 1.5 if s["name"] in focus_sym_set else 1.0
            s_rank = round(f_rank * sym_boost, 6)
            sym_id = f"{rel}:{s['line_no']}:{s['name']}"
            row = {**s, "symbol_id": sym_id, "pagerank": s_rank}
            all_symbols.append(row)
            conn.execute(
                """
                INSERT OR REPLACE INTO repomap_symbols(
                    symbol_id, rel_path, name, kind, line_no, pagerank, signature
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (sym_id, rel, s["name"], s["kind"], s["line_no"], s_rank, s["signature"]),
            )
    for src_f, dst_f, sym, w in edge_rows[:5000]:
        conn.execute(
            "INSERT INTO repomap_edges(src_file, dst_file, symbol, weight) VALUES (?, ?, ?, ?)",
            (src_f, dst_f, sym, w),
        )

    ranked_files = sorted(nodes, key=lambda u: (-file_ranks.get(u, 0.0), u))
    call_slices = _partition_call_slices(
        ranked_files, file_locs, out_edges, symbols_by_file, slice_cap=slice_cap
    )

    # Compact `< 1 KB` structural skeleton for 100K+ LoC repositories.
    top_subs = sorted(subsystems_loc.items(), key=lambda kv: (-kv[1], kv[0]))[:8]
    skel_lines = [
        f"# Repo Skeleton ({len(nodes)} files, {sum(file_locs.values())} lines, {len(call_slices)} slice(s) <= {int(slice_cap)} LoC)",
        "Subsystems: " + ", ".join(f"{k}({v}L)" for k, v in top_subs),
    ]
    for slc in call_slices[:8]:
        skel_lines.append(f"- {slc['slice_id']}: {slc['seed_locus']} ({slc['total_loc']}L, {len(slc['files'])} file(s))")
    skeleton_md = "\n".join(skel_lines)
    if len(skeleton_md.encode("utf-8")) > 960:
        skeleton_md = skeleton_md.encode("utf-8")[:960].decode("utf-8", errors="ignore")

    char_budget = max(256, int(budget_tokens) * 4)
    lines: list[str] = [
        f"# Repository Map ({len(nodes)} files, {len(all_symbols)} symbols, {len(call_slices)} slices <= {int(slice_cap)} LoC)"
    ]
    used_chars = len(lines[0]) + 1

    included_symbols: list[dict[str, Any]] = []
    for rel in ranked_files:
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
        "symbols_indexed": len(all_symbols),
        "edges_indexed": len(edge_rows),
        "slice_cap": int(slice_cap),
        "slice_count": len(call_slices),
        "call_slices": call_slices,
        "skeleton_md": skeleton_md,
        "token_estimate": max(1, len(rendered) // 4),
        "symbols": included_symbols,
        "rendered": rendered,
    }
