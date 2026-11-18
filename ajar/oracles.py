"""SQLite FTS5 indexing and search over `intent`, `reachability`, and `precedent`.

Replaces prompt-heavy prose wrappers with deterministic BM25 full-text lookup:
- `intent`: READMEs, architecture docs, and inline security/invariant comments
  (tagged `provenance='untrusted_target'` so prompt-injected or misleading docs
  never masquerade as verified code guards)
- `reachability`: public routes, handlers, RPC/CLI entrypoints, top-level public functions,
  FFI/intrinsics, and outbound response deserialization sinks (`provenance='code_symbol'`)
- `precedent`: curated CVE, defect-chain, fix-diff, and false-positive corpora
  (`provenance='trusted_builtin'`)
"""

from __future__ import annotations

import os
import pathlib
import re
import sqlite3
from typing import Any

from ajar.redact import scrub_text
from ajar.repomap import SKIP_DIRS, iter_source_files

INVARIANT_COMMENT_RE = re.compile(
    r"\b(invariant|security|must|never|auth|authorize|permission|owner|nonce|signature|overflow|bounds|verify|trust|lock|atomic)\b",
    re.IGNORECASE,
)

REACHABILITY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("python_route", re.compile(r"^\s*@(?:app|router|bp|api)\.(?:route|get|post|put|delete|patch)\b")),
    ("python_cli", re.compile(r"\badd_parser\s*\(|^\s*def\s+do_[A-Za-z0-9_]+\s*\(")),
    ("python_public_def", re.compile(r"^def\s+(?!_|test_)([A-Za-z][A-Za-z0-9_]*)\s*\(")),
    ("http_handler", re.compile(r"\b(?:HandleFunc|Handle|Get|Post|Put|Delete)\s*\(\s*[\"']/")),
    ("solidity_entry", re.compile(r"^\s*function\s+[A-Za-z_][A-Za-z0-9_]*\s*\([^)]*\)\s*(?:[^{]*\b(?:external|public)\b)")),
    ("rust_pub_entry", re.compile(r"^\s*pub\s+(?:async\s+)?(?:extern\s+[\"']C[\"']\s+)?fn\s+[A-Za-z_][A-Za-z0-9_]*")),
    ("ts_export_handler", re.compile(r"^\s*export\s+(?:default\s+)?(?:async\s+)?function\s+(?:GET|POST|PUT|DELETE|PATCH|fetch|[A-Za-z_][A-Za-z0-9_]*)")),
    ("c_entry", re.compile(r"^\s*(?:int\s+main\s*\(|ssize_t\s+|int\s+parse_[A-Za-z0-9_]*\s*\()")),
    ("ffi_intrinsic", re.compile(r"(?:@IntrinsicCandidate|\bextern\s+\"C\"|\bctypes\.CDLL\b|\bcgo\b)")),
    ("peer_response_sink", re.compile(r"\b(?:json\.loads|pickle\.loads|yaml\.load|xml\.etree|json\.Unmarshal)\s*\(")),
)


