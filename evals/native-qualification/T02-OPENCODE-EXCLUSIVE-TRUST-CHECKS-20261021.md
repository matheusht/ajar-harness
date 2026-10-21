# OpenCode exclusive trust preparation

This is a source and test contract for one missing T02 prerequisite. It does not qualify a runtime, authorize Docker execution, authorize inference, or change the `cloud_live_route_not_qualified` stop. No existing image is described as exclusive-trust capable.

## Runtime fact pattern

The candidate is OpenCode `v2.0.32` at upstream commit `843a6c514e606b436a7fe713422ace0a93ad3d61`, built with Bun 1.4.2. The OpenCode executable bakes Bun's `--use-system-ca` option. On Linux, `SSL_CERT_FILE`, `SSL_CERT_DIR`, and `NODE_EXTRA_CA_CERTS` add or redirect parts of the default trust construction, but they do not remove Bun's bundled roots. They cannot prove a supplied-only trust boundary.

OpenCode 2.0.32 rewrites the selected `opencode/deepseek-v4.1-flash-free` model from `@ai-sdk/openai-compatible` to its native `@opencode/ai/providers/openai-compatible` route. An `aisdk` plugin hook is therefore not the transport boundary for this model. The source seam used by native HTTP inference is `FetchHttpClient.RequestInit` in `packages/core/src/effect/app-node-platform.ts`.

The primary-source analysis is in `T02-OPENCODE-EXCLUSIVE-TRUST-RESEARCH-20261021.md`. The candidate source change is `patches/opencode-v2.0.32-exclusive-ca.patch`.

## Candidate replacement-store design

Apply the patch only to the exact upstream commit above and build a new image. Each execution of the patched native HTTP response effect requires both `OPENCODE_EXCLUSIVE_CA_FILE=/fixture/runtime-ca.pem` and a lowercase `OPENCODE_EXCLUSIVE_CA_SHA256`. Validation is deliberately deferred from request-executor layer acquisition to request execution: the persistent OpenCode server can start and expose its authoritative provider/model/config readback before an invalid input is exercised through that same server. At execution, the patch opens the fixed path once without following a symlink, bounds and reads that descriptor, checks stable file metadata and the required digest, and supplies the bytes as Bun `fetch` option `tls.ca` with certificate verification enabled. It emits only fixed `OPENCODE_EXCLUSIVE_CA_REJECT:<code>` markers for validation failures. A version-only command and successful server startup do not execute this effect and are not fail-closed probes.

Bun documents and implements request-level `tls.ca` as a replacement CA set. This is the required mechanism. It is not an environment alias for the additive default store.

The host-side runner must retain its existing certificate-only parsing, exact SHA-256 match, stable-descriptor read, private mode-0600 snapshot, and read-only mount checks. The runtime patch is not a reason to weaken any of those controls.

The build is not complete until a receipt binds all of these values:

- upstream commit `843a6c514e606b436a7fe713422ace0a93ad3d61`;
- the patch SHA-256;
- source/build binding to Bun 1.4.2 and runtime readback of OpenCode `v2.0.32`;
- Linux/amd64 image ID in `sha256:<64 lowercase hex>` form;
- the build inputs and the absence of CA bytes, private keys, credentials, and proxy values from image layers.

No tag alone is sufficient. The dual-chain checker accepts separate exact local image IDs for the unpatched ambient control and patched candidate. It never pulls or builds an image.

## Prewritten owned check

`smoke/check_opencode_exclusive_trust.py` is a dormant, confirmation-gated checker. A later operator-approved run must use a new private output directory and two already built exact images. The checker creates two one-run CAs with distinct subjects and serials. Each leaf has `DNS:opencode.ai` and `serverAuth`, verifies under its own root, and fails under the other root.

It then runs three core arms in fresh OpenCode containers against an owned TLS/SSE responder on a labeled internal Docker bridge:

