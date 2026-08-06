# Build plan: white-box smart-contract (Solidity/EVM) audit capability

> Status: build plan, ready for operator review. This document does not itself authorize a build.
> This is **not** a corpus-grounding pass — it is a phased capability build. Its severity/disposition/
> dedup grounding is **B1 (landed)**; its chainability/impact grounding is **B2 (planned)**; its
> pipeline already exists (`engine/whitebox-analysis.md`). The goal is to make the harness able to
> *run* a contract audit at the same rigor bar as the existing source-available flow.

## 1. Goal and the "don't reinvent" principle

Make the harness able to **run a white-box smart-contract (Solidity/EVM) VR engagement end to end** —
recon → candidate hunt → confirm-on-fork → chainability → severity → advisory → triage — under the
existing gates, ledgers, and anti-reward-hacking discipline. The contract engagement is a **white-box
engagement**; it plugs into machinery that already exists rather than a parallel stack:

| Need | Already exists — reuse it | New work |
|---|---|---|
| Staged funnel + anti-reward-hacking + model roles | `engine/whitebox-analysis.md` (§1 funnel, §4 verification epistemics, §5 roles) | §7 contract-domain extension |
| Engagement flow (scope, ledgers, findings, cleanup) | `engagements/_TEMPLATE/` (scope.md, events/attempts/artifacts.jsonl, findings/, evidence/) | contract-flavored scope.md + recon-signals |
| Judgment layer (severity, disposition, dedup) | oracles now DeFi-grounded by **B1** | wire cards → B1 anchors |
| Chainability shapes | `chainability.md` §3b (B1 contest chains; **B2** realized chains) | consume, don't author |
| Tool integration contract (arms-length, oracle-owns-truth) | `tool-families/*/FAMILY.md` + `engine/capabilities.md` + `docs/tool-family-adapter-architecture.md` | a Foundry/Slither family |
| Zone-2 fence + gates | `engine/gates.md`, README scope fence, `engine/escalation.md` | one ADR extending it to on-fork PoCs |

So the build is four concrete deliverables: **vuln cards**, a **tool-family**, a **pipeline+template
extension**, and a **validation fixture** — not a new engine.

## 2. Hard fences (decide before any build)

1. **No mainnet interaction, ever.** All dynamic work runs against a **local fork** (Anvil/Foundry) at a
   pinned block, or a local devnet. No transaction is ever broadcast to a public network.
2. **An on-fork drain PoC is a Zone-2 artifact.** A Foundry test that moves value in forked state to
   demonstrate impact is Zone-2 (see README scope fence) → **explicit human impact-escalation confirm
   before creation, never autonomous** (`CLAUDE.md` §1.3), contained, logged in `cleanup.md`.
3. **Static-only on upstream tool source.** Slither/Foundry are arms-length subprocesses under the
   tool-family adapter contract; upstream code is reviewed statically, not vendored into Plane 1/2 (the
   P4RS3LT0NGV3 precedent).
4. **The tool never emits `confirmed`.** A Slither detector or a Foundry run *proposes*; the oracle —
   never the tool or the Hunter — emits `confirmed` (the harness prime directive). The fork-invariant is
   evidence, not a verdict.
5. **Anti-reward-hacking on the fork (the fake-client lesson).** The fork must be a **real mainnet fork
   at a real block** and the asserted invariant must be the **protocol's real invariant** — never a
   mocked state or a tautological assertion that "confirms" a reward-hacked PoC
   (`fake-client-poc-invariant-check`). Verification-of-the-verification per `whitebox-analysis.md` §4.

## 3. Phases, deliverables, gates

### Phase 0 — scope, fences, ADR  *(smallest; unblocks the rest)*
- **Deliverable:** an ADR in `docs/decisions/` ("white-box contract-audit capability"); a
  contract-flavored `scope.md` addendum (in-scope contracts + addresses/commit, the **invariants**
  asserted, the fork block + RPC, the account model, impact-demo auth y/n) and a `recon-signals.md`
  guide (what a contract recon emits: external calls, privileged setters, oracle reads, upgradeability,
  ERC-4626 vaults, delegatecall).
- **Gate:** the Zone-2-on-fork fence (§2.2) is written into `engine/gates.md` / the scope fence and
  signed off. No dynamic work authorized before this.

### Phase 1 — vuln cards  *(the core knowledge; grounded by B1, ideally after B2)*
- **Deliverable:** a Solidity/EVM vuln-card set under `skills/vulns/`, each with the full card schema
  (`activation` signals, `safe_signal`, `impact_escalation`, `oracle`, `severity_rubric`, `procedure`,
  `emits`) authored via the `writing-for-agents` skill. Proposed set (matches B1's class taxonomy so the
  `severity_rubric` is directly B1-anchored):
  reentrancy (classic / read-only / cross-function); oracle-price-manipulation; access-control
  (missing-modifier / unprotected-init / privileged-setter); arithmetic-rounding-precision;
  first-depositor-ERC4626-share-inflation; signature-permit-replay; slippage-MEV-sandwich;
  flash-loan-governance; delegatecall-proxy-upgrade-init; unchecked-external-call-return;
  dos-unbounded-gas-griefing; accounting-invariant-break.
