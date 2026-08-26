---
id: vulns.resource-precision-loss
name: Resource/Stake-2.0 Precision-Loss Accounting (float→long truncation)
description: >
  Prove that a blockchain resource-accounting path (freeze/delegate/unfreeze/withdraw usage
  ratios, energy/bandwidth usage computation, reward/vote rescale) truncates or floors a
  float→long conversion or integer division in an attacker-favorable direction, so the user
  obtains more delegated resource, more usable resource, or more reward than the invariant
  (usage <= frozen balance) allows — the #6599 family (CVSS 9.3). Confirmed only by measuring
  the delta on a real node with exact-BigInteger math as the negative control.
type: vuln
owasp: "no single CWE — CWE-681 (incorrect conversion between numeric types) / CWE-682 (incorrect
calculation)"
atlas: "—"
patterns: []

activation:
  strong:
    - "a `(long)(double)` ratio cast or floor-division in a resource usage / delegation-availability
      / reward computation, where truncation direction is attacker-favorable (usage understated →
      more available to delegate; ratio floor → free resource)"
    - "a validate path and its execution path compute the same quantity with different precision
      (validate unguarded, execution hardened — or vice versa), creating a delegation/consumption
      asymmetry"
    - "a hardening fix (BigInteger exact-math branch) exists but is flag-gated OFF by default, or
      applied to only some of the sibling call sites (incomplete-fix shape)"
    - "freeze/delegate/unfreeze/withdraw window math where the ratio can be pushed toward ~0 or
      wrapped negative by extreme inputs (tiny usage vs huge frozen balance, zero limits/weights)"
  weak:
    - "double/float division anywhere in vote, reward, or resource rescale math (dust-level,
      user-unfriendly but not attacker-gain unless composable)"
    - "query-path (read-only) endpoints computing the same ratios with the same unguarded formula"
  negative:
    - "all call sites of the ratio use exact BigInteger rational math with no float/floor at all
      → likely held"
    - "validate and execute paths both hardened identically, and the harden flag defaults ON
      → positive control, do not re-report"

safe_signal:
  proxy: >
    a predeclared measurable delta in an OWNED disposable private network: locally-minted test
    TRX, freeze → consume energy/bandwidth → delegate → measure. The proof is the difference
    between the balance/usage the exact-BigInteger math says the actor should hold and what the
    truncating path grants (delegated amount > frozen-remaining, or usage ratio pinned at ~0).
    Never a real network (mainnet/Shasta/Nile) or real TRX.
  never: >
    do not touch a live TRON network, real TRX, or third-party accounts; do not exceed the
    minimal local demonstration of the invariant break; revert any local state change and log it
    in cleanup.md.

impact_escalation:
  enabled_by: scope.md#impact_demo_authorized (tron-2026-08 signed MAX Zone-2, 2026-08-06)
  requires: human_confirm_only_for_submission
  containment: "disposable local private net, locally-minted test TRX; any escalation (chain
    divergence, validator-set halt) stays inside the local validator set"

oracle: [signal-oracle, adjudication-oracle, ghsa-fix-diff-oracle]
severity_rubric: >
  free_resource_delegation_or_theft (usage ratio ~0 → delegate/consume more than staked):
  critical — #6599 precedent scored CVSS 9.3 in exactly this code; resource_double_dip (receiver
  keeps allowance after undelegate undercharge): high; dust_undercharge (floor costs the
  protocol cents): medium; query_path_display_only: low.

