# Cloud amd64 Kanboard PHP 8.4.27 current-runtime checks

21 October 2026. This is a separate, bounded qualification of one newly
built `linux/amd64` PHP 8.4.27 image against the existing owned two-arm T01
Kanboard observer. It compares application semantics with the historical T01
controls. It does **not** establish byte-identical PHP 8.4.26 parity, repair
the sealed 8.4.26 build, run OpenCode, call a provider or model, create a
researcher bundle, use credentials, or contact an engagement target.

## Immutable starting material

Fail before the build unless the isolated branch starts at the sealed PR #179
head `8e7b730edce6480eec3c92fc10a21a7cb74147a9`, the worktree was clean when
the outer Docker baseline was captured, and each historical input has its
published hash:

- `smoke/check_v2_php_parity_amd64.py`:
  `bf983ccc93fac42033c7785fab35aa10e263c9035ee8680a3896c183df281927`;
- `smoke/check_v2_php_parity_amd64_test.py`:
  `3bd6542d300de103a8f142655c576de74c6f4665b97a5ee8c57a161b30235c18`;
- `observer_case.py`:
  `72273bfd4e1c1aa9f7f53279e525ec1c74c2669324fa62f1b6b22abf65d596bf`;
- `observer-evidence-final/observer-results.json`:
  `9db3bc220484a7a786729847f3c8fa8cc1d364a74b1e4a81d2bb78f80dc924fa`;
- `RESEARCHER-BRIEF.md`:
  `8f2b5604870cf86719ae94ac180cb6cbe0c5c12cdd2356bc90f4104bb7179a5a`;
  and
- every byte in the sealed PHP 8.4.26 blocked receipt
  `t02-evidence/opencode-v2-php-parity-amd64-fresh-20261021b/`.

Do not modify the historical Dockerfile, runner, tests, observer, or either
blocked receipt. This qualification uses an additive adapter and an additive
Dockerfile only.

## Frozen source, package and trust provenance

Fail before the build unless all of these conditions hold:

1. `Dockerfile.opencode-kanboard-runtime-php8427` uses the unoverrideable
   direct base
   `ghcr.io/anomalyco/opencode@sha256:85986f556e985e377bd24cd68a5ccfbc647bb49e591194edda8a0e4542303319`.
   No build argument may replace it.
2. Every explicitly requested package is pinned to exactly `8.4.27-r0`:
   `php84`, `php84-ctype`, `php84-dom`, `php84-gd`, `php84-iconv`,
   `php84-mbstring`, `php84-openssl`, `php84-pdo_sqlite`, `php84-session`,
   `php84-simplexml`, and `php84-xml`.
3. The existing managed CA file `/etc/ssl/certs/ca-certificates.crt` has
   SHA-256
   `43e169bf3454bc74c12d3df8c1403f0b4e7da135bf5959f8ab31eb634896bf73`
   and size 230249 bytes. Supply it only as BuildKit secret `proxy_ca` at
   `/etc/apk/ca.pem`. Do not record its bytes or proxy values, add it to the
   image, or change persistent system trust.
4. The source manifest, Dockerfile, checks, adapter and tests agree on all
   fixed paths, hashes, package pins, archive pins and claim limits.

The live Alpine repository is not an archival package source. Success
qualifies only the resulting immutable image ID. If it no longer serves the
exact package revision, stop with a blocked receipt rather than relaxing or
mixing pins.

## Pre-build baseline and candidate registration

Before the one permitted build, freeze containers, image IDs and tag
mappings, volumes, networks, builder and BuildKit identity, cache record IDs
and bytes. The fresh tag
`t02-kanboard-runtime:amd64-php8427-20261021c` must be absent. Keep the private
baseline digest in the public input receipt.

Build once through the supported `docker buildx build --platform linux/amd64
--load` route with the exact new Dockerfile and context, the fresh tag and the
managed CA secret. Do not pass a base override. A build failure stops all
dependent work.

After a successful build, use metadata-only inspection. Before the first
`docker run`, archive retrieval or arm:

1. require the fresh tag to resolve to one new immutable `linux/amd64` image
   ID, different from historical IDs and absent from the baseline;
2. require all frozen source and CA hashes to remain unchanged; and
3. write and hash a narrow candidate receipt recording exact build inputs,
   image identity, platform, baseline digest, zero image executions, zero
   retrieved archives and zero arms. Its `status: pass` is scoped only to
   build and registration; application qualification remains `not_run`.

No pull, retag, silent substitution or caller-selected receipt/image is
allowed.

## Runtime and archive admission

The first execution must use the registered image ID with `--pull=never
--network none` and inspect installed packages. Require every explicitly
requested package above and require every installed package whose name starts
with `php84` to end in `-8.4.27-r0`. Any missing package or mixed revision
fails. Record the exact package listing and PHP/module checks in a distinct
runtime-admission receipt; do not backfill them into the pre-execution
candidate receipt.

Before either application arm starts, retrieve both archives into bounded
private memory or cache, then verify both byte hashes:

- vulnerable commit `f0f7d27007f5a788f14416c548421efd740b7bce`,
  SHA-256
  `3f24269475bf00137d4b0d957d97a2567a5249101dad89067a49d609f4df2edf`;
- fixed commit `a98bc5f855d4e7e47eb3425a6c7da6c6cc6748a3`,
  SHA-256
  `44db3df81a25bbd56c768c8b3180a1f05879e2c7fbaa6ac73707e7f3e9098f56`.

An archive failure means zero arms. The preserved observer must consume the
verified bytes and recheck every extracted file. Every image execution,
including PHP version/module probes and both servers, must use the registered
immutable image ID with explicit `--pull=never`. Reject any unknown Docker
run shape.

## Application outcome and historical comparison

Only the existing ordinary owned loopback observer may run. On both arms,
create two synthetic users and one private project, prove Alice's authorized
project and swimlane reads, and prove Bob's project denial. Bob must receive
the exact swimlane metadata on the vulnerable arm and the expected access
denial on the fixed arm. Wrong objects, unrelated errors, missing controls or
changed source pins fail.

Compare only the historical semantic fields: release, loopback boundary,
synthetic object identities and controls, differentiating result, commit and
archive hash. Require PHP 8.4.27 and the registered current image ID on both
new arms. Do not normalize the runtime to 8.4.26 or claim byte-identical
runtime parity.

## Evidence and exact cleanup

Keep raw output and build logs private. Public derivatives must remove
container IDs, ephemeral ports, private paths, generated passwords,
Authorization values, cookies, tokens, API keys, credentials, proxy values,
CA bytes and raw build logs. Public verification must hash raw bytes before
decoding, reject CRLF/byte substitutions, enforce narrow receipt schemas and
exercise negative cases for the image, runtime, archives, missing arms,
cleanup, secrets and false PHP 8.4.26 parity claims.

Stop only exact task container IDs. Require closed loopback ports and removed
run directories/databases. After evidence is read, remove only the recorded
fresh tag/image and cache records created after the outer baseline, retrying a
parent cache record only after its task-created children. Never use a global
prune. Final containers, image IDs/tag mappings, volumes, networks, builder
identity and cache record IDs/bytes must exactly equal the pre-build baseline.
If exact restoration cannot be established, preserve the failure and do not
claim qualification.
