# Fresh cloud amd64 Kanboard candidate attempt

Status: **blocked during image build, before candidate registration or image
execution** on 21 October 2026.

This bounded, owned, no-provider attempt started from PR #175 commit
`9c0c0e3f0f7d25fece945a564c8c991a5368d8b9`. The outer Docker baseline was
captured before the build: no containers, images, volumes, or BuildKit cache;
only the three default networks; and no fresh candidate tag.

The supported `linux/amd64` Buildx route resolved the exact effective base and
used the existing managed CA bundle as a BuildKit secret. The unchanged
Dockerfile then asked Alpine for PHP 8.4.26-r0. The live package repository
offered 8.4.27-r0, so `apk` rejected every exact 8.4.26-r0 package constraint
and the build stopped with `apk` exit code 11. No image was loaded and no
candidate image ID was registered.

Consequently:

- no `docker run` command or image inspection after a successful build ran;
- neither public Kanboard archive was retrieved or extracted;
- neither vulnerable nor fixed application arm started;
- ordinary controls and the vulnerable-versus-fixed split were not observed;
- no researcher bundle, provider request, model call, target contact, or
  external credential was used; and
- this receipt does not establish fresh cloud amd64 application parity.

Six BuildKit cache records were created after the empty baseline. They were
removed by exact ID, with two zero-byte parent records retried only after
their children were gone. Final readback found zero cache records, no
containers, images, or volumes, the same three network IDs, and no candidate
tag. No global prune was used.

Files:

- `inputs.json` records the exact base, Dockerfile, managed-CA provenance,
  Docker baseline, source pins, candidate intent, and public archive pins.
- `result.json` records the bounded build failure, non-execution facts, exact
  cache cleanup, restored baseline, limitations, and inherited follow-ups.
- `failed-build-command.txt` is the redacted historical build shape. It
  refuses to overwrite an existing tag and contains no parity runner.
- `verify.py` validates narrow receipt schemas, full command bytes, source
  immutability, fail-closed semantics, cleanup, and broader secret-key cases
  without Docker or network access.
- `verification.json` is the resulting public verification receipt.

The immutable PR #175 blocked receipt and its hash-pinned runner were not
changed. Because this attempt blocked before a candidate existed, the
inherited PR #175 verifier and command weaknesses were not rewritten here:
its command substring/order check can be hidden in a false shell branch, its
secret scan misses quoted JSON `Authorization` and `api_key` keys, its
historical build can retag before exact-ID admission, and its runner baseline
starts after that build. A later successful candidate lane must address those
defects additively, inspect a supplied registered image before replay, and
keep build creation separate from replay.

The exact remaining input is a reproducible supported source for the pinned
8.4.26-r0 Alpine packages under the existing Dockerfile and base constraints,
or an explicit operator decision to qualify a newly pinned runtime version in
a separate change. This task did not infer that decision or alter the pin.
