# Roadmap

Date: 2026-08-08.

## Objective

Reduce the operator work per engagement. Keep the quality of the results. Do this in steps. Do not
try to remove the operator in one step.

`CLM-0001` gives the test: interventions must fall while external acceptance stays the same.

## Principle for all phases

Move work from the model into code. Do not move work from the operator to the model. The model is
the part that makes the errors that the operator corrects.

Each phase must produce a number. If a phase produces only a document, it does not count as done.

---

## Phase 0 — Hygiene — **DONE 2026-08-08**

**Effort taken:** about one hour. **Risk:** none.

1. **Done.** 13 files staged. `engine/escalation.md`, `engine/blackbox-web.md`,
   `engine/multi-round-orchestration.md`, `skills/oracles/chainability-oracle.md`, and four
   `skills/` directories. 1,660 insertions. No secret files in the set.
2. **Changed and done.** The first plan said to delete `AGENTS.md`. That was wrong. See D-03 in
   `002-decisions.md`. A preregistration file pins its sha256, and `docs/agents/domain.md` documents
   the mirror as intentional. Added `check_doctrine_mirror()` to `tools/check-conformance.py`
   instead. The check compares the two hashes.
3. **Done.** `engagements/_TEMPLATE/scope.md` now holds a `standing_impact_maximization_mandate`
   field, default `no`, plus the canonical text. It points to the engine doctrine files rather than
   copying them.
4. **Done, and made permanent.** Added `check_cited_fixtures()` to `tools/check-conformance.py`. The
   check found 4 missing fixture paths across 3 cards, not 3 as first counted. The three cards now
   carry `fixture_status: planned`. The check blocks any future card that names a fixture directory
   that does not exist.

**Result:** conformance moved from 452 checks with 0 failures to **463 checks with 0 failures**.

**Note on method:** items 2 and 4 became machine checks instead of one-time edits. A one-time edit
fixes today. A check fixes every future case. Prefer the check.

**Not fixed by Phase 0:** three cards (`evm-access-control`, `evm-accounting-invariant`,
`evm-arithmetic-rounding`) cite `jpegd-reentrancy`, which is a reentrancy fixture. The path exists,
so the new check passes. The calibration is still wrong. This needs a real fixture for each class.
Record it as work for a later phase.

---

## Phase 1 — Measure, then grade

**Effort:** one to two weeks. **Risk:** low. **Blocked by:** nothing.

This phase is the core of the plan. Build the instrument first. Then build the first grader. The
order matters: without a baseline, you cannot prove that the grader helped.

### 1a. `tools/intervention_ledger.py` and `schemas/intervention.schema.json`

Record each operator correction when it happens. Fields: stage, class, the wrong value, the correct
value, and how the error was found.

Classes: authorization, calibration, persistence, skepticism, taste, process.

Run this for two engagements with no other change. This gives the baseline.

### 1b. `tools/score-finding.py`

Port the pattern from `tools/score-candidate.py`. The judge note is advisory. The code decides.

Checks:
- Each quantitative claim has a re-derivation reference.
- Each cited file, line, or artifact exists.
- The severity vector recomputes to the stated score.
- The version pin matches the source tree.
- No outbound document contradicts the finding verdict.
- No internal process word appears in an outbound document.

**Done when:** the ledger holds a baseline from two engagements, and `score-finding.py` blocks a
finding that fails a check.

**Measure:** the late-catch ratio. The baseline is about 65%. Watch this number after Phase 1b.

---

## Phase 2 — Graduate the first gate

**Effort:** one engagement. **Risk:** low. **Blocked by:** Phase 1a. **Needs:** answer to Q-07.

1. Write `engine/autonomy.md`. Give each of the four automation stages its own level.
2. Pick one gate. The research names three candidates: recon and routing snapshots, per-attempt
   dispatch inside an approved scope, and re-confirmation of oracle negatives.
3. Run the gate on standby only. The operator watches but does not gate. Count the real
   interventions.
4. Remove the gate when the count is near zero on fresh controls.

**Recommendation:** start with re-confirmation of oracle negatives. It is the largest source of
low-value operator attention. Batch these and show only the disagreements.

**Done when:** one gate is removed with intervention data as the evidence.

---

## Phase 3 — Close the learning loop

**Effort:** one week. **Risk:** low. **Blocked by:** Phase 1a.

The promote step works. It has no next step. One valid `promote` produced zero change.

1. Add a required field `ablation_fixture` to the memory disposition schema.
2. The fixture must show a different result with the lesson present and with the lesson removed.
3. Add a script that opens a tracked draft pull request on each `promote` event.

**Done when:** one pattern moves from a candidate to an engine file or a card, with a fixture that
proves the pattern changes a result.

**Note:** no external source measures this. This is new engineering. Record it well.

---

## Phase 4 — The evaluation primitive

**Effort:** unknown. **Risk:** high. **Blocked by:** a decision on Q-04.

This phase needs an answer first. A white-box source audit has no crash and no response
differential. The `IRIS` model is the closest: a model proposes the taint sources and sinks, and
`CodeQL` computes the dataflow.

