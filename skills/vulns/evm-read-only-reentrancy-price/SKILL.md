---
id: evm.read-only-reentrancy-price
name: EVM Read-Only Reentrancy — Manipulated Price / Value Read
description: >
  Prove that a value-reading path (an LP-token/share price, a virtual_price, a getPrice/getPricePerFullShare,
  a collateral valuation) can be called DURING an external-call window in which the underlying pool's
  balances and supply are transiently desynchronized — so a *different* protocol consuming that read
  gets a stale/manipulated value and makes a wrong decision (a fraudulent liquidation, an over-borrow,
  a mispriced mint/redeem). The victim contract writes no state and needs no reentrancy guard on itself;
  the flaw is that a consuming protocol trusts a read that is manipulable inside a reentrancy window.
  A view that *looks* manipulable is an activation signal; a finding needs a reproduced stale read
  driving a real, invariant-breaking decision on a fork.
type: vuln
owasp: "SWC-107 (Reentrancy, read-only variant); CWE-662 (Improper Synchronization), CWE-841. Not an OWASP-web category — EVM smart-contract class."
atlas: "—"
patterns: []

activation:
  strong:
    - "a lending/vault/derivatives protocol reads an EXTERNAL pool's price via a getter (Curve get_virtual_price / balances-based math, Balancer BPT price via getPoolTokens, an LP getPricePerFullShare) that can be entered mid-`remove_liquidity`/join/`receive`-callback window, and consumes it for a collateral/borrow/liquidation decision — read-only reentrancy on the price source"
    - "the price/value getter is NOT behind a reentrancy check (no nonReentrant view, no `vault.manipulation` re-entrancy sentinel), while the AMM it reads is known to hand control to the caller during add/remove-liquidity (ETH refund, ERC777/hook token)"
    - "one borrowing-power / collateral-valuation entrypoint routes its oracle read through the guarded path, but ANOTHER entrypoint (e.g. setUserUseReserveAsCollateral) reads the same value WITHOUT the guard — the exact Sturdy Finance shape (a missing `_validateOracle(msg.sender)` on one path)"
  weak:
    - "a protocol reads an AMM spot/LP price but the specific AMM cannot hand control to the caller during the balance-update window (no callback/hook/ETH send) — confirm the reentrancy window exists before treating as strong"
    - "a getter reads pool state but no consuming protocol makes a value-at-risk decision on it — the stale read has no sink; downgrade"
  negative:
    - "every value-reading path the protocol consumes is either behind a reentrancy sentinel (Curve `remove_liquidity` re-entrancy check / Balancer manipulation guard) or reads a manipulation-resistant source (a TWAP with no mid-window read), consistently across ALL entrypoints → likely held; record as a positive control"
    - "the consumed price cannot be moved within a single transaction (no reentrancy window, no atomic manipulation) → likely held"

safe_signal:
  proxy: >
    a LOCAL Foundry harness — a mainnet fork at a pinned pre-fix block, or the REAL consuming contract
    at its pinned in-scope commit plus the real AMM — in which the read-only-reentrancy sequence
    produces a stale/manipulated price that drives an invariant-breaking decision (a position liquidated
    though truly healthy, or an over-borrow), while the PATCHED twin (the guard added — e.g. Sturdy's
    one-line `_validateOracle`) makes the same assertion HOLD (covered-dry). The benign marker is the
    invariant-assertion failure on the local disposable harness. The confirm-on-fork LOOP itself is
    already proven by the sibling `evals/contract-audit/fixtures/jpegd-reentrancy/` fixture; the
    dedicated read-only-reentrancy fixture (Sturdy 0af7167 -> 1ee1971) needs a mainnet-fork/archive-RPC
    setup to stay faithful (no AMM mock, which would reintroduce reward-hacking) and is a tracked
    follow-up.
  never: >
    never run the sequence against any live deployment or any party you do not control; local fork
    only, valueless test tokens. A value-extraction/drain demonstration is a Zone-2 artifact — create
    only under explicit human impact-escalation authorization, contained and logged.

impact_escalation:
  enabled_by: scope.md#impact_demo_authorized
  requires: >
    a benign local invariant-break assertion needs no per-artifact pause; a value-moving/drain PoC on
    the local fork is Zone-2 and requires a fresh explicit human confirmation before creation
  containment: "local disposable Foundry/Anvil fork only; locally-minted valueless test tokens; logged in the fixture cleanup notes and the engagement cleanup ledger"

oracle: [whitebox-analysis, regrade-oracle, pocinator-oracle]
severity_rubric: { fraudulent_liquidation_or_overborrow_drain_reproduced: critical, bounded_mispricing_value_extraction_reproduced: high, manipulable_read_no_reproduced_consuming_decision: medium, stale_read_no_consuming_sink: low }

