# Cloud amd64 Kanboard parity attempt

Status: **blocked before parity execution** on 21 October 2026.

This bounded, no-provider attempt started from PR #174 commit
`513b662eda0345d943eb0582f7bc39a8a6512617`. The failure checks required the
local tag `t02-kanboard-runtime:amd64-live-prep` to resolve, without a pull, to
the previously published exact image ID
`sha256:9ef722322521322a1288a18427ba5bf6ce1479085c97e0ac821982eec4f01769`
on `linux/amd64`.

The tag was absent in the initially empty Docker daemon. The documented build
route completed successfully from the pinned base and Dockerfile, but it
created image ID
`sha256:d0b96c08541486079634fd70a0ffb221c32b07a2a04a1a2ab7d041912a7c9a91`.
That is not the required image, so admission stopped. A successful rebuild of
similar inputs is not evidence for the unavailable byte-exact image.

Consequently:

- neither pinned public Kanboard archive was retrieved or extracted;
- neither vulnerable nor fixed application arm was started;
- ordinary behavior and the vulnerable-versus-fixed split were not run;
- no researcher bundle, provider request, model call, live target, or
  credential was used; and
- the historical arm64 13/13 and 29/29 results remain historical arm64
  evidence only.

The task-created mismatched image and its seven recorded BuildKit cache
records were removed individually. Final readback found no containers, images,
volumes, or build cache, the same three default network IDs as the frozen
baseline, and no task image tag. No global prune was used.

Files:

- `inputs.json` pins the qualification base, source files, expected runtime,
  and both public archive inputs.
- `result.json` is the sanitized failure and cleanup receipt. It contains no
  raw build log, CA material, proxy value, credentials, or private source.
- `run-command.txt` records the redacted build and parity commands and marks
  the parity command as not run.
- `verify.py` checks the receipt, source pins, blocked-state semantics,
  redaction boundary, and false-proof cases without Docker or network access.
- `verification.json` records the public verification result.

This receipt does not establish current-image Kanboard parity. The remaining
input is the exact image
`sha256:9ef722322521322a1288a18427ba5bf6ce1479085c97e0ac821982eec4f01769`
made available through a supported route under the pinned tag, or a trusted
OCI artifact whose loaded image ID verifies exactly. A different rebuild must
not be substituted.

PR #174 later added a separate local arm64 application-parity receipt at
`b9323ee64d2e670aaca22e89d77ceb8cab82846e`. It does not qualify this cloud
amd64 image and does not change the blocked status above.

A later bounded cloud rerun is safe to prepare if its candidate is assigned a
new immutable image ID and input receipt, made locally available through a
supported route, and checked before any image execution. The rerun must keep
`--pull=never`, verify the two archive hashes before extraction, preserve the
same ordinary and differentiating checks, and restore a newly frozen Docker
baseline. It must use a new evidence directory rather than overwrite this
failed attempt.
