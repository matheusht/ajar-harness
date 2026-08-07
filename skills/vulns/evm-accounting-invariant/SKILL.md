---
id: evm.accounting-invariant
name: EVM Accounting / Ledger-Conservation Invariant Break
description: >
  Prove that a protocol's OWN internal ledger (a recorded-balance/reserve variable, a fee/reward
  accumulator, a high-water-mark, a debt/solvency flag) diverges from the real value it is supposed to
  represent — because it trusts a NOMINAL amount instead of a MEASURED balance delta (deflationary /
  fee-on-transfer / rebasing tokens), updates only on a partial/conditional transition and silently
  drops the rest (a fee/reward bookkeeping gap), or can be credited twice through two independent code
  paths (double-count) — breaking a conservation invariant the protocol depends on (sum(withdrawable)
  <= real backing; fees/rewards owed == fees/rewards ever collectable; no unit of value credited on
  more than one ledger path). This is NOT reentrancy (the desync here is a steady-state bookkeeping
  defect, not a mid-call re-entry window) and NOT a pure rounding-direction bug (the defect is which
  ledger update happened or didn't, not which way a division truncated). A ledger update that trusts a
  nominal amount or updates conditionally is an activation signal; a finding requires a reproduced
  divergence that breaks the protocol's own conservation invariant on a real fork, with a passing
  patched-twin negative control.
type: vuln
owasp: "No single SWC id — the accounting/conservation-invariant class; adjacent to SWC-101 (arithmetic) but the defect is bookkeeping logic, not the operator. CWE-682 (Incorrect Calculation), CWE-840 (Business Logic Errors), CWE-1023 (Incomplete Comparison with Missing Factors). Not an OWASP-web category — EVM smart-contract class."
atlas: "—"
patterns: []

activation:
  strong:
    - "an internal ledger/reserve/recorded-balance state variable (recordedBalance, reserve[token], totalDeposited, _records[token].balance) is written using the NOMINAL amount passed to a transfer/transferFrom call rather than a MEASURED balance delta (token.balanceOf(this) before vs after) — so a fee-on-transfer, deflationary, or rebasing token silently desyncs the ledger from the real balance the contract can actually pay out (the exact Balancer STA/STONK shape: swap accounting updated by nominal amount, not amount actually received)"
    - "a fee/reward accumulator or high-water-mark (navPerShareHighMark, rewardPerTokenStored, a cumulative index) updates ONLY on one specific conditional transition (e.g. 'bump the high-water-mark only when NAV rises past the prior mark') so a SUBSEQUENT occurrence of the same transition is silently un-counted, permanently losing fee/reward revenue the protocol is owed (the Tokemak #661 shape: fee collected on the first NAV rise past a mark, the second rise past a stale mark is never counted)"
    - "a payout/claim path silently caps at the currently-available balance with NO bookkeeping of the shortfall (claimRewards() pays min(owed, available) and forgets the difference) — so total value ever claimable across all users can exceed what was ever funded, breaking sum(claims paid) <= sum(value ever funded) (the Ajna RewardsManager #251/H-08 shape)"
    - "the same underlying unit of value can be credited to the ledger through two INDEPENDENT code paths (a deposit both queued into a pending-state total AND immediately reflected in totalAssets(); a position write-off that reduces one account's debt but is separately re-added to protocol reserves) — a double-count that lets sum(user-credited value) exceed the real backing the contract holds"
  weak:
    - "a nominal-vs-measured transfer accounting gap exists, but every token the contract accepts is a fixed, known-standard ERC20 with no transfer fee/rebase and no attacker-controlled listing path — confirm a fee-on-transfer/deflationary/rebasing token is actually depositable/listable before treating as strong"
    - "a conditional accumulator update exists, but the skipped transition is provably unreachable or economically irrelevant under the protocol's own bounds — confirm the skipped case is reachable with a real economic incentive (not just a code-reading curiosity) before treating as strong"
    - "a partial/limited-scope accounting design is present (e.g. principal-only debt tracking with interest handled elsewhere) — this MAY be an intentional, README-declared design choice rather than a bug; check the docs for a declared invariant before flagging (the Union Finance #124 precedent: a Watson-escalated 'borrower avoids interest' claim was rejected because principal/interest separation was the explicit documented design, not an oversight — judged Low, essentially a non-issue)"
  negative:
    - "every credit to an internal ledger is sourced by a MEASURED balance delta (balanceOf(this) before/after), for every accepted token including any fee-on-transfer/rebasing path -> likely held; record as a positive control"
    - "accumulators/high-water-marks are recomputed unconditionally against current state on every relevant call (not gated on a one-time transition), and any payout shortfall is tracked/carried forward rather than silently dropped -> likely held"
    - "every credit path is single-sourced (no state can be double-counted across two independent update paths) AND the protocol's own README/docs declare the exact accounting scope with no contradiction from the code -> likely held; record as a positive control (Union Finance #124 precedent: declared partial-scope accounting judged not a bug)"

safe_signal:
  proxy: >
    a LOCAL Foundry harness built from REAL contracts at pinned refs (never a reimplementation), that
    observably BREAKS the protocol's own conservation invariant pre-fix and HOLDS it post-fix — the
    mandatory patched-twin negative control (a fixture that "confirms" against both refs is
    tautological, fake-client-poc-invariant-check). Two PLANNED fixtures (tracked follow-up, not yet
    shipped; follow the shipped `evals/contract-audit/fixtures/jpegd-reentrancy/` pattern of vendoring
    the real contract byte-for-byte at both refs):
    (1) **reward/fee-bookkeeping shortfall shape** — `ajna-finance/ajna-core`, vulnerable ref pinned at
    the 2023-05-ajna Code4rena contest snapshot (`RewardsManager.claimRewards()` silently caps payout
    at the current AJNA balance with no shortfall bookkeeping — canonical issue #251/H-08, judge
    Picodes raised severity to High, sponsor MikeHathaway confirmed); patched ref pinned at ajna-core's
    post-contest mitigation-review commit (C4 contests routinely run a public mitigation-review after
    the main audit; exact SHA to confirm from the public repo at fixture-build time, not fabricated
    here). Assertion: sum(claims paid across stakers) <= sum(AJNA ever funded to the RewardsManager) —
    breaks pre-fix (a later claimant is permanently short-paid, the shortfall never carried forward),
    holds post-fix.
    (2) **deflationary/fee-on-transfer ledger-desync shape** — `balancer-labs/balancer-core`,
    vulnerable ref pinned at the `BPool.sol` commit live during the Jun 2020 STA/STONK pool drain
    (real, on-chain, $523,616.52 realized loss, B2-anchored). V1 pools are immutable so there is no
    in-place historical patch commit; the patched twin applies the corrected-accounting version
    (credit the internal balance record by the MEASURED `balanceOf(this)` before/after delta instead
    of the nominal swap amount) — the same allowance the sibling `evals/contract-audit` rounding
    fixtures use ("the fix commit, or the round-direction flipped / bounds added"). Assertion: the
    pool's real recoverable STA/STONK balance never diverges from its internal balance record across a
    driven repeated-swap sequence — breaks pre-fix, holds post-fix.
    Neither fixture is shipped yet — do not claim a `confirmed` finding against this card until the
    relevant fixture exists and its negative control passes.
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
severity_rubric: { permissionless_ledger_or_solvency_invariant_break_fund_drain_reproduced: critical, reward_or_fee_bookkeeping_error_permanent_shortfall_or_overpay_reproduced: high, gated_or_protocol_side_revenue_loss_no_permissionless_user_drain: medium, declared_partial_accounting_design_or_dust_drift_no_invariant_break: low }

procedure:
  - "MAP THE LEDGER: enumerate every state variable that represents 'how much value the protocol believes it holds or owes' (recordedBalance, totalDeposited, exchangeRate, rewardPerTokenStored, navPerShareHighMark, totalDebt) and the events that should update it (deposit/withdraw/swap/fee-collect/reward-accrue/liquidation/write-off)."
  - "TRACE NOMINAL VS MEASURED: for each ledger write tied to a token transfer, determine whether it trusts the NOMINAL amount (the caller-supplied or pre-transfer amount) or a MEASURED amount (balanceOf-before/after delta). Fee-on-transfer, deflationary, and rebasing tokens break nominal-trusting ledgers."
  - "CHECK FOR CONDITIONAL/PARTIAL ACCUMULATOR UPDATES: does an accumulator/high-water-mark/index update ONLY on a specific transition (e.g. 'only when NAV increases') such that a subsequent occurrence of the same transition is silently skipped or uncounted? (the Tokemak #661 shape)."
  - "CHECK FOR DUAL-CREDIT PATHS: can the same underlying value be credited to the ledger via two independent code paths (queued+immediate, claim+re-pool, write-off+re-add-to-reserves) such that sum(credited) can exceed sum(value actually backing it)?"
  - "DISTINGUISH DESIGN CHOICE FROM BUG: read the README/docs for a DECLARED accounting scope (e.g. 'interest is not part of principal write-off') before flagging — a documented partial-accounting design is not a break (Union Finance #124 precedent: ruled Low/non-issue because the separation was an explicit, intentional design, not an oversight)."
  - "PIN THE INVARIANT: state the protocol's OWN conservation invariant the defect breaks, in one sentence (sum(withdrawable) <= real token balance held; fee/reward accrued == fee/reward owed on the declared basis; no unit of value credited on more than one ledger path). This is the confirm-on-fork assertion, not a printed marker (whitebox-analysis §4)."
  - "REPRODUCE ON A LOCAL FORK WITH THE REAL CONTRACT: build a Foundry harness vendoring the real contract at the pinned in-scope commit; drive the sequence (repeated fee-on-transfer swaps, the two-step conditional-transition sequence, or the dual-credit path); assert the invariant breaks (ledger diverges from real balance, fee/reward owed exceeds fee/reward ever collectable, or sum(credited) exceeds backing). Never a reimplementation of the vulnerable logic."
  - "RUN THE PATCHED/NEGATIVE CONTROL: the same harness against the fixed/mitigated version MUST yield covered-dry — the invariant holds. Without a passing neg-control the confirmation is reward-hackable (fake-client-poc-invariant-check)."
  - "TRACE REACHABILITY: who can trigger the divergence — a permissionless depositor/swapper, or a gated admin-only fee-sweep/keeper-only accrual? A permissionless path with real fund loss is critical/high; a gated or protocol-side-only revenue loss caps severity at medium (the Tokemak #661 precedent: PROTOCOL loses fee revenue, no user fund drain, judged Medium not High)."
  - "CHECK RELEASE ELIGIBILITY: confirm the exact pinned in-scope commit still has the gap (a fix already merged and released takes the disclosed instance out of scope — cite it as precedent, not a live finding)."

emits: [attempt, finding]
---

## What "confirmed" looks like here

A `confirmed` accounting-invariant finding shows, on a local fork running the REAL in-scope contract:
(1) a one-sentence statement of the protocol's OWN conservation invariant, (2) a reproduced sequence
(repeated fee-on-transfer swaps, a two-step conditional-transition trigger, or a dual-credit path)
that breaks it via an assertion failure — the ledger diverges from real balance, a fee/reward owed
exceeds what remains collectable, or sum(credited) exceeds backing — not a console marker, and (3) a
passing negative control (the patched/corrected-accounting version yields covered-dry). Missing (3)
routes to `needs_rework` at pocinator. A defect that only shows up as a printed "would have lost X" or
a static-analysis hit on a nominal-amount write, with no reproduced on-fork divergence, is `weak`
activation, not a finding.

## Real disclosed anchors for this class (verified, cited)

- **Balancer Finance — deflationary-token (STA/STONK) pool drain, Jun 2020 (realized, $523,616.52).**
  A dYdX flash-loan of 104,331 WETH funded a repeated back-and-forth WETH<->STA swap inside a Balancer
  pool. STA/STONK charge a 1% transfer fee, so each swap delivered less than the nominal amount
  Balancer's swap accounting recorded — the pool's internal balance record stayed at pre-fee nominal
  values while the pool's REAL STA balance drained toward zero. The attacker called `gulp()` to resync
  the internal record down to the near-zero actual balance, permanently skewing the pool's price
  curve, then drained the other pooled asset at the skewed rate. Root cause (PeckShield): "Balancer's
  swap accounting updated internal token balances by the nominal transferred amount instead of the
  amount actually received." This is the class's flagship deflationary/fee-on-transfer ledger-desync
  shape and the intended fixture-2 vulnerable ref (V1 pools are immutable, so the fixture's patched
  twin is the corrected-accounting version, not a historical in-place patch — see `safe_signal.proxy`).
- **Ajna Protocol — RewardsManager underfunded-claim loss, Code4rena #251/H-08 (2023-05, judged High,
  sponsor confirmed).** `claimRewards()` silently capped payout at the RewardsManager's current AJNA
  balance with no bookkeeping of the shortfall, permanently losing rewards for any staker unlucky
  enough to claim while the contract was underfunded. Judge Picodes explicitly raised severity to
  High; 24 duplicate submissions merged into the canonical issue. This is the class's flagship
  fee/reward-bookkeeping-gap shape and the intended fixture-1 vulnerable ref.

