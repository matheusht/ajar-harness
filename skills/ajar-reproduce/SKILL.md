---
name: ajar-reproduce
description: Prove survived vulnerability claims through locus-bound 4-arm causal reproduction and the 12 PoC interrogation lenses.
---

# Ajar Reproduce

Use this skill to convert a `survived_falsify` claim into a causally verified finding. Prose agreement never confirms a finding; `ajar claim reproduce` requires all four experimental arms plus causal locus alignment to pass.

## 1. The Locus-Bound 4-Arm Causal Proof

| Arm | Target State | Input | Required Outcome |
| --- | --- | --- | --- |
| **Arm 1** | Unmodified target | Exploit PoC (`--poc-cmd`) | Fires the specific security assertion, sanitizer crash, or unauthorized canary effect |
| **Arm 2** | Unmodified target | Benign control (`--control-cmd`) | Completes normal operation on the same surface without triggering the exploit assertion |
| **Arm 3** | Minimal root-cause fix (`--micropatch` / `--guard-json`) | Exploit PoC (`--poc-cmd`) | Blocks the exploit assertion via a `1–5` line edit overlapping `claim.locus` (`±60` lines) |
| **Arm 4** | Minimal root-cause fix (`--micropatch` / `--guard-json`) | Benign control (`--control-cmd`) | Completes normal operation without breaking legitimate callers |

**Locus-Match & `claim_mismatch` Recovery:** In `source` mode, `ajar claim reproduce` verifies that `--micropatch` modifies lines overlapping `claim.locus` (or an explicit `--shared-guard-locus` when fixing a shared chokepoint). If your patch fixes a different file or distant function, `reproduce` rejects it with `claim_mismatch:`. Recover by running `ajar claim rescope <claim_id> --locus "<actual_file:line>" --reason "..."`, passing independent `survive`, and re-running `reproduce`.

## 2. The 12 PoC Interrogation Lenses

Interrogate every PoC, control, and micro-patch against all 12 lenses before invoking `ajar claim reproduce`:

1. **Control Contrast:** Arm 2 invokes the same handler or state path with valid input rather than `true` or an unrelated noop.
2. **Path Proof:** The PoC reaches `claim.locus` rather than failing early in an unrelated parser or fixture check.
3. **Locus Match:** The `1–5` line `--micropatch` overlaps `claim.locus` (or `--shared-guard-locus`), proving causal alignment between prose and patch.
4. **Cross-Boundary Provenance:** Attacker input crosses an actual trust boundary rather than mutating caller-owned local state.
5. **State Mutation vs Echo:** The PoC proves unauthorized state corruption, read disclosure, or memory fault—never bare HTTP `200` or harmless input reflection.
6. **Privilege Delta:** The unprivileged caller achieves an outcome denied to that role's intended baseline permissions.
7. **Default Configuration:** Reproduction holds under default or documented production settings without artificial debug flags.
8. **Determinism / Statistical Contrast:** Use `--determinism deterministic` by default; for race conditions, use `--determinism probabilistic_race --trials 8` to prove repeatable Arm 1 vs Arm 3 separation.
9. **Zero Harness Artifact:** The failure originates in target production code, not a bug inside the PoC script or mock harness.
10. **Anti-Mitigation Cleanliness:** `--micropatch` never edits tests, calls `exit(0)` / `os._exit(0)`, swallows all exceptions (`except Exception: pass`), or disables the endpoint unconditionally.
11. **Warm Sibling Cross-Kill:** Pass `--sibling-poc-cmd "<cmd>"` when testing whether one root-cause micro-patch simultaneously kills candidate duplicate claims (`duplicate_root_cause`).
12. **Sample Enumeration (`N`):** Before stating blast radius or severity, count exact affected routes, records, or sibling call sites (`N = verified count`) instead of extrapolating from `N = 1`.

## 3. Execution by Target Mode

### Source Targets (`--mode source`)

1. **Strike-Free Smoke Probe (`ajar repro try`):** Before running full 4-arm reproduction, validate compiler flags, fixtures (`$AJAR_ARTIFACTS_DIR`), and candidate patches inside scratch `slot-inst` with zero `failed_repro_count` impact (`build_or_env_error` and `preflight_error` never burn strikes on `ajar claim reproduce` either):
   ```bash
   ajar repro try \
     [--build-cmd "<incremental build command>"] \
     --cmd "<exploratory PoC command>" \
     [--patch <path/to/candidate.diff>]
   ```
