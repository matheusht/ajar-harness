# engine/multi-round-orchestration.md — the portfolio layer over a single asset

> Everything else in `engine/` operates *within one route*: `loop.md` is the ladder for a single card,
> `routing.md` picks the card, `escalation.md`/`chainability.md` push a confirmed primitive. Missing was
> the layer that manages the **set of routes across rounds** for a whole asset — so we kept running one
> routed fan-out per asset, anchored on a pre-named crown-jewel, then adjudicating. That is exactly the
> two anti-patterns a strong multiagent auditor avoids: letting one suspicious approach dominate, and
> telling every agent the favored hypothesis. This doc is the fix.
> Pairs with `loop.md` (ladder inside a route), `routing.md` (seeds the family registry),
> `chainability.md` (the compose-pass), `persistence.md` (the termination governor), `whitebox-analysis.md`
> (the funnel each route runs). Adapted from a peer's WordPress-RCE agent methodology; **de-biased for our
> fuzzy oracle** — his target always contains a bug, ours often don't (see §5).

## When this applies
Per asset, in place of a single fan-out, whenever the surface admits genuinely independent mechanism
families (whitebox source audit: net, crypto, bazel, gson, …). It wraps **Stages 0→3.5** of the funnel.
It does NOT change Stage 4.25 (execute-to-oracle) or Stage 5.25 (novelty/reportability) — see §6.

## The core inversion
A single anchored round optimizes for *confirming the lead we already suspect*. That gives the same
coverage as the lead's blind spots. Multi-round independent portfolios optimize for *coverage of the
mechanism space* first, and only collapse toward a lead once independent signal justifies it. Depth of
composition (chaining weak fragments), not breadth of restated suspicion, is what turns a capped
primitive into a finding.

## 1. Three live artifacts (state carried between rounds)

### Approach-family registry (anti-convergence ledger)
One row per **mechanism** family, not per wording. The orchestrator reads it each round to force
diversity.

| family | mechanism (one line) | status | agents this round | signal | blocked-reason (exact missing mechanism) |
|---|---|---|---|---|---|

`status ∈ {untouched, live, crowded, exhausted, blocked}`. `signal ∈ {strong, weak, negative, —}`.
A `negative` family (a control that looks correctly enforced) is recorded as likely-held, not deleted.

### Primitive registry (chain-fragment inventory)
Every confirmed **or capped** primitive lands here as a fragment — a capped primitive is never terminal,
it is a fragment awaiting composition. This is what makes chaining *continuous* rather than a late pass.

| primitive | pre-auth source? | sink | reach / cap | composes-with (candidate fragments) | status |
|---|---|---|---|---|---|

### Round ledger
Per round: hypotheses opened / closed, families redirected, routes newly blocked **with the specific
mechanism that is missing**, compose-passes attempted, and the persistence-governor state (§5).

## 2. The round loop

- **Round 0 — blind portfolio.** N independent hunters, **no crown-jewel prior revealed**. Each is
  seeded a distinct family from the routing seed list (or self-selects into an `untouched` family), and
  told to report anything outside its lane too. Contract: return concrete source→sink triples with
  `file:line`, keep-biased; a real runnable PoC for anything concrete; never a status report. Purpose:
  independent signal, anti-anchoring. **The orchestrator withholds what it already suspects.**
- **Between every round — orchestrator synthesis.** Update all three artifacts; detect convergence;
  mark blocked routes with their exact missing mechanism; decide redirects and the next allocation.
  This is the "synthesize → challenge → redirect → launch new round" beat.
