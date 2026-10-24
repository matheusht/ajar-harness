# Source-only long-running engagement goal template

This is the legacy queue/record route for supported existing engagements and
tasks explicitly assigned to that runtime. New local source research is
prepared through the [native entry procedure](../../../docs/agents/native-local-research.md);
the candidate source default is implemented, while #165 qualification/adoption
remains open. Actual native execution still needs the signed scope, plan-bound
approval, supported route and independent evidence.

Replace every bracketed field with verified engagement facts. Delete inapplicable sections; never fill unknowns by guessing.

> **Standard goal-prompt templates (the scaffold's defaults — use these first, this file is the
> long-form fallback).** The canonical formats live in the scaffold at
> `engagements/_TEMPLATE/goal-prompts/`:
> - `goal-prompt-START.md` — **standard format for STARTING an explicitly legacy engagement** (densely structured
>   GOAL / IN / OUT / BUILD-A-CARD / PIPELINE / CASCADING / OPERATING-MODEL / KEY-ROUTING /
>   AUTHORIZATION / FIRST-MOVE blocks; adapted per engagement by the LLM). Modeled on the Tron
>   engagement's goal prompt.
> - `goal-prompt-REVISIT-ESCALATION.md` — **standard format for REVISITING / REDOING / RE-RUNNING an
>   already-closed engagement** when the operator wants escalation vectors, an exhaustion check, or a
>   fresh pass ("was it exhausted?", "find the critical escalation, no reward-hacking"). Adds the
>   orchestrator-participation / second-reviewer-synchronisation rule, re-attack-the-prior-kill-
>   conditions framing, and the never-audited-surface-first routing. Modeled on the Crown engagement's
>   revisit prompt.
> - `goal-prompt-LONG-RUN.md` — **standard format for a LONG-RUN (budget-bounded, multi-round) deep hunt on
>   ONE asset**, when the operator will not be available to steer. Twelve parts + the anti-bias
>   construction in Part 0: a **symmetric exit obligation** replaces the source method's asserted
>   vulnerability, the optimistic prior is confined to the hunter lane and barred from the adjudicating
>   lane, and the stubbornness framing is scoped to effort and kept out of the verdict. Governs the round
>   loop through `engine/multi-round-orchestration.md`. Modeled on the Sol-Ultra prompts in
>   `docs/research/` (gvisor, protobuf, gemini-cli), de-biased per that engine doc §5.
>
> All three are referenced by `/goal` via `engagements/<id>/goal-prompts/<id>-goal-prompt[-<round>].md`.
> The LLM adapts structure and detail to the engagement's domain; the section skeleton is the constant.
> This file below remains the long-form structured fallback for cases neither template fits (very large
> multi-surface engagements wanting a fuller section layout).

## Entry and resume procedure

Use this procedure from the harness checkout before new work or resume. It is setup and reconstruction,
not permission to execute a target or to bypass a pending queue item.

1. Reuse the named local source and verify its exact commit/artifact identity and dirty state. Acquire
   source only when missing and explicitly authorized; changing the pin is a scope decision. Keep
   original source identity evidence, unique narrative and human cleanup context.
2. Before asking for signature, prepare the complete scope and goal draft with verified runtime/provider availability, finite budgets and pending launch requirements. For a new engagement, prepare the exact corpus manifest/enumeration and put its digest in the
   initial scope **before signing** if budget-bounded completion may be used. The genesis pin cannot
   be added by a later re-attestation. Obtain the real operator's exact scope signature; then use
   `tools/run-engagement.py init` with its required operator-console SSH authority for that scope and
   operation. An inline scope signature does not replace init's SSH check. Initialization and admitted
   state must precede recon. After authorized initialization, run the root-required mechanical proof from the harness checkout: `./.venv/bin/python tools/finding_lifecycle.py preflight --engagement <absolute-engagement>`. It must pass before any recon or attempt. Existing engagements run this same preflight without reinitialization. This is an agent-run check, not another human approval; refusal blocks recon/attempt execution while diagnostic read-only inspection remains available under its existing admission rules. Existing engagements use admission, not reinitialization or manual ledgers.
3. Run `tools/inspect-dossier.py --source <absolute-engagement>` for current revisions, typed reviews,
   outstanding obligations, stale projections and attributed optional context. Run
   `tools/run-engagement.py list|next|gate --engagement <absolute-engagement>` separately for the
   computed queue (invoke one subcommand at a time). These reads create no coordination state; invalid
   base or missing lock is unavailable. Inspector output explains evidence; it grants no authority and
   cannot run work. Generated progress/views are derived: record facts through canonical commands and
   use the governed render path only when needed, rather than transcribing another current-state view.
