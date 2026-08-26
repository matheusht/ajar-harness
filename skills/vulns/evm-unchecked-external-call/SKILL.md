---
id: evm.unchecked-external-call
name: Unchecked External Call / Return Value (Silent Failure Treated as Success)
description: >
  Prove that a Solidity/EVM contract performs an external call (raw `.call`/`.send`/`.delegatecall`,
  an ERC20 `transfer`/`transferFrom`/`approve`, or a precompile/library call such as `ecrecover`)
  whose boolean or sentinel result signals FAILURE WITHOUT REVERTING — and the caller discards that
  result, or checks it but doesn't act on it, or assumes the call's nominal effect (amount sent,
  signer recovered) equals its actual effect — so the contract credits a balance, clears a debt,
  forges a valid signer, or releases value as if the call had succeeded when it silently didn't. This
  is distinct from reentrancy: the bug here is a MISSING or MISHANDLED result check on a call that
  returns cleanly (no reentrant re-entry required), most often against a non-reverting/non-standard
  ERC20 (USDT-style missing return, a fee-on-transfer/deflationary/rebasing token) or a precompile
  whose documented failure sentinel (zero address from `ecrecover`) is never checked. An unchecked
  call site alone is an activation signal; a finding requires a reproduced silent-failure-as-success
  that breaks the protocol's own invariant on a real fork.
type: vuln
owasp: "SWC-104 (Unchecked Call Return Value); CWE-252 (Unchecked Return Value), CWE-390 (Detection of Error Condition Without Action), CWE-703 (Improper Check or Handling of Exceptional Conditions). Not an OWASP Top 10 category — this is the EVM smart-contract class."
atlas: "—"
patterns: []

activation:
  strong:
    - "a raw `.call{value:}(\"\")`, `.send()`, or `.delegatecall()` whose returned `bool success` is discarded entirely (not assigned, not checked) or is checked but the failure branch does nothing security-relevant (no revert, no rollback of an already-written credit/state change)"
    - "an ERC20 `transfer`/`transferFrom`/`approve` call is made WITHOUT `require(...)`/`SafeERC20` wrapping its boolean return AND the token set is not provably restricted to a fixed, verified-standard-compliant token — a non-standard token (USDT-style missing return value, entirely reverting the call under strict ABI decoding) or a token that can return `false` on failure without reverting silently defeats the assumption"
    - "accounting credits/records the NOMINAL amount passed into a transfer call (`amountIn`, a parameter) rather than measuring the actual balance delta (`balanceOf(this)` before vs after) — a fee-on-transfer, deflationary, or rebasing token silently desyncs internal bookkeeping from real backing"
    - "a precompile or library call whose documented failure mode is a sentinel value rather than a revert (`ecrecover` returning `address(0)` on invalid/malformed signature data, a `staticcall` returning empty returndata) is consumed directly (used as a signer, an oracle price, an authorization check) without checking for that sentinel first"
    - "a try/catch or low-level-call wrapper catches a failure but the code path AFTER the catch block still proceeds to write the success-path state (mark paid, credit shares, release collateral) regardless of which branch executed"
  weak:
    - "an external call's return value is unchecked, but the callee is a fixed, verified-standard-compliant token/address with no fee-on-transfer/rebase/non-standard-return behavior AND the call's outcome is not security-relevant (e.g., a best-effort refund of dust) — needs confirmation the callee can actually produce a silent non-reverting failure, and that the resulting state divergence matters, before treating as strong"
    - "the nominal-amount-credited pattern exists but the in-scope token allowlist has not been confirmed to admit any fee-on-transfer/deflationary/rebasing token — check the allowlist/permissioned-listing path before concluding reachable"
  negative:
    - "every external call whose result affects accounting, authorization, or entitlement either has its boolean/sentinel return checked AND acted upon (revert or explicit safe branch), uses `SafeERC20`/an equivalent wrapper, or measures the actual balance delta rather than trusting the nominal transfer amount, AND every precompile/library sentinel (zero address, empty returndata) is checked before consumption → likely held; record as a positive control"
    - "the token set is provably restricted (immutable allowlist, no governance-addable tokens) to fixed, standard-compliant, non-fee, non-rebasing tokens AND no precompile/library return is consumed unchecked → likely held"

