# Explicit upstream HTTP CONNECT proxy — checks before implementation

Owned scope: v2_connect.py only for runtime changes. Keep existing direct/default
and --dummy-port behavior; NativeRun forwards unchanged proxy_args. Add explicit
--upstream-proxy-env HTTP_PROXY|HTTPS_PROXY; no URL/credential CLI argument, no
ambient automatic routing, dependency, private-bridge listener or Docker/provider run.

Protocol/interface decisions: only http:// proxy URLs with a host and finite port,
optional percent-encoded Basic user/password, no non-root path/query/fragment or
control/whitespace. Proxy and dummy mode are mutually exclusive. Resolve only the
selected proxy before accepting clients. Fixed outbound CONNECT opencode.ai:443;
never forward client/local proxy credentials, headers or authority overrides.
Explicit mode fails closed with no raw-provider fallback. Freeze selected mode,
environment selector, canonical endpoint and credential identity in the existing
pool config. Credential identity must use HMAC with the private local capability,
not a bare reusable password hash or stored URL. Direct pool config stays byte
compatible. CONNECT handshake bytes are bounded transport overhead, not billed
model usage or tunnel payload accounting.

Use one owned Python fake HTTP proxy and one owned TLS receiver. New mode must
exercise the real proxy branch, not dummy-port. A test-only launch wrapper records
and rejects any public/non-owned resolution/connection attempt; the fake proxy
routes the fixed authority solely to the owned receiver. Record only sanitized
booleans/endpoint IDs and hashes; scan all retained artifacts for ephemeral proxy
and local credentials. Preserve before/after archived source, original failures,
private key cleanup and exact host process/listener absence. No native/Docker stop
qualification is inferred from these transport-only checks.

| Failure | Required external E2E check |
| --- | --- |
| Missing/invalid proxy | Missing variable, wrong scheme, bad port/path/query/fragment/control characters, unsupported variable and dummy conflict fail before readiness/connection, with sanitized error. |
| Wrong authority/auth | Incoming wrong host/port/method/local capability rejected before fake proxy receives a request; positive fixed authority reaches owned TLS and returns exact bytes. |
| Proxy auth leakage | Fake proxy confirms selected Basic credentials match; local run capability never reaches it. No secrets in argv, log, source wrapper, ledger or receipt. |
| Denied/malformed/timeout | Proxy 403, invalid status/header, oversized response, EOF and hang/slow header never yield client 200. Header total deadline/byte limit apply. No public DNS/connection attempt or raw fallback. |
| Socket ownership during handshake | After admission but before proxy CONNECT reply, provider revocation and original deadline close the pending upstream socket and client; no worker leak or later readiness. |
| Frozen transport/identity | Same state cannot switch endpoint, credentials, selector or proxy/direct mode; refusal before connection with original config/counters/deadline unchanged. Same-mode clean restart retains charged counters/deadline. |
| Direct regression | Existing owned check_v2_connect.py passes unchanged; no mode ignores bad ambient proxy and preserves prior dummy/default pool config. |
| Stop/backpressure | Real bounded unread proxy sockets stage charged uploads. Provider revoke/deadline closes held and fresh transport; no post-stop charged payload. All workers/upstream sockets settle. Existing native dispatch guard remains in its original final-send position. |
| Wrong end-to-end evidence | TLS positive, trusted CA and returned payload must be actual. Proxy fixture receives exact authority and records no copied client routing headers. SNI/Host opacity and request/token/USD limits remain explicit. |

Runtime should register upstream sockets before proxy handshake, so existing
watcher shutdown interrupts a blocked handshake. Keep five-second finite socket
and whole-header timeout, sixteen-KiB response bound, same worker cap, accounting,
no retry/reset, and existing guard/unsafe-marker logic. Only then refresh owned
pins and hand the final source SHA to T02 before any cloud launch.

Review-discovered pre-send boundary: socket creation and upstream CONNECT header
write must take the existing NativeRun dispatch guard with an active recheck.
Use one five-second total budget for connect+header send; response reading stays
outside the guard so stop can interrupt it. In a clearly labelled host-only
fixture, use actual native_run state/dispatch_guard without pretending a Docker
manifest or verified producer stop exists. Hold actual Pool.admit after admission,
close the real host dispatch authority, hold watcher socket teardown independently,
then release the admitted operation. Neither a new upstream TCP connect nor HTTP
CONNECT may happen. No native run REVOKED/producer qualification is inferred.
Also reject status-line control bytes and empty query/fragment proxy URL delimiters.

Independent-run failure before checker repair: ordinary test SIGTERM can interrupt
an owned SQLite transaction and leave a hot rollback journal. A mode=ro ledger
read cannot recover it and may raise SQLITE_READONLY after otherwise good checks.
Read/recover only this test's owned working pool with a normal SQLite connection;
preserve the independent failed receipt/journal. Validate recovery on a disposable
copy of the failed pool and rerun the full E2E. Archived/native evidence integrity
checks remain copy-only; do not rewrite the failed original or runtime source.

Linux cloud evidence before predicate repair: recv(65536) legally returned 32768.
Four live senders and an unread proxy were genuinely backpressured, but requiring
each active tunnel uploaded>=65536 stayed false until the real five-second socket
timeout closed workers. Cloud recorded proxy payload consumption zero, receive
buffer 8192 and client buffers around four MiB. Preserve that failed cloud receipt.

Repair only the checker oracle: four active tunnels each have positive charged
payload, senders remain live and the actual proxy's payload-consumed counter is
zero. Observe the zero counter around real recv calls, not a synthetic transport.
Bound staging and record stop issuance before the five-second timeout; retain all
socket shutdown, exact cleanup and unchanged post-stop-charge assertions. Do not
change runtime buffers/caps/timeouts, invent a full-read guarantee, or count later
buffer drain as post-stop dispatch. Real chunk sizes are allowed to differ by OS.
