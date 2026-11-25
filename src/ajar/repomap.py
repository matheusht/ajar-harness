"""Ring-1 polyglot structural indexer, slice query engine, and deterministic REALITY.md builder."""

from __future__ import annotations

import ast
import io
import json
import os
import re
import tokenize
from bisect import bisect_right
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Sequence

try:
    import tree_sitter_language_pack as _ts_pack  # type: ignore[import-not-found]
except ImportError:
    _ts_pack = None

_SKIP_DIRS = frozenset({
    ".git",
    ".ajar",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "target",
    "dist",
    "build",
    "out",
    "cache",
    ".mypy_cache",
    ".pytest_cache",
})

_CODE_EXTS = frozenset({
    ".py",
    ".sol",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".rs",
    ".go",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
})

_MANIFESTS = frozenset({
    "CMakeLists.txt",
    "Cargo.toml",
    "go.mod",
    "pyproject.toml",
    "package.json",
    "foundry.toml",
})

_QUAL_SINKS = frozenset({
    "syscall.Mount",
    "os.OpenFile",
    "exec.Command",
    "exec.CommandContext",
    "subprocess.run",
    "subprocess.Popen",
    "subprocess.call",
    "cursor.execute",
    "os.chmod",
    "fs.chmod",
})

_UNQUAL_SINKS = frozenset({
    "memcpy",
    "memmove",
    "realloc",
    "free",
    "system",
    "popen",
    "dlopen",
    "ALLOC_GROW",
    "subprocess",
    "eval",
    "exec",
    "open",
    "chmod",
    "delegatecall",
    "transferFrom",
    "safeTransferFrom",
    "mulDiv",
    "mulDivDown",
    "mulDivUp",
    "checkVaultStatus",
})

_ENTRY_NAMES = frozenset({
    "main",
    "__main__",
    "fallback",
    "receive",
    "unlockCallback",
    "nsenter",
    "ServeHTTP",
})

_ENTRY_PREFIXES = (
    "parse",
    "decode",
    "read",
    "load",
    "handle",
    "rpc_",
    "serve",
    "onMorpho",
)

_GUARD_PREFIXES = (
    "check",
    "verify",
    "validate",
    "require",
    "assert",
    "ensure",
    "auth",
    "guard",
    "only",
)

_CTRL_KW = frozenset({
    "if",
    "for",
    "while",
    "switch",
    "catch",
    "else",
    "return",
    "sizeof",
    "alignof",
    "delete",
})

_NON_FN = frozenset({"NULL", "nullptr", "true", "false", "None"})

_GUARD_LINE_RE = re.compile(
    r"\b(if|assert|require|revert|ensure|raise|checkVaultStatus)\b|assert!|debug_assert!|ensure!"
)
_SOL_DOT_CALL_RE = re.compile(r"\.call\s*\{")
_VTABLE_RE = re.compile(r"(?:\.|->)\s*([A-Za-z_]\w*)\s*(?<![=!<>])=(?!=)\s*&?\s*([A-Za-z_]\w*)\b")
_CALL_SCAN_RE = re.compile(r"\b([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?)\s*\(")
_SOL_DECL_RE = re.compile(r"\b(?:(?:function|modifier)\s+([A-Za-z_]\w*)|(fallback|receive))\s*\(")
_GO_DECL_RE = re.compile(r"\bfunc\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*[(\[]")
_RS_DECL_RE = re.compile(r"\bfn\s+([A-Za-z_]\w*)\s*[<(]")
_TS_DECL_RE = re.compile(r"\b(?:function\s+([A-Za-z_]\w*)|([A-Za-z_]\w*)\s*\()")
_C_DECL_RE = re.compile(r"\b(?:[A-Za-z_]\w*[\s*&:]+)+([A-Za-z_]\w*)\s*\(")

_CROSS_SEAM_LENSES = (
    "1. Parser/Consumer Differential: compare parse/decode validation vs downstream length use.",
    "2. Precision/Rounding Seam: audit mulDiv rounding, integer width casts, and ALLOC_GROW math.",
    "3. Callback/Reentrancy Seam: trace external/public -> .call{/onMorpho*/unlockCallback state.",
    "4. Privilege/Capability Seam: verify authority before Mount, OpenFile, transferFrom, or exec.",
    "5. Dispatch/Delegate Seam: inspect vtable (.decode/->parse), realloc/free, and 1-hop libs.",
)


