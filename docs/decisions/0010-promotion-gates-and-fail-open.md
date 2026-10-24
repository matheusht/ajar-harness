# Decision 0010 — Promotion gates: default-reject, computable where possible, and the fail-open lesson

**Replacement draft: [0013](0013-canonical-filing-contract.md); #85 remains incomplete.**
The package writer and gate classifications below are historical rationale. The
local draft refuses legacy promotion; any role may
still demote a legacy package. Current GQ/GK/G0–G6 applicability and mechanical,
signed-review and heuristic distinctions live in `engine/finding-lifecycle.md`.


**Status:** accepted; implemented (G0–G6 live, Phase 9 complete for G1/G2)\
**Date:** 2026-08-16\
**Effect:** records the gate stack that governs promotion, why each gate exists, and the recurring
defect class that nearly made the whole stack decorative. Extends Decision 0004 (autonomy) and 0005
(evidence state). Supersedes nothing.\
**Related:** `tools/finding_lifecycle.py`, `engine/finding-lifecycle.md`,
`tools/adjudication_audit.py`, `tools/score_finding.py`, `docs/engineering/002-decisions.md` (D-05),
`fixtures/preregistration/obyte-gate-validation-OUTCOME.md`

## Context

Until 2026-08-09 a finding was created directly in `findings/` and carried its own status field. The
run that produced the finding also set the field. On 2026-08-09 a script set `claim_state: supported`
on seven spotify-backstage findings and nothing objected, **because nothing had to**.

That is a default-accept pipeline. Every check that does not run is a silent pass, so a broken
unattended run produces confident garbage and looks productive.

## Decision

**A finding has a LOCATION, not a status.** It is written to `unproven/`. It reaches `findings/`
only by running `promote`, which runs gates that can each say no. A broken unattended run now
produces nothing, which is visible and harmless.

### The gate stack

| Gate | Asks | Kind |
|---|---|---|
| G0 | every path the package cites exists | computable |
| G1 | the primary attempt resolves to a real execution that **signalled** | computable + attestable |
| G2 | a **distinct** negative control resolves to **held/no_signal** | computable + attestable |
| G3 | the proven execution context is no more privileged than the claim | computable |
| G4 | the adjudication is judgement, not generation | computable |
| G5 | a claimed severity carries a CVSS vector that recomputes | computable |
| G6 | the impact-bearing state was **reached**, not written | attestable |

Two gates were bought by specific failures and are worth stating:

**G3** — ZSec documented a named pipe that looked exploitable from SYSTEM and was unreachable as a
standard user. G3 cannot decide whether a proof really ran unprivileged; it decides that the package
DECLARES both positions and that they agree.

**G6** — `obyte-2026-08-004` answered G3 honestly and still promoted a false impact, because its PoC
wrote itself into a `count>=30` fee window the real network cannot reach. G3 asks WHO the attacker
was; **G6 asks whether the situation they attacked can occur at all.** The same class had already
killed a Kubernetes finding built on a fake client, and a crash PoC in that same engagement.

G6 is scoped to the **impact-bearing** state only. Background seeding is permitted but must be
itemised with a `reachability_basis` per element. This is what lets `obyte-2026-08-003` pass — it
seeds a private asset by direct INSERT, but the defect step ran through the real validator — while
`004` blocks.

### Computable beats attestable, and we convert where we can

An attestable gate reads a string the package wrote about itself. A computable gate resolves that
string against something the package does not control. Phase 9 converted G1 and G2: both now index
`attempts.jsonl` and require the primary to resolve to a signalling record and the control to
resolve to a held/no-signal one, role-disjoint. Together they make *"this fired and the control did
not"* computable rather than asserted.

**G6 remains a pure string check.** It is the odd one out and is the next conversion.

### Asymmetry between promote and demote is deliberate, and its justification is now known to be incomplete

Promotion runs seven gates. Demotion requires a reason string. The stated rationale was that a wrong
demote costs a re-review and a wrong promote reaches a vendor.

**An audit found the re-review does not exist.** Nothing reads `lifecycle.jsonl` back, and there
were zero re-promotions in repo history. The asymmetry is retained because false positives really do
cost more, but the justification is recorded here as *known incomplete* — the counterweight is
scheduling a re-review, not blocking the kill.

## The failure class this decision exists to name: FAIL-OPEN

Four separate instruments failed by returning a pass when they had not run:

1. `adjudication_audit.load_reviews` used `os.listdir`. Pointed at an engagement root it found zero
   reviews and printed `VERDICT: CLEAR`.
2. G4's corpus arm looked for `<engagement>/reviews/` — **a directory no engagement has ever had.**
   It was added specifically to catch the spotify fabrication and was dead from the day it shipped.
3. `fixtures/lifecycle-corpus` was built with a top-level `reviews/` dir. **The fixture was shaped to
   the code instead of to the world**, so conformance was green while the feature did nothing.
4. The framing probe's `verify` reported CLEAN on five packets that still carried bare CVSS scores
   and the audit's own narrative, because **it looked only for what the scrubber already removed**.

### Three rules, each paid for

1. **An instrument must fail CLOSED on empty input** when the input cannot legitimately be empty.
2. **A fixture is authored from a real directory's shape.** If you invent the layout, you are
   testing your own assumption.
3. **A verifier built from the same list as the thing it verifies is not an independent check.**
   Validate every repair against data with known ground truth — the repaired walker was confirmed by
   pointing it at spotify-backstage's known-fabricated 15-review corpus and getting `SYNTHETIC`.

### The exculpatory rule, and its own correction

A corpus whose verdicts are all rejections is not manufacturing findings, so it must not block a
promotion. The first version of that rule zeroed every signal and returned `clear` — meaning a
corpus firing all seven signals, fatal ones included, passed purely because it rejected. **That is
the shape of findings killed without review**, and it was written on the same day the operator asked
whether the harness over-kills.

The verdict now splits: `synthetic` (generated confirmations, blocks) and `rejections-unreviewed`
(blocks nothing, never reported as clear).

## G0's scope, ruled on evidence

G0 flagged two shippable packages on cited-but-missing paths. Splitting the cases:

- `pr.yml` and obyte's five evidence logs were **real gaps** — cited with line numbers, never
  packaged. Fixed by shipping them.
- `action.yml` was **G0 over-matching**: every composite action's file carries that name, and the
  package shipped them disambiguated.

**Ruling:** G0 resolves a citation against the package at any depth, by basename. It does not invent
matches — a cited `action.yml` still fails when the package ships `action-browserstack.yml`, because
there is genuinely no `action.yml` in the zip.

## How future agents should act

- Never write into `findings/` directly. `cmd_promote` refuses a source outside `unproven/`.
- If no reviewer ran, do **not** write a review record. An unwritten review is an honest gap; a
  written one describing nothing is fabrication, and this harness has caught that twice.
- Declare `state_provenance` honestly. `synthesized` blocks, and that is the point — the block
  message offers capping the claim to what the real path shows.
- When adding any check: ask what it returns when its input is missing. If the answer is "pass",
  it is broken.

## What remains deliberately flexible

- G6's conversion from attestable to computable is intended, not scheduled.
- The promote/demote asymmetry stays until a re-review mechanism exists to justify it.
- Gate *count* is not a target. A gate that has never blocked anything is unproven, not proven —
  across twelve promotions the stack has blocked zero, which is measured in Decision 0011.
