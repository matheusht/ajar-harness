# T02 OSLIT topology assessment

Recorded: 2026-10-21 UTC

## Result

The remaining owned-receiver proof cannot use a receiver inside this OSLIT client. The selected policy declares managed outbound proxies and no receiver, callback, or authority-remap field. The prior managed-proxy attempt to reach two client-owned addresses returned `503`, and the receiver recorded zero connections. This assessment did not repeat that known failed probe.

`--live-free` remains unconditionally denied with `cloud_live_route_not_qualified` before output creation or Docker. No source gate, transport authority, network policy, system trust, or persistent setting changed. No network probe, provider request, model call, or Docker mutation occurred.

## Observed boundary

- Source branch `codex/t02-live-prep-fail-closed-20261021` was clean at `5425d5869f4d835b3111b05be7b14b3769953028`.
- `/etc/codex/network-policy.json` was mode `0444`, SHA-256 `266ee47b22dd736206e1454a525c3003a458e742c7fca6b13765f4d8b5289275`, and declared managed HTTP and TCP CONNECT proxies. Raw proxy values were not retained.
- The HTTP policy type was `unrestricted`. The raw TCP destination domain and IP allowlists were empty. The policy contained no receiver, callback, or authority-remap field.
- `v2_connect.py` still fixes the production CONNECT authority to `opencode.ai:443`. Its owned fake-proxy check passes because that fixture locally redirects the fixed authority to its owned TLS listener. That behavior does not exist in the managed policy.
- The Docker baseline contained no containers, images, or volumes and only the default `bridge`, `host`, and `none` networks.

The policy file describes outbound access. The lack of a reverse route is an inference from the environment contract and the retained zero-connection result, not a claim about every deployment of the managed proxy.

## Evidence method and limits

`verify.py` parses the current policy and source, checks their hashes and fail-closed predicates, rejects retained raw proxy values, and emits `verification.json`. Its public entrypoint observes the checker and descendants with `strace -f -e trace=network`; the retained result records zero network syscalls. The verifier does not contact a receiver, provider, model, or Docker.

The no-probe and no-mutation fields describe this agent run from its command transcript. They are transcript attestations, not independent runtime observations. The Docker counts came from read-only `version`, `info`, `ps`, `image ls`, `volume ls`, and `network ls` commands. The repository projection omits daemon and network identifiers.

The three owned offline receipt hashes point to local prior-run artifacts that are not published here. The managed self-receiver failure has no raw probe receipt. Its retained provenance is the prior-run summary and append-only decision trail. This bundle keeps that limitation explicit instead of upgrading the summary into machine evidence.

## Smallest supported alternative

An operator must supply one task-owned TLS receiver outside this OSLIT client on a fixed FQDN and port that the managed proxy can reach. Before any provider request, a separately reviewed preflight must correlate one per-run nonce hash with a sanitized receiver-side connection record. The input must include:

- receiver ownership and authorization;
- the approved FQDN and port;
- confirmation that the managed proxy permits that route;
- the hostname-matching certificate chain and CA hashes;
- an ambient-only negative chain for the same runtime-path test;
- the sanitized receipt method, retention, and cleanup terms.

The actual OpenCode TLS path must accept the supplied owned chain and reject the ambient-only chain. CONNECT `200`, PHP TLS, a local fake proxy, or a caller-written receipt cannot substitute for that observation. A future implementation may use one reviewed immutable route profile supplied by the OpenCode qualification adapter to the transport core. It must not add a general `--authority` option.

## #161 boundary

The current 64-check owned run proves shared synthetic accounting, orderly first-session resume, stop ordering, and post-stop dispatch denial. It does not prove live interruption and recovery. The current resume happens before run-wide stop, and the live post-stop health path is an in-process dispatch-guard check rather than a network send.

A later live transport test must interrupt an active sidecar/TLS send, show no new admission or post-stop bytes, freeze the exact producers before trusted run revocation, and reconcile the old run before a separately bounded recovery run. Original-application effects remain outside this lane.

## Architecture boundary

`native_run.py` remains transport-neutral. `opencode_v2_managed_owned.py` is the OpenCode qualification adapter, not the general harness architecture. The fixed PHP workflow qualifies this adapter and does not prove model/provider/runtime-agnostic in-run hypothesis adaptation. No outer optimizer is introduced by this assessment.

The machine-readable receipt is `topology-assessment.json`. The deterministic checker is `verify.py`, and its observed result is `verification.json`. The published files omit raw proxy values and Docker identifiers.
