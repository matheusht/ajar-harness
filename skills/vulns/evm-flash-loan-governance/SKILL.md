---
id: evm.flash-loan-governance
name: Flash-Loan-Acquired Voting Weight / Spot-Balance-Priced Privileged Decision
description: >
  Prove that a privileged, threshold-gated decision — a governance proposal's execution path, a
  fast-track/emergency bypass of a normal timelock, a mint/burn or price-setting authorization, a
  liquidation or parameter-change trigger — is priced off a LIVE/spot balance (a token balance, an
  internal "roots"/share accounting value, an LP-token holding) read at the moment of the decision
  rather than a balance checkpointed/snapshotted at an earlier block, AND that the weighted asset can
  be acquired in decision-swinging size inside a single transaction (flash loan, flash mint, or a
  one-tx wrapper-and-deposit). A live-balance weight read is an activation signal; a finding requires
  reproducing the acquire -> vote/commit -> threshold-cross -> privileged-execution sequence inside
  one transaction/block on a real fork, with the borrowed capital returned and the privileged outcome
  still standing.
type: vuln
owasp: "No dedicated SWC-registry entry (flash-loan-priced governance weight postdates the registry); CWE-841 (Improper Enforcement of Behavioral Workflow), CWE-367 (Time-of-Check/Time-of-Use — the balance is read at use-time instead of snapshotted at decision-creation-time). Not an OWASP-web category — this is the EVM smart-contract class."
atlas: "—"
patterns: []

activation:
  strong:
    - "a governance/voting-weight function (recordVote, castVote, a delegate/boost weight calc) reads the CURRENT/live balance of msg.sender (balanceOf, an internal share/'roots' accounting value, getVotes called WITHOUT a block-number/checkpoint argument) at the moment of the vote/decision call, rather than a balance snapshotted at proposal-creation time or an earlier checkpoint block"
    - "a privileged execution path (fast-track/emergency commit, a reduced-or-zero timelock bypass, a mint/burn or price-setting authorization, an admin-role grant) becomes callable once an aggregate vote/threshold measured against that live balance crosses a numeric bar (e.g. a 2/3 supermajority), AND the threshold check happens in the SAME transaction/block the balance could have been acquired in — no minimum holding period before the balance counts"
    - "the token/LP/share being weighted is itself acquirable in a single permissionless transaction in decision-swinging size — a flash loan swapped/deposited into a whitelisted pool, a flash-mintable token, or a 1:1 deposit wrapper — i.e. there is a same-tx path from 'attacker holds ~0' to 'attacker holds enough to cross the threshold'"
    - "the decision's execution path grants delegatecall, an arbitrary CREATE2-precomputed target, or otherwise unrestricted authority over protocol funds/state — so capturing the decision converts directly into a fund-loss primitive, not merely a parameter tweak"
  weak:
    - "balance-weighted voting exists but the weighted asset requires depositing into a specific whitelisted pool/asset that is not yet confirmed flash-loan-able at decision-swinging size (liquidity depth, transfer-fee friction) — needs confirmation before treating as strong"
    - "the privileged decision reachable via an inflated live balance is low-impact (a cosmetic parameter, an informational flag) rather than fund-moving or authority-granting — reachability confirmed, impact thin"
  negative:
    - "voting weight is checkpointed (ERC20Votes/getPriorVotes-style: weight recorded at proposal-creation block or an earlier snapshot, looked up historically at vote time) so a same-tx or same-block flash loan cannot retroactively inflate it -> likely held"
    - "voting weight requires a minimum holding/lock/vesting period (a time-weighted-average balance, a lockup contract, a 'must have held before block X' gate) exceeding one flash-loan transaction -> likely held"
    - "the privileged execution path carries an unconditional timelock/delay independent of vote share — no fast-track/emergency bypass keyed to a supermajority — so a swayed vote cannot execute before the flash-loaned balance must be unwound -> likely held; record as a positive control"

