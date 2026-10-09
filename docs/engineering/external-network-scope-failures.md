# External network-scope enforcement: failure inventory

Recorded before implementation on 2026-09-22.  The acceptance workflow is
`tools/external-network-scope-test.py`; its saved results belong under
`artifacts/external-network-scope/`.

1. The queue creates a non-internal bridge (`network_internal=False`), so descendants have
   ordinary Internet egress.
2. The inherited seccomp filter does not classify `socket`, `socketpair`, `connect`, `sendto`,
   `sendmsg`, or `sendmmsg`.  IPv6, UDP, raw/packet/netlink/vsock sockets and TCP Fast Open are
   therefore available.
3. A descendant can connect directly to a host IP or `host.docker.internal`, bypassing HTTP proxy
   variables and the semantic action broker.
4. Continuing a notified `connect` after checking tracee memory would be raceable by a sibling;
   the sockaddr must be copied once and the exact duplicated socket connected by PID 1.
5. Real provider credentials and the configured provider URL are currently copied into the model
   environment.  A worker can read and reuse them outside the intended provider operation.
6. There is no fixed provider method/host/path proxy, request/response bound, request budget,
   redirect rejection, deadline, streaming preservation, or parent-owned egress audit.
7. There is no typed target-fetch operation.  Adding a generic URL fetch would let the worker turn
   the broker into an SSRF primitive; authorization must instead come from an exact network-policy
   block in the current signed scope and the current admission/state binding.
8. DNS results are not resolved, filtered, pinned, and rechecked per connection.  Redirects and
   alternate textual forms can therefore cross a destination boundary unless the parent gateway
   validates every hop and rejects non-global aliases.
9. Fork/exec inheritance, descriptor hygiene, listener lifetime, timeout, parent death, stale
   admission, and scope-policy tamper behavior have no network-specific qualification evidence.
10. Existing fake-provider tests do not prove real Anthropic authentication.  That qualification
    remains separate; the current host probe is blocked by `403 oauth_not_allowed_for_organization`.
11. An IP listener or inherited connected/listening descriptor would let a descendant reply to an
    inbound peer without a new `connect`; `bind`, `listen`, `accept`, and `accept4` therefore need
    the same inherited syscall boundary and launch-time descriptor hygiene.
12. A fixed provider origin is not sufficient when the Messages body can enable provider-side web
    fetch, web search, code execution, a remote MCP connector, remote image/document sources, or
    future server tools.  The parent must parse duplicate-safe JSON and admit only inference plus
    ordinary client-side tool schemas before contacting the provider.

The workflow checks the positive control and each negative control independently.  A denied case
passes only when the denied sink observed zero requests; a client-side error alone is insufficient.
