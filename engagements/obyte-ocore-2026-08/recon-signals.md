# recon-signals.md — obyte-ocore-2026-08

Pinned: `a7eb776afc68ed4bed05ba554f7f1e95f5d49b44` (2026-08-10). Local clone:
`/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore`.

One row per observation. A `negative` signal — a control that looks correctly enforced — is recorded
as likely-held and a positive-control candidate, never as a finding.

## History-sweep shapes (one-time sweep, 2026-08-11 — SHAPES, never diffs)

A fixed bug marks a family. Recorded abstract shapes from the public commit history (verified against
the local clone). Hunting rules: never report a fix as a find; a candidate that maps to a swept shape
must be checked against the actual fix first (if the fix covers it → `covered-dry`); the sweep seeds
routing, it does not steer the loop.

| Shape (abstract) | Fixed-in commit (family anchor) | Family to hunt | Why siblings may exist |
|---|---|---|---|
| S1: upgrade rules gated on `last_ball_mci >= constants.X` **without** the `!hasBall && getMinRetrievableMci() >= X` disjunct → bypass by attaching a unit to an old part of the DAG / no-ball unit | `277fad7`, `048fbdb`, `c368211` (added the disjunct) | F1 validation gating | The team is mid-migration adding this disjunct rule-by-rule; any rule they missed is a live bypass. GREP: `last_ball_mci >= constants.` without `getMinRetrievableMci` nearby. |
| S2: unescaped SQL interpolation of message/output indices in validation queries | `991c5d6` V-001 (`divisible_asset.js` `validateAndSaveDivisiblePrivatePayment`) | F7/F8 asset + private payment SQL | Codebase builds raw SQL with `+conn.escape(...)` and `+"...` mixed; siblings likely. GREP: `+"` in `addQuery`/`conn.query` strings across asset/private-payment/storage paths. |
| S3: unbounded structured-payload depth/size — formulas, definitions, oscript/ojson, objects | `6fe2938`, `048fbdb`, `eb63aaf`, `aea941a`, `885686d`, `fd52b0c` | F6 formula, F5 definitions, F12 encoding | Caps were added incrementally per-payload-type; enumerate every user-controlled structured payload and check it has a cap (network messages, catchup, private payments, AA trigger objects, wallet data). |
| S4: type confusion before sort/compare/hash — non-string values in ordering comparisons, charset checks | `e56fa5c`, `f3b253e`, `60850f6` | F12 encoding, F4 signature, F1 validation | `<=` comparisons and hashing assume strings; malformed types could throw mid-validation (fail-open?) or diverge. Check validation ORDER (isValidAddress before compare). |
| S5: canonicalization divergence — `-0` vs `0`, `lodash.isEqual` replacement, `sortObject` array descent, `expunge -0` | `22d8fb1`, `9dc4fc5` | F12 hashing, F6 formula | Canonicalization inconsistency ⇒ different nodes hash/compare differently ⇒ consensus split potential. Check every place a value is serialized for hashing (object_hash, sortObject, formula result). |
| S6: stability-point / main-chain advancement races and logic errors | `2afd965`, `f503efc`, `07c25ba`, `47da02e`, `bdac590`, `6d124d0` | F2 main-chain/stability | MC stability logic under heavy recent rework (best-parent algo, tie-breakers, stability-by-1-MCI); fresh code = fresh bugs. |
| S7: AA trigger/getter validation gaps — early-success returns, getter at wrong MCI, error swallowed | `c368211`, `41f5cc0`, `f9fd994`, `16ddd6a` | F11 AA engine | validateAATriggerObject had "no early success if no non-base assets"; getters must run at definition MCI. Check trigger object validation completeness + getter error handling. |
| S8: private-payment spend-proof uniqueness / output-hash checks | `05f291d8` (2025-02, light client), `9f91195`, `dd29823` | F8 private payments | Spend-proof uniqueness was once NOT verified (light path); output_hash check added to sign requests. Check full-node path + multiple-asset private payments. |
| S9: merkle proof sibling validation in catchup/proof chains | `e01ba3e` | F10 catchup/proofs | Proof-chain validation gaps → false proofs accepted. Check catchup.js + merkle.js proof paths. |
| S10: signing-path validation — inputs/outputs checked before signing, multisig order | `f5d8552`, `d724068` | F4 signature | Units to be signed must have validated inputs/outputs; signing-order determinism. |
| S11: catchup/network hardening — only joints with balls, no ball via post_joint, refuse unsigned | `a7eb776`, `615e258`, `60850f6`, `6ea4640` | F9 network, F10 catchup | Catchup path recently hardened; check for sibling message types still lacking the new checks. |
| S12: depth limits apply to "new units even if attached to old DAG part" — old-vs-new rule asymmetry | `682e136`, `277fad7`, `048fbdb` | F1, F5 | Same family as S1; the old-DAG attachment attack is the recurring bypass mechanism. |

## Activation signals (recon → routing)

