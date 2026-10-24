# Kanboard v1.2.36 native effect capture: checks before implementation

This is a local #158 capture candidate on an owned, disposable Kanboard copy. It
does not run a model, qualify a native session, file a finding, or clear G01.
The original S10 six-arm preflight is reused byte-for-byte for its seed, normal,
denial, release, and one-line-repair controls. Its source in the operator tree was
`evals/native-qualification/s10_observer_case.py` at SHA-256
`da8da588a0ea0c81a106151324e0ee0bbeff9cf80565c6fefe833b6750b2e8e4`.
It is a local synthetic preflight and was not in PR185 or `origin/main` when this
check was written.

## Decision and existing route

The missing fact is whether the **same protected app request** made by A added B
to private project Q, followed by B's fresh authenticated read of task T. The
operator's earlier `s10_observer_case.py` proves this with a host client and
post-request SQLite reads, but does not bind those effects to a researcher-owned
request. `ProjectPermissionController::addUser()` authorizes URL project S and
uses the POST body project ID in v1.2.36; the write precedes
`Response::send()`'s redirect. `TaskViewController::show()` returns the protected
T page after `ProjectAuthorizationMiddleware` derives Q from T. A transport
proxy would miss direct app routes and cannot obtain the authenticated actor or
pre-write row by itself. The smaller serious alternative is PHP's
`auto_prepend_file` on a host-owned, read-only app container: snapshot the private
SQLite rows before Kanboard dispatch; at shutdown read Kanboard's authenticated
session, effective project role, response status/marker, and the after rows. The
app sends only a fixed sanitized receipt to a host-owned collector on a second
internal Docker network. Docker Desktop rejected a bind-mounted Unix socket in
an owned probe (`stream_socket_client`: `Not supported`), so the collector uses
an internal TCP socket and writes private SQLite outside all researcher mounts.
Writing sanitized receipts to the app's Docker error log would avoid the
collector, but would mix them with request/error logs and leave raw app access
logs in the Docker log store. This E2E disables app/client Docker logging and
uses the separate collector for schema validation, ordered persistence, and a
missing-receipt failure check. The collector still logs only fixed status and
rejection codes; its own access path contains no request data.

Touched seams are only the observer PHP file loaded by the app runtime, the
collector's PHP endpoint, and one focused Docker E2E/checker. Kanboard source
files, `index.php`, `jsonrpc.php`, the existing S10 seed logic, OpenCode config,
provider route, and filing code are unchanged. The runtime manifest must pin
the v1.2.36 commit, archive/source inventory and controller hash, app image ID,
observer and collector hashes, exact network/container IDs/IPs, and the input
S/Q/T/B IDs. `auto_prepend_file` is a local instrument, not a target repair.

## Failure conditions and checks

