# Goal prompt — START an engagement (standard format)

Follow the harness [entry/resume procedure]([HARNESS_CHECKOUT]/skills/source-engagement-bootstrap/references/goal-template.md#entry-and-resume-procedure) for signed-scope/init ordering, inspector reconstruction, list/next/gate queue reads and supported runner readiness.


> **This is the standard goal-prompt format for STARTING a new engagement.** Copy it into
> `engagements/<id>/goal-prompts/<id>-goal-prompt.md` and fill every `<...>` with verified engagement
> facts. For a REVISIT / REDO / RE-RUN of an already-closed engagement (escalation-vector hunting, "was
> it exhausted?"), use `goal-prompt-REVISIT-ESCALATION.md` instead. The LLM adapts structure and detail
> to the engagement's domain; the section skeleton below is the constant. Binding gates (CLAUDE.md,
> scope.md, engine/*) always override this template.

GOAL: white-box EXHAUSTION of the <TARGET> — <PROGRAM> (program: <PROGRAM NAME>,
<PLATFORM: HackerOne/bugcrowd/immunefi/...>, rewards by CVSS: <REWARD TABLE>; policy in
program-policy.md). Audit baseline pinned: <VERSION/TAG/COMMIT> (identity recorded in authoritative source/environment records),
cloned to <LOCAL_PATH> (commit identities recorded in authoritative source/environment records). Source-only + local disposable proof
(local <ENV> instances, locally-minted <SYNTHETIC ASSET>). ROUTED to <IMPACT CLASSES: funds, resources,
consensus, availability, data, auth>. IN: <EXACT SURFACES: dirs, files, modules, entry points, sinks>.
OUT/KILL before deep work (program-policy.md + recon-signals.md): <EXPLICIT EXCLUSIONS: generated code,
third-party deps, already-fixed hardening wave as positive controls only — check for INCOMPLETE fixes,
don't re-hunt; dependency CVEs without a <TARGET>-specific PoC; previously-disclosed; any live
<NETWORK>/production>. Work to the kernel-backed, independently reviewed exhaustion terminal OR a
surviving finding, per subsystem, laddered. Binding:
CLAUDE.md, scope.md (signed <DATE> — <ZONE-2 LEVEL>), program-policy.md,
engine/{whitebox-analysis,persistence,regrade,pocinator,chainability,escalation}.md. Use the admitted inspector/queue handoff and read unique recon-signals.md context FIRST.

BUILD A CARD FIRST if a lead needs one: <VULN CLASSES WITHOUT A DEDICATED CARD>. Author a
skills/{vulns,patterns} card for the trigger class BEFORE deep grading — card-less = no oracle.
Oracle-grade it like the existing cards. Log a pattern-candidate.

PIPELINE: narrow->classify->triples->reachability->confirm->faithfulness-verify->chainability->Post
(engine/whitebox-analysis.md; jump back freely). Grading agents manage the pipeline themselves and
don't stop until every lead is exhausted and adjudicated.

CASCADING (second-order discovery discipline — every discovery is a tree branch, not an endpoint): the
best source of hypothesis inspiration is something that nobody else knows about. When a finding or
significant research discovery survives, INTERROGATE IT WITH TWO QUESTIONS: (Q1) "how can I detect
similar behavior elsewhere?" — the same shape in a sibling processor, module, or input surface; (Q2)
"does the origin of that behavior enable other attacks?" — the root mechanism as a primitive (<SEED
EXAMPLES FROM THE DOMAIN>). Explore back UP the discovery tree to find the branches you overlooked.
LOG EVERY CASCADE in cascades.md (append-only, same discipline as hypotheses): parent discovery id →
Q1 answer → Q2 answer → cascade leads (file:line, hypothesis, why real/fake, confidence) →
disposition. Every cascade lead enters the pipeline like any other hypothesis, gets multi-round graded,
and can itself cascade — this is the positive feedback loop that takes the engagement beyond predictable
findings. It's going to get messy — that's the point; the ledger is what keeps the mess productive.

OPERATING MODEL: one bounded worker by default; additional concurrency requires explicit authorization
and a concrete independent assignment. Use <PLANNING MODEL> for planning/triage and <EXECUTION MODEL>
for bounded implementation. Verify actual model/runtime availability through the entry procedure.
Rules are Stage-1 prefilters, not verdicts. Preserve independent cold verification of the complete
real pinned path, controls, replay and adjudication; record why each candidate survives or is refuted.
Distinct sequential review sessions can preserve independence without a default fleet. Human action
is required at named authority gates or when independent review is unavailable, not for routine
transcription. Bound effort by evidence, explicit budgets and the computed queue; priors allocate
work, never establish truth. A refuted lead and reviewed bounded exhaustion are valid outcomes.

KEY ROUTING (ceiling = the program's <HIGHEST/CRITICAL> classes only): (1) <ROUTING LANE 1 — the
payout class>: can <BAD ACTOR ACTION> be achieved (<mechanism>)? If yes → <IMPACT CLASS> = the payout
class (<PRECEDENT, e.g. a CVE/CARD ID> is the proven family in exactly this code). (2) <ROUTING LANE 2>:
can <BAD ACTOR ACTION> (<mechanism>)? If yes → <IMPACT CLASS>. (3) <ROUTING LANE 3>: can <BAD ACTOR
ACTION> (<mechanism>)? If yes → <IMPACT CLASS>. ... Each sub-surface: what the invariant should be, how
can this code break it, in one sentence.

AUTHORIZATION (scope.md signed <DATE> — <ZONE-2 LEVEL>): retain exact local scope and cleanup limits.
Obtain explicit human confirmation before creating any Zone-2 PoC artifact, including local benign
ones, under root policy. Keep real-network, other-user, disclosure and filing gates intact. Do NOT fabricate / reward-hack /
overclaim (escalation.md §1 marginal-contribution critique: severity = the delta the bug adds vs the
world without it, never the total nearby). PoC = a real <DOMAIN> test/script against the pinned code or
a loopback private sim, real code branches, max-impact within the local sandbox. Emit attempt always,
finding only on oracle-confirmed; operator re-authors + files (AI barred from filing); cleanup.md
logged.

FIRST MOVE: (1) complete the shared entry/resume procedure; reuse the verified pinned <LOCAL_PATH>;
(2) after signed scope, authorized initialization and runner readiness, perform the scoped environment
preflight for <TOOLCHAIN>, then the targeted test subset, recording blockers through canonical records;
(3) Stage-1
classify pass on <PRIMARY SURFACES>; (4) formal recon on the clone: complete the activation-signals
table in recon-signals.md — <DOMAIN-SPECIFIC RECON QUESTIONS: confirm the canonical-<X> question, map
every <PATTERN> site, enumerate the <CONTROL> flags and activation heights, inventory the <PROTOCOL>
types vs handlers>; (5) oracle calibration vs the program CVSS-reward table + severity corpus; (6)
select one bounded next assignment from recon-signals and the computed queue.
