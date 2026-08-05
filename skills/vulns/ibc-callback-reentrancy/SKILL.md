---
id: cosmos.ibc-callback-reentrancy
name: IBC Callback Reentrancy (Checks-Effects-Interactions Violation)
description: >
  Prove that an IBC packet lifecycle handler (timeout, acknowledgement, or receive) invokes an
  application-level callback (a CosmWasm contract via ibc-hooks, or any middleware that can itself
  dispatch new SDK messages) BEFORE mutating the state that provides replay protection (deleting a
  packet commitment, marking a packet processed), letting a malicious callback recursively resubmit
  the same message while the stale state still exists — voiding replay protection and enabling
  repeated execution of logic meant to run exactly once (refund, mint, unlock).
type: vuln
owasp: "CWE-696 (Incorrect Behavior Order), CWE-841 (Improper Enforcement of Behavioral Workflow) — adjacent to classic smart-contract reentrancy, applied to IBC packet lifecycle handlers"
atlas: "—"
patterns: []

activation:
  strong:
    - "a packet lifecycle handler (OnTimeoutPacket, OnAcknowledgementPacket, OnRecvPacket, or middleware wrapping any of these) invokes an application-specific or contract callback BEFORE the corresponding state mutation that provides replay protection (DeleteCommitment / marking the packet processed) — checks-effects-interactions violated: interaction before effect"
    - "the callback target can itself dispatch new SDK messages synchronously within the same execution context (CosmWasm submessages, ICS-20 hooks, any 'reply-to' contract-call pattern) — meaning it can call back into the same or a related handler before the original call returns"
    - "CosmWasm (or an equivalent contract-execution capability) is enabled with permissive-to-semi-permissive contract uploads, and ibc-hooks-style middleware wraps a token-transfer or value-bearing application module"
  weak:
    - "a callback-before-effect ordering exists but the callback target cannot synchronously dispatch new messages (e.g. a pure read-only hook) — lower priority, confirm the callback truly cannot re-enter before treating as strong"
  negative:
    - "the state mutation providing replay protection happens strictly before any external/application callback is invoked (effects before interactions) → likely held"
    - "CosmWasm/contract execution is disabled or uploads are fully permissioned to trusted parties only in this deployment configuration → precondition not met, note but lower priority per 'must not require a previously compromised environment'"

safe_signal:
  proxy: >
    a local test chain with the real, unmodified IBC/module code and a locally-deployed, benign
    test contract you author, demonstrating that the test contract's callback can trigger the same
    handler to run more than once for a single original packet — observed via a real counter/state
    value only incrementable through the vulnerable re-entry path (e.g. a refund/mint amount that
    should be credited exactly once being credited N times), reproduced against real keeper code,
    never a hand-rolled emulation of the packet lifecycle.
  never: >
    never deploy the demonstration contract or trigger the reentrant call against any live public
    mainnet or testnet; the local test contract must be your own benign code, never derived from or
    resembling a real exploit intended for use elsewhere; no real-value tokens at any point.

impact_escalation:
  enabled_by: scope.md#impact_demo_authorized
  requires: >
    benign/non-destructive local reproduction proceeds without a per-artifact pause under this
    engagement's standing Zone-2 authorization (see scope.md)
  containment: "local disposable test chain and locally-authored benign test contract only; logged in engagement cleanup.md"

oracle: [whitebox-analysis, regrade-oracle, pocinator-oracle]
severity_rubric: { reentrant_unbounded_mint_or_drain_reproduced: critical, reentrant_double_execution_bounded_impact: high, ordering_violation_no_reentry_path_confirmed: medium }