| # | Observation (file:line) | Cards it lights up | strong / weak / negative | Note |
|---|---|---|---|---|
| A1 | Upgrade-gated validation rules in `validation.js` use `last_ball_mci >= constants.X` gating; disjunct being added per-rule | dag.old-dag-rule-gating | **strong** | S1 — highest-value sibling hunt; a missed rule = old-DAG bypass |
| A2 | Raw SQL string building with unescaped index interpolation in `divisible_asset.js` private-payment path | dag.sql-interpolation | **strong** | S2 — V-001 was this shape, fixed 7 days ago |
| A3 | User-controlled structured payloads: definitions, formulas (oscript/ojson), AA trigger objects, network messages, catchup data | dag.depth-size-limits | strong | S3 — caps added incrementally; enumerate remaining uncapped |
| A4 | `object_hash.js`/`string_utils.js` canonicalization (sortObject, -0 expunge, isEqual removal) | dag.canonicalization-split | strong | S5 — consensus-split potential if divergent |
| A5 | Type-order in validations: charset/address checks added before `<=` comparisons | dag.type-confusion | weak→strong | S4 — validation ORDER matters; find remaining unguarded comparisons |
| A6 | Stability/MC advancement reworked in last 3 weeks (best-parent, tie-breakers, stability-by-1) | dag.main-chain-stability | strong | S6 — fresh code, consensus-critical |
| A7 | AA trigger validation "no early success" + getter-at-definition-MCI + error-object preservation | dag.aa-trigger-getter | strong | S7 |
| A8 | Spend-proof uniqueness + output_hash checks in private payment sign path | dag.spend-proof-uniqueness | strong | S8 |
| A9 | Catchup "only joints with balls" + "no ball via post_joint" + length checks on parent units | dag.catchup-network | strong | S11 |
| A10 | merkle proof sibling check added | dag.proof-chain | weak | S9 |
| A11 | test suite 957 passed on pinned commit; test runner crash is environmental (ava/Node25) | — | negative | environment quirk, not a finding |
| A12 | no prior obyte/byteball/ocore work in this harness repo (freshness verified) | — | negative | no contamination source |

## Baseline controls — what the node refuses with no attack

Recorded statically (validation.js paths); will be confirmed live in the lab (TODO: multi-node lab
bring-up, then record actual observed refusals).

| Control | Behaviour observed | Where enforced |
|---|---|---|
| C1 | Invalid address checksum refused | `validation.js` isValidAddress (also `f3b253e` charset) |
| C2 | Unsorted recipient/attestor lists refused | `validation.js` validateHeadersCommissionRecipients / checkAttestorList |
| C3 | Formula depth > 100 refused; expression-count and array/dict caps | `formula/validation.js` (048fbdb, aea941a, 885686d) |
| C4 | "unsigned" joints refused over network | `network.js` (60850f6) |
| C5 | `max_aa_responses=0` refused post-`pemCurvesFixMci` | `validation.js` validateAATrigger |
| C6 | Merkle proof siblings validated | `catchup.js`/`merkle.js` (e01ba3e) |
| C7 | Private assets may not carry issue/transfer conditions | `validation.js` validateAssetDefinition |
| C8 | Units to be signed have inputs/outputs checked | `wallet_defined_by_keys.js` signing path (f5d8552) |

## The two ladder questions — PROOF STRATEGIES (not feasibility verdicts)

**Q-A — What would an unrecoverable total shutdown of the entire Obyte network require?**
Sub-conditions (each is a lane):
1. **Permanent consensus split:** different honest nodes permanently accept different chains such
   that no valid unit can extend both — from a validation rule evaluated inconsistently (S5
   canonicalization, S4 type confusion, nondeterministic evaluation), or an old-DAG rule asymmetry
   (S1) that makes node A accept a unit node B rejects. Proof: two-node local lab, feed the
   adversarial input, show MC/stability divergence that persists across restarts and cannot be
   resolved by any single node's unilateral action (requires network coordination to heal).
2. **Stability-point stall:** all order-provider waypoints stop advancing because a rule prevents
   any unit from becoming stable (e.g., MC selection never advances stability — S6). Proof:
   synthetic OPs in the lab, show stability point frozen while valid units exist; recovery requires
   coordinated intervention (new ruleset/upgrade).
