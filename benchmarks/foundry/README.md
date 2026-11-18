# Foundry Paired-Control Benchmarks

Offline Solidity benchmarks that pair a vulnerable target implementation with a `patched-control` twin. Every benchmark runs locally under `forge test` without external RPC dependencies.

## Included Targets

| Target | Vulnerable Mechanism | Patched Control | Verification Command |
| --- | --- | --- | --- |
| `curve-readonly-reentrancy` | Stale `get_virtual_price()` read during native ETH `remove_liquidity` callback inflates collateral valuation | Reentrancy lock / state-updated pool read blocks callback price inflation (`test_patched_..._patched_control`) | `forge test -vv` |
| `erc4626-first-depositor` | OpenZeppelin v4.8.3 share rounding theft via 1-wei initial mint + direct asset donation | OpenZeppelin v4.9.3 virtual shares/assets (`_decimalsOffset`) makes donation attack unprofitable (`test_patched_virtual_shares_patched_control`) | `forge test -vv` |
| `jpegd-reentrancy` | Missing `nonReentrant` guard across vault position state transitions | `nonReentrant` modifier holds position accounting invariant (`test_patched_reentrancy_patched_control`) | `forge test -vv` |

## 4-Arm Reproduction Contract

When verifying a claim against these targets with `ajar claim reproduce`:

1. **Arm 1 (Clean + PoC):** Runs the exploit test against the vulnerable contract and asserts concrete attacker profit or broken accounting invariant.
2. **Arm 2 (Clean + Benign Control):** Runs normal deposit/withdraw/borrow user flows without triggering the exploit failure.
3. **Arm 3 (Micro-Patch + PoC):** Applies the minimal state/reentrancy/virtual-share fix (`patched-control`) and verifies the exploit test no longer profits (`control-invariant-check`).
4. **Arm 4 (Micro-Patch + Benign Control):** Runs normal user flows against the patched contract and confirms zero regression.
