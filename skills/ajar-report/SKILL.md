---
name: ajar-report
description: Verify deterministic closeout gates G1-G5, calibrate severity from primary precedents, and generate concise, evidence-backed security reports.
---

# Ajar Report

Use this skill to verify run completion against SQL closeout gates `G1–G5`, seal the run receipt, and produce customer-ready deliverables for `Code`, `Fixes`, `Security reviews`, or `Supply chain` engagements.

## 1. Run Closeout Gates and Seal the Run

1. Check all five deterministic SQL gates before writing any final summary:
   ```bash
   ajar gate check
   ```
   - `G1`: All `critical`/`high` surfaces and tasks completed (or `first-verified-high` satisfied with zero leased verification tasks).
   - `G2`: Zero unresolved claims in `proposed`, `survived_falsify`, or `needs_instrumentation`.
   - `G3`: Every confirmed finding carries a 4-arm reproduction record and independent falsification (`proposer_worker_id != falsifier_worker_id`).
   - `G4`: Zero-Skill First-Principles worker quota satisfied when `>= 2` workers ran, and every `dry` closure cites a valid `file:line` locus.
   - `G5`: Zero orphaned `unexplained` anomalies and multi-primitive chain check completed.
2. Seal the run and emit `CLOSEOUT_RECEIPT`:
   ```bash
   ajar finish
   ```
3. Generate the structured report:
   ```bash
   ajar report --format markdown --output report.md
   ```
   Customer reports include only causally verified `findings` and verified `chains`, plus bounded `dry` surface coverage. Pass `--include-rejected-appendix` only for internal postmortems.

## 2. Precedent-Grounded Severity Calibration

Calibrate every finding's severity against primary external benchmarks before finalizing:

- Query `skills/references/severity-precedent-corpus.md` (NVD/GHSA CVSS v3.1/v4.0 anchors) and `skills/references/defi-contest-rulings-corpus.md` (Code4rena, Sherlock, and Immunefi rulings):
  ```bash
  ajar precedent search "<vulnerability_class> severity"
  ```
- Score strictly by **proven preconditions and proven impact**:
  - Require `AV:L` / `UI:R` when exploitation requires local file open or user click (`ZDI-26-355` / `CVE-2026-27220`).
  - Cap severity when non-default administrative misconfiguration is a prerequisite (`CVE-2012-5613`).
  - Never score a crash or out-of-bounds read as RCE unless control-flow or write primitive execution is reproduced (`CVE-2013-3245`).

## 3. Direct Technical Writing Rules

Write for senior software and security engineers:

1. Lead with the exact `file:line` locus, affected component, required attacker privilege, and concrete impact in the first two sentences.
2. State the exact reproduction command, benign control command, and 4-arm verification result.
3. Explain the root cause using concrete variable, function, and state names from the codebase.
4. Provide the minimal root-cause fix diff and note any audited sibling routes.
5. Preserve exact attribution (`found_autonomously_by_ajar`, `found_with_ajar`, or `validated_by_ajar`) computed from `human_touches`.
6. Never use filler adjectives, dramatic framing, or unsupported assurances (never claim "complete security", "guaranteed clean", or "zero false positives"). When a run finishes with zero findings, state the exact surfaces mapped, `dry` controls verified, and any out-of-scope boundaries.
