# Source references

Pin: `okx/go-wallet-sdk`, `coins/bitcoin`, commit `89c5153f4669b0d81658b37bae902b62d495d574`.
Paths are relative to `poc/module/` unless marked btcd. Line numbers are from that shipped copy.

## SDK anchors

| Symbol / site | Anchor | Observation | Stage |
|---|---|---|---|
| `allowedSighashTypes` | `psbt_tx.go:31-36` | allowlist is `SINGLE\|ACP` (`0x83`), `ALL\|ACP` (`0x81`), `ALL` (`0x01`), `DEFAULT` (`0x00`); membership-test only | S1 |
| `SignRawPSBTTransaction` | `psbt_tx.go:642` | PSBT-only entry point; no caller option needed | S1 |
| declared-sighash check | `psbt_tx.go:667-668` | `if _, ok := allowedSighashTypes[pIn.SighashType]; !ok { continue }` then `signPSBTPacket(..., pIn.SighashType)`; `0x83` passes | S1, edge S1 to S2 |
| signer loop error handling | `psbt_tx.go:670-673` | `if err != nil { //return "", err }`; failed input returns `nil` and an unsigned PSBT | S3 |
| caller override | `psbt_tx.go:1643-1645` | `hashType = txscript.SigHashType(toSignInput.SigHashTypes[0])`; no re-validation against the allowlist | S1 |
| commented-out address check | `psbt_tx.go:1646-1654` | `ToSignInput.Address` guard disabled; hygiene only, not on any demonstrated route | boundaries |
| `signPSBTPacket` | `psbt_tx.go:683` | shared signer entry; prevout from PSBT | S1 |
| legacy digest + sign | `psbt_tx.go:728-732` | `txscript.RawTxInSignature` takes the same `hashType` and `i` and computes the digest internally; `updater.Sign` at `:732` stores the signature | S2, S3, edge S1 to S2, edge S2 to S3 |
| witness digest + sign | `psbt_tx.go:755`, `:1349`, `:1454`, `:1768-1784` | `RawTxInWitnessSignature` signs the witness digest; `CalcWitnessSigHash` computes it; `updater.Sign` at `:1784` stores the signature | S2, S3 |
| second signer digest + sign | `psbt_tx.go:1733` | same pattern in the keypath/scriptpath path | S1 |
| keypath loop error handling | `psbt_tx.go:1600-1609` | `if err != nil { continue }` and empty `if err != nil { }` after `psbt.Finalize` | S3 |
| `calcInputSigHash` | `psbt_tx.go:1293` | digest helper, same scope handling | S1, S2 |
| `CalcInputSigHashForUnsignedPSBT` | `psbt_tx.go:1395` | digest helper used by the MPC unsigned flow | S2, S4 |
| digest call in the MPC helper | `psbt_tx.go:1438` | `txscript.CalcSignatureHash(prevPkScript, hashType, tx, i)` receives the scope unchanged | S1, S2, S4 |
| `GenerateMPCUnsignedPSBT` | `psbt_tx.go:1473` | returns `SignHashList` to the external signer | S4 |
| digest loop in MPC flow | `psbt_tx.go:1497-1505` | on digest error, substitutes `GetRandomHash()` instead of returning the error | S4, dead end |
| `GetRandomHash` | `psbt_tx.go:1519-1526` | `"ffffffff"` plus 28 random bytes; looks like a plausible digest | S4, dead end |
| `GenerateMPCSignedPSBT` | `psbt_tx.go:1528` | attaches signatures returned by the signer | S4 |
| attach loop error handling | `psbt_tx.go:1546-1548` | `if err != nil { //return nil, err }`; attach failure swallowed | S4, edge S3 to S4 |
| listing builder scope | `psbt_tx.go:145` | `GenerateMPCUnsignedListingPSBT` signs the seller input with `SIGHASH_SINGLE\|ANYONECANPAY` (`0x83`), the same scope the allowlist exists for | S1, fix constraint |
| unguarded prevout index | `psbt_tx.go:558, 602, 659, 694, 1401, 1487, 1579, 1636` | `NonWitnessUtxo.TxOut[prevOut.Index]` indexed without a bounds check; arm 6 panics at index 99 of a one-output funding tx | dead end |

## btcd anchors (dependency, not the defect)

| Site | Anchor | Observation | Stage |
|---|---|---|---|
| legacy out-of-range `SINGLE` | `txscript/sighash.go:110-115` | returns the consensus constant `0100...00`; the upstream comment calls it a Satoshi-client bug now part of consensus | S2 |
| v0-witness out-of-range `SINGLE` | `txscript/sighash.go:279-287` | writes `zeroHash` for the outputs commitment, a `NONE`-equivalent digest, not an error | S2 |
| taproot out-of-range `SINGLE` | `txscript/sighash.go:567-572` | returns an error instead of a digest; this is why taproot is the error branch of S2 | S2, fragile stage |

## Edge anchors

| Edge | Producer | Consumer | Anchor |
|---|---|---|---|
| S1 to S2 | effective `hashType`, input index | `RawTxInSignature`; digest inside btcd | `psbt_tx.go:728` |
| S2 to S3 | 32-byte digest | `RawTxInSignature` signs; `updater.Sign` stores | `psbt_tx.go:728`, `:732` |
| S3 to S4 | valid signature and digest | `SignHashList` append and attach | `psbt_tx.go:1497-1505`, `:1546-1548` |
| S4 to S5 | returned signature | consumer verification | not in this repository |

## Package evidence

| File | Contents |
|---|---|
| `poc/expected.stdout` | verbatim stdout of `poc/stage.sh`; every cell quoted in the report appears here |
| `poc/build-meta.txt` | pin, toolchain, build command, binary SHA-256s, date 2026-10-15 |
| `poc/module/` tree | SHA-256 `130469d5df260543439115a4e0c2520c2a34f6c9e5ba7ef0e67e78f5c1f5e403` over sorted `path + file hash` lines; source files match upstream by `cmp` against the checkout at `89c5153f`; `go.sum` is added |
| `poc/arms/*/main.go` | one harness per arm; synthetic WIF and UTXOs, no broadcast |
| `evidence/reliability.txt` | three-run result, exit code, stdout equality |

No other source files were consulted for the claims in this package. The public prior-art pass is
recorded in `report.md` §Novelty: Bitcoin Core PR #35984 (merged 2026-09-25) fixes the same unsafe
`SIGHASH_SINGLE` PSBT condition in Core; the delta here is the SDK-specific override, swallowed
errors, and MPC digest export. The finding is the same one in the engagement's existing internal
report.
