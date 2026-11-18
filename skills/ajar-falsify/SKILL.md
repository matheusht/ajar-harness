---
name: ajar-falsify
description: Challenge proposed vulnerability claims from an independent worker identity before spending reproduction budget.
---

# Ajar Falsify

Use this skill to attempt disconfirmation of a `proposed` claim using an independent challenger identity (`falsifier_worker_id != proposer_worker_id`). Closeout gate `G3` rejects self-certified claims.

## 1. Lease a Falsification Task

```bash
ajar task lease --worker <challenger_worker_id> --kind falsify --recover
ajar context --task <task_id>
```

Never pass the same `--worker` identifier stored in `proposer_worker_id` on the target claim.

## 2. Execute the Four Disconfirmation Checks

Run the claim's declared `falsification_test` and check all four failure modes documented in `skills/references/false-positive-controls-corpus.md` and `skills/references/rejected-disputed-cve-corpus.md`:

1. **Upstream Guard Check (`reachability`):**
   ```bash
   ajar ref query --kind reachability "<sink_or_handler_symbol>"
   ```
   Verify whether middleware, router prefixes, Solidity modifiers, database RLS policies, framework auto-escaping, or caller bounds checks normalize or reject the payload before `locus`.
2. **Design and Trust-Boundary Check (`intent`):**
   ```bash
   ajar ref query --kind intent "<feature_or_module>"
   ```
   Verify that the required attacker precondition does not already grant the claimed capability (for example, database superuser running OS commands, admin HTML authoring, or local CLI user self-DoS).
3. **Precedent and False-Positive Trap Check (`precedent`):**
   ```bash
   ajar precedent search "<defect_class or component>"
   ```
   Reject claims that rely on echoed input without cross-boundary provenance, HTTP `200` on mutations without state change, valid JWT signatures with rejected claims, or inert text reflection inside escaped DOM sinks.
4. **State Invariant Check:**
   Confirm whether constructor constraints, decimal offsets, lock ordering, or saturating/checked arithmetic make the alleged bad state unreachable.

## 3. Record the Ruling

- **If you find a concrete compensating control or broken reachability link, falsify the claim:**
  ```bash
  ajar claim falsify <claim_id> \
    --worker <challenger_worker_id> \
    --control-locus "<file:line>" \
    --notes "<exact guard or unreachable precondition that refutes the mechanism>"
  ```
  Falsifying a claim marks the hypothesis `falsified` (`rejected_during_research`), while preserving any underlying `anomaly` as `unexplained` so real crashes or differentials are never silently discarded. If the underlying anomaly itself is benign, explain it explicitly:
  ```bash
  ajar anomaly explain <anomaly_id> \
    --locus "<file:line>" \
    --reason "<why the observed behavior is benign and intended>"
  ```

- **If the claim survives every disconfirmation check, promote it to reproduction:**
  ```bash
  ajar claim survive <claim_id> \
    --worker <challenger_worker_id> \
    --notes "<verified reachability path and why tested upstream controls do not block it>"
  ```

Close the leased `falsify` task with `ajar task done <task_id> --worker <challenger_worker_id> --summary "<ruling>"`.
