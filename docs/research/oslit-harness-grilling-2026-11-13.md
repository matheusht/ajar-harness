# OSLit harness: operator decisions from the November grilling

**Status:** Agreed design requirements through Q30. Q1–Q29 were recorded
13 November 2026; runtime/duration corrections and Q30 were agreed on 14 November.
The design discussion was documentation-only. A subsequent assignment on
14 November authorized the full M0–M6 implementation and engineering verification;
see the [delivery record](oslit-implementation-2026-11-14.md). These choices are not
implemented-capability claims, qualification results, adoption, or permission to
run a research engagement. The fresh-target test remains operator-owned.

**Source:** The operator's answers to Q1–Q30 in the `technical oslit` chat,
thread `01a0728c-7cc1-7003-b9f9-c30ed7fbde8b`. Short quoted phrases below identify
the approving replies. Later corrections are included with the decision they
change. Assistant recommendations alone are not recorded as agreement.

Read this before planning the next harness improvement, agent-team coordination,
or its acceptance evaluation. It updates the planning choices in the
[12 November foundation brief](oslit-research-foundation-2026-11-12.md), while
preserving that brief's dated source observations. The
[product direction](../wiki/product-and-engineering-direction.md) supplies the
broader rationale; [native status](../wiki/native-research-status.md) and its
source evidence remain separate from this design record.

## Destination and work boundary

Build a general autonomous security researcher. From an authorized target, goal,
available access, and resources, the agent owns setup, hypotheses, experiments,
adaptation, independent checks, internal results, and cleanup. It can pursue
connected effects over long investigations and carry useful work across
interruptions. Patching applies when the goal calls for it. A threat model is
one research aid, not the organizing objective of the harness improvement.

The intended internal workflow completes under its initial authorization without
routine mid-run human approvals or research directions. Optional operator steering
is supported separately, as recorded in Q12.

The current work concerns a capable single engagement and the team operating
inside it. The operator will provide the fresh-target test when the time comes.
The assistant is not assigned to perform that test or the native-agent comparison.
Target-specific facts must not define the general architecture. Future engineering
checks are distinct from this acceptance test and cannot substitute for its
research evidence. Existing runtime gates and historical engagement contracts
are unchanged by this planning document.

## Recorded choices

### Q1 — Improve the engagement first

Focus now on autonomous research within one engagement. Cross-engagement memory
and self-learning come later. Reusable improvements must be tested before
adoption. Agent-driven improvement of shared tools and methods between engagements
is deferred. Building useful tools during an active engagement remains in scope.

Approval: "cross engagement memory and this self learning comes next and later."

### Q2 — Agent-owned environment and internet access

The agent can research online and obtain the tools and dependencies it needs
within the authorized scope and resources. It sets up and adapts its own
environment; supplied target-specific setup commands are not a prerequisite.
Record sources, versions, and reproducible setup instructions for local and
remote environments.

Approval: "it should set up its own environment and get the tools and dependencies."

### Q3 — One lead, specialists, and shared coordination

One lead researcher owns the goal, verifies specialist work, and owns the final
result. It uses specialists when useful. The team shares a task queue and
knowledge base for questions, directions, experiments, findings, and learnings.
The lead monitors progress and goal drift and redirects work as evidence changes.
This shared knowledge belongs to the active engagement and is in scope now;
it is distinct from Q1's deferred cross-engagement learning.

Approval: "one lead researcher and specialists when useful" and "message board/knowledge base shared with agents."

### Q4 — Persistence with reviewed early endings

The harness must maintain the goal rather than accept a worker's unsupported
decision to stop. Failure of one approach does not end the investigation. The
lead should investigate whether low-severity effects can connect into greater
impact. A reviewer can send the team back to investigate concrete overlooked
paths or experiments. Reviewed early ending is allowed; endless activity is not
required merely because resources remain. Preserve unexplored and unresolved
work, and distinguish a refuted hypothesis from a blocked test.

