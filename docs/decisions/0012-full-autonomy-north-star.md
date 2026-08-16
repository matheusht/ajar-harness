# Decision 0012 — Full autonomy as the north star: scope is the only human decision

**Status:** **RECORDED DIRECTION — not accepted for implementation, not scheduled, not authorized.**
Nothing in this document changes any current gate.\
**Date:** 2026-08-16\
**Effect:** records the product's intended end state and, more importantly, the reasoning that would
have to be overturned to reach it. Extends Decision 0004 (autonomy envelopes) and 0010 (gates).
Supersedes nothing.\
**Related:** `engine/autonomy.md`, `docs/decisions/0004-epistemic-autonomy-complexity-budget.md`,
`docs/decisions/0010-promotion-gates-and-fail-open.md`

## The direction, as stated by the operator (2026-08-16)

> Once our product evolves more, we will make it fully autonomous, and for that we have to think and
> develop on different controls and gates will be autonomous. Only scope will be decided at first;
> after that, some gates that we consider "hard gates" today will need to change. Not for now, but
> to think about later. That is the ultimate and last step on scalability and full product autonomy.

**The end state:** the operator signs a scope. Everything downstream — recon, analysis, adjudication,
packaging, and eventually filing — runs without a human in the loop.

**The reason:** scalability. A harness that needs a human at four points per finding does not scale
past one operator's attention, and the portfolio already shows the cost — 12 of 13 engagements that
produced a report sit at "drafted, operator files" for 28-36 days. The bottleneck is the human, and
at some point the answer is not a faster human.

## Why this document exists, and it is not to agree

This is recorded now, while the reasoning behind today's gates is fresh, so that a future version can
change them **deliberately** rather than by drift. The failure mode this repository keeps producing
is not bad decisions — it is decisions whose justification quietly stopped being true and nobody
noticed. The promote/demote asymmetry is one: its stated cost model assumed a re-review that never
existed.

So this document records what would have to become true. A future reader who removes a hard gate
should be able to point at the item below that changed.

## What is a "hard gate" today, and what argument holds it

`engine/autonomy.md` §2 names two gates as irreducible. Both would have to change.

### Hard gate 1 — Zone-2 confirmation before an impact artifact

**Held by:** irreversibility. The act cannot be undone by the identity that performed it.

**What would have to change:** not the supervision, the **capability**. Every production system
surveyed that handles this class narrows what the actor *can do* rather than trusting supervision
more. Full autonomy here does not mean an agent decides to fire an irreversible act unsupervised. It
means the act is no longer irreversible — sandboxed, transactional, or bounded so that the worst
outcome is recoverable.

**The reframe that matters: you do not remove a control, you replace it.** A gate is a control on an
unbounded capability. Bound the capability and the gate becomes redundant rather than absent.

### Hard gate 2 — adjudicating `confirmed`

**Held by:** automation bias, specifically its omission half. Skitka et al. measured that training
reduces *commission* errors and does **not** reduce *omission* errors. Telling a model to be careful
does not fix a missed check; only an independent check does.

**What would have to change:** an independent verifier that is not the thing being verified. Today
the harness has no such thing for adjudication — every internal pass shares the priors of the pass it
checks, which is exactly what two audits in August 2026 concluded. Candidates that would count:

- a **deterministic** layer for the mechanical part of the claim (Phase 7's reachability engine —
  which is why "a model confirming a model" was rejected in the DeepSec evaluation);
- **external ground truth** at volume (Decision 0011's disposition ledger, once it holds enough
  graded records to bound our error rate rather than describe it);
- **cross-family panels** where minority verdicts are recorded rather than aggregated away, since the
  2025-2026 literature finds same-family panels entrench bias rather than correct it.

## Preconditions — what must be true before any hard gate moves

None of these is satisfied today. Each is measurable, which is the point of writing them down.

1. **A quality proxy with external ground truth.** Not internal re-review. Currently 1 graded
   disposition against a floor of 5, and no engagement has closed the loop at volume.
2. **A measured miss rate with a stated bound.** `engine/autonomy.md` §5: N=40 with zero misses puts
   the 95% upper bound near 7.5%. Full autonomy on adjudication needs a far tighter bound than that,
   over far more samples, and the bound must be reported every time the number is.
3. **The gates have demonstrably blocked something real.** As of 2026-08-16: **12 promotions, 1
   demotion, zero blocked rows.** A gate that has never fired is untested, not proven. You cannot
   automate a control whose accuracy is unmeasured.
4. **Irreversible acts are bounded, not merely supervised.** See hard gate 1.
5. **An independent verifier exists that does not share the priors of the thing it verifies.**
6. **Reversal is cheap and rehearsed.** A gate removed without a tested restoration path is a
   one-way door. Decision 0010 records four instruments that failed open without anyone noticing;
   the same class at full autonomy fails silently and at scale.

## The staging, if it is ever taken

Strictly one gate at a time (`engine/autonomy.md` §7 — graduate two and you cannot attribute a
quality drop). In increasing order of what it costs to be wrong:

1. Information **acquisition** gates — preflight, recon snapshots, per-attempt dispatch in scope
2. Information **analysis** gates — oracle-negative re-confirmation, narrowing, chain construction
3. **Packaging and filing** — action stage, but reversible-ish: a filed report can be withdrawn,
   at a reputational cost that is real and should be priced
4. **Adjudicating `confirmed`** — decision selection, the hardest, and last
5. **Zone-2** — only after the capability is bounded, never by trusting supervision more

Scope stays human throughout. That is the operator's stated floor and this document does not
question it.

## What this does NOT authorize

- No gate graduates on the strength of this document.
- No current hard gate is weakened, and `engine/autonomy.md` §2 remains binding until superseded by
  a decision that cites the specific precondition it satisfied.
- Phase 2's standby method (`engine/autonomy.md` §3) still governs every graduation: preregister the
  rule, run on standby, record interventions live, decide at N.

## The honest tension, recorded rather than resolved

The operator's direction and `engine/autonomy.md` §2 currently disagree. §2 says no framework
surveyed supports removing those two gates. The direction says they will change.

Both can be right, and the resolution is in the reframe above: **§2 is an argument about supervision,
and the direction is an argument about capability.** A bounded irreversible act is not the same
decision §2 was about. Where they genuinely conflict — adjudicating `confirmed` — the direction needs
an independent verifier that does not exist yet, and Phase 7 plus Decision 0011's ledger are the two
things being built that could become one.

If a future reader finds this document being used to justify removing a gate without the
corresponding precondition, that is the drift it was written to prevent.
