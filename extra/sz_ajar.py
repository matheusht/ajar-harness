#!/usr/bin/env python3
"""Ring-2 structural architecture and anti-golf gate for Ajar v3.6."""
from __future__ import annotations

import argparse
import ast
import io
import json
import sys
import tokenize
from pathlib import Path
from typing import Any

RING0_MODULES: tuple[str, ...] = ("cli.py", "llm.py", "agent.py", "verify.py")
RING1_MODULES: tuple[str, ...] = (
    "repomap.py",
    "whiteboard.py",
    "epistemic.py",
    "chain_weaver.py",
    "autobuild.py",
    "swarm.py",
    "bench.py",
)
LOGIC_MODULES: tuple[str, ...] = RING0_MODULES + RING1_MODULES
REQUIRED_DISABLE_FLAGS: tuple[str, ...] = (
    "--disable-repomap",
    "--disable-whiteboard",
    "--disable-epistemic",
    "--disable-chain-weaver",
    "--disable-autobuild",
    "--disable-swarm",
    "--disable-microfuzz",
)
RING0_MAX_SLOC: int = 1800
EPISTEMIC_MAX_SLOC: int = 180
MAX_TOKENS_PER_SLOC: float = 10.5

RING1_STEMS: frozenset[str] = frozenset(m.removesuffix(".py") for m in RING1_MODULES)
TRIVIA_TOKENS: frozenset[int] = frozenset({
    tokenize.COMMENT,
    tokenize.NL,
    tokenize.NEWLINE,
    tokenize.INDENT,
    tokenize.DEDENT,
    tokenize.ENCODING,
    tokenize.ENDMARKER,
})
FSTRING_START: int | None = getattr(tokenize, "FSTRING_START", None)
FSTRING_END: int | None = getattr(tokenize, "FSTRING_END", None)
SpanBounds = tuple[tuple[int, int], tuple[int, int]]


def _docstring_spans(tree: ast.AST) -> list[SpanBounds]:
    spans: list[SpanBounds] = []
    scopes = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, scopes) or not node.body:
            continue
        first = node.body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
            and first.value.lineno is not None
        ):
            start = (first.value.lineno, first.value.col_offset or 0)
            end = (first.value.end_lineno or first.value.lineno, first.value.end_col_offset or 0)
            spans.append((start, end))
    return spans


def analyze_python_file(path: Path) -> dict[str, Any]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    doc_spans = _docstring_spans(tree)
    code_lines: set[int] = set()
    semicolon_lines: list[int] = []
    tokens = 0
    fstring_depth = 0
    fstring_line = 1
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if fstring_depth == 0 and tok.type == tokenize.OP and tok.string == ";":
            semicolon_lines.append(tok.start[0])
        if FSTRING_START is not None and tok.type == FSTRING_START:
            if fstring_depth == 0:
                fstring_line = tok.start[0]
            fstring_depth += 1
            continue
        if fstring_depth > 0:
            if tok.type == FSTRING_END:
                fstring_depth -= 1
                if fstring_depth == 0:
                    tokens += 1
                    code_lines.add(fstring_line)
            continue
        if tok.type in TRIVIA_TOKENS:
            continue
        if tok.type == tokenize.STRING and any(ds <= tok.start and tok.end <= de for ds, de in doc_spans):
            continue
        tokens += 1
        code_lines.add(tok.start[0])
    sloc = len(code_lines)
    raw_density = (tokens / sloc) if sloc else 0.0
    return {
        "sloc": sloc,
        "tokens": tokens,
        "tokens_per_sloc": round(raw_density, 2),
        "raw_density": raw_density,
        "semicolon_lines": semicolon_lines,
        "tree": tree,
        "doc_spans": doc_spans,
    }


