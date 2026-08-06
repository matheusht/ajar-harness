---
id: klever.vm-hook-lifecycle
name: VM-Hook Lifecycle Escape (abandoned execution after timeout / uninterruptible hook)
description: >
  Prove that a smart-contract VM-hook execution can escape its lifecycle controls — either a
  timed-out hook goroutine is abandoned but keeps executing against shared VM/host state (racing
  or corrupting subsequent executions, up to a process crash or cross-transaction state
  contamination), or a hook classified as "fast"/uninterruptible performs attacker-scalable work
  (allocation, loops) on near-zero gas because its metering math is bypassed. The class is
  "unbounded work on fixed/zero gas in a timeout-immune or timeout-abandoned path", the same
  family as the KLR-14 advisory class. A theoretical possibility with no real-path reproduction is
  coverage, not a finding.
type: vuln
owasp: "CWE-400 (Uncontrolled Resource Consumption), CWE-190 (Integer Overflow in metering math), CWE-416 (Use After Free — zombie vs cleaned instance at the C boundary), CWE-362 (Concurrent Execution using Shared Resource with Improper Synchronization) — blockchain VM boundary classes, not an OWASP Top 10 category"
atlas: "—"
patterns: []

activation:
  strong:
    - "a VM hook runs on the main execution thread with NO interrupt path (classified fast/uninterruptible) while its gas cost is computed from attacker-controlled sizes via narrow arithmetic (int32/i64 wrap or truncation), so an attacker contract can trigger work (big allocation, loops, CGO reads) vastly exceeding the charged gas"
    - "a timeout mechanism abandons the executing hook goroutine WITHOUT cancellation ('keeps running until f() returns'), and the abandoned goroutine holds live references to shared host contexts (output/storage/managed-types) that subsequent executions on the same host reuse"
    - "on timeout the host destroys the wasm instance (CleanInstance) while the abandoned goroutine may still be executing against it (C-boundary use-after-free)"
    - "gas is charged AFTER the expensive work (or only for a bounded subset of it), or a slow-hook gas pre-charge exists for some hooks but not others (partial fix — sibling hooks remain unbounded)"
  weak:
    - "a hook does unbounded loops over wasm-memory-derived sizes but the memory cap is small enough to bound the work (quantify before treating as strong)"
    - "a timeout wrapper exists whose Fast/Slow classification is a static allow-list (any misclassified hook silently becomes uninterruptible)"
  negative:
    - "every expensive hook is gas-metered up front (charge proportional to work BEFORE the loop/allocation), runs under an interruptible goroutine with a cancellation check inside the loop, and the abandoned-goroutine path is provably short-lived (gas-bounded to ms) AND its writes are provably unreachable to later executions → likely held"
    - "the host serializes executions with an exclusive lock the zombie cannot hold past its timeout window, and rollback replaces (not reuses) the objects the zombie holds → likely held"

safe_signal:
  proxy: >
    a local Go test or single-node test chain built from the actual pinned code that runs the REAL
    VM host + REAL wasm executor (wasmer2/CGO) with an attacker-style contract: either (a)
    measures the actual gas charged vs wall-clock/allocation for the adversarial hook input, or (b)
    observes the abandoned goroutine surviving past the timeout (goroutine count, stack dump) and
    its effects on a subsequent execution (crash, failed/corrupted output, race under repetition).
    The benign marker is the observed stall/crash/contamination on your own disposable local
    environment.
  never: >
    never run the adversarial contract against any live network, public node, or shared
    infrastructure; local synthetic keys/contracts only; the reproduction must not require real
    tokens or real users.

impact_escalation:
  enabled_by: scope.md#impact_demo_authorized
  requires: >
    benign/non-destructive local reproduction under the engagement's standing Zone-2
    authorization; fresh human confirmation only if the PoC needs beyond a local disposable
    single-operator environment
  containment: "local build/test environment only; synthetic contracts and keys; logged in engagement cleanup.md"

