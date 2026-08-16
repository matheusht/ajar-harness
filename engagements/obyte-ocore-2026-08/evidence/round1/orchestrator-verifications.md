# Orchestrator independent verifications (during round 1)

These are my own source reads + direct tests, cross-checking hunter claims while the round-1 builders work.

## V1 — Crash family: FOUR uncaught-throw sites in the validation path (not one)
Reading validation.js + main_chain.js directly, the "crash on attacker-input" family has four sites:
1. `validation.js:1662` — `throw Error("conflicting <type> spent from another address?")` — unconditional, fires before `conf.bLight`, when a conflicting spend-proof/input record's address is not among the unit's authors. (f8-TRIPLE-1 — remote, persistent, hits light wallets.)
2. `validation.js:1678` — `throw Error("unreachable code, conflicting ...")` — when a conflicting record's unit is `temp-bad` (not too-young, not good, not final-bad).
3. `validation.js:2289` — `onDone` of `checkInputDoubleSpend` — `if (err && is_private && !conf.bLight) throw Error("spend proof didn't help")`. Reachable only where the message-level `validateSpendProofs` (1640) did NOT reject first: private-elements chain flow (validateDivisiblePrivatePayment has no message-level uniqueness check), concurrent-validation race, or missing spend_proofs message. f8's refutation of the f1/f7/f13 claim holds for units carrying spend_proofs; the chain flow is the open question (round-1 P2).
4. `validation.js:2449` — `throw Error("spending a stable temp-bad output ...")` — fires BEFORE the clean rejection at 2466 (`stable input unit is not serial`) for stable temp-bad src outputs. Reachable if an attacker can make a unit temp-bad and spend its output.
All four: throw in an async completion callback → escapes → `network.js:4367` uncaughtException handler → re-throw → process death. The correct behavior for every one of these is the clean `cb(err)` rejection path that exists adjacent (1678 has no adjacent path; 2449's is at 2466).
**Orchestrator verdict: the crash family is real in code; per-site reachability is the round-1 P1/P2 empirical question.**

## V2 — P9 merkle vacuous satisfiability: CONFIRMED (direct test)
`merkle.verifyMerkleProof(X, deserializeMerkleProof("0-" + sha256(X).base64))` → **true** for arbitrary X (siblings=[], index=0 → loop never runs → `hash(element) === proof.root`, attacker-chosen). Control: different element → false; real 2-element-tree membership → true; non-member → false. The formula construct `is_valid_merkle_proof` (evaluation.js:1763-1810) hashes the raw element with the merkle-internal plain sha256 — the attacker can always satisfy it. Contrast `in merkle` (definition.js:1006-1031): root must equal a POSTED feed value → sound. **Verdict: engine-level footgun confirmed at function level; P9 builder's end-to-end formula test pending.**

## V3 — S1 disjunct audit (orchestrator grep, cross-checking f1/f4/f7/f11/f5)
- validation.js sites WITH disjunct (migration done): 996, 1030, 1194, 1813, 1896, 2735, 2784.
- validation.js sites WITHOUT (migration incomplete): 741 (non-AA parent gate), 1025-1028 (count_primary_aa_triggers>1 — f1-T2), 986-992 (outer v4 gate — f1-T3; `!last_ball_mci` skips ALL AA-trigger validation).
- formula/evaluation.js: `is_valid_signed_package` gates bare-mci (f5-T1) — max_complexity=0 below the gate.
- definition.js: all gates carry the disjunct (f4-H1).
**Verdict: the migration is incomplete in 3 validation sites + the formula eval side — A5/A6/f5-T1 are live S1 siblings.**

## V4 — tps-fee math (orchestrator direct computation, cross-checking f16-T1)
`getFinalTpsFee = round(base * (exp(tps) - 1))`, mainnet defaults base_tps_fee=10, tps_interval=1:
count=29 → fee ≈ 3.9e13 (3.9% of total supply); count=30 → 1.07e14 (10.7%); count=709 → Infinity.
The self-limiting question (spammer's own last unit must declare a fee they can afford) is P6's lab question.
