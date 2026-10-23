# Product and engineering direction

Maintained synthesis, 23 October 2026. Read this before changing the harness's product
scope, research workflow, runtime architecture, or engineering plan. Accepted
[decision records](../decisions/README.md) retain their authority. The
[discussion record](../research/research-direction-discussion-2026-10.md) attributes
later operator choices and separates them from proposals. The
[implementation status](native-research-status.md) owns the dated capability and
qualification picture. A direction, implementation, and successful run are distinct facts.

## Product and north stars

The harness is a domain-neutral security research system: capable researchers use
source, tools, experiments, and runtime feedback inside an explicit authority and
evidence boundary. LLM application security is one domain. A native session means a
coding agent with a usable environment, rather than a prompt alone.

The product should make deep research possible with less operator steering. Useful
results include independently supported effects, corrected explanations, faithful
partial results, and bounded negative conclusions. Discovery stays open and creative;
confirmation and reporting stay tied to evidence. These are the distinct biases in
[Decision 0005](../decisions/0005-reasoning-directed-evidence-constrained-research.md).

The north stars are:

1. **Ownership.** The researcher selects and revises useful questions from evidence.
   Progress should require fewer human hints, repairs, and repeated requests to look
   deeper. Record those interventions when assessing autonomy.
2. **Depth.** Pursue the material explanation and its consequences. Preserve a
   supported base effect while larger claims remain unresolved. Depth is understanding
   and faithful proof, not a required number of stages or findings.
3. **Continuity.** Carry useful experiments, failed hypotheses, conditions, and
   unresolved effects across interruptions and context changes. Longer elapsed time
   or more invocations alone establishes no research benefit.
4. **Credibility.** Establish claims through relevant observations, controls, clean
   replay, and fresh challenge. A confident narrative, matching report text, or
   agreement between models cannot supply missing execution evidence.
5. **Portability and simplicity.** Keep methodology independent of a particular
   model, provider, agent runtime, or first test domain. Add a mechanism when an
   observed gap earns its complexity; prefer a smaller existing path when it suffices.

The ultimate autonomy aspiration in
[Decision 0012](../decisions/0012-full-autonomy-north-star.md) remains recorded
direction. Its possible future gate changes are not current permission. Current
scope, consequential review, escalation, and external-action requirements still apply.

## Choices that guide engineering

| Choice | Consequence for a change |
| --- | --- |
| Native research is the chosen direction for new local source work. | Develop one coherent native workflow. Keep the source default, live qualification, and scoped adoption separate; see the [cutover contract](../agents/native-cutover-contract.md). |
| Model and provider independence is a product requirement. | Treat OpenCode as the current integration and qualification vehicle. Describe actual supported tuples precisely; generic source-runtime support does not prove generic agent/provider support. |
| The researcher chooses the investigation. | Tools, cards, graphs, and prior results inform choices. Stages describe evidence maturity; they do not impose a fixed order or mandatory roster. |
| Ordinary working files carry native continuity. | Save scripts, results, interpretation, and unfinished work once and link them. Native history can help; it does not replace material state or independent evidence. |
| Independent challenge covers consequential acceptance and strong-lead dismissal. | Bind review to the checked claim and evidence. A fresh context must inspect a material link; a model name, signature, or accepted file alone cannot prove that happened. |
| Evidence properties survive process simplification. | Preserve authority, effect provenance, resource limits, uncertain-effect recovery, cleanup, and historical integrity while retiring unnecessary ceremony. |
| Time and cost support research quality. | Avoid cheap-first product goals or repeated budget prompts inside an existing allowance. Honor configured outer limits, account for research and review, and preserve useful unfinished work when a limit ends the run. |
| Existing engagements retain their supported route. | Use the explicit [legacy procedure](../agents/legacy-local-research.md) for queue/record work. Preserve its callers and immutable history; native notes do not become canonical legacy findings. |