safe_signal:
  proxy: >
    a LOCAL Foundry harness built from the REAL contract at its pinned in-scope commit (never a
    reimplementation) that observably lets a silently-failed call get treated as success and corrupt
    the protocol's OWN accounting on a local fork. Concrete fixture plan for this card: vendor
    Polygon/Matic's real child-chain `MRC20.transferWithSig()` (`maticnetwork/contracts`, the
    contract named in the disclosed Immunefi Bug Fix Review cited below — an Immunefi
    platform-assessed Critical, ~$2.2M bounty paid pre-exploitation) at the pinned pre-fix commit
    named in that review: the function used `ecrecover()`'s returned signer directly, without
    checking for the `address(0)` failure sentinel, and without a balance/allowance check — so a
    crafted malformed-signature call is silently treated as a valid signer and credits a transfer
    that never should have cleared. Assert on a local fork that a locally-crafted invalid-signature
    call moves locally-minted, valueless test-MRC20 balance (PnL > 0 for the attacker address). Pin
    the exact vulnerable-ref and fix commit hashes from the cited Immunefi writeup at fixture-build
    time rather than trusting a paraphrase. The PATCHED twin — the fix commit shipped in that same
    review (adds the zero-address check and the balance/allowance check) — run through the identical
    harness MUST yield covered-dry (no balance move, assertion holds). For the sibling
    non-reverting-ERC20 sub-case (fee-on-transfer/USDT-style-missing-return), drive the IN-SCOPE
    contract's real code against the REAL mainnet USDT contract forked locally (a real, well-documented
    non-standard token — its `transfer`/`transferFrom` omit the boolean return entirely under strict
    Solidity ABI decoding) rather than a hand-rolled "returns false" mock. The benign marker in both
    cases is the invariant-assertion failure on the local disposable harness, not any live effect. The
    neg-control (patched twin returns covered-dry) is mandatory — a fixture that "confirms" against
    both refs is tautological (fake-client-poc-invariant-check).
  never: >
    never run any sequence against a live mainnet/testnet deployment or any contract/party you do not
    control (the mainnet-USDT fork use above is a READ-ONLY local fork of its bytecode for test
    purposes, never a live call against real USDT); the harness uses only locally-minted, valueless
    test tokens and a locally forked chain state on a local Anvil/EVM. A value-extraction/drain
    demonstration (as opposed to a pure invariant-break assertion) is a Zone-2 artifact — create only
    under explicit human impact-escalation authorization, contained and logged.

impact_escalation:
  enabled_by: scope.md#impact_demo_authorized
  requires: >
    a benign local invariant-break assertion needs no per-artifact pause; a value-moving/drain PoC on
    the local fork is Zone-2 and requires a fresh explicit human confirmation before creation
  containment: "local disposable Foundry/Anvil environment only; locally-minted valueless test tokens; a read-only local fork for any real third-party bytecode (e.g. USDT); logged in the fixture cleanup.md and the engagement cleanup ledger"

oracle: [whitebox-analysis, regrade-oracle, pocinator-oracle]
severity_rubric: { permissionless_forged_credit_or_fund_drain_reproduced: critical, permissionless_accounting_desync_realized_or_reproduced_loss: high, gated_or_bounded_unchecked_call_confirmed_no_permissionless_path: medium, unchecked_call_no_reachable_consuming_sink: low }

