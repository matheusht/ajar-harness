# ER-4 — Verify OV-1 (fee-accounting adjudication, replacing timed-out E1-1)

**Reviewer:** fresh context, adversarial-lite. **Pinned source:** ocore
`a7eb776afc68ed4bed05ba554f7f1e95f5d49b44` (verified: local clone HEAD == pin). **Doctrine:**
claims verified against pinned source; hunter/orchestrator summaries not trusted. **Local only:**
no network, no secrets, no source modifications.

Scope: OV-1 in `evidence/roundE1/orchestrator-verifications.md` — claims (a)–(e). E1-1 timed out
mid-verification; no raw E1-1 results exist (`evidence/lab/e1-1-conservation.js` probe never
logged). This review is therefore source-grounded, not log-grounded, for (e).

## Claim (a) — declared tps_fee burned from inputs at save: **VERIFIED**

| Element | Verdict | Decisive evidence |
|---|---|---|
| closure includes tps_fee | verified | validation.js:2650-2653 (cite said 2654-2656; +4 drift): `const tps_fee = objUnit.tps_fee || 0;` then `if (total_input !== total_output + headers_commission + payload_commission + oversize_fee + tps_fee + burn_fee + vote_count_fee) return callback("inputs and outputs do not balance"...)`. The declared fee must be covered by inputs; it is not an output and is not credited to any balance at save. |
| tps_fee well-formed | verified | validation.js:198-199 — nonnegative integer required; :292-293 banned in genesis; :1054-1055 banned in AA responses (AA response fees fold into the trigger). |
| minimum fee floor | verified | validation.js:1070-1093 — declared fee must satisfy the local-TPS estimate floor (transient error if not, except OP). |
| no other writer credits the declared fee | verified | the only writer of `tps_fees_balances` is storage.js:1261 (settlement delta); composer.js:384/628, light.js:637, validation.js:1085 are read-only SELECTs. |

## Claim (b) — settlement applies ONLY the delta (declared − final) to recipient balances: **VERIFIED**

storage.js:1247-1261 (cite 1246-1261; −3/+0 drift):

- :1247 final fee = `getFinalTpsFee(objUnitProps) * (1 + (objUnitProps.count_aa_responses || 0))`
  (AA responses folded into the trigger's fee — consistent with validation's count_units at :1070).
- :1248 `UPDATE units SET actual_tps_fee` — a record, not a balance.
- :1249 `total_tps_fees_delta = (objUnitProps.tps_fee || 0) - tps_fee` — exactly (declared − final), "can be negative".
- :1258 `tps_fees_delta = Math.floor(total_tps_fees_delta * share / 100)`.
- :1261 `REPLACE INTO tps_fees_balances (address, mci, tps_fees_balance) VALUES(?,?,?)` with the
  running balance read at :1260 (`WHERE address=? AND mci<=? ORDER BY mci DESC LIMIT 1`).

## Claim (c) — getTpsFeeRecipients overrides non-author recipients to the author: **VERIFIED**

storage.js:1460-1469 (cite 1458-1465; −2/+4 drift): `recipients = assocEarnedHeadersCommissionRecipients
|| { [author_addresses[0]]: 100 }`; if ANY named recipient is not in `author_addresses` →
`recipients = { [author_addresses[0]]: 100 }` ("non-authors won't pay for our tps fee"). The author
absorbs the ENTIRE delta (positive refund or negative debit). A named-victim recipient can never
receive or absorb a tps-fee delta unless it is an author of the unit — no targeted drain. ✓

## Claim (d) — conservation: net cost = final, no money creation: **VERIFIED** (analytical)

- Declared fee is consumed from inputs at validation (closure, claim a) and never credited.
- Settlement credits/debits exactly (declared − final) to recipients (== author after override, claim c).
- `tps_fees_balances` is a zero-sum prepaid-credit ledger: `BIGINT ... -- can be negative`
  (initial-db/byteball-mysql.sql:986), used only as a minimum-fee floor check at validation
  (validation.js:1085-1092), with the single writer at storage.js:1261 and no conversion to
  spendable outputs.
- Author net: declared burned − (declared − final) credit (or + (final − declared) debit) = final. ✓
- Only writer = storage.js:1261; all other references (composer.js, light.js, validation.js) read-only.

## Claim (e) — double-application candidate: **VERIFIED (no double path in direct callers / sqlite), ONE conditional residual risk (MySQL watermark tie-break)**

### e1 — keying: (address, mci) IS unique, but REPLACE INTO does NOT dedup
`PRIMARY KEY (address, mci DESC)` in initial-db/byteball-mysql.sql:984-987,
byteball-sqlite.sql:1004-1007, sqlite_migrations.js:560-566 → true upsert, no duplicate rows.
**However** the SELECT at storage.js:1260 (`mci<=?`) includes a row at exactly `mci` written by a
prior application, and the delta is then added and REPLACEd — a second application of the same
(address, mci) **would** double the delta. Dedup rests entirely on caller discipline + watermark,
verified below.