| ID | Failure injected or observed | Required local result |
| --- | --- | --- |
| F01 | Wrong/dirty source, changed source after launch, unexpected PHP/image, or missing/changed observer file | Refuse attribution; preserve a source/image/hash manifest and compare it before/after the owned run. |
| F02 | B already has Q access by direct/group/app role, Q is public, or T is absent/not in Q before A's request | Refuse the original-effect claim before dispatch. Seal the private baseline and prove a fresh B T read denies without the marker. |
| F03 | A is not app-authenticated, lacks S manager role, POST uses a forged actor header, invalid CSRF, or the route/body IDs are not S URL/Q body/B target | Receipt cannot credit the A write. Actor comes from Kanboard's post-middleware user session, effective role from its project-role model, and source IP from `REMOTE_ADDR`, never headers or an earlier API `getMe`. |
| F04 | The write mutates before the observer's prestate, leaves B-Q unchanged, mutates an unexplained row, or a later host replay supplies the only success | Require one same-request B-Q `absent -> project-manager` row transition, S/Q/T invariants, monotonic collector order, and no other protected-state transition. A post-run replay is labeled separately and cannot replace it. |
| F05 | B's fresh web read is absent, not B-authenticated, not Q-authorized, returns a different task, or lacks the marker | Require a new B session's `TaskViewController::show(T)` receipt with B's Q role, HTTP 200, marker present, and matching protected T/Q rows; the separate B client result must agree. |
| F06 | Scratch PHP, another container, host replay, or forged `X-Forwarded-For` makes a request | App source/data/observer/collector are absent from the researcher container. Its exact inspected IP is necessary, never sufficient, for native attribution; header text cannot change `REMOTE_ADDR`. A second client's different IP is rejected. The researcher cannot reach the collector network directly. A host `docker exec` inside the researcher container has that same IP, so a later native run must bind its own session/tool time window and independently audit host exec events; absent that audit, this remains a run-level local candidate. |
| F07 | JSON-RPC batch, unexpected route, extra writer/read, or unexplained state change | Mark JSON-RPC unsupported and fail attribution; never infer one actor/effect from a batch or a later state read. The E2E requires the exact 11-request login/form/invalid-CSRF/A-write/fresh-B-read sequence. Its ordinary `other` requests must leave every protected row unchanged, and any extra request fails. Only the web A-write/B-read path can pass this slice. |
| F08 | Collector socket is unavailable, app hook errors, receipt is missing/duplicate/reordered, or collector SQLite is researcher-writable | The app's ordinary response may proceed, but the capture checker fails closed. The collector stays on its own internal network and private writable mount, with no published port. |
| F09 | Observer changes target semantics, leaks a cookie/password/header/raw body/signed URL, or cleanup leaves processes/networks/data | Compare the same-image pristine and observed web statuses, marker presence, and protected state; retain body hashes as diagnostics because fresh sessions/CSRF make exact bytes unstable. Keep the existing six-arm normal/repair controls. Retain only fixed fields and digests; inspect saved outputs for sensitive patterns; stop/remove only nonce-owned resources and verify absence. |
| F10 | The researcher/client mount or saved output contains any synthetic account password, including private-project owner C's unused password | Keep credentials in host memory; pass only A and B's needed synthetic login values over stdin to the disposable client. Assert the mounted input has no password and the saved result contains none. |
| F11 | A receipt changes the denied task ID, invalid write route/body IDs, or either write's captured HTTP status while the verifier still returns true | Before accepting a positive, mutate each field in a copy of the passing receipt and require `verify_original` to reject it. Compare the actual request IDs and statuses to the client result. |
| F12 | The researcher shares the collector network but a rejected HTTP GET is mistaken for a network denial | Treat any HTTP response, including 403, as reachable; only DNS/connect failure counts as unreachable. Temporarily attach the owned client to the app-only network, prove the reach check turns true, then detach it and prove the original isolation check turns false again. |

The E2E must run its protected A/B HTTP against a disposable pinned v1.2.36 app,
save a private machine-readable result with input pins, expected/actual checks,
collector rows, Docker readback and cleanup, and return nonzero on any failed
condition. Passing this candidate still does not establish a live model's first
request, its process origin, provider access, shared allowance, or native review.

Run from the repository root with a clean committed HEAD, the pinned source,
reference archive, local image, PHP, and Docker Desktop:

```sh
python3 evals/native-qualification/smoke/check_kanboard_native_effect.py \
  --source /private/tmp/kanboard-source-644ad391 \
  --reference-archive /private/tmp/s10-kanboard-e5ff28a8.tar.gz \
  --output /private/tmp/kanboard-effect-owned-NEW \
  --require-clean-head
```

The output directory must not exist. `result.json` must report `status: pass`,
the pinned harness HEAD, 11 original receipts, one protected B-Q role transition,
the pristine/observed parity checks, and every owned Docker ID absent after
cleanup. The six-arm replay remains at `s10-six-arm/receipt.json` and is a
separate local synthetic control.
