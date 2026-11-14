## Severity, after arm 7

Arm 7 is the reason this is one step below Critical rather than a rounding error. The degenerate digest is
produced by the **SDK's own MPC product API**, from data only (a PSBT), with no malicious caller option. The
signer that receives it is an unattended component by design; it signs a 32-byte value it cannot judge, and
the signature that comes back is a bearer instrument for the input. That is the "steal funds" and
"fully bypass authorisation protections" shape. What keeps the tier at High is that I found no live MPC
service in this repository to point at; the flow is exported and test-covered, not deployed here.

## What I checked and refused

- The buying and batch flows (main, runes, atomical) compute digests only for the buyer's inputs with
  `SigHashAll`, and they copy the seller's input and its matching output at the same index — the
  mapping that would break the seller's `SINGLE` commitment is preserved.
- The listing builders are self-consistent: 3 inputs / 3 outputs with the seller at index 2 in
  `psbt_tx.go`, 2 / 2 with the seller at index 1 in the runes and atomical packages. The seller's
  index always has its output in the shape the builder itself creates.
- The inscription, brc20, doginals and runes-etching builders sign with hardcoded `SigHashAll`.
- There is no JSON entry point in this package, so the reach is Go-struct callers plus PSBT strings.

## What I didn't prove
No mainnet broadcast, and the keys and UTXOs are synthetic. Arm 6's panic is crash-class; I include it as an ingredient, not as the finding. The theft route now goes past digest recomputation: arm 8 shows the attacker transaction passing btcd's script engine under standard flags (the `0x01` control fails). Fee and standardness policy checks are still untested, so I am not claiming a relayable transaction, only one that is valid and script-accepted. The consumer layer that forwards signing requests sits outside this repository, and no live MPC service is visible here either. Taproot is the one input type that errors at the digest level, and even there the caller sees `err=nil` and an unsigned input. Those are the reasons the tier is High and not Critical.
