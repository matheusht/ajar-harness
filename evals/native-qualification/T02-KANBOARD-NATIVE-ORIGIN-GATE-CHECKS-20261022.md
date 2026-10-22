# Kanboard native origin admission: checks before code

This is a narrow, provider-free integration guard for #158/#159. It consumes
host-owned dispatch, observer-window, and sanitized native-event records. It
does not run Kanboard, deliver credentials, trace a process, or qualify a native
request. The existing local socket-to-PID experiment showed that a host
`docker exec` can make an OpenCode process appear under PID 1; container IP,
socket owner, executable name, and PID ancestry cannot establish tool origin.

The decision is to refuse original-observation credit until a separate,
independently qualified host credential route and complete native tool/process
producer exist. A transport proxy or host client can support local controls,
but its request must be labeled host-authored. The check is deliberately
negative-only; no caller-supplied "qualified" flag can make it pass.

`tools/native_kanboard_origin_gate.py::assess(window, dispatch_before,
dispatch_after, native_trace, host_exec_audit=None)` is the proposed seam.
All inputs must come from the host-owned `controls` tree, outside every
researcher/reviewer/resume mount. The caller must independently verify that
tree's ownership and frozen bytes before invoking the function. The function
returns only fixed codes and non-secret IDs. It never accepts raw credentials,
requests, responses, tool input/output, or app rows.

| ID | Failure or false proof | Required result |
| --- | --- | --- |
| O01 | Missing/extra fields, wrong kind, malformed ID or digest | Fixed `invalid_evidence` hold; never publish a positive claim. |
| O02 | Window is from another dispatch, session, role, target, or pre-dispatch bytes | Fixed `binding_mismatch` hold. |
| O03 | Dispatch was not durable `unknown_effect` before execution, or its later ACK is absent/mismatched | Hold. An ACK proves native completion only, not an app effect. |
| O04 | Native trace is absent, belongs to another session, lacks a completed tool event, or declares a tool error | Hold. Tool names and input/output hashes are corroboration only. |
| O05 | App receipt, matching source IP, socket inode/PID, or PID 1 ancestry is offered without an independent full process/host-exec audit | `native_origin_unproven` hold, even when all supplied records match. |
| O06 | Extra host exec overlaps the window, audit is incomplete, or audit bytes are caller-authored | `host_exec_overlap` or `native_origin_unproven` hold. No inference from an empty list. |
| O07 | Credential route is missing, merely claimed, or a cookie/password/header reaches OpenCode input, mount, trace, or native store | `native_credential_route_unavailable` hold. No secret-bearing field is accepted by this interface. |
| O08 | A host replay or native-origin claim is supplied as an override | Ignore the override and hold; this function has no positive branch. |

Write a provider-free assert-based checker before implementing the function.
It must exercise a valid shaped record, each binding mutation, stale/missing
trace, fake completed tool, extra host exec, and attempted positive override.
The expected result for every case is a hold with `native_request_attributable:
false`. The checker uses synthetic IDs/hashes only and makes zero Docker,
provider, or target calls. A later human E2E must supply the independent
credential and process producers before this gate can be replaced by a
positive admission path.

Run from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 evals/native-qualification/smoke/check_native_kanboard_origin_gate.py
```

Observed in this isolated PR188 checkout: `PASS: 13 provider-free origin holds;
Docker/provider/target calls: 0`. The integration must retain the exact
pre-dispatch bytes separately: the current candidate runner rewrites its
dispatch JSON when it acknowledges a turn, while the observer window binds
the original pre-dispatch digest. A post-run reconstruction of those bytes
would not meet this check.