procedure:
  - "MAP EXTERNAL CALLS AND RETURN-VALUE HANDLING: enumerate every raw `.call`/`.send`/`.delegatecall`, every ERC20 `transfer`/`transferFrom`/`approve`, and every precompile/library call (`ecrecover`, a `staticcall` to a view function) reachable from untrusted input. For each, is the boolean/sentinel result checked AND acted upon (revert or an explicit safe branch), or discarded/only logged?"
  - "CLASSIFY THE FAILURE MODE: (a) raw call/send returns `false` without reverting and the bool is ignored; (b) an ERC20 `transfer`/`transferFrom` returns `false`, or — USDT-style — omits the return value entirely, and isn't `require`d/`SafeERC20`-wrapped; (c) accounting trusts the NOMINAL transfer amount instead of measuring the actual balance delta, which a fee-on-transfer/deflationary/rebasing token defeats; (d) a precompile/library call's documented failure sentinel (`ecrecover` → `address(0)`, empty returndata) is consumed without being checked first."
  - "IDENTIFY WHAT THE SILENT FAILURE LETS THE ATTACKER DO: trace to the protocol's OWN invariant this breaks — sum(credited) <= sum(actually received), signer == the address that actually signed, debt cleared only if payment cleared, collateral released only if repayment landed. A silent failure that doesn't feed a consuming sink is not yet an impact."
  - "TEST THE ERC20 SUB-CASE AGAINST A REAL NON-COMPLIANT TOKEN, NOT A MOCK: for (b)/(c), fork mainnet USDT (or another real, well-documented non-standard/fee/rebasing token relevant to the in-scope deployment) locally and drive the in-scope contract's real code against it — a hand-rolled 'returns false' mock is not sufficient evidence that the real bytecode's ABI-decoding/accounting behaves as assumed."
  - "REPRODUCE ON A LOCAL FORK WITH THE REAL CONTRACT: build a Foundry harness vendoring the real in-scope contract at its pinned commit (never a reimplementation of the vulnerable logic); drive the failing call; assert the invariant breaks with a real assertion failure, not a printed marker (whitebox-analysis §4)."
  - "RUN THE PATCHED/NEGATIVE CONTROL: the same harness against the fixed version (return-value check added, `SafeERC20` adopted, balance-delta accounting added, or the sentinel check added) MUST yield covered-dry — the invariant holds. Without a passing neg-control the confirmation is reward-hackable."
  - "TRACE REACHABILITY: who can trigger the call whose result is mishandled — permissionless caller, or gated behind an admin/keeper/whitelist role? A permissionless path with fund loss or forged credit is critical/high; a gated path caps severity at medium."
  - "CHECK RELEASE ELIGIBILITY: confirm the exact pinned in-scope commit still has the gap (a fix already merged and released takes the disclosed instance out of scope — cite it as precedent, not a live finding)."

emits: [attempt, finding]
---

## What "confirmed" looks like here

A `confirmed` unchecked-external-call finding shows, on a local fork running the REAL in-scope
contract: (1) a reproduced call whose failure was silent (no revert) and whose result was ignored or
mishandled, (2) the protocol's OWN invariant broken by an assertion failure — a forged credit, an
accounting desync, or a value release that outran what was actually received — not a console marker,
and (3) a passing negative control (the patched/checked version yields covered-dry). Missing (3)
makes the confirmation reward-hackable and routes to `needs_rework` at pocinator.

## Real disclosed anchors for this class (verified, cited)

