# T02 cloud source transfer — 20 October 2026

This is a credential-free snapshot of the current managed V2 CONNECT candidate,
its prewritten checks, the pinned T05 controls, and a Linux/amd64 relay
cross-build. `source.zip` contains exactly the repository paths listed in
`SOURCE-MANIFEST.json`, plus that manifest. `TRANSFER-REPORT.json` records the
ZIP and manifest hashes. Verify both before extracting into a private checkout.
The shared local worktree is mostly untracked; cloning its Git HEAD alone will
not reproduce this candidate.

**Status:** transfer ready; cloud and live provider execution unqualified. The
relay binary was built twice with identical bytes from pinned Go source, but
has not run on the cloud executor. The runner accepts an explicit cloud
platform, immutable image ID, relay SHA, RFC1918 subnet/listener/peer, and
selected HTTP proxy variable. Cloud `direct` is rejected. `--live-free` is
hard-blocked before output creation until a later reviewed change has evidence
for the actual owned cloud sidecar route and native TLS trust. The offline
owned-response run uses `--dummy-port`, so it cannot prove that upstream hop.

The next cloud operator should:

1. Verify the ZIP and every manifest entry. Review conflicts before copying
   files into another checkout. Do not put credentials or account settings in
   the transfer or its ordinary receipts.
2. Read the executor's current environment status and enforced network policy.
   Confirm the local Docker socket and bind-source visibility without changing
   its configuration or existing services. Observe image OS/architecture and
   build the pinned Dockerfile there; record its immutable image ID.
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
capabilities, keys, or provider credentials. It supplies source and a
cross-built binary, not evidence that cloud policy, route, image, trust, or
provider behavior is qualified.
