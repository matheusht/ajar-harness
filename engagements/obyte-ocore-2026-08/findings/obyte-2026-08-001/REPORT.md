# obyte-2026-08-001 — Formula `is_valid_merkle_proof` is vacuously satisfiable (engine-level footgun)

**Status:** unproven (no status field — promotion requires the six gates).
**Pinned target:** `github.com/byteball/ocore` @ `a7eb776afc68ed4bed05ba554f7f1e95f5d49b44`

## Summary (one sentence)

The AA formula engine ships a verification predicate (`is_valid_merkle_proof`) whose proof root is
supplied by the prover and never bound to a committed tree, so the predicate returns true for any
element — it proves self-consistency, not membership — and any AA using it as a membership or
authorization gate is bypassable.

## Affected surface

- `formula/evaluation.js:1763-1810` — `case 'is_valid_merkle_proof'` (proof cap 1024 at :1781;
  sibling checks at :1787-1791 are bare-`mci` gated — S1 family)
- `merkle.js:84-101` — `verifyMerkleProof`: with `index=0, siblings=[]` the check reduces to
  `hash(element) === proof.root` (attacker-chosen)
- `merkle.js:75-78` — `deserializeMerkleProof` splits on `-`; `"0-" + b64(hash(X))` yields
  `{index: "0", siblings: [], root: hash(X)}`
- Contrast (sound): `definition.js:1004-1031` — `in merkle` binds `proof.root` to an on-chain
  posted data-feed value (`dataFeeds.dataFeedExists(..., '=', proof.root, ...)`)
- In-scope surface: AA engine (SF-9/SF-10); individual AA logic out of scope

## Claim tuple

- **target/version:** ocore `a7eb776`, formula engine
- **entrypoint:** any AA formula (init/response/condition/getter) calling `is_valid_merkle_proof(element, proof)`
- **preconditions:** AA uses the construct without separately pinning `proof.root`
- **mechanism:** root from the proof itself; `proof = "0-" + base64(sha256(element))` always verifies
- **observable effect:** predicate true for arbitrary X with no tree membership (measured 4/4)
- **negative control:** wrong root → false; the sound sibling `in merkle` rejects the same proof
  without a posted feed (measured)
- **claimed impact/severity:** engine footgun — membership/whitelist/authz gates in AAs are
  bypassable; usage-capped Medium.

**CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:L/A:N** = 5.3

## Reproduction (maximum-impact PoC + independent run — standing gate)

PoC: `evidence/p9-poc.js` (real formula engine, real definition predicate engine, real
dataFeedExists SQL against a scratch sqlite, real secp256k1).

```
cd /Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore
node lab-obyte.js <abs>/evidence/lab/p9/p9-poc.js
```

Raw results (builder `evidence/p9-builder.md` + independent reviewer `evidence/IR-F1-review.md`):

| test | result |
|---|---|
| vacuous X="not-in-any-tree-1" / "hello world" / random / "user-supplied element 42" | true ×4 (both runs) |
| positive control: real 5-element tree proof | true |
| negative control: wrong root | false |
| 60-sibling proof, mci=15,000,000 (≥ pemCurvesFixMci) | false (cap active) |
| 60-sibling proof, mci=1,000,000 | true (cap bare-mci gated — S1 family) |
| `in merkle` with the same vacuous proof, no posted feed | false (real dataFeedExists: 0 records) |

Independent reviewer (IR-F1, fresh context) executed the unmodified PoC, read raw output, and
cross-constructed proofs on the real engine; verdict **confirmed**, no reward-hacking.

## Impact analysis (marginal contribution)

- The world without this bug: `is_valid_merkle_proof` would either bind the root to an anchor (like
  `in merkle`) or not exist — AAs would use the sound primitive.
- The delta this bug adds: any AA whose logic trusts the construct for membership (whitelists,
  proof-of-publication, authorization predicates) can be bypassed with a self-consistent proof —
  the AA's protected behavior is reached without the intended membership condition.
- **Cap:** which AAs use the construct is not enumerable from ocore (AA repos out of scope);
  severity is usage-capped at Medium. The engine defect itself is confirmed.

## Negative control

Wrong-root proof → false (the predicate is not always-true; it checks self-consistency only).
The sound `in merkle` construct rejects the identical vacuous proof without an on-chain feed.

## Remediation note

Bind the root to a committed/anchored value (e.g., require a posted data feed like `in merkle`
does), or remove `is_valid_merkle_proof` from the formula language unless a root-binding parameter
is provided. Add the `!hasBall && getMinRetrievableMci()` disjunct to the eval-side sibling checks
(e01ba3e migration — see the S1 family note).

## Evidence refs

- `evidence/p9-builder.md` — builder report (real-path confirmation)
- `evidence/IR-F1-review.md` — independent fresh-context run + source verification + reward-hack audit
- `evidence/p9-poc.js`, `evidence/p9-README.md` — runnable PoC
- `attempts.jsonl` — round-1/round-2 attempt records
