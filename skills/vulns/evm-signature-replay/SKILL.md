---
id: evm.signature-replay
name: EVM Off-Chain Signature / EIP-712 Replay (Permit, Meta-Tx, Order)
description: >
  Prove that a signed off-chain authorization (an EIP-2612 `permit`, an EIP-712 meta-tx/forwarder
  request, a signed order/approval like `changeOrder`) can be accepted a second time, on a different
  chain, or against a different identity/account than the signer intended — because the `domainSeparator`
  is caller-supplied or frozen at deploy-time instead of re-derived from live `block.chainid`, a nonce
  or invalidation flag that should consume the signature is skippable, or the signed hash never binds
  the specific chain/identity/account it authorizes. A missing chain/identity binding or a skippable
  invalidation write is an activation signal; a finding requires a reproduced replay that gets a real
  signature accepted somewhere the signer never authorized.
type: vuln
# fixture_status: planned — the fixture directories cited below are NOT built. This card is
# researched (real incidents, real commits) but NOT calibrated: nothing executes against it.
# Remove this line only when every cited evals/ fixture directory exists and runs.
fixture_status: planned
owasp: "SWC-121 (Missing Protection against Signature Replay Attack), SWC-117 (Signature Malleability); CWE-347 (Improper Verification of Cryptographic Signature), CWE-294 (Authentication Bypass by Capture-replay). EVM smart-contract class."
atlas: "—"
patterns: []

activation:
  strong:
    - "a function that verifies an EIP-712 signature accepts `domainSeparator` as a caller-supplied argument rather than deriving it internally from `block.chainid`/`address(this)` at verification time — the exact C4 next-generation H-01 shape: the same signed payload hashes identically on every chain the contract is deployed to at the same address"
    - "`DOMAIN_SEPARATOR`/the EIP-712 domain typehash is computed ONCE in the constructor from `block.chainid` captured at deploy time and cached as `immutable`/constant with no runtime re-check for a chainid mismatch — a hard fork produces two live chains sharing pre-fork history, so a pre-fork signature replays on whichever fork didn't get an intentional re-deploy (the Golom #391 shape)"
    - "a signed authorization is consumed but the state that should invalidate it (a nonce increment, a used-hash mapping, a status/lifecycle flag) is written on a code path a specific function bypasses, or isn't written at all — the Rigor #95 shape: `Tasks.unApprove()` lacked the modifier that would have blocked replaying a stale approval into a funds-releasing `setComplete()`"
    - "the same signer key backs multiple distinct on-chain accounts/identities/vaults and the signed message hash does not bind the target identity/account address into what's hashed — the Ambire #39 shape: a signature valid for identity A recovers and authorizes unchanged against identity B"
  weak:
    - "domainSeparator/nonce plumbing looks nonstandard but the actual verifying function still independently re-derives the separator or checks nonce state on every call — confirm the check is live (not dead code / not skippable via an alternate entrypoint) before treating as strong"
    - "the contract uses OpenZeppelin's `ERC20Permit`/`EIP712` base with the modern `_domainSeparatorV4()` fork-detection pattern (recomputes when `block.chainid` != a cached value) — looks like a candidate but the library already resists both hard-fork and address-reuse replay; only strong if a local override or a custom verify path bypasses it"
  negative:
    - "the nonce increments monotonically and is checked+written atomically with signature consumption (no window to reuse), domainSeparator is derived internally from live `block.chainid`+`address(this)` at verification time (never cached across a fork, never a function parameter), and no signer key is shared across distinct protected identities/accounts → likely held; record as a positive control (the xDeFi #92 shape: sponsor+judge agreed OpenZeppelin's nonce-based ERC20Permit prevents replay)"

