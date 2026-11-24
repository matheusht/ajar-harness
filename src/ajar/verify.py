"""Deterministic Clean-Room Judge (`ajar prove` & `ajar critique` — Red/Green, Wrong-Bug Guard, D5 Races, 4x3 Matrix)."""

from __future__ import annotations

import shlex
from pathlib import Path

from ajar.reality import record_falsified_hypothesis
from ajar.schemas import (
    DIAGONAL_REQUIRED,
    Finding,
    ajar_dir,
    append_jsonl,
    evaluate_kill_matrix,
)
from ajar.worktree import BUILD_PROFILES, clean_worktree, run_hermetic


def _matches_claimed_sink(finding: Finding, combined_output: str) -> bool:
    """Prevent OpenAI's documented 10% 'wrong-bug trap': trace output must implicate the claimed sink."""
    tokens = [finding.sink_symbol.strip()]
    if finding.entry_to_sink:
        sink_leaf = Path(finding.entry_to_sink[-1].split(":")[0]).stem
        if sink_leaf:
            tokens.append(sink_leaf)
    tokens = [t for t in tokens if t]
    if not tokens:
        return True
    return any(tok in combined_output for tok in tokens)


def _run_concurrency_red_gate(
    wt: Path,
    repro_script: str,
    profile: str,
    dep_env: dict[str, str],
    mode: str,
    trials: int,
    min_hits: int,
) -> tuple[bool, int, str]:
    """D5 Concurrency Gate: `2/2` deterministic (`TSan`/`rr`) OR `>=min_hits/trials` concurrent vs `0/trials` serial."""
    if mode == "deterministic":
        outputs: list[str] = []
        for idx in range(2):
            env = dict(dep_env)
            env["TSAN_OPTIONS"] = "halt_on_error=1:second_deadlock_stack=1"
            env["AJAR_TRIAL"] = str(idx)
            res = run_hermetic(repro_script, cwd=wt, profile=profile, extra_env=env)
            outputs.append(res.stderr + "\n" + res.stdout)
            if res.returncode == 0 or res.returncode == 124:
                return False, res.returncode, f"deterministic_concurrency_failed_on_run_{idx + 1}"
        return True, 1, "\n".join(outputs)

    if mode == "statistical":
        conc_hits = 0
        serial_hits = 0
        sample_trace = ""
        for idx in range(trials):
            c_env = {**dep_env, "AJAR_SERIAL_CONTROL": "0", "AJAR_TRIAL": str(idx)}
            c_res = run_hermetic(repro_script, cwd=wt, profile=profile, extra_env=c_env)
            if c_res.returncode not in (0, 124):
                conc_hits += 1
                sample_trace = c_res.stderr + "\n" + c_res.stdout
            s_env = {**dep_env, "AJAR_SERIAL_CONTROL": "1", "AJAR_TRIAL": str(idx)}
            s_res = run_hermetic(repro_script, cwd=wt, profile=profile, extra_env=s_env)
            if s_res.returncode not in (0, 124):
                serial_hits += 1
        ok = conc_hits >= min_hits and serial_hits == 0
        detail = f"statistical_race(concurrent={conc_hits}/{trials}, serial_control={serial_hits}/{trials})\n{sample_trace}"
        return ok, (1 if ok else 0), detail

    raise ValueError(f"Unsupported concurrency_mode {mode!r}; expected 'deterministic' or 'statistical'")


