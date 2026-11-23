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

from ajar import EXIT_GATE_BLOCKED, EXIT_USER_ERROR
from ajar.db import utc_now_iso
from ajar.domain import AjarError
from ajar.gates import compute_attribution_and_economics
from ajar.redact import detect_secret_classes, scan_file_secret_classes, scrub_text

HEX_SALT_RE = re.compile(r"^[0-9a-fA-F]{16,128}$")
SHA256_HEX_RE = re.compile(r"^[0-9a-fA-F]{64}$")
BUNDLE_LOCAL_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_.+/-])(?:/(?:home|Users)/[A-Za-z0-9._-]+|/(?:private/)?(?:tmp|var/tmp)/[A-Za-z0-9._-]+|/shared/user\b)"
)
BUNDLE_META_FILES: frozenset[str] = frozenset({"BUNDLE-MANIFEST.json", "SEAL.sha256"})


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


def _snapshot_bundle_tree(literal_root: pathlib.Path) -> dict[str, tuple[int, int]]:
    """Walk `literal_root` without following symlinks; reject any symlink root or child entry."""
    import stat as stat_mod

    try:
        st_root = os.lstat(literal_root)
    except OSError as exc:
        raise AjarError(f"Bundle directory does not exist: {literal_root}", EXIT_USER_ERROR) from exc
    if stat_mod.S_ISLNK(st_root.st_mode):
        raise AjarError(
            f"Bundle seal refuses symlink root path: {literal_root}. Pass the real directory path.",
            EXIT_GATE_BLOCKED,
        )
    if not stat_mod.S_ISDIR(st_root.st_mode):
        raise AjarError(f"Bundle path is not a directory: {literal_root}", EXIT_USER_ERROR)

    snap: dict[str, tuple[int, int]] = {}
    for cur_root, dirs, files in os.walk(literal_root, followlinks=False):
        cur_p = pathlib.Path(cur_root)
        dirs.sort()
        for d in dirs:
            dp = cur_p / d
            dst = os.lstat(dp)
            if stat_mod.S_ISLNK(dst.st_mode):
                raise AjarError(
                    f"Bundle seal refuses symlink directory inside bundle: {dp.relative_to(literal_root)}",
                    EXIT_GATE_BLOCKED,
                )
        for f in sorted(files):
            fp = cur_p / f
            rel = fp.relative_to(literal_root).as_posix()
            if rel in BUNDLE_META_FILES:
                continue
            fst = os.lstat(fp)
            if stat_mod.S_ISLNK(fst.st_mode):
                raise AjarError(
                    f"Bundle seal refuses symlink file inside bundle: {rel}",
                    EXIT_GATE_BLOCKED,
                )
            if not stat_mod.S_ISREG(fst.st_mode):
                raise AjarError(
                    f"Bundle seal refuses non-regular file inside bundle: {rel}",
                    EXIT_GATE_BLOCKED,
                )
            snap[rel] = (int(fst.st_size), int(fst.st_mtime_ns))
    return snap


def _scan_text_hygiene(rel_label: str, raw_bytes: bytes, *, allow_local_paths: bool) -> list[str]:
    issues: list[str] = []
    if b"\x00" in raw_bytes[:4096]:
        return issues
    secret_hits = detect_secret_classes(raw_bytes)
    if secret_hits:
        issues.append(f"{rel_label}: secret pattern(s) detected ({', '.join(secret_hits)})")
    if not allow_local_paths:
        text = raw_bytes.decode("utf-8", errors="ignore")
        m = BUNDLE_LOCAL_PATH_RE.search(text)
        if m is not None:
            issues.append(f"{rel_label}: local filesystem path leaked ({m.group(0)!r})")
    return issues


