# Chain: PSBT sighash scope to external signer

Target: `okx/go-wallet-sdk`, `coins/bitcoin/psbt_tx.go`, commit `89c5153f4669b0d81658b37bae902b62d495d574`.
Closed at **S4**; S5 is argued, not demonstrated. Fragile stage **S2**: the digest value depends on the
input type, and taproot errors at the digest instead of collapsing.

## Stage table

| # | Stage | Carried in | Operation | Gains (with constraint envelope) | Depends on | Class | Anchor | Proof marker | Control | State |
|---|---|---|---|---|---|---|---|---|---|---|
| S1 | Reach the signer | attacker-supplied PSBT, or `ToSignInput.SigHashTypes[0]` | set declared sighash `0x83` (or override `0x03`); input at index 1, transaction has 1 output | effective sighash with the `SINGLE` bit reaches the digest for `index >= len(txOut)`; no index or output guard on any sink | entry | root | `psbt_tx.go:31-36`, `:667-668`, `:1643-1645` | `CELL A-returned_err_nil=true` and `declared_psbt_sighash=0x83` | same PSBT declaring `0x01` | proven |
| S2 | Collapse the digest | S1's scope plus input index | btcd computes the sighash for `SINGLE` with no matching output (or `NONE`) | 32 bytes with no outputs commitment: legacy constant `0100...00`, v0-witness zero hash, or `SIGHASH_NONE`; taproot errors instead | S1 | consequence | `psbt_tx.go:728` (legacy `RawTxInSignature`), `:755` / `:1768` (witness `RawTxInWitnessSignature`), `:1349` / `:1454` (`CalcWitnessSigHash`); btcd `txscript/sighash.go:110-115`, `:279-287`, `:567-572` | `(single-bug constant=true)`, `digest_is_constant_01=true` | scope `0x01` | proven for legacy and v0 witness; taproot is the error branch |
| S3 | Verify on a rebuilt transaction | S2's digest and the signature over it | rebuild the tx: attacker inputs, victim input at the same index, one output to an attacker script (`0x33` in arms 1/2, `0x55` in arm 8); verify ECDSA; run btcd's script engine with `StandardVerifyFlags` | valid signature for a transaction the victim never approved, accepted by the script engine | S2 | consequence | `psbt_tx.go:670-673`, `:728-732`, `:1600-1609`, `:1768-1784` | `script_engine_accepts_attacker_tx=true` | scope `0x01`, which fails checksig | proven |
| S4 | Hand the same value to an external signer | S2's digest, S3's validity, victim public key | `GenerateMPCUnsignedPSBT` returns `SignHashList`; signer signs the 32 bytes; `GenerateMPCSignedPSBT` attaches | the collapsed digest leaves the SDK as an opaque signing request; the returned signature verifies on the attacker transaction. SDK side proven; signer policy assumed | S2, S3 | consequence | `psbt_tx.go:1395`, `:1438`, `:1473`, `:1528`, `:1546-1548` | `mpc_signed_attacker_tx_sig_valid=true` | scope `0x01` | proven for SDK hand-off; signer policy assumed |
| S5 | Credit or settle | S4's signature | submit the attacker transaction to a service that verifies with this code | funds moved at that service; no constraint envelope measured because no consumer was available | S4 | consequence | none in this repository | none | none | argued, blocked on a live consumer |

## Diagram

```
S1  scope 0x83 reaches the digest (root)
     |  victim input index 1, len(txOut)=1
     v
S2  digest collapses: 0100..00 | zeroHash | NONE
     |
     v
S3  signature valid on attacker-rebuilt tx, script engine accepts
     |
     v
S4  digest exported in SignHashList -> external signer -> attached back
     |
     v
S5  deployed consumer credits or settles   [argued, no live consumer]
```

## Requirements and assumptions

- Go 1.23 or newer; the PoC was run with `go1.26.4` on darwin/arm64, offline, with synthetic keys.
- The victim input's index is at or past the transaction's output count (`idx=1 n_out=1`). If it is not,
  the digest commits to an output and S2 does not collapse.
- The victim prevout is legacy P2PKH (constant digest) or P2WPKH (zero-hash commitment). Taproot is the
  error branch and produces no signature.
- For S4, the external signer signs the 32 bytes it is handed. The PoC uses a local test key as the
  stand-in; no live MPC service is in scope.
- For S5, a deployed consumer must trust the verifier's result. Nothing in this repository does.

## Edge anchors

| Edge | Producer output | Consumer precondition | Anchor |
|---|---|---|---|
| S1 -> S2 | effective `hashType` and input index | `RawTxInSignature` at `:728` for legacy, `RawTxInWitnessSignature` at `:755`/`:1768` for witness; both take `hashType` and `i`; digest is computed inside btcd (`CalcWitnessSigHash` at `:1349`/`:1454`) | `psbt_tx.go:728`, `:755`, `:1349`, `:1454`, `:1768` |
| S2 -> S3 | 32-byte digest | `RawTxInSignature` / `RawTxInWitnessSignature` signs exactly those bytes; `updater.Sign` stores the signature | `psbt_tx.go:728`, `:732`, `:1768`, `:1784` |
| S3 -> S4 | valid signature for the attacker transaction | `SignHashList` carries the digest, attach accepts the signature | `psbt_tx.go:1497-1505`, `:1546-1548` |
| S4 -> S5 | signature returned by the external signer | consumer verifies and credits | not in repository |

## Reliability

All four demonstrated stages ran three times as part of the package and produced byte-identical output;
each is deterministic by construction (fixed keys, fixed UTXOs, fixed scripts, no randomness in the
digest inputs). S5 has no runs. No rate is claimed for taproot, which is the error branch.
