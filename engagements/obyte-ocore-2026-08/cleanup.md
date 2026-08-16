# cleanup.md — artifact ledger (chain-of-custody)

Every artifact the harness creates is recorded here with a revert action and status. Unresolved
cleanup **blocks pattern promotion**. Redact secrets always.

| Artifact | Type | Created (when) | Canary id | Revert action | Status |
| --- | --- | --- | --- | --- | --- |

## Canary disposal
Every canary issued gets an id and a disposal state (`live / revoked / expired`). Persistence,
memory-bleed, and residual poisoned content are themselves part of what we measure — track them.
| ~/Library/Application Support/ocore/ (empty scratch sqlite, side-effect of an out-of-lab node -e probe) | artifact | 2026-08-11 | — | deleted | done |
| docker containers p4mysql, p4mysql57 (MySQL 5.7/8.0 predicate verification) | docker | 2026-08-11 | — | docker rm -f (performed by p4 builder) | done |
| lab harness + scratch sqlite dirs (evidence/lab/.labdata-*, lab/r1/.r1data, lab/kp-f3/.kp-f3-data) | lab | 2026-08-11 | — | delete scratch dirs (contain synthetic genesis + local keys only) | done |
| lab-obyte.js symlink in the ocore tree | lab | 2026-08-11 | — | remove symlink (untracked; tree otherwise clean) | pending — remove at close |
| evidence/lab/p9|p8|p6|p1|p2|p4|r1|kp-f3 scripts + raw logs | evidence | 2026-08-11 | — | retained as engagement evidence (no secrets; synthetic keys only) | retained |
| /tmp mini-lab / f3 / f5 / lr8 throwaway probes | scratch | 2026-08-11 | — | deleted | done |
| seeded spend-proof/inputs rows in lab scratch DBs | lab | 2026-08-11 | — | destroyed with scratch dirs | done |