def prove_finding(
    repo: Path,
    finding: Finding,
    test_cmd: str | None = None,
    concurrency_mode: str | None = None,
    trials: int = 50,
    min_hits: int = 5,
    mount_deps: list[Path] | None = None,
) -> Finding:
    """Verify a candidate finding inside an ephemeral clean worktree (`Red -> Wrong-Bug Check -> Patch Green -> 4x3`)."""
    if finding.build_profile not in BUILD_PROFILES:
        finding.status = "REJECTED_PROFILE"
        finding.notes = f"Invalid build_profile={finding.build_profile!r}"
        return finding

    with clean_worktree(repo, mount_deps=mount_deps) as (wt, dep_env):
        if concurrency_mode:
            red_ok, red_rc, red_trace = _run_concurrency_red_gate(
                wt, finding.repro_script, finding.build_profile, dep_env, concurrency_mode, trials, min_hits
            )
        else:
            red_res = run_hermetic(
                finding.repro_script, cwd=wt, profile=finding.build_profile, extra_env=dep_env
            )
            red_rc = red_res.returncode
            red_trace = red_res.stderr + "\n" + red_res.stdout
            red_ok = red_rc not in (0, 124)

        finding.red_rc = red_rc
        if not red_ok:
            finding.status = "KILLED"
            finding.notes = f"Red reproduction failed to trigger on clean HEAD (rc={red_rc}): {red_trace[-240:]}"
            record_falsified_hypothesis(repo, f"`{finding.id}` ({finding.title}): failed clean Red repro.")
            append_jsonl(ajar_dir(repo) / "findings.jsonl", finding.to_dict())
            return finding

        if not _matches_claimed_sink(finding, red_trace):
            finding.status = "REJECTED_WRONG_BUG"
            finding.notes = f"PoC crashed/triggered outside claimed sink {finding.sink_symbol!r}: {red_trace[-240:]}"
            record_falsified_hypothesis(
                repo, f"`{finding.id}` hit wrong-bug trap (claimed `{finding.sink_symbol}`, trace differed)."
            )
            append_jsonl(ajar_dir(repo) / "findings.jsonl", finding.to_dict())
            return finding

        finding.kill_matrix.setdefault("controllability:clean_replay", "VERIFIED")
        finding.kill_matrix.setdefault("boundary_validity:shipped_profile", "VERIFIED")

        if finding.patch_diff.strip():
            patch_file = wt / ".ajar-candidate.patch"
            patch_file.write_text(finding.patch_diff, encoding="utf-8")
            apply_res = run_hermetic(f"git apply {shlex.quote(str(patch_file))}", cwd=wt, profile=finding.build_profile)
            if apply_res.returncode != 0:
                finding.status = "REJECTED_BAD_PATCH"
                finding.notes = f"Patch failed git apply: {apply_res.stderr[-240:]}"
                append_jsonl(ajar_dir(repo) / "findings.jsonl", finding.to_dict())
                return finding

            green_res = run_hermetic(
                finding.repro_script, cwd=wt, profile=finding.build_profile, extra_env=dep_env
            )
            finding.green_rc = green_res.returncode
            if green_res.returncode != 0:
                finding.status = "REJECTED_PATCH_INCOMPLETE"
                finding.notes = f"PoC still fails after patch (rc={green_res.returncode})"
                append_jsonl(ajar_dir(repo) / "findings.jsonl", finding.to_dict())
                return finding

            if test_cmd:
                suite_res = run_hermetic(test_cmd, cwd=wt, profile=finding.build_profile, extra_env=dep_env)
                if suite_res.returncode != 0:
                    finding.status = "REJECTED_REGRESSION"
                    finding.notes = f"Upstream test_cmd failed after patch (rc={suite_res.returncode})"
                    append_jsonl(ajar_dir(repo) / "findings.jsonl", finding.to_dict())
                    return finding
            finding.kill_matrix.setdefault("impact_and_patch:clean_replay", "VERIFIED")

        matrix_ok, reasons = evaluate_kill_matrix(finding.kill_matrix)
        if not matrix_ok:
            finding.status = "KILLED" if any(r.startswith("falsified:") for r in reasons) else "NEEDS_CRITIQUE"
            finding.notes = "; ".join(reasons)
            if finding.status == "KILLED":
                record_falsified_hypothesis(repo, f"`{finding.id}` killed by Diagonal Matrix ({finding.notes}).")
        else:
            finding.status = "PROVED"
            finding.notes = "Clean-worktree Red/Green + Wrong-Bug check + 4x3 Diagonal Kill Matrix verified."

        append_jsonl(ajar_dir(repo) / "findings.jsonl", finding.to_dict())
        return finding


def build_cross_family_critic_prompt(finding: Finding) -> str:
    """Construct the adversarial Cross-Family Critic prompt (targets 5.3%–6.5% FP rate)."""
    return (
        "You are an adversarial Cross-Family Security Critic. Attempt to DISPROVE this candidate finding.\n"
        f"- ID / Title: {finding.id} — {finding.title}\n"
        f"- Lens / Profile: {finding.lens} / {finding.build_profile}\n"
        f"- Entry -> Sink: {' -> '.join(finding.entry_to_sink)} (sink={finding.sink_symbol})\n"
        f"- Required Diagonal Cells: {', '.join(DIAGONAL_REQUIRED)}\n"
        "Reply `CRITIC_PASS` ONLY if attacker reachability, payload control, trust-boundary violation, "
        "and minimal patch soundness hold in shipped builds; otherwise reply `CRITIC_KILL: <reason>`."
    )


def critique_finding(repo: Path, finding: Finding, critic_cmd: str | None = None) -> Finding:
    """Run an external Cross-Family Critic command or deterministic rubric check."""
    prompt = build_cross_family_critic_prompt(finding)
    if critic_cmd:
        res = run_hermetic(critic_cmd, cwd=repo, extra_env={"AJAR_CRITIC_PROMPT": prompt}, isolate_net=False)
        out = (res.stdout + "\n" + res.stderr).strip()
        if "CRITIC_KILL" in out or res.returncode != 0:
            finding.critic_verdict = f"KILLED: {out[-200:]}"
            finding.kill_matrix["boundary_validity:static_code"] = "FALSIFIED"
            finding.status = "KILLED"
            record_falsified_hypothesis(repo, f"`{finding.id}` killed by Cross-Family Critic: {out[-160:]}")
        else:
            finding.critic_verdict = "VERIFIED"
            finding.kill_matrix.setdefault("reachability:static_code", "VERIFIED")
    else:
        ok, reasons = evaluate_kill_matrix(finding.kill_matrix)
        finding.critic_verdict = "VERIFIED" if ok else f"INCOMPLETE ({', '.join(reasons)})"
    append_jsonl(ajar_dir(repo) / "findings.jsonl", finding.to_dict())
    return finding
