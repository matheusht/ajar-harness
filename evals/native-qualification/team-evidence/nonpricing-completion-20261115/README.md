# Shared team state and owned application completion — 15 November 2026

The operator excluded further pricing/billing and dollar/token caps, asked to finish
shared communication and the whiteboard, and selected operator-owned Docker
database/volume state. The candidate implementation remains on PR #220.

The searchable board is a view of the existing journal. The existing status tool
exposes stable search pages; typed team messages and native steering deliver peer
updates, while durable acknowledgments recover missed journal pages. Export includes
the same board. Recipient lists route notices; messages remain team-visible.

Application profile v2 declares bounded disposable state volumes. The signed
startup initializes their baseline inside the container, with Docker copy disabled. It records exact creation/ownership and refuses clean settlement
when volume removal is uncertain. An optional signed application artifact effect
uses the existing intent/readiness/cleanup ledger. This is not an existing external
volume attachment, an external database reset API or durable disk snapshot support.

## Repeatable evidence

Run from the repository root with Python 3, OpenSSL and ssh-keygen:

```sh
python3 evals/native-qualification/smoke/check_engagement_board_e2e.py --output /tmp/board-result.json
python3 evals/native-qualification/smoke/check_application_state_volumes_e2e.py --output /tmp/volumes-result.json
python3 evals/native-qualification/smoke/check_application_artifact_e2e.py --output /tmp/app-artifact-result.json
python3 tools/check-conformance.py
```

The scenario documents specify inputs, expected outcomes and test boundaries:
[shared board](../../smoke/ENGAGEMENT-BOARD-STEERING-E2E.md),
[state volumes](../../APPLICATION-STATE-VOLUMES-SCENARIOS.md),
[application artifacts](../../smoke/ENGAGEMENT-APPLICATION-ARTIFACT-E2E.md).
Saved results are in [board](../shared-board-20261115/result.json),
[volumes](../application-state-volumes-20261115/result.json) and
[artifacts](../application-artifact-20261115/result.json).
The manifest binds source and result bytes; conformance passed 900 checks with
zero failures. Scenario matrices include intended coverage beyond individual
executed assertions; the result files and scripts define what was actually run.

These local checks use simulated Docker/native runtime boundaries and real signed
contract/controller paths. Application checks also run a local HTTP service and
private connector. No Docker daemon, external provider or research target is used.
Live Docker volume behavior, provider integration of these changes, separate-host
outages and full-day research remain unverified. No new hosted CI was requested.
