# P9 — formula `is_valid_merkle_proof` is vacuously satisfiable (engine-level footgun)

**Status: CONFIRMED_SIGNAL** (real-path evaluation on pinned `a7eb776afc68ed4bed05ba554f7f1e95f5d49b44`)

## Claim tuple

- **target/version:** ocore `a7eb776afc68ed4bed05ba554f7f1e95f5d49b44`, `formula/evaluation.js` `is_valid_merkle_proof` case (lines ~1763-1810), `merkle.js` `verifyMerkleProof` (84-101).
- **entrypoint:** any AA formula (init/response/condition/getter) that calls `is_valid_merkle_proof(element, proof)`.
- **precondition:** the AA author uses the construct without separately pinning `proof.root` to a committed on-chain value.
- **mechanism:** `verifyMerkleProof(element, proof)` computes `hash(element)` folded with the attacker-supplied sibling list and compares against `proof.root` — the root comes from the attacker-supplied proof itself, never from a committed tree. With `index=0`, `siblings=[]`, the check reduces to `hash(element) === proof.root`, which the caller can always arrange (`proof = "0-" + base64(sha256(element))`). The proof "proves" only self-consistency.
- **observable effect:** `is_valid_merkle_proof(X, "0-" + hash(X))` evaluates to `true` for ANY X with no tree membership whatsoever (measured: 4/4 arbitrary elements).
- **negative control:** (a) wrong root → `false` (the construct is not always-true; it checks self-consistency only); (b) the definition-language sibling `['in merkle', ...]` (definition.js:1006-1031) requires the root to equal an on-chain posted data-feed value (`dataFeeds.dataFeedExists(..., '=', proof.root, ...)`) — the same vacuous proof returns `false` there without a posted feed (measured).
- **claimed impact/severity:** engine-level footgun. Any AA whose logic trusts `is_valid_merkle_proof` for membership (e.g., whitelist gates, proof-of-publication checks, authorization predicates) is bypassable by constructing a self-consistent proof. Conditional on AA usage (in-scope engine SF-9/SF-10; individual AA logic out of scope). Conservative grade: **info/medium engine defect** — the sound primitive exists (`in merkle`) and the unsound one should not be usable as a membership proof.

## Bonus finding (S1 family, same construct)

- **S1 position-gating on the eval side:** the sibling checks added in `e01ba3e` (`siblings.every(isNonemptyString)`, `siblings.length > 50 → false`) apply ONLY when `mci >= constants.pemCurvesFixMci` — no `!hasBall && getMinRetrievableMci()` disjunct (formula/evaluation.js ~1783). Measured: a crafted 60-sibling proof (attacker-computed root) evaluates **false above** the fix MCI and **true below** it. Old-DAG-attached units skip the cap — the f5-T1 family confirmed at the eval side for this opcode.

## Measured results (raw, from the real formula/definition engines)

| test | formula `is_valid_merkle_proof` | result |
|---|---|---|
| vacuous X="not-in-any-tree-1" | `true` | CONFIRMS claim |
| vacuous X="hello world" | `true` | CONFIRMS claim |
| vacuous X=random-base64 | `true` | CONFIRMS claim |
| vacuous X="user-supplied element 42" | `true` | CONFIRMS claim |
| positive control: real 5-element tree proof for "c" | `true` | engine not broken |
| negative control: wrong root | `false` | self-consistency-only |
| 60-sibling crafted proof, mci=15000000 (above fix) | `false` | e01ba3e cap works |
| 60-sibling crafted proof, mci=1000000 (below fix) | `true` | S1 gating confirmed |
| definition `['in merkle', ...]`, same vacuous proof, no posted feed | `false` | contrast confirmed |

## Files

- `evidence/p9-poc.js` — the PoC (one-command: `cd <ocore> && node lab-obyte.js <abs>/evidence/lab/p9/p9-poc.js`)
- `evidence/p9-README.md` — run + interpretation
- `evidence/p9-builder.md` — this report

## How an independent reviewer re-runs it

```
cd /Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore
node lab-obyte.js /Users/matheusvsky/Documents/trab/llm-redteam-harness/engagements/obyte-ocore-2026-08/evidence/lab/p9/p9-poc.js
# expect P9-RESULTS block; the vacuous rows must be true, in-merkle contrast false.
```

No network contact, no DB writes beyond the scratch lab SQLite, no real funds/keys (test-vector key only).
