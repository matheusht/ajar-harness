# engine/persistence.md — exhausting leads, thoughtfully

> The **computed work queue is the single completion condition** (`engine/loop.md`). Evidence changes
> the work that must be represented in that queue: it *licenses* persistence, a bounded space makes
> "dry" mean something, a staged funnel keeps the grind rigorous, and a counterweight keeps it from
> becoming tunnel vision.
> Pairs with `engine/loop.md` (the ladder) and `engine/routing.md` (the signals).

## When this applies (evidence-licensed, not default)
Persistence mode turns on only under **evidence**: a confirmed finding, a `strong` activation signal,
or an explicit operator prior ("there is a vuln in these 57 tables + 97 RPCs, I'm sure of it"). Absent
evidence, the computed work queue governs without expanding the bounded search — do **not** grind a
cold surface. Fishing is not persistence; persistence is licensed by a signal that something here is
already wrong.

## The core inversion
Default loop: a refusal/dead-end is an input to the next rung, terminal verdict is coverage/dry. With
evidence in hand, sharpen it:

> A held vector is a **wrong turn** for the current route. It is negative evidence for that route; it
> does **not** by itself decide whether the vuln is reachable another way.

Update belief in the route, mechanism and broader hypothesis according to how diagnostic the observation
is. Continue the remaining bounded work while its evidence-adjusted priority and budget justify it. A
dead end neither proves the broader space clean nor guarantees a vulnerability elsewhere in it.

## Bound the space so "dry" is real
Quantify the surface up front: N tables + M RPCs, the sink set, the route list, the delivery channels.
Then **dry has a definition** — every one of the N+M enumerated *and adjudicated* — instead of "I got
tired." A bounded, enumerable space is what converts "try harder" into a finite, checkable job. The
operator's conviction that a vuln exists is a prior; treat it as a search signal, not claim truth or
pressure to force a finding. Contradictory evidence may lower it.

## The funnel — grade top to bottom, revisit freely
Run leads through a wide-to-narrow funnel with a rigor gate at each narrowing:

```
narrow → cheap-classify → hypothesis triples → reachability → confirm → re-verify + classify
       → chain → novelty → evidence dossier → advisory → triage/regrade/file
```

Two properties make this thoughtful rather than a rigid march:
- **Top-to-bottom grading.** Each stage is a gate a candidate earns its way through. Cheap filters
  before expensive confirmation (don't spend oracle budget on un-narrowed space). Nothing is a finding
  until **reachable/deliverable** (the analog of reflection≠execution, sink≠delivery). Nothing ships
  without the **post-confirmation re-verify** — a single `confirmed` is not enough.
- **Backtrack freely.** You may return to any **earlier** stage at any time — redo recon, re-narrow,
  add a hypothesis — and you may **insert a refinement sub-pass** between stages when one needs it. The
  funnel says *where the rigor gates sit*, not that work flows one way. Revisiting is the method, not a
  failure of it.

## The counterweight — persistence is not tunnel vision
"You don't have to make yourself stuck." If a sub-area goes dry, **step back**: redo the recon phase,
look for a surface you missed, or dive deeper elsewhere. Alternate **zoom-out** (what did I miss? what
did recon not cover?) and **zoom-in** (dig this one lead harder). Exhausting a lead means *cover it,
then move* — never fixate on one dead sub-stage. Getting stuck grinding a held vector is the same
failure as calling a surface dry after one pass, from the opposite direction.

## Rigor does not bend under persistence
Trying harder never lowers the bar — it raises the effort to reach ground truth, not the willingness to
claim a hit.
- **Default-to-disbelief holds.** A strong lead can still end `refuted` (e.g. an accepted metadata-IP
  literal that the OAST oracle shows never triggers an actual fetch → DNS-only, not SSRF). Persistence
  buys a *definitive answer*, not a forced finding.
- **Reconcile conflicting evidence.** When a source read *looks* fixed but an independently observed
  live effect says otherwise, re-verify both and name the mechanism that reconciles them. A confirmed
  effect supported by its oracle is strong evidence for that observed path; it does not make unrelated
  claims true, and source text does not erase the effect without an explanation.
- **Land the result honestly.** Terminal states are `confirmed` / `chained`, `real-but-capped` (a held
  control bounds impact — *prove* the cap), or `covered-dry`. Never "it finally worked," never "I gave
  up."
- **Persist inside the gates.** If exhausting a lead needs a Zone-2 / escalation step, record the
  authorization in the ledger first, then proceed (`AGENTS.md §1`). Persistence operates within scope.

## Prime with prior engagements
Seed a run with a casebook or a past engagement's methodology as a worked template ("this is how it was
done before; adopt it"). That is the harness's purpose: give the model real-engagement knowledge to act
on instead of training-set intuition. (`casebooks/`, `engine/routing.md`.)

## Terminal verdicts (what "done" means here)
- **covered-dry** — the bounded space is fully enumerated and adjudicated; every material route is
  decisively `exhausted` or `closed`, the computed work queue's final cold-review item has been closed,
  and no reduced item has `blocking: true`. A non-empty operator-only queue remains visible and is
  not falsely presented as resolved; while coverage is active it pauses agent work. A merely `held`
  route remains unresolved and cannot support dry.
- **confirmed / chained** — found, and composed forward where a finding unlocks the next.
- **real-but-capped** — the vuln is real but a held control bounds its impact, and the cap is proven.

### Decision-0005 persistence records

Record each material route as a `hypothesis.created` event and append evidence-rich status changes;
do not collapse a broader mechanism when one implementation is refuted. Controls and replay are typed
immutable attempts. `coverage_dry` is accepted only after a committed fresh-context coverage review
matches every current hypothesis disposition. A signed-scope operator prior can explicitly reopen an
exhausted hypothesis and coverage, while leaving claim state untouched. The reducer enforces these
boundaries without prescribing how the researcher generates or revises hypotheses.

A dry verdict is only credible once the space was *bounded* and *enumerated* and the computed work
queue contains no blocking item; "dry after one pass" is the failure mode this whole doc exists to
prevent.
