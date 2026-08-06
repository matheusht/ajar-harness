---
id: evm.reentrancy
name: EVM Reentrancy (Checks-Effects-Interactions Violation)
description: >
  Prove that a Solidity/EVM contract makes an external call (a token transfer to a control-giving
  token, a raw call/send, a callback, or a cross-contract call) BEFORE it finishes updating the state
  that call's correctness depends on — letting an attacker re-enter the same function (single-function),
  a different function guarded separately (cross-function), or a value-reading path (read-only
  reentrancy) while the contract is in a half-updated state, and extract value or corrupt accounting.
  A reordering that merely *looks* unsafe is an activation signal; a finding requires a reproduced
  re-entry that breaks the protocol's own invariant on a real fork.
type: vuln
owasp: "SWC-107 (Reentrancy); CWE-841 (Improper Enforcement of Behavioral Workflow), CWE-662 (Improper Synchronization). Not an OWASP-web category — this is the EVM smart-contract class."
atlas: "—"
patterns: []

activation:
  strong:
    - "an external call (token.transfer/transferFrom on a token that can give the sender control — ERC777/ERC677/hook tokens, native ETH send/call, a user-supplied callback, or a call into an attacker-influenced contract) occurs BEFORE the function finishes writing the state that provides correctness/replay protection (balance/share accounting, a processed flag, a nonce) — checks-effects-INTERACTIONS violated: interaction before effect"
    - "a function has a reentrancy guard (nonReentrant) but a DIFFERENT function that shares the same state does not — cross-function reentrancy: the guard on A doesn't cover the re-entry into unguarded B"
    - "a value-reading path (an oracle getPrice, a share-price/getPricePerFullShare, a collateral valuation) can be called DURING an external-call window in which the underlying balances are transiently desynced — read-only reentrancy: no state is written by the victim, but a stale/manipulated read is consumed by another protocol"
    - "a vault/AMM computes shares or price from balanceBefore/totalSupply where the two are sampled at different points relative to an external transfer (the exact JPEG'd C4 #81 shape: balanceBefore read, transfer, THEN supply read) — reentrancy lets one logical action mint/price at two effective rates in one tx"
  weak:
    - "an external call precedes a state write, but the called contract/token is fixed and cannot give control to the attacker (a known non-hook ERC20, a trusted immutable callee) — needs confirmation the callee can actually re-enter before treating as strong"
    - "a nonReentrant guard exists on the obvious function but the full set of state-sharing functions has not been enumerated — check for a cross-function gap before concluding held"
  negative:
    - "checks-effects-interactions is followed everywhere the shared state is touched (all effects written before any external call), AND every state-sharing function carries a consistent reentrancy guard, AND value-reading paths cannot be called mid-window (or read a manipulation-resistant source) → likely held; record as a positive control"
    - "the only external calls are to fixed, non-control-giving callees and no read-only path consumes transiently-desynced state → likely held"

safe_signal:
  proxy: >
    a LOCAL Foundry harness built from the REAL contract at its pinned in-scope commit (never a
    reimplementation) that observably BREAKS the protocol's own invariant when driven through the
    reentrant sequence — e.g. the shipped Milestone-1 fixture
    `evals/contract-audit/fixtures/jpegd-reentrancy/`: the real JPEG'd YVault at the vulnerable ref
    lets a split reentrant deposit mint shares at two rates (1250 vs a fair 1000 for equal value) so
    attacker PnL > 0, and the PATCHED twin makes the same assertion HOLD (PnL == 0, covered-dry). The
    benign marker is the invariant-assertion failure on the local disposable harness, not any live
    effect. The neg-control (patched twin returns covered-dry) is mandatory — a fixture that "confirms"
    against both refs is tautological (fake-client-poc-invariant-check).
  never: >
    never run the sequence against any live mainnet/testnet deployment or any contract/party you do
    not control; the harness uses only locally-minted, valueless test tokens on a local Anvil/EVM. A
    value-extraction/drain demonstration (as opposed to a pure invariant-break assertion) is a Zone-2
    artifact — create only under explicit human impact-escalation authorization, contained and logged.

impact_escalation:
  enabled_by: scope.md#impact_demo_authorized
  requires: >
    a benign local invariant-break assertion needs no per-artifact pause; a value-moving/drain PoC on
    the local fork is Zone-2 and requires a fresh explicit human confirmation before creation
  containment: "local disposable Foundry/Anvil environment only; locally-minted valueless test tokens; logged in the fixture cleanup.md and the engagement cleanup ledger"

oracle: [whitebox-analysis, regrade-oracle, pocinator-oracle]
severity_rubric: { reentrant_fund_drain_or_unbounded_mint_reproduced: critical, reentrant_bounded_value_extraction_or_accounting_corruption: high, ordering_violation_no_reachable_reentry_path_confirmed: medium, read_only_reentrancy_stale_read_no_consuming_sink: low }

