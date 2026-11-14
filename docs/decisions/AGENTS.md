# OSLit architecture work

Read this when changing research behavior, runtime integration, coordination,
state/evidence ownership, environment access, stopping rules or acceptance criteria,
including changes outside this directory. Root instructions still apply.

## Read the right source

- **Founder intent:** [November decisions](../research/oslit-harness-grilling-2026-11-13.md),
  including the 14 November correction. The founder endorsed the plan's direction,
  selected Codex/OMP and rejected a fixed 24-hour research ceiling. Q30 records
  task-local scored search and minimal, enforced native-tool integration.
- **Proposed implementation:** [engineering plan](../research/oslit-engineering-plan-2026-11-14.md).
  Read the affected section and its failure scenarios. Endorsement is not proof
  of implementation, qualification or a signed engagement.
- **Current rules:** [decision index](README.md), the applicable accepted decision,
  root instructions and actual source. Existing contracts retain their meaning
  until a versioned replacement is implemented and adopted.
- **Current evidence:** [native status](../wiki/native-research-status.md) and the
  dated source/result it cites. Recheck the affected code; a status page is a snapshot.
- **Broader rationale:** [product direction](../wiki/product-and-engineering-direction.md).
  [The old architecture summary](../architecture.md) is historical.

## The product we are trying to build

From an authorized target, goal, access and resources, the system should own a
serious investigation: prepare its environment, form and revise hypotheses,
build instruments, connect effects, challenge claims, preserve useful work and
deliver an honest internal result. The operator should not have to repeatedly
say “look deeper,” choose every experiment or repair ordinary setup failures.

Keep these properties when changing the design:

- **Model-directed research.** The lead selects questions and priorities from
  evidence; specialists choose experiments. Tasks organize ownership and shared
  work. A fixed taxonomy, roster or sequence cannot become the research strategy.
- **Depth with honest endings.** A small supported effect can lead to a larger
  chain. Initial suspicions remain hypotheses. A bounded goal may finish after
  independent confirmation; a broad investigation continues past its first finding.
  Report tested conditions, unresolved paths and access limits precisely.
- **Continuity for days.** Research duration follows valid authority, remaining
  resources and the goal. A deadline applies when the operator supplies one.
  Short renewable worker leases control failures; they do not set engagement age.
- **Agent-owned environments.** Use supplied source, binaries, running services
  or combined access. The agent obtains permitted tools, diagnoses setup and
  uses authorized local/remote infrastructure. A prepared build recipe is optional.
- **Useful teams.** One lead owns direction and team expansion. Retain useful
  specialists; share evidence; obtain fresh review when evidence or closure calls
  for it. Recovery can replace a nonresponsive lead while preserving valid work.
- **Native strengths.** Codex and OMP supply agent execution, tools, context,
  sessions and native workers. OSLit supplies missing engagement behavior across
  those lifetimes. Reuse requires verified actor/role/resource enforcement; a role
  prompt is insufficient. Provider credentials do not select an agent runtime.
- **Local optimization.** Agents may build evaluators for a task. Keep their scores,
  instrument versions and tested conditions distinct from claim acceptance and
  engagement priorities. Share relevant updates and reusable evidence without
  imposing one explanation or a global ranking on the team.
- **Credibility.** Confirmation requires an observed effect, relevant control and
  clean independent reproduction. Review checks measurement and permissions.
  Keep claim, search and cleanup states separate; preserve contrary evidence.
- **Measured added value.** Engineering checks establish mechanics. The operator
  owns the future fresh-target test and comparison with a capable native agent
  using the same reusable instructions and generous limits. Count all agent work
  and human interventions. Do not weaken the baseline to make OSLit look useful.

The current focus is one capable engagement. Cross-engagement learning, automatic
method promotion and commercial optimization remain separate work. No universal
absence-of-vulnerability claim or automatic external filing follows from this vision.

## Before choosing a mechanism

1. State the user-visible capability and a concrete failure it must prevent.
   Trace the real path and all affected callers, records and readers.
2. Try deletion, the existing native feature and the smallest adequate extension.
   Explain what remains missing and how enforcement works before proposing a new
   tool, controller, service or store. Fewer tool names alone do not prove simplicity.
3. Assign each fact one owner. Native sessions own conversation state; engagement
   records own assignments/authority/evidence meaning; executors own observations.
   Derived views must not become competing authorities.
4. Define the failure scenarios before code: ordinary success, interruption,
   uncertain effects, stale ownership, loss of authority and recovery as relevant.
   Exercise the public workflow and retain repeatable inputs/results.
5. Reconcile the implementation and documentation with the founder's decisions.
   Report chosen, implemented, locally checked, integrated and qualified separately.

## When to ask the founder

Read the recorded answer first. Ask only when a new choice materially changes
intent or an unresolved tradeoff cannot be settled from code/evidence. State the
specific fork, consequence, recommendation and smallest useful experiment. Follow
the invoked interview format; ask only decisions whose prerequisites are settled,
and continue independent work. These are
decision triggers, not an approval questionnaire for routine engineering.

| Proposed change | Question to resolve if not already answered |
| --- | --- |
| Narrow the supported access or environment | Which intended investigations would this exclude, and is that tradeoff intended? |
| Encode research steps or rank paths mechanically | Which repeated reasoning failure needs this rule, and should evidence/model judgment handle it instead? |
| Add coordination, memory or an abstraction | What cannot the native runtime already do, and what result would justify deleting this addition? |
| Replace the runtime or provider strategy | Are we changing model access or the agent's execution environment? What capability requires the change? |
| Change stopping, review or lead replacement | What observation justifies stopping/replacing rather than continuing, and how can the lead rebut a mistaken challenge? |
| Restrict long work or optimize cost | Is the proposed limit an operator constraint, a provider limit or an engineering convenience? Which capability is being traded away? |
| Change authority or who approves effects | Which exact effect becomes permitted, by whose grant, and what enforces that boundary? |
| Expand to cross-engagement learning or target-specific logic | Is this a new product goal, or can an engagement-local tool solve the present need? |
| Change acceptance or claim success | What evidence would distinguish real research improvement from more activity, stronger instructions or extra human help? |

Use abstract counterexamples before asking: would the design still work with no
source, an unexpected hypothesis, no finding, a three-day investigation, a lost
session, an unavailable provider or a stronger future model? A failing example
identifies a design gap; it does not automatically justify more machinery.

## Keep the direction usable

Record founder corrections with their date/source. Link durable choices through
the [decision index](README.md); update the plan and maintained product direction,
then append the wiki log. Preserve historical decisions and execution records.
For an important choice, retain the problem, serious alternatives, source evidence,
inferences, chosen tradeoff and the evidence that would justify revisiting it.
Record the useful rationale, not a transcript of every discussion or tool call.
Keep root `AGENTS.md` and `CLAUDE.md` byte-identical when changing their pointers.
Run structural conformance after entrypoint changes and check affected links.

A change is ready for review when its scope and owner are clear, applicable
decisions are traced, affected workflow checks have reviewable evidence, and
remaining limits are explicit. A documentation change needs link/consistency
checks; it does not need a provider run. Documenting broader authority never
activates it in an existing engagement.