## Grounding: severity + realized impact (B1 / B2 corpora)

- **B1 (`skills/oracles/references/defi-contest-adjudication-corpus.md`)** — `accounting` is a
  7-row worked class (matches the corpus's own class-distribution count) spanning Critical down to
  Low by reachability/impact, not mechanism alone: **Critical** (Immunefi, platform-assessed) — Aurora
  Engine's DELEGATECALL handling credited the Aurora-side balance without verifying ETH was actually
  transferred, letting an attacker mint ETH and drain the nested nETH pool (~70k ETH / ~$200M capped).
  **High** — 88mph (Immunefi: `vestRewardPerTokenPaid` not updated at deposit, over-claim of
  `rewardPerToken`); Pods Finance (Immunefi: `unmintWithRewards()` let any minter repeatedly claim
  rewards owed to other users); C4 Ajna #251/H-08 (above); C4 Reserve-findings #310/H-01 (a
  rounding-nudged cToken redemption unconditionally disabled a collateral plugin, chaining accounting
  + a hard-coded price-only-increases assumption). **Medium** — Sherlock Tokemak #661
  (`navPerShareHighMark` bumped only on the specific NAV-rise transition that first crosses it; a
  SUBSEQUENT rise past a now-stale mark is never counted, permanently losing PROTOCOL fee revenue —
  contest-time marked invalid, escalated by Watson xiaoming9090 for High, judged Medium: protocol-side
  revenue loss, not user fund drain, caps the tier). **Low** — Sherlock Union Finance #124
  (`debtWriteOff()` is an explicit PRINCIPAL-only write-off; Watson ctf-sec escalated arguing borrowers
  "escape interest," senior judge hyh/Evert0x rejected — the accounting scope was declared design, not
  a bug). The Union/Tokemak pair is the card's central calibration signal: same `accounting` class,
  same platform, one ruled essentially a non-issue (declared design) and the other a real but
  bounded/protocol-side gap — grounds the `activation.weak`/`negative` "design choice vs bug" split.
