# HARDENING-NOTES.md — confirmed-mechanism / unreachable / below-floor observations

Pinned: `a7eb776afc68ed4bed05ba554f7f1e95f5d49b44`. These are REAL mechanisms confirmed on the
pinned code, with the reason each is NOT a reportable finding under the program rules. They are the
engagement's hardening backlog — the operator may forward them to the vendor as defense-in-depth
suggestions (filing is operator-only).

## HN-1 — S1 old-DAG rule-gating: incomplete disjunct migration (validation + eval sides)
- **Mechanism (confirmed):** upgrade-gated rules keyed on `last_ball_mci >= constants.X` without the
  `!hasBall && getMinRetrievableMci() >= X` disjunct: validation.js:741 (non-AA parent gate),
  :986-992 (outer AA-trigger gate — `!last_ball_mci` skips ALL trigger validation), :1025-1028
  (count_primary_aa_triggers>1), and formula/evaluation.js 10+ bare-mci gates (min/max/hypot,
  array/dict literals, is_valid_signed_package cap, merkle sibling cap, search-param caps,
  isTooBigObj). The validation-side migration is complete (17+ sites with the disjunct); the
  evaluation side has none.
- **Why not a finding:** KP-F2-link proved old-DAG-attached units cannot stabilize (witnessed level
  is ancestry-derived; best-parent sorts by it; MC walk starts from the tip) — every execution path
  runs at a current position. The skips affect only never-stabilizing junk units → no consensus or
  availability impact.
- **Fix:** add the disjunct to all eval-side gates (one pattern) and to the three validation sites.
- **Severity if reachable ever:** Medium availability (valid-unit amplification — the signed-package
  case measured 20× call-count and 10× budget divergence).

## HN-2 — Uncaught-throw-on-attacker-input pattern in async completion callbacks
- **Mechanism (confirmed):** `throw Error(...)` in `conn.query`/async completion callbacks escapes
  async's iterator try/catch → `uncaughtException` → network.js:4367-4379 re-throw → process death.
  Sites: validation.js:1667 (conflicting record from another address), :1686 ("unreachable code"),
  :2292 ("spend proof didn't help"), :2451 ("spending a stable temp-bad output").
- **Why not a finding:** all four are unreachable from attacker input in the consistent ledger
  (1667: address-binding 1557-1568 precedes; 1686/2451: temp-bad state machine — resolution is
  atomic with ball creation; 2292: message-level check preempts + flow ordering).
- **Fix:** convert throws to `cb(err)` (the 05f291d8 light-path pattern); add a try/catch at the
  ws-message boundary. Any future reachable site becomes a network-wide crash-loop.

## HN-3 — SQL `+` unary-plus idiom on TEXT columns (5 sites)
- **Mechanism (confirmed):** `+competitor_units.sequence='good'` etc. at main_chain.js:1401/1415,
  headers_commission.js:27/40/43/58, validation.js:1328/1333 — relies on unary-plus-no-op semantics
  for non-numeric strings, which is undocumented and engine-specific (Oracle MySQL coerces pure
  integers only; sequence values are never numeric → correct today on sqlite/MariaDB/MySQL5.7/8.0,
  empirically tested).
- **Why not a finding:** correct on every supported engine (tested); `conf.js:66-68` marks mysql
  "not currently supported".
- **Fix:** remove the `+` prefixes (5 sites). If sequence ever carried numeric values or a future
  engine coerced differently: DB-backend-dependent final-bad resolution → divergent ball hashes →
  consensus split.

## HN-4 — tps-fee estimation/settlement asymmetry + unbounded settlement
- **Mechanism (confirmed):** `getLocalTpsFee` (estimation) applies `tps_fee_multiplier` (10) while
  `getFinalTpsFee` (settlement) does not — estimation can over-charge by 10× at the same rate; and
  the settlement fee itself is unbounded relative to author balances (see finding 004).
- **Why not a finding (beyond 004):** the estimation asymmetry is sender-side economics (self-DoS);
  the settlement unboundedness is finding 004 (Low, below the in-scope bar).

## HN-5 — `getRecentTps` counts future-timestamped units; `getCurrentTps` does not
- **Mechanism (confirmed, source):** storage.js:1447 (`ts - objUnitProps.timestamp <= period` counts
  future-dated units) vs :1360 (`timestamp > now → continue` skipped). An attacker posting units
  dated now+1..now+5 at ≥15/s inflates the `min_acceptable_tps_fee_multiplier` to 5 network-wide
  (3.33× the 1.5 default).
- **Why not a finding:** griefing-class fee inflation; below the $1,000 minimum impact; one-line fix
  (skip future timestamps in getRecentTps).

## HN-6 — `handleSavedPrivatePayments` missing return after catch (network.js:2324-2331)
- **Mechanism (confirmed, definite control-flow bug):** the catch block deletes the handled-chain
  row and sends `result:'error'` but does NOT return — processing continues with `json_payload_hash`
  undefined, the event key becomes `...-undefined-...`, and `validateAndSavePrivatePaymentChain`
  still runs (double-cb possible). The wallet sibling (wallet.js:1029-1031) has the `return cb(...)`.
