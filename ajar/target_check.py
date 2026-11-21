"""Exogenous target liveness, freshness, scope-hygiene, and peer-checkout checks (`Ajar v3.2.3`).

Prevents Closed-World / Open-World validity mismatches before compute is spent:
- Offline `inspect_local_target_freshness` blocks archived or stale (`> max_age_days`) git checkouts on `ajar init`.
- `evaluate_target_readiness` (`ajar doctor --target ...`) verifies canonical upstream liveness (`gh api` / `git ls-remote`),
  branch/mirror parity, subdirectory `Code` LoC & `35%` COGS cap, embedded agent-config hazards (`CLAUDE.md` / `AGENTS.md`),
  Rust `#![no_std]` crates, sibling `--peer` checkouts, disclosure channels (`SECURITY.md` / GitHub PVR), and disk headroom.
"""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any, Sequence

from ajar.redact import scrubbed_subprocess_env
from ajar.repomap import compute_cogs_cap_usd, count_in_scope_loc

HARNESS_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

ARCHIVAL_COMMIT_SUBJECT_RE = re.compile(
    r"(?:\b(?:chore|docs|meta)\s*(?:\([^)]*\))?\s*:\s*archiv(?:e|ed|ing|al)\b"
    r"|\barchiv(?:al|ing)\s+(?:announcement|notice)\b"
    r"|\brepo(?:sitory)?\s+(?:is\s+|has\s+been\s+)?(?:archived|deprecated)\b"
    r"|\bmoved\s+to\s+(?:monorepo|https?://|[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+))",
    re.IGNORECASE,
)

ARCHIVAL_README_BANNER_RE = re.compile(
    r"(?:\bthis\s+(?:repository|repo|project)\s+(?:is|has\s+been)\s+(?:archived|deprecated|unmaintained|moved)\b"
    r"|\bno\s+longer\s+(?:actively\s+)?maintained\b[^\n]{0,80}\bmoved\s+to\b"
    r"|^>\s*\*\*?(?:archived|deprecated)\b"
    r"|\barchived\s+and\s+moved\s+to\b)",
    re.IGNORECASE | re.MULTILINE,
)

GITHUB_SLUG_RE = re.compile(r"^([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)$")
GITHUB_REMOTE_URL_RE = re.compile(
    r"(?:https?://github\.com/|git@github\.com:)([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?$"
)
REMOTE_GIT_URL_RE = re.compile(r"^(?:https?|ssh|git)://\S+|^git@\S+:\S+")

AGENT_CONFIG_NAMES: tuple[str, ...] = (
    "CLAUDE.md",
    "AGENTS.md",
    ".claude",
    ".mcp.json",
    ".cursor",
    ".codex",
)


def compute_disk_free_gib() -> dict[str, float]:
    """Return available disk headroom in GiB for `/tmp` (build cache) and `HOME`."""
    out: dict[str, float] = {}
    for label, path in (("tmp_free_gib", pathlib.Path(tempfile.gettempdir())), ("home_free_gib", pathlib.Path.home())):
        try:
            usage = shutil.disk_usage(path)
            out[label] = round(usage.free / float(1024**3), 2)
        except OSError:
            out[label] = -1.0
    return out


def _parse_iso_age_days(iso_str: str) -> float | None:
    if not iso_str:
        return None
    try:
        cleaned = iso_str.strip().replace("Z", "+00:00")
        dt = datetime.datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        now = datetime.datetime.now(datetime.timezone.utc)
        return round(max(0.0, (now - dt).total_seconds() / 86400.0), 1)
    except ValueError:
        return None


def _scan_readme_archival_banner(directory: pathlib.Path) -> str:
    for name in ("README.md", "README.rst", "README.txt", "README"):
        cand = directory / name
        if cand.is_file():
            try:
                head_lines = "\n".join(cand.read_text(encoding="utf-8", errors="ignore").splitlines()[:35])
            except OSError:
                continue
            m = ARCHIVAL_README_BANNER_RE.search(head_lines)
            if m:
                return f"{cand.name}: {m.group(0).strip()}"
    return ""


