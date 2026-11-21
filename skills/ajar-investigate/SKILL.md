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
3. Record bounded capabilities (`--role capability`) AND non-buggy **Trust-Laundering Gadgets** (`--role trust_gadget` — normal code that trusts an upstream invariant such as path containment or pre-validated config) with typed `--provides-tags` and `--requires-tags` (`ns:name`) so multi-hop percolation and Open Doors snap together automatically:
   ```bash
   ajar primitive add \
     --surface <surface_id> \
     --locus "<file:line>" \
     --kind "<capability_or_gadget_type>" \
     --role <capability|trust_gadget> \
     [--trusted-invariant "<invariant assumed by trust_gadget>"] \
     [--symbols "<fn_or_state_carrier>"] \
     --preconditions "<required caller state and inputs>" \
     --postconditions "<state or capability gained>" \
     --provides-tags "<ns:capability_provided>" \
     --requires-tags "<ns:precondition_needed>" \
     --guarded-by "<optional upstream guard file:line>" \
     --guard-assumption "<optional invariant assumed by upstream guard>" \
     [--micropatch <optional_ablation.diff>] \
     --evidence-cmd "<verification command>"
   ```
4. Update explicit campaign threat-model assumptions when code inspection proves or breaks them:
   ```bash
   ajar threat-model verify <assumption_id> --locus "<file:line>" --notes "<verified boundary guard>"
   ajar threat-model invalidate <assumption_id> --evidence "<prim_id|finding_id|file:line>" --notes "<how boundary breaks>"
   ```

## 3. Suspended Open Doors (`ajar door park`) & Anti-Premature-`dry` Rule

Push maximum depth on every promising lead. When a deep sink or partial chain hits a concrete missing link, **park** it as a reactive **Open Door** instead of abandoning the idea or spinning indefinitely on one surface:

1. Suspend the blocked sink or partial prefix/suffix with `ajar door park`. Ajar spawns `<= 2` bounded `bridge` hunter tasks while preserving parallel greenfield exploration, and automatically wakes the door (`status = 'ready'`, `salience >= 96`) via tags, code symbols/call edges, or FTS5 the moment any worker discovers a matching piece:
   ```bash
   ajar door park \
     --direction <sink_to_source|source_to_sink|middle_bridge> \
     [--jewel <jewel_id>] \
     [--held-ids "<prim_or_fnd_id>"] \
     [--snapshot <snp_id>] \
     --anchor-locus "<sink_or_tip_file:line>" \
     [--blocker-locus "<guard_file:line>"] \
     --missing "<exact upstream capability, state carrier, or guard bypass needed>" \
     [--wanted-tags "<ns:tag1,ns:tag2>"] \
     [--wanted-symbols "<symbol_or_filename>"]
   ```
2. If inside-out verification proves a guarded primitive's upstream check cannot be bypassed on any reachable caller, close the primitive cleanly via `ajar primitive dry <prim_id> --locus "<guard_file:line>" --reason "<verified invariant>"`.
3. `ajar task dry` deterministically rejects closing a task when an active (`status != 'dry'`) unchained guarded primitive on the same surface/subsystem still awaits completed guard verification.

## 4. Propose Falsifiable Claims

Trace reachability from an untrusted entrypoint to the sink and state a concrete disconfirmation test. Express `--title`, `--mechanism`, and `--falsification-test` strictly as structural code transitions and boundary violations (for example, `prepare_symlink_changes skips SYMLINK_IN_RESULT when patch->old_mode == 0, allowing writes through a renamed intra-repo symlink`), never speculative post-exploitation `.git/hooks/*` persistence scripts, reverse-shell commands, or raw shellcode literals (`ajar claim propose` deterministically rejects weaponized prose tails):

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
