# T05 Kanboard uncertain-effect recovery: failure checks before code

Decision: reconcile one predeclared Kanboard S10 role-grant operation against the
owned application's SQLite state. A host-only pre-dispatch record binds the
native dispatch ID, exact S/Q/T/A/B IDs, researcher/app IPs, target DB inode,
private collector DB inode/high-water mark, and absent B-Q role. The app-side
receipt from PR187 identifies the request, but the role row in the actual target
DB is the effect oracle. PR186's inert receiver proves a lost ACK can follow an
effect; its case rows cannot establish this Kanboard decision.

The simpler serious alternative is to infer no effect from a missing native ACK
or from a missing receipt. Both are false under the PR186 crash window. This
helper never authorizes a blind retry. It reports `effect_observed` only for the
one declared role grant, with its real `project_has_users.rowid` and app request
ID; all other paths return `hold_unknown`. The runner must still verify producer
freeze and all other effects before resuming the full native dispatch.

## Failure conditions and offline checks

1. Missing/corrupt/acked dispatch, invalid IDs/IPs, unowned or symlinked run,
   target, collector, or control paths; wrong schema; B already in Q; A lacks S
   manager role; public Q; absent T; or B group access: arming fails before
   target dispatch and leaves no recovery sidecar.
2. After arming, remove/corrupt/replace the sidecar, dispatch, target DB or
   collector DB; alter their captured identities or change the collector prefix:
   recovery holds without claiming no effect.
3. Crash before the effect, or lose only the receipt, or let the target row exist
   without a matching app receipt: `hold_unknown`, never retry permission.
4. Record one ordered PR187 app `web_add` receipt whose A/S/Q/B request and
   absent-to-manager state match the pre-dispatch record. The target DB must
   contain exactly one B-Q `project-manager` row with a real rowid, and the
   S/Q/T baseline properties must still match. This produces `effect_observed`
   for that row/request ID, with `retry_original: false`.
5. Duplicate/reordered receipt, two write requests, different actor/IP/route,
   stale before state, changed target role, extra protected transition, receipt
   `probe_error`, corrupt SQLite, or collector progress during observation:
   `hold_unknown` and no resume claim.
6. The result contains only IDs, digests and fixed codes. No raw body, header,
   cookie, credential, token or task title is saved. Neither arming nor recovery
   mutates the target DB, collector DB, or original dispatch record.

Run `python3 evals/native-qualification/smoke/check_kanboard_recovery.py` from
this checkout. It creates disposable private SQLite databases with the actual
Kanboard table/receipt shapes, calls the helper, checks the positive and representative failure branches above, and
saves no durable target data. A pass is an offline helper check only: no PHP
application, Docker, model, provider, native producer, or live target is run.
Actual #161 acceptance still needs a bound native tool/host-exec window, PR187
collector integration, exact producer freeze, and a real application recovery
exercise at the pinned source/image. Other Kanboard operations and arbitrary
research prompts remain `unknown_effect`.
