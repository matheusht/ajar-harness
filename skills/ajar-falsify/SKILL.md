---
name: ajar-falsify
description: Challenge proposed vulnerability claims from an independent worker identity and rescope shifted claims before spending reproduction budget.
---

# Ajar Falsify

Use this skill as the kill-biased disconfirmation filter on `proposed` claims using an independent challenger identity (`falsifier_worker_id != proposer_worker_id`). Closeout gate `G3` blocks self-certified claims.

## 1. Lease a Falsification Task

```bash
ajar task lease --worker <challenger_worker_id> --kind falsify --recover
ajar context --task <task_id>
```

Never pass the same `--worker` identifier stored in `proposer_worker_id` on the target claim.

## 2. Execute the Four Disconfirmation Checks

Run the claim's declared `falsification_test`, check `Active Workspace Steers`, and test all four failure modes documented in `skills/references/false-positive-controls-corpus.md` and `skills/references/rejected-disputed-cve-corpus.md`:

1. **Upstream Guard Check (`reachability`):**
   ```bash
   ajar ref query --kind reachability "<sink_or_handler_symbol>"
   ```
   Verify whether middleware, router prefixes, Solidity modifiers, database RLS policies, framework auto-escaping, or caller bounds checks normalize or reject the payload before `locus`.
2. **Design, Steer, and Trust-Boundary Check (`intent`):**
   ```bash
   ajar ref query --kind intent "<feature_or_module>"
   ```
   Verify that the required attacker precondition does not already grant the claimed capability (for example, database superuser running OS commands, admin HTML authoring, or local CLI self-DoS) and does not violate an active operator `Steer`.
3. **Precedent and False-Positive Trap Check (`precedent`):**
   ```bash
   ajar precedent search "<defect_class or component>"
   ```
   Reject claims that rely on echoed input without cross-boundary provenance, HTTP `200` on mutations without state change, valid JWT signatures with rejected claims, or inert text reflection inside escaped DOM sinks.
4. **State Invariant Check:**
   Confirm whether constructor constraints, decimal offsets, lock ordering, or saturating/checked arithmetic make the alleged bad state unreachable.

## 3. Record the Ruling (`falsify`, `rescope`, or `survive`)

- **If a concrete compensating control or unreachable precondition refutes the claim completely, falsify it:**
  ```bash
  ajar claim falsify <claim_id> \
    --worker <challenger_worker_id> \
    --control-locus "<file:line>" \
    --notes "<exact guard or unreachable precondition that refutes the mechanism>"
  ```
  Falsifying a claim marks the hypothesis `falsified` (`rejected_during_research`) while restoring any linked `anomaly` to `unexplained` so real crashes or state differentials are never silently lost. If the underlying anomaly itself is intended behavior, explain it explicitly:
  ```bash
  ajar anomaly explain <anomaly_id> \
    --locus "<file:line>" \
    --reason "<why the observed behavior is benign and intended>"
  ```

- **If a sink is disabled by default configuration (`config_gated`), park it and spawn a 1-lease override probe instead of burying it permanently:**
  ```bash
  ajar claim falsify <claim_id> \
    --worker <challenger_worker_id> \
    --control-locus "<file:line>" \
    --config-gate "<config_flag_or_env_predicate>" \
    --notes "<sink is real at locus but gated by default-off config predicate>"
  ```
  `--config-gate` transitions the claim to `config_gated` and spawns one bounded `investigate` probe checking whether tenant preferences, container templates, or sibling routes enable that predicate.

- **If a real defect exists but its true causal `locus`, preconditions, or `severity` differ from the proposal, rescope instead of discarding:**
  ```bash
  ajar claim rescope <claim_id> \
    --worker <challenger_worker_id> \
    --locus "<true_root_cause_file:line>" \
    --severity <critical|high|medium|low> \
    --mechanism "<updated causal mechanism and preconditions>" \
    --reason "<why locus or severity shifted during disconfirmation>"
  ```
  When `--locus` or `--mechanism` changes, `rescope` resets the claim to `proposed` so a fresh challenger verifies the updated root cause cleanly.

- **If the claim survives every disconfirmation check at its stated `locus`, promote it to reproduction:**
  ```bash
  ajar claim survive <claim_id> \
    --worker <challenger_worker_id> \
    --notes "<verified reachability path and why tested upstream controls do not block it>"
  ```

Close the leased `falsify` task with `ajar task done <task_id> --worker <challenger_worker_id> --summary "<ruling>"`.
