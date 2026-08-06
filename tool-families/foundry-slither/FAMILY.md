# FAMILY — FOUNDRY-SLITHER (EVM contract-audit sensor + confirm-on-fork harness)

**Status:** S0 family profile — authority contract + detector→activation map. Arms-length subprocess
integration; no upstream code vendored, none executed as untrusted payload.
**Upstream (pinned, arms-length):** Slither `crytic/slither@0.10.4` (AGPL-3.0) · Aderyn
`Cyfrin/aderyn@0.1.9` (MIT) · Foundry `foundry-rs/foundry@v1.7.1` (MIT/Apache-2.0). These are standard,
widely-used EVM dev tools run as subprocesses; the manifest, broker, and oracle hold authority.
**Decision:** `docs/decisions/0008-smart-contract-audit-capability.md`.

## What this family is, for us

The EVM contract-audit sensor + confirm-on-fork layer. It may **detect / build / inspect / assert an
invariant on a local fork / propose**. It NEVER decides truth: no output becomes `confirmed` — a Slither
detector or a Foundry run proposes an activation signal or presents an invariant-break; the **oracle**
(`engine/whitebox-analysis.md` §4, regrade/pocinator) confirms. Two capabilities are exposed now:

- **Static detection (Slither / Aderyn) → activation signals.** Detectors run over the in-scope source
  and emit `attempt`/activation candidates for the EVM vuln cards — never a verdict.
- **Confirm-on-fork invariant assertion (Foundry / Anvil).** A local-fork test asserts the protocol's
  OWN invariant before/after a triggering sequence; the **assertion break** is the evidence (never a
  printed marker). A value-extraction/drain demonstration is a separate, Zone-2-gated surface (below).

## Detector → activation-signal map (Milestone-1 seed cards)

| Card | Slither detector(s) | Tier | Notes |
|---|---|---|---|
| `evm.reentrancy` | `reentrancy-eth`, `reentrancy-no-eth` (internal class `ReentrancyReadBeforeWritten`), `reentrancy-benign`/`-events` | STRONG | plus Aderyn `reentrancy_state_change`; map to the card's strong activation |
| `evm.read-only-reentrancy-price` | no direct detector — `reentrancy-*` on the writing path + manual "view reads state a guard doesn't cover" | RECON-ONLY | read-only reentrancy has no dedicated Slither detector; static tier is a lead, confirm-on-fork decides |

**Honest gap:** neither Slither nor Aderyn ships a generic oracle-price-manipulation detector; the
oracle/price class is recon-only at the static tier and leans on the confirm-on-fork step + card
procedure. Also: Slither/Aderyn are **not installed in the current authoring environment** — the
detector tier is declared-and-contracted here but was not run this session (Foundry `v1.7.1` IS
installed and the confirm-on-fork lane is exercised by the Milestone-1 fixture).

## What is exposed today vs staged

- **Now (`allowed_actions`):** `slither_detect`, `aderyn_detect`, `list_detectors`, `static_inspect`,
  `forge_build`, `fork_invariant_assert` — all benign, no value movement, no live chain.
- **Staged (`blocked_until`):** `value_moving_fork_poc` (a fork PoC that MOVES value to demonstrate
  impact) is **Zone-2** — gated on `human_impact_escalation_confirm` + signed scope + containment +
  cleanup; `symbolic_fuzz_lane` (Halmos/Echidna) is deferred to Milestone 2.

## Permanent non-negotiables (any phase)

- **No mainnet / live-target interaction, ever.** All dynamic work is a local Anvil/EVM fork with
  locally-minted, valueless test tokens. No live RPC, address, or key enters any plane (`redaction`).
- **The tool never emits `confirmed`.** Detection + invariant evidence only; the oracle judges.
- **Real-fork / real-invariant.** The fork is a real fork at a pinned block and the invariant is the
  protocol's OWN — never a mocked state or tautological assertion (`fake-client-poc-invariant-check`);
  the patched-twin neg-control must yield covered-dry (see `evals/contract-audit/fixtures/`).

## License note

Slither is AGPL-3.0 and Foundry MIT/Apache — used arms-length as subprocesses, not vendored. Vendored
target/fixture contracts carry their own SPDX headers (attribution preserved in each fixture).