- **Round k — directed + adversarial + compositional.** Allocate by §3; pair a refuter with every
  surviving candidate (§4); run compose-passes over the primitive registry (does fragment A feed
  fragment B's sink?). Each route internally runs the `whitebox-analysis.md` funnel / `loop.md` ladder.

## 3. Allocation heuristics (no fixed "N per family")
- No family gets more than ~half the round's concurrency.
- Every round spends ≥1 agent on an `untouched`/`empty` family until all families are touched.
- Every surviving candidate gets exactly one independent refuter before promotion.
- A `blocked` family reopens **only** on a materially new mechanism, logged in the round ledger — not on
  renewed optimism.
- Keep ≥2 *incompatible* routes alive through ≥2 rounds before cross-pollinating (prevents premature
  collapse onto the shiniest lead).
- Concurrency: whitebox source audit parallelizes cleanly (no shared browser) — up to 4 concurrent is
  the working default; a live/browser target serializes per `CLAUDE.md` and drops this toward 1.

## 4. Adversarial-throughout
Refuter-per-candidate from round 1, not only at Stage 4.25. Each skeptic is tasked to REFUTE against the
asset's sanity checklist (the sanitizer-neutralization / reachability / real-runtime-behavior checks).
A candidate survives only if its skeptic cannot break it. (This is the gson "save-the-crown-jewel"
adversary, made standing.)

### 4a. The kill-pair — for framing-ambiguous candidates only
A standing refuter (above) answers *"can I break this?"*. It does not answer *"is this the right frame
at all?"* — and a lone reviewer asked to be "balanced" on a framing question reliably produces mush.

**Kill-pair:** two reviewers on one candidate, run concurrently and blind to each other. One is
**assigned to kill** — build the strongest case it is not reportable, concede only where code forces
it. One is **assigned to establish** — find the strongest TRUE form and the aggravating facts the
killer won't look for, with an explicit instruction that "this is empty" is an acceptable outcome.
The orchestrator adjudicates; it does not average them.

**Trigger — ambiguity, not routine.** Fire it when:
- the candidate's status turns on a **framing** question rather than a measurement (*"is this a bug or
  the function's intended purpose?"*), or
- two lanes disagree, or
- a finding survives only because nobody has attacked it hard.

**Do not fire it** for anything one measurement settles — whether a call reverts, who holds a role,
how deep a pool is. That is refuter work (§4) or just a query, and a kill-pair there is pure cost.

**Why the split beats one reviewer, from practice (crown-2026-08, 4 pairs):** the killer produced a
*control experiment* rather than an argument — replay-twice vs. one-call-for-the-sum consumed
byte-identical surplus, which is what actually retired the finding. The establisher, on the same
candidate, went hunting for a production incident and found exactly one real byte-identical duplicate
in 411 live events. Neither result is reachable by the other's brief, and the honest verdict needed
both: *not attacker-reachable, but a real Low anchored on an event that already happened.* On a second
pair the finding got **stronger** under attack — the establisher discovered the intuitive remedy was
inert, not merely expensive.

**Adjudication rules:**
- The killer's *factual* verifications stand on their own; its *precedent* arguments are discounted if
  it read the orchestrator's own prior conclusions — that is circular, and it happened.
- If a pair was briefed on a number that later changed, its verdict is against a weaker target. Re-brief
  the one still running; weight the finished one accordingly.
- A pair that corrects the orchestrator **downward** (an establisher refusing to pad 7 roots to 7 when
  only 6 qualify) is the signal the mechanism is working, not a disappointing result.

## 5. Termination governor — evidence-licensed (the de-bias)
The peer method says "never give up" because its benchmark *always* contains a bug. Ours often do not,
so unconditional persistence here is how you reward-hack a clean codebase into a fake finding. Exit is
governed by `persistence.md`:

- **Exit = FOUND** when a candidate is confirmed **and executed to oracle** (Stage 4.25 with a negative
  control) → hand to the reportability gate.
- **Exit = COVERED-DRY** only when ALL hold: every registry family is `exhausted` or `blocked`
  (no-new-mechanism); the primitive registry has no un-attempted composition; and a recent blind round
  produced **no new family** — sustained for a bounded number of consecutive dry rounds (floor `K≈2`).
- **The persistence bar scales with evidence.** A confirmed primitive, a `strong` routing signal, a
  ghsa-fix-diff anchor, or an operator prior *raises* the round bound and forbids early dry (a held
  vector = wrong turn). Absent such evidence, dry is allowed at the floor. Fishing is not persistence;
  persistence is licensed by a signal that something is already wrong.

## 6. What it deliberately does NOT touch
It wraps Stages 0→3.5 only. Downstream is unchanged and non-negotiable:
- **Stage 4.25 — execute-to-oracle with a negative control.** A chain that isn't run is `unconfirmed`,
  never `found`. Confirm from RAW output, never a wrapper's summary (see the rtk / fake-client lessons).
- **Stage 5.25 — novelty / reportability / attribution.** The gate the peer method has no need for (a
  planted flag is definitionally in-scope) and the reason our covered-dry verdicts are *correct*
  (declined / already-fixed / on-roadmap / app-attributable). The loop improves *finding*; it never
  overrides *reportability*.

## 7. Minimal operating record
For an asset run under this doc, keep the three artifacts (a `rounds.md` beside the asset's findings is
enough) and end with the terminal state per §5 plus a one-line honesty note: did the blind multi-round
portfolio surface any family the initial routed pass missed? That answer is itself a measurement of
whether single-round routed hunting was leaking coverage.
