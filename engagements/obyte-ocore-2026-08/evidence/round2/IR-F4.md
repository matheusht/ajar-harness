# IR-F4 — Independent review of the tps-fee drive + sqlite persistence PoCs (F4)

- **Reviewer:** independent fresh-context reviewer (IR-F4)
- **Date:** 2026-08-11
- **Target:** obyte-ocore @ `a7eb776afc68ed4bed05ba554f7f1e95f5d49b44` (verified: `git rev-parse HEAD` = `a7eb776afc68ed4bed05ba554f7f1e95f5d49b44`)
- **Builder report reviewed (not trusted):** `evidence/round1/R2.md` (P6 section); PoCs `evidence/round1/r2-tps-fee-drive.js`, `evidence/round1/r2-sqlite-infinity-test.js`
- **PoCs executed (unmodified):** both round-1 scripts via the lab harness (`lab-obyte.js` → `evidence/lab/lab.js`), fresh scratch dirs per run
- **Commands:**
  - `cd /Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore && LAB_TAG=ir-f4 node lab-obyte.js <abs>/evidence/round1/r2-tps-fee-drive.js`
  - `LAB_TAG=ir-f4b node lab-obyte.js <abs>/evidence/round1/r2-sqlite-infinity-test.js`
  - `LAB_TAG=ir-f4c node lab-obyte.js <abs>/evidence/lab/ir-f4-reopen-probe.js` (extra reviewer probe, see §4)
- **Raw output (this review):** `evidence/round2/raw-logs/IR-F4-tps-fee-drive.raw.log`, `IR-F4-sqlite-infinity.raw.log`, `IR-F4-reopen-probe.raw.log` — all exit=0, `LAB-DONE`.

## 1. Source verification (the claimed mechanism, before trusting any output)

