# ER-1 — review of E1-2 (fork race capped) + E1-8 (merchant exposure)

**Reviewer:** ER-1 (independent, fresh context) · **Pinned:** ocore `a7eb776afc68ed4bed05ba554f7f1e95f5d49b44` (verified: `git rev-parse HEAD` == pin)
**Doctrine:** claims verified against the pinned source + raw logs/DB reads. Hunter summaries not trusted. Disconfirming is the default posture.

**Overall verdict: verified** — all four claims (a)–(d) hold against the source and the raw evidence, with three documented nuances (none severity-changing).

---

## Claim (a) — the MC race between C and A is position-only; conflict machinery never fires on two 'good' units

**Verdict: verified**

Decisive evidence:

- `main_chain.js:1292-1293` — `handleNonserialUnits` runs `SELECT * FROM units WHERE main_chain_index=? AND sequence!='good' ORDER BY unit`. Units with `sequence='good'` are never processed; `final-bad`/`good` resolution (`findStableConflictingUnits`, `main_chain.js:1390-1427`) is only reachable from the temp-bad branch. Both C and A validate `'good'` → the machinery never fires on this pair.
- Temp-bad marking is conditional on *detected* conflicts: `checkSerialAddressUse` (`validation.js:1304-1337`) sets `sequence='temp-bad'`/`'final-bad'` only when `findConflictingUnits` (same-address author-seriality) returns matches. F3's ghost is authored by a different address, so no conflict is ever detected (the spend-proof check at `validation.js:1637-1654` is keyed on `(spend_proof, address-of-author)`, `validation.js:1556-1568` — the victim's row `(P, merchant)` never matches `(P, sender)`).
- "Smallest unit wins" comment (`main_chain.js:1389-1392`, query comment `:1426`) is dead for this pair — it applies to temp-bad units on the same MCI only.
- Empirical: `round2/IR-F3.md` DB read — `U2 (victim) |1|0|good|1`, `A_own (attacker) |2|0|good|1`, no final-bad; `round3/LR-2.md` §Q2 confirms two 'good' same-proof units coexist and nothing voids C.

Consequence as claimed: C can never become `final-bad` through this machinery; merchant flows keyed on a final-bad signal never trigger.

---

## Claim (b) — attacker reliably wins the MC position via tip anchoring + unit-hash grind

**Verdict: verified** (with nuances, none material to reliability)

Decisive evidence:

- Ranking/tie-break is real: `readLastUnitProps` (`main_chain.js:43-88`) selects the MC-walk start among free units with `ORDER BY witnessed_level DESC, level-witnessed_level ASC, unit ASC` — the last key is the **unit hash** (base64 string comparison). Same sort semantics in `determineBestParent` (`storage.js:2075-2077` SQL; `storage.js:2080-2086` OP-pref JS sort, both ending `unit ASC`).
- Displacement mechanics: `goDownAndUpdateMainChainIndex` (`main_chain.js:202-205`) resets `is_on_main_chain=0, main_chain_index=NULL WHERE main_chain_index>?` (sibling excluded from the re-walk), bounded by the stable-unit throw (`main_chain.js:133-146`). The window is inclusion→stabilization.
- Tip anchoring: `determineWitnessedLevelAndBestParent` (`storage.js:691-725`) walks the best-parent chain until `MAJORITY_OF_WITNESSES` distinct witness authors accumulate (`constants.js:119` → 6 on mainnet); anchoring the ghost on a newer OP-authored waypoint raises its `witnessed_level` ≥ C's — attacker free to choose parents.
- Grind is real: `getUnitHash` (`object_hash.js:60-85`) = base64 sha256 of the stripped unit, which embeds `content_hash` = sha256 of the naked unit **including messages with `payload_hash`** (payload text is stripped, but `payload_hash` remains). Varying a text message changes `payload_hash` → `content_hash` → unit hash. **Fresh reproduction against the pinned source: 8 content variants → 8 distinct unit hashes spanning the base64 lexicographic range (min first char `9`, max `p`).** Each candidate is a valid unit (text message validates).
- Fairness of the tie-break: P(candidate < C) averages 0.5 per attempt for a uniformly random C (expected ~2 attempts); it is target-position-dependent — measured 0.008 (target first char `+`) to 0.87 (target first char `r`) across runs — worst case ~125 expected attempts, always trivially cheap (CPU-only). The claim's "~2 attempts" is the expected value; "a handful for near-certainty" holds for the average case. Reliable and cheap: **verified**.

