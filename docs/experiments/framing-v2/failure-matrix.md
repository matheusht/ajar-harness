# Framing v2 pre-implementation failure matrix

These checks were specified before the runner. The run is inadmissible if any
required check fails.

| Failure | Required check |
|---|---|
| Candidate sees the hidden oracle | Candidate prompt contains no oracle file bytes, expected verdict, or gold labels. |
| Fixture tells the candidate the answer | Source contains no `BUG`, `gold`, expected-verdict, or treatment label. |
| Framing changes available evidence | All three arms for a case receive byte-identical source and operation schemas and the same two-probe ceiling. |
| A requested probe is invented or unsafe | Reject unknown operations, extra keys, invalid actors/documents, more than two probes, shell text, or non-JSON output. |
| A receipt is fabricated | The controller imports the committed fixture and records the exact request, result, fixture hash, and exception. |
| Candidate revises its probe after seeing a result | Collect the complete probe plan in the first call and execute it once, in order. |
| A favorable failure is rerun | Every first attempt is retained; there are no candidate retries. |
| Hidden expected labels influence inference | The candidate runner never reads the oracle section until all candidate calls have completed. |
| Runner or rubric changes after inference | Verify every preregistered path against the frozen manifest before the first model call and again at completion. |
| An allocation borrows budget from another arm | Enforce two candidate calls and two probes per assignment, with no transfers. |
| Global budget is crossed | Stop before a call if the reserved per-call input/output allowance would exceed the frozen ceiling; retain the partial run. |
| CLI silently falls back or uses a tool | Require the requested model name in config, reject tool items, and retain runtime warning items. |
| A static classification is reported as search evidence | Results distinguish the selected probe plan, executed receipts, and final classification. |

No model grader is used. The hidden oracle performs fixed typed comparisons and
probe-coverage checks; semantic quality of prose remains unmeasured.
