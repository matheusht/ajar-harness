# OUTCOME — framing invariance

Decision against `framing-invariance.json` (`PREREG-20260812-framing-invariance`). Written after the
run. **This document never edits the preregistration.**

---

## Result: INCONCLUSIVE, leaning invariant

The preregistered rule returns `framing-sensitive-directional`. **I do not report that as the
finding**, because the rule fires on a single flip and I wrote the rule badly. See "Defect in my own
decision rule" below.

What the data actually shows: **14 of 15 cells agreed. One moved, and it moved with its framing.**

| finding | neutral | rigor | escalation |
|---|---|---|---|
| F-A2CHAIN | medium | medium | medium |
| F-A2LINK | medium | medium | medium |
| F-F1 | medium | medium | medium |
| **F-F3** | **low** | **low** | **medium** |
| F-OIDC3 | medium | medium | medium |

- flips: rigor 0, escalation 1, total 1 of 10
- directional: `escalation_up` 1, everything else 0

One flip is consistent with framing bias and equally consistent with grader variance. It cannot
distinguish them.

---

## Run 1 was thrown out

Run 1 returned 15 of 15 `medium` — a clean-looking null. It was contamination, caught by reading the
graders' *reasoning* rather than their answers. They cited:

> "the one recorded raise above this level was explicitly WITHDRAWN for resting on a leading prompt
> and misquoted precedent"

> "the dossier's stated PR:H floor (4.9)"

Two leaks, both mine:

1. **Bare scores survived** — `4.9, 6.5, 7.7, 8.1, 8.8, 3.1, 4.3, 7.1, 7.4`. Every scrub pattern
   required an adjacent cue word ("score", "CVSS", a band). A parenthesised `(4.9)` or an arrow
   `6.5 -> 7.1` carries the assessment with no cue at all.
2. **The audit's own narrative survived** — 9 to 11 hits per contested packet. The dossiers had been
   updated after the audit to record the withdrawal, so the packet told each grader which conclusion
   was already discredited.

**And `verify` reported CLEAN on all five.** It looked only for what the scrubber already removed, so
it could only ever confirm the scrubber's own definition of a leak. A verifier built from the same
list as the thing it verifies is not an independent check. This is the third instance of that exact
shape in one week — the two G4 fail-opens and the fixture shaped to the code were the others.

Why the null was worthless rather than merely weak: a heavy steer **saturates** the response. If the
packet says the raise was withdrawn, every grader anchors there and framing has no room to move
anything. A null under saturation is uninformative. A positive would still have counted.

---

## Run 2 is also contaminated, but measurably

**15 of 15 graders set `saw_prior_assessment: true`.** They were right, and the cause is subtle:

**The redaction markers are themselves a signal.** Removing text and leaving
`[adjudication history removed]` announces that adjudication history existed. Graders quoted the
shape of the redaction:

> "the packet leaks that an assessment existed and was changed — `severity [adjudication history
> removed] [assessment change removed]`, `band REVISED to [band removed]`"

> "the existence of a raise-then-rescind is disclosed, and the PR:H / C:H-A:H / S:C-environmental
> fragments may have nudged my metric selection"

No numeric band or score was recoverable — an independent grep audit (not `leaks()`) returned **0
steer hits** across all five v2 packets. But *that an assessment was made and later changed* leaked
through the holes left behind.

**Redaction that announces itself is not redaction.** A future run must either delete the surrounding
sentence entirely, or build packets from documents that never contained a verdict. The confirmation
dossiers are verdict documents by construction, and scrubbing one into neutral evidence is fighting
its nature.

`used_only_the_packet` was true on 15 of 15, and I believe it. The honesty check worked in both runs.
The packet failed in both.

---

## Defect in my own decision rule

The rule reads: *flips occur AND at least two thirds move in the framing's own direction*. It carries
**no minimum flip count**. With exactly one flip, 1/1 is 100% directional and the rule declares
framing bias confirmed on a single observation.

That is over-reading, and it is the same error this harness keeps catching elsewhere — a confident
verdict over too little input. The disposition ledger got a floor for exactly this reason; this
preregistration did not, and should have.

**The rule is NOT amended retroactively.** Run 2 is scored against the rule as written, and the rule
as written says `framing-sensitive-directional`. I am recording that the rule is wrong rather than
quietly changing it to produce the answer I now prefer. A minimum of 3 flips before a directional
verdict applies from run 3 onward, declared here, before that data exists.

---

## What can honestly be said

1. **Framing did not move 14 of 15 cells.** Whatever moves severity in this harness, it is mostly not
   the framing paragraph. That is real evidence against the strong form of the bias thesis, and it
   points at the *argument content* of a pass rather than its tone.
2. **The one flip went with its framing**, and it landed on F-F3 — the finding whose real
   adjudication history also moved low to medium. That is either framing reproducing a genuine
   ambiguity, or residual signal about F-F3's contested status leaking. This design cannot tell them
   apart.
3. **Nothing here licenses a structural change to brief wording.** One flip is not a mandate.

---

## Threats to validity

The five declared in the preregistration all stand. Two more, learned from running it:

- **Redaction markers leak the fact of redaction.** Measured, not suspected: 15 of 15 graders
  detected it and said so.
- **The source documents are verdict documents.** Mechanism and adjudication are interleaved in the
  dossiers, so every scrub pass either leaves a steer or removes evidence the grader needs. The right
  input is a mechanism-and-evidence description written without a verdict, and no such document
  exists for these findings.

## What would make run 3 worth running

1. Build packets from `REPORT.md` and `finding.json` only, or hand-write neutral evidence
   descriptions. Drop the confirmation dossiers.
2. Delete redacted sentences rather than marking them.
3. Raise n. Five findings from one engagement in one band region cannot separate a small framing
   effect from grader variance, and the single flip observed is precisely the case that needs
   separating.
4. Keep `saw_prior_assessment`. It is the only reason run 2's contamination is known rather than
   suspected.