Nuances (non-material):
1. **The "8 distinct hashes" measurement has no raw artifact** in the evidence tree (no log/script in `roundE1/` or `lab/`; the phrase appears only in the roundER brief). I reproduced the equivalent result fresh against the pinned source (8/8 distinct, range-spanning). The specific cited measurement is unattested; the underlying claim is verified.
2. **Citation drift:** E1-2's evidence index cites `storage.js:2080-2086` for the ranking ORDER BY; the free-unit ranking is `main_chain.js:46-48`. Both encode the same semantics (unit ASC last). Cosmetic.
3. **OP-pref branch:** on mainnet past `bestParentPrefersOpUpgradeMci` (=12155000, `constants.js:103`), the free-unit ranking is overridden by `determineBestParent(..., true)` (`main_chain.js:63-70`) which prefers OP-authored parents *before* `unit ASC`. For a non-witness attacker both siblings are non-OP, so `unit ASC` still decides. The claim holds on the live mainnet.

---

## Claim (c) — the value ledger always resolves to the victim; ghost payload rejected by the owner binding

**Verdict: verified**

Decisive evidence:

- `divisible_asset.js:120-136` — payload-side spend-proof recomputation is keyed on `src_output.address` (the actual output owner) plus `unit/message_index/output_index/amount/blinding` of the source output. `divisible_asset.js:159` — `"incorrect spend proof"` on address/proof mismatch.
- The ghost's stored rows are `(sender-address, P)` (written from the message's `spend_proofs` at save, `writer.js:279-286` per IR-F3); the recomputed proof for spending X is `(merchant-address, P)`. Address mismatch → rejection, always.
- Empirical (round 2, real private-asset path): `kp-f3-ghost-exp` — `A_own PAYLOAD RESULT: REJECTED: incorrect spend proof` (LR-2.md §verification 1); `X is_spent: [{...is_spent:1}]` (set by C only); ghost `INPUTS rows: []`.
- Consequence: X's value materializes only via C's payload; the ghost's outputs never materialize; C remains `'good'` even when displaced off-MC, so no re-spend of X ever succeeds.

---

## Claim (d) — merchant exposure: direct-descendant ghost, unbounded window, no signal

**Verdict: verified**

Decisive raw evidence:

- `evidence/lab/e1-8/e1-8-merchant-exp.raw.log` (exit 0): `C VALIDATION OK sequence=good` → saved mci 1 on-MC; `A VALIDATION OK sequence=good` → `GHOST-ARRIVAL: accepted (ifOk), no rejection/error signal emitted`; `UNITS-AFTER-GHOST`: genesis mci 0, C mci 1 good onMC, A mci 2 good onMC; `SPEND-PROOFS-AFTER-GHOST`: same P under `GC6I5…` (merchant) and `W2OKT…` (sender).
- Post-run DB queried directly (`.e18data/byteball.sqlite`):
  - `units`: `MPdvIH… |1|good|1|0` (C), `oyVVrR… |2|good|1|0` (A) — both good, on-MC, unstable.
  - `parenthoods`: `oyVVrR… → MPdvIH…` — **the ghost is a direct descendant of the accepted payment** (composer log: `parents: [unit MPdvIH…]`, `1 free units consumed`).
  - `spend_proofs`: two rows, identical `uIpBWDs77yYo/PjxL+ee+HIGUpICr0PYCETD9VdxqfU=` under merchant and sender addresses.
- No-signal/no-resolution mechanics: `handleNonserialUnits` filters non-good (main_chain.js:1292-1293); same-author conflict detection is author-keyed (`findStableConflictingUnits` JOIN on `unit_authors.address`); the spend-proof check is address-keyed (`validation.js:1637-1654`); the payload-side binding rejects the ghost's payload but is per-node payload flow, not unit-level consensus (`bPrivate` only in the payload flow, `validation.js:2695`). Negative control from IR-F3: same P + same address is cleanly rejected (`"conflicting spend proof in inner unit"`), same P + different address silently accepted — the dodge is exactly the address key.
- "Unbounded window": nothing ever flips either unit's sequence; both persist `'good'` indefinitely (stabilization only balls the MC, it does not re-grade them).