procedure:
  - "MAP EXTERNAL CALLS vs STATE WRITES: in the in-scope contract, list every external call (token transfers, raw call/send, callbacks, cross-contract calls) and, for each, whether the state its correctness depends on is fully written BEFORE it (effects-before-interactions) or after."
  - "CLASSIFY THE RE-ENTRY: single-function (re-enter the same fn), cross-function (a guard on A, a re-entry into unguarded state-sharing B), or read-only (a value-reading path consumed by another protocol during a desync window). Each needs a different reproduction."
  - "IDENTIFY THE CONTROL-GIVING VECTOR: for a token path, confirm the token can actually give the sender control (ERC777/hook/callback). For an ETH path, the receiver's fallback. For a callback, who supplies it. No control vector -> downgrade to weak/held."
  - "PIN THE INVARIANT: state the protocol's OWN invariant the re-entry breaks (share/asset fair pricing, sum(withdrawable) <= backing, debt <= collateral at a guarded price). This is the confirm-on-fork assertion, not a printed marker (whitebox-analysis §4)."
  - "REPRODUCE ON A LOCAL FORK WITH THE REAL CONTRACT: build a Foundry harness vendoring the real contract at the pinned in-scope commit; drive the reentrant sequence; assert the invariant breaks. Never a reimplementation of the vulnerable logic."
  - "RUN THE PATCHED/NEGATIVE CONTROL: the same harness against the fixed version (or with the guard added) MUST yield covered-dry — the invariant holds. Without a passing neg-control the confirmation is reward-hackable."
  - "TRACE REACHABILITY: who can call the entrypoint (permissioning, whitelist, noContract-style gates)? A whitelisted-only or admin-only path caps severity; a permissionless path with fund loss is critical."
  - "CHECK RELEASE ELIGIBILITY: confirm the exact pinned in-scope commit still has the gap (a fix already merged and released takes the disclosed instance out of scope — cite it as precedent, not a live finding)."

emits: [attempt, finding]
---

## What "confirmed" looks like here

A `confirmed` reentrancy finding shows, on a local fork running the REAL in-scope contract: (1) a
reproduced re-entry through a real control-giving vector, (2) the protocol's OWN invariant broken by
an assertion failure (not a console marker), and (3) a passing negative control (the patched/guarded
version yields covered-dry). Missing (3) makes the confirmation reward-hackable and routes to
`needs_rework` at pocinator.

## Real disclosed anchor for this class (verified, cited)

**JPEG'd yVault reentrant deposit — Code4rena #81 (Apr 2022), High-Risk, sponsor-confirmed/resolved.**
`YVault.deposit` read `balanceBefore = balance()`, called `token.safeTransferFrom` (which a
control-giving token re-enters), THEN read `supply = totalSupply()` — so an attacker could split one
deposit into two nested deposits and mint shares against a stale `balanceBefore` with an inflated
`supply` (1250 shares for value that should mint 1000), draining other depositors. Fixed by reading
`supply` together with `balanceBefore` before the transfer and moving `safeTransferFrom` last
(jpegd/core `cb7af8a`, "fix reentrancy issue"). The shipped Milestone-1 fixture
`evals/contract-audit/fixtures/jpegd-reentrancy/` reproduces this on the real contract at both refs
and is the worked `safe_signal` for this card (vuln → PnL +111, patched → PnL 0).

## Grounding: severity + realized impact (B1 / B2 corpora)

- **B1 (`skills/oracles/references/defi-contest-adjudication-corpus.md`)** — reentrancy is a
  contest-graded class across Axis A/B/C: judged severities span High (permissionless fund loss,
  read-only-reentrancy → fraudulent liquidation at Blueberry/Sentiment) down to Medium/QA when gated
  (a read-only-reentrancy behind `KEEPER_ROLE` was QA at LoopFi). Use it to set `severity_rubric` by
  reachability, not by mechanism alone.
- **B2 (`skills/oracles/references/defi-exploit-chain-corpus.md`)** — realized reentrancy exploits:
  Cream AMP ERC-777 cross-function reentrancy (~$18.8M), Sentiment/Blueberry read-only-reentrancy →
  stale price → fraudulent liquidation. Realized-loss impact anchors the critical tier.

## Not this card
- A reentrancy-shaped ordering where the callee provably cannot give the attacker control → weak
  activation, not a finding, until a real re-entry path is shown.
- A read-only-reentrancy stale read with no consuming sink (nothing reads the desynced value) → low;
  the impact is whatever the consuming protocol does with it, which must be traced.

## Do not overclaim
- A checks-effects-interactions ordering issue alone is an activation signal, not a finding — you must
  reproduce an actual re-entry breaking a real invariant, with a passing patched-twin neg-control.
- The disclosed anchor's "$" figures are the reporting party's exposure estimate unless a realized
  on-chain loss is cited (B2) — state the distinction in any report.