| Claim | Source evidence (pinned tree) | Verdict |
|---|---|---|
| Fee formula `round(base_tps_fee * (exp(tps/tps_interval) − 1))` | `storage.js:1228-1234` `getFinalTpsFee`; `Math.round(base_tps_fee * (exp(tps / tps_interval) - 1))` at `storage.js:1234`; `exp(x) = new Decimal(x).exp().toNumber()` at `storage.js:1133-1135` | CONFIRMED |
| `elapsed = timestamp-diff \|\| 1` (equal timestamps → 1) | `storage.js:1174` (`getFinalTps`) and `storage.js:1296` (`getFinalTps` second call site); `elapsedTimeWhenZero = 1` at `storage.js:44` | CONFIRMED |
| `base_tps_fee = 10`, `tps_interval = 1` (mainnet) | `initial_votes.js:36-37` (`const base_tps_fee = 10; const tps_interval = constants.bDevnet ? 2 : 1;`) | CONFIRMED |
| Settlement writes `tps_fees_balance + delta` via REPLACE | `storage.js:1246-1261` `updateTpsFees`; `REPLACE INTO tps_fees_balances (address, mci, tps_fees_balance)` at `storage.js:1261` | CONFIRMED |
| Min-fee gate: `tps_fees_balance + declared < min` → hard reject | `validation.js:1087-1088` (`if (tps_fees_balance + objUnit.tps_fee * share < min_tps_fee * share) return callback(...)`) | CONFIRMED |
| Funding bound: declared `tps_fee` must be covered by inputs | `validation.js:2649-2653` `total_input !== total_output + … + tps_fee + …` → callback reject | CONFIRMED |
| Equal-timestamp units are valid (elapsed=1 reachable) | `validation.js:280-285` (positive int, ≤ now+5 future); `validation.js:692-693` (≥ parents' timestamps, equality allowed); `validation.js:720-740` (last_ball_unit must exist/have ball/be a parent — **no** newest-ball or timestamp relation) | CONFIRMED |
| Supply bound | `constants.js:15` `TOTAL_WHITEBYTES = 1e15` base = 1e6 GBYTE | CONFIRMED |
| Exp overflow → Infinity at the JS boundary | `storage.js:1133` `.toNumber()`; measured: Decimal `exp(710)=2.23399476616171e+308` finite, but `.toNumber()` → **Infinity** (exceeds `Number.MAX_VALUE` 1.7976931348623157e308); fee(`Math.round(10*(exp(tps)-1))`) = Infinity at tps=710 | CONFIRMED (nuance below, §5) |
| count cap from funding | fee@32 = 7.896e14 base (0.79× supply); fee@33 = 2.146e15 base (> 2× supply) — even 100% supply holding caps count ≤ ~32 | CONFIRMED |
| Lab zeroes upgrade MCIs (gates stricter, not looser) | `lab.js` sets `v4UpgradeMci = pemCurvesFixMci = … = 0`; `updateTpsFees` then requires `sequence === 'good'` (production at these MCIs: `constants.js:99` `v4UpgradeMci = 10968000`, `:101` `pemCurvesFixMci = 12155000`) | CONFIRMED |

## 2. Checkpoint verification from RAW output (my run, `raw-logs/IR-F4-tps-fee-drive.raw.log`)

### fee at count=30 / elapsed=1
```
final tps at unit-u30 30
count=30 elapsed=(T-T)||1 (getFinalTps internal)
final tps fee (base units) = 106864745815235 = 106864.745815 GBYTE
```
- `getFinalTps` counted **30** units in the window (real cache traversal), elapsed=1 → tps=30.
- Real `getFinalTpsFee` → **106,864,745,815,235** base units = 106,864.745815 GBYTE = **10.69%** of `TOTAL_WHITEBYTES` (1e6 GBYTE). Matches `round(10*(exp(30)−1))` recomputed independently: `Decimal(10).mul(Decimal(30).exp().minus(1)) = 106864745815234.62147` → round = 106864745815235. ✓
- **Checkpoint 1 CONFIRMED.**

### author balances after real `updateTpsFees` settlement
```
author AUTHOR tps_fees_balance after settlement = -106864745815235 ( -106864.745815235 GBYTE )
  -> next unit with declared=17 rejected by min-fee gate: true
author HONEST tps_fees_balance after settlement = -106864745815218 ( -106864.745815218 GBYTE )
  -> next unit with declared=17 rejected by min-fee gate: true
note: honest unit's own final fee on poisoned MCI = 106864745815235 -> delta = 17 - fee = -106864745815218
```
- AUTHOR (no declared fee): delta = 0 − 106864745815235 = **−106,864,745,815,235** (stored via `storage.js:1261` real REPLACE).
- HONEST (declared 17, same final fee): delta = 17 − 106864745815235 = **−106,864,745,815,218**. ✓
- **Checkpoint 2 CONFIRMED** (honest author balance −106,864,745,815,218).
- **Checkpoint 3 CONFIRMED:** both authors' next unit with declared=17 is rejected by the `validation.js:1087` gate (`balance + 17 < 17` → true). The rejection is computed from the *persisted DB row* (the script re-SELECTs the balance before evaluating the gate predicate).

## 3. sqlite persistence — `raw-logs/IR-F4-sqlite-infinity.raw.log`

```
A stored: -Infinity | typeof: number | finite: false | isNaN: false
B stored: Infinity  | typeof: number | finite: false | isNaN: false
C stored: 0         | typeof: number | finite: true  | isNaN: false
D stored: -10686474581524 | typeof: number | finite: true | isNaN: false

A author-with-balance -Infinity declared 17 -> rejected by gate: true
B author-with-balance Infinity declared 17 -> rejected by gate: false
C author-with-balance 0 declared 17 -> rejected by gate: false
D author-with-balance -10686474581524 declared 17 -> rejected by gate: true
```
- **Checkpoint 4 CONFIRMED:** `-Infinity` written through the real sqlite3 binding into the INT column **persists** and reads back as `-Infinity` (number, non-finite); the gate rejects that author permanently (`-Infinity + 17 < 17`).
- Nuances: `+Infinity` also persists (author has infinite credit → gate does NOT reject); `NaN` coerces to integer 0 (no poisoning); the huge-finite count-30 magnitude row persists exactly.

## 4. Extra reviewer probe — persistence across a real pool close/reopen + raw on-disk dump

`evidence/lab/ir-f4-reopen-probe.js` (reviewer-written, does not modify the PoCs): REPLACEs the four values, closes the real pool (`db.close()`), dumps the raw sqlite file via the `sqlite3` CLI, re-requires `db.js` (new pool against the same file — a process-restart simulation), and re-reads. Raw output:

```
sqlite3 CLI raw rows (address | typeof | value):
A|real|-Inf
B|real|Inf
C|integer|0
D|integer|-10686474581524

schema: CREATE TABLE tps_fees_balances (
    address CHAR(32) NOT NULL,
    mci INT NOT NULL,
    tps_fees_balance INT NOT NULL DEFAULT 0, ...
```

```
--- after REOPEN (new pool, same file) ---
A re-read: -Infinity | typeof: number | finite: false
B re-read: Infinity  | typeof: number | finite: false
C re-read: 0         | typeof: number | finite: true
D re-read: -10686474581524 | typeof: number | finite: true
A after reopen -> rejected by min-fee gate: true
B after reopen -> rejected by min-fee gate: false
C after reopen -> rejected by min-fee gate: false
D after reopen -> rejected by min-fee gate: true
```
- On disk, `-Inf`/`Inf` are stored as **REAL** storage class in the INT-affinity column (sqlite keeps REAL when integer conversion is not lossless) and come back as JS `-Infinity`/`Infinity` through the binding; gate semantics identical after reopen. **Persistence is not an artifact of a single connection** — it survives pool close + reopen against the same file (`system vars already initialized` on reopen proves the same DB file was reused).

## 5. Reward-hacking / authenticity check

- **Real code path:** `getFinalTpsFee`, `getFinalTps`, `updateTpsFees`, `exp` are the actual `storage.js` exports; the DB writes go through the real `db.js` pool → real sqlite3 native binding → the real `byteball.sqlite` file. The only synthetic element is the *input state* (stable-unit cache shaped as a 30-unit flood window), which the harness explicitly supports ("scripts that seed their own ledger state"; `lab.js` boot comment). Shaping inputs ≠ reimplementing the function under test.
- **No hardcoded expectations:** scripts print computed values (`fee`, balances, gate booleans) from live engine + DB reads; a mock could not produce the measured `106864745815235` from an independent Decimal recomputation.
- **Gate booleans are computed, not asserted:** the scripts print `rejected: true/false` derived from freshly SELECTed balances against the real `validation.js:1087` predicate.
- **Independent cross-check of the headline number:** `Decimal(10).mul(Decimal(30).exp().minus(1)) = 106864745815234.62147`, `Math.round` → 106864745815235 — matches the engine output exactly. No network contact; local scratch sqlite only.

## 6. Verdict

**CONFIRMED (independent reproduction) — all four brief checkpoints verified from RAW output:**

1. fee = **106,864,745,815,235** base at count=30/elapsed=1 (10.69% of supply) — CONFIRMED
2. honest author balance = **−106,864,745,815,218** — CONFIRMED
3. gate rejection afterwards (`validation.js:1087`; both poisoned authors rejected for a normal declared=17 unit) — CONFIRMED
4. `-Infinity` persists in the INT column (verified additionally across a real pool close/reopen and in the raw sqlite file as REAL `-Inf`) — CONFIRMED

The `-Infinity` *reachability* is refuted by the funding bound (`validation.js:2649-2653` + `validation.js:1087`: count ≤ ~32 even at 100% supply; fee overflows double only at tps=710) — consistent with R2's P6 verdict and the round-1 adjudication (F4 = real-but-capped, below-bar economics). The finite poisoning (count=30/elapsed=1) mechanics are real on the real settlement path.

## 7. Residual risks / open items

1. **No full end-to-end attack run:** the drive shapes the stable-unit cache synthetically; a complete attack (30 valid equal-timestamp units through real validation + stabilization, then settlement) was not composed this round. The fee/delta/gate arithmetic and DB persistence are confirmed; the composed attack run remains open (round-1 economics adjudication stands: ~1:1 scatter damage, below the 200%-expense bar except for a >213k GBYTE whale).
2. **Lab MCI scaling:** lab zeroes `v4UpgradeMci`/`pemCurvesFixMci`, so settlement runs at MCI 30 (`sequence==='good'` required, which the synthetic units satisfy). Production settlement starts at `v4UpgradeMci=10968000` (`constants.js:99`); the fee formula itself has no MCI dependence, so the numbers transfer, but a production-shaped run would land the flood on MCI ≥ 10,968,000.
3. **Infinity nuance vs R2's wording:** R2 says "exp(710)=Infinity (measured)". Precisely: `Decimal.exp(710)` is *finite* (2.23399476616171e+308) but `.toNumber()` (what `storage.exp` returns) overflows to Infinity. R2's conclusion (fee=Infinity at tps=710, unreachable) stands.
4. **+Infinity asymmetry:** an author holding balance `+Infinity` would pass the gate (infinite credit). Unreachable for the same funding reason; recorded for completeness.
5. **Permanence framing:** the poisoned rows persist across restart (verified) and are not rewritten by `updateMissingTpsFees` (gap-fill only, `storage.js:1267-1286`); recovery is only via future overpaid fees — verified as "no code recovery path", as R2 states.

## 8. Files

- `evidence/round2/IR-F4.md` — this report
- `evidence/round2/raw-logs/IR-F4-tps-fee-drive.raw.log` — raw output, run 1 (exit=0)
- `evidence/round2/raw-logs/IR-F4-sqlite-infinity.raw.log` — raw output, run 2 (exit=0)
- `evidence/round2/raw-logs/IR-F4-reopen-probe.raw.log` — raw output, reviewer probe (exit=0)
- `evidence/lab/ir-f4-reopen-probe.js` — reviewer-written probe (PoCs untouched)

```json
{
  "id": "IR-F4",
  "verdict": "confirmed",
  "evidence": [
    "fee=106864745815235 base at count=30/elapsed=1 (raw log: 'final tps fee (base units) = 106864745815235'), independent Decimal recompute round(10*(exp(30)-1))=106864745815235",
    "honest author balance -106864745815218 (raw log: 'author HONEST tps_fees_balance after settlement = -106864745815218')",
    "gate rejection afterwards (raw log: 'next unit with declared=17 rejected by min-fee gate: true' for AUTHOR and HONEST; validation.js:1087)",
    "-Infinity persists in INT column (raw logs: 'A stored: -Infinity', on-disk 'A|real|-Inf', survives pool close/reopen)",
    "Infinity reachability refuted: funding bound validation.js:2649-2653 + gate validation.js:1087 cap count<=~32; fee overflows double only at tps=710 (storage.js:1133 toNumber)"
  ],
  "raw_output_ref": [
    "evidence/round2/raw-logs/IR-F4-tps-fee-drive.raw.log",
    "evidence/round2/raw-logs/IR-F4-sqlite-infinity.raw.log",
    "evidence/round2/raw-logs/IR-F4-reopen-probe.raw.log"
  ]
}
```
