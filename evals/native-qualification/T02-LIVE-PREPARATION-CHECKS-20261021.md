# T02 fail-closed live-path preparation checks

This document supplements `T02-V2-MANAGED-LIVE-CHECKS-20261020.md`. It prepares two source defects found during OSLIT qualification. It does not authorize live inference or claim that the managed upstream reaches an owned receiver. `--live-free` must continue to stop with `cloud_live_route_not_qualified` before output creation or Docker.

## Explicit runtime trust input

A future live launch must supply both `--live-runtime-ca` and `--live-runtime-ca-sha256`. The runner rejects either input outside `--live-free`. For a live launch it rejects a missing half, a malformed digest, a relative or control-character path, a symlink, a nonregular file, group- or world-writable bytes, an empty or larger-than-4-MiB file, a private-key block, malformed PEM, or a digest mismatch.

The runner opens the file without following the final symlink, reads at most the fixed bound, checks the same descriptor before and after the read, and parses the in-memory bytes as a certificate-only bundle. Any non-whitespace bytes outside complete PEM certificate blocks make the whole bundle invalid. It must not print or retain the host path, PEM bytes, certificate subjects, proxy value, or environment. A valid bundle still reaches the unconditional live denial.

If a later reviewed change enables execution after all external gates pass, the runner writes the already validated bytes to a mode-0600 file inside its private per-run temporary directory. It mounts that snapshot read-only at `/fixture/runtime-ca.pem` and requests exactly `SSL_CERT_FILE=/fixture/runtime-ca.pem`. It never mounts the mutable caller path or copies trust bytes into the image, archived source, or ordinary receipt. The existing verified temporary cleanup removes the snapshot only after producer stop and owned-resource absence.

Container readback treats proxy, credential, and trust environment variables as critical. Safe file/directory override variables are explicitly empty when unrequested. Verification-disable and TLS-secret-output controls are different: `NODE_TLS_REJECT_UNAUTHORIZED`, `GIT_SSL_NO_VERIFY`, and `SSLKEYLOGFILE` must be absent, because even an empty exported Boolean can change client behavior and a key-log path can disclose session secrets. Any image-provided occurrence fails before activation; the runner never synthesizes these variables. Certificate-bundle parsing uses an in-memory `SSLContext` that does not consult ambient default-context variables, so an inherited host `SSLKEYLOGFILE` cannot create a file before the live denial.

This proves an explicit, hash-pinned trust input and exact source-level mount/environment plan; it does not prove a container request or that the pinned OpenCode runtime excludes every compiled-in or system root. Replacing that runtime's built-in trust authority would be a separate security-authority change, so this patch does not guess at a flag or hide the uncertainty. Before the live denial can move, an operator-reviewed design must identify the pinned runtime's supported replacement-store mechanism and use an owned dual-chain fixture to show that the supplied runtime CA succeeds while a chain trusted only by the ambient store fails. The result must be read back from the actual OpenCode TLS path. Until then, exclusive runtime trust is blocked, not passed.

## Exclusive-store follow-up

Primary-source review now confirms that `SSL_CERT_FILE`, `SSL_CERT_DIR`, and `NODE_EXTRA_CA_CERTS` cannot make the pinned OpenCode 2.0.32 executable trust only the supplied CA. Bun 1.4.2 keeps bundled roots in its default store, and OpenCode bakes `--use-system-ca`. The existing `SSL_CERT_FILE` plan therefore remains dormant input plumbing, not a qualified trust boundary.

`T02-OPENCODE-EXCLUSIVE-TRUST-RESEARCH-20261021.md` records the source findings. `T02-OPENCODE-EXCLUSIVE-TRUST-CHECKS-20261021.md` defines a source-patched native HTTP design and a bounded owned check with three core arms plus ten pre-socket cases. `patches/opencode-v2.0.32-exclusive-ca.patch` and `smoke/check_opencode_exclusive_trust.py` are prepared inputs only. No patched image has been built or run, and no dual-chain result exists. The managed runner is intentionally unchanged, including its unconditional live denial.

## Responder-independent provider state

Provider ledger reads always return the tunnel and byte facts. `owned_responses` and `owned_health` are integers only when the owned offline responder exists. They are `null` in a future live run. Zero must not stand in for an unobserved live receiver count.

## Required offline proof

Run:

```sh
python3 evals/native-qualification/smoke/check_v2_live_preparation.py --output <new-private-output>
python3 evals/native-qualification/smoke/check_opencode_exclusive_trust.py --self-test
python3 evals/native-qualification/smoke/check_v2_cloud_manifest_layout.py
python3 evals/native-qualification/smoke/check_v2_cloud_owned_source.py --current-manifest
```

The preparation checker's public entrypoint uses a generated benign CA and a fake Docker executable. It must cover missing and partial pairs, offline-only misuse, invalid paths and bytes, digest failures, the valid-but-still-blocked case, exact trust mount/environment construction, unexpected trust override rejection, provider state with and without an owned responder, the dormant exclusive-checker boundary, and the exclusive receipt evaluator's pure self-test. The checker's core and all descendants run under `strace -f -e trace=network -e signal=none`; an unavailable observer or any network syscall fails without a receipt. The hidden core can emit only `status: unobserved`; only the observing parent can promote that object to `status: pass`. Its receipt may contain only named checks, fixed error codes, source hashes, synthetic CA size/hash/count, the Docker marker result, the zero-syscall observation method/count, and the retained live-gate code.

The owned managed workflow must still pass 64/64 with synthetic responses and zero provider calls after this source change. That result does not clear the owned-upstream, real-model, interruption/recovery, independent-review, hidden-case, false-proof, or adoption gates.

## Remaining external gates

The selected managed sidecar still needs an operator-approved reachable owned receiver. Native TLS through that route needs an owned receipt, not this source-only plan. Immediately before any later bounded request, recheck that the exact model is free and that all resource caps remain active. No source change may remove `cloud_live_route_not_qualified` until those receipts receive separate review and authority.

## Complexity and source-authority record

The concrete additions are one paired trust-input invariant, one responder-optional ledger projection, one standalone source checker, one explicit current-source manifest, and a later dormant exclusive-trust source patch/checker pair. They add no service, agent, or live entrypoint. The dual-chain checker is an explicit future runtime action, but neither the managed runner nor the source checker invokes that action. The offline checker does add a Linux test-tool dependency on `strace`: absence or lack of ptrace capability blocks the receipt rather than degrading observation, so non-Linux and restricted executors cannot produce this evidence. The historical ZIP-root manifest remains the default authority; the new manifest is selected only by `--current-manifest`, so old readers keep their prior fail-closed behavior and correctly report the post-transfer bytes as drift.

The current manifest is necessary because changing the authenticated root manifest would rewrite the historical transfer while leaving it unable to pin the post-transfer bytes. Its stable path avoids a new dated selection branch for every qualification. The checker and this document are loaded only when the T02 preparation is invoked, so they do not increase the orchestrator's always-loaded context. The two standalone checks retain their short CA-generation commands rather than adding a shared test-helper module and another source pin.

The new failure modes are an invalid explicit manifest selection, CA validation/snapshot refusal, and nullable owned-responder counters; the offline cases cover each before live execution. The dormant snapshot and trust-plan branch is the requested prepared interface while execution remains forbidden, not a claim of runtime proof. If the source is adopted into a canonical repository manifest, remove the explicit current-manifest option and this temporary manifest together. If it is not adopted, delete them and the dormant live trust helpers without changing the historical transfer reader.
