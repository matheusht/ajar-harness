---
id: pattern.dag-spend-proof-uniqueness
name: Spend-Proof Uniqueness and Full-vs-Light Asymmetry — private payment double-spend
description: >
  Private payments rely on spend proofs that are not inherently unique (a proof for output X can be
  replayed or duplicated unless the ledger verifies uniqueness). The asymmetric risk: the light
  client and the full node verify DIFFERENT properties (light = check proof validity only; full =
  check uniqueness), so a spend proof that is merely valid but not unique passes where the
  full-node check is absent, gated, or skipped — double-spending a private asset output.
type: pattern
owasp: "—"
also: "DAG/DLT private payments — spend-proof uniqueness"
atlas: "—"
routes_to: ["stub:dag-dlt-vuln-cards"]

activation:
  strong:
    - "a recent commit fixed 'uniqueness of spend proof is not verified' in ANY path (full or light) — siblings likely in the other path"
    - "private payment validation queries `inputs` by (unit, message_index, output_index) with an `is_unique` field that is nullable / conditional on stability"
    - "spend-proof checks differ between light (`conf.bLight`) and full-node code paths"
    - "output_hash / spend-proof content not bound to the specific output being spent"
  weak:
    - "private assets (is_private) in divisible_asset.js / private_payment.js with their own validation flow"
    - "uniqueness checks that only run once the input is 'stable' (is_unique = null while unstable)"
    - "multiple private divisible assets in one payment (recently added feature = fresh surface)"
  negative:
    - "uniqueness is enforced unconditionally on every spend-proof application, full and light"
    - "the spend proof cryptographically binds the output (unit+index) so it cannot be replayed to another output"
    - "stability-based deferral is only a scheduling delay, not a skipped check (the check runs before credit)"
---

# Spend-proof uniqueness

> **The money question.** Private payments in DAG ledgers often use a proof the spender holds that
> proves entitlement to a hidden output. A proof that is *valid* but *not unique* lets the holder
> spend the same output twice (or once per place that accepts it) if nothing enforces uniqueness at
> credit time. The uniqueness check is the money boundary.

**The asymmetry to hunt.** Full nodes and light clients legitimately verify different things —
but a *check that exists on one path and is skipped, gated, or conditional on the other* is the
shape. V-001's sibling (`05f291d8`, "uniqueness of spend proof is not verified in light") is the
canonical anchor: the fix made the full-node error path throw only when NOT light. Hunt both sides:
a check now gated on `!conf.bLight` may have a sibling where the *full* node skips something the
light client does.

**Uniqueness vs stability.** `is_unique = bStable ? 1 : null` — an unstable input is allowed to be
non-unique because it may still become non-serial. The risk is a path that *credits* on an input
before uniqueness is settled, or that treats `null` as "checked" anywhere.

## Suggested probes (benign, local-fork only)
- **Map the check matrix.** For each private-payment spend application (full node, light node,
  divisible, indivisible, multiple-asset), record: proof-validity check? uniqueness check? output
  binding? stability condition? The matrix rows that differ are candidates.
- **Replay the proof.** Locally generate a private asset, build two spend transactions using the
  same spend proof (or a proof not bound to the output), apply on a local fork, and observe whether
  both credit. Negative control: the same proof applied twice where uniqueness IS enforced must
  fail the second time.
- **Unstable-credit path.** Check whether any code credits or forwards value based on an input whose
  uniqueness is still `null` (unstable), and what happens when the input later resolves to
  non-unique (double-spend).
- **Multi-asset private payments** (recent feature): uniqueness per (asset, output) tuple, not per
  unit.

## Negative controls
- Same proof, second application, refused (where enforced).
- The proof binds the exact output (unit+message_index+output_index).
- Light and full paths agree on which checks run.

## Counterexample (held)
- Uniqueness enforced unconditionally at credit time on both paths; the stability deferral never
  credits before resolution.