Steps after the decision:
1. Write `engine/evaluation.md`. Each engagement declares its cheapest mechanical check first.
2. Add the deterministic reachability layer for one language.
3. Measure the false-positive rate against a known corpus.

**Do not start this phase before the operator answers Q-04.** The decision changes the tool chain.

---

## Phase 5 — Ideation experiments

**Effort:** two experiments. **Risk:** low cost, high value if positive. **Blocked by:** nothing.

These are experiments. They are not committed work.

1. **Q-02 test.** Run one engagement twice. Give one run the full goal prompt. Give the other run
   only the objective and the scope. Compare the findings.
2. **Q-01 test.** Split one target specification into fragments. Generate one to three hypotheses
   per fragment. Compare against the card-based method.

**Done when:** both tests have a result. Then answer Q-03.

---

## Closed-loop measurement

A phase is **closed-loop** when the team can measure its quality with data that exists now. A phase
is **open-loop** when it needs a new engagement to produce the measurement.

Prefer closed-loop phases first. An open-loop phase cannot show a result until an engagement ends,
which can take weeks and adds target-specific noise.

| Phase | Loop | How to measure it |
|---|---|---|
| 0 Hygiene | **Closed** | Conformance check count and failure count. Done: 452 to 463 checks, 0 failing. |
| 1a Intervention ledger | **Closed** | Backfill the ledger from the 147 corrections already written in the engagement records. This gives a baseline with no new work against a target. |
| 1b `score-finding.py` | **Closed** | Build a regression corpus from the documented corrections. Measure the catch rate offline. |
| 3 Learning loop | **Closed** | The ablation test is a differential by definition. Run the evaluator with the lesson present and with the lesson removed. Compare. |
| 5 Q-01 ideation | **Partly closed** | Generate hypotheses offline from a past target specification. Compare against the existing 45 cards. Novelty against a live target stays open-loop. |
| 2 Gate graduation | **Open** | The standby method counts live interventions. This needs engagements. |
| 4 Evaluation primitive | **Partly open** | Recall is closed-loop if the pinned source trees still exist: re-run against past engagements and check that the confirmed findings return. Precision needs new work. |

### The corpus for 1b

The engagement records hold 147 corrections. Each one states the wrong value and the correct value.
Examples: "the 10-14 restarts-per-event figure was WRONG ... E[restarts] ≤ 1.4"; "The word 'verified'
in the original verdict was unearned ... n=0". A card cites `audius-storage-collision`, which does
not exist.

Build one small test entry per correction. Each entry holds the known-bad claim in the shape of a
real finding fragment. Then measure the catch rate of `score-finding.py`.

This copies the method already used in `fixtures/false-discovery/corpus.json`, which holds 24
hand-built traps and gates on `invalid_accept_rate == 0`.

**Source note:** the engagements are mostly untracked in git, so the original bad artifacts are not
recoverable. Build the entries from the documented corrections instead. State this in the corpus.

**Limit, stated plainly:** this measures the catch rate for error shapes that already happened. It
does not measure the catch rate for new error shapes. Every regression suite has this limit. Do not
report the number as a false-negative rate.

## Priority order and reason

Revised 2026-08-08 after the closed-loop analysis above. Phase 3 moved ahead of Phase 2, because
Phase 3 is closed-loop and Phase 2 is not.

| Order | Phase | Loop | Reason |
|---|---|---|---|
| 1 | Phase 0 | Closed | Done. No risk. Removed a real data-loss risk. |
| 2 | Phase 1a | Closed | Nothing else can be measured without it. Backfill gives a baseline now. |
| 3 | Phase 1b | Closed | Attacks the largest problem. It is a port. The corpus proves it offline. |
| 4 | Phase 3 | Closed | Cheap. Stops the loss of every lesson. Measurable by ablation. |
| 5 | Phase 5 Q-01 | Partly | Offline generation test. Runs beside other work. |
| 6 | Phase 2 | Open | First real cut in operator work, but it needs live engagements. |
| 7 | Phase 4 | Partly | Largest value and largest cost. Needs the answer to Q-04 first. |

**Rule that produced this order:** do every closed-loop phase before any open-loop phase. The team
can finish orders 1 to 4 without starting a single new engagement.

---

## Do not do these yet

1. **Do not add more doctrine files.** The harness holds about 3 MB of prose. A promotion path that
   never completed shows that more prose does not change behaviour.
2. **Do not rebuild the record kernel** before Q-06 has an answer. The operator stopped it for a
   reason. `score-finding.py` may give the same protection at a lower cost.
3. **Do not change the goal prompts** before the Q-02 test. The seeding may be correct for a scoped
   engagement.
4. **Do not attempt Kettle scale** (many targets, many threads) before Q-05 has an answer. The
   harness design and the OSLit scope both point to depth on one target.
5. **Do not relax the anti-volume rule** in `docs/decisions/0001` before Q-03 has an answer. Separate
   generation from promotion instead.

---

## What this does not fix

The operator stays in the loop for two things. No framework in the research supports their removal.

1. The Zone-2 confirmation before an impact artifact. The action is not reversible.
2. The adjudication of `confirmed`. This is the decision stage, where silent misses hide.

The plan reduces the work around these two gates. It does not remove them.
