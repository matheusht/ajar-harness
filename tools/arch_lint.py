#!/usr/bin/env python3
"""Mechanical architecture and invariant linter for `ajar-harness`.

Every rule encodes a concrete historical bug class or architectural invariant
(the `/correct` rule-to-enforcer contract) and emits an actionable `fix_hint`
so agents can self-repair violations on the first pass.

Usage:
    python3 tools/arch_lint.py [--root <repo_root>] [--json]
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import json
import pathlib
import re
import sys

SQL_WRITE_RE = re.compile(
    r"\b(?:INSERT\s+(?:OR\s+\w+\s+)?INTO|REPLACE\s+INTO|UPDATE\s+(?:OR\s+\w+\s+)?[\w.\"]+\s+SET|DELETE\s+FROM)\b",
    re.IGNORECASE,
)

# Ratchet ceiling for inline SQL mutations in `ajar/cli.py` / `ajar/cli/*.py` (locked at 0).
MAX_CLI_RAW_SQL_WRITES = 0

FORBIDDEN_LLM_SDKS: frozenset[str] = frozenset(
    {
        "openai",
        "anthropic",
        "litellm",
        "langchain",
        "llama_index",
        "google.genai",
        "google.generativeai",
        "bedrock",
    }
)

DOMAIN_ALLOWED_AJAR_PREFIXES: tuple[str, ...] = ("ajar", "ajar.domain")
STORE_ALLOWED_AJAR_PREFIXES: tuple[str, ...] = ("ajar", "ajar.domain", "ajar.store")
SERVICES_FORBIDDEN_AJAR_PREFIXES: tuple[str, ...] = (
    "ajar.cli",
    "ajar.mcp",
    "ajar.runner",
    "ajar.hooks",
)

SAFE_TAR_FILTERS: frozenset[str] = frozenset({"tar", "data"})
PROTECTED_ENV_KEYS: frozenset[str] = frozenset({"HOME", "PATH"})

HARDCODED_PATH_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("devbox home path", re.compile(r"/home/antigravity\b")),
    ("temporary venv path", re.compile(r"/tmp/ajar-venv\b")),
    ("macOS user home path", re.compile(r"/Users/[A-Za-z0-9._-]+")),
)


@dataclasses.dataclass(frozen=True)
class LintViolation:
    rule: str
    path: str
    line: int
    message: str
    fix_hint: str

    def to_dict(self) -> dict[str, object]:
        return {
            "rule": self.rule,
            "path": self.path,
            "line": self.line,
            "message": self.message,
            "fix_hint": self.fix_hint,
        }


def _package_parts_for_rel(rel_posix: str) -> list[str]:
    p = pathlib.PurePosixPath(rel_posix)
    parts = list(p.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        return parts[:-1]
    return parts[:-1]


def _resolve_import_from(rel_posix: str, node: ast.ImportFrom) -> list[str]:
    if node.level > 0:
        pkg = _package_parts_for_rel(rel_posix)
        up = node.level - 1
        base_parts = pkg[:-up] if up > 0 else list(pkg)
        if node.module:
            base_parts = base_parts + node.module.split(".")
        base = ".".join(base_parts)
    else:
        base = node.module or ""

    resolved: list[str] = []
    if base:
        resolved.append(base)
        for alias in node.names:
            if alias.name != "*":
                resolved.append(f"{base}.{alias.name}")
    else:
        for alias in node.names:
            if alias.name != "*":
                resolved.append(alias.name)
    return resolved


def _iter_imported_modules(tree: ast.AST, rel_posix: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            for mod in _resolve_import_from(rel_posix, node):
                found.append((node.lineno, mod))
    return found


def _extract_string_fragments(expr: ast.AST) -> str:
    if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        return expr.value
    if isinstance(expr, ast.JoinedStr):
        parts: list[str] = []
        for val in expr.values:
            if isinstance(val, ast.Constant) and isinstance(val.value, str):
                parts.append(val.value)
            else:
                parts.append(" _expr_ ")
        return "".join(parts)
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, (ast.Add, ast.Mod)):
        left = _extract_string_fragments(expr.left)
        right = _extract_string_fragments(expr.right)
        return f"{left}{right}" if isinstance(expr.op, ast.Add) else left
    if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute) and expr.func.attr == "format":
        return _extract_string_fragments(expr.func.value)
    return ""


_HARDCODED_PATH_PREFILTER = re.compile(
    "|".join(f"(?:{pat.pattern})" for _, pat in HARDCODED_PATH_PATTERNS)
)


class _ParsedPy:
    """Lazily parses `.py` source so substring-filtered files never pay `ast.parse` cost."""

    def __init__(self, rel: str, src: str) -> None:
        self.rel = rel
        self.src = src
        self._tree: ast.AST | None = None

    @property
    def tree(self) -> ast.AST:
        if self._tree is None:
            self._tree = ast.parse(self.src, filename=self.rel)
        return self._tree


class _RepoAstCache:
    """Single-pass source + lazy AST cache for `run_all_checks`."""

    def __init__(self, root: pathlib.Path) -> None:
        self.root = root
        self._by_path: dict[pathlib.Path, _ParsedPy] = {}
        self._dir_files: dict[str, list[_ParsedPy]] = {}

    def get(self, path: pathlib.Path) -> _ParsedPy | None:
        if path in self._by_path:
            return self._by_path[path]
        if not path.is_file():
            return None
        rel = path.relative_to(self.root).as_posix()
        src = path.read_text(encoding="utf-8")
        parsed = _ParsedPy(rel=rel, src=src)
        self._by_path[path] = parsed
        return parsed

    def py_files_under(self, subdir: str) -> list[_ParsedPy]:
        if subdir in self._dir_files:
            return self._dir_files[subdir]
        base = self.root / subdir
        if not base.is_dir():
            self._dir_files[subdir] = []
            return []
        items: list[_ParsedPy] = []
        for py_path in sorted(base.rglob("*.py")):
            parsed = self.get(py_path)
            if parsed is not None:
                items.append(parsed)
        self._dir_files[subdir] = items
        return items


def _count_raw_sql_writes(
    path: pathlib.Path,
    *,
    tree: ast.AST | None = None,
) -> list[tuple[int, str]]:
    if tree is None:
        if not path.is_file():
            return []
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("execute", "executemany", "executescript")
            and node.args
        ):
            sql_text = _extract_string_fragments(node.args[0])
            if sql_text and SQL_WRITE_RE.search(sql_text):
                snippet = sql_text.strip().splitlines()[0][:80]
                hits.append((node.lineno, snippet))
    return hits


def check_no_raw_sql_in_mcp(
    root: pathlib.Path,
    *,
    _cache: _RepoAstCache | None = None,
) -> list[LintViolation]:
    mcp_path = root / "ajar" / "mcp.py"
    parsed = _cache.get(mcp_path) if _cache is not None else None
    if _cache is not None and parsed is None:
        return []
    violations: list[LintViolation] = []
    for lineno, snippet in _count_raw_sql_writes(mcp_path, tree=parsed.tree if parsed else None):
        violations.append(
            LintViolation(
                rule="NO_RAW_SQL_IN_MCP",
                path="ajar/mcp.py",
                line=lineno,
                message=f"Raw SQL mutation found in MCP transport adapter: {snippet!r}",
                fix_hint="Move this state mutation into `ajar/services/workflow.py` and call the service from `ajar/mcp.py`.",
            )
        )
    return violations


def check_cli_raw_sql_ratchet(
    root: pathlib.Path,
    *,
    max_writes: int = MAX_CLI_RAW_SQL_WRITES,
    _cache: _RepoAstCache | None = None,
) -> list[LintViolation]:
    targets: list[pathlib.Path] = []
    cli_file = root / "ajar" / "cli.py"
    if cli_file.is_file():
        targets.append(cli_file)
    cli_pkg = root / "ajar" / "cli"
    if cli_pkg.is_dir():
        targets.extend(sorted(cli_pkg.rglob("*.py")))
    if not targets:
        return []

    all_hits: list[tuple[str, int, str]] = []
    for tpath in targets:
        parsed = _cache.get(tpath) if _cache is not None else None
        rel = parsed.rel if parsed is not None else tpath.relative_to(root).as_posix()
        for lineno, snippet in _count_raw_sql_writes(tpath, tree=parsed.tree if parsed else None):
            all_hits.append((rel, lineno, snippet))

    if len(all_hits) <= max_writes:
        return []
    first_rel, first_line, _ = all_hits[0]
    return [
        LintViolation(
            rule="CLI_RAW_SQL_RATCHET",
            path=first_rel,
            line=first_line,
            message=f"CLI layer has {len(all_hits)} raw SQL write(s), exceeding the ratchet ceiling of {max_writes}.",
            fix_hint="Do not add inline INSERT/UPDATE/DELETE statements to `ajar/cli`; delegate via `ajar/services/`.",
        )
    ]


def _module_is_under(mod: str, prefix: str) -> bool:
    return mod == prefix or mod.startswith(prefix + ".")


def check_layer_dag_boundaries(
    root: pathlib.Path,
    *,
    _cache: _RepoAstCache | None = None,
) -> list[LintViolation]:
    ajar_dir = root / "ajar"
    if not ajar_dir.is_dir():
        return []
    cache = _cache if _cache is not None else _RepoAstCache(root)
    violations: list[LintViolation] = []
    for parsed in cache.py_files_under("ajar"):
        rel = parsed.rel
        imports = _iter_imported_modules(parsed.tree, rel)
        seen_line_rule: set[tuple[int, str]] = set()

        def _record(
            lineno: int,
            rule: str,
            msg: str,
            hint: str,
            *,
            _rel: str = rel,
            _seen: set[tuple[int, str]] = seen_line_rule,
        ) -> None:
            key = (lineno, rule)
            if key in _seen:
                return
            _seen.add(key)
            violations.append(LintViolation(rule=rule, path=_rel, line=lineno, message=msg, fix_hint=hint))

        for lineno, mod in imports:
            # 1. Global Zero-LLM & Frozen-Legacy boundaries for all of `ajar/`
            if _module_is_under(mod, "tools.legacy") or mod == "legacy":
                _record(
                    lineno,
                    "LAYER_DAG_BOUNDARY",
                    f"Core package module `{rel}` imports archived legacy module `{mod}`.",
                    "Never import `tools/legacy/` from `ajar/`. Implement clean pure-stdlib code in `ajar/`.",
                )
            for sdk in FORBIDDEN_LLM_SDKS:
                if _module_is_under(mod, sdk):
                    _record(
                        lineno,
                        "ZERO_LLM_ENGINE",
                        f"Zero-LLM invariant violated: `{rel}` imports LLM SDK `{mod}`.",
                        "Remove all LLM SDK imports from `ajar/`. Ajar's core engine must stay pure stdlib.",
                    )

            # 2. Layer-specific DAG rules
            if rel.startswith("ajar/domain/") and mod.startswith("ajar."):
                if not any(_module_is_under(mod, p) for p in DOMAIN_ALLOWED_AJAR_PREFIXES if p != "ajar"):
                    top_sub = mod.split(".", 2)[1]
                    if (ajar_dir / f"{top_sub}.py").exists() or (ajar_dir / top_sub).is_dir():
                        _record(
                            lineno,
                            "LAYER_DAG_BOUNDARY",
                            f"`ajar/domain/` must remain pure and cannot import `{mod}`.",
                            "Move pure types/enums/transitions into `ajar/domain/` or move SQL/IO logic to `ajar/store/` or `ajar/services/`.",
                        )

            elif rel.startswith("ajar/store/") and mod.startswith("ajar."):
                if not any(_module_is_under(mod, p) for p in STORE_ALLOWED_AJAR_PREFIXES if p != "ajar"):
                    top_sub = mod.split(".", 2)[1]
                    if (ajar_dir / f"{top_sub}.py").exists() or (ajar_dir / top_sub).is_dir():
                        _record(
                            lineno,
                            "LAYER_DAG_BOUNDARY",
                            f"`ajar/store/` cannot depend upward on `{mod}`.",
                            "`ajar/store/` may only import stdlib, top-level `ajar` constants, `ajar.domain`, and `ajar.store`.",
                        )

            elif rel.startswith("ajar/services/") and any(
                _module_is_under(mod, p) for p in SERVICES_FORBIDDEN_AJAR_PREFIXES
            ):
                _record(
                    lineno,
                    "LAYER_DAG_BOUNDARY",
                    f"`ajar/services/` cannot import transport/driver module `{mod}`.",
                    "Transport layers (`cli.py`, `mcp.py`, `runner.py`) depend on `ajar/services/`, never the reverse.",
                )
    return violations


def check_no_hardcoded_devbox_paths(
    root: pathlib.Path,
    *,
    _cache: _RepoAstCache | None = None,
) -> list[LintViolation]:
    violations: list[LintViolation] = []
    scan_roots = ("ajar", "tests", "skills", "docs")
    scan_exts = {".py", ".md", ".sh", ".yml", ".yaml", ".json", ".toml"}
    for subdir in scan_roots:
        base = root / subdir
        if not base.is_dir():
            continue
        for fpath in sorted(base.rglob("*")):
            if not fpath.is_file() or fpath.suffix.lower() not in scan_exts:
                continue
            cached = _cache.get(fpath) if (_cache is not None and fpath.suffix.lower() == ".py") else None
            text = cached.src if cached is not None else fpath.read_text(encoding="utf-8", errors="ignore")
            if _HARDCODED_PATH_PREFILTER.search(text) is None:
                continue
            rel = cached.rel if cached is not None else fpath.relative_to(root).as_posix()
            for idx, line in enumerate(text.splitlines(), start=1):
                if "arch-lint: ignore-fixture" in line:
                    continue
                for label, pat in HARDCODED_PATH_PATTERNS:
                    if pat.search(line):
                        violations.append(
                            LintViolation(
                                rule="NO_HARDCODED_DEVBOX_PATH",
                                path=rel,
                                line=idx,
                                message=f"Hardcoded {label} found in `{rel}:{idx}`.",
                                fix_hint="Use `pathlib.Path.home()`, `tempfile`, or `$AJAR_HOME`/`base_env` instead of developer-specific absolute paths.",
                            )
                        )
    return violations


def _is_os_environ(node: ast.AST) -> bool:
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return node.value.id == "os" and node.attr == "environ"
    return isinstance(node, ast.Name) and node.id == "environ"


def _protected_env_key(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in PROTECTED_ENV_KEYS:
        return node.value
    return None


def check_no_ambient_env_mutation_in_tests(
    root: pathlib.Path,
    *,
    _cache: _RepoAstCache | None = None,
) -> list[LintViolation]:
    tests_dir = root / "tests"
    if not tests_dir.is_dir():
        return []
    cache = _cache if _cache is not None else _RepoAstCache(root)
    violations: list[LintViolation] = []
    for parsed in cache.py_files_under("tests"):
        rel = parsed.rel
        if "environ" not in parsed.src and "putenv" not in parsed.src and "unsetenv" not in parsed.src:
            continue
        lines = parsed.src.splitlines()
        tree = parsed.tree

        def _ignored(lineno: int, *, _lines: list[str] = lines) -> bool:
            return 0 < lineno <= len(_lines) and "arch-lint: ignore-fixture" in _lines[lineno - 1]

        def _add(lineno: int, msg: str, *, _rel: str = rel) -> None:
            if _ignored(lineno):
                return
            violations.append(
                LintViolation(
                    rule="NO_AMBIENT_ENV_MUTATION",
                    path=_rel,
                    line=lineno,
                    message=msg,
                    fix_hint="Pass an explicit `base_env=` dict or use `unittest.mock.patch.dict(os.environ, ...)` so parallel tests never leak state.",
                )
            )

        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Subscript) and _is_os_environ(target.value):
                        key = _protected_env_key(target.slice)
                        if key is not None:
                            _add(node.lineno, f"Test mutates ambient `os.environ[{key!r}]` directly.")
            elif isinstance(node, ast.Delete):
                for target in node.targets:
                    if isinstance(target, ast.Subscript) and _is_os_environ(target.value):
                        key = _protected_env_key(target.slice)
                        if key is not None:
                            _add(node.lineno, f"Test deletes ambient `os.environ[{key!r}]` directly.")
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if _is_os_environ(node.func.value):
                    if node.func.attr in ("pop", "setdefault") and node.args:
                        key = _protected_env_key(node.args[0])
                        if key is not None:
                            _add(node.lineno, f"Test mutates ambient `os.environ.{node.func.attr}({key!r}, ...)` directly.")
                    elif node.func.attr == "update":
                        for arg in node.args:
                            if isinstance(arg, ast.Dict):
                                for k in arg.keys:
                                    key = _protected_env_key(k) if k is not None else None
                                    if key is not None:
                                        _add(node.lineno, f"Test mutates ambient `os.environ.update({{{key!r}: ...}})` directly.")
                        for kw in node.keywords:
                            if kw.arg in PROTECTED_ENV_KEYS:
                                _add(node.lineno, f"Test mutates ambient `os.environ.update({kw.arg}=...)` directly.")
                elif (
                    isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "os"
                    and node.func.attr in ("putenv", "unsetenv")
                    and node.args
                ):
                    key = _protected_env_key(node.args[0])
                    if key is not None:
                        _add(node.lineno, f"Test mutates ambient env via `os.{node.func.attr}({key!r})` directly.")
    return violations


def check_no_unfiltered_tar_extract(
    root: pathlib.Path,
    *,
    _cache: _RepoAstCache | None = None,
) -> list[LintViolation]:
    ajar_dir = root / "ajar"
    if not ajar_dir.is_dir():
        return []
    cache = _cache if _cache is not None else _RepoAstCache(root)
    violations: list[LintViolation] = []
    for parsed in cache.py_files_under("ajar"):
        if "tarfile" not in parsed.src:
            continue
        rel = parsed.rel
        tree = parsed.tree
        imported = {mod for _, mod in _iter_imported_modules(tree, rel)}
        if not any(_module_is_under(mod, "tarfile") for mod in imported):
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("extract", "extractall")
            ):
                filter_kw = next((kw for kw in node.keywords if kw.arg == "filter"), None)
                if filter_kw is None:
                    violations.append(
                        LintViolation(
                            rule="NO_UNFILTERED_TAR_EXTRACT",
                            path=rel,
                            line=node.lineno,
                            message=f"`{node.func.attr}()` called without explicit safe `filter=` argument.",
                            fix_hint="Pass `filter='tar'` or `filter='data'` and validate member paths against archive root to prevent tar-slip.",
                        )
                    )
                elif not (
                    isinstance(filter_kw.value, ast.Constant)
                    and isinstance(filter_kw.value.value, str)
                    and filter_kw.value.value in SAFE_TAR_FILTERS
                ):
                    violations.append(
                        LintViolation(
                            rule="NO_UNFILTERED_TAR_EXTRACT",
                            path=rel,
                            line=node.lineno,
                            message=f"`{node.func.attr}()` passes unsafe or non-literal `filter=` value.",
                            fix_hint="Use literal `filter='tar'` or `filter='data'` (never `None` or `'fully_trusted'`).",
                        )
                    )
    return violations


_MIGRATION_FUNC_RE = re.compile(r"^_ensure_v\d+_schema$")


def check_no_commit_noop(
    root: pathlib.Path,
    *,
    _cache: _RepoAstCache | None = None,
) -> list[LintViolation]:
    """Reject `.commit()` calls inside `ajar/` (connections use autocommit + `immediate_tx`)."""
    ajar_dir = root / "ajar"
    if not ajar_dir.is_dir():
        return []
    cache = _cache if _cache is not None else _RepoAstCache(root)
    violations: list[LintViolation] = []
    for parsed in cache.py_files_under("ajar"):
        if ".commit(" not in parsed.src:
            continue
        for node in ast.walk(parsed.tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "commit"
            ):
                violations.append(
                    LintViolation(
                        rule="NO_COMMIT_NOOP",
                        path=parsed.rel,
                        line=node.lineno,
                        message=f"`.commit()` call in `{parsed.rel}:{node.lineno}` is a no-op under `isolation_level=None`.",
                        fix_hint="Wrap multi-statement SQLite mutations in `with immediate_tx(conn):` from `ajar.store` and remove `.commit()`.",
                    )
                )
    return violations


def _function_sql_writes_and_tx(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[list[int], bool]:
    writes: list[int] = []
    has_tx = False

    def _visit(node: ast.AST) -> None:
        nonlocal has_tx
        if node is not fn and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ("execute", "executemany", "executescript") and node.args:
                sql_text = _extract_string_fragments(node.args[0])
                if sql_text and SQL_WRITE_RE.search(sql_text):
                    writes.append(node.lineno)
        elif isinstance(node, ast.With):
            for item in node.items:
                if isinstance(item.context_expr, ast.Call):
                    f = item.context_expr.func
                    name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
                    if name == "immediate_tx":
                        has_tx = True
        for child in ast.iter_child_nodes(node):
            _visit(child)

    _visit(fn)
    return (writes, has_tx)


def check_multi_write_requires_immediate_tx(
    root: pathlib.Path,
    *,
    _cache: _RepoAstCache | None = None,
) -> list[LintViolation]:
    """Require `with immediate_tx(conn):` on any function in `ajar/` issuing >= 2 SQL writes."""
    ajar_dir = root / "ajar"
    if not ajar_dir.is_dir():
        return []
    cache = _cache if _cache is not None else _RepoAstCache(root)
    violations: list[LintViolation] = []
    for parsed in cache.py_files_under("ajar"):
        if "execute" not in parsed.src:
            continue
        for node in ast.walk(parsed.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if _MIGRATION_FUNC_RE.match(node.name):
                    continue
                writes, has_tx = _function_sql_writes_and_tx(node)
                if len(writes) >= 2 and not has_tx:
                    violations.append(
                        LintViolation(
                            rule="MULTI_WRITE_REQUIRES_IMMEDIATE_TX",
                            path=parsed.rel,
                            line=node.lineno,
                            message=(
                                f"`{node.name}` executes {len(writes)} SQL write statements without `immediate_tx(conn)`."
                            ),
                            fix_hint="Wrap the multi-statement write block in `with immediate_tx(conn):` (never across subprocess calls).",
                        )
                    )
    return violations


def run_all_checks(root: pathlib.Path) -> list[LintViolation]:
    cache = _RepoAstCache(root)
    violations: list[LintViolation] = []
    violations.extend(check_no_raw_sql_in_mcp(root, _cache=cache))
    violations.extend(check_cli_raw_sql_ratchet(root, _cache=cache))
    violations.extend(check_layer_dag_boundaries(root, _cache=cache))
    violations.extend(check_no_hardcoded_devbox_paths(root, _cache=cache))
    violations.extend(check_no_ambient_env_mutation_in_tests(root, _cache=cache))
    violations.extend(check_no_unfiltered_tar_extract(root, _cache=cache))
    violations.extend(check_no_commit_noop(root, _cache=cache))
    violations.extend(check_multi_write_requires_immediate_tx(root, _cache=cache))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Ajar mechanical architecture guardrails.")
    parser.add_argument("--root", default=str(pathlib.Path(__file__).resolve().parents[1]))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    root = pathlib.Path(args.root).resolve()
    violations = run_all_checks(root)
    if args.json:
        print(
            json.dumps(
                {
                    "passed": len(violations) == 0,
                    "violation_count": len(violations),
                    "violations": [v.to_dict() for v in violations],
                },
                indent=2,
            )
        )
    else:
        if not violations:
            print("arch_lint: OK (0 violations)")
        else:
            for v in violations:
                print(f"[{v.rule}] {v.path}:{v.line}: {v.message}")
                print(f"  fix: {v.fix_hint}")
            print(f"arch_lint: FAILED ({len(violations)} violation(s))")
    return 0 if not violations else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
