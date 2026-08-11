# CHAIN-1 — composition pass over F1+F2+F3+F4 (chainability)

Pinned `a7eb776afc68ed4bed05ba554f7f1e95f5d49b44`. Scope: per `evidence/round2/BRIEFS.md` CHAIN-1.
All line refs verified against the pinned tree.

## Angle 1 — S1 root: F1 and F2 share one primitive; the family is bigger than two sites

**The shared root:** old-DAG attachment (a unit whose validation-time `last_ball_mci <
pemCurvesFixMci` with `hasBall=true`) passes full unit validation (no recency requirement on
parents, validation.js:639-833; the AA-definition guard at :1764 requires `!hasBall` — a
ball-carrying old-DAG definition passes) and then reaches evaluation-side gates that are keyed on
the **bare** `mci` with **no** `!hasBall && getMinRetrievableMci()` disjunct. The validation-side
gates in `formula/validation.js` carry the disjunct (17+ sites, e.g. :281, :338, :525, :534, :702,
:810, :1267); the evaluation-side gates in `formula/evaluation.js` do not (10+ sites, listed
below). For a `hasBall=true` old-DAG unit the disjunct's second arm never fires (`!hasBall` is
required), so the validation side lets the oversized forms through and the evaluation side skips
every cap.

**Enumerated bare-mci gates in formula/evaluation.js (all `pemCurvesFixMci`, none carry the
disjunct):**

| line | gate | what is skipped below the fix |
|---|---|---|
| 327 | `arr[1].length > 30` (min/max/hypot) | arg-count cap |
| 1130 | `arrItemExprs.length > 100` (foreach/map/filter/reduce) | expression-count cap |
| 1169 | `arrPairs.length > 100` (dictionary literal) | dict-size cap |
| 1601 | `delete objUnit.actual_tps_fee` | canonicalization step (skipped) |
| 1654 | `count_signed_packages >= MAX(3)` | the 3-package cap — **F2** |
| 1787 | merkle sibling guards (≤50, non-empty) | the sibling cap — **F1 bonus** |
| 1810 / 1849 | `isTooBigObj(res.obj)` | object-size cap after json/feed ops |
| 2558 / 2588 | `arrExpressions.length > 30` (search_param_list) | search-param cap |

**Chainability verdict — Angle 1: `amplifier_found`.** If the stabilization link (KP-F2-link)
holds, F1/F2 are not two findings but one family: "evaluation-side resource caps are position-gated
without the network-height disjunct — N sites". The individual caps are bounded amplification
(min/max/array/dict caps bounded by unit size); the expensive members are the signed-package
validation (per-call DB + definition walk — F2) and merkle verification (F1). The family finding is
stronger than either site alone because the fix is one pattern (add the disjunct to all eval-side
gates), and the sweep shows the migration is simply unfinished there.

**Getter path — closed as an alternative reachability:** `executeGetterInState`
(formula/evaluation.js:3374-3396) sets `last_ball_mci = props.main_chain_index` (the node's CURRENT
last unit) — getters run at the current mci, so the bare gates fire and the caps are enforced. No
old-mci reachability via `light/execute_getter`. (The f5 comment about getters amplifying expensive
ops remains, but not via S1.)

## Angle 2 — F3 x F4 interaction: bounded (no material composition)

- F4's flood needs the attacker's units **on the MC** in a 1-second window (`getFinalTps` counts
  stable MC units, storage.js:1178-1218). F3's forked units are off-MC → they do not contribute to
  the count → the invisible fork does not multiply the fee window.
- F4 does not need old-DAG attachment (its units anchor on the tip; the elapsed=1 trick is
  timestamp-based, not position-based).
- No shared primitive, no amplifier. Each stands alone (F3 bounded below; F4 economics-capped per
  r2).

## Angle 3 — persistence-of-effect / sibling sweeps

