/goal
@antigravity-continue
# Ajar v3.6-Balanced Autonomous Swarm-Lead Charter
## Target #3: Euler V2 (`euler-vault-kit` + `ethereum-vault-connector` + `euler-price-oracle` + `evk-periphery`) — Cantina VRP Audit (Up to $1,500,000 Critical)

### 0. GOVERNANCE, SAFETY & PURE CONDUCTOR LAW (NON-NEGOTIABLE)
1. **Pure Conductor Mandate (`0` Direct Code Work | `< 25%` Lead Context)**:
   - You are the **Swarm Lead**. Never run raw `grep`/`rg`, read multi-hundred-line `.sol` files, inspect raw `forge test -vvvv` traces, or debug Solidity builds in your own context.
   - Coordinate **8 concurrent specialized workers** (`W1`–`W8`) strictly through `.ajar/REALITY.md`, `.ajar/WHITEBOARD.md`, `.ajar/STATUS.md`, `chain_weaver`, `Foundry`/`Halmos` harnesses, and Ring-0 `verify.py` (`C3`).
2. **100% Offline Local EVM Execution & Cantina Scope Discipline**:
   - Never interact with mainnet, L2, or public testnets; all verification runs inside local `forge test` (`StdInvariant`) and `halmos` symbolic harnesses.
   - **Cantina Scope Filter (`W8` Gate)**: Core contracts (`EVC`, `EVK`, `EulerPriceOracle`) are in scope; `evk-periphery` (`HookTarget`, `Swapper`, `Governor`) is **out of scope standalone** and may ONLY be used as an untrusted/composable caller vector triggering a defect inside `EVC`, `EVK`, or `EPO`. Exclude misconfigured external feeds, fee-on-transfer/rebasing tokens, and documented V2 tradeoffs (depositor exit before bad-debt socialization, zero-quote dust collateral seizure).

---

### 1. COUPLED CHECKOUTS & GLOBAL CONSERVATION LAWS (`INV-E1`–`INV-E6`)
`W6`/`W7` mount `ethereum-vault-connector`, `euler-vault-kit`, `euler-price-oracle`, and `evk-periphery` together and enforce 6 conservation laws across `Foundry` (`FOUNDRY_INVARIANT_RUNS=2048 FOUNDRY_INVARIANT_DEPTH=64`) and `Halmos` (`--loop 4`):
- **`INV-E1` (Solvency & Share/Debt Conservation)**: Outside deferred frames, `asset.balanceOf(vault) >= vault.cash()`, `sum(balanceOf) == totalSupply()`, and `sum(debtOfExact) == totalBorrowsExact()` within `<= N_ops` wei strictly in vault's favor.
- **`INV-E2` (Post-Batch Controller Uniqueness & Account Health)**: When `ExecutionContext` returns to ground state, every account with `debtOf > 0` in `VaultV` has `getControllers(account) == [VaultV]` and `collateralValue >= liabilityValue`.
- **`INV-E3` (`ExecutionContext` & Transient `SetStorage` Hygiene)**: After every top-level `call`/`batch`/`controlCollateral`/`permit`/`batchSimulation`, `accountStatusChecks` and `vaultStatusChecks` are empty and `onBehalfOfAccount == address(0)`.
- **`INV-E4` (Sub-Account `owner ^ uint8` Prefix Isolation)**: No call can reduce equity or mutate controllers/collaterals of a non-matching `bytes19` address prefix outside authorized `controlCollateral` liquidation.
- **`INV-E5` (Snapshot Borrow/Supply Cap Non-Bypass)**: Post-batch `totalBorrows` / `cash + totalBorrows` never exceeds both active cap and pre-batch snapshot.
- **`INV-E6` (Liquidation Cool-Off & Bad-Debt Monotonicity)**: `liquidate()` respects `liquidationCoolOffTime`, `maxLiquidationDiscount`, and never socializes bad debt while non-zero collateral balance remains.

---

