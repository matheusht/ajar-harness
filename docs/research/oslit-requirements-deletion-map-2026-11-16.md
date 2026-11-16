# Integration map for the selected requirement deletions

Companion to the [research autonomy plan](oslit-research-autonomy-plan-2026-11-16.md).

Source inspection on 16 November 2026 at commit 95e5e0f1 in /private/tmp/oslit-final-implementation-20261115. This is the preimplementation source map, not a test result. Q12–Q15 and Q18–Q20 were selected. The inspected baseline enforced the old rules; its line numbers and present-tense code descriptions below refer to that baseline.

## Local implementation update, 16 November 2026

The working tree now implements [research-autonomy-v1](../decisions/0016-research-autonomy.md)
through the existing controller/native boundaries, with separate frozen guidance
and unchanged historical-policy meaning. The [operator guide](../agents/engagement.md)
and [library guide](../agents/knowledge-library.md) describe that interface.
Focused local checks are distinct from the full E2E/provider/research workflows
listed below, which the operator deferred. This map remains the historical rationale
and caller checklist; it is not live qualification evidence.

## One policy revision, not a collection of switches

Current scope validation accepts only an absent authority policy or initial-scope-v1 (engagement_contract.py:473–488). Controller initialization freezes the signed scope and methodology/protocol bytes and records their hashes (engagement_controller.py:134–178). Replay validates frozen bytes but runs the current reducer; it does not restore a historical controller binary (245–277). Therefore changing only the source implementation can change how an old journal is interpreted even when no event file changes.

Use one explicit versioned behavior selection for newly initialized engagements, with a compatibility path for existing roots. The exact field/version name is an implementation choice. Do not add an independent toggle for every deleted rule, auto-upgrade a running engagement, rewrite old signatures or recompute historical findings under new criteria. Existing initialization, scope loading and route selection provide the seam; no new migration service is needed. Existing v1 routing stays explicit (native_engagement.py:754–773).

Before implementation, define a recovery comparison: open/export an old retained fixture and compare its recorded claim, obligation and stopping meaning before/after. Then perform its next ordinary operation, including a pending challenge/review or later-rung effect. Replay alone cannot establish preserved resumed behavior. Select policy from frozen initialization, with absent new selectors retaining historical behavior, across reduction, admission, validation and guidance selection. Start a new fixture and show the selected new behavior. The new default templates and documentation must select the new policy consistently. This is ordinary engineering verification, not another operator approval for each experiment.

## Q12: strategy discussion cannot deny resources or replace the lead

Reach controller._dispatch_resources (632–636), runner._resources (146–157), runner's completed-checkpoint/replacement paths (388–406,439–449), evidence strategy_challenge/review_response reduction (709–715), decision_checkpoint reduction (794–802), and controller.replace_lead (1639–1654). Status/export currently expose replacement_required; readers must not interpret an old field as a new automatic trigger. Also remove the strategy veto from current_closure (evidence.py:1140–1151): otherwise disputed advice can still block completion after dispatch is freed. Retain review of actual claim support and honest unfinished work.

Remove the resource exclusion and automatic two-opportunity consequence for new runs. Preserve actual process recovery, operator direction, current lead identity, resource ownership and unknown physical effects. A strategy critique can remain an ordinary publication/message. Do not keep mandatory review_response transitions solely to clear an obsolete semantic debt. Closure-review reduction (evidence.py:728–736) already reopens a rejected closure; remove the extra semantic obligation it manufactures solely to force that response.

Existing scenario homes: check_engagement_evidence_e2e.py, check_engagement_lifecycle_edges_e2e.py, check_engagement_runner_e2e.py, check_engagement_runner_recovery_e2e.py. Preserve old-policy fixture assertions; add the new public workflow before implementation: critique arrives, lead investigates on the same resource, disagreement remains visible, unknown-effect and revocation still stop the affected action. No new evaluator is needed to decide whether a turn was thoughtful enough.

## Q13: validate factual identity, review scientific adequacy

The comparable helper is shared by experiment_compare, related/control/replay, repetition challenges and patch_checks (engagement_evidence.py:323–345,513,524–539,594–598,1021–1035). Do not weaken it globally without inspecting its callers. Exact equality can still serve an explicitly identical-workload numeric comparison. It does not decide whether different-account controls or independently written probes test the same causal claim.

The new review path preserves exact instrument/probe/candidate bytes, declared conditions, source/environment identity, selected account bindings, executor-origin binding and independent actor/session facts. Conditions are worker-authored metadata bound to the run (native_boundary.py:863–866; evidence.py:459–461), not automatically measured truths. Likewise, the account resolver records which configured credential binding it selected (target_accounts.py:195–211); that alone does not prove the principal or privileges the target recognized. The reviewer checks actual preconditions and causal relations from the relevant observations. A declared reset description is distinct from an observed reset. Claims still need actual evidence; the change does not make a reviewer's narrative into a receipt. A fresh environment identifier alone never proves a clean relevant state, and a different valid reproducer need not share bytes. Independent reproduction need not be personally executed by the final reviewer if the reviewer can inspect an actual independently executed result.

