# Portable local research workflow

Use this with the task's visible brief and the operator's current run snapshot. The
brief defines the target, objective, permitted actors and effects; the operator
controls scope, shared allowance, stop, and cleanup. This workflow supplies a
research method, not new authority. Use `/workspace/RESEARCH.md` as an ordinary
working note when useful; keep scripts and permitted raw results under
`/workspace/project`.
The host evidence carries runtime and session identity; the notebook need not.
Save material research once in ordinary files or captured evidence and link to it.
The notebook preserves interpretation and continuity, not a duplicate of every
tool event. No attempt/event pairs, routing transitions, harmless-file registration
or signed internal report are required for this native workflow. Legacy scheduling
and closure rules do not apply when a reference links to their domain reasoning.
Resolve a missing permission boundary before a target action. These paths are
the current integration's layout; another runtime can use the same ordinary
files under its own workspace root and must supply its own enforced run limits.
When `/research/checked-setup/` is present, read `INITIAL_THREAT_MODEL.md`
and `SETUP_TRACE.json` before the first research action. They are frozen setup
inputs, not findings. Record any correction in `/workspace/RESEARCH.md` or a
new research artifact; do not overwrite the original threat model or treat the
setup build as evidence of a security effect.
For a signed full-engagement scope, carry the internal investigation through
the remaining allowance without requesting another human plan or approval.
The host derives phase authority from that initial scope, arranges fresh review,
and verifies owner stop. A limit or uncertain effect ends incomplete until
protected readback resolves it.

1. **Ground the case.** Check the target and source version, build and service
   state, available actors, permitted effects, and remaining allowance against
   the current operator snapshot. Learn the normal path and a relevant denial or
   other control before interpreting unusual behavior. Choose leads from the
   source and observations; the brief does not select a flaw or test sequence.

2. **State a testable explanation.** Before a material security test, state what
   you think happens, the conditions it needs, the result you predict, and a result
   that would count against it. Keep that explanation in the native research or
   an ordinary note/script; link existing evidence instead of transcribing it
   again. Pick a test that separates it from a serious alternative. Keep the
   earlier statement when the explanation changes so the change is traceable.
   For a correction to the initial threat model, name the old assumption, the
   protected observation's receipt ID and hash, the revised condition, a serious
   alternative, and the next test that separates them. The correction guides
   research; it does not change scope.

3. **Run and observe.** Use the permitted entry path and ordinary tools. Save
   the command or script, inputs, source/build conditions, response, and relevant
   target state, or reference their existing capture. Link the result to independent
   observer evidence when available;
   your own text or edited logs cannot establish an effect. A denial is evidence
   about that request; a setup failure or missing response is not a security
   result. If an effect may have occurred but its result is unknown, request
   host-controlled readback or an authorized reset before any retry.

