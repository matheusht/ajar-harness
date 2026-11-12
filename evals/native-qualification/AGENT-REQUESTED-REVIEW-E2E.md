# Agent-requested source review: failure-first check

This is the contained source-only workflow for issue #205, starting from the
reviewed #203 source-action commit `0f4863d612722443b64590640b2f6bec052a8b78`.
A real run needs a signed target-local scope, prepared offline source runtime,
live plan-bound approval, shared allowance, and permitted provider route. This
document grants none of them. The local check uses synthetic host receipts and a
fake native reviewer; it makes no provider or target call.

## Failures to check before implementation

| Failure | Required behavior |
| --- | --- |
| Malformed, stale, symlinked or changed request/claim/source | No packet or reviewer session; keep the request and its reason. |
| An adverse source batch is omitted from the agent request, or a protected batch/terminal/output changes or is missing | Host enumerates every protected source action independently; the packet includes the adverse batch or the request stays incomplete. |
| A required raw output is withheld, sensitive, oversized, or unavailable | No silent drop or favorable summary; keep review incomplete. |
| Agent notes omit a failed result or an unfinished lead | Packet includes the host's entire source-action corpus and labels the frozen notebook/checkpoint as agent statements. It does not claim unknown native tool content was reviewed. |
| Original effect, causal control, actor or starting state is absent | The reviewer may investigate, but no security-effect or confirmed finding follows from repeated output. The result records the exact missing link. |
| Approval is stale, the shared allowance is exhausted, a prior action is uncertain, or the reviewer slot/store is reused | Reject before filling `/handoff` or creating a reviewer session. Recheck authority and allowance before dispatch. |
| The review packet or claim changes after freezing | Refuse dispatch or hold the result; an earlier review never covers new bytes. |
| A cached review projection remains but its protected receipt, host evidence, packet, observer selection or source-action corpus disappears or changes | Hold readback as incomplete; never send a second reviewer turn. |
| Reviewer dispatch is uncertain or a result is lost | Do not send a second review automatically. Reconcile from the exact protected receipt or leave it unfinished. |
| Review output is favorable without a material effect/control check | Keep the assessment unfinished or at most a candidate for operator review. Filing and escalation remain unauthorized. |

## Contained E2E scenario

1. Create one private source-only fixture with a current plan and approval, a
   native run identity and allowance, an empty reviewer slot, and a harmless
   script. Use #203's actual frozen source-action layout for two host batches:
   one `before` result and one contradictory `after` result. Keep a separate
   unfinished lead in the research checkpoint. The request names the claim,
   never the selected evidence files.
2. Submit `NEXT.json` with one `host_action` for fresh source review. Run the
   native `continue` entry against synthetic native turns. The host must freeze
   the exact request and current source, enumerate both protected source-action
   receipts, prepare the six-role observer selection, and reuse the existing
   read-only packet freezer and fresh reviewer. Its packet must contain both
   raw batches, the contradictory result, original source and conditions, and
   the unfinished state with provenance labels.
3. Challenge each failure above on disposable copies. Assert that a denied
   preflight leaves both reviewer handoff roots empty and creates no reviewer
   session. After an unknown, unfinished, or packet-changed dispatched review,
   a replayed request must not consume the second slot or issue another native
   turn. Repeat from a captured review with a missing or changed protected
   receipt, host evidence, packet, selection or source-action output; no researcher readback may
   be sent from the cached projection alone.
4. Return a hash-bound review receipt through the same run's read-only
   `/research` projection. Have the synthetic researcher read it on the next
   turn. Save exact source/check hashes, packet file hashes, reviewer action and
   receipt, source-action input and output hashes, allowance snapshots, denied
   cases, cleanup result, and the limits below.

Expected in an authorized live run: one review request yields one frozen packet,
one fresh reviewer turn, the host's effect/control executions, and one same-run
readback. The assessment is never `confirmed`; repeatable output alone has
`security_effect: unproven`.
The check is repeatable from the repository root with:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 evals/native-qualification/smoke/check_agent_requested_review.py
```

Save its JSON output as `evals/native-qualification/AGENT-REQUESTED-REVIEW-LOCAL-CHECKS.json`.
This synthetic command checks packet construction and control flow with a fake
reviewer receipt. It does not execute the existing source reviewer's effect and
control commands; those are exercised by the separate source-review checks. It
cannot qualify native model judgment, provider containment/cost, original
attacker reachability, a real target, or cleanup of a live owned runtime. Those
need a separately authorized, pinned E2E run.

For the cached-readback repair, the failure-first run removed the protected
reviewer receipt after a captured review. The old controller invoked the
researcher from the surviving projection and the check raised
`cached_readback_sent`. The saved result now records the blocked cached cases.
