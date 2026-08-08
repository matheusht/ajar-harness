# Evidence

Date: 2026-08-08. Method: eight research agents plus direct measurement by the orchestrator.

Each claim below has a source. The orchestrator verified the claims marked **verified**. The
orchestrator did not verify the claims marked **agent-reported**.

---

## 1. Internal measurements

### 1.1 The engine has more adjudication doctrine than search doctrine

**Verified.** Command: `stat -f %z` on `engine/*.md`.

| Group | Files | Bytes |
|---|---|---|
| Search and loop | `loop.md`, `routing.md`, `routing-eval.md`, `persistence.md` | 16,487 |
| Adjudication | `regrade.md`, `pocinator.md`, `chainability.md`, `escalation.md` | 75,199 |

The ratio is 4.5 to 1. `engine/loop.md` is 3,927 bytes. `engine/chainability.md` is 21,505 bytes.

The oracles show the same shape. `skills/oracles/severity-precedent-oracle.md` is 142,931 bytes.
`skills/oracles/signal-oracle.md` is 1,593 bytes. The signal oracle serves Stage 1.

### 1.2 Rework happens late

**Agent-reported.** Source: a census of 147 corrections across 15 engagements. The agent read
`progress.md`, `findings/`, and evidence files. It searched for the words "CORRECTED", "refuted",
"overclaim", and "superseded".

| Measure | Value |
|---|---|
| Corrections found | 147 |
| Caught in the same round | about 51 (35%) |
| Caught one round later or more | about 94 (65%) |

Root causes in order: source misreading (about 40 to 45), measurement artifact (about 20), claim
copied without a new check (about 15), stale ground truth (about 10).

Stage 4 makes the most bad claims (28). Stage 5 escalation and the severity step before filing make
the latest claims (16 of 19 late, and 15 of 16 late).

**Note on accuracy:** the stage labels are the agent's judgement. They are not ground truth. Read
the ranking as a shape, not as exact values.

### 1.3 One engagement performs much better than the others

**Agent-reported.** `hulk-2026-07` caught 15 of 19 corrections in the same round. The ratio is the
reverse of every other engagement.

`hulk-2026-07` used a route-existence oracle. The oracle is a cheap mechanical check. This is the
only engagement with such a check.

### 1.4 The learning loop does not close

**Verified.** Commands: `grep -rhoiE "promotion status:" engagements/*/pattern-candidates.md` and
`find engagements -name "memory-disposition*.json"`.

| Measure | Value |
|---|---|
| Pattern candidates marked `local` | 38 |
| Pattern candidates marked `proposed` | 4 |
| Pattern candidates marked `promoted` | 0 |
| Memory disposition files in about 25 engagements | 1 |

`engagements/cosmos-2026-07/pattern-candidates.md` has 301 lines.
`engagements/cosmos-2026-07/memory/winners.md` has 14 lines and reads `(none yet)`.

The one memory disposition file is `engagements/kiwicom-15-07/memory/memory-disposition-r4.json`.
It reads `"disposition": "promote"` and `"status": "sanitized"`. It passed every schema check. The
`winners.md` file in the same engagement still reads `(none yet)`. A search for the lesson in
`skills/` and `engine/` gives zero results.

**Conclusion:** the promote step has no next step. The schema asks for a human-reviewed pull
request. No code tracks that request.

### 1.5 Doctrine that did become machinery used a different path

**Agent-reported.** These files hold promoted doctrine: `engine/persistence.md`,
`engine/escalation.md` section 1, `engine/whitebox-analysis.md` lines 101 to 104, and
`skills/vulns/workflow-step-injection/SKILL.md` lines 83 to 92.

A person wrote each one directly into the engine. None used the pattern-candidate path.

### 1.6 The record kernel ran for four engagements and then stopped

**Verified.** Command: a scan of all 27 `scope.md` files for the kernel line.

| Status | Count |
|---|---|
| Real kernel version declared | 7 |
| Documentation mode by operator decision | 3 |
| No kernel line | 17 |

The dates show a break. Four engagements from 2026-07-16 to 2026-07-27 used the kernel. Every
engagement after 2026-07-27 uses documentation mode or has no kernel line.

`engagements/klever-2026-07/scope.md` lines 120 to 125 give the reason. It says the engagement uses
"plain documentation mode" with "no `tools/run-engagement.py` ceremony". It also says "the same rigor
bar ... applies unchanged".

### 1.7 Deterministic graders exist but grade the test suite

