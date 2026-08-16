# Research plan — mechanical reachability, and cross-engagement memory

Written 2026-08-10. Status: **plan only. No build starts until the operator confirms this document.**

Two workstreams. They are independent and can run in parallel. Both answer a question this harness
cannot answer today.

| | question it answers |
|---|---|
| **A. Mechanical reachability** | is a claimed source-to-sink path real, decided by a machine? |
| **B. Cross-engagement memory** | does what we learned in run 1 change what run 20 does? |

Governing decisions: `docs/engineering/002-decisions.md` D-07, D-08, D-09.

---

## Ground rules for both workstreams

**1. Measure before we build.** The operator agreed the engine joins the harness. The experiment still
runs first, because we cannot yet say what success looks like. Two opposite results are both possible
today — the engine agrees with us nearly always (it added cost and no information), or it disagrees
often (we have two oracles and no tiebreak). If we build first, we will rationalise whichever result
arrives. Preregistration applies to our own engineering, not only to engagements.

**2. Every metric is fixed in this document, before any data exists.** A metric chosen after seeing
results is not a metric.

**3. Confirm only, never kill.** Holds for the engine (D-08) and for the knowledge base (D-09). Neither
may remove a route, kill a candidate, or lower a verdict.

**4. Report the denominator.** Every result states what was tried, not only what worked. This is the
thing all three practitioner posts we reviewed left out.

---

# Workstream A — mechanical reachability

## A.0 The problem, stated plainly

When a hunter says "attacker input reaches this dangerous function", the only thing deciding whether
that is true is a model reading code. There is no independent check.

| | mechanical evaluator |
|---|---|
| Kettle, web | send a request, compare responses — the machine decides |
| Big Sleep, memory safety | run it, AddressSanitizer names the overflow — the machine decides |
| this harness, source audit | **nothing** — a model gives an opinion |

That absence is why the work is filtering thousands of fakes, and why Stage 2 and Stage 3 need many
grading rounds.

## A.1 Blocking question — licence

**This is checked first. It can invalidate everything below it.**

CodeQL is free for research on open-source code and **restricted for commercial use**. OSLit is a
commercial product. The operator approved CodeQL "for now", which covers the experiment and does not
cover shipping.

Deliverable: the exact terms for CodeQL, Semgrep and Joern, quoted from each licence, against three
uses — (a) internal research on open source, (b) paid engagement work for a client, (c) embedded in a
product we sell. If CodeQL fails (b) or (c), the experiment still runs on CodeQL and the shipping
engine may have to differ. Say so plainly rather than discovering it later.

## A.2 The experiment — Go reachability

**Scope: one language. Go.** It is the language of most of our engagements — Cosmos, Klever,
Kubernetes, gVisor. One language, one experiment, a number at the end.

**Corpus: findings we have already adjudicated**, both directions. Confirmed findings AND refuted
candidates. A confirm-only corpus cannot measure a false positive.

**Method:** for each case, express the claimed path as a source-to-sink query and run it. The model
proposes the sources and sinks (semantic); the engine computes the dataflow (mechanical). That is the
IRIS split.

**The three numbers, defined now:**

| number | meaning | why it matters |
|---|---|---|
| **confirm rate** | of our confirmed findings, how many does the engine confirm? | the useful case |
| **miss rate** | of our confirmed findings, how many does it fail to confirm? | **the deciding number** — it bounds how far we may ever lean on the engine |
| **contradiction rate** | of our refuted candidates, how many does it confirm? | alarming: one of us is wrong, and each case must be read by hand |

**Reading the result, fixed in advance:**

- miss rate under ~20% → the engine is a usable confirmer; proceed to design the integration
- miss rate 20–50% → weak confirmer only; it may add evidence and never carry a verdict
- miss rate over 50% → the engine does not transfer to our work; record the negative result and stop

**No outcome here is a failure.** A measured negative result is a real deliverable and stops us
spending months on a tool that does not fit.

**Honest limits to state with the result:** the corpus is small, it is our own past work, and our
adjudications are themselves fallible. This measures agreement with us, not truth.

## A.3 Research questions

- **Build cost.** CodeQL needs a **working compile**, and this repo has repeatedly failed to build
  targets. Per target: how long to build a database, how large, and what breaks? A version bump throws
  the database away — how often did our engagements re-pin?
- **Query authoring.** Is a per-finding query hand-written each time, or is there a reusable template
  where the model fills in source and sink? The second is the only version that scales.
- **The IRIS result.** What did it actually measure, on what corpus, with what false-negative rate?
  Has anyone replicated it? Treat one preprint as one preprint.
- **The alternatives.** Semgrep (cheaper, weaker dataflow) and Joern (no compile needed, CPG-based).
  Joern's no-compile property may matter more than CodeQL's precision, given our build record.
- **Where it cannot go.** Solidity, and any target we cannot build. Name the dead zone up front.

## A.4 What A does NOT do

It does not become an oracle. It does not kill. It does not adjudicate severity, novelty, or
reportability. It answers one narrow question — does this path exist in the call graph — and that
answer is evidence at Stage 3.

---

