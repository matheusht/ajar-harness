# cleanup.md — artifact ledger (chain-of-custody)

Every artifact the harness creates is recorded here with a revert action and status. Unresolved
cleanup **blocks pattern promotion**. Redact secrets always.

| Artifact | Type | Created (when) | Canary id | Revert action | Status |
| --- | --- | --- | --- | --- | --- |
| _example: test skill #x_ | skill | — | — | unshare + delete | pending |

## Canary disposal
Every canary issued gets an id and a disposal state (`live / revoked / expired`). Persistence,
memory-bleed, and residual poisoned content are themselves part of what we measure — track them.
| ~/Library/Application Support/ocore/ (empty scratch sqlite, side-effect of an out-of-lab node -e probe) | artifact | 2026-08-11 | — | deleted | done |
| docker containers p4mysql, p4mysql57 (MySQL 5.7/8.0 predicate verification) | docker | 2026-08-11 | — | docker rm -f (performed by p4 builder) | done |
