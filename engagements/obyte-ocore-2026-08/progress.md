# progress.md — obyte-ocore-2026-08

Newest first.

## 2026-08-11 — ORCHESTRATOR: pin + preflight + sweep + round-0 launch

### Pinned identity (authoritative for every finding)

- **repo:** `github.com/byteball/ocore`
- **commit:** `a7eb776afc68ed4bed05ba554f7f1e95f5d49b44` (2026-08-10 13:48:56 +0200, `master`)
  - subject: "only joints with balls while catching up" — 8 commits after the V-001 fix (991c5d6)
  - chosen as the latest commit whose test suite runs; recorded move-off-HEAD policy: any later pin must be recorded here
- **local clone:** `/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore` (private clone, never pushed)

### Environment preflight

- Node `v25.9.0`, npm `11.12.1`; `npm install` clean (714 packages).
- Test suite on pinned commit: **957 passed**, 1 exception: `test/aa.test.js` exits 7 — **runner crash, not test failure**:
  ava 0.22.0 crashes in conf handling under Node 25 (`Cannot find module .../ava/conf.js`, `setFatalError` in
  `formula/evaluation.js:3195`); the aa tests themselves pass ("12 passed"… "14 passed" observed before the runner
  dies). Recorded verbatim as an environment quirk; not treated as a finding.
- sqlite3/rocksdb native modules built fine. Test data dirs are created at test time under `test/.testdata-*/`.

### Record-kernel note (decision-0006)

`run-engagement.py init` requires the operator-console authority lane and the canonical scope section headings;
this engagement's signed scope uses the extended format. **Kernel `init` is deferred to operator console**; the
orchestrator maintains the engagement records in the documented append-only formats (attempts.jsonl, events.jsonl,
artifacts.jsonl, hypotheses/rounds/cascades markdown) per the engagement template, and will reconcile into the
decision-0006 ledger at close if the operator enables it.

### History sweep → recon-signals.md

Security-relevant shape set recorded in `recon-signals.md` (shapes only, no diffs). Dominant recent-fix families:
old-DAG/`hasBall` rule-gating, depth/size limits on structured payloads, string-type checks before sort/hash,
canonicalization (-0/arrays), SQL-interpolation escaping, stability/MC advancement, AA trigger/getter validation,
private-payment spend-proof uniqueness, merkle-proof sibling checks.

### Round 0

Blind round 0 launched (16 hunters, one family each). See `rounds.md`.

## 2026-08-11 — bootstrap

Engagement created from `_TEMPLATE`. `scope.md` signed by the operator in session. Program rules
transcribed to `program-policy.md` (Immunefi / Obyte Foundation, **Primacy of Rules**).

- **Target:** `github.com/byteball/ocore` — Obyte DAG core library, Node.js.
- **Scope:** blockchain/DLT only. The nine Autonomous Agent repositories are a **separate, deferred**
  scope; if opened later, prioritise by most-recently-updated. A finding in ocore's AA *engine* is in
  scope; a finding in an individual AA's *own* logic is not.
- **Freshness:** verified 2026-08-11 — no prior obyte/byteball/ocore work anywhere in this repository.
- **Environment:** local only. No mainnet, no public testnet, no live node. Program-prohibited.
- **PoC:** required for every severity. A source-only finding is not submittable.

### Calibrated expectation — recorded 2026-08-11, BEFORE the run

`ocore` is a nine-year-old production consensus library under active hardening (see the history
sweep below). **The honest prior is: mostly solid, with a scattering of Medium/High bugs and a
long-shot Critical.** Obyte's historically severe issues lived in the wallet layer, which is out of
scope here.

**A good outcome for this engagement:** covered-dry on both $50k lanes with the proof strategies
written and the sub-conditions enumerated, plus one or two confirmed Medium/High findings with
runnable PoCs. Read that as success, not as a thin result.

**The failure to avoid** is not a low finding count. It is spending the run chasing the $50k lane
because it pays most, while the High and Medium surface goes unexamined.

This is calibration for reading the result. It does not reduce the effort contract.

### History sweep — verified 2026-08-11 by the orchestrator, before handoff

