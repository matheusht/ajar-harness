# Checked shared learning, issue 126

Use the saved signed synthetic internal-filing result from issue 124. Its current
finding is confirmed by an independent review and cites a separate replay attempt.
The proposed winner contains only a benign objective and transferable mechanism.

Checks defined before implementation:

| Input | Expected result |
| --- | --- |
| Exact current finding, checked replay, scrubbed entry, routing ablation | One portable KB entry with finding and replay digests; future route order changes, past claim stays confirmed |
| Missing or stale finding revision, open chain, or failed/wrong replay | Deny before KB mutation |
| Entry with an engagement ID, secret-shaped text, or raw source reference | Deny before KB mutation |
| Entry whose fixture changes no route order | Deny before KB mutation |
| Loser without an evidenced held control | Deny before KB mutation |
| Exact retry | No second KB row |

Run from the repository root after producing the #124 artifact:

```sh
.venv/bin/python tools/learning-promotion-workflow-test.py --source /tmp/internal-filing-result --output /tmp/learning-promotion-result
.venv/bin/python fixtures/learning-promotion-126/verify_saved.py --output /tmp/learning-promotion-result
```

The output must say `valid: true`. It is a synthetic local check, with no live
target contact, provider inference, or claim of transfer efficacy.
