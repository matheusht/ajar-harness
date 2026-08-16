# promotion-notes.md — what promotes, what stays local, sanitization sign-off

Draft for casebooks/case-2026-08-dag-ledger-consensus/ (promotion is manual + operator-reviewed;
this draft is staged at evidence/roundE4/casebook-draft/).

## Promotes to Plane-1 pattern cards (with the reachability caps recorded)
- **PC-2 → pattern.dag-old-dag-rule-gating** (authored this engagement, conformance green).
  Promote the REACHABILITY CAP as part of the card: the old-DAG attachment vector is blocked at
  execution by stabilization mechanics (witnessed level ancestry-derived; best-parent sorts by it;
  MC walks from the tip) — the card's probe list must include the stabilization check, or future
  users will chase dead windows. The migration-completeness audit method (grep both sides of a
  rule boundary for the disjunct) is the card's reusable procedure.
- **PC-3 → new pattern.verification-root-not-anchored** (or fold into
  pattern.dag-canonicalization-split). Confirmed finding F1. The general shape: any verification
  predicate whose truth anchor is prover-supplied (Merkle root, aggregator, commitment) is
  vacuously satisfiable; the fix pattern is binding the anchor on-chain. The contrast sibling in
  the same codebase is the teaching case.
- **PC-5 → new pattern.bearer-token-uniqueness-party-keyed** (or extend
  pattern.dag-spend-proof-uniqueness). Confirmed finding F3. The general shape: a uniqueness
  registry keyed on a claimable identity instead of the committed value. The sound-sibling
  contrast (payload-side owner binding) is the teaching case.

## Stays engagement-local (no promotion)
- PC-1/PC-4 (uncaught-throw pattern): real and generalizable, but all four sites are unreachable
  today → defer; revisit if a reachable instance appears or as a defensive-engineering pattern.
  The async iterator-vs-completion boundary lesson (L-8) goes to field-notes.
- F4 mechanism (fee-curve design note): the exp() settlement has no balance-relative cap — a real
  design hazard if a future stabilization change re-opens the window; keep as a hardening note +
  field-notes lesson (L-3), not a pattern card.
- The quarantine candidates (Q-1 device-layer crash, Q-2 multisig wallet DoS): wallet/adjacent
  surfaces; operator scope decision first; they would promote to a device-layer/pattern card only
  after a scoped engagement demonstrates them in the target class.

## Lessons → docs/field-notes.md (draft list)
L-1 (synthesized-state reachability), L-2 (escalation refutes its own finding), L-3 (settlement
ordering vs window claims), L-4 (execute SQL claims), L-5 (defense-commit routing), L-6 (blind
round), L-7 (bearer-token keying), L-8 (async throw boundary). Each is abstract and portable as
drafted in lessons.md.

## Sanitization sign-off (draft)
- Stripped: target name beyond the DAG class, all unit/address/hash literals, the pinned commit
  id, evidence file paths (replaced by engagement-local labels F1/F3/F4 and surface names).
- Retained: abstract shapes, file-level mechanism descriptions, severities, the refutation trail.
- Verification: grep for base64 literals, 44-char hash-shaped tokens, and URLs in the draft files
  — zero hits (see the acceptance report). No live ids, tokens, passwords, or signed URLs.
- Status: DRAFT — requires the operator's review + a human promotion pass before moving into
  casebooks/ (per engine/finding-lifecycle.md and docs/decisions/0001).
