# Agent-requested paired patch check: failure-first scenario

Issue #207 adds an optional source-only action. A goal opts in with the exact
line `Patch goal: required` in its frozen, scope-bound `BRIEF.md`. The agent
writes `/workspace/PATCH.diff` and asks for `native-patch-check-v1` in
`/workspace/NEXT.json`. The host applies the diff to a clean original copy;
the reviewer writes independent checks. The patch is never submitted as an
original-target replay. A goal without that line may close without this action.

## Failures defined before implementation

| Failure | Required result |
| --- | --- |
| Missing goal opt-in, stale plan/approval, or exhausted allowance | No patch or reviewer dispatch. |
| Missing, empty, unsafe, oversized, or changed diff; diff escaping the tree | Reject before review and preserve the reason. |
| Original target differs from its plan manifest | Reject before applying the diff. |
| Patched tree differs from the exact applied diff or either saved manifest changes | No checked-fix result or cached readback. |
| Reviewer check file is missing effect, causal control, ordinary function, or connected-path command | No host checks. |
| Patch changes a reviewer check script, or a command changes that script during execution | Reject the check instead of crediting a passing test. |
| Original and patched checks run different commands, source inputs, actor, or initial-state envelope | Reject the pair. |
| Review is interrupted after dispatch, a receipt is missing, or execution status is unknown | Hold incomplete; never automatically retry the effect or consume another reviewer slot. |
| Effect is not differentiated, normal or connected behavior regresses, or reviewer does not bind the effect/fix link to the diff | Keep fix unproven; retain the observations and limits. |
| Stop or cleanup is missing, uncertain, or reports surviving resources | Do not mark the engagement complete. |

## Contained scenario

1. Make a private, harmless source fixture whose `app.py` prints `before` for
   the `effect` argument and echoes the `control`, `normal`, and `connected`
   arguments. The diff changes only `before` to `after`. Freeze its
   source, signed-goal hash, plan, live approval and resource allowance. Write
   the diff and one typed agent request.
2. Through the native continuation entry, freeze the diff, reproduce patched
   bytes from the original, create separate full manifests, and pass a packet
   to a fresh reviewer. The reviewer chooses four commands (effect, control,
   normal, connected). Freeze the definition and reviewer scripts once, then
   run each command on three clean original copies and three clean patched
   copies with the same approved source executor. Save commands, actor, initial
   state, results, hashes, allowance, reviewer trace/receipt, and cleanup.
3. Challenge each failure above on disposable copies. After a dispatched
   uncertain check, replay must not run it again. A patched execution must be
   labeled patched and cannot satisfy an original replay. The reviewer must
   read and hash paired host evidence before any checked-fix candidate is
   returned. A changed test or manifest must block cached readback.
4. Let the agent read the hash-bound result. Keep the internal claim bounded
   and use the existing result and cleanup path. First return an uncertain
   cleanup receipt and verify closeout holds; complete the synthetic cleanup
   and verify closeout succeeds without another stop. A second fixture without
   the opt-in line must close without a patch check.

Run from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 evals/native-qualification/smoke/check_agent_paired_patch.py \
  > evals/native-qualification/AGENT-PAIRED-PATCH-LOCAL-CHECKS.json
```

Expected output is JSON with `status: passed`, all four reviewer commands,
`before`/`after` for the effect, matching `control`/`normal`/`connected` output
across the pair, 8 command executions with 3 clean replays each, denied cases,
the bound patch request, execution receipts and hashes, verified cleanup
receipts for patch and no-patch closeout,
and `provider_calls: 0`, `target_calls: 0`.
The command uses disposable source trees and synthetic provider/Docker receipts.
Fresh review identifiers and their derived hashes vary between runs; the
commands, outputs, denial outcomes, and cleanup statuses should agree.
It tests the host's binding and control flow, not a live provider, attacker
reachability, actual target effect, hosted CI, or live cleanup. Those remain a
separate authorized acceptance gate.
