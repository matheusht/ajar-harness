---
id: evm.delegatecall-proxy-upgrade
name: EVM Delegatecall / Proxy / Upgrade Mechanics (Storage Collision, Uninitialized Implementation, Target Hijack)
description: >
  Prove that the delegatecall/proxy MACHINERY underneath an upgradeable contract — not the
  authorization check gating it — is broken: an implementation contract reachable and callable
  directly (not only through its proxy) whose own initializer/ownership is unprotected and whose
  privileged sinks (selfdestruct, ownership grant, arbitrary storage write) are therefore reachable by
  anyone; a non-standard (non-EIP-1967) proxy storage slot that a privileged address (proxyAdmin,
  owner) shares with an unrelated contract's packed flags (OpenZeppelin `Initializable`'s
  `initialized`/`initializing` booleans), so one context's data is misread as the other's state; or a
  `delegatecall` whose TARGET is computed at runtime from caller-influenced input (a router/handler
  lookup, a diamond facet, an authorization check reused for more than one purpose) rather than a
  fixed immutable address, letting an attacker steer execution into a contract they control or into
  destroying the real implementation. A proxy pattern that merely *looks* non-standard or
  under-initialized is an activation signal; a finding requires a reproduced concrete primitive
  (aliased storage read, direct-call-reachable initializer, or hijacked delegatecall target) that
  breaks the protocol's own invariant on a real fork.
type: vuln
owasp: "SWC-112 (Delegatecall to Untrusted Callee); CWE-665 (Improper Initialization), CWE-829 (Inclusion of Functionality from Untrusted Control Sphere). Not an OWASP-web category — this is the EVM smart-contract class."
atlas: "—"
patterns: []

activation:
  strong:
    - "the implementation contract behind a Transparent/UUPS/Beacon proxy can be called DIRECTLY (not only through the proxy) and its `initialize()`/constructor-equivalent is not protected by `_disableInitializers()` (or an equivalent OZ >=4.3.2 guard in the constructor) — anyone can call `initialize()` on the raw implementation address and, if it exposes ANY privileged sink (ownership grant, a delegatecall/selfdestruct-capable path, an arbitrary-write), take it over or destroy it, bricking every proxy pointing at it (the Wormhole shape)"
    - "a non-EIP-1967 (custom-slot) proxy stores a privileged address (proxyAdmin, owner) in a storage slot that a linearized inherited contract also writes to for its own packed state (OpenZeppelin `Initializable`'s `initialized`/`initializing` booleans) — the two writers were never checked for slot non-overlap, so one context's data aliases into the other's flag bits and a guarded initializer reads as re-callable (the Audius `AudiusAdminUpgradeabilityProxy` shape: the low bytes of the proxyAdmin address were misread as `initialized=false`)"
    - "a `delegatecall` target is computed at runtime from caller-influenced input (a router/handler-lookup pattern, a diamond-facet address, a whitelist/`isValid()`-style authorization check) rather than a fixed immutable/constant address — AND the SAME check that authorizes an unrelated inbound call is reused to authorize the outbound delegatecall target, so satisfying the inbound check for one purpose also steers the outbound delegatecall (the Furucombo `isValid()`-reuse shape: one authorization check gated both which calls could enter the proxy and which addresses the proxy would delegatecall into)"
    - "an upgrade changes the implementation's storage layout incompatibly with the proxy's existing storage (a new variable inserted ahead of an old one, a struct reordered, an inherited contract's storage-gap consumed) without a layout diff being checked — a correctly-AUTHORIZED upgrade can still corrupt state read/written by the old layout"
  weak:
    - "a delegatecall target is runtime-computed but drawn from a registry/allowlist with no bypass found yet — trace the allowlist/authorization-reuse path before treating as strong"
    - "the proxy declares a custom admin/implementation slot but no concrete collision with another contract's packed state has been demonstrated — a custom slot alone is not evidence of collision, only of non-standard-ness that needs checking"
    - "`initialize()` is guarded by an `initializer` modifier but whether the modifier's own state variable could itself collide with something else in a non-standard proxy is unconfirmed"
  negative:
    - "the proxy uses EIP-1967 canonical slots exclusively (implementation/admin at the standardized keccak-1 slots, which structurally cannot collide with typical contract-declared storage), the implementation's constructor calls `_disableInitializers()` (or equivalent), and every delegatecall target is a fixed/immutable address never influenced by caller input → likely held; record as a positive control"
    - "an upgrade path exists and changes storage layout, but a documented storage-gap / layout-diff check is enforced (OZ upgrades-plugin validation, a CI storage-layout diff) → likely held"

