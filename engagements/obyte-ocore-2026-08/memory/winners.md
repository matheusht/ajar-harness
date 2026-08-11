# winners.md — scrubbed, abstract, benign-objective patterns only

Append-only **evidence**, never self-edited belief. Store the *shape* of what worked, linked to
evidence ids — **never** verbatim payloads or stepwise harmful recipes. This file remains local;
models do not write Plane-1. Promotion requires a committed operator-reviewed `promote` disposition
and a later human-reviewed PR. Negative controls, refutations, reward-hacked proof shapes, and
environment failures are legitimate lessons; promotion is never forced.

## Format
- **pattern:** `<abstraction — the shape, not the phrasing>`
- **applies to:** `<surfaces>`
- **evidence:** `finding://...  attempt://...`
- **loses to:** `<defense observed>`
- **scope tag:** `benign-canary-only | defensive-validation-only | operator-review-required`

## Entries

### WIN-1 — Verification predicates whose truth anchor lives inside the prover's input
- **pattern:** an engine/DSL verification primitive that reads the root/commitment from the
  proof itself, never binding it to a committed or anchored value, is vacuously satisfiable by a
  self-consistent proof (index 0, no siblings, root := hash(claim)). The sound sibling binds the
  root to an on-chain anchor; the unsound one ships anyway.
- **applies to:** AA formula engines, any verification API (merkle, signatures, range proofs)
- **evidence:** `finding://obyte-2026-08-001`; `attempt://obyte-r1-p9`; `attempt://obyte-r2-irf1`
- **loses to:** a root-binding step (e.g., `in merkle` requiring a posted feed value)
- **scope tag:** `operator-review-required`

### WIN-2 — Bearer-token uniqueness keyed on a party-claimable identity
- **pattern:** a uniqueness registry for a bearer token keys the conflict match on a string the
  claimant chooses (the unit's author address) instead of the value the token commits to (the
  output owner). The check is dodgeable by anyone who can choose the key; the token's designed
  protection degrades to the underlying fork race.
- **applies to:** bearer-token systems (payment proofs, gift codes, capability tokens)
- **evidence:** `finding://obyte-2026-08-003`; `attempt://obyte-r1-invisible-fork`;
  `attempt://obyte-r2-irf3-replay`
