# winners.md — scrubbed, abstract, benign-objective patterns only

Append-only **evidence**, never self-edited belief. Store the *shape* of what worked, linked to
evidence ids — **never** verbatim payloads or stepwise harmful recipes. This file remains local;
models do not write Plane-1. Promotion requires a committed operator-reviewed `promote` disposition
and a later human-reviewed PR. Negative controls, refutations, reward-hacked proof shapes, and
environment failures are legitimate lessons; promotion is never forced.

## Format
- **pattern:** `<abstraction — the shape, not the phrasing>`
- **applies to:** `<surfaces>`
- **evidence:** `finding://...  attempt://...`
- **loses to:** `<defense observed>`
- **scope tag:** `benign-canary-only | defensive-validation-only | operator-review-required`

## Entries
- (none yet)
## Standing engagement gate (operator, 2026-08-11) — MAX-IMPACT PoC + INDEPENDENT RUN
- **pattern:** every finding must ship with a maximum-impact runnable PoC (blast radius demonstrated to the ceiling inside the authorized local environment, per scope.md §7), AND that PoC must be run from an independent reviewer's perspective after it is fully built and testable — the reviewer executes the PoC themselves, reads RAW output (never the builder's summary), and confirms the claim tuple (target/entry/precondition/mechanism/effect/negative control/impact). Builder and reviewer must be different contexts; reviewer is fresh-context.
- **applies to:** all findings that reach `unproven/` in this engagement.
- **evidence:** `engine/pocinator.md` (claim tuple, lens 10 self-attestation-is-not-evidence); `engine/escalation.md` §3 (re-run PoCs in your own hand; a builder's PASS is not ground truth).
- **scope tag:** operator-review-required (standing).
