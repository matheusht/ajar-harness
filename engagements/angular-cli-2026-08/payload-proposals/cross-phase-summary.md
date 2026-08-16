All facts verified from the records. Writing the cross-phase synthesis:

---

# CROSS-PHASE SYNTHESIS — `angular-cli-2026-08` (Phase 1 → Cascading → Deep)

**Engagement:** authorized white-box red-team of `github.com/angular/angular-cli` · pin `d827ba9005b86b23d05ee7c62c0823367aa245c1` (HEAD 2026-08-13) · local lab only, no wires, no filing (operator-only) · kernel decision-0006, append-only.

## (a) Phase 1 — longrun (`angular-cli-longrun-v1.md`, ~6h, blind sweep)

**Structure (verified, plan.md §5):** R0 blind (12 families, one per hunter) → R1 verification → R2 refutation → R3 SCC deep push (ng add/update/lane-A/aliases/spawn-sweep/MCP-chain) → R4 corners, plus a deepsec cross-scan (408 files analyzed, 31 API-errors, 82 findings — every finding adjudicated against pinned source). Kernel activation landed late-phase; records were staged and replayed.

**Findings promoted (#1-#5, all gates G0-G6 CLEAR):**

| # | Finding | Severity | Posture at phase end |
|---|---|---|---|
| 1 | **M3** `outputPath` → recursive deletion outside the workspace root — flagship application builder delete path (fix `8358805d3` covered writes only) + legacy browser/server | Medium | confirmed-escalated; sibling-miss framing; refuter R2-2 CONFIRMED |
| 2 | **D2** `ng cache clean` recursively deletes an arbitrary directory via workspace-controlled `cli.cache.path` | Medium | real-command PoC; tempDirectory-sibling guard is the discriminator |
| 3 | **M2** MCP `get_best_practices` reads outside declared roots (createRequire ancestor walk) and injects content into the agent context | Low-Med | real-but-capped (refuter R2-1); supply-chain precondition |
| 4 | **D1** `--route` quote-breakout codegen injection | Low-Med | deepsec-confirmed; no schema validation |
| 5 | **D3** branch-manager fork guard ineffective (`github.event.repository.fork` always-false on PR events) | Low | control-ineffectiveness; API-only action caps impact |

**What the phase established:** breadth-first discovery; every candidate got an adversarial refuter; the deepsec cross-scan doubled the finding count (D1/D2/D3); honest capping (M2 real-but-capped, D3 control-only) became the house style.

## (b) Cascading phase — E0 (`angular-cli-cascading-v1.md`, 12 rounds × 4 subagents = 48 slots)

**Structure:** composition matrix (12 cells: finding × chainability angle), kill-pairs on every amplifier, fold-QA, held-cap sweep, family sweeps (×4), report QA (×2), doctrine research began.

**Outcome (verified, plan.md §8):**
- **W1 spun off + promoted as finding #6** — yarn-classic win32 command injection via unvalidated registry `dist-tags` values (metadata-fetch path → quote-wrap-no-escape → win32 `shell:true`), pre-gate/pre-confirmation invisible execution; kill-pair SURVIVES; CVSS 7.5; Windows E2E rung environment-blocked (fixture specified).
- **Amplifiers folded:** D2 ← purgeStaleBuildCache (9 builder entrypoints, shared `getCacheBasePath` chokepoint); D3 ← unbounded event-stream × robot-key jobs (E12); M2 ← re-poisoning persistence; D1 ← **comma-exec PoC correction** (original demo payload was invalid TS) + production-SSR reach + persistence.
- **Killed:** D1 schematics-defaults channel (precondition already code-exec), title sibling sink, D3 spam sub-claim; 4 held caps HOLD under adversarial attack.
- **Doctrine discovery began:** #32509 (severity6, same sink class), #32678 (git-only fix), #32892 (full fix REJECTED), 3/27 won't-fix posture — changed W1's filing framing from "first report" to "fix-bypass with a narrow delta".

**What the phase changed:** findings went from *discovered* to *bounded* — every amplifier adjudicated, every cap demonstrated, and the family/doctrine context that determines filing viability was surfaced.

## (c) Deep phase — E1 (`angular-cli-deep-v1.md`, 12 rounds × 8 subagents = 96 slots)

**Structure (verified):** E1-R1..R10 executed (10 × 8 = 80 slots); E1-R11/R12 in progress (terminal synthesis + final verification, 16 slots → 96 total). Lanes: W1 Windows rung, M3 case-guard escalation, D3 merge-queue wedge, deepsec resume, create/analytics, scripts CI, D1 channels, M2 shell-less, novelty ×3, filing packaging, memory disposition, dev-infra handoff.

**Outcome (verified, plan.md §11):**
- **E1-C1 promoted as finding #7** — i18n locale-key/`sourceLocale` bypass of `ensureValidSubPath` → webpack-stack output-dir escape + locale-data module load; Low-Med; **NOVEL** (no public disclosure); 7/7 gates; **re-scoped by adversarial review** (RV-C1-A refuted the app-builder A1/D members — `generateFullPath` re-contains; the webpack stack A2/A3/B/C survived).
- **Material widenings folded:** W1 ng-update entry is **manager-INDEPENDENT** (npm default reaches the sink; yarn-classic-only applies to the add path); M3 amplifier #3 (legacy prerender route-escape write).
- **Escalation resolved:** M3 case-guard bypass — the only root-protection (`resolvedOutputPath === root`, case-sensitive string compare) is defeated by case-variant paths on case-insensitive filesystems (macOS APFS, Windows NTFS, GH Actions macOS runners); compiled-module PoC, survived 7-variant refutation.
- **Closures:** W1 Windows rung (wire-gate: no Windows execution layer in lab; static filing argument complete); create CLEAN (7/7 angles); analytics CAPPED; scripts CI CAPPED (untrusted-job boundary); D3 queue-wedge KILLED (status-reporter only; robot-budget NARROWED-SURVIVES); deepsec resume COMPLETE (451/451; 16 findings → 1 promoted, rest folded/capped/refuted); **deepsec findings treated as untrusted until verified** (A4 redirect family refuted on a mechanism error).
- **Novelty matrix:** M3 NOVEL, D2 NOVEL, D1 NEAR-MISS (#33074/#33076 closed not-a-vuln — re-framed disclosed+REJECTED), W1 NEAR-MISS fix-bypass, M2 residual NOVEL, D3 no disclosure, E1-C1 NOVEL.
- **Deliverables:** filing bundle (FILING-COVER + humanized M3/D2/W1 drafts + evidence inventory; credential scan CLEAN), memory disposition (12 pattern candidates in winners.md format; PC-3 operator-gated), dev-infra handoff note (4 advisory-grade items; boundary respected).

**What the phase changed:** the findings became *filing-ready* — novelty established, doctrine framing written in, one new finding promoted, two widened with verified mechanism corrections, one escalated, and every claim re-scoped to what the evidence actually shows.

## (d) Engagement totals (verified from records)

| Metric | Value |
|---|---|
| Findings promoted | **7** (M3, D2, M2, D1, D3, W1, E1-C1) — all gates CLEAR (re-verified E1-R8/R9/R10) |
| Hypotheses | **7** (d1, d2, d3, m2, m3, w1, e1c1-i18n-locale) — all closed (not 8; verified from events.jsonl) |
| Kernel events | **45** (scope.attested 1, observation.recorded 15, hypothesis.created 7, hypothesis.status_changed 19, environment.preflight_recorded 1, record.committed 1, authority.requested 1) |
| Attempts | **24** (7 primary, 13 negative-control, 4 replay) |
| Rounds | Phase 1: R0-R4 + deepsec scan; Cascading: E0-R1..R12; Deep: E1-R1..R12 |
| Subagent slots | Cascading: 12×4 = **48**; Deep: 12×8 = **96** (R1-R10 done = 80, R11-R12 queued = 16). Phase 1 used round-structured hunts (R0 blind 12-lane + R1-R4 + deepsec) — not a clean 12×4; the 12×4/12×8 counts are the cascading/deep goal contracts, which the records confirm |
| Attribution | 10 cascades.md rows (dev-infra/angular-cli split; row 5 corrected E1-R6) |
| Records | rounds.md E0-R1..R12 + E1-R1..R12; plan.md §7 matrix, §8 terminal, §9 lanes, §10 hardening H1-H17, §11 deep terminal |

## (e) Narrative — what each phase changed about the findings posture

1. **Phase 1 — discovery.** Five findings emerged from a blind breadth-first sweep plus an independent scanner cross-check. Posture: *new and honest* — sibling-miss framing (M3 vs 8358805d3), real-but-capped (M2), control-ineffectiveness (D3). Refutation discipline was established.
2. **Cascading — depth and correction.** The composition matrix forced every finding to be attacked from six chainability angles. This produced the most consequential correction of the engagement (D1's PoC was invalid TS; the comma-exec shape works, and production-SSR reach widened it), one cap-removal spin-off (W1), and the first reading of the maintainers' actual posture (won't-fix doctrine for the package-manager sink class). Posture: *bounded and documented*.
3. **Deep — closure and filing-readiness.** One new finding (E1-C1), two verified widenings (W1 to npm-default via ng update; M3 prerender), one escalation (case-guard bypass), full novelty/doctrine framing, adversarial re-scoping that *removed* claims (A1/D) — evidence discipline at its strictest (deepsec findings proven wrong twice: SSR redirect family, app-builder expansion). The filing bundle, memory disposition, and dev-infra handoff were built to operator-gate. Posture: *the most honest versions the evidence supports — every lane closed with a reason, nothing "probably".*

**Standing operator decisions (from OP-decisions, 12 items):** filing per finding (7), W1 Windows E2E rung, memory disposition run (record-memory), PC-3 disposition, dev-infra handoff pointer, severity-taxonomy cleanup, cleanup ledger execution at closure (incl. `opencode-key` credential), stale close-authority request for the cascading-phase close.

```acceptance-report
{
  "criteriaSatisfied": [
    {
      "id": "criterion-1",
      "status": "satisfied",
      "evidence": "Cross-phase synthesis written from the engagement records with per-finding file paths and severities: 7 findings under engagements/angular-cli-2026-08/findings/ (M3-legacy-builder-outputpath-delete Medium, D2-cache-clean-deletion Medium, M2-mcp-best-practices-roots-escape Low-Med, D1-route-codegen-injection Low-Med, D3-branch-manager-fork-guard Low, W1-yarn-classic-disttags-win32 Low-Med CVSS 7.5, E1-C1-i18n-locale-key-escape Low-Med NOVEL); all gates CLEAR. Counts verified from events.jsonl (45 events, 7 hypotheses), attempts.jsonl (24: 7 primary/13 neg-control/4 replay), rounds.md (E0-R1..R12, E1-R1..R12), plan.md §5/§7/§8/§9/§10/§11, and the three goal prompts."
    }
  ],
  "changedFiles": [],
  "testsAddedOrUpdated": [],
  "commandsRun": [
    {
      "command": "ls engagements/angular-cli-2026-08/findings/ + wc -l events.jsonl attempts.jsonl + python hypothesis/attempt-kind counts",
      "result": "passed",
      "summary": "7 findings; 45 events; 24 attempts (7 primary, 13 negative_control, 4 replay); 7 hypotheses — the hypothesized '8 hypotheses' corrected to 7"
    },
    {
      "command": "grep E0-R/E1-R rows in rounds.md + goal-prompt round contracts",
      "result": "passed",
      "summary": "Cascading E0-R1..R12 (12 rounds x 4 = 48 slots per plan.md §8 header); Deep E1-R1..R12 (12 rounds x 8 = 96 slots per goal contract; R1-R10 executed = 80, R11-R12 queued); Phase 1 = R0-R4 + deepsec scan (round-structured, not 12x4)"
    },
    {
      "command": "sed plan.md §5/§7/§8/§11 + cascading goal terminal-states section",
      "result": "passed",
      "summary": "Phase outcome wording anchored to the recorded verdict vocabulary and the §8/§11 terminal tables"
    }
  ],
  "validationOutput": [
    "Synthesis covers (a) Phase 1 discovery (5 findings, sibling-miss/real-but-capped/control-ineffectiveness postures), (b) cascading depth (W1 spin-off #6, amplifier folds, kill-pairs, D1 PoC correction, doctrine discovery), (c) deep closure (E1-C1 #7, W1 manager-independent widening, M3 case-guard escalation + amplifier #3, deepsec resume, novelty matrix, bundle/memory/handoff), (d) verified engagement totals, (e) the three-phase posture narrative."
  ],
  "residualRisks": [
    "Deep-phase E1-R11/R12 rows in rounds.md remain 'planned' — the deep phase is at R10 complete with the final two rounds in progress; slot total 96 assumes both complete at 8 slots each",
    "W1's physical Windows execution rung remains environment-blocked (wire-gate); the static-only filing argument is the current evidence ceiling",
    "finding.json cvss empty for D1/D2/D3 and the low_medium severity vocabulary are engagement-wide conventions flagged for operator taxonomy cleanup",
    "deepsec workspace /tmp/deepsec-scan-cli (962 MB) + /tmp/deepsec (1.9 GB tool) hold the opencode-key credential — cleanup-listed, deletion at closure"
  ],
  "noStagedFiles": true,
  "diffSummary": "Read-only lane; no files modified; synthesis returned inline for the operator report",
  "reviewFindings": [
    "no blockers: all counts and phase structures verified against the actual records (findings dir, events/attempts ledgers, rounds.md, plan.md, goal prompts)",
    "correction: the task brief's '8 hypotheses (7+1)' is 7 hypotheses — events.jsonl shows exactly 7 hypothesis.created events, all closed",
    "correction: the task brief's 'Phase 1: 12x4=48' does not match the records — Phase 1 used R0-R4 round structure + deepsec scan; 12x4=48 is the cascading contract (confirmed by plan.md §8 header)"
  ],
  "manualNotes": "For the parent: this synthesis is the operator-report input, not a record — nothing written to the engagement. The 7 hypotheses / 45 events / 24 attempts / 7 findings totals are the authoritative numbers for the final report. E1-R11/R12 still owed the funnel to reach the full 96-slot deep contract."
}
```