3. **Chain-halting valid unit:** a unit that is valid-but-unprocessable crashes every honest node
   deterministically (exception in a path that isn't caught — S12/S4), so no node can advance past
   it; recovery requires a coordinated node upgrade = in scope. Proof: craft the unit, show all
   nodes crash-loop on it, show no unilateral fix.
Each lane stays OPEN until the bounded space (all rule-gating sites, all canonicalization sites,
all stability code paths) is enumerated and adjudicated. A written strategy with no path yet keeps
the lane open.

**Q-B — What would executing a transaction from another user's account, without their private key,
require?**
Sub-conditions:
1. **Signature verification bypass:** a unit passes authentifier verification without the key —
   malleable signature, curve edge case, pubkey parsing confusion, definition predicate satisfied
   without the key (S4, S10). Proof: generate victim keypair locally, craft a unit that spends the
   victim's output with a forged/absent authentifier, show the node accepts it and transfers value.
2. **Definition-language bypass:** a smart-address definition (multisig threshold, `cosigned by`,
   `has`, `in data feed`, nested boolean) evaluates satisfied for an attacker-controlled witness set
   (F5). Proof: construct a definition whose predicate passes without the required key material.
3. **Spend-proof forgery / private payment:** a private-payment spend proof accepted without the
   recipient's secret (S8 uniqueness/output-hash gaps). Proof: forge a spend proof for a locally
   generated private asset, show the node credits it.
4. **Validation omission:** an output spend that skips a check other nodes perform (old-DAG
   attachment, S1) — node A credits a double-spend that node B rejects. Proof: two-node lab, show
   divergent acceptance + the affected balance.
Same rule: each lane stays open until enumerated + adjudicated.

## The DoS coordination question

Out of scope: temporary disruption a fix resolves **without** network coordination.
In scope: disruption whose resolution **requires** network coordination (temporary freezing of
network transactions).

| Availability candidate | Resolvable without coordination? | Therefore |
|---|---|---|
| Single-node crash from a malformed message only that node accepts (bad config, non-shared state) | yes — operator fixes node | **out of scope** |
| Crash-on-valid-unit that hits every honest node deterministically (the unit is valid and propagated) | no — requires coordinated rejection/upgrade | **in scope** (temporary freezing of transactions) |
| Stability/MC stall from a crafted unit that all nodes accept as valid but that prevents advancement | no — coordinated ruleset change needed | **in scope** |
| Resource exhaustion from a huge unit that only the receiving node processes (size cap exists elsewhere) | yes if a node-side cap fixes it | **out of scope** (verify the cap exists on ALL paths) |
| Catchup/network DoS that requires peers to coordinate on rejecting a peer | varies — decide per candidate with the fix's shape | **decide per candidate** |

Settling rule: for every availability candidate, first answer "what is the fix?" — if a single node
can fix itself (ignore the message, cap the size, crash-recover), it's out; if the whole network
must agree to reject or upgrade, it's in.

## Ladder-question final verdicts (2026-08-11, after rounds 0-2)

**Q-A — unrecoverable total network shutdown: COVERED-DRY (bounded + enumerated).**
Sub-conditions and dispositions:
1. *Permanent consensus split* — ENUMERATED + CLOSED. Canonicalization (f12 N3/N4: serializers
   total + deterministic, -0 handled), definition language (f4 H1-H6: spend-time revalidation),
   signature paths (f3: malleability refuted, pubkey fail-closed), SQL backend divergence
   (p4: empirically refuted on 4 engines; conf.js marks mysql unsupported), validation ordering
   (f1 H2/H3: all paths converge on the same pipeline; fail-closed). No rule evaluated
   inconsistently across honest nodes was found.
2. *Stability-point stall* — ENUMERATED + CLOSED. Main-chain selection is deterministic
   (f2: tie-breakers stable, OP-preference verified); the alt-branch stall (f2-T-f2-03) was held
   weak (WL-increasing constraint bounds it); stability advancement is 1-MCI-at-a-time and
   resolution is atomic with ball creation (r1 state machine). No attacker-reachable freeze found.
3. *Chain-halting valid unit* — ENUMERATED + CLOSED. Crash family (4 sites) refuted as
   attacker-reachable (address-binding, state machine, flow ordering). Network layer: no
   crash-on-crafted-message (f9 H4). No valid-unit crash found.
Verdict: covered-dry with the proof strategies written and sub-conditions enumerated; no path to
the $50k shutdown condition.

**Q-B — spend from another user's account without their key: COVERED-DRY (bounded + enumerated).**
Sub-conditions and dispositions:
1. *Signature verification bypass* — ENUMERATED + CLOSED. secp256k1 high-S rejected (f3 T1
   tested), pubkey parsing fail-closed (T2 tested), unsigned joints refused on all 3 delivery
   paths (T4/H3), authentifier paths require consumed signatures (f4 H6/H7).
2. *Definition-language bypass* — ENUMERATED + CLOSED. All predicate gates carry the S1 disjunct
   (f4 H1); malformed-mci definitions refuted by spend-time revalidation (f4 T1); thresholds and
   nesting bounded (f4 T2/T3, T8).
3. *Spend-proof forgery* — ENUMERATED + CLOSED for forgery (proof binds output fields +
   blinding; no blinding → cannot compute P — f6 H3/H4). **BUT the uniqueness dodge (F3) is real**:
   the SENDER (who retains P) can place a second 'good' unit — that is not forgery (the sender
   legitimately holds P); it is a protection-defeat (Low-Medium, F3).
4. *Validation omission* — ENUMERATED + CLOSED. Old-DAG attachment cannot stabilize (KP-F2-link);
   validation gates are position-consistent for all units that matter.
Verdict: covered-dry for the $50k spend-without-key condition (no signature/definition/forgery
bypass); the F3 protection-defeat is a Low-Medium finding, not key-free spend.

**DoS coordination question — settled per candidate:** every availability candidate found
(crash family, unbounded streaming f9-T1, unhandled-joints flood f9-T4, paid-witness walk f16-T4,
signed-package amplification F2) resolves with a node-side fix → OUT of scope per the program rule;
none requires network coordination. F2's valid-unit amplification would have been in-scope had the
stabilization link held — it does not.
