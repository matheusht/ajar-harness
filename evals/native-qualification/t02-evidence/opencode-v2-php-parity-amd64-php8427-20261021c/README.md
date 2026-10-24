# Cloud amd64 Kanboard PHP 8.4.27 current-runtime qualification

This receipt records a successful, bounded, owned two-arm application
qualification on 21 October 2026. A newly built `linux/amd64` image pinned all
installed `php84*` packages to `8.4.27-r0`; the preserved ordinary observer
then matched the historical T01 application semantics on both releases.

This is **not** byte-identical PHP 8.4.26 parity. The sealed 8.4.26 build
failure in the parent PR remains unchanged. This result qualifies only image
ID
`sha256:241dd8f788c62d5c9ef87bdab07ce1f05aca7db0199d532a68b5910c7397f7de`
for this owned observer. The live Alpine repository is not a durable package
snapshot.

## Observed result

- The direct base digest and exact 8.4.27 package set built once on
  `linux/amd64`.
- The candidate was registered by immutable ID before its first execution.
- All 13 installed `php84*` packages had revision `8.4.27-r0`; PHP reported
  8.4.27 and the required `gd` and `pdo_sqlite` modules were present.
- Both public Kanboard archives matched their frozen hashes before either arm
  could start.
- Both arms proved Alice's authorized project/swimlane reads and Bob's project
  denial. The vulnerable arm returned Bob the exact synthetic swimlane
  metadata; the fixed arm denied that read with 403.
- The preserved runner passed 32/32 checks, including historical semantic
  comparison, source pins, arm cleanup and its post-build Docker baseline.
- The outer cleanup removed only the recorded task image and seven exact
  BuildKit cache IDs. The complete pre-build Docker baseline was restored.

No provider or model was called. No engagement or live target was contacted;
no external credential or researcher bundle was used. Raw logs, build
metadata, container IDs, ports, private paths and disposable databases remain
private. The scoped `status: pass` fields in `candidate.json` and
`runtime-admission.json` apply only to their local gates. `result.json`
remains `needs_review`; only `verification.json` is the public offline oracle.

## Files

- `inputs.json` binds source, runtime, archive and baseline inputs.
- `candidate.json` is the immutable pre-execution build-registration receipt.
- `runtime-admission.json` is the exact-ID package/PHP admission receipt.
- `result.json` records the pre-oracle application result and outer cleanup.
- `evidence/` contains the sanitized two-arm observer result and redacted
  request traces.
- `build-command.txt` preserves the one-attempt build shape for historical
  provenance. It is not the replay path.
- `run-command.txt` is fail-closed: it never builds, tags or pulls and refuses
  anything except the already supplied exact image and platform.
- `docker-observations.txt` is a sanitized lifecycle readback.
- `verify.py --self-test` verifies the receipt without Docker or network.

The task image was removed during exact cleanup, so replay requires that the
same immutable image already be supplied through an authorized route. Do not
substitute a rebuild. Hosted CI was not used to establish this source result.
