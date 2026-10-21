# Local current-image Kanboard parity — 2026-10-21

The [saved result](result.json) passed 9/9 checks on a local arm64 image built
from the current `Dockerfile.opencode-kanboard-runtime` (SHA-256
`7a1ab9b257fb36a216fc1baafabc757436d0a15ffcb9498b6fbe697da3a9bf4b`).
The exact image was
`sha256:76bd7fcb18d052bd7bd744db6ce0db324c78210de8c5c52433bce6f27aecb513`,
PHP 8.4.26 with GD and SQLite, and OpenCode v2.0.32. The copied T01 observer
source, brief, prior result and both release archives were hash-checked before
the app arms started. The [runner](run.py) records those pins and fails on a
different local image.

The local build used this command from the repository root:

```sh
docker buildx build --load --platform linux/arm64 --progress plain \
  -f evals/native-qualification/Dockerfile.opencode-kanboard-runtime \
  -t nq-kanboard-current:arm64-20261021 evals/native-qualification
```

The build result must have the exact image ID above before repeating this
receipt. A new build with a different ID is a new runtime candidate and needs
its own reviewed receipt.

From the repository root, with Docker running and the two Kanboard archives
in a private directory as `vulnerable.tar.gz` and `fixed.tar.gz`, repeat with
a new private output path:

```sh
python3 evals/native-qualification/t02-evidence/opencode-v2-current-arm64-parity-20261021a/run.py \
  --archives /tmp/native-qualification-observer-20261019-final \
  --output /tmp/nq-current-arm64-parity-repeat-1
```

The archives are the pinned `kanboard/kanboard` release snapshots at commits
`f0f7d27007f5a788f14416c548421efd740b7bce` and
`a98bc5f855d4e7e47eb3425a6c7da6c6cc6748a3`; `observer_case.py` holds
their SHA-256 values. The runner verifies every extracted file before use.
Keep its private output outside the repository: it contains copied archives
and extracted source. A different image ID requires a new reviewed receipt.

Both arms made nine ordinary JSON-RPC calls through the loopback app. Bob's
private-project control was 403 in both. His `getSwimlane` returned the
created swimlane metadata on the vulnerable release and 403 on the fixed
release, matching T01. The saved [request and server traces](evidence/) are
redacted. Both owned containers and their databases were removed and ports
closed. An unrelated pre-existing Postgres container was left alone.

This is an offline application observer check with synthetic accounts and no
model/provider call. It does not qualify the cloud amd64 image, original
researcher observation, independent model review, or positive filing.
