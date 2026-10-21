# Owned original-application observation failure checks

Frozen 21 October 2026 before implementation. These checks cover one harmless,
local, synthetic application. They authorize no provider, model, CI, engagement,
external target, or shared-launcher call.

## Candidate and evidence boundary

The smallest locally testable candidate is an exact spawned process subtree
traced only for network `connect` syscalls, joined one-to-one with a separate
host-owned application receipt. The producer runs in a user/pid sandbox whose
private `/tmp` hides the host observer path. Its exact `lstat` probe must return
`FileNotFoundError` (`absent`); `inaccessible`, `present`, or any observer write
fails. The trace captures no reads, writes, request bodies, commands,
environment, or credentials. Raw trace and response bytes are ephemeral;
durable evidence is a bounded sanitized projection. Pattern scanning is only
defense in depth: the caller remains responsible for supplying sanitized input.

The frozen case inventory and outcome expectations below belong only to the
owned checker. The core evaluator accepts arbitrary sanitized application cases
and portable chain state; it validates attribution, ordering, state references,
observer protection, source-manifest integrity, stop, and cleanup invariants
without requiring these fixture IDs.

A same-container proxy, access log, source IP, host replay, or final effect alone
does not prove original researcher activity. The candidate qualifies only the
owned dispatch fixture. It does not establish OpenCode process attribution,
agent discovery, model/provider behavior, route enforcement, or a live target.

## Frozen failures

The run fails, or refuses the capture claim where stated, if any predicate below
is observed:

| Failure | Exact predicate |
| --- | --- |
| `source_pin_mismatch` | The handoff/base/source file identities differ from the frozen inputs. |
| `observer_unavailable` | The independent local receiver does not start or does not return its real result. |
| `observer_channel_exposed` | The observer path's exact producer-side `lstat` result is anything other than `absent`, or an observer write succeeds. |
| `trace_incomplete` | The exact spawned subtree is not traced to exit, a trace record is unfinished, any connect syscall is omitted, or the admitted application-connect cardinality is not one. |
| `session_binding_missing` | A researcher dispatch lacks its non-secret session binding. |
| `tool_binding_missing` | A researcher dispatch lacks its tool-call binding or normalized request-intent digest. |
| `request_binding_ambiguous` | Zero, duplicate, or mismatched observer receipts can satisfy an ordinary researcher dispatch. |
| `host_replay_miscredited` | A host-authored request is classified as researcher-originated or discovery. |
| `host_activity_in_researcher_window` | A host client request occurs between a researcher dispatch's open and close events. |
| `causal_order_invalid` | Dispatch, application receipt, effect, and completion are not strictly ordered. |
| `authorized_result_mismatch` | The authorized read does not return the independently observed authorized/no-effect outcome. |
| `denied_effect_changed` | A denied request changes application state or is not independently observed as denied. |
| `unexpected_route` | The traced request reaches a route outside the declared observer route. This must produce `capture_claim_refused`. |
| `capture_completeness_unproven` | The run claims complete capture, or a bypass refusal lacks its explicit application-observer missing transition. |
| `producer_can_write_observer` | The producer can create, replace, or append observer evidence. |
| `sensitive_evidence_detected` | A retained artifact contains raw auth, a cookie, password, capability, request/response body, or secret-bearing URL. |
| `stop_unverified` | A client or listener remains live after its exact stop operation. |
| `cleanup_incomplete` | A raw trace/private scratch path remains, a listener cannot be rebound, or an owned process is still running. |
| `normalized_repeat_mismatch` | A second clean run differs after removing run-specific PID, port, nonce, and monotonic values. |

Unknown or inaccessible evidence never passes as zero activity. Missing process
attribution returns `unavailable`; an observed direct bypass returns
`capture_claim_refused`.

## Frozen owned E2E

The public check runs twice from fresh mode-0700 scratch and requires the same
normalized result:

1. Preflight exact source pins, `strace`, bubblewrap user/pid isolation, and the
   two host-owned loopback listeners. No external address is permitted.
2. Send an otherwise valid host replay while no researcher dispatch exists. It
   must have an application receipt but remain `host_replay` and never discovery.
3. Trace one exact sandboxed process subtree for an authorized read. Require one
   matching connect, one receipt, host idle, exact session/tool/intent binding,
   an authorized result, and no effect.
4. Repeat for a denied state change. Require denial and unchanged state.
5. Repeat for an allowed local effect, then for a read that consumes the exact
   produced state. Preserve both state digests and the transition.
6. Trace a direct request to the separately inventoried bypass listener. Require
   no main-observer receipt, one bypass hit, no state change, and
   `capture_claim_refused` with a missing transition. Stop at any other semantic
   failure.
7. Require the producer's attempted observer-storage write to fail in every
   sandboxed dispatch. Retain no raw body, response, trace, auth, or command.
8. Stop exact clients/listeners, rebind both ports, remove only owned scratch,
   scan retained artifacts, require the exact six portable cleanup categories,
   and compare the two normalized runs. Known failed local name-service socket probes remain
   counted as non-route connects; any other Unix, IPv6, or undecodable connect is
   an admitted unexpected route and fails.

The durable bundle contains portable `hypothesis.json`, `observation.json`, and
`evidence.json` plus their hashes in `result.json`. It preserves produced and
consumed state, contrary results, the bypass's missing transition, unfinished
conditions, source pins, and cleanup status. Runtime/session/tool IDs are
evidence bindings, not hypothesis state.

## Managed integration stop

This lane does not edit or call the shared managed launcher. A later caller must
open a bounded observation lease around the exact native dispatch and supply a
protected process-subtree trace plus the native session/tool event. Until that
caller path is independently qualified, managed native process attribution is
`unavailable`; the owned fixture cannot be relabeled as agent discovery.
