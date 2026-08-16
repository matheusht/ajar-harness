# GOAL PROMPT — `angular-cli-2026-08`, NEXT PHASE (the filing-completion + closing-branch + current-main re-verification phase)

You are the **orchestrator** of the next phase of an authorized white-box red-team of
`github.com/angular/angular-cli`. Read `CLAUDE.md`, then this engagement's `scope.md`,
`program-policy.md`, `goal-prompts/angular-cli-chainstorm-v1.md` (the completed chainstorm phase),
`cascades.md`, and `plan.md` (§7-§13). The kernel is **ACTIVE** (61 events at the chainstorm
terminal); the chainstorm phase ended with **seven promoted findings** (all gates CLEAR), **five
chain verdicts** (C1 CONFIRMED fixture 9/9 · C2 NARROWED-SURVIVES · C3 ARMED-WITH-ESTIMATED-FOLLOW ·
C4 CONFIRMED venue-restricted · C5 FUTURE-CONDITIONAL), a **36-subagent per-finding swarm** (Wave B)
that added per-finding precision and severity corrections, and a **64-subagent Wave D** that begins
THIS phase. This phase completes the filing bundle, closes the documented closing branches, and
re-verifies the findings against CURRENT main.

---

## 0. The contract

Work this phase for **8+ rounds × 8 subagents (64+ slots)**. The four Wave-D rounds (4 × 16) are
the first four rounds of this phase: D-R2 executes the highest-value lanes, D-R3 kill-pairs +
verifies, D-R4 synthesizes + records + phase-terminal — and the phase continues to R5-R8 (16 lanes
per round structure below) until coverage.

**It is possible. If you give up you are not trying hard enough** — that governs *effort*, never a
verdict. A closing branch that stays blocked names its exact missing mechanism; a filing bundle that
is not operator-ready is not done.

## 1. State — the residue this phase consumes (verified 2026-08-15)