def _norm_ext(suffix: str) -> str:
    low = suffix.lower()
    return low if low.startswith(".") else f".{low}"


def _blank_span(grid: list[list[str]], start: tuple[int, int], end: tuple[int, int]) -> None:
    srow, scol = start
    erow, ecol = end
    for r in range(srow - 1, min(erow, len(grid))):
        row = grid[r]
        c0 = scol if r == srow - 1 else 0
        c1 = ecol if r == erow - 1 else len(row)
        for c in range(c0, min(c1, len(row))):
            if row[c] not in ("\n", "\r"):
                row[c] = " "


def _strip_py_fallback(source: str, blank_strings: bool) -> str:
    cleaned = re.sub(
        r'("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\')',
        lambda m: "".join("\n" if ch == "\n" else " " for ch in m.group(0)),
        source,
    )
    lines: list[str] = []
    for line in cleaned.splitlines(keepends=True):
        pos = line.find("#")
        if pos >= 0:
            eol = "\n" if line.endswith("\n") else ""
            line = line[:pos] + (" " * (len(line) - pos - len(eol))) + eol
        if blank_strings:
            line = re.sub(r'"[^"\n]*"|\'[^\'\n]*\'', '""', line)
        lines.append(line)
    return "".join(lines)


def _strip_python(source: str, blank_strings: bool = False) -> str:
    doc_starts: set[tuple[int, int]] = set()
    try:
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.body and isinstance(node.body[0], ast.Expr):
                    val = node.body[0].value
                    if isinstance(val, ast.Constant) and isinstance(val.value, str):
                        doc_starts.add((val.lineno, val.col_offset))
    except SyntaxError:
        return _strip_py_fallback(source, blank_strings)
    grid = [list(row) for row in source.splitlines(keepends=True)]
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            is_doc = tok.type == tokenize.STRING and tok.start in doc_starts
            is_str = blank_strings and tok.type == tokenize.STRING
            if tok.type == tokenize.COMMENT or is_doc or is_str:
                _blank_span(grid, tok.start, tok.end)
    except tokenize.TokenError:
        return _strip_py_fallback(source, blank_strings)
    return "".join("".join(row) for row in grid)


def _strip_c_family(source: str, blank_strings: bool = False) -> str:
    out: list[str] = []
    idx = 0
    size = len(source)
    state = "code"
    while idx < size:
        ch = source[idx]
        nxt = source[idx + 1] if idx + 1 < size else ""
        if state == "code":
            if ch == "/" and nxt in ("/", "*"):
                out.append("  ")
                state = "line" if nxt == "/" else "block"
                idx += 2
                continue
            if ch in ('"', "'", "`"):
                out.append(ch)
                state = ch
                idx += 1
                continue
            out.append(ch)
        elif state == "line":
            if ch == "\n":
                out.append("\n")
                state = "code"
            else:
                out.append("\r" if ch == "\r" else " ")
        elif state == "block":
            if ch == "*" and nxt == "/":
                out.append("  ")
                state = "code"
                idx += 2
                continue
            out.append(ch if ch in ("\n", "\r") else " ")
        else:
            if ch == "\\" and idx + 1 < size:
                out.append(" " if blank_strings else ch)
                out.append(nxt if nxt in ("\n", "\r") or not blank_strings else " ")
                idx += 2
                continue
            if ch == state:
                out.append(ch)
                state = "code"
            elif ch in ("\n", "\r"):
                out.append(ch)
            else:
                out.append(" " if blank_strings else ch)
        idx += 1
    return "".join(out)


def strip_comments_and_docstrings(source: str, suffix: str) -> str:
    ext = _norm_ext(suffix)
    if ext == ".py":
        return _strip_python(source, blank_strings=False)
    return _strip_c_family(source, blank_strings=False)


def has_real_code_guard(source: str, suffix: str, line: int) -> bool:
    if line < 1:
        return False
    ext = _norm_ext(suffix)
    stripped = _strip_python(source, True) if ext == ".py" else _strip_c_family(source, True)
    lines = stripped.splitlines()
    if line > len(lines):
        return False
    return bool(_GUARD_LINE_RE.search(lines[line - 1]))


