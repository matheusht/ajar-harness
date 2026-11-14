# Hosted model image build and readback — failure scenarios

These acceptance cases are written before the fixture implementation. The next
workflow will use the real context installer and Docker on an explicitly selected,
disposable native Linux host. It does not start a model, contact a provider or
exercise research. The base image must already be installed by its registry
digest. Native release files are acquired only by an explicit CLI invocation.

Required observations:

- A non-Linux host, wrong native architecture, mutable base reference, absent
  daemon or mismatched base platform fails before native-asset acquisition.
  Inherited base OnBuild hooks, volumes, healthchecks and ports are refused at
  the same boundary, before Docker can run a build hook.
- Each successful installer receipt points to its retained canonical host
  executable and records the exact runtime/helper manifest. Existing destination
  data is never replaced. The caller owns the new context directory after the
  fixture ends; it remains available for signed-profile input validation.
- Building uses the digest-pinned base, the prepared context, disabled build
  networking and a fresh ownership nonce. The resulting local image ID is read
  from Docker and bound to that nonce and the expected platform. No build-time
  command or native binary is executed.
- The image has inert defaults, no inherited volumes, healthcheck, OnBuild hook,
  exposed port or unexpected entrypoint. An owned probe is created from that
  exact image with no networking, a read-only filesystem, bounded resources,
  dropped capabilities and nonroot identity. The probe stays stopped.
- Streaming readback of `/runtime` from the stopped probe matches every installer
  manifest path, byte count, digest and mode. Directories have mode `0755`; all
  files and directories are owned by UID/GID 0. A changed/missing/extra file,
  link, special entry or wrong permission/owner fails. No archive is extracted
  onto the host and readback output is bounded by the expected manifest.
- A failure during acquisition, build, create or readback retains a failed result
  and reconciles only the fixture's observed or nonce-discovered resources.
  A daemon, image, probe or label mismatch remains unresolved; it never grants
  permission to delete another resource. Partial or ambiguous creation is not
  reported clean merely because a subprocess failed. A nonzero mutating client
  exit or timeout keeps completion unresolved even after observed resources have
  been removed; a lost client connection can outlive its response channel.
- Cleanup removes only the exact owned probe and newly built image. It verifies
  their absence and preserves the base image and preexisting images/containers.
  It retains the installer context/executable/receipt and result. Interrupted
  or unresolved cleanup records enough exact identity for operator inspection.
- The standalone CLI always attempts cleanup. A runtime E2E caller may reuse the
  returned image and retained executable, then call the same cleanup function
  after its own runtime resources are settled.

Local checks will cover syntax, CLI refusal on unsupported hosts and fixtures for
the readback/recovery failure paths. They do not substitute for the hosted image
build. At this point no actual build/readback result has been recorded.

## Repeat the hosted workflow

The fixture now implements those checks through
[`check_model_image_docker_e2e.py`](../../smoke/check_model_image_docker_e2e.py).
Use Python 3.11+, Docker and enough disk on a disposable native Linux host. Install
the reviewed base by digest first; the script does not pull a base implicitly.
It invokes the existing installer to acquire the selected pinned native assets,
then builds with `--pull=false --network none` and verifies a stopped container.
The integrated checkout must contain the model-owner bootstrap helper.

```sh
python3 evals/native-qualification/smoke/check_model_image_docker_e2e.py \
  --runtime codex --platform linux/amd64 \
  --base-image python@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39 \
  --endpoint unix:///var/run/docker.sock \
  --directory /tmp/oslit-model-codex \
  --output /tmp/oslit-model-codex.json
```

Use `--runtime omp` with a distinct new directory and result for OMP. Expected:
exit zero, `status: passed`, complete runtime readback, `cleanup.status: clean`,
and retained `context/runtime/bin/model` plus `context-receipt.json`. A failed
or interrupted operation records available identities and cleanup status. An
unresolved result requires inspection of those identities; it is not permission
to remove a container/image with a mismatched daemon, ID or ownership label.
Docker build cache is outside this fixture's resource ownership and is not pruned.

For a native runtime check in the same process, import `prepare_image`,
`verify_image` and `cleanup_image` from the script. `prepare_image` takes keyword
arguments `runtime`, `platform`, `base_image`, `endpoint`, `directory` and `result`.
It returns an `ImageFixture` with `image_id`, `daemon_id`, `directory` and
`context_receipt`. The executable pin is
`fixture.context_receipt['profile_fields']['executable']`. Call `verify_image`
before using the image; after the caller's native resources have settled, call
`cleanup_image(fixture, result)` in a `finally` block. Preparation failures attempt
their own exact cleanup before propagating. This reuse does not turn image
readback into proof of native startup or credential containment.

## Local engineering evidence

The companion [public-CLI fixture](../../smoke/check_model_image_docker_fixture_e2e.py)
uses synthetic Docker and installer subprocesses in an isolated temporary tree.
Its initial run failed because the driver was absent ([before](before.json)).
A later pair of pre-fix faults showed a falsely clean result for a lost build
response/tag and an image-ID mismatch ([identity-before](identity-before.json)).
Nonce discovery now cleans the first and leaves the mismatch unresolved. The
root review also identified pre-build OnBuild admission and uncertain mutation
response gaps. Four inherited-base cases and failed-client expectations failed
before correction ([admission-before](admission-before.json)); the final
[29 cases](after.json) pass. Their subprocesses do not contact a real Docker
daemon, download a release binary or start native code.

A separate [direct invocation on the development Mac](nonlinux-refusal.json)
failed its first admission check, with no Docker command or acquisition directory.
Source and result hashes are in the [manifest](manifest.json). Repeat the local
fault check without Docker or network access:

```sh
python3 evals/native-qualification/smoke/check_model_image_docker_fixture_e2e.py \
  --output /tmp/model-image-driver-fixture.json
```

This checkpoint contains no actual Linux build/readback result. Actual image
packaging, native model behavior, live provider operation and research acceptance
remain separate evidence.
