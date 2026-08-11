# unproven/ — findings start here, no status field

Per `engine/finding-lifecycle.md`: every finding is written to `unproven/<FINDING_ID>/` and has **no
status field**. It reaches `findings/` only by passing the six gates
(`tools/finding_lifecycle.py gates <PKG> --engagement obyte-ocore-2026-08`): G0 paths exist, G1
primary attempt named+attested, G2 negative control named+attested, G3 privilege
`rank(proven) <= rank(claimed)` with `proven` never `not-established` for claims that must hold,
G4 adjudication corpus non-synthetic, G5 CVSS recomputes.

**Standing engagement gate (operator):** every finding ships (a) a maximum-impact runnable PoC and
(b) an independent fresh-context reviewer run of that PoC reading RAW output (recorded in
`memory/winners.md`). Builder and reviewer are different contexts.

Package layout (per goal prompt Part 9):

```
unproven/<FINDING_ID>/
  finding.json      record incl. privilege_context {claimed, proven}
  attest.json       attestations the attestable gates need
  REPORT.md         writeup
  reviews/*.json    claim_adjudication reviews (only if a reviewer actually ran)
```

Promotion is the orchestrator's act. Any role may demote with a reason. A review that did not
happen is not written — an unwritten review is an honest gap.

## Finding candidates in flight (round 1 PoC + refute)

| id | claim (one line) | round-1 status |
|---|---|---|
| (TBD) | crash family: uncaught throw on attacker-input in validation path (validation.js 1662/1678/2289/2449) | p1/p2 building |
| (TBD) | tps-fee exp() blow-up → author balance poisoning (storage.js 1228) | p6 building |
| (TBD) | is_valid_merkle_proof vacuously satisfiable (formula/evaluation.js 1763) | p9 building — orchestrator-confirmed at function level |
| (TBD) | is_valid_signed_package budget bypass via old-DAG (formula/evaluation.js 1652) | p8 building |
| (TBD) | `+sequence='good'` MySQL coercion → ball-hash divergence (main_chain.js 1401) | p4 building |
| (TBD) | getRecentTps future-timestamp multiplier inflation (storage.js 1447) | orchestrator source-confirmed; below floor likely |