safe_signal:
  proxy: >
    Two LOCAL Foundry/Anvil harnesses vendoring REAL contracts at pinned refs (never a
    reimplementation), each with a mandatory patched-twin neg-control (fake-client-poc-invariant-check
    — a fixture that "confirms" against both refs is tautological): (1)
    `evals/contract-audit/fixtures/audius-storage-collision/` — vendor the real
    `AudiusAdminUpgradeabilityProxy` + governance `Initializable`-inheriting contracts
    (github.com/AudiusProject/audius-protocol, `contracts/` package) at the commit live at the
    pre-incident block, and show the proxyAdmin-slot/`Initializable`-flag aliasing lets the harness
    re-invoke an initializer that fabricates delegated voting weight; the benign marker is an
    assertion that a harness-controlled address's post-re-init voting weight differs from what normal
    delegation could produce, never an actually-executed governance proposal or a real token transfer.
    The SAME contracts forked/vendored at a post-remediation block (per Audius's linked post-mortem)
    MUST yield covered-dry (re-init reverts or no longer aliases). (2)
    `evals/contract-audit/fixtures/furucombo-delegatecall-hijack/` — vendor the real Furucombo
    `Proxy.sol` + `HAaveProtocolV2.sol` handler (github.com/dinngo/furucombo) at the pinned pre-hack
    ref, drive the `isValid()`-reuse path documented in Furucombo's own post-mortem, and assert the
    harness's `Proxy.execute` delegatecalls into an address the harness (attacker role) controls rather
    than an entry from Furucombo's own handler registry — an execution-flow assertion (recorded
    delegatecall target != expected registry entry), never a real fund movement. The post-fix
    ref (registry hardening, per the same post-mortem) MUST yield covered-dry. Exact commit SHAs /
    block heights must be verified against the named public repos and post-mortems before either
    fixture is built — never guessed or fabricated.
  never: >
    never run either sequence against any live mainnet/testnet deployment or any contract/party you do
    not control; the harness uses only a local disposable Anvil/EVM with vendored source and, where a
    mainnet fork is needed for realistic state, historical block data only — no signed transactions
    against a live chain. A value-moving drain, an actually-executed malicious governance proposal, or
    an actual `selfdestruct` of a real (non-local) implementation is a Zone-2 artifact — create only
    under explicit human impact-escalation authorization, contained and logged.

impact_escalation:
  enabled_by: scope.md#impact_demo_authorized
  requires: >
    a benign local invariant-break assertion (aliased storage read demonstrated, delegatecall target
    hijack demonstrated, initializer-reachable-on-raw-implementation demonstrated) needs no
    per-artifact pause; escalating to a full simulated fund-drain, an executed governance takeover, or
    an implementation-bricking `selfdestruct` on the local fork is Zone-2 and requires a fresh explicit
    human confirmation before creation
  containment: "local disposable Foundry/Anvil environment only; no live contract calls; vendored/forked historical state, no signed live-chain transactions; logged in the fixture cleanup.md and the engagement cleanup ledger"

oracle: [whitebox-analysis, regrade-oracle, pocinator-oracle]
severity_rubric: { storage_collision_or_uninitialized_impl_permissionless_takeover_or_brick_reproduced: critical, delegatecall_hijack_or_uninitialized_proxy_fund_drain_reproduced: high, uninitialized_owner_or_storage_gap_no_fund_loss_path_gated_or_deployment_mitigated: medium, storage_layout_drift_theoretical_no_reachable_primitive_demonstrated: low }

