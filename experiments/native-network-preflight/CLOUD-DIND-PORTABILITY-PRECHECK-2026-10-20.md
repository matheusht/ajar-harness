# #161 — cloud Docker-in-Docker portability precheck

Status: the explicit upstream HTTP CONNECT proxy leg is implemented and locally
exercised with an owned proxy/TLS receiver (84 checks), with the existing direct
transport regression passing 28 checks. Bridge ingress remains a proposal. Actual
OSLit executor topology, network policy, trust and architecture remain unverified.
No Docker, provider, model, CI or cloud command ran for this implementation.
#161 remains open. Existing local receipts are not cloud qualification.

## Source observations

- `tcp_relay.go:43` dials `host.docker.internal:$HOST_GATEWAY_PORT`. Its source has no
  configurable host or Unix-socket target. `v2_connect.py:297` binds TCP to
  `127.0.0.1`; readiness reports that loopback host. The original source line
  references here describe the initial precheck, before the proxy-leg addition.
- The direct/default branch still resolves and dials public `opencode.ai`. The
  implemented explicit `--upstream-proxy-env HTTP_PROXY|HTTPS_PROXY` mode instead
  resolves only the selected HTTP proxy and sends fixed CONNECT opencode.ai:443.
  The new branch has no direct fallback. Actual cloud sidecar policy is unverified.
- `NativeRun` launches CONNECT as an immediate subprocess and passes proxy_args;
  both remain in the outer executor namespace. Inner Docker containers have
  separate loopback. No extra lifecycle process is needed for a transport change.
- `check_v2_network.py:140-151` hardcodes `/opt/homebrew/bin/go`, GOARCH=arm64 and
  a Linux arm64 output. T02's managed runner pins that compiled artifact and a
  locally derived image ID. Cloud compatibility and new architecture-specific
  image/binary digests must be established, not assumed from those local pins.
- `tools/docker_session_runtime.py:218` preserves DOCKER_HOST/DOCKER_CONTEXT.
  Merely checking the cloud local socket does not pin later helper operations
  if the launcher still inherits selectors for another daemon.

The cloud runtime skill's Docker reference forbids using host networking or proxy
bypass to work around policy. Its networking reference requires the selected
executor's current network-policy snapshot and observed readiness. Neither
host.docker.internal availability nor an explicit TCP grant is established here.
Adding host-gateway alone would map a bridge address, not make a loopback listener
bind that address. A wildcard listener alone would expand listener exposure.

## Bridge proposal and implemented upstream leg

Keep CONNECT/NativeRun in the outer executor. Keep the sealed producer manifest,
run/provider state, capability file and dispatch lock outside every producer mount.
Keep researchers internal and the existing bounded relay in the producer inventory.

1. Explicit private ingress: propose `--listen-address PRIVATE_BRIDGE_GATEWAY`
   and `--relay-peer EXACT_RELAY_IP` for CONNECT. Default stays loopback outside
   the cloud recipe. Non-loopback mode must require the exact relay peer, reject
   wildcard/public addresses, and reject other sources before admission. Read back
   actual bridge/relay IPs in cloud; do not assume source NAT preserves an address.
   Seal bind/peer configuration into the frozen pool identity. T02 supplies a
   relay-target host such as `HOST_GATEWAY_HOST`, using the inspected owned bridge
   gateway instead of a Desktop-only hostname. The existing port stays explicit.
   This preserves the TCP readiness shape and avoids host networking/route changes.

2. Implemented explicit proxy egress: `--upstream-proxy-env HTTPS_PROXY` (or
   HTTP_PROXY). Owned E2E receipts and limits are in
   `UPSTREAM-PROXY-RESULTS-2026-10-20.md`. Actual cloud policy compliance is not
   inferred from a local fake proxy.
   Read the selected outer executor's injected variable without printing it.
   The implementation requires a valid HTTP proxy and uses bounded stdlib socket
   HTTP CONNECT to the single
   fixed `opencode.ai:443` authority through that proxy. Do not resolve/dial the
   public provider directly in this mode; denial/error never falls back to direct.
   Preserve configured proxy authentication and trust, and never send the inbound
   local capability as sidecar credentials. Freeze the selected transport mode
   and non-secret proxy endpoint identity; do not record credential-bearing URLs,
   headers or environment dumps. Unsupported proxy schemes fail closed.

3. Retain existing controls: same worker/connection/charged-byte/deadline limits,
   final-send guard, PPID watcher, parent fallback, freeze-before-run-REVOKED and
   UNSAFE semantics. Add the sidecar socket to the same owned socket set, with
   bounded connect/handshake/send waits and no retry or pool reset. NativeRun's
   public API can continue forwarding proxy_args; it needs no new supervisor.

The sidecar may terminate/reissue TLS under configured trust. T02 must provide
its combined CA through the actual native client's supported read-only trust
mechanism. Proxy defaults on new inner containers must not become an alternate
researcher egress route. Preserve inherited runtime authentication guard variables
on the outer executor while explicitly retaining the researchers' local relay
proxy settings and isolation. Never disable certificate verification.

The bridge ingress leg is still an unimplemented TCP proposal pending cloud
evidence; the explicit upstream leg is locally implemented and tested. If cloud policy/topology cannot safely expose one bridge listener,
consider an AF_UNIX socket mounted only into the trusted relay as the alternative.
That avoids bridge listener exposure but changes listener/readiness/mount contracts
and requires additional permission/cleanup checks. Do not implement both paths.
Moving the host control files or Docker socket into a producer, host networking,
a general forward proxy or raw public TCP fallback are not acceptable alternatives.

