# LR-3 — F4 natural-burst escalation + multi-private-asset per-tuple uniqueness

Pinned `a7eb776afc68ed4bed05ba554f7f1e95f5d49b44`. Worker report for the terminal round.

## Part 1 — F4 natural-burst form: does the severity rise? **NO (stays Low)**

### Mechanism framing — confirmed in source, then bounded

The settlement path is as documented in F4:
- `storage.js:1228-1234` `getFinalTpsFee = Math.round(base_tps_fee * (exp(tps / tps_interval) - 1))`
  with mainnet `base_tps_fee = 10`, `tps_interval = 1` (initial_votes.js:36-37).
- `storage.js:1174` `elapsed = (mc_ts - last_ball_ts) || 1` — equal-second waypoint timestamps
  force `elapsed = 1`, so `tps = count` (the number of units in the stabilization window).
- `storage.js:1246-1261` `updateTpsFees` writes `tps_fees_balance += declared - final` per author.

So a window with N units and elapsed=1 charges each settling author
`10×(exp(N)−1)` base units. For N=30 that is 1.07e14 base ≈ 107,000 GBYTE (10.7% of the 1e15
supply) — the catastrophic form. **The natural-burst question is whether N≥30 with elapsed=1 is
reachable without an attacker.**

### The two self-limiting controls (both verified in source)

1. **The declared-fee gate is 10× more aggressive than the settlement.** The min-acceptable gate
   (`validation.js:1065-1095`) requires each unit to declare `tps_fee` such that
   `balance + declared ≥ getLocalTpsFee(...)` where `getLocalTpsFee` (`storage.js:1329-1349`)
   = `count_units × round(tps_fee_multiplier × base_tps_fee × (exp(tps) − 1))` with
   `tps_fee_multiplier = 10` (initial_votes.js:38) — i.e. the estimate curve is 10× the settlement
   curve, and the unit's inputs must fund the declared fee (`validation.js:2649-2653`). A spike
   therefore stalls once the estimate requires more than the authors hold.
2. **Elapsed damping.** On a calm network the two waypoints bounding a window are seconds apart, so
   `elapsed = 5..10` and `tps = count/elapsed` is small even for a burst. `elapsed = 1` requires
   same-second waypoints — a network already posting waypoints at ≥1/sec.

### Measured magnitudes (real formula, `Decimal.exp()`)

| scenario | tps | settlement fee/unit | estimate requirement/unit |
|---|---|---|---|
| sharp spike 15u/1s | 15 | 0.03 GBYTE | 0.33 GBYTE |
| sharp spike 20u/1s | 20 | 4.9 GBYTE | 48.5 GBYTE |
| spike 30u/1s | 30 | 107,000 GBYTE | 1,070,000 GBYTE (≈ whole supply — impossible) |
| burst 30u/2s | 15 | 0.03 GBYTE | 0.33 GBYTE |
| flood 60u/5s | 12 | ≈0 | ≈0 |

### Verdict

- **The catastrophic natural case is impossible.** A 30-unit/1s window requires the later units to
  declare ≥1,070,000 GBYTE (the entire money supply) — the spike stalls at ~20 units for authors
  holding <48.5 GBYTE.
- **The realistic natural damage is a small-author freeze of single-digit GBYTE.** A sharp 20-unit
  spike in a 1-second window (e.g., a mass-claim AA launch or an exchange sweep landing between two
  same-second waypoints) settles the early units (validated at the calm estimate, declared small
  fees) at ~4.9 GBYTE each — authors with less balance are frozen (can't author until the debt is
  paid). At current GBYTE prices that is on the order of tens of USD per affected small author —
  **below the program's USD 1,000 minimum impact** and subject to the same griefing-downgrade
  feasibility rule as the attack form.
- **F4's severity stays Low.** The natural-burst trigger is real and is the *more honest* framing
  (no attacker expense), but the magnitude is bounded by the estimate stall and the elapsed
  damping to the same below-floor economics the round-1 refuter established for the attack form.
- **Recommendation:** add the natural-burst trigger to the finding's impact narrative (attacker-free
  trigger; still bounded below the floor) and keep the remediation note (cap the settlement fee
  relative to declared/balance — the fix covers both forms). No severity change.

## Part 2 — multi-private-asset per-tuple uniqueness: **HOLDS (no cross-asset dodge)**

The f8 gap ("per-tuple uniqueness across two private assets in one unit not verified") is closed by
three independent bindings, verified in source:

1. **Per-message structure:** each private asset's chain is a separate payment message with its own
   `message_index`; the composer validates each payload independently in a series
   (`divisible_asset.js:347-383`, the dd29823 change: `async.eachSeries(Object.keys(assocPrivatePayloads), ...)`
   calling `validateAndSaveDivisiblePrivatePayment` per payload). Output indices live in distinct
   per-message spaces, so `(unit, message_index, output_index)` tuples are unique per asset by
   construction.
2. **Asset-committing proofs:** the transfer spend proof hashes `{asset, amount, address, unit,
   message_index, output_index, blinding}` (`inputs.js:73-80`) — a proof for asset A cannot match a
   proof row for asset B (the values differ). The message-level uniqueness check
   (`validation.js:1637-1654`, keyed on `(spend_proof, claimed-address)`) therefore cannot collide
   across assets.
3. **Src-output binding per asset:** the payload-level validation resolves the claimed input against
   the outputs table (`divisible_asset.js:118-122`: `SELECT ... FROM outputs WHERE unit=? AND
   message_index=? AND output_index=? AND asset=?`; "not 1 row when selecting src output" otherwise)
   — a chain claiming an output that exists only in another asset's message fails the lookup. The
   input-level double-spend check is likewise per-asset (`validation.js:2259` `AND asset=?`).

**Residual edge (recorded, not exploitable):** two messages in the same unit carrying the *same*
spend proof for the *same* output would not be caught by the `spend_proofs` table check
(`WHERE unit != ?` excludes the unit's own rows), but the proof value commits to the output tuple,
so identical proofs imply the identical output — which cannot exist in two asset messages (binding
3). No reachable dodge.

**Verdict:** per-tuple uniqueness holds; the f8 gap is closed. No new finding.

## Files

- This report: `evidence/round3/LR-3.md`
- Commands: `sed`/`git show dd29823`/`grep` over the pinned tree; `node -e` Decimal fee computation
  (results above). No lab scripts needed; no live contact.

## Residual risks

- The 20-unit-spike natural scenario assumes same-second waypoints on a network whose OPs are
  fee-exempt (`validation.js:1091` `!bFromOP` accepts low fees from OPs) — the exemption is what
  makes 1/sec waypoints sustainable; if OPs were not exempt the natural case would damp further.
- Real GBYTE pricing varies; the below-floor conclusion assumes a price in the tens of USD.
