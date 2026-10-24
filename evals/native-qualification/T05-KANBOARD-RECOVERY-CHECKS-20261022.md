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
Actual #161 acceptance still needs a live single-POST interruption, exact
producer freeze, and real-application recovery at the pinned source/image.
Other Kanboard operations and arbitrary research prompts remain
`unknown_effect`.

## Runner integration failure checks (written before implementation)

The normal `resume` CLI may explicitly select this one S10 operation after a
prior unselected turn prepared the broker's A session and CSRF token.
The selected turn must bind the already sealed native dispatch window, staged
S/Q/T/B IDs, unique active A manager in S, attested researcher and observer IPs,
and private collector DB before `opencode run`. Missing capture, changed stage,
wrong role/target, ambiguous A, missing or changed window/topology, or any helper
arming failure must leave the durable dispatch `unknown_effect` and must not call
the native turn. An unselected turn must retain its existing behavior and create
no recovery sidecar.

Reconciliation is an explicit post-stop read. A live run, absent or incomplete
final/recovery record, missing exact REVOKED/manifest/host snapshot proof, missing
or changed frozen collector digest, acknowledged dispatch, or an unarmed turn
must return `hold_unknown`. It must never retry the original call, resume the
run, or rewrite the dispatch. A valid stopped record delegates only the one
declared S10 effect to the helper. The broker's backend TCP source is loopback;
the helper must check the broker-recorded peer against the attested researcher
IP, broker handle A, and broker request ID, while continuing to hold native
process-origin confirmation separately. A direct or malformed receipt holds.

Provider-free checks should exercise selected arming, unselected behavior,
fail-before-native paths, post-stop refusal, and the broker receipt's positive
and negative shapes. Passing checks show local wiring only; live interruption,
recovery, and exact native process origin remain unproven.

Run `python3 evals/native-qualification/smoke/check_native_role_grant_integration.py`
from this checkout for the selected-turn and post-stop fixture checks. In the
real workflow, first use an unselected turn to prepare A's broker session and
CSRF token, then select exactly one planned S10 POST with
`resume --observe-kanboard-role-grant`. After the owner exits with
`stopped_complete`, use `reconcile-role-grant --run-root ... --dispatch-id ...`.
Any extra request in that selected window produces `hold_unknown`; it is not a
no-effect verdict. The result never permits retrying the original dispatch or
resuming the stopped run.
