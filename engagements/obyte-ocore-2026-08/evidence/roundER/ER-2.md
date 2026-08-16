# ER-2 — review of E1-5 (parent_composer crash) + E1-11 (storage accounting)

**Reviewer:** independent (fresh context) · **Pinned source:** ocore `a7eb776afc68ed4bed05ba554f7f1e95f5d49b44` (git HEAD verified)
**Inputs read:** `evidence/roundE1/E1-5.md`, `evidence/roundE1/E1-11.md`, `evidence/lab/e15/e15-throw-repro.log` (2321 lines), `evidence/lab/e15/e15-parent-crash.js`
**Method:** raw-log line-by-line verification + source line verification + independent re-execution of the conservation probe on the pinned tree.

---

## Claim (a) — E1-5: filterParentsByTpsFeeAndReplace throw → unhandled rejection when all candidates underpay

### Verdict: **verified** (with one precision — the crash itself was intercepted by the lab handler; unhandled rejection is directly observed, crash is Node-default semantics)

### Raw-log evidence (e15-throw-repro.log)
The claimed exclusion sequence is literally present, in order:
- `:2291` `E1-5 VICTIM FIRST COMPOSITION` (fresh victim address, no own free units — pool = 16 seeded attacker units, `E1-5 SEEDED-UNITS: 16`, `E1-5 FREE-POOL-SIZE: 16`)
- `:2293-2294` `getCurrentTps shift=0 ... current tps with shift 0 33`
- `:2295-2310` **exactly 16** `skipping potential parent <unit> as its paid tps fee per unit 1 < min parentable tps fee 21` (counted: gsHCQ, qUXVS, svcKO, /QmPf, SNiwH, 5Sc1f, mfL/, c0BV9, GB6W6, DlQ0z, 1z6zy, Y26lo, R59NV, TiHJm, GSbt0, RzJxI)
- `:2311` `replacement_parents [ 'F5UCrX...=' ]` → `:2312` `added replacement parent F5UCrX...` (genesis added, recursion)
- `:2315` `skipping potential parent F5UCrX... as its paid tps fee per unit 0 < min parentable tps fee 21` (genesis paid fee 0)
- `:2316` `replacement_parents []` (no replacements)
- `:2317-2319` `E1-5-UNHANDLED-REJECTION: Error: all potential parents underpay the tps fee` with stack `at filterParentsByTpsFeeAndReplace (parent_composer.js:461:9)` → `at async ... :458:11` → `at async ... :384:12`
- `:2320` `E1-5-PROPAGATION: unhandled rejection (Node15+ default: process crash)` (end of log, 2321 lines)

The brief's compression "16 exclusions → no replacements → unhandled rejection" is accurate; the full sequence is 16 exclusions → 1 replacement (genesis) → 1 exclusion → no replacements → throw.

### Source evidence (pinned tree)
- Throw site: `parent_composer.js:461` `throw Error('all potential parents underpay the tps fee')` inside `filterParentsByTpsFeeAndReplace` (function at 426; multiplier default 3 at 428-429; self-authored exception at 445-449; recursion at 458; sibling throw "all potential parents have the top OP list" at 496). All match the claimed lines exactly.
- The throw executes inside the `conn.query(..., async function (prows) {...})` callback (`parent_composer.js:374`), reached via `await filterParentsByTpsFeeAndReplace(...)` at `:384`.
- The callback's returned promise is discarded: `sqlite_pool.js:132` `last_arg(result)` invokes the user callback and ignores its return value. Nothing awaits it → rejected promise is unhandled.
- Caller shapes verified: `composer.js:361` (callback API, async callback), `composer.js:621` (promise API — the wrapper promise only settles via onDone, which the throw bypasses → **hang**), `composer.js:862` (callback API). So the error path `onDone(err)`/`cb("unable to find parents: ...")` is bypassed on every shape.
- Default crash semantics: Node ≥15 unhandled-rejection default is throw-as-uncaught-exception; `network.js:4367-4377` uncaughtException handler logs then `throw err; // crash the process`. Verified.
- `getPaidTpsFee` genesis special case `storage.js:1402-1403` (`if (unit === constants.GENESIS_UNIT) return 0`) — matches the log's `paid tps fee per unit 0` for genesis.

### Precision (does not change the verdict)
The raw log's `E1-5-UNHANDLED-REJECTION` line is printed by the repro's **own** handler (`e15-parent-crash.js:338-341`: `process.on("unhandledRejection", ...)` → log → `process.exit(0)`). So the lab observed the unhandled rejection but **intercepted the crash** and exited 0. The "process death" claim rests on Node ≥15 default semantics + network.js re-throw, which is correct production behavior for a node without a custom rejection handler. E1-5's report is honest about this ("Observed in the repro: unhandled rejection"). Claim (a) verified as stated ("unhandled rejection when all candidate parents underpay" — directly observed; "crashes the composing process" — default semantics, verified at source level).

