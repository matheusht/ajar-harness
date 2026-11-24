---
name: ajar-report
description: Verify deterministic closeout gates G1-G5, seal internal run ledgers, calibrate precedent-grounded severity and root-cause truth, and render de-jargonized customer or maintainer deliverables.
---

# Ajar Report

Use this skill to verify run completion against SQL closeout gates `G1–G5`, seal internal `Platform` telemetry, calibrate finding severity and deduplication, and emit audience-scoped deliverables for `Code`, `Fixes`, `Security reviews`, and `Supply chain` runs.

## 1. Deterministic Closeout Gates (`G1–G5`) & Internal Run Sealing

1. Verify all five deterministic SQL gates pass before sealing a completed run:
   ```bash
   ajar gate check
   ```
   - `G1`: All `critical`/`high` surfaces and tasks completed (or `first-verified-high` / `crown-jewel` stopping rule satisfied cleanly).
   - `G2`: Zero unresolved claims in `proposed`, `survived_falsify`, `needs_instrumentation`, or open `config_gated` override probes.
   - `G3`: Every confirmed finding has passing locus-bound 4-arm JSON receipts, `proposer_worker_id != falsifier_worker_id`, and zero `debug_assert_only` `critical`/`high` findings.
   - `G4`: `zero_skill` first-principles worker quota satisfied when `>= 2` workers ran, `dry` guard loci verified with zero unchained active guarded primitives, and zero policy-withheld `blocked` claims.
   - `G5`: Zero orphaned `unexplained` anomalies, zero unwaived `ready` Open Doors, and Stage-5 `Converge` (`chain`) evaluation completed across composable signals.
2. Export the `Platform` component and attack-flow graph (`ajar-platform-graph/2`) and seal the run (or close early via `ajar close --reason <stopped_by_operator|window_reached|superseded> --notes "<why>"` when stopping before `G1–G5` complete, without claiming `all_gates_passed`):
   ```bash
   ajar export-graph --visibility <internal_full|customer_private|public_disclosure> --output graph.json
   ajar finish
   ```
3. Emit internal engineering ledgers (`--audience internal`) when operator postmortems require `G1–G5` receipts, `runs.harness_sha256` integrity (`harness_modified_mid_run`), `COGS` telemetry, active `Steers`, raw `clm-*`/`fnd-*` IDs, `micropatched` vs `9-arm` `verified_local` `remediation_state`, and `found_autonomously_by_ajar` / `found_with_ajar` / `validated_by_ajar` attribution:
   ```bash
   ajar report --audience internal --format md --output internal-ledger.md
   ajar report --audience internal --format json --output internal-ledger.json
   ```
   Pass `--include-rejected-appendix` only on `--audience internal` postmortems.

## 2. Audience-Scoped Deliverables (`customer` vs `maintainer`)

Render external deliverables from timestamp-ordered calibrated truth (`apply_latest_finding_corrections`) with repo-relative `path:line` normalization and host-path scrubbing (`ajar report --audience customer|maintainer [--finding <id>]`):

```bash
ajar report --audience customer --format md --output security-review.md
ajar report --audience customer --format json --output security-review.json
ajar report --audience maintainer --finding <finding_id> --format md --output advisory.md
ajar ledger commit-preimage <finding_id> --public-out commitment.json --preimage-out preimage.json
ajar bundle seal <bundle_dir>
ajar bundle verify <bundle_dir>
```

