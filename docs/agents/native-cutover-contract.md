# Native local research cutover contract (candidate)

This is the proposed source delta for issues #166–170. Issue #165 has no scoped adopt
decision. Keep this branch separate from the active default until the operator records
that decision and the final native workflow is qualified. A failed or pilot decision
does not enable this cutover.

## Failure conditions fixed before implementation

1. A fresh worker follows the legacy queue from root or bootstrap instructions when
   the adopted local class should start a native run; or a legacy worker loses its
   supported entrypoint after this change.
2. The native run inherits a queue Stop hook, exact-next-action admission, manual
   attempt/event pairs, harmless-file registration, signed report acceptance, or
   formal closure as a condition of ordinary research.
3. A user stop, allowance exhaustion, denied effect, uncertain dispatched request,
   changed source, or failed cleanup is hidden by a successful-looking note or view.
4. A material strong lead is marked disproved or irrelevant without fresh review;
   a changed claim/evidence remains accepted by an earlier review; a local draft
   is represented as an external submission or canonical confirmed filing.
5. A quote, stale generated view, or unrelated scratch file controls native
   execution or result validity. Historical record tampering or corruption goes
   unnoticed because a legacy reader/check was removed.
6. A source-bootstrap mirror gives a different procedure depending on the agent
   that loaded it. Existing engagements or global user configuration change.

## Caller and control inventory at PR #185 head `d94e908`

| Candidate | Current caller or consumer | Cutover treatment |
| --- | --- | --- |
| `tools/run-work-queue.py`, `work_queue_driver.py`, `work_queue_admission.py`, `driver_action_admission.py`, `work_queue_actions.py` | Public Docker queue CLI, `run-engagement.py` queue commands, Docker session runtime, CI and queue tests | Retain for supported legacy work. Native CLI must have no import or dispatch to these modules. |
| `.claude/settings.json`, `tools/claude-stop-hook.py`, `tools/container_broker_client.py` | Project Claude Stop setting and legacy Docker queue session | Retain while a supported legacy Claude caller exists; native OpenCode route does not load Claude settings. |
| `run-engagement.py`, `engagement_state.py`, `engagement_records.py` | Public legacy record writer/reader, `inspect-dossier.py`, `finding_lifecycle.py`, `reporting.py`, migration and self-tests | Retain. Native files are outside `engagements/<id>` and do not append legacy ledger entries. |
| `completion_claims.py`, `engagement_views.py` | Legacy mutation/render/read path in `run-engagement.py` and `engagement_state.py`; historical inspector | Retain for legacy state integrity. Native output has no generated-view admission. |
| `finding_review.py`, `reporting.py`, `memory_disposition.py` | Legacy finding/review/report/submission and closure commands | Retain for legacy. Native review/output does not call these writers; external filing stays separate. |
| `skills/source-engagement-bootstrap/` and `.pi/skills/source-engagement-bootstrap/` | Claude/Codex and Pi skill discovery; goal templates point to canonical reference | Keep Pi's discoverable entrypoint as a pointer to the canonical skill; remove its stale duplicated references/script. Keep legacy template paths for existing work. |
| `README.md`, `AGENTS.md`/`CLAUDE.md`, `docs/agents/`, `engagements/_TEMPLATE/` | Fresh-worker instructions and legacy template/help | Route the adopted class to one native recipe only after #165; leave named legacy recipe for existing work. |

This inventory is a deletion boundary, not evidence that the native route is qualified.
Historical ledgers, hashes, signatures, waivers, frozen campaign pins, and active
engagements remain unchanged. Other blind behavioral and GEPA adapters stay separate.

## Intended public interface

The candidate native route uses `tools/native_research.py prepare`, `research`,
`resume`, `review`, `status`, `stop`, and `recover-start` on a persistent
run root; consult each command's `--help` for current arguments. For the pinned
Kanboard T01 API-only route, `prepare` opts into `--t01-capture
--origin-ingress`; `--kanboard-capture` selects the separate UI capture route.
`capture-stage` binds each private target copy, and the qualification approval
binds the frozen plan and target state. A future standing grant needs exact
target/model/effect/expiry binding. After stop, `reconcile-origin-transport`
assesses process-bound transport origin, while `reconcile-t01-semantic`
separately assesses the selected API effect and controls from frozen receipts
and target state. Neither establishes clean replay or fixed-control
qualification. `assess-poststop-review` composes the reviewer turn with
the reviewer-target T01 effect/control chain and process-origin attribution for
the selected requests. A successful assessment produces at most a partial
candidate for operator review. Live qualification, clean replay, fixed control,
and review of strong-lead dismissal remain separate requirements as applicable.
Offline checks exercise source and synthetic evidence only; they do not qualify
a provider or target.
Research files live in the run root, with observer capture and sanitized
reviewer handoff. The route preserves the legacy queue and record path for
existing work and has no dependency on either.

## Public-workflow checks to execute after the last edit

- From a clean checkout, follow only root/README/skill pointers to prepare a
  permitted local source task; confirm one native start/resume/stop path, an
  explicit allowance, persistent workspace, observer capture, and review input.
- Interrupt after material workspace/target state and before a fixed test trigger;
  resume the exact session, preserve a strong unfinished lead, and report a
  budget/user/blocked stop without claiming exhaustive coverage.
- Change a material claim after review; require a fresh review. Deny an effect
  and force an uncertain request; confirm neither becomes accepted impact.
- Draft the requested internal result and reconcile every effect/condition with
  independent observation and review. Verify actual cleanup and remaining effects.
- Read a retained legacy engagement and corrupt a disposable copy; historical
  readback must remain read-only and corruption must fail visibly. Check the
  legacy public CLI/help and Docker queue path are still available.
- Restore the pre-cutover branch in a disposable checkout and confirm old records
  remain readable. Compare the exact changed paths and decision revision before
  any default switch.

The first four are provider/target qualification checks and remain pending in
this branch. The local checks can verify syntax, references, source topology,
help, and historical readback without starting a provider or target.