Approval: "allow reviewed early ending" and "the reviewer should be able to send them back to investigate more."

### Q5 — Adapt to source, binaries, and running applications

The same general research system must work from source code, a binary, a running
application, or a combination. The agent chooses its methods from the access it
has. Source access is not a universal input requirement.

Approval: "the agent should adapt to whatever access it has."

### Q6 — Goal-directed depth and reassessment

Prioritize the strongest evidence-backed path toward the goal. Keep unexplored
surfaces visible and clearly documented. The lead reassesses and redirects
specialists as results arrive. Research capability is the present priority;
product-specific budget optimization belongs to later OSLit product work.
Resource records can explain results, and explicit authorized limits still apply;
the direction is not an unlimited spending grant.

Approval: "prioritize the strongest path toward the goal" and "dont worry about budget most of the cases."

### Q7 — Authorized remote laboratories when available

Use available, authorized remote infrastructure when the investigation needs it.
The agent handles setup, verifies that the environment is suitable, and cleans
up its resources. Remote infrastructure is optional, not an assumed entitlement
or a prerequisite for every run. Unavailable required infrastructure is a specific
blocker, not a security conclusion.

Approval: "using infrastructure authorized if there are any."

### Q8 — The original goal determines successful completion

Close a bounded objective after verification and review establish that it was
met. Continue a broad investigation beyond the first finding when its goal
requires more work. Document remaining leads and coverage limits in either case.
One successful chain does not imply that the whole target was exhausted.

Approval: "follow the original goal" and "keep going on broad investigations."

### Q9 — Working autonomy and added research value

Acceptance requires autonomous operation and improved research compared with a
capable native agent using the same model and target access. Compare verified
results, missed paths where assessable, false claims, recovery, and human
intervention. Simplify or remove mechanisms that add no value. Agent counts,
activity, code volume, and passing mechanical checks do not establish the gain.

Approval: "it needs to work autonomously and actually improve research compared to the native agent."

### Q10 — Fresh real targets across all three access modes

Evaluate unrelated real targets spanning source code, binaries, and running
applications. The agent adapts and builds its own instruments. Engineers do not
supply custom research steps to make a target pass. The operator will provide a
fresh real target; it begins the evaluation rather than replacing the agreed
coverage of unrelated targets and access modes.
Plan real evaluation coverage of chaining without supplying its research path
or assuming that every fresh target contains a vulnerability.

The later ownership correction is explicit: "You wont perform that test, we will
provide a test on a fresh target when time comes." The criteria here describe
the intended evidence; they do not assign test execution to the assistant.

The later instruction "We will provide a fresh target, no synthetic one"
updates the earlier evaluation discussion. Synthetic targets or planted
challenges cannot substitute for this acceptance evidence. A known defect or
supplied answer is not a required input. Preserve unsuccessful runs as well as
successes; a finite set demonstrates only the transfer actually observed.

Approval: "test across all three access modes on unrelated targets."

### Q11 — Human assessment after autonomous runs

Independent human assessment is allowed after the harness and baseline have
finished their investigations. Each must complete its own verification, internal
result, and cleanup first. Evaluators can assess evidence, attempt reproduction,
and identify missed opportunities afterward; they provide no research assistance
during an autonomous evaluation run. A real target has no complete answer key,
so finding counts alone cannot establish superiority or absence of flaws.

Approval: "human review after the runs is fine, but no hints or help during the investigation."

### Q12 — Initial hypotheses and recorded operator directions

An ordinary engagement may start with a suspicion, such as believing an RCE
exists. That is a hypothesis to test, not a conclusion the agent must manufacture.
Both comparison arms receive the same declared starting information.

The operator can add directions or redirect an ordinary engagement mid-run
without restarting it. Preserve completed work, record the intervention, and
let the lead revise priorities within the authorized scope. Use the operator's
preferred term **directions** for this steering. Record what was supplied instead
of conflating an initial goal with a detailed research hint. Later intervention
changes the autonomy claim; it does not invalidate otherwise sound evidence.