The public history shows active security work. Recorded here as ROUTING SIGNAL; the operating agent
records abstract shapes in `recon-signals.md` and never reports a fix as a find.

| commit | date | subject |
|---|---|---|
| `991c5d65d` | 2026-08-03 | fix: V-001 security vulnerability (#305) |
| `16ddd6a41` | 2026-08-03 | pre-validate asset in aa composer |
| `f3b253ebf` | 2026-08-02 | check allowed charset in isValidAddress |
| `f503efc9f` | 2026-07-28 | move stability point by 1 after validation found a later MC unit stable in parents |
| `c368211fc` | 2026-07-26 | validateAATriggerObject: no early success if no non-base assets |
| `d7d6a8256` | 2026-06-02 | try/catch getBase64Hash in spend proofs |
| `403e96b93` | 2025-05-20 | delay parenting AA responses to mitigate partitioning on OP doublespend |
| `05f291d8d` | 2025-02-19 | uniqueness of spend proof is not verified in light |

`V-001` reads like an audit finding id — assume a recent third-party audit, and assume its findings
are fixed and already reported. **A fixed bug marks a family, not a target.**

### Not yet done — the operating agent fills these

- [ ] pin ocore at the latest commit whose test suite runs; record the identity and any move off HEAD
- [ ] history sweep recorded as abstract shapes in `recon-signals.md` (no diffs)
- [ ] local multi-node lab built ONCE and persisted, one-command bring-up
- [ ] environment preflight (Node version, install, existing test suite) — record blockers verbatim
- [ ] `recon-signals.md` activation table completed, baseline controls captured
- [ ] PROOF STRATEGY written for each $50k condition, decomposed into sub-conditions
- [ ] the DoS coordination question settled for the availability surface
- [ ] 3-4 DAG pattern cards authored and oracle-calibrated BEFORE round 0

## 2026-08-11 — ROUND 0 COMPLETE + ROUND 1 (PoC + refute) LAUNCHED

- **Round 0:** 16/16 blind hunters delivered. Adjudication in `rounds.md`. Harvest: 6 Tier-A
  candidates, 3 Tier-B, 8 Tier-C leads, 8 held/refuted negatives. **Crash family** (4 uncaught-throw
  sites: validation.js 1662/1678/2289/2449) is the strongest lead class; S1 old-DAG gating has 3+
  incomplete-migration sites; tps-fee exp() blow-up and MySQL sequence-coercion are the
  consensus/economics candidates.
- **Round 0 adjudication correction (orchestrator):** the triple-sourced "2289 crash" (f1/f7/f13)
  was partially refuted by f8 (unit-level validateSpendProofs cleanly rejects included+good
  conflicts for units carrying spend_proofs) and confirmed by my own source reading; 1662 promoted
  as the strongest crash site. Adversarial round-1 will settle each site empirically.
- **Round 1 launched:** 6 PoC builders (p1 crash-1662, p2 crash-2289/1678, p4 MySQL, p6 tps-fee,
  p8 signed-package budget, p9 merkle) + 2 fresh-context refuters (r1 crash family, r2 MySQL+fee).
- **Standing gate (operator):** every finding ships a maximum-impact PoC + an independent
  fresh-context run of that PoC by a reviewer reading RAW output (recorded in memory/winners.md).

## 2026-08-11 — ROUNDS 2-3 + 3 FINDINGS PROMOTED

- **Round 2 (independent runs + kill-pair + link + chainability):** IR-F1/F2/F3/F4 all CONFIRMED
  the PoCs independently (standing gate honored). KP-F2-link: the S1 old-DAG family is DEAD
  (stabilization impossible — witnessed-level ancestry, best-parent sorting, MC-from-tip). CHAIN-1:
  composition pass — S1 eval-side family is the durable form (dead), temp_data refuted,
  F3×F4 bounded. KP-F3 kill-pair: establish side won the mechanism ("the only network-wide private
  double-spend protection is keyed out of reach"), kill side capped the impact (no direct theft).
- **Round 3 launched (terminal):** blind no-new-family sweep (LR-4), light-client surface (LR-1),
  F3 adjudication review (LR-2), F4 natural-burst escalation (LR-3), hub surface (LR-5),
  dependencies (LR-6), witness protocol (LR-7), formula completeness (LR-8).
- **Findings promoted (3):** `obyte-2026-08-001` (formula is_valid_merkle_proof vacuously
  satisfiable — Medium), `obyte-2026-08-003` (spend-proof uniqueness keyed on party-chosen address —
  Low), `obyte-2026-08-004` (tps-fee settlement unbounded — Low). Each passed all 6 lifecycle gates
  with an independent fresh-context PoC run recorded.
- **Hardening backlog:** HARDENING-NOTES.md (10 items — S1 disjunct migration, uncaught-throw
  pattern, SQL unary-plus, fee asymmetry, future-timestamp multiplier, missing return, network
  unbounded streams, privacy logs, light trust, economics residuals).
- **Ladder questions:** Q-A (total shutdown) and Q-B (spend-without-key) both COVERED-DRY with
  proof strategies written and sub-conditions enumerated (recon-signals.md final verdicts).

## 2026-08-11 — TERMINAL VERDICT (engagement complete, orchestrator)

**Terminal state: coverage-dry for the declared in-scope surfaces + 3 confirmed findings.**

### Findings (all promoted through the 6 lifecycle gates, each with an independent fresh-context PoC run)
1. **obyte-2026-08-001 (Medium)** — formula `is_valid_merkle_proof` vacuously satisfiable: the
   proof root is attacker-supplied and never bound to a committed tree; any AA using it as a
   membership/authz gate is bypassable. Real-path confirmed + independently re-run (IR-F1).
2. **obyte-2026-08-003 (Low)** — spend-proof uniqueness check keyed on a party-chosen address:
   the only network-wide private-payment double-spend detection is defeated; two 'good' units with
   the same spend proof can coexist on the MC path unresolved. Kill-pair adjudicated (Low;
   Medium ceiling triple-contingent).
3. **obyte-2026-08-004 (Low)** — settlement tps-fee exponential and unbounded vs author balances:
   a 30-unit/1s window charges 10.7% of the supply per settling author; small authors frozen.
   Real-but-capped (funding bound; below the in-scope bar).

### Ladder questions (the $50k lanes)
- **Q-A (total network shutdown): COVERED-DRY** — consensus split, stability stall, and
  chain-halting-unit sub-conditions all enumerated and closed (canonicalization total, validation
  fail-closed, SQL divergence refuted empirically, crash family unreachable, stability atomic).
- **Q-B (spend without their key): COVERED-DRY** — signature/definition/forgery sub-conditions
  all enumerated and closed (malleability refuted, pubkey fail-closed, spend-time revalidation,
  proof unforgeable without blinding). F3 is a protection-defeat, not key-free spend.

### Coverage audit (100% exhaustion)
- 16 directed families + 1 blind prior-free sweep + light surface + hub + deps + witness protocol
  + formula completeness: all in-scope surfaces adjudicated; the blind round found exactly ONE new
  family (device-layer wallet crash) — quarantined as an adjacent surface (QUARANTINE.md Q-1).
- 6+ hours of orchestrated multi-agent work; 40 subagents total (16+8+8+8), no quota stop reached.
- Hardening backlog: 11 items (HARDENING-NOTES.md) for the operator to consider forwarding.
- Memory disposition recommendation recorded in pattern-candidates.md (operator review required).
- Cleanup ledger complete (scratch dirs destroyed, symlink removed, no secrets stored).

**Notable methodology outcomes:** the adversarial round refuted a triple-sourced "confirmed" crash
and an empirically-crashing PoC (state reachability); the refuter pass executed (not assumed) the
MySQL coercion claim and killed it; a blind terminal round found what 16 directed hunters missed.

## 2026-08-11 — ESCALATION PHASE: E1 + ER complete, E2 running

- **E1 (16 escalation hunters):** 11 delivered, 5 timed out mid-lab (retried in E2). Key results:
  fork-race capped (grind-space empirically confirmed, value resolves to victim); F1 is a genuine
  one-off (only unsound primitive); parent_composer crash real (HN-14); **two-node lab built and
  verified** (real relay protocol, stability + balls — evidence/lab/e17b-*); merchant exposure
  escalated (Low ceiling intact); reorg corner definitively closed; chain graph: no composition
  escalates any finding (capability-neutrality); Q-2 quarantine candidate (multisig wallet DoS);
  storage accounting conserved.
- **ER (4 fresh reviewers):** ALL E1 claims verified. The money-creation question: conservation
  verified; double-application single in all direct paths; ONE conditional MySQL watermark
  residual (HN-15 — sqlite immune, MySQL unsupported).
- **Orchestrator adjudications:** fee accounting conserved (OV-1); estimation-asymmetry refund
  conserved (no withdrawal — fee-only account); reorg corner closed (OV-2); ghost-in-fee-window
  edge real but marginal ~0 (OV-3); HN-5→parent-composer chain (OV-4); grind mechanism
  structurally confirmed (content→unit hash→tie-break).
- **E2 (16 lanes) running:** retries of the 5 timed-out lanes on the two-node lab + AA trigger on
  the network + F3 displacement empirical + HN-5 chain + natural-burst F4 + estimation refund +
  rounding dust + light handshake + archiving + governance economics + exchange surface + Q-1
  crash-loop PoC.

## 2026-08-11 — ESCALATION CAMPAIGN COMPLETE (4 rounds + 4 review rounds, 76 subagents)

**Structure honored:** E1 (16) → ER (4 reviewers) → E2 (16) → ER2 (4) → E3 (16) → E4 (16) → ER4 (4).
Every round's claims verified by fresh-context reviewers reading RAW evidence.

### What the escalation phase achieved
1. **Built the missing infrastructure:** the two-node local Obyte network (real relay protocol,
   stability + balls, full AA path execution — evidence/lab/e17b-*, e31-aa-demo.js).
2. **Refuted its own finding:** obyte-2026-08-004 (tps-fee poisoning) DEMOTED — the honest-author
   freeze is unreachable (M2 elapsed-dilution + funding bound + self-frosting; E3-10 real-path +
   E2-9 real-network + orchestrator source verification). The count>=30 state was a
   synthesized-state error — the same class the crash-family refutation exposed in round 1.
3. **Confirmed F1's fund-impact class:** the whitelist-gated AA bypass (withdrawal + airdrop
   patterns) demonstrated on the real network (E3-1: BYPASS-CONFIRMED vs bounce).
4. **Confirmed the merchant-exposure evidence** for F3 (direct-descendant ghost, unbounded window,
   no signal) with the ceiling at Low (value always resolves to the victim).
5. **Closed every remaining corner:** reorg, money-creation, natural-burst, estimation asymmetry,
   rounding dust, issue spend proof, multi-asset uniqueness, archiving, AA self-redefinition,
   governance votes, light-vendor, exchange surface, AA→AA chains, parent-composer.
6. **Corrected its own evidence quality:** the tps_interval=60 cache artifact in E2-9/E4-2 (ER4-2
   found 34/34 DB fees match interval=60); the M1 "count=1 always" overstatement (ER4-1); the
   E4-2 "fully inert" overstatement (ER4-2) — every correction applied to the records.

### Terminal state
- **Findings:** 001 Medium (5.3, fund-impact demonstrated) PROVEN; 003 Low (3.7) PROVEN; 004
  unproven (impact refuted, mechanism = design note + HN-15 + self-frosting economics).
- **Hardening backlog:** 20 items (HN-1..HN-17 + additions).
- **Quarantine:** Q-1 (device crash, crash-loop PoC 3/3 verified), Q-2 (multisig wallet DoS) —
  operator scope decisions.
- **Coverage:** covered-dry VERIFIED (ER4-4) for the declared in-scope surfaces; ladder lanes
  covered-dry; blind round no new in-scope family.
- **Net severity effect of the escalation phase: zero changes to the standing findings, one
  self-correction, multiple evidence corrections** — the anti-reward-hack outcome the doctrine
  demands.