def _classify_call(raw: str, calls: set[str], sinks: set[str], guards: set[str]) -> None:
    tail = raw.rsplit(".", 1)[-1]
    if tail in _CTRL_KW:
        return
    calls.add(raw)
    if raw in _QUAL_SINKS:
        sinks.add(raw)
    elif tail in _UNQUAL_SINKS:
        sinks.add(tail)
    elif raw.startswith("subprocess."):
        sinks.add("subprocess")
    if tail.startswith(_GUARD_PREFIXES) or tail == "checkVaultStatus":
        guards.add(tail)


def _is_entry_name(name: str) -> bool:
    return name in _ENTRY_NAMES or name.startswith(_ENTRY_PREFIXES)


def _find_body_bounds(clean: str, start: int) -> tuple[int, int] | None:
    parens = 0
    idx = start
    size = len(clean)
    brace_open = -1
    while idx < size:
        ch = clean[idx]
        if ch == "(":
            parens += 1
        elif ch == ")":
            parens = max(0, parens - 1)
        elif parens == 0 and ch == "\x3b":
            return None
        elif parens == 0 and ch == "{":
            brace_open = idx
            break
        idx += 1
    if brace_open < 0:
        return None
    depth = 0
    for pos in range(brace_open, size):
        if clean[pos] == "{":
            depth += 1
        elif clean[pos] == "}":
            depth -= 1
            if depth == 0:
                return brace_open, pos + 1
    return None


def _ts_extra_calls(source: str, ext: str) -> set[str]:
    if _ts_pack is None:
        return set()
    lang_map = {".sol": "solidity", ".c": "c", ".cpp": "cpp", ".rs": "rust", ".go": "go"}
    lang = lang_map.get(ext)
    if not lang:
        return set()
    try:
        tree = _ts_pack.get_parser(lang).parse(source.encode("utf-8"))
    except Exception:
        return set()
    found: set[str] = set()
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if "call" in node.type and node.children:
            head = node.children[0].text
            if head:
                found.add(head.decode("utf-8", errors="ignore").strip())
        stack.extend(node.children)
    return found


def _index_python(source: str) -> tuple[int, list[dict[str, Any]], list[list[Any]]]:
    stripped = _strip_python(source, blank_strings=False)
    loc = sum(1 for row in stripped.splitlines() if row.strip())
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return loc, [], []
    symbols: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        decos = [ast.unparse(d).lower() for d in node.decorator_list]
        deco_entry = any(
            any(k in d for k in ("route", ".get", ".post", "tool", "rpc", "command"))
            for d in decos
        )
        calls: set[str] = set()
        sinks: set[str] = set()
        guards: set[str] = set()
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                if isinstance(sub.func, ast.Name):
                    _classify_call(sub.func.id, calls, sinks, guards)
                elif isinstance(sub.func, ast.Attribute):
                    prefix = sub.func.value.id if isinstance(sub.func.value, ast.Name) else ""
                    full = f"{prefix}.{sub.func.attr}" if prefix else sub.func.attr
                    _classify_call(full, calls, sinks, guards)
        symbols.append({
            "name": node.name,
            "line": node.lineno,
            "entry": _is_entry_name(node.name) or deco_entry,
            "sinks": sorted(sinks),
            "calls": sorted(calls),
            "guards": sorted(guards),
        })
    symbols.sort(key=lambda s: (s["line"], s["name"]))
    return loc, symbols, []


def _decl_pattern(ext: str) -> re.Pattern[str]:
    if ext == ".sol":
        return _SOL_DECL_RE
    if ext == ".go":
        return _GO_DECL_RE
    if ext == ".rs":
        return _RS_DECL_RE
    if ext in (".ts", ".tsx", ".js", ".jsx"):
        return _TS_DECL_RE
    return _C_DECL_RE