Seven promoted findings, all gates CLEAR:
- **W1** win32 dist-tags injection (Low-Med base; **CI-variant severity Medium? = operator decision**; version-check venue cli-version.ts:63 + package.json poisoning + CI-venue severity split 5.6 UI:N / conditional-High-OIDC added by Wave B; Windows E2E execution rung = the single evidence-grade gap, fixture ready).
- **M3** outputPath deletion (Medium; case-guard amplifier; write amplifiers #2/#3 at Low; **#33312/bd413b0eb follow-up fix (main-only, write-path) + #32873 delete-guard proposal disclosed-but-unfixed — CURRENT-MAIN RE-VERIFICATION REQUIRED before filing**).
- **D2** cache-path deletion (Medium; the keystone unconditional hop of Chains 1/2; one-family-report recommendation with M3).
- **D1** route codegen (Low-Med; route unique across the 22-member family; app-trust scoping applied).
- **E1-C1** i18n locale-key bypass (venue-split: browser Low-Med 4.0 / **legacy-SSR MEDIUM 6.3 — CORRECTED from 7.3 by Wave-B kill-pair ECKP; plan.md §13 still carries the stale 7.3 — SYNC REQUIRED**; members A-F: E translation-path read (Low), F baseHref raw HTML injection (Low-Med, both stacks, filing-relevant, compiled demo pending)).
- **M2** MCP roots-escape (Low-Med; residual file-now recommendation; steering chain armed-but-unconfirmed, two closing branches).
- **D3** fork guard (Low; **file-now strategy** — angular/components #33632 co-discovery OPEN; corrected budget numbers: issue_labels 7-10 + AI-key, labels 8-12, per-INSTALLATION org-wide 5,000/hr budget, single coordinated attacker EXCEEDS (S1 120% / S5 200%)).

Five chains: C1 CONFIRMED (fixture 9/9, cmd.exe hop execution-pending) · C2 NARROWED-SURVIVES (config-as-data demonstrated in-lab; wire-2 private-fork demo = the only missing rung) · C3 ARMED-WITH-ESTIMATED-FOLLOW (real desktop-client chain demo = the closing branch) · C4 CONFIRMED venue-restricted · C5 FUTURE-CONDITIONAL (5-trigger watch-list).

## 2. The lanes (each with an owner round)

1. **L1 — W1 Windows E2E (the missing rung).** Execute `WINDOWS-E2E-FIXTURE.md` on any available Windows host (local, no wires): registry server + malrepo + `ng add`/`ng update` → marker execution BEFORE the confirmation gate; both manager paths (yarn-classic add, npm-default update). If no Windows host exists, document the exact blocker and finalize the static-only filing argument (already complete — the phase only ADDS the execution rung or closes the branch with reason).
2. **L2 — CURRENT-MAIN re-verification (pin is 2026-08-13; main has moved ~2 days + follow-up fixes).** Re-verify at main HEAD: M3 delete path + case-guard residual (bd413b0eb/#33312 covers the write path only — the DELETE path and the case-guard amplifier were declared likely-still-live), E1-C1 venue chain (dataPath/entry-path + i18n inliner caching refactors #33859/#33866 may have changed the bundle-embedding path), W1 quote-wrap + shell:true shape, D1 route sink, D2 getCacheBasePath twins, M2 best-practices residual. Record per-finding: still-live / fixed (with commit) / changed-shape.
3. **L3 — Wire-2 private-fork CI demo (Chain 2, OPERATOR-GATED).** Fresh operator confirmation at the moment of the act; private repo, macOS + windows runners, no secrets, the exact config-as-data malicious angular.json; cleanup path stated. If the operator declines, the config-as-data shape stays in-lab-demonstrated + mechanism-complete.
4. **L4 — Chain 3 closing branch: real-agent steering demo.** The H2 hop (an actual agent following the priority-0.9 instruction content): use the lab's own agent runtime with a fresh, unprepared context; the tsConfig-existence cross-check is the decision split (blind-test verdict: CONDITIONAL-FOLLOW). Outcome: H2 demonstrated → M2 promotion trigger branch (a) CLOSED; H2 refused → record the refusal mechanism.
5. **L5 — E1-C1 member F compiled demo + member E PoC.** Bundle the index-html generator (augment-index-html.ts:267-270 emitRaw) with a malicious baseHref → emitted index.html with the injected script; member E translation-path read (i18n-options.ts:258-262 + createTranslationLoader). Evidence → evidence/chain4/.
6. **L6 — Filing bundle completion (per-finding humanized reports).** Operator-ready, delta-first, per finding: M3+D2 ONE family report (case-guard M3-only, CI-wipe D2-primary, both Medium) + W1 (delta-first vs #32509/#32892 doctrine; CI-variant venue-split; version-check + poisoning + CI-token as context) + D1 (route-unique; app-trust scoping; REJECTED-doctrine framing) + E1-C1 (venue-split 4.0/6.3; members E/F; foxllb #33073 + doctrine) + M2 (residual file-as-is; steering chain as CONTEXT) + D3 (delta-first opening with the quantified robot-budget; #33632 race). FILING-COVER.md updated with the chain sections + the severity/vote decisions.
7. **L7 — Record sync + decision prep.** plan.md §13 severity drift (7.3 → 6.3) + any stale chain-cell numbers; E1-C1 finding.json venue-split recording decision (separate SSR-venue record vs report-only — operator input, prepare both options); W1 CI-variant severity recommendation (Medium?) with the derived CVSS; M3+D2 one-report vs two (prepare both filing shapes).
8. **L8 — M3KP + W1KP pending actions.** M3 remediation sharpening (Chain-2 environment:'ci' condition line); W1 filing-reality filter (npm config walk-up: the CI shape requires ng add/ng new INSIDE the checkout subtree).
9. **L9 — M2 trigger closing-branch documentation + D3 watch-list refresh.** M2: the two branches (in-lab real-agent demo / documented shell-less deployment evidence) with the current status; D3: the 5-trigger watch-list re-checked at current main (guard line, action fs-ops, sibling workflows).
10. **L10 — Dev-infra handoff finalization.** The 4 NEW advisory-grade items + F4 disposition (branch-manager auto-merge gating as positive control) + the googlers/Gemini corrected rows; the operator note (never writes into the dev-infra engagement) is the deliverable shape.
11. **L11 — Chain-2 Actions-minute burn sub-claim.** Quantify the fork-PR flood billing burn (per-event minutes × sustained rates) as a filing line for the C2 config-as-data shape (KP-C2 added it; needs the numbers artifact).
12. **L12 — Cleanup + close prep.** Cleanup ledger final audit (deepsec workspace + opencode-key credential rm -P, all /tmp scratch, chain fixtures, w1poc, d3-budget-math); the stale close-request disposition (auth-close-cli-2026-08-15 — superseded; resolve-authority options documented); engagement stays OPEN with the operator's decision points listed.

## 3. Method — unchanged discipline

`engine/whitebox-analysis.md` funnel; kill-pairs before any fold; gates G0-G6 before any promotion;
severity = marginal delta; wire-2 only with a fresh operator confirmation at the moment of the act;
attribution boundary (dev-infra-rooted → cascades.md); local lab only; no real credentials; cleanup
ledger for every artifact; redaction always. The G0 path-check gotcha (backticked non-artifact paths
block) and the silent str.replace no-op failure mode are KNOWN lessons — grep after every record edit.

## 4. Round structure (8+ rounds × 8; Wave D = the first 4)

- **D-R2 / R1 (16):** execute the highest-value lanes — L1 (Windows E2E attempt or blocker-final),
  L2 (current-main re-verification, 4 lanes: M3/E1-C1/W1+D2/D1+M2), L4 (real-agent H2), L5 (member F
  demo + E PoC), L6 (filing drafts x3: M3+D2, W1, D3).
- **D-R3 / R2 (16):** kill-pairs + verify — reviewers on every L1/L2/L4/L5 claim, L6 drafts
  cross-checked against REPORTs, L3 wire-2 request prep (operator gate), L7 record-sync prep.
- **D-R4 / R3 (16):** synthesis + records — L6 completion (E1-C1, D1, M2 drafts), L7 record sync
  APPLIED, L8/L9/L10/L11 lanes, L12 cleanup + close prep, phase-terminal drafting.
- **R4-R8 (8 per round):** filing-bundle final QA (operator-readiness pass), FILING-COVER final,
  novelty re-check on the changed-main items, chain-matrix refresh, current-main re-verified
  findings updates, memory-disposition refresh (PC-1..PC-12 + any new), final records consistency,
  and the phase-terminal verification round (matrix of lanes × verdicts + kernel + gates).

## 5. Terminal states

Per lane: `resolved` (rung closed / demo built / bundle item operator-ready) · `closed` (blocker
exact or operator-declined) · `blocked` (the specific missing mechanism) · `needs_more_evidence`
(the concrete next test). The phase terminal is **the filing bundle operator-ready** (7 findings, all
humanized, delta-first, FILING-COVER complete) + **each closing branch resolved-or-blocked-with-
reason** + **current-main status recorded per finding**.

## 6. Calibration

Realistic yield: L2 (current-main) is the highest-value — it either confirms the findings survive
into the current release (filing-relevant) or discovers the maintainers fixed something (filing-
critical). L4 (real-agent H2) is the most likely to close a branch. L1 (Windows) stays
environment-gated. Both a bundle-complete phase and one that surfaces a current-main fix are
successes. The failure to avoid: filing without the current-main re-verification, or a closing
branch left silently open.

## 7. First move

1. Record the Wave-D D-R1 plan (this prompt) into plan.md §14 + rounds.md E3 rows.
2. Launch D-R2 (16 subagents) immediately per the R1 structure above.
3. Funnel D-R2 the same session; record; re-route.

**Do not file, submit, publish, or contact Google, Angular, or any maintainer. The operator files.**

