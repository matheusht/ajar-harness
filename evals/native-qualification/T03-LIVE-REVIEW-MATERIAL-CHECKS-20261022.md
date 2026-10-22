# T03 live reviewer material: checks before implementation

This change preserves material from one already authorized native reviewer turn
for a later, separate post-stop assessment. It does not grant review credit.
The existing `review-<role>.json` remains a single immutable write. The new
`material` member is a projection of the transient native stdout, not the raw
stdout, shell command, shell output, target body, or native store.

| Failure | Required check |
| --- | --- |
| Missing/changed packet, wrong reviewer session, dispatch, stdout digest, or trace digest | Return a held projection with no conclusion or action. |
| Reviewer did not read all packet files or verify their hashes, returned malformed JSON, or omitted required conclusion fields | Return a held projection. The existing assessment remains unfinished. |
| Reviewer shell action failed, has empty output, is in another session, or merely appears in model prose | Do not record it as a completed shell action; no eligible action means held. |
| Tool command/output contains a secret or a large raw body | Save only action line and hashes; never save command or output text. |
| Conclusion contains credential-like text, private host path, or exceeds the bounded projection | Return a held projection with no conclusion. Do not write the unsafe text. |
| Native stdout is oversized, has too many events/actions, duplicate JSON fields, or nonfinite JSON values | Return a held projection and avoid unbounded parsing or output. |
| The reviewer adds `raw_tool_output` or another extra conclusion field, nested lead field, non-string list item, or oversized text/list | Return a held projection. Only the fixed conclusion schema may be retained. |
| The dispatch reports a plausible trace digest but the protected trace file is absent, changed, or its completed shell row hashes disagree | Return a held projection. A digest supplied by the caller alone is not evidence. |
| A JSON number such as `1e999` becomes infinity inside a conclusion or tool input | Return a held projection that can still be serialized with `allow_nan=False`; the review receipt write must not fail after the turn. |
| A short named credential such as `password: hunter2` or `X-API-Key: shortkey` appears in reviewer text | Reject the projection regardless of credential length; the durable receipt must omit the value. |
| Reviewer JSON is deeply nested or malformed after a native turn | Keep assessment unfinished and material held; return a serializable receipt even when a future independent oracle is supplied. |
| Stop occurs before independent target effect, control, or process-origin proof | Preserve the original `assessment.status=unfinished`; the projection is evidence only. |

Provider-free check: `PYTHONDONTWRITEBYTECODE=1 python3 experiments/native-review-qualification/check_live_review_material.py --output /absolute/new/private-output`. Expected `PASS`, one `result.json`, and no Docker, provider, or target call. The check uses synthetic packet and native-event bytes. A fresh live reviewer and later successor assessment remain separate work.
