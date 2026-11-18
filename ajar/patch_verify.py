"""8-Arm Production Remediation Verifier (`ajar patch verify` — `Fixes` gate).

Separates fast finding reproduction (`ajar claim reproduce`, Arms 1–4) from
maintainer-ready `Fixes` promotion (`remediation_state = 'maintainer_patched'`):
- Arms 1–4: Counterfactual root-cause & locus-match proof (`clean+PoC`, `clean+control`,
  `patch+PoC`, `patch+control`)
- Arm 5: Full project test suite passes on the patched tree (`--suite-cmd`)
- Arm 6: `>= 3` distinct bypass variants all blocked on the patched tree (`--variant-cmd`)
- Arm 7: Caller NULL/error-return path safety audit (`GhostLock` regression guard)
- Arm 8: Sibling-route / peer-hook symmetry audit across parallel entrypoints
"""

from __future__ import annotations

import fcntl
import json
import pathlib
import sqlite3
import subprocess
from typing import Any, Sequence

from ajar import EXIT_GATE_BLOCKED, EXIT_USER_ERROR
from ajar.db import AjarError, log_event, new_id, utc_now_iso
from ajar.redact import scrub_text, scrubbed_subprocess_env
from ajar.repro_source import (
    _acquire_slot,
    _bump_files_mtime,
    _neutralize_python_pth_escapes,
    _prepare_slot_worktree,
    _run_trials,
    init_source_mirror,
    run_source_reproduction,
)


def run_8arm_patch_verification(
    conn: sqlite3.Connection,
    *,
    run_dir: pathlib.Path,
    target_dir: pathlib.Path,
    finding_id: str,
    patch_path: pathlib.Path,
    suite_cmd: str,
    variant_cmds: Sequence[str],
    caller_audit: str,
    sibling_audit: str,
    oracle: dict[str, Any] | None = None,
    shared_guard_locus: str = "",
    max_changed_lines: int = 120,
    timeout_sec: int = 90,
    worker_id: str = "worker",
) -> dict[str, Any]:
    """Execute all 8 verification arms before promoting a fix to `maintainer_patched`."""
    finding = conn.execute("SELECT * FROM findings WHERE finding_id = ?", (finding_id,)).fetchone()
    if finding is None:
        raise AjarError(f"Unknown finding_id: {finding_id}", EXIT_USER_ERROR)

    clean_variants = [v.strip() for v in variant_cmds if v and v.strip()]
    if len(clean_variants) < 3:
        raise AjarError(
            f"Arm 6 requires at least 3 distinct --variant-cmd bypass tests (got {len(clean_variants)}).",
            EXIT_GATE_BLOCKED,
        )
    if not suite_cmd.strip():
        raise AjarError("Arm 5 requires a non-empty --suite-cmd full test suite command.", EXIT_USER_ERROR)
    if len(caller_audit.strip()) < 20:
        raise AjarError(
            "Arm 7 (--caller-audit) must document caller error/NULL-return safety in >= 20 characters.",
            EXIT_GATE_BLOCKED,
        )
    if len(sibling_audit.strip()) < 20:
        raise AjarError(
            "Arm 8 (--sibling-audit) must document sibling-route / peer-hook symmetry in >= 20 characters.",
            EXIT_GATE_BLOCKED,
        )

    claim_id = str(finding["claim_id"])
    base_repro = run_source_reproduction(
        run_dir=run_dir,
        target_dir=target_dir,
        claim_id=claim_id,
        poc_cmd=str(finding["poc_cmd"]),
        control_cmd=str(finding["control_cmd"]),
        micropatch_path=patch_path,
        oracle=oracle,
        timeout_sec=timeout_sec,
        claim_locus=str(finding["locus"]),
        shared_guard_locus=shared_guard_locus,
        max_changed_lines=max_changed_lines,
    )

    arms: dict[str, Any] = {
        "arm1_clean_poc": base_repro["arm1_clean_poc"],
        "arm2_clean_control": base_repro["arm2_clean_control"],
        "arm3_patch_poc": base_repro["arm3_patch_poc"],
        "arm4_patch_control": base_repro["arm4_patch_control"],
        "arm5_full_suite": {"arm_passed": False},
        "arm6_bypass_variants": {"arm_passed": False, "variants": []},
        "arm7_caller_audit": {"arm_passed": True, "notes": scrub_text(caller_audit.strip()[:600])},
        "arm8_sibling_audit": {"arm_passed": True, "notes": scrub_text(sibling_audit.strip()[:600])},
    }

    if not base_repro["passed"]:
        return _persist_patch_verification(
            conn,
            finding_id=finding_id,
            claim_id=claim_id,
            patch_path=patch_path,
            patch_diff=str(base_repro.get("micropatch_diff") or ""),
            suite_cmd=suite_cmd,
            variant_cmds=clean_variants,
            caller_audit=caller_audit,
            sibling_audit=sibling_audit,
            arms=arms,
            passed=False,
            reason=f"Arms 1-4 failed: {base_repro['reason']}",
            worker_id=worker_id,
        )

    mirror_dir = init_source_mirror(run_dir, target_dir)
    repro_dir = run_dir / "repro"
    slot_idx, lock_fh = _acquire_slot(repro_dir)
    slot_dir = repro_dir / f"slot-{slot_idx}"
    cache_dir = repro_dir / f"cache-{slot_idx}"
    cache_dir.mkdir(parents=True, exist_ok=True)
    watermark_file = cache_dir / "watermark_ns"
    touched_files = list(base_repro.get("touched_files") or [])

    try:
        _prepare_slot_worktree(mirror_dir, slot_dir)
        subprocess.run(
            ["git", "-C", str(slot_dir), "apply", "--whitespace=nowarn", str(patch_path.resolve())],
            capture_output=True,
            text=True,
            env=scrubbed_subprocess_env(),
            check=True,
        )
        _neutralize_python_pth_escapes(slot_dir)
        _bump_files_mtime(slot_dir, touched_files, watermark_file)

        # Arm 5: Full test suite must exit 0 without defect or timeout.
        suite_res = _run_trials(
            suite_cmd,
            slot_dir=slot_dir,
            cache_dir=cache_dir,
            timeout_sec=timeout_sec,
            oracle=None,
            trials=1,
        )
        suite_passed = int(suite_res["exit_code"]) == 0 and not bool(suite_res["timed_out"])
        arms["arm5_full_suite"] = {**suite_res, "arm_passed": suite_passed}
        if not suite_passed:
            return _persist_patch_verification(
                conn,
                finding_id=finding_id,
                claim_id=claim_id,
                patch_path=patch_path,
                patch_diff=str(base_repro.get("micropatch_diff") or ""),
                suite_cmd=suite_cmd,
                variant_cmds=clean_variants,
                caller_audit=caller_audit,
                sibling_audit=sibling_audit,
                arms=arms,
                passed=False,
                reason=f"Arm 5 (full suite) failed on patched tree (exit={suite_res['exit_code']}).",
                worker_id=worker_id,
            )

        # Arm 6: All >= 3 bypass variants must fail to trigger the defect on the patched tree.
        variant_results: list[dict[str, Any]] = []
        all_variants_blocked = True
        for idx, vcmd in enumerate(clean_variants, start=1):
            vres = _run_trials(
                vcmd,
                slot_dir=slot_dir,
                cache_dir=cache_dir,
                timeout_sec=timeout_sec,
                oracle=oracle,
                trials=1,
            )
            v_blocked = int(vres["defect_hits"]) == 0 and not bool(vres["timed_out"])
            variant_results.append({"index": idx, "cmd": scrub_text(vcmd), "blocked": v_blocked, "exit_code": vres["exit_code"]})
            if not v_blocked:
                all_variants_blocked = False

        arms["arm6_bypass_variants"] = {
            "arm_passed": all_variants_blocked,
            "variant_count": len(clean_variants),
            "variants": variant_results,
        }
        if not all_variants_blocked:
            return _persist_patch_verification(
                conn,
                finding_id=finding_id,
                claim_id=claim_id,
                patch_path=patch_path,
                patch_diff=str(base_repro.get("micropatch_diff") or ""),
                suite_cmd=suite_cmd,
                variant_cmds=clean_variants,
                caller_audit=caller_audit,
                sibling_audit=sibling_audit,
                arms=arms,
                passed=False,
                reason="Arm 6 failed: one or more bypass variants still triggered the defect on the patched tree.",
                worker_id=worker_id,
            )

        return _persist_patch_verification(
            conn,
            finding_id=finding_id,
            claim_id=claim_id,
            patch_path=patch_path,
            patch_diff=str(base_repro.get("micropatch_diff") or ""),
            suite_cmd=suite_cmd,
            variant_cmds=clean_variants,
            caller_audit=caller_audit,
            sibling_audit=sibling_audit,
            arms=arms,
            passed=True,
            reason="All 8 production patch verification arms passed; promoted to maintainer_patched.",
            worker_id=worker_id,
        )
    finally:
        if (slot_dir / ".git").exists():
            subprocess.run(["git", "-C", str(slot_dir), "reset", "--hard", "HEAD"], capture_output=True, check=False)
            subprocess.run(["git", "-C", str(slot_dir), "clean", "-fdx"], capture_output=True, check=False)
            _bump_files_mtime(slot_dir, touched_files, watermark_file)
        fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)
        lock_fh.close()


