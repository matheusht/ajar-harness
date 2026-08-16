# Round 0 briefs — obyte-ocore-2026-08 (blind portfolio, 16 families)

Launched 2026-08-11. One independent hunter per family, **no crown-jewel prior revealed beyond the
shared recon-signals.md seed**. Each hunter returns source→sink→path triples with `file:line`,
concrete input constructions, negative controls, and honest verdicts. Keep-biased on candidates,
honest on controls. Reports land in `evidence/round0/<key>.md`.

| key | family | primary files | focus |
|---|---|---|---|
| f1 | DAG validation & unit acceptance | validation.js, joint_storage.js | structural checks, parent selection, size limits, skip-able checks (S1), fail-open |
| f2 | Main-chain selection & stability | main_chain.js, witness_proof.js | best-parent algo, tie-breakers, stability advancement, witnessing rules, lock races |
| f3 | Signature & authentifier verification | signature.js, definition.js (sig parts), object_hash.js | ECDSA malleability, pubkey parsing, authentifier edge cases, hash verification |
| f4 | Definition language / smart addresses | definition.js | sig/hash/cosigned/in-data-feed/has, nested booleans, definition-change path, threshold edges, depth |
| f5 | Formula / oscript evaluation | formula/ (evaluation.js, validation.js, grammars) | numeric handling (S5), state r/w, bounce, response chains, recursion/depth limits (S3), limits-on-all-paths |
| f6 | Divisible assets | divisible_asset.js | private divisible path (V-001 site), SQL interpolation (S2), spend proofs (S8), amount math (S12) |
| f7 | Indivisible assets | indivisible_asset.js | caps, issue/transfer conditions, auto-destroy, transferability, attestations, counts |
| f8 | Private payments & spend proofs | private_payment.js + related | proof structure, uniqueness (S8), output binding, full-vs-light asymmetry, replay |
| f9 | Network protocol | network.js | message parsing, gossip, request handling, unsigned joints (S11), sizes, DoS, hub/peer desync |
| f10 | Storage, catchup, proof chains | storage.js, catchup.js, merkle.js, proof_chain.js, archiving.js | hash-tree proofs, catchup validation, merkle siblings (S9), joints-with-balls (S11), write atomicity |
| f11 | AA engine (in ocore) | aa_validation.js, aa_composer.js | trigger validation (S7), getters at definition MCI, response chains, AA state atomicity, asset pre-validation |
| f12 | Encoding & hashing | object_hash.js, string_utils.js, validation_utils.js, object_length.js | canonicalization (S5), sort comparators, base64/base32, unicode, key order |
| f13 | Races & TOCTOU | mutex.js, joint_storage.js, main_chain.js, network.js | validate-then-write gaps, lock acquisition, double-processing, concurrent unit handling |
| f14 | Fail-open error handling | cross-cutting (validation/network/storage) | try/catch → valid, callback(err) handling, swallowed errors, partial writes on error |
| f15 | Composer & signing | composer.js, parent_composer.js, wallet_defined_by_keys.js, signed_message.js | signing unvalidated units (S10), parent selection, multisig order, nonce handling |
| f16 | Economics & misc | headers_commission.js, paid_witnessing.js, data_feeds.js, arbiter_contract.js, balances.js | fee/commission math (S12), paid witnessing replay, data feed handling, balance updates |

Each brief also pins: scope rules (Primacy of Rules; PoC required per severity; DoS coordination
question; min USD 1,000), the hard wall (local only), the record discipline (attempt fields), and
the output contract.

## Family-specific briefs (delivered verbatim to each hunter)

### f1 — DAG validation & unit acceptance
Read `validation.js` (~126KB) and `joint_storage.js`. Map the full unit/joint acceptance path:
structural checks (required fields, types, lengths), parent validation (exists, valid, no
self-reference, no duplicates, no cycles), size limits, unit hash recomputation, signature presence
per message, and error handling. Questions: (1) which checks are gated on position/height
(`last_ball_mci`, `hasBall`) and can be skipped by attaching a unit to an old DAG part (shape S1 in
recon-signals)? (2) which fields are trusted from the unit without independent validation? (3) on
validation failure, is the unit ever stored/forwarded anyway (fail-open)? (4) are the checks applied
in the same order on every path (handleJoint vs post_joint vs catchup)?

### f2 — Main-chain selection & stability
Read `main_chain.js` (~79KB) and `witness_proof.js`. Map MC selection: best-parent algorithm,
tie-breaker rules (OP preference, genesis-parent), stability point advancement (stability-by-1-MCI,
"move stability point by 1"), witnessed level computation, witness list mutation, mutation distance
rule, and the lock/async structure (recent fixes: "recheck stability after acquiring the lock",
"check bKeepStabilityPoint earlier"). Questions: (1) any path where MC advances with an incorrect
witness count or where stability races with unit arrival? (2) tie-breaker nondeterminism that could
split honest nodes? (3) "push back upgrade MCIs" — what does it do and can it be abused? (4) does
stability affect validation gating (S1 interplay)?

