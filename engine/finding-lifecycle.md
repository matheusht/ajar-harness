# engine/finding-lifecycle.md — findings start unproven

## 1. The rule

A finding is written to `unproven/`. It has no status field. It has a **location**.

The location changes only by running `promote`, which runs gates. Any gate can say no. A finding
that does not pass stays where it is.

```
engagements/<id>/
  unproven/<FINDING_ID>/     every finding starts here
  findings/<FINDING_ID>/     a finding arrives here only through promote
  lifecycle.jsonl            append-only record of every promote and demote
```

## 2. Why the default matters

Every system that produces claims picks one of two defaults.

| default | with no action | an unattended run drifts toward | failure mode |
|---|---|---|---|
| accept | the claim stands | **more** claims | silent, and it compounds |
| reject | the claim is nothing | **fewer** claims | loud, and it self-limits |

Most software is default-accept because most software trusts its input. This pipeline takes claims
from an unreliable narrator, so it must be default-reject.

The reason is unattended operation. Under default-accept a check that does not run is a silent pass,
so a broken run produces confident garbage and looks productive. Under default-reject a check that
does not run is a silent block, so a broken run produces nothing. Choose the failure that is visible.

**The case that produced this doc.** In spotify-backstage-2026-07 (2026-08-09) seven findings were
written straight into `findings/` with `claim_state: supported` set by the script that created them.
Nothing objected, because nothing had to. See `fixtures/preregistration/spotify-phase2-OUTCOME.md`.

## 3. Who may move a finding

| action | role | why |
|---|---|---|
| write to `unproven/` | hunter, orchestrator | a hunter may propose, never confirm (`CLAUDE.md` §2) |
| `promote` | **orchestrator only** | this is decision selection, the stage that stays human-supervised |
| `demote` | **any role, any time** | a wrong demote costs a re-review; a wrong promote reaches a vendor |

Promote is hard and demote is easy on purpose. The costs are not symmetric, so the friction should
not be either.

The orchestrator running `promote` is necessary and **not sufficient**. The orchestrator is what
fabricated the adjudication in the case above. The gates therefore check things that cannot be
satisfied by writing more text.

## 4. The gates

`tools/finding_lifecycle.py gates PACKAGE` runs them without moving anything.

| gate | question | kind |
|---|---|---|
| G0 | does every path the package cites exist? | computable |
| G1 | is a primary attempt named, and real execution attested? | computable + attestable |
| G2 | is a negative control named and attested? | computable + attestable |
| G3 | did the proof run at or below the claimed attacker privilege? | computable |
| G4 | is the adjudication judgement rather than generation? | computable |
| G5 | does a claimed severity carry a CVSS vector that recomputes? | computable |

### G3 — the privilege gate

A program cannot decide whether a proof truly ran as a low-privilege user. It can decide that the
package **declares both positions** and that they agree.

The package declares `privilege_context: {claimed, proven}`. The gate ranks both on a ladder —
unauthenticated 0, authenticated or co-tenant 1, privileged or admin 2, system or root 3 — and
requires `rank(proven) <= rank(claimed)`.

Proving from **less** privilege than claimed passes: that is a stronger result. Proving from more
privilege fails, because it does not establish that the attacker can reach the code at all.

This is the failure ZSec documented: a named pipe that looked exploitable from SYSTEM and was
unreachable as a standard user. Our own equivalent is any finding whose PoC ran as the operator.

**`proven: not-established`** is a valid declared value. Use it when the proof does not start from an
attacker position at all — a unit test that constructs the post-bypass state, a harness that begins
mid-chain. It always blocks, but it blocks as a STATEMENT rather than as an omission. "We know this is
missing" and "nobody looked" should not look the same in the record.

First real use, 2026-08-10: all eleven spotify findings declare it. The A2 keystone PoC calls
`mockCredentials.service()`, which constructs the post-bypass state and asserts the real
`ServerPermissionClient` allows it. That proves the CONSUMER against real code; the PRODUCER half is
source-verified, not executed.

### G4 — the adjudication gate

`tools/adjudication_audit.py` over the package's `reviews/` **and over the engagement's whole
claim_adjudication set**. It blocks a review corpus that carries the signature of generation: one
reviewer identity, no dissent, and boilerplate rationale, all together.

Auditing the engagement corpus is not optional. The signature is a property of the **corpus**, not of
one review. A package normally carries the single review that adjudicated it, and one review can
never show all three signals. Running the gates over the eleven spotify findings on 2026-08-10 passed
G4 on all eleven, while the engagement's 15-review corpus audited `synthetic`. If the corpus was
generated, no finding resting on it may promote.

## 5. The package

```
unproven/<FINDING_ID>/
  finding.json      the finding record; v1 flat and v3 nested are both read
  attest.json       the references the attestable gates require
  REPORT.md         the writeup
  reviews/*.json    claim_adjudication reviews
```

`finding.json` must carry `privilege_context`. Without it, G3 blocks — a finding that does not say
what position it was proven from has not been proven.

## 6. What this does not do

It does not decide whether a vulnerability is real. It decides whether the package's own claims
survive mechanical checking, which is the same boundary `tools/score_finding.py` draws.

Novelty, reportability, and attribution stay at Stage 5.25. Zone-2 artifacts and the operator's
review before submission are unchanged and are not gates in this file
(`engine/autonomy.md` §2 — those two do not graduate).

## 7. Increasing autonomy

The way to run more of this unattended is **not** to trust the model more. It is to convert
judgement into decidable checks. Every check that becomes computable is autonomy gained while
trusting nothing extra.

G3 was judgement until 2026-08-10. G4 was judgement until 2026-08-09. Both are now gates. The next
candidates are G1 and G2, which are attestable today and could become computable once attempt records
carry a machine-readable execution context.
