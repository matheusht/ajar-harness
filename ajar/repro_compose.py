"""Composable State Builder, Capability Helpers, Chain Ablation, and Scratch Instrumentation (`Ajar v3.2`).

Turns verified `primitives` into read-only (`0444`) importable capability modules mounted at
`~/.ajar/runs/<run_id>/repro/helpers/ajar_helpers/` outside `repro/slot-<k>` so:
- Zero untracked helper files ever pollute `slot-<k>` or the target repository.
- Downstream `reproduce` and `chain` workers import Stage 1 state builders directly via
  `StageContext` instead of re-deriving complex framing inside monolithic shell strings.
- `ajar chain propose` executes inside an isolated `slot-<k>` worktree with `--oracle-json`
  and proves $N$-step marginal causal contribution by ablating each primitive step.
- `ajar claim instrument` executes scratch trace probes in `slot-inst` to unblock
  `needs_instrumentation` claims cleanly.
"""

from __future__ import annotations

import ast
import fcntl
import hashlib
import json
import os
import pathlib
import re
import sqlite3
import stat
import subprocess
from typing import Any, Mapping, Sequence

from ajar import EXIT_GATE_BLOCKED, EXIT_USER_ERROR
from ajar.db import AjarError, log_event, new_id, utc_now_iso
from ajar.epistemic_hooks import on_primitive_added, parse_tag_list
from ajar.redact import scrub_text, scrubbed_subprocess_env
from ajar.repro_source import (
    _acquire_slot,
    _bump_files_mtime,
    _clean_slot_preserving_objects,
    _evaluate_defect_fired,
    _neutralize_python_pth_escapes,
    _prepare_slot_worktree,
    _run_shell_in_slot,
    init_source_mirror,
    resolve_local_build_cache_dir,
    validate_no_static_source_cheat,
)

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