def _index_polyglot(source: str, ext: str) -> tuple[int, list[dict[str, Any]], list[list[Any]]]:
    clean = _strip_c_family(source, blank_strings=True)
    loc = sum(1 for row in clean.splitlines() if row.strip())
    nl_pos = [idx for idx, ch in enumerate(clean) if ch == "\n"]
    vtables: list[list[Any]] = []
    for vm in _VTABLE_RE.finditer(clean):
        field_name = vm.group(1)
        target = vm.group(2)
        if target not in _NON_FN and not target[0].isdigit():
            vtables.append([field_name, target, bisect_right(nl_pos, vm.start()) + 1])
    ts_calls = _ts_extra_calls(clean, ext)
    symbols: list[dict[str, Any]] = []
    seen_spans: set[tuple[int, str]] = set()
    for dm in _decl_pattern(ext).finditer(clean):
        name = next((g for g in dm.groups() if g), "")
        if not name or name in _CTRL_KW:
            continue
        bounds = _find_body_bounds(clean, dm.start())
        if bounds is None:
            continue
        b_open, b_close = bounds
        line_no = bisect_right(nl_pos, dm.start()) + 1
        if (line_no, name) in seen_spans:
            continue
        seen_spans.add((line_no, name))
        header = clean[dm.start() : b_open]
        body = clean[b_open:b_close]
        entry = _is_entry_name(name)
        if ext == ".sol" and re.search(r"\b(external|public)\b", header):
            entry = True
        if ext == ".go" and name[0].isupper():
            if any(tok in header for tok in ("ResponseWriter", "Request", "Context")):
                entry = True
        calls: set[str] = set()
        sinks: set[str] = set()
        guards: set[str] = set()
        if ext == ".sol" and _SOL_DOT_CALL_RE.search(body):
            sinks.add(".call{")
        for cm in _CALL_SCAN_RE.finditer(body):
            _classify_call(cm.group(1), calls, sinks, guards)
        for extra in ts_calls:
            if extra in body:
                _classify_call(extra, calls, sinks, guards)
        symbols.append({
            "name": name,
            "line": line_no,
            "entry": entry,
            "sinks": sorted(sinks),
            "calls": sorted(calls),
            "guards": sorted(guards),
        })
    symbols.sort(key=lambda s: (s["line"], s["name"]))
    return loc, symbols, vtables