Approval: "preserve the work and record the intervention so we dont call it unassisted"; clarification: "steering the model into certain directions."

### Q13 — Isolate experiments; share knowledge

Specialists normally use separate workspaces and target instances while sharing
the task queue and knowledge base. Coordinate access and state changes when the
target cannot be copied. The lead combines work to test chains and other useful
experiments. Isolation must support the investigation rather than prohibit
experiments that need shared state.

Approval: "isolate experiments by default but share the task queue and knowledge base."

### Q14 — The lead controls team expansion

Only the lead creates agents and owns team expansion and priorities. Specialists
can create follow-up tasks, share leads, communicate, and request collaborators.
The lead can assign an existing specialist or create another one. Specialists
spawning agents is deferred; a later experiment may justify changing this rule.
Harness-controlled lead replacement is the recovery exception recorded in Q27.

Approval: "keep agent creation with the lead" and "not for now."

### Q15 — Specialists claim ready work

Specialists independently claim ready tasks from the lead-prioritized shared
queue, with one accountable owner per task. The lead can assign, redirect, or
reassign work when needed. Specialists choose experiments within their task;
the queue tracks meaningful research questions rather than every tool call.

Approval: "let specialists claim ready tasks from the lead-prioritized queue, one owner per task."

### Q16 — Test competing explanations; review when needed

The lead can first investigate specialist disagreements through experiments that
distinguish competing explanations. Preserve conflicting observations and keep
uncertainty visible when evidence is inconclusive. Unrelated research can
continue. The lead may also spawn fresh independent review during the
investigation whenever needed; experiments are not a prerequisite that prevents
it from requesting review.

Independent review remains required for final claims and closure. This does not
remove the earlier review requirement for abandoning strong leads.

Approval: "let the lead test competing explanations first and keep uncertainty visible" and "if necessary it can spawn independent review aswell."

### Q17 — Fresh reviewer context and complete evidence access

The independent reviewer starts in a fresh context with an evidence packet:
the precise claim, scope and attacker assumptions, reproduction artifacts,
supporting and contrary observations, and unresolved limits. Include relevant
contrary evidence directly rather than leaving it for the reviewer to discover.
The reviewer can inspect the full knowledge base and run its own checks.
Fresh context is a means of independent challenge, not evidence that validation
has succeeded.

Approval: "fresh context with an evidence packet and access to the full knowledge base" and "let the reviewer run its own checks."

### Q18 — Isolate failures and reconcile uncertain effects

When a specialist or laboratory fails, preserve the affected task's evidence
and state, inspect what happened, and recover or reassign it. Continue work that
is independent of the failure. Check uncertain effects before retrying an action
that may already have changed the target. Pause every task that depends on the
same uncertain state until that state is understood. A failure in an isolated
laboratory does not automatically pause the whole engagement.

Approval: "isolate failures and keep unaffected work going" and "check uncertain effects before retrying and pause anything depending on that state."

### Q19 — Flexible model choice; separate comparative experiments

The lead may choose different available models for specialists and reviewers
when useful; model diversity is optional. Record the model used for each role
and preserve work when assignments change. Different models do not by themselves
establish independent validation.

Keep the initial harness-versus-native-agent comparison on the same model.
Evaluate mixed-model teams separately so improvements from model choice can be
distinguished from the harness's contribution.

Approval: "allow different models when useful, but keep the initial comparison on the same model and test mixed-model teams separately."

### Q20 — Retain useful specialist context and preserve handoffs

Retain a specialist across related tasks while its accumulated understanding
remains useful. The lead can replace or retire it when needed, including when
the work changes or a fresh perspective would help. Save useful knowledge,
experiments, and unresolved questions so another agent can take over without
depending on the original session's memory. Independent reviewers still start
with fresh contexts as agreed in Q17.

Approval: "retain specialists while their context is useful, let the lead replace them when needed, and save their work so others can take over" and "keep reviewers fresh."