---

## Claim (b) — pool is attacker-influenceable (top-16, ORDER BY last_ball_mci DESC LIMIT 16)

### Verdict: **verified** for pool shape and exclusion logic; **partially verified** (source-traced, not multi-node demonstrated) for the flood reachability — matching E1-5's own honest caveat

- LIMIT 16: `parent_composer.js:371-372` (`LIMIT ?` with `[timestamp, constants.MAX_PARENTS_PER_UNIT]`) and `constants.js:44` `exports.MAX_PARENTS_PER_UNIT = 16`. **Verified.**
- Ordering: `parent_composer.js:370` `ORDER BY last_ball_mci DESC` — top-16 pool shape by highest last-ball MCI. **Verified.**
- Pool predicate: `sequence='good' AND is_free=1 AND archived_joints.unit IS NULL AND timestamp<=now` (`parent_composer.js:367-369`); AA-response 30-second age filter in non-devnet (line 373). Any peer's valid unit is stored free (`is_free=1`) and becomes pool-eligible; flooding ≥16 tip-anchored units with the highest `last_ball_mci` pushes the victim's own units off the cap, defeating the self-authored exception (445-449). Source-plausible; **the multi-node flood itself is not demonstrated** (lab seeded the pool directly — E1-5 §3 caveat (1) acknowledged; consistent with verdict "partial, source-traced").
- Exclusion logic: non-AA candidates with `paid_tps_fee_per_unit < current_tps_fee * (conf.min_parentable_tps_fee_multiplier || 3)` are excluded unless authored by the composer's own from-addresses (428-449). The log demonstrates the exact math: current tps 33 → min parentable 21 = 7×3 (rate-change exposure: units paid 1 at their low-rate composition time undercut the later min). **Verified.**

---

## Claim (c) — E1-11: storage accounting conserved (16/16) + checkStorageSizes throw → scheduled crash

### Verdict: **verified** (independent replication: 0 mismatches across a 20-shape superset) + **verified** for the scheduled-crash mechanics

### (c1) Accounting conservation — independently re-executed on the pinned tree
Replicated `getTypeAndValue` / `getValueSize` / the `checkStorageSizes` measure (`data.value.length - 2`) using the pinned tree's own `string_utils.getJsonSourceString` and `decimal.js`:

```
OK  plain string / quote / bslash / newline / unicode('héllo→世界') / emoji😀 / lone surrogate / empty string
OK  int / float / exp(1e21) / negative / zero / -0 / NaN / Infinity
OK  decimal hi-prec / subnormal(1e-300) / exp
OK  nested object with embedded quote
TOTAL MISMATCHES: 0 of 20
```

- By construction: `getValueSize` (aa_composer.js:1511-1521) mirrors `getTypeAndValue` serialization (aa_composer.js:1497-1507) exactly for every branch (string `.length`; number `.toString().length`; Decimal `.toNumber().toString().length`; wrappedObject `getJsonSourceString(obj, true).length`).
- The audit measure matches because the kvstore round-trip is lossless for the length: `kvstore.js` wraps `level-rocksdb` = `levelup(encode(leveldown(...)))` (verified in node_modules: level-packager/level-packager.js, level-rocksdb/level-rocksdb.js), and `encoding-down@7.1.0` defaults `keyEncoding`/`valueEncoding` to **'utf8'** (node_modules/encoding-down/index.js:40-41) → `createReadStream` emits **strings**, so `data.value.length` = JS code-unit length = `getValueSize` — including unicode and surrogate pairs.
- Lifecycle conservation (source-traced): deletion subtracts `var_name.length + getValueSize(original_old_value)` (aa_composer.js:1533-1536); new var adds `var_name.length + newSize`; update adds `newSize - oldSize` (1547-1549); key parse `data.key.substr(3,32)` / `substr(36)` (1918-1919) matches the `'st\n'+address+'\n'+var_name` write key (1485). Summed deltas = final − initial. Consistent.

