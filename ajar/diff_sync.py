"""Differential PR state synchronization for `Code` reviews (`ajar init --diff <base>..<head>`).

Synchronizes a child PR run against `<base>..<head>` (and an optional `--parent-run <run_id>`):
1. Resolves `base_sha` and `head_sha` and extracts exact changed files and line hunks.
2. Re-runs prior confirmed `findings` (`poc_cmd` + `control_cmd`) in `slot-0` at `$0` LLM cost:
   - Still fires -> carried forward with `diff_state = 'kept'`.
   - Mitigated by the PR -> recorded as `status = 'falsified'` (`diff_state = 'closed'`) so
     `Subsystem Dead Ends` stops high-thinking workers from re-reporting fixed bugs.
3. Carries forward prior `certified_bindings` and `dry` controls untouched by `<diff_range>`;
   any touched guard (`dry_control_locus`, `blocker_check_locus`, or changed `file_sha256`) is
   classified `invalidated_guard` and enqueues a high-salience (`reopened_boost = 25`) audit task.
4. Enqueues focused `new` slice tasks (`slice_loc <= 15000`) on modified/added files in `<diff_range>`
   and evaluates deterministic epistemic hooks (`H2`, `H3`, `H7`, `H8`) on changed code.
"""

from __future__ import annotations

import fcntl
import json
import pathlib
import re
import sqlite3
import subprocess
from typing import Any

from ajar import EXIT_USER_ERROR
from ajar.db import (
    AjarError,
    file_locus_sha256,
    infer_subsystem,
    log_event,
    new_id,
    open_run_db,
    utc_now_iso,
)
from ajar.epistemic_hooks import register_epistemic_hook, scan_source_for_epistemic_signals
from ajar.redact import scrub_text, scrubbed_subprocess_env
from ajar.repomap import SOURCE_EXTENSIONS
from ajar.repro_compose import ensure_helpers_runtime
from ajar.repro_source import (
    _acquire_slot,
    _evaluate_defect_fired,
    _prepare_slot_worktree,
    _run_shell_in_slot,
    init_source_mirror,
)

HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse_diff_range_commits(target_dir: pathlib.Path, diff_range: str) -> tuple[str, str, str]:
    """Resolve `diff_range` into `(normalized_spec, base_sha, head_sha)` via `git rev-parse`."""
    spec = diff_range.strip()
    if not spec:
        raise AjarError("Empty --diff range.", EXIT_USER_ERROR)
    if "..." in spec:
        base_ref, _, head_ref = spec.partition("...")
        head_ref = head_ref.strip() or "HEAD"
        norm_spec = f"{base_ref.strip()}...{head_ref}"
    elif ".." in spec:
        base_ref, _, head_ref = spec.partition("..")
        head_ref = head_ref.strip() or "HEAD"
        norm_spec = f"{base_ref.strip()}..{head_ref}"
    else:
        base_ref = spec
        head_ref = "HEAD"
        norm_spec = f"{base_ref}..HEAD"

    env = scrubbed_subprocess_env()
    r_base = subprocess.run(
        ["git", "-C", str(target_dir), "rev-parse", "--verify", base_ref.strip()],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    r_head = subprocess.run(
        ["git", "-C", str(target_dir), "rev-parse", "--verify", head_ref.strip()],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if r_base.returncode != 0 or r_head.returncode != 0:
        err = (r_base.stderr or r_head.stderr or "unknown git rev-parse error").strip()
        raise AjarError(f"Invalid --diff range {diff_range!r} in {target_dir}: {err[:200]}", EXIT_USER_ERROR)

    return (norm_spec, r_base.stdout.strip(), r_head.stdout.strip())


def extract_diff_hunks(target_dir: pathlib.Path, norm_spec: str) -> dict[str, list[tuple[int, int]]]:
    """Return mapping `rel_path -> [(start_line, end_line), ...]` for changed files in `norm_spec`."""
    res = subprocess.run(
        ["git", "-C", str(target_dir), "diff", "--unified=0", "--no-color", norm_spec],
        capture_output=True,
        text=True,
        env=scrubbed_subprocess_env(),
        check=False,
    )
    if res.returncode != 0:
        raise AjarError(f"`git diff {norm_spec}` failed: {res.stderr.strip()[:200]}", EXIT_USER_ERROR)

    changed: dict[str, list[tuple[int, int]]] = {}
    cur_file: str | None = None
    for line in res.stdout.splitlines():
        if line.startswith("+++ "):
            raw_b = line[4:].split("\t", 1)[0].strip()
            if raw_b == "/dev/null":
                cur_file = None
            else:
                cur_file = re.sub(r"^b/", "", raw_b)
                changed.setdefault(cur_file, [])
        elif line.startswith("--- ") and cur_file is None:
            raw_a = line[4:].split("\t", 1)[0].strip()
            if raw_a != "/dev/null":
                rel_a = re.sub(r"^a/", "", raw_a)
                changed.setdefault(rel_a, [(1, 1)])
        elif line.startswith("@@ ") and cur_file is not None:
            m = HUNK_HEADER_RE.match(line)
            if m:
                old_start = int(m.group(1))
                old_cnt = int(m.group(2) if m.group(2) is not None else 1)
                new_start = int(m.group(3))
                new_cnt = int(m.group(4) if m.group(4) is not None else 1)
                s_ln = max(1, min(old_start, new_start))
                e_ln = max(s_ln, new_start + max(1, new_cnt) - 1, old_start + max(1, old_cnt) - 1)
                changed[cur_file].append((s_ln, e_ln))
    return changed


def _locus_touched_by_diff(locus: str, changed_hunks: dict[str, list[tuple[int, int]]]) -> bool:
    """Return True if `locus` (`path/to/file.py[:start[-end]]`) intersects any modified hunk."""
    raw = (locus or "").strip()
    if not raw:
        return False
    parts = raw.split(":", 1)
    rel_file = parts[0].strip().lstrip("./")
    if rel_file not in changed_hunks:
        return False
    hunks = changed_hunks[rel_file]
    if len(parts) == 1 or not parts[1].strip() or not hunks:
        return True
    m = re.match(r"^(\d+)(?:-(\d+))?", parts[1].strip())
    if not m:
        return True
    l_start = int(m.group(1))
    l_end = int(m.group(2) or l_start)
    # Allow a 3-line safety margin around shifted hunks.
    for h_start, h_end in hunks:
        if not (l_end + 3 < h_start or l_start - 3 > h_end):
            return True
    return False


def sync_pr_differential_state(
    conn: sqlite3.Connection,
    *,
    run_dir: pathlib.Path,
    target_dir: pathlib.Path,
    diff_range: str,
    git_repo_dir: pathlib.Path | None = None,
    parent_run_id: str | None = None,
    ajar_home: pathlib.Path | str | None = None,
) -> dict[str, Any]:
    """Synchronize PR differential state (`kept | closed | invalidated_guard | new`)."""
    repo_dir = git_repo_dir or target_dir
    norm_spec, base_sha, head_sha = parse_diff_range_commits(repo_dir, diff_range)
    changed_hunks = extract_diff_hunks(repo_dir, norm_spec)
    now_iso = utc_now_iso()

    conn.execute(
        """
        UPDATE runs
        SET diff_range = ?, base_sha = ?, head_sha = ?, parent_run_id = ?
        """,
        (norm_spec, base_sha, head_sha, (parent_run_id or "").strip()),
    )

    kept_findings: list[str] = []
    closed_findings: list[str] = []
    kept_dry_tasks: list[str] = []
    invalidated_guards: list[dict[str, str]] = []
    reopened_task_ids: list[str] = []
    new_task_ids: list[str] = []

    if parent_run_id and parent_run_id.strip():
        parent_conn = open_run_db(parent_run_id.strip(), create=False, ajar_home=ajar_home)
        try:
            # 1. Re-verify prior confirmed findings in `slot-0` at `$0` LLM cost.
            prior_findings = parent_conn.execute(
                """
                SELECT f.*, c.surface_id, c.proposer_worker_id, c.seeded_by_human,
                       c.subsystem, c.mechanism, c.mechanism_key,
                       c.falsification_prediction, c.falsification_test, c.falsifier_worker_id
                FROM findings f
                JOIN claims c ON f.claim_id = c.claim_id
                ORDER BY f.created_at ASC
                """
            ).fetchall()

            if prior_findings:
                helpers_dir = ensure_helpers_runtime(run_dir)
                mirror_dir = init_source_mirror(run_dir, target_dir)
                repro_dir = run_dir / "repro"
                slot_idx, lock_fh = _acquire_slot(repro_dir)
                slot_dir = repro_dir / f"slot-{slot_idx}"
                cache_dir = repro_dir / f"cache-{slot_idx}"
                cache_dir.mkdir(parents=True, exist_ok=True)
                try:
                    for pf in prior_findings:
                        _prepare_slot_worktree(mirror_dir, slot_dir)
                        oracle_raw = pf["oracle_json"] if "oracle_json" in pf.keys() else "{}"
                        try:
                            oracle = json.loads(oracle_raw or "{}")
                            if not oracle:
                                oracle = None
                        except json.JSONDecodeError:
                            oracle = None

                        poc_res = _run_shell_in_slot(
                            str(pf["poc_cmd"]),
                            slot_dir=slot_dir,
                            cache_dir=cache_dir,
                            timeout_sec=45,
                            helpers_dir=helpers_dir,
                        )
                        poc_fired = _evaluate_defect_fired(
                            poc_res["exit_code"], poc_res["stdout"], poc_res["stderr"], poc_res["timed_out"], oracle
                        )
                        subprocess.run(["git", "-C", str(slot_dir), "reset", "--hard", "HEAD"], capture_output=True, check=False)
                        subprocess.run(["git", "-C", str(slot_dir), "clean", "-fdx"], capture_output=True, check=False)

                        ctrl_res = _run_shell_in_slot(
                            str(pf["control_cmd"]),
                            slot_dir=slot_dir,
                            cache_dir=cache_dir,
                            timeout_sec=45,
                            helpers_dir=helpers_dir,
                        )
                        ctrl_fired = _evaluate_defect_fired(
                            ctrl_res["exit_code"], ctrl_res["stdout"], ctrl_res["stderr"], ctrl_res["timed_out"], oracle
                        )
                        still_vulnerable = poc_fired and (not ctrl_fired) and ctrl_res["exit_code"] == 0

                        new_cid = new_id("clm")
                        if still_vulnerable:
                            new_fid = new_id("fnd")
                            conn.execute(
                                """
                                INSERT INTO claims(
                                    claim_id, surface_id, proposer_worker_id, seeded_by_human,
                                    title, subsystem, locus, mechanism, mechanism_key, severity,
                                    falsification_prediction, falsification_test, status,
                                    falsifier_worker_id, falsify_notes, research_state,
                                    evidence_state, diff_state, created_at, updated_at
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'reproduced', ?, ?, 'confirmed', 'reproduced', 'kept', ?, ?)
                                """,
                                (
                                    new_cid,
                                    pf["surface_id"],
                                    pf["proposer_worker_id"],
                                    pf["seeded_by_human"],
                                    pf["title"],
                                    pf["subsystem"],
                                    pf["locus"],
                                    pf["mechanism"],
                                    pf["mechanism_key"],
                                    pf["severity"],
                                    pf["falsification_prediction"],
                                    pf["falsification_test"],
                                    pf["falsifier_worker_id"] or "diff-sync-verifier",
                                    f"Carried forward from {parent_run_id}:{pf['finding_id']} (PoC still triggers on {head_sha[:8]}).",
                                    now_iso,
                                    now_iso,
                                ),
                            )
                            conn.execute(
                                """
                                INSERT INTO findings(
                                    finding_id, claim_id, title, severity, locus, root_cause,
                                    poc_cmd, control_cmd, micropatch_path, micropatch_diff,
                                    arm1_clean_poc_json, arm2_clean_ctrl_json,
                                    arm3_patch_poc_json, arm4_patch_ctrl_json,
                                    oracle_json, diff_state, attribution, created_at
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'kept', ?, ?)
                                """,
                                (
                                    new_fid,
                                    new_cid,
                                    pf["title"],
                                    pf["severity"],
                                    pf["locus"],
                                    pf["root_cause"],
                                    pf["poc_cmd"],
                                    pf["control_cmd"],
                                    pf["micropatch_path"],
                                    pf["micropatch_diff"],
                                    json.dumps({**poc_res, "arm_passed": True}, sort_keys=True),
                                    json.dumps({**ctrl_res, "arm_passed": True}, sort_keys=True),
                                    pf["arm3_patch_poc_json"],
                                    pf["arm4_patch_ctrl_json"],
                                    oracle_raw or "{}",
                                    pf["attribution"],
                                    now_iso,
                                ),
                            )
                            kept_findings.append(new_fid)
                        else:
                            conn.execute(
                                """
                                INSERT INTO claims(
                                    claim_id, surface_id, proposer_worker_id, seeded_by_human,
                                    title, subsystem, locus, mechanism, mechanism_key, severity,
                                    falsification_prediction, falsification_test, status,
                                    falsifier_worker_id, falsify_notes, falsify_control_locus,
                                    research_state, evidence_state, diff_state, created_at, updated_at
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'falsified', 'diff-sync-verifier', ?, ?, 'rejected_during_research', 'falsified', 'closed', ?, ?)
                                """,
                                (
                                    new_cid,
                                    pf["surface_id"],
                                    pf["proposer_worker_id"],
                                    pf["seeded_by_human"],
                                    pf["title"],
                                    pf["subsystem"],
                                    pf["locus"],
                                    pf["mechanism"],
                                    pf["mechanism_key"],
                                    pf["severity"],
                                    pf["falsification_prediction"],
                                    pf["falsification_test"],
                                    f"Closed by PR diff {norm_spec}: prior PoC ({pf['finding_id']}) no longer triggers defect oracle on {head_sha[:8]}.",
                                    pf["locus"],
                                    now_iso,
                                    now_iso,
                                ),
                            )
                            closed_findings.append(str(pf["finding_id"]))
                finally:
                    if (slot_dir / ".git").exists():
                        subprocess.run(["git", "-C", str(slot_dir), "reset", "--hard", "HEAD"], capture_output=True, check=False)
                        subprocess.run(["git", "-C", str(slot_dir), "clean", "-fdx"], capture_output=True, check=False)
                    fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)
                    lock_fh.close()

            # 2. Check prior `certified_bindings` (`kept` vs `invalidated_guard`).
            for pb in parent_conn.execute("SELECT * FROM certified_bindings WHERE valid = 1").fetchall():
                cur_sha, l_start, l_end = file_locus_sha256(target_dir, str(pb["locus"]))
                if cur_sha and cur_sha == pb["file_sha256"] and not _locus_touched_by_diff(str(pb["locus"]), changed_hunks):
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO certified_bindings(
                            binding_id, task_id, name, value, locus,
                            file_sha256, line_start, line_end, valid, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                        """,
                        (
                            new_id("bind"),
                            pb["task_id"],
                            pb["name"],
                            pb["value"],
                            pb["locus"],
                            cur_sha,
                            l_start,
                            l_end,
                            now_iso,
                            now_iso,
                        ),
                    )
                else:
                    invalidated_guards.append({"kind": "binding", "name": str(pb["name"]), "locus": str(pb["locus"])})

            # 3. Check prior `dry` & `conditional_blocked` tasks + `guarded_by_locus` primitives.
            for pt in parent_conn.execute(
                "SELECT * FROM tasks WHERE status IN ('dry', 'conditional_blocked')"
            ).fetchall():
                guard_loc = str(pt["dry_control_locus"] or pt["blocker_check_locus"] or "")
                task_loc = str(pt["locus"] or "")
                if _locus_touched_by_diff(guard_loc, changed_hunks) or _locus_touched_by_diff(task_loc, changed_hunks):
                    rtid = new_id("task")
                    target_loc = guard_loc or task_loc
                    sub = infer_subsystem(target_loc)
                    conn.execute(
                        """
                        INSERT INTO tasks(
                            task_id, kind, direction, title, subsystem, locus, priority,
                            status, salience_score, reopened_boost, diff_state, summary, created_at, updated_at
                        ) VALUES (?, 'investigate', 'inside_out', ?, ?, ?, 'critical', 'open', 92, 25, 'invalidated_guard', ?, ?, ?)
                        """,
                        (
                            rtid,
                            f"Re-audit PR-modified guard {target_loc} (prior {pt['status']} task {pt['task_id']})",
                            sub,
                            target_loc,
                            scrub_text(
                                f"PR diff {norm_spec} modified guard/locus {target_loc} previously relied upon by {pt['task_id']}."
                            ),
                            now_iso,
                            now_iso,
                        ),
                    )
                    invalidated_guards.append({"kind": "task_guard", "prior_task_id": str(pt["task_id"]), "locus": target_loc})
                    reopened_task_ids.append(rtid)
                elif pt["status"] == "dry":
                    dtid = new_id("task")
                    conn.execute(
                        """
                        INSERT INTO tasks(
                            task_id, kind, direction, title, subsystem, locus, priority,
                            status, dry_control_locus, dry_control_reason, salience_score,
                            diff_state, summary, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'dry', ?, ?, 20, 'kept', ?, ?, ?)
                        """,
                        (
                            dtid,
                            pt["kind"],
                            pt["direction"] if "direction" in pt.keys() else "outside_in",
                            pt["title"],
                            pt["subsystem"],
                            pt["locus"],
                            pt["priority"],
                            pt["dry_control_locus"],
                            pt["dry_control_reason"],
                            f"Carried forward untouched dry guard from {parent_run_id}:{pt['task_id']}",
                            now_iso,
                            now_iso,
                        ),
                    )
                    kept_dry_tasks.append(dtid)

            for pp in parent_conn.execute(
                "SELECT * FROM primitives WHERE guarded_by_locus != '' AND chained = 0 AND status != 'dry'"
            ).fetchall():
                gloc = str(pp["guarded_by_locus"])
                new_pid = new_id("prim")
                pp_keys = set(pp.keys())
                conn.execute(
                    """
                    INSERT INTO primitives(
                        primitive_id, surface_id, subsystem, locus, kind, role, trusted_invariant,
                        symbols_json, preconditions, postconditions, guarded_by_locus, guard_assumption,
                        provides_tags_json, requires_tags_json, micropatch_diff, snapshot_id,
                        evidence_cmd, evidence_output, chained, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'active', ?)
                    """,
                    (
                        new_pid,
                        pp["surface_id"],
                        pp["subsystem"],
                        pp["locus"],
                        pp["kind"],
                        pp["role"] if "role" in pp_keys else "capability",
                        pp["trusted_invariant"] if "trusted_invariant" in pp_keys else "",
                        pp["symbols_json"] if "symbols_json" in pp_keys else "[]",
                        pp["preconditions"],
                        pp["postconditions"],
                        gloc,
                        pp["guard_assumption"],
                        pp["provides_tags_json"] if "provides_tags_json" in pp_keys else "[]",
                        pp["requires_tags_json"] if "requires_tags_json" in pp_keys else "[]",
                        pp["micropatch_diff"] if "micropatch_diff" in pp_keys else "",
                        pp["snapshot_id"] if "snapshot_id" in pp_keys else "",
                        pp["evidence_cmd"],
                        pp["evidence_output"],
                        now_iso,
                    ),
                )
                if _locus_touched_by_diff(gloc, changed_hunks):
                    rtid = new_id("task")
                    gsub = infer_subsystem(gloc)
                    conn.execute(
                        """
                        INSERT INTO tasks(
                            task_id, kind, direction, title, subsystem, locus, priority,
                            status, salience_score, reopened_boost, diff_state, summary, created_at, updated_at
                        ) VALUES (?, 'investigate', 'inside_out', ?, ?, ?, 'critical', 'open', 94, 25, 'invalidated_guard', ?, ?, ?)
                        """,
                        (
                            rtid,
                            f"PR modified guard {gloc} protecting inner primitive {new_pid} ({pp['kind']})",
                            gsub,
                            gloc,
                            f"PR diff {norm_spec} modified {gloc} guarding {new_pid}@{pp['locus']}.",
                            now_iso,
                            now_iso,
                        ),
                    )
                    invalidated_guards.append({"kind": "primitive_guard", "primitive_id": new_pid, "locus": gloc})
                    reopened_task_ids.append(rtid)
        finally:
            parent_conn.close()

    # 4. Enqueue focused `new` PR slice tasks (`<= 15000` LoC) for modified/added source files.
    for rel_path, hunks in sorted(changed_hunks.items()):
        fpath = target_dir / rel_path
        if not fpath.is_file() or fpath.suffix.lower() not in SOURCE_EXTENSIONS:
            continue
        src_text = fpath.read_text(encoding="utf-8", errors="ignore")
        loc_count = max(1, len(src_text.splitlines()))
        first_line = hunks[0][0] if hunks else 1
        locus = f"{rel_path}:{first_line}"
        sub = infer_subsystem(rel_path)

        already_queued = conn.execute(
            "SELECT task_id FROM tasks WHERE status = 'open' AND (locus = ? OR locus LIKE ?)",
            (locus, f"{rel_path}:%"),
        ).fetchone()
        tid: str | None = None
        if already_queued is None:
            tid = new_id("task")
            hunk_desc = ", ".join(f"L{s}-L{e}" for s, e in hunks[:4]) or "file changed"
            conn.execute(
                """
                INSERT INTO tasks(
                    task_id, kind, direction, title, subsystem, locus, priority,
                    status, salience_score, slice_loc, diff_state, summary, created_at, updated_at
                ) VALUES (?, 'investigate', 'outside_in', ?, ?, ?, 'high', 'open', 76, ?, 'new', ?, ?, ?)
                """,
                (
                    tid,
                    f"Audit PR diff hunks in {rel_path} ({hunk_desc})",
                    sub,
                    locus,
                    min(15000, loc_count),
                    f"PR diff {norm_spec} modified {rel_path} ({hunk_desc}).",
                    now_iso,
                    now_iso,
                ),
            )
            new_task_ids.append(tid)

        for hcode, directive, kill_r in scan_source_for_epistemic_signals(rel_path, src_text):
            register_epistemic_hook(
                conn,
                hook_code=hcode,
                trigger_cmd="init.diff",
                source_entity_id=tid or rel_path,
                dedup_material=f"{rel_path}:{hcode}",
                subsystem=sub,
                target_locus=locus,
                spawned_task_id=tid,
                directive_text=directive,
                kill_rule=kill_r,
            )

    summary = {
        "diff_range": norm_spec,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "parent_run_id": parent_run_id or "",
        "changed_files": sorted(changed_hunks.keys()),
        "kept_findings": kept_findings,
        "closed_findings": closed_findings,
        "kept_dry_tasks": kept_dry_tasks,
        "invalidated_guards": invalidated_guards,
        "reopened_task_ids": reopened_task_ids,
        "new_task_ids": new_task_ids,
    }
    log_event(conn, "operator", "diff_sync_initialized", parent_run_id or norm_spec, summary)
    return summary