# Workstream B — cross-engagement memory

## B.0 The problem

There is **no cross-engagement memory of any kind**. `winners.md` exists once per engagement and
nothing reads it afterwards. `engine/routing.md` reads recon signals only. All 30 engagements started
cold, in both directions.

Inside one engagement this job is already done: `engine/multi-round-orchestration.md` has the
approach-family registry, a route goes `blocked` with the exact missing mechanism, and it reopens only
on a materially new mechanism. **Do not rebuild that.** The gap is strictly between engagements.

## B.1 Design, as agreed

**One mechanism, two entry kinds.** Winners and losers share a file format. Building two is waste and
the promotion discipline is identical.

**Four rules, each answering a way this fails:**

1. **A loss must name the control that held.** "We looked and found nothing" is not a loss; it is an
   absence of work. "The parser normalises before the guard runs, so the traversal family cannot reach
   the sink" is a loss worth keeping. Without this the file fills with shrugs.
2. **Each entry declares its transfer scope** — `this-target` / `this-framework` / `this-language` /
   `this-mechanism-class`. Without it a Backstage result would wrongly suppress a Kubernetes route.
   This field is what stops false transfer.
3. **Bounded and unbounded are different and must be said.** A route we exhausted is not a route we
   abandoned. Both are worth recording; they mean different things to the next run.
4. **It changes ORDER, never removal.** ZSec's version multiplies a hardened target's priority down.
   That is a feedback trap — a target you once found hard gets buried, including one that later went
   soft. Ours re-orders and annotates. The reopen rule from the family registry applies unchanged: a
   materially new mechanism reopens anything.

**Storage: JSONL in git.** Hundreds of records, not hundreds of thousands. It diffs, it reviews, it
needs no service.

**Not vector search.** ZSec indexes 561,000 chunks. A mature file here is 100–300 entries — four
orders of magnitude smaller. At that size structured query is exact, explainable and deterministic,
and `CLAUDE.md` §3 already chose determinism over fuzzy matching on purpose. Revisit only if the
corpus grows past the point where structured query fails. Research question, not a build item.

**Two storage problems, kept apart.** The CodeQL database (workstream A, multi-gigabyte, per target,
needs a compile) and our own index (workstream B, hundreds of records) are unrelated. Designing them
together produces a bad answer for both.

## B.2 It never kills — the reasoning

A losers entry records that **we** failed to find something. That is evidence about our search, not
about the target. Killing on it converts "we did not find it" into "it is not there", which is the
omission error Skitka measured as untrainable.

One edge case: an entry recording a **proven control** rather than a failed search is a fact about the
target, not about us. Even then it earns a stronger annotation, not kill authority, because a control
is version-specific and may have changed.

## B.3 How B is tested — reuse the ablation gate

`tools/ablation.py` already encodes the rule: a promoted lesson must change a verdict, or it is not a
lesson. The same rule applies here.

> **A knowledge-base entry must change a routing decision, or it is not promoted.**

Mechanically: run routing over a recon-signal set with the entry and without it. Identical family
order means the entry is noise, and it is dropped. Same fixture shape we already use, so the new parts
are one file, one small tool, one conformance check.

## B.4 Open question carried into the research — who writes an entry, and when

If the orchestrator writes its own entry at close, that is self-reporting: the same shape that
produced the fabricated status field. The ablation gate limits the damage, but the write path deserves
the scrutiny a finding's does. The research should look at how other systems handle self-reported
learning, and whether an independent writer is worth the cost at our scale.

## B.5 Seed corpus

Spotify's `60-coverage-dry-ledger.md` (22K) is the obvious first input, plus the covered-dry verdicts
across the Cosmos campaign and the Google OSS-VRP assets. Enough to test the format against real data
rather than invented data.

---

# Execution

## Order

1. **A.1 licence** — first, alone. It can invalidate A.
2. **A.3 and B.4 research** — parallel agents, no build.
3. **Grill the findings**, then confirm the build plan with the operator.
4. **A.2 experiment** on the Go corpus. Numbers, not opinions.
5. **B build**, if the research surfaces nothing that changes the design.

## Agents

Parallel, each with a bounded brief and a required concrete output. Every claim cites a source, every
inference is marked, and an unreachable source is reported rather than filled in. Rules from
`engine/multi-round-orchestration.md` apply: independent briefs, no shared favoured hypothesis, and an
adversarial pass on anything that looks conclusive.

Roster: licence terms; CodeQL build cost and failure modes; IRIS and the LLM-plus-static-analysis
literature, read sceptically; Semgrep and Joern as alternatives, with Joern's no-compile property
weighed against our build record; cross-engagement learning and negative-result reuse in other
systems; the corpus-size threshold where semantic retrieval beats structured query.

## What the operator decides after the research

- whether the Go experiment proceeds as specified
- the shipping engine, once the licence terms are known
- whether an independent writer is required for knowledge-base entries

## Success for this plan

Not "we adopted a static analysis engine". Success is: **we know the miss rate, and we know what the
engine cannot do.** A measured negative result that stops us building the wrong thing is worth the
same as a positive one.