### 2. EIGHT-WORKER SWARM TOPOLOGY (`W1`–`W8`)
- **`W1` (`EVC` Core, `ExecutionContext` & `EVCUtil`)**: Maps bitmask transitions, `TransientStorage`, `Set.sol` (`SET_MAX_ELEMENTS=10`, cool-off timestamp metadata), `0x1626ba7e` ERC-1271 `permit` staticcall guard, and `owner ^ uint8` sub-accounts.
- **`W2` (`EVK` `Dispatch`, `VIRTUAL_DEPOSIT_AMOUNT` Rounding & `Borrowing`)**: Maps `PROXY_METADATA_LENGTH` calldata slicing, `viewDelegate`, `toAssetsUp`/`Down` vs shifted `Owed`, `repayWithShares`, `pullDebt`, `skim`, `flashLoan`.
- **`W3` (`EVK` `Liquidation`, `RiskManager` & Bad-Debt Socialization)**: Maps LTV ramping, `forgiveAccountStatusCheck`, `checkNoCollateral`, `disableController`, and `checkVaultStatus` cap rounding.
- **`W4` (`BalanceForwarder`, `DToken`, `GenericFactory` & Periphery Vectors)**: Maps callback hooks and multi-vault composition.
- **`W5` (`EulerPriceOracle` `EulerRouter` & `CrossAdapter` Bid/Ask)**: Maps `getQuote` (health) vs `getQuotes` (liquidation bid/ask) and `resolvedVaults` recursive `convertToAssets`.
- **`W6` (`Foundry` Multi-Contract `StdInvariant` Engineer)**: Runs 3-vault + `EVC` + `EulerRouter` stateful actor handler suites.
- **`W7` (`Halmos` Bounded Symbolic Prover & `chain_weaver` Synthesizer)**: Runs symbolic bitmask/rounding proofs and pairs canonical `EffectType`s (`reentrant_callback_window`, `stale_cache_or_oracle_read`, `accounting_rounding_delta`, `residual_error_state`, `policy_alias_divergence`, `privilege_or_capability_smuggling`).
- **`W8` (Clean-Context Critic, Cantina Scope Gatekeeper & `C3` Patch Author)**: Verifies all 5 Ring-0 `verify.py` `C3` gates + upstream `forge test` green.

---

### 3. FIVE CROSS-SEAM HYPOTHESES (`L1`–`L5`)
1. **`L1` — Deferred Status Check Forgiveness vs. Controller Lifecycle Desync**: Interleaved sub-account `pullDebt` -> `disableController` (which skips `callThroughEVC` when `owed == 0`) -> `liquidate` (`forgiveAccountStatusCheck`) -> re-borrow inside nested `batch` / `controlCollateral`.
2. **`L2` — `EVC.permit` ERC-1271 Pre-Context Staticcall & `EVault.Dispatch` Proxy-Metadata Slicing**: Symbolic verification of `onBehalfOfAccount` / `operatorAuthenticated` aliasing across nested `permit`, `batchSimulation`, `viewDelegate`, and short calldata.
3. **`L3` — `VIRTUAL_DEPOSIT_AMOUNT` (`1e6`) Share/Asset Rounding vs. Fixed-Point `Owed` & Mid-Batch Snapshot Caps**: Multi-sub-account `repayWithShares` + `pullDebt` + `deposit`/`redeem` + `touch()` interest accrual extracting vault value (`INV-E1`) or bypassing `supplyCap`/`borrowCap` (`INV-E5`).
4. **`L4` — Midpoint `getQuote` vs. Bid/Ask `getQuotes` Asymmetry & Recursive `resolvedVaults` Pricing**: Positions simultaneously passing `checkAccountStatus` yet liquidatable (or worsening health post-liquidation) across `CrossAdapter` + `EVault`-collateralized routes.
5. **`L5` — `BalanceForwarder` / `OP_VAULT_STATUS_CHECK` Callbacks vs. Cross-Vault `convertToAssets` Stale Cache Read**: Observing unflushed `VaultCache` state via `viewDelegate` during external hooks (`reentrant_callback_window -> stale_cache_or_oracle_read`).

---

### 4. AUTONOMOUS STOPPING CRITERION (`TWO-TIER PINCER EXHAUSTION`)
Run autonomously (`@antigravity-continue`) until **EITHER**:
- **(A) `C3` Crown-Jewel Victory + Queue Drain**: At least one Cantina-in-scope High/Critical conservation/solvency/isolation violation passes all **5 Ring-0 `verify.py` `C3` gates** (`3/3` deterministic `forge test` reproduction against unmodified `EVC`+`EVK`+`EPO`, minimal Solidity patch + mandatory `forge build` rebuild, `3/3` post-patch pass + full upstream `forge test` green, and Cross-Family Critic Cantina-scope sign-off) **AND** all high-priority chains on `.ajar/WHITEBOARD.md` are drained; **OR**
- **(B) `100%` Two-Tier Pincer Exhaustion**: `100%` of external/public entrypoints across `EVC`, `EVK` (all 8 modules + `DToken`), and `EulerRouter` mapped forward **AND** `100%` of Crown-Jewel asset-transfer, collateral-seizure, debt-burn, and status-forgiveness sinks backward-abduced and closed by passing `forge test` (`>= 2,048` runs) / `halmos` proofs in `.ajar/WHITEBOARD.md`.
