# obyte-2026-08-004 — Settlement tps-fee is exponential and unbounded vs author balances (fee poisoning)

**Status:** unproven. **Pinned target:** ocore @ `a7eb776afc68ed4bed05ba554f7f1e95f5d49b44`

## Summary (one sentence)

The settlement tps fee (`round(base_tps_fee * (exp(tps) - 1))`, base=10, interval=1) is unbounded
relative to any author's balance: a 30-unit 1-second window charges every settling author ~10.7% of
the total supply, permanently freezing small authors whose `tps_fees_balance` plunges negative.

## Affected surface

- `storage.js:1228-1234` `getFinalTpsFee` (settlement fee, exponential in the window rate)
- `storage.js:1174` `elapsed = (mc_ts - last_ball_ts) || 1` (equal timestamps → elapsed=1)
- `storage.js:1246-1261` `updateTpsFees` (`tps_fees_balance += declared - fee`)
- `validation.js:1087` min-fee gate (rejects authors with negative balances)
- `initial_votes.js:36-37` mainnet defaults base_tps_fee=10, tps_interval=1

## Claim tuple

- **target/version:** ocore `a7eb776`, tps-fee settlement path
- **entrypoint:** any unit settling on the MC in a flood window
- **preconditions:** attacker funds a ~30-unit linear chain with equal-second timestamps landing in
  a 1-second window (timestamps have no past bound — validation.js:280-285 bounds only the future)
- **mechanism:** fee = 10×(exp(30)−1) ≈ 1.0686e14 base ≈ 10.7% of supply at count=30/elapsed=1
- **observable effect (measured, real path):** fee = 106,864,745,815,235 base; honest author balance
  −106,864,745,815,218; subsequent normal-fee units hard-rejected by the min-fee gate; −Infinity
  persists as REAL −Inf in the sqlite file (for the unreachable overflow variant)
- **negative control:** normal rate → small deltas; the gate rejection of the poisoned author is the
  observed control
- **claimed impact/severity:** Low — real mechanism, demonstrated cap: funding bound (inputs must
  cover declared fees) caps count at ~32 even at 100% supply; Infinity unreachable; damage ~1:1 with
  attacker expense (below the program's 200% bar); scatter, not targetable; griefing downgrade likely

## Reproduction (maximum-impact PoC + independent run — standing gate)

```
cd /Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore
node lab-obyte.js <abs>/unproven/obyte-2026-08-004/r2-tps-fee-drive.js
node lab-obyte.js <abs>/unproven/obyte-2026-08-004/r2-sqlite-infinity-test.js
```

Raw results (refuter `evidence-R2.md` + independent reviewer `evidence-IR-F4.md`):
- fee = 106,864,745,815,235 base at count=30/elapsed=1 (10.69% of supply) — CONFIRMED (both runs)
- honest author balance = −106,864,745,815,218 — CONFIRMED
- gate rejection afterwards (validation.js:1087) — CONFIRMED
- −Infinity persists in the INT column as REAL −Inf across a pool close/reopen — CONFIRMED

## Impact analysis (marginal contribution)

- World without the bug: the settlement fee would be capped relative to the author's balance (e.g.,
  a floor at the declared fee, or a per-window fee cap).
- Delta: authors settling in a flood window are frozen (can't author units; recovery costs >the
  debt). The attacker's own units are priced by the same gate — the attack costs ~10.7% of supply.
- **Cap (proven):** the Infinity variant is unreachable (funding bound validation.js:2649-2653 +
  min-fee gate → count ≤ ~32); permanence is partial (repayable debt); damage ~1:1 (below the
  200%-expense bar); scatter (not targetable). This caps the finding below the program's in-scope
  bar → Low.

## Negative control

Normal-rate windows (count 1-5, elapsed > 1) produce small deltas; the poisoned-author gate
rejection is the demonstrated control. `-Infinity` storage is real but its trigger (count≥709) is
unreachable by ~20 orders of magnitude.

## Remediation note

Cap the settlement fee (e.g., relative to the declared fee or a max multiple of the author's
balance); the fee-formula parameters are system-vote governance, so a coordinated formula change is
the fix (in-scope class if it were reached; the economics keep it below).

## Evidence refs

- `evidence-R2.md` — round-1 refuter drive (real path, synthetic 30-unit window)
- `evidence-IR-F4.md` — round-2 independent run (all checkpoints + pool-reopen −Inf verification)
- `r2-tps-fee-drive.js`, `r2-sqlite-infinity-test.js` — runnable scripts
- `attempts.jsonl` — round-1/round-2 attempt records

**CVSS:3.1/AV:N/AC:H/PR:L/UI:N/S:U/C:N/I:N/A:L** = 3.1