### e2 — function boundaries (E1-1's trace): verified
- `advanceMcStability`'s `finish()` (main_chain.js:568-576) does **NOT** update fees — only
  `onDone(arrStabilizedMcis, bStabilizedAATriggers)` (cite :577, −1 drift). ✓
- `updateMainChain`'s `finish()` (main_chain.js:446-454) **does**, but only when
  `!bStabilizedAATriggers && arrStabilizedMcis.length > 0` (cite :448 → actual :451). When AA
  triggers fired, the fees are applied by the writer after `handleAATriggers` (writer.js:722-734). ✓
- `stabilizeMci` (main_chain.js:1244-1265) also calls `updateTpsFees(conn, [mci])` (:1258) — a
  third path the OV-1 trace omitted, but it is likewise under the handleJoint lock. ✓
- Writer loop calls it separately after each additional stabilization (writer.js:738-766). ✓

### e3 — serialization: verified — all four updateTpsFees call sites run under `handleJoint`
- inbound units: network.js:1074 `mutex.lock(['handleJoint'])` → validation → saveJoint (:1165) →
  updateMainChain/loop. Dependent joints route through network.handleJoint (joint_storage.js:92 →
  network.js:1074). composer.js:735, divisible_asset.js:320, indivisible_asset.js:833 lock
  handleJoint before saveJoint. aa_composer.handleAATriggers is invoked only from writer.js:722/753
  and network.js:4289 (startup) — all under handleJoint or handleJoint+initial. (The `write` mutex
  at writer.js:582 is commented out; handleJoint provides the serialization.)
- The inner lock in determineIfStableInLaterUnitsAndUpdateStableMcFlag (main_chain.js:1201) only
  acquires after the outer flow unwinds: `handleResult(bStable, true)` fires first (validation.js:802-813
  → transient error "last ball just advanced" → `process.nextTick(unlock)`), then the queued inner
  job runs. mutex.js:75-86 is non-reentrant (queues) — no deadlock, no concurrent settlement.

### e4 — single-stabilization: verified
Each stabilization pass stabilizes exactly **one** new MCI: advanceMcStability pushes one mci
("// not trying next any more", main_chain.js:540-543); writer.js:718/740 throw if >1. Every pass
reads the last-stable state fresh from the DB under the lock → no mci is stabilized twice, and the
fees for each freshly-stabilized mci are applied exactly once.

### e5 — updateMissingTpsFees re-runs / restart: verified
- Called only at startup (network.js:4290, under `handleJoint`+`initial` before any unit
  processing) and watermark-guarded: processes only mcis > max(mci in tps_fees_balances)
  (storage.js:1267-1286). Every processed good non-AA unit writes ≥1 row (getTpsFeeRecipients never
  returns empty — author[0]:100 at minimum), so the watermark is monotonic across sessions.
- Restart rebuilds assocStableUnitsByMci via initCaches (network.js:4266; storage.js:2328-2370),
  but the watermark is DB-persisted → no re-settlement of covered mcis.
- Crash-consistency: updateMainChain.finish's fee rows share the unit-save transaction (atomic);
  stabilizeMci and the writer loop write fee rows in a separate transaction AFTER the is_stable
  commit — a crash in between leaves no fee rows; startup catch-up then applies exactly once.
- Two MCIs in one batch (updateMissingTpsFees): ascending order, each mci's delta read off the
  prior mci's row in the same transaction — cumulative by design, each delta once.

### e6 — CONDITIONAL RISK (MySQL only): watermark tie-break in getLastTpsFeesMci
storage.js:1287-1290: `SELECT mci FROM tps_fees_balances ORDER BY ${sqlite ? 'rowid' :
'creation_date'} DESC LIMIT 1`. MySQL `creation_date` is second-resolution (`TIMESTAMP NOT NULL
DEFAULT CURRENT_TIMESTAMP`, byteball-mysql.sql:985 — no fractional precision), unindexed, with no
secondary sort key. When ≥2 mcis are settled within the same second (a catch-up range written by
one updateMissingTpsFees transaction, or back-to-back stabilization bursts via writer.js:738-766 /
stabilizeMci / updateMainChain.finish), all those rows share the max creation_date and `LIMIT 1`
tie-breaking is nondeterministic → it can return a row whose mci is NOT the max mci. On the next
startup, updateMissingTpsFees then reprocesses the higher mcis (stale watermark < last_stable_mci),
re-reading balances that already include the previous application → **double-application of those
deltas** (double-credit for positive deltas/refunds, double-debit for negative). The reprocessed
units are present in the startup cache (initStableUnits bounds top_mci by
`last_ball_mci_of_last_tps_fees_mci` when the watermark lags, storage.js:2334-2340), so the
re-application executes. sqlite is immune (`rowid` is insertion-monotonic). Not directly
attacker-triggerable (needs a node restart + same-second multi-mci settlement + stale tie-break),
but a latent value-leak hazard on MySQL hubs. Fix: `SELECT MAX(mci) ...` or a dedicated watermark
row. **Residual risk — not a confirmed finding** (MySQL tie-break behavior is not determinable from
the pinned source alone).