safe_signal:
  proxy: >
    a LOCAL Foundry harness vendoring the REAL vulnerable contract at its pinned in-scope commit (never
    a reimplementation) — the fixture plan `evals/contract-audit/fixtures/next-generation-forwarder-replay/`:
    vendor `Forwarder.sol` from `code-423n4/2025-01-next-generation` at the pinned contest commit
    `f1b9fa13a` (verified real code: `verify()`/`execute()` accept `bytes32 domainSeparator` as a caller
    argument and feed it straight into `_verifySig`'s `keccak256("\x19\x01", domainSeparator, ...)`
    digest with no internal `block.chainid` re-derivation — the exact C4 H-01 root cause, 35 duplicate
    submissions merged, judged High). Deploy the identical bytecode at the identical address on two
    local Anvil instances with DIFFERENT chain ids; sign one `ForwardRequest` + that deployment's
    `domainSeparator` off-chain for "chain A"; replay the identical calldata against "chain B"'s
    deployment. The benign invariant assertion: a meta-tx the signer authorized only for chain A must
    NOT execute on chain B — assert this FAILS on the vulnerable ref (`execute()` succeeds, `nonces`
    increments, a value transfer the signer never intended for chain B goes through), using only
    locally-minted valueless test tokens and locally-generated throwaway keys, never any external
    party's funds. The PATCHED twin applies the canonical EIP-712 remediation this card requires —
    mirroring OpenZeppelin's shipped `EIP712._domainSeparatorV4()` fork/address re-derivation pattern
    (read live from `OpenZeppelin/openzeppelin-contracts`): remove `domainSeparator` as a parameter and
    re-derive it internally from `block.chainid`/`address(this)` inside `_verifySig`, so the replayed
    digest no longer recovers `req.from` on chain B and `execute()` reverts — covered-dry. State plainly
    in any report that this patch is a locally-applied remediation mirroring the industry-canonical fix,
    NOT an upstream merged commit — the Next Generation team held deployment after H-01 and no public
    fix commit exists in that repo. The neg-control is mandatory (fake-client-poc-invariant-check) — a
    harness that "confirms" against both refs identically is tautological.
  never: >
    never sign with, submit to, or replay against any live mainnet/testnet deployment, any real user's
    key, or any contract/party you do not control; the harness uses only locally-generated disposable
    ECDSA keypairs and locally-minted valueless test tokens on local Anvil/EVM instances. A
    value-extraction PoC that moves a real, value-bearing asset (as opposed to a pure
    replay-accepted/invariant-break assertion on throwaway test tokens) is a Zone-2 artifact — create
    only under explicit human impact-escalation authorization, contained and logged.

impact_escalation:
  enabled_by: scope.md#impact_demo_authorized
  requires: >
    a benign local invariant-break assertion (replay accepted where it shouldn't be, on locally-minted
    test tokens) needs no per-artifact pause; a value-moving/drain PoC against a value-bearing token or
    a live-style multi-account setup is Zone-2 and requires a fresh explicit human confirmation before
    creation
  containment: "local disposable Foundry/Anvil environment only; locally-minted valueless test tokens; disposable local keypairs, never a real signer; logged in the fixture cleanup.md and the engagement cleanup ledger"

oracle: [whitebox-analysis, regrade-oracle, pocinator-oracle]
severity_rubric: { permissionless_signature_replay_fund_drain_reproduced: critical, cross_chain_or_cross_identity_replay_reproduced_ordinary_precondition: high, signature_or_nonce_invalidation_bypass_reproduced_role_gated_participant: high, hardfork_replay_via_frozen_domain_separator_no_reproduced_drain: medium, replay_path_identified_no_reachable_drain_or_nonce_protected: low }

