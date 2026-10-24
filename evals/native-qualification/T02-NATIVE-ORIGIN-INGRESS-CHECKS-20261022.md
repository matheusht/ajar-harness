# Native request-origin ingress: failure checks before code

Decision under review: use four trusted Unix-domain ingresses: target plus
researcher, target plus resume, review-target-1 plus reviewer-1, and
review-target-2 plus reviewer-2. The target's PHP broker keeps session cookies
and CSRF tokens and binds only to target loopback. Each ingress shares its
target's network namespace and its agent's PID namespace, but has a separate
read-only root and host-owned ledger mount. The agent sees only a
read-only-mounted Unix socket and client executable. A single `SOCK_SEQPACKET`
message carries one bounded HTTP request; `SO_PASSCRED` supplies kernel-checked
sender credentials for that exact message. The ingress reads the sender's
PID/start time and live `/proc` ancestor chain, requiring the exact
host-registered OpenCode exec root before forwarding. It joins the broker
response ID to the app collector after stop. A copied ID in tool output alone
never grants origin.

The simpler serious alternative is the current broker peer IP plus process
inventory and Docker exec audit. It cannot reject a host-owned client sharing
the agent network namespace, and an inventory at dispatch start misses a later
fork. A stream Unix socket with `SO_PEERCRED` alone also accepts a connection
whose file descriptor is handed to another process; per-message credentials
are required. Linux `SO_PASSCRED`/`SCM_CREDENTIALS` and `SOCK_SEQPACKET` are the
chosen primitives. This design remains a candidate until a disposable Linux
runtime proves the mount, PID namespace, credentials, and Docker stop behavior.

## Failure matrix

1. The source or cross-compiled ingress/client binary is unpinned, missing,
   wrong ELF platform, writable by the agent, or fails its local protocol
   checks: stop before Docker creation.
2. The socket directory is writable by the agent, the ledger or arm directory
   is visible through agent mounts, or those directories are reachable through
   the ingress process's `/proc` root/fds:
   refuse activation. The ingress must become nondumpable, have no capabilities,
   and receive no target credentials.
3. Either PHP broker listens on a nonloopback interface, the agent can reach it
   over TCP, or any of the four ingresses is missing or not in its exact target
   network and agent PID namespaces: refuse activation. A host replay may still
   cause an effect, but without an ingress record it must never receive
   native-origin credit.
4. No exact pre-dispatch OpenCode exec root PID/start time is registered by the
   host before the model runs; wrapper preamble is missing, duplicate, changed,
   stale, or followed by an unexpected process; its arm heartbeat is stale; or
   the release FD closes: keep the turn `unknown_effect` and do not release the
   model.
5. The sender credential message is absent, truncated, duplicated, malformed,
   or names a PID that exited, was reused, is not a live descendant of the
   registered root, or changed start time during the read: never forward.
   An inherited/passed connection FD must not transfer sender identity.
6. A request is oversized, malformed, pipelined, issued outside the armed
   dispatch, or is a duplicate; the backend is unavailable; or the response
   lacks one valid `X-LRH-Request-ID`: do not claim a positive origin record.
   No raw request, response, cookie, password, or token enters the ledger.
7. The ingress record is missing, rewritten, has a duplicate broker ID, lacks
   an exact native tool line/command hash, or cannot join one protected app
   receipt with matching target/source/run/dispatch: hold. A same-IP host
   replay or printed broker ID alone holds.
8. The four effect-capable ingresses are absent from their separate exact-ID
   resource ledger or from their stop/cleanup proof; NativeRun stop, ingress
   stop, collector freeze, receipt DB hash, target DB state, or exact-resource
   cleanup is incomplete or reordered: no final proof.
   A stopped positive applies only to the exact observed request; it cannot
   authorize original-call retry, run resume, finding filing, or other effects.

## Validation boundary

The provider-free check is `GO111MODULE=off go test ./tools/native_origin`
plus static cross-builds of the exact pinned Go source for `linux/amd64` and
`linux/arm64`. The recovery fixture and runner wiring checks exercise missing
and mismatched ledger records. `prepare --origin-ingress` checks the source
hashes, compiles the requested platform, and archives its binary digest. The
local Go checks run on macOS; Linux tests compile but have not run. These are
source/protocol checks, not native qualification.

The post-stop `reconcile-origin-transport` command may emit
`process_request_attributed` only for an acknowledged dispatch with an exact
gate registration, completed native tool output, ingress ledger row, broker
ID, app receipt in that dispatch's closed window, frozen collector, and exact
NativeRun/ingress stop and cleanup. This status means transport attribution
only: `semantic_verdict` remains `unreviewed`, and it grants no filing or
effect authorization. An uncertain S10 role-grant can be observed only through
its separately armed recovery contract, never retried or resumed.

The required later E2E uses disposable source and Docker only: show a native
tool process request with the exact broker/app receipt join for both S10 and
T01, including the resume role, plus a host client in a shared network
namespace, an agent background process from a prior turn, FD handoff,
stale/recycled PID, direct TCP attempt, missing broker ID, one missing
sidecar, and interrupted stop. Save redacted sidecar, app, NativeRun and
cleanup receipts. The route remains unqualified until that run succeeds.
