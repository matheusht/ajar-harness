# Model image packaging evidence — 14 November 2026

This is local installer evidence using an owned localhost asset server, synthetic
ELF headers and synthetic helper files. No release executable was downloaded or
run, no Docker daemon was contacted, no image was built, and no provider or target
was called. This checkpoint does not qualify a Linux model host.

The [failure-first workflow](../../smoke/check_model_image_install_e2e.py) was
written before the installer change. At base `fd8674b1`, all 23 cases failed
because `model-image-context` did not exist ([before](before.json)). The candidate
passed all 23 public-CLI cases ([after](after.json)), and the existing tool
installer passed its 10 unchanged cases ([regression](tool-regression.json)).
The [manifest](manifest.json) pins the checked installer, scenarios, lock and
saved results. The new bootstrap helper belongs to the separate model-owner
integration unit; this fixture verifies its required packaging path and bytes,
not that helper's behavior.

The scenarios cover Codex and OMP on both declared architectures, raw checksums
and exact lengths (including missing Content-Length), truncated downloads, the
selected ELF architecture for model and Bun, missing or linked helpers, existing
destinations and receipts, receipt aliases, mutable/injected base references,
version mismatch, cleanup and the generated context's contents/modes. Two cases
reduce only the general archive ceiling to 256 bytes inside a subprocess before
calling the same CLI. A 512-byte raw fixture then passes its explicit reviewed
size while an archive of the same size fails. This proves limit selection without
allocating a large test asset; it is not a full-size release download.

Repeat from the repository root with Python 3 and localhost binding available:

```sh
python3 evals/native-qualification/smoke/check_model_image_install_e2e.py \
  --output /tmp/model-image-packaging.json
python3 evals/native-qualification/smoke/check_native_tool_install_e2e.py \
  --output /tmp/native-tool-packaging.json
```

Expected: both commands exit zero and write `status: passed`; no Docker or native
executable is needed. Temporary fixture directories and localhost server are
removed at completion. The repository lock's standalone OMP pins come from the
[official 18.20.0 release metadata](https://api.github.com/repos/can1357/oh-my-pi/releases/tags/v18.20.0):
`omp-linux-x64` is 287484080 bytes and `omp-linux-arm64` is 244435960 bytes. The
actual asset bodies were not fetched in this check.

Before use, the [installation guide](../../../../docs/agents/native-tool-installation.md#prepare-a-linux-model-image)
requires an actual image build, immutable image/file readback, native startup and
containment/recovery checks. Keep the installed host executable for signed input
validation. Packaging does not release credentials or activate an engagement.