procedure:
  - "MAP THE PROXY PATTERN: identify the proxy type (Transparent, UUPS, Beacon, minimal-clone, diamond/facet) and whether it uses EIP-1967 canonical slots or custom/non-standard slots for implementation address, admin address, and any packed flags."
  - "CHECK DIRECT-CALL REACHABILITY OF THE IMPLEMENTATION: can the raw implementation address (not the proxy) be called directly? If so, is its `initialize()`/constructor-equivalent protected (`_disableInitializers()` or equivalent)? Does an unprotected initializer expose a privileged sink (ownership grant, a delegatecall/selfdestruct path, arbitrary write)?"
  - "DIFF STORAGE LAYOUT FOR NON-STANDARD PROXIES: for any proxy NOT using EIP-1967 slots, enumerate the exact storage slot each critical variable occupies — in the proxy itself AND in every linearized inherited contract (especially OpenZeppelin's `Initializable`, which packs `_initialized`/`_initializing` into low-order bits) — and check for aliasing between a privileged address (proxyAdmin) and packed flags (the Audius shape)."
  - "TRACE DELEGATECALL TARGET RESOLUTION: for any delegatecall whose target is computed/looked-up rather than a fixed immutable address (a router/handler pattern, a diamond facet lookup, a governance-settable pointer), confirm the target-selection logic cannot be steered by attacker-supplied input or a spoofed/reused authorization check (the Furucombo `isValid()`-reuse shape)."
  - "SCOPE OUT THE UPGRADE-AUTHORIZATION QUESTION: if the upgrade TRIGGER itself (`_authorizeUpgrade`, a beacon's `upgradeTo`) lacks access control, that is `evm.access-control`'s confirm step, not this card's — this card assumes the trigger is nominally gated (or notes the gap and hands off) and asks whether the delegatecall/storage mechanics underneath can still be abused (an uninitialized implementation reachable directly, a storage collision misread by `Initializable`, a delegatecall landing on an attacker-controlled target, or a layout-incompatible upgrade corrupting state) regardless of who is authorized to trigger it."
  - "PIN THE INVARIANT: state the protocol's OWN invariant the primitive breaks — implementation destroyed and every dependent proxy call reverts; an attacker-controlled address now holds admin/owner state; a delegatecall executed attacker-supplied bytecode inside the proxy's storage context; or post-upgrade state reads a value the old layout never wrote there. This is the confirm-on-fork assertion, not a printed marker (whitebox-analysis §4)."
  - "REPRODUCE ON A LOCAL FORK WITH THE REAL CONTRACT: build a Foundry harness vendoring the real proxy + implementation (and, where the mechanic requires it, a real dependency like Aave's LendingPoolAddressesProvider) at the pinned in-scope commit; drive the concrete primitive; assert the invariant breaks. Never a reimplementation of the vulnerable layout/logic."
  - "RUN THE PATCHED/NEGATIVE CONTROL: the same harness against the fixed version (canonical slots adopted, `_disableInitializers()` added, delegatecall target allowlist hardened, storage gap restored) MUST yield covered-dry. Without a passing neg-control the confirmation is reward-hackable."
  - "GRADE BY REACHABILITY + BLAST RADIUS: is the primitive triggerable by ANY address (worst case — permissionless takeover/brick), or does it require the attacker to already hold a privileged role (capped)? Does the proxy hold funds/allowances directly, or is bricking it availability-only-but-critical (a core bridge/router, cf. Wormhole)?"

emits: [attempt, finding]
---

## What "confirmed" looks like here

A `confirmed` finding shows, on a local fork/vendored-source harness running the REAL in-scope proxy +
implementation at a pinned ref: (1) a reproduced concrete primitive — either (a) the raw
implementation's initializer is invoked by an unauthorized harness address and a privileged sink fires
(ownership taken, a selfdestruct-capable path executed), or (b) a storage read demonstrably aliases two
unrelated pieces of state (a proxyAdmin/owner slot is misread as an `Initializable` flag, letting a
guarded initializer be re-entered), or (c) a delegatecall provably lands on an address the harness
(attacker role) controls rather than the intended fixed/allowlisted target; (2) the protocol's OWN
invariant broken by an assertion failure (not a console marker) — implementation destroyed and every
dependent proxy call now reverts, OR an attacker-controlled address now holds admin/owner state, OR
delegatecall executed attacker-supplied bytecode inside the proxy's storage context; and (3) a passing
negative control (the patched/hardened version yields covered-dry). Missing (3) makes the confirmation
reward-hackable and routes to `needs_rework` at pocinator.

## Real disclosed anchors for this class (verified, cited — B2)