### Q21 — Preserve the native baseline's normal capabilities

The native-agent baseline retains its normal capabilities, including built-in
delegation where available. Give it the same model, target, goal, starting
directions, access, and authorized infrastructure. It may use its native tools
and build research instruments without installing the OSLit candidate. Do not
restrict it to one worker merely to create a contrast with the harness's team.
The comparison must measure the harness's contribution over a capable native
setup, not an artificial restriction of the baseline.

Here, "native agent" means a capable coding agent in its normal working
environment without the OSLit candidate. The exact runtime and baseline
configuration have not yet been selected for this evaluation.

Approval: "let the native agent use all its normal capabilities, including delegation, with the same model and access."

### Q22 — Require real positive evidence and retain negative results

Acceptance requires at least one independently reproduced real finding or chain
across the evaluation, together with the already-required improvement over the
native baseline. Retain honest negative results and failed investigations as
part of the evidence. Novelty and severity are assessed separately; a positive
result must still be evaluated against the engagement's original goal.

If fresh targets yield no supported positive result, preserve the autonomy and
negative-result evidence actually obtained and leave positive qualification open.
This criterion does not assume that every target contains a vulnerability.

Approval: "require at least one independently reproduced real finding or chain, plus improvement over the native agent" and "keep honest negative results too."

### Q23 — Allow exploration without complete intermediate capture

An authorized native capability may support exploration even when the harness
cannot fully capture its intermediate work, provided scope enforcement and
cleanup remain reliable. Treat those observations as leads. Before accepting
a claim, require inspectable evidence of the decisive effect, control, and
independent reproduction. A model's account of success is not a substitute.

Add deeper runtime integration when a demonstrated gap requires it, rather than
requiring complete intermediate capture for every exploratory capability. If the
required evidence cannot be obtained, preserve the lead as unconfirmed. Uncertain
effects still follow Q18; this decision does not relax authority or cleanup.

Approval: "allow exploration if scope and cleanup stay enforced, but require inspectable evidence and independent reproduction before accepting claims."

### Q24 — Independently validate the measurement, not just its output

A reviewer may reuse the researcher's tools rather than write a separate
reproducer for every claim. It must independently verify the actual attacker
permissions, preconditions, observed effects, and causal controls. Repeating a
tool's success message does not establish that its measurement or interpretation
is correct. Build another probe when the existing instrument cannot establish
the relevant facts. Agent-built instruments enable research; their own pass/fail
outputs do not determine whether a claim is accepted.

Approval: "allow reuse, but the reviewer must independently verify permissions, effects and controls, not just success messages" and "build another probe when needed."

### Q25 — A portable engagement contract with runtime-specific capabilities

Standardize the shared engagement contract: goals, scope, tasks, ownership,
evidence, operator directions, and recovery state. Preserve useful native
runtime-specific features within that contract rather than requiring identical
tools and behavior across runtimes. The lead selects suitable workers; accepted
claims meet the same evidence standard regardless of runtime.

Keep research state usable outside a particular runtime's conversation history.
Portability does not imply identical capabilities or seamless session transfer;
unavailable capabilities must remain explicit when work moves between runtimes.

Approval: "standardize the engagement contract but preserve useful runtime-specific features" and "keep research state portable."

### Q26 — Require strategy review when evidence challenges progress

The harness may require fresh strategy review during an active investigation
when the record shows repeated uninformative work or unresolved contradictions.
The lead creates the reviewer, preserving Q14's ownership rule. The reviewer
identifies a concrete overlooked condition, alternative explanation, or
experiment that can distinguish competing explanations. The lead must act on
the review or record an evidence-backed rebuttal.

Review extends beyond final claims and proposed closure without adding a
permanent second supervisor. Message counts, token usage, and elapsed time alone
do not establish stagnation. Concrete triggers still need validation on real
runs. Lead replacement for failure to address review follows Q27.