safe_signal:
  proxy: >
    a LOCAL Foundry harness built from the REAL BeanstalkFarms/Beanstalk contracts at their pinned
    pre-exploit commit (never a reimplementation), driven through the acquire -> vote -> emergencyCommit
    sequence and asserting the protocol's own governance invariant breaks — hand-verified against the
    live repo (github.com/BeanstalkFarms/Beanstalk) for this card:
    at commit `e9f49910e2` (2022-04-11, last commit before the Apr-17-2022 exploit tx),
    `protocol/contracts/farm/facets/GovernanceFacet/VotingBooth.sol::recordVote()` adds
    `balanceOfRoots(account)` — a LIVE internal Silo-share balance, not a snapshot — to the bip's vote
    tally on every `vote()` call, and
    `protocol/contracts/farm/facets/GovernanceFacet/GovernanceFacet.sol::emergencyCommit()` executes a
    bip once `bipVotePercent(bip) >= C.getGovernanceEmergencyThreshold()` (2/3, `protocol/contracts/C.sol`
    lines 49-50) after only `GOVERNANCE_EMERGENCY_PERIOD` = 86400s / 1 day (`C.sol` line 47) instead of
    the normal `GOVERNANCE_PERIOD` = 168 seasons / 7 days (line 46) — the harness deposits a flash-loaned
    whitelisted asset into the Silo, calls `vote()` in the same transaction to register the freshly
    minted roots against a planted malicious bip, and asserts `emergencyCommit()` becomes callable and
    executes (`s.g.bips[bip].executed == true`) while the attacker's flash loan is still outstanding —
    reproducing Beanstalk's own disclosed mechanism (`bean.money/blog/beanstalk-governance-exploit`).
    The mandatory patched-twin neg-control: at commit `8cfd4c3404` (2022-05-30, post-"Replant"
    rewrite, hand-verified via the GitHub tree API), `GovernanceFacet/` is ABSENT from the Diamond's
    facet set entirely (`protocol/contracts/farm/facets/` no longer contains a governance facet) —
    the same harness against this ref cannot resolve `vote()`/`emergencyCommit()` at all, so the
    sequence fails to construct and the harness reports covered-dry by construction. This is a real
    disclosed removal (PR #4, "+ Internal Balances, + Token Facet, - Governance"), not a
    guard-added-to-the-same-function patch — record that distinction in any report so the neg-control
    isn't misread as "the same code path now guarded." The benign marker is the invariant-assertion
    (bip executed / not executed), never any live effect; a fixture that "confirms" against both refs
    is tautological (fake-client-poc-invariant-check).
  never: >
    never run the acquire/vote/execute sequence against any live mainnet/testnet deployment or any
    contract/party the operator does not control; the harness uses only a local Anvil/EVM fork with
    locally-minted, valueless test tokens and a flash loan sourced from a local mock or a forked
    permissionless pool the operator controls the state of. A demonstration that ends in an actual
    transfer of real value out of the protocol (as opposed to a pure invariant-break / privileged-call
    reached assertion) is a Zone-2 artifact — create only under explicit human impact-escalation
    authorization, contained and logged.

impact_escalation:
  enabled_by: scope.md#impact_demo_authorized
  requires: >
    a benign local invariant-break assertion (privileged action reached/executed on the fork) needs no
    per-artifact pause; a value-moving/drain PoC built on top of the reached privileged-execution path
    is Zone-2 and requires a fresh explicit human confirmation before creation
  containment: "local disposable Foundry/Anvil environment only; locally-minted valueless test tokens and a local/mocked flash-loan source; logged in the fixture cleanup.md and the engagement cleanup ledger"

oracle: [whitebox-analysis, regrade-oracle, pocinator-oracle]
severity_rubric: { permissionless_flashloan_crosses_threshold_and_privileged_execution_reproduced_before_repayment: critical, permissionless_flashloan_crosses_threshold_privileged_decision_swayed_reproduced_no_realized_fund_loss: high, gated_or_role_restricted_decision_still_swayable_by_flashloan_reproduced: medium, live_balance_weight_read_confirmed_no_privileged_action_reachable_within_borrow_window: low }

procedure:
  - "MAP PRIVILEGED DECISIONS vs THEIR WEIGHT SOURCE: enumerate every privileged/threshold-gated action in the in-scope contract (governance execution, a fast-track/emergency path, price-setting, mint/burn authorization, a liquidation trigger) and, for each, what balance/share/weight value decides whether the threshold is crossed."
  - "CLASSIFY THE WEIGHT READ: a live/spot balance read at decision time (vulnerable class) vs a checkpointed/snapshotted balance from an earlier block (ERC20Votes/getPriorVotes-style, held class) vs a time-weighted-average balance (held unless the averaging window is shorter than a practical flash-loan+multi-block strategy)."
  - "IDENTIFY THE ACQUISITION VECTOR: confirm the weighted token/LP/share can actually be acquired inside one transaction in decision-swinging size — a flash loan swapped/deposited into a whitelisted pool, a flash-mintable token, or a 1:1 deposit wrapper. No same-tx acquisition vector -> downgrade to weak/held."
  - "PIN THE THRESHOLD AND THE BYPASS: state the exact numeric threshold (e.g. 2/3) and whether crossing it unlocks a FASTER execution path (a reduced/zero timelock) than the contract's normal path — this is what converts 'can sway a vote' into 'can execute a privileged action inside one attack transaction, or before the flash loan must be repaid.'"
  - "PIN THE INVARIANT: state the protocol's OWN invariant broken (e.g. 'only stakeholders who held voting weight across a real time window — not weight manufactured in-block — can approve privileged execution'). This is the confirm-on-fork assertion, not a printed marker (whitebox-analysis §4)."
  - "REPRODUCE ON A LOCAL FORK WITH THE REAL CONTRACT: build a Foundry harness vendoring the real governance/decision contract at the pinned in-scope commit; acquire the weighted balance (flash loan / flash mint), cast the vote/commit, cross the threshold, and — if in scope — trigger the privileged execution, all inside one transaction/block; assert the invariant breaks. Never a reimplementation of the vulnerable logic."
  - "RUN THE PATCHED/NEGATIVE CONTROL: the same harness against a version with checkpointed/time-weighted voting weight (or with the weighted asset/path removed) MUST yield covered-dry — the sequence cannot be constructed or the threshold cannot be crossed. Without a passing neg-control the confirmation is reward-hackable."
  - "TRACE REACHABILITY AND CAP BY THE REPAYMENT WINDOW: confirm the privileged action is reachable PERMISSIONLESSLY and executes, or locks in an unstoppable outcome, before the flash loan must be repaid / before the borrowed weight must be returned; a decision only swayable but not executable/lockable within that window caps severity below critical."
  - "CHECK RELEASE ELIGIBILITY: confirm the exact pinned in-scope commit still has the gap (a fix already merged/released — e.g. migration to checkpointed voting weight, or removal of the fast-track path — takes the disclosed instance out of scope; cite it as precedent, not a live finding)."

emits: [attempt, finding]
---

## What "confirmed" looks like here

A `confirmed` finding shows, on a local fork running the REAL in-scope governance/decision contract:
(1) a reproduced same-transaction/block sequence of acquiring the weighted balance, casting a
vote/commit, and crossing the privileged-decision threshold, (2) the protocol's OWN invariant broken by
an assertion failure — the privileged action is reached/executed while the borrowed capital is still
outstanding, not a console marker, and (3) a passing negative control (a checkpointed/time-weighted or
path-removed version yields covered-dry). Missing (3) makes the confirmation reward-hackable and routes
to `needs_rework` at pocinator. Severity beyond "reachable" additionally requires tracing whether the
privileged action's effect survives the flash loan being unwound (§ severity_rubric).

## Real disclosed anchor for this class (verified, cited)

**Beanstalk Farms (Apr 2022), ~$182M press/headline figure, flash-loan-governance (B2).** Attacker
flash-loaned roughly $1B in stablecoins, converted it into whitelisted Curve/BEAN LP tokens, and
deposited them into Beanstalk's Silo in the same transaction — instantly minting a 2/3 Stalk
(governance) supermajority — then called `emergencyCommit()`, which lets a proposal execute after only
a 1-day fast-track (instead of the normal 7-day timelock) once that supermajority is reached; the
executed proposal `delegatecall`ed a malicious CREATE2-precomputed contract that drained the protocol.
Root cause per Beanstalk's own post-mortem: `emergencyCommit()`'s 1-day fast-track combined with
flash-loan-mintable Stalk weight and a delegatecall-based execution path let an attacker buy, use, and
return governance power within a single transaction
([post-mortem](https://bean.money/blog/beanstalk-governance-exploit) ·
[tx](https://etherscan.io/tx/0x68cdec0ac76454c3b0f7af0b8a3895db00adf6daaf3b50a99716858c4fa54c6f)). The
mechanism was hand-verified directly against the disclosed repo for this card (not just the corpus
description): `VotingBooth.sol::recordVote()` reads a live `balanceOfRoots()`, `C.sol` fixes the
emergency threshold at 2/3 and the emergency period at 1 day vs. a normal 7-day `GOVERNANCE_PERIOD`,
and the facet was excised entirely six weeks later in the "Replant" rewrite — see `safe_signal.proxy`
for the exact pinned refs. This corpus row is recorded under "Contested (recorded, not asserted)" for
one narrow reason only — a note confirming it is a genuine flash-loan-mintable-governance CODE chain
and NOT a multisig/key-compromise incident, i.e. it stays IN; it is not disputed as a real code
exploit.

**Vader Protocol — Code4rena contest (Apr 2021), Issue #187 / final report H-05: "Flash loans can
affect governance voting in DAO.sol" (B1), High, dedup class
`flash-loan-instantaneous-voting-weight-governance-manipulation`.** The sponsor (strictly-scarce)
disputed validity ("Not valid. All pools use slip-based fees so flash loan attack by buying up USDV or
synths is not going to work."); the assigned judge (dmvt) personally rebutted this in the published
report, quoted verbatim: "The funds to execute this attack do not need to come from a pool. It could be
done as simply as malicious members pooling their funds in a flash loan contract, and each borrowing
the funds in turn to..." — and the finding stood as High
([C4 2021-04-vader-findings #187](https://github.com/code-423n4/2021-04-vader-findings/issues/187)).
This is the corpus's worked instance of a judge overruling a sponsor's "flash loans can't actually reach
decision-swinging size" defense — treat that defense as needing a concrete liquidity-depth check
(activation: weak), not as automatically dispositive.

## Grounding: severity + realized impact (B1 / B2 corpora)

- **B2 (`skills/oracles/references/defi-exploit-chain-corpus.md`)** — Beanstalk Farms is the corpus's
  single `flash-loan-governance`-class realized-loss row (rollup: `flash-loan-governance (1)`) —
  permissionless, same-transaction, executed to a delegatecall drain: anchors the `critical` rung.
- **B1 (`skills/oracles/references/defi-contest-adjudication-corpus.md`)** — Vader C4 #187 is the
  corpus's single worked `governance-flashloan`-class row (its own class-distribution note: `governance`
  and `governance-flashloan` "remain single- or low-count classes — usable as one worked precedent each,
  not yet a distribution"), permissionless, contest-graded High with no realized on-chain loss (a
  proposed/judged attack, not an executed one): anchors the `high` rung.
- **Honest gap — `medium`/`low` rungs.** Neither corpus carries a governance/flash-loan-class row that is
  gated by a role, or reachable-but-not-executable-in-window. Those two buckets in `severity_rubric` are
  extrapolated from this card's own reachability logic (a gated/role-restricted decision, or a decision
  that cannot execute before flash-loan repayment, is mechanically lower-impact than Beanstalk's
  permissionless-and-executed chain) and from B1's general reachability doctrine that a trusted/admin-
  gated path caps severity (e.g. C4 2021-10-slingshot #76: sponsor/judge-affirmed Invalid because the
  gated role "is the most trusted role in the system... governance of that role will be decentralized" —
  a different class, cited only for the general doctrine, not as a governance-flashloan precedent) —
  not a governance-flashloan-specific worked instance in either corpus. Say so in any report rather than
  implying a Medium/Low precedent exists for this exact class.

## Not this card

- A flash loan used to desync an AMM pool's balances vs. its LP totalSupply mid-transaction so a
  DIFFERENT protocol's price ORACLE reads a stale/manipulated rate (Sturdy/Balancer, dForce/Curve) is
  `evm.read-only-reentrancy-price`, not this card, even though a flash loan funds the attack — the
  weighted value here is a privileged-decision THRESHOLD, not a price feed.
- A flash loan used only to bypass a timing gate (e.g. a cooldown before rewards can be sold, via a
  reentrant callback — C4 2023-05-ajna #488 H-03) without any vote/threshold being swayed is a
  reentrancy/timing-bypass shape, not this card.
- A privileged decision gated by a genuinely trusted/admin role with no balance-weighted vote at all
  (a multisig, an owner-only setter) is `evm.access-control`, not this card — there is no spot balance
  to flash-borrow into.
- A governance system whose weight is checkpointed (ERC20Votes-style) but where the checkpoint itself
  can be manipulated by a DIFFERENT bug (a delegation-replay, a storage-collision re-initialization as
  in Audius) is a distinct root cause — cite Audius as an adjacent precedent, not this card's mechanism,
  if the checkpoint read itself is sound and only its initialization was corrupted.

## Do not overclaim

- A live-balance vote-weight read alone is an activation signal, not a finding — you must reproduce the
  full acquire -> vote -> threshold-cross sequence inside one transaction/block, with a passing
  checkpointed/removed-path neg-control, per `severity_rubric` and the procedure above.
- A sponsor's "flash loans can't reach decision-swinging size against our pool" defense is not
  dispositive on its own (Vader #187) — it must be checked against real liquidity depth/fee friction for
  the specific whitelisted asset in the in-scope protocol, not assumed either way.
- The disclosed anchors' "$" figures are the reporting party's press/headline exposure estimate
  (Beanstalk ~$182M) unless a realized on-chain-traced loss is separately cited — state the distinction
  in any report, and note Vader #187 had no realized loss at all (a contest-judged attack, not an
  executed one).
- A privileged decision that becomes swayable but cannot execute (or lock in an unstoppable outcome)
  before the flash loan must be repaid is real but capped — do not report it at the `critical` rung
  reserved for a reproduced, executed, within-window chain.
