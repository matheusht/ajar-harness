---
id: evm.slippage-MEV
name: EVM Slippage / Sandwich / MEV — Missing minAmountOut / Deadline Enforcement
description: >
  Prove that a swap/rebalance/liquidation path in the in-scope contract executes against an AMM or
  aggregator WITHOUT an attacker-unmovable output floor (a hardcoded or caller-spoofable
  `amountOutMin`/`minAmountOut` of 0, or a value the caller — not the beneficiary — controls) and/or
  without a real deadline bound (no `deadline` param, or one set to `block.timestamp` which is a
  no-op), so a searcher can sandwich the transaction (front-run to move price, let the victim trade at
  the worse rate, back-run to capture the difference) or hold it until a stale price is favorable, and
  the protocol/user provably loses value versus the fair execution price. A missing/zero/spoofable
  slippage bound is an activation signal; a finding requires a reproduced, quantified value loss on a
  local fork, AND the class is graded by the actual deployment's mempool model and by whether the loss
  is direct/significant, not by "MEV existed."
type: vuln
owasp: "SWC-114 (Transaction Order Dependence / front-running); CWE-362 (Race Condition / TOCTOU), CWE-841 (Improper Enforcement of Behavioral Workflow — missing deadline/output-floor bound). Not an OWASP-web category — EVM smart-contract class."
atlas: "—"
patterns: []

activation:
  strong:
    - "a swap/zap/liquidate/harvest call into a DEX router or pool passes `amountOutMin`/`minAmountOut` as a hardcoded `0` (or a value derived from the SAME on-chain spot price it is meant to protect against, so it can never bind), on a chain with a PUBLIC mempool — the exact 'no output floor' shape"
    - "a swap call's `deadline` parameter is hardcoded to `block.timestamp` (always 'now', so it never actually expires and can sit in the mempool/be held indefinitely) or the function has no deadline parameter at all, letting a searcher choose the most favorable block to execute a held tx"
    - "the caller (a keeper/relayer/any EOA), not the beneficiary/depositor, supplies `amountOutMin` for a swap that moves the beneficiary's funds — a malicious or lazy caller can pass 0 regardless of what protection the code path nominally offers"
  weak:
    - "the same missing/zero minAmountOut or no-op deadline pattern, but the deployment chain has a private mempool / uses a private-orderflow relay (e.g. Flashbots Protect, a sequencer with no public txpool) — Sherlock's rule downgrades a would-be High to Medium and a would-be Medium to Invalid; confirm the actual mempool model before grading"
    - "a slippage bound exists but is bounded by a static/config percentage rather than a live off-chain-computed quote — usually a partial mitigation (caps loss, does not eliminate MEV); check whether the static bound is tight enough to matter"
    - "a limit-order/oracle-price-read path that requires atomic same-block execution against a stale-vs-live price gap (the Flat Money #216 shape) — sponsor/judge may contest reachability; confirm the atomicity constraint is actually satisfiable before treating as strong"
  negative:
    - "`amountOutMin`/`minAmountOut` is supplied by the beneficiary (or computed on-chain from a manipulation-resistant reference — a TWAP with a real window, not the same-block spot price) AND a real, tight `deadline` is enforced (reverts if `block.timestamp > deadline`) → likely held; record as a positive control"
    - "the deployment chain has a private mempool / private-orderflow relay AND the loss, even if theoretically nonzero, does not clear Sherlock's 'direct loss, no extensive external condition limitations' High bar → likely held at most Medium/Invalid; do not report as a standalone finding without a quantified loss"

safe_signal:
  proxy: >
    a LOCAL Foundry harness on a pinned mainnet fork, vendoring the REAL, canonical Uniswap V2
    contracts byte-for-byte (never a reimplementation): `Uniswap/v2-periphery` `UniswapV2Router02.sol`
    (the real, always-shipped PROTECTED path — `swapExactTokensForTokens(amountIn, amountOutMin, path,
    to, deadline)` enforces `require(amounts[amounts.length-1] >= amountOutMin, 'UniswapV2Router:
    INSUFFICIENT_OUTPUT_AMOUNT')` and a real `deadline` check) and `Uniswap/v2-core`
    `UniswapV2Pair.swap(amount0Out, amount1Out, to, data)` (the real, low-level UNPROTECTED path — by
    design it takes no `amountOutMin`/`deadline` at all; that enforcement is the periphery's job, so a
    contract that calls the pair directly, or wraps the router with a hardcoded `amountOutMin: 0` /
    `deadline: block.timestamp`, reproduces the exact real-world integrator anti-pattern). Drive a
    front-run/victim-swap/back-run sequence against both paths on the fork: the UNPROTECTED path lets
    the sandwich complete and the victim's realized output falls measurably below the pre-attack quote
    (assert victim_loss > 0). The PATCHED/protected twin — the same victim call routed through
    `UniswapV2Router02` with a real, beneficiary-supplied `amountOutMin` (computed from a
    pre-transaction quote with a normal tolerance) and a tight `deadline` — MUST make the identical
    sandwich sequence revert with `INSUFFICIENT_OUTPUT_AMOUNT` = covered-dry. The benign marker is the
    revert/PnL-assertion on the local disposable fork, not any live effect. The mandatory neg-control
    (fake-client-poc-invariant-check) is the protected-path revert; a fixture that "confirms" loss on
    both paths is tautological. Locally-minted valueless test tokens (or fork-forked real tokens with
    no real value transferred out) only.
  never: >
    never run the sandwich sequence against any live mainnet/testnet mempool, any real MEV
    infrastructure (a real Flashbots bundle, a real searcher/builder relay), or any counterparty you do
    not control — this card never touches a public mempool for real, only a local fork's simulated
    block ordering. A value-extracting demonstration (an actual realized-profit sandwich against a
    funded victim) is a Zone-2 artifact — create only under explicit human impact-escalation
    authorization, contained and logged.