Remove the universal CHECKS Boolean form at evidence.py:580–587 and the fixed four-purpose original/patched matrix at 1021–1035 where they encode scientific sufficiency. Preserve actual original/patched byte binding and evidence access. Derive facts the controller already owns, such as remaining task IDs, instead of requiring a copied exact list in closure requests (625–641).

Scenario homes: check_engagement_evidence_e2e.py, check_application_reset_e2e.py, check_engagement_export_references_e2e.py and patch scenarios found through patch_checks callers. New public cases: honest changed-account control; distinct valid reproducer; reviewer rejects a mismatched causal claim; fabricated or edited execution facts remain rejected; a relevant patch check need not manufacture an inapplicable variant row. Historical evidence remains unchanged.

## Q14: remove the universal escalation ladder

Reach RUNGS/scope ceiling validation in engagement_contract.py:35,473–488,603–621; escalation_material/current_escalation/admit_effect in engagement_evidence.py:348–424; protected environment and network observation callers at182,196,307; escalation review request/result and evidence invalidation; the protocol, contract examples and user entry. Also update native boundary startup effect selection (:262–267), preflight environment selection (:119–125), owned-lab effect/policy checks (engagement_lab_artifacts.py:32–74) and literal initial-scope-v1 checks in contract validation (:625/640/657). A new policy that passes only the top-level validator can otherwise fail before tools start.

The new policy checks each requested effect against its actual signed resources, accounts, destinations, limits and current ownership. A prior unrelated self/stored finding is not a prerequisite. Retain any sequence the operator explicitly selected and state transitions genuinely needed for this experiment. Existing signed scopes keep their original interpretation. Avoid replacing the old ladder with another universal taxonomy or implied stronger authority.

Scenario home: check_engagement_escalation_e2e.py plus network journal/admission scenarios. Define the new case first: a permitted two-account read executes without first writing persistent state, while an ungranted account/destination/effect remains refused. Confirm that a real multi-stage claim still presents the observations supporting its actual links; this is review of evidence, not compulsory test order.

## Q19: optional total research limits

For the new policy, remove the requirement to supply both total caps (`engagement_contract.py:512–518`). Preserve historical scopes. Check only present operator-selected caps in grant admission, reservation renewal and invocation admission (`engagement_controller.py:910–925,1132–1157`). Continue recording usage with its actual meaning; a counter need not be a stop condition. Keep machine capacity, operator stop and short renewable permissions for abandoned-worker recovery. Do not substitute a large hidden default for an omitted limit.

Trace indirect dependencies too. Proxy certificate lifetime currently reads the mandatory total worker-time cap (`engagement_native_boundary.py:376–377`); certificate renewal or controlled session recovery must follow valid authority without introducing a new engagement deadline. Native transport also raises at 4,096 session invocations or remembered tool calls (`native_runtime_transport.py:526–546`). Preserve bounded memory and exact-retry handling, but arrange continuation/recovery instead of treating these implementation limits as a finished investigation. Queue and concurrency pressure must have bounded handling, not unbounded storage or a disguised total research cap.

Define checks before implementation: a new run omits both total caps and starts; either selected cap still applies; session continuation preserves evidence and unfinished work; operator stop revokes parent and helpers; old scopes retain their limits. Reuse contract, runner/recovery and native-boundary scenarios. An accelerated boundary check is not proof of a multi-day run.

## Preserve continuation and recover useful context

Keep the existing repeated invocation loop (`engagement_runner.py:361–410`), active lease renewal (`370–377`) and reviewed closure (`434–437,469–476`). A normal model answer is not engagement completion. Removing strategy access holds and the fixed replacement counter does not remove these mechanisms.

Connect safely recoverable session exhaustion/interruption to reconstruction in the existing runner. Exceptions currently mark a generation failed (`411–423`); the scheduler excludes it and can return `worker_progress_unavailable` (`439–490`), leaving a later public resume to recover. Preserve actual failure reporting, spending, ownership and uncertain-effect handling. Do not endlessly repeat an unresolved failure or invent success when continuation is unavailable. No second planner or generic effort judge is needed.

`worker_resumed` creates a new session while preserving the delivery cursor (`engagement_controller.py:423–428`). `_prompt` then requests updates after that cursor (`engagement_runner.py:225–238`). Earlier evidence remains in the journal, but acknowledged delivery to a lost session is not understanding in its replacement. Supply useful current orientation through the existing board/status and source links without resetting delivery history or replaying every event into the prompt.

