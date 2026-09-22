# Canonical filing activation failure matrix

Issue #85 implementation contract. These checks precede the implementation.

| Case | Required result |
| --- | --- |
| Arbitrary `finding_lifecycle.py promote --actor ...` | Never creates active membership or moves a package. |
| Package-only gate invocation | Advisory inspection only; cannot activate. |
| Empty/missing kernel ledger or ambient waiver | Cannot activate. |
| New filing through the historical action contract | Rejected; historical ledgers still replay with their original semantics. |
| Direct v3 file or `record.committed` write | Stored/inert until the exact signed activation commits. |
| Positive claim missing typed privilege evidence | Rejected. |
| Positive claim proved from more privilege than claimed | Rejected. |
| Positive claim with synthesized/not-established impact state | Rejected. |
| Non-informational severity without a recomputable CVSS 3.1 vector and score | Rejected. |
| Generated-confirmation signature in the applicable committed review corpus | Rejected by computed G4; this corpus heuristic remains distinct from exact independent adjudication. |
| Refuted or contaminated claim | May be stored and activated through signed authority without successful exploit proof; severity remains informational. |
| Interruption after revision bytes, before record commit | Revision remains inactive; identical retry commits once. |
| Interruption after record commit, before activation | Revision remains inactive; identical retry activates once. |
| Concurrent/duplicate retry | One activation event and one active revision. |

Repeatable workflow checks:

```sh
./.venv/bin/python tools/filing-activation-test.py
./.venv/bin/python tools/run-engagement.py --self-test
```

The first isolates adversarial evidence predicates. The second exercises historical replay, public
activation, raw-writer denial, interruption at both durable boundaries, and idempotent retry.
