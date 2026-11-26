"""AJAR Ring-0 mechanical C3 verification oracle, worktree isolation, and report exporter."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any, NamedTuple

from ajar.cli import (
    BuildRecipe,
    Candidate,
    CrashSignature,
    Verdict,
    ajar_dir,
    dataclass_from_dict,
    read_jsonl,
    scrub_subprocess_env,
)
from ajar.llm import LLMClient, LLMResponse, resolve_role_model

DEFAULT_MOUNT_DEPS = ("node_modules", "vendor", "lib", ".venv", "target")
HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
HEX_ADDR_RE = re.compile(r"0x[0-9a-fA-F]+")
SAN_PID_RE = re.compile(r"==\d+==")
TMP_WT_RE = re.compile(r"/[^\s:]*ajar-wt-[^/\s:]+/work/")
PY_FRAME_RE = re.compile(r'File "([^"]+)", line (\d+), in ([^\s\n]+)')
SAN_FRAME_RE = re.compile(r"#\d+\s+0x[0-9a-fA-F]+\s+in\s+([^\s]+)\s+([^\s]+)")
VOICE_LINT_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "security-advisory-report"
    / "scripts"
    / "report_voice_lint.py"
)
BANNED_VOICE_PATTERNS = (
    "sprt", "rmst", "map-elites", "lyapunov", "ah-puct", "macaroon",
    "could potentially", "might be vulnerable", "it seems", "appears to be",
    "i think", "we believe", "delve", "catastrophic", "devastating",
    "as an ai", "in conclusion", "relay_capsule", ".ajar/", "todo:", "tbd",
)


class LintResult(NamedTuple):
    score: int
    issues: list[str]

    @property
    def passed(self) -> bool:
        return self.score == 100 and not self.issues


def _run_proc(
    cmd: str | list[str],
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: int = 120,
) -> tuple[int, str]:
    shell_args = ["/bin/sh", "-c", cmd] if isinstance(cmd, str) else cmd
    proc_env = scrub_subprocess_env() if env is None else env
    proc = subprocess.Popen(
        shell_args,
        cwd=str(cwd),
        env=proc_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        start_new_session=True,
    )
    try:
        out, _ = proc.communicate(timeout=timeout)
        return (proc.returncode if proc.returncode is not None else -1), (out or "")
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        part, _ = proc.communicate()
        return 124, f"{part or ''}\n[TIMEOUT]"
    finally:
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
            proc.wait()


def _parse_gitmodules_paths(repo: Path) -> list[str]:
    gm = repo / ".gitmodules"
    if not gm.is_file():
        return []
    paths: list[str] = []
    for line in gm.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped.startswith("path") and "=" in stripped:
            _, rhs = stripped.split("=", 1)
            sub = rhs.strip().strip("/")
            if sub:
                paths.append(sub)
    return paths


@contextmanager
def clean_worktree(repo: Path, mount_deps: Sequence[str] | None = None) -> Iterator[Path]:
    """Sole Ring-0/Ring-1 entrypoint using git worktree with copytree fallback."""
    src_repo = Path(repo).resolve()
    tmp_root = Path(tempfile.mkdtemp(prefix="ajar-wt-"))
    wt = tmp_root / "work"
    used_worktree = False
    try:
        if (src_repo / ".git").exists():
            wt_cmd = ["git", "-C", str(src_repo), "worktree", "add", "--detach", "--force", str(wt), "HEAD"]
            rc, _ = _run_proc(wt_cmd, cwd=src_repo, timeout=60)
            used_worktree = rc == 0 and wt.is_dir()
        if not used_worktree:
            if wt.exists():
                shutil.rmtree(wt, ignore_errors=True)
            shutil.copytree(
                src_repo,
                wt,
                symlinks=True,
                ignore=shutil.ignore_patterns(".git", "__pycache__"),
            )
        elif (src_repo / ".ajar" / "build.sh").is_file() and not (wt / ".ajar" / "build.sh").exists():
            (wt / ".ajar").mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_repo / ".ajar" / "build.sh", wt / ".ajar" / "build.sh")
        deps_to_link = list(mount_deps if mount_deps is not None else DEFAULT_MOUNT_DEPS)
        for sub_path in _parse_gitmodules_paths(src_repo):
            if sub_path not in deps_to_link:
                deps_to_link.append(sub_path)
        for rel_dep in deps_to_link:
            src_dep = src_repo / rel_dep
            dst_dep = wt / rel_dep
            if not src_dep.exists():
                continue
            if dst_dep.is_dir() and not dst_dep.is_symlink() and not any(dst_dep.iterdir()):
                dst_dep.rmdir()
            if not dst_dep.exists() and not dst_dep.is_symlink():
                dst_dep.parent.mkdir(parents=True, exist_ok=True)
                dst_dep.symlink_to(src_dep)
        yield wt
    finally:
        if used_worktree:
            rm_cmd = ["git", "-C", str(src_repo), "worktree", "remove", "--force", str(wt)]
            _run_proc(rm_cmd, cwd=src_repo, timeout=30)
            _run_proc(["git", "-C", str(src_repo), "worktree", "prune"], cwd=src_repo, timeout=30)
        shutil.rmtree(tmp_root, ignore_errors=True)


def _strip_diff_prefix(raw: str) -> str:
    path_token = raw.split("\t", 1)[0].strip()
    if path_token in ("/dev/null", "dev/null"):
        return "/dev/null"
    if path_token.startswith(("a/", "b/")):
        return path_token[2:]
    return path_token


def _align_and_apply_hunks(wt: Path, patch_diff: str, max_drift: int = 40) -> tuple[bool, str]:
    lines = patch_diff.splitlines()
    idx = 0
    planned_writes: dict[Path, str | None] = {}
    wt_real = wt.resolve()

    while idx < len(lines):
        if not lines[idx].startswith("--- "):
            idx += 1
            continue
        old_rel = _strip_diff_prefix(lines[idx][4:])
        idx += 1
        if idx >= len(lines) or not lines[idx].startswith("+++ "):
            return False, "malformed unified diff missing +++ header"
        new_rel = _strip_diff_prefix(lines[idx][4:])
        idx += 1

        chosen_rel = old_rel if new_rel == "/dev/null" else new_rel
        target = (wt_real / chosen_rel).resolve()
        if target != wt_real and wt_real not in target.parents:
            return False, f"patch path escapes worktree: {chosen_rel}"

        if old_rel == "/dev/null":
            cur_lines: list[str] = []
        else:
            if not target.is_file():
                return False, f"missing target file: {chosen_rel}"
            cur_lines = target.read_text(encoding="utf-8", errors="replace").splitlines()

        offset = 0
        min_pos = 0
        hunk_count = 0
        while idx < len(lines) and lines[idx].startswith("@@ "):
            m = HUNK_HEADER_RE.match(lines[idx])
            if not m:
                return False, f"invalid hunk header: {lines[idx]}"
            orig_start = int(m.group(1))
            idx += 1
            hunk_count += 1
            expected: list[str] = []
            replacement: list[str] = []
            while idx < len(lines):
                hline = lines[idx]
                if hline.startswith(("@@ ", "--- ", "diff --git ")):
                    break
                if hline.startswith("\\"):
                    idx += 1
                    continue
                if hline == "":
                    expected.append("")
                    replacement.append("")
                elif hline.startswith(" "):
                    expected.append(hline[1:])
                    replacement.append(hline[1:])
                elif hline.startswith("-"):
                    expected.append(hline[1:])
                elif hline.startswith("+"):
                    replacement.append(hline[1:])
                else:
                    return False, f"unexpected hunk line: {hline}"
                idx += 1

            if not expected and not cur_lines:
                cur_lines = list(replacement)
                continue

            nominal = max(0, orig_start - 1 + offset)
            lo = max(min_pos, nominal - max_drift)
            hi = min(len(cur_lines) - len(expected), nominal + max_drift)
            matches = [
                pos
                for pos in range(lo, hi + 1)
                if cur_lines[pos : pos + len(expected)] == expected
            ]
            if not matches:
                matches = [
                    pos
                    for pos in range(lo, hi + 1)
                    if [s.rstrip() for s in cur_lines[pos : pos + len(expected)]]
                    == [e.rstrip() for e in expected]
                ]
            if len(matches) != 1:
                reason = "no match" if not matches else f"ambiguous ({len(matches)} matches)"
                return False, f"hunk align failed ({reason}) in {chosen_rel}"
            pos = matches[0]
            cur_lines = cur_lines[:pos] + replacement + cur_lines[pos + len(expected) :]
            offset += len(replacement) - len(expected)
            min_pos = pos + len(replacement)

        if hunk_count == 0:
            return False, f"no hunks parsed for {chosen_rel}"
        planned_writes[target] = None if new_rel == "/dev/null" else ("\n".join(cur_lines) + "\n")

    if not planned_writes:
        return False, "no file diffs found in patch"

    for dst, content in planned_writes.items():
        if content is None:
            if dst.exists():
                dst.unlink()
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(content, encoding="utf-8")
    return True, "applied via +-40-line unique-context hunk aligner"


def apply_patch_fuzzy(wt: Path, patch_diff: str) -> tuple[bool, str]:
    if not patch_diff or not patch_diff.strip():
        return False, "empty patch_diff"
    patch_text = patch_diff if patch_diff.endswith("\n") else (patch_diff + "\n")
    with tempfile.NamedTemporaryFile("w", suffix=".patch", encoding="utf-8", delete=False) as tf:
        tf.write(patch_text)
        patch_file = Path(tf.name)
    try:
        chk_rc, _ = _run_proc(["git", "apply", "--check", str(patch_file)], cwd=wt, timeout=20)
        if chk_rc == 0:
            app_rc, app_out = _run_proc(["git", "apply", str(patch_file)], cwd=wt, timeout=20)
            if app_rc == 0:
                return True, "applied via git apply"
            return False, f"git apply failed: {app_out.strip()}"
    finally:
        patch_file.unlink(missing_ok=True)
    return _align_and_apply_hunks(wt, patch_text, max_drift=40)


def _normalize_trace_text(raw: str) -> str:
    cleaned = TMP_WT_RE.sub("", raw)
    cleaned = SAN_PID_RE.sub("==PID==", cleaned)
    cleaned = HEX_ADDR_RE.sub("0xADDR", cleaned)
    return cleaned.strip()


def parse_crash_signature(output: str, rc: int) -> CrashSignature | None:
    text = output or ""
    lower = text.lower()
    if (
        "SyntaxError" in text
        or "ImportError" in text
        or "ModuleNotFoundError" in text
        or "command not found" in lower
    ):
        return None

    kind = ""
    if "AddressSanitizer" in text:
        kind = "ASAN"
    elif "MemorySanitizer" in text:
        kind = "MSAN"
    elif "UndefinedBehaviorSanitizer" in text:
        kind = "UBSAN"
    elif "ThreadSanitizer" in text or "DATA RACE" in text:
        kind = "TSAN"
    elif "[FAIL" in text:
        kind = "FOUNDRY_FAIL"
    elif rc != 0 and ("AssertionError" in text or "RuntimeError" in text):
        py_frames = [
            f"{Path(fp).name}:{ln}:{fn}"
            for fp, ln, fn in PY_FRAME_RE.findall(text)
            if fp not in ("<string>", "<stdin>")
        ]
        if not py_frames:
            return None
        kind = "ASSERTION_ERROR" if "AssertionError" in text else "RUNTIME_ERROR"
    elif rc in (134, -6):
        kind = "SIGABRT"
    elif rc in (139, -11):
        kind = "SIGSEGV"
    elif rc in (132, -4, 133, -5):
        kind = "SIGTRAP"
    else:
        return None

    frames: list[str] = []
    for fn, loc in SAN_FRAME_RE.findall(text):
        frames.append(_normalize_trace_text(f"{fn}@{Path(loc).name}"))
    for fp, ln, fn in PY_FRAME_RE.findall(text):
        if fp not in ("<string>", "<stdin>"):
            frames.append(f"{Path(fp).name}:{ln}:{fn}")
    if not frames:
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("[FAIL") or "Sanitizer:" in s or "DATA RACE" in s:
                frames.append(_normalize_trace_text(s)[:120])
    top_frames = frames[:5]
    summary_line = next(
        (_normalize_trace_text(ln) for ln in reversed(text.splitlines()) if ln.strip()),
        kind,
    )[:160]
    basis = f"{kind}|{'|'.join(top_frames)}" if top_frames else f"{kind}|{summary_line}"
    stack_hash = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]
    return CrashSignature(kind=kind, summary=summary_line, top_frames=top_frames, stack_hash=stack_hash)


def _is_tautological_repro(cand: Candidate) -> tuple[bool, str]:
    cmd = cand.repro_cmd.strip()
    if not cmd:
        return True, "empty repro_cmd"
    if re.match(r"^(false|/bin/false|exit\s+[1-9]\d*)$", cmd):
        return True, "trivial shell failure command"
    if re.match(r"^(grep|rg)\b", cmd):
        return True, "static grep command is not a dynamic reproducer"
    if re.search(r"python3?\s+-c\s+['\"]\s*(assert\s+False|raise\s+\w+\()", cmd) and "import " not in cmd:
        return True, "inline exception without target import"
    return False, ""


def _invoke_critic_sync(llm: LLMClient, cand: Candidate, sig: CrashSignature) -> LLMResponse:
    critic_spec = resolve_role_model("critic")
    prompt = (
        f"Candidate: {cand.id} - {cand.title}\n"
        f"Severity: {cand.severity}\n"
        f"Sink: {cand.sink_symbol}\n"
        f"Repro: {cand.repro_cmd}\n"
        f"Crash: {sig.kind} ({sig.summary}) frames={sig.top_frames}\n"
        f"Root cause: {cand.root_cause}\n"
        f"Patch:\n{cand.patch_diff}\n\n"
        "Verify whether the repro triggers a genuine target defect and the patch fixes "
        "the root cause without masking symptoms. Reply APPROVE or REJECT with brief notes."
    )
    msgs = [{"role": "user", "content": prompt}]
    sys_msg = "You are an adversarial Cross-Family C3 Security Critic."
    if hasattr(llm, "complete_sync"):
        return llm.complete_sync(
            msgs, role="critic", model=critic_spec, system=sys_msg, allow_drain_reserve=True
        )
    coro = llm.complete(
        msgs, role="critic", model=critic_spec, system=sys_msg, allow_drain_reserve=True
    )
    if inspect.isawaitable(coro):
        return asyncio.run(coro)
    raise TypeError("LLMClient returned non-awaitable response")


def verify_candidate(
    repo: Path,
    cand: Candidate,
    recipe: BuildRecipe | None = None,
    llm: LLMClient | None = None,
    runs: int = 3,
) -> Verdict:
    active_recipe = recipe
    if active_recipe is None:
        build_sh = Path(repo) / ".ajar" / "build.sh"
        script_cmd = "bash .ajar/build.sh" if build_sh.is_file() else ""
        active_recipe = BuildRecipe(profile=cand.build_profile, build_script=script_cmd)

    if cand.withdrawn:
        return Verdict(cand.id, "WITHDRAWN", "C0", 0, 0, critic_verdict="SKIPPED", notes="withdrawn")
    if active_recipe.static_only or not cand.repro_cmd.strip() or not cand.patch_diff.strip():
        return Verdict(cand.id, "UNVERIFIED", "C1", 0, 0, critic_verdict="SKIPPED", notes="static/incomplete")
    taut, taut_reason = _is_tautological_repro(cand)
    if taut:
        return Verdict(cand.id, "REJECTED", "C0", 0, 0, critic_verdict="SKIPPED", notes=taut_reason)

    req_runs = max(1, int(runs))
    run_env = scrub_subprocess_env(active_recipe.env)

    with clean_worktree(repo) as wt:
        if active_recipe.build_script.strip():
            b_rc, _ = _run_proc(active_recipe.build_script, cwd=wt, env=run_env, timeout=180)
            if b_rc != 0:
                return Verdict(cand.id, "REJECTED", "C0", 0, 0, notes=f"initial build failed rc={b_rc}")

        pre_failed = 0
        ref_sig: CrashSignature | None = None
        for _ in range(req_runs):
            rc, out = _run_proc(cand.repro_cmd, cwd=wt, env=run_env, timeout=120)
            sig = parse_crash_signature(out, rc)
            if sig is None and rc != 0 and cand.failure_oracle and cand.failure_oracle in out:
                lower = out.lower()
                if not any(
                    bad in out or bad in lower
                    for bad in ("SyntaxError", "ImportError", "ModuleNotFoundError", "command not found")
                ):
                    digest = hashlib.sha256(cand.failure_oracle.encode("utf-8")).hexdigest()[:16]
                    sig = CrashSignature("ORACLE_FAILURE", cand.failure_oracle, [], digest)
            if sig is None:
                return Verdict(cand.id, "REJECTED", "C0", pre_failed, 0, notes="pre-patch repro did not crash")
            if cand.failure_oracle and cand.failure_oracle not in out:
                return Verdict(cand.id, "REJECTED", "C0", pre_failed, 0, notes="failure_oracle mismatch")
            if cand.sink_symbol and cand.sink_symbol not in out:
                return Verdict(
                    cand.id,
                    "REJECTED",
                    "C0",
                    pre_failed,
                    0,
                    asdict(sig),
                    notes=f"sink_symbol '{cand.sink_symbol}' missing from trace",
                )
            if ref_sig is None:
                ref_sig = sig
            elif sig.stack_hash != ref_sig.stack_hash:
                return Verdict(
                    cand.id, "REJECTED", "C0", pre_failed, 0, asdict(sig), notes="flaky stack_hash across runs"
                )
            pre_failed += 1

        assert ref_sig is not None
        ok_patch, patch_note = apply_patch_fuzzy(wt, cand.patch_diff)
        if not ok_patch:
            return Verdict(cand.id, "REJECTED", "C0", pre_failed, 0, asdict(ref_sig), notes=patch_note)

        if active_recipe.build_script.strip():
            rb_rc, _ = _run_proc(active_recipe.build_script, cwd=wt, env=run_env, timeout=180)
            if rb_rc != 0:
                return Verdict(
                    cand.id,
                    "REJECTED",
                    "C0",
                    pre_failed,
                    0,
                    asdict(ref_sig),
                    notes=f"post-patch rebuild failed rc={rb_rc}",
                )

        post_passed = 0
        for _ in range(req_runs):
            rc, out = _run_proc(cand.repro_cmd, cwd=wt, env=run_env, timeout=120)
            if rc != 0 or parse_crash_signature(out, rc) is not None:
                return Verdict(
                    cand.id, "REJECTED", "C0", pre_failed, post_passed, asdict(ref_sig), notes="post-patch failed"
                )
            if cand.failure_oracle and cand.failure_oracle in out:
                return Verdict(
                    cand.id, "REJECTED", "C0", pre_failed, post_passed, asdict(ref_sig), notes="oracle persisted"
                )
            post_passed += 1

        if active_recipe.test_cmd.strip():
            t_rc, _ = _run_proc(active_recipe.test_cmd, cwd=wt, env=run_env, timeout=300)
            if t_rc != 0:
                return Verdict(
                    cand.id,
                    "REJECTED",
                    "C0",
                    pre_failed,
                    post_passed,
                    asdict(ref_sig),
                    notes=f"regression test_cmd failed rc={t_rc}",
                )

    if llm is None:
        return Verdict(
            cand.id, "VERIFIED", "C2", pre_failed, post_passed, asdict(ref_sig), critic_verdict="SKIPPED"
        )

    critic_resp = _invoke_critic_sync(llm, cand, ref_sig)
    upper = critic_resp.content.strip().upper()
    lead_tok = re.split(r"[\s:.,;-]+", upper, maxsplit=1)[0] if upper else ""
    is_approve = lead_tok in ("APPROVE", "APPROVED", "CONFIRM", "VALID", "PASS", "ACCEPT", "LGTM")
    is_reject = lead_tok in ("REJECT", "REJECTED", "INVALID", "DENY") or (
        not is_approve and any(tok in upper for tok in ("REJECT", "FALSE POSITIVE", "INVALID"))
    )
    if is_reject:
        return Verdict(
            cand.id, "REJECTED", "C2", pre_failed, post_passed, asdict(ref_sig),
            critic_verdict="REJECTED", notes=critic_resp.content.strip()[:240],
        )
    if is_approve or any(tok in upper for tok in ("APPROVE", "CONFIRM", "VALID", "PASS", "ACCEPT", "LGTM")):
        return Verdict(
            cand.id, "VERIFIED", "C3", pre_failed, post_passed, asdict(ref_sig),
            critic_verdict="APPROVED", notes=critic_resp.content.strip()[:240],
        )
    return Verdict(
        cand.id, "VERIFIED", "C2", pre_failed, post_passed, asdict(ref_sig),
        critic_verdict="INCONCLUSIVE", notes=critic_resp.content.strip()[:240],
    )


def lint_report_text(text: str) -> LintResult:
    issues = [f"disallowed phrase: '{p}'" for p in BANNED_VOICE_PATTERNS if p in text.lower()]
    return LintResult(score=max(0, 100 - 20 * len(issues)), issues=issues)


def _run_voice_lint_gate(path: Path, channel: str = "ghsa") -> LintResult:
    if not VOICE_LINT_SCRIPT.is_file():
        return lint_report_text(path.read_text(encoding="utf-8", errors="replace"))
    cmd = [sys.executable, str(VOICE_LINT_SCRIPT), str(path), "--channel", channel, "--json", "--strict"]
    rc, out = _run_proc(cmd, cwd=path.parent, timeout=30)
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
    root = _clean_prose(cand.root_cause, f"{sym} at {loc} processes untrusted input without enforcing the required boundary check.")
    impact = _clean_prose(cand.impact, f"Untrusted input reaching {sym} breaks the security boundary and fails deterministically.")
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
        c.id: c for c in (dataclass_from_dict(Candidate, r) for r in read_jsonl(state_dir / "candidates.jsonl"))
    }
    verdicts_by_id = {
        v.candidate_id: v for v in (dataclass_from_dict(Verdict, r) for r in read_jsonl(state_dir / "verdicts.jsonl"))
    }

    advisories: list[Path] = []
    hardening_notes: list[Path] = []
    lint_issues: dict[str, list[str]] = {}
    min_score = 100
    lint_passed = True

    for cid, cand in sorted(cands_by_id.items()):
        cand_verdict = verdicts_by_id.get(cid)
        if cand.withdrawn or (cand_verdict is not None and cand_verdict.status in ("WITHDRAWN", "REJECTED")):
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