The October operator choice to implement candidate default routing preceded the
final E2E. It did not establish qualification or supply the still-separate
[adoption decision](https://github.com/matheusht/redteam-harness/issues/165).
An incumbent comparison is optional diagnostic evidence for that decision. A claim
that a new mechanism is better still needs a suitable comparison; absence of one
proves neither superiority nor inferiority.

## Three different kinds of improvement

| Concern | What must change | Evidence needed |
| --- | --- | --- |
| Continuation and recovery | Work resumes with the correct material state, authority, remaining allowance, and unresolved effects. | Actual interruption/recovery evidence. Repeated dispatch proves only that dispatch continued. |
| Adaptation within a run | Observations change the explanation or next useful test when warranted. | Adaptive test selection needs a prediction, observation, and executed discriminating follow-up. A causal-revision claim additionally needs a changed explanation supported by that follow-up. A changed condition or successful retry alone does not prove causal revision. |
| Harness improvement across runs | A methodology, tool, model, or implementation change improves results. | Protected evaluation, a justified baseline, full costs, retained negative results, and independent validation. This remains separate from ordinary research. |

The October discussion's use of “hill climbing” primarily concerned adaptation
within an investigation. It did not approve self-editing evaluators, training,
automatic methodology promotion, or a new harness-optimization service.
[Decision 0004](../decisions/0004-epistemic-autonomy-complexity-budget.md) continues to
govern evaluator integrity and the separate autonomous-learning metric.

## How agents should change this system

1. **Locate the decision.** Read the applicable accepted decision, current source,
   and revision-bound evidence. Finish with an explicit distinction between what
   is chosen, implemented, checked locally, and qualified for actual use.
2. **Trace the affected path.** Account for callers, instructions, configuration,
   fixtures, evidence consumers, and retained legacy readers. Identify data or
   authority the change could lose or expose before editing.
3. **Question the mechanism.** Name the concrete capability or invariant needed.
   Compare deletion, an existing native feature, and the smallest serious
   alternative. Record why any new dependency or durable abstraction is necessary.
4. **Define failure before implementation.** State the relevant failures and the
   observable acceptance check. Follow the repository's failure-first and E2E
   rules; produce commands, inputs, environment requirements, expected results,
   observed evidence, and cleanup for completed workflow checks.
5. **Integrate and verify the final revision.** Exercise the affected public
   workflow and inspect its artifacts. Distinguish local structure, synthetic
   execution, actual native/provider behavior, target effects, hosted CI, and
   production evidence. An unavailable prerequisite yields an unavailable result.
6. **Reconcile the claim.** Review the final artifact against the original request
   and later corrections. Update the owning documentation and links, preserve
   historical receipts, and state remaining gaps. A source merge, ticket closure,
   or passing narrow check does not establish the full outcome.

Graphs, specialized workers, retrieval, a separate task chooser, and memory
services remain serious options. Each needs a named observed gap, an appropriate
baseline, a falsifier, total cost, and a removal criterion. First test whether the
same useful tools work in the native session. Published success stories justify
investigation; they do not isolate which component caused success. The retained
[research lessons](../research/research-direction-discussion-2026-10.md#research-lessons-and-limits)
record both useful ideas and the evidence limits.

## What an ending can establish

Claim state, search state, and bounded coverage remain separate. A refuted path
settles its tested conditions. A blocked environment supplies no security verdict.
An unfinished strong lead stays visible. A supported primitive does not establish
an unsupported larger claim, and it does not require abandoning that larger question.

“Exhaust all surfaces” expresses a depth aspiration. On an open-world target,
report the surfaces and conditions actually examined, decisive controls, access
limits, and remaining uncertainty. A time allowance is a ceiling. Neither a long
run nor a no-finding ending proves absence of vulnerabilities.

Use independent supported results and their conditions to assess research quality.
Record assistance, invalid claims, missed known paths, useful partials, elapsed
time, human effort, and costs separately. The accepted
`autonomous_gap_closure_count` measures autonomous harness learning; it is not a
synonym for target findings, continuity, or external acceptance.

## Open and deferred work

The [current status page](native-research-status.md) records source and evidence
limits. Multi-day reliability, outcome-sensitive adaptation, whole-run monetary
accounting, broader runtime/provider support, and comparative research benefit
remain questions to prove. No permanent swarm, scheduler service, graph database,
memory service, automatic external filing, or universal-coverage guarantee follows
from the discussion. The 23 October documentation request defers the experiment
follow-up; it does not qualify the candidate or change target-local authority.
