# Contained review crash adoption check

Decision: a restart may adopt a completed review only when the pending checkpoint,
protected packet, terminal reviewer receipt, and independent evidence still describe
the same request. If the derivative readback projection was not written before the
crash, reconstruct it from those protected inputs and verify it before agent readback.
It must not call the reviewer again. A partial or changed review holds.

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
| Terminal reviewer receipt persisted but projection was never written | Rebuild and verify the derivative projection, then adopt once; one reviewer call total |
| Existing projection changed | Hold; no reviewer or agent call |
| Reviewer receipt missing or changed | Hold; no reviewer or agent call |
| Packet or selection missing or changed before projection | Hold; no reviewer or agent call; no projection written |
| Claim checkpoint or live source changed | Hold; no reviewer or agent call |
| Reviewer receipt says `unfinished`, even with a matching projection | Hold; no reviewer or agent call |

The script prints one JSON result with case outcomes, receipt/projection digests,
reviewer and agent call counts, source and check digests, and cleanup. A pass is
local synthetic recovery evidence only; it does not qualify provider review,
security impact, hosted CI, or adoption.

Saved local result: `evals/native-qualification/t02-evidence/review-crash-adoption-synthetic-20261112/result.json`.