- **Why not a finding:** outcome branches are (a) silent-drop (row already deleted) or (b)
  accept-despite-error — neither moves funds incorrectly (the payload is attacker-controlled
  anyway); impact unclear, no fund path demonstrated.
- **Fix:** add the missing `return`.

## HN-7 — Unbounded joint streaming and unhandled-joints growth (network)
- **Mechanism (confirmed):** `refresh`/`subscribe` with mci=0 streams the full unstable/free joint
  set with no cap or rate limit (network.js:2634-2640, 842-852); missing-parent joints grow
  `unhandled_joints` unboundedly (joint_storage.js:70-95). No rate limiting anywhere in the network
  layer (grep: zero hits).
- **Why not a finding:** node-side caps resolve without network coordination → out of scope per the
  DoS rule. **Fix:** caps + per-peer rate limits.

## HN-8 — Private-payment secrecy leak via console logging
- **Mechanism (confirmed):** indivisible_asset.js:126-131 logs spend-proof inputs including the
  blinding and amount; :241-258 logs inserted outputs with blinding. Node operators can learn
  private-payment amounts.
- **Why not a finding:** privacy disclosures are not on the program's impact list (fund loss/freeze
  only). **Fix:** remove/redact the logs.

## HN-9 — Light-mode hub-position trust
- **Mechanism (confirmed):** light wallets take parent_units/last_ball/tps_fee verbatim from the
  hub (composer.js:312-330) and light validation short-circuits after structural checks
  (validation.js:340-344).
- **Why not a finding:** light model trusts the hub by design; full nodes still validate posted
  units. **Fix:** verify position reasonableness light-side (optional hardening).

## HN-10 — Fee-penalty / economics residual
- `getOversizeFee` Infinity overflow for size > 710×threshold (storage.js:1145-1155): sender-side
  only (self-DoS), held.
- Headers-commission SHA1 winner grinding (headers_commission.js:249-257): economically unattractive
  at current fee levels, held.
- `sum` op float arithmetic in definitions (definition.js:1228-1245): bounded by MAX_CAP < 2^53,
  held.

## Delivery note
All HN items are engagement-local records. The operator decides which (if any) to forward to the
Obyte Foundation as hardening suggestions alongside the three findings (001/003/004). None are
claimed as bounty-reportable under Primacy of Rules.

## HN-11 — Scheduled uncaught throw on unknown device key (device.js:431-432)
- **Mechanism (verified):** remote, zero-cost wallet crash — any peer can deliver a device message
  encrypted to an unknown key; `decryptPackage` schedules an uncaught throw 100ms later. The
  intended pattern (eventBus nonfatal_error) is commented out beside it.
- **Why not a finding here:** wallet/device layer, outside the declared DLT surfaces; node-side fix.
  **Fix:** restore the eventBus.emit pattern (delete the throw).

## HN-12 — is_valid_sig / vrf_verify with prover-supplied keys (E1-4)
- An AA that keys on trigger-supplied pubkeys gets no authenticity (any self-chosen key+sig pair
  verifies — measured). The opcode makes no identity claim — sound as stated; AA authors must pin
  the key. is_valid_signed_package replay: last_ball_unit is optional (evaluation.js:1666) — an AA
  using it for authorization must require freshness itself.

## HN-13 — checkStorageSizes audit throw -> scheduled node crash (E1-11)
- The periodic checkStorageSizes audit (aa_composer.js:1913-1935) throws on ANY mismatch -> uncaught
  -> node crash, scheduled at startup + every 10 minutes on every full node (aa_composer.js:2061-2062).
  Not attacker-reachable today (storage accounting conserved, 16/16 shapes measured) — the HN-2
  uncaught-throw pattern. Fix: log + repair instead of throw.

## HN-14 — parent_composer throw via fee-inflation (E1-5/OV-4)
- filterParentsByTpsFeeAndReplace (parent_composer.js:~461) throws "all potential parents underpay
  the tps fee" when every candidate parent's paid fee is below the local estimate — reachable when
  HN-5's future-timestamp units inflate the local fee estimate above historical parents' paid fees:
  the victim wallet's composition crashes. Wallet-layer client DoS; fix: fall back to the best
  available parent instead of throwing.

## HN-15 — MySQL-only watermark tie-break → double fee application across restarts (ER-4 e5)
- getLastTpsFeesMci (storage.js:1264-1266) orders by creation_date on MySQL; same-second rows
  tie-break nondeterministically → a stale watermark makes updateMissingTpsFees reprocess higher
  mcis → the (address, mci) delta applies twice (double-credit for refunds, double-debit for fees).
  sqlite immune (rowid). MySQL is "not currently supported" (conf.js:66-68). Not attacker-
  triggerable (needs restart + same-second settlement + stale tie-break). Fix: SELECT MAX(mci) or
  a dedicated watermark column.
