# Install native tool bundles

The installer prepares the Linux **tool executor** used by Codex or OMP. The
credentialed model process remains a separately owned host runtime. This command
does not install a host runtime, activate an engagement, or authorize provider use.

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
network boundary, and prove cleanup. The current protected host model owner uses
macOS kernel process identity and a no-fork sandbox. Installing these Linux tool
bundles does not establish unattended Linux host support.

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