procedure:
  - "MAP EVERY RATIO SITE: enumerate every `(long)(double)` cast / floor-division in
    Energy/Bandwidth/Resource processors, RepositoryImpl.usageToBalance, nativecontract
    Delegate/UnDelegate/Freeze processors + their actuator twins, FreezeV2Util, vote/reward
    rescale. Record file:line, the formula, and the truncation direction."
  - "DETERMINE ATTACKER-FAVORABLE DIRECTION: for each site, which party does flooring benefit?
    usage understated → owner delegates more than the invariant allows (attacker-gain); usage
    overstated → user overcharged (protocol-gain, not a finding unless composable)."
  - "NEGATIVE CONTROL (exact math): compute the same quantities with BigInteger/rounded-up
    arithmetic (or flip the harden flag to ON) — the delta between the two is the measurable
    exploit surface; the control must diverge THROUGH THE TRUNCATION specifically."
  - "CHECK VALIDATE vs EXECUTE ASYMMETRY: the gate that authorizes delegation vs the processor
    that charges it may use different precision (the #6599-family shape: validate never hardened,
    execute hardened behind a flag). An unguarded validate path is a finding independent of
    proposal activation state."
  - "NAME THE BROKEN INVARIANT: 'usage ratio truncates to ~0 → actor delegates full frozen V2
    balance despite consumed energy' — not 'precision loss in resource math'."
  - "FAITHFULNESS: reproduce on the REAL pinned code (GreatVoyage-v4.8.2.1) on a disposable
    single/multi-node private net with locally-minted TRX; the real transaction path, real TVM
    where applicable. A standalone math snippet that never runs the real processor path is a
    reward-hack, not evidence."
  - "DIFFERENTIAL (lens 11): where a hardened branch exists (ALLOW_HARDEN_RESOURCE_CALCULATION
    flag, BigInteger branches), run the PoC with the flag OFF (must reproduce) and ON (must NOT
    reproduce) — the maintainers' own #6599 fix as the pre/post boundary."
  - "Default to needs_review unless the broken invariant, the exact site, and the measured delta
    are all stated; resource-math findings overclaim easily when the direction of truncation is
    misread."
  - "CASCADE (Q1/Q2): every surviving site is a branch — Q1: which sibling processor/actuator
    twin/query path repeats the same formula? Q2: does the truncation primitive compose
    (undelegate undercharge → receiver keeps allowance → re-delegate → ratio again ~0)?"

emits: [attempt, finding]
---

## What "confirmed" looks like here

A named resource invariant (usage <= frozen balance; delegated resource <= staked-remaining) is
broken by float→long truncation, proven on the real pinned node by a measured balance/usage delta
between the truncating path and the exact-math negative control, with the normal (exact) path
behaving correctly as baseline. The #6599 precedent: `(long)(usage * TRX_PRECISION *
(weight/limit))` understated energy usage to ~0, granting free delegated energy — the exact shape
now confirmed live, unguarded, in `DelegateResourceProcessor.validate` / `DelegateResourceActuator`
(found at pinned GreatVoyage-v4.8.2.1 by recon, 2026-08-06).

## The gated-fix trap (incomplete-fix shape)

The processor layer (Energy/Bandwidth/Resource, RepositoryImpl) has exact-BigInteger hardened
branches, but they sit behind `ALLOW_HARDEN_RESOURCE_CALCULATION` which defaults to 0. Two
consequences, both in-scope as separate findings:

1. **Default-deployment exposure** — if the flag is 0 in the audited default config, the
   "fixed" sites are still truncating at runtime on every node.
2. **Un-fixed validate path** — `DelegateResourceProcessor.validate` / `DelegateResourceActuator`
   were never given hardened branches at all; the gate that authorizes delegation computes
   available-to-delegate with the identical truncating ratio #6599 exploited. This is a live
   sibling independent of the proposal, and it is a NEW finding, not a re-report of #6599
   (the fix's own code is the differential, used as lens-11 control, never re-reported itself).

## Not this card

- Pure integer/BigInteger accounting with no float or floor → nothing to truncate; route to
  unchecked-arithmetic if overflow is the question.
- Truncation that favors the protocol (usage overstated → user pays more) with no composable
  attacker path → cost-dust, not a finding.
- The exact #6599 already-fixed site re-hunted without a new angle (flag-ON config, execute
  path) → the hardened branch is a positive control, never a report.
- Query-path display-only endpoints with no state change → severity capped at low, still
  useful as a confirming lens, not a standalone finding.

## Do not overclaim

- "There is a `(long)(double)` cast" is not a finding — the direction of truncation and the
  party it favors must be established, then demonstrated as a real delta on the real path.
- Do not claim resource theft without measuring it on the node: the ratio must be pushed
  measurably toward ~0 (or the double-dip composed) through real freeze/delegate transactions,
  not computed in isolation.
- If the harden flag's on-chain activation state is unverifiable from source, say so in the
  finding and scope the claim accordingly (default-config exposure vs flag-activated exposure).
