// SPDX-License-Identifier: MIT
pragma solidity ^0.8.13;
import "../src/ICurve.sol";
import "../src/Oracles.sol";
import "../src/harness/Attacker.sol";

interface IVm { function deal(address, uint256) external; }

/// Milestone-1 read-only-reentrancy fixture (ADR 0008). Runs against a mainnet FORK using the REAL
/// Curve stETH/ETH pool (the un-mockable reentrancy window). Acceptance gate: the VULNERABLE consumer
/// serves a price manipulated inside the callback (invariant break); the PATCHED consumer, using Curve's
/// real reentrancy-lock mitigation, REFUSES to serve it (reverts) = covered-dry.
contract CurveReadOnlyReentrancyTest {
    ICurve constant POOL = ICurve(CURVE_STETH);
    IVm constant vm = IVm(0x7109709ECfa91a80626fF3989D68f67F5b1DD12D);
    event Reading(string tag, uint256 duringCallback, uint256 honest, bool reverted);

    function _attack(address oracle) internal returns (uint256 during, bool reverted, uint256 honest) {
        uint256 before = POOL.get_virtual_price();
        Attacker atk = new Attacker(oracle);
        vm.deal(address(atk), 100 ether);
        atk.run();
        uint256 after_ = POOL.get_virtual_price();
        honest = (before + after_) / 2; // settled price, before ~= after
        during = atk.priceInCallback();
        reverted = atk.revertedInCallback();
    }

    /// VULNERABLE: the oracle serves a manipulated (deviating) price read inside the reentrancy window.
    function test_vuln_serves_manipulated_price() external {
        VulnOracle o = new VulnOracle();
        (uint256 during, bool reverted, uint256 honest) = _attack(address(o));
        emit Reading("VULN", during, honest, reverted);
        require(!reverted, "VULN: unexpected revert");
        require(during != 0 && during != honest, "VULN: expected a manipulated price != honest, invariant intact");
    }

    /// PATCHED: works normally outside reentrancy, but REFUSES (reverts) inside the window -> covered-dry.
    function test_patched_refuses_during_reentrancy() external {
        PatchedOracle o = new PatchedOracle();
        require(o.getPrice() > 0, "PATCHED: must serve a price when not reentered");
        (uint256 during, bool reverted, uint256 honest) = _attack(address(o));
        emit Reading("PATCHED", during, honest, reverted);
        require(reverted, "PATCHED: expected covered-dry (revert under reentrancy) but a price was served");
    }
}
