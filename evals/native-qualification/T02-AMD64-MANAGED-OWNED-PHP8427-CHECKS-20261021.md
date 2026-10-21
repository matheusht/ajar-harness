# T02 cloud amd64 managed-owned PHP 8.4.27 rehearsal checks

These checks govern one bounded, offline, owned-response rehearsal of the
integrated T02 runner from draft PR #180. They are frozen before any image
build or container execution. A failed prerequisite stops dependent work and
is recorded as a blocked result; it is never converted into a weaker run.

## Scope and immutable inputs

- The integration source is exactly
  `b8f0453575740cb1482dc716fa1807c195459f58`, the published head of PR #180.
- The image source is imported without semantic change from candidate PR #182
  head `adf6692474c81771e7e6fa2bc19e2a8dd067eb30`. Its Dockerfile SHA-256 is
  `be4948ac34c02f1cf84560f86874f07dc4d6c4b4efc8b1141956d2bf16f7497e`
  and its direct base is
  `ghcr.io/anomalyco/opencode@sha256:85986f556e985e377bd24cd68a5ccfbc647bb49e591194edda8a0e4542303319`.
- Every requested `php84*` package is pinned to `8.4.27-r0`; every installed
  `php84*` package must report that same revision. This is a current-runtime
  rehearsal, not byte-identical PHP 8.4.26 parity.
- The managed build CA is a regular, non-group/world-writable file supplied
  only as BuildKit secret `proxy_ca`; its bytes, proxy values, and build logs
  are not public evidence. The expected CA SHA-256 is
  `43e169bf3454bc74c12d3df8c1403f0b4e7da135bf5959f8ab31eb634896bf73`.
- The amd64 relay must be a regular executable ELF x86-64 file at the pinned
  repository path with SHA-256
  `33ef7484c2a2415915af399689e91e9efee8000b2c685a6b2b72eb4eddedf895`.
- The PR #180 current source manifest, managed runner, owned fixture/config,
  reviewer-packet controls, exact-set stop owner, and Docker runtime must pass
  their no-Docker source checks before the build.

## Pre-build failures

Stop before building if any immutable input is missing or mismatched, the
selected environment is not the verified local `linux/amd64` Docker engine,
the exact task tag already exists, a requested subnet overlaps an existing
Docker network, the managed CA fails its file/hash checks, or the source tests
do not prove that live admission still fails before output and Docker.

Capture the complete pre-build Docker baseline before the build: container
IDs, image IDs and tag mappings, volume IDs, network identity/configuration,
builder identity, and BuildKit cache record IDs/bytes. Do not remove or alter
pre-existing resources.

## Build and admission failures

- Perform at most one `linux/amd64` `docker buildx build --load` using the
  frozen Dockerfile, direct base digest, and managed CA secret. Do not pass a
  base override.
- Stop before any candidate container if the build fails, the new tag does
  not resolve to exactly one newly registered immutable image ID, its platform
  is not `linux/amd64`, the base/diff provenance is inconsistent, OpenCode is
  not `v2.0.32`, PHP is not 8.4.27, any of `sh`, `php`, `wget`, or `opencode`
  is unavailable, a requested module is absent, the image supplies an
  unexpected critical proxy/trust/credential environment value, or any
  installed `php84*` package has a revision other than `8.4.27-r0`.
- Register the immutable image ID and build/source pins in a receipt before
  the first image execution. Every subsequent image reference must be that ID
  with `--pull=never`; no tag substitution or pull is allowed.

## Managed rehearsal failures

- Invoke `opencode_v2_managed_owned.py` only without `--live-free` and without
  live runtime-CA arguments. The provider/model endpoint is the runner's
  ephemeral owned TLS responder; no external provider, model, target,
  engagement, credential, or researcher bundle is permitted.
- Supply the exact admitted `linux/amd64` image ID, pinned amd64 relay and
  hash, two non-overlapping owned private subnets, the selected gateway/peer,
  and the already approved managed proxy environment name. Do not change host
  trust, managed network policy, credentials, permissions, or persistent
  security settings.
- The run fails unless all managed checks pass, including exact source-copy
  pins, native config/store readback, fixed CONNECT authority, wrong-peer and
  wrong-capability denial, owned TLS trust, first-run edit/check, stopped
  first producer, frozen read-only reviewer packet, fresh independent
  reviewer, exact-session resume, shared allowance/cap denial, ordered stop,
  exact producer stop proof, effect retention, and task-resource cleanup.
- `result.json` must classify the route as owned offline synthetic response,
  not live/provider qualification. Any provider/model/target contact, live
  admission, unexpected network route, missing source pin, failed check,
  uncertain stop, incomplete cleanup, or sensitive public material fails the
  rehearsal.

## Outer cleanup and public evidence

After the managed runner terminates, remove only the exact task image/tag and
the BuildKit cache records proven newly created by this attempt, child before
parent. Never use a global prune. Re-read the complete Docker state and require
byte-equivalent baseline identity for containers, images/tags, volumes,
networks, builder, and cache IDs/bytes. If exact cache removal is unsupported,
record the unresolved records and fail cleanup rather than widening scope.

Publish only sanitized receipts: frozen inputs, pre-execution candidate
registration, redacted repeatable build/run commands, bounded result summary,
source hashes, exact cleanup comparison, and an offline verifier. Do not
publish raw logs, proxy values, credentials, CA bytes, capability material,
private paths, container IDs, ports, disposable databases, or unredacted
native transcripts.

Passing this rehearsal qualifies only the integrated owned-response workflow
on the recorded immutable image. It does not qualify a provider/model route,
live TLS, hosted CI, a target, default adoption, #165, or any retirement work.
