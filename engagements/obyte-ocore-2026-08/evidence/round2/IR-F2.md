# IR-F2 — Independent review of P8 signed-package PoC (F2, eval-side S1 bypass)

- **Reviewer:** independent fresh-context reviewer (IR-F2)
- **Date:** 2026-08-11
- **Target:** obyte-ocore @ `a7eb776afc68ed4bed05ba554f7f1e95f5d49b44` (verified: `git rev-parse HEAD` = `a7eb776afc68ed4bed05ba554f7f1e95f5d49b44`)
- **Builder report reviewed (not trusted):** `evidence/round1/p8.md`; builder raw log `evidence/round1/p8-raw-output.log`
- **PoC executed (unmodified):** `evidence/lab/p8/run.js` via lab harness (`lab-obyte.js` → `evidence/lab/lab.js`), scratch dir `.labdata-ir-f2`
- **Command:** `cd /Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore && LAB_TAG=ir-f2 node lab-obyte.js /Users/matheusvsky/Documents/trab/llm-redteam-harness/engagements/obyte-ocore-2026-08/evidence/lab/p8/run.js`
- **Raw output (this review):** `evidence/round2/raw-logs/IR-F2-p8-raw.log` — exit=0, `LAB-DONE`, fresh keys/address each run.

## 1. Source verification (the claimed mechanism, before trusting any output)

| Claim | Source evidence | Verdict |
|---|---|---|
| 3-call cap gated on **bare** `mci`, no disjunct | `formula/evaluation.js:1654` `if (objValidationState.count_signed_packages >= constants.MAX_SIGNED_PACKAGES_PER_AA_EVAL && mci >= constants.pemCurvesFixMci) return setFatalError("too many signed packages in evaluation", ...)`; `mci` sourced at `formula/evaluation.js:79` `var mci = objValidationState.last_ball_mci` | CONFIRMED |
| `max_complexity = mci >= pemCurvesFixMci ? 10 : 0` (bare gate) | `formula/evaluation.js:1693` | CONFIRMED |
| `MAX_SIGNED_PACKAGES_PER_AA_EVAL = 3`; mainnet `pemCurvesFixMci = 12155000` | `constants.js:70`, `constants.js:101` | CONFIRMED |
| falsy `max_complexity` skips budget | `definition.js:110` `if (objValidationState.max_complexity && objValidationState.complexity + complexity > ...)` (per-node walk check skipped at 0) and `definition.js:632` `if (objValidationState.max_complexity) { ... }` (whole-walk check skipped at 0) | CONFIRMED |
| `max_complexity` flows from eval into definition walk | `signed_message.js:269` builds `objValidationState = { ..., max_complexity }` → `Definition.validateAuthentifiers` | CONFIRMED |
| validation-side gate HAS the disjunct (migration asymmetry) | `formula/validation.js:281,338,492,508,525,534,546,594,702,810,989,1154,1183,1245,1267,1313,1351` all `mci >= constants.pemCurvesFixMci \|\| require('../storage.js').getMinRetrievableMci() >= constants.pemCurvesFixMci`; `is_valid_signed_package` validation case at `:809-812` | CONFIRMED |

## 2. Checkpoint verification from RAW output (my run, `raw-logs/IR-F2-p8-raw.log`)

### 7a — max_complexity 0 vs 10 (instrumented observer on the REAL validateSignedMessage)
```
[P8-7a] below-fix: {"res":true,"err":null,"elapsed":4,"maxComplexity":[0]}
[P8-7a] above-fix: {"res":true,"err":null,"elapsed":0,"maxComplexity":[10]}
```
- Below fix MCI (500000): the real `signed_message.validateSignedMessage` was invoked with `max_complexity=0` (falsy → custom budget skipped).
- Above fix MCI (1500000): invoked with `max_complexity=10`.
- Both return res=true (simple `["sig",{pubkey}]` definition; sig verified — `[P8] simple package sig verify: true`).
- **7a CONFIRMED** — recorded argument divergence 0 vs 10 exactly as claimed.

### 7b — acceptance divergence (20-member `r of set`, walk complexity ~21)
```
[P8-7b] below-fix (max_complexity=0, budget SKIPPED): {"res":true,"err":null,"elapsed":1,"maxComplexity":[0],"results":[{"err":null,"last_ball_mci":-1}]}
[P8-7b] above-fix (max_complexity=10, budget ENFORCED): {"res":false,"err":null,"elapsed":0,"maxComplexity":[10],"results":[{"err":"custom complexity limit 10 exceeded at r.9"}]}
```
- Same package, same definition, same real ECDSA signature. Below the fix MCI it is **accepted** (the 20-member walk completes against the real definition walker — proof the budget is skipped, since any nonzero budget ≤ 10 would have failed earlier); above it is **rejected** with the real engine error `custom complexity limit 10 exceeded at r.9` from `definition.js:110-111`.
- **7b CONFIRMED** — acceptance is position-dependent; identical payload diverges below vs above `pemCurvesFixMci`.

