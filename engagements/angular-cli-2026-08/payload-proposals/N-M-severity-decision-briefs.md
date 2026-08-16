# N-M — OPERATOR SEVERITY DECISION BRIEFS (final)

## (a) E1-C1 venue-split record — filing vector decision

**State (verified):** `findings/E1-C1-i18n-locale-key-escape/REPORT.md:42-46` carries the venue split. Three defensible vectors exist; the operator picks ONE for the filing:

| Venue | Vector | Score | Notes |
|---|---|---|---|
| Browser (webpack client bundle) | AV:L/AC:H/PR:N/UI:N/S:U/C:L/I:L/A:N | **4.0 Low-Med** | Integrity + limited disclosure; no exec in the build process; config-trust channel |
| Legacy-SSR (server bundle) | AV:L/AC:H/PR:N/UI:R/S:U/C:H/I:H/A:H | **6.3 Medium (RECOMMENDED)** | Attacker-authored JS executes in the SSR Node process at server boot (N1D E2E: real i18n-inlining pipeline, boot-time module evaluation, negative clean); honest preconditions = local attacker file/package placement + dev must run the localized build → AV:L + UI:R |
| Legacy-SSR (calculator variant) | AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:H/A:H | **8.1 High** | Only if the operator treats the config value as remotely-suppliable (cloned-repo = remote delivery) and the build as unattended (CI). Recorded per ECRV; **not recommended** — the UI:R + AV:L preconditions are the honest reading and the 8.1 variant invites a maintainer doctrine dismissal |

**Decision framing:** file the SSR venue with the **6.3 vector** (the delta-first opening already exists at `payload-proposals/E1C1-filing-openings.md`); record the 8.1 variant as a one-line sensitivity note in the finding (already in REPORT:45 — "superseded by this correction... recorded for the operator"). If filed as a separate report (operator option), the record brief `payload-proposals/E1C1-venue-split-record-brief.md` is the basis.

## (b) W1 CI-venue — file as part of W1 or separate?

**State (verified):** `findings/W1-yarn-classic-disttags-win32/REPORT.md:75` + the N6B QA correction: the fork-PR CI venue vector AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:H/A:H computes to **8.1 HIGH** (harness calculator + independent recompute; the earlier 5.6 figure was superseded). The mechanism hops are source-verified (checkCLIVersion fires first at cli-version.ts:63 / update/cli.ts:168-171; env inheritance host.ts:150-165); the execution rung is environment-blocked (no Windows host; the run-bundle at `payload-proposals/W1-windows-runbundle/` is operator-ready).

