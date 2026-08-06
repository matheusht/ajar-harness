---
id: evm.arithmetic-rounding
name: EVM Arithmetic — Rounding / Precision-Loss / Overflow Value Extraction
description: >
  Prove that a rounding direction, a precision-loss in fixed-point/decimal math, or an unchecked
  overflow/truncation lets an attacker extract value or corrupt accounting: division that rounds in the
  attacker's favor (mint rounds up / burn rounds down), an accumulator/index that can be inflated then
  read at a favorable truncation, a `mulDiv`/exponent step that loses precision on attacker-sized
  inputs, or a silent `unchecked`/cast wraparound (Solidity <0.8 or an explicit `unchecked{}`/shift)
  that mints or mis-prices. The specific bug is directional: which side of the rounding the protocol
  eats, and whether the attacker can amplify it. A rounding remark is an activation signal; a finding
  requires a reproduced net extraction (or a broken accounting invariant) the corrected math prevents.
type: vuln
owasp: "SWC-101 (Integer Overflow/Underflow); CWE-190 (Overflow), CWE-681 (Incorrect Conversion), CWE-1339 (rounding). EVM smart-contract class."
atlas: "—"
patterns: []

activation:
  strong:
    - "a value the attacker controls (deposit/withdraw amount, share/asset ratio, a tick/range parameter) flows into a division/mulDiv/exponent where the rounding DIRECTION favors the caller (mint rounds up, or withdraw/burn rounds the protocol's payout up) — and can be repeated to amplify dust into a real amount"
    - "an accumulator / index / exchange-rate (lending_accumulator, rewardPerToken, compound-style exchangeRate) can be inflated (donation, empty-market, or a self-transfer) and then read at a SafeMath/truncation step so `withdrawable = deposit * inflated / base` yields more than deposited (the zkLend shape)"
    - "an `unchecked{}` block, a narrowing cast (uint256->uint128/uint112), or a bit-shift (`checked_shlw`/`<<`) can wrap/overflow on an attacker-supplied degenerate input, minting liquidity/shares/tokens from near-zero (the Cetus shape) — or Solidity <0.8 arithmetic with no SafeMath"
  weak:
    - "a rounding exists but always favors the PROTOCOL (mint rounds down, withdraw rounds down) — the safe direction; confirm the direction and amplifiability before treating as strong"
    - "precision loss exists but is dust-bounded and non-amplifiable (rounds to <1 wei per op, no repetition path) → weak/QA"
  negative:
    - "every rounding favors the protocol, mulDiv uses a correct round-direction per call site, casts are range-checked, and `unchecked`/shift inputs are bounded so no wrap is reachable → likely held; record as a positive control"
    - "the loss is dust and non-amplifiable (Sherlock/C4 treat marginal rounding/dust as QA/Low) → not a finding"

safe_signal:
  proxy: >
    a LOCAL Foundry harness with the REAL contract at a pinned ref (never a reimplementation): the
    attacker drives the rounding/overflow path and ends able to withdraw/redeem MORE than deposited, or
    mints value from near-zero — the conservation invariant (`sum(withdrawable) <= sum(deposited) + yield`)
    breaks. The corrected-math version (the fix commit, or the round-direction flipped / bounds added)
    makes the same sequence conserve = covered-dry. Planned fixture: a Code4rena/Sherlock rounding or
    overflow finding with a public vulnerable commit + fix (e.g. an accumulator/precision case), vendored
    byte-for-byte like `evals/contract-audit/fixtures/jpegd-reentrancy/`; assertion is attacker PnL > 0 /
    invariant break pre-fix and conserved post-fix.
  never: >
    never run against any live deployment; local fork/EVM only, valueless test tokens. A value-extracting
    demonstration is a Zone-2 artifact — create only under explicit human impact-escalation authorization,
    contained and logged.

