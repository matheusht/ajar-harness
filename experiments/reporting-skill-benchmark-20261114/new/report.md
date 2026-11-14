# Output-blind sighash scopes in PSBT signing let a PSBT author reuse a victim signature (coins/bitcoin @ 89c5153f)

## Summary

`coins/bitcoin/psbt_tx.go` hands the signer a sighash scope that can commit to no outputs, because the
`SINGLE` bit is never checked against the input's index and the caller override at `:1643-1645` replaces
the allowlisted value without being re-validated. A hostile PSBT needs no caller option: declaring the
allowlisted `0x83` (`SINGLE|ANYONECANPAY`) on an input whose index is past the end of the output list is
enough, and the signature stays valid on a transaction I rebuilt to pay an attacker script. The same
32-byte digest leaves the SDK through `GenerateMPCUnsignedPSBT` in `SignHashList` for an external MPC
signer, and `GenerateMPCSignedPSBT` attaches the returned signature, which is the last stage I closed.
The ceiling is a deployed service that credits or settles on a signature this verifier accepted: I argue
that stage from the demonstrated primitives but did not run it, because no live consumer is in this
repository.

## At a glance

| Field | Value |
|---|---|
| Affected | `coins/bitcoin/psbt_tx.go` in `okx/go-wallet-sdk`, commit `89c5153f4669b0d81658b37bae902b62d495d574` |
| Tested | source-identical copy of the pinned package (`go.sum` added), Go 1.26.4, darwin/arm64; arms need no network after the first build |
| Chain | S1 scope reaches the signer, S2 digest collapses, S3 signature verifies on a rebuilt transaction, S4 SDK MPC flow hands the same digest to an external signer, S5 consumer credits (argued) |
| Closed at | S4 |
| Fragile stage | S2: the digest value is input-type dependent, and taproot errors at the digest level instead of producing one |
| Demonstrated | collapsed digest for legacy and v0-witness arms; valid signature on an attacker-built transaction; btcd script-engine acceptance; MPC digest and signature round trip |
| Not demonstrated | any taproot signature; any live consumer, broadcast, or settlement |
| Control | the `0x01` cells: same entry point and same PSBT, scope without the `SINGLE` bit |
| Severity | 6.5 at the SDK boundary (`S:U`); 7.7 chain-level (`S:C`), High; Critical only if a deployed consumer trusts the verifier |
| Artifact | `btc-psbt-sighash-override-report.zip` |

## Affected and tested

`okx/go-wallet-sdk`, package `coins/bitcoin`, pinned at `89c5153f4669b0d81658b37bae902b62d495d574`.
The PoC ships that package under `poc/module/` plus the `doginals` package it imports. The source
files are byte-identical to the pin; `go.sum` is added so the build is reproducible. I compared every shipped
source file with the upstream checkout at the same commit using `cmp`; only `go.sum` differs. Every
stage below executes against that copy; there is no deployed build in scope. Go toolchain
`go1.26.4` on darwin/arm64, built with `-trimpath -buildvcs=false`, so binaries and cell order are fixed.
Pin and build date recorded in the package: 2026-10-15. Module tree SHA-256
`130469d5df260543439115a4e0c2520c2a34f6c9e5ba7ef0e67e78f5c1f5e403`, computed as
`find poc/module -type f -print0 | sort -z | xargs -0 shasum -a 256 | shasum -a 256`; this covers the
shipped tree, including the added `go.sum`. The arms need no network after the first build; the Go toolchain may fetch btcd and btcutil
then. Keys and UTXOs are synthetic, and nothing is broadcast. The three package runs I compared
produced byte-identical stdout (`35abd6f3...`); S1 through S4 are deterministic by construction, not
sampled. The original `poc/build-meta.txt` records two identical builds from the earlier package; the
three full stage runs are recorded separately in `evidence/reliability.txt`.

## Chain overview