## Notes
- E1-1's lab probe (`evidence/lab/e1-1-conservation.js`) directly demonstrates the no-dedup
  property (double-call doubles the balance) — consistent with e1 here; it never logged results
  (timed out), so no raw log exists.
- OV-1's line cites drift +4/−3/−2 lines but match the same code. The adjudication conclusion
  (conservation + recipient override + single application) holds; the MySQL watermark tie-break is
  the one gap in OV-1's "no double-credit" reasoning (it is conditional and outside the sqlite
  local box).

## Verdict JSON

```json
{
  "id": "ER-4",
  "verdict": "verified",
  "per_claim": [
    {
      "claim": "a: declared tps_fee burned from inputs at save (validation.js:2654-2656)",
      "verdict": "verified",
      "evidence": "validation.js:2650-2653 closure includes tps_fee; :198-199 nonnegativity; :1070-1093 min-fee floor; only writer of tps_fees_balances is storage.js:1261 (delta only)"
    },
    {
      "claim": "b: settlement applies ONLY the delta (declared - final) (storage.js:1246-1261)",
      "verdict": "verified",
      "evidence": "storage.js:1249 total_tps_fees_delta = declared - final; :1258 per-share floor; :1261 REPLACE INTO; :1248 actual_tps_fee is a record, not a balance"
    },
    {
      "claim": "c: getTpsFeeRecipients overrides non-author recipients to author (storage.js:1458-1465)",
      "verdict": "verified",
      "evidence": "storage.js:1460-1469: any non-author recipient -> {author[0]: 100}; no targeted drain"
    },
    {
      "claim": "d: conservation: net cost = final, no money creation",
      "verdict": "verified",
      "evidence": "closure burns declared (a); settlement credits only (declared - final) to author (b+c); tps_fees_balances is zero-sum prepaid ledger (schema comment 'can be negative', single writer :1261, floor-check use only validation.js:1085-1092); author net = final"
    },
    {
      "claim": "e1: (address, mci) unique keying makes REPLACE INTO safe",
      "verdict": "verified-with-caveat",
      "evidence": "PRIMARY KEY (address, mci DESC) in byteball-mysql.sql:984-987, byteball-sqlite.sql:1004-1007, sqlite_migrations.js:560-566; BUT storage.js:1260 SELECT reads the row at exactly mci, so a second application of the same mci WOULD double the delta - dedup rests on caller discipline, not the key"
    },
    {
      "claim": "e2: advanceMcStability.finish does NOT update fees; updateMainChain.finish does",
      "verdict": "verified",
      "evidence": "main_chain.js:568-576 finish() only calls onDone; main_chain.js:446-454 finish() calls updateTpsFees when !bStabilizedAATriggers (writer.js:722-734 covers the AA-trigger case); stabilizeMci also settles via :1258; writer loop writer.js:738-766"
    },
    {
      "claim": "e3: callers serialized under handleJoint/write locks",
      "verdict": "verified",
      "evidence": "all 4 updateTpsFees sites under handleJoint (network.js:1074->1165, composer.js:735, divisible_asset.js:320, indivisible_asset.js:833, aa_composer via writer.js:722/753 or network.js:4289); inner lock main_chain.js:1201 acquires only after transient-error unwind (validation.js:802-813; mutex.js:75-86 non-reentrant queues)"
    },
    {
      "claim": "e4: no path where the same (address, mci) delta applies twice",
      "verdict": "verified-with-caveat",
      "evidence": "single-mci stabilization (main_chain.js:540-543; writer.js:718/740 throw if >1); fresh last-stable reads under lock; watermark-guarded startup catch-up (storage.js:1267-1286, network.js:4290); crash-consistency split-transaction cases recover via startup catch-up; CONDITIONAL HOLE: MySQL watermark tie-break in getLastTpsFeesMci (storage.js:1287-1290 ORDER BY creation_date DESC LIMIT 1, second-resolution TIMESTAMP, no tie-breaker) can return a non-max mci after same-second multi-mci settlement -> next startup double-applies higher mcis (units present in cache per storage.js:2334-2340). sqlite immune (rowid). Residual risk, not confirmed"
    }
  ]
}
```
