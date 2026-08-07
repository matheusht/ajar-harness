---
id: evm.dos-unbounded-gas
name: EVM Denial of Service via Unbounded Gas (Unbounded Loop / Griefing / Block Stuffing / Reverting Receiver)
description: >
  Prove that a Solidity/EVM contract has a code path whose gas cost grows with an attacker-influenced
  or attacker-growable quantity — an unbounded loop over a permissionlessly-growable array/mapping
  (positions, orders, claimants, stakers), a push-payment loop to a list of recipients where one
  reverting/gas-guzzling receiver blocks the whole batch, or an admin/keeper batch job whose input set
  an attacker can permissionlessly inflate — so that the path eventually exceeds the block gas limit or
  a documented practical gas ceiling, denying availability to legitimate users. A theoretical unbounded
  loop is an activation signal; a finding requires reproducing the gas-cost growth (or the induced
  revert) against the REAL in-scope contract on a local fork, showing WHO is denied WHAT, for how long,
  and at what cost to the attacker.
type: vuln
owasp: "SWC-113 (DoS with Failed Call); SWC-128 (DoS With Block Gas Limit); CWE-400 (Uncontrolled Resource Consumption), CWE-834 (Excessive Iteration). Not an OWASP-web category — this is the EVM smart-contract class."
atlas: "—"
patterns: []

activation:
  strong:
    - "an unbounded loop iterates a storage array/mapping whose LENGTH can be grown permissionlessly (anyone can call a function that appends to it — memorialize/deposit/order/claim entries) and the loop sits on a path OTHER users' funds or availability depend on (reward calculation, withdrawal enumeration, liquidation sweep) — the attacker spends near-zero cost per entry to inflate a victim's or the protocol's gas cost past the practical ceiling"
    - "a push-payment loop sends ETH/tokens to a list of recipients (batch payout, auction refund, dividend distribution) with no per-recipient try/catch isolation and no pull-based fallback, so one recipient's reverting/gas-guzzling fallback blocks the ENTIRE batch for every other recipient"
    - "an admin/keeper-triggered batch job (settle-all, sweep-all, process-pending) iterates a set an attacker can permissionlessly inflate (open dust orders, spam deposits, spam positions) with no cap/pagination/cursor, letting an attacker force the batch above the block gas limit"
    - "gas cost of a state-changing function is O(n) where n is fully or partially attacker-controlled (array-length input, number of approvals/signatures/proofs) with no upper bound enforced and no batching/pagination on a path other users' funds/availability depend on"
  weak:
    - "an unbounded loop exists but growing it costs the attacker real, non-recoverable value per entry (e.g. each spam entry requires locking meaningful collateral) — check the cost/benefit ratio before calling strong; griefing that costs more than it damages is a weaker case"
    - "a reverting-receiver push-payment pattern exists but the system already has SOME isolation (a try/catch per recipient, or a documented pull-based withdraw() as fallback) — confirm the SPECIFIC loop path under test actually lacks that isolation before treating as strong"
    - "growth of the iterated structure is possible but requires a precondition (a specific market/pool state, a role that is normally but not provably restricted) not yet confirmed reachable"
  negative:
    - "every attacker-growable iteration surface uses a pull-based payment pattern, cursor/pagination, or an enforced per-call/per-block/per-user cap on collection growth → likely held; record as a positive control"
    - "growth of the iterated structure is gated to a trusted/admin-only role (not permissionlessly callable) and the README/scope doesn't declare that role untrusted → per the Sherlock admin-trust and array-length-trusted-admin-controlled exclusions, discount — record as likely-held, not a finding, unless the role is shown to be permissionlessly obtainable"
    - "gas cost grows with n but n is bounded by a hard-coded/enforced ceiling that keeps the worst case comfortably under the practical gas limit → likely held"

