# PSBT signing accepts output-blind sighash scopes; the signature stays valid after the attacker rewrites the outputs (coins/bitcoin @ 89c5153f)

**Severity claim:** High, "Unauthorised access to sensitive user data or funds in limited scope" (Critical is conditional on a deployed consumer; none in this repo).
**CVSS 3.1:** `AV:N/AC:L/PR:L/UI:N/S:C/C:N/I:H/A:N` = 7.7 (S:U read 6.5; unauthenticated-reachable 8.6).
**Weakness:** CWE-347 (Improper Verification of Cryptographic Signature); secondary CWE-682 (Incorrect Calculation), CWE-863 (Incorrect Authorization), CWE-1284/CWE-248 (prevout index).

Hi OKX team,

`coins/bitcoin/psbt_tx.go` signs a signature scope that ends up committing to nothing. Two things make that happen, the caller's `SigHashTypes[0]` overrides the allowlist at `:1643-1645` without being re-checked against it. And even with no caller options at all, the PSBT's own declared sighash goes straight into the signer, so a hostile PSBT is enough. Three digest outcomes follow, and I have all three running offline against a byte-exact copy of the pinned commit: the legacy constant hash `0x01…00`, a v0-witness digest whose outputs commitment is the zero hash, and plain `SIGHASH_NONE`. In each case the signature stays valid on a transaction I rebuilt to pay a script the victim never agreed to.

There is a third path, and it needs neither the override nor any caller option. The SDK's own MPC API computes the digest from the PSBT and hands it to the external signer (`GenerateMPCUnsignedPSBT`, `:1473` into `CalcInputSigHashForUnsignedPSBT`, `:1438`), and `GenerateMPCSignedPSBT` (`:1528`) attaches whatever the signer returns. For a hostile PSBT the value handed over is the **constant `0100…00`**, and the MPC key cannot tell: it sees a 32-byte hash. Arm 7 runs that whole flow inside the SDK. One command below reproduces every cell.

## Root cause
The allowlist is at `coins/bitcoin/psbt_tx.go:31-36` (`SINGLE|ACP`, `ALL|ACP`, `ALL`, `DEFAULT`). Four things that we can assume from these:

1. **The override is not re-validated.** `:1643-1645` takes the caller's number verbatim:

       if toSignInput != nil && len(toSignInput.SigHashTypes) > 0 {
           hashType = txscript.SigHashType(toSignInput.SigHashTypes[0])
       }
`ToSignInput` and `SignPsbtOption` are exported request objects (`:77-89`), JSON-tagged, so this is the shape a dApp or a service hands to the SDK.

2. **The PSBT-declared sighash reaches the sink with no index/output guard, and the MPC API hands it to the hardware/MPC signer.** `SignRawPSBTTransaction` (`:642`) does check the declared value against the allowlist (`:667`) and then signs it (`:668`, into `signPSBTPacket` at `:683`; the legacy branch computes the digest at `:728`). `0x83` (`SINGLE|ANYONECANPAY`) passes that check. The `SINGLE` bit is still there, and nothing checks whether the input's index has a matching output. The MPC digest helpers are the same: `calcInputSigHash` (`:1340`) and `CalcInputSigHashForUnsignedPSBT` (`:1438`). `GenerateMPCUnsignedPSBT` returns those digests in `SignHashList` for the external signer, and `GenerateMPCSignedPSBT` swallows the attach error too (`:1541-1543`, `//return nil, err`).

3. **Both signing loops discard their own errors.** `SignRawPSBTTransaction` has `err = signPSBTPacket(...); if err != nil { //return "", err }` (`:670-673`). `SignPsbtWithKeyPathAndScriptPath` has `err = signPsbtWithKeyPathAndScriptPath(...); if err != nil { continue }` (`:1600-1603`) and `err = psbt.Finalize(p, i); if err != nil { }` with an empty body (`:1607-1609`). Both return `hex.EncodeToString(b.Bytes()), nil`. A failed input comes back as an unsigned PSBT with no error, which is why the `err=nil` in my cells is decoration. The cells' evidence is the signature read back and verified, not the returned error.