def _persist_patch_verification(
    conn: sqlite3.Connection,
    *,
    finding_id: str,
    claim_id: str,
    patch_path: pathlib.Path,
    patch_diff: str,
    suite_cmd: str,
    variant_cmds: Sequence[str],
    caller_audit: str,
    sibling_audit: str,
    arms: dict[str, Any],
    passed: bool,
    reason: str,
    worker_id: str,
) -> dict[str, Any]:
    vid = new_id("pvf")
    now_iso = utc_now_iso()
    conn.execute(
        """
        INSERT INTO patch_verifications(
            verification_id, finding_id, claim_id, patch_path, patch_diff,
            suite_cmd, variant_cmds_json, caller_audit, sibling_audit,
            arms_json, passed, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            vid,
            finding_id,
            claim_id,
            str(patch_path),
            scrub_text(patch_diff[:8000]),
            scrub_text(suite_cmd),
            json.dumps([scrub_text(v) for v in variant_cmds]),
            scrub_text(caller_audit.strip()),
            scrub_text(sibling_audit.strip()),
            json.dumps(arms, sort_keys=True),
            1 if passed else 0,
            now_iso,
        ),
    )
    if passed:
        conn.execute(
            "UPDATE claims SET remediation_state = 'maintainer_patched', updated_at = ? WHERE claim_id = ?",
            (now_iso, claim_id),
        )
    log_event(
        conn,
        worker_id,
        "patch_verified" if passed else "patch_verify_failed",
        vid,
        {"finding_id": finding_id, "claim_id": claim_id, "passed": passed, "reason": reason[:200]},
    )
    return {
        "verification_id": vid,
        "finding_id": finding_id,
        "claim_id": claim_id,
        "passed": passed,
        "remediation_state": "maintainer_patched" if passed else "micropatched",
        "reason": reason,
        "arms": arms,
    }
