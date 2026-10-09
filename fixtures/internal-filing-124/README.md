# Scoped internal filing acceptance, issue 124

The input is a separately signed synthetic engagement whose independently reviewed
claim is `confirmed` and whose proof has a primary, matched controls, replay, and
raw-output commitments. The broker may resolve only the exact internal finding
revision and report-draft requests from the active signed scope. Acceptance and
submission remain operator actions.

Failure modes to check before implementation:

| Case | Required result |
| --- | --- |
| Confirmed current claim and exact v3 proposal | One canonical internal revision, then one deterministic draft through public commands |
| Same request after commit | Exact replay reports the existing revision or draft without another effect |
| Supported, needs-review, refuted, or contaminated claim | Scope-derived approval denied; no positive finding or draft |
| Open or refuted partial chain for the full-chain ID | No scope-derived approval or positive finding |
| Stale review, scope, environment, proposal bytes, or lane | No scope-derived approval or revision |
| Missing control, replay, raw output, or claim proof | Confirmation or v3 filing fails before internal effect |
| Broker tries accept-report or record-submission | Scope-derived approval denied, report stays draft |
| Crash after immutable finding or report commit | Retry uses exact bytes, creates no duplicate event or report |

The test must save the source commit, public commands, signed-scope copy, ledgers,
finding, report manifest, report bytes, and an independent verifier result. A local
synthetic pass does not establish provider behavior, live vulnerability efficacy, or
external filing.

Run from the repository root with the existing lifecycle proof bundle:

```sh
.venv/bin/python tools/run-engagement.py --self-test --self-test-proof-output /tmp/internal-filing-source
.venv/bin/python tools/internal-filing-workflow-test.py --proof-bundle /tmp/internal-filing-source --output /tmp/internal-filing-result
.venv/bin/python fixtures/internal-filing-124/verify_saved.py --output /tmp/internal-filing-result
```

The output must report `ok: true`, then `valid: true` with every check true. The
saved `engagement/` holds the signed synthetic scope, public-command events,
attempts, artifacts, reviews, canonical finding, and draft report. `result.json`
records the exact source commit, negative outcomes, and retry results. The public
commands exercised are `request-authority`, `resolve-internal-authority`,
`settle-approved-revision`, and `generate-report`.
