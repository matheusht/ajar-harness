# Goal prompt — START an engagement (standard format)

> **This is the standard goal-prompt format for STARTING a new engagement.** Copy it into
> `engagements/<id>/goal-prompts/<id>-goal-prompt.md` and fill every `<...>` with verified engagement
> facts. For a REVISIT / REDO / RE-RUN of an already-closed engagement (escalation-vector hunting, "was
> it exhausted?"), use `goal-prompt-REVISIT-ESCALATION.md` instead. The LLM adapts structure and detail
> to the engagement's domain; the section skeleton below is the constant. Binding gates (CLAUDE.md,
> scope.md, engine/*) always override this template.

GOAL: white-box EXHAUSTION of the <TARGET> — <PROGRAM> (program: <PROGRAM NAME>,
<PLATFORM: HackerOne/bugcrowd/immunefi/...>, rewards by CVSS: <REWARD TABLE>; policy in
program-policy.md). Audit baseline pinned: <VERSION/TAG/COMMIT> (identity recorded in progress.md),
cloned to <LOCAL_PATH> (commit identities recorded in progress.md). Source-only + local disposable proof
(local <ENV> instances, locally-minted <SYNTHETIC ASSET>). ROUTED to <IMPACT CLASSES: funds, resources,
consensus, availability, data, auth>. IN: <EXACT SURFACES: dirs, files, modules, entry points, sinks>.
OUT/KILL before deep work (program-policy.md + recon-signals.md): <EXPLICIT EXCLUSIONS: generated code,
third-party deps, already-fixed hardening wave as positive controls only — check for INCOMPLETE fixes,
don't re-hunt; dependency CVEs without a <TARGET>-specific PoC; previously-disclosed; any live
<NETWORK>/production>. Work to the kernel-backed, independently reviewed exhaustion terminal OR a
surviving finding, per subsystem, laddered. Binding:
CLAUDE.md, scope.md (signed <DATE> — <ZONE-2 LEVEL>), program-policy.md,
engine/{whitebox-analysis,persistence,regrade,pocinator,chainability,escalation}.md. Read
recon-signals.md + progress.md FIRST.

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

OPERATING MODEL: filter 9,999 fakes for the 1 real, NOT find sinks. FLEET of hunters
(one/sub: <DIVERSE LENS ROSTER PER TARGET — taint/sink, concurrency/TOCTOU, dependency-CVE-reachability,
unicode/encoding, numeric/serialization, protocol/state, framework-internals, by-design-vs-gap, plus
domain-specific lenses>), keep-biased; rules = Stage-1 pre-filter only — rules misclassify, miss what an
LLM would find, and overmatch; every binary is a black box, so NEVER let one source kill a potential
payout. NEVER one-pass kill OR bless: multiple genuinely independent keep-biased grading rounds, each
adds NEW signal, log every kill — LLM grading top-to-bottom + harness rules + human double-checking,
and the grading agents keep going until all leads are exhausted. Faithfulness pass = FRESH context: the
PoC must exercise the REAL pinned code path the real control flow executes (real build, real runtime,
real network where applicable) — a fuzzer/emulator that replicates a sink without the real path is a
REWARD-HACK and the #1 way a real bug gets closed; "did the state change / was the exception thrown" is
only meaningful against the real execution path. Understand the WHOLE exploit, not the sink: know what's
real vs fake BEFORE verifying, and give a one-sentence "why it's real" per survivor. MODELS: <PLANNING
MODEL> = planning, triaging, finding candidates, writing the pipeline, debugging issues; <EXECUTION
MODEL> = the long-horizon grunt (<DOMAIN-SPECIFIC PoCs>, fuzzers, instrumentation, private-net sims —
tens of thousands of lines when required). Don't invert. RUN LONG: up to <N> subagents, 6+ hours
straight, no check-in until the kernel-backed exhaustion terminal or a surviving finding; document every
hypothesis/escalation/chain/kill; 100% exhaustion of enumerated leads — no shortcuts, "it's possible, if
you give up you're not trying hard enough"; a held vector is a wrong turn to revisit, not a dry verdict.
Be more stubborn than the developer was careful.

KEY ROUTING (ceiling = the program's <HIGHEST/CRITICAL> classes only): (1) <ROUTING LANE 1 — the
payout class>: can <BAD ACTOR ACTION> be achieved (<mechanism>)? If yes → <IMPACT CLASS> = the payout
class (<PRECEDENT, e.g. a CVE/CARD ID> is the proven family in exactly this code). (2) <ROUTING LANE 2>:
can <BAD ACTOR ACTION> (<mechanism>)? If yes → <IMPACT CLASS>. (3) <ROUTING LANE 3>: can <BAD ACTOR
ACTION> (<mechanism>)? If yes → <IMPACT CLASS>. ... Each sub-surface: what the invariant should be, how
can this code break it, in one sentence.

AUTHORIZATION (standing, scope.md signed <DATE> — <ZONE-2 LEVEL>): Zone-2 open+autonomous **for benign
non-destructive proofs in the disposable owned local environment**. Build any local PoC and ESCALATE
each confirmed bug to MAXIMAL demonstrated impact (never under-demonstrate; push INSIDE local scope,
don't expand surface). ONE hard stop for fresh human confirm: anything touching a real <NETWORK>/
production, real funds/accounts/keys, third-party systems, or any submission/public-disclosure step.
The fresh-confirm gate is NOT waived for live-harm/other-user actions. Do NOT fabricate / reward-hack /
overclaim (escalation.md §1 marginal-contribution critique: severity = the delta the bug adds vs the
world without it, never the total nearby). PoC = a real <DOMAIN> test/script against the pinned code or
a loopback private sim, real code branches, max-impact within the local sandbox. Emit attempt always,
finding only on oracle-confirmed; operator re-authors + files (AI barred from filing); cleanup.md
logged.

FIRST MOVE: (1) clone + pin <TARGET>: shallow clone of <TAG> + fetch <BRANCH> HEAD; record both commit
identities in progress.md; (2) environment preflight — <TOOLCHAIN: JDK/gradle, node, go, cargo, etc.>,
build the pinned source, then the targeted test subset (record any blocker verbatim); (3) Stage-1
classify pass on <PRIMARY SURFACES>; (4) formal recon on the clone: complete the activation-signals
table in recon-signals.md — <DOMAIN-SPECIFIC RECON QUESTIONS: confirm the canonical-<X> question, map
every <PATTERN> site, enumerate the <CONTROL> flags and activation heights, inventory the <PROTOCOL>
types vs handlers>; (5) oracle calibration vs the program CVSS-reward table + severity corpus; (6)
route to per-family hunters per recon-signals.
