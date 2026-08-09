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

- **pattern:** `a refutation resting on a generic validation layer does not stand until the
  resource-specific opt-out has been checked`
- **applies to:** white-box source audit; any regrade that refutes a claim by citing a shared or
  generic code path rather than the path the claim actually traverses
- **evidence:** `memory-disposition-r4-kiwicom-vs02-reversal-and-verification`;
  finding `vs02-foreign-secret-overwrite`; review `vs02-foreign-secret-overwrite-regrade`
- **loses to:** a refutation that already names the resource-specific strategy and rules the opt-out
  out; a verification run against the real component rather than a fake client
- **scope tag:** `operator-review-required`
- **ablation:** `fixtures/ablation/kiwicom-vs02-layer-check/` — executable. Removing the lesson flips
  the historical VS-02 case from `reopen` to `stands`. Two controls do NOT flip, which is what
  separates a rule from a blanket reopen.

**Why this entry exists and the others do not.** The disposition that authorised this promotion was
recorded on 2026-08-08 and passed every schema gate, and this file still read `(none yet)` afterward.
The promote step had no next step. `tools/ablation.py check-dispositions` now refuses a `promote`
that cannot demonstrate a changed verdict.
