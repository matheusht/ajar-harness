---
id: evm.access-control
name: EVM Access Control — Missing / Incorrect Authorization
description: >
  Prove that a state-changing or value-moving function is callable by an actor who should not reach it:
  a privileged setter / mint / withdraw / upgrade / initializer with a missing or wrong modifier
  (`onlyOwner`/role check absent, `_authorizeUpgrade` un-overridden, an `initialize()` left
  re-callable or unprotected, a proxy-admin slot collision), so an unprivileged caller changes state
  the protocol trusts (ownership, config, an oracle/router address, a token balance). A function that
  merely *looks* under-guarded is an activation signal; a finding requires a reproduced unauthorized
  call that a correctly-authorized deployment would reject.
type: vuln
owasp: "SWC-105 (Unprotected function), SWC-118 (Incorrect constructor/init), SWC-112 (delegatecall to untrusted); CWE-284/862/863 (Improper/Missing/Incorrect Authorization). EVM smart-contract class."
atlas: "—"
patterns: []

activation:
  strong:
    - "a state-changing function (setter for owner/controller/oracle/router/fee, mint, withdraw, pause, whitelist) has NO access modifier, or a modifier that checks the wrong role/address, and is reachable by any caller"
    - "an upgradeable contract's `_authorizeUpgrade(address)` is not overridden with an owner/role check (or overridden empty), so anyone can `upgradeTo` — or an `initialize()` is `public`/`external` without an initializer guard, or the guard can be bypassed via a proxy storage-collision (the Audius shape: proxyAdmin slot overlaps `Initializable`'s flags)"
    - "a privileged cross-chain / router / callback entrypoint uses an unauthenticated dispatch (e.g. `performCallOut` instead of a router-gated `performSystemCallOut`) so any caller registers/spoofs trusted state"
  weak:
    - "a function looks privileged but is actually guarded one layer up (a router/manager gates the only caller) — trace the real reachable caller before treating as strong"
    - "an `initialize()` is unprotected but is front-run-only with no irreversible damage (re-init reverts or is idempotent) — Sherlock §VII treats a front-run of an initializer with no irreversible damage as invalid; confirm the actual impact"
  negative:
    - "every privileged function carries a consistent, correct modifier; `_authorizeUpgrade` is owner/role-gated; `initialize()` has an `initializer`/`reinitializer` guard with no proxy-slot collision → likely held; record as a positive control"
    - "the only 'unguarded' functions are view/pure or write state no other logic trusts → not a finding"

