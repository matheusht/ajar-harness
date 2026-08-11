# pattern-candidates.md — local, unpromoted observations

Capture repeated *shapes* you notice during this engagement that might generalize into a Plane-1
`skills/patterns/` card. This file is **engagement-local and append-only** — it is NOT a promotion.
Promotion is manual and scrubbed: candidate here → operator-reviewed `record-memory` disposition →
sanitized `casebooks/<id>/` PR → pattern card update. A `promote` disposition proposes that later PR;
it never writes Plane-1. `defer` and `no_novel_lesson` are equally valid terminal outcomes.

Keep entries abstract enough to survive scrubbing later: describe the shape, not the secret. Link
evidence by id (`finding://`, `attempt://`), never paste transcripts or live values.

## Format per candidate
- **observed shape:** the repeated thing (one sentence — the structure, not the payload)
- **seen on:** surfaces / endpoints (abstract)
- **evidence:** `finding://...  attempt://...`
- **why it may generalize:** what makes this bigger than this target
- **why it may NOT:** the honest counter — target-specific quirk? already covered by a card?
- **candidate destination:** existing pattern card to extend, or a proposed new `pattern.<id>`
- **lesson kind:** `positive | negative | refutation | reward_hacked_proof | environment_failure | mixed`
- **held counterexample (if any):** where the SAME class was enforced correctly here (strengthens the card)
- **sanitization:** target identifiers, credential values, and harmful recipes removed; evidence IDs retained
- **promotion status:** `local` → `proposed` → `promoted` / `dropped`

## Entries
- (none yet)
## Candidates from round 0/1 (2026-08-11)