Define the joined failure checks first: a normal answer leads to further permitted work; a safe internal session limit reconstructs without operator steering; fresh context recovers an older acknowledged partial and uses it in a new test; rejected closure returns to investigation; operator stop and genuinely unresolved effects still stop affected work. Scripted continuation proves mechanics. A live model discovering the next test provides behavioral evidence, and an actual sustained run is a separate continuity check.

## Hide transport chores through existing owners

Controller.submit already locks, validates actors and deduplicates accepted request IDs durably (767–805). Native transport supplies session/invocation/call identity and an in-memory duplicate-result cache (native_runtime_transport.py:534–568). Reuse these together; the in-memory cache alone is not restart-safe idempotency. The model need not invent transport request IDs, retry unrelated revision collisions or implement byte decoding.

Use current-state projections and source links instead of requiring the agent to replay the entire event stream. Keep bounded responses, explicit incomplete results and durable delivery accounting underneath. Ordinary large-file reads/search should use the existing isolated native executor. The 4 MiB evidence-object limit is real; corpus/source files larger than that need a retained file path and bounded reading, not a hidden assumption that store_object accepts arbitrary documents.

Affected public paths include native boundary tool schemas and handlers, WorkerContext.submit, controller/board/status, Codex and OMP transport, native_engagement CLI help, examples and exports. Existing board/native-boundary/public-CLI/journal-recovery scenarios are the starting points. Test a repeated call across interrupted delivery and concurrent independent publications; preserve at-most-once accepted mutations and real stale-owner rejection. Do not add another controller or mandatory wrapper workflow.

## Remove the protocol-example reading obstruction once

The shared scanner rejects even a bare Authorization or Cookie header followed by a colon (engagement_contract.py:36–42,213–251). It runs in object storage, native host tool results (native_runtime_transport.py:89–94), OMP reads (native_runtime_omp.py:431–442), and environment output/artifact reads (research_environment.py:666,734). A storage-only exception cannot provide a usable library.

Distinguish harmless header syntax and unmistakably redacted/synthetic placeholders from actual credentials in this shared path. Preserve known-secret/reflection checks and actual credential exclusion; a public URL is no blanket exemption. Check retention, selected-source reading and delivery together. A completed read whose content is withheld is not an unknown physical execution. When only a redacted/extracted form can be retained, identify that form honestly rather than labelling it the original bytes. No per-source approval form or separate allowlist at each boundary is needed.

## Documentation and verification boundary

Update the new plan and accepted correction record, decision index, maintained direction, README, v2 guide, contract examples and method/protocol together. Root AGENTS/CLAUDE currently name `initial-scope-v1` and require the prior rung to succeed (:55–63); update their authority/review wording to distinguish the new policy from preserved older policies. Keep the two files identical and run structural conformance. Retain route pointers unless routing changes. The old plan and historical evidence remain dated records. A source change, local contained scenario, actual native runtime run and fresh-target research comparison prove different things. The operator retains the fresh-target test.

## Minimum knowledge delivery reach

Keep permission and evidence rules in shared OSLit code, with file/process/network limits in the test environment. Runtime adapters connect to those controls; they must not duplicate research policy. Current Codex restrictions (`native_runtime_codex.py:239–272`) and OMP startup restrictions (`native_runtime_omp.py:44–76`) disable useful native features. Audit each restriction against the action it prevents and reuse existing runtime/environment controls where sufficient. The new library does not require the agent to follow a skill or pass a reasoning check before reading it.

Q18 selects internal helpers under their parent's permissions and limits, with separate independent reviewers. Codex currently accepts calls only from the one bound thread and ignores other thread events, including usage (`native_runtime_codex.py:147–182`). OMP's tool process exposes six file/shell tools and no session-spawn interface (`native_runtime_omp_tools.mjs:24–29`). Add verified native child-to-parent mapping and shared usage/stop handling; do not add a controller task or independent-review identity for each helper. Preserve native feature use wherever existing controls suffice. Define the joined check before implementation: a helper performs permitted work, its use counts under the parent, and parent revocation stops descendants; a forged parent identity and self-review remain refused.

Keep counter meanings explicit. `max_workers` currently counts registered workers and pending/unknown dispatches; `invocations` counts controller dispatches and top-level turns; `worker_seconds` measures elapsed time per owned dispatch (`engagement_controller.py:360–367,429–448,668–669,910–925`; `engagement_runner.py:325–336`). None establishes total native helper use. Preserve old contracts and adapt the applicable accounting without quietly relabeling elapsed time as summed agent time. Q19 makes the total research caps optional for new scopes, as mapped above. It does not create a budget for each helper.

Both adapters expose isolated file tools, so selected Markdown and helper files can supply the first usable path. Native skill catalogs are optional integration work. Codex currently omits selected executor capability roots; OMP disables skills in its model process and runs file tools in a separate owner. A file staged for the tool environment is not automatically visible in the model owner's filesystem. Keep those owners explicit rather than copying host skills or enabling ambient discovery.

