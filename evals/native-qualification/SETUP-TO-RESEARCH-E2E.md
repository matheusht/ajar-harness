# Checked setup to native research: failure-first scenario

Issue #204 joins the checked offline setup package to the existing source-only
native route. The agent's recipe and threat model are proposals. The host must
verify the checked package and still require the separate, exact research-plan
approval before starting research. A caller must not supply a new build command
or dependency set at this transition.

## Failure cases written before implementation

| Case | Required result |
| --- | --- |
| No checked package, proposal only, or package not `ready` | Reject before creating a research run. |
| Changed source, scope, goal, setup output, builder output, or dependency bytes | Reject the changed input; an old receipt cannot authorize it. |
| Changed or stale setup/build approval, missing signature, or changed signer | Reject before research preparation or Docker contact. |
| Invalid image/platform, runtime probe, build argv, or dependency closure | Reject; do not substitute an operator command or fetch packages. |
| Package says cleanup complete but an owned resource remains | Reject until exact resource absence is verified. |
| Research plan or approval omits or changes the checked-package pin | Reject before research start. |
| Transition interrupted after preparation | Resume only against the same immutable plan and package; do not duplicate setup build or reset setup spend. |
| Threat model correction in research | Preserve the original pinned threat model and record the correction as a new observation. |
| Setup result or repeated build presented as a security effect | Keep it as setup evidence; require original entry-path evidence and independent review for a claim. |

## Public end-to-end scenario

1. Use a fresh harmless multi-file source and a signed scope with only the
   approved setup effects. Save the source, goal, scope, model/image IDs,
   signers, approvals, allowance, and expected source output. Run the bounded
   setup turn and the offline host builder. Keep their exact receipts and
   cleanup readback.
2. Prepare research from the checked package, without an operator build command
   or dependency selection. Assert the research plan pins the source, setup
   output, builder receipt, runtime, dependencies, build argv, initial threat
   model, setup allowance used, and separate research allowance.
3. Present a human-authored research approval bound to that exact plan. Start
   the native owner, run one real research turn, pause, and resume. Verify that
   the workspace exposes the pinned initial threat model and setup trace and
   that the target runtime matches the checked package. A later correction must
   appear as a new research observation.
4. Mutate each input from the failure table in disposable copies. Assert that
   no target build or native turn is dispatched. Stop and verify exact owned
   resource absence and remaining effects. Save CLI output, plan and receipt
   hashes, trace, allowance, assistance, and cleanup as the repeatable result.

A synthetic local scenario may check the transition mechanics, but it cannot
qualify the live model, provider, or a new target. The live scenario needs a
fresh signed target and authority supplied for that run.