### PC-1 — uncaught-throw-on-attacker-input in consensus validation paths (crash family)
- **observed shape:** validation code paths that `throw Error(...)` on attacker-influenced input inside async completion callbacks (NOT inside async iterators) — the throw escapes as `uncaughtException`, the process-level handler (network.js:4367) re-throws, and the node dies. Found at validation.js:1662 (conflicting record from another address), :1678 (unreachable-code on temp-bad conflict), :2289 (spend proof didn't help, private full-node), :2449 (spending stable temp-bad output). In every case an adjacent clean `cb(err)` rejection exists or is the obvious intent.
- **seen on:** validation.js payment/doublespend paths; private payments (divisible_asset.js chain flow).
- **evidence:** attempt://obyte-r1-p1, attempt://obyte-r1-p2 (pending), round0 f1-T1/f7-C1/f13-T-A/f8-TRIPLE-1
- **why it may generalize:** any async/callback-heavy ledger or service that throws inside db-query callbacks on attacker input instead of routing to the error callback. The async-library throw-catching boundary (iterator vs completion callback) is the generalizable mechanism — most engineers believe async.series catches all throws; it does not.
- **why it may NOT:** Node process managers (pm2/systemd) restart nodes; the unit is usually rejected by OTHER nodes; single-node crash may be below the program floor.
- **candidate destination:** new pattern.consensus-crash-on-attacker-input (or field-notes first)
- **lesson kind:** positive
- **held counterexample:** f11 (forged AA unit) — 3 layers of clean rejection show the intended pattern; the crash sites are the exceptions.
- **sanitization:** no secrets; file:line + mechanism only
- **promotion status:** **deferred** (PC-1 + PC-4 merged — unreachable states today; hardening note)

### PC-2 — upgrade-gated rules keyed on position-height without the network-height disjunct (old-DAG rule gating)
- **observed shape:** consensus rules gated on `last_ball_mci >= constants.X` (the unit's position) where the fix pattern adds `|| (!hasBall && getMinRetrievableMci() >= X)` (the network's height). Rules missing the disjunct are bypassable by attaching a unit to an old DAG part. Found: validation.js:741 (non-AA parent), :1025-1028 (multi-trigger), :986-992 (outer AA-trigger gate), formula/evaluation.js:1652-1687 (signed-package budget, max_complexity=0). The migration is mid-flight — the team fixed the validation-side rules (277fad7/048fbdb) and is missing eval-side + 3 validation sites.
- **seen on:** validation.js, formula/evaluation.js, definition.js (migration complete there)
- **evidence:** round0 f1-T2/T3, f5-T1, f11 cross-flag; orchestrator grep audit (V3)
- **why it may generalize:** any DAG/chain with height-gated rule upgrades; the "enforce new rules for new units even if attached to old parts" concept applies to any append-only ledger with era-dependent validation.
- **why it may NOT:** requires old-DAG attachment to be possible + ball/stability mechanics; may be intended era-consistency in some sites.
- **candidate destination:** extend dag.old-dag-rule-gating (already authored this engagement)
- **lesson kind:** positive
- **held counterexample:** definition.js — migration complete (f4-H1); f11 — AA-trigger rules all carry the disjunct.
- **sanitization:** shapes only
- **promotion status:** **proposed → PROMOTED pending operator review** (card updated with the stabilization cap; conformance re-run clean)

### PC-3 — vacuously-satisfiable verification predicate in an engine (merkle)
- **observed shape:** an engine-level predicate that verifies a proof whose root is supplied by the prover and never bound to a committed/anchored value — self-consistency masquerading as membership. `is_valid_merkle_proof` (formula/evaluation.js:1763) vs the sound sibling `in merkle` (definition.js:1006-1031, root must equal a posted feed).
- **seen on:** formula language (AA engine)
- **evidence:** orchestrator direct test (V2); p9 pending
- **why it may generalize:** any verification API where the verifier trusts a root/commitment from the proof itself (Merkle, signature aggregators, range proofs); the fix pattern is binding the root to an on-chain/trusted anchor.
- **why it may NOT:** usage-dependent (which AAs call it); may be documented as a helper.
- **candidate destination:** new pattern.verification-root-not-anchored
- **lesson kind:** positive
- **promotion status:** **proposed → PROMOTED pending operator review** (card authored: skills/patterns/verification-root-not-anchored; conformance re-run clean)

### PC-4 — uncaught-throw-on-attacker-input in async completion callbacks (crash-pattern family)
- **observed shape:** `throw Error(...)` inside `conn.query`/async completion callbacks (outside
  async iterators) escapes to `uncaughtException` → process-level re-throw (network.js:4367-4379) →
  node death. Found at validation.js:1667/1686/2292/2451; all four currently unreachable from
  attacker input (address-binding 1557-1568; temp-bad state machine; flow ordering), but the
  mechanism is real and any future reachable site becomes a network-wide crash-loop.
- **seen on:** validation.js doublespend/spend-proof paths; private payment flows.
- **why it may generalize:** async-callback-heavy services; the async-library throw boundary
  (iterator vs completion callback) is the generalizable mechanism.
- **why it may NOT:** unreachable states today; node managers restart.
- **lesson kind:** negative (refutation) + hardening
- **promotion status:** **deferred** (merged into PC-1 — the uncaught-throw family is unreachable today; hardening note)

### PC-5 — bearer-token uniqueness keyed on a party-chosen string (F3 root)
- **observed shape:** a uniqueness check for a bearer secret keys the conflict match on a
  party-claimed string (the unit's author address) instead of the value the token commits to (the
  output owner) — the check is dodgeable by any party who can choose the key.
- **seen on:** private-payment spend-proof uniqueness (validation.js:1640-1642 vs inputs.js:73-80).
- **why it may generalize:** any bearer-token system (gift codes, payment proofs, capability
  tokens) where the uniqueness registry is keyed by a claimable identity.
- **why it may NOT:** the input-layer check partially compensates for public payloads.
- **lesson kind:** positive
- **promotion status:** **proposed → PROMOTED pending operator review** (card authored: skills/patterns/bearer-token-uniqueness-party-keyed; conformance re-run clean)

## Memory disposition — FINALIZED (E4-11, 2026-08-11; operator review + scrubbed PR required)

Per Decision 0005 §11: a disposition is a requirement to decide, not a requirement to promote.
Full rationale + evidence in `evidence/roundE4/E4-11.md`.

| candidate | disposition | destination | recorded cap |
|---|---|---|---|
| PC-1 uncaught-throw pattern | DEFER (merge PC-4) | field-notes | all 4 sites unreachable (address-binding; temp-bad state machine; flow ordering; reorg corner closed) |
| PC-2 old-DAG rule gating | PROMOTE | extend pattern.dag-old-dag-rule-gating | old-DAG units cannot stabilize → skips affect junk only; the audit method is the durable value |
| PC-3 verification-root-not-anchored | PROMOTE | new pattern.dag.verification-root-not-anchored | confirmed F1; usage-cap (which AAs use the construct not enumerable) |
| PC-4 crash-pattern family | DEFER (merge PC-1) | field-notes | same reachability argument |
| PC-5 bearer-token uniqueness party-keyed | PROMOTE | extend pattern.dag-spend-proof-uniqueness | confirmed F3; impact-cap (no direct theft; merchant exposure triple-contingent) |

**Field-notes lessons (5)** + **casebook PROMOTE recommendation** in `evidence/roundE4/E4-11.md`.
Engagement disposition: **promote**.