procedure:
  - "MAP SIGNED AUTHORIZATION SURFACES: enumerate every function that accepts an off-chain signature (permit, meta-tx/forwarder, signed order/approval) and for each, trace where domainSeparator, typehash, and nonce/invalidation state come from."
  - "CLASSIFY THE REPLAY VECTOR: cross-chain (domainSeparator caller-supplied or frozen-immutable, not re-derived from block.chainid), cross-identity (a shared signer key not bound into the hash), same-chain nonce/invalidation bypass (consumed-signature state skippable on some path), or malleability (non-canonical signature recovery, no per-message uniqueness). Each needs a different reproduction."
  - "CONFIRM THE DOMAIN BINDING: read exactly how domainSeparator is produced AT VERIFICATION TIME — a literal function parameter, a cached immutable set once at deploy, or a value re-derived live from block.chainid/address(this) (OZ `_domainSeparatorV4()`-style). Only the last resists both hard-fork replay and multi-chain-same-address replay."
  - "CONFIRM NONCE/INVALIDATION ENFORCEMENT: trace every code path that is supposed to write the nonce/used-hash/status flag that invalidates a consumed signature; find any function or branch that skips it (Rigor #95's missing-modifier shape)."
  - "PIN THE INVARIANT: state the protocol's OWN invariant the replay breaks (a signature valid once authorizes value exactly once; a signature scoped to chain/identity A never authorizes an action on chain/identity B). This is the confirm-on-fork assertion, not a printed marker (whitebox-analysis §4)."
  - "REPRODUCE ON A LOCAL HARNESS WITH THE REAL CONTRACT: vendor the real contract at its pinned in-scope commit; sign one authorization; replay it across the second chain/identity/consumed-state path; assert the invariant breaks. Never a reimplementation of the vulnerable logic."
  - "RUN THE PATCHED/NEGATIVE CONTROL: the same harness with domainSeparator internally re-derived (or the missing invalidation guard restored) MUST yield covered-dry. Without a passing neg-control the confirmation is reward-hackable."
  - "TRACE REACHABILITY & PRECONDITIONS: does the replay require a rare externally-triggered event (an actual hard fork — the Golom/Aloe II contested Medium-vs-invalid split) or an ordinary, attacker-observable condition (the protocol's own multi-chain same-address deployment, an already-authorized signer)? A rare/external-condition-gated path caps severity per the stricter judging bar; an attacker-triggerable/ordinary-condition path does not."
  - "CHECK RELEASE ELIGIBILITY: confirm the exact pinned in-scope commit/deployment still lacks the fix; internal domainSeparator re-derivation or restored nonce/invalidation enforcement already shipped takes the disclosed instance out of scope — cite it as precedent, not a live finding."

emits: [attempt, finding]
---

## What "confirmed" looks like here

A `confirmed` signature-replay finding shows, on a local harness running the REAL in-scope contract:
(1) a signature legitimately produced for one chain/identity/consumption is reproduced accepting a
SECOND time, on a different chain, against a different identity, or after the state that should have
invalidated it, (2) the protocol's OWN invariant broken by an assertion failure (a value transfer or
state change the signer never authorized for that context actually executes) — not a console marker,
and (3) a passing negative control (domainSeparator internally re-derived, or the invalidation guard
restored, yields covered-dry). Missing (3) makes the confirmation reward-hackable and routes to
`needs_rework` at pocinator.

## Real disclosed anchors for this class (verified, cited)

- **Code4rena 2025-01-next-generation, H-01 — cross-chain signature replay via caller-supplied
  `domainSeparator`** (High, C4; 35 duplicate submissions merged into H-01). The Forwarder's `verify`/
  `execute` accept `domainSeparator` as a function argument and pass it straight into `_verifySig`'s
  digest with no internal `block.chainid` check, so a signature captured on one chain replays unchanged
  on any other chain where the protocol is deployed at the same address (the corpus's multi-chain
  MPC-signer deployment precondition, an ordinary architecture choice, not a rare event). Verified
  directly against the live contest repo (`code-423n4/2025-01-next-generation`, commit `f1b9fa13a`,
  `contracts/Forwarder.sol`): `verify`/`execute` at lines ~77–110 both take `bytes32 domainSeparator`
  as a parameter, and `_verifySig` builds `keccak256("\x19\x01", domainSeparator, structHash)` from it
  unchecked. This is the primary worked `safe_signal` fixture for this card.
- **Code4rena 2022-07-golom-findings #391 — hard-fork replay via an immutable `DOMAIN_SEPARATOR`**
  (Medium, C4). Judge dmvt, quoted verbatim: "I'm going to leave this as a medium risk. It would be a
  very high-impact scenario, but it relies on the external factor of a hard fork. That said, hard forks
  can and do happen." Verified against the live contest repo (`code-423n4/2022-07-golom`, `contracts/core/GolomTrader.sol`):
  the constructor reads `chainid()` once and bakes it into an `immutable EIP712_DOMAIN_TYPEHASH`, never
  re-derived afterward.