def _extract_delegates(filename: str, text: str) -> list[str]:
    found: set[str] = set()
    if filename == "package.json":
        try:
            data = json.loads(text)
            found.update(data.get("dependencies", {}).keys())
        except ValueError:
            pass
    elif filename == "CMakeLists.txt":
        pat = r"(?:find_package|FetchContent_Declare|add_subdirectory)\(\s*([\w.+-]+)"
        for m in re.finditer(pat, text):
            found.add(m.group(1))
    elif filename == "go.mod":
        for m in re.finditer(r"\b([a-zA-Z0-9._-]+\.[a-zA-Z0-9._-]+/[a-zA-Z0-9._/-]+)", text):
            found.add(m.group(1))
    elif filename == "Cargo.toml":
        in_deps = False
        for line in text.splitlines():
            sec = line.strip()
            if sec.startswith("["):
                in_deps = "dependencies" in sec
            elif in_deps and "=" in sec and not sec.startswith("#"):
                found.add(sec.split("=", 1)[0].strip())
    elif filename == "pyproject.toml":
        for m in re.finditer(r'"([A-Za-z0-9_.-]+)\s*(?:[><=~!\[]|")', text):
            if m.group(1).lower() not in ("python", "setuptools", "wheel", "hatchling"):
                found.add(m.group(1))
    elif filename == "foundry.toml":
        for m in re.finditer(r"""['"]([^='"#\s]+)=([^'"]+)['"]""", text):
            found.add(m.group(1).rstrip("/"))
    return sorted(found)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{os.getpid()}.tmp"
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def index_repo(repo: Path) -> dict[str, Any]:
    root = Path(repo).resolve()
    cache_path = root / ".ajar" / "repomap_cache.json"
    old_files: dict[str, Any] = {}
    if cache_path.exists():
        try:
            old_files = json.loads(cache_path.read_text(encoding="utf-8")).get("files", {})
        except (OSError, ValueError):
            old_files = {}
    files_out: dict[str, Any] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
        for fname in sorted(filenames):
            fpath = Path(dirpath) / fname
            ext = fpath.suffix.lower()
            if ext not in _CODE_EXTS and fname not in _MANIFESTS:
                continue
            try:
                st = fpath.stat()
            except OSError:
                continue
            rel = fpath.relative_to(root).as_posix()
            cached = old_files.get(rel)
            if cached and cached.get("mtime_ns") == st.st_mtime_ns and cached.get("size") == st.st_size:
                files_out[rel] = cached
                continue
            try:
                src = fpath.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if fname in _MANIFESTS:
                files_out[rel] = {
                    "mtime_ns": st.st_mtime_ns,
                    "size": st.st_size,
                    "loc": 0,
                    "delegates": _extract_delegates(fname, src),
                    "symbols": [],
                    "vtables": [],
                }
            elif ext == ".py":
                loc, syms, vtabs = _index_python(src)
                files_out[rel] = {
                    "mtime_ns": st.st_mtime_ns,
                    "size": st.st_size,
                    "loc": loc,
                    "delegates": [],
                    "symbols": syms,
                    "vtables": vtabs,
                }
            else:
                loc, syms, vtabs = _index_polyglot(src, ext)
                files_out[rel] = {
                    "mtime_ns": st.st_mtime_ns,
                    "size": st.st_size,
                    "loc": loc,
                    "delegates": [],
                    "symbols": syms,
                    "vtables": vtabs,
                }
    payload = {"files": files_out}
    _atomic_write(cache_path, json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return payload


def _build_graph(files_map: dict[str, Any]) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    by_name: dict[str, list[str]] = defaultdict(list)
    vtable_map: dict[str, set[str]] = defaultdict(set)
    for rel in sorted(files_map):
        fdata = files_map[rel]
        for field_name, target, _ in fdata.get("vtables", []):
            vtable_map[field_name].add(target)
        for sym in fdata.get("symbols", []):
            nid = f"{rel}:{sym['line']}:{sym['name']}"
            nodes[nid] = {**sym, "file": rel, "id": nid, "vtable": False}
            by_name[sym["name"]].append(nid)
    for field_name, targets in vtable_map.items():
        for tname in targets:
            for nid in by_name.get(tname, []):
                nodes[nid]["vtable"] = True
                if _is_entry_name(field_name):
                    nodes[nid]["entry"] = True
    weights: dict[str, dict[str, float]] = defaultdict(dict)
    adj: dict[str, list[str]] = defaultdict(list)
    rev: dict[str, list[str]] = defaultdict(list)
    for uid in sorted(nodes):
        u = nodes[uid]
        for call in u["calls"]:
            tail = call.rsplit(".", 1)[-1]
            cands = list(by_name.get(call) or by_name.get(tail, []))
            for vt_target in sorted(vtable_map.get(tail, ())):
                cands.extend(by_name.get(vt_target, []))
            uniq = [vid for vid in dict.fromkeys(sorted(cands)) if vid != uid]
            deg = len(uniq)
            if deg == 0:
                continue
            for vid in uniq:
                same_file = nodes[vid]["file"] == u["file"]
                w = (1.0 / deg) if same_file else (1.0 / (deg * deg))
                weights[uid][vid] = weights[uid].get(vid, 0.0) + w
                if deg <= 8 or same_file or nodes[vid]["sinks"] or nodes[vid]["vtable"]:
                    adj[uid].append(vid)
                    rev[vid].append(uid)
    ordered = sorted(nodes)
    pers: dict[str, float] = {}
    for uid in ordered:
        u = nodes[uid]
        p = 0.25 if "/test" in f"/{u['file'].lower()}" else 1.0
        p += (3.0 if u["entry"] else 0.0) + (4.0 if u["sinks"] else 0.0)
        pers[uid] = p + (1.5 if u["vtable"] else 0.0)
    total_p = sum(pers.values()) or 1.0
    pers = {uid: val / total_p for uid, val in pers.items()}
    rank = dict(pers)
    for _ in range(15):
        dangling = sum(rank[u] for u in ordered if not weights[u])
        nxt = {u: (0.15 + 0.85 * dangling) * pers[u] for u in ordered}
        for uid in ordered:
            out_w = sum(weights[uid].values())
            if out_w > 0.0:
                for vid, w in weights[uid].items():
                    nxt[vid] += 0.85 * rank[uid] * (w / out_w)
        rank = nxt
    slices = _bidirectional_slices(ordered, nodes, adj, rev, rank, max_hops=6)
    return {
        "nodes": nodes,
        "by_name": by_name,
        "adj": adj,
        "rev": rev,
        "rank": rank,
        "slices": slices,
    }


def _bidirectional_slices(
    ordered: list[str],
    nodes: dict[str, dict[str, Any]],
    adj: dict[str, list[str]],
    rev: dict[str, list[str]],
    rank: dict[str, float],
    max_hops: int = 6,
) -> list[list[str]]:
    half = max_hops // 2
    f_dist: dict[str, int] = {}
    f_prev: dict[str, str | None] = {}
    fq: deque[str] = deque()
    for uid in ordered:
        if nodes[uid]["entry"]:
            f_dist[uid] = 0
            f_prev[uid] = None
            fq.append(uid)
    while fq:
        cur = fq.popleft()
        if f_dist[cur] < half:
            for nxt in adj.get(cur, ()):
                if nxt not in f_dist:
                    f_dist[nxt] = f_dist[cur] + 1
                    f_prev[nxt] = cur
                    fq.append(nxt)
    b_dist: dict[str, int] = {}
    b_next: dict[str, str | None] = {}
    bq: deque[str] = deque()
    for uid in ordered:
        if nodes[uid]["sinks"]:
            b_dist[uid] = 0
            b_next[uid] = None
            bq.append(uid)
    while bq:
        cur = bq.popleft()
        if b_dist[cur] < max_hops - half:
            for prv in rev.get(cur, ()):
                if prv not in b_dist:
                    b_dist[prv] = b_dist[cur] + 1
                    b_next[prv] = cur
                    bq.append(prv)
    meets = [
        u
        for u in ordered
        if u in f_dist and u in b_dist and f_dist[u] + b_dist[u] <= max_hops
    ]
    meets.sort(key=lambda u: (f_dist[u] + b_dist[u], -rank.get(u, 0.0), u))
    chains: list[list[str]] = []
    seen_keys: set[tuple[str, str]] = set()
    for mid in meets:
        left: list[str] = []
        node_cur: str | None = mid
        while node_cur is not None:
            left.append(node_cur)
            node_cur = f_prev[node_cur]
        left.reverse()
        node_cur = b_next[mid]
        while node_cur is not None:
            left.append(node_cur)
            node_cur = b_next[node_cur]
        key = (left[0], left[-1])
        if len(set(left)) == len(left) and key not in seen_keys:
            seen_keys.add(key)
            chains.append(left)
    return chains


def _fmt_node(node: dict[str, Any]) -> str:
    tags: list[str] = []
    if node["entry"]:
        tags.append("entry")
    if node["vtable"]:
        tags.append("vtable")
    if node["sinks"]:
        tags.append("sink:" + ",".join(node["sinks"]))
    suffix = f" [{' '.join(tags)}]" if tags else ""
    return f"{node['file']}:{node['line']} {node['name']}{suffix}"


def ego_query(repo: Path, symbol: str, hops: int = 1) -> str:
    graph = _build_graph(index_repo(repo)["files"])
    nodes = graph["nodes"]
    seeds = list(graph["by_name"].get(symbol, []))
    if not seeds:
        seeds = [u for u in sorted(nodes) if symbol in nodes[u]["sinks"] or symbol in u]
    if not seeds:
        return f"No symbol matching '{symbol}'"
    out_lines: list[str] = []
    for sid in seeds[:8]:
        out_lines.append(_fmt_node(nodes[sid]))
        q_out: deque[tuple[str, int]] = deque([(sid, 0)])
        seen_o = {sid}
        while q_out:
            cur, d = q_out.popleft()
            if d < hops:
                for nxt in graph["adj"].get(cur, ()):
                    if nxt not in seen_o:
                        seen_o.add(nxt)
                        out_lines.append("  " * (d + 1) + "-> " + _fmt_node(nodes[nxt]))
                        q_out.append((nxt, d + 1))
        q_in: deque[tuple[str, int]] = deque([(sid, 0)])
        seen_i = {sid}
        while q_in:
            cur, d = q_in.popleft()
            if d < hops:
                for prv in graph["rev"].get(cur, ()):
                    if prv not in seen_i:
                        seen_i.add(prv)
                        out_lines.append("  " * (d + 1) + "<- " + _fmt_node(nodes[prv]))
                        q_in.append((prv, d + 1))
    return "\n".join(out_lines)


def backslice_query(repo: Path, symbol: str, hops: int = 5) -> str:
    graph = _build_graph(index_repo(repo)["files"])
    nodes = graph["nodes"]
    seeds = list(graph["by_name"].get(symbol, []))
    if not seeds:
        seeds = [u for u in sorted(nodes) if symbol in nodes[u]["sinks"]]
    if not seeds:
        return f"No sink or symbol matching '{symbol}'"
    lines: list[str] = []
    queue: deque[tuple[str, list[str]]] = deque((s, [s]) for s in seeds[:8])
    visited: set[str] = set(seeds[:8])
    while queue:
        cur, chain = queue.popleft()
        preds = [p for p in graph["rev"].get(cur, ()) if p not in chain]
        if not preds or len(chain) - 1 >= hops or nodes[cur]["entry"]:
            rendered = " -> ".join(_fmt_node(nodes[nid]) for nid in reversed(chain))
            guards = sorted({g for nid in chain for g in nodes[nid]["guards"]})
            guard_note = f" (guards: {', '.join(guards)})" if guards else ""
            lines.append(f"- {rendered}{guard_note}")
            continue
        for prv in preds[:6]:
            if prv not in visited or nodes[prv]["entry"]:
                visited.add(prv)
                queue.append((prv, chain + [prv]))
    return "\n".join(lines)


def _preserved_falsified(reality_path: Path) -> str:
    if not reality_path.exists():
        return "- (none recorded)"
    text = reality_path.read_text(encoding="utf-8", errors="replace")
    marker = "## Falsified Hypotheses"
    pos = text.find(marker)
    if pos < 0:
        return "- (none recorded)"
    tail = text[pos + len(marker) :].strip()
    return tail if tail else "- (none recorded)"


def build_repomap_and_reality(
    repo: Path,
    profiles: Sequence[str] = ("upstream",),
    max_tokens: int = 1000,
) -> Path:
    root = Path(repo).resolve()
    files_map = index_repo(root)["files"]
    graph = _build_graph(files_map)
    nodes = graph["nodes"]
    rank = graph["rank"]
    total_loc = sum(f.get("loc", 0) for f in files_map.values())
    code_files = sum(1 for f in files_map.values() if f.get("loc", 0) > 0 or f.get("symbols"))
    delegates = sorted({d for f in files_map.values() for d in f.get("delegates", [])})
    compact = total_loc < 8000
    spine_limit = min(max_tokens, 550) if compact else max_tokens
    reality_path = root / ".ajar" / "REALITY.md"
    falsified = _preserved_falsified(reality_path)
    prof_str = ", ".join(profiles) if profiles else "upstream"
    del_str = ", ".join(delegates[:16]) if delegates else "none"
    slice_lines: list[str] = []
    for chain in graph["slices"][:12]:
        slice_lines.append("- " + " -> ".join(_fmt_node(nodes[u]) for u in chain))
    if not slice_lines:
        for uid in sorted(nodes, key=lambda u: (-rank[u], u)):
            if nodes[uid]["entry"] or nodes[uid]["sinks"]:
                slice_lines.append(f"- {_fmt_node(nodes[uid])}")
            if len(slice_lines) >= 8:
                break
    ranked = sorted(nodes, key=lambda u: (-rank[u], u))
    cap = 10 if compact else 28
    spine_lines: list[str] = []
    char_budget = max(400, spine_limit * 4)
    used_chars = 0
    for uid in ranked[:cap]:
        line = f"- {_fmt_node(nodes[uid])} (pr={rank[uid]:.4f})"
        if used_chars + len(line) > char_budget and spine_lines:
            break
        spine_lines.append(line)
        used_chars += len(line) + 1
    sections = [
        "# REALITY MAP",
        f"Profiles: {prof_str}",
        f"Scope: {code_files} files | {total_loc} LoC | Auto-compact: {'yes' if compact else 'no'}",
        f"Data-Plane Delegates (1-hop): {del_str}",
        "",
        "## Cross-Seam Lenses",
        *_CROSS_SEAM_LENSES,
        "",
        "## Entry-to-Sink Slice",
        *(slice_lines or ["- (no entry-to-sink slices indexed)"]),
        "",
        "## PageRank Spine",
        *(spine_lines or ["- (no symbols indexed)"]),
        "",
        "## Falsified Hypotheses",
        falsified,
        "",
    ]
    _atomic_write(reality_path, "\n".join(sections))
    return reality_path
