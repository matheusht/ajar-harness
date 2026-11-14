# BTC PSBT sighash scope chain: report package

Chain report for `okx/go-wallet-sdk`, `coins/bitcoin/psbt_tx.go`, commit `89c5153f`. A PSBT author
chooses a sighash scope with the `SINGLE` bit that has no matching output, the digest collapses, the
signature stays valid on a rebuilt transaction, and the SDK hands the same 32 bytes to an external MPC
signer. Closed at S4; S5 (a deployed consumer crediting the result) is argued, not demonstrated.

## Quick start

```sh
sh poc/stage.sh
```

Prerequisites: `go` 1.23 or newer (observed `go1.26.4`), `shasum`, a writable temp directory. The first
build may fetch btcd and btcutil from the module proxy. The script copies `poc/module/` to a `mktemp`
directory, builds eight arms with `-trimpath -buildvcs=false`, and prints binary hashes plus every cell.
Exit status 0.

Expected output is `poc/expected.stdout`, verbatim. The lines that carry the chain:

```text
CELL A-declared-empty-options declared_psbt_sighash=0x83 digest_is_constant_01=true attacker_tx_script_0x33_sig_valid=true
CELL S-0x83 signer_digest=0100000000000000000000000000000000000000000000000000000000000000 (single-bug constant=true) attacker_tx_sig_valid=true err=<nil>
CELL A1-single-0x83 declared=0x83 script_engine_accepts_attacker_tx=true err=<nil>
CELL M-direct-0x83 mpc_signed_attacker_tx_sig_valid=true
```

The `0x01` cells in the same arms are the controls: same entry point and PSBT, no `SINGLE` bit, and the
signature fails. Nothing is broadcast and all keys are synthetic.

## Inventory

| Path | Contents |
|---|---|
| `report.md` | paste-ready report body, starting at `## Summary` |
| `impact.md` | impact and severity argument, including the 6.5 and 7.7 vector arithmetic |
| `chain.md` | five-stage table with anchors, proofs, controls, and the ASCII diagram |
| `metadata.json` | title, asset, commit, CVSS, `closed_at`, `fragile_stage`, `stages` array |
| `evidence/source-refs.md` | every source anchor used, the symbol, and the observation |
| `evidence/reliability.txt` | three-run result, exit code, stdout equality, per-stage state |
| `cleanup.md` | host effects, temp directory handling, absence of broadcast and live keys |
| `poc/` | unchanged PoC: `stage.sh`, eight arms, pinned `module/`, `expected.stdout`, `build-meta.txt` |