Startup support registration closes after preparation. The active read path therefore needs automatic retention and selected-file materialization through the existing bridge and owned working environment. Bounded `engagement_read` and artifact capture provide useful pieces; they do not already form a shared active library. Reuse their identities and native file operations without exposing byte decoding or a separate import transaction to the researcher.

Q20 selects continued reference delivery when durable retention fails. Attempt to save automatically; if otherwise permitted content is available, deliver it with a clear `not retained` status. Keep that state visible on recovery/export where records survive, and never claim exact recovery of unsaved bytes. Reuse existing delivery/error handling rather than adding an import approval or a research hold. Define the failure check first: successful fetch, failed save, useful continued research, honest export gap, and no retroactive claim that a later fetch is the original version. Required experiment evidence and exact-version technique evaluation keep their separate requirements.

Acquisition currently admits credential-free GET/HEAD requests at fixed origins and records transfer identity, not the response body. Retain the delivered body and its extraction separately. Q11's broader public-reference grant needs a new versioned capability. A search backend requiring POST or credentials needs a narrow adapter/configuration path; it does not justify unrestricted POST or another service. Exercise the chosen backend through each claimed runtime, including unavailable versus empty results.

The joined check is one running worker reading a newly available reference/helper, retaining its selected version across a later update and interruption, and exporting what it actually received. It includes a source above the evidence-object size limit. Source availability, successful delivery and useful application remain distinct results.

## Pinned source references

All line references above refer to the inspected commit, not to a later checkout.

- [engagement_controller.py](https://github.com/matheusht/redteam-harness/blob/95e5e0f1c01817c54cd4e137b990f9c663f1e960/tools/engagement_controller.py)
- [engagement_evidence.py](https://github.com/matheusht/redteam-harness/blob/95e5e0f1c01817c54cd4e137b990f9c663f1e960/tools/engagement_evidence.py)
- [engagement_contract.py](https://github.com/matheusht/redteam-harness/blob/95e5e0f1c01817c54cd4e137b990f9c663f1e960/tools/engagement_contract.py)
- [engagement_runner.py](https://github.com/matheusht/redteam-harness/blob/95e5e0f1c01817c54cd4e137b990f9c663f1e960/tools/engagement_runner.py)
- [engagement_native_boundary.py](https://github.com/matheusht/redteam-harness/blob/95e5e0f1c01817c54cd4e137b990f9c663f1e960/tools/engagement_native_boundary.py)
- [engagement_preflight.py](https://github.com/matheusht/redteam-harness/blob/95e5e0f1c01817c54cd4e137b990f9c663f1e960/tools/engagement_preflight.py)
- [engagement_lab_artifacts.py](https://github.com/matheusht/redteam-harness/blob/95e5e0f1c01817c54cd4e137b990f9c663f1e960/tools/engagement_lab_artifacts.py)
- [engagement_board.py](https://github.com/matheusht/redteam-harness/blob/95e5e0f1c01817c54cd4e137b990f9c663f1e960/tools/engagement_board.py)
- [native_runtime_transport.py](https://github.com/matheusht/redteam-harness/blob/95e5e0f1c01817c54cd4e137b990f9c663f1e960/tools/native_runtime_transport.py)
- [native_runtime_omp.py](https://github.com/matheusht/redteam-harness/blob/95e5e0f1c01817c54cd4e137b990f9c663f1e960/tools/native_runtime_omp.py)
- [research_environment.py](https://github.com/matheusht/redteam-harness/blob/95e5e0f1c01817c54cd4e137b990f9c663f1e960/tools/research_environment.py)
- [target_accounts.py](https://github.com/matheusht/redteam-harness/blob/95e5e0f1c01817c54cd4e137b990f9c663f1e960/tools/target_accounts.py)
- [native_runtime_codex.py](https://github.com/matheusht/redteam-harness/blob/95e5e0f1c01817c54cd4e137b990f9c663f1e960/tools/native_runtime_codex.py)
- [acquisition_network.py](https://github.com/matheusht/redteam-harness/blob/95e5e0f1c01817c54cd4e137b990f9c663f1e960/tools/acquisition_network.py)
- [AGENTS.md](https://github.com/matheusht/redteam-harness/blob/95e5e0f1c01817c54cd4e137b990f9c663f1e960/AGENTS.md)
- [CLAUDE.md](https://github.com/matheusht/redteam-harness/blob/95e5e0f1c01817c54cd4e137b990f9c663f1e960/CLAUDE.md)
- [README.md](https://github.com/matheusht/redteam-harness/blob/95e5e0f1c01817c54cd4e137b990f9c663f1e960/README.md)