| Arm | Runtime | Ambient store | Replacement input | Server chain | Required result |
| --- | --- | --- | --- | --- | --- |
| Ambient control | Exact unpatched control image | CA A | absent | CA A | OpenCode succeeds and the owned responder records HTTP |
| Supplied positive | Exact patched candidate image | CA A | CA B | CA B | OpenCode succeeds and the owned responder records HTTP |
| Exclusivity negative | Exact patched candidate image | CA A | CA B | CA A | OpenCode fails TLS; the responder records TCP and server-side TLS failure, with zero HTTP requests |

The positive and negative arms use identical ambient and replacement trust inputs, including CA B's required digest. At fixture creation, immediately before and after each container creation, after each dispatch, and after all arms, the checker reopens all active host CA, leaf, and leaf-key paths with `O_NOFOLLOW`, requires regular mode-0600 bounded files, and compares stable descriptor identities and hashes with the initial fixture. After each core container starts, it separately hashes CA A—and CA B in candidate containers—from the running container's mount namespace before and after dispatch. Each core row records those mounted CA hashes and a stable-before/after result; the evaluator requires both candidate rows to match each other and the initial fixture. Every responder starts with an all-zero snapshot, must remain at zero through native readback, and records only the post-readback dispatch delta as result evidence. A nonsecret per-arm header is fixed in the mounted config, verified in authoritative provider readback, and required on every accepted positive HTTP request. Pre-baseline traffic or an unmarked request cannot satisfy an arm. The tested server chain is the only security-relevant trust-input difference; each arm still gets a fresh container and workspace. Both retain CA A through the ambient `SSL_CERT_FILE` path while CA B is supplied through the paired exclusive path and digest variables. This makes acceptance of the negative CA A chain a test failure, not an ambiguous default-store result. Ten additional fresh candidate containers exercise the pre-socket cases below, so a complete bounded run creates 13 containers in total.

Every arm uses its declared exact image ID, a fresh HOME/XDG/project tree, no provider credential, no inherited proxy, no TLS disable or key-log variable, a read-only root, dropped capabilities, `no-new-privileges`, equal memory and memory-plus-swap limits, bounded PIDs/CPU, disabled restart, disabled Docker logging, and the internal bridge. Container inspection must read back each of those limits and settings before start. Both images must read back as Linux/amd64 OpenCode 2.0.32. `opencode.ai` resolves only to the owned bridge endpoint. Before dispatch, the sole matching provider and model must both read back the owned base URL; the provider must select HTTP and the effective model must have no transport override. Model-catalog fetches are disabled. The response is synthetic and local; no external or live provider/model service is called.

Package, effective HTTP transport, and dispatch must resolve in one loopback-only OpenCode server process per core arm. OpenCode requires a server lease value even on loopback. Each container generates its own value inside the foreground `opencode serve` process boundary; the checker keeps it only in the bounded server and client process environments, excludes it from Docker configuration, arguments, files, logs, and receipts, disables core dumps, and destroys it through exact container cleanup. This is OpenCode's internal `default` server-process mode, not its persistent managed-service mode. Supplying the normal-mode confirmation does not by itself authorize that runtime action; the future operator approval must explicitly cover all 13 ephemeral local leases as well as Docker and the owned sockets.

## Result requirements

A passing receipt must include only public source/image hashes, public certificate hashes and serials, sanitized arm return codes, TCP/TLS/HTTP counts, named checks, exact cleanup outcomes, and the non-secret run label nonce plus predetermined resource names needed for recovery. It must not include PEM bodies, private keys, private-key hashes, raw request bodies, raw process logs, environment dumps, tokens, credentials, or unrelated host details.

The negative result needs all of the following:

- a nonzero OpenCode exit;
- at least one owned TCP connection;
- at least one server-side TLS handshake failure;
- zero parsed HTTP requests;
- an all-zero pre-dispatch baseline and counts drawn only from the dispatch delta;
- the same replacement and ambient inputs as the supplied-positive arm.

Client stderr alone cannot prove exclusivity. A positive response alone cannot prove ambient roots were excluded.