safe_signal:
  proxy: >
    a LOCAL Foundry harness built from the REAL contract at its pinned in-scope commit (never a
    reimplementation) in which an unprivileged address performs the privileged call and the resulting
    state change breaks a protocol invariant (ownership transferred, an oracle/router address swapped,
    funds moved), while the PATCHED/correctly-guarded version reverts on the same call = covered-dry. The
    benign marker is the revert/invariant-assertion on the local harness, not any live effect. Planned
    fixture: a Code4rena/Sherlock access-control finding with a public vulnerable commit + its fix PR
    (e.g. the Basin `_authorizeUpgrade` omission, or Non-fungible's missing `__Ownable_init`), vendored
    byte-for-byte at both refs like the shipped `evals/contract-audit/fixtures/jpegd-reentrancy/` pattern.
  never: >
    never run the privileged call against any live deployment or any party you do not control; local
    fork/EVM only, valueless test tokens. A value-moving demonstration (an actual drain via the
    unauthorized call) is a Zone-2 artifact — create only under explicit human impact-escalation
    authorization, contained and logged.

impact_escalation:
  enabled_by: scope.md#impact_demo_authorized
  requires: >
    a benign local invariant/revert assertion needs no per-artifact pause; a value-moving/drain PoC via
    the unauthorized call is Zone-2 and requires a fresh explicit human confirmation before creation
  containment: "local disposable Foundry/EVM only; locally-minted valueless test tokens; logged in the fixture cleanup notes and the engagement cleanup ledger"

oracle: [whitebox-analysis, regrade-oracle, pocinator-oracle]
severity_rubric: { unauth_fund_drain_or_ownership_takeover_reproduced: critical, unauth_privileged_state_change_bounded_impact: high, unauth_change_gated_by_trusted_role_or_no_real_impact: medium, misconfig_or_centralization_only: low }

procedure:
  - "ENUMERATE PRIVILEGED FUNCTIONS: every setter, mint/burn, withdraw, pause, whitelist, upgrade, and initializer in the in-scope contracts; note the modifier (or absence) on each."
  - "TRACE THE REAL REACHABLE CALLER: is the function actually reachable by an arbitrary EOA, or gated one layer up (router/manager)? Confirm reachability before treating a missing modifier as a finding."
  - "CHECK UPGRADE + INIT PATHS SPECIFICALLY: is `_authorizeUpgrade` overridden with an owner/role check? Is `initialize()` behind an `initializer` guard, and does any proxy-admin storage slot collide with `Initializable`'s flags (the Audius shape)?"
  - "PIN THE INVARIANT: what does the unauthorized state change break — ownership, an oracle/router address the protocol trusts, a token balance? This is the confirm assertion."
  - "REPRODUCE ON A FORK WITH THE REAL CONTRACT: an unprivileged address performs the call; assert the invariant breaks (state changed / value moved)."
  - "RUN THE NEGATIVE CONTROL: the correctly-guarded version (or the fix commit) MUST revert on the same call = covered-dry."
  - "GRADE BY REACHABILITY + IMPACT: permissionless fund-drain/ownership-takeover is critical; a trusted-role-only or no-real-impact change is capped (the Slingshot 'admin is trusted' / Asymmetry 'owner-drain is OOS centralization' precedents)."

emits: [attempt, finding]
---

## What "confirmed" looks like here

On a local fork with the REAL in-scope contract: an unprivileged address makes the privileged call and
a protocol invariant breaks (ownership/config/oracle changed, or value moved), an assertion failure
(not a marker), AND a passing neg-control (the guarded/patched version reverts on the same call).

## Real disclosed anchors for this class (verified, cited — B1/B2)

- **C4 Basin #52 (H-01).** `WellUpgradeable._authorizeUpgrade` omitted `onlyOwner`; since well
  registration is permissionless, anyone could upgrade any well → total fund loss (judge: valid High).
- **C4 Non-fungible #186 (M-04).** `Pool` inherited `OwnableUpgradeable` but never called
  `__Ownable_init()`, so `owner()` stayed zero → a fresh `initialize()` could seize ownership.
- **C4 Slingshot #76 / Asymmetry #398 (the CAP precedents).** "Owner can drain" / "admin can act
  maliciously" was ruled **invalid / OOS centralization** — a trusted role acting maliciously is not
  this card unless the role is permissionlessly obtainable or an *external* admin unknowingly harms.
- **B2 Audius ($1.1M AUDIO, Jul 2022).** Proxy storage-collision let `initialize()` re-run → fabricated
  governance weight → treasury drain (a real realized access-control/proxy-init exploit). Furucombo:
  uninitialized Aave-V2 proxy hijacked via transitive delegatecall → approval drain.

## Grounding: severity by reachability (B1)

B1's `defi-contest-adjudication-corpus.md` is explicit that access-control severity is set by
**reachability**: permissionless + fund-loss = High/Critical (Basin); trusted-role or admin-mistake =
invalid/QA (Slingshot, Asymmetry). Set `severity_rubric` accordingly — never grade a trusted-admin
"can drain" as a finding without a permissionless or external-admin-unknowing path.

## Not this card
- A trusted-role/admin function that requires the admin to act maliciously → invalid centralization
  (the CAP precedent), unless the role is permissionlessly obtainable or an external admin is unknowingly
  harmed.
- An unprotected `initialize()` that is front-run-only with no irreversible damage → Sherlock §VII invalid.

## Do not overclaim
- A missing modifier is an activation signal, not a finding — reproduce the unauthorized call breaking a
  real invariant, with a passing guarded-version neg-control.
- "Owner can rug" is a centralization note, not this card, unless you show a permissionless or
  external-admin-unknowing reachability path.
