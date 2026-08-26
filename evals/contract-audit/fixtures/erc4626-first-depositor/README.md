# Milestone-1 validation fixture — ERC-4626 first-depositor share inflation

The verified fixture for the `evm.first-depositor-share-inflation` card (ADR 0008, Milestone 1). It
proves the acceptance gate using a **canonical real before/after**: OpenZeppelin ERC-4626 at **v4.8.3**
(pre-mitigation, vulnerable) vs **v4.9.3** (the virtual-shares mitigation).

## Provenance

Both ERC-4626 trees are vendored **byte-for-byte** from OpenZeppelin at the pinned release tags under
`lib/oz-4.8/` and `lib/oz-4.9/` (MIT). The only new code is a minimal standalone asset token and the
attacker/vault-wrapper harness (`src/harness/`, `src/VaultVuln.sol`, `src/VaultPatched.sol`). The two
versions have same-named libraries (`Math`, `SafeERC20`), so the test deploys the vaults via
`vm.deployCode` by artifact name — keeping v4.8 and v4.9 in **separate compilation units**.

## The bug and the fix

v4.8 `_convertToShares(assets) = assets * totalSupply / totalAssets` (with `totalAssets = balanceOf`) —
a first depositor mints 1 share, **donates** assets directly to inflate price-per-share, and the next
depositor's shares round down to zero. v4.9 uses **virtual shares/assets**
(`mulDiv(totalSupply + 10**_decimalsOffset(), totalAssets + 1)`), which makes the attack unprofitable.

## Run it

```
forge test -vv        # offline; no RPC needed
```

| Test | Vault | Result | Meaning |
|---|---|---|---|
| `test_vuln_first_depositor_inflation` | OZ v4.8.3 | attacker PnL **+5000e18**, honest **0 shares** | inflation **profits** the attacker (steals the victim's deposit) |
| `test_patched_virtual_shares_covered_dry` | OZ v4.9.3 | attacker PnL **−2500e18** | attack **unprofitable** → deterred = **covered-dry** |

The invariant that matters is **"the attacker cannot profit from first-depositor inflation"**: broken on
v4.8 (+5000e18), held on v4.9 (−2500e18). The signal is an assertion, not a printed marker; the
mandatory covered-dry patched twin is what makes the fixture non-reward-hackable
(`fake-client-poc-invariant-check`).

Honest note: v4.9 with the **default `_decimalsOffset()=0`** deters the attack by making the attacker
*lose* money, but for a very large donation the honest depositor can still round to zero shares — full
honest-side protection needs a vault-chosen `offset > 0` (or dead-shares/seed). The card's severity is
graded by whether a *net attacker profit / victim loss* is reproduced.

## Safety

Fully **offline** (no fork, no RPC), local EVM only, valueless test tokens. No live network or target.
The value movement is confined to this local disposable harness against the public OpenZeppelin library.
