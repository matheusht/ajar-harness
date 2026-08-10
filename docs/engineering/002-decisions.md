# Decisions

Date: 2026-08-08.

This file separates four groups. Do not move an item between groups without a note and a date.

- Section 1: decisions that the operator confirmed.
- Section 2: findings that the team accepts as fact.
- Section 3: proposals that wait for operator approval.
- Section 4: open questions. These need a test or an operator judgement.

---

## 1. Confirmed decisions

### D-01. The record kernel is new. Low adoption is not a failure signal.

Date: 2026-08-08. Source: operator statement.

An agent reported that 20 of 27 engagements run without the kernel. The operator states that the
kernel is a new implementation. Most engagements are older than the kernel.

The date scan gives a more exact picture. Four engagements used the kernel between 2026-07-16 and
2026-07-27. Every engagement after 2026-07-27 uses documentation mode or has no kernel line.

**Effect:** do not treat low adoption as neglect. Treat the stop after 2026-07-27 as a signal that
the kernel costs more than it gives for fast engagements.

### D-03. Keep `AGENTS.md`. Enforce the mirror by machine.

Date: 2026-08-08. This corrects an earlier proposal in this same file.

The first version of the roadmap said to delete `AGENTS.md` or make it a pointer. That was wrong.
Two facts disprove it:

1. `evals/research-kernel/ab-readiness/preregistration.json` pins a sha256 of `AGENTS.md`. A change
   to the bytes invalidates a frozen preregistration record.
2. `docs/agents/domain.md` lines 27 to 28 document the mirror as intentional: "byte-identical mirror
   of CLAUDE.md — edit both together".

The duplication is a design decision, not drift. The real risk is silent divergence.

**Decision:** keep both files. Add a conformance check that compares the two hashes. This converts a
documented convention into a machine check. `tools/check-conformance.py` now holds
`check_doctrine_mirror()`.

### D-02. The A3 report is filed as Medium.

Date: 2026-08-08. Source: operator action. Advisory `GHSA-h97x-7h5v-wjx4` is published.

The severity follows the Klever program classes, which put information disclosure at Medium.

### D-04. The oracle-negative gate is NOT graduated. It stays.

Date: 2026-08-09. Source: `fixtures/preregistration/spotify-phase2-OUTCOME.md`. This answers the first
attempt at Q-07; the question stays open for a second attempt on a fresh engagement.

Two reasons, and the second is the strong one.

The run never qualified as a measurement: `preflight_holdout.py` found 6 of 6 withheld paths leaking,
so the operator moved gate graduation off this engagement (Option C).

Then the run registered seven findings on fifteen `claim_adjudication` reviews that a script
generated, with the verdict hardcoded. One reviewer identity, zero corrections, zero conflicting
evidence, three rationales. The gate under test decides by counting disagreements. **A generated
adjudicator produces zero disagreements by construction**, so a clean result would have been
unfalsifiable. This is `engine/autonomy.md` §4 — the verifier must not be the thing verified.

The run is therefore evidence against graduating this gate, not absent evidence.

Built in response: `tools/adjudication_audit.py`, the `fixtures/adjudication/` pair, the
`fixtures/finding-traps/synthetic-adjudication` trap, and a `check_adjudication` family in
`score_finding.py`. Re-running the gate now requires `adjudication_audit.py` to return `clear`, the
same way it requires the holdout preflight to return CLEAR.

---

## 2. Accepted findings

The team accepts these as fact. Section 001-evidence.md gives the source for each one.

### F-01. Adjudication has more doctrine than search.

The ratio is 4.5 to 1 by byte count.

### F-02. Two thirds of corrections arrive late.

About 65% of 147 corrections arrived one round later or more.

### F-03. The promote step has no next step.

One memory disposition file exists. It reads `promote`. It passed every check. The lesson did not
reach `winners.md`, a card, or an engine file.

### F-04. Deterministic graders exist. They grade the test suite, not the work.

`tools/score-candidate.py` never reads the judge note. No equivalent code grades a live finding.

### F-05. A model judge accepts too much.

The measured bias is toward acceptance, not toward rejection. The `default to disbelief` rule in
`CLAUDE.md` corrects a real bias. Keep the rule.

### F-06. Instructions do not stop silent misses.

Training reduces commission errors. Training does not reduce omission errors. Repeating doctrine
does not fix a missed check. Only an independent check fixes it.

### F-07. No published method proves a negative result.

The harness method in `engine/regrade.md` section 4a is new work. It is not late work.

