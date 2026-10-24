# Local CONNECT 200 vs stop — failure check before source changes

Finding: after upstream proxy 200, Handler tests pool.active(), then writes local
HTTP 200 outside dispatch_guard. A stop may complete between the test and write.
Reproduce the actual write ordering before changing runtime code. No Docker,
provider/cloud, T02/relay/readiness edits or native producer qualification.

Use the established owned fake HTTP proxy and TLS receiver, and real NativeRun
request_stop/dispatch_guard with a labelled host-only state fixture. A child-only
wrapper marks completion of actual accept_proxy_tunnel and holds the following
active() call after computing its return value. Record actual local 200 sendall
begin/end and client observation timestamps; do not replace I/O. Independently
hold watcher teardown so socket closure does not hide a stale readiness write.

Start request_stop in a separate host thread, release the held readiness point
within a bounded interval, and retain original outcomes. Failure: local 200 is
written after request_stop returned, even if subsequent TLS/model bytes never
flow. Pass: no readiness write occurs, or the bounded write finishes under the
same dispatch guard before stop returns. A stop request waiting behind an already
held readiness guard is allowed; response reading stays outside that guard.

Client receive time alone is not the oracle: bytes written before stop may remain
buffered and be observed afterward. No implementation can recall those bytes.
The oracle is actual sendall completion ordered against completed stop. Record
this narrower boundary explicitly; no provider effect/billing claim follows.

If reproduced, smallest fix is a fresh dispatch guard around active recheck plus
local 200 send, preserving finite write timeout, guarded upstream connect/header,
payload guard, private-peer gate and existing stop logic. Do not reuse an exhausted
contextmanager instance. Rerun upstream, private-listener and frozen direct E2Es
on final source, preserve credentials/cleanup/source pins and tell coordinator the
new source SHA before T02 transfer/launch. If not reproduced/material, retain the
observed limit without a runtime edit.

Additional parser review before repair: strict status framing requires a space
after the three-digit status code, even when reason phrase is empty. An owned fake
proxy sends HTTP/1.1 200 followed directly by CRLF CRLF; require no local 200.
Preserve the failing E2E before tightening the status split. The valid empty-reason
form includes the trailing space and must remain accepted. No provider call.