def _scan_archive_hygiene(fpath: pathlib.Path, rel: str, *, allow_local_paths: bool) -> list[str]:
    import tarfile
    import zipfile

    issues: list[str] = []
    low = rel.lower()
    max_member_bytes = 8 * 1024 * 1024
    if low.endswith((".tar", ".tar.gz", ".tgz")):
        try:
            with tarfile.open(fpath, "r:*") as tf:
                for m in tf.getmembers():
                    if m.issym() or m.islnk():
                        issues.append(f"{rel}!{m.name}: symlink/hardlink member inside tar archive")
                        continue
                    if m.isfile() and 0 < m.size <= max_member_bytes:
                        fh = tf.extractfile(m)
                        if fh is not None:
                            issues.extend(
                                _scan_text_hygiene(f"{rel}!{m.name}", fh.read(max_member_bytes), allow_local_paths=allow_local_paths)
                            )
        except (tarfile.TarError, OSError) as exc:
            issues.append(f"{rel}: corrupt tar archive ({exc})")
    elif low.endswith(".zip"):
        try:
            with zipfile.ZipFile(fpath, "r") as zf:
                for info in zf.infolist():
                    is_symlink = ((info.external_attr >> 16) & 0o170000) == 0o120000
                    if is_symlink:
                        issues.append(f"{rel}!{info.filename}: symlink member inside zip archive")
                        continue
                    if not info.is_dir() and 0 < info.file_size <= max_member_bytes:
                        with zf.open(info, "r") as zfh:
                            issues.extend(
                                _scan_text_hygiene(
                                    f"{rel}!{info.filename}",
                                    zfh.read(max_member_bytes),
                                    allow_local_paths=allow_local_paths,
                                )
                            )
        except (zipfile.BadZipFile, OSError) as exc:
            issues.append(f"{rel}: corrupt zip archive ({exc})")
    return issues


def seal_bundle(
    bundle_dir: pathlib.Path | str,
    *,
    allow_local_paths: bool = False,
) -> dict[str, Any]:
    """Atomically verify hygiene, check writer stability, and emit `BUNDLE-MANIFEST.json` + `SEAL.sha256`."""
    literal_root = pathlib.Path(os.path.abspath(os.fspath(bundle_dir)))
    snap_before = _snapshot_bundle_tree(literal_root)
    if not snap_before:
        raise AjarError(f"Cannot seal empty bundle directory: {literal_root}", EXIT_USER_ERROR)

    hygiene_issues: list[str] = []
    entries: list[dict[str, Any]] = []
    for rel in sorted(snap_before.keys()):
        fpath = literal_root / rel
        h = hashlib.sha256()
        head_chunks: list[bytes] = []
        head_budget = 4 * 1024 * 1024
        size_read = 0
        with open(fpath, "rb") as fh:
            while chunk := fh.read(65536):
                h.update(chunk)
                if size_read < head_budget:
                    head_chunks.append(chunk[: head_budget - size_read])
                size_read += len(chunk)
        raw_head = b"".join(head_chunks)
        low = rel.lower()
        if low.endswith((".tar", ".tar.gz", ".tgz", ".zip")):
            hygiene_issues.extend(_scan_archive_hygiene(fpath, rel, allow_local_paths=allow_local_paths))
        else:
            hygiene_issues.extend(_scan_text_hygiene(rel, raw_head, allow_local_paths=allow_local_paths))
            if size_read > head_budget and b"\x00" not in raw_head[:4096]:
                tail_hits = scan_file_secret_classes(fpath)
                if tail_hits:
                    hygiene_issues.append(f"{rel}: secret pattern(s) detected ({', '.join(tail_hits)})")
        entries.append(
            {
                "path": rel,
                "sha256": h.hexdigest(),
                "size_bytes": size_read,
            }
        )

    if hygiene_issues:
        raise AjarError(
            "Bundle hygiene gate failed ("
            + f"{len(hygiene_issues)} issue(s)): "
            + "; ".join(hygiene_issues[:6]),
            EXIT_GATE_BLOCKED,
        )

    snap_after = _snapshot_bundle_tree(literal_root)
    if snap_before != snap_after:
        raise AjarError(
            "Concurrent writer modified bundle files during seal; wait for writers to finish and re-run `ajar bundle seal`.",
            EXIT_GATE_BLOCKED,
        )

    manifest_core = {
        "schema_version": "ajar-bundle-manifest/1",
        "file_count": len(entries),
        "total_bytes": sum(int(e["size_bytes"]) for e in entries),
        "allow_local_paths": bool(allow_local_paths),
        "files": entries,
    }
    seal_sha256 = hashlib.sha256(_canonical_json_bytes(manifest_core)).hexdigest()
    manifest_doc = {
        **manifest_core,
        "seal_sha256": seal_sha256,
        "sealed_at": utc_now_iso(),
    }

    manifest_path = literal_root / "BUNDLE-MANIFEST.json"
    seal_path = literal_root / "SEAL.sha256"
    write_restricted_json(manifest_path, manifest_doc, mode=0o644)
    tmp_seal = literal_root / f".SEAL.sha256.{secrets.token_hex(8)}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(str(tmp_seal), flags, 0o644)
    try:
        with os.fdopen(fd, "wb") as sfh:
            sfh.write(f"{seal_sha256}  BUNDLE-MANIFEST.json\n".encode("ascii"))
            sfh.flush()
        os.replace(str(tmp_seal), str(seal_path))
    except BaseException:
        tmp_seal.unlink(missing_ok=True)
        raise

    return {
        "schema_version": "ajar-bundle-manifest/1",
        "bundle_dir": str(literal_root),
        "file_count": len(entries),
        "total_bytes": manifest_core["total_bytes"],
        "seal_sha256": seal_sha256,
        "manifest_path": str(manifest_path),
        "seal_path": str(seal_path),
    }