oracle: [whitebox-analysis, regrade-oracle, pocinator-oracle]
severity_rubric: { reproducible_process_crash_or_chain_availability: high, cross_tx_state_contamination_demonstrated: high, stalled_hook_quantified_node_degradation: medium, theoretical_only: not_a_finding }

procedure:
  - "ENUMERATE THE HOOK SURFACE: list every VM hook (generated wrapper + registrations) and its classification (fast/slow), gas-charging site, and timeout path."
  - "AUDIT THE METERING MATH: recompute the charged gas for adversarial input sizes (check int32/int64 wraparound and truncation in the size-to-gas formula, and charge-before-vs-after-work ordering)."
  - "AUDIT THE TIMEOUT LIFECYCLE: on timeout, is the hook goroutine cancelled or abandoned? Does the abandoned path hold live references to host contexts reused by later executions? Is the wasm instance destroyed under a possibly-running zombie?"
  - "BUILD A FAITHFUL REPRODUCTION: a Go test running the real host + real executor (CGO/wasmer) with a compiled attacker contract — measure gas vs wall-clock/allocation (or goroutine survival + next-execution effects) with the production gas schedule and timeout config."
  - "NEGATIVE CONTROL: the same hook with benign input sizes (scales normally) and, for the zombie case, a non-timeout baseline that leaves no goroutine behind."
  - "CLASSIFY THE IMPACT: crash (process-level, reproducible rate), cross-tx contamination (zombie writes committed with a later tx), or stall (uninterruptible fast hook). Quantify per-tx cost and per-block economics (block gas limit / attacker fee) honestly."

emits: [attempt, finding]
---

## What "confirmed" looks like here
A real contract, run against the real host/executor, either (a) charges a tiny gas for measured
unbounded work in a timeout-immune path (with the per-tx stall and per-block economics stated), or
(b) leaves an abandoned goroutine that demonstrably survives the timeout, races/corrupts a
subsequent execution, or crashes the process at a reproducible rate. Negative controls hold.

## Real disclosed anchors for this class
- Certik KLR-14 (Klever, fixed in v1.7.20 @ 0b70b0f): BigIntPow/BigFloatPow performed unbounded
  work on fixed gas; fix pre-charges gas proportional to the result size. The residual class is
  that the timeout wrapper still ABANDONS slow-hook goroutines (timeoutWrapper.go comment: "it is
  NOT cancelled, it keeps running until f() returns"), so sibling slow hooks (ExecuteOnDestContext,
  CreateContract, Upgrade, Delete) remain unbounded-after-timeout — and "fast" hooks have no
  interrupt path at all.
- Upstream mx-chain-go GHSA-mv8x-668m-53fg (Critical): VM "execute on same context" improper
  initialization — instance/context reuse across executions. The lifecycle-reuse theme (instance
  destroyed under a running goroutine) rhymes with this anchor.

## Not this card
- A plain expensive-computation tx that IS fully gas-metered (slow but honest) — that is
  gas-mitigated DoS, excluded by policy.
- Hooks whose timeouts and metering are fully correct (positive control).

## Do not overclaim
- "The hook could stall" with no real measurement of the stall on the real executor is
  `needs_review`, never `confirmed`.
- A zombie observed only in a mocked host (no real wasmer CGO) does not prove the C-boundary
  crash/contamination paths — run the real executor.
- Report the honest branch you proved: if the crash rate is what you observed, say so with the
  rate; if deterministic cross-tx contamination was not observed, state that it was not observed.

## Cross-ecosystem fix-diff corpus (B3)
Verified **merged** fix-commits for this class — pre-patch shape → added guard — in `skills/oracles/references/blockchain-client-cve-corpus.md`: 4 merged CosmWasm/cosmos-evm anchors (call-depth bound, precompile RunAtomic snapshot, simulate-mode divergence, decode_sections gas-bypass); non-cosmos coverage is analogical only (see corpus honest-gaps). Every fix SHA was verified merged (unmerged/version-bump/substituted SHAs rejected); use it to cross-check a candidate's mechanism against how the real disclosed instances were actually closed.
