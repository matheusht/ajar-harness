# T02 cloud source transfer — 20 October 2026

This is a credential-free snapshot of the current managed V2 CONNECT candidate,
its prewritten checks, the pinned T05 controls, and a Linux/amd64 relay
cross-build. `source.zip` contains exactly the repository paths listed in
`SOURCE-MANIFEST.json`, plus that manifest. The allowlist includes
`READINESS-STOP-CHECKS.md` and `ORPHAN-REAP-CHECKS.md`, which document the
transport checker failures, and the no-Docker cloud source/teardown and
manifest-layout checkers with their prewritten failure conditions.
`TRANSFER-REPORT.json` records the
ZIP and manifest hashes. Verify both before extracting into a private checkout.
The shared local worktree is mostly untracked; cloning its Git HEAD alone will
not reproduce this candidate.

The bundled Dockerfile defaults to the reviewed OpenCode 2.0.32 Linux/arm64
child `sha256:2fc782d346b0670c43378557cf8a2a9926a1f3d28e596180e7b21a0736d8cb7d`.
For an explicit Linux/amd64 build, set `OPENCODE_BASE` to
`ghcr.io/anomalyco/opencode@sha256:85986f556e985e377bd24cd68a5ccfbc647bb49e591194edda8a0e4542303319`,
the separately verified amd64 child of the official 2.0.32 OCI index
`sha256:02998f912cc8bf84ce20ff9d9faa33225406c52f9d13f8f86b376490f1e28813`.
This is a source/build candidate only. On the cloud executor with its managed
proxy and an existing combined CA bundle, the exact amd64 build command is:

```sh
docker buildx build --platform linux/amd64 --load \
  --build-arg OPENCODE_BASE=ghcr.io/anomalyco/opencode@sha256:85986f556e985e377bd24cd68a5ccfbc647bb49e591194edda8a0e4542303319 \
  --secret id=proxy_ca,type=file,src=/etc/ssl/certs/ca-certificates.crt \
  -f evals/native-qualification/Dockerfile.opencode-kanboard-runtime \
  -t t02-kanboard-runtime:amd64-candidate evals/native-qualification
```

Keep HTTPS certificate and hostname checks on. The secret is mounted only at
`/etc/apk/ca.pem` during `apk add`; do not copy it into the image or receipt.
The mount is optional for the local arm64 default, which retains its existing
base digest and system trust when the build argument and secret are omitted.
Record the exact build command, derived image ID, architecture, OpenCode
version, PHP version and modules before using the image. Keep the historical
arm64 receipts.

**Status of this refreshed bundle:** source transfer ready after the local
36-file and source-only checks. The embedded relay cross-build receipt
`experiments/native-network-preflight/tcp-relay-host-override/cloud-linux-amd64-20261020a/result.json`
has `cloud_execution: false`: it records the earlier local cross-build only.
Cloud task `01a15aae-2ba3-7160-96ba-2fdf5e20700b` (20 October 2026)
later ran that exact binary twice against an owned receiver. Cloud task
`01a15b0a-9bba-7282-8f57-2f37f42a0012` (20 October 2026) passed both
source checks and Linux direct 29/29, upstream proxy 95/95, and private
listener 106/106 on the preceding bundle; its amd64 base downloaded, but
`apk add` failed TLS trust, so no derived image was produced. A later run in
that same cloud task used the CA-backed bundle and verified Linux/amd64 image
`sha256:a50c602b437f30d2d1d27ba73d08df47db7461915a0d563282d07e862f2ad29b`. Its
first managed runner attempt stopped at host-check check 8, before container
start: Docker had injected upper- and lowercase `HTTP_PROXY`, `HTTPS_PROXY`,
and `NO_PROXY` despite no request for those six variables. Exact image/cache
cleanup passed. The next cloud run at source commit `998d10f` proved the
explicit empty proxy overrides: its stopped network-none host checker had
all ten proxy variables empty. It built and inspected immutable amd64 image
`sha256:93a34186b699a11925b9b965e5e9a7c60e33ec0d5ee08db4949c3796b12ca423`.
The runner then failed check 17 before `NativeRun`, because this daemon
rejects a static relay IP on an internal bridge whose subnet Docker assigned
automatically. It removed its exact containers, networks, image and cache;
no native session started. The later `5aa13885` bundle added an explicit
internal subnet and passed 35/35 cloud pre-session checks, including stopped
static relay attachment, owned CONNECT/native TLS and exact cleanup; it
deliberately stopped before `session.create`. A separate owned-only challenge
on that pinned topology passed 126/126: the kernel observed distinct relay
and unrelated-container peers, denied an unrelated same-capability spoof
without ledger or receiver spend, denied direct researcher access, and
restored the Docker baseline. It made no native session or provider call. This
refreshed runner checks the wrong peer and direct bypass again on each cloud
owned-response run before `session.create`; that new guard has not yet had a
cloud execution receipt.

The runner accepts an explicit cloud platform, immutable image ID, relay SHA,
nonoverlapping private internal and external subnets, external listener/peer,
and selected HTTP proxy variable.
Cloud `direct` is rejected. `--live-free` is hard-blocked before output
creation until a later reviewed change has evidence for the actual owned
cloud sidecar route and native TLS trust. The offline owned-response run uses
`--dummy-port`, so it cannot prove that upstream hop.

The next cloud operator should:

1. Verify the ZIP and every manifest entry. Review conflicts before copying
   files into another checkout. Do not put credentials or account settings in
   the transfer or its ordinary receipts.
2. Read the executor's current environment status and enforced network policy.
   Confirm the local Docker socket and bind-source visibility without changing
   its configuration or existing services. Observe image OS/architecture and
   use the exact amd64 build command above; record the build command and
   immutable derived image ID. Stop if PHP 8.4.26, SQLite or GD cannot be
   verified in that image. Keep the CA secret out of the image and logs.
3. Choose and read back nonoverlapping private internal and external Docker
   bridge subnets, intended gateway and relay peer on each run. The 126/126
   peer result applies only to its pinned topology and daemon. Before native
   inference, require per-run wrong-peer and researcher
   direct-bypass probes to fail closed. If Docker NAT makes peers
   indistinguishable, stop.
4. Prove the selected executor HTTP CONNECT sidecar with an owned receiver,
   then prove native TLS trust through the relay without disabling certificate
   checks. This candidate runner places the per-run wrong-peer guard before
   its first cloud native request. Exercise that guard and then the full
   owned-response native E2E with source/image/relay pins, producer stop, and
   exact cleanup. The 126/126 one-off challenge alone does not qualify it.
5. Review that receipt before considering the one bounded harmless free-model
   diagnostic in `T02-V2-MANAGED-LIVE-CHECKS-20261020.md`. A failed preflight
   is an unavailable result, not a reason to relax isolation or retry blindly.

The bundle contains no raw prior run outputs, native stores, Docker volumes,
capabilities, keys, or provider credentials. It supplies source and the
previously cloud-exercised relay binary. The separate cloud checks apply to
their recorded inputs; the new per-run guard and managed native E2E still need
cloud execution. The upstream sidecar and provider remain unqualified.
