# Local CONNECT readiness vs stop and strict status framing

Both reviewed intervals reproduced on owned TCP sockets before source changes.
The minimal fix passes 94/94 upstream checks, 106/106 private-listener checks and
28/28 frozen direct checks on final source. No Docker/provider/cloud/CI call or
T02/relay/readiness-document edit occurred. #161 remains open; no G01 adoption.

Final v2_connect.py SHA-256:
`f3bca478555f72a5411987a51e59d630b69dd8b86dd3c8ecc5d7d9971e4f24ea`.
Before source: 9a8854363064ada3d8b351f153e7feb99792fbaa4fc302ec4c07785f056cf607.
NativeRun is unchanged. T02 and the transfer bundle require review/repin to the
final CONNECT source before any launch; no runner change was made by this lane.

## Reproduced readiness write

The real fake-proxy CONNECT completed. A child-only wrapper held the subsequent
pool.active() call after it computed true, and independently held watcher socket
teardown. The host invoked the real NativeRun request_stop against a labelled
host-only dispatch fixture. After stop returned, releasing the held active check
caused actual client.sendall HTTP 200 begin/end events and client acceptance.
The retained receipt records the ordering, not only an in-memory socket result.

This is a late local readiness write after completed dispatch-authority closure.
It does not establish a provider/model request, native effect, producer freeze or
post-native-REVOKED dispatch. The fixture never invents a native verified marker.
The before receipt keeps native_verified_marker_present=false.

The fix creates a fresh dispatch guard around the active recheck plus local 200
write. It does not reuse the exhausted opening-hop context manager. Existing
bounded write timeout, upstream response reading outside the guard, guarded
upstream connect/header, payload guard, peer filter, accounting and marker logic
remain. New runtime diff is that guard plus the strict status-token condition.

The final deterministic run holds the active check inside the acquired readiness
guard. Stop waits until release; actual local 200 write ends before request_stop
returns. If stop wins before guard acquisition, the active recheck refuses the
write. Already-written readiness bytes can remain buffered and be observed after
stop; the guarantee is write ordering, not recall or a promise about receive time.
This serialized guarantee uses managed NativeRun dispatch authority. Standalone
provider-marker closure remains the existing watcher mechanism, not a native
verified-stop API or a zero-lag physical stop guarantee.

## Reproduced framing gap

An owned proxy sent HTTP/1.1 200 immediately followed by CRLF CRLF, omitting the
required space after the status code. The old parser accepted two split fields
and emitted local 200. The independent negative receipt records acceptance=true.
The parser now requires all three fields from its bounded status split. It rejects
that malformed line while the valid empty-reason form HTTP/1.1 200 SP CRLF CRLF
still tunnels real owned TLS bytes. Existing malformed/denied/EOF/header-bound/
timeout cases continue to fail closed with no raw-provider fallback.

## Evidence

| Cohort | Result |
| --- | --- |
| v2-readiness-stop-before-20261020a | actual local 200 write after completed stop; failed check retained |
| v2-status-space-before-20261020a | malformed no-space status accepted; failed check retained |
| v2-readiness-status-final-20261020a | 94/94, readiness order and strict framing plus proxy regression |
| v2-readiness-private-regression-20261020a | 106/106, private peer and audit-budget controls |
| v2-readiness-direct-capsule-20261020a/result | 28/28, exact frozen direct/default inputs |

Machine index: evidence/readiness-status-qualification-20261020.json.
Read-only audit: evidence/readiness-status-audit-20261020.json. It verifies exact
source cohorts, original SQLite unchanged after 31 disposable-copy checks, 91
recorded host PIDs absent, 51 listeners absent, temporary capability/private-key
workspaces removed and final credential/source checks passing. Failed receipts
remain unchanged. No timing/performance or universal lock-fairness bound is claimed.

## Repeat and limits

```sh
python3 experiments/native-network-preflight/check_v2_upstream_proxy.py --output NEW_OUTPUT
python3 experiments/native-network-preflight/check_v2_private_listener.py --output ANOTHER_OUTPUT
python3 experiments/native-network-preflight/evidence/v2-readiness-direct-capsule-20261020a/source/check_v2_connect.py --output THIRD_OUTPUT
```

Requires Python stdlib/OpenSSL and an already assigned local RFC1918 interface
for the private check. Each output must be fresh. The direct capsule pins the
otherwise unused Go metadata source against other-lane edits; no relay is built
or executed by that check. The upstream wrapper refuses non-owned network hops,
records actual socket writes and uses the existing real guard without claiming a
Docker inventory or native stop verdict.

Cloud ingress/NAT source isolation, policy/CA trust, all native producer routes,
provider/inference accounting, recovery and simultaneous loss of both stop paths
remain separate qualification. This bounded transport repair cannot close #161
or turn the prior local native source cohort into final-source native proof.
