// SPDX-License-Identifier: MIT
pragma solidity ^0.8.13;
import "./ICurve.sol";


/// VULNERABLE consumer: reads the Curve LP price with no reentrancy guard — the exact read-only-
/// reentrancy shape (Sturdy/Sentiment/Blueberry). Returns a manipulated value inside a remove_liquidity
/// callback.
contract VulnOracle is IPriceOracle {
    function getPrice() external view returns (uint256) {
        return ICurve(CURVE_STETH).get_virtual_price();
    }
}

/// PATCHED consumer: applies Curve's documented read-only-reentrancy mitigation — probe the pool's
/// the pool's nonreentrant lock path (a 0-amount remove_liquidity) BEFORE reading; it reverts if the pool is
/// mid-reentrancy, so a manipulable price is never served. This is the real fix pattern (the analog of
/// Sturdy's added `_validateOracle`), not a mock.
contract PatchedOracle is IPriceOracle {
    function getPrice() external returns (uint256) {
        uint256[2] memory zero;
        ICurve(CURVE_STETH).remove_liquidity(0, zero); // reverts under the pool's reentrancy lock
        return ICurve(CURVE_STETH).get_virtual_price();
    }
    receive() external payable {}
}