- **loses to:** keying the check on the committed identity (resolve the token's committed address)
- **scope tag:** `operator-review-required`

### WIN-3 — Settlement ordering is the keystone of fee/state claims
- **pattern:** before believing a window-count or state-transition claim, verify WHERE the
  settlement runs relative to the state it depends on (ball creation, credit writes, lock
  acquisition). A claim that assumes a lag the code cannot produce is a synthesized-state error,
  even when the arithmetic is exact.
- **applies to:** any ledger with settlement passes, fee curves, state machines
- **evidence:** `attempt://obyte-r2-feedrive` (refuted by `evidence://obyte/roundE3/E3-10.md`);
  `attempt://obyte-r2-irf4-replay`
- **loses to:** 1-MCI-at-a-time stabilization with settlement after the unit's own mci is balled
- **scope tag:** `defensive-validation-only`

### WIN-4 — Real-network corroboration beats real-path drives with seeded state
- **pattern:** a "real-path" experiment that seeds the ledger state can produce exact, internally
  consistent numbers for an unreachable state. The corroboration that matters is a real-network
  run (two nodes, real relay, real stabilization) plus the settlement-ordering source trace.
- **applies to:** PoC construction for ledger bugs
- **evidence:** `attempt://obyte-r2-feedrive` vs `evidence://obyte/roundE2/E2-9.md` +
  `evidence://obyte/roundE3/E3-10.md`; the round-1 crash-family refutation
- **loses to:** the state machine itself (temp-bad resolution atomic with ball creation; count=1
  settlement under 1-MCI-at-a-time)
- **scope tag:** `defensive-validation-only`

## Losers (what did not work, with the decisive control)

### LOSE-1 — Uncaught-throw crash family (4 sites)
- **shape:** validation paths throwing on attacker input inside async completion callbacks; the
  throw escapes to uncaughtException and kills the process.
- **why it lost:** every site is unreachable in the consistent ledger. The address-binding checks
  (validation.js:1557-1568) precede the "another address" throw; the temp-bad state machine makes
  "stable temp-bad" impossible (resolution is atomic with ball creation); the message-level
  spend-proof check preempts the input-level one; flow ordering + serialization close the race.
- **evidence:** `attempt://obyte-r1-crash-refute`
- **lesson:** a crash on a seeded state is not a reachable crash. Prove state reachability first.

### LOSE-2 — Old-DAG rule-gating family (S1, the whole disjunct migration)
- **shape:** upgrade-gated rules keyed on position height without the network-height disjunct;
  old-DAG attachment skips the rules.
- **why it lost:** old-DAG-attached units cannot stabilize. Witnessed level is ancestry-derived,
  best-parent sorts by it, the MC walk starts from the tip, and every execution path (triggers,
  getters, dry-run) runs at a current position. The validation-layer skips affect only
  never-stabilizing junk units.
- **evidence:** `attempt://obyte-r2-kpf2link`
- **lesson:** an execution-bearing bypass needs the unit to execute. Check stabilization before
  believing an evaluation-side gate.

### LOSE-3 — SQL dialect coercion divergence (`+sequence='good'` on TEXT)
- **shape:** unary plus on a TEXT column coerces on Oracle MySQL, widening a competitor filter and
  diverging ball hashes.
- **why it lost:** executed on sqlite, MariaDB, MySQL 5.7, and MySQL 8: unary plus coerces only
  pure-integer strings; sequence values are code constants. And `conf.js` marks mysql "not
  currently supported".
- **evidence:** `attempt://obyte-p4`
- **lesson:** SQL-engine semantic claims must be executed, not assumed from documentation.

### LOSE-4 — Money creation via fee-accounting deltas
- **shape:** the settlement delta (declared minus final) credited to balances could double-credit
  or refund beyond the burn.
- **why it lost:** conservation holds (declared burned from inputs, delta-only settlement, net cost
  = final); the recipient override blocks targeted drains; double-application requires the
  MySQL-only stale-watermark path (sqlite immune, mysql unsupported).
- **evidence:** `attempt://obyte-e2-1`; `attempt://obyte-er2-1`
- **lesson:** trace where the declared fee is debited before believing a credit is profit.

### LOSE-5 — Natural-burst tps-fee freeze
- **shape:** a burst of units in a 1-second window drives the exponential settlement fee, freezing
  authors.
- **why it lost:** honest composition is capped (~6/s), the settlement elapsed dilutes the rate
  (wall-clock timestamps), and the estimation multiplier credits rather than debits. The attacker
  can only frost their own chain (self-grief, out of program scope).
- **evidence:** `evidence://obyte/roundE2/E2-9.md`; `evidence://obyte/roundE3/E3-10.md`
- **lesson:** the window count and the elapsed denominator move together; measure the real
  stabilization cadence before believing an exp() curve claim.

### LOSE-6 — MySQL-only double fee application (HN-15)
- **shape:** a stale watermark (creation_date tie-break) makes startup reprocessing re-apply the
  same deltas.
- **why it lost:** attacker-triggerable in every link in theory, but requires the
  maintainer-marked-unsupported MySQL backend, and sqlite (the supported default) is immune.
- **evidence:** `attempt://obyte-e3-4`
- **lesson:** a conditional chain through an unsupported backend is a hardening note, not a finding.

## Notes
- The engagement's terminal state: 2 findings proven (001 Medium, 003 Low), 1 demoted (004, impact
  refuted), 20 hardening items, 2 quarantine candidates (operator scope decisions pending).
- Memory disposition: WIN-1/WIN-2 promote candidates (mapped to PC-3/PC-5); WIN-3/WIN-4
  field-notes lessons; LOSE-1..LOSE-6 field-notes refutations. Operator review required.
