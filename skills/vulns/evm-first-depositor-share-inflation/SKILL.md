---
id: evm.first-depositor-share-inflation
name: EVM First-Depositor / ERC-4626 Share-Price Inflation (Donation Attack)
description: >
  Prove that an attacker who is (or front-runs) the FIRST depositor into a share-based vault
  (ERC-4626 or a Compound/Aave-fork cToken/market) can mint a negligible number of shares, then
  transfer assets DIRECTLY into the vault (a "donation", bypassing the deposit accounting) to inflate
  assets-per-share, so the next honest depositor's shares round DOWN toward zero and the attacker
  redeems a disproportionate share of the victim's deposit. The read is the exchange rate; the flaw is
  that price-per-share is movable by a raw transfer while share issuance rounds against the depositor.
  An empty-market listing is an activation signal; a finding requires a reproduced net attacker profit
  (victim loss) that the mitigated version prevents.
type: vuln
owasp: "No SWC id — the ERC-4626 inflation/donation class; CWE-682 (Incorrect Calculation), CWE-1339 (rounding). EVM smart-contract class."
atlas: "—"
patterns: []

activation:
  strong:
    - "a vault computes `shares = assets * totalSupply / totalAssets` (or a cToken exchange rate = cash/supply) where `totalAssets`/cash is `token.balanceOf(this)` — so a direct transfer INTO the vault inflates the rate without minting shares, and the first depositor can set totalSupply to 1 wei"
    - "a newly listed market/vault starts at zero/near-zero total supply AND is immediately usable as collateral / by other depositors (a live collateral factor, or a public deposit) with no minimum-liquidity / dead-shares / virtual-shares protection"
    - "share issuance rounds DOWN (floor) with no `+1`/virtual-offset cushion, so an inflated rate makes a normal deposit mint 0 shares"
  weak:
    - "an ERC-4626 vault with OpenZeppelin >= 4.9 virtual-shares/`_decimalsOffset` mitigation, or a seeded initial deposit / dead-shares burn — the donation still moves the rate but the attack is bounded/unprofitable; confirm profitability before treating as strong"
    - "the vault is empty but not yet reachable by any victim (no live collateral factor, no other depositor path) → weak until a victim path opens"
  negative:
    - "the vault mints virtual shares / uses a decimals-offset (OZ 4.9+), burns dead shares to address(0) on first deposit, seeds a permanent minimum liquidity, or values assets by internal accounting not `balanceOf` → likely held; record as a positive control"
    - "totalSupply can never be driven to a manipulable-small value (a mandatory seed at deploy) → held"

safe_signal:
  proxy: >
    a LOCAL Foundry harness with the REAL vault code at a pinned ref (never a reimplementation): the
    attacker mints 1 share, donates a large amount, an honest depositor deposits and receives near-zero
    shares, and the attacker redeems for a net PROFIT (victim LOSS) — the fair-share invariant
    (`no depositor loses value at a 1:1, no-yield rate`) breaks. The PATCHED/mitigated version (virtual
    shares / dead shares / seed) makes attacker PnL <= 0 = covered-dry. Planned fixture: OpenZeppelin
    ERC-4626 at v4.8.x (pre-mitigation, vulnerable) vs v4.9.x (virtual-shares mitigation) — a real,
    canonical before/after, vendored byte-for-byte like `evals/contract-audit/fixtures/jpegd-reentrancy/`;
    the assertion is attacker PnL > 0 on 4.8 and <= 0 on 4.9.
  never: >
    never run the sequence against any live deployment; local fork/EVM only, valueless test tokens. A
    value-extracting demonstration is a Zone-2 artifact — create only under explicit human
    impact-escalation authorization, contained and logged.

impact_escalation:
  enabled_by: scope.md#impact_demo_authorized
  requires: >
    a benign local invariant-break/PnL assertion needs no per-artifact pause; a value-extracting drain
    PoC is Zone-2 and requires a fresh explicit human confirmation before creation
  containment: "local disposable Foundry/EVM only; locally-minted valueless test tokens; logged in the fixture cleanup notes and the engagement cleanup ledger"

oracle: [whitebox-analysis, regrade-oracle, pocinator-oracle]
severity_rubric: { permissionless_first_depositor_drain_of_next_depositors_reproduced: high, bounded_dust_loss_or_seed_required: medium, mitigated_attack_unprofitable: low }

procedure:
  - "FIND THE SHARE MATH + THE ASSET SOURCE: locate the share issuance formula and confirm `totalAssets`/cash is `token.balanceOf(this)` (donatable) rather than an internal ledger."
  - "CONFIRM THE EMPTY-MARKET WINDOW: can totalSupply be driven to 1 wei by the attacker (first depositor / newly listed market), and is the vault reachable by a victim (public deposit, or a live collateral factor)?"
  - "CHECK FOR MITIGATION: virtual shares/decimals-offset (OZ 4.9+), dead-shares burn, a mandatory seed, or internal accounting. Any of these usually caps the attack — confirm which is present at the pinned ref."
  - "PIN THE INVARIANT: no depositor loses value at a 1:1, no-yield exchange rate; attacker net PnL <= 0. This is the confirm assertion."
  - "REPRODUCE ON A FORK WITH REAL CODE: attacker mints 1 share, donates, honest deposits, attacker redeems; assert attacker PnL > 0 / honest shortfall."
  - "RUN THE NEGATIVE CONTROL: the mitigated version makes the same sequence yield attacker PnL <= 0 = covered-dry."
  - "GRADE BY REACHABILITY: permissionless first-depositor with real next-depositor loss is High (GoGoPool/Kelp precedent); a seed-required or dust-only variant is Medium (Smilee epoch-gated)."

emits: [attempt, finding]
---

## What "confirmed" looks like here

On a fork with the REAL vault code: attacker mints ~1 share, donates, an honest depositor's shares
round toward zero, and the attacker redeems for a net profit — asserted as attacker PnL > 0 (victim
loss), with a passing neg-control where the mitigated version yields PnL <= 0.

## Real disclosed anchors for this class (verified, cited — B1/B2)

- **C4 GoGoPool #209 (H-05) / Kelp #42 (H-03) / BakerFi H-02.** First-depositor ERC-4626 inflation via
  donation — judged High (permissionless, real next-depositor loss); Kelp's judge overruled a sponsor
  downgrade twice ("potential loss of funds is present").
- **Sherlock Napier #125 / Smilee #22.** ERC-4626 donation inflation (Napier High; Smilee Medium,
  epoch-gated — the reachability cap).
- **B2 realized:** Cream Finance yUSD ($130M, Oct 2021 — donation → vault pricePerShare inflation read
  by the lending oracle); Sonne ($20M, first-depositor on a newly listed Compound-fork market with a
  live collateral factor); Hundred Finance (empty-market exchange-rate). These anchor the impact.

## Grounding: severity + mitigation (B1 / B2)

B1 grades this High when permissionless with real loss, Medium when seed/epoch-gated. The canonical
mitigations (virtual shares — OZ 4.9; dead shares; seed) are what the **negative control** must exercise:
a fixture that doesn't show the mitigated version going covered-dry hasn't proven the class.

## Not this card
- A vault that values assets by an internal accounting ledger (not `balanceOf`) → donation doesn't move
  the rate; not this class.
- A donation that moves the rate but yields no next-depositor loss (mitigated, or no victim path) → low.

## Do not overclaim
- An empty market is an activation signal, not a finding — reproduce a net attacker profit / victim loss
  with a passing mitigated-version neg-control.
- If OZ 4.9+ virtual shares or a seed is present, the attack is usually unprofitable — say so; do not
  report a bounded/dust loss as a drain.
