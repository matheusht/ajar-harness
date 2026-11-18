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

```bash
ajar claim reproduce <claim_id> \
  --worker <worker_id> \
  --mode source \
  --poc-cmd "<command proving exploit impact>" \
  --control-cmd "<command exercising benign caller path>" \
  --micropatch <path/to/micropatch.diff> \
  [--shared-guard-locus "<file:line>"] \
  --determinism deterministic
```

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

## 4. Two-Failure Telemetry Pivot

If `ajar claim reproduce` fails twice on the same claim with an unchanged observation hash, `run.db` transitions the claim to `needs_instrumentation` and spawns an `instrument` task. Stop guessing payload variations; instrument the target, inspect runtime values at `claim.locus`, record a `binding` or `anomaly`, and retry only after new runtime evidence lands.
