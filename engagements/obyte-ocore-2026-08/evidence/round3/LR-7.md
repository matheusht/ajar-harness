# LR-7 — Witness / OP protocol depth

**Target:** ocore pinned `a7eb776afc68ed4bed05ba554f7f1e95f5d49b44` (verified `git rev-parse HEAD`).
**Role:** round-3 terminal audit of the witness/OP surface (round-0 family f2/f16 residuals + the
f1-T4 lead). Local source analysis only; no live contact.

## Verdict (one line)

**Held across all three questions** — the witness-list mutation surface (f1-T4 lead), the
paid-witnessing earnings spend paths (f16 gap), and the OP-list vote counting edges show no
attacker-reachable defect; the vote-count surface is governance-excluded by program policy.

---

## Q1 — witness-list mutation distance rule (f1-T4 lead)

### 1a. The 512000 gate is real but inert for its exploit shape

`validateWitnesses` → `validateWitnessListMutations` (validation.js:888-897):

```js
storage.determineIfHasWitnessListMutationsAlongMc(conn, objUnit, last_ball_unit, arrWitnesses, function(err){
    if (err && objValidationState.last_ball_mci >= 512000) // do not enforce before the || bug was fixed
        return callback(err);
    ...
```

A unit attached below MCI 512000 whose witness list carries >1 mutation is NOT rejected for the
mutation (`err` ignored → falls through to the witness-address/known-good/retreat checks). The
mutation rule itself (`determineIfHasWitnessListMutationsAlongMc`, storage.js:2102-2136): the
unit's witness list must share ≥ `COUNT_WITNESSES - MAX_WITNESS_LIST_MUTATIONS` = **11 of 12**
witnesses with every MC unit between the unit and the last ball.

**Why inert as a bypass:** the mutation affects only the unit's OWN witnessed-level computation and
the units that reference it. Per the round-2 KP-F2-link verdict (Q1/Q2), a unit attached to an old
DAG part (which is the only way to get `last_ball_mci < 512000` while the network is past it)
cannot win best-parent selection (witnessed level is ancestry-derived and old), cannot reach the
MC, cannot stabilize, and its outputs are economically inert. An old-attached unit with a mutated
witness list (e.g., 12 attacker-chosen addresses) computes witnessed_level=0 — the OPs are not in
its ancestry — and never executes anything. The mutation check protects exactly the units that
matter (those on the MC path); the gate's skip applies only to junk.

**Additional structural protections verified:**
- A referenced `witness_list_unit` must be serial + stable + before last ball (validation.js:945-950)
  — you cannot reference an arbitrary attacker-authored list.
- Pre-v4 units without a valid witness list of exactly 12 are rejected
  (`"no witnesses or not enough witnesses"`, validation.js:984).
- v4 units have no per-unit witness lists (`"should have no per-unit witnesses since version 4.0"`,
  validation.js:755); their witnesses are the OP list from system vars (validation.js:924-926).
- Witness addresses must be known/stable/good and definition-reference-free
  (`checkWitnessesKnownAndGood`, `checkNoReferencesInWitnessAddressDefinitions`,
  validation.js:872-878, 966-976) — an attacker cannot name non-existent addresses as witnesses
  (that is itself a rejection path).

### 1b. Witnessed-level retreat non-enforcement below its upgrade MCI

`checkWitnessedLevelDidNotRetreat` (validation.js:899-926): below
`witnessedLevelMustNotRetreatUpgradeMci` the retreat check returns early (`// not enforced`).
Same old-DAG inertness: a retreating old unit cannot stabilize (KP-F2-link). The
`throw Error('no max_parent_wl')` at :912 is unreachable — `max_parent_wl` is set in
`validateParents` (validation.js:686, :699), which runs before `validateWitnesses` in the
pipeline.

**f1-T4 lead disposition: CLOSED** (held — gate real, exploit shape inert by stabilization).

## Q2 — paid-witnessing earnings spend validation (f16 gap)

### 2a. Witness identity for payment is MC-unit-derived (side-chain flip defended)

`readMcUnitWitnesses` (paid_witnessing.js:229-246): for v4+, `storage.getOpList(main_chain_index)`;
pre-v4, the MC unit's `witness_list_unit` (RAM-vs-DB cross-checked: `throw Error("witness_list_units
are not equal...")`). The code comment at :142 states the defense explicitly: *"we read witnesses
from MC unit (users can cheat with side-chains to flip the witness list and pay commissions to their
own witnesses)"* — the attacker's side-chain witness-list cannot redirect commissions because the
payment goes to the MC-designated list, not the unit-designated list. (Confirms f16-H5.)

### 2b. Earnings spend path (mc_outputs.js) is bounded

- `calcWitnessEarnings` (paid_witnessing.js:15-27) requires `COUNT_MC_BALLS_FOR_PAID_WITNESSING+2`
  stable MC units after `to_main_chain_index` before any earnings are even computed → earnings are
  finality-gated.