4. **Revise the investigation.** Compare the result with the prediction. Keep
   supported conditions, narrow or refute contradicted ones, and choose and run
   the next discriminating test when authority and allowance remain. Preserve a
   distinct supported alternative and useful unfinished leads; one held path
   does not settle another. Recheck dependent impact claims when source, roles,
   resources, or target state change. Label operator-induced changes separately
   from agent-discovered effects. A correct first result needs no invented failure.
   Record the result in `/workspace/NEXT.json` as `supported`, `refuted`,
   `blocked`, or `inconclusive`; state what it rules out, the useful capabilities
   and coverage, and the next discriminating test or an explicit stop proposal.
   A refutation may close the lead; do not add a branch merely because a test
   failed. Keep coverage as a changing map with its limits, not proof of absence.
   The exact handoff shape is:

   ```json
   {
     "kind": "native-continuation-next-v1",
     "last_result": {
       "state": "supported",
       "rules_out": "what the result excludes",
       "unresolved": "what remains unknown"
     },
     "capabilities": [
       {"capability": "observed effect", "enables": "next reachable state",
        "interface": "optional concrete interface", "evidence": "optional evidence link"}
     ],
     "coverage": [
       {"surface": "named entry", "status": "tested",
        "limit": "optional limit"}
     ],
     "next": {
       "question": "the next question",
       "test": "the next discriminating test",
       "prediction": "what this test predicts",
       "disconfirming": "what result would count against it",
       "authority": "existing authority for the test",
       "expected_cost": "optional cost estimate"
     },
     "proposed_stop": false,
     "strong_lead": true
   }
   ```

   Set `next` to `null` only for a stop proposal or a typed host action.
   Coverage status is one of `tested`, `blocked`, `out_of_scope`, or
   `untested`. Changing a strong lead from `true` to `false` is an abandonment
   decision and needs fresh review.

   In an approved source-only run, a host check request is the other reason for
   `next: null`. Keep `proposed_stop: false` and add exactly one typed
   `host_action`, for example
   `{"kind":"native-source-execute-v1","command":["sh","check.sh"]}`.
   Put the chosen script in the source workspace first. The host checks the
   approved offline effect envelope and shared allowance, freezes the command
   and source, and runs one protected batch. The following native turn reads
   `/research/source-actions/<id>/RESULTS.json` and updates `NEXT.json` from the
   result. The projection exposes exit codes and hashes, while raw output stays
   host-protected. A matching replay output is only a reproducibility result;
   it cannot establish a security effect. See
   [native source research](../docs/agents/native-source-sdk.md#researcher-requested-source-check).


5. **Follow real connections.** When one step appears to enable another, record
   the actual output or state produced, the next step that consumed it, and the
   actors, permissions, source version, resources, and timing that made both
   steps compatible. Test the complete connection through the application.
   Separately successful parts or a narrated handoff support only partial work.
   Stop at the supported depth; extra steps are not required.

6. **Challenge a consequential claim.** Ask for independent replay of the exact
   effect on a fresh, clean original target with the same starting conditions
   and actor capability. Show ordinary behavior and a control that removes the causal
   condition. Declare research-only source edits and instruments; an effect that
   depends on changed target logic, injected private state, or extra privilege
   is a different claim. Give a fresh reviewer the exact claim, raw and contrary
   evidence, conditions, and source, and ask for an independent check of a
   material link. Renew affected review after a material change. A strong lead
   can remain unfinished; final dismissal as disproved or irrelevant needs
   evidence and fresh review.

7. **Resume from evidence.** In a new context, read the saved research notes,
   `/workspace/NEXT.json`, scripts and results, and the current operator run snapshot
   before dispatching another effect. Reconstruct the active hypotheses, failed tests, unfinished conditions,
   source and service state, pending effects, prior review, and remaining shared
   allowance. Native conversation history may help, but does not replace material
   evidence. A stale generated summary or unrelated scratch does not define this
   state or require view repair before continuing. An absent advisory notebook
   does not block resume; reconstruct from the saved research material. If a
   material fact is missing or an effect is uncertain, mark it
   unresolved and reconcile under operator authority; never reset spend or
   blindly repeat the effect.

8. **End truthfully.** Save the requested internal result as an ordinary file
   under `/workspace/project` and reference it from any maintained working notes.
   Include supported effects, controls, contrary evidence, invalid or assisted
   parts, and unfinished leads.
   Reconcile every affected claim and dependency with its evidence and renewed
   review after material edits. Distinguish agent tests, host replay and independent
   review; wording or a matching phrase establishes none of them. A harmless quote
   does not block work and an unsupported paraphrase is not accepted impact.
   Record what allowance, user instruction, safety or a blocker stopped. No empty
   queue, signed ending, memory/no-lesson record or formal closure is required.
   A proposed final closure, negative conclusion, or abandonment of a strong lead
   needs a fresh review with a concrete reason; budget or operator stop is immediate
   and bypasses that review. State the remaining uncertainty, not a claim that no
   effect exists. Have the host verify actual cleanup and remaining effects; a saved status
   cannot perform cleanup. If no effects or owned resources remain, no extra
   ceremony is needed. Learning remains optional under current memory permissions.
   A local result is not external delivery or a legacy accepted finding; those
   actions retain their separate authority and validation. A no-finding or
   unavailable run establishes neither target safety nor full coverage. Keep
   credentials, cookies, tokens and signed URLs out of durable notes and results.

   For a checked-setup source-only run, write `/workspace/project/RESULT.md` with
   nonempty `## Supported effects`, `## Controls`, `## Contrary evidence`,
   `## Tested paths`, `## Untested paths`, `## Assistance`,
   `## Unfinished leads`, and `## Limits` sections. Request a fresh
   `native-source-review-v1` host action after the final result draft and the
   final claim, coverage, capabilities, and lead state in `NEXT.json` are saved.
   Keep those fields, the result, and source bytes unchanged after that review. Then set
   `proposed_stop: true`, `next: null`, and `host_action: null` in `NEXT.json`.
   The continuation host checks that exact review, requests owner stop, and
   reads back cleanup and exact resource absence. An unavailable review holds
   the claim; an operator, allowance, or unknown-effect stop ends the run as
   incomplete without another review experiment.
