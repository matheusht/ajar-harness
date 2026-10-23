# Native local research cutover contract (candidate)

The candidate native source route implements the source changes for issues #166–170. On 2026-10-22 the
operator authorized implementation of all five tickets and deferred testing to one
full E2E run after integration. New local source work follows the native entry;
existing queue/record engagements use the named legacy entry. This source change
does not establish qualification, a passing #165 adoption decision, or permission
to run a target. Signed scope, exact plan-bound approval, effect limits and external
action authorization still apply. The branch remains a draft pending that review.

## Failure conditions fixed before implementation

1. A fresh worker follows the legacy queue from root or bootstrap instructions when
   the new local class should start a native run; or a legacy worker loses its
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

## Caller and control inventory

The removal boundary was recorded before implementation at PR #185 head
`d94e908`; the treatment below records the integrated source change.

| Candidate | Current caller or consumer | Cutover treatment |
| --- | --- | --- |
| `tools/run-work-queue.py`, `work_queue_driver.py`, `work_queue_admission.py`, `driver_action_admission.py`, `work_queue_actions.py` | Public Docker queue CLI, `run-engagement.py` queue commands, Docker session runtime, CI and queue tests | Retain for supported legacy work. Native CLI must have no import or dispatch to these modules. |
| `.claude/settings.json`, `tools/claude-stop-hook.py`, `tools/container_broker_client.py` | Project Claude Stop setting and legacy Docker queue session | Remove automatic project Stop registration. Retain the hook and broker client for explicit legacy sessions, whose launcher writes the authenticated hook setting itself. |
| `run-engagement.py`, `engagement_state.py`, `engagement_records.py` | Public legacy record writer/reader, `inspect-dossier.py`, `finding_lifecycle.py`, `reporting.py`, migration and self-tests | Retain. Native files are outside `engagements/<id>` and do not append legacy ledger entries. |
| `completion_claims.py`, `engagement_views.py` | Legacy mutation/render/read path in `run-engagement.py` and `engagement_state.py`; historical inspector | Retain for legacy state integrity. Native output has no generated-view admission. |
| `finding_review.py`, `reporting.py`, `memory_disposition.py` | Legacy finding/review/report/submission and closure commands | Retain for legacy. Native review/output does not call these writers; external filing stays separate. |
| `skills/source-engagement-bootstrap/` and `.pi/skills/source-engagement-bootstrap/` | Claude/Codex and Pi skill discovery; goal templates point to canonical reference | Keep Pi's discoverable entrypoint as a pointer to the canonical skill; remove its stale duplicated references/script. Keep legacy template paths for existing work. |
| `README.md`, `AGENTS.md`/`CLAUDE.md`, `docs/agents/`, `engagements/_TEMPLATE/` | Fresh-worker instructions and legacy template/help | Route new local source work to one native recipe; move the queue/kernel runbook behind the named existing-engagement entry. Qualification remains pending. |

This inventory is a deletion boundary, not evidence that the native route is qualified.
Historical ledgers, hashes, signatures, waivers, frozen campaign pins, and active
engagements remain unchanged. Other blind behavioral and GEPA adapters stay separate.

Two unused pieces are removed before cutover: the uncalled
`engagement_records.summarize_errors` formatter and the duplicate local
`queue_command_payload` import in `driver_action_admission`. The shared import
and every action-selection check remain. These deletions do not retire a queue,
record writer, or historical reader; those still have the callers listed above.

## Implementation by ticket

| Ticket | Implemented source change | Retained dependency / remaining evidence |
| --- | --- | --- |
| #166 | Root, README, bootstrap, Pi discovery and template navigation lead new local source work to one native entry. The moved legacy runbook is explicit. | Existing engagements keep their queue/record route. Final fresh-worker E2E and adoption remain pending. |
| #167 | Remove project-wide Stop registration; update existing registration checks and legacy help/docs. | Explicit host/container session settings, scheduler/admission, reviewer selection, broker and cleanup remain required by the legacy CLI. |
| #168 | Native instructions save experiments and reviews once in ordinary files/captured evidence; no legacy record mutation is required. Remove the already-unused record formatter. | Public legacy writers, dossier/lifecycle readers, review records and integrity checks still have supported callers. |
| #169 | Native internal output and stopping require evidence, uncertainty, unfinished leads and actual cleanup, without report acceptance, queue exhaustion, formal closure or memory disposition. | Existing filing/report/closure commands keep their original authority and historical semantics. |
| #170 | Missing ordinary notebooks no longer gate native resume/reconstruction or host-byte receipt completeness. Existing workflow checks are updated before the code change. | Present notebook capture still validates safe paths and bounded bytes. Frozen inputs, native store, unknown effects, historical reduction/validation and registered bytes retain their checks. |

The queue conformance contract now names retained legacy doctrine and reads its
moved entrypoint. Its queue invariants and negative checks remain; it does not
make queue completion a native research requirement. Shared legacy modules are
not wholesale retired while the listed callers remain. This is the implemented
boundary, not a claim that every deletion candidate became unused.

## Intended public interface

The candidate native route uses `tools/native_research.py` on a persistent run
root; its `--help` and each command's help own the current interface. Later source
work adds source execution and candidate continuation; see the
[dated status](../wiki/native-research-status.md). For the pinned
Kanboard T01 protected API route, `prepare` opts into `--t01-capture
--origin-ingress`; select the exact workspace or historical API-only brief
as described in the [native guide](native-local-research.md#start-and-resume).
Workspace research does not expand the protected API's effect coverage.
`--kanboard-capture` selects the separate S10 UI case.
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

At the 22 October #166–170 integration pass, the runtime checks above were deferred
to the operator's final E2E. That pass used source/caller inspection and syntax/diff
checks; it included no tests, CLI execution, provider sessions, Docker workloads or
target runs. Subsequent source-mode and continuation work added bounded local
checks, described in [current status](../wiki/native-research-status.md). They do
not qualify the final integrated workflow or change earlier receipts' revision scope.