- `findMcIndexIntervalToTargetAmount` (mc_outputs.js:49-103): sqlite branch caps the read at
  `ceil(target_amount/MIN_MC_OUTPUT)+1` rows (MIN_MC_OUTPUT=10 for witnessing) — bounded scan;
  overpay is ≤ MIN_MC_OUTPUT−1 = 9 units (handled as change by the caller); `bHasSufficient=false`
  → the caller handles a partial interval (no negative/absurd amounts).
- `readNextSpendableMcIndex` (mc_outputs.js:11-29): spends are serialized by the inputs table
  (type+address ordered by `to_main_chain_index DESC`); `sequence!='final-bad'` filter means a
  voided spend re-opens its interval — correct (the voided unit's outputs are unspent on archive;
  if they were consumed-and-not-unspent, the `is_spent=0` filter yields `ifNothing` — a self-loss
  for a witness who double-spends their own earnings, not a theft).
- `calcEarnings` (mc_outputs.js:105-122): `+address=?` on a base32 string — the P4 family
  (unary-plus no-op on non-numeric strings, empirically verified on 4 engines); estimation/display
  function only.
- `buildPaidWitnesses` (paid_witnessing.js:262-305): count=0 → "nobody witnessed, pay equally to
  all" — bounded by the witness-list size; RAM-vs-DB cross-checks (`throwError("different count/
  amount...")`) on every aggregation.

**f16 gap disposition: CLOSED** (held — spend-path math bounded, identity MC-anchored).

## Q3 — OP-list vote counting edges (countVotes)

### 3a. Emergency path merges unstable votes — governance-excluded

`countVotes(conn, mci, subject, is_emergency=1)` (main_chain.js:1520-1630):
- `getUnstableVotes` (main_chain.js:~1900-1918): unstable 'good' units' `system_vote` messages for
  `op_list`, at least `EMERGENCY_COUNT_MIN_VOTE_AGE` (1h) old, sorted deterministically by
  (timestamp, level), applied in order with per-address override semantics.
- Reachable by anyone paying `SYSTEM_VOTE_COUNT_FEE` (1e9) via a `system_vote_count` message
  (writer.js:640, validation.js:1911), gated by `EMERGENCY_OP_LIST_CHANGE_TIMEOUT` (3 days).
- The unstable-vote inclusion is the recent hardening (commit `1f3915b` "add unstable voters in
  emergency count") — an intentional design change, not a gap.
- **Classification:** balance-weighted OP-list influence is a **basic economic/governance attack,
  explicitly excluded** by `program-policy.md` ("Basic economic and governance attacks... Sybil
  attacks. Centralization risk"). The f2-T-f2-06 disposition (held/out-of-scope) stands.

### 3b. Vote balance accounting — recent fix verified

The `countVotes` balance query (main_chain.js:~1547-1565) counts stable-good outputs with **no
stable-good spender** (NOT EXISTS subquery over inputs) — the fix for the "final-bad spender
undercount" (f2 noted it). Verified correct: an output whose only spending unit went final-bad is
correctly counted as unspent (the inputs row is excluded by `su.sequence='good'`).

### 3c. Vote timeframe expansion — bounded

`since_timestamp` expands 1 year at a time until ≥ `SYSTEM_VOTE_MIN_SHARE` of supply has voted or
the activation timestamp is reached (main_chain.js:~1585-1596) — deterministic, no edge found.

**Q3 disposition: CLOSED** (held — governance-excluded; accounting fix verified; edges bounded).

---

## Additional observations (all held)

1. **Unary-plus on string columns in the witness/vote queries** (`+sequence='good'`,
   `+change_units.sequence='good'`, `+address=?`, `+address IN(?)` at validation.js:845-874,
   paid_witnessing.js:280, mc_outputs.js:115) — the P4 family. Empirically verified on sqlite,
   MariaDB 12.3.2, MySQL 8.0.46, MySQL 5.7.44 (round-1 P4 report): unary plus on a TEXT column is
   a no-op for non-numeric strings; `sequence`/addresses are never numeric. Safe on all supported
   engines. Hygiene note only (matches P4's residual).
2. `readMcUnitWitnesses` RAM-vs-DB `throw` — defensive consistency guard; reachable only on
   internal state divergence (a bug, not attacker input); would crash a node that diverged, which
   is the fail-loud behavior this codebase prefers.
3. `initial_votes.js` SQL is constant-only (compile-time OP addresses/voters — no user input).
4. `my_witnesses.js` is wallet-config (operator choice of witnesses) — no consensus surface.

## Gaps not covered and why

- **Live multi-node witness simulation** (two-node lab with synthetic OPs to empirically confirm
  an old-attached unit failing to stabilize): the lab cannot construct the witness state; the
  deterministic chain (witnessed level → best parent → MC → stabilization) is source-verified and
  matches KP-F2-link's independent trace. Recorded as the engagement's known residual.
- **Emergency-count transient influence window** (an unstable 'good' vote later going final-bad):
  governance-excluded; the next stable count corrects the op_list. Not chased further.
- **`graph.readDescendantUnitsByAuthorsBeforeMcIndex` cost profile** (per-MC-unit graph walk):
  node-side-fixable DoS, out-of-scope class (f16-T4 already recorded it).

## Files

- This report: `evidence/round3/LR-7.md`
- No scripts run (pure source trace; anchors verified against the pinned tree).
