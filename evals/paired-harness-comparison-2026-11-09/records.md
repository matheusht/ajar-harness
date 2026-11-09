# Record contract — empty scaffold

No comparison result exists. Create the records below only in a signed,
target-local engagement after a future run. Keep the raw evidence and a redacted
index. Never fill missing values with zero. `unavailable`, `not_run`, and
`blocked` are distinct from an observed zero.

| Record | Required fields |
| --- | --- |
| Frozen manifest | Study revision; both harness commits and dirty-state checks; source archive and image digests; target state and route parity; exact model, provider endpoint and settings; enabled tools; shared limits and meter; neutral brief hash; hidden observer hash; scope and approval identities. |
| Run | Run ID; case ID; arm; order; start and stop time; status `valid`, `blocked`, `invalid`, or `unavailable`; source and target hashes; actual model and provider receipts; calls, tokens, billed cost or `unavailable`; wall time; gateway connections and bytes; prior spent allowance on resume; evidence paths; cleanup result. |
| Claim | Run ID; claim ID and revision; reported effect and severity; conditions and actor; original observation; control; clean replay; contrary evidence; independent reviewer identity; verdict `true`, `false`, or `unresolved`; `assisted` state; duplicate root ID; limitation. |
| Human help | Run ID; event time; actor; type `setup`, `hint`, `rescue`, `prompt_edit`, `reset`, `review`, or `adjudication`; exact intervention; minutes; reason; effect on research; before and after evidence references. |
| Observer | Case ID; hidden reference and validation receipt; vulnerable-path signal; fixed or denial control; supported ground-truth limit; discovered extra defects and their independent validation. Never mount this record into a researcher workspace. |
| Score | Per-arm, per-case raw totals first: true, false, unresolved, missed references, time, provider usage, help by type, assisted findings, and invalid runs. Add precision and cost-normalized values only when their denominators and usage are complete. State the size and coverage of the scored roster before any winner claim. |

The coordinator must retain failed attempts, no-finding runs, blocked setup,
retries, canceled runs, and overspend. A clean installation or an accepted
report is not a substitute for a run record. The reviewer must record its own
checks and any disagreement with the observer. Redact credentials and private
data before storing or sharing records.
