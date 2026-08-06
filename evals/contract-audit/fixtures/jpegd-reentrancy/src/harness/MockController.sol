// SPDX-License-Identifier: GPL-3.0
pragma solidity ^0.8.0;

import "../interfaces/IController.sol";

/// @notice Minimal controller: reports zero strategy balance so `YVault.balance()` reduces to the
/// vault's own token balance. No strategy funds move, so the bug is isolated to the deposit path.
contract MockController is IController {
    function withdraw(address, uint256) external {}
    function balanceOf(address) external pure returns (uint256) { return 0; }
    function earn(address, uint256) external {}
    function want(address) external pure returns (address) { return address(0); }
    function feeAddress() external pure returns (address) { return address(0); }
    function vaults(address) external pure returns (address) { return address(0); }
    function strategies(address) external pure returns (address) { return address(0); }
    function balanceOfJPEG(address) external pure returns (uint256) { return 0; }
    function withdrawJPEG(address, address) external {}
}
