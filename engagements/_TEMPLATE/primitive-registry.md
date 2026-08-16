# primitive-registry.md — confirmed fragments awaiting composition

Every capped, partial or refuted-at-the-top primitive stays here as a **fragment**. Depth comes from
composing fragments across rounds; a fragment that is not written down cannot compose with anything.

Added to the template 2026-08-16. An audit found this registry held 11 rows in
`obyte-ocore-2026-08` and **1 row** in `angular-dev-infra-2026-08` — the CI/supply-chain engagement,
where composition is the characteristic bug shape, and where the round ledger recorded at least six
textbook fragments that never reached the registry.

| # | Primitive (what you can make happen) | Confirmed by | Preconditions | Composes with | Status |
|---|---|---|---|---|---|
|   |                                      |              |               |               |        |

Rules:
- A primitive is a **capability**, not a finding. "I can overwrite an arbitrary path under
  $RUNNER_TEMP" is a primitive. "Path traversal in the deploy action" is a finding.
- Record it the moment it is confirmed, even when its own impact is nil. Nil-impact primitives are
  the ones that compose.
- `Composes with` is filled in on a later pass. Leaving it blank is fine; leaving the row out is not.
- Every finding that gets capped contributes its proven rungs here before the cap is recorded.
