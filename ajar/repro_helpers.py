"""Pure-stdlib runtime provisioning and AST validation for Ajar reproduction helpers.

Leaf module (zero `ajar.*` imports) shared by `repro_source`, `repro_compose`,
`diff_sync`, and `workspace` without circular dependencies.
"""

from __future__ import annotations

import ast
import os
import pathlib
import re
import stat

STAGE_CONTEXT_INIT_PY = '''"""Auto-provisioned Ajar Composable State Builder runtime (`StageContext`)."""

from __future__ import annotations

import json
import os
import pathlib
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StageContext:
    slot_dir: pathlib.Path
    mode: str = "exploit_path"
    ablated_primitives: frozenset[str] = field(default_factory=frozenset)
    state: dict[str, Any] = field(default_factory=dict)
    receipts: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_env(cls) -> "StageContext":
        ablated = frozenset(
            x.strip() for x in os.environ.get("AJAR_ABLATE_STEPS", "").split(",") if x.strip()
        )
        mode = os.environ.get("AJAR_REPRO_MODE", "exploit_path").strip() or "exploit_path"
        raw_seed = os.environ.get("AJAR_STAGE_STATE_JSON", "{}").strip() or "{}"
        try:
            seed = json.loads(raw_seed)
            if not isinstance(seed, dict):
                seed = {}
        except Exception:
            seed = {}
        return cls(
            slot_dir=pathlib.Path.cwd(),
            mode=mode,
            ablated_primitives=ablated,
            state=seed,
        )

    @property
    def is_active_probe(self) -> bool:
        return self.mode in ("exploit_path", "active_probe")

    def is_ablated(self, primitive_id: str) -> bool:
        return self.mode == "benign_control" or primitive_id in self.ablated_primitives

    def record_step(self, primitive_id: str, **outputs: Any) -> None:
        self.state.update(outputs)
        self.receipts.append({"primitive_id": primitive_id, "keys": sorted(outputs.keys())})

    def to_json(self) -> str:
        return json.dumps(
            {
                "mode": self.mode,
                "ablated_primitives": sorted(self.ablated_primitives),
                "state": self.state,
                "receipts": self.receipts,
            },
            sort_keys=True,
            default=str,
        )
'''

SITECUSTOMIZE_LOOPBACK_GUARD_PY = '''"""Container loopback socket guard when `unshare -rn` is unavailable in `source` mode."""

from __future__ import annotations

import ipaddress
import os
import socket

if os.environ.get("AJAR_BLOCK_EXTERNAL_NET") == "1":
    _orig_connect = socket.socket.connect
    _orig_connect_ex = socket.socket.connect_ex
    _orig_sendto = socket.socket.sendto

    def _is_loopback_target(family: int, address: object) -> bool:
        if family not in (socket.AF_INET, socket.AF_INET6):
            return True
        if not isinstance(address, tuple) or not address:
            return True
        host = str(address[0]).strip()
        if host in ("", "localhost", "0.0.0.0", "::"):
            return True
        if host.startswith("::ffff:"):
            host = host[7:]
        try:
            ip = ipaddress.ip_address(host)
            return bool(ip.is_loopback or ip.is_unspecified)
        except ValueError:
            return False

    def _guarded_connect(self: socket.socket, address: object) -> object:
        if not _is_loopback_target(self.family, address):
            raise PermissionError(
                f"Ajar source isolation blocked outbound non-loopback socket connect to {address!r}"
            )
        return _orig_connect(self, address)

    def _guarded_connect_ex(self: socket.socket, address: object) -> int:
        if not _is_loopback_target(self.family, address):
            raise PermissionError(
                f"Ajar source isolation blocked outbound non-loopback socket connect_ex to {address!r}"
            )
        return _orig_connect_ex(self, address)

    def _guarded_sendto(self: socket.socket, data: bytes, *args: object) -> int:
        address = args[-1] if args else None
        if not _is_loopback_target(self.family, address):
            raise PermissionError(
                f"Ajar source isolation blocked outbound non-loopback socket sendto {address!r}"
            )
        return _orig_sendto(self, data, *args)

    socket.socket.connect = _guarded_connect  # type: ignore[assignment]
    socket.socket.connect_ex = _guarded_connect_ex  # type: ignore[assignment]
    socket.socket.sendto = _guarded_sendto  # type: ignore[assignment]
'''

