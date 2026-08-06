# Milestone-1 validation fixture — Curve read-only reentrancy (price manipulation)

The verified fixture for the `evm.read-only-reentrancy-price` card (ADR
`docs/decisions/0008-smart-contract-audit-capability.md`, Milestone 1). It proves the acceptance gate
for the **read-only-reentrancy** class: a vulnerable consumer serves a price manipulated inside an AMM
reentrancy window, and a patched consumer using the real mitigation refuses to (covered-dry).

## Why Curve (and how this relates to Sturdy)

The class card is grounded in **Sturdy Finance** ($800K, Jun 2023), **Sentiment**, and **Blueberry** —
all real-world instances of the **same mechanism**: a value read (`get_virtual_price` / LP price) is
manipulable inside an AMM's `remove_liquidity` / join callback, and a consuming protocol trusts it. The
part that **cannot be mocked** is that reentrancy window — so this fixture uses the **real deployed
Curve stETH/ETH pool** (`0xDC24316b9AE028F1497c275EB9192a3Ea0f67022`) on a mainnet fork. The vulnerable
vs. patched **consumer** is the read-only-reentrancy pattern and its **documented Curve mitigation** (a
`nonreentrant`-lock probe before reading — the analog of Sturdy's added `_validateOracle`).

Honesty: this validates the read-only-reentrancy **class + mechanism** faithfully (real pool, real
mitigation, no mock). It is not the literal Sturdy `LendingPool` before/after commit — reproducing that
needs the full Aave-v2-fork Sturdy deployment on the fork, a heavier lift; the mechanism and the
non-reward-hackable neg-control are what this fixture proves.

## Run it

```
forge test --fork-url mainnet -vv     # needs a mainnet RPC; the foundry.toml alias uses a public node
```

| Test | Consumer | Result | Meaning |
|---|---|---|---|
| `test_vuln_serves_manipulated_price` | vuln | serves **1.1427e18** vs honest **1.1412e18** | manipulable price **served** (invariant break) |
| `test_patched_refuses_during_reentrancy` | patched | works normally; **reverts** in the callback | **covered-dry** neg-control |

The vulnerable consumer reads `get_virtual_price()` with no guard and gets the ~0.13%-inflated value
inside the `remove_liquidity` ETH-refund callback. The patched consumer first probes the pool's
`nonreentrant` lock (a 0-amount `remove_liquidity`), which **reverts** when the pool is mid-reentrancy —
so it never serves a manipulable price. The signal is a revert/assertion, not a printed marker; the
mandatory covered-dry on the patched consumer is what makes the fixture non-reward-hackable
(`fake-client-poc-invariant-check`).

Not pinned to a fork block: the manipulation (during ≠ settled) is block-independent, so the assertion
is reproducible in behavior against current state. A frozen-block variant would need an archive RPC.

## Safety & authorization (ADR 0008 §5)

- **No mainnet interaction / no broadcast.** A local Foundry fork of mainnet; forked, **valueless**
  state. The attacker's ETH is `vm.deal`'d into the fork. Nothing is sent to a live network.
- **No drain.** The PoC reads a *manipulated price* and asserts the manipulation; it does not extract
  value from any protocol (there is no victim lending pool here — just the price oracle). Built under
  the operator's Zone-2 authorization, contained to this local disposable fork.
