# Fresh cloud amd64 Kanboard candidate checks

21 October 2026. This is a bounded, owned, no-provider qualification of one
fresh `linux/amd64` PHP runtime candidate for the existing two-arm T01
Kanboard observer. It does not run OpenCode, call a provider or model, create a
researcher bundle, engage a target, use external credentials, or qualify any
route beyond this ordinary synthetic application observer.

## Immutable starting material

Fail before the build if the isolated branch did not start at PR #175 commit
`9c0c0e3f0f7d25fece945a564c8c991a5368d8b9`, or if any of these preserved
inputs differs:

- `smoke/check_v2_php_parity_amd64.py` SHA-256
  `bf983ccc93fac42033c7785fab35aa10e263c9035ee8680a3896c183df281927`;
- `smoke/check_v2_php_parity_amd64_test.py` SHA-256
  `3bd6542d300de103a8f142655c576de74c6f4665b97a5ee8c57a161b30235c18`;
- `observer_case.py` SHA-256
  `72273bfd4e1c1aa9f7f53279e525ec1c74c2669324fa62f1b6b22abf65d596bf`;
- `observer-evidence-final/observer-results.json` SHA-256
  `9db3bc220484a7a786729847f3c8fa8cc1d364a74b1e4a81d2bb78f80dc924fa`;
- `RESEARCHER-BRIEF.md` SHA-256
  `8f2b5604870cf86719ae94ac180cb6cbe0c5c12cdd2356bc90f4104bb7179a5a`;
- `Dockerfile.opencode-kanboard-runtime` SHA-256
  `7a1ab9b257fb36a216fc1baafabc757436d0a15ffcb9498b6fbe697da3a9bf4b`;
  and
- every file in the immutable blocked receipt
  `t02-evidence/opencode-v2-php-parity-amd64-20261021a/`.

The earlier blocked image IDs
`sha256:9ef722322521322a1288a18427ba5bf6ce1479085c97e0ac821982eec4f01769`
and
`sha256:d0b96c08541486079634fd70a0ffb221c32b07a2a04a1a2ab7d041912a7c9a91`
are historical evidence, not candidates for this run.

## Pre-build provenance and baseline

Fail before the build unless all of the following are frozen outside the
runner:

1. The complete Docker baseline includes container IDs, image IDs with tag
   mappings, volumes, networks, builder identity, BuildKit version, and cache
   record IDs. The task tag
   `t02-kanboard-runtime:amd64-parity-20261021b` must be absent.
2. The Dockerfile's embedded default base is
   `ghcr.io/anomalyco/opencode@sha256:2fc782d346b0670c43378557cf8a2a9926a1f3d28e596180e7b21a0736d8cb7d`.
   The effective build argument is the distinct, previously published pin
   `ghcr.io/anomalyco/opencode@sha256:85986f556e985e377bd24cd68a5ccfbc647bb49e591194edda8a0e4542303319`.
   Record both so the override is explicit.
3. The existing managed CA bundle is read from
   `/etc/ssl/certs/ca-certificates.crt`, has SHA-256
   `43e169bf3454bc74c12d3df8c1403f0b4e7da135bf5959f8ab31eb634896bf73`
   and size 230249 bytes, and is supplied only as BuildKit secret `proxy_ca`
   at `/etc/apk/ca.pem`. Do not copy its bytes into evidence, change system
   trust, or record proxy values.

## Candidate build and registration

Use one supported `docker buildx build --platform linux/amd64 --load` with the
effective base above, the managed CA secret, the exact Dockerfile, build
context `evals/native-qualification`, and the fresh task tag. Preserve a
private bounded diagnostic if it fails.

After a successful build, perform metadata-only image inspection. Before any
`docker run`, archive retrieval, extraction, or application arm:

1. Require the fresh tag to resolve locally to one new immutable image ID on
   `linux/amd64`. The ID must differ from both historical IDs above. Do not
   pull, retag, or silently substitute an image.
2. Require the Dockerfile and managed CA hashes to remain unchanged.
3. Write a new candidate input receipt with the exact image ID and tag,
   platform, effective and default base pins, Dockerfile hash, CA provenance,
   build metadata, archive pins, source pins, pre-build baseline digest, zero
   image/container executions, and zero arms started.
4. Hash that receipt. A small additive adapter must verify the exact receipt
   hash, its narrow schema, current source/CA/Dockerfile hashes, and current
   tag-to-ID/platform mapping before it can delegate to the preserved runner.

The candidate receipt may report that build-and-registration checks passed;
it must not claim PHP/module or application qualification before execution.

## Archive and execution admission

Before the first arm, retrieve both archives only from their public pinned
codeload URLs into a new private cache. Verify both byte hashes before either
archive is extracted or any application container starts:

- vulnerable commit `f0f7d27007f5a788f14416c548421efd740b7bce`, SHA-256
  `3f24269475bf00137d4b0d957d97a2567a5249101dad89067a49d609f4df2edf`;
- fixed commit `a98bc5f855d4e7e47eb3425a6c7da6c6cc6748a3`, SHA-256
  `44db3df81a25bbd56c768c8b3180a1f05879e2c7fbaa6ac73707e7f3e9098f56`.

The preserved runner must consume those verified bytes and recheck every
archive and extracted file through `observer_case.prepare_source()`. Every
Docker image execution, including PHP version/module probes, must carry
`--pull=never` and use the registered immutable image ID. A wrong receipt,
image ID, tag, platform, base, Dockerfile, CA hash, archive, or source pin must
stop before the dependent action.

Only the existing ordinary observer may run. Both arms must create two
synthetic users and a private project, prove Alice's authorized project and
swimlane reads, and prove Bob's project denial. Bob must read the exact
swimlane metadata on the vulnerable arm and receive the expected access denial
on the fixed arm. Wrong objects, unrelated failures, missing controls, or a
semantic mismatch with the pinned T01 result fail qualification.

## Evidence and cleanup

Keep raw output private. Public derivatives must remove container IDs,
ephemeral ports, private paths, generated passwords, Authorization values,
cookies, tokens, API keys, credentials, proxy values, CA bytes, and raw build
logs. The public verifier must fail closed on missing or extra receipt keys,
pin complete command bytes, exercise an executable wrong-image negative case,
and mutate image, archive, cleanup, and secret-bearing fields.

Stop only exact arm container IDs. Require closed loopback ports and removal
of disposable run directories and databases. After evidence is read, remove
only the recorded fresh tag/image and the cache records created after the
outer baseline; never use a global prune. Final container IDs, image IDs and
tag mappings, volumes, networks, and cache records must equal the pre-build
baseline. Preserve a cleanup failure and do not claim parity if exact
restoration cannot be established.

The historical blocked command remains reproduction evidence only. The new
build command must refuse an already present task tag; the new replay command
must inspect an explicitly registered image before invoking Python and must
never build or retag.
