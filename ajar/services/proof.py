"""Startup proof helpers: `DEC-0132` COGS calibration export and `P0-3` commit-before-submit ledger preimages.

Pure-stdlib, read-only over `run.db`, strictly redacted via `scrub_text`, and non-interfering
with Host Mode execution.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import secrets
import sqlite3
from typing import Any

from ajar import EXIT_USER_ERROR
from ajar.db import utc_now_iso
from ajar.domain import AjarError
from ajar.gates import compute_attribution_and_economics
from ajar.redact import scrub_text


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
    digest = hashlib.sha256(_canonical_json_bytes(preimage)).hexdigest()
    return secrets.compare_digest(digest, commitment_sha256.strip().lower())


def build_commit_preimage(
    conn: sqlite3.Connection,
    *,
    finding_id: str,
    commit_sha: str = "",
    target_slug: str = "",
    salt: str | None = None,
) -> dict[str, Any]:
    """Build a gapless `P0-3` commit-before-submit SHA-256 ledger commitment for a confirmed finding.

    All text fields are passed through `scrub_text` so raw exploit payloads, credentials, or
    tokens can never leak into either the public commitment record or private reveal preimage.
    """
    fid = finding_id.strip()
    if not fid:
        raise AjarError("finding_id must be non-empty.", EXIT_USER_ERROR)
    finding = conn.execute("SELECT * FROM findings WHERE finding_id = ?", (fid,)).fetchone()
    if finding is None:
        raise AjarError(f"Unknown finding_id: {fid}", EXIT_USER_ERROR)

    run = conn.execute("SELECT run_id, target_path, commitment_hash FROM runs LIMIT 1").fetchone()
    run_id = str(run["run_id"]) if run is not None else ""
    derived_slug = (target_slug or "").strip()
    if not derived_slug and run is not None and run["target_path"]:
        derived_slug = pathlib.Path(str(run["target_path"])).name
    derived_commit = (commit_sha or "").strip() or (str(run["commitment_hash"]) if run is not None else "")
    salt_hex = (salt or "").strip() or secrets.token_hex(16)
    created_at = utc_now_iso()

    preimage: dict[str, Any] = {
        "schema_version": "ajar-ledger-preimage/1",
        "run_id": run_id,
        "finding_id": fid,
        "claim_id": str(finding["claim_id"]),
        "target_slug": scrub_text(derived_slug),
        "commit_sha": scrub_text(derived_commit),
        "severity": str(finding["severity"]),
        "title": scrub_text(str(finding["title"])),
        "locus": scrub_text(str(finding["locus"])),
        "attribution": str(finding["attribution"]),
        "created_at": created_at,
        "salt": salt_hex,
    }
    commitment_sha256 = hashlib.sha256(_canonical_json_bytes(preimage)).hexdigest()

    public_record: dict[str, Any] = {
        "schema_version": "ajar-ledger-commitment/1",
        "commitment_sha256": commitment_sha256,
        "finding_id": fid,
        "target_slug": preimage["target_slug"],
        "commit_sha": preimage["commit_sha"],
        "severity": preimage["severity"],
        "attribution": preimage["attribution"],
        "committed_at": created_at,
    }

    return {
        "schema_version": "ajar-ledger-commitment/1",
        "commitment_sha256": commitment_sha256,
        "public_record": public_record,
        "private_preimage": preimage,
    }


def write_restricted_json(path: pathlib.Path, payload: dict[str, Any], *, mode: int = 0o600) -> None:
    """Atomically write JSON with restrictive permissions (used for private reveal preimages)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)
    os.chmod(path, mode)