def _iter_ring0_import_nodes(module_name: str, tree: ast.Module) -> list[ast.Import | ast.ImportFrom]:
    found: list[ast.Import | ast.ImportFrom] = []

    def _walk(node: ast.AST) -> None:
        if (
            module_name == "cli.py"
            and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in {"main", "_main", "_amain", "async_main"}
        ):
            return
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            found.append(node)
        for child in ast.iter_child_nodes(node):
            _walk(child)

    _walk(tree)
    return found


def _extract_ring1_imports(module_name: str, tree: ast.Module) -> list[str]:
    bad: list[str] = []
    for node in _iter_ring0_import_nodes(module_name, tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if parts[0] in RING1_STEMS or (
                    parts[:1] == ["ajar"] and len(parts) > 1 and parts[1] in RING1_STEMS
                ):
                    bad.append(f"{module_name}:{node.lineno}->{alias.name}")
        else:
            mod = node.module or ""
            parts = mod.split(".") if mod else []
            if parts and (
                parts[0] in RING1_STEMS
                or (parts[0] == "ajar" and len(parts) > 1 and parts[1] in RING1_STEMS)
            ):
                bad.append(f"{module_name}:{node.lineno}->{mod}")
            elif (node.level >= 1 and not mod) or mod == "ajar":
                for alias in node.names:
                    if alias.name in RING1_STEMS:
                        bad.append(f"{module_name}:{node.lineno}->{alias.name}")
    return bad


def _find_worktree_invocations(
    module_name: str, tree: ast.Module, doc_spans: list[SpanBounds]
) -> list[str]:
    if module_name == "verify.py":
        return []
    hits: list[str] = []

    def _in_doc(node: ast.AST) -> bool:
        ln = int(getattr(node, "lineno", 1))
        end_ln = int(getattr(node, "end_lineno", ln) or ln)
        pos = (
            (ln, int(getattr(node, "col_offset", 0) or 0)),
            (end_ln, int(getattr(node, "end_col_offset", 0) or 0)),
        )
        return any(ds <= pos[0] and pos[1] <= de for ds, de in doc_spans)

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and not _in_doc(node):
            if "git worktree" in node.value.lower():
                hits.append(f"{module_name}:{node.lineno}")
        elif isinstance(node, (ast.List, ast.Tuple, ast.Call)):
            items = node.elts if isinstance(node, (ast.List, ast.Tuple)) else node.args
            for elt in items:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str) and not _in_doc(elt):
                    if elt.value.strip().lower() == "worktree":
                        hits.append(f"{module_name}:{elt.lineno}")
    return list(dict.fromkeys(hits))