- **B2 (`skills/oracles/references/defi-exploit-chain-corpus.md`)** — `logic-accounting` is a 4-row
  realized class (matches the corpus's own rollup count): Balancer STA/STONK (above, $523,616.52,
  permissionless AMM); **Euler Finance (Mar 2023, $197,000,000, largest DeFi hack of 2023)** —
  `donateToReserves()` had no insolvency check, letting an attacker push their own leveraged position
  underwater on purpose and then profitably self-liquidate it, a permissionless solvency-invariant
  break; **Platypus Finance (Feb 2023, ~$8.5M realized profit)** — `emergencyWithdraw()`'s solvency
  check read only a boolean `Solvent` flag and ignored the actual outstanding debt amount, letting an
  under-collateralized position withdraw as if solvent; **Sperax USDs (Feb 2023, ~309,000 USDs)** — a
  rebasing-migration function set `nonRebaseCreditsPerToken` to 1 prematurely for a not-yet-deployed
  Safe address, corrupting `balanceOf()`. Euler and Platypus anchor the `critical` rubric tier
  (permissionless, real fund loss, a solvency/ledger invariant broken outright); Balancer anchors the
  `critical`/`high` boundary depending on scale; Sperax is a smaller-scale but still-permissionless
  realized instance. **Coverage note (honesty, not fabrication):** neither corpus file contains a
  Penpie/reward-accounting-reentrancy row — a targeted grep of both files for "penpie"/"magpie" found
  no match, so no such incident is cited here as corpus-grounded; the fee/reward-bookkeeping tier is
  instead anchored on the real, corpus-present Ajna #251/H-08 (B1) and Tokemak #661 (B1) rows above. A
  reward-accounting-reentrancy shape that hinges on a mid-call re-entry window belongs primarily to
  `evm-reentrancy`/`evm-read-only-reentrancy-price`, not this card (see "Not this card").

