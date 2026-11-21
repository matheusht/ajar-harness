"""Startup proof helpers: `DEC-0132` COGS calibration export and `P0-3` commit-before-submit ledger preimages.

Pure-stdlib, read-only over `run.db`, strictly redacted via `scrub_text`, and non-interfering
with Host Mode execution.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import secrets
import sqlite3
from typing import Any

from ajar import EXIT_USER_ERROR
from ajar.db import utc_now_iso
from ajar.domain import AjarError
from ajar.gates import compute_attribution_and_economics
from ajar.redact import scrub_text

HEX_SALT_RE = re.compile(r"^[0-9a-fA-F]{16,128}$")
SHA256_HEX_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def export_run_economics(conn: sqlite3.Connection) -> dict[str, Any]:
    """Export a structured `DEC-0132` COGS/LoC calibration telemetry record for a run.

    Strictly read-only and advisory in Host Mode (never mutates `runs.status` or blocks tasks).
    """
    run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
    if run is None:
        raise AjarError("Run metadata missing in run.db.", EXIT_USER_ERROR)

    econ = compute_attribution_and_economics(conn)
    quote = float(econ["code_quote_usd"])
    total_spend = float(econ["total_spend_usd"])
    implied_gm_pct = round(((quote - total_spend) / quote) * 100.0, 2) if quote > 0.0 else None

    findings_total = int(conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0])
    findings_high = int(
        conn.execute("SELECT COUNT(*) FROM findings WHERE severity IN ('critical', 'high')").fetchone()[0]
    )
    claims_total = int(conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0])
    claims_falsified = int(conn.execute("SELECT COUNT(*) FROM claims WHERE status = 'falsified'").fetchone()[0])
    claims_reproduced = int(conn.execute("SELECT COUNT(*) FROM claims WHERE status = 'reproduced'").fetchone()[0])
    chains_verified = int(conn.execute("SELECT COUNT(*) FROM chains WHERE verified = 1").fetchone()[0])

    run_keys = set(run.keys())
    return {
        "schema_version": "ajar-economics-calibration/1",
        "exported_at": utc_now_iso(),
        "run_id": str(run["run_id"]),
        "target_mode": str(run["target_mode"]),
        "stopping_criterion": str(run["stopping_criterion"]),
        "campaign_phase": str(run["campaign_phase"]) if "campaign_phase" in run_keys else "hunt",
        "status": str(run["status"]),
        "host_mode_advisory": True,
        "findings_count": findings_total,
        "high_or_critical_findings": findings_high,
        "claims_total": claims_total,
        "claims_falsified": claims_falsified,
        "claims_reproduced": claims_reproduced,
        "chains_verified": chains_verified,
        "implied_gross_margin_pct": implied_gm_pct,
        **econ,
    }


def _canonical_json_bytes(obj: dict[str, Any]) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def verify_commit_preimage(preimage: dict[str, Any], commitment_sha256: str) -> bool:
    """Deterministically verify that a revealed preimage matches a published SHA-256 commitment."""
    candidate = commitment_sha256.strip()
    if not SHA256_HEX_RE.match(candidate):
        return False
    digest = hashlib.sha256(_canonical_json_bytes(preimage)).hexdigest().encode("ascii")
    return secrets.compare_digest(digest, candidate.lower().encode("ascii"))


def build_commit_preimage(
    conn: sqlite3.Connection,
    *,
    finding_id: str,
    commit_sha: str = "",
    target_slug: str = "",
    salt: str | None = None,
) -> dict[str, Any]:
    """Build a gapless `P0-3` commit-before-submit SHA-256 ledger commitment for a confirmed finding.

    All string fields are passed through `scrub_text` so raw exploit payloads, credentials, or
    tokens can never leak into either the public commitment record or private reveal preimage.
    Passing an explicit `--salt` produces a 100% deterministic `commitment_sha256` across calls
    because the preimage hashes the finding's immutable `created_at` timestamp rather than wall time.
    """
    fid = finding_id.strip()
    if not fid:
        raise AjarError("finding_id must be non-empty.", EXIT_USER_ERROR)
    finding = conn.execute("SELECT * FROM findings WHERE finding_id = ?", (fid,)).fetchone()
    if finding is None:
        raise AjarError(f"Unknown finding_id: {fid}", EXIT_USER_ERROR)

    if salt is not None:
        salt_hex = salt.strip().lower()
        if not HEX_SALT_RE.match(salt_hex):
            raise AjarError(
                "Invalid --salt: expected 16–128 hexadecimal characters.",
                EXIT_USER_ERROR,
            )
    else:
        salt_hex = secrets.token_hex(16)

    run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
    run_keys = set(run.keys()) if run is not None else set()
    run_id = str(run["run_id"]) if run is not None else ""
    derived_slug = (target_slug or "").strip()
    if not derived_slug and run is not None and run["target_path"]:
        derived_slug = pathlib.Path(str(run["target_path"])).name

    head_sha = str(run["head_sha"] or "").strip() if (run is not None and "head_sha" in run_keys) else ""
    run_commit_fallback = str(run["commitment_hash"] or "").strip() if run is not None else ""
    derived_commit = (commit_sha or "").strip() or head_sha or run_commit_fallback
    finding_created_at = str(finding["created_at"] or "").strip()

    preimage: dict[str, Any] = {
        "schema_version": "ajar-ledger-preimage/1",
        "run_id": scrub_text(run_id),
        "finding_id": scrub_text(fid),
        "claim_id": scrub_text(str(finding["claim_id"])),
        "target_slug": scrub_text(derived_slug),
        "commit_sha": scrub_text(derived_commit),
        "severity": scrub_text(str(finding["severity"])),
        "title": scrub_text(str(finding["title"])),
        "locus": scrub_text(str(finding["locus"])),
        "attribution": scrub_text(str(finding["attribution"])),
        "created_at": scrub_text(finding_created_at),
        "salt": salt_hex,
    }
    commitment_sha256 = hashlib.sha256(_canonical_json_bytes(preimage)).hexdigest()

    public_record: dict[str, Any] = {
        "schema_version": "ajar-ledger-commitment/1",
        "commitment_sha256": commitment_sha256,
        "finding_id": preimage["finding_id"],
        "target_slug": preimage["target_slug"],
        "commit_sha": preimage["commit_sha"],
        "severity": preimage["severity"],
        "attribution": preimage["attribution"],
        "finding_created_at": preimage["created_at"],
        "committed_at": utc_now_iso(),
    }

    return {
        "schema_version": "ajar-ledger-commitment/1",
        "commitment_sha256": commitment_sha256,
        "public_record": public_record,
        "private_preimage": preimage,
    }


def write_restricted_json(path: pathlib.Path, payload: dict[str, Any], *, mode: int = 0o600) -> None:
    """Atomically write JSON with restrictive permissions, refusing symlinks."""
    if path.is_symlink():
        raise AjarError(f"Refusing to write private preimage through symlink: {path}", EXIT_USER_ERROR)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    tmp_path = path.parent / f".{path.name}.{secrets.token_hex(8)}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(str(tmp_path), flags, mode)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
        os.replace(str(tmp_path), str(path))
    except BaseException:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
