# Preflight and prerequisite follow-ups

These receipts preserve three reviewed changes made on 14 November 2026:

- `54107b21` requires one account-free read permission for initial setup.
  Execute-only scopes and ambiguous read permissions are refused. The two new
  refusal cases failed before the change; all 31 cases then passed, including an
  independent rerun.
- `c3b31449` counts only initial `source_only` or `self` permissions. Declared
  higher-rung reads cannot authorize startup or make a valid initial read
  ambiguous. Both new cases failed before the change; all 33 then passed.
- `e1c8899b` preserves safe native and environment prerequisite error codes in
  workflow status. Unexpected exceptions retain a generic private-error result.
  Two new cases failed before the change; all 16 runner cases and seven public
  CLI cases then passed.

The [manifest](manifest.json) binds each receipt to its bytes and each
implementation unit to its committed source. Independent review records state
whether the reviewer reran a check or inspected the supplied results. These
historical counts describe those revisions, not every later head.

From the repository root, with Python 3.11+ and `ssh-keygen` available:

```sh
python3 evals/native-qualification/smoke/check_engagement_preflight_e2e.py --output /tmp/oslit-preflight.json
python3 evals/native-qualification/smoke/check_engagement_runner_e2e.py --output /tmp/oslit-runner.json
python3 evals/native-qualification/smoke/check_engagement_public_cli_e2e.py --output /tmp/oslit-public-cli.json
```

Expected: every command exits zero and its JSON reports passing scenarios.
The checks create and remove owned disposable fixtures. Preflight uses signed
inputs and controlled prerequisite observations. Runner scenarios simulate
workers; the public CLI uses a deliberately unavailable native prerequisite.
No live provider, external target, Docker daemon or SSH host is contacted.
These checks establish refusal and recovery behavior, not native containment
or research acceptance.