Minor imprecision in E1-11 (not claim-breaking):
- "gate active since genesis on every network" — `aaStorageSizeUpgradeMci = 0` (constants.js:136) only under `process.env.devnet || process.env.GENESIS_UNIT` (local forks); mainnet default is 5210000 (constants.js:94), testnet 1034000. Practically the gate is active on every current network (mainnet passed MCI 5.21M long ago), and on local forks since genesis — so the conclusion holds; the literal "since genesis" phrasing is wrong for mainnet.
- `FULL_TRANSFER_INPUT_SIZE` = 0 or 29 bytes (`TRANSFER_INPUT_SIZE=0` aa_composer.js:37; `TRANSFER_INPUT_KEYS_SIZE=4+13+12=29` :41; used at :456), not "~200 bytes".

### (c2) Gate (Q1)
`aa_composer.js:1553-1557`: `new_storage_size < 0` → throw (:1554); `byte_balance < new_storage_size && new_storage_size > FULL_TRANSFER_INPUT_SIZE && mci >= aaStorageSizeUpgradeMci` → `cb("byte balance ... would drop below new storage size ...")` (:1556-1557). E1-11 cites 1550-1551 — 5-line drift, same code. **Verified.**

### (c3) checkStorageSizes scheduled crash
- Function `aa_composer.js:1906-1940`; mismatch `throw Error("storage size mismatch on ...")` at :1928-1929 inside the `conn.query` callback (E1-11 cited :1931 — 2-3 line drift); stream-error throw at :1936.
- Scheduling `aa_composer.js:2061-2062`: `setTimeout(checkStorageSizes, 1000); setInterval(checkStorageSizes, 600*1000)` guarded by `if (!conf.bLight)` — every full node, startup + 10-minute cadence. **Verified exactly as cited.**
- Throw escapes via `mutex.lockOrSkip` → `takeConnectionFromPool` → stream/query callbacks with no try/catch → uncaughtException → `network.js:4367-4377` re-throw → process crash. **Verified.**
- Not attacker-reachable today (accounting conserved through every drivable path; 0 mismatches in both E1-11's run and this review's independent run) — consistent with E1-11's own "hardening note, not a finding" classification. Residual: crash-on-kill inconsistency between the rocksdb batch and sqlite COMMIT (two-store, no cross-store transaction) remains argued, not demonstrated — as E1-11 states.

---

## Per-claim verdicts

| # | Claim | Verdict | Decisive evidence |
|---|-------|---------|-------------------|
| a | Throw at parent_composer.js:461 → unhandled rejection when all candidates underpay | **verified** (crash = Node-default semantics; rejection directly observed) | log :2295-2319; parent_composer.js:374/384/428-461; sqlite_pool.js:132; network.js:4367-4377; e15-parent-crash.js:338-341 |
| b | Pool attacker-influenceable: top-16 `ORDER BY last_ball_mci DESC LIMIT 16` + exclusion logic | **verified** (shape+exclusion); reachability **partially verified** (source-traced, no multi-node demo) | parent_composer.js:367-372, 428-449; constants.js:44; E1-5 §3 caveat |
| c | E1-11 accounting conserved (16/16) + checkStorageSizes throw → scheduled crash | **verified** (0/20 mismatches in independent rerun) | aa_composer.js:1497-1521, 1553-1557, 1906-1940, 2061-2062; constants.js:94/136; encoding-down default utf8 |
| — | Attacker reachability of the crash (pool flood) | **overstated** (E1-5 already concedes this: lab seeded pool; flood is source-traced) | E1-5 §3; log :2287-2290 |

## Residual risks (reviewer's own)

1. **Crash-not-observed gap:** the lab's unhandledRejection handler (`process.exit(0)`) means the actual process-death behavior was never executed. A 5-minute run of a stock node (no custom handler) under the same conditions would close this; without it, the crash claim is Node-semantics + network.js, not an observation.
2. **Pool-flood reachability is unproven end-to-end:** whether 16 attacker tip units can reliably occupy the victim's top-16 `last_ball_mci` window (and stay `is_free=1`, unarchived, sequence good) requires a multi-node local fork — not demonstrated.
3. **checkStorageSizes crash-on-kill window:** the rocksdb-batch vs sqlite-COMMIT ordering argument remains untested; if a mid-write kill can leave a permanent mismatch, every full node crash-loops on restart — but this is an operator/node-kill path, not attacker-controlled.
4. **Unicode edge shapes** (emoji, lone surrogates) verified only by replication of the three functions, not by a real rocksdb round-trip; utf8-encoding default verified in node_modules, but a real store round-trip was not executed in this review.
5. Both candidates sit in the out-of-scope availability class (node-side-fixable without network coordination); E1-5's own verdict `capped` and E1-11's hardening-note classification are consistent with the evidence.

## Files

- This report: `evidence/roundER/ER-2.md`
- No changes to the pinned ocore tree (`git status` untouched); no new lab artifacts.
