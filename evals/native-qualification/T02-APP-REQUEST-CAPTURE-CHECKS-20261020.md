# T02 first-test application observation — 20 October 2026

Decision: qualify a host-owned application observer before #160 is launched.
The current combined OpenCode/PHP container runs Kanboard on private loopback;
the host client in the offline Kanboard receipt issued its **own** JSON-RPC
requests. PHP's server log records only HTTP lines, and the provider CONNECT
ledger sees no local application traffic. None proves the researcher's first
test request and response.

The smallest candidate is one host-owned HTTP observer on the private Docker
network, between the researcher client and its PHP service. Keep the PHP server
in the researcher's pinned container so the researcher still builds and runs
it. The observer forwards only to that exact container and port. The researcher
receives only the observer's internal address. A host-owned receipt records the
researcher container ID and network IP, the exact PHP server process and
listening port, the native session/tool call, request method and JSON-RPC
method, response status and outcome, and a monotonic order before any host
replay. It stores no Authorization value, password, cookie, token, or raw
request/response body. The observer must be read-only to the researcher and
must not be able to call an external target.

This is an observation candidate, not an enforced route. A researcher in the
same container can still call its PHP loopback directly. A proxy receipt is
therefore evidence only for requests it actually saw. Source IP binds a
container, not a process; a native tool record or independent process trace
must bind the sending process. If process attribution is unavailable, or if
the first test used the direct loopback path, fail the #160 capture gate rather
than crediting the host's synthetic request. The more complete alternative is
an independently captured network/process trace in the researcher's network
namespace, but no available image/tool has yet proved that path.

Before implementation or provider use, the offline E2E must falsify these
failure modes:

1. The observer receives a harmless researcher-originated JSON-RPC request and
   returns the exact live response while the host client remains idle. A host
   request on its own must be distinguishable and cannot satisfy this check.
2. Docker readback binds both exact container IDs, internal network, source IP,
   target IP and PHP listener process. A missing or ambiguous process binding
   fails even when the response body looks correct.
3. An ordinary authorized read, a denied private-project read, and a local
   effect produce distinct saved response outcomes. The host independently
   checks application state after the original request; a synthetic replay is
   separately labeled.
4. A direct loopback request bypasses the observer and is detected as an
   unobserved route, not silently credited. The run cannot claim complete
   capture from proxy logs alone.
5. The saved receipt and Docker logs contain no Basic value, password, cookie,
   token, raw body, or signed URL. Observer and app processes, ports, network,
   and disposable data are removed by exact owned IDs; source pins survive.

This step produced checks and topology only; it made no model/provider call.
T05's [first managed-send receipt](../../experiments/native-network-preflight/evidence/v2-managed-send-before-20261020a/result.json)
exposed an upload forwarded after verified producer stop. Its
[offline rerun](../../experiments/native-network-preflight/evidence/v2-managed-send-after-20261020b/result.json)
held that upload and passed the focused case with exact cleanup. That receipt
is explicitly partial T05 evidence; T02 must wait for the completed producer
stop qualification before binding the handle to a live run.
