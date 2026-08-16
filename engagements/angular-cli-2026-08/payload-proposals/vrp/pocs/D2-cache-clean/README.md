# D2 PoC kit — ng cache clean / purgeStaleBuildCache deletion

Run: `node poc.mjs`

NOTE from the independent audit (2026-08-15): the purge only removes STALE VERSION DIRECTORIES
(the victim must contain a directory child, e.g. `old-version-dir/`, for the deletion to fire).
A lone file in the victim is left alone (the isDirectory filter). The `ng cache clean` command
deletes the whole configured path; the compiled purge PoC demonstrates the build-time purge hop.

Origin: findings/D2-cache-clean-deletion/evidence/ (real-CLI run recorded in the finding REPORT).
