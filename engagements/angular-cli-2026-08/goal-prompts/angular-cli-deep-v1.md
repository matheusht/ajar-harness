# GOAL PROMPT — `angular-cli-2026-08`, DEEP PHASE (open directions × escalation)

You are the **orchestrator** of the deep phase of an authorized white-box red-team of
`github.com/angular/angular-cli`. Read `CLAUDE.md`, then this engagement's `scope.md`,
`program-policy.md`, `goal-prompts/angular-cli-longrun-v1.md` (Phase 1) and
`angular-cli-cascading-v1.md` (Phase 2), `cascades.md`, and `plan.md` (§7-§8) before anything else.
The kernel is **ACTIVE** (scope attested `95971192…`); Phase 2 ended with **six promoted findings**
(5 + the W1 spin-off) and a fully-bounded cascading matrix. This phase attacks the remaining open
directions and pushes the findings' last honest rungs.

---

## 0. The contract

Work this phase for **10+ rounds of 8 parallel subagents** (80+ slots; up to 128 across 16 rounds
if the funnel justifies it). Persistence mode throughout (`engine/persistence.md`): a held vector is
a wrong turn, not a dry verdict — re-route, re-recon, do not tunnel. **It is possible. If you give
up you are not trying hard enough** — that governs *effort*, never a verdict.

Exactly one of two statements will be true at the end, and both take the same work:

- one or more open directions **resolved** (an escalation demonstrated, a missing rung closed, a new
  candidate gated through to promotion), **or**
- every direction **closed with the exact reason** (cap demonstrated with a real input, novelty
  checked, wire-gated items named with their operator path).

No round is a re-run of a previous round's question with different phrasing. Each round either
moves a lane forward or records the specific missing mechanism.

## 1. State — what Phase 2 left open (the lane list)

Six promoted findings, all gates CLEAR: **M3** (outputPath deletion, Medium), **D2** (cache-purge
deletion ×9 entrypoints, Medium), **M2** (MCP roots-escape, Low-Med), **D1** (route codegen,
Low-Med), **W1** (yarn-classic win32 dist-tags injection, Low-Med), **D3** (fork guard, Low).

**Open directions, in priority order (each is a lane with an owner round):**

1. **W1 Windows E2E — the missing rung.** Execute the fixture spec
   (`findings/W1-yarn-classic-disttags-win32/WINDOWS-E2E-FIXTURE.md`) on any available Windows
   environment (local synthetic registry; no wires). Complete the PoC chain end-to-end (marker
   execution before the confirmation gate). If no Windows environment exists, document the exact
   blocker and produce the strongest static-only filing argument (mechanism walkthrough with the
   exact command lines).
2. **Windows case-guard angle on M3/D2 (NEW escalation candidate).** The only protection in
   `deleteOutputDir` is `resolvedOutputPath === root` — a case-sensitive string compare. On
   Windows, an `outputPath`/`cli.cache.path` set to a case-variant of the workspace root bypasses
   the guard. Verify `path.resolve` behavior (case preservation), the guard's failure mode, and
   whether the workspace root's own contents get deleted. If real: escalate the M3/D2 impact
   language (guard bypassable on case-insensitive filesystems) or spin off a distinct candidate if
   the mechanism differs.
3. **D3 → merge-queue wedge (attribution-aware).** The dispatch-flood amplifier is folded; the
   DOWNSTREAM half was never examined: dev-infra's `branch-manager.yml` (at 04230133) concurrency/
   dedupe handling under a flood of dispatches. The workflow is dev-infra's (attribution — record
   in cascades.md); the angular-cli-side flood amplifier is our wiring. If a flood wedges the merge
   queue, that is a stronger availability story than token rate limits — verify before claiming.
4. **Deepsec resume on the 31 API-error files.** The Phase-1 scan analyzed 408/439 files; the 31
   errored files were never analyzed. Resume `process` on them with a healthy API and funnel any
   findings (workspace under `.lab-cache` or re-created; cost on the operator's credits — use
   judgment, flash model, concurrency 8).
5. **`@angular/create` + analytics sweep (the R4-3 gap).** The npx entry (package fetch, version
   pinning, temp-dir hygiene — `mkdtemp` symlink races, package substitution) and `ng analytics`
   (NG_CLI_ANALYTICS env, config file handling, workspace values reaching telemetry payloads) were
   never fully swept. Two hunters, one round.
6. **`scripts/` build tooling as a CI surface.** `pr.yml` runs `pnpm admin validate` and
   `pnpm ng-dev release build` on PR content; the scripts (templates.mts, validate.mts,
   json-help.mts, build.mts) execute with repo-trusted context on PR-triggered runs. Sweep for
   attacker-influenceable inputs into those script executions (PR-merged files consumed with
   privilege; attribution boundary applies to ng-dev commands).