## Not this card

- A ledger desync caused by a mid-call RE-ENTRY (a control-giving external call before the ledger
  write finishes) is `evm-reentrancy` (single/cross-function) or `evm-read-only-reentrancy-price`
  (a stale desynced value consumed by a price/valuation read) — this card is for a STEADY-STATE
  bookkeeping defect (nominal-vs-measured, conditional-update, dual-credit), not a reentrancy window.
  The Sturdy/Blueberry/Sentiment read-only-reentrancy chains corrupt accounting too, but the mechanism
  is the reentrant call, and they belong to that sibling card.
- A pure rounding-DIRECTION or precision-loss defect (which way a division/mulDiv truncates) with no
  conditional-update or nominal-vs-measured gap is `evm-arithmetic-rounding`, even when the visible
  symptom is an accounting number being off — the fix there is a rounding direction, not a bookkeeping
  rule.
- An empty-vault/first-depositor donation attack on share pricing is `evm-first-depositor-share-
  inflation` — the mechanism (donate to inflate assets-per-share at a manipulable totalSupply) is
  specific enough to own its own card even though it is also, at root, a ledger-vs-balance issue.
- A declared, README-consistent partial-accounting design (principal-only tracking, interest handled
  elsewhere) is not a finding — see the Union Finance #124 precedent; confirm against the docs before
  flagging.

## Do not overclaim

- A nominal-vs-measured transfer-accounting gap, a conditional accumulator update, or a dual-credit
  code path is `activation` only — you must reproduce an actual invariant-breaking divergence on a
  local fork with the real contract, with a passing patched-twin neg-control, before calling it a
  finding.
- Severity tracks WHO can trigger the divergence and WHO bears the loss, not just the mechanism: a
  permissionless path with real user fund loss is critical/high (Euler, Platypus, Balancer STA); a
  gated or protocol-side-only revenue loss (Tokemak #661: the PROTOCOL loses fee income, not users)
  caps at medium; a declared partial-scope design with no contradicted invariant (Union Finance #124)
  is not a finding at all.
- The B2 anchors' "$" figures are the primary post-mortem's realized-loss / attacker-profit figures,
  not a generic TVL-at-risk estimate — state that distinction in any report, per the reentrancy card's
  same caveat.
- Both `safe_signal.proxy` fixtures in this card are PLANNED, not shipped — do not claim `confirmed`
  against this card's mechanism until the relevant fixture exists locally and its negative control
  demonstrably passes; an activation-only finding stays `needs_review`.
