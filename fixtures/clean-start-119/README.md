# #119 clean-start fixture

The target and input are synthetic. `verify.py` creates a separate target repository,
generates an ephemeral operator key, signs its initial scope, and uses public
`tools/run-engagement.py` commands for the record path. It also replays the existing
queue driver with a deterministic fake provider that reads the pinned source and
submits each event through the action broker. The operator key stays outside the
target and is deleted with the temporary fixture.

Failure modes frozen before implementation:

| Failure | Required observation |
| --- | --- |
| Scope is unsigned or its intake source/card fields are absent or malformed | `init` refuses before a research record. |
| Source path escapes the target, is a symlink/non-regular file, changes bytes, or contains a secret shape | Intake refuses before a research event or model session. |
| A routed card is outside the signed allowlist, missing, or a vuln card without `safe_signal` | The route is rejected without advancing the source frontier. |
| Model supplies another source digest, scope hash, environment, or observation reference | Broker/kernel reject the event; the queue still names the same work. |
| Run stops after any one write | Reducer resumes at the next source step without a seeded event or duplicate. |
| No route is justified | Source remains visibly unread/deferred; coverage cannot claim dry. |
| Valid source and allowed signal | Observation, route, and a bounded hypothesis are linked; `next` exposes its experiment. |

Run with the repository's pinned Python:

```sh
/Users/matheusvsky/Documents/trab/llm-redteam-harness/.venv/bin/python fixtures/clean-start-119/verify.py --output /absolute/result-directory
```

The verifier saves `result.json`, public-command transcripts, the synthetic
target, and its ledger. The pinned source is `target/inert-source.txt`, SHA256
`209f924da60336cb63194c47e2bafa6083b35c88e92c08fa4acbf94fe12c8459`.
The public `preflight` command records a `ready` local-runtime identity for that
source as `preflight-clean-start`; its reproduction argv is recorded, not run.
The expected ledger is `scope.attested`, `record.committed`,
`environment.preflight_recorded`, `observation.recorded`, `routing.assessed`,
`hypothesis.created`; the expected queue then exposes
`hypothesis_unrouted` and the source intake status is `hypothesized`.
The verifier asserts a one-file frozen denominator, the initial
`unread` state, source observation, card routing, a queued bounded hypothesis,
and a `deferred` no-route branch that remains blocking. It also checks that
invalid scope/source/card bindings fail without a new event and that a changed
source does not make historical reduction fail while new research writes stop.
The host replay must start three sessions, derive its observation from the source
text, bind all three research records to `preflight-clean-start`, and record the
same event sequence. A separate changed-source host replay must fail before
starting a session or adding a research event.

The production launcher is `tools/run-work-queue.py run` with a pinned Docker image,
Claude executable, model, and budgets. See `--help` for its complete arguments;
pass the separately signed target root as `--workspace` and its engagement directory
as `--engagement`. This fixture proves the record path through public commands and
the host driver/broker with a deterministic fake provider. It does not qualify the
Docker session, real model behavior, or a live-target experiment.
