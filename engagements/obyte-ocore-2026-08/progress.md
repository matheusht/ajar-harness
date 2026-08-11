# progress.md — obyte-ocore-2026-08

Newest first.

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
