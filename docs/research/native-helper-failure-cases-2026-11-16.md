# Native helper failure cases

Defined before implementing the shared Codex and OMP helper session bridge.
These direct contract checks do not claim a live native runtime run.

| Case | Required observation |
| --- | --- |
| Spawn under an active parent | Host creates the child identity; its controller principal, permissions, effects and optional limits match the parent. |
| Forged or stale child identity | Reject before reading or mutating parent state. |
| Helper activity and accounting | Each admitted helper invocation/usage delta is counted once under the parent; duplicate cumulative usage does not double count. Overlapping elapsed time is not added to parent elapsed time. |
| Reviewer isolation | A helper cannot create or satisfy an independent reviewer identity. |
| Parent stop or revoke | Stop every child and the owned parent runtime; no child action remains admitted. |
| Child stop or exit | Release that child without revoking siblings or the parent. |
| Omitted optional total limits | Helper work has no hidden total deadline; machine limits, explicit operator stop and renewable short leases still apply. |
| Recovery | A lost helper is reconciled before retry; uncertain effects are not repeated as if absent. |

The check is limited to local identity, accounting and stop-state behavior. It
does not claim provider usage accuracy, native Codex/OMP interoperability or
long-running continuity.