def _find_security_md(target_dir: pathlib.Path, git_root: pathlib.Path | None = None) -> str:
    roots = [target_dir]
    if git_root is not None and git_root != target_dir:
        roots.append(git_root)
    for r in roots:
        for rel in ("SECURITY.md", ".github/SECURITY.md", "docs/SECURITY.md"):
            p = r / rel
            if p.is_file():
                return str(p)
    return ""


def _scan_embedded_agent_configs(target_dir: pathlib.Path, git_root: pathlib.Path | None = None) -> list[str]:
    found: list[str] = []
    roots = [target_dir]
    if git_root is not None and git_root != target_dir:
        roots.append(git_root)
    seen: set[pathlib.Path] = set()
    for r in roots:
        for name in AGENT_CONFIG_NAMES:
            p = r / name
            if p.exists() and p not in seen:
                seen.add(p)
                found.append(str(p))
    return found


def _count_rust_no_std_crates(target_dir: pathlib.Path) -> int:
    if not (target_dir / "Cargo.toml").is_file() and not any(target_dir.glob("*/Cargo.toml")):
        return 0
    count = 0
    for lib_rs in target_dir.rglob("lib.rs"):
        if any(part in {"target", ".git", "node_modules"} for part in lib_rs.parts):
            continue
        try:
            head = lib_rs.read_text(encoding="utf-8", errors="ignore")[:1024]
        except OSError:
            continue
        if "#![no_std]" in head or "#![cfg_attr(not(feature = \"std\"), no_std)]" in head or "no_std" in head[:512]:
            count += 1
    return count


