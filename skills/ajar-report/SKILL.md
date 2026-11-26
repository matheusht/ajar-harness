---
name: ajar-report
description: Export C3-verified advisories and hardening notes via ajar report, enforce DEC-0139 withdrawal hygiene, calibrate severity, and pass 100/100 voice lint.
---

# Ajar Report (`v3.6-Balanced`)

Use this skill to export verified findings from `.ajar/candidates.jsonl` + `.ajar/verdicts.jsonl` into maintainer-ready advisories and hardening notes, and validate outbound prose to `100/100` voice hygiene.

## 1. Export Reports (`ajar report`)

Run `ajar report` after `ajar verify` has written verdicts into `.ajar/verdicts.jsonl`:

```bash
ajar report <repo> --out ./reports
```

`src/ajar/verify.py:export_reports` separates outputs deterministically:

- **`advisories/`:** Exclusively `VERIFIED` `C3` security advisories (passed `3x` attributed pre-patch fail, fuzzy patch apply, mandatory post-patch rebuild, `3x` post-patch pass + upstream `test_cmd`, and Cross-Family Critic `APPROVED`). Each file is checked automatically against `skills/security-advisory-report/scripts/report_voice_lint.py --channel ghsa --strict`.
- **`hardening-notes/`:** Verified `C1`/`C2` items (such as `--offline` runs) and explicit `hardening` / `informational` findings.
- **Withdrawn & Rejected Omission (`DEC-0139`):** Any candidate with `withdrawn: true` or verdict `WITHDRAWN` / `REJECTED` is omitted completely from exported deliverables.

## 2. Severity Calibration & Deduplication

Before external handoff, calibrate every advisory against primary external rulings in `skills/references/severity-precedent-corpus.md` and `skills/references/defi-contest-rulings-corpus.md`:

1. **Deduplicate Root Causes:** Merge alternate entry routes that share one underlying defect into a single advisory rather than inflating finding counts.
2. **Precondition Honesty:** Score strictly by proven preconditions and reproduced impact (local/user-interaction preconditions require `AV:L`/`UI:R`; non-default config or operator prerequisites cap severity; never call a crash or OOB read RCE without reproduced control-flow execution).
3. **Check Upstream State:** Confirm the bug reproduces on upstream `HEAD`, is not already patched in a release or open PR, and violates the project's documented security boundary.

## 3. Channel Tailoring & `100/100` Voice Lint

Load [`skills/security-advisory-report/SKILL.md`](../security-advisory-report/SKILL.md) when tailoring drafts for specific disclosure channels (`ghsa`, `mailing-list`, `h1`, `immunefi`, `customer`), and run the strict voice gate on every outbound file:

```bash
python3 skills/security-advisory-report/scripts/report_voice_lint.py <draft.md> --channel ghsa --strict
```

Mandatory prose rules:
- **Direct 2-Sentence Lead (`<= 55` words):** State tested revision, repo-relative `file:line` and symbol, attacker precondition, and concrete impact upfront.
- **Canonical Sections:** Keep `### Summary`, `### Details`, `### PoC`, `### Impact`, `### Suggested Fix`, and `### Workarounds` crisp and proportional to bug complexity (one line per Markdown paragraph; 72-column wrapping only for `--channel mailing-list`).
- **Zero Internal Jargon & Zero Host Paths:** Never leak internal harness terms, speculative hedging (`could potentially`, `might be vulnerable`, `appears to be`), AI filler, `.ajar/` paths, or developer home paths.
- **Honest Dry-Run Boundaries (`DEC-0099`):** When an audit finishes with zero findings, state exact commit, scope, tested invariants, verified guard loci, and an explicit non-certification notice (never claim "complete security", "proof of clean", "zero false positives", or "guaranteed findings").

## 4. External Action Gate

Never submit advisories, open vendor tickets, contact maintainers, or publish deliverables without explicit founder authorization (`AGENTS.md` Boundary #4).
