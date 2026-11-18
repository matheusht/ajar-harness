---
name: ajar-investigate
description: Lease bi-directional investigation tasks, apply keep-biased discovery, enforce the guarded-primitive anti-premature-dry rule, and propose falsifiable claims.
---

# Ajar Investigate

Use this skill to execute leased `investigate` or `instrument` tasks, persist verified code facts, and propose falsifiable vulnerability claims.

## 1. Lease and Hydrate Prefix-Stable Context

1. Lease the highest-salience open task and recover expired worker leases:
   ```bash
   ajar task lease --worker <worker_id> --kind investigate --recover
   ```
2. Load the prefix-stable `< 4 KB` certified context frame:
   ```bash
   ajar context --task <task_id>
   ```
3. Follow the task's `skill_mode`, `direction`, `Active Workspace Steers`, and `Active Epistemic Hooks`:
   - **Workspace Steers:** Obey all `Active Workspace Steers` listed in the `Certified Run Prefix`. Never pursue out-of-scope paths barred by a Steer.
   - **Active Epistemic Hooks (`H1`–`H8`):** When `Task Delta` surfaces an active hook (`<= 2` per task), execute its check on the target locus and obey its `Kill Rule` immediately if the compensating invariant holds. Never fabricate shell/gdb output in prose.
   - **`skill_mode=zero_skill`:** Analyze target code from first principles. Do **not** open any file under `skills/domains/`. Derive invariants directly from state transitions, types, locks, and callers.
   - **`skill_mode=domain`:** Open only the single matching contrastive pack under `skills/domains/<domain>/SKILL.md`. Exit immediately if target code enforces a verified compensating control.
   - **`direction`:** Follow the assigned search direction (`outside_in`, `inside_out`, `native_ffi`, or `peer_symmetry`).

## 2. Keep-Biased Discovery, Capability Tags, and Durable Memory

Discovery is **keep-biased**: capture real behavioral signals first and let `ajar-falsify` and `ajar-reproduce` act as the kill-biased disconfirmation funnel.

1. Pin verified constants, record audited line coverage, and checkpoint multi-step progress before context compaction:
   ```bash
   ajar binding set --name "<binding_name>" --value "<verified_value>" --locus "<file:line>" --task <task_id>
   ajar coverage record <rel_path> --start-line <start> --end-line <end> --task <task_id> --worker <worker_id>
   ajar task checkpoint <task_id> --worker <worker_id> --state-json '{"checked_callers":["a.c:40"],"next_focus":"b.c:88"}'
   ```
2. Record unexpected state, differential behavior, or crashes immediately as an `anomaly` (anomalies survive even if an initial claim is later falsified):
   ```bash
   ajar anomaly add \
     --locus "<file:line>" \
     --observation "<exact observed state or differential>" \
     --repro-cmd "<command that triggers observation>" \
     --surface <surface_id>
   ```
3. Record bounded capabilities as a `primitive` with typed `--provides-tags` and `--requires-tags` (`ns:name`) so `ajar` matches cross-subsystem bridges automatically:
   ```bash
   ajar primitive add \
     --surface <surface_id> \
     --locus "<file:line>" \
     --kind "<capability_type>" \
     --preconditions "<required caller state and inputs>" \
     --postconditions "<state or capability gained>" \
     --provides-tags "<ns:capability_provided>" \
     --requires-tags "<ns:precondition_needed>" \
     --guarded-by "<optional upstream guard file:line>" \
     --guard-assumption "<optional invariant assumed by upstream guard>" \
     --evidence-cmd "<verification command>"
   ```

## 3. Anti-Premature-`dry` Rule for Guarded Sinks

Never mark a task `dry` the moment you spot an upstream check if an inner sink or primitive remains dangerous when that check's assumption breaks:

1. Register the inner capability with `ajar primitive add --guarded-by "<guard_file:line>" --guard-assumption "<assumption>"`. `H1_GUARD_SYMMETRY` automatically enqueues an inside-out audit of `<guard_file:line>`.
2. Either complete the guard-break audit on `<guard_file:line>` (proving it sound via `dry` or breaking it via `chain`), or park the current task with `ajar task block`.
3. `ajar task dry` deterministically rejects closing a task when an unchained guarded primitive on the same surface/subsystem still awaits completed guard verification.

## 4. Propose Falsifiable Claims

Trace reachability from an untrusted entrypoint to the sink and state a concrete disconfirmation test:

```bash
ajar claim propose \
  --worker <worker_id> \
  --surface <surface_id> \
  --title "<concise defect title>" \
  --locus "<file:line>" \
  --mechanism "<entry -> missing guard -> corrupted invariant -> impact>" \
  --severity <critical|high|medium|low> \
  --falsification-prediction "<what must hold if a hidden upstream guard blocks this path>" \
  --falsification-test "<exact caller check or negative-control command to try disproving the claim>"
```

## 5. Close the Task Cleanly

Every leased task must end in an explicit state:

- **Completed investigation (claim, primitive, or child tasks recorded):**
  ```bash
  ajar task done <task_id> --worker <worker_id> --summary "<concise result>"
  ```
- **Verified safe surface (`dry` — requires verified `file:line`, `>= 15`-char guard explanation, and zero unchained guarded primitives):**
  ```bash
  ajar task dry <task_id> \
    --worker <worker_id> \
    --locus "<file:line>" \
    --control "<exact upstream check, type invariant, or modifier that blocks exploitation>"
  ```
- **Conditionally blocked on an unmet prerequisite (auto-reopened by `ajar pulse` when a matching primitive/anomaly lands):**
  ```bash
  ajar task block <task_id> \
    --worker <worker_id> \
    --predicate "<condition required to unblock>" \
    --check-locus "<file:line>"
  ```