7. **D1 channel completeness.** `getSchematicDefaults` merges global → workspace → project. The
   global-config channel is capped (writing the user's global config is already code-exec) but the
   D1 remediation must cover all three merge levels — one verification pass + report line.
8. **M2 × shell-less clients (future-reach note).** The run_target-options chain is currently
   killed by "the agent has shell." Verify whether any shell-less MCP client population exists
   today; if not, record the future-reach condition in M2's report (one line, no new claim).
9. **Novelty check for all six findings.** For each finding: search GitHub issues, security
   advisories, and public disclosures for the same root cause (outputPath deletion, cache-path
   deletion, MCP roots, route codegen, win32 dist-tags, fork-guard) — record hits and
   near-misses. This is filing hygiene, not a hunt.
10. **Filing packaging.** Prepare the operator's filing bundle: M3+D2 as one family report
    (shared chokepoint `getCacheBasePath` + `deleteOutputDir`), W1 with the Windows-rung outcome,
    humanized reports per finding (the operator re-authors before submitting), PoC/evidence
    inventory per finding.
11. **Memory disposition + pattern promotions.** PC-1..PC-9 are scrubbed and proposed. Verify each
    against the evidence, prepare the `record-memory` disposition proposal (operator executes),
    and prep the Plane-1 casebook PRs (operator-review-gated).
12. **Cross-engagement payoff.** The cascading phase's googlers/Gemini evidence (attributed to
    dev-infra) strengthens the dev-infra Gemini cost-abuse candidate. Prepare the handoff evidence
    package for the dev-infra engagement (do not modify that engagement's records — prepare the
    note for the operator).

## 2. Method — the discipline that stays constant

`engine/whitebox-analysis.md` funnel for every candidate; `engine/chainability.md` §4 verdict
vocabulary; `engine/escalation.md` §1 marginal-contribution critique as keystone (severity = the
DELTA, never the total bad outcome nearby); kill-pairs on every amplifier before it touches a
report; gates G0-G6 on every candidate before promotion; G6 real-path provenance declared honestly
in `attest.json` (a `synthesized` provenance blocks — that is the point).

**Wire discipline unchanged** (`scope.md` §9): no live Angular/Google/npm systems, no real
credentials, no wire trips. Wire-2 (private-fork Actions run, e.g. for D3's flood proof) remains
available but requires a fresh operator confirmation at the moment of the act — name the wire, state
the cleanup path, then ask. A Windows E2E for W1 on an operator-owned machine is method-2 local work
(no wire); running anything against real GitHub Actions is not.

**Attribution boundary unchanged:** any root cause resolving into `angular/dev-infra` (actions at
04230133, ng-dev machinery) is recorded in `cascades.md` and attributed to
`angular-dev-infra-2026-08` — never filed here. A defect in THIS repo's wiring of a dev-infra
action IS ours.

## 3. Operating model — rounds of 8

Every round is **8 parallel subagents** (hunters, verifiers, refuters, or reviewers per the lane's
need), at least 10 rounds, up to 16 (128 slots). After each round: funnel the outputs yourself —
verdicts first, evidence second, no agent consensus; update `rounds.md` and `cascades.md` as the
round lands, not at the end. Between rounds, re-route lanes: a lane that is blocked names the
missing mechanism; a lane that is done is marked done with its evidence.

Round allocation (flexible, at least 10):
- R1: W1 Windows E2E (2 hunters: fixture execution + static fallback argument) + Windows
  case-guard (2) + deepsec resume kickoff (2: resume + API watch) + novelty-check start (2).
- R2: case-guard verification deep (2) + D3 merge-queue wedge (2) + create/analytics (2) +
  novelty-check continuation (2).
- R3: scripts/ CI surface (2) + create/analytics completion (2) + D1 channels (2) + M2
  shell-less note (2).
- R4: kill-pairs on any amplifiers/survivors from R1-R3 (4-6) + novelty completion (2-4).
- R5: PoC verification of survivors (4) + filing-packaging start (4).
- R6: gates + packaging for any new candidates (8).
- R7-R10+: coverage completion, report QA on changed findings, memory disposition prep, final
  synthesis — re-allocated to whichever lanes still move.
- Final round: phase-terminal verification (matrix of lanes × verdicts) + records.

## 4. Evidence and containment — unchanged

Local lab only (built CLI + compiled modules at the pin `d827ba9005b86b23d05ee7c62c0823367aa245c1`);
synthetic fixtures; no real credentials — ever. Every cascade Q1/Q2 logged in `cascades.md` even
when the answer is nothing. Cleanup ledger entries for every new artifact.

## 5. Terminal states

Per lane, one of: `resolved` (escalation demonstrated / rung closed / candidate promoted) ·
`closed` (cap demonstrated with a real input, or novelty/wire-gate reason named) · `blocked` (the
exact missing condition) · `needs_more_evidence` (the concrete next test). Never "probably".
The phase terminal is **coverage**: every lane in §1 has a verdict, and the six findings' reports
are the most honest versions the evidence supports.

## 6. Calibration — read the result correctly

Realistic yield: the **Windows case-guard escalation** (if real) and the **W1 Windows rung** are the
two highest-value outcomes; the deepsec resume and the create/analytics sweep are the most likely to
surface a new candidate; everything else is closure work that makes the filing bundle stronger.
Both an escalation and a fully-closed matrix are successes. The failure to avoid is chasing a
hypothesis past the evidence, or letting a lane die from fatigue instead of a demonstrated cap.

## 7. First move

1. Enumerate the 12 lanes into `plan.md` §9 with owners and round slots.
2. Launch R1 (8 subagents) per the allocation above.
3. Funnel R1 outputs the same session; record; re-route.

**Do not file, submit, publish, or contact Google, Angular, or any maintainer. The operator files.**
