# Decision 0011 — Depth over provability: partials, primitives, external calibration, and where the ceiling actually is

> **Status:** Superseded by [ADR-0017: Ajar v3 Dual-Mode Architecture](0017-ajar-v3-dual-mode-architecture.md) (2026-11-18).
> Retained as an immutable historical decision record. Active agents and contributors MUST NOT follow paths, schemas, or workflow rules defined in this document.


**Status:** accepted; implemented (partials, `ceiling-requests.md`, `primitive-registry.md`,
disposition ledger)\
**Date:** 2026-08-16\
**Effect:** records why the harness was measured for excess rigor, what the measurement found, and
the three changes it produced. Extends Decision 0010. Supersedes nothing.\
**Related:** `engine/finding-lifecycle.md` §5b §5c, `tools/disposition_ledger.py`,
`schemas/disposition.schema.json`, `engagements/_TEMPLATE/{ceiling-requests,primitive-registry}.md`,
`fixtures/preregistration/framing-invariance-OUTCOME.md`

## Context

A peer argued that everyone building AI security tooling optimises for low false positives, and that
this is a trap: *"making your tool's judging phase too rigorous can lead to dropping valid severe
vulnerabilities."* Another reported valid findings dropping ~60% after optimising against false
positives.

This harness is built almost entirely out of rigor. The question deserved measurement rather than an
opinion, and it was asked twice with different framings.

## What was measured

### Round 1 — is severity demoted too aggressively? (2026-08-12, 4 reviewers)

**No, at the level of individual findings.** All seven spotify demotions were evidence-backed, each
citing a falsifiable external anchor — a real GHSA verified live, an upstream maintainer statement,
Backstage's own threat model, or the program's own policy text. Zero were bare assertions.

A correction to the framing: the four "High" findings were registered by a **fabrication script with
no CVSS vector at all.** "High demoted to Medium" described a move from a fabricated label to a
computed one.

**But the machinery is structurally one-directional**, in three locatable ways: refuters are always
briefed to attack and never to argue upward; kill-side machinery (`regrade`, `pocinator`) is
mandatory while raise-side (`escalation`, `chainability`) is opt-in; and demotion runs no gates.

The deeper finding: **the harness has no counterweight in either direction.** A re-escalation run
under a leading prompt produced four raises, three of which died under a symmetric re-audit. It
reproduced the flaw it was sent to correct.

### Round 2 — does the pipeline select for shallow findings? (2026-08-16, 6 lanes)

Four lanes said calibrated, one said *not rigorous enough*, one said the comparison cannot be made.
**Zero said too rigorous.**

The decisive number: **12 promotions, 1 demotion, zero rows with `blocked_by`** across the entire
repository. The mechanism the peer describes has never fired here.

G6 specifically does not kill chains. `R8` is a five-stage chain — fork-controlled genrule → daemon
overwrites metadata between inject and tar → tar crosses the job boundary → trusted deploy job →
lands in `channelId` — and it passed all seven gates.

### The honest reading

**We have no evidence the gates are well-calibrated. We have evidence they have never had to say
no.** Agents iterate `gates` until clean and then `promote`, so a block never enters the record.
"Zero blocks" is consistent with a well-tuned stack and with an untested one, and this data cannot
separate them.

## Where the ceiling actually is: AUTHORIZATION, not rigor

The highest-value result in `angular-dev-infra-2026-08` is the GCP service-account key → RBE
ActionCache/CAS write → cache poisoning → compromised Angular-org build outputs chain. That is the
Supply-Chain **top band ($31,337)**. It is written out in full in `cascades.md` and marked
*"hypothesis, not claimed"*, because liveness and IAM are Google-side facts and probing them trips
wires 2 and 4.

**Correct about the act. Wrong about the record** — it capped silently instead of asking.

This fully explains the severity ceiling (five post-gate findings, all Medium or Low) without any
appeal to over-rigorous judging. The top band requires demonstrating impact on live third-party
infrastructure, which our own scope forbids.

## Decisions

### 1. Partials live in `unproven/`

`unproven/` was **empty in two of three post-gate engagements**. 100% promote, zero partial. The
designed home for incomplete work existed and nobody used it.

