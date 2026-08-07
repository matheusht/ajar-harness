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
| `evm.reentrancy` | `reentrancy-benign`/`-events` (+ `reentrancy-eth`/`-no-eth`) | STRONG (activation) | **Empirically verified (Slither 0.11.6):** fires on the JPEG'd `YVault.deposit` (`token.safeTransferFrom` → `_mint` after) — but on **BOTH** the vuln and patched refs (2 vs 3 findings), because the fix reorders the *supply read*, not transfer-before-mint. So it is **activation, not a verdict** — confirm-on-fork distinguishes them. Aderyn `reentrancy_state_change` not run. |
| `evm.read-only-reentrancy-price` | no direct detector — `reentrancy-*` on the writing path + manual "view reads state a guard doesn't cover" | RECON-ONLY | read-only reentrancy has no dedicated Slither detector; static tier is a lead, confirm-on-fork decides |

**Empirical note (this session):** Slither `0.11.6` is **installed and run** — the `evm.reentrancy` row
above is a real result. Its key lesson is the tool-family's whole thesis in miniature: the reentrancy
detector fires **identically on the vulnerable and the fixed contract**, so a Slither hit is an
*activation signal*, never a confirmation — the oracle over the confirm-on-fork invariant break (with the
covered-dry patched twin) is what decides. **Honest gaps:** Aderyn was not run; neither Slither nor
Aderyn ships a generic oracle-price-manipulation detector (the oracle/price class stays recon-only).

## What is exposed today vs staged

- **Now (`allowed_actions`):** `slither_detect`, `aderyn_detect`, `list_detectors`, `static_inspect`,
  `forge_build`, `fork_invariant_assert` — all benign, no value movement, no live chain.
- **Staged (`blocked_until`):** `value_moving_fork_poc` (a fork PoC that MOVES value to demonstrate
  impact) is **Zone-2** — gated on `human_impact_escalation_confirm` + signed scope + containment +
  cleanup; `symbolic_fuzz_lane` (Halmos/Echidna) stages here.

**Tooling status (this session):** Foundry `v1.7.1`, Slither `0.11.6`, and Halmos `0.3.3` are installed
and available; Echidna is not installed. Slither is **run** (the empirical `evm.reentrancy` result
above). The Halmos symbolic lane is ready to activate — the natural first symbolic proof is
"the v4.9 ERC-4626 vault has no first-depositor profit for ANY donation" over the
`erc4626-first-depositor` fixture — and is the immediate next tooling increment.

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
