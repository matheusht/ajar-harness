---
name: ajar-investigate
description: Lease prioritized investigation tasks, trace attacker inputs across trust boundaries, record durable anomalies and primitives, and propose falsifiable claims.
---

# Ajar Investigate

Use this skill to execute leased `investigate` or `instrument` tasks, record verified code facts, and propose concrete vulnerability claims.

## 1. Lease and Hydrate Context

1. Lease the highest-salience open task and recover any expired worker leases:
   ```bash
   ajar task lease --worker <worker_id> --kind investigate --recover
   ```
2. Load the `< 4 KB` context frame for the leased task:
   ```bash
   ajar context --task <task_id>
   ```
3. Check the assigned `skill_mode` on the leased task:
   - If `skill_mode` is `zero_skill`: Read the target source code from first principles. Do **not** open any file under `skills/domains/`. Derive invariants directly from state transitions, types, locks, and callers.
   - If `skill_mode` is `domain`: Open only the single matching contrastive pack under `skills/domains/<domain>/SKILL.md`. Stop following a domain pattern immediately if Step 2 shows a concrete guard or divergent architecture.

## 2. Trace State Reachability and Record Durable Facts

1. Pin verified constants, offsets, role bitmasks, or route guards as line-hashed bindings so downstream workers never re-derive them:
   ```bash
   ajar binding set \
     --name "<binding_name>" \
     --value "<verified_value>" \
     --locus "<file:line>" \
     --task <task_id>
   ```
2. When you observe unexpected state, differential behavior, or a crash whose full exploit path is not yet clear, record an `anomaly` immediately (anomalies survive even if a specific hypothesis is later falsified):
   ```bash
   ajar anomaly add \
     --locus "<file:line>" \
     --observation "<exact observed state or differential>" \
     --repro-cmd "<command that triggers observation>" \
     --surface <surface_id>
   ```
3. When you prove a bounded capability (such as partial path traversal, header injection, stale price read, or unauthenticated state write) that lacks standalone high impact, record a `primitive` for chain composition:
   ```bash
   ajar primitive add \
     --locus "<file:line>" \
     --kind "<capability_type>" \
     --preconditions "<required caller state and inputs>" \
     --postconditions "<state or capability gained>" \
     --evidence-cmd "<verification command>"
   ```

## 3. Propose Falsifiable Claims

Before proposing a claim, trace reachability from an untrusted entrypoint to the sink and state a concrete disconfirmation test:

```bash
ajar claim propose \
  --worker <worker_id> \
  --surface <surface_id> \
  --title "<concise defect title>" \
  --locus "<file:line>" \
  --mechanism "<entry -> missing guard -> corrupted invariant -> impact>" \
  --severity <critical|high|medium|low> \
  --falsification-prediction "<what must hold if a hidden upstream guard blocks this path>" \
  --falsification-test "<exact file/caller check or negative-control command to try disproving the claim>"
```

## 4. Close the Task Cleanly

Every leased task must end in an explicit terminal or conditional state:

- **Completed investigation (claim, primitive, or child tasks recorded):**
  ```bash
  ajar task done <task_id> --worker <worker_id> --summary "<concise result>"
  ```
- **Safe surface (`dry` — requires verified `file:line` and `>= 15`-character guard explanation):**
  ```bash
  ajar task dry <task_id> \
    --worker <worker_id> \
    --locus "<file:line>" \
    --control "<exact upstream check, type invariant, or modifier that blocks exploitation>"
  ```
- **Conditionally blocked on an unmet prerequisite:**
  ```bash
  ajar task block <task_id> \
    --worker <worker_id> \
    --predicate "<condition required to unblock>" \
    --check-locus "<file:line>"
  ```

Run `ajar pulse` periodically (automatic check every 8 closed tasks) to surface stale bindings, unblocked tasks, or unchained primitives.