impact_escalation:
  enabled_by: scope.md#impact_demo_authorized
  requires: >
    a benign local invariant-break/PnL assertion (victim_loss > 0 on the unprotected path, == 0 on the
    protected path) needs no per-artifact pause; a value-extracting sandwich PoC against realistically
    funded parties on the local fork is Zone-2 and requires a fresh explicit human confirmation before
    creation
  containment: "local disposable Foundry/Anvil fork only; locally-minted or fork-only valueless test tokens; logged in the fixture cleanup notes and the engagement cleanup ledger"

oracle: [whitebox-analysis, regrade-oracle, pocinator-oracle]
severity_rubric: { permissionless_direct_fund_loss_public_mempool_reproduced: high, same_reproduced_loss_downgraded_on_private_mempool_chain: medium, constrained_external_conditions_or_narrow_atomic_window: medium, bounded_dust_loss_or_static_slippage_cap_effective: low }

procedure:
  - "MAP SWAP/EXECUTION ENTRYPOINTS: every path that trades against an AMM/aggregator/oracle-priced limit order (deposit zaps, harvest/compound, liquidation, rebalance, limit-order fill) — note who calls it and what triggers it (permissionless keeper, user-initiated, cron-style)."
  - "CHECK THE OUTPUT FLOOR: for each entrypoint, is `amountOutMin`/`minAmountOut` hardcoded 0, derived from the same on-chain spot price being protected against, or supplied by a party OTHER than the beneficiary (a keeper, not the depositor)? Any of these means no real floor."
  - "CHECK THE DEADLINE: is `deadline` absent, or set to `block.timestamp` (always 'now')? Either means the call can sit in the mempool / be held for a favorable block indefinitely."
  - "IDENTIFY THE DEPLOYMENT'S MEMPOOL MODEL: does the target chain have a public mempool (Ethereum L1, most L2 sequencers historically) or private mempool / private-orderflow relay? This is the FIRST severity gate per Sherlock's explicit rule — grade accordingly before anything else."
  - "QUANTIFY THE LOSS: reproduce a front-run/victim/back-run (or held-until-favorable-block) sequence on a local fork with the REAL router/pool contracts; compute victim realized output vs the fair pre-attack quote. A 'MEV exists' claim with no quantified victim loss is not a finding."
  - "RUN THE PATCHED/NEGATIVE CONTROL: the same victim call routed through the real router with a beneficiary-supplied `amountOutMin` and a tight `deadline` MUST revert or bound the loss to the stated tolerance = covered-dry. Without this the confirmation is reward-hackable."
  - "GRADE BY REACHABILITY + SHERLOCK'S BAR: permissionless, public-mempool, direct/significant loss with no extensive external-condition limitations = High (Sherlock §VIII). The SAME shape on a private-mempool chain downgrades one notch (High->Medium, Medium->Invalid, per Sherlock's private-mempool rule). An atomic-same-block-execution precondition that is contested/unrealistic caps at Medium (Flat Money #216 precedent) or lower."
  - "SEPARATE 'MEV-SHAPED' FROM 'CODE BUG': if the loss exists only because MEV extraction is generically possible on any public-mempool chain (not because THIS contract omitted a floor it could have enforced), this is a market-structure fact, not a code vulnerability — do not report it as one (see 'Do not overclaim')."

emits: [attempt, finding]
---

## What "confirmed" looks like here

On a local fork with the REAL router/pool contracts: a reproduced front-run/victim-swap/back-run (or
held-transaction) sequence through the in-scope contract's actual unprotected path shows a quantified
victim value loss (an assertion, not a console marker) versus the fair pre-attack quote, AND a passing
negative control — the same call routed with a real beneficiary-supplied `amountOutMin` and a tight
`deadline` reverts or bounds the loss to the stated tolerance. Missing the neg-control makes the
confirmation reward-hackable and routes to `needs_rework` at pocinator. The severity is then set by the
deployment's actual mempool model (public vs private) and by whether the loss clears Sherlock's "direct
loss, no extensive external condition limitations" bar — not by "a sandwich is theoretically possible."

## Real disclosed anchors for this class (verified, cited — B1)

