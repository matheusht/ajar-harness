// SPDX-License-Identifier: GPL-3.0
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/// @notice The hook a control-giving token (e.g. ERC777 `tokensToSend`) calls on the sender.
interface IReentrancyHook {
    function onTokenTransfer() external;
}

/// @notice A minimal "token that gives control to the sender mid-transfer" — the exact class the
/// C4 #81 finding names ("a token that gives control to the sender, like ERC777 tokens"). On the
/// FIRST `transferFrom` after being armed, it invokes the sender's hook BEFORE moving balances
/// (mirroring ERC777 `tokensToSend`), then disarms so recursion terminates.
contract HookToken is ERC20 {
    address public hookTarget;
    bool public armed;

    constructor() ERC20("Hook Token", "HOOK") {}

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }

    /// @notice Arm the reentrancy hook to fire once, calling `target` mid-transfer.
    function arm(address target) external {
        hookTarget = target;
        armed = true;
    }

    function transferFrom(address from, address to, uint256 amount) public override returns (bool) {
        if (armed && hookTarget != address(0)) {
            armed = false; // one-shot: prevents infinite recursion
            IReentrancyHook(hookTarget).onTokenTransfer();
        }
        return super.transferFrom(from, to, amount);
    }
}
