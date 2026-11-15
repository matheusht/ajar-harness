# Signed-review schema setup check

This local, synthetic workflow check addresses intermittent
`record_review_staging_budget_exceeded: live commit` refusals. The existing
10-second prewrite deadline is unchanged. Every validation still reads the current
schema bytes and validates its record; only parsing and registry construction are
reused for an exact matching schema snapshot. Each cache retains one entry.

The baseline and candidate each completed five signed reviews in alternating order.
Median whole-command times were 7.967846s and 3.714510s respectively. Each successful
command was independently checked for the exact review bytes, two appended events,
reduced snapshot and current generated views. Input copying and independent result
verification were outside the timed interval. These are macOS measurements, not
Linux performance or research qualification.

`comparison.json` records all trials, source/input hashes and environment details.
`failure-checks.json` records the focused schema mutation and refusal checks.
An initial comparison lacked two engine data files and refused before any write;
those times are excluded from the successful comparison.

## Repeat the public workflow

From the repository root, use Python with `requirements-ci.txt` installed:

```sh
python3 tools/engagement-schema-cache-test.py --expect-cache
python3 tools/run-engagement.py --self-test
```

Expect all focused checks and the full signed-review self-test to pass. The focused
check uses temporary schemas, including same-size/same-mtime edits, missing or
malformed schemas, duplicate identifiers, read failures and dependency mismatch.
The full workflow creates synthetic engagement inputs and exercises signed review
staging, live commit and failure behavior. It does not alter historical records.

The exact local timing replay, captured signed inputs, immutable source snapshots,
full self-test log and initial setup refusal remain together under
`/private/tmp/oslit-conformance-staging-20261115/`. Its `record-review-ab.py` reruns
the five pairs on the originating Mac and independently checks the writes. It needs
the captured local actor UID; only the unsigned event's session binding is renewed.
The signed review, signature and allowed-signers bytes remain fixed. This capture
is local evidence, not a portable benchmark package.