| # | Stage | Gains | Depends on | Class | Anchor | Proof |
|---|---|---|---|---|---|---|
| S1 | reach the signer | effective sighash `0x83` (or `0x03` via the override) reaches the digest for an input with `index >= len(txOut)`; no output-index check on any sink | entry | root | `psbt_tx.go:31-36`, `:667-668`, `:1643-1645` | `declared_psbt_sighash=0x83` with `A-returned_err_nil=true` |
| S2 | collapse the digest | 32-byte digest with no outputs commitment: legacy constant, v0-witness zero hash, or `SIGHASH_NONE`; taproot errors instead | S1 | consequence | `psbt_tx.go:728` (legacy `RawTxInSignature`), `:755` / `:1768` (witness `RawTxInWitnessSignature`), `:1349` / `:1454` (`CalcWitnessSigHash`), btcd `txscript/sighash.go:110-115`, `:279-287`, `:567-572` | `(single-bug constant=true)` with `digest_is_constant_01=true` |
| S3 | verify on a rebuilt transaction | valid signature over an attacker-built transaction paying a 20-byte attacker script (`0x33` in arms 1 and 2, `0x55` in arm 8); accepted by btcd's script engine under `StandardVerifyFlags` | S2 | consequence | `psbt_tx.go:670-673`, `:728-732`, `:1600-1609`, `:1768-1784` | `script_engine_accepts_attacker_tx=true` |
| S4 | hand the same value to an external signer | same 32 bytes in `SignHashList`; returned signature attaches to the attacker transaction; signer policy assumed | S2, S3 | consequence | `psbt_tx.go:1395`, `:1438`, `:1473`, `:1528`, `:1546-1548` | `mpc_signed_attacker_tx_sig_valid=true` |
| S5 | credit or settle | funds moved at a service that trusts this verifier | S4 | consequence, argued | no anchor in this repository | none; blocked, not run |

