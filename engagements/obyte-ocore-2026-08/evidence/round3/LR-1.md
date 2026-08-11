# LR-1 — Light-client surface audit (light.js, light_wallet.js, wallet.js light paths, aa_addresses.js)

**Pinned:** ocore `a7eb776afc68ed4bed05ba554f7f1e95f5d49b44` (2026-08-10). Terminal round, local-only.

## Verdict (one line)

**No reportable finding on the light surface.** The light client's confirmed state is
witness-anchored and sound; its unconfirmed state is peer-trusted by design. Three hardening notes
recorded — the most important being that light-mode `validate()` short-circuits to timestamp +
no-ball checks, so ANY connected hub can forge the wallet's *unconfirmed* view (the proofchain
membership checks that would have bound unit validity to the witness-anchored chain are commented
out in `light.js:processHistory`).

## Surface covered (files + line ranges)

- `light.js` (890 lines, full): `prepareHistory` (12-203, vendor-side), `processHistory`
  (205-431, client-side sync: witness proof → proofchain → joints → AA responses → save),
  `processLinkProofs` (789-866), `prepareLinkProofs`/`createLinkProof`/`buildPath` (613-787),
  `prepareParentsAndLastBallAndWitnessListUnit` (519-611).
- `light_wallet.js` (293 lines, full): vendor connection (`setLightVendorHost`,
  `reconnectToLightVendor`), `refreshLightClientHistory` (145-293), history request construction.
- `validation.js`: `validateLight` (96-117), the `conf.bLight` short-circuit (339-346), the light
  spend-proof branch (1668), private-attestation branch (2110).
- `writer.js:saveJoint` (24-90) — light inserts.
- `aa_addresses.js` `readAADefinitions` (34-155) — light vendor definition fetch/insert.
- `inputs.js` `getConfirmationConditionSql` (302-319).
- `wallet.js` light paths (782, 986, 1314-1345, 1433, 1564).

## Answers to the brief's four questions

### Q1 — Light proof-chain validation gaps (can a malicious vendor serve forged units/proofs?)

**The chain of stability is cryptographically anchored — sound.**
- `processHistory` → `witnessProof.processWitnessProof(unstable_mc_joints,
  witness_change_and_definition_joints, false, arrWitnesses, ...)` (light.js:215-236): witness
  signatures are verified against the light client's OWN witness list (f10's T3 layer-1). The
  `MAJORITY_OF_WITNESSES` anchor binds the last-ball set.
- Proofchain balls (light.js:237-276): every ball must satisfy `ball ===
  getBallHash(unit, parent_balls, skiplist_balls, is_nonserial)` AND be in `assocKnownBalls`, seeded
  from the witness-anchored last-ball units. Each ball's `parent_balls`/`skiplist_balls` extend the
  known set. A forged ball cannot chain to the witness anchor without witness keys. **No gap found.**

**Unit authenticity is NOT verified — the client accepts unconfirmed joints on timestamp +
no-ball only.**
- `validateLight` (validation.js:96-117) calls the full `validate()` which, in a light process,
  short-circuits at validation.js:339-346:
  ```js
  if (conf.bLight){
      if (!isPositiveInteger(objUnit.timestamp) && !objJoint.unsigned)
          return callbacks.ifJointError("bad timestamp");
      if (objJoint.ball)
          return callbacks.ifJointError(lightStableErrorMessage);
      return objJoint.unsigned ? callbacks.ifOkUnsigned(true)
          : callbacks.ifOk({sequence: 'good', ...});
  }
  ```
  What DOES run before the short-circuit: unit hash self-consistency (validation.js:126-131),
  depth caps (`isTooDeeplyNestedOrHasTooManyNodes`, :147), well-formedness (:152), joint field
  structure (:155-172), timestamp. What does NOT run: author-address validity, authentifier /
  signature verification, definition evaluation, message/payment validation, spend-proof and
  double-spend checks, witnesses. The hash check is self-consistent (the attacker computes the hash
  of their own forged content) — it proves internal consistency, not authenticity.
- `validateLight` explicitly suppresses the intended "stable unit without proof" rejection:
  `if (err !== lightStableErrorMessage) error = err` (validation.js:107-109) — a joint carrying a
  ball is accepted into the validation flow instead of being rejected as unproven.
- In `processHistory`, the checks that would have bound joints to the proofchain are **commented
  out** (light.js:242-244 and 250-252: "stable but not proven" / "proofchain doesn't prove unit").
  The comment "we receive unconfirmed units too" (light.js:327) documents the design intent: show
  unconfirmed transactions. The consequence: every joint the vendor/hub serves — including a forged
  spend — is saved via `writer.saveJoint(objJoint, {sequence: 'good', ...})` (light.js:361-365) with no
  signature check; `fixIsSpentFlag` (light.js:438-460) then marks any outputs referenced by the new
  unit's inputs as spent in the wallet's DB.
- **Confirmed units ARE proofchain-bound**: a unit is marked stable only if it appears in the
  witness-anchored proofchain (`assocProvenUnitsNonserialness[unit]` hasOwnProperty → arrProvenUnits
  → `UPDATE units SET is_stable=1` and `is_unique=1`, light.js:329-356). So the wallet's *final*
  state is authentic; the *pending/unconfirmed* state is peer-trusted.
- **Trust-boundary width**: `refreshLightClientHistory` connects to `network.light_vendor_url`
  (light_wallet.js:166), but Obyte light wallets also connect to other hubs as ordinary peers, and
  any hub can deliver joints (`handleJoint` path) — in light mode every such joint hits the same
  short-circuit. The wallet's view (outputs marked spent, fake incoming balances, fake
  `my_transactions_became_stable` events → light.js:396-416 emitStability) is therefore forgeable by
  ANY connected hub, not only the configured vendor.