- **Sherlock Flat Money contest judging, Issue #216 (2023-12-flatmoney) — Medium, post-escalation.**
  A same-block Pyth-price-arbitrage-on-limit-orders report: contest-time judge takarez marked it
  invalid; escalators 0xLogos and xiaoming9090 argued Medium given execution constraints; sponsor-side
  shaka0x countered the attack requires atomic execution within tight constraints. Final judged
  disposition: Medium. This is the corpus's sole worked `slippage-MEV` case (class count = 1 —
  thinly represented; treat as one worked precedent, not a distribution) and the direct analog for a
  contested, execution-constrained variant of this card.
- **Sherlock judging criteria — private-mempool downgrade rule (verbatim doctrine, not a single case).**
  "Issues that depend on front-running will get their severity downgraded if the deployment chain has
  a private mempool. High will be Medium, and Medium will be Invalid." A standard front-run/slippage
  issue that would be High on a public-mempool chain (e.g. Ethereum mainnet) is Medium on a
  private-mempool chain (e.g. Optimism); reports must also explain how the front-run happens
  unintentionally, not just assert "the attacker could front-run."
- **Sherlock judging criteria §VIII (verbatim doctrine).** "Slippage related issues showing a direct
  loss of funds with a detailed explanation... can be considered valid high" — the affirmative bar this
  card's High tier targets: a quantified, direct loss, not a hypothetical MEV-extraction narrative.
- **C4 2023-04-rubicon Issue #558 — downgraded to QA (real precondition-unreachable precedent).**
  Judge HickupHH3: "Downgrading to QA because front-running on L2s isn't possible, which this vuln
  relies on." A griefing/front-run finding whose precondition (a public, front-runnable mempool)
  provably did not hold on the target L2 — the direct negative-signal analog of the private-mempool
  downgrade rule, from a different platform (C4, not Sherlock).

## Grounding: severity + realized impact (B1 corpus; B2 explicitly declines this class)

- **B1 (`defi-contest-adjudication-corpus.md`)** grades this class by (1) the deployment's mempool
  model — public vs private, per Sherlock's explicit downgrade rule — and (2) whether the loss is
  direct/significant per Sherlock §VIII/§V/§IV, or constrained by external conditions/an atomicity
  requirement a sponsor can credibly dispute (Flat Money #216: Medium, not High, precisely because the
  attack needed a contested same-block execution window). There is no worked Critical/High
  `slippage-MEV` row in the corpus — grade this class High only when the loss is direct, quantified,
  and unconstrained on a confirmed public-mempool deployment; do not default to High on mechanism alone.
- **B2 (`defi-exploit-chain-corpus.md`) explicitly excludes this class from realized-exploit grounding**:
  "MEV/sandwich and algorithmic-stablecoin-depeg chains remain absent — out of scope for the
  realized-code-exploit lens (MEV is not a code bug; depegs are usually economic, not a single
  exploitable tx)." There is no B2 anchor for this card — say so honestly rather than borrow an
  unrelated realized-loss figure. The severity_rubric above is grounded in B1 only.

## Not this card

- Generic MEV extraction that exists on any public-mempool chain regardless of what the in-scope
  contract does (arbitrage between two public pools, ordinary transaction-ordering value that no
  contract-level check could prevent) — this is market structure, not a code vulnerability; do not
  file it as a finding on this card.
- A front-run of an `initialize()` or other action with no irreversible damage — Sherlock §VII rules
  this invalid regardless of impact narrative (see `evm.access-control`); this card is about swap-path
  value loss, not init races.
- A front-run/slippage precondition that does not hold in the actual deployment (a private mempool /
  private-orderflow relay, or an L2 where front-running the specific mempool step is not possible, per
  the Rubicon #558 precedent) → downgrade per the Sherlock rule or treat as invalid; do not report the
  public-mempool-chain severity against a private-mempool deployment.
- A static/config-percentage slippage bound that is tight enough to cap the loss below Sherlock's
  "significant loss" thresholds (>1%/>$10 principal for High; >0.01%/>$10 for Medium) → not a finding
  at that bound; only the gap between the bound and a realistic execution-time move matters.

## Do not overclaim

- A missing/zero `amountOutMin` or a `deadline` set to `block.timestamp` is an activation signal, not a
  finding — reproduce a quantified victim loss on a local fork through the sandwich/held-transaction
  sequence, with a passing protected-path neg-control.
- Always check the deployment's actual mempool model FIRST. The identical code pattern is a different
  severity tier (High vs Medium vs Invalid) purely as a function of public vs private mempool per
  Sherlock's rule — grading by mechanism alone before checking this is the single most common
  overclaim for this class.
- This class caps at High absent a chained escalation into a larger, unbounded loss (e.g. the sandwich
  desyncs an oracle/accounting invariant consumed elsewhere) — that composition, if present, belongs to
  chainability (`engine/chainability.md` §3b), not a standalone Critical claim on this card.
- "A sandwich/front-run is theoretically possible" is not itself a vulnerability report — per B2's own
  scoping note, MEV-per-se is often not a code bug; the reportable claim is specifically that THIS
  contract omitted an output floor or deadline it could have enforced, with a quantified resulting loss.
