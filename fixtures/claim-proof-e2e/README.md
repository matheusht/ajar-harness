# Claim proof before confirmation — E2E contract

Run from this repository with a Python environment installed from
`requirements-ci.txt` (for example, `python3 -m venv .venv` followed by
`./.venv/bin/pip install -r requirements-ci.txt`). The self-test also needs
`/usr/bin/ssh-keygen`:

```sh
./.venv/bin/python tools/run-engagement.py \
  --self-test --self-test-proof-output /tmp/claim-proof-e2e-unique-run \
  > /tmp/claim-proof-e2e-unique-run.log 2>&1
```

The self-test creates a temporary, separately signed synthetic scope, registers inert
source evidence and attempts, signs an independent review, and invokes the public
`record-review` command. New confirmed events carry `confirmation_policy_version: 1`;
an unmarked historical confirmation still replays but cannot be newly appended. It
saves no target data or credentials. Choose a new output path for each run; the
command preserves synthetic positive and negative review/event records, their
reducible engagement ledgers, and a manifest with the tested Git commit. It does
not save the temporary signing key. The log includes
the `claim proof before confirmation` checks below; `RUN-ENGAGEMENT SELF-TEST: PASS`
is the expected result. Save stdout with the exact source commit when reporting a run.

| Arm | Expected result before any claim state change |
| --- | --- |
| Complete bounded mechanism, reachability, demonstrated impact, primary, matched negative and positive controls, fresh replay, and registered output | `confirmed` |
| No profile or only a second model's agreement | Rejected; prior claim state retained |
| Missing primary, negative control, or replay; wrong kind, outcome, or control linkage | Rejected; prior claim state retained |
| Wrong scope or environment; contaminated attempt; unbound, reused, or stale replay output | Rejected; prior claim state retained |
| Reviewer identity, signer, session, or origin is not independent | Rejected; prior claim state retained |
| Missing, duplicate, or mismatched atomic claim mapping; impact not demonstrated; mismatched claim/evidence link | Rejected; prior claim state retained |

The existing synthetic signing key is generated inside the temporary directory.
This check proves local kernel behavior and environment-level reachability
binding. It cannot prove that a model actually executed the recorded target
operation or qualify a live provider, Docker, or engagement. This runtime has
no target registration path, so an empty `target_refs` list cannot prove a
specific target identity.
