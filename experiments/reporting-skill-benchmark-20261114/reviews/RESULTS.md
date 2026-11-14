# Benchmark results — chain reporting

Same finding, same PoC, same expected output. `A` is the new chain overlay; `B` is the
pre-refactor package. Mapping is in `MAPPING.private.md`, outside the reviewer copies.

## Blind scores

| Reviewer | A | B | Notes |
|---|---:|---:|---|
| R1 (A first) | 91 | 59 | B gate 3/6; no stage table, no per-stage state, arm-count conflicts, meta. |
| R2 (B first) | 87 | 59 | B gate 3/6; no stage table, unanchored 6.5/8.6, unsupported within-policy route. |
| R3 (A first) | 87 | 59 | A's severity condition contradicted `impact.md`; reliability hash was a placeholder. |
| Final verification (corrected A) | 100 | — | One summary-consistency copyedit remained; applied after the score. |

Mean before the final copyedit: A 88.3, B 59.0. R1–R3 all chose A as more triage-ready.

## What the reviewers rewarded

- The chain overview table and ASCII diagram gave a closed S1–S4 chain with `Closed at: S4` and
  `S5` explicitly `argued`.
- Per-stage anchors, edge anchors, and `0x01` controls made the evidence local to each stage.
- `3/3` per-stage reliability with a real stdout SHA-256 and the environment removed the
  "single green run" objection.
- The boundary table distinguished the SDK hand-off (proven) from external-signer policy
  (assumed) and the consumer stage (argued).

## What they caught

- A first-pass severity contradiction: At a glance and metadata said High only with a consumer,
  while `impact.md` said 7.7 High at S4 and only Critical needed S5. Fixed.
- A placeholder `<three-run-identical>` instead of a hash, and `build-meta.txt`'s two-run claim
  versus the report's three runs. Fixed with the actual hash and a provenance note.
- Wrong anchors for the witness path and the MPC attach loop. Fixed after checking the shipped
  `psbt_tx.go`: `:755`/`:1768` (`RawTxInWitnessSignature`), `:1349`/`:1454`
  (`CalcWitnessSigHash`), `:1784` (`updater.Sign`), `:1546-1548` (attach error).
- The artifact name and checksum were stale. Fixed to
  `btc-psbt-sighash-override-report.zip`; final SHA-256
  `dea65992d15e6ee26d59f99c6a5926dee8584b4d1a9eaf6cccba0fbd94f0771e`.
- B's strongest narrative claim, the "within-policy listing flow" route, had no arm and was
  judged cryptographically suspect. It is not part of A's demonstrated chain.

## Package check

- `new/poc/stage.sh` exits 0; stdout matches `new/poc/expected.stdout` byte for byte.
- Three runs produced the same stdout SHA-256
  `35abd6f32cefc948c84b186e2fd224f8795b58607143acb34e1742cf2185ecce`.
- `new/poc/module` source files are `cmp`-equal to the upstream checkout at `89c5153f`; `go.sum`
  is added. Module tree hash:
  `130469d5df260543439115a4e0c2520c2a34f6c9e5ba7ef0e67e78f5c1f5e403`.
- The chain report, impact, metadata, evidence, chain table, and zip all use the same S1–S5 IDs.