def promote_primitive_helper(
    conn: sqlite3.Connection,
    *,
    run_dir: pathlib.Path,
    target_dir: pathlib.Path,
    primitive_id: str,
    helper_file: pathlib.Path,
    callable_name: str,
    provides_tags: Sequence[str] = (),
    requires_tags: Sequence[str] = (),
    self_test_cmd: str = "",
    timeout_sec: int = 45,
    worker_id: str = "worker",
) -> dict[str, Any]:
    """Verify a Stage capability helper in both `exploit_path` and `benign_control` modes and mount it `0444`."""
    prim = conn.execute("SELECT * FROM primitives WHERE primitive_id = ?", (primitive_id,)).fetchone()
    if prim is None:
        raise AjarError(f"Unknown primitive_id: {primitive_id}", EXIT_USER_ERROR)
    if not helper_file.is_file():
        raise AjarError(f"Helper source file not found: {helper_file}", EXIT_USER_ERROR)
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", callable_name.strip()):
        raise AjarError(f"Invalid --callable identifier: {callable_name!r}", EXIT_USER_ERROR)

    run = conn.execute("SELECT target_mode FROM runs LIMIT 1").fetchone()
    allow_net = bool(run and str(run["target_mode"]) == "live")
    src_text = helper_file.read_text(encoding="utf-8", errors="replace")
    ok_ast, ast_msg, has_verify_self = validate_helper_python_ast(
        src_text, callable_name.strip(), allow_network=allow_net
    )
    if not ok_ast:
        raise AjarError(f"Helper pre-flight check failed: {ast_msg}", EXIT_GATE_BLOCKED)

    helpers_dir = ensure_helpers_runtime(run_dir)
    mod_name = sanitize_module_name(primitive_id)
    dest_path = helpers_dir / "ajar_helpers" / f"{mod_name}.py"
    rel_helper_path = f"repro/helpers/ajar_helpers/{mod_name}.py"

    # Write candidate helper and verify inside an isolated `slot-<k>` worktree before locking `0444`.
    _write_readonly_file(dest_path, src_text, mode=0o644)

    mirror_dir = init_source_mirror(run_dir, target_dir)
    repro_dir = run_dir / "repro"
    slot_idx, lock_fh = _acquire_slot(repro_dir)
    slot_dir = repro_dir / f"slot-{slot_idx}"
    cache_dir = resolve_local_build_cache_dir(run_dir, f"cache-{slot_idx}")

    check_fn = "verify_self" if has_verify_self else callable_name.strip()
    default_driver = (
        f"python3 -c 'import json; from ajar_helpers import StageContext; "
        f"import ajar_helpers.{mod_name} as m; ctx = StageContext.from_env(); "
        f"r = m.{check_fn}(ctx); ctx = r if isinstance(r, StageContext) else ctx; "
        f"print(\"AJAR_HELPER_STATE:\" + json.dumps(sorted(ctx.state.keys())))'"
    )
    eff_cmd = self_test_cmd.strip() or default_driver

    try:
        _prepare_slot_worktree(mirror_dir, slot_dir)
        exp_res = _run_shell_in_slot(
            eff_cmd,
            slot_dir=slot_dir,
            cache_dir=cache_dir,
            timeout_sec=timeout_sec,
            helpers_dir=helpers_dir,
            extra_env={"AJAR_REPRO_MODE": "exploit_path", "AJAR_ABLATE_STEPS": ""},
        )
        subprocess.run(["git", "-C", str(slot_dir), "reset", "--hard", "HEAD"], capture_output=True, check=False)
        _clean_slot_preserving_objects(slot_dir, check=False)

        ctrl_res = _run_shell_in_slot(
            eff_cmd,
            slot_dir=slot_dir,
            cache_dir=cache_dir,
            timeout_sec=timeout_sec,
            helpers_dir=helpers_dir,
            extra_env={"AJAR_REPRO_MODE": "benign_control", "AJAR_ABLATE_STEPS": primitive_id},
        )
    except Exception:
        dest_path.unlink(missing_ok=True)
        raise
    finally:
        if (slot_dir / ".git").exists():
            subprocess.run(["git", "-C", str(slot_dir), "reset", "--hard", "HEAD"], capture_output=True, check=False)
            _clean_slot_preserving_objects(slot_dir, check=False)
        fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)
        lock_fh.close()

    if exp_res["exit_code"] != 0 or exp_res["timed_out"] or ctrl_res["exit_code"] != 0 or ctrl_res["timed_out"]:
        dest_path.unlink(missing_ok=True)
        raise AjarError(
            f"Helper dual-mode verification failed (exploit_exit={exp_res['exit_code']}, "
            f"benign_exit={ctrl_res['exit_code']}): {exp_res['stderr'][:180]} {ctrl_res['stderr'][:180]}",
            EXIT_GATE_BLOCKED,
            {"exploit_mode": exp_res, "benign_mode": ctrl_res},
        )

    # Lock read-only (`0444`) outside `slot-<k>`.
    os.chmod(dest_path, 0o444)
    sha256_hex = hashlib.sha256(src_text.encode("utf-8")).hexdigest()

    state_out_keys: list[str] = []
    for line in exp_res["stdout"].splitlines():
        if line.startswith("AJAR_HELPER_STATE:"):
            try:
                parsed = json.loads(line.split("AJAR_HELPER_STATE:", 1)[1])
                if isinstance(parsed, list):
                    state_out_keys = [str(k) for k in parsed]
            except json.JSONDecodeError:
                pass

    existing_prov = parse_tag_list(prim["provides_tags_json"] if "provides_tags_json" in prim.keys() else "[]")
    existing_req = parse_tag_list(prim["requires_tags_json"] if "requires_tags_json" in prim.keys() else "[]")
    merged_prov = sorted(set(existing_prov) | set(parse_tag_list(provides_tags)))
    merged_req = sorted(set(existing_req) | set(parse_tag_list(requires_tags)))

    now_iso = utc_now_iso()
    existing_row = conn.execute("SELECT helper_id FROM primitive_helpers WHERE module_name = ?", (mod_name,)).fetchone()
    hid = str(existing_row["helper_id"]) if existing_row else new_id("hlp")
    verification_receipt = {"exploit_mode": exp_res, "benign_mode": ctrl_res}

    conn.execute(
        """
        INSERT INTO primitive_helpers(
            helper_id, primitive_id, module_name, rel_helper_path, sha256,
            callable_name, language, requires_tags_json, provides_tags_json,
            state_in_keys_json, state_out_keys_json, self_test_cmd,
            verified, verification_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'python', ?, ?, '[]', ?, ?, 1, ?, ?)
        ON CONFLICT(module_name) DO UPDATE SET
            sha256 = excluded.sha256,
            callable_name = excluded.callable_name,
            requires_tags_json = excluded.requires_tags_json,
            provides_tags_json = excluded.provides_tags_json,
            state_out_keys_json = excluded.state_out_keys_json,
            self_test_cmd = excluded.self_test_cmd,
            verified = 1,
            verification_json = excluded.verification_json
        """,
        (
            hid,
            primitive_id,
            mod_name,
            rel_helper_path,
            sha256_hex,
            callable_name.strip(),
            json.dumps(merged_req),
            json.dumps(merged_prov),
            json.dumps(state_out_keys),
            scrub_text(eff_cmd),
            json.dumps(verification_receipt, sort_keys=True),
            now_iso,
        ),
    )
    conn.execute(
        """
        UPDATE primitives
        SET helper_id = ?, provides_tags_json = ?, requires_tags_json = ?
        WHERE primitive_id = ?
        """,
        (hid, json.dumps(merged_prov), json.dumps(merged_req), primitive_id),
    )
    hooks = on_primitive_added(
        conn,
        primitive_id=primitive_id,
        subsystem=str(prim["subsystem"] or ""),
        locus=str(prim["locus"] or ""),
        kind=str(prim["kind"] or ""),
        guarded_by_locus="",
        provides_tags=merged_prov,
        requires_tags=merged_req,
        spawn_guard_task=False,
    )
    log_event(
        conn,
        worker_id,
        "primitive_helper_promoted",
        hid,
        {
            "primitive_id": primitive_id,
            "module": f"ajar_helpers.{mod_name}",
            "callable": callable_name.strip(),
            "provides_tags": merged_prov,
        },
    )
    return {
        "helper_id": hid,
        "primitive_id": primitive_id,
        "import_path": f"ajar_helpers.{mod_name}",
        "callable": callable_name.strip(),
        "rel_helper_path": rel_helper_path,
        "sha256": sha256_hex,
        "state_out_keys": state_out_keys,
        "provides_tags": merged_prov,
        "requires_tags": merged_req,
        "hooks_triggered": [h["hook_code"] for h in hooks],
        "verified": True,
    }