**Audius Governance Takeover — storage-collision proxy re-initialization (Jul 2022).**
`AudiusAdminUpgradeabilityProxy` stored its proxyAdmin address in the same storage slot OpenZeppelin's
`Initializable` contract packs its `initialized`/`initializing` booleans into; the low bytes of that
address were read as those booleans already indicating a re-initializable state. The attacker
repeatedly re-invoked governance-contract initializer functions to fabricate internal token-delegation
voting weight, the fabricated votes passed a malicious governance proposal, and the proposal executed a
transfer of 18,564,497 AUDIO from the community treasury to the attacker. This is the worked
storage-collision anchor for `evals/contract-audit/fixtures/audius-storage-collision/`.
[post-mortem](https://blog.audius.co/posts/audius-governance-takeover-post-mortem-7-23-22) ·
[tx](https://etherscan.io/tx/0x4227bca8ed4b8915c7eec0e14ad3748a88c4371d4176e716e8007249b9980dc9)

**Furucombo Hack — uninitialized Aave V2 proxy via transitive delegatecall (Feb 2021).** Furucombo
reused one `isValid()` authorization check both to gate inbound calls into its proxy and to authorize
outbound delegatecall targets; this let an attacker satisfy the check for an unrelated reason and
steer the proxy's delegatecall into a target under attacker control, transitively reaching Aave V2's
uninitialized `LendingPoolAddressesProvider` and hijacking it, ultimately draining ~$15M across 21
assets from 22 addresses that had granted Furucombo's proxy token approvals. This is the worked
delegatecall-target-hijack anchor for `evals/contract-audit/fixtures/furucombo-delegatecall-hijack/`.
[post-mortem](https://medium.com/furucombo/furucombo-post-mortem-march-2021-ad19afd415e)

## Grounding: severity + realized impact (B1 / B2 corpora)

- **B1 (`skills/oracles/references/defi-contest-adjudication-corpus.md`)** — the closest matched rows
  bracket this card's severity range: **Wormhole Uninitialized Proxy** (Immunefi, Critical,
  platform-assessed) — a prior bugfix reverted initialization on the Solana-side Ethereum core bridge
  proxy, leaving the UUPS implementation uninitialized and self-destructible, permanently bricking the
  bridge if exploited — grounds this card's critical tier for a permissionlessly-reachable, direct-call
  primitive on a high-value target. **C4 Non-fungible #186 (M-04)** — `Pool` inherits
  `OwnableUpgradeable` but never calls `__Ownable_init()`, so `owner()` stays zero; judge
  berndartmueller marked it primary/selected-for-report, sponsor confirmed and added an explicit
  `initialize()` call invoked at proxy deployment to close the gap — grounds this card's medium tier
  (a genuine init/layout gap, but no realized or demonstrated fund-loss path in the judged writeup,
  and closeable by a deployment-step fix rather than a code-level authorization change). Note
  **C4 Basin #52 (H-01)** (`WellUpgradeable._authorizeUpgrade` omitting `onlyOwner`) is the
  `evm.access-control` sibling anchor, not this card's — see "Not this card" below.
- **B2 (`skills/oracles/references/defi-exploit-chain-corpus.md`)** — both worked anchors above are
  realized, on-chain-adjudicated losses: Audius (class `storage-collision-proxy-governance`) and
  Furucombo (class `uninitialized-proxy`). The corpus's realized loss-by-class rollup lists each as a
  **single incident** (`storage-collision-proxy-governance (1)`, `uninitialized-proxy (1)`) — this
  class is realized and severe when it hits, but thinly represented in the corpus; say so honestly
  rather than imply a high base rate. The AUDIO/`$` figures are each incident's own post-mortem
  accounting, not an independently re-audited loss figure.

## Not this card

- An unprotected upgrade TRIGGER (`_authorizeUpgrade`/`upgradeTo` missing an owner/role check) is
  `evm.access-control`'s confirm step (cf. C4 Basin #52, H-01) — this card assumes the trigger is
  nominally gated and asks whether the delegatecall/storage mechanics underneath can still be abused
  regardless. The Audius and Furucombo incidents each chain a mechanics bug (this card) into an
  authorization bypass (`evm.access-control`) — both cards legitimately anchor on the same incidents
  from different mechanic lenses; attack the mechanics here, hand the resulting unauthorized privileged
  call to that card's confirm step.
- A plain reentrancy bug reached through a proxy-fronted contract is `evm.reentrancy` — the vulnerable
  class is checks-effects-interactions ordering, not delegatecall/proxy mechanics; that the vulnerable
  code happens to live behind a proxy is incidental.
- A delegatecall to a genuinely fixed, immutable, non-attacker-influenced target with a verified
  non-colliding storage layout is not this card's activation, even if the contract is superficially
  "upgradeable."

## Do not overclaim

- Standard-slot (EIP-1967) proxies structurally resist the Audius-shape collision — do not claim
  storage-collision without demonstrating a genuinely non-standard/custom slot AND an actual aliasing
  read; "the proxy is upgradeable" alone is not evidence.
- An uninitialized implementation that exposes no privileged sink reachable via a direct call (no
  ownership grant, no selfdestruct-capable path, no arbitrary-write) is not a critical/high finding
  merely because it is uninitialized — the reachable primitive must be shown.
- Both B2 anchors (Audius, Furucombo) are single incidents in the corpus's class rollup — realized and
  severe, but thin representation; do not inflate two anchors into "this is a high-base-rate class."
- A delegatecall-target-hijack confirmed only as an execution-flow assertion (recorded target !=
  expected registry entry) on a local fork is the confirm bar — actually driving the hijacked
  delegatecall into a live fund-moving sink, executing a governance proposal, or self-destructing a
  real implementation is a stronger, Zone-2 escalation requiring fresh human confirmation, never
  bundled into the base confirm step.
