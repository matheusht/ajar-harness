---
name: ajar-reproduce
description: Prove survived vulnerability claims through deterministic 4-arm causal reproduction across source, binary, or live targets.
---

# Ajar Reproduce

Use this skill to convert a `survived_falsify` claim into a causally verified finding. Prose agreement never confirms a finding; `ajar claim reproduce` requires all four experimental arms to pass.

## The 4-Arm Causal Proof

| Arm | Target State | Input | Required Outcome |
| --- | --- | --- | --- |
| **Arm 1** | Unmodified target | Exploit PoC (`--poc-cmd`) | Fires the specific security assertion, sanitizer signature, or unauthorized canary effect |
| **Arm 2** | Unmodified target | Benign control (`--control-cmd`) | Completes normal operation without triggering the exploit assertion |
| **Arm 3** | Minimal root-cause fix (`--micropatch` / `--guard-json`) | Exploit PoC (`--poc-cmd`) | Blocks the exploit assertion (`reproduce` rejects reward-hacked assertions that still fire) |
| **Arm 4** | Minimal root-cause fix (`--micropatch` / `--guard-json`) | Benign control (`--control-cmd`) | Completes normal operation without breaking legitimate functionality |

## Mode 1: Source Targets (`--mode source`)

1. Write a minimal 1–5 line root-cause diff (`micropatch.diff`) against the target source.
   - **Strict Micro-Patch Rules:** Edit only production code at the root-cause locus. Never modify tests, add `sys.exit(0)` / `os._exit(0)`, swallow all exceptions (`except Exception: pass`), or unconditionally disable the endpoint (`return None` / `return False` at function entry). The anti-mitigation validator rejects deceptive patches.
2. Run 4-arm reproduction in isolated worktree slots:
   ```bash
   ajar claim reproduce <claim_id> \
     --worker <worker_id> \
     --mode source \
     --poc-cmd "<command proving exploit impact>" \
     --control-cmd "<command exercising benign caller path>" \
     --micropatch <path/to/micropatch.diff> \
     --determinism strict
   ```
   For race conditions, pass `--determinism probabilistic --trials 10` so statistical contrast verifies Arm 1 vs Arm 3. Pass `--sibling-poc-cmd "<cmd>"` when checking whether the same root-cause patch kills a candidate duplicate claim.

## Mode 2: Stripped or Closed-Source Binaries (`--mode binary`)

When source code is unavailable, prove root-cause specificity using ASLR-normalized crash/trap PCs, input-field ablation, and a runtime preload/eBPF/wrapper guard:

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

## Mode 3: Authorized Live Endpoints (`--mode live`)

Only run `--mode live` when `scope_rules` explicitly permits live target requests (`--allow-live-requests` and `--allow-host <host>`). Live reproduction plants a fresh 128-bit CSPRNG canary (`ajar_canary_<32hex>`) owned by Principal A and tests cross-principal access from Principal B with mandatory teardown verification:

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

## Two-Failure Telemetry Pivot

If `ajar claim reproduce` fails twice on the same claim with an unchanged observation hash, `run.db` transitions the claim to `needs_instrumentation` and spawns an `instrument` task. Stop guessing payload variations; add tracing, inspect exact state values at the sink, record a `binding` or `anomaly`, and resume reproduction only after new evidence is recorded.