Candidate pre-socket cases must distinguish both variables absent, only the path variable absent, only the digest variable absent, malformed digest, wrong path, fixed path with no mount, unreadable file, empty file, oversized file, and valid CA bytes with the wrong digest. For every case, the candidate server must first start and prove the exact native package, HTTP transport, selected base URL, and mounted source document. The checker then dispatches through that same server and requires exit status 1 plus one bounded structured JSON error carrying the exact expected fixed rejection marker and a nonempty session ID. After the rejection, the same container and server must remain running, readiness must succeed, and the authoritative native readback must be byte-for-byte equivalent as sanitized facts. The owned provider endpoint must see zero TCP connections. A server-startup exit, generic client nonzero result, unstructured diagnostic, wrong marker, or marker without the post-failure liveness/readback proof cannot pass. Malformed certificate, mixed private-key input, and host hash mismatch remain host-preparation failures and must continue to stop before output, Docker, or any network syscall.

The runtime patch also has fixed `read_failed`, `changed`, and `close_failed` branches. The bounded checker does not manufacture a concurrent file-mutation race or descriptor failure. Those branches receive source review only, and a future receipt must not claim that it dynamically exercised them.

The checker must remove each owned container and network by exact ID after verifying its run label. Post-cleanup inspection proves absence only when stdout returns no object—whitespace-empty or the exact parsed empty list—plus an exact one-line Docker "no such" diagnostic naming that ID, followed by a successful parsed Docker-engine liveness read with empty stderr. Label-list absence likewise requires successful reads with both empty stdout and empty stderr; warnings are not absence. A generic nonzero inspection is not absence. Before the first create, the checker durably writes its non-secret nonce, all predetermined resource names, and the private temporary workspace path needed for recovery. It durably journals every create as unconfirmed before invoking Docker. Only after a syntactically valid exact ID has entered the owned-resource set does it durably replace that journal state with the exact-ID confirmation; final cleanup requires a one-to-one match between confirmed journal entries and owned resources. A timeout, interrupt, exception, nonzero result, malformed result, or interrupted confirmation therefore leaves an uncertain mutation; label reconciliation still attempts exact-ID cleanup, but that run cannot pass or delete the temporary CA/private-key workspace because a late daemon completion may remain possible. Any uncertain create or unresolved inspection, ownership, removal, or engine-liveness result leaves the temporary path in the sanitized receipt and requires later operator recovery by the recorded names and nonce. A later exact-ID retry may resolve the latter cleanup results, but never an uncertain create in the same run. Pass status also requires an explicitly completed positive verdict; cleanup success cannot promote an interrupted or otherwise incomplete run. A successful run removes the workspace, proves `lstat` absence, fsyncs the workspace parent directory, proves absence again, and only then omits the recovery path from its durable final receipt.

## Source-only checks allowed now

Before any runtime approval, reviewers may perform only source operations:

```sh
git -C <exact-opencode-v2.0.32-source> apply --check \
  <redteam-harness>/evals/native-qualification/patches/opencode-v2.0.32-exclusive-ca.patch
python3 -m py_compile \
  evals/native-qualification/smoke/check_opencode_exclusive_trust.py
python3 evals/native-qualification/smoke/check_opencode_exclusive_trust.py --self-test
python3 evals/native-qualification/smoke/check_v2_live_preparation.py
```

The self-test exercises only pure receipt, cleanup-diagnostic, engine-result, and uncertain-mutation decision logic with in-memory fixtures. It must not inspect Docker, create a socket, or make a network syscall. The live-preparation checker must continue to observe zero network syscalls and no Docker invocation.

## Holds after a future pass

This check covers only the native HTTP path for the exact selected model and image. It does not cover AI SDK packages, a plugin-supplied custom fetch, WebSocket transport, MCP, web search, update traffic, provider availability, cost, shared allowance, recovery, target observation, or the hidden case.

Do not integrate the patched image or replacement variable into the live runner until the exact build and dual-chain receipts have independent review and an operator adopts them. Even after adoption, the live denial remains until the separate owned-ingress, provider-free-state, allowance, recovery, review, and issue dependencies are satisfied. Issue #165 remains no-go, and issues #166 through #171 remain open until adoption evidence exists.
