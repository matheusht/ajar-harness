"""9-Arm Production Remediation Verifier (`ajar patch verify` — `Fixes` gate).

Separates fast finding reproduction (`ajar claim reproduce`, Arms 1–4) from
production `Fixes` verification (`remediation_state = 'verified_local'`):
- Enforces `campaign_phase != 'hunt'` so autonomous hunt campaigns never burn budget
  running full test suites prematurely before advancing to `remediate`.
- Arms 1–4: Counterfactual root-cause & locus-match proof (`clean+PoC`, `clean+control`,
  `patch+PoC`, `patch+control`)
- Arm 5: Full project test suite passes on patched tree or introduces zero new test
  regressions relative to cached clean-`HEAD` baseline (`repro/baseline_suite.json`)
- Arm 6: `>= 3` distinct `--variant-cmd` bypass probes (`>= 1` proven to trigger on
  unpatched `HEAD`, blocking trivial `true` commands) all blocked on patched tree
- Arm 7: Caller NULL/error-return safety audit + optional executable `--caller-cmd`
- Arm 8: Sibling-route / peer-hook symmetry audit + optional executable `--sibling-cmd`
- Arm 9: `git apply -R` patch-revert re-failure proof (`poc_cmd` triggers again after revert)
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import pathlib
import re
import sqlite3
import subprocess
from typing import Any, Sequence

from ajar import EXIT_GATE_BLOCKED, EXIT_USER_ERROR
from ajar.db import AjarError, log_event, new_id, utc_now_iso
from ajar.redact import scrub_text, scrubbed_subprocess_env
from ajar.repro_source import (
    _acquire_slot,
    _bump_files_mtime,
    _clean_slot_preserving_objects,
    _neutralize_python_pth_escapes,
    _prepare_slot_worktree,
    _run_trials,
    init_source_mirror,
    resolve_local_build_cache_dir,
    run_source_reproduction,
)

FAILURE_MARKER_RE = re.compile(
    r"^(?:FAIL(?:ED)?\b.*|ERROR\b.*|---\s*FAIL:\s*\S+.*|.*::\S+\s+FAILED\b.*|test\s+\S+\s+\.\.\.\s+FAILED.*)$",
    re.MULTILINE,
)


def _extract_failure_markers(stdout: str, stderr: str) -> list[str]:
    combined = f"{stdout}\n{stderr}"
    markers = {m.strip()[:160] for m in FAILURE_MARKER_RE.findall(combined) if m.strip()}
    return sorted(markers)


def _load_or_run_baseline_suite(
    suite_cmd: str,
    *,
    repro_dir: pathlib.Path,
    slot_dir: pathlib.Path,
    cache_dir: pathlib.Path,
    timeout_sec: int,
) -> dict[str, Any]:
    """Run or load cached clean-`HEAD` baseline suite receipt (`repro/baseline_suite.json`)."""
    cache_file = repro_dir / "baseline_suite.json"
    cmd_key = hashlib.sha256(suite_cmd.strip().encode("utf-8")).hexdigest()[:16]
    store: dict[str, Any] = {}
    if cache_file.is_file():
        try:
            loaded = json.loads(cache_file.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                store = loaded
        except json.JSONDecodeError:
            store = {}

    if cmd_key in store and isinstance(store[cmd_key], dict):
        return dict(store[cmd_key])

    res = _run_trials(
        suite_cmd,
        slot_dir=slot_dir,
        cache_dir=cache_dir,
        timeout_sec=timeout_sec,
        oracle=None,
        trials=1,
    )
    subprocess.run(["git", "-C", str(slot_dir), "reset", "--hard", "HEAD"], capture_output=True, check=False)
    _clean_slot_preserving_objects(slot_dir, check=False)

    entry = {
        "suite_cmd": scrub_text(suite_cmd.strip()),
        "exit_code": int(res["exit_code"]),
        "timed_out": bool(res["timed_out"]),
        "failure_markers": _extract_failure_markers(str(res.get("stdout", "")), str(res.get("stderr", ""))),
    }
    store[cmd_key] = entry
    cache_file.write_text(json.dumps(store, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return entry


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
    caller_cmd: str = "",
    sibling_cmd: str = "",
    oracle: dict[str, Any] | None = None,
    shared_guard_locus: str = "",
    max_changed_lines: int = 120,
    timeout_sec: int = 90,
    suite_timeout_sec: int = 1800,
    worker_id: str = "worker",
) -> dict[str, Any]:
    """Execute all 9 hardened verification arms before promoting a fix to `verified_local`."""
    run_row = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
    if run_row is not None and "campaign_phase" in run_row.keys():
        cur_phase = str(run_row["campaign_phase"] or "hunt")
        if cur_phase == "hunt":
            raise AjarError(
                "Phase gate blocked: 9-arm `ajar patch verify` is disabled while `campaign_phase='hunt'` "
                "so workers focus on discovery and multi-step chains instead of full test-suite rebuilds. "
                "Run `ajar phase advance --to remediate` (or initialize with `--phase full`) when ready to verify fixes.",
                EXIT_GATE_BLOCKED,
            )

    finding = conn.execute("SELECT * FROM findings WHERE finding_id = ?", (finding_id,)).fetchone()
    if finding is None:
        raise AjarError(f"Unknown finding_id: {finding_id}", EXIT_USER_ERROR)

    clean_variants = [v.strip() for v in variant_cmds if v and v.strip()]
    if len(clean_variants) < 3:
        raise AjarError(
            f"Arm 6 requires at least 3 distinct --variant-cmd bypass tests (got {len(clean_variants)}).",
            EXIT_GATE_BLOCKED,
        )
    if len(set(clean_variants)) < len(clean_variants):
        raise AjarError(
            "Arm 6 requires distinct --variant-cmd bypass tests; duplicate commands are rejected.",
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

    eff_oracle = oracle
    if eff_oracle is None and "oracle_json" in finding.keys():
        try:
            parsed_oracle = json.loads(str(finding["oracle_json"] or "{}"))
            if isinstance(parsed_oracle, dict) and parsed_oracle:
                eff_oracle = parsed_oracle
        except json.JSONDecodeError:
            eff_oracle = None

    claim_id = str(finding["claim_id"])
    base_repro = run_source_reproduction(
        run_dir=run_dir,
        target_dir=target_dir,
        claim_id=claim_id,
        poc_cmd=str(finding["poc_cmd"]),
        control_cmd=str(finding["control_cmd"]),
        micropatch_path=patch_path,
        oracle=eff_oracle,
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
        "arm9_revert_poc": {"arm_passed": False},
    }
    baseline_suite: dict[str, Any] = {}

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
            caller_cmd=caller_cmd,
            sibling_cmd=sibling_cmd,
            baseline_suite=baseline_suite,
            arms=arms,
            passed=False,
            reason=f"Arms 1-4 failed: {base_repro['reason']}",
            worker_id=worker_id,
        )

    mirror_dir = init_source_mirror(run_dir, target_dir)
    repro_dir = run_dir / "repro"
    slot_idx, lock_fh = _acquire_slot(repro_dir)
    slot_dir = repro_dir / f"slot-{slot_idx}"
    cache_dir = resolve_local_build_cache_dir(run_dir, f"cache-{slot_idx}")
    watermark_file = cache_dir / "watermark_ns"
    touched_files = list(base_repro.get("touched_files") or [])
    eff_suite_timeout = max(int(timeout_sec), int(suite_timeout_sec))

    try:
        _prepare_slot_worktree(mirror_dir, slot_dir)

        # Clean-HEAD pre-checks:
        # (a) Record/load clean-HEAD suite baseline (`AISLE` baseline diffing).
        baseline_suite = _load_or_run_baseline_suite(
            suite_cmd,
            repro_dir=repro_dir,
            slot_dir=slot_dir,
            cache_dir=cache_dir,
            timeout_sec=eff_suite_timeout,
        )

        # (b) Verify >= 1 `--variant-cmd` triggers the defect on unpatched `HEAD` (blocks `--variant-cmd true` x3).
        clean_variant_hits = 0
        for vcmd in clean_variants:
            cv_res = _run_trials(
                vcmd,
                slot_dir=slot_dir,
                cache_dir=cache_dir,
                timeout_sec=timeout_sec,
                oracle=eff_oracle,
                trials=1,
            )
            subprocess.run(["git", "-C", str(slot_dir), "reset", "--hard", "HEAD"], capture_output=True, check=False)
            _clean_slot_preserving_objects(slot_dir, check=False)
            if int(cv_res["defect_hits"]) >= 1:
                clean_variant_hits += 1

        if clean_variant_hits == 0:
            arms["arm6_bypass_variants"] = {
                "arm_passed": False,
                "clean_head_hits": 0,
                "variant_count": len(clean_variants),
                "variants": [],
            }
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
                caller_cmd=caller_cmd,
                sibling_cmd=sibling_cmd,
                baseline_suite=baseline_suite,
                arms=arms,
                passed=False,
                reason=(
                    "Arm 6 failed pre-flight: zero --variant-cmd commands triggered the defect oracle on clean HEAD "
                    "(noop variants such as `true` are rejected)."
                ),
                worker_id=worker_id,
            )

        # Apply candidate production patch onto `slot-<k>`.
        subprocess.run(
            ["git", "-C", str(slot_dir), "apply", "--whitespace=nowarn", str(patch_path.resolve())],
            capture_output=True,
            text=True,
            env=scrubbed_subprocess_env(),
            check=True,
        )
        _neutralize_python_pth_escapes(slot_dir)
        _bump_files_mtime(slot_dir, touched_files, watermark_file)

        # Arm 5: Full test suite passes (exit 0) OR introduces zero new failure markers vs clean-HEAD baseline.
        suite_res = _run_trials(
            suite_cmd,
            slot_dir=slot_dir,
            cache_dir=cache_dir,
            timeout_sec=eff_suite_timeout,
            oracle=None,
            trials=1,
        )
        patched_markers = _extract_failure_markers(str(suite_res.get("stdout", "")), str(suite_res.get("stderr", "")))
        base_markers = set(baseline_suite.get("failure_markers") or [])
        new_regressions = sorted(set(patched_markers) - base_markers)

        if bool(suite_res["timed_out"]):
            suite_passed = False
        elif int(suite_res["exit_code"]) == 0:
            suite_passed = True
        elif int(baseline_suite.get("exit_code", 0)) != 0 and patched_markers and not new_regressions:
            suite_passed = True
        else:
            suite_passed = False

        arms["arm5_full_suite"] = {
            **suite_res,
            "arm_passed": suite_passed,
            "baseline_exit_code": baseline_suite.get("exit_code", 0),
            "new_regressions": new_regressions,
        }
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
                caller_cmd=caller_cmd,
                sibling_cmd=sibling_cmd,
                baseline_suite=baseline_suite,
                arms=arms,
                passed=False,
                reason=f"Arm 5 (full suite) failed on patched tree (exit={suite_res['exit_code']}, new_regressions={new_regressions[:3]}).",
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
                oracle=eff_oracle,
                trials=1,
            )
            v_blocked = int(vres["defect_hits"]) == 0 and not bool(vres["timed_out"])
            variant_results.append({"index": idx, "cmd": scrub_text(vcmd), "blocked": v_blocked, "exit_code": vres["exit_code"]})
            if not v_blocked:
                all_variants_blocked = False

        arms["arm6_bypass_variants"] = {
            "arm_passed": all_variants_blocked,
            "clean_head_hits": clean_variant_hits,
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
                caller_cmd=caller_cmd,
                sibling_cmd=sibling_cmd,
                baseline_suite=baseline_suite,
                arms=arms,
                passed=False,
                reason="Arm 6 failed: one or more bypass variants still triggered the defect on the patched tree.",
                worker_id=worker_id,
            )

        # Arm 7: Optional executable caller error-handling test (`--caller-cmd`).
        if caller_cmd.strip():
            c_res = _run_trials(
                caller_cmd.strip(),
                slot_dir=slot_dir,
                cache_dir=cache_dir,
                timeout_sec=timeout_sec,
                oracle=None,
                trials=1,
            )
            c_ok = int(c_res["exit_code"]) == 0 and not bool(c_res["timed_out"])
            arms["arm7_caller_audit"] = {
                "arm_passed": c_ok,
                "notes": scrub_text(caller_audit.strip()[:600]),
                "cmd_result": c_res,
            }
            if not c_ok:
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
                    caller_cmd=caller_cmd,
                    sibling_cmd=sibling_cmd,
                    baseline_suite=baseline_suite,
                    arms=arms,
                    passed=False,
                    reason=f"Arm 7 (--caller-cmd) failed caller error-return check (exit={c_res['exit_code']}).",
                    worker_id=worker_id,
                )

        # Arm 8: Optional executable sibling-entrypoint symmetry test (`--sibling-cmd`).
        if sibling_cmd.strip():
            s_res = _run_trials(
                sibling_cmd.strip(),
                slot_dir=slot_dir,
                cache_dir=cache_dir,
                timeout_sec=timeout_sec,
                oracle=eff_oracle,
                trials=1,
            )
            s_ok = int(s_res["defect_hits"]) == 0 and int(s_res["exit_code"]) == 0 and not bool(s_res["timed_out"])
            arms["arm8_sibling_audit"] = {
                "arm_passed": s_ok,
                "notes": scrub_text(sibling_audit.strip()[:600]),
                "cmd_result": s_res,
            }
            if not s_ok:
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
                    caller_cmd=caller_cmd,
                    sibling_cmd=sibling_cmd,
                    baseline_suite=baseline_suite,
                    arms=arms,
                    passed=False,
                    reason=f"Arm 8 (--sibling-cmd) failed sibling symmetry check (exit={s_res['exit_code']}, hits={s_res['defect_hits']}).",
                    worker_id=worker_id,
                )

        # Arm 9: `git apply -R` patch-revert re-failure proof (`Trail of Bits` patching-bugs discipline).
        rev_proc = subprocess.run(
            ["git", "-C", str(slot_dir), "apply", "-R", "--whitespace=nowarn", str(patch_path.resolve())],
            capture_output=True,
            text=True,
            env=scrubbed_subprocess_env(),
            check=False,
        )
        if rev_proc.returncode != 0:
            arms["arm9_revert_poc"] = {"arm_passed": False, "stderr": scrub_text(rev_proc.stderr[:240])}
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
                caller_cmd=caller_cmd,
                sibling_cmd=sibling_cmd,
                baseline_suite=baseline_suite,
                arms=arms,
                passed=False,
                reason=f"Arm 9 (`git apply -R`) failed to revert cleanly: {scrub_text(rev_proc.stderr[:180])}",
                worker_id=worker_id,
            )

        _bump_files_mtime(slot_dir, touched_files, watermark_file)
        rev_poc_res = _run_trials(
            str(finding["poc_cmd"]),
            slot_dir=slot_dir,
            cache_dir=cache_dir,
            timeout_sec=timeout_sec,
            oracle=eff_oracle,
            trials=1,
        )
        rev_passed = int(rev_poc_res["defect_hits"]) >= 1
        arms["arm9_revert_poc"] = {**rev_poc_res, "arm_passed": rev_passed}
        if not rev_passed:
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
                caller_cmd=caller_cmd,
                sibling_cmd=sibling_cmd,
                baseline_suite=baseline_suite,
                arms=arms,
                passed=False,
                reason="Arm 9 failed: reverting patch (`git apply -R`) did not re-trigger the PoC defect oracle.",
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
            caller_cmd=caller_cmd,
            sibling_cmd=sibling_cmd,
            baseline_suite=baseline_suite,
            arms=arms,
            passed=True,
            reason="All 9 production patch verification arms passed (including clean-HEAD variant & revert proof); promoted to verified_local.",
            worker_id=worker_id,
        )
    finally:
        if (slot_dir / ".git").exists():
            subprocess.run(["git", "-C", str(slot_dir), "reset", "--hard", "HEAD"], capture_output=True, check=False)
            _clean_slot_preserving_objects(slot_dir, check=False)
            _bump_files_mtime(slot_dir, touched_files, watermark_file)
        fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)
        lock_fh.close()


run_9arm_patch_verification = run_8arm_patch_verification


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
    caller_cmd: str,
    sibling_cmd: str,
    baseline_suite: dict[str, Any],
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
            arms_json, baseline_suite_json, arm7_caller_cmd, arm8_sibling_cmd,
            arm9_revert_poc_json, passed, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            json.dumps(baseline_suite, sort_keys=True),
            scrub_text(caller_cmd.strip()),
            scrub_text(sibling_cmd.strip()),
            json.dumps(arms.get("arm9_revert_poc", {}), sort_keys=True),
            1 if passed else 0,
            now_iso,
        ),
    )
    if passed:
        conn.execute(
            "UPDATE claims SET remediation_state = 'verified_local', updated_at = ? WHERE claim_id = ?",
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
        "remediation_state": "verified_local" if passed else "micropatched",
        "reason": reason,
        "arms": arms,
    }
