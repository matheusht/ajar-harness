# Decision 0008 — Smart-contract (Solidity/EVM) audit capability

**Status:** accepted as product direction; implementation not started — this ADR scopes the build. First
milestone is a thin end-to-end slice (below), not the full card set.\
**Effect:** applies Decision 0005's reasoning-directed, evidence-constrained white-box posture to a new
target class — **on-chain smart contracts** — the same way Decision 0007 applied it to black-box web.
Supersedes nothing. Extends the build plan in `docs/research/smart-contract-audit-capability-build-plan.md`
and consumes the blockchain oracle corpora (B1 `defi-contest-adjudication`, B2 `defi-exploit-chain`,
B3 `blockchain-client-cve`) already in `main`.

---

## Context

The crypto/fintech-Brazil positioning (`brand/`) points at the **smart-contract / DeFi application
layer**, where the audit market and the losses concentrate. The harness has already built the *judgment*
layer for this domain — B1 grounds DeFi severity (impact×likelihood, not CVSS) + disposition + dedup, B2
grounds realized exploit chains + real-loss impact — but it has **no capability to actually run a
contract audit**: no Solidity vuln cards, no contract-analysis tooling, no engagement flow. That is the
gap this decision opens.

The protocol/client layer is a *different* target class (consensus/relayer node software) that the
harness already worked (cosmos-2026-07) and that B3 back-anchors; it is out of scope here. This ADR is
the **contract** layer only.

The load-bearing risk is not "can we find contract bugs" — it is **can we confirm one without
reward-hacking**. A Foundry proof-of-concept that "passes" against a mocked or tautological state is the
exact failure mode `[[fake-client-poc-invariant-check]]` and `engine/whitebox-analysis.md` §4 warn about,
in a domain where a fork PoC is cheap to fake. The design below is built around that risk.

---

## Decision

### 1. Contract audit is a white-box specialization, not a new engine

A contract audit **is** a source-available white-box VR engagement and plugs into the machinery that
already exists — `engine/whitebox-analysis.md` (staged funnel §1, verification epistemics §4, model
roles §5), `engagements/_TEMPLATE/` (scope + ledgers + findings), the tool-family adapter contract
(`tool-families/*/FAMILY.md`, `engine/capabilities.md`), and the oracles (now DeFi-grounded by B1/B2).
The build adds **cards, a tool-family, a pipeline extension, and a fixture** — never a parallel stack.

### 2. Scope: EVM / Solidity first; Move and Rust-contract deferred

EVM/Solidity is where B1's corpus, the tooling maturity (Foundry/Slither), and the target market
concentrate. Move (Sui/Aptos) and Rust-contract (Solana/CosmWasm) are a **later tool-family**, added only
once the EVM slice has proven the loop. This mirrors 0007's "vertical-first, bar never moves."

### 3. Tool stack: Foundry + Slither (+Aderyn), as an arms-length tool-family; oracle owns truth

- **Static** — Slither (+ Aderyn) detectors produce **activation signals** only (list / inspect /
  propose). A detector NEVER emits `confirmed`.
- **Dynamic** — Foundry / Anvil provides a **mainnet-fork + invariant/PoC harness** — the confirm-on-fork
  step. The invariant break is *evidence*, adjudicated by the oracle; it is not itself a verdict.
- Wrapped under the existing adapter architecture (a `tool-families/<foundry-slither>/FAMILY.md` profile +
  manifest + broker; upstream reviewed statically, not vendored into Plane 1/2 — the P4RS3LT0NGV3
  precedent). **Symbolic/fuzz (Halmos / Echidna) is deferred** — added later as a capability, not built
  into the first family.

### 4. Rollout: thin end-to-end slice first, then scale — and the bar never moves

Do **not** author all 12 cards before the tooling exists. **Milestone 1** proves the whole loop on a
minimal slice (spec below); only once the loop confirms a real bug *and* returns `covered-dry` on the
patched twin does the card set scale to the full 12. Same discipline as 0007 §2.

### 5. Hard fences (non-negotiable, gate every dynamic step)

1. **No mainnet interaction, ever.** All dynamic work runs against a **local Anvil fork** at a pinned
   block, or a local devnet. No transaction is broadcast to any public network.
2. **An on-fork drain/impact PoC is a Zone-2 artifact.** A Foundry test that moves value in forked state
   to demonstrate impact is Zone-2 (README scope fence) → **explicit human impact-escalation confirm
   before creation, never autonomous** (`CLAUDE.md` §1.3), contained, logged in the engagement
   `cleanup.md`. Static analysis + a non-value-moving invariant assertion are Zone-1.
