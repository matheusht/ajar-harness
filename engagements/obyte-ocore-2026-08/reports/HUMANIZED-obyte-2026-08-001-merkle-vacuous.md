# [MEDIUM] AA formula `is_valid_merkle_proof` accepts any element via a self-consistent proof (whitelist/membership gates bypassable)

**Target:** ocore core library (Obyte Foundation, Immunefi)
**Pinned:** `a7eb776afc68ed4bed05ba554f7f1e95f5d49b44` (2026-08-10)
**Severity:** Medium (CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:L/A:N = 5.3)

## Summary

Hi Obyte team,

I found that the AA formula opcode `is_valid_merkle_proof(element, proof)` verifies the proof against a root that comes from the proof itself. It never binds the root to any committed or anchored value. A self-consistent proof, `"0-" + base64(sha256(element))`, verifies as true for any element, in any tree or no tree at all. Any AA that uses this opcode as a membership or authorization gate (whitelists, airdrop claims, withdrawal conditions) can be bypassed by anyone.

I confirmed the bypass end to end on a local two-process Obyte network: a withdrawal-gated AA whose condition is "only merkle-tree members may withdraw" paid out to a non-member who supplied the self-consistent proof, and correctly bounced the identical trigger with a wrong-root proof.

## Root cause

Three facts intersect here.

1. `merkle.verifyMerkleProof` (merkle.js:84-101) folds `hash(element)` with the proof's sibling list and compares the result to `proof.root`. With `index=0` and no siblings, the check reduces to `hash(element) === proof.root`.
2. `proof.root` is deserialized from the attacker-supplied proof (merkle.js:75-78, `deserializeMerkleProof`). Nothing anchors it to a tree the attacker does not control.
3. The formula opcode (formula/evaluation.js:1763-1810) has no root-binding step. The definition-language sibling `in merkle` (definition.js:1004-1031) does have one: it requires the root to equal an on-chain posted data-feed value. The formula opcode simply lacks that step.

So the predicate does not prove membership. It proves that the element hashes to the root the caller picked. The e01ba3e sibling-count guard (max 50 siblings, non-empty strings) does not help; the vacuous proof uses zero siblings.

## Steps to reproduce

The full chain runs on a real two-node local network. I packaged it as a one-command script; here is what it does.

1. Boot two ocore full nodes on loopback (ports 6611/6612) with a deterministic synthetic genesis.
2. Define an AA with a single case: `if: "{is_valid_merkle_proof(trigger.data.element, trigger.data.proof)}"`, whose message pays `{trigger.address}` an amount from the AA's balance. This is a standard merkle-whitelist withdrawal pattern.
3. Pay 10000 base units into the AA (the trigger).
4. Trigger it with `trigger.data = { element: "attacker-NOT-A-MERKLE-MEMBER-2026", proof: "0-" + base64(sha256(element)) }`. The element is not in any merkle tree anywhere.
5. Observe the result.

Result: the AA response unit is committed with `sequence=good`, and the withdrawal output of 1000 base units goes to the trigger address. Value conservation is exact (10000 = 8401 change + 1000 withdrawal + 288 + 311 in commissions).

Control, same setup: `trigger.data = { element: "some-member", proof: "0-" + base64(sha256("different-root")) }`. The gate is evaluated and bounces: `"neither case is true in messages"` at aa_composer.js:903. No response unit, no withdrawal.

The runnable PoC is `e31-run.sh` (one command, prints the verdict) with `e31-aa-demo.js` in the engagement evidence. An independent reviewer re-ran it from scratch and verified the raw output, the post-run sqlite state, and the exact value conservation.

## Impact

The engine ships a predicate that cannot do the job it advertises. Any AA that gates a payment, a claim, or a state change on `is_valid_merkle_proof` is bypassable with a two-line proof, regardless of the tree's actual membership.

The honest ceiling: I cannot name a deployed AA that uses the construct, because the individual AA repositories are a separate scope and I did not audit them. The engine defect and its exploitability are confirmed; the usage is the cap. If any deployed AA gates value on this opcode, the impact is direct fund loss for that AA's users.

## Severity

I'm rating this Medium. The mechanism is real, the exploit is trivial, and I demonstrated fund movement on the real code path. The severity is capped by usage: the construct must appear in an AA for the impact to materialize. I think that's a fair read of the evidence; happy to discuss.

## Remediation

Bind the root before verifying, or remove the opcode. The minimal fix is to require the formula to name an on-chain anchor for the root (a data feed, like `in merkle` does) instead of accepting it from the proof. If the opcode is kept for compatibility, its documentation should state plainly that it verifies self-consistency only, so AA authors stop using it as a membership check.

Happy to retest once you've had a look.