```
S1  scope 0x83 reaches the digest (root)
     |  victim input at index 1, transaction has 1 output
     v
S2  digest collapses: 0100..00 (legacy) | zeroHash (v0 witness) | NONE
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

## Root cause

**S1, root.** The allowlist at `psbt_tx.go:31-36` contains `SINGLE|ACP`, `ALL|ACP`, `ALL`, and
`DEFAULT`. Two entry paths reach the digest: a PSBT-declared sighash, membership-tested at `:667` and
signed at `:668`, and a caller override taken verbatim at `:1643-1645`:

```go
if toSignInput != nil && len(toSignInput.SigHashTypes) > 0 {
    hashType = txscript.SigHashType(toSignInput.SigHashTypes[0])
}
```

The invariant that fails: before any `SINGLE`-bit scope reaches a digest, the signer must establish that
the input's index has a corresponding output. No sink in this file performs that check: the legacy
sink is `:728` (with the other legacy digest at `:1340`), the witness sinks are `:755` and `:1768`
(digests at `:1349` and `:1454`), the MPC helper is `:1438`, and `:293` and `:1733` are the other
signing entries. The override is not compared
against `allowedSighashTypes`, so `0x83` passes for the wrong reason on both paths.

**Edge S1 to S2.** The producer is `:668` and `:1643-1645`: the effective `hashType` and the input index.
The consumer is `txscript.RawTxInSignature` at `:728` for legacy inputs, and
`txscript.RawTxInWitnessSignature` at `:755` / `:1768` for witness inputs; both take `hashType` and
`i` and compute the digest internally (`CalcWitnessSigHash` at `:1349` / `:1454`). Same two values,
one call apart, with no index check between them.

**S2, consequence.** btcd computes the digest. With the `SINGLE` bit and `index >= len(txOut)` it returns
the consensus constant `0100...00` (32 bytes, `0x01` then 31 zeros) for legacy inputs
(`txscript/sighash.go:110-115`), writes `zeroHash` as the outputs commitment for v0 witness inputs
(`:279-287`), and errors for taproot (`:567-572`).
The witness path reaches `RawTxInWitnessSignature` at `:755` and `:1768`, whose digest comes from
`CalcWitnessSigHash` at `:1349` and `:1454`; the same missing index check applies.
`SIGHASH_NONE` needs no out-of-range index at all. The invariant that fails: a signature must commit to
the transaction the victim approved, including the output that pays them. The digest above commits to no
output, so the commitment is not merely weak, it is absent. This link is a consequence of S1: the signer
was never given a reason to refuse the scope.

**Edge S2 to S3.** The producer is the digest computed inside `txscript.RawTxInSignature` at `:728`;
the consumer is the signature that call returns and `updater.Sign` stores at `:732`. The same value is
recomputed by the verifier for a different transaction, which is why the rebuilt transaction verifies.

**S3, consequence.** `updater.Sign` stores the partial signature, and the loop at `:670-673` discards a
failure and returns `hex.EncodeToString(b.Bytes()), nil`. The signature is a bearer instrument for the
input: anyone who can reference the victim's outpoint in a transaction can attach it to a transaction
paying any script, as long as the digest reproduces.

**Edge S3 to S4.** The producer is the valid signature and the digest from S2; the consumer is
`GenerateMPCUnsignedPSBT`, which recomputes the digest through `CalcInputSigHashForUnsignedPSBT`
(`:1395`, digest call at `:1438`) and appends it to `SignHashList` (`:1473`, loop at `:1497-1505`).

**S4, consequence.** The external signer sees a 32-byte value, not a PSBT, so it cannot judge what the
digest commits to. `GenerateMPCSignedPSBT` at `:1528` attaches whatever comes back and swallows the attach
error at `:1546-1548`. This link adds no new root cause; it removes the last place a human or a policy
check could have noticed the missing output commitment.

**Patch reachability.** A structural `index < len(txOut)` check, plus re-validation of the override,
closes S1 and makes S2 through S4 unreachable. Propagating errors alone does not close the chain: the
signature is still produced and valid, so the caller learns about other failures while the signed
transaction remains usable. Removing `SINGLE|ACP` from the
allowlist closes the PSBT-declared arm only, and would break the listing flow at `:145` that signs with
that exact scope.

## Stage walkthrough

### S1: Reach the signer with an output-blind scope

- **Precondition:** attacker controls the PSBT bytes, or a caller forwards `ToSignInput.SigHashTypes`; the
  victim input is at index 1 and the transaction has one output.
- **Action:** set the input's declared sighash to `0x83`, or pass `SigHashTypes: []int{0x83}`. Arm 2 does
  the first with three different entry shapes: empty `ToSignInputs`, `nil` option, and
  `SignRawPSBTTransaction`. Arm 1 does the second. No output-index check runs.
- **Success marker:** `CELL A-returned_err_nil=true` followed by
  `CELL C-raw-psbt-entry declared_psbt_sighash=0x83 digest_is_constant_01=true attacker_tx_script_0x33_sig_valid=true`.
- **Failure signature:** an unguarded prevout index panics instead:
  `CELL P-raw panic=runtime error: index out of range [99] with length 1`. A build with the index guard
  would print a rejected or unsigned input instead of a signature.
- **Abort:** nothing persistent. Offline, the work directory is removed by the script. On a live SDK,
  cancel the signing request; a failed input returns an unsigned PSBT with a nil error, so a caller must
  inspect the PSBT, not the error.
- **Hand-off:** `hashType` with the `SINGLE` bit and input index 1 reach the digest call, and 1 is already
  past the end of a one-output list.

### S2: Collapse the digest

- **Precondition:** S1 marker; legacy P2PKH prevout, `hashType` `0x83` or `0x03`, victim at index 1,
  `len(txOut) = 1`.
- **Action:** call the same digest function the signer uses. `txscript.CalcSignatureHash` for the legacy
  arm returns the constant; the v0-witness arm writes `zeroHash` for the outputs commitment.
- **Success marker:**
  `CELL S-0x83 signer_digest=0100000000000000000000000000000000000000000000000000000000000000 (single-bug constant=true) attacker_tx_sig_valid=true err=<nil>`
- **Failure signature:** on taproot the digest call returns an error and no digest, so the input comes
  back unsigned; the observed symptom is a missing signature, not a forged one. `SIGHASH_NONE` takes the
  other branch and needs no out-of-range index.
- **Abort:** nothing to restore. On a live signer, refuse to sign a digest that arrived without the PSBT.
- **Hand-off:** the signer commits to 32 bytes that contain no output, so any transaction reproducing this
  digest accepts the signature.

### S3: Verify the signature on a rebuilt transaction

- **Precondition:** S2 signature; the victim UTXO; an attacker script (`0x33`-repeated bytes in arms 1
  and 2, `0x55`-repeated bytes in arm 8).
- **Action:** rebuild a transaction with attacker inputs, the victim input at the same index, and one
  output to the attacker script; recompute the digest with `CalcSignatureHash`; verify the ECDSA
  signature; then run the transaction through btcd's script engine with `StandardVerifyFlags`.
- **Success marker:** `CELL A1-single-0x83 declared=0x83 script_engine_accepts_attacker_tx=true err=<nil>`,
  and for v0 witness
  `CELL W2-p2wpkh-single original_valid=true redirected_output_to_0x22_script_still_valid=true`.
- **Failure signature:** `CELL A2-control-0x01 declared=0x01 script_engine_accepts_attacker_tx=false err=signature not empty on failed checksig`.
- **Abort:** none needed; the rebuilt transaction is never broadcast.
- **Hand-off:** the value is now a valid signature for a transaction the victim never approved. Nothing in
  it binds to the victim's output, so it can be handed to an unattended signer.

### S4: Hand the same digest to the external MPC signer

- **Precondition:** S2 digest; S3 acceptance; the victim public key.
- **Action:** `GenerateMPCUnsignedPSBT` returns `SignHashList`, with the victim input's digest at index 1.
  I signed that 32-byte value with the test key to stand in for the external MPC signer; there is no live
  MPC service in this repository. `GenerateMPCSignedPSBT` attaches the signature, and the arm reads the
  partial signature back and verifies it against the attacker transaction.
- **Success marker:**
  `CELL M-direct-0x83 declared=0x83 signer_digest=0100000000000000000000000000000000000000000000000000000000000000 digest_is_constant_01=true`
  followed by `CELL M-direct-0x83 mpc_signed_attacker_tx_sig_valid=true`.
- **Failure signature:** `CELL M-control-0x01 mpc_signed_attacker_tx_sig_valid=false`, or `no partial sig on
  victim input` when the attach fails.
- **Abort:** signer-side only; do not sign the digest. No state changes, no keys touched beyond the
  synthetic WIF.
- **Hand-off:** the SDK side is proven: it exports the collapsed digest and attaches the returned
  signature. The signer's policy is assumed; it receives 32 bytes and cannot distinguish them from a
  real digest. The chain now depends on what the consumer does with that signature.

### S5: Credit or settle on that signature (argued)

- **Precondition:** the S4 signature reaches a service that verifies signatures without re-deriving the
  digest from its own approved transaction, and that service credits or releases funds on that check.
- **Action:** submit the attacker-built transaction. This is the argument, not a run: no consumer,
  endpoint, or service is in this repository.
- **Success marker:** none. I did not observe this stage.
- **Failure signature:** a consumer that recomputes the sighash from its own transaction, or checks that a
  `SINGLE` input has a matching output, rejects the transaction. That is the branch I expect in a
  correctly built service.
- **Abort:** not applicable; nothing was submitted.
- **Hand-off:** the chain ends here. Theft is conditional on this stage, which is why the severity is High
  and not Critical.

## Reproduction

Fast path, from the package root:

```sh
sh poc/stage.sh
```

Prerequisites: `go` 1.23 or newer (observed `go1.26.4`), `shasum`; the first build may fetch btcd and
btcutil from the module proxy. The script copies `poc/module/` to a `mktemp` directory, builds the eight
arms with `-trimpath -buildvcs=false`, prints the binary SHA-256s, then prints every cell. Expected output
is `poc/expected.stdout`, verbatim. Exit status 0.

Per-stage observation, all from that one run:

| Stage | Command | Look for |
|---|---|---|
| S1 | `sh poc/stage.sh` | `== arm 2` block, three cells, all `declared_psbt_sighash=0x83`, each with `*-returned_err_nil=true`; `== arm 8` for the raw-entry pair |
| S2 | same | `(single-bug constant=true)` in arm 1; `digest_is_constant_01=true` in arms 2 and 7; `hash_byte=0x03 idx=1 n_out=1` in arm 3 |
| S3 | same | `script_engine_accepts_attacker_tx=true` in arm 8; `redirected_output_to_0x22_script_still_valid=true` in arm 3 |
| S4 | same | `== arm 7` block, `mpc_signed_attacker_tx_sig_valid=true` for `M-direct-0x83` |

`Will not work if`: the Go toolchain is older than 1.23, the module proxy is unreachable on a cold cache,
or the `poc/module/` tree is modified. Binary hashes in `expected.stdout` pin the build; cells are printed
by the built binaries, so comparing cells is the meaningful check on a different platform.

Cleanup: the script's `trap` removes the work directory on exit. Nothing is written to the repository,
nothing is broadcast, and no live keys are used.

## Evidence and controls

| Stage | Claim | Decisive line | Control | Control output | State |
|---|---|---|---|---|---|
| S1 | the raw entry signs a PSBT declaring `0x83` with no caller option | `CELL A1-single-0x83 declared=0x83 script_engine_accepts_attacker_tx=true err=<nil>` | same PSBT declaring `0x01`, same entry | `CELL A2-control-0x01 declared=0x01 script_engine_accepts_attacker_tx=false err=signature not empty on failed checksig` | proven |
| S1 | the options entry reaches the same digest with empty `ToSignInputs` | `CELL A-declared-empty-options declared_psbt_sighash=0x83 digest_is_constant_01=true attacker_tx_script_0x33_sig_valid=true` | none in this arm; the scope change is covered by the raw-entry row above | none | proven |
| S2 | the digest is the legacy constant | `CELL S-0x83 signer_digest=0100000000000000000000000000000000000000000000000000000000000000 (single-bug constant=true) attacker_tx_sig_valid=true err=<nil>` | scope `0x01` in the same arm | `CELL S-0x01 signer_digest=f6da778b2a846438df6f49a1b53de0fa3d89f8dda642813a52148763923942be (single-bug constant=false) attacker_tx_sig_valid=false err=<nil>` | proven |
| S2 | v0 witness takes the zero-hash branch | `CELL W1-sign-0x03 err=nil hash_byte=0x03 idx=1 n_out=1` | scope `0x01` | `CELL W3-control-0x01 redirected_still_valid=false (expect false)` | proven |
| S2 | `SIGHASH_NONE` needs no index trick | `CELL H1R-0x02 original_valid=true redirected_output(999 to 0x11..)_still_valid=true` | scope `0x01` | `CELL H1R-0x01 original_valid=true redirected_output(999 to 0x11..)_still_valid=false` | proven |
| S3 | the signature is valid on a rebuilt transaction | `CELL A1-single-0x83 declared=0x83 script_engine_accepts_attacker_tx=true err=<nil>` | scope `0x01` | `CELL A2-control-0x01 declared=0x01 script_engine_accepts_attacker_tx=false err=signature not empty on failed checksig` | proven |
| S3 | the prepared signature survives an appended input | `CELL H1-acp-0x83 sig_survives_appended_input=true` | scope `0x01` | `CELL H1-acp-0x01 sig_survives_appended_input=false` | proven |
| S4 | the SDK hands the constant digest to the external signer | `CELL M-direct-0x83 declared=0x83 signer_digest=0100000000000000000000000000000000000000000000000000000000000000 digest_is_constant_01=true` | same PSBT declaring `0x01` | `CELL M-control-0x01 declared=0x01 signer_digest=bfb50792126e6774e06e97706ecd5a9f349f34449ea3b87838c7cde281ac5dff digest_is_constant_01=false` | proven |
| S4 | the returned signature verifies on the attacker transaction | `CELL M-direct-0x83 mpc_signed_attacker_tx_sig_valid=true` | same PSBT declaring `0x01` | `CELL M-control-0x01 mpc_signed_attacker_tx_sig_valid=false` | proven |
| S5 | a consumer credits the result | not run | none | none | argued |

Controls isolate one condition: the scope changes from `0x83` to `0x01` while the entry point, the PSBT,
the keys, and the attacker transaction stay the same. In every case the stage marker disappears and the
earlier markers remain (the signing call still returns `err=<nil>`, the digest is still printed). Arm 6's
panic is a separate crash-class path and is not used as a control. Arm 2 has no `0x01` cell, so its
options-entry row relies on the raw-entry control above for the scope change; the claim it carries is
reachability, not digest shape.

**Per-stage reliability.**

| Stage | Runs | Successes | Failure signature | Retryable | Bound |
|---|---:|---:|---|---|---|
| S1 | 3 | 3 | rejected or unsigned input | no | deterministic |
| S2 | 3 | 3 | taproot digest error, then unsigned input | no | deterministic |
| S3 | 3 | 3 | `signature not empty on failed checksig` | no | deterministic |
| S4 | 3 | 3 | `mpc_signed_attacker_tx_sig_valid=false` | no | deterministic |
| S5 | 0 | 0 | not run | no | blocked on a live consumer |

The three package runs produced byte-identical stdout, including every cell quoted here. S1 through S4 are
deterministic by construction: fixed synthetic keys, fixed UTXOs, fixed scripts, and no clock, randomness,
or allocator input in the digest inputs. The only variable part of the package is the first-build module
fetch. Taproot is the error branch of S2 and is not the demonstrated path, so no rate is claimed for it.

## Impact

Entry: anyone who can hand a PSBT to the SDK, or a caller that forwards a sighash override, with no
credential beyond the request itself. Chain: a signature that stays valid on a transaction paying the
attacker, delivered to an external signer as an opaque 32-byte digest. That reaches a bearer instrument
for the victim's UTXO once a deployed consumer credits or settles on the verifier's result.

The SDK-boundary score is 6.5: `AV:N/AC:L/PR:L/UI:N/S:U/C:N/I:H/A:N`, integrity high with no
confidentiality or availability effect, because the artifact produces a signature, not a broadcast.
Chain-level, the same vector with `S:C` is 7.7, since the verifier's failure crosses into the external
signer's decision and then a consumer's authorization. Neither score assumes a named consumer. The full argument, the vector arithmetic,
and the conditional Critical ceiling are in `impact.md`.

## Boundaries and non-claims

| Stage | Assumption | Status | What breaks if false |
|---|---|---|---|
| S1 | the attacker can supply a PSBT or a caller forwards `SigHashTypes` | confirmed by code and arms 1, 2 | no scope reaches the signer |
| S1 | the victim input's index is at or past the output count | confirmed, `idx=1 n_out=1` | digest commits to an output; signature fails on the rebuilt tx |
| S2 | the victim prevout is legacy P2PKH or P2WPKH | confirmed for the demonstrated arms | taproot errors at the digest and produces no signature |
| S2 | the legacy constant is consensus behavior, not a btcd artifact | confirmed by the btcd comment and by arms 1, 2, 7 | the network would reject the signature |
| S3 | the attacker can build a transaction that reproduces the digest | confirmed for legacy and v0 witness | the signature does not transfer |
| S3 | the transaction is relayable | not measured | valid and script-accepted, but standardness and fee policy are untested |
| S4 | the external signer signs the 32 bytes it is given without its own policy check | assumed for the external signer; confirmed only for the SDK hand-off and attach, using a local stand-in key | a signer that inspects the PSBT would refuse |
| S5 | a deployed consumer trusts this verifier | assumed; no consumer in scope | no funds move |

The last proven stage is S4; S5 is argued only. The weakest link is S5, which is also the stage that
carries the difference between High and Critical. No taproot signature exists in this chain, and I did not
test fee or standardness policy.

## Dead ends and constraints

| Symptom | Root cause | What I do instead | What it means for you |
|---|---|---|---|
| The allowlist looks like a guard | `0x83` is allowlisted by design for the listing flow at `:145` | Treat the allowlist as policy, not a structural check; the index guard is the missing control | Removing `SINGLE|ACP` breaks the marketplace flow and leaves the override arm open |
| Errors are nil everywhere | `:670-673` and `:1600-1609` discard failures | Read the signature back and verify it; do not treat `err=nil` as evidence | A failed input returns an unsigned PSBT that still looks successful |
| Taproot does not reproduce the constant | `txscript/sighash.go:567-572` errors at the digest | Keep the demonstration on legacy and v0 witness arms | Do not generalize `0100...00` to every input type |
| A digest failure becomes a plausible hash | `:1497-1505` substitutes `GetRandomHash()` (`ffffffff` prefix) | Distinguish an absent signature from a wrong digest | A silent wrong hash is harder to notice than an error |
| Attacker-chosen prevout index crashes the SDK | `NonWitnessUtxo.TxOut[prevOut.Index]` is unguarded at eight sites | Use a valid index in the fund-path arms | Arm 6 is crash-class, an ingredient, not a theft route |
| The buying and batch builders keep the matching output | They copy the seller's input and its output at the same index | Use a builder that drops the output, or the hostile PSBT | The within-policy route needs a transaction builder outside those flows |

## Novelty

I searched the public web, GitHub issues, and advisory indexes on 2026-11-14. The only adjacent
public item that surfaced was Bitcoin Core PR #35984 and its Optech summary; no OKX advisory, CVE,
or GHSA for this SDK path appeared. Bitcoin Core merged
[PR #35984](https://github.com/bitcoin/bitcoin/pull/35984) on 2026-09-25 for the same unsafe
`SIGHASH_SINGLE` condition in wallet PSBT signing: `SignPSBTInput()` signed an input with no matching
output, while raw transaction signing already skipped it. Bitcoin Optech summarized the fix on
2026-10-02. This SDK at `89c5153f` still has the signing gap, and adds three things the Core fix does
not cover: a caller override that is not re-validated, signing loops that return `nil` after a failed
input, and an MPC helper that exports the degenerate digest to an external signer and substitutes a
random hash on digest failure. The btcd constant-hash behavior is documented upstream and is not
claimed as new; the contribution is the SDK-specific reach and the external-signer crossing.

## Suggested fix

This is a suggestion, ordered by what closes the chain.

1. Enforce `index < len(txOut)` whenever the effective sighash has the `SINGLE` bit, at every sink:
   `:293`, `:728`, `:755`, `:1340`, `:1349`, `:1438`, `:1454`, `:1733`, `:1768`, for every input type. On v0 witness inputs the faulty state
   is a zero-hash commitment, not the constant, so the check must be structural, not a comparison with
   `0100...00`.
2. Re-validate the override against `allowedSighashTypes` before it replaces `hashType` at `:1643-1645`.
   This closes the arm that needs no hostile PSBT.
3. Propagate per-input failures at `:670-673`, `:1600-1603`, `:1607-1609`, and the attach loop at
   `:1546-1548`, and stop substituting a random hash for a failed digest at `:1497-1505`; return the error.
4. Bounds-check `prevOut.Index` against the funding transaction's outputs at all eight sites.
5. Treat PSBT prevouts as untrusted and cross-check them against a trusted outpoint source. Restoring the
   commented-out `ToSignInput.Address` check at `:1646-1654` is hygiene; it does not close any route above.

Fixes 1 and 2 close S1 and S2 and make S3 and S4 unreachable. Fix 3 stops the silent-success behavior but
does not remove a signature that was already produced. The `SINGLE` check must stay even if the allowlist
changes, because a caller override and a `SIGHASH_NONE` PSBT both bypass the allowlist argument.