def _ensure_fts_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS oracle_docs (
            doc_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL CHECK(kind IN ('intent', 'reachability', 'precedent')),
            title TEXT NOT NULL,
            locus TEXT NOT NULL,
            body TEXT NOT NULL,
            provenance TEXT NOT NULL DEFAULT 'untrusted_target'
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS oracle_fts USING fts5(
            doc_id UNINDEXED,
            kind UNINDEXED,
            title,
            locus,
            body
        );
        """
    )
    cols = {r[1] for r in conn.execute("PRAGMA table_info(oracle_docs)").fetchall()}
    if "provenance" not in cols:
        conn.execute("ALTER TABLE oracle_docs ADD COLUMN provenance TEXT NOT NULL DEFAULT 'untrusted_target'")


def _default_references_dir() -> pathlib.Path | None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    primary = repo_root / "skills" / "references"
    if primary.is_dir():
        return primary
    fallback = repo_root / "skills" / "oracles" / "references"
    if fallback.is_dir():
        return fallback
    return None


def _chunk_markdown_sections(md_path: pathlib.Path, rel_label: str) -> list[tuple[str, str, str]]:
    """Return `(title, locus, body)` chunks split on markdown headings or table blocks."""
    try:
        text = md_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    lines = text.splitlines()
    chunks: list[tuple[str, str, str]] = []
    cur_title = md_path.stem
    cur_start = 1
    cur_buf: list[str] = []

    def flush(end_line: int) -> None:
        body = "\n".join(cur_buf).strip()
        if len(body) >= 24:
            for offset in range(0, len(body), 1800):
                piece = body[offset : offset + 1800]
                chunks.append((cur_title[:140], f"{rel_label}:{cur_start}-{end_line}", piece))

    for idx, line in enumerate(lines, start=1):
        if line.startswith("#"):
            if cur_buf:
                flush(idx - 1)
                cur_buf = []
            cur_title = line.lstrip("#").strip() or md_path.stem
            cur_start = idx
        cur_buf.append(line)
    if cur_buf:
        flush(len(lines))
    return chunks


def index_target_oracles(
    conn: sqlite3.Connection,
    target_dir: pathlib.Path,
    *,
    references_dir: pathlib.Path | None = None,
) -> dict[str, int]:
    """Index target `intent` and `reachability`, plus reference `precedent`, into SQLite FTS5."""
    _ensure_fts_tables(conn)
    conn.execute("DELETE FROM oracle_docs")
    conn.execute("DELETE FROM oracle_fts")

    counts = {"intent": 0, "reachability": 0, "precedent": 0}
    root = target_dir.resolve()
    base_root = root.parent if root.is_file() else root

    def insert_doc(doc_id: str, kind: str, title: str, locus: str, body: str, provenance: str) -> None:
        c_title = scrub_text(title)
        c_body = scrub_text(body)
        conn.execute(
            "INSERT OR REPLACE INTO oracle_docs(doc_id, kind, title, locus, body, provenance) VALUES (?, ?, ?, ?, ?, ?)",
            (doc_id, kind, c_title, locus, c_body, provenance),
        )
        conn.execute(
            "INSERT INTO oracle_fts(doc_id, kind, title, locus, body) VALUES (?, ?, ?, ?, ?)",
            (doc_id, kind, c_title, locus, c_body),
        )
        counts[kind] += 1

    # 1. Index target markdown docs into `intent` (`untrusted_target`).
    if root.is_dir():
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
                fpath = pathlib.Path(dirpath) / fname
                if fpath.is_symlink():
                    continue
                if fpath.suffix.lower() in (".md", ".txt", ".rst"):
                    rel = str(fpath.relative_to(base_root))
                    for c_idx, (title, locus, body) in enumerate(_chunk_markdown_sections(fpath, rel)):
                        insert_doc(f"intent:doc:{rel}:{c_idx}", "intent", title, locus, body, "untrusted_target")

    # 2. Index inline invariant comments (`intent`) and entrypoints (`reachability`) across source files.
    for fpath in iter_source_files(root):
        try:
            text = fpath.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = str(fpath.relative_to(base_root))
        lines = text.splitlines()
        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            if (stripped.startswith(("#", "//", "/*", "*")) or '"""' in stripped) and INVARIANT_COMMENT_RE.search(stripped):
                window = "\n".join(lines[max(0, idx - 1) : min(len(lines), idx + 4)])
                insert_doc(
                    f"intent:code:{rel}:{idx}",
                    "intent",
                    f"Code invariant note in {rel}",
                    f"{rel}:{idx}",
                    window[:900],
                    "untrusted_target",
                )
            for label, pat in REACHABILITY_PATTERNS:
                if pat.search(line):
                    snippet = "\n".join(lines[max(0, idx - 1) : min(len(lines), idx + 6)])
                    insert_doc(
                        f"reach:{label}:{rel}:{idx}",
                        "reachability",
                        f"{label} @ {rel}:{idx}",
                        f"{rel}:{idx}",
                        snippet[:900],
                        "code_symbol",
                    )
                    break

    # 3. Index `precedent` reference corpora (`trusted_builtin`).
    ref_root = references_dir if references_dir is not None else _default_references_dir()
    if ref_root is not None and ref_root.is_dir():
        for md_file in sorted(ref_root.glob("*.md")):
            rel = md_file.name
            for c_idx, (title, locus, body) in enumerate(_chunk_markdown_sections(md_file, rel)):
                insert_doc(f"precedent:{rel}:{c_idx}", "precedent", title, locus, body, "trusted_builtin")

    return counts


def _build_safe_fts_query(raw_query: str) -> str:
    """Convert arbitrary user/CVE queries (e.g. `CVE-2021-31207`) into syntax-safe FTS5 expressions."""
    phrases = re.findall(r"[A-Za-z]+-\d{2,4}-[A-Za-z0-9-]+", raw_query)
    tokens = re.findall(r"[A-Za-z0-9_]{2,}", raw_query)
    parts: list[str] = []
    seen: set[str] = set()
    for ph in phrases:
        clean_ph = ph.replace('"', "")
        expr = f'"{clean_ph}"'
        if expr.lower() not in seen:
            seen.add(expr.lower())
            parts.append(expr)
    for tok in tokens[:12]:
        expr = f'"{tok}"'
        if expr.lower() not in seen:
            seen.add(expr.lower())
            parts.append(expr)
    return " OR ".join(parts)


def query_oracle(
    conn: sqlite3.Connection,
    kind: str,
    query: str,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Query `oracle_fts` with BM25 ranking (`kind` in `intent`, `reachability`, `precedent`, `all`)."""
    _ensure_fts_tables(conn)
    fts_expr = _build_safe_fts_query(query)
    if not fts_expr:
        return []

    if kind and kind != "all":
        rows = conn.execute(
            """
            SELECT f.doc_id, f.kind, f.title, f.locus,
                   COALESCE(d.provenance, 'untrusted_target') AS provenance,
                   snippet(oracle_fts, 4, '[', ']', ' ... ', 32) AS snippet,
                   bm25(oracle_fts) AS rank_score
            FROM oracle_fts f
            LEFT JOIN oracle_docs d ON f.doc_id = d.doc_id
            WHERE oracle_fts MATCH ? AND f.kind = ?
            ORDER BY rank_score ASC
            LIMIT ?
            """,
            (fts_expr, kind, int(limit)),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT f.doc_id, f.kind, f.title, f.locus,
                   COALESCE(d.provenance, 'untrusted_target') AS provenance,
                   snippet(oracle_fts, 4, '[', ']', ' ... ', 32) AS snippet,
                   bm25(oracle_fts) AS rank_score
            FROM oracle_fts f
            LEFT JOIN oracle_docs d ON f.doc_id = d.doc_id
            WHERE oracle_fts MATCH ?
            ORDER BY rank_score ASC
            LIMIT ?
            """,
            (fts_expr, int(limit)),
        ).fetchall()

    results: list[dict[str, Any]] = []
    for r in rows:
        prov = str(r["provenance"] or "untrusted_target")
        raw_snip = str(r["snippet"] or "")
        snip = f"[UNTRUSTED_TARGET_DOC: verify in code] {raw_snip}" if prov == "untrusted_target" else raw_snip
        results.append(
            {
                "doc_id": r["doc_id"],
                "kind": r["kind"],
                "title": r["title"],
                "locus": r["locus"],
                "provenance": prov,
                "snippet": snip,
                "score": round(float(-r["rank_score"]), 4),
            }
        )
    return results