2. **4-Arm Reproduction + Post-State Snapshot (`--save-post-state`):** Supply `--build-cmd` when compiling untracked target binaries across clean/patched resets, `--save-post-state <rel_dir>` to archive Arm-1 post-state (`snp-*` `.tar.gz`) for downstream `ajar door park` / `ajar chain probe`, and `--release-cmd` when `H6_RELEASE_UB_DIFF` fires. Never pass caller-supplied self-execution flags (`-c core.sshCommand=`, `--upload-pack=`, `GIT_SSH_COMMAND=`, `LD_PRELOAD=` — rejected by `evaluate_precondition_realism`):
   ```bash
   ajar claim reproduce <claim_id> \
     --worker <worker_id> \
     --mode source \
     [--build-cmd "<incremental build command>"] \
     --poc-cmd "<command proving exploit impact>" \
     --control-cmd "<command exercising benign caller path>" \
     --micropatch <path/to/micropatch.diff> \
     [--save-post-state "<rel_dir_written_by_arm1>"] \
     [--provides-tags "<ns:capability_unlocked>"] \
     [--declared-steps <N>] \
     [--release-cmd "<release-profile PoC command>"] \
     [--release-control-cmd "<release-profile benign control command>"] \
     [--shared-guard-locus "<file:line>"] \
     --determinism deterministic
   ```
3. **Single-Command Realism Calibration (`ajar finding calibrate`):** If post-confirm review finds that a reproduced finding requires multi-step caller interaction or carries a lower standalone ceiling (`stepping_stone`), calibrate it in one atomic command (`ajar finding calibrate <finding_id> --severity <sev> --reason "..."`).

### Stripped or Closed-Source Binaries (`--mode binary`)

```bash
ajar claim reproduce <claim_id> \
  --worker <worker_id> \
  --mode binary \
  --binary <path/to/binary> \
  --poc-io-json <poc_spec.json> \
  --control-io-json <control_spec.json> \
  --guard-json <runtime_guard.json> \
  --ablation-json <ablation_spec.json>
```

### Authorized Live Endpoints (`--mode live`)

Only run `--mode live` when `scope_rules` explicitly authorizes the target host (`--allow-live-requests` and `--allow-host <host>`). Plant a 128-bit CSPRNG canary (`ajar_canary_<32hex>`) owned by Principal A, test cross-principal access from Principal B, and verify teardown removal:

```bash
ajar claim reproduce <claim_id> \
  --worker <worker_id> \
  --mode live \
  --target-url "https://<authorized-host>" \
  --seed-cmd "<plant Principal A canary>" \
  --poc-cmd "<unprivileged Principal B exploit request>" \
  --control-cmd "<authorized Principal A control request>" \
  --teardown-cmd "<delete canary and verify HTTP 404/absent>"
```

## 4. Two-Failure Telemetry Pivot (`ajar claim instrument`)

If `ajar claim reproduce` fails twice on the same claim with an unchanged observation hash, `run.db` transitions the claim to `needs_instrumentation` and spawns an `instrument` task. Stop guessing payload variations and run an isolated diagnostic probe inside `slot-inst`:

```bash
ajar claim instrument <claim_id> \
  --worker <worker_id> \
  --probe-cmd "<diagnostic trace command>" \
  [--probe-patch <path/to/temporary_trace.diff>]
```

`slot-inst` captures runtime output into `anomalies`, resets the worktree cleanly, and unlocks `survived_falsify` so you can retry `reproduce` with verified state.

## 5. Swarm Worker Packets, Fallback Ladder, & Execution Integrity

1. **Just-Enough-Context Swarm Dispatch (`ajar swarm packet`):**
   - Lead orchestrators generate stripped `"Swarm Worker"` assignment packets (`--wire-profile direct`, `<= 45` lines, `(claim_id, severity, locus)` tuples with zero parent reasoning or hype prose):
     ```bash
     ajar swarm packet --stage reproduce --limit 3 --worker w-repro-1
     ```
   - Step down the `--wire-profile` fallback ladder (`direct -> swarm_patch_first -> regression_tdd`, automatically halving multi-claim batches `[4] -> [2, 2] -> [1, 1]`) **only** when a worker subagent is filter-blocked or goes idle with `0` tool calls:
     ```bash
     ajar swarm fallback <dispatch_id> --reason filter_blocked
     ```
2. **Entrypoint Fidelity & Runtime Execution Anti-Cheat:**
   - On `cli` / daemon / server surfaces, `--poc-cmd` and `--control-cmd` must build and invoke the real target binary or entrypoint (`./git ...`, `cargo test ...`), never link a synthetic `stub.c` harness directly against internal `.o` object files (permitted only when `surfaces.kind = 'library_api'`).
   - Never substitute `<conceptual_placeholder>` tokens or inspect patched `.c`/`.rs`/`.go`/`.sol` source text via `grep`, `rg`, or `.read_text()` inside `--poc-cmd`; `ajar claim reproduce` deterministically rejects static source-inspection cheats.
3. **Strict `--env-blocker` Gate (`ajar claim block`):**
   - `ajar claim block <claim_id> --worker <id> --env-blocker <missing_hardware|external_service|privileged_kernel|license_or_key|host_os_mismatch> --reason "<exact command error>"` is strictly reserved for concrete missing infrastructure. Voluntary policy/safety refusals are rejected by both `ajar claim block` and closeout gate `G4`.

