# Continuation controller checks

Status: controller implemented; the retained evidence establishes no native model,
provider, target, comparative or multi-day qualification. These checks are offline contracts.
The inventory was added after candidate implementation. The smoke calls the
controller function with a synthetic child-runner CLI; it does not cover the
public `native_research.py continue` entrypoint.

## Failure inventory

| Failure | Required behavior | Covered by |
| --- | --- | --- |
| Two loops on one run | One lease; the second loop is rejected | `test_lease_blocks_second_loop` |
| Controller crash after dispatch | Pending marker survives; next loop refuses to redispatch | `test_pending_dispatch_is_not_retried` |
| Missing receipt reconciliation | `no_effect` clears pending; `effect_observed` clears pending and keeps the stop; acknowledged receipt is refused | `test_reconcile_no_effect_clears_pending`; `test_reconcile_effect_observed_stops` |
| Acknowledged dispatch in reconcile | Refuse as already completed; do not drop its receipt | `test_reconcile_refuses_acknowledged_dispatch` |
| Strong-lead abandonment | True-to-false transition produces a closure request | `test_strong_lead_abandonment_requires_review` |
| Spend reset | Decreasing shared spend stops the loop | `test_spend_reset_is_detected` |
| Previous terminal stop | Requires explicit `--resume-after-stop`; no silent retry | `test_previous_stop_requires_explicit_resume` |
| Child reports unknown effect | Stop; preserve pending; require reconciliation | `test_unknown_effect_preserves_pending` |
| Child success without spend evidence | Stop; preserve pending; do not reset or retry | `test_spend_unavailable_preserves_pending` |
| Missing native session | Reconstruct from workspace; record the reconstruction | `test_context_loss_reconstructs`; smoke check |
| Missing or invalid next brief | Stop; do not invent an experiment | `test_missing_next_brief_stops`; `test_invalid_next_is_rejected` |
| Inactive or stopped run | No new invocation | `test_inactive_run_blocks_invocation` |
| Stale checkpoint or changed plan | Reject; no dispatch | `test_stale_checkpoint_is_rejected` |
| Operator stop | Durable stop; no new invocation | `test_operator_stop_blocks_invocation` |
| Invocation bound | Stop at the declared maximum | `test_max_invocations_and_journal` |
| Proposed final closure | Stop for a request-bound review artifact; reviewer independence remains procedural | `test_accept_closes`; smoke check |
| Reviewer reopens | Require a concrete next brief, then continue | `test_reopen_requires_next_and_resumes` |
| Stale closure review | Reject a review bound to a different request | `test_stale_closure_review_is_rejected` |
| Malformed closure review | Reject wrong kind, decision, or missing reason | code path; not separately tested |
| Expired approval / exhausted allowance | Child must reject before dispatch; controller must stop | Synthetic expired-child rejection is covered; actual child approval/allowance checks through the controller remain unrun |
| Repeated identical next brief | Not implemented; requires an observed failure and a decision | not covered |

## Contract

- `NEXT.json` is the only research handoff. It records a result state
  (`supported`, `refuted`, `blocked`, `inconclusive`), what the result rules out,
  useful capabilities and coverage, and either a next brief or a stop proposal.
- The controller writes `controls/continuation/state.json`, `events.jsonl`, and
  `closure-request.json`; these are not research authority.
- A missing next brief is a stop, not a request to speculate. A refutation may close
  a lead. A blocked surface stays unresolved. Coverage is not proof of absence.
- The native 24-hour run ceiling remains. The runner hard-rejects
  `duration_seconds` above 86400 and approval expiry more than 24 hours after
  `approved_at`; a multi-day run needs both a new plan/approval and a reviewed
  validator change. The controller does not renew authority or reset spend.
- Live model/provider behavior, target effects, independent replay, fresh review and
  a real multi-day run remain unqualified.