def inspect_local_target_freshness(
    target_path: pathlib.Path,
    *,
    max_age_days: int = 90,
) -> dict[str, Any]:
    """Offline check for archived banners or stale git `HEAD` on a local source directory."""
    src_dir = target_path if target_path.is_dir() else target_path.parent
    env = scrubbed_subprocess_env()
    blockers: list[str] = []
    warnings: list[str] = []

    readme_hit = _scan_readme_archival_banner(src_dir)
    if readme_hit:
        blockers.append(f"target_archived_readme_banner: {readme_hit}")

    top_proc = subprocess.run(
        ["git", "-C", str(src_dir), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if top_proc.returncode != 0 or not top_proc.stdout.strip():
        return {
            "is_git_repo": False,
            "passed": len(blockers) == 0,
            "blockers": blockers,
            "warnings": warnings,
        }

    git_root = pathlib.Path(top_proc.stdout.strip()).resolve()
    # Ignore ambient parent git repo if someone created a scratch folder inside /tmp or HOME root.
    if git_root in (pathlib.Path("/tmp").resolve(), pathlib.Path.home().resolve()):
        return {
            "is_git_repo": False,
            "passed": len(blockers) == 0,
            "blockers": blockers,
            "warnings": warnings,
        }

    if git_root != src_dir:
        root_readme_hit = _scan_readme_archival_banner(git_root)
        if root_readme_hit and not readme_hit:
            blockers.append(f"target_archived_readme_banner: {root_readme_hit}")

    log_proc = subprocess.run(
        ["git", "-C", str(git_root), "log", "-1", "--format=%ct%n%H%n%cI%n%s"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if log_proc.returncode != 0 or not log_proc.stdout.strip():
        return {
            "is_git_repo": True,
            "git_root": str(git_root),
            "passed": len(blockers) == 0,
            "blockers": blockers,
            "warnings": warnings,
        }

    lines = log_proc.stdout.splitlines()
    epoch = int(lines[0].strip()) if lines and lines[0].strip().isdigit() else int(time.time())
    head_sha = lines[1].strip() if len(lines) > 1 else ""
    head_iso = lines[2].strip() if len(lines) > 2 else ""
    head_subject = lines[3].strip() if len(lines) > 3 else ""
    age_days = round(max(0.0, (time.time() - float(epoch)) / 86400.0), 1)

    br_proc = subprocess.run(
        ["git", "-C", str(git_root), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    branch = br_proc.stdout.strip() if br_proc.returncode == 0 else ""

    rem_proc = subprocess.run(
        ["git", "-C", str(git_root), "config", "--get", "remote.origin.url"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    origin_url = rem_proc.stdout.strip() if rem_proc.returncode == 0 else ""

    if ARCHIVAL_COMMIT_SUBJECT_RE.search(head_subject):
        blockers.append(f"target_archived_commit_notice: HEAD {head_sha[:12]} subject indicates archival/migration ({head_subject!r}).")

    inside_internal_benchmarks = git_root == HARNESS_REPO_ROOT
    if not inside_internal_benchmarks and max_age_days > 0:
        if age_days > float(max_age_days):
            blockers.append(
                f"target_stale_git_head: HEAD {head_sha[:12]} ({head_iso}) is {age_days} days old (> {max_age_days}d limit). "
                "Verify canonical active upstream/monorepo before auditing, or pass --allow-historical-target."
            )
        elif age_days > 30.0:
            warnings.append(
                f"HEAD {head_sha[:12]} is {age_days} days old; confirm `{branch}` is the active production/release branch."
            )

    return {
        "is_git_repo": True,
        "git_root": str(git_root),
        "branch": branch,
        "head_sha": head_sha,
        "head_date": head_iso,
        "head_age_days": age_days,
        "head_subject": head_subject,
        "origin_url": origin_url,
        "passed": len(blockers) == 0,
        "blockers": blockers,
        "warnings": warnings,
    }


def _probe_github_repo(slug: str, *, ref: str = "", max_age_days: int = 90) -> dict[str, Any]:
    if not shutil.which("gh"):
        return {"checked": False, "reason": "gh_cli_unavailable"}

    proc = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{slug}",
            "--jq",
            "{full_name,archived,disabled,default_branch,pushed_at,stargazers_count,language}",
        ],
        capture_output=True,
        text=True,
        env=dict(os.environ),
        timeout=10,
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        err_tail = proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else "gh_api_failed"
        return {"checked": False, "slug": slug, "error": err_tail}

    meta = json.loads(proc.stdout)
    def_br = str(meta.get("default_branch") or "main")
    target_ref = ref.strip() or def_br

    head_proc = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{slug}/commits/{target_ref}",
            "--jq",
            "{sha: .sha, date: .commit.committer.date, subject: (.commit.message | split(\"\\n\")[0])}",
        ],
        capture_output=True,
        text=True,
        env=dict(os.environ),
        timeout=10,
        check=False,
    )
    if head_proc.returncode != 0 or not head_proc.stdout.strip():
        err_tail = head_proc.stderr.strip().splitlines()[-1] if head_proc.stderr.strip() else "ref_not_found"
        return {
            "checked": True,
            "kind": "github",
            "slug": str(meta.get("full_name") or slug),
            "checked_ref": target_ref,
            "blockers": [f"remote_ref_not_found: `{slug}` ref `{target_ref}` failed lookup ({err_tail})."],
            "warnings": [],
        }
    head_meta = json.loads(head_proc.stdout)

    pvr_proc = subprocess.run(
        ["gh", "api", f"repos/{slug}/private-vulnerability-reporting", "--jq", ".enabled"],
        capture_output=True,
        text=True,
        env=dict(os.environ),
        timeout=8,
        check=False,
    )
    pvr_enabled = pvr_proc.stdout.strip() == "true" if pvr_proc.returncode == 0 else None

    pushed_age = _parse_iso_age_days(str(meta.get("pushed_at") or ""))
    commit_age = _parse_iso_age_days(str(head_meta.get("date") or ""))
    eff_age = commit_age if commit_age is not None else pushed_age

    blockers: list[str] = []
    warnings: list[str] = []
    if meta.get("archived"):
        blockers.append(f"remote_repo_archived: GitHub repository `{slug}` has `archived: true`.")
    if meta.get("disabled"):
        blockers.append(f"remote_repo_disabled: GitHub repository `{slug}` is disabled.")
    subj = str(head_meta.get("subject") or "")
    if ARCHIVAL_COMMIT_SUBJECT_RE.search(subj):
        blockers.append(f"remote_archived_commit_notice: `{slug}` ref `{target_ref}` indicates archival ({subj!r}).")
    if eff_age is not None and max_age_days > 0 and eff_age > float(max_age_days):
        blockers.append(
            f"remote_stale_ref: `{slug}` (`{target_ref}`) last commit is {eff_age} days old (> {max_age_days}d limit)."
        )

    return {
        "checked": True,
        "kind": "github",
        "slug": str(meta.get("full_name") or slug),
        "archived": bool(meta.get("archived")),
        "disabled": bool(meta.get("disabled")),
        "default_branch": def_br,
        "checked_ref": target_ref,
        "pushed_at": meta.get("pushed_at"),
        "remote_head_sha": head_meta.get("sha", ""),
        "remote_head_date": head_meta.get("date", ""),
        "remote_head_age_days": eff_age,
        "remote_head_subject": subj,
        "private_vulnerability_reporting": pvr_enabled,
        "stargazers_count": meta.get("stargazers_count"),
        "language": meta.get("language"),
        "blockers": blockers,
        "warnings": warnings,
    }


def _probe_git_ls_remote(url: str, *, ref: str = "") -> dict[str, Any]:
    target_ref = ref.strip() or "HEAD"
    proc = subprocess.run(
        ["git", "ls-remote", url, target_ref],
        capture_output=True,
        text=True,
        env=dict(os.environ),
        timeout=10,
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        err_tail = proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else "ls_remote_failed"
        return {
            "checked": False,
            "kind": "git_remote",
            "url": url,
            "checked_ref": target_ref,
            "error": err_tail,
            "blockers": [f"remote_unreachable: `git ls-remote {url} {target_ref}` failed ({err_tail})."],
            "warnings": [],
        }
    sha = proc.stdout.strip().split()[0]
    return {
        "checked": True,
        "kind": "git_remote",
        "url": url,
        "checked_ref": target_ref,
        "remote_head_sha": sha,
        "blockers": [],
        "warnings": [],
    }


def evaluate_target_readiness(
    target: str,
    *,
    subdir: str = "",
    ref: str = "",
    peers: Sequence[str] = (),
    max_age_days: int = 90,
    check_remote: bool = True,
) -> dict[str, Any]:
    """Run exogenous readiness checks (`E1–E4`) on a local path, `owner/repo` slug, or remote git URL."""
    raw = target.strip()
    blockers: list[str] = []
    warnings: list[str] = []
    disk = compute_disk_free_gib()

    cand_path = pathlib.Path(raw).expanduser()
    local_exists = cand_path.exists()
    local_info: dict[str, Any] = {}
    scope_info: dict[str, Any] = {}
    remote_info: dict[str, Any] = {"checked": False}
    gh_slug = ""
    remote_url = ""

    if local_exists:
        resolved_root = cand_path.resolve()
        eff_dir = (resolved_root / subdir.strip().strip("/")).resolve() if subdir.strip() else resolved_root
        if not eff_dir.exists():
            blockers.append(f"subdir_missing: requested --subdir {subdir!r} does not exist under {resolved_root}.")
            eff_dir = resolved_root

        local_info = inspect_local_target_freshness(eff_dir, max_age_days=max_age_days)
        blockers.extend(local_info.get("blockers", []))
        warnings.extend(local_info.get("warnings", []))

        git_root_path = pathlib.Path(local_info["git_root"]) if local_info.get("git_root") else None
        loc = count_in_scope_loc(eff_dir) if eff_dir.is_dir() else {"total_loc": 0, "files_counted": 1, "code_quote_usd": 10.0}
        quote_usd = float(loc["code_quote_usd"])
        agent_cfgs = _scan_embedded_agent_configs(eff_dir, git_root_path) if eff_dir.is_dir() else []
        no_std_count = _count_rust_no_std_crates(eff_dir) if eff_dir.is_dir() else 0
        sec_md = _find_security_md(eff_dir, git_root_path) if eff_dir.is_dir() else ""

        if agent_cfgs:
            warnings.append(
                f"Target contains {len(agent_cfgs)} embedded agent config file(s) ({', '.join(pathlib.Path(p).name for p in agent_cfgs[:4])}); "
                "run workers from a neutral workspace directory outside the target checkout or `--envelope` so target coding rules do not override Ajar."
            )
        if no_std_count > 0:
            warnings.append(
                f"Detected {no_std_count} Rust `#![no_std]` crate(s); pass `--features std` or workspace-level test flags when reproducing."
            )
        if (eff_dir / "Cargo.toml").is_file() or (git_root_path and (git_root_path / "Cargo.toml").is_file()):
            if 0.0 <= disk.get("tmp_free_gib", 99.0) < 4.0:
                warnings.append(
                    f"Low `/tmp` disk headroom ({disk['tmp_free_gib']} GiB free) for Rust incremental builds."
                )

        scope_info = {
            "effective_target_path": str(eff_dir),
            "in_scope_loc": int(loc["total_loc"]),
            "files_counted": int(loc["files_counted"]),
            "code_quote_usd": quote_usd,
            "cogs_cap_usd": compute_cogs_cap_usd(quote_usd),
            "embedded_agent_configs": agent_cfgs,
            "rust_no_std_crates": no_std_count,
            "security_md_path": sec_md,
        }

        origin = str(local_info.get("origin_url") or "")
        m_gh = GITHUB_REMOTE_URL_RE.search(origin)
        if m_gh:
            gh_slug = m_gh.group(1)
        elif REMOTE_GIT_URL_RE.match(origin):
            remote_url = origin
    else:
        m_slug = GITHUB_SLUG_RE.match(raw)
        m_gh_url = GITHUB_REMOTE_URL_RE.search(raw)
        if m_slug:
            gh_slug = f"{m_slug.group(1)}/{m_slug.group(2)}"
        elif m_gh_url:
            gh_slug = m_gh_url.group(1)
        elif REMOTE_GIT_URL_RE.match(raw):
            remote_url = raw
        else:
            blockers.append(f"target_not_found: {raw!r} is neither an existing local path, `owner/repo` slug, nor git URL.")

    if check_remote:
        if gh_slug:
            remote_info = _probe_github_repo(gh_slug, ref=ref, max_age_days=max_age_days)
            if remote_info.get("checked"):
                blockers.extend(remote_info.get("blockers", []))
                warnings.extend(remote_info.get("warnings", []))
                if local_info.get("head_sha") and remote_info.get("remote_head_sha"):
                    if local_info["head_sha"] != remote_info["remote_head_sha"]:
                        warnings.append(
                            f"Local HEAD ({local_info['head_sha'][:12]} on `{local_info.get('branch', '')}`) differs from "
                            f"remote ref `{remote_info.get('checked_ref', '')}` ({remote_info['remote_head_sha'][:12]}); "
                            "confirm whether this is an intentional scope pin or a stale mirror/checkout."
                        )
            elif not local_exists and remote_info.get("error"):
                blockers.append(f"remote_lookup_failed: `{gh_slug}` ({remote_info['error']}).")
        elif remote_url:
            remote_info = _probe_git_ls_remote(remote_url, ref=ref)
            blockers.extend(remote_info.get("blockers", []))
            warnings.extend(remote_info.get("warnings", []))

    peer_reports: list[dict[str, Any]] = []
    for p_raw in peers:
        if not p_raw or not p_raw.strip():
            continue
        pp = pathlib.Path(p_raw.strip()).expanduser().resolve()
        if not pp.exists():
            blockers.append(f"peer_missing: reference peer path does not exist: {pp}")
            peer_reports.append({"path": str(pp), "exists": False})
            continue
        p_fresh = inspect_local_target_freshness(pp, max_age_days=max_age_days)
        peer_reports.append(
            {
                "path": str(pp),
                "exists": True,
                "head_sha": p_fresh.get("head_sha", ""),
                "head_age_days": p_fresh.get("head_age_days"),
                "passed": p_fresh.get("passed", True),
            }
        )
        if not p_fresh.get("passed", True):
            warnings.append(f"Reference peer `{pp.name}` has freshness warnings/blockers: {p_fresh.get('blockers')}")

    return {
        "target": raw,
        "subdir": subdir,
        "passed": len(blockers) == 0,
        "blockers": blockers,
        "warnings": warnings,
        "local": local_info,
        "scope": scope_info,
        "remote": remote_info,
        "peers": peer_reports,
        "disk": disk,
    }
