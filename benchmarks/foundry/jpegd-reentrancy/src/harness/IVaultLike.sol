// SPDX-License-Identifier: GPL-3.0
pragma solidity ^0.8.0;

/// @notice The subset of the real YVault API the harness drives — lets the same attack run against
/// either the vulnerable or the patched YVault without duplicating the reproduction.
interface IVaultLike {
    function deposit(uint256 amount) external;
    function withdraw(uint256 shares) external;
    function balanceOf(address account) external view returns (uint256);
    function setContractWhitelisted(address _contract, bool _isWhitelisted) external;
}