**3a. Spend-proof address-validation siblings — swept, bounded.**
- The only gap is the message-level key `(spend_proof, address)` where the address must merely be
  *an author* (validation.js:1557-1568), not the output owner — the F3 dodge (r1's A_own
  experiment: accepted+saved while the victim's row exists).
- **The decisive bound:** the input-level check (`checkInputDoubleSpend` → `checkForDoublespends`,
  validation.js:2255-2262) keys on `(src_unit, src_message_index, src_output_index)` — not
  dodgeable, since spending X requires referencing X's creation record. For **indivisible
  (fixed-denomination)** private assets the chain walker binds the claimed input to the actual
  predecessor (`prevElement.unit === payload.inputs[0].unit`, indivisible_asset.js:206-208). For
  **divisible** private assets the claimed input must match a real DB output row
  (`SELECT ... FROM outputs WHERE unit=? AND message_index=? AND output_index=?` —
  divisible_asset.js:118-122; "not 1 row when selecting src output" otherwise). So both paths'
  input-layer checks detect the double-spend exactly as public assets do: **included → clean
  rejection; forked → accepted (standard fork race).**
- **Net verdict on F3:** the dodge defeats a *redundant* detection layer; the input layer provides
  equivalent protection; the ledger outcome is identical to a public-asset fork. F3 as a
  vulnerability is **bounded** (info/defense-in-depth: the spend-proof uniqueness key should bind
  the output identity, and its redundancy makes it pure complexity). The empirically confirmed
  behavior (r1: A_own saved) is real but the impact ceiling is the standard fork race. Hand to the
  KP-F3 kill-pair with this analysis; the establish side's strongest remaining form is the
  "designed early-detection defeated" argument, which the input-layer equivalence rebuts.

**3b. Other bare-mci eval gates — enumerated (Angle 1 table).** No additional gate class beyond
the family listed above.

## Angle 4 — temp_data fee claim (f12-T5): REFUTED (settled)

`validateInlinePayload` case `temp_data` (validation.js:1977-1991): when `data` is present,
`objectLength.getLength(payload.data, true)` is computed and compared against the claimed
`payload.data_length` — **mismatch → clean rejection** (`"data_length mismatch, expected ..., got
..."`, validation.js:1983-1985). The paid fee is `ceil((data_length + 4) * TEMP_DATA_PRICE)`
(object_length.js:110-112) — computed from the *reconciled* length. No underpayment path exists
for inline temp_data. (The `data`-absent case charges the claim, but the data must later be
fetched and hash-verified — the claim is the only source of truth for externally-stored data, and
the hash binds it.) **f12-T5 closed.**

## Per-angle verdicts (chainability)

| angle | verdict | evidence |
|---|---|---|
| 1 — S1 root family | **amplifier_found** (conditional on KP-F2-link) | 10+ bare-mci eval gates enumerated; validation side has the disjunct (17+ sites), eval side none |
| 2 — F3 x F4 | **bounded** | fork units off-MC (not counted); no shared primitive |
| 3a — F3 (spend-proof dodge) | **bounded** | input layer keys on non-dodgeable output identity; chain-walker + DB-lookup bind claimed inputs; outcome = standard fork race |
| 3b — eval gate siblings | **new_finding family** (same as angle 1) | the S1 eval-side family is the durable finding form |
| 4 — temp_data fee | **bounded / refuted** | validation.js:1983 reconciles data_length vs actual |

## Recommendation to the orchestrator

1. Fold F1+F2 into one family finding ("eval-side S1 gate family") pending KP-F2-link; if the link
   fails, file each site as real-but-capped (no-ball transient window only).
2. Demote F3 to info/defense-in-depth unless the KP-F3 establish side surfaces a counter-argument
   to the input-layer-equivalence bound.
3. Close f12-T5 (temp_data) permanently.
4. The getter path is closed as an S1 alternative — do not re-hunt it.

## Files

- `evidence/round2/CHAIN-1.md` — this report
- Line refs: formula/evaluation.js (327, 1130, 1169, 1601, 1654, 1787, 1810, 1849, 2558, 2588,
  3374-3396); formula/validation.js (disjunct sites); validation.js (1557-1568, 1764, 1977-1991,
  2255-2262); indivisible_asset.js (206-208); divisible_asset.js (118-122); storage.js (1178-1218);
  object_length.js (110-112)
