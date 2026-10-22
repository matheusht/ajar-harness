# Kanboard seeded baseline: checks before implementation

This is a host-only pre-start gate for the S/Q/T/B case in #157. The pinned
Kanboard source routes `TaskViewController::show(T)` through
`ProjectAuthorizationMiddleware`, which obtains Q from T, and
`ProjectRoleHelper`, which uses B's direct or group Q role. The smallest useful
gate reads each staged target's private SQLite database before live approval
and again before producer creation. A stage hash and database hash alone bind
bytes but do not establish that those bytes contain the intended case.

The stage record names S, Q, T, and B. It does not name A or C, carry a task
marker, or contain a fresh authenticated B denial. This gate can establish a
state-derived initial-denial precondition: B is an ordinary user with no direct
or group role on private, tokenless Q, and active T belongs to Q. It cannot
claim that Kanboard actually returned HTTP 403, that the intended A owns the S
manager row, or that a native process made a request. Those remain separate
live observations and holds.

## Failure inventory and required provider-free checks

| Failure | Check before code | Required result |
| --- | --- | --- |
| Stage uses zero, duplicate S/Q, or a changed positive ID | Try invalid `capture-stage` IDs and a stage pointing at a different seeded Q | Reject before any Docker call. |
| DB missing, non-SQLite, corrupt, or with an uncheckpointed WAL | Replace one staged private DB or leave a WAL sidecar | Reject before approval; do not copy or expose DB bytes. |
| S missing/inactive or without an ordinary project manager | Delete S, deactivate it, or remove the role | Reject the case. |
| Q missing, public, tokenized, inactive, or owned by B | Change each relevant Q field | Reject the state-derived denial precondition. |
| T missing, inactive, or outside Q | Change task row | Reject the case. |
| B missing, admin/manager, inactive, or already has S/Q direct or group access | Change B or permission rows | Reject the baseline before dispatch. |
| Valid seeded state with a wrong approval stage hash | Keep all three DBs valid and supply a wrong stage hash | Reach `live_approval_mismatch`, proving state passed while approval binding still fails. |
| DB or immutable source changes after approval but before producer start | Change T title or the pinned controller after the approval archive exists | The final producer-start gate rejects changed DB bytes or source before `native.start()`. |

Run the existing provider-free CLI workflow with a clean pinned Kanboard source,
Python 3, OpenSSL CLI, and the local pinned relay binary:

```sh
python3 evals/native-qualification/smoke/check_native_research_capture_stage.py \
  --source /private/tmp/kanboard-source-644ad391 \
  --output /private/tmp/native-research-seed-baseline-NEW
```

Expected: `result.json` status `pass` and zero provider/Docker calls. The
fixture databases are synthetic, contain no account secrets, and stay under the
private output directory. A pass proves this pre-start gate only; it is not a
fresh app denial, live target run, provider response, or native qualification.
