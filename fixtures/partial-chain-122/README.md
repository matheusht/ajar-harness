# Partial-chain acceptance, issue 122

Use one separately signed local synthetic engagement. A chain with a proven base stage and an argued later stage is recorded in the governed event ledger and projected under `unproven/`. The current hypothesis, not a new scheduler, owns the next test.

Failure cases to check before implementation:

| Case | Required result |
| --- | --- |
| Proven base, argued next stage | Schema-valid saved stages and blocker; hypothesis queued with the exact next question |
| Restart from saved ledgers | Same chain and next action; no lost partial |
| Refuted later stage | Hypothesis closed, partial evidence retained; separate base finding unchanged |
| Claimed proven stage without a real attempt | Event rejected without ledger or projection mutation |
| Secret-shaped stage text | Event rejected before saving raw text |
| Positive full-chain promotion while a stage is argued or refuted | Rejected even if other finding gates would pass |
| All stages proven | Chain guard clears; ordinary finding gates still apply |
| Complete chain added after independent review | Promotion waits for a fresh review that cites the exact chain event |

Run `HARNESS_PARTIAL_CHAIN_OUTPUT_DIR=<new directory> <project-python> tools/partial-chain-workflow-test.py` from the repository root, then `<project-python> fixtures/partial-chain-122/verify_saved.py --output <that directory>`. The test saves its synthetic ledgers, projection, scope, state, and command. It does not contact a live target or file a report.