4. **What the digests do.** `SINGLE` with `index >= len(txOut)`:
   - **legacy**: btcd returns the consensus constant hash (`txscript/sighash.go:110-115`), and the upstream comment says it plainly: *"a bug in the original Satoshi client implementation means specifying an index that is out of range results in a signature hash of 1… this buggy behavior is now part of the consensus… presents an opportunity for attackers to cleverly construct transactions which can steal those coins provided they can reuse signatures."*
   - **v0 witness (P2WPKH/P2WSH)**: btcd writes `zeroHash` for the outputs commitment (`txscript/sighash.go:279-287`), which is `NONE`-equivalent. Not an error.
   - **taproot**: this one does error (`txscript/sighash.go:567-572`), but fact 3 means the caller still sees `err=nil` and gets an unsigned input.

`SIGHASH_NONE` (`0x02`) commits to no outputs at all, by definition.
The defect is not that btcd has this quirk. The defect is that the signing entries let the scope through and hide the failure, so the SDK produces the signature and the caller never learns.
Three more facts from the same file, because they shape the reach:

- **The SDK's own listing flow writes the scope that triggers this.** `GenerateMPCUnsignedListingPSBT` signs the seller input with `SIGHASH_SINGLE|ANYONECANPAY` (`:145`), and nothing in the builder enforces that the final transaction keeps an output at that input's index. So the within-policy route needs no hostile caller: a buyer-built transaction that drops the matching output is enough, and the seller's signature collapses.
- **The MPC digest helpers replace an error with a random hash.** `:1497-1505` catches a digest failure and substitutes `GetRandomHash()` (`:1519-1526`, an `"ffffffff"`-prefixed random value) into the `SignHashList` the external signer is asked to sign. A failing input becomes a plausible-looking hash instead of an error.
- **The PSBT's prevout index is used unguarded.** `NonWitnessUtxo.TxOut[prevOut.Index]` appears eight times (`:558`, `:602`, `:659`, `:694`, `:1401`, `:1487`, `:1579`, `:1636`). Arm 6 shows an attacker-chosen index panicking both entry points.

Two smaller facts from the same file. The `ToSignInput.Address` guard is commented out (`:1646-1654`); restoring it is hygiene, not a fix for any route below, because the demonstration passes an empty or correct address. And prevout `PkScript`/`value` are read out of the PSBT with no cross-check (`:1636-1642`).

## Steps to reproduce
Offline, deterministic, synthetic keys, no broadcasts. One command (workstation: darwin/arm64, `go1.26.4`):

    ./poc/stage.sh
It copies the pinned `coins/bitcoin` sources that ship in `poc/module/` to a temp dir, builds the six arms with `-trimpath -buildvcs=false`, and prints the cells plus the binary hashes. `poc/expected.stdout` is that output verbatim, and I confirmed two runs are identical.

**Arm 2 is the most important: a hostile PSBT, no caller options.**

    CELL A-declared-empty-options declared_psbt_sighash=0x83 digest_is_constant_01=true attacker_tx_script_0x33_sig_valid=true
    CELL B-declared-nil-option  declared_psbt_sighash=0x83 digest_is_constant_01=true attacker_tx_script_0x33_sig_valid=true
    CELL C-raw-psbt-entry       declared_psbt_sighash=0x83 digest_is_constant_01=true attacker_tx_script_0x33_sig_valid=true
The PSBT declares `0x83`, which is allowlisted; the victim's input sits at index 1 and the tx has one output; the digest collapses to the constant; the signature verifies inside my attacker transaction (their input plus the victim's UTXO, one output to `0x33…`). Empty `ToSignInputs`, a `nil` option, and `SignRawPSBTTransaction` all produce the same result, all with `err=nil`.

**Arm 1, legacy `SINGLE` through the override, including the allowlist's own seller type:**

    CELL S-0x03 signer_digest=0100…00 (single-bug constant=true) attacker_tx_sig_valid=true
    CELL S-0x83 signer_digest=0100…00 (single-bug constant=true) attacker_tx_sig_valid=true
    CELL S-0x01 signer_digest=f6da778b… (single-bug constant=false) attacker_tx_sig_valid=false