Approval: "require fresh strategy review when evidence shows stalled work or contradictions" and "the lead should act or give an evidence-backed rebuttal."

### Q27 — Replace a lead that repeatedly ignores review

The harness may autonomously replace a lead that repeatedly ignores required
review without an evidence-backed reason, after a clear opportunity to respond.
Use the review evidence to justify the handoff. Difficulty, absent findings,
and reasonable disagreement do not establish this failure.

Preserve the goal, scope, specialist work, evidence, unresolved questions and
effects, and remaining resources. Transfer control with only one active lead;
the old lead loses authority before its replacement takes control. This is a
recovery exception to Q14's lead-only agent creation rule, not a permanent
second supervisor. Replacement criteria still need validation on real runs.

Approval: "allow autonomous replacement when the lead repeatedly ignores review without an evidence-backed reason" and "preserve the work and one active lead."

### Q28 — Equal comparison limits and separate actual usage

Use the same generous total resource limits for the initial harness-versus-native
comparison. Count all agent work across setup, the lead, specialists, in-run
reviewers, and recovery. Each side chooses how to allocate its allowance and may
finish without spending it all. Report actual usage separately alongside verified
outcomes and human assistance; equal limits do not imply equal consumption or
demonstrate efficiency.

This is a condition for the initial comparison, not a reversal of Q6's decision
to defer product budget optimization. Larger capability runs may supply separate
evidence. Keep post-run independent assessment distinct from work done during
the investigation, following Q11.

Approval: "use the same generous limits for the initial comparison, count all agent work and report actual usage separately."

### Q29 — Share reusable research instructions with the baseline

Give the native agent the same reusable research instructions as the harness
team. The intended comparison must establish value from the added harness
beyond those instructions. Preserve Q21's normal native capabilities and Q28's
equal generous limits and separate actual-usage accounting. The baseline does
not install the OSLit candidate's coordination and recovery mechanisms.

Approval: "give the native agent the same reusable research instructions too"
and "we need to prove the harness adds value beyond that."

### Q30 — Scored search within a task; minimal native-tool integration

Allow scored candidate search as an agent-selected technique within a research
task. The overall investigation remains driven by questions, evidence and lead
judgment. A local evaluator's output informs an experiment; it cannot confirm a
security claim, close the broader investigation or change its acceptance standard.
No universal security score, global leaderboard or dedicated optimizer is required.

Reuse native tools for research, communication, worker control and discovery.
Keep extra interaction with the engagement controller minimal. The plan sketches
`status`, `claim` and typed `submit` commands through the existing shell; their
names and encoding are engineering choices, not new required tool definitions.
The controller must enforce actor identity, assignment, role, authority and resource
limits. Native reuse is conditional on those properties being enforceable; prompt
instructions or hidden menu entries do not establish a boundary.

The operator also accepted the accompanying coordination refinements: deliver
relevant changes with durable recovery; preserve competing explanations; share
versioned instruments and their operating conditions; separate messages from
accepted facts; coordinate writes to shared targets; and verify actual native role
boundaries. These refine Q13–Q18 and Q23–Q25 rather than replacing their decisions.

Approval, 14 November: "Agree, allow scored search as a technique within a task."
Also: "reuse native tools wherever possible, but make sure to enforce them" and
"keep the extra interface minimal. No code yet."

