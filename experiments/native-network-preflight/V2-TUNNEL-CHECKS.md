# V2 exact-host tunnel checks, before implementation

19 October 2026. Supersedes JSON-gateway use for current qualification. Root's
official V2 client succeeded with its built-in free provider; direct custom API
calls were 403. Preserve official TLS/client behavior. Never spoof identity,
retrieve Keychain, import credentials, or use the hidden case.

Scope: implement and test an opaque CONNECT transport using owned dummy endpoints
first. Root alone reviews/starts the live official-client route. V2 image pin:
`ghcr.io/anomalyco/opencode@sha256:2fc782d346b0670c43378557cf8a2a9926a1f3d28e596180e7b21a0736d8cb7d`.

| Failure | Required check |
| --- | --- |
| Arbitrary proxy / wrong endpoint | Only authenticated `CONNECT opencode.ai:443`; reject GET, other authorities, ports, IP literals and suffix lookalikes. Host connects only fixed opencode.ai:443. Dummy mode maps only to a literal host-loopback port, never another external URL. |
| TLS/client identity altered | Tunnel forwards opaque bytes, supplies no provider headers/certificate/secret. Owned dummy TLS client verifies its own fixture certificate through the tunnel. No copied official identity header and no TLS interception. |
| Proxy environment is sole boundary | Researcher has one internal-only network and a static proxy address. Keyless relay alone is dual-homed. Direct external/host routes fail with reachable positive controls; arbitrary changed proxy settings cannot supply another route. |
| DNS bypass | Set researcher `--dns 127.0.0.1`, use literal proxy IP, inspect Docker DNS and resolv.conf. Challenge configured DNS, embedded 127.0.0.11 and direct owned DNS endpoint; save independent resolver observations and a working relay positive. Do not call failed TCP proof all-protocol or DNS containment. |
| Reset / race / overload | Persistent shared connection/byte quota and initial deadline, charged atomically before forwarding; at most four workers and bounded header/idle waits. Test concurrent byte exhaustion, restart, changed caps, rejected authorities and connection exhaustion. Bytes remain charged on failed writes; no refund or automatic inference retry. |
| Stop / crash / parent loss | Host REVOKED marker, duration and parent loss stop new tunnels and close active owned sockets. A crashed active tunnel leaves visible uncertainty and blocks restart admission. No claim that teardown recalls provider effects or that a tunnel equals a model request. |
| Secret / transcript exposure | Local proxy capability is researcher-readable and has no provider authority elsewhere. Record only metadata/counters/hashes, never decrypted provider content or auth values. No Keychain or provider credential in any lane invocation. |
| Cleanup / rollback | Exact owned IDs/processes only, preserve unrelated canary and persistent researcher files, retain source pins/ledger and failures. Verify listeners/resources absent. |

**Hard limits:** connections, total encrypted bytes (both directions), concurrency
and wall time. **Measured only:** model/API request count, output tokens and
provider usage from official client/provider evidence. CONNECT encryption prevents
gateway enforcement of model, URL path, request count or output tokens. A tunnel
may carry many requests. It permits the whole selected HTTPS host, not just the
inference path. These limits must remain explicit in T02/T05/G01; no complete
accounting, arbitrary-protocol, target-effect recovery or adoption pass follows.

Before network rerun: V2 reports `opencode v2.0.32`, not bare `2.0.32`. Its first
non-root check also needed explicit writable HOME/XDG. BusyBox wget sent a GET
through the HTTPS proxy and was correctly rejected; it cannot serve as CONNECT
positive. Use an owned Go standard-library CONNECT/TLS client with only the public
dummy CA, then separately test the official V2 client with production TLS intact.
Retain both failed receipts; do not weaken the proxy to accept arbitrary GET.

Further checks before the final revision: initialize rejection audit before any
header read; short/incomplete headers must save a sanitized rejection. Log only
method/protocol, exact known official/loopback hostname and port; no URL, path,
query, auth value, arbitrary hostname or full-target hash. Capability input must
be an owned private regular file, opened without following symlinks; reject loose
mode, symlink and nonregular input before listening. The smoke creates it 0600.

The official-client diagnostic requires loopback-only `NO_PROXY` for V2's own
standalone control server. Without it the proxy rejected a local GET before any
provider tunnel. A dummy-only rerun with that bypass observed official CONNECT to
`opencode.ai:443`; `models.opencode.ai:443` remained denied. The dummy certificate
caused retries and a bounded timeout. Do not call either observation a provider
403 or a native success; do not add a wildcard/bootstrap host automatically.

Stop contract correction before new tests: SIGTERM alone stops the process, not
the durable grant. Demonstrate idle stop/restart can admit within original caps,
then require a host REVOKED marker before controlled stop and show same-pool
restart cannot admit. Add an already-open owned connection at deadline and
independently verify no post-deadline payload. Document wall-clock rollback as a
residual; no monotonic-cross-restart guarantee is invented. Existing receipts
remain frozen.