def _parse_step_micropatches(specs: Sequence[str] | None) -> dict[str, pathlib.Path]:
    mapping: dict[str, pathlib.Path] = {}
    for raw in specs or ():
        step_id, sep, p_str = str(raw).partition(":")
        if not sep or not step_id.strip() or not p_str.strip():
            raise AjarError(
                f"Invalid --step-micropatch {raw!r}; expected `<step_id>:<path/to/step.diff>`.",
                EXIT_USER_ERROR,
            )
        p = pathlib.Path(p_str.strip()).expanduser().resolve()
        if not p.is_file():
            raise AjarError(f"Step micropatch file not found for {step_id!r}: {p}", EXIT_USER_ERROR)
        mapping[step_id.strip()] = p
    return mapping


def run_chain_reproduction(
    conn: sqlite3.Connection,
    *,
    run_dir: pathlib.Path,
    target_dir: pathlib.Path,
    title: str,
    steps: Sequence[str],
    poc_cmd: str,
    control_cmd: str,
    severity: str = "critical",
    oracle: dict[str, Any] | None = None,
    step_micropatches: Mapping[str, pathlib.Path] | None = None,
    ablate_steps: bool = True,
    door_id: str = "",
    jewel_id: str = "",
    declared_steps: int | None = None,
    timeout_sec: int = 60,
    worker_id: str = "worker",
) -> dict[str, Any]:
    """Execute end-to-end chain verification inside `repro/slot-<k>` with $N$-step causal ablation."""
    from ajar.chain_planner import (
        evaluate_precondition_realism,
        mark_chain_doors_and_jewels_resolved,
    )

    clean_steps = [s.strip() for s in steps if s and s.strip()]
    if not clean_steps:
        raise AjarError("Chain --steps requires at least one primitive, anomaly, claim, or finding ID.", EXIT_USER_ERROR)

    # Pre-flight realism check (blocks self-override CLI/env flags in `< 1 ms`).
    evaluate_precondition_realism(
        conn,
        poc_cmd=poc_cmd,
        control_cmd=control_cmd,
        severity=severity,
        step_ids=clean_steps,
        declared_steps=declared_steps,
        explicit_jewel_id=jewel_id,
    )

    prim_rows: dict[str, sqlite3.Row] = {}
    finding_rows: dict[str, sqlite3.Row] = {}
    step_roles: dict[str, str] = {}
    chain_touched_files: list[str] = []
    invariant_breaking_count = 0
    auto_patch_dir = run_dir / "repro" / "auto_step_patches"
    patch_map = dict(step_micropatches or {})

    for sid in clean_steps:
        prow = conn.execute("SELECT * FROM primitives WHERE primitive_id = ?", (sid,)).fetchone()
        if prow is not None:
            prim_rows[sid] = prow
            prole = str(prow["role"] if "role" in prow.keys() else "capability")
            step_roles[sid] = prole
            if prole != "trust_gadget":
                invariant_breaking_count += 1
            ploc = str(prow["locus"] or "").split(":", 1)[0].strip()
            if ploc and ploc not in chain_touched_files:
                chain_touched_files.append(ploc)
            if sid not in patch_map and "micropatch_diff" in prow.keys() and str(prow["micropatch_diff"] or "").strip():
                auto_patch_dir.mkdir(parents=True, exist_ok=True)
                ap_file = auto_patch_dir / f"{sid}.diff"
                ap_file.write_text(str(prow["micropatch_diff"]), encoding="utf-8")
                patch_map[sid] = ap_file
            continue

        frow = conn.execute("SELECT * FROM findings WHERE finding_id = ?", (sid,)).fetchone()
        if frow is None and sid.startswith("clm-"):
            frow = conn.execute("SELECT * FROM findings WHERE claim_id = ?", (sid,)).fetchone()
        if frow is not None:
            finding_rows[sid] = frow
            step_roles[sid] = "finding"
            invariant_breaking_count += 1
            floc = str(frow["locus"] or "").split(":", 1)[0].strip()
            if floc and floc not in chain_touched_files:
                chain_touched_files.append(floc)
            if sid not in patch_map:
                mp_path = pathlib.Path(str(frow["micropatch_path"] or ""))
                if mp_path.is_file():
                    patch_map[sid] = mp_path
                elif str(frow["micropatch_diff"] or "").strip():
                    auto_patch_dir.mkdir(parents=True, exist_ok=True)
                    ap_file = auto_patch_dir / f"{sid}.diff"
                    ap_file.write_text(str(frow["micropatch_diff"]), encoding="utf-8")
                    patch_map[sid] = ap_file
            continue

        crow = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (sid,)).fetchone()
        if crow is not None:
            step_roles[sid] = "claim"
            invariant_breaking_count += 1
            cloc = str(crow["locus"] or "").split(":", 1)[0].strip()
            if cloc and cloc not in chain_touched_files:
                chain_touched_files.append(cloc)
            continue

        arow = conn.execute("SELECT * FROM anomalies WHERE anomaly_id = ?", (sid,)).fetchone()
        if arow is not None:
            step_roles[sid] = "anomaly"
            invariant_breaking_count += 1
            aloc = str(arow["locus"] or "").split(":", 1)[0].strip()
            if aloc and aloc not in chain_touched_files:
                chain_touched_files.append(aloc)
            continue

        raise AjarError(
            f"Unknown chain step ID {sid!r}; pass verified `fnd-*`, `clm-*`, `prim-*`, or `anom-*` IDs.",
            EXIT_USER_ERROR,
        )

    if invariant_breaking_count == 0:
        raise AjarError(
            "Gadget-only chain rejected: `--steps` contains only `trust_gadget` normal-code transitions with zero "
            "invariant-breaking `capability`, `finding`, or `anomaly` steps.",
            EXIT_GATE_BLOCKED,
        )

    for pfile in patch_map.values():
        for ln in pfile.read_text(encoding="utf-8", errors="ignore").splitlines():
            if ln.startswith("+++ ") and ln[4:].strip() != "/dev/null":
                tf = re.sub(r"^b/", "", ln[4:].split("\t", 1)[0].strip())
                if tf and tf not in chain_touched_files:
                    chain_touched_files.append(tf)

    cheat_ok, cheat_msg = validate_no_static_source_cheat(
        poc_cmd,
        chain_touched_files,
        search_roots=(run_dir,),
        target_dir=target_dir,
    )
    if not cheat_ok:
        raise AjarError(cheat_msg, EXIT_GATE_BLOCKED)

    helpers_dir = ensure_helpers_runtime(run_dir)
    mirror_dir = init_source_mirror(run_dir, target_dir)
    repro_dir = run_dir / "repro"
    slot_idx, lock_fh = _acquire_slot(repro_dir)
    slot_dir = repro_dir / f"slot-{slot_idx}"
    cache_dir = resolve_local_build_cache_dir(run_dir, f"cache-{slot_idx}")
    watermark_file = cache_dir / "watermark_ns"

    ablation_matrix: list[dict[str, Any]] = []

    try:
        _prepare_slot_worktree(mirror_dir, slot_dir)

        # 1. Full Chain Arm (`exploit_path`, zero ablated steps) -> oracle MUST fire.
        full_res = _run_shell_in_slot(
            poc_cmd,
            slot_dir=slot_dir,
            cache_dir=cache_dir,
            timeout_sec=timeout_sec,
            helpers_dir=helpers_dir,
            extra_env={"AJAR_REPRO_MODE": "exploit_path", "AJAR_ABLATE_STEPS": ""},
        )
        full_fired = _evaluate_defect_fired(
            full_res["exit_code"], full_res["stdout"], full_res["stderr"], full_res["timed_out"], oracle
        )
        full_res["defect_fired"] = full_fired

        subprocess.run(["git", "-C", str(slot_dir), "reset", "--hard", "HEAD"], capture_output=True, check=True)
        _clean_slot_preserving_objects(slot_dir, check=True)

        # 2. Benign Control Arm (`benign_control`, zero ablated steps so control_cmd tests benign input directly) -> MUST pass cleanly.
        ctrl_res = _run_shell_in_slot(
            control_cmd,
            slot_dir=slot_dir,
            cache_dir=cache_dir,
            timeout_sec=timeout_sec,
            helpers_dir=helpers_dir,
            extra_env={"AJAR_REPRO_MODE": "benign_control", "AJAR_ABLATE_STEPS": ""},
        )
        ctrl_fired = _evaluate_defect_fired(
            ctrl_res["exit_code"], ctrl_res["stdout"], ctrl_res["stderr"], ctrl_res["timed_out"], oracle
        )
        ctrl_passed = (not ctrl_fired) and ctrl_res["exit_code"] == 0 and (not ctrl_res["timed_out"])
        ctrl_res["control_passed"] = ctrl_passed

        subprocess.run(["git", "-C", str(slot_dir), "reset", "--hard", "HEAD"], capture_output=True, check=True)
        _clean_slot_preserving_objects(slot_dir, check=True)

        ablation_passed = True
        ablation_failure_reason = ""

        # 3. Automated $N$-Step Marginal-Contribution Ablation:
        env_ablatable = (
            ("AJAR_ABLATE_STEPS" in poc_cmd)
            or ("StageContext" in poc_cmd)
            or ("ajar_helpers" in poc_cmd)
        )
        uses_composable_ablation = (
            bool(patch_map)
            or any(bool(r["helper_id"]) for r in prim_rows.values() if "helper_id" in r.keys())
            or env_ablatable
        )

        if full_fired and ctrl_passed and ablate_steps:
            non_gadget_steps = [s for s in clean_steps if step_roles.get(s) != "trust_gadget"]
            if len(clean_steps) >= 2 and not uses_composable_ablation:
                ablation_passed = False
                ablation_failure_reason = (
                    "Marginal-contribution gate: multi-step chains require step-ablatable capabilities "
                    "(`fnd-*` with verified micropatch, `prim-*` `--micropatch`, `--step-micropatch <id>:<diff>`, "
                    "or `AJAR_ABLATE_STEPS`) to prove causal necessity."
                )
            elif uses_composable_ablation:
                causally_ablated_count = 0
                for step_id in clean_steps:
                    has_helper = bool(step_id in prim_rows and "helper_id" in prim_rows[step_id].keys() and prim_rows[step_id]["helper_id"])
                    can_ablate_this_step = (step_id in patch_map) or has_helper or env_ablatable
                    if not can_ablate_this_step:
                        if step_roles.get(step_id) == "trust_gadget":
                            ablation_matrix.append(
                                {
                                    "step_id": step_id,
                                    "ablated_via": "trust_gadget_bridge",
                                    "defect_still_fired": False,
                                    "exit_code": 0,
                                    "causally_required": True,
                                }
                            )
                            continue
                        if len(non_gadget_steps) >= 2:
                            ablation_passed = False
                            ablation_failure_reason = (
                                f"Marginal-contribution gate: non-gadget step {step_id} lacks a micropatch or "
                                f"`AJAR_ABLATE_STEPS` hook (`--step-micropatch {step_id}:<diff>`)."
                            )
                            break
                        continue

                    touched_step_files: list[str] = []
                    if step_id in patch_map:
                        pfile = patch_map[step_id]
                        ap = subprocess.run(
                            ["git", "-C", str(slot_dir), "apply", "--whitespace=nowarn", str(pfile)],
                            capture_output=True,
                            text=True,
                            env=scrubbed_subprocess_env(),
                            check=False,
                        )
                        if ap.returncode != 0:
                            ablation_passed = False
                            ablation_failure_reason = (
                                f"Step micropatch for {step_id} failed `git apply`: {scrub_text(ap.stderr[:200])}"
                            )
                            ablation_matrix.append({"step_id": step_id, "causally_required": False, "apply_failed": True})
                            break
                        for ln in pfile.read_text(encoding="utf-8", errors="ignore").splitlines():
                            if ln.startswith("+++ ") and ln[4:].strip() != "/dev/null":
                                touched_step_files.append(re.sub(r"^b/", "", ln[4:].split("\t", 1)[0].strip()))
                        _neutralize_python_pth_escapes(slot_dir)
                        _bump_files_mtime(slot_dir, touched_step_files, watermark_file)

                    abl_res = _run_shell_in_slot(
                        poc_cmd,
                        slot_dir=slot_dir,
                        cache_dir=cache_dir,
                        timeout_sec=timeout_sec,
                        helpers_dir=helpers_dir,
                        extra_env={"AJAR_REPRO_MODE": "exploit_path", "AJAR_ABLATE_STEPS": step_id},
                    )
                    still_fired = _evaluate_defect_fired(
                        abl_res["exit_code"], abl_res["stdout"], abl_res["stderr"], abl_res["timed_out"], oracle
                    )
                    step_necessary = (not still_fired) and (not abl_res["timed_out"])
                    ablation_matrix.append(
                        {
                            "step_id": step_id,
                            "ablated_via": "step_micropatch" if step_id in patch_map else "stage_context_env",
                            "defect_still_fired": still_fired,
                            "exit_code": abl_res["exit_code"],
                            "causally_required": step_necessary,
                        }
                    )
                    subprocess.run(["git", "-C", str(slot_dir), "reset", "--hard", "HEAD"], capture_output=True, check=True)
                    _clean_slot_preserving_objects(slot_dir, check=True)
                    if touched_step_files:
                        _bump_files_mtime(slot_dir, touched_step_files, watermark_file)

                    if not step_necessary:
                        ablation_passed = False
                        ablation_failure_reason = (
                            f"Step ablation failed: chain still triggered defect when {step_id} was neutralized. "
                            f"Remove redundant padding step {step_id} from --steps."
                        )
                        break
                    causally_ablated_count += 1

                if ablation_passed and len(clean_steps) >= 2 and causally_ablated_count == 0:
                    ablation_passed = False
                    ablation_failure_reason = (
                        "Marginal-contribution gate: at least one upstream capability/finding step must be causally ablated."
                    )
    finally:
        if (slot_dir / ".git").exists():
            subprocess.run(["git", "-C", str(slot_dir), "reset", "--hard", "HEAD"], capture_output=True, check=False)
            _clean_slot_preserving_objects(slot_dir, check=False)
        fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)
        lock_fh.close()

    verified = bool(full_fired and ctrl_passed and ablation_passed)
    tail_locus = chain_touched_files[-1] if chain_touched_files else ""
    realism = evaluate_precondition_realism(
        conn,
        poc_cmd=poc_cmd,
        control_cmd=control_cmd,
        stdout=str(full_res.get("stdout", "")),
        stderr=str(full_res.get("stderr", "")),
        severity=severity,
        step_ids=clean_steps,
        declared_steps=declared_steps,
        target_locus=tail_locus,
        explicit_jewel_id=jewel_id,
    )

    if not full_fired:
        reason = f"Full chain PoC did not trigger defect oracle (exit={full_res['exit_code']})."
    elif not ctrl_passed:
        reason = f"Benign control failed or triggered defect oracle (exit={ctrl_res['exit_code']})."
    elif not ablation_passed:
        reason = ablation_failure_reason
    else:
        reason = (
            f"Verified end-to-end chain in slot-{slot_idx} "
            f"({len(ablation_matrix)} step(s) verified, realism_tier={realism['realism_tier']})."
        )

    cid = new_id("chn")
    now_iso = utc_now_iso()
    ev = {
        "slot_index": slot_idx,
        "reason": reason,
        "poc_exit": int(full_res["exit_code"]),
        "control_exit": int(ctrl_res["exit_code"]),
        "poc_stdout": full_res["stdout"][:1500],
        "poc_stderr": full_res["stderr"][:800],
        "ablation_matrix": ablation_matrix,
        "realism": realism,
    }
    conn.execute(
        """
        INSERT INTO chains(
            chain_id, title, severity, step_ids_json, e2e_poc_cmd, control_cmd,
            verified, evidence_json, slot_index, oracle_json, ablation_matrix_json,
            realism_tier, realism_json, jewel_id, door_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            cid,
            scrub_text(title),
            severity,
            json.dumps(clean_steps),
            scrub_text(poc_cmd),
            scrub_text(control_cmd),
            1 if verified else 0,
            json.dumps(ev, sort_keys=True),
            slot_idx,
            json.dumps(oracle or {}, sort_keys=True),
            json.dumps(ablation_matrix, sort_keys=True),
            str(realism["realism_tier"]),
            json.dumps(realism, sort_keys=True),
            str(realism["jewel_id"]),
            door_id.strip(),
            now_iso,
        ),
    )
    resolved_doors: list[str] = []
    if verified:
        from ajar.epistemic_hooks import consume_hooks_for_locus

        for sid in clean_steps:
            conn.execute(
                "UPDATE primitives SET chained = 1, status = 'chained' WHERE primitive_id = ?",
                (sid,),
            )
            if sid in prim_rows and prim_rows[sid]["guarded_by_locus"]:
                consume_hooks_for_locus(
                    conn,
                    locus=str(prim_rows[sid]["guarded_by_locus"]),
                    source_entity_id=sid,
                    hook_code="H1_GUARD_SYMMETRY",
                )
            conn.execute(
                "UPDATE anomalies SET status = 'consumed_by_chain', consumed_by_id = ?, updated_at = ? WHERE anomaly_id = ?",
                (cid, now_iso, sid),
            )
        resolved_doors = mark_chain_doors_and_jewels_resolved(
            conn,
            chain_id=cid,
            step_ids=clean_steps,
            door_id=door_id.strip(),
            jewel_id=str(realism["jewel_id"]),
            realism_tier=str(realism["realism_tier"]),
        )
    log_event(
        conn,
        worker_id,
        "chain_proposed",
        cid,
        {
            "verified": verified,
            "steps": clean_steps,
            "ablated_steps": len(ablation_matrix),
            "realism_tier": realism["realism_tier"],
            "resolved_doors": resolved_doors,
            "reason": reason[:200],
        },
    )
    return {
        "chain_id": cid,
        "verified": verified,
        "realism_tier": realism["realism_tier"],
        "jewel_id": realism["jewel_id"],
        "resolved_doors": resolved_doors,
        "reason": reason,
        "slot_index": slot_idx,
        "ablation_matrix": ablation_matrix,
        "evidence": ev,
    }


def run_snapshot_chain_probe(
    conn: sqlite3.Connection,
    *,
    run_dir: pathlib.Path,
    target_dir: pathlib.Path,
    snapshot_id: str,
    cmd: str,
    patch_path: pathlib.Path | None = None,
    oracle: dict[str, Any] | None = None,
    timeout_sec: int = 60,
    worker_id: str = "worker",
) -> dict[str, Any]:
    """Hydrate a verified Stage-1 post-state `.tar.gz` snapshot into `slot-inst` in `< 50 ms` and execute Stage 2."""
    import tarfile

    srow = conn.execute("SELECT * FROM repro_snapshots WHERE snapshot_id = ?", (snapshot_id,)).fetchone()
    if srow is None:
        raise AjarError(f"Unknown snapshot_id: {snapshot_id}", EXIT_USER_ERROR)
    if not cmd.strip():
        raise AjarError("`ajar chain probe` requires a non-empty --cmd.", EXIT_USER_ERROR)

    raw_arch = pathlib.Path(str(srow["archive_path"]))
    arch_path = raw_arch if raw_arch.is_absolute() else (run_dir / raw_arch)
    if not arch_path.is_file():
        fallback_arch = run_dir / "repro" / "snapshots" / raw_arch.name
        if fallback_arch.is_file():
            arch_path = fallback_arch
        else:
            raise AjarError(f"Snapshot archive missing on disk: {arch_path}", EXIT_USER_ERROR)
    actual_sha = hashlib.sha256(arch_path.read_bytes()).hexdigest()
    if actual_sha != str(srow["sha256"]):
        raise AjarError(f"Snapshot SHA-256 integrity mismatch for {snapshot_id}.", EXIT_GATE_BLOCKED)

    helpers_dir = ensure_helpers_runtime(run_dir)
    mirror_dir = init_source_mirror(run_dir, target_dir)
    repro_dir = run_dir / "repro"
    repro_dir.mkdir(parents=True, exist_ok=True)
    lock_fh = open(repro_dir / "slot-inst.lock", "a+", encoding="utf-8")
    fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
    slot_dir = repro_dir / "slot-inst"
    cache_dir = resolve_local_build_cache_dir(run_dir, "cache-inst")
    watermark_file = cache_dir / "watermark_ns"
    touched: list[str] = []

    try:
        _prepare_slot_worktree(mirror_dir, slot_dir)

        # Safe tar extraction into `slot-inst` preserving validated intra-slot relative symlinks.
        with tarfile.open(arch_path, "r:gz") as tar:
            safe_members: list[tarfile.TarInfo] = []
            for member in tar.getmembers():
                m_path = pathlib.PurePosixPath(member.name)
                if m_path.is_absolute() or ".." in m_path.parts:
                    raise AjarError(f"Unsafe tar member path in snapshot {snapshot_id}: {member.name!r}", EXIT_GATE_BLOCKED)
                if member.ischr() or member.isblk() or member.isfifo():
                    continue
                if member.issym() or member.islnk():
                    lnk = member.linkname
                    if os.path.isabs(lnk):
                        continue
                    joined = os.path.normpath(os.path.join(os.path.dirname(member.name), lnk))
                    if joined == ".." or joined.startswith("../"):
                        continue
                safe_members.append(member)
            use_filter = hasattr(tarfile, "data_filter")
            for member in safe_members:
                dest = slot_dir / member.name
                if dest.exists() or dest.is_symlink():
                    if dest.is_symlink() or dest.is_file():
                        dest.unlink(missing_ok=True)
                if use_filter:
                    tar.extract(member, path=str(slot_dir), set_attrs=False, filter="data")
                else:
                    tar.extract(member, path=str(slot_dir), set_attrs=False)

        if patch_path is not None:
            if not patch_path.is_file():
                raise AjarError(f"Patch file not found: {patch_path}", EXIT_USER_ERROR)
            ap = subprocess.run(
                ["git", "-C", str(slot_dir), "apply", "--whitespace=nowarn", str(patch_path.resolve())],
                capture_output=True,
                text=True,
                env=scrubbed_subprocess_env(),
                check=False,
            )
            if ap.returncode != 0:
                raise AjarError(f"Probe patch failed `git apply`: {scrub_text(ap.stderr[:240])}", EXIT_USER_ERROR)
            for ln in patch_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if ln.startswith("+++ ") and ln[4:].strip() != "/dev/null":
                    touched.append(re.sub(r"^b/", "", ln[4:].split("\t", 1)[0].strip()))
            _bump_files_mtime(slot_dir, touched, watermark_file)

        res = _run_shell_in_slot(
            cmd,
            slot_dir=slot_dir,
            cache_dir=cache_dir,
            timeout_sec=timeout_sec,
            helpers_dir=helpers_dir,
            extra_env={"AJAR_SNAPSHOT_ID": snapshot_id},
        )
        fired = _evaluate_defect_fired(res["exit_code"], res["stdout"], res["stderr"], res["timed_out"], oracle)
    finally:
        if (slot_dir / ".git").exists():
            subprocess.run(["git", "-C", str(slot_dir), "reset", "--hard", "HEAD"], capture_output=True, check=False)
            _clean_slot_preserving_objects(slot_dir, check=False)
            if touched:
                _bump_files_mtime(slot_dir, touched, watermark_file)
        fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)
        lock_fh.close()

    log_event(
        conn,
        worker_id,
        "chain_snapshot_probed",
        snapshot_id,
        {"exit_code": res["exit_code"], "defect_fired": fired},
    )
    return {
        "snapshot_id": snapshot_id,
        "rel_dir": str(srow["rel_dir"]),
        "defect_fired": fired,
        "probe": res,
    }


def run_claim_instrumentation(
    conn: sqlite3.Connection,
    *,
    run_dir: pathlib.Path,
    target_dir: pathlib.Path,
    claim_id: str,
    probe_cmd: str,
    probe_patch: pathlib.Path | None = None,
    record_anomaly: bool = True,
    timeout_sec: int = 60,
    worker_id: str = "worker",
) -> dict[str, Any]:
    """Run an ephemeral diagnostic trace inside scratch `slot-inst` to unblock `needs_instrumentation`."""
    clm = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (claim_id,)).fetchone()
    if clm is None:
        raise AjarError(f"Unknown claim_id: {claim_id}", EXIT_USER_ERROR)
    if not probe_cmd.strip():
        raise AjarError("Instrumentation requires a non-empty --probe-cmd.", EXIT_USER_ERROR)

    helpers_dir = ensure_helpers_runtime(run_dir)
    mirror_dir = init_source_mirror(run_dir, target_dir)
    repro_dir = run_dir / "repro"
    repro_dir.mkdir(parents=True, exist_ok=True)
    lock_fh = open(repro_dir / "slot-inst.lock", "a+", encoding="utf-8")
    fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
    slot_dir = repro_dir / "slot-inst"
    cache_dir = resolve_local_build_cache_dir(run_dir, "cache-inst")
    watermark_file = cache_dir / "watermark_ns"
    touched: list[str] = []

    try:
        _prepare_slot_worktree(mirror_dir, slot_dir)
        if probe_patch is not None:
            if not probe_patch.is_file():
                raise AjarError(f"Probe patch file not found: {probe_patch}", EXIT_USER_ERROR)
            ap = subprocess.run(
                ["git", "-C", str(slot_dir), "apply", "--whitespace=nowarn", str(probe_patch.resolve())],
                capture_output=True,
                text=True,
                env=scrubbed_subprocess_env(),
                check=False,
            )
            if ap.returncode != 0:
                raise AjarError(f"Probe patch failed `git apply`: {scrub_text(ap.stderr[:240])}", EXIT_USER_ERROR)
            for ln in probe_patch.read_text(encoding="utf-8", errors="ignore").splitlines():
                if ln.startswith("+++ ") and ln[4:].strip() != "/dev/null":
                    touched.append(re.sub(r"^b/", "", ln[4:].split("\t", 1)[0].strip()))
            _neutralize_python_pth_escapes(slot_dir)
            _bump_files_mtime(slot_dir, touched, watermark_file)

        res = _run_shell_in_slot(
            probe_cmd,
            slot_dir=slot_dir,
            cache_dir=cache_dir,
            timeout_sec=timeout_sec,
            helpers_dir=helpers_dir,
        )
    finally:
        if (slot_dir / ".git").exists():
            subprocess.run(["git", "-C", str(slot_dir), "reset", "--hard", "HEAD"], capture_output=True, check=False)
            _clean_slot_preserving_objects(slot_dir, check=False)
            if touched:
                _bump_files_mtime(slot_dir, touched, watermark_file)
        fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)
        lock_fh.close()

    now_iso = utc_now_iso()
    trace_excerpt = scrub_text((res["stdout"] + "\n" + res["stderr"]).strip()[:600])
    anomaly_id: str | None = None
    if record_anomaly and trace_excerpt:
        anomaly_id = new_id("anom")
        conn.execute(
            """
            INSERT INTO anomalies(
                anomaly_id, surface_id, source_claim_id, subsystem, locus,
                observation, repro_cmd, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'consumed_by_claim', ?, ?)
            """,
            (
                anomaly_id,
                clm["surface_id"],
                claim_id,
                clm["subsystem"],
                clm["locus"],
                f"[instrument trace exit={res['exit_code']}] {trace_excerpt[:300]}",
                scrub_text(probe_cmd),
                now_iso,
                now_iso,
            ),
        )
        conn.execute("UPDATE anomalies SET consumed_by_id = ? WHERE anomaly_id = ?", (claim_id, anomaly_id))

    conn.execute(
        """
        UPDATE claims
        SET instrumented_since_fail = 1,
            status = CASE WHEN status = 'needs_instrumentation' THEN 'survived_falsify' ELSE status END,
            updated_at = ?
        WHERE claim_id = ?
        """,
        (now_iso, claim_id),
    )
    conn.execute(
        """
        UPDATE tasks
        SET status = 'done', worker_id = ?, summary = ?, updated_at = ?
        WHERE kind = 'instrument' AND status IN ('open', 'leased')
          AND (parent_claim_id = ? OR locus = ?)
        """,
        (worker_id, f"Completed slot-inst probe for {claim_id}", now_iso, claim_id, clm["locus"]),
    )
    log_event(
        conn,
        worker_id,
        "claim_instrumented",
        claim_id,
        {"exit_code": res["exit_code"], "anomaly_id": anomaly_id},
    )
    updated_status = str(
        conn.execute("SELECT status FROM claims WHERE claim_id = ?", (claim_id,)).fetchone()["status"]
    )
    return {
        "claim_id": claim_id,
        "status": updated_status,
        "instrumented_since_fail": 1,
        "anomaly_id": anomaly_id,
        "probe": res,
    }