## Cloud E2E failure checklist, written before implementation

All first-stage positives use an owned fake policy proxy and owned TLS receiver;
no provider/model call. The fake proxy must exercise the new upstream-proxy branch,
not --dummy-port that could skip it. Preserve exact command inputs, source/build
pins, sanitized logs, policy observations, independent receiver traces and cleanup.

| Failure | Required external check / acceptance |
| --- | --- |
| Wrong or unready executor/policy | On the actual cloud executor inspect environment status and `/etc/codex/network-policy.json`; require current ready observations and enforced policy. Missing/unsupported/pending is unavailable, not clearance. |
| Wrong Docker daemon or bind source | Use the skill's explicit local-socket daemon check. Launch qualification with endpoint/context/TLS selectors cleared for that command and its descendants; preserve DOCKER_CONFIG/registry credentials. Prove same daemon and source-path visibility with a harmless private bind sentinel before native activation. No daemon restart without required authority. |
| Binary/image architecture mismatch | Record executor/daemon and image OS/architecture, Go executable/version/hash, source/hash and exact offline build settings. Build the relay for actual Linux architecture, pin the resulting binary and derived image. No stale arm64/image-ID shortcut or implicit emulation claim. |
| Desktop-only bridge assumption | From the actual relay prove reachability to the explicit private bind address/port. Save outer bind and actual relay peer readback. Failed relay positive is unavailability, not passing researcher isolation. |
| Listener exposure or source spoof | A researcher and an unrelated inner container cannot use the outer listener even with a known local run capability; the exact sealed relay can. Wrong capability/authority still reject. No wildcard/host network or route-rule bypass. |
| Direct public egress bypass | Owned policy proxy records fixed CONNECT authority, the TLS receiver sees the positive, and instrumented connection evidence establishes no raw public-destination fallback. Sidecar deny, timeout, malformed response and missing proxy all fail closed. Never infer global no-egress from one silent observer. |
| Wrong proxy branch tested | Fake proxy mode uses actual upstream CONNECT establishment; --dummy-port does not silently bypass that branch. Change the selected proxy endpoint/mode on the same retained pool and require frozen-config refusal without counters/deadline reset. |
| Trust bypass | Correct read-only combined CA permits the owned positive; missing/wrong CA rejects at the real client. No --insecure, skip-verify, TLS downgrade or credential-bearing log. |
| Inner inherited proxy escape | Inspect only necessary proxy/trust fields with values redacted. Researchers use the bounded local relay; injected default proxy variables/alternate proxy addresses do not provide an unmetered route. Retain negative DNS/direct-route/Host/SNI limits explicitly. |
| Alternate CONNECT authority | Wrong host/port/method/capability rejected before proxy forwarding and without an accepted tunnel. Exact authorized host still succeeds. No client-selected sidecar or routing headers. |
| Lost parent/child or user stop | Run actual single-parent loss, single-child loss, explicit stop and original run/provider deadlines. All registered producers freeze before trusted run REVOKED; held/fresh native and host effects stay blocked. Mark provider-only closure separately. Compound parent+watcher SIGKILL remains the already-observed residual limit, not repaired by networking. |
| In-flight/blocked proxy path | Hold a sidecar handshake and real backpressured sends, stop, then verify no false run marker, bounded cleanup and conservative charged counts. Already-sent settlement stays distinct from new dispatch; no retry. |
| Inventory/control exposure | Read back every registered researcher/reviewer/resume/relay container. Exact IDs/nonce/config/mounts match; all host control and proxy-auth files remain outside their mounts. No Docker socket or whole outer HOME mount. |
| Cleanup/false proof | Only exact nonce-owned IDs removed; unrelated cloud services remain. Preserve research/history, copy-check SQLite, verify processes/listeners/resources absent. Proxy or Docker failure retains UNSAFE/unresolved, never a fabricated verified stop. |

NativeRun POSIX flock, permissions, PPID detection and monotonic clocks look
source-compatible with Linux; this is not execution proof. Cloud PID1 reaping,
filesystem ownership, binding and daemon access remain E2E prerequisites.

## Ownership and integration handoff

This lane owns CONNECT/native_run only. Proposed transport flags/config validation
and proxy chaining belong in v2_connect.py; native_run continues forwarding args
with unchanged lifecycle code. The coordinator authorized the upstream leg after
this precheck; that leg is implemented. Bridge ingress remains unimplemented.

T02 owns runner topology, explicit local-daemon invocation, host bridge/relay IP
readback, architecture-appropriate build/image, trust mounts, producer inventory,
artifact sanitization and final pin refresh in
`evals/native-qualification/smoke/opencode_v2_managed_owned.py` and its checks.
The relay target/build change in tcp_relay.go needs allocation with T02/coordinator;
this lane has not edited it. These are dependent integration steps, not separate
cloud clearance. Coordinate them before source pins are refreshed.

Cloud access and the actual executor's enforced policy must arrive first. Until
then ingress/cloud integration remains source-grounded and untested; the owned
upstream E2E is transport evidence only. No local Docker/provider run substitutes
for cloud qualification, and no #161 closure or G01 adoption follows.
