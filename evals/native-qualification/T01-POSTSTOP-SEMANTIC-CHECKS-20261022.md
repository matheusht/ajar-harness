# T01 post-stop semantic reconciliation: failure checks before code

Decision: inspect the frozen, observer-owned T01 collector and the stopped
application database for one narrow claim: an ordinary user received a
swimlane's metadata despite being denied access to its project. The checker
does not run a target, retry a request, grant native origin, perform clean
replay, or accept a reviewer conclusion. It works for the researcher target
and either separate reviewer target, derived from the selected native dispatch.

| Failure | Required provider-free check | Result |
| --- | --- | --- |
| A project or lane was inserted by setup, another actor, or a direct DB edit | Setup receipt and DB readback have zero projects/lanes. A `createProject` receipt names the logged-in actor, returned project ID, before/after project counts, owner/manager row and name digest; an `addSwimlane` receipt names its returned lane ID, input project ID, before/after lane counts and matching row. Each creation receipt belongs to an earlier closed native window. | Hold creation provenance. |
| The automatic default lane is mistaken for the agent's created lane | The selected lane ID must be the integer result of `addSwimlane`, with the same project ID and name digest. | Hold. |
| Project ownership, direct/group role, or public state makes the cross-role read authorized | At the effect's captured prestate, the other user is not the owner, has no direct/group project role, and `is_public=0`. A separate `getProjectById` request by that user is denied with HTTP 403. | Hold. |
| A different ID, a redacted field, or an API error is called the effect | The selected `getSwimlane` receipt is HTTP 200, `swimlane_result`, and `result_matches_db=true`; its requested, returned and DB IDs/project/name digest agree. | Hold. |
| Ordinary behavior is broken | The authorized actor's `getProjectById` and `getSwimlane` succeed for the same project/lane with matching DB identities. | Hold. |
| Source, target, dispatch, or collector changes after stop | Require exact T01 plan/source/code pins, acknowledged dispatch, target derived from role, complete NativeRun stop, host snapshot, capture freeze and cleanup. Compare collector bytes/count with `frozen.json` and target tree with `host-snapshot.json`. | Hold before semantic selection. |
| A receipt is from another target/window, outside the selected dispatch, duplicated, or only a copied native response ID | Validate every selected receipt against its own window prefix and closed row list. The effect ID belongs to the selected dispatch, and every selected ID is in exactly one closed window's joined response IDs. This is correlation only; a separate qualified process-origin proof remains required. | Hold. |
| A later dispatch is mistaken for an earlier dispatch's receipt | Use the closed window's `collector_count_after` as the upper bound, not every row after `collector_max_id_before` in the final database. Reject overlapping or inconsistent windows. | Hold. |
| Readable final DB contradicts captured state or has an unaccounted mutation | Check SQLite integrity and exact stopped tree bytes; require the selected project/lane and both user roles in the final DB to match the effect receipt. | Hold; a prior receipt may remain a partial observation. |
| A local fixture or historical fixed-release preflight is called a native pass | Synthetic offline checks establish only parser and boundary behavior. The result reports `effect_and_controls_observed` separately from held native origin, clean replay, fixed/causal control and fresh review. | No #158/#159/#160 pass. |

Provider-free check to write before implementation:

```sh
python3 evals/native-qualification/smoke/check_t01_poststop_semantic.py --output /private/tmp/t01-semantic-check-NEW
```

It creates an in-memory synthetic SQLite database and receipt chain, then
writes a result under a new private output. It checks the positive narrow
chain, absent or altered creation result, wrong actor/role, missing ordinary
or denial control, a changed effect dispatch, and unjoined selected receipts.
The full stopped-run boundary and reviewer-target isolation are implemented
in `reconcile-t01-semantic`; they require a real frozen run and are not
exercised by this synthetic check. No Docker, provider or application process
is used. The result must say `synthetic_provider_free` and `status=pass`.