- **Grounding:** each card cites real anchors — **B1** (contest disposition + judged severity), **B2**
  (realized-loss impact), and where useful a known fix commit. `severity_rubric` uses B1's
  impact×likelihood tiers, **not** CVSS.
- **Gate:** each card's `safe_signal` is a **benign local-fork invariant-violation demo** (e.g. "on an
  Anvil fork, `totalAssets() >= Σ balances` breaks after the sequence") — never a mainnet action; every
  card passes `check-conformance.py`.

### Phase 2 — tool-family (Foundry + Slither)  *(the heaviest new component)*
- **Deliverable:** `tool-families/<name>/FAMILY.md` under the adapter architecture — a profile+contract,
  not vendored code. Two capabilities: **Slither/Aderyn** static detectors → `activation` signals
  (arms-length, list/inspect/propose only); **Foundry/Anvil** fork + invariant/fuzz harness → the
  confirm-on-fork step. Register capabilities in `engine/capabilities.md` +
  `engine/operation-capabilities.json`; the manifest+broker+oracle own authority.
- **Gate:** static-only review of upstream; PoC runs only on a local fork; the `safe_signal` broker
  gates any value-moving test behind the Zone-2 confirm (§2.2).

### Phase 3 — pipeline + engagement-template wiring
- **Deliverable:** extend `engine/whitebox-analysis.md` §7 with the contract-domain funnel — Slither
  pre-filter → cheap classify → **reachability** (who can call / what's permissioned / is it upgradeable)
  → **confirm-on-fork** (Foundry invariant break) → **chainability** (B1+B2 §3b DeFi shapes) →
  **severity** (B1 impact×likelihood) → advisory. Add the contract `recon-signals.md` + a worked
  scope.md example to `engagements/_TEMPLATE/`.
- **Gate:** a dry-run of the funnel on a toy contract routes end-to-end with a rigor gate at each
  narrowing (no auto-`confirmed`).

### Phase 4 — validation fixture (the frozen-eval slice)
- **Deliverable:** a hermetic engagement against a **known-vulnerable pinned contract** (a deliberately
  vulnerable teaching target, or a past audit-contest repo at a fixed commit with a known planted bug)
  under `evals/`, proving the pipeline finds the planted bug **end to end via a real fork-invariant
  break** — not a mocked assertion.
- **Gate:** the fixture confirms the real bug **and** a negative control (a patched version) yields
  `covered-dry`, not a false positive — the anti-reward-hacking proof (§2.5). This becomes the frozen
  slice a future autoresearch ratchet rides.

## 4. Dependencies, sequencing, effort

- **B1 (done)** grounds Phase-1 severity/disposition. **B2 (planned)** grounds Phase-1 chainability +
  impact realism — **recommended before Phase-1 card severity is finalized** (so cards cite realized
  impact, not just judged). **B3 is orthogonal** (client layer) and can run fully in parallel; it does
  not gate this build.
- **Order:** Phase 0 → (B2 in parallel) → Phase 1 → Phase 2 → Phase 3 → Phase 4. Phases 1 and 2 can
  overlap once Phase 0 fences are set.
- **Effort:** **High** — this is the largest item of the three (B2/B3 are Med / Low-Med corpus passes).
  Phase 2 (tooling) and Phase 4 (a non-reward-hackable fixture) are the hard parts; Phase 1 is
  bounded by B1's taxonomy.

## 5. Open decisions for the operator

> **Operator decisions (2026-08-05 / -08-06) — now recorded in ADR
> [`docs/decisions/0008-smart-contract-audit-capability.md`](../decisions/0008-smart-contract-audit-capability.md):**
> sequencing **B3 → B2 → this build** (both corpora now landed in `main`); domain **EVM/Solidity first**
> (decision 1); **tool stack Foundry + Slither (+Aderyn)**, symbolic/fuzz deferred (decision 2);
> **thin end-to-end slice first** — 2 seed cards (`evm.reentrancy`, `evm.oracle-price-manipulation`) +
> a Foundry fork-PoC + one known-vuln fixture and its patched twin — before the full card set
> (decisions 3–4); planes per §5.5. See ADR 0008 for the Milestone-1 spec + acceptance gate.

1. **Scope: EVM/Solidity first only, or also Move (Sui/Aptos) / Rust-contract (Solana/CosmWasm)?**
   **DECIDED — EVM/Solidity first** — where B1's corpus, the tooling maturity (Foundry/Slither), and the
   Brazil crypto/fintech market concentrate; Move/Rust as a later family.
2. **Tool-family stack: Foundry + Slither (+ Aderyn)?** *Recommend yes* — vs Hardhat/Echidna/Halmos.
   Foundry's fork + invariant testing is the cleanest confirm-on-fork; Slither the standard detector
   set. (Halmos/symbolic could be a later capability.)
3. **First card set: the 12 above?** *Recommend yes* — it mirrors B1's class taxonomy 1:1 so grounding
   is direct.
4. **Do B2 before finalizing Phase-1 card severity?** *Recommend yes* — realized-impact anchors make the
   `severity_rubric` measured, not just judged.
5. **Is this a portable-repo capability or does it live per-target (Plane 3)?** The cards + tool-family +
   pipeline are portable (Plane 1/2); a specific contract engagement (scope, fork, findings) lives with
   the target (Plane 3), per the harness plane model.