procedure:
  - "FIND THE CONSUMED READ: identify every place the in-scope protocol reads an EXTERNAL pool/vault price or value (LP price, virtual_price, share price, getPoolTokens-derived value) to make a collateral/borrow/liquidation/mint decision."
  - "LOCATE THE REENTRANCY WINDOW: confirm the underlying AMM/vault hands control to the caller during a balance-update (Curve remove_liquidity ETH send, Balancer join callback, a hook token) — the window in which the read is transiently wrong."
  - "CHECK GUARD COVERAGE ACROSS ALL ENTRYPOINTS: the flaw is usually inconsistency — one path guards the read (a reentrancy sentinel / `_validateOracle`), another does not. Enumerate every entrypoint that consumes the read; a single unguarded one is the bug (the Sturdy shape)."
  - "PIN THE INVARIANT: state the decision the stale read corrupts (a healthy position must not be liquidatable; borrow value <= collateral value at a manipulation-resistant price). This is the confirm-on-fork assertion."
  - "REPRODUCE ON A FORK WITH THE REAL CONSUMER + REAL AMM: fork at a pinned pre-fix block (or vendor the real consuming contract + use the real AMM); drive the read-only-reentrancy sequence; assert the invariant breaks. Do NOT mock the AMM — a mocked pool cannot faithfully reproduce the reentrancy window and reintroduces reward-hacking."
  - "RUN THE PATCHED/NEGATIVE CONTROL: the same harness with the guard added (or the fixed commit) MUST yield covered-dry. Without a passing neg-control the confirmation is reward-hackable."
  - "TRACE REACHABILITY + SEVERITY: permissionless liquidation/borrow with fund loss is critical; a gated path (behind a KEEPER/admin role) caps severity (the LoopFi QA precedent)."

emits: [attempt, finding]
---

## What "confirmed" looks like here

On a local fork with the REAL consuming protocol + the REAL AMM (never a mocked pool): a reproduced
read-only-reentrancy that yields a stale price which drives an invariant-breaking decision (a healthy
position liquidated, or an over-borrow), an assertion failure (not a marker), AND a passing negative
control (the guarded/patched version yields covered-dry).

## Real disclosed anchors for this class (verified, cited)

- **Sturdy Finance (Jun 2023, ~$800K).** `LendingPool.setUserUseReserveAsCollateral()` read collateral
  value without the `_validateOracle(msg.sender)` reentrancy check that guarded the other borrowing-power
  paths — a read-only reentrancy via a Balancer oracle path. Fixed same-day by adding that one line
  (`sturdyfi/sturdy-contracts` `0af7167` -> `1ee1971`). This is the intended dedicated fixture (tracked
  follow-up; needs a mainnet fork to reproduce the Balancer window faithfully).
- **Blueberry (Sherlock, 2023, High).** `BalancerPairOracle.getPrice` read a desynced BPT
  supply-vs-token-balance during a Balancer join callback -> fraudulent liquidation.
- **Sentiment (Sherlock, Dec 2022, High, escalation-resolved).** wstETH-ETH Curve LP `virtual_price`
  depressed inside a `remove_liquidity` reentrancy window -> stale collateral price -> unwarranted
  liquidation of healthy positions.

## Grounding: severity + realized impact (B1 / B2 corpora)

- **B1 (`skills/oracles/references/defi-contest-adjudication-corpus.md`)** — read-only-reentrancy is
  contest-graded High when permissionless (Blueberry, Sentiment) but QA when the price-refresh is gated
  (LoopFi `KEEPER_ROLE`). Set `severity_rubric` by reachability.
- **B2 (`skills/oracles/references/defi-exploit-chain-corpus.md`)** — realized read-only-reentrancy
  exploits (Sturdy, and the Sentiment/Blueberry shapes) anchor the critical/high tiers with on-chain
  loss.

## Not this card
- A same-function or cross-function reentrancy where the VICTIM writes state and can be guarded on
  itself -> that is `evm.reentrancy`; this card is specifically the read-only variant where a
  *consuming* protocol trusts a manipulable read.
- A manipulable price read with no protocol consuming it for a value-at-risk decision -> low; trace the
  sink or it is not a finding.

## Do not overclaim
- "This getter is manipulable" is an activation signal, not a finding — you must reproduce the stale
  read driving a real invariant-breaking decision, with a passing patched-twin neg-control.
- Do NOT mock the AMM to force a reproduction — a mocked pool that cannot reproduce the real reentrancy
  window is a reward-hacked confirmation (`fake-client-poc-invariant-check`).