- **`customer` (default):** Buyer-safe `DEC-0099` security review report reporting `distinct_root_causes_count`, verified multi-step chains, and inspected `dry` controls while stripping internal unit-economics headers, worker handles, and harness state enums.
- **`maintainer`:** Upstream OSS, GHSA, or bug-bounty advisory (`Summary`, `Root Cause`, `Reproduction`, `Impact`, `Suggested Fix`; pass `--finding <finding_id>` to split one subsystem per advisory) preferring `9-arm` `verified_local` production patches over raw counterfactual micropatches.
- **External Action & Sealing Gate:** Never file advisories, contact vendors, or publish deliverables without explicit operator authorization (`AGENTS.md` Boundary #4). Commit the `DEC-0113` SHA-256 preimage (`ajar ledger commit-preimage`) and seal/verify deliverable directories (`BUNDLE-MANIFEST.json` + `SEAL.sha256`, rejecting symlinks, secrets, and local host paths) before authorized handoff.

## 3. Precedent-Grounded Severity Calibration & Deduplication

Deduplicate shared root causes and calibrate every finding against primary external rulings before rendering `customer` or `maintainer` outputs:

1. **Root-Cause Deduplication & Pre-Filing Checks:** Group alternate entry routes sharing one defect under a single root cause (`ajar claim duplicate <claim_id> --of <parent_claim_id> --worker <worker_id> --reason "<shared root defect>"` or `--same-root-of` at proposal) so `distinct_root_causes_count` stays exact. Before external filing, verify upstream `HEAD`, latest release tag, open and recently closed PRs/issues, published advisories/changelogs, documented security boundaries/known issues, and real capability delta over starting privilege.
2. **Precedent Search & Atomic Calibration:** Query `skills/references/severity-precedent-corpus.md` (NVD/GHSA CVSS v3.1/v4.0 anchors) and `skills/references/defi-contest-rulings-corpus.md` (Code4rena, Sherlock, and Immunefi rulings), then update severity, title, root-cause prose, victim step count, or realism tier atomically:
   ```bash
   ajar precedent search "<vulnerability_class> severity"
   ajar finding calibrate <finding_id> \
     --severity <critical|high|medium|low> \
     --title "<calibrated title>" \
     --root-cause "<calibrated root-cause prose>" \
     --declared-steps <N> \
     --realism-tier <crown_jewel|high_impact|stepping_stone> \
     --reason "<precondition and precedent rationale>"
   ```
3. **Precondition Honesty & Executive Split:** Score strictly by proven preconditions, enumerated sample scope (`N`), and reproduced impact: require `AV:L` / `UI:R` for local file open or user interaction (`ZDI-26-355` / `CVE-2026-27220`), cap non-default config or permissioned operator prerequisites (`CVE-2012-5613`), and never score a crash or out-of-bounds read as RCE without reproduced control-flow or write execution (`CVE-2013-3245`). Separate **(a) Unprivileged Live Entrypoint Findings** from **(b) Config/Operator-Gated, Component-Isolated, or Pre-Activation Findings** in executive summaries.

## 4. Humanistic Technical Writing & Zero-Jargon Discipline

Write direct, active-voice prose for senior software maintainers and security engineers:

1. **2-Sentence Lead (`<= 55w`):** State the tested revision/commit SHA, repo-relative `file:line` and function/struct symbol, required attacker precondition, and concrete outcome within the first `1–2` sentences (`<= 55` words).
2. **Complexity-Proportional Length:** Match prose length to the bug (`90–350w` single-invariant simple defect, `350–650w` stateful or protocol bug, `600–1,000w` multi-step chain). Never pad concise findings to hit an artificial floor or repeat the same explanation across `Summary`, `Root Cause`, and `Impact`.
3. **Code-Subject Causal Trace & Upfront Negative Scope:** Put functions, types, and callers in the grammatical subject slot, cite `Introduced-in:` commit provenance (`git bisect` SHA, subject, and date) plus sibling-route contrast where applicable, and state non-default config/OS/build gates, sanitizer vs release (`-O2`) behavior, and blast-radius ceilings upfront.
4. **Portable Defensive Verification & `9-Arm` `Suggested Fix`:** Supply a self-contained, hermetic verification script (`mktemp -d` + `trap` cleanup) paired with a benign control check, and present an idiomatic root-cause `Suggested Fix` diff verified against the `9-arm` `verified_local` remediation gate (`ajar patch verify` covering caller error/NULL safety, sibling symmetry, regression suite, and `git apply -R` revert proof).
5. **Zero Internal Jargon & Zero Host Paths:** Strip all internal harness tokens (`G1–G5`, `H1–H9`, `4-arm`, `9-arm`, `micropatched`, `verified_local`, `Steers`, `clm-*`, `fnd-*`, `prim-*`, `chn-*`, `Hop 1..N`, `trust_gadget`, `stepping_stone`, `found_autonomously_by_ajar`, worker IDs, and raw `/Users/`, `/home/`, `/tmp/`, or `~/.ajar/` host paths), em-dash punctuation, minimizing adverbs (`simply`/`trivially`), and AI filler from `customer` and `maintainer` prose.
6. **Honest Dry-Run & Review Boundaries (`DEC-0099`):** When a run or surface finishes with zero findings, state the exact commit/scope, engineering invariants tested, repo-relative `file:line` guards verified, unresolved or blocked paths, explicit non-certification notice (never claim "complete security", "proof of clean", "guaranteed findings", or "zero false positives"), and next-review trigger.