Nuance (consistent with E1-8's own framing, not a contradiction): in the descendant variant C **keeps** its MC position (mci 1, on-MC) — an inclusion-keyed acceptance of C is never revoked. The exposure is the *contested state*: the merchant's node offers no signal distinguishing the accepted payment from a second 'good' unit carrying the identical bearer proof, and no resolution ever arrives. The experiment's ghost carries `payload_location:'none'` (no payload), so the payload-side rejection is not re-exercised here — it was exercised in round 2 (claim c) and is source-verified. E1-8's own residual-risk note covers this.

---

## Severity cross-check (adjudication, not re-litigated)

Nothing in this verification contradicts E1-2's "capped" verdict or the Low ceiling: value is conserved (claim c), stable-C is protected from displacement (`main_chain.js:133-146`), and the displacement/contested state is bounded to the unstable window or to validity-keyed (non-inclusion-checking) acceptance flows. The reliable, attacker-controlled displacement strengthens the *mechanism* description (silent, deterministic, signal-free) but does not create value theft or permanent freezing — consistent with the round-3 LR-2 adjudication.

---

## Residual risks / open items

1. **No live multi-node demonstration of the fork-race displacement** — the lab lacks witness/MC-advancement machinery (units are `is_stable=0`; MC indices come from the single-writer save path). Displacement mechanics are source-verified (ranking query, goDown reset, stable throw), same evidence grade as the round-2 link findings.
2. **Real stabilization behavior of the C/A pair is inferred, not network-observed** — both staying `'good'` follows from the resolution code (handleNonserialUnits filters non-good), which is source-verified.
3. **The "8 distinct hashes" measurement lacks a raw artifact** in the evidence tree; fresh reproduction against the pinned source confirms the claim (8/8 distinct, range-spanning).
4. **Grind cost is target-position-dependent** — worst case ~125 expected attempts (victim's unit-hash first base64 char `+`/`/`); still trivial. E1-2's "~2 attempts" is the average-case expectation.
5. **Synthetic spend proof in E1-8** — the unit-level mechanism is message-level and faithful; the full private-asset end-to-end with real blinding was established in round 2 (kp-f3-ghost-exp).

---

## Verdict JSON

```json
{
  "id": "ER-1",
  "verdict": "verified",
  "per_claim": [
    {
      "claim": "(a) MC race position-only: conflict machinery never fires on two 'good' units",
      "verdict": "verified",
      "evidence": "main_chain.js:1292-1293 (handleNonserialUnits filters sequence!='good'); validation.js:1304-1337 (temp-bad only on detected same-address conflicts; F3 ghost different author -> never temp-bad); main_chain.js:1389-1392/1426 (smallest-unit-wins comment dead for this pair); empirical: IR-F3.md DB read (U2 mci1 good, A_own mci2 good, no final-bad), LR-2.md Q2"
    },
    {
      "claim": "(b) attacker reliably wins MC position via tip anchoring + unit-hash grind",
      "verdict": "verified",
      "evidence": "main_chain.js:43-88 free-unit ranking ORDER BY witnessed_level DESC, level-witnessed_level ASC, unit ASC (unit hash last key); storage.js:691-725 witnessed level (MAJORITY_OF_WITNESSES=6, constants.js:119); main_chain.js:202-205 reset, :133-146 stable-protection throw bound the window; object_hash.js:60-85 unit hash content-controllable via message payload_hash -> content_hash (fresh repro: 8/8 distinct hashes spanning lexicographic range; P(candidate<C) averages 0.5, measured 0.008-0.87 by target position); nuances: '8 distinct hashes' measurement lacks raw artifact; mainnet >=12155000 adds isOP tier before unit ASC (no-op for non-witness attacker); storage.js:2080-2086 citation is the OP-pref sort, ranking is main_chain.js:46-48"
    },
    {
      "claim": "(c) value ledger always resolves to the victim (owner binding rejects ghost payload)",
      "verdict": "verified",
      "evidence": "divisible_asset.js:120-136 (recompute keyed on src_output.address), :159 ('incorrect spend proof'); ghost rows (sender,P) != recomputed (merchant,P); empirical: kp-f3-ghost-exp 'A_own PAYLOAD RESULT: REJECTED: incorrect spend proof', X is_spent=1 via C only (LR-2.md)"
    },
    {
      "claim": "(d) merchant exposure: direct-descendant ghost, unbounded window, no signal",
      "verdict": "verified",
      "evidence": "e1-8-merchant-exp.raw.log (C good mci1 onMC; A VALIDATION OK good, accepted ifOk no rejection; both on MC); .e18data/byteball.sqlite: units (C mci1 good onMC, A mci2 good onMC), parenthoods (A->C direct descendant), spend_proofs (same P under merchant+sender); no resolution path (main_chain.js:1292-1293 author-keyed findStableConflictingUnits, validation.js:1637-1654 address-keyed check); negative control IR-F3: same P same address rejected, same P different address accepted; nuance: descendant variant keeps C on-MC (inclusion-keyed acceptance of C not revoked); exposure = signal-free contested state, unbounded"
    }
  ]
}
```
