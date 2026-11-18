// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;
import "@oz48/contracts/token/ERC20/extensions/ERC4626.sol";
import "@oz48/contracts/token/ERC20/ERC20.sol";
import "@oz48/contracts/token/ERC20/IERC20.sol";

/// VULNERABLE: OpenZeppelin ERC4626 v4.8.3 (pre-mitigation) — share math is `assets*supply/totalAssets`,
/// so a first-depositor donation inflates price-per-share and the next depositor rounds to zero shares.
contract VaultVuln is ERC4626 {
    constructor(address asset_) ERC20("Vuln Vault", "vV") ERC4626(IERC20(asset_)) {}
}