3. **The tool never emits `confirmed`.** Slither/Foundry propose; the oracle adjudicates (harness prime
   directive).
4. **Anti-reward-hacking on the fork.** The fork must be a **real mainnet fork at a real block** and the
   asserted invariant must be the **protocol's own real invariant** (e.g. `totalAssets ≥ Σ balances`,
   `Σ debt ≤ Σ collateral·CF`), never a mocked state or a tautological assertion. Verification-of-the-
   verification per `whitebox-analysis.md` §4; the neg-control (patched twin) must yield `covered-dry`.

### 6. Plane model: cards + tooling portable; the engagement lives with the target

Cards, the tool-family, and the pipeline extension are **portable** (Plane 1/2, in this repo). A specific
contract engagement — its `scope.md`, the fork block, the target addresses/commit, findings — lives
**with the target (Plane 3)**, per the harness plane model. No target specifics enter this repo.

### 7. Grounding: reuse the corpora already landed

Severity + disposition + dedup from **B1** (`defi-contest-adjudication-corpus`); realized chain shapes +
real-loss impact from **B2** (`defi-exploit-chain-corpus`); the DeFi cross-check in
`severity-precedent-oracle`. Each card's `severity_rubric` is B1/B2-anchored (impact×likelihood over
funds, **not** CVSS). No new corpus is required for the contract cards — they cite the existing anchors.

---

## Milestone 1 — the thin end-to-end slice (the concrete scope)

**Goal:** prove the full loop, non-reward-hackably, before scaling. Deliverables:

- **2 vuln cards** (`skills/vulns/`), full card schema, B1/B2-grounded severity:
  - `evm.reentrancy` — classic + read-only + cross-function; `safe_signal` = a benign local-fork
    invariant break (e.g. balance-accounting desync after a re-entrant call), no mainnet.
  - `evm.oracle-price-manipulation` — spot/LP-price / share-price manipulation feeding a lending or
    vault decision; `safe_signal` = a fork-simulated price move breaking a collateral/borrow invariant.
- **Tool-family v0** — `tool-families/<name>/FAMILY.md` + manifest wrapping: `slither` (detect →
  activation), `forge`/`anvil` (fork + invariant PoC). Capabilities registered in
  `engine/capabilities.md`; the `safe_signal` broker gates any value-moving test behind the Zone-2
  confirm (fence §5.2).
- **Pipeline extension** — `engine/whitebox-analysis.md` §7 gets a contract-domain funnel: Slither
  pre-filter → cheap classify → **reachability** (who can call / what's permissioned / upgradeable) →
  **confirm-on-fork** (Foundry invariant break) → **chainability** (B1/B2 §3b DeFi shapes) → **severity**
  (B1 impact×likelihood) → advisory. Plus a contract `recon-signals.md` note + a worked `scope.md`
  example in `engagements/_TEMPLATE/`.
- **Validation fixture** — one **pinned known-vulnerable contract** (a deliberately-vulnerable teaching
  target or a past audit-contest repo at a fixed commit with a known bug) **plus its patched twin**,
  under `evals/`. The fixture is the frozen slice a future ratchet rides.

**Acceptance gate (all must hold):**
1. The loop **confirms the real planted bug** end-to-end via a **real fork-invariant break** — not a
   mocked assertion.
2. The **patched twin yields `covered-dry`** — not a false positive (the anti-reward-hacking proof).
3. No mainnet interaction occurred; any value-moving PoC passed the Zone-2 confirm; `cleanup.md` logged.
4. `check-conformance.py` introduces no new failures; both cards pass the card schema.

Only when 1–4 hold does the card set scale to the full 12 (build plan Phase 1) and the tool-family gain
symbolic/fuzz capabilities.

---

## Success criterion

A contract engagement reaches the **same rigor bar** as the existing white-box flow: every `confirmed`
comes from the oracle over a real-fork invariant break with a passing neg-control, severity is B1/B2-
grounded, and no reward-hacked PoC survives verification-of-the-verification. Discovery is cheap; the
product is the **proof** (`brand/` thesis, `[[oslit-brand-positioning]]`).

## What remains deliberately flexible

- The exact fixture (teaching contract vs. a specific past-contest repo) — pick whichever gives the
  cleanest known-bug + patched-twin pair.
- The tool-family name and the precise Slither detector → activation-signal mapping.
- Whether read-only-reentrancy is its own card or a mode of `evm.reentrancy` (resolve during authoring).
- Move/Solana families, Halmos/Echidna, and multi-contract cross-protocol chainability — all deferred,
  earned by the vertical.