**Arm 3, v0 witness (`P2WPKH`), 2-in/1-out:**

    CELL W2-p2wpkh-single original_valid=true redirected_output_to_0x22_script_still_valid=true
    CELL W3-control-0x01 redirected_still_valid=false

**Arm 4, `SIGHASH_NONE`:**

    CELL H1R-0x02 original_valid=true redirected_output(999 to 0x11..)_still_valid=true
    CELL H1R-0x01 original_valid=true redirected_output(999 to 0x11..)_still_valid=false

**Arm 5, allowlisted `0x83` with an appended input:** `sig_survives_appended_input=true`, control `false`.

**Arm 8, script-engine acceptance:** the attacker transaction carrying the constant-hash signature (victim input at index 1, one output to the attacker) is run through btcd's script engine with `StandardVerifyFlags`:

    CELL A1-single-0x83 declared=0x83 script_engine_accepts_attacker_tx=true err=<nil>
    CELL A2-control-0x01 declared=0x01 script_engine_accepts_attacker_tx=false err=signature not empty on failed checksig

**Arm 6, attacker-chosen prevout index:** the PSBT points at index 99 of a one-output funding transaction; both entry points panic instead of returning an error.

    CELL P-raw panic=runtime error: index out of range [99] with length 1
    CELL P-keypath panic=runtime error: index out of range [99] with length 1

**Arm 7, the SDK's own MPC flow.** Hostile PSBT in, `GenerateMPCUnsignedPSBT` out, sign the returned hash with the key, `GenerateMPCSignedPSBT` back, signature checked against the attacker's transaction:

    CELL M-direct-0x83 declared=0x83 signer_digest=0100…00 digest_is_constant_01=true
    CELL M-direct-0x83 mpc_signed_attacker_tx_sig_valid=true
    CELL M-control-0x01 declared=0x01 signer_digest=bfb50792… digest_is_constant_01=false
    CELL M-control-0x01 mpc_signed_attacker_tx_sig_valid=false

## Suggested fix

1. Enforce `index < len(txOut)` whenever the effective sighash has the `SINGLE` bit, at every sink (`:293`, `:728`, `:1733`, `:1340`, `:1438`) and for every input type. On v0 witness inputs that condition is `NONE`-equivalent rather than the constant, so the check has to be structural, not a comparison against `0x01…00`. Removing `SINGLE|ACP` from the allowlist would also close the within-policy route, at the cost of the marketplace flow it exists for.
2. Re-validate any override against `allowedSighashTypes` before it replaces `hashType` (`:1643-1645`).
3. Propagate the per-input errors (`:670-673`, `:1502-1516` digest failure, `:1541-1543`, `:1600-1603`, `:1607-1609`). Today a failed input returns `nil` and an unsigned PSBT. The MPC digest path must not substitute a random hash either (`:1497-1505`): return the error.
3b. Bounds-check `prevOut.Index` against the funding transaction's outputs (`:558`, `:602`, `:659`, `:694`, `:1401`, `:1487`, `:1579`, `:1636`). Arm 6 panics.
4. Treat PSBT prevouts as untrusted and cross-check them against a trusted outpoint source.
5. Restore the `ToSignInput.Address` check (`:1646-1654`, needs `reflect` back in the imports) as hygiene. It does not stop the routes above.

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

## AI usage disclosure
Per policy: the discovery, the harness and this draft were AI-assisted, using a model inside a purpose-built harness the operator authorized. Every claim above was executed and reproduced offline against byte-exact copies of the pinned source, and I validated each cell by hand before filing.

## Attachments
`btc-psbt-sighash-override-poc.zip` (58 KB) holds `module/` (the pinned `coins/bitcoin` sources, files byte-identical to `89c5153f`), seven arm sources, `stage.sh`, `expected.stdout` and `build-meta.txt` with full SHA-256s. `VIDEO-POC.md` is the storyboard and the recording commands; happy to record the video PoC if you want one.

Thanks,
matheusht