That is how a careful pipeline loses deep findings — **not by rejecting them, but by having nowhere
to put an incomplete one.** If the only two states are "passes seven gates" and "a line in a
hardening note", a three-stage chain with two stages proven evaporates.

A partial declares `stages` (`proven` / `argued` / `refuted`) with `what_would_close_it` on each
non-proven stage. It claims no severity above its proven stages and is not promoted. **A hardening
note is a dead end; a partial is a queue.**

### 2. A scope-blocked ceiling is a REQUEST, not a cap

**Operator standing instruction (2026-08-16): scope will always widen if more authorization is what
it takes to prove a ceiling. Always.**

Encoded carefully: **this does not authorize anyone to widen it.** The five wires are unchanged and
the acts needing a fresh confirm still need one. What changes is that a ceiling held down only by
authorization gets a row in `ceiling-requests.md` — the ceiling, the band, the exact act, the wire
tripped, what is irreversible, the cleanup path — stated precisely enough to answer in one reading.

*A ceiling nobody asked about is a finding we chose not to have.*

### 3. Primitives get registered as they are confirmed

The primitive registry held 11 rows in obyte and **1 row in dev-infra** — the CI/supply-chain
engagement where composition is the characteristic bug shape, and whose round ledger recorded at
least six fragments that never reached the registry.

A primitive is a **capability** ("I can overwrite an arbitrary path under `$RUNNER_TEMP`"), not a
finding ("path traversal in the deploy action"). It is recorded the moment it is confirmed, **even
at nil impact** — nil-impact primitives are the ones that compose. Every capped finding contributes
its proven rungs before the cap is recorded.

### 4. External verdicts are the only ground truth, and they must be recorded

Four reviewers read every engagement record and concluded almost nothing had been filed. The
operator then said findings HAD been filed and adjudicated across four programs. **Both were right:
reports went out, the repository did not know.** Every argument in that audit was the harness
grading itself.

`schemas/disposition.schema.json` + `tools/disposition_ledger.py` record one external verdict per
filed finding. The measurement is the **severity delta** — our band minus theirs.

Design points that matter:

- **`our_severity` is never back-edited** to match the vendor. It records what we believed before we
  knew; rewriting it erases the only signal in the file.
- **`outcome` and severity are separate**, because they dissociate: Klever closed our report
  not-accepted *while publishing their own advisory crediting us as reporter*.
- **`novelty` is separate from `outcome`.** A duplicate is the program confirming the bug is REAL
  and that someone filed it first — a **novelty failure, not a validity failure**. Duplicates
  validate DETECTION; only non-duplicates test SEVERITY calibration. One field would destroy both.
- **`their_rating` keeps the program's own words.** Google speaks in `P2 / S4`, not CVSS bands.
  Mapping loses information, so the original is kept.
- **Below 5 graded records, `calibrate` issues no verdict.** A confident answer over too little
  input is this harness's recurring failure and this is where it would be most tempting.

## Method note: preregistration, and a rule that was wrong

The framing-invariance probe fixed its metrics before any grader ran, and named the result that
would refute the operator's thesis as a live possibility.

Run 1 was invalidated — the packets leaked bare scores and the audit's own narrative, and graders
anchored on them. Run 2 found **14 of 15 cells unmoved by framing**.

The preregistered rule then declared "framing bias confirmed" on a **single flip**, because it
carried no minimum flip count. **The rule was not amended retroactively.** The outcome document
scores run 2 against the rule as written and records that the rule is wrong; a 3-flip minimum
applies from run 3 onward, declared before that data exists.

Two lessons kept: **redaction that announces itself is not redaction** (15/15 graders detected the
redaction markers), and a preregistered rule needs a floor for the same reason the ledger does.

## What remains deliberately flexible

- Whether the OSS-VRP scope widens to reach the Supply-Chain top band is an operator decision per
  ceiling, not a standing posture.
- The gates' calibration is unmeasured until one blocks a candidate later confirmed real.
- Depth instrumentation (partials, primitives) is now available; whether it changes outcomes is the
  next thing to measure, not to assume.
