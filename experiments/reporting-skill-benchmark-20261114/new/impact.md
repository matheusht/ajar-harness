## Impact

Affected: `okx/go-wallet-sdk`, `coins/bitcoin/psbt_tx.go`, commit `89c5153f`, tested offline on darwin/arm64.
An attacker who can hand a PSBT to that package, or who can get a caller to forward a
sighash override, obtains a signature that commits to no output. That signature stays valid on a
transaction the victim never approved, paying any script the attacker chooses. No private key, no
credential, and no user interaction are involved; the only input is data.

Three consequences follow from the demonstrated stages, in order of distance from the code:

1. **SDK boundary.** A Go caller that trusts this package to sign what it was asked receives a
   signature that is valid for a different transaction. The caller has no signal: both signing loops
   return `err=nil`, and a wrong digest is replaced by a random hash rather than an error.
2. **External signer boundary.** `GenerateMPCUnsignedPSBT` exports the same 32 bytes in
   `SignHashList`, and `GenerateMPCSignedPSBT` attaches whatever signature comes back. An unattended
   MPC or hardware signer sees only a digest, so it cannot tell that the value commits to no output.
   The signature it returns is a bearer instrument for that input.
3. **Consumer boundary.** A service that credits, releases, or settles on a signature after verifying
   it with this code moves funds to the attacker. This stage is argued, not run: no consumer exists in
   this repository, and I did not name one.

### Scores

The origin vector is `CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:C/C:N/I:H/A:N`. With `C:N`, `I:H`, `A:N`:

```text
ISS            = 1 - ((1 - C)(1 - I)(1 - A)) = 1 - (1 * 0.44 * 1) = 0.56
Impact (S:U)   = 6.42 * 0.56 = 3.60
Exploit (S:U)  = 8.22 * 0.85 (AV:N) * 0.77 (AC:L) * 0.62 (PR:L) * 0.85 (UI:N) = 2.84
Base (S:U)     = Roundup(min(3.60 + 2.84, 10)) = 6.5
```

That is the **SDK-boundary score, 6.5**: the artifact yields a signature, not a transfer, and scope is
unchanged because nothing outside the signing call is yet affected.

```text
Impact (S:C)   = 7.52 * (0.56 - 0.029) - 3.25 * (0.56 - 0.02)^15 = 3.99
Exploit (S:C)  = 8.22 * 0.85 * 0.77 * 0.68 (PR:L, changed) * 0.85 = 3.11
Base (S:C)     = Roundup(min(1.08 * (3.99 + 3.11), 10)) = 7.7
```

That is the **chain-level score, 7.7**, and it is the number the platform field should carry. Scope
changes because the verifier's failure crosses into the external signer's decision, and potentially a
consumer's authorization: the signer is asked to authorize bytes whose meaning lives in another
component. The `PR:L` reflects a caller or service that can submit a PSBT; the `AV:N` reflects remote
submission of data, not a network exploit.

For reference, dropping the precondition to `PR:N` with `S:C` gives `Exploit = 3.89` and
`Base = Roundup(1.08 * (3.99 + 3.89)) = 8.6`, which is the source vector's note for an unauthenticated
submission path. I did not observe such a path, so 8.6 is not claimed.

### Which link carries the score, and the ceiling

The score is carried by S4, because that is where the collapsed digest (S2) stops being an internal
value and becomes an instruction to a signer that cannot audit it. S1 through S3 are reachable within a
single SDK process; S4 crosses a trust boundary between the SDK and the key holder. That crossing is
what justifies `S:C`. S5 is the link that would justify the program's direct-fund-loss tier, and it is
the one I did not prove.

Severity, stated exactly:

- **6.5** is what the code alone supports: a signature the caller did not intend, no funds moved.
- **7.7** (High) is the chain-level claim and applies only while the S4 path is exported as it is today.
- **Critical** is conditional on a deployed consumer that trusts this verifier and settles on its
  result. The existing internal report states that condition; I found no such consumer in this
  repository and name none, so the tier I claim is High, not Critical.

Floor, not sum: the strongest independently reachable link is S2/S3 (a valid signature on a rebuilt
transaction). S4 raises it because the signature is handed to a component that cannot re-derive intent.
S5 would raise it further and is capped in prose.

### Non-claims

No mainnet broadcast and no live keys; keys and UTXOs are synthetic. Arm 8 shows the transaction passes
btcd's script engine under `StandardVerifyFlags`; fee and standardness policy are untested, so I claim a
script-valid transaction, not a relayable one. Taproot errors at the digest level and produces no
signature, so no taproot theft is claimed. The MPC signing step in the PoC uses a local test key to stand
in for the external signer; the fact demonstrated is what the SDK hands out and attaches, not the
behavior of any specific MPC deployment.
