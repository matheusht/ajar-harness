# Agent-owned internal closeout: failure-first scenario

Issue #206 starts from an active native research run with a current signed
scope, exact plan approval, host action receipts, and an agent-written internal
result. The host freezes the exact result and evidence, obtains any required
fresh review, stops the owner, and checks real cleanup before calling the
engagement complete. External filing and deployment are separate actions.

## Failure cases written before implementation

| Case | Required result |
| --- | --- |
| Missing, malformed, credential-like, or changed result or evidence link | Hold closeout; do not accept a claim or erase the draft. |
| Old review applied after the final result, source, effect receipt, or claim changed | Reject stale review and request a fresh check on the new bytes. |
| Strong lead dismissed without fresh review and contrary evidence | Keep the lead unfinished or reopen with a concrete next test. |
| Pending/unknown host or native effect | Stop dispatch; retain the effect and cleanup obligation as unresolved. |
| Agent labels untested paths safe or a bounded negative as full coverage | Return a bounded result that states the tested paths and limits. |
| Budget, operator, or safety stop | Stop immediately without a new review experiment; keep draft and unfinished work. |
| Operator stop arrives while review bytes are checked | Treat it as an incomplete stop and verify cleanup before returning. |
| Review asks for a new test | Reopen only under the same live approval and remaining allowance, with a concrete next test. |
| Owner stops but cleanup/readback is absent or incomplete | Do not mark complete; record exact owned resources and remaining effects. |
| Docker context points at a different daemon during cleanup readback | Reject completion; check the daemon identity pinned before resource creation. |
| Controller reports `closed` without actual native stop | Keep engagement open until stop and cleanup are verified. |
| A stop proposal depends on manually running a second closeout command | The continuation controller invokes closeout and returns the verified terminal status. |
| A source-only stop proposal lacks a result or uses stale review | Prompt the agent to complete the result or request fresh review under the same allowance; unchanged bytes after a turn stop incomplete. |
| Fresh review says reopen | Put its concrete next check in the next agent prompt under the same live approval and allowance. Freeze the old proposal, result and review; require fresh review after material changes. |
| The reopened agent leaves `NEXT.json` unchanged | Stop incomplete; do not loop on the same proposal or dispatch another effect. |

## Public end-to-end scenario

1. Start a contained signed fixture with a live owner and one native research
   turn. Have the agent write an ordinary internal result that names supported
   effects, controls, contrary evidence, tested and untested paths, assistance,
   and unfinished leads. Save its exact bytes and linked evidence hashes.
2. Request closeout. Freeze one result version and give a reviewer that version
   plus the complete relevant evidence. Exercise an accepted closeout and a
   review that reopens a strong lead with one concrete next test. Mutating the
   result after review must invalidate that review.
3. Exercise blocked, bounded negative, unknown-effect, budget-stop, and
   failed-cleanup endings on disposable copies. None may claim target safety.
   No new target effect may be dispatched after stop or while an effect is
   unknown.
4. For accepted closeout, call the existing native `stop`, wait for the owner
   to finish, inspect exact container and network IDs, and read back remaining
   effects independently. Save the result/version, review request and receipt,
   host action receipts, native trace, limits, stop reason, cleanup receipt,
   resource absence, and observed output as a repeatable artifact.

Local synthetic checks can establish control-flow behavior. A live provider,
fresh target, and independent effect readback are required to qualify an
actual security conclusion or the full agent-owned engagement.
## Repeatable contained check

From the repository root, run:

```sh
python3 evals/native-qualification/smoke/check_agent_closeout.py \
  > /tmp/agent-closeout-e2e.json
```

It needs Python 3 and the repository checkout. It uses disposable run roots,
synthetic owner and Docker responses, and no provider or target calls. Expected
output is JSON with `status: passed`, `provider_calls: 0`, `target_calls: 0`,
source, continuation and check hashes, and a `continuation_bridge` case map.
The checked-in result of this run is
[AGENT-CLOSEOUT-E2E-RESULT.json](AGENT-CLOSEOUT-E2E-RESULT.json). That map checks
automatic acceptance after an agent turn, autonomous reopen with a second fresh
review, stale-review refusal, immediate user/allowance/unknown-effect stop,
delayed cleanup readback, wrong-daemon refusal, stop-request replay, agent repair of a missing result, fresh review after a changed result, and a no-change reopen ending. The redirected JSON is
the saved local result. It is control-flow evidence only; the cleanup receipt
and resource absence in these cases are simulated.
