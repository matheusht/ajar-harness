// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;
import "@oz49/contracts/token/ERC20/extensions/ERC4626.sol";
import "@oz49/contracts/token/ERC20/ERC20.sol";
import "@oz49/contracts/token/ERC20/IERC20.sol";

/// PATCHED: OpenZeppelin ERC4626 v4.9.3 — virtual shares/assets (`+10**_decimalsOffset()`, `+1`) absorb
/// the donation, so the inflation attack is unprofitable and the next depositor is not diluted to zero.
contract VaultPatched is ERC4626 {
    constructor(address asset_) ERC20("Patched Vault", "pV") ERC4626(IERC20(asset_)) {}
}
