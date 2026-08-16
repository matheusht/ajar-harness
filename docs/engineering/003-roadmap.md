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

## REVISION 2026-08-10 — the organising idea changed

This roadmap was written around **graduating gates**: pick a human check, run a standby experiment,
remove it. Phase 2 tried that and the answer was KEEP (`D-04`). The attempt was not wasted, but the
framing was wrong.

The better lever is **making checks decidable** (`D-07`). Every check that becomes computable is
autonomy gained while trusting nothing extra. It is a capability you build, not a risk you take.

Evidence from one session: G4 was judgement until 2026-08-09, G3 until 2026-08-10. Both now run with
no human. Neither needed an experiment or a graduation.

Gate graduation is not cancelled. It is second place.

### Status at 2026-08-10

| Phase | State |
|---|---|
| 0 Hygiene | done |
| 1a Intervention ledger | done — 62 backfilled, 3 live |
| 1b Deterministic grader | done |
| 2 Graduate a gate | attempted; answer is KEEP (`D-04`); retry needs a fresh engagement |
| 3 Learning loop | done — ablation gate |
| 4 Evaluation primitive | direction decided (`D-08`); scoped to a Go experiment |
| 5 Ideation experiments | half — tool built and used once; the Q-02 test has not run |

### Added this revision

**Phase 6 — finding lifecycle. DONE 2026-08-10.** Findings start in `unproven/`; promotion runs six
gates (`D-05`, `engine/finding-lifecycle.md`). This is the default inversion, and it is the piece that
makes an unattended run fail loudly instead of quietly.

**Phase 7 — mechanical reachability.** Workstream A of
`docs/research/static-analysis-and-knowledge-base-plan.md`. Licence question first, then a Go
experiment producing a miss rate. Confirm only, never kill.

**Phase 8 — cross-engagement memory.** Workstream B of the same plan. One format, two entry kinds,
JSONL in git, gated by the existing ablation rule. Changes order, never kills (`D-09`).

**Phase 9 — make G1 and G2 computable. PARTIAL 2026-08-13.** G2 now resolves v3 control refs against
`attempts.jsonl`, rejects replay/control role collisions, and checks `kind` plus held/no-signal
outcome. Its attestation remains; legacy flat v1 packages remain attestable until migrated. G1 still
needs machine-readable execution context. This is autonomy under `D-07`: the gate stayed, while more
of its decision became decidable.

### Revised order

| Order | Phase | Why |
|---|---|---|
| 1 | Phase 8 — memory | no decision blocks it; the only compounding machinery identified |
| 2 | Phase 9 — finish G1 + migrate legacy G2 records | small, closed-loop, direct autonomy gain |
| 3 | Phase 7 — reachability | high value, needs the licence answer and the experiment first |
| 4 | Phase 2 retry | needs a fresh engagement with no answer key |
| 5 | Phase 5 Q-02 | rides on a real engagement we run twice; not scheduled alone |

---

## Priority order and reason (superseded 2026-08-10 — kept for the record)

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

---

## REVISION 2026-08-16 — three phases closed, and the ceiling relocated

### Status corrections

**Phase 3 — DONE.** `tools/ablation.py` and `check_ablation_fixtures()` already existed and already
asserted that every `promote` disposition carries a fixture proving the lesson changes a verdict.
What was missing was WHERE that lived: enforcement sat in conformance, noticed after the record was
written, and the disposition-to-fixture link was inferred by matching ids against directory names.
`ablation_fixture` is now a schema property, conditionally required when `disposition == "promote"`.
It blocked six fixture records on its first run. A `defer` owes nothing — demanding a fixture there
would push authors toward a weaker disposition to dodge the work.

Deliberately NOT done: the "open a draft PR on each promote" step. Auto-opening PRs is an outbound
side effect on every promotion and trip-wire 5 covers outbound contact. If wanted, it is an explicit
operator command, not a hook.

**Phase 6 — DONE** (2026-08-10, unchanged).

**Phase 9 — DONE 2026-08-16.** All three attestable gates now resolve against `attempts.jsonl`:
G2 (control resolves to held/no_signal, role-disjoint), G1 (primary resolves to a signalling
non-control record), G6 (`established_by` resolves when it is an attempt ref). Legacy handling is
uniform: a ledger with no addressable records passes with a stated caveat rather than a false block,
because blocking there is an alarm about the format, not about the package.

### Added this revision

**Phase 10 — depth instrumentation. DONE 2026-08-16, effect UNMEASURED.** Partials in `unproven/`
with declared `stages`, `ceiling-requests.md`, and `primitive-registry.md` in the template. See
Decision 0011. These exist because an audit found `unproven/` empty in two of three post-gate
engagements and the primitive registry holding 1 row in the engagement where composition is the
characteristic bug shape. **Whether they change outcomes is the next thing to measure, not to
assume.**

**Phase 11 — external calibration. STARTED, blocked on operator data.**
`tools/disposition_ledger.py` + `schemas/disposition.schema.json`. 5 records, 1 graded; the floor is
5 graded before `calibrate` issues a verdict. This is the only ground truth the harness will ever
have — every internal audit shares the priors of the thing it measures.

### What the audits changed about the plan

The roadmap assumed the binding constraint was tooling. Two audits say otherwise.

1. **The gates have blocked ZERO promotions out of twelve.** They have never had to say no. That is
   consistent with a well-calibrated stack and with an untested one, and no current data separates
   them. Gate count is not a target; a gate that has never blocked is unproven.
2. **The ceiling is AUTHORIZATION, not rigor.** The Supply-Chain top band ($31,337) requires
   demonstrating impact on live third-party infrastructure, which scope forbids. That fully explains
   a Medium/Low severity ceiling with no appeal to over-rigorous judging. The operator's standing
   instruction is that scope widens when a ceiling needs it — which makes surfacing the request the
   binding step, not loosening a gate.
3. **The stall is the last inch.** 12 of 13 engagements that produced a report are parked at
   "drafted, operator files"; drafts land 0-2 days after scope and then sit 28-36 days.

### Revised order

| # | Item | Why |
|---|---|---|
| 1 | **Phase 2** — graduate a gate | 3 of 4 steps remain; standby instrumentation is reversible and unblocks the rest |
| 2 | **Phase 11** — fill the disposition ledger | blocked only on operator data; the only external calibration that exists |
| 3 | **Measure Phase 10** | partials and primitives are shipped and unproven; measure before building more |
| 4 | Phase 8 — cross-engagement memory | the only compounding machinery identified |
| 5 | Phase 7 — reachability | **licence answered 2026-08-16**: CodeQL permits analysis of OSI-licensed codebases hosted on GitHub, including automated/CI database generation. It restricts by CODEBASE type, not by business model — so it is licensed for every OSS VRP target and NOT for the private commercial ones. Scope Phase 7 to OSS targets, TypeScript first. |
| 6 | Phase 4 — evaluation primitive | needs Q-04's scope settled; direction already decided (D-08) |

### Not a substitute for CodeQL, recorded so it is not re-litigated

`vercel-labs/deepsec` was evaluated 2026-08-16 by reading its source. Its `MatcherPlugin` contract is
`match(content: string, filePath: string)` — one file's text and its path is the entire input. 200
matchers, all regex, no parser dependency, zero occurrences of taint/dataflow/interprocedural across
its docs. It is a candidate finder plus an LLM reviewer: architecturally the same funnel this harness
already runs, and its matchers map onto our Stage-1 rules. Using it as the confirmer would be a model
confirming a model, which D-08 forbids. Worth watching as a peer product; not a component.