### f3 — Signature & authentifier verification
Read `signature.js` (~12KB), the authentifier parts of `definition.js`, and `object_hash.js`.
Map: ECDSA secp256k1 verification (which lib, malleability handling, low-S enforcement?), pubkey
parsing (compressed/uncompressed/point validation), address derivation, hash verification (unit
hash, message hash), and the authentifier signature-list path (empty list, duplicate sigs, wrong
count). Questions: (1) signature malleability accepted? (2) pubkey recovery confusion (y-parity,
R/S bounds)? (3) is any signature *trusted* rather than verified? (4) definition-change
authorization — can an attacker change a definition without the old definition's consent?

### f4 — Definition language / smart addresses
Read `definition.js` (~57KB). Map the smart-address predicate language: `sig`, `hash`, `cosigned
by`, `in data feed`, `has`, nested boolean structure, the definition-change path, definition
validation (depth limits — recent fix 048fbdb), composition. Questions: (1) predicate evaluation
errors → fail-open (a malformed predicate treated as satisfied)? (2) threshold edge cases
(0-of-N, N-of-0, threshold > N, duplicate cosigners)? (3) definition-change without proper
authorization? (4) old-vs-new definition depth limits (S1)? (5) can a definition be crafted that
evaluates differently on different nodes (S5)?

### f5 — Formula / oscript evaluation
Read `formula/` (evaluation.js ~3200 lines, validation.js, grammars oscript.ne/ojson.ne, and the
compiled grammars). Map: numeric handling (Decimal vs Number, -0, NaN, Inf, exponent forms),
string handling, state variable read/write, bounce conditions, response chains, recursion/depth
limits (expression count, array/dict caps, search-param caps), getters, error paths. Questions:
(1) where can evaluation produce non-canonical results (S5 — -0, key order, exponent)? (2) are the
limits applied on ALL paths (old-DAG attachment S1, getters, triggers)? (3) error paths that leave
state partially written or swallow errors (S7 — "preserve error object" fix)? (4) unbounded loops /
recursion / memory in evaluation? (5) formula result divergence across nodes?

### f6 — Divisible assets
Read `divisible_asset.js` (~19KB). Map: divisible asset transfers, private divisible assets, the
`validateAndSaveDivisiblePrivatePayment` path (V-001 SQL-injection site — fixed by escaping
message/output indices), input/output handling, spend proofs, amount math. Questions: (1) SIBLING
SQL interpolations — grep for raw `+` concatenation inside SQL strings in this file and its callers
(S2); (2) spend-proof uniqueness on this path (S8); (3) index/amount validation gaps (negative,
huge, non-integer); (4) amount arithmetic on JS Number (S12)? (5) multiple private divisible assets
in one payment (recent feature dd29823) — fresh surface?

### f7 — Indivisible assets
Read `indivisible_asset.js` (~47KB). Map: asset definitions (cap, issued_by_definer_only,
auto_destroy, is_transferrable, transfer/issue conditions), attestations, asset metadata,
issuance path. Questions: (1) cap enforcement — can issuance exceed cap? can cap be changed after
issuance? (2) transfer conditions bypass (definition-change, condition evaluation fail-open)? (3)
auto-destroy / transferability logic errors? (4) count/amount arithmetic (S12)? (5) private-asset
conditions rule (noPrivateAssetsWithConditionsUpgradeMci — S1 gating)?

### f8 — Private payments & spend proofs
Read `private_payment.js` (~4KB) plus the private-payment paths in `divisible_asset.js`, `wallet.js`,
and `validation.js`. Map: spend proof structure, proof validity, uniqueness (S8 — the 2025 fix
"uniqueness of spend proof is not verified in light" gated an error on `!conf.bLight` — hunt
siblings), output binding (output_hash — 9f91195), light-vs-full asymmetry, replay. Questions:
(1) is uniqueness enforced on every path that credits? (2) is the proof bound to the exact output
(unit+message_index+output_index)? (3) any path treating unstable inputs (is_unique=null) as
checked? (4) multiple private assets — uniqueness per tuple?

### f9 — Network protocol
Read `network.js` (~163KB). Map: peer protocol (hub/peer, websocket), message types (post_joint,
getdata, joint retrieval, subscription, witness/OP announcements), request handling, gossip,
peer banning, backpressure. Questions: (1) message-type confusion / missing field validation /
unbounded sizes? (2) "unsigned" joints refused (60850f6) — are there sibling message types lacking
the same check (S11)? (3) DoS: can a peer force unbounded work (recursive structures, huge payloads,
endless retries)? (4) hub/peer desync: does the node accept from a peer what it would reject
locally (validation asymmetry)? (5) can a crafted message crash a node (crash-on-valid = in-scope
only if network-wide; record which)?