def _check_disable_flags(cli_tree: ast.Module) -> tuple[list[str], list[str]]:
    literals = {
        n.value
        for n in ast.walk(cli_tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    }
    registered = [f for f in REQUIRED_DISABLE_FLAGS if any(f == s or f in s.split() for s in literals)]
    missing = [f for f in REQUIRED_DISABLE_FLAGS if f not in registered]
    return registered, missing


def audit_repo(repo_root: Path | None = None) -> dict[str, Any]:
    root = (repo_root or Path(__file__).resolve().parents[1]).resolve()
    src_dir = root / "src" / "ajar"
    violations: list[str] = []
    expected_all = set(LOGIC_MODULES) | {"__init__.py"}
    actual_py = {p.name for p in src_dir.glob("*.py")} if src_dir.is_dir() else set()
    missing_files = sorted(expected_all - actual_py)
    extra_files = sorted(actual_py - expected_all)
    if missing_files or extra_files:
        violations.append(f"Ring partition mismatch: missing={missing_files}, extra={extra_files}")

    file_stats: dict[str, dict[str, Any]] = {}
    upward_imports: list[str] = []
    worktree_violations: list[str] = []
    registered_flags: list[str] = []
    missing_flags: list[str] = list(REQUIRED_DISABLE_FLAGS)

    for name in ("__init__.py", *LOGIC_MODULES):
        fpath = src_dir / name
        if not fpath.is_file():
            continue
        info = analyze_python_file(fpath)
        ring = "ring0" if name in RING0_MODULES else ("ring1" if name in RING1_MODULES else "pkg")
        file_stats[name] = {
            "ring": ring,
            "sloc": info["sloc"],
            "tokens": info["tokens"],
            "tokens_per_sloc": info["tokens_per_sloc"],
            "semicolons": len(info["semicolon_lines"]),
        }
        if info["raw_density"] > MAX_TOKENS_PER_SLOC:
            violations.append(
                f"Anti-golf violation in {name}: {info['tokens_per_sloc']} > {MAX_TOKENS_PER_SLOC}"
            )
        if info["semicolon_lines"]:
            violations.append(f"Semicolon violation in {name} at lines {info['semicolon_lines']}")
        if name in RING0_MODULES:
            upward_imports.extend(_extract_ring1_imports(name, info["tree"]))
        worktree_violations.extend(_find_worktree_invocations(name, info["tree"], info["doc_spans"]))
        if name == "cli.py":
            registered_flags, missing_flags = _check_disable_flags(info["tree"])

    ring0_sloc = sum(file_stats[m]["sloc"] for m in RING0_MODULES if m in file_stats)
    ring1_sloc = sum(file_stats[m]["sloc"] for m in RING1_MODULES if m in file_stats)
    epistemic_sloc = file_stats.get("epistemic.py", {}).get("sloc", 0)
    logic_count = len([m for m in actual_py if m != "__init__.py"])

    if logic_count != len(LOGIC_MODULES):
        violations.append(f"Expected {len(LOGIC_MODULES)} logic modules, found {logic_count}")
    if ring0_sloc > RING0_MAX_SLOC:
        violations.append(f"Ring-0 SLOC {ring0_sloc} exceeds cap {RING0_MAX_SLOC}")
    if epistemic_sloc > EPISTEMIC_MAX_SLOC:
        violations.append(f"epistemic.py SLOC {epistemic_sloc} exceeds cap {EPISTEMIC_MAX_SLOC}")
    if upward_imports:
        violations.append(f"Upward Ring-0->Ring-1 imports: {upward_imports}")
    if worktree_violations:
        violations.append(f"Worktree invocations outside verify.py: {worktree_violations}")
    if missing_flags:
        violations.append(f"Missing CLI ablation flags: {missing_flags}")

    return {
        "ok": len(violations) == 0,
        "logic_module_count": logic_count,
        "ring0_sloc": ring0_sloc,
        "ring1_sloc": ring1_sloc,
        "total_sloc": ring0_sloc + ring1_sloc + file_stats.get("__init__.py", {}).get("sloc", 0),
        "epistemic_sloc": epistemic_sloc,
        "upward_imports": upward_imports,
        "worktree_violations": worktree_violations,
        "registered_disable_flags": registered_flags,
        "missing_disable_flags": missing_flags,
        "files": file_stats,
        "violations": violations,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify Ajar v3.6 Ring-2 structural and anti-golf gates.")
    parser.add_argument("repo_root", nargs="?", default=None, help="Repository root path")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Emit JSON report only")
    args = parser.parse_args(argv)
    report = audit_repo(Path(args.repo_root) if args.repo_root else None)
    if args.as_json:
        print(json.dumps(report, indent=2))
    else:
        print(f"{'Module':<18} {'Ring':<6} {'SLOC':>6} {'Tokens':>8} {'Tok/SLOC':>9} {'Semis':>6}")
        print("-" * 59)
        for mod, st in report["files"].items():
            print(
                f"{mod:<18} {st['ring']:<6} {st['sloc']:>6} "
                f"{st['tokens']:>8} {st['tokens_per_sloc']:>9.2f} {st['semicolons']:>6}"
            )
        print("-" * 59)
        summary = {
            k: report[k]
            for k in (
                "ok",
                "logic_module_count",
                "ring0_sloc",
                "ring1_sloc",
                "epistemic_sloc",
                "violations",
            )
        }
        print(json.dumps(summary, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
