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

SQL_WRITE_RE = re.compile(r"\b(INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM)\b", re.IGNORECASE)

# Ratchet ceiling for remaining inline SQL mutations in `ajar/cli.py`.
# Lower this whenever another CLI command moves into `ajar/services/`.
MAX_CLI_RAW_SQL_WRITES = 12

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


def _iter_imported_modules(tree: ast.AST) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod:
                found.append((node.lineno, mod))
                for alias in node.names:
                    found.append((node.lineno, f"{mod}.{alias.name}"))
    return found


def _count_raw_sql_writes(path: pathlib.Path) -> list[tuple[int, str]]:
    if not path.is_file():
        return []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("execute", "executemany")
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
            and SQL_WRITE_RE.search(node.args[0].value)
        ):
            snippet = node.args[0].value.strip().splitlines()[0][:80]
            hits.append((node.lineno, snippet))
    return hits


def check_no_raw_sql_in_mcp(root: pathlib.Path) -> list[LintViolation]:
    mcp_path = root / "ajar" / "mcp.py"
    violations: list[LintViolation] = []
    for lineno, snippet in _count_raw_sql_writes(mcp_path):
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
) -> list[LintViolation]:
    cli_path = root / "ajar" / "cli.py"
    hits = _count_raw_sql_writes(cli_path)
    if len(hits) <= max_writes:
        return []
    first_line = hits[0][0] if hits else 1
    return [
        LintViolation(
            rule="CLI_RAW_SQL_RATCHET",
            path="ajar/cli.py",
            line=first_line,
            message=f"`ajar/cli.py` has {len(hits)} raw SQL writes, exceeding the ratchet ceiling of {max_writes}.",
            fix_hint="Do not add inline INSERT/UPDATE/DELETE statements to `ajar/cli.py`; delegate via `ajar/services/`.",
        )
    ]


def _module_is_under(mod: str, prefix: str) -> bool:
    return mod == prefix or mod.startswith(prefix + ".")


def check_layer_dag_boundaries(root: pathlib.Path) -> list[LintViolation]:
    ajar_dir = root / "ajar"
    if not ajar_dir.is_dir():
        return []
    violations: list[LintViolation] = []
    for py_path in sorted(ajar_dir.rglob("*.py")):
        rel = py_path.relative_to(root).as_posix()
        tree = ast.parse(py_path.read_text(encoding="utf-8"), filename=rel)
        imports = _iter_imported_modules(tree)
        for lineno, mod in imports:
            # 1. Global Zero-LLM & Frozen-Legacy boundaries for all of `ajar/`
            if _module_is_under(mod, "tools.legacy") or mod == "legacy":
                violations.append(
                    LintViolation(
                        rule="LAYER_DAG_BOUNDARY",
                        path=rel,
                        line=lineno,
                        message=f"Core package module `{rel}` imports archived legacy module `{mod}`.",
                        fix_hint="Never import `tools/legacy/` from `ajar/`. Implement clean pure-stdlib code in `ajar/`.",
                    )
                )
            for sdk in FORBIDDEN_LLM_SDKS:
                if _module_is_under(mod, sdk):
                    violations.append(
                        LintViolation(
                            rule="ZERO_LLM_ENGINE",
                            path=rel,
                            line=lineno,
                            message=f"Zero-LLM invariant violated: `{rel}` imports LLM SDK `{mod}`.",
                            fix_hint="Remove all LLM SDK imports from `ajar/`. Ajar's core engine must stay pure stdlib.",
                        )
                    )

            # 2. Layer-specific DAG rules
            if rel.startswith("ajar/domain/") and mod.startswith("ajar."):
                if not any(_module_is_under(mod, p) for p in DOMAIN_ALLOWED_AJAR_PREFIXES if p != "ajar"):
                    # Allow importing top-level `ajar` constants (e.g. `from ajar import EXIT_GATE_BLOCKED`)
                    # which yields `mod == "ajar"` and `mod == "ajar.<CONST>"`; disallow submodules.
                    top_sub = mod.split(".", 2)[1]
                    if (ajar_dir / f"{top_sub}.py").exists() or (ajar_dir / top_sub).is_dir():
                        violations.append(
                            LintViolation(
                                rule="LAYER_DAG_BOUNDARY",
                                path=rel,
                                line=lineno,
                                message=f"`ajar/domain/` must remain pure and cannot import `{mod}`.",
                                fix_hint="Move pure types/enums/transitions into `ajar/domain/` or move SQL/IO logic to `ajar/store/` or `ajar/services/`.",
                            )
                        )

            elif rel.startswith("ajar/store/") and mod.startswith("ajar."):
                if not any(_module_is_under(mod, p) for p in STORE_ALLOWED_AJAR_PREFIXES if p != "ajar"):
                    top_sub = mod.split(".", 2)[1]
                    if (ajar_dir / f"{top_sub}.py").exists() or (ajar_dir / top_sub).is_dir():
                        violations.append(
                            LintViolation(
                                rule="LAYER_DAG_BOUNDARY",
                                path=rel,
                                line=lineno,
                                message=f"`ajar/store/` cannot depend upward on `{mod}`.",
                                fix_hint="`ajar/store/` may only import stdlib, top-level `ajar` constants, `ajar.domain`, and `ajar.store`.",
                            )
                        )

            elif rel.startswith("ajar/services/") and any(
                _module_is_under(mod, p) for p in SERVICES_FORBIDDEN_AJAR_PREFIXES
            ):
                violations.append(
                    LintViolation(
                        rule="LAYER_DAG_BOUNDARY",
                        path=rel,
                        line=lineno,
                        message=f"`ajar/services/` cannot import transport/driver module `{mod}`.",
                        fix_hint="Transport layers (`cli.py`, `mcp.py`, `runner.py`) depend on `ajar/services/`, never the reverse.",
                    )
                )
    return violations