safe_signal:
  proxy: >
    a LOCAL Foundry harness built from the REAL contract at its pinned in-scope commit (never a
    reimplementation) that observably reproduces the gas-cost-growth/availability-break invariant
    failure — the worked fixture plan for this card is `evals/contract-audit/fixtures/ajna-positionmanager-dos/`,
    built from Ajna Protocol's `PositionManager.sol`: at the real vulnerable ref (code-423n4/2023-05-ajna
    contest snapshot, commit `276942bc2f97488d07b887c8edceaaab7a5c3964`, `ajna-core/src/PositionManager.sol`
    `memorializePositions`), the function is `external override` with NO ownership/approval check, so
    ANY caller can attach dust positions to ANY other user's position NFT — the harness drives a
    non-owner attacker calling `memorializePositions` repeatedly against a victim's `tokenId` and
    asserts the growth of `positionIndexes[tokenId]` drives `getPositionIndexesFiltered`/
    `RewardsManager.calculateRewards` gas cost past a documented practical ceiling (or reverts
    out-of-gas), reproducing Code4rena 2023-05-ajna #488 (H-03). The PATCHED twin — real fix commit
    `ajna-finance/ajna-core@d3106d01a50ea0263c6a58b857e1d0e460af6756` ("add auth modifier to
    memorializePositions (#817)"), independently re-fetched this session via `gh api`, which adds the
    `mayInteract(pool_, tokenId_)` modifier requiring `_isApprovedOrOwner` — makes the same non-owner
    call revert immediately with `NoAuth()`, so the spam-growth path never opens (covered-dry). The
    benign marker is the gas-measurement/revert assertion on the local disposable harness, never any
    live effect. The neg-control (patched twin returns covered-dry) is mandatory — a fixture that
    "confirms" against both refs is tautological (fake-client-poc-invariant-check).
  never: >
    never run the growth/spam/reverting-receiver sequence against any live mainnet/testnet deployment
    or any contract/party you do not control; the harness uses only locally-minted, valueless test
    tokens and synthetic accounts on a local Anvil/EVM, and measures gas cost / revert behavior only. A
    demonstration that stages realistic mainnet-fork state to show a dollar figure of funds actually
    locked/inaccessible (as opposed to a bare gas-cost-exceeds-ceiling or revert assertion) is a Zone-2
    artifact — create only under explicit human impact-escalation authorization, contained and logged.

impact_escalation:
  enabled_by: scope.md#impact_demo_authorized
  requires: >
    a benign local gas-cost-growth or revert assertion needs no per-artifact pause; a demonstration
    that quantifies real funds locked/inaccessible (a $-figure fund-freeze narrative built on
    realistic mainnet-fork balances rather than a bare invariant assertion) is Zone-2 and requires a
    fresh explicit human confirmation before creation
  containment: "local disposable Foundry/Anvil environment only; locally-minted valueless test tokens; logged in the fixture cleanup.md and the engagement cleanup ledger"

oracle: [whitebox-analysis, regrade-oracle, pocinator-oracle]
severity_rubric: { permanent_unrecoverable_fund_freeze_all_users_no_admin_recovery_path: critical, permissionless_out_of_gas_dos_reproduced_blocking_all_user_funds_permanently_or_a_genuinely_time_sensitive_function: high, permissionless_griefing_dos_reproduced_meets_sherlock_two_part_test_funds_locked_over_1wk_or_time_sensitive_availability_impacted: medium, gated_admin_only_growth_or_low_likelihood_or_short_lived_under_1wk_single_occurrence_or_costly_to_attacker: low }

procedure:
  - "MAP UNBOUNDED SURFACES: in the in-scope contract(s), list every loop/iteration whose bound is a storage array/mapping length or a caller-supplied array-length parameter, and every payment-to-a-list loop. For each, note whether the bound is grown permissionlessly, by a whitelisted role, or is fixed."
  - "CLASSIFY THE MECHANISM: unbounded-loop-over-permissionlessly-growable-collection, push-payment-to-reverting-receiver, admin/keeper batch-iteration over an attacker-inflatable set, or O(n) state-write with attacker-controlled n. Each needs a different reproduction."
  - "IDENTIFY THE GRIEFING VECTOR AND ITS COST: who can grow the collection or control the reverting receiver, and what does one griefing unit cost the attacker (near-zero dust vs. real locked value)? Cheap-to-free griefing on a path other users depend on raises severity; griefing that costs the attacker more than the damage it causes lowers it (weak activation until shown otherwise)."
  - "PIN THE AVAILABILITY INVARIANT: state exactly which downstream function becomes unreachable/reverts, and for whom — one specific user, a whitelisted role's operations, or the whole protocol. This is the confirm-on-fork assertion (gas cost crosses the block gas limit, or the call reverts), not a printed marker (whitebox-analysis §4)."
  - "APPLY THE SHERLOCK DOS TWO-PART TEST: (1) does the block cause funds to be locked for more than a week, and/or (2) does it impact the availability of a genuinely time-sensitive function (cutoff functions do not count)? Neither -> below Medium; at least one -> Medium; both, or the block is permanent and covers ALL user funds -> High. A single-occurrence DOS lasting under a week with no time-sensitive impact is NOT Medium."
  - "REPRODUCE ON A LOCAL FORK WITH THE REAL CONTRACT: build a Foundry harness vendoring the real contract at the pinned in-scope commit; drive the growth/spam/reverting-receiver sequence; measure gas cost as the attacker-controlled quantity grows (or show the downstream call reverts / exceeds a documented practical gas ceiling). Never a reimplementation of the vulnerable logic."
  - "RUN THE PATCHED/NEGATIVE CONTROL: the same harness against the fixed version (auth-gated growth, pagination/cursor, pull-payment, or an enforced cap) MUST yield covered-dry — the availability invariant holds. Without a passing neg-control the confirmation is reward-hackable."
  - "TRACE REACHABILITY AND RECOVERY: who can trigger the griefing path (permissionless vs. trusted-role-gated — a trusted/admin-only growth path is discounted per Sherlock's admin-trust and array-length-trusted-admin-controlled exclusions)? Is there ANY recovery path (admin sweep, pagination retrofit, migration) that caps a 'permanent' claim to 'temporary'?"
  - "CHECK RELEASE ELIGIBILITY: confirm the exact pinned in-scope commit still lacks the cap/pagination/auth guard (a fix already merged and released takes the disclosed instance out of scope — cite it as precedent, not a live finding)."

emits: [attempt, finding]
---

## What "confirmed" looks like here

A `confirmed` DoS-via-unbounded-gas finding shows, on a local fork running the REAL in-scope contract:
(1) a reproduced growth/spam/reverting-receiver sequence through a real permissionless (or role that is
shown to be permissionlessly obtainable) vector, (2) a measured gas-cost crossing of the block gas limit
or documented practical ceiling — or the induced revert — on the protocol's OWN downstream function
(not a printed marker), (3) the Sherlock DOS two-part test explicitly applied (funds-locked-over-1-week
and/or time-sensitive-function-impacted) to set the severity floor, and (4) a passing negative control
(the patched/guarded/paginated version yields covered-dry). Missing (4) makes the confirmation
reward-hackable and routes to `needs_rework` at pocinator.

## Real disclosed anchor for this class (verified, cited)

**Ajna Protocol `PositionManager.memorializePositions` NFT-spam rewards DoS — Code4rena 2023-05-ajna
#488 (H-03), High-Risk, sponsor-confirmed.** `memorializePositions` could be called by **anyone** (not
just the position-NFT owner) to attach insignificant (any value > 0) positions to someone else's
position NFT, growing that NFT's `positionIndexes` storage array without the owner's consent; because
`RewardsManager.calculateRewards`/`_calculateAndClaimRewards` depend on
`PositionManager.getPositionIndexesFiltered` iterating that same array, a griefer could spam a victim's
NFT with dust positions until reward calculation (and NFT burning) became gas-prohibitive — "a griefer
can spam anyone's position NFT with insignificant positions until the rewards mechanism fails for the
NFT owner due to DoS (gas limit)." 12 duplicate submissions merged into the canonical #488 (13 wardens
total), sponsor `ith-harvey` confirmed directly on the issue thread. Fixed by
`ajna-finance/ajna-core@d3106d01a50ea0263c6a58b857e1d0e460af6756` ("add auth modifier to
memorializePositions (#817)"), which adds the `mayInteract(pool_, tokenId_)` modifier requiring
`_isApprovedOrOwner(msg.sender, tokenId_)` — independently re-fetched via `gh api` this session against
the live `ajna-finance/ajna-core` repository (not itself part of the B1/B2 corpus text, which records
only the contest disposition). The shipped fixture plan
`evals/contract-audit/fixtures/ajna-positionmanager-dos/` reproduces this on the real contract at both
refs and is the worked `safe_signal` for this card.

## Grounding: severity + realized impact (B1 / B2 corpora)

- **B1 (`skills/oracles/references/defi-contest-adjudication-corpus.md`)** — this is a directly-graded
  class across all three rubric spines: Immunefi ISVCS v2.3 places "Smart contract unable to operate
  due to lack of token funds", "Block stuffing", "Griefing (e.g. no profit motive for an attacker, but
  damage to the users or the protocol)", "Theft of gas", and "Unbounded gas consumption" at
  **Medium**, while "Permanent freezing of funds" sits at **Critical** and "Temporary freezing of
  funds" at **High** (same source table). Sherlock's judging guidelines give the class its own named
  two-part test verbatim: "(1) The issue causes funds to be locked for more than a week. (2) The issue
  impacts the availability of time-sensitive functions (cutoff functions are not considered
  time-sensitive). If at least one of these is describing the case, the issue can be Medium. If both
  apply, the issue can be considered High severity" — and separately, Sherlock Section VIII names
  "Out-of-Gas DOS as Medium (High if it blocks all user funds permanently), except where array length
  is trusted-admin-…" (the corpus's own captured text truncates there; treat the trusted-admin-controlled
  exception as real but do not extend the quote past what the corpus actually captured). The worked
  Code4rena anchor is Ajna #488 above (permissionless griefer, High). Two negative-disposition
  precedents bound the class from below: **C4 2023-04-rubicon #558** — a griefing/front-run finding
  downgraded C4 High-Risk-submission → QA because "front-running on L2s isn't possible, which this vuln
  relies on" (the griefing precondition is unreachable on the real deployment); and **C4
  2024-08-chakra #98** — a griefing finding (locked, never-burnable tokens via a bridge handshake edge
  case) downgraded to QA because the judge assessed it "a low-likelihood event with a low impact, as
  the protocol would still be 'solvent'". One further Immunefi griefing/ransom item (Charged Particles,
  malicious-royalty-based griefing) is recorded only in the corpus's own **Contested** table, flagged
  `thin_rationale` — cited here as a data point, not asserted as a worked case.
