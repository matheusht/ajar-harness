# P2 lab — crash-family reachability (validation.js:2289 / 1678 / 1662 / 2450)

Pinned ocore: `a7eb776afc68ed4bed05ba554f7f1e95f5d49b44`. All experiments drive REAL pinned code
through its real entry points (`validation.validate`, `private_payment.validateAndSavePrivatePaymentChain`
→ `validateDivisiblePrivatePayment`). Ledger rows are seeded directly (schema-exact, mirroring
`writer.saveJoint` + the private-chain flow) because the lab cannot stand up a full real network
(no genesis joint content in this repo). Absolute heights are stand-ins; the RELATIONS the code
checks are what matter.

## How to run (independent reviewer — each run takes ~1 min)

```
cd /Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore
LAB_NO_NETWORK=1 node lab-obyte.js <harness>/evidence/lab/p2/exp-a-preemption.js   # expect EXIT 0 + 3 clean rejections
LAB_NO_NETWORK=1 node lab-obyte.js <harness>/evidence/lab/p2/exp-b-1678-crash.js  # expect EXIT 1 + "unreachable code, conflicting spend proof in unit ..."
LAB_NO_NETWORK=1 node lab-obyte.js <harness>/evidence/lab/p2/exp-c-elements-flow.js # expect EXIT 1 + "spend proof didn't help: ..." (see note below)
```

`<harness>` = `/Users/matheusvsky/Documents/trab/llm-redteam-harness/engagements/obyte-ocore-2026-08`.
`LAB_NO_NETWORK=1` skips the module-load auto-start (`network.js:4347 start()`), whose boot-time
`initCaches` would run against the unseeded DB; the scripts seed first, then call `storage.initCaches()`
themselves (a lab-harness adaptation — `evidence/lab/lab.js` gained the `LAB_NO_NETWORK` flag).
The migration "duplicate column name: my_party_name" race at boot is pre-existing and nondeterministic;
re-run if it fires (it is unrelated to the experiments).

## What each experiment shows

| exp | scenario | expected | observed (2026-08-11) |
|---|---|---|---|
| a | B carries no `spend_proofs` (private payment, payload_location none) | clean reject "private payment must come with spend proof(s)" | `ifUnitError` same message — flow (c) REFUTED (validation.js:1614) |
| a | U1 conflict `sequence='good'`, included in B's parents | clean message-level reject "conflicting spend proof in inner unit" | `ifUnitError` same message — the input-level 2289 site is PREEMPTED |
| a | B single-authored with `address` in spend_proofs | clean reject "when single-authored, must not put address in spend proof" | `ifUnitError` same message — 1662 precondition (address ∈ authors) unachievable |
| b | U1 conflict `sequence='temp-bad'`, on MC, included | **process crash** (1678 "unreachable code") | `EXIT=1`, `Error: unreachable code, conflicting spend proof in unit ...` |
| c | elements flow, B parents do NOT include U1 (fork — consistent) | accepted fork, no crash | `ifOk (accepted as forked doublespend, NO crash)` |
| c | elements flow, B parents INCLUDE U1 (good) | 2289 "spend proof didn't help" throw | crash — but this state is **ledger-inconsistent** (B cannot be saved: see verdict) |

## Claim tuple (per finding candidate)

- **1678 crash (CONFIRMED):** target `ocore@a7eb776`; entry: any full node validating an attacker
  unit B that (1) carries a spend proof P for private output X, (2) parents on (or descends from)
  unit U1 whose `spend_proofs` record `(P, owner)` has `sequence='temp-bad'` and
  `main_chain_index <= B.last_ball_mci`; precondition: U1 is in the MC-inclusion → stability
  resolution window (attacker arranges U1/U2 input conflict per validation.js:1303-1339, then times
  B within the window); mechanism: `checkForDoublespends` (validation.js:1655) → included + temp-bad
  → `throw Error("unreachable code, conflicting spend proof in unit ...")` (validation.js:1678)
  inside the graph callback → uncaughtException → process death (network.js:4367 handler re-throws);
  effect: deterministic full-node crash, repeatable (B re-delivery); negative control: U1 `good`
  → clean rejection (exp-a), U1 not-included → fork accepted (exp-c), U1 `final-bad` → accepted.
- **2450 crash (CONFIRMED statically; same window):** `validation.js:2450` `throw Error("spending a
  stable temp-bad output")` — transfer path, fires before `checkInputDoubleSpend` when the src
  output's unit is `temp-bad` + `main_chain_index <= last_ball_mci`. Same attacker-reachable window;
  applies to public assets too (no spend_proofs required).
- **2289 "spend proof didn't help" (REFUTED as reachable):** the message-level
  `validateSpendProofs` (validation.js:1640-1665) runs first and cleanly rejects every included
  conflict (`good`/too-young) or accepts forks/final-bad — identical decisions to the input-level
  graph check (empirically: exp-a 'good', exp-c fork). A state where B is SAVED (so its private
  elements can be validated) while an included `good` conflict exists is ledger-inconsistent: U1's
  spend_proofs row is inserted at U1's save (writer.js:279-286), and B's parents including U1
  require U1 saved before B's validation — so B's message-level check saw the row (exp-a 'good'
  rejects). The elements flow (exp-c included) can only reach it with a state that cannot occur.
- **1662 "spent from another address" (REFUTED):** message-level spend_proofs addresses must be
  authors (validation.js:1551-1568; exp-a 'addr-binding'); input-level owner-in-authors precedes
  checkInputDoubleSpend (validation.js:2430/2478). The throw is also inside the async iterator →
  caught → clean rejection even if it fired.
- **(c) missing spend_proofs (REFUTED):** validation.js:1614 "private payment must come with spend
  proof(s)".

## Residual risks / honesty notes

1. Ledger state is synthesized (no real network). The validation code is 100% real; the reachability
   of the seeded states is argued statically (temp-bad lifecycle validation.js:1303-1339 + writer
   temp-bad marking).
2. The 1678 window duration (MC inclusion → stability resolution) is network-timing-dependent;
   the attacker must fire B within it. Programmatic timing is feasible but unmeasured here.
3. `is_stable=0` + `main_chain_index` set models the temp-bad-on-MC state; real heights satisfy
   `U1.mci < B.last_ball_mci` trivially (mci=0/0 in the lab is the boundary where the too-young
   check is off).
4. DoS-coordination classification (in/out of bounty scope) is the orchestrator's call — the crash
   is on an INVALID unit; a node-side catch fixes it (out per strict rule), but crash-loop
   persistence + network-wide effect may classify it as temporary freezing of transactions.
