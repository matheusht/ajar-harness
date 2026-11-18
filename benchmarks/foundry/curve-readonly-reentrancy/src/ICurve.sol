// SPDX-License-Identifier: MIT
pragma solidity ^0.8.13;

/// Minimal interface to the REAL deployed Curve stETH/ETH StableSwap pool
/// (0xDC24316b9AE028F1497c275EB9192a3Ea0f67022). No mock — the reentrancy window is the pool's own.
interface ICurve {
    function add_liquidity(uint256[2] calldata amounts, uint256 min_mint) external payable returns (uint256);
    function remove_liquidity(uint256 amount, uint256[2] calldata min_amounts) external;
    function get_virtual_price() external view returns (uint256);
}
interface IERC20 { function balanceOf(address) external view returns (uint256); }
interface IPriceOracle { function getPrice() external returns (uint256); }

address constant CURVE_STETH = 0xDC24316b9AE028F1497c275EB9192a3Ea0f67022;
address constant STECRV_LP   = 0x06325440D014e39736583c165C2963BA99fAf14E;
