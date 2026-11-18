// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/// Minimal standalone ERC20 underlying asset (implements IERC20 + IERC20Metadata) with a public mint.
/// Version-agnostic so it can back either the v4.8 or v4.9 ERC4626 vault via an address cast.
contract MintableERC20 {
    string public name = "Asset"; string public symbol = "AST"; uint8 public decimals = 18;
    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;
    event Transfer(address indexed from, address indexed to, uint256 v);
    event Approval(address indexed owner, address indexed spender, uint256 v);
    function mint(address to, uint256 a) external { totalSupply += a; balanceOf[to] += a; emit Transfer(address(0), to, a); }
    function approve(address s, uint256 a) external returns (bool) { allowance[msg.sender][s] = a; emit Approval(msg.sender, s, a); return true; }
    function transfer(address to, uint256 a) external returns (bool) { _t(msg.sender, to, a); return true; }
    function transferFrom(address f, address to, uint256 a) external returns (bool) {
        uint256 al = allowance[f][msg.sender];
        if (al != type(uint256).max) allowance[f][msg.sender] = al - a;
        _t(f, to, a); return true;
    }
    function _t(address f, address to, uint256 a) internal { balanceOf[f] -= a; balanceOf[to] += a; emit Transfer(f, to, a); }
}