### f10 — Storage, catchup, proof chains
Read `storage.js` (~100KB), `catchup.js` (~20KB), `merkle.js`, `proof_chain.js`, `archiving.js`.
Map: joint storage, hash-tree proofs, catchup chain validation, reorg handling, archiving, the
"only joints with balls while catching up" (a7eb776) and "no ball via post_joint" (615e258) paths,
merkle proof siblings (e01ba3e). Questions: (1) proof validation gaps (accept a false proof)? (2)
catchup desync: node accepts during catchup what it would reject at full sync (S11 siblings)? (3)
partial writes on error / missing rollback? (4) storage of invalid joints (write-then-validate)? (5)
merkle proof edge cases (empty tree, single-leaf, sibling order)?

### f11 — AA engine (in ocore)
Read `aa_validation.js` (~30KB) and `aa_composer.js` (~78KB). Map: AA trigger validation
(validateAATrigger, validateAATriggerObject), getters (determineGetterProps at definition MCI —
41f5cc0), max_aa_responses, response chains, bounce conditions, AA state handling, formula-in-AA,
asset pre-validation (16ddd6a). Questions: (1) trigger object validation completeness — the
"no early success if no non-base assets" fix (c368211) suggests early-success paths; find siblings
(S7)? (2) getters run at the wrong MCI or with wrong state? (3) response chain depth / recursion? (4)
AA state write atomicity (partial state on error)? (5) asset validation gaps in composer?

### f12 — Encoding & hashing
Read `object_hash.js`, `string_utils.js`, `validation_utils.js`, `object_length.js`, `chash.js`.
Map: canonical serialization for hashing (sortObject — does it descend into arrays? key order?),
-0/NaN/exponent handling, base64/base32 encoding, unicode in text messages, JSON parsing of units,
length/weight computation. Questions: (1) canonicalization divergence (S5) — the same logical value
serialized two ways → different hash (consensus split)? (2) sort comparators that are not
type-stable (S4)? (3) `JSON.stringify` used as hash input anywhere without a total canonicalizer? (4)
exponent/decimal forms in hashed values? (5) unicode edge cases in text (overlong, surrogates)?

### f13 — Races & TOCTOU
Read `mutex.js`, `joint_storage.js`, storage write paths, `main_chain.js` locking, `network.js`
concurrency. Map: validate-then-act gaps (validation reads state, then a later write acts on
different state), lock acquisition/release (recent fix: "lock handleJoint while initializing"),
double-processing of the same unit, concurrent unit handling (same unit via network + local),
stability recheck after lock (2afd965). Questions: (1) any check-then-act where the checked state
can change before the act? (2) any path where a unit is processed twice (idempotency)? (3) lock
ordering deadlocks or missing locks on shared state? (4) races between MC update and unit
validation?

### f14 — Fail-open error handling
Cross-cutting grep: in validation/network/storage, find `try { ... } catch` blocks that return
success/valid, `callback(null)` on error, swallowed errors, empty catches, and validation functions
that catch and continue. Recent anchor: "preserve error object in executeGetter()" (f9fd994) —
error objects were being lost somewhere; find siblings. Questions: (1) any caught exception that
results in "valid" or in continuing processing? (2) any validation function that returns success by
default and only fails on explicit error? (3) partial writes before the error is handled? (4) error
messages that leak internal state (info disclosure)? Every candidate needs the exact file:line of
both the catch and the return.

### f15 — Composer & signing
Read `composer.js` (~39KB), `parent_composer.js` (~29KB), `wallet_defined_by_keys.js` (~35KB),
`signed_message.js`. Map: unit composition (messages, payments, definitions), parent selection,
signing (which authentifiers, input/output checks — f5d8552 "check inputs and outputs of units to
be signed"; multisig order — d724068), nonce handling, private payments in composer. Questions:
(1) can the composer sign a unit with unvalidated inputs/outputs (S10 siblings)? (2) parent
selection bugs (choosing parents that make the unit invalid)? (3) nonce/sequential-number handling?
(4) any path where the composed unit differs from what was validated?

### f16 — Economics & misc
Read `headers_commission.js`, `paid_witnessing.js`, `data_feeds.js`, `arbiter_contract.js`,
`prosaic_contract.js`, `balances.js`, `mc_outputs.js`, `my_witnesses.js`, `initial_votes.js`.
Map: headers commission math (shares, sorting — S4), paid witnessing (replay?), data feed handling,
arbiter contracts, balance updates, witness selection. Questions: (1) fee/commission arithmetic on
JS Number (S12) — precision/rounding? (2) paid witnessing: can a payment be replayed or counted
twice? (3) data feed: can a feed value be used before validation? (4) balance update atomicity? (5)
headers commission recipient list handling (S4 — the sort-order fix)?

## Post-round-0 (orchestrator)
Adjudicate every triple (signal → adjudication), log attempts, allocate round 1 (directed +
adversarial), refute survivors, compose primitives, then escalate + chainability on confirmeds.
