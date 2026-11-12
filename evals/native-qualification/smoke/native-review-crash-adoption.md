# Contained review crash adoption check

Decision: a restart may adopt a completed review only when the pending checkpoint,
protected packet, terminal reviewer receipt, independent evidence, and published
readback projection still describe the same request. It must not call the reviewer
again. A partial or changed review holds.

Run `python3 evals/native-qualification/smoke/check_native_review_crash_adoption.py`
from the repository root. Python 3 and the checked-in source are the only inputs.
The script makes a temporary contained source-only run with a signed fixture plan,
two synthetic source-check receipts (one adverse), and a synthetic terminal fresh
review. It calls the public `continue_run` entrypoint, interrupts it at two exact
write boundaries, then calls the same entrypoint again. No provider or real target
is contacted. The temporary run is removed on exit.

Expected cases, written before the implementation:

| Interrupted or changed state | Expected restart result |
| --- | --- |
| Terminal receipt, packet, evidence, and projection persisted; checkpoint still `dispatched` | Adopt once, show the same projection to the agent, one reviewer call total |
| Reviewer receipt persisted but no projection | Hold; no reviewer or agent call |
| Projection missing or changed | Hold; no reviewer or agent call |
| Reviewer receipt missing or changed | Hold; no reviewer or agent call |
| Packet changed | Hold; no reviewer or agent call |
| Claim checkpoint or live source changed | Hold; no reviewer or agent call |
| Reviewer receipt says `unfinished`, even with a matching projection | Hold; no reviewer or agent call |

The script prints one JSON result with case outcomes, receipt/projection digests,
reviewer and agent call counts, source and check digests, and cleanup. A pass is
local synthetic recovery evidence only; it does not qualify provider review,
security impact, hosted CI, or adoption.

Saved local result: `evals/native-qualification/t02-evidence/review-crash-adoption-synthetic-20261112/result.json`.