HELPER_EXEC_CLI_SH = """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import pathlib
import sys

from ajar_helpers import StageContext


def main() -> int:
    p = argparse.ArgumentParser(description="Execute a verified ajar_helpers capability callable.")
    p.add_argument("spec", help="<module_name>.<callable_name>")
    p.add_argument("--emit-json", help="Optional file path to write StageContext JSON.")
    args = p.parse_args()
    mod_name, sep, fn_name = args.spec.rpartition(".")
    if not sep or not mod_name or not fn_name:
        sys.stderr.write("Expected <module_name>.<callable_name>\\n")
        return 2
    full_mod = mod_name if mod_name.startswith("ajar_helpers.") else f"ajar_helpers.{mod_name}"
    mod = importlib.import_module(full_mod)
    fn = getattr(mod, fn_name)
    ctx = StageContext.from_env()
    out = fn(ctx)
    if isinstance(out, StageContext):
        ctx = out
    rendered = ctx.to_json()
    if args.emit_json:
        pathlib.Path(args.emit_json).write_text(rendered + "\\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""

FORBIDDEN_HELPER_IMPORTS: frozenset[str] = frozenset(
    {"urllib.request", "http.client", "ftplib", "smtplib", "telnetlib", "xmlrpc.client"}
)


def _write_readonly_file(path: pathlib.Path, content: str, mode: int = 0o444) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        os.chmod(path, stat.S_IWUSR | stat.S_IRUSR)
    path.write_text(content, encoding="utf-8")
    os.chmod(path, mode)


def ensure_helpers_runtime(run_dir: pathlib.Path) -> pathlib.Path:
    """Provision `repro/helpers/ajar_helpers` (`StageContext`), `sitecustomize.py`, and `ajar-helper-exec`."""
    helpers_dir = run_dir / "repro" / "helpers"
    pkg_dir = helpers_dir / "ajar_helpers"
    bin_dir = helpers_dir / "bin"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    bin_dir.mkdir(parents=True, exist_ok=True)

    _write_readonly_file(pkg_dir / "__init__.py", STAGE_CONTEXT_INIT_PY, mode=0o444)
    _write_readonly_file(helpers_dir / "sitecustomize.py", SITECUSTOMIZE_LOOPBACK_GUARD_PY, mode=0o444)
    _write_readonly_file(bin_dir / "ajar-helper-exec", HELPER_EXEC_CLI_SH, mode=0o555)
    return helpers_dir


def sanitize_module_name(primitive_id: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_]", "_", primitive_id.strip())
    if not clean or clean[0].isdigit():
        clean = f"prim_{clean}"
    return clean[:64]


def validate_helper_python_ast(source_text: str, callable_name: str, *, allow_network: bool = False) -> tuple[bool, str, bool]:
    """Validate Python helper syntax, required callable presence, and forbidden network imports.

    Returns `(ok, message, has_verify_self)`.
    """
    try:
        tree = ast.parse(source_text)
    except SyntaxError as exc:
        return (False, f"Helper Python syntax error at line {exc.lineno}: {exc.msg}", False)

    defined_funcs: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defined_funcs.add(node.name)
        elif not allow_network and isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in FORBIDDEN_HELPER_IMPORTS:
                    return (False, f"Helper imports forbidden network module in source mode: {alias.name}", False)
        elif not allow_network and isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                full = f"{mod}.{alias.name}" if mod else alias.name
                if mod in FORBIDDEN_HELPER_IMPORTS or full in FORBIDDEN_HELPER_IMPORTS:
                    return (False, f"Helper imports forbidden network module in source mode: {full}", False)

    if callable_name not in defined_funcs:
        return (False, f"Helper file does not define required callable `def {callable_name}(ctx)`.", False)
    return (True, "ok", "verify_self" in defined_funcs)

