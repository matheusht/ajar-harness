# Milestone-1 validation fixture — JPEG'd yVault reentrancy (Code4rena #81)

The frozen, **non-reward-hackable** validation fixture for the EVM contract-audit capability
(ADR `docs/decisions/0008-smart-contract-audit-capability.md`, Milestone 1). It proves the acceptance
gate: the **real** vulnerable contract breaks its own invariant, and the **patched twin** — on the
byte-identical harness — does not.

## Provenance (real contract at both refs — verified via GitHub API)

- **Vulnerable:** `jpegd/core@651e50704997d7d15241b5c9a1c03199293865d0` (`src/vuln/yVault/YVault.sol`),
  content-identical to the audited contest snapshot `code-423n4/2022-04-jpegd@e72861a`.
- **Patched:** `jpegd/core@cb7af8ab3145cc01ea8718ab4d4cb2bb600657a6` (`src/patched/yVault/YVault.sol`),
  commit *"fix reentrancy issue"* (PR #19 `code4rena-81`) — the accepted fix for **Code4rena #81**
  (High-Risk, sponsor-confirmed, resolved).
- Both `YVault.sol` are vendored **byte-for-byte** (only their directory depth is arranged so the
  original `../../interfaces/` imports resolve). OpenZeppelin `v4.7.3` is vendored under `lib/`.
- License: the JPEG'd contract is **GPL-3.0** (per-file SPDX); OZ is MIT. Attribution preserved.

## The bug (C4 #81) and the fix

Vulnerable `deposit`: `balanceBefore = balance()` → `token.safeTransferFrom(...)` (a control-giving
token re-enters here) → `supply = totalSupply()` → mint. A split reentrant deposit mints against a
stale `balanceBefore` with an inflated `supply`. Fix: read `supply` **together with** `balanceBefore`
before the transfer, and move `safeTransferFrom` **last**.

## Run it

```
forge test -vv        # from this directory
```

Expected (both pass): the two tests ARE the acceptance gate.

| Test | Ref | Result | Meaning |
|---|---|---|---|
| `test_vuln_reentrancy_breaks_invariant` | vulnerable | attacker **1250 shares**, **PnL +111e18** | fair-share invariant **breaks** (real bug) |
| `test_patched_reentrancy_patched_control` | patched | attacker **1000 shares**, **PnL 0** | invariant **holds** — **patched-control** neg-control |

The 1250-vs-1000 share split and the +111 profit reproduce the C4 #81 write-up exactly — fidelity to
the real mechanism, not an accidental `PnL > 0`. The signal is an **assertion failure**, never a
printed marker (`skills/ajar-investigate/SKILL.md` §4). The mandatory **patched-control on the patched twin**
is what makes the fixture non-reward-hackable (`control-invariant-check`).

## Safety & authorization (ADR 0008 §5)

- **No mainnet, ever.** Runs only on a local Foundry/Anvil EVM with locally-minted, **valueless** test
  tokens. No live network, no live target, no real address.
- This demonstrates real value movement in local state (attacker PnL) → a **local-sandbox** artifact per
  ADR 0008 §5.2. Built under **explicit operator local-sandbox authorization** (this session), scoped to
  local disposable PoCs against the **public, already-disclosed-and-patched** JPEG'd contract only.
  Contained here; no drain against any live system exists or is implied.
- The harness (`src/harness/`) is a minimal reproduction aid (a control-giving token + a reentrant
  attacker + a zero-strategy controller), not a weaponized exploit for any deployed contract.
