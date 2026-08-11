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
