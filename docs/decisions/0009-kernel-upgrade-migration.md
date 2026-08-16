# 0009 — Kernel upgrade path: decision-0005 → decision-0006 with orphan reconciliation

**Status:** accepted (2026-08-09, operator-authorized)

## Problem

An existing decision-0005 engagement (`spotify-backstage-2026-07`) has 7 confirmed findings and 19
report drafts that cannot be registered in its record kernel. The current CLI has **no path** to move
a decision-0005 engagement to decision-0006:

1. Every finding/report/close command (`revise-finding`, `accept-report`, `generate-report`,
   `record-review`, `close`) requires the decision-0006 kernel (`_require_decision6_kernel`,
   `run-engagement.py:226-230`).
2. The scope-amendment commands (`propose-scope`, `reattest-scope`) are also decision-0006-gated
   (`run-engagement.py:355,368`) — a chicken-and-egg: you cannot re-attest to 0006 because
   re-attestation requires 0006.
3. `reduce_engagement` is additionally blocked by two orphan classes: 19 unbound `reports/*.md`
   drafts (report-file orphans) and 66 unregistered `evidence/**` files (artifact orphans).
4. `migrate` also requires a decision-0006 source scope (`run-engagement.py:747`).

## Decision

Add a single authority-tier command **`migrate-kernel`** that moves an engagement from decision-0005
to decision-0006 and reconciles the orphan state in one operator-signed operation. Model: `init`
(which creates the first `scope.attested` event via a direct operator-console signature, not async
authority) combined with the re-attestation event shape from `command_reattest_scope`.

**Command contract (authority tier, operator role, operator-console signature):**

1. Validate the engagement's current kernel is `decision-0005-v1` (upgrade-only; refuse if already
   0006, if unattested, or if the draft does not select 0006).
2. Take the operator-signed `--draft` scope.md (must select `decision-0006-v1` and the same operator).
3. Reconcile orphans so the post-migration reduce passes:
   - Register unregistered `evidence/**` files as artifacts (clear_local, digest-bound) — bulk,
     without per-file classification events (the migration command itself is the authority).
   - Move unbound `reports/*.md` drafts to `report-drafts/` per decision-0006 §7.1 ("report drafts
     belong in report-drafts/"), preserving bytes and recording a migration note.
4. Write the new scope.md, persist the scope snapshot, and append a `scope.attested` event with
   `record_kernel: decision-0006-v1`, `supersedes_scope_hash` = the prior 0005 hash, actor = operator,
   `operation_class: authority` — via `_append_kernel_event` (which reads the ledger directly, not
   reduce, so the pre-migration orphan state does not block the append).
5. `reduce` + write snapshot + views; emit the new scope hash.

**Why operator-console signature and not async authority:** the async-authority path
(`request-authority`) itself calls `reduce_engagement` (`run-engagement.py:416`), which fails on the
orphans — so it cannot bootstrap. `init` establishes the authority boundary with a console signature
without async authority; the migration is the same shape (one authoritative event by the signed
operator) and does not lower the bar: the operator's SSH signature over the canonical challenge is
required (`_require_operator_console`-style verification against the draft's signer binding). The
signature is checked against the **draft** scope's `Operator allowed signers SHA256` binding, because
the draft is what becomes the new attested scope — the migration introduces the binding exactly as
`init` does for a new engagement. Post-migration, all decision-0006 commands work through the normal
async-authority path (now that reduce passes).

**Why `migrate-kernel` is a distinct command, not a `reattest-scope` relaxation:** reattest-scope
consumes an async authority request and requires the decision-0006 gate by design; silently relaxing
that gate would let any decision-0005 engagement re-attest without the operator-facing migration
record. A dedicated command makes the upgrade an explicit, documented, operator-signed operation.

## Why not alternatives

- **Accept current state (Option B):** leaves `findings: None` in the kernel forever; rejected by the
  operator.
- **New decision-0006 engagement (Option C):** needs a decision-0006 source to migrate from; same gap.
- **Manual scope.md edit + ledger append:** violates append-only and would bypass the authority
  machinery; rejected.
- **Per-file artifact preflight + async authority for every step:** requires `reduce` to pass first,
  which the orphans block; a 66+66 step process; rejected as unbounded.

## Consequences

- The migration is one bounded, operator-signed, digest-bound operation.
- Post-migration, the standard decision-0006 flow works: `revise-finding` ×7, `generate-report` +
  `accept-report` ×7, `close`.
- The orphan evidence artifacts are registered with the migration as authority (their digests are
  bound); the report drafts are preserved in `report-drafts/` (bytes unchanged).
- Conformance must stay green; a self-test must cover: refuses non-0005 source, refuses non-0006
  draft, requires operator signature, registers evidence orphans, moves report drafts, appends the
  0006 attestation, and reduces cleanly afterward.

## Open items

- The `close` gate requires a memory disposition (`record-memory`) and a coverage terminal state;
  these are operator steps after registration.
- The migration does not invent findings or claims; it only switches the kernel and reconciles
  orphan state. The 7 findings are registered afterward via the standard `revise-finding` flow.