- **B2 (`skills/oracles/references/defi-exploit-chain-corpus.md`)** — **thin, stated honestly, not
  fabricated.** A direct grep of the realized-exploit-chain corpus for `unbounded`/`array
  length`/`out-of-gas`/`block-stuffing`/`griefing`/`gas limit`/`loop`/`iteration` returns **zero
  matching rows** — no realized, on-chain, primary-sourced DoS-via-gas exploit chain is present in this
  corpus. This is consistent with B2's own stated method (Axis C is "realized loss-by-class," anchored
  on postmortems with a measurable stolen-value tx) and its own "Honest coverage gaps" note that
  MEV/sandwich-class and non-fund-theft incidents are structurally under-represented in a realized-loss
  lens: a pure availability/DoS bug produces a blocked or reverted transaction, not a stolen-value tx
  with a postmortem $-figure, so it rarely surfaces in exploit-chain writeups the way reentrancy or
  oracle-manipulation does. Do not claim a B2-grounded "realized loss" figure for this class — grade
  severity by the B1 contest-adjudication bar (reachability × Sherlock's two-part test) and report the
  impact honestly as fund-**availability**, not fund-**theft**, unless a separately-confirmed theft
  mechanism is chained in.

## Not this card
- A reachability-gated griefing path where the precondition the attack depends on does not hold in the
  real deployment (e.g. front-running relied on for the grief, but the target chain has a private
  mempool or the grief requires an on-chain condition never reachable) → downgrade per the Rubicon #558
  precedent, not a finding until the precondition is independently confirmed live.
- Growth of the iterated collection gated to a trusted/admin-only role with no evidence that role is
  permissionlessly obtainable → per Sherlock's admin-trust exclusion and the array-length
  trusted-admin-controlled carve-out, record as likely-held, not a finding.
- A low-likelihood, low-impact griefing shape where the protocol remains solvent and no genuine
  fund-lock or availability break is shown (the Chakra #98 shape) → QA-tier, not this card.
- Pure gas-cost inefficiency with no attacker-amplification and no availability impact (a function is
  merely expensive, not attacker-drivable past the block gas limit) → out per Sherlock's Section VII
  "gas optimizations" exclusion; this card is about denial of availability, not efficiency.

## Do not overclaim
- An unbounded loop over a growable collection is an activation signal, not a finding — you must
  reproduce the gas-cost growth (or induced revert) actually crossing the block gas limit or a
  documented practical ceiling on a real fork with the real contract, with a passing patched-twin
  neg-control.
- A "permanent" fund-freeze claim requires tracing whether ANY admin/recovery/migration path exists; if
  one does, the correct claim is "temporary" (High-tier per Sherlock/Immunefi), not "permanent"
  (Critical-tier).
- Do not inflate a short-lived (< 1 week), non-time-sensitive, single-occurrence gas bump into a Medium
  — Sherlock's own two-part test explicitly does not grade that shape as Medium.
- There is no B2 realized-loss anchor for this class (see Grounding) — do not cite a "$ stolen" figure;
  report the impact as availability/fund-lock, and if a theft mechanism is actually chained through the
  DoS (e.g. the block enables a separate, independently-confirmed drain), report that as its own
  finding with its own evidence, not folded into this card's severity.
