# Engagement board and steering check

This local check exercises the real v2 controller and runner with a simulated native boundary. It
does not call a model provider, Docker daemon, target, CI, or pricing path. Its output must label the
run `engineering_simulation` and research acceptance `not_run`.

## Failure-first scenarios

1. **Search and snapshot:** Call `Controller.board(principal, query=, kinds=, since=, limit=)` and
   the native `engagement_status` board view. Create journal tasks and publications (including
   observations, instruments, claims, and a correction with `supersedes`). Search and paginate a board snapshot.
   Assert author/source, provenance, verification state, and correction links survive projection;
   page size is bounded; continuation is stable when a later journal event arrives; query bounds
   are enforced. A board result never changes journal state.
2. **Peer communication:** A current worker sends `team_message` with `message_id`,
   `recipient_ids`, `subject`, `body`, and publication `refs` to eligible current recipients.
   The host records the authenticated author and stable event reference. Invalid or unknown
   recipients and malformed content fail closed. Replaying peer text cannot create a task, change
   assignment, scope, or role.
3. **Native delivery and recovery:** The simulated runtime records `Runner._updates` steering. A relevant peer or
   operator update is steered once with its stable event reference; unrelated events are not
   delivered. A durable acknowledgement survives a newly constructed controller/runner and status
   recovers changes after the saved cursor without replaying acknowledged events.
4. **Revocation:** Revoke a worker, then attempt a late message/ack from its old principal and
   deliver an already queued notice. Submission is rejected, no stale worker is revived, and the
   notice cannot change authority or resume execution.

Each assertion is against journal/controller state and the simulated boundary's observed calls,
not a prompt-only claim. Keep fixture scope signed and harmless.

## Local result

Command: `python3 evals/native-qualification/smoke/check_engagement_board_e2e.py --output evals/native-qualification/team-evidence/shared-board-20261115/result.json`

All four scenario groups passed as `engineering_simulation`; provider, Docker, and target calls
were zero. This is mechanics evidence, not research acceptance or the operator's full-day target
test. See the saved [JSON results](../team-evidence/shared-board-20261115/result.json).