procedure:
  - "MAP EVERY PACKET LIFECYCLE HANDLER in scope (OnTimeoutPacket, OnAcknowledgementPacket, OnRecvPacket) across ibc-go core and any middleware/hooks layered on top (ibc-hooks, custom middleware in scope modules)."
  - "FOR EACH HANDLER, ORDER THE OPERATIONS: list, in exact source order, every state mutation and every external/callback invocation. Identify precisely where the replay-protection mutation (commitment deletion, processed-flag set) sits relative to any callback."
  - "IDENTIFY REENTRY CAPABILITY: for each callback invoked before the replay-protection mutation, determine whether the callback target can synchronously dispatch a new SDK message within the same call stack (CosmWasm submessages are the primary real-world vector; check the exact submessage reply semantics in scope)."
  - "CONFIRM THE DEPLOYMENT PRECONDITION: verify CosmWasm/contract execution is actually enabled and reachable in the configuration this program considers 'intended deployed environment' — this precondition existing is not itself a compromised environment, per program scope."
  - "BUILD A REAL LOCAL REPRODUCTION: author a minimal, benign CosmWasm (or equivalent) test contract that, when invoked as the callback target, resubmits the same message; deploy it on a local test chain running real module code."
  - "OBSERVE ACTUAL RE-EXECUTION: confirm via real state queries that the once-only logic executed more than once for a single original packet, and quantify the exact amplification achieved (bounded by recursion depth, gas, or genuinely unbounded)."
  - "NEGATIVE CONTROL: confirm a benign, non-reentrant callback does not trigger repeated execution, isolating that the reentrant call pattern (not the callback mechanism generally) causes it."
  - "CHECK RELEASE ELIGIBILITY: this exact class was fixed in ibc-go v4.6.0/v5.4.0/v6.3.0/v7.4.0/v8.2.0 for the disclosed instance — confirm any candidate is either a genuinely new instance of the pattern or a regression, not the already-patched historical bug, at the exact pinned/released version in scope."

emits: [attempt, finding]
---

## What "confirmed" looks like here
A real local reproduction, using the actual unmodified ibc-go/module code and a benign test
contract you authored, shows a packet-lifecycle handler's once-only logic executing more than once
for a single packet because the replay-protection state mutation happens after an external callback
that can re-enter — with the exact amplification quantified and a negative control showing a
non-reentrant callback behaves correctly.

## Real disclosed anchor for this class (verified, cited — the single most concretely evidenced,
most distinctly Cosmos-specific class found in research for this engagement; patched, use as a
taxonomy template for finding regressions or structurally similar gaps elsewhere in scope, not as a
currently-exploitable bug in patched, released ibc-go)
- ibc-hooks `OnTimeoutPacket`: invoked the CosmWasm callback before `DeleteCommitment`; a malicious
  contract used a submessage to recursively resubmit `MsgTimeout` 102 times in a real PoC, minting
  ~102x the original IBC token amount across the 102 reentrant calls. CWE-696, Critical,
  ASA-2024-007 / GHSA-j496-crgh-34mx, reported by
  Maxwell Dulin (Asymmetric Research). Estimated $126M+ at risk on Osmosis (largest-TVL affected
  chain); no funds actually lost, patched. Note: this exact bug class later caused a real ~$6.4M
  Astroport-on-Terra exploit in July 2024 after a regression of the fix — a concrete, dated example
  of why this class deserves scrutiny even in code that claims to already be patched.

## Not this card
- A reentrancy-shaped bug in a smart contract's own logic, with no IBC packet-lifecycle handler
  involved → this is a CosmWasm-contract-authoring concern, not a Cosmos Stack protocol bug, unless
  the platform's own host-function/callback contract enables it.
- A callback-ordering issue where the callback truly cannot dispatch new synchronous messages (a
  read-only hook) → note as a weak/lower-priority activation, don't claim reentrancy without a
  demonstrated re-entry path.

## Do not overclaim
- Finding a callback-before-state-mutation ordering alone is an activation signal, not a finding —
  you must demonstrate an actual reentrant call achieving repeated execution.
- Report/advisory "at risk" dollar figures (like the $126M Osmosis estimate) are the reporting
  party's own TVL-based estimate of exposure, not a realized loss — state this distinction plainly
  if citing precedent in a report; do not imply funds were actually lost in the disclosed anchor.