### 7c — call-count divergence (amplification)
```
[P8-7c] n=1  | validation below-fix: ok(complexity=2)  | validation above-fix: ok(complexity=2)  | below: res=true calls=1  | above: res=true calls=1
[P8-7c] n=3  | validation below-fix: ok(complexity=4)  | validation above-fix: ok(complexity=4)  | below: res=true calls=3  | above: res=true calls=3
[P8-7c] n=10 | validation below-fix: ok(complexity=11) | validation above-fix: ok(complexity=11) | below: res=true calls=10 | above: res=null calls=3 err="too many signed packages in evaluation" (line 4)
[P8-7c] n=30 | validation below-fix: ok(complexity=31) | validation above-fix: ok(complexity=31) | below: res=true calls=30 | above: res=null calls=3 err=...
[P8-7c] n=60 | validation below-fix: ok(complexity=61) | validation above-fix: ok(complexity=61) | below: res=true calls=60 elapsed=26ms | above: res=null calls=3 err=...
```
- Below fix MCI: **all N calls run** (N=10/30/60, res=true) — 60 calls observed, no cap.
- Above fix MCI: **cut at 3** (`calls=3`), 4th call hits the fatal `too many signed packages in evaluation` (`formula/evaluation.js:1654`) and the formula result becomes an error.
- Validation side passes at BOTH positions for all N (complexity 2..61 ≤ `MAX_COMPLEXITY=100`) — the definition itself is legal; only the **evaluation** side diverges. This is the exact migration asymmetry (`formula/validation.js` has the disjunct, `formula/evaluation.js` does not).
- **7c CONFIRMED** — 20× structural amplification (60 vs 3) below the gate; the cap only exists above it.

## 3. Reward-hacking / authenticity check

- **Real crypto:** keys from `node_modules/secp256k1` (`publicKeyCreate`), signatures made and verified with real `signature.sign/verify`; `[P8] simple package sig verify: true` and the successful walk in 7b prove real verification, not a stub.
- **Real engine:** `formula/index.js` exports the actual `evaluation.js` `evaluate` and `validation.js` `validate`; packages are delivered via `trigger.data` (the real AA trigger delivery pattern, so dotted authentifier paths survive). Errors `custom complexity limit 10 exceeded at r.9` and `too many signed packages in evaluation` originate in `definition.js:110` and `formula/evaluation.js:1654` respectively — real code paths.
- **Instrumentation is a thin pass-through observer:** the wrapper on `signed_message.validateSignedMessage` only records `(max_complexity, calls, results)` and delegates to the original; it cannot fabricate res/err. The recorded `maxComplexity` values [0]/[10] match the input `mci` positions deterministically.
- **No hardcoded expectations:** the script prints engine output; a mock would not produce position-dependent, engine-generated errors.
- **No network / local only:** run against the scratch sqlite dir under the lab harness. No live node contacted.

## 4. Verdict

**CONFIRMED (independent reproduction)** — all three claimed divergences reproduce on the real path from RAW output:

- 7a: max_complexity 0 (below) vs 10 (above) — `raw log [P8-7a]`
- 7b: 20-member r-of-set accepted below fix MCI, rejected above (`custom complexity limit 10 exceeded at r.9`) — `raw log [P8-7b]`
- 7c: 60 calls below vs 3-cap above, with validation passing at both positions — `raw log [P8-7c]`

The evaluation-side gates (`formula/evaluation.js:1654`, `:1693`) are bare-`mci` where the validation side (`formula/validation.js:281 et al.`) carries the `|| getMinRetrievableMci() >= pemCurvesFixMci` disjunct. The migration is incomplete on the evaluation side, exactly as the builder claims.

## 5. Residual risks / open items (not part of this review's verification)

1. **Stabilization link (reachability boundary):** this PoC proves the eval-side divergence for any AA trigger evaluated with `last_ball_mci < pemCurvesFixMci`. Whether an old-DAG-attached trigger actually stabilizes (gets a ball) and executes on the real network is the open link — that is the KP-F2-link workstream, not demonstrated here. If it cannot stabilize, the mechanism degrades to the no-ball window (transient, `real-but-capped`).
2. **Severity framing:** availability/CPU-amplification class; the overload unit is valid and propagates. In-scope-ness per the DoS-coordination rule hinges on the stabilization link. No fund-loss path identified.
3. **Eval mci provenance** (`validation.js:1761` `top_mci = objValidationState.aa_mci || objValidationState.last_ball_mci`) was asserted by the builder; the PoC sets `objValidationState.last_ball_mci` directly, which `formula/evaluation.js:79` consumes. Consistent with the claim; network-level confirmation belongs to KP-F2-link.
4. Cost figures (20× calls, 10× budget) are structural caps; real per-call cost depends on package definition complexity and DB lookups (e.g., `last_ball_unit` query at `formula/evaluation.js:1666-1670`).

## 6. Files

- `evidence/round2/IR-F2.md` — this report
- `evidence/round2/raw-logs/IR-F2-p8-raw.log` — raw output of the independent run
- PoC `evidence/lab/p8/run.js` — unchanged (no modifications by reviewer)
