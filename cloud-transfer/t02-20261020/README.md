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
This is a source/build candidate only: the amd64 base and derived image have
not been built or run on the cloud executor. Record the exact build argument,
derived image ID, architecture, OpenCode version, PHP version and modules before
using it with the owned-response runner. Keep the historical arm64 receipts.

**Status of this refreshed bundle:** transfer ready; its updated Dockerfile and
source ZIP have passed local source checks, but have not been built or run on
the cloud executor. The exact cross-built amd64 relay binary ran twice there
against an owned receiver in earlier OSLit work, and separate Linux
source/transport suites passed in the cloud chat. Those receipts do not
qualify this bundle's derived Docker image, native run, provider route, or
cleanup. The runner accepts an explicit cloud platform, immutable image ID,
relay SHA, RFC1918 subnet/listener/peer, and selected HTTP proxy variable.
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
   build the Dockerfile with the explicit amd64 child digest above; record the
   build command and immutable derived image ID. Stop if PHP 8.4.26, SQLite or
   GD cannot be verified in that image.
3. Read back the private Docker bridge subnet, intended gateway and relay peer.
   Run the cross-built relay there against an owned receiver. Require the exact
   kernel-observed peer and reject researcher/unrelated-container bypass. If
   Docker NAT makes peers indistinguishable, stop.
4. Prove the selected executor HTTP CONNECT sidecar with an owned receiver,
   then prove native TLS trust through the relay without disabling certificate
   checks. Repeat the full owned-response managed native E2E on that cloud host
   with source/image/relay pins, producer stop, and exact cleanup.
5. Review that receipt before considering the one bounded harmless free-model
   diagnostic in `T02-V2-MANAGED-LIVE-CHECKS-20261020.md`. A failed preflight
   is an unavailable result, not a reason to relax isolation or retry blindly.

The bundle contains no raw prior run outputs, native stores, Docker volumes,
capabilities, keys, or provider credentials. It supplies source and the
previously cloud-exercised relay binary. The separate cloud checks apply to
their recorded inputs; this refreshed bundle still needs its own Docker,
native, sidecar, and provider qualification.