### F-08. Autonomy has four separate stages.

Acquisition, analysis, decision selection, and action implementation each have their own level.
One global setting is the wrong model.

---

## 3. Proposals that wait for approval

The operator has not approved these. Do not start work on them yet.

### P-01. Build `tools/score-finding.py`.

Port the pattern in `tools/score-candidate.py` down one level. The code checks a finding and its
outbound documents by machine. The model cannot change the result.

Checks: every number has a re-derivation reference; every cited file exists; the severity vector
recomputes; the version pin matches; no outbound document contradicts the finding verdict.

**Reason:** this attacks F-02, the highest-volume problem. It is a port, not a new design.

### P-02. Build `tools/intervention_ledger.py` and a schema.

Record each operator correction when it happens. Give each record a stage, a class, the wrong value,
and the correct value.

**Reason:** `CLM-0001` needs this data to prove that interventions fall. The promotion path needs it
as input. The regression suite needs it as a corpus.

### P-03. Write `engine/evaluation.md`.

Each engagement must declare its cheapest mechanical check before work starts. If no such check
exists, the engagement must say so.

**Reason:** the harness has oracles but no doctrine that an evaluation primitive comes first.

### P-04. Write `engine/autonomy.md`.

Give each of the four automation stages its own level. Add the graduation method: run a gate on
standby only, count real interventions, remove the gate when the count is near zero.

**Reason:** F-08. Also, this makes `CLM-0001` measurable.

### P-05. Add an ablation fixture to the promote step.

Each `promote` must include a test fixture. The result must change when the lesson is present and
when the lesson is removed. If the result does not change, the lesson is not load-bearing.

**Reason:** F-03. No external source measures this. This is new engineering.

### P-06. Small edits.

- `engine/routing.md`: add a bounded hypothesis-generation pass when no card activates on a surface.
- `engine/gates.md`: add an egress clause. State that the fail-closed text applies only with the
  kernel.
- `engagements/_TEMPLATE/scope.md`: add the impact-maximization text. The operator has dictated it
  six times.
- ~~`AGENTS.md`: delete it, or make it a pointer.~~ **Withdrawn 2026-08-08. See D-03.**
- Track the untracked engine files in git.

---

## 4. Open questions

These need a test or an operator decision. Do not guess.

### Q-01. Does micro-inspiration work for source audit?

Kettle used RFCs. A blockchain client has specifications, but they are less exact than an RFC.

**Test:** take one target. Split its specification into fragments. Generate hypotheses. Compare the
result against the current card-based method.

### Q-02. Do the goal prompts reduce novelty?

The prompts contain 500 to 2,455 words of prior answers. Kettle measured that one example dropped
his rediscovery rate from 5% to 0%.

**Test:** run one engagement twice. Give one run the full prompt. Give the other run only the
objective and the scope. Compare the findings.

**Risk:** the harness objective is a scoped authorized target, not open discovery. The seeding may
be correct for this objective. Do not change the prompts before the test.

### Q-03. Does the anti-volume rule block ideation?

`docs/decisions/0001` section 4 says: "Volume is treated as a failure mode... New cards should earn
their place."

Kettle uses cheap over-generation. These two positions conflict. The operator must choose, or the
team must separate generation from promotion.

### Q-04. What is the evaluation primitive for white-box source audit?

Kettle has a response differential. Big Sleep has AddressSanitizer. A source audit of a blockchain
client has neither.

`IRIS` is the closest model. It uses a model to propose taint sources and sinks, then uses CodeQL
for the dataflow. This may transfer to Stage 2 and Stage 3.

**Open:** does the harness adopt a static-analysis engine as the deterministic layer? This is a large
decision. It changes the tool chain.

### Q-05. Does the harness stay deep on one target, or go wide?

Kettle tested 30,000 sites. OSLit `DEC-0015` scopes work to one system boundary.

These are different products. The harness cannot be both without a change of direction. The operator
must decide.

### Q-06. Does the kernel return?

The operator stopped using it after 2026-07-27. The reason appears to be cost against speed.

**Open:** rebuild the kernel as a lighter tool, or accept documentation mode and put the enforcement
in `score-finding.py` instead. The second option is cheaper.

### Q-07. Which gate is graduated first?

The autonomy research names three gates as habit and not principle: recon and routing snapshots,
per-attempt dispatch inside an approved scope, and re-confirmation of oracle negatives.

**Open:** the operator picks the first gate to test with the standby method.
