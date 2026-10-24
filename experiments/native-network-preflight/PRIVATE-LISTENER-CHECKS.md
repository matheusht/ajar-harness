# Private bridge listener — checks before implementation

Scope: v2_connect.py explicit ingress only, default 127.0.0.1 unchanged. No Docker,
provider/cloud run, routing/interface change, T02 runner/relay/readiness edit or
selection of actual cloud values. Use owned local TCP and cached stdlib/OpenSSL.

Proposed interface: --listen-address IPv4 --relay-peer IPv4, both or neither.
Both must be literal RFC1918 addresses (10/8, 172.16/12, 192.168/16); reject public,
wildcard, loopback, link-local, multicast, reserved/documentation, CIDR, hostname,
IPv6/mapped IPv6 and malformed input. is_private alone is insufficient. Neither
flag means the exact previous loopback behavior and pool config. Freeze canonical
listen/peer values in private mode's retained pool config; no downgrade/change on
reuse. Do not select interface or relay addresses automatically in runtime code.

Filter the actual accepted TCP client_address before worker allocation, request
header/capability processing or tunnel admission. Forwarded headers cannot set
peer identity. Unauthorized traffic may emit a sanitized rejection event but must
not consume tunnel count/charged bytes or cause any upstream connection. Both
source-IP and local capability checks are required. Keep existing lifecycle,
upstream proxy and payload guards, timeouts and quotas.

Before implementation, an owned local TCP probe successfully bound an existing
RFC1918 interface and accepted two local connections with distinct kernel peers:
the interface's own address and 127.0.0.1. This required no alias, route, firewall,
Docker or cloud operation. The E2E must independently repeat/record that proof.
If safe positive/wrong-source behavior is unavailable, report no-go, not acceptance.

| Failure | Required E2E observation |
| --- | --- |
| Default changes | Existing direct/default owned E2E passes. Explicit invalid flags never bind; neither flag leaves 127.0.0.1 and the old pool config shape unchanged. |
| Invalid/broad endpoint | Public/wildcard/loopback/link-local/multicast/reserved/hostname/CIDR/IPv6/malformed addresses, missing one flag, fail before readiness. Neither flag silently widens the listener. |
| Source spoof/admission | Own actual listener on assigned RFC1918 interface. Authorized TCP source + correct local capability reaches independent owned TLS/byte receiver. A different real kernel source, even with correct capability and spoofed X-Forwarded-For/Forwarded/PROXY data, closes before admission; zero new tunnels/bytes/upstream. |
| Capability bypass | Authorized TCP source with wrong capability rejects; authorized source/capability/wrong authority rejects. Independent receiver still works afterward. |
| Freeze bypass | Same retained pool cannot change listen address, exact peer, remove one/both flags or switch transport. Config/counters/original deadline unchanged. Clean same-mode reopen retains state and works within its original budget. |
| Resource/stop regression | Real held transport plus provider revocation and original timeout close the socket/listener and reject fresh source-authorized attempts; no additional payload reaches independent receiver. No Docker/native freeze or billing claim. |
| Trusted peer stalls | A rejected peer must not take the bounded worker slot or wait for a request header. Four authorized incomplete handshakes may use existing slots; wrong peers must still reject before header/admission. |
| Cleanup/secrets | All exact owned processes/listeners close; temporary capability/private key disappear; credentials absent from artifacts; source hashes stable. SQLite working-pool recovery is writable, archived integrity checks copy-only. |

Cloud acceptance remains separate: inspect actual interface binding, registered
relay IP/namespace and observed source after Docker routing/NAT. A researcher and
an unrelated inner container (including one with the local capability) must not
appear as the permitted relay peer. If NAT collapses their sources, peer IP alone
is not an identity boundary: stop/no-go until a compatible isolated ingress exists.
No local result proves that topology or grants cloud policy/trust clearance.

Additional exact-peer discriminator: on a fresh pool keep the same assigned listen
address but configure a different RFC1918 relay peer used only as a negative test
value. The real local source that equals the listen address must now reject with
zero admission/upstream. This verifies that listen-address equality cannot replace
the explicit relay-peer predicate when only one assigned RFC1918 interface exists.

Review-discovered availability boundary before repair: wrong-peer rejection must
not append SQLite audit events. Otherwise untrusted clients can exhaust the audit
cap and close provider admission without passing capability. Stage 4096 short
wrong-source connections before any positive, recording only aggregate outcomes;
require no events/tunnels/charged-byte change, no upstream activity, no provider
REVOKED and a surviving positive. Preserve the original logging failure before
removing the unnecessary DB write. Per-source denial is close-only; independent
TCP/ledger/receiver evidence supplies the E2E proof.
