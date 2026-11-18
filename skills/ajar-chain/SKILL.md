---
name: ajar-chain
description: Compose bounded primitives, unexplained anomalies, and low-or-medium findings into verified end-to-end exploit chains.
---

# Ajar Chain

Use this skill when two or more `primitives`, `unexplained` anomalies, or low/medium `findings` exist in `run.db`, or when closeout gate `G5` enqueues a `chain` composition task.

## 1. Enumerate Composable Building Blocks

Inspect all recorded capabilities, anomalies, and findings across subsystems:

```bash
ajar primitive list
ajar anomaly list
ajar claim list
ajar binding list
```

Query historical multi-stage exploit precedents when evaluating cross-boundary composition:

```bash
ajar precedent search "<stage1_kind> <stage2_kind>"
```

Consult `skills/references/project-zero-zdi-chain-corpus.md` (system, browser, virtualization, and enterprise chains) and `skills/references/defi-exploit-chain-corpus.md` (flash-loan, oracle manipulation, callback reentrancy, and governance chains) for verified stage handoff patterns.

## 2. Backward and Forward Interface Matching

Compose chains using strict contract matching between stages:

1. **Backward Goal Chaining:** Start from a high-impact sink (`critical` or `high` surface whose direct exploitation was blocked by a precondition such as internal-only network origin, missing admin token, non-zero vault supply, or KASLR/ASLR). Search `primitives` whose `postconditions` satisfy that exact precondition.
2. **Forward Escalation:** Start from a verified entry primitive (such as SSRF, open redirect in privileged WebView, arbitrary header/cookie write, or unauthenticated state nudge) and query `reachability` for internal surfaces exposed by that postcondition.
3. **Modular Stage Boundaries:** Keep each stage interface explicit (`input -> state transition -> output artifact/token`). If one intermediate stage fails under a specific configuration, substitute an alternative primitive that satisfies the same interface contract without discarding the rest of the chain.

## 3. Verify and Propose the End-to-End Chain

Never assert a theoretical chain from prose alone. Build a single end-to-end script or test that executes every stage sequentially in one run and passes a benign negative control:

```bash
ajar chain propose \
  --title "<Stage 1 -> Stage 2 -> Terminal Impact>" \
  --steps "<primitive_or_finding_id_1>,<primitive_or_finding_id_2>" \
  --poc-cmd "<end-to-end multi-stage exploit command>" \
  --control-cmd "<benign workflow command that does not cross boundary>" \
  --severity critical
```

## 4. Severity Calibration Rule

Elevate chain severity above its individual links only when:
- Every stage executes end-to-end without manual state injection between stages, and
- The combined path crosses a trust boundary or achieves an impact (`C`/`I`/`A`) that no single stage reaches on its own.