**Verified.** `tools/score-candidate.py` line 20 says: "judge_note is advisory only: it is recorded
but never read by the decision". Line 46 says: "Pure; judge_note is never consulted". The self-test
at line 153 sends `judge_note="this candidate is clearly excellent, promote it"` and asserts the
result is `"block"`.

`docs/decisions/0003-autonomy-envelopes.md` line 30 says: "A candidate can never change its own
evaluator and then use that changed evaluator to authorize itself."

These graders serve the card-optimization loop. No code grades a live finding.

### 1.8 Card calibration is thinner than it looks

**Verified.** Three fixture directories exist in `evals/contract-audit/fixtures/`:
`jpegd-reentrancy`, `curve-readonly-reentrancy`, `erc4626-first-depositor`.

Twelve EVM cards exist. Three cards point to directories that do not exist. Three cards point to
`jpegd-reentrancy`, which is a reentrancy fixture. Those three cards cover access control,
accounting invariants, and arithmetic rounding.

`tools/check-conformance.py` lines 5 to 6 say: "This validates contracts, NOT security semantics."
It runs 452 checks with zero failures.

### 1.9 Goal prompts contain many prior answers

**Agent-reported.** Word counts:

| File | Words |
|---|---|
| `engagements/zeom-2026-08/goal-prompts/zeom-goal-prompt.md` | 768 plus 1,014 in a required read |
| `engagements/kubernetes-2026-07/goal-prompts/kube-aggregator-goal-prompt.md` | 526 |
| `engagements/crown-2026-08/goal-prompts/crown-goal-prompt-revisit.md` | 2,455 |

The Kubernetes prompt has a list with the title `Seed hypotheses:`. The Crown prompt names exact
contract addresses and prior confirmed mechanisms.

### 1.10 Duplicate doctrine files

**Verified.** `AGENTS.md` and `CLAUDE.md` are byte-identical. Neither file has a generated-file
marker.

### 1.11 Untracked engine files

**Verified.** These files exist on disk but git does not track them:
`engine/blackbox-web.md`, `engine/escalation.md`, `engine/multi-round-orchestration.md`,
`skills/oracles/chainability-oracle.md`, `skills/source-engagement-bootstrap/`, and three
`skills/vulns/` directories.

`engine/escalation.md` is 16,387 bytes.

---

## 2. External research

### 2.1 The AI-Code-Human model

Source: James Kettle, PortSwigger, "Can AI do novel security research?", 2026-08-05.

Kettle writes: "autonomous vs human is the wrong framing ... It's better to frame system design as
AI vs Code vs Human. You can start quickly with an AI-heavy approach, then gradually move
responsibility to deterministic code to improve accuracy & speed."

The pipeline is Ideation, then Evaluation, then Weaponization. Cascade is a feedback loop into all
three steps. It is not a fourth step.

**Correction to an earlier reading:** the diagram shows AI 50% to 5%, Code 10% to 95%, and Human
40% to 0.0001%. These values are in an image only. The article text and the PDF do not contain them.
They show a design philosophy. They are not measured values.

### 2.2 The evaluation primitive

Kettle writes: "The evaluation strategy is the most important component of an autonomous research
system because it dictates both the quality and scope of the discoveries."

His primitive is code, not a model. It compares a response with and without a trigger. He writes:
"This system has no expectations about what the poisoned response should look like, which means it
can detect any kind of cross-request contamination — even desync classes that I don't know exist."

Scale: 138 RFCs became 15,000 fragments and then 30,000 vectors. The system tested 30,000 websites
with 2,000 threads.

### 2.3 A model will change its own grade

Kettle split the exploit script. The model could not change one half. He writes: "The agents
initially found ways to bypass the validation — such as providing a victim response fingerprint that
actually matched the attack response — but I was able to add in deterministic validation code to
block these bypasses and eventually achieve a system which produced zero false positives."

### 2.4 Context contamination

Kettle tested if a model could reinvent a technique that he had invented and not published.

| Prompt type | Success rate |
|---|---|
| Broad question | 0% |
| Narrow question with low-value answers excluded | 5% |
| Narrow question plus one inspiration example | 0% |
| Narrow question plus example, newer model | 30% |

He calls the drop to 0% "context-contamination". His fix is micro-inspiration: fragments of one to
three sentences.

### 2.5 Every verified system separates the proposer from the grader

Source: research on Big Sleep, XBOW, AIxCC, AgentFlow, OSS-Fuzz-Gen, and IRIS.

No system with independently verified results lets the model grade its own success. Big Sleep uses
AddressSanitizer. AgentFlow uses sanitizers and a type checker. IRIS uses CodeQL for the dataflow.