**Aurora Engine DELEGATECALL exit-event handling — Immunefi Bug Fix Review, Critical
(platform-assessed).** Aurora Engine's handling of native-contract 'exit' events failed to verify
that ETH was actually transferred before crediting the corresponding Aurora-side balance, letting an
attacker mint ETH inside the Aurora EVM and drain the nested nETH pool on NEAR; Immunefi/Aurora
assessed ~70k ETH (~$200M) of capacity at risk. This is the class's cleanest mechanistic match: a
value-transfer's actual outcome was never verified before the corresponding internal credit was
written.
([Immunefi Bug Fix Review — Aurora Engine](https://immunefi.com/blog/bug-fix-reviews/aurora-inflation-spend-bugfix-review-6m-payout/))

**Polygon (Matic) `MRC20.transferWithSig()` — Immunefi Bug Fix Review, Critical
(platform-assessed), ~$2.2M bounty.** `transferWithSig()` lacked balance/allowance checks and
mishandled ECDSA signature recovery returning the zero address — i.e. `ecrecover()`'s documented
invalid-signature sentinel was never checked before the recovered address was trusted as the signer
— letting an attacker mint/steal all ~9,276,584,332 MATIC then held in the MRC20 contract via crafted
invalid-signature transactions; disclosed and patched pre-exploitation. This is the worked
`safe_signal` fixture plan for this card.
([Immunefi Bug Fix Review — Polygon MRC20](https://medium.com/immunefi/polygon-lack-of-balance-check-bugfix-postmortem-2-2m-bounty-64ec66c24c7d))

## Grounding: severity + realized impact (B1 / B2 corpora)

- **B1 (`skills/oracles/references/defi-contest-adjudication-corpus.md`)** — both worked rows for
  this class (Aurora Engine, Polygon MRC20) are **Immunefi platform-assessed Critical** — program
  postmortem/payout authority, not an adversarial contest-judge disposition, but both are
  permissionless-reachable with existential/near-total fund-loss impact, anchoring the `critical`
  tier by reachability (per this card's own methodology: permissionless + fund loss = top tier).
  Grep across the full corpus found **no medium- or low-severity worked row for this specific
  bug-class** (unchecked call/return-value mishandling as root cause) — the corpus is thin here
  compared to reentrancy; the `medium`/`low` tiers in `severity_rubric` are inferred from the general
  reachability-gating principle applied elsewhere in this corpus (a gated/admin-only path caps
  severity), not from a directly cited same-class row. State this honestly in any report rather than
  implying a matching precedent that doesn't exist in the corpus.
- **B2 (`skills/oracles/references/defi-exploit-chain-corpus.md`)** — **Balancer Finance
  deflationary-token (STA/STONK) pool drain, Jun 2020, realized $523,616.52** (601 ETH + 11 WBTC +
  22,600+ other tokens): a dYdX flash loan drove repeated WETH↔STA swaps inside a Balancer pool; STA's
  1%-transfer-fee meant the pool's real STA balance diverged from Balancer's internal record, which
  updated by the NOMINAL transferred amount rather than the amount actually received; the attacker
  then called `gulp()` to resync the internal record down to the near-zero actual balance, permanently
  skewing the pool's price curve for follow-on drainage of the other pooled assets. This is the B2
  realized-loss anchor for the fee-on-transfer/nominal-vs-actual sub-case named in this card's scope,
  and grounds the `high` tier (realized, permissionless, but bounded to one pool's liquidity rather
  than the near-total-supply exposure of the two Critical B1 rows).
  ([Balancer root-cause analysis, PeckShield](https://peckshield.medium.com/balancer-hacks-root-cause-and-loss-analysis-4916f7f0fff5))

## Not this card

- **Reentrancy, even when the write-up's prose says "mishandled return value."** The B2 Sturdy
  Finance incident is titled around a "mishandled oracle return value" (`SturdyOracle` trusted
  Balancer's `getRate()`), but the corpus's own root-cause line is explicit: the actual mechanism is
  **read-only reentrancy** — Balancer's internal `totalSupply()`/balance accounting was transiently
  desynced during a mid-transaction callback window, and the oracle read a manipulated value during
  that window. No call in that chain silently failed and was ignored; the call succeeded and returned
  a value that was itself manipulated by a concurrent re-entry. Route that shape to `evm.reentrancy`
  (read-only-reentrancy activation), not this card. The distinguishing question: did a call FAIL
  WITHOUT REVERTING and get treated as success (this card), or did a call SUCCEED and return a value
  that was corrupted by a reentrant desync window (reentrancy)?
- A call that reverts normally on failure (standard Solidity ERC20s, a `require`-guarded raw call) is
  not this class — the whole point is a failure that does NOT revert and is silently swallowed.
- An unchecked call to a fixed, provably standard-compliant, non-fee, non-rebasing token with no
  security-relevant outcome on failure → weak activation, not a finding, until the callee's actual
  non-reverting-failure capability is confirmed.

## Do not overclaim

- An unchecked-return call site alone is an activation signal, not a finding — you must reproduce an
  actual silent-failure-as-success that breaks a real invariant, with a passing patched-twin
  neg-control.
- The Polygon and Aurora anchors are Immunefi **platform-assessed** dispositions (program
  postmortem/payout authority), not an adversarial contest-judge verdict — state that distinction in
  any report rather than implying contest-style adjudication.
- This class is **thinly represented** in both B1 and B2 relative to reentrancy or access-control: two
  B1 rows and one B2 row survived an exhaustive grep of both corpora for this exact root cause. Do not
  cite additional "precedent" beyond these three without independently verifying the source.
- The disclosed anchors' "$"/token-count figures are the assessing party's exposure-at-risk estimate
  (Aurora, Polygon) or a documented realized on-chain loss (Balancer, B2) — state which one you're
  citing in any report.
