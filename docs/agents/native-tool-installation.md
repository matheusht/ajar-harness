# Install native tool bundles and model images

The `install` command prepares the Linux **tool executor** used by Codex or OMP.
The separate `model-image-context` command prepares a build context for the Linux
model owner. Neither command activates an engagement or authorizes provider use.
The model process and tool environment keep separate identities and files.

The repository lock fixes Codex 0.166.0, OMP SDK 18.20.0 and Bun 1.4.4 for
`linux/arm64` and `linux/amd64`. Release archives have SHA-256 pins; every OMP
package has an integrity pin and exact destination. The retained Bun resolution
records the dependency source. The installer downloads only those archives,
verifies each checksum, unpacks regular files into a new private directory, and
copies the reviewed OMP tool sidecar. It runs no package scripts or downloaded
executable, creates no system install, and refuses an existing destination.

Use a canonical absolute directory on the operator's machine. The parent must
already exist. Keep the receipt outside the bundle, because its manifest hashes
every file inside the bundle.

```sh
mkdir -m 700 /private/native-tools
python3 tools/install_native_tools.py install \
  --runtime codex --platform linux/arm64 \
  --destination /private/native-tools/codex-linux-arm64 \
  --receipt /private/native-tools/codex-linux-arm64.receipt.json
python3 tools/install_native_tools.py install \
  --runtime omp --platform linux/arm64 \
  --destination /private/native-tools/omp-linux-arm64 \
  --receipt /private/native-tools/omp-linux-arm64.receipt.json
python3 tools/install_native_tools.py preflight \
  --receipt /private/native-tools/codex-linux-arm64.receipt.json
python3 tools/install_native_tools.py preflight \
  --receipt /private/native-tools/omp-linux-arm64.receipt.json
```

Choose the platform of the Docker or SSH tool environment, which may differ from
the host platform. The receipt's `profile_fields.tool_bundle` is the exact object
to include in that runtime's input profile before signing. Preflight rehashes the
tree and uses the adapter's existing bundle inspector. A modified binary, wrong
ELF architecture, missing SDK/native addon, old Bun version or changed sidecar
fails preflight. Moving a bundle requires producing and signing the updated path;
an installation receipt itself grants no engagement authority.

`ready_for_environment_check` and `execution_verified: false` mean that packaging
checks passed. The selected environment must still start the native executor and
return the pinned version/platform handshake, enforce its filesystem/process/
network boundary, and prove cleanup. The existing macOS model owner uses kernel
process identity and a no-fork sandbox.
Installing Linux tool bundles alone does not establish Linux model-host support;
the separate model owner and its actual startup/containment checks are required.

The installer uses Python's HTTPS trust store and needs GitHub release and npm
registry access. Its temporary archive is removed after extraction. An exception
removes the newly created bundle; a hard process/host loss can leave an incomplete
directory without a receipt, which must not be used as ready. Inspect that owned
directory before removing it and retrying. Never replace a directory belonging to
an active or historically pinned engagement.

The optional `--lock` argument supports a separately reviewed lock and the owned
archive fixtures. The receipt records its digest. It is not a mechanism for
bypassing signed runtime input checks.

Repeat the packaging failure workflows:

```sh
python3 evals/native-qualification/smoke/check_native_tool_install_e2e.py \
  --output /private/results/native-tool-installation.json
```

Those fixtures contain minimal ELF headers and fake SDK files. They establish
installer behavior, not native Linux compatibility. The installed release bundle
receipts and their later environment readbacks are separate evidence.

## Prepare a Linux model image

Run this on a build host with space for the selected release binary, temporary
acquisition and image. It produces a new private context, retains the host model
executable, and writes an external receipt. It invokes no Docker command and
executes no acquired code. Use the platform of the **model host**, independently
of the tool environment's platform.

```sh
python3 tools/install_native_tools.py model-image-context \
  --runtime codex --platform linux/amd64 \
  --base-image python@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39 \
  --destination /private/native-tools/codex-model-amd64 \
  --receipt /private/native-tools/codex-model-amd64.receipt.json
```

Use `--runtime omp` and a different destination/receipt for OMP. The Python base
above was observed in the hosted amd64 environment check; model compatibility
with that base still requires native startup. A base must provide Python 3,
its standard library, `/bin/sh` and the selected binaries' shared libraries.
Its registry digest fixes the supplied image; packaging does not inspect or
certify that image, and a different architecture needs its own verified base.

The context contains `/runtime/bin/model`, the private-bootstrap and network-relay
helpers, plus pinned Bun and the native executor bridge for Codex. Codex and Bun
reuse the existing archive pins. OMP uses the official standalone binary, with
its own exact byte count and SHA-256 pin. Its raw-asset limit leaves the general
archive limit unchanged. No npm installation or optional OMP dependency download
is included. The copied helpers come from the current checkout; their hashes and
modes are recorded in `runtime_manifest`.

The Dockerfile copies only the runtime tree as root-owned files: binaries are
`0555`, helpers `0444` and directories `0755`. The outer host context remains
`0700`. It has a public fixed PATH, an inert default command, and no build-time
code execution. Credentials, target inputs, account files and model configuration
are not build inputs. Model state belongs in the private owner's bounded
`/work/.model` directory at execution time.

Before signing a profile, complete the hosted build and readback workflow:

1. Pull the exact base digest and inspect its actual image ID and platform.
   Build the generated context on that architecture with Docker build networking
   disabled. Preserve the context receipt and complete built image ID.
2. Inspect an owned stopped container from the built image. Verify `/runtime`
   against `runtime_manifest`, including modes and root ownership. Reject
   unexpected mounts, inherited volumes, entrypoints, healthchecks or other
   configuration that the owner does not admit. Remove that exact probe.
3. Retain the context's `runtime/bin/model`: its canonical host path and SHA-256
   in `profile_fields.executable` are still required by input validation. Use the
   **built image's inspected ID** for the signed model host, not the base registry
   digest. Moving the host executable requires updating and signing its path.
4. Run the real model-owner startup, native-tool, credential containment,
   revocation and recovery workflows. A packaging receipt or `--version` result
   does not establish those behaviors. The owner repeats relevant file/image
   readbacks before releasing credentials.

The receipt has kind `native-model-image-context-receipt-v1`, status `prepared`
and `execution_verified: false`. Existing `preflight` accepts tool-bundle receipts
only. Model-image packaging is checked without binaries or Docker by:

```sh
python3 evals/native-qualification/smoke/check_model_image_install_e2e.py \
  --output /private/results/model-image-installation.json
```

These public-CLI fixtures use synthetic ELF headers and helper files on an owned
localhost server. Two limit-selection cases lower the archive ceiling inside an
isolated subprocess, avoiding a large test download. They prove packaging and
failure cleanup only; image construction, Linux native compatibility and provider
operation require separately recorded observations.