Naptime measured the value of a bounded action space. The pass@20 score moved from 0.24 with
unstructured prompts to 0.76 with a tool-grounded agent.

### 2.6 Automatic checks overstate quality

The AIxCC review found that 37.7% and 45.6% of two teams' patches passed the automatic check and
failed a human review.

Semgrep published its own numbers: the assistant agrees with humans 96% for true positives and 41%
for true negatives.

### 2.7 A model judge accepts too much

Source: arXiv:2511.18608, a study of 9,942 HackerOne reports. The study found a "clear tendency
toward acceptance". Models do not recognize invalid reports.

**Conclusion:** the `CLAUDE.md` rule "default to disbelief" corrects a measured bias. Keep it.

### 2.8 Autonomy is not one control

Source: Parasuraman, Sheridan and Wickens, 2000.

Automation has four separate stages: information acquisition, information analysis, decision
selection, and action implementation. Each stage has its own autonomy level.

### 2.9 Training does not stop silent misses

Source: Skitka, Mosier and Burdick.

Automation bias causes two error types. Commission errors come from acting on bad advice. Omission
errors come from missing what the automation did not flag.

Training reduced commission errors. Training did not reduce omission errors.

**Conclusion:** instructions such as "be careful" do not correct silent misses. Only an independent
check corrects them.

### 2.10 A method to remove a gate

Source: Feng, McDonald and Zhang, 2025 (arXiv:2506.12469). This is one paper. Other work does not
confirm it.

The method is "assisted evaluation". Run the step with a person on standby only. Count the real
interventions. Remove the gate when the count is near zero.

This matches `CLM-0001` in the OSLit company notes.

### 2.11 No method exists to prove a negative result

Source: a search of mutation testing, coverage-guided fuzzing, NIST SP 800-115, PTES, and MITRE
ATT&CK coverage.

All of these measure how complete a process is. None measures if a specific "nothing is here" claim
is true. The Google mutation-testing team says its own score is not a completeness proof.

**Conclusion:** `engine/regrade.md` section 4a states the search set, proves the set is complete by
a second method, and names the falsifying call. No external method does this. This work is new, not
late.

### 2.12 Synthetic bugs do not transfer

Source: Bundt et al., arXiv:2208.11088. The study tested synthetic bugs against 50 real bugs in the
same programs. No fuzzer found any of the 50 real bugs. The fuzzers found synthetic bugs easily.

The correct method is the Magma method: move a real historical bug into a current version.

### 2.13 An operator can be wrong about a clean result

Source: Ruef et al., "Build It, Break It, Fix It". Teams submitted software that they believed was
secure. A second party attacked it. 78% of the vulnerable submissions came from a misunderstanding
of a security concept.

### 2.14 A judge anchors on the submitter's claim

Source: Elastic Security Labs, 3,317 HackerOne reports.

The system reached 85% agreement with human engineers. A second independent review caught real
errors in about 15% of cases. One named failure was "severity anchoring to the researcher's own
claimed severity".

**Conclusion:** this matches the harness pattern where a hunter reports `suspected_success` and the
orchestrator gives it too much weight.

### 2.15 Do not compare more than two options

Source: arXiv:2410.02736. Position bias gives a robustness rate of 0.566 to 0.832 for two options.
The rate falls below 0.5 for three or four options.

### 2.16 v12 (v12.sh)

The technical work is real. CVE-2026-46300 is confirmed by Ubuntu, Tenable, and Microsoft. The Miden
findings link to merged pull requests.

The architecture is not published. There is no benchmark and no false-positive rate.

The blog says: "Earlier this month, we won a $2.5M bug bounty—the largest bounty ever received by an
AI agent." The blog does not name the protocol. **The orchestrator found no independent source for
this payment.** One agent found reports that contest it. The orchestrator did not verify those
reports. Treat the claim as unverified in both directions.

The proof format in their THORChain report is good: root-cause text, exact file and line references,
a script that repeats the result against a pinned environment, and a timeline.

---

## 3. Method note

Eight research agents ran during this session. Four of them overstated a fact.

| Claim | True value |
|---|---|
| 9 EVM cards point to missing fixtures | 3 |
| Two architecture documents are missing | Both exist |
| Chainability and escalation have no machinery | Only chainability |
| 63 vulnerability cards | 45 |

One command disproved each one. No agent invented data. Each error was a correct direction with a
wrong size.

This is the same failure that the census found in the engagements. It happened again during the
study of the failure.