**Reasoning and evidence.** The discussion started from
[Scaling Adaptive Prompt Injection Attacks with Agent Swarms, v1](https://arxiv.org/pdf/2611.11861v1).
Its optimizer receives a scorer and shares candidate results. The main experiment
uses synthetic scenarios and evaluates a single defender turn. It does not isolate
whiteboards, leaderboards or team size in ablations; the reported relationship
between stronger models and leaderboard use is observational (§§3–5). This makes
sharing worth considering, without establishing that a particular tool or swarm
configuration improves long-horizon security research.

We compared three choices: copy the optimizer's tool set, rely entirely on native
messages/files, or reuse native capabilities with one small controller interface.
The third fits the agreed contract. General research lacks one reliable ranking
for unlike questions; negative and uncertain results can still change the useful
next experiment. Native messages/files already handle much of the interaction,
but do not by themselves supply atomic task claims, protected evidence publication
or enforceable role identity. Full-board rereads also become costly over days.

The resulting plan makes shared knowledge discoverable without forcing agreement,
keeps numerical search local, and adds enforcement only where existing mechanisms
fall short. Exact native identity/revocation behavior still needs engineering
verification. Research benefit remains unproven until the operator-owned test;
this paper and this decision are not qualification evidence.

Revisit the transport if real usage exposes unreliable calls, recovery or actor
attribution; a native host tool can then expose the same controller operations.
A dedicated optimizer needs a demonstrated recurring task and comparative evidence
of useful results beyond the native technique, with its costs and failures retained.

## 14 November clarification — runtimes, duration and architecture guidance

After reading the complete plan, the operator said, "Agree with the whole plan
except for that it seems," specifically challenged the OpenCode integration
requirement and a 24-hour ceiling, and endorsed section 6's environment direction.
This is agreement on the overall direction with corrections, not a claim that its
proposed mechanisms are implemented or verified.

- **Runtimes:** Codex and OMP (oh-my-pi) are the intended harness integrations.
  OpenCode may supply model access; that is separate from adopting its runtime.
  The earlier first-adapter proposal followed existing code and is superseded.
- **Duration:** multi-day research is required. The agent may work while allowed
  and budgeted; a fixed 24-hour engagement ceiling is not a requirement. The
  revised plan uses optional operator deadlines and renewable worker leases to
  express this without resetting allowance or weakening revocation.
- **Layering:** explain what the native harnesses already supply and what OSLit
  needs to add. The plan now separates model/provider access, native execution
  and engagement-wide coordination/evidence/recovery.
- **Documentation:** expand section 7 with an example and create architecture
  guidance capturing current vision and questions for material founder decisions.
  See [architecture instructions](../decisions/AGENTS.md).

Source: the same `technical oslit` chat, user message on 14 November 2026.
This clarification updates Q6/Q25's planning interpretation without rewriting
their original answers or adding an invented interview question.

## Remaining engineering work

The [complete engineering plan](oslit-engineering-plan-2026-11-14.md), drafted
14 November against current source, now proposes the implementation of all 30
decisions. The operator endorsed its direction with the corrections above. Exact
interfaces, execution policy migration and failure scenarios still need engineering
verification; they are not implemented capabilities.

The tool/coordination discussion raised Q30, now settled. No further founder
choice was identified for this documentation revision. Runtime feasibility and
wire-format details remain engineering work, not unanswered product questions.
If a new material choice emerges, continue from Q31 without reopening settled
requirements. The remaining work belongs in the reviewable plan:

1. **Runtime integration:** propose supported runtime/model configurations,
   preserve useful native capabilities, and define portable engagement state.
2. **Research environment:** map agent-owned setup and execution across source,
   binaries, running applications, and authorized remote laboratories. Identify
   existing code to retain, simplify, replace, or delete.
3. **Autonomy and recovery:** specify durable task ownership and shared state,
   review triggers, lead replacement, uncertain-effect handling, and cleanup.
   Show the exact policy changes needed to reconcile initial authorization with
   existing mid-run approval gates; this planning record does not change them.
4. **Usable delivery:** specify installation, engagement input, operation,
   recovery, evidence export, aggregate usage records, and engineering checks.
   Prepare the handoff for the operator-provided fresh-target test without
   assigning that test or the comparison to the assistant.

The plan maps these requirements to retained capabilities, changes or deletions,
engineering verification and the operator-owned acceptance handoff. The operator
has now agreed to the direction with the recorded corrections and subsequently
assigned its implementation. Engineering verification follows the plan; research
target runs require their own signed authority.
External disclosure, publication, deployment, and any change to a signed engagement's
authority boundary remain separate actions.
