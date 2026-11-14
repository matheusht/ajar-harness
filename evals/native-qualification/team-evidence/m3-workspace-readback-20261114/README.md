# Trusted worker workspace readback

The host Environment adapter now reads actual worker files through two bounded
operations. The model cannot select a host filesystem path or provide a digest in
place of these reads.

- `read_workspace_manifest(path='/work')` returns `{operation_id, path,
  manifest_sha256, manifest}`. The path must be `/work` or a normalized directory
  below it. The manifest maps relative paths to exact `{sha256, mode, size}` and
  uses the contract's UTF-8, sorted-key, trailing-newline canonical hash.
- `read_artifact(relative_path, max_bytes)` returns `{operation_id, path,
  output_sha256, bytes, content}`. `bytes` is the byte count and `content` contains
  the actual bytes. The caller's cap cannot exceed the signed workspace/output
  caps or the existing publication limit.

Successful callbacks are result-only environment observations. Both include the
explicit operation ID, exact resource receipt, settled status and `/work/...`
path. Manifest callbacks add manifest_sha256 and files (integer count); artifact
callbacks add output_sha256 and bytes (integer count). They never include raw
artifact bytes. Existing publication checks run before callbacks or returned
content. The controller still owns protected storage and known-secret handling.

The adapter launches the fixed standard-library helper with `python3 -I -S`, an
explicit PATH limited to immutable image directories, and `/` as its working
directory. It uses the same signed worker UID, exact container identity, dispatch
guard and active lease. The image must provide Python 3. No helper is loaded from
the writable workspace, and no host bind or Docker copy path supplies evidence.

The helper opens paths relative to a descriptor for `/work`, refuses symlinks and
nonregular artifacts, bounds reads, and checks file stamps and directory identities.
A manifest does a second metadata traversal to detect concurrent tree changes.
Modes are preserved exactly, unlike the read-only mode remap used for `/input`.
Manifests require at least one file and obey signed workspace/output bounds plus
the existing 8 GiB / 200,000-file source limits. No raw body is spooled to disk.

This is readback evidence at the time of the read. A later matching manifest does
not prove which bytes an earlier experiment executed. Execution capture must bind
the actual command, source, instrument and clean-start state independently.

## Repeatable controls

```sh
python3 evals/native-qualification/smoke/check_environment_workspace_e2e.py --output /tmp/environment-workspace.json
python3 evals/native-qualification/smoke/check_environment_transport_e2e.py --output /tmp/environment-transport.json
python3 evals/native-qualification/smoke/check_environment_stdio_e2e.py --output /tmp/environment-stdio.json
```

Requires Python 3 and local process/filesystem access. At this isolated branch
checkpoint, use PYTHONPATH pointing to the coordinator checkout's tools directory
for engagement_contract; integration must rerun with that module in the same tree.
Expect exit zero and status passed. All fake Docker commands are explicitly named
simulations; no Docker daemon or SSH host is used.

The 28 readback controls run the real helper on actual temporary local files,
with a test-only mapping of `/work` to that tree. Race cases insert a synchronized
filesystem mutation after an actual read and verify that the mutation happened;
this shim supplies timing, while the helper's descriptor/stamp checks detect the
changed object. Controls cover exact hashes/modes, operation binding, empty files,
path escapes, symlinks, FIFOs, byte limits, withheld unsafe content, mutation and
revocation. The initial before-readback result records the missing API. The final
scenario corrected race-shim string escaping and added the root trailing-slash
case before claiming the race results.

The22 existing transport and9 persistent-pipe controls also passed. Real Docker
and SSH workspace reads, live research and earlier-execution identity remain
unverified. Source/dependency and result hashes are recorded in manifest.json.