def check_no_hardcoded_devbox_paths(root: pathlib.Path) -> list[LintViolation]:
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
            rel = fpath.relative_to(root).as_posix()
            text = fpath.read_text(encoding="utf-8", errors="ignore")
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


def check_no_ambient_env_mutation_in_tests(root: pathlib.Path) -> list[LintViolation]:
    tests_dir = root / "tests"
    if not tests_dir.is_dir():
        return []
    violations: list[LintViolation] = []
    for py_path in sorted(tests_dir.rglob("*.py")):
        rel = py_path.relative_to(root).as_posix()
        src = py_path.read_text(encoding="utf-8")
        lines = src.splitlines()
        tree = ast.parse(src, filename=rel)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if (
                        isinstance(target, ast.Subscript)
                        and isinstance(target.value, ast.Attribute)
                        and isinstance(target.value.value, ast.Name)
                        and target.value.value.id == "os"
                        and target.value.attr == "environ"
                        and isinstance(target.slice, ast.Constant)
                        and target.slice.value in ("HOME", "PATH")
                    ):
                        line_txt = lines[node.lineno - 1] if 0 < node.lineno <= len(lines) else ""
                        if "arch-lint: ignore-fixture" in line_txt:
                            continue
                        violations.append(
                            LintViolation(
                                rule="NO_AMBIENT_ENV_MUTATION",
                                path=rel,
                                line=node.lineno,
                                message=f"Test mutates ambient `os.environ[{target.slice.value!r}]` directly.",
                                fix_hint="Pass an explicit `base_env=` dict or use `unittest.mock.patch.dict(os.environ, ...)` so parallel tests never leak state.",
                            )
                        )
    return violations


def check_no_unfiltered_tar_extract(root: pathlib.Path) -> list[LintViolation]:
    ajar_dir = root / "ajar"
    if not ajar_dir.is_dir():
        return []
    violations: list[LintViolation] = []
    for py_path in sorted(ajar_dir.rglob("*.py")):
        rel = py_path.relative_to(root).as_posix()
        tree = ast.parse(py_path.read_text(encoding="utf-8"), filename=rel)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("extract", "extractall")
            ):
                kw_names = {kw.arg for kw in node.keywords}
                if "filter" not in kw_names:
                    violations.append(
                        LintViolation(
                            rule="NO_UNFILTERED_TAR_EXTRACT",
                            path=rel,
                            line=node.lineno,
                            message=f"`{node.func.attr}()` called without explicit `filter=` argument.",
                            fix_hint="Pass `filter='tar'` (or `filter='data'`) and validate member paths against archive root to prevent tar-slip.",
                        )
                    )
    return violations


def run_all_checks(root: pathlib.Path) -> list[LintViolation]:
    violations: list[LintViolation] = []
    violations.extend(check_no_raw_sql_in_mcp(root))
    violations.extend(check_cli_raw_sql_ratchet(root))
    violations.extend(check_layer_dag_boundaries(root))
    violations.extend(check_no_hardcoded_devbox_paths(root))
    violations.extend(check_no_ambient_env_mutation_in_tests(root))
    violations.extend(check_no_unfiltered_tar_extract(root))
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
