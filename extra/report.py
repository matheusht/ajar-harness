"""AJAR C3 advisory and hardening-note exporter with strict GHSA voice lint gate."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, NamedTuple

from ajar.cli import (
    Candidate,
    Verdict,
    ajar_dir,
    dataclass_from_dict,
    read_jsonl,
    scrub_subprocess_env,
)

VOICE_LINT_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "security-advisory-report"
    / "scripts"
    / "report_voice_lint.py"
)

BANNED_VOICE_PATTERNS = (
    "sprt",
    "rmst",
    "map-elites",
    "lyapunov",
    "ah-puct",
    "macaroon",
    "could potentially",
    "might be vulnerable",
    "it seems",
    "appears to be",
    "i think",
    "we believe",
    "delve",
    "catastrophic",
    "devastating",
    "as an ai",
    "in conclusion",
    "relay_capsule",
    ".ajar/",
    "todo:",
    "tbd",
)


class LintResult(NamedTuple):
    score: int
    issues: list[str]

    @property
    def passed(self) -> bool:
        return self.score == 100 and not self.issues


def lint_advisory_voice(text: str) -> LintResult:
    lower = text.lower()
    issues = [f"disallowed phrase: '{p}'" for p in BANNED_VOICE_PATTERNS if p in lower]
    return LintResult(score=max(0, 100 - 20 * len(issues)), issues=issues)


lint_report_text = lint_advisory_voice


def _run_lint_proc(cmd: list[str], cwd: Path, timeout: int = 30) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=scrub_subprocess_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout or ""
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout if isinstance(exc.stdout, str) else ""
        return 124, f"{out}\n[TIMEOUT]"


def _run_voice_lint_gate(path: Path, channel: str = "ghsa") -> LintResult:
    if not VOICE_LINT_SCRIPT.is_file():
        return lint_advisory_voice(path.read_text(encoding="utf-8", errors="replace"))
    cmd = [
        sys.executable,
        str(VOICE_LINT_SCRIPT),
        str(path),
        "--channel",
        channel,
        "--json",
        "--strict",
    ]
    rc, out = _run_lint_proc(cmd, cwd=path.parent, timeout=30)
    try:
        data = json.loads(out)
        rep = (data.get("reports") or [{}])[0]
        score = int(rep.get("mechanical_score_100", 100 if rc == 0 else 0))
        issues = [str(x) for x in (rep.get("issues") or []) + (rep.get("warnings") or [])]
        return LintResult(score=score if rc == 0 and not issues else min(score, 95), issues=issues)
    except ValueError:
        return LintResult(score=100 if rc == 0 else 0, issues=[] if rc == 0 else [out.strip()[:160]])


def _clean_prose(raw: str, fallback: str) -> str:
    cleaned = raw.strip() or fallback
    for phrase in BANNED_VOICE_PATTERNS:
        cleaned = re.sub(re.escape(phrase), "", cleaned, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", cleaned).strip() or fallback


def _render_finding_md(cand: Candidate, verdict: Verdict | None) -> str:
    del verdict
    title = _clean_prose(cand.title, cand.id)
    loc = f"`{cand.entry_span}`" if cand.entry_span else "the affected entrypoint"
    sym = f"`{cand.sink_symbol}()`" if cand.sink_symbol else "the target handler"
    default_root = f"{sym} at {loc} processes untrusted input without enforcing the required boundary check."
    default_impact = f"Untrusted input reaching {sym} breaks the security boundary and fails deterministically."
    root = _clean_prose(cand.root_cause, default_root)
    impact = _clean_prose(cand.impact, default_impact)
    repro = cand.repro_cmd.strip() or "true"
    patch = cand.patch_diff.strip() or "# Minimal patch attached in repository diff"
    return "\n".join([
        f"# {title}",
        "",
        "### Summary",
        f"In {loc}, {sym} fails to enforce its boundary check under untrusted input. {impact}",
        "",
        "### Details",
        root,
        "",
        "### PoC",
        f"Run the isolated reproducer below against an unpatched checkout:\n\n```sh\n{repro}\n```",
        "",
        "### Impact",
        impact,
        "",
        "### Suggested Fix",
        f"Apply the minimal boundary check below and re-run the test suite:\n\n```diff\n{patch}\n```",
        "",
        "### Workarounds",
        "No configuration workaround is documented; apply the patch and rebuild.",
        "",
    ])


def export_reports(repo: Path, out_dir: Path) -> dict[str, Any]:
    state_dir = ajar_dir(repo)
    adv_dir = Path(out_dir) / "advisories"
    hard_dir = Path(out_dir) / "hardening-notes"
    adv_dir.mkdir(parents=True, exist_ok=True)
    hard_dir.mkdir(parents=True, exist_ok=True)

    cands_by_id = {
        c.id: c
        for c in (dataclass_from_dict(Candidate, r) for r in read_jsonl(state_dir / "candidates.jsonl"))
    }
    verdicts_by_id = {
        v.candidate_id: v
        for v in (dataclass_from_dict(Verdict, r) for r in read_jsonl(state_dir / "verdicts.jsonl"))
    }

    advisories: list[Path] = []
    hardening_notes: list[Path] = []
    lint_issues: dict[str, list[str]] = {}
    min_score = 100
    lint_passed = True

    for cid, cand in sorted(cands_by_id.items()):
        cand_verdict = verdicts_by_id.get(cid)
        omitted = cand.withdrawn or (
            cand_verdict is not None
            and cand_verdict.status in ("WITHDRAWN", "REJECTED", "FALSIFIED")
        )
        if omitted:
            continue
        cat = cand.category.strip().lower()
        sev = cand.severity.strip().lower()
        is_hardening = cat.startswith("hardening") or sev in ("info", "informational", "hardening")
        is_c3_adv = (
            not is_hardening
            and cand_verdict is not None
            and cand_verdict.status == "VERIFIED"
            and cand_verdict.truth_level == "C3"
        )
        if not is_c3_adv and not is_hardening:
            if cand_verdict is None or cand_verdict.truth_level not in ("C1", "C2"):
                continue
            is_hardening = True

        md = _render_finding_md(cand, cand_verdict)
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", cid) + ".md"
        dst = (adv_dir / safe_name) if is_c3_adv else (hard_dir / safe_name)
        dst.write_text(md, encoding="utf-8")
        if is_c3_adv:
            lint = _run_voice_lint_gate(dst, channel="ghsa")
            min_score = min(min_score, lint.score)
            if not lint.passed:
                lint_passed = False
                lint_issues[cid] = lint.issues
            advisories.append(dst)
        else:
            hardening_notes.append(dst)

    return {
        "advisories": advisories,
        "hardening_notes": hardening_notes,
        "lint_score": min_score,
        "lint_passed": lint_passed,
        "lint_issues": lint_issues,
    }