def verify_bundle(bundle_dir: pathlib.Path | str) -> dict[str, Any]:
    """Verify an existing `BUNDLE-MANIFEST.json` + `SEAL.sha256` against on-disk regular files."""
    literal_root = pathlib.Path(os.path.abspath(os.fspath(bundle_dir)))
    snap = _snapshot_bundle_tree(literal_root)
    manifest_path = literal_root / "BUNDLE-MANIFEST.json"
    seal_path = literal_root / "SEAL.sha256"
    if manifest_path.is_symlink() or seal_path.is_symlink():
        raise AjarError("Bundle manifest or seal file is a symlink.", EXIT_GATE_BLOCKED)
    if not manifest_path.is_file() or not seal_path.is_file():
        raise AjarError(
            f"Bundle at {literal_root} is missing BUNDLE-MANIFEST.json or SEAL.sha256.",
            EXIT_GATE_BLOCKED,
        )
    try:
        manifest_doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AjarError(f"Invalid BUNDLE-MANIFEST.json: {exc}", EXIT_GATE_BLOCKED) from exc

    seal_line = seal_path.read_text(encoding="utf-8", errors="replace").strip().split()
    recorded_seal = seal_line[0] if seal_line else ""
    files_list = manifest_doc.get("files")
    if not isinstance(files_list, list):
        raise AjarError("Invalid BUNDLE-MANIFEST.json: missing `files` list.", EXIT_GATE_BLOCKED)

    manifest_core = {
        "schema_version": str(manifest_doc.get("schema_version") or ""),
        "file_count": int(manifest_doc.get("file_count") or 0),
        "total_bytes": int(manifest_doc.get("total_bytes") or 0),
        "allow_local_paths": bool(manifest_doc.get("allow_local_paths", False)),
        "files": files_list,
    }
    expected_seal = hashlib.sha256(_canonical_json_bytes(manifest_core)).hexdigest()
    issues: list[str] = []
    if not recorded_seal or not secrets.compare_digest(recorded_seal.lower(), expected_seal.lower()):
        issues.append("SEAL.sha256 does not match canonical BUNDLE-MANIFEST.json digest")
    if str(manifest_doc.get("seal_sha256") or "").lower() != expected_seal.lower():
        issues.append("manifest seal_sha256 field does not match canonical digest")

    recorded_map: dict[str, dict[str, Any]] = {}
    for entry in files_list:
        if isinstance(entry, dict) and entry.get("path"):
            recorded_map[str(entry["path"])] = entry

    extra_files = sorted(set(snap.keys()) - set(recorded_map.keys()))
    missing_files = sorted(set(recorded_map.keys()) - set(snap.keys()))
    if extra_files:
        issues.append(f"untracked file(s) added after seal: {extra_files[:5]}")
    if missing_files:
        issues.append(f"manifest file(s) missing on disk: {missing_files[:5]}")

    for rel, entry in sorted(recorded_map.items()):
        if rel not in snap:
            continue
        fp = literal_root / rel
        h = hashlib.sha256()
        sz = 0
        with open(fp, "rb") as fh:
            while chunk := fh.read(65536):
                h.update(chunk)
                sz += len(chunk)
        if sz != int(entry.get("size_bytes", -1)) or h.hexdigest() != str(entry.get("sha256") or ""):
            issues.append(f"modified after seal: {rel}")

    return {
        "verified": len(issues) == 0,
        "bundle_dir": str(literal_root),
        "file_count": len(recorded_map),
        "seal_sha256": expected_seal,
        "issues": issues,
    }