### Q2 — Light spend-proof handling (uniqueness NOT verified in light — what actually breaks)

- The `conf.bLight` short-circuit means the spend-proof checks (`validateSpendProofs`,
  `checkForDoublespends`) never run in a light process. The `if (conf.bLight)` branch at
  validation.js:1668 is inside the full pipeline and is unreachable in a light process (dead code
  there). The 05f291d8 fix ("uniqueness of spend proof is not verified in light") corresponds to
  this: light clients rely entirely on their hub/vendor for private-payment double-spend detection.
- What breaks: a light client holding a private payment cannot itself detect a double-spend of it;
  its view is whatever the hub serves. This is the documented light trust model; combined with Q1 it
  means even the *unconfirmed* spend history is hub-forgeable. **Trust-model consequence, not a new
  defect.**

### Q3 — Light AA definition handling (aa_addresses.js readAADefinitions)

- In light mode, unknown AA addresses are fetched from the vendor via `light/get_definition`
  (aa_addresses.js:74-155). The definition must pass the chash check (`getChash160(arrDefinition)
  !== address` → reject, :83-86) — so the vendor cannot substitute a different definition for a
  known address. But `validateAADefinition` (structure, getters, complexity, references) is NOT run
  before `storage.insertAADefinitions(db, [...], GENESIS_UNIT, 0, 0, false, ...)` (mci=0,
  :92-95). Consequences (wallet-side only):
  - `checkAAOutputs` computes bounce fees from the possibly-malformed definition → the wallet may
    compose a unit with wrong bounce fees → the full node rejects it (failed transaction, no theft).
  - `determineGetterProps` with validation_mci=0 could throw for mci-gated getters (wallet compose
    path crash — the f11-R1-B lead).
  - The try/catch around `getChash160` (:81-87) treats a hash-compute failure as "not an AA"
    (fail-open shape — f14-T2).
  - Impact is bounded: the wallet's own compose/estimate path; the consensus path (full nodes) is
    unaffected. **Vendor-trust, wallet-side only.**

### Q4 — Any light-path fund movement without full validation?

- The light wallet composes and signs its own units with its own keys; the units are broadcast and
  validated by full nodes (all spend decisions are re-validated at consensus). No light path posts
  to the ledger without full-node validation. A wallet that spends based on a hub-inflated balance
  composes a unit the full node rejects — failed transaction, not theft.
- The one wallet-behavior consequence: `getConfirmationConditionSql` with the default
  `spend_unconfirmed='own'` (composer.js:504) spends stable outputs or the wallet's own
  unconfirmed outputs — an output marked spent by a hub-forged unit is excluded from the balance
  query (wallet.js:1345 `outputs.is_spent=0`) → the wallet refuses to spend it (wallet-view freeze;
  on-chain funds unaffected).

## Held / refuted observations

- **H-L0 (held, positive):** the witness proof + proofchain verification is cryptographically sound
  end-to-end (Q1). Confirmed-state integrity does not depend on vendor honesty.
- **H-L1 (hardening note):** light-mode `validate()` short-circuits to timestamp+no-ball; unit
  authenticity (signatures — locally verifiable) is not checked; the proofchain-membership checks
  that would have bound joints to the witness-anchored chain are commented out in `light.js`
  processHistory. Any connected hub can forge the wallet's *unconfirmed* view (fake spends → outputs
  marked spent; fake stability events). **Trust-model consequence; not reportable under the program
  (no consensus or on-chain fund impact demonstrated).**
- **H-L2 (hardening note):** light AA definitions are chash-verified but not
  `validateAADefinition`'d, inserted at mci=0 (aa_addresses.js:92-95); malformed definitions cause
  wallet-side bounce-fee miscalculation / possible getter throw. Wallet-side, vendor-trust.
- **H-L3 (hardening note):** `processLinkProofs` (light.js:789-866) verifies reference-closure and
  hashes but not real-DAG ancestry — a hub can serve a reference-closed chain claiming inclusion
  that the real DAG does not support. Link proofs are consumed by the wallet owner verifying their
  own payments; vendor-trust.
- **H-L4 (held):** the 05f291d8 light asymmetry is the documented design (light cannot run the
  graph check; the vendor is the trust anchor for private-payment uniqueness).

## Gaps not covered and why

- The wallet GUI/decision layer (what the user is shown and what auto-actions fire on
  `aa_response`/stability events) is out of the core-library scope.
- The vendor implementation (hub-side prepareHistory) is the same ocore code running as a full
  node; its honest behavior is assumed (trust model).
- Device-message E2E layer (chat) untouched — out of the DLT surface.

## Files / evidence

- This report: `evidence/round3/LR-1.md`
- No scripts run this pass (pure source trace; the light flow requires a hub/vendor harness the lab
  does not provide — the vendor-side `prepareHistory` and client-side `processHistory` are only
  exercisable end-to-end with two running nodes).

## Verdict JSON

{"id": "LR-1", "claim": "light client confirmed-state is witness-anchored and sound; unconfirmed-state unit authenticity is not verified (light-mode validate short-circuits; proofchain-membership checks disabled) but this is the documented peer-trust model", "verdict": "no_finding (hardening notes H-L1/H-L2/H-L3)", "decisive_control": "confirmed units require proofchain membership (light.js:329-356) — forged units can only poison the unconfirmed view; no consensus or on-chain fund impact", "raw_evidence": "evidence/round3/LR-1.md"}
