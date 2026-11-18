"""Dual-Mode workspace initializer (`--envelope` default and `--in-place` optional).

- `--envelope`: Creates `~/.ajar/runs/<run_id>/workspace/` with a read-only `target/`
  snapshot (`chmod -R a-w`), strips untrusted agent hook configs inside `target/`,
  initializes the `repro/repo.git` bare mirror, and pre-wires Host Mode `.mcp.json`
  and `.claude/settings.json`.
- `--in-place`: Writes ZERO files into the target repository; stores all run state
  and reproduction mirrors under `~/.ajar/runs/<run_id>/`.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import stat
from typing import Any

from ajar import EXIT_USER_ERROR
from ajar.db import (
    AjarError,
    compute_commitment_hash,
    get_ajar_home,
    log_event,
    new_id,
    open_run_db,
    run_dir_for,
    utc_now_iso,
)
from ajar.oracles import index_target_oracles
from ajar.redact import scrub_text
from ajar.repomap import build_repomap, compute_cogs_cap_usd, count_in_scope_loc
from ajar.repro_source import init_source_mirror

UNTRUSTED_TARGET_AGENT_CONFIGS: frozenset[str] = frozenset(
    {".claude", ".mcp.json", ".cursor", ".codex"}
)


def _compute_target_digest(target_path: pathlib.Path, target_mode: str, target_url: str = "") -> str:
    h = hashlib.sha256()
    if target_mode == "live":
        h.update(f"live:{target_url}".encode("utf-8"))
        return h.hexdigest()
    if target_path.is_file():
        with open(target_path, "rb") as fh:
            while chunk := fh.read(65536):
                h.update(chunk)
        return h.hexdigest()

    for root, dirs, files in os.walk(target_path, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in {".git", "node_modules", "target", "__pycache__", ".venv"})
        for fname in sorted(files):
            fpath = pathlib.Path(root) / fname
            if fpath.is_symlink():
                continue
            rel = str(fpath.relative_to(target_path))
            h.update(rel.encode("utf-8") + b"\x00")
            try:
                with open(fpath, "rb") as fh:
                    while chunk := fh.read(65536):
                        h.update(chunk)
            except OSError:
                continue
    return h.hexdigest()


def _lock_tree_readonly(tree: pathlib.Path) -> None:
    """Apply `chmod a-w` across files and directories (bottom-up so dirs lock last)."""
    for root, dirs, files in os.walk(tree, topdown=False, followlinks=False):
        for fname in files:
            p = pathlib.Path(root) / fname
            if not p.is_symlink():
                st = os.stat(p)
                os.chmod(p, st.st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
        for dname in dirs:
            dp = pathlib.Path(root) / dname
            if not dp.is_symlink():
                st = os.stat(dp)
                os.chmod(dp, st.st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    st_root = os.stat(tree)
    os.chmod(tree, st_root.st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def unlock_run_dir_permissions(run_dir: pathlib.Path) -> None:
    """Restore owner write bits under `run_dir` so temporary test runs can clean up."""
    if not run_dir.exists():
        return
    for root, dirs, files in os.walk(run_dir, topdown=True, followlinks=False):
        os.chmod(root, 0o755)
        for dname in dirs:
            dp = pathlib.Path(root) / dname
            if not dp.is_symlink():
                os.chmod(dp, 0o755)
        for fname in files:
            fp = pathlib.Path(root) / fname
            if not fp.is_symlink():
                os.chmod(fp, 0o644)


def _snapshot_envelope_target(src_target: pathlib.Path, dst_target: pathlib.Path) -> None:
    if src_target.is_file():
        dst_target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_target, dst_target / src_target.name)
        return

    def _ignore(cur_dir: str, names: list[str]) -> set[str]:
        ignored = {".git", "__pycache__", ".pytest_cache", "node_modules", ".venv", ".ajar"}
        if pathlib.Path(cur_dir).resolve() == src_target.resolve():
            ignored |= set(UNTRUSTED_TARGET_AGENT_CONFIGS)
        return ignored & set(names)

    shutil.copytree(src_target, dst_target, symlinks=False, ignore=_ignore)


def _write_envelope_host_configs(workspace_dir: pathlib.Path, run_id: str, ajar_bin: str) -> None:
    (workspace_dir / ".ajar-run-id").write_text(f"{run_id}\n", encoding="utf-8")

    mcp_cfg = {
        "mcpServers": {
            "ajar": {
                "command": ajar_bin,
                "args": ["mcp", "--run", run_id],
            }
        }
    }
    (workspace_dir / ".mcp.json").write_text(json.dumps(mcp_cfg, indent=2) + "\n", encoding="utf-8")

    claude_dir = workspace_dir / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    import shlex

    hook_bin_prefix = ajar_bin if ajar_bin == "python3 -m ajar" else shlex.quote(ajar_bin)
    claude_cfg = {
        "hooks": {
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"{hook_bin_prefix} hook claude-stop --run {shlex.quote(run_id)}",
                        }
                    ]
                }
            ]
        }
    }
    (claude_dir / "settings.json").write_text(json.dumps(claude_cfg, indent=2) + "\n", encoding="utf-8")

    agents_text = (
        f"# Ajar Run Workspace (`{run_id}`)\n\n"
        "- Target snapshot (`./target/`) is read-only. Never modify `./target/` directly.\n"
        "- Run `ajar status` and `ajar task lease --worker <id>` to inspect and lease work.\n"
        "- Record unexplained observations with `ajar anomaly add`.\n"
        "- Propose hypotheses with `ajar claim propose` (including `--falsification-prediction` and `--falsification-test`).\n"
        "- Prove findings with `ajar claim reproduce` (4-arm causal check) before `ajar finish`.\n"
    )
    (workspace_dir / "AGENTS.md").write_text(agents_text, encoding="utf-8")


def init_run_workspace(
    *,
    target: str,
    target_mode: str = "source",
    workspace_mode: str = "envelope",
    goal: str = "Identify, falsify, and reproduce high-severity software vulnerabilities.",
    stopping_criterion: str = "exhaustive-high",
    budget_usd: float | None = None,
    allowed_hosts: list[str] | None = None,
    allow_live_requests: bool = False,
    allow_live_mutations: bool = False,
    diff_range: str | None = None,
    parent_run_id: str | None = None,
    run_id: str | None = None,
    ajar_home: pathlib.Path | str | None = None,
) -> dict[str, Any]:
    """Initialize a new Ajar run in `--envelope` (default) or `--in-place` mode."""
    from ajar.repomap import count_diff_loc
    from ajar.repro_compose import ensure_helpers_runtime

    if target_mode not in ("source", "binary", "live"):
        raise AjarError(f"Unsupported --mode {target_mode!r}.", EXIT_USER_ERROR)
    if workspace_mode not in ("envelope", "in_place"):
        raise AjarError(f"Unsupported workspace mode {workspace_mode!r}.", EXIT_USER_ERROR)

    home = get_ajar_home(ajar_home)
    rid = run_id or new_id("run")
    rdir = run_dir_for(rid, home)
    if (rdir / "run.db").exists():
        raise AjarError(f"Run {rid} already exists at {rdir}", EXIT_USER_ERROR)

    src_git_dir: pathlib.Path | None = None
    if target_mode == "live":
        target_url = target.strip()
        target_path_str = target_url
        effective_target_dir = rdir / "workspace"
        effective_target_dir.mkdir(parents=True, exist_ok=True)
        workspace_dir = effective_target_dir
        loc_info = {"total_loc": 0, "files_counted": 0, "code_quote_usd": 10.0}
        target_sha = _compute_target_digest(effective_target_dir, "live", target_url)
    else:
        src_path = pathlib.Path(target).expanduser().resolve()
        if not src_path.exists():
            raise AjarError(f"Target path does not exist: {src_path}", EXIT_USER_ERROR)
        if target_mode == "binary" and not src_path.is_file():
            raise AjarError(f"--mode binary requires an executable file, got: {src_path}", EXIT_USER_ERROR)
        src_git_dir = src_path if src_path.is_dir() else src_path.parent

        if workspace_mode == "envelope":
            workspace_dir = rdir / "workspace"
            workspace_dir.mkdir(parents=True, exist_ok=True)
            if target_mode == "binary":
                env_target = workspace_dir / "target"
                env_target.mkdir(parents=True, exist_ok=True)
                dst_bin = env_target / src_path.name
                shutil.copy2(src_path, dst_bin)
                os.chmod(dst_bin, 0o555)
                effective_target_dir = dst_bin
            else:
                env_target = workspace_dir / "target"
                _snapshot_envelope_target(src_path, env_target)
                init_source_mirror(rdir, env_target)
                ensure_helpers_runtime(rdir)
                _lock_tree_readonly(env_target)
                effective_target_dir = env_target

            repo_bin = pathlib.Path(__file__).resolve().parents[1] / "bin" / "ajar"
            ajar_cmd = str(repo_bin) if repo_bin.is_file() else "python3 -m ajar"
            _write_envelope_host_configs(workspace_dir, rid, ajar_cmd)
        else:
            # `--in-place`: write ZERO files into `src_path`!
            workspace_dir = src_path if src_path.is_dir() else src_path.parent
            effective_target_dir = src_path
            if target_mode == "source":
                init_source_mirror(rdir, src_path)
                ensure_helpers_runtime(rdir)

        target_path_str = str(effective_target_dir)
        if target_mode == "source" and diff_range and diff_range.strip():
            try:
                loc_info = count_diff_loc(src_git_dir, diff_range.strip())
            except ValueError as exc:
                raise AjarError(str(exc), EXIT_USER_ERROR) from exc
        elif target_mode == "source":
            loc_info = count_in_scope_loc(effective_target_dir)
        else:
            loc_info = {
                "total_loc": 0,
                "files_counted": 1,
                "code_quote_usd": 10.0,
            }
        target_sha = _compute_target_digest(effective_target_dir, target_mode)

    quote_usd = float(loc_info["code_quote_usd"])
    if budget_usd is None:
        eff_cogs_cap = compute_cogs_cap_usd(quote_usd)
        pricing_mode = "commercial_code"
    else:
        eff_cogs_cap = round(float(budget_usd), 4)
        pricing_mode = "custom_or_bounty"

    (rdir / "artifacts").mkdir(parents=True, exist_ok=True)
    created_at = utc_now_iso()
    clean_goal = scrub_text(goal)
    commit_hash = compute_commitment_hash(target_sha, clean_goal, stopping_criterion, created_at)

    diff_sync_summary: dict[str, Any] | None = None
    conn = open_run_db(rid, create=True, ajar_home=home)
    try:
        conn.execute(
            """
            INSERT INTO runs(
                run_id, target_path, workspace_path, target_mode, workspace_mode,
                goal, stopping_criterion, budget_usd, in_scope_loc, code_quote_usd,
                cogs_cap_usd, pricing_mode, commitment_hash, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
            """,
            (
                rid,
                target_path_str,
                str(workspace_dir),
                target_mode,
                workspace_mode,
                clean_goal,
                stopping_criterion,
                eff_cogs_cap,
                int(loc_info["total_loc"]),
                quote_usd,
                eff_cogs_cap,
                pricing_mode,
                commit_hash,
                created_at,
            ),
        )
        hosts = [h.strip().lower() for h in (allowed_hosts or []) if h.strip()]
        conn.execute(
            """
            INSERT INTO scope_rules(
                run_id, allowed_hosts_json, allow_live_requests, allow_live_mutations, signed_by, raw_scope_json
            ) VALUES (?, ?, ?, ?, 'operator', ?)
            """,
            (
                rid,
                json.dumps(hosts),
                1 if allow_live_requests else 0,
                1 if allow_live_mutations else 0,
                json.dumps(
                    {
                        "target": target_path_str,
                        "target_mode": target_mode,
                        "allowed_hosts": hosts,
                        "allow_live_requests": bool(allow_live_requests),
                        "allow_live_mutations": bool(allow_live_mutations),
                        "diff_range": (diff_range or "").strip(),
                    },
                    sort_keys=True,
                ),
            ),
        )

        oracle_counts = {"intent": 0, "reachability": 0, "precedent": 0}
        map_summary = {"files_indexed": 0, "symbols_indexed": 0}
        if target_mode == "source" and pathlib.Path(target_path_str).exists():
            tpath = pathlib.Path(target_path_str)
            map_res = build_repomap(conn, tpath, budget_tokens=1500)
            map_summary = {
                "files_indexed": map_res["files_indexed"],
                "symbols_indexed": map_res["symbols_indexed"],
                "slice_count": map_res["slice_count"],
            }
            oracle_counts = index_target_oracles(conn, tpath)
            if diff_range and diff_range.strip() and src_git_dir is not None:
                from ajar.diff_sync import sync_pr_differential_state

                diff_sync_summary = sync_pr_differential_state(
                    conn,
                    run_dir=rdir,
                    target_dir=tpath,
                    git_repo_dir=src_git_dir,
                    diff_range=diff_range.strip(),
                    parent_run_id=parent_run_id,
                    ajar_home=home,
                )
        else:
            oracle_counts = index_target_oracles(conn, rdir / "artifacts")

        log_event(
            conn,
            "operator",
            "run_initialized",
            rid,
            {
                "target_mode": target_mode,
                "workspace_mode": workspace_mode,
                "in_scope_loc": loc_info["total_loc"],
                "code_quote_usd": quote_usd,
                "cogs_cap_usd": eff_cogs_cap,
                "pricing_mode": pricing_mode,
                "diff_range": (diff_range or "").strip(),
                "parent_run_id": (parent_run_id or "").strip(),
                "commitment_hash": commit_hash,
            },
        )
    finally:
        conn.close()

    home.mkdir(parents=True, exist_ok=True)
    (home / "current_run").write_text(f"{rid}\n", encoding="utf-8")

    result: dict[str, Any] = {
        "run_id": rid,
        "run_dir": str(rdir),
        "workspace_path": str(workspace_dir),
        "target_path": target_path_str,
        "target_mode": target_mode,
        "workspace_mode": workspace_mode,
        "in_scope_loc": int(loc_info["total_loc"]),
        "code_quote_usd": quote_usd,
        "cogs_cap_usd": eff_cogs_cap,
        "pricing_mode": pricing_mode,
        "budget_usd": eff_cogs_cap,
        "commitment_hash": commit_hash,
        "repomap": map_summary,
        "indexed_docs": oracle_counts,
    }
    if diff_sync_summary is not None:
        result["diff_sync"] = diff_sync_summary
    return result