**Decision framing — file as a SEPARATE entry (recommended):** the CI venue has a distinct attacker model (fork-PR trigger, zero user interaction, secret-bearing runner env) vs the dev-machine base (UI:R, won't-fix doctrine #32509/#32892). A separate entry: (1) survives the doctrine dismissal that the dev-machine base will face; (2) carries its own delta-first lede (zero-interaction fork-PR RCE with runner-token reach); (3) gets its own severity (8.1 HIGH) without inflating the base's Low-Medium filing. Risk of separate filing: co-credit/precedence overlap with #32509 (cite it as the class fix) — handled by the doctrine citations already drafted. If the operator prefers one report, the CI venue goes in as an amplifier section with its own vector (the current REPORT layout already supports this).

## (c) Actions-minute quantification (Chain 2 cost-abuse)

**State (verified):** the cost-abuse is a surviving Chain-2 delta (KP-C2: "Actions-minute burn — fork-PR flood = billed minutes, mitigated only by repo fork-PR policies"; wire-2 spec cost section).

**Quantification (two sides):**
- **Victim-side burn (attacker flood):** each fork PR that passes the repo's workflow gate burns the BASE repo's Actions quota (GitHub bills PR-triggered workflows to the base-account by default). Per-event cost ≈ job wall-time × runner multiplier (ubuntu 1×; macOS 10×; Windows 2× — per GitHub runner-pricing). A 10-min ubuntu build ≈ 10 quota-min; a 10-min macOS build ≈ 100 quota-min. A coordinated flood of ~50-200 fork PRs (issue+PR automation) yields **~0.5k-20k quota-minutes of burned quota** depending on the runner mix — enough to exhaust a 2,000-min free/Pro private quota or materially degrade an org plan (public-repo minutes are free, so the abuse targets private/org repos and self-hosted-runner pools via concurrency). Mitigations: fork-PR policies, `workflow_dispatch` gates, and per-repo public-runner settings — but none of these are universal, and the purge/delete hops fire regardless of the minute economics (the availability damage is the primary, the billing burn the amplifier).
- **Demo cost (wire-2, operator's own account):** the private-repo demo ≈ **90 quota-min total** (macos 10× ≈ 80; ubuntu ≈ 8) — within a free/Pro private budget; macos-only option ≈ 80. Charged to the operator's own account, no third party.

**Filing framing:** Actions-minute burn is a supportable but secondary claim — file it as a supporting impact paragraph in the M3+D2 family report (or the Chain-2 context note), NOT as a standalone finding (no new root cause; the delete/write hops are the primary).

```acceptance-report
{
  "criteriaSatisfied": [
    {
      "id": "criterion-1",
      "status": "satisfied",
      "evidence": "Three decision briefs returned with concrete file paths and severities: (a) E1-C1 venue-split (4.0/6.3/8.1 variants, grounded in findings/E1-C1-i18n-locale-key-escape/REPORT.md:42-46 + N1D E2E + ECRV), (b) W1 CI-venue 8.1 HIGH (findings/W1-yarn-classic-disttags-win32/REPORT.md:75 + N6B correction; separate-entry recommendation with doctrine citations), (c) Actions-minute quantification (KP-C2 surviving delta + wire-2 spec cost section lines 61-65; victim-side burn model + demo cost ~90 quota-min)"
    }
  ],
  "changedFiles": [],
  "testsAddedOrUpdated": [],
  "commandsRun": [
    {
      "command": "grep/sed over findings/E1-C1-i18n-locale-key-escape/REPORT.md (venue-split section), findings/W1-yarn-classic-disttags-win32/REPORT.md (CI-venue section), payload-proposals/chain2-wire2-spec.md (cost section), /tmp/ir/KP-C2-chain-full.md (Actions-minute burn)",
      "result": "passed",
      "summary": "All three records verified at source; no invented figures; the 8.1 recompute matches the harness-calculator correction from N6B"
    }
  ],
  "validationOutput": [
    "E1-C1: 6.3 Medium recommended for the SSR venue (honest preconditions), 8.1 variant recorded as a sensitivity note; browser venue stays 4.0",
    "W1: CI venue 8.1 HIGH — separate-entry recommendation (distinct attacker model, survives the won't-fix doctrine); one-report alternative documented",
    "Actions minutes: victim-side flood burn ~0.5k-20k quota-min by runner mix; wire-2 demo cost ~90 quota-min on the operator's own account"
  ],
  "residualRisks": [
    "W1 CI-venue physical execution rung remains environment-blocked (Windows) — the 8.1 claim is source-verified/mechanism-complete, execution-pending",
    "Actions-minute billing attribution for fork-PR workflows can vary with org policy (billing to the fork in some configurations) — the model states the default GitHub behavior and flags policy as a mitigation",
    "E1-C1 8.1 variant decision is the operator's call; if chosen, the finding.json cvss field and the opening draft must be updated to match"
  ],
  "noStagedFiles": true,
  "diffSummary": "Read-only records lane; no files modified; three briefs returned inline for the parent to save under payload-proposals/ (e.g. N7-operator-severity-briefs.md)",
  "reviewFindings": [
    "no blockers: all three briefs grounded in verified on-file records with exact anchors and severities",
    "note: brief (b) recommends a separate W1-CI entry — this reverses the earlier 'part of W1' leaning because the N6B 8.1 recompute changed the calculus (a HIGH severity separate from a Low-Medium base filing)",
    "note: brief (c) is a supporting-impact paragraph, not a standalone finding — no new root cause"
  ],
  "manualNotes": "Parent: save these three briefs as payload-proposals/N7-operator-severity-briefs.md; they feed the N7 rounds row (decision briefs final) and the FILING-SEQUENCE final (W1-CI separate entry insertion). The E1-C1 6.3 recommendation is consistent with the Wave-B correction already applied."
}
```