- **Sherlock 2023-10-aloe-judging #44 — the SAME hard-fork-replay mechanism ruled invalid/Non-Reward.**
  Judge panprog, quoted verbatim: "invalid, because this is the problem to be solved by the forked
  chain, not by the protocol. Existing chains are handled correctly by the protocol." This is the
  corpus's own flagged cross-platform contrast pair with Golom #391 — same mechanism, opposite
  disposition, because C4's bar accepts "a valid attack path with a stated assumption" while Sherlock's
  bar excludes an externally-triggered, low-likelihood precondition. Use this pair to cap severity
  honestly on the hard-fork-specific sub-mechanism, not the caller-supplied-domainSeparator sub-mechanism.
- **Code4rena 2021-10-ambire-findings #39 — cross-identity signature replay via a shared signer key**
  (High, C4; sponsor confirmed, resolved). Judge (GalloDaSballo), quoted verbatim: "The warden identified
  a Signature Replay attack, allowing to re-use a signature throughout the system. Requiring the identity
  to be part of the signatures mitigates the vulnerability... The sponsor has mitigated in a subsequent
  PR." A single QuickAccount signer key backs multiple distinct on-chain 'identity' wallets that opted
  into the same `accHash`, and the signed-message hash for send/cancel/execScheduled never binds the
  specific identity — a signature valid for one identity replays against another.
  Dedup: `signature-replay-shared-signer-cross-identity`.
  [Ambire — Code4rena #39](https://github.com/code-423n4/2021-10-ambire-findings/issues/39)
- **Code4rena 2022-08-rigor-findings #95 — signature/state never invalidated after consumption**
  (High, C4; sponsor confirmed, valid). Mechanism per the corpus: a signed `changeOrder()`/`setComplete()`
  message that was already validly used is never invalidated after being consumed; a subcontractor (or
  colluding parties) reuses the same still-valid signature to re-trigger `changeOrder()`, toggling a
  task's price/subcontractor back to a state that satisfies the funding check, then `setComplete()` is
  re-run against the same stale signature set. Verified directly against the live contest repo
  (`code-423n4/2022-08-rigor`, `contracts/libraries/Tasks.sol`): `unApprove()`'s own doc comment says
  `@dev modifier onlyActive` but the function signature carries NO modifier — the missing-guard root
  cause is real code, not a paraphrase. Judge zgorizzo69: "very nice wrap up." Dedup:
  `signature-replay-repeated-fund-release`. Reachability is participant-gated (a project subcontractor
  role), which is why C4 rated High rather than Critical.
- **Immunefi Bug Fix Review — Polygon Plasma Bridge WithdrawManager double-spend** (Critical,
  Immunefi platform-assessed, ~$2M bounty). `WithdrawManager` decoded the Merkle-proof branch mask two
  different ways (nibble-array in one path, uint256 in another), so semantically identical proofs had
  multiple valid encodings and the same burn/exit receipt could be replayed — up to 223x per the
  postmortem — permissionlessly against the bridge. Authority type is program postmortem/payout tier,
  not an adversarial contest-judge disposition; cited here as the corpus's clearest fully-permissionless
  signature/proof-replay fund-loss anchor, grounding the `critical` rubric tier.
- **Contested, recorded not asserted — Code4rena 2022-01-xdefi-findings #92** (invalid). Reported as a
  3/High-Risk signature-replay/malleability bug; sponsor (deluca-mike): "The permit function is
  implemented in the ERC20 contract... Nonces are used in the [contract] to prevent replay, thus no
  replay is possible," citing OpenZeppelin's `ERC20Permit` nonce mechanism. C4 judge Ivshti: "agreed with
  sponsor." This is the corpus's worked negative control — a properly nonce-enforced permit is NOT this
  card's finding — grounds the `negative` activation signal.

## Grounding: severity + realized impact (B1 / B2 corpora)

- **B1 (`skills/oracles/references/defi-contest-adjudication-corpus.md`)** — signature-replay is a
  contest-graded class spanning judged Critical (Immunefi Polygon Plasma, platform-assessed,
  permissionless) down to Medium (Golom #391, hard-fork-gated) and invalid (Aloe II #44 same
  mechanism on Sherlock's bar; xDeFi #92 nonce-protected permit). The corpus's own cross-platform
  contrast line names this exact pair explicitly: "immutable `DOMAIN_SEPARATOR` replay-after-hardfork
  rated Medium at Golom (C4) but invalid/Non-Reward at Aloe II (Sherlock)" — the single most load-bearing
  calibration signal for this card's severity_rubric. High-tier anchors (next-generation H-01, Ambire
  #39, Rigor #95) share an ordinary, attacker-reachable precondition rather than a rare external event,
  which is exactly why they cleared C4's bar at High while the hard-fork-specific mechanism stayed
  capped/contested.
- **B2 (`skills/oracles/references/defi-exploit-chain-corpus.md`)** — this corpus's IN-set
  `signature-proof-bridge` rows (Wormhole ~$320–326M, BSC Token Hub ~$566M face value, Qubit ~$80M) are
  a SIBLING mechanism — forged/duplicate cross-chain proof signatures accepted by a bridge relayer/light
  client — not this card's EIP-712 domain-separator/permit/meta-tx replay shape; do not cite them as
  direct anchors for this class, only as the realized-loss ceiling for "signature verification gap →
  fund loss" broadly. The one B2 row that IS this card's exact mechanism, `KiloEx MinimalForwarder
  signature-validation`, is recorded **Contested, not asserted** in that corpus (primary sourcing only
  relayed via an unfetchable X/402 thread, tx merely format-checked not RPC-verified) — cite it only as
  a contested data point, never as a confirmed realized-loss anchor.

## Not this card

- A hard-fork-replay path via a frozen/immutable `DOMAIN_SEPARATOR` with no reproduced acceptance on a
  second live chain → activation signal capped at `medium`, and honestly flag the Golom/Aloe II
  cross-platform disposition split in any writeup — this exact mechanism has been judged both Medium
  and invalid on real programs depending on the bar for an externally-triggered precondition.
  Sibling `signature-proof-bridge` mechanisms — a bridge relayer/light-client accepting a forged or
  duplicate-encoded cross-chain PROOF signature (Wormhole's sysvar-account check, BSC's IAVL proof
  forgery) — are a related but distinct root cause (bridge message/proof verification, not EIP-712
  domain/nonce plumbing); route those to a bridge/cross-chain-messaging card, not this one.
- A `permit`/EIP-712 scheme that already re-derives `domainSeparator` live from `block.chainid` (OZ
  `_domainSeparatorV4()`-style) and enforces monotonic nonces atomically with consumption → likely held,
  not a finding (the xDeFi #92 shape).

## Do not overclaim
- A caller-supplied or frozen-immutable `domainSeparator`, or a missing invalidation modifier, is an
  activation signal, not a finding — you must reproduce an actual accepted replay (a second chain, a
  second identity, or a stale-signature reuse) breaking a real invariant, with a passing patched-twin
  neg-control.
- Severity depends on the replay's precondition, not just the mechanism: an ordinary, attacker-reachable
  precondition (a protocol's own multi-chain same-address deployment, an already-authorized signer
  sharing a key across identities) supports High; a rare externally-triggered precondition (an actual
  chain hard fork) is contested down to Medium/invalid depending on the judging bar — state which one
  applies and cite the precedent honestly rather than defaulting to the higher tier.
- Disclosed "$"/bounty figures are the reporting program's exposure or payout-tier estimate unless a
  realized on-chain loss with a transaction is cited — state the distinction in any report, and do not
  borrow B2's `signature-proof-bridge` realized-loss figures for this card's mechanism (they are a
  sibling root cause, not this one).