impact_escalation:
  enabled_by: scope.md#impact_demo_authorized
  requires: >
    a benign local invariant/PnL assertion needs no per-artifact pause; a value-extracting drain PoC is
    Zone-2 and requires a fresh explicit human confirmation before creation
  containment: "local disposable Foundry/EVM only; locally-minted valueless test tokens; logged in the fixture cleanup notes and the engagement cleanup ledger"

oracle: [whitebox-analysis, regrade-oracle, pocinator-oracle]
severity_rubric: { amplifiable_rounding_or_overflow_drain_reproduced: high, bounded_or_seed_gated_extraction: medium, dust_only_non_amplifiable_precision_loss: low }

procedure:
  - "FIND THE MATH SINK: locate divisions/mulDiv/exponent/cast/shift/unchecked steps on attacker-influenced values; for each, determine the ROUNDING DIRECTION (who eats the remainder) and whether an overflow/truncation is reachable."
  - "CHECK AMPLIFIABILITY: can a favorable rounding be repeated (loop, many small ops) to turn dust into a real amount, or an accumulator inflated then read at a truncation? A single sub-wei rounding is QA; an amplifiable one is a finding."
  - "READ THE LIBRARY'S ROUND CONTRACT: for mulDiv/FullMath/decimal libs, confirm the actual rounding mode at THIS call site (round-up vs round-down) — the bug is usually a wrong direction, not the absence of a library."
  - "PIN THE INVARIANT: value conservation at a 1:1 no-yield rate (sum(withdrawable) <= sum(deposited)); or 'liquidity/shares minted match value in'. This is the confirm assertion."
  - "REPRODUCE ON A FORK WITH REAL CODE: drive the path; assert the attacker withdraws more than deposited / mints from near-zero (invariant break)."
  - "RUN THE NEGATIVE CONTROL: the corrected-math version (fix commit, flipped direction, or bounds added) MUST conserve = covered-dry."
  - "GRADE: an amplifiable drain is High; a seed/precondition-gated or dust-bounded case is Medium/QA (C4/Sherlock treat marginal rounding as QA)."

emits: [attempt, finding]
---

## What "confirmed" looks like here

On a fork with the REAL contract: the attacker drives the rounding/overflow path and can withdraw more
than deposited (or mint from near-zero), asserted as a value-conservation invariant break with attacker
PnL > 0, and a passing neg-control where the corrected math conserves.

## Real disclosed anchors for this class (verified, cited — B1/B2)

- **C4 Juicebox #191 (H-04).** A "no token minted yet? round up to 1" special-case let a project owner
  mint a reserve token and drain a first contributor — a rounding-direction bug; judge upgraded QA/Gas
  to High.
- **Sherlock Ajna #18.** A `_bpf` function deviated from spec (returned 0 where it should equal
  bondFactor), costing the kicker all auction rewards — precision/spec rounding, escalation-resolved.
- **B2 realized:** zkLend ($9.57M, Feb 2025) — flash-loan-inflated `lending_accumulator` + SafeMath
  truncation on withdrawal let ~4.069 wstETH be withdrawn as ~6.103; Cetus ($223M, May 2025) — a silent
  `checked_shlw` 256-bit shift overflow minted ~10^34 liquidity from a 1-token deposit.

## Grounding: severity + the dust boundary (B1)

B1 is explicit that **marginal rounding / dust loss is QA/Low** (C4 "loss of dust amounts … are
QA/Low"); the finding requires an **amplifiable** extraction (repeatable, or accumulator-inflatable).
The zkLend/Cetus realized cases anchor the High/amplifiable tier; grade non-amplifiable precision loss
as QA.

## Not this card
- Rounding that always favors the protocol → the safe direction; not a finding.
- Sub-wei, non-amplifiable precision loss → QA/Low per the B1 dust boundary.

## Do not overclaim
- A rounding remark is an activation signal, not a finding — reproduce an amplifiable net extraction with
  a passing corrected-math neg-control.
- State the amplification path explicitly (how dust becomes a real amount); an unamplifiable rounding is
  QA, not a drain.