4. Before execution, verify signed environment scope, real runtime/provider availability and finite
   session/wall/cost/resource budgets. If declaring `budget_bounded` coverage, register the exact precommitted corpus artifacts for the driver's `--corpus-enumeration-ref`. Corpus omission does not prohibit a bounded session or inspection; retain the existing `operator_required`/noncompletion boundary. Read [the existing runner contract](../../../docs/agents/docker-work-queue.md)
   and `tools/run-work-queue.py run --help`: its public backend is Docker with a locally available
   immutable image containing Claude and Python, on the documented supported host. It has no implicit
   host fallback and does not implement an Astra/Codex backend. Record unavailable requirements as
   blockers; retain independent reviewer requirements and use only explicitly authorized concurrency.
5. Continue the next admitted queue action through the existing governed driver when ready. A gate
   release is a queue/session decision, not automatic approval of findings or global completion.
   Retain independent verification and named human gates. For handoff, link immutable evidence and
   the inspector/queue results; add only unique intent, unavailable observations or decisions.

For fallback generation, copy only the fenced goal body below and substitute the verified absolute
`[HARNESS_CHECKOUT]`. Keep this shared procedure in the harness; do not copy or rewrite it into the
target goal. Its local runner-document link resolves here.

```markdown
# Goal — [ENGAGEMENT_ID]

## Authority and starting state

Follow [the entry/resume procedure]([HARNESS_CHECKOUT]/skills/source-engagement-bootstrap/references/goal-template.md#entry-and-resume-procedure) before execution; use its inspector and list/next/gate handoff instead of manual generated-state transcription.

Execute an authorized, source-only white-box assessment of `[REPOSITORY]` at exact identity `[COMMIT/TAG]`, limited to the signed `engagements/[ENGAGEMENT_ID]/scope.md`. Read `CLAUDE.md`, the signed scope, `asset-prioritization.md`, `engine/whitebox-analysis.md`, `engine/loop.md`, `engine/persistence.md`, `engine/regrade.md`, `engine/pocinator.md`, `engine/chainability.md`, `engine/escalation.md`, and applicable oracle/card files before acting. Root policy and the signed scope override this goal.

Do not contact production or any live application. Work only in the authorized source tree and signed, disposable local environment. Do not access secrets, other users, real funds/data, or excluded components. Do not file, disclose, deploy, push, or promote memory autonomously.

## Outcome

Produce a rigorously adjudicated disposition for every material candidate in the bounded critical-asset corpus: `confirmed/chained`, `refuted`, `real-but-capped`, `deferred/blocked`, or `covered-dry`. A finding exists only after the oracle and evidence contracts pass. Finding volume is not success; evidence-constrained resolution is.

## Critical assets and bounded corpus

[INSERT RANKED ASSETS, SOURCE PATHS/SYMBOLS, TRUST BOUNDARIES, RELEASE ELIGIBILITY, AND COVERAGE DENOMINATOR]

If declaring `budget_bounded` coverage, before initial scope signing freeze the denominator as specified in the entry/resume procedure; record newly discovered assets without rewriting the genesis pin. "Dry" is unavailable while material assets/candidates lack a disposition.

## Progression map — backtrack freely

Stage 0 candidate sink/function narrowing → Stage 1 primitive vocabulary and cheap classifier → Stage 2 source/sink/path triples → Stage 3 cross-function reachability → Stage 3.5 chain construction → Stage 4 finding confirmation → Stage 4.25 post-confirmation verification and classification → Stage 5 chainability → Stage 5.25 novelty and paper-review → Stage 5.5 reachability dossier → advisory draft → Post: triage, regrade, pocinator, escalation, operator review/filing.

This is a map of rigor gates, not a one-pass waterfall. A failure at 4/4.25 returns to 2/3. A chainability failure returns to 3.5. New source evidence can reopen earlier narrowing. Preserve every transition and rationale.

## Search and grading policy

- Rules, regexes, SAST, sink lists, and cheap classifiers are Stage-1 prioritizers only. They cannot kill or confirm candidates.
- Over-generation is cheaper than a false negative. Keep uncertain candidates alive, but do not confuse persistence with infinite repetition.
- No single model pass may kill or bless a candidate. Use genuinely independent runs/sessions with distinct evidence access where available; do not simulate multiple experts in one response. If independence is unavailable, route to human review or retain `needs_review`/`blocked`.
- Separate finder, keep/kill review, adjudication, regrade, and pocinator proof review. Preserve cold-review requirements and contamination status.
- Operator priors influence effort only. They never increase confidence or substitute for source/runtime evidence.

## Verification-of-the-verification

Mechanical signals—breakpoint hit, corrupted state, file written, assertion passed—are necessary but not sufficient. Before confirmation, independently verify that the harness/PoC:

1. exercises the real in-scope source and eligible build;
2. follows reachable production-equivalent control flow and preconditions;
3. does not replace decisive logic with a favorable emulator or mock;
4. has matched negative and applicable positive controls;
5. demonstrates the exact claimed mechanism, reachability, and bounded impact;
6. cannot pass because of fixture setup, monkeypatching, stale state, or reward-hacked assertions.

Large PoCs may require long, decomposed implementation. Persist through debugging while evidence supports the lead, but never make the PoC prove a stronger claim than the target actually supports.

## Model-role preference

Use `[PLANNING_MODEL]` for planning, corpus triage, candidate prioritization, pipeline/debug strategy, and high-context re-evaluation. Use `[EXECUTION_MODEL]` for bounded long-horizon source tracing, harness construction, test iteration, and repetitive implementation work. Helpers may perform offline mechanical extraction/diffing only. Models remain non-oracular; availability must be verified, not assumed.

## Persistence and stopping

Activate persistence only for a confirmed primitive, strong activation signal, or explicit recorded operator prior. Bound each lead before grinding. Alternate zoom-in and zoom-out; a held vector is a wrong turn, while repeated variants of the same disproven path are tunnel vision.

Do not stop merely because construction is difficult or lengthy. Do stop a sub-thread when its bounded variants and decisive falsifiers are exhausted, then move elsewhere. Represent [TARGET-SPECIFIC BOUNDED-COVERAGE EVIDENCE] in the computed work queue. The independent cold review is its final blocking item; coverage completes only when that review closes and the reduced queue is empty. A non-empty operator-only queue pauses, and a pass that adds no material candidate is only evidence for review—not a counter or completion rule.

## Escalation of confirmed findings

For every confirmed finding, run an escalation/chainability pass (`engine/escalation.md`) before treating it as advisory-ready: drive it to its maximum *honest* impact and apply the marginal-contribution critique (severity = the delta the bug adds vs the world without it, never the total bad outcome nearby). Terminal state per finding: `escalated-confirmed` / `real-but-capped` (cap proven) / `bounded` / `new_finding_spun_off` / `no-escalation-and-sure` (with the exhaustion trail). Never under-demonstrate a real bug; never over-sell one.

## Human gates and Zone-2

The signed scope names exact categories: [EXACT CATEGORY LIST OR NONE]. Before creating any Zone-2 PoC artifact, obtain the explicit per-artifact human confirmation required by root policy, naming:

- candidate/finding and exact artifact;
- bounded action and capability;
- disposable owned environment and identity;
- expected impact and non-user-impact controls;
- expiry and cleanup obligation.

Proceed only after that confirmation is recorded. Never autonomously cross users/accounts you do not own, touch production, use real credentials/funds/data, create destructive or persistent capability, publish a package/image, or file a report. Log every artifact and cleanup status.

## Records and anti-fabrication

Use the mandatory canonical engagement record commands after admitted initialization. Attempts/artifacts are immutable; findings are revisioned; views are derived. Record failed attempts, controls, held/refuted candidates, reopenings, cost, and missing evidence. Never invent attempts, source identity, test output, independent review, environment fidelity, or impact. Missing environment produces `blocked`, not synthetic pass/fail.

## Done criteria

Call `goal_complete` only after all are true:

- signed scope and exact source/environment identity remained valid;
- every ranked critical asset and material candidate has a traceable terminal disposition;
- every claimed finding survived independent adjudication, regrade, pocinator, escalation/chainability, controls, replay where applicable, and verification-of-the-verification;
- unsupported claims were corrected or withdrawn;
- reports remain internal and revision-bound; no autonomous filing occurred;
- cleanup is terminal or explicitly blocked and operator-visible;
- memory has an operator-reviewed terminal disposition without automatic Plane-1 promotion;
- final summary separates demonstrated findings, supported negatives, unresolved blockers, coverage limitations, cost, and what was not demonstrated.

If a human gate blocks progress, pause with the exact requested decision. Do not redefine the goal smaller, bypass the gate, fabricate completion, or call `goal_complete` early.
```
